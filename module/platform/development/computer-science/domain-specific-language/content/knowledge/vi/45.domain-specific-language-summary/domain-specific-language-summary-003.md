# Danh sách kiểm tra chất lượng

## 1. Mục đích của danh sách kiểm tra chất lượng DSL

Một DSL (*Domain-Specific Language*) có thể bắt đầu từ vài declaration đơn giản rồi phát triển thành một ngôn ngữ có grammar, type system, compiler, runtime, plugin, API, tài liệu và hệ sinh thái tooling. Khi quy mô tăng, chất lượng không còn phụ thuộc riêng vào việc parser có đọc được source hay không.

**Danh sách kiểm tra chất lượng (*quality checklist*)** là tập hợp câu hỏi và tiêu chí giúp team đánh giá một DSL trong suốt vòng đời thiết kế, triển khai, sử dụng và vận hành. Checklist tạo một cách nhìn chung về những gì cần được xác định, kiểm chứng và lưu bằng chứng.

Checklist này dùng để:
- Định hướng thiết kế DSL mới.
- Review thay đổi grammar hoặc semantics.
- Đánh giá compiler và runtime.
- Kiểm tra trải nghiệm của người viết DSL.
- Xem xét security, reliability và performance.
- Xác nhận interoperability với hệ thống khác.
- Đánh giá tài liệu và developer tooling.
- Chuẩn bị release và vận hành production.
- Theo dõi rủi ro và các khoản nợ kỹ thuật.

Đây là tài liệu hướng dẫn cách tổ chức một quality checklist. Việc áp dụng checklist cho một project cụ thể cần bằng chứng từ source, tests, runtime và quy trình của chính project đó.

## 2. Cách sử dụng checklist

Một checklist có giá trị khi mỗi câu hỏi gắn với phạm vi, người chịu trách nhiệm và bằng chứng.

### 2.1. Trạng thái của từng mục

Có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Not assessed | Chưa xem xét |
| Pass | Có bằng chứng đáp ứng |
| Fail | Có bằng chứng chưa đáp ứng |
| Blocked | Chưa thể đánh giá do dependency hoặc quyền truy cập |
| Not applicable | Không áp dụng, kèm lý do |
| Planned | Có kế hoạch và owner |
| Accepted risk | Rủi ro được người có thẩm quyền chấp nhận |

Không nên dùng Not applicable chỉ để bỏ qua một mục khó. Cần ghi lý do và phạm vi áp dụng.

### 2.2. Bằng chứng

Bằng chứng có thể gồm:
- Architecture decision record.
- Language specification.
- Grammar source và parser tests.
- Compiler diagnostics.
- Unit/integration/property tests.
- Benchmark và load test reports.
- Threat model và security review.
- API/schema compatibility reports.
- Documentation examples.
- Release notes.
- Operational dashboards và runbooks.

Một checkbox được đánh dấu Pass nên có link, file, test result hoặc người xác nhận tương ứng.

### 2.3. Owner và thời điểm

Mỗi mục nên có:
- Owner chịu trách nhiệm.
- Reviewer nếu cần.
- Milestone hoặc release.
- Evidence location.
- Risk/impact nếu chưa hoàn tất.
- Ngày đánh giá lại nếu có thể thay đổi theo thời gian.

### 2.4. Critical gates và improvements

Không phải mọi mục đều có cùng mức độ quan trọng.

**Release blocker** thường là:
- Parser hoặc runtime có thể thực thi sai semantics.
- Có đường bypass authorization.
- Có khả năng mất hoặc làm hỏng dữ liệu.
- Untrusted input có thể làm cạn tài nguyên mà không có giới hạn.
- Breaking change không có migration hoặc thông báo phù hợp.
- Artifact phát hành không tái lập hoặc không xác định nguồn gốc.

**Improvement** có thể là:
- Tối ưu autocomplete.
- Thêm syntax diagram.
- Cải thiện search.
- Giảm compile latency trong một workload không critical.
- Bổ sung thêm ví dụ cho construct ít dùng.

Việc phân loại phải dựa trên risk và release policy của project.

## 3. Product goals và phạm vi DSL

Trước khi đánh giá kỹ thuật, cần xác nhận ngôn ngữ giải quyết đúng vấn đề.

- [ ] Mục tiêu chính của DSL được mô tả bằng các use case cụ thể.
- [ ] Đối tượng người dùng được xác định: domain expert, developer, operator hay nhiều nhóm.
- [ ] Các tác vụ cốt lõi mà DSL cần hỗ trợ đã được liệt kê.
- [ ] Những việc DSL không nhằm giải quyết cũng được nêu rõ.
- [ ] Lợi ích so với configuration file, API hoặc general-purpose language được giải thích.
- [ ] Các domain concepts có định nghĩa thống nhất.
- [ ] Phạm vi của phiên bản đầu tiên có giới hạn và có thứ tự ưu tiên.
- [ ] Các non-goals không bị biến thành feature mặc định ngoài kế hoạch.
- [ ] Success criteria có thể đo được.
- [ ] Có ví dụ end-to-end đại diện cho workload thực tế.
- [ ] Có feedback từ người dùng mục tiêu.
- [ ] Có owner chịu trách nhiệm về product direction và language governance.

### 3.1. Câu hỏi review

- Người dùng có thể hoàn thành tác vụ chính với ít bước và ít cấu hình hơn không?
- DSL có từ vựng gần với domain mà không che giấu các khái niệm quan trọng không?
- Người dùng có thể hiểu source mà không phải biết implementation nội bộ không?
- Các use case phổ biến có được ưu tiên hơn các edge case hiếm gặp không?
- Có lý do rõ ràng cho từng abstraction quan trọng không?

## 4. Language design và consistency

Ngôn ngữ cần có mô hình khái niệm nhất quán để người dùng không phải học nhiều ngoại lệ.

- [ ] Mỗi construct có một mục đích rõ.
- [ ] Tên keyword, declaration và type nhất quán.
- [ ] Cú pháp thể hiện được sự khác nhau giữa declaration, expression và statement.
- [ ] Scope và visibility rules được xác định.
- [ ] Mutability và side effects được xác định.
- [ ] Default values có semantics rõ.
- [ ] Null, absent, optional và default được phân biệt.
- [ ] Evaluation order được xác định.
- [ ] Error propagation được xác định.
- [ ] Các construct tương tự có behavior tương tự hoặc có giải thích cho khác biệt.
- [ ] Không có hai cú pháp khác nhau cùng biểu diễn một behavior mà không có lý do.
- [ ] Syntax sugar có mapping rõ về core model.
- [ ] Reserved words và contextual keywords được quản lý.
- [ ] Naming conventions được tài liệu hóa.
- [ ] Explicit override có quy tắc rõ.
- [ ] Convention-derived values có thể được giải thích trong tooling.
- [ ] Các quyết định ngôn ngữ quan trọng có rationale và owner.

### 4.1. Cognitive load

- [ ] Người mới có thể đọc một chương trình mẫu mà không cần hiểu toàn bộ language internals.
- [ ] Các construct thường dùng có cú pháp ngắn và dễ nhớ.
- [ ] Các construct nguy hiểm hoặc hiếm gặp không bị ẩn sau shorthand khó nhận biết.
- [ ] Abstraction không yêu cầu người dùng nhớ quá nhiều implicit rules.
- [ ] Có ví dụ thể hiện cách đọc và cách viết.
- [ ] Error messages dùng thuật ngữ gần với source language.

## 5. Grammar và lexical rules

Parser phải nhận diện chính xác ngôn ngữ được công bố.

- [ ] Grammar source được quản lý trong version control.
- [ ] Root production xác định cấu trúc toàn chương trình.
- [ ] Lexer rules và parser rules được phân biệt.
- [ ] Terminal và nonterminal được định nghĩa rõ.
- [ ] Identifier start/continue rules được công bố.
- [ ] Case sensitivity được xác định.
- [ ] Reserved và contextual keywords có danh sách.
- [ ] String literal và escape rules được mô tả.
- [ ] Numeric literal formats được mô tả.
- [ ] Boolean/null/special literals được định nghĩa.
- [ ] Comment syntax và nesting behavior được xác định.
- [ ] Whitespace và newline semantics được xác định.
- [ ] Unicode support và normalization policy được xác định.
- [ ] Encoding và BOM behavior được xác định.
- [ ] Operator list đầy đủ.
- [ ] Precedence và associativity có bảng chính thức.
- [ ] Parentheses và grouping behavior rõ ràng.
- [ ] Ambiguous grammar đã được xử lý hoặc có rule precedence.
- [ ] Parser yêu cầu end-of-input ở đúng entry point.
- [ ] Grammar thay đổi có changelog và compatibility impact.

### 5.1. Parser behavior

- [ ] Syntax errors có source range chính xác.
- [ ] Lexer errors và parser errors có thể phân biệt.
- [ ] Parser recovery không tạo model được execute nhầm.
- [ ] Error recovery có giới hạn và không làm parser treo.
- [ ] Diagnostics không bị lặp quá mức.
- [ ] Parser xử lý input rỗng và input malformed.
- [ ] Parser có giới hạn nesting và input size.
- [ ] Parser behavior ổn định giữa các lần chạy cùng version.
- [ ] Parser tests bao phủ valid, invalid và boundary cases.

## 6. Semantics và type system

Source parse được không đồng nghĩa chương trình hợp lệ hoặc có behavior đúng.

- [ ] Name resolution và namespace rules được xác định.
- [ ] Duplicate declaration behavior rõ.
- [ ] Scope lookup order rõ.
- [ ] Type model có định nghĩa.
- [ ] Type inference rules được mô tả nếu có.
- [ ] Assignment compatibility được xác định.
- [ ] Numeric conversion và overflow behavior rõ.
- [ ] Generic constraints được kiểm tra.
- [ ] Nullability và optionality có semantics.
- [ ] Function parameter và return rules được xác định.
- [ ] Operator semantics nhất quán với precedence.
- [ ] Short-circuit behavior được mô tả nếu hỗ trợ.
- [ ] Pattern matching có exhaustiveness rules nếu phù hợp.
- [ ] Domain constraints được phân biệt với syntax constraints.
- [ ] Static semantics được kiểm tra trước runtime khi có thể.
- [ ] Dynamic semantics có thứ tự thực thi rõ.
- [ ] Side effects được phân loại.
- [ ] Determinism requirements được xác định.
- [ ] Undefined hoặc implementation-defined behavior được hạn chế và công bố.

### 6.1. Semantic tests

- [ ] Có test cho type compatibility.
- [ ] Có test cho invalid references.
- [ ] Có test cho overload resolution.
- [ ] Có test cho precedence và associativity.
- [ ] Có test cho null/absent/default.
- [ ] Có test cho scope shadowing.
- [ ] Có test cho evaluation order.
- [ ] Có test cho side effects và error propagation.
- [ ] Có regression tests cho semantic bugs đã gặp.

## 7. Compiler và build pipeline

Compiler cần tạo kết quả xác định, diagnostics có ích và artifact có thể tái lập.

- [ ] Các phase parse, resolve, type-check, optimize và generate được xác định.
- [ ] Intermediate representation có schema và ownership rõ.
- [ ] Mỗi phase có diagnostics và error boundaries phù hợp.
- [ ] Compiler không thực hiện side effect không được phép trong compile phase.
- [ ] Generated artifacts có provenance.
- [ ] Source mapping được giữ qua transformation.
- [ ] Build output ổn định với cùng inputs.
- [ ] Compiler version và language version được ghi.
- [ ] Dependency resolution có version pinning hoặc lock mechanism.
- [ ] Incremental compilation invalidates đúng dependency.
- [ ] Cache key chứa đầy đủ inputs liên quan.
- [ ] Cache có size limit và eviction.
- [ ] Build failure không để lại artifact nửa chừng được coi là hợp lệ.
- [ ] Compiler có timeout và resource limits.
- [ ] Build logs không chứa secret.
- [ ] Compiler hỗ trợ cancellation nếu build bị hủy.
- [ ] Generated code có thể truy ngược về DSL source.
- [ ] Compiler upgrade có migration notes khi behavior thay đổi.

### 7.1. Reproducibility

- [ ] Cùng source, dependencies, compiler và options tạo artifact tương đương.
- [ ] Build không phụ thuộc current directory ngoài project root được chỉ định.
- [ ] File enumeration order không làm thay đổi output.
- [ ] Timestamp/random IDs không tạo diff không cần thiết.
- [ ] Locale và timezone inputs được cố định hoặc khai báo.
- [ ] Environment-dependent inputs được ghi lại.
- [ ] Có thể tái tạo artifact của release đã phát hành.

## 8. Runtime và execution model

Runtime cần thực thi semantics đúng và quản lý tài nguyên trong mọi tình huống.

- [ ] Execution lifecycle được định nghĩa.
- [ ] Runtime state transitions có mô hình rõ.
- [ ] Evaluation order được giữ đúng.
- [ ] Transaction boundary được xác định.
- [ ] Concurrency semantics được mô tả.
- [ ] Cancellation được hỗ trợ ở các điểm cần thiết.
- [ ] Deadline được truyền tới child operations.
- [ ] Errors được phân loại và propagate.
- [ ] Retry policy có maximum attempts và total budget.
- [ ] Idempotency được xác định cho side-effecting operations.
- [ ] Background jobs giữ actor/authorization context phù hợp.
- [ ] Resource cleanup xảy ra khi success, failure, timeout và cancellation.
- [ ] Runtime không chạy operation chưa được bind hoặc chưa được authorize.
- [ ] Runtime logs có execution ID và correlation context.
- [ ] Runtime có health/readiness signals.
- [ ] Execution history gắn với language/runtime/profile version.
- [ ] Replay semantics được xác định nếu hỗ trợ replay.

### 8.1. Runtime error handling

- [ ] Error code ổn định.
- [ ] Message không làm lộ secret hoặc stack trace nội bộ.
- [ ] Retryable và permanent errors phân biệt được.
- [ ] Partial result được đánh dấu rõ.
- [ ] Timeout khác cancellation nếu semantics cần phân biệt.
- [ ] Failure có source location hoặc operation ID khi có thể.
- [ ] Error có correlation ID để điều tra.

## 9. Resource limits và scalability

Một DSL an toàn cần giới hạn đầu vào và chi phí thực thi.

- [ ] Source size có hard limit.
- [ ] Token/AST node count có limit.
- [ ] Nesting depth có limit.
- [ ] Module/dependency graph size có limit.
- [ ] Compilation time và memory có budget.
- [ ] Runtime wall-clock và CPU có budget.
- [ ] Instruction/fuel count có limit nếu phù hợp.
- [ ] Recursion và loop iterations có giới hạn.
- [ ] Collection, payload và result size có giới hạn.
- [ ] Concurrency và fan-out có giới hạn.
- [ ] External calls có timeout, count và concurrency cap.
- [ ] Database query và transaction có giới hạn.
- [ ] Queue có bounded capacity.
- [ ] Backpressure được propagate.
- [ ] Admission control có policy.
- [ ] Tenant quota và fairness được xác định.
- [ ] Budget được truyền xuống child tasks.
- [ ] Cancellation giải phóng worker và connection.
- [ ] Limit errors cho biết dimension và scope.
- [ ] Capacity planning có headroom.

### 9.1. Performance evidence

- [ ] Có benchmark cho workload đại diện.
- [ ] Có benchmark cho large input.
- [ ] Có load test và stress test.
- [ ] Có soak test cho memory/queue/cache growth.
- [ ] p50, p95 và p99 được theo dõi khi phù hợp.
- [ ] Compile và runtime costs được đo riêng.
- [ ] Regression thresholds được định nghĩa.
- [ ] Performance claims có environment và test conditions.

## 10. Security và trust boundaries

Security cần được thiết kế từ parser tới runtime, connector và deployment.

- [ ] Threat model xác định assets, actors và trust boundaries.
- [ ] Authentication và authorization được phân biệt.
- [ ] Authorization được enforce ở mọi entry point.
- [ ] Default deny được áp dụng khi policy không cho phép.
- [ ] Missing/invalid context không tạo permit.
- [ ] Tenant isolation được enforce ở data layer.
- [ ] Field/resource-level access được kiểm soát nếu cần.
- [ ] DSL built-in operations có capability requirements.
- [ ] Plugin identity và permissions được kiểm tra.
- [ ] Sandbox giới hạn filesystem, network, process và native access.
- [ ] Untrusted input được validate và giới hạn.
- [ ] Path traversal và symlink boundaries được xử lý.
- [ ] Policy expression không cho arbitrary code execution.
- [ ] Secrets không nằm trong source, generated docs hoặc logs.
- [ ] Sensitive fields được redact.
- [ ] Dependency và plugin supply chain được quản lý.
- [ ] Audit events có integrity và retention policy.
- [ ] Delegation và impersonation giữ actor chain.
- [ ] Emergency access có expiry và audit.
- [ ] Security-sensitive defaults yêu cầu explicit review.

### 10.1. Security testing

- [ ] Có negative authorization tests.
- [ ] Có tenant boundary tests.
- [ ] Có direct-handler/bypass tests.
- [ ] Có malicious input tests.
- [ ] Có parser resource-exhaustion tests.
- [ ] Có plugin boundary tests.
- [ ] Có secret leakage checks.
- [ ] Có dependency vulnerability review.
- [ ] Có security regression tests cho incident đã biết.

## 11. Usability và developer experience

Một DSL tốt cần giúp người dùng viết, hiểu và sửa chương trình.

- [ ] Syntax phổ biến dễ đọc.
- [ ] Naming conventions nhất quán.
- [ ] Defaults có thể được khám phá.
- [ ] Effective configuration có thể xem.
- [ ] Ambiguity được báo rõ.
- [ ] Error message chỉ ra vị trí và cách sửa.
- [ ] Autocomplete phù hợp context.
- [ ] Hover hiển thị type và metadata.
- [ ] Go to Definition hoạt động với symbol được resolve.
- [ ] Find References và Rename giữ semantics.
- [ ] Formatter không đổi behavior.
- [ ] Linter phân biệt error, warning và hint.
- [ ] Refactoring có preview khi thay đổi nhiều generated symbols.
- [ ] Large project navigation có hiệu năng phù hợp.
- [ ] Keyboard accessibility được hỗ trợ.
- [ ] Editor không bị treo khi parse lỗi hoặc file lớn.
- [ ] Người dùng có thể tắt hoặc override convention phù hợp.

## 12. Documentation và learning materials

Tài liệu cần đồng bộ với language/compiler version và audience.

- [ ] Có getting-started tutorial.
- [ ] Có language overview.
- [ ] Có syntax/grammar reference.
- [ ] Có semantics và type-system explanation.
- [ ] Có examples end-to-end.
- [ ] Có error/diagnostic guide.
- [ ] Có API/operation reference nếu DSL cung cấp interface.
- [ ] Có security guidance.
- [ ] Có performance/resource-limit guidance.
- [ ] Có interoperability guide.
- [ ] Có migration guide.
- [ ] Có versioned documentation.
- [ ] Examples được xác định là executable hay illustrative.
- [ ] Executable examples được kiểm tra với compiler phù hợp.
- [ ] Code blocks copy được.
- [ ] Syntax diagrams có text alternative.
- [ ] Cross-reference và anchors ổn định.
- [ ] Search index keyword, symbol và error codes.
- [ ] Glossary thống nhất thuật ngữ.
- [ ] Không có secret hoặc dữ liệu production trong examples.
- [ ] Documentation có owner và release cadence.

## 13. Interoperability và integration

DSL cần trao đổi đúng dữ liệu và semantics với hệ thống khác.

- [ ] Source of truth được xác định.
- [ ] Canonical model boundaries rõ.
- [ ] Import/export formats được liệt kê.
- [ ] Type mapping được đặc tả.
- [ ] Nullability và presence semantics được giữ.
- [ ] Identity và reference mapping ổn định.
- [ ] Unsupported constructs có loss report.
- [ ] Round-trip fidelity được công bố.
- [ ] API contracts có version.
- [ ] Event schemas có compatibility policy.
- [ ] Protocol adapters có timeout/retry/cancellation.
- [ ] Authentication và authorization context được propagate đúng.
- [ ] Correlation ID và trace context được giữ.
- [ ] Adapter không để vendor-specific types lan vào domain model.
- [ ] Contract ownership và deprecation process rõ.
- [ ] Consumer/provider tests có trong pipeline.
- [ ] Compatibility matrix được kiểm tra.

## 14. Testing strategy

Một DSL cần nhiều loại test vì parser tests không thể chứng minh runtime hoặc integration đúng.

- [ ] Lexer tests.
- [ ] Parser tests.
- [ ] AST/model tests.
- [ ] Name resolution tests.
- [ ] Type-checking tests.
- [ ] Semantic evaluation tests.
- [ ] Runtime lifecycle tests.
- [ ] Error/diagnostic tests.
- [ ] Security/authorization tests.
- [ ] Resource-limit tests.
- [ ] Concurrency/cancellation tests.
- [ ] Adapter/contract tests.
- [ ] Code generation tests.
- [ ] Documentation example tests.
- [ ] Compatibility tests.
- [ ] Property-based tests.
- [ ] Fuzz tests cho parser/importers khi phù hợp.
- [ ] Regression corpus được duy trì.
- [ ] Golden outputs có version và update review.
- [ ] Tests chạy trong CI theo đúng release policy.

### 14.1. Test coverage theo construct

Với mỗi public construct, có thể theo dõi:
- Valid minimal example.
- Valid complex example.
- Invalid syntax example.
- Semantic failure example.
- Boundary case.
- Version-specific behavior.
- Runtime behavior nếu construct có execution semantics.

Không cần mọi internal parser rule có cùng số lượng tests. Ưu tiên public behavior và rủi ro thực tế.

## 15. Observability và operability

DSL runtime cần cung cấp thông tin đủ để vận hành và điều tra.

- [ ] Logs có stable execution/request IDs.
- [ ] Metrics đo compile duration và runtime duration.
- [ ] Error rate được phân loại.
- [ ] Resource usage được đo.
- [ ] Queue depth và queue age được theo dõi.
- [ ] Limit events có scope và reason code.
- [ ] Distributed trace được propagate.
- [ ] Logs/metrics không chứa secret.
- [ ] Metric labels có cardinality kiểm soát.
- [ ] Dashboards phản ánh service objectives.
- [ ] Alerts có owner và action.
- [ ] Runbooks mô tả lỗi thường gặp.
- [ ] Có quy trình incident response.
- [ ] Audit logs có retention và access control.
- [ ] Runtime version và policy version được gắn vào execution records.

## 16. Configuration, conventions và extensibility

Mặc định và extension points cần dễ hiểu và có kiểm soát.

- [ ] Convention được tài liệu hóa.
- [ ] Precedence giữa platform/project/module/declaration/default rõ.
- [ ] Effective values có thể inspect.
- [ ] Explicit overrides có validation.
- [ ] Ambiguous convention resolution tạo diagnostic.
- [ ] Generated names ổn định.
- [ ] Convention profiles có version.
- [ ] Plugin API có compatibility contract.
- [ ] Extension không tự động cấp quyền rộng.
- [ ] Extension discovery có trusted boundary.
- [ ] Plugin có timeout và resource limits.
- [ ] Plugin failure không làm sập runtime chung nếu có thể.
- [ ] Extension có lifecycle và deprecation policy.
- [ ] API surface công khai có owner.

## 17. Versioning, compatibility và migration

Ngôn ngữ, compiler, runtime và external contracts có thể phát triển độc lập.

- [ ] DSL language version được xác định.
- [ ] Compiler version được ghi.
- [ ] Runtime version được ghi.
- [ ] Convention profile version được ghi.
- [ ] Schema/API/event versions được quản lý.
- [ ] Breaking changes được phân loại.
- [ ] Deprecation có replacement và timeline.
- [ ] Migration guide có ví dụ trước/sau.
- [ ] Compatibility matrix được duy trì.
- [ ] Old source có behavior xác định khi compile bằng version mới.
- [ ] Generated artifacts có provenance.
- [ ] Rollback strategy được xác định.
- [ ] Migration có thể được thử nghiệm trước khi áp dụng.
- [ ] Changelog phản ánh syntax, semantics và runtime changes.

## 18. Release readiness

Trước khi phát hành một DSL/compiler/runtime version, cần xác định artifact và trách nhiệm.

- [ ] Release scope được chốt.
- [ ] Language/compiler/runtime versions tương thích.
- [ ] Build artifacts có checksum hoặc provenance.
- [ ] Dependencies được pin và kiểm tra.
- [ ] Required tests đã hoàn tất theo release policy.
- [ ] Security blockers đã được xử lý hoặc risk acceptance được ghi.
- [ ] Breaking changes có migration notes.
- [ ] Documentation khớp release.
- [ ] Generated code/schema đã được kiểm tra.
- [ ] Compatibility matrix được cập nhật.
- [ ] Rollback procedure đã được chuẩn bị.
- [ ] Release owner và approver được xác định.
- [ ] Known limitations được công bố.
- [ ] Support window được xác định.
- [ ] Release notes có link tới artifacts và migration guidance.

## 19. Production readiness

Một DSL có thể build thành công nhưng chưa sẵn sàng cho production.

- [ ] Capacity và quota được cấu hình.
- [ ] Admission control và backpressure được bật khi cần.
- [ ] Runtime isolation phù hợp trust model.
- [ ] Secrets và credentials được quản lý an toàn.
- [ ] Tenant isolation được xác nhận.
- [ ] Monitoring và alerts hoạt động.
- [ ] Runbooks và escalation path sẵn sàng.
- [ ] Backup/restore strategy rõ nếu có persistent state.
- [ ] Data retention và deletion policy rõ.
- [ ] Disaster recovery objectives được xác định.
- [ ] Dependency outage behavior được kiểm tra.
- [ ] Graceful shutdown và deployment strategy được xác định.
- [ ] Rollback đã được diễn tập khi phù hợp.
- [ ] On-call owner và service owner được xác định.
- [ ] Usage/cost reporting có thể quan sát.

## 20. Risk register và quality decisions

Checklist không nên che giấu những mục chưa hoàn tất. Các rủi ro cần được ghi nhận và theo dõi.

Một risk record có thể gồm:

~~~text
Risk ID: DSL-042
Area: Runtime resource limits
Description: A plugin operation may ignore cancellation.
Impact: Worker exhaustion during downstream outage.
Likelihood: Medium
Mitigation: Isolate plugin execution and enforce process deadline.
Owner: Runtime team
Due date: Release milestone
Status: Planned
Evidence: Link to design and cancellation tests
~~~

### 20.1. Risk assessment

Có thể đánh giá:
- Impact: mức độ ảnh hưởng tới dữ liệu, security, availability hoặc user.
- Likelihood: khả năng xảy ra.
- Detectability: khả năng phát hiện trước khi ảnh hưởng.
- Exposure: phạm vi người dùng hoặc tenant bị ảnh hưởng.
- Mitigation: biện pháp giảm rủi ro.

Không nên cộng điểm máy móc nếu không có risk model được thống nhất.

### 20.2. Accepted risk

Một risk chỉ được coi là accepted khi:
- Có mô tả cụ thể.
- Có impact và likelihood.
- Có owner.
- Có người có thẩm quyền chấp nhận.
- Có thời hạn hoặc trigger review.
- Có mitigation hoặc contingency khi cần.

### 20.3. Decision log

Các quyết định như grammar notation, type mapping, default security, execution model và compatibility policy nên có record để người review sau này hiểu rationale.

## 21. Mẫu checklist record

Có thể quản lý từng mục theo mẫu:

| Field | Nội dung |
|---|---|
| ID | Mã mục ổn định |
| Area | Nhóm chất lượng |
| Requirement | Câu hỏi hoặc tiêu chí |
| Applicability | Áp dụng/không áp dụng |
| Status | Pass/Fail/Blocked/Planned |
| Evidence | Link test, doc hoặc artifact |
| Owner | Người chịu trách nhiệm |
| Risk | Tác động nếu chưa đạt |
| Target release | Mốc dự kiến |
| Reviewed at | Thời điểm đánh giá |

Một record không cần chứa toàn bộ bằng chứng; nó nên trỏ đến artifact cụ thể để review có thể tái kiểm tra.

## 22. Cách diễn giải kết quả

Không nên dùng một tỷ lệ checkbox đơn giản làm kết luận duy nhất về chất lượng.

Một project có thể đạt 95% mục nhỏ nhưng vẫn có một lỗi critical trong authorization hoặc data integrity. Ngược lại, một DSL nội bộ nhỏ có thể không cần một số hạng mục enterprise như public schema registry.

Nên báo cáo theo:
- Critical blockers.
- High risks.
- Passed requirements.
- Planned improvements.
- Not-applicable items kèm lý do.
- Evidence coverage.
- Owners và target dates.

### 22.1. Release gate

Release gate nên xác định trước:
- Mục nào bắt buộc Pass.
- Mục nào có thể là Accepted risk.
- Ai có quyền chấp nhận risk.
- Evidence nào được chấp nhận.
- Điều kiện nào buộc dừng release.

### 22.2. Continuous quality

Chất lượng DSL thay đổi theo thời gian. Checklist nên được chạy lại khi:
- Thêm construct hoặc thay đổi grammar.
- Thay type system hoặc evaluation semantics.
- Thêm runtime operation/plugin.
- Đổi security policy.
- Đổi external contract.
- Nâng compiler/runtime.
- Thay đổi deployment topology.
- Có incident hoặc vulnerability mới.

## 23. Những sai lầm thường gặp khi dùng checklist

1. **Đánh dấu Pass không có evidence:** trạng thái không thể kiểm chứng.
2. **Dùng một checklist cho mọi DSL:** bỏ qua khác biệt về domain và risk.
3. **Chỉ kiểm tra parser:** bỏ sót semantics, runtime và security.
4. **Đếm checkbox thay cho đánh giá risk:** một blocker critical bị che bởi nhiều mục nhỏ.
5. **Để mục Not applicable không có lý do:** phạm vi kiểm tra trở nên mơ hồ.
6. **Không có owner:** phát hiện không chuyển thành hành động.
7. **Checklist quá dài nhưng không phân nhóm:** người review bỏ qua nội dung.
8. **Không cập nhật sau incident:** cùng lỗi lặp lại.
9. **Không phân biệt release gate với improvement:** release bị chặn bởi mục không critical hoặc rủi ro thật bị bỏ qua.
10. **Chỉ dùng checklist cuối dự án:** vấn đề kiến trúc đã trở nên tốn kém để sửa.
11. **Không quản lý version:** không biết checklist nào áp dụng cho release nào.
12. **Không review accepted risks:** rủi ro tạm thời trở thành vĩnh viễn.

## 24. Quy trình áp dụng quality checklist

Một quy trình thực tế:

1. **Xác định phạm vi đánh giá:** language design, compiler, runtime, tooling hay toàn platform.
2. **Chọn checklist phù hợp:** bỏ mục không liên quan nhưng ghi lý do.
3. **Chỉ định owner/reviewer:** mỗi mục có người chịu trách nhiệm.
4. **Thu thập evidence:** source, tests, reports, architecture records và operational data.
5. **Đánh giá trạng thái:** Pass, Fail, Blocked, Planned hoặc Not applicable.
6. **Phân loại risk:** impact, likelihood, exposure và detectability.
7. **Xác định release blockers:** dựa trên policy và risk model.
8. **Ghi action items:** owner, due date và mitigation.
9. **Review accepted risks:** có approver và thời hạn.
10. **Cập nhật decision log:** lưu rationale cho lựa chọn quan trọng.
11. **Theo dõi remediation:** cập nhật evidence khi fix hoàn tất.
12. **Đánh giá lại sau thay đổi:** grammar, runtime, dependency, security hoặc deployment.
13. **Tổng hợp kết quả:** blockers, risks, passes, planned work và evidence coverage.
14. **Lưu checklist theo release:** có thể truy nguyên trạng thái tại thời điểm phát hành.

## 25. Kết luận

Danh sách kiểm tra chất lượng giúp team đánh giá DSL trên toàn bộ vòng đời, từ mục tiêu sản phẩm và language design đến grammar, semantics, compiler, runtime, security, performance, tooling, documentation, interoperability và production operations. Checklist cần có tiêu chí rõ, trạng thái nhất quán, owner và bằng chứng có thể kiểm tra lại.

Không nên xem số lượng mục được đánh dấu là thước đo duy nhất. Các rủi ro về correctness, security, data integrity và availability cần được ưu tiên theo impact; những cải tiến trải nghiệm có thể được lên kế hoạch theo release. Khi checklist được duy trì cùng risk register, decision log, test evidence và release policy, nó trở thành công cụ quản trị chất lượng liên tục thay vì một thủ tục đánh dấu ở cuối dự án.

