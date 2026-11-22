# AWS Security Hub và tổng hợp phát hiện bảo mật

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, bảo vệ môi trường AWS cần một nơi tập trung để nhìn thấy cấu hình rủi ro, lỗ hổng, dấu hiệu tấn công và các vấn đề bảo mật do nhiều dịch vụ phát hiện. AWS Security Hub CSPM (Cloud Security Posture Management) giúp đánh giá tài nguyên theo các tiêu chuẩn bảo mật, tiếp nhận findings từ dịch vụ AWS và đối tác, chuẩn hóa chúng theo AWS Security Finding Format (ASFF), rồi hỗ trợ phân loại và theo dõi xử lý. Khi kết hợp với AWS Organizations, Amazon EventBridge, AWS Security Lake và các dịch vụ như GuardDuty, Inspector, Macie, tổ chức có thể xây dựng quy trình giám sát và phản ứng xuyên tài khoản, xuyên Region.

Tại thời điểm biên soạn, AWS phân biệt **AWS Security Hub CSPM** và **AWS Security Hub** theo trải nghiệm hợp nhất mới. Security Hub CSPM tập trung vào posture management, security standards, controls và findings theo ASFF. AWS Security Hub mới cung cấp góc nhìn hợp nhất về exposures, threats, vulnerability và security response; nó nhận dữ liệu OCSF từ Security Hub CSPM cùng các dịch vụ bảo mật khác để tương quan rủi ro và hiển thị attack path. Bài học này tập trung vào Security Hub CSPM và cơ chế tổng hợp findings, đồng thời giải thích mối quan hệ với trải nghiệm Security Hub mới để tránh nhầm lẫn tên dịch vụ.

Sau bài học, người học có thể:

- Phân biệt Security Hub CSPM với GuardDuty, Inspector, Macie và AWS Security Hub mới.
- Giải thích mối quan hệ giữa security standard, control, security check và finding.
- Chuẩn bị AWS Config và bật Security Hub CSPM để thu thập control findings.
- Đọc các trường quan trọng trong ASFF và phân biệt compliance status, workflow status, record state.
- Tích hợp findings từ dịch vụ AWS, sản phẩm đối tác và nguồn tùy chỉnh.
- Quản lý findings, insights, consolidated control findings và security scores.
- Thiết kế quản trị nhiều tài khoản và Region bằng AWS Organizations declarative policies và cross-Region aggregation.
- Tự động hóa triage, thông báo, tạo ticket và remediation bằng Security Hub automation rules cùng EventBridge.
- Theo dõi chi phí, quyền truy cập và chất lượng dữ liệu để duy trì quy trình giám sát đáng tin cậy.

## 1. Vai trò của Security Hub trong kiến trúc bảo mật

Mỗi dịch vụ bảo mật AWS giải quyết một nhóm câu hỏi riêng:

| Dịch vụ | Câu hỏi chính | Dữ liệu hoặc kết quả |
|---|---|---|
| AWS Security Hub CSPM | Cấu hình tài nguyên có phù hợp với best practice và tiêu chuẩn bảo mật không? | Control findings, compliance status, security score |
| Amazon GuardDuty | Có hành vi đáng ngờ hoặc dấu hiệu đe dọa trong tài khoản, workload hay dữ liệu mạng không? | Threat detection findings |
| Amazon Inspector | EC2, container image và Lambda có lỗ hổng hoặc vấn đề exposure nào không? | Vulnerability findings |
| Amazon Macie | Dữ liệu nhạy cảm trong Amazon S3 nằm ở đâu và có rủi ro gì? | Sensitive data findings |
| IAM Access Analyzer | Resource policy có chia sẻ quyền truy cập ra ngoài phạm vi dự kiến không? | Access analysis findings |
| AWS Config | Cấu hình tài nguyên đã thay đổi thế nào và có đáp ứng Config rule không? | Configuration items và rule evaluations |
| AWS Security Hub mới | Nhiều tín hiệu bảo mật kết hợp tạo thành exposure hoặc attack path quan trọng nào? | OCSF findings, correlated exposures và security operations context |

Security Hub CSPM không thay thế các dịch vụ phát hiện chuyên biệt. GuardDuty tiếp tục phân tích tín hiệu để phát hiện threat; Inspector quét lỗ hổng; Macie phân tích dữ liệu nhạy cảm; AWS Config ghi nhận cấu hình. Security Hub CSPM tập hợp các kết quả liên quan vào một giao diện và chuẩn hóa findings để đội bảo mật có thể lọc, ưu tiên và giao xử lý.

Ví dụ, một EC2 instance có thể đồng thời có ba vấn đề: cổng quản trị mở ra Internet, package có lỗ hổng nghiêm trọng và GuardDuty phát hiện hành vi kết nối bất thường. Mỗi dịch vụ tạo finding riêng. Khi xem chúng cùng tài nguyên, tài khoản, Region và mức độ nghiêm trọng, đội bảo mật có thêm bối cảnh để ưu tiên instance đó trước một cấu hình rủi ro ít cấp bách hơn.

Luồng dữ liệu khái quát:

~~~mermaid
flowchart TD
    A[AWS Config] --> H[Security Hub CSPM]
    G[GuardDuty] --> H
    I[Inspector] --> H
    M[Macie] --> H
    X[IAM Access Analyzer và đối tác] --> H
    H --> F[Findings chuẩn hóa ASFF]
    F --> V[Findings, Insights, Standards và Security Scores]
    F --> R[Automation rules]
    R --> E[Amazon EventBridge]
    E --> T[Ticket, SNS, Lambda, Step Functions hoặc SSM]
    F --> L[Amazon Security Lake]
    L --> O[OCSF và phân tích bảo mật]
    F --> U[AWS Security Hub mới]
    U --> P[Exposure correlation và attack path]
~~~

## 2. Security Hub CSPM và AWS Security Hub mới

Tên gọi trong tài liệu AWS đã thay đổi theo quá trình phát triển dịch vụ. Security Hub CSPM trước đây thường được gọi ngắn gọn là AWS Security Hub. Hiện nay, AWS phân biệt hai dịch vụ bổ trợ nhau:

| Khả năng | Security Hub CSPM | AWS Security Hub mới |
|---|---|---|
| Trọng tâm | Cloud security posture management | Unified cloud security operations |
| Kiểm tra best practice và standards | Có | Sử dụng findings từ CSPM |
| Security controls và compliance status | Có | Hiển thị ngữ cảnh từ CSPM |
| Định dạng findings chính | ASFF | OCSF |
| Nguồn dữ liệu | Control checks, dịch vụ AWS và đối tác | CSPM, GuardDuty, Inspector, Macie và các nguồn được hỗ trợ |
| Tương quan exposures và attack paths | Không phải trọng tâm chính | Có |
| Tự động hóa triage và phản ứng | Automation rules và EventBridge | Workflow hợp nhất theo tính năng của Security Hub mới |

Security Hub CSPM gửi findings sang Security Hub mới. Security Hub mới có thể kết hợp misconfiguration từ CSPM, threat findings từ GuardDuty, vulnerability từ Inspector và dữ liệu nhạy cảm từ Macie để xác định exposures có mức rủi ro cao. Ví dụ, một package có lỗ hổng chưa chắc là exposure nghiêm trọng nếu workload không thể truy cập từ bên ngoài. Khi kết hợp lỗ hổng với network reachability và cấu hình quyền, hệ thống có thể giúp đội bảo mật nhìn thấy đường tấn công có khả năng khai thác.

OCSF là Open Cybersecurity Schema Framework, một schema mở dùng để chuẩn hóa dữ liệu an ninh. ASFF vẫn là định dạng findings của Security Hub CSPM. Khi đưa findings vào Amazon Security Lake, Security Lake có thể chuyển đổi dữ liệu từ ASFF sang OCSF để phân tích cùng các nguồn bảo mật khác.

Khi đọc tài liệu, API hoặc màn hình console, hãy xác định đang thao tác với Security Hub CSPM hay AWS Security Hub mới. Hai dịch vụ có thể xuất hiện trong cùng quy trình, nhưng schema, cách tính giá và phạm vi tính năng không hoàn toàn giống nhau.

## 3. Security standards và security controls

Security standard là bộ yêu cầu dựa trên quy định, framework ngành hoặc best practice. Mỗi standard bao gồm nhiều control. Control mô tả một biện pháp bảo vệ có thể kiểm tra trên tài nguyên AWS.

Một số standard Security Hub CSPM hỗ trợ gồm:

- AWS Foundational Security Best Practices (FSBP).
- CIS AWS Foundations Benchmark.
- NIST SP 800-53 Revision 5.
- NIST SP 800-171 Revision 2.
- Payment Card Industry Data Security Standard (PCI DSS).
- AWS Resource Tagging và AI Security Best Practices.
- Một số standard hoặc profile khác, bao gồm CRI và service-managed standards.

Danh sách và phiên bản standard có thể khác nhau theo Region và thay đổi theo thời gian. Hãy xem trang Standards reference trong tài liệu AWS trước khi đưa một standard vào phạm vi kiểm toán.

Ví dụ, một control có thể yêu cầu Amazon S3 bucket không cho phép public read. Security Hub CSPM kiểm tra cấu hình liên quan và tạo finding nếu bucket vi phạm. Một control khác có thể yêu cầu EBS volume được mã hóa. Mỗi control thường gắn với một hoặc nhiều loại tài nguyên và một phép kiểm tra cụ thể.

Cần phân biệt ba khái niệm:

- **Standard:** bộ yêu cầu tổng thể, chẳng hạn FSBP hoặc CIS.
- **Control:** một safeguard nằm trong standard, chẳng hạn kiểm tra mã hóa hoặc public access.
- **Finding:** kết quả cụ thể của lần kiểm tra hoặc một cảnh báo bảo mật, gắn với tài nguyên và nguồn phát hiện.

Một control có thể xuất hiện trong nhiều standard. Nếu không dùng consolidated control findings, Security Hub CSPM có thể tạo nhiều finding cho cùng một lần kiểm tra, mỗi finding gắn với một standard. Khi bật consolidated control findings, dịch vụ tạo một finding chung cho control đó, giúp giảm nhiễu và trùng lặp.

Security Hub CSPM không cấp chứng nhận tuân thủ thay cho tổ chức. Một control passed chỉ cho biết phép kiểm tra tương ứng đạt tại thời điểm đánh giá. Việc đáp ứng toàn bộ một standard còn phụ thuộc vào phạm vi, quy trình, bằng chứng và những yêu cầu ngoài phạm vi kiểm tra tự động.

## 4. AWS Config là điều kiện quan trọng để tạo control findings

Security Hub CSPM dùng service-linked AWS Config rules để thực hiện phần lớn security checks. Vì vậy, AWS Config cần được bật và resource recorder cần ghi nhận các loại tài nguyên mà controls đang kiểm tra.

Trước khi bật standards:

1. Chọn các AWS account và Region nằm trong phạm vi giám sát.
2. Bật AWS Config tại từng account và Region.
3. Cấu hình recorder ghi nhận các resource type cần thiết.
4. Kiểm tra IAM role của Configuration Recorder có đủ quyền ghi nhận tài nguyên.
5. Xác nhận AWS Config đang hoạt động và có dữ liệu.
6. Sau đó bật Security Hub CSPM và các standards cần thiết.

Nếu không ghi nhận resource type cần thiết, control có thể không có đủ dữ liệu để đánh giá. Finding có thể mang trạng thái WARNING hoặc NOT_AVAILABLE thay vì PASSED/FAILED. Không nên kết luận môi trường an toàn chỉ vì không thấy finding thất bại.

Khi triển khai trong Organizations, cần bảo đảm AWS Config được thiết lập đồng nhất cho member accounts và Regions thuộc phạm vi. Việc bật Security Hub CSPM không tự động đồng nghĩa mọi resource type đều được AWS Config ghi nhận theo yêu cầu của mọi control.

## 5. Bật Security Hub CSPM cho một tài khoản và Region

Có thể bật Security Hub CSPM qua console hoặc API. Ví dụ AWS CLI:

~~~bash
aws securityhub enable-security-hub \
  --enable-default-standards \
  --region ap-southeast-1
~~~

Khi bật qua API với default standards, Security Hub CSPM bật AWS Foundational Security Best Practices và CIS AWS Foundations Benchmark v1.2.0 theo hành vi mặc định được tài liệu hóa. Có thể dùng tùy chọn không bật default standards nếu muốn chủ động chọn tiêu chuẩn sau đó.

Kiểm tra standards đã bật:

~~~bash
aws securityhub get-enabled-standards \
  --region ap-southeast-1
~~~

Xem các findings hiện có:

~~~bash
aws securityhub get-findings \
  --max-results 20 \
  --region ap-southeast-1
~~~

Trong môi trường production, không nên chỉ bật service rồi kết luận triển khai đã hoàn tất. Hãy xác minh Config recorder, standards, controls, integrations, account coverage, Region coverage và quyền truy cập vào findings.

Security Hub CSPM có service-linked role để thực hiện các tác vụ được dịch vụ quản lý. Người vận hành và delegated administrator vẫn cần IAM permissions phù hợp để bật dịch vụ, cấu hình standard, xem findings, cập nhật workflow hoặc quản lý Organizations policies.

## 6. Tổ chức findings theo AWS Security Finding Format (ASFF)

Security Hub CSPM chuẩn hóa findings từ các nguồn về ASFF. Mục tiêu là giúp các sản phẩm khác nhau dùng chung một cấu trúc để tìm kiếm, lọc, tương quan và chuyển giao cho hệ thống xử lý.

Các trường ASFF thường gặp:

| Trường | Ý nghĩa |
|---|---|
| Id | Định danh finding do provider tạo |
| ProductArn | ARN của sản phẩm tạo finding |
| GeneratorId | Thành phần hoặc control tạo finding |
| AwsAccountId | AWS account liên quan |
| Region | Region của finding |
| Title | Tiêu đề ngắn |
| Description | Mô tả vấn đề và bối cảnh |
| Severity | Mức độ nghiêm trọng |
| Types | Phân loại finding |
| Resources | Tài nguyên bị ảnh hưởng |
| CreatedAt / UpdatedAt | Thời điểm tạo và cập nhật |
| Compliance | Trạng thái compliance nếu finding có liên quan tới control |
| Workflow | Trạng thái điều tra của khách hàng |
| RecordState | Finding còn active hay đã archived |
| Remediation | Hướng dẫn xử lý hoặc liên kết remediation |

Ví dụ finding rút gọn:

~~~json
{
  "SchemaVersion": "2018-10-08",
  "Id": "example-finding-id",
  "ProductArn": "arn:aws:securityhub:ap-southeast-1::product/aws/securityhub",
  "GeneratorId": "security-control/EC2.2",
  "AwsAccountId": "123456789012",
  "Region": "ap-southeast-1",
  "Title": "EC2 security group allows unrestricted SSH access",
  "Description": "An inbound rule allows SSH access from 0.0.0.0/0.",
  "Severity": {
    "Label": "HIGH"
  },
  "Workflow": {
    "Status": "NEW"
  },
  "RecordState": "ACTIVE",
  "Resources": [
    {
      "Type": "AwsEc2SecurityGroup",
      "Id": "arn:aws:ec2:ap-southeast-1:123456789012:security-group/sg-0123456789abcdef0"
    }
  ]
}
~~~

Ví dụ trên chỉ minh họa các trường chính. Finding thực tế có thể chứa nhiều thuộc tính hơn, bao gồm ProductFields, UserDefinedFields, Network, Process, ThreatIntelIndicators, Vulnerabilities và các đối tượng resource chi tiết.

Đối với control findings, các trường SecurityControlId và SecurityControlArn rất hữu ích khi viết automation. AWS khuyến nghị lọc theo control ID hoặc ARN thay vì Title hoặc Description, vì tiêu đề và mô tả có thể thay đổi theo thời gian.

## 7. Severity, compliance status và workflow status

Ba nhóm trạng thái này trả lời các câu hỏi khác nhau và không nên dùng thay thế cho nhau.

**Severity** cho biết mức độ quan trọng hoặc tác động của vấn đề. Các mức thường gặp là CRITICAL, HIGH, MEDIUM, LOW và INFORMATIONAL. Severity giúp ưu tiên điều tra, nhưng cần kết hợp với mức độ quan trọng của tài nguyên và khả năng khai thác.

**Compliance.Status** mô tả kết quả security check của control finding:

| Giá trị | Ý nghĩa |
|---|---|
| PASSED | Tài nguyên đáp ứng điều kiện của control tại lần kiểm tra |
| FAILED | Tài nguyên không đáp ứng điều kiện |
| WARNING | Không thể xác định PASSED hay FAILED, ví dụ thiếu AWS Config recording cho resource type |
| NOT_AVAILABLE | Không thể hoàn tất kiểm tra, resource bị xóa hoặc đánh giá không áp dụng |

**Workflow.Status** theo dõi tiến độ điều tra của đội vận hành:

| Giá trị | Ý nghĩa |
|---|---|
| NEW | Finding mới cần được xem xét |
| NOTIFIED | Đã thông báo cho chủ sở hữu tài nguyên |
| SUPPRESSED | Đã xem xét và xác định không cần hành động theo chính sách |
| RESOLVED | Đã khắc phục và xác nhận vấn đề được giải quyết |

**RecordState** mô tả finding còn active hay đã archived. Một finding có thể có Workflow.Status là RESOLVED nhưng RecordState vẫn ACTIVE. Điều này không mâu thuẫn: vấn đề đã được xử lý theo workflow, còn finding record vẫn tồn tại để lưu lịch sử.

Security Hub CSPM có thể tự thay đổi workflow status của control finding. Ví dụ, khi compliance chuyển từ PASSED sang FAILED, WARNING hoặc NOT_AVAILABLE, workflow status có thể được đặt lại thành NEW để yêu cầu điều tra. Khi control finding có compliance PASSED, dịch vụ tự đặt workflow status thành RESOLVED.

Không dùng SUPPRESSED để che giấu vấn đề chỉ vì finding gây nhiều nhiễu. Trước khi suppress, cần có lý do, chủ sở hữu, phạm vi áp dụng, thời hạn xem xét và tài liệu phê duyệt nếu tổ chức yêu cầu.

## 8. Đọc control status và security score

Security Hub CSPM tổng hợp trạng thái của các findings thuộc cùng một control để tạo control status:

- **Passed:** các findings liên quan đều PASSED.
- **Failed:** có ít nhất một finding FAILED.
- **Unknown:** có WARNING hoặc NOT_AVAILABLE nhưng không có FAILED.
- **No data:** chưa có finding để đánh giá, hoặc không có dữ liệu áp dụng.
- **Disabled:** control đang bị tắt trong account và Region.

Security score cho biết tỷ lệ controls đã passed trong tập controls được tính điểm. Controls có trạng thái No data không được đưa vào mẫu số. Các findings bị archived hoặc suppressed không được tính khi xác định control status. Do đó, việc suppress hàng loạt có thể làm score trông tốt hơn mà rủi ro thực tế chưa được giải quyết.

Security Hub CSPM thường tạo control status ban đầu trong khoảng 30 phút sau khi người dùng mở Summary hoặc Security standards page lần đầu; các lần cập nhật tiếp theo thường dựa trên dữ liệu 24 giờ trước đó. Ở một số Region như China và AWS GovCloud (US), lần tạo trạng thái đầu tiên có thể lâu hơn. AWS Config resource recording cần được cấu hình để control status và score xuất hiện.

Không dùng security score làm bằng chứng duy nhất để tuyên bố tuân thủ. Score không phản ánh mọi yêu cầu quy trình, ứng dụng ngoài AWS, ngoại lệ được phê duyệt hoặc toàn bộ rủi ro nghiệp vụ. Hãy xem chi tiết control, findings, tài nguyên, thời gian đánh giá và phạm vi account/Region trước khi báo cáo.

## 9. Consolidated control findings và giảm nhiễu

Một control có thể thuộc nhiều standards. Nếu bật nhiều standards mà không bật consolidated control findings, cùng một security check có thể tạo một finding cho mỗi standard. Điều này làm tăng số lượng finding và gây khó khăn cho deduplication trong ticketing hoặc SIEM.

Consolidated control findings tạo một finding cho mỗi control check, kể cả khi control thuộc nhiều standards. Tính năng này được bật mặc định cho tài khoản bật Security Hub CSPM từ ngày 23/02/2023 trở đi. Với tài khoản cũ, cần kiểm tra cấu hình hiện tại.

Có thể kiểm tra và bật bằng AWS CLI:

~~~bash
aws securityhub update-security-hub-configuration \
  --control-finding-generator SECURITY_CONTROL \
  --region ap-southeast-1
~~~

Giá trị SECURITY_CONTROL bật consolidated control findings. Giá trị STANDARD_CONTROL chuyển về finding riêng theo standard.

Khi thay đổi chế độ, Security Hub CSPM có thể tạo finding mới và archive finding cũ. Quá trình chuyển đổi có thể mất tới 24 giờ và trong thời gian đó có thể thấy cả hai dạng finding. Trước khi đổi, hãy kiểm tra các tích hợp bên ngoài, rule EventBridge, SOAR và dashboard đang dựa trên trường ASFF nào.

## 10. Tích hợp findings từ dịch vụ AWS và đối tác

Sau khi bật Security Hub CSPM, có thể kích hoạt các tích hợp nguồn findings. Một số tích hợp AWS được kích hoạt tự động khi cả Security Hub CSPM và dịch vụ nguồn được bật; những tích hợp khác cần được cấu hình hoặc chấp nhận rõ ràng.

Các nguồn phổ biến:

| Nguồn | Loại findings |
|---|---|
| GuardDuty | Phát hiện hành vi đáng ngờ, credential compromise, kết nối hoặc hoạt động bất thường |
| Inspector | Lỗ hổng trong EC2, container image và Lambda |
| Macie | Dữ liệu nhạy cảm và rủi ro liên quan tới S3 |
| IAM Access Analyzer | Resource policy hoặc quyền truy cập ngoài phạm vi dự kiến |
| AWS Firewall Manager | Vi phạm chính sách bảo vệ mạng hoặc WAF |
| AWS Health | Sự kiện bảo mật, abuse hoặc thay đổi có liên quan đến rủi ro tài khoản |
| IoT Device Defender | Vấn đề bảo mật của thiết bị IoT |
| Third-party products | Findings từ CSPM, EDR, vulnerability scanner, SIEM hoặc công cụ bảo mật khác |

Tích hợp không có nghĩa Security Hub CSPM thực hiện lại phép phân tích của mọi nguồn. Dịch vụ nhận finding đã được provider tạo, chuẩn hóa và hiển thị. Khi điều tra, hãy mở chi tiết finding và xác định ProductArn, ProductName, GeneratorId cùng hướng dẫn của provider để hiểu dữ liệu gốc.

Một sản phẩm đối tác có thể gửi findings qua cơ chế tích hợp được hỗ trợ. Với nguồn tùy chỉnh, có thể dùng BatchImportFindings để tạo hoặc cập nhật findings do provider đó sở hữu. Khách hàng hoặc công cụ SOAR thay mặt khách hàng dùng BatchUpdateFindings để cập nhật workflow và thông tin điều tra. BatchUpdateFindings không dùng để tạo finding mới và hỗ trợ tối đa 100 finding identifiers trong một request.

## 11. Lọc findings và tạo custom insights

Trang Findings có thể chứa số lượng lớn bản ghi. Hãy lọc theo các thuộc tính như:

- AwsAccountId, Region, ResourceType và ResourceId.
- ProductArn hoặc ProductName.
- Severity.Label.
- Workflow.Status và RecordState.
- Compliance.Status.
- Types, Title hoặc các trường liên quan đến control.

Ví dụ file filters.json:

~~~json
{
  "WorkflowStatus": [
    {
      "Value": "NEW",
      "Comparison": "EQUALS"
    }
  ],
  "SeverityLabel": [
    {
      "Value": "HIGH",
      "Comparison": "EQUALS"
    }
  ],
  "RecordState": [
    {
      "Value": "ACTIVE",
      "Comparison": "EQUALS"
    }
  ]
}
~~~

Truy vấn findings:

~~~bash
aws securityhub get-findings \
  --filters file://filters.json \
  --max-results 50 \
  --region ap-southeast-1
~~~

Một custom insight là truy vấn đã lưu để theo dõi một tập findings có ý nghĩa. Ví dụ:

- Findings CRITICAL/HIGH ở tài khoản production.
- Findings của EC2 có port quản trị mở ra Internet.
- Findings chưa được xử lý quá 7 ngày.
- Findings do GuardDuty tạo trong một OU cụ thể.
- Findings liên quan tới resource có tag Owner hoặc Application.

Insight giúp đội bảo mật xem xu hướng và danh sách cần xử lý. Insight không tự sửa tài nguyên và không thay thế workflow ticket hoặc remediation.

## 12. Quản trị nhiều tài khoản bằng AWS Organizations declarative policies

Tại ngày 20/11/2026, AWS khuyến nghị dùng **Security Hub CSPM declarative policies** để quản lý cấu hình nhiều tài khoản và Region trong AWS Organizations. Tính năng này được công bố ngày 13/11/2026 và thay thế central configuration như cơ chế được khuyến nghị cho triển khai mới.

Declarative policy có thể quy định:

- Security Hub CSPM được bật ở Region nào và tắt ở Region nào.
- Standards nào được bật.
- Controls nào được bật hoặc tắt.
- Tham số của một số controls.
- Chính sách được áp dụng cho organization root, OU hoặc account cụ thể.
- Tài khoản mới hoặc tài khoản chuyển OU tự động kế thừa chính sách tương ứng.

Ví dụ policy bật Security Hub CSPM tại tất cả supported Regions, dùng FSBP và bật các controls mặc định:

~~~json
{
  "securityhub_cspm": {
    "cspm_enablement": {
      "enable_in_regions": {
        "@@assign": ["ALL_SUPPORTED"]
      },
      "disable_in_regions": {
        "@@assign": []
      }
    },
    "cspm_standards_controls": {
      "default": {
        "enabled_standards": {
          "@@assign": [
            "aws-foundational-security-best-practices/v/1.0.0"
          ]
        },
        "controls_configuration": {
          "default_control_association_status": {
            "@@assign": "ENABLED"
          }
        }
      }
    }
  }
}
~~~

Policy trên minh họa cấu trúc cơ bản. Trong tổ chức thực tế, có thể tạo regional override cho những Region cần cấu hình standard hoặc controls khác nhau. Cần xem xét cẩn thận vì regional override thay thế cấu hình mặc định của Region đó; nó không tự động hợp nhất mọi thiết lập từ default.

Trước khi áp dụng policy, bảo đảm AWS Config đã ghi nhận các resource types cần thiết và service-linked role AWSServiceRoleForSecurityHub đã tồn tại trong management account hoặc delegated administrator account. Policy không tự cấu hình AWS Config. Nếu dùng delegated administrator, đăng ký account đó với AWS Organizations và bật quyền quản trị Security Hub CSPM theo hướng dẫn AWS. Có thể kiểm tra service-linked role bằng lệnh aws iam get-role --role-name AWSServiceRoleForSecurityHub.

Quy trình CLI tổng quát:

~~~bash
# Enable trusted access for Security Hub CSPM
aws organizations enable-aws-service-access \
  --service-principal securityhub.amazonaws.com

# Optional: register a delegated administrator account
aws organizations register-delegated-administrator \
  --account-id 111122223333 \
  --service-principal securityhub.amazonaws.com

# Enable the delegated administrator in the home Region
aws securityhub enable-organization-admin-account \
  --admin-account-id 111122223333 \
  --region ap-southeast-1

# Enable the Security Hub CSPM policy type on the organization root
aws organizations enable-policy-type \
  --root-id r-example \
  --policy-type SECURITYHUB_CSPM_POLICY

# Create a declarative policy
aws organizations create-policy \
  --name "securityhub-cspm-baseline" \
  --description "Enable Security Hub CSPM and FSBP across supported Regions" \
  --type SECURITYHUB_CSPM_POLICY \
  --content file://securityhub-cspm-policy.json

# Attach the policy to an OU or organization root
aws organizations attach-policy \
  --policy-id p-example \
  --target-id r-example
~~~

Thay root ID, policy ID và target ID bằng giá trị thực của tổ chức. Thực hiện từ principal có quyền quản trị Organizations policy type tương ứng. Nên thử trên OU sandbox trước, xem preview tác động và xác nhận account/Region coverage trước khi gắn vào root.

Declarative policies và central configuration không thể được sử dụng đồng thời trong cùng tổ chức. Nếu đang dùng central configuration, hãy dùng import tool trong Security Hub CSPM console để chuyển cấu hình hiện tại sang declarative policies trước khi thay đổi. Không đính kèm policy thử nghiệm vào một account production trước khi hiểu rằng việc dùng declarative policy sẽ thay đổi cơ chế quản trị central configuration của toàn tổ chức.

Central configuration vẫn được hỗ trợ cho tổ chức đang dùng, nhưng hiện được xem là cơ chế cũ. Khi bắt đầu triển khai mới, ưu tiên declarative policies.

## 13. Cross-Region aggregation và home Region

Cross-Region aggregation cho phép tập trung findings, finding updates, insights, control compliance statuses và security scores từ nhiều Region về một **home Region**. Một số API cũ vẫn dùng thuật ngữ aggregation Region.

Tạo finding aggregator từ Region dự kiến làm home Region:

~~~bash
aws securityhub create-finding-aggregator \
  --region ap-southeast-1 \
  --region-linking-mode SPECIFIED_REGIONS \
  --regions ap-southeast-2 eu-west-1
~~~

Các chế độ Region linking:

- ALL_REGIONS: liên kết tất cả Region được hỗ trợ và tự động bao gồm Region mới khi dịch vụ hỗ trợ và tài khoản đã opt-in.
- ALL_REGIONS_EXCEPT_SPECIFIED: liên kết tất cả ngoại trừ danh sách Region loại trừ.
- SPECIFIED_REGIONS: chỉ liên kết danh sách đã chỉ định.
- NO_REGIONS: không liên kết Region nào.

Home Region không tự động bật Security Hub CSPM tại các linked Regions. Mỗi account và Region cần được bật Security Hub CSPM, Config và các controls cần thiết. Chỉ những Region có Security Hub CSPM enabled mới gửi dữ liệu để tổng hợp.

Declarative policies và cross-Region aggregation là hai cấu hình riêng. Declarative policy quyết định account/Region nào bật Security Hub CSPM và controls nào hoạt động; finding aggregator quyết định dữ liệu findings từ các Region được gom về đâu. Nếu policy bật một Region nhưng Region đó không nằm trong linked Regions, delegated administrator có thể không nhìn thấy findings của Region đó ở home Region.

Với control đánh giá global resources như IAM, cần chú ý việc tạo finding ở nhiều Region. Hãy cấu hình controls và Region coverage để tránh trùng lặp hoặc hiểu nhầm rằng nhiều finding tương đương nhiều tài nguyên khác nhau.

## 14. Delegated administrator và quyền của member accounts

Trong mô hình Organizations, nên chỉ định một delegated administrator chuyên trách bảo mật. Tài khoản này quản lý cấu hình Security Hub CSPM, tổng hợp findings và điều phối xử lý. Tài khoản quản lý Organizations vẫn giữ vai trò quản trị tổ chức; không nên dùng tài khoản này làm nơi vận hành hằng ngày của nhóm bảo mật.

Delegated administrator có thể xem findings của member accounts theo quyền và phạm vi quản trị. Member account vẫn có thể xem findings của chính mình và xử lý các vấn đề thuộc phạm vi tài khoản. Quyền cập nhật finding, quản lý standards, integrations và automation phụ thuộc mô hình quản trị cùng IAM policy.

Các nguyên tắc:

- Tách quyền quản trị Organizations, quyền cấu hình Security Hub và quyền xử lý findings.
- Dùng IAM Identity Center hoặc cơ chế federation phù hợp để cấp quyền cho người trực.
- Chỉ cho phép người có trách nhiệm cập nhật workflow status hoặc suppress findings.
- Dùng role riêng cho automation và giới hạn resource/action có thể thay đổi.
- Kiểm toán các thay đổi về standards, controls, policy attachments và finding updates bằng CloudTrail.
- Không chia sẻ thông tin xác thực giữa delegated administrator và member accounts.

## 15. Automation rules trong Security Hub CSPM

Automation rules tự động cập nhật hoặc suppress findings theo điều kiện. Ví dụ:

- Thay đổi severity dựa trên tag hoặc criticality của resource.
- Đặt Workflow.Status thành SUPPRESSED cho finding đã được chấp thuận là ngoại lệ.
- Thêm note và UserDefinedFields để gắn ticket ID.
- Đặt Workflow.Status thành NOTIFIED khi finding được giao cho owner.
- Điều chỉnh severity của finding từ nguồn đối tác theo quy tắc nội bộ.

Nên lọc theo các trường ổn định như SecurityControlId, ProductArn, ResourceType, ResourceId hoặc tag. Hạn chế phụ thuộc vào Title/Description vì các trường này có thể được provider cập nhật.

Automation rules được áp dụng gần thời gian thực và chạy trước EventBridge rules. Vì vậy, EventBridge nhận finding sau khi các trường đã được automation rule cập nhật. Thứ tự này rất quan trọng nếu EventBridge rule lọc theo Severity hoặc Workflow.Status.

Không tự động suppress mọi finding severity thấp. Một finding LOW có thể là dấu hiệu của vấn đề lớn hơn khi kết hợp với lỗ hổng, exposure hoặc tài nguyên quan trọng.

## 16. Tự động phản ứng bằng Amazon EventBridge

Security Hub CSPM gửi findings mới và findings được cập nhật tới EventBridge. EventBridge có thể kích hoạt Lambda, Step Functions, SNS, SQS, Systems Manager Automation, API destination hoặc chuyển sự kiện tới bus của tài khoản khác.

Ví dụ event pattern lọc findings CRITICAL/HIGH đang NEW và ACTIVE:

~~~json
{
  "source": [
    "aws.securityhub"
  ],
  "detail-type": [
    "Security Hub Findings - Imported"
  ],
  "detail": {
    "findings": {
      "Severity": {
        "Label": [
          "CRITICAL",
          "HIGH"
        ]
      },
      "Workflow": {
        "Status": [
          "NEW"
        ]
      },
      "RecordState": [
        "ACTIVE"
      ]
    }
  }
}
~~~

EventBridge rule có thể gọi một Lambda để tạo ticket hoặc gửi thông báo SNS. Với remediation, có thể gọi Step Functions để điều phối các bước như kiểm tra resource owner, xác minh trạng thái, yêu cầu approval và chạy Systems Manager Automation.

Luồng phản ứng mẫu:

~~~mermaid
flowchart TD
    A[Security Hub CSPM finding] --> B[Automation rule cập nhật finding]
    B --> C[EventBridge nhận event]
    C --> D{Severity và resource phù hợp?}
    D -- Không --> E[Giữ trong hàng đợi triage]
    D -- Có --> F[Tạo ticket và thông báo owner]
    F --> G[Kiểm tra quyền và điều kiện remediation]
    G --> H{Cần phê duyệt?}
    H -- Có --> I[Chờ người có thẩm quyền]
    H -- Không --> J[Chạy remediation]
    I --> J
    J --> K[Kiểm tra lại resource]
    K --> L[Cập nhật workflow và lưu audit trail]
~~~

Ví dụ thực tế: Security Hub CSPM phát hiện security group cho phép SSH từ 0.0.0.0/0. EventBridge gửi finding tới Lambda. Lambda kiểm tra tag Environment, Owner và ticket change hiện có. Nếu là môi trường production, workflow tạo ticket và yêu cầu phê duyệt. Sau khi được duyệt, Systems Manager Automation hoặc quy trình IaC cập nhật rule. Sau remediation, AWS Config và Security Hub CSPM chạy kiểm tra lại; finding được cập nhật khi trạng thái thay đổi.

Automation phải idempotent. EventBridge có thể gửi lại event; workflow không được tạo nhiều ticket hoặc lặp lại thao tác thay đổi cấu hình ngoài ý muốn. Hãy dùng finding ID, resource ARN và trạng thái xử lý làm khóa deduplication. Với hành động có thể gây gián đoạn, cần approval, rollback và bước hậu kiểm.

## 17. Cập nhật workflow và ghi chú cho finding

Có thể dùng BatchUpdateFindings để cập nhật workflow status, note, severity, confidence, criticality và một số trường khách hàng được phép chỉnh sửa. API không tạo finding mới; provider dùng BatchImportFindings cho findings do chính họ sở hữu.

Ví dụ cập nhật một finding thành RESOLVED:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers Id="FINDING_ID",ProductArn="PRODUCT_ARN" \
  --workflow Status="RESOLVED" \
  --note Text="Remediated by change CHG-1234 and verified.",UpdatedBy="security-operations" \
  --region ap-southeast-1
~~~

Cần truyền cả Id và ProductArn của finding. Có thể lấy các giá trị này bằng GetFindings. BatchUpdateFindings hỗ trợ tối đa 100 findings trong một request và cập nhật có thể mất vài phút để hiển thị.

Việc đặt Workflow.Status thành RESOLVED là ghi nhận kết quả điều tra của khách hàng. Nó không tự sửa resource. Để xác nhận remediation, cần kiểm tra tài nguyên bằng API, Config hoặc kiểm tra nghiệp vụ phù hợp. Nếu provider phát hiện vấn đề tái xuất hiện, finding có thể trở lại trạng thái cần điều tra.

## 18. Kết nối Security Hub CSPM với Amazon Security Lake

Security Lake tập trung dữ liệu bảo mật theo OCSF. Khi bật Security Hub CSPM findings làm nguồn cho Security Lake, Security Lake nhận findings qua luồng độc lập và chuyển đổi ASFF sang OCSF.

Sự kết hợp này hữu ích khi tổ chức cần:

- Lưu trữ dữ liệu bảo mật lâu dài cho điều tra và phân tích.
- Truy vấn findings cùng CloudTrail, VPC Flow Logs và các nguồn khác.
- Xây dựng dashboard hoặc phát hiện tương quan bằng công cụ phân tích hỗ trợ OCSF.
- Chia sẻ dữ liệu với hệ thống SIEM mà không phải tự chuẩn hóa từng định dạng provider.

Security Lake không quản lý findings và không thay đổi cấu hình Security Hub CSPM. Muốn cập nhật Workflow.Status hoặc xử lý control findings, vẫn thao tác qua Security Hub CSPM console, API hoặc CLI. Security Lake phục vụ lưu trữ và phân tích dữ liệu; Security Hub CSPM phục vụ posture management và workflow findings.

## 19. Giám sát chất lượng dữ liệu và xử lý sự cố

Một hệ thống tổng hợp chỉ hữu ích khi coverage và dữ liệu đầu vào đầy đủ. Khi findings không xuất hiện hoặc security score bất thường, kiểm tra theo thứ tự:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có control findings | AWS Config chưa bật hoặc thiếu resource recording | Kiểm tra recorder, resource type và Region |
| Không thấy findings của member account | Account chưa liên kết với delegated administrator hoặc chưa bật service | Kiểm tra Organizations, service access và account status |
| Không thấy findings từ Region khác | Region chưa bật Security Hub CSPM hoặc chưa linked | Kiểm tra policy Region và home Region aggregation |
| Control status là Unknown | Config không có dữ liệu hoặc check không thể xác định kết quả | Kiểm tra Config recorder, quyền và resource state |
| Findings bị lặp | Nhiều standards tạo findings riêng hoặc nguồn tích hợp trùng | Kiểm tra consolidated control findings và ProductArn |
| Finding vẫn NEW sau remediation | Check chưa chạy lại hoặc resource chưa thực sự đạt yêu cầu | Kiểm tra Config evaluation và lần cập nhật mới nhất |
| Finding biến mất khỏi danh sách | RecordState ARCHIVED hoặc filter đang loại bản ghi | Kiểm tra RecordState và bộ lọc |
| EventBridge không kích hoạt | Sai source, detail-type, event pattern hoặc target permission | Kiểm tra EventBridge metrics, DLQ và role |
| Automation cập nhật sai finding | Filter quá rộng hoặc phụ thuộc Title/Description | Dùng SecurityControlId, ProductArn và ResourceId |
| Score không khớp kỳ vọng | No data, suppressed hoặc archived findings ảnh hưởng phép tính | Xem từng control và timestamp score |

Khi điều tra, cần lưu finding ID, ProductArn, account, Region, resource ARN, thời điểm, severity, compliance status và workflow status. Đối chiếu dữ liệu với provider gốc và CloudTrail để biết finding được tạo, cập nhật hoặc suppress bởi thành phần nào.

Đối với lỗi permission, kiểm tra IAM policy của người vận hành, delegated administrator và role mà EventBridge/Lambda/Step Functions sử dụng. Không cấp quyền Security Hub quản trị rộng chỉ để sửa một workflow; hãy giới hạn action và resource cần thiết.

## 20. Bảo mật, lưu giữ và kiểm soát chi phí

Findings có thể chứa ARN tài nguyên, cấu hình, thông tin mạng, metadata ứng dụng và dữ liệu liên quan tới sự cố. Hãy bảo vệ chúng như dữ liệu vận hành nhạy cảm.

Các nguyên tắc bảo vệ:

- Chỉ cấp quyền xem findings cho người cần thiết.
- Tách quyền đọc, cập nhật workflow và quản trị standards.
- Kiểm soát quyền truy cập Security Lake, S3 và log destination.
- Ghi lại thay đổi qua CloudTrail.
- Không đưa credential, token hoặc dữ liệu nhạy cảm vào note và user-defined fields.
- Đặt retention theo yêu cầu điều tra và tuân thủ.
- Xác định quy trình xử lý findings do đối tác gửi và kiểm tra độ tin cậy của provider.

Security Hub CSPM có 30-day free trial khi bật lần đầu cho account và Region. Trong thời gian trial, bản thân Security Hub CSPM không tính phí, nhưng các dịch vụ mà nó sử dụng như AWS Config có thể phát sinh chi phí riêng. Sau trial, chi phí CSPM phụ thuộc vào số lượng security checks, finding ingestion events và automation rule evaluations. Bảng giá hiện hành cũng nêu free tier thường xuyên 10.000 finding ingestion events mỗi tháng; hãy kiểm tra pricing page và AWS Pricing Calculator để tính mức phí thực tế.

AWS Security Hub mới có mô hình tính phí riêng theo resources được giám sát và các capability bổ sung như threat analytics. Không gộp chi phí Security Hub CSPM, GuardDuty, Inspector, Macie, Security Lake, CloudWatch và EventBridge thành một khoản duy nhất. Các dịch vụ nguồn, Config items, log storage và truy vấn dữ liệu có thể phát sinh phí riêng.

Biện pháp tối ưu:

- Chỉ bật standards và controls phù hợp với yêu cầu bảo vệ và kiểm toán.
- Dùng consolidated control findings để giảm duplicate findings.
- Dùng automation rules và insights để giảm thao tác thủ công.
- Tối ưu logging và retention nhưng vẫn giữ đủ dữ liệu điều tra.
- Rà soát account/Region coverage để tránh bật dịch vụ ngoài phạm vi.
- Theo dõi chi phí theo account, Region và nguồn findings.

## 21. Thực hành: tập trung findings cho cửa hàng trực tuyến

Một doanh nghiệp thương mại điện tử chạy ứng dụng trên nhiều AWS accounts: production, staging, development và security tooling. Hệ thống dùng CloudFront, ALB, EC2, ECS, S3, RDS và Lambda. Đội bảo mật muốn phát hiện cấu hình yếu, lỗ hổng và dấu hiệu tấn công, sau đó chuyển finding cho đúng nhóm phụ trách.

Một phương án triển khai:

1. Dùng AWS Organizations và chỉ định delegated administrator cho Security Hub CSPM.
2. Tạo declarative policy cho các OU production, staging và development; bật FSBP ở các Region cần thiết.
3. Bật AWS Config recorder cho resource types liên quan ở mọi account và Region thuộc phạm vi.
4. Bật Security Hub CSPM, GuardDuty, Inspector, Macie và IAM Access Analyzer theo nhu cầu.
5. Cấu hình cross-Region aggregation về home Region để đội bảo mật có một điểm quan sát.
6. Bật consolidated control findings để giảm duplicate findings giữa các standards.
7. Tạo custom insights cho findings CRITICAL/HIGH, findings theo application owner và findings chưa xử lý.
8. Tạo automation rules để gắn ticket ID, cập nhật severity theo criticality của resource và suppress ngoại lệ đã phê duyệt.
9. Dùng EventBridge để tạo ticket, gửi SNS và gọi Step Functions hoặc Systems Manager Automation khi cần remediation.
10. Lưu findings vào Security Lake để phục vụ điều tra dài hạn và phân tích tương quan.
11. Theo dõi security score, control status, coverage account/Region, finding age và thời gian xử lý.

Ví dụ quy tắc phân công:

| Nhóm finding | Chủ sở hữu | Hành động |
|---|---|---|
| Public access hoặc security group mở rộng | Cloud platform | Kiểm tra network/resource policy và khắc phục |
| EC2/ECR/Lambda vulnerability | Application owner | Nâng phiên bản, rebuild image hoặc deploy bản vá |
| GuardDuty threat finding | Security operations | Điều tra hoạt động, credential và phạm vi ảnh hưởng |
| S3 sensitive data finding | Data owner và security | Xác minh dữ liệu, policy, encryption và access |
| IAM external access | IAM team | Rà soát trust policy, resource policy và external principal |

Đánh giá hiệu quả bằng các chỉ số: tỷ lệ account/Region được bao phủ, tỷ lệ controls có dữ liệu, số findings CRITICAL/HIGH còn NEW, tuổi finding, thời gian trung bình đến khi được giao owner, thời gian remediation và tỷ lệ tái xuất hiện.

## Kết luận

AWS Security Hub CSPM tập hợp findings từ security checks, dịch vụ AWS và đối tác vào một định dạng ASFF để đội bảo mật có thể lọc, ưu tiên và theo dõi điều tra. Chất lượng tổng hợp phụ thuộc vào AWS Config recording, standards và controls được bật, integrations, account/Region coverage và quy trình quản lý workflow.

Trong triển khai nhiều tài khoản, AWS Organizations declarative policies hiện là cách được khuyến nghị để quản lý cấu hình Security Hub CSPM; cross-Region aggregation vẫn là cấu hình riêng để gom findings về home Region. Automation rules và EventBridge giúp chuyển findings thành ticket, thông báo và remediation có kiểm soát. AWS Security Hub mới bổ sung OCSF, exposure correlation và attack path để tăng ngữ cảnh rủi ro khi kết hợp nhiều nguồn bảo mật.

## Tài liệu tham khảo

- [What is AWS Security Hub CSPM?](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html)
- [What are AWS Security Hub and Security Hub CSPM?](https://docs.aws.amazon.com/securityhub/latest/userguide/)
- [AWS Security Finding Format (ASFF)](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [Creating and updating findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html)
- [Understanding security standards](https://docs.aws.amazon.com/securityhub/latest/userguide/standards-view-manage.html)
- [Standards reference for Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/standards-reference.html)
- [Enabling and configuring AWS Config](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html)
- [Evaluating compliance status and control status](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-overall-status.html)
- [Setting the workflow status of findings](https://docs.aws.amazon.com/securityhub/latest/userguide/findings-workflow-status.html)
- [Consolidated control findings](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html)
- [Managing accounts with declarative policies](https://docs.aws.amazon.com/securityhub/latest/userguide/accounts-orgs-policies.html)
- [Security Hub CSPM policy syntax and examples](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_security_hub_cspm_syntax.html)
- [Declarative policies and central configuration](https://docs.aws.amazon.com/securityhub/latest/userguide/orgs-policies-and-central-config.html)
- [Understanding cross-Region aggregation](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation.html)
- [Enabling cross-Region aggregation](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation-enable.html)
- [AWS service integrations with Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-internal-providers.html)
- [Automatically modifying and acting on findings](https://docs.aws.amazon.com/securityhub/latest/userguide/automations.html)
- [Configuring EventBridge for Security Hub findings](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-all-findings.html)
- [AWS Security Hub CSPM events in EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-securityhub.html)
- [Security Hub CSPM findings in Security Lake](https://docs.aws.amazon.com/security-lake/latest/userguide/security-hub-findings.html)
- [Introduction to the new AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub-v2.html)
- [AWS Security Hub CSPM pricing](https://aws.amazon.com/security-hub/cspm/pricing/)
- [AWS Security Hub unified experience pricing](https://aws.amazon.com/security-hub/pricing/)

