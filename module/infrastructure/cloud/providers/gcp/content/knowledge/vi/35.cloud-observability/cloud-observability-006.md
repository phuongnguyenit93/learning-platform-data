# Cloud Audit Logs và lựa chọn loại nhật ký kiểm toán

Khi vận hành Google Cloud, nhóm nền tảng cần trả lời được những câu hỏi như: ai đã thay đổi quyền IAM, dịch vụ nào đã đọc dữ liệu nhạy cảm, thao tác nào bị từ chối và một thay đổi cấu hình bắt nguồn từ đâu. Cloud Audit Logs ghi lại hoạt động liên quan đến việc sử dụng tài nguyên Google Cloud, giúp tổ chức điều tra sự cố, kiểm soát thay đổi, đáp ứng yêu cầu kiểm toán và chứng minh cách tài nguyên được truy cập.

Cloud Audit Logs là một phần của Cloud Logging. Mỗi bản ghi kiểm toán thường có thông tin về dịch vụ, phương thức API, tài nguyên, danh tính gọi API, kết quả và ngữ cảnh yêu cầu. Tuy nhiên, mức chi tiết thay đổi theo dịch vụ và phương thức API. Vì vậy, thiết kế kiểm toán cần bắt đầu bằng việc xác định sự kiện nào phải được ghi, danh tính nào cần được theo dõi và dữ liệu nhật ký sẽ được bảo vệ, lưu trữ, truy vấn như thế nào.

## 1. Bốn loại Cloud Audit Logs

Cloud Audit Logs có bốn loại chính. Mỗi loại phản ánh một nhóm hoạt động khác nhau và phục vụ một mục tiêu điều tra riêng.

| Loại nhật ký | Nội dung | Trạng thái mặc định và ví dụ |
| --- | --- | --- |
| Admin Activity | Thao tác làm thay đổi cấu hình hoặc metadata của tài nguyên | Luôn được bật. Ví dụ: tạo VM, thay đổi firewall rule, cập nhật IAM policy hoặc xóa bucket |
| Data Access | Thao tác đọc metadata, đọc dữ liệu hoặc ghi dữ liệu do người dùng cung cấp | Thường bị tắt mặc định, ngoại trừ một số dịch vụ như BigQuery. Ví dụ: đọc object trong Cloud Storage hoặc truy vấn bảng |
| System Event | Thao tác quản trị do hệ thống Google thực hiện trên tài nguyên | Luôn được bật. Ví dụ: hành động hệ thống làm thay đổi trạng thái hoặc cấu hình tài nguyên |
| Policy Denied | Yêu cầu bị từ chối do vi phạm chính sách bảo mật hoặc kiểm soát truy cập | Được tạo cho các trường hợp và dịch vụ hỗ trợ loại nhật ký này; dùng để tìm nguyên nhân truy cập bị chặn |

Admin Activity và System Event là hai nguồn quan trọng để theo dõi thay đổi tài nguyên. Chúng được Google Cloud tự động ghi lại và người dùng không thể tắt bằng cấu hình audit logging thông thường. Data Access cần được cân nhắc chủ động vì có thể tạo lượng log lớn. Policy Denied giúp nhận biết hoạt động bị chặn, nhưng không thay thế việc kiểm tra IAM policy, VPC Service Controls hoặc các chính sách bảo mật khác.

### Admin Activity: ai đã thay đổi cấu hình?

Admin Activity ghi lại các thao tác quản trị làm thay đổi cấu hình hoặc metadata của tài nguyên. Các ví dụ thường gặp gồm:

- Tạo, cập nhật hoặc xóa tài nguyên Compute Engine.
- Thay đổi IAM policy của project, folder hoặc resource.
- Tạo hoặc cập nhật bucket, dataset, service account hay cấu hình mạng.
- Thay đổi cấu hình dịch vụ có ảnh hưởng đến cách tài nguyên được vận hành.

Đây thường là loại nhật ký đầu tiên cần xem khi một thay đổi bất ngờ xuất hiện. Nếu một tài khoản cấp thêm quyền Owner cho principal khác, bản ghi Admin Activity có thể giúp xác định danh tính gọi API, phương thức được gọi, tài nguyên bị tác động và thời điểm thay đổi.

### Data Access: ai đã đọc hoặc ghi dữ liệu?

Data Access ghi lại các thao tác truy cập dữ liệu hoặc metadata. Loại này bao gồm ba nhóm cấu hình:

| Nhóm cấu hình | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| ADMIN_READ | Đọc cấu hình hoặc metadata của tài nguyên | Đọc thông tin cấu hình hoặc metadata của một tài nguyên |
| DATA_READ | Đọc dữ liệu do người dùng cung cấp | Đọc object trong Cloud Storage hoặc truy vấn dữ liệu trong BigQuery |
| DATA_WRITE | Ghi, tạo, cập nhật hoặc xóa dữ liệu do người dùng cung cấp | Tải object lên bucket hoặc thay đổi dữ liệu trong bảng |

Điểm dễ nhầm là ADMIN_READ vẫn thuộc nhóm Data Access audit logs. Nó ghi lại việc đọc cấu hình hoặc metadata, trong khi Admin Activity ghi lại các thao tác quản trị làm thay đổi cấu hình. Vì vậy, một truy vấn đọc IAM policy có thể thuộc ADMIN_READ; thao tác thay đổi IAM policy thuộc Admin Activity.

Data Access thường bị tắt mặc định ở nhiều dịch vụ vì số lượng yêu cầu đọc và ghi có thể rất lớn. BigQuery là ngoại lệ quan trọng: BigQuery Data Access audit logs được bật mặc định và không thể tắt. Khi cần điều tra việc dữ liệu nhạy cảm bị đọc, không thể chỉ dựa vào Admin Activity; phải bảo đảm Data Access logging được bật cho dịch vụ và phạm vi dữ liệu liên quan.

### System Event: hệ thống đã tự thực hiện điều gì?

System Event ghi lại các thao tác quản trị do hệ thống Google thực hiện trên tài nguyên. Những sự kiện này có thể xảy ra mà không có người dùng trực tiếp gọi thao tác quản trị tương ứng. Khi tài nguyên thay đổi trạng thái do hành động của nền tảng, System Event giúp nhóm vận hành phân biệt sự kiện do hệ thống tạo ra với thay đổi do người dùng hoặc ứng dụng yêu cầu.

System Event luôn được bật. Khi điều tra, hãy xem cùng Admin Activity và các log vận hành khác để hiểu đầy đủ chuỗi sự kiện, thay vì kết luận rằng mọi thay đổi đều bắt nguồn từ một tài khoản người dùng.

### Policy Denied: vì sao yêu cầu bị chặn?

Policy Denied ghi lại các yêu cầu bị từ chối do chính sách bảo mật hoặc kiểm soát truy cập. Chẳng hạn, người dùng có thể có quyền IAM ở một cấp nhưng yêu cầu vẫn bị chặn bởi một ràng buộc khác, hoặc một thao tác vi phạm chính sách của tổ chức.

Khi xem loại log này, hãy kiểm tra principal, tài nguyên, dịch vụ, phương thức API, mã trạng thái và thông tin lý do từ chối nếu dịch vụ cung cấp. Không phải mọi lỗi ứng dụng đều là Policy Denied: lỗi mạng, lỗi xác thực, lỗi quota hoặc lỗi trạng thái dịch vụ có thể có nguyên nhân khác. Hãy đối chiếu log kiểm toán với log ứng dụng và trạng thái dịch vụ.

## 2. Chọn loại log theo câu hỏi kiểm toán

Không nên bật mọi loại Data Access ở mọi project mà không xác định mục tiêu. Hãy bắt đầu từ câu hỏi cần trả lời, sau đó chọn log type và dịch vụ tương ứng.

| Câu hỏi cần trả lời | Loại log nên kiểm tra | Ví dụ phạm vi |
| --- | --- | --- |
| Ai tạo, sửa hoặc xóa tài nguyên? | Admin Activity | Project, folder, Compute Engine, IAM |
| Ai đọc cấu hình hoặc metadata? | Data Access – ADMIN_READ | Metadata bucket, cấu hình dịch vụ |
| Ai đọc dữ liệu nghiệp vụ? | Data Access – DATA_READ | Object nhạy cảm, bảng BigQuery, secret |
| Ai tạo, sửa hoặc xóa dữ liệu? | Data Access – DATA_WRITE | Bucket, dataset hoặc kho dữ liệu |
| Hành động tự động nào do nền tảng thực hiện? | System Event | Tài nguyên được dịch vụ Google quản lý |
| Vì sao yêu cầu bị từ chối? | Policy Denied và log liên quan | IAM, chính sách tổ chức hoặc kiểm soát dịch vụ |

Với môi trường phát triển ít dữ liệu nhạy cảm, tổ chức có thể ưu tiên Admin Activity và System Event, đồng thời bật Data Access cho những dịch vụ cần điều tra chi tiết. Với môi trường sản xuất chứa dữ liệu khách hàng, hồ sơ tài chính hoặc bí mật ứng dụng, cần đánh giá việc bật DATA_READ và DATA_WRITE trên các dịch vụ lưu trữ, cơ sở dữ liệu và Secret Manager.

Một ma trận lựa chọn thực tế có thể như sau:

| Tài nguyên hoặc dịch vụ | Câu hỏi kiểm soát | Lựa chọn cần đánh giá |
| --- | --- | --- |
| IAM và service account | Ai thay đổi quyền hoặc sử dụng danh tính? | Admin Activity; Data Access ADMIN_READ nếu cần theo dõi việc đọc metadata |
| Cloud Storage | Ai đọc hoặc ghi object? | DATA_READ và DATA_WRITE |
| BigQuery | Ai truy vấn hoặc thay đổi dữ liệu? | BigQuery Data Access được bật mặc định; kiểm tra phạm vi và khả năng truy vấn |
| Secret Manager | Ai đọc phiên bản secret hoặc thay đổi secret? | Admin Activity và Data Access theo khả năng hỗ trợ của dịch vụ |
| Compute Engine và VPC | Ai thay đổi VM, firewall hoặc cấu hình mạng? | Admin Activity; System Event cho hoạt động do hệ thống thực hiện |
| Dịch vụ dùng CMEK | Ai thay đổi cấu hình khóa hoặc truy cập dữ liệu qua dịch vụ? | Admin Activity của Cloud KMS và Data Access của dịch vụ dữ liệu khi cần |

Tên loại log không bảo đảm rằng mọi API method của một dịch vụ đều tạo ra cùng một trường dữ liệu. Trước khi đưa yêu cầu kiểm toán vào vận hành, hãy kiểm tra tài liệu audit logging của từng dịch vụ để biết method nào được ghi, loại log nào được hỗ trợ và trường nào có thể truy vấn.

## 3. Bật Data Access logs bằng IAM auditConfigs

Data Access logging được cấu hình thông qua phần auditConfigs trong IAM policy của tổ chức, folder hoặc project. Cấu hình có thể áp dụng cho tất cả dịch vụ hoặc chỉ một dịch vụ cụ thể. Khi thiết kế, hãy chọn đúng phạm vi để đáp ứng chính sách kiểm toán mà không tạo lượng log không cần thiết.

Ví dụ sau minh họa cấu hình ghi lại thao tác đọc và ghi dữ liệu của Cloud Storage:

~~~yaml
auditConfigs:
- service: storage.googleapis.com
  auditLogConfigs:
  - logType: DATA_READ
  - logType: DATA_WRITE
~~~

Đây là đoạn cấu hình auditConfigs để hợp nhất vào IAM policy hiện có, không phải toàn bộ policy độc lập. Khi cập nhật policy, cần giữ nguyên các binding, điều kiện, cấu hình kiểm toán khác và etag hiện tại. Không thay thế policy đang dùng bằng một tệp chỉ chứa đoạn ví dụ này.

Nếu tổ chức muốn áp dụng cấu hình chung cho nhiều dịch vụ, có thể dùng service là allServices, sau đó tạo cấu hình riêng cho dịch vụ cần ngoại lệ. Hãy kiểm tra quy tắc kế thừa từ organization xuống folder và project, cũng như cấu hình cụ thể của từng dịch vụ. Một cấu hình ở cấp thấp hơn có thể làm thay đổi cách cấu hình kế thừa được áp dụng cho dịch vụ đó.

Trường exemptedMembers cho phép loại trừ principal khỏi một số Data Access audit logs. Đây là cơ chế có ảnh hưởng trực tiếp đến khả năng kiểm toán. Chỉ sử dụng ngoại lệ khi có lý do rõ ràng, được phê duyệt và ghi nhận; tránh loại trừ tài khoản vận hành hoặc service account quan trọng chỉ để giảm lượng log.

### Kiểm tra cấu hình sau khi bật

Sau khi cập nhật IAM policy:

1. Đọc lại policy tại đúng cấp tổ chức, folder hoặc project để xác nhận auditConfigs được lưu.
2. Kiểm tra cấu hình có bị ghi đè hoặc ảnh hưởng bởi policy kế thừa hay không.
3. Thực hiện một thao tác thử phù hợp trên tài nguyên kiểm thử, chẳng hạn đọc hoặc ghi một object không nhạy cảm.
4. Mở Logs Explorer và tìm Data Access log theo dịch vụ, principal và thời gian thử nghiệm.
5. Nếu chưa thấy log, kiểm tra dịch vụ có hỗ trợ method đó không, log có bị loại trừ hoặc định tuyến sang bucket khác không, và người xem có đủ quyền đọc log không.

Việc bật auditConfigs không đồng nghĩa rằng mọi bản ghi sẽ xuất hiện ngay trong một truy vấn bất kỳ. Hãy kiểm tra đúng project chứa log, đúng loại log, khoảng thời gian và phạm vi tài nguyên.

## 4. Đọc cấu trúc một bản ghi kiểm toán

Cloud Audit Logs thường lưu thông tin kiểm toán trong trường protoPayload với kiểu dữ liệu AuditLog. Một bản ghi có thể chứa các trường quan trọng sau:

| Trường | Ý nghĩa khi điều tra |
| --- | --- |
| serviceName | Dịch vụ Google Cloud nhận yêu cầu |
| methodName | Phương thức API được gọi |
| resourceName | Tài nguyên chịu tác động |
| authenticationInfo | Danh tính hoặc thông tin xác thực gắn với yêu cầu |
| authorizationInfo | Thông tin kiểm tra quyền đối với tài nguyên |
| requestMetadata | Ngữ cảnh yêu cầu, có thể gồm thông tin nguồn gọi |
| status | Kết quả hoặc lỗi của thao tác |
| request và response | Một phần nội dung yêu cầu hoặc phản hồi nếu dịch vụ ghi lại |
| timestamp | Thời điểm bản ghi được tạo |

Không phải dịch vụ nào cũng cung cấp mọi trường hoặc cùng mức chi tiết. Một số giá trị có thể bị lược bỏ, làm mờ hoặc không được ghi vì lý do bảo mật. Audit logs không phải bản sao đầy đủ của dữ liệu nghiệp vụ; không nên giả định rằng nội dung object, hàng dữ liệu hay secret sẽ xuất hiện trong bản ghi.

Khi điều tra, hãy ghép principal với methodName, resourceName, status và timestamp. Nếu có nhiều project, cần xác định log nằm ở project tài nguyên, project chứa log hoặc đích tập trung do Log Router định tuyến.

## 5. Truy vấn Cloud Audit Logs trong Logs Explorer

Logs Explorer cho phép lọc log bằng Logging query language. Có thể bắt đầu bằng log ID, sau đó thu hẹp theo dịch vụ, phương thức API, principal hoặc tài nguyên.

Tìm các thao tác quản trị:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="storage.googleapis.com"
~~~

Tìm các lần đọc object qua Data Access:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.serviceName="storage.googleapis.com"
protoPayload.methodName="storage.objects.get"
~~~

Tìm các lần ghi object:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.serviceName="storage.googleapis.com"
protoPayload.methodName="storage.objects.create"
~~~

Tìm thao tác của một danh tính cụ thể:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.authenticationInfo.principalEmail="app-reader@example.iam.gserviceaccount.com"
~~~

Tìm các yêu cầu bị từ chối do policy:

~~~text
log_id("cloudaudit.googleapis.com/policy")
protoPayload.status.code=7
~~~

Các truy vấn trên là điểm bắt đầu. Tên method, resource type và trường principal có thể khác theo dịch vụ và loại danh tính. Khi không có kết quả, hãy mở rộng bộ lọc theo thời gian và project trước khi kết luận rằng sự kiện không được ghi.

Một quy trình điều tra thay đổi trái phép có thể thực hiện như sau:

1. Tìm Admin Activity quanh thời điểm phát hiện thay đổi.
2. Lọc theo serviceName và resourceName để xác định tài nguyên bị tác động.
3. Kiểm tra authenticationInfo để nhận diện principal gọi API.
4. Đọc methodName, authorizationInfo và status để hiểu thao tác được thực hiện và kết quả.
5. Mở rộng sang Data Access để xem dữ liệu có bị đọc hoặc ghi sau thay đổi hay không.
6. Đối chiếu timestamp với log ứng dụng, Cloud Monitoring alert và hệ thống quản lý thay đổi.

## 6. Quyền đọc log và quyền quản lý log

Log có thể chứa danh tính, tên tài nguyên, địa chỉ nguồn gọi và thông tin vận hành nhạy cảm. Vì vậy, quyền xem log cũng phải được quản lý theo nguyên tắc đặc quyền tối thiểu.

| IAM role | Phạm vi quyền chính | Đối tượng phù hợp |
| --- | --- | --- |
| roles/logging.viewer | Đọc phần lớn log, không bao gồm Data Access audit logs | Nhóm vận hành cần tra cứu log thông thường |
| roles/logging.privateLogViewer | Đọc các log riêng tư, bao gồm Data Access audit logs | Nhóm bảo mật hoặc kiểm toán được phép xem hoạt động truy cập dữ liệu |
| roles/logging.configWriter | Tạo và quản lý cấu hình định tuyến log như sink | Nhóm nền tảng quản lý luồng log |
| roles/logging.admin | Quyền quản trị Cloud Logging rộng | Nhóm quản trị logging được ủy quyền |

Không nên cấp quyền quản trị Cloud Logging cho mọi người chỉ vì họ cần xem một số log. Có thể cấp roles/logging.viewer cho nhóm hỗ trợ, sau đó cấp roles/logging.privateLogViewer riêng cho nhóm được phép điều tra Data Access. Quyền đọc log, quyền tạo sink và quyền thay đổi IAM policy nên được phân công theo trách nhiệm.

Ngoài IAM role, cần bảo vệ project nhận log tập trung, log bucket, sink và các đích xuất dữ liệu. Người có quyền đọc BigQuery dataset hoặc Cloud Storage bucket đích có thể truy cập bản sao log đã xuất, ngay cả khi họ không có quyền xem log gốc trong project nguồn.

## 7. Lưu trữ, định tuyến và tập trung nhật ký

Cloud Logging Log Router tiếp nhận log và định tuyến chúng đến log bucket hoặc các đích hỗ trợ như BigQuery, Cloud Storage và Pub/Sub. Sink có thể đặt ở project, folder hoặc organization. Với tổ chức có nhiều project, aggregated sink ở cấp organization hoặc folder giúp tập trung log để giám sát và kiểm toán xuyên suốt.

Một kiến trúc thường gặp gồm:

- Project workload tạo Audit Logs khi người dùng hoặc dịch vụ gọi API.
- Sink ở cấp folder hoặc organization chọn log cần thu thập và gửi đến project bảo mật.
- Project bảo mật lưu log trong log bucket riêng, áp dụng quyền truy cập và thời hạn lưu phù hợp.
- Hệ thống SIEM hoặc pipeline phân tích nhận log từ BigQuery hoặc Pub/Sub khi cần xử lý bổ sung.

Khi tạo sink tập trung, cần bảo đảm danh tính dịch vụ của sink có quyền ghi vào đích nhận. Với sink bao gồm tài nguyên con, phải bật lựa chọn bao gồm log từ các project con theo đúng phạm vi mong muốn. Bộ lọc sink cần được kiểm tra để tránh vô tình bỏ qua Data Access hoặc Policy Denied logs cần cho kiểm toán.

Log bucket mặc định có thời hạn lưu khác nhau: bucket _Required giữ các loại log bắt buộc như Admin Activity và System Event trong 400 ngày; bucket _Default có thời hạn lưu mặc định 30 ngày và có thể được điều chỉnh theo cấu hình, chính sách và giới hạn dịch vụ. Data Access và các log khác có thể được định tuyến vào bucket _Default hoặc đích do tổ chức cấu hình. Hãy xác nhận vị trí thực tế của từng loại log và retention policy trước khi xây dựng cam kết lưu trữ.

Nếu yêu cầu pháp lý hoặc chính sách nội bộ đòi hỏi lưu log lâu hơn, cần cấu hình retention phù hợp hoặc xuất log sang kho lưu trữ được quản lý riêng. Hãy bảo vệ bản sao xuất, kiểm soát quyền xóa và xác định ai được thay đổi retention. Lưu log lâu hơn không tự động làm log đáng tin cậy hơn nếu người không phù hợp vẫn có thể sửa cấu hình định tuyến hoặc xóa bản sao.

## 8. Chi phí và chất lượng dữ liệu kiểm toán

Data Access logs có thể tăng nhanh khi ứng dụng thường xuyên đọc dữ liệu hoặc truy vấn bảng. Chi phí phụ thuộc vào lượng log được thu thập, lưu trữ và định tuyến theo cấu hình Cloud Logging cũng như các đích nhận. Trước khi bật trên toàn tổ chức, nên ước lượng lưu lượng, thử nghiệm trên một project đại diện và theo dõi mức sử dụng thực tế.

Các biện pháp kiểm soát gồm:

1. Bật Data Access theo dịch vụ và phạm vi dữ liệu có yêu cầu kiểm toán rõ ràng.
2. Dùng log bucket, sink và retention phù hợp với nhu cầu điều tra và lưu trữ.
3. Theo dõi lượng log theo project, loại log và dịch vụ để phát hiện tăng đột biến.
4. Tránh loại trừ các sự kiện bắt buộc chỉ để giảm chi phí; nếu cần lọc, phải đánh giá tác động đến khả năng kiểm toán.
5. Giới hạn quyền đọc log riêng tư và quyền quản lý cấu hình định tuyến.

Một hệ thống kiểm toán tốt phải cân bằng ba yêu cầu: đủ dữ liệu để điều tra, bảo vệ dữ liệu log khỏi truy cập trái phép và duy trì chi phí có thể dự đoán. Không nên tối ưu chi phí bằng cách loại bỏ những sự kiện mà tổ chức cần để phát hiện truy cập trái phép hoặc chứng minh tuân thủ.

## 9. Kịch bản thực tế: điều tra việc đọc dữ liệu bất thường

Giả sử nhóm bảo mật phát hiện service account của một ứng dụng đọc một lượng lớn object trong bucket chứa dữ liệu khách hàng vào thời điểm ngoài lịch vận hành. Nhóm cần xác định hoạt động nào đã xảy ra và có thay đổi quyền trước đó hay không.

**Bước 1 – Xác định danh tính và thời gian.** Dùng Data Access logs của Cloud Storage để lọc theo principalEmail, bucket và khoảng thời gian. Kiểm tra methodName để phân biệt đọc object với thao tác liệt kê hoặc thay đổi metadata.

**Bước 2 – Xác định phạm vi dữ liệu.** Dựa trên resourceName và các trường tài nguyên được dịch vụ cung cấp để xác định object hoặc bucket liên quan. So sánh với phạm vi dữ liệu mà ứng dụng được phép xử lý.

**Bước 3 – Kiểm tra thay đổi quyền.** Tìm Admin Activity trong cùng khoảng thời gian và trước đó để xem IAM policy, service account hoặc cấu hình bucket có bị thay đổi không.

**Bước 4 – Kiểm tra yêu cầu bị chặn.** Tìm Policy Denied logs để biết có các lần truy cập bị từ chối hoặc thử vượt quyền hay không. Kết hợp với log ứng dụng và cảnh báo Cloud Monitoring để xác định chuỗi sự kiện.

**Bước 5 – Lưu bằng chứng và xử lý.** Xuất các log liên quan đến kho điều tra được bảo vệ, ghi lại bộ lọc và khoảng thời gian đã sử dụng, sau đó phối hợp với chủ sở hữu workload để đánh giá credential và thu hồi quyền nếu cần.

Kịch bản này chỉ khả thi nếu Data Access logging đã được bật và log được giữ đủ lâu. Nếu trước thời điểm sự cố không thu thập DATA_READ, Admin Activity vẫn có thể cho biết ai đã thay đổi quyền nhưng không nhất thiết chứng minh được ai đã đọc từng object.

## 10. Danh sách kiểm tra khi thiết kế Cloud Audit Logs

Trước khi đưa một project hoặc workload vào sản xuất, hãy xác nhận:

- Admin Activity và System Event được giữ theo cơ chế mặc định của Google Cloud.
- Các dịch vụ chứa dữ liệu nhạy cảm đã được đánh giá và bật Data Access phù hợp.
- Đã phân biệt ADMIN_READ với Admin Activity, DATA_READ và DATA_WRITE.
- Các ngoại lệ exemptedMembers có lý do, chủ sở hữu và phê duyệt rõ ràng.
- Nhóm vận hành, bảo mật và kiểm toán có quyền đọc log đúng phạm vi; Data Access logs chỉ hiển thị cho principal được phép.
- Sink và log bucket tập trung có bộ lọc, quyền ghi, retention và vị trí lưu trữ phù hợp.
- Các truy vấn Logs Explorer quan trọng đã được thử nghiệm bằng dữ liệu thực tế.
- Quy trình điều tra kết hợp Audit Logs với log ứng dụng, cảnh báo và quản lý thay đổi.
- Chi phí và lượng Data Access logs được theo dõi định kỳ.

Cloud Audit Logs tạo nền tảng bằng chứng cho hoạt động trên Google Cloud. Khi chọn đúng loại log theo câu hỏi kiểm toán, bật Data Access ở nơi cần thiết, bảo vệ quyền đọc log và định tuyến dữ liệu đến nơi lưu trữ phù hợp, tổ chức có thể truy vết thay đổi và hoạt động truy cập đáng tin cậy hơn mà vẫn kiểm soát được chi phí vận hành.
