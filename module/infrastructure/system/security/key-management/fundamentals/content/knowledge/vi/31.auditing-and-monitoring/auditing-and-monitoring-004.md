# Key used event

Key used event là sự kiện ghi nhận một thao tác sử dụng khóa mật mã, chẳng hạn mã hóa, giải mã, ký, xác minh chữ ký, bọc hoặc mở khóa dữ liệu. Sự kiện giúp tổ chức trả lời các câu hỏi quan trọng: khóa nào đã được sử dụng, bởi danh tính nào, cho thao tác gì, vào thời điểm nào, request đến từ đâu và kết quả ra sao.

Trong quản lý khóa mật mã, vòng đời khóa không kết thúc ở việc tạo, lưu trữ và xoay vòng. Tổ chức còn phải biết khóa đang được sử dụng như thế nào để phát hiện truy cập trái phép, điều tra sự cố, kiểm tra việc tuân thủ policy và chứng minh các thao tác nhạy cảm có thể truy vết. Key used event là một phần của audit trail và monitoring, đặc biệt đối với khóa nằm trong KMS hoặc HSM.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích key used event và phân biệt nó với sự kiện quản trị khóa hoặc sự kiện nghiệp vụ của ứng dụng.
- Xác định các trường cần có trong một audit event về sử dụng khóa.
- Phân biệt thao tác encrypt, decrypt, sign, verify, wrap, unwrap và generate data key.
- Thiết kế luồng thu thập, chuẩn hóa, lưu trữ và bảo vệ sự kiện.
- Kết hợp sự kiện từ KMS/HSM với log ứng dụng và hệ thống định danh.
- Phát hiện mẫu sử dụng khóa bất thường và xây dựng cảnh báo có thể điều tra.
- Hiểu giới hạn của audit event khi ứng dụng cache DEK hoặc thực hiện mật mã ngoài KMS.

## 2. Key used event là gì?

Key used event là bản ghi mô tả một lần hoặc một yêu cầu sử dụng khóa. Trong hệ thống KMS, sự kiện thường được phát ra khi một API thao tác với khóa được gọi, ví dụ Encrypt, Decrypt, Sign, Verify hoặc GenerateDataKey. Trong HSM, sự kiện có thể được ghi tại thiết bị, partition, client library hoặc hệ thống quản lý HSM, tùy sản phẩm.

Ví dụ, dịch vụ Billing yêu cầu KMS giải mã một encrypted data key để đọc bản ghi hóa đơn. Một key used event có thể ghi nhận:

- Khóa hoặc phiên bản khóa được yêu cầu sử dụng.
- Principal đã xác thực, chẳng hạn workload identity của Billing.
- Thao tác là decrypt hoặc unwrap.
- Thời điểm, request ID và nguồn gọi.
- Context hoặc metadata được phép ghi nhận.
- Quyết định authorization và kết quả của thao tác.

Sự kiện không cần và không được chứa plaintext key material, secret xác thực hoặc dữ liệu nhạy cảm được giải mã. Mục tiêu là ghi lại bằng chứng về hoạt động của khóa mà không tạo thêm một nơi lưu trữ bí mật.

Một key used event có thể tương ứng với một API call, một lần xử lý mật mã hoặc một nhóm thao tác được nhà cung cấp tổng hợp. Cần hiểu chính xác ngữ nghĩa sự kiện của nền tảng đang dùng trước khi xây dựng metric hoặc cảnh báo dựa trên số lượng event.

## 3. Vì sao phải ghi nhận việc sử dụng khóa?

Không có dữ liệu sử dụng, tổ chức khó biết một khóa có còn cần thiết hay không, workload nào đang phụ thuộc vào nó và liệu khóa có bị dùng ngoài mục đích dự kiến hay không.

Key used event hỗ trợ các mục tiêu:

1. **Truy vết:** xác định principal, khóa, thao tác và thời điểm khi có sự cố.
2. **Phát hiện lạm dụng:** nhận diện decrypt hoặc sign tăng đột biến, nguồn gọi lạ hay thao tác ngoài giờ bất thường.
3. **Kiểm tra phân quyền:** đối chiếu hoạt động thực tế với role và policy được phê duyệt.
4. **Quản lý vòng đời:** tìm khóa không còn được dùng, consumer còn sử dụng version cũ hoặc khóa có tần suất sử dụng khác thường.
5. **Điều tra sự cố:** liên kết thao tác KMS với request ứng dụng, người dùng cuối và tài nguyên bị tác động.
6. **Kiểm toán:** cung cấp bằng chứng về việc sử dụng khóa và quyết định allow/deny.
7. **Vận hành:** theo dõi lỗi, độ trễ, quota và khả năng sẵn sàng của KMS/HSM.

Một event đơn lẻ hiếm khi chứng minh được hành vi là hợp lệ hay độc hại. Giá trị của nó tăng lên khi được kết hợp với danh tính, policy, trạng thái khóa, log ứng dụng và baseline sử dụng bình thường.

## 4. Phân biệt sự kiện sử dụng khóa với các loại sự kiện khác

Hệ thống quản lý khóa thường tạo ra nhiều nhóm sự kiện. Không nên gộp chúng thành một loại vì mỗi nhóm trả lời một câu hỏi khác nhau.

| Loại sự kiện | Ví dụ | Câu hỏi chính |
|---|---|---|
| Key lifecycle event | CreateKey, ImportKey, RotateKey, DisableKey, ScheduleDeletion | Khóa được tạo hoặc thay đổi trạng thái như thế nào? |
| Key used event | Encrypt, Decrypt, Sign, Verify, WrapKey, UnwrapKey | Ai đã yêu cầu sử dụng khóa và thao tác đó có kết quả gì? |
| Access control event | GrantRole, RevokeRole, SetKeyPolicy, DenyAccess | Ai đã thay đổi quyền truy cập? |
| Authentication event | Login, AssumeRole, WorkloadIdentityTokenIssued | Danh tính nào đã được xác thực hoặc cấp credential? |
| Application event | ReadInvoice, ApprovePayment, ExportReport | Ứng dụng đã thực hiện hành động nghiệp vụ nào? |
| Infrastructure event | HSM restart, KMS outage, policy deployment | Thành phần bảo vệ khóa có thay đổi hoặc gặp sự cố gì? |

Ví dụ, sự kiện Decrypt cho biết một thao tác giải mã đã được yêu cầu. Nó không tự chứng minh người dùng cuối có quyền đọc hóa đơn. Muốn hiểu hành động nghiệp vụ, cần liên kết event với request ID hoặc trace ID của ứng dụng và kiểm tra authorization tại tầng nghiệp vụ.

Ngược lại, log ứng dụng ghi “đã đọc hóa đơn” không đủ để chứng minh KMS đã thực hiện thao tác giải mã nào. Hai nguồn dữ liệu bổ sung cho nhau.

## 5. Các thao tác cần theo dõi

Những thao tác được ghi nhận phụ thuộc loại khóa, dịch vụ và API mà hệ thống cung cấp. Các nhóm thường gặp gồm:

| Thao tác | Ý nghĩa | Điều cần quan sát |
|---|---|---|
| Encrypt | Mã hóa plaintext bằng khóa hoặc dịch vụ quản lý khóa | Principal, key ID/version, số request, lỗi và nguồn gọi |
| Decrypt | Giải mã ciphertext | Phạm vi dữ liệu, principal, tần suất, lỗi và thời điểm |
| Sign | Tạo chữ ký số hoặc MAC | Khóa ký, thuật toán, workload và khối lượng ký |
| Verify | Xác minh chữ ký hoặc MAC | Nguồn gọi, kết quả xác minh và mẫu lỗi |
| WrapKey | Bọc DEK hoặc key material bằng KEK | Khóa bọc, loại vật liệu được bọc và context |
| UnwrapKey | Mở khóa dữ liệu đã được bọc | Principal, key version và mục đích giải bọc |
| GenerateDataKey | Sinh DEK, thường trả về plaintext DEK và bản mã hóa của nó | Key ID, encryption context, số lần sinh và caller |
| ReEncrypt | Chuyển ciphertext từ khóa hoặc context này sang khóa/context khác | Khóa nguồn, khóa đích, caller và kết quả |
| DeriveKey | Dẫn xuất khóa con từ khóa gốc hoặc secret | Thuật toán dẫn xuất, context và principal |

Một số nền tảng không phát ra event riêng cho tất cả thao tác hoặc có thể ghi nhận thao tác ở tên API khác. Hãy lập danh mục event type dựa trên tài liệu và cấu hình audit của nhà cung cấp.

Các thao tác nhạy cảm như Decrypt, UnwrapKey, Sign, Export hoặc thay đổi policy thường cần mức giám sát cao hơn. Tuy nhiên, Encrypt hoặc Verify cũng có thể bị lạm dụng để gây tiêu hao tài nguyên hoặc dò thông tin nếu API phản hồi khác nhau theo đầu vào.

## 6. Cấu trúc của một key used event

Một event hữu ích cần đủ thông tin để điều tra và tương quan, đồng thời giới hạn dữ liệu nhạy cảm. Có thể chia trường thành các nhóm:

| Nhóm | Trường ví dụ | Mục đích |
|---|---|---|
| Event identity | event_id, event_type, schema_version | Nhận diện, phân loại và xử lý phiên bản schema |
| Time | event_time, observed_time | Thời điểm thao tác và thời điểm hệ thống thu thập |
| Principal | principal_id, principal_type, session_id | Xác định người hoặc workload |
| Key | key_id, key_version, key_type, key_state | Xác định khóa được sử dụng |
| Operation | operation, algorithm, mode | Xác định thao tác và thuật toán |
| Resource | project, account, tenant, region | Xác định phạm vi tài nguyên |
| Request | request_id, trace_id, source_service | Liên kết với request ứng dụng |
| Network | source_ip, source_region, user_agent hoặc workload metadata | Điều tra nguồn gọi khi phù hợp |
| Authorization | decision, policy_id, role hoặc permission context | Giải thích quyết định truy cập |
| Outcome | result, error_code, latency_ms | Theo dõi kết quả và vận hành |
| Context | encryption_context hoặc context fingerprint | Phân biệt mục đích sử dụng mà không lộ dữ liệu |

Không phải nền tảng nào cũng cung cấp mọi trường. Không nên tự điền giá trị suy đoán nếu nguồn không ghi nhận; dùng null hoặc đánh dấu unavailable theo schema chuẩn hóa.

### 6.1. Event time và observed time

Event time là thời điểm thao tác xảy ra theo nguồn phát sự kiện. Observed time là thời điểm pipeline nhận được event. Hai thời điểm có thể khác nhau do độ trễ, retry, hàng đợi hoặc đồng hồ hệ thống lệch nhau.

Giữ cả hai trường giúp phát hiện event đến muộn, tính toán độ trễ thu thập và sắp xếp sự kiện trong điều tra. Hệ thống nên đồng bộ thời gian bằng nguồn đáng tin cậy và lưu múi giờ hoặc chuẩn UTC nhất quán.

### 6.2. Key ID và key version

Key ID xác định khóa logic. Key version xác định phiên bản vật liệu hoặc phiên bản vận hành cụ thể được sử dụng. Hai trường này rất quan trọng khi rotation: một key có thể có nhiều version, trong đó version cũ vẫn cần để giải mã dữ liệu đã mã hóa trước đây.

Nếu event chỉ ghi key ID, điều tra viên có thể không biết phiên bản nào đã xử lý request. Khi nền tảng cung cấp version ID, hãy lưu nó cùng trạng thái version tại thời điểm thao tác.

### 6.3. Principal và workload identity

Principal cần được ghi dưới dạng định danh ổn định, có thể liên kết với IAM hoặc identity provider. Tên hiển thị có thể thay đổi và không đủ để xác định duy nhất một danh tính.

Đối với workload, nên ghi service identity, service account hoặc workload principal. Nếu một dịch vụ dùng chung credential cho nhiều workload, audit event có thể chỉ nhận diện được credential chung; điều đó làm giảm khả năng quy trách nhiệm.

### 6.4. Authorization decision và outcome

Authorization decision cho biết policy engine có cho phép request hay không. Outcome cho biết thao tác thực tế thành công hay thất bại. Hai trường này không giống nhau:

- Deny: policy không cho phép thao tác.
- Allow nhưng operation failed: request vượt qua kiểm tra quyền nhưng thao tác thất bại do ciphertext sai định dạng, key version không khả dụng, quota hoặc lỗi dịch vụ.
- Allow và operation succeeded: thao tác được phép và hoàn thành.

Giữ riêng decision và outcome giúp phân biệt vấn đề bảo mật với vấn đề vận hành.

## 7. Ví dụ event schema

Một bản ghi minh họa có thể ở dạng JSON:

~~~json
{
  "event_id": "evt-7f2a91",
  "schema_version": "1.0",
  "event_type": "kms.key.used",
  "event_time": "2026-11-28T03:15:22.481Z",
  "observed_time": "2026-11-28T03:15:23.017Z",
  "principal": {
    "id": "workload:billing-api-prod",
    "type": "workload"
  },
  "key": {
    "id": "key/billing-data-kek",
    "version": "v12",
    "purpose": "encryption"
  },
  "operation": {
    "name": "Decrypt",
    "algorithm": "AES-256-GCM"
  },
  "resource": {
    "project": "billing-prod",
    "region": "asia-southeast1"
  },
  "request": {
    "id": "req-91c4",
    "trace_id": "trace-6d20",
    "source_service": "invoice-reader"
  },
  "authorization": {
    "decision": "allow",
    "policy_id": "billing-decrypt-policy"
  },
  "outcome": {
    "result": "success",
    "latency_ms": 18
  }
}
~~~

Đây là schema minh họa, không phải định dạng chuẩn của một nhà cung cấp cụ thể. Giá trị ID cũng chỉ là dữ liệu ví dụ. Trong hệ thống thực tế, schema cần có quy tắc rõ ràng cho trường bắt buộc, trường tùy chọn, giá trị không có sẵn và phiên bản tương thích.

Không đưa ciphertext, plaintext, khóa, access token, client secret hoặc toàn bộ request payload vào event chỉ để làm giàu dữ liệu điều tra. Nếu cần liên kết với dữ liệu nghiệp vụ, dùng request ID, resource ID hoặc fingerprint được thiết kế an toàn.

## 8. Encryption context và dữ liệu nhạy cảm

Encryption context là tập thuộc tính bổ sung được dùng trong một số hệ thống mã hóa để ràng buộc thao tác với ngữ cảnh, ví dụ tenant, record type hoặc data domain. Context có thể xuất hiện trong audit event và giúp điều tra vì nó cho biết mục đích hoặc miền dữ liệu của thao tác.

Context thường không phải bí mật và trong một số API được cung cấp dưới dạng plaintext. Do đó, không đưa thông tin nhạy cảm như tên khách hàng, số tài khoản, email, dữ liệu cá nhân hoặc nội dung nghiệp vụ trực tiếp vào context nếu không cần thiết.

Nên ưu tiên các mã định danh không nhạy cảm, giá trị phân loại hoặc fingerprint có kiểm soát. Nếu context chứa giá trị do client tự cung cấp, phải xem nó là dữ liệu không đáng tin cậy cho đến khi được xác thực và chuẩn hóa.

Encryption context cũng không tự thay thế authorization. Một context có giá trị tenant hợp lệ không chứng minh principal được phép truy cập tenant đó. Policy phải xác minh mối quan hệ giữa principal, resource và context.

## 9. Nguồn phát sự kiện và mức độ tin cậy

Các nguồn có thể tạo key used event:

- **KMS control plane hoặc data plane:** ghi lại API request sử dụng khóa, principal, resource và kết quả ở phía dịch vụ quản lý khóa.
- **HSM audit facility:** ghi nhận thao tác trong thiết bị hoặc partition theo khả năng của nhà cung cấp.
- **Client library hoặc SDK:** ghi log ứng dụng khi gọi KMS/HSM.
- **API gateway hoặc service mesh:** ghi nhận request đi qua lớp trung gian.
- **Ứng dụng nghiệp vụ:** ghi lại lý do nghiệp vụ, người dùng cuối và request/trace ID.

Event do KMS/HSM phát ra thường là bằng chứng quan trọng về thao tác mà dịch vụ quản lý khóa đã nhận hoặc xử lý. Log ứng dụng cung cấp thêm ngữ cảnh nghiệp vụ. Không nên coi log do client tự ghi là nguồn duy nhất để chứng minh khóa đã được sử dụng; một ứng dụng bị xâm nhập có thể sửa hoặc bỏ qua log của chính nó.

Ngược lại, KMS event có thể không chứa đầy đủ người dùng cuối hoặc mục đích nghiệp vụ. Hãy kết hợp các nguồn bằng request ID, trace ID, principal ID và resource ID.

## 10. Luồng thu thập và xử lý sự kiện

Một pipeline audit có thể gồm các bước:

1. **Phát sinh:** KMS/HSM tạo event khi thao tác được gọi hoặc hoàn tất.
2. **Chuyển tiếp:** dịch vụ audit, event stream hoặc agent gửi event đến vùng thu thập.
3. **Xác minh nguồn:** kiểm tra danh tính nguồn, chữ ký hoặc cơ chế bảo vệ kênh theo khả năng nền tảng.
4. **Chuẩn hóa:** ánh xạ event vào schema chung, chuẩn hóa timestamp, operation, principal và key ID.
5. **Làm giàu có kiểm soát:** liên kết owner, service, environment, policy và thông tin CMDB cần thiết.
6. **Lưu trữ:** ghi vào kho audit có kiểm soát truy cập, bảo vệ toàn vẹn và retention phù hợp.
7. **Phân tích:** tạo metric, baseline, rule phát hiện và cảnh báo.
8. **Điều tra:** liên kết event với log ứng dụng, identity provider, change record và incident.

~~~mermaid
flowchart TD
    A[KMS hoặc HSM] --> B[Audit event source]
    C[Application logs] --> D[Event collector]
    B --> D
    D --> E[Verify and normalize]
    E --> F[Protected audit storage]
    E --> G[Metrics and detection]
    G --> H[Alert and investigation]
    F --> H
    H --> I[Incident response]
~~~

Pipeline cần được giám sát như một dịch vụ bảo mật. Nếu nguồn event ngừng gửi, hàng đợi bị nghẽn hoặc collector mất kết nối, tổ chức có thể mất khả năng quan sát mà không biết. Cần theo dõi heartbeat, event volume, ingestion lag, dropped event và lỗi xác minh nguồn.

## 11. Bảo đảm tính toàn vẹn và độ tin cậy của audit log

Audit log chỉ có giá trị khi có thể tin rằng event không bị sửa hoặc xóa trái phép. Các biện pháp phù hợp có thể gồm:

- Gửi event trực tiếp từ dịch vụ KMS/HSM đến tài khoản hoặc vùng audit riêng.
- Giới hạn quyền ghi và đọc theo nguyên tắc least privilege.
- Tách quyền quản trị khóa khỏi quyền quản trị kho audit.
- Dùng storage có retention lock, immutability hoặc cơ chế WORM khi yêu cầu phù hợp.
- Bật versioning và kiểm soát xóa đối với kho lưu trữ nếu nền tảng hỗ trợ.
- Bảo vệ kênh truyền, xác thực nguồn phát và kiểm tra chữ ký hoặc checksum khi có.
- Theo dõi thay đổi cấu hình audit, subscription, sink, retention và quyền truy cập.
- Sao lưu và kiểm tra khả năng khôi phục dữ liệu audit.

Hash chain hoặc chữ ký số có thể hỗ trợ phát hiện thay đổi nếu được triển khai đúng, nhưng không tự giải quyết việc kẻ tấn công xóa toàn bộ chuỗi hoặc chiếm quyền khóa ký. Cần bảo vệ cả dữ liệu, khóa xác minh, checkpoint và quyền quản trị.

Nên lưu event gốc hoặc giữ được khả năng truy xuất bản gốc từ nguồn đáng tin cậy. Khi chuẩn hóa hoặc làm giàu, tránh ghi đè dữ liệu gốc; hãy lưu trường đã chuẩn hóa riêng và giữ thông tin nguồn, thời điểm nhận cùng schema version.

## 12. Xử lý event trùng, đến muộn và mất thứ tự

Pipeline phân tán có thể giao event nhiều lần, đến trễ hoặc không theo thứ tự thời gian phát sinh. Điều này thường xảy ra khi có retry, queue, mạng gián đoạn hoặc nhiều vùng xử lý.

Thiết kế xử lý nên:

- Dùng event ID ổn định để loại bỏ bản ghi trùng khi tổng hợp.
- Giữ event time và observed time riêng biệt.
- Không giả định thứ tự đến là thứ tự thao tác.
- Dùng cửa sổ thời gian và watermark khi tính metric hoặc phát hiện chuỗi hành động.
- Có cơ chế phát hiện gap, sequence discontinuity hoặc nguồn ngừng gửi nếu nền tảng hỗ trợ.
- Giữ raw event để có thể xử lý lại khi parser hoặc schema mapping có lỗi.

Không nên loại bỏ event chỉ vì nó đến muộn. Một event Decrypt đến muộn có thể là bằng chứng quan trọng trong điều tra, dù nó không còn phù hợp với dashboard thời gian thực.

## 13. Theo dõi baseline sử dụng khóa

Baseline mô tả hành vi sử dụng thông thường của khóa hoặc workload trong một khoảng thời gian. Baseline có thể dựa trên:

- Số request theo key ID, principal, operation và environment.
- Tỷ lệ Encrypt/Decrypt/Sign/Verify.
- Phân bố thời gian trong ngày và ngày trong tuần.
- Nguồn gọi, vùng địa lý, service identity hoặc network zone.
- Latency, error rate và quota consumption.
- Key version được sử dụng và thời điểm chuyển version.
- Encryption context hoặc data domain đã chuẩn hóa.

Ví dụ, workload invoice-reader-prod thường gọi Decrypt với lưu lượng ổn định vào giờ làm việc. Một đợt tăng gấp nhiều lần trong thời gian ngắn, nhất là từ một principal hoặc vùng mới, cần được kiểm tra.

Baseline không nên là một con số cố định cho mọi hệ thống. Lưu lượng có thể thay đổi theo mùa, batch job, ngày chốt sổ hoặc đợt migration. Nên kết hợp ngưỡng thống kê, lịch vận hành và thông tin change management để giảm cảnh báo sai.

## 14. Phát hiện hoạt động bất thường

Một số mẫu đáng theo dõi:

### 14.1. Decrypt tăng đột biến

Một principal thực hiện số lượng Decrypt cao bất thường có thể đang đọc dữ liệu hàng loạt, xử lý batch hợp lệ hoặc bị lạm dụng. Cần so sánh với baseline, job schedule, tenant, key version và log nghiệp vụ.

### 14.2. Sử dụng khóa từ danh tính hoặc nguồn lạ

Một key production được gọi bởi workload chưa đăng ký, service account mới hoặc nguồn mạng ngoài vùng dự kiến có thể cho thấy credential bị lộ hoặc policy bị mở rộng sai.

### 14.3. Truy cập version cũ

Sau rotation, việc tiếp tục sử dụng version cũ có thể hợp lệ khi giải mã dữ liệu lịch sử. Tuy nhiên, nếu workload mã hóa mới vẫn dùng version cũ sau thời điểm cutover, cần kiểm tra cấu hình và quá trình triển khai.

### 14.4. Sign bất thường

Tần suất ký tăng đột ngột, signer mới hoặc request ký ngoài luồng phát hành dự kiến có thể ảnh hưởng đến tính xác thực của token, artifact hoặc giao dịch. Cần liên kết với hệ thống phát hành chữ ký và change record.

### 14.5. Thao tác nhạy cảm ngoài lịch thay đổi

Disable, export, import, rotate hoặc thay policy có thể làm gián đoạn hoặc thay đổi mức bảo vệ. Nếu event không gắn với ticket hoặc phê duyệt tương ứng, cần xác minh.

### 14.6. Mẫu lỗi xác thực và authorization

Nhiều request bị deny liên tiếp, lỗi xác thực từ một principal hoặc thử gọi nhiều key ID có thể là dấu hiệu dò quyền hoặc cấu hình sai. Không nên tự động kết luận là tấn công; đối chiếu với rollout, thay đổi IAM và lỗi ứng dụng.

### 14.7. Khoảng trống telemetry

Event volume về 0, heartbeat mất, ingestion lag tăng hoặc subscription bị tắt có thể cho thấy pipeline giám sát bị hỏng hoặc bị can thiệp. Đây là một tín hiệu bảo mật cần cảnh báo riêng.

## 15. Xây dựng rule và cảnh báo

Một cảnh báo hữu ích cần xác định rõ điều kiện, mức độ nghiêm trọng, owner và hành động tiếp theo. Ví dụ:

| Rule | Điều kiện gợi ý | Mức ưu tiên | Hành động ban đầu |
|---|---|---|---|
| Decrypt spike | Số Decrypt vượt baseline theo principal và key trong cửa sổ ngắn | Cao | Xác minh batch/job, principal, tenant và nguồn gọi |
| Unknown principal | Key nhạy cảm được gọi bởi principal ngoài inventory được duyệt | Cao | Kiểm tra role binding và identity credential |
| Unexpected key version | Workload mã hóa mới tiếp tục dùng version cũ sau cutover | Trung bình | Kiểm tra cấu hình, cache và rollout |
| Unusual signing | Sign tăng mạnh hoặc phát sinh từ service không phải signer dự kiến | Cao | Kiểm tra token/artifact được ký và nguồn request |
| Policy change without change record | Thay policy hoặc role binding không liên kết change ticket | Cao | Xác minh người thực hiện và khôi phục policy nếu cần |
| Audit pipeline gap | Heartbeat mất, event volume bất thường hoặc ingestion lag vượt ngưỡng | Cao | Kiểm tra nguồn event, collector, queue và quyền cấu hình |
| Repeated denied operations | Nhiều lần deny trên cùng principal hoặc nhiều key | Trung bình/Cao | Phân biệt lỗi cấu hình với hành vi dò quyền |

Ngưỡng trong rule cần được hiệu chỉnh theo tải thực tế. Cảnh báo nên có đường dẫn đến event liên quan, dashboard, owner và runbook. Tránh tạo alert chỉ có một con số mà không có đủ ngữ cảnh để xử lý.

## 16. Tương quan KMS event với log ứng dụng

KMS event thường xác định được principal và key nhưng có thể không biết người dùng cuối, bản ghi nghiệp vụ hoặc lý do đọc dữ liệu. Log ứng dụng thường có thông tin nghiệp vụ nhưng có thể không biết chính xác key version hay thao tác KMS đã xảy ra.

Để liên kết hai nguồn:

1. Tạo request ID hoặc trace ID tại biên nhận request.
2. Truyền ID qua các service call và metadata hỗ trợ của KMS nếu được phép.
3. Ghi request ID, trace ID, service identity và resource ID trong log ứng dụng.
4. Giữ các ID tương ứng trong event KMS nếu API hoặc provider hỗ trợ.
5. Đồng bộ thời gian và chuẩn hóa định dạng ID.
6. Khi điều tra, nối event theo ID trước; chỉ dùng khoảng thời gian và principal làm điều kiện phụ khi thiếu ID.

Không nhồi dữ liệu cá nhân hoặc nội dung nghiệp vụ vào encryption context chỉ để có thể tương quan. Request ID ngẫu nhiên hoặc opaque thường phù hợp hơn.

## 17. Giới hạn quan sát khi dùng envelope encryption và cache

Một điểm dễ hiểu nhầm là mỗi lần ứng dụng mã hóa dữ liệu đều tạo ra một key used event ở KMS. Điều này không phải lúc nào cũng đúng.

Trong envelope encryption, ứng dụng có thể gọi KMS để tạo DEK hoặc mở một encrypted DEK, sau đó sử dụng plaintext DEK trong bộ nhớ để mã hóa nhiều bản ghi cục bộ. Nếu DEK được cache, KMS chỉ ghi nhận các lần GenerateDataKey, Decrypt hoặc UnwrapKey thực sự được gọi. Các phép AES-GCM thực hiện cục bộ có thể không tạo event tại KMS.

Do đó:

- KMS event cho biết các lần gọi dịch vụ quản lý khóa.
- Application telemetry có thể ghi nhận số thao tác mã hóa dữ liệu thực tế bằng DEK trong tiến trình.
- HSM audit có thể ghi nhận thao tác xảy ra trong HSM nếu khóa và thuật toán được thực hiện trong thiết bị.
- Cache lifetime và số lượng dữ liệu xử lý bằng một DEK cần được quản lý theo chính sách mật mã của hệ thống.

Nếu chỉ dùng KMS event để đếm số bản ghi được mã hóa hoặc giải mã, báo cáo có thể thấp hơn thực tế. Hãy ghi rõ metric đo số lần gọi KMS hay số phép mật mã ở ứng dụng.

## 18. Bảo vệ dữ liệu trong event và quyền truy cập audit

Audit event có thể tiết lộ kiến trúc, tên dịch vụ, danh tính workload, thời điểm truy cập, tần suất xử lý và quan hệ giữa các tenant. Dù không chứa key material, đây vẫn là dữ liệu nhạy cảm.

Áp dụng các biện pháp:

- Chỉ thu thập trường cần thiết cho audit và monitoring.
- Che hoặc loại bỏ secret, token, plaintext, ciphertext không cần thiết và dữ liệu cá nhân.
- Giới hạn người đọc event theo vai trò; ứng dụng nghiệp vụ không cần quyền đọc toàn bộ audit log.
- Tách quyền xem log khỏi quyền sửa retention, xóa hoặc thay đổi pipeline.
- Mã hóa dữ liệu audit khi lưu và khi truyền.
- Theo dõi việc truy cập, xuất và thay đổi cấu hình kho audit.
- Đặt retention theo yêu cầu pháp lý, hợp đồng, điều tra và chính sách nội bộ.
- Xóa hoặc ẩn danh dữ liệu khi hết thời hạn lưu trữ và được phép theo chính sách.

Auditor cần đủ dữ liệu để kiểm tra nhưng không mặc nhiên cần quyền truy cập plaintext hoặc quyền sử dụng khóa. Người quản trị kho log cũng không nên có quyền thay đổi policy của khóa chỉ vì họ quản lý dữ liệu audit.

## 19. Điều tra một key used event

Khi một event đáng ngờ xuất hiện, có thể điều tra theo trình tự:

1. Xác minh event đến từ nguồn đáng tin cậy và kiểm tra event ID, event time, observed time.
2. Xác định key ID, key version, operation, principal và resource scope.
3. Kiểm tra authorization decision, policy ID, role binding và thay đổi quyền gần thời điểm đó.
4. Tra cứu workload owner, deployment, identity session và nguồn mạng.
5. Tương quan request ID hoặc trace ID với log ứng dụng, API gateway và hệ thống nghiệp vụ.
6. So sánh tần suất, thời gian, tenant và operation với baseline.
7. Kiểm tra change ticket, batch schedule, migration hoặc hoạt động vận hành hợp lệ.
8. Xác định dữ liệu hoặc chức năng có thể bị ảnh hưởng; không suy luận phạm vi chỉ từ số event.
9. Nếu có dấu hiệu lạm dụng, phối hợp quy trình incident response để giới hạn quyền, thu hồi credential hoặc vô hiệu hóa khóa theo đánh giá tác động.
10. Bảo toàn event gốc, ghi lại quyết định và kết quả điều tra.

Không xóa hoặc sửa event đáng ngờ trong quá trình điều tra. Ghi chú phân tích nên nằm ở hệ thống case management riêng và liên kết với event ID.

## 20. Ví dụ: điều tra một đợt Decrypt bất thường

Một cảnh báo cho biết key customer-record-kek-prod có lượng Decrypt tăng gấp mười lần baseline trong mười phút.

Nhóm vận hành thực hiện:

1. Nhóm theo key ID, key version và principal để xác định workload tạo ra phần tăng.
2. Đối chiếu principal với inventory; phát hiện request đến từ report-export-prod.
3. Tra cứu trace ID và log ứng dụng; thấy một job xuất báo cáo vừa được triển khai.
4. Kiểm tra change ticket và xác nhận job mới được phê duyệt nhưng cấu hình phân trang bị lỗi, khiến cùng dữ liệu được đọc lặp lại.
5. Tạm dừng job, xác minh không có truy cập ngoài tenant được phép và kiểm tra các thao tác đã hoàn tất.
6. Sửa lỗi, chạy lại với giới hạn batch, sau đó theo dõi metric để xác nhận lưu lượng trở về baseline.
7. Ghi nhận nguyên nhân, phạm vi, quyết định xử lý và thay đổi rule để phân biệt batch đã được phê duyệt với hành vi bất thường trong tương lai.

Nếu điều tra cho thấy principal không được nhận diện hoặc có dấu hiệu credential bị lộ, phản ứng cần chuyển sang quy trình sự cố bảo mật: giới hạn hoặc thu hồi quyền, bảo toàn log và đánh giá dữ liệu bị ảnh hưởng.

## 21. Chỉ số vận hành cho audit pipeline

Ngoài metric về thao tác khóa, cần theo dõi sức khỏe của pipeline:

| Chỉ số | Ý nghĩa | Dấu hiệu cần xử lý |
|---|---|---|
| Event ingestion rate | Số event nhận được theo thời gian | Đột ngột về 0 hoặc tăng bất thường |
| Ingestion lag | Độ trễ từ event time đến observed time | Tăng vượt mục tiêu vận hành |
| Dropped / rejected events | Event bị mất hoặc không hợp lệ | Tăng liên tục hoặc có nguồn bị loại |
| Duplicate rate | Tỷ lệ event trùng | Tăng mạnh sau retry hoặc thay đổi queue |
| Source heartbeat | Nguồn phát event còn hoạt động | Mất heartbeat hoặc không có event dự kiến |
| Parse failure rate | Tỷ lệ event không chuẩn hóa được | Tăng sau khi provider đổi schema |
| Storage write failure | Lỗi ghi vào kho audit | Có nguy cơ mất bằng chứng |
| Alert delivery latency | Thời gian từ event đến cảnh báo | Cảnh báo đến quá muộn để phản ứng |

Đặt mục tiêu về độ trễ và độ đầy đủ dựa trên mức độ quan trọng của hệ thống. Cần có runbook cho trường hợp pipeline không hoạt động, vì khoảng trống audit có thể che giấu hoạt động sử dụng khóa.

## 22. Checklist triển khai Key used event

- [ ] Đã xác định các thao tác sử dụng khóa cần audit ở KMS/HSM.
- [ ] Đã hiểu event type và giới hạn telemetry của nhà cung cấp.
- [ ] Event có event ID, event time, observed time và schema version.
- [ ] Event xác định được principal, key ID, key version và operation khi nguồn cung cấp.
- [ ] Có authorization decision và operation outcome riêng biệt.
- [ ] Có request ID hoặc trace ID để liên kết với ứng dụng.
- [ ] Không ghi key material, secret, token, plaintext hoặc dữ liệu nghiệp vụ không cần thiết.
- [ ] Encryption context và metadata đã được rà soát về dữ liệu nhạy cảm.
- [ ] Event gốc được bảo toàn và pipeline có xác minh nguồn.
- [ ] Kho audit có kiểm soát quyền, mã hóa, retention và bảo vệ toàn vẹn.
- [ ] Có xử lý event trùng, đến muộn, mất thứ tự và lỗi schema.
- [ ] Có baseline theo principal, key, operation và môi trường.
- [ ] Có rule cho Decrypt spike, principal lạ, Sign bất thường và khoảng trống telemetry.
- [ ] Có tương quan với log ứng dụng, IAM và change management.
- [ ] Có dashboard và runbook để điều tra cảnh báo.
- [ ] Đã phân biệt số lần gọi KMS với số phép mật mã thực hiện cục bộ bằng DEK cache.
- [ ] Có kiểm tra định kỳ khả năng thu thập và khôi phục audit log.

## Kết luận

Key used event ghi lại bằng chứng về việc khóa được yêu cầu sử dụng cho thao tác nào, bởi danh tính nào, trên tài nguyên nào và với kết quả ra sao. Sự kiện này hỗ trợ truy vết, kiểm toán, phát hiện lạm dụng và quản lý vòng đời khóa. Một hệ thống audit tốt cần schema nhất quán, event time đáng tin cậy, key ID và version, principal, operation, authorization decision, outcome cùng request ID để tương quan. Event phải được thu thập từ nguồn đáng tin cậy, bảo vệ toàn vẹn, giới hạn dữ liệu nhạy cảm và lưu theo retention phù hợp. Khi phân tích, cần kết hợp KMS/HSM event với log ứng dụng và identity telemetry, đồng thời hiểu rằng DEK cache có thể khiến nhiều phép mã hóa cục bộ không tạo ra một event KMS cho mỗi lần sử dụng dữ liệu.
