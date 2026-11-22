# Xác định bằng chứng cho nền tảng đám mây với thành phần do nhà cung cấp quản lý

## Mục tiêu bài học

Nền tảng đám mây thường sử dụng nhiều thành phần do nhà cung cấp vận hành, chẳng hạn cơ sở dữ liệu managed, hàng đợi thông điệp, object storage, identity provider, load balancer, dịch vụ sao lưu và nền tảng quan sát. Nhóm phát triển và kiểm thử không trực tiếp kiểm soát mã nguồn, hệ điều hành hoặc toàn bộ hoạt động bên trong các dịch vụ này. Vì vậy, việc xác minh chất lượng không thể chỉ dựa vào kiểm tra mã ứng dụng hoặc yêu cầu nhà cung cấp cam kết rằng dịch vụ an toàn và sẵn sàng.

Trong VALIDATION_TESTING_STRATEGY, cần xác định bằng chứng phù hợp để chứng minh các yêu cầu và rủi ro liên quan đến nền tảng cloud đã được kiểm soát. Bằng chứng có thể đến từ tài liệu và báo cáo đảm bảo của nhà cung cấp, cấu hình và nhật ký phía khách hàng, kết quả kiểm thử tích hợp, chỉ số vận hành, diễn tập phục hồi và hồ sơ sự cố. Cần hiểu bằng chứng nào chứng minh trách nhiệm của nhà cung cấp, bằng chứng nào chứng minh cấu hình và cách sử dụng của khách hàng, và phần nào vẫn chưa thể quan sát trực tiếp.

Sau bài học, người học có thể:

- Giải thích mô hình trách nhiệm chia sẻ giữa nhà cung cấp cloud và khách hàng.
- Xác định ranh giới trách nhiệm theo từng dịch vụ managed và cách cấu hình.
- Chuyển yêu cầu, rủi ro và kiểm soát thành câu hỏi cần bằng chứng.
- Chọn và đánh giá tài liệu assurance, chứng nhận, báo cáo kiểm toán và thông báo của nhà cung cấp.
- Thu thập bằng chứng phía khách hàng từ cấu hình, audit log, metric, trace và test run.
- Thiết kế kiểm thử hành vi cho database, storage, queue, identity và các dịch vụ managed khác.
- Đánh giá độ mới, phạm vi, tính xác thực và giới hạn của từng bằng chứng.
- Xây dựng ma trận truy vết bằng chứng, owner, tần suất và tiêu chí chấp nhận.
- Xử lý khoảng trống bằng chứng, thay đổi dịch vụ và sự cố từ nhà cung cấp.

## 1. Vì sao cần xác định bằng chứng cho thành phần managed?

Dịch vụ managed giúp nhóm giảm công việc vận hành phần cứng, hệ điều hành và phần mềm nền. Tuy nhiên, việc nhà cung cấp chịu trách nhiệm vận hành không có nghĩa mọi yêu cầu về bảo mật, khả dụng, dữ liệu và phục hồi đã tự động được đáp ứng.

Ví dụ:

- Nhà cung cấp vận hành database service, nhưng khách hàng vẫn có thể cấu hình sai quyền truy cập, network exposure, encryption key hoặc backup retention.
- Nhà cung cấp bảo trì object storage, nhưng khách hàng phải chọn policy, quyền bucket, replication và cách xử lý dữ liệu bị xóa.
- Nhà cung cấp cung cấp message queue có tính sẵn sàng cao, nhưng ứng dụng vẫn có thể xử lý message trùng, mất thứ tự hoặc retry sai.
- Nhà cung cấp vận hành identity service, nhưng khách hàng vẫn phải cấu hình federation, role mapping, session policy và quy trình thu hồi quyền.
- Nhà cung cấp công bố SLA, nhưng ứng dụng có thể không đáp ứng mục tiêu thời gian phục hồi hoặc không xử lý được lỗi vùng.

Nếu không xác định bằng chứng, nhóm có thể:

- Dùng chứng nhận chung của nhà cung cấp để kết luận quá rộng về một dịch vụ hoặc cấu hình cụ thể.
- Không chứng minh được tenant, region hoặc service tier đang sử dụng nằm trong phạm vi assurance.
- Bỏ sót trách nhiệm cấu hình thuộc khách hàng.
- Không có bằng chứng về cách ứng dụng xử lý timeout, retry, failover hoặc dữ liệu không nhất quán.
- Không phát hiện thay đổi dịch vụ, giới hạn quota hoặc thông báo ngừng hỗ trợ.
- Không thể chứng minh backup có thể restore hoặc bản sao dữ liệu có thể truy cập khi cần.
- Không có hồ sơ đáng tin cậy khi audit, incident review hoặc đánh giá release.

Mục tiêu không phải thu thập càng nhiều tài liệu càng tốt. Mục tiêu là có bằng chứng đủ phù hợp, đáng tin, còn hiệu lực và liên kết trực tiếp với yêu cầu hoặc rủi ro cần kiểm soát.

## 2. Mô hình trách nhiệm chia sẻ

Trong môi trường cloud, trách nhiệm thường được chia giữa nhà cung cấp và khách hàng. Ranh giới thay đổi theo loại dịch vụ, cấu hình và hợp đồng.

### 2.1. Các lớp trách nhiệm

Có thể xem xét các lớp sau:

- **Hạ tầng vật lý:** trung tâm dữ liệu, nguồn điện, làm mát, phần cứng và kiểm soát vật lý.
- **Nền tảng ảo hóa và mạng cloud:** hypervisor, control plane, mạng nền và cơ chế cô lập do nhà cung cấp vận hành.
- **Dịch vụ managed:** database engine, object storage, queue, identity, cache hoặc dịch vụ phân tích.
- **Cấu hình dịch vụ:** quyền, network policy, encryption, retention, replication, backup và quota.
- **Ứng dụng và dữ liệu khách hàng:** logic nghiệp vụ, phân quyền ở cấp ứng dụng, dữ liệu, xử lý lỗi và tích hợp.
- **Vận hành và quản trị:** giám sát, incident response, thay đổi, access review, phục hồi và quyết định phát hành.

Một số trách nhiệm được nhà cung cấp thực hiện hoàn toàn; một số được chia sẻ; một số thuộc khách hàng. Không nên dùng một ma trận chung cho mọi dịch vụ mà không kiểm tra tài liệu dịch vụ cụ thể.

### 2.2. IaaS, PaaS và dịch vụ managed

Mức trách nhiệm có thể thay đổi theo mô hình:

| Mô hình | Nhà cung cấp thường quản lý | Khách hàng thường quản lý |
|---|---|---|
| IaaS | Trung tâm dữ liệu, phần cứng, ảo hóa và một phần mạng nền. | Hệ điều hành guest, patching, runtime, ứng dụng, dữ liệu, identity và cấu hình network của workload. |
| PaaS | Hạ tầng, hệ điều hành hoặc runtime nền và nền tảng dịch vụ theo hợp đồng. | Mã ứng dụng, dữ liệu, quyền, cấu hình dịch vụ và cách tích hợp. |
| Managed service | Vận hành một dịch vụ chuyên biệt như database, queue hoặc storage. | Schema, dữ liệu, quyền, endpoint, encryption option, backup policy và hành vi ứng dụng. |
| SaaS | Ứng dụng và phần lớn nền tảng vận hành. | Người dùng, role, dữ liệu nhập/xuất, cấu hình tenant, tích hợp và cách sử dụng. |

Đây là mô tả khái quát. Ranh giới thật phải được xác nhận theo dịch vụ, region, phiên bản, tier và điều khoản hiện hành.

### 2.3. Ma trận trách nhiệm cho từng dịch vụ

Với mỗi dịch vụ managed, tài liệu nên ghi:

- Thành phần nào do nhà cung cấp vận hành.
- Cấu hình nào khách hàng có thể và phải quản lý.
- Kiểm soát nào được thực hiện chung.
- Bằng chứng nào nhà cung cấp cung cấp.
- Bằng chứng nào khách hàng phải tự tạo.
- Ai chịu trách nhiệm đánh giá và chấp nhận rủi ro.
- Những giới hạn không thể kiểm chứng trực tiếp.

Ví dụ database managed:

| Chủ đề | Nhà cung cấp | Khách hàng |
|---|---|---|
| Phần cứng và thay thế máy chủ | Vận hành phần cứng. | Theo dõi trạng thái dịch vụ và tác động ứng dụng. |
| Database engine patching | Cung cấp lịch và cơ chế patch theo dịch vụ. | Chọn cửa sổ bảo trì nếu được hỗ trợ, kiểm tra tương thích và xác minh sau patch. |
| Database access | Bảo vệ control plane và tính năng IAM của dịch vụ. | Cấu hình principal, role, network access và quyền schema/data. |
| Backup | Cung cấp tính năng backup theo tier. | Cấu hình retention, point-in-time recovery, kiểm tra restore và lưu bằng chứng. |
| Encryption | Cung cấp khả năng mã hóa. | Chọn key, policy, rotation và kiểm tra quyền sử dụng key. |
| Availability | Duy trì hạ tầng theo kiến trúc dịch vụ. | Chọn cấu hình HA, kiểm tra failover và thiết kế retry/recovery ở ứng dụng. |

## 3. Chuyển yêu cầu và rủi ro thành câu hỏi bằng chứng

Bắt đầu từ yêu cầu và rủi ro, không bắt đầu từ danh sách PDF nhà cung cấp gửi. Mỗi yêu cầu cần được chuyển thành câu hỏi có thể trả lời bằng một hoặc nhiều nguồn bằng chứng.

### 3.1. Các nhóm yêu cầu thường gặp

- Bảo mật vật lý và hạ tầng.
- Quản lý danh tính và quyền truy cập.
- Phân tách tenant và network.
- Mã hóa khi truyền và khi lưu.
- Quản lý khóa và secret.
- Bảo vệ dữ liệu, retention và xóa dữ liệu.
- Backup, restore và disaster recovery.
- Khả dụng, độ bền và khả năng mở rộng.
- Logging, monitoring và auditability.
- Quản lý lỗ hổng, patching và thay đổi.
- Incident response và thông báo sự cố.
- Data residency, privacy và nghĩa vụ tuân thủ.

### 3.2. Ví dụ chuyển yêu cầu thành bằng chứng

| Yêu cầu | Câu hỏi bằng chứng | Nguồn bằng chứng có thể dùng |
|---|---|---|
| Dữ liệu được mã hóa khi lưu | Dịch vụ và loại dữ liệu đang dùng có bật encryption không? Key do ai quản lý? | Provider documentation, cấu hình encryption, key policy, audit log. |
| Chỉ workload được phép truy cập database | Principal và network path nào có quyền kết nối? | IAM policy export, security group/firewall config, connection audit log, negative test. |
| Có thể phục hồi dữ liệu | Backup có được tạo và restore được trong thời gian yêu cầu không? | Backup configuration, restore exercise, recovery time record, evidence đối soát dữ liệu. |
| Dịch vụ có khả dụng | Mục tiêu availability nào áp dụng và khách hàng đã cấu hình HA ra sao? | SLA, service status history, HA configuration, application SLI/SLO. |
| Có thể điều tra sự cố | Có audit log, request ID và retention đủ không? | Logging configuration, sample audit events, retention setting, incident exercise. |
| Thay đổi nhà cung cấp được kiểm soát | Nhóm nhận được thông báo và đánh giá tác động như thế nào? | Change notification, release notes, review record, regression test report. |

### 3.3. Liên kết bằng chứng với risk register

Một bằng chứng nên tham chiếu:

- Requirement ID hoặc control ID.
- Risk ID và hậu quả được kiểm soát.
- Service và component cụ thể.
- Environment, region và tier áp dụng.
- Owner chịu trách nhiệm đánh giá.
- Ngày thu thập và thời hạn hiệu lực.
- Tiêu chí chấp nhận.
- Khoảng trống và rủi ro còn lại.

Một báo cáo assurance có thể liên quan đến nhiều kiểm soát, nhưng cần chỉ rõ phần nào hỗ trợ yêu cầu nào. Tránh gắn một tài liệu chung vào mọi rủi ro chỉ để đánh dấu đã có evidence.

## 4. Các loại bằng chứng từ nhà cung cấp

Nhà cung cấp cloud có thể cung cấp nhiều loại tài liệu và dữ liệu assurance. Mỗi loại chứng minh một khía cạnh và có giới hạn riêng.

### 4.1. Chứng nhận và báo cáo kiểm toán

Ví dụ các dạng tài liệu có thể gặp:

- Chứng nhận theo tiêu chuẩn quản lý an toàn thông tin.
- Báo cáo kiểm soát dịch vụ độc lập.
- Báo cáo đánh giá bảo mật hoặc privacy.
- Báo cáo tuân thủ theo ngành hoặc khu vực.
- Báo cáo kiểm toán độc lập theo kỳ.
- Tài liệu xác nhận phạm vi hệ thống và dịch vụ được đánh giá.

Khi xem xét, cần kiểm tra:

- Đơn vị pháp lý hoặc thực thể nhà cung cấp được đánh giá.
- Dịch vụ, region và loại hình triển khai nằm trong phạm vi.
- Thời gian báo cáo và ngày kết thúc kỳ đánh giá.
- Các ngoại lệ, phát hiện hoặc qualification.
- Kiểm soát phụ thuộc khách hàng cần tự thực hiện.
- Phạm vi nhà thầu phụ hoặc subprocessor.
- Báo cáo có phải bản đầy đủ hay bản tóm tắt.
- Cách xử lý phát hiện sau kỳ kiểm toán.

Một chứng nhận của công ty không tự chứng minh mọi dịch vụ, region hoặc cấu hình mà khách hàng đang dùng đều nằm trong phạm vi.

### 4.2. Tài liệu kiến trúc và bảo mật dịch vụ

Tài liệu này có thể mô tả:

- Kiến trúc logic và ranh giới dịch vụ.
- Mô hình cô lập tenant.
- Mã hóa, quản lý khóa và bảo vệ network.
- Cơ chế HA, replication và failover.
- Backup, restore và retention.
- Identity integration và access control.
- Logging, monitoring và audit.
- Giới hạn, quota và vùng khả dụng.

Tài liệu kiến trúc giúp hiểu cách dịch vụ được thiết kế, nhưng không nhất thiết chứng minh cấu hình tenant của khách hàng đang đúng. Cần kết hợp với bằng chứng cấu hình thực tế.

### 4.3. SLA và service commitment

SLA thường mô tả cam kết dịch vụ theo điều kiện, phạm vi và phương pháp tính nhất định. Cần kiểm tra:

- Dịch vụ và tier nào được bao phủ.
- Định nghĩa downtime và availability.
- Cửa sổ đo và cách tính.
- Các trường hợp loại trừ.
- Điều kiện khách hàng phải đáp ứng.
- Cách gửi yêu cầu service credit.
- SLA có phải cam kết phục hồi, độ bền hay chỉ availability không.

SLA không đồng nghĩa với SLO nội bộ và cũng không bảo đảm ứng dụng end-to-end đạt mục tiêu. Một dịch vụ có thể đáp ứng SLA trong khi ứng dụng khách hàng vẫn lỗi do cấu hình, dependency hoặc logic retry.

### 4.4. Tài liệu vận hành và thay đổi

Các bằng chứng khác có thể gồm:

- Service health dashboard và lịch sử sự cố.
- Release notes và thông báo deprecation.
- Lịch bảo trì và thông báo patch.
- Hướng dẫn migration.
- Hướng dẫn giới hạn và quota.
- Báo cáo sự cố hoặc post-incident summary.
- Thông tin thay đổi API, SDK hoặc behavior.
- Tài liệu hỗ trợ và ticket nhà cung cấp.

Những tài liệu này cần được đánh giá theo thời điểm và dịch vụ thực tế đang sử dụng. Một trang tài liệu có thể thay đổi mà không giữ nội dung cũ; nên lưu phiên bản hoặc bản chụp có ngày thu thập nếu cần truy vết.

## 5. Đánh giá phạm vi và độ tin cậy của evidence nhà cung cấp

Không phải tài liệu nào có logo hoặc tên tiêu chuẩn cũng phù hợp với yêu cầu cần chứng minh. Cần đánh giá bằng chứng theo nhiều chiều.

### 5.1. Kiểm tra phạm vi

- Tên dịch vụ chính xác.
- Region hoặc location được bao gồm.
- Service tier, edition hoặc feature đang dùng.
- Mô hình deployment.
- Phạm vi tổ chức hoặc pháp nhân.
- Subprocessor có liên quan.
- Loại dữ liệu và use case.
- Khoảng thời gian được đánh giá.

Nếu dịch vụ được triển khai ở một region chưa nằm trong báo cáo, không thể tự động áp dụng kết luận của region khác.

### 5.2. Kiểm tra thời gian và độ mới

Ghi:

- Ngày phát hành tài liệu.
- Kỳ đánh giá hoặc kỳ báo cáo.
- Ngày hết hạn chứng nhận nếu có.
- Ngày nhà cung cấp cập nhật tài liệu.
- Ngày nhóm tải hoặc xác minh.
- Sự kiện thay đổi sau ngày tài liệu.

Một báo cáo có kỳ đánh giá đã kết thúc nhiều tháng trước vẫn có thể hữu ích, nhưng cần xác nhận không có thay đổi trọng yếu và có bằng chứng bổ sung cho khoảng thời gian chưa được bao phủ.

### 5.3. Kiểm tra loại bằng chứng

| Loại | Có thể hỗ trợ điều gì | Không tự chứng minh điều gì |
|---|---|---|
| Chứng nhận | Hệ thống quản lý hoặc phạm vi kiểm soát đã được đánh giá theo tiêu chuẩn. | Cấu hình tài khoản khách hàng đúng. |
| Báo cáo kiểm toán | Thiết kế/vận hành kiểm soát trong kỳ và phạm vi cụ thể. | Mọi kiểm soát khách hàng đã thực hiện. |
| SLA | Cam kết dịch vụ theo định nghĩa và điều kiện. | Ứng dụng end-to-end đáp ứng SLO. |
| Kiến trúc dịch vụ | Cách dịch vụ được thiết kế và giới hạn. | Cấu hình triển khai thực tế không sai. |
| Service status | Tình trạng dịch vụ được nhà cung cấp công bố. | Tất cả request của khách hàng đều thành công. |
| Release note | Thay đổi được công bố. | Không có tác động ngoài những gì được mô tả. |
| Support ticket | Nhà cung cấp đã nhận và xử lý một vấn đề cụ thể. | Nguyên nhân gốc đã được loại bỏ trong mọi region. |

### 5.4. Đọc ngoại lệ và complementary user entity controls

Một số báo cáo assurance nêu kiểm soát mà khách hàng phải thực hiện. Ví dụ, nhà cung cấp có thể cung cấp encryption capability nhưng khách hàng phải bật tính năng, quản lý key và giới hạn quyền. Các kiểm soát này thường được mô tả như trách nhiệm hoặc kiểm soát bổ sung của tổ chức sử dụng dịch vụ.

Không được bỏ qua phần ngoại lệ hoặc giả định. Nếu báo cáo nói kiểm soát của khách hàng là cần thiết, phải có bằng chứng nội bộ cho thấy kiểm soát đó đã được triển khai và vận hành.

### 5.5. Phân loại kết quả đánh giá

Có thể dùng:

- **Sufficient:** bằng chứng đúng phạm vi, còn hiệu lực và hỗ trợ yêu cầu.
- **Partially sufficient:** hỗ trợ một phần, còn thiếu phạm vi hoặc bằng chứng bổ sung.
- **Out of scope:** tài liệu không bao phủ dịch vụ hoặc region liên quan.
- **Stale:** quá cũ hoặc không phản ánh trạng thái hiện tại.
- **Inconclusive:** không đủ thông tin để đánh giá.
- **Not available:** nhà cung cấp không cung cấp loại bằng chứng cần thiết.

Mỗi trạng thái cần có lý do, owner và hành động tiếp theo. Không coi Not available là pass.

## 6. Bằng chứng phía khách hàng

Nhà cung cấp không thể chứng minh thay khách hàng rằng tài khoản, network, dữ liệu và ứng dụng đã được cấu hình đúng. Vì vậy, nhóm cần thu thập bằng chứng từ môi trường và quy trình của chính mình.

### 6.1. Bằng chứng cấu hình

Có thể gồm:

- Infrastructure-as-code và kết quả plan/apply.
- Export cấu hình dịch vụ.
- IAM policy và role binding.
- Network security rule, route và private endpoint.
- Encryption setting và key policy.
- Backup retention, replication và lifecycle rule.
- Audit logging configuration.
- Quota, autoscaling và service limit.
- Policy về public access và data sharing.

Nên lưu snapshot có timestamp, environment, account/project ID đã được kiểm soát và commit cấu hình. Cấu hình mong muốn trong code không tự chứng minh cấu hình thực tế đã được áp dụng; cần xác minh trạng thái deployed hoặc drift.

### 6.2. Bằng chứng audit và vận hành

- Audit event cho thay đổi quyền hoặc cấu hình.
- Deployment log và change record.
- Access review và approval.
- Backup job status.
- Restore exercise result.
- Failover event và recovery timing.
- Metric, log, trace và alert history.
- Incident record và postmortem.
- Bằng chứng xử lý thông báo nhà cung cấp.

Cần biết nguồn, thời gian đồng bộ, retention và quyền truy cập. Nếu logging không bật hoặc dữ liệu đã hết hạn, đó là khoảng trống bằng chứng cần ghi nhận.

### 6.3. Bằng chứng kiểm soát quy trình

- Review và approval cho thay đổi hạ tầng.
- Quy trình cấp và thu hồi quyền.
- Kiểm tra định kỳ cấu hình.
- Access recertification.
- Quy trình xử lý vulnerability.
- Runbook và diễn tập.
- Hồ sơ đánh giá rủi ro nhà cung cấp.
- Hợp đồng, phụ lục bảo mật và quy trình thông báo sự cố.

Một policy viết trên tài liệu chỉ chứng minh quy định đã được mô tả. Để chứng minh vận hành, cần có mẫu hồ sơ thực hiện, log hoặc kết quả kiểm tra.

## 7. Kiểm thử hành vi của dịch vụ managed

Tài liệu nhà cung cấp không thay thế kiểm thử cách ứng dụng sử dụng dịch vụ. Cần kiểm tra các hành vi quan sát được tại ranh giới dịch vụ.

### 7.1. Database managed

Các mục tiêu có thể gồm:

- Kết nối bằng danh tính và quyền tối thiểu.
- Truy vấn và transaction đúng trong điều kiện bình thường.
- Hành vi khi connection timeout hoặc pool cạn.
- Retry và xử lý lỗi transient.
- Backup và point-in-time restore.
- Migration và tương thích schema.
- HA/failover trong phạm vi được phép.
- Encryption và quyền truy cập key.
- Audit event cho truy cập hoặc thay đổi quan trọng.

Cần ghi loại instance/tier, phiên bản engine, region, cấu hình HA, backup retention và giới hạn connection. Không thực hiện thử nghiệm phá hủy trên dịch vụ production nếu không có kế hoạch và phê duyệt riêng.

### 7.2. Object storage

Kiểm tra:

- Bucket/container không public ngoài ý muốn.
- IAM và policy giới hạn đúng principal.
- Encryption và key access.
- Versioning, retention và lifecycle.
- Upload/download và xử lý object lớn.
- Multipart upload và thao tác bị gián đoạn.
- Replication và khả năng truy cập bản sao.
- Delete, recovery và retention lock nếu có.
- Audit log cho hành động nhạy cảm.

Cần phân biệt object đã được upload thành công với object có thể được phục hồi sau khi xóa hoặc lỗi vùng. Những mục tiêu đó cần bằng chứng riêng.

### 7.3. Message queue và event service

Kiểm tra:

- Publish/consume theo contract.
- Acknowledgement và redelivery.
- Duplicate delivery và idempotent processing.
- Ordering trong phạm vi được cam kết.
- Retry, dead-letter queue và poison message.
- Consumer lag và back-pressure.
- Quota, retention và message expiry.
- Khả năng xử lý khi broker tạm thời không sẵn sàng.

Không giả định mọi managed queue cung cấp exactly-once end-to-end. Cần đọc guarantee của dịch vụ và xác minh ứng dụng xử lý duplicate, ordering và retry đúng theo mô hình thực tế.

### 7.4. Identity và access service

Kiểm tra:

- Authentication và federation.
- Role mapping và quyền theo tenant.
- Token lifetime, audience, issuer và rotation.
- Thu hồi phiên hoặc quyền.
- MFA hoặc policy bắt buộc.
- Audit log cho thay đổi role và đăng nhập.
- Hành vi khi identity provider không sẵn sàng.
- Quyền của workload identity và service account.

Bằng chứng từ nhà cung cấp về tính năng IAM không chứng minh policy khách hàng đã áp dụng đúng. Cần kết hợp export policy, negative test và audit event.

### 7.5. Managed cache, search và analytics

Tùy dịch vụ, kiểm tra:

- Cache eviction, TTL và invalidation.
- Hành vi khi cache miss hoặc cache unavailable.
- Search index consistency và reindex.
- Data ingestion delay và duplicate.
- Query limit, quota và throttling.
- Backup/snapshot và restore.
- Access control và encryption.
- Khả năng phục hồi khi node hoặc partition thay đổi.

Mục tiêu cần dựa trên guarantee được nhà cung cấp công bố và rủi ro ứng dụng. Không áp đặt một giả định chung cho mọi sản phẩm managed.

## 8. Bằng chứng về bảo mật và quyền riêng tư

Dịch vụ managed có thể cung cấp nhiều kiểm soát bảo mật, nhưng nhóm cần xác minh cách chúng được cấu hình và dùng trong kiến trúc cụ thể.

### 8.1. Identity và quyền truy cập

Bằng chứng có thể gồm:

- Role/policy export.
- Danh sách principal và service identity.
- Access review và approval.
- Audit log về cấp, sửa và thu hồi quyền.
- Negative test chứng minh truy cập trái phép bị từ chối.
- Bằng chứng sử dụng quyền tối thiểu.
- Kiểm tra tài khoản đặc quyền và break-glass.

Cần xem xét cả quyền control plane lẫn data plane. Một người không có quyền thay đổi cấu hình vẫn có thể có quyền đọc dữ liệu, hoặc ngược lại.

### 8.2. Encryption và key management

Kiểm tra:

- Encryption at rest và in transit.
- Loại key và owner.
- Key policy, grant và rotation.
- Quy trình revoke hoặc disable key.
- Hành vi khi key không khả dụng.
- Audit log về sử dụng key.
- Phạm vi dịch vụ và loại dữ liệu được mã hóa.

Không chỉ dựa vào tuyên bố “dịch vụ hỗ trợ encryption”. Cần bằng chứng tính năng đang bật, key phù hợp và ứng dụng không tạo đường truy cập ngoài kiểm soát.

### 8.3. Data residency, retention và deletion

Cần xác minh:

- Region lưu dữ liệu chính và bản sao.
- Dữ liệu backup hoặc log có thể được lưu ở đâu.
- Subprocessor liên quan.
- Retention period và lifecycle policy.
- Quy trình xóa dữ liệu và thời gian hoàn tất.
- Cách xử lý dữ liệu trong snapshot, backup và replica.
- Nghĩa vụ thông báo khi vị trí lưu trữ thay đổi.

Một cấu hình region cho workload không tự chứng minh mọi bản sao, log và backup đều nằm cùng region. Cần xem tài liệu dịch vụ và điều khoản cụ thể.

### 8.4. Vulnerability và patching

Nhà cung cấp có thể quản lý patch của nền tảng, nhưng khách hàng vẫn phải quản lý runtime, thư viện, cấu hình và phần ứng dụng thuộc phạm vi của mình. Cần ghi:

- Phần nào được provider patch.
- Cách nhận thông báo bảo trì hoặc vulnerability.
- Mốc thời gian và SLA xử lý nếu có.
- Khách hàng có quyền chọn maintenance window không.
- Cách kiểm tra phiên bản sau patch.
- Test tương thích và rollback plan.
- Các thành phần vẫn thuộc trách nhiệm khách hàng.

Không suy ra rằng managed service không cần vulnerability review chỉ vì nhà cung cấp quản lý hệ điều hành.

## 9. Bằng chứng về khả dụng, độ bền và phục hồi

Khả dụng của một dịch vụ managed không đồng nghĩa ứng dụng end-to-end luôn sẵn sàng. Cần đánh giá cả cam kết provider và khả năng hệ thống khách hàng xử lý sự cố.

### 9.1. Availability

Bằng chứng có thể gồm:

- SLA và service commitment.
- Lịch sử service health.
- Metric availability phía khách hàng.
- Error rate, timeout và dependency latency.
- Cấu hình HA và failover.
- Kiểm tra retry, circuit breaker và graceful degradation.
- Kết quả smoke test sau failover.

Cần định nghĩa availability theo trải nghiệm người dùng hoặc giao dịch, không chỉ trạng thái control plane của dịch vụ.

### 9.2. Durability và integrity

Đối với dữ liệu, cần phân biệt:

- Dịch vụ cam kết độ bền lưu trữ.
- Ứng dụng ghi đúng dữ liệu.
- Dữ liệu không bị ghi trùng hoặc ghi sai.
- Replica nhất quán theo mức dịch vụ cung cấp.
- Backup có thể khôi phục.
- Người dùng có thể truy cập dữ liệu sau phục hồi.

Bằng chứng durability của provider không thay thế đối soát nghiệp vụ hoặc restore exercise của khách hàng.

### 9.3. Backup và restore

Một kế hoạch bằng chứng nên bao gồm:

- Backup policy và retention.
- Trạng thái job và tỷ lệ hoàn tất.
- Phạm vi database, bucket hoặc volume.
- Mã định danh snapshot và thời điểm tạo.
- Kết quả restore vào môi trường an toàn.
- Thời gian khôi phục thực tế.
- Đối soát số bản ghi, checksum hoặc bất biến nghiệp vụ.
- Quyền và người thực hiện.
- Lỗi hoặc giới hạn phát hiện được.

Chỉ có trạng thái backup success không chứng minh restore thành công. Cần kiểm tra khôi phục định kỳ theo RPO/RTO và mục tiêu rủi ro.

### 9.4. Failover và disaster recovery

Cần xác định:

- Mô hình multi-zone hoặc multi-region.
- Phạm vi thành phần được replicate.
- RPO/RTO mục tiêu.
- Cách kích hoạt failover.
- Phụ thuộc identity, DNS, network và key.
- Dữ liệu có thể bị mất hoặc trễ.
- Cách xác minh ứng dụng sau chuyển vùng.
- Cách failback và đồng bộ lại.
- Người có quyền quyết định và thông báo.

Một kiến trúc được quảng bá là multi-region không tự chứng minh failover hoạt động đúng. Cần có diễn tập và kết quả đo được.

## 10. Kiểm thử và thu thập bằng chứng an toàn

Các dịch vụ managed thường dùng chung hạ tầng với khách hàng khác. Kiểm thử cần tôn trọng giới hạn dịch vụ và không tạo tác động ngoài phạm vi được phép.

### 10.1. Phân loại hoạt động kiểm thử

- **Configuration verification:** kiểm tra cấu hình, policy và trạng thái dịch vụ.
- **Functional integration:** kiểm tra hành vi ứng dụng qua API của dịch vụ.
- **Negative/security testing:** xác minh quyền trái phép bị từ chối.
- **Resilience testing:** kiểm tra timeout, retry, failover và dependency loss.
- **Performance testing:** đo latency, throughput, quota và throttling.
- **Recovery testing:** restore backup, đối soát và xác minh RPO/RTO.

### 10.2. Kiểm soát trước khi thử nghiệm

Trước hoạt động có thể gây tải hoặc gián đoạn, cần:

- Xác nhận phạm vi và môi trường.
- Kiểm tra điều khoản và chính sách acceptable use.
- Xác định quota, rate limit và chi phí.
- Dùng dữ liệu tổng hợp hoặc dữ liệu được phê duyệt.
- Có cửa sổ thử nghiệm và owner trực.
- Chuẩn bị rollback và dừng khẩn cấp.
- Thông báo các nhóm phụ thuộc.
- Ghi lại baseline trước thử nghiệm.

Không chạy stress, chaos hoặc failover test trên dịch vụ production nếu chưa có phê duyệt và kế hoạch kiểm soát tác động.

### 10.3. Lưu kết quả có thể tái lập

Mỗi lần kiểm thử nên ghi:

- Test ID và mục tiêu.
- Service, region, tier và account/project scope.
- Build, commit và artifact.
- Environment và cấu hình.
- Thời điểm và workload.
- Data set hoặc seed.
- Kết quả, log, trace và metric.
- Bằng chứng provider nếu có.
- Owner, người review và giới hạn.
- Defect hoặc incident phát sinh.

## 11. Đánh giá thay đổi và thông báo của nhà cung cấp

Dịch vụ managed có thể thay đổi phiên bản, API, behavior, quota, region availability hoặc maintenance schedule mà khách hàng không trực tiếp triển khai. Nhóm cần quy trình theo dõi và đánh giá tác động.

### 11.1. Các loại thay đổi cần theo dõi

- Deprecation hoặc end-of-life.
- Thay đổi API, SDK hoặc protocol.
- Thay đổi mặc định về bảo mật.
- Patch, maintenance và engine upgrade.
- Thay đổi quota, rate limit hoặc pricing tier.
- Thay đổi SLA hoặc service commitment.
- Mở hoặc đóng region/zone.
- Thay đổi subprocessor hoặc data residency.
- Sự cố và advisory bảo mật.
- Thay đổi logging, metric hoặc audit event.

### 11.2. Quy trình xử lý thông báo

1. Nhận thông báo từ kênh chính thức.
2. Xác định dịch vụ, region, tier và workload bị ảnh hưởng.
3. Liên kết với requirement, risk và test liên quan.
4. Đánh giá thời điểm và mức độ tác động.
5. Chỉ định owner kỹ thuật và người quyết định.
6. Lập kế hoạch thử nghiệm, migration hoặc cấu hình.
7. Thu thập evidence trước và sau thay đổi.
8. Cập nhật tài liệu, runbook và risk record.
9. Theo dõi sau khi thay đổi có hiệu lực.

### 11.3. Không coi thông báo provider là xác minh hoàn tất

Thông báo cho biết nhà cung cấp dự kiến thay đổi hoặc đã thay đổi. Khách hàng vẫn cần xác minh ứng dụng, integration, dữ liệu và cấu hình của mình. Nếu thay đổi không ảnh hưởng workload, cần ghi căn cứ đánh giá thay vì bỏ qua thông báo.

## 12. Ma trận quản lý bằng chứng

Ma trận giúp liên kết yêu cầu với nguồn bằng chứng, owner, tần suất và tiêu chí đánh giá.

### 12.1. Mẫu ma trận

~~~text
Evidence ID:
Requirement / Control ID:
Risk ID:
Cloud service / component:
Provider or customer evidence:
Evidence description:
Source / system:
Scope (account, region, tier, environment):
Date collected / period covered:
Freshness / expiry:
Owner:
Reviewer / approver:
Acceptance criteria:
Result:
Known limitations / gaps:
Related test / build / incident:
Storage location / access classification:
Next review date:
~~~

### 12.2. Ví dụ ma trận

| Yêu cầu/rủi ro | Dịch vụ | Bằng chứng provider | Bằng chứng khách hàng | Owner |
|---|---|---|---|---|
| Database chỉ truy cập từ workload được phép | Managed database | Tài liệu IAM/network capability và assurance scope. | IAM export, network rule, audit event, negative integration test. | Platform Owner và Data Owner. |
| Dữ liệu được mã hóa | Object storage | Tài liệu encryption và key service. | Bucket configuration, key policy, audit log, test truy cập. | Security Owner. |
| Có thể phục hồi dữ liệu trong RTO | Database | Backup/restore capability, service commitment. | Restore exercise, thời gian thực tế, data reconciliation. | Database/Service Owner. |
| Message được xử lý an toàn khi redelivery | Managed queue | Delivery semantics, retention và quota documentation. | Duplicate delivery test, idempotency test, DLQ evidence. | Application Owner. |
| Có thể điều tra thay đổi quyền | Identity service | Audit capability và log retention options. | Audit configuration, sample event, access review record. | Identity Owner. |
| Dịch vụ được duy trì theo cam kết | Cloud platform | SLA và service health report. | Customer SLI, incident history và dependency dashboard. | SRE/Service Owner. |

Một hàng có thể cần nhiều bằng chứng. Kết quả chỉ nên được đánh dấu đạt khi toàn bộ điều kiện liên quan được đáp ứng hoặc ngoại lệ đã được người có thẩm quyền chấp nhận.

## 13. Đánh giá khoảng trống bằng chứng

Không phải mọi rủi ro đều có thể được chứng minh trực tiếp. Một số hoạt động nội bộ của nhà cung cấp chỉ có thể được đánh giá qua assurance report, hợp đồng hoặc bằng chứng gián tiếp.

### 13.1. Các dạng khoảng trống

- Nhà cung cấp không công bố chi tiết nội bộ.
- Báo cáo assurance không bao phủ region hoặc tier đang dùng.
- Tài liệu hết kỳ hoặc chưa có bản mới.
- Không có log phía khách hàng cho sự kiện cần điều tra.
- Backup có trạng thái thành công nhưng chưa từng restore.
- SLA có nhưng chưa đo SLI end-to-end.
- Không thể thử failover do giới hạn dịch vụ hoặc chi phí.
- Không rõ ai chịu trách nhiệm cho một control.
- Thông báo provider chưa được đánh giá tác động.
- Evidence được lưu nhưng không truy xuất được hoặc thiếu quyền.

### 13.2. Cách xử lý khoảng trống

Có thể:

- Yêu cầu nhà cung cấp cung cấp tài liệu hoặc xác nhận chính thức.
- Bổ sung bằng chứng từ cấu hình và audit log phía khách hàng.
- Thiết kế test hành vi ở ranh giới dịch vụ.
- Tăng cường giám sát và cảnh báo.
- Thực hiện restore hoặc failover exercise trong môi trường phù hợp.
- Chọn dịch vụ hoặc tier có assurance phù hợp hơn.
- Giảm phạm vi sử dụng hoặc áp dụng biện pháp kiểm soát bổ sung.
- Ghi nhận rủi ro còn lại và yêu cầu người có thẩm quyền chấp nhận.

Không nên biến “không thể kiểm tra” thành “đạt”. Cần ghi rõ mức tin cậy và quyết định đối với khoảng trống.

### 13.3. Phân biệt bằng chứng gián tiếp và trực tiếp

Ví dụ, tài liệu nhà cung cấp mô tả backup được mã hóa là bằng chứng về capability hoặc control của provider. Cấu hình backup của tenant là bằng chứng khách hàng đã bật tính năng. Restore test là bằng chứng trực tiếp hơn về khả năng phục hồi dữ liệu cụ thể trong điều kiện đã thử.

Các loại bằng chứng bổ trợ nhau, nhưng không thay thế nhau hoàn toàn.

## 14. Quản lý vòng đời và tính toàn vẹn của evidence

Bằng chứng có thể nhạy cảm, hết hạn hoặc mất liên kết theo thời gian. Cần quản lý như một tài sản có owner và vòng đời.

### 14.1. Thu thập và lưu trữ

Mỗi evidence cần:

- ID duy nhất.
- Nguồn chính thức hoặc hệ thống thu thập.
- Ngày và người thu thập.
- Phạm vi và kỳ được bao phủ.
- Phiên bản hoặc digest nếu có.
- Mô tả cách tạo và mọi biến đổi.
- Quyền truy cập và phân loại.
- Retention và ngày rà soát.
- Liên kết tới requirement, risk và service.

### 14.2. Bảo vệ thông tin nhạy cảm

Báo cáo provider, log cloud và cấu hình có thể chứa thông tin hạn chế. Cần:

- Lưu trong kho được phê duyệt.
- Giới hạn quyền theo nguyên tắc tối thiểu.
- Không đưa secret, token hoặc private key vào evidence.
- Che dữ liệu cá nhân khi không cần thiết.
- Theo dõi việc tải xuống hoặc chia sẻ nếu chính sách yêu cầu.
- Hết hạn quyền truy cập khi người dùng không còn nhu cầu.
- Xóa hoặc archive theo retention policy.

### 14.3. Lưu phiên bản và dấu vết thay đổi

Nếu tài liệu provider được cập nhật, không nên ghi đè bản cũ khi bản cũ còn cần cho audit hoặc quyết định lịch sử. Lưu version, ngày tải và kỳ áp dụng. Với cấu hình, giữ liên kết đến commit hoặc snapshot để biết trạng thái nào được đánh giá.

Không cần tạo thủ tục pháp chứng phức tạp cho mọi tài liệu. Mức kiểm soát cần tương xứng với tính nhạy cảm, rủi ro và nghĩa vụ tuân thủ.

## 15. Trách nhiệm và quản trị bằng chứng

Việc thu thập evidence cần owner rõ ràng. Nhà cung cấp có thể cung cấp tài liệu, nhưng khách hàng chịu trách nhiệm đánh giá sự phù hợp với kiến trúc và rủi ro của mình.

### 15.1. Vai trò thường gặp

- **Cloud service owner:** chịu trách nhiệm về lựa chọn, cấu hình và sử dụng dịch vụ.
- **Platform/SRE owner:** quản lý hạ tầng, network, observability và phục hồi.
- **Security owner:** đánh giá assurance, identity, encryption và security evidence.
- **Data owner:** quản lý phân loại, vị trí, retention và phục hồi dữ liệu.
- **Application owner:** xác minh behavior, integration và xử lý lỗi.
- **QA/Test owner:** thiết kế test, thu thập kết quả và liên kết evidence.
- **Vendor/procurement owner:** quản lý hợp đồng, SLA, thông báo và kênh hỗ trợ.
- **Risk/compliance owner:** đánh giá kiểm soát, khoảng trống và chấp nhận rủi ro.
- **Release owner:** dùng bằng chứng và risk status để ra quyết định phát hành.

### 15.2. RACI minh họa

| Hoạt động | Cloud/Platform Owner | Security | Data Owner | QA/Test | Vendor Owner | Release/Risk Owner |
|---|---|---|---|---|---|---|
| Xác định dịch vụ và phạm vi | A/R | C | C | C | C | I |
| Thu thập assurance report | C | C | I | I | A/R | I |
| Đánh giá phạm vi chứng nhận | C | A/R | C | I | R | I |
| Xác minh cấu hình cloud | A/R | C | C | C | I | I |
| Kiểm thử hành vi integration | C | C | C | A/R | I | I |
| Kiểm tra backup/restore | R | C | A/R | C | I | I |
| Đánh giá khoảng trống và risk | C | R | R | C | C | A |
| Chấp nhận ngoại lệ | C | C | C | C | I | A/R |
| Rà soát evidence định kỳ | R | R | R | R | R | A hoặc người được chỉ định |

Điều chỉnh ma trận theo tổ chức và xác định một người chịu trách nhiệm cuối cùng cho mỗi quyết định. Với hoạt động có nhiều owner chuyên môn, cần có một coordinator.

### 15.3. Tần suất rà soát

Có thể rà soát theo:

- Chu kỳ định kỳ, chẳng hạn hàng quý hoặc theo kỳ audit.
- Mỗi release lớn hoặc thay đổi kiến trúc.
- Khi nhà cung cấp cập nhật SLA, certification hoặc service scope.
- Khi chuyển region, tier hoặc loại dịch vụ.
- Sau incident, security advisory hoặc outage.
- Khi thay đổi data classification hoặc yêu cầu tuân thủ.
- Khi evidence hết hạn hoặc không còn truy xuất được.

Tần suất cần dựa trên mức rủi ro và tốc độ thay đổi. Không nên giả định một chứng nhận chỉ cần thu thập một lần rồi có giá trị vô thời hạn.

## 16. Ví dụ tổng hợp: ứng dụng dùng database, object storage và queue managed

Một nền tảng SaaS chạy trên cloud dùng ba dịch vụ managed:

- Database lưu tài khoản và giao dịch.
- Object storage lưu tài liệu.
- Queue xử lý tác vụ bất đồng bộ.

Nhóm xác định các rủi ro trọng yếu: truy cập trái phép, mất dữ liệu, xử lý message trùng và gián đoạn dịch vụ.

### 16.1. Bằng chứng provider

- Assurance report bao phủ dịch vụ và region đang sử dụng.
- Tài liệu database về HA, backup và encryption.
- Tài liệu object storage về durability, versioning và lifecycle.
- Tài liệu queue về delivery semantics, retention và dead-letter.
- SLA và service health history.
- Thông báo maintenance, deprecation và security advisory.

Nhóm kiểm tra kỳ báo cáo, service scope, region, tier và các kiểm soát bổ sung thuộc khách hàng.

### 16.2. Bằng chứng phía khách hàng

- Infrastructure-as-code và snapshot cấu hình.
- IAM policy, network rules và key policy.
- Backup retention và kết quả restore exercise.
- Object access policy và test public access bị từ chối.
- Queue consumer test về duplicate, retry và dead-letter.
- Audit log và trace có correlation ID.
- Metric availability, latency, error rate và consumer lag.
- Incident record và kết quả diễn tập failover.

### 16.3. Xác minh và quyết định

Nhóm liên kết từng bằng chứng với requirement và risk. Nếu provider có backup capability nhưng restore test của khách hàng chưa chạy, trạng thái phục hồi chỉ được đánh giá một phần. Nếu queue cung cấp at-least-once delivery, ứng dụng cần chứng minh xử lý idempotent. Nếu SLA đạt nhưng metric end-to-end của ứng dụng vượt ngưỡng, release vẫn cần đánh giá theo SLO và rủi ro sản phẩm.

Khi có khoảng trống, owner lập kế hoạch bổ sung bằng chứng hoặc biện pháp giảm thiểu. Release owner chỉ quyết định tiếp tục khi các gate bắt buộc đạt hoặc ngoại lệ được phê duyệt đúng thẩm quyền.

## 17. Những sai lầm thường gặp

- **Dùng chứng nhận chung để kết luận mọi dịch vụ an toàn:** bỏ qua phạm vi, region, tier và kỳ đánh giá.
- **Cho rằng provider chịu trách nhiệm mọi thứ:** bỏ sót cấu hình, identity, dữ liệu và logic ứng dụng thuộc khách hàng.
- **Chỉ lưu SLA:** không đo availability và behavior end-to-end.
- **Tin trạng thái backup success:** chưa chứng minh restore và tính toàn vẹn dữ liệu.
- **Giả định queue exactly-once:** không kiểm tra duplicate, retry và idempotency.
- **Coi tài liệu kiến trúc là bằng chứng cấu hình:** capability không đồng nghĩa đã bật hoặc cấu hình đúng.
- **Bỏ qua customer controls trong báo cáo audit:** thiếu bằng chứng nội bộ.
- **Không kiểm tra service scope:** tài liệu không bao phủ đúng dịch vụ đang sử dụng.
- **Dùng tài liệu cũ:** bỏ qua thay đổi dịch vụ và kỳ đánh giá.
- **Chỉ kiểm tra control plane:** không xác minh hành vi dữ liệu và ứng dụng.
- **Thử nghiệm phá hủy không có kiểm soát:** gây ảnh hưởng dịch vụ dùng chung hoặc phát sinh chi phí.
- **Không lưu bằng chứng gắn với build và region:** không thể tái lập quyết định.
- **Coi khoảng trống là đạt:** che giấu rủi ro chưa được xác minh.
- **Không có owner evidence:** tài liệu hết hạn hoặc thay đổi mà không ai cập nhật.

## 18. Checklist xác định bằng chứng cho thành phần managed

- [ ] Đã lập danh mục dịch vụ managed, region, tier và mục đích sử dụng.
- [ ] Đã xác định ranh giới trách nhiệm provider/customer cho từng dịch vụ.
- [ ] Yêu cầu và risk được chuyển thành câu hỏi bằng chứng cụ thể.
- [ ] Assurance report và chứng nhận có đúng phạm vi, kỳ và pháp nhân.
- [ ] Các ngoại lệ và customer controls đã được đánh giá.
- [ ] SLA được phân biệt với SLO và availability end-to-end.
- [ ] Có bằng chứng cấu hình thực tế phía khách hàng.
- [ ] IAM, network, encryption, key và logging được xác minh.
- [ ] Dữ liệu, retention, deletion và residency được xem xét.
- [ ] Backup có restore evidence và đối soát kết quả.
- [ ] HA/failover/DR được kiểm tra theo phạm vi cho phép.
- [ ] Database, storage, queue, identity và dependency có test phù hợp.
- [ ] Retry, duplicate, ordering, timeout và quota được xem xét.
- [ ] Thông báo provider và thay đổi dịch vụ có owner đánh giá.
- [ ] Evidence có nguồn, ngày, scope, phiên bản, owner và nơi lưu.
- [ ] Dữ liệu nhạy cảm và secret được bảo vệ.
- [ ] Khoảng trống, giới hạn và rủi ro còn lại được ghi rõ.
- [ ] Có ma trận truy vết tới requirement, risk, test và release.
- [ ] Có tần suất review và điều kiện cập nhật.
- [ ] Release decision dựa trên bằng chứng và risk acceptance có thẩm quyền.

## Kết luận

Xác định bằng chứng cho nền tảng cloud với thành phần managed đòi hỏi hiểu rõ trách nhiệm chia sẻ và kết hợp bằng chứng từ cả nhà cung cấp lẫn khách hàng. Assurance report, chứng nhận, SLA và tài liệu kiến trúc giúp đánh giá năng lực và cam kết của provider trong phạm vi cụ thể; cấu hình, audit log, metric, test integration, restore exercise và hồ sơ vận hành chứng minh cách khách hàng triển khai và sử dụng dịch vụ. Mỗi bằng chứng cần được kiểm tra về phạm vi, thời gian, nguồn, độ tin cậy và giới hạn. Khi liên kết evidence với requirement, risk, service, region, build và owner, nhóm có thể xác định khoảng trống, kiểm soát thay đổi và đưa ra quyết định phát hành dựa trên bằng chứng phù hợp thay vì giả định rằng dịch vụ managed tự động đáp ứng mọi yêu cầu.
