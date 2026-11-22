# So sánh GridFS với lưu tệp trong document hoặc object storage

Trong MongoDB, tệp đính kèm có thể là ảnh đại diện, PDF hợp đồng, báo cáo, bản ghi âm, video hoặc tài liệu được tạo tự động. Ba lựa chọn phổ biến là: nhúng bytes vào một BSON document, lưu bằng GridFS, hoặc lưu bytes ở object storage và chỉ giữ metadata trong MongoDB.

Ba lựa chọn đáp ứng các nhu cầu khác nhau. Binary trong document có lợi khi dữ liệu nhỏ và gắn chặt với record; GridFS có ích khi file lớn nhưng vẫn muốn quản lý bytes trong MongoDB; object storage thuận tiện cho phân phối media, CDN, lifecycle và lưu trữ file độc lập với database. Không có câu trả lời tối ưu nếu chỉ nhìn kích thước tệp.

Bài học thuộc chương **GridFS**, module **Database Engine Document MongoDB**, sẽ so sánh theo giới hạn 16 MiB, streaming, index/metadata, tính nhất quán, phiên bản, quyền truy cập, sao lưu/khôi phục, hiệu năng, tổng chi phí và quy trình xử lý lỗi. Phần cuối có ví dụ mongosh, Java Sync Driver, kiến trúc API, bài tập và checklist.

**Phạm vi:** GridFS là một quy ước lưu file thông qua MongoDB drivers. Object storage là lớp lưu bytes bên ngoài MongoDB, ví dụ một dịch vụ S3-compatible. Những ví dụ giả định phiên bản và topology hỗ trợ API đang dùng; không dùng file mẫu trong bài làm dữ liệu production.

## 1. Ba mô hình lưu file

### 1.1. Binary trực tiếp trong document

~~~javascript
{
  _id: "attachment-001",
  ownerId: "user-001",
  filename: "hello.txt",
  contentType: "text/plain",
  length: 5,
  data: BinData(0, "SGVsbG8="),
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

BinData biểu diễn BSON Binary. Base64 của chữ "Hello" ở đây chỉ giúp minh họa dữ liệu bytes trong shell; ứng dụng thường gửi byte array thực qua driver.

**Metadata và file bytes nằm trong cùng một document.** Điều này đơn giản cho dữ liệu nhỏ, nhưng toàn bộ BSON document bị giới hạn kích thước.

### 1.2. GridFS

~~~text
MongoDB database
  |
  +-- fs.files
  |    _id
  |    filename
  |    length
  |    chunkSize
  |    uploadDate
  |    metadata
  |
  +-- fs.chunks
       files_id, n=0, data=<bytes>
       files_id, n=1, data=<bytes>
       files_id, n=2, data=<bytes>
       ...
~~~

File được chia thành nhiều chunks. Mỗi chunk là BSON document có kích thước nhỏ, cho phép lưu file tổng thể vượt ngưỡng một document. GridFS driver cung cấp upload/download dạng stream.

### 1.3. Object storage và MongoDB metadata

~~~text
MongoDB attachments:
  _id = ATT-001
  ownerId = USER-001
  status = ready
  storage = {bucket, key, versionId}

Object storage:
  bucket = private-files
  key = tenant-a/ATT-001/v1
  content = file bytes
~~~

MongoDB chịu trách nhiệm record nghiệp vụ, metadata, quyền và trạng thái. Object storage giữ bytes và các tính năng phân phối/lifecycle theo dịch vụ.

## 2. Bảng so sánh tổng quan

| Tiêu chí | Nhúng BSON Binary | GridFS | Object storage |
| --- | --- | --- | --- |
| Vị trí bytes | Trong một MongoDB document | Nhiều MongoDB chunk documents | Dịch vụ ngoài MongoDB |
| File vượt 16 MiB | Không thể trong một document | Được bằng chunks | Được theo service limits |
| Streaming file lớn | Không thuận tiện | API driver hỗ trợ | API/HTTP thường hỗ trợ |
| Atomic bytes + metadata | Trong cùng document | Nhiều writes/docs | Hai hệ thống khác nhau |
| Query business metadata | Trực tiếp MongoDB | fs.files hoặc app collection | MongoDB metadata collection |
| Khả năng CDN | Cần gateway riêng | Cần gateway riêng | Thường có ecosystem thuận tiện |
| HTTP Range/multipart | Ứng dụng tự làm | Cần xử lý bổ sung | Thường có chức năng chuyên dụng |
| Bytes trong MongoDB backup | Có | Có | Không, phải backup riêng |
| Database footprint | Cả bytes và metadata | Cả bytes/chunks/indexes | Chủ yếu metadata |
| Phân quyền | MongoDB + backend | MongoDB + backend | Backend + object IAM/policies |
| Versioning | Application version | FileId mới | Object key/versionId |
| Lifecycle/archive | Application | Application | Có thể dùng storage policies |
| Ví dụ thường gặp | Tệp/thumbnail nhỏ | Tệp lớn lưu nội bộ | Video, PDF lớn, CDN |

**Kết luận sơ bộ:** Kích thước là điều kiện cần xem, nhưng tần suất đọc, quyền, retention, yêu cầu triển khai và tổng chi phí mới quyết định lựa chọn.

## 3. Giới hạn 16 MiB của BSON document

MongoDB thông thường giới hạn một BSON document tối đa **16 MiB**:

\[
16\ \mathrm{MiB}=16 \times 1024 \times 1024=16{,}777{,}216\ \text{bytes}
\]

Giới hạn tính **toàn bộ** document:

~~~text
_id
tenantId
filename
contentType
length
metadata
data bytes
BSON field names, type markers and overhead
~~~

### 3.1. File đúng 16 MiB vẫn không thể nhúng cùng metadata

Nếu bytes đã 16 MiB thì không còn chỗ cho fields khác và BSON overhead. Ứng dụng nên dùng giới hạn upload thấp hơn đủ nhiều, không nhắm chính xác ngưỡng 16 MiB.

### 3.2. Base64 string khác BSON Binary

Một HTTP API nhận:

~~~json
{"dataBase64":"SGVsbG8="}
~~~

có thể decode thành bytes. Nếu lưu nguyên chuỗi, document chịu overhead Base64 và field là String; nếu dùng BSON Binary thì field là binary bytes.

### 3.3. Khi nào dùng GridFS để vượt giới hạn?

Khi file không nhúng được mà tổ chức muốn lưu bytes trong MongoDB, **GridFS là cơ chế chuẩn**. Nếu đã có object storage tốt, vẫn cần so sánh trước khi quyết định.

### 3.4. Giới hạn tổng dữ liệu khác giới hạn một record

MongoDB có thể lưu rất nhiều file nhỏ ở nhiều documents, nhưng một document không được vượt 16 MiB. GridFS chia file thành nhiều documents để đáp ứng điều đó, không hủy giới hạn BSON.

## 4. Khi nào nhúng binary vào document?

Nhúng thường hợp lý nếu:

- File nhỏ và size được giới hạn.
- File được đọc cùng record nghiệp vụ.
- Muốn update bytes và metadata **nguyên tử trong cùng document**.
- Không cần stream một file khổng lồ.
- Không có yêu cầu CDN hoặc lifecycle độc lập.
- Tổng database footprint có thể kiểm soát.

Ví dụ một chữ ký nhỏ hoặc thumbnail:

~~~javascript
{
  _id: "avatar:user-001",
  userId: "user-001",
  version: 2,
  mimeType: "image/webp",
  data: BinData(0, "..."),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

### 4.1. Atomic update trong một document

~~~javascript
db.avatars.updateOne(
  {
    _id: "avatar:user-001",
    version: 2
  },
  {
    $set: {
      data: BinData(0, "SGVsbG8="),
      mimeType: "text/plain",
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
~~~

Trong ví dụ, bytes chỉ là chữ Hello, không phải ảnh WebP thật. Điểm minh họa là việc version, bytes và MIME field được cập nhật trong **một MongoDB document operation**.

### 4.2. Khi nào không nên nhúng dù file nhỏ?

- File tải rất thường xuyên từ Internet.
- File cần CDN/cache độc lập.
- Metadata được query thường xuyên nhưng bytes ít dùng.
- Số file cực nhiều, database storage/backup trở nên đắt.
- File cần versioning/lifecycle riêng.

**Một file 40 KiB tải một triệu lượt/ngày có thể phù hợp object storage + CDN hơn nhúng BSON.**

### 4.3. Dùng projection khi chỉ cần metadata

~~~javascript
db.avatars.find(
  {
    userId: "user-001"
  },
  {
    data: 0
  }
);
~~~

Tránh truyền bytes mỗi lần chỉ muốn hiện filename/status.

### 4.4. Quy định ngưỡng application-level

Ứng dụng có thể chọn tối đa 1 MiB cho binary nhúng. Đó là policy tùy workload, **không** phải giới hạn MongoDB thay cho 16 MiB.

## 5. GridFS là gì?

**GridFS** là quy ước lưu file bằng hai MongoDB collections: một collection metadata file và một collection chứa các chunks binary.

Bucket mặc định thường là **fs**, tương ứng:

~~~text
fs.files
fs.chunks
~~~

Có thể đặt bucket khác:

~~~text
attachments.files
attachments.chunks
reports.files
reports.chunks
~~~

### 5.1. GridFS không phải POSIX filesystem

Không tự có directory tree, path permissions, file locking, media streaming HTTP hay CDN. Nó là lớp lưu trữ file trên MongoDB collections và API driver.

### 5.2. Vì sao có thể lưu file lớn?

Một file dài được chia thành nhiều chunks; mỗi chunk là BSON document riêng. Vì thế file tổng thể lớn hơn 16 MiB mà không cần một document chứa toàn bộ bytes.

### 5.3. Nên dùng GridFS driver thay vì sửa collections thủ công

Driver xử lý chia/ghép chunks, numbering, upload/download. Việc insert/xóa trực tiếp fs.chunks có thể làm thiếu chunk, sai length hoặc hỏng file.

## 6. Metadata trong fs.files

Một record GridFS thường có dạng:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  filename: "contract.pdf",
  length: NumberLong(10485760),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  metadata: {
    ownerId: "user-001",
    tenantId: "tenant-a",
    contentType: "application/pdf",
    businessAttachmentId: "ATT-001"
  }
}
~~~

| Field | Vai trò |
| --- | --- |
| _id | GridFS file identity |
| filename | Tên gợi nhớ, có thể trùng |
| length | Tổng bytes |
| chunkSize | Kích thước chunks |
| uploadDate | Thời điểm upload |
| metadata | Dữ liệu tùy chọn của ứng dụng |

### 6.1. Filename không unique

Hai người dùng có thể cùng upload invoice.pdf, hoặc một tài liệu có nhiều versions cùng tên. **Không download hoặc delete dựa vào filename duy nhất.** Lưu fileId chính xác trong record nghiệp vụ.

### 6.2. Một application attachment record riêng

~~~javascript
{
  _id: "ATT-001",
  ownerId: "user-001",
  tenantId: "tenant-a",
  status: "ready",
  storageType: "gridfs",
  gridFsBucket: "attachments",
  gridFsFileId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

Bản ghi này kiểm soát quyền, version, trạng thái và liên kết tới order/customer mà không phải dựa toàn bộ vào fs.files.metadata.

### 6.3. Tránh trùng nguồn sự thật

Nếu ownerId và status được copy giữa app collection và fs.files.metadata, cần xác định đâu là nguồn chính và xử lý khi quyền thay đổi.

## 7. Chunk documents trong fs.chunks

Một chunk:

~~~javascript
{
  _id: ObjectId("507f191e810c19729de860ea"),
  files_id: ObjectId("507f1f77bcf86cd799439011"),
  n: 0,
  data: BinData(0, "...")
}
~~~

- **files_id** liên kết với file.
- **n** là thứ tự chunk từ 0.
- **data** là bytes của chunk.

### 7.1. Unique index quan trọng

GridFS sử dụng index:

~~~javascript
{
  files_id: 1,
  n: 1
}
~~~

với uniqueness để một file không có hai chunks cùng n.

### 7.2. File metadata index

Index theo filename và uploadDate thường được GridFS dùng để tìm file theo tên/thời gian. Business metadata có thể cần index thêm nếu ứng dụng query nhiều.

### 7.3. Không search nội dung PDF bằng query chunks

Chứa bytes PDF không có nghĩa MongoDB có thể trực tiếp tìm câu bên trong. Cần extract text và tạo text/vector index riêng.

## 8. Chunk size và chi phí chia file

GridFS thường có chunk size mặc định **255 KiB**:

\[
255 \times 1024 = 261{,}120\ \text{bytes}
\]

Nếu file có L bytes và chunk size C:

\[
N=\left\lceil \frac{L}{C}\right\rceil
\]

Ví dụ file 10 MiB thường cần khoảng **41 chunks** với kích thước trên.

### 8.1. Chunk cuối thường nhỏ hơn

Nếu L không chia hết C, chunk cuối có phần bytes còn lại. Không được bỏ chunk cuối chỉ vì nó không đủ kích thước.

### 8.2. File hàng gigabyte có nhiều chunk documents

Một file 1 GiB ở 255 KiB/chunk cần hơn bốn nghìn chunks. Điều này tăng document/index count và số thao tác backend.

### 8.3. Chunk lớn hơn không luôn tốt hơn

- Tăng chunk size có thể giảm number of chunks.
- Chunk lớn cũng thay đổi memory, retries và per-operation size.
- Chunk rất lớn vẫn phải tuân thủ giới hạn BSON document.

Benchmark với file sizes, concurrency và storage topology thực tế.

### 8.4. File rỗng

Một file length=0 có thể không có chunks; không tự xem là lỗi nếu ứng dụng cho phép file rỗng.

## 9. GridFS upload workflow

~~~text
InputStream
   |
   v
GridFS driver
   |
   +--> write chunk n=0
   +--> write chunk n=1
   +--> write chunk n=2
   |
   v
Write fs.files metadata
   |
   v
Return fileId
~~~

Thông thường driver ghi fs.files khi upload hoàn tất.

### 9.1. Upload bị lỗi giữa chừng

Có thể còn chunks chưa có fs.files tương ứng. Đây là một loại orphan/incomplete upload, cần cleanup cẩn thận.

### 9.2. Crash sau upload trước application metadata

File GridFS hoàn chỉnh có thể đã tồn tại nhưng application chưa kịp lưu fileId vào ATT-001. Retry thiếu idempotency có thể tạo file thứ hai.

### 9.3. Trạng thái ready

Chỉ mark ứng dụng attachment ready khi GridFS upload và validation tương ứng đã thành công. Nếu cần antivirus, giữ file trong quarantine/pending cho đến khi scan xong.

### 9.4. Không giả định atomicity trên mọi chunks

GridFS gồm nhiều writes/docs. Một upload không phải một single-document atomic operation. Dù backend dùng transaction ở chỗ khác, cần hiểu phạm vi hỗ trợ của driver và topology thay vì mặc định mọi thao tác file có transaction chung.

## 10. GridFS download workflow

~~~text
HTTP request ATT-001
      |
      v
Authenticate + authorize
      |
      v
Lookup attachment metadata
      |
      v
GridFS fileId
      |
      v
Driver đọc chunks theo n
      |
      v
OutputStream -> HTTP response
~~~

### 10.1. Streaming giảm memory usage

Có thể đọc tuần tự chunks mà không load toàn bộ file vào một byte[] lớn.

### 10.2. Backpressure và client chậm

Nếu downloader nhận chậm, application phải tránh buffer không giới hạn; cần stream cancellation, timeout và backpressure.

### 10.3. HTTP Range không tự có

Một GridFS stream không tự thực hiện đầy đủ các HTTP headers/range semantics. Ứng dụng có thể triển khai partial reads phù hợp driver, nhưng phải tự xử lý Range/206/If-Range đúng.

### 10.4. CDN cần lớp bổ sung

GridFS không tự phát public URL hoặc cache ở edge. Nếu tải media nhiều, object storage/CDN thường thuận tiện hơn.

## 11. Thay nội dung file GridFS

Một cách an toàn là **tạo fileId mới và đổi reference**.

~~~text
File version 1 -> GridFS ID A
File version 2 -> GridFS ID B
~~~

Quy trình:

1. Upload version 2 vào GridFS.
2. Verify length/checksum và policy.
3. Cập nhật business record từ A sang B có kiểm tra version.
4. Giữ A cho rollback/retention nếu cần.
5. Xóa A khi không còn reference hoặc hết retention.

### 11.1. Không sửa chunks trực tiếp

Nếu tự update một chunk, file có thể lệch length/ordering và những readers đang download có thể thấy bytes không nhất quán.

### 11.2. Atomic pointer switch

~~~javascript
db.attachments.updateOne(
  {
    _id: "ATT-001",
    activeVersion: 1
  },
  {
    $set: {
      activeVersion: 2,
      gridFsFileId: newFileId
    }
  }
);
~~~

Update business pointer trong một document có tính atomic, dù upload mới và cleanup cũ là những bước độc lập.

## 12. Xóa GridFS file

Dùng **GridFSBucket.delete(fileId)** thay vì xóa trực tiếp chỉ một collection.

### 12.1. Xóa fs.files mà giữ fs.chunks

Chunks còn chiếm storage nhưng không có file metadata hợp lệ.

### 12.2. Xóa fs.chunks mà giữ fs.files

File metadata còn tồn tại nhưng download có thể thiếu dữ liệu.

### 12.3. Failed delete

Vì nhiều documents liên quan, cần xử lý retry/reconciliation. Không mặc định delete luôn nguyên tử trong mọi tình huống lỗi.

### 12.4. Shared references

Nếu nhiều business records cùng tham chiếu fileId, không xóa bytes khi chỉ một reference bị gỡ. Cần ownership/reference policy.

## 13. Object storage hoạt động thế nào?

Object storage lưu dữ liệu bằng **bucket/container + object key**.

~~~text
Bucket: private-attachments
Key: tenant-a/contracts/ATT-001/v1
Bytes: <contents of contract.pdf>
~~~

MongoDB lưu metadata:

~~~javascript
{
  _id: "ATT-001",
  tenantId: "tenant-a",
  ownerId: "user-001",
  filename: "contract.pdf",
  contentType: "application/pdf",
  length: NumberLong(10485760),
  status: "ready",
  storage: {
    kind: "object",
    bucket: "private-attachments",
    key: "tenant-a/contracts/ATT-001/v1",
    versionId: "if-supported"
  }
}
~~~

### 13.1. Key không phải file path với POSIX semantics

Dấu slash trong object key thường chỉ là naming convention/prefix. Object storage không nhất thiết có thư mục thật.

### 13.2. Không lưu presigned URL làm reference vĩnh viễn

Presigned URL hết hạn. Lưu bucket/key/version ID, phát URL mới khi user đủ quyền.

### 13.3. Object metadata không thay business database

Một provider có object tags/metadata nhưng không thay thế MongoDB query theo orderId, ownerId, status, tenant hoặc authorization rules.

## 14. Upload object qua backend

~~~text
Client -> Application API -> Object storage
                        |
                        v
                  MongoDB metadata
~~~

Ưu điểm:

- Backend nhìn thấy bytes, dễ validate/scan.
- Có thể thực hiện các policy đồng bộ.

Nhược điểm:

- Application chịu toàn bộ upload bandwidth.
- File lớn và concurrent uploads gây tải.

Dùng streaming thay vì đọc toàn bộ file vào heap.

## 15. Direct upload bằng presigned URL

Một quy trình:

~~~text
Client -> Backend: request upload
Backend: authenticate + validate size/type
Backend -> MongoDB: create pending attachment
Backend -> Client: short-lived upload URL
Client -> Object storage: put/multipart
Client -> Backend: finalize request
Backend -> Object storage: verify
Backend -> MongoDB: mark ready
~~~

### 15.1. Không tin client báo upload thành công

Backend cần xác minh existence, byte size, checksum/file signature và scan policy nếu cần.

### 15.2. Scope và TTL

Presigned URL cần scope hẹp theo key/method/time. Không cấp một token cho phép ghi cả bucket.

### 15.3. Multipart

Object storage thường có multipart APIs cho file lớn. Nếu upload thất bại cần abort/cleanup incomplete parts theo provider.

### 15.4. Retry idempotent

Dùng stable attachment ID và upload attempt/version để tránh tạo duplicate object không cần thiết.

## 16. Download object và CDN

Có hai kiểu:

~~~text
Backend proxy:
Client -> App -> Object storage -> App -> Client

Direct signed download:
Client -> App (auth)
App -> Client (short-lived URL)
Client -> Object storage
~~~

### 16.1. CDN

Object storage thường tích hợp thuận tiện với CDN cho media đọc nhiều. Cache hit giúp giảm origin requests và latency.

### 16.2. Private objects

Không public bucket chứa hợp đồng cá nhân. Dùng private origin, signed URL/cookie, cache keys và expiration phù hợp.

### 16.3. Byte Range

Object storage thường hỗ trợ Range requests qua HTTP/SDK, thuận tiện cho media seeking và download resume.

### 16.4. Egress cost

Khi sử dụng object storage/CDN, theo dõi lưu lượng đi ra, cache hit và request charges; không chỉ nhìn chi phí lưu GB-tháng.

## 17. So sánh atomicity và consistency

### 17.1. Binary trong document

Nếu bytes và metadata cùng một document, một update có thể thay cả hai nguyên tử theo semantics của MongoDB.

### 17.2. GridFS

Bytes nằm trong nhiều chunk documents cộng file metadata; business record có thể là document thứ ba. Application cần trạng thái workflow và xử lý partial failures.

### 17.3. Object storage

Object put/delete nằm ngoài MongoDB transactions. Hai writes thành công/thất bại độc lập.

~~~text
MongoDB attachment update
            +
Object storage put
            !=
One automatic distributed transaction
~~~

### 17.4. State machine được đề xuất

~~~text
PENDING
   |
   v
UPLOADING
   |
   v
VERIFYING / SCANNING
   |
   +----> READY
   |
   +----> FAILED / RETRY

READY -> DELETING -> DELETED
~~~

Chỉ phục vụ files READY và thuộc quyền người dùng.

## 18. Thiết kế two-phase finalize

Reserve metadata:

~~~javascript
db.attachments.insertOne({
  _id: "ATT-001",
  tenantId: "tenant-a",
  ownerId: "user-001",
  storage: {
    kind: "object",
    bucket: "private-attachments",
    key: "tenant-a/ATT-001/v1"
  },
  status: "pending",
  createdAt: new Date()
});
~~~

Sau khi upload hoàn tất, backend verify rồi finalize:

~~~javascript
db.attachments.updateOne(
  {
    _id: "ATT-001",
    status: "pending"
  },
  {
    $set: {
      status: "ready",
      verifiedAt: new Date()
    }
  }
);
~~~

### 18.1. Failure sau upload trước finalize

Object đã tồn tại nhưng metadata vẫn pending. Reconciliation job có thể kiểm tra object theo stable key và tiếp tục finalize hoặc cleanup theo policy.

### 18.2. Failure trước upload

Metadata pending nhưng object chưa tồn tại. Sau timeout có thể retry hoặc mark failed; không trả download link.

### 18.3. Không tự chuyển pending thành ready theo thời gian

Thời gian chờ không chứng minh bytes đã upload đúng. Cần evidence từ storage service/backend validation.

## 19. Idempotency và duplicate uploads

Một request có thể upload thành công nhưng response mất trên network.

~~~text
Server put success
  |
  v
Response lost
  |
  v
Client retries
~~~

Nếu retry tạo fileId hoặc objectKey mới mỗi lần, có thể sinh duplicates.

### 19.1. Stable logical attachment ID

Tạo ATT-001 trước upload. Một lần retry của cùng operation phải có cách nhận diện ATT-001.

### 19.2. Upload attempt/version

Lưu attempt ID, version hoặc hash để phân biệt retry với một phiên bản nội dung hoàn toàn mới.

### 19.3. Conditional update

Khi finalize hoặc switch reference, kiểm tra expected version/status để không ghi đè state mới hơn.

### 19.4. Cleanup duplicates

Đừng xóa file chỉ vì trùng checksum nếu file có thể có multiple owners hoặc retention khác nhau. Cần chính sách ownership/reference.

## 20. Versioning trong ba mô hình

| Mô hình | Thay file thường theo cách |
| --- | --- |
| Embedded | Update field Binary + version trong document |
| GridFS | Upload fileId mới, đổi pointer |
| Object storage | Dùng key version mới hoặc provider versionId |

### 20.1. Immutable versions giúp rollback

~~~text
ATT-001/v1
ATT-001/v2
ATT-001/v3
~~~

Khi v3 gặp lỗi, hệ thống có thể trỏ lại v2 nếu còn được giữ và policy cho phép.

### 20.2. Không xóa bản cũ trước khi bản mới được verify

Nếu upload v2 fail mà v1 bị xóa trước, user mất file. Dùng verify → switch → grace period → cleanup.

### 20.3. Concurrent edits

Nếu user upload v3 trong lúc migration copy v2, migration worker không được đổi active pointer từ v3 về v2. Dùng document version/CAS.

## 21. Checksum và integrity

Có thể lưu:

~~~javascript
{
  length: NumberLong(1234567),
  sha256: "sha256-digest-of-exact-bytes"
}
~~~

### 21.1. MD5 legacy trong GridFS

Một số GridFS versions/APIs cũ có field md5 hoặc filemd5. Không xem đây là cơ chế xác thực bảo mật hiện đại hoặc mặc định luôn tồn tại.

### 21.2. ETag của object storage

ETag có thể khác MD5, nhất là multipart/encryption và tùy provider. Không thay thế SHA-256 chỉ vì provider trả ETag.

### 21.3. Checksum không thay authorization

SHA-256 giúp kiểm tra bytes, không chứng minh user có quyền truy cập hoặc tài liệu do nguồn tin cậy tạo ra. Nếu cần authenticity, có thể cần chữ ký/verification khác.

### 21.4. Khi nào cần verify?

Sau upload, sau migration, khi khôi phục từ backup hoặc theo integrity policy. Với file rất lớn, đo chi phí CPU/I/O.

## 22. Bảo mật và dữ liệu nhạy cảm

### 22.1. Binary/GridFS trong MongoDB

Sử dụng database RBAC, TLS, encryption, giới hạn direct DB access, backend ownership checks.

### 22.2. Object storage

Sử dụng private bucket, IAM least privilege, encryption at rest/TLS, scoped presigned URLs, audit logs.

### 22.3. ID khó đoán không phải permission

Một client biết GridFS fileId hoặc object key của tenant khác không có quyền xem chỉ vì biết chuỗi đó.

### 22.4. File type giả mạo

Không tin tên file .pdf, MIME do client gửi hay extension để quyết định an toàn. Kiểm tra bytes/signature và chính sách cho loại file được phép.

### 22.5. Malware scanning

~~~text
UPLOADED -> QUARANTINED -> SCAN
                              |
                              +-> CLEAN -> READY
                              |
                              +-> INFECTED -> REJECT
~~~

Nếu scanner timeout mà policy yêu cầu scan, file chưa được READY.

### 22.6. Caching private attachments

Không đưa private PDFs vào public CDN cache không có signed controls. Sử dụng Cache-Control/TTL/invalidation phù hợp.

## 23. HTTP file response

Khi tự phục vụ bytes qua backend, cần chuẩn bị headers:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
Content-Length: 1234567
Cache-Control: private, no-store
~~~

Đây là ví dụ, không phải chính sách cố định mọi tệp.

### 23.1. Sanitize filename

Filename do user nhập phải được encode/sanitize khi đưa vào HTTP headers để tránh header injection/path tricks.

### 23.2. Content-Disposition

inline cho phép hiển thị một số định dạng; attachment thường yêu cầu download. Với file không tin cậy, cần đánh giá XSS/active content risk trước khi inline.

### 23.3. Range

Chỉ trả status 206 khi server đã implement đúng byte ranges, If-Range, Content-Range và invalid ranges.

### 23.4. Cancellation

Dừng đọc stream khi client disconnect, không tiếp tục download file 2 GiB vào buffer không dùng.

## 24. Chi phí và capacity

### 24.1. Embedded và GridFS

Bytes đi vào MongoDB data storage, replication và backups.

Chi phí bao gồm:

- Primary/secondary disk.
- Network replication.
- Index overhead.
- Backup/snapshot.
- Restore time.
- Database CPU/I/O.
- Client download bandwidth qua DB/app.

### 24.2. GridFS chunk overhead

Mỗi file lớn có nhiều chunk docs và index entries. Chi phí lưu không chỉ tổng bytes mà còn số documents/operations.

### 24.3. Object storage

Chi phí có thể gồm GB-month, PUT/GET requests, multipart, egress, CDN, archive retrieval, cross-region replication, versioning.

### 24.4. Ví dụ ước lượng

~~~text
Stored bytes ~ sum(file sizes)
Monthly served bytes ~ requests * mean bytes transferred
Mongo replicated footprint ~ bytes * replica copies + overhead
~~~

Cần tính thêm peak traffic, backup, cross-region, CDN cache hits và giai đoạn migration.

### 24.5. Không có mô hình rẻ nhất tuyệt đối

Object storage có thể rẻ cho file lớn ít tải, nhưng egress nhiều cũng tốn. GridFS có thể phù hợp hệ thống nội bộ tận dụng MongoDB sẵn có, nhưng cần capacity và ảnh hưởng query latency.

## 25. Backup và disaster recovery

### 25.1. Nhúng

Bytes và metadata cùng MongoDB document. Backup/restore database bao gồm cả hai.

### 25.2. GridFS

Phải backup/restore **cả files và chunks collections**, cùng application attachment mappings. Backup chỉ fs.files không đủ phục hồi bytes.

### 25.3. Object storage

Metadata ở MongoDB và bytes ở object store. Có thể có hai lịch backup/retention khác nhau.

### 25.4. Restore lệch thời gian

~~~text
MongoDB restored at T1
Object storage current at T2
~~~

Có thể tạo orphan objects hoặc dangling references. Cần reconciliation sau DR.

### 25.5. RTO/RPO phải xét toàn hệ

Không thể chỉ đo MongoDB restore thành công; còn phải xác minh object references tải được và file permissions/versions còn đúng.

## 26. Metadata indexing

Với binary nhúng hoặc app attachments:

~~~javascript
db.attachments.createIndex({
  tenantId: 1,
  ownerId: 1,
  status: 1,
  createdAt: -1
});
~~~

Với GridFS metadata:

~~~javascript
db.fs.files.find(
  {
    "metadata.tenantId": "tenant-a",
    "metadata.businessAttachmentId": "ATT-001"
  },
  {
    filename: 1,
    length: 1,
    uploadDate: 1
  }
);
~~~

Nếu workload thường filter theo metadata, có thể cần index tương ứng ở fs.files hoặc app collection.

### 26.1. Tìm trong file không phải tìm metadata

PDF nằm trong GridFS/object storage không tự query được theo câu văn. Cần extraction/OCR (nếu cần), text index hoặc vector search.

### 26.2. Đừng tạo tất cả indexes theo cảm tính

Tạo index cho query patterns quan trọng rồi đo thực tế; mỗi index có storage/write cost.

## 27. Java Sync Driver: lưu Binary nhỏ

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;

import org.bson.Document;
import org.bson.types.Binary;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;

public class SaveSmallFile {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        Path path = Path.of("hello.txt");
        byte[] bytes = Files.readAllBytes(path);

        int applicationLimit = 1024 * 1024;

        if (bytes.length > applicationLimit) {
            throw new IllegalArgumentException(
                    "File quá lớn cho embedded storage"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> files =
                    client.getDatabase("file_lab")
                          .getCollection("smallFiles");

            files.insertOne(
                    new Document("_id", "hello-file")
                            .append("filename", "hello.txt")
                            .append("contentType", "text/plain")
                            .append("length", bytes.length)
                            .append("data", new Binary(bytes))
                            .append("createdAt", new Date())
            );
        }
    }
}
~~~

### 27.1. Memory

Files.readAllBytes() phù hợp file nhỏ đã giới hạn. Không dùng cho file lớn trong production.

### 27.2. Application limit là ví dụ

Một MiB chỉ là policy của ví dụ, không phải hard limit MongoDB.

## 28. Java Sync Driver: GridFS upload

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;

import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class UploadGridFS {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        Path path = Path.of("manual.pdf");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("file_lab");

            GridFSBucket bucket = GridFSBuckets.create(
                    db,
                    "attachments"
            );

            GridFSUploadOptions options =
                    new GridFSUploadOptions()
                            .chunkSizeBytes(255 * 1024)
                            .metadata(
                                    new Document(
                                            "tenantId",
                                            "tenant-a"
                                    ).append(
                                            "ownerId",
                                            "user-001"
                                    ).append(
                                            "contentType",
                                            "application/pdf"
                                    )
                            );

            try (InputStream source =
                         Files.newInputStream(path)) {

                ObjectId fileId = bucket.uploadFromStream(
                        path.getFileName().toString(),
                        source,
                        options
                );

                System.out.println(fileId);
            }
        }
    }
}
~~~

### 28.1. Bucket name

Bucket attachments dùng attachments.files và attachments.chunks, không phải fs.files/fs.chunks.

### 28.2. Returned fileId

Lưu fileId trong application record khi upload xong, có xử lý retry và authorization theo tenant.

### 28.3. Chunk size

255 KiB là cấu hình phổ biến; chỉ thay đổi sau khi benchmark.

## 29. Java Sync Driver: GridFS download

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

import org.bson.types.ObjectId;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DownloadGridFS {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        ObjectId fileId = new ObjectId(
                "507f1f77bcf86cd799439011"
        );

        try (MongoClient client = MongoClients.create(uri);
             OutputStream target = Files.newOutputStream(
                     Path.of("downloaded.pdf")
             )) {

            GridFSBucket bucket = GridFSBuckets.create(
                    client.getDatabase("file_lab"),
                    "attachments"
            );

            bucket.downloadToStream(fileId, target);
        }
    }
}
~~~

### 29.1. File ID minh họa

ObjectId trong code phải thay bằng giá trị thực do upload trả về.

### 29.2. HTTP endpoints phải check quyền

Đoạn code chỉ là thao tác download. Trong API thật, tải metadata trước, xác minh user có quyền rồi mới download.

### 29.3. Partial downloads

Nếu file destination mới chỉ ghi được một phần do lỗi mạng, cần xóa hoặc giữ như temporary file và verify trước khi coi thành công.

## 30. Java: metadata và xóa GridFS

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;

import org.bson.types.ObjectId;

public class GridFSOperations {

    public static GridFSFile find(
            GridFSBucket bucket,
            ObjectId fileId
    ) {
        return bucket.find(
                Filters.eq("_id", fileId)
        ).first();
    }

    public static void delete(
            GridFSBucket bucket,
            ObjectId fileId
    ) {
        bucket.delete(fileId);
    }
}
~~~

Trước khi delete, application phải kiểm tra retention, shared references, owner và trạng thái.

## 31. Abstraction cho cả ba storage backends

Một interface:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Map;

public interface FileStorage {

    StoredFile upload(
            String name,
            InputStream input,
            Map<String, String> metadata
    ) throws Exception;

    void download(
            StoredFile reference,
            OutputStream output
    ) throws Exception;

    void delete(
            StoredFile reference
    ) throws Exception;
}
~~~

~~~java
public record StoredFile(
        String kind,
        String storageId,
        String filename,
        String contentType,
        long length
) {}
~~~

Có thể triển khai:

~~~text
EmbeddedMongoStorage
GridFSStorage
ObjectStorageAdapter
~~~

### 31.1. Không che sự khác biệt

Một abstraction không nên giả định mọi backend đều có presigned URL, Range, atomic update, multipart hay versioning giống nhau.

### 31.2. Storage reference

Nên giữ kind và định danh bền vững (GridFS bucket/fileId hoặc object bucket/key/versionId), không chỉ filename hoặc URL tạm.

## 32. API download ổn định

Một endpoint:

~~~text
GET /attachments/ATT-001/content
~~~

Workflow:

1. Authenticate user.
2. Load attachment metadata từ MongoDB.
3. Check tenant/owner/status/ACL.
4. Resolve storage backend.
5. Download stream hoặc cấp signed URL theo policy.
6. Log access và metrics.

### 32.1. Không cho frontend tự gửi fileId để vượt quyền

FileId/ObjectId không phải access token. Backend phải kiểm tra quyền của ATT-001.

### 32.2. Thay backend không đổi API

Nếu storage metadata có kind và reference rõ, có thể chuyển dần từ GridFS sang object storage mà frontend vẫn gọi attachment API.

## 33. Migration: nhúng sang GridFS

Một quy trình:

1. Inventory file sizes và access patterns.
2. Chuẩn bị GridFS bucket/index/capacity.
3. Đọc binary source.
4. Upload bằng GridFS driver.
5. Verify length/checksum.
6. Update attachment reference với version check.
7. Đọc được cả embedded và GridFS trong giai đoạn chuyển đổi.
8. Monitor lỗi/download sample.
9. Giữ source cho rollback.
10. Cleanup bytes cũ sau khi xác nhận.

Không xóa bytes gốc trước khi upload mới được verify và reference đã switch.

## 34. Migration: GridFS sang object storage

~~~text
GridFS download stream
       |
       v
Object upload stream
       |
       v
Verify size + checksum
       |
       v
Switch MongoDB reference
       |
       v
Serve from object storage
       |
       v
Retire GridFS after grace period
~~~

### 34.1. Không đọc toàn bộ file vào RAM

Dùng streaming và multipart object upload khi cần.

### 34.2. Concurrency

Nếu source file được thay trong lúc migration, worker phải kiểm tra activeVersion trước khi switch.

### 34.3. Rollback

Giữ GridFS file gốc trong grace period tương ứng để rollback.

### 34.4. Orphan object

Upload object thành công nhưng switch thất bại có thể để lại object không được tham chiếu; cần reconciliation.

## 35. Migration ngược về GridFS

Khi policy yêu cầu file nằm trong MongoDB:

1. Tải đúng object version.
2. Stream vào GridFS.
3. Verify size/checksum.
4. Cập nhật reference có kiểm tra version.
5. Đọc qua GridFS.
6. Cleanup object cũ sau retention.

Không dựa vào presigned URL hết hạn làm nguồn dữ liệu bền vững.

## 36. Những trường hợp lựa chọn cụ thể

| Workload | Lựa chọn đáng cân nhắc | Lý do |
| --- | --- | --- |
| Avatar 12 KiB, traffic thấp | Nhúng BSON | Đơn giản, atomic cùng profile |
| Logo 50 KiB, triệu lượt xem | Object storage + CDN | Distribution/caching |
| Hợp đồng PDF 25 MiB | GridFS hoặc object | Vượt BSON limit, cần quyền/retention |
| Báo cáo nội bộ 100 MiB | GridFS | Stream trong MongoDB nếu capacity đủ |
| Video 2 GiB xem công khai | Object storage + CDN | Range, egress, media ecosystem |
| ZIP backup lớn lưu nhiều năm | Object storage/archive tier | Lifecycle và chi phí |
| Artifact JSON 100 KiB đi cùng record | Nhúng BSON | Có thể cập nhật atomic |
| File public rất nhỏ nhưng đọc liên tục | Object/CDN hoặc cache layer | Access pattern quan trọng hơn size |

Không coi bảng là quy tắc bắt buộc. Phải đánh giá deployment, chi phí mạng, SLA, tổ chức vận hành và yêu cầu compliance.

## 37. Vận hành và monitoring

Các metrics quan trọng:

- Upload success/failure rate.
- File size distribution P50/P95/max.
- Download P50/P95 latency và time to first byte.
- Concurrent streams.
- MongoDB disk, I/O, replica lag khi dùng GridFS.
- Chunks per file và orphan chunk count.
- Object storage egress/request charges.
- CDN hit/miss.
- Uploads pending quá hạn.
- Failed scans và checksum mismatches.
- Dangling references và orphan objects.
- Backup/restore duration.
- Delete/lifecycle processing errors.

### 37.1. Chỉ đo database latency là chưa đủ

Với HTTP file API phải đo tới khi client nhận bytes cuối, kể cả network chậm, Range requests và cancellation.

### 37.2. Orphan cleanup phải thận trọng

Trước khi xóa orphan candidate, cần grace period và tránh uploads đang hoạt động. Xóa nhầm có thể gây mất dữ liệu không phục hồi.

## 38. Các sai lầm phổ biến

| Sai lầm | Hệ quả |
| --- | --- |
| Nhúng file quá gần 16 MiB | BSON document vượt giới hạn |
| Lưu Base64 string thay BSON Binary | Overhead và sai schema |
| Query metadata mà không project bỏ bytes | Network/memory lớn |
| Dùng GridFS cho mọi thumbnail rất nhỏ | Overhead không cần |
| Xem GridFS là CDN | Thiếu HTTP distribution ecosystem |
| Chỉ backup fs.files | Không có chunks để khôi phục |
| Xóa fs.files thủ công | Orphan chunks |
| Xóa fs.chunks thủ công | File hỏng |
| Filename được xem là unique ID | Download/delete sai version |
| Mark ready trước verify | File rỗng/chưa upload được phục vụ |
| Upload bị crash không cleanup | Orphan storage |
| Download file lớn vào byte[] | Memory pressure |
| Retry luôn tạo fileId mới | Duplicate |
| Sửa chunks trực tiếp | Inconsistent file |
| Xóa file dùng chung | Mất dữ liệu của reference khác |
| Chỉ lưu presigned URL | Hết hạn, reference hỏng |
| Trust MIME từ client | Content nguy hiểm |
| ETag luôn được coi là MD5 | Kiểm tra integrity sai |
| Không kiểm tra user tenant | Lộ dữ liệu |
| Đưa private file lên public CDN | Rò rỉ dữ liệu |
| Backup chỉ MongoDB khi bytes ở object store | Disaster recovery thiếu file |
| Không có cleanup incomplete multipart | Storage leak |
| Xóa source trước target verify | Mất file |
| Tìm văn bản trong PDF bằng query chunks | Không có text index |
| Không đo egress | Chi phí bất ngờ |

## 39. Bài thực hành: lựa chọn mô hình

### Bài 1
Avatar 15 KiB lưu cùng profile, ít tải. Chọn nhúng, GridFS hay object storage và giải thích.

### Bài 2
PDF 20 MiB, ít truy cập và chỉ dùng nội bộ. So sánh GridFS với object storage.

### Bài 3
Video 3 GiB có nhiều người xem, cần CDN và HTTP Range. Chọn kiến trúc và nêu trade-off.

### Bài 4
Một ảnh 40 KiB được tải 1 triệu lượt/ngày. Vì sao dung lượng nhỏ không đủ để chọn nhúng BSON?

### Bài 5
Một JSON artifact 100 KiB phải cập nhật atomic cùng trạng thái báo cáo. Có cần GridFS không?

## 40. Bài thực hành: GridFS

### Bài 6
Tính số chunks cho file 10 MiB với chunk size 255 KiB. Chunk cuối có thể ngắn hơn chunkSize không?

### Bài 7
Giải thích vai trò fs.files, fs.chunks, files_id, n và unique index theo files_id/n.

### Bài 8
Worker upload crash sau 5 chunks nhưng chưa có fs.files. Các bytes còn lại ở đâu, cleanup thế nào?

### Bài 9
Hai người cùng upload invoice.pdf. Vì sao filename không đủ để chọn file chính xác?

### Bài 10
Thay file v1 bằng v2 trong GridFS nhưng vẫn cho rollback. Thiết kế các bước verify/switch/cleanup.

### Bài 11
Nếu chỉ xóa fs.files, điều gì có thể xảy ra? Nếu chỉ xóa fs.chunks thì sao?

### Bài 12
Viết Java Sync Driver dùng GridFSBucket.uploadFromStream và downloadToStream cho file lớn.

## 41. Bài thực hành: object storage và consistency

### Bài 13
Thiết kế direct upload bằng presigned URL, MongoDB pending record, backend verify rồi mark ready.

### Bài 14
Object upload đã thành công nhưng metadata vẫn pending. Thiết kế retry/reconcile an toàn.

### Bài 15
Vì sao không lưu presigned URL như storage ID bền vững? Nêu bucket/key/versionId.

### Bài 16
MongoDB restored tại T1, object storage tại T2. Có những orphan/dangling trường hợp nào?

### Bài 17
ETag có luôn là checksum MD5 không? Vì sao nên có contract SHA-256 riêng?

### Bài 18
User biết fileId của tenant khác. Endpoint download phải kiểm tra những gì?

### Bài 19
Hai business records dùng chung một fileId. Khi xóa một record, có thể xóa bytes ngay không?

### Bài 20
Thiết kế quarantine → scan → ready cho PDF upload và xử lý khi scanner timeout.

## 42. Bài thực hành: migration và chi phí

### Bài 21
Migration một triệu documents chứa binary sang GridFS. Viết kế hoạch dual-read, verify, rollback và cleanup.

### Bài 22
Migration từ GridFS sang object storage. Nêu stream copy, checksum verify và version checking.

### Bài 23
Một file được lưu trong MongoDB GridFS và có một triệu lượt download/tháng. Những thành phần TCO nào cần đo để so với object storage?

### Bài 24
Báo cáo PDF ở GridFS muốn hỗ trợ semantic search/trích dẫn trang. Phải làm những bước extract text/index nào ngoài lưu bytes?

### Bài 25
Object storage đang có incomplete multipart uploads và MongoDB pending records quá hạn. Thiết kế cleanup có grace period và audit.

### Bài 26
Đề xuất abstraction FileStorage cho cả embedded, GridFS và object storage. Những capabilities nào không được giả định giống nhau?

## 43. Checklist trước production

1. Thống kê P50/P95/max kích thước file.
2. Nếu nhúng BSON, tính tổng document size và đặt headroom dưới 16 MiB.
3. Phân biệt endpoint chỉ cần metadata với endpoint cần bytes.
4. Sử dụng streaming cho file lớn, tránh load toàn bộ vào heap.
5. Xác định nhu cầu CDN, Range, multipart và direct upload.
6. Đánh giá concurrent uploads/downloads.
7. Dùng stable business attachment ID.
8. GridFS fileId hoặc object bucket/key/version được lưu chính xác.
9. Không xem filename là unique.
10. Có status pending/uploading/verifying/ready/deleting/failed.
11. Chỉ ready sau verify và scan theo policy.
12. Có retry idempotent cho network failures.
13. Có checksum và size validation theo contract.
14. Thay nội dung bằng version mới và atomic pointer switch.
15. Không xóa file dùng chung khi còn live reference.
16. Check quyền tenant/owner/ACL ở backend.
17. Dùng private object buckets và scoped signed URLs.
18. HTTP headers/Content-Disposition/Range đúng.
19. Client cancellation và streaming backpressure được xử lý.
20. Backup đủ metadata và bytes.
21. Với GridFS backup cả files/chunks collections.
22. Với object storage có backup/retention độc lập và DR reconciliation.
23. Có orphan cleanup với grace period.
24. Có legal hold/retention/delete policy.
25. Tính chi phí disk/replication/index/backup/egress.
26. Theo dõi p95 download latency và database impact.
27. Migration copy/verify trước switch và cleanup.
28. API không cần lộ storage backend cho client.
29. Nếu muốn search nội dung file, phải extraction và index độc lập.
30. Có runbook cho upload timeout, partial chunks và dangling references.

## 44. Kết luận

**Nhúng file trong BSON document** hợp lý khi file nhỏ, được đọc cùng dữ liệu nghiệp vụ và có lợi ích từ atomic update trong một document. Giới hạn 16 MiB áp dụng cho **tổng BSON document** chứ không chỉ bytes của file.

**GridFS** thích hợp khi cần lưu file lớn trong MongoDB và muốn dùng upload/download streaming. Nó có fs.files và fs.chunks, nhưng cũng tạo nhiều documents, tăng chi phí database và đòi hỏi xử lý trạng thái, retries, orphan chunks và xóa đúng cách.

**Object storage + MongoDB metadata** thường phù hợp cho media và file lớn có nhiều downloads, CDN, multipart, Range requests và lifecycle riêng. Đánh đổi là phải điều phối nhất quán giữa hai hệ thống và quản lý object permissions.

Vì vậy lựa chọn không chỉ dựa trên **file size**, mà dựa trên **access pattern, atomicity, streaming/CDN, quyền truy cập, versioning, backup, tổng chi phí và khả năng phục hồi lỗi**. Dù dùng backend nào, ổn định attachment ID, xác minh bytes, quản lý trạng thái và reconciliation sẽ giúp tránh duplicate, mất file và rò rỉ dữ liệu.

## Tài liệu tham khảo

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB GridFS Specifications](https://github.com/mongodb/specifications/tree/master/source/gridfs)
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
