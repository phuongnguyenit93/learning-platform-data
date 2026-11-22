# Tiêu chí lựa chọn công cụ

## 1. Vai trò của việc lựa chọn công cụ trong phát triển DSL

Khi xây dựng một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), nhóm phát triển cần chọn nhiều loại công cụ: parser generator, framework xây dựng ngôn ngữ, compiler infrastructure, runtime, IDE integration, language server, debugger, visualizer, hệ thống kiểm thử, đóng gói và phân phối. Những công cụ này tạo thành môi trường phát triển và vận hành DSL.

**Tiêu chí lựa chọn công cụ** là tập hợp yêu cầu và phương pháp dùng để đánh giá một công cụ có phù hợp với mục tiêu, kiến trúc, đội ngũ và vòng đời của DSL hay không. Việc lựa chọn không nên chỉ dựa vào mức độ phổ biến hoặc số lượng tính năng. Một công cụ tốt phải giải quyết đúng vấn đề của dự án, tích hợp được với hệ thống hiện tại, có chi phí vận hành chấp nhận được và có thể duy trì trong thời gian dài.

Ví dụ, một nhóm muốn xây dựng DSL mô tả workflow:

~~~text
workflow "monthly-report" {
    source "orders"
    filter status == "PAID"
    group by customer_id
    aggregate sum(amount)
    output "report.csv"
}
~~~

Nhóm có thể cần:

- Parser để đọc cú pháp.
- Framework hoặc thư viện AST để biểu diễn chương trình.
- Semantic analyzer để kiểm tra schema, kiểu và quy tắc miền.
- Runtime hoặc compiler backend để thực thi.
- Language server để hỗ trợ editor.
- Visualizer để hiển thị pipeline và dependency.
- Test framework để kiểm tra cú pháp, ngữ nghĩa và hành vi.
- Công cụ build và package để phát hành module, schema và runtime.

Không phải dự án nào cũng cần tự xây tất cả thành phần. Một framework có thể cung cấp parser, AST, validation và code generation; một workbench có thể tích hợp nhiều công cụ thành môi trường phát triển thống nhất. Nhiệm vụ của nhóm là xác định phần nào nên dùng sẵn, phần nào cần mở rộng và phần nào thực sự phải tự triển khai.

## 2. Phân biệt framework, library, tool và workbench

Các khái niệm thường được dùng gần nhau nhưng có phạm vi khác nhau.

### 2.1. Library

Library cung cấp API để ứng dụng gọi khi cần. Nhóm phát triển thường kiểm soát luồng chương trình và gọi thư viện tại các điểm thích hợp.

Ví dụ, một thư viện parser có thể cung cấp hàm parse chuỗi DSL thành AST. Ứng dụng tự quyết định lúc nào parse, cách lưu AST và cách chạy semantic analysis.

### 2.2. Framework

Framework cung cấp cấu trúc, quy ước và vòng đời để xây dựng một loại ứng dụng. Framework có thể gọi code do nhóm phát triển viết tại các extension point.

Ví dụ, language framework có thể định nghĩa cách khai báo grammar, scope, type system, validator và generator. Nhóm triển khai các phần đặc thù của DSL trong cấu trúc framework quy định.

### 2.3. Tool

Tool là công cụ thực hiện một nhiệm vụ cụ thể, ví dụ:

- Lexer hoặc parser generator.
- Formatter.
- Linter.
- Compiler.
- Debugger.
- Schema registry.
- Package manager.
- Benchmark tool.

Một tool có thể hoạt động độc lập hoặc được tích hợp vào framework/workbench.

### 2.4. Workbench

Workbench là môi trường tích hợp nhiều công cụ và dịch vụ để hỗ trợ một vòng đời công việc. Language workbench thường giúp định nghĩa ngôn ngữ, kiểm tra mô hình, sinh editor, tạo generator và quản lý artifact trong cùng một môi trường.

Workbench có thể bao gồm:

- Grammar hoặc language definition editor.
- Model/AST viewer.
- Scope và type system tooling.
- Generator và transformation pipeline.
- Editor support.
- Debugging và visualization.
- Build, test và packaging integration.

### 2.5. Không đồng nhất tên gọi với năng lực

Một sản phẩm tự gọi là framework không có nghĩa nó hỗ trợ mọi bước của compiler. Một workbench có thể mạnh về modeling và editor nhưng thiếu runtime phù hợp. Cần đánh giá theo năng lực thực tế, không chỉ theo nhãn sản phẩm.

## 3. Bắt đầu từ yêu cầu của DSL

Trước khi so sánh công cụ, cần hiểu ngôn ngữ sẽ phục vụ ai và giải quyết công việc gì.

### 3.1. Miền nghiệp vụ

Xác định DSL mô tả:

- Cấu hình hạ tầng.
- Workflow hoặc orchestration.
- Quy tắc nghiệp vụ.
- Truy vấn và xử lý dữ liệu.
- Mô hình giao diện.
- Giao thức hoặc state machine.
- Chính sách bảo mật.
- Một miền kỹ thuật khác.

Mỗi miền có kiểu cấu trúc và yêu cầu khác nhau. DSL workflow thường cần dependency graph và scheduler; DSL truy vấn cần schema resolution và query optimizer; DSL cấu hình cần validation, diff và quản lý version.

### 3.2. Người dùng mục tiêu

Xác định người viết DSL là developer, analyst, operator, chuyên gia nghiệp vụ hay người dùng không chuyên lập trình. Điều này ảnh hưởng:

- Độ phức tạp cú pháp.
- Khả năng đọc và thông báo lỗi.
- Nhu cầu editor trực quan.
- Mức kiểm soát được phép cho người dùng.
- Cách triển khai và phân quyền.

Một DSL dành cho developer có thể ưu tiên khả năng mở rộng và tích hợp IDE. DSL dành cho chuyên gia nghiệp vụ có thể cần form editor, validation dễ hiểu và guardrail chặt chẽ.

### 3.3. Quy mô và độ phức tạp

Ước lượng:

- Số lượng cú pháp và construct.
- Số lượng module hoặc file.
- Kích thước chương trình điển hình và lớn nhất.
- Số loại schema và dependency.
- Số backend hoặc runtime target.
- Tần suất thay đổi ngôn ngữ.
- Số người dùng và số lần thực thi.

Một parser nhỏ cho vài chục cấu hình không có cùng yêu cầu với compiler cho hàng triệu dòng DSL và nhiều backend.

### 3.4. Vòng đời

Xem xét toàn bộ vòng đời:

~~~text
Language Design
      |
      v
Authoring / Editing
      |
      v
Parsing and Validation
      |
      v
Compilation / Transformation
      |
      v
Packaging and Distribution
      |
      v
Execution
      |
      v
Debugging / Observability
      |
      v
Evolution and Migration
~~~

Không nên chọn công cụ chỉ tối ưu bước parser nếu các bước sau như migration, deployment và debugging mới là phần tốn chi phí lớn.

## 4. Functional fit: mức độ đáp ứng chức năng

Functional fit là mức độ công cụ hỗ trợ các công việc cần thiết của dự án.

### 4.1. Grammar và parsing

Đánh giá:

- Có hỗ trợ grammar phù hợp với cú pháp mong muốn không?
- Có xử lý precedence, associativity và ambiguity không?
- Có hỗ trợ left recursion hoặc grammar modular không?
- Có parser recovery để tiếp tục sau lỗi không?
- Có incremental parsing không?
- Có thể giữ source location và trivia phục vụ formatter không?
- Có thể tùy biến diagnostic không?

Nếu DSL cần cú pháp tự do và grammar phức tạp, parser generator hoặc language framework mạnh có thể phù hợp. Nếu cấu trúc đơn giản và ổn định, parser thư viện nhỏ có thể đủ.

### 4.2. AST, CST và mô hình dữ liệu

Kiểm tra công cụ có:

- Mô hình node có kiểu.
- Visitor hoặc pattern matching.
- Cơ chế giữ source span.
- Cấu trúc immutable hoặc API mutation rõ ràng.
- Serialization và versioning.
- Hỗ trợ metadata và annotation.
- Khả năng mở rộng node mới.

Nếu cần refactoring và formatter, CST hoặc concrete syntax preservation có thể quan trọng. Nếu chủ yếu biên dịch và tối ưu, AST/IR có kiểu có thể phù hợp hơn.

### 4.3. Semantic analysis

Đánh giá khả năng:

- Scope và name resolution.
- Symbol table.
- Type checking và type inference.
- Constraint validation.
- Cross-reference giữa module.
- Import và dependency resolution.
- Kiểm tra schema ngoài.
- Diagnostic liên tài liệu.

Với DSL có quy tắc nghiệp vụ phong phú, semantic analysis thường là phần quan trọng hơn cú pháp. Công cụ chỉ parse được văn bản nhưng không hỗ trợ tốt symbol và type system có thể khiến nhóm phải tự xây nhiều hạ tầng.

### 4.4. Transformation và code generation

Kiểm tra:

- Có AST transformation hoặc IR pass không?
- Có quản lý nhiều tầng IR không?
- Có source mapping và provenance không?
- Có hỗ trợ nhiều backend không?
- Có kiểm soát side effect và type trong generator không?
- Có thể kiểm tra tính đúng của transformation không?
- Có thể mở rộng instruction hoặc target không?

Nếu DSL cần sinh SQL, Java, bytecode hoặc workflow plan, khả năng backend và kiểm soát semantics cần được đánh giá sớm.

### 4.5. Runtime

Nếu DSL được thông dịch hoặc thực thi qua VM, xem xét:

- Execution model.
- Quản lý state và resource.
- Concurrency và cancellation.
- Exception handling.
- Sandboxing.
- Quota và timeout.
- Observability.
- Compatibility giữa runtime và artifact.

Một framework tập trung vào language authoring có thể không cung cấp runtime production-ready. Cần xác định rõ runtime thuộc sản phẩm nào và nhóm sẽ phải tự xây phần gì.

### 4.6. Developer experience

Đánh giá:

- Syntax highlighting.
- Completion.
- Hover và documentation.
- Go to definition và find references.
- Rename.
- Formatting.
- Diagnostics thời gian thực.
- Code actions.
- Debugging.
- Visualizer.

Đây là yếu tố quan trọng nếu DSL được sử dụng thường xuyên. Một ngôn ngữ có cú pháp tốt nhưng thiếu tooling có thể gây chi phí sử dụng cao.

## 5. Độ phù hợp với kiến trúc hiện tại

Một công cụ có nhiều tính năng nhưng khó tích hợp có thể tạo chi phí lớn hơn lợi ích.

### 5.1. Ngôn ngữ và runtime nền

Xem công cụ hỗ trợ ngôn ngữ lập trình, phiên bản runtime và nền tảng mà dự án đang sử dụng. Ví dụ, nhóm có hệ thống Java có thể ưu tiên thư viện JVM, nhưng vẫn cần đánh giá khả năng gọi từ các thành phần khác.

### 5.2. Build system

Kiểm tra tích hợp với Gradle, Maven, Bazel, npm hoặc hệ thống build hiện có:

- Dependency declaration.
- Plugin và task.
- Incremental build.
- Cache.
- Reproducibility.
- CI integration.

Nếu phải tạo một quy trình build riêng hoàn toàn, cần tính chi phí bảo trì.

### 5.3. Editor và IDE

Đánh giá công cụ hỗ trợ VS Code, IntelliJ IDEA, Eclipse, web editor hoặc IDE nội bộ. Nếu dùng LSP, xem mức hỗ trợ và khả năng tích hợp với client mục tiêu.

### 5.4. Storage và repository

DSL có thể lưu source trong Git, schema registry, object storage hoặc database. Công cụ nên tích hợp được với hệ thống quản lý version, artifact repository và quyền truy cập hiện có.

### 5.5. Hệ thống bên ngoài

Kiểm tra API và connector cho:

- Database.
- Cloud platform.
- Workflow engine.
- Message broker.
- Authentication provider.
- Monitoring.
- Package repository.

Không nên chọn công cụ chỉ vì có connector quảng cáo nếu connector đó không hỗ trợ authentication, retry, version hoặc vận hành thực tế cần thiết.

### 5.6. Deployment model

Xác định công cụ cần chạy:

- Trên máy developer.
- Trong CI.
- Trong server tập trung.
- Trong container.
- Trên cloud.
- Trong môi trường offline hoặc mạng hạn chế.

Deployment model ảnh hưởng license, bảo mật, cập nhật, hiệu năng và hỗ trợ.

## 6. Khả năng mở rộng và tùy biến

DSL thường phát triển theo nhu cầu miền. Công cụ cần cho phép mở rộng mà không buộc nhóm phải fork toàn bộ framework.

### 6.1. Extension points

Tìm hiểu cách thêm:

- Grammar rule.
- AST node.
- Type hoặc domain type.
- Validator.
- Transformation pass.
- Generator/backend.
- Runtime function.
- Editor feature.
- Plugin.

API extension cần ổn định và có tài liệu. Nếu chỉ có thể sửa source nội bộ hoặc phụ thuộc vào class không public, chi phí nâng cấp có thể cao.

### 6.2. Plugin architecture

Plugin cho phép thêm tính năng độc lập. Cần đánh giá:

- Cách đăng ký và khám phá plugin.
- Version compatibility.
- Isolation và permissions.
- Dependency conflict.
- Lifecycle và error handling.
- API stability.

Plugin có thể tăng khả năng mở rộng nhưng cũng tăng bề mặt bảo mật và độ phức tạp vận hành.

### 6.3. Customization

Một framework có thể cho phép thay đổi diagnostic, syntax convention, code generation template, editor UI hoặc runtime policy. Cần phân biệt customization được hỗ trợ chính thức với việc sửa trực tiếp implementation.

### 6.4. Forkability

Fork source code có thể cần thiết trong một số tình huống, nhưng cần đánh giá khả năng duy trì fork, nhận security update và merge upstream. Fork không nên là lựa chọn mặc định chỉ để thay đổi một hành vi có thể mở rộng qua API.

### 6.5. Extensibility so với complexity

Một framework quá linh hoạt có thể khó học và khó cấu hình. Chỉ chọn mức mở rộng mà dự án có khả năng sử dụng và duy trì.

## 7. Hiệu năng và khả năng mở rộng quy mô

Hiệu năng cần được đo trên workload thực tế thay vì dựa vào benchmark quảng bá.

### 7.1. Parsing performance

Đo thời gian parse theo:

- File nhỏ và lớn.
- Grammar đơn giản và phức tạp.
- Tài liệu lỗi cú pháp.
- Incremental edit.
- Workspace nhiều file.

### 7.2. Semantic analysis

Name resolution, type inference và validation có thể tốn nhiều thời gian hơn parsing. Đo hiệu năng khi có nhiều module, schema và dependency.

### 7.3. Incremental behavior

Khi sửa một biểu thức nhỏ, công cụ có thể phân tích lại toàn bộ project hay chỉ phần phụ thuộc? Đo thời gian cập nhật và tính đúng của invalidation.

### 7.4. Memory usage

AST, symbol table, IR, cache và graph visualization có thể chiếm nhiều bộ nhớ. Đo mức dùng bộ nhớ khi mở nhiều file và chạy nhiều compilation song song.

### 7.5. Throughput

Với compiler service hoặc CI, đo số compilation mỗi phút, số request đồng thời và khả năng xử lý khi tải tăng.

### 7.6. Cold start và warm start

Phân biệt thời gian khởi động lần đầu với thời gian sau khi cache và runtime đã sẵn sàng. Với CLI chạy thường xuyên, cold start có thể ảnh hưởng đáng kể.

### 7.7. Scalability

Xem hiệu năng khi tăng:

- Số dòng DSL.
- Số module.
- Số dependency.
- Số user/session.
- Số task thực thi.
- Số backend hoặc target.

Một công cụ nhanh ở dự án nhỏ có thể không đáp ứng khi workspace lớn.

## 8. Chất lượng diagnostics và khả năng gỡ lỗi

Lỗi của DSL cần được giải thích ở ngôn ngữ người dùng hiểu được.

### 8.1. Source mapping

Parser, analyzer và generator cần giữ liên kết từ node nội bộ về source span. Nếu công cụ làm mất vị trí nguồn sau transformation, debugging sẽ khó hơn.

### 8.2. Error recovery

Trong editor, parser nên tiếp tục phân tích phần còn lại sau lỗi cú pháp để không chỉ hiển thị một lỗi duy nhất ở đầu file.

### 8.3. Diagnostic customization

Có thể thay đổi code, severity, message, related information và quick fix hay không? Diagnostic code có ổn định giữa các phiên bản không?

### 8.4. Debugger

Nếu DSL có runtime, đánh giá khả năng:

- Breakpoint ở source DSL.
- Step over/into/out.
- Inspect variable.
- Call stack hoặc task stack.
- Exception mapping.
- Debug async hoặc concurrent task.
- Replay hoặc trace.

### 8.5. Explain và visualizer

Với DSL workflow hoặc query, explain plan và visualizer có thể quan trọng hơn debugger từng dòng. Cần chọn theo cách người dùng hiểu và vận hành chương trình.

### 8.6. Diagnostic quality as acceptance criterion

Trong proof of concept, hãy cố ý tạo lỗi cú pháp, lỗi kiểu, lỗi schema và lỗi dependency. Đánh giá người dùng có thể xác định nguyên nhân và vị trí sửa mà không cần đọc source code framework hay không.

## 9. Khả năng tương thích và tiến hóa ngôn ngữ

DSL có thể tồn tại lâu hơn phiên bản framework ban đầu. Cần đánh giá công cụ có hỗ trợ evolution không.

### 9.1. Grammar evolution

Thêm cú pháp mới có làm thay đổi cách parse chương trình cũ không? Công cụ có hỗ trợ versioned grammar hoặc feature flag không?

### 9.2. Schema evolution

Field, type hoặc constraint có thể thay đổi. Công cụ có hỗ trợ migration, compatibility checking và diagnostic cho schema cũ không?

### 9.3. Artifact compatibility

Nếu bytecode hoặc IR được lưu lâu dài, runtime mới có đọc được artifact cũ không? Có format version và migration path không?

### 9.4. Backward và forward compatibility

- Backward compatibility: phiên bản mới có thể đọc hoặc xử lý artifact cũ theo hợp đồng.
- Forward compatibility: phiên bản cũ có thể bỏ qua hoặc xử lý có kiểm soát một số nội dung mới, nếu định dạng cho phép.

Không phải mọi định dạng đều hỗ trợ cả hai. Cần xác định chính sách rõ.

### 9.5. Deprecation

Công cụ nên hỗ trợ cảnh báo cú pháp hoặc API sắp bị loại bỏ, hướng dẫn thay thế và thời gian chuyển đổi.

### 9.6. Migration tooling

Khi DSL thay đổi, có thể cần codemod hoặc migration tool để chuyển source cũ. Đánh giá khả năng tạo AST transformation, giữ comment và source formatting.

## 10. Độ trưởng thành và độ tin cậy của hệ sinh thái

Một công cụ dùng trong production cần được duy trì và có cộng đồng hoặc nhà cung cấp đủ năng lực hỗ trợ.

### 10.1. Hoạt động phát triển

Xem:

- Tần suất release.
- Thời gian xử lý issue.
- Lịch sử sửa lỗi.
- Security advisory.
- Tương thích với phiên bản runtime mới.
- Chính sách hỗ trợ phiên bản cũ.

Commit gần đây không tự chứng minh chất lượng; cần xem nội dung và mức ổn định của các release.

### 10.2. Tài liệu

Tài liệu cần có:

- Quick start.
- API reference.
- Tutorial.
- Ví dụ hoàn chỉnh.
- Migration guide.
- Troubleshooting.
- Security guidance.
- Best practices.

Tài liệu tốt giúp giảm phụ thuộc vào một vài thành viên hiểu sâu framework.

### 10.3. Community và support

Đánh giá cộng đồng, diễn đàn, issue tracker, mailing list, commercial support và khả năng nhận trợ giúp khi gặp lỗi nghiêm trọng.

### 10.4. Ecosystem

Kiểm tra plugin, extension, integration, sample project và công cụ liên quan. Hệ sinh thái rộng có thể giảm công sức tự xây, nhưng số lượng package không quan trọng bằng chất lượng và khả năng tương thích.

### 10.5. Bus factor

Nếu chỉ một cá nhân hiểu cách cấu hình hoặc mở rộng công cụ, dự án có rủi ro phụ thuộc nhân sự. Đánh giá khả năng onboarding và mức độ dễ chuyển giao.

## 11. License và tổng chi phí sở hữu

Giá mua hoặc phí subscription chỉ là một phần chi phí.

### 11.1. License

Kiểm tra:

- License mã nguồn mở hoặc thương mại.
- Quyền sử dụng trong sản phẩm thương mại.
- Quyền phân phối runtime hoặc generated code.
- Điều kiện copyleft.
- Giới hạn số developer, server hoặc deployment.
- Điều khoản sử dụng cloud-hosted service.
- Quyền sửa đổi và phân phối fork.

Không nên kết luận license phù hợp chỉ dựa vào tên license; cần đọc điều khoản và chính sách pháp lý của tổ chức.

### 11.2. Total Cost of Ownership (TCO)

TCO có thể bao gồm:

- License hoặc subscription.
- Hạ tầng chạy công cụ.
- Thời gian tích hợp.
- Thời gian đào tạo.
- Phát triển plugin hoặc extension.
- Bảo trì custom code.
- Chi phí nâng cấp.
- Chi phí hỗ trợ.
- Chi phí chuyển đổi nếu thay công cụ.

Một công cụ miễn phí có thể có TCO cao nếu cần nhiều code tùy chỉnh và chuyên gia hiếm. Một sản phẩm thương mại có thể tiết kiệm thời gian nếu giảm đáng kể công sức xây dựng tooling.

### 11.3. Chi phí theo quy mô

Một số sản phẩm tính phí theo developer, project, build minute, request hoặc resource. Cần mô phỏng chi phí ở quy mô dự kiến, không chỉ giá ở gói thử nghiệm.

### 11.4. Exit cost

Nếu sau vài năm phải chuyển công cụ, dữ liệu, grammar, model và plugin có thể xuất được không? Có định dạng mở hoặc API để giảm lock-in không?

## 12. Bảo mật và quản trị

DSL có thể mô tả thao tác nhạy cảm hoặc được thực thi trong môi trường có quyền truy cập dữ liệu thật. Công cụ phát triển và runtime cần đáp ứng yêu cầu bảo mật tương ứng.

### 12.1. Supply chain

Kiểm tra nguồn dependency, chữ ký package, checksum, provenance và quy trình cập nhật plugin.

### 12.2. Sandboxing

Nếu DSL cho phép extension hoặc function do người dùng định nghĩa, xem khả năng sandbox và giới hạn quyền. Không nên giả định compiler framework tự động tạo môi trường thực thi an toàn.

### 12.3. Authentication và authorization

Workbench hoặc server tập trung có thể cần SSO, role-based access control, audit log và quản lý secret.

### 12.4. Data handling

Xác định nội dung DSL, schema và diagnostic có thể chứa secret hoặc thông tin nhạy cảm. Kiểm tra dữ liệu được gửi đến cloud service, telemetry hoặc vendor support như thế nào.

### 12.5. Vulnerability response

Nhà cung cấp hoặc dự án mã nguồn mở có quy trình công bố lỗ hổng, release bản vá và thông báo ảnh hưởng hay không?

### 12.6. Compliance

Nếu tổ chức có yêu cầu về lưu trữ dữ liệu, audit, residency hoặc kiểm soát truy cập, công cụ phải đáp ứng chính sách đó. Không nên giả định một chứng nhận chung tự động bao phủ mọi cách triển khai.

## 13. Portability và vendor lock-in

Một công cụ có thể gắn chặt với định dạng, runtime hoặc nền tảng riêng.

### 13.1. Open standards

Ưu tiên định dạng hoặc giao thức có đặc tả rõ và được nhiều implementation hỗ trợ khi phù hợp, ví dụ LSP cho editor integration hoặc định dạng serialization phổ biến.

### 13.2. Export và import

Đánh giá có thể xuất:

- Grammar.
- AST hoặc model.
- Schema.
- IR.
- Generated source.
- Package metadata.
- Diagnostics.
- Visualization model.

Khả năng export không chỉ là tải file; cần xem dữ liệu có thể được sử dụng độc lập trong công cụ khác không.

### 13.3. Backend portability

Nếu DSL cần chạy trên nhiều runtime, framework có hỗ trợ nhiều backend hoặc abstraction phù hợp không? Cần xác định semantics có nhất quán giữa backend hay không.

### 13.4. Proprietary extension

Một số tính năng chỉ có trong phiên bản thương mại hoặc định dạng riêng. Ghi rõ tính năng nào tạo lock-in và tác động nếu hợp đồng hoặc sản phẩm thay đổi.

### 13.5. Portability có chi phí

Không phải mọi dự án đều cần đa nền tảng. Tạo abstraction để hỗ trợ nhiều backend có thể làm tăng độ phức tạp. Chỉ đầu tư khi có nhu cầu thực tế hoặc rủi ro phụ thuộc đủ lớn.

## 14. Khả năng sử dụng và đường cong học tập

Tooling tốt cần phù hợp năng lực của nhóm phát triển và người dùng DSL.

### 14.1. Learning curve

Đánh giá thời gian để một developer:

- Cài đặt môi trường.
- Tạo DSL tối thiểu.
- Thêm grammar rule.
- Thêm validator.
- Debug một lỗi.
- Tạo backend hoặc plugin.
- Phát hành phiên bản.

### 14.2. Conceptual complexity

Một framework có thể dùng nhiều khái niệm như metamodel, generator, transformation language, scope provider và workflow. Nếu nhóm không có kinh nghiệm, cần tính chi phí đào tạo.

### 14.3. Documentation by example

Ví dụ thực tế có thể rút ngắn thời gian học. Tuy nhiên, cần kiểm tra ví dụ còn tương thích với phiên bản hiện tại và có giải thích giới hạn.

### 14.4. Developer feedback

Cho người dùng mục tiêu thử một tác vụ thật. Quan sát họ có hiểu lỗi, tìm tài liệu và hoàn thành công việc mà không cần trợ giúp liên tục hay không.

### 14.5. Operational usability

Không chỉ developer mới dùng công cụ. Operator cần đọc được log, plan, diagnostic và trạng thái runtime. Giao diện vận hành cũng cần được đánh giá.

## 15. Khả năng kiểm thử và tự động hóa

Tooling DSL cần hoạt động ổn định trong CI và môi trường phát triển.

### 15.1. Test integration

Kiểm tra có thể tích hợp với unit test, integration test, snapshot test, property-based test và test runner hiện có không.

### 15.2. Golden files

Parser hoặc generator có thể được kiểm thử bằng input và output mong đợi. Công cụ cần hỗ trợ output ổn định hoặc canonicalization để golden diff có ý nghĩa.

### 15.3. Property-based testing

Nếu có thể sinh chương trình DSL ngẫu nhiên, kiểm tra parser không crash, serializer round trip và transformation bảo toàn invariant.

### 15.4. Fuzzing

Fuzzing giúp tìm crash hoặc input gây tiêu thụ tài nguyên bất thường trong parser, deserializer và runtime. Xem framework có hỗ trợ fuzz target hoặc dễ tích hợp với công cụ fuzzing không.

### 15.5. CI support

Kiểm tra:

- Headless mode.
- Exit code có ý nghĩa.
- Diagnostic output có thể máy đọc.
- Reproducible build.
- Cache.
- Parallel execution.
- Artifact publishing.

### 15.6. Testability của plugin

Extension point nên có thể kiểm thử độc lập. Plugin không nên bắt buộc khởi chạy toàn bộ IDE hoặc workbench để kiểm tra logic cốt lõi.

## 16. Tiêu chí riêng khi chọn parser generator

Parser generator là công cụ tạo parser từ grammar. Các tiêu chí cần xem:

- Loại parser được sinh: LL, LR, PEG hoặc parser khác.
- Hỗ trợ grammar ambiguity và precedence.
- Khả năng error recovery.
- Tạo source code cho ngôn ngữ mục tiêu.
- Tốc độ parse và kích thước parser.
- Incremental parsing.
- Hỗ trợ lexical modes và contextual keywords.
- Source location và Unicode.
- Tài liệu và công cụ debug grammar.
- License và khả năng duy trì.

Một grammar generator dễ dùng nhưng error recovery yếu có thể gây trải nghiệm editor kém. Ngược lại, parser generator mạnh nhưng yêu cầu kiến thức phức tạp có thể không phù hợp DSL nhỏ.

## 17. Tiêu chí riêng khi chọn language framework hoặc workbench

Language framework/workbench thường bao phủ nhiều bước, vì vậy cần đánh giá độ liền mạch giữa các thành phần.

### 17.1. Language definition

Có thể mô tả grammar, type, scope và constraint ở cùng một mô hình không? Có hỗ trợ modular language definition không?

### 17.2. Generated tooling

Workbench có tự sinh editor, outline, completion, validation hoặc visualizer không? Generated code có thể tùy chỉnh mà không bị ghi đè khi regenerate không?

### 17.3. Model transformation

Có transformation language, generator template hoặc pipeline quản lý dependency không? Có thể debug transformation không?

### 17.4. Runtime integration

Workbench có cung cấp runtime hay chỉ tạo code? Runtime có phù hợp deployment target và security policy không?

### 17.5. Team workflow

Có hỗ trợ collaboration, version control, review và merge language definition không? Model hoặc project có thể diff trong Git không?

### 17.6. Generated artifact ownership

Phân biệt file do generator quản lý với file developer chỉnh sửa. Nếu regenerate làm mất thay đổi thủ công, cần extension point hoặc vùng tùy chỉnh được bảo vệ.

### 17.7. Escape hatch

Khi framework không hỗ trợ một trường hợp đặc thù, nhóm có thể gọi API thấp hơn hoặc viết extension bằng ngôn ngữ thông thường không? Escape hatch giúp xử lý ngoại lệ nhưng không nên trở thành cách triển khai mọi tính năng.

## 18. Tiêu chí riêng khi chọn IDE và language server

Nếu DSL cần trải nghiệm authoring tốt, đánh giá:

- LSP compatibility và capability coverage.
- Completion chính xác theo scope và type.
- Diagnostics có source range đúng.
- Rename và references.
- Formatting và code actions.
- Semantic tokens và syntax highlighting.
- Workspace symbol và navigation.
- Incremental updates.
- Multi-root workspace.
- Cancellation và performance.
- Debug adapter nếu cần.
- Extension API và packaging.

### 18.1. LSP portability

LSP giúp language server phục vụ nhiều editor, nhưng không bảo đảm mọi client hỗ trợ mọi capability. Cần thử trên các client mà người dùng thực tế sử dụng.

### 18.2. Client-specific features

Một số tính năng như custom visualization, interactive debugger hoặc specialized refactoring có thể cần extension riêng cho IDE. Cần cân bằng giữa khả năng đa editor và trải nghiệm tích hợp sâu.

### 18.3. Offline và remote development

Nếu developer làm việc trong môi trường remote container hoặc offline, language server và dependency của nó cần chạy phù hợp với môi trường đó.

## 19. Ma trận đánh giá có trọng số

Khi có nhiều ứng viên, có thể dùng ma trận để so sánh có hệ thống.

### 19.1. Xác định tiêu chí và trọng số

Ví dụ:

| Tiêu chí | Trọng số |
|---|---:|
| Functional fit | 20% |
| Integration | 15% |
| Extensibility | 12% |
| Performance | 12% |
| Diagnostics and debugging | 10% |
| Ecosystem and support | 8% |
| Security | 8% |
| Compatibility and evolution | 7% |
| TCO and licensing | 5% |
| Learning curve | 3% |
| **Tổng** | **100%** |

Trọng số chỉ là ví dụ. Dự án có yêu cầu bảo mật cao có thể tăng trọng số security; dự án cần nhiều backend có thể tăng portability và extensibility.

### 19.2. Thang điểm

Có thể dùng thang 1 đến 5:

| Điểm | Diễn giải |
|---:|---|
| 1 | Không đáp ứng hoặc cần tự xây gần như toàn bộ |
| 2 | Đáp ứng một phần, có nhiều giới hạn |
| 3 | Đáp ứng yêu cầu cơ bản |
| 4 | Đáp ứng tốt, có ít hạn chế |
| 5 | Đáp ứng rất tốt và có bằng chứng phù hợp |

### 19.3. Tính điểm tổng

Điểm tổng có trọng số:

\[
Score = \sum_{i=1}^{n} Weight_i \times Rating_i
\]

Nếu weight được biểu diễn dạng phần trăm, cần chuẩn hóa về tổng bằng 1 hoặc chia kết quả cho 100.

Ví dụ:

| Tiêu chí | Weight | Tool A | Tool B |
|---|---:|---:|---:|
| Functional fit | 0.30 | 5 | 4 |
| Integration | 0.25 | 3 | 5 |
| Extensibility | 0.20 | 5 | 3 |
| TCO | 0.15 | 3 | 4 |
| Learning curve | 0.10 | 2 | 4 |
| **Tổng** | **1.00** | **3.95** | **4.05** |

Điểm số giúp so sánh có cấu trúc, nhưng không thay thế phân tích. Một tiêu chí bắt buộc không được đáp ứng có thể loại ứng viên dù tổng điểm cao.

### 19.4. Must-have và nice-to-have

Phân loại yêu cầu:

- Must-have: không đáp ứng thì không thể dùng.
- Should-have: quan trọng nhưng có thể có phương án bù.
- Nice-to-have: tăng tiện ích nhưng không quyết định.

Nên dùng must-have như điều kiện lọc trước khi tính điểm.

### 19.5. Ghi độ tin cậy của điểm

Mỗi điểm nên kèm bằng chứng và mức tin cậy:

- Đã xác nhận bằng prototype.
- Đã xác nhận qua tài liệu chính thức.
- Được vendor xác nhận nhưng chưa thử.
- Chưa rõ.

Điểm 5 dựa trên quảng cáo không tương đương điểm 5 đã kiểm chứng trong workload thực tế.

## 20. Proof of concept (PoC) để xác minh lựa chọn

PoC là cách kiểm tra ứng viên bằng một lát cắt thực tế của DSL trước khi cam kết dài hạn.

### 20.1. Chọn use case đại diện

PoC nên có:

- Cú pháp cơ bản.
- Một số cấu trúc lồng nhau.
- Name resolution.
- Kiểm tra kiểu.
- Một quy tắc miền.
- Một transformation hoặc code generation.
- Một lỗi cần diagnostic.
- Một tình huống editor.
- Một bài test CI.

Không nên chỉ chọn ví dụ đơn giản nhất vì nó có thể không bộc lộ giới hạn của công cụ.

### 20.2. Xác định tiêu chí đo

Ví dụ:

- Thời gian triển khai grammar đầu tiên.
- Thời gian thêm một rule semantic.
- Độ chính xác source mapping.
- Thời gian parse file lớn.
- Độ trễ diagnostics sau edit.
- Khả năng debug generator.
- Số dòng custom code.
- Thời gian build.
- Mức sử dụng memory.

### 20.3. Kiểm tra failure path

Thử cú pháp lỗi, schema thiếu, dependency không tồn tại, runtime exception và input lớn bất thường. Công cụ tốt cần giúp phát hiện và chẩn đoán thất bại, không chỉ chạy được happy path.

### 20.4. Đánh giá khả năng thay đổi

Sau khi PoC hoạt động, thử thay grammar, thêm type, đổi backend hoặc nâng version framework. Nhiều chi phí chỉ xuất hiện khi ngôn ngữ tiến hóa.

### 20.5. PoC không phải production proof

PoC xác minh tính khả thi và các rủi ro chính. Trước khi production, vẫn cần kiểm tra bảo mật, tải, vận hành, backup, migration, support và quy trình phát hành.

## 21. So sánh build-versus-buy

Nhóm có thể tự xây tooling, dùng open-source framework hoặc mua sản phẩm thương mại.

### 21.1. Tự xây

Phù hợp khi:

- DSL nhỏ và phạm vi rõ.
- Yêu cầu đặc thù không được công cụ sẵn có hỗ trợ.
- Nhóm có năng lực compiler phù hợp.
- Muốn kiểm soát toàn bộ kiến trúc.

Chi phí:

- Phải xây và duy trì parser, diagnostics, tooling.
- Cần tự xử lý bug, performance và compatibility.
- Có nguy cơ phụ thuộc vào một vài người.

### 21.2. Dùng framework mã nguồn mở

Phù hợp khi:

- Có năng lực cốt lõi gần với framework.
- API và license phù hợp.
- Có thể mở rộng mà không fork sâu.
- Cộng đồng hoặc dự án có mức duy trì đủ tin cậy.

Chi phí:

- Học mô hình framework.
- Theo dõi thay đổi upstream.
- Tích hợp và xử lý giới hạn.
- Có thể cần đóng góp hoặc duy trì fork.

### 21.3. Dùng sản phẩm thương mại

Phù hợp khi:

- Cần tooling tích hợp và support.
- Thời gian đưa sản phẩm ra thị trường quan trọng.
- Chi phí license thấp hơn chi phí tự xây và vận hành.
- Điều khoản bảo mật và deployment đáp ứng yêu cầu.

Rủi ro:

- Vendor lock-in.
- Giá thay đổi.
- Giới hạn customization.
- Phụ thuộc roadmap và support của nhà cung cấp.

### 21.4. Hybrid

Một lựa chọn phổ biến là dùng parser/framework mã nguồn mở, tự xây semantic model đặc thù, dùng LSP cho editor và dùng runtime riêng. Hybrid giúp tái sử dụng hạ tầng nhưng cần quản lý ranh giới giữa các thành phần.

## 22. Quản lý rủi ro phụ thuộc công cụ

Sau khi chọn công cụ, cần quản lý rủi ro trong suốt vòng đời.

### 22.1. Version pinning

Pin phiên bản dependency để build tái lập. Nâng cấp có kiểm soát thay vì tự động lấy phiên bản mới nhất.

### 22.2. Upgrade policy

Quy định:

- Tần suất xem xét release.
- Cách đánh giá breaking change.
- Kiểm thử trước nâng cấp.
- Thời gian hỗ trợ phiên bản cũ.
- Quy trình rollback.

### 22.3. Dependency inventory

Ghi danh sách framework, plugin, transitive dependency, license và phiên bản. Đây là cơ sở cho security response và migration.

### 22.4. Adapter boundary

Đặt adapter giữa mô hình miền của DSL và API framework. Nếu framework thay đổi, adapter có thể cô lập phần cần sửa.

### 22.5. Exportable artifacts

Giữ grammar, schema, test fixture, generated source và package metadata trong định dạng có thể quản lý bằng version control. Tránh chỉ lưu trong database hoặc định dạng độc quyền không thể xuất.

### 22.6. Exit plan

Ghi lại phần nào phụ thuộc đặc thù công cụ và cách thay thế nếu phải chuyển đổi. Không cần xây sẵn toàn bộ đường di chuyển, nhưng cần biết dữ liệu và logic nào có nguy cơ bị khóa.

## 23. Ví dụ lựa chọn công cụ cho ba loại DSL

### 23.1. DSL cấu hình nhỏ

Đặc điểm:

- Cú pháp đơn giản.
- Ít loại dữ liệu.
- Không cần runtime phức tạp.
- Người dùng cần diagnostics và validation.

Ưu tiên:

- Parser đơn giản, dễ bảo trì.
- Schema validation.
- Formatter.
- CLI và CI integration.
- Error messages rõ.

Một language workbench lớn có thể quá nặng nếu dự án chỉ cần đọc YAML-like syntax và xác thực vài quy tắc.

### 23.2. DSL workflow

Đặc điểm:

- Task và dependency.
- Concurrency.
- Retry, timeout và cancellation.
- Runtime observability.
- Visualization.

Ưu tiên:

- DAG model và validation chu trình.
- Scheduler/runtime hoặc integration với workflow engine.
- Task lifecycle và error handling.
- Timeline và dependency visualizer.
- Quản lý secret và quyền thực thi.
- Versioning và migration.

Parser không phải rủi ro duy nhất; semantics runtime và vận hành có thể quyết định thành công.

### 23.3. DSL truy vấn dữ liệu

Đặc điểm:

- Schema resolution.
- Expression type checking.
- Query optimization.
- Nhiều backend.
- Execution plan.

Ưu tiên:

- Typed AST/IR.
- Query planner hoặc optimizer.
- Predicate pushdown và projection pruning.
- Backend compatibility.
- Explain plan và metrics.
- Kiểm thử tương đương kết quả giữa backend.

Một parser generator tốt nhưng thiếu mô hình biểu thức có kiểu và optimizer có thể chưa đủ.

## 24. Bảng checklist đánh giá ứng viên

Bảng dưới đây có thể dùng trong buổi đánh giá hoặc PoC. Không phải mọi mục đều bắt buộc cho mọi dự án.

| Nhóm | Câu hỏi đánh giá |
|---|---|
| Domain fit | Công cụ có hỗ trợ construct và workflow đặc thù của DSL không? |
| Grammar | Có hỗ trợ grammar, precedence, recovery và incremental parsing không? |
| Semantic | Có scope, symbol, type và validation phù hợp không? |
| Transformation | Có AST/IR pass, source mapping và generator không? |
| Runtime | Có execution model, resource control, cancellation và sandbox không? |
| IDE | Có completion, diagnostics, navigation, formatting và code action không? |
| Visualization | Có tree, graph, plan hoặc timeline view cần thiết không? |
| Integration | Có phù hợp ngôn ngữ, build, storage, CI và deployment hiện tại không? |
| Extensibility | Có extension point ổn định và plugin isolation không? |
| Performance | Đáp ứng file, workspace, throughput và memory mục tiêu không? |
| Evolution | Có versioning, deprecation, migration và compatibility policy không? |
| Reliability | Release, bug fix, documentation và support có đáng tin không? |
| Security | Có đáp ứng supply chain, access control, sandbox và data policy không? |
| License | Điều khoản sử dụng và phân phối có phù hợp không? |
| TCO | Tổng chi phí triển khai, đào tạo, nâng cấp và vận hành là bao nhiêu? |
| Portability | Có thể export artifact và chuyển backend/tool khi cần không? |
| Usability | Người dùng mục tiêu có học và hoàn thành công việc được không? |
| Testability | Có thể tự động hóa test, CI, fuzzing và reproducible build không? |

## 25. Quy trình ra quyết định

Một quy trình lựa chọn công cụ có thể triển khai theo các bước:

1. **Thu thập yêu cầu.** Xác định miền, người dùng, quy mô, backend và vòng đời DSL.
2. **Phân loại công việc.** Tách nhu cầu parser, semantic analysis, runtime, IDE, visualization, packaging và operations.
3. **Đặt must-have.** Loại các công cụ không đáp ứng yêu cầu bắt buộc.
4. **Lập danh sách ứng viên.** Gồm tự xây, framework mã nguồn mở, sản phẩm thương mại và phương án hybrid.
5. **Kiểm tra bằng chứng.** Đọc tài liệu, release history, license, support và security policy.
6. **Đánh giá kiến trúc.** Xem integration, extension points, portability và vendor lock-in.
7. **Tạo ma trận có trọng số.** Ghi điểm, bằng chứng và độ tin cậy.
8. **Thực hiện PoC.** Dùng một use case đại diện có cả happy path và failure path.
9. **Đo hiệu năng.** Dùng workload và môi trường gần thực tế.
10. **Ước lượng TCO.** Tính license, engineering, training, operation và exit cost.
11. **Đánh giá rủi ro.** Xác định phụ thuộc, security, compatibility và khả năng nâng cấp.
12. **Ghi quyết định.** Nêu lý do chọn, lý do loại ứng viên khác, giả định và điều kiện cần xem xét lại.
13. **Lập kế hoạch adoption.** Xác định cách tích hợp, đào tạo, version pinning và migration.

Quyết định nên có ngày xem xét lại hoặc trigger cụ thể, ví dụ khi quy mô DSL tăng, cần backend mới, framework ngừng hỗ trợ hoặc chi phí vận hành vượt ngưỡng.

## 26. Những sai lầm thường gặp

### 26.1. Chọn theo độ phổ biến

Công cụ phổ biến có thể có cộng đồng lớn nhưng không phù hợp semantics hoặc deployment của DSL. Đánh giá bằng yêu cầu thực tế.

### 26.2. Chỉ xem demo happy path

Demo đơn giản không bộc lộ parser recovery, error diagnostics, incremental behavior, migration và lỗi runtime. PoC cần bao phủ cả tình huống thất bại.

### 26.3. Chỉ so sánh số lượng tính năng

Tính năng có thể tồn tại nhưng chất lượng, độ ổn định hoặc khả năng tích hợp không đủ. Kiểm tra cách dùng và bằng chứng vận hành.

### 26.4. Bỏ qua chi phí bảo trì

Custom extension, fork và plugin cần người duy trì. Tính chi phí nâng cấp và hỗ trợ, không chỉ thời gian xây bản đầu tiên.

### 26.5. Đánh giá license quá muộn

Một công cụ có thể rất phù hợp kỹ thuật nhưng không được phép dùng hoặc phân phối theo mô hình sản phẩm. Kiểm tra license trước khi đầu tư sâu.

### 26.6. Không kiểm tra API extension

Một tính năng có thể hoạt động nhờ sửa class nội bộ nhưng bị phá vỡ ở bản nâng cấp. Ưu tiên extension point được hỗ trợ chính thức.

### 26.7. Bỏ qua runtime

Framework có thể giúp định nghĩa ngôn ngữ nhưng không giải quyết an toàn thực thi, concurrency, resource quota hoặc observability. Đánh giá toàn bộ đường đi từ source đến runtime.

### 26.8. Chỉ đo hiệu năng parser

Semantic analysis, generator, build và editor update có thể là bottleneck thật. Đo từng giai đoạn trên workload đại diện.

### 26.9. Tin điểm số tổng tuyệt đối

Điểm có trọng số phụ thuộc trọng số và giả định. Một yêu cầu bắt buộc không đạt có thể loại ứng viên dù tổng điểm cao.

### 26.10. Không thử nâng cấp

PoC với một phiên bản không cho biết công cụ dễ nâng cấp thế nào. Thử nâng một phiên bản hoặc đọc migration history trước khi cam kết.

### 26.11. Không có exit plan

Nếu toàn bộ grammar và model nằm trong định dạng độc quyền, chi phí chuyển đổi có thể rất lớn. Xác định artifact nào có thể export và phần nào bị khóa.

### 26.12. Mua workbench trước khi hiểu workflow

Một workbench có thể cung cấp nhiều tính năng không được sử dụng. Làm rõ công việc và người dùng trước, rồi chọn phạm vi tooling cần thiết.

## 27. Câu hỏi tự kiểm tra

1. Phân biệt library, framework, tool và workbench trong phát triển DSL.
2. Vì sao cần bắt đầu việc chọn công cụ từ miền nghiệp vụ, người dùng và vòng đời DSL?
3. Functional fit gồm những năng lực nào từ grammar đến runtime?
4. Khi đánh giá AST/CST, cần xem xét source mapping và khả năng mở rộng ra sao?
5. Những yếu tố kiến trúc nào có thể làm một công cụ khó tích hợp?
6. Extension point và plugin architecture cần được đánh giá theo những tiêu chí nào?
7. Vì sao cần đo hiệu năng parser, semantic analysis, editor và runtime riêng?
8. Source mapping và error recovery ảnh hưởng thế nào đến trải nghiệm phát triển?
9. Những vấn đề compatibility nào xuất hiện khi DSL, schema và bytecode tiến hóa?
10. Độ trưởng thành của hệ sinh thái có thể được đánh giá bằng bằng chứng nào?
11. Total Cost of Ownership gồm những khoản chi phí nào ngoài license?
12. Vendor lock-in có thể giảm bằng API, định dạng mở và export artifact ra sao?
13. Một PoC tốt cần bao gồm những use case và failure path nào?
14. Ma trận đánh giá có trọng số được tính thế nào và vì sao không thể thay thế judgment?
15. Những tiêu chí nào quan trọng khi chọn parser generator?
16. Những tiêu chí nào quan trọng khi chọn language workbench?
17. Hãy đề xuất bộ công cụ cho một DSL workflow có concurrency, runtime và visualizer; giải thích các trade-off.
18. Hãy viết một quyết định lựa chọn công cụ ngắn, nêu must-have, ứng viên, bằng chứng, TCO, rủi ro và điều kiện xem xét lại.
