# Thống nhất người sở hữu từng nhóm bằng chứng và bộ kiểm thử

## 1. Vì sao cần xác định ownership cho bằng chứng và bộ kiểm thử?

Một chiến lược kiểm thử có thể có hàng trăm hoặc hàng nghìn test, nhiều pipeline, báo cáo tự động, log, trace, kết quả kiểm thử thủ công, hồ sơ bảo mật và bằng chứng vận hành. Các tài sản này thường được tạo bởi nhiều vai trò và nhiều nhóm. Nếu không xác định ai chịu trách nhiệm, test có thể lỗi thời, bằng chứng không còn truy xuất được, finding không được xử lý hoặc một thay đổi quan trọng không có người đánh giá tác động.

**Ownership** là sự phân công trách nhiệm rõ ràng đối với một tài sản kiểm thử hoặc bằng chứng: ai chịu trách nhiệm cuối cùng về tính đúng đắn và tính hữu ích, ai thực hiện công việc thường xuyên, ai cung cấp chuyên môn, ai phê duyệt thay đổi và ai cần được thông báo. Ownership không có nghĩa một cá nhân phải tự làm mọi việc. Một nhóm có thể cùng đóng góp, nhưng cần có một vai trò hoặc nhóm chịu trách nhiệm cuối cùng cho từng phạm vi.

Trong **VALIDATION_TESTING_STRATEGY**, cần thống nhất ownership cho ít nhất hai nhóm tài sản:

- **Bộ kiểm thử (test suite):** tập test được tổ chức theo mục tiêu, thành phần, rủi ro, tầng kiểm thử hoặc giai đoạn phát hành; bao gồm mã test, dữ liệu, cấu hình, fixture, tài liệu và quy tắc thực thi.
- **Bằng chứng kiểm thử (test evidence):** kết quả và artifact dùng để chứng minh điều gì đã được kiểm tra, trong điều kiện nào, với phiên bản nào và kết luận ra sao.

Một test suite có thể được duy trì bởi một nhóm nhưng kiểm tra hành vi do nhóm khác sở hữu. Một báo cáo có thể được tạo tự động bởi CI nhưng trách nhiệm xác nhận ý nghĩa và xử lý finding thuộc về service owner hoặc domain owner. Vì vậy, cần phân biệt người sở hữu sản phẩm, người sở hữu test, người sở hữu bằng chứng, người vận hành công cụ và người chấp thuận rủi ro.

Khi ownership rõ ràng, nhóm biết phải hỏi ai khi test thất bại, ai cập nhật test khi yêu cầu thay đổi, ai bảo đảm artifact được lưu, ai đánh giá độ tin cậy của kết quả và ai chịu trách nhiệm khắc phục khoảng trống bao phủ.

## 2. Phân biệt các loại ownership

Một tài sản có thể liên quan đến nhiều vai trò. Không nên dùng một nhãn owner chung để che lấp những trách nhiệm khác nhau.

| Loại ownership | Trách nhiệm | Ví dụ |
|---|---|---|
| Product/service ownership | Chịu trách nhiệm về hành vi, chất lượng và rủi ro của dịch vụ | Order service owner chịu trách nhiệm về quy tắc tạo đơn |
| Test suite ownership | Duy trì phạm vi, chất lượng, khả năng chạy và tính cập nhật của bộ test | Order test owner quản lý API regression suite |
| Test implementation ownership | Sửa mã test, fixture, assertion và cấu hình liên quan | Developer trong nhóm dịch vụ cập nhật test khi contract đổi |
| Evidence ownership | Bảo đảm bằng chứng đầy đủ, đúng phiên bản, có ngữ cảnh và truy xuất được | Test lead xác nhận báo cáo hồi quy của release |
| Evidence custody | Quản lý nơi lưu, quyền truy cập, thời hạn lưu và tính toàn vẹn artifact | CI/platform team vận hành kho report và log |
| Test infrastructure ownership | Duy trì runner, framework, môi trường, dữ liệu nền và pipeline | Platform team quản lý runner và template môi trường |
| Domain ownership | Xác nhận quy tắc nghiệp vụ và ý nghĩa kết quả | Finance domain expert xác nhận quy tắc đối soát |
| Risk ownership | Đánh giá và theo dõi rủi ro còn lại | Service owner chịu trách nhiệm rủi ro mất dữ liệu |
| Approval authority | Chấp thuận quyết định hoặc ngoại lệ trong phạm vi thẩm quyền | Release authority phê duyệt phát hành có điều kiện |

Ví dụ, khi API thanh toán thay đổi:

- Payment service owner chịu trách nhiệm hành vi và tương thích của provider.
- Consumer team sở hữu test xác nhận consumer sử dụng contract đúng.
- Test lead điều phối phạm vi hồi quy và đánh giá bằng chứng.
- Platform team duy trì pipeline và lưu report.
- Security owner đánh giá các kiểm tra liên quan đến xác thực và dữ liệu nhạy cảm.
- Release authority quyết định phát hành theo policy và rủi ro đã được trình bày.

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ. Tuy nhiên, hồ sơ vẫn cần ghi rõ vai trò nào người đó đang thực hiện, để khi tổ chức thay đổi hoặc bàn giao không bị mất trách nhiệm.

## 3. Xác định phạm vi tài sản cần có owner

### 3.1. Nhóm bộ kiểm thử

Không chỉ gán owner cho toàn bộ test repository. Cần chia phạm vi đủ nhỏ để có thể giao trách nhiệm và đánh giá thay đổi:

- Unit test theo module, package hoặc domain.
- Component và repository test theo thành phần.
- API test theo endpoint, capability hoặc service.
- Contract test theo provider-consumer pair.
- Integration test theo luồng xuyên dịch vụ.
- End-to-end test theo hành trình người dùng.
- Regression suite theo release hoặc nhóm rủi ro.
- Performance, load, stress và soak test.
- Security, privacy và permission test.
- Migration, backup/restore và data integrity test.
- Manual/exploratory charter và checklist.
- Test dữ liệu, fixture, generator và simulator.

Một suite quá lớn và không có ranh giới khiến owner khó biết mình phải duy trì những gì. Một suite bị chia quá nhỏ lại tạo nhiều đầu mối và tăng chi phí phối hợp. Chọn đơn vị ownership dựa trên ranh giới thay đổi, rủi ro, kiến trúc và khả năng xử lý của nhóm.

### 3.2. Nhóm bằng chứng

Bằng chứng cần được phân nhóm theo nguồn và mục đích:

| Nhóm bằng chứng | Nội dung thường có | Trách nhiệm cần xác định |
|---|---|---|
| Test execution report | Trạng thái, số lượng, thời gian, test ID, build ID | Ai xác nhận kết quả và phạm vi |
| Test artifacts | Ảnh, video, log, trace, request/response đã làm sạch | Ai bảo đảm chất lượng, quyền và thời hạn lưu |
| Coverage/traceability | Liên kết requirement-risk-test-result | Ai duy trì mapping và xác nhận khoảng trống |
| Defect/finding record | Mô tả, severity, bước tái hiện, bằng chứng và trạng thái | Ai triage, ai sửa và ai xác minh |
| Performance evidence | Workload, latency, throughput, error rate, resource metric | Ai xác nhận phương pháp và kết quả |
| Security evidence | Scan, review, threat analysis, penetration test report | Ai đánh giá finding và kiểm soát truy cập |
| Operational readiness | Dashboard, alert, runbook, restore/rollback record | Ai chịu trách nhiệm vận hành và phê duyệt |
| Manual/exploratory notes | Charter, thao tác, quan sát, phát hiện và debrief | Ai xác nhận nội dung và follow-up |
| Release evidence | Quality gate, waiver, risk acceptance, release decision | Ai tổng hợp và ai có quyền quyết định |

Một artifact có thể được lưu bởi platform nhưng nội dung do test owner tạo ra. Do đó, nên ghi riêng evidence owner và evidence custodian khi hai trách nhiệm khác nhau.

### 3.3. Nhóm dữ liệu và cấu hình hỗ trợ

Test suite thường phụ thuộc vào fixture, generator, seed, tài khoản, secret reference, mock, simulator, schema, container image và cấu hình môi trường. Các tài sản này cũng cần owner hoặc một nhóm chịu trách nhiệm. Test không thể đáng tin nếu dữ liệu không được cập nhật hoặc cấu hình thay đổi mà không ai biết.

Không đưa secret hoặc dữ liệu cá nhân vào registry ownership. Chỉ lưu tên tham chiếu, hệ thống quản lý và nhóm có quyền; giá trị bí mật phải nằm trong cơ chế được phê duyệt.

## 4. Nguyên tắc phân công ownership

### 4.1. Mỗi phạm vi cần một accountable owner rõ ràng

Có thể có nhiều người cùng thực hiện, nhưng mỗi suite hoặc nhóm bằng chứng cần một vai trò chịu trách nhiệm cuối cùng. Nếu có hai accountable owner ngang nhau mà không phân ranh giới, khi xảy ra lỗi thường không ai biết ai phải quyết định.

Với tài sản liên nhóm, có thể chọn một nhóm điều phối chịu trách nhiệm về hợp đồng và quy trình chung, trong khi từng service team vẫn sở hữu test và bằng chứng của phần mình. Cần ghi rõ ranh giới thay vì gán toàn bộ trách nhiệm cho nhóm trung tâm.

### 4.2. Ownership đi cùng khả năng quyết định

Không giao trách nhiệm cho một nhóm nếu nhóm đó không có quyền sửa, yêu cầu sửa hoặc điều phối người có quyền. Ví dụ, nhóm QA có thể phát hiện test của service lỗi thời nhưng không có quyền thay đổi mã dịch vụ; quy trình phải xác định service owner chịu trách nhiệm cập nhật.

### 4.3. Gần nơi có hiểu biết và khả năng thay đổi

Test cho quy tắc nghiệp vụ thường nên có sự tham gia của nhóm hiểu domain. Test cho pipeline và runner nên do nhóm platform vận hành. Test contract cần sự phối hợp giữa provider và consumer. Phân công gần nguồn hiểu biết giúp giảm thời gian giải thích và tăng khả năng phát hiện tác động.

### 4.4. Tách người tạo bằng chứng và người đánh giá khi cần

Với rủi ro cao, có thể cần review độc lập. Người viết test có thể cung cấp kết quả; test lead hoặc reviewer khác xác nhận phạm vi; security specialist đánh giá finding bảo mật; release authority chấp thuận rủi ro. Mức độc lập cần tương xứng với hậu quả và chính sách.

### 4.5. Ownership phải liên tục qua vòng đời

Trách nhiệm không kết thúc khi test pass. Cần duy trì test khi yêu cầu thay đổi, giữ bằng chứng theo chính sách, xử lý finding, cập nhật mapping, rà soát suite và bàn giao khi owner thay đổi.

### 4.6. Không đồng nhất người chạy với người sở hữu

Pipeline có thể chạy test tự động, vendor có thể thực hiện kiểm thử chuyên biệt và QA có thể điều phối một phiên kiểm thử. Điều đó không tự động chuyển trách nhiệm chất lượng của sản phẩm sang người chạy. Service owner vẫn chịu trách nhiệm về rủi ro dịch vụ trong phạm vi của mình.

## 5. Các mô hình tổ chức ownership

### 5.1. Mô hình tập trung

Một nhóm quality engineering hoặc QA platform quản lý phần lớn test framework, suite chung, quy tắc báo cáo và bằng chứng.

**Phù hợp khi:**

- Tổ chức còn nhỏ hoặc đang chuẩn hóa cách kiểm thử.
- Nhiều nhóm dùng chung công cụ và cần một đầu mối hỗ trợ.
- Có yêu cầu kiểm soát thống nhất về bằng chứng và báo cáo.

**Rủi ro:**

- Nhóm trung tâm trở thành nút thắt.
- Người viết test xa domain nên khó hiểu hành vi nghiệp vụ.
- Nhóm phát triển có thể coi chất lượng là trách nhiệm riêng của QA.

Để tránh các vấn đề này, nhóm trung tâm nên sở hữu nền tảng, tiêu chuẩn và các suite dùng chung; service team vẫn chịu trách nhiệm test cho hành vi dịch vụ của mình.

### 5.2. Mô hình liên kết/federated

Mỗi service hoặc domain team sở hữu test và bằng chứng của thành phần mình; một nhóm quality engineering duy trì chuẩn chung, công cụ, taxonomy và báo cáo tổng hợp.

**Ưu điểm:**

- Trách nhiệm gần với nơi thay đổi sản phẩm.
- Nhóm hiểu domain có thể cập nhật test nhanh.
- Vẫn có chuẩn chung để tổng hợp kết quả liên dịch vụ.

**Điều kiện cần:**

- Có quy ước chung về ID, metadata, trạng thái và artifact.
- Có owner cho test liên nhóm và contract.
- Có review định kỳ để phát hiện khoảng trống hoặc trùng lặp.

Đây là mô hình phù hợp với nhiều tổ chức có nhiều dịch vụ và nhóm độc lập.

### 5.3. Mô hình chia sẻ theo năng lực

Một số tài sản được sở hữu bởi nhóm chuyên môn: security test do security team, performance platform do performance engineering, device lab do mobile quality, còn service team sở hữu functional regression. Mô hình này phù hợp khi tài sản đòi hỏi chuyên môn hoặc hạ tầng chuyên biệt.

Ranh giới cần rõ: nhóm chuyên môn chịu trách nhiệm phương pháp, công cụ và kết luận chuyên môn; service owner chịu trách nhiệm xử lý tác động lên dịch vụ và rủi ro còn lại.

### 5.4. Kết hợp mô hình

Thực tế thường kết hợp:

- Nhóm platform sở hữu runner, môi trường và kho artifact.
- Service team sở hữu unit/API/component suite và hành vi sản phẩm.
- Test lead sở hữu chiến lược hồi quy, mapping và tổng hợp evidence.
- Security/performance team sở hữu các kiểm thử chuyên biệt.
- Release authority sở hữu quyết định phát hành.

Không có mô hình tổ chức tối ưu cho mọi công ty. Điều quan trọng là mỗi tài sản có owner, quyền hạn, đầu vào/đầu ra và đường escalation rõ ràng.

## 6. Vai trò và trách nhiệm cụ thể

### 6.1. Service owner

Service owner chịu trách nhiệm cuối cùng về chất lượng dịch vụ trong phạm vi được giao. Trách nhiệm thường gồm:

- Xác định các hành vi, dependency và rủi ro quan trọng.
- Bảo đảm test cho các thay đổi của dịch vụ được cập nhật.
- Chỉ định owner cho từng suite hoặc capability.
- Xử lý defect và finding thuộc dịch vụ.
- Cung cấp thông tin phiên bản, cấu hình và thay đổi cho người tiêu thụ.
- Đánh giá rủi ro còn lại và đề xuất hành động.
- Bảo đảm có người tiếp nhận trách nhiệm khi thành viên rời nhóm.

Service owner không nhất thiết trực tiếp viết mọi test. Họ phải bảo đảm trách nhiệm được giao và có thể truy xuất.

### 6.2. Test suite owner

Test suite owner chịu trách nhiệm về sức khỏe và tính hữu ích của một suite:

- Xác định mục tiêu, phạm vi, loại test và rủi ro được bảo vệ.
- Duy trì danh sách test, metadata, fixture và tài liệu.
- Bảo đảm test có expected result rõ và không phụ thuộc thứ tự ngoài ý muốn.
- Theo dõi flaky test, thời gian chạy và lỗi môi trường.
- Review thay đổi test và đánh giá ảnh hưởng khi yêu cầu đổi.
- Phối hợp xử lý test lỗi với service owner hoặc platform owner.
- Định kỳ loại bỏ test lỗi thời hoặc bổ sung khoảng trống có căn cứ.

Suite owner cần biết suite đang bảo vệ yêu cầu hoặc rủi ro nào. Một thư mục có nhiều file test nhưng không có mục tiêu rõ chưa phải một bộ kiểm thử được quản trị tốt.

### 6.3. Evidence owner

Evidence owner chịu trách nhiệm về tính đầy đủ và ý nghĩa của một nhóm bằng chứng:

- Xác định bằng chứng cần có cho quyết định.
- Kiểm tra bằng chứng gắn với đúng build, commit, môi trường và thời điểm.
- Xác nhận test status và giới hạn của kết quả.
- Liên kết report với requirement, risk, suite và release.
- Ghi nhận khoảng trống, ngoại lệ và bằng chứng thay thế.
- Bảo đảm report dễ hiểu và có thể truy xuất.

Evidence owner không nhất thiết quản lý hạ tầng lưu trữ. Nếu việc lưu trữ do platform team thực hiện, cần phân định rõ trách nhiệm nội dung và trách nhiệm custody.

### 6.4. Evidence custodian/platform owner

Vai trò này quản lý cơ chế kỹ thuật:

- Lưu trữ artifact, metadata và lịch sử.
- Quản lý quyền truy cập, thời hạn lưu và cleanup.
- Bảo đảm backup hoặc khả năng khôi phục khi cần.
- Duy trì runner, pipeline, report service và tích hợp công cụ.
- Theo dõi dung lượng, tính sẵn sàng và lỗi thu thập.
- Cung cấp cách truy xuất và audit theo chính sách.

Platform owner không tự xác nhận nội dung nghiệp vụ của báo cáo nếu không được giao vai trò đó.

### 6.5. Domain expert/product owner

Domain expert hoặc product owner xác nhận quy tắc nghiệp vụ, expected behavior, mức ưu tiên và tác động đến người dùng. Họ giúp phân biệt lỗi sản phẩm với yêu cầu chưa rõ, đồng thời xác nhận test có phản ánh đúng mục tiêu nghiệp vụ không.

### 6.6. Security, privacy và performance specialist

Nhóm chuyên môn xác định phương pháp, tiêu chí và cách diễn giải kết quả thuộc lĩnh vực của mình. Họ review finding, tư vấn biện pháp xử lý và chấp thuận ngoại lệ nếu chính sách trao quyền. Service owner vẫn chịu trách nhiệm triển khai sửa đổi trong dịch vụ.

### 6.7. Release authority

Release authority đánh giá tổng hợp readiness và quyết định trong phạm vi được ủy quyền. Họ cần nhận báo cáo thể hiện test đã chạy, phần chưa chạy, finding, rủi ro còn lại, waiver và điều kiện rollout. Quyền phát hành không đồng nghĩa quyền miễn trừ mọi yêu cầu chuyên môn hoặc nghĩa vụ bắt buộc.

## 7. Xây dựng registry ownership

### 7.1. Vì sao cần registry?

Registry là danh mục có thể tra cứu các suite, nhóm bằng chứng, owner và liên kết liên quan. Nó giúp trả lời nhanh:

- Suite này bảo vệ hành vi hoặc rủi ro nào?
- Ai chịu trách nhiệm khi test fail hoặc lỗi thời?
- Test chạy ở đâu và được kích hoạt khi nào?
- Bằng chứng được lưu ở đâu và ai có quyền truy cập?
- Phụ thuộc nào cần phối hợp với nhóm khác?
- Khi owner thay đổi, ai tiếp nhận?

Registry có thể nằm trong hệ thống quản lý test, repository, catalog dịch vụ hoặc công cụ quản lý engineering. Không nhất thiết tạo một hệ thống mới nếu công cụ hiện tại đã đáp ứng.

### 7.2. Trường thông tin đề xuất

| Trường | Mục đích |
|---|---|
| Asset ID | Định danh ổn định cho suite hoặc nhóm evidence |
| Asset name/type | Tên và loại tài sản: unit, API, contract, performance, report... |
| Scope | Service, domain, journey, requirement hoặc risk liên quan |
| Accountable owner | Nhóm/vai trò chịu trách nhiệm cuối cùng |
| Responsible contacts | Người hoặc nhóm thực hiện bảo trì, chạy và review |
| Backup owner | Người/nhóm thay thế khi owner chính vắng mặt |
| Consumers | Nhóm sử dụng kết quả hoặc phụ thuộc vào suite |
| Trigger/cadence | Khi nào test chạy hoặc bằng chứng được tạo |
| Environment | Môi trường, phiên bản và điều kiện cần thiết |
| Evidence location | Nơi lưu report/artifact và cách truy xuất |
| Retention/access | Quyền truy cập và thời hạn lưu |
| Dependencies | Dịch vụ, dữ liệu, công cụ hoặc nhóm liên quan |
| Criticality | Mức độ quan trọng theo rủi ro |
| Last reviewed | Thời điểm review ownership và nội dung gần nhất |
| Lifecycle state | Active, deprecated, migrating hoặc retired |

Không nhất thiết điền mọi trường cho mọi asset. Nhưng owner, scope, cách thực thi và nơi truy xuất bằng chứng cần có với những tài sản đang được dùng cho quyết định chất lượng.

### 7.3. Ví dụ registry

~~~yaml
assets:
  - id: SUITE-ORDER-API-01
    name: "Order API regression"
    type: api-regression
    scope:
      service: order
      risks:
        - duplicate-order
        - inventory-consistency
    accountable_owner: order-team
    responsible:
      - order-test-owner
      - order-developers
    backup_owner: commerce-quality
    consumers:
      - release-management
      - inventory-team
    trigger:
      - pull-request
      - pre-release
    evidence_location: "ci-artifact:order-api-regression"
    dependencies:
      - order-test-database
      - inventory-contract
    criticality: high
    lifecycle: active
    last_reviewed: "2026-11-01"

  - id: EVIDENCE-SECURITY-ORDER
    name: "Order security assessment"
    type: security-evidence
    scope:
      service: order
      risks:
        - unauthorized-order-access
    accountable_owner: security-team
    responsible:
      - application-security
    backup_owner: security-operations
    consumers:
      - order-team
      - release-management
    evidence_location: "approved-security-report-store"
    access: restricted
    retention: "according-to-security-policy"
    criticality: high
    lifecycle: active
    last_reviewed: "2026-11-01"
~~~

Đây là ví dụ cấu trúc, không phải dữ liệu ownership thật của tổ chức. Không ghi URL chứa token, mật khẩu, secret hoặc dữ liệu cá nhân trong registry. Với bằng chứng nhạy cảm, chỉ ghi tham chiếu đến kho được kiểm soát quyền.

## 8. Ma trận RACI cho suite và evidence

RACI giúp phân biệt người thực hiện (Responsible), người chịu trách nhiệm cuối cùng (Accountable), người cần tham vấn (Consulted) và người cần được thông báo (Informed).

| Hoạt động | Service owner | Suite owner | Test lead | Platform/evidence custodian | Domain/security specialist | Release authority |
|---|---|---|---|---|---|---|
| Xác định hành vi và rủi ro của service | A/R | C | C | I | C | I |
| Xác định phạm vi suite | A | R | C | I | C | I |
| Viết và bảo trì test | A | R | C | C | C | I |
| Duy trì runner/framework | C | C | I | A/R | I | I |
| Tạo và xác nhận test report | C | R | A | R* | C | I |
| Lưu trữ và quản lý quyền artifact | I | C | C | A/R | C | I |
| Diễn giải bằng chứng chuyên môn | C | C | R | I | A/R* | I |
| Xử lý defect trong service | A/R | R* | C | C | C | I |
| Đánh giá rủi ro còn lại | A/R | C | R | I | C | C |
| Chấp thuận release/ngoại lệ | C | I | C | I | C* | A/R* |
| Bàn giao ownership | A | R | C | C | C | I |

RACI phải được điều chỉnh theo cơ cấu và quyền hạn thực tế. Với từng dòng, chỉ nên có một Accountable trong phạm vi trách nhiệm đã xác định. Dấu * chỉ trách nhiệm có điều kiện: ví dụ platform chịu trách nhiệm kỹ thuật về report pipeline nhưng test lead chịu trách nhiệm xác nhận nội dung; chuyên gia bảo mật có thể có quyền phê duyệt riêng đối với ngoại lệ bảo mật theo policy.

RACI không thay thế mô tả công việc hoặc quy trình escalation. Nó là công cụ để thống nhất ai làm gì trong một hoạt động cụ thể.

## 9. Thiết lập hợp đồng phối hợp giữa các nhóm

### 9.1. Khi suite kiểm tra service do nhóm khác sở hữu

Một nhóm có thể duy trì test đầu cuối cho hành trình gồm nhiều dịch vụ. Khi một service thay đổi, suite owner cần biết thay đổi có ảnh hưởng đến test, dữ liệu, fixture hay expected behavior không.

Hợp đồng phối hợp nên xác định:

- Nhóm provider thông báo thay đổi API, event, schema và hành vi.
- Nhóm consumer cung cấp danh sách tương tác và kỳ vọng tương thích.
- Suite owner đánh giá impact và cập nhật test.
- Service owner cung cấp môi trường, dữ liệu hoặc endpoint cần thiết.
- Test lead xác nhận phạm vi hồi quy và bằng chứng.
- Quy trình xử lý khi contract test hoặc integration test thất bại.

Không mặc định nhóm sở hữu test phải tự đoán mọi thay đổi từ mã nguồn của nhóm khác. Cần có cơ chế thông báo và tài liệu thay đổi.

### 9.2. Khi bằng chứng được nhiều nhóm sử dụng

Một report có thể phục vụ developer, QA, security, operations và release management. Cần xác định:

- Phiên bản và phạm vi được chứng minh.
- Các trạng thái và giới hạn diễn giải.
- Ai có quyền xem, tải hoặc chia sẻ.
- Ai cập nhật nếu report có lỗi hoặc thiếu dữ liệu.
- Thời hạn lưu và cách tham chiếu trong release record.
- Kênh thông báo khi bằng chứng bị thu hồi hoặc phát hiện sai.

Người tiêu thụ bằng chứng không được tự diễn giải report vượt quá phạm vi đã ghi. Ví dụ, contract test đạt không chứng minh performance hoặc toàn bộ end-to-end journey đã đạt.

### 9.3. Khi phụ thuộc là dịch vụ hoặc công cụ dùng chung

Nếu test phụ thuộc vào shared environment, sandbox, identity provider hoặc data service, cần có owner của dependency và quy ước availability, version, lịch bảo trì, giới hạn tải và thông báo sự cố. Suite owner phải ghi rõ kết quả nào bị ảnh hưởng khi dependency không sẵn sàng.

### 9.4. Thỏa thuận mức dịch vụ nội bộ

Với suite hoặc bằng chứng trọng yếu, nhóm có thể thống nhất cam kết nội bộ như:

- Thời gian phản hồi khi suite bắt buộc bị lỗi.
- Thời gian thông báo khi thay đổi dependency.
- Thời gian khôi phục pipeline hoặc evidence store.
- Thời gian triage finding nghiêm trọng.
- Thời gian cập nhật registry khi owner thay đổi.

Các mục tiêu cần khả thi và phù hợp mức quan trọng. Không đặt SLA chỉ để có con số; cần gắn mục tiêu với tác động khi suite hoặc bằng chứng không sẵn sàng.

## 10. Ownership trong vòng đời của bộ kiểm thử

### 10.1. Khi tạo suite mới

Trước khi suite được dùng làm bằng chứng cho quyết định, cần:

1. Xác định mục tiêu, phạm vi và rủi ro được bảo vệ.
2. Chỉ định accountable owner, suite owner và backup.
3. Xác định người review, người chạy và consumer của kết quả.
4. Định nghĩa test ID, metadata, môi trường và dữ liệu.
5. Xác định trigger, cadence, timeout và tiêu chí kết quả.
6. Chọn nơi lưu report/artifact và quyền truy cập.
7. Đưa suite vào registry và tài liệu vận hành.
8. Xác nhận quy trình triage, bảo trì và escalation.

Một suite chưa có owner hoặc chưa có cách xử lý khi thất bại không nên được coi là kiểm soát ổn định.

### 10.2. Khi yêu cầu hoặc sản phẩm thay đổi

Change owner thông báo thay đổi và phạm vi ảnh hưởng. Suite owner đánh giá test nào cần cập nhật, thêm hoặc loại bỏ; service owner xác nhận hành vi mới; test lead đánh giá tác động đến regression strategy và coverage. Nếu thay đổi làm mất hiệu lực bằng chứng cũ, cần ghi rõ thời điểm và phiên bản bắt đầu áp dụng.

### 10.3. Khi test fail hoặc flaky

Suite owner phân loại lỗi test, lỗi sản phẩm, môi trường, dữ liệu hoặc phụ thuộc. Service owner nhận defect sản phẩm; platform owner xử lý runner/môi trường; domain expert làm rõ expected behavior. Test bị quarantine cần có owner, lý do, rủi ro mất bao phủ và hạn xử lý.

Không để một test flaky bị vô hiệu hóa vô thời hạn. Nếu cần cách ly để giữ pipeline hoạt động, phải ghi nhận và có biện pháp thay thế hoặc quyết định rủi ro.

### 10.4. Khi suite không còn được sử dụng

Trước khi retire suite, xác định:

- Rủi ro hoặc yêu cầu nào nó từng bảo vệ.
- Có suite hoặc kiểm soát nào thay thế không.
- Consumer nào đang phụ thuộc vào kết quả.
- Bằng chứng lịch sử cần giữ bao lâu.
- Dữ liệu, môi trường và secret reference nào cần thu hồi.
- Ai phê duyệt việc ngừng sử dụng.

Đánh dấu deprecated trước khi xóa nếu cần thời gian chuyển tiếp. Không xóa test chỉ vì pipeline chậm mà chưa đánh giá khoảng trống bao phủ.

## 11. Ownership trong vòng đời bằng chứng

### 11.1. Trước khi thực thi

Evidence owner xác định loại bằng chứng cần tạo, build identity, môi trường, dữ liệu, thời điểm, metadata và nơi lưu. Nếu cần bằng chứng chuyên môn, xác định reviewer hoặc specialist.

### 11.2. Khi tạo bằng chứng

Người thực hiện hoặc pipeline cần gắn kết quả với:

- Test suite và test ID.
- Commit/build/release candidate.
- Environment ID và cấu hình liên quan.
- Thời gian, múi giờ và run ID.
- Dữ liệu/seed hoặc định danh dataset.
- Trạng thái, expected result và actual result.
- Artifact, log, trace hoặc report.

Nếu test chạy thất bại do môi trường, bằng chứng phải thể hiện trạng thái blocked/inconclusive phù hợp. Không tạo report pass giả khi không thu được kết quả.

### 11.3. Sau khi tạo

Evidence owner kiểm tra report có đủ ngữ cảnh, đúng phiên bản, không bị cắt cụt và có thể truy xuất. Evidence custodian bảo đảm artifact được lưu, quyền truy cập và thời hạn phù hợp. Test lead liên kết evidence với requirement, risk, defect hoặc release decision.

### 11.4. Khi bằng chứng bị sai hoặc mất

Nếu report sai build, thiếu artifact, bị thay đổi hoặc không thể truy xuất, cần đánh dấu không còn hợp lệ cho quyết định liên quan. Xác định người thông báo, phạm vi quyết định bị ảnh hưởng và việc chạy lại hoặc tái tạo bằng chứng.

Không âm thầm ghi đè artifact đã được dùng cho quyết định. Nếu cần sửa report, lưu lịch sử và chỉ rõ bản thay thế.

### 11.5. Thời hạn lưu và quyền truy cập

Retention phụ thuộc loại bằng chứng, nghĩa vụ hợp đồng, chính sách tổ chức và nhu cầu điều tra. Test report thông thường có thể có thời hạn khác với security report, audit evidence hoặc dữ liệu liên quan sự cố.

Áp dụng quyền tối thiểu. Log, HAR, video và database snapshot có thể chứa token, dữ liệu cá nhân hoặc thông tin nội bộ. Evidence custodian quản lý lưu trữ kỹ thuật; data/security owner xác định yêu cầu bảo vệ; evidence owner kiểm tra nội dung trước khi chia sẻ.

## 12. Bàn giao và thay đổi người sở hữu

Ownership cần được bàn giao có chủ đích khi nhân sự chuyển nhóm, nghỉ việc, thay đổi cấu trúc hoặc chuyển giao dịch vụ.

### 12.1. Nội dung bàn giao

- Danh sách suite và evidence thuộc phạm vi.
- Mục tiêu, rủi ro và consumer của từng tài sản.
- Owner hiện tại, backup và owner tiếp nhận.
- Cách chạy test, môi trường, dữ liệu và dependency.
- Pipeline, lịch chạy, quyền và nơi lưu artifact.
- Flaky test, defect mở, waiver và khoảng trống bao phủ.
- Công việc bảo trì sắp tới và thay đổi đang diễn ra.
- Hướng dẫn triage, escalation và liên hệ chuyên môn.

### 12.2. Xác nhận tiếp nhận

Người nhận cần xác nhận có quyền truy cập, hiểu cách chạy và biết cách xử lý lỗi. Với suite quan trọng, nên có một lần chạy thử hoặc review cùng owner cũ. Chỉ cập nhật registry sau khi trách nhiệm đã được tiếp nhận và quyền cần thiết đã sẵn sàng.

### 12.3. Khi chưa có owner thay thế

Không để tài sản trọng yếu rơi vào trạng thái không người chịu trách nhiệm. Service owner hoặc engineering manager cần chỉ định owner tạm thời, đánh giá rủi ro và đặt thời hạn tìm owner chính thức. Nếu không có người duy trì test bắt buộc hoặc bằng chứng phát hành, cần đưa vấn đề vào risk register và quality review.

## 13. Theo dõi sức khỏe ownership

Không nên chỉ đo số suite trên mỗi người. Cần theo dõi xem ownership có giúp tài sản được duy trì và bằng chứng được sử dụng đúng hay không.

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Ownership coverage | Tỷ lệ suite/evidence trọng yếu có accountable owner và backup | Phát hiện tài sản không có người chịu trách nhiệm |
| Registry freshness | Tỷ lệ record được review trong chu kỳ quy định | Phát hiện owner, link hoặc scope lỗi thời |
| Unowned findings | Finding chưa có owner xử lý | Đánh giá chất lượng triage và trách nhiệm |
| Time to acknowledge | Thời gian từ khi suite/evidence có vấn đề đến khi owner xác nhận | Đánh giá khả năng phản ứng |
| Time to restore | Thời gian khôi phục suite hoặc evidence pipeline | Đánh giá tính liên tục |
| Flaky test age | Thời gian test ở trạng thái flaky/quarantined | Phát hiện khoảng trống kéo dài |
| Evidence completeness | Tỷ lệ report có build, environment, run ID và artifact cần thiết | Đánh giá khả năng truy xuất |
| Handoff completion | Tỷ lệ bàn giao có xác nhận của người nhận | Giảm rủi ro mất tri thức |
| Duplicate suite rate | Mức trùng lặp giữa các suite | Cơ hội hợp nhất và giảm chi phí |
| Consumer satisfaction | Mức hữu ích và dễ hiểu của bằng chứng đối với nhóm sử dụng | Cải thiện báo cáo và giao diện |

Chỉ số cần được đọc theo bối cảnh. Một nhóm có nhiều suite không có nghĩa ownership kém; một suite có ít finding không nhất thiết tốt nếu không được chạy. Không dùng metric để xếp hạng cá nhân hoặc khuyến khích che giấu lỗi.

## 14. Quy trình thống nhất ownership trong một nhóm hoặc chương trình

Có thể áp dụng quy trình sau khi thiết lập hoặc rà soát ownership:

### Bước 1: Kiểm kê tài sản

Liệt kê suite, test framework, dataset, report, evidence store, pipeline và các kiểm soát chuyên môn đang được sử dụng. Ưu tiên tài sản ảnh hưởng đến release, bảo mật, dữ liệu và hành trình nghiệp vụ trọng yếu.

### Bước 2: Xác định mục đích và consumer

Với mỗi tài sản, ghi rõ nó bảo vệ điều gì, ai sử dụng kết quả và quyết định nào phụ thuộc vào nó. Nếu không xác định được consumer hoặc mục tiêu, cần xem xét tài sản có còn giá trị hay không.

### Bước 3: Chọn accountable owner

Chọn nhóm gần nhất có hiểu biết, quyền thay đổi và khả năng xử lý. Với tài sản liên nhóm, xác định ranh giới provider, consumer và nhóm điều phối. Không gán owner chỉ vì nhóm đó đang vận hành công cụ tạo report.

### Bước 4: Phân vai thực hiện, review và backup

Ghi người viết/sửa test, người review, người chạy, evidence owner, custodian và backup. Xác định ai triage khi test fail và ai có quyền quyết định ngoại lệ.

### Bước 5: Định nghĩa hợp đồng phối hợp

Thống nhất cách thông báo thay đổi, thời gian phản hồi, đầu vào/đầu ra, nơi lưu bằng chứng và quy trình escalation. Với contract hoặc integration suite, cần sự đồng thuận của provider và consumer.

### Bước 6: Ghi registry và liên kết

Ghi asset ID, owner, scope, trigger, dependency, evidence location, retention và trạng thái vòng đời. Liên kết với service catalog, requirement, risk hoặc release process nếu công cụ hỗ trợ.

### Bước 7: Xác nhận vận hành

Chạy thử hoặc kiểm tra quy trình để xác nhận owner có quyền, biết cách thực hiện và nhận được thông báo. Kiểm tra một tình huống fail hoặc evidence missing để xác nhận đường escalation.

### Bước 8: Review định kỳ và khi có thay đổi

Rà soát khi service đổi owner, suite thay đổi, dependency bị thay thế, có incident, test bị quarantine hoặc bằng chứng không còn truy xuất được. Cập nhật registry và thông báo cho consumer.

## 15. Ví dụ thực tế

### Ví dụ A: Bộ API regression của dịch vụ đơn hàng

Nhóm Order sở hữu API tạo đơn, kiểm tra tồn kho và hủy đơn. Test suite được gán cho một suite owner trong nhóm; các developer chịu trách nhiệm sửa test khi contract hoặc logic thay đổi. Test lead sở hữu mapping giữa suite với rủi ro và tổng hợp kết quả cho release. Platform team vận hành CI và lưu artifact.

Khi test tạo đơn thất bại, suite owner triage ban đầu, service owner quyết định xử lý defect, platform owner chỉ tham gia nếu runner hoặc môi trường có vấn đề. Inventory team được tham vấn khi lỗi liên quan đến hợp đồng tồn kho. Ranh giới này giúp tránh chuyển mọi lỗi sang QA hoặc platform.

### Ví dụ B: Contract test giữa provider và consumer

Payment provider cung cấp API giao dịch; Order consumer gọi API đó. Provider team sở hữu provider verification và bằng chứng tương thích phía provider. Order team sở hữu consumer contract và test xác nhận cách sử dụng response. Hai nhóm cùng chịu trách nhiệm phối hợp khi contract thay đổi.

Contract report có thể được dùng trong release của cả hai dịch vụ. Report phải ghi provider version, consumer version, contract revision và thời điểm xác nhận. Một bên không được tự tuyên bố toàn bộ tích hợp đã đạt chỉ dựa trên test ở phía mình.

### Ví dụ C: Bằng chứng bảo mật

Security team sở hữu phương pháp scan, quy tắc severity và kho báo cáo hạn chế quyền. Service team chịu trách nhiệm sửa finding trong mã và cấu hình của dịch vụ. Security owner xác nhận cách xử lý finding hoặc chấp thuận ngoại lệ thuộc thẩm quyền. Release authority sử dụng kết luận và rủi ro còn lại để quyết định trong phạm vi được phép.

Nếu báo cáo chứa endpoint nội bộ hoặc dữ liệu nhạy cảm, evidence custodian áp dụng quyền truy cập hạn chế. Release report chỉ trỏ đến bản ghi phù hợp với người nhận, không sao chép chi tiết nhạy cảm vào kênh rộng.

### Ví dụ D: Suite end-to-end xuyên nhiều nhóm

Một hành trình mua hàng gồm catalog, cart, order, payment và notification. Một nhóm quality engineering điều phối suite end-to-end và sở hữu cấu trúc hành trình, test data chung và báo cáo. Mỗi service team sở hữu contract, API test và xử lý defect trong thành phần mình. Product owner xác nhận expected behavior.

Khi catalog thay đổi schema, catalog owner thông báo consumer; suite owner đánh giá test và fixture; cart/order team xác nhận tương thích. Bằng chứng tích hợp được gắn với phiên bản của tất cả dịch vụ, không chỉ commit của nhóm điều phối.

### Ví dụ E: Bàn giao ownership khi thành viên rời nhóm

Một kỹ sư đang sở hữu performance suite chuyển sang nhóm khác. Trước khi chuyển, service owner chỉ định người nhận và backup. Hai bên rà soát workload, dataset seed, cấu hình môi trường riêng, dashboard, lịch chạy, lịch sử baseline và các giới hạn đã biết.

Người nhận thực hiện một lần chạy thử và xác nhận có quyền truy cập artifact. Registry được cập nhật sau khi bàn giao hoàn tất. Nếu không có người nhận ngay, engineering manager chỉ định owner tạm thời và đưa rủi ro thiếu năng lực vào kế hoạch.

## 16. Mẫu hồ sơ ownership cho một suite

~~~yaml
test_asset:
  id: SUITE-CHECKOUT-E2E-01
  name: "Checkout end-to-end regression"
  type: e2e-suite
  purpose: "Xác nhận hành trình checkout trọng yếu"

scope:
  services:
    - cart
    - order
    - payment
  risks:
    - duplicate-order
    - incorrect-payment-state
    - lost-checkout-data

ownership:
  accountable_owner: commerce-quality
  suite_owner: checkout-test-owner
  backup_owner: commerce-test-lead
  service_contacts:
    cart: cart-team
    order: order-team
    payment: payment-team
  evidence_owner: release-test-lead
  evidence_custodian: ci-platform

execution:
  triggers:
    - pre-release
    - scheduled-nightly
  environment: integration-checkout
  data_profile: synthetic-checkout-v3

evidence:
  report_type: junit-and-summary
  artifact_location: "approved-ci-artifact-store"
  retention: "according-to-test-evidence-policy"
  access: team-and-release-review

governance:
  review_cycle: quarterly
  change_notification: required
  flaky_test_owner_required: true
  handoff_required: true
  lifecycle: active
~~~

Mẫu này chỉ minh họa các trường cần quản lý. Tên nhóm, môi trường, đường dẫn và chu kỳ review cần theo quy ước thực tế. Không ghi secret hoặc thông tin xác thực vào hồ sơ.

## 17. Mẫu thỏa thuận ownership liên nhóm

~~~text
ASSET:
PURPOSE AND RISK:
ACCOUNTABLE OWNER:
SUITE/EVIDENCE OWNER:
BACKUP OWNER:
CONSUMER TEAMS:
PROVIDER/DEPENDENCY TEAMS:

CHANGE NOTIFICATION:
- Thay đổi cần thông báo:
- Kênh và thời điểm:
- Thông tin phiên bản/contract cần cung cấp:

EXECUTION AND EVIDENCE:
- Trigger/cadence:
- Môi trường và dữ liệu:
- Report/artifact location:
- Access and retention:

FAILURE HANDLING:
- Ai triage:
- Ai sửa test:
- Ai sửa service:
- Ai xử lý môi trường:
- Escalation path:

HANDOFF:
- Điều kiện thay owner:
- Người nhận và backup:
- Tài liệu/quyền cần bàn giao:

REVIEW:
- Chu kỳ:
- Ngày review tiếp:
- Người xác nhận:
~~~

Thỏa thuận cần ngắn gọn, có thể tra cứu và được các nhóm liên quan xác nhận. Không thay thế hợp đồng API hoặc policy bảo mật; nó xác định cách các nhóm cùng duy trì bằng chứng và bộ kiểm thử.

## 18. Những sai lầm thường gặp

- **Chỉ gán owner cho repository:** không biết ai chịu trách nhiệm cho từng suite hoặc nhóm evidence.
- **Gán nhiều accountable owner ngang nhau:** không rõ ai quyết định khi có tranh chấp.
- **Giao trách nhiệm nhưng không có quyền:** owner không thể sửa hoặc yêu cầu xử lý.
- **Nhầm người chạy test với người sở hữu test:** pipeline chạy tự động nhưng không ai duy trì nội dung.
- **Nhầm evidence custodian với evidence owner:** nơi lưu report có trách nhiệm về storage, không tự xác nhận nội dung.
- **Đẩy toàn bộ chất lượng cho QA:** service team không cập nhật test và không chịu trách nhiệm về hành vi dịch vụ.
- **Không có backup owner:** tài sản bị bỏ trống khi người chính vắng mặt.
- **Không ghi consumer:** thay đổi suite hoặc report làm nhóm khác mất bằng chứng mà không được thông báo.
- **Không quản lý fixture và dữ liệu:** test fail do dữ liệu lỗi thời nhưng không rõ ai sửa.
- **Không gắn suite với rủi ro:** nhóm không biết test nào quan trọng khi cần ưu tiên.
- **Không có quy trình bàn giao:** tri thức về môi trường, seed và flaky test bị mất.
- **Không review registry:** owner, link và phạm vi không còn đúng.
- **Giữ test quarantined vô thời hạn:** khoảng trống bao phủ tồn tại mà không có quyết định.
- **Lưu bằng chứng không kiểm soát quyền:** report có thể làm lộ dữ liệu nhạy cảm.
- **Dùng RACI thay cho trao đổi:** ma trận tồn tại nhưng nhóm không thống nhất cách xử lý thực tế.

## 19. Checklist thống nhất ownership

### Khi kiểm kê và phân công

- [ ] Bộ test và nhóm bằng chứng trọng yếu đã được liệt kê.
- [ ] Mỗi tài sản có ID, mục đích, phạm vi và rủi ro liên quan.
- [ ] Có một accountable owner rõ ràng cho từng phạm vi.
- [ ] Suite owner, evidence owner và evidence custodian được phân biệt khi cần.
- [ ] Có người thực hiện, reviewer và backup owner.
- [ ] Consumer và dependency team đã được ghi nhận.
- [ ] Owner có quyền và năng lực cần thiết để thực hiện trách nhiệm.

### Khi vận hành

- [ ] Trigger, cadence, môi trường và dữ liệu được ghi.
- [ ] Test fail/flaky có quy trình triage và owner.
- [ ] Bằng chứng gắn với đúng build, run, environment và thời điểm.
- [ ] Artifact có nơi lưu, quyền truy cập và thời hạn lưu.
- [ ] Finding và khoảng trống bao phủ có owner và hạn xử lý.
- [ ] Thay đổi từ provider được thông báo cho suite owner và consumer.

### Khi thay đổi hoặc bàn giao

- [ ] Ownership được review khi nhóm, service hoặc dependency thay đổi.
- [ ] Người nhận có quyền truy cập và đã xác nhận tiếp nhận.
- [ ] Tài liệu, dữ liệu, pipeline, artifact và finding mở được bàn giao.
- [ ] Có owner tạm thời nếu chưa tìm được owner chính thức.
- [ ] Registry được cập nhật và consumer được thông báo.

### Khi cải tiến

- [ ] Theo dõi tài sản không owner, registry lỗi thời và finding chưa nhận.
- [ ] Theo dõi tuổi của flaky/quarantined test.
- [ ] Review suite trùng lặp hoặc không còn giá trị.
- [ ] Kiểm tra chất lượng và khả năng truy xuất evidence.
- [ ] Rà soát RACI và thỏa thuận liên nhóm theo thay đổi thực tế.

## Kết luận

Thống nhất ownership cho từng nhóm bằng chứng và bộ kiểm thử giúp bảo đảm tài sản kiểm thử có người duy trì, kết quả có người xác nhận và rủi ro có người chịu trách nhiệm. Cần phân biệt service owner, suite owner, evidence owner, evidence custodian, specialist và release authority; chọn mô hình tập trung, liên kết hoặc chia sẻ theo năng lực phù hợp; ghi rõ trách nhiệm trong registry và RACI; thiết lập hợp đồng phối hợp, quy trình triage và bàn giao. Khi ownership gắn với quyền quyết định, bằng chứng có thể truy xuất và trách nhiệm được review định kỳ, chiến lược kiểm thử có thể duy trì qua thay đổi sản phẩm và tổ chức.
