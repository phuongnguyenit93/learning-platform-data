# Hỗ trợ người dùng

Trong vòng đời của một sản phẩm sử dụng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), hỗ trợ người dùng là hoạt động giúp người dùng cài đặt, học, áp dụng, vận hành và nâng cấp sản phẩm một cách hiệu quả. Hỗ trợ không chỉ bắt đầu khi có ticket lỗi. Nó bắt đầu từ lúc người dùng tìm hiểu sản phẩm, tiếp tục trong onboarding, phát triển mô hình, tích hợp, triển khai, vận hành và kết thúc khi sản phẩm hoặc một phiên bản được ngừng hỗ trợ.

Một nền tảng DSL có thể có nhiều nhóm người dùng: người viết DSL, kiến trúc sư mô hình, lập trình viên tích hợp, quản trị viên, nhóm vận hành, plugin author và người dùng nghiệp vụ. Mỗi nhóm gặp vấn đề khác nhau. Người viết DSL cần giải thích syntax và diagnostics; quản trị viên cần hướng dẫn cấu hình, phân quyền và backup; đội vận hành cần thông tin sự cố, log và quy trình khôi phục; plugin author cần contract và compatibility guide.

**Hỗ trợ người dùng (user support)** là hệ thống quy trình, tài liệu, công cụ, kênh giao tiếp và trách nhiệm giúp người dùng giải quyết vấn đề trong suốt vòng đời sản phẩm. Một chương trình hỗ trợ tốt giảm thời gian tìm nguyên nhân, giúp người dùng tự xử lý các vấn đề phổ biến, chuyển đúng vấn đề đến nhóm chịu trách nhiệm và biến phản hồi thực tế thành cải tiến sản phẩm.

## 1. Vai trò của hỗ trợ trong vòng đời sản phẩm

Hỗ trợ cần được thiết kế cùng sản phẩm thay vì chỉ bổ sung sau khi phát hành.

Các giai đoạn chính:

1. **Discovery:** giúp người dùng hiểu sản phẩm phù hợp với nhu cầu nào.
2. **Evaluation:** cung cấp ví dụ, sandbox, tài liệu kiến trúc và hướng dẫn thử nghiệm.
3. **Onboarding:** hỗ trợ cài đặt, cấu hình, tạo project đầu tiên và học cú pháp.
4. **Adoption:** giúp nhóm áp dụng DSL vào workflow thực tế.
5. **Integration:** hỗ trợ API, database, plugin, CI/CD và hệ thống ngoài.
6. **Production operation:** hỗ trợ giám sát, chẩn đoán, incident và phục hồi.
7. **Upgrade/migration:** giúp chuyển version, schema và artifact.
8. **Renewal/optimization:** thu thập feedback và tối ưu cách sử dụng.
9. **Deprecation/end of life:** thông báo, hỗ trợ chuyển đổi và lưu trữ dữ liệu.

Mỗi giai đoạn cần loại hỗ trợ và tài liệu khác nhau. Người mới cần quickstart và ví dụ nhỏ; người vận hành cần runbook, log format, backup/restore và escalation path.

## 2. Xác định nhóm người dùng và nhu cầu

Không nên thiết kế một kênh hoặc một tài liệu cho mọi đối tượng.

| Nhóm | Nhu cầu thường gặp | Hình thức hỗ trợ |
|---|---|---|
| DSL author | Syntax, type errors, examples, formatter | Language reference, IDE help, diagnostics |
| Model architect | Module boundaries, dependencies, versioning | Design guide, architecture review |
| Application developer | API, generated code, runtime integration | API docs, SDK examples, integration guide |
| Plugin author | Extension API, lifecycle, compatibility | Plugin guide, sample plugin, contract tests |
| Administrator | Installation, access, configuration | Admin guide, setup checklist |
| Operator/SRE | Monitoring, incidents, recovery | Runbook, dashboards, escalation |
| Business user | Workflow meaning and outcomes | User guide, domain glossary, training |

Cần xác định ai là người mở ticket, ai có thể cung cấp log, ai được phép chia sẻ model source và ai có quyền thay đổi production. Việc phân vai giúp support không yêu cầu người dùng cung cấp thông tin vượt quá quyền hoặc khả năng của họ.

## 3. Mô hình hỗ trợ nhiều tầng

Một mô hình phổ biến chia hỗ trợ thành nhiều tầng:

- **Self-service:** tài liệu, FAQ, tutorial, examples, knowledge base và diagnostics trong sản phẩm.
- **First-line support:** tiếp nhận, phân loại, xác nhận thông tin và xử lý vấn đề phổ biến.
- **Technical support:** phân tích DSL, configuration, API, build và runtime.
- **Engineering escalation:** xử lý bug trong compiler, runtime, plugin API hoặc platform.
- **Product/domain escalation:** giải thích semantics, policy hoặc quyết định thiết kế sản phẩm.
- **Incident management:** điều phối sự cố ảnh hưởng nhiều người dùng hoặc production.

~~~mermaid
flowchart TD
    A[User question or issue] --> B[Self-service resources]
    B --> C{Resolved?}
    C -->|Yes| D[Feedback and close]
    C -->|No| E[First-line support]
    E --> F{Known procedure?}
    F -->|Yes| G[Apply runbook]
    F -->|No| H[Technical support]
    H --> I{Product defect or deep issue?}
    I -->|No| J[Configuration or usage guidance]
    I -->|Yes| K[Engineering escalation]
    K --> L[Fix or workaround]
    G --> M[Confirm resolution]
    J --> M
    L --> M
    M --> D
~~~

Tầng đầu tiên không cần giải quyết mọi vấn đề. Nhiệm vụ của nó là xác định vấn đề, thu thập thông tin cần thiết, cung cấp hướng dẫn đã được xác nhận và chuyển tiếp đúng nhóm khi cần.

## 4. Kênh hỗ trợ

Các kênh thường gặp:

- Help center hoặc knowledge base.
- Issue tracker.
- Email support.
- In-app feedback.
- Community forum.
- Chat hoặc live support.
- Office hours và technical workshop.
- Incident status page.
- Customer success hoặc account channel.
- Internal support portal cho đội vận hành.

Mỗi kênh cần có mục đích và kỳ vọng phản hồi rõ. Ví dụ, community forum phù hợp câu hỏi và chia sẻ kinh nghiệm; incident channel phù hợp cập nhật sự cố; issue tracker phù hợp theo dõi bug có reproduction steps.

Không nên để người dùng phải đăng cùng một vấn đề ở nhiều nơi. Ticket hoặc case ID nên là tham chiếu chính, các trao đổi liên quan được liên kết vào đó.

## 5. Phạm vi và cam kết hỗ trợ

Một chương trình hỗ trợ cần công bố:
- Sản phẩm và version được hỗ trợ.
- Các loại câu hỏi được tiếp nhận.
- Kênh và giờ làm việc.
- Ngôn ngữ hỗ trợ.
- Thời gian phản hồi mục tiêu.
- Cách phân loại severity.
- Thông tin cần cung cấp khi mở case.
- Quy tắc bảo mật và xử lý dữ liệu.
- Điều kiện escalation.
- Chính sách support cho plugin hoặc integration bên thứ ba.

Cần phân biệt response time với resolution time. Response time là thời gian đến khi người dùng nhận phản hồi đầu tiên có ý nghĩa. Resolution time là thời gian đến khi vấn đề được giải quyết hoặc có phương án chấp nhận được. Một bug phức tạp có thể mất nhiều ngày để sửa dù support đã phản hồi nhanh.

Service Level Agreement (SLA) là cam kết chính thức nếu tổ chức có cung cấp. Service Level Objective (SLO) là mục tiêu vận hành nội bộ. Không nên gọi mọi mục tiêu nội bộ là SLA nếu chưa có cam kết tương ứng.

## 6. Phân loại yêu cầu hỗ trợ

Một taxonomy rõ giúp route case đúng nhóm và phân tích xu hướng.

Ví dụ category:
- Getting started/onboarding.
- Syntax and language usage.
- Type checking and diagnostics.
- Model design and architecture.
- Code generation.
- Runtime behavior.
- API and data integration.
- Plugin and extension.
- Build and deployment.
- Performance and scalability.
- Security and access.
- Versioning and migration.
- Incident/outage.
- Documentation or feature request.

Có thể tách loại yêu cầu:
- Question: cần giải thích.
- How-to: cần hướng dẫn thao tác.
- Configuration issue: cấu hình sai hoặc thiếu.
- Defect: behavior không đúng contract.
- Compatibility issue: version không tương thích.
- Incident: gián đoạn hoặc suy giảm dịch vụ.
- Feature request: yêu cầu khả năng mới.
- Documentation gap: tài liệu thiếu hoặc gây hiểu nhầm.

Phân loại không nên quá phức tạp. Nếu support phải chọn giữa hàng trăm category gần giống nhau, dữ liệu thống kê sẽ thiếu nhất quán.

## 7. Severity và priority

Severity mô tả mức ảnh hưởng của vấn đề; priority mô tả thứ tự xử lý theo nhu cầu kinh doanh và nguồn lực.

Một ví dụ severity:

| Mức | Mô tả | Ví dụ |
|---|---|---|
| Critical | Production ngừng hoạt động hoặc dữ liệu có nguy cơ nghiêm trọng | Runtime không xử lý được mọi request |
| High | Chức năng chính bị hỏng, không có workaround hợp lý | Compiler tạo artifact sai cho module quan trọng |
| Medium | Một nhóm chức năng bị ảnh hưởng, có workaround | Plugin không nạp trong một cấu hình cụ thể |
| Low | Tác động nhỏ hoặc câu hỏi sử dụng | Tài liệu thiếu ví dụ cho một option |

Priority có thể chịu ảnh hưởng bởi:
- Số người dùng bị ảnh hưởng.
- Mức độ quan trọng của workflow.
- Có workaround hay không.
- Rủi ro dữ liệu hoặc bảo mật.
- Deadline hoặc cam kết khách hàng.
- Tần suất tái diễn.
- Mức độ lan rộng của lỗi.

Không nên phân loại chỉ dựa vào ngôn từ của ticket. Cần xác minh impact, scope và production status.

## 8. Quy trình tiếp nhận case

Một quy trình tiếp nhận có thể gồm:

1. Tạo case ID.
2. Xác nhận người gửi và môi trường liên quan.
3. Ghi phiên bản sản phẩm, DSL, runtime và plugin.
4. Phân loại category và severity.
5. Tóm tắt triệu chứng bằng ngôn ngữ trung lập.
6. Xác định thời điểm bắt đầu và tần suất.
7. Thu thập reproduction steps hoặc diagnostics.
8. Xác định workaround hiện có.
9. Chỉ định owner.
10. Thông báo bước tiếp theo và thời điểm cập nhật.

Một ticket tốt giúp người xử lý tiếp tục mà không phải hỏi lại những thông tin đã có. Tuy nhiên, không nên yêu cầu mọi thông tin trong mọi trường hợp. Với câu hỏi tài liệu đơn giản, một đoạn source nhỏ và version có thể là đủ.

## 9. Thông tin cần thu thập cho vấn đề DSL

Khi người dùng báo lỗi DSL, thông tin hữu ích có thể gồm:

- DSL language version.
- Compiler hoặc parser version.
- Runtime version.
- IDE/workbench và extension version.
- OS và architecture nếu liên quan.
- Project/module structure ở mức cần thiết.
- Source snippet tối thiểu tái hiện lỗi.
- Input data đã được làm sạch.
- Diagnostic code và source location.
- Expected behavior.
- Actual behavior.
- Các bước thực hiện.
- Lần cuối hoạt động đúng.
- Thay đổi gần nhất.
- Build command hoặc execution context.
- Plugin và dependency liên quan.

Không phải mọi case cần full repository. Hãy ưu tiên minimal reproduction: phần source, config và input nhỏ nhất vẫn tái hiện lỗi.

## 10. Diagnostic bundle và khả năng tự chẩn đoán

Một DSL workbench có thể tạo diagnostic bundle để người dùng gửi cho support.

Bundle có thể chứa:
- Product/version information.
- Environment summary.
- Sanitized configuration.
- Compiler/runtime diagnostics.
- Relevant log excerpt.
- Plugin inventory.
- Dependency resolution summary.
- Build task report.
- Model statistics.
- Correlation IDs.
- Reproduction command.

Bundle cần được xem trước khi gửi để người dùng biết nội dung nào được thu thập. Không nên tự động đính kèm source code, secret, token, database URL có password hoặc dữ liệu cá nhân.

Một diagnostic bundle tốt có schema version và timestamp. Support tool cần biết bundle được tạo bởi version nào để parse đúng.

## 11. Privacy và bảo vệ dữ liệu

Support thường cần thông tin kỹ thuật nhưng không nhất thiết cần dữ liệu thật. Cần áp dụng data minimization.

Nguyên tắc:
- Thu thập ít dữ liệu nhất đủ để chẩn đoán.
- Redact token, password, API key và private key.
- Không yêu cầu production database dump nếu không cần.
- Dùng synthetic hoặc masked sample.
- Mã hóa dữ liệu khi truyền và lưu.
- Giới hạn người có quyền truy cập case attachment.
- Đặt retention và deletion policy.
- Không dùng dữ liệu support cho mục đích khác nếu chưa có căn cứ và thông báo phù hợp.
- Ghi audit khi truy cập dữ liệu nhạy cảm.

Ví dụ, một error log có thể chứa Authorization header hoặc connection string. Diagnostic exporter nên có redaction rules trước khi tạo bundle, đồng thời cho phép người dùng review.

## 12. Hướng dẫn tái hiện lỗi (reproduction)

Reproduction là cách tạo lại triệu chứng theo các bước xác định. Nó giúp phân biệt:
- Bug trong sản phẩm.
- Cấu hình sai.
- Source không hợp lệ.
- Version mismatch.
- External dependency failure.
- Race condition hoặc dữ liệu không ổn định.

Một reproduction report nên có:
1. Preconditions.
2. Environment/version.
3. Input hoặc source fixture.
4. Exact steps/command.
5. Expected result.
6. Actual result.
7. Frequency.
8. Relevant log/diagnostic.

Ví dụ:

~~~text
Precondition:
  DSL compiler 3.4
  Runtime 5.2
  Plugin database-postgres 2.1

Steps:
  1. Open fixture order-model.dsl
  2. Run compile target postgres
  3. Load generated artifact
  4. Execute query with a null optional field

Expected:
  Query returns no match.

Actual:
  Runtime throws NullComparisonException.

Frequency:
  100% with the fixture.
~~~

Reproduction cần đủ nhỏ để chạy nhanh và không chứa dữ liệu nhạy cảm.

## 13. Triage và phân tích nguyên nhân

Triage là quá trình xác định loại vấn đề, impact, owner và hướng xử lý.

Một flow có thể:
- Xác nhận có tái hiện được không.
- Kiểm tra version có nằm trong support matrix không.
- So sánh với behavior đã công bố.
- Kiểm tra known issue và release note.
- Xác định layer gây lỗi.
- Đánh giá workaround.
- Chuyển engineering nếu có dấu hiệu defect.
- Cập nhật severity khi có thêm evidence.

Không nên kết luận “user error” chỉ vì support không tái hiện được. Có thể environment, plugin hoặc data khác nhau. Ghi rõ điều đã thử và thông tin còn thiếu.

Root cause analysis (RCA) nên phân biệt symptom, trigger, root cause và contributing factors. Ví dụ symptom là endpoint trả 500; trigger là request có optional field null; root cause là generator tạo validator sai; contributing factor là test fixture không có null case.

## 14. Escalation sang engineering

Escalation cần có context đủ để engineering bắt đầu điều tra.

Một handoff tốt gồm:
- Case ID và severity.
- User impact.
- Affected version/environment.
- Minimal reproduction.
- Expected vs actual.
- Logs/diagnostics đã redacted.
- Các bước đã thử.
- Workaround.
- Hypothesis nếu có, được ghi rõ là giả thuyết.
- Owner support và communication owner.

Không nên chuyển một ticket chỉ với câu “không hoạt động”. Support nên gom evidence, nhưng không cần chứng minh root cause trước khi escalation nếu impact nghiêm trọng.

Engineering có thể trả về:
- Confirmed defect.
- Configuration guidance.
- Unsupported scenario.
- Known issue.
- Need more evidence.
- Fix planned.
- Fixed in version X.
- Won't fix với lý do sản phẩm.

Support cần chuyển câu trả lời kỹ thuật thành hướng dẫn phù hợp với người dùng.

## 15. Workaround và resolution

Workaround giúp khôi phục công việc trong khi chưa có fix đầy đủ. Một workaround cần:
- Nêu rõ version và điều kiện áp dụng.
- Giải thích trade-off hoặc giới hạn.
- Có bước rollback nếu thay đổi cấu hình.
- Không làm mất dữ liệu.
- Không bỏ qua security control.
- Có thời hạn xem xét lại nếu chỉ là giải pháp tạm.

Resolution có thể là:
- Hướng dẫn sử dụng đúng.
- Cấu hình được sửa.
- Migration được chạy.
- Patch hoặc release mới.
- Plugin được nâng cấp.
- Dữ liệu được khôi phục.
- External service được khắc phục.
- Feature request được đưa vào roadmap.

Một case chỉ nên đóng khi người dùng đã xác nhận hoặc có quy trình closure rõ. Nếu người dùng không phản hồi, có thể đóng sau thời gian thông báo và cho phép reopen theo policy.

## 16. Documentation như một phần của support

Knowledge base nên bao phủ câu hỏi phổ biến và các lỗi đã biết.

Các loại nội dung:
- Quickstart.
- Concept guide.
- Language reference.
- API reference.
- Tutorial.
- Example project.
- Troubleshooting.
- FAQ.
- Migration guide.
- Release notes.
- Known issues.
- Security advisory.
- Admin/operator guide.
- Plugin developer guide.

Tài liệu cần có:
- Product/version applicability.
- Preconditions.
- Steps rõ ràng.
- Expected result.
- Common failure modes.
- Links tới khái niệm liên quan.
- Owner và ngày review.

Một bài hướng dẫn không còn đúng với version hiện tại có thể gây nhiều ticket hơn là không có tài liệu. Cần version hóa tài liệu hoặc đánh dấu nội dung cũ.

## 17. In-product help và diagnostics

Hỗ trợ hiệu quả khi sản phẩm giúp người dùng hiểu lỗi ngay tại nơi xảy ra.

Ví dụ:
- Diagnostic có code và source span.
- Hover giải thích type hoặc function.
- Quick fix cho import hoặc syntax phổ biến.
- Link từ error code đến troubleshooting guide.
- Build report chỉ ra task và dependency thất bại.
- Plugin manager hiển thị lý do plugin không tương thích.
- Migration tool báo construct chưa hỗ trợ và vị trí source.
- Runtime trace gắn với rule ID/version.

Thông báo nên nói:
- Điều gì xảy ra.
- Vị trí hoặc thành phần liên quan.
- Vì sao có thể xảy ra.
- Người dùng có thể làm gì tiếp theo.
- Mã tham chiếu để support tra cứu.

Không nên đưa stack trace nội bộ hoặc chi tiết implementation vào thông báo người dùng thông thường. Có thể cung cấp technical detail trong diagnostic view có kiểm soát.

## 18. Onboarding và đào tạo

Onboarding tốt giảm ticket lặp lại và tăng adoption.

Một hành trình có thể:
1. Kiểm tra yêu cầu môi trường.
2. Cài CLI/IDE/plugin.
3. Tạo project mẫu.
4. Viết DSL đầu tiên.
5. Parse, validate và generate.
6. Chạy test hoặc runtime.
7. Tích hợp với ứng dụng mẫu.
8. Tạo build pipeline.
9. Học versioning và migration.
10. Triển khai vào môi trường thử nghiệm.

Nên có learning path theo vai trò:
- DSL author.
- Application developer.
- Administrator.
- Plugin author.
- Operator.

Tutorial nên có checkpoint và output mong đợi để người học biết mình đã hoàn thành bước. Sample project cần được kiểm tra với version mà tài liệu công bố.

## 19. Hỗ trợ khi tích hợp

Integration support thường phức tạp vì liên quan nhiều hệ thống.

Cần tài liệu:
- API contract.
- Authentication/authorization.
- Network requirements.
- Database compatibility.
- Plugin API.
- Event schema.
- Build and deployment.
- Timeout/retry.
- Error mapping.
- Observability.
- Version support matrix.

Khi tích hợp không hoạt động, cần xác định boundary:
- DSL source có compile không?
- Generated artifact có đúng không?
- Host có load artifact không?
- Network request có đến service không?
- Authentication thành công không?
- Schema có tương thích không?
- Database transaction có commit không?

Một sequence diagram hoặc request trace thường hữu ích hơn việc đọc log của một service riêng lẻ.

## 20. Hỗ trợ vận hành và production incident

Production support cần runbook cho:
- Service unavailable.
- High latency.
- Error rate tăng.
- Queue backlog.
- Database connection exhaustion.
- Plugin load failure.
- Build cache corruption.
- Generated artifact mismatch.
- Data migration failure.
- Resource exhaustion.

Incident process thường gồm:
1. Detect và xác nhận impact.
2. Assign incident commander hoặc owner.
3. Phân loại severity.
4. Giảm tác động bằng mitigation.
5. Cập nhật trạng thái cho người dùng.
6. Khôi phục service.
7. Xác minh dữ liệu và behavior.
8. Theo dõi sau khôi phục.
9. Viết post-incident review.
10. Theo dõi action items.

Trong incident, communication cần rõ ràng và có nhịp cập nhật. Nếu chưa biết root cause, nói rõ điều đã xác nhận, impact hiện tại và thời điểm cập nhật tiếp theo; không suy đoán như thể đó là sự thật.

## 21. Status page và thông báo sự cố

Status page có thể hiển thị trạng thái của:
- DSL registry/package repository.
- License/authentication service.
- Build cache.
- Hosted runtime.
- Documentation portal.
- Plugin marketplace.
- Deployment service.

Thông báo nên có:
- Component bị ảnh hưởng.
- Start time.
- User impact.
- Workaround nếu có.
- Current status.
- Next update time.
- Resolution time khi đã khôi phục.

Không nên công bố thông tin bảo mật hoặc dữ liệu khách hàng trong status update. Một sự cố đã kết thúc vẫn cần postmortem phù hợp nếu impact đáng kể.

## 22. Hỗ trợ versioning và migration

Người dùng có thể cần nâng DSL compiler, runtime, plugin, schema hoặc project model. Support cần:
- Support matrix.
- Release notes.
- Breaking change list.
- Migration guide.
- Compatibility checker.
- Automated migration tool.
- Backup/restore instructions.
- Known issue và workaround.
- Rollback plan.
- End-of-support dates.

Trước khi upgrade:
1. Xác định version hiện tại.
2. Kiểm tra target version được hỗ trợ.
3. Backup source, configuration và dữ liệu.
4. Chạy compatibility scan.
5. Thử migration trên copy.
6. Chạy test suite.
7. Deploy theo môi trường.
8. Theo dõi output và error.
9. Giữ rollback option trong thời gian phù hợp.

Support không nên hướng dẫn người dùng bỏ qua migration warning nếu chưa hiểu tác động. Một migration có thể thay đổi data hoặc behavior, không chỉ syntax.

## 23. Release notes và known issues

Release notes giúp người dùng hiểu:
- Tính năng mới.
- Behavior thay đổi.
- Bug được sửa.
- Deprecation.
- Breaking changes.
- Migration requirement.
- Plugin/runtime compatibility.
- Security fixes.
- Known issues.

Known issue nên ghi:
- Triệu chứng.
- Affected versions.
- Điều kiện xảy ra.
- Impact.
- Workaround.
- Planned fix hoặc status nếu được công bố.

Một known issue rõ ràng có thể giúp người dùng tự nhận diện và tránh mở nhiều ticket giống nhau.

## 24. Deprecation và end of life

Một version không thể được hỗ trợ vô thời hạn. End-of-life (EOL) cần có quy trình công bố và migration.

Thông tin cần:
- Version hoặc feature bị deprecate.
- Ngày thông báo.
- Ngày ngừng nhận bug fix.
- Ngày kết thúc security support.
- Ngày EOL.
- Version thay thế.
- Migration guide.
- Các trường hợp ngoại lệ nếu có.
- Cách truy cập tài liệu cũ.

Deprecation nên đi trước removal đủ lâu để người dùng có thời gian chuyển đổi. Tooling có thể cảnh báo construct deprecated và chỉ rõ replacement.

Không nên xóa documentation hoặc artifact ngay khi EOL nếu người dùng còn cần tái hiện build hoặc quyết định lịch sử. Có thể lưu archive read-only theo policy.

## 25. Feedback loop và product improvement

Support là nguồn dữ liệu về trải nghiệm thực tế. Ticket có thể cho thấy:
- Một diagnostic khó hiểu.
- Một API thiếu khả năng.
- Tutorial có bước sai.
- Migration tool không bao phủ construct phổ biến.
- Plugin contract khó sử dụng.
- Performance không đáp ứng workload.
- Một behavior không phù hợp domain.

Feedback cần được tổng hợp và phân loại:
- Defect.
- Documentation gap.
- UX friction.
- Feature request.
- Product limitation.
- Training need.

Không nên xem số ticket đơn lẻ là thước đo chất lượng. Một tính năng được dùng nhiều có thể có nhiều ticket vì mức độ adoption cao. Cần xem tỷ lệ theo user/usage, mức độ nghiêm trọng và xu hướng theo version.

## 26. Knowledge management

Khi một case được giải quyết, tri thức hữu ích nên được chuyển thành:
- FAQ.
- Troubleshooting article.
- Known issue.
- Runbook update.
- Example project.
- Diagnostic improvement.
- Regression test.
- Release note.
- Migration note.

Không phải mọi ticket đều cần bài viết mới. Nhưng những vấn đề lặp lại hoặc có workaround đáng chú ý nên được lưu lại.

Knowledge base cần owner, review date, version applicability và quy trình cập nhật khi product behavior thay đổi. Tránh copy nội dung không kiểm soát ở nhiều nơi vì các bản sao có thể mâu thuẫn.

## 27. Hỗ trợ plugin và ecosystem bên thứ ba

Một DSL platform có thể phụ thuộc plugin do vendor hoặc community phát triển. Support boundary cần rõ:
- Plugin core hay third-party?
- Version có nằm trong support matrix không?
- Ai chịu trách nhiệm code plugin?
- Host API có tương thích không?
- Plugin có được ký/xác minh không?
- Có reproduction không dùng plugin để isolate issue không?

Một quy trình hữu ích:
1. Ghi plugin ID/version và host version.
2. Kiểm tra compatibility matrix.
3. Reproduce với plugin tối thiểu.
4. Thử tắt plugin để xác định phạm vi.
5. Kiểm tra log lifecycle và extension registration.
6. Chuyển vendor/plugin maintainer khi phù hợp.
7. Ghi rõ ranh giới trách nhiệm và workaround.

Không nên yêu cầu người dùng gỡ plugin production nếu chưa đánh giá tác động và có phương án an toàn.

## 28. Hỗ trợ accessibility và localization

Tài liệu và kênh hỗ trợ cần dễ tiếp cận:
- Hướng dẫn có cấu trúc và heading rõ.
- Code sample có thể sao chép.
- Không chỉ dùng màu để biểu thị lỗi.
- Diagnostics có text và code.
- UI hỗ trợ keyboard và screen reader.
- Hình ảnh có mô tả.
- Message có thể dịch.
- Date/time và number format được ghi rõ.
- Tài liệu có ngôn ngữ phù hợp với nhóm người dùng.

Localization không nên thay đổi error code hoặc identifier. Mã lỗi cần ổn định để client và support tool xử lý; message có thể được dịch theo locale.

## 29. Metrics cho hoạt động hỗ trợ

Một số metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| First response time | Thời gian phản hồi đầu tiên |
| Time to resolution | Thời gian đến khi giải quyết |
| Reopen rate | Tỷ lệ case mở lại |
| Escalation rate | Tỷ lệ chuyển engineering |
| Backlog age | Tuổi của case chưa xử lý |
| Self-service success | Tỷ lệ người dùng tự giải quyết |
| Repeat issue rate | Tỷ lệ vấn đề lặp lại |
| CSAT | Mức hài lòng sau hỗ trợ |
| Documentation helpfulness | Mức hữu ích của tài liệu |
| Incident recurrence | Sự cố lặp lại |
| Version distribution | Tỷ lệ người dùng theo version |
| Migration completion | Tỷ lệ hoàn thành nâng cấp |

Metrics cần được phân đoạn theo category, severity, product version và user group. Không nên tối ưu first response bằng cách gửi phản hồi chung chung nhưng không giúp người dùng tiến triển.

## 30. Customer communication và expectation management

Mỗi case nên có owner giao tiếp. Người dùng cần biết:
- Ai đang xử lý.
- Vấn đề đã được xác nhận đến đâu.
- Thông tin nào còn thiếu.
- Có workaround không.
- Bước tiếp theo là gì.
- Khi nào sẽ có cập nhật tiếp theo.

Nếu chưa có resolution, vẫn có thể cập nhật tiến độ và những gì đã kiểm tra. Tránh hứa ngày fix khi engineering chưa xác nhận. Phân biệt target date, estimate và committed date.

Khi fix được phát hành, thông báo version, release note và bước người dùng cần thực hiện. Một bug fix không tự động áp dụng nếu user chưa nâng cấp hoặc chưa chạy migration.

## 31. Support runbook

Runbook là hướng dẫn thao tác cho một loại vấn đề hoặc quy trình vận hành. Một runbook nên có:
- Trigger hoặc triệu chứng.
- Scope và impact.
- Preconditions/permissions.
- Các bước chẩn đoán.
- Cách thu thập log.
- Workaround được xác nhận.
- Điều kiện escalation.
- Recovery/rollback.
- Verification sau xử lý.
- Owner và ngày review.

Ví dụ runbook cho plugin không load:

~~~text
Symptom:
  Plugin appears in the catalog but is not active.

Steps:
  1. Record host and plugin versions.
  2. Inspect manifest validation diagnostics.
  3. Check dependency resolution.
  4. Verify package checksum and signature.
  5. Inspect plugin initialization log.
  6. Confirm extension point version.
  7. Disable and re-enable only after preserving logs.
  8. Escalate with sanitized diagnostic bundle if unresolved.
~~~

Runbook cần được thử nghiệm định kỳ. Một hướng dẫn chưa từng được thực hiện trong môi trường thật có thể thiếu bước hoặc chứa lệnh nguy hiểm.

## 32. Supportability by design

Một sản phẩm dễ hỗ trợ cần có khả năng chẩn đoán ngay từ thiết kế:

- Stable error codes.
- Correlation IDs.
- Structured logs.
- Version and provenance metadata.
- Diagnostics có source span.
- Health/readiness endpoints.
- Plugin status và dependency report.
- Build task outcome.
- Trace xuyên service.
- Export diagnostic bundle.
- Safe configuration inspection.
- Clear support matrix.

Mỗi component nên trả lỗi có context đủ để xác định boundary, nhưng không tiết lộ secret. Logs cần có mức độ và retention phù hợp.

Supportability cũng cần test. Có thể kiểm tra rằng error response chứa code, log chứa correlation ID và diagnostic bundle không chứa token.

## 33. Hỗ trợ khi người dùng không thể tái hiện lỗi

Một số lỗi chỉ xuất hiện trên production, dữ liệu lớn hoặc thời điểm cụ thể. Khi không tái hiện được:
- Ghi lại thời điểm, version và correlation ID.
- Thu thập sanitized trace.
- So sánh config và dependency.
- Kiểm tra resource/latency metrics.
- Tìm thay đổi gần thời điểm xảy ra.
- Kiểm tra concurrency và ordering.
- Xác định có thể tạo reproduction an toàn không.
- Đưa instrumentation bổ sung nếu cần.
- Theo dõi tái diễn.

Không nên yêu cầu user bật debug logging rộng trên production mà không đánh giá dung lượng, performance và dữ liệu nhạy cảm. Có thể bật sampling hoặc targeted diagnostic trong thời gian ngắn.

## 34. Hỗ trợ theo mức độ trưởng thành của tổ chức

Một nhóm nhỏ có thể bắt đầu với:
- Một support channel.
- Issue template.
- Version/environment fields.
- FAQ và quickstart.
- Severity đơn giản.
- Owner rõ.
- Release notes.
- Một số runbook quan trọng.

Khi sản phẩm lớn hơn, có thể bổ sung:
- Support tiers.
- SLA/SLO.
- Case management.
- Knowledge base có version.
- Incident commander rotation.
- Plugin/vendor escalation.
- Customer health metrics.
- Self-service diagnostics.
- Support analytics.
- Formal EOL policy.

Không nên triển khai quy trình nặng hơn nhu cầu. Quy trình cần giúp giải quyết vấn đề, không tạo thêm nhiều bước nhập liệu mà không có giá trị.

## 35. Ví dụ: xử lý một case DSL end-to-end

Người dùng báo rằng sau khi nâng compiler, generated API trả 500 khi field optional bị null.

Quy trình hỗ trợ:

1. Tạo case và ghi compiler/runtime/plugin versions.
2. Xác định endpoint và request sample đã được làm sạch.
3. Thu diagnostic code và correlation ID.
4. Kiểm tra release notes về null semantics.
5. Tạo minimal DSL fixture và request.
6. Reproduce trên version cũ và mới.
7. Xác định generator tạo validator mới có behavior khác.
8. Đánh giá impact và workaround.
9. Escalate engineering với reproduction và semantic diff.
10. Engineering cung cấp patch hoặc workaround đã xác nhận.
11. Support thông báo version fix và hướng dẫn upgrade.
12. Người dùng chạy regression test và xác nhận.
13. Case được đóng; knowledge base và regression fixture được cập nhật.

Luồng này vừa giải quyết case, vừa bổ sung test để lỗi không quay lại.

## 36. Quy trình vận hành chương trình hỗ trợ

Có thể tổ chức theo chu kỳ:

1. **Define support scope:** xác định product/version và nhóm người dùng.
2. **Publish channels:** công bố kênh, giờ làm việc và cam kết.
3. **Prepare knowledge:** quickstart, reference, troubleshooting và migration guide.
4. **Instrument product:** error code, logs, traces và diagnostic bundle.
5. **Receive and classify:** tạo case, category, severity và owner.
6. **Triage and reproduce:** xác định impact và minimal reproduction.
7. **Resolve or escalate:** dùng runbook, workaround hoặc engineering handoff.
8. **Communicate:** cập nhật trạng thái và bước tiếp theo.
9. **Verify:** xác nhận resolution trong môi trường người dùng.
10. **Close and learn:** ghi knowledge, regression test và product feedback.
11. **Review metrics:** tìm vấn đề lặp lại và bottleneck support.
12. **Improve lifecycle:** cập nhật tài liệu, diagnostics, migration và release process.

## 37. Nguyên tắc thiết kế

- **Thiết kế hỗ trợ cho từng vai trò:** DSL author, developer, administrator và operator có nhu cầu khác nhau.
- **Bắt đầu từ self-service:** tài liệu, examples và diagnostics cần dễ tìm, dễ dùng.
- **Công bố support scope:** version, channel, giờ làm việc và kỳ vọng phản hồi phải rõ.
- **Phân loại severity theo impact:** không dựa vào cách người gửi diễn đạt.
- **Thu thập minimal reproduction:** chỉ lấy dữ liệu cần thiết để chẩn đoán.
- **Bảo vệ privacy:** redaction, access control và retention phải được thiết kế ngay từ đầu.
- **Giữ case có owner:** người dùng cần biết ai đang điều phối và khi nào được cập nhật.
- **Escalate có context:** version, reproduction, expected/actual và diagnostics giúp engineering bắt đầu nhanh.
- **Runbook phải được kiểm chứng:** hướng dẫn thao tác cần an toàn và cập nhật.
- **Tách workaround khỏi fix:** nêu rõ giới hạn và kế hoạch loại bỏ giải pháp tạm.
- **Gắn tài liệu với version:** hướng dẫn cũ phải được đánh dấu và có migration path.
- **Hỗ trợ upgrade có chuẩn bị:** compatibility scan, backup, test và rollback cần được hướng dẫn.
- **Không replay side effect khi chẩn đoán:** test và shadow evaluation phải cô lập hành động thật.
- **Biến case thành tri thức:** ticket lặp lại cần tạo documentation, diagnostics hoặc regression test.
- **Đo chất lượng toàn diện:** response time, resolution, reopen, self-service và user satisfaction cùng có ý nghĩa.
- **Giao tiếp trung thực:** phân biệt điều đã xác nhận, giả thuyết, workaround và thời điểm cập nhật.
- **Chuẩn bị EOL từ sớm:** người dùng cần thời gian chuyển version và truy cập tài liệu lịch sử.
- **Xem supportability là tính năng:** stable diagnostics, provenance và correlation IDs giảm thời gian xử lý.

Hỗ trợ người dùng là một phần của chất lượng sản phẩm DSL trong toàn bộ vòng đời. Khi người dùng có tài liệu theo version, diagnostics có thể hành động, kênh hỗ trợ rõ, quy trình triage và escalation nhất quán, dữ liệu được bảo vệ và feedback được chuyển thành cải tiến, họ có thể sử dụng và nâng cấp hệ thống với ít gián đoạn hơn.
