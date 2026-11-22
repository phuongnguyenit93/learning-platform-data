# Xóa tệp, phát hiện phần dữ liệu mồ côi và xử lý tải lên dang dở trong MongoDB GridFS

## 1. Bài toán mở đầu: upload bị ngắt giữa chừng

Một ứng dụng quản lý hợp đồng cho phép người dùng tải lên tệp PDF 40 MiB. Ứng dụng lưu tệp bằng **GridFS**, một cơ chế lưu tệp thành nhiều document nhỏ trong MongoDB. Khi nhận được khoảng 25 MiB, đường truyền ngắt và tiến trình API bị khởi động lại.

Người dùng nhìn thấy thông báo “tải lên thất bại”. Nhưng kiểm tra dung lượng MongoDB thấy collection lưu chunk vẫn lớn lên. Một nhân viên định xử lý bằng lệnh:

```javascript
// NGUY HIỂM: Không bao giờ xóa tất cả chunks như thế này.
db.fs.chunks.deleteMany({});
```

Lệnh đó có thể xóa nội dung của **mọi tệp** trong bucket, kể cả những tệp hợp lệ.

Tình huống trên dẫn tới ba câu hỏi khác nhau:

1. **Xóa tệp đúng cách:** khi người dùng yêu cầu xóa một tệp đã lưu hoàn chỉnh, phải xóa những gì?
2. **Phát hiện dữ liệu mồ côi:** làm sao tìm những chunk không còn bản ghi tệp tương ứng, nhưng không nhầm với chunk của một upload vẫn đang chạy?
3. **Tải lên dang dở:** khi ứng dụng hủy upload, gặp lỗi ghi, mất kết nối hoặc bị crash, làm sao xử lý trạng thái và khôi phục an toàn?

Bài học **“Xóa tệp, phát hiện phần dữ liệu mồ côi và xử lý tải lên dang dở”** nằm trong chương **GridFS** của module **Database Engine Document MongoDB**. Sau bài, bạn có thể:

- Nhận diện cấu trúc `<bucket>.files` và `<bucket>.chunks`, các khóa liên kết và index.
- Hiểu chính xác khi nào metadata tệp được tạo và vì sao upload đang chạy trông giống “orphan”.
- Sử dụng API GridFSBucket để xóa tệp theo `_id`, không xóa chỉ theo `filename`.
- Sử dụng cơ chế `abort()` của upload stream khi chủ động hủy.
- Phân biệt **orphan chunks**, **tệp thiếu chunk**, **chunk dư**, và **tệp hoàn chỉnh nhưng không còn tham chiếu nghiệp vụ**.
- Viết báo cáo ứng viên orphan bằng aggregation **chỉ đọc** và kiểm tra toàn vẹn tệp.
- Thiết kế upload ledger/lease, idempotency và cleanup job tránh cạnh tranh với uploader.
- Xây runbook dọn rác có giới hạn phạm vi, quan sát trước và xác nhận sau.
- Đánh giá tác động của replication, backup, bảo mật và yêu cầu lưu giữ dữ liệu.

## 2. GridFS lưu một tệp như thế nào?

### 2.1. Một bucket gồm hai collection

Theo quy ước GridFS, bucket mặc định có tên `fs`, chứa:

```text
database
  |
  +-- fs.files      // metadata của mỗi tệp hoàn chỉnh
  |
  +-- fs.chunks     // những mảnh dữ liệu nhị phân
```

Nếu ứng dụng tạo bucket tên `contracts` thì hai collection tương ứng là `contracts.files` và `contracts.chunks`. Trong cùng database có thể tồn tại nhiều bucket. Vì vậy **không mặc định mọi chunk nằm trong `fs.chunks`**.

Một tệp được chia thành các chunk có kích thước mặc định thường là **255 KiB**; chunk cuối có thể nhỏ hơn. Kích thước chunk có thể được cấu hình khi upload.

### 2.2. Document trong `files`

Ví dụ metadata của tệp đã upload thành công:

```javascript
{
  _id: ObjectId("66a000000000000000000323"),
  filename: "hop-dong-2026.pdf",
  length: NumberLong("420000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T03:20:00Z"),
  metadata: {
    tenantId: "TENANT-A",
    documentType: "contract",
    sha256: "..."
  }
}
```

Ý nghĩa:

| Field | Vai trò |
| --- | --- |
| `_id` | **File ID** duy nhất trong `files`, được chunk tham chiếu qua `files_id` |
| `filename` | Tên hiển thị, **không bắt buộc duy nhất** |
| `length` | Tổng số byte của nội dung tệp |
| `chunkSize` | Số byte tối đa cho một chunk của tệp |
| `uploadDate` | Thời điểm hoàn tất upload theo đặc tả GridFS |
| `metadata` | Dữ liệu tùy ứng dụng: quyền sở hữu, loại tệp, checksum, v.v. |

File ID thường là BSON `ObjectId`, nhưng ứng dụng có thể dùng một kiểu ID khác được driver hỗ trợ. Khi so sánh `fs.files._id` với `fs.chunks.files_id` cần **giữ nguyên kiểu BSON**. Chuỗi `"abc"` không đồng nhất với một BSON ObjectId hoặc UUID có biểu diễn ký tự tương tự.

### 2.3. Document trong `chunks`

Ví dụ một phần của tệp:

```javascript
{
  _id: ObjectId("66b000000000000000000001"),
  files_id: ObjectId("66a000000000000000000323"),
  n: 0,
  data: BinData(0, "...")
}
```

Các trường chính:

- `_id`: ID riêng của chunk.
- `files_id`: tham chiếu đến `_id` của document `files`.
- `n`: thứ tự chunk, **bắt đầu từ 0**.
- `data`: dữ liệu nhị phân của chunk.

Sơ đồ:

```text
contracts.files
  _id: F123
  filename: hop-dong.pdf
  length: 420000
  chunkSize: 261120
           |
           | files_id = F123
           v
contracts.chunks
  { files_id: F123, n: 0, data: 261120 bytes }
  { files_id: F123, n: 1, data: 158880 bytes }
```

Để tải xuống, driver tìm metadata theo file ID, đọc các chunk theo `n` rồi ghép dữ liệu. Nếu mất một chunk ở giữa, việc tái tạo nội dung có thể thất bại.

### 2.4. Hai index quan trọng

GridFS sử dụng:

```javascript
// Trên collection chunks của bucket "fs":
db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);

// Trên collection files:
db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 }
);
```

Driver GridFS tương thích đặc tả thường tự bảo đảm index cần thiết theo quy tắc phiên bản và khi collection ở trạng thái phù hợp. Trong production, không tạo lại index một cách mù quáng; trước hết xem `getIndexes()` và tình trạng dữ liệu.

Index `{files_id:1,n:1}` giúp tải chunk theo thứ tự và không cho hai chunk cùng `files_id` có cùng số `n`. Nó **không tạo foreign key**: MongoDB vẫn có thể chứa chunk mà `files_id` không có parent trong `files`.

### 2.5. GridFS không hỗ trợ multi-document transactions

Đây là giới hạn quan trọng: **GridFS không hỗ trợ multi-document transactions** theo tài liệu MongoDB GridFS, dù MongoDB nói chung hỗ trợ transaction giữa nhiều document/collection.

Không viết:

```javascript
// KHÔNG xem đây là giải pháp nguyên tử cho toàn bộ GridFS upload.
await session.withTransaction(async () => {
  await bucket.uploadFromStream(...);
  await otherCollection.insertOne(..., { session });
});
```

GridFS lưu/chỉnh nhiều chunk và metadata bằng quy trình riêng. Không giả định một `GridFSBucket` upload/delete có thể được đưa vào transaction MongoDB để biến mọi chunk và mọi document nghiệp vụ thành một thay đổi nguyên tử.

Muốn phối hợp với collection nghiệp vụ, hãy thiết kế **trạng thái quy trình, idempotency, kiểm tra sau ghi và reconciliation**.

## 3. Vòng đời upload: điều gì xảy ra trước khi tệp hoàn tất?

### 3.1. Chunks được ghi trước, files metadata được ghi cuối

Theo đặc tả GridFS, driver upload dữ liệu theo trình tự khái niệm:

```text
T0: mở upload stream, cấp fileId
            |
T1: ghi chunk n=0 vào <bucket>.chunks
            |
T2: ghi chunk n=1
            |
T3: ghi chunk n=2
            |
        ... nhiều chunk ...
            |
T4: nguồn dữ liệu kết thúc và driver flush thành công
            |
T5: driver tạo document trong <bucket>.files
            |
T6: upload stream hoàn tất thành công
```

**Document `files` chỉ được tạo sau khi các chunk của tệp đã được ghi hoàn tất.** `uploadDate` biểu thị thời điểm upload hoàn tất, **không phải** thời điểm bắt đầu.

Đối với tệp rỗng có `length:0`, driver tạo document `files` mà **không có chunk dữ liệu**. Đây là trạng thái hợp lệ.

### 3.2. Vì sao chunk không có parent chưa chắc là rác?

Tại thời điểm T2:

```text
fs.chunks:
  { files_id: F123, n: 0 }
  { files_id: F123, n: 1 }

fs.files:
  // Chưa có document _id F123
```

Một job chạy ngay tại thời điểm này sẽ thấy **hai chunk có files_id không tồn tại trong files**. Nhưng upload vẫn đang hoạt động; nếu job xóa chúng, nó sẽ làm hỏng tệp đang được ghi.

Do đó:

> “Không tìm thấy parent ở `files`” là một **dấu hiệu để điều tra**, không phải bằng chứng đầy đủ rằng chunk có thể xóa ngay.

Phải kết hợp trạng thái upload, tuổi dữ liệu, khả năng có writer đang hoạt động và chính sách phối hợp cleanup.

### 3.3. Các trạng thái kết thúc

| Trường hợp | `files` | `chunks` | Kết luận |
| --- | --- | --- | --- |
| Upload đang chạy | Thường chưa có | Có thể có một phần | **Không xóa** |
| Upload hoàn tất tệp có dữ liệu | Có | Đầy đủ | Bình thường |
| Upload hoàn tất tệp rỗng | Có, `length:0` | Không có | Bình thường |
| Upload bị hủy có cleanup thành công | Không có | Không còn | Bình thường |
| Upload lỗi giữa chừng, cleanup không thành công | Có thể không có | Có thể còn | Ứng viên orphan |
| Upload hoàn tất nhưng ứng dụng chưa lưu reference | Có | Đầy đủ | Unreferenced ở **tầng ứng dụng**, không phải orphan GridFS |
| Tệp bị xóa dở dang | Có thể đã mất parent | Có thể còn chunk | Ứng viên orphan do delete lỗi |
| Metadata tồn tại nhưng thiếu chunk | Có | Thiếu hoặc sai thứ tự | **Corruption/inconsistency**, không phải orphan chunks |

## 4. Xóa một tệp đã upload đúng cách

### 4.1. Dùng GridFSBucket API theo file ID

Với Node.js MongoDB driver:

```javascript
import { GridFSBucket, ObjectId } from "mongodb";

const bucket = new GridFSBucket(db, {
  bucketName: "contracts"
});

const fileId = new ObjectId("66a000000000000000000323");

await bucket.delete(fileId);
```

`bucket.delete(fileId)` là API để xóa **document metadata của một tệp cùng các chunk liên quan**. File ID phải thuộc bucket bạn chọn.

Không dùng tên tệp làm khóa xóa:

```javascript
// Sai ý định: filename không duy nhất, không phải ID mong đợi.
await bucket.delete("hop-dong.pdf");
```

Hai lần upload với cùng `filename` có thể tạo **hai file ID khác nhau**. Một số API của driver hỗ trợ thao tác theo tên/tất cả revisions, nhưng phải kiểm tra chính xác hợp đồng theo driver; để xóa **một bản** cụ thể, chọn `_id`.

### 4.2. Thứ tự xóa trong đặc tả

Đặc tả GridFS quy định khi delete, driver xóa:

1. Document trong `<bucket>.files` trước.
2. Các document có `files_id = fileId` trong `<bucket>.chunks` sau.

Mục đích giảm cửa sổ mà người đọc vẫn thấy metadata nhưng nội dung chunk đã bị xóa. Tuy nhiên, **không có một transaction chung bao trùm cả hai collection**.

```text
Trước:
    files(F123) + chunks(F123,n=0..N)
                 |
          bucket.delete(F123)
                 |
     xóa metadata files(F123)
                 |
     xóa chunks(files_id=F123)
                 |
Sau:
    không còn parent hoặc chunk cho F123
```

Nếu tiến trình hoặc kết nối hỏng **sau khi metadata đã bị xóa nhưng trước khi chunks được dọn hết**, có thể còn những chunk mồ côi.

### 4.3. Không đồng nhất “delete trả lỗi” với “chưa xóa gì”

Một delete có thể gặp:

- Không tìm thấy file document.
- Timeout khi xóa metadata hoặc chunks.
- Mất phản hồi mạng sau khi server đã thực hiện một phần.
- Lỗi primary failover.
- Quyền xóa hoặc storage issue.
- Reader khác đang tải tệp.

Nếu nhận lỗi, trạng thái cuối **có thể chưa rõ**. Một lần retry `bucket.delete(fileId)` có thể gặp lỗi **FileNotFound** vì document `files` đã bị xóa ở lần trước. Điều này không đủ chứng minh mọi chunk đã biến mất.

Cần đối soát cả:

```javascript
const parent = await db.collection("contracts.files").findOne({
  _id: fileId
});

const remainingChunks = await db.collection("contracts.chunks")
  .countDocuments({
    files_id: { $eq: fileId }
  });

console.log({
  fileMetadataExists: Boolean(parent),
  remainingChunks
});
```

Đặc tả cho phép một số driver cố dọn orphan chunks dù không thấy metadata, nhưng không được **phụ thuộc vào hành vi đó ở mọi driver/version**. Quyết định khôi phục phải dựa trên trạng thái thực và quyền sở hữu file ID.

### 4.4. Reader và delete chạy đồng thời

Có một race tự nhiên:

```text
Reader A: đọc files(F123)
Deleter B: xóa files(F123)
Deleter B: xóa chunks(F123)
Reader A: đọc chunks(F123)
          -> chunk có thể đã mất
```

GridFS không hứa mọi download đang chạy sẽ tự được bảo vệ đến cuối nếu một actor khác xóa tệp đó. Nếu ứng dụng cần bảo đảm download hoàn tất trước khi xóa, hãy dùng trạng thái nghiệp vụ, giới hạn lượt đọc, grace period hoặc cơ chế điều phối phù hợp.

### 4.5. Xóa theo quyền sở hữu và trạng thái ứng dụng

Một handler production không nên tin `fileId` từ client là đủ quyền xóa.

Quy trình gợi ý:

1. Xác thực người dùng và tenant.
2. Kiểm tra tài liệu tham chiếu thuộc quyền sở hữu.
3. Kiểm tra retention/legal hold.
4. Đánh dấu trạng thái nghiệp vụ `DELETING` hoặc ghi tombstone.
5. Chặn các download/link mới theo trạng thái đó.
6. Xóa GridFS bằng `bucket.delete(fileId)`.
7. Đối soát metadata/chunks.
8. Đánh dấu `DELETED` khi xác minh thành công.
9. Ghi audit event tối thiểu, không log nội dung nhạy cảm.

Không hứa rằng xóa GridFS đồng nghĩa byte đã được xóa vật lý ngay ở backup, snapshot, cache, CDN hoặc hệ lưu trữ phụ. Các hệ đó có retention và quy trình hủy dữ liệu riêng.

### 4.6. Tệp đang được tham chiếu ở nhiều nơi

Ví dụ:

```text
Attachment A -> GridFS file F123
Attachment B -> GridFS file F123
Document C   -> GridFS file F123
```

Xóa F123 khi người dùng chỉ xóa Attachment A có thể làm hỏng B và C. Nếu tệp được chia sẻ, cần chính sách **reference ownership/reference count hoặc registry** rõ ràng.

Không dùng một phép `countDocuments({fileId})` đơn lẻ giữa các thao tác ghi concurrent như bằng chứng không có reference nữa; phải điều phối việc thêm/xóa reference.

## 5. Phân biệt các loại dữ liệu “mồ côi”

### 5.1. Orphan chunk theo đặc tả GridFS

**Orphan chunk** là document trong `chunks` có `files_id` không tương ứng với bất kỳ `_id` trong `files`.

```text
chunks:
   C1 -> files_id: F123

files:
   không có _id F123

=> C1 là orphan candidate theo quan hệ GridFS
```

Nhưng cần nhớ cửa sổ upload đang hoạt động có cùng biểu hiện; muốn **xóa**, phải có thêm bằng chứng file ID không còn đang được ghi.

### 5.2. Tệp có metadata nhưng chunk bị thiếu

```text
files:
  F123 length=600000 chunkSize=261120

expected chunks:
  n=0, n=1, n=2

actual chunks:
  n=0, n=2
```

Đây là **missing chunk**, không phải orphan theo định nghĩa. Tệp có thể không đọc được trọn vẹn. **Không được xóa `fs.files` để biến nó thành orphan rồi dọn** như cách “sửa lỗi” tự động.

Cần khôi phục từ bản gốc/backup hoặc yêu cầu upload lại, kiểm tra tác động nghiệp vụ và ghi nhận tình trạng hỏng dữ liệu.

### 5.3. Tệp có chunk dư

```text
files:
  F123 length=420000 chunkSize=261120
  => cần n=0, n=1

actual chunks:
  n=0, n=1, n=2
```

Chunk `n=2` là chunk dư so với metadata, nhưng `files_id` **vẫn có parent hợp lệ**, nên nó không được phát hiện bởi truy vấn chỉ tìm “không có parent”.

Cần quy trình integrity scan riêng. Một số driver có thể không kiểm tra mọi chunk dư khi tải xuống; không suy luận “download thành công” nghĩa mọi chunk dư/độ dài metadata đều hợp lệ.

### 5.4. Tệp hoàn chỉnh nhưng không có reference nghiệp vụ

Ví dụ `fs.files` có F123 và các chunk đầy đủ, nhưng collection `attachments` không còn record nào trỏ đến F123.

Đây là **application-level unreferenced file**, không phải orphan chunk. Có thể là:

- Upload hoàn tất nhưng API chết trước khi tạo attachment.
- File thuộc một bản nháp chưa được publish.
- File còn cần cho audit hoặc retention.
- Tham chiếu nằm trong collection/service khác.
- Tệp đang chờ nhân viên duyệt.
- Registry còn chậm đồng bộ.

Muốn dọn phải xem **lifecycle và reference của ứng dụng**, không chỉ xem foreign key tại một collection.

### 5.5. Reference nghiệp vụ trỏ tới file ID không tồn tại

Trường hợp ngược lại:

```text
attachments:
  { _id: A1, fileId: F123, status: AVAILABLE }

GridFS files:
  không có F123
```

Đây là **dangling application reference**. Cần trả lỗi download có kiểm soát, kiểm tra lại GridFS chunks, đối soát upload/delete và sửa business state. Không tạo một document `fs.files` rỗng để “vá” cho có parent.

### 5.6. Ma trận chẩn đoán

| Files doc | Chunks | App reference | Tình huống |
| --- | --- | --- | --- |
| Có | Đủ | Có | Bình thường |
| Có | 0, `length=0` | Có/không | Tệp rỗng hợp lệ |
| Không | 0 | Không | Chưa upload hoặc đã xóa sạch |
| Không | Có | Có/không | **Orphan candidate**; cần kiểm tra active upload |
| Có | Thiếu/sai `n` | Có/không | Tệp hỏng/inconsistent |
| Có | Đủ | Không | Unreferenced, không phải orphan GridFS |
| Không | 0 | Có | Dangling reference nghiệp vụ |

## 6. Vì sao GridFS có thể để lại orphan chunks?

### 6.1. Upload lỗi giữa chừng

Một quá trình upload có thể tạo vài chunk rồi gặp lỗi:

```text
insert chunk 0 -> success
insert chunk 1 -> success
insert chunk 2 -> network error
              -> không tạo files document
```

Đặc tả GridFS quy định khi **thao tác ghi lên server thất bại**, driver phải trả lỗi; nó **không bắt buộc và không nên cố dọn mọi chunk đã ghi thành công** trước khi báo lỗi gốc, vì nguyên nhân lỗi có thể cũng cản trở cleanup.

Kết quả là những chunk đã ghi có thể tồn tại mà không có parent. Đây là một lý do cần có **job reconciliation định kỳ**.

### 6.2. Process crash

Nếu process bị kill, pod bị terminate cứng, máy mất điện hoặc kết nối bị cắt trước khi client kịp gọi cơ chế abort, **không có lời gọi abort nào chắc chắn đã chạy**.

Không được hiểu `finally` trong code là bảo đảm tuyệt đối: `finally` không được thực thi khi process crash theo những cách nhất định.

### 6.3. Abort cũng có thể thất bại

Khi ứng dụng chủ động hủy upload, driver có thể xóa các chunk đã ghi. Nhưng nếu chính thao tác xóa gặp network/server error thì cleanup có thể không hoàn tất.

Phải lưu trạng thái **cần đối soát**, thay vì ngay lập tức báo “đã xóa mọi chunk” chỉ vì client đã gửi lệnh abort.

### 6.4. Delete không hoàn tất

Một thao tác delete có thể xóa `files` trước rồi thất bại ở bước xóa `chunks`. Các chunk còn lại không có parent và sẽ được tính là orphan.

### 6.5. Ghi/xóa thủ công sai

Các lệnh tự sửa dữ liệu như:

```javascript
// Không dùng trong production để xóa tệp GridFS.
db.fs.files.deleteOne({ filename: "hop-dong.pdf" });

// Càng không được:
db.fs.chunks.deleteMany({});
```

có thể để lại orphan hoặc làm hỏng tệp. Driver GridFS quản lý hai collection như một định dạng lưu trữ, không phải hai bảng độc lập để sửa tùy ý.

## 7. Hủy một upload đang chạy bằng API driver

### 7.1. `abort()` khác `delete()`

- `abort()`: áp dụng cho **upload stream còn đang mở/chưa hoàn tất**, nhằm hủy việc ghi và dọn các chunk đã upload.
- `bucket.delete(fileId)`: áp dụng để **xóa một tệp đã được lưu** theo file ID, gồm metadata và chunks.

Không gọi `abort()` sau khi upload stream đã hoàn tất rồi kỳ vọng xóa tệp thành công. Trong Node.js driver, upload stream có thể báo lỗi nếu abort sau khi hoàn thành hoặc abort hai lần.

### 7.2. Ví dụ Node.js về hủy chủ động

Ví dụ dưới đây dùng MongoDB Node.js driver hiện đại, một bucket thử nghiệm cô lập và một chunk lớn hơn `chunkSizeBytes` để minh họa. Nó **không cần gây lỗi mạng**:

```javascript
import {
  MongoClient,
  GridFSBucket,
  ObjectId
} from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);

await client.connect();

try {
  const lab = client.db("mongo_gridfs_row323_lab");
  const runId = new ObjectId().toHexString();
  const bucketName = "row323_" + runId;

  const bucket = new GridFSBucket(lab, {
    bucketName
  });

  const stream = bucket.openUploadStream(
    "cancelled.bin",
    {
      chunkSizeBytes: 255 * 1024,
      metadata: {
        runId,
        purpose: "abort-demo"
      }
    }
  );

  const fileId = stream.id;

  // Gửi dữ liệu nhưng KHÔNG end() stream.
  // Callback cho biết lượt write được xử lý bởi writable.
  await new Promise((resolve, reject) => {
    stream.write(
      Buffer.alloc(300 * 1024, 0x2a),
      (error) => error ? reject(error) : resolve()
    );
  });

  // Chỉ gọi MỘT lần, trước khi stream hoàn tất.
  await stream.abort();

  const files = lab.collection(bucketName + ".files");
  const chunks = lab.collection(bucketName + ".chunks");

  console.log({
    fileId,
    metadata: await files.findOne({ _id: fileId }),
    remainingChunks: await chunks.countDocuments({
      files_id: { $eq: fileId }
    })
  });
} finally {
  await client.close();
}
```

Nếu abort thành công trong môi trường bình thường, document `files` chưa được tạo và chunks của upload bị hủy không còn. Tuy nhiên, nếu một lệnh write/abort báo lỗi, **không giả định cleanup đã xong**. Hãy ghi nhận fileId để reconciliation.

Ví dụ này tạo **bucket tên riêng**. Không chạy với bucket production hoặc file ID của người khác.

### 7.3. Khi nguồn upload bị hủy giữa chừng

Ứng dụng HTTP có thể biết client ngắt kết nối hoặc người dùng bấm Cancel. Cần phân biệt:

```text
Client đóng kết nối
       |
       v
Ứng dụng xác định upload chưa finish
       |
       v
Chặn nhận thêm input, dừng source stream
       |
       v
Gọi abort của GridFS upload stream khi còn hợp lệ
       |
       v
Ghi nhận cleanup success / cleanup failure
```

Chi tiết gọi `destroy()`, `abort()` và `pipeline()` phụ thuộc Node.js driver và trạng thái stream. Một stream đã bị destroy bởi `pipeline()` sau lỗi có thể cần xử lý khác so với stream đang mở; **đừng gọi abort hai lần hoặc cố abort sau finish**. Kiểm thử đoạn xử lý cancellation với đúng driver version.

### 7.4. Không biến lỗi hủy thành “đã upload hoàn tất”

Một API có thể trả:

```json
{
  "uploadId": "up-123",
  "status": "CANCELLED",
  "fileAvailable": false
}
```

khi người dùng hủy, nhưng phải phân biệt trạng thái nghiệp vụ **“không cho truy cập”** với kết luận **“mọi chunk đã được xóa khỏi database”**.

Nếu abort cleanup lỗi, trạng thái vận hành phù hợp hơn là:

```text
CANCEL_REQUESTED
CLEANUP_PENDING
CLEANUP_FAILED
```

và đưa fileId vào queue reconciliation. Không trả file URL trước khi upload finish và validate.

## 8. Thiết kế upload lifecycle để biết tệp còn được ghi hay không

### 8.1. Vì sao `fs.files` không đủ quản lý upload đang chạy?

Khi upload đang chạy, document `files` chưa tồn tại. Do đó không thể query `fs.files` để biết:

- Upload bắt đầu khi nào.
- Ai sở hữu upload.
- Lượt upload nào vẫn heartbeat.
- Client có chủ động cancel chưa.
- Chunk không parent được phép giữ bao lâu.
- Lần cleanup trước đã thất bại không.

Ứng dụng có thể quản lý một collection **upload ledger** riêng, ví dụ `gridfs_upload_jobs`.

### 8.2. Một document lifecycle gợi ý

```javascript
{
  _id: ObjectId("66a000000000000000000324"),
  fileId: ObjectId("66a000000000000000000323"),
  bucketName: "contracts",
  tenantId: "TENANT-A",
  requestId: "req-f37a",
  attemptId: "attempt-01",
  status: "UPLOADING",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  heartbeatAt: ISODate("2026-11-14T03:00:15Z"),
  leaseUntil: ISODate("2026-11-14T03:01:15Z"),
  workerId: "uploader-3",
  fencingVersion: 7,
  expectedBytes: NumberLong("420000"),
  actualBytesReceived: NumberLong("260000"),
  lastErrorCode: null
}
```

Tùy hệ thống, có thể dùng `_id = fileId` để đơn giản hóa lookup. Điều quan trọng là ứng dụng có một **định danh ổn định** nối upload job với GridFS file ID.

Trạng thái ví dụ:

```text
CREATED
   |
   v
UPLOADING ------> CANCEL_REQUESTED
   |                       |
   |                       v
   |                   ABORTING
   |                       |
   |             +---------+---------+
   |             |                   |
   v             v                   v
VERIFYING      ABORTED         CLEANUP_REQUIRED
   |
   v
AVAILABLE
   |
   v
DELETING
   |
   v
DELETED
```

Đây là **state machine do ứng dụng tự thiết kế**, không phải danh sách trạng thái mặc định của MongoDB GridFS.

### 8.3. Tạo ledger trước khi ghi chunks

Quy trình:

1. Xác thực quyền upload và quota.
2. Sinh `fileId`/`attemptId` ổn định.
3. Ghi upload ledger với `UPLOADING`.
4. Mở GridFS upload stream bằng ID đã chọn khi driver hỗ trợ.
5. Cập nhật heartbeat/progress định kỳ.
6. Kết thúc source stream, đợi GridFS xác nhận hoàn tất.
7. Xác minh document `files`/size/checksum nếu nghiệp vụ yêu cầu.
8. Chuyển ledger sang `AVAILABLE` bằng compare-and-set.
9. Cho phép download qua API nghiệp vụ.

Đối với Node.js có thể dùng:

```javascript
const upload = bucket.openUploadStreamWithId(
  fileId,
  "contract.pdf",
  {
    metadata: {
      tenantId,
      requestId,
      attemptId
    }
  }
);
```

`fileId` được chuẩn bị trước giúp ledger, error logs và cleanup cùng nói về một đối tượng. Tuy nhiên, không reuse ID cho **hai attempt ghi đồng thời** hoặc sau một attempt chưa rõ trạng thái.

### 8.4. Heartbeat không phải chứng cứ tuyệt đối

Nếu `heartbeatAt` quá cũ, có thể:

- Uploader đã chết.
- Node bị stop-the-world GC.
- Mạng tới ledger lỗi nhưng upload vẫn tiếp tục.
- Worker đã bị phân vùng mạng.
- Hệ thống đồng hồ không đồng bộ.

Không kết luận “heartbeat quá 2 phút = có thể xóa tất cả chunks ngay” khi writer có thể còn chạy. Phải có **lease/ownership/fencing** hoặc cơ chế quiesce khác đảm bảo writer cũ không tiếp tục ghi sau khi cleanup nhận quyền.

### 8.5. Lease và fencing token

Một kiến trúc mạnh hơn:

- Mỗi upload attempt có `owner` và `leaseUntil`.
- Lease được gia hạn khi worker còn hoạt động.
- Worker phải kiểm tra phiên bản sở hữu trước những bước quan trọng.
- Cleanup chỉ nhận quyền khi lease cũ đã mất hiệu lực và owner cũ bị **fenced**.
- Mọi writer tuân theo cùng giao thức kiểm tra ownership.

Ví dụ compare-and-set:

```javascript
const claimed = await jobs.findOneAndUpdate(
  {
    _id: fileId,
    status: "UPLOADING",
    leaseUntil: { $lt: new Date() }
  },
  {
    $set: {
      status: "CLEANUP_PENDING",
      workerId: "cleanup-worker-1",
      claimedAt: new Date()
    },
    $inc: { fencingVersion: 1 }
  },
  { returnDocument: "after" }
);
```

Đây mới là **bước claim trong state machine**, **không đủ tự mình ngăn** một writer cũ tiếp tục ghi vào GridFS. Ứng dụng phải triển khai fencing/quiescence thực sự ở đường ghi, ví dụ quản lý worker ownership và ngừng nhận chunk từ attempt mất quyền. MongoDB GridFS API tự thân không có một trường `fencingVersion` bắt buộc trên mỗi chunk insert.

### 8.6. Tránh reuse file ID khi retry upload

Một request HTTP có thể timeout sau khi server đã hoàn tất upload. Nếu client retry với cùng file ID mà không đối soát, có thể:

- File document đã tồn tại.
- Các chunk cũ tồn tại nhưng metadata chưa có.
- Một uploader cũ vẫn đang ghi.
- Các insert mới vi phạm unique `{files_id,n}`.
- Hai attempt trộn dữ liệu nếu giao thức không kiểm soát.

Quy tắc:

1. Giữ **business idempotency key** ổn định cho cùng ý định của người dùng.
2. Giữ **fileId gắn với một upload attempt cụ thể**.
3. Khi retry, trước tiên đối soát ledger và `files/chunks`.
4. Nếu attempt trước đã thành công, trả fileId cũ sau xác minh.
5. Nếu chưa rõ, không bắt đầu ghi đè cùng fileId.
6. Nếu thật sự cần upload mới, tạo attempt/fileId mới theo protocol, dọn attempt cũ sau khi được xác nhận an toàn.

## 9. Phát hiện orphan chunks bằng truy vấn chỉ đọc

### 9.1. Nguyên tắc phân loại hai giai đoạn

Không nên gắn một truy vấn `$lookup` trực tiếp vào `deleteMany`.

**Giai đoạn A — tìm ứng viên:**

- Group chunks theo `files_id`.
- Join với `files._id`.
- Nếu không có parent, ghi nhận là **candidate**.
- Thu thập chunk count, phạm vi `n`, dung lượng ước lượng.

**Giai đoạn B — quyết định cleanup:**

- Kiểm tra upload ledger.
- Kiểm tra còn active writer/lease không.
- Kiểm tra thời gian và chính sách grace period.
- Xác nhận không còn parent sau khi hệ thống ở trạng thái an toàn.
- Lưu audit/dry-run và nhận quyền cleanup.
- Chỉ xóa những file IDs đã được phê duyệt.

### 9.2. Aggregation tìm ứng viên orphan

Giả sử một bucket tên `fs`. Trong database đã kết nối đúng:

```javascript
const chunks = db.getCollection("fs.chunks");
const fileCollectionName = "fs.files";

const candidates = chunks.aggregate(
  [
    {
      $group: {
        _id: "$files_id",
        chunkCount: { $sum: 1 },
        minChunkNumber: { $min: "$n" },
        maxChunkNumber: { $max: "$n" }
      }
    },
    {
      $lookup: {
        from: fileCollectionName,
        localField: "_id",
        foreignField: "_id",
        as: "parentFiles"
      }
    },
    {
      $match: {
        "parentFiles.0": { $exists: false }
      }
    },
    {
      $project: {
        _id: 1,
        chunkCount: 1,
        minChunkNumber: 1,
        maxChunkNumber: 1
      }
    }
  ],
  { allowDiskUse: true }
).toArray();

printjson(candidates);
```

Trong output, `_id` của mỗi nhóm là **`files_id`**, không phải chunk `_id`. Giữ kiểu BSON khi tiếp tục lookup.

**Quan trọng:**

- Đây là **báo cáo ứng viên**, không phải danh sách được phép xóa.
- Aggregation có thể tốn nhiều CPU, I/O, bộ nhớ/temp disk trên bucket lớn.
- Với sharded collections, khả năng `$lookup` và hiệu năng phụ thuộc phiên bản/topology.
- Kết quả đọc trong lúc có ghi đồng thời không tạo một “snapshot vĩnh viễn” cho quyết định xóa sau đó.
- `allowDiskUse` cho phép dùng disk khi cần, **không có nghĩa truy vấn miễn phí**.
- Không chạy thường xuyên trên cluster lớn nếu không có capacity plan.

### 9.3. Vì sao không dựa vào `ObjectId.getTimestamp()` một mình?

Một script có thể xem thời điểm gần đúng từ `chunks._id`:

```javascript
const chunk = chunks.findOne({});
print(chunk?._id?.getTimestamp?.());
```

Nhưng timestamp ObjectId:

- Có độ chính xác giới hạn và được tạo phía client.
- Có thể không phản ánh lúc server thật sự ghi.
- Có thể sai nếu đồng hồ client sai.
- Không đại diện cho thời điểm bắt đầu/kết thúc của **toàn bộ upload**.
- Không áp dụng nếu ứng dụng/legacy dùng kiểu ID khác trong tình huống tương ứng.

Vì vậy, timestamp của chunk chỉ là **tín hiệu hỗ trợ**; ưu tiên upload ledger/heartbeat/attempt ID do ứng dụng quản lý. Đừng tính “orphan quá 24 giờ” chỉ từ một ObjectId rồi tự động xóa.

### 9.4. Khi bucket quá lớn

Quét toàn bộ `chunks` rồi `$group` có thể rất đắt với hàng trăm triệu chunk.

Các chiến lược nhẹ hơn:

- Bắt đầu từ **upload jobs bị timeout/failed** trong ledger để lấy danh sách fileId giới hạn.
- Dùng index `{files_id:1,n:1}` để `countDocuments`/`find` theo từng ID.
- Ghi nhận fileId khi driver báo lỗi write/abort/delete để ưu tiên điều tra.
- Chạy quét theo batch/maintenance window khi có quyền.
- Phân tách quyền audit và quyền xóa.
- Chỉ làm full integrity audit định kỳ theo lịch có budget.
- Sử dụng checkpoint riêng của audit job để tránh chạy lại quá nhiều.

Không dùng `distinct("files_id")` trên toàn bộ collection như giải pháp mặc định cho dữ liệu lớn: kết quả có thể quá lớn, có giới hạn BSON và chi phí scan.

### 9.5. Hai lần quét cũng chưa thay thế phối hợp

Một số hệ thống quét orphan vào lúc T0 rồi kiểm tra lại lúc T0+5 phút. Điều này giảm nguy cơ xóa nhầm, nhưng **không loại bỏ race**:

```text
T0: query không thấy files(F123)
T1: upload F123 vẫn đang chạy, chậm
T2: job query lần hai vẫn không thấy files(F123)
T3: job xóa chunks(F123)
T4: uploader ghi chunk mới hoặc files(F123)
```

Nếu không có **quy tắc phối hợp với uploader**, hai phép đọc không bảo đảm an toàn tuyệt đối. Trên production, cần lease/fencing/quiesce hoặc một cơ chế kiểm soát lượt upload riêng.

## 10. Kiểm tra tính toàn vẹn của tệp có metadata

### 10.1. Số chunk dự kiến

Nếu metadata có:

- `length = L` byte.
- `chunkSize = S` byte.

thì với tệp không rỗng:

\[
N_{\text{expected}}=\left\lceil \frac{L}{S} \right\rceil
\]

Ví dụ:

```text
length = 600000 bytes
chunkSize = 261120 bytes

600000 / 261120 ≈ 2.30
=> expectedChunks = 3
=> các số n phải là 0, 1, 2
```

Với `length=0`, số chunk dự kiến **bằng 0**.

### 10.2. Không chỉ kiểm tra count

Một tệp có 3 chunk:

```text
n = 0, 1, 3
```

cũng có count = 3 nhưng thiếu `n=2`. Phải kiểm tra:

- `n` bắt đầu từ 0.
- `n` liên tục đến `N-1`.
- Không có trùng `n` (unique index giúp cưỡng chế).
- Độ dài của mỗi chunk đúng `chunkSize`, trừ chunk cuối.
- Tổng số byte bằng `files.length`.
- Các chunk có đúng `files_id` và kiểu BSON.
- Có thể đọc toàn bộ nội dung qua driver.
- Checksum ứng dụng nếu được lưu có khớp không.

Đặc tả cho phép một số driver **bỏ qua chunk dư** thay vì luôn kiểm tra toàn bộ tính nhất quán. Đừng dùng download một phần làm bằng chứng mọi chunk còn lại đều đúng.

### 10.3. Kiểm tra một file nhỏ bằng `mongosh`

Chỉ dùng ví dụ này cho file ID đã chọn, với metadata length đủ nhỏ để tính bằng JavaScript `Number` an toàn:

```javascript
const fileId = ObjectId("66a000000000000000000323");
const files = db.getCollection("fs.files");
const chunks = db.getCollection("fs.chunks");

const file = files.findOne({
  _id: fileId
});

if (!file) {
  throw new Error("File metadata không tồn tại");
}

const length = Number(file.length);
const chunkSize = Number(file.chunkSize);

if (!Number.isSafeInteger(length) ||
    !Number.isSafeInteger(chunkSize) ||
    length < 0 || chunkSize <= 0) {
  throw new Error("Metadata không phù hợp phép tính Number");
}

const expected = Math.ceil(length / chunkSize);
const parts = chunks.find(
  { files_id: { $eq: fileId } },
  { n: 1, data: 1 }
).sort({ n: 1 }).toArray();

printjson({
  fileId,
  length,
  chunkSize,
  expectedChunks: expected,
  actualChunks: parts.length,
  chunkNumbers: parts.map((part) => part.n)
});
```

Trên tệp rất lớn, **không** gọi `toArray()` cho tất cả chunks: dùng cursor streaming, aggregation có giới hạn hoặc công cụ audit có checkpoint. File length có thể là BSON `Long`, và chuyển sang JS Number không an toàn khi vượt phạm vi safe integer; cần dùng BSON Long/BigInt hoặc cách tính tương đương phù hợp driver.

### 10.4. Kiểm tra byte count và hash

Một ứng dụng có thể tính **SHA-256** của nội dung gốc trước hoặc trong lúc upload, lưu vào `files.metadata.sha256` sau khi hoàn tất theo quy trình kiểm soát.

Khi audit, đọc tệp qua GridFS download stream rồi tính SHA-256 và so với metadata kỳ vọng. Điều này giúp phát hiện dữ liệu sai hoặc bị thay đổi. Nó **không chứng minh chống giả mạo** nếu attacker có quyền sửa cả nội dung lẫn metadata hash.

Không dùng field `files.md5` deprecated làm giải pháp toàn vẹn mặc định; MD5 không phù hợp cho các nhu cầu bảo mật hiện đại. Thực hiện checksum ở tầng ứng dụng khi cần.

### 10.5. Corruption cần recovery, không dọn “theo linh cảm”

Nếu metadata tồn tại nhưng thiếu chunk:

1. Ngừng phục vụ tệp như thể hợp lệ.
2. Kiểm tra replicas, lỗi ghi, logs và lịch sử thao tác delete.
3. Xác định có bản gốc/backup hoặc upload source không.
4. Khôi phục bằng một quy trình an toàn, có verification.
5. Thông báo chủ sở hữu nghiệp vụ nếu cần upload lại.
6. Không tự sửa `length`/`chunkSize` để làm tệp có vẻ hợp lệ.

Chỉnh metadata cho khớp các chunk còn sót **không khôi phục phần dữ liệu đã mất**.

## 11. Dọn orphan có kiểm soát

### 11.1. Quy trình an toàn gồm nhiều cổng

Một cleanup job production nên đi qua:

```text
Detect orphan CANDIDATES
          |
          v
Correlate upload ledger / delete logs
          |
          v
Exclude active uploads and protected files
          |
          v
Wait quarantine / grace period
          |
          v
Acquire cleanup ownership / fence writers
          |
          v
Recheck files and chunks by exact fileId
          |
          v
Dry-run + audit / approval
          |
          v
Delete narrowly scoped chunks
          |
          v
Verify zero remains + record outcome
```

Nếu không có cách chứng minh uploader đã dừng hoặc đã bị fenced, trạng thái **“cần điều tra”** tốt hơn việc tự động xóa.

### 11.2. Không xóa theo `filename` hoặc theo ngày thiếu parent

Một lệnh như:

```javascript
// Chống chỉ định trong production:
db.fs.chunks.deleteMany({
  files_id: { $nin: oldFileIds }
});
```

có rủi ro rất lớn:

- File ID có kiểu BSON khác nhau.
- `oldFileIds` có thể không đầy đủ.
- Có uploads mới vừa bắt đầu.
- Logic `$nin` trên phạm vi lớn dễ phá hủy dữ liệu hợp lệ.
- Không ghi lại evidence cho từng ID.

Nên dọn theo **danh sách file ID rõ ràng**, một ID/lô nhỏ, có recheck và log.

### 11.3. Mẫu đọc lại trước khi xóa một candidate

Giả sử đã có `candidateFileId` từ ledger và hệ thống **đã đảm bảo không có uploader nào tiếp tục ghi ID đó**:

```javascript
const candidateFileId = new ObjectId(
  "66a000000000000000000325"
);

const files = db.getCollection("fs.files");
const chunks = db.getCollection("fs.chunks");

// Read-only preflight:
const parent = files.findOne({
  _id: { $eq: candidateFileId }
});

const count = chunks.countDocuments({
  files_id: { $eq: candidateFileId }
});

printjson({
  candidateFileId,
  hasParent: Boolean(parent),
  chunksCount: count
});
```

Nếu `parent` xuất hiện, **dừng cleanup orphan**, vì lúc đó không còn thuộc loại “chunk không parent”. Nếu `count=0`, có thể không cần làm gì. Nếu `count>0`, phải tiếp tục kiểm tra ledger/quyền/quarantine trước khi có lệnh xóa.

### 11.4. Thao tác cleanup cụ thể sau khi có quyền

Chỉ sau khi đạt tất cả precondition, một thao tác cleanup kỹ thuật có thể là:

```javascript
// Chỉ thực hiện khi đã có approval, quiescence/fencing
// và candidateFileId đã xác minh thuộc đúng bucket.
const result = chunks.deleteMany({
  files_id: { $eq: candidateFileId }
});

printjson(result);

print("remaining=" + chunks.countDocuments({
  files_id: { $eq: candidateFileId }
}));
```

Đây là thao tác trực tiếp trên cấu trúc nội bộ GridFS, không phải API xóa tệp thông thường. Nó chỉ phù hợp với **orphan chunks đã được xác minh**, không dành cho tệp có metadata hợp lệ.

Không chạy thao tác này trên production chỉ vì một báo cáo `$lookup` trả candidate. Trong hệ thống không có fencing/quiescence, dùng maintenance window có ngừng writer được xác nhận hoặc triển khai protocol upload an toàn trước khi bật auto cleanup.

### 11.5. Giới hạn batch, tốc độ và tài nguyên

Cleanup nhiều GB chunk có thể gây:

- Nhiều deletes và tác động replication/oplog.
- I/O spike và cache pressure.
- Primary write latency tăng.
- Secondary replication lag.
- Chi phí storage/compaction không giải phóng tức thời theo dung lượng mong đợi.
- Ảnh hưởng tới backup hoặc change streams.

Nên:

- Dọn theo batch file IDs có giới hạn.
- Throttle theo QPS/bytes dự kiến.
- Có deadline/stop flag.
- Theo dõi replication lag, disk, CPU, p95 write latency.
- Có điểm dừng trước ngưỡng resource/SLO.
- Lưu lại danh sách file IDs đã xử lý để tránh lặp vô hạn.

**Xóa logical documents không đồng nghĩa disk usage giảm ngay lập tức** vì cơ chế cấp phát và tái sử dụng không gian của storage engine.

## 12. Ví dụ thực hành an toàn: bucket riêng, không đụng dữ liệu người khác

### 12.1. Điều kiện

Các đoạn dưới đây dành cho **MongoDB test** và Node.js MongoDB driver tương thích. Không cần cố tình kill primary, ngắt replica set hay làm hỏng file thật.

Mục tiêu:

1. Tạo một bucket **tên duy nhất của lần chạy**.
2. Upload tệp hoàn chỉnh.
3. Tạo một chunk “mồ côi giả lập” bằng thao tác thủ công **chỉ trong bucket test**.
4. Tìm candidate orphan bằng truy vấn chỉ đọc.
5. Xóa đúng chunk giả lập sau khi xác nhận không có uploader tương ứng.
6. Xóa tệp hoàn chỉnh qua `bucket.delete()`.

### 12.2. Tạo bucket và upload tệp hoàn chỉnh

```javascript
import {
  MongoClient,
  GridFSBucket,
  ObjectId,
  Binary
} from "mongodb";

import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);

await client.connect();

try {
  const lab = client.db("mongo_gridfs_row323_lab");
  const runId = new ObjectId().toHexString();
  const bucketName = "row323_" + runId;
  const bucket = new GridFSBucket(lab, { bucketName });

  const files = lab.collection(bucketName + ".files");
  const chunks = lab.collection(bucketName + ".chunks");

  const upload = bucket.openUploadStream(
    "readme-row323.txt",
    {
      metadata: {
        runId,
        case: "complete"
      }
    }
  );

  await pipeline(
    Readable.from([
      Buffer.from("GridFS row323 completed file\n", "utf8")
    ]),
    upload
  );

  const completedFileId = upload.id;

  console.log({
    runId,
    bucketName,
    completedFileId,
    fileMetadata: await files.findOne({
      _id: completedFileId
    }),
    chunkCount: await chunks.countDocuments({
      files_id: { $eq: completedFileId }
    })
  });

  // Các phần thực hành tiếp theo có thể đặt trong try này.
} finally {
  await client.close();
}
```

`pipeline()` hoàn tất thành công khi luồng upload hoàn tất theo contract của Node.js driver. Nếu pipeline bị lỗi, cần ghi nhận fileId để cleanup/reconciliation; không tự hứa rằng mọi chunk đã được dọn.

### 12.3. Tạo một orphan giả lập

**Chỉ trong bucket vừa tạo ở môi trường test**, sau khi upload hoàn chỉnh ở phần trước:

```javascript
const orphanFileId = new ObjectId();
const orphanChunkId = new ObjectId();

await chunks.insertOne({
  _id: orphanChunkId,
  files_id: orphanFileId,
  n: 0,
  data: new Binary(
    Buffer.from("test orphan chunk", "utf8")
  )
});

console.log({
  parent: await files.findOne({
    _id: orphanFileId
  }),
  chunksCount: await chunks.countDocuments({
    files_id: { $eq: orphanFileId }
  })
});
```

Kết quả mong đợi:

```text
parent: null
chunksCount: 1
```

Đây là thao tác cố ý tạo **dữ liệu sai định dạng hoàn chỉnh** để học cách phát hiện orphan. Tuyệt đối không chạy trên `fs.chunks` production hay bucket đang được ứng dụng khác dùng.

### 12.4. Tìm orphan trong bucket test

```javascript
const candidates = await chunks.aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 }
    }
  },
  {
    $lookup: {
      from: bucketName + ".files",
      localField: "_id",
      foreignField: "_id",
      as: "parents"
    }
  },
  {
    $match: {
      "parents.0": { $exists: false }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1
    }
  }
]).toArray();

console.log(candidates);
```

Trong bucket test không có uploader nào đang chạy, file ID `orphanFileId` là candidate hợp lệ. ID `completedFileId` **không** phải candidate, vì có parent metadata.

### 12.5. Dọn đúng orphan giả lập

Vì chính chương trình đã tạo orphanFileId/chunkId và không có uploader tương ứng:

```javascript
const parent = await files.findOne({
  _id: orphanFileId
});

if (parent) {
  throw new Error("Orphan demo ID đã có parent: dừng!");
}

const deleted = await chunks.deleteOne({
  _id: orphanChunkId,
  files_id: { $eq: orphanFileId },
  n: 0
});

console.log({
  deletedCount: deleted.deletedCount,
  remaining: await chunks.countDocuments({
    files_id: { $eq: orphanFileId }
  })
});
```

Ở đây dùng `deleteOne()` với **cả chunk ID và file ID**, an toàn hơn cho dữ liệu thử. Trên production, sau khi xác minh không còn active writer, có thể cần cleanup tất cả chunks của một fileId cụ thể, nhưng phải tuân thủ quy trình ở phần trước.

### 12.6. Xóa tệp hoàn chỉnh bằng driver

```javascript
const ownedFile = await files.findOne({
  _id: completedFileId,
  "metadata.runId": runId
});

if (!ownedFile) {
  throw new Error("Không xác nhận được tệp demo sở hữu");
}

await bucket.delete(completedFileId);

console.log({
  fileStillExists: Boolean(
    await files.findOne({ _id: completedFileId })
  ),
  chunksRemaining: await chunks.countDocuments({
    files_id: { $eq: completedFileId }
  })
});
```

Trường hợp bình thường, output xác nhận metadata không còn và chunk count bằng 0.

**Lưu ý:** đoạn code ví dụ phần 12.3–12.6 dùng các biến `lab`, `runId`, `bucketName`, `bucket`, `files`, `chunks` và `completedFileId` được tạo ở phần 12.2; khi muốn chạy liên tục hãy đặt toàn bộ các bước trong cùng khối `try` trước `client.close()` hoặc tổ chức lại thành một hàm hoàn chỉnh. Không chép từng snippet vào process độc lập rồi đoán fileId cũ.

### 12.7. Sau lab, không tự drop database dùng chung

Bucket test có tên ngẫu nhiên để cô lập. Sau khi xác nhận không còn file/chunk demo, người có quyền quản trị có thể thu hồi hai collection rỗng **theo quy trình lab**. Nhưng không dùng:

```javascript
// Nguy hiểm trong database chia sẻ:
db.dropDatabase();
db.fs.files.drop();
db.fs.chunks.drop();
```

Nếu môi trường test có chính sách tự dọn namespace, hãy theo chính sách đó. Không tự tạo/xóa MongoDB cluster hoặc tắt replication chỉ để học orphan cleanup.

## 13. Một worker reconciliation có trạng thái

### 13.1. Vì sao job nên đọc từ ledger trước?

Giả sử có 30 triệu chunks, nhưng chỉ 12 upload báo lỗi hôm nay. Quét toàn bộ `chunks` để nhóm 30 triệu bản ghi có thể đắt hơn rất nhiều so với:

```text
gridfs_upload_jobs:
  status in ["CLEANUP_REQUIRED", "ABORT_FAILED"]
  lease expired
  age > gracePeriod
       |
       v
12 candidate fileIds
       |
       v
findOne files by _id
count chunks by files_id
       |
       v
cleanup only approved IDs
```

Đây là **candidate-driven reconciliation**, thường thân thiện với tài nguyên hơn.

### 13.2. Pseudocode cleanup có điều kiện

```javascript
async function inspectCandidate({
  jobs,
  files,
  chunks,
  fileId
}) {
  const job = await jobs.findOne({ fileId });

  if (!job) {
    return {
      action: "MANUAL_REVIEW",
      reason: "NO_UPLOAD_LEDGER"
    };
  }

  if (!["CLEANUP_REQUIRED", "ABORT_FAILED"].includes(job.status)) {
    return {
      action: "SKIP",
      reason: "STATUS_NOT_ELIGIBLE"
    };
  }

  const parent = await files.findOne({
    _id: { $eq: fileId }
  });

  if (parent) {
    return {
      action: "MANUAL_REVIEW",
      reason: "PARENT_EXISTS"
    };
  }

  const chunksCount = await chunks.countDocuments({
    files_id: { $eq: fileId }
  });

  return {
    action: "CANDIDATE_FOR_APPROVAL",
    fileId,
    chunksCount
  };
}
```

**Hàm trên chỉ đọc, không xóa.** Nó chưa xác minh fencing, lease owner, retention hoặc backup, vì vậy không thể coi output là giấy phép cleanup. Trong production, worker phải có bước claim/recheck/authorization riêng và không xử lý hai job cùng file ID song song.

### 13.3. Không để “repair” chạy khi source tiếp tục ghi

Nếu server uploader đang chạy, chỉ việc kiểm tra `parent=null` không đủ. Một cleanup service tốt phải có thỏa thuận rõ:

- Uploader dùng cùng upload ledger và ownership protocol.
- Uploader đã nhận cancellation/fencing và chắc chắn không ghi chunk mới.
- Cleanup giữ quyền sở hữu trong thời gian thực thi.
- Nếu không đạt điều kiện, ghi `MANUAL_REVIEW`, không xóa.
- Một quá trình chỉ được chuyển `UPLOADING -> CLEANUP_PENDING` qua atomic compare-and-set khi đủ điều kiện.
- Khi cleanup thất bại, giữ trạng thái/attempt để chạy lại an toàn, không xóa thông tin gốc.

Nếu không kiểm soát toàn bộ uploader, tốt nhất dùng **maintenance window** dừng ghi vào bucket rồi mới xử lý rác.

### 13.4. Chạy lại cleanup không tạo thêm hư hại

Một job nên idempotent ở mức ý định:

- Nếu đã xóa hết chunk và không còn parent → đánh dấu hoàn tất cleanup.
- Nếu parent bất ngờ xuất hiện → **dừng**, chuyển sang điều tra.
- Nếu đã có một worker cleanup khác nhận lease → không tranh nhau.
- Nếu chỉ còn một phần chunks và writer bị fenced → tiếp tục dọn đúng fileId.
- Nếu có timeout không rõ kết quả → query lại, không giả định “đã xóa sạch”.

Không giữ kết quả “DONE” chỉ vì `deleteMany` được gửi đi, mà không xác nhận và ghi outcome.

## 14. Khôi phục khi upload hoàn tất nhưng API không nhận được phản hồi

### 14.1. Một tình huống khó

```text
Client -> API -> GridFS
                |
                | các chunks ghi đủ
                | files metadata được tạo
                | upload stream hoàn tất
                |
API mất kết nối trước khi trả fileId cho client
```

Client có thể nhận timeout và bấm “Tải lại”. Nếu API tạo fileId khác ngay, database có thể lưu **hai bản hoàn chỉnh** cho cùng một ý định nghiệp vụ.

### 14.2. Đối soát theo requestId

Một thiết kế upload ledger chứa:

```javascript
{
  requestId: "req-8821",
  tenantId: "TENANT-A",
  fileId: ObjectId("66a000000000000000000323"),
  status: "UPLOADING",
  expectedBytes: NumberLong("420000")
}
```

Khi client retry:

1. Tìm ledger theo `tenantId + requestId` được bảo vệ bằng unique constraint phù hợp.
2. Nếu ledger `AVAILABLE`, xác thực attachment/file ID rồi trả lại.
3. Nếu ledger `UPLOADING`, kiểm tra owner/lease, không tạo attempt trùng bừa bãi.
4. Nếu `fs.files` có parent cho fileId và có thể xác minh kích thước/hash, reconcile ledger sang `AVAILABLE` nếu policy cho phép.
5. Nếu chỉ có chunks không parent, chưa coi đó là file hoàn chỉnh.
6. Nếu attempt trước đã thực sự kết thúc thất bại và được cleanup/fenced, tạo attempt mới theo protocol.

**Idempotency key** bảo vệ ý định “upload tài liệu này một lần”; file ID bảo vệ cấu trúc chunk của từng attempt. Hai tầng ID có vai trò khác nhau.

### 14.3. Không tự tái tạo metadata nếu chỉ còn chunks

Đặc tả GridFS định nghĩa nhiều thông tin trong `files` như `length`, `chunkSize`, `uploadDate` và `metadata`. Nếu thiếu parent, không thể chỉ dựa vào các chunk còn sót để đảm bảo biết đầy đủ:

- Nguồn có gửi hết file không.
- Chunk cuối có đúng hay chưa.
- Kích thước thật có bằng expectation không.
- Filename/metadata có đúng nghiệp vụ không.
- Checksum có khớp bản gốc không.

Vì vậy không insert một document `fs.files` phỏng đoán để biến orphan thành file hợp lệ. Khi cần recovery, ưu tiên **upload lại từ nguồn đáng tin** hoặc quy trình phục hồi được thẩm định.

### 14.4. Retry không được trộn hai attempt

```text
Attempt A: fileId F123, chunks n=0..4, lỗi
Attempt B: fileId F124, upload lại từ đầu
```

Đây là một thiết kế dễ phân biệt và cleanup. Còn nếu cả A và B cùng dùng F123 mà A chưa bị fenced:

```text
A: ghi chunk 4
B: ghi chunk 0..5
A: ghi chunk 5
```

thì unique index có thể phát hiện trùng `n`, nhưng không phải cách quản lý concurrency đúng. Không cho phép hai uploader độc lập cùng fileId.

## 15. Những yếu tố ảnh hưởng đến cleanup trong cluster thật

### 15.1. Replica set và read preference

Nếu audit đọc `fs.files` từ một secondary trễ nhưng đọc `fs.chunks` ở node khác/tại thời điểm khác, nó có thể nhận ảnh chụp không nhất quán:

```text
Primary:
  files(F123) đã được ghi

Secondary chậm:
  chưa thấy files(F123)

Audit:
  thấy chunks(F123), không thấy files(F123)
  -> kết luận orphan giả
```

Để quyết định xóa, dùng chiến lược đọc **nhất quán và đáng tin** theo deployment, kiểm tra primary/current state, write concern và thời gian áp dụng thay đổi. Nhưng **read concern alone** không loại bỏ race với uploader còn chạy.

### 15.2. Không dùng GridFS như transaction giữa collections

Dù có read concern `majority` hoặc write concern `majority`, việc xóa hai collections vẫn không tự trở thành transaction GridFS. Các chính sách concern giúp mức xác nhận/quan sát, không giải quyết toàn bộ trạng thái nghiệp vụ/cạnh tranh.

### 15.3. Sharded GridFS

Với sharded cluster, cần xem:

- Bucket nào đang dùng.
- `files` và `chunks` có sharded không.
- Shard key của `chunks` có chứa `files_id` theo cấu hình phù hợp không.
- Unique index `{files_id:1,n:1}` có còn hợp lệ theo quy tắc sharding/uniqueness không.
- Query cleanup theo `files_id` có targeted routing hay scatter-gather.
- Dữ liệu chunks có thể nằm ở nhiều shard không.
- Có chunk migration/resharding/DDL đang chạy không.

Không cố sửa shard key hoặc tạo/drop index GridFS trong lúc cleanup sự cố nếu chưa có kế hoạch được DBA phê duyệt.

### 15.4. Storage không giảm ngay sau delete

Sau xóa nhiều chunk, `countDocuments` có thể giảm đúng nhưng file hệ thống database chưa giảm kích thước tương ứng. WiredTiger có thể **tái sử dụng** không gian được giải phóng.

Không tự chạy `compact`, `repairDatabase`, tái tạo replica set hay drop collection chỉ vì dung lượng hệ điều hành chưa giảm ngay; đó là quyết định vận hành riêng với rủi ro và tính sẵn sàng của cluster.

### 15.5. Backup, retention và legal hold

Xóa file trong GridFS không xóa bản sao của nó khỏi:

- snapshot/backup có retention;
- archive ngoài MongoDB;
- CDN và HTTP cache;
- log hoặc hệ thống gửi thông điệp có kèm nội dung;
- client đã tải xuống trước đó.

Với tài liệu pháp lý hoặc dữ liệu cần retention, cần kiểm tra legal hold trước khi xóa. Với yêu cầu xóa dữ liệu cá nhân, cần phối hợp quy trình xóa tại mọi bản sao được quản lý và ghi nhận thời hạn lưu backup theo chính sách.

## 16. Giám sát và cảnh báo

### 16.1. Metric đề xuất

Tên dưới đây là **metric do ứng dụng tự định nghĩa**, không phải field mặc định MongoDB cung cấp:

| Metric | Mục đích |
| --- | --- |
| `gridfs_uploads_started_total` | Số upload bắt đầu |
| `gridfs_uploads_completed_total` | Số upload hoàn tất |
| `gridfs_uploads_aborted_total` | Số upload hủy chủ động |
| `gridfs_upload_errors_total` | Phân loại lỗi upload |
| `gridfs_abort_cleanup_failures_total` | Số lần abort không dọn được |
| `gridfs_upload_inflight` | Số upload còn mở |
| `gridfs_upload_age_seconds` | Tuổi upload đang mở |
| `gridfs_orphan_candidates` | Số fileIds có chunks nhưng thiếu parent |
| `gridfs_orphan_candidate_bytes` | Dung lượng ứng viên ước lượng |
| `gridfs_verified_orphan_bytes` | Dung lượng đã xác minh được phép dọn |
| `gridfs_missing_chunk_files` | Số tệp có metadata nhưng thiếu chunk |
| `gridfs_unreferenced_completed_files` | Số file hoàn chỉnh không còn reference nghiệp vụ |
| `gridfs_delete_errors_total` | Lỗi delete theo fileId |
| `gridfs_reconciliation_duration_seconds` | Thời gian chạy audit/cleanup |
| `gridfs_cleanup_deleted_chunks_total` | Chunks đã xóa sau khi xác minh |
| `gridfs_cleanup_jobs_manual_review` | Trường hợp không đủ điều kiện xóa tự động |

Đặc biệt, **orphan candidates** và **verified orphans** không phải cùng một chỉ số. Candidate count có thể tăng do uploads đang chạy trong giờ cao điểm mà không có hư hại.

### 16.2. Dashboard vận hành

Một dashboard có thể nhóm:

```text
+---------------------------+-------------------------+
| Upload success / error    | Abort / cleanup errors  |
+---------------------------+-------------------------+
| Upload inflight & age     | Orphan candidates age   |
+---------------------------+-------------------------+
| Verified cleanup backlog  | Missing chunks alerts   |
+---------------------------+-------------------------+
| Bucket files/chunks count | Chunk storage growth    |
+---------------------------+-------------------------+
| Primary write latency     | Replication lag         |
+---------------------------+-------------------------+
```

Quan sát cả xu hướng: vài chunk orphan tạm thời trong lúc upload đang chạy chưa chắc là sự cố; **verified orphan backlog tăng liên tục** mới đáng ưu tiên.

### 16.3. Alert nên có ngữ cảnh

Ví dụ **ngưỡng giả định**, không phải giá trị do MongoDB bảo đảm:

- Một upload `UPLOADING` quá 2 giờ dù SLA chỉ 10 phút.
- Upload đã `ABORT_FAILED` và chunks chưa được dọn sau 24 giờ.
- Verified orphan bytes tăng vượt 10 GiB.
- Tệp đang `AVAILABLE` nhưng đọc bị `ChunkIsMissing`.
- Số delete error tăng đột ngột.
- Reconciliation job không hoàn thành nhiều chu kỳ.

Chọn ngưỡng theo file size, tốc độ mạng, SLA upload và legal retention. Với tệp có kích thước hàng trăm GiB, upload kéo dài hàng giờ có thể hoàn toàn hợp lệ; không áp ngưỡng 10 phút cho mọi bucket.

### 16.4. Log và trace an toàn

Một log hữu ích có thể chứa:

```json
{
  "requestId": "req-8821",
  "attemptId": "attempt-02",
  "tenantId": "TENANT-TEST",
  "bucket": "contracts",
  "fileId": "66a000000000000000000323",
  "status": "CLEANUP_REQUIRED",
  "operation": "UPLOAD_ABORT",
  "errorCode": "NETWORK_TIMEOUT",
  "bytesUploaded": 260000,
  "occurredAt": "2026-11-14T04:00:00Z"
}
```

Không log tệp, chunk data, access token, tên file chứa PII hoặc URL tải xuống có chữ ký. Với hệ đa tenant, áp dụng RBAC và retention cho log.

## 17. Runbook điều tra sự cố

### 17.1. Trường hợp A — Upload failed, chunks vẫn tăng

1. Lấy `fileId`, bucket name, attempt ID và thời điểm lỗi.
2. Kiểm tra có uploader nào **vẫn hoạt động** không.
3. Xem upload ledger/lease và client retries.
4. Kiểm tra `fs.files` có parent chưa.
5. Đếm chunks theo exact fileId.
6. Nếu uploader còn sống, **không cleanup**.
7. Nếu đã dừng/fenced, đưa candidate qua quarantine rồi cleanup có kiểm soát.
8. Xác nhận chunks về 0 và cập nhật ledger.

Không dùng `filename` để tìm tất cả chunk của một upload, vì chunk không có filename và nhiều revision có thể trùng tên.

### 17.2. Trường hợp B — Delete trả lỗi nhưng API đã ẩn file

1. Kiểm tra tombstone/`DELETING` của attachment.
2. Query metadata theo fileId từ authoritative source.
3. Đếm chunks theo fileId.
4. Nếu parent còn: cần xem có phải delete chưa đi qua bước đầu, quyền, network.
5. Nếu parent mất nhưng chunks còn: đây là cleanup candidate do delete chưa hoàn tất.
6. Dừng download mới và xác nhận không có uploader cho ID.
7. Thực hiện cleanup được phê duyệt.
8. Chỉ mark `DELETED` khi xác nhận trạng thái tương ứng và lưu audit.

Không “retry bucket.delete đến khi hết lỗi” mà không phân biệt FileNotFound với lỗi do mạng/authorization.

### 17.3. Trường hợp C — Download báo thiếu chunk

1. Xác nhận file metadata tồn tại và `length/chunkSize` hợp lệ.
2. So expected count, min/max `n`, chunk size và checksum.
3. Xác định người dùng/ứng dụng nào đang tham chiếu.
4. Tạm ngừng phục vụ file hỏng nếu cần.
5. Kiểm tra lịch sử delete/cleanup/manual write.
6. Khôi phục từ nguồn tin cậy hoặc yêu cầu upload lại.
7. Không xóa metadata để che giấu lỗi.

### 17.4. Trường hợp D — Bucket quá lớn, muốn giải phóng dung lượng

1. Phân loại **dung lượng tệp còn hợp lệ** với **verified orphan bytes**.
2. Tách file hoàn chỉnh nhưng unreferenced khỏi orphan chunks.
3. Kiểm tra policy retention và legal hold.
4. Lập batch cleanup có throttle.
5. Quan sát replication lag và write latency.
6. Xác nhận count/bytes đã dọn.
7. Không đánh đồng giải phóng logical records với OS disk shrink tức thì.

## 18. Kiến trúc tham chiếu: upload, download, delete và cleanup

Một thiết kế phối hợp:

```text
                API Gateway
                     |
                     v
           Attachment Service
               |          |
          auth/quota       | file references
               |          v
               |      attachments
               |
          upload ledger <---------+
               |                  |
               v                  |
          GridFSBucket            |
        +------+-------+          |
        |              |          |
        v              v          |
    bucket.files   bucket.chunks   |
        |              |          |
        +--------------+          |
               |                  |
       successful upload          |
               |                  |
               v                  |
       mark AVAILABLE ------------+
               |
        downloads permitted
               |
        deletion requested
               |
         mark DELETING
               |
        bucket.delete(fileId)
               |
         verify / reconcile
               |
         mark DELETED

Cleanup worker:
    reads failed uploads + delete errors
                  |
            checks leases
                  |
         excludes active writers
                  |
          rechecks exact IDs
                  |
         deletes verified chunks
                  |
           records audit
```

Trong thiết kế này, **GridFS giữ byte**, còn **application ledger và attachments giữ ý nghĩa nghiệp vụ**. Không cho rằng chỉ nhìn `fs.files` biết được tệp đó đang chờ duyệt, bị hủy, được giữ vì retention hay đang được người dùng tải xuống.

## 19. Những sai lầm dễ gây mất dữ liệu

| Sai lầm | Tại sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Xóa theo `filename` không kiểm revisions | Tên không unique | Xác định exact fileId |
| Xóa riêng `fs.files` bằng lệnh thủ công | Để lại chunks không parent | Dùng `bucket.delete(fileId)` |
| Xóa toàn bộ `fs.chunks` | Phá nội dung mọi file | Chỉ dọn file IDs đã xác minh |
| Thấy thiếu parent rồi xóa ngay | Có thể là upload đang chạy | Kiểm tra ledger/lease/quiescence |
| Dùng timestamp ObjectId làm bằng chứng uploader chết | Đồng hồ/độ chính xác/race | Dùng workflow state và fencing |
| Gọi `abort()` sau khi upload đã finish | Abort không còn đúng ngữ nghĩa | Dùng `delete()` cho file hoàn chỉnh |
| Gọi `abort()` hai lần | Driver có thể báo lỗi | Quản lý state abort một lần |
| Tin `finally` luôn chạy khi crash | Process có thể bị kill | Có reconciliation job |
| Tin upload write lỗi sẽ tự dọn mọi chunk | Đặc tả cho phép để orphan sau lỗi ghi | Ghi fileId và cleanup sau |
| Retry upload cùng fileId khi attempt cũ chưa rõ | Chunks trùng/hỗn hợp | Đối soát, fencing, attempt IDs |
| Cho hai worker dùng cùng file ID đồng thời | Race và duplicate chunk `n` | Single owner/lease/fencing |
| Dùng GridFS trong multi-document transaction | GridFS không hỗ trợ | State machine và reconciliation |
| Metadata có nhưng không có chunk luôn là lỗi | Tệp rỗng hợp lệ | Kiểm `length` |
| Parent tồn tại nghĩa chunks chắc chắn đủ | Có thể thiếu hoặc dư | Integrity check |
| Chỉ so chunk count | Không phát hiện lỗ hổng thứ tự | So `n`, bytes, checksum |
| Tệp không còn trong attachments nên xóa ngay | Có thể còn reference/retention | Reference registry và legal hold |
| `delete()` trả FileNotFound nghĩa chunks đã hết | Driver/version và lỗi trước đó khác nhau | Đếm/reconcile remaining chunks |
| Đọc secondary trễ để quyết định cleanup | Có thể kết luận orphan giả | Dùng nguồn authoritative và quiescence |
| Full scan chunks liên tục trên cluster lớn | Tốn CPU/disk/memory | Candidate-driven audit |
| Dọn hàng trăm GB trong một lệnh không throttle | Ảnh hưởng replication và API | Batch, rate limit, monitor |
| Xóa MongoDB là xóa ngay mọi bản backup/CDN | Dữ liệu còn ở hệ khác | Quy trình retention/end-to-end deletion |
| Không log file ID khi upload lỗi | Không thể tra cứu orphan | Stable fileId/attemptId và audit |

## 20. Bài tập thực hành và câu hỏi ôn tập

### Bài A. Nhận diện orphan

Bucket `fs` có:

```javascript
// files
{ _id: "F1", length: 500000, chunkSize: 261120 }
{ _id: "F2", length: 0, chunkSize: 261120 }

// chunks
{ files_id: "F1", n: 0 }
{ files_id: "F1", n: 1 }
{ files_id: "F3", n: 0 }
```

Hãy trả lời:

1. File nào bình thường?
2. `F2` không có chunk có phải corruption không?
3. `F3` có phải candidate orphan không?
4. Cần thêm thông tin nào trước khi xóa `F3`?
5. Vì sao `F3` không được coi là file hoàn chỉnh?

### Bài B. Xóa file có nhiều revision

Có ba document `fs.files` đều tên `report.pdf` nhưng `_id` khác nhau.

1. Tại sao `filename` không đủ để xóa một bản?
2. `bucket.delete(fileId)` xóa những gì?
3. Nếu client muốn xóa tất cả revisions, cần thu thập và xác thực điều gì?
4. Nếu delete bị timeout, vì sao không được kết luận mọi chunk vẫn còn?

### Bài C. Upload bị crash

Một upload đã ghi chunks `n=0..8` nhưng chưa có metadata trong `files`.

1. Đây có nhất thiết là orphan được phép xóa không?
2. Sự khác nhau giữa client cancel có gọi `abort()` và process crash là gì?
3. Upload ledger nên lưu những field nào?
4. Cần fencing/quiescence gì trước cleanup?

### Bài D. Tệp thiếu chunk

Metadata:

```text
length=600000
chunkSize=261120
```

Chunks hiện có có `n=0` và `n=2`.

1. Expected count là mấy?
2. Actual count là mấy?
3. Tại sao không thể chỉ dựa vào `countDocuments`?
4. Có nên chỉnh `length` để tránh download error không?
5. Nên khôi phục theo nguồn nào?

### Bài E. Retry không rõ kết quả

Một request nhận HTTP timeout sau khi upload có thể đã hoàn tất.

1. Vì sao upload lại ngay bằng fileId mới có thể tạo duplicate?
2. Làm sao tra theo business idempotency key?
3. Nếu `fs.files` tồn tại nhưng ledger vẫn `UPLOADING`, cần xác minh gì?
4. Nếu chỉ có chunks mà không có parent, có nên tiếp tục upload cùng ID không?

### Bài F. Cleanup khi replication lag

Audit dùng secondary để đọc `fs.files`, trong khi uploader vừa commit metadata trên primary.

1. Vì sao có thể báo orphan giả?
2. Nếu chuyển audit sang primary, race với upload đã hết chưa?
3. Khi nào cần maintenance window?
4. Vì sao không nên tự tăng `readConcern` rồi coi đó là fencing?

### Bài G. Dung lượng bucket tăng

Một bucket có:

```text
Valid file bytes:              800 GiB
Verified orphan bytes:          12 GiB
Completed but unreferenced:     30 GiB
Unknown / active uploads:        5 GiB
```

1. Trong các nhóm, nhóm nào có thể ưu tiên cleanup sau review?
2. Vì sao không được tự xóa nhóm 30 GiB?
3. Vì sao không được tự xóa nhóm 5 GiB?
4. Nếu xóa 12 GiB chunks, tại sao OS disk chưa chắc giảm ngay?

### Bài H. Thiết kế hai lớp trạng thái

Hãy vẽ state machine cho:

- Attachment nghiệp vụ: `PENDING → AVAILABLE → DELETING → DELETED`.
- Upload job: `CREATED → UPLOADING → VERIFYING → COMPLETED/FAILED/CLEANUP_REQUIRED`.

Giải thích vì sao hai state machine khác nhau và vì sao file hoàn chỉnh nhưng attachment chưa `AVAILABLE` không tự là orphan.

### Bài I. Audit theo batch

Một bucket có 100 triệu chunk và 200 upload thất bại gần đây.

1. Tại sao `$group` toàn bộ chunk không phải cách đầu tiên tốt nhất?
2. Index nào giúp tra chunks theo fileId?
3. Cần thông tin gì trong ledger?
4. Nếu job cleanup chạy lại sau timeout, nên xác nhận gì trước khi xóa tiếp?
5. Làm sao hạn chế tác động lên primary write latency?

### Bài J. Quyền và bảo mật

Một người dùng nhập một `fileId` ngẫu nhiên rồi gọi DELETE API.

1. Tại sao chỉ biết ID không có nghĩa được quyền xóa?
2. Cần xác minh tenant/reference/retention ở đâu?
3. Khi đã xóa GridFS, dữ liệu còn có thể xuất hiện trong những bản sao nào?
4. Những thông tin nào không nên đưa vào logs?

## 21. Tài liệu tham khảo chính thức

Khi triển khai, cần đối chiếu **MongoDB server version, driver version, topology, sharding và chính sách của deployment**:

- [GridFS — MongoDB Manual](https://www.mongodb.com/docs/manual/core/gridfs/) — định dạng hai collection, indexes, giới hạn và lưu ý không hỗ trợ multi-document transactions.
- [MongoDB GridFS Specification](https://github.com/mongodb/specifications/blob/master/source/gridfs/gridfs-spec.md) — thứ tự ghi chunks/files, upload abort, các tình huống orphan và delete semantics.
- [Store Large Files with GridFS — Node.js Driver](https://www.mongodb.com/docs/drivers/node/current/crud/gridfs/) — dùng `GridFSBucket`, upload/download/delete/drop.
- [GridFSBucketWriteStream API — Node.js Driver](https://mongodb.github.io/node-mongodb-native/6.17/classes/GridFSBucketWriteStream.html) — `abort()`, stream state và phương thức của upload stream theo driver.
- [GridFS — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/) — ví dụ và lưu ý orphan chunks khi upload thất bại.
- [MongoDB Node.js Driver API](https://mongodb.github.io/node-mongodb-native/) — đối chiếu kiểu file ID, stream upload và error handling với phiên bản đang dùng.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — thiết kế index và xem index trên `files/chunks`.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — mức xác nhận ghi và ảnh hưởng khi gặp lỗi network/replication.

Đặc tả GridFS có giá trị đặc biệt để hiểu vì sao driver **không thể bảo đảm mọi thao tác trên `files` và `chunks` nguyên tử như một transaction** và vì sao một số lỗi upload có thể để lại chunk chưa có metadata. API cụ thể như `abort()`, event stream và errors vẫn cần xác minh theo driver.

## 22. Kết luận

**GridFS** chia một tệp thành các chunk và chỉ tạo metadata trong `files` khi upload hoàn tất. Vì vậy, **chunk không có parent** có thể là tệp lỗi, tàn dư delete hoặc đơn giản là **một upload đang diễn ra**. Không có quy tắc an toàn kiểu “`files_id` không xuất hiện trong `fs.files` thì xóa ngay”.

Khi xóa tệp hoàn chỉnh, dùng **GridFSBucket.delete(fileId)** với ID đã được xác thực; khi chủ động hủy upload còn mở, dùng **abort** và xác nhận cleanup. Nếu upload hoặc delete thất bại, hãy ghi lại fileId/attemptId và đối soát cả hai collection. GridFS **không hỗ trợ multi-document transactions**, nên ứng dụng phải có state machine, idempotency và quy trình khôi phục riêng.

Phát hiện orphan chỉ là bước đầu. Một hệ thống đáng tin cần **upload ledger, quyền sở hữu, heartbeat/lease, fencing hoặc ngừng writer, grace period, dry-run, cleanup theo exact file ID, post-delete verification và metrics**. Ngoài orphan chunks còn phải nhận diện missing/extra chunks, file hoàn chỉnh không còn reference và reference trỏ tới file đã mất; mỗi loại có chính sách xử lý khác nhau.

**Nguyên tắc cốt lõi:** chỉ xóa những dữ liệu đã xác minh là không còn thuộc một upload hoạt động hoặc tệp hợp lệ, và luôn ưu tiên khả năng phục hồi dữ liệu hơn việc dọn dung lượng thật nhanh.
