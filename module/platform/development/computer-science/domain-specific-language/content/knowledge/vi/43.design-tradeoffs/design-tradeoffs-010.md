# Khung ra quyết định

## 1. Khung ra quyết định trong thiết kế DSL là gì?

Khung ra quyết định (decision framework) là một cách tiếp cận có cấu trúc để lựa chọn giữa nhiều phương án thiết kế dựa trên mục tiêu, ràng buộc, bằng chứng và rủi ro. Trong quá trình xây dựng DSL (Domain-Specific Language), nhóm thường phải lựa chọn giữa các phương án có ưu điểm và chi phí khác nhau: parser generator hay parser tự viết, interpreter hay compiler, cú pháp khai báo hay mệnh lệnh, static typing hay dynamic typing, một backend chung hay nhiều adapter chuyên biệt.

Không có lựa chọn nào luôn tốt nhất cho mọi DSL. Một thiết kế phù hợp với DSL cấu hình nhỏ có thể không phù hợp với query engine xử lý dữ liệu lớn hoặc workflow engine có side effect. Khung ra quyết định giúp nhóm xác định lựa chọn phù hợp với bối cảnh cụ thể và giải thích được vì sao lựa chọn đó được đưa ra.

Ví dụ, nhóm cần chọn cách thực thi DSL:

| Phương án | Lợi ích chính | Chi phí chính |
|---|---|---|
| Tree-walking interpreter | Dễ triển khai và debug | Runtime dispatch có thể chậm |
| Bytecode VM | Runtime model thống nhất | Cần instruction set và VM |
| JIT compiler | Tối ưu theo workload thực tế | Warm-up và độ phức tạp cao |
| AOT compiler | Startup nhanh, artifact độc lập hơn | Build target-specific và pipeline phức tạp |

Khung quyết định giúp đánh giá workload, latency, startup, memory, portability, năng lực nhóm và chi phí bảo trì trước khi chọn.

## 2. Vì sao cần một khung ra quyết định?

Quyết định kiến trúc DSL thường có ảnh hưởng lâu dài. Một lựa chọn parser có thể ảnh hưởng grammar evolution, IDE tooling và error recovery. Một lựa chọn type system có thể tác động compiler, runtime, documentation và migration. Một abstraction backend có thể quyết định khả năng portability trong nhiều năm.

Khung ra quyết định giúp:

1. Làm rõ vấn đề thực sự cần giải quyết.
2. Tách yêu cầu bắt buộc khỏi sở thích hoặc giả định.
3. So sánh các phương án trên cùng một bộ tiêu chí.
4. Nhận diện chi phí ẩn và tác động dây chuyền.
5. Tránh chọn công nghệ chỉ vì phổ biến hoặc quen thuộc.
6. Dùng prototype và benchmark để kiểm chứng giả định.
7. Ghi lại lý do, bằng chứng và rủi ro được chấp nhận.
8. Giúp stakeholder hiểu trade-off.
9. Tạo cơ sở cho review và thay đổi quyết định sau này.
10. Giảm việc lặp lại tranh luận khi nhóm hoặc bối cảnh thay đổi.

Một framework không thay thế judgment của kiến trúc sư. Nó giúp judgment dựa trên bằng chứng và được diễn đạt rõ ràng.

## 3. Bắt đầu từ vấn đề và bối cảnh

Không nên bắt đầu bằng câu hỏi "nên dùng công nghệ nào?". Trước tiên cần mô tả vấn đề, người dùng và môi trường mà DSL sẽ hoạt động.

Các câu hỏi:

- DSL phục vụ ai: developer, analyst, operator hay người dùng nghiệp vụ?
- Người dùng cần diễn đạt loại logic nào?
- DSL chạy trong editor, server, embedded runtime hay CI?
- Có bao nhiêu project hoặc module?
- Source có được lưu lâu dài không?
- Có nhiều backend hoặc runtime không?
- Tần suất thay đổi grammar và schema ra sao?
- Hệ thống có yêu cầu latency, throughput hoặc startup cụ thể không?
- Dữ liệu và thao tác có nhạy cảm không?
- Ai chịu trách nhiệm vận hành và bảo trì?

Ví dụ bối cảnh:

~~~text
Use case:
  Analysts define reporting queries over business data.

Constraints:
  - Queries must be type checked before execution.
  - Tenant data must remain isolated.
  - The same query model should support SQL and test execution.
  - Query response target is under 500 ms for common reports.
  - The team has limited compiler engineering capacity.
~~~

Context giúp loại bỏ phương án không phù hợp trước khi so sánh chi tiết.

## 4. Xác định stakeholder và người ra quyết định

Một thiết kế DSL có thể ảnh hưởng nhiều nhóm:

- Language designer: grammar, type system và semantics.
- Compiler/runtime engineer: parser, optimizer và execution.
- Domain expert: vocabulary và business rules.
- Application developer: integration và API.
- Operator: deployment, monitoring và recovery.
- Security owner: identity, policy và data protection.
- End user: khả năng học và sử dụng DSL.

Không phải mọi stakeholder đều có quyền quyết định mọi vấn đề. Cần xác định:

- Ai đề xuất phương án?
- Ai cung cấp yêu cầu hoặc bằng chứng?
- Ai review?
- Ai phê duyệt quyết định có ảnh hưởng lớn?
- Ai sở hữu việc triển khai và theo dõi?

Nếu một quyết định ảnh hưởng tới contract công khai của ngôn ngữ, nên có owner rõ ràng và quy trình review rộng hơn thay đổi implementation nội bộ.

## 5. Phân biệt driver, constraint và preference

Ba loại thông tin thường bị trộn lẫn:

### 5.1. Decision driver

Driver là yếu tố quan trọng ảnh hưởng lựa chọn:

- Compile time.
- Runtime latency.
- Khả năng mở rộng.
- Tính an toàn kiểu.
- Portability.
- Khả năng học.
- Khả năng bảo trì.

### 5.2. Constraint

Constraint là điều kiện bắt buộc:

- Phải chạy trên JDK version được hỗ trợ.
- Phải giữ tương thích với artifact format hiện tại.
- Không được thực thi code không tin cậy ngoài sandbox.
- Không được vượt ngân sách memory của thiết bị.
- Phải hỗ trợ backend đã cam kết.

Phương án vi phạm constraint nên bị loại, dù có điểm số cao ở các tiêu chí khác.

### 5.3. Preference

Preference là điều mong muốn nhưng có thể đánh đổi:

- Dùng ngôn ngữ lập trình nhóm đã quen.
- Ưu tiên thư viện có cộng đồng lớn.
- Giữ API gần với framework hiện có.
- Muốn giảm số dependency.

Preference giúp xếp hạng phương án sau khi kiểm tra constraints.

## 6. Xác định quality attributes

Quality attributes là các đặc tính chất lượng mà kiến trúc cần đạt.

| Nhóm | Thuộc tính |
|---|---|
| Performance | Latency, throughput, startup, compile time |
| Scalability | Số module, số user, kích thước workspace, concurrency |
| Reliability | Recovery, fault isolation, availability |
| Security | Least privilege, isolation, audit, integrity |
| Usability | Learnability, readability, diagnostics |
| Maintainability | Modularity, testability, complexity |
| Portability | Backend, platform và runtime support |
| Evolvability | Grammar evolution, versioning, migration |
| Operability | Monitoring, deployment, debugging |
| Cost | Development, infrastructure và maintenance cost |

Không nên chọn quá nhiều thuộc tính làm tiêu chí chính. Hãy xác định một vài quality attributes quyết định thành công của use case và dùng các thuộc tính khác làm guardrail.

## 7. Chuyển mục tiêu thành tiêu chí có thể đo

Tiêu chí nên có cách đánh giá cụ thể thay vì chỉ dùng từ "nhanh", "dễ" hoặc "linh hoạt".

Ví dụ:

| Mục tiêu | Tiêu chí đo hoặc bằng chứng |
|---|---|
| Editor phản hồi nhanh | Completion p95 dưới 150 ms |
| Build workspace lớn | Compile time trên corpus đại diện |
| Runtime tiết kiệm memory | Peak heap trong workload chuẩn |
| Hỗ trợ nhiều backend | Số semantics chung có conformance test |
| Dễ học | Thời gian hoàn thành task của nhóm người dùng thử |
| Dễ bảo trì | Số module phụ thuộc, độ phức tạp và testability |
| An toàn | Threat coverage và security test result |

Các ngưỡng phải đến từ nhu cầu thực tế. Không nên chọn con số tùy ý chỉ để tạo vẻ định lượng.

### 7.1. Scenario-based requirements

Một cách hữu ích là mô tả tình huống:

~~~text
When an analyst edits a query in a workspace with 500 files,
the language server should return completion suggestions
within the agreed latency target under normal load.
~~~

Scenario giúp liên kết kiến trúc với trải nghiệm hoặc vận hành thực tế.

### 7.2. Guardrail

Guardrail là giới hạn không được vượt:

- Memory không vượt mức thiết bị.
- Query không chạy vô hạn.
- Không có quyền truy cập cross-tenant.
- Build không phụ thuộc network không kiểm soát.
- Public API không bị phá vỡ ngoài version policy.

Guardrail có thể là điều kiện pass/fail thay vì điểm số.

## 8. Tạo các phương án khả thi

Sau khi xác định vấn đề, tạo ít nhất hai phương án có thể triển khai. Không nên tạo một phương án yếu chỉ để phương án ưa thích có vẻ tốt hơn.

Ví dụ chọn parser:

| Phương án | Mô tả |
|---|---|
| A: Parser tự viết | Recursive descent và Pratt parser |
| B: Parser generator | Grammar khai báo và generated parser |
| C: Incremental parser framework | Parser hỗ trợ cập nhật từng phần cho editor |

Mỗi phương án nên có:

- Kiến trúc khái quát.
- Dependency hoặc công nghệ cần dùng.
- Ưu điểm.
- Chi phí và rủi ro.
- Ảnh hưởng tới tooling.
- Khả năng mở rộng.
- Cách kiểm chứng.

### 8.1. Phương án giữ nguyên hiện trạng

Luôn cân nhắc không thay đổi hoặc trì hoãn quyết định nếu chưa có bằng chứng đủ mạnh. Đây là một phương án thực sự, không phải mặc định thất bại.

### 8.2. Phương án kết hợp

Có thể kết hợp giải pháp, ví dụ dùng parser generator cho grammar chính và handwritten parser cho expression đặc biệt. Tuy nhiên, phương án kết hợp cũng có chi phí tích hợp và hai mô hình error recovery.

### 8.3. Loại phương án không khả thi

Loại sớm phương án vi phạm constraint, không có người bảo trì hoặc yêu cầu capability không thể đáp ứng. Ghi lý do để tránh đưa lại vào vòng thảo luận sau mà không có thông tin mới.

## 9. Ma trận đánh giá có trọng số

Decision matrix giúp so sánh phương án theo tiêu chí và trọng số.

Ví dụ chọn execution model:

| Tiêu chí | Trọng số | Interpreter | Bytecode VM | JIT |
|---|---:|---:|---:|---:|
| Startup time | 20% | 5 | 4 | 2 |
| Steady-state speed | 25% | 2 | 4 | 5 |
| Implementation effort | 20% | 5 | 3 | 1 |
| Debuggability | 15% | 5 | 4 | 2 |
| Memory footprint | 10% | 4 | 4 | 2 |
| Portability | 10% | 5 | 5 | 3 |

Điểm số là ví dụ minh họa. Có thể tính:

\[
Score(option) = \sum_i weight_i \times rating_{i,option}
\]

### 9.1. Chọn thang điểm

Thang 1-5 có thể dùng:

- 1: đáp ứng kém.
- 2: có nhiều hạn chế.
- 3: đáp ứng chấp nhận được.
- 4: đáp ứng tốt.
- 5: đáp ứng rất tốt.

Mỗi rating nên có lý do hoặc bằng chứng. Nếu không có số đo, ghi rõ đây là estimate.

### 9.2. Tránh độ chính xác giả

Điểm 4.2 không nhất thiết chính xác hơn điểm 4. Không nên để tổng điểm quyết định máy móc khi khác biệt rất nhỏ hoặc dữ liệu đầu vào chưa chắc chắn.

### 9.3. Sensitivity analysis

Thử thay đổi trọng số để xem kết luận có đổi không. Nếu phương án thắng chỉ khi một tiêu chí có trọng số rất cao, cần xác nhận tiêu chí đó thực sự quan trọng.

### 9.4. Hard constraints

Không dùng weighted score để bù cho việc vi phạm constraint bảo mật hoặc tương thích. Phương án vi phạm hard constraint bị loại trước khi tính điểm.

## 10. Phân tích trade-off và chi phí vòng đời

Chi phí của thiết kế không chỉ là effort ban đầu.

Các loại chi phí:

- Implementation cost.
- Learning cost.
- Build và runtime infrastructure.
- Testing và CI.
- Observability và support.
- Upgrade và migration.
- Dependency maintenance.
- Training và documentation.
- Operational incident cost.

Ví dụ, parser tự viết có thể triển khai nhanh với grammar nhỏ nhưng tốn nhiều effort khi thêm error recovery, incremental parsing và syntax highlighting. Parser generator có chi phí setup ban đầu nhưng có thể giảm maintenance cho grammar lớn.

### 10.1. Total Cost of Ownership

TCO xem tổng chi phí trong vòng đời:

~~~text
TCO =
  initial development
  + maintenance
  + operations
  + upgrades
  + support
  + migration
~~~

Một thư viện miễn phí không có nghĩa chi phí sở hữu bằng không. Nếu không có maintainer hoặc khó nâng version, chi phí tương lai có thể cao.

### 10.2. Opportunity cost

Thời gian xây một optimizer phức tạp là thời gian không dành cho language server, documentation hoặc security. Cần xem lựa chọn ảnh hưởng roadmap và khả năng hoàn thành mục tiêu khác thế nào.

## 11. Rủi ro và độ bất định

Một quyết định có thể có lợi ích cao nhưng dựa trên giả định chưa được kiểm chứng.

Ghi nhận:

- Giả định kỹ thuật.
- Giả định về workload.
- Dependency hoặc vendor risk.
- Khả năng lock-in.
- Khả năng team duy trì.
- Tác động khi phương án thất bại.
- Chi phí chuyển đổi.

### 11.1. Risk matrix

Có thể đánh giá likelihood và impact:

| Likelihood | Impact | Cách xử lý gợi ý |
|---|---|---|
| Thấp | Thấp | Theo dõi |
| Thấp | Cao | Có contingency |
| Cao | Thấp | Giảm chi phí hoặc tự động hóa |
| Cao | Cao | Ưu tiên mitigation hoặc loại phương án |

Đánh giá phải ghi giả định. Risk score không phải xác suất chính xác nếu không có dữ liệu thống kê.

### 11.2. Reversibility

Một quyết định dễ đảo ngược có thể được thử sớm. Quyết định khó đảo ngược như public language syntax, serialized format hoặc plugin API cần review kỹ hơn.

Có thể phân loại:

- Reversible: thay đổi implementation nội bộ.
- Costly to reverse: đổi parser architecture hoặc IR.
- Hard to reverse: công bố public semantics hoặc artifact format được sử dụng rộng rãi.

## 12. Prototype và spike kỹ thuật

Khi thiếu bằng chứng, tạo prototype nhỏ để kiểm chứng giả định.

Ví dụ:

- Parse corpus thật bằng hai parser.
- Compile một query representative bằng interpreter và bytecode.
- Benchmark incremental type checking.
- Thử adapter trên database thật.
- Mô phỏng migration từ schema cũ.

Prototype nên có câu hỏi rõ:

~~~text
Question:
  Can incremental parsing keep editor latency under the target
  for a large document?

Measure:
  p50/p95 edit-to-diagnostics latency

Success condition:
  Meets target without excessive memory growth
~~~

### 12.1. Spike không phải production implementation

Prototype có thể bỏ qua một số concerns để kiểm chứng ý tưởng. Không nên đưa code spike vào production mà không đánh giá security, error handling, observability và maintainability.

### 12.2. Benchmark công bằng

So sánh phương án trên cùng hardware, input, version và warm-up condition. Ghi lại cấu hình để người khác có thể lặp lại.

## 13. Decision record và Architecture Decision Record

Architecture Decision Record (ADR) ghi lại một quyết định kiến trúc và bối cảnh của nó.

Một ADR thường gồm:

- Title và ID.
- Status.
- Context.
- Decision drivers.
- Options considered.
- Decision.
- Consequences.
- Risks.
- Evidence.
- Review trigger.

Ví dụ:

~~~markdown
# ADR-012: Use bytecode VM for workflow execution

## Status
Accepted

## Context
Workflow definitions are executed repeatedly and need predictable startup.

## Decision
Compile workflow AST to versioned bytecode and execute it in a VM.

## Consequences
- Runtime dispatch becomes more uniform.
- A bytecode verifier and format version are required.
- Debugging needs source maps.

## Review trigger
Revisit if startup or throughput targets are not met.
~~~

ADR không cần ghi lại mọi chi tiết implementation. Nó tập trung vào quyết định và hệ quả có ảnh hưởng dài hạn.

### 13.1. Status

Trạng thái thường gồm:

- Proposed.
- Accepted.
- Rejected.
- Superseded.
- Deprecated.

Nếu quyết định bị thay thế, liên kết ADR mới với ADR cũ để giữ lịch sử.

### 13.2. Không xóa quyết định cũ

Một ADR cũ có thể không còn áp dụng nhưng vẫn giải thích tại sao hệ thống có cấu trúc hiện tại. Đánh dấu Superseded thay vì xóa.

## 14. Phân tích tác động theo vòng đời DSL

Một quyết định cần được đánh giá xuyên suốt:

~~~mermaid
flowchart TD
    A["Authoring"] --> B["Parsing and validation"]
    B --> C["Compilation or planning"]
    C --> D["Packaging"]
    D --> E["Deployment"]
    E --> F["Execution"]
    F --> G["Monitoring and evolution"]
~~~

Ví dụ chọn dynamic typing có thể:

- Giảm annotation khi authoring.
- Tăng runtime type checks.
- Làm diagnostics muộn hơn.
- Ảnh hưởng optimizer.
- Tăng lỗi khi execution.
- Làm documentation khó mô tả output type.

Không nên đánh giá một quyết định chỉ ở tầng nơi nó được triển khai. Cần xem tác động tới author, compiler, runtime và operator.

## 15. Decision framework cho grammar và syntax

Khi chọn cú pháp, đánh giá:

- Readability.
- Learnability.
- Ambiguity.
- Parser complexity.
- Error recovery.
- Extensibility.
- Formatting.
- Backward compatibility.

Ví dụ lựa chọn block delimiter:

~~~text
if condition {
    action()
}
~~~

so với:

~~~text
IF condition THEN
    action()
END
~~~

Một cú pháp có thể gần với ngôn ngữ lập trình phổ biến; cú pháp khác có thể dễ đọc trong môi trường cấu hình hoặc nghiệp vụ. Cần thử với người dùng mục tiêu và các cấu trúc lồng nhau, không chỉ một ví dụ đơn giản.

### 15.1. Ambiguity

Nếu grammar có nhiều cách parse cho cùng source, parser cần precedence hoặc disambiguation rule. Ambiguity có thể làm compiler và IDE diễn giải khác nhau.

### 15.2. Error recovery

Syntax dễ parse chưa chắc dễ sửa khi lỗi. Cần xem editor có thể tiếp tục phân tích file chưa hoàn chỉnh không.

## 16. Decision framework cho type system

Các lựa chọn:

- Static typing hay dynamic typing.
- Explicit annotation hay type inference.
- Nominal hay structural typing.
- Nullable type hay option type.
- Implicit coercion hay conversion tường minh.
- Generic hay specialized API.

Đánh giá:

- Lỗi được phát hiện khi nào?
- Người dùng có hiểu diagnostics không?
- Compiler time và memory tăng bao nhiêu?
- Runtime checks có cần thiết không?
- API có dễ tích hợp không?
- Schema evolution ảnh hưởng thế nào?

Ví dụ, static typing phù hợp khi DSL cần validate trước khi triển khai; dynamic typing có thể phù hợp với scripting nhỏ hoặc dữ liệu không có schema ổn định. Một lựa chọn hybrid có thể cung cấp type inference nhưng yêu cầu annotation ở boundary.

## 17. Decision framework cho execution model

Lựa chọn interpreter, bytecode, JIT, AOT hoặc transpilation cần xét:

- Startup time.
- Steady-state throughput.
- Compile time.
- Artifact size.
- Memory.
- Debuggability.
- Platform portability.
- Runtime sandbox.
- Operational complexity.

Không nên chọn JIT chỉ vì benchmark hot loop nhanh nếu workload thực tế chạy vài giây rồi thoát. Cũng không nên chọn interpreter chỉ vì prototype dễ viết nếu production yêu cầu throughput cao.

## 18. Decision framework cho backend abstraction

Một DSL có thể:

- Hỗ trợ một backend cụ thể.
- Có portable core và dialect extension.
- Dùng adapter interface.
- Sinh code target-specific.
- Đẩy toàn bộ query xuống backend.
- Chạy một phần logic ở engine trung gian.

Đánh giá:

- Semantics có giống nhau không?
- Capability nào bị thiếu?
- Cost của data transfer?
- Transaction và consistency?
- Observability và explain?
- Vendor lock-in?
- Test conformance?

Một abstraction quá rộng có thể làm mất khả năng tối ưu của backend. Một abstraction quá cụ thể làm source khó chuyển đổi. Decision cần cân bằng portability và performance.

## 19. Decision framework cho security và isolation

Các quyết định:

- In-process hay process isolation.
- Capability allowlist hay unrestricted host access.
- Static authorization hay runtime authorization.
- Tenant isolation ở application hay database.
- Secret injection qua environment hay secret manager.
- Sandboxed plugin hay trusted extension.

Security requirement nên là hard constraint khi liên quan dữ liệu nhạy cảm hoặc code không tin cậy. Không nên dùng điểm performance cao để bù cho việc vi phạm yêu cầu cách ly.

Threat model và risk assessment nên cung cấp input cho decision matrix. Test evidence phải chứng minh enforcement thực tế.

## 20. Decision framework cho versioning và evolution

Các câu hỏi:

- Có cần nhiều language version đồng thời không?
- Artifact format có cần ổn định qua release không?
- Có migration tool không?
- Public API có SemVer không?
- Plugin cần compatibility range nào?
- Workflow instance đang chạy có được migrate không?

Một quyết định versioning có ảnh hưởng lớn tới chi phí support. Cần xem tuổi thọ artifact và dữ liệu, không chỉ thời gian phát hành compiler.

## 21. Decision framework cho performance

Trước khi tối ưu:

1. Xác định workload đại diện.
2. Chọn chỉ số quan trọng.
3. Đo baseline.
4. Xác định bottleneck.
5. Tạo phương án.
6. Đánh giá ảnh hưởng tới correctness, memory và complexity.
7. Prototype và benchmark.
8. Kiểm tra regression.

Ví dụ cache:

| Tiêu chí | Không cache | Cache |
|---|---|---|
| Latency lặp lại | Cao hơn | Thấp hơn khi hit |
| Memory | Thấp | Cao hơn |
| Freshness | Theo source hiện tại | Cần invalidation |
| Complexity | Thấp | Cao hơn |
| Multi-tenant safety | Ít rủi ro cache leakage | Key phải chứa security scope |

Nếu cache hit rate thấp hoặc invalidation phức tạp, cache có thể không đáng dùng.

## 22. Quyết định reversible và irreversible

Một cách ưu tiên là xem mức độ đảo ngược:

- Quyết định dễ đảo ngược: thử nhanh và đo.
- Quyết định tốn kém để đảo: tạo prototype và ADR.
- Quyết định khó đảo: review kỹ, kiểm tra compatibility và lấy ý kiến stakeholder.

Ví dụ:

| Quyết định | Mức đảo ngược |
|---|---|
| Thay implementation nội bộ của visitor | Dễ |
| Chuyển AST sang IR mới | Trung bình |
| Thay artifact format công khai | Khó |
| Đổi semantics của operator trong language version đã phát hành | Rất khó |

Không nên trì hoãn mọi quyết định khó đảo, nhưng cần thêm bằng chứng và kế hoạch migration.

## 23. Khi nào cần prototype, khi nào cần quyết định ngay?

Prototype hữu ích khi:

- Có rủi ro kỹ thuật chưa rõ.
- Benchmark có thể thay đổi kết luận.
- Backend capability chưa được xác nhận.
- Integration API chưa ổn định.
- Team chưa có kinh nghiệm với công nghệ.

Có thể quyết định trực tiếp khi:

- Constraint đã loại bỏ các phương án khác.
- Thay đổi nhỏ và reversible.
- Bằng chứng từ workload tương tự đủ mạnh.
- Chi phí thử nghiệm lớn hơn giá trị thông tin.

Prototype nên có timebox và success criteria. Nếu không, spike có thể kéo dài thành dự án thứ hai mà không tạo quyết định.

## 24. Theo dõi quyết định sau khi triển khai

Một quyết định không kết thúc khi merge code. Cần theo dõi xem giả định có đúng trong production hay không.

Các tín hiệu:

- Performance metrics.
- Error rate.
- Support ticket.
- Developer feedback.
- Incident.
- Cost.
- Dependency lifecycle.
- Upgrade difficulty.

Review trigger có thể là:

- p95 latency vượt ngưỡng.
- Số backend tăng.
- Team hoặc workload thay đổi.
- Dependency hết support.
- Security advisory.
- Language feature mới làm giả định cũ không còn đúng.

Nếu trigger xảy ra, mở lại ADR hoặc tạo quyết định thay thế.

## 25. Những lỗi thường gặp khi ra quyết định

### Chọn công nghệ trước khi hiểu vấn đề

Nhóm bị dẫn dắt bởi xu hướng. Viết context và decision drivers trước.

### Không phân biệt constraint và preference

Một preference được xem như yêu cầu bắt buộc và loại bỏ phương án tốt. Phân loại rõ.

### Chỉ có một phương án

Không có so sánh thực sự. Tạo các lựa chọn khả thi, bao gồm giữ nguyên hiện trạng.

### Chấm điểm không có bằng chứng

Decision matrix tạo cảm giác khách quan nhưng dựa trên phỏng đoán. Ghi confidence và nguồn dữ liệu.

### Quá nhiều tiêu chí

Mọi thứ đều quan trọng nên không có ưu tiên. Chọn driver chính và guardrail.

### Bỏ qua chi phí vòng đời

Chỉ tính implementation effort. Đưa maintenance, migration, operations và support vào TCO.

### Tối ưu theo benchmark không đại diện

Phương án thắng trong microbenchmark nhưng thua workload thực. Dùng workload thực tế và macrobenchmark.

### Không ghi quyết định

Người sau không biết vì sao lựa chọn được đưa ra. Viết ADR ngắn, liên kết bằng chứng.

### Không có review trigger

Quyết định cũ tồn tại dù bối cảnh đã thay đổi. Ghi điều kiện xem xét lại.

## 26. Quy trình ra quyết định cho một thay đổi DSL

Một quy trình có thể áp dụng:

1. **Mô tả vấn đề.** Nêu người dùng, bối cảnh và kết quả mong muốn.
2. **Xác định constraints.** Platform, security, compatibility, cost và deadline.
3. **Chọn decision drivers.** Xác định vài quality attributes quan trọng nhất.
4. **Đặt tiêu chí đo.** Định nghĩa threshold hoặc evidence cần có.
5. **Tạo phương án.** Bao gồm giữ nguyên hiện trạng và phương án kết hợp.
6. **Loại phương án không khả thi.** Ghi lý do theo constraint.
7. **Đánh giá trade-off.** Dùng bảng so sánh và risk analysis.
8. **Kiểm chứng giả định.** Prototype, benchmark hoặc spike có timebox.
9. **Chọn phương án.** Nêu lý do và các đánh đổi được chấp nhận.
10. **Ghi ADR.** Lưu context, decision, consequence và owner.
11. **Triển khai và đo.** Theo dõi metrics, test và feedback.
12. **Xem xét lại.** Mở lại khi review trigger xuất hiện.

## 27. Ví dụ end-to-end: chọn parser cho DSL

Giả sử nhóm cần parser cho một DSL có:

- Grammar có expression lồng nhau.
- IDE cần diagnostics khi source chưa hoàn chỉnh.
- Project có nhiều file.
- Team có ba developer compiler.
- Cần giữ language version cũ trong vài năm.

### 27.1. Constraints

- Phải hỗ trợ error recovery.
- Phải có source range chính xác.
- Không được phụ thuộc runtime không hỗ trợ platform mục tiêu.

### 27.2. Decision drivers

- Developer feedback latency.
- Grammar maintainability.
- Error recovery.
- Incremental update.
- Team expertise.

### 27.3. Options

| Phương án | Điểm mạnh | Điểm yếu |
|---|---|---|
| Handwritten recursive descent | Kiểm soát cao, dễ tùy biến | Tốn effort khi grammar phát triển |
| Parser generator | Grammar rõ, generated parser nhất quán | Error recovery phụ thuộc công cụ |
| Incremental parser framework | Phù hợp editor và large file | Học framework và tích hợp query |

### 27.4. Prototype

Dùng corpus 100 file đại diện, đo:

- Parse latency cold/warm.
- Edit-to-diagnostics latency.
- Memory footprint.
- Khả năng recovery khi thiếu delimiter.
- Effort thêm một grammar feature.

### 27.5. Quyết định

Giả sử prototype cho thấy incremental parser framework đáp ứng latency và error recovery, nhóm có thể chọn nó cho editor parser, trong khi compiler batch vẫn dùng parser generated nếu semantics và grammar được chia sẻ qua specification.

### 27.6. Hệ quả

- Cần duy trì hai integration path.
- Cần conformance test để hai parser tạo cùng semantic model.
- Cần theo dõi version framework.
- Có thể giảm độ trễ editor trên file lớn.

ADR ghi lại lý do và review trigger, ví dụ khi grammar hoặc framework version thay đổi lớn.

## 28. Mẫu ADR

Một template đơn giản:

~~~markdown
# ADR-NNN: Decision title

## Status
Proposed | Accepted | Rejected | Superseded

## Context
What problem and constraints led to this decision?

## Decision drivers
Which quality attributes and constraints matter most?

## Options considered
What alternatives were evaluated?

## Decision
What option was selected and why?

## Consequences
What benefits, costs and risks follow?

## Evidence
Benchmarks, prototypes, tests or references.

## Review triggers
What future conditions should reopen this decision?
~~~

ADR nên ngắn đủ để đọc trong review nhưng có đủ thông tin để người khác hiểu quyết định sau này.

## 29. Kết luận

Khung ra quyết định giúp nhóm lựa chọn thiết kế DSL dựa trên bối cảnh, mục tiêu chất lượng, constraints, bằng chứng và rủi ro. Quy trình tốt bắt đầu từ vấn đề thực tế, phân biệt yêu cầu bắt buộc với preference, tạo các phương án khả thi, đánh giá trade-off và kiểm chứng giả định bằng prototype hoặc benchmark khi cần.

Decision matrix và risk analysis hỗ trợ so sánh nhưng không thay thế judgment. Các quyết định quan trọng nên được ghi trong ADR cùng hệ quả, owner và điều kiện xem xét lại. Sau khi triển khai, metrics và feedback cần được dùng để xác nhận giả định còn đúng.

Một khung ra quyết định hiệu quả không cố tìm một kiến trúc hoàn hảo cho mọi DSL. Nó giúp chọn phương án phù hợp nhất với người dùng, workload, nguồn lực và vòng đời cụ thể, đồng thời giữ lại lý do để nhóm có thể điều chỉnh khi bối cảnh thay đổi.
