# Multipart upload, checksum và tối ưu truyền dữ liệu trong Amazon S3

Khi một ứng dụng tải tệp vài kilobyte lên Amazon S3, thao tác `PutObject` thường đủ đơn giản. Nhưng nếu phải chuyển video 30 GiB từ máy người dùng, bản sao lưu 2 TiB từ EC2 hoặc hàng nghìn tệp qua đường truyền không ổn định, việc gửi toàn bộ nội dung bằng một request duy nhất gây khó khăn: lỗi mạng ở cuối quá trình có thể buộc tải lại từ đầu, không tận dụng hết băng thông và khó kiểm tra tính toàn vẹn của dữ liệu.

**Multipart upload** cho phép tách một object lớn thành nhiều **part**, tải từng part độc lập hoặc song song, thử lại đúng part bị lỗi rồi hoàn tất để Amazon S3 ghép thành một object. **Checksum** giúp phát hiện lỗi dữ liệu trong quá trình truyền hoặc khi đối chiếu dữ liệu đã lưu. **Tối ưu truyền dữ liệu** là việc điều chỉnh part size, concurrency, vùng mạng, giao thức, retry và công cụ đo lường để cân bằng tốc độ, độ ổn định, độ an toàn và chi phí.

Bài học thuộc chương **Lưu trữ đối tượng S3** của mô-đun **CLOUD_PROVIDERS_AWS**. Những kỹ thuật này hữu ích khi ứng dụng Java/Spring Boot trên EC2, ECS, EKS hoặc Lambda chuyển dữ liệu sang S3; khi hệ thống tích hợp RDS, sự kiện và serverless cần tiếp nhận file; hoặc khi thiết kế backup, giám sát và phục hồi trên nhiều AWS account/Region.

> **Nguyên tắc:** Chọn multipart cho dữ liệu đủ lớn và yêu cầu truyền tin cậy; dùng checksum phù hợp để kiểm tra đúng **nội dung**; dọn những multipart upload chưa hoàn tất; và tối ưu bằng số đo thực tế thay vì luôn tăng số request song song.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vòng đời `CreateMultipartUpload → UploadPart → CompleteMultipartUpload`, vai trò `UploadId`, `PartNumber` và hành vi `AbortMultipartUpload`.
2. Nêu giới hạn kích thước object, số part, kích thước part và cách chọn part size.
3. Phân biệt `ETag` với checksum, đồng thời hiểu `FULL_OBJECT` và `COMPOSITE`.
4. Chọn được CRC64NVME, CRC32C, SHA256 hoặc thuật toán khác theo mục tiêu và khả năng hỗ trợ của API.
5. Sử dụng AWS CLI để upload tự động, xem checksum, kiểm tra multipart upload còn dang dở và cấu hình thông số hiệu năng.
6. Hiểu cách AWS SDK for Java 2.x `S3TransferManager` quản lý upload lớn, concurrency và credentials.
7. Đưa ra giải pháp cho timeout, `SlowDown`, `BadDigest`, lỗi quyền IAM/KMS và object chưa xuất hiện sau upload part.
8. Đánh giá độ an toàn, độ bền dữ liệu, chi phí request/transfer, vị trí Region và dọn multipart upload thất bại.

## 2. Object storage và lý do multipart upload hữu ích

Một S3 object được định danh bởi **bucket** và **object key** trong bucket đó. Bucket gắn với một AWS Region; object được lưu cùng dữ liệu và metadata như content type, mã hóa, storage class và checksum. S3 không cần cấp phát một filesystem disk trước như EBS, nhưng ứng dụng phải hiểu cơ chế object-level API và quyền IAM.

Có hai phương án upload cơ bản:

| Tiêu chí | Single-part `PutObject` | Multipart upload |
|---|---|---|
| Số lần gửi dữ liệu | Một request chứa object | Nhiều `UploadPart`, ghép bằng `CompleteMultipartUpload` |
| Retry khi lỗi giữa chừng | Thường phải gửi lại request object | Gửi lại part lỗi, giữ các part đã thành công |
| Tận dụng song song | Một đường upload logic | Có thể upload nhiều part song song |
| Quản lý phiên | Không có UploadId riêng | Có `UploadId`, danh sách part và thao tác complete/abort |
| Checksum | Full-object checksum | Full-object hoặc composite checksum tùy thuật toán |
| Chi phí quản lý | Ít request | Nhiều request và parts tạm thời có thể bị tính phí |
| Thích hợp | File nhỏ, thao tác đơn giản | File lớn, mạng không ổn định, yêu cầu throughput cao |

**Khuyến nghị AWS:** Khi kích thước object đạt khoảng **100 MB**, nên cân nhắc multipart. Đây là ngưỡng gợi ý về thiết kế, **không phải** kích thước tối thiểu bắt buộc của multipart; AWS CLI và SDK có thể tự chọn ngưỡng thấp hơn.

### 2.1. Minh họa một file 600 MiB

Giả sử upload một tệp 600 MiB, chọn part size 100 MiB:

~~~mermaid
flowchart TD
    F["Tệp gốc 600 MiB"] --> P1["Part 1: 100 MiB"]
    F --> P2["Part 2: 100 MiB"]
    F --> P3["Part 3: 100 MiB"]
    F --> P4["Part 4: 100 MiB"]
    F --> P5["Part 5: 100 MiB"]
    F --> P6["Part 6: 100 MiB"]
    P1 --> S["Amazon S3 - UploadId"]
    P2 --> S
    P3 --> S
    P4 --> S
    P5 --> S
    P6 --> S
    S --> C["CompleteMultipartUpload"]
    C --> O["Một object với key đã chọn"]
~~~

Nếu part 4 thất bại vì đứt mạng, client **không cần** gửi lại năm part khác đã được S3 nhận thành công. Nó retry part 4, rồi chỉ hoàn tất khi đã biết đầy đủ part đã upload.

Điều này khác với việc **tạo sáu object riêng**: trước khi complete, các part được quản lý dưới một multipart upload ID. Sau complete, ứng dụng truy cập qua **một key**.

## 3. Vòng đời API và trạng thái của multipart upload

### 3.1. Khởi tạo: `CreateMultipartUpload`

Client gửi yêu cầu gồm bucket, key, storage class (nếu có), metadata, Content-Type, chế độ mã hóa, checksum algorithm/type và các thuộc tính khác. S3 trả về **`UploadId`** để phân biệt phiên upload đang diễn ra.

Trong cùng bucket/key, có thể tồn tại nhiều multipart uploads **chưa hoàn tất** với các UploadId khác nhau. Key không phải khóa mutex: cần cơ chế kiểm soát ghi đè nếu nhiều producer upload cùng key.

Các metadata và cách mã hóa thường được quyết định ở **thời điểm initiate**. Nếu muốn đổi những thông tin quan trọng sau khi đã upload nhiều part, thường phải khởi tạo multipart upload mới hoặc thực hiện copy/update metadata theo quy trình thích hợp.

### 3.2. Gửi dữ liệu: `UploadPart`

Với mỗi part:

- Client gửi `Bucket`, `Key`, `UploadId`, `PartNumber` (1–10.000), bytes của part và checksum/thông số cần thiết.
- S3 phản hồi **ETag của part** và có thể trả checksum của part.
- Part có thể được upload **không theo thứ tự**, giúp concurrency.
- Nếu upload lại **cùng PartNumber trong cùng UploadId**, S3 **thay thế** nội dung part số đó đã tải trước.

Client cần giữ bảng ánh xạ **PartNumber → ETag, checksum cần thiết**, đặc biệt nếu tự xây luồng multipart API. Upload thành công một số part **chưa tạo object hoàn chỉnh** có thể `GetObject` qua key như bình thường.

### 3.3. Kết thúc: `CompleteMultipartUpload`

Khi đủ part, client gửi danh sách part/ETag theo **thứ tự part number tăng dần**, kèm checksum khi chế độ checksum yêu cầu. S3 xác minh và ghép dữ liệu thành object cuối cùng. Từ lúc complete thành công, object có thể được truy cập như object S3 thông thường với mô hình **strong read-after-write consistency** của S3.

**Phân biệt upload thành công và upload hoàn tất:** nhận HTTP 200 ở từng `UploadPart` chỉ chứng minh part đó được S3 nhận. Chỉ khi `CompleteMultipartUpload` thành công object mới hoàn chỉnh. API complete có trường hợp phản hồi HTTP 200 lúc bắt đầu xử lý rồi chứa thông tin lỗi trong body; SDK AWS xử lý tình huống này. Nếu tự viết HTTP client, phải **parse toàn bộ response body**, không chỉ nhìn status code.

### 3.4. Hủy phiên: `AbortMultipartUpload`

Khi không còn cần upload, gọi `AbortMultipartUpload` bằng đúng bucket, key và UploadId để giải phóng các part đã upload.

Một số upload part **đang bay** có thể hoàn tất ngay sau khi yêu cầu abort được gửi; ứng dụng cần dừng các worker đang upload trước, và nếu cần bảo đảm dọn sạch, kiểm tra lại danh sách part/abort theo hướng dẫn API. S3 tính phí lưu trữ các part từ lúc tải lên cho đến khi **complete hoặc abort** thực sự giải phóng chúng.

~~~mermaid
sequenceDiagram
    participant C as Client / Transfer Manager
    participant S as Amazon S3
    C->>S: CreateMultipartUpload (bucket, key, checksum)
    S-->>C: UploadId
    par Nhiều part
        C->>S: UploadPart #1
        S-->>C: ETag / checksum #1
    and
        C->>S: UploadPart #2
        S-->>C: ETag / checksum #2
    and
        C->>S: UploadPart #3
        S-->>C: ETag / checksum #3
    end
    alt Tất cả part hợp lệ
        C->>S: CompleteMultipartUpload (parts, ETags, checksums)
        S-->>C: Object / VersionId / checksum
    else Hủy hoặc lỗi không thể phục hồi
        C->>S: AbortMultipartUpload
        S-->>C: Giải phóng parts sau khi hoàn tất cleanup
    end
~~~

## 4. Các giới hạn cần nhớ trước khi chia part

Theo tài liệu AWS S3 multipart hiện hành cho general purpose buckets:

| Giới hạn | Giá trị |
|---|---:|
| Object size tối đa | **48,8 TiB** (xấp xỉ 50 TB theo cách ghi thập phân) |
| Số part tối đa trong một upload | **10.000** |
| PartNumber hợp lệ | **1 đến 10.000** |
| Kích thước **mỗi part trừ part cuối** | Từ **5 MiB** đến **5 GiB** |
| Kích thước part cuối | Có thể **nhỏ hơn 5 MiB** |
| `ListParts` trả về tối đa mỗi trang | **1.000 part** |
| `ListMultipartUploads` trả về tối đa mỗi trang | **1.000 upload** |

Giới hạn có thể khác ở các loại bucket/công cụ đặc biệt. Khi thực hành hãy phân biệt **MB, MiB, GB, GiB, TB và TiB**; 1 MiB = 1.048.576 bytes, trong khi 1 MB = 1.000.000 bytes.

### 4.1. Công thức chọn part size

Gọi:

- `F`: số bytes của object.
- `P`: số bytes cho mỗi part thông thường.
- `N = ceil(F/P)`: số part sẽ gửi.

Cần:

\[
N = \left\lceil \frac{F}{P} \right\rceil \leq 10{,}000
\]

và `5 MiB ≤ P ≤ 5 GiB` cho mọi part không cuối; part cuối có thể ngắn hơn.

**Ví dụ 2 TiB:** nếu chọn part size 64 MiB, `2 TiB = 2.097.152 MiB`, nên `N = 2.097.152/64 = 32.768` part, **vượt giới hạn**. Chọn `256 MiB` sẽ có `8.192` part, hợp lệ. Ngoài phép tính, cần cân bằng số request, bộ nhớ, retry cost và đường truyền.

| Dung lượng tệp | Part size minh họa | Số part gần đúng | Nhận xét |
|---|---:|---:|---|
| 600 MiB | 100 MiB | 6 | Dễ kiểm soát retry |
| 10 GiB | 64 MiB | 160 | Cho phép concurrency hợp lý |
| 100 GiB | 128 MiB | 800 | Cần theo dõi throughput |
| 2 TiB | 64 MiB | 32.768 | **Không hợp lệ** |
| 2 TiB | 256 MiB | 8.192 | Hợp lệ về số part |
| 10 TiB | 1 GiB | 10.240 | **Không hợp lệ** |
| 10 TiB | 2 GiB | 5.120 | Hợp lệ về số part |

Giá trị trong bảng là **ví dụ để tính toán**, không phải preset phù hợp với mọi mạng. Chọn part size cần tính đến RAM (nhất là khi nhiều part được buffer đồng thời), network latency, timeout và số lượng file.

### 4.2. Part number và composite checksum

Mặc dù API cho phép upload các part với số thứ tự không liên tiếp khi đang gửi, **khi sử dụng composite/part-level checksum, danh sách part để complete phải liên tiếp và bắt đầu từ 1**. AWS cảnh báo complete với part number không liên tiếp trong cơ chế này có thể trả lỗi `HTTP 500 Internal Server Error`.

Quy tắc vận hành tốt: đánh số part **1, 2, 3, ...**, giữ metadata cho từng part, gửi part list theo thứ tự tăng dần và validate số lượng trước khi complete.

## 5. Checksum là gì và kiểm tra được điều gì?

Checksum là giá trị tính từ bytes dữ liệu bằng một thuật toán xác định. Trong đường truyền, phía client có thể tính checksum trước/gần lúc upload; S3 tính lại trên dữ liệu nhận và so sánh. Nếu khác nhau, S3 trả lỗi thay vì lưu object hỏng.

Checksum trả lời câu hỏi **“bytes nhận được có phù hợp với bytes đã đưa vào phép tính không?”**. Nó không tự chứng minh ai tạo dữ liệu, không thay thế TLS, IAM policy, mã hóa hoặc chữ ký số đáng tin cậy.

### 5.1. Các thuật toán thường gặp

| Thuật toán | Đặc điểm | Gợi ý dùng |
|---|---|---|
| `CRC64NVME` | CRC 64-bit, là checksum mặc định do S3 chọn khi không có checksum được chỉ định | Kiểm tra toàn vẹn nhanh, hỗ trợ full-object checksum cho multipart |
| `CRC32` | CRC 32-bit, nhanh | Kiểm tra lỗi truyền dữ liệu, không phải hash chống giả mạo |
| `CRC32C` | CRC 32-bit polynomial Castagnoli, tối ưu trên nhiều CPU | Kiểm tra nhanh, tương thích full-object/composite trong multipart |
| `SHA1` | Cryptographic hash cũ, có rủi ro va chạm | Chỉ dùng khi cần tương thích; không dùng để bảo đảm chống giả mạo |
| `SHA256` | Cryptographic hash 256-bit | So sánh nội dung với digest độc lập, composite trong multipart S3 |
| `MD5` | Hash cũ, không còn phù hợp làm chứng thực bảo mật | Một số luồng tương thích/kiểm tra dữ liệu legacy |
| `SHA512`, `XXHASH64`, `XXHASH3`, `XXHASH128` | Thuật toán bổ sung được S3 hỗ trợ tùy API/version | Chọn theo yêu cầu checksum và loại kết quả được hỗ trợ |

**Lưu ý:** SHA256 được dùng ở nhiều hệ thống để lập manifest/digest độc lập. Nhưng checksum `SHA256` trả từ S3 cho một **multipart upload dạng `COMPOSITE`** không nhất thiết bằng lệnh `sha256sum` của **toàn bộ file**. Muốn so sánh theo giá trị toàn file, cần dùng **full-object checksum phù hợp** hoặc tự quản lý một digest SHA256 toàn file độc lập trong manifest/metadata và so sánh sau khi tải về.

### 5.2. S3 tự kiểm tra integrity

Công cụ AWS được cập nhật thường tính checksum trước hoặc trong lúc upload, S3 tính độc lập để xác nhận. Nếu không chỉ định thuật toán và SDK không cung cấp checksum, S3 áp dụng mặc định `CRC64NVME` theo tài liệu hiện hành.

Giá trị checksum có thể được lưu như metadata object và được trả qua `HeadObject` hoặc `GetObjectAttributes` khi operation và quyền đáp ứng điều kiện. Việc **có checksum S3** giúp xác minh dữ liệu trên đường truyền, nhưng để chứng minh dữ liệu vẫn đúng với một nguồn ban đầu từ hệ thống khác, phải giữ **digest nguồn tin cậy** và biết hai bên dùng cùng thuật toán/cách tính.

## 6. Full-object checksum và composite checksum

Đây là phân biệt quan trọng nhất khi dùng multipart với checksum.

### 6.1. `FULL_OBJECT`

**Full-object checksum** được tính trên **toàn bộ byte stream của object**, từ byte đầu tới byte cuối. Với multipart, S3 hỗ trợ full-object checksum cho các thuật toán CRC có thể kết hợp toán học từ checksum các phần mà không phải đọc lại toàn bộ payload:

- `CRC64NVME`.
- `CRC32`.
- `CRC32C`.

Khi client truyền giá trị full-object checksum phù hợp (và object size theo API), S3 đối chiếu trong giai đoạn complete. Nếu không khớp, có thể nhận `BadDigest`.

### 6.2. `COMPOSITE`

**Composite checksum** được hình thành từ checksum **của từng part**, sau đó tính giá trị tổng hợp theo quy tắc thuật toán. Nó có thể kiểm tra integrity từng phần tốt, nhưng **không đồng nghĩa** với một checksum được tính bằng cách chạy thuật toán trực tiếp trên toàn bộ file.

Ví dụ: object gồm ba part có checksum SHA256 riêng. Giá trị `ChecksumSHA256` của S3 ở loại `COMPOSITE` được tổng hợp từ các part-level digests, không trùng với `sha256sum whole-file.bin` trong trường hợp tổng quát.

### 6.3. Tổ hợp được hỗ trợ

| Thuật toán | Full-object multipart | Composite multipart |
|---|---|---|
| `CRC64NVME` | Có | **Không** |
| `CRC32` | Có | Có |
| `CRC32C` | Có | Có |
| `SHA1` | Không | Có |
| `SHA256` | Không | Có |
| `MD5` | Không | Có |
| `SHA512` và các `XXHASH*` | Không | Có |

Ở single-part `PutObject`, checksum thuộc loại full-object. Trong multipart, chọn **checksum algorithm và checksum type từ bước `CreateMultipartUpload`** và đảm bảo các phần/upload/complete nhất quán. Một số thuật toán mới còn yêu cầu bắt buộc khai báo thuật toán ngay ở bước khởi tạo để Complete request được chấp nhận.

### 6.4. Một ví dụ kiểm thử đúng và sai

Giả sử file `backup.bin` do nhà sản xuất gửi kèm manifest `sha256=...`:

- Nếu client tải bằng single-part với `SHA256`, có thể so sánh trực tiếp full-file digest theo cách tính phù hợp.
- Nếu tải bằng multipart và S3 có `ChecksumSHA256` loại `COMPOSITE`, **không được** so chuỗi checksum đó trực tiếp với SHA256 của manifest rồi kết luận hỏng.
- Để xác minh manifest SHA256, có thể tải lại file và tính SHA256 toàn file, hoặc dùng **S3 Batch Operations Compute checksum** khi phù hợp rồi đối chiếu kết quả full-object, hoặc lưu manifest digest do nguồn độc lập tạo và có quy trình xác minh tương ứng.
- Nếu mục tiêu chủ yếu là integrity của **đường truyền multipart**, `CRC64NVME FULL_OBJECT` hoặc `CRC32C FULL_OBJECT` là lựa chọn thực dụng.

## 7. ETag không phải luôn là MD5 của object

**ETag** là entity tag dùng cho nhận diện phiên bản nội dung và hỗ trợ điều kiện HTTP. Một ETag có thể trông như chuỗi hash, nhưng không nên suy ra rằng nó **luôn** bằng MD5 của toàn bộ bytes.

| Trường hợp | ETag có thể bằng MD5 của toàn object? |
|---|---|
| Single-part `PutObject` trong điều kiện được AWS tài liệu hóa, ví dụ SSE-S3 | Có thể |
| Multipart upload | **Không** |
| Một số chế độ mã hóa/copy | Không được giả định |
| Thao tác ghi với công cụ thay đổi part boundaries | ETag có thể khác dù object bytes tương đương |

Với multipart upload, ETag cuối thường có hậu tố dạng `-N`, ví dụ:

~~~text
"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-8"
~~~

`8` thường cho biết số part được dùng để ghép object. ETag không phải một phép chứng minh integrity chuẩn cho file ở mọi trường hợp. Ứng dụng cần checksum **nêu rõ thuật toán, kiểu checksum, versionId/ETag và nguồn digest**, tránh gọi chung “MD5 của S3”.

**Quan trọng:** Chỉ xem `ETag` mà không đọc `ChecksumType` có thể dẫn đến kết luận sai. Một object được multipart upload rồi copy bằng cách khác có thể được S3 lưu với ETag/checksum biểu diễn khác mặc dù bytes nội dung không đổi.

## 8. Làm việc với AWS CLI: high-level transfer tự quản lý multipart

### 8.1. Chuẩn bị môi trường

Ví dụ bên dưới dùng AWS CLI v2, IAM Identity Center profile tên `dev` và một **bucket được quản trị viên cấp quyền**, nằm tại Region `ap-southeast-1`. Thay `amzn-s3-demo-bucket` bằng tên bucket thật trước khi thực thi.

Kiểm tra danh tính và vị trí bucket:

~~~bash
aws --version
aws sts get-caller-identity --profile dev

aws s3api get-bucket-location \
  --bucket amzn-s3-demo-bucket \
  --profile dev
~~~

Lưu ý: `GetBucketLocation` có thể trả `null` cho bucket ở `us-east-1` do quy ước lịch sử API. Khi cần đối chiếu Region, sử dụng `HeadBucket` theo hướng dẫn SDK/CLI và account có quyền.

### 8.2. Tải file bằng `aws s3 cp`

~~~bash
# Tác động thật: upload file và phát sinh phí theo AWS pricing.
aws s3 cp "./large-video.mp4" \
  "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" \
  --region ap-southeast-1 \
  --profile dev \
  --checksum-algorithm CRC64NVME
~~~

Công cụ high-level `aws s3 cp` sẽ tự chọn single-part/multipart tùy ngưỡng cấu hình, chia file, upload song song, retry các part cần thiết và hoàn tất object. Nó tiện hơn nhiều so với tự gọi `s3api create-multipart-upload` cho công việc thường ngày.

Nếu dùng PowerShell trên Windows, ví dụ cùng thao tác viết **một dòng** để tránh cú pháp continuation khác Bash:

~~~powershell
aws s3 cp ".\large-video.mp4" "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" --region ap-southeast-1 --profile dev --checksum-algorithm CRC64NVME
~~~

### 8.3. Tải xuống và kiểm tra checksum

~~~bash
aws s3 cp \
  "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" \
  "./large-video-downloaded.mp4" \
  --region ap-southeast-1 \
  --profile dev \
  --checksum-mode ENABLED
~~~

Tùy loại object/checksum, CLI có thể lấy checksum và xác minh. Đây vẫn là thao tác **đọc dữ liệu có thể phát sinh phí transfer/GET**. Muốn có bằng chứng end-to-end từ hệ thống nguồn, hãy so sánh checksum nguồn và file tải về bằng cùng thuật toán, ví dụ:

~~~bash
# Chạy trong Bash hoặc môi trường có sha256sum
sha256sum large-video.mp4
sha256sum large-video-downloaded.mp4
~~~

Nếu hai file khác nhau, cần tìm nguyên nhân; nếu digest khớp, dữ liệu hai file khớp theo SHA256. Không nhầm giá trị này với `ChecksumSHA256` kiểu composite trả từ S3.

### 8.4. Xem metadata và checksum mà không tải toàn object

~~~bash
aws s3api head-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/large-video.mp4 \
  --checksum-mode ENABLED \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Bytes:ContentLength,ETag:ETag,ChecksumCRC64NVME:ChecksumCRC64NVME,ChecksumType:ChecksumType,VersionId:VersionId}' \
  --output json

aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/large-video.mp4 \
  --object-attributes ETag Checksum ObjectSize ObjectParts \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Các lệnh trên cần quyền tương ứng, ví dụ `s3:GetObject`/`s3:GetObjectAttributes` (và KMS permissions khi dùng SSE-KMS theo cấu hình). Không phải mọi object đều có checksum tương ứng trường đang hỏi; trường có thể không xuất hiện. `ObjectParts` có phân trang và metadata phụ thuộc cách object được upload.

## 9. Tinh chỉnh AWS CLI để tối ưu tốc độ và tài nguyên

AWS CLI high-level S3 commands có các tham số cấu hình riêng:

| Tham số | Mặc định theo hướng dẫn CLI hiện hành | Tác dụng |
|---|---|---|
| `multipart_threshold` | `8MB` | Kích thước file bắt đầu dùng multipart |
| `multipart_chunksize` | `8MB` | Kích thước part; tối thiểu `5MB` cho upload |
| `max_concurrent_requests` | `10` | Số request truyền dữ liệu chạy đồng thời |
| `max_queue_size` | `1000` | Số công việc transfer có thể xếp hàng; ảnh hưởng RAM/hiển thị tiến độ |
| `max_bandwidth` | Không giới hạn riêng theo cấu hình mặc định | Giới hạn tốc độ upload/download theo băng thông |
| `use_accelerate_endpoint` | `false` | Sử dụng S3 Transfer Acceleration khi bucket hỗ trợ |

Đây là giá trị mặc định của AWS CLI tại thời điểm tài liệu được tra cứu, **không phải** cam kết hiệu năng và có thể thay đổi theo phiên bản. Không nhầm `multipart_threshold` của CLI với giới hạn part S3 API.

### 9.1. Ví dụ cấu hình một profile

~~~ini
[profile dev]
region = ap-southeast-1
output = json
s3 =
    multipart_threshold = 64MB
    multipart_chunksize = 32MB
    max_concurrent_requests = 12
    max_queue_size = 1000
    max_bandwidth = 80MB/s
~~~

*Đây là đoạn cấu hình minh họa, không bắt buộc phải áp dụng.* Trong `~/.aws/config`, cấu hình các tham số bên dưới khóa `s3` với đúng mức thụt lề. Có thể dùng CLI để cấu hình theo từng profile:

~~~bash
# Tác động đến cấu hình CLI cục bộ của profile 'dev', không đổi bucket.
aws configure set s3.multipart_threshold 64MB --profile dev
aws configure set s3.multipart_chunksize 32MB --profile dev
aws configure set s3.max_concurrent_requests 12 --profile dev
aws configure set s3.max_bandwidth 80MB/s --profile dev
~~~

Không nên thay cấu hình profile người dùng thật khi chưa hiểu tác động; việc tối ưu phải dựa trên benchmark tại môi trường của mình.

### 9.2. Tăng concurrency có luôn tăng throughput?

Không. Với network 50 Mbps, tăng từ 10 lên 100 request có thể chỉ làm tăng tranh chấp băng thông, RAM và timeout. Một công thức xấp xỉ thông lượng truyền tối đa do đường mạng:

\[
T_{\max} \approx \frac{B_{\text{effective}}}{8}
\]

Nếu `B_effective = 80 Mbps`, mức lý thuyết khoảng `10 MB/s` trước khi trừ overhead của TCP/TLS, client và disk. Upload 10 GiB khó thể hoàn thành trong vài giây dù có 100 part parallel.

Một số bottleneck phổ biến:

- CPU bị tiêu tốn khi checksum/mã hóa/compression.
- RAM bị chiếm bởi part buffers và queue.
- Network throughput/latency, proxy hoặc kết nối ra Internet.
- Giới hạn IOPS của ổ đĩa nguồn, nhất là trên EC2/EBS.
- KMS request rate, S3 API request patterns, proxy connections và retry overhead.
- Chi phí request tăng theo số part không cần thiết.

### 9.3. Chọn part size theo mạng

- Part quá **nhỏ**: nhiều `UploadPart`, tăng overhead/request count và dễ vượt 10.000 part.
- Part quá **lớn**: retry thất bại phải gửi lại nhiều bytes, tiêu tốn RAM nếu buffer nhiều part, có nguy cơ timeout trên mạng yếu.
- Concurrency quá **thấp**: chưa tận dụng được uplink.
- Concurrency quá **cao**: quá tải CPU/RAM/network, dễ gặp `503 SlowDown` hoặc timeout.

Bắt đầu với cấu hình mặc định, đo tốc độ và tỷ lệ lỗi, sau đó thay đổi **một biến mỗi lần**. Ví dụ với file 100 GiB, có thể thử 64 MiB rồi 128 MiB part size với 8/16 concurrent requests và ghi kết quả thực tế. Không áp dụng một “part size tối ưu tuyệt đối” cho mọi hệ thống.

## 10. AWS SDK for Java 2.x và S3 Transfer Manager

Với ứng dụng Java/Spring Boot, không nên tự quản lý low-level multipart nếu mục tiêu chỉ là chuyển tệp. AWS SDK for Java 2.x cung cấp **`S3TransferManager`**, có thể sử dụng S3 async client với multipart support để tự xử lý phân part, concurrency, retry, complete và theo dõi tiến độ.

### 10.1. Chuẩn bị dependency

Sử dụng AWS SDK for Java 2.x đồng bộ phiên bản thông qua BOM. Ít nhất cần các module phù hợp:

~~~xml
<!-- Ví dụ dependency bên trong pom.xml của ứng dụng -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3-transfer-manager</artifactId>
</dependency>
~~~

Cần quản lý phiên bản trong `dependencyManagement` của dự án (ví dụ AWS SDK BOM); không chắp vá các version khác nhau. Nếu dùng **CRT-based S3 client**, cần dependency/runtime theo hướng dẫn chính thức của AWS; đoạn bên dưới minh họa Java-based async client.

### 10.2. Ví dụ upload file theo cách high-level

~~~java
import java.nio.file.Path;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

public class UploadLargeObject {
    public static void main(String[] args) {
        try (S3AsyncClient s3 = S3AsyncClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .multipartEnabled(true)
                .build();
             S3TransferManager tm = S3TransferManager.builder()
                .s3Client(s3)
                .build()) {

            UploadFileRequest req = UploadFileRequest.builder()
                    .putObjectRequest(p -> p
                            .bucket("amzn-s3-demo-bucket")
                            .key("uploads/archive.bin"))
                    .source(Path.of("archive.bin"))
                    .build();

            var upload = tm.uploadFile(req);
            var done = upload.completionFuture().join();
            System.out.println("Upload completed: " +
                    done.response().eTag());
        }
    }
}
~~~

**Đây là code thực hiện upload thật nếu chạy với bucket/credentials hợp lệ.** `S3AsyncClient` và Transfer Manager nên được khởi tạo/tái sử dụng có kiểm soát trong ứng dụng server thay vì tạo client mới trên mọi HTTP request.

AWS SDK v2 dùng default credentials provider chain (IAM Identity Center profile trên máy phát triển, IAM role trên EC2, ECS task role, IRSA/Pod Identity trên EKS, Lambda execution role…). Không ghi access key/secret key vào source code.

### 10.3. Những điều Java service cần thiết kế thêm

1. **Idempotency:** dùng object key có định danh upload/job duy nhất hoặc cơ chế conditional write để tránh user retry làm ghi đè object ngoài ý muốn.
2. **Progress và cancel:** ghi nhận trạng thái job, tiến độ, thất bại; khi hủy cần bảo đảm multipart upload bỏ dở được dọn.
3. **Memory pressure:** giới hạn số upload đồng thời; upload 20 file lớn cùng lúc có thể vượt budget RAM dù từng file đã chia part.
4. **Time-out và retry:** để SDK xử lý retry thông thường; custom retry cần exponential backoff + jitter, tránh bắn dồn request.
5. **Checksum/metadata:** chọn thuật toán và content type theo yêu cầu; kiểm tra checksum/object size khi hoàn tất.
6. **Transaction workflow:** chỉ đánh dấu record database `READY` sau khi đã xác nhận S3 object hoàn tất. Nếu DB commit thất bại sau S3 upload, cần quy trình dọn object mồ côi hoặc reconcile.
7. **Security:** role chỉ được `s3:PutObject` trên prefix được cấp, quyền KMS nếu cần; không mở bucket public.

Với Spring Boot xử lý upload qua web, tránh giữ toàn bộ tệp vào heap; sử dụng streaming hoặc temp file theo giới hạn upload, kiểm tra MIME/virus theo chính sách và dùng asynchronous job cho tệp lớn. Nếu client ở Internet, có thể thiết kế **presigned URLs** để browser/mobile upload parts trực tiếp lên S3, giảm tải trên server API.

## 11. Khi cần low-level multipart API

Thông thường SDK/CLI high-level là lựa chọn tốt nhất. Tuy nhiên, hiểu API giúp kiểm tra log, retry ở mức part hoặc tích hợp với client tự phát triển.

### 11.1. Khởi tạo multipart upload thủ công

~~~bash
# MINH HỌA CÓ TÁC ĐỘNG THẬT - cần quyền và bucket cho phép.
aws s3api create-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --checksum-algorithm SHA256 \
  --checksum-type COMPOSITE \
  --profile dev \
  --region ap-southeast-1
~~~

Phản hồi có `UploadId`. Đặt metadata/chế độ mã hóa ngay lúc này. Không chia sẻ UploadId công khai nếu nó giúp kết hợp với quyền của principal để tác động tới một upload đang diễn ra.

### 11.2. Upload parts

~~~bash
# Thay UPLOAD_ID và các file bằng dữ liệu thật trong môi trường lab.
aws s3api upload-part \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --part-number 1 \
  --body part-001.bin \
  --checksum-algorithm SHA256 \
  --profile dev \
  --region ap-southeast-1
~~~

Lặp lại với `part-number 2, 3, ...`, lưu **ETag** và **ChecksumSHA256** trả về cho từng part. Trong ví dụ này, dùng `COMPOSITE` với `SHA256`, số part khi complete phải **liên tiếp từ 1**.

### 11.3. Complete và abort

Với AWS CLI, `complete-multipart-upload` cần JSON chứa danh sách các part theo đúng thứ tự. Ví dụ **nội dung minh họa** của `complete-parts.json` (ETag/checksum placeholder, không dùng nguyên văn):

~~~json
{
  "Parts": [
    {
      "PartNumber": 1,
      "ETag": "\"EXAMPLE_ETAG_1\"",
      "ChecksumSHA256": "EXAMPLE_BASE64_PART_CHECKSUM_1"
    },
    {
      "PartNumber": 2,
      "ETag": "\"EXAMPLE_ETAG_2\"",
      "ChecksumSHA256": "EXAMPLE_BASE64_PART_CHECKSUM_2"
    }
  ]
}
~~~

Sau khi điền kết quả **thật** của mỗi part và xác minh đầy đủ:

~~~bash
# Tác động thật: hoàn tất object nếu tất cả dữ liệu/metadata hợp lệ.
aws s3api complete-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --multipart-upload file://complete-parts.json \
  --checksum-type COMPOSITE \
  --profile dev \
  --region ap-southeast-1

# Nếu đã quyết định hủy thay vì hoàn tất:
aws s3api abort-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --profile dev \
  --region ap-southeast-1
~~~

**Không** vừa complete vừa abort cùng một UploadId. Trước một workflow thực, hãy dùng SDK/high-level transfer nếu có thể; thao tác thủ công dễ tạo upload dở dang và tính phí nếu quên cleanup. Chú ý khác biệt giữa **JSON quoting** trong Bash và PowerShell, đặc biệt khi dùng `--multipart-upload` inline; `file://...` thường rõ ràng hơn.

## 12. Các lệnh chỉ đọc để kiểm tra multipart và checksum

Không cần upload mới để luyện tập các lệnh sau, miễn là account có bucket/object thực tế để xem và được cấp quyền thích hợp.

### 12.1. Liệt kê upload chưa hoàn tất

~~~bash
aws s3api list-multipart-uploads \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Uploads[].{Key:Key,UploadId:UploadId,Initiated:Initiated,StorageClass:StorageClass}' \
  --output table
~~~

Danh sách có thể rỗng nếu không có upload dở dang. Lệnh này cần quyền `s3:ListBucketMultipartUploads` trên bucket. Kết quả có phân trang; khi cần kiểm toán toàn bộ không dùng `--no-paginate` hoặc cắt `--max-items` mà quên đọc token tiếp theo.

### 12.2. Liệt kê part của một upload

~~~bash
aws s3api list-parts \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Parts[].{PartNumber:PartNumber,Bytes:Size,ETag:ETag}' \
  --output table
~~~

Cần quyền `s3:ListMultipartUploadParts` tương ứng. S3 có thể trả nhiều trang nếu vượt 1.000 part, nên cần hiểu phân trang. `ListParts` phản ánh upload chưa complete; sau complete, dùng `GetObjectAttributes` để xem metadata phần đã hoàn tất khi được hỗ trợ.

### 12.3. Kiểm tra object đã hoàn tất

~~~bash
aws s3api head-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --checksum-mode ENABLED \
  --profile dev \
  --region ap-southeast-1

aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --object-attributes ETag ObjectSize Checksum ObjectParts \
  --profile dev \
  --region ap-southeast-1
~~~

Nếu kết quả `NoSuchKey`, phân biệt chưa complete, sai key, sai bucket/account hoặc lỗi truy cập bị che dưới mã HTTP. Nếu object dùng SSE-KMS, việc yêu cầu checksum có thể cần quyền KMS đặc biệt; không tắt mã hóa để “lấy checksum dễ hơn”.

## 13. Kiểm soát chi phí của multipart upload chưa hoàn tất

### 13.1. Vì sao phần upload dở dang bị tính phí?

Từ khi part đầu tiên được upload, S3 có dữ liệu cần lưu. Nếu client bị tắt máy sau khi tải 95% của file 100 GiB nhưng **không complete hoặc abort**, các part còn lại vẫn tồn tại trong hệ thống S3 theo UploadId và **có thể bị tính phí lưu trữ, request, truyền dữ liệu**. Không nhìn thấy object ở giao diện thông thường không đồng nghĩa không còn dữ liệu tính phí.

### 13.2. Lifecycle rule `AbortIncompleteMultipartUpload`

Có thể cấu hình **S3 Lifecycle** trên bucket để tự hủy các multipart upload chưa hoàn tất sau số ngày kể từ khi initiate. Ví dụ cấu trúc JSON minh họa:

~~~json
{
  "Rules": [
    {
      "ID": "AbortIncompleteMultipartUploadsAfter7Days",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
~~~

Đây là **một rule mẫu**, chưa phải toàn bộ lifecycle policy của bucket. **Không dùng `put-bucket-lifecycle-configuration` ghi đè policy thật** nếu chưa đọc và hợp nhất các rules hiện có; API ghi toàn cấu hình lifecycle. Hãy để IaC/owner bucket quản lý.

Kiểm tra chính sách hiện có bằng lệnh chỉ đọc:

~~~bash
aws s3api get-bucket-lifecycle-configuration \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1
~~~

Chọn thời hạn sau khi biết tốc độ upload tối đa của hệ thống. Nếu upload hợp lệ cần hơn 7 ngày mà rule hủy sau 7 ngày, tác vụ có thể bị hủy giữa chừng. Mặt khác, quá dài sẽ tăng phí storage cho upload thất bại.

### 13.3. Chi phí nhiều lớp

| Thành phần | Có thể phát sinh phí |
|---|---|
| `CreateMultipartUpload` / `UploadPart` / `CompleteMultipartUpload` | API requests theo storage class/Region |
| Các part chưa hoàn tất | Dung lượng lưu trữ tạm tới khi complete/abort, theo quy định storage class |
| Object đã hoàn tất | Dung lượng lưu trữ, các lớp storage và minimum storage duration (nếu áp dụng) |
| Data transfer | Truyền từ S3 ra ngoài, liên Region, liên AZ hoặc đường truyền tùy cấu hình |
| S3 Transfer Acceleration | Phụ phí khi sử dụng accelerated endpoint đủ điều kiện |
| KMS | Số lượt gọi AWS KMS và khóa KMS nếu có |
| CloudWatch/logging | Metrics, logs, audit, tracing và các dịch vụ giám sát khác |

Việc **abort incomplete upload** theo lifecycle không có early deletion charge cho các incomplete parts; nhưng không coi toàn bộ lưu trữ/operations đã phát sinh trước đó là miễn phí. Với storage classes Glacier, phí part đang upload có quy tắc staging riêng.

## 14. Hiệu năng mạng: cùng Region, parallelism và byte-range

### 14.1. Đặt client gần bucket khi có thể

Với ứng dụng trên EC2/ECS/EKS:

- Nếu service và bucket cùng Region, latency và data transfer paths thường thuận lợi hơn so với truyền nhiều dữ liệu cross-Region.
- Với VPC private subnets, cân nhắc **S3 Gateway VPC Endpoint** để dùng đường truy cập S3 qua hạ tầng AWS mà không phải đi qua NAT Gateway cho luồng S3 tương ứng, khi route/policy/Region cho phép.
- Cấu hình endpoint policy, bucket policy, IAM role và KMS key policy theo đúng yêu cầu; endpoint không tự cấp quyền bucket.
- Nếu dùng NAT Gateway để lên public S3 endpoint, lượng data processing có thể tăng chi phí; benchmark mô hình được cấp phép trước khi tối ưu.

### 14.2. Parallel upload và parallel download

Multipart upload chia part song song để tăng thông lượng tổng hợp. Ở chiều download, có thể dùng **`GetObject` với header `Range: bytes=start-end`** hoặc tải nhiều part/range đồng thời khi công cụ hỗ trợ. S3 Transfer Manager có thể dùng byte-range fetches.

Ví dụ đọc 1 MiB đầu của object (trả về file, không in dữ liệu nhị phân vào terminal):

~~~bash
aws s3api get-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --range bytes=0-1048575 \
  --profile dev \
  --region ap-southeast-1 \
  first-megabyte.bin
~~~

Dữ liệu thực sự trả về từ object; phải có quyền đọc và có thể có phí GET/data transfer. Không dùng lệnh `head-object` để kỳ vọng nó trả payload.

### 14.3. Ưu tiên đo lường

Một vòng benchmark có thể ghi:

- **Throughput:** bytes thành công / thời gian.
- **P50/P95/P99 upload part latency**, tỷ lệ retry và HTTP 503.
- **Network utilization** trên EC2/host và proxy.
- **CPU/RAM**, disk read throughput, EBS throttling.
- **Request count**, KMS API count, giá transfer, số part chưa dọn.

Với 100 GiB upload, nếu 8 concurrent workers đạt 450 MB/s nhưng 32 workers chỉ đạt 460 MB/s và tăng retry 4 lần, cấu hình 8 workers có thể hiệu quả hơn về tổng chi phí và độ ổn định.

## 15. S3 Transfer Acceleration và trường hợp nên dùng

**Amazon S3 Transfer Acceleration** dùng mạng edge của AWS/CloudFront để tối ưu đường truyền **khoảng cách xa** từ client Internet tới S3 general purpose bucket. Khi bật trên bucket tương thích, client dùng endpoint dạng:

~~~text
bucket-name.s3-accelerate.amazonaws.com
~~~

Nếu cần dual-stack IPv4/IPv6, có dạng:

~~~text
bucket-name.s3-accelerate.dualstack.amazonaws.com
~~~

Điều kiện:

1. Bucket nằm trong Region có hỗ trợ Transfer Acceleration.
2. Chủ bucket hoặc principal được ủy quyền đã bật feature.
3. Bucket name tương thích DNS và **không có dấu chấm**.
4. Client/công cụ dùng accelerated endpoint đúng cách.
5. Doanh nghiệp chấp nhận phụ phí nếu lưu lượng đủ điều kiện.

S3 Transfer Acceleration **không luôn nhanh hơn** đường chuẩn, nhất là khi client đã ở cùng Region hoặc đường kết nối đã tối ưu. AWS có **Speed Comparison tool** để đo từ vị trí sử dụng. Bật feature rồi chờ AWS áp dụng có thể mất thời gian; không kết luận ngay từ một lần thử.

CLI có thể cấu hình:

~~~bash
# Thay đổi config profile cục bộ; bucket phải được enable trước.
aws configure set s3.use_accelerate_endpoint true --profile dev
~~~

Dùng `Transfer Acceleration` cho client xa Region, ví dụ người dùng ở nhiều quốc gia upload file lớn vào một bucket được quản lý tập trung. Nếu dữ liệu lưu trên EC2 cùng Region, **truy cập trực tiếp S3 với endpoint thích hợp** thường là điểm xuất phát hợp lý hơn.

## 16. Bảo mật: IAM, KMS và chống ghi đè

### 16.1. Quyền cần thiết tùy thao tác

| Thao tác | IAM action thường liên quan |
|---|---|
| Tải object / multipart upload | `s3:PutObject` trên object ARN của prefix được cấp |
| Xem multipart upload trong bucket | `s3:ListBucketMultipartUploads` trên bucket ARN |
| Xem các part đang upload | `s3:ListMultipartUploadParts` |
| Hủy multipart upload | `s3:AbortMultipartUpload` |
| Xem hoặc tải object | `s3:GetObject` (và `s3:GetObjectVersion` khi truy cập version cụ thể) |
| Xem thông tin checksum/object parts | `s3:GetObjectAttributes` hoặc quyền tương đương theo API |
| Quản lý bucket lifecycle | `s3:GetLifecycleConfiguration` / `s3:PutLifecycleConfiguration` |

Quyền phải được giới hạn đúng **bucket/prefix** và chịu bucket policy, SCP, permissions boundary cùng các guardrail khác. Với multipart SSE-KMS, cần các quyền **AWS KMS** thích hợp như `kms:GenerateDataKey` và `kms:Decrypt` theo từng giai đoạn. Nếu upload part thành công nhưng complete/đọc checksum bị AccessDenied, cần kiểm tra **cả IAM S3 và KMS key policy/permissions**.

### 16.2. Mã hóa và toàn vẹn là hai lớp khác nhau

- **TLS (HTTPS):** bảo vệ đường truyền khỏi nghe lén/đổi dữ liệu trên mạng.
- **SSE-S3 hoặc SSE-KMS:** mã hóa dữ liệu khi lưu tại S3.
- **Checksum:** kiểm tra bytes dữ liệu, không tự xác thực danh tính nguồn.
- **IAM/bucket policy:** quyết định ai được upload/đọc/ghi đè.
- **S3 Object Lock/versioning:** có thể giảm tác hại khi ghi đè/xóa theo chính sách, nhưng cần thiết kế và quản trị độc lập.

Không bật public read/write cho bucket chỉ để app upload dễ hơn. Ứng dụng frontend có thể dùng **presigned URL** có thời hạn ngắn và scope chặt để tải phần dữ liệu trực tiếp, kết hợp API backend điều phối `UploadId`, part numbers, checksum và complete. Server phải kiểm soát quyền user tạo upload, file size, content type, key/prefix và cleanup.

### 16.3. Bảo vệ tránh ghi đè object cùng key

Nếu nhiều clients cùng tải lên `exports/report.zip`, việc complete upload sau cùng có thể thay thế object đang ở key đó theo versioning/conditional writes. Các chiến lược:

- Dùng key duy nhất, chẳng hạn `uploads/{job-id}/report.zip` (đây là cách đặt key minh họa).
- Dùng `If-None-Match: *` tại thời điểm `CompleteMultipartUpload` khi API hỗ trợ để chỉ tạo object nếu key chưa tồn tại.
- Bật versioning nếu yêu cầu quản lý các phiên bản dữ liệu, kết hợp quyền và lifecycle đúng.
- Lưu tham chiếu `VersionId` hoặc ETag/checksum trong cơ sở dữ liệu để xử lý idempotency.

Tránh khẳng định rằng multipart chỉ có một UploadId trên mỗi key; S3 có thể có nhiều upload đang diễn ra cùng một key.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `EntityTooSmall` khi complete | Một part không cuối nhỏ hơn 5 MiB | Kiểm tra part boundaries/size; upload lại part hợp lệ |
| `InvalidPart` | ETag sai, part chưa tồn tại hoặc UploadId/key không khớp | `ListParts`, xác minh UploadId và ETags thật |
| `InvalidPartOrder` | Danh sách complete không theo thứ tự tăng dần | Sắp xếp PartNumber trước khi complete |
| HTTP 500 khi complete composite | Part numbers không liên tiếp/bắt đầu từ 1, hoặc lỗi tạm thời | Kiểm tra numbering, docs checksum và retries |
| `BadDigest` | Checksum không khớp dữ liệu S3 nhận | Tính lại checksum, chọn đúng FULL_OBJECT/COMPOSITE, kiểm tra encoding Base64 |
| `AccessDenied` khi upload/complete | IAM bucket/KMS policy không đủ | Đối chiếu action của từng giai đoạn, bucket/prefix, KMS |
| `NoSuchUpload` | UploadId đã complete/abort, hết hạn hoặc key sai | Kiểm tra trạng thái và ID, không retry mù quáng |
| `NoSuchKey` khi tải dù đã gửi parts | Chưa gọi `CompleteMultipartUpload` thành công | Xem kết quả complete, `HeadObject`/`GetObjectAttributes` |
| `503 SlowDown` | Request rate tăng nhanh, client quá nhiều request hoặc S3 đang scale | Exponential backoff + jitter, giảm concurrency, đo lại |
| Transfer hay timeout/`Connection reset` | Mạng/proxy không ổn định, part quá lớn | Retry part, cân nhắc giảm part size/concurrency, tăng timeout hợp lý |
| Upload xong ETag khác local MD5 | Multipart/SSE/copy | Dùng checksum được xác định đúng thuật toán và loại |
| Checksum SHA256 S3 khác `sha256sum` | S3 dùng `COMPOSITE`, local là full-file digest | So sánh cùng loại hoặc dùng full-object checksum/manifest độc lập |
| Chi phí storage tăng nhưng ít object | Nhiều multipart uploads chưa hoàn tất | `ListMultipartUploads`, abort và lifecycle cleanup |
| Download chậm dù S3 khỏe | Client disk/CPU/network hoặc tải tuần tự | Benchmark parallel range GET, gần Region, kiểm tra NIC/EBS |
| Bật acceleration không nhanh hơn | Network gần bucket hoặc overhead/phí không đáng | Đo endpoint chuẩn vs accelerated và so sánh chi phí |
| SSE-KMS checksum/complete lỗi | Thiếu KMS permissions hoặc cấu hình key | Kiểm tra `kms:GenerateDataKey`/`kms:Decrypt`, key policy |

### 17.1. Quy trình xử lý theo thứ tự

1. Xác nhận **AWS account, IAM principal và Region/bucket** bằng CLI/Console.
2. Xác định **đã có object hoàn chỉnh** hay chỉ có multipart upload in-progress.
3. Kiểm tra `UploadId`, part list, ETags, checksum algorithm/type, số part và part sizes.
4. Đọc lỗi từ response body, AWS request ID/extended request ID khi có; tránh in tokens/credentials.
5. Kiểm tra quyền S3/KMS; chỉ mở đúng quyền cần, không tạm cấp wildcard admin.
6. Dùng SDK retry với backoff; nếu lỗi dữ liệu logic thì sửa dữ liệu/checksum, không retry vô hạn.
7. Khi hủy task, bảo đảm abort và kiểm tra cleanup; quan sát phí incomplete parts.
8. Tạo metric cho tốc độ, lỗi, retry, dung lượng incomplete uploads và chi phí.

## 18. Bài thực hành: so sánh một chiến lược upload lớn

### 18.1. Bối cảnh

Một service Java/Spring Boot chạy trên ECS nhận tệp camera từ người dùng tại nhiều quốc gia và lưu vào S3 bucket trong Region Singapore. Mỗi tệp 30 GiB; đường truyền client đôi khi mất kết nối. Hệ thống phải:

- Tránh tải lại cả tệp sau một lỗi part.
- Đảm bảo bytes đến S3 đúng với dữ liệu client đã gửi.
- Không để unfinished parts tích tụ làm tăng phí.
- Không dùng IAM access key dài hạn trong container.
- Cung cấp giám sát upload success/failure, retry và thời gian hoàn thành.

### 18.2. Thiết kế đề xuất

1. Backend xác thực user, chọn object key duy nhất và kiểm tra quota/kích thước cho phép.
2. Dùng multipart; ví dụ part size **64 MiB** cho file 30 GiB dẫn tới **480 part**, trong giới hạn.
3. Chọn checksum **CRC64NVME FULL_OBJECT** cho integrity S3; nếu cần digest SHA256 chứng minh nội dung gốc, giữ manifest SHA256 độc lập và có bước kiểm chứng đúng loại.
4. Sử dụng presigned `UploadPart` URLs theo thời hạn thích hợp hoặc upload qua service tích hợp S3TransferManager; tránh chuyển dữ liệu qua backend vô ích khi có thể.
5. Cho phép retry part, hạn chế số worker concurrent theo benchmark; lưu UploadId/parts/ETag cần thiết.
6. Gọi complete sau khi xác minh đủ parts; chỉ công bố object là `READY` trong DB khi complete và verify metadata thành công.
7. Có cleanup theo job state và Lifecycle `AbortIncompleteMultipartUpload` (ví dụ sau 7 ngày nếu phù hợp với SLA).
8. Dùng ECS task role + IAM least privilege, KMS permissions và TLS; theo dõi CloudWatch/CloudTrail/S3 metrics thích hợp.
9. Thử endpoint thường và Transfer Acceleration với client xa bucket; chọn dựa trên throughput, retry rate và chi phí.

### 18.3. Bài tập tính toán

**Bài A — Part size:** Nếu tệp 1,5 TiB và bạn chọn 32 MiB/part, số part là bao nhiêu? Có hợp lệ không? Chọn lại part size để không vượt 10.000 part.

Gợi ý:

\[
1.5\ \text{TiB} = 1{,}572{,}864\ \text{MiB}
\]

- `1.572.864 / 32 = 49.152` part, không hợp lệ.
- Chọn `256 MiB/part` sẽ có `6.144` part, hợp lệ.

**Bài B — Kiểm tra checksum:** Một object multipart có `ChecksumSHA256` và `ChecksumType = COMPOSITE`; client chạy `sha256sum` toàn file rồi thấy không khớp. Có thể kết luận dữ liệu hỏng không? Giải thích checksum type và cách chứng minh toàn file.

**Bài C — Chi phí:** Hệ thống có 100 phiên upload 10 GiB bị bỏ dở ở khoảng 80%. Ước tính khoảng **800 GiB** dữ liệu part chưa complete có thể đang được lưu và tính phí cho tới khi dọn. Nêu hai biện pháp ngăn tích tụ.

**Bài D — Hiệu năng:** Với đường truyền hiệu dụng 160 Mbps, thông lượng lý thuyết khoảng **20 MB/s**. Nếu upload 10 GiB một đường, thời gian tối thiểu do giới hạn băng thông ở mức khoảng **9 phút**, trước khi tính protocol overhead. Việc tăng từ 8 lên 64 workers có thể giảm thời gian xuống dưới 1 phút không? Vì sao?

### 18.4. Bộ lệnh lab chỉ đọc

Nếu có quyền đọc bucket thực tế, có thể chạy:

~~~bash
# 1. Kiểm tra tài khoản và principal
aws sts get-caller-identity --profile dev

# 2. Xem các multipart uploads còn dang dở
aws s3api list-multipart-uploads \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1 \
  --output json

# 3. Xem bucket lifecycle rule đã có
aws s3api get-bucket-lifecycle-configuration \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1

# 4. Đọc object metadata/checksum đã hoàn tất
aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --object-attributes ObjectSize ETag Checksum \
  --profile dev \
  --region ap-southeast-1
~~~

Nếu không có bucket/quyền, người học sử dụng output minh họa ở trên để phân tích; **không cần tạo tài nguyên AWS thật**. Các lệnh chỉ đọc có thể vẫn có request charges nhỏ tùy tài khoản và loại operation.

## 19. Câu hỏi tự kiểm tra

1. Multipart upload khác với tạo nhiều S3 objects riêng biệt như thế nào?
2. Các bước bắt buộc từ initiate tới object có thể `GetObject` là gì?
3. `UploadId` và `PartNumber` dùng để làm gì? Upload lại cùng part number có tác động gì?
4. Tại sao cần `CompleteMultipartUpload` và vì sao không chỉ nhìn HTTP 200 của `UploadPart`?
5. Tại sao phải có `AbortMultipartUpload` và lifecycle cleanup?
6. 5 MiB là giới hạn cho mọi part hay có ngoại lệ?
7. Tại sao file 2 TiB với 64 MiB/part không hợp lệ?
8. Khi nào `ETag` có thể khác MD5 toàn file?
9. `FULL_OBJECT` và `COMPOSITE` khác nhau thế nào?
10. Các thuật toán nào hỗ trợ full-object checksum với multipart S3?
11. Vì sao không nên so `ChecksumSHA256 COMPOSITE` với `sha256sum` toàn file?
12. Những tham số nào ảnh hưởng throughput trong AWS CLI `s3 cp`?
13. Khi tăng concurrency gây nhiều `SlowDown`, nên làm gì?
14. Tình huống nào phù hợp với S3 Transfer Acceleration hơn endpoint thông thường?
15. Vì sao SSE-KMS có thể làm hoàn tất multipart gặp lỗi dù upload part đã thành công?
16. Những quyền IAM nào cần cho việc list/abort multipart upload?
17. EC2/ECS và S3 cùng Region có thể tối ưu đường truyền bằng cách nào?
18. Vì sao S3 Transfer Manager thường hợp lý hơn tự triển khai low-level multipart trong Spring Boot?

### Đáp án định hướng

- **Multipart** có UploadId và nhiều part, chỉ sau complete mới thành một object.
- **Giới hạn cốt lõi:** tối đa 10.000 part, mỗi part không cuối từ 5 MiB tới 5 GiB; object tối đa khoảng 48,8 TiB.
- **Checksum:** dùng thuật toán và `ChecksumType` đồng nhất; ETag không phải chứng cứ MD5 toàn object cho multipart.
- **Tối ưu:** điều chỉnh part size, concurrency, retry/backoff, vị trí Region, đường mạng và transfer manager dựa trên benchmark.
- **Vận hành:** IAM/KMS đúng quyền, dọn unfinished parts, bảo vệ chống overwrite và theo dõi cả chi phí S3 lẫn data transfer.

## 20. Tài liệu AWS chính thức

1. [Uploading and copying objects using multipart upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — Luồng create/upload/complete/abort, retry và phí part dở dang.
2. [Amazon S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html) — Kích thước object/part và giới hạn 10.000 part.
3. [Checking object integrity for data uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html) — Checksum algorithms, full-object/composite và ETag.
4. [Checking object integrity in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html) — Truy xuất và xác minh checksum.
5. [AWS CLI S3 configuration](https://docs.aws.amazon.com/cli/latest/topic/s3-config.html) — Multipart threshold, part size, concurrency, bandwidth.
6. [AWS CLI `s3 cp`](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html) — Upload/download và các tùy chọn checksum.
7. [AWS CLI `get-object-attributes`](https://docs.aws.amazon.com/cli/latest/reference/s3api/get-object-attributes.html) — Object size, ETag, checksum, part metadata.
8. [S3 Transfer Manager for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/transfer-manager.html) — Upload/download song song.
9. [Performance guidelines for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html) — Benchmark, parallelism, range GET.
10. [Performance design patterns](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html) — Thông lượng, caching, retry và request patterns.
11. [S3 Transfer Acceleration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/transfer-acceleration.html) — Endpoint, điều kiện và chi phí.
12. [Abort incomplete multipart uploads using a lifecycle rule](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html) — Tự động dọn unfinished parts.
13. [CompleteMultipartUpload API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html) — Part list, errors và checksum.
14. [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) — Storage, requests, transfer và các phí liên quan.

> **Ghi nhớ:** **Upload part thành công chưa phải object đã sẵn sàng**. Thiết kế đúng cần quản lý UploadId, retry từng part, kiểm tra checksum **đúng thuật toán/kiểu**, complete rồi xác minh object, đồng thời dọn upload bị bỏ dở. Tốc độ tốt nhất đến từ part size, concurrency, network placement và retry được **đo lường thực tế**, kết hợp IAM/KMS, giám sát và quản trị chi phí.

