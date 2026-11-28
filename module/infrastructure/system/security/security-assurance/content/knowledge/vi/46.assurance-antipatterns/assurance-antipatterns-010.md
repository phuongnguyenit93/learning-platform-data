# Báo cáo không phản ánh thực tế: Anti-pattern nguy hiểm trong Security Assurance

Một tổ chức công bố dashboard tháng: **98% tài sản đạt baseline**, **100% cảnh báo critical được xử lý**, **không có ngoại lệ bảo mật quá hạn**. Ban quản lý dựa vào ba chỉ số màu xanh để kết luận rủi ro đã được kiểm soát. Sau một sự cố rò rỉ dữ liệu, cuộc điều tra chỉ ra rằng scanner không có quyền đọc 20 cloud accounts mới, cảnh báo critical chưa xử lý bị loại vì ticket vẫn mở và nhiều ngoại lệ hết hạn được chuyển trạng thái sang “đang gia hạn”. Các phép tính trên tập dữ liệu mà dashboard dùng có thể hoàn toàn chính xác; **đối tượng đo, định nghĩa và cách trình bày mới là những phần không phản ánh thực tế**.

**Báo cáo không phản ánh thực tế** là một **anti-pattern của security assurance**: thông tin được tổng hợp, diễn giải hoặc trình bày khiến người ra quyết định hiểu sai tình trạng kiểm soát, mức phơi nhiễm, độ tin cậy của bằng chứng hoặc nghĩa vụ còn tồn tại. Sai lệch có thể đến từ lỗi kỹ thuật, số liệu không đầy đủ, định nghĩa chỉ số bất nhất, lựa chọn mẫu thiên lệch, thời điểm đánh giá không phù hợp, suy luận quá mức hoặc động cơ làm đẹp KPI; **không phải mọi sai lệch đều là gian lận cố ý**.

Trong chương **Anti-pattern assurance** của module **SECURITY_SECURITY_ASSURANCE**, bài học tập trung vào mục tiêu cốt lõi: **xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật** qua phân tích rủi ro, yêu cầu và security controls, kiểm thử, audit, xử lý finding và khắc phục liên tục trong phát triển/vận hành. Một báo cáo tốt không nhất thiết luôn có màu xanh. Nó phải **trung thực về điều đã chứng minh, điều chưa biết, điều không đạt và giới hạn của kết luận**.

Sau bài học, người học có thể nhận diện sai lệch assurance reporting, xác định mẫu số và phạm vi đúng, phân biệt kết quả control với trạng thái workflow, đối chiếu dữ liệu nguồn và bằng chứng, phát hiện các kiểu làm đẹp số liệu, thiết kế báo cáo có thể tái lập, xử lý kết quả INCONCLUSIVE và xây dựng cơ chế kiểm tra độc lập giúp quyết định dựa trên rủi ro thực thay vì ảo giác an toàn.

## 1. Vì sao một báo cáo “đúng số” vẫn có thể sai bản chất?

Có ít nhất ba cấp độ đúng sai khác nhau:

1. **Arithmetic correctness — đúng phép tính:** công thức tính trên những bản ghi đã chọn trả kết quả chính xác.
2. **Measurement validity — đúng đối tượng đo:** population, mốc thời gian, định nghĩa “đạt”, quy tắc loại trừ và nguồn dữ liệu phù hợp câu hỏi.
3. **Decision validity — đúng mức suy luận:** kết luận gửi quản lý không vượt quá những gì evidence và rủi ro cho phép.

Ví dụ scanner báo 76 tài sản PASS trên 80 tài sản quét thành công, tức **76/80 = 95% trong tập đã kiểm tra**. Nhưng inventory production ghi 100 tài sản: 20 tài sản còn lại scanner không đọc được. Nếu dashboard ghi **“95% production assets compliant”**, nó đã chuyển từ một tỷ lệ trên tập kiểm tra sang kết luận cho toàn bộ population.

Báo cáo có căn cứ hơn là:

| Trạng thái | Số tài sản | Cách hiểu |
|---|---:|---|
| In scope theo inventory đối chiếu | 100 | Mẫu số mục tiêu. |
| Đã kiểm tra hợp lệ | 80 | 80% coverage theo số tài sản. |
| PASS trong tập đã kiểm tra | 76 | 95% pass rate **của 80 đã kiểm tra**. |
| FAIL trong tập đã kiểm tra | 4 | Có control gap được xác nhận. |
| Chưa kiểm tra/không đủ bằng chứng | 20 | Trạng thái **UNKNOWN/INCONCLUSIVE**, không tự gọi PASS hoặc FAIL. |
| Verified PASS trên tổng in-scope | 76 | 76% tài sản có bằng chứng PASS, không phải “tỷ lệ tuân thủ thật” của 100 tài sản. |

Như vậy, **95% tested-pass rate**, **80% assessment coverage**, **76% verified-pass coverage** là ba metric khác nhau. Không được chọn con số trông đẹp nhất rồi bỏ điều kiện đi kèm.

### 1.1. Điều gì nguy hiểm hơn việc tính sai?

Một lỗi cộng/trừ thường có thể tìm ra khi kiểm tra lại. Một **mẫu số sai, control criteria bị tráo nghĩa hoặc missing data bị che** có thể tồn tại nhiều kỳ vì biểu đồ vẫn nhất quán với logic đã lập trình. Chính tính nhất quán giả ấy dễ khiến lãnh đạo tin tưởng.

### 1.2. Khi nào anti-pattern xảy ra?

Sai lệch có thể xuất hiện tại mọi bước:

~~~mermaid
flowchart LR
    A["Thực tế: assets, configs, incidents, risk"] --> B["Sensing / collection"]
    B --> C["Normalize + correlate"]
    C --> D["Cohort + denominator"]
    D --> E["Tests / control verdicts"]
    E --> F["Aggregation + metrics"]
    F --> G["Dashboard / narrative"]
    G --> H["Quyết định quản trị"]
    I["Blind spots"] -.-> B
    J["Filtering bias"] -.-> D
    K["Weak evidence"] -.-> E
    L["Misleading presentation"] -.-> G
~~~

Không thể sửa anti-pattern chỉ bằng việc đổi màu biểu đồ nếu upstream population hoặc logic đánh giá sai.

## 2. Assurance report phải trả lời một claim cụ thể

Một **security assurance claim** là mệnh đề có thể phản biện, ví dụ:

> “Mọi production account đang xử lý dữ liệu khách hàng trong phạm vi đánh giá đều có audit logs gửi tới kho tập trung, với độ trễ và retention phù hợp yêu cầu trong kỳ báo cáo.”

Một claim như vậy đòi xác định:

- **Security objective:** có thể truy vết hành động quan trọng để phát hiện và điều tra.
- **Requirement/control:** rule nào, version nào, áp dụng cho hệ thống nào.
- **Population:** danh sách account/service/data flow có scope rõ.
- **Evidence:** cấu hình log, event nguồn, synthetic test, ingest, collector health và retention.
- **Time:** trạng thái tại một mốc hay liên tục trong cả kỳ.
- **Warrant:** tại sao những phép thử và dữ liệu nguồn đủ sức hỗ trợ kết luận.
- **Limitations:** event types chưa thử, region chưa có quyền, những đoạn mất pipeline.
- **Verdict:** PASS, FAIL, INCONCLUSIVE hoặc NOT_APPLICABLE cho tiêu chí được nêu.

Báo cáo “Logging: 99,9%” không trả lời được claim nếu không biết **99,9% cái gì**: thời gian SIEM uptime, tỷ lệ sự kiện nhận, số source có cấu hình, hay lượng log sau lọc.

### 2.1. Những câu khẳng định không tương đương

| Câu báo cáo | Điều được chứng minh nếu evidence phù hợp | Điều không thể suy ra |
|---|---|---|
| “SIEM online 99,9% thời gian.” | Dịch vụ đích sẵn sàng theo phép đo uptime. | Mọi source đã gửi đúng, đủ event quan trọng. |
| “95% agent EDR online.” | Độ phủ agent trên tập endpoint xác định. | 95% cuộc tấn công được phát hiện. |
| “100% security tests PASS.” | Các test **đã chạy hợp lệ** đạt trong scope được kiểm. | Không có lỗ hổng hoặc mọi required test đã chạy. |
| “Mean Time to Respond = 8 phút.” | Trung bình trên tập incident/case đủ điều kiện theo T0/T1 đã định nghĩa. | Mọi incident critical phản ứng đúng hạn; containment thành công. |
| “0 high vulnerabilities.” | Không tìm thấy trong nguồn và phiên bản scanner được khai báo. | Toàn hệ thống không có lỗ hổng high hoặc scanner có coverage đầy đủ. |
| “Exception approved.” | Có quyết định đúng quyền và điều kiện nếu đã được kiểm chứng. | Control gốc PASS hoặc nghĩa vụ ngoài tổ chức được miễn. |

Một dashboard chỉ có ý nghĩa khi **nhãn hiển thị không mạnh hơn độ tin cậy của claim**.

## 3. Nhận diện các nhóm anti-pattern báo cáo phổ biến

| Anti-pattern | Cách biểu hiện | Rủi ro phát sinh |
|---|---|---|
| **Vanity metrics** | Đếm số scan, ticket đóng, alert xử lý mà bỏ hiệu lực control. | Quản lý nghĩ hoạt động nhiều là an toàn hơn. |
| **Greenwashing of status** | Đổi INCONCLUSIVE, EXPIRED, RISK_ACCEPTED thành PASS. | Che tình trạng không đáp ứng và rủi ro còn lại. |
| **Denominator manipulation** | Chỉ tính asset online/đã quét hoặc case đã đóng. | Loại những đối tượng khó hoặc chưa giải quyết. |
| **Survivorship bias** | MTTD/MTTR từ incident phát hiện/đã phản ứng, bỏ incident chưa phản ứng. | Đánh giá thấp độ trễ và mức thất bại. |
| **Stale evidence** | Giữ verdict PASS từ nhiều tuần trước sau khi runtime thay đổi. | Báo an toàn theo trạng thái không còn tồn tại. |
| **Scope leakage** | Dùng test staging để tuyên bố production hoặc region A để tuyên bố toàn cloud. | Kết luận vượt phạm vi evidence. |
| **False precision** | Score “98,734% secure” từ thang điểm chủ quan. | Tạo vẻ chính xác định lượng giả. |
| **Aggregation masking** | Gộp critical với hàng nghìn low để che trường hợp rủi ro lớn. | Không thấy hotspot dù trung bình đẹp. |
| **Metric drift** | Đổi công thức, source hoặc severity rubric mà không version. | So sánh trend không hợp lệ. |
| **Proxy substitution** | Dùng “PR merged” thay cho “fix verified”, ACK thay response. | Đếm quy trình thay vì outcome. |
| **Missingness is success** | Không có log/alert được hiểu là không có tấn công. | Lỗi collector biến thành màu xanh. |
| **Unreviewed exceptions** | Gia hạn hạn/waiver, hạ severity mà không lưu quyết định. | Báo cáo vô tình hợp thức hóa noncompliance. |
| **Cherry-picking** | Chỉ chọn tháng, sample, sản phẩm có số đẹp. | Ban quản lý không thấy rủi ro toàn bộ danh mục. |
| **Untraceable aggregates** | Chỉ có KPI tổng, không drill-down tới evidence. | Audit không thể tái tính hoặc kiểm tra kết luận. |

Những tên gọi mô tả nhóm lỗi, không phải danh mục chuẩn bắt buộc. Một hệ thống có thể đồng thời mắc nhiều anti-pattern; cách xử lý phải bắt đầu từ **mục đích ra quyết định** và **chuỗi chứng cứ thực tế**.

## 4. Anti-pattern 1: Dùng sai mẫu số và population

Mẫu số không chỉ là một con số trong công thức. Nó là quyết định nghiệp vụ về **đối tượng đáng lẽ phải được bảo vệ**.

### 4.1. Những cách bỏ sót phổ biến

- Chỉ lấy tài sản đã đăng ký trong CMDB, bỏ tài khoản cloud mới.
- Chỉ đo những host có agent, bỏ host không cài được agent.
- Chỉ lấy scanner results có status `SUCCESS`, bỏ `ERROR` và `TIMEOUT`.
- Chỉ tính managed Kubernetes namespaces, bỏ cluster được tạo thủ công.
- Chỉ tính identity nhân viên, bỏ service accounts, emergency users và vendor accounts.
- Chỉ tính incidents đã đóng, bỏ incidents pending/overdue.
- Chỉ xét một region hay tenant vì collector ở vùng khác không đủ quyền.
- Chỉ đếm vulnerabilities trên image đang chạy mà bỏ tài sản tồn tại ngoài container platform.

### 4.2. Mẫu số chuẩn phải đến từ đâu?

Tùy mục tiêu, xác định **authoritative/inventory population** từ cloud organization APIs, directory/IdP, service catalog, asset management, data catalog và runtime discovery. Không có một nguồn duy nhất luôn hoàn chỉnh, nên cần **reconciliation** giữa ít nhất những nguồn liên quan theo rủi ro.

Một metric contract phải nói rõ:

~~~text
Population definition:
  Production assets in accounts owned by organization X
  Processing customer data during reporting window
  Includes newly created and temporarily offline resources
  Excludes only approved out-of-scope assets with rationale

Assessment population:
  Assets with a valid control test under approved test method

Unassessed population:
  In-scope assets lacking complete/valid evidence
~~~

### 4.3. Công thức minh bạch

Với `N_scope` đối tượng trong phạm vi, `N_tested` được kiểm tra hợp lệ và `N_pass` có verdict PASS:

\[
\operatorname{Coverage} = \frac{N_{tested}}{N_{scope}}
\]

\[
\operatorname{TestedPassRate} = \frac{N_{pass}}{N_{tested}}
\]

\[
\operatorname{VerifiedPassCoverage} = \frac{N_{pass}}{N_{scope}}
\]

Khi mẫu số bằng 0, **không tự ghi 100%**; phải nêu trường hợp `N/A` có căn cứ hoặc `undefined`/không thể tính theo metric contract. Nếu population chưa đầy đủ, ba tỷ lệ đều có **hạn chế coverage** và không được xem là toàn bộ sự thật.

## 5. Anti-pattern 2: Tự chuyển UNKNOWN, FAIL hoặc ngoại lệ thành PASS

Security assurance có ít nhất ba lớp thường bị gộp sai:

1. **Control effectiveness:** control thực sự đạt tiêu chí chưa?
2. **Governance status:** vấn đề/ngoại lệ được ghi nhận, đúng thẩm quyền và theo dõi chưa?
3. **Residual risk/compliance:** rủi ro còn lại và nghĩa vụ bên ngoài được xử lý thế nào?

Ví dụ một máy chủ chưa vá lỗ hổng theo hạn nội bộ nhưng có firewall segmentation được test và risk owner chấp thuận ngoại lệ 30 ngày.

| Trục | Kết luận có thể đúng cùng lúc |
|---|---|
| Patch control theo baseline | **FAIL** trên server tại thời điểm đánh giá. |
| Compensating network control | **PASS** trong các đường được kiểm tra, có giới hạn rõ. |
| Exception authorization | **PASS** về thủ tục nếu còn hạn, đúng quyền/scope. |
| Permanent remediation | **IN_PROGRESS** hoặc **NOT_STARTED**. |
| External contractual compliance | **UNKNOWN/INCONCLUSIVE** nếu chưa đối chiếu nghĩa vụ. |
| Residual risk | **ACCEPTED_WITH_CONDITIONS**, không đồng nghĩa “an toàn”. |

Nếu dashboard tổng hợp record có exception vào `compliant=true`, nó có thể **che control failure**. Kết luận được phép vận hành có điều kiện **không phải chứng cứ control gốc đã đạt**.

### 5.1. Một phép ánh xạ trạng thái nguy hiểm

~~~text
BAD:
  if ticket.closed or exception.approved or scanner.unreachable:
      control_result = PASS

SAFER:
  control_result = evaluate_original_requirement(evidence)
  exception_status = assess_exception_authority_and_validity()
  residual_risk = evaluate_risk_with_verified_compensating_controls()
  remediation_status = assess_fix_and_independent_retest()
  external_obligations = review_applicable_requirements_separately()
~~~

Đây là pseudocode mô tả cách tách trục, không phải script triển khai.

### 5.2. “Không áp dụng” phải có cơ sở

`NOT_APPLICABLE` không dành cho hệ thống khó test, asset không có owner hay scanner chưa hỗ trợ. Phải chứng minh **requirement thật sự không áp dụng** với scope và thời kỳ, cùng người phê duyệt nếu quy trình yêu cầu.

## 6. Anti-pattern 3: Báo cáo trạng thái workflow thay cho hiệu lực bảo mật

Một pipeline có thể hoàn tất, ticket có thể đóng, nhưng control vẫn sai.

| Proxy dễ đo | Kết luận sai thường gặp | Evidence cần bổ sung |
|---|---|---|
| PR merge thành công | “Vulnerability fixed.” | Artifact triển khai đúng asset, retest attack path và regression. |
| Configuration applied | “IAM least privilege PASS.” | Effective permissions, allow/deny tests trên identities có liên quan. |
| WAF rule enabled | “Attack prevented.” | Negative traffic tests, bypass coverage, telemetry và residual risk. |
| EDR agent installed | “Endpoint protected.” | Agent healthy, policy nhận, detection/response tests phù hợp. |
| Alert acknowledged | “Incident responded/contained.” | Action có ý nghĩa, execution/outcome và containment confirmation. |
| Backup job succeeded | “System recoverable.” | Restore rehearsal, decrypt dependencies và integrity verification. |
| Audit policy enabled | “Logs complete.” | Event nguồn tới SIEM, coverage, retention và collector health. |
| Risk acceptance signed | “Finding remediated.” | Control retest hoặc quyết định governance được báo ở trục riêng. |

### 6.1. Action evidence và outcome evidence

Nên phân biệt **requested**, **executed**, **effective** và **verified**. Một lệnh revoke session được gửi chưa chứng minh session thực tế đã mất hiệu lực; một task cấu hình IAM thành công chưa chứng minh role cache đã cập nhật tại runtime. Bằng chứng phải khớp với **mức độ claim**.

## 7. Anti-pattern 4: Dùng evidence lỗi thời hoặc không đúng môi trường

Một kết quả kiểm thử chỉ hỗ trợ kết luận trong **điều kiện, phạm vi và thời điểm** được kiểm tra. Trong hạ tầng vận hành liên tục, thay đổi mới có thể làm mệnh đề cũ không còn đại diện.

### 7.1. Những thay đổi cần invalidate hoặc trigger review

- Deploy artifact/config khác bản đã được test và phê duyệt.
- Thêm account, region, tenant, human/machine identity hoặc public endpoint.
- Thay trust boundary, federation hoặc privilege model.
- Đổi route của audit logs, parser, retention hoặc nguồn telemetry.
- Rotate KMS key ảnh hưởng backup/restore.
- Vendor thêm subprocessor, thay data region hoặc API logging.
- Control bù trừ mất hiệu lực, exception hết hạn.
- Threat intelligence mới làm kịch bản rủi ro đổi đáng kể.
- Một incident chứng minh giả định bảo vệ có thể sai.

### 7.2. Point-in-time và period-wide evidence

| Câu hỏi | Evidence phù hợp | Cạm bẫy |
|---|---|---|
| IAM role hiện có quyền gì? | Effective policy và access tests tại thời điểm T. | Không thể nói role chưa từng có quyền rộng trong cả tháng. |
| Trong cả tháng log có liên tục không? | Config history, source monitoring, gap analysis, synthetic checks trong kỳ. | Một screenshot SIEM hôm nay không chứng minh cả kỳ. |
| Release chạy đúng bản đã duyệt? | Build digest, deployment observed digest, manifest và approval scope. | Chỉ đối chiếu tên release tag mutable. |
| Backup mới nhất restore được? | Backup metadata, key access và restore test theo scope phù hợp. | Restore test của tháng trước không đại diện cho schema/key mới. |

### 7.3. Một “PASS” phải có validity boundary

Một assurance verdict nên ghi **scope, assessed_at, valid_for/assumptions và invalidation triggers**. Không nên coi PASS là trạng thái vĩnh viễn. Khi trigger xảy ra, có thể đặt verdict hiện tại ở trạng thái **REASSESSMENT_REQUIRED** mà vẫn giữ lịch sử PASS đúng tại thời điểm trước đó.

## 8. Anti-pattern 5: Lấy tình trạng công cụ làm đại diện toàn bộ hệ thống

Dashboard từ một scanner, SIEM hay GRC vendor thường chỉ quan sát **những gì công cụ có nguồn, quyền và rule để quan sát**.

### 8.1. Scanner “không thấy lỗi” có thể có nghĩa gì?

- Không có finding trong **mẫu đã scan** với **rule/version** đó.
- Scanner thiếu quyền hoặc không thấy đường tấn công nằm ngoài bộ test.
- Asset vừa sinh chưa được onboard.
- Scanner gặp timeout nhưng hệ thống loại hàng lỗi khỏi KPI.
- Một CVE chưa có detection plugin/signature hoặc runtime path khác ảnh hưởng mức khai thác.
- Policy baseline cần kiểm tra vận hành nhưng công cụ chỉ đọc cấu hình tĩnh.

Vì thế câu “zero detected findings” **không đồng nghĩa** “zero vulnerabilities”.

### 8.2. Tự đánh giá độ phủ collector

| Kiểm tra | Câu hỏi |
|---|---|
| **Account/asset reconciliation** | Các tài sản trong inventory có cùng tập với scanner/SIEM? |
| **Collector authorization** | Token/API scope có đọc hết account, region, resource types? |
| **Source health** | Heartbeat, last successful pull, API errors và dead-letter queue? |
| **Rule coverage** | Những controls/threat scenarios nào công cụ thật sự kiểm tra? |
| **End-to-end synthetic test** | Event thử từ nguồn tới kết quả có đến đúng nơi và cảnh báo? |
| **Pagination/filters** | Data export có bỏ trang, loại status ERROR hay cắt vì quota? |
| **Sample inspection** | Asset quan trọng được kiểm chứng thủ công đối chiếu kết quả tự động? |

Nếu collector không có quyền, đây có thể là **evidence gap**; không tự khẳng định control failure cũng không báo PASS. Cần khắc phục đường quan sát trước khi đưa ra kết luận rộng.

## 9. Anti-pattern 6: Gộp dữ liệu không đồng chất để che rủi ro cao

Một số báo cáo trình bày một giá trị trung bình duy nhất cho nhiều nhóm severity/asset khác nhau.

### 9.1. Một ví dụ so sánh hai tháng

Giả sử Mean Time to Respond (mốc T0/T1 được định nghĩa nhất quán) của các incident **đã phản ứng**:

| Nhóm | Tháng A | Tháng B |
|---|---:|---:|
| Critical: số incident và mean | 10 incident, 12 phút | 5 incident, 18 phút |
| Low: số incident và mean | 90 incident, 5 phút | 195 incident, 4 phút |
| Mean tổng (trọng số theo số incident) | (10×12 + 90×5)/100 = **5,7 phút** | (5×18 + 195×4)/200 = **4,35 phút** |

Mean tổng giảm từ 5,7 xuống 4,35 phút, nhưng **critical response chậm hơn từ 12 lên 18 phút**. Nếu báo cáo chỉ ghi “response improved 24%” sẽ che rủi ro chính. Thay đổi phân bổ có thể gây hiện tượng **đảo chiều khi gộp nhóm**; phải phân đoạn theo severity, service, criticality, nguồn phát hiện và duty coverage.

### 9.2. Các nhóm không được gộp tùy tiện

- Production và development nếu nghĩa vụ/rủi ro khác nhau.
- Critical data và public assets.
- Human admin và machine identity.
- True incident và false positive triage.
- Risk accepted và verified fixed.
- PASS và INCONCLUSIVE.
- Bên cung cấp có quyền xử lý dữ liệu và bên chỉ cung cấp hạ tầng phụ trợ.
- Các kỳ dùng nguồn hoặc logic scoring khác nhau.

Phân nhóm không phải để “chia nhỏ KPI cho dễ đẹp”, mà để **thể hiện sự thật giúp ra quyết định đúng**.

## 10. Anti-pattern 7: Survivorship bias và dữ liệu chưa hoàn tất

Chỉ thống kê những trường hợp đã có kết quả hoàn chỉnh dễ tạo con số lạc quan.

### 10.1. Trường hợp incident response

Một nhóm SOC có 10 incident high-risk khởi phát trong kỳ, 8 incident đã có hành động response với duration 5–20 phút, 2 incident chưa có T1 và đã quá thời hạn phản ứng. Mean của 8 incident đã phản ứng có thể thấp, nhưng không đại diện cho **toàn bộ 10 incident**.

Cần báo ít nhất:

- Eligible incident cohort và quy tắc T0/T1.
- Responded có T1 hợp lệ.
- Pending/chưa phản ứng; bao nhiêu đã overdue.
- Missing/invalid timestamps và lý do.
- Mean/median/P90 của tập đã phản ứng với nhãn rõ.
- Tỷ lệ đạt SLO critical/high, gồm cách xử lý pending/unknown theo metric contract.

Chưa có T1 là **quan sát thời gian đến sự kiện chưa hoàn tất**, không gán duration = 0 cũng không âm thầm loại khỏi câu kết “tất cả được phản ứng kịp”.

### 10.2. Trường hợp remediation

Tương tự, **Mean Time to Remediate** tính trên findings đã đóng không phản ánh backlog có lỗi tồn tại hàng tháng. Báo thêm **open age, overdue, verified closure, reopen/recurrence, blockers và effective mitigation**.

### 10.3. Một trường hợp tồi tệ có thể quan trọng hơn mean

Nếu 99 incident low-risk được xử lý nhanh và một incident critical tồn tại chưa có containment, việc cải thiện mean không giải quyết rủi ro critical. **Severity-weighted view và worst-case review** giúp đặt ưu tiên đúng, nhưng phải ghi cách phân nhóm/trọng số thay vì tạo score chủ quan không giải thích được.

## 11. Anti-pattern 8: Định nghĩa chỉ số thay đổi âm thầm

Có những tháng hệ thống dùng “response = ACK”, tháng sau dùng “response = containment”; hoặc thay scanner làm thay đổi population, detection rules và cách gán severity.

### 11.1. Metric contract phải versioned

| Trường | Nội dung cần chốt |
|---|---|
| **metric_id/version/name** | Tên đủ rõ, phân biệt MTTR (respond) với MTTR (recover). |
| **business/security question** | Chỉ số giúp quyết định gì và liên quan control nào? |
| **observation unit** | Alert, incident, asset, user, service, finding hay event? |
| **population & exclusions** | Scope, nguồn inventory, điều kiện đủ, reason code. |
| **start/end or PASS criterion** | T0/T1, detection logic, test method và các ngưỡng. |
| **time basis** | UTC/elapsed/business hours, kỳ quan sát, xử lý late events. |
| **data sources** | API/query, rule/tool version, schema và owner. |
| **missingness rule** | Pending, ERROR, UNKNOWN, N/A được báo thế nào? |
| **aggregation** | Mean, median, percentile, count, weighted risk và group breakdown. |
| **quality checks** | Completeness, dedup, range, clock, reconciliation và outcome. |
| **approval and change history** | Ai duyệt thay đổi định nghĩa, ngày hiệu lực, cách backfill/trend. |

### 11.2. Quy tắc so sánh thời gian

Khi đổi công cụ hoặc metric contract, có ba hướng:

1. **Backfill có công bố:** tính lại kỳ trước bằng công thức mới và nguồn hợp lệ nếu dữ liệu còn đủ.
2. **Dual-run:** một thời gian chạy song song công thức cũ/mới để hiểu sai khác.
3. **Break series:** đánh dấu đường gãy và không kết luận xu hướng liên tục nếu không so được.

Không tạo đồ thị nối hai tập số liệu không tương thích mà không ghi chú; người xem dễ hiểu nhầm “tháng này tốt hơn”.

## 12. Anti-pattern 9: Ngưỡng PASS tùy tiện và độ chính xác giả

Một công cụ có thể trả “Security Score 92”, nhưng điểm này là **hàm của trọng số, phạm vi, mapping và dữ liệu hiện có**, không phải xác suất 92% an toàn.

### 12.1. Phải giải thích score

Nếu tổ chức dùng composite score, cần công khai:

- Những controls nào được chấm và lý do lựa chọn.
- Thang điểm, trọng số và phương pháp aggregation.
- Cách xử lý critical control FAIL, unknown và ngoại lệ.
- Tập tài sản, data criticality và rủi ro không đo được.
- Phương pháp kiểm định mối liên hệ giữa score với mục tiêu rủi ro.
- Sensitivity khi đổi trọng số, thêm nhóm asset hoặc thay scanner.
- Những trường hợp một score cao **vẫn không đủ để cho phép release**.

### 12.2. Một tỷ lệ chung không thay gate bắt buộc

Một môi trường có 99/100 controls PASS nhưng **control còn lại** là bảo vệ truy cập dữ liệu khách hàng có thể không đáp ứng mức rủi ro chấp nhận được. Không nên dùng “99% compliant” để bỏ qua mandatory gate.

### 12.3. Khi nào dùng ngưỡng?

Một ngưỡng chỉ có ý nghĩa khi **gắn với yêu cầu, risk appetite, SLO/contract hoặc tiêu chí đã được phê duyệt**. Không được hạ ngưỡng sau khi kết quả xấu mà thiếu decision history. Một threshold thay đổi có thể là quyết định hợp lệ nhưng phải diễn giải và phê duyệt đúng quyền.

## 13. Anti-pattern 10: Trình bày gây hiểu lầm ngay cả khi dữ liệu đúng

Cách hiển thị có thể làm người xem bỏ sót rủi ro.

| Cách trình bày | Vì sao sai lệch | Cách khắc phục |
|---|---|---|
| Chỉ có một thẻ màu xanh “Secure”. | Gộp nhiều claim khác nghĩa. | Tiêu chí và kết luận theo control, severity và scope. |
| Tỷ lệ % không có mẫu số. | Không biết 99% của 10 hay 10.000 quan sát. | Luôn ghi numerator, denominator, cohort. |
| Không hiển thị UNKNOWN. | Biến thiếu dữ liệu thành bình thường. | Hiển thị số/percentage chưa đánh giá và lý do. |
| Dùng màu xanh cho RISK_ACCEPTED. | Làm người xem tưởng lỗi đã sửa. | Trạng thái riêng với residual risk và expiry. |
| Cắt trục hoặc đổi đơn vị không ghi chú. | Làm thay đổi nhỏ nhìn như đột biến lớn. | Ghi đơn vị, trục, baseline và version. |
| Chỉ chọn tuần tốt nhất. | Cherry-picking, che tình trạng xấu trước đó. | Kỳ báo cáo cố định và lý do exclusion. |
| Không hiển thị critical outliers. | Mean tổng che những ca nguy hiểm. | Phân đoạn theo rủi ro và overdue worst cases. |
| Dùng biểu đồ trend dù đổi công thức. | Người xem hiểu nhầm nguyên nhân cải thiện. | Annotation, dual-run hoặc tách series. |
| Đổi “PASS” thành “compliant” trên slide. | Kéo dài kết luận sang nghĩa vụ bên ngoài chưa được đánh giá. | Đặt tiêu đề đúng phạm vi và loại assessment. |
| Kết luận vượt kỳ đánh giá. | PASS ở thời điểm T bị coi là bao phủ cả năm. | Reporting period, freshness và invalidation triggers. |

**Nghệ thuật trình bày không thay thế kỷ luật chứng cứ.** Một dashboard tối giản có thể rất hữu ích, nhưng cần drill-down và chú thích rủi ro trọng yếu; không che thông tin cần thiết chỉ để slide đẹp.

## 14. Ranh giới giữa dữ liệu, inference và quyết định quản trị

Security assurance cần tách **facts, assessment, judgment và decision**.

~~~mermaid
flowchart TD
    A["Raw source + timestamp + integrity"] --> B["Observed facts / effective state"]
    B --> C["Tests theo requirement & scope"]
    C --> D["Control verdict + assumptions + limitations"]
    D --> E["Risk assessment / residual risk"]
    E --> F["Authority decision / action"]
    F --> G["Release/operate/remediate/retest"]
    G --> H["Evidence và review version mới"]
~~~

### 14.1. Một ví dụ cụ thể

- **Fact:** audit event nguồn ghi service account được gán role admin lúc 10:10.
- **Assessment cần thêm:** role có effective rights nào sau inheritance, scope và phiên hiện hành?
- **Control verdict:** FAIL nếu kiểm chứng role vượt least privilege theo policy.
- **Risk analysis:** mức phơi nhiễm có thể khai thác, dữ liệu, impact, threat context.
- **Decision:** revoke, emergency containment, remediation hoặc exception đúng quyền nếu được phép.
- **Report:** không ghi “đã kiểm soát” chỉ vì alert tạo ticket hay risk owner đã xem.

### 14.2. Mỗi lớp có chủ sở hữu khác nhau

Người vận hành nguồn dữ liệu chịu trách nhiệm telemetry, control owner xác định tiêu chí, assessor kiểm tra bằng chứng, risk owner quyết định risk treatment, change/incident authority thực thi theo quyền. Nhập các vai trò vào một trường `approved_by` có thể làm mất khả năng kiểm tra ai chịu trách nhiệm về điều gì.

## 15. Đối chiếu dữ liệu nguồn (reconciliation) trước khi tin báo cáo

Kỹ thuật đối chiếu giúp phát hiện trường hợp chỉ số đẹp vì bỏ sót.

### 15.1. Reconciliation theo tập hợp

Giả sử:

- `Inventory`: toàn bộ production assets trong scope theo nguồn đối chiếu.
- `Assessment`: assets có kiểm thử hợp lệ trong kỳ.
- `PASS`: subset của Assessment có control verdict PASS.

Cần tính:

~~~text
Unassessed   = Inventory - Assessment
Unexpected   = Assessment - Inventory
VerifiedPass = PASS intersection Inventory
VerifiedFail = FAIL intersection Inventory
Ambiguous    = records with missing IDs / duplicates / stale snapshots
~~~

`Unassessed` không tự là FAIL nhưng **ngăn claim về toàn bộ population**. `Unexpected` có thể là asset bị bỏ trong inventory hoặc đối tượng ngoài scope bị scanner đếm nhầm; phải kiểm tra nguyên nhân, không tự xóa record.

### 15.2. Dữ liệu cần cùng identity và thời điểm

Một VM có thể đổi IP, pod có thể bị thay, identity đổi display name. Join theo tên dễ tạo đếm lặp hoặc bỏ qua. Dùng canonical resource IDs, cloud account, region, cluster và time-aware keys phù hợp; lưu quan hệ merge/split. Không so inventory cuối tháng với scan đầu tháng mà không ghi các assets sinh/hủy trong khoảng đó.

### 15.3. Kiểm tra chất lượng tối thiểu

| Kiểm tra | Biểu hiện lỗi | Phản ứng đúng |
|---|---|---|
| **Completeness** | Không đủ assets hoặc API pages. | Flag coverage gap, retry/reconcile. |
| **Validity** | Timestamp âm, severity ngoài enum, test result lạ. | Quarantine, source review. |
| **Uniqueness** | Một finding xuất hiện nhiều lần bởi scanners khác nhau. | Canonical ID, mapping và dedup có lịch sử. |
| **Consistency** | Ticket `CLOSED` nhưng retest còn FAIL. | Giữ conflict, điều tra state mapping. |
| **Timeliness** | Data cũ hơn ngưỡng freshness đã duyệt. | Refresh, báo stale hoặc invalidated. |
| **Referential integrity** | Evidence không có asset/control/release link. | Không đưa vào claim chưa xác minh. |
| **Provenance** | Chỉ có số tổng từ spreadsheet, không rõ query. | Yêu cầu raw/source snapshot, lineage. |
| **Scope mapping** | Có account ngoài mẫu số hoặc region thiếu. | Xác minh authoritative population. |
| **Action outcome** | SOAR request accepted nhưng endpoint chưa đổi. | Verify effective state và retest. |

### 15.4. Không xóa dấu vết dữ liệu lỗi

Nếu source trả lỗi, cần lưu **error code, timestamp, collector identity, scope và số lượng ảnh hưởng**. Không sửa data file thủ công để dashboard xanh mà không có audit trail; các bước làm sạch phải có transform version và kiểm thử.

## 16. Tái lập một chỉ số từ báo cáo tới bằng chứng gốc

Một phép kiểm toán mạnh là chọn ngẫu nhiên một con số rồi hỏi **có thể truy lại toàn bộ record nào tạo ra nó không?**

~~~mermaid
flowchart LR
    KPI["Dashboard KPI + period"] --> DEF["Metric contract/version"]
    DEF --> POP["Population/denominator snapshot"]
    POP --> REC["Canonical records + inclusion/exclusion reasons"]
    REC --> TEST["Control test verdict + method + scope"]
    TEST --> RAW["Raw source evidence + collector"]
    RAW --> AUD["Integrity, authority, reviewer and history"]
~~~

### 16.1. Trình tự audit gợi ý

1. Chọn KPI có ảnh hưởng quyết định lớn: critical SLO, patch compliance, logging coverage, exception expiry.
2. Lấy **đúng definition version và reporting window** đã dùng.
3. Lấy source population và đối chiếu owner/scope bằng nguồn độc lập.
4. Tái chạy filter/join/aggregation hoặc kiểm tra per-record derivation.
5. Trích mẫu gồm PASS, FAIL, UNKNOWN, duplicate, excluded và case quá hạn.
6. Đối chiếu raw evidence với control tiêu chí gốc và thời điểm.
7. Kiểm tra approval của exceptions, risk decisions và thay đổi metric.
8. Ghi phát hiện, nguyên nhân, ảnh hưởng tới những quyết định đã dựa trên KPI.
9. Sửa pipeline/contract, backfill hoặc đánh dấu series không thể so sánh.
10. Retest bằng bộ dữ liệu có trường hợp thành công và thất bại, lưu sign-off.

### 16.2. Các câu hỏi phản chứng

- Nếu scanner mất quyền đọc một region, dashboard có chuyển từ PASS sang **coverage warning** không?
- Nếu incident chưa phản ứng, nó xuất hiện ở **pending/overdue** hay biến mất khỏi biểu đồ?
- Nếu exception hết hạn, control còn FAIL có được hiển thị?
- Nếu deployment dùng digest khác bản review, release status có bị invalidate?
- Nếu source log không có event trong 24 giờ, có health check/synthetic test nào phát hiện?
- Nếu một tài sản critical mới được thêm, mẫu số có tăng đúng lúc?

Nếu pipeline vẫn báo xanh trước các trường hợp cố ý tạo dữ liệu thiếu, nó chưa đủ cơ sở để được coi là **assurance reporting đáng tin**.

## 17. Kiểm thử báo cáo bằng positive, negative và fault-injection cases

Không chỉ test công thức với một bảng hoàn hảo. Cần xây dựng **test vectors** để xác minh pipeline xử lý đúng tình huống xấu.

| Test case | Dữ liệu thử | Kết quả mong đợi |
|---|---|---|
| **Known PASS** | Asset có control test đạt, nguồn hợp lệ. | PASS đúng phạm vi. |
| **Known FAIL** | Asset có config vi phạm và test xác nhận. | FAIL, không auto-override vì ticket đã tạo. |
| **No collector access** | API trả 403 cho một account. | INCONCLUSIVE/coverage gap, không PASS. |
| **Duplicate finding** | Hai scanner báo cùng lỗi trên một asset. | Không đếm thành hai asset hoặc hai risk scenarios giả. |
| **Expired exception** | Ngoại lệ quá hạn không renewal được duyệt. | Không tính là authorized active exception. |
| **Open overdue incident** | Có T0, chưa có response T1 và vượt SLO. | Hiển thị pending/overdue, không loại lặng lẽ. |
| **Stale release test** | Test trên digest A nhưng deploy digest B. | Không kết luận B đạt từ evidence A. |
| **Region population drift** | Tạo account/region mới trong scope. | Tăng denominator, yêu cầu enrollment/review. |
| **Clock skew** | Timestamp T1 sớm hơn T0 do nguồn lỗi. | Error quality, không ép duration = 0. |
| **Rule version change** | Scanner đổi severity rubric giữa hai kỳ. | Trend break hoặc backfill có công bố. |
| **Evidence tampering** | Artifact bị sửa sau khi chốt hash. | Integrity alert và điều tra provenance. |
| **Critical failure under high mean score** | Một control trọng yếu FAIL giữa nhiều PASS. | Không cho aggregate score che mandatory gate. |

Có thể dùng dữ liệu mô phỏng và test environment được phép, tránh sinh lỗ hổng thực hoặc vô hiệu hóa control production để “test dashboard”.

### 17.1. Kiểm thử cả presentation layer

Ngay cả khi pipeline tính đúng, UI có thể ẩn UNKNOWN, làm tròn 0,5% thành 100%, màu hóa RISK_ACCEPTED thành xanh hoặc rút ngắn mô tả “verified-pass coverage” thành “secure”. Cần xem bản xuất PDF/slide/dashboard mà lãnh đạo thực sự nhận được, không chỉ kiểm thử API backend.

## 18. Thiết kế lại dashboard assurance trung thực và hữu ích

Một báo cáo tốt **không phải dài tối đa**, mà là cung cấp đủ căn cứ để người quản lý biết **quyết định nào an toàn, điều gì chưa rõ và hành động gì cần làm**.

### 18.1. Một bố cục đề xuất

| Khối | Nội dung tối thiểu |
|---|---|
| **Executive risk summary** | Critical/high control failures, exposure và quyết định cần chủ sở hữu. |
| **Scope and confidence** | Population, coverage, data quality, unknown/invalid evidence. |
| **Control effectiveness** | PASS/FAIL/INCONCLUSIVE theo objectives và criticality. |
| **Exceptions and obligations** | Active/expired/unapproved, accepted risk và kết luận nghĩa vụ bên ngoài riêng. |
| **Incidents and response** | Critical pending/overdue, detection/response quality, confirmed outcomes. |
| **Remediation** | Verified fixed, overdue, blockers, time-to-retest, recurrence. |
| **Change/release** | Artifact match, gate failures, unauthorized deployments, rollbacks và post-release checks. |
| **Trend & method** | So sánh các kỳ tương thích, định nghĩa và điểm gãy. |
| **Evidence and audit** | Dataset snapshot, metric contract, drill-down và reviewer sign-off. |
| **Action agenda** | Ai quyết định gì, trong hạn nào, cần evidence/mitigation nào. |

### 18.2. Đưa uncertainty ra mặt tiền

Nếu 30% tài sản production chưa thể đánh giá, dòng **“30% unknown coverage”** phải xuất hiện cùng nhóm headline, không nằm trong ghi chú cuối báo cáo. Với high-risk controls, có thể cần cảnh báo riêng dù tỷ lệ unknown thấp do asset quan trọng.

### 18.3. Không tạo score “secure” duy nhất

Nếu người dùng cần một trạng thái điều hành, dùng **điều kiện cụ thể** như “critical blocking controls: 2 FAIL / 1 INCONCLUSIVE / 17 PASS”, kèm risk owner action. Một composite score có thể dùng bổ sung nếu model rõ, nhưng không thay mandatory gates.

### 18.4. Tách tỷ lệ kiểm chứng và tỷ lệ đáp ứng

Ví dụ:

~~~text
Scope: 100 in-scope assets
Assessment coverage: 80/100 (80%)
Verified PASS: 76/100 (76%)
Known FAIL: 4/100 (4%)
Not assessed / inconclusive: 20/100 (20%)
Pass rate on assessed: 76/80 (95%) — not fleet compliance
Critical controls: 2 FAIL, 1 INCONCLUSIVE
Owner for unknown: Cloud Assurance Lead
Next evidence review: per approved remediation plan
~~~

Bản tóm tắt ngắn này hữu ích hơn nhiều so với một thẻ “Compliance 95%” nếu người đọc cần quyết định đưa dữ liệu mới lên production.

## 19. Governance, trách nhiệm và xung đột động cơ KPI

Một anti-pattern báo cáo không chỉ là lỗi dashboard; thường có nguyên nhân sâu hơn ở quyền sở hữu và động cơ quản trị.

### 19.1. RACI minh họa

| Hoạt động | Responsible | Accountable | Reviewer/Consulted |
|---|---|---|---|
| Xác định security claim và control criteria | Security/Control Analyst | Control Owner | Risk/Compliance |
| Duy trì asset population | Cloud/Asset Engineering | Service/Asset Owner | Security Assurance |
| Vận hành collectors và source integrity | Platform/Observability | Data Source Owner | Security Engineering |
| Định nghĩa metric contract và aggregation | Metrics/Assurance Engineer | Assurance Program Owner | Risk, Audit |
| Xác thực kết quả control | Qualified Security Assessor | Control Owner | Engineering |
| Phê duyệt ngoại lệ hoặc residual risk | Authorized Business/Risk Owner | Risk Governance theo policy | Security, Legal khi cần |
| Review dashboard và kết luận management | Assurance Reviewer | Security Assurance Lead | Internal Audit/Risk |
| Xử lý finding dữ liệu và retest | Engineering/Data Owner | Relevant Service Owner | Independent Verifier |

Người có quyền sửa dữ liệu nguồn không nên có quyền **âm thầm thay metric definition, xóa findings và tự ký chứng nhận toàn bộ báo cáo** đối với các rủi ro quan trọng. Cần segregation of duties, audit trail và reviewer sampling phù hợp.

### 19.2. KPI pressure và Goodhart's law

Khi “100% tickets closed” trở thành chỉ tiêu thưởng, đội vận hành có thể chuyển ticket sang “accepted”, chia finding để giảm severity hoặc đổi hạn. Không nhất thiết có ý định gian lận ở mọi trường hợp; quy trình có thể khuyến khích hành động sai do định nghĩa KPI yếu.

Một thiết kế tốt dùng **nhiều thước đo bổ sung**: verified closure, reopen rate, residual risk, overdue critical, evidence quality, incident outcomes, và đánh giá định tính với trường hợp ngoại lệ. Không dùng một tỷ lệ đơn để đánh giá cá nhân mà bỏ qua độ phức tạp, severity và chất lượng xử lý.

### 19.3. Các quyết định phải có lịch sử

- Original severity và lý do thay đổi severity.
- Original due date, extension approvals và residual risk khi gia hạn.
- Original exception expiry, renewal history và thời gian không có phê duyệt.
- Metric contract version và người duyệt thay đổi.
- Findings reopened và kết quả retest.
- Dashboard correction sau khi tìm thấy data gap.
- Những quyết định quản trị đã sử dụng báo cáo trước khi phát hiện sai.

Không xóa hoặc ghi đè lịch sử chỉ để tạo đường trend liên tục đẹp.

## 20. Xử lý khi đã phát hành một báo cáo sai lệch

Nếu phát hiện dashboard từng làm cho tình trạng rủi ro trông tốt hơn thực tế, việc sửa chỉ số là chưa đủ; phải xử lý **tác động tới những quyết định đã đưa ra**.

### 20.1. Quy trình khắc phục gợi ý

1. **Preserve evidence:** lưu bản báo cáo cũ, metric code/config, source snapshots, người nhận, thời gian và approvals.
2. **Establish scope:** xác định metric, kỳ, asset/control, người đọc và quyết định bị ảnh hưởng.
3. **Classify defect:** sai dữ liệu, mẫu số, timing, test method, logic aggregation, UI hay diễn giải.
4. **Recompute/reassess:** dùng population và evidence đáng tin, đánh dấu phần chưa thể tái tính.
5. **Assess security impact:** có critical gap, incident, nghĩa vụ thông báo hoặc rủi ro cần containment không?
6. **Correct transparently:** phát bản đính chính, nêu thay đổi, giới hạn và confidence; không xóa báo cáo cũ.
7. **Escalate decisions:** báo tới risk owner, change/release authority, audit/legal khi phạm vi và nghĩa vụ yêu cầu.
8. **Open corrective actions:** sửa collector, metric contract, permission, test suite hoặc quy trình phê duyệt.
9. **Independent retest:** kiểm thử negative scenarios, reconciliation và report rendering.
10. **Monitor recurrence:** thiết lập alert khi data quality giảm hoặc numerator/denominator biến động bất thường.

### 20.2. Cách nói điều chỉnh báo cáo

**Tránh:** “Dashboard tháng trước chỉ gặp lỗi hiển thị nhỏ” khi 20 cloud accounts bị bỏ sót và decision đã dựa trên coverage sai.

**Nên:** “Báo cáo kỳ X đã sử dụng 80/100 tài sản theo inventory mới đối chiếu. Tỷ lệ 95% là PASS trong 80 tài sản đã được test, không phải 95% tổng production. Đã xác nhận 4 FAIL và 20 chưa đánh giá; cần cập nhật quyết định rủi ro của những services liên quan. Bản đính chính cung cấp phương pháp tính, ảnh hưởng và kế hoạch đánh giá bổ sung.”

Không cần tự nhận có vi phạm pháp luật nếu chưa có đánh giá đủ căn cứ; nhưng cũng không được che nghĩa vụ có thể áp dụng. Với phát hiện nghiêm trọng, quy trình incident/privacy/compliance riêng có thể cần kích hoạt.

## 21. Mẫu hồ sơ báo cáo assurance có lineage và uncertainty

YAML sau là **mẫu học tập**, không phải schema chuẩn của GRC/SIEM. Các ID, kết quả và ngày đều giả định. Mục đích là **tách rõ coverage, technical results, governance và data quality**, tránh gộp vào một boolean `secure`.

~~~yaml
assurance_report:
  id: "ANTIPATTERN-REPORT-EXAMPLE-010"
  report_version: "2.0-corrected"
  module: "SECURITY_SECURITY_ASSURANCE"
  service: "customer-data-platform"
  chapter: "Anti-pattern assurance"
  metric_definition_version: "asset-control-coverage-v3"
  reporting_period_utc:
    from: "2026-11-01T00:00:00Z"
    to: "2026-11-28T06:00:00Z"
  generated_at_utc: "2026-11-28T06:00:00Z"
  reporting_window_status: "PRELIMINARY_AS_OF_CUTOFF"
  assurance_owner: "Cloud Security Assurance Lead"
  reviewer: "Independent Control Assurance Reviewer"
  report_status: "CORRECTED_WITH_GAPS_DISCLOSED"

population:
  authoritative_sources:
    - "cloud-organization-api"
    - "runtime-asset-discovery"
    - "service-owner-inventory"
  target_scope: "production customer-data assets"
  in_scope_count: 100
  assessed_with_valid_evidence_count: 80
  missing_evidence_count: 20
  duplicate_records_removed: 0
  reconciliation_status: "PARTIAL_GAP_IDENTIFIED"
  excluded_assets:
    count: 0
    rationale: "No approved out-of-scope exclusions"

control_evaluation:
  control_id: "BASELINE-EXAMPLE-01"
  requirement_version: "internal-standard-2026.4"
  evaluated_assets: 80
  pass_count: 76
  fail_count: 4
  inconclusive_count_within_evaluated: 0
  not_assessed_count: 20
  assessment_scope: "80 assets accessible to validated scanner"
  temporal_claim: "POINT_IN_TIME_TESTS_WITHIN_REPORTING_PERIOD"
  method: "effective-configuration-plus-test-on-selected-paths"
  evidence:
    raw_scan_snapshot: "restricted/assurance-010/scan-run-101"
    inventory_snapshot: "restricted/assurance-010/inventory-reconciled"
    scanner_version: "approved-scanner-version-example"
    permissions_review: "restricted/assurance-010/collector-access-review"
    query_version: "assurance-metric-query-v3"

metrics:
  assessment_coverage_percent: 80.0
  pass_rate_among_assessed_percent: 95.0
  verified_pass_coverage_percent: 76.0
  known_fail_coverage_percent: 4.0
  unknown_coverage_percent: 20.0
  critical_control_blockers:
    fail: 2
    inconclusive: 1
  overall_security_pass: "NOT_DETERMINED_FROM_AGGREGATES"

quality:
  source_access_complete: false
  population_reconciled: true
  evidence_provenance: "PASS_FOR_80_ASSESSED_ASSETS"
  unknown_assets_require_review: true
  missingness_visible_on_dashboard: true
  point_in_time_limitation_disclosed: true
  historical_report_comparable: false
  comparability_note: "Version 1 used scanner-only denominator"

governance:
  original_report:
    id: "ANTIPATTERN-REPORT-EXAMPLE-010-v1"
    claim: "95% of production assets compliant"
    corrected_reason: "Denominator omitted 20 unassessed assets"
  exceptions_tracked_separately: true
  risk_acceptance_tracked_separately: true
  legal_contract_compliance_not_inferred: true
  correction_requires_notification: true
  decision_history_preserved: true

actions:
  - id: "FIX-EVIDENCE-01"
    action: "Restore collector read access for missing accounts"
    owner: "Cloud Platform Owner"
    acceptance: "All 100 assets have validated coverage or documented scoped limitations"
    status: "IN_PROGRESS"
  - id: "FIX-METRIC-02"
    action: "Publish numerator, denominator and unknown category"
    owner: "Assurance Reporting Owner"
    acceptance: "Dashboard matches reconciled evidence for all test vectors"
    status: "READY_FOR_INDEPENDENT_RETEST"
  - id: "FIX-RISK-03"
    action: "Reassess high-risk assets without verified evidence"
    owner: "Business Risk Owner"
    acceptance: "Risk triage and appropriate mitigation decisions documented"
    status: "PENDING_EVIDENCE"

assurance_conclusion:
  original_control: "MIXED_PASS_FAIL_WITH_UNKNOWN"
  evidence_quality: "PARTIAL_COVERAGE"
  governance_reporting_integrity: "CORRECTION_REQUIRED"
  residual_risk: "REASSESSMENT_REQUIRED"
  decision: "DO_NOT_CLAIM_FULL_SCOPE_COMPLIANCE"
~~~

### 21.1. Vì sao không ghi overall PASS?

Vì tồn tại **4 FAIL có bằng chứng và 20 asset chưa đủ chứng cứ**. Metric chỉ xác nhận 76/100 có PASS trên phương pháp được khai báo, không chứng minh 24 asset còn lại an toàn hay không an toàn. Việc dashboard được đính chính không tự sửa control failures hoặc data gaps.

### 21.2. Vì sao vẫn cần version 1?

Để audit biết quyết định nào đã được thực hiện trên cơ sở claim “95% production compliant” và quá trình sửa đã diễn ra thế nào. Không xóa bản cũ: giữ source, timestamp, recipients và correction history phù hợp chính sách lưu hồ sơ.

### 21.3. Lưu ý thời gian của mẫu

Dữ liệu minh họa chỉ bao phủ từ ngày 01/11 đến **mốc chốt 28/11 lúc 06:00 UTC**, nên trường `reporting_window_status` ghi rõ **PRELIMINARY_AS_OF_CUTOFF**. Không được diễn giải các số này như kết quả cuối cùng của cả tháng 11. Khi áp dụng thực tế, phải ghi mốc chốt dữ liệu và trạng thái báo cáo, hoặc chờ kỳ kết thúc rồi mới phát hành bản final. Đây là một ranh giới thời gian quan trọng để tránh temporal claim sai.

## 22. Tình huống thực hành: Dashboard xanh trong lúc rủi ro cloud tăng

Một nền tảng SaaS xử lý dữ liệu khách hàng có ba mệnh đề quan trọng:

1. **IAM:** mỗi service identity production chỉ có quyền cần thiết.
2. **Logging:** mọi thao tác quản trị quan trọng được thu và chuyển tới SIEM.
3. **Remediation:** các finding mức high được khắc phục hoặc quản trị đúng thời hạn.

Vào cuộc họp đầu tháng, báo cáo điều hành cho biết:

- “Cloud security coverage **97%**.”
- “Critical alerts **100% responded within SLO**.”
- “**0 high findings overdue**.”
- “**100% exceptions approved**.”
- “No evidence of compromise.”

Người đánh giá độc lập xác minh:

- Inventory mới có **120 production assets**, nhưng scanner chỉ biết 100; 97 trong 100 đã scan là PASS, 3 FAIL.
- Scanner không có quyền đọc 20 asset mới; 6 asset trong nhóm đó đang xử lý dữ liệu nhạy cảm.
- Có 12 incident critical với T0 trong kỳ: 9 có T1 hợp lệ, 2 chưa phản ứng khi chốt kỳ và đã quá SLO, 1 không thể xác minh timestamp vì case migration. Trong 9 đã phản ứng, 8 đạt SLO và 1 trễ.
- Dashboard lấy “100% responded” từ số alert đã được **ACK**, không dùng T1 action đủ điều kiện theo playbook.
- Có 5 high findings, trong đó 2 retest PASS, 1 fix deployed chưa test, 2 quá hạn. Dashboard đếm cả 5 ticket đã chuyển sang `CLOSED` hoặc `RISK_REVIEW` và hiển thị “0 overdue”.
- Có 4 exception: 2 ACTIVE đúng quyền/hạn, 1 EXPIRED và 1 request còn PENDING. Bảng tổng hợp dùng filter `exception_id IS NOT NULL` rồi đánh dấu mọi record “approved”.
- SIEM có một khoảng mất sự kiện từ một account quan trọng do connector credential hết hạn; báo cáo threat detection không công bố khoảng mù.
- Ban điều hành dự kiến dựa vào dashboard để **mở rộng sản phẩm sang region mới**.

### 22.1. Câu hỏi

1. Tỷ lệ 97% đang đo cái gì? Có thể dùng để nói 97% tổng production đạt baseline không?
2. Tình trạng incident critical thực sự ra sao? Số ACK cho biết điều gì?
3. Những finding nào đủ điều kiện VERIFIED_CLOSED và cái nào vẫn chưa?
4. Bao nhiêu security exceptions đang ACTIVE hợp lệ theo dữ kiện?
5. “No evidence of compromise” có nghĩa “đã chứng minh không có compromise” không?
6. Tối thiểu phải sửa điều gì trong báo cáo trước khi quyết định mở region mới?

### 22.2. Phân tích từng bước

**Bước 1 — Sửa mẫu số cloud.** 97/100 = **97% trong tập đã scan**; population mới là 120. Assessment coverage = 100/120 ≈ **83,33%** và verified-pass coverage = 97/120 ≈ **80,83%**. Ba tài sản FAIL cần finding. Hai mươi asset thiếu chứng cứ, trong đó sáu xử lý dữ liệu nhạy cảm, cần ưu tiên inventory/collector/risk triage. Không tự gán 20 asset là FAIL; đồng thời không cho phép tuyên bố full-scope PASS.

**Bước 2 — Phân loại incident.** Có 12 incident critical đủ điều kiện theo T0. Trong 9 có T1, **8 đạt SLO và 1 trễ**; hai pending đã quá SLO; một record không thể chứng minh do lỗi timestamp. Không thể báo 100% đúng hạn. Một tỷ lệ xác minh được là **8/12 ≈ 66,67% incident có bằng chứng đáp ứng SLO**; record timestamp lỗi phải ghi unknown, không tự coi đáp ứng hay vi phạm nếu chưa có kết luận. Nêu rõ phương pháp để không lẫn với tỷ lệ SLA hợp đồng có thể có quy tắc khác.

**Bước 3 — Kiểm tra proxy ACK.** ACK chỉ xác nhận đã nhận/nhìn thấy alert; không phải action response hay containment nếu contract định nghĩa khác. Cần truy case timeline, response action, execution logs, outcome và T0/T1.

**Bước 4 — Phân loại remediation.** Chỉ 2 finding đã có retest PASS được xem xét VERIFIED_CLOSED nếu các điều kiện closure khác đạt; 1 deployed chưa retest vẫn **VERIFYING/INCONCLUSIVE**, 2 quá hạn vẫn **OVERDUE**. Dùng ticket status để tự tính `0 overdue` là sai.

**Bước 5 — Phân loại ngoại lệ.** Trong bốn hồ sơ, chỉ **2 ACTIVE đúng hạn và quyền** theo dữ kiện. Một EXPIRED không còn authorization hiện hành; một PENDING chưa được phê duyệt. Trạng thái control gốc vẫn phải được báo riêng, kể cả với hai exception hợp lệ.

**Bước 6 — Đánh giá logging và threat conclusion.** Khoảng mất collector khiến khả năng phát hiện không đủ để kết luận “không có compromise”. Cách nói đúng là **“không phát hiện được sự cố trong phần telemetry đã được quan sát; có khoảng mù cần điều tra”**. Nếu có dấu hiệu khai thác, cần IR theo playbook; không dùng KPI để kết luận an toàn tuyệt đối.

**Bước 7 — Xác định điều kiện mở region.** Trước quyết định, phải có inventory và control mapping cho region mới, xác minh IAM/logging/DR/privacy obligations, xử lý critical overdue và evidence gaps, đánh giá residual risk, release/change gates, scope và approver authority. Một thẻ dashboard tổng thể xanh không thay thế những tiêu chí này.

### 22.3. Bảng kết luận audit minh họa

| Claim trên dashboard | Thực tế có thể xác minh | Verdict |
|---|---|---|
| “97% toàn bộ cloud compliant.” | 97 PASS trong 100 scanned; 120 in-scope. | **MISLEADING**, cần sửa scope/coverage. |
| “100% critical response SLO.” | 8/12 có evidence đạt; 1 trễ, 2 pending quá hạn, 1 unknown. | **FAIL đối với những case không đạt; không có cơ sở cho 100%**. |
| “0 high findings overdue.” | 2 high overdue, 1 chưa retest. | **FAIL về tính chính xác của reporting**. |
| “100% exceptions approved.” | 2 active, 1 expired, 1 pending. | **FAIL về logic trạng thái**. |
| “No compromise.” | Có telemetry gap chưa được điều tra đủ. | **INCONCLUSIVE** cho claim toàn bộ thời kỳ. |
| “Có thể mở region mới dựa dashboard.” | Nhiều gate và dữ liệu rủi ro chưa đạt. | **Chưa đủ căn cứ**, cần re-review có thẩm quyền. |

Bài tập chỉ ra nhiều lỗi **không nằm trong phép tính cộng/trừ** mà nằm trong việc dịch “có hoạt động” thành “đã đáp ứng mục tiêu” và dịch “không thấy” thành “không tồn tại”.

## 23. Mẫu kế hoạch sửa anti-pattern reporting

| Hạng mục | Hành động | Owner minh họa | Acceptance criteria |
|---|---|---|---|
| **Data population** | Đối chiếu cloud assets từ organization/runtime và scanner. | Cloud Platform Owner | 120/120 asset được phân loại scope và trạng thái evidence, không bỏ 20 unseen. |
| **Collector access** | Sửa quyền đọc và kiểm tra pagination/regions. | Observability Engineering | Thu hợp lệ hoặc báo gap có evidence cho mọi account trong scope. |
| **Metric contract** | Tách tested pass, verified pass coverage, assessment coverage. | Assurance Reporting Owner | Numerator/denominator và UNKNOWN hiển thị đúng. |
| **Incident SLO** | Định nghĩa T0/T1 action, bổ sung pending/overdue/error. | SOC Operations Lead | Recompute 12 incidents, test missing-T1 không rơi khỏi dashboard. |
| **Remediation** | Liên kết finding với retest verdict, giữ overdue. | Vulnerability/Remediation Lead | Không đóng VERIFIED_CLOSED khi chỉ deploy hoặc risk review. |
| **Exception register** | Dùng state, approval authority, effective/expiry và control verdict. | Risk Governance Owner | PENDING/EXPIRED không còn hiển thị approved active. |
| **Telemetry completeness** | Khôi phục SIEM connector và synthetic source-to-destination test. | Security Monitoring | Evidence end-to-end và gap history, có cảnh báo khi collector ngừng. |
| **Executive display** | Đính chính headline và chú thích risk/confidence. | Security Assurance Lead | Report có full-scope coverage, blockers và decision needs. |
| **Independent QA** | Re-run logic với negative test vectors và sample audit. | Independent Assurance Reviewer | Known fail/unknown/overdue không biến thành PASS. |
| **Governance impact** | Xem lại quyết định mở region và các quyết định phụ thuộc báo cáo cũ. | Business Risk Owner | Quyết định được ban hành lại với evidence và quyền hợp lệ. |

Đây là kế hoạch minh họa, thời hạn phải xác định theo risk policy/obligations thực tế. Không được đưa toàn bộ action thành “Complete” chỉ vì dashboard đã sửa màu; còn cần **kiểm chứng control gaps và sửa pipeline nguồn**.

## 24. Checklist kiểm toán báo cáo Security Assurance

Trước khi tin hoặc phát hành một báo cáo, kiểm tra:

1. **Claim:** Báo cáo đang khẳng định điều gì, có liên hệ security objective/control rõ?
2. **Requirement:** ID, source, version, applicability và kỳ đánh giá được ghi?
3. **Population:** Có authoritative inventory, in-scope và exclusions với lý do?
4. **Denominator:** Mỗi tỷ lệ có numerator/denominator, observation unit và cohort?
5. **Unknown:** Missing/invalid/unassessed có hiển thị riêng, không âm thầm bỏ?
6. **Source trust:** Collector quyền đủ, API pagination, event source health và data completeness được kiểm?
7. **Freshness:** Bằng chứng còn đại diện cho runtime, artifact, identity và thời điểm?
8. **Scope:** Kết luận có vượt staging/region/tenant/sample đã test không?
9. **Effective controls:** PASS dựa trên behavior/config thực, không chỉ plan hoặc ticket?
10. **Gate outcomes:** PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE có semantics và bằng chứng?
11. **Exceptions:** Có tách technical FAIL, authorization, mitigation effectiveness và residual risk?
12. **External obligations:** Có kết luận riêng cho luật/hợp đồng và thẩm quyền nếu áp dụng?
13. **Process vs outcome:** PR merge, ACK, scan complete, approval có bị dùng làm bằng chứng outcome?
14. **Critical cases:** Có thể nhìn thấy critical FAIL/overdue dù aggregate đẹp?
15. **Trend:** Metric version, tool/rule/severity changes và population mix được công bố?
16. **Statistics:** Mean, median, percentiles, SLO và pending được dùng đúng phương pháp?
17. **Provenance:** Có raw evidence, source IDs, timestamps, tool/query versions và history?
18. **Reproducibility:** Người độc lập có thể tái tính KPI và kiểm mẫu bất thường?
19. **Integrity/privacy:** Bằng chứng được phân quyền, bảo toàn và không lộ secrets/PII?
20. **Visual integrity:** Biểu đồ, màu, nhãn, trục và chú thích không phóng đại claim?
21. **Owner & review:** Có control owner, reporting owner, reviewer và quyền ký xác nhận?
22. **Negative tests:** Pipeline có thử known FAIL, missing data, expired exception, overdue case?
23. **Remediation:** Số liệu lỗi có finding, action plan, owner, retest và escalation?
24. **Decision impact:** Báo cáo có nêu rõ điều chưa thể quyết định và các điều kiện cần?
25. **History:** Bản đính chính, metric definition changes và decisions cũ có được giữ?

### Câu hỏi tự đánh giá

Một báo cáo ghi “Patch compliance đạt 100%” vì 400/400 host mà scanner đã scan đều không còn finding patch quá hạn. Tuy nhiên, danh mục máy chủ production theo cloud API có 450 host; 30 host không cài agent, 20 host vừa tạo chưa nằm trong scanner. Mười host trong 50 host không được đánh giá đang chạy dịch vụ nhạy cảm.

**Có thể kết luận patch compliance 100% không? Nên báo số nào và hành động gì?**

**Gợi ý:** Không có căn cứ kết luận toàn bộ production đáp ứng. **100% là tỷ lệ PASS trong 400 host có assessment hợp lệ**; assessment coverage = 400/450 ≈ **88,89%** và verified-pass coverage = 400/450 ≈ **88,89%**, với **50 host (11,11%) chưa được đánh giá**. Không tự biến 50 host thành FAIL hoặc PASS. Cần đối chiếu danh sách host/agent, kiểm tra nguồn và quyền collector, bổ sung scan bằng phương pháp phù hợp cho host không thể cài agent, ưu tiên 10 host nhạy cảm theo risk assessment, xác minh effective patch state, cập nhật báo cáo/exception và giữ những findings hoặc khoảng trống evidence cho tới khi có kết quả.

**Báo cáo security assurance phản ánh thực tế khi điều được trình bày không mạnh hơn điều đã được chứng minh: population minh bạch, evidence có nguồn và thời điểm, control verdict tách khỏi trạng thái thủ tục, phần chưa biết được hiển thị và critical failures không bị che bởi số trung bình. Màu xanh có thể giúp đọc nhanh, nhưng giá trị thực của assurance nằm ở khả năng người khác kiểm chứng, phản biện và ra quyết định đúng trước những rủi ro còn tồn tại.**
