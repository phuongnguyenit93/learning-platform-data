# Bucket, object, key và mô hình nhất quán S3

> **Chương:** Lưu trữ đối tượng S3  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — tìm hiểu các dịch vụ AWS từ hạ tầng Region/AZ, IAM và VPC đến tính toán, lưu trữ, dữ liệu, tích hợp và serverless; thực hành lựa chọn giải pháp an toàn, quan sát được, phục hồi được và có chi phí phù hợp.

Amazon Simple Storage Service (**Amazon S3**) là dịch vụ **lưu trữ đối tượng (object storage)**. Thay vì tạo ổ đĩa rồi quản lý cấu trúc thư mục của hệ điều hành, ứng dụng lưu một **object** trong **bucket** và truy cập qua **key** bằng API. Cách tổ chức này thích hợp cho ảnh sản phẩm, tài liệu, bản sao lưu, log, dữ liệu phân tích và các tệp tĩnh cần mở rộng theo nhu cầu.

Để xây dựng ứng dụng đúng, người học cần nắm hai nhóm khái niệm: **mô hình dữ liệu** (`bucket → object → key`) và **mô hình nhất quán** (khi vừa ghi/xóa, thao tác đọc hoặc liệt kê sẽ thấy trạng thái nào). Với S3 hiện đại, việc ghi một object thành công rồi đọc lại có **strong read-after-write consistency**; nhưng điều đó không có nghĩa là mọi thao tác liên quan đến nhiều object, cache hoặc nhiều Region đều là một giao dịch đồng bộ.

Các ví dụ trong bài chủ yếu áp dụng cho **general purpose bucket**. S3 còn có **directory bucket** với cấu trúc, cách đặt tên, mô hình vị trí và một số khả năng riêng; chúng được phân biệt ở mục 4. Mọi tên bucket, account và key trong ví dụ chỉ là minh họa, không phải tài nguyên có sẵn trong AWS của người học.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **bucket**, **object**, **object key**, **prefix**, **metadata**, **tag** và **version ID**.
2. Giải thích namespace phẳng của general purpose bucket; hiểu vì sao đường dẫn chứa dấu `/` không mặc nhiên là thư mục thật.
3. Chọn và đặt tên bucket, thiết kế object key cho ứng dụng và nhận diện hệ quả của quyền IAM theo bucket/object.
4. Mô tả chính xác **strong consistency** của `PUT`, `GET`, `HEAD`, `DELETE`, `LIST` khi thao tác với object.
5. Nhận biết rủi ro khi **ghi đồng thời cùng key**, cập nhật nhiều key, bật versioning, đọc qua CDN và sao chép liên Region.
6. Thực hiện thao tác S3 cơ bản bằng AWS CLI, đưa ra phương án tránh ghi đè và kiểm tra tính đúng đắn trong môi trường thử.

## 2. S3 khác ổ đĩa và hệ thống tệp như thế nào?

Khi dùng ổ đĩa khối như **Amazon EBS**, hệ điều hành nhìn thấy một thiết bị block; thường cần tạo filesystem, mount và quản lý file. Khi dùng **Amazon EFS**, ứng dụng nhìn thấy filesystem dùng giao thức phù hợp và có ngữ nghĩa thư mục. Với **Amazon S3**, đối tượng được lưu và truy xuất qua HTTP/API hoặc công cụ tích hợp.

| Nhu cầu | Loại lưu trữ thường xem xét | Vì sao |
| --- | --- | --- |
| Ổ đĩa hệ điều hành/volume cho EC2 | **EBS** | Truy cập ở mức block cho EC2 |
| Filesystem chia sẻ, cần mô hình thư mục và giao thức NFS | **EFS** | Nhiều máy sử dụng cùng filesystem theo ngữ nghĩa NFS |
| Ảnh, video, file download, log, backup, data lake | **S3** | API object, mở rộng dung lượng và truy xuất theo key |

**Không đồng nhất S3 với filesystem POSIX**: general purpose bucket không hỗ trợ mọi thao tác kiểu `rename()`, khóa file, append hoặc cập nhật một vài byte như ổ đĩa thông thường. Việc “đổi tên file” thường phải **copy object sang key mới rồi xóa key cũ**; đây không phải giao dịch nguyên tử qua hai key. Một số ứng dụng có lớp tích hợp để *mount* S3, nhưng cách đó không tự biến S3 thành filesystem POSIX đầy đủ.

## 3. Ba khái niệm cốt lõi: bucket, object và key

~~~mermaid
flowchart TB
    B["General purpose bucket: example-learning-assets-2026"]
    B --> O1["Object 1"]
    B --> O2["Object 2"]
    B --> O3["Object 3"]
    O1 --> K1["key = images/products/sku-123/front.webp"]
    O2 --> K2["key = reports/2026/11/sales.csv"]
    O3 --> K3["key = reports/2026/11/summary.json"]
    O1 --> M1["Body + metadata + tags + tùy chọn version ID"]
    O2 --> M2["Body + metadata + tags + tùy chọn version ID"]
    O3 --> M3["Body + metadata + tags + tùy chọn version ID"]
~~~

Sơ đồ diễn giải cấu trúc logic. Những chuỗi `images/`, `products/`, `reports/` chỉ là phần của key và có thể được dùng làm **prefix**.

### 3.1. Bucket

**Bucket** là vùng chứa các object và là nơi áp dụng nhiều thiết lập quan trọng: Region/vị trí lưu trữ, quyền truy cập, versioning, lifecycle, encryption và logging. Với general purpose bucket, tên bucket phải **duy nhất trong AWS partition** phù hợp, nên một tên đơn giản có thể đã được tài khoản khác sử dụng.

Ví dụ:

~~~text
Bucket name: example-learning-assets-2026
Region:      ap-southeast-1
Purpose:     Ảnh sản phẩm và báo cáo của ứng dụng minh họa
~~~

Các điểm cần nhớ:

- Tên bucket khác với tên object. Bucket là vùng chứa, object được định danh bằng **key bên trong bucket**.
- Region của general purpose bucket được chọn lúc tạo; không có lệnh “đổi Region” tại chỗ cho bucket đang hoạt động. Muốn chuyển sang Region khác thường cần tạo bucket đích và di chuyển/sao chép dữ liệu.
- Bucket không tự public chỉ vì tên giống tên website. Quyền truy cập phụ thuộc IAM, bucket policy, S3 Block Public Access, Object Ownership và các cấu hình khác.
- **Bucket name không phải thông tin bí mật** và không nên nhúng dữ liệu nhạy cảm vào tên.
- Trong thực tế cần kiểm tra **quy tắc đặt tên cập nhật**; tên có những tiền tố/hậu tố dành riêng cho tính năng S3 nên không thể chọn tùy ý.
- Một số thiết lập cấp bucket, ví dụ bật versioning lần đầu, có thời gian lan truyền riêng; không suy luận tất cả thao tác quản trị bucket đều có tính nhất quán giống GET/PUT object.

Một bucket có thể chứa nhiều object. **S3 không yêu cầu biết trước tổng dung lượng** của cả bucket; tuy nhiên vẫn có giới hạn cho từng API, object, request và quota tài khoản tùy trường hợp. Hãy kiểm tra tài liệu dịch vụ trước khi thiết kế upload lớn.

### 3.2. Object

**Object** gồm **nội dung dữ liệu** (*body*) và **các thông tin mô tả/thuộc tính liên quan**, được lưu bằng một key trong bucket. Trong mô hình có versioning, một key có thể gắn với nhiều phiên bản, mỗi phiên bản có **version ID** riêng.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Object key** | `images/sku-123/front.webp` | Địa chỉ logic duy nhất trong bucket cho phiên bản hiện hành |
| **Body** | Các byte của ảnh WebP | Nội dung do ứng dụng tải lên |
| **Content-Type** | `image/webp` | Cho client biết loại dữ liệu được khai báo |
| **System metadata** | Kích thước, thời gian chỉnh sửa, ETag | Thông tin do S3 và API quản lý |
| **User-defined metadata** | `x-amz-meta-source: catalog` | Thông tin do ứng dụng khai báo khi ghi/copy object |
| **Object tags** | `Environment=prod`, `Team=catalog` | Phân loại phục vụ IAM, lifecycle, quản lý |
| **Storage class** | `STANDARD`, `STANDARD_IA`, ... | Mức tối ưu lưu trữ/truy xuất theo nhu cầu |
| **Encryption** | SSE-S3 hoặc cách mã hóa phù hợp | Bảo vệ dữ liệu lưu trữ, quản lý khóa theo chính sách |
| **Version ID** | Giá trị do S3 trả về khi bật versioning | Nhắm tới một phiên bản cụ thể của key |

**Metadata không phải object tag**. Metadata thường được xác lập khi tải object lên; để đổi user-defined metadata có thể phải **copy object với bộ metadata mới**. Tag được quản lý bằng API tagging riêng khi dịch vụ/loại bucket hỗ trợ. Cả hai đều cần quyền IAM thích hợp và có giới hạn kích thước/số lượng.

**ETag không luôn là MD5 của toàn bộ body**. Đặc biệt với multipart upload và một số cách mã hóa, không được dùng ETag như checksum MD5 tổng quát. Khi ứng dụng cần kiểm tra toàn vẹn, hãy dùng các checksum S3 hỗ trợ và xác minh quy trình tải lên.

### 3.3. Object key

Một **key** là tên của object **bên trong một bucket**; general purpose bucket cho phép key dài tối đa **1.024 byte theo UTF-8**. Key phân biệt chữ hoa/chữ thường:

~~~text
images/products/sku-123/front.webp
images/products/sku-123/FRONT.webp
~~~

Hai dòng trên là **hai key khác nhau**. Nếu không bật versioning, ghi object mới vào **cùng key** thường thay thế nội dung hiện hành; ghi vào key khác tạo object khác.

Một định danh logic dễ hiểu:

~~~text
s3://example-learning-assets-2026/images/products/sku-123/front.webp
└────────────────── bucket ──────────────────┘└────── object key ────────┘
~~~

`s3://...` là cách biểu diễn của AWS CLI/SDK, **không phải URL HTTPS mà trình duyệt tự tải được**. Truy cập HTTPS cần endpoint thích hợp, quyền hợp lệ hoặc **presigned URL** còn hiệu lực; một key có thể phải được URL-encode đúng khi đưa vào HTTP path.

## 4. Prefix, dấu / và “thư mục” trong S3

Trong **general purpose bucket**, không gian key là **phẳng** (*flat namespace*). Giao diện S3 Console thường hiển thị các key có dấu `/` như thư mục để người dùng dễ duyệt.

Ví dụ các key:

~~~text
images/products/sku-123/front.webp
images/products/sku-123/back.webp
images/products/sku-456/front.webp
reports/2026/11/sales.csv
reports/2026/12/sales.csv
readme.txt
~~~

Khi muốn xem “bên trong thư mục `images/products/sku-123/`”, ứng dụng thực tế đang lọc key có **prefix**:

~~~text
Prefix = images/products/sku-123/
Kết quả = hai key .../front.webp và .../back.webp
~~~

**Delimiter** `/` giúp API `ListObjectsV2` nhóm những chuỗi key thành `CommonPrefixes`, tạo trải nghiệm duyệt thư mục. Nhưng trong general purpose bucket:

- Không cần tạo “thư mục cha” trước khi PUT một object có key chứa dấu `/`.
- Có thể tồn tại object key `images/products/` có body rỗng (thường được Console tạo làm *folder marker*), nhưng điều này **không biến prefix thành thư mục POSIX**.
- Đổi tên `reports/2026/` không tự đổi tên tất cả object như thao tác rename một directory trên ổ đĩa; phải xử lý từng object/nhóm object bằng workflow copy/delete hoặc công cụ tương thích.
- Ký tự như dấu cách, dấu `+`, Unicode, `./`, `../` hoặc dấu `/` ở cuối có thể gây nhầm lẫn với CLI, URL parser, browser và các công cụ tích hợp. Nên dùng quy ước key đơn giản, ổn định.

### 4.1. Quy ước key cho ứng dụng

Một cấu trúc dễ quản trị cho hệ thống bán hàng:

~~~text
assets/products/<product-id>/<image-id>.webp
exports/orders/year=2026/month=11/day=20/<export-id>.parquet
logs/service=checkout/year=2026/month=11/day=20/<request-batch>.json.gz
backups/db/<backup-timestamp>/<filename>
~~~

Trong ứng dụng thật, hãy thay các đoạn `<...>` bằng giá trị được tạo/kiểm tra an toàn. Có thể dùng UUID/ULID để tránh trùng key, dùng phân vùng thời gian để truy vấn dễ hơn, và tách **dữ liệu người dùng cung cấp** khỏi quy ước nội bộ.

**Không dùng key làm nơi cất dữ liệu nhạy cảm.** Object key có thể xuất hiện trong log, URL, metrics và thông báo lỗi. Không đưa access token, mật khẩu, số giấy tờ cá nhân hay bí mật ứng dụng vào key.

### 4.2. General purpose bucket khác directory bucket

S3 hiện cung cấp nhiều kiểu bucket. Bài này tập trung vào **general purpose bucket**, trong đó prefix chỉ là cách tổ chức key logic. **Directory bucket** có cấu trúc phân cấp thực sự theo `/`, được dùng với những lớp lưu trữ/tính năng thích hợp như **S3 Express One Zone** trong một Zone được chọn; quy tắc tên bucket, endpoint, API và khả năng hỗ trợ khác general purpose bucket.

| Khía cạnh | General purpose bucket | Directory bucket |
| --- | --- | --- |
| Cấu trúc key | Namespace phẳng, `/` được dùng làm prefix/delimiter | Namespace phân cấp theo directory |
| Vị trí | Chọn Region khi tạo bucket | Gắn với Zone phù hợp theo loại directory bucket |
| Tên | Duy nhất trong AWS partition phù hợp | Có hậu tố Zone ID dạng `--zone-id--x-s3` |
| Tình huống chính | Ảnh, lưu trữ phổ dụng, backup, data lake | Workload yêu cầu truy cập đối tượng độ trễ thấp ở gần compute |
| Tính năng | Nhiều storage class, versioning và tính năng S3 phổ biến | Một số tính năng/API/giới hạn khác, cần kiểm tra riêng |

**Không sao chép tất cả câu lệnh trong bài sang directory bucket** khi chưa kiểm tra tài liệu S3 Express/Directory Buckets. Chẳng hạn, một số thao tác versioning, endpoint và cách liệt kê có khác biệt.

## 5. Tên và địa chỉ bucket/object trong các API

Ba dạng thường gặp:

| Biểu diễn | Ví dụ | Dùng ở đâu |
| --- | --- | --- |
| **S3 URI** | `s3://example-learning-assets-2026/reports/2026/11/sales.csv` | AWS CLI, một số tích hợp |
| **Bucket ARN** | `arn:aws:s3:::example-learning-assets-2026` | IAM `s3:ListBucket` và một số quyền cấp bucket |
| **Object ARN** | `arn:aws:s3:::example-learning-assets-2026/reports/*` | IAM `s3:GetObject`, `s3:PutObject`... |

ARN S3 general purpose bucket không mang Region hay account ID trong các trường tương ứng như nhiều ARN EC2. Điều đó **không** có nghĩa object tồn tại toàn cầu hay IAM không cần kiểm soát tài khoản.

Với AWS SDK, thường truyền **bucket** và **key** riêng:

~~~javascript
// Pseudocode theo API S3, minh họa cấu trúc request
const request = {
  Bucket: "example-learning-assets-2026",
  Key: "reports/2026/11/sales.csv"
};
~~~

Bucket policy thường áp dụng cho tài nguyên bucket hoặc object ARN, còn code ứng dụng thực hiện PUT/GET với đúng tên bucket/key. Không dùng chuỗi `s3://...` làm `Key`, vì phần prefix `s3://bucket/` không thuộc key.

## 6. Mô hình nhất quán S3: strong read-after-write

### 6.1. Khi một PUT thành công

Với object trong S3, **strong read-after-write consistency** nghĩa là: sau khi một lời gọi `PUT` thành công và client đã nhận phản hồi thành công, những lời gọi **GET** hoặc **LIST** bắt đầu sau đó sẽ nhìn thấy object/vùng dữ liệu mới. Điều này áp dụng cho **object mới** và **ghi đè object hiện có**; các yêu cầu xóa (`DELETE`) thành công cũng có tính nhất quán mạnh.

Đối với object hiện hành trong một bucket, bảng sau diễn giải kết quả kỳ vọng nếu không có hoạt động ghi mới khác chen vào:

| Hành động đã hoàn tất thành công | GET/HEAD bắt đầu sau đó | LIST bắt đầu sau đó |
| --- | --- | --- |
| **PUT key mới** `a.txt` | Thấy nội dung/metadata mới | Có `a.txt` |
| **PUT ghi đè** `a.txt` | Thấy phiên bản hiện hành mới | Key `a.txt` vẫn xuất hiện |
| **DELETE** key `a.txt` | Không trả object hiện hành vừa bị xóa | `a.txt` không còn trong danh sách object hiện hành |
| **PUT metadata/object mới cùng key** | Thấy trạng thái mới của object hiện hành | Thấy key phù hợp |

S3 còn cung cấp tính nhất quán mạnh cho nhiều thao tác đọc metadata, object tags và ACL được dịch vụ hỗ trợ. Cần phân biệt với việc thay đổi **cấu hình cấp bucket** (ví dụ một số thiết lập versioning hoặc chính sách) và các hệ thống bên ngoài: chúng có thể có độ trễ lan truyền riêng.

### 6.2. Thứ tự thời gian của PUT → GET → LIST

~~~mermaid
sequenceDiagram
    participant Writer as Service ghi file
    participant S3 as Amazon S3
    participant Reader as Service đọc file
    Writer->>S3: PUT reports/2026/11/sales.csv = V1
    S3-->>Writer: 200 OK / thành công
    Reader->>S3: GET cùng key (sau phản hồi thành công)
    S3-->>Reader: Body V1
    Reader->>S3: LIST prefix reports/2026/11/
    S3-->>Reader: Có sales.csv
~~~

Nếu PUT thành công ở thời điểm `t1`, GET/LIST được **bắt đầu sau `t1`** có thể quan sát trạng thái mới mà không cần client chờ “S3 đồng bộ vài giây” như cách diễn giải về eventual consistency cũ.

### 6.3. Ghi đè không tạo trạng thái nửa cũ nửa mới

Khi S3 xử lý cập nhật **một key**, thao tác là **atomic ở mức object/key**: với một GET đồng thời lúc ghi đè, client có thể nhận **toàn bộ body cũ hoặc toàn bộ body mới**, không nhận tệp chứa nửa byte cũ, nửa byte mới do S3 trộn lại.

Ví dụ:

~~~text
Trước PUT: key = config/app.json, body = V1
PUT mới:   key = config/app.json, body = V2

GET diễn ra đồng thời với PUT: có thể thấy V1 hoặc V2
GET bắt đầu sau phản hồi PUT thành công: thấy V2,
nếu không có một ghi/xóa mới hơn.
~~~

Đây là **atomicity của một object**, không phải transaction trên nhiều object.

### 6.4. DELETE và GET: lưu ý IAM

Sau khi xóa object hiện hành thành công, S3 không còn trả body hiện hành. Tuy vậy, **HTTP status** client nhìn thấy còn phụ thuộc quyền:

- Với quyền `s3:ListBucket` phù hợp, yêu cầu GET một key không tồn tại thường nhận `404 NoSuchKey`.
- Nếu principal không có quyền `s3:ListBucket`, GET một key không tồn tại có thể nhận **`403 AccessDenied`** thay vì 404.

Vì vậy **403 không chứng minh object có tồn tại**, và 404 không tự chứng minh cấu hình ứng dụng đã đúng. Khi debug, phải xem IAM, bucket policy, encryption, key, versioning và request context.

## 7. Điều S3 strong consistency **không** bảo đảm

S3 nhất quán mạnh với thao tác object không đồng nghĩa mọi hệ thống bên trên đều trả dữ liệu mới tức thời.

### 7.1. Không có giao dịch nguyên tử qua nhiều key

Giả sử quy trình xuất báo cáo ghi:

~~~text
reports/2026-11-20/part-0001.csv
reports/2026-11-20/part-0002.csv
reports/2026-11-20/manifest.json
~~~

Hai file `part` và `manifest.json` là **ba object riêng**. Nếu ứng dụng ghi dở file thứ hai rồi gặp lỗi, một client LIST có thể thấy trạng thái trung gian (ví dụ chỉ có `part-0001.csv`). S3 không bảo đảm **all-or-nothing** cho ba PUT.

**Mẫu thiết kế phù hợp:** ghi các phần dữ liệu dưới key bất biến, xác nhận chúng đã hoàn tất, **cuối cùng** ghi manifest hoặc dấu hiệu `_SUCCESS`. Client đọc manifest để biết tập dữ liệu nào đã sẵn sàng. Khi cần dữ liệu nhất quán nhiều bản ghi, hãy cân nhắc thêm một hệ thống hỗ trợ giao dịch như DynamoDB hoặc cơ sở dữ liệu quan hệ.

### 7.2. Không tự giải quyết tranh chấp ghi cùng key

Hai client đồng thời PUT lên cùng key có thể ghi đè lẫn nhau. S3 xử lý nhất quán ở cấp key, nhưng ứng dụng cần cơ chế **tránh lost update** nếu cả hai client đều có quyền ghi.

### 7.3. Không làm cache CDN luôn mới

Ví dụ CloudFront đã cache ảnh `images/sku-123/front.webp` và còn TTL. Nếu ứng dụng PUT ảnh mới lên **cùng key** trong S3, một client GET trực tiếp từ S3 sau PUT thành công sẽ thấy body mới, nhưng người dùng qua CloudFront **có thể vẫn nhận bản cache cũ** cho đến khi cache hết hiệu lực hoặc được invalidation theo thiết kế.

**Khuyến nghị:** với asset tĩnh, dùng key có phiên bản nội dung như `front.a3d91c.webp` và cập nhật đường dẫn trong trang; với tài nguyên phải giữ nguyên URL, thiết kế Cache-Control/TTL và invalidation hợp lý.

### 7.4. Không biến sao chép liên Region thành đồng bộ tức thì

**S3 Replication** (như Cross-Region Replication) thường thực hiện **bất đồng bộ**. GET ở bucket nguồn có thể thấy dữ liệu mới sau PUT thành công, trong khi bucket đích ở Region khác chưa kịp nhận bản sao. Phải theo dõi replication status/metrics và thiết kế **RPO, quy trình failover** phù hợp.

Tương tự, S3 Event Notifications hoặc luồng dữ liệu qua SQS/Lambda/EventBridge có cơ chế giao hàng, độ trễ và khả năng lặp riêng. **S3 strong consistency không có nghĩa event luôn tới đúng một lần và theo thứ tự toàn cục**; consumer cần thiết kế idempotent.

### 7.5. Lỗi mạng không đồng nghĩa PUT thất bại

Client có thể gửi PUT thành công đến S3 nhưng **không nhận được phản hồi** vì timeout mạng. Khi đó, không thể kết luận object không được lưu. Thay vì retry mù quáng, hãy dùng key/idempotency strategy, `HEAD` hoặc điều kiện ghi phù hợp để quyết định thao tác tiếp theo.

## 8. Ghi đồng thời, conditional writes và ETag

### 8.1. Lost update là gì?

Hai service đọc cùng một trạng thái rồi đều ghi lại cùng key:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant S as S3 (object config.json)
    participant B as Writer B
    A->>S: GET config.json = V1
    B->>S: GET config.json = V1
    A->>S: PUT config.json = V2A
    S-->>A: Thành công
    B->>S: PUT config.json = V2B
    S-->>B: Thành công
    Note over A,B: B có thể ghi đè thay đổi của A
~~~

Sau khi B PUT thành công và không còn hoạt động ghi khác, GET sẽ thấy V2B. S3 **không tự khóa object để writer A/B phối hợp nhau**. Khả năng nhìn thấy dữ liệu mới nhất và điều phối nhiều writer là hai vấn đề khác nhau.

### 8.2. `If-None-Match: *`: chỉ ghi nếu key chưa có object hiện hành

Conditional PUT với header `If-None-Match: *` yêu cầu S3 chỉ tạo object nếu chưa có object hiện hành ở key đó. Nếu key đã có object hiện hành, S3 trả lỗi `412 Precondition Failed`. Điều này hữu ích khi ứng dụng muốn **tránh ghi đè** hoặc sử dụng key không trùng lặp.

Ví dụ AWS CLI (trên phiên bản CLI hỗ trợ tham số, bucket đã có sẵn):

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key exports/job-123/result.csv \
  --body ./result.csv \
  --if-none-match "*"
~~~

Khi có ghi/xóa cạnh tranh, một số yêu cầu có thể nhận **`409 ConditionalRequestConflict`**. Quy trình retry cần dựa trên mã lỗi và API thực tế; không tự động coi mọi 409 như lỗi vĩnh viễn.

**Khi bật versioning:** nếu current version là **delete marker**, yêu cầu `If-None-Match: *` có thể thành công vì không có phiên bản object hiện hành. Vì vậy điều kiện này **không bảo đảm key chưa từng tồn tại trong lịch sử**.

### 8.3. `If-Match`: chỉ ghi nếu object vẫn như trạng thái đã đọc

Ứng dụng đọc `HEAD`/`GET` lấy **ETag hiện hành**, sau đó chỉ cập nhật khi ETag chưa đổi:

~~~text
HEAD  config/app.json → ETag = "etag-v1"
PUT   config/app.json với If-Match: "etag-v1"

Nếu ETag hiện hành vẫn khớp: ghi thành công
Nếu ETag khác: 412 Precondition Failed
~~~

Đây là hình thức **optimistic concurrency control**: tránh âm thầm ghi đè khi một writer khác đã thay object. Tuy nhiên, ETag là bộ so khớp trạng thái object, không phải checksum MD5 bảo đảm cho mọi cách upload. Ứng dụng vẫn cần xử lý tình huống cạnh tranh/xóa/timeout và thiết kế retry có kiểm soát.

### 8.4. Chọn mẫu cập nhật phù hợp

| Bài toán | Chiến lược nên xem xét |
| --- | --- |
| Mỗi lần xuất một file, không muốn ghi đè | Key chứa ID duy nhất; `If-None-Match: *` |
| Nhiều người sửa cùng object cấu hình | `HEAD/GET` lấy ETag, `If-Match` khi PUT, giải quyết conflict |
| Cần khôi phục bản cũ | S3 Versioning và quy trình phục hồi |
| Ghi nhiều object thành một “bản phát hành” | Ghi immutable objects trước, cập nhật manifest sau |
| Quy trình tiền/đơn hàng đòi atomic multi-record | Dùng datastore có transaction; S3 chỉ lưu file/đầu ra phù hợp |
| Phải chống xóa/sửa trong kỳ lưu giữ | Xem xét S3 Object Lock và quyền quản trị phù hợp |

**S3 Object Lock** là tính năng lưu giữ/khóa đối tượng theo chế độ được hỗ trợ, **khác với cơ chế khóa phối hợp writer**. Không dùng tên “Object Lock” để suy rằng S3 tự có mutex cho nhiều PUT cùng key.

## 9. Versioning: có nhiều phiên bản dưới một key

**S3 Versioning** là tính năng cấp bucket giúp lưu giữ các phiên bản của object. Khi bật:

- Một lần PUT vào key hiện có tạo **phiên bản mới**; phiên bản cũ trở thành *noncurrent version* thay vì bị ghi đè mất ngay.
- GET thông thường lấy **current version** của key.
- GET với **version ID** hợp lệ có thể đọc một phiên bản cũ nếu principal có quyền và object còn được lưu.
- DELETE **không nêu version ID** thường tạo **delete marker** trở thành current version. Object trước đó có thể vẫn tồn tại ở lịch sử.
- Muốn xóa **vĩnh viễn một version**, phải dùng thao tác/xác thực quyền xóa version cụ thể; việc này không giống DELETE bình thường.

~~~mermaid
flowchart LR
    V1["PUT key=a.txt, body=V1"] --> V2["PUT cùng key, body=V2"]
    V2 --> D["DELETE không version ID"]
    D --> M["Current = delete marker"]
    M --> OLD["V1, V2 vẫn có thể là noncurrent versions"]
~~~

**Cẩn trọng khi nói “DELETE là xóa vĩnh viễn”**: trong bucket bật versioning, DELETE không chỉ định version thường khiến GET object hiện hành trả lỗi giống không tồn tại (theo quyền), nhưng phiên bản cũ vẫn có thể khôi phục nếu còn lưu.

Đối với hệ thống production:

- Versioning giảm rủi ro ghi đè/xóa nhầm, nhưng **không thay thế backup, quyền hạn chế và diễn tập phục hồi**.
- Mỗi version chiếm dung lượng/lớp lưu trữ tương ứng và có chi phí; dùng **Lifecycle Rules** quản lý noncurrent versions và thời hạn giữ dữ liệu theo yêu cầu.
- Sau khi bật versioning lần đầu, AWS lưu ý có thời gian lan truyền thiết lập; nên cho phép hoàn tất quá trình trước khi dựa vào versioning trong một workflow nhạy cảm.
- Versioning có các trạng thái như **Enabled** và **Suspended**; behavior của `null version`/delete marker cần hiểu trước khi chuyển trạng thái.

Ví dụ CLI chỉ đọc danh sách version (yêu cầu `s3:ListBucketVersions`):

~~~bash
aws s3api list-object-versions \
  --bucket example-learning-assets-2026 \
  --prefix reports/2026/ \
  --query "{Versions:Versions[].{Key:Key,Version:VersionId,Latest:IsLatest},DeleteMarkers:DeleteMarkers[].{Key:Key,Version:VersionId,Latest:IsLatest}}" \
  --output json
~~~

## 10. LIST và quy tắc phân trang

`ListObjectsV2` trả về danh sách object hiện hành theo điều kiện lọc. Một request có giới hạn số key trả về; khi danh sách lớn, phải **phân trang** bằng continuation token hoặc paginator của AWS SDK/CLI.

Ví dụ liệt kê các object có prefix `reports/2026/11/`:

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix reports/2026/11/ \
  --query "Contents[].{Key:Key,Size:Size,LastModified:LastModified}" \
  --output table
~~~

Ví dụ nhóm các “thư mục con” bằng delimiter:

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix reports/ \
  --delimiter "/" \
  --query "{Files:Contents[].Key,Folders:CommonPrefixes[].Prefix}" \
  --output json
~~~

**Cần phân biệt:**

- `Prefix` là bộ lọc **đầu chuỗi key**, không phải một thư mục thực trong general purpose bucket.
- `Delimiter` giúp nhóm key vào `CommonPrefixes`; các prefix này không phải object.
- Với general purpose bucket, kết quả LIST có thứ tự từ điển theo key trong những điều kiện API tương ứng; **directory bucket** có quy tắc thứ tự khác, không thể suy diễn y hệt.
- **Mỗi trang LIST được xử lý theo thời điểm request riêng**. Nếu ứng dụng đang thêm/xóa key trong lúc quét nhiều trang, không nên coi toàn bộ kết quả các trang là một **snapshot transaction** bất biến.
- Listing không tự bảo đảm rằng client có quyền `GetObject` đối với mọi key nhìn thấy; IAM có action riêng cho bucket và object.

### 10.1. Một lỗi logic phổ biến

Giả sử ETL đang xử lý tất cả key có prefix `incoming/`. Một tiến trình khác vẫn đang upload dữ liệu mới vào đó. Vòng LIST phân trang có thể đọc một tập key thay đổi trong thời gian chạy, dẫn tới bỏ sót hoặc xử lý lặp khi kết hợp với retry/đổi key.

**Cách thiết kế:** dùng key không đổi, viết marker/manifest khi một batch hoàn tất, hoặc dùng queue/event + trạng thái xử lý idempotent. Strong consistency của mỗi yêu cầu S3 **không thay thế cơ chế xác định “một batch đã đóng”** trong ứng dụng.

## 11. Multipart upload và tính nhất quán

Với object lớn, S3 hỗ trợ **multipart upload**: ứng dụng khởi tạo upload, gửi các part, rồi hoàn tất bằng `CompleteMultipartUpload`. Một key mới chỉ trở thành **object hiện hành** sau khi hoàn tất thành công; việc upload vài part chưa biến chúng thành một object hoàn chỉnh có thể GET theo key.

~~~mermaid
flowchart LR
    START["CreateMultipartUpload"] --> P1["UploadPart 1"]
    START --> P2["UploadPart 2"]
    START --> P3["UploadPart N"]
    P1 --> COMPLETE["CompleteMultipartUpload"]
    P2 --> COMPLETE
    P3 --> COMPLETE
    COMPLETE --> VISIBLE["Object hiện hành có thể GET/LIST"]
~~~

Khi quá trình hoàn tất thành công, tính nhất quán mạnh áp dụng cho object hiện hành. Khi xảy ra lỗi giữa chừng, multipart upload có thể còn các part chưa hoàn tất và **phát sinh chi phí lưu trữ**; cần hủy upload không dùng hoặc đặt lifecycle rule dọn multipart upload chưa hoàn thành.

**Lưu ý ETag:** multipart upload thường cho ETag không tương đương với MD5 của toàn bộ object. Dùng checksum mà API hỗ trợ để kiểm tra toàn vẹn.

## 12. IAM và bảo mật gắn với bucket/key

S3 thường được triển khai theo nguyên tắc **private by default, least privilege**. AWS kiểm soát quyền theo danh tính IAM, bucket policy, các chính sách quản trị/giới hạn liên quan và cấu hình truy cập công khai. Không dùng object key khó đoán như một biện pháp bảo mật thay cho authorization.

### 12.1. Quyền bucket và object là hai cấp tài nguyên

| Thao tác | Action IAM | ARN thường dùng |
| --- | --- | --- |
| Liệt kê key trong bucket | `s3:ListBucket` | `arn:aws:s3:::example-learning-assets-2026` |
| Đọc body object | `s3:GetObject` | `arn:aws:s3:::example-learning-assets-2026/exports/*` |
| Ghi object | `s3:PutObject` | `arn:aws:s3:::example-learning-assets-2026/uploads/*` |
| Xóa object hiện hành | `s3:DeleteObject` | ARN object |
| Đọc phiên bản cụ thể | `s3:GetObjectVersion` | ARN object, quyền phù hợp |
| Liệt kê các phiên bản | `s3:ListBucketVersions` | ARN bucket |

Ví dụ identity-based policy cho role ETL **được liệt kê và đọc** file dưới `reports/`, không có Allow cho upload/delete:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListReportPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-learning-assets-2026",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["reports/", "reports/*"]
        }
      }
    },
    {
      "Sid": "ReadReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-learning-assets-2026/reports/*"
    }
  ]
}
~~~

**Diễn giải:**

1. `s3:ListBucket` phải dùng **bucket ARN**, có thể thêm `s3:prefix` để chỉ liệt kê phần cần thiết.
2. `s3:GetObject` dùng **object ARN**, có wildcard giới hạn prefix.
3. Không có Allow `PutObject`, `DeleteObject` hoặc `GetObject` ngoài prefix được nêu.
4. Policy này chưa tính tới những giới hạn bổ sung của IAM Organizations/SCP, permission boundary, bucket policy, KMS key policy hay điều kiện của môi trường thật.

### 12.2. Mã hóa, quyền sở hữu và truy cập công khai

- S3 mã hóa object mới khi lưu trữ theo mặc định với SSE-S3; nếu dùng **SSE-KMS**, ứng dụng còn phải đáp ứng quyền KMS phù hợp và quản lý key policy.
- **S3 Block Public Access** nên được cấu hình ở phạm vi phù hợp để tránh vô tình cấp quyền công khai không mong muốn.
- **Object Ownership – Bucket owner enforced** (khi áp dụng) giúp đơn giản hóa kiểm soát quyền sở hữu và tắt ACL trong các tình huống hỗ trợ; ưu tiên IAM và bucket policy hơn việc dựa vào ACL cá nhân nếu không có yêu cầu đặc thù.
- Với file phục vụ qua **CloudFront**, có thể dùng bucket S3 private và **Origin Access Control (OAC)** để CloudFront truy cập origin theo chính sách.
- Presigned URL cấp khả năng thực hiện một yêu cầu trong thời hạn/điều kiện nhất định thông qua quyền của principal ký; không biến object thành public vĩnh viễn, nhưng **URL là một dạng bearer token** cần giữ kín khi còn hiệu lực.
- Bucket hoặc object có thể bị chặn theo VPC endpoint policy, IP/condition, Block Public Access hoặc explicit Deny dù identity policy có Allow.

### 12.3. Đặt key và dữ liệu đúng nhu cầu phục hồi

Ảnh sản phẩm, log và backup không có cùng yêu cầu:

| Dữ liệu | Yêu cầu nổi bật | Cân nhắc |
| --- | --- | --- |
| Ảnh/tệp tĩnh công khai | Tải nhanh và cache hiệu quả | S3 private origin + CloudFront, key có version nội dung |
| Báo cáo nhạy cảm | Chỉ role được phép đọc, có lịch sử sửa | IAM/prefix, encryption, versioning, audit |
| Backup | Khả năng phục hồi khi bị xóa nhầm/ransomware | Versioning, Object Lock nếu phù hợp, sao chép/backup, kiểm thử restore |
| Log hệ thống | Tần suất ghi cao, giữ theo quy định, truy vấn sau | Prefix theo thời gian, lifecycle, quyền ghi riêng và retention |
| Data lake | Nhiều file, phân vùng dữ liệu, ETL song song | Immutable keys, manifest/transaction layer, lifecycle, catalog |

S3 Standard lưu dữ liệu qua nhiều AZ do AWS quản lý trong một Region. **Không phải mọi storage class đều có cùng phạm vi AZ**; ví dụ các lớp One Zone tập trung trong một AZ. Hãy chọn storage class theo độ trễ, tần suất đọc, mục tiêu phục hồi và giá thật.

## 13. Thực hành AWS CLI: quan sát tính nhất quán

Thực hành này dùng **một general purpose bucket dành riêng cho phòng lab**. Các lệnh có thể tạo/xóa object và tính phí theo request/dung lượng; **không chạy trên bucket production**. Chỉ thực hiện khi có quyền với dữ liệu lab và đã xem trước tên bucket/key. Các đoạn lệnh giả sử AWS CLI cài sẵn và shell kiểu Bash (Linux/macOS/WSL); PowerShell có cú pháp biến khác.

### 13.1. Chuẩn bị

1. Chọn một bucket lab đã có sẵn trong Region phù hợp; hoặc tạo bucket mới bằng tài khoản lab theo hướng dẫn chính thức.
2. Đảm bảo bạn có các quyền cần thiết để đọc, liệt kê, ghi và xóa các object lab, cùng quyền bucket nếu tự tạo bucket.
3. Tạo tệp local `report-v1.txt` và `report-v2.txt`, tuyệt đối không chứa dữ liệu thật.
4. Kiểm tra danh tính AWS trước khi thao tác.

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Trong các ví dụ dưới đây, thay `example-learning-assets-2026` bằng tên bucket lab thuộc quyền quản trị và hai tệp đã chuẩn bị trong thư mục hiện tại. Các ví dụ **không tự tạo bucket** và không gọi `DeleteBucket`.

### 13.2. PUT object mới

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v1.txt
~~~

Chỉ tiếp tục khi lệnh trả về thành công. Một số thông tin ETag, version ID hoặc checksum trong phản hồi phụ thuộc cấu hình bucket và cách upload.

### 13.3. GET và HEAD ngay sau PUT

~~~bash
aws s3api head-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --query "{Length:ContentLength,ETag:ETag,Modified:LastModified}" \
  --output json

aws s3api get-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  ./downloaded-report.txt
~~~

So sánh `downloaded-report.txt` với `report-v1.txt` bằng công cụ hệ điều hành phù hợp. Khi PUT đã hoàn tất thành công và không có writer khác, GET sẽ thấy body V1.

### 13.4. LIST ngay sau PUT

~~~bash
aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix lab/consistency/ \
  --query "Contents[].{Key:Key,Size:Size}" \
  --output table
~~~

Kết quả phải có key `lab/consistency/report.txt` nếu bucket/key/quyền đúng và không có thao tác khác xóa hoặc thay đổi kết quả theo thời gian.

### 13.5. Ghi đè và đọc lại

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v2.txt

aws s3api get-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  ./downloaded-report-v2.txt
~~~

Khi PUT V2 thành công và không có ghi mới, kết quả GET là **V2**. Nếu bucket bật versioning, V1 có thể vẫn tồn tại như một phiên bản cũ.

### 13.6. Thử chống ghi đè

~~~bash
aws s3api put-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt \
  --body ./report-v1.txt \
  --if-none-match "*"
~~~

Nếu key đang có object hiện hành, lệnh này dự kiến bị từ chối với `412 Precondition Failed`. Đây là **lỗi được mong đợi trong bài thử**, xác nhận cơ chế conditional PUT đã chặn ghi đè.

### 13.7. Dọn dữ liệu lab

Chỉ xóa **đúng key lab** vừa tạo, sau khi kiểm tra bucket và key:

~~~bash
aws s3api delete-object \
  --bucket example-learning-assets-2026 \
  --key lab/consistency/report.txt

aws s3api list-objects-v2 \
  --bucket example-learning-assets-2026 \
  --prefix lab/consistency/ \
  --output json
~~~

Nếu bật versioning, lệnh DELETE có thể tạo **delete marker**; phiên bản cũ vẫn tồn tại, tính phí và cần quy trình riêng nếu muốn dọn toàn bộ lịch sử. **Không dùng lệnh xóa hàng loạt hoặc xóa bucket** khi chưa xem đầy đủ danh sách version/object và quyền trên môi trường lab.

## 14. Bài toán thực tế: ảnh sản phẩm và báo cáo đơn hàng

### 14.1. Ảnh sản phẩm

Nhóm sản phẩm muốn thay ảnh cho SKU-123. Có hai cách:

**Cách A — ghi đè cùng key**

~~~text
PUT images/products/sku-123/front.webp  (body mới)
GET trực tiếp S3 sau khi PUT thành công → body mới
GET qua CloudFront trước khi cache hết hạn → có thể còn body cũ
~~~

Ưu điểm là giữ URL ổn định. Nhược điểm là phải quản lý cache, đồng thời ghi đè có thể gây mất dữ liệu nếu không có versioning/conditional write.

**Cách B — key bất biến theo phiên bản nội dung**

~~~text
PUT images/products/sku-123/front.20261120-a3d9.webp
GET key mới từ S3 → body mới
Ứng dụng cập nhật catalog để chỉ tới key mới
~~~

Cách B giúp cache rõ ràng hơn và tránh ghi đè; cần cơ chế dọn những phiên bản không còn sử dụng theo chính sách retention.

### 14.2. Báo cáo đơn hàng

Một job xuất đơn hàng theo ngày có thể tạo nhiều phần dữ liệu:

~~~text
exports/orders/date=2026-11-20/part-0001.parquet
exports/orders/date=2026-11-20/part-0002.parquet
exports/orders/date=2026-11-20/manifest.json
~~~

Quy trình:

1. Worker tạo mỗi file part bằng một key riêng, không ghi đè file hoàn tất.
2. Sau khi tất cả PUT thành công, service kiểm tra đủ file/key và ghi `manifest.json` cuối cùng.
3. Consumer chỉ đọc bản manifest hợp lệ, sau đó xử lý đúng các key được liệt kê.
4. Khi retry, job phải phân biệt file đã hoàn tất, file lỗi và batch có thể chạy lại; dùng job ID và idempotency key.

Đây là **mẫu đảm bảo ở tầng ứng dụng**, không phải giao dịch multi-object do S3 tự hỗ trợ.

### 14.3. S3 phù hợp vai trò nào trong kiến trúc AWS?

~~~mermaid
flowchart TB
    USER["Người dùng"] --> APP["API chạy trên EC2/ECS/Lambda"]
    APP -->|"PUT ảnh gốc"| S3["S3 general purpose bucket"]
    APP --> DB["RDS/DynamoDB: metadata nghiệp vụ"]
    S3 --> CF["CloudFront: cache đối tượng"]
    CF --> USER
    S3 -.->|"Event notification - bất đồng bộ"| Q["SQS/EventBridge/Lambda"]
    Q --> WORKER["Xử lý ảnh, tạo thumbnail"]
    WORKER -->|"PUT key thumbnail mới"| S3
~~~

Với luồng này, database thường giữ thông tin nghiệp vụ như product ID, owner, quyền hiển thị và **key/version** tương ứng. S3 giữ body của ảnh. Nếu sự kiện bị gửi lại hoặc đến trễ, worker phải idempotent; nếu catalog thay đổi, cần bảo đảm metadata DB không trỏ tới object chưa sẵn sàng.

## 15. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “S3 là ổ đĩa có thư mục truyền thống.” | General purpose bucket có **flat key namespace**; dấu `/` là cách quy ước prefix. |
| “Bucket name trùng ở mọi Region cũng được.” | Với general purpose bucket, tên phải duy nhất trong **AWS partition** liên quan. |
| “Key là cả chuỗi `s3://bucket/file`.” | Key chỉ là `file` hoặc đường key tương ứng bên trong bucket. |
| “PUT thành công nhưng phải đợi vài giây mới GET/LIST thấy.” | S3 có **strong read-after-write consistency** cho object operations được hỗ trợ. |
| “Strong consistency nghĩa là tất cả GET đồng thời với PUT đều thấy bản mới.” | GET diễn ra **đồng thời** có thể thấy bản cũ hoặc mới, không thấy object bị ghi dở. |
| “Hai PUT cùng key tự hợp nhất dữ liệu.” | Ghi đồng thời có thể ghi đè nhau; dùng conditional writes/versioning theo nhu cầu. |
| “Ghi 10 object là một giao dịch.” | S3 không có atomic multi-object transaction; ứng dụng phải tạo manifest/quy trình riêng. |
| “Đổi tên folder là thao tác nguyên tử.” | Với general purpose bucket thường là copy/delete nhiều object, có trạng thái trung gian. |
| “Versioning làm DELETE biến mất hoàn toàn khỏi lịch sử.” | DELETE thường tạo delete marker; noncurrent versions có thể vẫn còn. |
| “ETag luôn bằng MD5.” | Không đúng cho nhiều kiểu upload/mã hóa, đặc biệt multipart. |
| “S3 mới thì CloudFront cũng phải lập tức trả bản mới.” | Cache/CDN có TTL và chính sách invalidation độc lập. |
| “Replica ở Region thứ hai nhất quán ngay với nguồn.” | Replication có độ trễ bất đồng bộ, phải đo và xử lý RPO. |
| “Nhìn thấy key khi LIST là đủ quyền GET body.” | `ListBucket` và `GetObject` là hai quyền khác nhau. |
| “S3 mạnh nhất quán nên event chỉ đến một lần theo đúng thứ tự.” | Notifications/queues có mô hình giao hàng riêng; consumer cần idempotency. |

## 16. Tự kiểm tra

### Bài tập 1 — bucket hay key?

Xem biểu diễn:

~~~text
s3://shop-media-2026/assets/products/sku-001/main.png
~~~

Hãy xác định bucket, key và prefix `assets/products/`.

**Gợi ý:** bucket là `shop-media-2026`; key là `assets/products/sku-001/main.png`. Prefix `assets/products/` là bộ lọc các key bắt đầu bằng chuỗi đó, không cần tạo thư mục vật lý trong general purpose bucket.

### Bài tập 2 — đọc sau ghi

Service A PUT `orders/summary.json` = V2 và đã nhận thành công. Service B bắt đầu GET đúng key từ cùng bucket, không đi qua cache và không có writer khác. B thấy V1 hay V2?

**Gợi ý:** B nhận V2 theo strong read-after-write consistency. Nếu GET diễn ra **đồng thời** với PUT, kết quả có thể là V1 hoặc V2 hoàn chỉnh.

### Bài tập 3 — hai writer

Worker A và B cùng đọc ETag của `config/app.json`, rồi cả hai muốn ghi đè key đó. Hãy đề xuất cách tránh B vô tình ghi đè thay đổi của A.

**Gợi ý:** dùng `If-Match` với ETag đã đọc, xử lý `412 Precondition Failed` bằng đọc lại/giải quyết xung đột. Nếu không cần cùng key, dùng key có định danh riêng và `If-None-Match: *`.

### Bài tập 4 — xóa object có versioning

Bucket đã bật versioning chứa V1, sau đó PUT V2 và DELETE mà không chỉ định version ID. Vì sao GET object hiện hành không trả body, trong khi bảng lịch sử vẫn có V1/V2?

**Gợi ý:** DELETE tạo current **delete marker**. Các noncurrent versions có thể vẫn được lưu; muốn phục hồi phải xử lý marker hoặc đọc/copy đúng version có quyền.

### Bài tập 5 — CDN không thấy cập nhật

Ứng dụng PUT ảnh mới vào S3 và GET trực tiếp thấy ảnh mới, nhưng trang web vẫn hiển thị ảnh cũ qua CloudFront. Có phải S3 mất strong consistency không?

**Gợi ý:** Không. Kiểm tra cache TTL, Cache-Control, đường dẫn object và invalidation; cân nhắc key bất biến gắn mã phiên bản nội dung.

### Bài tập 6 — thiết kế batch an toàn

Một pipeline phải xuất 200 file CSV rồi thông báo “batch đã sẵn sàng”. Người đọc chỉ được xử lý khi đủ 200 file. Tại sao không chỉ LIST prefix rồi mặc định đủ dữ liệu? Hãy thiết kế manifest, điều kiện ghi và cách retry.

**Gợi ý:** LIST không nói tiến trình upload đã kết thúc hay chưa. Ghi mỗi part bằng key không đổi, xác nhận số lượng/checksum, sau cùng PUT manifest (có thể dùng conditional write); reader chỉ xử lý tập file được manifest chỉ ra.

## 17. Ghi nhớ

**Bucket** là vùng chứa được cấu hình theo vị trí và quyền; **object** là dữ liệu cùng các thuộc tính liên quan; **key** là định danh của object trong bucket. Với **general purpose bucket**, key có thể chứa dấu `/` để mô phỏng thư mục, nhưng namespace về bản chất là **phẳng**.

Amazon S3 hiện cung cấp **strong read-after-write consistency** cho việc ghi mới, ghi đè, xóa và liệt kê object: sau phản hồi thành công, GET/LIST bắt đầu sau đó phản ánh trạng thái mới, nếu không có hoạt động cạnh tranh. Mỗi object là một đơn vị atomic; **không có giao dịch đa key tự động**. Khi thiết kế hệ thống thực tế, phải bổ sung cơ chế xử lý ghi đồng thời, versioning, cache, replication, IAM, chi phí và phục hồi dữ liệu phù hợp với nghiệp vụ.

### Tài liệu AWS chính thức

- [What is Amazon S3? — Data consistency model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel) — strong read-after-write cho PUT, DELETE, GET/LIST và giới hạn cập nhật nhiều key.
- [General purpose buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingBucket.html) — khái niệm bucket và cấu hình chung.
- [Naming Amazon S3 objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html) — key, prefix, delimiter, độ dài và ký tự.
- [Listing object keys programmatically](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ListingKeysUsingAPIs.html) — `ListObjectsV2`, prefix và phân trang.
- [Working with directory buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/directory-buckets-overview.html) — namespace phân cấp và các khác biệt so với general purpose bucket.
- [How to prevent object overwrites with conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) — `If-None-Match`, `If-Match` và tình huống cạnh tranh.
- [How S3 Versioning works](https://docs.aws.amazon.com/AmazonS3/latest/userguide/versioning-workflows.html) — version ID, noncurrent versions và delete markers.
- [Uploading objects using multipart upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — hoàn tất upload và quản lý các part.
- [S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — IAM, Block Public Access và quản trị bucket.
- [Replicating objects within and across Regions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html) — sao chép dữ liệu và những điều cần kiểm tra trong DR.
- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — cách kết hợp S3 với pipeline bất đồng bộ.
