# Amazon GuardDuty và phát hiện hành vi bất thường

Một tài khoản AWS có thể tạo ra hàng triệu sự kiện hoạt động mỗi ngày: người dùng đăng nhập, role được assume, API được gọi, máy chủ kết nối ra Internet, container khởi chạy tiến trình và ứng dụng truy cập dữ liệu. Đội an ninh khó có thể đọc từng log để phát hiện một credential bị đánh cắp, một máy chủ bị điều khiển từ xa hoặc một bucket bị truy cập bất thường. Họ cần một dịch vụ liên tục phân tích tín hiệu, nhận diện mẫu hành vi đáng ngờ và đưa ra cảnh báo có ngữ cảnh để điều tra.

**Amazon GuardDuty** là dịch vụ phát hiện mối đe dọa được quản lý của AWS. Dịch vụ phân tích các nguồn dữ liệu như CloudTrail events, VPC Flow Logs, DNS logs và các nguồn telemetry bảo vệ được bật thêm để nhận diện hoạt động có dấu hiệu xâm nhập hoặc lạm dụng. GuardDuty dùng threat intelligence, quy tắc phát hiện và machine learning để tạo finding khi nhận diện hành vi đáng ngờ.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, GuardDuty giúp bảo vệ account, workload, dữ liệu và môi trường container trên nhiều Region. Người học cần hiểu cách bật dịch vụ, đọc finding, phân biệt mức độ nghiêm trọng, cấu hình tổ chức nhiều account, tích hợp EventBridge và xây dựng quy trình ứng phó. GuardDuty hỗ trợ phát hiện; đội vận hành vẫn phải xác minh, khoanh vùng, xử lý và lưu bằng chứng để duy trì hệ thống an toàn, có khả năng phục hồi và kiểm soát chi phí.

## 1. GuardDuty giải quyết vấn đề gì?

GuardDuty phân tích hoạt động trong môi trường AWS để tìm các dấu hiệu có thể liên quan tới:

- Credential bị lộ hoặc bị sử dụng bất thường.
- API call có dấu hiệu do kẻ tấn công thực hiện.
- EC2 instance liên lạc với địa chỉ IP hoặc domain liên quan đến hoạt động độc hại.
- Máy chủ bị dò quét, khai thác hoặc điều khiển từ xa.
- S3 bucket bị truy cập theo mẫu đáng ngờ hoặc có nguy cơ lộ dữ liệu.
- Container hoặc Kubernetes workload có hành vi bất thường.
- Hoạt động liên quan đến malware hoặc tiến trình đáng ngờ trên workload được hỗ trợ.
- Dấu hiệu xâm nhập hoặc truy cập bất thường vào một số dịch vụ dữ liệu được GuardDuty hỗ trợ.

GuardDuty tạo ra **finding** để mô tả hành vi bị phát hiện, tài nguyên liên quan, thời điểm, mức độ nghiêm trọng và thông tin bổ sung. Finding là một tín hiệu điều tra. Nó không tự chứng minh rằng hệ thống đã bị xâm nhập thành công, cũng không tự xác định đầy đủ phạm vi ảnh hưởng.

GuardDuty có thể giúp phát hiện một số hành vi mà log thuần túy khó nhận ra. Ví dụ, một IAM user vốn chỉ thao tác ở một Region đột nhiên gọi API quản trị từ một địa chỉ IP lạ; một EC2 instance bắt đầu kết nối tới domain liên quan tới command-and-control; hoặc một principal đọc dữ liệu S3 theo mẫu khác thường. Dịch vụ tổng hợp tín hiệu và cung cấp finding để nhóm an ninh ưu tiên điều tra.

GuardDuty không thay thế:

- CloudTrail, VPC Flow Logs hoặc CloudWatch Logs như nguồn log phục vụ điều tra chi tiết.
- IAM, SCP, security group, network firewall hoặc cơ chế preventive control.
- Amazon Inspector, công cụ quét lỗ hổng và quy trình patch.
- Security Hub, nơi tổng hợp và quản lý posture/finding từ nhiều dịch vụ bảo mật.
- Quy trình incident response, người trực vận hành và quyết định nghiệp vụ.

GuardDuty là một lớp phát hiện trong kiến trúc phòng thủ nhiều lớp. Muốn giảm rủi ro, tổ chức cần kết hợp phát hiện, ngăn chặn, giám sát, điều tra và khôi phục.

## 2. Cách GuardDuty phân tích tín hiệu

GuardDuty tạo một detector trong từng account và Region. Detector là thực thể quản lý việc phát hiện tại Region đó. Khi bật GuardDuty, dịch vụ sử dụng các nguồn dữ liệu nền tảng được hỗ trợ để phân tích hoạt động. Một số protection plan có thể cần bật riêng để mở rộng phạm vi bảo vệ.

### Nguồn dữ liệu nền tảng

| Nguồn dữ liệu | Tín hiệu được phân tích | Ví dụ phát hiện |
|---|---|---|
| CloudTrail management events | Các thao tác quản trị AWS như tạo user, sửa policy, thay đổi cấu hình dịch vụ | API call đáng ngờ, credential bị sử dụng bất thường |
| VPC Flow Logs | Metadata luồng mạng vào/ra VPC | Kết nối tới IP độc hại, hoạt động dò quét hoặc liên lạc bất thường |
| DNS query logs | Truy vấn DNS từ workload được hỗ trợ | Truy vấn domain có liên quan tới malware hoặc command-and-control |
| Nguồn threat intelligence của AWS | IP, domain hoặc mẫu hạ tầng đã được nhận diện là đáng ngờ | Kết nối tới hạ tầng có liên quan đến mối đe dọa |
| Telemetry của protection plan | Dữ liệu bổ sung từ S3, EKS, runtime, malware hoặc dịch vụ được hỗ trợ | Truy cập dữ liệu bất thường, hành vi tiến trình hoặc malware |

GuardDuty quản lý việc phân tích các nguồn dữ liệu nền tảng; khách hàng không phải tự xây dựng pipeline để đưa CloudTrail management events, VPC Flow Logs và DNS logs vào một hệ thống phân tích riêng chỉ để bật GuardDuty. Tuy vậy, khách hàng vẫn cần cấu hình logging độc lập khi muốn lưu trữ, truy vấn và điều tra log gốc theo chính sách của tổ chức.

Một số loại telemetry và protection plan có thể phụ thuộc cấu hình, hệ điều hành, Region hoặc loại tài nguyên. Không giả định bật detector mặc định đồng nghĩa mọi tính năng mở rộng đã được bật.

### Quy trình khái quát

~~~mermaid
flowchart TD
    A[Hoạt động account và workload] --> B[CloudTrail, VPC Flow Logs, DNS và telemetry]
    B --> C[GuardDuty phân tích tín hiệu]
    C --> D{Nhận diện hành vi đáng ngờ?}
    D -->|Không| E[Tiếp tục giám sát]
    D -->|Có| F[Tạo finding]
    F --> G[EventBridge và Security Hub]
    G --> H[Đội an ninh phân loại và điều tra]
    H --> I[Khoanh vùng, khắc phục và lưu bằng chứng]
~~~

## 3. Các nhóm finding và ý nghĩa

Finding có loại (type) mô tả nhóm phát hiện. Tên type thường có cấu trúc phân cấp theo dịch vụ hoặc tài nguyên, ví dụ nhóm UnauthorizedAccess, Recon, Backdoor, CryptoCurrency hoặc Policy. Danh sách type và nội dung cụ thể thay đổi theo tính năng GuardDuty và được AWS cập nhật theo thời gian.

| Nhóm phát hiện | Ý nghĩa khái quát | Hành động điều tra ban đầu |
|---|---|---|
| UnauthorizedAccess | Có dấu hiệu truy cập trái phép hoặc credential bị lạm dụng | Kiểm tra principal, source IP, API event, MFA và thay đổi IAM |
| Recon | Có dấu hiệu dò quét hoặc thu thập thông tin | Xác định tài nguyên bị dò quét, nguồn kết nối và phạm vi mạng |
| Backdoor | Có dấu hiệu liên lạc với hạ tầng điều khiển hoặc cửa hậu | Cô lập workload phù hợp, lưu bằng chứng mạng và tiến trình |
| CryptoCurrency | Workload có thể đang thực hiện hoạt động đào tiền mã hóa | Kiểm tra CPU, process, image, user data và kết nối mạng |
| Trojan hoặc malware-related | Có tín hiệu liên quan đến malware hoặc hành vi độc hại | Bảo toàn snapshot/log, xác định nguồn tải và phạm vi lây lan |
| Persistence | Có dấu hiệu thiết lập cơ chế duy trì quyền truy cập | Rà soát IAM, startup scripts, scheduled tasks và thay đổi cấu hình |
| Policy | Cấu hình hoặc hành vi chính sách có thể làm tăng rủi ro | Kiểm tra bucket policy, IAM policy, security group hoặc cấu hình liên quan |
| Exfiltration | Có dấu hiệu dữ liệu bị truy xuất hoặc truyền ra ngoài bất thường | Xác định dữ liệu, principal, destination và thời điểm truy cập |
| Impact | Có dấu hiệu tác động đến tính sẵn sàng hoặc tính toàn vẹn | Đánh giá phạm vi dịch vụ, tài nguyên và ảnh hưởng nghiệp vụ |

Một finding có thể thuộc nhiều ngữ cảnh khác nhau tùy tài nguyên. Khi đọc finding, không chỉ dựa vào tên type; cần xem mô tả, resource, service action, evidence, thời điểm, account, Region và các trường bổ sung.

## 4. Severity và cách ưu tiên xử lý

GuardDuty gán mức độ nghiêm trọng cho finding để hỗ trợ ưu tiên. Mức severity là tín hiệu về mức rủi ro mà finding thể hiện; tổ chức cần kết hợp với bối cảnh tài sản, môi trường và tác động nghiệp vụ.

| Mức độ | Dải điểm tham khảo | Cách xử lý |
|---|---:|---|
| Low | 1.0 đến 3.9 | Rà soát theo lịch, xác định có phải hoạt động được chấp thuận hoặc cần theo dõi |
| Medium | 4.0 đến 6.9 | Điều tra trong thời gian ngắn, xác định phạm vi và quyết định hành động |
| High | 7.0 đến 8.9 | Ưu tiên phản ứng, kiểm tra khả năng xâm nhập và khoanh vùng nếu cần |

GuardDuty sử dụng ba mức severity chính là Low, Medium và High. Nếu hệ thống SIEM/SOAR nội bộ ánh xạ thêm nhãn Critical, đó là quy ước ưu tiên của tổ chức; không phải mức severity gốc thứ tư của GuardDuty.

Severity không phải xác suất chính xác rằng hệ thống đã bị xâm nhập. Ví dụ, một finding High liên quan tới account production có quyền quản trị có thể cần xử lý ngay; một finding cùng điểm trên sandbox cô lập có thể có tác động thấp hơn. Ngược lại, finding Medium liên quan tới dữ liệu được phân loại đặc biệt có thể cần ưu tiên cao theo chính sách nội bộ.

Nên xây dựng ma trận ưu tiên dựa trên:

- Severity của finding.
- Giá trị và mức độ nhạy cảm của tài nguyên.
- Môi trường production, staging hay sandbox.
- Quyền của principal hoặc role liên quan.
- Khả năng dữ liệu bị truy cập hoặc truyền ra ngoài.
- Dấu hiệu bổ sung từ CloudTrail, VPC Flow Logs, EDR và các dịch vụ bảo mật.
- Tình trạng hoạt động nghiệp vụ và phạm vi ảnh hưởng.

## 5. Đọc một finding đúng cách

Finding GuardDuty chứa nhiều trường có thể dùng để điều tra và tự động hóa. Các trường thường cần chú ý:

| Trường | Ý nghĩa |
|---|---|
| id | Định danh finding |
| type | Loại phát hiện |
| title và description | Tóm tắt và diễn giải hành vi |
| severity | Điểm mức độ nghiêm trọng |
| accountId | Account phát sinh finding |
| region | Region liên quan |
| createdAt / updatedAt | Thời điểm tạo và cập nhật |
| resource | Tài nguyên bị ảnh hưởng hoặc có liên quan |
| service | Thông tin dịch vụ phát hiện, action và evidence |
| schemaVersion | Phiên bản schema finding |
| partition | AWS partition liên quan |

Trường resource có thể chứa thông tin khác nhau theo loại finding. Với EC2, cần kiểm tra instance ID, image, instance type, network interface, security group, subnet, VPC và tag. Với IAM, cần kiểm tra access key, user/role, principal ID, session context và source IP. Với S3, xem bucket, object hoặc principal được mô tả trong finding. Với EKS, kiểm tra cluster, namespace, workload, pod và thông tin runtime nếu có.

### Quy trình triage

1. Xác nhận finding thuộc account và Region nào.
2. Xem type, severity, title, description và thời điểm.
3. Xác định principal hoặc tài nguyên liên quan.
4. Đối chiếu CloudTrail, VPC Flow Logs, DNS logs và log ứng dụng trong cùng khoảng thời gian.
5. Kiểm tra thay đổi gần đây: deployment, scaling, job định kỳ, pentest được phê duyệt hoặc thay đổi mạng.
6. Xác định hoạt động là hợp lệ, false positive, cần theo dõi hay có dấu hiệu xâm nhập.
7. Ghi lại kết luận, bằng chứng, người xử lý và quyết định tiếp theo.

Không archive finding chỉ vì chưa hiểu nguyên nhân. Nếu cần giảm nhiễu, tạo suppression rule có điều kiện hẹp, owner và thời hạn rà soát.

## 6. Bật GuardDuty trong một account và Region

GuardDuty có detector riêng theo Region. Một tổ chức triển khai nhiều Region cần bật và quản lý detector ở những Region nằm trong phạm vi bảo vệ. Việc bật ở một Region không tự động có nghĩa detector đã được bật ở tất cả Region khác.

Ví dụ tạo detector và bật GuardDuty bằng AWS CLI:

~~~bash
aws guardduty create-detector \
  --enable \
  --finding-publishing-frequency FIFTEEN_MINUTES
~~~

Lệnh trả về detector ID. Có thể kiểm tra detector:

~~~bash
aws guardduty list-detectors
~~~

Sau khi có detector ID, lấy finding theo tiêu chí:

~~~bash
aws guardduty list-findings \
  --detector-id "DETECTOR_ID" \
  --finding-criteria '{"Criterion":{"severity":{"Gte":7}}}'
~~~

Sau đó lấy chi tiết finding:

~~~bash
aws guardduty get-findings \
  --detector-id "DETECTOR_ID" \
  --finding-ids "FINDING_ID"
~~~

Các ví dụ dùng giá trị minh họa cho detector và finding ID. Lệnh phải chạy ở đúng account và Region; caller cần quyền GuardDuty tương ứng. Trong thực tế, hãy lưu detector ID theo Region và không hardcode ID vào pipeline dùng chung cho nhiều account.

## 7. Quản lý GuardDuty nhiều account với AWS Organizations

Trong môi trường nhiều account, bật và duy trì GuardDuty thủ công trên từng account dễ dẫn tới cấu hình không đồng nhất. GuardDuty hỗ trợ quản lý tập trung qua AWS Organizations.

Một account có thể được chỉ định làm **delegated administrator** cho GuardDuty. Account này quản lý các member account trong phạm vi tổ chức, bật GuardDuty và protection plan theo chính sách, theo dõi trạng thái và tập trung finding. Management account có thể đăng ký delegated administrator; nên dùng một account bảo mật chuyên trách thay vì dùng management account cho mọi hoạt động vận hành.

Mô hình tham khảo:

~~~mermaid
flowchart TD
    A[AWS Organizations Management Account] --> B[Đăng ký GuardDuty delegated administrator]
    B --> C[Security Tooling Account]
    C --> D[Member Account Development]
    C --> E[Member Account Staging]
    C --> F[Member Account Production]
    D --> G[GuardDuty detectors theo Region]
    E --> G
    F --> G
    G --> H[Finding tập trung]
    H --> I[Security Hub / EventBridge / SIEM]
~~~

Các bước quản trị:

1. Chọn account bảo mật làm delegated administrator.
2. Đăng ký delegated administrator cho GuardDuty từ management account.
3. Bật tự động thêm member account hoặc mời account theo mô hình tổ chức.
4. Chọn Region và protection plan cần bật.
5. Cấu hình auto-enable cho account hiện có và account mới theo yêu cầu.
6. Xác nhận từng member account có detector hoạt động và trạng thái đồng bộ.
7. Kiểm tra finding tập trung và phân quyền người vận hành.

GuardDuty là dịch vụ theo Region. Delegated administrator cần có cấu hình phù hợp ở từng Region được sử dụng. Account mới gia nhập organization hoặc account chuyển OU cần được kiểm tra theo chính sách onboarding và offboarding.

## 8. Protection plans mở rộng phạm vi phát hiện

Ngoài nguồn dữ liệu nền tảng, GuardDuty cung cấp các protection plan để mở rộng giám sát. Tên gọi, phạm vi và điều kiện hỗ trợ có thể thay đổi; cần kiểm tra cấu hình thực tế trong Region.

### 8.1. S3 Protection

S3 Protection phân tích các sự kiện dữ liệu S3 được hỗ trợ để nhận diện hành vi truy cập bất thường hoặc có dấu hiệu độc hại. Ví dụ, một principal truy cập object theo cách khác thường hoặc có dấu hiệu thu thập dữ liệu hàng loạt.

S3 Protection tập trung vào phát hiện hành vi. Nó không thay thế bucket policy, Block Public Access, IAM, access point policy, encryption hoặc quy trình phân loại dữ liệu. Muốn ngăn truy cập trái phép, vẫn cần preventive controls và giám sát quyền truy cập.

### 8.2. EKS Protection và Runtime Monitoring

EKS Protection có thể phân tích Kubernetes audit logs để phát hiện hành vi bất thường ở control plane, chẳng hạn API request đáng ngờ, thao tác quyền hoặc hành vi liên quan tới cluster.

Runtime Monitoring mở rộng giám sát hành vi runtime của workload được hỗ trợ, bao gồm tiến trình, network và hoạt động ở mức hệ điều hành/container. Tùy môi trường, GuardDuty có thể yêu cầu triển khai hoặc quản lý security agent trên node. Cần kiểm tra điều kiện OS, kiến trúc, phiên bản và cách quản lý agent trong cluster.

Kubernetes audit finding và runtime finding phản ánh hai lớp khác nhau: một bên quan sát API/control plane, bên còn lại quan sát hành vi trong workload. Kết hợp chúng giúp điều tra cả thao tác quản trị cluster lẫn hoạt động bên trong node/container.

### 8.3. Malware Protection for EC2

Malware Protection for EC2 hỗ trợ quét malware trên volume EBS của EC2 theo các điều kiện và trigger được AWS hỗ trợ. Quá trình quét có thể tạo snapshot phục vụ phân tích. Cần hiểu cơ chế snapshot, quyền service-linked role, mã hóa volume, key policy, chi phí snapshot và yêu cầu bảo vệ dữ liệu.

Finding liên quan malware cần được xử lý như một sự kiện bảo mật: xác minh workload, bảo toàn bằng chứng, cô lập khi phù hợp và đánh giá liệu cần rebuild từ image sạch hay không. Không xóa snapshot hoặc volume trước khi nhóm ứng phó hoàn tất điều tra.

### 8.4. Malware Protection for S3

Malware Protection for S3 quét object được tải lên bucket được bảo vệ theo phạm vi cấu hình. Tổ chức có thể dùng kết quả quét để tích hợp với workflow kiểm duyệt object, cách ly dữ liệu hoặc thông báo. Cần kiểm tra bucket, prefix, role, quyền truy cập object, KMS key và cách xử lý file chưa có kết quả quét.

Không nên cho ứng dụng downstream xử lý file không tin cậy trước khi quy trình quét và quyết định chấp nhận hoàn tất. Việc quét malware không thay thế kiểm tra định dạng, kiểm soát nội dung và validation nghiệp vụ.

### 8.5. RDS Protection và các nguồn dữ liệu được hỗ trợ

GuardDuty có thể cung cấp phát hiện liên quan tới hoạt động đăng nhập hoặc hành vi bất thường trên một số dịch vụ cơ sở dữ liệu được hỗ trợ. Khả năng này phụ thuộc loại database, Region, cấu hình và protection plan hiện hành. Không giả định mọi engine hoặc mọi account đều tự động được bảo vệ.

### 8.6. Lambda Protection

Lambda Protection phân tích các tín hiệu liên quan tới network activity từ Lambda execution environment được hỗ trợ để nhận diện hành vi đáng ngờ, chẳng hạn function kết nối tới domain hoặc địa chỉ IP liên quan đến mối đe dọa. Cần đánh giá ảnh hưởng chi phí và phạm vi function khi bật protection plan.

## 9. Phát hiện hành vi bất thường bằng machine learning

Không phải mọi cuộc tấn công đều dùng IP hoặc domain đã có trong threat intelligence. Kẻ tấn công có thể sử dụng credential hợp lệ, truy cập từ hạ tầng bình thường hoặc thay đổi hành vi theo cách không trùng với chữ ký đã biết. Vì vậy, GuardDuty kết hợp phân tích hành vi và machine learning để tìm các mẫu khác với hoạt động thường thấy.

Ví dụ về tín hiệu bất thường:

- IAM principal gọi API mà trước đó chưa từng sử dụng hoặc dùng trong bối cảnh khác thường.
- Credential được sử dụng từ vị trí, ASN, thiết bị hoặc source IP có đặc điểm khác với lịch sử.
- Một instance bắt đầu gửi lượng dữ liệu mạng hoặc kết nối tới đích khác thường.
- Một workload truy cập tài nguyên nhạy cảm theo mô hình chưa từng xuất hiện.
- Một role thực hiện chuỗi thao tác có thể liên quan đến privilege escalation hoặc persistence.

Phát hiện dựa trên hành vi có thể giúp nhận diện kỹ thuật tấn công chưa có indicator cụ thể. Tuy nhiên, baseline không phải quy tắc bất biến. Một deployment mới, autoscaling, batch job, backup hoặc hoạt động kiểm thử bảo mật có thể làm thay đổi hành vi hợp lệ.

### Baseline và ngữ cảnh

GuardDuty phân tích dữ liệu theo cách triển khai của dịch vụ; khách hàng không cần tự xây dựng baseline cho từng principal để bật tính năng phát hiện. Dù vậy, đội an ninh cần bổ sung ngữ cảnh nội bộ:

- Owner và mục đích của workload.
- Lịch deploy, backup, batch và maintenance.
- Source IP, VPN, NAT gateway và hệ thống truy cập quản trị hợp lệ.
- Vai trò IAM, quyền dự kiến và phạm vi dữ liệu.
- Tài nguyên production và mức độ nhạy cảm.
- Thời điểm có pentest hoặc hoạt động red team được phê duyệt.

Nếu finding trùng với một hoạt động hợp lệ, lưu lại bằng chứng và xác định có cần suppression rule hay không. Không tạo allowlist quá rộng vì có thể che khuất hành vi xâm nhập thật.

## 10. Tích hợp GuardDuty với EventBridge

GuardDuty phát finding event lên Amazon EventBridge. EventBridge cho phép định tuyến finding tới SNS, Lambda, SQS, Step Functions, Systems Manager Automation, Security Hub hoặc hệ thống SIEM/SOAR.

Một event finding thường có:

- source là aws.guardduty.
- detail-type là GuardDuty Finding.
- detail chứa finding ID, type, severity, account, Region, resource và các trường khác.

Ví dụ event pattern chỉ chọn finding có severity từ 7 trở lên:

~~~json
{
  "source": ["aws.guardduty"],
  "detail-type": ["GuardDuty Finding"],
  "detail": {
    "severity": [{"numeric": [">=", 7]}]
  }
}
~~~

Pattern này chỉ minh họa cách lọc theo severity. Khi triển khai, cần xác nhận event schema thực tế, loại finding, trường resource và điều kiện theo từng workflow.

Một rule có thể gửi finding High tới SQS để xử lý tuần tự, gửi thông báo cho nhóm trực hoặc gọi Lambda để enrich bằng tag và thông tin owner. Đối với thao tác cô lập tài nguyên, nên có kiểm tra điều kiện và bước phê duyệt phù hợp với mức rủi ro.

### Thiết kế workflow an toàn

~~~mermaid
flowchart LR
    A[GuardDuty Finding] --> B[EventBridge Rule]
    B --> C[Enrichment Lambda]
    C --> D[SQS Incident Queue]
    D --> E[SOAR / Security Team]
    E --> F{Cần hành động tự động?}
    F -->|Có, đã được phê duyệt| G[SSM Automation / Lambda]
    F -->|Cần xác minh| H[Analyst điều tra]
    G --> I[Kiểm tra kết quả và lưu audit]
    H --> I
~~~

EventBridge delivery và target invocation có thể được retry. Workflow cần idempotency để một finding không tạo nhiều hành động phá vỡ dịch vụ. Lưu finding ID hoặc khóa tương quan trong hệ thống incident để nhận diện sự kiện trùng lặp và cập nhật case hiện có.

## 11. Suppression rule và quản lý false positive

Không phải finding nào cũng cần mở incident. Một số finding có thể xuất hiện lặp lại do hoạt động được phê duyệt hoặc một môi trường thử nghiệm. GuardDuty hỗ trợ filter và suppression rule để giảm nhiễu.

Một suppression rule nên có:

- Điều kiện rõ ràng dựa trên type, resource, severity hoặc thuộc tính cụ thể.
- Chủ sở hữu và lý do nghiệp vụ.
- Phạm vi account/Region/tài nguyên hẹp.
- Thời hạn hoặc lịch rà soát.
- Cách kiểm tra rằng rule không che giấu finding mới có ý nghĩa.

Có thể archive một finding cụ thể sau khi đã điều tra, hoặc dùng filter rule để tự động archive những finding khớp điều kiện. Archive không xóa bằng chứng gốc khỏi mọi hệ thống liên quan và không có nghĩa vấn đề đã được khắc phục.

Không nên suppress toàn bộ finding Low hoặc tất cả finding từ một subnet chỉ vì có nhiều cảnh báo. Một attacker có thể sử dụng chính subnet hoặc workload hợp lệ làm điểm xuất phát. Tốt hơn là xác định hoạt động cụ thể, principal, process hoặc đích kết nối được chấp thuận.

## 12. Ứng phó với finding: từ triage tới khôi phục

Quy trình ứng phó cần được chuẩn bị trước khi có incident. Khi finding High hoặc Critical xuất hiện, đội trực nên thực hiện theo playbook đã được phê duyệt.

### Bước 1: Nhận và xác nhận

Ghi nhận finding ID, type, severity, account, Region, resource, thời điểm và nguồn phát hiện. Xác minh finding chưa được xử lý trong incident khác. Đánh giá xem hoạt động có trùng với deployment, pentest hoặc thay đổi được phê duyệt không.

### Bước 2: Mở rộng điều tra

Đối chiếu CloudTrail management/data events, VPC Flow Logs, DNS logs, application logs, EDR, IAM Access Analyzer, Security Hub và các finding liên quan. Xác định principal, source IP, session, resource và khoảng thời gian. Tìm dấu hiệu persistence, privilege escalation, lateral movement hoặc data exfiltration.

### Bước 3: Bảo toàn bằng chứng

Lưu finding JSON, CloudTrail event, log liên quan, cấu hình IAM và network, metadata tài nguyên và thời điểm thu thập. Với EC2, có thể tạo snapshot EBS theo quy trình điều tra trước khi thay đổi hoặc terminate instance. Bảo vệ snapshot và log bằng IAM, KMS, retention và quyền truy cập hạn chế.

### Bước 4: Khoanh vùng

Hành động phụ thuộc tài nguyên và mức độ chắc chắn:

- Với IAM credential: disable access key, revoke session hoặc cập nhật policy theo quy trình khẩn cấp; kiểm tra role trust và user access.
- Với EC2: áp dụng security group cô lập hoặc chuyển sang subnet/quarantine theo kiến trúc; giữ đường quản trị điều tra cần thiết.
- Với S3: chặn principal hoặc đường truy cập đáng ngờ, rà soát bucket policy, access point và object ACL nếu còn dùng.
- Với EKS/container: cô lập workload hoặc node theo playbook, kiểm tra service account, RBAC và image.
- Với Lambda: xem xét vô hiệu hóa trigger hoặc giới hạn quyền execution role nếu function có dấu hiệu bị lạm dụng.

Không áp dụng một hành động tự động cho mọi finding. Cô lập nhầm database, load balancer hoặc node điều khiển có thể gây gián đoạn lớn hơn chính sự cố.

### Bước 5: Loại bỏ nguyên nhân và khôi phục

Xóa persistence, thay credential, sửa IAM/network policy, cập nhật image hoặc rebuild workload từ nguồn tin cậy. Nếu không thể chứng minh một máy đã sạch, ưu tiên tái tạo từ image hoặc artifact đã được xác minh thay vì chỉ xóa file đáng ngờ.

### Bước 6: Xác nhận và đóng incident

Kiểm tra GuardDuty finding mới, CloudTrail, network telemetry, health check và hoạt động nghiệp vụ. Ghi lại phạm vi ảnh hưởng, nguyên nhân gốc, hành động đã thực hiện, bằng chứng, người phê duyệt và bài học cải tiến. Không đóng incident chỉ vì finding đã được archive.

## 13. Ví dụ: finding về credential IAM bị lạm dụng

Giả sử GuardDuty tạo finding liên quan đến một IAM access key được sử dụng từ địa chỉ IP lạ để gọi API quản trị. Đội an ninh cần xác định đây có phải automation hợp lệ hay không.

Quy trình tham khảo:

1. Lấy finding và xác định access key ID, principal, source IP, Region, API action và thời điểm.
2. Tìm CloudTrail events theo access key ID và thời gian xung quanh finding.
3. Kiểm tra user/role owner, lần sử dụng hợp lệ gần nhất và hệ thống CI/CD có dùng key này không.
4. Tìm các thay đổi sau đó như CreateAccessKey, AttachUserPolicy, PutRolePolicy, CreateLoginProfile hoặc thay đổi trust policy.
5. Kiểm tra resource mới được tạo, dữ liệu bị truy cập và các account/Region liên quan.
6. Nếu nghi ngờ credential bị lộ, vô hiệu hóa key và thu hồi session phù hợp; tạo credential mới qua quy trình bảo mật.
7. Rà soát workload dùng key, chuyển sang IAM role hoặc federation để giảm phụ thuộc vào long-lived access key.
8. Theo dõi finding tiếp theo và xác minh không còn hoạt động bất thường.

Sơ đồ phản ứng:

~~~mermaid
flowchart TD
    A[Finding IAM credential bất thường] --> B[Đối chiếu CloudTrail]
    B --> C{Hoạt động đã được phê duyệt?}
    C -->|Có| D[Ghi nhận bằng chứng và đánh giá suppression]
    C -->|Không / chưa rõ| E[Đánh giá mức độ compromise]
    E --> F[Disable key hoặc revoke session]
    F --> G[Kiểm tra thay đổi IAM và resource]
    G --> H[Khắc phục, thay credential, loại bỏ persistence]
    H --> I[Theo dõi và xác nhận sạch]
    D --> J[Đóng hoặc theo dõi incident]
    I --> J
~~~

Việc vô hiệu hóa credential có thể ảnh hưởng workload đang chạy. Nếu chưa đủ căn cứ, cần phối hợp owner để thay credential an toàn; nếu đang có hành vi tấn công tích cực, ưu tiên containment theo playbook khẩn cấp.

## 14. Tích hợp Security Hub, Detective và các dịch vụ khác

GuardDuty là một nguồn phát hiện. Để quản lý nhiều loại cảnh báo, tổ chức có thể tích hợp:

| Dịch vụ | Vai trò khi phối hợp với GuardDuty |
|---|---|
| AWS Security Hub | Tập trung security findings, chuẩn hóa và ưu tiên theo posture |
| Amazon Detective | Khám phá mối quan hệ giữa finding, principal, IP, instance và hoạt động để hỗ trợ điều tra |
| Amazon EventBridge | Định tuyến finding tới workflow, queue, Lambda hoặc hệ thống bên ngoài |
| Amazon SNS | Gửi thông báo tới nhóm trực hoặc hệ thống thông báo |
| AWS Systems Manager Automation | Chạy runbook ứng phó theo điều kiện và quyền đã phê duyệt |
| AWS CloudTrail | Tra cứu API activity và thay đổi quản trị để xác định hành động thực tế |
| Amazon CloudWatch | Theo dõi trạng thái workflow, metric và log của automation |
| AWS Organizations | Quản lý detector và protection plan trên nhiều account |
| SIEM/SOAR | Tương quan finding với log và incident từ hệ thống khác |

Security Hub giúp tổng hợp posture và findings; Detective hỗ trợ phân tích mối quan hệ; EventBridge đưa finding tới hệ thống phản ứng. Không nên tạo nhiều pipeline gửi cùng một finding tới nhiều hệ thống mà không có định danh tương quan, vì có thể sinh incident trùng lặp và hành động xung đột.

## 15. Bảo mật quyền quản trị GuardDuty

GuardDuty có service-linked role để thực hiện các tác vụ dịch vụ cần thiết. Người quản trị cần quyền bật/tắt detector, quản lý member account, protection plan, finding filter và export/integration theo phạm vi được giao.

Một mô hình phân quyền tham khảo:

| Vai trò | Quyền phù hợp |
|---|---|
| Security administrator | Quản lý detector, delegated admin, protection plan và cấu hình toàn tổ chức |
| Incident responder | Đọc finding, xem resource và chạy hành động phản ứng đã được phê duyệt |
| Workload owner | Xem finding liên quan tới account/application của mình và cung cấp ngữ cảnh |
| Auditor | Đọc finding, policy, cấu hình và bằng chứng; không có quyền tắt dịch vụ |
| Automation role | Chỉ chạy những hành động cụ thể như cô lập instance hoặc disable key theo playbook |

Không cấp quyền tắt GuardDuty hoặc sửa suppression rule rộng cho mọi developer. Những thao tác này có thể làm mất khả năng phát hiện hoặc che giấu hoạt động bất thường. Dùng CloudTrail để theo dõi thay đổi cấu hình detector, member account, protection plan và filter.

## 16. Chi phí và hiệu năng

GuardDuty tính phí theo nguồn dữ liệu và protection plan được bật. Cách tính có thể dựa trên lượng CloudTrail events, lượng VPC Flow Logs/DNS data phân tích, số lượng workload hoặc object được bảo vệ và các yếu tố riêng của từng tính năng. Mức giá khác nhau theo Region và có thể thay đổi.

Để kiểm soát chi phí:

1. Bật protection plan theo yêu cầu rủi ro và phạm vi tài nguyên.
2. Theo dõi usage và estimated cost theo account/Region.
3. Phân loại workload, account và Region để biết nơi phát sinh chi phí.
4. Đánh giá S3, EKS, Runtime, Malware và Lambda protection theo nhu cầu thực tế.
5. Tích hợp billing alerts và AWS Cost Explorer.
6. Đưa GuardDuty vào baseline onboarding account mới để tránh bật muộn hoặc cấu hình thiếu.
7. Không tắt detector chỉ để giảm chi phí khi chưa đánh giá rủi ro và được phê duyệt.

GuardDuty là dịch vụ được quản lý, nhưng vẫn cần theo dõi tình trạng detector, coverage, member account, protection plan và workflow phản ứng. Một detector bật nhưng không bao phủ account/Region cần bảo vệ vẫn tạo ra khoảng trống an ninh.

## 17. Kiểm thử và xác nhận GuardDuty hoạt động

Không nên tạo hành vi tấn công thật trong production để thử GuardDuty. AWS cung cấp cách tạo sample findings trong GuardDuty để kiểm tra quy trình hiển thị, EventBridge, Security Hub và hệ thống incident.

Ví dụ tạo sample finding:

~~~bash
aws guardduty create-sample-findings \
  --detector-id "DETECTOR_ID"
~~~

Sample finding dùng để kiểm tra pipeline xử lý và thường được đánh dấu là mẫu. Nó không xác nhận mọi nguồn telemetry, protection plan hoặc detection model đang hoạt động đúng. Cần kiểm tra riêng trạng thái detector, cấu hình feature, member account và event delivery.

Checklist kiểm thử:

- Detector đã Enabled ở từng Region trong phạm vi.
- Member account được quản lý và trạng thái đồng bộ đúng.
- Protection plan cần thiết đã bật.
- Sample finding xuất hiện trong console/API.
- EventBridge rule nhận được event đúng pattern.
- Target xử lý thành công và không tạo incident trùng lặp.
- Quyền của responder/automation hoạt động đúng.
- Suppression rule không che mất sample hoặc finding quan trọng.
- Log và bằng chứng được lưu ở nơi có quyền truy cập hạn chế.
- Có quy trình xử lý khi EventBridge target lỗi hoặc workflow không phản hồi.

## 18. Lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy finding ở một Region | Detector chưa bật hoặc đang xem nhầm Region | Kiểm tra list-detectors và account/Region |
| Account mới không có detector | Auto-enable hoặc delegated admin chưa cấu hình đúng | Kiểm tra AWS Organizations integration và member status |
| Không có finding từ S3 | S3 Protection chưa bật hoặc bucket không thuộc phạm vi | Kiểm tra feature status, bucket và Region |
| Không có runtime finding từ EKS/EC2 | Runtime Monitoring chưa bật hoặc agent/OS không đáp ứng điều kiện | Kiểm tra coverage và trạng thái agent |
| EventBridge không nhận finding | Event pattern sai, rule ở sai Region hoặc target policy thiếu quyền | Kiểm tra event history, rule, target và IAM |
| Finding bị archive quá sớm | Suppression/filter rule quá rộng | Rà soát criteria, owner và lịch sử rule |
| Quá nhiều cảnh báo | Thiếu ngữ cảnh, rule không phù hợp hoặc workflow không deduplicate | Enrich finding, nhóm theo resource và incident key |
| Không thể đọc finding qua CLI | Thiếu IAM permission hoặc detector ID sai | Kiểm tra role, policy, Region và detector |
| Automation không cô lập được EC2 | Role thiếu quyền, resource đã đổi trạng thái hoặc action không idempotent | Xem execution log, kiểm tra precondition và quyền |
| Finding không phản ánh toàn bộ incident | GuardDuty chỉ phát hiện một phần tín hiệu và có độ trễ | Tương quan thêm CloudTrail, logs, EDR và dữ liệu nghiệp vụ |

## 19. Checklist vận hành GuardDuty

- [ ] GuardDuty được bật ở tất cả account và Region cần bảo vệ.
- [ ] Delegated administrator và AWS Organizations integration được cấu hình.
- [ ] Auto-enable cho account mới đã được kiểm tra.
- [ ] Protection plan phù hợp với EC2, S3, EKS, RDS, Lambda và workload cần bảo vệ đã được đánh giá.
- [ ] Detector và feature coverage được theo dõi định kỳ.
- [ ] Finding được định tuyến qua EventBridge tới nhóm trực hoặc hệ thống SIEM/SOAR.
- [ ] Workflow có deduplication và idempotency.
- [ ] Severity được kết hợp với criticality và owner của tài nguyên.
- [ ] Suppression rule có điều kiện hẹp, lý do và ngày rà soát.
- [ ] Có playbook cho IAM credential, EC2, S3, EKS và malware.
- [ ] Log và snapshot bằng chứng được bảo vệ bằng IAM/KMS/retention.
- [ ] Automation có precondition, phê duyệt phù hợp và khả năng rollback.
- [ ] CloudTrail ghi nhận thay đổi cấu hình GuardDuty.
- [ ] Chi phí theo Region/account được theo dõi.
- [ ] Sample finding được dùng để kiểm thử pipeline định kỳ.

## 20. Ghi nhớ

Amazon GuardDuty phân tích tín hiệu từ hoạt động account, mạng, DNS và các protection plan để phát hiện dấu hiệu xâm nhập hoặc hành vi bất thường. Detector được quản lý theo Region; AWS Organizations và delegated administrator giúp quản lý nhiều account. Finding mô tả loại phát hiện, severity, resource và bằng chứng để đội an ninh triage.

Phát hiện tự động cần được kết hợp với ngữ cảnh nội bộ và nguồn log gốc. EventBridge giúp định tuyến finding tới Security Hub, Detective, SQS, Lambda, Systems Manager Automation hoặc SIEM/SOAR. Quy trình phản ứng phải xác minh, bảo toàn bằng chứng, khoanh vùng, loại bỏ nguyên nhân và xác nhận hệ thống sạch.

GuardDuty tạo ra tín hiệu phát hiện có giá trị; chất lượng bảo vệ phụ thuộc vào coverage, quyền quản trị, cách ưu tiên finding và khả năng phản ứng của tổ chức. Hãy duy trì detector ở mọi account/Region cần thiết, kiểm tra protection plan, giảm nhiễu có kiểm soát và diễn tập incident response để phát hiện sớm, xử lý đúng và phục hồi an toàn.

## Tài liệu tham khảo

- [What is Amazon GuardDuty?](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html)
- [How Amazon GuardDuty Uses Its Data Sources](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_data-sources.html)
- [Understanding GuardDuty Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings.html)
- [Finding Severity Levels](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings-severity.html)
- [Managing GuardDuty Accounts with AWS Organizations](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_organizations.html)
- [Managing GuardDuty Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings-manage.html)
- [Filtering and Suppressing Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_filter-findings.html)
- [GuardDuty Findings and Amazon EventBridge](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings_eventbridge.html)
- [GuardDuty S3 Protection](https://docs.aws.amazon.com/guardduty/latest/ug/s3-protection.html)
- [GuardDuty EKS Protection](https://docs.aws.amazon.com/guardduty/latest/ug/kubernetes-protection.html)
- [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html)
- [GuardDuty Malware Protection for EC2](https://docs.aws.amazon.com/guardduty/latest/ug/malware-protection.html)
- [GuardDuty Malware Protection for S3](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty-malware-protection-s3.html)
- [Creating Sample Findings](https://docs.aws.amazon.com/guardduty/latest/ug/sample_findings.html)
- [GuardDuty Pricing](https://aws.amazon.com/guardduty/pricing/)
