# Thu thập bằng chứng kiểm toán và lưu giữ nhật ký

Một hệ thống Google Cloud có thể vận hành ổn định trong nhiều tháng nhưng vẫn khó đáp ứng kiểm toán nếu tổ chức không chứng minh được ai đã thay đổi tài nguyên, thao tác diễn ra khi nào, dịch vụ nào bị tác động và bằng chứng được bảo vệ ra sao. Thu thập bằng chứng kiểm toán vì thế phải được thiết kế ngay trong kiến trúc vận hành, từ việc bật đúng loại audit log đến định tuyến, phân quyền, lưu giữ và truy xuất khi cần điều tra.

Trong Google Cloud, Cloud Audit Logs ghi lại hoạt động quản trị và truy cập dữ liệu của các dịch vụ được hỗ trợ. Cloud Logging tiếp nhận, truy vấn, định tuyến và lưu giữ các log entry. Khi kết hợp hai thành phần này với IAM, Log Router, log bucket, BigQuery, Cloud Storage và quy trình quản lý bằng chứng, tổ chức có thể xây dựng một chuỗi kiểm soát có thể kiểm tra lại.

Bài học tập trung vào phạm vi bảo mật và tuân thủ của Google Cloud. Sau khi hoàn thành, bạn có thể:

- Phân biệt các loại Cloud Audit Logs và xác định loại nào cần bật cho từng dịch vụ.
- Cấu hình Data Access audit logs và kiểm tra hoạt động được ghi nhận.
- Thu thập log tập trung ở cấp project, folder hoặc organization.
- Thiết kế log sink, log bucket và đích lưu trữ theo thời hạn lưu giữ.
- Phân quyền người xem, người quản trị logging và người kiểm soát bằng chứng.
- Truy vấn, xuất và bảo toàn bằng chứng phục vụ kiểm toán hoặc điều tra sự cố.

## 1. Vì sao cần bằng chứng kiểm toán?

Bằng chứng kiểm toán là dữ liệu có thể kiểm tra lại để xác nhận một hoạt động đã xảy ra, một kiểm soát đã được thực hiện hoặc một quyết định vận hành đã được phê duyệt. Trong môi trường cloud, bằng chứng thường đến từ audit logs, cấu hình IAM, lịch sử thay đổi, kết quả kiểm tra bảo mật và hồ sơ xử lý sự cố.

Ví dụ, khi một VM production bị thay đổi firewall rule, nhóm bảo mật cần trả lời được:

- Ai hoặc service account nào đã gửi yêu cầu thay đổi?
- Thao tác diễn ra lúc nào và từ dịch vụ nào?
- Tài nguyên nào bị tác động?
- Yêu cầu thành công hay bị từ chối?
- Quyền truy cập được cấp từ IAM policy nào?
- Log có được lưu giữ trong thời gian quy định và có thể truy xuất nguyên vẹn không?

Nếu chỉ dựa vào ghi chú của nhân viên hoặc ảnh chụp màn hình, tổ chức khó xác minh nguồn gốc và tính đầy đủ của thông tin. Audit log cung cấp sự kiện do dịch vụ Google Cloud tạo ra, còn quy trình quản lý bằng chứng bổ sung phạm vi thu thập, quyền truy cập, thời hạn lưu giữ và hồ sơ bàn giao.

Một quy trình tốt cần bảo đảm bốn thuộc tính:

1. **Đầy đủ:** các loại sự kiện cần thiết được ghi nhận ở đúng phạm vi.
2. **Có thể truy nguyên:** log thể hiện principal, thời gian, dịch vụ, tài nguyên và kết quả thao tác khi các trường này được dịch vụ cung cấp.
3. **Được bảo vệ:** người dùng thông thường không thể âm thầm sửa hoặc xóa bằng chứng.
4. **Có thể truy xuất:** nhóm kiểm toán có thể tìm, xuất và diễn giải log trong thời gian yêu cầu.

Audit log không tự chứng minh rằng toàn bộ kiểm soát của tổ chức đã hoạt động đúng. Nó là một nguồn bằng chứng quan trọng, cần được kết hợp với cấu hình chính sách, kết quả giám sát, ticket thay đổi và quy trình phê duyệt.

## 2. Cloud Audit Logs ghi lại những gì?

Cloud Audit Logs ghi lại các hoạt động liên quan đến việc sử dụng tài nguyên Google Cloud. Mỗi audit log entry thường chứa thông tin về dịch vụ, phương thức API, tài nguyên, danh tính gọi API, thời gian và trạng thái kết quả. Các trường cụ thể phụ thuộc vào dịch vụ và loại sự kiện.

Google Cloud phân loại audit logs thành bốn nhóm chính:

| Loại log | Nội dung | Trạng thái mặc định |
|---|---|---|
| Admin Activity | Thao tác quản trị hoặc thay đổi cấu hình tài nguyên | Luôn được ghi; không thể tắt |
| Data Access | Đọc hoặc ghi dữ liệu người dùng và thao tác đọc metadata được kiểm soát | Phần lớn bị tắt mặc định; BigQuery có quy tắc riêng và ghi Data Access mặc định |
| System Event | Thay đổi do hệ thống Google Cloud thực hiện thay mặt người dùng | Luôn được ghi; không thể tắt |
| Policy Denied | Yêu cầu bị từ chối do chính sách bảo mật, ví dụ IAM hoặc VPC Service Controls | Được tạo khi dịch vụ hỗ trợ và chính sách từ chối yêu cầu |

### 2.1. Admin Activity

Admin Activity audit logs ghi lại các thao tác thay đổi cấu hình hoặc quản trị tài nguyên, ví dụ:

- Tạo, cập nhật hoặc xóa Compute Engine instance.
- Thay đổi firewall rule hoặc cấu hình mạng.
- Thay đổi IAM policy.
- Tạo hoặc cập nhật Cloud Storage bucket.
- Thay đổi cấu hình dịch vụ hoặc tài nguyên được hỗ trợ.

Loại log này luôn được bật và không thể tắt. Vì vậy, đây là nền tảng quan trọng để kiểm tra các thay đổi đối với hạ tầng.

### 2.2. Data Access

Data Access audit logs ghi lại hoạt động truy cập dữ liệu hoặc đọc thông tin được bảo vệ bởi dịch vụ. Ví dụ:

- Một principal đọc object trong Cloud Storage.
- Một người dùng truy vấn dữ liệu trong dịch vụ hỗ trợ audit.
- Một ứng dụng đọc secret hoặc metadata nhạy cảm.
- Một principal đọc cấu hình hoặc dữ liệu của tài nguyên được dịch vụ ghi audit.

Data Access thường gồm ba log type:

- DATA_READ: đọc dữ liệu.
- DATA_WRITE: ghi hoặc thay đổi dữ liệu.
- ADMIN_READ: đọc metadata hoặc cấu hình quản trị.

Phần lớn Data Access logs bị tắt mặc định vì có thể tạo lượng log lớn. BigQuery là ngoại lệ quan trọng: dịch vụ ghi Data Access audit logs mặc định. Khi tổ chức cần chứng minh ai đã đọc dữ liệu, phải kiểm tra cấu hình audit cho từng dịch vụ và bật loại log phù hợp.

### 2.3. System Event

System Event audit logs ghi lại hành động do hệ thống Google Cloud thực hiện để quản lý tài nguyên, ví dụ thao tác bảo trì hoặc hành động tự động của dịch vụ. Loại log này luôn được bật và không thể tắt.

Khi điều tra, hãy phân biệt hành động do người dùng hoặc workload yêu cầu với hành động do hệ thống thực hiện. Hai loại sự kiện có thể xuất hiện gần nhau nhưng mang ý nghĩa khác nhau.

### 2.4. Policy Denied

Policy Denied audit logs giúp nhận diện các yêu cầu bị chặn bởi chính sách bảo mật. Ví dụ, một request bị VPC Service Controls từ chối hoặc một thao tác không đáp ứng chính sách truy cập.

Loại log này hữu ích để phát hiện cấu hình sai, hành vi truy cập bất thường và các lần vi phạm ranh giới bảo mật. Khả năng ghi nhận và trường dữ liệu cụ thể phụ thuộc dịch vụ hoặc cơ chế chính sách tạo ra sự kiện.

### 2.5. Access Transparency

Với các dịch vụ và tổ chức đủ điều kiện, Access Transparency logs có thể cung cấp thông tin về một số lần nhân viên Google truy cập nội dung khách hàng trong quá trình hỗ trợ hoặc vận hành. Đây là nguồn bằng chứng bổ sung khi tổ chức cần kiểm soát việc truy cập dữ liệu từ phía nhà cung cấp. Khả năng sử dụng phụ thuộc dịch vụ, khu vực và điều kiện sản phẩm; hãy kiểm tra phạm vi hỗ trợ trước khi đưa vào yêu cầu tuân thủ.

## 3. Cấu trúc một audit log entry

Audit log entry được ghi vào Cloud Logging. Một số trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| logName | Tên log, ví dụ activity hoặc data_access |
| resource | Loại tài nguyên và các nhãn định danh tài nguyên |
| timestamp | Thời điểm sự kiện xảy ra |
| receiveTimestamp | Thời điểm Cloud Logging nhận log entry |
| severity | Mức độ nghiêm trọng nếu entry có trường này |
| insertId | Định danh entry phục vụ xử lý log |
| protoPayload.serviceName | Dịch vụ phát sinh audit event |
| protoPayload.methodName | Phương thức hoặc hành động API |
| protoPayload.resourceName | Tên tài nguyên liên quan |
| protoPayload.authenticationInfo | Thông tin danh tính xác thực |
| protoPayload.authorizationInfo | Thông tin kiểm tra quyền |
| protoPayload.requestMetadata | Metadata về request, có thể gồm thông tin nguồn gọi |
| protoPayload.status | Trạng thái hoặc lỗi của thao tác |

Ví dụ một audit entry có thể cho biết service account của ứng dụng triển khai đã gọi API tạo VM trong project production. Nhóm kiểm toán có thể dùng principal, method, resource và timestamp để đối chiếu với ticket phát hành.

Không phải mọi dịch vụ đều cung cấp đầy đủ mọi trường. Một số thông tin request có thể bị lược bỏ hoặc làm mờ vì lý do bảo mật và quyền riêng tư. Vì vậy, khi thiết kế bằng chứng, hãy xác định những trường mà dịch vụ thực tế ghi ra thay vì giả định mọi log đều có cùng schema.

## 4. Bật Data Access audit logs

Admin Activity và System Event đã được ghi tự động. Đối với Data Access, tổ chức cần quyết định dịch vụ nào cần ghi DATA_READ, DATA_WRITE và ADMIN_READ.

Ví dụ, một tổ chức muốn ghi nhận việc đọc và ghi dữ liệu cho các dịch vụ hỗ trợ có thể cấu hình auditConfigs trong IAM policy:

~~~yaml
auditConfigs:
  - service: allServices
    auditLogConfigs:
      - logType: DATA_READ
      - logType: DATA_WRITE
      - logType: ADMIN_READ
~~~

Cấu hình trên là một phần của IAM policy. Trước khi áp dụng ở cấp project, folder hoặc organization, hãy kiểm tra policy hiện tại để không vô tình ghi đè các binding hoặc audit configuration đang tồn tại. Có thể dùng cấu hình theo từng service nếu tổ chức chỉ cần thu thập một số loại log cụ thể.

Quy trình triển khai nên gồm:

1. Liệt kê dữ liệu nhạy cảm và dịch vụ cần có bằng chứng truy cập.
2. Xác định DATA_READ, DATA_WRITE hoặc ADMIN_READ phù hợp.
3. Kiểm tra các dịch vụ có hỗ trợ loại audit log tương ứng.
4. Cấu hình auditConfigs tại phạm vi quản lý thích hợp.
5. Tạo một hoạt động kiểm thử có kiểm soát để phát sinh log.
6. Truy vấn Cloud Logging và xác nhận principal, resource, method cùng timestamp.
7. Theo dõi dung lượng log và chi phí sau khi bật.

Ví dụ đọc IAM policy của project:

~~~bash
gcloud projects get-iam-policy acme-prod-123 --format=json
~~~

Sau khi cập nhật policy đã được review, có thể áp dụng bằng:

~~~bash
gcloud projects set-iam-policy acme-prod-123 policy-with-audit-config.json
~~~

Không dùng một file policy cũ để ghi đè policy mới nếu có thay đổi đồng thời. Với môi trường tổ chức, nên quản lý policy qua quy trình Infrastructure as Code hoặc quy trình thay đổi đã được kiểm soát.

### 4.1. Phạm vi cấu hình audit

Audit configuration có thể được quản lý ở cấp organization, folder hoặc project. Chính sách IAM có tính kế thừa, vì vậy cấu hình ở cấp cao hơn có thể áp dụng cho tài nguyên con. Một cấu hình cấp thấp hơn có thể bổ sung hoặc điều chỉnh một số hành vi theo quy tắc hợp nhất của IAM audit config.

Hãy chọn phạm vi dựa trên cách tổ chức quản trị:

- Organization: phù hợp với yêu cầu thu thập thống nhất trên toàn tổ chức.
- Folder: phù hợp khi các nhóm hoặc môi trường có chính sách riêng.
- Project: phù hợp với ngoại lệ hoặc yêu cầu đặc thù của một workload.

Nếu có exemptedMembers, hãy review rất kỹ. Một principal được miễn Data Access audit logging có thể làm giảm khả năng chứng minh hoạt động truy cập. Chỉ dùng ngoại lệ khi có lý do rõ ràng, người phê duyệt và thời hạn rà soát.

## 5. Thu thập log tập trung bằng Log Router

Cloud Logging có thể nhận log từ nhiều project và định tuyến chúng đến các đích lưu trữ hoặc phân tích. Thành phần thực hiện việc định tuyến là Log Router. Một cấu hình định tuyến được gọi là log sink.

Các đích phổ biến:

| Đích | Trường hợp sử dụng |
|---|---|
| Cloud Logging log bucket | Lưu trữ tập trung, truy vấn bằng Logs Explorer hoặc Log Analytics |
| BigQuery dataset | Phân tích audit event bằng SQL và kết hợp dữ liệu kiểm toán |
| Cloud Storage bucket | Lưu trữ dài hạn, xuất hồ sơ và áp dụng retention policy |
| Pub/Sub topic | Chuyển log gần thời gian thực tới SIEM hoặc hệ thống xử lý sự kiện |

Sơ đồ tổng quát:

~~~mermaid
flowchart TB
    P1["Project production A"] --> LR["Cloud Logging / Log Router"]
    P2["Project production B"] --> LR
    P3["Project security"] --> LR
    LR --> LB["Central audit log bucket"]
    LR --> BQ["BigQuery audit dataset"]
    LR --> GCS["Cloud Storage archive"]
    LR --> PS["Pub/Sub"]
    PS --> SIEM["SIEM / Security analytics"]
    LB --> EX["Kiểm toán viên / điều tra viên"]
~~~

### 5.1. Project log sink và aggregated sink

Project sink định tuyến log phát sinh trong một project. Aggregated sink được tạo ở cấp folder hoặc organization và có thể thu thập log từ các project con khi bật tùy chọn include children.

Với tổ chức có nhiều project, aggregated sink giúp chuẩn hóa nơi lưu bằng chứng. Ví dụ, security team có thể tạo một log bucket trong project chuyên dụng để nhận audit logs từ các project production.

Một sink có thể dùng filter để chỉ định loại log cần chuyển. Ví dụ filter sau chọn Admin Activity và Data Access audit logs của Compute Engine. Khi viết filter thực tế, hãy nhóm điều kiện bằng ngoặc để bảo đảm logic OR/AND đúng ý định:

~~~text
(log_id("cloudaudit.googleapis.com/activity")
 OR log_id("cloudaudit.googleapis.com/data_access"))
 AND protoPayload.serviceName="compute.googleapis.com"
~~~

Đối với bằng chứng tuân thủ, hãy tránh loại bỏ nhầm audit logs qua inclusion hoặc exclusion filters. Exclusion có thể khiến một số entry không được lưu ở đích mong muốn. Cần review filter như một thay đổi bảo mật và kiểm thử bằng log entry thực tế.

### 5.2. Quyền ghi vào đích của sink

Khi tạo sink, Cloud Logging sử dụng một writer identity để ghi log vào destination. Principal này cần quyền phù hợp trên đích lưu trữ, ví dụ quyền ghi vào log bucket, BigQuery dataset, Cloud Storage bucket hoặc Pub/Sub topic.

Quy trình triển khai:

1. Tạo destination trong project bảo mật hoặc project lưu trữ.
2. Tạo sink ở project, folder hoặc organization nguồn.
3. Lấy writer identity của sink.
4. Cấp đúng quyền ghi cho writer identity trên destination.
5. Kiểm tra log entry mới đã xuất hiện ở đích.
6. Theo dõi lỗi định tuyến trong cấu hình sink và log của hệ thống.

Không cấp quyền quản trị rộng cho writer identity. Sink chỉ cần quyền ghi vào destination đã chỉ định.

Lưu ý rằng sink chỉ định tuyến log phát sinh sau khi sink được tạo và hoạt động. Việc tạo sink không tự động xuất ngược log cũ đã tồn tại trước đó. Nếu cần thu thập dữ liệu lịch sử, phải truy vấn và xuất từ nguồn còn lưu giữ trong thời hạn retention.

## 6. Thiết kế log bucket và thời hạn lưu giữ

Log bucket là nơi Cloud Logging lưu trữ log entry. Tổ chức có thể dùng bucket mặc định hoặc tạo bucket riêng theo môi trường, loại bằng chứng và yêu cầu lưu giữ.

Trong project, Cloud Logging thường có hai bucket hệ thống:

| Bucket | Nội dung chính | Retention mặc định |
|---|---|---|
| _Required | Admin Activity, System Event và Access Transparency logs | 400 ngày, cố định |
| _Default | Các log còn lại được định tuyến vào bucket mặc định, gồm nhiều Data Access và application logs | 30 ngày, có thể cấu hình |

Log bucket do người dùng tạo có thể được cấu hình thời hạn lưu giữ theo yêu cầu. Thời hạn retention của log bucket thông thường có thể đặt trong khoảng 1 đến 3650 ngày; bucket _Required có quy tắc riêng và giữ 400 ngày.

Không nên mặc định rằng 30 hoặc 400 ngày đáp ứng mọi quy định. Thời hạn thực tế phải dựa trên luật áp dụng, hợp đồng, chính sách nội bộ, thời gian phát hiện sự cố và nhu cầu điều tra.

### 6.1. Chọn retention theo mục đích

Một ma trận chính sách có thể như sau:

| Nhóm log | Mục đích | Chính sách tham khảo |
|---|---|---|
| Admin Activity | Truy vết thay đổi hạ tầng và IAM | Giữ theo thời hạn kiểm toán bắt buộc; có thể xuất archive khi cần lâu hơn |
| Data Access | Chứng minh ai đọc/ghi dữ liệu | Chọn theo độ nhạy dữ liệu, yêu cầu tuân thủ và chi phí |
| Policy Denied | Phân tích truy cập bị chặn | Giữ đủ dài để phát hiện mẫu bất thường và điều tra |
| Application security logs | Điều tra hoạt động của ứng dụng | Theo chính sách vận hành và phân loại dữ liệu |
| Security incident evidence | Hồ sơ vụ việc cụ thể | Giữ theo legal hold hoặc chính sách vụ việc |

Đây là ví dụ thiết kế, không phải thời hạn bắt buộc chung cho mọi tổ chức.

### 6.2. Cấu hình retention cho log bucket

Có thể cập nhật retention của bucket bằng gcloud:

~~~bash
gcloud logging buckets update audit-evidence --location=global --retention-days=2555 --project=security-archive-123
~~~

Lệnh ví dụ đặt retention khoảng bảy năm cho bucket audit-evidence. Trước khi áp dụng, xác minh rằng location và project đúng, thời hạn phù hợp với chính sách, và destination đã được cấp quyền ghi.

Hãy kiểm tra cấu hình thực tế sau khi cập nhật:

~~~bash
gcloud logging buckets describe audit-evidence --location=global --project=security-archive-123
~~~

Đối với bucket _Required, retention 400 ngày được Google Cloud quản lý theo quy tắc riêng; không áp dụng ví dụ cập nhật retention này cho bucket đó.

### 6.3. Retention lock

Cloud Logging hỗ trợ khóa retention cho log bucket. Khi bucket đã bị khóa, thời hạn lưu giữ không thể bị giảm và log không thể bị xóa trước khi hết thời hạn retention. Thao tác khóa có tính không thể đảo ngược, vì vậy cần review trước khi bật.

Retention lock hữu ích khi tổ chức cần chứng minh log được lưu giữ theo một thời hạn đã cam kết. Tuy nhiên, hãy cân nhắc kỹ:

- Thời hạn được chọn có đúng quy định và hợp đồng không?
- Dung lượng và chi phí lưu trữ có được dự toán không?
- Ai được phép tạo bucket, thay đổi retention hoặc khóa bucket?
- Có quy trình xử lý yêu cầu legal hold và hết hạn lưu giữ không?

Retention lock không ngăn mọi loại truy cập trái phép. Tổ chức vẫn cần kiểm soát IAM, bảo vệ project lưu trữ và giám sát thay đổi cấu hình.

## 7. Lưu trữ dài hạn và bảo vệ tính toàn vẹn của bằng chứng

Cloud Logging log bucket phù hợp để truy vấn và phân tích trong thời gian retention. Với hồ sơ cần lưu lâu dài hoặc cần tách khỏi môi trường vận hành, có thể định tuyến log sang Cloud Storage.

Cloud Storage cho phép áp dụng retention policy cho bucket và có thể khóa retention policy bằng Bucket Lock. Khi retention policy đã bị khóa, thời hạn lưu giữ không thể giảm hoặc bị gỡ bỏ trước khi hết thời gian đã cam kết. Bucket Lock là thao tác có tác động lâu dài; hãy thử nghiệm trên bucket riêng và review chính sách trước khi khóa.

Một kiến trúc lưu trữ bằng chứng có thể chia thành hai lớp:

- **Operational logs:** log bucket phục vụ Logs Explorer, điều tra nhanh và phân tích vận hành.
- **Evidence archive:** Cloud Storage bucket trong project bảo mật riêng, có retention policy, Bucket Lock khi cần và IAM tách biệt.

Sơ đồ luồng lưu trữ:

~~~mermaid
flowchart LR
    A["Cloud Audit Logs"] --> R["Log Router"]
    R --> O["Operational log bucket"]
    R --> G["Cloud Storage archive"]
    G --> RP["Retention policy / Bucket Lock"]
    G --> EV["Evidence package"]
    EV --> H["Manifest và SHA-256"]
    EV --> RV["Reviewer / Auditor"]
~~~

### 7.1. Tách quyền giữa nguồn và kho bằng chứng

Một người có quyền quản trị project workload không nên mặc nhiên có quyền xóa kho lưu trữ bằng chứng. Hãy đặt archive trong project bảo mật riêng và giới hạn quyền theo nhiệm vụ.

Ví dụ phân tách:

- Nhóm platform quản lý sink và cấu hình định tuyến.
- Nhóm security quản lý quyền truy cập log bucket và chính sách lưu giữ.
- Nhóm auditor chỉ có quyền xem hoặc truy xuất hồ sơ được phép.
- Nhóm ứng dụng không có quyền xóa hoặc sửa archive.

IAM role cần được gán ở phạm vi nhỏ nhất. Có thể dùng các role Logging Viewer, Private Logs Viewer và Logging Admin theo trách nhiệm. Data Access audit logs có thể yêu cầu quyền Private Logs Viewer để xem. Logging Admin có quyền quản trị rộng hơn, vì vậy không nên cấp cho người chỉ cần đọc bằng chứng.

### 7.2. Giữ hồ sơ truy xuất và chain of custody

Khi xuất log phục vụ kiểm toán hoặc điều tra, hãy lưu kèm thông tin giúp người khác tái lập việc truy xuất:

- Mã vụ việc hoặc mã yêu cầu kiểm toán.
- Project, folder hoặc organization được truy vấn.
- Khoảng thời gian, múi giờ và filter đã sử dụng.
- Thời điểm truy vấn và người thực hiện.
- Nguồn log bucket hoặc dataset.
- Số lượng entry được xuất và định dạng file.
- SHA-256 checksum của từng file hoặc gói bằng chứng.
- Người review, thời điểm bàn giao và các lần truy cập sau đó.

Checksum giúp phát hiện thay đổi nội dung file sau khi xuất. Nó không tự chứng minh rằng dữ liệu nguồn đã đầy đủ hoặc chưa bị thay đổi trước thời điểm xuất. Muốn bảo vệ toàn bộ chuỗi bằng chứng, cần kết hợp checksum với retention lock, IAM tách biệt, audit trail và quy trình bàn giao được ghi nhận.

## 8. Phân quyền truy cập log và bằng chứng

Log có thể chứa email principal, địa chỉ IP, tên tài nguyên, truy vấn hoặc metadata nhạy cảm. Không phải mọi người vận hành đều cần đọc toàn bộ log.

Một số role phổ biến:

| IAM role | Mục đích |
|---|---|
| roles/logging.viewer | Xem log entry và truy vấn log trong phạm vi được cấp |
| roles/logging.privateLogViewer | Xem log riêng tư, gồm Data Access audit logs |
| roles/logging.admin | Quản trị Cloud Logging, gồm cấu hình và quản lý log |
| roles/logging.logWriter | Ghi log vào Cloud Logging trong phạm vi được phép |

Quyền xem log và quyền quản trị log cần được tách biệt. Kiểm toán viên có thể cần quyền xem, trong khi chỉ một nhóm nhỏ được phép thay đổi sink hoặc retention. Principal ghi log của ứng dụng cũng không cần quyền xem tất cả log.

Có thể dùng log views để giới hạn tập log mà một nhóm người dùng được phép truy cập. Ví dụ, auditor phụ trách một nhóm project chỉ cần xem audit logs của nhóm đó. Kết hợp log views với IAM giúp giảm nguy cơ lộ thông tin từ workload khác.

Hãy bật audit logging cho các thao tác quản trị logging quan trọng và theo dõi thay đổi đối với:

- IAM policy của log bucket.
- Log sink và filter.
- Retention period và retention lock.
- Log view và quyền truy cập.
- Destination bucket, dataset hoặc topic.

## 9. Truy vấn và phân tích bằng chứng

Logs Explorer cho phép truy vấn log bằng Logging query language. Hãy bắt đầu từ phạm vi thời gian, resource type và log name; sau đó lọc principal, service, method hoặc resource cần điều tra.

Ví dụ tìm Admin Activity logs của project:

~~~text
logName="projects/acme-prod-123/logs/cloudaudit.googleapis.com%2Factivity"
timestamp >= "2026-11-01T00:00:00Z"
timestamp < "2026-11-02T00:00:00Z"
~~~

Tìm hoạt động do một service account thực hiện:

~~~text
logName="projects/acme-prod-123/logs/cloudaudit.googleapis.com%2Factivity"
protoPayload.authenticationInfo.principalEmail="deployer@acme-prod-123.iam.gserviceaccount.com"
~~~

Tìm Data Access logs của Cloud Storage:

~~~text
logName="projects/acme-prod-123/logs/cloudaudit.googleapis.com%2Fdata_access"
protoPayload.serviceName="storage.googleapis.com"
~~~

Có thể dùng gcloud để đọc log theo filter:

~~~bash
gcloud logging read 'logName="projects/acme-prod-123/logs/cloudaudit.googleapis.com%2Factivity" AND protoPayload.serviceName="compute.googleapis.com"' --project=acme-prod-123 --freshness=7d --limit=1000 --format=json
~~~

Khi điều tra, không chỉ tìm theo email principal. Một workload có thể dùng service account, service agent hoặc danh tính liên kết. Hãy đối chiếu authenticationInfo, serviceName, methodName, resourceName và status. Nếu log có delegationInfo hoặc thông tin impersonation, hãy kiểm tra chuỗi danh tính liên quan.

### 9.1. Phân tích trên BigQuery

Nếu log sink định tuyến audit logs sang BigQuery, nhóm kiểm toán có thể sử dụng SQL để phân tích số lượng hoạt động theo principal, dịch vụ hoặc ngày. Schema và cách biểu diễn trường phụ thuộc cấu hình export; hãy kiểm tra schema dataset trước khi dùng truy vấn mẫu.

Ví dụ truy vấn minh họa khi dataset đã có cột tương ứng:

~~~sql
SELECT
  DATE(timestamp) AS event_date,
  protopayload_auditlog.authenticationInfo.principalEmail AS principal,
  protopayload_auditlog.serviceName AS service,
  COUNT(*) AS event_count
FROM
  `security-archive-123.audit_logs.cloudaudit_googleapis_com_activity_*`
WHERE
  timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY
  event_date, principal, service
ORDER BY
  event_date DESC, event_count DESC;
~~~

Kết quả tổng hợp giúp nhận diện principal có số lượng thao tác tăng bất thường hoặc dịch vụ phát sinh thay đổi ngoài lịch triển khai. Khi cần bằng chứng cho một sự kiện cụ thể, hãy truy xuất các log entry gốc thay vì chỉ lưu bảng tổng hợp.

### 9.2. Log-based metrics và cảnh báo

Cloud Logging có thể tạo log-based metrics từ các entry phù hợp, sau đó dùng Cloud Monitoring để tạo alert. Ví dụ:

- Số lần Policy Denied tăng đột biến.
- Có thay đổi IAM policy ngoài cửa sổ bảo trì.
- Một service account thực hiện thao tác quản trị không thường lệ.
- Số lần truy cập dữ liệu nhạy cảm tăng bất thường.

Metric và alert giúp phát hiện sớm, nhưng không thay thế việc lưu giữ log gốc. Metric thường chỉ giữ thông tin tổng hợp; khi điều tra cần quay lại audit log entry.

## 10. Quy trình thu thập bằng chứng cho một cuộc kiểm toán

Giả sử auditor yêu cầu bằng chứng về các thay đổi quyền IAM trong project production trong tháng vừa qua. Quy trình có thể triển khai như sau:

1. **Xác định phạm vi:** project, folder hoặc organization; khoảng thời gian; loại thay đổi cần chứng minh.
2. **Kiểm tra nguồn:** xác nhận Admin Activity audit logs đã được ghi và log bucket còn dữ liệu trong khoảng thời gian yêu cầu.
3. **Truy vấn:** lọc audit logs theo service, method, principal và resource liên quan đến IAM.
4. **Đối chiếu:** so sánh event với ticket thay đổi, phê duyệt và lịch phát hành.
5. **Xuất dữ liệu:** lưu log entry gốc ở định dạng phù hợp, ví dụ JSON.
6. **Tạo manifest:** ghi filter, khoảng thời gian, nguồn, số lượng entry, thời điểm xuất và checksum.
7. **Review:** người có trách nhiệm kiểm tra tính đầy đủ, diễn giải và phê duyệt gói bằng chứng.
8. **Lưu archive:** đưa gói bằng chứng vào kho lưu trữ có retention phù hợp và quyền truy cập giới hạn.
9. **Ghi nhận bàn giao:** lưu người nhận, thời gian, mục đích và các lần truy cập tiếp theo.

Ví dụ cấu trúc một gói bằng chứng:

~~~text
IAM-CHANGE-REVIEW-2026-11/
  README.md
  query-filter.txt
  audit-entries.json
  manifest.json
  checksums.sha256
  review-notes.pdf
~~~

Manifest có thể chứa metadata, không chứa payload nhạy cảm:

~~~json
{
  "caseId": "IAM-CHANGE-REVIEW-2026-11",
  "sourceProject": "acme-prod-123",
  "logType": "ADMIN_ACTIVITY",
  "timeRangeUtc": {
    "start": "2026-11-01T00:00:00Z",
    "end": "2026-12-01T00:00:00Z"
  },
  "queryFile": "query-filter.txt",
  "exportFile": "audit-entries.json",
  "reviewStatus": "approved"
}
~~~

Đây là mẫu cấu trúc hồ sơ. Trong thực tế, cần bổ sung checksum được tính từ file đã xuất và thông tin người thực hiện, người review theo quy trình nội bộ.

## 11. Tình huống thực tế: xây dựng audit archive cho nhiều project

Một tổ chức có các project dev, staging và production. Nhóm security cần thu thập Admin Activity, Data Access và Policy Denied logs vào một nơi độc lập để phục vụ kiểm toán.

Thiết kế đề xuất:

- Mỗi project nguồn bật các Data Access audit logs cần thiết.
- Organization tạo aggregated sink với include children để thu thập log từ project con.
- Sink định tuyến log phù hợp đến log bucket trung tâm trong project security.
- Một sink khác có thể xuất bản lưu dài hạn sang Cloud Storage.
- Project security dùng IAM tách biệt với nhóm workload.
- Bucket archive áp dụng retention policy và Bucket Lock khi yêu cầu lưu giữ không thể thay đổi.
- Nhóm auditor chỉ được đọc log view hoặc gói bằng chứng trong phạm vi được giao.
- Cảnh báo được tạo cho các thay đổi IAM, sink, retention và quyền truy cập kho archive.

Luồng thay đổi cấu hình:

~~~mermaid
sequenceDiagram
    participant OP as Nhóm vận hành
    participant GCP as Google Cloud resource
    participant LOG as Cloud Audit Logs
    participant ROUTER as Log Router
    participant ARCH as Security archive
    participant AUD as Auditor

    OP->>GCP: Thực hiện thay đổi IAM đã phê duyệt
    GCP->>LOG: Ghi Admin Activity event
    LOG->>ROUTER: Chuyển log entry
    ROUTER->>ARCH: Ghi vào bucket trung tâm
    AUD->>ARCH: Truy vấn hoặc nhận gói bằng chứng
    ARCH-->>AUD: Trả log theo quyền được cấp
~~~

Khi triển khai, hãy kiểm tra một thay đổi thử nghiệm có kiểm soát ở từng project. Xác nhận log entry xuất hiện ở project nguồn, được sink định tuyến và có thể truy vấn tại archive. Kiểm tra cả tình huống principal không có quyền truy cập archive để bảo đảm IAM hoạt động đúng.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy log đọc dữ liệu | Data Access chưa được bật cho service hoặc log type | Kiểm tra auditConfigs, dịch vụ hỗ trợ và thời gian phát sinh sự kiện |
| Có log ở project nguồn nhưng không có ở archive | Sink filter sai hoặc writer identity thiếu quyền trên destination | Kiểm tra filter, sink status và IAM của destination |
| Auditor không xem được Data Access logs | Thiếu quyền Private Logs Viewer hoặc log view giới hạn phạm vi | Cấp đúng role hoặc cập nhật log view theo phê duyệt |
| Log cũ không xuất hiện sau khi tạo sink | Sink chỉ định tuyến log phát sinh sau khi được tạo | Truy vấn nguồn còn retention và xuất lịch sử riêng |
| Kho lưu trữ hết hạn sớm | Retention không phù hợp với yêu cầu hoặc cấu hình sai bucket | Kiểm tra retention của bucket và chính sách archive |
| Log entry thiếu một số trường | Dịch vụ không cung cấp trường đó hoặc dữ liệu bị lược bỏ | Xem schema audit log của dịch vụ và bổ sung nguồn bằng chứng khác |
| Chi phí Logging tăng | Bật quá nhiều Data Access logs hoặc lưu trữ lâu không có phân loại | Đánh giá dịch vụ, filter, retention và khối lượng thực tế; không loại bỏ log bắt buộc |
| Log có dữ liệu nhạy cảm | Ứng dụng ghi thông tin không phù hợp hoặc request metadata chứa dữ liệu riêng tư | Hạn chế nội dung log ở nguồn, kiểm soát quyền xem và xử lý theo chính sách dữ liệu |

Một lỗi đặc biệt nguy hiểm là tạo exclusion filter để giảm chi phí nhưng vô tình loại bỏ audit logs. Mọi thay đổi filter phải được review, kiểm thử và ghi nhận như một thay đổi kiểm soát bảo mật.

## 13. Checklist thiết kế logging và audit evidence

- [ ] Xác định project, folder và organization thuộc phạm vi kiểm toán.
- [ ] Liệt kê các dịch vụ chứa dữ liệu hoặc tài nguyên quan trọng.
- [ ] Xác định loại Admin Activity, Data Access, System Event và Policy Denied cần theo dõi.
- [ ] Bật DATA_READ, DATA_WRITE và ADMIN_READ cho dịch vụ phù hợp.
- [ ] Review exemptedMembers và mọi ngoại lệ trong auditConfigs.
- [ ] Tạo aggregated sink khi cần thu thập log từ nhiều project.
- [ ] Kiểm tra writer identity có đúng quyền ghi trên destination.
- [ ] Không loại bỏ audit logs cần thiết bằng exclusion filter.
- [ ] Chọn log bucket và retention theo quy định, hợp đồng và chính sách nội bộ.
- [ ] Tách project lưu archive khỏi project workload.
- [ ] Áp dụng retention lock hoặc Cloud Storage Bucket Lock sau khi review kỹ.
- [ ] Phân tách quyền xem log, quản trị logging và quản trị kho bằng chứng.
- [ ] Bật cảnh báo cho thay đổi IAM, sink, retention và quyền archive.
- [ ] Kiểm tra định kỳ việc định tuyến và khả năng truy vấn.
- [ ] Lưu filter, time range, manifest, checksum và thông tin bàn giao khi xuất bằng chứng.
- [ ] Không ghi secret, token hoặc dữ liệu nhạy cảm không cần thiết vào application logs.
- [ ] Kiểm tra chi phí ingest, lưu trữ, truy vấn và xuất log.

## 14. Câu hỏi tự kiểm tra

**1. Admin Activity và Data Access audit logs khác nhau thế nào?**

Admin Activity ghi lại thao tác quản trị và thay đổi cấu hình tài nguyên. Data Access ghi lại các hoạt động đọc/ghi dữ liệu hoặc đọc metadata được dịch vụ hỗ trợ. Admin Activity luôn được bật; phần lớn Data Access cần được cấu hình.

**2. Vì sao tổ chức nên dùng aggregated sink ở cấp organization hoặc folder?**

Aggregated sink có thể thu thập log từ nhiều project con vào một destination tập trung. Điều này giúp áp dụng chính sách lưu giữ, phân quyền và giám sát thống nhất, giảm nguy cơ một project bị bỏ sót.

**3. Log sink có tự xuất các log cũ trước khi sink được tạo không?**

Không. Sink định tuyến các log entry mới phù hợp với filter sau khi sink hoạt động. Muốn xuất dữ liệu lịch sử, cần truy vấn nguồn còn dữ liệu và thực hiện export riêng.

**4. Retention lock giúp bảo vệ bằng chứng như thế nào?**

Retention lock ngăn giảm thời hạn lưu giữ hoặc xóa log trước khi hết thời hạn đã cấu hình. Với Cloud Logging, thao tác khóa bucket không thể đảo ngược; với Cloud Storage, Bucket Lock khóa retention policy. Cần review thời hạn trước khi khóa.

**5. Checksum có đủ để chứng minh tính toàn vẹn của bằng chứng không?**

Checksum giúp phát hiện file bị thay đổi sau khi tính hash. Nó không chứng minh dữ liệu nguồn đầy đủ hoặc không bị thay đổi trước lúc xuất. Cần kết hợp checksum với audit trail, retention lock, IAM tách biệt và quy trình chain of custody.

## 15. Tài liệu tham khảo

- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit)
- [Types of audit logs](https://cloud.google.com/logging/docs/audit#types)
- [Configure Data Access audit logs](https://cloud.google.com/logging/docs/audit/configure-data-access)
- [Route logs with sinks](https://cloud.google.com/logging/docs/routing/overview)
- [Create and manage log buckets](https://cloud.google.com/logging/docs/buckets)
- [Set log bucket retention](https://cloud.google.com/logging/docs/buckets#configure_retention)
- [Lock a log bucket](https://cloud.google.com/logging/docs/buckets#lock)
- [Cloud Storage Bucket Lock](https://cloud.google.com/storage/docs/bucket-lock)
- [Cloud Logging IAM roles](https://cloud.google.com/logging/docs/access-control)
- [Logging query language](https://cloud.google.com/logging/docs/view/logging-query-language)
- [Export logs to BigQuery](https://cloud.google.com/logging/docs/export/bigquery)

