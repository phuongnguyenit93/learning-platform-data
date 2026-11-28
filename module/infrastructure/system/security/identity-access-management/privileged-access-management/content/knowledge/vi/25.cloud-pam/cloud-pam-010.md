# Cloud activity audit

Cloud activity audit là việc thu thập, bảo vệ, liên kết và rà soát bằng chứng về hoạt động diễn ra trên môi trường cloud. Trong Privileged Access Management (PAM), audit phải giúp giải thích được ai hoặc workload nào đã sử dụng quyền đặc biệt, sử dụng qua phiên nào, tác động lên tài nguyên nào, vào lúc nào và với kết quả gì.

Một bản ghi “người dùng đã đăng nhập” chưa chứng minh người đó làm gì sau đăng nhập. Một bản ghi “đã assume role” cũng chưa chứng minh phiên đã đọc dữ liệu hay sửa cấu hình nào. Ngược lại, một sự kiện API có danh tính role chung chưa đủ để xác định người yêu cầu, lý do nghiệp vụ và phê duyệt liên quan.

Mục tiêu của bài học là thiết kế chuỗi bằng chứng nối từ danh tính và quyền tới hoạt động cloud, đồng thời hiểu rõ giới hạn của bằng chứng. Ví dụ, tên trường và truy vấn chuẩn hóa trong bài là mô hình minh họa; cần ánh xạ sang schema và khả năng của nền tảng thực tế trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt log xác thực, cấp quyền, hoạt động quản trị và truy cập dữ liệu.
- Xây dựng ma trận độ bao phủ theo account, môi trường, dịch vụ và loại hành động.
- Liên kết người hoặc workload với phiên PAM và sự kiện cloud.
- Thiết kế lưu trữ bằng chứng có phân tách quyền và kiểm tra toàn vẹn.
- Phát hiện hoạt động đặc quyền ngoài phạm vi và phát hiện chính pipeline audit bị lỗi.
- Phân biệt việc không tìm thấy log với việc chứng minh không có hoạt động.
- Chuẩn bị hồ sơ sự cố có nguồn gốc, thời gian và giới hạn kết luận rõ ràng.

## 2. Audit cần trả lời những câu hỏi nào?

### 2.1. Từ câu hỏi nghiệp vụ tới bằng chứng kỹ thuật

Một số câu hỏi thường gặp:

- Ai đã đổi policy truy cập production?
- Ai đã đọc một secret trong khoảng sự cố?
- Workload nào tạo credential mới?
- Một phiên break-glass đã làm gì sau khi được cấp?
- Thay đổi có thuộc nhiệm vụ được duyệt không?
- Principal nào đã tắt hoặc làm suy yếu audit?
- Sau quyết định thu hồi, có hoạt động tiếp tục hay phiên mới được cấp không?
- Kho dữ liệu nào có thể đã bị truy cập?

Mỗi câu hỏi cần một hoặc nhiều nguồn bằng chứng. Không có một loại log duy nhất luôn trả lời được tất cả.

| Câu hỏi | Nguồn thường cần |
| --- | --- |
| Ai đã xác thực? | Log hệ thống danh tính và federation |
| Vì sao được cấp quyền? | Policy, grant và phê duyệt PAM |
| Phiên nào được tạo? | Log broker hoặc dịch vụ cấp phiên |
| Phiên đã gọi API nào? | Audit của control plane hoặc dịch vụ |
| Dữ liệu nào được truy cập? | Log data plane phù hợp với tài nguyên |
| Tài nguyên thực sự thay đổi thế nào? | Audit kết hợp lịch sử cấu hình hoặc trạng thái |
| Bằng chứng có bị thay đổi không? | Kiểm tra toàn vẹn và lịch sử truy cập kho log |
| Vì sao không có sự kiện? | Cấu hình thu thập, telemetry pipeline và kiểm thử nguồn |

### 2.2. Phân biệt hành động được yêu cầu và kết quả cuối

Một API có thể chỉ nhận yêu cầu tạo job. Request được chấp nhận không có nghĩa job đã hoàn tất, dữ liệu đã được chuyển hết hoặc cấu hình đã có hiệu lực trên mọi instance.

Audit cần phân biệt:

~~~text
Yêu cầu được gửi
    -> được xác thực và kiểm tra
    -> được chấp nhận
    -> tác vụ được thực thi
    -> kết quả được xác minh
~~~

Tùy dịch vụ, các bước này có thể xuất hiện trong nhiều sự kiện khác nhau. Nếu chỉ có bằng chứng ở bước đầu, kết luận phải dừng ở mức đó.

### 2.3. Audit là khả năng giải thích, không chỉ là dung lượng lưu

Lưu rất nhiều log vẫn có thể không đủ nếu:

- Thiếu sự kiện đọc dữ liệu quan trọng.
- Không biết role chung đại diện cho người nào.
- Không thu thập account mới.
- Không thể giải mã log cũ khi cần.
- Truy vấn đã bỏ qua dữ liệu lỗi định dạng.
- Không có bằng chứng cấu hình audit tại thời điểm sự cố.

Một thiết kế tốt cần xác định câu hỏi cần trả lời trước, rồi chứng minh dữ liệu thu thập đáp ứng được câu hỏi ấy.

## 3. Phân loại nguồn log trong Cloud PAM

### 3.1. Xác thực và vòng đời danh tính

Nguồn này có thể ghi:

- Đăng nhập thành công hoặc thất bại.
- Điều kiện xác thực tăng cường.
- Thay đổi phương thức xác thực.
- Tạo, vô hiệu hóa hoặc thay thuộc tính tài khoản.
- Thay đổi nhóm hoặc entitlement.
- Thiết lập federation và quan hệ trust.

Không suy ra mọi hoạt động dùng credential đều có một lần đăng nhập tương tác tương ứng. Workload, credential tạm thời và tiến trình nền có vòng đời khác người dùng.

### 3.2. Cấp và sử dụng đặc quyền

Các sự kiện PAM cần thể hiện:

- Yêu cầu sử dụng role hoặc tài nguyên.
- Quyết định tự động hoặc phê duyệt.
- Grant, phạm vi và thời hạn.
- Cấp, gia hạn và kết thúc phiên.
- Thu hồi hoặc thay đổi điều kiện.
- Sử dụng break-glass.
- Thay đổi cấu hình broker và policy.

PAM cần lưu cả quyết định từ chối khi điều đó nằm trong yêu cầu giám sát. Tuy nhiên, đừng mặc định mọi nguồn cloud đều ghi tất cả request bị chặn ở mọi lớp; cần xác minh độ bao phủ của từng loại lỗi.

### 3.3. Control plane

Control plane liên quan tới quản lý tài nguyên và cấu hình, chẳng hạn:

- Tạo hoặc xóa workload.
- Thay policy và role.
- Đổi cấu hình mạng.
- Tạo credential.
- Thay thiết lập audit.
- Thay nguồn hoặc thời hạn lưu log.

Đây thường là nhóm sự kiện quan trọng để phát hiện mở rộng quyền và làm suy yếu kiểm soát.

### 3.4. Data plane

Data plane liên quan tới sử dụng nội dung hoặc chức năng của tài nguyên:

- Đọc hoặc ghi object.
- Lấy secret.
- Thực thi một truy vấn dữ liệu.
- Gọi một chức năng xử lý.
- Xuất dữ liệu.

Một principal chỉ có quyền đọc vẫn có thể gây tác động đáng kể nếu đọc dữ liệu nhạy cảm hoặc secret. Vì vậy, không bỏ log đọc chỉ vì muốn tập trung vào thao tác sửa và xóa.

### 3.5. Log ứng dụng, hệ điều hành và phiên tương tác

Audit cloud không thay thế hoàn toàn:

- Log nghiệp vụ trong ứng dụng.
- Sự kiện hệ điều hành.
- Log cơ sở dữ liệu.
- Ghi nhận lệnh hoặc phiên qua PAM.
- Log pipeline và artifact.

Một thao tác trong máy ảo có thể không tạo API quản trị cloud tương ứng. Ngược lại, nhiều thao tác cloud được thực hiện qua SDK và không có màn hình để ghi.

Cần liên kết các nguồn khi câu hỏi điều tra đi qua nhiều lớp.

## 4. Một số khác biệt giữa các nền tảng

### 4.1. AWS CloudTrail

CloudTrail Event history cho phép xem các management event đã ghi trong 90 ngày gần nhất của một AWS Region; nó không hiển thị data event. Khi cần dữ liệu khác hoặc lưu dài hơn, phải thiết kế nguồn thu và lưu phù hợp thay vì coi Event history là kho audit đầy đủ. [CloudTrail Event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events-console.html).

Data event mô tả thao tác trên hoặc bên trong tài nguyên, ví dụ hoạt động object của S3. Trail và event data store không mặc định ghi data event; cần cấu hình phạm vi lựa chọn phù hợp. [Ghi data event trong CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html).

Hệ quả thiết kế: nếu mục tiêu là chứng minh phiên đã đọc object nào, việc tìm thấy sự kiện tạo phiên hoặc thay cấu hình bucket chưa đáp ứng mục tiêu đó.

### 4.2. Azure

Azure Activity log chủ yếu ghi hoạt động control plane. Hoạt động bên trong tài nguyên cần resource log phù hợp, với diagnostic setting để thu thập. Activity log không thường ghi thao tác đọc và cũng không phải log xác thực, phân quyền cho mọi request bị chặn trước khi thao tác bắt đầu. Thời gian lưu Activity log là 90 ngày; nhu cầu lưu dài hơn cần cấu hình đích bổ sung. [Activity log trong Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log).

Hệ quả thiết kế: không lấy Activity log làm bằng chứng duy nhất cho việc đọc secret hoặc xác định mọi lần thử truy cập bị từ chối.

### 4.3. Google Cloud

Cloud Audit Logs có các nhóm Admin Activity, Data Access, System Event và Policy Denied. Admin Activity luôn được ghi. Data Access phần lớn cần được bật chủ động; BigQuery là ngoại lệ đối với mặc định này. Khả năng ghi và nội dung sự kiện cần đối chiếu theo dịch vụ. [Tổng quan Cloud Audit Logs](https://docs.cloud.google.com/logging/docs/audit).

Hệ quả thiết kế: tên dịch vụ audit được bật ở cấp tổ chức không thay thế việc xác minh hoạt động cụ thể và quyền đọc được loại log cần điều tra.

### 4.4. Không chuẩn hóa bằng cách xóa mọi khác biệt

Có thể chuẩn hóa để tìm kiếm đa cloud, nhưng cần giữ:

- Nguồn và schema gốc.
- Loại sự kiện của nhà cung cấp.
- Ý nghĩa thời gian và kết quả.
- Phạm vi tài nguyên.
- Trường tùy chọn và dữ liệu bị thiếu.
- Tham chiếu tới bản gốc.

Không đổi mọi trạng thái thiếu thông tin thành success, mọi principal thành user hoặc mọi thao tác đọc thành cùng một loại hành động. Chuẩn hóa không được tạo ra bằng chứng chưa tồn tại.

## 5. Xây dựng ma trận độ bao phủ

### 5.1. Các chiều cần kiểm kê

Ma trận nên bao gồm:

- Tổ chức, tenant hoặc partition có liên quan.
- Account, subscription hoặc project.
- Region và dịch vụ.
- Môi trường.
- Loại principal.
- Loại tài nguyên.
- Hành động quan trọng.
- Sự kiện thành công và loại từ chối cần theo dõi.
- Nơi phát sinh, nơi lưu và nơi truy vấn.
- Owner.
- Kiểm thử gần nhất.
- Ngoại lệ và rủi ro chưa được xử lý.

Đừng dùng danh sách account hiện tại như thể nó là toàn bộ phạm vi lịch sử. Account bị đóng hoặc dự án đã chuyển owner vẫn có thể liên quan đến sự cố trước đó.

### 5.2. Ví dụ ma trận

| Phạm vi | Hành động cần biết | Nguồn cần xác minh | Phép thử |
| --- | --- | --- | --- |
| IAM production | Sửa trust hoặc quyền role | Audit quản trị | Thay đổi role lab và đối chiếu sự kiện |
| Object storage nhạy cảm | Đọc và xóa object | Data audit đúng tài nguyên | Đọc, ghi, xóa object lab |
| Secret store | Lấy secret | Audit của dịch vụ | Lấy secret giả trong lab |
| Broker PAM | Cấp và từ chối phiên | Log broker và token service | Grant hợp lệ, hết hạn, sai đích |
| Kho log | Đổi policy, retention, khóa mã hóa | Audit quản trị và lưu trữ | Thử thay đổi được kiểm soát |
| Pipeline phát hành | Chạy thay đổi production | Log pipeline và audit đích | Liên kết run ID tới hoạt động |

Các phép thử trên chỉ thực hiện với tài nguyên được phép. Không cần dùng dữ liệu thật hoặc thao tác phá hủy production để chứng minh log hoạt động.

### 5.3. Theo dõi account và tài nguyên mới

Một pipeline audit phải có quy trình onboarding khi xuất hiện:

- Account hoặc project mới.
- Region mới được sử dụng.
- Dịch vụ mới.
- Nhóm tài nguyên nhạy cảm mới.
- Đường truy cập bên thứ ba.
- Cơ chế cấp credential mới.

Cần kiểm tra cả cấu hình kế thừa và trạng thái thực tế. Một template có thiết lập audit không chứng minh mọi tài nguyên đã được triển khai bằng template đó.

### 5.4. Ghi nhận ngoại lệ rõ ràng

Nếu chưa có log đáp ứng yêu cầu cho một hành động, ghi:

- Hành động và phạm vi bị thiếu.
- Tại sao chưa thu được.
- Bằng chứng thay thế hiện có.
- Giới hạn của bằng chứng thay thế.
- Owner và kế hoạch xử lý.
- Thời hạn đánh giá lại.

Không âm thầm loại hành động ấy khỏi mẫu số rồi báo “100% đã audit”.

## 6. Kiến trúc thu thập và lưu trữ

### 6.1. Luồng tham khảo

~~~text
Danh tính / PAM / API cloud / data service / ứng dụng
                         |
                         v
              Thu thập và định tuyến
                         |
              +----------+-----------+
              |                      |
              v                      v
      Kho bản ghi gốc          Chuẩn hóa và lập chỉ mục
      được bảo vệ                     |
              |                      v
              |              Tương quan và cảnh báo
              |                      |
              +----------+-----------+
                         v
             Điều tra và xuất bằng chứng
~~~

Kho gốc và kho phân tích có mục đích khác nhau. Kho phân tích giúp tìm kiếm; kho gốc giữ dữ liệu và nguồn gốc phục vụ kiểm tra lại. Một hệ thống có thể kết hợp các chức năng, nhưng phải biết chức năng nào được bảo đảm bằng cơ chế nào.

### 6.2. Phân tách quyền

Một mô hình phân quyền tham khảo:

| Nhóm hoặc principal | Quyền cần có | Khả năng cần hạn chế |
| --- | --- | --- |
| Collector | Ghi đúng đích hoặc đọc đúng nguồn | Không quản trị mọi tài nguyên nghiệp vụ |
| Parser | Đọc bản ghi được giao, tạo dữ liệu chuẩn hóa | Không sửa bản gốc |
| Analyst | Truy vấn theo phạm vi nhiệm vụ | Không đổi retention hoặc xóa bằng chứng |
| Audit administrator | Quản lý pipeline theo quy trình | Không tự hợp thức hóa mọi thay đổi của mình |
| Evidence exporter | Xuất đúng hồ sơ được duyệt | Không truy cập tùy ý toàn bộ dữ liệu nhạy cảm |
| Workload nghiệp vụ | Quyền vận hành cần thiết | Không sửa hoặc xóa kho audit |

Nếu tài khoản quản trị môi trường nghiệp vụ cũng có toàn quyền sửa kho log, một sự cố quyền cao có thể ảnh hưởng cả tài nguyên lẫn bằng chứng.

Cần xác định rõ ranh giới mà kiến trúc thực sự bảo vệ được, kể cả quyền quản trị cấp tổ chức.

### 6.3. Bảo vệ đích lưu và khóa mã hóa

Kiểm soát cần xét:

- Quyền ghi, đọc, sửa và xóa.
- Chính sách retention và cơ chế lưu giữ chống thay đổi nếu được sử dụng.
- Quyền sửa lifecycle hoặc chuyển tầng lưu trữ.
- Quyền quản trị khóa mã hóa.
- Khả năng giải mã dữ liệu lịch sử.
- Backup hoặc bản sao cần thiết.
- Đường xuất log ra ngoài.
- Quy trình thay đổi và phê duyệt.

Giữ được object mã hóa nhưng mất khả năng giải mã vẫn có thể làm mất khả năng điều tra. Cần quản lý vòng đời khóa theo nhu cầu giữ và phục hồi bằng chứng.

### 6.4. Tính sẵn sàng và khả năng khôi phục

Phải biết pipeline phản ứng thế nào khi:

- Nguồn không gửi được.
- Collector hết quyền.
- Đích từ chối ghi.
- Hàng đợi tồn đọng.
- Parser gặp schema mới.
- Kho truy vấn bị gián đoạn.
- Khóa mã hóa không dùng được.

Cần có telemetry về lỗi, retry, backlog và dữ liệu bị loại. Không cho phép parser bỏ qua lỗi rồi báo pipeline thành công chỉ vì tiến trình vẫn chạy.

## 7. Chuẩn hóa sự kiện mà vẫn giữ ngữ nghĩa

### 7.1. Bộ trường tham khảo

Một schema chuẩn hóa có thể gồm:

| Nhóm | Trường minh họa |
| --- | --- |
| Nguồn | provider, sourceType, schemaVersion |
| Phạm vi | tenantId, accountId, region, environment |
| Định danh sự kiện | sourceEventId, requestId, rawReference |
| Thời gian | occurredAt, ingestedAt |
| Principal | principalType, principalId, sessionId |
| Nguồn yêu cầu | sourceIdentity, delegatedBy, workloadRunId |
| Hành động | service, operation, actionCategory |
| Tài nguyên | resourceId, resourceType |
| Kết quả | outcome, errorCode, completionState |
| PAM | grantId, changeId, correlationStatus |
| Chất lượng | parseStatus, missingFields, mappingVersion |

Không phải nguồn nào cũng có mọi trường. Giá trị thiếu phải được thể hiện trung thực, cùng quy tắc xử lý.

### 7.2. Ví dụ sự kiện chuẩn hóa

~~~json
{
  "provider": "example-cloud",
  "sourceType": "resource-audit",
  "sourceEventId": "evt-7301",
  "occurredAt": "2026-11-26T07:12:30Z",
  "ingestedAt": "2026-11-26T07:14:05Z",
  "accountId": "production-account",
  "principalType": "assumed-role-session",
  "principalId": "billing-evidence-reader",
  "sessionId": "session-019",
  "sourceIdentity": "operator-017",
  "operation": "object.read",
  "resourceId": "reports/run-2026-11-26/report-a",
  "outcome": "success",
  "grantId": "GRANT-2841",
  "correlationStatus": "matched",
  "rawReference": "evidence/source/evt-7301",
  "mappingVersion": "audit-map-3"
}
~~~

Đây không phải sự kiện nguyên bản của AWS, Azure hay Google Cloud. grantId có thể là dữ liệu bổ sung từ phép nối với PAM, không phải trường được nhà cung cấp ghi trực tiếp.

Cần lưu nguồn của mỗi dữ liệu bổ sung. Người điều tra phải phân biệt “nguồn cloud khẳng định” với “hệ thống tương quan suy ra”.

### 7.3. Trường gốc có thể tùy chọn hoặc bị giới hạn

Trong CloudTrail, các trường như danh tính, hành động, nguồn dịch vụ, thời gian, lỗi và tham số có ngữ nghĩa riêng; một số trường chỉ có ở loại API hoặc sự kiện phù hợp, và một số nội dung có giới hạn kích thước. Không nên xây parser dựa trên giả định mọi record luôn có một payload đầy đủ. [Nội dung record CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html).

Thiết kế nên:

- Giữ bản gốc.
- Theo dõi phiên bản mapping.
- Chấp nhận trường mới theo cách có kiểm soát.
- Cảnh báo thiếu trường cần thiết.
- Tách sự kiện lỗi parse để xử lý lại.
- Không tự điền success khi không xác định được kết quả.

### 7.4. Thời gian phát sinh khác thời gian nhận

occurredAt là thời gian sự kiện theo ngữ nghĩa của nguồn. ingestedAt là thời gian hệ thống nhận hoặc xử lý.

Độ trễ quan sát có thể tính:

~~~text
observedLag = ingestedAt - occurredAt
~~~

Phải thống nhất múi giờ, cách xử lý đồng hồ và ý nghĩa trường. Nếu độ trễ âm hoặc lớn bất thường, cần kiểm tra mapping và nguồn thời gian thay vì tự sửa dữ liệu gốc.

Không sắp xếp toàn bộ điều tra chỉ theo thời gian nhận, vì các sự kiện có thể tới trễ hoặc không theo thứ tự phát sinh.

### 7.5. Dữ liệu trùng và retry

Một hoạt động có thể tạo nhiều record, còn một record có thể được giao lại nhiều lần. Hai vấn đề này khác nhau.

Dedupe cần dùng khóa phù hợp với hợp đồng của nguồn, chẳng hạn kết hợp định danh nguồn và phạm vi. Không chỉ dựa vào timestamp và tên API.

Khi hợp nhất dữ liệu, cần giữ khả năng giải thích:

- Record nào là bản giao lại.
- Record nào thuộc hoạt động khác.
- Vì sao đã gộp.
- Bản gốc nào hỗ trợ kết quả.

Nếu đếm nhiều bản giao lại thành nhiều thao tác quản trị, cảnh báo và báo cáo sẽ sai.

## 8. Liên kết danh tính, phiên PAM và hoạt động cloud

### 8.1. Chuỗi tương quan

~~~text
Danh tính doanh nghiệp hoặc workload
                |
                v
       Request / grant PAM
                |
                v
       Sự kiện cấp phiên cloud
                |
                v
       Hành động trên tài nguyên
                |
                v
       Kết quả và trạng thái thực tế
~~~

Một role có thể được nhiều người và workload sử dụng. Cần dựa vào ngữ cảnh phiên, nguồn danh tính và sự kiện cấp phiên để truy ngược, không chỉ tên role.

### 8.2. Mức độ tin cậy của phép nối

Có thể phân loại kết quả tương quan:

- **Khớp xác định:** có định danh hoặc chuỗi bằng chứng được kiểm soát nối trực tiếp.
- **Khớp theo quy tắc:** nối bằng các thuộc tính đã được xác định nhưng cần giả định.
- **Chưa khớp:** thiếu dữ liệu hoặc không tìm được grant.
- **Mâu thuẫn:** có nhiều ứng viên hoặc thông tin không nhất quán.

Không đổi một phép nối gần đúng theo thời gian thành khẳng định chắc chắn về người thực hiện.

Nếu nhiều phiên dùng cùng tên trong cùng khoảng thời gian, cần thêm dữ liệu. Tên phiên hoặc mã ticket do client tự chọn không tự chứng minh danh tính hay phê duyệt.

### 8.3. Phân biệt người khởi tạo và principal trực tiếp

Một người có thể tạo job rồi dịch vụ chạy job bằng service account khác. Audit cần giữ:

- Người khởi tạo nếu có bằng chứng.
- Workload hoặc dịch vụ thực thi.
- Principal trực tiếp gọi API.
- Chuỗi ủy quyền hoặc tham chiếu job.
- Thời gian yêu cầu và thời gian thực thi.

Không gán mọi hành động của dịch vụ cho người đã tạo tài nguyên từ nhiều tháng trước. Cần chứng minh mối liên kết với lần thực thi đang xét.

### 8.4. Phiên tự động và workload

Đối với pipeline, các dữ liệu có ích gồm:

- Repository hoặc nguồn mã.
- Workflow.
- Run ID.
- Phiên bản được phát hành.
- Môi trường.
- Danh tính workload.
- Grant hoặc policy cho phép.
- Role và tài nguyên đích.

Các thuộc tính chỉ có giá trị nếu nguồn và mapping được bảo vệ. Một biến môi trường do mã không tin cậy tự đặt không nên trở thành căn cứ duy nhất để quy trách nhiệm.

## 9. Phát hiện hoạt động đặc quyền bất thường

### 9.1. Bắt đầu từ hành vi và ranh giới

Các nhóm phát hiện thường có ích:

- Cấp quyền mới hoặc mở rộng trust.
- Tạo credential ngoài quy trình.
- Role tác nghiệp sửa policy hoặc audit.
- Principal truy cập tài nguyên ngoài nhiệm vụ.
- Sử dụng break-glass nhưng không có hồ sơ tương ứng.
- Cấp hoặc refresh phiên sau khi grant đã kết thúc.
- Thay đích log, filter, retention hoặc khóa mã hóa.
- Khối lượng truy cập dữ liệu lệch đáng kể khỏi công việc đã xác nhận.
- Hoạt động từ principal chưa có owner.

Cần định nghĩa sự kiện và ngữ cảnh cụ thể. Một rule chỉ kiểm tra tên role chứa admin có thể bỏ qua quyền đặc biệt với tên khác.

### 9.2. Kết hợp điều kiện thay vì kết luận từ một tín hiệu yếu

Một địa chỉ IP mới không tự chứng minh bị chiếm quyền. Workload có thể đổi hạ tầng hoặc đi qua proxy. Một user agent lạ cũng có thể là công cụ hợp lệ.

Tín hiệu mạnh hơn thường đến từ tổ hợp:

~~~text
Phiên có quyền đặc biệt
    + không nối được với grant hợp lệ
    + truy cập tài nguyên ngoài nhiệm vụ
    + thay cấu hình audit hoặc tạo quyền mới
~~~

Cần giữ bằng chứng cho từng điều kiện và thể hiện những phần chưa biết.

### 9.3. Truy vấn minh họa tìm sự kiện chưa nối được grant

~~~sql
SELECT
    account_id,
    principal_id,
    session_id,
    operation,
    resource_id,
    occurred_at,
    source_event_id
FROM normalized_cloud_events
WHERE action_category = 'privileged'
  AND occurred_at >= :start_time
  AND occurred_at < :end_time
  AND correlation_status IN ('unmatched', 'conflict');
~~~

Đây là SQL minh họa trên schema chuẩn hóa tự thiết kế, không phải truy vấn dùng trực tiếp cho một sản phẩm cụ thể.

Kết quả là danh sách cần kiểm tra. Nó có thể bao gồm:

- Hoạt động ngoài quy trình.
- Grant đến trễ.
- Mapping phiên lỗi.
- Workload hợp lệ chưa được onboarding.
- Dữ liệu lịch sử thiếu.

Không tự kết luận mọi dòng là hành vi trái phép.

### 9.4. Hoạt động sau thời điểm kết thúc grant

Cần phân biệt:

- Phiên mới được cấp sau khi grant kết thúc.
- Phiên cũ vẫn có quyền theo thời hạn credential.
- Job đã nhận trước đó chạy sau.
- Dịch vụ tiếp tục tác vụ bằng danh tính riêng.
- Log đến muộn nhưng hành động xảy ra trước.

Rule phải dùng thời gian phát sinh và ngữ cảnh phù hợp, không chỉ thời gian nhận log. Kết luận phụ thuộc hợp đồng vòng đời quyền đã thiết kế.

## 10. Phát hiện audit bị mất hoặc bị làm suy yếu

### 10.1. Mất log là một phát hiện riêng

Không có sự kiện trong một cửa sổ có thể do:

- Không có hoạt động.
- Nguồn chưa được bật.
- Filter đã loại loại sự kiện đó.
- Đích ghi bị lỗi.
- Collector mất quyền.
- Parser không nhận schema.
- Truy vấn sai account, thời gian hoặc loại log.
- Người điều tra không có quyền xem dữ liệu.
- Dữ liệu chưa tới.
- Dữ liệu đã hết thời gian lưu.

Do đó, “không thấy” là trạng thái cần giải thích, chưa phải bằng chứng rằng “không xảy ra”.

### 10.2. Theo dõi sức khỏe từ đầu tới cuối

Các telemetry cần có:

- Trạng thái nguồn và cấu hình lựa chọn sự kiện.
- Số lượng record được nguồn ghi hoặc giao khi có dữ liệu đó.
- Lỗi giao nhận.
- Backlog và tuổi record cũ nhất đang chờ.
- Độ trễ ingest.
- Tỷ lệ parse lỗi.
- Sự kiện bị lọc hoặc loại.
- Lỗi truy cập kho lưu và khóa mã hóa.
- Kết quả kiểm thử tổng hợp.

Một biểu đồ số lượng log bằng không không phân biệt được môi trường yên tĩnh với pipeline hỏng nếu không có tín hiệu bổ sung.

### 10.3. Kiểm thử tổng hợp

Có thể định kỳ tạo hoạt động lành tính trong lab hoặc tài nguyên kiểm thử:

1. Dùng principal được xác định.
2. Thực hiện hành động nhỏ đã được cho phép.
3. Ghi thời gian và mã thử.
4. Tìm sự kiện ở nguồn.
5. Tìm bản gốc ở đích lưu.
6. Tìm record chuẩn hóa.
7. Kiểm tra tương quan và cảnh báo thử.
8. Lưu độ trễ và kết quả.

Một phép thử đi hết chuỗi giúp kiểm tra nhiều lớp hơn việc chỉ xác nhận collector đang chạy.

Phép thử cần đủ tương đồng với loại hoạt động quan trọng. Một sự kiện control plane không chứng minh data audit của secret store cũng hoạt động.

### 10.4. Bảo vệ cấu hình audit

Những thay đổi cần được quản lý như hành động đặc quyền:

- Tắt nguồn hoặc đổi filter.
- Xóa hoặc đổi sink.
- Đổi policy kho log.
- Rút ngắn retention.
- Đổi khóa hoặc quyền giải mã.
- Thay parser và mapping.
- Tắt rule cảnh báo.
- Tạo ngoại lệ bỏ qua principal.

Cần lưu ai thay đổi, lý do, cấu hình trước và sau khi có thể thu được, cùng kết quả kiểm thử sau thay đổi. Không để cùng một principal dễ dàng sửa cả hoạt động nghiệp vụ lẫn bằng chứng về hoạt động đó.

## 11. Tính toàn vẹn và nguồn gốc bằng chứng

### 11.1. Toàn vẹn khác đầy đủ

Tính toàn vẹn trả lời: bản ghi đang xét có bị thay đổi ngoài quy trình hoặc sau mốc được xác minh không?

Tính đầy đủ trả lời: những hoạt động cần được ghi có thực sự được ghi, chuyển và giữ lại không?

Hai điều này không thay thế nhau:

~~~text
Tệp không bị sửa
    không đồng nghĩa
Mọi hoạt động cần thiết đều nằm trong tệp
~~~

Một bộ log hoàn toàn nguyên vẹn vẫn có thể thiếu data event vì chưa bật đúng nguồn.

### 11.2. Ví dụ kiểm tra toàn vẹn CloudTrail

CloudTrail hỗ trợ digest có chữ ký và hash để kiểm tra log đã được giao có bị thay đổi hoặc thiếu theo cơ chế xác minh. Bật log file integrity validation làm hệ thống giao digest; việc bật không tự thực hiện thao tác validate. [Kiểm tra toàn vẹn log CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html).

Khi cơ chế validation bị tắt trong một giai đoạn, digest không được tạo cho các log được giao trong giai đoạn đó. Không coi bật lại là tự phục hồi chuỗi bằng chứng toàn vẹn của mọi khoảng trước đó. [Cấu trúc và chuỗi digest CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-digest-file-structure.html).

Thiết kế cần lưu phạm vi, thời gian và kết quả validate, không chỉ trạng thái “feature enabled”.

### 11.3. Hash tự tính có giới hạn gì?

Hash của một tệp khi xuất giúp kiểm tra bản sao có khớp tệp đã xuất hay không. Nó không tự chứng minh:

- Tệp đến từ nhà cung cấp thật.
- Tệp chưa bị sửa trước lúc tính hash.
- Bộ dữ liệu đã đầy đủ.
- Người sử dụng credential chính là chủ tài khoản.
- Cấu hình thu thập đã đúng tại thời điểm sự cố.

Cần nối hash với nguồn gốc, cách lấy dữ liệu, thời gian, người thực hiện và cơ chế xác minh tương ứng.

### 11.4. Hồ sơ xuất bằng chứng

Một hồ sơ có thể gồm:

- Mã vụ việc.
- Câu hỏi điều tra và phạm vi.
- Nguồn log.
- Khoảng thời gian và múi giờ.
- Truy vấn và phiên bản truy vấn.
- Filter, cách xử lý phân trang và dữ liệu đến trễ.
- Danh sách tệp và hash.
- Kết quả kiểm tra toàn vẹn nếu áp dụng.
- Người thực hiện và thời điểm xuất.
- Hạn chế, nguồn thiếu và giả định.
- Lịch sử chuyển giao và truy cập hồ sơ.

Bản chuẩn hóa hoặc bảng tổng hợp nên có tham chiếu tới dữ liệu gốc đủ để người khác kiểm tra lại kết luận trong phạm vi quyền được cấp.

## 12. Lưu giữ, dữ liệu nhạy cảm và quyền của người điều tra

### 12.1. Chọn retention theo nhu cầu đã xác nhận

Nhu cầu lưu có thể đến từ:

- Khoảng phát hiện sự cố.
- Khả năng điều tra lại.
- Chu kỳ rà soát quyền.
- Yêu cầu nội bộ hoặc nghĩa vụ áp dụng.
- Loại dữ liệu và chi phí truy xuất.
- Khả năng khôi phục khóa và công cụ đọc dữ liệu.

Không áp một thời hạn tùy ý cho mọi nguồn. Cần ghi owner, căn cứ và cách xác minh dữ liệu còn đọc được trong toàn bộ khoảng cần giữ.

Thời gian lưu ở nguồn và thời gian lưu tại kho tập trung có thể khác nhau. Việc export phải xảy ra đủ sớm theo thiết kế để tránh mất dữ liệu trước khi chuyển.

### 12.2. Audit log cũng chứa thông tin nhạy cảm

Log có thể chứa:

- Định danh cá nhân hoặc workload.
- Tên tài nguyên.
- Địa chỉ mạng.
- Tham số request.
- Nội dung truy vấn.
- Metadata khách hàng.
- Thông tin lỗi có ngữ cảnh nghiệp vụ.

Không mặc định dữ liệu audit đã được làm sạch hoàn toàn. Cần kiểm tra thực tế và hạn chế việc thêm secret, token hoặc payload nhạy cảm vào các log do tổ chức tự tạo.

### 12.3. Giữ bản gốc và tạo bản dùng cho phân tích

Một cách thiết kế là bảo vệ bản gốc trong phạm vi hẹp, đồng thời tạo bản chuẩn hóa hoặc che dữ liệu cho nhóm sử dụng rộng hơn.

Việc che dữ liệu cần có:

- Quy tắc rõ.
- Phiên bản xử lý.
- Giải thích trường nào đã bị thay đổi.
- Kiểm soát quyền truy cập bản đầy đủ.
- Khả năng nối lại trong điều tra được phép.

Không sửa âm thầm bản gốc rồi coi đó là dữ liệu nhà cung cấp đã giao.

### 12.4. Quyền điều tra cũng là quyền đặc biệt

Người điều tra có thể nhìn thấy thông tin trên nhiều môi trường. Áp dụng least privilege cho:

- Phạm vi account hoặc project.
- Loại log.
- Khoảng thời gian.
- Khả năng xem trường nhạy cảm.
- Khả năng xuất.
- Thời hạn truy cập.

Các truy vấn và lần xuất bằng chứng cũng nên được audit theo yêu cầu của hệ thống. Không dùng tài khoản dùng chung cho mọi người điều tra.

## 13. Quy trình rà soát và ứng phó

### 13.1. Rà soát theo tín hiệu và theo mẫu

Có thể kết hợp:

- Cảnh báo gần thời gian thực cho hành vi quan trọng.
- Rà soát định kỳ các thay đổi quyền.
- Đối soát phiên PAM với grant.
- Kiểm tra mọi lần break-glass.
- Lấy mẫu hoạt động đặc quyền theo mức tác động.
- Kiểm tra nguồn log và ngoại lệ.

Rà soát phải có owner và kết quả. Một dashboard được mở nhiều lần nhưng không có quyết định xử lý chưa chứng minh kiểm soát đang hoạt động.

### 13.2. Trình tự điều tra tham khảo

1. Xác định câu hỏi, tài nguyên và khoảng thời gian ban đầu.
2. Kiểm tra nguồn audit nào bao phủ hành động cần tìm.
3. Bảo toàn dữ liệu liên quan và ghi nguồn gốc.
4. Xác định principal trực tiếp và phiên.
5. Nối tới người hoặc workload, grant và phê duyệt.
6. Dựng timeline theo thời gian phát sinh.
7. Kiểm tra quyền và cấu hình tại thời điểm sự kiện nếu có dữ liệu.
8. Xác định tác động và các hành động phát sinh.
9. Thực hiện biện pháp ngăn chặn theo runbook được phép.
10. Xác minh hiệu lực và ghi giới hạn kết luận.

Policy hiện tại không nhất thiết là policy tại thời điểm sự cố. Nếu cần kết luận về quyền lúc đó, phải tìm lịch sử phù hợp hoặc ghi rõ chưa có bằng chứng.

### 13.3. Không chờ audit hoàn hảo mới xử lý tác động đang diễn ra

Trong sự cố, bằng chứng có thể chưa đầy đủ. Có thể cần ngăn cấp phiên, chặn quyền hoặc cô lập workload theo quy trình ứng phó đã được cho phép.

Cần ghi rõ quyết định dựa trên dữ kiện nào, phần nào còn chưa biết và thời điểm hành động. Sau đó tiếp tục thu thập để xác định phạm vi.

Tránh nhầm “chưa tìm thấy log” với “không có rủi ro”, nhưng cũng tránh khẳng định dữ liệu đã bị lấy chỉ vì thấy một lần cấp phiên.

## 14. Tình huống thực hành: thiếu bằng chứng đọc báo cáo

### 14.1. Bối cảnh

Một người trực ca được cấp phiên đọc báo cáo Billing production theo GRANT-2841. Sau đó hệ thống cảnh báo có thay đổi policy của kho báo cáo.

Nhóm điều tra tìm thấy:

- Yêu cầu và phê duyệt PAM.
- Sự kiện tạo phiên cloud.
- Một sự kiện thay policy.
- Không thấy sự kiện đọc object trong màn hình lịch sử quản trị.

Một người kết luận: “Không có log đọc nên không có dữ liệu bị truy cập.”

### 14.2. Phân tích cần thực hiện

Kết luận trên chưa có cơ sở đầy đủ. Cần xác định:

- Màn hình hoặc nguồn đang xem có hiển thị data event không?
- Data audit có được bật cho đúng kho và hành động tại thời điểm đó không?
- Có filter hoặc exclusion nào không?
- Dữ liệu nằm ở account, project hoặc region nào?
- Người điều tra có quyền đọc loại log đó không?
- Sự kiện có đến trễ hay nằm ngoài cửa sổ truy vấn không?
- Phiên thay policy có đúng phiên được cấp không?
- Có workload hoặc principal khác tham gia không?

Nếu data audit chưa được bật, có thể không tái dựng được toàn bộ lịch sử đọc từ nguồn đó. Bật audit sau sự cố không tạo lại các sự kiện chưa từng được ghi.

### 14.3. Đầu ra cần nộp

- Timeline với sự kiện được xác minh và phần chưa biết.
- Ma trận độ bao phủ tại thời điểm sự cố.
- Chuỗi liên kết grant, phiên và hành động.
- Đánh giá thay đổi policy và quyền hiệu lực liên quan.
- Danh sách bằng chứng thay thế có thể dùng cùng giới hạn.
- Kế hoạch xử lý khoảng trống audit.
- Kết quả kiểm thử sau khi sửa.
- Cách điều chỉnh báo cáo để không khẳng định vượt dữ liệu.

Mục tiêu là đưa ra kết luận đúng mức bằng chứng, không phải buộc mọi vụ việc phải có câu trả lời chắc chắn về từng hành động.

## 15. Kế hoạch kiểm thử nghiệm thu

| Phép thử | Điều cần chứng minh |
| --- | --- |
| Thực hiện thay đổi IAM trên tài nguyên lab | Sự kiện quản trị tới nguồn và kho đích |
| Đọc dữ liệu lab nhạy cảm giả | Data audit đúng hành động và tài nguyên |
| Lấy secret giả | Có nguồn bằng chứng phù hợp với dịch vụ |
| Request bị từ chối có chủ đích | Biết nguồn nào ghi và giới hạn trường hợp không ghi |
| Cấp phiên qua PAM | Nối được danh tính, grant và phiên |
| Principal dùng chung role | Không nhầm hai người hoặc hai workload |
| Record giao lại | Dedupe không tạo số đếm giả |
| Sự kiện đến trễ | Timeline dùng đúng thời gian và có cơ chế xử lý |
| Schema có trường mới hoặc thiếu trường | Parser không bỏ dữ liệu âm thầm |
| Đích log từ chối ghi trong lab | Phát hiện lỗi giao nhận và có khôi phục |
| Thay cấu hình lựa chọn log | Có audit và kiểm thử độ bao phủ sau thay đổi |
| Principal nghiệp vụ thử xóa bản log được bảo vệ | Bị hạn chế theo mô hình quyền |
| Xuất hồ sơ điều tra | Có nguồn, truy vấn, danh sách tệp và kiểm tra bản sao |
| Đọc dữ liệu lịch sử ở tầng lưu trữ cũ | Khôi phục và giải mã được trong yêu cầu |
| Account hoặc project mới | Tự động hoặc theo quy trình đưa vào kiểm soát |

Mỗi phép thử cần đầu vào, tài nguyên được phép, sự kiện mong đợi, thời gian chờ phù hợp với nguồn và điều kiện PASS rõ ràng.

Không dùng một phép thử thành công để suy ra mọi account, dịch vụ và loại hoạt động đều đã được bao phủ.

## 16. Chỉ số đánh giá

### 16.1. Chỉ số độ bao phủ

- Tỷ lệ phạm vi cloud đã có owner audit.
- Tỷ lệ hành động đặc quyền quan trọng đã có nguồn được kiểm thử.
- Số ngoại lệ chưa có bằng chứng phù hợp.
- Thời gian onboarding account hoặc dịch vụ mới.

Mẫu số phải là danh mục hành động và phạm vi được xác nhận, không chỉ là những nguồn đã gửi log.

### 16.2. Chỉ số chất lượng và khả năng sử dụng

- Độ trễ ingest theo từng nhóm nguồn.
- Tỷ lệ parse lỗi hoặc trường bắt buộc bị thiếu.
- Tỷ lệ phiên nối được với grant.
- Tỷ lệ sự kiện tương quan mâu thuẫn.
- Kết quả kiểm tra toàn vẹn theo phạm vi áp dụng.
- Tỷ lệ truy xuất thành công bằng chứng lịch sử.
- Số lần pipeline mất log chưa được giải thích.

### 16.3. Chỉ số vận hành

- Thời gian phát hiện và phân loại tín hiệu quan trọng.
- Thời gian dựng chuỗi danh tính tới tài nguyên.
- Tỷ lệ cảnh báo có kết luận và bằng chứng.
- Số thay đổi audit chưa qua quy trình.
- Tỷ lệ break-glass được hậu kiểm.
- Thời gian xác minh hiệu lực sau biện pháp thu hồi.

Không tối ưu riêng số lượng cảnh báo. Ít cảnh báo có thể do kiểm soát tốt, cũng có thể do nguồn đã bị tắt hoặc rule không còn chạy.

## 17. Câu hỏi tự kiểm tra

**Có sự kiện assume-role thì đã biết phiên đọc những dữ liệu nào chưa?**

Chưa. Cần audit của hoạt động trên tài nguyên với độ bao phủ phù hợp.

**Không thấy log có chứng minh hành động không xảy ra không?**

Chưa. Phải loại trừ khoảng trống thu thập, quyền xem, truy vấn sai, độ trễ và hết retention trước khi đưa ra kết luận phù hợp.

**Một bản log nguyên vẹn có chắc là đầy đủ không?**

Không. Toàn vẹn của bản ghi và độ bao phủ hành động là hai yêu cầu khác nhau.

**Hash tệp xuất có chứng minh nguồn dữ liệu đáng tin cậy không?**

Nó giúp kiểm tra bản sao khớp nội dung đã tính hash. Nguồn gốc và tính đầy đủ cần bằng chứng riêng.

**Role chung có đủ để quy trách nhiệm cho một người không?**

Không. Cần ngữ cảnh phiên và chuỗi liên kết được kiểm soát tới người hoặc workload.

**Vì sao log sau khi grant kết thúc cần được phân tích cẩn thận?**

Có thể là sự kiện đến trễ, phiên cũ, job đã nhận hoặc dịch vụ dùng danh tính riêng. Cần dùng đúng thời gian và hợp đồng vòng đời quyền.

**Có nên lưu toàn bộ token và secret để điều tra thuận tiện hơn không?**

Không. Chỉ thu dữ liệu cần thiết, bảo vệ thông tin nhạy cảm và tránh tạo thêm nguồn lộ credential.

**Vì sao quyền sửa retention hoặc khóa mã hóa là quyền đặc biệt?**

Nó có thể làm mất khả năng giữ, đọc hoặc xác minh bằng chứng, ngay cả khi tài nguyên nghiệp vụ không bị sửa trực tiếp.

Cloud activity audit có giá trị khi người rà soát nối được quyết định cấp quyền với hoạt động thực tế, kiểm tra được nguồn gốc bằng chứng và hiểu phần dữ liệu còn thiếu. Trong Cloud PAM, thu thập đúng loại sự kiện, bảo vệ pipeline và kiểm thử khả năng truy vết là những công việc phải được duy trì cùng với quản lý role, phiên và credential.
