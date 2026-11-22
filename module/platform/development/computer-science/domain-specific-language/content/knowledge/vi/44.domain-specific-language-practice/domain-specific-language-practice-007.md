# Thêm kiểm tra ngữ nghĩa

## 1. Thêm kiểm tra ngữ nghĩa trong một DSL project

Một DSL compiler thường thực hiện nhiều bước trước khi tạo artifact hoặc thực thi chương trình: đọc source, lexer, parser, xây abstract syntax tree (AST), resolve tên, kiểm tra kiểu, kiểm tra quy tắc miền, rồi mới lowering hoặc code generation. Parser xác nhận source có cấu trúc cú pháp hợp lệ, nhưng một AST hợp lệ về cú pháp vẫn có thể chứa lỗi về ý nghĩa.

**Kiểm tra ngữ nghĩa (semantic checking)** là quá trình xác nhận chương trình DSL tuân theo các quy tắc về tên, kiểu, phạm vi, quan hệ, trạng thái và invariant của miền. Thêm semantic checks giúp compiler phát hiện lỗi sớm, tạo diagnostic gần vị trí source và ngăn chương trình không hợp lệ đi tới runtime.

Ví dụ source có thể parse thành công:

~~~text
workflow "approve-order" {
    task "load-order" {
        result order = orders.load(order_id)
    }

    task "approve" {
        result approval = approval_service.approve(customer_id)
    }
}
~~~

Nhưng chương trình có thể có lỗi ngữ nghĩa:

- order_id chưa được khai báo.
- orders.load không tồn tại.
- approve yêu cầu Order nhưng nhận CustomerId.
- task approve tham chiếu order nhưng không có dependency hoặc binding hợp lệ.
- hai task có cùng identifier trong một scope cấm trùng.
- workflow thiếu terminal outcome bắt buộc.

Parser không nhất thiết phát hiện được những lỗi này vì chúng phụ thuộc symbol table, type model hoặc quy tắc nghiệp vụ. Semantic analyzer đảm nhiệm phần đó.

## 2. Phân biệt syntax checking và semantic checking

Hai bước có trách nhiệm khác nhau.

### 2.1. Syntax checking

Parser kiểm tra token có tạo thành cấu trúc được grammar cho phép hay không. Ví dụ thiếu dấu ngoặc hoặc viết sai thứ tự keyword là syntax error.

### 2.2. Semantic checking

Semantic analyzer kiểm tra cấu trúc đã parse có ý nghĩa trong context hiện tại hay không. Ví dụ gọi function không tồn tại hoặc truyền sai kiểu là semantic error.

### 2.3. Ví dụ

Syntax hợp lệ:

~~~text
let total = price + tax
~~~

Semantic error nếu price là Money còn tax là Customer:

~~~text
let total = price + tax
~~~

Grammar vẫn đúng, nhưng phép cộng không có ý nghĩa theo type system.

### 2.4. Không đưa mọi validation vào parser

Parser nên tập trung vào grammar và cấu trúc AST. Nếu parser phải tra database, resolve symbol hoặc kiểm tra policy, nó trở nên khó test, khó phục hồi sau lỗi và phụ thuộc runtime context.

### 2.5. Một số kiểm tra có thể nằm ở nhiều phase

Ví dụ duplicate declaration có thể được phát hiện khi xây symbol table. Type compatibility cần symbol đã resolve. Domain invariant có thể cần typed expression và constant evaluation.

## 3. Xác định semantic rules trước khi viết code

Trước khi thêm analyzer, hãy liệt kê quy tắc ngôn ngữ cần bảo đảm.

### 3.1. Name rules

- Mọi identifier được tham chiếu phải resolve được.
- Declaration trùng tên phải tuân scope policy.
- Import phải tồn tại và không tạo cycle nếu cycle bị cấm.
- Reference phải trỏ tới đúng loại symbol.

### 3.2. Type rules

- Operand của operator phải có kiểu phù hợp.
- Argument phải tương thích parameter.
- Return expression phải phù hợp return type.
- Nullable value phải được xử lý theo nullability policy.

### 3.3. Structural rules

- Field bắt buộc phải được khai báo.
- Block phải chứa loại statement được phép.
- Cardinality của collection phải hợp lệ.
- Một workflow phải có entry point hoặc terminal state theo contract.

### 3.4. Domain rules

- Amount không âm.
- Deadline phải sau thời điểm bắt đầu.
- State transition phải hợp lệ.
- Một operation chỉ được dùng với resource phù hợp.

### 3.5. Dependency rules

- Tham chiếu giữa task phải tồn tại.
- Dependency graph không có cycle nếu workflow yêu cầu DAG.
- Output của task phải được tạo trước khi consumer dùng.

### 3.6. Execution rules

- Có termination condition khi loop cần kết thúc.
- Side effect phải nằm trong context cho phép.
- Resource phải được đóng hoặc giải phóng.
- Policy retry và timeout phải nằm trong giới hạn.

### 3.7. Phân loại theo phase

Mỗi rule nên chỉ rõ dữ liệu cần có và phase phù hợp. Điều này tránh chạy kiểm tra quá sớm khi symbol hoặc type chưa được xác định.

## 4. Kiến trúc compiler pipeline

Semantic checking thường nằm sau parsing và name resolution, trước lowering hoặc code generation.

~~~text
Source Text
    |
    v
Lexer
    |
    v
Parser
    |
    v
AST
    |
    v
Declaration Collection
    |
    v
Name Resolution
    |
    v
Type Checking
    |
    v
Domain Semantic Checks
    |
    v
Validated Model / Typed IR
    |
    v
Lowering and Code Generation
~~~

### 4.1. Declaration collection

Thu thập declaration trước để hỗ trợ forward reference nếu language semantics cho phép.

### 4.2. Name resolution

Liên kết identifier reference với symbol declaration.

### 4.3. Type checking

Suy luận hoặc kiểm tra kiểu cho expression, function, field và operation.

### 4.4. Domain checks

Kiểm tra invariant và quan hệ riêng của miền sau khi thông tin tên và kiểu đã sẵn sàng.

### 4.5. Validated model

Downstream phase nên nhận model đã được kiểm tra hoặc có trạng thái lỗi rõ ràng, thay vì phải lặp lại việc resolve và type checking.

### 4.6. Phase dependency

Không nên kiểm tra một rule trước khi các prerequisite của nó hoàn tất. Ví dụ kiểm tra function argument type cần biết function signature và type của từng argument.

## 5. Thiết kế semantic context

Semantic context chứa thông tin analyzer cần trong quá trình duyệt AST.

### 5.1. Symbol table

Lưu declaration, scope, symbol kind, type và source location.

### 5.2. Type environment

Lưu type của biến, function, field, generic parameter và inferred expression.

### 5.3. Module context

Chứa import, exported symbol, module version và dependency.

### 5.4. Domain schema

Chứa model nghiệp vụ, state machine, constraint và operation contract.

### 5.5. Configuration

Chứa language version, feature flags và policy ảnh hưởng semantic rules.

### 5.6. Diagnostic collector

Nhận lỗi, warning và hint với source range, code và message.

### 5.7. Cancellation và budget

Compiler service hoặc IDE cần cancellation token và giới hạn thời gian/độ sâu để semantic analysis không chạy vô hạn.

## 6. Source location và diagnostic model

Semantic error cần trỏ về source chính xác để người dùng sửa được.

### 6.1. Source span

Mỗi AST node nên có source span gồm file ID, start offset và end offset. Có thể chuyển offset thành line/column ở lớp hiển thị.

### 6.2. Diagnostic code

Dùng code ổn định như SEM001 cho unknown symbol hoặc SEM120 cho type mismatch. Code ổn định giúp test, IDE và tài liệu tham chiếu.

### 6.3. Severity

- Error: chương trình không thể tiếp tục tới phase cần semantic correctness.
- Warning: construct hợp lệ nhưng có nguy cơ hoặc sắp bị loại.
- Information: thông tin bổ sung.
- Hint: gợi ý cải thiện.

### 6.4. Primary và related location

Primary location chỉ nơi lỗi được phát hiện. Related location có thể chỉ declaration liên quan, ví dụ symbol trùng tên đã khai báo ở dòng khác.

### 6.5. Expected và actual

Type mismatch nên hiển thị expected type và actual type. Unknown symbol nên nêu tên chưa resolve và context tìm kiếm.

### 6.6. Không nhúng payload nhạy cảm

Diagnostic không nên chứa secret, token hoặc toàn bộ dữ liệu đầu vào có thể nhạy cảm.

## 7. Xây dựng symbol table và scope

Name resolution là một trong những semantic checks đầu tiên cần triển khai.

### 7.1. Symbol model

~~~java
public enum SymbolKind {
    VARIABLE,
    FUNCTION,
    TYPE,
    SERVICE,
    WORKFLOW,
    CONSTANT
}

public record Symbol(
        String name,
        SymbolKind kind,
        Type type,
        SourceSpan declaration
) {
}
~~~

### 7.2. Scope

Scope chứa symbol được khai báo trong block và reference tới parent scope.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

public final class Scope {
    private final Scope parent;
    private final Map<String, Symbol> symbols = new LinkedHashMap<>();

    public Scope(Scope parent) {
        this.parent = parent;
    }

    public Optional<Symbol> declare(Symbol symbol) {
        Symbol previous = symbols.putIfAbsent(symbol.name(), symbol);
        return Optional.ofNullable(previous);
    }

    public Optional<Symbol> resolve(String name) {
        Symbol local = symbols.get(name);
        if (local != null) {
            return Optional.of(local);
        }
        return parent == null
            ? Optional.empty()
            : parent.resolve(name);
    }
}
~~~

Đây là ví dụ tối giản. Một implementation đầy đủ cần quy định case sensitivity, namespace, import precedence, overload set và shadowing policy.

### 7.3. Duplicate declaration

Khi declare trả về symbol cũ, analyzer phát diagnostic tại declaration mới và có thể thêm related location trỏ declaration trước.

### 7.4. Shadowing

Nếu nested scope cho phép shadowing, symbol ở scope trong che symbol ở scope ngoài. Nếu không cho phép, analyzer cần tìm symbol ở parent và báo lỗi theo policy.

### 7.5. Forward reference

Nếu language cho phép tham chiếu declaration ở phía sau, cần collect declaration trước rồi mới resolve reference. Nếu không cho phép, resolver phải giữ thứ tự visibility.

### 7.6. Scope lifetime

Scope của block nên được tạo và đóng theo cấu trúc AST. Không chia sẻ mutable scope giữa các compilation unit nếu không có ownership rõ.

## 8. Name resolution

Name resolution biến identifier text thành reference tới declaration cụ thể.

### 8.1. Identifier expression

Với mỗi identifier, resolver tìm symbol theo scope và namespace.

### 8.2. Field access

Với customer.address.city, resolver phải resolve customer trước, sau đó kiểm tra type có field address và type tiếp theo có field city.

### 8.3. Function call

Resolver tìm function theo tên và module/import context, sau đó chọn overload phù hợp nếu language hỗ trợ.

### 8.4. Import

Import cần resolve module path, version và exported symbol. Circular import phải theo policy rõ.

### 8.5. Unknown symbol

Nếu không tìm thấy symbol, phát diagnostic và gắn ErrorSymbol hoặc ErrorType để analyzer có thể tiếp tục.

### 8.6. Ambiguous symbol

Nếu nhiều symbol cùng phù hợp, báo ambiguity thay vì chọn ngẫu nhiên.

### 8.7. Binding identity

Typed AST nên giữ symbol ID hoặc reference trực tiếp, không chỉ giữ tên string. Điều này giúp các phase sau tránh resolve lại.

## 9. Type checking

Type checking xác nhận expression và operation sử dụng giá trị có kiểu tương thích.

### 9.1. Type model

Type model có thể gồm Boolean, Integer, Decimal, String, Duration, Money, Record, List, Optional, Function và ErrorType.

### 9.2. Expression typing

Mỗi expression được gán một type. Ví dụ comparison thường trả Boolean; arithmetic phụ thuộc operator và operand types.

### 9.3. Assignment

Kiểm tra kiểu expression bên phải có assignable vào biến hoặc field bên trái không.

### 9.4. Function call

Kiểm tra arity, argument type, generic inference và return type.

### 9.5. Operator typing

Định nghĩa operator signature. Ví dụ cộng hai Money cần cùng currency hoặc một conversion rule rõ.

### 9.6. Nullability

Kiểm tra dereference nullable value và xử lý optional theo semantics của DSL.

### 9.7. Type coercion

>Implicit conversion có thể tiện nhưng cần giới hạn để tránh thay đổi precision hoặc unit âm thầm.

### 9.8. ErrorType

>ErrorType giúp ngăn hàng loạt diagnostic thứ cấp sau lỗi type đầu tiên. Khi một operand đã có ErrorType, analyzer có thể tránh báo thêm mismatch không hữu ích.

## 10. Kiểm tra kiểu trong Java

Một type checker có thể trả type cùng diagnostic thay vì chỉ trả boolean.

### 10.1. Type result

~~~java
public record TypeResult(
        Type type,
        java.util.List<Diagnostic> diagnostics
) {
}
~~~

### 10.2. Binary expression

~~~java
public TypeResult checkBinary(
        BinaryExpression expression,
        SemanticContext context
) {
    TypeResult left = checkExpression(expression.left(), context);
    TypeResult right = checkExpression(expression.right(), context);

    if (left.type().isError() || right.type().isError()) {
        return TypeResult.error();
    }

    return operatorTyping.resolve(
        expression.operator(),
        left.type(),
        right.type(),
        expression.span()
    );
}
~~~

Ví dụ minh họa cần được điều chỉnh theo Type model và Diagnostic API của project. Điểm quan trọng là operator typing phải là một quy tắc tập trung, không rải điều kiện type ở nhiều visitor.

### 10.3. Assignability

~~~java
public boolean isAssignable(Type source, Type target) {
    if (source.isError() || target.isError()) {
        return true;
    }
    if (source.equals(target)) {
        return true;
    }
    return conversions.hasSafeImplicitConversion(source, target);
}
~~~

### 10.4. Conversion policy

Implicit conversion nên được phân loại safe, lossy hoặc forbidden. Với tiền tệ, thời gian và identifier, conversion cần đặc biệt tường minh.

## 11. Kiểm tra declaration và schema

DSL thường cho phép khai báo object, record, service hoặc workflow.

### 11.1. Required field

Kiểm tra mọi field bắt buộc đã được cung cấp hoặc có default hợp lệ.

### 11.2. Unknown field

>Nếu object khai báo field không tồn tại trong schema, báo diagnostic thay vì âm thầm bỏ qua.

### 11.3. Duplicate field

>Phát hiện field được gán nhiều lần nếu schema không cho phép override.

### 11.4. Field type

>Kiểm tra type của value với declared field type.

### 11.5. Range và pattern

>Kiểm tra constant value có nằm trong range hoặc khớp pattern hay không.

### 11.6. Default value

>Default cần được type-check và chỉ áp dụng theo presence semantics đã định nghĩa.

### 11.7. Schema version

>Schema import từ bên ngoài cần version hoặc digest để build reproducible.

## 12. Domain invariant và business rules

Semantic checking có thể kiểm tra quy tắc riêng của miền thay vì chỉ type.

### 12.1. Numeric invariant

>Ví dụ amount phải không âm, percentage nằm trong khoảng cho phép hoặc quantity phải lớn hơn zero.

### 12.2. Temporal invariant

>Ví dụ end time phải sau start time, deadline không vượt policy limit hoặc schedule không có khoảng thời gian xung đột.

### 12.3. State transition

>Kiểm tra transition từ state hiện tại sang state mới có được phép trong state machine hay không.

### 12.4. Cross-field invariant

>Ví dụ currency phải phù hợp payment method hoặc country; nếu một field phụ thuộc field khác, analyzer cần context đủ để kiểm tra.

### 12.5. Referential invariant

>Kiểm tra reference tới resource, tenant hoặc module tồn tại và có scope phù hợp.

### 12.6. Static versus runtime validation

>Nếu giá trị được biết lúc compile, kiểm tra tĩnh. Nếu phụ thuộc input runtime, tạo validation plan hoặc runtime guard thay vì giả vờ biết trước kết quả.

## 13. Kiểm tra workflow và dependency graph

Với DSL workflow, nhiều quy tắc phụ thuộc quan hệ giữa các task.

### 13.1. Build graph

>Tạo node cho task và edge cho dependency.

### 13.2. Missing dependency

>Tham chiếu tới task không tồn tại phải được báo lỗi.

### 13.3. Cycle detection

>Nếu workflow yêu cầu DAG, dùng DFS hoặc topological sort để phát hiện cycle và chỉ ra các task liên quan.

### 13.4. Output availability

>Kiểm tra output được dùng sau khi producer hoàn thành và trên mọi path hợp lệ.

### 13.5. Parallel conflict

>Hai task chạy song song có thể ghi cùng resource. Analyzer có thể phát cảnh báo nếu DSL không khai báo synchronization hoặc ownership.

### 13.6. Terminal state

>Kiểm tra mọi path có thể đi tới terminal state hoặc có policy xử lý failure/cancellation.

### 13.7. Retry và compensation

>Kiểm tra retry policy có giới hạn hợp lệ và compensation tham chiếu tới side effect đã khai báo.

## 14. Kiểm tra control flow và reachability

Semantic analyzer có thể phân tích đường đi trong function hoặc workflow.

### 14.1. Unreachable statement

>Statement sau một return hoặc unconditional transition có thể không bao giờ chạy.

### 14.2. Missing return

>Function khai báo return type nhưng có path không trả về giá trị cần thiết.

### 14.3. Definite assignment

>Biến phải được gán trước khi đọc trên mọi path hợp lệ.

### 14.4. Exhaustive branch

>Match hoặc decision branch cần bao phủ mọi variant nếu language yêu cầu exhaustive.

### 14.5. Infinite loop

>Compiler có thể phát hiện một số vòng lặp rõ ràng không có điều kiện thoát, nhưng không nên tuyên bố chứng minh termination cho mọi chương trình nếu không có phân tích đủ mạnh.

### 14.6. Data flow

>Data-flow analysis có thể theo dõi taint, nullability, resource ownership hoặc giá trị constant.

## 15. Kiểm tra effect và capability

DSL có thể cần phân biệt expression thuần với thao tác có side effect.

### 15.1. Effect annotation

>Function có thể khai báo read, write, network, filesystem hoặc external-call effect.

### 15.2. Context permission

>Block chỉ được gọi operation nằm trong capability được cấp. Ví dụ policy evaluation có thể cấm network access.

### 15.3. Pure expression

>Expression thuần có thể được constant-fold hoặc cache an toàn hơn.

### 15.4. Resource lifetime

>File, stream, lock hoặc transaction cần được đóng hoặc kết thúc theo scope.

### 15.5. Secret flow

>Analyzer có thể ngăn secret value chảy vào output công khai, log hoặc telemetry.

### 15.6. Static limitation

>Một số effect chỉ biết ở runtime do dynamic dispatch hoặc plugin. Compiler cần đánh dấu unknown effect và áp dụng runtime policy.

## 16. Error recovery và tiếp tục phân tích

>Một semantic error không nên luôn làm analyzer dừng ngay lập tức.

### 16.1. Error symbol

>Khi identifier không resolve, tạo ErrorSymbol để các phase sau không phát sinh nhiều lỗi thứ cấp.

### 16.2. Error type

>Expression có lỗi type có thể mang ErrorType để visitor tiếp tục xử lý node khác.

### 16.3. Diagnostic suppression

>Suppress lỗi phụ thuộc trực tiếp vào lỗi gốc để tránh làm người dùng quá tải.

### 16.4. Continue independent checks

>Nếu một task lỗi type, analyzer vẫn có thể kiểm tra task khác độc lập.

### 16.5. Error budget

>IDE có thể giới hạn số diagnostic hoặc thời gian analysis để không làm UI treo khi source đang dở.

### 16.6. Partial model

>Compiler có thể tạo partial semantic model cho IDE, nhưng code generation hoặc execution phải từ chối nếu còn semantic error bắt buộc.

## 17. Thiết kế semantic analyzer theo visitor hoặc pass

>Có thể triển khai analyzer bằng visitor hoặc nhiều pass chuyên biệt.

### 17.1. Visitor

>Visitor phù hợp khi mỗi AST node cần được duyệt theo cấu trúc và context. Nó giúp gom logic theo node type.

### 17.2. Multiple passes

>Separate passes phù hợp khi mỗi kiểm tra có prerequisite riêng như declaration collection, resolution, typing và domain validation.

### 17.3. Pass contract

>Mỗi pass nên nêu input invariant, output metadata, diagnostics và điều kiện chạy.

### 17.4. Avoid duplicated traversal

>Nếu AST lớn, nhiều pass có thể tốn thời gian. Có thể gộp những kiểm tra độc lập trong một traversal khi không làm semantics khó hiểu.

### 17.5. Deterministic order

>Diagnostic order nên ổn định theo source order hoặc quy tắc được công bố để test và editor không bị dao động.

### 17.6. Incremental analysis

>IDE có thể chỉ chạy lại pass cho file hoặc dependency bị ảnh hưởng, nhưng phải invalidation đúng khi symbol hoặc schema thay đổi.

## 18. Semantic pipeline minh họa bằng Java

Một compiler service có thể tổ chức các pass qua interface chung.

### 18.1. Semantic pass

~~~java
public interface SemanticPass {
    void analyze(
        AstNode root,
        SemanticContext context,
        DiagnosticSink diagnostics
    );
}
~~~

### 18.2. Pipeline

~~~java
public final class SemanticPipeline {
    private final java.util.List<SemanticPass> passes;

    public SemanticPipeline(java.util.List<SemanticPass> passes) {
        this.passes = java.util.List.copyOf(passes);
    }

    public SemanticResult analyze(AstNode root, SemanticContext context) {
        DiagnosticCollector diagnostics = new DiagnosticCollector();
        for (SemanticPass pass : passes) {
            if (context.isCancelled()) {
                break;
            }
            pass.analyze(root, context, diagnostics);
        }
        return new SemanticResult(
            context.semanticModel(),
            diagnostics.snapshot()
        );
    }
}
~~~

Đây là cấu trúc khái niệm. Trong project thực tế, pipeline cần thể hiện dependency giữa pass và ngăn pass downstream chạy khi prerequisite chưa đạt.

### 18.3. Diagnostic

~~~java
public record Diagnostic(
        String code,
        Severity severity,
        String message,
        SourceSpan primary,
        java.util.List<RelatedLocation> related
) {
}
~~~

### 18.4. Analyzer result

~~~java
public record SemanticResult(
        SemanticModel model,
        java.util.List<Diagnostic> diagnostics
) {
    public boolean hasErrors() {
        return diagnostics.stream()
            .anyMatch(d -> d.severity() == Severity.ERROR);
    }
}
~~~

## 19. Ví dụ thêm một semantic rule

Giả sử DSL khai báo workflow có task ID duy nhất trong cùng workflow.

### 19.1. Quy tắc

~~~text
workflow "checkout" {
    task "reserve-stock" { ... }
    task "charge-payment" { ... }
    task "reserve-stock" { ... }
}
~~~

Hai task có cùng ID nên cần diagnostic.

### 19.2. Analyzer

~~~java
public final class UniqueTaskIdPass implements SemanticPass {
    @Override
    public void analyze(
            AstNode root,
            SemanticContext context,
            DiagnosticSink diagnostics
    ) {
        for (WorkflowNode workflow : AstQueries.workflows(root)) {
            java.util.Map<String, TaskNode> seen = new java.util.HashMap<>();

            for (TaskNode task : workflow.tasks()) {
                TaskNode previous = seen.putIfAbsent(task.id(), task);
                if (previous != null) {
                    diagnostics.report(new Diagnostic(
                        "SEM-WF-001",
                        Severity.ERROR,
                        "Task identifier is duplicated: " + task.id(),
                        task.idSpan(),
                        java.util.List.of(
                            new RelatedLocation(
                                previous.idSpan(),
                                "First declaration is here"
                            )
                        )
                    ));
                }
            }
        }
    }
}
~~~

Ví dụ giả định AST đã có WorkflowNode và TaskNode. Rule này chỉ kiểm tra uniqueness trong một workflow; nếu scope policy khác, cần thay phạm vi map tương ứng.

### 19.3. Diagnostic location

Primary location nên nằm ở declaration trùng thứ hai; related location trỏ declaration đầu tiên để người dùng tìm được nguyên nhân.

### 19.4. Stable diagnostic code

Code SEM-WF-001 có thể được dùng trong test, IDE và tài liệu. Message có thể được cải thiện mà không đổi code.

## 20. Kết nối semantic checks với DSL schema

Không nên hard-code mọi domain rule trong analyzer nếu DSL cho phép người dùng khai báo schema.

### 20.1. Schema-driven checks

Semantic analyzer đọc schema để kiểm tra field, type, required value, enum và constraint.

### 20.2. Rule registry

>Domain rule có thể được đăng ký theo node kind hoặc annotation. Registry giúp thêm rule mà không sửa một visitor khổng lồ.

### 20.3. Rule priority

>Nếu rule phụ thuộc nhau, registry cần thứ tự hoặc dependency graph rõ ràng.

### 20.4. Custom validator

>Plugin có thể cung cấp validator nhưng phải có contract về input model, output diagnostic, timeout và capability.

### 20.5. Schema version

>Semantic rule cần gắn với schema version để cùng source không bị diễn giải khác khi schema đổi ngoài ý muốn.

## 21. Kiểm thử semantic checks

 Mỗi semantic rule nên có fixture thể hiện source hợp lệ và source không hợp lệ.

### 21.1. Positive fixture

>Source hợp lệ phải không có diagnostic tương ứng và tạo semantic model mong đợi.

### 21.2. Negative fixture

>Source sai phải phát đúng diagnostic code và source range.

### 21.3. Boundary fixture

>Với range hoặc threshold, kiểm tra giá trị ngay dưới, đúng tại và ngay trên boundary.

### 21.4. Scope fixture

>Kiểm tra nested scope, shadowing, import và forward reference theo policy.

### 21.5. Error recovery fixture

>Một lỗi không nên ngăn analyzer phát hiện lỗi độc lập ở declaration khác.

### 21.6. Golden diagnostics

>Snapshot diagnostic có thể kiểm tra code, severity, message và location. Nên tránh phụ thuộc formatting không ổn định nếu không phải contract.

### 21.7. Property-based tests

>Sinh AST hoặc source hợp lệ và kiểm tra invariant tổng quát, ví dụ mọi symbol reference đã resolve đều trỏ tới declaration có kind phù hợp.

### 21.8. Mutation tests

>Mutation testing có thể kiểm tra test suite có phát hiện khi một semantic condition bị bỏ hoặc đảo hay không. Đây là hoạt động đánh giá test riêng, không phải logic runtime của analyzer.

## 22. Performance và incremental semantic analysis

Semantic checking có thể chạy trên project lớn hoặc mỗi lần người dùng gõ.

### 22.1. Avoid repeated lookup

>Cache symbol resolution hoặc type result theo compilation snapshot khi có thể.

### 22.2. Index by symbol ID

>Reference trực tiếp tới symbol ID giảm việc tìm kiếm lại theo string.

### 22.3. Dependency invalidation

>Khi declaration thay đổi, chỉ invalidation các file hoặc pass phụ thuộc vào symbol đó nếu dependency graph đủ chính xác.

### 22.4. Cancellation

>Hủy analysis cũ khi source version mới đến. Không để nhiều task obsolete cùng giữ AST và symbol graph.

### 22.5. Bounded analysis

>Giới hạn recursion depth, graph traversal và thời gian xử lý cho source không tin cậy.

### 22.6. Determinism

>Cache và parallel pass không được làm diagnostic order hoặc semantic result thay đổi ngẫu nhiên.

### 22.7. Profile before optimizing

>Đo thời gian từng pass, số symbol, số type constraint và memory trước khi thay cấu trúc dữ liệu.

## 23. Những sai lầm thường gặp

### 23.1. Đưa business validation vào parser

Parser trở nên phụ thuộc schema và runtime context. Giữ grammar parsing riêng, đặt domain checks trong semantic phase.

### 23.2. Chạy kiểm tra sai thứ tự

Type check trước name resolution có thể tạo lỗi thứ cấp. Khai báo dependency giữa pass.

### 23.3. Chỉ trả về boolean

Boolean không đủ để giải thích lỗi. Trả diagnostic có code, location và related information.

### 23.4. Dừng ngay ở lỗi đầu tiên

Compiler hoặc IDE mất khả năng báo các lỗi độc lập khác. Dùng ErrorSymbol/ErrorType và tiếp tục khi an toàn.

### 23.5. Resolve lại symbol ở nhiều nơi

>Logic phân tán có thể cho kết quả khác nhau. Tạo semantic model dùng chung.

### 23.6. Hard-code domain rules

>Rule khó thay đổi và khó version hóa. Dùng schema hoặc registry khi rule thực sự cấu hình được.

### 23.7. Chấp nhận implicit conversion quá rộng

>Type checking trở nên khó đoán và có thể mất precision hoặc unit. Giới hạn conversion và báo rõ.

### 23.8. Không giữ source span

>Diagnostic không thể trỏ đúng vị trí. Mọi AST node và symbol declaration cần source location phù hợp.

### 23.9. Không xử lý cancellation

>Language server có thể tích lũy semantic jobs cũ. Truyền cancellation token qua mọi pass.

### 23.10. Chỉ test happy path

>Không phát hiện duplicate, unknown symbol, type mismatch, cycle và boundary error. Dùng positive, negative và boundary fixtures.

## 24. Quy trình thêm semantic check vào DSL project

1. **Đọc language contract.** Xác định construct, type, scope và domain invariant liên quan.
2. **Viết rule statement.** Mô tả điều kiện hợp lệ, điều kiện lỗi và phạm vi áp dụng bằng ngôn ngữ rõ ràng.
3. **Xác định prerequisite.** Chỉ ra cần AST, symbol resolution, type information, schema hay control-flow graph.
4. **Chọn phase.** Đặt check vào pass phù hợp sau khi dữ liệu cần thiết đã sẵn sàng.
5. **Xác định diagnostic.** Chọn code, severity, primary range, related location và remediation hint.
6. **Cập nhật semantic context.** Thêm metadata hoặc registry nếu rule cần.
7. **Triển khai pass.** Giữ rule tập trung, deterministic và có cancellation support.
8. **Tích hợp pipeline.** Khai báo dependency và điều kiện chạy của pass.
9. **Tạo fixtures.** Có source hợp lệ, không hợp lệ, boundary, nested scope và recovery case.
10. **Kiểm tra downstream.** Đảm bảo code generation hoặc execution không tiếp tục khi có semantic error bắt buộc.
11. **Cập nhật tooling.** Hiển thị diagnostic trong editor và hỗ trợ navigation nếu cần.
12. **Theo dõi performance.** Đo thời gian và memory của pass trên project đại diện.
13. **Version rule.** Nếu semantics thay đổi theo language version hoặc schema, gắn rule với version tương ứng.
14. **Tài liệu hóa.** Giải thích quy tắc, ví dụ lỗi và cách sửa.

## 25. Câu hỏi tự kiểm tra

1. Semantic checking khác parsing như thế nào?
2. Những nhóm semantic rules nào thường xuất hiện trong DSL?
3. Vì sao cần xác định prerequisite và thứ tự semantic passes?
4. Semantic context nên chứa những thành phần nào?
5. Symbol table và scope hỗ trợ name resolution ra sao?
6. Làm thế nào phát hiện duplicate declaration, shadowing và unknown symbol?
7. Type checker nên xử lý ErrorType để giảm diagnostic cascade như thế nào?
8. Domain invariant khác type constraint ra sao?
9. Workflow dependency graph có thể được kiểm tra cycle và output availability như thế nào?
10. Control-flow analysis có thể phát hiện unreachable statement và missing return ra sao?
11. Effect checking và capability checking giúp kiểm soát side effect như thế nào?
12. Diagnostic cần có code, severity, source span và related location vì sao?
13. Error recovery giúp IDE tiếp tục phân tích sau semantic error như thế nào?
14. Visitor và multiple-pass architecture có trade-off gì?
15. Làm thế nào kết nối semantic analyzer với schema hoặc rule registry?
16. Positive, negative, boundary và recovery fixture kiểm tra những trường hợp nào?
17. Incremental analysis cần invalidation và cancellation ra sao?
18. Những lỗi thiết kế nào khiến semantic analyzer khó bảo trì?
19. Hãy mô tả cách thêm rule phát hiện task ID trùng trong workflow DSL.
20. Hãy đề xuất một semantic check cho state transition, gồm prerequisite, diagnostic và các fixture cần có.
