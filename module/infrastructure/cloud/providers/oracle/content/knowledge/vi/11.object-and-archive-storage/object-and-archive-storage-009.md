# Object replication và sao chép dữ liệu liên vùng

Trong chương **Object Storage và Archive Storage** của module **CLOUD_PROVIDERS_ORACLE**, bài học này trình bày cách duy trì dữ liệu đối tượng tại nhiều OCI region. Nội dung kết nối tenancy, compartment và IAM với Object Storage, giám sát, tự động hóa, chi phí và phương án duy trì hoạt động khi region chính gặp sự cố.

Một bucket lưu hóa đơn tại region A có thể phục vụ tốt trong điều kiện bình thường, nhưng ứng dụng ở region B vẫn cần biết dữ liệu nào đã đến, có thể đọc được hay chưa và khi nào được phép ghi. Vì vậy, triển khai liên vùng cần cả cơ chế chuyển dữ liệu lẫn quy trình vận hành.

## 1. Mục tiêu và phạm vi

Sau bài học, người học có thể:

- Chọn giữa replication liên tục và CopyObject theo từng yêu cầu.
- Chuẩn bị bucket nguồn, bucket đích và hai lớp quyền IAM.
- Tạo replication policy và xác minh dữ liệu ở region dự phòng.
- Lập kế hoạch sao chép dữ liệu cũ, xử lý thay đổi đồng thời và lỗi từng object.
- Thiết kế theo dõi độ trễ, failover, failback và kiểm soát chi phí.

Ví dụ chính sử dụng **hai region trong cùng một tenancy**. Việc sao chép giữa hai tenancy cần thiết kế quyền xuyên tenancy riêng; không áp dụng nguyên trạng các policy trong bài cho trường hợp đó. Các lệnh bên dưới là hướng dẫn thực hành, cần thay biến mẫu trước khi chạy trên OCI.

## 2. Ba nhu cầu cần phân biệt

### Replication liên tục

Object Storage replication thiết lập quan hệ từ bucket nguồn sang bucket đích. Dữ liệu được chuyển bất đồng bộ, tức là thành công của thao tác ghi ở nguồn chưa chứng minh object đã sẵn sàng tại đích. Có thể dùng bucket cùng region hoặc khác region trong tenancy; bài này chọn khác region để phục vụ dự phòng. [Nguồn: Oracle Object Storage FAQ](https://www.oracle.com/cloud/storage/object-storage/faq/).

### Sao chép chủ động bằng CopyObject

CopyObject thực hiện một lần sao chép cho một object được chỉ định. Người vận hành quyết định tên đích, region, thời điểm và cách xử lý object đã tồn tại. Lệnh này phù hợp khi xuất một tập dữ liệu đã chốt hoặc chuyển dữ liệu theo kế hoạch. Một lần copy không tạo quan hệ đồng bộ lâu dài.

Ví dụ: đưa báo cáo tháng đã khóa từ bucket vận hành sang bucket phục vụ phân tích. Job hôm nay phải có danh sách rõ ràng; báo cáo xuất hiện ngày mai cần một yêu cầu khác.

### Bản phục hồi có lịch sử độc lập

Giả sử ứng dụng ghi đè hóa đơn bằng nội dung sai. Một bản dữ liệu ở region khác vẫn có thể nhận nội dung sai đó. Hệ thống còn cần cơ chế lưu lịch sử hoặc bản dữ liệu đã chốt để phục hồi lỗi nghiệp vụ.

| Nhu cầu | Phương án nên đánh giá | Bằng chứng cần thu thập |
| --- | --- | --- |
| Tiếp tục phục vụ khi region chính không truy cập được | Replication và runbook chuyển vùng | Object đã xuất hiện và đọc được ở region dự phòng |
| Chuyển một danh sách object đã xác định | CopyObject theo manifest | Kết quả từng work request và đối chiếu nội dung |
| Khôi phục dữ liệu trước một lỗi nghiệp vụ | Lịch sử phiên bản hoặc bản sao độc lập phù hợp | Mốc dữ liệu phục hồi, quyền đọc và thử khôi phục |
| Giảm thời gian truy cập cho người dùng ở vùng khác | Đánh giá thêm bản đọc ở region gần người dùng | Độ trễ ứng dụng đo được và chính sách chọn endpoint |

Bảng trên là gợi ý thiết kế. Mỗi phương án cần được kiểm chứng với cách ghi dữ liệu và yêu cầu phục hồi của ứng dụng.

## 3. Vòng đời dữ liệu khi bật replication

Ví dụ nguồn là bucket **oci-objects-primary-lab** tại **us-ashburn-1**; đích là **oci-objects-dr-lab** tại **us-phoenix-1**.

~~~mermaid
flowchart LR
    App["Ứng dụng tại region chính"] -->|"Ghi object"| Source["Bucket nguồn: đọc và ghi"]
    Source -->|"Replication bất đồng bộ"| Target["Bucket đích: chỉ đọc với ứng dụng"]
    Target -->|"Đọc dữ liệu đã tới"| DR["Ứng dụng dự phòng"]
    Operator["Người vận hành"] -->|"IAM và replication policy"| Source
~~~

Các ngữ nghĩa quan trọng của replication:

- Object được tải lên **sau khi policy được tạo** mới thuộc luồng replication tự động; object có trước đó không được tự nạp sang đích.
- Xóa object ở nguồn có thể làm object tương ứng bị xóa ở đích.
- Bucket đích trở thành chỉ đọc đối với thao tác ghi thông thường; replication cập nhật dữ liệu tại đó.
- Mỗi nguồn có tối đa một policy và một đích; mỗi đích có một nguồn. Đích không đồng thời làm nguồn cho chuỗi replication.
- Không hỗ trợ replication object mã hóa bằng khóa do khách hàng cung cấp trực tiếp theo cơ chế SSE-C. [Nguồn: Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm).

Không diễn giải việc ghi thành công ở nguồn thành một giao dịch đã hoàn tất tại cả hai region. Chẳng hạn, nếu ứng dụng cập nhật cơ sở dữ liệu để tham chiếu một object vừa ghi, region dự phòng có thể nhìn thấy bản ghi tham chiếu trước khi đọc được object. Cần quy ước xử lý object chưa đến, như trì hoãn phục vụ yêu cầu đó, retry có giới hạn hoặc hiển thị trạng thái đang xử lý.

### Ví dụ về ranh giới thời gian

| Thời điểm trong ví dụ | Hành động | Điều cần kiểm chứng |
| --- | --- | --- |
| 09:00 | Tải old-report.csv trước khi tạo policy | Dữ liệu cũ cần kế hoạch nạp riêng |
| 09:10 | Tạo policy nguồn sang đích | Đúng bucket và đúng region |
| 09:12 | Tải new-report.csv | Thời điểm object xuất hiện tại đích |
| 09:15 | Ghi đè new-report.csv | Nội dung mà ứng dụng dự phòng thực sự đọc |
| 09:20 | Xóa object thử nghiệm ở nguồn | Hành vi tại đích sau khi xử lý xong |

Các mốc giờ chỉ minh họa trình tự, không phải cam kết thời gian xử lý của OCI.

## 4. Chuẩn bị bucket, compartment và IAM

### Điều kiện trước khi tạo policy

Chuẩn bị hai bucket trong đúng region, xác nhận tenancy đã đăng ký region đích và người cấu hình có quyền truy cập cả hai phía. Việc tạo replication policy không thay thế bước chuẩn bị bucket. Trên Console, policy được tạo ở bucket nguồn với thông tin region và bucket đích. [Nguồn: Creating an Object Storage Replication Policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

Đối với bài thực hành:

- Dùng hai compartment riêng: **StoragePrimaryLab** và **StorageDRLab**.
- Chọn Standard để việc kiểm tra đọc không phụ thuộc thời gian phục hồi từ Archive.
- Giữ bucket private và chỉ dùng dữ liệu giả lập.
- Đích không bật versioning và không có retention rule; đây là các điều kiện có thể làm tạo policy thất bại. [Nguồn: Troubleshooting Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm).

Không dùng một bucket đích đang chứa dữ liệu quan trọng không liên quan. Thiết kế tên và mục đích bucket rõ ràng giúp tránh nhầm lẫn khi diễn tập hoặc dọn môi trường.

### Quyền người vận hành và quyền dịch vụ

Có hai danh tính cần được cấp quyền:

1. Người dùng hoặc nhóm vận hành tạo bucket, cấu hình policy và kiểm tra object.
2. Dịch vụ Object Storage tại region nguồn thực hiện chuyển dữ liệu thay người dùng.

Quyền của người chạy CLI không tự trở thành quyền của dịch vụ. Cũng không khắc phục lỗi quyền dịch vụ bằng cách công khai bucket.

Ví dụ policy cho nhóm trong identity domain mặc định của môi trường lab:

~~~text
Allow group Default/StorageReplicationOperators to manage buckets in compartment StoragePrimaryLab
Allow group Default/StorageReplicationOperators to manage objects in compartment StoragePrimaryLab
Allow group Default/StorageReplicationOperators to manage buckets in compartment StorageDRLab
Allow group Default/StorageReplicationOperators to manage objects in compartment StorageDRLab

Allow service objectstorage-us-ashburn-1 to manage object-family in compartment StoragePrimaryLab
Allow service objectstorage-us-ashburn-1 to manage object-family in compartment StorageDRLab
~~~

Thay **Default**, tên nhóm và tên compartment bằng giá trị thật. Đặt policy ở phạm vi có thể cấp quyền cho cả hai compartment, chẳng hạn policy tại root tenancy cho hai compartment con tương ứng.

Đây là ví dụ quyền rộng trong hai compartment dành riêng cho lab, chưa phải policy tối thiểu cho production. Có thể thu hẹp bằng quyền cụ thể và điều kiện bucket/region theo mô hình IAM của OCI. Với nguồn ở region khác, thay service principal tương ứng; khi đảo chiều, phải đánh giá quyền cho dịch vụ tại region nguồn mới. [Nguồn: IAM cho replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm), [giới hạn theo bucket và region](https://www.oracle.com/cloud/storage/object-storage/faq/).

Đối với môi trường sử dụng Vault hoặc cơ chế mã hóa tùy chỉnh, đưa khóa, quyền sử dụng khóa và khả năng truy cập khóa vào kế hoạch kiểm tra DR. Không coi việc object đã xuất hiện là bằng chứng rằng ứng dụng dự phòng đã có đầy đủ quyền đọc.

## 5. Thực hành tạo replication liên vùng

Các đoạn lệnh sử dụng **PowerShell và OCI CLI** đã cấu hình xác thực. Có thể kiểm tra cú pháp tại máy bằng tùy chọn **--help**. Bài học không yêu cầu tạo Compute hay VCN mới chỉ để thực hành chuyển object.

### Khai báo tham số

~~~powershell
$SourceRegion = 'us-ashburn-1'
$DestinationRegion = 'us-phoenix-1'
$Namespace = 'THAY_NAMESPACE_CUA_TENANCY'
$SourceCompartmentId = 'THAY_OCID_COMPARTMENT_NGUON'
$DestinationCompartmentId = 'THAY_OCID_COMPARTMENT_DICH'
$SourceBucket = 'oci-objects-primary-lab'
$DestinationBucket = 'oci-objects-dr-lab'
$PolicyName = 'primary-to-dr-lab'
~~~

Namespace là namespace Object Storage, không phải tên hiển thị tenancy. Chọn tên bucket còn trống tại region tương ứng.

### Tạo hai bucket

~~~powershell
$SourceBucketArgs = @(
    'os', 'bucket', 'create',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--compartment-id', $SourceCompartmentId,
    '--name', $SourceBucket,
    '--storage-tier', 'Standard',
    '--public-access-type', 'NoPublicAccess',
    '--versioning', 'Disabled'
)
oci @SourceBucketArgs
if ($LASTEXITCODE -ne 0) { throw 'Tao bucket nguon that bai' }

$DestinationBucketArgs = @(
    'os', 'bucket', 'create',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--compartment-id', $DestinationCompartmentId,
    '--name', $DestinationBucket,
    '--storage-tier', 'Standard',
    '--public-access-type', 'NoPublicAccess',
    '--versioning', 'Disabled'
)
oci @DestinationBucketArgs
if ($LASTEXITCODE -ne 0) { throw 'Tao bucket dich that bai' }
~~~

Nếu dùng bucket lab có sẵn, kiểm tra cấu hình rồi bỏ bước tạo thay vì chạy lại một cách mù quáng. Các tùy chọn loại truy cập, storage tier và versioning được mô tả trong [OCI CLI: bucket create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/create.html).

Trước bước kế tiếp, có thể dùng Console tải một file giả lập **before-policy.txt** vào nguồn để quan sát trường hợp dữ liệu tồn tại từ trước.

### Tạo policy tại nguồn

~~~powershell
$ReplicationArgs = @(
    'os', 'replication', 'create-replication-policy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--destination-region', $DestinationRegion,
    '--destination-bucket', $DestinationBucket,
    '--name', $PolicyName
)
$PolicyJson = oci @ReplicationArgs
if ($LASTEXITCODE -ne 0) { throw 'Tao replication policy that bai' }

$Policy = ($PolicyJson -join [Environment]::NewLine) | ConvertFrom-Json
$ReplicationId = $Policy.data.id
if ([string]::IsNullOrWhiteSpace($ReplicationId)) {
    throw 'Khong nhan duoc replication ID'
}
$Policy.data
~~~

Lưu replication ID trong hồ sơ vận hành để kiểm tra đúng policy về sau. **--region** xác định phía nguồn đang nhận lệnh; **--destination-region** xác định nơi dữ liệu được đưa tới. Không đảo hai tham số này. [Tham chiếu tạo policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

### Đọc lại quan hệ replication

~~~powershell
$GetPolicyArgs = @(
    'os', 'replication', 'get-replication-policy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--replication-id', $ReplicationId
)
oci @GetPolicyArgs

$ListSourcesArgs = @(
    'os', 'replication', 'list-replication-sources',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket
)
oci @ListSourcesArgs
~~~

Kiểm tra tên nguồn, tên đích, region và trạng thái policy. Dùng **get-replication-policy** để xem trạng thái, thông báo và trường thời gian đồng bộ được trả về; dùng **list-replication-sources** tại region đích để xác minh phía nhận. [Tham chiếu get policy](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/replication/get-replication-policy.html), [tham chiếu liệt kê nguồn](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_list_replication_policies.htm).

Một policy hiển thị ACTIVE mới xác nhận cấu hình đang hoạt động ở mức policy. Cần kiểm tra dữ liệu cụ thể trước khi kết luận ứng dụng có thể phục vụ tại đích.

### Kiểm chứng với object thử nghiệm

Sau khi tạo policy, dùng Console tải **after-policy.txt** với nội dung đã biết vào bucket nguồn. Sau đó kiểm tra đích:

~~~powershell
$HeadArgs = @(
    'os', 'object', 'head',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket,
    '--name', 'after-policy.txt'
)
oci @HeadArgs
~~~

HeadObject trả thông tin như ETag và metadata mà không cần tải toàn bộ nội dung. [Tham chiếu OCI CLI: object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html).

Lặp kiểm tra có giới hạn thời gian; ghi lại lúc tải nguồn thành công và lúc đích đọc được. Nếu chưa thấy object, kiểm tra trạng thái và quyền trước khi kết luận mất dữ liệu. Với file thử nghiệm nhỏ, tải bản đích bằng Console và mở nội dung để xác nhận thêm.

Có thể kiểm tra ghi đè và xóa bằng object dùng riêng cho lab. Không sử dụng file nghiệp vụ để diễn tập thao tác xóa.

## 6. Sao chép một object theo yêu cầu

Dùng bucket nhận riêng **oci-objects-copy-lab**, đã tạo ở region đích, để tránh xung đột với bucket đang là replication destination.

### Gửi yêu cầu CopyObject

~~~powershell
$CopyBucket = 'oci-objects-copy-lab'
$CopyArgs = @(
    'os', 'object', 'copy',
    '--region', $SourceRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $SourceBucket,
    '--source-object-name', 'before-policy.txt',
    '--destination-region', $DestinationRegion,
    '--destination-namespace', $Namespace,
    '--destination-bucket', $CopyBucket,
    '--destination-object-name', 'initial-load/before-policy.txt',
    '--destination-object-if-none-match-e-tag', '*'
)
$CopyJson = oci @CopyArgs
if ($LASTEXITCODE -ne 0) { throw 'Gui yeu cau copy that bai' }

$CopyResponse = ($CopyJson -join [Environment]::NewLine) | ConvertFrom-Json
$WorkRequestId = $CopyResponse.'opc-work-request-id'
$CopyResponse
~~~

Điều kiện **--destination-object-if-none-match-e-tag '*'** yêu cầu thao tác thất bại nếu tên đích đã tồn tại. Có thể bổ sung **--source-object-if-match-e-tag** với ETag đã đọc từ nguồn để bảo đảm object chưa bị thay đổi so với thời điểm lập kế hoạch. [Nguồn: OCI CLI CopyObject](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

Chọn tên chứa mã đợt chuyển dữ liệu khi muốn giữ các đợt độc lập. Nếu nghiệp vụ cho phép ghi đè, phải quy định rõ object nào được thay thế và điều kiện kiểm tra; tránh dùng ghi đè không điều kiện như cách xử lý lỗi mặc định.

### Theo dõi work request của CopyObject

~~~powershell
if ([string]::IsNullOrWhiteSpace($WorkRequestId)) {
    throw 'Can lay opc-work-request-id tu phan hoi copy'
}

$WorkRequestArgs = @(
    'os', 'work-request', 'get',
    '--region', $SourceRegion,
    '--work-request-id', $WorkRequestId
)
oci @WorkRequestArgs
~~~

Truy vấn tại region nơi gửi yêu cầu copy. Lưu work request ID cùng object nguồn, tên đích và thời điểm gửi để đối chiếu khi có lỗi. API truy vấn trả trạng thái xử lý của yêu cầu bất đồng bộ. [Nguồn: OCI CLI work-request get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/work-request/get.html).

Có thể dùng **--wait-for-state COMPLETED --wait-for-state FAILED** ngay trong lệnh copy để đợi một trong hai kết quả, rồi tự kiểm tra trạng thái trả về. Timeout của phía CLI chưa chứng minh thao tác phía dịch vụ đã thất bại; truy vấn lại work request trước khi gửi thêm yêu cầu. [Tham chiếu tùy chọn chờ của CopyObject](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

### Các điểm khác biệt về dữ liệu và Archive

Một copy thành công tạo object đích với ETag mới, vì vậy không yêu cầu ETag hai phía bằng nhau để kết luận nội dung đúng. Object ở Archive phải được restore trước khi dùng làm nguồn copy. Copy vào bucket Archive làm bản đích được lưu trữ ở Archive; điều này ảnh hưởng thời gian sẵn sàng khi cần đọc. Mỗi yêu cầu copy chỉ chỉ định một object. [Nguồn: Copying an Object](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/copyingobjects.htm).

Đối với dữ liệu quan trọng, quy ước checksum ở cấp ứng dụng và lưu cùng manifest. So sánh nội dung hoặc checksum của dữ liệu ổn định giúp phát hiện nhầm object, sai tên và lỗi chọn tập dữ liệu; việc thấy cùng số lượng object chưa đủ chứng minh dữ liệu đúng.

## 7. Nạp dữ liệu cũ và kiểm soát thay đổi đồng thời

Một hệ thống đã chạy nhiều tháng thường có dữ liệu tồn tại trước lúc bật replication. Hãy coi nạp dữ liệu ban đầu là một công việc riêng, có đầu vào và kết quả kiểm chứng.

### Phương án đơn giản: có khoảng dừng ghi

Quy trình gợi ý cho hệ thống nhỏ:

1. Dừng các tác vụ ghi và xóa có thể thay đổi tập dữ liệu cần nạp.
2. Lập manifest liệt kê tên, kích thước, ETag và checksum ứng dụng nếu có.
3. Khi bucket đích còn ghi được, copy từng object cũ sang đó.
4. Đợi tất cả work request hoàn tất và đối chiếu manifest.
5. Tạo replication policy giữa hai bucket.
6. Xác minh policy rồi mở lại luồng ghi nguồn.
7. Thử một object mới để xác nhận phần dữ liệu tiếp theo đi đúng hướng.

Khoảng dừng phải bao phủ cả việc chốt manifest, nạp và tạo policy. Nếu mở ghi giữa các bước mà không có cơ chế ghi nhận thay đổi, có thể tạo khoảng trống dữ liệu.

### Khi không thể dừng ghi lâu

Cần thiết kế quy trình chuyển dữ liệu có mốc và phần thay đổi phát sinh, chẳng hạn:

- Dùng object có tên bất biến theo mã nghiệp vụ hoặc mã phiên bản.
- Ghi nhận các thao tác phát sinh vào nhật ký riêng có thể phát lại.
- Nạp dữ liệu nền sang vùng đích tạm, sau đó đối chiếu phần thay đổi.
- Chốt một khoảng chuyển ngắn để xử lý phần còn lại và xác nhận tập dữ liệu.

Đây là các phương án kiến trúc cần triển khai và thử riêng. Không giả định việc liệt kê object trong khi ứng dụng vẫn ghi sẽ tạo một snapshot nhất quán của cả ứng dụng.

Nếu policy đã hoạt động và phát hiện còn thiếu dữ liệu cũ, không tùy tiện ghi vào destination đang chỉ đọc. Có thể chuẩn bị đích mới và lập lại quy trình, hoặc dùng kho nạp riêng với kế hoạch chuyển được kiểm soát.

### Thiết kế job xử lý nhiều object

CopyObject từng object cần một bộ điều phối khi tập dữ liệu lớn. Manifest có thể chứa:

| Trường | Mục đích |
| --- | --- |
| batch_id | Phân biệt các đợt nạp |
| source_region, source_bucket, object_name | Xác định nguồn |
| source_etag hoặc source_version_id | Khóa trạng thái nguồn cần đọc |
| destination_region, destination_bucket, destination_name | Xác định đích |
| work_request_id, status, attempts | Theo dõi thực thi |
| expected_size, application_checksum | Kiểm chứng kết quả |

Job nên giới hạn số yêu cầu đồng thời, xử lý phân trang khi liệt kê object, retry lỗi tạm thời với khoảng chờ tăng dần và lưu tiến độ từng mục. Tách lỗi nguồn bị thay đổi khỏi lỗi mạng: trường hợp đầu cần quyết định lại dữ liệu phải copy, không chỉ retry cùng yêu cầu.

Nếu lần chạy trước đã tạo object đích và lần chạy lại gặp điều kiện “đã tồn tại”, đối chiếu manifest và dữ liệu trước khi đánh dấu hoàn tất. Xung đột tên không tự chứng minh lần sao chép trước đã đúng.

## 8. Giám sát và đánh giá RPO, RTO

**RPO** thể hiện mức dữ liệu có thể mất theo thời gian khi phục hồi. **RTO** thể hiện thời gian cần để đưa dịch vụ trở lại mức hoạt động đã đặt ra. Đây là mục tiêu của hệ thống và quy trình vận hành, cần được đo bằng diễn tập.

Một phép đo thực nghiệm có thể dùng:

~~~text
observed_replication_delay
  = thời điểm đọc được object tại đích
  - thời điểm ghi nguồn hoàn tất

observed_recovery_time
  = thời điểm kiểm tra nghiệp vụ tại đích thành công
  - thời điểm bắt đầu sự cố giả lập
~~~

Ghi một object canary với tên duy nhất và thời gian UTC, kiểm tra nó ở đích, rồi lưu độ trễ theo nhiều thời điểm tải khác nhau. Đặt ngưỡng cảnh báo theo yêu cầu nghiệp vụ. Một canary đến nhanh không chứng minh tất cả object đã đến, đặc biệt khi kích thước và luồng ghi khác nhau.

Kết hợp ba lớp kiểm tra:

| Lớp | Tín hiệu | Quyết định hỗ trợ |
| --- | --- | --- |
| Cấu hình | Trạng thái policy và thông báo lỗi | Phát hiện quan hệ replication có vấn đề |
| Dữ liệu | Canary, manifest, object nghiệp vụ mới nhất đã đối chiếu | Đánh giá khả năng phục hồi dữ liệu |
| Ứng dụng | Thử đăng nhập, đọc tài liệu và xử lý giao dịch mẫu tại DR | Đánh giá khả năng phục vụ thực tế |

Theo tài liệu Oracle được tham chiếu, Console chưa cung cấp replication metrics chuyên biệt. Vì vậy, không xây toàn bộ cảnh báo dựa trên giả định có sẵn biểu đồ replication lag. [Nguồn: Scope and Constraints](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm).

Nếu ứng dụng dùng Oracle Database hoặc cơ sở dữ liệu khác để lưu metadata, phải kiểm tra tính nhất quán giữa metadata và object. Việc chuẩn bị bản dữ liệu Object Storage không thay thế kế hoạch phục hồi cơ sở dữ liệu, Compute, mạng, khóa và cấu hình ứng dụng.

## 9. Failover và failback có kiểm soát

### Chuyển sang region dự phòng

Runbook gợi ý:

1. Ghi nhận sự cố, người quyết định chuyển vùng và mốc dữ liệu đã xác minh.
2. Ngăn writer cũ tiếp tục ghi khi có thể, tránh hai phía cùng nhận cập nhật.
3. Kiểm tra các object quan trọng và phụ thuộc ứng dụng tại region dự phòng.
4. Nếu chỉ cần đọc dữ liệu đã đến, đánh giá khả năng phục vụ đọc ngay trên đích.
5. Nếu phải ghi, chủ động chấm dứt vai trò replication destination trước.
6. Chuyển cấu hình ứng dụng sang endpoint/bucket dự phòng.
7. Chạy kiểm tra nghiệp vụ và ghi nhận dữ liệu thiếu hoặc cần xử lý bù.

Trong tình huống đã quyết định cho phép ghi ở DR, thao tác minh họa:

~~~powershell
$PromoteArgs = @(
    'os', 'replication', 'make-bucket-writable',
    '--region', $DestinationRegion,
    '--namespace-name', $Namespace,
    '--bucket-name', $DestinationBucket
)
oci @PromoteArgs
~~~

**MakeBucketWritable** dừng việc nhận replication và cho phép ghi vào bucket đích. Đây là thao tác đổi vai trò dữ liệu, không phải kiểm tra chỉ đọc. [Nguồn: OCI CLI make-bucket-writable](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/replication/make-bucket-writable.html).

Sau khi dừng ở phía đích, policy nguồn có thể chuyển sang lỗi. Muốn dùng lại quan hệ cũ phải xử lý policy nguồn và tạo lại theo quy trình của Oracle. Không kỳ vọng mở ghi ở DR rồi tự khôi phục được quan hệ hai chiều. [Nguồn: Troubleshooting Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm).

### Trở lại region ban đầu

Sau thời gian DR nhận ghi, dữ liệu mới nhất có thể nằm tại DR. Một kế hoạch failback nên:

- Xác định phía có thẩm quyền với từng loại dữ liệu.
- Đối chiếu các thay đổi trong thời gian sự cố và xử lý xung đột.
- Chuẩn bị lại bucket nhận và quyền cho chiều chuyển dữ liệu mới.
- Nạp dữ liệu đã có trước thời điểm tạo policy mới.
- Chuyển ứng dụng trong khoảng đã thống nhất, rồi kiểm tra nghiệp vụ.

Không chỉ đổi endpoint trở về region cũ. Nếu bỏ qua phần thay đổi tại DR, ứng dụng có thể phục vụ dữ liệu cũ hoặc ghi đè dữ liệu mới.

## 10. Versioning, retention và chi phí

Replication không mang toàn bộ lịch sử phiên bản cũ sang đích; destination không được bật versioning. Do đó, nếu cần quay lại hóa đơn trước một lần sửa sai, phải xác định rõ lịch sử được giữ ở đâu và ai có thể phục hồi. [Nguồn: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Khi cần lưu bất biến theo yêu cầu nghiệp vụ, đánh giá một bucket lưu trữ độc lập với quyền và retention phù hợp. Không thiết kế bằng cách thêm retention rule vào destination hiện tại, vì điều kiện destination đã phải được kiểm tra từ đầu.

Lập dự toán theo các nhóm sau, với đơn giá và điều kiện thực tế của tenancy tại thời điểm triển khai:

- Dung lượng nguồn, đích, kho nạp tạm và bản lưu lịch sử.
- Lượng dữ liệu thay đổi, kể cả ghi đè cùng tên nhiều lần.
- Yêu cầu đọc/ghi, hoạt động sao chép và truyền dữ liệu liên vùng.
- Đọc, phục hồi và điều kiện tính phí của từng storage tier.
- Chi phí job, log, giám sát và các lần diễn tập.

Có thể ước lượng sơ bộ lượng dữ liệu cần chuyển:

~~~text
khối lượng chuyển trong kỳ
  ≈ dữ liệu nạp ban đầu của kỳ
  + tổng dung lượng các lần ghi mới và ghi đè cần chuyển
~~~

Ví dụ giả định 300 GB dữ liệu ban đầu và 20 GB nội dung thay đổi mỗi ngày trong 30 ngày tạo khoảng 900 GB đầu vào chuyển dữ liệu trước khi xét retry và đặc điểm vận hành. Đây là ước lượng khối lượng cho bài toán, không phải cách tính hóa đơn OCI.

Nếu RTO yêu cầu đọc dữ liệu ngay, hãy thử thực tế trước khi chọn Archive cho bản dự phòng. Giá lưu trữ thấp chưa quyết định tổng chi phí phục hồi hoặc thời gian đáp ứng nghiệp vụ.

## 11. Chẩn đoán theo triệu chứng

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Không tạo được policy | Đúng region, bucket đích, versioning, retention và hai lớp IAM |
| Policy chuyển sang lỗi | Destination còn nhận replication hay đã mở ghi; quyền còn hiệu lực; giới hạn dung lượng |
| Bài kiểm tra không thấy object cũ | So thời điểm tải lên với thời điểm tạo policy và manifest nạp ban đầu |
| Copy được chấp nhận nhưng chưa có dữ liệu | Trạng thái work request tại region gửi yêu cầu |
| Copy bị lỗi điều kiện ETag | Đối chiếu phiên bản nguồn và tình trạng object đích |
| Có object nhưng ứng dụng đọc thất bại | Danh tính ứng dụng DR, cấu hình endpoint, quyền đọc và khóa |
| Dữ liệu tham chiếu bị thiếu | Đối chiếu mốc phục hồi metadata với mốc dữ liệu object |
| DR có dữ liệu mới nhưng nguồn cũ chưa có | Thực hiện đối chiếu và failback, không đổi endpoint vội |

Các nguyên nhân lỗi tạo policy và lỗi quan hệ replication được Oracle mô tả trong [Troubleshooting Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Troubleshooting/usingreplication_topic-Troubleshooting_Replication.htm). Các hàng về ứng dụng và quy trình là gợi ý điều tra, cần đối chiếu kiến trúc thực tế.

Khi báo lỗi, lưu request ID hoặc work request ID, region, tên bucket, object và thời điểm UTC. Không đưa khóa, token hoặc nội dung nhạy cảm vào log chẩn đoán.

## 12. Bài thực hành củng cố

Dùng dữ liệu giả lập trong các bucket lab để hoàn thành:

1. Tải một object trước policy và một object sau policy; ghi lại khác biệt ở đích.
2. Kiểm tra đọc nội dung object sau policy tại region dự phòng.
3. Ghi đè và xóa một object thử nghiệm, quan sát kết quả và thời gian.
4. Copy object cũ sang bucket copy riêng, lưu work request và đối chiếu nội dung.
5. Thử chạy lại yêu cầu copy có điều kiện chống ghi đè; giải thích cách xử lý an toàn.
6. Viết runbook chuyển ứng dụng sang DR, bao gồm quyết định mở ghi và ngăn writer cũ.
7. Đánh giá chi phí nếu lượng ghi đè tăng nhiều dù dung lượng cuối kỳ gần như không đổi.

Kết quả cần có: sơ đồ nguồn–đích, phạm vi IAM, manifest nhỏ, bằng chứng đọc ở đích, độ trễ quan sát được và các bước chuyển vùng. Không dùng một trạng thái ACTIVE duy nhất làm tiêu chí hoàn thành.

Sau buổi lab, xác định dữ liệu nào phải giữ, dừng quan hệ replication theo kế hoạch rồi dọn các tài nguyên thử nghiệm khi đã kiểm tra đúng phạm vi. Không dọn bucket đang được ứng dụng sử dụng.

## 13. Ghi nhớ khi thiết kế

Bắt đầu từ dữ liệu và yêu cầu phục hồi: dữ liệu nào cần có ở region khác, có cho phép mất cập nhật gần nhất không, có cần lịch sử không và ứng dụng sẽ chọn nơi đọc/ghi bằng cách nào.

Triển khai tốt cần chứng minh cả ba việc: quan hệ replication được cấu hình đúng, dữ liệu đích đáp ứng mốc phục hồi cần thiết và ứng dụng dự phòng thực hiện được nghiệp vụ. Replication, CopyObject, manifest và runbook phối hợp để tạo ra bằng chứng đó.