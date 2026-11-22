# Lịch phát hành

## 1. Lịch phát hành trong quản trị vòng đời DSL là gì?

**Lịch phát hành (release schedule)** là kế hoạch xác định thời điểm, nhịp độ và các mốc mà một phiên bản sản phẩm được chuẩn bị, kiểm tra, công bố, triển khai và hỗ trợ.

Với một nền tảng ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), một lần phát hành có thể bao gồm nhiều thành phần:

- Grammar, lexer và parser.
- Semantic analyzer, type system và compiler.
- Runtime hoặc workflow engine.
- Host API và plugin SDK.
- CLI, editor extension và Language Server.
- Built-in functions, libraries và templates.
- Documentation, examples và migration guides.
- Schema, configuration và dữ liệu persisted.

Các thành phần này có thể có version và nhịp phát hành khác nhau. Một parser mới có thể yêu cầu runtime mới; plugin mới có thể yêu cầu host API level mới; tài liệu có thể cần cập nhật cùng thời điểm thay đổi syntax.

Lịch phát hành giúp đội dự án phối hợp những thay đổi đó, để người dùng biết khi nào có tính năng mới, khi nào cần nâng cấp, phiên bản nào còn được hỗ trợ và cách xử lý khi cần quay lại phiên bản trước.

Một lịch phát hành tốt cân bằng giữa tốc độ đưa cải tiến đến người dùng, chất lượng, tính tương thích, khả năng vận hành và mức độ rủi ro.

## 2. Vì sao dự án DSL cần lịch phát hành rõ ràng?

DSL thường được nhúng vào quy trình nghiệp vụ hoặc ứng dụng khác. Một thay đổi nhỏ trong syntax hay semantics có thể ảnh hưởng nhiều project DSL đã tồn tại.

Lịch phát hành giúp:

1. Dự đoán thời điểm có tính năng, bản vá và thay đổi tương thích.
2. Phối hợp compiler, runtime, plugin, editor và tài liệu.
3. Dành đủ thời gian cho kiểm thử và migration.
4. Tránh phát hành khi còn lỗi nghiêm trọng đã biết.
5. Thông báo sớm cho người dùng và nhóm tích hợp.
6. Duy trì thời gian hỗ trợ và bản vá bảo mật.
7. Chuẩn bị rollout, rollback và hỗ trợ sau phát hành.
8. Theo dõi chất lượng của từng phiên bản.

Nếu không có lịch rõ, các nhóm có thể cập nhật API vào thời điểm khác nhau, tài liệu mô tả syntax chưa được phát hành hoặc plugin bị buộc nâng cấp đột ngột.

### 2.1 Lịch phát hành không phải lời hứa cứng nhắc

Ngày dự kiến là công cụ lập kế hoạch. Nếu phát hiện regression nghiêm trọng hoặc rủi ro dữ liệu, nhóm có thể hoãn phát hành theo tiêu chí đã công bố.

Điều quan trọng là quyết định hoãn phải có lý do, owner và thông tin cập nhật cho các bên liên quan.

### 2.2 Lịch phát hành là một phần của contract với người dùng

Khi công bố cadence, support window hoặc ngày ngừng hỗ trợ, tổ chức tạo ra kỳ vọng vận hành. Thay đổi lịch cần được truyền thông và quản lý có trách nhiệm.

## 3. Các loại nhịp phát hành

Không có một cadence phù hợp cho mọi sản phẩm. Lựa chọn phụ thuộc vào mức độ trưởng thành, rủi ro và cách người dùng triển khai DSL.

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| Fixed cadence | Phát hành theo chu kỳ cố định | Cần khả năng dự đoán |
| Release train | Thay đổi sẵn sàng sẽ lên chuyến phát hành kế tiếp | Nhiều nhóm cần phối hợp |
| Continuous delivery | Có thể phát hành thường xuyên khi đạt gate | Pipeline tự động và rủi ro được kiểm soát |
| Feature-based | Phát hành khi một nhóm tính năng hoàn tất | Sản phẩm nhỏ hoặc mốc tính năng rõ |
| LTS cadence | Có nhánh hỗ trợ dài hạn và bản cập nhật định kỳ | Khách hàng cần ổn định lâu dài |
| Patch-on-demand | Bản vá khẩn cấp khi có sự cố | Cần xử lý bảo mật hoặc lỗi nghiêm trọng |

### 3.1 Fixed cadence

Ví dụ phát hành minor mỗi tháng và patch khi cần. Cadence cố định giúp khách hàng sắp xếp nâng cấp và giúp nhóm lập kế hoạch năng lực.

### 3.2 Release train

Một release train có ngày chốt nội dung và ngày phát hành định kỳ. Tính năng chưa đạt tiêu chí sẽ chuyển sang chuyến sau, thay vì làm trễ toàn bộ lịch.

### 3.3 Continuous delivery

Mỗi thay đổi có thể được đưa vào production sau khi pipeline, approval và rollout policy đạt yêu cầu. Mô hình này cần kiểm soát feature flag, backward compatibility và khả năng rollback tốt.

### 3.4 LTS và nhánh hỗ trợ

Phiên bản Long-Term Support (LTS) nhận bản vá trong thời gian dài hơn, thường ưu tiên security fix và bug fix có rủi ro thấp. Tính năng mới thường đi vào nhánh phát triển hoặc release train chính.

### 3.5 Patch-on-demand

Patch khẩn cấp có thể được phát hành ngoài cadence khi có lỗ hổng bảo mật hoặc lỗi ảnh hưởng nghiêm trọng. Cần quy trình rút gọn nhưng vẫn có kiểm tra, phê duyệt và thông tin phát hành.

## 4. Phân biệt release, deployment và rollout

Các khái niệm này liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Release | Một phiên bản được đóng gói và công bố | DSL Platform 3.4.0 |
| Deployment | Đưa artifact vào một môi trường | Deploy runtime 3.4.0 lên staging |
| Rollout | Mở dần phiên bản hoặc tính năng cho người dùng | Bật compiler mới cho 10% tenant |
| Promotion | Chuyển cùng artifact qua môi trường tiếp theo | Staging sang production |
| Rollback | Quay về phiên bản hoặc trạng thái trước | Chuyển traffic về runtime 3.3.2 |
| Hotfix | Bản sửa khẩn cấp | 3.3.3 để vá lỗi nghiêm trọng |

Một release có thể đã được công bố nhưng chưa được rollout cho tất cả tenant. Ngược lại, một deployment nội bộ có thể chỉ là bước kiểm tra trước khi phát hành chính thức.

Với DSL chạy trong nhiều host application, việc phát hành compiler package và triển khai runtime server có thể diễn ra ở thời điểm khác nhau. Lịch cần nói rõ mốc nào áp dụng cho từng đối tượng.

## 5. Vòng đời của một release

Một release thường đi qua các giai đoạn:

~~~text
Plan
  |
  v
Develop
  |
  v
Integrate
  |
  v
Feature complete
  |
  v
Code freeze
  |
  v
Release candidate
  |
  v
Validation and approval
  |
  v
Publish
  |
  v
Rollout and monitor
  |
  v
Maintain / retire
~~~

### 5.1 Planning

Chọn mục tiêu, scope, dependency, owner và mốc thời gian.

### 5.2 Development

Nhóm triển khai feature, bug fix, documentation và migration.

### 5.3 Integration

Tích hợp thay đổi giữa compiler, runtime, plugin, editor và các service phụ thuộc.

### 5.4 Feature complete

Không nhận thêm feature mới cho release trừ khi có quyết định rõ. Nhóm tập trung hoàn thiện và sửa lỗi.

### 5.5 Code freeze

Giới hạn thay đổi vào branch phát hành. Chỉ nhận fix đáp ứng tiêu chí đã định.

### 5.6 Release candidate

Đóng gói một phiên bản ứng viên để kiểm tra trên môi trường gần production.

### 5.7 Approval

Xác nhận release đạt các gate về chất lượng, bảo mật, tương thích, tài liệu và vận hành.

### 5.8 Publish và rollout

Phát hành artifact, công bố release notes và triển khai theo rollout plan.

### 5.9 Maintain và retire

Theo dõi lỗi, phát hành patch, hỗ trợ migration và kết thúc hỗ trợ khi đến thời hạn.

## 6. Lập kế hoạch release

Planning nên bắt đầu từ mục tiêu người dùng và rủi ro kỹ thuật.

### 6.1 Xác định mục tiêu

Ví dụ:

- Hỗ trợ một cấu trúc syntax mới.
- Cải thiện diagnostic và source mapping.
- Thêm host API capability.
- Tăng hiệu năng compiler.
- Sửa lỗi runtime.
- Nâng version dependency.
- Vá lỗ hổng bảo mật.

Mỗi mục tiêu cần mô tả lợi ích và cách xác nhận.

### 6.2 Xác định scope

Ghi rõ feature dự kiến, bug fix, migration, API changes, documentation, platform support và phần không nằm trong release.

### 6.3 Phân tích dependency

Ví dụ một tính năng mới có thể cần:

~~~text
New DSL syntax
      |
      v
Parser and AST
      |
      v
Semantic model
      |
      v
Compiler backend
      |
      v
Runtime capability
      |
      v
Editor support and docs
~~~

Lập dependency graph để biết thứ tự thực hiện và nhóm nào cần phối hợp.

### 6.4 Ước lượng và buffer

Ước lượng dựa trên công việc và dependency thực tế. Dành buffer cho integration, bug fixing, migration và release operations. Không dùng toàn bộ thời gian cho feature development.

### 6.5 Owner và decision maker

Mỗi deliverable cần owner. Cần xác định ai quyết định scope, ai phê duyệt release và ai có quyền hoãn.

### 6.6 Risk register

Ghi rủi ro như breaking syntax, persisted state migration, plugin compatibility, dependency vulnerability, performance regression và thiếu khả năng rollback.

## 7. Lịch theo mốc và release calendar

Release calendar thể hiện các mốc quan trọng để các nhóm cùng theo dõi.

Ví dụ một chu kỳ sáu tuần:

| Tuần | Mốc | Công việc chính |
|---|---|---|
| 1 | Planning | Chốt mục tiêu, owner và dependency |
| 2–3 | Development | Implement feature và test |
| 4 | Feature complete | Hoàn thiện feature, docs và integration |
| 5 | Stabilization | Code freeze, regression và release candidate |
| 6 | Release | Approval, publish, rollout và monitoring |

Đây là lịch minh họa. Nhịp thực tế cần điều chỉnh theo kích thước sản phẩm và năng lực nhóm.

### 7.1 Mốc có owner

Mỗi mốc cần owner và tiêu chí hoàn thành, không chỉ có ngày trên calendar.

### 7.2 Mốc phụ thuộc

Ví dụ ngày phát hành plugin SDK phụ thuộc vào API contract được chốt. Nếu dependency trễ, lịch của consumer cần được cập nhật.

### 7.3 Lịch theo timezone

Với nhóm phân tán, ghi rõ timezone cho thời điểm code freeze, approval và deployment. Tránh diễn giải một thời gian địa phương thành nhiều thời điểm khác nhau.

### 7.4 Thay đổi lịch

Khi mốc thay đổi, cập nhật calendar, issue tracker và thông báo tới nhóm bị ảnh hưởng. Không để lịch cũ còn tồn tại ở tài liệu khác.

## 8. Versioning của DSL và sản phẩm

Release schedule cần đi cùng chính sách versioning.

### 8.1 Product version

Version sản phẩm có thể biểu diễn compiler, runtime, CLI hoặc một bundle tương thích.

### 8.2 Language version

DSL language version mô tả grammar và semantics mà source tuân theo. Một compiler mới có thể hỗ trợ nhiều language version.

Ví dụ:

~~~text
compiler version: 4.2.0
language version: 3
runtime API level: 2
plugin API level: 5
~~~

Các version này có thể khác nhau và cần được ghi rõ.

### 8.3 Semantic Versioning

SemVer thường dùng dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích với public contract.
- MINOR: bổ sung tính năng tương thích.
- PATCH: sửa lỗi tương thích với contract hiện có.

SemVer chỉ có ý nghĩa khi dự án xác định rõ public API và quy tắc phân loại thay đổi.

### 8.4 Pre-release version

Alpha, beta, preview hoặc release candidate cho phép người dùng thử trước. Cần nói rõ mức ổn định, support và migration policy của bản pre-release.

### 8.5 Build metadata

Build number hoặc commit identifier giúp truy vết artifact. Không nên dùng build metadata như một thay thế cho version contract.

### 8.6 Version compatibility matrix

Ghi rõ compiler/runtime/plugin/host version nào được hỗ trợ kết hợp. Ví dụ:

| Compiler | Runtime | Plugin API | Trạng thái |
|---|---|---|---|
| 4.2 | 4.2 | 5 | Supported |
| 4.2 | 4.1 | 5 | Supported nếu feature không yêu cầu runtime mới |
| 4.2 | 3.x | 5 | Unsupported |
| 4.1 | 4.2 | 4 | Cần kiểm tra compatibility policy |

Ma trận thực tế cần được duy trì theo product contract.

## 9. Feature freeze và code freeze

Freeze tạo khoảng ổn định trước khi phát hành.

### 9.1 Feature freeze

Sau feature freeze, không đưa thêm tính năng mới vào release. Nhóm tập trung hoàn thiện feature đã có và sửa lỗi.

### 9.2 Code freeze

Code freeze giới hạn mọi thay đổi. Chỉ những sửa lỗi được chấp thuận mới được merge vào release branch.

### 9.3 Exception process

Một exception cần:

- Lý do và mức độ cần thiết.
- Phạm vi thay đổi.
- Rủi ro regression.
- Test plan.
- Người phê duyệt.
- Kế hoạch rollback nếu cần.

### 9.4 Freeze không dừng công việc

Nhóm vẫn có thể tiếp tục phát triển trên main branch hoặc release tiếp theo. Freeze chỉ áp dụng cho branch hoặc artifact đang ổn định.

### 9.5 Khi nào cần hoãn?

Nếu còn lỗi critical, data migration không an toàn, compatibility chưa được xác nhận hoặc release artifact không thể tái lập, cần xem xét hoãn thay vì bỏ qua gate.

## 10. Release branch và source control

Branch strategy giúp tách phát triển liên tục khỏi ổn định release.

### 10.1 Mainline development

Các feature mới được tích hợp vào branch chính theo quy trình review và test.

### 10.2 Release branch

Khi scope đã ổn định, tạo release branch để sửa lỗi và chuẩn bị artifact.

### 10.3 Patch branch

Với phiên bản cũ còn được hỗ trợ, có thể cần branch riêng để phát hành security/bug patch.

### 10.4 Cherry-pick

Fix từ main có thể được cherry-pick sang release branch. Cần kiểm tra conflict và test trên đúng version branch.

### 10.5 Tag

Tag release nên trỏ đến commit đã được phê duyệt và dùng để build artifact. Không di chuyển tag đã công bố để thay đổi nội dung release một cách âm thầm.

### 10.6 Reproducible build

Build cùng source, toolchain và dependency nên tạo artifact có thể xác minh. Ghi commit, tool versions, dependency lock và build metadata.

## 11. Release gates: điều kiện để được phát hành

Release gate là tiêu chí phải đạt trước khi publish hoặc rollout.

### 11.1 Functional gate

Các behavior được cam kết phải hoạt động theo acceptance criteria. Compiler và runtime cần xử lý các use case chính.

### 11.2 Test gate

Chạy các suite phù hợp: unit, parser, semantic, golden, integration, runtime và regression.

### 11.3 Compatibility gate

Kiểm tra:

- Source DSL cũ có tiếp tục chạy không?
- API/host/plugin contract có thay đổi không?
- Persisted workflow state có đọc được không?
- Configuration cũ có còn hợp lệ không?
- Migration guide đã sẵn sàng chưa?

### 11.4 Security gate

Xem xét dependency, secret, permission, signing, vulnerability và thay đổi capability.

### 11.5 Performance gate

Đánh giá compile time, memory, runtime latency, throughput và resource consumption ở workload đại diện.

### 11.6 Documentation gate

Tutorial, reference, release notes, deprecation notice và migration guide cần khớp với behavior sẽ phát hành.

### 11.7 Operational gate

Xác nhận monitoring, alert, deployment procedure, rollback path và người trực hỗ trợ.

### 11.8 Approval

Gate cần có kết quả và owner. Không coi việc pipeline màu xanh là thay thế cho đánh giá rủi ro hoặc phê duyệt được yêu cầu.

## 12. Release candidate và beta program

Release candidate (RC) là artifact gần với release chính thức, được dùng để kiểm tra cuối.

### 12.1 RC numbering

Ví dụ:

~~~text
4.2.0-alpha.1
4.2.0-beta.1
4.2.0-rc.1
4.2.0-rc.2
4.2.0
~~~

Nếu RC có lỗi cần sửa, tạo RC mới và giữ lại metadata của RC cũ.

### 12.2 Beta users

Chọn nhóm người dùng có use case đại diện, có khả năng cung cấp feedback và chấp nhận mức ổn định của beta.

### 12.3 Feedback loop

Thu thập issue, crash, compatibility report và mức độ sử dụng feature. Phân loại bug, usability issue và request.

### 12.4 RC criteria

Định nghĩa điều kiện RC được promote: không còn lỗi blocker, test gate đạt, compatibility được xác nhận và tài liệu sẵn sàng.

### 12.5 Không dùng beta như production guarantee

Nêu rõ support level, dữ liệu có thể cần migrate lại và giới hạn của pre-release.

## 13. Phát hành thành phần DSL đồng bộ

Một DSL platform có nhiều artifact phụ thuộc lẫn nhau.

### 13.1 Compiler và runtime

Compiler có thể generate IR hoặc bytecode mà runtime phải hiểu. Release cần kiểm tra compatibility giữa producer và consumer.

### 13.2 Plugin SDK và host

Plugin SDK cần công bố API level và host version được hỗ trợ. Host mới có thể giữ compatibility với plugin cũ trong một support window.

### 13.3 CLI và Language Server

CLI và Language Server có thể dùng chung compiler library nhưng có cadence riêng. Cần bảo đảm protocol và capability negotiation phù hợp.

### 13.4 Standard library

Thêm hoặc đổi built-in function có thể ảnh hưởng name resolution, overload và runtime behavior. Cần release notes và language version policy.

### 13.5 Documentation và examples

Ví dụ cần được kiểm tra với version phát hành. Một syntax mới không nên xuất hiện trong tutorial chính thức trước khi compiler stable hỗ trợ, trừ khi tài liệu được đánh dấu preview.

### 13.6 Artifact manifest

Release manifest có thể ghi version, checksum, signature, source revision, dependency và compatibility range.

## 14. Migration và deprecation trong lịch phát hành

Breaking change cần có lộ trình chuyển đổi.

### 14.1 Introduce

Đưa API hoặc syntax mới vào version có thể chạy song song với dạng cũ.

### 14.2 Deprecate

Đánh dấu phần cũ deprecated, phát diagnostic hoặc warning phù hợp và cung cấp hướng dẫn thay thế.

### 14.3 Migration window

Cho người dùng thời gian cập nhật source, plugin và host integration. Độ dài phụ thuộc mức độ ảnh hưởng và support policy.

### 14.4 Migration tool

Nếu có thể, cung cấp codemod hoặc command tự động chuyển syntax/configuration. Tool cần preview diff và không ghi đè dữ liệu mà không có kiểm soát.

### 14.5 Remove

Chỉ xóa API/syntax cũ theo major version hoặc mốc đã công bố. Nêu rõ version cuối cùng hỗ trợ và cách xử lý source cũ.

### 14.6 Persisted state

Workflow đang chạy hoặc AST/IR được lưu có thể tồn tại qua nhiều release. Cần migration hoặc reader compatibility để không làm mất process state.

## 15. Release notes và truyền thông

Release notes giúp người dùng hiểu điều gì thay đổi và cần hành động gì.

### 15.1 Cấu trúc release notes

Một mẫu thường gồm:

- Highlights.
- New features.
- Improvements.
- Bug fixes.
- Breaking changes.
- Deprecations.
- Security fixes.
- Migration steps.
- Known issues.
- Supported versions/platforms.

### 15.2 Viết theo tác động người dùng

Mô tả thay đổi và hệ quả thực tế. Ví dụ, thay vì chỉ ghi "Parser refactored", hãy nói grammar nào được hỗ trợ, diagnostic nào thay đổi và người dùng có cần sửa source không.

### 15.3 Migration guide

Với breaking change, cung cấp ví dụ before/after, cách phát hiện source cũ, command migration và cách kiểm tra kết quả.

### 15.4 Thông báo trước

Thông báo deprecation và sunset đủ sớm để người dùng có thể lên kế hoạch.

### 15.5 Kênh truyền thông

Chọn kênh phù hợp như changelog, release page, email thông báo sản phẩm, developer portal hoặc in-product notice. Đảm bảo owner và thời điểm cập nhật nhất quán.

## 16. Rollout và progressive delivery

Không phải release nào cũng cần bật cho tất cả người dùng ngay lập tức.

### 16.1 Internal rollout

Triển khai cho nhóm nội bộ để xác nhận artifact và telemetry.

### 16.2 Canary

Mở cho một nhóm nhỏ tenant hoặc traffic. Theo dõi error rate, latency, crash và business outcome.

### 16.3 Percentage rollout

Tăng tỷ lệ người dùng theo từng bước, nếu metric nằm trong ngưỡng chấp nhận.

### 16.4 Ring deployment

Có thể chia ring:

1. Internal.
2. Early adopters.
3. Small production cohort.
4. General availability.

### 16.5 Feature flag

Feature flag cho phép tách deploy code khỏi việc bật tính năng. Flag cần owner, default, scope và ngày xem xét loại bỏ.

### 16.6 Tenant-specific rollout

Với DSL platform multi-tenant, có thể rollout theo tenant hoặc workspace. Cần bảo đảm flag và configuration không rò rỉ giữa tenant.

### 16.7 Promotion criteria

Mỗi bước rollout cần metric và thời gian quan sát rõ. Không tăng traffic chỉ vì chưa thấy alert trong vài phút nếu workload cần thời gian dài hơn để bộc lộ lỗi.

## 17. Monitoring sau phát hành

Release chưa kết thúc khi artifact được publish.

### 17.1 Technical metrics

Theo dõi:

- Compiler success/failure rate.
- Parse và compile latency.
- Runtime error và timeout rate.
- Memory/CPU consumption.
- Queue depth và worker utilization.
- Plugin load failures.
- API latency và error rate.
- Crash hoặc restart count.

### 17.2 User-impact metrics

Đo tỷ lệ workflow hoàn thành, số project cần migration, tần suất diagnostic mới, tỷ lệ rollback và support ticket liên quan.

### 17.3 Error budget

Nếu tổ chức dùng SLO/error budget, release có thể bị hạn chế khi độ tin cậy thấp hơn mục tiêu. Chính sách cần nêu ai quyết định và điều kiện mở lại phát hành.

### 17.4 Alert ownership

Mỗi alert cần owner và runbook. Alert không có người xử lý chỉ tạo thêm nhiễu.

### 17.5 Feedback window

Định nghĩa khoảng thời gian quan sát trước khi kết luận rollout ổn định. Với workload định kỳ, cần quan sát đủ chu kỳ nghiệp vụ.

## 18. Rollback và forward fix

Khi release gây lỗi, nhóm cần chọn cách phục hồi.

### 18.1 Rollback

Quay lại artifact hoặc version trước nếu nó còn tương thích với dữ liệu và trạng thái hiện tại.

### 18.2 Forward fix

Phát hành bản sửa mới khi rollback không an toàn hoặc schema đã thay đổi.

### 18.3 Database và persisted state

Rollback binary không tự động hoàn tác migration dữ liệu. Cần biết migration có thể đảo ngược hay cần forward migration.

### 18.4 DSL source compatibility

Nếu compiler mới đã chấp nhận syntax mới và người dùng đã lưu source đó, rollback compiler cũ có thể không parse được. Cần kiểm tra language version và migration.

### 18.5 Runtime side effects

Rollback không thể tự hoàn tác email, payment hoặc event đã phát. Có thể cần compensation và reconciliation.

### 18.6 Rollback trigger

Định nghĩa trước ngưỡng như crash rate, data integrity error, workflow failure hoặc security indicator. Quyết định rollback cần được ghi lại.

### 18.7 Diễn tập rollback

Thử rollback trong staging hoặc môi trường kiểm thử để biết thời gian, dependency và giới hạn thực tế.

## 19. Hotfix và security release

Một số lỗi không thể chờ release train kế tiếp.

### 19.1 Khi cần hotfix

- Lỗ hổng bảo mật đang bị khai thác.
- Mất hoặc hỏng dữ liệu.
- Runtime không thể thực hiện workload trọng yếu.
- Regression ảnh hưởng rộng.
- Compatibility break nghiêm trọng.

### 19.2 Quy trình rút gọn

Hotfix vẫn cần:

1. Xác định phạm vi và severity.
2. Chọn branch/version bị ảnh hưởng.
3. Tạo fix nhỏ nhất có thể.
4. Chạy test tập trung và regression liên quan.
5. Review/approval theo quy trình khẩn cấp.
6. Build và ký artifact.
7. Triển khai có kiểm soát.
8. Theo dõi và thông báo.

### 19.3 Patch nhiều nhánh

Nếu nhiều version còn được hỗ trợ, xác định nhánh nào cần patch. Không giả định fix cho version mới tự động áp dụng an toàn cho nhánh cũ.

### 19.4 Security advisory

Thông báo cần nêu affected versions, severity, mitigation, fixed versions và hành động người dùng cần thực hiện theo policy công bố.

### 19.5 Post-hotfix review

Sau khi xử lý khẩn cấp, quay lại quy trình review đầy đủ, bổ sung test và ghi nhận lý do quy trình thông thường không phát hiện vấn đề.

## 20. Support window và end of life

Mỗi version cần vòng đời hỗ trợ rõ.

### 20.1 Support status

Có thể dùng các trạng thái:

- Current: phiên bản hiện hành.
- Maintenance: chỉ nhận bug/security fix.
- LTS: được hỗ trợ dài hạn.
- Deprecated: còn hoạt động nhưng đã có kế hoạch thay thế.
- End of Support: không còn nhận hỗ trợ thông thường.
- End of Life: không còn được phát hành hoặc duy trì.

### 20.2 Support policy

Nêu rõ thời gian hỗ trợ, loại patch được cung cấp, mức hỗ trợ và cách nhận hỗ trợ.

### 20.3 EOL notice

Thông báo phiên bản bị ngừng hỗ trợ, ngày hiệu lực, version thay thế và hướng dẫn nâng cấp.

### 20.4 Legacy source

Nếu language version cũ không còn được compiler mới hỗ trợ, cần cung cấp migration path hoặc compiler compatibility window.

### 20.5 Extended support

Có thể có hỗ trợ mở rộng theo hợp đồng, nhưng cần phân biệt rõ với support mặc định.

## 21. Quản lý rủi ro trong lịch phát hành

Rủi ro cần được xem xét xuyên suốt planning và rollout.

### 21.1 Compatibility risk

Thay đổi syntax, AST, host API, plugin contract hoặc persisted schema có thể phá consumer.

### 21.2 Integration risk

Các module phát hành không đồng bộ có thể tạo tổ hợp version không được hỗ trợ.

### 21.3 Security risk

Dependency, plugin signing, permission hoặc runtime isolation có thể thay đổi.

### 21.4 Operational risk

Deployment, migration, monitoring hoặc rollback có thể chưa sẵn sàng.

### 21.5 Capacity risk

Release có thể tăng CPU/memory, queue hoặc API load.

### 21.6 Mitigation

Với mỗi rủi ro, ghi likelihood, impact, owner, mitigation, detection signal và fallback. Risk register cần được cập nhật khi có thông tin mới.

## 22. Trách nhiệm và phối hợp release

Một release liên quan nhiều nhóm.

| Vai trò | Trách nhiệm |
|---|---|
| Release manager | Điều phối lịch, scope, status và go/no-go |
| Product owner | Xác nhận giá trị và ưu tiên |
| Compiler/runtime owner | Chịu trách nhiệm behavior và technical readiness |
| QA/test owner | Cung cấp kết quả kiểm thử |
| Security owner | Đánh giá rủi ro và security gate |
| DevOps/platform | Build, signing, deployment và monitoring |
| Documentation owner | Release notes và migration guide |
| Support/customer success | Chuẩn bị hỗ trợ và thông báo người dùng |

### 22.1 Go/no-go meeting

Review scope, gate status, known issues, risk, rollout và rollback. Ghi rõ quyết định, người quyết định và action còn lại.

### 22.2 Escalation

Khi gate không đạt hoặc mốc trễ, xác định ai quyết định hoãn, giảm scope hay chấp nhận rủi ro theo policy.

### 22.3 Single release record

Giữ một release record chứa version, commit, artifact, checksum, test result, approvals, release notes và rollout status.

## 23. Release metrics và cải tiến cadence

Theo dõi metrics giúp đánh giá lịch có thực tế và sản phẩm có ổn định không.

| Metric | Ý nghĩa |
|---|---|
| Release frequency | Số lần phát hành trong một khoảng thời gian |
| Lead time for changes | Thời gian từ thay đổi được commit đến khi phát hành |
| Change failure rate | Tỷ lệ release gây incident hoặc rollback |
| Time to restore | Thời gian khôi phục sau release failure |
| Patch latency | Thời gian từ xác nhận lỗi đến bản vá |
| Adoption rate | Tỷ lệ người dùng nâng cấp lên version mới |
| Deprecation completion | Mức độ consumer đã rời API/version cũ |

Metrics cần được diễn giải theo context. Release frequency cao không tự động có nghĩa chất lượng tốt; release chậm cũng không tự động an toàn hơn.

### 23.1 Review cadence

Định kỳ xem xét:

- Release có thường xuyên trễ không?
- Code freeze có quá dài không?
- Có quá nhiều hotfix không?
- Người dùng có đủ thời gian migration không?
- Gate nào thường gây tắc nghẽn?
- Rollout có phát hiện lỗi đủ sớm không?

### 23.2 Thay đổi cadence

Nếu thay cadence, thông báo mốc mới, support policy và cách chuyển các release đã lên kế hoạch.

## 24. Những sai lầm thường gặp

### Lập lịch chỉ theo ngày

Calendar có ngày phát hành nhưng không có owner, dependency hoặc exit criteria.

**Cách khắc phục:** mỗi milestone có owner, deliverable và điều kiện hoàn thành.

### Nhồi feature vào release cuối kỳ

Thay đổi lớn được merge sát code freeze, không đủ thời gian integration.

**Cách khắc phục:** scope control, feature freeze và release train.

### Phát hành compiler mà quên runtime

Compiler tạo IR hoặc bytecode mới nhưng runtime production không hiểu.

**Cách khắc phục:** compatibility matrix và coordinated release.

### Coi release là deployment

Artifact được publish nhưng người dùng không biết version nào được bật hoặc hỗ trợ.

**Cách khắc phục:** tách release, deployment, rollout và promotion trong calendar.

### Không có migration window

Breaking change xuất hiện mà consumer không đủ thời gian nâng cấp.

**Cách khắc phục:** deprecation notice, migration guide và support window.

### Không chuẩn bị rollback

Rollback binary làm dữ liệu hoặc DSL source trở nên không tương thích.

**Cách khắc phục:** kiểm tra rollback cùng schema, persisted state và external side effects.

### Cập nhật release notes quá muộn

Người dùng không biết syntax, API hoặc behavior đã đổi.

**Cách khắc phục:** duy trì changelog trong quá trình phát triển và review trước publish.

### Hotfix thiếu kiểm tra

Fix khẩn cấp tạo regression ở nhánh cũ hoặc bỏ qua signing.

**Cách khắc phục:** quy trình emergency release có gate rút gọn nhưng được ghi nhận.

### Không theo dõi sau phát hành

Lỗi chỉ xuất hiện ở workload thật nhưng không có metric hoặc owner.

**Cách khắc phục:** rollout theo giai đoạn, alert và feedback window.

## 25. Quy trình xây dựng lịch phát hành

Khi lập lịch cho một phiên bản DSL, có thể thực hiện:

1. **Xác định mục tiêu:** phiên bản mang lại giá trị gì?
2. **Chốt phạm vi:** feature, fix, migration và phần loại trừ.
3. **Phân tích dependency:** compiler, runtime, plugin, editor, host và docs.
4. **Chọn cadence:** fixed, release train, continuous hoặc LTS.
5. **Đặt mốc:** planning, feature complete, freeze, RC, approval, publish và rollout.
6. **Gán owner:** mỗi deliverable và gate có người chịu trách nhiệm.
7. **Đánh giá compatibility:** language, API, plugin, schema và persisted state.
8. **Lập test plan:** functional, regression, security, performance và integration.
9. **Chuẩn bị migration:** deprecation, tool và support window.
10. **Chuẩn bị release artifacts:** version, tag, checksum, signature và manifest.
11. **Chuẩn bị truyền thông:** release notes, known issues và migration guide.
12. **Định nghĩa rollout:** canary, rings, feature flags và promotion criteria.
13. **Định nghĩa rollback:** trigger, owner, artifact và dữ liệu liên quan.
14. **Theo dõi:** metrics, alerts, support feedback và incident.
15. **Review cadence:** ghi nhận điều cần cải thiện cho chu kỳ sau.

## 26. Ví dụ tổng hợp: lịch phát hành DSL Platform 4.2

Giả sử nền tảng chuẩn bị phát hành version 4.2 với một cú pháp rule mới, diagnostics cải tiến và host API bổ sung.

### 26.1 Scope

- Thêm cú pháp pattern matching.
- Cải thiện source range cho diagnostics.
- Bổ sung host function read-only.
- Cập nhật CLI và Language Server.
- Bổ sung migration guide cho language version mới.

### 26.2 Dependency

~~~text
Grammar update
     |
     v
Parser / AST
     |
     v
Semantic analysis
     |
     +------> Diagnostics
     |
     v
Compiler backend
     |
     +------> Runtime compatibility
     |
     +------> CLI / Language Server
     |
     v
Documentation and examples
~~~

### 26.3 Calendar

| Mốc | Thời điểm minh họa | Exit criteria |
|---|---|---|
| Planning | Tuần 1 | Scope và owner được xác nhận |
| Feature complete | Tuần 4 | Feature chính được tích hợp |
| Code freeze | Tuần 5 | Chỉ nhận fix được phê duyệt |
| RC1 | Tuần 5 | Artifact được build và ký |
| RC validation | Tuần 6 | Test, compatibility và security gate đạt |
| GA | Cuối tuần 6 | Go/no-go được thông qua |
| Canary | Sau GA | Metrics trong ngưỡng |
| General rollout | Sau canary | Không có blocker mới |

### 26.4 Compatibility

Compiler 4.2 hỗ trợ language version cũ và mới. Runtime API level được công bố. Plugin API giữ compatibility với version được hỗ trợ; host function mới chỉ xuất hiện khi capability được cấp.

### 26.5 Release gates

Chạy parser, semantic, golden, runtime integration, plugin compatibility và security checks. Generated artifacts được kiểm tra với runtime tương ứng.

### 26.6 Rollout

Triển khai nội bộ, sau đó một nhóm tenant beta, rồi canary production. Theo dõi compile error rate, runtime failure, latency và host API permission denial.

### 26.7 Rollback

Nếu compiler mới tạo IR không tương thích, dừng rollout và chuyển traffic về compiler/runtime pair trước đó. Kiểm tra source đã dùng syntax mới và persisted workflow state trước khi rollback.

### 26.8 Maintenance

Sau GA, theo dõi issue, phát hành patch khi cần và cập nhật support matrix. Công bố thời điểm deprecate language construct cũ nếu có.

## 27. Câu hỏi tự kiểm tra

1. Lịch phát hành là gì và vì sao DSL platform cần lịch rõ ràng?
2. Fixed cadence, release train và continuous delivery khác nhau như thế nào?
3. Phân biệt release, deployment, rollout, promotion và rollback.
4. Các giai đoạn chính của vòng đời một release là gì?
5. Planning cần xác định scope, dependency và owner như thế nào?
6. Release calendar cần có thông tin nào ngoài ngày phát hành?
7. Product version, language version, runtime API level và plugin API level khác nhau ra sao?
8. SemVer phân loại breaking, feature và patch như thế nào?
9. Feature freeze và code freeze có mục đích gì?
10. Release branch và tag hỗ trợ phát hành như thế nào?
11. Release gate cần kiểm tra functional, test, compatibility, security và operation ra sao?
12. Release candidate và beta program giúp giảm rủi ro như thế nào?
13. Vì sao compiler, runtime, plugin SDK và editor cần phối hợp release?
14. Deprecation và migration window nên được đưa vào lịch như thế nào?
15. Release notes cần nêu những thay đổi nào?
16. Canary và progressive rollout hoạt động ra sao?
17. Những metric nào cần theo dõi sau phát hành?
18. Khi nào nên rollback và khi nào nên forward fix?
19. Hotfix cần giữ những kiểm soát tối thiểu nào?
20. Support window và end-of-life policy ảnh hưởng người dùng ra sao?
21. Những metric nào giúp đánh giá cadence có phù hợp không?
22. Một release plan cần có những exit criteria nào?

Lịch phát hành biến việc đưa phiên bản DSL đến người dùng thành một quy trình có thể dự đoán và điều phối. Khi scope, dependency, versioning, freeze, release gates, migration, rollout, rollback và support window được lập kế hoạch rõ, các nhóm có thể phát hành thường xuyên mà vẫn bảo vệ tính tương thích, dữ liệu và độ tin cậy của nền tảng.
