# Rà soát quyết định

## 1. Rà soát quyết định là gì?

Rà soát quyết định (decision review) là hoạt động xem lại các lựa chọn thiết kế, kiến trúc và ngôn ngữ đã được đưa ra để xác định chúng còn phù hợp với mục tiêu, ràng buộc và bối cảnh hiện tại hay không. Trong một dự án DSL (Domain-Specific Language), quyết định có thể liên quan tới grammar, type system, compiler, runtime, execution model, backend, plugin API, security policy, versioning hoặc quy trình phát hành.

Một quyết định có thể hợp lý khi dự án còn nhỏ nhưng trở nên không phù hợp khi số người dùng, workload, backend hoặc yêu cầu bảo mật tăng lên. Ví dụ, một interpreter đơn giản có thể đáp ứng tốt giai đoạn đầu; khi workload lớn và cần throughput cao, nhóm cần xem lại execution model. Điều đó không có nghĩa quyết định ban đầu sai. Nó có nghĩa bối cảnh đã thay đổi và cần đánh giá lại.

Rà soát quyết định không chỉ tìm lỗi. Nó xác nhận những quyết định vẫn đang tạo ra giá trị, phát hiện hệ quả ngoài dự kiến, ghi nhận rủi ro mới và xác định việc nào cần tiếp tục, điều chỉnh hoặc thay thế.

## 2. Vì sao cần rà soát quyết định?

DSL có vòng đời dài và thường mở rộng qua nhiều giai đoạn. Một quyết định ban đầu có thể ảnh hưởng tới source compatibility, artifact format, developer tooling, runtime behavior và chi phí vận hành.

Rà soát định kỳ giúp:

1. Kiểm tra giả định ban đầu còn đúng không.
2. So sánh kết quả thực tế với mục tiêu thiết kế.
3. Phát hiện performance, security hoặc usability regression.
4. Nhận diện nợ kỹ thuật và chi phí bảo trì tích lũy.
5. Đánh giá tác động của thay đổi workload và người dùng.
6. Xác định quyết định nào cần migration hoặc deprecation.
7. Giữ kiến trúc và documentation nhất quán.
8. Tránh duy trì abstraction hoặc dependency không còn giá trị.
9. Bảo đảm các quyết định cũ vẫn tương thích với support policy.
10. Tạo cơ sở minh bạch cho việc đầu tư hoặc thay đổi roadmap.

Không nên chỉ rà soát khi có sự cố. Nếu đợi tới lúc quyết định gây vấn đề nghiêm trọng, chi phí thay đổi có thể đã tăng rất cao.

## 3. Phân biệt rà soát quyết định với review code

Code review thường tập trung vào một thay đổi cụ thể: logic, style, test và lỗi trong patch. Decision review xem xét lý do và hệ quả của một lựa chọn ở phạm vi rộng hơn.

| Hoạt động | Trọng tâm |
|---|---|
| Code review | Chất lượng của thay đổi code |
| Design review | Cấu trúc và cách giải quyết vấn đề |
| Architecture review | Các ranh giới, thành phần và quality attributes |
| Decision review | Quyết định đã chọn, giả định, bằng chứng và hệ quả |
| Security review | Threat, policy và kiểm soát bảo mật |
| Operational review | Hành vi trong môi trường chạy và khả năng vận hành |

Một quyết định có thể được triển khai đúng theo code review nhưng vẫn không còn phù hợp với nhu cầu hiện tại. Ngược lại, quyết định kiến trúc vẫn tốt dù một implementation cụ thể cần refactor.

## 4. Đối tượng cần rà soát

Trong một hệ sinh thái DSL, các quyết định đáng xem xét có thể gồm:

### 4.1. Language design

- Cú pháp và grammar.
- Keyword, operator và precedence.
- Static/dynamic typing.
- Type inference và coercion.
- Scope, visibility và module system.
- Error semantics.
- Versioning và deprecation.

### 4.2. Compiler và runtime

- Parser generator hoặc parser tự viết.
- AST, IR và serialized format.
- Interpreter, bytecode, JIT hoặc AOT.
- Optimization pipeline.
- Memory model và concurrency.
- Source mapping và debugger.

### 4.3. Integration và backend

- Query engine và database adapter.
- Workflow engine và connector.
- Plugin API và language server.
- Build tool và package manager.
- Deployment model.
- Schema registry và migration.

### 4.4. Security và operations

- Authentication và authorization.
- Sandbox và capability model.
- Secret management.
- Audit và observability.
- Timeout, retry và resource budget.
- Artifact integrity và provenance.

Không cần rà soát mọi quyết định với cùng tần suất. Ưu tiên quyết định có ảnh hưởng lớn, khó đảo ngược, có rủi ro cao hoặc đang có dấu hiệu không đạt mục tiêu.

## 5. Nguồn thông tin để rà soát

Decision review nên dựa trên nhiều loại bằng chứng:

- Architecture Decision Record (ADR).
- Requirement và use case hiện tại.
- Source và configuration.
- Benchmark và performance metrics.
- Test result và conformance suite.
- Incident, defect và support ticket.
- Security assessment và threat model.
- Cost và capacity report.
- Developer/user feedback.
- Dependency lifecycle và release note.
- Migration history.

ADR giải thích vì sao lựa chọn được đưa ra. Metrics và incident cho biết kết quả thực tế. User feedback cho biết trải nghiệm. Không nguồn nào riêng lẻ đủ để đánh giá toàn bộ quyết định.

### 5.1. Kiểm tra nguồn dữ liệu

Khi sử dụng metric, cần biết:

- Workload nào được đo?
- Khoảng thời gian nào?
- Có thay đổi traffic hoặc dữ liệu không?
- Có thay đổi phần cứng hoặc runtime không?
- Sampling và instrumentation có thay đổi không?

Nếu môi trường đo đã thay đổi, không nên so sánh trực tiếp mà không điều chỉnh hoặc giải thích.

## 6. Xác định trigger để rà soát

Một quyết định có thể được xem xét lại khi:

- Workload tăng hoặc thay đổi loại.
- Thêm backend hoặc platform.
- Số lượng người dùng hoặc module tăng.
- Performance target không còn đạt.
- Security requirement thay đổi.
- Dependency sắp hết support.
- Có incident liên quan tới quyết định.
- Chi phí vận hành vượt dự kiến.
- Team thay đổi kỹ năng hoặc quy mô.
- Language version mới cần compatibility.
- Migration trở nên quá khó hoặc thường xuyên.

Có thể phân biệt:

### 6.1. Scheduled review

Rà soát theo chu kỳ, ví dụ mỗi quý hoặc mỗi release lớn. Phù hợp với quyết định nền tảng, dependency và support policy.

### 6.2. Event-driven review

Rà soát khi có trigger như incident, workload change, security advisory hoặc feature mới.

### 6.3. Release review

Trước khi phát hành major version, xem lại các quyết định ảnh hưởng tới public contract, artifact format, migration và compatibility.

### 6.4. Review khi thay owner

Khi owner của quyết định rời nhóm hoặc chuyển trách nhiệm, cần bảo đảm rationale và operational knowledge được lưu lại.

## 7. Kiểm tra giả định ban đầu

Mỗi quyết định thường dựa trên giả định. Ví dụ:

- Parser tự viết sẽ đủ dễ bảo trì.
- Query workload chủ yếu là read-heavy.
- Người dùng chỉ cần một backend.
- Runtime có thể chạy trong một process.
- Artifact không cần được lưu lâu.
- Plugin chỉ do đội nội bộ phát triển.

Rà soát cần hỏi:

1. Giả định nào vẫn đúng?
2. Giả định nào đã thay đổi?
3. Giả định nào chưa từng được xác minh?
4. Hệ quả nào phát sinh khi giả định sai?
5. Có dữ liệu nào chứng minh điều đó?

Không nên giữ một quyết định chỉ vì nó từng được phê duyệt. Nhưng cũng không nên thay đổi chỉ vì có một công nghệ mới hấp dẫn hơn.

### 7.1. Assumption register

Có thể duy trì danh sách:

| Giả định | Cách kiểm chứng | Owner | Trạng thái |
|---|---|---|---|
| 90% query là read-only | Query telemetry | Data team | Confirmed |
| Một runtime đủ cho mọi tenant | Capacity test | Platform | Needs review |
| Artifact format ít thay đổi | Release history | Compiler team | Confirmed |

Assumption register giúp phát hiện các quyết định dựa trên giả định chưa được kiểm tra.

## 8. Đánh giá kết quả so với mục tiêu

Khi quyết định được đưa ra, nhóm nên có mục tiêu hoặc success criteria. Rà soát so sánh kết quả hiện tại với những tiêu chí đó.

Ví dụ:

~~~text
Decision:
  Use incremental parsing in the language server.

Original target:
  p95 edit-to-diagnostics latency < 200 ms
  for documents up to 20,000 lines.

Observed:
  p95 = 130 ms for common documents
  p95 = 480 ms for deeply nested documents.
~~~

Kết quả cho thấy quyết định có hiệu quả với workload phổ biến nhưng còn một nhóm trường hợp không đạt mục tiêu. Nhóm có thể tối ưu parser recovery hoặc giới hạn nesting thay vì thay toàn bộ kiến trúc.

### 8.1. Leading và lagging indicators

- Leading indicator: tín hiệu sớm như allocation rate, queue depth hoặc dependency growth.
- Lagging indicator: kết quả đã xảy ra như incident, downtime, support cost hoặc migration failure.

Kết hợp hai loại giúp phát hiện vấn đề trước khi ảnh hưởng người dùng.

### 8.2. Không thay đổi mục tiêu để hợp thức hóa kết quả

Nếu mục tiêu ban đầu không còn phù hợp, cần ghi lý do và phê duyệt thay đổi. Không nên âm thầm thay threshold sau khi không đạt.

## 9. Rà soát performance decisions

Các quyết định hiệu năng nên được xem lại bằng workload và metric thực tế:

- Interpreter hay bytecode?
- Có cần JIT hoặc AOT?
- Cache có hit rate đủ cao không?
- Incremental compilation có giảm build time?
- Parallelism có tăng throughput hay chỉ tăng contention?
- Query pushdown có giảm I/O?
- Materialization có tiết kiệm tổng chi phí?

Các chỉ số:

- Latency p50/p95/p99.
- Throughput.
- CPU và memory.
- GC pause.
- Build time.
- Startup time.
- I/O và network volume.
- Cost per successful operation.

### 9.1. Xem cả chi phí phụ

Cache có thể giảm latency nhưng tăng memory và invalidation complexity. JIT có thể tăng throughput nhưng làm cold start chậm. Parallelism có thể tăng throughput nhưng làm database saturation.

Rà soát cần xem toàn bộ trade-off, không chỉ chỉ số ban đầu được tối ưu.

### 9.2. Kiểm tra workload drift

Workload có thể thay đổi khi người dùng tạo query dài hơn, module lớn hơn hoặc workflow có nhiều branch hơn. Benchmark cũ có thể không còn đại diện.

## 10. Rà soát language design decisions

Một quyết định về syntax hoặc semantics cần được đánh giá qua:

- Người dùng có hiểu và sử dụng đúng không?
- Có ambiguity hoặc workaround thường xuyên không?
- Error diagnostics có giúp sửa lỗi không?
- Feature mới có tương tác khó hiểu với feature cũ không?
- Có ảnh hưởng đến backward compatibility không?
- Tooling có theo kịp grammar không?

Ví dụ, implicit coercion có thể làm source ngắn nhưng tạo lỗi khó đoán. Nếu support ticket cho thấy người dùng thường hiểu sai kiểu chuyển đổi, nhóm có thể cân nhắc warning, stricter mode hoặc explicit conversion trong language version mới.

### 10.1. Feature usage

Telemetry hoặc survey có thể cho biết feature nào được sử dụng. Tuy nhiên, usage thấp không tự động chứng minh feature vô ích; nó có thể là feature quan trọng nhưng hiếm hoặc khó khám phá.

### 10.2. Language complexity

Feature mới có thể tăng số quy tắc tương tác. Rà soát nên xem chi phí học, parser, type checker, documentation và test.

### 10.3. Semantic ambiguity

Nếu người dùng thường hỏi cùng một câu về null, evaluation order hoặc overload, có thể tài liệu hoặc semantics chưa đủ rõ.

## 11. Rà soát compiler và runtime architecture

Các câu hỏi:

- AST/IR có còn phản ánh đúng ngôn ngữ?
- Compiler pass có tạo bottleneck?
- Runtime có quá nhiều abstraction?
- Source mapping có đủ cho debug?
- Cache có invalidation chính xác?
- Có thể thay parser hoặc backend mà không sửa toàn hệ thống?
- Runtime có resource leak hoặc state retention?

Rà soát cần phân biệt:

- Vấn đề do quyết định kiến trúc.
- Vấn đề do implementation chưa tốt.
- Vấn đề do workload hoặc môi trường thay đổi.

Không phải mọi performance regression đều yêu cầu thay kiến trúc. Một implementation kém hiệu quả có thể được sửa trong cùng architecture.

## 12. Rà soát backend và abstraction decisions

Nếu DSL hỗ trợ nhiều backend, xem xét:

- Có bao nhiêu query/operation dùng portable core?
- Backend-specific extension có tăng nhanh không?
- Semantics có khác giữa backend?
- Adapter có cùng contract?
- Có feature nào không thể biểu đạt qua abstraction hiện tại?
- Có chi phí chuyển dữ liệu quá lớn?

Nếu chỉ còn một backend được sử dụng, abstraction đa backend có thể tạo chi phí không cần thiết. Ngược lại, khi thêm backend thứ ba, abstraction hiện tại có thể bộc lộ giới hạn.

### 12.1. Capability drift

Backend có thể bổ sung capability hoặc loại bỏ API. Compatibility matrix và planner cần được cập nhật. Không nên giữ capability declaration cũ nếu implementation không còn hỗ trợ.

### 12.2. Lock-in

Rà soát mức độ phụ thuộc vào dialect hoặc API riêng. Lock-in có thể là lựa chọn hợp lý nếu nó mang lại giá trị lớn, nhưng cần được ghi nhận thay vì xem như portability đầy đủ.

## 13. Rà soát security decisions

Security decision cần được xem lại khi threat model, dữ liệu hoặc môi trường thay đổi.

Các câu hỏi:

- Trust boundary có thay đổi không?
- Plugin hoặc dependency mới có quyền rộng hơn không?
- Authorization có được thực thi ở mọi đường truy cập?
- Tenant isolation có còn đúng với join, cache và export?
- Secret có bị ghi vào log hoặc workflow state?
- Sandbox có đủ giới hạn?
- Artifact verification có được bật trong production?
- Policy cache có phản ánh revocation?

### 13.1. Security drift

Một policy từng phù hợp có thể trở nên quá rộng khi thêm loại người dùng hoặc source mới. Rà soát role, capability và service identity theo least privilege.

### 13.2. Incident-driven review

Sau incident, cần xem quyết định nào cho phép sự cố xảy ra hoặc làm tác động lan rộng. Mục tiêu là cải thiện hệ thống và kiểm soát, không chỉ tìm cá nhân chịu trách nhiệm.

## 14. Rà soát versioning và migration decisions

Các quyết định versioning ảnh hưởng nhiều năm:

- Language version có được pin theo source không?
- Compiler hỗ trợ bao nhiêu version cũ?
- Artifact format có backward compatibility?
- Plugin API có support window?
- Schema migration có thể chạy nhiều giai đoạn?
- Workflow instance cũ được tiếp tục bằng definition nào?

Rà soát:

- Số lượng version đang phải hỗ trợ.
- Chi phí test matrix.
- Tần suất migration.
- Tỷ lệ migration tự động thành công.
- Số case cần can thiệp thủ công.
- Rủi ro artifact cũ không thể load.

Nếu support window quá rộng, chi phí maintenance có thể tăng. Nếu quá ngắn, người dùng không có đủ thời gian nâng cấp. Quyết định cần cân bằng nhu cầu vận hành và năng lực support.

## 15. Rà soát developer experience

Một DSL có thể đúng về kỹ thuật nhưng khó sử dụng:

- Completion chậm.
- Diagnostics không rõ.
- Documentation khó tìm.
- Formatter gây diff lớn.
- Error message không chỉ vị trí.
- Debugger không map về source.
- Setup project phức tạp.

Rà soát nên kết hợp:

- Task completion time.
- User feedback.
- Support ticket.
- Editor telemetry phù hợp privacy policy.
- Onboarding feedback.
- Tỷ lệ lỗi thường gặp.

Nếu người dùng thường xuyên phải dùng workaround, đó có thể là tín hiệu abstraction hoặc tooling chưa phù hợp.

## 16. Rà soát technical debt

Technical debt là chi phí tương lai phát sinh từ lựa chọn hoặc shortcut kỹ thuật hiện tại.

Trong DSL, debt có thể gồm:

- Parser rule khó mở rộng.
- AST chứa nhiều metadata trùng lặp.
- Legacy syntax chưa được loại bỏ.
- Adapter phụ thuộc API nội bộ.
- Test corpus không có version.
- Documentation không đồng bộ semantics.
- Cache invalidation thủ công.
- Build script không tái lập.
- Runtime có global state.

### 16.1. Debt register

Ghi:

- Mô tả debt.
- Quyết định hoặc nguyên nhân tạo debt.
- Tác động hiện tại.
- Chi phí nếu không xử lý.
- Owner.
- Trigger hoặc thời điểm xem xét.

### 16.2. Không phải mọi debt đều phải trả ngay

Một shortcut có thể hợp lý nếu giúp kiểm chứng use case và chưa tạo chi phí lớn. Rà soát giúp phân biệt debt chấp nhận được với debt đang làm chậm phát triển hoặc tăng rủi ro.

## 17. Đánh giá lựa chọn: giữ, điều chỉnh hay thay thế

Sau khi thu thập bằng chứng, thường có ba hướng:

### 17.1. Giữ nguyên

Chọn khi:

- Mục tiêu vẫn đạt.
- Rủi ro được kiểm soát.
- Chi phí bảo trì chấp nhận được.
- Không có phương án thay thế tạo giá trị đủ lớn.

### 17.2. Điều chỉnh

Chọn khi ý tưởng cốt lõi vẫn đúng nhưng implementation hoặc cấu hình cần thay đổi.

Ví dụ:

- Giữ bytecode VM nhưng cải thiện instruction dispatch.
- Giữ adapter abstraction nhưng thêm capability extension.
- Giữ cache nhưng thay invalidation strategy.
- Giữ language syntax nhưng cải thiện diagnostics.

### 17.3. Thay thế

Chọn khi:

- Giả định nền tảng không còn đúng.
- Rủi ro hoặc chi phí vượt lợi ích.
- Requirement mới không thể đáp ứng hợp lý.
- Công nghệ hết support hoặc có rủi ro bảo mật.
- Một phương án mới có lợi ích đủ lớn sau khi tính migration cost.

Thay thế thường cần migration plan, compatibility window và rollback strategy.

## 18. Decision review workshop

Một buổi review có thể theo trình tự:

1. Nêu decision ID và phạm vi.
2. Đọc lại context và rationale ban đầu.
3. Xác nhận mục tiêu và constraints hiện tại.
4. Xem metrics, incidents và feedback.
5. Kiểm tra giả định.
6. Liệt kê hệ quả ngoài dự kiến.
7. Đánh giá rủi ro và technical debt.
8. Xem các phương án giữ/điều chỉnh/thay thế.
9. Ghi quyết định và action items.
10. Đặt review trigger tiếp theo.

### 18.1. Thành phần tham gia

Tùy phạm vi, có thể mời:

- Decision owner.
- Maintainer của component.
- Developer sử dụng DSL.
- Domain expert.
- Operator.
- Security/platform representative.
- Product hoặc architecture owner.

Không cần mời mọi người cho mọi quyết định. Cần đủ người hiểu context, usage và impact.

### 18.2. Cách tránh review thành tranh luận ý kiến

- Dùng dữ liệu và ví dụ cụ thể.
- Phân biệt fact với assumption.
- Ghi confidence level.
- Nêu điều kiện có thể làm thay đổi kết luận.
- Timebox phần thảo luận.
- Chốt owner và hành động.

## 19. Cập nhật ADR sau review

Nếu quyết định vẫn giữ, có thể thêm review note:

~~~markdown
## Review — 2026-11

Status: Confirmed

Evidence:
- p95 latency remains within target.
- No compatibility incidents in supported matrix.

Decision:
- Keep current execution model.

Next review trigger:
- Revisit when workflow throughput grows beyond current capacity.
~~~

Nếu quyết định thay đổi, tạo ADR mới và đánh dấu ADR cũ là Superseded. Không nên viết lại lịch sử như thể lựa chọn mới đã luôn tồn tại.

## 20. Theo dõi action items

Decision review cần tạo hành động có owner và điều kiện hoàn tất:

| Action | Owner | Evidence of completion |
|---|---|---|
| Thêm benchmark cho query lớn | Query team | CI benchmark report |
| Cập nhật compatibility matrix | Compiler owner | Published matrix |
| Thử migration trên corpus cũ | Migration owner | Migration test result |
| Giảm quyền plugin | Security owner | Permission test |

Action item không có owner hoặc tiêu chí hoàn tất thường dễ bị quên.

## 21. Đo lường chất lượng của quá trình ra quyết định

Không nên đánh giá decision process chỉ bằng số lượng ADR. Có thể xem:

- Tỷ lệ quyết định có rationale và evidence.
- Số giả định được kiểm chứng.
- Số quyết định được xem lại khi trigger xuất hiện.
- Thời gian từ phát hiện vấn đề tới quyết định.
- Số incident liên quan tới assumption sai.
- Chi phí migration so với ước lượng.
- Số action item hoàn thành đúng hạn.

Mục tiêu là tăng chất lượng và khả năng truy nguyên, không tạo thủ tục giấy tờ quá nặng.

## 22. Những lỗi thường gặp khi rà soát quyết định

### Chỉ xem lại khi có incident

Các vấn đề âm thầm tích lũy không được phát hiện. Dùng cả scheduled và event-driven review.

### Không đọc rationale ban đầu

Nhóm đánh giá quyết định trong bối cảnh hiện tại mà quên constraints lúc chọn. Đọc lại context và assumptions.

### Dùng dữ liệu không đại diện

Benchmark nhỏ hoặc feedback từ một nhóm không phản ánh workload chung. Chọn evidence phù hợp với phạm vi.

### Đánh đồng implementation bug với kiến trúc sai

Một bug có thể sửa mà không cần thay architecture. Phân tích nguyên nhân trước khi quyết định.

### Giữ quyết định vì sunk cost

Chi phí đã bỏ ra không phải lý do đủ để tiếp tục nếu lợi ích tương lai không còn. So sánh chi phí tương lai của các phương án.

### Thay quyết định theo xu hướng

Công nghệ mới không tự động tốt hơn. Đánh giá migration, team expertise và TCO.

### Không ghi lại kết quả review

Nhóm sau không biết quyết định đã được xem xét và vì sao vẫn giữ. Cập nhật ADR hoặc review note.

### Không có action owner

Vấn đề được thảo luận nhưng không được xử lý. Giao owner và evidence rõ ràng.

## 23. Quy trình rà soát quyết định cho dự án DSL

Một quy trình có thể áp dụng:

1. **Lập danh mục quyết định.** Tìm ADR, design note và các contract quan trọng.
2. **Phân loại mức ảnh hưởng.** Public semantics, runtime, security, performance, operations.
3. **Xác định trigger.** Scheduled, incident, release hoặc thay đổi workload.
4. **Thu thập evidence.** Metrics, tests, user feedback, cost và dependency status.
5. **Đọc rationale.** Xác nhận giả định và constraint ban đầu.
6. **Đánh giá kết quả.** So sánh mục tiêu với hành vi hiện tại.
7. **Phân tích residual risk.** Ghi rủi ro và technical debt còn lại.
8. **Chọn hướng.** Giữ, điều chỉnh hoặc thay thế.
9. **Cập nhật ADR.** Ghi quyết định, evidence và review trigger.
10. **Tạo action items.** Owner, deadline và tiêu chí hoàn tất.
11. **Theo dõi kết quả.** Xác nhận thay đổi tạo tác động mong muốn.
12. **Lên lịch review tiếp theo.** Dựa trên mức rủi ro và tốc độ thay đổi.

## 24. Ví dụ end-to-end: rà soát quyết định về query backend

Giả sử một DSL ban đầu chỉ hỗ trợ SQL backend. ADR cũ ghi:

~~~text
Decision:
  Use SQL-specific query translation.

Rationale:
  Only one relational database is required.
  Direct SQL translation minimizes implementation effort.
~~~

Sau hai năm, hệ thống cần thêm document database và in-memory executor cho test.

### 24.1. Evidence

- Số backend đã tăng từ một lên ba.
- Nhiều query logic đang bị lặp trong từng adapter.
- Null và ordering semantics khác giữa các backend.
- Integration test phụ thuộc database thật nên chậm.
- Một số feature không thể chạy trên in-memory test adapter.

### 24.2. Review

Giả định "chỉ có một relational backend" không còn đúng. SQL translation vẫn có giá trị nhưng không còn phù hợp làm mô hình trung tâm.

### 24.3. Options

| Phương án | Ưu điểm | Đánh đổi |
|---|---|---|
| Giữ SQL-specific model | Không cần migration lớn | Backend mới tiếp tục phải giả lập SQL |
| Thêm adapter song song | Ít thay đổi core | Logic query bị trùng |
| Tạo logical query IR | Core độc lập backend | Chi phí migration và planner |

### 24.4. Decision

Chuyển dần sang logical query IR, giữ SQL adapter hiện tại và thêm document/in-memory adapter theo capability. Không chuyển toàn bộ trong một release.

### 24.5. Actions

- Định nghĩa semantics portable cho null, ordering và projection.
- Tạo conformance suite.
- Chuyển một nhóm query representative.
- So sánh result và performance.
- Giữ fallback SQL path trong thời gian migration.
- Cập nhật ADR cũ thành Superseded khi migration đạt điều kiện.

Ví dụ cho thấy review không phủ nhận lựa chọn cũ; nó xác định giả định đã thay đổi và đưa ra lộ trình thích nghi.

## 25. Mẫu decision review note

~~~markdown
# Decision Review: [Decision ID and title]

## Original decision
What was selected and when?

## Original context
Which problem, assumptions and constraints led to it?

## Current context
What has changed in users, workload, platform or requirements?

## Evidence
Metrics, incidents, tests, cost and feedback.

## Assessment
Which goals are met? Which assumptions no longer hold?

## Risks and debt
Current limitations and residual risks.

## Outcome
Keep | Adjust | Replace

## Actions
Owner, target date and completion evidence.

## Next review trigger
What event or metric should reopen the decision?
~~~

## 26. Kết luận

Rà soát quyết định giúp dự án DSL xác nhận các lựa chọn kiến trúc và ngôn ngữ vẫn phù hợp khi người dùng, workload, backend, security requirement và môi trường vận hành thay đổi. Hoạt động này kết hợp rationale ban đầu với evidence hiện tại như metrics, test, incident, feedback và cost để quyết định giữ, điều chỉnh hoặc thay thế.

Một quy trình tốt không tìm người chịu lỗi cho quyết định cũ. Nó kiểm tra giả định, nhận diện hệ quả và residual risk, ghi lại kết quả trong ADR, rồi giao action có owner và evidence. Các quyết định khó đảo ngược hoặc ảnh hưởng public contract cần được xem xét kỹ hơn; quyết định nhỏ và reversible có thể được đánh giá nhanh hơn.

Khi review được thực hiện định kỳ và theo trigger, nhóm tránh duy trì kiến trúc chỉ vì thói quen hoặc sunk cost. DSL có thể tiếp tục phát triển mà vẫn giữ được lý do thiết kế, compatibility và khả năng vận hành lâu dài.
