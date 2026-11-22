# Thống nhất trách nhiệm giữa phát triển, kiểm thử, bảo mật và vận hành

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao chất lượng và khả năng phát hành là trách nhiệm chung của nhiều vai trò.
- Xác định trách nhiệm của phát triển, kiểm thử, bảo mật và vận hành trong từng giai đoạn CI/CD.
- Phân biệt người thực hiện công việc, người chịu trách nhiệm cuối cùng, người được tham vấn và người cần được thông báo.
- Thiết kế ma trận RACI và quyền quyết định cho thay đổi, quality gate, release và incident.
- Đưa kiểm thử, bảo mật và yêu cầu vận hành vào sớm trong quá trình phát triển.
- Thiết kế quality gate có owner, tiêu chí, bằng chứng và quy trình xử lý ngoại lệ.
- Tổ chức release readiness, bàn giao thông tin và xác minh sau triển khai.
- Phối hợp xử lý sự cố, rollback và cải tiến sau incident mà không tạo ra các silo trách nhiệm.

## 1. Vì sao cần thống nhất trách nhiệm?

Một thay đổi phần mềm đi qua nhiều nhóm: developer viết code, QA kiểm thử, security đánh giá rủi ro, operations triển khai và duy trì dịch vụ. Nếu mỗi nhóm chỉ hoàn thành phần việc riêng rồi chuyển trách nhiệm sang nhóm kế tiếp, các khoảng trống dễ xuất hiện.

Ví dụ:

- Developer cho rằng QA sẽ tìm mọi lỗi trước khi release.
- QA chỉ kiểm tra theo test case được giao, không có quyền yêu cầu sửa các rủi ro kiến trúc.
- Security chỉ được mời review ngay trước production nên phát hiện vấn đề quá muộn.
- Operations nhận artifact nhưng thiếu hướng dẫn cấu hình, dashboard hoặc rollback.
- Khi release gây sự cố, các nhóm tranh luận ai phải xử lý thay vì cùng khôi phục dịch vụ.

CI/CD rút ngắn thời gian từ thay đổi đến phát hành, nhưng tốc độ chỉ có ý nghĩa khi các vai trò phối hợp đúng lúc. Một pipeline tự động không tự xác định ai chịu trách nhiệm về tiêu chí kiểm thử, ai phê duyệt rủi ro, ai quản lý production và ai quyết định dừng rollout.

Mục tiêu là tạo **một chuỗi trách nhiệm liên tục từ lúc hình thành thay đổi đến khi dịch vụ được vận hành ổn định**. Mỗi hoạt động cần có owner, tiêu chí hoàn tất, bằng chứng và đường xử lý khi không đạt.

Trách nhiệm chung không có nghĩa mọi người cùng chịu trách nhiệm một cách mơ hồ. Mỗi quyết định quan trọng vẫn cần một người hoặc vai trò chịu trách nhiệm cuối cùng, cùng các vai trò thực hiện và tham vấn phù hợp.

## 2. Bốn nhóm vai trò chính

Tên nhóm và cách tổ chức có thể khác nhau giữa các công ty. Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ; điều quan trọng là năng lực và quyền quyết định được xác định rõ.

### 2.1. Phát triển (Development)

Development chịu trách nhiệm thiết kế và xây dựng thay đổi phần mềm có thể kiểm tra, triển khai và bảo trì.

Trách nhiệm thường gồm:

- Làm rõ yêu cầu kỹ thuật và hành vi mong muốn.
- Thiết kế code, API, schema và tương tác với dependency.
- Viết unit test, component test và kiểm tra phù hợp ở cấp code.
- Review code và xử lý finding từ test, scan hoặc review.
- Khai báo dependency, cấu hình và migration.
- Tạo artifact có thể tái lập và truy vết về source revision.
- Cung cấp thông tin thay đổi, giới hạn, feature flag và rủi ro đã biết.
- Hỗ trợ điều tra và sửa lỗi khi release gây ảnh hưởng.

Developer không chỉ chịu trách nhiệm làm cho code compile. Họ cần hiểu thay đổi ảnh hưởng đến dữ liệu, bảo mật, hiệu năng và khả năng vận hành như thế nào.

### 2.2. Kiểm thử và đảm bảo chất lượng (QA)

QA giúp xác định sản phẩm có đáp ứng yêu cầu và rủi ro đã được kiểm soát hay chưa. QA không phải nhóm duy nhất chịu trách nhiệm về chất lượng.

Trách nhiệm thường gồm:

- Xây dựng chiến lược kiểm thử dựa trên rủi ro.
- Xác định phạm vi, dữ liệu và môi trường test.
- Thiết kế test case, exploratory test và test tự động.
- Kiểm tra luồng nghiệp vụ, integration, regression và compatibility.
- Đánh giá độ tin cậy của test suite và flaky test.
- Phân tích failure, phân biệt lỗi sản phẩm với lỗi môi trường.
- Cung cấp test report và khuyến nghị release readiness.
- Tham gia xác minh sau deploy và kiểm tra lỗi thực tế.

QA cần được tham gia từ lúc làm rõ yêu cầu và thiết kế, thay vì chỉ nhận một build gần ngày phát hành. QA cũng cần quyền nêu rủi ro và yêu cầu bằng chứng, nhưng tiêu chí chấp nhận cuối cùng phải được xác định cùng product owner và các bên liên quan.

### 2.3. Bảo mật (Security)

Security giúp nhận diện và giảm rủi ro bảo mật trong source, dependency, hạ tầng, quy trình build và môi trường chạy.

Trách nhiệm thường gồm:

- Tư vấn threat modeling và security requirements.
- Xác định baseline cho SAST, SCA, secret scanning, IaC và image scanning.
- Định nghĩa severity, remediation SLA và exception policy.
- Review các thay đổi có rủi ro cao như authentication, authorization, crypto hoặc xử lý dữ liệu nhạy cảm.
- Hướng dẫn quản lý secret, identity và quyền tối thiểu.
- Xác minh provenance, artifact integrity và chuỗi cung ứng phần mềm.
- Hỗ trợ incident liên quan đến lỗ hổng hoặc compromise.
- Theo dõi rủi ro tồn đọng và thời hạn xử lý.

Security không thể tự kiểm tra mọi dòng code thay cho developer. Developer chịu trách nhiệm sửa lỗi trong phần mình xây dựng; security định nghĩa chuẩn, tư vấn và xác minh các rủi ro cần chuyên môn hoặc quyền độc lập.

### 2.4. Vận hành và nền tảng (Operations/Platform)

Operations và platform giúp phần mềm được triển khai, quan sát, mở rộng và phục hồi trong môi trường thực tế.

Trách nhiệm thường gồm:

- Quản lý môi trường, network, compute, storage và deployment platform.
- Cung cấp pipeline runner, identity và cơ chế secret an toàn.
- Định nghĩa deployment strategy, approval và change control.
- Xây dựng monitoring, logging, tracing, alert và dashboard.
- Xác định SLI/SLO, capacity và giới hạn tài nguyên.
- Quản lý backup, restore, rollback và disaster recovery.
- Xác minh readiness, health và trạng thái sau deploy.
- Điều phối incident và đảm bảo runbook có thể sử dụng.
- Phản hồi về khả năng vận hành ngay từ giai đoạn thiết kế.

Operations không nên là nhóm phải đoán cách chạy ứng dụng sau khi nhận artifact. Developer cần cung cấp yêu cầu runtime và thông tin thay đổi; platform/operations cung cấp nền tảng và ràng buộc vận hành.

## 3. Trách nhiệm chung và quyền quyết định riêng

Một số hoạt động cần nhiều nhóm cùng tham gia, nhưng quyền quyết định phải rõ.

Ví dụ:

- Developer thực hiện sửa lỗi code.
- QA xác định test evidence có đủ theo chiến lược kiểm thử hay không.
- Security xác định finding có vi phạm policy hoặc cần exception hay không.
- Operations xác nhận môi trường, capacity và khả năng phục hồi đáp ứng điều kiện deploy.
- Release owner hoặc người có thẩm quyền phát hành quyết định có tiếp tục dựa trên bằng chứng và risk acceptance.

Một nhóm có thể đưa ra khuyến nghị dừng release, nhưng cần quy định ai có quyền block theo policy và ai có quyền chấp nhận ngoại lệ. Không nên để một cá nhân tự bỏ qua kiểm soát bắt buộc chỉ vì deadline.

Có thể phân loại quyền:

| Loại quyền | Ví dụ | Cách quản lý |
|---|---|---|
| Thực hiện (execute) | Sửa code, chạy test, triển khai | Cấp theo job, môi trường và phạm vi |
| Đánh giá (review) | Review code, test result, security finding | Xác định reviewer có chuyên môn |
| Phê duyệt (approve) | Chấp nhận release hoặc exception | Gắn với policy và audit |
| Chặn (block) | Chặn gate khi điều kiện bắt buộc không đạt | Quy định rõ trigger và cách gỡ |
| Điều phối (coordinate) | Điều phối release hoặc incident | Chỉ định release owner/incident commander |
| Chấp nhận rủi ro (risk accept) | Chấp nhận finding còn tồn tại | Có owner, lý do, phạm vi và expiry |

Tách quyền giúp tránh xung đột lợi ích. Ví dụ người tạo thay đổi production không nên là người duy nhất phê duyệt thay đổi đó nếu policy yêu cầu review độc lập.

## 4. Dùng RACI để làm rõ trách nhiệm

RACI là cách mô tả vai trò tham gia vào từng hoạt động:

- **R — Responsible:** người trực tiếp thực hiện.
- **A — Accountable:** người chịu trách nhiệm cuối cùng và bảo đảm hoạt động hoàn tất.
- **C — Consulted:** người cần được tham vấn trước quyết định hoặc thực hiện.
- **I — Informed:** người cần được thông báo kết quả.

Một hoạt động nên có một vai trò A rõ ràng. Có thể có nhiều R và C, nhưng nếu không ai là A thì công việc dễ bị bỏ sót; nếu quá nhiều A thì quyền quyết định trở nên mơ hồ.

Ví dụ ma trận tham khảo:

| Hoạt động | Development | QA | Security | Operations | Release owner |
|---|---|---|---|---|---|
| Làm rõ yêu cầu và acceptance criteria | R | C | C | C | A |
| Thiết kế kỹ thuật và API | A/R | C | C | C | I |
| Unit/component test | A/R | C | C | I | I |
| Test strategy và regression | R | A | C | C | I |
| Threat model cho thay đổi rủi ro cao | R | C | A | C | I |
| Sửa security finding trong code | A/R | I | C | I | I |
| Security policy và exception review | C | I | A/R | C | I |
| Build và tạo artifact | A/R | C | C | C | I |
| Quản lý runner và deployment platform | C | I | C | A/R | I |
| Xác nhận release readiness | R | R | C | R | A |
| Phê duyệt production theo policy | C | C | C | C | A/R |
| Theo dõi sau deploy | R | C | C | A/R | I |
| Điều phối incident | R | C | C | R | A |
| Post-incident review | R | R | R | R | A |

Ma trận chỉ là điểm bắt đầu. Tổ chức cần điều chỉnh theo cấu trúc thật, phân loại hệ thống và chính sách nội bộ. Với hoạt động có rủi ro bảo mật hoặc dữ liệu cao, có thể cần một approval độc lập ngoài các vai trò trong bảng.

RACI không thay thế quy trình ra quyết định. Nó cần được gắn với tài liệu mô tả tiêu chí hoàn tất, quyền block, người thay thế khi vắng mặt và cách xử lý bất đồng.

## 5. Phối hợp từ giai đoạn yêu cầu và thiết kế

Phối hợp hiệu quả bắt đầu trước khi có pull request.

Khi một thay đổi được đề xuất, các nhóm nên cùng làm rõ:

- Hành vi nào sẽ thay đổi?
- Người dùng hoặc hệ thống nào bị ảnh hưởng?
- Có thay đổi API, event, schema hoặc dữ liệu không?
- Có dữ liệu nhạy cảm hoặc quyền mới không?
- Cần test ở những lớp nào?
- Có yêu cầu về latency, throughput, availability hoặc capacity không?
- Có thể triển khai dần hoặc dùng feature flag không?
- Nếu thất bại, có thể rollback hay cần forward fix?
- Cần dashboard, alert hoặc runbook mới không?

Developer chịu trách nhiệm đề xuất thiết kế kỹ thuật. QA đóng góp testability và acceptance criteria. Security xác định threat và control cần có. Operations đánh giá runtime, capacity và recovery.

Không cần tổ chức cuộc họp lớn cho mọi thay đổi. Có thể dùng checklist trong ticket, template pull request hoặc review bất đồng bộ. Chỉ các thay đổi có rủi ro cao mới cần design review liên chức năng.

## 6. Shift-left: đưa kiểm thử và bảo mật vào sớm

Shift-left có nghĩa là phát hiện vấn đề ở giai đoạn sớm khi chi phí sửa thường thấp hơn và phạm vi ảnh hưởng nhỏ hơn.

Ví dụ:

- QA tham gia viết acceptance criteria trước khi code hoàn tất.
- Developer viết unit test cùng thay đổi.
- Security review threat model khi thiết kế authentication hoặc data flow.
- IaC scan chạy khi pull request thay đổi hạ tầng.
- Secret scan chạy trước khi code được merge.
- Dependency policy được kiểm tra trước khi artifact được publish.
- Operations review yêu cầu logging, metrics và rollback trước production.

Shift-left không có nghĩa chuyển toàn bộ trách nhiệm của QA hoặc security sang developer. Nó giúp các chuyên môn tham gia đúng thời điểm và đưa tiêu chí của họ vào workflow.

Một số kiểm soát nên tự động hóa trong CI:

- Lint và static analysis.
- Unit và component test.
- Dependency và secret scanning.
- IaC validation.
- License policy.
- Container image scan.
- Contract test.
- Build reproducibility hoặc provenance check.

Các đánh giá cần phán đoán chuyên môn như threat modeling, usability, risk acceptance hoặc kiến trúc phục hồi vẫn cần con người tham gia.

## 7. Đặt quality gate với owner và bằng chứng rõ ràng

Quality gate là điều kiện phải đạt trước khi pipeline chuyển sang bước tiếp theo. Gate chỉ có giá trị khi biết:

- Tiêu chí là gì?
- Ai sở hữu tiêu chí?
- Bằng chứng nào chứng minh đã đạt?
- Khi nào gate được đánh giá?
- Nếu không đạt thì ai xử lý?
- Có ngoại lệ không và ai phê duyệt?

Ví dụ:

| Gate | Owner chính | Bằng chứng |
|---|---|---|
| Code review | Development | Approval và review status |
| Unit test | Development | Test report và commit SHA |
| Regression/integration test | QA | Test report, scope và environment |
| Security baseline | Security | Scanner report, policy revision |
| Artifact integrity | Platform/Security | Digest, provenance và signature |
| Capacity/readiness | Operations | Capacity check, health và rollout plan |
| Release readiness | Release owner | Gate summary và risk record |
| Post-deploy verification | Operations cùng Development/QA | Runtime metrics, smoke test và deployment record |

Gate phải phân biệt failure với missing evidence. Nếu scanner không chạy, không thể kết luận không có finding. Nếu test report thuộc commit cũ, không thể dùng nó cho commit hiện tại.

Nên lưu policy version, report ID và quyết định gate để có thể truy vết sau này.

## 8. Xử lý ngoại lệ và risk acceptance

Không phải mọi finding đều có thể sửa ngay. Một số trường hợp cần exception có kiểm soát, nhưng exception không nên là cách bỏ qua gate thường xuyên.

Một request exception nên nêu:

- Finding hoặc điều kiện không đạt.
- Hệ thống và phiên bản bị ảnh hưởng.
- Lý do chưa thể xử lý.
- Mức độ rủi ro và tác động.
- Biện pháp giảm thiểu tạm thời.
- Người chịu trách nhiệm khắc phục.
- Thời hạn hết hiệu lực.
- Người có quyền chấp nhận rủi ro.
- Bằng chứng và quyết định phê duyệt.

Security finding cần được chấp nhận bởi vai trò có thẩm quyền theo policy, không chỉ bởi developer của thay đổi. Rủi ro availability hoặc capacity cần có operations owner tham gia. Ngoại lệ phải có expiry và được đánh giá lại khi scope thay đổi.

Không nên dùng một approval chung để bỏ qua nhiều gate không liên quan. Mỗi exception cần có phạm vi rõ ràng.

## 9. Trách nhiệm trong pull request và code review

Pull request là điểm phối hợp quan trọng giữa developer, QA, security và đôi khi operations.

Một pull request tốt nên mô tả:

- Vấn đề và hành vi mong muốn.
- Phạm vi thay đổi.
- API/schema/event thay đổi.
- Test đã chạy và kết quả.
- Migration hoặc data impact.
- Security considerations.
- Cấu hình và secret mới nếu có.
- Monitoring/alert cần cập nhật.
- Cách triển khai và rollback.
- Feature flag hoặc rollout strategy.

Reviewer cần tập trung vào trách nhiệm chuyên môn:

- Developer review logic, maintainability và compatibility.
- QA review test coverage, edge cases và acceptance behavior.
- Security review threat và control liên quan.
- Operations/platform review ảnh hưởng runtime hoặc hạ tầng khi cần.

Không phải mọi pull request đều cần bốn nhóm phê duyệt. Dựa trên risk classification để chọn reviewer phù hợp. Tuy nhiên, policy bắt buộc như code owner, protected branch hoặc security approval cần được thực thi tự động, không dựa vào trí nhớ của người tạo PR.

## 10. Trách nhiệm khi xây dựng và vận hành pipeline

Pipeline cũng là một phần của hệ thống sản xuất. Thay đổi workflow có thể mở quyền, bỏ gate hoặc làm sai artifact.

Development/platform cần phối hợp để xác định:

- Workflow nào do project sở hữu, workflow nào do platform sở hữu?
- Ai được sửa reusable workflow?
- Job nào được cấp quyền đọc source, ghi registry hoặc deploy?
- Runner nào được dùng cho mã không tin cậy?
- Secret được cấp ở bước nào?
- Artifact và report được lưu ở đâu?
- Làm thế nào pin version của shared action/workflow?
- Ai xử lý khi runner hoặc registry gặp sự cố?

Security cần review thay đổi ảnh hưởng trust boundary, token permission, secret handling và provenance. Operations/platform chịu trách nhiệm năng lực runner, network, quota và độ sẵn sàng của nền tảng. Development chịu trách nhiệm cấu hình dự án và sửa pipeline riêng của repository trong phạm vi được phép.

Không nên cấp quyền production cho toàn bộ job chỉ vì một job cuối cần deploy. Tách validation, build, publish và deploy thành các job hoặc workflow có quyền tối thiểu.

## 11. Chuẩn bị release readiness

Release readiness là đánh giá tổng hợp trước khi phát hành. Đây không chỉ là việc nhìn thấy tất cả job màu xanh.

Một release readiness review cần xem:

- Source commit và pull request đã được review.
- Test bắt buộc đã chạy trên đúng source revision.
- Security scan đủ phạm vi và đúng policy revision.
- Artifact digest và provenance hợp lệ.
- Migration tương thích với phiên bản đang chạy.
- Cấu hình môi trường đã validate.
- Deployment strategy phù hợp với năng lực nền tảng.
- Capacity và change window đã được xác nhận.
- Dashboard, alert và runbook đã sẵn sàng.
- Rollback hoặc recovery plan có thể thực hiện.
- Owner và người trực hỗ trợ đã được xác định.
- Các exception còn hiệu lực và có risk acceptance.

Một release có thể đạt tất cả automated checks nhưng vẫn chưa sẵn sàng nếu không có người trực, thiếu capacity hoặc thay đổi database không có recovery plan.

Release owner tổng hợp bằng chứng và điều phối quyết định. Các nhóm chuyên môn xác nhận phần trách nhiệm của mình, còn quyền phê duyệt cuối cùng tuân theo chính sách của tổ chức.

## 12. Bàn giao từ phát triển sang vận hành

Bàn giao không nên chỉ là gửi link artifact. Operations cần đủ thông tin để triển khai, quan sát và xử lý sự cố.

Một deployment handoff nên bao gồm:

- Release ID, source commit và artifact digest.
- Tóm tắt thay đổi và dependency mới.
- Config revision và secret reference cần thiết.
- Migration hoặc data change.
- Deployment strategy và rollout steps.
- Health endpoint và readiness criteria.
- Dashboard, alert và SLO liên quan.
- Runbook và thao tác thường gặp.
- Rollback/recovery constraints.
- Feature flag và kill switch.
- Owner kỹ thuật và kênh liên hệ.
- Known issues và exception còn tồn tại.

Developer cần giải thích hành vi ứng dụng và giới hạn đã biết. Operations/platform xác nhận môi trường có thể đáp ứng yêu cầu. QA có thể cung cấp test report và các luồng cần smoke test. Security cung cấp finding hoặc điều kiện còn phải theo dõi.

Bàn giao tốt giúp operations không phải reverse-engineer thay đổi ngay trong cửa sổ phát hành.

## 13. Theo dõi sau triển khai là trách nhiệm liên chức năng

Sau deploy, cần xác minh cả trạng thái kỹ thuật và hành vi nghiệp vụ.

Operations thường theo dõi:

- Instance readiness và restart.
- Error rate, latency và saturation.
- Queue lag và dependency health.
- Traffic distribution và rollout status.
- Alert và SLO.

Development hỗ trợ phân tích log, trace, code path và lỗi runtime. QA xác minh smoke test, critical user journey và regression có thể xảy ra trong môi trường thật. Security theo dõi các tín hiệu bất thường hoặc vấn đề bảo mật nếu release thay đổi bề mặt tấn công.

Cần thống nhất cửa sổ quan sát và điều kiện dừng rollout. Ví dụ, nếu error rate tăng vượt ngưỡng trong canary, pipeline pause hoặc abort theo policy. Người trực vận hành điều phối hành động; developer hỗ trợ xác định nguyên nhân và sửa lỗi.

Không nên kết thúc release chỉ vì deployment command thành công. Chỉ ghi nhận release hoàn tất khi trạng thái thực tế và các kiểm tra bắt buộc đã được xác minh.

## 14. Phối hợp trong incident và rollback

Khi production gặp sự cố, mục tiêu đầu tiên là bảo vệ người dùng và khôi phục dịch vụ. Phân tích trách nhiệm cá nhân không nên làm chậm containment.

Một mô hình incident có thể gồm:

- **Incident commander:** điều phối, xác định ưu tiên và phân công.
- **Operations/on-call:** đánh giá phạm vi, giảm tác động, điều khiển traffic và thực hiện runbook.
- **Development:** phân tích code, dependency và cung cấp fix.
- **QA:** hỗ trợ tái hiện, xác minh bản sửa và kiểm tra luồng quan trọng.
- **Security:** tham gia nếu có dấu hiệu compromise, lộ secret hoặc lỗ hổng.
- **Communications/product owner:** cập nhật stakeholder và quyết định tác động người dùng theo quy trình.

Quy trình tham khảo:

1. Xác nhận incident và chỉ định incident commander.
2. Xác định mức độ ảnh hưởng, dịch vụ và người dùng bị tác động.
3. Dừng rollout hoặc giới hạn traffic nếu cần.
4. Tắt feature flag, rollback artifact hoặc áp dụng mitigation phù hợp.
5. Kiểm tra dữ liệu và side effect; phục hồi riêng nếu cần.
6. Xác minh health và critical journey.
7. Cập nhật trạng thái cho stakeholder.
8. Thu thập timeline, quyết định và bằng chứng.
9. Tổ chức post-incident review và theo dõi action item.

Rollback không phải lúc nào cũng là lựa chọn đầu tiên. Nếu lỗi do dependency ngoài, config hoặc dữ liệu, rollback code có thể không giải quyết được. Quyết định cần dựa trên bằng chứng và khả năng tương thích.

## 15. Post-incident review và cải tiến hệ thống

Post-incident review nên tập trung vào cách hệ thống và quy trình cho phép sự cố xảy ra, được phát hiện và được xử lý.

Các câu hỏi hữu ích:

- Thay đổi nào kích hoạt sự cố?
- Kiểm soát nào đã phát hiện hoặc bỏ sót lỗi?
- Test environment có đại diện cho production không?
- Security hoặc operational review có được tham gia đúng lúc không?
- Pipeline có đủ bằng chứng và truy vết không?
- Có thể giảm blast radius bằng feature flag hoặc canary không?
- Runbook có đầy đủ và chính xác không?
- Quyền và trách nhiệm có rõ trong incident không?
- Điều gì làm chậm khôi phục?
- Cần thay đổi code, test, policy, pipeline hoặc vận hành?

Action item cần có owner, deadline, mức ưu tiên và cách xác minh hoàn tất. Không nên tạo danh sách việc chung chung như “cải thiện monitoring” mà không chỉ rõ metric, alert, service và người chịu trách nhiệm.

Một review tốt không nhằm tìm người để đổ lỗi. Nó tìm ra điều kiện hệ thống cần thay đổi để giảm xác suất hoặc tác động của sự cố tiếp theo.

## 16. Giao tiếp và nhịp phối hợp

Các nhóm cần có cách trao đổi thông tin phù hợp với mức rủi ro và tốc độ thay đổi.

Có thể dùng:

- Ticket hoặc change request cho mục tiêu, phạm vi và owner.
- Pull request cho thay đổi code và review.
- Pipeline report cho test, scan và artifact evidence.
- Release record cho quyết định phát hành.
- Runbook cho thao tác vận hành.
- Incident channel hoặc bridge cho sự cố đang diễn ra.
- Post-incident review cho bài học và action item.

Thông tin cần rõ và có thể truy lại. Tránh gửi một thông báo “đã deploy xong” mà không có release ID, môi trường, artifact digest hoặc kết quả xác minh.

Các cuộc họp nên tập trung vào quyết định cần nhiều bên tham gia: design review, risk review, release readiness hoặc incident review. Những thông tin có thể ghi nhận trong ticket hoặc report nên được trao đổi bất đồng bộ để giảm thời gian chờ.

## 17. Ví dụ: một thay đổi đi qua các vai trò

Giả sử nhóm phát triển thêm API hoàn tiền cho dịch vụ thanh toán.

**Giai đoạn yêu cầu và thiết kế**

- Development mô tả API, authorization và state transition.
- QA xác định acceptance criteria, test case cho hoàn tiền một phần và yêu cầu idempotency.
- Security review quyền truy cập, chống lạm dụng và dữ liệu nhạy cảm.
- Operations đánh giá rate limit, monitoring, alert và cách xử lý dependency payment provider.
- Product/release owner xác định mức rủi ro và phạm vi rollout.

**Giai đoạn pull request**

- Developer viết code, unit test và contract test.
- QA review các case lỗi, duplicate request và trạng thái không xác định.
- Security kiểm tra authorization và scanner findings.
- Pipeline tạo test report, scan report và artifact provenance.
- Reviewer phê duyệt theo code ownership và policy.

**Giai đoạn staging**

- Artifact được promote theo digest.
- QA chạy integration và end-to-end test với sandbox.
- Operations xác minh dashboard, alert và rollback.
- Security xác nhận các finding còn lại đã được xử lý hoặc có exception hợp lệ.

**Giai đoạn production**

- Release owner xác nhận readiness.
- Người có thẩm quyền phê duyệt theo policy.
- Operations triển khai canary.
- Development và QA theo dõi error rate, duplicate refund và critical journey.
- Nếu đạt ngưỡng, rollout tiếp tục; nếu không, dừng rollout và thực hiện mitigation.

**Sau phát hành**

- Deployment record liên kết artifact, config và environment.
- Team theo dõi metric và phản hồi người dùng.
- Nếu có incident, các vai trò phối hợp theo incident command.
- Action item sau incident được giao owner cụ thể.

Ví dụ cho thấy không một nhóm nào sở hữu toàn bộ chất lượng. Mỗi nhóm đóng góp chuyên môn vào một quyết định chung và cung cấp bằng chứng để release owner hành động.

## 18. Những anti-pattern trong phối hợp nhóm

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Development ném build qua QA | QA nhận thay đổi muộn, thiếu bối cảnh | QA tham gia từ yêu cầu và thiết kế |
| QA chịu trách nhiệm duy nhất về chất lượng | Developer ít đầu tư test và maintainability | Chất lượng là trách nhiệm chung, QA dẫn dắt chiến lược test |
| Security chỉ review trước production | Phát hiện muộn, sửa tốn kém | Shift-left và tự động hóa baseline |
| Operations chỉ tham gia khi deploy | Thiếu observability, capacity và recovery | Tham gia design/release readiness theo rủi ro |
| Không có owner cho quality gate | Gate fail nhưng không ai xử lý | Gắn owner, SLA và escalation |
| Quá nhiều người cùng phê duyệt | Quyết định chậm và trách nhiệm mờ | RACI với một A rõ ràng |
| Developer tự bỏ qua security finding | Risk acceptance không độc lập | Exception theo policy và approval phù hợp |
| Bàn giao chỉ có artifact | Operations thiếu config và runbook | Deployment handoff có cấu trúc |
| Release chỉ dựa vào pipeline xanh | Bỏ sót readiness và runtime risk | Review bằng chứng và điều kiện production |
| Incident tập trung tìm lỗi cá nhân | Giảm hợp tác, action item yếu | Post-incident review tập trung vào hệ thống |
| Không ghi quyết định | Khó audit và lặp lại tranh luận | Lưu release/incident record |
| Không đóng action item | Cùng lỗi xuất hiện nhiều lần | Owner, deadline và xác minh hiệu quả |

## 19. Checklist thống nhất trách nhiệm

Trước khi đưa một thay đổi vào production, hãy xác nhận:

- [ ] Có owner cho thay đổi và người điều phối release.
- [ ] Development, QA, Security và Operations được tham gia theo mức rủi ro.
- [ ] Acceptance criteria và test strategy đã rõ.
- [ ] Developer sở hữu unit/component test và xử lý lỗi code.
- [ ] QA cung cấp test scope, kết quả và rủi ro còn lại.
- [ ] Security policy, findings và exception có owner.
- [ ] Operations xác nhận môi trường, capacity, observability và recovery.
- [ ] Quality gate có tiêu chí, bằng chứng và người chịu trách nhiệm.
- [ ] Quyền block, approve và risk accept được quy định.
- [ ] Pull request ghi rõ data/schema/config impact.
- [ ] Artifact, report và release được liên kết bằng ID/digest.
- [ ] Deployment handoff có runbook, dashboard, alert và rollback constraint.
- [ ] Có release readiness review theo rủi ro.
- [ ] Có người theo dõi sau deploy và điều kiện dừng rollout.
- [ ] Incident commander và on-call path đã xác định.
- [ ] Post-incident action item có owner, deadline và cách xác minh.

## 20. Bài tập tự đánh giá

Một nhóm chuẩn bị phát hành tính năng chuyển tiền nội bộ. Hiện trạng:

- Developer đã hoàn tất code và unit test.
- QA chỉ nhận build vào ngày cuối cùng trước release.
- Security chưa review authorization và threat model.
- Operations chưa biết thay đổi có cần migration hay không.
- Pipeline báo xanh nhưng không có report integration test.
- Release manager không biết ai có quyền chấp nhận security exception.
- Không có runbook hoặc dashboard riêng cho luồng chuyển tiền.

Hãy thiết kế lại cách phối hợp:

1. Vai trò nào cần tham gia ở giai đoạn yêu cầu và thiết kế?
2. Acceptance criteria và test strategy cần bao gồm trường hợp nào?
3. Ai chịu trách nhiệm sửa lỗi authorization và ai xác nhận policy?
4. Ai cần xác minh migration và khả năng tương thích dữ liệu?
5. Pipeline phải xử lý thế nào khi integration report bị thiếu?
6. RACI cho release readiness nên có những vai trò nào?
7. Ai có quyền approve production và risk exception?
8. Operations cần dashboard, alert và runbook gì?
9. Nếu canary làm tăng lỗi chuyển tiền, ai điều phối incident và ai thực hiện mitigation?
10. Những action item nào cần hoàn thành trước lần phát hành tiếp theo?

Một phương án tốt đưa QA, security và operations vào trước khi code hoàn tất; xác định owner cho từng gate; yêu cầu report đầy đủ; chuẩn bị deployment handoff; và chỉ phát hành khi người có thẩm quyền đã xem xét bằng chứng cùng rủi ro còn lại.

## Kết luận

Phối hợp CI/CD hiệu quả cần một chuỗi trách nhiệm liên tục giữa phát triển, kiểm thử, bảo mật và vận hành. Development xây dựng thay đổi có thể kiểm tra và vận hành; QA dẫn dắt chiến lược kiểm thử và cung cấp bằng chứng; Security xác định và tư vấn kiểm soát rủi ro; Operations bảo đảm môi trường, triển khai, quan sát và phục hồi. Release owner điều phối quyết định dựa trên policy và bằng chứng.

Hãy xác định RACI và quyền quyết định, đưa chuyên môn vào sớm, gắn owner với từng quality gate, chuẩn bị release handoff và thống nhất cách ứng phó incident. Khi mỗi hoạt động có người chịu trách nhiệm, tiêu chí hoàn tất và bằng chứng rõ ràng, các nhóm có thể phát hành nhanh hơn mà vẫn giữ được chất lượng, bảo mật và độ tin cậy của dịch vụ.

