# Autoclass và object lifecycle management

> **Chương:** Cloud Storage  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một hệ thống trên Google Cloud có thể sinh hàng triệu tệp: ảnh người dùng được đọc thường xuyên trong vài ngày đầu, file log chỉ phục vụ điều tra, báo cáo xuất hằng tháng, bản sao lưu có thể không được đọc trong nhiều năm và dữ liệu tạm chỉ cần giữ vài tuần. Nếu mọi object đều lưu ở **Standard storage** mãi mãi, chi phí lưu trữ có thể cao; nếu chuyển hết sang **Archive**, chi phí thao tác, mức sử dụng và yêu cầu phục hồi có thể không phù hợp. Cloud Storage cung cấp hai cơ chế quan trọng để tự động quản trị vòng đời object:

- **Autoclass:** tự quyết định **storage class** dựa trên hoạt động **đọc dữ liệu object**; thuận tiện khi tần suất truy cập khó dự đoán.
- **Object Lifecycle Management (OLM):** chạy các **hành động đã cấu hình** khi object đáp ứng điều kiện như tuổi, tiền tố tên, phiên bản hoặc ngày trong metadata; phù hợp để chuyển lớp có quy tắc và **xóa dữ liệu hết hạn**.

Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, nơi người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống vận hành, người học cần biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài này dùng ví dụ Cloud Storage cho API Java, pipeline dữ liệu và bản sao lưu để đưa ra lựa chọn có căn cứ thay vì bật automation theo cảm tính.

**Kết quả học tập:** Sau bài này, bạn có thể:

1. Phân biệt object, bucket, storage class, access pattern, lifecycle rule và retention.
2. Diễn giải cách Autoclass chuyển giữa Standard, Nearline, Coldline và Archive; biết ngưỡng kích thước và các loại phí.
3. Thiết kế lifecycle rules dạng JSON cho `Delete`, `SetStorageClass` và `AbortIncompleteMultipartUpload`.
4. Chọn đúng cơ chế theo yêu cầu truy cập, lưu trữ, bảo mật, khôi phục và chi phí.
5. Nhận diện quy tắc **không tương thích giữa Autoclass và Lifecycle Management**.
6. Bật và kiểm tra tính năng bằng Console hoặc `gcloud storage` trong project thử nghiệm.
7. Xử lý các trường hợp object chưa chuyển lớp, chưa xóa, không thể xóa hoặc chi phí tăng bất ngờ.
8. Lập kế hoạch kiểm thử, giám sát, bảo vệ dữ liệu và rollback trước khi áp dụng production.

## 1. Hiểu mô hình Cloud Storage trước khi cấu hình tự động

**Cloud Storage** là dịch vụ lưu trữ object. Dữ liệu được tổ chức thành **buckets**, trong mỗi bucket có các **objects**. Một object gồm dữ liệu và metadata, được định danh bằng tên; với versioning, các **generations** có thể lưu nhiều phiên bản cùng tên.

~~~text
Google Cloud project: order-platform-prod
  └── Bucket: gs://order-assets-prod
      ├── receipts/2026/11/order-123.pdf     (object)
      ├── images/products/item-456.jpg      (object)
      ├── reports/monthly/2026-10.csv       (object)
      ├── temp/exports/task-789.json        (object)
      └── backups/db/2026-11-01.dump        (object)
~~~

Trong bucket **flat namespace**, các dấu `/` trong tên thường được dùng như prefix logic chứ không nhất thiết là thư mục hệ điều hành. Với **hierarchical namespace**, Cloud Storage hỗ trợ thư mục theo mô hình riêng; khi lập lifecycle rule vẫn phải đọc chính xác quy tắc khớp prefix và phạm vi dữ liệu.

### 1.1. Bucket location khác object storage class

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Bucket location** | `asia-southeast1`, dual-region hoặc multi-region | Nơi dữ liệu được lưu theo lựa chọn vùng |
| **Storage class của object** | Standard, Nearline, Coldline, Archive | Mô hình giá và đặc điểm truy cập/lưu trữ |
| **Default storage class** | Standard | Storage class mặc định cho object mới khi không chỉ định khác |
| **Retention policy** | Giữ ít nhất 365 ngày | Cấm xóa/ghi đè sớm khi chưa đáp ứng điều kiện |
| **Soft delete policy** | Có thể giữ bản đã xóa thêm một khoảng | Cơ chế phục hồi sau xóa |
| **Object Versioning** | Lưu generations đã bị ghi đè/xóa | Hỗ trợ phục hồi các phiên bản |
| **Autoclass** | Enabled, terminal storage class | Dịch vụ tự chuyển lớp dựa trên truy cập |
| **Lifecycle configuration** | Một hoặc nhiều rules | Dịch vụ tự làm hành động theo điều kiện |

Chuyển object từ Standard sang Nearline **không di chuyển bucket sang region khác**. Giảm storage cost bằng cách đổi class cũng không thay đổi quyền IAM, VPC Service Controls, khóa mã hóa hay cấu hình truy cập public của bucket.

### 1.2. Storage classes thường gặp

| Storage class | Ý định sử dụng thường thấy | Minimum storage duration khi **quản lý thủ công** | Retrieval fee theo bảng giá thông thường |
| --- | --- | --- | --- |
| **Standard** | Đọc thường xuyên, ứng dụng hoạt động | Không có | Không |
| **Nearline** | Đọc không thường xuyên, ví dụ ít hơn mỗi tháng | 30 ngày | Có |
| **Coldline** | Dữ liệu lạnh hơn, dự kiến đọc rất ít | 90 ngày | Có |
| **Archive** | Dữ liệu lưu dài hạn, hiếm khôi phục | 365 ngày | Có |

Cloud Storage còn có các khả năng/lớp lưu trữ khác như **Rapid storage** trong những mô hình bucket riêng. Tuy nhiên, chuỗi Autoclass được học trong bài này áp dụng các class Standard, Nearline, Coldline và Archive.

**Lưu ý:** Archive của Cloud Storage không có nghĩa phải mở một yêu cầu phục hồi kéo dài nhiều giờ như một số hệ thống băng từ. Object vẫn có khả năng truy cập online theo dịch vụ; chi phí request/retrieval và minimum storage duration mới là yếu tố cần tính, ngoại trừ các cơ chế miễn trừ dành riêng cho Autoclass.

## 2. Hai hình thức tự động: điểm giống và khác

~~~mermaid
flowchart TB
  BUCKET["Cloud Storage bucket"] --> A{"Chọn chiến lược"}
  A --> AUTO["Autoclass\nTheo lịch sử truy cập dữ liệu"]
  A --> LC["Object Lifecycle Management\nTheo action + condition"]
  AUTO --> COST["Tối ưu class, tự đưa lên Standard khi được đọc"]
  LC --> DELETE["Delete sau hạn hoặc xóa phiên bản"]
  LC --> TRANS["SetStorageClass nếu không bật Autoclass"]
  AUTO -. "Có thể phối hợp với rule Delete" .-> DELETE
~~~

| Tiêu chí | Autoclass | Object Lifecycle Management |
| --- | --- | --- |
| Phạm vi cấu hình | **Cả bucket** | Quy tắc trên bucket, áp dụng đối tượng phù hợp |
| Căn cứ quyết định | **Đọc dữ liệu** object; hệ thống theo dõi mức truy cập | `age`, `isLive`, `matchesPrefix`, `customTime`, class... |
| Thay storage class | **Tự động** theo đường chuyển của Google | **Theo rule** `SetStorageClass` tự khai báo |
| Tự chuyển object được đọc về Standard | **Có**, theo quy tắc Autoclass | Không phải hành vi mặc định của lifecycle |
| Xóa object hết hạn | **Không** | **Có** qua `Delete` |
| Xóa incomplete multipart upload | Không phải chức năng Autoclass | **Có** qua `AbortIncompleteMultipartUpload` |
| Quản lý class theo prefix khác nhau | Không: logic áp dụng cho bucket, có loại trừ theo kích thước | Có thể khai báo rules theo `matchesPrefix` |
| Cần dự báo truy cập | Ít cần hơn | Cần thiết kế timeline và điều kiện phù hợp |
| Chi phí đáng chú ý | Management fee, enablement charge, các loại operation, storage | Operation chuyển lớp, minimum duration/early deletion khi xóa, lưu trữ |
| Dùng chung trong một bucket? | **Có giới hạn:** cho phép một số lifecycle actions | **Không được** `SetStorageClass` hay `matchesStorageClass` khi Autoclass enabled |

**Điểm quyết định:** Autoclass và Lifecycle Management **không phải hai tên cho cùng một tính năng**. Autoclass tối ưu lớp lưu trữ theo access, còn lifecycle giải quyết các quy tắc vòng đời như *“xóa file tạm sau 30 ngày”* hoặc *“xóa phiên bản cũ sau 90 ngày”*.

### 2.1. Ví dụ phân loại dữ liệu

- Ảnh sản phẩm mới được đọc nhiều nhưng ảnh cũ có thể bất ngờ được xem lại: **Autoclass** đáng khảo sát.
- File báo cáo kế toán phải giữ đúng 7 năm và xóa theo chính sách: dùng **retention** cộng **Lifecycle Delete**, không dựa vào Autoclass.
- Backup chắc chắn không cần đọc trong 12 tháng, có thời gian lưu chuẩn: **storage class tĩnh + lifecycle** có thể tối ưu hơn management fee của Autoclass.
- File tạm sinh hàng ngày có tuổi cố định 14 ngày: **Lifecycle Delete theo prefix/age**, không cần Autoclass.
- Object vừa có access pattern không chắc chắn vừa phải hết hạn: **Autoclass + Delete lifecycle** (không dùng SetStorageClass/matchesStorageClass).

## 3. Autoclass hoạt động như thế nào?

**Autoclass** là cấu hình ở **bucket**, theo dõi hoạt động đọc **dữ liệu** từng object. Khi bật, Google Cloud tự chọn class của object theo thời gian không truy cập; khi dữ liệu được đọc trở lại, object có thể chuyển lên **Standard**.

Các nguyên tắc quan trọng:

1. **Object mới đều bắt đầu ở Standard**, kể cả khi request upload cố chỉ định một class khác.
2. **Default storage class của bucket phải là Standard** khi Autoclass bật; yêu cầu đổi default class sang loại khác sẽ thất bại.
3. Object **nhỏ hơn 128 KiB** được giữ ở Standard, **không** xuống lớp lạnh; ngưỡng xét kích thước **dữ liệu object**, không cộng metadata.
4. Object **ít nhất 128 KiB** có thể xuống Nearline/Coldline/Archive theo thời gian không đọc.
5. Truy cập **dữ liệu** bằng phương thức được hỗ trợ có thể đưa object về Standard; thao tác **chỉ xem/sửa metadata** không làm nóng dữ liệu.
6. Các lần chuyển lớp là **bất đồng bộ**; không được trông đợi đúng giây object đủ điều kiện thì metadata class đã đổi.
7. **Soft-deleted objects** không tiếp tục được Autoclass đổi storage class cho tới khi hết giai đoạn giữ bản đã xóa; khôi phục soft-deleted object tạo object ở Standard.

### 3.1. Terminal storage class là gì?

**Terminal storage class** là class lạnh nhất mà Autoclass được phép chuyển object đến khi lâu không được đọc.

- **NEARLINE:** là **mặc định**. Object không được đọc 30 ngày có thể chuyển từ Standard xuống Nearline; không đi xuống Coldline/Archive.
- **ARCHIVE:** lựa chọn cho phép object đi từ Standard → Nearline → Coldline → Archive, nếu tiếp tục không được đọc đủ thời gian.

**Không có lựa chọn terminal `COLDLINE`** trong thiết lập Autoclass hiện tại; chỉ có `NEARLINE` hoặc `ARCHIVE`. Nếu cần lịch riêng như “Coldline từ ngày thứ 180, không Archive”, dùng Lifecycle Management trên bucket **không bật Autoclass** hoặc chia bucket.

### 3.2. Timeline khi terminal là NEARLINE

~~~text
Object >= 128 KiB được upload / dữ liệu vừa được đọc
      |
      v
STANDARD
      |
      | 30 ngày không được đọc
      v
NEARLINE <---- terminal, giữ ở đây cho tới lần đọc dữ liệu
      |
      | GET dữ liệu object thành công
      v
STANDARD, bắt đầu chu kỳ 30 ngày mới
~~~

Ví dụ một file `images/products/seasonal.jpg`:

- Ngày 0: upload ở Standard.
- Không có truy cập dữ liệu 30 ngày: đủ điều kiện chuyển Nearline.
- Ngày 45: ứng dụng GET nội dung file: object được đưa về Standard.
- Nếu không được đọc thêm 30 ngày: lại đủ điều kiện chuyển Nearline.

Số ngày là **ngưỡng đủ điều kiện**, không phải lịch chạy chính xác từng phút. Metadata được xem trong Console không nhất thiết làm “reset” lịch không đọc.

### 3.3. Timeline khi terminal là ARCHIVE

~~~mermaid
flowchart LR
    STD["Standard\nNgay sau upload/GET"] -->|"Không đọc 30 ngày"| NEAR["Nearline"]
    NEAR -->|"Không đọc đến ngày 90"| COLD["Coldline"]
    COLD -->|"Không đọc đến ngày 365"| ARCH["Archive"]
    NEAR -. "GET dữ liệu" .-> STD
    COLD -. "GET dữ liệu" .-> STD
    ARCH -. "GET dữ liệu" .-> STD
~~~

| Mốc không được đọc | Class mục tiêu nếu đủ điều kiện | Ghi chú |
| --- | --- | --- |
| Dưới 30 ngày | Standard | Object mới hoặc vừa được đọc |
| Từ 30 ngày | Nearline | Bước đầu tiên |
| Từ 90 ngày | Coldline | Tổng thời gian không đọc từ lúc bắt đầu chu kỳ |
| Từ 365 ngày | Archive | Chỉ khi terminal=ARCHIVE |

**Không cộng các mốc thành 30+90+365 ngày.** Mốc 90 ngày đã bao gồm 30 ngày Standard và 60 ngày Nearline; mốc 365 ngày bao gồm 30 Standard + 60 Nearline + 275 Coldline.

### 3.4. Điều gì được tính là truy cập dữ liệu?

Theo Google Cloud, timestamp lần đọc cuối dùng trong quyết định Autoclass được cập nhật khi object được truy cập bằng **GET object** theo ngữ nghĩa được hỗ trợ. Các thao tác như **COPY** hoặc **REWRITE**, và việc đọc/sửa metadata, không cập nhật timestamp theo cùng cách.

Hệ quả:

- Một batch job thường xuyên **GET toàn bộ ảnh** để scan, training hoặc phân tích có thể giữ phần lớn dữ liệu ở Standard → Autoclass ít tiết kiệm.
- Một quy trình chỉ **liệt kê/đọc metadata** không nhất thiết làm object nóng.
- Di chuyển hoặc copy đối tượng trong pipeline không nên được dùng làm thí nghiệm giả định chắc chắn sẽ reset last access.
- Với Cloud Storage FUSE, CDN cache và các proxy, hãy đo **GET thực sự tới Cloud Storage**; cache hit ở tầng khác không nhất thiết là GET đến object gốc.

Để hiểu chi phí, không chỉ nhìn tần suất người dùng mở ứng dụng; cần biết **luồng dữ liệu nào chạm tới object**.

### 3.5. Kích thước object và biểu đồ loại trừ

| Object size | Autoclass quản lý chuyển xuống class lạnh? | Giải thích |
| --- | --- | --- |
| 16 KiB | Không | Nhỏ hơn 128 KiB, giữ Standard |
| 127 KiB | Không | Nhỏ hơn 128 KiB |
| 128 KiB | Có | Đạt ngưỡng |
| 4 MiB | Có | Chuyển theo thời gian GET |
| 5 GiB | Có | Cần đánh giá access/cost |

Bucket có **hàng triệu object vài KiB** có thể không hưởng lợi nhiều từ Autoclass: những object này không được chuyển lớp, dù storage của chúng vẫn có chi phí. Lựa chọn khác có thể là **gom batch dữ liệu một cách an toàn**, lifecycle Delete đúng thời hạn hoặc định dạng lưu trữ phù hợp pipeline, nhưng không tự gộp object nếu làm mất khả năng truy cập riêng lẻ.

## 4. Bật Autoclass cho bucket mới và bucket đang sử dụng

### 4.1. Điều kiện IAM và bảo mật

Tài liệu setup hiện hành nêu các permissions:

- `storage.buckets.get`.
- `storage.buckets.update` để thay cấu hình bucket.
- `storage.buckets.list` khi sử dụng Console cần liệt kê bucket.

Vai trò gợi ý là `roles/storage.admin` **trên đúng bucket**, hoặc custom role có quyền nhỏ nhất cần thiết. Không dùng Project Owner/Editor để vượt lỗi permission; một người có quyền đọc object không mặc nhiên có quyền bật Autoclass.

Trước khi bật trên production:

1. Xuất/sao lưu bucket metadata và cấu hình lifecycle đang có.
2. Kiểm tra có `SetStorageClass` hoặc `matchesStorageClass` không; phải xử lý tương thích **trước** khi bật.
3. Ước lượng **one-time enablement charge** và tác động lên tất cả object cũ.
4. Kiểm tra retention/soft delete/versioning, quy tắc mã hóa, audit.
5. Đánh giá các pipeline thường xuyên GET dữ liệu, kể cả backup scan hoặc DLP.
6. Chuẩn bị báo cáo baseline chi phí và số byte theo class.

### 4.2. Console cho bucket mới

1. Mở [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser).
2. Chọn **Create bucket** trong project được phép và nhập tên bucket duy nhất toàn cục.
3. Chọn bucket location phù hợp residency/latency.
4. Ở **Default storage class**, chọn **Autoclass** theo giao diện hiện hành.
5. Chọn **included classes/terminal class**: Nearline mặc định hoặc Archive.
6. Đặt **Uniform bucket-level access**, **Public access prevention**, soft delete, encryption và retention theo chính sách.
7. Kiểm tra cấu hình, tạo bucket.
8. Vào tab **Configuration** xem trạng thái **Managed with Autoclass** và included classes.

Khi mới tạo bucket, chưa có object nên không phát sinh enablement charge áp trên dữ liệu cũ như trường hợp bật cho bucket đã có dữ liệu; vẫn có chi phí object và quản lý Autoclass trong giai đoạn sử dụng.

### 4.3. CLI: đọc cấu hình rồi mới thay đổi

Các lệnh chỉ đọc:

~~~bash
gcloud config get-value project

gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(name,location,storageClass,autoclass,lifecycle,softDeletePolicy,versioning)"

gcloud storage ls gs://BUCKET_NAME/
~~~

Để bật Autoclass trên bucket test đã được phê duyệt:

~~~bash
# THAY ĐỔI bucket: kiểm tra chi phí và lifecycle trước khi chạy
gcloud storage buckets update gs://BUCKET_NAME \
  --default-storage-class=STANDARD \
  --enable-autoclass \
  --autoclass-terminal-storage-class=NEARLINE
~~~

Nếu muốn cho phép Archive ở bucket **thử nghiệm** (sau khi cân nhắc chi phí), dùng:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --enable-autoclass \
  --autoclass-terminal-storage-class=ARCHIVE
~~~

Tùy phiên bản SDK, khi bật Autoclass trên bucket có default class khác Standard, cần **đặt `--default-storage-class=STANDARD` trong cùng thao tác**. Kiểm tra `gcloud storage buckets update --help` và trạng thái thực tế sau update.

Xem trạng thái:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(autoclass)"
~~~

**Lưu ý quyền/thay đổi:** Lệnh `update` tác động bucket thật và có thể thay lớp đối tượng cũ. Không chạy với bucket dùng chung hoặc bucket của production mà chưa có đánh giá tác động, rollback và chấp thuận.

### 4.4. Bật Autoclass cho bucket có dữ liệu cũ

Khi **enable Autoclass trên bucket hiện có**:

- Các object không ở trạng thái soft-deleted được đưa về **Standard**, dù metadata class có thể chưa hiển thị Standard ngay.
- Object vốn đã ở Standard cũng được xem là bắt đầu lại **chu kỳ 30 ngày** không đọc.
- Có **one-time enablement charge**, có thể gồm phí retrieval và early deletion của dữ liệu cũ cùng Class A operations tùy object/class.
- Cấu hình có thể mất tới **một ngày** để thay đổi có hiệu lực; một số tác vụ vẫn hoạt động theo thiết lập cũ trong khoảng này.

Ví dụ: Bucket chứa 50 TB Archive với hàng triệu object ít đọc có thể bị tính **chi phí đáng kể** khi bật Autoclass, vì nó phải chuyển đối tượng trở về Standard để bắt đầu quản lý. Không coi “bật Autoclass để tiết kiệm ngay” là một thao tác miễn phí.

### 4.5. Đổi terminal class và tắt Autoclass

- Nếu đổi `ARCHIVE → NEARLINE`, object đang Coldline/Archive có thể được chuyển lên Nearline theo quy tắc.
- Nếu đổi `NEARLINE → ARCHIVE`, object hiện Nearline được xem như mới chuyển Nearline và cần thêm **60 ngày không đọc** trước khi đủ điều kiện Coldline.
- Khi **tắt Autoclass**, mỗi object **giữ storage class hiện tại**. Nó không tự trở về Standard.
- Sau khi tắt, cần **chờ ít nhất một ngày** trước khi bật lại Autoclass cho cùng bucket.
- Thay đổi cấu hình có thể mất tới một ngày để hoàn tất.

Ví dụ lệnh tắt (tác động thật):

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --no-enable-autoclass
~~~

**Nguy cơ:** Tắt Autoclass khi nhiều object còn ở Archive khiến các lần đọc sau chịu pricing thông thường của Archive (retrieval/minimum duration tùy tình huống), không còn ưu đãi Autoclass. Hãy tính chi phí chuyển đổi và chính sách lớp thủ công trước khi tắt.

## 5. Chi phí Autoclass: những khoản không nên bỏ sót

Autoclass tối ưu storage cost nhưng **không miễn phí**. Các dòng chi phí nên được tính riêng:

| Thành phần | Khi nào có | Cách hiểu |
| --- | --- | --- |
| Storage at rest | Object đang ở từng storage class | Giá theo location/class và Autoclass-specific SKUs |
| **Autoclass management fee** | Object đủ điều kiện (ít nhất 128 KiB) trong bucket có Autoclass | Tính theo số object và thời gian được quản lý |
| **One-time enablement charge** | Bật trên bucket có objects hiện hữu | Có thể bao gồm retrieval, early deletion và Class A |
| GET/PUT/LIST và operations khác | Ứng dụng gọi Cloud Storage | Theo mức operation Standard tương ứng trong Autoclass |
| Transition xuống lớp lạnh | Autoclass chuyển tự động | Không có transition operation charge |
| Nearline → Standard do đọc | Khi Autoclass làm nóng object | Không có Class A transition charge cho nhánh này |
| Coldline/Archive → Standard hoặc Nearline | Khi Autoclass chuyển lên lớp ấm | Có Class A transition operation theo tài liệu |
| Data transfer/egress | Truy cập từ region/mạng thích hợp | Vẫn có phí mạng theo bảng giá |
| Soft delete, versioning, replication | Nếu bật | Tăng lượng bytes/objects và phí tương ứng |

### 5.1. Autoclass và retrieval/early deletion fees

Trong **quá trình sử dụng Autoclass**:

- Google Cloud **không thu retrieval fees** theo mô hình thông thường của class lạnh, **ngoại trừ phần có thể nằm trong one-time enablement charge**.
- Google Cloud **không thu early deletion fees** của class lạnh trong sử dụng Autoclass, **ngoại trừ enablement charge**.
- Các operations được tính theo mức Standard operation, nhưng một số chuyển lớp từ Coldline/Archive có thêm Class A transition charge.
- **Không nhầm** “không retrieval fee” với “đọc hoàn toàn miễn phí”: request, class transitions được tính phí, network egress và các dịch vụ gọi dữ liệu vẫn có thể phát sinh tiền.

### 5.2. Đánh giá break-even thay vì dựa mỗi giá/GB

Một công thức mô hình hóa:

~~~text
TCO_Autoclass ≈
    SUM(bytes-at-rest theo class/location × giá class tương ứng)
  + management fee theo object-thời-gian đủ điều kiện
  + enablement charge (nếu mới bật trên dữ liệu cũ)
  + operations / transition operations áp dụng
  + network egress / replication / soft-delete
  + vận hành

TCO_Lifecycle ≈
    SUM(bytes-at-rest theo class/location × giá class)
  + Class A operations do SetStorageClass
  + retrieval/early-deletion phí theo class và cách dùng
  + operation / network / soft-delete / replication
  + quản trị lifecycle rules và kiểm thử
~~~

Ví dụ một bucket có **1 triệu object nhỏ, mỗi object 32 KiB** và được đọc hằng ngày: đa số object không được Autoclass chuyển xuống lớp lạnh, vì vậy khó kỳ vọng tiết kiệm lớn từ Autoclass. Ngược lại, một bucket chứa object lớn có chu kỳ nóng/lạnh không biết trước có thể giảm storage cost nhờ Autoclass.

**Không hard-code một con số tiết kiệm như “30%”** cho mọi workload. Hãy dựng bảng TCO bằng giá Cloud Storage hiện hành của location thật, số lượng object theo kích thước, tần suất GET, dữ liệu egress và thời gian giữ.

### 5.3. Biến động chi phí khi dùng class lạnh thủ công

Nếu không dùng Autoclass, Nearline, Coldline và Archive có các **minimum storage durations** lần lượt **30, 90 và 365 ngày**. Việc xóa hoặc thay thế/di chuyển object sớm có thể tạo **early deletion charge**. Với Object Lifecycle Management, việc **SetStorageClass không bị tính early deletion charge** do chuyển lớp theo rule, nhưng có **Class A operation charge**. Khi rule Delete làm object rời lớp lạnh sớm theo cách tính phí thực tế, early deletion có thể áp dụng. Xem chi tiết phần Lifecycle ở dưới.

## 6. Object Lifecycle Management: action + condition

**Object Lifecycle Management** cho phép đặt **một tập rules trên bucket**. Mỗi rule có:

- **Action:** việc Cloud Storage sẽ làm đối với object phù hợp.
- **Conditions:** tiêu chí phải được thỏa mãn để action chạy.

Ví dụ policy:

~~~text
Khi object trong prefix temp/ đủ 30 ngày kể từ lúc tạo:
    → Delete

Khi object báo cáo đủ 90 ngày kể từ lúc tạo:
    → SetStorageClass COLDLINE  (chỉ bucket KHÔNG bật Autoclass)

Khi một noncurrent version đã tồn tại 60 ngày:
    → Delete phiên bản đó
~~~

### 6.1. Nguyên tắc boolean và mức ưu tiên

- **Một rule:** tất cả conditions trong rule phải đúng (**AND**).
- **Nhiều rule cùng loại action:** action có thể chạy nếu thỏa một rule phù hợp (**OR** giữa các rule).
- Nếu nhiều rules khác action cùng khớp một object, Cloud Storage **chỉ thực hiện một action** theo thứ tự ưu tiên, ví dụ **Delete ưu tiên hơn SetStorageClass**.
- Khi nhiều SetStorageClass rules cùng khớp, rule chuyển đến class có giá lưu trữ at-rest thấp nhất được ưu tiên theo tài liệu.
- Hành động **không xảy ra chính xác vào thời điểm điều kiện vừa đúng**. Cloud Storage quét/thi hành **bất đồng bộ**.

~~~mermaid
flowchart TD
    OBJ["Object và metadata"] --> MATCH{"Một hoặc nhiều rules khớp?"}
    MATCH -- "Không" --> STAY["Giữ nguyên"]
    MATCH -- "Có" --> CONFLICT{"Có nhiều actions xung đột?"}
    CONFLICT -- "Có Delete" --> DEL["Delete khi retention/hold cho phép"]
    CONFLICT -- "Chỉ SetStorageClass" --> TRANS["Chọn lớp theo quy tắc ưu tiên"]
    CONFLICT -- "Một action" --> ACT["Thực hiện action tương ứng"]
    DEL --> PROTECT["Soft delete / Versioning có thể giữ lại dữ liệu"]
~~~

### 6.2. Ba lifecycle actions

| Action | Công dụng | Điều kiện đặc biệt |
| --- | --- | --- |
| **Delete** | Xóa object khi hết hạn; có thể tác động live/noncurrent versions | Bị chặn khi retention policy/object hold còn hiệu lực |
| **SetStorageClass** | Chuyển object sang class lạnh hơn được hỗ trợ | **Không dùng khi Autoclass enabled**; có phí Class A per transition |
| **AbortIncompleteMultipartUpload** | Bỏ các lần XML API multipart upload chưa hoàn tất | Chỉ hỗ trợ `age`, `matchesPrefix` và `matchesSuffix` làm điều kiện |

Object Lifecycle Management **không hỗ trợ action tùy ý** như gửi email, nén dữ liệu, gọi Cloud Run hoặc move object sang bucket khác. Nếu cần workflow phức tạp, dùng event-driven processing/Cloud Run/Workflows hoặc Storage Batch Operations theo điều kiện được hỗ trợ; vẫn cần IAM và kiểm soát lỗi.

### 6.3. Những lifecycle conditions phổ biến

| Condition trong JSON | Cách khớp | Ví dụ |
| --- | --- | --- |
| `age` | Số ngày từ **thời điểm object được tạo/upload hoàn tất** | `"age": 30` |
| `createdBefore` | Object tạo trước ngày UTC chỉ định | `"createdBefore": "2026-01-01"` |
| `isLive` | Có phải live generation hiện tại không | `"isLive": false` |
| `daysSinceNoncurrentTime` | Số ngày sau khi generation trở thành noncurrent | `"daysSinceNoncurrentTime": 60` |
| `numNewerVersions` | Có ít nhất N generation mới hơn | `"numNewerVersions": 3` |
| `matchesPrefix` | Object name bắt đầu bằng một trong các prefix, phân biệt hoa thường | `"matchesPrefix": ["temp/"]` |
| `matchesSuffix` | Object name kết thúc bằng một trong các hậu tố | `"matchesSuffix": [".log", ".tmp"]` |
| `matchesStorageClass` | Object đang thuộc một trong class liệt kê | **Không dùng với Autoclass** |
| `daysSinceCustomTime` | Số ngày từ metadata `Custom-Time` | Dùng khi ứng dụng đặt thời điểm nghiệp vụ |
| `customTimeBefore` | Custom-Time trước một ngày được chỉ định | Lưu dữ liệu theo mốc nghiệp vụ |
| `sizeAboveBytes`/`sizeBelowBytes` | Lọc theo kích thước bytes | Chặn chuyển lớp cho quá nhiều object nhỏ |

**Hai loại “tuổi” khác nhau:**

- `age` dùng **object creation time**, **không** tính từ lần GET cuối, **không** tự reset khi chuyển storage class hoặc thành noncurrent.
- `daysSinceNoncurrentTime` tính từ lúc một object generation bị thay thế/xóa và trở thành **noncurrent**, chỉ có ý nghĩa khi có versioning tương ứng.
- `daysSinceCustomTime` dựa vào **Custom-Time metadata** do ứng dụng thiết lập.
- **Autoclass** lại dựa vào **hoạt động đọc dữ liệu**, không phải ba điều kiện tuổi trên.

### 6.4. Prefix là tên object, không phải đường dẫn đầy đủ

Ví dụ object:

~~~text
gs://company-audit-data/temp/reports/job-123.csv
~~~

Để khớp prefix, khai báo:

~~~json
"matchesPrefix": ["temp/reports/"]
~~~

Không khai báo `"gs://company-audit-data/temp/reports/"` hoặc thêm dấu `/` đứng trước object name. So khớp prefix **phân biệt chữ hoa/chữ thường**, vì vậy `Temp/` và `temp/` là hai giá trị khác nhau.

## 7. JSON lifecycle cơ bản và tương thích với Autoclass

### 7.1. Rule Delete file tạm sau 30 ngày

Đây là rule tương thích với **cả bucket Standard và bucket có Autoclass**:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"],
        "isLive": true
      }
    }
  ]
}
~~~

**Diễn giải:** Chỉ live objects có tên bắt đầu bằng `temp/` và đã được tạo **ít nhất 30 ngày** mới đủ điều kiện Delete. Không cần xét class, vì mục tiêu là xóa hết hạn **dù Autoclass đã chuyển lớp hay chưa**.

**Cảnh báo versioning:** Nếu Object Versioning bật, xóa live generation có thể làm generation đó trở thành noncurrent. Rule chỉ có `isLive:true` **không xóa noncurrent generations**, do đó tổng storage có thể tiếp tục tăng. Cần rule riêng xóa các bản cũ theo thời hạn có thỏa thuận.

### 7.2. Kết hợp Delete và dọn noncurrent generations

Nếu có Object Versioning và muốn:

- Live object trong `temp/` được xóa sau 30 ngày tuổi.
- Noncurrent generation ở `temp/` được xóa sau 14 ngày kể từ lúc không còn là live.

Có thể sử dụng:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"],
        "isLive": true
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "daysSinceNoncurrentTime": 14,
        "matchesPrefix": ["temp/"],
        "isLive": false
      }
    }
  ]
}
~~~

**Ràng buộc vận hành:** Các ngưỡng 30/14 ngày chỉ minh họa cho **dữ liệu lab không quan trọng**. Với báo cáo/backup, cần thời hạn lưu theo pháp lý, SLA khôi phục và chính sách backup, không xóa phiên bản cũ chỉ vì muốn giảm chi phí.

### 7.3. Rule chuyển class theo tuổi — chỉ dành cho bucket KHÔNG Autoclass

Khi bạn biết báo cáo không cần đọc thường xuyên sau 90 ngày, có thể chuyển lớp tự động:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": ["reports/monthly/"],
        "sizeAboveBytes": 131072
      }
    }
  ]
}
~~~

Dùng cho **bucket không có Autoclass**. Khi bucket đã bật Autoclass, rule này **không hợp lệ**. Cần thêm quy tắc Delete riêng khi có yêu cầu xóa, chú ý retention và early deletion.

**Vì sao có `sizeAboveBytes`?** Chuyển storage class bằng lifecycle tạo **Class A operation** trên mỗi object. Với hàng triệu object nhỏ, phí operations có thể lớn hơn khoản tiết kiệm từ giá lưu trữ. Điều kiện này chỉ là ví dụ lọc object lớn hơn 128 KiB; giá trị ngưỡng cần tính theo cost model thực tế.

### 7.4. Rule dọn multipart upload chưa hoàn tất

~~~json
{
  "rule": [
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7,
        "matchesPrefix": ["uploads/"]
      }
    }
  ]
}
~~~

Rule này chỉ áp dụng đến những **XML API multipart uploads chưa hoàn thành**, không phải “xóa tất cả object ở uploads/ sau 7 ngày”. Không dùng các conditions khác ngoài `age`, `matchesPrefix` và `matchesSuffix` cho action này.

### 7.5. Bucket có Autoclass + Delete + Abort

Một cấu hình **tương thích**:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 60,
        "matchesPrefix": ["temporary/"]
      }
    },
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7
      }
    }
  ]
}
~~~

Không có `SetStorageClass` hoặc `matchesStorageClass`, nên có thể được dùng cùng Autoclass **nếu không xung đột các chính sách khác**. Rule Delete vẫn chịu ràng buộc Object Versioning, soft delete, object holds và retention.

### 7.6. Cấu hình KHÔNG hợp lệ khi bật Autoclass

Hai ví dụ **không thể dùng chung với Autoclass**:

~~~json
{
  "rule": [
    {
      "action": { "type": "SetStorageClass", "storageClass": "ARCHIVE" },
      "condition": { "age": 365 }
    }
  ]
}
~~~

Hoặc:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 365,
        "matchesStorageClass": ["NEARLINE"]
      }
    }
  ]
}
~~~

**Trường hợp thứ hai dễ bị bỏ sót:** Dù action là Delete, condition `matchesStorageClass` **vẫn bị cấm** với Autoclass. Nếu mục tiêu là xóa theo hạn, hãy dùng `age`, `matchesPrefix`, `isLive` hoặc Custom-Time phù hợp, không dựa storage class đang được Autoclass quản lý.

## 8. Thứ tự ưu tiên rules và hiện tượng khó hiểu

### 8.1. Multiple actions cùng khớp

Một bucket Standard, không bật Autoclass, có hai rules:

~~~json
{
  "rule": [
    {
      "action": { "type": "SetStorageClass", "storageClass": "COLDLINE" },
      "condition": { "age": 60 }
    },
    {
      "action": { "type": "Delete" },
      "condition": { "age": 60 }
    }
  ]
}
~~~

Khi object đủ 60 ngày, **Delete có ưu tiên cao hơn SetStorageClass**. Không kỳ vọng object sẽ được chuyển lớp rồi sau đó xóa vào cùng một lượt. Muốn lưu ít nhất đến 180 ngày, dùng rule SetStorageClass age=60 và Delete age=180, sau khi xét class/minimum duration.

### 8.2. Mọi conditions trong một rule là AND

Ví dụ:

~~~json
"condition": {
  "age": 90,
  "matchesPrefix": ["reports/"],
  "isLive": false
}
~~~

Nghĩa là object phải **ít nhất 90 ngày tuổi kể từ creation**, **bắt đầu bằng reports/** và đang là **noncurrent version**. Nếu bạn muốn “90 ngày từ khi bị ghi đè”, thay `age` bằng `daysSinceNoncurrentTime`.

### 8.3. Ngày đủ điều kiện không phải ngày thao tác chắc chắn diễn ra

Object tạo lúc 10:00 UTC ngày 01/01; với `age=30`, từ 10:00 UTC ngày 31/01 object đủ điều kiện. Nhưng Cloud Storage thực hiện Lifecycle **asynchronously**. Dữ liệu có thể còn xuất hiện một thời gian sau mốc này.

**Không lập kế hoạch nghiệp vụ kiểu “object chắc chắn biến mất đúng 00:00 ngày hết hạn”.** Nếu ứng dụng cần xóa chính xác theo deadline, phải có workflow chủ động và kiểm tra tuân thủ; lifecycle là công cụ background hữu ích nhưng không cung cấp SLA “xóa đến đúng giây”.

### 8.4. Sửa rule không loại bỏ ngay tác động của rule cũ

Sau khi cập nhật lifecycle configuration, Google Cloud có thể tiếp tục chạy theo rule cũ trong tối đa khoảng **24 giờ**. Ví dụ đổi `age:10` lên `age:20`, object 11 ngày tuổi **vẫn có thể bị xóa** trong giai đoạn lan truyền cấu hình. Vì vậy:

- Không đặt rule xóa quá mạnh rồi “sửa nhanh nếu thấy sai”.
- Phải kiểm tra trên bucket lab hoặc prefix nhỏ trước.
- Không xem việc xóa/cập nhật rule là rollback bảo đảm giữ lại mọi object.
- Bật soft delete/versioning hoặc snapshot/backup phù hợp với RPO để giảm rủi ro.

## 9. Triển khai Object Lifecycle Management qua Console và CLI

### 9.1. Quyền và khâu preflight

Các quyền thường cần: `storage.buckets.get` và `storage.buckets.update` (Console thường cần thêm `storage.buckets.list`). `roles/storage.admin` trên bucket chứa các quyền này, hoặc có thể dùng custom role.

Trước khi cập nhật:

1. Xem bucket/project/location và xác nhận **đúng bucket thuộc quyền sở hữu**.
2. Đọc lifecycle rules đang có, soft delete/versioning/retention/hold.
3. Nếu dùng Autoclass, kiểm tra **không có** `SetStorageClass`/`matchesStorageClass`.
4. Chuẩn bị JSON chứa **tất cả rules** muốn giữ, không chỉ rule mới.
5. Được phê duyệt action Delete và tuổi xóa theo data owner.
6. Kiểm tra chi phí Class A operations và khả năng phục hồi.

### 9.2. Console

1. Mở [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser).
2. Chọn bucket rồi tới tab **Lifecycle**.
3. Chọn **Add rule**, chọn action (Delete, SetStorageClass, Abort incomplete multipart upload nếu giao diện hỗ trợ).
4. Định nghĩa conditions: age, prefix, live version hoặc trường thích hợp.
5. Kiểm tra toàn bộ danh sách rules, thứ tự ưu tiên/khả năng xung đột.
6. Lưu và **đọc lại** cấu hình.
7. Theo dõi object/chi phí. Đừng kết luận sai ngay nếu background process chưa chạy.

Để tránh xóa nhầm, chỉ thử với **bucket lab** chứa dữ liệu không quan trọng hoặc prefix thử nghiệm có owner xác nhận.

### 9.3. CLI chỉ đọc hiện trạng

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(name,location,autoclass,lifecycle,softDeletePolicy,retentionPolicy,versioning)"

# Liệt kê object để xác định prefix (chỉ đọc)
gcloud storage ls gs://BUCKET_NAME/temp/

# Xem metadata của một object cụ thể, không tải dữ liệu
gcloud storage objects describe gs://BUCKET_NAME/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated,updated)"
~~~

Dù lệnh đọc metadata không làm Autoclass chuyển lớp, lệnh truy cập **dữ liệu** (ví dụ download/cat) có thể khiến object Autoclass chuyển về Standard. Trước khi làm bài thí nghiệm với class transitions, đừng vô tình đọc nội dung khi mục tiêu chỉ là quan sát.

### 9.4. CLI áp dụng lifecycle JSON

Sau khi **bạn tự chuẩn bị file JSON ngoài bài học** (ví dụ `lifecycle.json` chứa đầy đủ rules), dùng:

~~~bash
# THAY ĐỔI bucket, không chạy trên production khi chưa review
gcloud storage buckets update gs://BUCKET_NAME \
  --lifecycle-file=lifecycle.json
~~~

**Cực kỳ quan trọng:** Lệnh này **thay thế toàn bộ lifecycle configuration đang có**. Nếu bucket đã có rules khác, file JSON phải bao gồm cả rules cũ cần giữ. Đừng dùng một file chỉ có 1 rule mới nếu ý định là “append” rule.

Nếu cần hủy toàn bộ lifecycle rules (tác động thật, không dùng làm rollback mặc định):

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --clear-lifecycle
~~~

Hủy rule xóa **không khôi phục** object đã bị xóa và **không bảo đảm ngừng ngay** những tác vụ đã lên lịch trong cửa sổ propagation.

### 9.5. JSON mẫu theo kịch bản doanh nghiệp

Bucket `gs://order-artifacts-lab` không bật Autoclass, cần:

- `reports/` chuyển Coldline khi ít nhất 90 ngày tuổi và đủ lớn.
- `temp/` xóa sau 30 ngày.
- XML multipart uploads còn dang dở sau 7 ngày thì hủy.

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": ["reports/"],
        "sizeAboveBytes": 131072
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"]
      }
    },
    {
      "action": { "type": "AbortIncompleteMultipartUpload" },
      "condition": {
        "age": 7
      }
    }
  ]
}
~~~

**Không dùng JSON này trên bucket có Autoclass.** Bỏ rule `SetStorageClass`, giữ Delete/Abort nếu muốn dùng Autoclass + lifecycle cùng lúc.

## 10. Tương tác với Soft Delete, Versioning, Retention và Object Holds

Các tính năng bảo vệ dữ liệu quyết định **Delete có thể thực sự khiến bytes biến mất khi nào**.

### 10.1. Soft delete

Soft delete có thể giữ object sau khi bị xóa trong một **soft delete retention duration** (thường mặc định **7 ngày** trên bucket mới, nhưng phải đọc cấu hình thực tế). Trong thời gian này có thể restore nếu còn đủ quyền và chưa hết hạn.

- Lifecycle `Delete` có thể đưa object vào trạng thái **soft-deleted**.
- Lifecycle rules **không áp dụng** cho soft-deleted objects: không chuyển lớp, không xóa vĩnh viễn bằng rule.
- Autoclass cũng **không chuyển lớp** những soft-deleted objects; **management fee của Autoclass không tính trên objects ở trạng thái soft-deleted**.
- Khi restore một soft-deleted object trong bucket Autoclass, object được phục hồi ở **Standard**.

Điều này lý giải vì sao object bị Delete nhưng billing vẫn còn phí lưu trữ cho đến khi soft delete retention hết hạn. **Không tắt soft delete chỉ để làm số liệu giảm ngay** nếu dữ liệu cần khả năng phục hồi.

### 10.2. Object Versioning

Khi Object Versioning bật:

- Một live generation bị ghi đè hoặc xóa có thể trở thành **noncurrent generation**.
- Nếu rule chỉ `isLive:true`, các phiên bản cũ có thể **tiếp tục tồn tại** và phát sinh storage cost.
- Có thể dùng `isLive:false` và `daysSinceNoncurrentTime` để quản lý tuổi của noncurrent generations.
- Nếu soft delete đồng thời bật, xóa noncurrent version có thể đưa bản đó thành soft-deleted trước khi bị xóa vĩnh viễn.

Một chính sách “chỉ giữ 3 phiên bản mới nhất” nên dùng conditions như `numNewerVersions` và `isLive:false` theo thiết kế, nhưng phải kiểm tra điều kiện retention và khả năng rollback từng generation.

### 10.3. Retention policy / Object holds

**Bucket retention policy**, **Object Retention Lock** và **object holds** không phải lifecycle rule. Chúng bảo vệ dữ liệu khỏi xóa trước thời hạn hoặc khi hold còn hiệu lực.

- Nếu object còn hold hoặc chưa đáp ứng retention, lifecycle `Delete` **không xóa được** dù tuổi đã đạt ngưỡng.
- Khi điều kiện hold/retention hết hiệu lực, nếu vẫn khớp Delete rule, hệ thống có thể xóa sau đó.
- Autoclass quản lý storage class **không thay đổi ràng buộc bảo lưu**.
- Khi bucket bị **Bucket Lock**, retention policy có thể không thể rút ngắn/gỡ; không tạo lock trong bài lab.
- Với quy định tuân thủ như lưu 7 năm, lifecycle Delete sau 7 năm chỉ thực hiện được khi retention và các holds cho phép; đối chiếu pháp lý và governance trước khi triển khai.

### 10.4. Khác biệt giữa retention và lifecycle delete

| Cơ chế | Mục đích | Khi object đủ điều kiện |
| --- | --- | --- |
| Retention | **Ngăn** xóa trước hạn | Sau khi hết hạn, **có thể xóa** nếu có tác vụ/rule |
| Lifecycle Delete | **Yêu cầu** xóa khi đạt điều kiện | Sẽ xóa **bất đồng bộ**, trừ khi retention/hold chặn |
| Soft delete | **Cho phục hồi sau xóa** trong cửa sổ được cấu hình | Hết cửa sổ thì object bị xóa vĩnh viễn |
| Versioning | **Giữ bản cũ** khi ghi đè/xóa live version | Noncurrent sống cho tới khi bị xóa theo policy |

**Đặt retention 365 ngày không có nghĩa object sẽ tự bị xóa ở ngày thứ 366.** Muốn có TTL tự động, cần lifecycle Delete hoặc quy trình xóa riêng.

## 11. Quy trình lựa chọn Autoclass hay Lifecycle cho một workload

Thay vì hỏi “Autoclass có giảm giá không?”, hãy mô tả **hành vi và hợp đồng dữ liệu** trước:

1. **Dữ liệu là gì?** Ảnh người dùng, log, backup, báo cáo, ML dataset, artifact, bản ghi tuân thủ?
2. **Kích thước object:** Có bao nhiêu object nhỏ hơn 128 KiB? Tổng số object và tổng bytes theo size bucket là bao nhiêu?
3. **Tần suất đọc:** Dự đoán được hay biến thiên khó lường? Có job scan định kỳ, lifecycle batch hoặc compliance reads không?
4. **Thời gian giữ:** Bao lâu là bắt buộc theo pháp lý? Khi nào được phép xóa? Có soft delete/versioning/hold?
5. **Khả năng lấy lại:** Đọc object cũ có phổ biến không? Có yêu cầu RTO/RPO hoặc chi phí request/egress lớn không?
6. **Số lượng thao tác:** PUT, GET, LIST, COPY/REWRITE, số transitions nếu dùng lifecycle?
7. **Thời gian/bảo mật vùng lưu:** Location, encryption, IAM, access policies và audit.
8. **Chi phí định lượng:** Giá storage class theo location, management/enablement, Class A, retrieval, early deletion, egress và soft delete.

~~~mermaid
flowchart TD
  START["Dữ liệu trên Cloud Storage"] --> RET{"Có yêu cầu giữ/xóa theo tuổi hay phiên bản?"}
  RET -- "Có" --> DEL["Thiết kế retention + lifecycle Delete"]
  RET -- "Không" --> ACCESS{"Tần suất đọc có khó dự đoán?"}
  DEL --> ACCESS
  ACCESS -- "Có" --> SIZE{"Đa số bytes nằm trong object >=128 KiB?"}
  SIZE -- "Có" --> AUT["Đánh giá Autoclass + Delete nếu cần"]
  SIZE -- "Không" --> MAN["Đánh giá Standard / quy tắc cụ thể"]
  ACCESS -- "Không" --> CLASS{"Biết rõ thời điểm chuyển class?"}
  CLASS -- "Có" --> LC["Đánh giá lifecycle SetStorageClass\ntrên bucket KHÔNG Autoclass"]
  CLASS -- "Không" --> AUT
  AUT --> COST["Tính TCO, kiểm tra enablement và phản ứng khi GET"]
  MAN --> COST
  LC --> COST
  COST --> VERIFY["Lab + review quyền + kiểm chứng trên billing"]
~~~

### 11.1. Ba câu hỏi quyết định nhanh

**A. Dữ liệu có bị xóa theo hạn không?**

Nếu có, bạn cần **Lifecycle Delete**, kể cả khi Autoclass đang bật. Autoclass không xóa dữ liệu chỉ vì không ai đọc nhiều năm.

**B. Nhóm vận hành có biết object nào “nóng” và object nào “lạnh” từ trước không?**

Nếu đã biết theo prefix hoặc nghiệp vụ (ví dụ `reports/final/` luôn phải giữ 5 năm và ít đọc), một policy đặt class và xóa theo tuổi có thể đơn giản, dễ dự báo chi phí. Nếu ảnh/product data có thể bất ngờ được đọc trở lại, Autoclass là ứng viên tốt.

**C. Bucket đang có dữ liệu lớp lạnh trị giá lớn không?**

Nếu có, **one-time enablement charge** khi chuyển sang Autoclass có thể khiến lợi ích ngắn hạn không đạt. Nên thử với bucket mới hoặc một nhóm dữ liệu tách riêng, không bật Autoclass đại trà trên bucket cũ trước khi tính toán.

## 12. Bốn tình huống áp dụng thực tế

### 12.1. Ảnh và tài liệu người dùng có access pattern khó đoán

**Bối cảnh:** Java API/Cloud Run lưu hóa đơn điện tử, ảnh sản phẩm và tài liệu người dùng. Object thường được đọc nhiều sau khi tạo nhưng thỉnh thoảng có tài liệu cũ được tải lại.

**Phương án:**

- Bucket mới có **Autoclass** nếu phần lớn bytes ở object từ 128 KiB trở lên.
- Terminal `NEARLINE` nếu không muốn chuyển tới Coldline/Archive; cân nhắc `ARCHIVE` nếu có lượng dữ liệu ít đọc trong năm dài.
- Dùng Lifecycle `Delete` cho **temporary uploads**, chứ không xóa ảnh/hóa đơn nếu còn trong retention.
- Nếu có Cloud CDN, so hit ratio và số GET thực đến origin Cloud Storage.
- Đo request cost và Autoclass management fee; có thể bật Cloud Billing budget.

**Nguy cơ:** Một job định kỳ đọc lại nội dung tất cả object cho indexing/DLP hoặc kiểm tra checksum có thể làm dữ liệu nóng liên tục. Hãy xem lịch đọc thực thay vì chỉ giao diện người dùng.

### 12.2. File log phục vụ điều tra sự cố

**Bối cảnh:** Logs xuất thành object `logs/app/2026/11/...`, lưu 90 ngày; phần lớn chỉ đọc khi sự cố.

**Ứng viên:** Bucket Standard hoặc Nearline với **Lifecycle Delete theo `age:90`**. Nếu lượng bytes lớn và access không dự đoán được, Autoclass có thể hợp lý, nhưng cần đánh giá object size và pipeline scan.

**Điểm phải kiểm tra:**

- Logs có dữ liệu nhận diện cá nhân? Có phải dữ liệu audit cần retention dài hơn không?
- Object mới đang rất nhỏ (vài KiB) hay được compact/partition thành tệp lớn hơn?
- Log được xuất từ hệ thống nào, bucket có do một **dịch vụ Google Cloud khác quản lý** không?
- Delete có phù hợp retention/soft delete/versioning và yêu cầu forensics không?

Không tùy tiện cấu hình lifecycle trên bucket do Artifact Registry hoặc dịch vụ khác tự quản lý: xóa object do hệ thống sử dụng có thể làm hỏng artifact/deployment.

### 12.3. Backup và dữ liệu lưu dài hạn có lịch rõ

**Bối cảnh:** Bản sao lưu bất biến của database, định kỳ 1 lần/ngày, phải giữ 365 ngày; chỉ phục hồi khi sự cố.

**Ứng viên:** Lớp storage thích hợp và **Lifecycle Management** theo chính sách lưu/xóa; không nhất thiết bật Autoclass vì pattern biết trước.

**Cần quyết định:**

1. Backup có đủ độc lập nguồn dữ liệu không, có cần backup thứ hai/vùng khác?
2. Có object versioning/soft delete/retention lock theo yêu cầu chống xóa mã độc?
3. Nếu đặt Archive từ đầu, chi phí retrieval/early deletion khi xóa sớm có được chấp nhận?
4. Quy tắc xóa có dùng **ngày tạo** hay **Custom-Time của kỳ backup**?
5. Có kiểm thử restore định kỳ? Việc restore có làm tăng tần suất GET và biến đổi Autoclass behavior không?

**Kết luận:** Autoclass tối ưu chi phí class nhưng **không thay thế backup/DR**. Dữ liệu đang ở Archive vẫn có thể bị xóa nếu IAM/Lifecycle sai và không có retention bảo vệ.

### 12.4. Dữ liệu tạm cho pipeline BigQuery/ML

**Bối cảnh:** Pipeline sinh CSV/Parquet ở `staging/` và `temp/`, tuổi sử dụng dưới 14 ngày; một số job bị lỗi tạo multipart uploads chưa hoàn tất.

**Ứng viên:** Bucket riêng với **Lifecycle Delete age=14 + matchesPrefix**, **AbortIncompleteMultipartUpload age=7**; không cần tối ưu class lạnh nếu toàn bộ dữ liệu được xóa nhanh.

**Nguy cơ:** Job chậm hoặc retry sau 15 ngày có thể không tìm thấy file. Cần xác định TTL theo vòng đời workflow và SLA, không chọn ngưỡng thấp nhất chỉ vì muốn giảm storage cost.

## 13. Tổ chức dữ liệu và phiên bản để lifecycle rules không làm mất dữ liệu

### 13.1. Phân bucket hay phân prefix?

| Phương án | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Một bucket, nhiều prefix** | Ít bucket, dễ triển khai, rules theo tiền tố | Autoclass áp dụng toàn bucket; IAM/retention có thể khó tách; thao tác nhầm tác động nhiều nhóm |
| **Nhiều bucket theo data class** | Có thể áp Autoclass/lifecycle/retention khác nhau; dễ chia owner | Cần quản trị IAM, DNS/URI, quotas và billing rõ ràng |
| **Managed folders / hierarchical namespace** | Tổ chức và quản trị truy cập theo khả năng hỗ trợ | Không thay thế việc xem quy tắc lifecycle và class, cần kiểm tra giới hạn sản phẩm |

**Quy tắc thiết kế:** Nếu hai nhóm dữ liệu có chính sách lưu trữ và tần suất đọc **rất khác nhau**, tách bucket thường giúp tránh một Autoclass policy chung hoặc rule Delete sai phạm vi. Nếu chỉ khác prefix nhưng cùng SLA/retention, có thể dùng bucket chung và lifecycle rules có prefix filter.

### 13.2. Naming convention giúp xóa đúng dữ liệu

Tên object nên có đặc điểm dễ kiểm tra:

~~~text
temporary/session-<id>/<filename>
reports/daily/YYYY/MM/DD/<filename>
reports/monthly/YYYY/MM/<filename>
backups/service/2026-11-19T00-00-00Z/<filename>
legal-hold/case-<id>/<filename>
~~~

**Không dùng một prefix `temp/` để chứa cả dữ liệu tạm và hóa đơn phải giữ 7 năm.** Rule `matchesPrefix` phân biệt case và chỉ nhìn **tên object**, không hiểu ngữ nghĩa kinh doanh.

### 13.3. Dữ liệu vừa upload và logic retry

Một pipeline có thể upload theo resumable/multipart trong nhiều giờ. Tuổi object cho rule `age` chỉ bắt đầu từ khi **object upload hoàn tất** (với XML multipart upload, tuổi của multipart upload trong rule Abort tính từ lúc **bắt đầu upload**). Thiết kế TTL không nên giả định tính từ lúc job khởi động nếu object chưa tồn tại hoàn chỉnh.

Nếu một workflow retry và viết lại object cùng tên:

- Thời điểm tạo **generation mới** khác generation cũ.
- Object Versioning có thể giữ generation cũ.
- Lifecycle Delete có thể tác động riêng từng generation theo điều kiện.
- Ứng dụng cần kiểm soát idempotency và generation preconditions khi ghi/xóa để tránh ghi đè ngoài ý muốn.

### 13.4. Data residency và mã hóa

Autoclass không di chuyển data location của bucket. Nó không làm cho dữ liệu đã xuất ra bên ngoài an toàn hơn, cũng không thay thế:

- **IAM** trên bucket/object, tài khoản dịch vụ và managed folder policies.
- **Uniform bucket-level access** và **Public access prevention**.
- **VPC Service Controls** cho sản phẩm hỗ trợ nếu có perimeter.
- **CMEK/CSEK**, quản lý key rotation và khả năng giải mã.
- Retention, object holds, audit logs và incident response.

Một bucket có lớp Archive rẻ nhưng public-read sai cấu hình vẫn là sự cố bảo mật nghiêm trọng.

## 14. Theo dõi hiệu quả Autoclass và Lifecycle

### 14.1. Monitoring metrics dành cho Autoclass

Google Cloud Monitoring có các metrics cho class transitions:

| Metric suffix | Diễn giải |
| --- | --- |
| `autoclass/transition_operation_count` | Số lần Autoclass chuyển storage class, không tính các lần phát sinh do bật Autoclass ban đầu |
| `autoclass/transitioned_bytes_count` | Tổng số bytes được chuyển class bởi Autoclass, cũng loại các transitions tại enablement |

Có thể nhóm metrics theo **source/destination storage class**. Trong Cloud Storage Console, vào bucket → **Configuration → See Performance** để quan sát số byte theo class theo thời gian nếu chức năng này được hiển thị cho bucket.

**Cách đọc:**

- Sau khi bật Autoclass cho bucket cũ, số object đang ở Standard có thể tăng do reset; transition metrics không bao gồm toàn bộ transitions của lúc enablement.
- Có nhiều chuyển xuống Nearline/Coldline thường cho thấy objects lâu không đọc. Nhưng một khối lượng lớn bị GET và chuyển lên Standard liên tục có thể báo hiệu pipeline scan nóng hóa dữ liệu.
- Chuyển lớp là asynchronous, nên metric không cần trùng chính xác mốc ngày 30/90/365 trên từng object.

### 14.2. Xem metadata mà không vô tình làm object nóng

Các lệnh sau chỉ đọc metadata hoặc liệt kê:

~~~bash
# Thông tin bucket
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="yaml(autoclass,lifecycle,location,softDeletePolicy,versioning)"

# Thông tin 1 object; không download dữ liệu
gcloud storage objects describe gs://BUCKET_NAME/reports/monthly/sample.csv \
  --format="yaml(name,storageClass,size,timeCreated,updated)"
~~~

**Không dùng `gcloud storage cat` hoặc `gcloud storage cp gs://... ./local` chỉ để kiểm tra class của object** nếu đang muốn quan sát quá trình lạnh hóa, vì đọc nội dung là hành động có thể làm Autoclass đưa object lên Standard.

### 14.3. Đối chiếu Billing và hiệu suất ứng dụng

Một dashboard FinOps có thể theo dõi:

- Tổng bytes ở Standard/Nearline/Coldline/Archive theo bucket và region.
- Số object theo dải kích thước: dưới 128 KiB, 128 KiB–1 MiB, 1–100 MiB, lớn hơn 100 MiB.
- Autoclass management charges, enablement charges, operations và class transitions.
- Retrieval/early deletion charges ở bucket **không Autoclass** hoặc khi chuyển đổi.
- Soft-deleted / noncurrent storage.
- Số object đủ điều kiện Delete nhưng chưa được xử lý.
- Cloud Storage request count, network egress, API latency và error rate.
- Chi phí phát sinh sau một thay đổi ứng dụng làm tăng GET.

Có thể dùng **Cloud Billing Reports**, **Budgets** hoặc **Cloud Billing export to BigQuery** để theo dõi phí theo SKU, project và kỳ hóa đơn. Khi so trước/sau thay đổi, cần giữ nguyên phạm vi region, số bytes, user traffic và thời gian quan sát để kết luận có căn cứ.

### 14.4. Định nghĩa thước đo hiệu quả

Một báo cáo Autoclass không nên chỉ ghi “chuyển 5 TB sang Archive”. Nó nên trả lời:

1. Tổng phí lưu trữ và quản lý **trước/sau** là bao nhiêu?
2. Enablement charge đã được phân bổ cho kỳ đánh giá chưa?
3. Có bao nhiêu object dưới 128 KiB không hưởng chuyển lớp?
4. Bao nhiêu object được đọc lại, Class A transitions phát sinh thế nào?
5. Có sự thay đổi tần suất GET, tăng egress hoặc quá trình scan không?
6. Khả năng lấy dữ liệu của ứng dụng có thay đổi không, có lỗi 403/404 không?
7. Quy tắc retention, soft delete, versioning và data governance có còn đúng không?

## 15. Bài lab có hướng dẫn: so sánh hai bucket

**Mục tiêu:** Cấu hình một bucket dùng **Autoclass + Lifecycle Delete**, một bucket dùng **Lifecycle SetStorageClass** không bật Autoclass, xác minh bằng metadata và giải thích trade-off.

**Lưu ý:** Các lệnh tạo/update/delete dưới đây **thay đổi tài nguyên thật và có thể phát sinh phí**. Chỉ chạy trong project lab được phê duyệt. Để kiểm tra hành vi class transitions thực tế phải có dữ liệu đã đủ **30/90/365 ngày** không đọc; bài lab có thể hoàn tất phần cấu hình/kiểm tra ngay, không cần thử đợi những khoảng thời gian đó.

### 15.1. Chuẩn bị dữ liệu thử nghiệm

Tạo hai bucket tên duy nhất toàn cục:

~~~text
gs://UNIQUE_AUTOC-LAB_BUCKET     (Autoclass)
gs://UNIQUE_MANUAL-LAB_BUCKET    (Lifecycle SetStorageClass)
~~~

Đây là placeholder; thay bằng tên hợp lệ của tổ chức, không chứa dấu `_` nếu không được phép theo quy định đặt tên. Đặt cả hai bucket ở cùng một location để so sánh chi phí công bằng.

Dùng CLI để xem project:

~~~bash
gcloud config get-value project
gcloud storage buckets list --project=LAB_PROJECT_ID
~~~

Tạo bucket lab nếu đã được cấp quyền (thay tên thực tế):

~~~bash
gcloud storage buckets create gs://AUTOC_BUCKET \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access

gcloud storage buckets create gs://MANUAL_BUCKET \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access
~~~

**Không dùng bucket đang quản lý artifact/image hoặc backup thật.** Tham chiếu data protection, IAM và default soft delete settings của project; không công khai object.

### 15.2. Kích hoạt Autoclass cho bucket A

~~~bash
# Thay đổi bucket: chỉ lab
gcloud storage buckets update gs://AUTOC_BUCKET \
  --enable-autoclass \
  --autoclass-terminal-storage-class=NEARLINE

# Đọc lại
gcloud storage buckets describe gs://AUTOC_BUCKET \
  --format="default(autoclass)"
~~~

Kết quả mong đợi: `autoclass.enabled: true` và terminal `NEARLINE`. Nếu bucket có default class không Standard, thêm `--default-storage-class=STANDARD` khi bật.

### 15.3. Chọn rule Delete cho bucket A

Tạo file **trong máy thực hành của người học** (không phải thư mục bài học) tên `lifecycle-autoc.json`:

~~~json
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 30,
        "matchesPrefix": ["temp/"]
      }
    }
  ]
}
~~~

Áp dụng:

~~~bash
# Update thay thế tất cả lifecycle rules đang có
gcloud storage buckets update gs://AUTOC_BUCKET \
  --lifecycle-file=lifecycle-autoc.json
~~~

Kiểm tra:

~~~bash
gcloud storage buckets describe gs://AUTOC_BUCKET \
  --format="yaml(autoclass,lifecycle)"
~~~

Đây là ví dụ hợp lệ vì dùng **Delete** theo tuổi và prefix, không dùng `SetStorageClass` hay `matchesStorageClass`.

### 15.4. Chọn rule SetStorageClass cho bucket B

Tạo file `lifecycle-manual.json`:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "NEARLINE"
      },
      "condition": {
        "age": 30,
        "matchesPrefix": ["reports/"]
      }
    },
    {
      "action": { "type": "Delete" },
      "condition": {
        "age": 180,
        "matchesPrefix": ["temp/"]
      }
    }
  ]
}
~~~

Áp dụng **chỉ cho bucket B, không bật Autoclass**:

~~~bash
gcloud storage buckets update gs://MANUAL_BUCKET \
  --lifecycle-file=lifecycle-manual.json
~~~

Tại đây, nếu bucket B vô tình đã bật Autoclass, lệnh có SetStorageClass sẽ bị từ chối theo quy tắc tương thích; không tắt Autoclass bừa bãi trên bucket chung để “sửa lỗi”.

### 15.5. Upload và đọc trạng thái object

Giả sử trên máy thực hành có một file **không nhạy cảm** tên `sample.txt`:

~~~bash
gcloud storage cp ./sample.txt gs://AUTOC_BUCKET/temp/sample.txt
gcloud storage cp ./sample.txt gs://MANUAL_BUCKET/temp/sample.txt
gcloud storage ls gs://AUTOC_BUCKET/temp/
gcloud storage ls gs://MANUAL_BUCKET/temp/
~~~

Đọc metadata, không tải dữ liệu:

~~~bash
gcloud storage objects describe gs://AUTOC_BUCKET/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated)"

gcloud storage objects describe gs://MANUAL_BUCKET/temp/sample.txt \
  --format="yaml(name,size,storageClass,timeCreated)"
~~~

**Kỳ vọng ngay sau upload:** Autoclass đặt object mới ở Standard. Bucket manual theo default class được chọn khi tạo; lifecycle sẽ không tức thì chuyển/xóa ngay khi object chưa đạt tuổi.

### 15.6. Bảng so sánh cần hoàn thành

| Câu hỏi | Bucket A: Autoclass | Bucket B: Manual Lifecycle |
| --- | --- | --- |
| Ai quyết định class? | Google dựa lịch sử GET | Rule SetStorageClass dựa tuổi/prefix |
| Object 32 KiB có xuống Nearline nhờ Autoclass không? | Không | Có thể bị rule chuyển lớp nếu khớp; cần đánh giá Class A fee |
| Đọc lại object Nearline thì thế nào? | Autoclass có thể đưa về Standard | Vẫn Nearline trừ khi có rewrite/logic khác |
| Rule Delete nào có hiệu lực? | `temp/` từ age 30 | `temp/` từ age 180 |
| Có dùng matchesStorageClass không? | Không | Có thể, nếu quy tắc hợp lệ |
| Có management fee Autoclass không? | Có với object đủ điều kiện | Không |
| Có Class A cho SetStorageClass không? | Không vì không có rule SetStorageClass | Có, khi rule thực hiện chuyển lớp |
| Có soft delete/retention không? | Tùy cấu hình bucket | Tùy cấu hình bucket |

**Không thử “xóa nhanh” bằng cách đặt `age:0` trên bucket production.** Một rule mới có thể tác động ngay đến dữ liệu cũ đủ điều kiện, trong khi xóa/restoration không có rollback an toàn tuyệt đối.

### 15.7. Dọn lab

- Đọc lại danh sách object, lifecycle, retention, soft delete và versioning.
- Chỉ xóa **những object và bucket do chính bài lab tạo**, sau khi xác nhận ownership.
- Nếu object vẫn ở trạng thái soft-deleted, bucket deletion có thể bị ràng buộc; kiểm tra theo tài liệu thay vì ép xóa.
- Nếu bucket có retention lock, không thể đơn giản bỏ lock để dọn.
- Không dùng lệnh recursive delete với wildcard trỏ vào bucket ngoài lab.
- Xác minh billing sau khi dọn; storage soft-delete hoặc log/monitoring có thể tiếp tục phát sinh phí trong thời hạn cấu hình.

## 16. Xử lý sự cố và câu hỏi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách điều tra / khắc phục |
| --- | --- | --- |
| Không bật được Autoclass | Lifecycle có SetStorageClass hoặc matchesStorageClass | Đọc lifecycle hiện tại, thiết kế lại rules phù hợp; không xóa bừa rule bảo vệ dữ liệu |
| Bật Autoclass nhưng thấy object class cũ | Enablement đang lan truyền/metadata chưa phản ánh ngay | Xem `autoclass.enabled`, thời điểm bật và chính sách charge; đừng suy chỉ từ một object |
| Autoclass đã bật nhưng object mới không xuống Nearline | Chưa đủ 30 ngày không đọc, nhỏ hơn 128 KiB hoặc có GET định kỳ | Kiểm tra size, access pattern, terminal class và thời gian đủ điều kiện |
| Không thấy Coldline/Archive | Terminal là NEARLINE hoặc object không đủ thời gian | Xem terminal class; chỉ ARCHIVE mới cho đường 90/365 |
| Object chuyển về Standard bất ngờ | Có GET nội dung từ app/job/scanner | Điều tra request logs và data-access pattern, đừng chỉ xem metadata |
| Chi phí tăng khi bật Autoclass trên bucket cũ | One-time enablement charge/objects reset về Standard | Đối chiếu Billing SKU, tổng bytes và class cũ |
| Tắt Autoclass nhưng đọc object vẫn bị tính phí class lạnh | Class của object không tự chuyển về Standard | Xem object storageClass, cost model sau disable |
| Lifecycle SetStorageClass bị từ chối | Bucket bật Autoclass | Chọn bucket non-Autoclass hoặc bỏ SetStorageClass |
| Delete với matchesStorageClass không được chấp nhận | Autoclass cấm condition này dù action là Delete | Dùng age/prefix/isLive/customTime phù hợp |
| Object đủ tuổi mà chưa xóa | Lifecycle bất đồng bộ, có retention/hold, soft delete/versioning | Xem rule, timeCreated, live/noncurrent, hold/retention |
| Xóa xong mà bytes tính phí vẫn còn | Soft-deleted hoặc noncurrent versions vẫn được giữ | Kiểm tra soft delete duration, generation và retention |
| Rule mới làm các object cũ bị xóa | Configuration thay thế toàn bộ rules, hoặc propagation rule cũ đến 24 giờ | Khôi phục từ soft delete/versioning nếu còn; xem audit, chỉnh quy trình review |
| SetStorageClass khiến phí operation cao | Hàng triệu object nhỏ cùng khớp | Tính Class A phí, đặt size filter hoặc tách bucket |
| GET object lạnh phí cao ở manual bucket | Retrieval fee và operation/egress của cold classes | Dự tính tần suất GET, cân nhắc Standard/Autoclass |
| Multipart upload dở dang chiếm phí | Chưa có AbortIncompleteMultipartUpload hoặc rule sai conditions | Dùng action Abort đúng loại API multipart và tuổi hợp lệ |
| Truy cập object bị `403` | IAM, KMS, ACL/PAP, retention/Org Policy tùy thao tác | Kiểm tra quyền riêng, không đổi storage class để “mở quyền” |
| Lỗi object compose trong Autoclass | Các source không đồng thời ở Standard | Theo tài liệu compose trong Autoclass, kiểm tra class source trước |
| Không thể xóa bucket lab | Còn object/versions/soft-deleted, retention/hold hoặc cấu hình khác | Kiểm tra trạng thái đúng bucket và thủ tục dọn được hỗ trợ |

### 16.1. Chẩn đoán theo thứ tự tránh phá dữ liệu

~~~text
Đúng bucket, project và owner?
  ↓
Autoclass có enabled, terminal class nào?
  ↓
Lifecycle hiện tại gồm những rules gì?
  ↓
Object nào, size, generation, creation time, live/noncurrent?
  ↓
Đọc dữ liệu GET gần đây? Có scan/job/caching?
  ↓
Có soft delete, retention policy hoặc object hold không?
  ↓
Đã đủ thời gian và có propagation delay?
  ↓
Chi phí phát sinh thuộc storage, operation, enablement hay egress?
  ↓
Đề xuất thay đổi + backup/rollback + phê duyệt
~~~

**Tránh thao tác chữa cháy không có bằng chứng:** Không bật/tắt Autoclass liên tục khi chi phí tăng; không sửa age Delete từ 10 sang 100 ngày rồi tưởng dữ liệu chắc chắn an toàn; không chuyển thủ công storage class trên Autoclass bucket để “ép” hệ thống.

## 17. Bài tập tình huống và đáp án định hướng

### Bài 1 — Đọc lại ảnh cũ

Một object ảnh 4 MiB được upload vào bucket có Autoclass terminal ARCHIVE. Nó không được đọc từ khi upload. Sau **40 ngày** object thuộc lớp nào theo timeline lý thuyết? Nếu được GET vào ngày 50, rồi không đọc thêm 100 ngày, các mốc dự kiến ra sao?

**Gợi ý:** Sau 40 ngày đủ điều kiện **Nearline** (thực thi bất đồng bộ); GET ngày 50 đưa object lên **Standard**. Tính chu kỳ mới từ lần GET: sau 30 ngày không đọc → Nearline; đến 90 ngày không đọc → Coldline; lúc 100 ngày không đọc, về lý thuyết đã đủ điều kiện Coldline, chưa Archive.

### Bài 2 — Một triệu object nhỏ

Bucket có 1 triệu object, mỗi object 16 KiB và ít đọc. Có nên kỳ vọng Autoclass chuyển tất cả sang Nearline sau 30 ngày?

**Gợi ý:** Không. Object **nhỏ hơn 128 KiB** luôn ở Standard trong Autoclass. Cần xem lại thiết kế dữ liệu và lifecycle/retention, không dựa vào Auto tiering để cứu chi phí.

### Bài 3 — Hai cách hiểu tuổi

Rule `Delete age=90` cho `reports/`. Object được upload ngày 1, đọc lại dữ liệu ngày 89. Ngày 91 có bị đủ điều kiện Delete không?

**Gợi ý:** Có, vì lifecycle `age` đo **từ creation time**, không reset khi GET. Autoclass có thể đổi storage class khi GET nhưng không thay quy tắc Delete theo tuổi.

### Bài 4 — Xung đột khi bật Autoclass

Bucket có Delete rule: `age:365, matchesStorageClass:["ARCHIVE"]`. Có bật Autoclass được ngay không? Nếu chỉ muốn xóa file cũ, sửa thế nào?

**Gợi ý:** Không, điều kiện `matchesStorageClass` không tương thích. Bỏ điều kiện theo class và dùng `age` cộng prefix/data category thích hợp, sau review chính sách giữ dữ liệu.

### Bài 5 — Soft delete và versioning

Bucket vừa bật Object Versioning, vừa soft delete. Rule Delete chỉ có `isLive:true` và `age:30`. Chi phí có giảm về zero sau 30 ngày không?

**Gợi ý:** Không. Live object có thể trở thành noncurrent; noncurrent generation chưa được rule này xóa. Nếu noncurrent bị xóa sau này, soft delete có thể giữ thêm. Xem retention và billing trước khi đặt rules cho bản cũ.

### Bài 6 — Tối ưu class theo tuổi

Một bucket không Autoclass chuyển object sang Nearline ở ngày 30, Coldline ngày 90, Archive ngày 365, xóa object ở ngày 400. Điều gì cần tính khi đánh giá chi phí?

**Gợi ý:** Class A operations của từng SetStorageClass, phí lưu trữ ở mỗi class, network/request/retrieval và khả năng early deletion khi Delete object trong Archive trước 365 ngày lưu ở class tương ứng. Không nhầm “age 400 từ creation” với “đã ở Archive 365 ngày”.

### Bài 7 — “Bật Autoclass luôn tiết kiệm”?

Một bucket đang có 20 TB Archive đã hơn một năm, hiếm được đọc. Có nên bật Autoclass vì Archive vốn rẻ?

**Gợi ý:** Chưa chắc. Bật sẽ đưa object cũ về Standard và có one-time enablement charge. Nếu access pattern ổn định, giữ class hiện tại có thể tốt hơn.

### Bài 8 — Lifecycle cập nhật rule xóa

Người vận hành đổi Delete `age:7` sang `age:30` vì phát hiện file đang bị xóa sớm. Có thể cam kết toàn bộ file 8–29 ngày tuổi sẽ được giữ ngay không?

**Gợi ý:** Không. Rule cũ có thể tiếp tục tác động tới **24 giờ** sau khi thay. Cần biện pháp bảo vệ dữ liệu và quy trình phê duyệt trước khi triển khai rule nguy hiểm.

### Bài 9 — Phân biệt rollback và restore

Bạn đã xóa `Delete` rule khỏi bucket và bật lại Autoclass. Điều này có khôi phục object đã xóa không?

**Gợi ý:** Không. Rule change không phải restore. Phục hồi chỉ khi có soft delete, noncurrent generations, backup/replica hoặc cơ chế khôi phục riêng còn hợp lệ.

## 18. Checklist trước khi áp dụng production

- [ ] Xác minh đúng project, bucket owner, location, data classification và data residency.
- [ ] Đo bytes/object count theo size: có bao nhiêu dưới 128 KiB.
- [ ] Biết access pattern thật, job scan, CDN/Cloud Storage FUSE và nhu cầu GET.
- [ ] Chọn Autoclass hay lifecycle dựa bài toán, không theo giá/GiB đơn lẻ.
- [ ] Nếu Autoclass: xác minh terminal class NEARLINE/ARCHIVE và mốc 30/90/365 ngày.
- [ ] Nếu bật Autoclass trên bucket có dữ liệu: dự toán one-time enablement, phí quản lý và reset class Standard.
- [ ] Nếu dùng lifecycle: JSON có **toàn bộ rules cần giữ**, đã review AND/OR, prefix và versioning.
- [ ] **Không** có `SetStorageClass` hoặc `matchesStorageClass` khi Autoclass bật.
- [ ] Không cấu hình lifecycle trực tiếp trên bucket do dịch vụ khác tự quản lý khi không được hỗ trợ.
- [ ] Kiểm tra minimum duration, phí Class A và retrieval/early deletion khi không dùng Autoclass.
- [ ] Kiểm tra soft delete duration, Object Versioning, retention, hold và chính sách pháp lý.
- [ ] Không lưu object quan trọng chung prefix temp với dữ liệu được phép xóa.
- [ ] Có backup/restore test và nhận thức lifecycle bất đồng bộ, rule cũ có thể tác động thêm 24 giờ.
- [ ] Có IAM tối thiểu, Uniform bucket-level access, Public access prevention và audit.
- [ ] Có dashboard chi phí, storage class, transitions và dữ liệu đã xóa/soft-deleted.
- [ ] Có phê duyệt, thử nghiệm lab, kế hoạch rollback và người chịu trách nhiệm.
- [ ] Đã đánh giá chi phí của cả mạng/operations, không chỉ at-rest storage.
- [ ] Có runbook khôi phục nếu Delete/retention/versioning được thiết lập sai.

## 19. Tài liệu chính thức Google Cloud

Các chi tiết chi phí, khả năng hỗ trợ và CLI có thể thay đổi theo thời gian. Khi thực hiện trên môi trường thật, đối chiếu các trang sau:

- [Autoclass overview](https://docs.cloud.google.com/storage/docs/autoclass) — nguyên tắc, terminal classes, ngưỡng 128 KiB, access behavior, restrictions, monitoring.
- [Use Autoclass](https://docs.cloud.google.com/storage/docs/using-autoclass) — bật/tắt/chỉnh terminal class, Console và `gcloud storage`.
- [Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle) — actions, conditions, thứ tự rules, phiên bản và deletion behavior.
- [Manage object lifecycles](https://docs.cloud.google.com/storage/docs/managing-lifecycles) — thiết lập/tải JSON, CLI, propagation và điều kiện quyền.
- [Object Lifecycle Management configuration samples](https://docs.cloud.google.com/storage/docs/lifecycle-configurations) — rules thực tế cho các trường hợp phổ biến.
- [Cloud Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes) — Standard/Nearline/Coldline/Archive và minimum storage duration.
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — storage, Class A/B operations, retrieval, Autoclass management/enablement, data transfer.
- [Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete) — thời hạn giữ, restore và tương tác với lifecycle.
- [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning) — live/noncurrent generations và recovery.
- [Bucket Lock and retention policies](https://docs.cloud.google.com/storage/docs/bucket-lock) — bảo lưu dữ liệu và những hạn chế không thể xóa.
- [Object holds](https://docs.cloud.google.com/storage/docs/object-holds) — temporary holds và event-based holds.
- [gcloud storage buckets update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update) — cờ Autoclass, lifecycle file và các tính năng bucket.
- [Cloud Storage monitoring](https://docs.cloud.google.com/storage/docs/monitoring) — metrics và quan sát.
- [Cloud Billing export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — phân tích chi phí thực tế theo project/SKU.

**Kết luận:** **Autoclass** giúp tự chọn storage class theo lịch sử đọc dữ liệu; **Object Lifecycle Management** thực hiện những quy tắc tuổi/phiên bản/prefix do bạn định nghĩa. Có thể dùng **Autoclass + Lifecycle Delete** trong cùng bucket nhưng không thể dùng Autoclass đồng thời với `SetStorageClass` hay `matchesStorageClass`. Quyết định tốt nhất phải xét thêm kích thước object, phí chuyển đổi, thời hạn bảo lưu, soft delete, versioning và số liệu billing thay vì chỉ nhìn giá lưu trữ trên mỗi GB.
