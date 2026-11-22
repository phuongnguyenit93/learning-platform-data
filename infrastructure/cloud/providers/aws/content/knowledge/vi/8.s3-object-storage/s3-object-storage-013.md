# Object Lock, Inventory, Storage Lens và Batch Operations

> **Chương:** Lưu trữ đối tượng S3  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — tìm hiểu hệ sinh thái AWS từ Region/AZ, IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp, serverless; luyện khả năng thiết kế ứng dụng an toàn, quan sát được, có phương án phục hồi và kiểm soát chi phí.

Khi một bucket Amazon S3 chứa hàng triệu đối tượng, quản trị lưu trữ không chỉ là tải lên và tải xuống. Tổ chức còn phải trả lời những câu hỏi như: **Làm sao ngăn việc xóa nhầm hồ sơ phải lưu 7 năm? Làm sao biết chính xác những object nào chưa mã hóa hoặc chưa có chính sách lưu giữ? Làm sao nhìn được xu hướng chi phí? Làm sao sửa hàng triệu object mà không tự viết script lặp nguy hiểm?**

Bốn tính năng dưới đây giải quyết các phần khác nhau của vấn đề:

| Tính năng | Câu hỏi chính | Kết quả điển hình |
| --- | --- | --- |
| **S3 Object Lock** | Object version nào phải được bảo vệ khỏi xóa/ghi đè đến thời điểm nào? | Thời hạn lưu giữ (*retention*), chế độ **Governance/Compliance**, **Legal Hold** |
| **S3 Inventory** | Trong bucket hiện có những object/version nào và thuộc tính của chúng là gì? | Báo cáo định kỳ dạng **CSV, ORC hoặc Parquet** lưu tại bucket đích |
| **S3 Storage Lens** | Dung lượng, số object, hoạt động, mức độ bảo vệ và xu hướng sử dụng đang ra sao? | Dashboard, metrics, phân tích theo account/Region/bucket và cấp chi tiết được hỗ trợ |
| **S3 Batch Operations** | Cần thực hiện cùng một thao tác với rất nhiều object/version như thế nào? | **Job** đọc manifest, thực hiện thao tác hàng loạt, báo cáo thành công/thất bại |

Điểm quan trọng: **Object Lock bảo vệ**, **Inventory liệt kê**, **Storage Lens quan sát xu hướng**, còn **Batch Operations thực hiện thay đổi**. Không tính năng nào tự thay thế hoàn toàn ba tính năng còn lại.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích quan hệ giữa Object Lock và S3 Versioning; phân biệt Governance, Compliance, Legal Hold và default retention.
2. Hiểu vì sao Object Lock bảo vệ **object version** và điều gì xảy ra khi DELETE không chỉ rõ `versionId`.
3. Thiết kế S3 Inventory theo lịch ngày/tuần, chọn định dạng, phạm vi current/all versions, thuộc tính tùy chọn và quyền ghi báo cáo.
4. Dùng S3 Storage Lens để phát hiện xu hướng sử dụng, lưu trữ không cần thiết và khoảng trống bảo vệ dữ liệu.
5. Lập kế hoạch S3 Batch Operations với manifest, IAM execution role, kiểm thử phạm vi, confirmation và completion report.
6. Kết hợp bốn tính năng để rà soát và xử lý dữ liệu ở quy mô lớn mà vẫn đảm bảo nguyên tắc đặc quyền tối thiểu và khả năng kiểm toán.

## 2. Bức tranh tổng thể: từ quan sát đến thay đổi

~~~mermaid
flowchart LR
    BUCKET["Bucket S3 nguồn\nObject + Versioning"]
    LOCK["Object Lock\nRetention / Legal Hold"]
    INV["S3 Inventory\nBáo cáo theo lịch"]
    LENS["S3 Storage Lens\nMetrics và xu hướng"]
    REPORT["Bucket báo cáo\nCSV / ORC / Parquet"]
    REVIEW["Người quản trị\nRà soát phạm vi"]
    BATCH["S3 Batch Operations\nJob theo manifest"]
    RESULT["Completion report\nThành công / Thất bại"]

    LOCK -->|"Bảo vệ version"| BUCKET
    BUCKET --> INV
    BUCKET --> LENS
    INV --> REPORT
    LENS --> REVIEW
    REPORT --> REVIEW
    REVIEW -->|"Phê duyệt manifest và thao tác"| BATCH
    BATCH -->|"API lên object/version được chọn"| BUCKET
    BATCH --> RESULT
~~~

*Sơ đồ thể hiện quy trình quản trị. Inventory và Storage Lens có thời gian làm mới riêng, không phải truy vấn trạng thái tức thời. Batch Operations vẫn chịu kiểm soát IAM, bucket policy, KMS và Object Lock.*

Trong một kiến trúc production, bốn tính năng này đi cùng các lớp khác:

- **IAM / bucket policy / KMS key policy** quyết định ai được đọc, ghi, thay đổi retention và thực hiện job.
- **Versioning, backup/replication, Object Lock** phục vụ khả năng khôi phục và yêu cầu lưu trữ dữ liệu.
- **CloudTrail, CloudWatch, S3 server access logs hoặc data events** hỗ trợ điều tra và quan sát theo cấu hình phù hợp.
- **AWS Budgets / Cost Explorer / Storage Lens** hỗ trợ nhìn vào chi phí và cơ hội tối ưu.

## 3. S3 Object Lock: WORM theo từng object version

**S3 Object Lock** hỗ trợ mô hình **Write Once Read Many (WORM)**: trong thời hạn được bảo vệ, một **phiên bản object cụ thể** không thể bị xóa hoặc ghi đè trực tiếp trái với các quy tắc lưu giữ. Tính năng này phù hợp cho log kiểm toán, chứng từ, bản sao lưu và hồ sơ có yêu cầu retention.

### 3.1. Điều kiện tiên quyết

- Object Lock được sử dụng với **general purpose bucket** có **S3 Versioning**.
- Khi bật Object Lock trên bucket, **Versioning được bật** và không thể suspend trong khi Object Lock được bật.
- Object Lock có thể được bật khi tạo bucket hoặc bật cho bucket hiện có theo hướng dẫn AWS. Một khi đã bật cho bucket, **không thể tắt lại Object Lock**.
- Không phải mọi loại bucket, storage class và API S3 đều hỗ trợ Object Lock với hành vi giống nhau. Kiểm tra rõ loại bucket và nhu cầu nghiệp vụ.

Object Lock gắn **retention hoặc legal hold với object version**, không chỉ với một chuỗi key. Ghi lên cùng key có thể tạo **version mới**, trong khi version cũ vẫn được bảo vệ.

### 3.2. Retention khác Legal Hold thế nào?

| Thuộc tính | Retention | Legal Hold |
| --- | --- | --- |
| Câu hỏi | “Giữ version tới ngày nào?” | “Version này đang bị giữ để phục vụ yêu cầu pháp lý/điều tra không?” |
| Cấu hình | **Mode** + **retain-until date** | Trạng thái **ON/OFF** |
| Thời hạn | Có thời điểm kết thúc | **Không tự hết hạn**; phải được gỡ bằng quyền phù hợp |
| Cách sử dụng | Chính sách lưu giữ định kỳ | Điều tra, tranh chấp, yêu cầu bảo toàn dữ liệu |
| Tác động | Bảo vệ version trong thời gian retention | Bảo vệ version khi hold đang ON |

**Retention và Legal Hold là hai cơ chế độc lập.** Nếu một version hết hạn retention nhưng vẫn đang bật Legal Hold, version đó tiếp tục được bảo vệ. Ngược lại, gỡ Legal Hold không cho phép xóa một version khi retention vẫn còn hiệu lực.

### 3.3. Governance mode và Compliance mode

| Đặc tính | **Governance** | **Compliance** |
| --- | --- | --- |
| Mục tiêu | Bảo vệ khỏi thay đổi thông thường, vẫn có đường xử lý ngoại lệ kiểm soát | Lưu giữ chặt chẽ trong thời hạn đã xác định |
| Có thể xóa version đang được giữ trước hạn? | Chỉ khi principal có **quyền bypass** phù hợp và request chủ động chỉ rõ bypass | **Không có quyền IAM nào cho phép bỏ qua** retention chưa hết hạn |
| Có thể rút ngắn retention? | Có thể theo cơ chế bypass được cấp quyền | Không được rút ngắn đối với version đã ở Compliance mode |
| Ai nên có quyền? | Rất ít vai trò vận hành ngoại lệ | Chọn retention thận trọng trước khi ghi dữ liệu |
| Rủi ro khi cấu hình sai | Role có `BypassGovernanceRetention` quá rộng có thể phá bảo vệ | Thời hạn dài hơn nhu cầu có thể khiến dữ liệu không thể xóa, tiếp tục phát sinh phí |

Trong **Governance mode**, để bỏ qua retention khi thao tác được hỗ trợ, principal cần quyền `s3:BypassGovernanceRetention` **và** request phải chỉ rõ header `x-amz-bypass-governance-retention:true`. AWS Console có thể gửi header này khi người dùng có quyền bypass; vì thế **phải hạn chế chặt quyền IAM**, không chỉ dựa vào một checkbox trong giao diện.

Trong **Compliance mode**, AWS ngăn việc xóa/ghi đè **version đang được giữ** trước ngày hết hạn, kể cả bởi quản trị viên trong tài khoản. Việc chọn Compliance là quyết định vận hành và tuân thủ cần được rà soát kỹ vì không thể dùng quyền quản trị thông thường để rút ngắn retention đã áp dụng.

### 3.4. Default retention và retention riêng từng version

Một bucket có thể được cấu hình **default retention** cho object mới, ví dụ Governance giữ 365 ngày hoặc Compliance giữ 7 năm. Khi PUT một object version mới mà không khai báo cấu hình retention riêng, default retention có thể được áp dụng theo thiết lập bucket.

~~~text
Bucket general purpose: audit-ledger-example
Object Lock: enabled
Versioning: enabled
Default retention: GOVERNANCE, 365 ngày

PUT audit/2026/tx-0001.json  -> version v1, giữ đến ngày tính theo policy
PUT audit/2026/tx-0001.json  -> version v2 mới, retention được xét riêng
~~~

Những điểm dễ bỏ sót:

- Bật default retention **không tự áp dụng ngược** cho mọi object/version đã có từ trước. Muốn bảo vệ dữ liệu cũ cần một quy trình gắn retention cho đúng version.
- Cấu hình retention cấp object/version và default retention tương tác theo quy tắc dịch vụ; cần hiểu trước khi tạo workflow upload.
- Một version có thể được **gia hạn** thời hạn retention theo quy tắc cho phép; việc **rút ngắn** hay thay mode phụ thuộc mode hiện hành và quyền.
- Nếu cần khóa dữ liệu lâu năm, hãy kiểm tra **lifecycle policies**: việc chuyển storage class hoặc xóa phiên bản phải tôn trọng retention và yêu cầu lưu giữ.

### 3.5. Điều gì xảy ra khi DELETE một key đang bị Object Lock?

Với bucket bật versioning, thao tác `DELETE Object` **không truyền version ID** thông thường tạo một **delete marker** là current version. Điều đó **không có nghĩa version trước bị xóa vĩnh viễn**, kể cả khi nó đang được bảo vệ bởi Object Lock.

~~~mermaid
sequenceDiagram
    participant U as Ứng dụng
    participant S as Bucket có Versioning + Object Lock
    U->>S: PUT record.json
    S-->>U: Version v1, đang được giữ
    U->>S: DELETE record.json (không version ID)
    S-->>U: Tạo delete marker hiện hành
    U->>S: GET record.json (không version ID)
    S-->>U: Không thấy body hiện hành
    Note over S: Version v1 vẫn được giữ trong lịch sử
~~~

Muốn xóa **permanent version v1** bằng `DELETE` có `versionId=v1` khi retention hoặc Legal Hold còn hiệu lực sẽ bị từ chối, trừ trường hợp bypass Governance hợp lệ. Vì thế, quy trình audit phải kiểm tra **version ID**, **delete markers**, retention và legal hold, không chỉ hỏi một key có đang GET được hay không.

### 3.6. Điều Object Lock không thay thế

- Không phải cơ chế phân quyền **đọc**: IAM và bucket policy vẫn quyết định ai được xem dữ liệu.
- Không đảm bảo ứng dụng không thể tạo **version mới** trên cùng key; bảo vệ version cũ khác với khóa toàn bộ namespace.
- Không thay thế backup, kiểm thử restore, replication hay bảo vệ trước lỗi ứng dụng.
- Không tự ngăn xóa nhầm dữ liệu **sau khi hết thời hạn**; chính sách lifecycle và quyền xóa vẫn quan trọng.
- Không phải “mutex” hoặc optimistic lock để hai worker cùng cập nhật một key.

## 4. Thiết kế IAM cho Object Lock

Các action IAM thường cần phân biệt:

| Action | Ý nghĩa |
| --- | --- |
| `s3:GetBucketObjectLockConfiguration` | Đọc cấu hình Object Lock ở bucket |
| `s3:PutBucketObjectLockConfiguration` | Thay cấu hình Object Lock/default retention cấp bucket |
| `s3:GetObjectRetention` | Đọc retention của một object version |
| `s3:PutObjectRetention` | Gắn/sửa retention khi quy tắc cho phép |
| `s3:GetObjectLegalHold` | Đọc trạng thái Legal Hold |
| `s3:PutObjectLegalHold` | Bật/tắt Legal Hold theo quyền |
| `s3:BypassGovernanceRetention` | Cho phép bỏ qua Governance retention trong thao tác hợp lệ |
| `s3:DeleteObjectVersion` | Xóa version cụ thể, vẫn chịu Object Lock |

**Nguyên tắc thiết kế:** phân chia quyền đọc kiểm toán, quyền cấu hình bucket, quyền gắn retention, quyền đặt Legal Hold và quyền bypass thành các role khác nhau. Đặc biệt `s3:BypassGovernanceRetention` không nên cấp cho pipeline tải object hàng ngày.

Ví dụ **identity-based policy chỉ đọc trạng thái Object Lock** của một bucket và các object bên trong:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBucketObjectLockConfig",
      "Effect": "Allow",
      "Action": "s3:GetBucketObjectLockConfiguration",
      "Resource": "arn:aws:s3:::audit-ledger-example"
    },
    {
      "Sid": "ReadObjectRetentionAndLegalHold",
      "Effect": "Allow",
      "Action": [
        "s3:GetObjectRetention",
        "s3:GetObjectLegalHold"
      ],
      "Resource": "arn:aws:s3:::audit-ledger-example/*"
    }
  ]
}
~~~

Đây là quyền **đọc metadata Object Lock**, không tự cấp `s3:GetObject` đọc nội dung, không cấp quyền gỡ hold hay thay retention. Với workflow xem danh sách version còn cần quyền `s3:ListBucketVersions` ở cấp bucket và các quyền liên quan. Quyền hiệu lực cuối cùng còn chịu IAM, bucket policy, SCP, permission boundary, KMS và các chính sách khác.

### 4.1. Kiểm tra bằng AWS CLI (chỉ đọc)

Giả sử bucket `audit-ledger-example` và key `records/2026/event-0001.json` là placeholder thuộc môi trường được phép:

~~~bash
aws s3api get-object-lock-configuration \
  --bucket audit-ledger-example

aws s3api list-object-versions \
  --bucket audit-ledger-example \
  --prefix records/2026/

aws s3api get-object-retention \
  --bucket audit-ledger-example \
  --key records/2026/event-0001.json \
  --version-id EXAMPLE_VERSION_ID

aws s3api get-object-legal-hold \
  --bucket audit-ledger-example \
  --key records/2026/event-0001.json \
  --version-id EXAMPLE_VERSION_ID
~~~

Các lệnh chỉ quan sát trạng thái, không gỡ retention. Thay `EXAMPLE_VERSION_ID` bằng version ID thật; cùng một key có thể có nhiều version với **thời hạn và trạng thái hold khác nhau**. Nếu API trả `AccessDenied`, cần kiểm tra quyền/đường dẫn và policy, không mặc định bucket thiếu Object Lock.

## 5. S3 Inventory: danh sách object và thuộc tính theo lịch

**S3 Inventory** tạo báo cáo về object trong **general purpose bucket** theo lịch. Nó là giải pháp hữu ích khi cần nhìn số lượng lớn object ở cấp từng key, thay vì liên tục gọi API `ListObjectsV2` và nhiều API `HeadObject` riêng lẻ.

### 5.1. Chọn phạm vi và định dạng

Một cấu hình Inventory thường gồm:

| Thuộc tính | Ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| **Source bucket** | `audit-ledger-example` | Bucket nào cần kiểm kê? |
| **Prefix filter** (tùy chọn) | `records/2026/` | Chỉ lấy một phần object hay toàn bucket? |
| **Included object versions** | `Current` hoặc `All` | Chỉ current version hay cả noncurrent versions/delete markers tương ứng? |
| **Schedule** | `Daily` hoặc `Weekly` | Tần suất báo cáo cần thiết? |
| **Output format** | `CSV`, `ORC` hoặc `Parquet` | Người dùng đọc thủ công hay truy vấn bằng Athena? |
| **Optional fields** | Size, StorageClass, EncryptionStatus, Object Lock metadata | Những thuộc tính nào giúp trả lời yêu cầu kiểm toán? |
| **Destination bucket/prefix** | `inventory-audit-destination/reports/` | Ai có quyền đọc báo cáo? Giữ báo cáo bao lâu? |

Khi kiểm toán Object Lock, nên cân nhắc cấu hình **All versions** và các trường tùy chọn liên quan như **ObjectLockRetainUntilDate**, **ObjectLockMode**, **ObjectLockLegalHoldStatus**, tùy định dạng/tính năng mà cấu hình Inventory hiện hành hỗ trợ. Không chỉ nhìn current version nếu quy định áp dụng cho cả phiên bản cũ.

**Inventory là báo cáo định kỳ, không phải API truy vấn trạng thái thời gian thực.** Báo cáo đầu tiên có thể cần thời gian để xuất hiện; các thay đổi PUT/DELETE mới nhất không nhất thiết lập tức có mặt trong tệp Inventory. Tính nhất quán mạnh của GET/LIST trực tiếp trên S3 **không biến snapshot Inventory thành báo cáo realtime**.

### 5.2. Báo cáo được đặt ở đâu?

~~~text
Source bucket: audit-ledger-example
  ├── records/2026/event-0001.json
  └── records/2026/event-0002.json

Destination bucket: inventory-audit-destination
  └── reports/...
      ├── manifest.json
      └── data file(s): CSV / ORC / Parquet
~~~

Đường dẫn cụ thể còn gồm cấu trúc do S3 Inventory tạo (theo cấu hình và thời gian báo cáo), không được giả định luôn có đúng một data file. **Manifest của báo cáo Inventory** mô tả tập tệp xuất ra; không nên coi tên manifest đó giống hoàn toàn định dạng manifest CSV thủ công cho mọi kiểu Batch job.

### 5.3. Quyền và mã hóa ở bucket đích

Khi thiết lập Inventory, cần cho dịch vụ S3 quyền **ghi đối tượng báo cáo vào bucket đích**, thường qua bucket policy dành cho service principal `s3.amazonaws.com` với giới hạn nguồn phù hợp. Khi dùng mã hóa **SSE-KMS**, cần thêm các quyền/key policy liên quan cho dịch vụ. Hạn chế:

- Chỉ cho phép report từ **source bucket ARN** và **account ID** được chỉ định, tránh lạm dụng service principal.
- Chỉ ghi vào prefix dành riêng cho Inventory.
- Giới hạn quyền **đọc báo cáo** vì inventory có thể lộ tên key, tag/phân loại, lịch sử dữ liệu và trạng thái retention.
- Thiết lập lifecycle/retention phù hợp để chi phí lưu báo cáo không tăng vô hạn.

### 5.4. Ví dụ cấu hình Inventory dưới dạng JSON

Đoạn sau chỉ **minh họa cấu trúc** một inventory configuration, không tự gửi lệnh thay đổi bucket:

~~~json
{
  "Id": "daily-object-lock-audit",
  "IsEnabled": true,
  "IncludedObjectVersions": "All",
  "Schedule": {
    "Frequency": "Daily"
  },
  "OptionalFields": [
    "Size",
    "LastModifiedDate",
    "StorageClass",
    "ObjectLockRetainUntilDate",
    "ObjectLockMode",
    "ObjectLockLegalHoldStatus"
  ],
  "Destination": {
    "S3BucketDestination": {
      "Bucket": "arn:aws:s3:::inventory-audit-destination",
      "Format": "Parquet",
      "Prefix": "reports/object-lock/"
    }
  }
}
~~~

Để áp dụng, còn cần cấu hình quyền ghi trên bucket đích, Region/loại bucket tương thích, chính sách mã hóa, quota và thông tin tài khoản theo yêu cầu môi trường. Hãy kiểm tra với tài liệu/CLI đang dùng trước khi tạo thật.

### 5.5. Kiểm tra cấu hình qua CLI (chỉ đọc)

~~~bash
aws s3api list-bucket-inventory-configurations \
  --bucket audit-ledger-example

aws s3api get-bucket-inventory-configuration \
  --bucket audit-ledger-example \
  --id daily-object-lock-audit
~~~

Nếu cấu hình chưa tồn tại, CLI có thể báo lỗi hoặc trả danh sách rỗng. Việc cấu hình đã tồn tại **không** chứng minh báo cáo mới nhất đã được sinh thành công; cần kiểm tra tệp manifest/data ở destination bucket và theo dõi lịch xuất.

## 6. S3 Storage Lens: nhìn xu hướng ở nhiều bucket

**Amazon S3 Storage Lens** cung cấp góc nhìn tập trung về các chỉ số sử dụng và hoạt động của S3. Thay vì chỉ biết từng file nào có retention, người quản trị muốn biết **bao nhiêu dung lượng đang nằm ở storage class nào, xu hướng tăng trưởng, dữ liệu không được bảo vệ, các multipart upload bỏ dở hoặc khu vực nào làm chi phí tăng**.

### 6.1. Phân biệt metrics và bản ghi object

| Câu hỏi | Storage Lens | Inventory |
| --- | --- | --- |
| Dung lượng lưu trữ của nhóm bucket tăng bao nhiêu theo thời gian? | **Phù hợp** | Có thể tổng hợp sau khi xử lý báo cáo |
| Bucket nào có nhiều version cũ hoặc delete markers? | Có metrics tổng hợp liên quan nếu được hỗ trợ | Có thể liệt kê chi tiết từng version nếu chọn All |
| Object `records/x.json` có retention đến ngày nào? | Không phải công cụ hỏi metadata từng object | **Phù hợp** nếu có cột Object Lock tương ứng |
| Bao nhiêu object/byte theo storage class? | Dashboard/metrics tổng hợp | Có thể nhóm từ báo cáo Inventory |
| API/lưu lượng có dấu hiệu bất thường? | Metrics hoạt động ở cấp độ/tier hỗ trợ | Inventory không phải lịch sử API request |
| Cần chọn 500.000 key để chạy job? | Không phải manifest per-object | **Có thể dùng Inventory làm đầu vào** |

Storage Lens bổ sung **dashboard**, khả năng **lọc theo phạm vi** và **xuất metrics** phục vụ phân tích lâu dài. Nó không tự thay đổi object, không tự bật Object Lock và không thay thế CloudTrail hoặc công cụ theo dõi request theo thời gian thực.

### 6.2. Metrics thường hữu ích

| Nhóm phân tích | Ví dụ chỉ số / câu hỏi |
| --- | --- |
| **Storage** | Tổng byte, tổng object, phân bố storage class |
| **Cost optimization** | Noncurrent-version bytes, delete markers, incomplete multipart uploads và cơ hội lifecycle |
| **Data protection** | Mức áp dụng versioning, replication, encryption hoặc cấu hình bảo vệ theo nhóm metrics hỗ trợ |
| **Activity** | Số request, traffic/hoạt động theo tier được kích hoạt |
| **Performance/Access** | Các góc nhìn nâng cao nếu loại metrics được cấp hỗ trợ |

Các chỉ số chính xác, bộ lọc và độ chi tiết có thể thay đổi theo **free metrics**, **advanced metrics and recommendations** và phạm vi dashboard. Không nên trình bày mọi metrics nâng cao như đã có sẵn miễn phí trong mọi tài khoản; xem danh mục và bảng giá hiện hành.

### 6.3. Cách đọc số liệu có trách nhiệm

Một dashboard hiển thị “noncurrent version bytes tăng mạnh” gợi ý cần điều tra:

1. Những bucket nào tạo ra phần lớn phiên bản cũ?
2. Có công việc ghi đè một key thường xuyên không?
3. Lifecycle hiện tại có xóa noncurrent versions quá sớm hoặc giữ mãi không?
4. Trong số đó có version **đang bị Object Lock** và vì vậy không thể xóa trước hạn không?
5. Tăng chi phí do backup/tuân thủ hợp lệ hay do cấu hình sai?

Storage Lens **không tự kết luận** nên xóa tất cả noncurrent versions. Dữ liệu cần giữ theo quy định có thể tạo chi phí hợp pháp, và Batch Operations không được phép vượt qua Compliance retention.

### 6.4. Độ trễ và phạm vi

Storage Lens tổng hợp dữ liệu theo **chu kỳ**, có thể có độ trễ làm mới trước khi xuất hiện trên dashboard. Không dùng dashboard như công cụ phát hiện thay đổi trong từng giây. Với cảnh báo an ninh gần thời gian thực, phải dùng CloudWatch, CloudTrail/EventBridge hoặc dịch vụ giám sát tương ứng.

Dashboard có thể được cấu hình theo những account/Region/bucket phù hợp và một số cấp chi tiết khác khi tier hỗ trợ. Ở tổ chức nhiều tài khoản AWS Organizations, cần xem IAM, vai trò quản trị được ủy quyền, quyền xem dashboard và chi phí hoạt động nâng cao.

### 6.5. Xem cấu hình Storage Lens bằng CLI

~~~bash
aws s3control list-storage-lens-configurations \
  --account-id 123456789012 \
  --region ap-southeast-1

aws s3control get-storage-lens-configuration \
  --account-id 123456789012 \
  --config-id org-storage-overview \
  --region ap-southeast-1
~~~

Các lệnh dùng **account ID và config ID giả định**; chỉ đọc cấu hình, không trả toàn bộ dữ liệu metrics của dashboard. Nếu chỉ muốn quan sát số liệu, dùng Storage Lens Console hoặc dữ liệu export mà tổ chức đã cấu hình và cấp quyền cho bạn.

## 7. S3 Batch Operations: thực thi trên tập object lớn

**S3 Batch Operations** cho phép tạo một **job** thực hiện thao tác được hỗ trợ trên nhiều object/version. Dịch vụ xử lý tập object từ **manifest** hoặc một số cơ chế tạo manifest được hỗ trợ, quản lý tiến độ và có thể xuất **completion report**.

Ứng dụng phổ biến:

- Gắn hoặc thay object tags cho tập object phù hợp.
- Áp dụng **Object Lock retention** hoặc **Legal Hold** cho nhiều version theo quy tắc hỗ trợ.
- Copy nhiều object sang vị trí khác.
- Khởi tạo restore từ các lớp lưu trữ cần restore.
- Thực hiện replication theo cơ chế Batch Replication.
- Gọi một Lambda function cho mỗi object để xử lý tác vụ tùy chỉnh.

**Không mọi thao tác đều giống nhau**: action nào được Batch Operations hỗ trợ, có hỗ trợ version ID không, cách ghi đè metadata và chi phí ra sao đều phải kiểm tra theo tài liệu từng operation.

### 7.1. Vòng đời job

~~~mermaid
flowchart TD
    S["Xác định yêu cầu và phạm vi key/version"] --> M["Tạo manifest\nInventory / CSV / bộ tạo manifest hỗ trợ"]
    M --> V["Rà soát danh sách\nlọc, sample, chi phí, IAM"]
    V --> J["Create Job\noperation + role + report"]
    J --> C{"Cần xác nhận?"}
    C -->|"Có"| REVIEW["Người có quyền rà soát và xác nhận"]
    C -->|"Không"| Q["Sẵn sàng xử lý"]
    REVIEW --> Q
    Q --> RUN["Batch Operations xử lý từng object/version"]
    RUN --> RESULT["Completion report + job summary"]
    RESULT --> CHECK["Xác minh API / Inventory lần sau\nretry có kiểm soát"]
~~~

**Job không có nghĩa tất cả object thành công.** Một job hoàn thành vẫn cần xem summary, per-object failures, lý do lỗi và tác động thực tế. Một số thao tác có thể được thử lại trong quá trình xử lý; Lambda xử lý object phải thiết kế **idempotent** khi dùng Batch Operations.

### 7.2. Manifest là gì?

Manifest chỉ rõ những object mà job được phép nhắm tới. Có thể dùng:

1. **Báo cáo S3 Inventory** được hỗ trợ, phù hợp khi chọn toàn bộ hoặc tập lớn object theo dữ liệu kiểm kê.
2. **CSV manifest tự chuẩn bị** có các cột bucket, key và **version ID** nếu cần nhắm đúng version.
3. **S3-generated manifest** theo các bộ lọc được dịch vụ hỗ trợ, nếu loại job/tính năng hiện hành đáp ứng.

Ví dụ CSV để minh họa cấu trúc các dòng (không có header):

~~~csv
audit-ledger-example,records/2026/event-0001.json,EXAMPLE_VERSION_01
audit-ledger-example,records/2026/event-0002.json,EXAMPLE_VERSION_02
~~~

Đây là ví dụ dữ liệu, **không phải manifest sẵn sàng chạy**: phải xác minh version ID thật, encoding của key, format theo API và tính tương thích với operation. Nếu một job thay retention của **version lịch sử**, omission của version ID có thể dẫn đến xử lý sai version hoặc không đúng mục tiêu.

Một báo cáo Inventory định kỳ có thể chưa phản ánh object vừa được thêm/xóa. Với thao tác nhạy cảm, cần **snapshot/phê duyệt manifest**, đối chiếu kết quả ngay trước khi chạy và kiểm tra lại sau job.

### 7.3. Execution role và quyền tạo job

Batch Operations thực hiện công việc thông qua **IAM role mà dịch vụ được phép assume**. Trust policy dành cho role được Batch Operations dùng có service principal `batchoperations.s3.amazonaws.com`.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "batchoperations.s3.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy trên **chỉ cho phép dịch vụ assume role**; nó chưa cấp quyền đọc manifest, xử lý object hoặc ghi completion report. Cần thêm permissions policy tương ứng, ví dụ:

| Tác vụ | Quyền cần nghiên cứu |
| --- | --- |
| Đọc manifest | `s3:GetObject` trên manifest object, và quyền KMS nếu mã hóa bằng SSE-KMS |
| Gắn tags | `s3:PutObjectTagging` / `s3:PutObjectVersionTagging` theo operation/version |
| Gắn retention | `s3:PutObjectRetention` trên object version phù hợp |
| Bật/tắt Legal Hold | `s3:PutObjectLegalHold` trên object version |
| Copy object | Quyền đọc nguồn, ghi đích, quyền KMS và metadata/tagging tương ứng |
| Ghi completion report | `s3:PutObject` trên prefix báo cáo, quyền encryption nếu cần |

Người **tạo job** còn phải được phép gọi API job, điển hình `s3:CreateJob` và `iam:PassRole` với role đã phê duyệt. Không cấp `iam:PassRole` trên mọi role, vì người tạo job có thể khiến dịch vụ hành động với phạm vi quyền ngoài ý muốn.

### 7.4. Completion report và điều tra lỗi

Một completion report có thể chứa trạng thái cho từng object cùng error code/message; tùy cấu hình, report ghi **tất cả tác vụ** hoặc **chỉ các tác vụ lỗi**. Bên cạnh job status, cần kiểm tra:

- Số object **được đưa vào manifest**, số được xử lý, số thất bại.
- Danh sách version không tồn tại hoặc đã thay trạng thái sau khi snapshot.
- Những object bị **Object Lock Compliance/Governance**, Legal Hold, bucket policy hoặc KMS chặn.
- Những task lỗi tạm thời cần retry, và object đã thành công không cần làm lại.
- Hệ quả nghiệp vụ khi một phần job thành công còn phần khác thất bại.

CloudTrail giúp kiểm toán **API quản lý job**; muốn theo dõi thao tác dữ liệu ở cấp object còn cần xem cấu hình **CloudTrail data events** hoặc nguồn nhật ký phù hợp. Completion report giúp phân tích kết quả, nhưng không thay thế lưu giữ bằng chứng/đăng ký thay đổi của tổ chức.

### 7.5. Kiểm tra jobs qua CLI (chỉ đọc)

~~~bash
aws s3control list-jobs \
  --account-id 123456789012 \
  --region ap-southeast-1

aws s3control describe-job \
  --account-id 123456789012 \
  --job-id EXAMPLE_JOB_ID \
  --region ap-southeast-1
~~~

Không chạy `create-job`, `update-job-status` hay `put-object-retention` trên dữ liệu production chỉ để thử khả năng truy cập. Với job cần thay retention/hold, chuẩn bị manifest và kết quả dự kiến ở môi trường thử trước khi thực hiện ở phạm vi thật.

## 8. Kết hợp bốn tính năng: kiểm toán hồ sơ phải giữ 7 năm

### 8.1. Bối cảnh

Một doanh nghiệp lưu chứng từ điện tử trên S3:

~~~text
Bucket: audit-ledger-example
Prefix: documents/year=2026/
Yêu cầu: lưu từng chứng từ 7 năm, có thể giữ lâu hơn khi có tranh chấp
Quy mô: hàng triệu phiên bản, phát sinh dữ liệu mới hằng ngày
~~~

Mục tiêu là bảo vệ version mới, tìm version cũ chưa có retention, xem dung lượng/lịch sử tăng trưởng và áp dụng sửa chữa **đúng phiên bản cần thiết**.

### 8.2. Quy trình đề xuất

**Bước 1 — Bảo vệ dữ liệu mới với Object Lock.** Chọn bucket hỗ trợ Object Lock và bật versioning. Phê duyệt mode và thời hạn retention với bộ phận phụ trách dữ liệu; cân nhắc Governance trong giai đoạn thử có quy trình ngoại lệ, Compliance khi yêu cầu buộc không được rút ngắn retention. Cấu hình default retention cho object version mới; người vận hành thông thường không được bypass.

**Bước 2 — Xuất Inventory đầy đủ version.** Cấu hình Daily Inventory (hoặc Weekly khi nghiệp vụ cho phép) với `IncludedObjectVersions=All` và các thuộc tính Object Lock liên quan. Ghi báo cáo vào bucket riêng được kiểm soát, mã hóa, có chính sách giữ báo cáo.

**Bước 3 — Phân tích bằng Athena hoặc công cụ dữ liệu phù hợp.** Lọc các version thuộc prefix `documents/year=2026/` mà trạng thái retention thiếu hoặc không đáp ứng chính sách. Phân biệt delete marker, version hiện hành và noncurrent versions. Truy vấn Inventory cần dựa vào schema thật của báo cáo và hiểu rằng đây là snapshot định kỳ.

**Bước 4 — Quan sát bối cảnh với Storage Lens.** Xem xu hướng total bytes, noncurrent versions, số object, storage class và data protection metrics theo phạm vi hỗ trợ. Kết hợp chi phí lưu trữ với thời hạn tuân thủ; không tự xem các version cũ là “rác” để xóa.

**Bước 5 — Chuẩn bị Batch Operations job.** Tạo manifest **chỉ chứa object versions cần sửa**, kèm version ID khi cần. Rà soát sample, hạn chế IAM role vào thao tác `PutObjectRetention`/`PutObjectLegalHold` được phê duyệt; tạo completion report đầy đủ và yêu cầu xác nhận.

**Bước 6 — Kiểm chứng sau job.** Xem số lỗi, các version bị chặn và kết quả retention thực tế. Tập đối chiếu cuối phải dùng API Object Lock trực tiếp trên mẫu hoặc toàn bộ tập cần xác minh theo khả năng, rồi so với Inventory được cập nhật kỳ tiếp theo.

### 8.3. Tại sao không chạy job “giữ 7 năm” trực tiếp trên mọi object?

Vì retention cần **tính đúng theo từng bản ghi**: object cũ có thể phải giữ tới ngày khác, một số version đang ở Compliance mode không được rút ngắn, một số object thuộc ngoại lệ pháp lý đang bật Legal Hold. Manifest không được xem qua có thể vô tình áp chính sách sai và khiến dữ liệu không thể xóa trong nhiều năm.

Ngoài ra, vì job chạy bất đồng bộ, trạng thái bucket có thể thay đổi sau khi tạo Inventory. Cần phê duyệt **danh sách version cụ thể** và xác minh trước/sau.

## 9. Bảo mật và rủi ro theo từng lớp

| Rủi ro | Biện pháp |
| --- | --- |
| Người vận hành có quyền bypass Governance quá rộng | Tách role ngoại lệ; giới hạn `s3:BypassGovernanceRetention` và ghi sự kiện thay đổi quyền |
| Bật Compliance retention quá dài | Thử trong bucket lab, đánh giá quy định, phê duyệt chính sách trước khi ghi |
| Tin rằng Object Lock chặn mọi PUT cùng key | Dùng version ID, quy trình catalog và kiểm soát ghi; hiểu current version có thể thay đổi |
| Inventory bị lộ tên tài liệu/đường dẫn | Bucket báo cáo private, IAM chặt, mã hóa và retention của báo cáo |
| Inventory bị xem như dữ liệu tức thời | Đối chiếu API trên object hiện tại hoặc kỳ report sau cho sự kiện mới |
| Storage Lens bị coi là công cụ audit từng request | Dùng CloudTrail data events/CloudWatch/logging theo yêu cầu |
| Batch job chạy nhầm toàn bucket | Manifest có version ID, sample và dry-run ở môi trường test; xác nhận trước job |
| Batch role được quyền xóa/ghi mọi object | IAM theo ARN/prefix, operation-specific action và `iam:PassRole` hẹp |
| Job thành công một phần | Completion report, retry idempotent và đối chiếu hậu kiểm |
| Chi phí tăng do giữ noncurrent versions | Lifecycle theo quy định, Storage Lens/Inventory phân tích, không xóa trước hạn |

### 9.1. Dữ liệu và khóa mã hóa

Version còn được Object Lock bảo vệ nhưng **khóa KMS không dùng được** vẫn có thể khiến dữ liệu không đọc được. Với SSE-KMS, phải quản lý IAM/KMS key policy, rotation và khả năng phục hồi khóa theo yêu cầu thực tế. Object Lock không tự sao lưu khóa KMS hoặc xử lý quyền đọc object.

Nếu dùng **cross-Region replication** cho bucket có Object Lock, cần kiểm tra điều kiện hỗ trợ Object Lock ở bucket đích, khả năng sao chép retention/legal hold và IAM permissions cho replication role. Replication thường có độ trễ bất đồng bộ; không giả định bản sao đã sẵn sàng ngay khi PUT nguồn thành công.

### 9.2. Chi phí và kiểm soát ngân sách

| Thành phần | Nguồn chi phí cần xem |
| --- | --- |
| **Object Lock** | Dữ liệu không thể xóa trước hạn → giữ object versions lâu hơn, phát sinh lưu trữ |
| **Inventory** | Phí tạo danh sách theo quy mô/tần suất, lưu output và truy vấn báo cáo |
| **Storage Lens** | Metrics/tính năng nâng cao có thể tính phí; dữ liệu export và nơi lưu trữ |
| **Batch Operations** | Phí mỗi job, mỗi object được xử lý và chi phí API/operation liên quan |
| **S3 Versioning** | Noncurrent versions, delete markers và các lớp lưu trữ áp dụng |
| **KMS / log / replication** | KMS API, nhật ký, data transfer, sao chép và lưu bucket đích |

Không có mức giá cố định dùng được cho mọi Region/tài khoản. Lập dự toán theo lượng object/version, kỳ Inventory, số Batch job, bytes, API, retention thực tế và bảng giá AWS ở thời điểm triển khai. Kết hợp **AWS Budgets** và báo cáo Cost Explorer để theo dõi bất thường.

## 10. Phân biệt “báo cáo”, “chỉ số” và “thay đổi dữ liệu”

Một cách chọn công cụ theo câu hỏi:

~~~text
Cần ngăn xóa/ghi đè một version đến ngày xác định?
    -> S3 Object Lock

Cần xuất danh sách version + metadata tại thời điểm kiểm kê?
    -> S3 Inventory

Cần so sánh xu hướng dung lượng/hoạt động giữa bucket/tài khoản?
    -> S3 Storage Lens

Cần gắn tag/retention, copy hoặc xử lý hàng triệu object?
    -> S3 Batch Operations + manifest + execution role + completion report
~~~

Trong hệ thống lớn, chúng phối hợp với nhau: **Inventory tìm ứng viên**, **Storage Lens đặt mục tiêu và theo dõi xu hướng**, **Batch Operations áp dụng biện pháp**, còn **Object Lock bảo đảm rào chắn lưu giữ**. Dữ liệu điều tra vẫn cần CloudTrail và các công cụ monitoring khác.

## 11. Thực hành an toàn: chỉ đọc và lập kế hoạch

Phần thực hành này **không tạo, sửa hoặc xóa object**, nên phù hợp để người học hiểu dữ liệu trước khi đề xuất Batch job. Thay các placeholder bằng bucket/account/config/job có thật mà bạn được phép xem.

### 11.1. Quan sát Object Lock và các version

~~~bash
aws sts get-caller-identity

aws s3api get-object-lock-configuration \
  --bucket audit-ledger-example

aws s3api list-object-versions \
  --bucket audit-ledger-example \
  --prefix records/2026/ \
  --max-items 20
~~~

Khi dùng `--max-items` của AWS CLI, xem pagination token để biết còn kết quả. Không kết luận bucket chỉ có 20 versions. Với một key cụ thể, có thể gọi `get-object-retention` và `get-object-legal-hold` với version ID đúng như mục 4.

### 11.2. Quan sát Inventory và Storage Lens

~~~bash
aws s3api list-bucket-inventory-configurations \
  --bucket audit-ledger-example

aws s3control list-storage-lens-configurations \
  --account-id 123456789012 \
  --region ap-southeast-1
~~~

Nếu đã có báo cáo Inventory, xem manifest ở bucket đích qua Console hoặc công cụ phân tích được cấp quyền. Quan sát ít nhất các cột: key, version ID, isLatest, size, storage class, retention mode/date và legal hold (nếu được cấu hình trong report).

### 11.3. Lập kế hoạch job nhưng chưa thực hiện

Tạo **bản thiết kế** gồm:

| Mục kiểm tra | Giá trị phải điền trước khi xin phê duyệt |
| --- | --- |
| Bucket nguồn và prefix | Tên thật, account, Region và phân loại dữ liệu |
| Danh sách version | Inventory manifest + ngày giờ báo cáo + xác minh mẫu |
| Operation | Ví dụ `PutObjectRetention`, mode, retain-until và trường hợp đặc biệt |
| Execution role | ARN, trust policy, quyền object, manifest, report và KMS |
| Dự kiến quy mô | Số version, phí job/operation và ảnh hưởng tới chi phí lưu giữ |
| Completion report | Bucket/prefix đích, toàn bộ task hoặc chỉ lỗi, retention report |
| Kế hoạch hậu kiểm | API kiểm tra, mẫu xác minh, xử lý lỗi và điều kiện hoàn thành |

Với thao tác Compliance retention, **không** thử tạo job trên dữ liệu giả định production nếu chưa phê duyệt ngày hết hạn và phạm vi. Có thể kiểm tra phương thức vận hành trước bằng job vô hại trên bucket lab riêng.

## 12. Bài tập củng cố

### Bài tập 1 — Governance hay Compliance?

Một nhóm lưu hồ sơ nội bộ 180 ngày và cần có đường xử lý sai sót dưới quy trình phê duyệt nghiêm ngặt. Một nhóm khác lưu chứng từ bắt buộc không ai được rút ngắn thời hạn 7 năm.

**Gợi ý:** nhóm thứ nhất có thể đánh giá **Governance mode** với quyền bypass rất hạn chế; nhóm thứ hai cân nhắc **Compliance mode** sau khi xác nhận yêu cầu pháp lý. Cả hai phải lập kế hoạch khi retention hết hạn, mã hóa, versioning và backup.

### Bài tập 2 — DELETE thành công nhưng vẫn có version được giữ?

Một key có version v1 bị giữ tới năm sau. Người quản trị gọi DELETE key **không nêu version ID** và nhận thành công. Hãy giải thích vì sao `GET` key hiện hành có thể không trả dữ liệu, nhưng `GET` theo version ID v1 vẫn có thể đọc được.

**Gợi ý:** thao tác DELETE có thể tạo **delete marker**; nó không xóa vĩnh viễn version v1 đang được Object Lock bảo vệ.

### Bài tập 3 — Inventory và nhất quán dữ liệu

Bạn tạo một object mới lúc 10:00, gọi `GET` trực tiếp S3 lúc 10:01 thấy object, nhưng Inventory báo cáo lúc sáng vẫn không có key.

**Gợi ý:** Inventory là **báo cáo theo lịch**, không phải LIST trực tiếp realtime. Sự khác biệt không chứng minh S3 mất strong read-after-write consistency.

### Bài tập 4 — Storage Lens hay Inventory?

Hãy chọn công cụ phù hợp:

1. Cần thống kê xu hướng noncurrent version bytes theo tháng.
2. Cần liệt kê version ID và retain-until date của 20.000 file.
3. Cần chạy operation gắn Legal Hold cho 20.000 version đã chọn.
4. Cần chặn xóa vĩnh viễn file đang có tranh chấp.

**Đáp án:** (1) Storage Lens; (2) Inventory với trường Object Lock phù hợp; (3) Batch Operations + manifest có version ID; (4) Object Lock Legal Hold. Ở trường hợp (3), kết quả cuối cần API hậu kiểm.

### Bài tập 5 — job thất bại 1,5%

Batch Operations job đã xử lý 100.000 object; completion report cho biết 1.500 task thất bại. Đội vận hành đề xuất chạy lại job toàn bộ manifest.

**Gợi ý:** trước hết phân tích lỗi: phiên bản không còn tồn tại, thiếu IAM/KMS, retention ngăn thao tác, lỗi tạm thời hay key đã được cập nhật. Nên tạo manifest retry cho **tập thất bại** hoặc dùng chiến lược idempotent khi operation cho phép; không mặc định chạy lại mọi object sẽ an toàn.

### Bài tập 6 — thiết kế quyền

Một IAM role có `s3:BypassGovernanceRetention` trên toàn bộ bucket và `s3:DeleteObjectVersion`. Role này được gắn cho pipeline ETL hàng ngày vốn chỉ cần ghi file mới. Rủi ro là gì?

**Gợi ý:** pipeline đã có khả năng vượt qua lớp Governance retention và xóa version đang cần bảo vệ nếu request sử dụng cơ chế bypass; tách các quyền này sang role ngoại lệ có kiểm soát và cấp cho ETL chỉ quyền thao tác key cần dùng.

## 13. Những nhầm lẫn thường gặp

| Nhận định | Điều cần hiểu đúng |
| --- | --- |
| “Object Lock khóa cả key, không ai tạo version mới được.” | Object Lock bảo vệ **version cụ thể**; key có thể nhận version mới theo quyền. |
| “Governance mode không ai có thể xóa.” | Người có quyền bypass phù hợp và request đúng có thể vượt Governance. |
| “Compliance mode có thể tắt bằng AdministratorAccess.” | Retention Compliance chưa hết hạn không bị bỏ qua bằng quyền IAM thông thường. |
| “Legal Hold tự hết hạn theo RetainUntilDate.” | Legal Hold độc lập và **không có ngày tự hết hạn**. |
| “Bật default retention sẽ khóa toàn bộ object cũ.” | Default retention chủ yếu áp dụng cho **version mới**; phải rà soát/migrate dữ liệu cũ. |
| “DELETE key thành công nghĩa là version được khóa đã bị xóa.” | DELETE không version ID có thể chỉ tạo delete marker. |
| “Inventory giống LIST realtime.” | Inventory cập nhật **định kỳ**, không dùng làm bản sao trạng thái tức thời. |
| “Storage Lens cho biết retain-until của từng object ngay trên dashboard.” | Storage Lens chủ yếu tổng hợp metrics; cần Inventory/API cho dữ liệu per-object. |
| “Batch Operations bỏ qua IAM, KMS và Object Lock.” | Job vẫn chịu các kiểm soát đó; phải có execution role đúng quyền. |
| “Job Complete nghĩa là 100% object thành công.” | Phải kiểm tra **per-object completion report** và trạng thái thật sau thao tác. |
| “Object Lock thay thế backup.” | Vẫn cần khôi phục, quản trị khóa KMS, lỗi Region và chiến lược DR phù hợp. |
| “S3 Versioning không tốn thêm chỗ.” | Noncurrent versions và báo cáo/replication có thể tạo thêm chi phí. |

## 14. Ghi nhớ

Đối với quản trị S3 ở quy mô doanh nghiệp:

1. **Object Lock** bảo vệ sự bất biến của **object version** bằng retention và Legal Hold; thiết kế đúng mode và quyền bypass là yêu cầu trọng tâm.
2. **S3 Inventory** cho phép kiểm kê **object/version và metadata theo lịch**, rất hữu ích để tìm phạm vi xử lý; báo cáo không phản ánh mọi thay đổi ngay lập tức.
3. **S3 Storage Lens** cung cấp **metrics tổng hợp và xu hướng sử dụng**, giúp phát hiện chi phí và thiếu sót bảo vệ ở cấp bucket/tài khoản/tổ chức.
4. **S3 Batch Operations** xử lý **nhiều object/version theo manifest**, cần role phù hợp, xác nhận phạm vi, completion report và hậu kiểm.

Giải pháp production tốt kết hợp cả bốn với **IAM, mã hóa, logging, replication/backup, lifecycle và quy trình phê duyệt**. Đặc biệt, một job có thể tác động rất nhiều version trong thời gian ngắn: **bảo vệ phạm vi và review manifest** phải là bước bắt buộc trong thiết kế vận hành.

### Tài liệu AWS chính thức để đọc thêm

- [Using S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — khái niệm, versioning và WORM.
- [Object Lock retention modes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html#object-lock-retention-modes) — Governance, Compliance và cơ chế bypass.
- [Legal holds in S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html#object-lock-legal-holds) — Legal Hold độc lập với retention.
- [Amazon S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html) — lịch xuất, định dạng, trường dữ liệu và độ trễ.
- [Setting up S3 Inventory](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configure-inventory.html) — cấu hình và quyền bucket đích.
- [Amazon S3 Storage Lens](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html) — dashboard, metrics và phạm vi.
- [S3 Storage Lens metrics glossary](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_metrics_glossary.html) — giải thích metrics theo loại/tier.
- [S3 Batch Operations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops.html) — jobs, manifest, execution roles, reports.
- [S3 Batch Operations job manifests](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-basics.html) — cách lựa chọn object và workflow job.
- [Tracking S3 Batch Operations job status](https://docs.aws.amazon.com/AmazonS3/latest/userguide/batch-ops-job-status.html) — theo dõi kết quả và trạng thái job.
- [Security best practices for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — phân quyền, mã hóa, truy cập công khai và audit.
