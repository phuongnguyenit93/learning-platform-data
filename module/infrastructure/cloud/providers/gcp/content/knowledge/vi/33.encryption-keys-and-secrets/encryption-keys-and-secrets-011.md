# Cloud KMS audit logs và theo dõi sử dụng khóa

Trong module `CLOUD_PROVIDERS_GCP`, bạn khám phá Google Cloud từ tổ chức, project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Các tình huống triển khai giúp bạn lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong chương **Khóa mã hóa và bí mật**, Cloud Key Management Service (Cloud KMS) cung cấp nơi quản lý khóa mã hóa tập trung; Cloud Audit Logs cung cấp bằng chứng để biết ai đã gọi API quản trị hoặc sử dụng khóa, vào thời điểm nào và trên tài nguyên nào.

Bài học này tập trung vào cách bật, truy vấn và giám sát audit logs của Cloud KMS. Mục tiêu là phát hiện thay đổi cấu hình trái phép, nhận biết danh tính đang sử dụng khóa, điều tra các lần giải mã bất thường và lưu giữ bằng chứng phục vụ vận hành hoặc kiểm toán.

## 1. Vì sao cần theo dõi hoạt động của khóa?

Một khóa KMS có thể được nhiều workload sử dụng: ứng dụng gọi `Encrypt` hoặc `Decrypt`, dịch vụ Google Cloud dùng khóa do khách hàng quản lý (CMEK), hay một pipeline ký dữ liệu bằng khóa bất đối xứng. Nếu chỉ theo dõi trạng thái khóa trong Cloud KMS, người vận hành biết khóa đang bật, đã xoay vòng hay đã bị vô hiệu hóa, nhưng chưa đủ thông tin để trả lời những câu hỏi như:

- Danh tính hoặc service account nào đã gọi thao tác giải mã?
- Khóa nào được sử dụng, API nào được gọi và lời gọi xảy ra lúc nào?
- Ai đã thay đổi IAM policy, đổi phiên bản khóa chính hoặc yêu cầu hủy một phiên bản?
- Một thao tác có bị từ chối hay thất bại không?
- Lưu lượng sử dụng khóa có tăng đột biến so với hoạt động bình thường không?

Cloud Audit Logs ghi lại hoạt động API mà Google Cloud hỗ trợ audit. Với Cloud KMS, log thường cho biết phương thức API, tài nguyên, danh tính gọi và kết quả. Log không phải bản sao dữ liệu ứng dụng: bạn không dùng nó để đọc plaintext đã mã hóa hoặc trích xuất vật liệu khóa bí mật. Để hiểu đầy đủ một sự kiện, hãy kết hợp audit log với log của ứng dụng, workload và các hệ thống liên quan.

## 2. Các loại Cloud Audit Logs liên quan đến Cloud KMS

Cloud Audit Logs có bốn loại. Chúng trả lời những câu hỏi khác nhau:

| Loại log | Nội dung | Trạng thái mặc định |
| --- | --- | --- |
| **Admin Activity** | Thao tác do người dùng hoặc workload thực hiện để tạo, cập nhật, xóa tài nguyên hay thay đổi cấu hình và quyền truy cập. | Luôn được ghi; không thể tắt hoặc loại trừ. |
| **Data Access** | Lời gọi đọc metadata/cấu hình hoặc truy cập dữ liệu do người dùng cung cấp. | Thường tắt mặc định, ngoại trừ một số dịch vụ BigQuery; cần bật rõ ràng. |
| **System Event** | Thay đổi được thực hiện bởi hệ thống Google Cloud hoặc service agent được quản lý. | Luôn được ghi. |
| **Policy Denied** | Lần truy cập bị từ chối do vi phạm chính sách bảo mật. | Mặc định được tạo; không thể tắt, nhưng có thể dùng exclusion filter để ngăn lưu trong Cloud Logging. |

Điểm cần nhớ khi làm việc với Cloud KMS là **việc sử dụng khóa thường nằm trong Data Access logs**. Nếu chỉ xem Admin Activity, bạn có thể thấy ai tạo hoặc thay đổi khóa nhưng không thấy đầy đủ các lời gọi `Encrypt`, `Decrypt` hay ký dữ liệu.

### 2.1. Admin Activity: thay đổi cấu hình và vòng đời khóa

Các thao tác quản trị cần quyền IAM loại `ADMIN_WRITE` tạo Admin Activity audit log. Ví dụ:

| Phương thức Cloud KMS | Ý nghĩa vận hành |
| --- | --- |
| `CreateKeyRing`, `CreateCryptoKey` | Tạo key ring hoặc crypto key. |
| `UpdateCryptoKey` | Thay đổi cấu hình của khóa, chẳng hạn cấu hình luân chuyển tự động. |
| `UpdateCryptoKeyPrimaryVersion` | Chuyển phiên bản chính của khóa sang phiên bản khác. |
| `CreateCryptoKeyVersion`, `UpdateCryptoKeyVersion` | Tạo hoặc cập nhật phiên bản khóa. |
| `DestroyCryptoKeyVersion`, `RestoreCryptoKeyVersion` | Hủy hoặc khôi phục một phiên bản khóa theo trạng thái vòng đời cho phép. |
| `SetIamPolicy` | Thay đổi quyền IAM trên key ring hoặc crypto key. |

Những log này giúp điều tra các thay đổi có thể ảnh hưởng đến khả năng bảo vệ dữ liệu. Chẳng hạn, một lần `SetIamPolicy` bất ngờ có thể cấp quyền sử dụng khóa cho service account mới; một lần `UpdateCryptoKeyPrimaryVersion` có thể liên quan đến kế hoạch xoay vòng hoặc sự cố vận hành.

### 2.2. Data Access: đọc thông tin và sử dụng khóa

Cloud KMS phân loại phương thức dựa trên loại quyền IAM mà phương thức kiểm tra. Quyền `ADMIN_READ`, `DATA_READ` và `DATA_WRITE` tạo Data Access audit logs; quyền `ADMIN_WRITE` tạo Admin Activity audit logs. Vì vậy, một số thao tác đọc metadata như `GetCryptoKey`, `GetCryptoKeyVersion`, `ListCryptoKeys` cũng thuộc Data Access, dù chúng không trực tiếp mã hóa dữ liệu.

Các phương thức sử dụng khóa thường gặp gồm:

| Phương thức | Mục đích | Loại log |
| --- | --- | --- |
| `Encrypt`, `RawEncrypt` | Mã hóa dữ liệu bằng khóa đối xứng. | Data Access (`DATA_READ`) |
| `Decrypt`, `RawDecrypt` | Giải mã dữ liệu. | Data Access (`DATA_READ`) |
| `AsymmetricSign` | Tạo chữ ký bằng khóa riêng bất đối xứng. | Data Access (`DATA_READ`) |
| `AsymmetricDecrypt` | Giải mã bằng khóa riêng bất đối xứng. | Data Access (`DATA_READ`) |
| `MacSign`, `MacVerify` | Tạo hoặc xác minh mã xác thực thông điệp (MAC). | Data Access (`DATA_READ`) |
| `GetPublicKey` | Lấy khóa công khai tương ứng với phiên bản khóa bất đối xứng. | Data Access (`DATA_READ`) |
| `GetCryptoKey`, `GetCryptoKeyVersion`, `ListCryptoKeys` | Đọc metadata hoặc liệt kê khóa và phiên bản. | Data Access (`ADMIN_READ`) |

Tên loại quyền trong bảng phản ánh phân loại IAM của API Cloud KMS; đừng suy luận rằng mọi phương thức `DATA_READ` đều trả dữ liệu plaintext cho caller. Ví dụ, `Encrypt` và `Decrypt` được ghi nhận theo phân loại quyền mà Cloud KMS quy định cho các phương thức đó.

**Lưu ý:** `GenerateRandomBytes` là một phương thức Cloud KMS không tạo audit log. Không nên coi việc không tìm thấy log của phương thức này là bằng chứng rằng API chưa được gọi. Danh sách phương thức có audit log có thể thay đổi theo API; hãy đối chiếu tài liệu audit logging của Cloud KMS khi thiết kế kiểm soát.

## 3. Bật Data Access audit logs cho Cloud KMS

Admin Activity được ghi tự động. Để theo dõi việc sử dụng khóa và các thao tác đọc metadata, bạn cần bật Data Access logs cho dịch vụ Cloud Key Management Service.

### 3.1. Cấu hình trong Google Cloud Console

1. Mở Google Cloud Console và chọn đúng organization, folder hoặc project cần cấu hình.
2. Mở **IAM & Admin → Audit Logs**.
3. Tìm dịch vụ **Cloud Key Management Service** (`cloudkms.googleapis.com`).
4. Bật các loại Data Access phù hợp với mục tiêu giám sát:
   - **Admin Read** để ghi nhận các thao tác đọc metadata/cấu hình như lấy thông tin khóa hoặc liệt kê phiên bản.
   - **Data Read** để ghi nhận các thao tác sử dụng khóa như mã hóa, giải mã, ký hoặc xác minh.
   - **Data Write** nếu các API Cloud KMS trong phạm vi của bạn kiểm tra quyền loại này.
5. Lưu cấu hình và thực hiện một thao tác thử nghiệm được cho phép để xác minh log xuất hiện.

Bạn có thể bật cấu hình ở cấp organization, folder hoặc project. Cấu hình được kế thừa từ cấp cha áp dụng cho các project con; project không thể tắt một loại Data Access log đã được bật ở organization hoặc folder cha. Khi thay đổi cấu hình ở cấp project, hãy kiểm tra chính sách kế thừa để hiểu phạm vi thực tế.

### 3.2. Cấu hình qua IAM AuditConfig

Trong IAM policy, cấu hình audit cho Cloud KMS có dạng như sau:

```json
{
  "auditConfigs": [
    {
      "service": "cloudkms.googleapis.com",
      "auditLogConfigs": [
        { "logType": "ADMIN_READ" },
        { "logType": "DATA_READ" },
        { "logType": "DATA_WRITE" }
      ]
    }
  ]
}
```

Đây là phần cấu hình minh họa để ghép vào IAM policy hiện có. Khi cập nhật policy bằng API hoặc công cụ dòng lệnh, hãy đọc policy hiện tại và giữ lại các `auditConfigs`, bindings cùng cấu hình khác đang tồn tại. Không thay toàn bộ IAM policy bằng riêng đoạn JSON minh họa này vì có thể vô tình làm mất quyền hoặc cấu hình audit của dịch vụ khác.

### 3.3. Quyền xem log

Quyền cấu hình audit log và quyền đọc log là hai việc riêng. Để đọc Admin Activity, System Event và Policy Denied logs, người vận hành thường cần `roles/logging.viewer`. Để đọc cả Data Access logs trong bucket `_Default`, cần quyền bao gồm `logging.privateLogEntries.list`; predefined role phù hợp là **Private Logs Viewer** (`roles/logging.privateLogViewer`). Role này bao gồm các quyền của Logs Viewer và quyền đọc Data Access logs. Role Editor (`roles/editor`) không tự động cấp quyền cần thiết để đọc Data Access logs.

Hãy cấp quyền đọc log theo nguyên tắc tối thiểu. Audit logs có thể tiết lộ danh tính, tên tài nguyên, địa chỉ IP caller và thông tin vận hành nhạy cảm; không nên cấp quyền xem rộng hơn nhu cầu công việc.

### 3.4. Dự trù dung lượng và chi phí

Data Access logs có thể tạo ra lượng log lớn và phát sinh chi phí Cloud Logging. Một hệ thống sử dụng CMEK có thể tạo log cho nhiều lần thao tác khóa từ các dịch vụ và service agent. Trước khi bật trên toàn organization, hãy xác định câu hỏi kiểm toán cần trả lời, ước lượng lưu lượng, kiểm tra chi phí ingest/lưu trữ và quyết định nơi lưu giữ log.

Với môi trường cần giám sát toàn diện, có thể bật Data Access ở phạm vi rộng và định tuyến log đến nơi lưu trữ tập trung. Với môi trường có lưu lượng lớn, cần xác định rõ loại quyền, dịch vụ và phạm vi tài nguyên cần quan sát để cân bằng giữa khả năng điều tra và chi phí. Không loại trừ log bắt buộc theo yêu cầu kiểm toán hoặc chính sách bảo mật của tổ chức.

## 4. Truy vấn Cloud KMS audit logs trong Logs Explorer

Mở **Logging → Logs Explorer** trong project đang lưu log. Bộ lọc cơ bản để xem audit log của Cloud KMS là:

```text
protoPayload.serviceName="cloudkms.googleapis.com"
```

`protoPayload.serviceName` giúp giới hạn kết quả vào Cloud KMS. Bạn có thể kết hợp bộ lọc theo `logName`, `methodName`, `resourceName`, danh tính caller hoặc trạng thái để thu hẹp điều tra.

### 4.1. Tìm các lần giải mã

```text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.serviceName="cloudkms.googleapis.com"
protoPayload.methodName="Decrypt"
```

Để tìm các lần mã hóa, thay `Decrypt` bằng `Encrypt`. Có thể lặp lại cách này với `AsymmetricSign`, `AsymmetricDecrypt`, `MacSign` hoặc `MacVerify` khi workload sử dụng các API tương ứng.

### 4.2. Theo dõi thay đổi quyền và vòng đời khóa

Ví dụ tìm thao tác thay đổi IAM policy:

```text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="cloudkms.googleapis.com"
protoPayload.methodName="SetIamPolicy"
```

Ví dụ tìm yêu cầu hủy phiên bản khóa:

```text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="cloudkms.googleapis.com"
protoPayload.methodName="DestroyCryptoKeyVersion"
```

Tương tự, có thể lọc `UpdateCryptoKeyPrimaryVersion` để kiểm tra thời điểm đổi phiên bản chính hoặc `UpdateCryptoKey` để điều tra thay đổi cấu hình khóa.

### 4.3. Lọc theo danh tính và tài nguyên

Để xem hoạt động của một service account, thêm bộ lọc principal:

```text
protoPayload.serviceName="cloudkms.googleapis.com"
protoPayload.authenticationInfo.principalEmail="orders-api@PROJECT_ID.iam.gserviceaccount.com"
```

Để giới hạn vào một crypto key, lọc theo đường dẫn tài nguyên:

```text
protoPayload.serviceName="cloudkms.googleapis.com"
protoPayload.resourceName:"projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME"
```

Thay các giá trị mẫu bằng project ID, location, key ring và tên khóa thực tế. Có thể kết hợp các bộ lọc trên với `methodName` để trả lời câu hỏi một danh tính đã thực hiện thao tác cụ thể trên khóa nào.

### 4.4. Tìm các lời gọi có lỗi

```text
protoPayload.serviceName="cloudkms.googleapis.com"
severity>=ERROR
```

Khi xem một bản ghi, kiểm tra `protoPayload.status` để hiểu mã lỗi và thông điệp. Nếu lời gọi bị từ chối, kiểm tra thêm `authorizationInfo` và IAM policy tại thời điểm sự kiện. Một số sự kiện bị từ chối bởi chính sách bảo mật có thể xuất hiện dưới loại Policy Denied; hãy phân biệt chúng với lỗi ứng dụng hoặc lỗi cấu hình khác.

## 5. Đọc các trường quan trọng trong một audit log entry

Một audit log entry có cấu trúc bao quanh là `LogEntry`; phần `protoPayload` chứa dữ liệu `AuditLog`. Các trường sau thường hữu ích khi điều tra Cloud KMS:

| Trường | Ý nghĩa khi điều tra |
| --- | --- |
| `timestamp` | Thời điểm sự kiện được ghi nhận. Chuẩn hóa múi giờ khi đối chiếu với log ứng dụng. |
| `logName` | Cho biết log thuộc nhóm như `cloudaudit.googleapis.com/activity` hoặc `cloudaudit.googleapis.com/data_access`. |
| `protoPayload.serviceName` | Tên dịch vụ tạo audit log; với Cloud KMS là `cloudkms.googleapis.com`. |
| `protoPayload.methodName` | Phương thức API được gọi, chẳng hạn `Decrypt` hoặc `SetIamPolicy`. |
| `protoPayload.resourceName` | Tài nguyên Cloud KMS liên quan, giúp xác định key ring, crypto key hoặc phiên bản khóa. |
| `protoPayload.authenticationInfo.principalEmail` | Danh tính đã xác thực, thường là email người dùng hoặc service account. |
| `protoPayload.requestMetadata.callerIp` | Địa chỉ IP của caller nếu trường này có trong sự kiện. |
| `protoPayload.requestMetadata.callerSuppliedUserAgent` | User agent do caller cung cấp nếu có; hữu ích để phân biệt client hoặc workload. |
| `protoPayload.authorizationInfo` | Các quyền được kiểm tra và kết quả cho phép/từ chối tương ứng. |
| `protoPayload.status` | Trạng thái kết quả; khi có lỗi, kiểm tra mã và thông điệp để tìm nguyên nhân. |

Không phải mọi bản ghi đều có đủ tất cả trường. Ví dụ, địa chỉ IP của lời gọi nội bộ giữa các dịch vụ Google Cloud có thể bị ẩn thành `private` hoặc một giá trị thay thế; đừng mặc định `callerIp` luôn là địa chỉ IP gốc của người dùng cuối. Với workload dùng CMEK, principal trong log có thể là service agent của dịch vụ đang sử dụng khóa thay vì người dùng cuối khởi tạo nghiệp vụ. Hãy xác định danh tính workload và đối chiếu với log của dịch vụ đó trước khi kết luận có truy cập trái phép.

Cloud KMS đang cập nhật một số trường trong `protoPayload` của Data Access logs. Với ứng dụng phân tích log mới, hãy ưu tiên các trường được tài liệu hiện hành khuyến nghị: dùng `protoPayload.status.details` thay cho `protoPayload.metadata` khi đọc chi tiết lỗi của thao tác với khóa Cloud EKM; dùng `protoPayload.metadata.entries.caller_provided_context` thay cho `protoPayload.request.caller_provided_context` khi đọc context do caller cung cấp. Việc chuyển đổi có thể diễn ra theo giai đoạn, vì vậy bộ phân tích log cần chịu được sự khác biệt schema trong thời gian tương thích.

## 6. Biến audit logs thành tín hiệu giám sát

Tìm log thủ công phù hợp khi điều tra một sự kiện đã biết. Để phát hiện sự kiện sớm, hãy chuyển các mẫu truy vấn quan trọng thành log-based metrics hoặc alerting policy.

### 6.1. Xác định hành vi bình thường

Trước khi đặt ngưỡng cảnh báo, hãy lập baseline theo từng workload:

- Service account nào được phép sử dụng từng crypto key?
- Workload thường gọi `Encrypt`, `Decrypt` hay phương thức ký nào?
- Khóa nào được dùng bởi dịch vụ Google Cloud thông qua CMEK?
- Tần suất và khung giờ sử dụng bình thường là bao nhiêu?
- Ai được phép thay đổi IAM policy, cấu hình xoay vòng hoặc trạng thái phiên bản khóa?

Baseline giúp phân biệt lưu lượng hợp lệ với một thay đổi thực sự bất thường. Ví dụ, một service account xử lý đơn hàng có thể giải mã thường xuyên trong giờ cao điểm; một service account triển khai chỉ gọi thao tác quản trị khi phát hành. Cảnh báo cần phản ánh vai trò và nhịp hoạt động của từng workload.

### 6.2. Những tín hiệu nên giám sát

| Tín hiệu | Câu hỏi cần điều tra |
| --- | --- |
| `Decrypt` tăng đột biến | Có workload mới, vòng lặp lỗi hoặc hành vi đọc dữ liệu bất thường không? |
| Principal lạ gọi `Decrypt` hoặc `AsymmetricSign` | Danh tính đó có được cấp quyền sử dụng khóa theo thiết kế không? |
| Lời gọi từ IP hoặc user agent khác thường | Caller có thuộc hạ tầng và đường đi mạng được phê duyệt không? |
| `SetIamPolicy` trên crypto key | Có quyền mới được cấp hoặc quyền nhạy cảm bị mở rộng không? |
| `DestroyCryptoKeyVersion` hoặc thay đổi phiên bản chính | Thao tác có nằm trong kế hoạch vòng đời/khôi phục khóa đã duyệt không? |
| Nhiều lỗi liên tiếp | Có lỗi IAM, cấu hình key version, giới hạn dịch vụ hoặc hoạt động dò quyền không? |

Không nên cảnh báo chỉ dựa vào một sự kiện đơn lẻ nếu thao tác đó vốn là một phần của quy trình phát hành. Kết hợp principal, resource name, method, thời gian, caller metadata và trạng thái để giảm cảnh báo giả.

### 6.3. Tạo metric, alert và định tuyến log

Một quy trình giám sát thực tế có thể gồm:

1. Tạo log-based metric đếm các lời gọi `Decrypt` theo project hoặc theo nhóm tài nguyên.
2. Tạo metric hoặc truy vấn riêng cho các thay đổi nhạy cảm như `SetIamPolicy`, `DestroyCryptoKeyVersion` và `UpdateCryptoKeyPrimaryVersion`.
3. Đặt ngưỡng hoặc điều kiện cảnh báo dựa trên baseline của workload; gửi cảnh báo đến kênh trực ca theo quy trình của tổ chức.
4. Dùng log sink để định tuyến audit logs đến project giám sát tập trung, BigQuery, Cloud Storage hoặc Pub/Sub tùy yêu cầu lưu trữ và phân tích.
5. Kiểm tra quyền truy cập, retention và khả năng truy vấn ở đích nhận log; định kỳ thử khôi phục một sự kiện mẫu để bảo đảm bằng chứng vẫn sử dụng được.

Với tổ chức có nhiều project, tập trung Admin Activity logs giúp đội bảo mật xem thay đổi Cloud KMS trên toàn bộ phạm vi. Có thể định tuyến thêm Data Access logs cho các project hoặc khóa có yêu cầu kiểm soát sử dụng cao. Hãy bảo vệ project lưu trữ log bằng IAM riêng, giới hạn quyền xóa hoặc thay đổi sink và theo dõi chính cấu hình định tuyến log.

## 7. Tình huống thực tế: điều tra một lần giải mã bất thường

Giả sử ứng dụng `orders-api` dùng service account `orders-api@PROJECT_ID.iam.gserviceaccount.com` để giải mã dữ liệu bằng khóa `orders-key`. Đội vận hành nhận cảnh báo rằng số lần `Decrypt` tăng mạnh vào ban đêm.

Thực hiện điều tra theo trình tự sau:

1. Mở Logs Explorer và lọc `serviceName="cloudkms.googleapis.com"`, `methodName="Decrypt"` cùng đường dẫn `resourceName` của `orders-key`.
2. Nhóm kết quả theo `principalEmail` để xác định danh tính tạo ra phần lớn lời gọi. Nếu principal là service agent của một dịch vụ dùng CMEK, xác định dịch vụ đó trước khi quy kết cho ứng dụng.
3. So sánh `timestamp`, `callerIp` và `callerSuppliedUserAgent` với baseline của workload. Trường nào không có trong log thì tiếp tục kiểm tra log ứng dụng hoặc log hạ tầng.
4. Kiểm tra `status` để phân biệt lời gọi thành công với lời gọi thất bại. Đối chiếu thời điểm với thay đổi IAM hoặc thay đổi cấu hình khóa, đặc biệt là `SetIamPolicy` và `UpdateCryptoKeyPrimaryVersion`.
5. Nếu principal hoặc nguồn gọi không được nhận diện, xác minh service account, quyền IAM, workload đang chạy và lịch sử triển khai. Thu thập log liên quan trước khi thu hồi quyền hoặc vô hiệu hóa workload để tránh làm mất dữ liệu điều tra.
6. Sau khi xác định nguyên nhân, điều chỉnh quyền theo nguyên tắc tối thiểu, cập nhật baseline/cảnh báo và ghi lại quyết định xử lý.

Audit log cung cấp dấu vết về lời gọi Cloud KMS. Nó không tự chứng minh người dùng cuối nào đã yêu cầu nghiệp vụ giải mã hoặc dữ liệu nào đã được đọc. Để hoàn tất điều tra, cần liên kết sự kiện KMS với request ID, user identity và log nghiệp vụ ở tầng ứng dụng nếu hệ thống có ghi nhận các thông tin đó.

## 8. Giới hạn và thực hành tốt

- **Bật đúng loại log:** Admin Activity không thay thế Data Access. Nếu mục tiêu là theo dõi `Encrypt`/`Decrypt`, hãy xác minh Data Read đã được bật cho Cloud KMS ở đúng phạm vi.
- **Xác minh log sau cấu hình:** Thực hiện một lời gọi thử nghiệm được cấp quyền, sau đó kiểm tra `serviceName`, `methodName`, principal và resource name trong Logs Explorer.
- **Không diễn giải sự vắng mặt của log quá mức:** Data Access có thể chưa bật, cấu hình có thể được kế thừa từ cấp cha, hoặc phương thức có thể không tạo audit log. `GenerateRandomBytes` là một ví dụ được Cloud KMS nêu rõ.
- **Bảo vệ dữ liệu audit:** Giới hạn quyền đọc Data Access logs, quản lý retention và log sink, đồng thời bảo vệ project lưu trữ log khỏi thay đổi trái phép.
- **Kiểm soát chi phí:** Theo dõi dung lượng log khi bật Data Access trên project có nhiều workload dùng CMEK. Đánh giá lại phạm vi và retention theo yêu cầu kiểm toán.
- **Đọc log theo ngữ cảnh:** Service agent có thể là principal hợp lệ khi dịch vụ Google Cloud dùng CMEK. Đối chiếu danh tính, resource name và log của dịch vụ gọi trước khi kết luận.
- **Chuẩn bị cho thay đổi schema:** Phân tích log bằng các trường được tài liệu Cloud KMS hiện hành khuyến nghị và tránh phụ thuộc lâu dài vào trường đã bị đánh dấu deprecated.
- **Kiểm tra quyền đọc:** Người có `roles/logging.viewer` có thể không xem được Data Access logs trong `_Default`; cấp `roles/logging.privateLogViewer` khi nhiệm vụ thực sự cần đọc loại log này.

## 9. Checklist triển khai

- [ ] Xác định project, folder hoặc organization cần theo dõi Cloud KMS.
- [ ] Xác định crypto key, workload, service account và thao tác cần giám sát.
- [ ] Bật Data Access logs phù hợp (`ADMIN_READ`, `DATA_READ`, và `DATA_WRITE` khi cần) cho `cloudkms.googleapis.com`.
- [ ] Xác nhận cấu hình kế thừa từ organization hoặc folder và kiểm tra quyền đọc log.
- [ ] Chạy thử thao tác mã hóa/giải mã được phép và xác minh audit log xuất hiện.
- [ ] Lưu các truy vấn cho thao tác sử dụng khóa và thay đổi cấu hình nhạy cảm.
- [ ] Tạo metric/alert dựa trên baseline của từng workload.
- [ ] Định tuyến log, thiết lập retention và giới hạn quyền truy cập kho log.
- [ ] Kiểm tra định kỳ cảnh báo, chi phí và khả năng truy xuất bằng chứng.

## Tài liệu tham khảo

- [Cloud Key Management Service audit logging](https://docs.cloud.google.com/kms/docs/audit-logging) — danh sách phương thức Cloud KMS tạo audit logs, loại log và bộ lọc Logs Explorer.
- [Cloud Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit) — bốn loại audit logs, quyền đọc và cách lưu trữ.
- [Enable Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access) — bật Data Access logs ở cấp organization, folder hoặc project.
- [Best practices for Cloud Audit Logs](https://docs.cloud.google.com/logging/docs/audit/best-practices) — khuyến nghị bảo vệ, quản lý và giám sát audit logs.
- [Recommended practices for using CMEKs](https://docs.cloud.google.com/kms/docs/cmek-recommended-practices) — khuyến nghị tổng hợp Admin Activity và cân nhắc lưu lượng/chi phí Data Access logs.
