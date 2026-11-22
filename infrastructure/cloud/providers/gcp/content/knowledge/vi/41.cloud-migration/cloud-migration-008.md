# Storage Transfer Service và di chuyển dữ liệu đối tượng

Khi di chuyển ứng dụng lên Google Cloud, một phần lớn dữ liệu có thể đã nằm trong Amazon S3, Azure Blob Storage, bucket Cloud Storage ở project khác hoặc hệ thống lưu trữ tại trung tâm dữ liệu. Dữ liệu này thường được lưu dưới dạng **object**: một tên đối tượng, nội dung và metadata, thay vì những bảng có schema quan hệ. Di chuyển hàng triệu object bằng một vòng lặp copy tự viết không đơn giản: cần xử lý lỗi tạm thời, giới hạn API, xác thực, đối tượng thay đổi trong lúc sao chép, chi phí truyền dữ liệu và việc kiểm chứng sau chuyển.

**Storage Transfer Service (STS)** là dịch vụ Google Cloud quản lý quá trình di chuyển dữ liệu giữa những hệ thống lưu trữ được hỗ trợ. Bạn khai báo nguồn, đích, điều kiện chọn object, quy tắc ghi đè, lịch chạy và quyền truy cập. STS lập kế hoạch, thực hiện các transfer operation và cung cấp trạng thái, thống kê cùng thông tin lỗi. STS được tối ưu cho chuyển dữ liệu quy mô lớn; với một số tác vụ rất nhỏ, các lệnh Cloud Storage CLI có thể đơn giản hơn.

Trong module CLOUD_PROVIDERS_GCP, STS nối phần tổ chức project, IAM và VPC với Cloud Storage, bảo vệ dữ liệu, tự động hóa và theo dõi chi phí. Di chuyển dữ liệu đối tượng thành công đòi hỏi thiết kế bucket đích, phân quyền service agent, chọn chính sách copy phù hợp và xác minh khả năng truy cập trước khi chuyển ứng dụng sang nguồn dữ liệu mới.

Sau bài học này, bạn có thể:

- Phân biệt Storage Transfer Service với lệnh sao chép thủ công, Storage Transfer Agent và Transfer Appliance.
- Chọn nguồn/đích được hỗ trợ và biết khi nào cần agent pool.
- Chuẩn bị bucket, service agent, IAM và các ràng buộc bảo mật trước khi chạy.
- Tạo job Cloud Storage-to-Cloud Storage bằng Google Cloud CLI theo cách không xóa dữ liệu nguồn.
- Cấu hình overwrite, delete, prefix filter, manifest, lịch chạy và event-driven transfer.
- Theo dõi transfer job và operation, xử lý lỗi và xác minh tính toàn vẹn.
- Lập kế hoạch initial copy, incremental sync, cutover và rollback.
- Ước lượng yếu tố chi phí và thiết lập checklist migration production.

## 1. Chọn công cụ di chuyển dữ liệu phù hợp

Không phải mọi lần copy object đều cần STS. Trước khi chọn công cụ, hãy xác định vị trí dữ liệu, dung lượng, số object, thời gian dừng dịch vụ được phép và yêu cầu sao chép lặp lại.

| Công cụ | Thế mạnh | Khi cân nhắc |
|---|---|---|
| \`gcloud storage cp\` hoặc \`gcloud storage rsync\` | Dễ dùng từ terminal hoặc script; phù hợp tập dữ liệu nhỏ và thao tác một lần | Sao chép ít object, thử nghiệm, thao tác vận hành ngắn |
| **Storage Transfer Service** | Quản lý job, operation, lịch, thống kê và retry; tối ưu dữ liệu lớn | Chuyển nhiều object giữa cloud, di chuyển project, copy lặp lại hoặc cần giám sát |
| **Agent-based Storage Transfer** | Chạy transfer agent gần hệ thống nguồn/đích; tận dụng kết nối và băng thông được kiểm soát | File system on-premises, HDFS hoặc S3-compatible storage |
| **Transfer Appliance** | Thiết bị vật lý để chuyển khối dữ liệu lớn khi băng thông WAN hạn chế | Dữ liệu rất lớn nhưng không thể chuyển hiệu quả qua mạng trong thời hạn yêu cầu |
| Công cụ chuyên cho CSDL | Hiểu schema, log giao dịch, replication hoặc CDC | Chuyển dữ liệu quan hệ, giao dịch hay database có yêu cầu consistency riêng |

STS thao tác với các object và file theo nguồn/đích hỗ trợ; nó không tự di chuyển database schema, sửa đường dẫn trong ứng dụng, thiết kế IAM đích hoặc bảo đảm workflow nghiệp vụ có transaction consistency. Với database, hãy dùng công cụ migration/replication phù hợp của loại cơ sở dữ liệu đó.

Google Cloud mô tả STS là dịch vụ tối ưu cho những lần chuyển lớn hơn khoảng 1 TiB. Đây là gợi ý lựa chọn công cụ, không phải điều kiện bắt buộc để tạo job.

## 2. Nguồn và đích nào được hỗ trợ?

STS hỗ trợ nhiều nguồn dữ liệu, nhưng không phải cặp nguồn–đích nào cũng có thể dùng ở cả hai chiều.

| Nguồn | Đích điển hình | Mô hình | Lưu ý |
|---|---|---|---|
| Cloud Storage | Cloud Storage | Agentless | Có thể chuyển giữa bucket ở cùng hoặc khác project |
| Amazon S3 | Cloud Storage | Agentless | Cần cấp quyền đọc từ AWS cho STS; kiểm tra chi phí egress |
| Azure Blob Storage / ADLS Gen2 | Cloud Storage | Agentless | Cần cơ chế xác thực nguồn tương ứng |
| HTTP/HTTPS URL list | Cloud Storage | Agentless | Dùng danh sách URL công khai hoặc URL ký có thời hạn phù hợp |
| S3-compatible object storage | Cloud Storage | Agent-based | Cần agent pool và endpoint tới storage tương thích S3 |
| File system tại on-premises hoặc trên VM | Cloud Storage, và một số chiều ngược lại | Agent-based | Agent cần quyền đọc/ghi file system và kết nối mạng |
| HDFS | Cloud Storage | Agent-based | Cần agent và cấu hình truy cập HDFS |

Khi phạm vi di chuyển có hệ thống lưu trữ khác hoặc chiều chuyển đặc biệt, hãy kiểm tra trang **Supported sources and sinks** theo phiên bản dịch vụ hiện hành trước khi thiết kế. Đặc biệt, không giả định STS hỗ trợ chuyển Amazon S3 sang Azure Blob hay chuyển mọi loại nguồn vào mọi loại đích.

### Agentless transfer

Với chuyển giữa các cloud object store được hỗ trợ, Google quản lý worker truyền dữ liệu. Bạn chủ yếu cấu hình nguồn/đích, credentials hoặc quyền nguồn, quyền của STS service agent trên Cloud Storage và lịch chuyển.

### Agent-based transfer

Với file system, HDFS hoặc S3-compatible storage, cần chạy transfer agent trên máy có kết nối tới nguồn/đích. Các agent được nhóm vào **agent pool**; STS giao việc và thu nhận trạng thái. Bên cạnh service agent của STS, còn có **transfer agent account** dùng để xác thực tiến trình agent. Hai danh tính này có trách nhiệm IAM khác nhau.

~~~mermaid
flowchart LR
    C[Người quản trị hoặc CI] --> J[Storage Transfer Service job]
    J --> O[Transfer operation]
    O --> A[Google-managed workers]
    A --> S1[Cloud object source]
    A --> D[Cloud Storage destination]
    O --> P[Agent pool - khi cần]
    P --> S2[On-prem file system / HDFS / S3-compatible]
    P --> D
~~~

Sơ đồ mô tả hai nhánh kiến trúc. Một job cụ thể chỉ dùng nhánh thích hợp với loại nguồn và đích; không phải mọi transfer đều có agent pool.

## 3. Phân biệt transfer job và transfer operation

**Transfer job** là cấu hình lâu dài: nó lưu source, sink, options và lịch thực thi. **Transfer operation** là một lần chạy của job, có thời điểm bắt đầu, trạng thái, tiến độ và số liệu riêng.

Ví dụ một job đồng bộ bucket mỗi ngày có thể sinh nhiều operation qua các ngày. Khi xem kết quả, cần phân biệt job còn ENABLED với operation vừa hoàn tất thành công hay thất bại. Job có thể được tạo với tùy chọn không chạy ngay; ngược lại, tạo job qua CLI mà không đặt lịch hoặc \`--do-not-run\` có thể khởi động transfer ngay.

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| Job | Định nghĩa điều gì cần copy và khi nào chạy | \`transferJobs/1234567890\` |
| Operation | Một lần chạy cụ thể của job | \`transferOperations/...\` |
| Schedule | Chạy một lần, hằng ngày hoặc theo chu kỳ | Mỗi đêm trong giai đoạn đồng bộ |
| Event stream | Nghe sự kiện object mới/thay đổi | Pub/Sub cho Cloud Storage, SQS cho S3 |
| Agent pool | Cụm agent chạy gần nguồn/đích | \`onprem-transfer-agents\` |

STS giúp lập lịch và theo dõi dữ liệu. Nó không giữ một snapshot nhất quán của mọi object trên những nguồn liên tục thay đổi. Cần xử lý riêng tính nhất quán trong thời điểm cutover.

## 4. Khảo sát dữ liệu nguồn trước khi di chuyển

Một migration có thể bị kéo dài do quá nhiều object nhỏ dù tổng dung lượng không lớn. Hãy lập bảng kiểm kê trước khi tạo job:

- **Dung lượng và số lượng:** tổng bytes, số object, kích thước trung vị và phân bố kích thước.
- **Namespace:** prefix, cấu trúc tên object, ký tự đặc biệt và đối tượng có cùng tên ở đích.
- **Biến động:** tốc độ tạo/sửa/xóa object theo giờ hoặc ngày; có writer nào còn hoạt động không.
- **Versioning:** bucket có giữ nhiều generation/version không; bản lịch sử nào cần bảo toàn.
- **Metadata:** content type, cache-control, custom metadata, object ACL, timestamp và checksum.
- **Bảo mật:** dữ liệu nhạy cảm, IAM nguồn/đích, CMEK, retention policy, object hold và VPC Service Controls.
- **Chi phí:** băng thông nguồn, phí đọc/GET, egress giữa nhà cung cấp và lớp lưu trữ đích.
- **Đích sử dụng:** ứng dụng tra cứu object bằng tên nào, URL nào, bucket name nào và quy tắc phân quyền nào.

Một bản inventory cơ bản có thể dùng Cloud Storage CLI để xem object và metadata:

~~~bash
gcloud storage ls --recursive "gs://my-source-bucket/"
gcloud storage objects describe "gs://my-source-bucket/sample/data.csv" \
  --format="json(name,size,crc32c,md5Hash,contentType)"
~~~

Đây chỉ là ví dụ đọc thông tin; trong bucket có hàng triệu object, tránh xuất toàn bộ danh sách lên terminal. Có thể tạo manifest, báo cáo inventory hoặc dùng công cụ phân tích dữ liệu được tổ chức phê duyệt để tổng hợp theo prefix.

### Xác định mục tiêu chuyển

Trước khi chạy, thống nhất các tiêu chí:

1. Tập object cần chuyển và tập object được loại trừ.
2. Những metadata nào bắt buộc giữ nguyên.
3. Mức độ chênh lệch tạm thời giữa source và sink được chấp nhận.
4. RTO/RPO hoặc thời gian cutover cho hệ thống ứng dụng.
5. Quy tắc xử lý object bị sửa, bị xóa hoặc trùng tên ở đích.
6. Ai được quyết định chuyển traffic ứng dụng sang đích.
7. Cách phục hồi hoặc quay lại nguồn nếu xác minh không đạt.

Không chỉ dùng chỉ tiêu “job succeeded” làm điều kiện hoàn tất migration. Một operation hoàn tất nhưng cấu hình chọn sai prefix vẫn có thể khiến dữ liệu nghiệp vụ bị thiếu.

## 5. Chuẩn bị project, bucket và quyền IAM

### Ba phạm vi quyền cần phân biệt

1. **Project chạy STS:** người tạo/chạy/giám sát job cần role STS phù hợp.
2. **Source bucket:** STS service agent cần quyền liệt kê, đọc object, và chỉ cần quyền xóa nếu cấu hình thực sự xóa nguồn.
3. **Destination bucket:** service agent cần quyền xem bucket, tạo/đọc object và quyền ghi đè/xóa nếu được yêu cầu.

Vai trò thường dùng:

| Vai trò | Principal | Mục đích |
|---|---|---|
| \`roles/storagetransfer.admin\` | Người quản trị hoặc pipeline được ủy quyền | Tạo, cập nhật, xóa job và quản lý agent pools |
| \`roles/storagetransfer.user\` | Người vận hành job | Tạo, cập nhật và chạy job, không có quyền xóa job |
| \`roles/storagetransfer.viewer\` | Người giám sát | Xem job và operation |
| \`roles/storage.legacyBucketReader\` | STS service agent | Đọc thông tin bucket nguồn/đích theo yêu cầu tích hợp |
| \`roles/storage.objectViewer\` | STS service agent trên nguồn | Đọc object khi giữ nguyên nguồn |
| \`roles/storage.objectUser\` | STS service agent trên đích | Tạo/đọc/ghi đè và xử lý object theo yêu cầu transfer |
| \`roles/storagetransfer.transferAgent\` | Transfer agent account, khi dùng agents | Trao đổi công việc và báo cáo với STS |

Quyền thực tế phụ thuộc loại transfer, lựa chọn giữ ACL, việc xóa nguồn, đích dùng hierarchical namespace và chính sách tổ chức. Với chuyển GCS-to-GCS không xóa dữ liệu nguồn, cấu hình vai trò ở bảng trên là một điểm bắt đầu thường dùng. Đừng cấp Storage Admin ở cấp project nếu chỉ cần quyền trên một bucket.

### Service agent của Storage Transfer Service

STS dùng một **Google-managed service agent** có dạng:

~~~text
project-PROJECT_NUMBER@storage-transfer-service.iam.gserviceaccount.com
~~~

Đây là danh tính gắn với **project quản lý transfer job**. Nó có thể truy cập source hoặc destination bucket ở project khác nếu được cấp quyền tương ứng trên bucket đó.

Có thể lấy chính xác email service agent bằng Storage Transfer Service API:

~~~bash
export TRANSFER_PROJECT_ID="migration-control-prod"

gcloud services enable storagetransfer.googleapis.com \
  --project="$TRANSFER_PROJECT_ID"

curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://storagetransfer.googleapis.com/v1/googleServiceAccounts/$TRANSFER_PROJECT_ID"
~~~

Response có trường \`accountEmail\`. Hãy copy email này vào biến \`SERVICE_AGENT_EMAIL\` cho những lệnh cấp quyền bên dưới. Không suy service agent email từ project ID; cần project number chính xác.

### Cấp quyền cho bài thực hành GCS-to-GCS

Ví dụ các bucket thuộc hai project khác nhau và job được quản lý trong \`migration-control-prod\`. Chọn bucket cụ thể:

~~~bash
export SOURCE_BUCKET="source-objects-example"
export DEST_BUCKET="destination-objects-example"
export SERVICE_AGENT_EMAIL="project-123456789012@storage-transfer-service.iam.gserviceaccount.com"
~~~

Giá trị service agent email bên trên chỉ là mẫu. Thay bằng \`accountEmail\` vừa lấy từ API. Giữ nguyên dữ liệu nguồn và cấp quyền tối thiểu cho một lần copy:

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$SOURCE_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.legacyBucketReader"

gcloud storage buckets add-iam-policy-binding "gs://$SOURCE_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$DEST_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.legacyBucketReader"

gcloud storage buckets add-iam-policy-binding "gs://$DEST_BUCKET" \
  --member="serviceAccount:$SERVICE_AGENT_EMAIL" \
  --role="roles/storage.objectUser"
~~~

Người chạy các lệnh trên phải có quyền sửa bucket IAM policies. Nếu cấu hình yêu cầu xóa source hoặc giữ object ACL, hãy kiểm tra quyền bổ sung trong tài liệu STS. Khi tạo job trong Console và người dùng có quyền cần thiết, Console có thể hướng dẫn tự cấp role cho service agent; CI/CD thường cần cấu hình IAM tường minh.

## 6. Thực hành: chuyển object giữa hai bucket Cloud Storage

Mục tiêu: tạo job copy dữ liệu từ bucket nguồn sang bucket đích, **không xóa nguồn**, tránh tạo operation trước khi cấu hình đã được review, sau đó chạy và theo dõi.

### Bước 1: Chuẩn bị bucket và vị trí lưu

Đảm bảo hai bucket đã tồn tại, bucket đích có location, storage class, default encryption và chính sách phù hợp. Nếu cần tạo bucket mới:

~~~bash
gcloud storage buckets create "gs://$DEST_BUCKET" \
  --project="destination-project-prod" \
  --location="asia-southeast1" \
  --uniform-bucket-level-access
~~~

Chỉ chạy lệnh tạo nếu bucket đích chưa tồn tại. Nếu đã tồn tại, kiểm tra metadata thay vì tạo lại. Location, retention policy, lifecycle rules và khả năng đọc dữ liệu bằng ứng dụng phải được thiết kế trước khi copy.

### Bước 2: Tạo transfer job nhưng chưa chạy

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --description="Initial GCS object migration, non-destructive" \
  --overwrite-when=different \
  --do-not-run
~~~

Ý nghĩa:

- \`gs://$SOURCE_BUCKET\` là nguồn; bucket destination là nơi nhận.
- \`--overwrite-when=different\` yêu cầu ghi đè khi đối tượng đích được xác định là khác nguồn theo cơ chế so sánh của STS.
- Không dùng \`--delete-from\`: job không được yêu cầu xóa object khỏi source hoặc sink.
- \`--do-not-run\` tạo cấu hình nhưng chưa bắt đầu copy.

Lệnh trả về **job name** có dạng \`transferJobs/...\`. Lưu chính xác job name từ output, không đoán ID. Trước khi chạy, mở lại cấu hình:

~~~bash
gcloud transfer jobs describe "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Kiểm tra đúng source/sink, prefix, delete option, overwrite và lịch. Trong production, nên tạo job thử với một prefix nhỏ trước khi mở rộng toàn bộ bucket.

### Bước 3: Chạy thủ công

~~~bash
gcloud transfer jobs run "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Với job lớn, thao tác này bắt đầu một operation và không nhất thiết chờ tới khi mọi object đã được chuyển. Bạn có thể dùng \`--no-async\` nếu muốn CLI chờ operation kết thúc, nhưng cần cân nhắc thời gian chạy và timeout của môi trường CI.

### Bước 4: Theo dõi transfer

~~~bash
gcloud transfer jobs monitor "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"

gcloud transfer operations list \
  --job-names="transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Lấy operation name từ danh sách rồi xem chi tiết:

~~~bash
gcloud transfer operations describe "transferOperations/OPERATION_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Theo dõi trạng thái, số object/bytes được copy, bị skip, số lỗi và thời điểm hoàn tất. Sau khi operation kết thúc, kiểm chứng dữ liệu bằng bước riêng ở phần 11.

### Bước 5: Tái chạy hoặc cập nhật job

Một job có thể được chạy lại để chuyển các object mới hoặc object được cập nhật. Điều này hữu ích trong giai đoạn migration khi ứng dụng cũ vẫn ghi dữ liệu nguồn:

~~~bash
gcloud transfer jobs run "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Nếu cập nhật source/destination, filter hoặc overwrite options, hãy review sự thay đổi trước lần chạy tiếp theo. Không mặc định rằng mọi object cũ sẽ được copy lại; hành vi phụ thuộc transfer options, metadata và trạng thái ở source/sink.

## 7. Prefix filter, đường dẫn và manifest

Không phải migration nào cũng cần toàn bộ bucket. Bạn có thể chuyển theo namespace như \`images/\`, \`exports/\` hoặc \`logs/2026/\`.

### Source và destination path

Với gcloud CLI, có thể chỉ định prefix làm một “folder” trong đường dẫn:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET/exports/" \
  "gs://$DEST_BUCKET/archive/" \
  --project="$TRANSFER_PROJECT_ID" \
  --overwrite-when=different \
  --do-not-run
~~~

Dấu \`/\` cuối đường dẫn có ý nghĩa khi khai báo folder. Hãy thử với dữ liệu mẫu để hiểu cách tên object được nối vào prefix đích; Cloud Storage sử dụng namespace object, không phải hệ thống thư mục POSIX truyền thống trong mọi bucket.

### Include/exclude prefixes

STS cho phép giới hạn object bằng prefix hoặc thời gian sửa đổi:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --include-prefixes="exports/,reports/" \
  --exclude-prefixes="exports/tmp/" \
  --do-not-run
~~~

Khi source đã chỉ định folder, các prefix filter được diễn giải tương đối với folder đó. Điều kiện thời gian như \`--include-modified-after-absolute\` hay \`--include-modified-before-absolute\` hỗ trợ chọn object theo thời điểm sửa đổi; xem \`gcloud transfer jobs create --help\` cho định dạng đối số hiện hành.

Không dùng prefix filter để kiểm tra quyền IAM. Filter chỉ chọn đối tượng cần chuyển; service agent vẫn phải có quyền đọc các tài nguyên cần truy cập theo cơ chế dịch vụ.

### Dùng manifest cho danh sách chính xác

**Manifest** là tệp CSV liệt kê những object/file cần chuyển. Với object storage, cột đầu là object name tương đối với source path; cột thứ hai có thể chứa generation của Cloud Storage object khi cần một phiên bản cụ thể.

Ví dụ \`objects.csv\`:

~~~csv
customers/2026/part-0001.json
customers/2026/part-0002.json
invoices/2025/invoice-042.pdf
~~~

Upload manifest vào bucket được STS có quyền đọc, rồi tham chiếu:

~~~bash
gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --manifest-file="gs://migration-manifests/objects.csv" \
  --do-not-run
~~~

Manifest phù hợp khi chỉ chuyển một tập object đã duyệt, di chuyển theo batch hoặc cần chỉ rõ generation. Không chỉnh sửa manifest trong lúc operation đang chạy. Đảm bảo đường dẫn trong CSV, dấu phân cách và encoding UTF-8 đúng theo tài liệu của loại nguồn đang dùng.

### Object versioning

Một lần chuyển bucket thông thường không mặc nhiên bảo toàn toàn bộ lịch sử versions của mọi object. Nếu phải chuyển non-current generations, hãy sử dụng quy trình manifest có generation và bật object versioning trên đích theo hướng dẫn GCS-to-GCS. Không tuyên bố migration “đã bảo toàn lịch sử” nếu chỉ kiểm tra current objects.

## 8. Ghi đè, xóa và bảo toàn metadata

Các lựa chọn dưới đây có thể thay đổi dữ liệu ở đích hoặc nguồn. Chúng cần được xác nhận từ inventory và mục tiêu migration.

| Lựa chọn | Ý nghĩa | Khi dùng |
|---|---|---|
| Không ghi đè object đã có | Giữ object ở đích nếu tên đã tồn tại | Thử nghiệm, import một lần, tránh ghi đè dữ liệu đích |
| \`--overwrite-when=different\` | Ghi đè khi STS xác định object đích khác nguồn | Incremental sync trong quá trình migration |
| \`--overwrite-when=always\` | Luôn thay object trùng tên ở đích | Khi cần copy lại toàn bộ theo chính sách đã duyệt |
| \`--delete-from=destination-if-unique\` | Xóa ở sink những object không có ở source | Đồng bộ mirror chặt chẽ; chỉ sau khi xác minh |
| \`--delete-from=source-after-transfer\` | Xóa object ở nguồn sau khi chuyển | Chuyển sở hữu dữ liệu; rủi ro cao nếu chưa có rollback |
| \`--preserve-metadata\` | Chọn trường metadata được giữ khi copy | Khi downstream phụ thuộc content type, ACL hoặc metadata |

Không bật hai tùy chọn xóa trong lần thử nghiệm đầu tiên. Nếu bucket đích có retention policy, legal hold hoặc versioning, việc ghi đè/xóa có thể tạo version mới hoặc bị chặn. Một số metadata và quyền ACL không thể bảo toàn nguyên vẹn do cấu hình bucket đích hoặc khác biệt giữa nhà cung cấp.

### ACL và uniform bucket-level access

Nếu bucket đích dùng Uniform Bucket-Level Access, quyền được quản lý bằng IAM thay vì object ACL. Những ứng dụng còn phụ thuộc vào ACL riêng từng object cần được cập nhật thiết kế phân quyền; STS không thể biến object ACL thành một mô hình IAM tương đương một cách tự động.

### Content type và custom metadata

Metadata như \`contentType\`, \`cacheControl\` hay custom metadata có thể ảnh hưởng cách ứng dụng đọc object. Hãy chỉ định yêu cầu bảo toàn và kiểm tra lại sau copy. Ngoài nội dung bytes, migration có thể được xem là chưa hoàn tất nếu một object JSON được phục vụ với content type sai hoặc cache policy thay đổi.

## 9. Lịch chạy, incremental transfer và event-driven transfer

### Chạy một lần hoặc theo lịch

STS có thể chạy một lần hoặc định kỳ theo schedule đã cấu hình. Trong Console, người dùng có thể chọn chạy một lần, hằng ngày, hằng tuần hoặc custom frequency. Qua gcloud CLI có các tùy chọn như \`--schedule-starts\`, \`--schedule-repeats-every\` và \`--schedule-repeats-until\`.

Với migration một lần, bạn có thể tạo job ở trạng thái chưa chạy, kiểm tra rồi chạy thủ công. Với source còn liên tục ghi dữ liệu, nên có các operation lặp lại để giảm lượng dữ liệu chưa đồng bộ trước cutover.

### Event-driven transfer

Event-driven transfer nghe sự kiện object được thêm hoặc cập nhật, thay vì liên tục quét toàn bộ source:

| Nguồn | Nguồn sự kiện | Đích |
|---|---|---|
| Cloud Storage | Pub/Sub subscription từ Cloud Storage notifications | Cloud Storage |
| Amazon S3 | S3 Event Notifications qua Amazon SQS | Cloud Storage |
| Azure Blob Storage / ADLS Gen2 | Azure Event Grid qua Azure Storage Queues | Cloud Storage |

Event-driven transfer có thể đưa object mới sang đích gần thời gian thực khi nguồn phát sự kiện và các hệ thống hoạt động bình thường. **Object deletions không được phát hiện qua cơ chế này**: xóa object ở nguồn không có nghĩa object cùng tên tự biến mất khỏi đích.

Ví dụ mô hình Cloud Storage:

~~~mermaid
flowchart LR
    W[Ứng dụng ghi object] --> S[Source bucket]
    S --> N[Cloud Storage notification]
    N --> T[Pub/Sub topic]
    T --> Q[Subscription riêng cho job]
    Q --> J[Event-driven STS job]
    J --> D[Destination bucket]
~~~

Để dùng event-driven, service agent cần quyền Pub/Sub Subscriber trên subscription phù hợp, bên cạnh quyền đối với các bucket. Mỗi transfer job dùng subscription riêng. Có thể tạo notification và subscription bằng gcloud, sau đó dùng \`--event-stream-name\` khi tạo job:

~~~bash
gcloud storage buckets notifications create "gs://$SOURCE_BUCKET" \
  --topic="object-transfer-events"

gcloud pubsub subscriptions create "object-transfer-sub" \
  --topic="object-transfer-events" \
  --ack-deadline=300

gcloud transfer jobs create \
  "gs://$SOURCE_BUCKET" \
  "gs://$DEST_BUCKET" \
  --project="$TRANSFER_PROJECT_ID" \
  --event-stream-name="projects/notification-project/subscriptions/object-transfer-sub"
~~~

Đây là minh họa cấu trúc lệnh, không phải toàn bộ cấu hình quyền. Cần tạo topic và subscription ở đúng project, cấp quyền publish cho Cloud Storage service agent và quyền subscribe cho STS service agent, đồng thời đặt thông số thời gian event stream theo nhu cầu. Không chạy đồng thời với job bulk migration khi chưa hiểu quy tắc chuyển trùng.

### Chọn giữa scheduled và event-driven

- **Scheduled transfer:** phù hợp với khối dữ liệu thay đổi theo chu kỳ, chấp nhận độ trễ từ giờ tới ngày hoặc khi cần kiểm kê lại toàn bộ source.
- **Event-driven:** phù hợp khi muốn cập nhật object mới và object được sửa với độ trễ thấp hơn; cần vận hành queue/topic và kiểm tra chênh lệch dữ liệu định kỳ.
- **Initial copy + incremental + cutover:** thường là mô hình an toàn cho migration có ứng dụng tiếp tục ghi nguồn trong lúc copy.

## 10. Di chuyển từ Amazon S3, Azure và nguồn on-premises

### Amazon S3 đến Cloud Storage

Một transfer agentless từ Amazon S3 tới Cloud Storage cần:

1. Xác định bucket, region, prefix và loại object ở AWS.
2. Cấp quyền đọc/list trên source qua cơ chế xác thực AWS được STS hỗ trợ.
3. Cấp quyền ghi Cloud Storage cho STS service agent trên đích.
4. Chọn overwrite, deletion, metadata preservation và schedule.
5. Chạy pilot với prefix nhỏ, theo dõi egress/requests rồi mở rộng.

Source có dạng \`s3://bucket/path\`, destination có dạng \`gs://bucket/path\`. Với tích hợp AWS IAM role, AWS access keys hoặc credential file, hãy làm theo tài liệu cấu hình nguồn hiện hành. Không đặt access key trực tiếp trong lệnh command line, README hoặc log CI.

### Azure Blob Storage và ADLS Gen2

STS hỗ trợ nguồn Azure Blob Storage hoặc ADLS Gen2 với đích Cloud Storage. Cần chuẩn bị quyền đọc và thông tin xác thực nguồn phù hợp; với event-driven, cấu hình Azure Event Grid và Storage Queues để phát thông báo cập nhật. Kiểm tra khác biệt metadata, naming rules và storage tiers trước khi copy dữ liệu lớn.

### S3-compatible storage

Với hệ thống tương thích S3 nhưng không phải Amazon S3, STS dùng **agent-based transfer**. Cần tạo agent pool và triển khai transfer agents có network route tới endpoint nguồn. Có thể cấu hình endpoint, region ký request, giao thức mạng và phương thức xác thực trong transfer job.

Đảm bảo agent có CPU, RAM, disk và băng thông để đọc nguồn; không coi agent chỉ là thành phần điều khiển. Đường truyền giữa agent và đích Google Cloud là một phần quan trọng của throughput.

### File system và HDFS

Với file system on-premises, agent chạy trên máy có thể đọc đường dẫn nguồn; job trỏ tới \`posix:///absolute/path\`. Nếu chuyển giữa hai file system, cần agent pool cho cả nguồn/đích và một Cloud Storage bucket trung gian theo hướng dẫn STS. Những trường hợp này không phải chuyển object cloud-to-cloud agentless; cần thiết kế kỹ quyền file system và network.

## 11. Giám sát operation và xác minh dữ liệu

### Theo dõi ngay trong Storage Transfer Service

Mỗi operation cho biết số lượng object và bytes đã chuyển, skip và lỗi. Trong Google Cloud Console, mở Storage Transfer Service → Jobs → job → lần chạy tương ứng để xem trạng thái và error details.

CLI cơ bản:

~~~bash
gcloud transfer jobs describe "transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"

gcloud transfer operations list \
  --job-names="transferJobs/JOB_ID" \
  --project="$TRANSFER_PROJECT_ID"
~~~

Phân biệt operation hoàn tất (DONE) với kết quả thành công không có lỗi: hãy đọc error counts và trạng thái cuối cùng của operation, không chỉ nhìn job đã kết thúc.

### Cơ chế kiểm tra toàn vẹn của STS

STS sử dụng checksum từ nguồn khi có, kết hợp metadata và phép tính checksum trong luồng chuyển để phát hiện lỗi dữ liệu. Khi nguồn không cung cấp checksum phù hợp, STS có thể phải dựa vào size và checksum tính trên luồng truyền. Một số nguồn AWS S3 multipart hoặc mã hóa bởi AWS KMS không cung cấp MD5 có thể so sánh trực tiếp với MD5 ở đích.

Điều này không có nghĩa STS đã xác minh toàn bộ yêu cầu nghiệp vụ sau migration. Google khuyến nghị kiểm tra thêm:

- Có đúng tập object và số lượng object mong đợi không?
- Object được chuyển có đúng phiên bản/generation mong muốn không?
- Kích thước và checksum có khớp khi có đủ metadata để so sánh không?
- Content type, cache policy và custom metadata quan trọng có được bảo toàn không?
- Tên object và đường dẫn mà ứng dụng sử dụng có đúng không?

### Đối chiếu mẫu trên GCS

Chọn một vài object đại diện: object nhỏ, lớn, tên có ký tự đặc biệt, metadata tùy chỉnh, và object mới được ghi gần lúc transfer:

~~~bash
gcloud storage objects describe \
  "gs://$SOURCE_BUCKET/customers/2026/sample.json" \
  --format="json(name,size,crc32c,md5Hash,contentType)"

gcloud storage objects describe \
  "gs://$DEST_BUCKET/customers/2026/sample.json" \
  --format="json(name,size,crc32c,md5Hash,contentType)"
~~~

Đối với migration lớn, hãy tạo báo cáo kiểm kê có cấu trúc hoặc chạy công cụ kiểm chứng để đối chiếu toàn bộ key set và mẫu checksum theo rủi ro. GCS CRC32C được hỗ trợ rộng; MD5 không phải lúc nào cũng có mặt, đặc biệt với composite objects. Không so sánh S3 ETag như thể mọi ETag đều là MD5 nội dung.

### Cloud Logging, Cloud Monitoring và thông báo

STS tích hợp log và metric để theo dõi tiến độ, bytes đã chuyển, errors và trạng thái operation. Có thể cấu hình Cloud Logging khi tạo job và Pub/Sub notifications cho sự kiện transfer. Khi chạy production, nên dựng dashboard và cảnh báo cho operation thất bại, lỗi permission, không có tiến độ kéo dài hoặc tỷ lệ lỗi tăng.

Tránh ghi URL đã ký, access key, object path nhạy cảm hoặc nội dung object vào log ứng dụng. Nếu log có tên đối tượng nhạy cảm, giới hạn quyền truy cập và retention của log.

## 12. Quy trình migration với dữ liệu đang thay đổi

Khi source còn có writer, bài toán lớn nhất không phải copy bytes mà là xác định thời điểm chuyển sang destination mà không mất cập nhật.

~~~mermaid
flowchart TD
    A[Inventory và chuẩn bị đích] --> B[Pilot prefix nhỏ]
    B --> C[Initial bulk copy]
    C --> D[Incremental sync hoặc event stream]
    D --> E{Chênh lệch đã đạt ngưỡng?}
    E -->|Chưa| D
    E -->|Đạt| F[Freeze/quiesce writes ở source]
    F --> G[Final sync và đối chiếu]
    G --> H{Kiểm chứng PASS?}
    H -->|Không| I[Sửa lỗi và chạy lại]
    I --> G
    H -->|Có| J[Chuyển ứng dụng sang destination]
    J --> K[Theo dõi và giữ rollback window]
~~~

### Giai đoạn 1: Initial bulk copy

Chạy job không xóa nguồn; dùng prefix và các lựa chọn overwrite phù hợp. Vì dữ liệu có thể thay đổi trong khi copy, kết quả sau bước này chỉ là bản gần đúng của source tại nhiều thời điểm khác nhau.

### Giai đoạn 2: Incremental transfer

Chạy lại job theo lịch hoặc dùng event-driven transfer để đưa các object mới/sửa sang đích. Theo dõi lag dự kiến và error count. Nếu một object đang bị ghi nhiều lần, cần hiểu quy tắc chọn version trước khi copy.

### Giai đoạn 3: Freeze và final sync

Trong cửa sổ cutover:

1. Tạm dừng writer hoặc chuyển ứng dụng sang chế độ chỉ đọc nếu được phép.
2. Đợi các request ghi đang chạy hoàn tất.
3. Chạy operation đồng bộ cuối cùng.
4. Đối chiếu số lượng, key set, checksum và metadata quan trọng.
5. Kiểm tra quyền ứng dụng tại bucket đích bằng service account thật.
6. Chỉ chuyển cấu hình ứng dụng khi tiêu chí kiểm chứng được đáp ứng.

Nếu không thể freeze writes, cần một cơ chế CDC/event stream và một quy tắc nhất quán rõ ràng. STS không tự cung cấp giao dịch nguyên tử giữa source và sink.

### Giai đoạn 4: Cutover và rollback

Sau cutover, theo dõi lỗi 403/404, độ trễ tải object và ảnh hưởng cache/CDN. Giữ source nguyên trạng trong khoảng rollback đã duyệt. Khi cần quay lại, phải xem xét dữ liệu mới chỉ xuất hiện ở destination để tránh mất cập nhật; rollback không đơn thuần là đổi bucket name về cũ.

Chỉ áp dụng chính sách xóa dữ liệu nguồn khi đã hoàn tất kiểm chứng, hết thời gian giữ rollback và có phê duyệt theo chính sách lưu trữ.

## 13. Bảo mật, compliance và dữ liệu nhạy cảm

### Nguyên tắc ít quyền nhất

- Cấp \`roles/storagetransfer.user\` hoặc custom role cho người chỉ vận hành job.
- Cấp bucket-scoped IAM cho đúng STS service agent của project quản lý job.
- Chỉ cấp quyền delete khi transfer có yêu cầu xóa đã được duyệt.
- Bảo vệ credentials của AWS/Azure/agent; ưu tiên cơ chế ủy quyền ngắn hạn hoặc do nền tảng quản lý.
- Tách project quản lý migration khỏi project production nếu phù hợp mô hình vận hành.
- Ghi lại ai có quyền sửa job, source/sink, lịch và delete options.

### CMEK và bucket đích

Bucket đích có thể dùng customer-managed encryption key (CMEK) nếu chính sách yêu cầu. Đảm bảo service agent hoặc service identity của Cloud Storage có quyền sử dụng khóa theo đúng mô hình mã hóa của dịch vụ và key location phù hợp. Kiểm tra cả khả năng đọc object sau copy bằng danh tính ứng dụng, không chỉ khả năng tạo object.

### Retention, holds và lifecycle

Object retention, legal hold và bucket lifecycle có thể ảnh hưởng khả năng ghi đè, xóa hoặc lưu giữ. Một job chuyển dữ liệu không tự động chuyển mọi policy ở cấp bucket. Hãy cấu hình retention/lifecycle tại destination và xác nhận điều kiện trước khi bật delete hoặc overwrite.

### VPC Service Controls và organization policy

Nếu các bucket nằm trong các service perimeter khác nhau, cần kiểm tra ingress/egress policies của VPC Service Controls để cho phép hoạt động transfer. Các organization policy như domain restricted sharing có thể chặn quyền cấp cho service agent cross-project. Điều tra policy trước khi mở rộng IAM quá mức.

## 14. Hiệu năng, quota và chi phí

Thời gian transfer không chỉ phụ thuộc tổng số GB. Các yếu tố quan trọng:

- Số lượng object và phân bố kích thước: hàng triệu object nhỏ làm tăng số request.
- Tốc độ đọc/list của source, quota và throttling của provider.
- Băng thông tới source, đặc biệt với agent-based transfer.
- Cách source mã hóa, lưu checksum và cung cấp metadata.
- Thời gian phát hiện thay đổi ở source và tần suất chạy incremental job.
- Số lần retry, số lỗi, thao tác kiểm tra và độ lớn metadata.

Chi phí có thể bao gồm xử lý STS theo mô hình định giá hiện hành, Cloud Storage operations, lưu trữ ở đích, phí egress từ nguồn AWS/Azure/region, chi phí agent VM/network và chi phí logging/monitoring. Không ước lượng chỉ theo dung lượng byte nếu có lượng object rất lớn hoặc giao dịch API thường xuyên.

Để dự báo:

1. Chọn một tập dữ liệu pilot đại diện cả object nhỏ và lớn.
2. Đo bytes/s, object/s, error rate và số API operations.
3. Ước lượng thời gian bulk copy theo dung lượng và số object, có dự phòng.
4. Tính chi phí đọc/egress của nguồn và storage class tại destination.
5. Lập lịch tránh đè lên workload nguồn và giới hạn network băng thông nếu cần.
6. Theo dõi quota và điều chỉnh agent pool khi là agent-based.

Không lấy tốc độ của vài object nhỏ làm chỉ số chắc chắn cho hàng trăm TB. Với agent-based transfer, nên benchmark một tập đủ lớn và kiểm tra năng lực network interface/CPU/disk của agent machines.

## 15. Troubleshooting: từ lỗi IAM tới dữ liệu thiếu

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Tạo job báo Permission denied | Người gọi thiếu STS role | Kiểm tra \`roles/storagetransfer.user/admin\` trên transfer project |
| Job đọc source thất bại | Service agent chưa có bucket metadata/object read | Xác nhận đúng service agent email và role trên bucket nguồn |
| Job ghi destination thất bại | Thiếu object write/read hoặc bucket metadata permission | Cấp role đúng trên bucket đích; kiểm tra retention/holds |
| Cross-project transfer bị chặn | Bucket IAM hoặc org policy/VPC SC ngăn service agent | Kiểm tra domain restrictions, service perimeter và IAM inheritance |
| Object không được copy | Prefix/filter/time condition/manifest loại object | Kiểm tra job spec, tên object thực, generation và filter |
| Job thành công nhưng thiếu dữ liệu mới | Source có writer sau lần chuyển; event stream không xử lý deletion | Chạy incremental/final sync và kiểm tra chênh lệch |
| Object bị ghi đè ngoài mong đợi | Chọn overwrite always/different sai mục tiêu | Review transfer options và versioning của destination |
| Không xóa được source/sink | Thiếu quyền xóa hoặc gặp retention/legal hold | Xem chính sách bucket và quyền; không bypass retention |
| Agent-based transfer chậm | Agent quá ít, nguồn chậm, WAN bị nghẽn | Benchmark, tăng agent hợp lý, kiểm tra CPU/disk/network |
| Lỗi đọc AWS/Azure | Credentials hết hạn hoặc provider từ chối request | Kiểm tra quyền nguồn, hạn token, throttling và egress |
| Metadata/ACL thay đổi | Chính sách metadata hoặc UBLA khác nhau | Kiểm tra cấu hình preservation và mô hình IAM đích |
| Checksum không so được | Nguồn không có checksum phù hợp, composite object, multipart ETag | So sánh checksum khả dụng, size và kiểm tra nội dung mẫu |

Khi xử lý sự cố, hãy mở **operation error details** trước, xác định đó là lỗi permission, object không tồn tại, quota, transient network hay dữ liệu đầu vào. Nếu lỗi chỉ ảnh hưởng một số object, không nhất thiết phải tạo job mới; có thể sửa nguyên nhân và chạy lại theo chính sách đã duyệt.

## 16. Checklist migration production

- [ ] Đã chốt tập object, tổng bytes, số lượng object, prefix và tính chất thay đổi.
- [ ] Đã chọn đúng loại nguồn/đích và xác định có cần transfer agents hay không.
- [ ] Đã xác định owner của source, destination và transfer project.
- [ ] Bucket đích đã có location, storage class, IAM, encryption và lifecycle phù hợp.
- [ ] Đã lấy chính xác STS service agent email và cấp đúng bucket-scoped roles.
- [ ] Có phương án credentials an toàn cho AWS, Azure hoặc transfer agent.
- [ ] Đã review prefix filter, manifest và versioning.
- [ ] Overwrite, delete và metadata preservation đã được phê duyệt.
- [ ] Pilot đủ đại diện đã chạy và có đối chiếu kết quả.
- [ ] Có dashboard/alert theo dõi operation, bytes, errors và stalled progress.
- [ ] Đã ước lượng egress, API operation, lưu trữ đích và chi phí agent.
- [ ] Nếu source còn ghi, đã thiết kế incremental sync hoặc event-driven transfer.
- [ ] Đã xác định freeze window, final sync, cutover owner và tiêu chí thành công.
- [ ] Đã kiểm tra checksum, key set, metadata và quyền truy cập của ứng dụng.
- [ ] Có rollback window; chưa xóa source trước khi kết thúc xác minh.
- [ ] Có tài liệu bàn giao job names, operations, cảnh báo và quy trình vận hành.

## 17. Bài tập áp dụng

Giả sử một doanh nghiệp có 12 TB ảnh và file JSON trong Cloud Storage project cũ. Ứng dụng đang ghi thêm khoảng 50 GB mỗi ngày. Mục tiêu chuyển sang project mới, region gần người dùng hơn, không mất ảnh và không làm gián đoạn dịch vụ quá một giờ.

Hãy thiết kế các bước:

1. Kiểm kê object theo prefix, size, metadata và tốc độ ghi mới.
2. Tạo bucket đích với location và chính sách phù hợp; xác nhận điều kiện IAM.
3. Cấp quyền STS service agent trên hai bucket.
4. Pilot một prefix nhỏ với \`--do-not-run\` rồi chạy thủ công sau khi review.
5. Chạy bulk transfer không xóa dữ liệu nguồn.
6. Dùng scheduled incremental job hoặc event-driven transfer để giảm delta.
7. Trong cửa sổ cutover, dừng writer, chạy final sync, đối chiếu key set và checksum, xác minh ứng dụng.
8. Chuyển cấu hình bucket trong ứng dụng, theo dõi 403/404 và latency; giữ đường rollback.

Câu hỏi mở: nếu nguồn vẫn ghi liên tục và không thể dừng một giờ, cơ chế nào giúp đồng bộ object mới và làm sao xử lý trường hợp object bị xóa? Gợi ý: event-driven transfer không tự phản ánh delete events; cần quy trình đối soát và chính sách xóa được kiểm soát.

## 18. Kết luận

Storage Transfer Service giúp chuyển dữ liệu đối tượng giữa các nguồn được hỗ trợ với job có thể lập lịch, theo dõi và chạy lại. Với chuyển giữa Cloud Storage, Amazon S3, Azure và một số nguồn cloud khác, dịch vụ có thể tự quản lý worker; với file system, HDFS và S3-compatible storage, cần agent pool. Thành công phụ thuộc vào thiết kế quyền cho service agent, lựa chọn overwrite/delete, xử lý metadata và validation sau copy.

Trong một migration thực tế, nên đi theo chuỗi **inventory → pilot → bulk copy → incremental → final sync → verify → cutover → monitor**. Giữ dữ liệu nguồn cho tới khi đã xác minh kết quả và hết rollback window. STS là công cụ chuyển dữ liệu, còn tính nhất quán nghiệp vụ và quyết định cutover vẫn cần được thiết kế, phê duyệt và kiểm thử bởi nhóm sở hữu ứng dụng.

## Tài liệu tham khảo

- [Storage Transfer Service overview](https://docs.cloud.google.com/storage-transfer/docs/overview)
- [Supported sources and sinks](https://docs.cloud.google.com/storage-transfer/docs/sources-and-sinks)
- [Create transfers](https://docs.cloud.google.com/storage-transfer/docs/create-transfers)
- [Transfer between Cloud Storage buckets](https://docs.cloud.google.com/storage-transfer/docs/cloud-storage-to-cloud-storage)
- [Required user permissions](https://docs.cloud.google.com/storage-transfer/docs/iam-user)
- [Configure Cloud Storage source access](https://docs.cloud.google.com/storage-transfer/docs/source-cloud-storage)
- [Configure Cloud Storage destination access](https://docs.cloud.google.com/storage-transfer/docs/sink-cloud-storage)
- [Agent-based project-level permissions](https://docs.cloud.google.com/storage-transfer/docs/iam-agent-based)
- [Manage transfers](https://docs.cloud.google.com/storage-transfer/docs/manage-transfers)
- [Transfer specific files or objects using a manifest](https://docs.cloud.google.com/storage-transfer/docs/manifest)
- [Event-driven transfers](https://docs.cloud.google.com/storage-transfer/docs/event-driven-transfers)
- [Event-driven transfers from Cloud Storage](https://docs.cloud.google.com/storage-transfer/docs/event-driven-google)
- [Data integrity](https://docs.cloud.google.com/storage-transfer/docs/data-integrity)
- [Storage Transfer Service pricing](https://cloud.google.com/storage-transfer/pricing)
