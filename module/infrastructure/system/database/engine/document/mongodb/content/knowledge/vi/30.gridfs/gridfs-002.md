# Cấu trúc collection files, chunks và các index cần thiết trong MongoDB GridFS

Một ứng dụng lưu ảnh gốc, video, tài liệu PDF hay các bản xuất dữ liệu có thể gặp ngay giới hạn quan trọng của MongoDB: **mỗi BSON document không thể lớn hơn 16 MiB**. Đưa toàn bộ một file 200 MiB vào một field `BinData` của một document là không khả thi. Kể cả file nhỏ hơn ngưỡng này, đọc và ghi nguyên file thành một document lớn có thể không phù hợp khi ứng dụng muốn **stream** dữ liệu theo từng phần.

**GridFS** giải quyết bài toán bằng cách chia một file thành nhiều phần (*chunks*) và lưu trong **hai collection**:

- **`fs.files`:** mỗi document đại diện cho **một file logic**, chứa ID, kích thước tổng, kích thước chunk, thời điểm upload và metadata.
- **`fs.chunks`:** mỗi document chứa **một đoạn byte** của file, liên kết qua `files_id` và thứ tự `n`.

Hai collection này đi kèm những **chỉ mục không thể bỏ qua**. Đặc biệt, chỉ mục **unique `{files_id:1,n:1}`** trên `fs.chunks` giữ mỗi vị trí chunk của một file chỉ có tối đa một document; chỉ mục **`{filename:1,uploadDate:1}`** trên `fs.files` hỗ trợ tra cứu file theo tên và thời gian tải lên. Chúng không có cùng mục đích, và **filename không phải ID duy nhất của file**.

Bài thuộc chương **GridFS** của module *Database Engine Document MongoDB*. Phần thực hành dùng **mongosh**, **Node.js MongoDB Driver** và **MongoDB Java Sync Driver**. Tất cả ví dụ nên chạy trên database học tập `gridfs_lab`, không thao tác thủ công vào các chunks của file production. Hành vi tạo index tự động, cách dùng stream, metadata và khả năng sharding cần đối chiếu **phiên bản server/driver thực tế** khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khi nào dùng GridFS và tại sao giới hạn 16 MiB của BSON dẫn đến mô hình chunked storage.
2. Mô tả hai collection `<bucket>.files` và `<bucket>.chunks`, và hiểu `fs` chỉ là tên bucket mặc định.
3. Đọc các trường `_id`, `length`, `chunkSize`, `uploadDate`, `filename` và `metadata` trong files document.
4. Đọc các trường `_id`, `files_id`, `n` và `data` trong chunks document.
5. Tính số chunks dự kiến, kích thước chunk cuối và offset cho một file.
6. Phân biệt chỉ mục `_id_` với hai chỉ mục GridFS tiêu chuẩn.
7. Giải thích tại sao `{files_id:1,n:1}` phải unique và vì sao `{filename:1,uploadDate:1}` không unique.
8. Tạo, kiểm tra và bảo trì đúng các chỉ mục cho bucket mặc định và bucket có tên riêng.
9. Upload/download file dưới dạng stream mà không gom toàn bộ file vào RAM.
10. Lấy một file bằng ID, liệt kê nhiều phiên bản cùng filename và thiết kế metadata index riêng.
11. Nhận diện upload dở dang, chunks mồ côi, thiếu chunk, trùng `n` và sai kích thước.
12. Xóa file qua GridFS API thay vì xóa một collection riêng lẻ.
13. Hiểu hạn chế của GridFS về atomicity toàn file, transaction, retention, checksum, sharding và backup.
14. Đo/tối ưu hiệu năng chunk size, số lượng index, query pattern và I/O của hệ thống lưu file.

## 2. GridFS là gì và không phải là gì?

GridFS là một **quy ước lưu trữ file trên MongoDB**, được các driver MongoDB hỗ trợ thông qua các API upload/download chuyên dụng. Nó không phải:

- Một BSON type mới có khả năng vượt 16 MiB trong một document.
- Một collection duy nhất chứa toàn bộ file.
- Một file system có thư mục, quyền POSIX, rename và random write giống ổ đĩa.
- Một mạng phân phối nội dung (CDN) hoặc dịch vụ xử lý ảnh/video.
- Một cơ chế tự động deduplicate các file có cùng nội dung.
- Một transaction nguyên tử cho toàn bộ hàng trăm chunks của file.

### 2.1. Khi nào GridFS phù hợp?

Ví dụ:

- File 30 MiB, 200 MiB hoặc vài GiB phải được lưu cùng hệ sinh thái MongoDB.
- Ứng dụng muốn upload/download theo stream, tránh nạp toàn file vào memory.
- Cần metadata nằm trong MongoDB và tra cứu theo quyền sở hữu/nhóm/ngày tạo.
- Cần backup/quản trị file storage đi cùng database theo chính sách triển khai.
- Muốn tự xây API download theo `fileId` và xử lý access control ở application.

### 2.2. Khi nào chưa chắc nên dùng?

- File chỉ vài KiB và chỉ đọc cùng một business document: có thể dùng `BinData` hoặc data model đơn giản hơn nếu phù hợp.
- Dữ liệu cần update vài byte ở giữa file liên tục: GridFS không được thiết kế để **in-place modify** các chunks một cách tùy tiện.
- Dữ liệu là hàng triệu object nhỏ cần direct public download qua CDN: object storage có thể phù hợp hơn.
- File phải tuân theo lifecycle, replication đa vùng hoặc signed URL chuyên biệt: cân nhắc object storage và lưu **metadata/reference** trong MongoDB.

**Nguyên tắc:** quyết định dùng GridFS dựa trên yêu cầu truy cập, lưu trữ, vận hành và độ lớn file; không mặc định “file nào cũng dùng GridFS”.

## 3. Kiến trúc hai collection

~~~mermaid
flowchart TD
    App["Ứng dụng / GridFSBucket API"] --> Upload["Upload stream: chia byte thành chunks"]
    Upload --> C["fs.chunks"]
    Upload --> F["fs.files"]
    F -->|"Một _id cho mỗi file"| FileMeta["files: length, chunkSize, uploadDate, filename, metadata"]
    C -->|"files_id tham chiếu _id của fs.files"| Chunk1["chunk n=0"]
    C --> Chunk2["chunk n=1"]
    C --> ChunkN["chunk n=N-1"]
    Read["Download bằng fileId"] --> F
    Read --> C
    Read --> Combine["Đọc chunks theo n tăng dần"]
    Combine --> Client["Stream bytes ra client"]
~~~

Giả sử file có `_id=ObjectId("...")`. Document trong `fs.files` mô tả file; mọi document `fs.chunks` thuộc file đó có `files_id` bằng đúng `_id`. **Thứ tự byte không dựa vào `_id` của chunks** mà dựa vào `n`.

### 3.1. Mỗi file logic có nhiều chunks

~~~text
fs.files:
  _id = F1, length = 700000, chunkSize = 261120

fs.chunks:
  files_id = F1, n = 0, data = 261120 bytes
  files_id = F1, n = 1, data = 261120 bytes
  files_id = F1, n = 2, data = 177760 bytes
~~~

Ghép `data` của các chunks theo `n=0,1,2` sẽ tái tạo file có đúng `700000` bytes.

### 3.2. Không có một field `chunks` chứa mảng trong `fs.files`

Một nhầm lẫn thường gặp:

~~~javascript
// KHÔNG phải schema tiêu chuẩn của GridFS.
{
  _id: fileId,
  filename: "video.mp4",
  chunks: [binary1, binary2, binary3]
}
~~~

GridFS dùng **hai collection tách biệt** để mỗi BSON document vẫn dưới 16 MiB và có thể stream từng chunk.

## 4. Bucket prefix: vì sao có `fs.files` và `fs.chunks`?

Tên bucket mặc định là **`fs`**, vì vậy các collection mặc định là:

~~~text
fs.files
fs.chunks
~~~

Khi dùng bucket tên `avatars`, các collection tương ứng trở thành:

~~~text
avatars.files
avatars.chunks
~~~

Một database có thể dùng nhiều bucket:

~~~text
gridfs_lab
├── fs.files
├── fs.chunks
├── avatars.files
├── avatars.chunks
├── exports.files
└── exports.chunks
~~~

### 4.1. Khi nào tạo bucket riêng?

- File khác nhau về **mục đích và vòng đời**: ảnh đại diện, file export, tài liệu đính kèm.
- Muốn metadata/indexing policy khác nhau.
- Muốn đơn giản hóa quản trị quyền truy cập và cleanup theo từng loại.
- Muốn tránh trộn tên file và semantics giữa các nhóm ứng dụng.

Bucket khác nhau **không tự tạo security boundary**. Quyền database/collection và kiểm tra quyền người dùng vẫn phải được thiết kế.

### 4.2. Các tùy chọn thường có của GridFSBucket

Một số driver cho cấu hình:

~~~javascript
{
  bucketName: "avatars",
  chunkSizeBytes: 261120
}
~~~

Tên option trong driver có thể khác, nhưng ý nghĩa là **tiền tố collection** và **kích thước chunk mặc định cho các upload trong bucket**. Trường `chunkSize` được lưu **riêng ở từng files document**, để các file cũ và mới có thể có chunk size khác nhau.

## 5. Schema của `fs.files`

Một files document ví dụ:

~~~javascript
{
  _id: ObjectId("6748abcd1234567890abcdef"),
  length: NumberLong("700000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:30:00Z"),
  filename: "monthly-report.bin",
  metadata: {
    tenantId: "t-01",
    ownerId: "user-18",
    contentType: "application/octet-stream",
    documentType: "report",
    visibility: "private",
    sha256: "hex-sha256-computed-by-application"
  }
}
~~~

Đây là **mẫu cấu trúc**, không phải bản ghi có thật. `sha256` là giá trị placeholder và không được dùng như checksum hợp lệ. Những trường và ý nghĩa:

| Field | Kiểu điển hình | Mục đích |
|---|---|---|
| `_id` | ObjectId mặc định thường gặp; có thể là BSON ID được driver hỗ trợ | Định danh duy nhất của **một phiên bản file** |
| `length` | BSON 64-bit integer | Kích thước đầy đủ của file, **tính bằng bytes** |
| `chunkSize` | Integer | Kích thước chunk chuẩn của file, **tính bằng bytes** |
| `uploadDate` | BSON Date | Thời điểm file được upload/hoàn tất theo driver |
| `filename` | String, tùy trường hợp có thể vắng | Tên logic để tìm kiếm/hiển thị; **không unique** |
| `metadata` | Document tùy chọn | Thông tin business do application định nghĩa |

### 5.1. `_id` là danh tính file, không phải filename

Hai file có thể cùng tên:

~~~text
monthly-report.bin  -> _id=F1, uploadDate=ngày 01
monthly-report.bin  -> _id=F2, uploadDate=ngày 14
~~~

Đây có thể là **hai version** của cùng một tên file. Khi tải đúng file người dùng đã chọn, nên dùng **file ID** thay vì chỉ filename.

### 5.2. `length` là bytes, không phải số chunks

`length=700000` có nghĩa **700000 bytes**. Không suy ra “700000 ký tự”, vì file có thể là nhị phân hoặc UTF-8 đa byte. Không dùng `String.length` trong JavaScript để tính byte length của nội dung Unicode; dùng byte buffer/stream length.

### 5.3. `chunkSize` là thuộc tính mỗi file

Một file cũ có `chunkSize=261120`, file mới có thể dùng `chunkSize=262144`. Driver đọc theo giá trị trong **files document của file đang tải**, không lấy chunk size hiện tại của bucket để giải mã mọi file cũ.

### 5.4. `uploadDate` khác thời gian nghiệp vụ

File report được tạo lúc 08:00 nhưng upload lúc 08:30; `uploadDate` ghi thông tin upload, không nhất thiết là thời điểm dữ liệu business được tạo. Nếu cần thời gian tạo report, lưu `metadata.generatedAt` hoặc field business khác với BSON Date hợp lệ.

### 5.5. `metadata` là dữ liệu ứng dụng

Ví dụ:

~~~javascript
metadata: {
  tenantId: "t-01",
  ownerId: "user-18",
  contentType: "application/pdf",
  reportPeriod: "2026-10",
  dataClassification: "internal"
}
~~~

GridFS không tự hiểu `ownerId` hoặc `visibility` như ACL bắt buộc. **Ứng dụng phải xác thực và phân quyền** khi truy vấn/download/xóa. Đừng đặt mật khẩu hay bí mật vào metadata.

### 5.6. `md5` và những trường legacy

Một số triển khai GridFS cũ có trường `md5`, `contentType` hoặc `aliases` ở top-level. Việc tính MD5 bằng server command và các trường legacy này đã bị **deprecated/không còn là cơ chế khuyến nghị** trong các driver/server hiện đại. Nếu cần toàn vẹn hoặc loại nội dung:

- Lưu `metadata.contentType` do ứng dụng kiểm tra.
- Dùng **SHA-256** (hoặc cơ chế checksum/ETag thích hợp) tính ở application khi cần.
- Không tin filename extension hoặc Content-Type từ client là bằng chứng file an toàn.
- Không thiết kế hệ thống mới phụ thuộc bắt buộc vào `md5` do GridFS tự sinh.

## 6. Schema của `fs.chunks`

Một chunk document:

~~~javascript
{
  _id: ObjectId("6748abcd1234567890abc001"),
  files_id: ObjectId("6748abcd1234567890abcdef"),
  n: 0,
  data: BinData(0, "...")
}
~~~

Giải thích:

| Field | Kiểu điển hình | Vai trò |
|---|---|---|
| `_id` | ID duy nhất trong `fs.chunks` | Định danh document chunk riêng |
| `files_id` | Cùng BSON type/value với `fs.files._id` | Liên kết chunk với file |
| `n` | Integer không âm | Vị trí chunk trong file, **bắt đầu từ 0** |
| `data` | BSON binary | Những byte thật của chunk |

### 6.1. Vì sao phải có `files_id`?

Trong cùng collection `fs.chunks`, chunks của nhiều file được trộn:

~~~text
files_id=F1 n=0
files_id=F2 n=0
files_id=F1 n=1
files_id=F3 n=0
files_id=F1 n=2
files_id=F2 n=1
~~~

Một download đúng phải filter `files_id=F1` và **sort theo `n` tăng dần**, không sort theo `_id` hay thứ tự vật lý trên disk.

### 6.2. `n` là thứ tự zero-based

~~~text
Chunk đầu tiên:  n = 0
Chunk thứ hai:   n = 1
Chunk thứ ba:    n = 2
...
Chunk thứ N:     n = N - 1
~~~

Nếu n bị thiếu, dữ liệu tải về có thể không đầy đủ hoặc driver báo lỗi chunk missing. Nếu có hai chunks cùng `files_id` và `n`, vị trí trở nên mơ hồ; **unique compound index** phải chặn tình huống này.

### 6.3. `data` là binary, không phải Base64 text lưu trữ

Khi mongosh hiển thị `BinData(...)`, đó là cách thể hiện dữ liệu BSON binary, không có nghĩa driver đã lưu file thành chuỗi Base64 như field JSON bình thường. Đừng đọc toàn bộ `data` vào log, hoặc chuyển hàng triệu bytes thành JSON để truyền qua API nội bộ nếu có thể dùng stream.

### 6.4. Chunk document vẫn chịu BSON limit

GridFS chia file để **từng chunk document** dưới 16 MiB. Tăng `chunkSizeBytes` quá lớn có thể vi phạm giới hạn document BSON vì còn overhead của `_id`, `files_id`, `n` và kiểu binary. Không chọn chunk size sát 16 MiB nếu chưa xác nhận giới hạn driver/server.

## 7. Tính số chunks, offset và chunk cuối

Giả sử:

~~~text
File length (L):     700000 bytes
Chunk size (C):      261120 bytes
Số chunks dự kiến:   ceil(700000 / 261120) = 3
~~~

Ba chunk:

| `n` | Byte offset bắt đầu | Số bytes trong `data` |
|---:|---:|---:|
| 0 | 0 | 261120 |
| 1 | 261120 | 261120 |
| 2 | 522240 | 177760 |
| **Tổng** | | **700000** |

### 7.1. Công thức chung

Với `L > 0` và `C > 0`:

\[
N = \left\lceil\frac{L}{C}\right\rceil
\]

Offset của chunk `n`:

\[
\operatorname{offset}(n)=nC,\qquad 0\le n<N
\]

Kích thước chunk tại `n`:

\[
\operatorname{size}(n)=
\min(C,\; L-nC)
\]

Chunk không cuối thường có đúng `C` bytes; chunk cuối có thể nhỏ hơn. Nếu `L` là bội số của `C`, chunk cuối cũng có đúng `C` bytes.

### 7.2. File rỗng

Với `L=0`, số chunks dự kiến **bằng 0**, nhưng file metadata vẫn có thể tồn tại:

~~~text
fs.files: length=0, chunkSize=C
fs.chunks: không có chunk nào cho fileId đó
~~~

Đừng cố tạo một chunk `n=0` có data rỗng chỉ vì thuật toán ứng dụng luôn mong đợi ít nhất một chunk.

### 7.3. Hàm tính toán

~~~javascript
function expectedChunks(lengthBytes, chunkSizeBytes) {
  if (!Number.isSafeInteger(lengthBytes) || lengthBytes < 0 ||
      !Number.isSafeInteger(chunkSizeBytes) || chunkSizeBytes <= 0) {
    throw new Error("INVALID_SIZE")
  }
  return Math.ceil(lengthBytes / chunkSizeBytes)
}

print(expectedChunks(700000, 261120)) // 3
print(expectedChunks(0, 261120))      // 0
print(expectedChunks(522240, 261120)) // 2
~~~

Với file rất lớn có `length` vượt giới hạn số nguyên an toàn của JavaScript, không ép BSON Int64 thành `Number` tùy tiện; dùng kiểu số lớn/logic phù hợp của driver. Ví dụ này chỉ minh họa file nhỏ.

### 7.4. Tại sao chunkSizeBytes mặc định là 255 KiB?

GridFS thường dùng kích thước mặc định **255 KiB = 255 × 1024 = 261120 bytes**. Đây là default GridFS được nhiều driver triển khai, không phải 255000 bytes và không phải 255 MiB. Người dùng có thể chọn chunk size khác theo driver, trong giới hạn server. Mỗi file ghi lại `chunkSize` được dùng thực tế.

## 8. Hai chỉ mục cốt lõi của GridFS

Ngoài `_id_` index thông thường của mỗi collection, GridFS quy định hai compound indexes đặc biệt:

| Collection | Key pattern | Unique? | Tác dụng |
|---|---|---|---|
| `fs.files` | `{filename:1,uploadDate:1}` | **Không** | Tìm file theo tên, hỗ trợ chọn phiên bản theo thời gian |
| `fs.chunks` | `{files_id:1,n:1}` | **Có** | Đọc chunks của một file theo thứ tự; chặn trùng vị trí `n` |

Đây là hai **index GridFS quan trọng nhất**. Không thay chúng bằng `{uploadDate:1}` trên chunks, `{n:1}` đơn lẻ hoặc unique `{filename:1}`.

### 8.1. Tạo chỉ mục files

~~~javascript
db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)
~~~

Không đặt `unique:true`, bởi cùng filename có thể có nhiều phiên bản upload khác nhau. `uploadDate` hỗ trợ sort theo thời gian. Nếu các version có cùng uploadDate đến độ phân giải thời gian, có thể dùng `_id` làm tie-breaker trong ứng dụng khi cần thứ tự ổn định.

### 8.2. Tạo chỉ mục chunks

~~~javascript
db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  {
    unique: true,
    name: "files_id_1_n_1"
  }
)
~~~

Chỉ mục này làm hai việc:

1. Filter `files_id` để chỉ lấy chunks của **một file**.
2. Cung cấp thứ tự `n` và bảo đảm không có hai chunks cùng `(files_id,n)`.

### 8.3. Vì sao unique phải nằm trên cặp `(files_id,n)`?

Nếu chỉ unique `n`, tất cả files đều có chunk `n=0` nên upload file thứ hai sẽ bị chặn sai. Nếu chỉ unique `files_id`, mỗi file chỉ có thể có một chunk. Unique trên **cặp** vừa cho nhiều chunks/file, vừa giữ mỗi vị trí chunk duy nhất.

### 8.4. Chỉ mục không kiểm tra tính liên tục

Unique `{files_id:1,n:1}` **không bảo đảm** có đủ các chunk:

~~~text
files_id=F1: n=0, n=1, n=3
~~~

Không có duplicate, nên unique index không phát hiện `n=2` bị thiếu. Driver cần dựa vào `length`, `chunkSize` và thứ tự để phát hiện một số dạng lỗi/incomplete file. Cần thêm chính sách integrity/checksum nếu nghiệp vụ yêu cầu.

### 8.5. Chỉ mục cũng không bảo đảm bytes đúng

Unique index không thể xác nhận `data` chunk thứ hai có chính xác 261120 bytes hay có bị thay đổi nội dung. Integrity không thể chỉ dựa vào chỉ mục.

## 9. Vì sao `fs.files` index không unique?

Giả sử ứng dụng upload:

~~~text
2026-10-01: filename = invoice.pdf, fileId = A
2026-10-15: filename = invoice.pdf, fileId = B
2026-11-01: filename = invoice.pdf, fileId = C
~~~

Theo GridFS, ba file logic khác nhau được phép dùng cùng `filename`. Đây có thể là ba bản upload của cùng một tài liệu, ba file từ người dùng khác nhau hoặc một tên phổ biến như `image.jpg`.

### 9.1. Tìm các file có cùng tên

~~~javascript
db.fs.files.find(
  { filename: "invoice.pdf" },
  {
    _id: 1,
    filename: 1,
    uploadDate: 1,
    length: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
~~~

Chỉ mục `{filename:1,uploadDate:1}` thường giúp tìm theo tên và quét theo thời gian. Không có nghĩa `invoice.pdf` thuộc đúng người yêu cầu; phải kiểm tra owner/tenant.

### 9.2. Dùng fileId khi tham chiếu lâu dài

Trong một document business:

~~~javascript
{
  _id: "application-2026-001",
  tenantId: "t-01",
  attachmentFileId: ObjectId("6748abcd1234567890abcdef"),
  attachmentFilename: "invoice.pdf"
}
~~~

`attachmentFileId` là tham chiếu chính xác. Filename chỉ để hiển thị. Nếu người dùng upload lại một file cùng tên, business document có thể chọn khi nào đổi tham chiếu, thay vì tự động tải “file mới nhất” ngoài ý muốn.

### 9.3. Unique business key cần đặt ở đâu?

Nếu yêu cầu “mỗi hồ sơ chỉ có một file đính kèm hiện hành”, có thể enforce bằng **regular collection** quản lý hồ sơ/attachment references, với unique index theo `tenantId + applicationId + attachmentType`. Không biến `fs.files.filename` thành unique toàn hệ thống để giải quyết một constraint nghiệp vụ riêng.

## 10. Khởi tạo bucket và các index

GridFSBucket của nhiều driver **kiểm tra/tạo các index chuẩn khi cần** (thường trong quá trình upload đầu tiên vào bucket mới/rỗng), theo GridFS specification và phiên bản driver. Tuy nhiên, không nên phụ thuộc vào một request upload đầu tiên trên production để lần đầu tạo index giữa nhiều request đồng thời.

### 10.1. Kiểm tra index hiện có

~~~javascript
use gridfs_lab

db.fs.files.getIndexes()
db.fs.chunks.getIndexes()
~~~

Kỳ vọng tối thiểu sau khi bucket được khởi tạo đúng:

~~~javascript
// fs.files
{ key: { _id: 1 }, name: "_id_" }
{ key: { filename: 1, uploadDate: 1 },
  name: "filename_1_uploadDate_1" }

// fs.chunks
{ key: { _id: 1 }, name: "_id_" }
{ key: { files_id: 1, n: 1 },
  name: "files_id_1_n_1", unique: true }
~~~

Đây là **hình dạng minh họa các index liên quan**, không phải nguyên văn đầy đủ mọi field trong output `getIndexes()`; tùy phiên bản còn có `v`, `ns` và options khác.

### 10.2. Có thể chuẩn bị index từ deployment/migration

Với database/bucket lab hoặc kế hoạch khởi tạo có kiểm soát:

~~~javascript
use gridfs_lab

db.createCollection("fs.files")
db.createCollection("fs.chunks")

db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)

db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  { unique: true, name: "files_id_1_n_1" }
)
~~~

**Chỉ chạy trong môi trường được phép tạo collection/index**, tránh triển khai lại không kiểm soát. Nếu có index cùng key pattern nhưng options/name khác, phải kiểm tra trước khi tạo để tránh conflict; không tự drop index đang được ứng dụng sử dụng.

### 10.3. Bucket custom `avatars`

~~~javascript
db.createCollection("avatars.files")
db.createCollection("avatars.chunks")

db.getCollection("avatars.files").createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)

db.getCollection("avatars.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true, name: "files_id_1_n_1" }
)
~~~

Tên `fs` không nằm trong key pattern. Với custom bucket, **đổi cả hai tên collection**. Nếu bạn tạo `avatars.files` nhưng chunks lại lưu trong `fs.chunks`, GridFSBucket với bucketName `avatars` sẽ không tìm được đúng chunks.

### 10.4. Không tự tạo unique index khi đang có dữ liệu trùng

Nếu do import sai từng có hai chunks cùng `(files_id,n)`, tạo unique index có thể thất bại. Trước khi sửa, sao lưu dữ liệu, xác định file nào bị lỗi và có nguồn dữ liệu gốc để khôi phục; không chọn ngẫu nhiên một chunk để xóa trong production.

## 11. Index nào dùng cho từng kiểu truy vấn?

| Truy vấn | Index phù hợp |
|---|---|
| Tìm metadata file theo `_id` | `fs.files._id_` |
| Tìm tên + liệt kê phiên bản theo uploadDate | `fs.files.{filename:1,uploadDate:1}` |
| Tải fileId F: đọc chunks theo n | `fs.chunks.{files_id:1,n:1}` unique |
| Tìm files theo tenant/owner/trạng thái | Index bổ sung trên `fs.files.metadata.*` nếu workload cần |
| Tìm file theo checksum SHA-256 | Index metadata checksum nếu thật sự cần; không mặc định unique |
| Dọn file theo policy thời hạn | Index theo metadata/expiration để tìm candidates; xóa qua GridFS API |

### 11.1. Index giúp tìm file, không thay business authorization

Một request:

~~~javascript
db.fs.files.find({
  "metadata.tenantId": "t-01",
  "metadata.ownerId": "user-18",
  filename: "monthly-report.bin"
})
~~~

có thể cần index bổ sung tùy khối lượng:

~~~javascript
db.fs.files.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.ownerId": 1,
    uploadDate: -1
  },
  { name: "idx_tenant_owner_uploaded" }
)
~~~

Đây là **index ứng viên**, không phải index GridFS bắt buộc. Chỉ tạo sau khi đo queries thật và biết field types/selectivity.

### 11.2. Index trên metadata không làm upload an toàn hơn

Index giúp lọc metadata nhanh, không tự xác thực content type, loại bỏ virus, bảo vệ quyền download hoặc kiểm tra checksum. Những việc đó cần ở ứng dụng/quy trình xử lý file.

### 11.3. Chi phí index

Mỗi insert `fs.files` và `fs.chunks` phải cập nhật indexes liên quan. Với file có hàng trăm nghìn chunks, index trên chunks là chi phí cần thiết; tạo thêm nhiều indexes trên chunks không có access pattern tương ứng sẽ tăng disk/CPU/write amplification.

## 12. Kiểm tra chỉ mục bằng `explain()`

Sau khi upload một file, bạn có thể xem plan đọc chunks:

~~~javascript
const fileDoc = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

if (fileDoc) {
  db.fs.chunks.explain("executionStats").find({
    files_id: fileDoc._id
  }).sort({ n: 1 })
}
~~~

Đây là truy vấn chỉ để **giải thích access path**. Việc tải file thực phải dùng GridFSBucket/driver để xác nhận kích thước và stream bytes.

Khi đọc explain, chú ý:

- `winningPlan` có dùng index `files_id_1_n_1` không?
- Có stage sort blocking không?
- `nReturned` tương ứng số chunk dự kiến không?
- `totalKeysExamined`/`totalDocsExamined` có phù hợp số chunk không?
- Query có filter đúng BSON value/type của `files_id` không?

Tên stage có thể thay đổi theo MongoDB/query engine. Không coi index scan là bảo đảm mọi byte dữ liệu không bị lỗi.

### 12.1. Index prefix

`{files_id:1,n:1}` phù hợp vì query có equality trên `files_id` rồi sort/range theo `n`. Một index `{n:1,files_id:1}` không tương đương đối với workload “đọc toàn bộ chunks của một file”.

### 12.2. Đừng tìm kiếm bằng chunk `_id`

`fs.chunks._id` xác định một document chunk; driver không sử dụng nó làm thứ tự byte. Index `_id_` mặc định không thay thế compound index `files_id,n`.

## 13. Upload file: thứ tự thao tác và thời điểm file hoàn tất

Luồng thông thường:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Bucket as GridFSBucket
    participant Chunks as fs.chunks
    participant Files as fs.files
    App->>Bucket: Mở upload stream(filename, metadata)
    loop Mỗi chunk
        Bucket->>Chunks: insert {files_id, n, data}
    end
    App->>Bucket: Hoàn tất input stream
    Bucket->>Files: insert file metadata {length, chunkSize, ...}
    Bucket-->>App: Upload hoàn tất + fileId
~~~

Về nguyên tắc GridFS, **file metadata được ghi sau khi các chunks đã ghi xong** để không công bố file như một object hoàn chỉnh khi còn thiếu dữ liệu. Nếu upload thất bại giữa chừng, có thể còn chunks chưa có files document (tùy cách driver đã xử lý cleanup và loại lỗi).

### 13.1. Không phải một transaction cho mọi chunks

Upload file 5 GiB gồm rất nhiều chunk inserts. Không được khẳng định các insert vào `fs.chunks` và `fs.files` tự động **atomic toàn file** theo nghĩa một multi-document transaction. GridFS sử dụng một **protocol upload/download**, không thay transaction engine.

### 13.2. File xuất hiện ở `fs.files` nghĩa là gì?

Trong upload bình thường qua driver, files document thường được tạo **sau khi hoàn tất ghi chunks**, giúp consumer tìm được file logic đã upload. Tuy nhiên:

- Chunk data vẫn có thể bị lỗi/corrupt nếu có sự cố nghiêm trọng hoặc sửa thủ công.
- Một writer tùy tiện có thể tạo files document sai.
- Backup/restore không nhất quán có thể làm mất tương ứng giữa hai collections.
- Không thể chỉ tin `fs.files` có document là mọi dữ liệu vật lý tuyệt đối đúng trong mọi failure scenario.

Khi integrity quan trọng, cần verify stream length và checksum.

### 13.3. Upload stream không nên buffering toàn file

Mục tiêu của GridFS là **stream chunks**. Tránh:

~~~javascript
// KHÔNG phù hợp cho file nhiều GiB:
const entireFile = await fs.promises.readFile(path)
await uploadAllBytesAtOnce(entireFile)
~~~

Trường hợp này vẫn nạp cả file vào RAM, bỏ lợi ích stream.

## 14. Node.js: upload stream qua GridFSBucket

Ví dụ driver hiện đại:

~~~javascript
import { MongoClient, GridFSBucket } from "mongodb";
import { createReadStream } from "node:fs";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const database = client.db("gridfs_lab");
  const bucket = new GridFSBucket(database, {
    bucketName: "fs",
    chunkSizeBytes: 261120
  });

  const source = createReadStream("sample-700000.bin");
  const upload = bucket.openUploadStream(
    "sample-700000.bin",
    {
      metadata: {
        tenantId: "t-01",
        ownerId: "user-18",
        contentType: "application/octet-stream",
        documentType: "lab"
      }
    }
  );

  const fileId = upload.id;
  await pipeline(source, upload);
  console.log("Upload completed, fileId =", fileId);
} finally {
  await client.close();
}
~~~

Đoạn code này cần **file local `sample-700000.bin` đã tồn tại** và có đường dẫn được kiểm soát. Nó không tự tạo file và không bảo đảm file thật có đúng 700000 bytes; tên chỉ để nhận biết. Dữ liệu metadata `tenantId` và `ownerId` phải đến từ **ngữ cảnh tin cậy của ứng dụng**, không lấy vô điều kiện từ request body.

### 14.1. Tại sao lấy `fileId` trước khi pipeline hoàn tất?

`openUploadStream()` tạo stream với ID có thể biết sớm, nhưng **biết ID không có nghĩa upload đã thành công**. Chỉ sau khi `await pipeline(...)` hoàn tất không lỗi mới công bố fileId như một file có thể tải xuống.

### 14.2. Khi pipeline lỗi

Nếu nguồn đọc lỗi, network lỗi hoặc upload stream abort, xử lý/cleanup phụ thuộc trạng thái và driver. Không công bố fileId cho người dùng như file đã hoàn tất. Ghi lại upload attempt, log error code và có quy trình dọn chunks mồ côi sau khi xác định chắc chắn không còn upload đang diễn ra.

### 14.3. Chunk size là options của upload/bucket

MongoDB lưu `chunkSize` thực tế trong `fs.files`. Đừng đọc từ biến cấu hình runtime để tính số chunks của **file được upload tuần trước**, vì cấu hình bucket có thể đã thay đổi.

## 15. Node.js: download bằng ID

Từ `fileId` nhận được sau upload:

~~~javascript
import { MongoClient, GridFSBucket, ObjectId } from "mongodb";
import { createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const database = client.db("gridfs_lab");
  const bucket = new GridFSBucket(database, {
    bucketName: "fs"
  });

  // Đây là ID ví dụ: thay bằng ID hợp lệ đã upload.
  const fileId = new ObjectId("6748abcd1234567890abcdef");

  // Production: kiểm tra quyền trên fs.files trước download.
  const download = bucket.openDownloadStream(fileId);
  const output = createWriteStream("downloaded.bin");

  await pipeline(download, output);
  console.log("Downloaded");
} finally {
  await client.close();
}
~~~

**Lưu ý:** ObjectId phía trên chỉ là placeholder 24 ký tự hex. Để demo chạy thành công, thay bằng ID thật của file vừa upload, và chọn đường dẫn output không ghi đè tệp quan trọng. Nếu `_id` của file không phải ObjectId, phải sử dụng cùng BSON type thay vì ép sang ObjectId.

### 15.1. Không để client chọn arbitrary local path

Trong API server, không dùng tên file do user gửi làm đường dẫn hệ thống không qua validation. Nếu client yêu cầu download filename `../../secret.txt` mà server ghi thẳng vào disk có thể tạo path traversal. Đường dẫn local do **service** quyết định; filename GridFS là metadata hiển thị.

### 15.2. Download by filename

Một số GridFS driver cung cấp `openDownloadStreamByName`. API này cần xác định **revision** khi một filename có nhiều phiên bản; mặc định/option phải được kiểm tra theo driver version. Khi business entity có sẵn fileId, ưu tiên `openDownloadStream(fileId)` để tránh tải nhầm bản.

### 15.3. Trả file qua HTTP

Streaming tới response có thể giảm RAM so với đọc toàn file vào buffer. Nhưng trước khi stream:

1. Xác thực principal.
2. Tra `fs.files`, kiểm tra tenant/owner/quyền.
3. Thiết lập `Content-Type` an toàn theo policy, không tin metadata chưa validate.
4. Đặt `Content-Disposition` để chống nội dung nguy hiểm render trực tiếp ngoài ý muốn.
5. Giới hạn rate/concurrency, xử lý client disconnect và stream errors.

GridFS không tự cấp quyền truy cập theo field metadata.

## 16. Java Sync Driver: GridFSBucket và upload/download

Ví dụ dùng MongoDB Java Sync Driver và `GridFSBuckets`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import org.bson.Document;
import org.bson.types.ObjectId;

public class GridFSUploadDownloadDemo {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("gridfs_lab");
            GridFSBucket bucket = GridFSBuckets.create(database, "fs");

            GridFSUploadOptions options = new GridFSUploadOptions()
                .chunkSizeBytes(261120)
                .metadata(new Document("tenantId", "t-01")
                    .append("ownerId", "user-18")
                    .append("contentType", "application/octet-stream"));

            ObjectId fileId;
            try (InputStream source =
                    new FileInputStream("sample-700000.bin")) {
                fileId = bucket.uploadFromStream(
                    "sample-700000.bin", source, options
                );
            }

            try (OutputStream output =
                    new FileOutputStream("downloaded-copy.bin")) {
                bucket.downloadToStream(fileId, output);
            }

            System.out.println("GridFS fileId: " + fileId);
        }
    }
}
~~~

Trong code này:

- `GridFSBuckets.create(database,"fs")` dùng bucket mặc định với prefix `fs`.
- `uploadFromStream` đọc từ `InputStream`, chia chunks theo `chunkSizeBytes` và tạo file metadata.
- `downloadToStream` tìm `fs.files` và các `fs.chunks` theo ID, ghi ra `OutputStream`.
- Đường dẫn local cố định chỉ phù hợp lab; service production phải kiểm soát quyền và đường dẫn.
- Code dùng `ObjectId` vì đây là kiểu ID thường gặp; tùy API/version có thể cho custom BSON ID.

### 16.1. Không trộn tên bucket khi tải

Nếu upload bằng bucket `exports`:

~~~java
GridFSBucket exports = GridFSBuckets.create(database, "exports");
~~~

thì phải download bằng **cùng bucket**. Dùng `fs` mặc định để tải ID nằm trong `exports.files` có thể báo file not found, dù ObjectId tồn tại ở collection khác.

## 17. Kiểm tra file upload bằng mongosh

Sau một upload thực sự thành công:

~~~javascript
use gridfs_lab

const fileDoc = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

printjson(fileDoc)
~~~

File có thể không đúng 700000 bytes nếu tên không phản ánh độ lớn; các phép tính luôn dùng **`fileDoc.length` thực tế**.

### 17.1. Liệt kê chunks nhưng không in binary

~~~javascript
if (fileDoc) {
  db.fs.chunks.find(
    { files_id: fileDoc._id },
    { data: 0 }
  ).sort({ n: 1 })
}
~~~

Projection `{data:0}` tránh hiển thị payload binary dài. Không xuất toàn bộ `BinData` ra console/log, đặc biệt khi file chứa thông tin nhạy cảm.

### 17.2. Đếm chunks

~~~javascript
if (fileDoc) {
  print("Chunks =", db.fs.chunks.countDocuments({
    files_id: fileDoc._id
  }))
}
~~~

### 17.3. Kiểm tra số chunks kỳ vọng

~~~javascript
if (fileDoc) {
  const expected = Math.ceil(
    Number(fileDoc.length) / fileDoc.chunkSize
  )
  const actual = db.fs.chunks.countDocuments({
    files_id: fileDoc._id
  })

  printjson({
    fileId: fileDoc._id,
    expectedChunks: expected,
    actualChunks: actual
  })
}
~~~

Ép `Number(fileDoc.length)` chỉ phù hợp lab/file đủ nhỏ để an toàn. Với file rất lớn, hãy dùng kiểu số 64-bit/BigInt phù hợp. **Count bằng nhau chưa đủ khẳng định file toàn vẹn**; chunks có thể thiếu `n=2` và có `n=3` thay thế, hoặc `data` bị sửa.

### 17.4. Đọc bytes dài chunk trong mongosh

Để kiểm tra thực tế byte length, có thể làm trong phạm vi lab với `BinData` API của phiên bản mongosh:

~~~javascript
const firstChunk = db.fs.chunks.findOne(
  { files_id: fileDoc._id, n: 0 }
)

if (firstChunk) {
  print("First chunk exists")
  // Không cần giải mã/in toàn bộ binary ở CLI.
}
~~~

Khi muốn xác minh toàn vẹn, dùng **download stream + checksum ở application** thay vì đọc toàn bộ `data` vào mongosh và tạo áp lực bộ nhớ.

## 18. Phân biệt truy vấn metadata với đọc nội dung file

Một API tìm kiếm:

~~~javascript
db.fs.files.find(
  {
    "metadata.tenantId": "t-01",
    filename: "sample-700000.bin"
  },
  {
    _id: 1,
    filename: 1,
    uploadDate: 1,
    length: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
~~~

đọc **metadata**, chưa tải bytes. Ứng dụng nhận `_id` rồi gọi GridFSBucket để stream nội dung. Đây là pattern tốt:

~~~text
Find metadata + authorize
  -> choose exact fileId
  -> GridFSBucket.openDownloadStream(fileId)
  -> stream bytes
~~~

Không query:

~~~javascript
db.fs.chunks.find({ files_id: fileId })
~~~

rồi serialize các documents thành JSON HTTP response để tải file; bạn sẽ vừa tăng memory/network overhead, vừa vô tình lộ cấu trúc nội bộ.

## 19. Kích thước chunk: đánh đổi không đơn giản

Default khoảng **255 KiB** thường là điểm khởi đầu hợp lý, nhưng không phải tối ưu tuyệt đối.

### 19.1. Chunk nhỏ

Ưu điểm:

- Mỗi thao tác đọc/ghi một chunk có payload nhỏ.
- Có thể linh hoạt hơn khi cần xử lý streaming incremental.
- Giảm kích thước mỗi BSON document.

Nhược điểm:

- File lớn tạo **nhiều documents** hơn.
- Nhiều entries trong `fs.chunks` index.
- Nhiều insert/read operations và overhead per chunk.
- Metadata/document overhead lớn hơn so với byte payload.

### 19.2. Chunk lớn

Ưu điểm có thể gồm:

- Ít documents/chunk inserts cho cùng file.
- Ít index entries hơn.
- Có thể giảm overhead operation trong một số workload.

Nhược điểm:

- Từng operation chuyển payload lớn hơn.
- Nặng hơn khi cần đọc một đoạn nhỏ hoặc khi backpressure/memory bị giới hạn.
- Phải nằm dưới BSON document limit 16 MiB và giới hạn driver/protocol.
- Không tự tăng throughput nếu bottleneck ở network, disk hoặc replication.

### 19.3. Ví dụ so sánh file 100 MiB

Đặt `L=104857600 bytes`:

| Chunk size | Số chunks dự kiến |
|---|---:|
| 255 KiB = 261120 bytes | 402 |
| 256 KiB = 262144 bytes | 400 |
| 1 MiB = 1048576 bytes | 100 |
| 4 MiB = 4194304 bytes | 25 |

Các giá trị chỉ là phép chia số chunks, **không phải benchmark hiệu năng**. Tăng chunk size không tự làm upload nhanh hơn 4 lần.

### 19.4. Chọn dựa trên workload

Hãy đo:

- P50/p95/p99 upload/download latency.
- Throughput bytes/s và concurrent streams.
- Số operation/giây trên `fs.chunks`.
- CPU/disk cache/network trên primary/secondaries.
- Index size và data size.
- Mức backpressure khi client có kết nối chậm.
- Tỷ lệ file nhỏ so với file lớn.

Không chuyển cả hệ thống sang chunk 8 MiB chỉ vì số insert ít hơn, đặc biệt khi đa số file chỉ 200 KiB.

## 20. File nhỏ hơn chunk size thì sao?

Ví dụ file 32 KiB, `chunkSize=261120`:

~~~text
fs.files.length = 32768
fs.files.chunkSize = 261120
fs.chunks: n=0, data=32768 bytes
~~~

GridFS vẫn tạo files metadata và một chunk cho file nhỏ khác rỗng. Mô hình GridFS có overhead tối thiểu **hai documents** và các index entries. Nếu ứng dụng chỉ lưu vô số icon 1 KiB, chi phí có thể cao hơn một data model/object storage thích hợp. GridFS không phải lựa chọn mặc định cho mọi binary nhỏ.

## 21. File rất lớn: số chunks và giới hạn thực tế

GridFS cho phép lưu file lớn hơn 16 MiB bằng cách chia chunks, nhưng điều đó không làm hệ thống vô hạn:

- Dung lượng đĩa, quota và oplog có giới hạn.
- Replica set phải replicate các chunks.
- Tốc độ upload bị ràng buộc network/driver/backpressure.
- Một file cực lớn có rất nhiều chunks/index entries.
- Backup/restore phải giữ nhất quán **cả hai collection**.
- Một upload thất bại có thể để lại phần dữ liệu đã ghi.
- Mỗi chunk BSON document vẫn chịu giới hạn BSON.

Nếu ứng dụng thường xuyên lưu media đa GiB đến nhiều TB, nên so sánh GridFS với object storage về throughput, CDN, chi phí, range retrieval, lifecycle và quản trị.

### 21.1. Không mở một multi-document transaction quanh toàn file

Tránh thiết kế:

~~~text
BEGIN TRANSACTION
  Upload 5 GiB gồm hàng chục nghìn chunk inserts
  Ghi business record
COMMIT
~~~

Một transaction dài/lớn có thể vượt lifetime, cache hoặc giới hạn khác. GridFS API cũng không được giả định có thể hoạt động như một thao tác đơn document nguyên tử bên trong mọi transaction. Nếu cần công bố file và business record nhất quán ở cấp ứng dụng, hãy dùng **staging/publish state**, không mở transaction cực lớn.

## 22. Vòng đời file: PENDING, READY và DELETED

Một mẫu ứng dụng thực dụng là có **regular collection** quản lý file reference và business lifecycle:

~~~javascript
{
  _id: "attachment-001",
  tenantId: "t-01",
  ownerId: "user-18",
  gridFsFileId: ObjectId("6748abcd1234567890abcdef"),
  bucketName: "fs",
  state: "READY",
  expectedSha256: "application-computed-sha256",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Một workflow:

~~~mermaid
flowchart TD
    Start["Tạo upload intent"] --> Pending["Business state=PENDING"]
    Pending --> Stream["Stream file vào GridFS"]
    Stream --> Success{"Upload hoàn tất?"}
    Success -->|"Không"| Failed["FAILED; cleanup theo policy"]
    Success -->|"Có"| Verify["Verify length/checksum/quét nội dung"]
    Verify --> Ready["Publish business reference=READY"]
    Ready --> Download["Chỉ cho download khi authorized"]
    Ready --> Delete["Nhận yêu cầu xóa"]
    Delete --> Cleanup["GridFSBucket.delete(fileId)"]
    Cleanup --> Deleted["Đánh dấu DELETED/ghi audit"]
~~~

### 22.1. Công bố file sau upload

Đừng viết business record ở trạng thái READY khi mới **biết fileId** nhưng stream chưa hoàn tất. Nếu ứng dụng crash giữa upload và publish, reconciliation job cần phân biệt file hoàn chỉnh chưa được publish với chunks mồ côi.

### 22.2. Không hứa two-phase atomicity chỉ vì có hai bước

Workflow staging/publish có **những trạng thái tạm thời** và cần recovery. Nếu job sau upload crash trước khi cập nhật business reference, có thể có một file GridFS hoàn tất nhưng chưa được liên kết. Hãy dùng stable upload intent ID, timeout và reconciliation.

## 23. Upload dở: chunks mồ côi

Một upload có thể ghi:

~~~text
fs.chunks:
  files_id=F1 n=0
  files_id=F1 n=1
  files_id=F1 n=2

fs.files:
  chưa có _id=F1
~~~

Đây là **orphan chunks**: chunk documents không có files document tương ứng. Một số driver cố cleanup khi abort bình thường, nhưng crash/network failure có thể để lại dữ liệu. Không mặc định mọi upload failure đều được dọn hoàn hảo.

### 23.1. Cảnh báo về orphan scanner

Một phép join/aggregation để nhận diện `files_id` chưa có metadata có thể hữu ích khi audit, nhưng **không tự động xóa tất cả**:

- Một upload **đang diễn ra** hợp lệ cũng có chunks trước khi files document được tạo.
- Secondary read có thể bị trễ.
- Batch upload dài có thể chưa hoàn tất.
- Một backend cũ có thể đang retry/recover.

Chỉ cleanup sau khi vượt **grace period an toàn**, xác định không còn active upload session, và đã có backup/audit theo chính sách.

### 23.2. Ví dụ audit bằng aggregation

Để nghiên cứu trong lab, có thể group theo `files_id` và so với files metadata:

~~~javascript
db.fs.chunks.aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 },
      minN: { $min: "$n" },
      maxN: { $max: "$n" }
    }
  },
  {
    $lookup: {
      from: "fs.files",
      localField: "_id",
      foreignField: "_id",
      as: "file"
    }
  },
  {
    $match: {
      file: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1,
      minN: 1,
      maxN: 1
    }
  }
])
~~~

Aggregation này có thể đắt trên collection chunks rất lớn; nó **chỉ nhận diện candidates** và không xác minh tuổi/active upload. Không chạy toàn cluster production vào giờ cao điểm mà không có kế hoạch.

### 23.3. Dọn orphan an toàn

Ưu tiên quy trình có quản lý upload intents/active sessions, xác minh tuổi, kiểm tra backup và chạy batch nhỏ. Tránh ví dụ:

~~~javascript
// KHÔNG dùng trong production:
db.fs.chunks.deleteMany({
  files_id: { $nin: allKnownFileIds }
})
~~~

Lệnh này có thể xóa chunks của upload đang hoạt động, tạo lỗi dữ liệu và quét toàn collection.

## 24. File có metadata nhưng thiếu chunk

Ví dụ:

~~~text
fs.files:
  _id=F2, length=700000, chunkSize=261120

fs.chunks:
  files_id=F2 n=0
  files_id=F2 n=2
~~~

Chunk `n=1` bị thiếu, dù files document còn tồn tại. Unique `{files_id:1,n:1}` không ngăn được tình huống này. Tùy driver/version, download có thể báo lỗi missing chunk hoặc chunk size mismatch.

### 24.1. Cách xử lý

1. Không cố xuất file “bằng mọi giá” khi biết thiếu bytes.
2. Ghi lại fileId, chunk count và lỗi, không log binary data.
3. Kiểm tra recent deploy, manual deletion, backup/restore, disk faults.
4. Nếu có nguồn file gốc, re-upload file thành **fileId mới**, verify checksum, rồi cập nhật reference.
5. Không tự tạo chunk `n=1` với bytes rỗng hoặc lặp chunk khác.

### 24.2. Không tin count một mình

File có N=3 chunks nhưng các giá trị `n` là 0,1,4 vẫn có **count=3**. Cần kiểm tra **dải liên tục** và kích thước từng chunk, sau cùng kiểm tra checksum toàn file nếu cần.

## 25. Checksum, integrity và `md5` legacy

GridFS chứa các byte, còn tính toàn vẹn đầu-cuối là yêu cầu riêng của ứng dụng. Một chính sách mạnh có thể ghi:

~~~javascript
metadata: {
  sha256: "sha256-digest-hex",
  expectedLengthBytes: NumberLong("700000"),
  contentType: "application/octet-stream"
}
~~~

Giá trị SHA-256 phải được **tính từ nội dung thật** bởi application, không dùng placeholder.

### 25.1. Streaming SHA-256

Trong Node.js:

~~~javascript
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";

async function sha256OfFile(path) {
  const hash = createHash("sha256");

  for await (const chunk of createReadStream(path)) {
    hash.update(chunk);
  }

  return hash.digest("hex");
}
~~~

Hàm này tính checksum mà không đọc toàn file vào RAM. Trong production, khi hash trước upload và file nguồn có thể đổi giữa hai lần đọc, cần bảo đảm nguồn immutable hoặc hash đồng thời với pipeline theo cơ chế streaming an toàn. Có thể tính lại checksum trên download stream để kiểm tra khớp với giá trị lưu.

### 25.2. Checksum khác authentication

Checksum xác nhận nội dung có giống giá trị băm dự kiến, nhưng nếu attacker có quyền thay cả file **và** metadata checksum thì vẫn có thể ngụy tạo. Cần access controls, audit, encryption/signature hoặc cơ chế bảo vệ integrity theo threat model.

### 25.3. Không mặc định GridFS tạo SHA-256

GridFS specification không biến SHA-256 thành một trường bắt buộc của `fs.files`. `metadata.sha256` là **quy ước ứng dụng**, và phải được tính/kiểm tra một cách chủ động.

## 26. Xóa file: phải dọn cả metadata và chunks

GridFSBucket cung cấp thao tác xóa theo **file ID**, ví dụ Node.js:

~~~javascript
import { MongoClient, GridFSBucket, ObjectId } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const bucket = new GridFSBucket(client.db("gridfs_lab"));
  const fileId = new ObjectId("6748abcd1234567890abcdef");

  // Chỉ gọi sau khi xác thực và xác nhận quyền xóa.
  await bucket.delete(fileId);
} finally {
  await client.close();
}
~~~

Thay ObjectId ví dụ bằng ID thật. GridFSBucket xử lý xóa file metadata và chunks tương ứng theo API/driver. Không chạy thử `delete` trên file production.

### 26.1. Sai: chỉ xóa `fs.files`

~~~javascript
// KHÔNG NÊN làm:
db.fs.files.deleteOne({ _id: fileId })
~~~

Nếu không dọn `fs.chunks`, file metadata biến mất nhưng chunks vẫn chiếm dung lượng, tạo orphan.

### 26.2. Sai: chỉ xóa `fs.chunks`

~~~javascript
// KHÔNG NÊN làm:
db.fs.chunks.deleteMany({ files_id: fileId })
~~~

Files metadata còn nhưng download thiếu byte, tạo file hỏng. Chỉ thao tác trực tiếp khi có runbook khôi phục/repair với ownership rõ ràng.

### 26.3. Xóa không phải lúc nào cũng atomic trên hai collections

Xóa GridFS file bao gồm nhiều document operations. Tùy failure point có thể cần retry/reconciliation. Một ứng dụng cần lifecycle state `DELETING`/`DELETED` và background cleanup để tránh hứa với user rằng mọi byte đã bị xóa vật lý ngay khi API bắt đầu xử lý.

## 27. Retention và TTL: cẩn thận orphan chunks

Một ý tưởng tưởng chừng hợp lý:

~~~javascript
// NGUY HIỂM nếu dùng như cơ chế xóa file hoàn chỉnh.
db.fs.files.createIndex(
  { uploadDate: 1 },
  { expireAfterSeconds: 2592000 }
)
~~~

TTL index trên `fs.files` chỉ tác động tới **documents của collection files**, không tự biết phải xóa documents trong `fs.chunks` tương ứng. Kết quả có thể tạo **rất nhiều orphan chunks**.

### 27.1. Retention đúng nên làm gì?

Một workflow:

1. Xác định file hết hạn bằng business policy và metadata (ví dụ `metadata.expiresAt`).
2. Kiểm tra file có còn được tham chiếu bởi business records, legal hold hoặc workflow đang chạy không.
3. Đặt trạng thái cần xóa, ghi audit.
4. Gọi `GridFSBucket.delete(fileId)` với retry/backoff phù hợp.
5. Reconcile trong trường hợp xóa thất bại một phần.
6. Theo dõi orphan chunks và storage reclaim.

### 27.2. Index để tìm candidates

~~~javascript
db.fs.files.createIndex(
  {
    "metadata.expiresAt": 1,
    "metadata.tenantId": 1
  },
  { name: "idx_expiry_tenant" }
)
~~~

Đây là **index thông thường**, không phải TTL. Nó giúp một cleanup worker tìm files có `expiresAt` đã qua rồi gọi GridFS API. Chọn thứ tự key theo query thực và đặc tính đa tenant; không làm mọi field metadata thành index.

### 27.3. Backup và deletion compliance

Xóa khỏi GridFS đang hoạt động không tự xóa bản sao trong backup, object cache hoặc hệ thống downstream. Nếu có chính sách xóa dữ liệu cá nhân, cần xét toàn bộ retention/backup lifecycle chứ không chỉ một API `delete`.

## 28. File versioning và filename collisions

Hai file khác ID nhưng cùng filename có thể là phiên bản:

~~~javascript
// Minh họa kết quả query metadata:
[
  { _id: "F-new", filename: "invoice.pdf", uploadDate: ISODate("2026-11-14T09:00:00Z") },
  { _id: "F-old", filename: "invoice.pdf", uploadDate: ISODate("2026-10-14T09:00:00Z") }
]
~~~

MongoDB không tự tạo version number `1,2,3` cho các tên giống nhau; `uploadDate` và ID là cơ sở tìm, còn **ý nghĩa version** phải do application quy định.

### 28.1. Tra cứu bằng tên có thể mơ hồ

~~~javascript
db.fs.files.find({ filename: "invoice.pdf" })
  .sort({ uploadDate: -1 })
~~~

Nếu hai files cùng `uploadDate` chính xác tới mili giây, cần tie-breaker xác định. Với nghiệp vụ yêu cầu revision 1, 2, 3, lưu `metadata.revision` hoặc một regular reference record với unique constraint thích hợp.

### 28.2. Tenant + filename

Nếu hai tenants đều có `avatar.png`, tìm chỉ bằng filename sẽ trộn kết quả. Trước download, query metadata có `tenantId` từ principal và kiểm tra owner/access policy, rồi download bằng exact fileId.

### 28.3. Dedupe theo checksum?

Hai file cùng SHA-256 có thể cùng bytes nhưng khác owner, quyền, thời gian lưu hoặc mã hóa. Dedupe vật lý không phải tính năng miễn phí của GridFS. Nếu tự xây content-addressable storage, cần reference counting, quyền truy cập, isolation, race conditions và đảm bảo không xóa bytes khi vẫn có user khác tham chiếu.

## 29. Backup và restore: phải nhất quán cả hai collections

Một snapshot của `fs.files` lúc 10:00 và snapshot `fs.chunks` lúc 10:15 có thể không thuộc cùng trạng thái logical files, đặc biệt khi upload/delete đang chạy:

~~~text
10:00: fs.files chưa có F1
10:05: upload F1 hoàn tất
10:15: fs.chunks đã chứa F1
~~~

Khôi phục hai phần ở thời điểm khác nhau có thể để orphan chunks. Tình huống ngược lại có thể tạo metadata nhưng thiếu chunks.

### 29.1. Backup nhất quán

Sử dụng chiến lược backup/restore phù hợp topology MongoDB (replica set/sharded cluster), với consistency point được bảo đảm bởi công cụ. Không tự copy `fs.files` vào một thời điểm và `fs.chunks` ở thời điểm ngẫu nhiên rồi coi đó là một bản backup hoàn chỉnh.

### 29.2. Sau restore

Kiểm tra:

- Hai collections và indexes có đủ không.
- Số file/chunks và dung lượng có hợp lý.
- Có orphan chunks hoặc files thiếu chunks không.
- Có thể tải một tập file mẫu và verify SHA-256 không.
- Business references có trỏ tới fileId còn tồn tại không.
- Encryption keys, credentials và ACL có được khôi phục đúng không.

## 30. Replica set, sharding và GridFS

GridFS lưu **nhiều documents**, nên replication làm việc với các insert/delete trên hai collections. Khi file lớn, upload tạo một luồng writes liên tục qua primary và oplog; secondaries phải replicate/apply.

### 30.1. Read preference và độ mới

Nếu upload vừa hoàn tất trên primary nhưng ứng dụng đọc `fs.files` và `fs.chunks` từ secondary bị trễ, có thể chưa thấy file hoặc chưa có đầy đủ view ngay lập tức theo consistency settings. Với yêu cầu “upload xong là tải được ngay”, cân nhắc đọc primary hoặc sử dụng read/write concern và causal consistency phù hợp.

### 30.2. Write concern

Write concern ảnh hưởng độ bền của các writes khi upload. `w:"majority"` có thể phù hợp cho tài liệu quan trọng nhưng gây thêm commit latency khi cluster có replication lag. Không suy ra upload thành công từ một chunk insert duy nhất; cần chờ **stream hoàn tất** và tuân thủ durability policy.

### 30.3. GridFS trên sharded cluster

Nếu cần phân tán dữ liệu file qua nhiều shards:

- Cần xem **các quy tắc sharding collection và unique indexes** theo MongoDB version.
- `fs.chunks` có unique compound index bắt buộc trên `{files_id:1,n:1}`; shard key và các unique-index constraints phải tương thích.
- `fs.files` và `fs.chunks` là **hai collections riêng**, có thể chịu những yêu cầu routing/placement khác nhau.
- Không tự chọn hashed shard key hoặc drop unique chunk index chỉ để sharding thành công.
- Upload/download có thể chạm nhiều shard và tạo network/coordination overhead.

Sharding GridFS là quyết định kiến trúc nâng cao; cần kiểm tra tài liệu phiên bản, dataset và workload cụ thể. Không dùng một vài lệnh `sh.shardCollection` thiếu thiết kế để thay thế runbook.

### 30.4. Nếu workload rất lớn

So sánh với object storage về:

- Giá thành/GB và chi phí egress.
- CDN, byte-range requests, signed URLs.
- Số lượng file và throughput.
- Replication đa vùng, lifecycle/archival.
- Chính sách quyền truy cập và compliance.

GridFS đáng giá khi mong muốn file storage nằm trong MongoDB cùng metadata/query/workflow; không phải lúc nào cũng rẻ hơn ở quy mô media toàn cầu.

## 31. Quyền truy cập và an toàn nội dung file

File binary không tự an toàn chỉ vì được lưu vào database.

### 31.1. Xác thực và ủy quyền

Một API download nên:

~~~text
User principal
  -> kiểm tra tenant/owner/business policy
  -> tìm fs.files bằng exact fileId
  -> xác thực metadata thuộc quyền truy cập
  -> GridFSBucket stream nội dung
  -> audit download
~~~

Đừng lấy `ownerId` trong request body để quyết định quyền; phải lấy từ session/token đã xác thực và business rules.

### 31.2. Content type và file extension

Không tin hoàn toàn `filename:"photo.jpg"` hoặc `metadata.contentType:"image/jpeg"` do client cung cấp. Nên kiểm tra magic bytes/MIME bằng cơ chế phù hợp, virus scan theo threat model và kiểm soát cách browser render file. File HTML/script nguy hiểm nếu phát trực tiếp với Content-Type không phù hợp.

### 31.3. Không log binary

Không in `fs.chunks.data` ra log, analytics hay error report. Điều đó có thể gây lộ dữ liệu người dùng, tăng log cost và làm khó điều tra.

### 31.4. Mã hóa

MongoDB có các khả năng bảo vệ kết nối/dữ liệu lưu trữ tùy deployment; nếu yêu cầu mã hóa phía ứng dụng, có thể mã hóa file trước khi upload và lưu metadata mã hóa/version key phù hợp. Đừng lưu encryption key trong `fs.files.metadata` cùng với file ciphertext.

## 32. Những vấn đề hiệu năng thường gặp

### 32.1. Truy vấn chunks không dùng index

~~~javascript
db.fs.chunks.find({ files_id: fileId }).sort({ n: 1 })
~~~

Nếu thiếu `{files_id:1,n:1}`, query có thể scan nhiều chunks của các file khác hoặc phải sort; tốc độ download giảm mạnh. Kiểm tra index tiêu chuẩn và plan.

### 32.2. File cực lớn nhưng chunk size quá nhỏ

Một file 50 GiB với chunk 8 KiB tạo hàng triệu chunks, tăng I/O/index entries. Cần chọn chunk size phù hợp khả năng memory/network và mục tiêu tải file.

### 32.3. File rất nhỏ nhưng dùng GridFS vô điều kiện

Nếu phần lớn files 1–2 KiB và số lượng rất lớn, overhead hai collections và indexes có thể không đáng. Regular collection/object storage đôi khi hợp hơn.

### 32.4. Mỗi download đều tìm filename không giới hạn

Tìm theo filename rồi lấy file mới nhất có thể bất ngờ vì tên trùng/đổi phiên bản. Dùng exact fileId đã gắn với business reference và auth.

### 32.5. Bỏ qua backpressure

Streaming không có nghĩa đường truyền luôn đủ nhanh. Cần xử lý client disconnect, giới hạn concurrent streams, request timeout và rate limits để không làm cạn connection pool hoặc tài nguyên database.

### 32.6. Index bừa bãi

Mỗi metadata field không cần một index riêng. Theo dõi `totalIndexSize`, write latency, query frequency và cache pressure.

## 33. Phân tích lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Download báo file not found | Sai fileId hoặc bucket prefix | Xem `<bucket>.files` và BSON type ID |
| Download thiếu chunk | Thiếu `n` trong `<bucket>.chunks` | Đếm/sort chunks, so `length` |
| Duplicate key khi insert chunk | Trùng `(files_id,n)` | Unique index và upload logic |
| File xuất hiện nhưng mở hỏng | Chunk bị sửa/thiếu hoặc checksum sai | Tải stream và hash, audit |
| Disk không giảm sau xóa metadata | Chunks orphan | Kiểm tra xóa qua GridFSBucket |
| Nhiều orphan chunks | Upload crash/cleanup lỗi hoặc TTL files | Audit theo grace period |
| Tìm theo filename trả nhiều file | Filename không unique | Chọn exact fileId/revision |
| Upload đầu tiên chậm bất thường | Tạo collections/indexes lần đầu | Kiểm tra migration/index |
| Download chậm khi nhiều files | Thiếu index chunks hoặc tài nguyên I/O | `explain`, metrics, index |
| Byte count lệch | Nhầm ký tự/bytes hoặc wrong chunk size | `length` và streaming checksum |
| File mới không thấy trên secondary | Replication lag/read consistency | Read preference và lag |
| Sharding báo lỗi index | Shard key/unique constraints không tương thích | Xem quy tắc phiên bản và thiết kế |
| File bị xóa trước retention | TTL trên files hoặc cleanup policy sai | Audit retention |

### 33.1. Cách khắc phục không nên làm

Không xóa hàng loạt `fs.chunks` chỉ vì một truy vấn thấy không có `fs.files` tại thời điểm đó; upload mới có thể đang ghi. Không drop unique index để cho upload đang lỗi tiếp tục. Không sửa `n` hoặc `data` bằng tay nếu không có nguồn bytes gốc và kế hoạch repair được xác minh.

## 34. Thực hành A — nhận diện schema

Cho hai documents:

~~~javascript
// Document A
{
  _id: ObjectId("6748abcd1234567890abcdef"),
  filename: "sample.bin",
  length: NumberLong("700000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:30:00Z")
}

// Document B
{
  _id: ObjectId("6748abcd1234567890abc001"),
  files_id: ObjectId("6748abcd1234567890abcdef"),
  n: 0,
  data: BinData(0, "...")
}
~~~

Trả lời:

1. Document nào thuộc `fs.files`? Document nào thuộc `fs.chunks`?
2. Trường nào liên kết hai documents?
3. Có thể dùng `filename` thay `files_id` trong chunk không? Vì sao?
4. `n=0` có ý nghĩa gì?

## 35. Thực hành B — tính số chunks

Cho `L=700000`, `C=261120`. Tính:

- Số chunks.
- Kích thước `n=0`, `n=1`, `n=2`.
- Byte offset bắt đầu của `n=2`.

Sau đó tính số chunks khi `L=0` và `L=522240`.

## 36. Thực hành C — xác định index bắt buộc

Trong những index sau, chọn hai index cốt lõi của GridFS:

~~~javascript
{ filename: 1 }
{ filename: 1, uploadDate: 1 }
{ files_id: 1, n: 1 }
{ n: 1, files_id: 1 }
{ "metadata.tenantId": 1 }
~~~

Index nào **unique**? Tại sao index khác không thể thay thế?

## 37. Thực hành D — filename trùng

Một bucket chứa ba files:

~~~text
F1: filename=invoice.pdf, uploadDate=2026-10-01
F2: filename=invoice.pdf, uploadDate=2026-11-01
F3: filename=invoice.pdf, uploadDate=2026-11-14
~~~

Yêu cầu:

- Viết query liệt kê cả ba files, sort mới nhất trước.
- Giải thích vì sao `filename` không unique.
- Thiết kế reference từ business invoice tới F2 mà không bị tự chuyển sang F3.

## 38. Thực hành E — inspect GridFSBucket sau upload

Chạy Node hoặc Java upload một file lab, sau đó trong mongosh:

~~~javascript
db.fs.files.getIndexes()
db.fs.chunks.getIndexes()
db.fs.files.find({}, { filename: 1, length: 1, chunkSize: 1, uploadDate: 1 })
~~~

Chọn một fileId thực và inspect chunks:

~~~javascript
const file = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

if (file) {
  db.fs.chunks.find(
    { files_id: file._id },
    { data: 0 }
  ).sort({ n: 1 })
}
~~~

Xác định `n` bắt đầu từ mấy, số chunks thực và trường nào biểu thị raw binary.

## 39. Thực hành F — chunk bị thiếu

Giả sử:

~~~text
fs.files:  F1 length=700000 chunkSize=261120
fs.chunks: F1 n=0, n=2
~~~

Hãy trả lời:

1. Số chunks mong đợi?
2. Unique index có phát hiện thiếu `n=1` không?
3. Download có thể gặp lỗi gì?
4. Có nên tự tạo chunk `n=1` chứa bytes rỗng không?
5. Quy trình recovery nên dùng nguồn dữ liệu nào?

## 40. Thực hành G — upload dở

Một upload bị mất mạng sau khi ghi 20 chunks; không tìm thấy files document. Hãy giải thích:

- Tại sao còn chunks mà không có file metadata?
- Tại sao không được xóa ngay mọi orphan candidate?
- Một job cleanup cần kiểm tra những thông tin nào?

## 41. Thực hành H — TTL sai

Một đội tạo:

~~~javascript
db.fs.files.createIndex(
  { uploadDate: 1 },
  { expireAfterSeconds: 86400 }
)
~~~

Hỏi:

1. Index này xóa documents trong collection nào?
2. Những chunks tương ứng có tự động được xóa không?
3. Vì sao có thể phát sinh tăng dung lượng?
4. Thiết kế một cleanup worker dùng `GridFSBucket.delete` và audit.

## 42. Thực hành I — chunk size

Một file 100 MiB có `chunkSize=255 KiB`. Tính số chunks dự kiến. Sau đó giả sử đổi chunk size thành 1 MiB:

- Số chunks thay đổi thế nào?
- Chi phí index/operation có thể thay đổi ra sao?
- Có thể kết luận throughput tăng 4 lần không?
- Driver tải file cũ dùng chunk size mới hay giá trị trong `fs.files`?

## 43. Thực hành J — bảo mật và metadata index

Thiết kế:

~~~javascript
metadata: {
  tenantId: "t-01",
  ownerId: "user-18",
  contentType: "application/pdf",
  expiresAt: ISODate("2027-01-01T00:00:00Z")
}
~~~

Viết một query tìm files của owner theo tenant, sort mới nhất. Chọn index bổ sung thích hợp. Giải thích vì sao `metadata.ownerId` **không tự cấp quyền** cho người dùng.

## 44. Thực hành K — custom bucket

Một service upload vào bucket `exports`. Hãy điền tên hai collections và hai chỉ mục GridFS tiêu chuẩn. Nếu download dùng bucket `fs`, điều gì xảy ra? Có thể tồn tại cùng fileId ở hai bucket khác nhau không?

## 45. Thực hành L — integrity

Upload một file, tính SHA-256 ở client rồi lưu `metadata.sha256`. Khi tải xuống, tính lại SHA-256 từ stream:

- Khi nào hai checksum phải khớp?
- Nếu bytes tải ra thiếu/chuyển đổi, triệu chứng là gì?
- Vì sao MD5 legacy không nên là rào kiểm tra integrity duy nhất?
- Vì sao SHA-256 lưu cùng metadata chưa đủ chống attacker có quyền sửa cả file và checksum?

## 46. Gợi ý đáp án thực hành

**A:** Document A thuộc `fs.files`; document B thuộc `fs.chunks`. `files_id` bằng `files._id`; `n=0` là chunk đầu. Filename có thể trùng nên không thay định danh.

**B:** Ba chunks. `n=0` 261120 bytes, `n=1` 261120, `n=2` 177760; offset `n=2` bằng 522240. File rỗng: 0 chunks. File 522240 bytes: 2 chunks.

**C:** `{filename:1,uploadDate:1}` trên files **không unique**; `{files_id:1,n:1}` trên chunks **unique**. Các index khác không thay đúng query/index invariant.

**D:** `find({filename:"invoice.pdf"}).sort({uploadDate:-1})`; lưu `fileId=F2` trong business reference để luôn tải đúng bản.

**E:** Chỉ mục phải có dạng files filename/uploadDate và chunks files_id/n unique. `n` bắt đầu 0; `data` là BSON binary. Số chunks kiểm tra theo `length/chunkSize` của file thật.

**F:** Mong đợi 3 chunks, thiếu `n=1`. Unique index không phát hiện gap. Download có thể lỗi missing chunk/corruption. Không bịa bytes; khôi phục từ nguồn file gốc hoặc bản backup nhất quán.

**G:** Chunks được ghi trước metadata; upload chưa hoàn tất. Orphan candidate có thể là upload vẫn đang chạy. Cần active intent, tuổi dữ liệu, grace period, backup và batch cleanup.

**H:** TTL trên `fs.files` chỉ xóa metadata, có thể để orphan chunks. Cleanup worker phải tìm file hết hạn rồi xóa qua GridFS API, retry và audit/reconcile.

**I:** 100 MiB với 255 KiB cần 402 chunks; với 1 MiB cần 100 chunks. Ít chunk có thể giảm operations/index entries, nhưng không kết luận throughput theo tỉ lệ. Driver đọc `chunkSize` đã lưu cho từng file.

**J:** Query theo `metadata.tenantId`, `metadata.ownerId` và sort `uploadDate:-1`; index ứng viên `{ "metadata.tenantId":1, "metadata.ownerId":1, uploadDate:-1 }`. Authorization do app kiểm tra theo principal, không phải MongoDB tự áp từ metadata.

**K:** `exports.files`, `exports.chunks`, với indexes filename/uploadDate và files_id/n unique. Bucket `fs` không tự nhìn thấy file của `exports`. `_id` chỉ unique trong từng collection; cần kết hợp bucketName với fileId nếu ID có thể tồn tại ở nhiều bucket.

**L:** SHA-256 upload/download phải khớp nếu bytes không đổi. Chênh checksum cho thấy dữ liệu sai hoặc metadata/hash bị tính khác. MD5 legacy không đáp ứng yêu cầu integrity hiện đại; cần access controls/signatures nếu threat model có attacker sửa cả data và hash.

## 47. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Lưu file 100 MiB trong một BSON document | Vượt 16 MiB | Dùng GridFS hoặc object storage |
| Nghĩ GridFS chỉ có `fs.files` | Không hiểu chunks/data | Luôn xét cả hai collections |
| Dùng `filename` làm unique ID | Version/name collisions | Lưu và tải bằng exact fileId |
| Dùng `n` làm ID toàn collection | Các file đều bắt đầu n=0 | Dùng `(files_id,n)` |
| Bỏ unique chunk index | Trùng chunk position, download không xác định | `{files_id:1,n:1} unique` |
| Đặt unique trên filename | Không upload được version trùng tên | Files filename/uploadDate index thường |
| Sort chunks theo `_id` | Sai thứ tự byte | Sort `n` tăng dần |
| Không kiểm tra BSON type của files_id | Query miss dù ID nhìn giống | Dùng cùng BSON ID |
| Giả định mọi file có 255 KiB chunk | Cấu hình có thể khác | Đọc `files.chunkSize` |
| Hiểu 255 KiB là 255000 bytes | Sai số chunk count/offset | 261120 bytes |
| Tin unique index ngăn mọi corruption | Missing chunk/data vẫn sai | Verify count/sequence/size/hash |
| Publish fileId trước khi stream xong | Business record trỏ tới upload chưa hoàn tất | Publish sau thành công |
| Xóa thẳng `fs.files` | Để orphan chunks | GridFSBucket.delete |
| Xóa thẳng `fs.chunks` | Metadata còn, file hỏng | GridFSBucket.delete |
| TTL chỉ trên files | Metadata mất, chunks còn | Cleanup worker qua GridFS API |
| Xóa mọi orphan ngay | Có thể xóa upload đang hoạt động | Grace period, active intents, audit |
| Nạp toàn file vào RAM | OOM/GC pressure | Streaming |
| Tin file extension để chọn MIME | Content unsafe | Validate/scan/content policy |
| Coi metadata tenant là ACL tự động | Lộ file cross-tenant | Authz trước download |
| Dựa vào MD5 legacy | Không bảo đảm integrity hiện đại | App SHA-256 và security controls |
| Backup files/chunks ở thời điểm khác nhau | Orphans/missing data sau restore | Consistent backup |
| Cho rằng GridFS tự dedupe | Tốn storage, duplicate uploads | Stable ID/dedupe architecture nếu cần |
| Tăng chunk size sát 16 MiB | Vượt BSON limit, memory pressure | Chọn size có headroom |
| Drop chunk unique index để sharding | Phá invariant GridFS | Thiết kế theo shard-key constraints |

## 48. Câu hỏi ôn tập

**1. GridFS dùng để làm gì?** — Chia file thành nhiều BSON chunks để lưu/stream file lớn hơn giới hạn một document hoặc phục vụ file streaming.

**2. Hai collections mặc định tên gì?** — `fs.files` và `fs.chunks`.

**3. Nếu bucket tên `images`?** — `images.files` và `images.chunks`.

**4. `fs.files` lưu bytes gốc trong field nào?** — Không có field chứa toàn bộ bytes; bytes nằm trong `fs.chunks.data`.

**5. Trường nào liên kết chunks với file?** — `fs.chunks.files_id` bằng `fs.files._id`, cùng BSON type/value.

**6. `n` có bắt đầu từ 1 không?** — Không, bắt đầu từ **0**.

**7. Chỉ mục chunks cần có key pattern nào?** — `{files_id:1,n:1}`.

**8. Chunk index có unique không?** — **Có**, trên cặp `(files_id,n)`.

**9. Chỉ mục files tiêu chuẩn là gì?** — `{filename:1,uploadDate:1}`, **không unique**.

**10. Vì sao filename không unique?** — Cho phép upload nhiều files/version có cùng tên.

**11. `_id_` của fs.chunks có thay được chunk compound index không?** — Không, vì nó không hỗ trợ filter/sort theo fileId và n.

**12. Default chunk size thường là bao nhiêu?** — **255 KiB = 261120 bytes**.

**13. File dài 700000 bytes với chunk 261120 cần bao nhiêu chunks?** — **3**.

**14. Chunk cuối của file đó dài bao nhiêu?** — **177760 bytes**.

**15. File rỗng có bao nhiêu chunks?** — **0**.

**16. Tại sao không dùng unique `{n:1}`?** — Vì mỗi file đều có `n=0`, `n=1`; unique phải kèm files_id.

**17. Unique index có tự phát hiện missing chunk không?** — Không; nó chỉ ngăn duplicate key positions.

**18. Có được xóa file bằng `db.fs.files.deleteOne` không?** — Không nên; có thể để chunks mồ côi. Dùng GridFS API.

**19. TTL trên files có xóa chunks không?** — Không tự động; cần cleanup worker dùng GridFSBucket.delete.

**20. Vì sao fileId được cấp trước khi upload hoàn tất chưa đủ để publish?** — Vì stream còn có thể lỗi và chưa có files document hoàn chỉnh.

**21. `metadata.contentType` có được MongoDB xác thực file thật không?** — Không; đó là metadata ứng dụng.

**22. Có thể upload file lớn trong một transaction khổng lồ không?** — Không nên; GridFS không phải cơ chế transaction toàn file, và transaction có giới hạn tài nguyên/lifetime.

**23. Khi nào chọn object storage thay vì GridFS?** — Khi cần CDN/signed URLs/lifecycle/media scale hoặc chi phí theo GB tốt hơn, tùy workload.

**24. Sharding GridFS cần quan tâm gì?** — Unique chunk index, shard-key constraints, routing, version và sự nhất quán của hai collections.

**25. Kiểm tra file toàn vẹn bằng cách nào?** — Tải stream, kiểm tra byte length/chunk sequence và hash SHA-256 theo policy.

## 49. Bảng lệnh ghi nhớ

| Mục tiêu | Câu lệnh/khái niệm |
|---|---|
| Xem files metadata | `db.fs.files.find()` |
| Xem chunks của một file | `db.fs.chunks.find({files_id:fileId}).sort({n:1})` |
| Đếm chunks | `db.fs.chunks.countDocuments({files_id:fileId})` |
| Chỉ mục files | `db.fs.files.createIndex({filename:1,uploadDate:1})` |
| Chỉ mục chunks | `db.fs.chunks.createIndex({files_id:1,n:1},{unique:true})` |
| Xem indexes | `getIndexes()` |
| Đo query plan | `explain("executionStats")` |
| Upload Node | `bucket.openUploadStream(filename,options)` |
| Download Node | `bucket.openDownloadStream(fileId)` |
| Xóa Node | `bucket.delete(fileId)` |
| Upload Java | `bucket.uploadFromStream(filename,input,options)` |
| Download Java | `bucket.downloadToStream(fileId,output)` |
| Default chunk size | 255 KiB = 261120 bytes |
| Số chunks | `ceil(length/chunkSize)` |
| Byte offset của chunk n | `n*chunkSize` |
| Kiểm tra integrity | SHA-256 streaming ở application |
| Xóa theo retention | Worker tìm candidates rồi GridFSBucket.delete |

## 50. Checklist trước khi dùng GridFS trên production

- [ ] File có thực sự cần GridFS hay object storage/regular BinData phù hợp hơn?
- [ ] Đã xác định bucket prefix và dùng đồng nhất khi upload/download/delete?
- [ ] `<bucket>.files` và `<bucket>.chunks` đều có indexes tiêu chuẩn?
- [ ] `{files_id:1,n:1}` ở chunks là **unique**?
- [ ] `{filename:1,uploadDate:1}` ở files **không unique**?
- [ ] Mọi business reference lưu exact fileId (và bucketName nếu có nhiều bucket)?
- [ ] `length` được hiểu là bytes, không phải ký tự hay số chunks?
- [ ] Đã chọn chunk size có headroom dưới giới hạn BSON, benchmark theo workload?
- [ ] Có streaming upload/download và xử lý backpressure/disconnect?
- [ ] Chỉ publish file sau khi upload thành công và verify cần thiết?
- [ ] Có quota/file size limit và rate limit ở API?
- [ ] Có metadata owner/tenant từ auth context, authorization trước download?
- [ ] Có kiểm soát MIME/file extension, scanning và response headers an toàn?
- [ ] Có checksum SHA-256 hoặc integrity policy phù hợp, không phụ thuộc MD5 legacy?
- [ ] Có xử lý file name trùng và revision rõ ràng?
- [ ] Có chính sách upload retry và trạng thái PENDING/READY/FAILED?
- [ ] Có reconciliation cho orphan chunks/file references chưa publish?
- [ ] Không đặt TTL chỉ lên files rồi bỏ lại chunks?
- [ ] Xóa qua GridFSBucket API, có audit và retry nếu thất bại một phần?
- [ ] Có backup nhất quán của cả hai collections và thử restore?
- [ ] Nếu sharded, đã kiểm tra unique-index/shard-key compatibility?
- [ ] Có metrics ingest/download throughput, p95/p99 latency, bytes, chunks và storage?
- [ ] Có kế hoạch vận hành khi index creation/driver upgrade gặp thay đổi?
- [ ] Không in binary data, secrets hoặc tọa độ/PII không cần thiết ra logs?

## 51. Kết luận

GridFS lưu file trong MongoDB bằng cách **tách thông tin file khỏi các byte dữ liệu**. `fs.files` chứa định danh, tổng kích thước, chunk size, thời điểm upload, filename và metadata; `fs.chunks` chứa các đoạn binary được liên kết bằng `files_id` và sắp thứ tự theo `n`. Kết hợp hai collection cho phép lưu/stream file vượt giới hạn **16 MiB của một BSON document** mà không phải tải toàn file vào RAM.

Hai chỉ mục cốt lõi giữ cho thiết kế này vận hành đúng: **`{files_id:1,n:1}` unique** trên chunks để đọc dữ liệu đúng thứ tự và không lặp vị trí, và **`{filename:1,uploadDate:1}` non-unique** trên files để tìm tên cùng các phiên bản upload. Chúng không thay thế nhau, và không index nào tự chứng minh file có đủ chunks hoặc mọi bytes toàn vẹn.

Trong ứng dụng thực tế, hãy dùng **GridFSBucket API** cho upload, download và delete; lưu **fileId** làm tham chiếu, stream thay vì buffer cả file, verify integrity khi cần, xử lý upload dở/orphan chunks, tránh TTL sai gây rò rỉ dung lượng và bảo vệ metadata theo quyền tenant. Khi workload lớn, đánh giá chunk size, index size, replication/sharding, backup và khả năng dùng object storage trước khi quyết định kiến trúc cuối cùng.
