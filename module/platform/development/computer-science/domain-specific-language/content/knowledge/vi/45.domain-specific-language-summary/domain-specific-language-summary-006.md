# Bước phát triển tiếp theo

Một DSL (Domain-Specific Language) không kết thúc ở thời điểm grammar, parser hoặc compiler đầu tiên hoạt động. Một ngôn ngữ chỉ thực sự có giá trị khi giải quyết được vấn đề trong domain, được người dùng hiểu và chấp nhận, có công cụ hỗ trợ, có quy trình phát hành và có khả năng phát triển cùng nhu cầu thực tế. Sau khi nắm được các khái niệm về thiết kế, triển khai, bảo mật, kiểm thử và quản trị DSL, bước tiếp theo là biến kiến thức đó thành một kế hoạch phát triển có thể thực hiện và đo lường.
 
**Bước phát triển tiếp theo (next steps)** là lộ trình những việc cần làm sau giai đoạn thiết kế hoặc xây dựng ban đầu để DSL trưởng thành hơn. Lộ trình có thể bao gồm xác nhận nhu cầu domain, hoàn thiện language specification, cải thiện compiler/runtime, mở rộng tooling, tăng bảo mật, xây dựng tài liệu, hỗ trợ người dùng và quản lý vòng đời.
 
Ví dụ, một nhóm đã có DSL mô tả service với parser và code generator ban đầu có thể tiếp tục theo các giai đoạn:
 
~~~mermaid
flowchart TD
    A[Validate domain problem] --> B[Refine language design]
    B --> C[Strengthen compiler and runtime]
    C --> D[Build developer tooling]
    D --> E[Testing and security]
    E --> F[Documentation and adoption]
    F --> G[Governance and releases]
    G --> H[Measure and evolve]
    H --> B
~~~
 
Đây không phải quy trình tuyến tính cứng nhắc. Phản hồi từ người dùng có thể khiến nhóm quay lại sửa grammar; security review có thể yêu cầu thay đổi runtime; dữ liệu sử dụng có thể cho thấy một tính năng không cần thiết. Phát triển DSL là quá trình lặp, có kiểm soát và dựa trên bằng chứng.
 
Trong chương **Tổng kết DSL**, nội dung này kết nối các kiến thức đã học thành kế hoạch hành động. Mục tiêu là biết nên bắt đầu ở đâu, ưu tiên việc gì, xác định kết quả ra sao và duy trì ngôn ngữ thế nào khi nó được sử dụng rộng hơn.
 
## 1. Đánh giá lại vấn đề domain
     
Bước đầu tiên sau prototype là xác nhận DSL thực sự giải quyết vấn đề nào và có đáng để tiếp tục đầu tư hay không.
 
### 1.1. Xác định người dùng và công việc
 
Viết rõ:
 
- Ai sẽ viết source DSL?
- Ai đọc, review hoặc vận hành chương trình DSL?
- Họ đang dùng công cụ hoặc ngôn ngữ nào?
- Công việc nào lặp lại, dễ sai hoặc khó tự động hóa?
- Kết quả nào cần được tạo ra?
- Những quyết định nào phải được thể hiện rõ trong source?
 
Một DSL tốt phản ánh cách người dùng nghĩ về domain. Nếu người dùng phải hiểu nhiều chi tiết compiler hoặc target platform mới viết được chương trình, abstraction có thể chưa đúng.
 
### 1.2. Xác định pain point cụ thể
 
Tránh mục tiêu chung như "làm cấu hình dễ hơn". Hãy diễn đạt vấn đề có thể quan sát:
 
- Một cấu hình service bị lặp ở nhiều repository.
- Các nhóm dùng tên field khác nhau cho cùng một khái niệm.
- Sai sót cấu hình chỉ được phát hiện sau deployment.
- Quy trình review không thể kiểm tra policy một cách tự động.
- Một workflow đòi hỏi nhiều script khó tái sử dụng.
 
Pain point cụ thể giúp đánh giá DSL bằng kết quả thực tế.
 
### 1.3. So sánh với giải pháp hiện có
 
Trước khi mở rộng DSL, xem xét:
 
- YAML/JSON/TOML hoặc schema-based configuration.
- API thư viện thông thường.
- Framework hiện có.
- Template hoặc code generator.
- Build system hoặc workflow engine.
- Một DSL đã có trong domain.
 
Không phải mọi vấn đề đều cần một ngôn ngữ mới. DSL có chi phí thiết kế, tooling, onboarding và maintenance. Chỉ nên tiếp tục khi lợi ích domain-specific đủ rõ.
 
### 1.4. Đặt success criteria
 
Ví dụ tiêu chí:
 
- Giảm số bước cấu hình lặp.
- Phát hiện lỗi trước khi chạy.
- Giảm thời gian onboarding.
- Tăng tỷ lệ project dùng chung module.
- Giảm số incident do cấu hình sai.
- Tăng khả năng tái lập build hoặc deployment.
 
Chọn số liệu có thể đo được và baseline trước khi triển khai rộng.
 
## 2. Xác định phạm vi và roadmap
     
Không nên cố hoàn thiện mọi tính năng trong một lần. Chia mục tiêu thành các giai đoạn có deliverable rõ.
 
### 2.1. Minimum viable language
 
Một MVP của DSL có thể chỉ cần:
 
- Một số construct cốt lõi.
- Grammar và parser.
- AST hoặc semantic model.
- Validation cơ bản.
- Một backend hoặc runtime.
- CLI tối thiểu.
- Ví dụ và tài liệu bắt đầu.
- Unit và integration tests.
 
MVP cần giải quyết một use case thật từ đầu đến cuối, không chỉ parse được vài dòng source.
 
### 2.2. Phân biệt prototype và production-ready
 
Prototype có thể chấp nhận API chưa ổn định, diagnostics đơn giản hoặc thao tác thủ công. Production DSL cần thêm:
 
- Versioning và compatibility.
- Error handling rõ.
- Security và resource limits.
- Reproducible build.
- CI và release process.
- Documentation và support.
- Observability và migration.
 
Không nên coi prototype chạy được là bằng chứng sản phẩm đã sẵn sàng.
 
### 2.3. Roadmap theo outcome
 
Mỗi milestone nên mô tả kết quả người dùng nhận được thay vì chỉ liệt kê class hoặc module sẽ viết.
 
Ví dụ:
 
| Giai đoạn | Outcome | Deliverable |
|---|---|---|
| Foundation | Source có grammar rõ | Language spec và parser |
| Validation | Lỗi được phát hiện sớm | Type checker và diagnostics |
| Execution | Chương trình tạo kết quả | Runtime hoặc backend |
| Developer experience | Dễ viết và sửa source | Formatter, LSP, examples |
| Adoption | Team có thể dùng thật | Docs, migration và support |
| Scale | Vận hành ổn định | Security, metrics và governance |
 
### 2.4. Giữ backlog có ưu tiên
 
Mỗi item nên có:
 
- Problem statement.
- User hoặc stakeholder bị ảnh hưởng.
- Expected outcome.
- Dependency.
- Risk.
- Acceptance criteria.
- Owner.
 
Không ưu tiên chỉ vì tính năng nghe hấp dẫn hoặc dễ demo.
 
## 3. Hoàn thiện language specification
     
Khi DSL bắt đầu được nhiều người sử dụng, grammar và semantics cần được mô tả chính thức.
 
### 3.1. Chốt grammar
 
Ghi lại:
 
- Token và literal.
- Declaration và statement.
- Expression và operator precedence.
- Block, list, map và separator.
- Comment và whitespace.
- Import và module syntax.
- Version-specific syntax.
 
Grammar nên có ví dụ hợp lệ và không hợp lệ.
 
### 3.2. Chốt semantics
 
Grammar chỉ cho biết source có cấu trúc nào. Specification cần nói cấu trúc đó có nghĩa gì:
 
- Scope và name resolution.
- Type system.
- Default value.
- Evaluation order.
- Side effect.
- Error behavior.
- Reference và dependency.
- Serialization và output.
 
### 3.3. Viết language reference
 
Reference nên mô tả construct theo một format nhất quán: syntax, meaning, constraints, examples, errors và version availability.
 
### 3.4. Quản lý ambiguity
 
Nếu source có thể được hiểu theo nhiều cách, cần quy tắc disambiguation rõ. Test phải bảo vệ precedence, associativity và keyword handling.
 
### 3.5. Quyết định tính năng có nên vào core
 
Trước khi thêm syntax mới, hỏi:
 
- Có phải use case phổ biến của domain không?
- Có thể biểu diễn bằng existing construct hoặc library không?
- Có làm grammar phức tạp hơn không?
- Có tạo ambiguity hoặc breaking change không?
- Có thể hỗ trợ bằng extension không?
 
Core language nên giữ nhỏ và nhất quán.
 
## 4. Củng cố compiler và semantic model
     
Compiler là nơi biến source thành model đáng tin cậy để runtime hoặc backend sử dụng.
 
### 4.1. Tách phase rõ ràng
 
Một pipeline có thể gồm:
 
~~~mermaid
flowchart LR
    A[Source] --> B[Lexing]
    B --> C[Parsing]
    C --> D[AST]
    D --> E[Name resolution]
    E --> F[Type checking]
    F --> G[Typed IR]
    G --> H[Optimization]
    H --> I[Backend]
    I --> J[Artifact]
~~~
 
Mỗi phase nên có input/output contract và diagnostics riêng. Điều này giúp test, cache và debug dễ hơn.
 
### 4.2. Xây AST/IR ổn định
 
Xác định node nào là public API, node nào là internal. Nếu plugin hoặc tool ngoài tiêu thụ IR, cần version và compatibility policy.
 
### 4.3. Cải thiện diagnostics
 
Diagnostic nên có:
 
- Code ổn định.
- Severity.
- Message rõ.
- Source range.
- Related location.
- Help hoặc quick fix nếu phù hợp.
- Link tới tài liệu.
 
Lỗi cần chỉ ra nguyên nhân và hướng xử lý, không chỉ báo parser thất bại.
 
### 4.4. Incremental processing
 
Với editor hoặc project lớn, incremental parsing/compilation có thể giảm latency. Cần cache invalidation đúng và kết quả tương đương full compile.
 
### 4.5. Determinism
 
Cùng source, dependency và toolchain version nên tạo kết quả ổn định nếu sản phẩm cam kết reproducibility. Loại bỏ ordering không xác định và ghi metadata cho input bên ngoài.
 
### 4.6. Performance profiling
 
Đo thời gian từng phase, peak memory, allocation, cache hit và graph size. Tối ưu theo workload thực tế thay vì đoán bottleneck.
 
## 5. Phát triển runtime và backend
     
Sau compiler, cần bảo đảm chương trình DSL tạo được hành vi có ý nghĩa.
 
### 5.1. Xác định execution model
 
DSL có thể:
 
- Sinh source code.
- Sinh configuration hoặc manifest.
- Chạy trên interpreter.
- Compile thành bytecode hoặc native artifact.
- Gọi host application qua function API.
- Điều khiển workflow hoặc deployment.
 
Execution model quyết định security, observability và resource management.
 
### 5.2. Xây backend theo abstraction
 
Backend nên nhận typed IR hoặc semantic model thay vì tự parse source lần nữa. Target-specific behavior được đặt trong module riêng.
 
### 5.3. Capability negotiation
 
Backend cần công bố tính năng được hỗ trợ. Compiler nên phát diagnostic khi source dùng capability không có ở target.
 
### 5.4. Runtime contract
 
Định nghĩa:
 
- Input và output.
- Error và exception mapping.
- Side effect.
- Cancellation.
- Timeout.
- Resource budget.
- Thread safety.
 
### 5.5. Host integration
 
Nếu DSL gọi host function hoặc external service, chỉ expose capability cần thiết và giữ authorization ở host boundary.
 
### 5.6. Version compatibility
 
Artifact cần ghi compiler, runtime, language và backend version. Runtime nên biết artifact nào được hỗ trợ.
 
## 6. Cải thiện developer experience
     
Một DSL có grammar tốt nhưng không có tooling phù hợp sẽ khó được chấp nhận.
 
### 6.1. CLI
 
CLI nên hỗ trợ các thao tác chính:
 
~~~text
dsl init
dsl check
dsl format
dsl compile
dsl test
dsl run
dsl docs
dsl migrate
~~~
 
Mỗi command cần help, exit code, output format và behavior rõ.
 
### 6.2. Formatter
 
Formatter tạo style nhất quán và giảm tranh luận về whitespace. Cần có configuration ổn định và idempotency: format lần hai không tạo diff mới.
 
### 6.3. Language server
 
LSP có thể cung cấp completion, hover, go to definition, references, rename, diagnostics và code actions.
 
### 6.4. IDE support
 
Cung cấp syntax highlighting, snippets, project navigation và debugging nếu execution model cho phép.
 
### 6.5. Debugging
 
Người dùng cần xem source location, variable value, execution step và dependency khi DSL được thực thi.
 
### 6.6. Generated code visibility
 
Nếu DSL sinh code hoặc manifest, cung cấp cách xem output và truy ngược về source declaration.
 
### 6.7. Error recovery
 
Editor cần tiếp tục cung cấp hỗ trợ khi source đang được gõ và chưa hợp lệ hoàn toàn.
 
## 7. Tăng cường kiểm thử và chất lượng
     
Một DSL cần test nhiều hơn việc parser có chấp nhận source hay không.
 
### 7.1. Test layers
 
- Lexer và parser unit tests.
- AST và semantic tests.
- Type checking tests.
- Runtime/backend tests.
- Integration tests.
- End-to-end project tests.
- Contract và compatibility tests.
- Performance tests.
- Security tests.
 
### 7.2. Regression corpus
 
Giữ các source từng gây bug. Mỗi parser hoặc compiler bug được sửa nên có test tái hiện.
 
### 7.3. Property-based testing
 
Sinh source từ grammar hoặc AST generator để kiểm tra round-trip, determinism và các invariant.
 
### 7.4. Fuzzing
 
Fuzz parser, deserializer, plugin boundary và runtime với timeout/sandbox. Lưu minimized input làm regression.
 
### 7.5. Compatibility tests
 
Chạy project và artifact từ phiên bản cũ trên toolchain mới theo policy đã công bố.
 
### 7.6. Test examples
 
Mọi sample trong tài liệu nên được compile hoặc execute trong CI khi có thể.
 
### 7.7. Test quality signals
 
Theo dõi flaky test, coverage của grammar construct và bug recurrence. Coverage cao không tự chứng minh semantics đúng.
 
## 8. Bảo mật và độ tin cậy
     
DSL có thể nhận source không tin cậy hoặc tạo hành động có side effect. Security cần được thiết kế từ đầu.
 
### 8.1. Threat model
 
Xác định source đến từ đâu, ai có thể gửi, tài nguyên nào bị ảnh hưởng và capability nào được expose.
 
### 8.2. Resource limits
 
Giới hạn input size, token, AST nodes, nesting, evaluation steps, memory, CPU, wall-clock time, external calls và output size.
 
### 8.3. Sandboxing
 
Plugin hoặc code không tin cậy nên chạy trong process/container/Wasm sandbox phù hợp với filesystem, network và capability giới hạn.
 
### 8.4. Least privilege
 
Runtime identity và deployment identity chỉ có quyền cần thiết. Không để DSL tự nâng quyền bằng một field trong source.
 
### 8.5. Secret management
 
Không commit secret vào project. Dùng secret reference, workload identity và redaction.
 
### 8.6. Supply chain
 
Pin dependency, kiểm tra provenance, signature, license và security advisory. Ghi dependency graph vào build metadata.
 
### 8.7. Audit và incident response
 
Ghi nhận ai chạy hoặc deploy project nào, bằng artifact nào và policy nào. Có quy trình xử lý lỗ hổng và thu hồi plugin bị xâm phạm.
 
## 9. Quản lý extension và ecosystem
     
Khi DSL phát triển, nhu cầu domain-specific có thể vượt quá core language.
 
### 9.1. Extension points
 
Thiết kế extension cho validator, function, type, backend, formatter hoặc plugin. Không cho plugin thay đổi tùy ý semantics core.
 
### 9.2. Stable API
 
Expose abstraction nhỏ, có version. Không bắt plugin phụ thuộc vào private compiler implementation.
 
### 9.3. Registry
 
Registry có thể quản lý extension ID, publisher, version, checksum, capability, dependency và deprecation.
 
### 9.4. Namespace và conflict resolution
 
Ngăn trùng tên và load order không xác định. Override cần được khai báo rõ.
 
### 9.5. Compatibility matrix
 
Công bố compiler version, extension API version và plugin version được hỗ trợ.
 
### 9.6. Governance
 
Xác định review, signing, admission, support status và emergency revocation.
 
### 9.7. Community contribution
 
Nếu dự án mở cho cộng đồng, cần contribution guide, issue template, code of conduct và quy trình review.
 
## 10. Tài liệu, onboarding và adoption
     
Người dùng chỉ có thể áp dụng DSL nếu biết cách bắt đầu và hiểu behavior.
 
### 10.1. Documentation set
 
Một bộ tài liệu có thể gồm:
 
- Getting started.
- Concepts.
- Tutorials.
- Language reference.
- API reference.
- Examples.
- Troubleshooting.
- Migration guides.
- Security guidance.
 
### 10.2. Glossary
 
Duy trì thuật ngữ chuẩn cho language, compiler, domain và lifecycle. Liên kết glossary từ API docs và diagnostics.
 
### 10.3. Example projects
 
Cung cấp project nhỏ, project thực tế và use case nâng cao. Examples cần được test với version cụ thể.
 
### 10.4. Migration guide
 
Khi grammar, schema hoặc API thay đổi, cung cấp before/after, automated migration nếu có và thời gian deprecation.
 
### 10.5. Onboarding path
 
Một người mới nên có thể:
 
1. Cài tool.
2. Tạo project.
3. Viết source đơn giản.
4. Chạy check.
5. Xem diagnostic.
6. Compile hoặc run.
7. Thêm module/dependency.
8. Chạy test.
 
### 10.6. Adoption feedback
 
Thu thập câu hỏi, lỗi onboarding, support issue và những workaround người dùng thường viết. Workaround lặp lại có thể cho thấy DSL thiếu abstraction.
 
## 11. Governance và lifecycle
     
Một DSL trưởng thành cần quy trình quyết định và phát hành rõ.
 
### 11.1. Ownership
 
Chỉ định owner cho grammar, compiler, runtime, backend, plugin API, docs và release.
 
### 11.2. RFC cho language change
 
Thay đổi semantics lớn nên có proposal gồm problem, alternatives, syntax, examples, compatibility và migration.
 
### 11.3. Versioning
 
Phân biệt language version, compiler version, runtime version, plugin API version và package version.
 
### 11.4. Deprecation policy
 
Thông báo API cũ, replacement, version bắt đầu deprecated và thời gian hỗ trợ.
 
### 11.5. Release management
 
Mỗi release nên có tag, artifact digest, changelog, compatibility matrix, SBOM/provenance khi phù hợp và support status.
 
### 11.6. Long-term support
 
Nếu DSL được dùng trong hệ thống quan trọng, xác định release LTS và quy trình backport security fix.
 
### 11.7. Archive
 
Khi module hoặc backend ngừng phát triển, thông báo trạng thái, migration path và lưu artifact/documentation cần thiết.
 
## 12. Đo lường mức độ trưởng thành của DSL
     
Không nên đánh giá thành công chỉ bằng số dòng code hoặc số tính năng.
 
Các chỉ số có thể theo dõi:
 
| Nhóm | Chỉ số |
|---|---|
| Usability | Thời gian hoàn thành task, lỗi onboarding, feedback |
| Language quality | Parser/semantic regression, diagnostic usefulness |
| Tooling | CLI/LSP latency, formatter adoption |
| Reliability | Crash, timeout, failed build, runtime error |
| Security | Vulnerability, policy violation, plugin incident |
| Performance | Compile time, memory, cache hit |
| Adoption | Project/team active, repeated usage |
| Maintainability | Change lead time, module coupling, flaky tests |
| Compatibility | Migration success, deprecated API usage |
 
### 12.1. Đo baseline
 
Trước khi phát hành tính năng mới, ghi nhận trạng thái hiện tại. Nếu không có baseline, khó biết thay đổi có tạo giá trị hay không.
 
### 12.2. Không tối ưu một metric riêng lẻ
 
Giảm compile time bằng cách bỏ validation có thể làm chất lượng giảm. Tăng số tính năng có thể làm onboarding khó hơn. Cần xem xét nhiều chỉ số cùng lúc.
 
### 12.3. Qualitative feedback
 
Phỏng vấn người dùng, quan sát họ viết DSL và đọc support request để hiểu nguyên nhân đằng sau metric.
 
### 12.4. Review roadmap định kỳ
 
Dựa vào usage, issue, security và compatibility để điều chỉnh ưu tiên.
 
## 13. Các hướng phát triển kỹ thuật có thể cân nhắc
     
Khi nền tảng cơ bản ổn định, một số hướng có thể đem lại giá trị. Không phải DSL nào cũng cần tất cả.
 
### 13.1. Declarative model và policy as code
 
Nếu domain cần mô tả desired state hoặc quy tắc, DSL có thể phát triển abstraction declarative và policy evaluation.
 
### 13.2. Incremental compiler
 
Giảm thời gian phản hồi trong editor và project lớn bằng incremental parsing, semantic cache và dependency-aware compilation.
 
### 13.3. Multiple backends
 
Hỗ trợ nhiều target thông qua IR ổn định và capability negotiation. Tránh để mỗi backend tự diễn giải source theo cách khác.
 
### 13.4. WebAssembly hoặc portable runtime
 
Nếu cần chạy DSL trong nhiều môi trường, có thể cân nhắc runtime portable như WebAssembly, với sandbox và resource metering phù hợp.
 
### 13.5. AI-assisted authoring
 
AI có thể gợi ý source, giải thích diagnostic hoặc tạo migration draft. Cần validation bằng parser/compiler thật, review của người dùng và giới hạn capability; không coi output sinh tự động là đáng tin cậy.
 
### 13.6. Schema-aware editor
 
Schema có thể hỗ trợ completion, validation, hover và documentation trong IDE.
 
### 13.7. Reproducible build và provenance
 
Ghi lại source revision, toolchain, dependency, extension và configuration để có thể tái tạo artifact.
 
### 13.8. Observability tích hợp
 
Runtime có thể cung cấp trace, metrics và structured logs theo domain concept thay vì chỉ log implementation detail.
 
## 14. Kế hoạch 30-60-90 ngày minh họa
     
Một roadmap ngắn giúp chuyển định hướng thành công việc cụ thể. Thời gian thực tế tùy quy mô nhóm.
 
| Giai đoạn | Trọng tâm | Kết quả mong đợi |
|---|---|---|
| 0-30 ngày | Xác nhận domain và baseline | Use case, user journey, language spec draft |
| 31-60 ngày | Hoàn thiện core workflow | Parser, semantic validation, CLI, test corpus |
| 61-90 ngày | Sẵn sàng cho nhóm pilot | Docs, CI, security limits, migration plan, feedback |
 
### 14.1. 0-30 ngày: xác nhận và thu hẹp
 
- Phỏng vấn người dùng.
- Chọn một use case có giá trị.
- So sánh với giải pháp hiện có.
- Viết grammar và semantics tối thiểu.
- Tạo prototype end-to-end.
- Xác định baseline và risk.
 
### 14.2. 31-60 ngày: xây nền tảng
 
- Hoàn thiện parser và semantic model.
- Xây validation và diagnostics.
- Tạo một backend/runtime hoạt động.
- Viết regression và integration tests.
- Pin dependency và build toolchain.
- Tạo CLI và project template.
 
### 14.3. 61-90 ngày: pilot có kiểm soát
 
- Tạo tài liệu và examples.
- Tích hợp CI.
- Đặt resource limit và permission policy.
- Chạy pilot với một nhóm người dùng.
- Thu thập metrics và feedback.
- Lập backlog dựa trên kết quả.
 
## 15. Lộ trình học tập tiếp theo cho người phát triển DSL
     
Nếu mục tiêu là tiếp tục học và tự xây dựng DSL, có thể đi theo các chủ đề sau.
 
### 15.1. Củng cố nền tảng ngôn ngữ
 
Học thêm:
 
- Formal grammar và EBNF.
- Lexing và parsing.
- AST và tree traversal.
- Type systems.
- Scope và name resolution.
- Evaluation semantics.
 
Thực hành bằng cách xây parser nhỏ cho arithmetic expression hoặc configuration language.
 
### 15.2. Học compiler architecture
 
Tìm hiểu compiler phases, IR, optimization, code generation và backend design. Thử sinh output cho một target đơn giản.
 
### 15.3. Học testing
 
Xây lexer/parser tests, property-based tests, fuzzing và golden tests. Tạo regression corpus từ lỗi thực tế.
 
### 15.4. Học runtime và execution
 
Tìm hiểu interpreter, bytecode, host function, capability, cancellation và resource budget.
 
### 15.5. Học developer tooling
 
Thử viết formatter, syntax highlighter hoặc language server. Một DSL có trải nghiệm editor tốt sẽ dễ được sử dụng hơn.
 
### 15.6. Học security
 
Tìm hiểu injection, sandboxing, least privilege, supply chain, resource exhaustion và secure plugin architecture.
 
### 15.7. Học governance
 
Tìm hiểu API versioning, compatibility, deprecation, RFC, release management và documentation as code.
 
### 15.8. Xây project portfolio
 
Một project học tập có thể tiến triển qua:
 
1. DSL tính toán đơn giản.
2. DSL cấu hình service.
3. Parser và AST.
4. Type checker và diagnostics.
5. Interpreter hoặc code generator.
6. CLI và formatter.
7. Test suite và fuzz harness.
8. Documentation và examples.
9. Plugin hoặc backend.
10. Release và migration.
 
## 16. Ví dụ tổng hợp: chuyển prototype thành DSL có thể dùng
     
Giả sử prototype hiện tại nhận:
 
~~~text
service "catalog" {
    replicas = 2
}
~~~
 
và sinh một manifest đơn giản.
 
### 16.1. Đánh giá prototype
 
Nhóm xác định:
 
- Người dùng là developer vận hành service.
- Vấn đề là cấu hình lặp và thiếu validation.
- Source cần hỗ trợ service, network, resource và environment.
- Target ban đầu là một nền tảng container.
 
### 16.2. Hoàn thiện semantics
 
Định nghĩa:
 
- replicas là integer dương.
- service name là unique trong project.
- network reference phải tồn tại.
- environment override có precedence xác định.
 
### 16.3. Hoàn thiện toolchain
 
Xây:
 
- Parser và typed AST.
- Semantic validation.
- CLI check/format/compile.
- Backend sinh manifest.
- Diagnostics có source range.
 
### 16.4. Thêm bảo vệ
 
- Giới hạn source bytes và nesting depth.
- Giới hạn output file count.
- Không cho DSL chứa secret literal.
- Chạy plugin trong sandbox.
- Giới hạn network access.
 
### 16.5. Kiểm thử
 
- Parser positive/negative tests.
- Semantic tests.
- Golden output.
- Integration test với target.
- Fuzzing source.
- Compatibility fixture từ release trước.
 
### 16.6. Pilot
 
Một nhóm dùng DSL cho một service không quá critical. Nhóm thu thập:
 
- Thời gian viết cấu hình.
- Số lỗi bị phát hiện trước deployment.
- Diagnostic có hữu ích không.
- Số lần phải dùng escape hatch.
- Khó khăn onboarding.
 
### 16.7. Quyết định tiếp theo
 
Nếu pilot cho thấy người dùng thường xuyên cần cùng một construct, cân nhắc thêm abstraction vào core. Nếu chỉ một platform cần, giữ nó ở backend extension. Nếu người dùng khó hiểu, cải thiện docs hoặc semantics trước khi thêm feature.
 
## 17. Những sai lầm khi lập kế hoạch phát triển tiếp theo
     
| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm feature trước khi xác nhận nhu cầu | Language phình to | Bắt đầu từ use case và outcome |
| Coi prototype là production-ready | Thiếu security, compatibility và operations | Có readiness criteria |
| Chỉ tập trung grammar | Người dùng thiếu compiler/tooling | Phát triển end-to-end workflow |
| Thêm syntax cho mọi nhu cầu | Parser và semantics phức tạp | Ưu tiên library/extension khi phù hợp |
| Không có language version | Source cũ đổi semantics âm thầm | Version và migration policy |
| Không có diagnostics tốt | Người dùng khó sửa source | Error code, source range và help |
| Không có regression tests | Bug cũ quay lại | Giữ corpus và test mỗi thay đổi |
| Không đo adoption | Không biết DSL tạo giá trị gì | Metrics và user feedback |
| Không quản lý plugin | Conflict và security risk | Registry, capability và version |
| Không viết migration guide | Nâng cấp khó | Before/after và automated migration |
| Không có owner | Backlog và API bị bỏ trống | Ownership theo domain/module |
| Chạy theo công nghệ mới | Tốn công nhưng ít giá trị | Đánh giá theo pain point |
| Không có deprecation policy | Khó tiến hóa API | Công bố support window |
| Không review roadmap | Ưu tiên lỗi thời | Điều chỉnh theo evidence |
 
## 18. Bộ câu hỏi để chọn bước tiếp theo
     
Trước mỗi milestone, hãy trả lời:
 
- Vấn đề người dùng nào đang được giải quyết?
- Có bằng chứng rằng vấn đề xảy ra thường xuyên không?
- Giải pháp hiện có có đủ không?
- Thay đổi nằm ở language core, library, tooling hay extension?
- Có làm source cũ thay đổi semantics không?
- Có cần version hoặc migration không?
- Compiler/runtime cần invariant mới nào?
- Có ảnh hưởng security hoặc resource budget không?
- Test nào chứng minh behavior đúng?
- Documentation và examples nào cần cập nhật?
- Ai sở hữu thay đổi và support sau release?
- Đo outcome bằng metric nào?
 
Nếu chưa trả lời được, nên thu thập thêm thông tin hoặc làm prototype nhỏ trước khi mở rộng core.
 
## 19. Tiêu chí của một DSL đang phát triển bền vững
     
Một DSL phát triển bền vững có mục tiêu domain rõ, specification đủ chính xác, compiler/runtime đáng tin cậy, tooling hữu ích, test và security được tích hợp, tài liệu dễ học, versioning có kiểm soát và feedback loop hoạt động.
 
Các dấu hiệu:
 
- Người dùng hoàn thành công việc domain với ít chi tiết kỹ thuật hơn.
- Lỗi được phát hiện sớm và diagnostics có thể hành động.
- Cùng source và dependency tạo kết quả có thể tái lập.
- Thay đổi language/API có compatibility analysis.
- Extension được quản lý bằng contract và capability.
- Performance và resource use được đo.
- Người dùng mới có thể tự học qua docs và examples.
- Team biết ai sở hữu từng thành phần.
- Release và migration có quy trình rõ.
- Roadmap dựa trên nhu cầu và dữ liệu thực tế.
 
## 20. Kết nối kiến thức DSL thành hành động
     
Các chủ đề đã học tạo thành một hệ thống liên kết:
 
~~~mermaid
flowchart TD
    A[Domain problem] --> B[Language design]
    B --> C[Grammar and parser]
    C --> D[AST and semantics]
    D --> E[Compiler/runtime]
    E --> F[Tooling and APIs]
    F --> G[Testing and security]
    G --> H[Documentation and adoption]
    H --> I[Governance and lifecycle]
    I --> J[Feedback and next iteration]
    J --> A
~~~
 
- Domain analysis giúp xác định ngôn ngữ cần diễn đạt gì.
- Grammar và parser xác định source hợp lệ.
- AST và semantic model làm rõ ý nghĩa.
- Compiler/runtime biến source thành kết quả.
- Tooling giúp viết, kiểm tra và vận hành.
- Testing/security bảo vệ correctness và availability.
- Documentation/adoption giúp người dùng áp dụng.
- Governance/lifecycle giữ compatibility và khả năng bảo trì.
- Feedback cung cấp dữ liệu cho vòng phát triển tiếp theo.
 
Không nên xem các phần này là những dự án độc lập. Một thay đổi grammar có thể cần cập nhật parser tests, IDE, docs và migration. Một extension mới có thể cần capability policy, registry và compatibility matrix. Một API mới có thể cần examples, error contract và release note.
 
## 21. Bước tiếp theo ngay sau khi hoàn thành một DSL prototype
     
Một kế hoạch ngắn, có thể bắt đầu ngay:
 
1. Viết một trang mô tả domain problem, người dùng và kết quả mong đợi.
2. Chọn một use case quan trọng để hoàn thiện end-to-end.
3. Ghi grammar và semantics thành language specification.
4. Tạo regression corpus cho source hợp lệ và không hợp lệ.
5. Hoàn thiện diagnostics và một workflow CLI chính.
6. Đặt resource limits, capability và security boundary.
7. Tạo examples, glossary và getting-started guide.
8. Chạy pilot với người dùng thật.
9. Đo thời gian, lỗi, adoption và feedback.
10. Ưu tiên milestone tiếp theo dựa trên kết quả.
 
## 22. Tiêu chí của một roadmap DSL tốt
     
Một roadmap tốt nối nhu cầu người dùng với thay đổi kỹ thuật và kết quả có thể đo. Nó phân biệt prototype với production, giữ core language ổn định, đầu tư vào compiler/tooling/security/docs và có quy trình versioning, ownership cùng migration.
 
Các câu hỏi quan trọng:
 
- Use case và audience đã được xác nhận chưa?
- DSL có thực sự tốt hơn giải pháp hiện có không?
- MVP giải quyết được một workflow hoàn chỉnh chưa?
- Grammar và semantics có specification không?
- Compiler/runtime có diagnostics và behavior ổn định không?
- Tooling có hỗ trợ người viết source không?
- Test, fuzzing và compatibility checks có bao phủ không?
- Security, resource limits và capability có được enforce không?
- Extension ecosystem có contract và governance không?
- Documentation, glossary và examples có được duy trì không?
- Release, deprecation và migration có kế hoạch không?
- Success criteria có baseline và metric không?
- Feedback từ pilot có thay đổi roadmap không?
 
Bước phát triển tiếp theo của một DSL không nhất thiết là thêm nhiều cú pháp. Đó là xác định phần nào đang giới hạn giá trị của ngôn ngữ và đầu tư vào đúng lớp: semantics, compiler, runtime, tooling, security, documentation hoặc governance. Khi roadmap dựa trên nhu cầu domain, có outcome đo được và được điều chỉnh bằng phản hồi thực tế, DSL có thể tiến hóa từ prototype thành một công cụ đáng tin cậy, dễ học và có thể bảo trì lâu dài.
