# Mã hóa đối tượng và lựa chọn khóa cho bucket trong Cloud Storage

> **Chương:** Cloud Storage  
> **Bài học:** Mã hóa đối tượng và lựa chọn khóa cho bucket  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu cách tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Khi triển khai hệ thống Java, người vận hành cần biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Một câu hỏi thường gặp khi lưu hóa đơn, ảnh, bản sao dữ liệu hoặc artifact ứng dụng vào **Cloud Storage** là: **Dữ liệu được mã hóa bằng khóa nào, ai có quyền sử dụng khóa và chuyện gì xảy ra nếu khóa không còn khả dụng?**

Cloud Storage **tự mã hóa nội dung khách hàng khi lưu trữ (encryption at rest)**. Tổ chức có thể giữ phương án **Google default encryption**, chủ động quản lý **customer-managed encryption keys (CMEK)** qua Cloud Key Management Service (Cloud KMS), hoặc cung cấp **customer-supplied encryption keys (CSEK)** theo từng yêu cầu. Một số bài toán có thể mã hóa ở phía ứng dụng **trước khi upload**. Những phương án này có ranh giới trách nhiệm, chi phí và hậu quả vận hành rất khác nhau.

**Tư tưởng chủ đạo:** chọn khóa mã hóa phải dựa trên **yêu cầu kiểm soát khóa, compliance, khả năng khôi phục, địa điểm dữ liệu, tích hợp workload và mức rủi ro tổ chức chịu được**. CMEK không tự làm bucket trở thành private; IAM, public access prevention, Uniform bucket-level access, lifecycle, retention và việc bảo vệ khóa vẫn là các lớp cần thiết.

Các tên project, bucket, key ring và CryptoKey trong bài chỉ là ví dụ. Mọi lệnh thay đổi tài nguyên đều phải thực thi ở **sandbox được cấp quyền**, có dự toán và phương án rollback.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **encryption in transit**, **at rest** và **client-side encryption** trong một ứng dụng tải object.
2. So sánh **Google default encryption**, **CMEK**, **CSEK** và mã hóa phía client theo ai quản lý khóa, tính tương thích và rủi ro mất dữ liệu.
3. Phân biệt **default KMS key của bucket** với **khóa thực tế trên một object**; hiểu thứ tự ưu tiên khi upload có chỉ định khóa riêng.
4. Chọn đúng **Cloud KMS key ring location**, key type, protection level và mô hình project lưu trữ khóa.
5. Xác định **Cloud Storage service agent** và cấp đúng role `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên khóa.
6. Cấu hình, kiểm tra hoặc gỡ **default CMEK** trên bucket qua Console và `gcloud storage`.
7. Giải thích **key rotation**, **key replacement**, **object rewrite**, versioning, retention và hậu quả khi khóa bị disable/destroy.
8. Dùng **encryption enforcement rules** để yêu cầu/giới hạn loại mã hóa cho object mới thay vì chỉ dựa vào cấu hình mặc định.
9. Thiết kế quy trình giám sát, gỡ lỗi `403`/key unavailable và đánh giá chi phí, backup, DR cho dữ liệu quan trọng.

## 2. Phân biệt dữ liệu, khóa và quyền truy cập

### 2.1. Ba lớp bảo vệ khác nhau

~~~mermaid
flowchart LR
    U["Ứng dụng Java<br/>Cloud Run / GKE / VM"] --> T["TLS/HTTPS<br/>Mã hóa đường truyền"]
    T --> S["Cloud Storage API<br/>IAM + bucket policy"]
    S --> E["Encryption at rest<br/>Google-managed / CMEK / CSEK"]
    E --> O["Object payload<br/>đã mã hóa khi lưu"]
    K["Cloud KMS key + IAM service agent"] -. "CMEK theo lựa chọn" .-> E
~~~

- **TLS/HTTPS:** bảo vệ dữ liệu khi truyền qua mạng; không phải lựa chọn khóa at rest cho object.
- **IAM/bucket authorization:** quyết định principal có được `storage.objects.get`, `storage.objects.create` hoặc thao tác khác hay không.
- **Encryption at rest:** bảo vệ dữ liệu lưu trên hạ tầng; Cloud Storage thực hiện mã hóa cho object.
- **Client-side encryption:** ứng dụng mã hóa dữ liệu **trước khi gửi** lên Cloud Storage, sau đó Cloud Storage vẫn áp mã hóa ở phía server.

Một người không có IAM permission phù hợp **không được đọc object** chỉ vì Cloud Storage có sẵn Google-managed key. Ngược lại, người có IAM đọc object dùng CMEK cũng cần Cloud Storage **có thể giải mã** qua quyền của service agent và tình trạng CryptoKey.

### 2.2. Mã hóa đối tượng không giống khóa tài khoản

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| **Google identity / service account** | Danh tính của người hoặc workload | `orders-api@project.iam.gserviceaccount.com` |
| **IAM role trên bucket** | Cho phép đọc/ghi object | `roles/storage.objectViewer` |
| **Cloud Storage service agent** | Danh tính dịch vụ thay mặt Cloud Storage dùng CMEK | Service agent của project sở hữu bucket |
| **Cloud KMS CryptoKey** | Khóa quản lý để bảo vệ dữ liệu lưu trữ | `projects/key-project/locations/asia-southeast1/keyRings/app/cryptoKeys/invoices` |
| **CryptoKeyVersion** | Phiên bản vật liệu khóa, phục vụ mã hóa/giải mã | Version primary và các version cũ |
| **Bucket default KMS key** | Khóa mặc định cho **object được ghi mới** | Một thuộc tính cấu hình bucket |
| **Object encryption metadata** | Thông tin phương thức/khóa dùng khi object được ghi | `kmsKeyName` với object CMEK |

**Không nhầm Google Cloud service account chạy API Java với Cloud Storage service agent.** Khi dùng CMEK, Cloud Storage gọi Cloud KMS qua **service agent của chính project chứa bucket**, không phải bằng email người dùng vừa upload object.

## 3. Bốn phương án mã hóa dữ liệu

### 3.1. Bảng so sánh

| Phương án | Ai quản lý khóa phía server? | Cách áp dụng | Lợi ích | Đánh đổi chính |
|---|---|---|---|---|
| **Google default encryption** | Google quản lý khóa mặc định | Tự động cho dữ liệu Cloud Storage | Đơn giản, ít phụ thuộc vận hành khóa | Ít quyền kiểm soát vòng đời/usage của khóa |
| **CMEK** | Khách hàng quản lý Cloud KMS CryptoKey; Cloud Storage mã hóa dữ liệu | Default của bucket hoặc cho từng object | Kiểm soát IAM khóa, rotation, audit, lifecycle | Phụ thuộc KMS/service agent; phí, quota, rủi ro mất quyền giải mã |
| **CSEK** | Khách hàng tự tạo và giữ **AES-256 key raw**, gửi kèm từng yêu cầu phù hợp | **Từng object**, không đặt làm default bucket | Tương thích tổ chức đã có hệ thống khóa ngoài Cloud KMS | Phải tự giữ/đưa khóa đúng mỗi lần; mất khóa có thể mất dữ liệu |
| **Client-side encryption** | Ứng dụng/khách hàng mã hóa trước upload | Mã hóa payload trước khi tới Cloud Storage | Kiểm soát plaintext ngay từ phía ứng dụng | Tự thiết kế quản trị khóa, format, rotation, index/search và recovery |

Cloud Storage vẫn mã hóa dữ liệu **ở phía server** nếu ứng dụng đã mã hóa client-side. Vì vậy client-side là lớp **bổ sung**, không phải cách “tắt” at-rest encryption của Cloud Storage.

### 3.2. Google default encryption: lựa chọn cơ sở

Với bucket mới nếu chưa chỉ định CMEK/CSEK, Cloud Storage sử dụng **Google default encryption** cho dữ liệu lưu trữ. Đây là lựa chọn phù hợp khi không có yêu cầu khách hàng trực tiếp sở hữu vòng đời khóa.

Không cần tạo Cloud KMS CryptoKey, gán role cho service agent hoặc viết code đưa khóa vào request. Tuy nhiên vẫn cần:

- Giới hạn quyền đọc/ghi qua IAM và Uniform bucket-level access.
- Ngăn public object ngoài ý muốn bằng policy phù hợp.
- Bảo vệ object bằng soft delete, retention, Object Versioning hoặc backup nếu yêu cầu.
- Thiết lập logging, data access audit theo chính sách, lifecycle và cảnh báo chi phí.

**Google default encryption không có nghĩa là object public**, và không có nghĩa dữ liệu sẽ tự phục hồi sau khi bị xóa nhầm.

### 3.3. CMEK: chủ động quản trị khóa bằng Cloud KMS

Với **customer-managed encryption key**, Cloud Storage gọi Cloud KMS để sử dụng một khóa **symmetric encryption** do tổ chức quản lý. Tổ chức có thể cấu hình:

- **Key ring**, **CryptoKey**, version và key rotation.
- Phạm vi vị trí khóa phù hợp với vị trí bucket.
- Quyền của các service agents sử dụng khóa.
- Protection level như **software**, **Cloud HSM** hoặc **Cloud EKM** khi được hỗ trợ.
- Audit logs, chính sách tách nhiệm vụ và quy trình disable/destroy có kiểm soát.

CMEK là **server-side encryption**: khi principal có quyền đọc object, Cloud Storage **giải mã tự động** nếu service agent còn quyền và khóa còn khả dụng. Client **không cần gọi trực tiếp Cloud KMS** chỉ để tải object theo luồng thông thường.

### 3.4. CSEK: tự giữ key raw

Với **customer-supplied encryption key**, client gửi khóa AES-256 trong header/API/CLI phù hợp **khi ghi hoặc đọc object**. Cloud Storage không lưu khóa thô này để trả lại; khách hàng phải giữ khả năng cung cấp lại key khi cần.

Các giới hạn cần ghi nhớ:

- **Không thể đặt CSEK làm default encryption key của cả bucket.**
- Không dùng Console để upload object với CSEK hoặc download object được bảo vệ bằng CSEK.
- Một số sản phẩm tích hợp không hỗ trợ object mã hóa CSEK (ví dụ một số luồng Dataflow/Storage Transfer Service).
- Nếu mất CSEK, không thể đọc dữ liệu bằng cách yêu cầu Google “khôi phục khóa”.
- Không viết CSEK vào mã nguồn, command history, log, ticket hoặc biến môi trường dễ lộ.
- Có thể **rewrite** object để đổi CSEK hoặc chuyển sang CMEK với key cũ vẫn còn được cung cấp.

**Chú ý:** CSEK của **Cloud Storage** vẫn là một lựa chọn được tài liệu hỗ trợ; đừng nhầm với thông báo deprecation của **Compute Engine CSEK**, vì đây là hai tích hợp khác nhau.

### 3.5. Khi nào cần client-side encryption?

Mô hình này phù hợp nếu yêu cầu **không để phía cung cấp dịch vụ thấy plaintext trong quá trình xử lý server-side** hoặc ứng dụng kiểm soát mật mã theo chính sách riêng. Nhưng điều này có thể làm giảm khả năng xử lý trực tiếp dữ liệu, preview, indexing, transform và khôi phục. Hệ thống phải tự quản lý:

- Sinh/rotate/backup key, key escrow hoặc HSM.
- Cấu trúc ciphertext, authentication tag, nonce/IV và metadata.
- Phân quyền giải mã cho ứng dụng hợp lệ.
- Quy trình khôi phục khi key version cũ không còn.
- Khả năng sao lưu và thử restore.

**Không tự thiết kế thuật toán mã hóa.** Dùng thư viện chuẩn và kế hoạch quản trị khóa được chuyên gia bảo mật phê duyệt.

## 4. Default KMS key của bucket và khóa từng object

Một bucket không “bị mã hóa lại toàn bộ” chỉ vì người quản trị đổi default encryption key. Cơ chế quan trọng nằm ở **thời điểm ghi object**.

~~~mermaid
flowchart TD
    W["Yêu cầu upload / copy / rewrite object"] --> X{"Yêu cầu có chỉ định<br/>một encryption key riêng?"}
    X -->|Có| O["Dùng key đã chỉ định<br/>nếu loại mã hóa được phép"]
    X -->|Không| B{"Bucket có default CMEK?"}
    B -->|Có| K["Cloud Storage dùng default CMEK"]
    B -->|Không| G["Google default encryption"]
    O --> E["Kiểm tra IAM / key availability<br/>và encryption enforcement"]
    K --> E
    G --> E
    E --> R["Object được lưu theo phương thức hợp lệ"]
~~~

### 4.1. Quy tắc áp dụng

| Trường hợp | Phương thức mã hóa object mới |
|---|---|
| Bucket không có default CMEK, request không chỉ định khóa | Google default encryption |
| Bucket có default CMEK, request không chỉ định khóa | CMEK của bucket |
| Bucket có default CMEK, request chỉ định **CMEK khác** | CMEK **của request**, nếu hợp lệ |
| Bucket có default CMEK, request có **CSEK** | CSEK **của request**, nếu hợp lệ |
| Bucket áp encryption enforcement chỉ cho phép CMEK | Object mới phải đáp ứng CMEK; các phương thức khác bị từ chối |
| Người quản trị đổi default CMEK từ A sang B | Object **mới** dùng B; object **đã có** vẫn dùng khóa cũ cho đến khi rewrite |

Một object chỉ có **một cơ chế mã hóa server-side tại một thời điểm**. Bên trong Cloud Storage có các bước mã hóa nhiều lớp, nhưng không được hiểu rằng một object lưu đồng thời “CMEK + CSEK” dưới hai khóa khách hàng.

### 4.2. Đổi default CMEK không tác động object cũ

Ví dụ:

~~~text
Ngày 01:
  Bucket invoices có default CMEK key-A
  → upload invoices/001.pdf → key-A

Ngày 10:
  Đổi bucket default sang key-B
  → upload invoices/002.pdf → key-B

Sau ngày 10:
  invoices/001.pdf vẫn được bảo vệ bởi key-A
  invoices/002.pdf được bảo vệ bởi key-B
~~~

Nếu cần chuyển `invoices/001.pdf` từ A sang B, phải **rewrite object** theo cơ chế được hỗ trợ. Xóa key-A ngay khi đổi default bucket có thể khiến object cũ **không đọc được**. Với Object Versioning hoặc soft delete, còn có thể có **generation cũ** vẫn tham chiếu key-A.

### 4.3. CMEK không mã hóa toàn bộ metadata bằng chính CMEK

Cloud Storage dùng CMEK để bảo vệ **nội dung object** và một số thông tin toàn vẹn như CRC32C/MD5 theo mô hình sản phẩm; **tên object và phần lớn metadata** vẫn được mã hóa bằng cơ chế server-side do Google quản lý.

Điều này có nghĩa:

- Việc disable/destroy key không phải “xóa sạch danh sách tên object”.
- Principal có quyền phù hợp vẫn có thể xem một số metadata hoặc xóa object theo chính sách.
- Tránh đặt thông tin nhạy cảm vào **bucket name, object name, metadata, labels** chỉ vì object payload đang dùng CMEK.
- Nếu muốn che giấu cả tên và metadata ở mức ứng dụng, cần thiết kế đặt tên/mã hóa phía client phù hợp.

## 5. Chọn Cloud KMS key cho bucket

### 5.1. Ba thành phần của Cloud KMS resource name

~~~text
projects/KEY_PROJECT_ID
  /locations/asia-southeast1
  /keyRings/storage-data
  /cryptoKeys/invoices
~~~

- **Project chứa khóa** có thể **khác** project chứa bucket để tách nhiệm vụ quản trị.
- **Location** của key ring phải **khớp với location của bucket** theo quy tắc Cloud Storage.
- **Key ring** nhóm các CryptoKey tại location đó.
- **CryptoKey** là khóa logic; Cloud KMS có các version và primary version riêng.

Không dùng khóa **asymmetric signing**, HMAC hay khóa công khai cho CMEK Cloud Storage; tích hợp này sử dụng **symmetric encryption key** phù hợp.

### 5.2. Yêu cầu cùng vị trí lưu trữ

| Vị trí Cloud Storage bucket | Cloud KMS key ring location |
|---|---|
| Single region `asia-southeast1` | `asia-southeast1` |
| Single region `us-east1` | `us-east1` |
| Multi-region `US` | `us` (đúng mã location tương ứng) |
| Configurable dual-region gồm hai vùng hợp lệ có location code `ASIA` | `asia` |
| Predefined dual-region `NAM4` | `nam4` |

**Không suy** hai region thành viên của dual-region đều dùng được làm nơi đặt khóa: với dual-region, KMS location phải **trùng location code của bucket**, không phải tự chọn một region con. Nếu region/location không khớp, yêu cầu cấu hình hoặc ghi object có thể bị từ chối.

Một key ring có location khác không thể chỉ “đổi region” để sửa; cần tạo key ring/khóa mới ở location phù hợp và lập kế hoạch đổi default/rewrite theo tài liệu.

### 5.3. Software, HSM và external key management

| Bảo vệ khóa | Lợi thế | Đánh đổi |
|---|---|---|
| **Cloud KMS software key** | Dễ dùng, vận hành đơn giản, API/rotation/audit | Chính sách và quản trị khóa nằm trong Google Cloud |
| **Cloud HSM key** | Key material được bảo vệ bằng HSM theo service assurance | Giá/quota/khả năng triển khai khác; cần dự toán |
| **Cloud EKM key** | Vật liệu khóa và một số quyết định bảo mật được giữ tại trình quản lý khóa ngoài Google Cloud | Phụ thuộc availability, connectivity, latency, policy của external key manager |
| **Autokey CMEK** | Tự tạo và liên kết key/role phục vụ resource theo tích hợp | Cần cấu hình tổ chức/project phù hợp; không giải quyết mọi thao tác object-level |

CMEK với Cloud KMS **Autokey** có thể hỗ trợ quản lý bucket với ít thao tác tay hơn. Nhưng **Autokey không tự tạo key riêng cho từng object**; object thường dùng default CMEK đã cấu hình trên bucket, trừ khi yêu cầu object-level đặt key riêng.

### 5.4. Đặt tên và quản trị trách nhiệm

Một quy ước gợi ý:

~~~text
Key project:  sec-keys-prod
Key ring:     storage-asia-southeast1
CryptoKey:    invoices-prod
Bucket:       gs://retail-invoices-prod-EXAMPLE-UNIQUE
Owner:        Security Key Management
Consumer:     Cloud Storage service agent của bucket project
Data owner:   Finance / Orders Platform
Recovery:     Backup owner + incident runbook
~~~

Tên trên là ví dụ, không phải tài nguyên thật. Nên có:

- Key owner và data owner riêng; quyền tạo/sửa khóa tách khỏi quyền đọc object.
- Lịch rotation, retention và chính sách disable/destroy.
- Danh mục bucket/object đang sử dụng khóa.
- Địa điểm khóa phù hợp data residency.
- Cảnh báo thao tác key, IAM grant, KMS request failures và billing.

## 6. IAM: ba principal không được nhầm lẫn

### 6.1. User hoặc workload đọc/ghi object

Ứng dụng Java trên Compute Engine, GKE hoặc Cloud Run sử dụng **runtime service account** với IAM permission trên bucket. Ví dụ một service chỉ cần upload hóa đơn có thể dùng role giới hạn **tạo object** trên bucket theo quy tắc sản phẩm.

### 6.2. Cloud Storage service agent dùng CMEK

Để Cloud Storage mã hóa/giải mã object với CMEK, phải cấp quyền **`roles/cloudkms.cryptoKeyEncrypterDecrypter`** trên CryptoKey cho **service agent** thuộc **project chứa bucket**.

~~~mermaid
flowchart TD
    J["orders-api runtime service account"] -->|"storage.objects.create/get theo IAM"| S["Cloud Storage bucket<br/>ở OBJECT_PROJECT_ID"]
    S --> A["Cloud Storage service agent<br/>của OBJECT_PROJECT_ID"]
    A -->|"cloudkms.cryptoKeyVersions.useToEncrypt/Decrypt"| K["Cloud KMS CryptoKey<br/>ở KEY_PROJECT_ID"]
    T["Security team"] -. "Quản trị key và role" .-> K
~~~

**Khi gọi `storage.objects.get`, người dùng ứng dụng không nhất thiết cần trực tiếp `roles/cloudkms.cryptoKeyDecrypter`** trên KMS key. Cloud Storage dùng service agent để giải mã, còn IAM của người dùng ở bucket quyết định quyền đọc object. Đây là cơ chế quan trọng để tránh cấp KMS role cho hàng trăm tài khoản ứng dụng.

### 6.3. Người quản trị Cloud KMS

Một người cần tạo CryptoKey hoặc thay IAM trên key phải có các permission KMS thích hợp trên **key project**, ví dụ những permission nằm trong role Cloud KMS Admin. Không cấp `roles/owner` trên cả key project chỉ để thiết lập một khóa cho bucket.

### 6.4. Kiểm tra service agent

Lệnh chỉ đọc/khởi tạo service agent khi chưa tồn tại:

~~~bash
gcloud storage service-agent --project=OBJECT_PROJECT_ID
~~~

Trong project cụ thể, Cloud Storage tạo và quản lý service agent; **không tự tạo một service account bất kỳ rồi gán nó vào ô “Cloud Storage service agent”**. Cú pháp và danh tính chính xác được trả về từ lệnh trên hoặc phần Cloud Storage Settings → Project Access.

**Lưu ý:** nếu service agent chưa tồn tại, lệnh lấy service agent có thể **khởi tạo nó**. Vì thế không xem lệnh này là 100% không thay đổi trạng thái trên một project hoàn toàn mới.

## 7. Thực hành A — Khám phá cấu hình mã hóa mà không thay đổi dữ liệu

**Môi trường:** project sandbox có sẵn bucket, người học được quyền xem thông tin. Không cần tạo khóa hoặc upload.

### 7.1. Xác nhận tài khoản và bucket

~~~bash
gcloud auth list
gcloud config get-value project

gcloud storage buckets describe gs://BUCKET_NAME
~~~

Kiểm tra các trường location, storage class, default encryption, Uniform bucket-level access và các cấu hình protection mà quyền hiện tại cho phép nhìn thấy.

### 7.2. Xem default KMS key

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)"
~~~

Nếu trường `default_kms_key` rỗng/không có, điều này thường cho biết bucket chưa có **default CMEK**. Nhưng **không chứng minh mọi object đều Google-managed**, vì từng object có thể đã được upload với CMEK hoặc CSEK riêng.

### 7.3. Xem encryption metadata của một object

~~~bash
gcloud storage objects describe gs://BUCKET_NAME/OBJECT_NAME
~~~

Tìm thông tin khóa như `kms_key`/`kmsKeyName` theo dạng hiển thị của CLI/API. Khi object dùng CMEK, tên CryptoKey được ghi trong metadata. Với CSEK, có các metadata/hash liên quan đến key, **không phải raw key để tải lại**.

Cần có quyền phù hợp để xem metadata; truy vấn mô tả object có thể bị chặn nếu tài khoản không có quyền đọc, không phải bằng chứng object không tồn tại.

### 7.4. Câu hỏi đọc hiểu

1. Bucket có default CMEK không?
2. Nếu có, key nằm tại project/location nào?
3. Object đã chọn có dùng chính key mặc định đó hay một key khác?
4. Những object tạo trước khi bucket đổi default key có cần được rewrite không?
5. Nếu tài khoản ứng dụng không có IAM role đọc object nhưng Cloud Storage service agent vẫn có quyền KMS, ứng dụng có tải được object không?

## 8. Thực hành B — Chuẩn bị Cloud KMS key cho bucket

**Các lệnh phần này thay đổi tài nguyên thật và có thể tính phí.** Chỉ thực thi khi đã được cấp quyền trên **OBJECT_PROJECT_ID** và **KEY_PROJECT_ID** và đã xem kế hoạch dọn dẹp; không thực hiện trên production mà thiếu quy trình phê duyệt.

### 8.1. Bước 1: chọn bucket location

Ví dụ bucket đã được tạo trong `asia-southeast1`. Trước tiên dùng lệnh `gcloud storage buckets describe` để **xác nhận** location thực tế; không tự suy từ tên bucket.

### 8.2. Bước 2: tạo key ring và CryptoKey

~~~bash
# Cần quyền tạo key ring / key trong KEY_PROJECT_ID.
gcloud kms keyrings create storage-data \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1

# Tạo symmetric key dùng cho encryption.
gcloud kms keys create invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data \
  --purpose=encryption
~~~

Sau khi tạo, CryptoKey resource sẽ có dạng:

~~~text
projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

**Không xóa key ring như một bước dọn lab thông thường.** Cloud KMS key rings và keys có những quy tắc vòng đời khác tài nguyên VM/bucket; vật liệu khóa và các version phải được quản lý theo chính sách. Đặt tên rõ ràng và tránh dùng key project chung cho lab khi chưa có phê duyệt.

### 8.3. Bước 3: cấp quyền cho Cloud Storage service agent

Phương án do Google Cloud CLI hỗ trợ:

~~~bash
gcloud storage service-agent \
  --project=OBJECT_PROJECT_ID \
  --authorize-cmek=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

Lệnh gán quyền encrypt/decrypt cần thiết cho service agent trên key; người chạy lệnh cần có quyền **thay IAM trên CryptoKey**. Nếu không đủ quyền, yêu cầu người quản trị KMS cấp `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên **đúng key** cho email service agent được xác nhận.

Không cấp quyền KMS cho `allUsers`, `allAuthenticatedUsers` hoặc mọi thành viên nhóm developer. Ưu tiên scope **CryptoKey**, không mở role trên toàn project khóa trừ khi có lý do đã xét duyệt.

### 8.4. Bước 4: kiểm tra KMS resource

~~~bash
gcloud kms keys describe invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data

gcloud kms keys get-iam-policy invoices \
  --project=KEY_PROJECT_ID \
  --location=asia-southeast1 \
  --keyring=storage-data
~~~

Kiểm tra policy có principal service agent và role phù hợp, key có **primary version enabled** và location chính xác. Đừng suy rằng người dùng có Storage Admin là đã tự có quyền sửa IAM trên key ở một project khác.

## 9. Thực hành C — Đặt và kiểm tra default CMEK của bucket

### 9.1. Thiết lập qua Google Cloud Console

1. Mở **Cloud Storage → Buckets**, chọn đúng bucket sandbox.
2. Vào **Configuration → Protection → Edit encryption** (hoặc tên menu tương ứng).
3. Tại **Default encryption key type**, chọn **Cloud KMS key**.
4. Chọn key đã chuẩn bị đúng **bucket location**, xác nhận quyền service agent.
5. Kiểm tra tác động dự kiến, lưu thay đổi và đọc lại bucket configuration.

### 9.2. Thiết lập bằng gcloud

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --default-encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/invoices
~~~

Đọc lại:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)"
~~~

Nếu thành công, bucket sẽ dùng CryptoKey đó cho **các object mới được tạo** nếu request không chỉ định key khác và nếu encryption enforcement cho phép phương thức đó.

### 9.3. Tạo object test mới

Ví dụ file mẫu không nhạy cảm:

~~~bash
printf "Cloud Storage CMEK lab\n" > cmek-test.txt

gcloud storage cp cmek-test.txt \
  gs://BUCKET_NAME/labs/cmek-test.txt

gcloud storage objects describe \
  gs://BUCKET_NAME/labs/cmek-test.txt
~~~

Đọc object metadata, xác nhận khóa thực sự dùng. Nếu bucket đã có default CMEK và service agent có quyền, quá trình upload thường dùng default key.

### 9.4. Chỉ định CMEK riêng cho object

Khi một object cần key khác, có thể upload:

~~~bash
gcloud storage cp cmek-test.txt \
  gs://BUCKET_NAME/labs/special-object.txt \
  --encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/KEY_FOR_SPECIAL_OBJECT
~~~

Ví dụ chỉ hoạt động khi `KEY_FOR_SPECIAL_OBJECT` **đã tồn tại**, có primary version hợp lệ, ở location tương thích và service agent có quyền dùng key đó. Nó cho thấy **per-object key có thể ghi đè default key**.

### 9.5. Gỡ default KMS key để quay lại Google-managed cho object tương lai

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --clear-default-encryption-key
~~~

Đây là thao tác **đổi cấu hình bucket**, không phải giải mã/mã hóa lại dữ liệu cũ. Object trước đó vẫn dùng CMEK nếu chưa rewrite. Nếu bucket có **encryption enforcement** cấm Google default encryption thì việc tạo object mới theo phương thức này có thể bị chặn; phải kiểm tra policy trước.

**Không nhầm việc gỡ default CMEK với vô hiệu hóa CryptoKey.** Gỡ default chỉ ảnh hưởng hành vi ghi mới; disable key có thể chặn đọc object cũ và gây gián đoạn.

## 10. Encryption enforcement: giới hạn phương thức được phép trên bucket

Chỉ đặt một **default CMEK** chưa đủ để bảo đảm *mọi object mới* đều được bảo vệ bằng CMEK, vì request có thể cung cấp một CSEK hoặc CMEK khác. Cloud Storage còn hỗ trợ **encryption enforcement rules** tại cấp bucket để cho phép hoặc hạn chế phương thức mã hóa khi **tạo object mới**.

### 10.1. Ba loại có thể giới hạn

| Loại | Tên trong file cấu hình | Giá trị giới hạn |
|---|---|---|
| Google default encryption | `gmekEnforcement` | `FullyRestricted` hoặc `NotRestricted` |
| Customer-managed CMEK | `cmekEnforcement` | `FullyRestricted` hoặc `NotRestricted` |
| Customer-supplied CSEK | `csekEnforcement` | `FullyRestricted` hoặc `NotRestricted` |

`FullyRestricted` nghĩa là không cho tạo object bằng loại đó. `NotRestricted` nghĩa là loại đó được phép. Phải cho phép **ít nhất một** phương thức mã hóa.

Enforcement áp dụng cho các thao tác tạo object như **upload, copy, compose, restore soft-deleted object** theo phạm vi dịch vụ; **không tự thay đổi loại mã hóa của object đã tồn tại**.

### 10.2. Ví dụ bucket chỉ cho phép CMEK

Tạo file **chỉ trong môi trường lab**, không đưa vào repo bí mật:

~~~json
{
  "gmekEnforcement": { "restrictionMode": "FullyRestricted" },
  "cmekEnforcement": { "restrictionMode": "NotRestricted" },
  "csekEnforcement": { "restrictionMode": "FullyRestricted" }
}
~~~

Lưu ví dụ thành `encryption-enforcement.json`, sau đó cập nhật:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --encryption-enforcement-file=encryption-enforcement.json
~~~

**Hành động trên chỉ để minh họa cấu hình.** Trước khi áp production, đánh giá các job, pipeline, client libraries, Transfer Service, sao chép dữ liệu và cách chúng chọn khóa. Với bucket chỉ cho phép CMEK, các lần upload không có key riêng phải dùng **default CMEK hợp lệ**; những thao tác tạo object không tuân thủ sẽ thất bại.

**Lưu ý thực tế:**

- Sau khi cập nhật, cấu hình có thể cần một khoảng thời gian để có hiệu lực (tài liệu nêu có thể tới khoảng **hai phút**).
- Với bucket đã có default CMEK, Cloud Storage không cho cấu hình hạn chế **cả CMEK lẫn CSEK** theo các giới hạn được công bố nếu không bỏ default key.
- Cấm Google default encryption **không có nghĩa tự chuyển object cũ sang CMEK**.
- Đừng chặn CSEK nếu còn hệ thống nghiệp vụ đang sử dụng CSEK mà chưa lập kế hoạch migrate.

### 10.3. Mặc định và enforcement giải quyết hai câu hỏi khác nhau

- **Default KMS key:** “Nếu client không nói gì, Cloud Storage nên dùng key nào cho object mới?”
- **Encryption enforcement:** “Những phương thức mã hóa nào **được phép** tạo object trong bucket này?”

Đối với compliance yêu cầu CMEK trên tất cả object mới, dùng **cả default CMEK lẫn enforcement chỉ cho CMEK** là một phương án rõ ràng. Tuy nhiên, việc kiểm tra hiện trạng đối với object cũ vẫn cần kiểm kê và rewrite theo kế hoạch.

## 11. Rotation, replacement và re-encryption

### 11.1. Rotation của Cloud KMS CryptoKey

Cloud KMS có thể tạo **CryptoKeyVersion mới** và đặt version mới làm **primary**. Khi Cloud Storage thực hiện những thao tác ghi mã hóa mới bằng **cùng CryptoKey**, nó dùng primary version mới theo cơ chế dịch vụ.

~~~text
Ngày 01:
  CryptoKey invoices
  primary version = 1
  object-A được bảo vệ bằng version 1

Ngày 90:
  CryptoKey invoices rotation
  primary version = 2
  object-B upload sau rotation → version 2

Object-A:
  vẫn phụ thuộc version 1 nếu không rewrite
~~~

**Rotation không tự mã hóa lại các object đã có.** Version 1 vẫn cần khả dụng để đọc object-A. Đừng disable/destroy version cũ chỉ vì version mới đã thành primary.

### 11.2. Key replacement là thay cả CryptoKey

Nếu tổ chức chuyển từ `key-A` sang `key-B`:

1. Xác định mọi bucket có default `key-A`.
2. Tạo `key-B` tại location tương thích và cấp role cho đúng service agent.
3. Đổi default bucket sang `key-B` và cập nhật những client đang chỉ định `key-A` ở từng upload.
4. Lập danh mục object/generation còn dùng `key-A`.
5. **Rewrite** object cần chuyển sang `key-B`, có kiểm tra generation/concurrency và chính sách retention.
6. Xác minh metadata và thử download thật với tài khoản hợp lệ.
7. Chỉ sau khi xác định không còn dependency cần giữ mới cân nhắc vô hiệu hóa version cũ theo quy trình change/retention.

Nếu có hàng triệu object, dùng **Storage batch operations** có hỗ trợ re-encryption theo prefix/manifest. Phải dự trù thời gian, API operations, chi phí rewrite và đối soát kết quả.

### 11.3. Rewrite object cụ thể

Lệnh minh họa trong sandbox:

~~~bash
gcloud storage objects update gs://BUCKET_NAME/labs/cmek-test.txt \
  --encryption-key=projects/KEY_PROJECT_ID/locations/asia-southeast1/keyRings/storage-data/cryptoKeys/NEW_KEY
~~~

Tuy lệnh có tên `objects update`, thay encryption key sẽ thực hiện **rewrite object**. Đây không phải chỉnh metadata thuần túy.

Để chuyển object về phương thức mặc định hiện có trên bucket (hoặc Google default nếu bucket không có CMEK):

~~~bash
gcloud storage objects update gs://BUCKET_NAME/labs/cmek-test.txt \
  --clear-encryption-key
~~~

Nếu bucket có enforcement không cho phép phương thức đích, rewrite có thể bị từ chối. Không thực hiện trên object production có retention lock/holds mà chưa kiểm tra constraints.

### 11.4. Versioning, soft delete và retention ảnh hưởng migration

| Cơ chế | Tác động khi rewrite/rotate |
|---|---|
| **Object Versioning** | Generation cũ có thể còn tồn tại với **key cũ**; phải quản lý cả noncurrent versions |
| **Soft delete** | Bản cũ có thể còn trong thời gian lưu giữ; không tự biến mất sau rewrite |
| **Retention policy / object retention** | Có thể hạn chế thay đổi/xóa cho đến hết thời gian cam kết |
| **Object holds** | Có thể chặn xóa/đổi theo semantics được hỗ trợ |
| **Lifecycle rules** | Có thể tự động xử lý generation cũ khi đủ điều kiện; phải kiểm thử để tránh xóa nhầm |
| **Nearline/Coldline/Archive** | Rewrite/copy có thể phát sinh request/early deletion charges nếu trước hạn |

**Mục tiêu audit:** không chỉ thấy live object dùng key-B; phải tìm cả **generation cũ, soft-deleted object, backup và bản sao ở bucket khác** còn phụ thuộc key-A trước khi hủy khóa.

## 12. Khi KMS key bị disable, destroy hoặc mất quyền

### 12.1. Disable và destroy khác nhau

| Thao tác | Tác động chính | Khả năng phục hồi |
|---|---|---|
| Gỡ default CMEK khỏi bucket | Ghi mới có thể quay về default server-side key nếu enforcement cho phép | Không thay dữ liệu cũ |
| Revoke IAM `cryptoKeyEncrypterDecrypter` của service agent | Cloud Storage có thể không mã hóa/giải mã bằng key đó được nữa | Có thể cấp lại đúng role |
| **Disable CryptoKeyVersion** | Object phụ thuộc version đó có thể không đọc/rewrite được | Có thể **enable lại** nếu chưa bị destroy |
| **Destroy CryptoKeyVersion** | Dữ liệu còn phụ thuộc version ấy có thể **mất khả năng giải mã vĩnh viễn** | Không thể khôi phục plaintext chỉ từ Cloud Storage |
| Không có primary version hợp lệ | Upload/copy/rewrite cần encrypt bằng key có thể thất bại | Rotation hoặc tạo primary hợp lệ |
| Cloud EKM/external key manager không khả dụng | Operations có thể thất bại dù storage còn khỏe | Phụ thuộc khôi phục external key manager/đường kết nối |

**Hậu quả quan trọng:** destroy khóa không đồng nghĩa Cloud Storage xóa object hoặc dừng tính tiền lưu trữ. Object có thể **vẫn tồn tại và vẫn phát sinh phí**, nhưng nội dung không thể giải mã.

### 12.2. Disable key không phải biện pháp dọn dẹp thông thường

Trong môi trường thực:

- Dùng **disable** chỉ khi có quy trình ứng cứu hoặc kiểm soát truy cập được phê duyệt.
- Hiệu lực thay đổi khóa/IAM có thể có **độ trễ đồng bộ**, không cam kết chặn ngay lập tức mọi yêu cầu.
- Cần giám sát lỗi upload/download/compose/rewrite và tác động ứng dụng.
- Khi cần khôi phục, xác nhận quyền service agent và key version trước khi thử lại.
- Với **destroy**, cần kiểm soát nhiều người phê duyệt, rà object dependencies và quy trình backup/restore.

### 12.3. Tại sao mất key ảnh hưởng cả ứng dụng không quản trị khóa?

Ví dụ Java Orders API có quyền `storage.objects.get` trên bucket. Key nằm ở một project bảo mật khác, được quản trị viên KMS vô tình disable. API vẫn xác thực và được IAM cho phép nhưng **Cloud Storage không còn giải mã nội dung**; ứng dụng nhận lỗi. Điều tra phải kiểm tra **key status và service agent IAM**, không giải quyết bằng cách gán `roles/storage.admin` cho API.

## 13. Tình huống thực tế: bucket chứa hóa đơn PDF

### 13.1. Bối cảnh hệ thống

Công ty bán lẻ `RetailOne` triển khai:

- **Cloud Run Orders API Java** trong project `retail-app-prod`.
- **Cloud SQL** lưu bản ghi đơn hàng.
- **Cloud Storage** bucket `gs://retail-invoices-prod-EXAMPLE-UNIQUE` chứa hóa đơn PDF.
- **Key project** `retail-security-keys` do đội Security quản trị.
- Bucket đặt tại region `asia-southeast1`, key ring cùng location.
- Đội FinOps muốn dự toán chi phí Cloud KMS, Storage operations và retention.

~~~mermaid
flowchart LR
    API["Java Orders API<br/>Cloud Run runtime identity"]
    API -->|"storage.objects.create / get"| B["Cloud Storage bucket invoices"]
    B -->|"dịch vụ dùng CMEK"| SA["Cloud Storage service agent"]
    SA --> K["CryptoKey invoices-prod<br/>KMS location asia-southeast1"]
    SEC["Security team"] -. "Quản lý rotation + IAM trên key" .-> K
    FIN["FinOps"] -. "Báo cáo chi phí và retention" .-> B
    FIN -. "KMS usage/chi phí" .-> K
~~~

### 13.2. Thiết kế khuyến nghị

1. **Chủ dữ liệu** phân loại hóa đơn, retention và yêu cầu phục hồi/tuân thủ.
2. **Security** tạo key trong project riêng, chọn location trùng bucket và cấu hình vòng đời khóa.
3. **Cloud Storage service agent** của `retail-app-prod` được cấp `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên CryptoKey.
4. **Orders API service account** có quyền tạo/đọc object ở bucket theo nhu cầu, không được cấp Cloud KMS Admin.
5. Bucket có default CMEK và, nếu compliance yêu cầu, **enforcement chỉ cho phép CMEK**.
6. Thiết lập Uniform bucket-level access, public access prevention, dữ liệu backup/soft delete/retention và logging phù hợp.
7. Khi deploy, API upload hóa đơn và theo dõi generation/checksum, request ID và errors.
8. Khi rotate key, kiểm thử các object mới/cũ; nếu cần chuyển toàn bộ sang CryptoKey khác, dùng rewrite/batch operations và kiểm kê generation.
9. Đội vận hành định kỳ thử download bản hóa đơn cũ được chọn để xác minh key version cũ vẫn khả dụng.

### 13.3. Vì sao không chọn CSEK mặc định cho mọi hóa đơn?

Đội ứng dụng cần pipeline Cloud Run, retry, background job, backup, truy xuất PDF và một số tích hợp quản lý dữ liệu. Nếu dùng CSEK, client phải bảo vệ và cung cấp raw key đúng cho từng object khi cần, trong khi một số công cụ có thể không hỗ trợ CSEK. **CMEK qua Cloud KMS** thường là lựa chọn dễ quản trị hơn khi yêu cầu chính là **điều khiển vòng đời khóa và chứng cứ audit**.

Nếu yêu cầu cao hơn là chỉ ứng dụng bên ngoài mới nhìn thấy plaintext, cân nhắc client-side encryption với quy trình key escrow và phục hồi đã thiết kế, không đồng nhất nhu cầu này với CMEK thông thường.

## 14. Chẩn đoán sự cố mã hóa

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Set default CMEK không được | KMS key location sai, key không hợp lệ, thiếu quyền service agent | Kiểm tra bucket location, KMS resource và role |
| Upload object trả `403` | Thiếu `storage.objects.create`, KMS key IAM sai hoặc policy khác chặn | Đọc error details, IAM bucket + key + encryption rules |
| Bucket default CMEK đúng nhưng object dùng CSEK | Request đã chỉ định per-object CSEK | Kiểm tra client flags/headers và enforcement |
| Object cũ vẫn dùng key-A sau đổi default key-B | Thay bucket default **không retroactive** | Rewrite object/generation cần migrate |
| Download object thất bại sau rotation | Version cũ bị disable/destroy hoặc service agent mất quyền | Đọc object encryption metadata và KMS versions |
| Bật CMEK-only nhưng upload từ pipeline cũ lỗi | Pipeline gửi CSEK/Google-managed request không hợp lệ | Kiểm tra encryption enforcement và chỉnh client |
| Tạo KMS key ở `global` nhưng bucket ở `asia-southeast1` | Key ring location không khớp bucket | Tạo key tại location phù hợp |
| Không có quyền xem KMS key policy | Người dùng có Storage role nhưng không có quyền trên key project | Nhờ KMS admin hỗ trợ, không tự cấp Owner |
| KMS HSM/EKM request lỗi hoặc chậm | Quota, external key manager availability, latency, auth | Kiểm tra quota, KMS logs và nhà cung cấp EKM |
| Re-encryption ảnh hưởng chi phí | Rewrite nhiều object, storage class/early deletion, retention | Dự toán API operations và lịch migration |
| Console không download được object CSEK | Console không hỗ trợ luồng CSEK đó | Dùng công cụ/API hỗ trợ và key theo quản lý secret |
| Không tìm thấy hash/checksum trong danh sách objects | CMEK/CSEK có hạn chế metadata trên LIST | Dùng metadata GET khi được cấp quyền |
| Disable key nhưng metadata object vẫn xem được | Tên/metadata không phụ thuộc cùng CMEK payload | Dùng IAM để giới hạn metadata, không xem disable là xóa |
| Ransomware xóa object dù CMEK đang bật | Encryption không ngăn xóa hợp lệ theo IAM | Dùng IAM tối thiểu, retention/soft delete/backup |
| Đọc được object dù team dev không có IAM KMS | Cloud Storage dùng **service agent** thay mặt request | Kiểm tra IAM storage và KMS agent riêng |

### 14.1. Quy trình điều tra trước khi cấp thêm quyền

1. Ghi **principal**, bucket/object/generation, thao tác `get/create/rewrite`, request time và error.
2. Kiểm tra **IAM Storage** ở bucket/project và quyền kế thừa.
3. Xem **default CMEK** và **encryption enforcement** của bucket.
4. Xem **per-object encryption metadata** để biết object có dùng CMEK/CSEK/key cũ hay không.
5. Nếu CMEK, xác nhận **service agent đúng project**, quyền KMS và vị trí/primary version/key state.
6. Nếu CSEK, kiểm tra key được bảo quản đúng và client có cung cấp key hợp lệ trong request (không dán raw key vào log).
7. Kiểm tra Cloud Audit Logs của Storage/KMS và application logs với quyền phù hợp.
8. Chỉ thay đổi cấu hình sau khi xác định nguyên nhân; thử object **không nhạy cảm** trong sandbox và có rollback.

### 14.2. Logging và bảo vệ nhật ký

- **Cloud Audit Logs của Cloud Storage:** cấu hình và truy cập dữ liệu theo loại log/tính năng được bật.
- **Cloud KMS audit logs:** hoạt động quản trị khóa và việc sử dụng key theo loại Data Access logs/cấu hình.
- **Cloud Monitoring:** lỗi request, latency, quota và tín hiệu ứng dụng.
- **Billing reports:** chi phí Cloud KMS/Cloud HSM/Cloud EKM, object storage, rewrite, lưu giữ và network.

Không ghi raw encryption key, access token, signed URL hoặc thông tin nhạy cảm vào log. KMS audit có thể chứa resource name và principal; chỉ cấp người có nhiệm vụ đọc.

## 15. Giá và vận hành vòng đời khóa

### 15.1. Các nguồn chi phí

| Thành phần | Có thể phát sinh |
|---|---|
| Cloud Storage object data | Phí lưu trữ theo class, location, thời gian |
| Storage API operations | Upload/download/copy/rewrite, metadata requests |
| Soft delete / versioning / retention | Dữ liệu và generations còn được lưu |
| Cloud KMS key versions | Phí key/version theo loại sản phẩm |
| Cloud KMS cryptographic operations | Phụ thuộc key protection level và loại operation |
| Cloud HSM/Cloud EKM | Giá, quota và vận hành riêng |
| Data transfer | Egress, cross-region theo cấu hình |
| Cloud Logging | Ingest/storage/retention/query theo quy tắc dịch vụ |
| Tích hợp ứng dụng | Chi phí vận hành failure handling, DR, compliance và audit |

Không dùng đơn giá cố định vì giá thay đổi theo location/SKU và chương trình. Với Cloud KMS **software key**, có những hoạt động cryptographic của Cloud Storage không tiêu thụ quota KMS theo cùng cách HSM/EKM; khi dùng HSM/EKM cần đặc biệt xem quota, độ trễ và phụ thuộc dịch vụ.

### 15.2. Quyết định dựa trên mức rủi ro

| Yêu cầu kinh doanh | Phương án bắt đầu đánh giá |
|---|---|
| File public/tĩnh, không có yêu cầu tự quản key | Google default encryption + IAM/public access policy phù hợp |
| Hóa đơn/hợp đồng cần kiểm toán quyền quản lý khóa | CMEK, key project riêng và audit |
| Tổ chức có chính sách chìa khóa bảo vệ bởi HSM | CMEK với Cloud HSM khi tương thích |
| Chính sách yêu cầu key material nằm ngoài Google Cloud | Cloud EKM hoặc client-side encryption theo threat model |
| Ứng dụng phải cung cấp raw key từ hệ thống ngoài | CSEK nếu hạn chế tích hợp chấp nhận được |
| Muốn đảm bảo object mới không dùng Google default/CSEK | Bucket default CMEK + encryption enforcement CMEK-only |
| Muốn chống xóa nhầm/đòi khôi phục dữ liệu | Versioning, soft delete, retention, backup; **không chỉ mã hóa** |

## 16. Bài tập thực hành và tự đánh giá

### Bài 1 — Default không retroactive

Bucket `reports` ban đầu dùng Google default encryption. Ngày 01/02, admin bật default CMEK key `key-A`; ngày 01/03 đổi sang `key-B`. Hai object `jan.csv` và `feb.csv` lần lượt được upload vào tháng 01 và tháng 02, request không chỉ định khóa riêng.

**Câu hỏi:** object nào dùng key nào? Nếu destroy `key-A` ngay sau ngày 01/03, rủi ro gì? Muốn chuyển tất cả object sang key-B cần làm gì?

**Gợi ý:** `jan.csv` vẫn dùng Google default encryption; `feb.csv` dùng key-A; đổi default không rewrite. Hãy kiểm kê old generations, rewrite object và thử read trước khi bỏ key-A.

### Bài 2 — Per-object override

Bucket mặc định CMEK `key-A`. Client upload object mới bằng CSEK còn chính sách bucket vẫn cho phép cả CMEK và CSEK.

**Câu hỏi:** object dùng phương thức nào? Làm sao buộc mọi object mới chỉ được dùng CMEK?

**Gợi ý:** request CSEK ghi đè bucket default khi hợp lệ; dùng encryption enforcement hạn chế Google default và CSEK.

### Bài 3 — KMS key location

Bucket nằm trong dual-region có location code `ASIA` với cặp region hợp lệ. Đội bảo mật đề xuất tạo key ring chỉ ở `asia-southeast1`.

**Câu hỏi:** có đúng không? Cần chọn key ring location nào?

**Gợi ý:** key ring phải trùng **location code của bucket**; với configurable dual-region này là `asia`, không phải một region thành viên.

### Bài 4 — Service agent

Ứng dụng Java có `roles/storage.objectViewer` ở bucket. Cloud Storage service agent mất `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên CryptoKey, sau đó API không tải được object CMEK.

**Câu hỏi:** có nên gán `roles/cloudkms.admin` cho ứng dụng không? Người quản trị cần kiểm tra điều gì?

**Gợi ý:** không. Kiểm tra service agent của bucket project, IAM trên CryptoKey, state/version và error; cấp lại role đúng service agent nếu được phê duyệt.

### Bài 5 — Rotation và rủi ro mất dữ liệu

Sau rotation, team thấy `CryptoKeyVersion 1` không còn primary và muốn destroy ngay cho “an toàn”. Một số object không được rewrite.

**Câu hỏi:** việc này có thể khiến object không đọc được không? Cần danh sách và thử nghiệm gì?

**Gợi ý:** có. Object cũ vẫn phụ thuộc version 1; kiểm kê từng generation, rewrite, thử download, đối soát retention/backup và chỉ destroy khi được phê duyệt.

### Bài 6 — CSEK và tích hợp

Pipeline Storage Transfer Service phải chuyển dữ liệu từ bucket A sang B. Một phần object nguồn dùng CSEK.

**Câu hỏi:** điều gì cần kiểm tra trước khi chạy transfer? Vì sao CSEK có thể gây khó khăn hơn CMEK?

**Gợi ý:** kiểm tra hạn chế tích hợp, thiết kế chuyển/rewrite CSEK sang CMEK hoặc Google default trong môi trường kiểm soát; key raw không được tự do đưa vào pipeline/log.

### Bài 7 — Lựa chọn cho hệ thống Java

Một nhóm triển khai API Java trên Cloud Run, lưu tài liệu từ người dùng vào Cloud Storage và phải chứng minh key rotation mỗi 90 ngày, tách quản trị khóa khỏi quản trị object. Doanh nghiệp cũng cần phục hồi dữ liệu bị xóa nhầm.

**Yêu cầu:** thiết kế bucket, key project, service agent IAM, encryption enforcement, rotation/rewrite và backup/soft delete. Đặt cảnh báo nào để phát hiện khóa bị disable hoặc mất quyền?

**Gợi ý:** CMEK ở Cloud KMS key project riêng, default CMEK bucket + CMEK-only nếu cần, agent role tối thiểu; rotation không thay thế rewrite; backup/lifecycle/retention giải quyết lỗi logic.

## 17. Checklist trước khi đưa CMEK lên production

- [ ] Đã xác định dữ liệu, người sở hữu và yêu cầu compliance/threat model.
- [ ] Đã phân biệt mã hóa at rest, TLS và client-side encryption.
- [ ] Đã chọn Google-managed, CMEK, CSEK hoặc client-side theo nhu cầu thật.
- [ ] Đã đối chiếu **bucket location = KMS key ring location** theo quy tắc region/dual-region/multi-region.
- [ ] CryptoKey là **symmetric encryption key** phù hợp; đã chọn protection level/tier.
- [ ] Key project, bucket project, team quản trị và owner dữ liệu được tách nhiệm vụ hợp lý.
- [ ] Đã xác nhận Cloud Storage **service agent đúng bucket project** và quyền KMS trên CryptoKey.
- [ ] Runtime service account có IAM trên bucket đúng nhu cầu, **không mặc định có KMS Admin**.
- [ ] Đã kiểm tra default key **chỉ áp dụng cho object mới**, không tự rewrite object cũ.
- [ ] Đã kiểm tra upload có per-object key và **encryption enforcement** cho đối tượng mới.
- [ ] Đã kiểm kê live/noncurrent/soft-deleted generations và key dependencies trước rotation/destroy.
- [ ] Đã thử upload/download/copy/rewrite và khôi phục object thử trong sandbox.
- [ ] Đã có playbook khi KMS key disabled, IAM bị revoke hoặc Cloud EKM mất kết nối.
- [ ] Đã có bảo vệ object khác: IAM, uniform bucket-level access, public access prevention, retention/soft delete/backup.
- [ ] Đã bật audit log/monitoring hợp lý, bảo mật thông tin KMS/metadata và đánh giá chi phí.
- [ ] Đã hiểu **xóa/destroy key không xóa object hay dừng phí lưu trữ**.
- [ ] Đã có người phê duyệt, rollback và kiểm tra trạng thái sau mỗi thay đổi.

## 18. Tài liệu chính thức của Google Cloud

Tính năng, giao diện và giới hạn được Google Cloud cập nhật theo thời gian. Trước khi thao tác trên hệ thống thật, đối chiếu tài liệu:

- [Cloud Storage — Data encryption options](https://docs.cloud.google.com/storage/docs/encryption)
- [Customer-managed encryption keys (CMEK)](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Use customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Get the Cloud Storage service agent](https://docs.cloud.google.com/storage/docs/getting-service-agent)
- [Enforce or restrict encryption types on a bucket](https://docs.cloud.google.com/storage/docs/encryption/enforce-encryption-types)
- [Customer-supplied encryption keys (CSEK)](https://docs.cloud.google.com/storage/docs/encryption/customer-supplied-keys)
- [Use customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-supplied-keys)
- [Cloud KMS — Customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [Cloud Storage bucket locations](https://docs.cloud.google.com/storage/docs/locations)
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update)
- [gcloud storage objects update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [gcloud storage service-agent](https://docs.cloud.google.com/sdk/gcloud/reference/storage/service-agent)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Cloud KMS pricing](https://cloud.google.com/kms/pricing)

**Điểm cần nhớ:** Cloud Storage **mã hóa mọi object ở trạng thái lưu trữ**; phương án mặc định của Google phù hợp đa số workload, trong khi **CMEK** giúp tổ chức kiểm soát vòng đời khóa qua Cloud KMS. **Bucket default CMEK không mã hóa lại object cũ** và không nhất thiết chặn **per-object override**; muốn bắt buộc CMEK cho các object mới, cần thiết kế thêm **encryption enforcement**. Đối với dữ liệu quan trọng, quản lý khóa phải đi cùng **IAM tối thiểu, key availability, rotation có kiểm thử, backup/restore, logging và dự toán chi phí**. Hủy khóa mà object còn phụ thuộc có thể làm dữ liệu mất khả năng giải mã vĩnh viễn.
