# Ưu tiên, phân công và theo dõi khắc phục finding

Trong môi trường AWS có nhiều tài khoản, Region và dịch vụ, các cảnh báo bảo mật có thể đến từ AWS Security Hub CSPM, Amazon GuardDuty, Amazon Inspector, Amazon Macie, IAM Access Analyzer, AWS Config và các sản phẩm bảo mật của bên thứ ba. Một finding riêng lẻ có thể mô tả cấu hình sai, lỗ hổng phần mềm, hành vi đáng ngờ hoặc tài nguyên đang bị lộ ra Internet. Nếu chỉ xử lý theo thứ tự xuất hiện hoặc theo nhãn severity, nhóm vận hành dễ bỏ sót rủi ro có tác động lớn và tiêu tốn thời gian vào các cảnh báo trùng lặp.

AWS Security Hub tập hợp và chuẩn hóa finding để nhóm bảo mật có thể tìm kiếm, phân tích, ưu tiên và điều phối xử lý. Với Security Hub CSPM, finding dùng AWS Security Finding Format (ASFF) và có các trường như Severity, Criticality, Workflow và RecordState. AWS Security Hub hiện hành còn cung cấp finding theo Open Cybersecurity Schema Framework (OCSF), exposure findings và remediation plans để gom nhiều vấn đề có cùng nguyên nhân gốc về một hành động khắc phục.

Bài học này trình bày quy trình vận hành từ lúc nhận finding đến khi xác minh đã khắc phục. Quy trình kết hợp đánh giá rủi ro, xác định chủ sở hữu tài nguyên, tạo ticket, thực hiện remediation, kiểm tra lại bằng nguồn phát hiện và lưu bằng chứng. AWS Security Hub cung cấp dữ liệu và cơ chế tự động hóa; nhóm vận hành vẫn cần xác định trách nhiệm, thời hạn và quy trình phê duyệt phù hợp với hệ thống.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt finding, severity, resource criticality, confidence, workflow status và record state.
- Ưu tiên finding dựa trên khả năng khai thác, mức độ phơi nhiễm, tác động kinh doanh và phạm vi ảnh hưởng.
- Nhận diện finding trùng lặp hoặc có cùng nguyên nhân gốc để tránh tạo nhiều công việc không cần thiết.
- Xác định đội ngũ hoặc người chịu trách nhiệm dựa trên tài khoản, resource tag, ứng dụng và hệ thống quản lý tài sản.
- Sử dụng AWS Security Hub CSPM automation rules, EventBridge và ticketing integrations để điều phối công việc.
- Phân biệt workflow của ASFF trong Security Hub CSPM với finding OCSF và remediation plans của AWS Security Hub hiện hành.
- Theo dõi tiến độ, SLA, tuổi finding, kết quả xác minh và nguy cơ tái xuất hiện.
- Thiết kế cơ chế tự động remediation có kiểm soát, có audit và có phương án rollback.

## 1. Finding là gì và đến từ đâu?

Finding là bản ghi mô tả một vấn đề bảo mật, một sự kiện đáng chú ý hoặc kết quả của một lần kiểm tra security control. Finding thường chỉ ra tài nguyên bị ảnh hưởng, tài khoản, Region, thời điểm quan sát, mức độ nghiêm trọng và thông tin hỗ trợ điều tra.

Trong hệ sinh thái AWS, finding có thể đến từ:

| Nguồn | Ví dụ finding | Công việc thường phát sinh |
|---|---|---|
| Amazon GuardDuty | Credential bất thường, malware, truy cập đáng ngờ hoặc hành vi từ IP độc hại. | Điều tra sự cố, cô lập workload, thu thập bằng chứng và bảo vệ danh tính. |
| Amazon Inspector | CVE trong package, container image hoặc EC2 instance. | Xác định khả năng khai thác, cập nhật package hoặc phát hành image mới. |
| Amazon Macie | Dữ liệu nhạy cảm trong Amazon S3 và rủi ro liên quan. | Xác minh phân loại dữ liệu, quyền truy cập và yêu cầu bảo vệ dữ liệu. |
| IAM Access Analyzer | Resource policy hoặc trust policy cho phép truy cập ngoài dự kiến. | Rà soát principal, thu hẹp quyền và xác nhận nhu cầu chia sẻ. |
| AWS Config và Security Hub CSPM controls | Security group mở cổng, S3 bucket sai cấu hình, logging chưa bật hoặc encryption chưa đáp ứng chuẩn. | Sửa cấu hình và chờ lần kiểm tra compliance tiếp theo. |
| Sản phẩm bên thứ ba | Lỗ hổng, dấu hiệu xâm nhập hoặc policy violation. | Điều tra theo nguồn phát hiện và phối hợp với chủ sở hữu sản phẩm. |

Security Hub CSPM tiếp nhận finding từ các dịch vụ tích hợp và chuẩn hóa theo ASFF. Security Hub hiện hành nhận finding theo OCSF, trong đó có dữ liệu từ Security Hub CSPM, GuardDuty, Macie, Inspector và các nguồn được hỗ trợ. Hai định dạng này có tên trường và vòng đời khác nhau; khi viết automation hoặc tích hợp, phải dùng đúng schema của nguồn sự kiện.

Một finding không đồng nghĩa với một incident. Finding có thể là cấu hình sai chưa bị khai thác, lỗ hổng cần lên lịch vá, kết quả kiểm tra tuân thủ hoặc tín hiệu cho thấy sự cố đang diễn ra. Nhóm bảo mật phải phân loại trước khi chọn quy trình phản ứng.

## 2. Đọc finding trước khi quyết định ưu tiên

Đừng chỉ nhìn vào tiêu đề hoặc nhãn severity. Hãy đọc các thuộc tính giúp xác định vấn đề, tài nguyên và bằng chứng.

Với finding ASFF trong Security Hub CSPM, các trường thường cần xem gồm:

| Trường | Ý nghĩa vận hành |
|---|---|
| Id và ProductArn | Định danh finding và sản phẩm tạo finding; cần cả hai khi gọi BatchUpdateFindings. |
| AwsAccountId | Tài khoản AWS chứa tài nguyên hoặc đối tượng liên quan. |
| Region | Region mà finding được ghi nhận. |
| Title, Description, Types | Tóm tắt, chi tiết và phân loại vấn đề. |
| Severity.Label | Nhãn severity: CRITICAL, HIGH, MEDIUM, LOW hoặc INFORMATIONAL. |
| Severity.Normalized | Giá trị severity chuẩn hóa trên thang 0–100 khi có. |
| Confidence | Mức tin cậy của phát hiện, trên thang 0–100. |
| Criticality | Mức quan trọng của tài nguyên liên quan, trên thang 0–100. |
| Resources | Tài nguyên bị ảnh hưởng, loại tài nguyên, ARN, ID và chi tiết có sẵn. |
| Compliance.Status | Kết quả compliance của control, ví dụ FAILED, PASSED, WARNING hoặc NOT_AVAILABLE. |
| Workflow.Status | Trạng thái điều tra của finding trong quy trình của khách hàng. |
| RecordState | Trạng thái bản ghi ACTIVE hoặc ARCHIVED. |
| CreatedAt, UpdatedAt, FirstObservedAt, LastObservedAt | Mốc thời gian tạo, cập nhật và quan sát finding. |
| Remediation | Hướng dẫn hoặc liên kết remediation nếu nhà cung cấp cung cấp. |
| RelatedFindings | Finding liên quan được liên kết với finding hiện tại. |
| UserDefinedFields và Note | Thông tin bổ sung do khách hàng ghi nhận. |

Với finding OCSF trong AWS Security Hub hiện hành, hãy xem các trường tương ứng như finding_info, resources, severity_id, confidence_score, remediation và thông tin tài khoản/Region. Không sao chép máy móc đường dẫn ASFF sang OCSF; hãy dùng schema OCSF và bộ lọc được API V2 hỗ trợ.

### 2.1. Severity không phải toàn bộ rủi ro

Severity phản ánh mức độ nghiêm trọng của vấn đề theo đánh giá của nguồn phát hiện hoặc control. Nhưng cùng một lỗi có thể tạo ra tác động rất khác nhau tùy tài nguyên.

Ví dụ:

- Một security group mở cổng quản trị trên máy thử nghiệm tạm thời có tác động khác với security group mở SSH trên hệ thống thanh toán production.
- Một CVE có sẵn exploit và đang ảnh hưởng dịch vụ Internet-facing cần được xử lý nhanh hơn một CVE khó khai thác trên workload cô lập.
- Một bucket chứa dữ liệu công khai đã được phê duyệt khác với bucket chứa dữ liệu khách hàng nhưng bị cấp quyền đọc công khai ngoài ý muốn.

Security Hub CSPM phân biệt severity với Criticality. Severity không tự tính đến mức quan trọng của tài nguyên. Trường Criticality trong ASFF dùng thang 0–100 để mô tả mức quan trọng của tài nguyên liên quan đến finding.

Trong AWS Security Hub hiện hành, tài nguyên có thể được gán criticality Very High, High, Medium, Low hoặc Unknown. Security Hub có thể suy luận criticality từ tên tài nguyên và tags; automation rule dạng resource rule có thể ghi đè mức suy luận này. Criticality của tài nguyên là đầu vào khi Security Hub tính impact và severity của exposure finding.

Không tự nâng severity chỉ vì tài nguyên thuộc production. Hãy lưu mức quan trọng của tài nguyên vào trường criticality hoặc metadata tương ứng, sau đó dùng nó trong quy tắc ưu tiên. Cách này giữ được ý nghĩa của severity gốc và giúp nhóm phân biệt rủi ro kỹ thuật với tác động kinh doanh.

### 2.2. Confidence và verification state

Confidence mô tả mức tin cậy rằng finding phản ánh đúng hành vi hoặc vấn đề mà nó định phát hiện. Giá trị 100 thể hiện mức tin cậy cao nhất; giá trị thấp hơn cho biết cần xác minh thêm. Confidence không phải xác suất sự cố chắc chắn xảy ra.

VerificationState trong ASFF hỗ trợ ghi nhận finding đã được xác minh là true positive, false positive hoặc trạng thái chưa xác định theo mô hình dữ liệu của Security Hub CSPM. Trước khi suppression, hãy kiểm tra bằng chứng và xác định false positive có phải do cấu hình scanner, môi trường thử nghiệm hay ngoại lệ được phê duyệt.

Một finding có severity cao nhưng confidence thấp cần được điều tra nhanh để xác nhận. Không nên tự động bỏ qua chỉ vì confidence thấp; cũng không nên thực hiện hành động phá hủy chỉ dựa trên một tín hiệu chưa được xác minh.

## 3. Phân biệt Workflow.Status và RecordState

Đây là hai trường khác nhau trong Security Hub CSPM.

- Workflow.Status thể hiện tiến độ điều tra và xử lý của khách hàng.
- RecordState thể hiện finding còn đang hoạt động trong tập dữ liệu hay đã được nhà cung cấp archive.

| Trường | Giá trị | Ý nghĩa |
|---|---|---|
| Workflow.Status | NEW | Finding mới, chưa được nhóm xử lý đánh giá. |
| Workflow.Status | NOTIFIED | Đã thông báo cho chủ sở hữu tài nguyên và đang chờ họ xử lý. |
| Workflow.Status | SUPPRESSED | Đã xem xét và xác định không cần hành động theo quy trình hiện tại. |
| Workflow.Status | RESOLVED | Đã khắc phục và được xem là đã giải quyết. |
| RecordState | ACTIVE | Finding còn hoạt động trong Security Hub CSPM. |
| RecordState | ARCHIVED | Finding đã được archive và được ẩn khỏi một số danh sách mặc định. |

Không dùng RecordState để biểu diễn người đang xử lý hoặc tiến độ ticket. Khách hàng cập nhật workflow bằng console hoặc BatchUpdateFindings; RecordState chỉ được finding provider cập nhật qua BatchImportFindings, không thể sửa bằng BatchUpdateFindings.

Một số hành vi vòng đời cần biết:

- Finding mới thường có workflow NEW và record state ACTIVE.
- Nếu control finding có Compliance.Status chuyển từ FAILED sang PASSED, Security Hub CSPM tự động đặt workflow thành RESOLVED.
- Nếu finding đang NOTIFIED hoặc RESOLVED mà record state chuyển từ ARCHIVED sang ACTIVE, workflow có thể được đặt lại thành NEW.
- Nếu compliance chuyển từ PASSED sang FAILED, WARNING hoặc NOT_AVAILABLE, workflow của control finding có thể trở lại NEW.
- SUPPRESSED có hành vi riêng và không tự đổi sang NEW chỉ vì record state được chuyển từ ARCHIVED sang ACTIVE.

Workflow status áp dụng cho từng finding. Đặt finding thành RESOLVED hoặc SUPPRESSED không ngăn provider tạo finding mới cho cùng vấn đề ở lần phát hiện sau. Vì vậy, nếu lỗi cấu hình vẫn còn, nhóm cần sửa nguyên nhân gốc thay vì chỉ đổi trạng thái.

## 4. Xây dựng thứ tự ưu tiên theo rủi ro

Một quy trình ưu tiên tốt kết hợp severity, khả năng khai thác, exposure, tài nguyên và tác động kinh doanh. Có thể bắt đầu bằng bảng phân loại nội bộ sau:

| Mức ưu tiên vận hành | Dấu hiệu điển hình | Hướng xử lý |
|---|---|---|
| P0 – Khẩn cấp | Có dấu hiệu compromise đang diễn ra, dữ liệu bị truy cập trái phép, credential bị lộ đang được sử dụng hoặc tài nguyên trọng yếu bị khai thác. | Kích hoạt incident response ngay, cô lập/contain theo runbook và bảo toàn bằng chứng. |
| P1 – Rất cao | Finding Critical/High trên tài nguyên Internet-facing hoặc business-critical; exploit đã biết; quyền truy cập rộng; có thể gây rò rỉ dữ liệu hoặc leo thang đặc quyền. | Giao owner ngay, xử lý trong cửa sổ khẩn cấp theo SLA tổ chức. |
| P2 – Cao | Lỗ hổng có bản vá, cấu hình sai trên production hoặc đường tấn công cần điều kiện bổ sung. | Đưa vào sprint/maintenance gần nhất, theo dõi deadline. |
| P3 – Trung bình | Vấn đề có tác động hạn chế, khó khai thác hoặc ảnh hưởng tài nguyên không trọng yếu. | Lập kế hoạch remediation và kiểm tra theo chu kỳ. |
| P4 – Thấp/Thông tin | Kết quả informational, khuyến nghị hardening hoặc phát hiện đã được chấp nhận có kiểm soát. | Theo dõi, cải thiện khi có cơ hội hoặc lưu làm bằng chứng. |

Đây là mô hình vận hành mẫu, không phải nhãn priority do AWS Security Hub tự gán. Tổ chức phải điều chỉnh theo yêu cầu pháp lý, SLA, khả năng trực vận hành và mức độ quan trọng của hệ thống.

### 4.1. Các yếu tố cần cân nhắc

Khi đánh giá một finding, hãy lần lượt xem xét:

1. **Severity:** finding có nhãn Critical/High hay chỉ là informational?
2. **Exploitability:** có exploit công khai, CVE đang bị khai thác, hoặc đường tấn công dễ thực hiện không?
3. **Exposure:** tài nguyên có public endpoint, public IP, public policy hoặc đường truy cập từ mạng không tin cậy không?
4. **Asset criticality:** tài nguyên phục vụ hệ thống trọng yếu, chứa dữ liệu nhạy cảm hay hỗ trợ danh tính đặc quyền không?
5. **Blast radius:** nếu bị khai thác, kẻ tấn công có thể truy cập thêm tài khoản, workload hoặc dữ liệu nào?
6. **Confidence:** bằng chứng của finding có đủ tin cậy để hành động không?
7. **Compensating controls:** đã có WAF, network segmentation, MFA, encryption hoặc biện pháp giảm thiểu khác chưa?
8. **Remediation effort và reversibility:** có thể sửa ngay, cần deployment hay cần cửa sổ bảo trì?

Không nên cộng điểm cơ học rồi bỏ qua ngữ cảnh. Một finding có severity Medium nhưng cho phép truy cập secret của nhiều production account có thể cần ưu tiên cao hơn một finding High trên tài nguyên thử nghiệm không chứa dữ liệu.

### 4.2. Ví dụ ma trận quyết định

| Finding | Severity | Resource | Exposure/khai thác | Ưu tiên gợi ý |
|---|---|---|---|---|
| GuardDuty phát hiện access key của role production có hành vi bất thường | High/Critical tùy finding | Role có quyền rộng | Có dấu hiệu sử dụng trái phép | P0/P1, xử lý như incident nếu xác minh có compromise |
| Inspector phát hiện CVE có exploit trên container Internet-facing | Critical/High | Dịch vụ production | Exploit công khai, đường truy cập trực tiếp | P1 |
| S3 bucket chứa dữ liệu nhạy cảm bị public | Critical | Data store trọng yếu | Truy cập công khai | P0/P1 tùy bằng chứng truy cập |
| Security group mở cổng thử nghiệm trên EC2 isolated | Medium/High | Non-production | Không public, có segmentation | P2/P3 sau khi xác minh |
| Security Hub control báo thiếu tag trên tài nguyên sandbox | Low | Sandbox | Không có exposure trực tiếp | P4 hoặc xử lý theo hygiene backlog |

Các mức P0–P4 trong bảng là ví dụ để nhóm thiết kế SLA. Hãy dùng nhãn severity và bằng chứng gốc của finding khi trao đổi với chủ sở hữu, tránh thay đổi severity chỉ để ép ticket vào một hàng đợi.

## 5. Gom finding trùng lặp và tìm nguyên nhân gốc

Một nguyên nhân gốc có thể tạo ra nhiều finding:

- Một security group được nhiều EC2 instance hoặc load balancer sử dụng.
- Một policy quá rộng ảnh hưởng nhiều resource.
- Một image nền chứa cùng package dễ tổn thương được triển khai lên nhiều ECS/EKS workload.
- Một control Security Hub thất bại trên nhiều tài nguyên do cùng một module Terraform hoặc CloudFormation.
- Một lỗ hổng network path tạo ra nhiều exposure finding liên quan.

Nếu tạo một ticket cho từng finding mà không nhóm theo nguyên nhân gốc, nhóm remediation sẽ xử lý cùng một thay đổi nhiều lần. Ngược lại, gộp các finding không liên quan có thể khiến việc xác minh và phân công không rõ ràng.

Có thể dùng các thuộc tính sau để xác định nhóm:

- Tài khoản, Region, resource ARN/ID và loại tài nguyên.
- Product ARN, Generator ID, control ID hoặc CVE.
- Rule ID, finding type, package name và version.
- Network path, security group, IAM role hoặc policy liên quan.
- RelatedFindings và mối quan hệ tài nguyên.
- Ứng dụng hoặc workload tag được gắn vào tài nguyên.

Không gộp chỉ vì hai finding có cùng Title. Hãy so sánh resource, evidence, control ID và nguyên nhân kỹ thuật. Mỗi finding vẫn cần được truy vết tới ticket hoặc remediation plan phù hợp.

### 5.1. Consolidated control findings

Security Hub CSPM hỗ trợ consolidated control findings để giảm số lượng finding trùng khi cùng một control xuất hiện trong nhiều security standards. Với tài khoản được bật tính năng này, Security Hub tạo một finding chuẩn hóa theo security control thay vì một finding riêng cho từng standard.

AWS khuyến nghị dùng consolidated control findings để giảm noise. Khi bật hoặc tắt tính năng, Security Hub có thể tạo finding mới và archive finding cũ; quá trình chuyển đổi có thể mất tới 24 giờ. Nếu có automation hoặc ticketing dựa trên ARN/GeneratorId cũ, hãy kiểm thử trước khi thay đổi.

### 5.2. Remediation plans trong AWS Security Hub hiện hành

AWS Security Hub hiện hành có thể tạo remediation plan từ exposure findings. Một plan nhóm các exposure có cùng nguyên nhân gốc, hướng tới một resource cụ thể. Sửa resource đó có thể giải quyết hoặc giảm severity của nhiều exposure cùng lúc.

Một remediation plan có các thông tin:

| Thuộc tính | Ý nghĩa |
|---|---|
| Priority | Mức cần xử lý: Critical, High, Medium hoặc Low. |
| Status | New, Updated hoặc Resolved. |
| Impact | Số exposure được giải quyết hoàn toàn, giảm severity hoặc được tác động mà severity không đổi. |
| Rollout | Thay đổi có hiệu lực ngay hay cần deployment. |
| Action | Thay đổi Security Hub khuyến nghị. |
| Trait | Đặc tính phơi nhiễm mà plan xử lý. |
| Target resource | Resource và loại resource cần sửa. |
| Account/Region | Tài khoản và Region sở hữu resource. |

Security Hub tự đặt trạng thái remediation plan; người dùng không đổi trực tiếp trạng thái này. New nghĩa là plan vừa được tạo; Updated nghĩa là plan đã thay đổi; Resolved nghĩa là Security Hub không còn tạo plan từ các exposure hiện tại. Plan đã resolved có thể tồn tại khoảng 14 ngày trước khi bị xóa khỏi danh sách.

Cần phân biệt trạng thái plan với trạng thái finding. Một plan Resolved không phải lúc nào cũng có nghĩa mọi exposure finding đã Resolved; ví dụ finding có thể chỉ giảm severity xuống Informational hoặc không còn trait mà plan xử lý. Hãy mở tab Affected exposures và kiểm tra từng finding.

Security Hub cung cấp hướng dẫn theo các pha như prerequisite, snapshot, fix, verify và done, đôi khi có lệnh CLI, Terraform, CDK hoặc CloudFormation. Security Hub mô tả bước khắc phục; người vận hành vẫn thực hiện thay đổi và kiểm tra kết quả.

## 6. Xác định owner và phân công remediation

Một finding chỉ có thể được xử lý đúng hạn khi có một nhóm hoặc người chịu trách nhiệm rõ ràng. Owner thường là đội quản lý tài nguyên, ứng dụng hoặc nền tảng tạo ra rủi ro.

Nguồn xác định owner có thể gồm:

- AWS account owner và OU trong AWS Organizations.
- Resource tags như Application, Owner, Team, Environment, CostCenter.
- AWS Service Catalog AppRegistry hoặc danh mục ứng dụng nội bộ.
- CMDB, hệ thống quản lý service ownership hoặc repository IaC.
- Account vending metadata và quy ước đặt tên tài nguyên.

Ví dụ routing:

| Điều kiện | Đội nhận việc |
|---|---|
| Application=checkout | Checkout team |
| Environment=production và ResourceType=AWS::RDS::DBInstance | Database platform/on-call DBA |
| Finding liên quan IAM role dùng bởi pipeline | Platform security hoặc CI/CD owner |
| EC2/ECS image có CVE | Container/platform team hoặc owner của service |
| S3 bucket có dữ liệu nhạy cảm | Data owner phối hợp Security/Privacy |
| GuardDuty finding cho credential compromise | SOC/Incident Response trước, sau đó chuyển owner workload |

### 6.1. Phân công trong ticketing system

Security Hub CSPM có workflow status để theo dõi điều tra, nhưng Workflow.Status không phải trường assignee. Đội vận hành nên dùng Jira, ServiceNow hoặc hệ thống quản lý công việc làm nguồn dữ liệu cho:

- Assignee hoặc team owner.
- Ticket ID và liên kết tới finding.
- SLA deadline, due date và mức ưu tiên.
- Kế hoạch remediation, deployment và rollback.
- Bằng chứng xác minh, người phê duyệt và thời điểm đóng ticket.

Nếu cần hiển thị thông tin routing trong ASFF, có thể dùng UserDefinedFields và Note để ghi metadata như team, ticket ID hoặc lý do phân công. Không đưa secret, dữ liệu cá nhân hoặc thông tin nhạy cảm không cần thiết vào note.

Một ticket nên chứa tối thiểu:

1. Finding ID, ProductArn và link tới Security Hub.
2. Tài khoản, Region, resource ARN/ID và application.
3. Severity, criticality, priority vận hành và evidence.
4. Hành động cần thực hiện và hướng dẫn remediation.
5. Owner, assignee, người phối hợp và deadline.
6. Điều kiện hoàn tất và bằng chứng cần đính kèm.
7. Phương án rollback hoặc escalation nếu thay đổi ảnh hưởng production.

### 6.2. Không giao ticket chỉ dựa vào tên resource

Tên tài nguyên có thể cũ hoặc không tuân theo quy ước. Nếu tag owner bị thiếu hoặc sai, hãy chuyển finding vào hàng đợi ownership triage và yêu cầu nhóm quản lý account/CMDB xác nhận. Không tự đoán owner từ chuỗi tên và không để finding Critical/High nằm chờ vô thời hạn vì metadata thiếu.

Nên có một hàng đợi riêng cho:

- Finding chưa xác định được owner.
- Resource tag thiếu hoặc không hợp lệ.
- Account không còn owner.
- Resource do nhiều nhóm cùng quản lý.
- Finding cần Security/Legal/Privacy hoặc incident commander quyết định.

## 7. Cập nhật finding trong Security Hub CSPM

Khách hàng có thể cập nhật một số trường thuộc quá trình điều tra bằng BatchUpdateFindings. API này không tạo finding mới; một request có thể cập nhật tối đa 100 finding hiện có. Cần truyền cả Id và ProductArn của từng finding.

Các trường khách hàng có thể cập nhật gồm Confidence, Criticality, Note, RelatedFindings, Severity, Types, UserDefinedFields, VerificationState và Workflow.

Không dùng BatchUpdateFindings để sửa RecordState hoặc các trường thuộc quyền sở hữu của finding provider. Thao tác này cũng không cập nhật giá trị UpdatedAt của finding. Nếu cần theo dõi thời điểm ticket được nhận hoặc remediation hoàn thành, hãy ghi thời gian trong ticket system hoặc metadata vận hành riêng.

Ví dụ cập nhật workflow và ghi note sau khi đã giao cho owner:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers '[{"Id":"<FINDING_ID>","ProductArn":"<PRODUCT_ARN>"}]' \
  --workflow '{"Status":"NOTIFIED"}' \
  --note '{"Text":"Assigned to Platform Team. Ticket SEC-1234. Target remediation: 2026-12-05.","UpdatedBy":"security-operations"}' \
  --region ap-southeast-1
~~~

Ví dụ đặt trạng thái RESOLVED sau khi đã xác minh remediation:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers '[{"Id":"<FINDING_ID>","ProductArn":"<PRODUCT_ARN>"}]' \
  --workflow '{"Status":"RESOLVED"}' \
  --note '{"Text":"Remediation verified. Security control passed and application owner confirmed.","UpdatedBy":"security-operations"}' \
  --region ap-southeast-1
~~~

Đây là ví dụ cú pháp. Hãy thay finding ID, Product ARN, Region, ticket ID và nội dung note bằng dữ liệu thật. Kiểm tra ProcessedFindings và UnprocessedFindings trong kết quả API; không giả định toàn bộ finding đã được cập nhật thành công.

### 7.1. Lưu ý về finding do control tạo

Với control findings, Security Hub CSPM chạy security checks theo lịch hoặc khi trạng thái tài nguyên thay đổi. Khi Compliance.Status chuyển từ FAILED sang PASSED, Security Hub cập nhật finding hiện có và tự động đặt workflow RESOLVED. Nếu trạng thái chuyển từ PASSED sang FAILED, finding có thể quay lại NEW.

Vì vậy, với control finding, hãy đợi kết quả kiểm tra mới và xác minh Compliance.Status. Đừng đóng ticket chỉ vì đã chạy lệnh sửa cấu hình; thay đổi cần được control đánh giá lại.

## 8. Automation rules để chuẩn hóa và giảm noise

Automation rules trong Security Hub CSPM cho phép tự động thay đổi các trường finding theo tiêu chí do nhóm định nghĩa. Một số trường hợp sử dụng:

- Nâng severity cho finding ảnh hưởng tài nguyên production trọng yếu.
- Đặt workflow thành SUPPRESSED cho finding đã được phê duyệt là không áp dụng trong môi trường thử nghiệm.
- Thêm note giải thích ngoại lệ hoặc mã ứng dụng.
- Gắn RelatedFindings để giúp nhóm nhận diện mối liên hệ.
- Điều chỉnh confidence hoặc criticality theo dữ liệu đã xác minh.
- Tự động chuẩn hóa finding từ một tích hợp bên thứ ba có cách ánh xạ severity khác.

Có thể tạo nhiều rule theo điều kiện tài khoản, Region, resource type, tag, product, control ID, severity và workflow. Thứ tự rule quan trọng: rule được áp dụng sau cùng có thể ghi đè giá trị do rule trước đặt.

Khi xây dựng automation cho control findings, nên lọc theo SecurityControlId hoặc SecurityControlArn thay vì Title/Description vì tiêu đề và mô tả có thể thay đổi trong các bản cập nhật tài liệu/control.

### 8.1. Automation rules và EventBridge khác nhau

- **Automation rules:** cập nhật hoặc suppress trường finding trong Security Hub CSPM.
- **EventBridge rules:** phản ứng với event, gọi Lambda, Step Functions, SSM Automation, SNS/SQS hoặc gửi finding tới công cụ ticketing/SIEM.

Trong Security Hub CSPM, automation rules được áp dụng trước EventBridge; EventBridge nhận finding sau khi automation đã cập nhật. Automation rules đánh giá finding mới hoặc được provider ingest/update qua BatchImportFindings. Thao tác BatchUpdateFindings của khách hàng không kích hoạt automation rule.

Điều này quan trọng khi thiết kế đồng bộ hai chiều. Nếu ticketing system cập nhật workflow qua BatchUpdateFindings, đừng chờ automation rule chạy lại trên chính lần cập nhật đó.

### 8.2. Automation trong AWS Security Hub hiện hành

AWS Security Hub hiện hành dùng OCSF. Automation rules có thể cập nhật các trường OCSF như Comment, SeverityId và StatusId. Ngoài finding rules, Security Hub còn có resource rules để gán criticality Very High, High, Medium, Low hoặc Unknown cho tài nguyên theo tiêu chí.

Finding rule có thể tạo ticket trực tiếp cho Jira Cloud hoặc ServiceNow ITSM khi finding khớp điều kiện. Resource rule chỉ cập nhật criticality tài nguyên; nó không đồng thời cập nhật finding hoặc tạo ticket. Hai loại rule dùng chung quota tối đa 100 rule cho mỗi account/Region.

Đừng dùng lẫn API V2/OCSF và API CSPM/ASFF. Chọn đúng loại rule, field path, event type và thao tác cập nhật theo sản phẩm đang dùng.

## 9. EventBridge: chuyển finding thành công việc

Security Hub CSPM tự gửi event tới Amazon EventBridge khi có finding mới hoặc finding được cập nhật. Event type phổ biến là Security Hub Findings - Imported, với source aws.securityhub. Event có thể phát sinh từ cả BatchImportFindings và BatchUpdateFindings.

Ví dụ event pattern lọc finding Critical/High còn active:

~~~json
{
  "source": ["aws.securityhub"],
  "detail-type": ["Security Hub Findings - Imported"],
  "detail": {
    "findings": {
      "RecordState": ["ACTIVE"],
      "Severity": {
        "Label": ["CRITICAL", "HIGH"]
      }
    }
  }
}
~~~

Pattern có thể chuyển event tới Lambda, Step Functions, SNS, SQS, Kinesis Data Streams hoặc API destination. Lambda/Step Functions có thể:

1. Đọc finding và lấy account/resource metadata.
2. Tra cứu owner từ resource tags, account inventory hoặc CMDB.
3. Tính priority vận hành theo chính sách.
4. Tạo ticket trong Jira/ServiceNow hoặc gửi yêu cầu tới hệ thống workflow.
5. Ghi ticket ID và owner vào metadata được phép.
6. Gửi thông báo tới nhóm phụ trách.
7. Lưu event/bằng chứng vào S3 hoặc hệ thống audit.

Với AWS Security Hub hiện hành, EventBridge dùng event type Findings Imported V2 cho sự kiện V2. Payload theo OCSF và cần viết event pattern theo các trường OCSF, không dùng đường dẫn ASFF trong ví dụ CSPM.

### 9.1. Thiết kế event processing đáng tin cậy

EventBridge và các dịch vụ đích hoạt động theo mô hình phân tán. Cùng một finding có thể được gửi lại khi provider cập nhật hoặc khi retry. Vì vậy, ticket automation cần idempotent:

- Dùng khóa định danh ổn định từ finding (ví dụ ProductArn + Id đối với ASFF, hoặc finding UID theo OCSF) để tra ticket đã tồn tại.
- Nếu ticket đã có, cập nhật nội dung thay vì tạo ticket mới.
- Phân biệt event tạo finding với event thay đổi finding.
- Xử lý retry, throttling, dead-letter queue và lỗi permission.
- Lưu trạng thái đồng bộ, thời gian lần thử cuối và lỗi gần nhất.
- Không tạo incident P0 chỉ vì cùng một event được gửi lại.

Không tự động block, terminate hoặc xóa resource chỉ dựa trên event pattern severity. Các hành động có tác động lớn cần điều kiện đủ mạnh, xác minh resource và phê duyệt theo runbook.

## 10. Tích hợp Jira Cloud và ServiceNow

AWS Security Hub hiện hành hỗ trợ ticketing integrations với Jira Cloud và ServiceNow ITSM. Nhóm có thể tạo ticket thủ công từ finding hoặc dùng automation rule để tạo ticket tự động khi finding khớp tiêu chí.

### 10.1. Jira Cloud

Tích hợp Jira Cloud cho phép gửi finding vào project để nhóm phát triển hoặc vận hành quản lý investigation và remediation. Ticket có thể được giao cho owner, đặt priority, due date và theo dõi trạng thái theo workflow Jira.

Các điểm cần chuẩn bị:

- Cài ứng dụng AWS Security Hub for Jira Cloud trong Jira.
- Dùng project dạng company-managed software project theo yêu cầu tích hợp.
- Liên kết project với ứng dụng AWS Security Hub for Jira Cloud.
- Thiết lập OAuth connector và quyền cần thiết.
- Xác định project ID, issue type, workflow và mapping severity/priority.
- Dùng tài khoản tích hợp chuyên dụng thay vì gắn OAuth vào tài khoản nhân viên có thể bị thay đổi quyền.

Jira có API rate limits. Khi volume finding lớn, ticket có thể tạo chậm; Security Hub retry các finding bị throttling trong tối đa 3 ngày. Sau thời gian retry, finding vẫn bị throttling có thể không tạo được ticket. Vì vậy, hãy lọc ticket theo priority, theo dõi API usage và xây dựng quy trình reconciliation để phát hiện finding chưa có ticket.

### 10.2. ServiceNow ITSM

Tích hợp ServiceNow ITSM có thể tạo incident hoặc problem từ finding. Trước khi cấu hình:

- Cài ứng dụng Security Hub findings integration for ITSM trong ServiceNow Store.
- Cấu hình OAuth client credentials cho inbound OAuth.
- Lưu client ID và client secret trong AWS Secrets Manager.
- Dùng customer managed KMS key và key policy phù hợp để Security Hub truy cập secret.
- Tạo connector V2 với URL instance và Secret ARN.
- Chọn hành vi khi nhận finding: không làm gì, tạo incident, tạo problem hoặc tạo cả hai.

ServiceNow có thể phù hợp với tổ chức đã dùng CMDB, assignment group, change request, incident/problem management và SLA. Cần thống nhất trạng thái ticket nào tương ứng với trạng thái workflow của finding.

### 10.3. Đồng bộ hai chiều

Nếu công cụ ticketing có khả năng cập nhật finding, hãy xác định rõ trường nào là nguồn sự thật:

| Thông tin | Nguồn nên quản lý chính |
|---|---|
| Finding evidence, provider severity và resource details | Security Hub / finding provider |
| Assignee, assignment group, due date, sprint | Jira hoặc ServiceNow |
| Workflow investigation trong CSPM | Security Hub Workflow.Status, đồng bộ theo chính sách |
| Remediation steps, change approval, rollback | Ticket/change management system |
| Compliance status sau remediation | Security Hub CSPM control hoặc nguồn kiểm tra tương ứng |
| Audit history của công việc | Ticket system và CloudTrail/EventBridge log |

Không để hai hệ thống ghi đè lẫn nhau mà không có quy tắc. Ví dụ, nếu ticket chuyển sang Done nhưng control vẫn FAILED, finding chưa được xem là đã khắc phục. Ngược lại, finding đã RESOLVED nhưng ticket chưa có bằng chứng hoặc chưa hoàn tất change record cũng cần được kiểm tra.

## 11. Remediation: chọn cách khắc phục và kiểm soát thay đổi

Remediation là thay đổi cấu hình, code, quyền hoặc quy trình để loại bỏ nguyên nhân gốc của finding. Hãy chọn phương án theo resource và bằng chứng, không áp dụng cùng một hành động cho mọi finding có cùng severity.

| Finding | Hướng remediation |
|---|---|
| S3 bucket public ngoài ý muốn | Rà soát bucket policy, ACL, Block Public Access, access points và nhu cầu chia sẻ; sau đó xác minh bằng kiểm tra truy cập. |
| Security group mở SSH/RDP ra Internet | Xác định nguồn quản trị hợp lệ, thu hẹp CIDR hoặc chuyển sang Systems Manager Session Manager. |
| CVE trong EC2/AMI | Cập nhật package, tạo AMI mới, triển khai thay thế và xác minh phiên bản sau deploy. |
| CVE trong container image | Cập nhật base image/dependency, build image mới, scan lại và triển khai digest đã được phê duyệt. |
| IAM policy quá rộng | Xác định action/resource cần thiết, thu hẹp policy, kiểm tra assume role và CloudTrail sau thay đổi. |
| GuardDuty phát hiện credential compromise | Cô lập/disable credential theo incident runbook, xác minh session, rotate secret và kiểm tra dấu hiệu truy cập tiếp theo. |
| Macie phát hiện dữ liệu nhạy cảm ngoài dự kiến | Xác nhận phân loại, giới hạn quyền truy cập, áp dụng encryption/retention và xử lý theo chính sách dữ liệu. |

### 11.1. Phân loại mức tự động hóa

| Loại remediation | Ví dụ | Kiểm soát nên có |
|---|---|---|
| Tự động an toàn | Gắn tag chuẩn, mở ticket, bổ sung metadata, thông báo owner. | Idempotency, quyền tối thiểu và audit. |
| Tự động có điều kiện | Thu hồi một rule ingress đã xác định là sai, sửa cấu hình log theo policy. | Điều kiện chặt, dry-run, kiểm thử, rollback và giới hạn phạm vi. |
| Cần phê duyệt | Thay IAM trust policy, sửa route table, đổi KMS key policy, triển khai bản vá production. | Owner approval, change record, maintenance window và kế hoạch rollback. |
| Phản ứng sự cố | Cô lập instance, revoke credential hoặc chặn network path khi có compromise. | Incident commander, runbook, bảo toàn bằng chứng và ghi log đầy đủ. |

AWS Systems Manager Automation, Lambda và Step Functions có thể điều phối remediation. Với hành động liên quan production hoặc danh tính, nên có bước approval và xác minh trước khi áp dụng. Không dùng một Lambda quyền AdministratorAccess để xử lý tất cả finding.

### 11.2. Runbook remediation

Một runbook tốt có cấu trúc:

1. Điều kiện kích hoạt và phạm vi tài nguyên.
2. Finding ID, resource ARN và dữ liệu cần xác minh.
3. Quyền IAM tối thiểu cần thiết.
4. Bước pre-check: trạng thái resource, backup/snapshot, phụ thuộc và maintenance window.
5. Bước thay đổi: CLI, API, Systems Manager Automation hoặc IaC.
6. Bước verify: gọi API đọc lại, chạy security check hoặc test traffic.
7. Bước rollback: khôi phục cấu hình trước nếu xác minh thất bại.
8. Bằng chứng: CloudTrail event, change ID, output kiểm tra và người phê duyệt.

Nếu remediation qua IaC, sửa source of truth rồi triển khai pipeline. Sửa trực tiếp tài nguyên trong console có thể bị lần deploy tiếp theo ghi đè hoặc tạo drift.

## 12. Xác minh đã khắc phục

Không đóng finding chỉ vì ticket đã được chuyển sang Done. Hãy kiểm tra lại bằng nguồn có thẩm quyền:

- Security Hub CSPM control finding: chờ security check tiếp theo và xác minh Compliance.Status là PASSED.
- Amazon Inspector: chạy hoặc chờ lần scan tiếp theo; kiểm tra package/version và finding lifecycle.
- GuardDuty: kiểm tra finding được provider cập nhật hoặc đóng theo logic phát hiện; xác minh không còn dấu hiệu compromise.
- Macie: kiểm tra lại dữ liệu và policy sau khi thay đổi; xác minh trạng thái theo lần phân tích tiếp theo.
- IAM Access Analyzer: chạy lại phân tích hoặc chờ analyzer cập nhật trạng thái.
- AWS Config: xác minh configuration item và compliance evaluation.
- Security Hub exposure finding: kiểm tra exposure đã giảm hoặc biến mất; nếu có remediation plan, mở tab Affected exposures để xem tác động.

Với control findings, Security Hub CSPM có thể tự đặt Workflow.Status=RESOLVED khi compliance chuyển sang PASSED. Với finding do dịch vụ khác tạo, provider có thể cập nhật finding theo vòng đời riêng. Không giả định mọi provider đều dùng cùng cách đóng finding.

### 12.1. Xác minh không tạo false closure

Một số tình huống cần điều tra thêm:

- Resource đã bị xóa nên finding được archive, nhưng ticket remediation chưa hoàn thành yêu cầu xóa.
- Control bị disable khiến finding được archive; điều này không chứng minh cấu hình resource đã an toàn.
- Scanner chưa chạy lại nên finding cũ vẫn hiển thị dù cấu hình đã sửa.
- Provider phát hiện lại vấn đề sau khi workflow đã RESOLVED.
- Ticket được đóng nhưng resource được tạo lại từ IaC với cấu hình cũ.

Hãy lưu kết quả verify, thời điểm kiểm tra, người xác minh và nguồn dữ liệu. Nếu finding tái xuất hiện, mở lại ticket hoặc tạo ticket liên kết với lần xử lý trước để tìm nguyên nhân tái diễn.

## 13. Theo dõi SLA, aging và hiệu quả remediation

Một quy trình finding cần đo cả tốc độ xử lý lẫn mức giảm rủi ro. Không chỉ đếm tổng số finding.

| Chỉ số | Cách hiểu | Mục đích |
|---|---|---|
| Open findings theo priority | Số finding chưa giải quyết ở P0–P4. | Nhìn backlog theo mức khẩn cấp. |
| Mean Time to Triage (MTTT) | Thời gian từ khi finding xuất hiện tới khi được phân loại/định tuyến. | Đo tốc độ tiếp nhận. |
| Mean Time to Assign (MTTA) | Thời gian từ khi finding xuất hiện tới khi có owner. | Phát hiện tắc nghẽn ownership. |
| Mean Time to Remediate (MTTR) | Thời gian từ phát hiện tới remediation được xác minh. | Đo khả năng khắc phục. |
| SLA breach rate | Tỷ lệ finding quá hạn theo priority. | Quản lý escalation. |
| Finding aging | Số finding tồn tại theo nhóm tuổi, ví dụ 0–7, 8–30, 31–60, trên 60 ngày. | Phát hiện backlog cũ. |
| Reopen/recurrence rate | Finding hoặc nguyên nhân gốc xuất hiện lại sau remediation. | Đo chất lượng khắc phục. |
| Suppression ratio | Tỷ lệ finding được suppress so với tổng finding. | Phát hiện suppression quá rộng. |
| Remediation success rate | Tỷ lệ ticket có kết quả verify thành công. | Đánh giá hiệu quả runbook. |
| Risk reduction | Số exposure được giải quyết/giảm severity và mức criticality của tài nguyên. | Đo kết quả bảo mật thực tế. |

Ví dụ SLA nội bộ để bắt đầu thiết kế (cần điều chỉnh theo tổ chức):

| Priority | Triage/owner | Kế hoạch xử lý | Escalation |
|---|---|---|---|
| P0 | Ngay khi nhận | Incident response ngay | Incident commander/on-call lead |
| P1 | Trong ca trực hiện tại | Remediation khẩn cấp theo runbook | Security lead và service owner |
| P2 | Trong 1 ngày làm việc | Sprint hoặc maintenance window gần nhất | Engineering manager |
| P3 | Trong 5 ngày làm việc | Backlog có deadline | Team lead |
| P4 | Theo chu kỳ review | Hardening backlog | Security governance |

Đây là ví dụ SLA nội bộ, không phải SLA mặc định của AWS. Các tổ chức cần điều chỉnh theo hợp đồng, chính sách compliance, mức độ trực và khả năng thay đổi production.

### 13.1. Lưu ý về thời hạn lưu finding

Security Hub CSPM tự xóa finding cũ để giảm noise:

- Finding ACTIVE không được cập nhật trong 90 ngày sẽ hết hạn và bị xóa vĩnh viễn.
- Finding ARCHIVED không được cập nhật trong 30 ngày sẽ hết hạn và bị xóa vĩnh viễn.

Thời gian tính phụ thuộc loại finding và các timestamp như UpdatedAt/ProcessedAt. BatchUpdateFindings không làm mới UpdatedAt. Nếu cần lưu trữ bằng chứng lâu dài, hãy export finding sang Amazon S3 qua EventBridge/custom action hoặc cơ chế export phù hợp. Ticket system cũng cần giữ liên kết tới finding và bản ghi audit độc lập.

## 14. Quản lý nhiều tài khoản và Region

Trong môi trường AWS Organizations, nên chỉ định delegated administrator cho Security Hub và quản lý coverage ở cấp tổ chức. Delegated administrator có thể xem finding của member accounts trong phạm vi được hỗ trợ và thiết lập tích hợp, automation, policy theo quyền.

Với Security Hub CSPM:

- AWS Organizations declarative policies là cách được khuyến nghị hiện nay để quản lý cấu hình CSPM trên tổ chức.
- Central configuration là cơ chế legacy; tổ chức đang dùng có thể tiếp tục, nhưng không nên chọn cho triển khai mới nếu không có lý do tương thích.
- Cross-Region aggregation có home Region và linked Regions để tập trung finding, insight, compliance status và security score.
- Bật aggregation không tự bật Security Hub CSPM trong các Region; mỗi account cần được enable/managed riêng.
- Administrator cần đăng nhập home Region để xem dữ liệu đã tổng hợp từ member accounts và linked Regions.

Với AWS Security Hub hiện hành, Region aggregation cho phép tạo automation ở home Region áp dụng cho các linked Regions theo cấu hình. Các Region chưa linked có thể cần rule riêng. Khi thay đổi aggregation hoặc delegated administrator, hãy kiểm tra ảnh hưởng tới automation và ticketing.

### 14.1. Ownership theo account/OU

Có thể chia trách nhiệm như sau:

- Security tooling account: quản lý delegated administration, policy, automation, integrations và dashboard.
- Workload account: chịu trách nhiệm sửa resource và cung cấp bằng chứng.
- Platform account: quản lý network, IAM nền tảng, CI/CD, logging và các dịch vụ dùng chung.
- Data account: chịu trách nhiệm phân loại, bảo vệ và retention dữ liệu.
- Incident response: xử lý finding cho thấy compromise hoặc hành vi đáng ngờ đang diễn ra.

Security team điều phối và xác minh; workload owner chịu trách nhiệm remediation trong phạm vi ứng dụng/resource. Mô hình RACI rõ ràng giúp finding không bị chuyển qua nhiều nhóm mà không có quyết định.

## 15. Quy trình vận hành end-to-end

Sơ đồ dưới đây mô tả một vòng đời tham khảo:

~~~mermaid
flowchart TD
    A["Finding từ GuardDuty / Inspector / Macie / Config"] --> B["Security Hub chuẩn hóa và tập hợp"]
    B --> C["Triage: xác minh, enrich, deduplicate"]
    C --> D{"Có dấu hiệu compromise đang diễn ra?"}
    D -->|"Có"| E["Incident response / containment"]
    D -->|"Không"| F["Ưu tiên theo severity + asset criticality + exposure"]
    E --> G["Chỉ định incident owner và lưu bằng chứng"]
    F --> H["Tra cứu application/resource owner"]
    H --> I["Tạo hoặc cập nhật ticket"]
    I --> J["Owner lập remediation plan và change"]
    J --> K["Thực hiện remediation"]
    K --> L["Verify bằng provider/control/scan"]
    L --> M{"Đã an toàn?"}
    M -->|"Chưa"| J
    M -->|"Rồi"| N["Cập nhật finding/ticket và đóng việc"]
    G --> L
    N --> O["Metrics, lessons learned và ngăn tái diễn"]
~~~

Quy trình vận hành chi tiết:

1. Nhận finding và xác định đúng account, Region, resource, provider.
2. Xác minh finding, evidence, confidence và tình trạng thực tế.
3. Tìm finding liên quan, deduplicate và xác định nguyên nhân gốc.
4. Đánh giá severity, exploitability, exposure, criticality và blast radius.
5. Xác định owner; nếu chưa rõ, chuyển ownership triage.
6. Tạo ticket hoặc remediation plan; ghi finding ID và resource ARN.
7. Đặt SLA, due date, approver và tiêu chí hoàn tất.
8. Chọn remediation phù hợp; có approval/rollback nếu cần.
9. Triển khai thay đổi qua IaC/pipeline/runbook.
10. Verify qua nguồn phát hiện hoặc kiểm tra độc lập.
11. Cập nhật workflow/ticket và lưu bằng chứng.
12. Theo dõi finding tái xuất hiện, aging và xu hướng backlog.

## 16. Tình huống thực hành: S3 bucket public trên tài khoản production

Một finding từ Security Hub CSPM cho biết S3 bucket có thể truy cập công khai. Bucket thuộc tài khoản production và có tag Application=customer-data. Nhóm bảo mật cần ưu tiên, phân công và theo dõi đến khi xác minh an toàn.

**Bước 1 – Triage**

- Đọc finding ID, ProductArn, resource ARN, severity và compliance status.
- Kiểm tra bucket policy, ACL, Block Public Access và access point.
- Tra cứu owner từ tag, AppRegistry hoặc CMDB.
- Xác định bucket có chứa dữ liệu nhạy cảm hay không và có access log/CloudTrail evidence về truy cập công khai không.
- Nếu có dấu hiệu dữ liệu bị truy cập trái phép, kích hoạt incident response và bảo toàn evidence.

**Bước 2 – Ưu tiên**

Nếu bucket chứa dữ liệu khách hàng và policy cho phép public read ngoài ý muốn, xếp P0/P1 theo bằng chứng và phạm vi exposure. Nếu bucket là website static public đã được phê duyệt, cần xác minh ngoại lệ, kiến trúc CloudFront/OAC và scope của finding trước khi suppress.

**Bước 3 – Phân công**

- Owner: customer-data team.
- Phối hợp: cloud platform và security.
- Ticket: ghi finding ID, bucket ARN, policy evidence, due date và remediation.
- Workflow: NOTIFIED khi đã giao owner trong Security Hub CSPM.

**Bước 4 – Remediation**

- Xác định nguồn public access là bucket policy, ACL, access point hay account-level setting.
- Nếu public access không cần thiết, sửa policy/ACL và bật Block Public Access ở phạm vi phù hợp.
- Nếu website cần public content, chuyển sang CloudFront với origin access control và policy giới hạn.
- Triển khai thay đổi qua IaC để tránh drift.

**Bước 5 – Verify**

- Đọc lại bucket policy và public access block settings.
- Kiểm tra truy cập từ một client không được phép.
- Kiểm tra luồng website hợp lệ nếu bucket phục vụ nội dung công khai.
- Chờ Security Hub/AWS Config đánh giá lại và xác minh Compliance.Status=PASSED.
- Lưu CloudTrail event, test output và ticket change record.

**Bước 6 – Đóng công việc**

Khi bằng chứng đầy đủ, ticket được chuyển Done và finding được cập nhật RESOLVED hoặc tự resolve theo kết quả control. Theo dõi lần scan tiếp theo để đảm bảo bucket không bị mở public lại do một pipeline hoặc policy khác.

## 17. Những sai lầm thường gặp

1. **Chỉ sắp xếp theo severity.** Bỏ qua resource criticality, exposure, exploitability và blast radius.
2. **Dùng severity làm priority.** Severity của finding và SLA priority nội bộ là hai khái niệm khác nhau.
3. **Nhầm Workflow với RecordState.** Workflow theo dõi điều tra; RecordState do provider quản lý vòng đời bản ghi.
4. **Giao owner theo tên resource.** Tên có thể sai; cần tags, AppRegistry, CMDB hoặc account owner.
5. **Tạo một ticket cho mọi finding.** Không gom theo nguyên nhân gốc có thể tạo backlog trùng lặp.
6. **Suppress để giảm backlog.** Suppression không khắc phục cấu hình và cần lý do, owner, thời hạn review.
7. **Đóng finding ngay sau khi deploy.** Phải xác minh bằng nguồn kiểm tra hoặc provider.
8. **Để ticket system và Security Hub tự ghi đè nhau.** Cần quy định nguồn sự thật cho assignee, workflow và evidence.
9. **Dùng BatchUpdateFindings để sửa RecordState.** API này không cập nhật RecordState.
10. **Cho rằng BatchUpdateFindings làm mới UpdatedAt.** API này không thay đổi UpdatedAt.
11. **Cho rằng finding RESOLVED sẽ không xuất hiện lại.** Provider có thể tạo hoặc cập nhật finding mới cho cùng vấn đề.
12. **Bỏ qua thời hạn lưu finding.** Active finding cũ có thể bị xóa sau 90 ngày; archived finding sau 30 ngày.
13. **Tự động remediation mọi finding Critical.** Một số hành động có thể gây gián đoạn hoặc phá hủy dữ liệu.
14. **Bỏ qua automation order.** Rule chạy sau có thể ghi đè giá trị rule trước.
15. **Dùng ASFF filter cho OCSF event.** Cần dùng đúng schema và event type.
16. **Đánh giá hiệu quả chỉ bằng số finding đã đóng.** Cần đo risk reduction, recurrence và verify success.

## 18. Bài tập tự kiểm tra

**1. Finding và incident khác nhau thế nào?**

Finding là bản ghi về vấn đề hoặc tín hiệu bảo mật. Incident là sự kiện cần quy trình phản ứng, điều tra và điều phối theo mức độ ảnh hưởng. Một finding có thể là đầu vào để xác định incident.

**2. Vì sao severity không đủ để quyết định priority?**

Severity không phản ánh đầy đủ criticality của tài nguyên, exposure, exploitability, blast radius và tác động kinh doanh.

**3. Workflow.Status=NOTIFIED có nghĩa gì?**

Nhóm đã thông báo cho resource owner và đang chờ owner can thiệp/khắc phục.

**4. Có thể dùng RecordState=ARCHIVED để đánh dấu ticket đã đóng không?**

Không. RecordState do finding provider quản lý và không phải trạng thái công việc của khách hàng.

**5. Finding control chuyển từ FAILED sang PASSED thì điều gì có thể xảy ra?**

Security Hub CSPM cập nhật finding hiện có và tự đặt workflow thành RESOLVED.

**6. Trường Criticality trong ASFF mô tả điều gì?**

Mức độ quan trọng của tài nguyên liên quan đến finding, theo thang 0–100.

**7. BatchUpdateFindings có thể cập nhật những trường nào?**

Có thể cập nhật một số trường do khách hàng quản lý như Confidence, Criticality, Note, RelatedFindings, Severity, Types, UserDefinedFields, VerificationState và Workflow.

**8. BatchUpdateFindings có thay đổi UpdatedAt không?**

Không. API này không cập nhật giá trị UpdatedAt của finding.

**9. Vì sao cần idempotency khi tạo ticket từ EventBridge?**

Một finding có thể phát sinh nhiều event do provider cập nhật hoặc retry. Idempotency giúp cập nhật ticket hiện có thay vì tạo ticket trùng.

**10. Khi nào nên dùng remediation plan thay vì ticket riêng cho từng exposure?**

Khi nhiều exposure findings cùng xuất phát từ một resource và một nguyên nhân gốc, và một thay đổi có thể giải quyết hoặc giảm rủi ro của nhiều finding.

**11. Trạng thái remediation plan Resolved có luôn đồng nghĩa mọi finding đã Resolved không?**

Không. Plan có thể resolved vì exposure bị suppress/archive, giảm về Informational hoặc không còn trait liên quan; cần kiểm tra từng finding.

**12. Tại sao không nên tự động block mọi tài nguyên có finding Critical?**

Finding có thể chưa được xác minh hoặc hành động block có thể gây gián đoạn. Cần runbook, điều kiện, approval và rollback theo tác động.

**13. Khi nào cần export finding sang S3?**

Khi cần lưu bằng chứng lâu hơn thời hạn lưu trữ tự động của Security Hub CSPM hoặc cần phân tích lịch sử dài hạn.

**14. Tại sao phải kiểm tra ticket và finding sau remediation?**

Ticket phản ánh công việc, còn finding phản ánh kết quả từ nguồn phát hiện. Hai hệ thống có thể cập nhật ở thời điểm khác nhau.

**15. AWS Security Hub CSPM và Security Hub OCSF có thể dùng chung event pattern không?**

Không. CSPM dùng ASFF với event type Security Hub Findings - Imported; Security Hub V2 dùng OCSF với event type Findings Imported V2.

## 19. Checklist vận hành

- [ ] Security Hub được bật và nhận finding từ các nguồn cần thiết trong account/Region.
- [ ] Có delegated administrator và quy trình quản lý nhiều account/Region.
- [ ] Có quy ước severity, resource criticality và priority nội bộ.
- [ ] Finding được xác minh, enrichment và deduplicate trước khi phân công.
- [ ] Có nguồn owner đáng tin cậy từ tag, AppRegistry, CMDB hoặc account inventory.
- [ ] Ticket chứa finding ID, resource ARN, priority, owner, deadline và tiêu chí verify.
- [ ] Workflow status và RecordState được dùng đúng mục đích.
- [ ] Automation rules có tiêu chí rõ ràng, thứ tự được review và có preview.
- [ ] EventBridge processing có idempotency, retry và dead-letter queue.
- [ ] Ticketing integration có OAuth/secret/KMS permissions và theo dõi throttling.
- [ ] Remediation có pre-check, approval, rollback và audit.
- [ ] Control finding được verify qua compliance status; finding khác được verify qua provider.
- [ ] Có dashboard backlog, aging, SLA, MTTR, recurrence và risk reduction.
- [ ] Finding dài hạn được export trước khi hết thời gian lưu trữ.
- [ ] Có quy trình review suppression và ngoại lệ định kỳ.
- [ ] Có bài học sau sự cố và biện pháp ngăn lỗi tái diễn.

## Tài liệu tham khảo

- [Creating and updating findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html)
- [AWS Security Finding Format (ASFF)](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [Required top-level ASFF attributes](https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html)
- [Optional top-level ASFF attributes](https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html)
- [Setting the workflow status of findings](https://docs.aws.amazon.com/securityhub/latest/userguide/findings-workflow-status.html)
- [BatchUpdateFindings for customers](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-update-batchupdatefindings.html)
- [Filtering findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-manage.html)
- [Understanding automation rules in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/automation-rules.html)
- [Automatically modifying and acting on findings](https://docs.aws.amazon.com/securityhub/latest/userguide/automations.html)
- [Using EventBridge for automated response and remediation](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cloudwatch-events.html)
- [Configuring an EventBridge rule for Security Hub CSPM findings](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-all-findings.html)
- [EventBridge event formats for Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-event-formats.html)
- [Managing Security Hub CSPM for multiple accounts with AWS Organizations](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-accounts-orgs.html)
- [Declarative policies and central configuration in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/orgs-policies-and-central-config.html)
- [Understanding cross-Region aggregation in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation.html)
- [Introduction to AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub-v2.html)
- [Exposure findings in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/exposure-findings.html)
- [Resources and criticality in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/resources-adv.html)
- [Remediation plans in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-remediation-plans.html)
- [Automations in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automations.html)
- [Automation rules in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automation-rules.html)
- [Integrations for AWS Security Hub Jira Cloud](https://docs.aws.amazon.com/securityhub/latest/userguide/jiracloud.html)
- [Integrations for ServiceNow](https://docs.aws.amazon.com/securityhub/latest/userguide/servicenow.html)
- [Security Hub CSPM examples using AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli_securityhub_code_examples.html)

