# Bài toán lưu tệp lớn và tiêu chí lựa chọn GridFS trong MongoDB

Một ứng dụng có thể lưu rất nhiều loại dữ liệu trong MongoDB: thông tin khách hàng, đơn hàng, phiếu bảo hành, hồ sơ nhân viên, bản ghi giao dịch và cả **tệp đính kèm**. Với dữ liệu nghiệp vụ thông thường, mỗi đối tượng thường là một document BSON có các trường rõ ràng. Tuy nhiên, khi ứng dụng cần lưu một video 200 MiB, một bản PDF 40 MiB, một bộ ảnh độ phân giải cao hoặc một tệp nén vài GiB, việc đặt toàn bộ byte vào một field của document sẽ gặp giới hạn.

MongoDB đặt **giới hạn kích thước một BSON document là 16 MiB** (16 × 1.024 × 1.024 byte), bao gồm cả cấu trúc document, tên field và dữ liệu bên trong. **GridFS** là cơ chế của MongoDB để lưu và truy xuất tệp lớn bằng cách **chia tệp thành nhiều chunk**, lưu từng chunk dưới dạng document riêng, đồng thời lưu metadata của tệp trong một collection khác.

GridFS giải quyết bài toán **lưu tệp vượt giới hạn một BSON document** và cung cấp cách **upload/download theo stream** thông qua driver hoặc công cụ tương thích. Nhưng GridFS không nhất thiết là lựa chọn tốt nhất cho mọi tệp. Trong nhiều hệ thống, **object storage** như S3-compatible storage, Google Cloud Storage hoặc Azure Blob Storage có thể hợp hơn cho tệp phục vụ trực tiếp tới nhiều người dùng, CDN và lưu trữ dung lượng rất lớn.

Bài học thuộc chương **GridFS** của module **Database Engine Document MongoDB**. Mục tiêu chính là giúp bạn trả lời:

1. Vì sao giới hạn 16 MiB làm một số cách lưu tệp trực tiếp không phù hợp?
2. GridFS lưu tệp qua hai collection như thế nào, và vì sao lại có chunk?
3. Khi nào nên dùng GridFS, khi nào chỉ cần BSON binary và khi nào nên dùng object storage?
4. Metadata, version, checksum, bảo mật, retention và backup cần được thiết kế ra sao?
5. Upload lỗi giữa chừng, retry và xóa tệp có thể để lại những trạng thái nào?
6. Cách thực hành upload, đọc, tìm metadata và xóa tệp bằng công cụ và MongoDB Java Sync Driver?

## 1. Đầu tiên: đừng nhầm tệp với document nghiệp vụ

Ví dụ một hợp đồng bảo hiểm:

```javascript
{
  _id: "contract-1001",
  customerId: "C01",
  status: "signed",
  documentName: "insurance-contract.pdf",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Document trên chứa **metadata**: tên, đối tượng liên quan, trạng thái và thời điểm. Nó chưa lưu nội dung PDF.

Một cách đơn giản khác là nhúng dữ liệu nhị phân vào document:

```javascript
{
  _id: "contract-1001",
  documentName: "insurance-contract.pdf",
  mimeType: "application/pdf",
  data: BinData(0, "...base64...")
}
```

Đây chỉ là **sơ đồ BSON binary**. Với tệp rất nhỏ, lưu dữ liệu nhị phân trực tiếp có thể hợp lý nếu nghiệp vụ thực sự muốn đọc document và bytes cùng lúc. Nhưng mọi document vẫn phải nằm trong **giới hạn 16 MiB**.

Nếu PDF thực tế lớn 30 MiB thì không thể nhét nguyên nội dung vào một document BSON. Việc chuyển sang Base64 hoặc đặt trong string **không né được giới hạn**; biểu diễn Base64 thường còn làm tăng dung lượng payload trước khi giải mã.

### Ba cách lưu cần cân nhắc

| Chiến lược | Dữ liệu byte nằm ở đâu? | Metadata nằm ở đâu? | Khi đáng cân nhắc |
| --- | --- | --- | --- |
| **Nhúng BSON binary** | Field `BinData` của một document | Cùng document | Tệp nhỏ, số lượng ít, cần thao tác cùng document |
| **GridFS** | Nhiều chunk trong MongoDB | Collection GridFS files và metadata nghiệp vụ nếu cần | Tệp lớn, cần stream, muốn quản lý trong MongoDB |
| **Object storage + MongoDB** | Object storage | MongoDB lưu object key, version, checksum, owner | Tệp lớn/nhiều, web/mobile/CDN, lifecycle và chi phí lưu trữ độc lập |

Không có quy tắc “mọi tệp nhỏ hơn 16 MiB thì phải nhúng BSON”. Một ảnh 2 MiB được phân phát hàng triệu lần qua CDN có thể **rất nên** nằm ở object storage; còn một blob nhỏ gắn chặt với document có thể nhúng trực tiếp.

## 2. Giới hạn 16 MiB giải thích được gì và không giải thích được gì?

16 MiB là giới hạn **của một BSON document**, không phải giới hạn kích thước cả collection, cả database hay toàn bộ dữ liệu trong MongoDB.

```text
Document thường:
  { _id, metadata, binary }
            |
            v
  Tổng BSON document <= 16 MiB

GridFS:
  File lớn
    |
    +--> chunk 0  (một document)
    +--> chunk 1  (một document)
    +--> chunk 2  (một document)
    ...
    +--> file metadata (document riêng)
```

Mỗi chunk là một document nhỏ riêng, nên không một document nào phải chứa toàn bộ file lớn. GridFS quản lý tập các document này như **một tệp logic**.

### Tại sao không chia file thủ công vào một mảng trong một document?

Một phương án sai là:

```javascript
{
  _id: "file-01",
  chunks: [
    BinData(0, "..."),
    BinData(0, "..."),
    BinData(0, "...")
  ]
}
```

Việc chia byte thành nhiều phần **nhưng vẫn đặt tất cả các phần trong một document** không thay đổi giới hạn 16 MiB của document đó.

Nếu lập nhiều document chunk thủ công, bạn đang tự viết lại một phần GridFS: chia chunk, ghép file, quản lý thứ tự, metadata, kiểm tra lỗi và API stream. Trừ khi có yêu cầu rất đặc thù, nên sử dụng **GridFS specification và driver** thay vì tự định nghĩa cơ chế không tương thích.

### Khi nào 16 MiB chưa phải lý do đủ mạnh?

Với 1.000 tệp mỗi tệp 50 KiB, tất cả đều nhỏ hơn giới hạn. Nhưng nếu ứng dụng cần phân phát chúng qua CDN, versioning theo object, hoặc chính sách lưu trữ rất dài hạn, lưu qua MongoDB chưa chắc là phương án tối ưu.

GridFS là một **lựa chọn lưu tệp dựa trên MongoDB**, không phải một quy định rằng “tệp lớn thì nhất định dùng MongoDB”.

## 3. GridFS tổ chức hai collection như thế nào?

GridFS dùng hai collection liên quan với cùng một **bucket name**:

- `<bucket>.files`: một document chứa metadata cho **mỗi tệp** đã được quản lý.
- `<bucket>.chunks`: nhiều document chứa các **mảnh dữ liệu nhị phân** của những tệp đó.

Bucket mặc định thường có tên `fs`, tức:

```text
fs.files
fs.chunks
```

Nếu ứng dụng tạo bucket `attachments`, hai collection logic là:

```text
attachments.files
attachments.chunks
```

Tên bucket **không phải** một field tùy ý đặt sau khi upload; các công cụ/driver phải cùng dùng đúng bucket để thấy cùng dữ liệu.

### 3.1. Sơ đồ liên hệ giữa hai collection

```text
                   GridFS bucket: attachments

  attachments.files
  +----------------------------------------------+
  | _id: ObjectId("...A1")                       |
  | filename: "report.pdf"                       |
  | length: 20971520                            |
  | chunkSize: 261120                           |
  | uploadDate: ...                             |
  | metadata: {tenantId, contentType, sha256}    |
  +----------------------------------------------+
                 |
                 | _id = chunks.files_id
                 v
  attachments.chunks
  +----------------------------------------------+
  | files_id: ObjectId("...A1"), n: 0, data: ... |
  | files_id: ObjectId("...A1"), n: 1, data: ... |
  | files_id: ObjectId("...A1"), n: 2, data: ... |
  | ...                                          |
  | files_id: ObjectId("...A1"), n: 80, data:... |
  +----------------------------------------------+
                 |
                 v
      Driver đọc chunk theo thứ tự n
                 |
                 v
          report.pdf nguyên vẹn
```

Các giá trị ObjectId/metadata trong sơ đồ chỉ là ví dụ, không phải dữ liệu do MongoDB đã tạo trên máy thực hành.

### 3.2. Document trong `files`

Một GridFS file entry có thể trông như:

```javascript
{
  _id: ObjectId("65f000000000000000000001"),
  length: NumberLong("20971520"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  filename: "report.pdf",
  metadata: {
    tenantId: "tenant-01",
    ownerId: "user-123",
    contentType: "application/pdf",
    sha256: "abcdef...",
    classification: "internal"
  }
}
```

Các trường chính:

| Field | Ý nghĩa |
| --- | --- |
| `_id` | **ID của tệp GridFS**, dùng để tải/xóa chính xác một phiên bản |
| `length` | Tổng kích thước dữ liệu tệp, tính theo **byte** |
| `chunkSize` | Kích thước chunk tối đa của tệp |
| `uploadDate` | Thời điểm upload được ghi nhận |
| `filename` | Tên tệp logic do ứng dụng cung cấp |
| `metadata` | Thuộc tính tự định nghĩa, ví dụ tenant, owner, content type, checksum |

Không phải mọi tệp có cùng filename đều là cùng một tệp. **GridFS cho phép nhiều file entries có cùng filename**, mỗi entry có `_id` khác nhau. Khi nghiệp vụ cần xác định một phiên bản, hãy dùng **file ID** và version metadata rõ ràng, không chỉ dựa vào filename.

Các field lịch sử như `md5` từng được thấy trong tài liệu/công cụ cũ, nhưng **không nên phụ thuộc vào MD5 mặc định của driver mới** để coi là xác minh toàn vẹn. Nếu cần checksum, ứng dụng nên dùng thuật toán hiện hành như SHA-256 và kiểm tra end-to-end.

### 3.3. Document trong `chunks`

Một chunk có thể được biểu diễn:

```javascript
{
  _id: ObjectId("65f000000000000000001001"),
  files_id: ObjectId("65f000000000000000000001"),
  n: 0,
  data: BinData(0, "...binary bytes...")
}
```

| Field | Ý nghĩa |
| --- | --- |
| `_id` | ID riêng của document chunk |
| `files_id` | Liên kết tới `_id` của file entry |
| `n` | Thứ tự chunk, thường bắt đầu từ **0** |
| `data` | Byte dữ liệu của chunk |

Driver ghép các chunk theo thứ tự `n = 0, 1, 2, ...` để tái tạo file. Không nên tự sửa `n`, thay `files_id` hoặc chỉnh `data` trực tiếp bằng thao tác CRUD thủ công: chỉ một chunk thiếu/sai thứ tự cũng có thể khiến file tải xuống lỗi hoặc bị hỏng.

### 3.4. Index quan trọng

GridFS specification dùng những index như:

- Trên `chunks`: compound index **`{files_id: 1, n: 1}`** với yêu cầu unique phù hợp để xác định thứ tự chunk trong một tệp.
- Trên `files`: index theo **`{filename: 1, uploadDate: 1}`** để hỗ trợ tìm các file entries theo tên và thời điểm.

Driver có thể kiểm tra/tạo index GridFS cần thiết theo trạng thái bucket và phiên bản. Không giả định index đã đúng trên collection bị chỉnh sửa thủ công; có thể xem:

```javascript
db.getCollection("fs.files").getIndexes()
db.getCollection("fs.chunks").getIndexes()
```

Nếu bucket tên `attachments`, thay `fs` bằng `attachments`. Không xóa/đổi index hệ thống chỉ để tối ưu một truy vấn khác khi chưa hiểu yêu cầu của GridFS.

## 4. Chunk size: vì sao không chia thành một vài document thật lớn?

GridFS dùng kích thước chunk mặc định thường là **255 KiB = 255 × 1.024 = 261.120 byte**. Chunk cuối có thể nhỏ hơn.

Một tệp 20 MiB có:

```text
20 MiB = 20 × 1.024 × 1.024
       = 20.971.520 byte

Chunk size mặc định = 261.120 byte

Số chunk = ceil(fileLength / chunkSize)
         = ceil(20.971.520 / 261.120)
         = 81 chunk
```

Không phải mọi tệp có đúng 81 chunk; số chunk phụ thuộc độ dài file và `chunkSize` của lần upload đó.

### Chọn chunk size lớn hay nhỏ?

| Chunk nhỏ | Chunk lớn |
| --- | --- |
| Nhiều chunk documents hơn | Ít chunk documents hơn |
| Nhiều metadata/index entries hơn | Giảm overhead per chunk |
| Có thể phù hợp một số kiểu streaming/seek | Mỗi thao tác cần xử lý chunk lớn hơn |
| Có thể tăng số thao tác truy xuất | Có thể tăng bộ nhớ/băng thông theo chunk |
| Vẫn có giới hạn overhead | Mỗi chunk phải nằm trong giới hạn BSON document |

**Không tăng chunk size lên đúng 16 MiB**, vì chunk là một BSON document có cả các field khác và overhead. GridFS driver/options và giới hạn server cần được tôn trọng. Kích thước tối ưu phụ thuộc file sizes, pattern download, network latency và memory constraints; phải benchmark thay vì luôn chọn lớn nhất.

### Bộ nhớ khi streaming

Ưu điểm của API stream là ứng dụng có thể xử lý file lớn với **bộ nhớ tương đối giới hạn theo buffer/chunk**, thay vì phải giữ toàn bộ file trong RAM.

```text
Sai cho tệp vài GiB:
  đọc toàn bộ file -> byte[] lớn -> upload

Đúng hướng:
  InputStream -> buffer/chunk -> GridFS
       (không cần materialize toàn bộ file)
```

Tuy nhiên, streaming không làm dung lượng mạng hoặc tổng bytes ghi xuống MongoDB nhỏ đi. Nó chủ yếu giúp kiểm soát **RAM, backpressure và đường truyền dữ liệu**.

## 5. Chu trình upload một tệp GridFS

Ở mức khái niệm, trình tự upload là:

```text
Client mở input stream
        |
        v
GridFS upload API
        |
        +--> đọc byte 0..N
        |
        +--> ghi chunk n=0
        +--> ghi chunk n=1
        +--> ghi chunk n=2
        +--> ...
        |
        v
Ghi file entry trong <bucket>.files
        |
        v
Trả file ID / kết quả upload
```

Theo quy ước GridFS, file entry metadata chỉ nên được công bố sau khi nội dung chunk được ghi hoàn tất. Điều đó giúp tránh việc một reader nhìn thấy file entry hoàn chỉnh trong khi file còn đang upload bình thường.

Nhưng đây **không phải** một multi-document transaction tự động cho mọi chunk. Nếu tiến trình chết sau khi ghi một số chunk nhưng trước khi ghi file entry, hệ thống có thể còn **orphan chunks**. Nếu gặp lỗi ở thời điểm cuối, client có thể chưa biết rõ file entry đã được ghi hay chưa.

### Điều driver hỗ trợ và điều ứng dụng phải tự lo

Driver GridFS giúp:

- Chia/ghép byte.
- Ghi và đọc collection theo GridFS specification.
- Mở stream để upload/download.
- Quản lý file ID và metadata cơ bản.

Ứng dụng vẫn cần:

- Xác thực và giới hạn dung lượng upload.
- Chống upload trùng do retry.
- Kiểm tra MIME/file signature và scan malware nếu phù hợp.
- Gán owner/tenant/business object.
- Lưu quyền truy cập và version.
- Xử lý trạng thái upload thất bại, file orphan hoặc tệp không còn được tham chiếu.
- Phục vụ HTTP download, caching hoặc CDN nếu cần.
- Theo dõi quota, storage, backup và xóa theo lifecycle.

**GridFS là API lưu trữ byte**, không phải một hệ quản lý tài liệu hoàn chỉnh.

## 6. Chu trình download một tệp GridFS

Khi đã có file ID:

```text
Client gửi fileId
       |
       v
Ứng dụng kiểm tra quyền trên metadata
       |
       v
GridFS tìm file entry
       |
       v
Đọc chunks có files_id tương ứng
       |
       v
Sắp thứ tự n và stream bytes
       |
       v
HTTP response / file output stream
```

Ứng dụng không nên tải file bằng cách `find()` trên `chunks` rồi tự chuyển từng `BinData` thành string. Dùng **GridFSBucket download API**, vì driver xử lý cấu trúc chunk và luồng dữ liệu đúng quy ước.

### Download theo filename hay file ID?

GridFS có thể tìm tệp theo filename, nhưng filename **không unique**. Ví dụ:

```text
filename: invoice.pdf, _id: A1, uploadDate: 08:00
filename: invoice.pdf, _id: B2, uploadDate: 09:00
```

Nếu API chỉ yêu cầu `invoice.pdf`, cần một **chính sách revision** rõ: bản mới nhất, bản được chọn theo business document, hay mọi phiên bản. Đối với ứng dụng nghiệp vụ, thường nên lưu **GridFS file ID** trong record đính kèm để truy xuất chính xác.

### Tải một phần tệp

Một số GridFS driver hỗ trợ các thao tác như seek trên download stream. Nhưng GridFS **không tự biến thành object store có HTTP Range API/CDN**. Nếu người dùng phát video và liên tục tua đến các byte ranges khác nhau, ứng dụng phải tự triển khai streaming/range semantics và kiểm tra hiệu năng đọc chunk.

Tác vụ xem video có thể cần transcoding, adaptive bitrate, caching theo edge và các yêu cầu rất khác upload/download một file PDF. GridFS có thể lưu bytes, nhưng **lưu được không đồng nghĩa phục vụ tốt nhất**.

## 7. Bộ dữ liệu nghiệp vụ: file ID phải liên kết với record nào?

Không nên xem collection `fs.files` như nơi duy nhất xác định mọi quyền sở hữu và trạng thái nghiệp vụ. Một kiến trúc phổ biến tách:

```text
business documents:
  contracts
    { _id:"contract-1001",
      customerId:"C01",
      currentAttachmentId: ObjectId("...") }

GridFS:
  attachments.files
    { _id:ObjectId("..."),
      filename:"contract.pdf",
      metadata:{tenantId:"T01", type:"contract"} }

  attachments.chunks
    { files_id:ObjectId("..."), n:0, data:... }
```

Document hợp đồng giữ **reference** đến phiên bản file đang có hiệu lực. Nếu người dùng tải bản PDF mới, ứng dụng có thể:

1. Upload thành một GridFS file ID mới.
2. Kiểm tra file mới đã hoàn tất và được xác thực.
3. Cập nhật `contracts.currentAttachmentId` sang ID mới theo quy tắc nghiệp vụ.
4. Giữ file cũ cho version history hoặc đưa vào quy trình xóa sau khi không còn tham chiếu.

Không ghi đè trực tiếp nội dung các chunk của file cũ để “cập nhật PDF”. GridFS không được thiết kế như editor có khả năng cập nhật byte tùy ý trong một tệp đang được dùng.

### Metadata gắn ở đâu?

Một số metadata nên nằm trong `attachments.files.metadata`:

```javascript
{
  tenantId: "tenant-01",
  ownerId: "user-123",
  businessType: "contract",
  contentType: "application/pdf",
  sha256: "...",
  classification: "internal",
  ingestionVersion: 2
}
```

Những field này giúp tìm và kiểm tra nhanh theo file entry. Nhưng quyền truy cập thực tế có thể phụ thuộc document nghiệp vụ khác, ví dụ hợp đồng đã đổi owner hoặc đã bị thu hồi quyền. **Metadata không tự là authorization**. Download endpoint phải xác minh ngữ cảnh truy cập hiện tại trước khi trả bytes.

### Đừng dùng path hoặc filename làm ID bảo mật

Filename do người dùng gửi có thể trùng, chứa ký tự không hợp lệ, chuỗi đường dẫn như `../` hoặc chứa nội dung không đáng tin cậy. Dùng file ID (ObjectId/ID ứng dụng) để quản lý và dùng tên hiển thị đã sanitize khi trả về header HTTP. Không ghép trực tiếp filename của user vào đường dẫn local để ghi file.

## 8. Các bài toán GridFS phù hợp

### 8.1. Tệp vượt 16 MiB và ứng dụng đã sử dụng MongoDB

Ví dụ hệ thống hồ sơ phải lưu PDF quét 25–60 MiB. Ứng dụng đã có MongoDB, không muốn thêm hạ tầng object storage cho một lượng tệp vừa phải, và cần các file chỉ truy xuất qua backend đã xác thực.

GridFS là ứng viên đáng xem vì:

- Không bị giới hạn một BSON document 16 MiB cho toàn file.
- Driver có API stream thay vì bắt buộc tải toàn file vào RAM.
- Metadata của file có thể lưu/truy vấn trong MongoDB.
- Dữ liệu file nằm trong hệ thống backup, authentication và replication của MongoDB deployment (với các điều kiện vận hành tương ứng).

Tuy vậy, phải đánh giá disk, replica write traffic, backup size và độ trễ download trước khi quyết định.

### 8.2. File nội bộ tải không quá thường xuyên

Ví dụ bản vẽ kỹ thuật, tệp CAD, hóa đơn scan hoặc tài liệu bảo hành được upload và đọc lại có kiểm soát. GridFS có thể phù hợp khi **tần suất đọc không quá lớn**, người dùng truy cập thông qua backend và việc tích hợp với MongoDB giúp đơn giản hóa quản trị.

### 8.3. Cần tổ chức file theo metadata trong MongoDB

Nếu luồng nghiệp vụ thường cần tìm “tất cả tài liệu PDF của hợp đồng thuộc tenant X và được nộp trong tháng Y”, metadata của file entry giúp xây truy vấn và index.

Ví dụ:

```javascript
db.getCollection("attachments.files").find({
  "metadata.tenantId": "tenant-01",
  "metadata.businessType": "contract",
  uploadDate: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}, {
  filename: 1,
  length: 1,
  uploadDate: 1,
  metadata: 1
})
```

Kết quả là metadata, **không phải toàn bộ bytes**. Đây là cách tránh tải file lớn khi chỉ cần một danh sách.

### 8.4. Cần quản lý cùng hệ MongoDB sẵn có

Một nhóm nhỏ có thể ưu tiên số ít hệ thống cần vận hành. GridFS cho phép dùng cùng:

- Cơ chế replica set/cluster hiện tại.
- MongoDB driver và cấu hình connection.
- Quyền truy cập database.
- Backup, restore, monitoring hạ tầng MongoDB.

Nhưng “cùng hệ” cũng có nghĩa **tệp lớn cùng cạnh tranh tài nguyên** với query nghiệp vụ; đây là đánh đổi về isolation, không phải lợi thế vô điều kiện.

## 9. Khi nào GridFS có thể không phải lựa chọn tốt?

### 9.1. Tệp web/media phục vụ lượng truy cập rất lớn

Ví dụ một nền tảng học trực tuyến có video hàng GiB, hàng chục nghìn người xem đồng thời, cần **CDN**, range requests, adaptive bitrate và caching tại edge. Lưu và phân phát bytes trực tiếp từ database có thể làm MongoDB chịu tải I/O/network không cần thiết.

Một kiến trúc thường cân nhắc:

```text
Uploader
   |
   v
Object storage (raw/video segments)
   |
   +----> CDN ----> Browser/mobile
   |
   v
MongoDB:
  videoId, objectKey, versions, owner, status, metadata
```

MongoDB vẫn giữ vai trò quan trọng cho metadata, authorization và luồng nghiệp vụ; **không nhất thiết phải giữ bytes**.

### 9.2. Tệp rất nhỏ và cần đi cùng document

Nếu tệp vài KiB, ví dụ một chứng thư nhỏ hoặc một ảnh thumbnail nội bộ, và yêu cầu của ứng dụng là đọc cùng document, việc lưu trong field BSON binary có thể đơn giản hơn hai collection GridFS. Nhưng vẫn phải xét tần suất trả toàn document và tác động lên working set.

Không nhúng hàng nghìn ảnh vào một document lớn chỉ vì từng ảnh nhỏ. **Tổng document** vẫn không được vượt 16 MiB và update/retrieval của document có thể trở nên đắt.

### 9.3. Cần POSIX filesystem semantics

GridFS **không phải filesystem chuẩn POSIX** có thể mount và dùng như thư mục bình thường với đầy đủ lock, rename, append, in-place random write và quy tắc permission của hệ điều hành. Nó là giao thức lưu và đọc tệp qua MongoDB driver.

Nếu ứng dụng bên thứ ba yêu cầu một path file thật để mở/seek/lock/write-in-place, cần một filesystem/object storage bridge phù hợp. Không tự coi GridFSBucket như một thư mục trên ổ đĩa.

### 9.4. Cần cập nhật byte giữa tệp thường xuyên

Ví dụ một database file 5 GiB được sửa từng block nhỏ mỗi giây. GridFS được thiết kế cho **upload/download file content**; việc thay đổi nội dung thường nên tạo **file version mới** hoặc lưu ở một hệ thống hỗ trợ block-level editing. Cập nhật trực tiếp các chunk có thể phá vỡ tính toàn vẹn và sự đồng bộ với file metadata.

### 9.5. Chi phí lưu trữ lớn và lifecycle phức tạp

Một kho sao lưu nhiều terabyte với chính sách archive lạnh, versioning, object lock, tiering và cross-region replication có thể được object storage hỗ trợ tự nhiên hơn. Việc đặt tất cả bytes vào MongoDB khiến chi phí replica copies, backup, index và vận hành có thể lớn.

GridFS không tự có cơ chế object lifecycle/tiered cold storage giống mọi dịch vụ object storage; phải tính **toàn bộ chi phí hệ thống**, không chỉ kích thước file gốc.

## 10. So sánh GridFS và object storage một cách có căn cứ

| Tiêu chí | GridFS trong MongoDB | Object storage + MongoDB metadata |
| --- | --- | --- |
| File lớn hơn 16 MiB | **Có**, nhờ chunks | **Có**, qua object API |
| Upload/download stream | Có qua driver/API | Có qua SDK/HTTP API |
| Metadata/query trong MongoDB | Metadata file lưu ngay trong MongoDB | MongoDB lưu metadata và object key |
| CDN/public distribution | Cần lớp ứng dụng/caching riêng | Thường có tích hợp CDN thuận lợi hơn |
| HTTP Range/video streaming | Có thể xây qua download stream/seek, cần triển khai | Object API thường hỗ trợ ranged GET tốt |
| Quản trị hạ tầng | Gắn với MongoDB sẵn có | Thêm dịch vụ/storage credentials và tích hợp |
| Backup/restore | File data góp vào quy mô backup MongoDB | Backup DB và policy backup object phải phối hợp |
| Chi phí replica copies | Bytes được replication theo cấu hình MongoDB | Do object storage quản lý replication/durability |
| Data locality với metadata | Cùng deployment DB | Metadata và bytes ở hai hệ thống |
| Thay đổi version | Upload file mới; quản lý pointer | Object versioning hoặc key mới + pointer |
| Xóa/retention | Ứng dụng xử lý lifecycle và GridFS delete | Object lifecycle rules có thể giúp |
| Concurrency đọc file cực lớn | Có thể cạnh tranh tài nguyên MongoDB | Dịch vụ blob/CDN thường tối ưu cho traffic này |
| Giao dịch atomic giữa metadata và bytes | **Không tự bảo đảm** cho nhiều GridFS documents | Cũng không có transaction chung với MongoDB mặc định |

**Tài nguyên quyết định:** ứng dụng cần một file store tích hợp với database, hay cần nền tảng phân phát/archival object quy mô lớn? Chi phí lập trình và vận hành cả hai phía phải được tính, không chỉ số dòng code upload.

### Object storage không tự giải quyết giao dịch hai hệ thống

Lưu file trên object storage rồi cập nhật MongoDB reference tạo một quy trình hai bước:

```text
Upload object -> ghi objectKey vào MongoDB
```

Nếu bước thứ hai lỗi, object có thể bị **orphan**. Nếu ghi DB reference trước upload, record có thể trỏ tới object chưa tồn tại. Vì vậy cả mô hình GridFS **và** object storage đều cần lifecycle, retry và cleanup; khác biệt là vị trí lưu bytes và giao thức cần điều phối.

## 11. Tiêu chí lựa chọn: mô hình quyết định

Hãy trả lời các câu hỏi trước khi chọn:

1. **Dung lượng một tệp:** nhỏ hơn 16 MiB hay có thể lớn hàng trăm MiB/GiB?
2. **Số lượng tệp:** vài nghìn, vài triệu hay nhiều hơn?
3. **Tổng dung lượng:** vài GiB hay nhiều terabyte?
4. **Tỷ lệ đọc/ghi:** upload ít, download thường xuyên; hay write-heavy?
5. **Đường tải:** qua backend riêng, HTTP Range, CDN, mobile, media streaming?
6. **Độ lớn file và cách truy cập:** tải trọn file hay cần nhiều byte ranges/seek?
7. **Nhu cầu metadata:** filter theo tenant, owner, loại tài liệu, version, timestamp?
8. **Bảo mật:** tài liệu nội bộ, PII, cần signed URL, scan malware, mã hóa?
9. **Retention:** xóa sau 30 ngày, giữ vĩnh viễn, archive lạnh, legal hold?
10. **Độ bền/phục hồi:** cần backup point-in-time, cross-region, kiểm tra checksum?
11. **Độ tải hiện tại của MongoDB:** database có đang chạy OLTP quan trọng với latency thấp?
12. **Khả năng vận hành:** đội có đang dùng object storage hay muốn tránh thêm hệ thống?

### Một cây quyết định thực dụng

```text
Có cần lưu bytes trong MongoDB không?
        |
   +----+----+
   |         |
 Không      Có / nên đánh giá
   |         |
   v         v
 Object    File có thể vượt 16 MiB?
 storage      |
           +--+--+
           |     |
          Không  Có
           |     |
           v     v
      Xem BSON  GridFS là ứng viên
      binary     |
      hoặc blob  v
              Cần CDN/range/tiered archive cực mạnh?
                     |
                +----+----+
                |         |
               Có        Không
                |         |
                v         v
           Cân nhắc    Benchmark GridFS
           object      với workload và
           storage     chi phí thực
```

Cây quyết định chỉ giúp đặt câu hỏi. Có thể dùng object storage ngay cả với file nhỏ, hoặc dùng GridFS cho file không quá lớn nếu cách tổ chức metadata và vận hành thực sự phù hợp.

## 12. Minh họa ba nghiệp vụ cụ thể

### Trường hợp A — PDF hồ sơ nội bộ

Yêu cầu:

- Mỗi PDF 5–100 MiB.
- Trung bình hàng chục đến hàng trăm upload/ngày.
- Chỉ người có quyền mới download qua backend.
- Tìm theo mã hồ sơ, người sở hữu và ngày upload.
- Không có nhu cầu CDN.

GridFS **đáng thử**: dùng stream, metadata MongoDB và cơ chế phân quyền ở backend. Cần kiểm tra áp lực backup, tốc độ download, số chunk và cleanup khi lỗi.

### Trường hợp B — video bài học

Yêu cầu:

- Video 100 MiB đến vài GiB.
- Hàng nghìn lượt xem đồng thời.
- Người xem có thể tua, chọn bitrate và tải từ nhiều khu vực.
- CDN và cache tại edge là yêu cầu quan trọng.

Object storage + CDN thường là **ứng viên nổi bật**. MongoDB lưu record video, metadata, owner, quyền, file versions và trạng thái xử lý. GridFS vẫn có thể lưu bytes về mặt kỹ thuật, nhưng có thể tạo gánh nặng phân phát nội dung không cần thiết trên MongoDB.

### Trường hợp C — thumbnail 30 KiB trong một record

Yêu cầu:

- Ảnh thumbnail nhỏ.
- Luôn đọc cùng document hồ sơ.
- Không có lưu lượng public lớn.
- Chỉ một ảnh cho mỗi record, không nhiều phiên bản.

Field BSON binary có thể đơn giản hơn GridFS. Tuy nhiên nếu danh sách hồ sơ được query rất thường xuyên nhưng không cần bytes ảnh, nhúng thumbnail trực tiếp có thể làm tăng payload/cache. Khi đó tách file thành GridFS/object storage hoặc collection riêng có thể phù hợp hơn.

## 13. Thực hành với `mongofiles`

**`mongofiles`** là công cụ dòng lệnh thuộc bộ **MongoDB Database Tools**, chuyên thao tác với GridFS. Nó không phải một helper có sẵn trong mọi phiên bản `mongosh`; cần cài đúng Database Tools và cấu hình kết nối phù hợp.

Ví dụ minh họa cho **MongoDB lab ở localhost**:

```bash
# Upload file demo.pdf vào bucket mặc định fs
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab put demo.pdf

# Liệt kê file trong bucket fs
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab list

# Download file cùng tên từ bucket (chú ý nơi chạy lệnh)
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab get demo.pdf
```

Các lệnh phụ thuộc phiên bản `mongofiles` và quyền trên server; nếu file `demo.pdf` chưa tồn tại ở working directory thì `put` sẽ thất bại. Với cluster có xác thực, dùng URI và cơ chế giữ credential an toàn thay vì ghi mật khẩu vào shell history.

**Cẩn thận với trùng tên và đường dẫn local khi download.** Đừng tự ghi đè một tệp đang được dùng ở production; dùng một thư mục lab và kiểm tra output theo công cụ. Trong ứng dụng thực, download theo **GridFS file ID** qua driver thường rõ ràng hơn dựa vào filename.

### Một ghi chú về bucket name

Ba ví dụ `mongofiles` trên dùng bucket mặc định `fs`. Nếu code Java ở các mục sau tạo bucket `attachments`, những file ấy nằm trong **`attachments.files` và `attachments.chunks`**, không xuất hiện trong `fs.files` trừ khi công cụ đã chọn đúng prefix/bucket.

## 14. Quan sát file metadata bằng `mongosh`

Sau khi `mongofiles put demo.pdf` thành công, vào database:

```javascript
use gridfs_lab

db.getCollection("fs.files").find(
  {},
  {
    filename: 1,
    length: 1,
    chunkSize: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
```

Chọn một file entry:

```javascript
const file = db.getCollection("fs.files").findOne({
  filename: "demo.pdf"
});

if (file) {
  printjson({
    id: file._id,
    filename: file.filename,
    length: file.length,
    chunkSize: file.chunkSize,
    estimatedChunkCount: Math.ceil(
      Number(file.length) / file.chunkSize
    )
  });
}
```

**Chỉ để quan sát metadata**, không tải bytes bằng query này.

Đếm chunks:

```javascript
if (file) {
  const count = db.getCollection("fs.chunks").countDocuments({
    files_id: file._id
  });
  print("chunk count =", count);
}
```

Trong một file hoàn chỉnh không hỏng, số chunk thường khớp phép tính dựa trên `length` và `chunkSize`, với file rỗng có thể có **0 chunk**. Nếu không khớp, cần điều tra về upload chưa hoàn tất/corruption và tình trạng index, nhưng **không sửa tay chunk** chỉ dựa trên một phép đếm.

### Đừng đọc toàn bộ bytes của chunks khi chỉ cần metadata

```javascript
// Không nên làm cho file rất lớn nếu chỉ muốn danh sách:
db.getCollection("fs.chunks").find({ files_id: file._id })
```

Lệnh trên có thể trả nhiều `BinData` lớn về client. Khi cần quan sát cấu trúc:

```javascript
db.getCollection("fs.chunks").find(
  { files_id: file._id },
  { _id: 0, files_id: 1, n: 1 }
).sort({ n: 1 }).limit(5)
```

Khi cần download bytes, dùng GridFS API hoặc `mongofiles get` thay vì tự ghép chuỗi nhị phân.

## 15. Upload bằng MongoDB Java Sync Driver

MongoDB Java Sync Driver có những API thường gặp:

- `GridFSBuckets.create(database, bucketName)` để lấy GridFSBucket.
- `uploadFromStream()` để upload từ một `InputStream`.
- `downloadToStream()` để download vào một `OutputStream`.
- `find()` để truy vấn file entries.
- `delete()` để xóa một file ID cùng các chunk liên quan theo cơ chế GridFS.
- `GridFSUploadOptions` để đặt chunk size và metadata.

Ví dụ sử dụng MongoDB Java Sync Driver tương thích, Java 17+ để đọc file từ ổ cứng lab và tạo GridFS entry. Biến môi trường `MONGODB_URI` chứa URI phù hợp; không hard-code credential.

### 15.1. Upload PDF theo stream

```java
import com.mongodb.WriteConcern;
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

public class UploadGridFsFile {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        Path source = Path.of("demo.pdf");
        if (!Files.isRegularFile(source)) {
            throw new IllegalArgumentException(
                "Không có file demo.pdf trong thư mục lab"
            );
        }

        // Ví dụ đặt một giới hạn upload nghiệp vụ riêng.
        long maxBytes = 200L * 1024 * 1024;
        if (Files.size(source) > maxBytes) {
            throw new IllegalArgumentException(
                "File vượt giới hạn 200 MiB của ứng dụng"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client
                .getDatabase("gridfs_lab")
                .withWriteConcern(WriteConcern.MAJORITY);

            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            Document metadata = new Document(
                "tenantId", "tenant-01")
                .append("ownerId", "user-123")
                .append("businessType", "contract")
                .append("contentType", "application/pdf")
                .append("status", "uploaded");

            GridFSUploadOptions options =
                new GridFSUploadOptions()
                    .chunkSizeBytes(255 * 1024)
                    .metadata(metadata);

            try (InputStream input =
                     Files.newInputStream(source)) {
                ObjectId fileId = bucket.uploadFromStream(
                    "demo.pdf", input, options);

                System.out.println(
                    "GridFS file ID: " + fileId.toHexString()
                );
            }
        }
    }
}
```

Code này:

1. Kiểm tra file local và kích thước upload theo chính sách ứng dụng.
2. Tạo bucket tên `attachments`.
3. Cấu hình metadata và chunk size.
4. Stream bytes qua driver.
5. Nhận file ID khi upload hoàn tất theo API.

**Không có thao tác `Files.readAllBytes(source)`**, nên ứng dụng không cần giữ toàn bộ PDF trong một `byte[]`. Bộ nhớ vẫn dùng cho buffers và hoạt động của driver, nhưng không tỷ lệ tuyến tính với kích thước nguyên file theo cách đọc tất cả bytes vào RAM.

### Tại sao dùng `withWriteConcern(WriteConcern.MAJORITY)`?

Ví dụ muốn GridFS writes được server xác nhận với mức write concern của database handle phù hợp, để giảm rủi ro những ghi đã được acknowledgment bị rollback khi failover thông thường.

Tuy vậy, **write concern majority không biến tất cả các chunk writes thành một transaction duy nhất**. Nếu upload lỗi giữa chừng, vẫn cần xử lý thất bại, retry/idempotency và cleanup. Độ trễ upload có thể tăng khi yêu cầu replication acknowledgment mạnh hơn.

### Nếu dữ liệu đầu vào đến từ HTTP

Trong web service, nguồn bytes có thể là `InputStream` của request upload thay vì một file trên ổ đĩa. Nhưng phải kiểm soát:

- Quota theo user/tenant.
- Tổng bytes thực đọc, không chỉ HTTP Content-Length do client khai báo.
- Timeout và tốc độ đọc tối thiểu để tránh kết nối treo.
- Số upload đồng thời.
- Kiểm tra loại tệp và malware.
- Các hạn chế request/multipart của web framework.
- Tình trạng client đóng kết nối giữa chừng.

GridFSBucket không tự xử lý các vấn đề HTTP/security này.

## 16. Download bằng Java Sync Driver

Giả sử ứng dụng đã lưu GridFS file ID trong document hợp đồng, có thể download chính xác bằng ID:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import org.bson.types.ObjectId;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DownloadGridFsFile {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");
        String rawFileId = System.getenv("GRIDFS_FILE_ID");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }
        if (rawFileId == null || !ObjectId.isValid(rawFileId)) {
            throw new IllegalArgumentException(
                "Thiếu hoặc sai GRIDFS_FILE_ID");
        }

        ObjectId fileId = new ObjectId(rawFileId);
        Path destination = Path.of("downloaded-demo.pdf");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("gridfs_lab");
            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            try (OutputStream output = Files.newOutputStream(
                    destination,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                bucket.downloadToStream(fileId, output);
            }
        }

        System.out.println(
            "Đã download vào " + destination.toAbsolutePath());
    }
}
```

Ví dụ dùng `CREATE_NEW` để **không vô tình ghi đè tệp lab đã tồn tại**. Nếu download giữa chừng báo lỗi, file output có thể chỉ chứa **một phần bytes**. Ứng dụng thực nên download vào **temporary path**, xác minh độ dài/checksum, sau đó rename/move an toàn hoặc xóa file tạm khi lỗi.

### Xác minh quyền trước khi tải

Trong backend đa tenant, không nên chỉ nhận một `fileId` từ URL rồi tải tệp. Ứng dụng phải kiểm tra user có quyền truy cập file và business record tương ứng.

```text
GET /attachments/{fileId}
       |
       v
Authenticate user
       |
       v
Load business record and GridFS metadata
       |
       v
Authorize tenant / owner / ACL
       |
       v
Stream download
```

Client có được một ObjectId hợp lệ **không đồng nghĩa** client được phép tải nội dung của ID đó.

## 17. Liệt kê file, lấy metadata và xóa bằng Java

Một backend thường cần liệt kê các tệp của một tenant mà **không tải nội dung**.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

public class ListGridFsFiles {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("gridfs_lab");
            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            for (GridFSFile file : bucket.find(
                    Filters.eq("metadata.tenantId", "tenant-01"))
                    .sort(Sorts.descending("uploadDate"))
                    .limit(20)) {
                System.out.println(
                    file.getId()
                        + " | " + file.getFilename()
                        + " | " + file.getLength()
                        + " bytes"
                );
            }
        }
    }
}
```

Ở đây `find()` chỉ trả **file metadata**, không download từng chunk. Nếu truy vấn theo `metadata.tenantId` và `uploadDate` thường xuyên trên bucket lớn, có thể đánh giá index phù hợp trên `attachments.files`; tránh thêm index trùng hoặc thiếu chọn lọc.

### Xóa file theo ID

Khi business workflow cho phép xóa, Java GridFSBucket hỗ trợ:

```java
// Chỉ thực hiện sau khi đã xác thực quyền và
// xác nhận file không còn được business record tham chiếu.
bucket.delete(fileId);
```

Không dùng lệnh:

```javascript
// KHÔNG XÓA THỦ CÔNG MỘT MẢNH:
db.getCollection("attachments.chunks").deleteMany({
  files_id: someFileId
});
```

nếu mục tiêu là xóa một file hợp lệ, bởi việc thao tác trực tiếp có thể làm mất nội dung mà file entry vẫn còn, tạo dữ liệu hỏng. Dùng API GridFS và chính sách lifecycle.

Một lần `delete()` cũng có thể lỗi giữa các bước. Ứng dụng cần hiểu rằng **xóa GridFS file có thể liên quan nhiều documents** và phải có quy trình phát hiện những tệp/chunks còn sót.

## 18. Kiểm tra tính toàn vẹn bằng checksum

Giả sử upload một file 40 MiB và lưu `length` trong file entry. Kích thước đúng **không đủ** để chứng minh từng byte giống nguồn: hai tệp có thể cùng độ dài nhưng khác nội dung.

Một cách thực tế là tính **SHA-256** ở tầng ứng dụng:

1. Tính hash của file nguồn theo stream.
2. Upload nội dung và lưu hash trong metadata hoặc business record.
3. Khi download, tính lại SHA-256 trên bytes nhận được.
4. So sánh hash và độ dài trước khi công bố file đã xác minh.

### Java tính SHA-256 không đọc toàn bộ file vào RAM

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class FileHash {
    public static String sha256(Path path) throws Exception {
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
```

Hàm dùng Java 17+ cho `HexFormat`. Nó không giữ file lớn trong bộ nhớ.

**Một lưu ý về tính nhất quán:** nếu ứng dụng tính hash trước, rồi file nguồn **bị thay đổi** trước/trong khi upload, metadata hash có thể không khớp bytes đã upload. Cần dùng nguồn immutable/staging file hoặc tính hash theo cùng luồng bytes được upload và cập nhật metadata sau khi hoàn tất bằng quy trình được kiểm soát.

### Checksum không thay thế authentication

Một hash phát hiện nội dung không khớp với hash đã lưu, nhưng nếu attacker có quyền sửa **cả file và metadata hash**, việc so hash thông thường không bảo vệ được tính xác thực. Với yêu cầu chống giả mạo mạnh, cần cơ chế ký số, kiểm soát quyền, audit và quản lý khóa phù hợp.

## 19. Duplicate filename, file version và idempotent upload

Giả sử một user upload `contract.pdf`, request bị timeout ngay sau khi server ghi xong. User bấm Upload lại.

```text
Upload request #1
    |
    +--> chunks đã ghi
    +--> files entry đã ghi
    |
    X  Response bị mất
    |
Upload request #2
    |
    +--> một file ID mới
    +--> nhiều chunks mới
```

Kết quả có thể là **hai GridFS files có cùng filename** và nội dung giống nhau. Driver trả error phía client không luôn cho biết bản upload trước chắc chắn chưa hoàn thành.

### Không dùng filename làm idempotency key

Hai người có thể upload hai file khác nhau cùng tên `contract.pdf`. Ngược lại cùng một user có thể cố tình upload bản v2 cũng dùng tên đó. Do đó, filename không đại diện cho một logical upload.

Thiết kế có thể dùng:

- **uploadRequestId** do backend cấp, duy nhất trong phạm vi tenant/business operation.
- **content hash** để hỗ trợ phát hiện nội dung trùng, với chính sách rõ liệu có được dedupe không.
- **version** của business attachment.
- Một **attachment record** có unique index theo khóa nghiệp vụ.
- Trạng thái `PENDING`, `UPLOADED`, `SCANNED`, `ACTIVE`, `FAILED`.

Ví dụ một record nghiệp vụ:

```javascript
{
  _id: "attach-1001",
  tenantId: "tenant-01",
  contractId: "contract-1001",
  uploadRequestId: "req-8f2d",
  fileId: ObjectId("65f000000000000000000001"),
  filename: "contract.pdf",
  sha256: "...",
  version: 2,
  state: "ACTIVE",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Nếu client retry cùng `uploadRequestId`, ứng dụng có thể trả lại kết quả đã ghi thay vì tạo file mới. Cơ chế cần được bảo vệ bằng unique constraint/conditional updates phù hợp và xử lý cạnh tranh; **chỉ kiểm tra trước bằng `findOne()` rồi insert không bảo đảm chống đua dữ liệu**.

### Thay tệp nhưng giữ phiên bản cũ

```text
contract-1001.currentAttachmentId ---> file A (v1)

Upload file B (v2)
        |
        v
Validate & scan thành công
        |
        v
Update contract pointer -> file B
        |
        v
file A: giữ trong lịch sử hoặc đưa vào cleanup
```

Không xóa file A **trước khi** pointer sang B đã an toàn nếu nghiệp vụ cần luôn có tệp có thể tải. Khi thay đổi pointer và xóa file liên quan nhiều collection, cần chính sách nhất quán/đối soát chứ không giả định GridFS có transaction tất cả các bước.

## 20. Upload lỗi giữa chừng và orphan chunks

Một trong những vấn đề vận hành quan trọng nhất là upload không hoàn tất:

```text
File 100 MiB
    |
    +-- chunk 0  [ghi xong]
    +-- chunk 1  [ghi xong]
    +-- chunk 2  [ghi xong]
    +-- ...
    +-- chunk 100 [ghi xong]
    |
    X  Mạng ngắt / process crash
    |
    ?  Chưa có file entry trong attachments.files
```

Những chunks đã ghi nhưng **không có files entry tương ứng** được gọi là **orphan chunks**. Tùy thời điểm lỗi và hành vi của driver, có thể còn dữ liệu thừa cần thu gom.

### Vì sao không xóa orphan chunks ngay khi vừa nhìn thấy?

Một file **đang upload hợp lệ** cũng có thể đã ghi chunks nhưng file entry chưa được công bố. Nếu job cleanup chạy trong lúc upload đang hoạt động, nó có thể xóa chunks còn cần, làm hỏng upload.

Do đó, quy trình cleanup cần:

1. Xác định upload đang hoạt động/đã hết lease hay không.
2. Có **grace period** đủ dài so với thời gian upload tối đa.
3. Phân biệt files entries còn tồn tại và chunks không được tham chiếu.
4. Xác nhận không có writer đang tiếp tục dùng file ID tương ứng.
5. Chạy theo batch và ghi log những gì bị xóa.
6. Có dry-run, cảnh báo và kế hoạch phục hồi cho môi trường production.

Không dùng một lệnh `deleteMany()` tự chế quét `fs.chunks` trên production khi chưa nắm rõ trạng thái các uploads.

### Xóa file không còn tham chiếu

Một loại orphan khác là **file entry hoàn chỉnh và đủ chunks**, nhưng không có business document nào còn tham chiếu file ID. Đây là **orphan file**, khác orphan chunk.

Ví dụ:

```text
attachments.files:
  A1, A2, A3

contracts.currentAttachmentId:
  A1, A3

A2 không được tham chiếu từ hợp đồng hiện tại
```

Nhưng A2 có thể vẫn cần được giữ vì là phiên bản lịch sử, legal hold hoặc một nghiệp vụ khác. Vì vậy cleanup phải dựa trên **lifecycle policy**, không chỉ phép join đơn giản từ một collection.

## 21. GridFS và multi-document transaction

Mỗi file GridFS thường trải qua **nhiều document** ở hai collections. **GridFS không hỗ trợ multi-document transactions cho chính các thao tác GridFS upload/download theo quy tắc được MongoDB công bố**, nên không nên tự hứa rằng toàn bộ upload có thể được gói nguyên tử bằng một lệnh transaction chung giống cập nhật hai document nghiệp vụ.

Ngay cả khi ứng dụng dùng MongoDB transactions cho những record khác, vẫn phải thiết kế trạng thái chuyển tiếp cho GridFS:

```text
ATTACHMENT_CREATED
        |
        v
UPLOADING
        |
        v
GRIDFS_UPLOAD_COMPLETE
        |
        v
CHECKSUM/SCAN_COMPLETE
        |
        v
BUSINESS_RECORD_ACTIVE
```

Nếu thất bại ở bất kỳ bước nào, cần xác định:

- Tệp đã tồn tại hoàn chỉnh trong GridFS chưa?
- Business pointer đã trỏ tới tệp chưa?
- Có scan result và checksum hợp lệ chưa?
- Retry nên tiếp tục từ bước nào, hay tạo upload request mới?
- Những bytes thừa được dọn thế nào sau một khoảng chờ?

### Phân biệt nguyên tử business pointer với nguyên tử file upload

Một lệnh:

```javascript
db.contracts.updateOne(
  { _id: "contract-1001", version: 1 },
  {
    $set: { currentAttachmentId: someNewFileId },
    $inc: { version: 1 }
  }
)
```

là một **single-document update** có tính nguyên tử trên document hợp đồng. Nhưng nó **không biến những chunk writes trước đó thành một phần của transaction cùng update**. Đây là ranh giới cần hiểu khi xây hệ quản lý tệp đáng tin cậy.

## 22. Độ bền và write concern cho file lớn

GridFS lưu chunks và metadata trong MongoDB nên vẫn chịu các quy tắc về **write concern** và replication:

- `w:1`: primary acknowledgement theo cấu hình.
- `w:"majority"`: cần mức xác nhận majority phù hợp của replica set.
- `j:true`: yêu cầu điều kiện journal khi phù hợp.
- `wtimeout`: giới hạn thời gian chờ mức xác nhận; timeout không tự kết luận thao tác đã rollback.

Với tệp có nhiều chunks, mức write concern ảnh hưởng tổng latency và throughput. Nếu upload chưa có đủ ACK hoặc kết nối mất giữa chừng, client không được giả định rằng mọi chunk đều đã tồn tại.

**Điểm cần nhớ:** ghi file thông qua MongoDB không có nghĩa mặc nhiên an toàn hơn object storage trong mọi tình huống. Độ bền thực tế còn phụ thuộc:

- Replica set topology và placement theo failure domains.
- Backup/restore, snapshot consistency.
- Disk I/O, corruption và checksum.
- Chính sách cập nhật/xóa tệp.
- Khả năng khôi phục sau lỗi upload/delete.

Đối với một attachment quan trọng, phải kiểm tra đầy đủ từ **upload bytes → metadata → business reference → restore test**, không chỉ xem `insert completed`.

## 23. Backup và restore: luôn nhớ có hai collection

Một file GridFS hoàn chỉnh yêu cầu **file entry và các chunks**. Nếu backup/restore chỉ mang theo `attachments.files` mà bỏ `attachments.chunks`, ứng dụng có thể thấy metadata nhưng không tải được nội dung.

```text
Backup GridFS:
  attachments.files   +
  attachments.chunks  +
  business references +
  metadata/indexes
            |
            v
     Khôi phục có thể dùng được
```

### Consistency của thời điểm backup

Nếu sao lưu file entry ở thời điểm T1 nhưng chunks ở T2 không nhất quán, dữ liệu có thể thiếu, dư hoặc không khớp với business reference. Với hệ hoạt động liên tục, nên dùng phương thức snapshot/backup được MongoDB hỗ trợ và kế hoạch consistency cho các collections liên quan.

### Thử khôi phục, không chỉ thử backup

Một bài kiểm tra restore tốt gồm:

1. Khôi phục các collections GridFS và business records vào môi trường riêng.
2. Chọn một số file ID có nhiều kích thước và phiên bản.
3. Dùng driver download bytes.
4. So độ dài và SHA-256 với metadata nguồn đã tin cậy.
5. Kiểm tra file permission và tenant association.
6. Đối chiếu kết quả khi restore sang cluster/topology khác.

Backup reports thành công chưa chứng minh mọi file đều đọc được sau sự cố. **Restore test** là bằng chứng vận hành mạnh hơn.

## 24. Index metadata và quy mô collection

GridFS tạo nhiều chunks cho mỗi file. Nếu hệ thống có **một triệu file**, số chunk documents có thể lớn hơn nhiều triệu tùy kích thước trung bình.

Giả sử trung bình mỗi file có 100 chunks:

```text
1.000.000 file entries
        × 100 chunks/file
        = 100.000.000 chunk documents
```

Các chunks còn có index entries, BSON overhead, replication và backup bytes. Vì thế, quyết định GridFS cần dự báo **số chunks**, không chỉ số file.

### Index cho truy vấn metadata

Nếu API liệt kê file của một tenant theo thời điểm:

```javascript
db.getCollection("attachments.files").createIndex(
  {
    "metadata.tenantId": 1,
    uploadDate: -1
  },
  { name: "idx_tenant_upload_date" }
)
```

Index trên hỗ trợ một truy vấn metadata phổ biến, nhưng vẫn có chi phí ghi/index storage. Không cần tạo index riêng cho mọi metadata field nếu không có query cần nó.

### Đừng index payload chunk `data`

`data` chứa bytes nhị phân. Index trên `data` không giúp tìm tên file, owner hay content type theo cách thông thường, và có thể gây chi phí lớn. Hãy index **metadata có ý nghĩa truy vấn**, không index toàn bộ binary payload.

### Tìm theo filename có ổn không?

`filename` là trường hữu ích khi người dùng muốn xem danh sách, nhưng không nên làm business primary key. Cùng tên có nhiều phiên bản, ký tự Unicode và chính sách chuẩn hóa khác nhau. File ID vẫn là định danh kỹ thuật ổn định hơn cho download/delete.

## 25. Bảo mật và an toàn tệp tải lên

Một tệp đính kèm có thể chứa dữ liệu nhạy cảm hoặc mã độc. Dù lưu trong MongoDB, ứng dụng vẫn phải bảo vệ cả metadata và bytes.

### 25.1. Authorization theo tenant và business record

Ví dụ user của tenant A đoán được ObjectId thuộc tenant B. Nếu endpoint tải file theo ID mà không kiểm tra quyền, đó là lỗ hổng nghiêm trọng.

Quy trình nên gồm:

1. Xác thực request.
2. Lấy business record/attachment record thuộc tenant người dùng được phép.
3. Kiểm tra role, owner, trạng thái và policy.
4. Xác định GridFS file ID gắn đúng record.
5. Stream bytes chỉ sau khi kiểm tra quyền.
6. Audit các download quan trọng.

Không tin `metadata.tenantId` do client tự truyền trong request upload; backend phải lấy tenant từ **ngữ cảnh xác thực đáng tin cậy**.

### 25.2. MIME type không phải bằng chứng file an toàn

Client có thể gửi:

```text
filename = invoice.pdf
Content-Type = application/pdf
```

nhưng bytes thật có thể không phải PDF. Nên kiểm tra file signature/magic bytes và áp dụng malware scanning/quarantine khi phù hợp. Không dựa vào phần mở rộng `.pdf` hoặc Content-Type header như bằng chứng.

### 25.3. Mã hóa và quyền truy cập database

Sử dụng TLS cho kết nối, quyền database tối thiểu, secret management và mã hóa lưu trữ theo yêu cầu. Nếu cần **application-level encryption**, phải định nghĩa vị trí mã hóa/giải mã stream, quản lý khóa và ảnh hưởng đến checksum/range requests.

### 25.4. HTTP response an toàn

Khi trả file, cần thiết lập header phù hợp:

- `Content-Type` được xác minh hoặc policy cho phép.
- `Content-Disposition` an toàn, có xử lý tên Unicode và ký tự đặc biệt.
- `X-Content-Type-Options: nosniff` khi phù hợp.
- Cache-control theo mức độ nhạy cảm.
- Giới hạn download concurrency, rate/bytes quota.

Không render trực tiếp HTML/SVG do user upload trong cùng origin mà không xét nguy cơ script/content injection.

## 26. Hiệu năng: những yếu tố ảnh hưởng upload/download

GridFS không tự nhanh hơn mọi hệ thống file. Một file 500 MiB có thể tạo hàng nghìn chunks, cần nhiều thao tác ghi/đọc, index access, network và replication.

### Upload throughput phụ thuộc:

- Chunk size và số chunk.
- Network latency giữa app và MongoDB.
- Write concern, journaling và replica lag.
- Disk throughput và write amplification.
- Nhiều upload song song.
- Driver connection pool và read buffer.
- Cấu hình sharding, tải các shard và indexes.

### Download throughput phụ thuộc:

- Vị trí server và client.
- Cache hit và I/O đọc.
- Số chunk/round-trip theo implementation driver.
- Xử lý HTTP streaming ở app.
- Network/bandwidth và giới hạn người dùng.
- Kiểm tra checksum, giải mã, nén và malware scanning nếu thực hiện khi download.

### Tác động lên OLTP workload

Giả sử cùng replica set đang phục vụ truy vấn đơn hàng latency thấp, và một job backup bắt đầu upload 200 file × 1 GiB:

```text
GridFS uploads
  -> disk writes
  -> oplog / replication traffic
  -> cache / I/O pressure
  -> có thể ảnh hưởng p95 query nghiệp vụ
```

Tách workload bằng storage tier/cluster riêng hoặc chọn object storage có thể là một quyết định kiến trúc hợp lý. Không chỉ nhìn throughput upload khi benchmark; cần đo **p95/p99 của API nghiệp vụ đang chạy song song**.

## 27. Benchmark GridFS với object storage

Thiết lập một workload đại diện:

| Loại file | Kích thước | Tần suất | Đường truy cập |
| --- | ---: | --- | --- |
| Ảnh thumbnail | 30 KiB | Rất nhiều | Web/mobile, cache/CDN |
| PDF hợp đồng | 20–80 MiB | Vừa | Backend authenticated |
| File ZIP xuất báo cáo | 100–500 MiB | Ít | Download theo yêu cầu |
| Video bài học | 200 MiB–2 GiB | Nhiều lượt đọc | Range/CDN |
| Log archive | 1–10 GiB | Ít đọc | Lưu trữ dài hạn |

Đo:

1. Upload p50/p95/p99 và throughput MiB/s.
2. Download p50/p95/p99, time-to-first-byte và throughput.
3. Số bytes thực truyền, retry traffic và số lần client timeout.
4. RAM/CPU của service upload/download.
5. I/O, cache, replication lag và query latency của MongoDB.
6. Tổng dung lượng **files + chunks + indexes**, tính cả replica copies/backup.
7. Chi phí storage, network egress và bảo trì.
8. Khả năng phục vụ HTTP Range, CDN hit ratio và latency đa khu vực.
9. Khả năng tìm kiếm metadata, version và chính sách xóa.
10. Mức phức tạp của backup/restore và cleanup sau lỗi.

**Không so sánh một lần tải file từ localhost GridFS với object storage ở một khu vực mạng xa rồi kết luận hệ nào nhanh hơn tuyệt đối.** Benchmark cần môi trường, topology và concurrency đại diện.

### Công thức dự báo số chunks

Với `N` file có kích thước `L_i` byte và chunk size `C_i`:

```text
chunks_for_file_i = ceil(L_i / C_i)
total_chunks ≈ sum(chunks_for_file_i)
```

Đây là ước lượng số document chunks cho những file hoàn chỉnh; chưa gồm orphan chunks, indexes, compression, replicas, oplog và backup. Đối với file rỗng, thường không có data chunk nhưng có file entry metadata.

## 28. Sharding GridFS: có thể mở rộng nhưng không tự động

Một GridFS bucket được lưu trong MongoDB collections, nên khi triển khai lớn có thể cần nghiên cứu **sharding** hoặc phân vùng workload. Nhưng không nên suy rằng “file được chia chunk” đồng nghĩa “đã chia đều chunk trên nhiều shard”.

Hai khái niệm khác nhau:

- **Chunk của GridFS**: mảnh dữ liệu nhị phân của một file.
- **Shard-key range/chunk của sharded cluster**: đơn vị phân phối dữ liệu MongoDB giữa các shard.

Nếu cần sharding các collection GridFS:

1. Kiểm tra **khả năng sharding, shard key và index restrictions** cho phiên bản MongoDB đang dùng.
2. Giữ tương thích với index/đường truy vấn `files_id + n` của GridFS.
3. Cân nhắc một file lớn có tạo hotspot ở một shard không.
4. Đo tác động scatter-gather/routing khi tìm metadata hoặc tải từng chunk.
5. Đánh giá chi phí balancer, shard migration, backup và restore.
6. Không sửa trực tiếp collection layout/chunk data mà bỏ qua GridFS driver.

Một giải pháp có nhiều shards nhưng mọi file download tập trung vào một nhóm tài nguyên có thể vẫn gặp bottleneck. Nếu workload chủ yếu phân phát bytes tới public users, object storage/CDN có thể phù hợp hơn so với mở rộng sharded cluster chỉ để phục vụ media.

## 29. GridFS và chính sách retention/xóa dữ liệu

Giả sử quy định là xóa file hợp đồng sau bảy năm, trừ các bản được giữ theo legal hold. Có thể lưu:

```javascript
{
  _id: "attach-1001",
  fileId: ObjectId("65f000000000000000000001"),
  uploadedAt: ISODate("2026-11-14T08:00:00Z"),
  retentionUntil: ISODate("2033-11-14T00:00:00Z"),
  legalHold: false,
  status: "ACTIVE"
}
```

Một job lifecycle:

1. Tìm attachment records đã hết hạn và không có legal hold.
2. Xác minh không có business reference cần giữ.
3. Đánh dấu `DELETING` hoặc trạng thái tương đương để tránh race.
4. Gọi GridFS delete theo ID có kiểm soát.
5. Ghi nhận việc xóa và đối soát files/chunks.
6. Cập nhật trạng thái nghiệp vụ, lưu audit metadata nếu policy cho phép.

**Không tạo TTL index trên `attachments.files.uploadDate` rồi coi việc MongoDB tự xóa file entry sẽ xóa mọi chunk liên quan**. TTL trực tiếp trên file metadata có thể xóa entry mà không qua GridFS delete workflow, để lại dữ liệu mồ côi trong `chunks`. Retention của GridFS phải được thực thi theo **đúng quy trình xóa file**, không chỉ xóa metadata.

Nếu cần hard delete theo yêu cầu pháp lý, còn phải xem backup retention, replica copies, cache, object versions và bằng chứng xóa. GridFS không tự xử lý toàn bộ khía cạnh compliance.

## 30. Khi nào cần giữ file immutable?

Một thực hành hữu ích là coi **mỗi GridFS file ID là một phiên bản nội dung immutable**:

```text
File A -> sha256 A -> attachment version 1
File B -> sha256 B -> attachment version 2

Business record -> current version = B
```

Lợi ích:

- Checksum/version rõ ràng.
- Download đang diễn ra không bị thay bytes giữa chừng.
- Dễ audit file nào đã được ký/duyệt.
- Có thể rollback business pointer sang phiên bản cũ nếu policy cho phép.
- Cleanup dựa vào reference count/retention rõ ràng hơn.

Nhược điểm là lưu nhiều version tốn dung lượng. Do đó, cần chính sách version retention và deduplication có kiểm soát; không tự dùng chung một file giữa các tenant nếu quyền xóa và phân tách dữ liệu không cho phép.

## 31. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Insert BinData file 30 MiB thất bại | BSON document vượt 16 MiB | GridFS hoặc object storage |
| Tạo bucket `attachments` nhưng `fs.files` trống | Kiểm tra sai bucket | Xem `attachments.files`/`attachments.chunks` |
| Hai `contract.pdf` xuất hiện | Filename không unique, upload lại/versions | Lưu file ID, operation ID và revision |
| Upload treo rồi timeout | Mạng/I/O/write concern/backend quá tải | Xác định trạng thái, retry idempotent, cleanup |
| Chunks tồn tại nhưng không có files entry | Upload bị hủy giữa chừng | Detect orphan, grace period, controlled cleanup |
| Files entry có nhưng download thiếu bytes | Chunk thiếu/hỏng hoặc restore không nhất quán | Kiểm tra dữ liệu/index/backup, checksum |
| Download cả file vào byte array làm OOM | Không dùng stream | Dùng InputStream/OutputStream và buffers |
| User tải được file tenant khác | Chỉ dựa vào file ID | AuthN/AuthZ trên business record và tenant |
| File `.pdf` thực ra không phải PDF | Tin MIME/extension của client | Kiểm tra signature, malware scanning |
| Xóa trực tiếp file entry, chunks còn lại | Bỏ qua GridFS delete | Dùng bucket.delete và lifecycle |
| TTL trên `fs.files` gây dữ liệu thừa | TTL chỉ xóa file entry | Thiết kế retention theo GridFS delete |
| Tải video chậm dù GridFS lưu được | Thiếu CDN/range/streaming architecture | So với object storage/CDN |
| Query metadata chậm | Chưa có index cho metadata filter | Tạo index phù hợp trên `files` |
| DB API đơn hàng chậm khi upload nhiều | GridFS cạnh tranh I/O/replication | Isolate workload/scale/chọn storage khác |
| File ID được trả nhưng business pointer chưa ghi | Hai bước không nguyên tử chung | Retry/state machine, reconciliation |
| Thay file bằng sửa chunk trực tiếp | Vi phạm GridFS structure | Upload version mới |
| Backup khôi phục metadata nhưng không mở file | Thiếu chunks hoặc snapshot sai thời điểm | Backup cả collections, restore test |
| SHA-256 stored không khớp download | Source thay giữa hai pass hoặc corruption | Immutable staging, kiểm tra end-to-end |
| Dùng file name từ URL làm local path | Path traversal/trùng tên | Dùng ID, sanitize, tempfile |
| Đội chỉ nhìn file count mà không tính chunk count | Overhead bị đánh giá thấp | Ước lượng chunks, indexes, replicas |

## 32. Bài tập có đáp án

### Bài 1. Giới hạn document

Ứng dụng muốn lưu một file ZIP 25 MiB trong một field `BinData` của document `exports`. Có thể lưu nguyên file trong một BSON document không?

**Đáp án:** Không. Giới hạn một BSON document là **16 MiB**, bao gồm overhead. Có thể dùng GridFS hoặc object storage; Base64 không giải quyết giới hạn.

### Bài 2. Chia chunks trong cùng document

Lập trình viên chia file 40 MiB thành 80 phần, rồi đặt mảng `chunks` chứa tất cả phần vào **một document**. Có né được giới hạn 16 MiB không?

**Đáp án:** Không. Tổng kích thước document vẫn vượt giới hạn. GridFS lưu **mỗi chunk ở một document riêng** và có file entry riêng.

### Bài 3. Hai collection của bucket

Bucket tên `archives` có những collection nào?

**Đáp án:** `archives.files` chứa file metadata và `archives.chunks` chứa chunk documents. Bucket mặc định `fs` dùng `fs.files` và `fs.chunks`.

### Bài 4. Field nào liên kết một chunk với file?

```javascript
{
  _id: ObjectId("..."),
  files_id: ObjectId("..."),
  n: 12,
  data: BinData(0, "...")
}
```

**Đáp án:** `files_id` trỏ đến `_id` của file entry trong `files`. `n` là thứ tự chunk, không phải file ID.

### Bài 5. Tính số chunk

Một file có kích thước 20 MiB, chunk size 255 KiB. Cần bao nhiêu data chunks?

**Đáp án:** `ceil(20 × 1024 / 255) = ceil(80,3137...) = 81` chunks. Chunk cuối không nhất thiết đủ 255 KiB.

### Bài 6. Duplicate filename

Trong `fs.files` có hai document với `filename: "receipt.pdf"` nhưng `_id` khác nhau. Đây có nhất thiết là lỗi dữ liệu không?

**Đáp án:** Không. GridFS cho phép nhiều file entries cùng filename. Ứng dụng phải định nghĩa version/revision và dùng file ID để truy xuất bản phù hợp.

### Bài 7. Chọn storage cho video

Nền tảng phát video 2 GiB cho hàng chục nghìn lượt xem, cần CDN và tua từng phần. GridFS hay object storage là ứng viên nên ưu tiên đánh giá?

**Đáp án:** **Object storage + CDN** thường phù hợp hơn cho media delivery quy mô lớn và ranged requests. MongoDB vẫn có thể lưu metadata, quyền và object key. GridFS lưu được bytes nhưng không tự có toàn bộ media-delivery features.

### Bài 8. Chọn storage cho hồ sơ nội bộ

Một dịch vụ lưu PDF 25 MiB, số lượt tải ít, cần metadata MongoDB và chỉ truy cập qua backend đã xác thực. GridFS có đáng thử không?

**Đáp án:** Có. File vượt giới hạn một BSON document; GridFS có stream và metadata cùng MongoDB. Tuy nhiên vẫn phải benchmark chi phí disk/backup/latency, so với object storage nếu đã có.

### Bài 9. Upload lỗi giữa chừng

Consumer crash sau khi upload 50 chunks nhưng trước khi file entry được ghi. Hệ thống có thể còn lại gì?

**Đáp án:** Có thể có **orphan chunks** không có file entry tương ứng. Phải có quy trình cleanup với grace period và nhận biết upload đang hoạt động, không xóa mọi chunk thiếu entry ngay lập tức.

### Bài 10. Thứ tự cập nhật business pointer

Muốn thay file hợp đồng A bằng file B. Nên cập nhật pointer sang B **trước** khi upload B thành công hay sau khi B đã upload/kiểm tra hoàn tất?

**Đáp án:** Thường **sau khi B hoàn tất và hợp lệ**. Sau đó cập nhật pointer theo điều kiện nghiệp vụ và xử lý file A theo version/retention. Không để record chính thức trỏ tới tệp chưa sẵn sàng.

### Bài 11. Checksum

Một file download có độ dài đúng bằng `files.length`. Có đủ kết luận bytes nguyên vẹn không?

**Đáp án:** Chưa đủ. Cần checksum mạnh như SHA-256 hoặc biện pháp xác minh nội dung tương đương. Hai file cùng length có thể khác bytes.

### Bài 12. Metadata và authorization

Endpoint nhận `fileId` từ URL. File ID tồn tại, nên server trả bytes luôn. Có vấn đề gì?

**Đáp án:** Có nguy cơ lộ file của người dùng/tenant khác. Phải xác thực và kiểm tra business ownership/ACL trước khi stream.

### Bài 13. Xóa bằng TTL

Nhóm vận hành tạo TTL index trên `fs.files.uploadDate` để sau 30 ngày file metadata tự biến mất. Đây có phải cách xóa cả file đúng chuẩn GridFS không?

**Đáp án:** Không. TTL trên file entry không tự gọi GridFS delete để xóa chunks. Có thể tạo orphan chunks. Cần lifecycle job dùng GridFS API và kiểm soát retention/permission.

### Bài 14. Tối ưu RAM upload

Code Java dùng `Files.readAllBytes()` cho tệp 1 GiB rồi truyền byte array vào một API. Hướng cải thiện?

**Đáp án:** Dùng `InputStream` và `GridFSBucket.uploadFromStream()`, áp giới hạn dung lượng, backpressure và timeout. Không giữ toàn bộ file trong RAM.

### Bài 15. Dự báo quy mô

Ứng dụng có 200.000 tệp, trung bình 150 chunks mỗi file. Có khoảng bao nhiêu chunk documents hoàn chỉnh?

**Đáp án:** `200.000 × 150 = 30.000.000` chunk documents. Đây chưa gồm file entries, indexes, replica copies, orphan data, backup và oplog.

### Bài 16. Phân biệt GridFS chunk và sharding chunk

GridFS chia file thành 500 chunks. Có thể kết luận bytes file đã được phân phối đều lên 500 shard không?

**Đáp án:** Không. GridFS chunk là **mảnh file**; sharding chunk/range là **đơn vị phân phối dữ liệu cluster**. Muốn nhiều shard tham gia cần thiết kế sharding riêng.

### Bài 17. File 10 KiB

Ứng dụng có một cấu hình JSON nhị phân 10 KiB được đọc cùng một document cấu hình duy nhất. Có cần dùng GridFS không?

**Đáp án:** Không bắt buộc. Nếu tổng BSON document dưới 16 MiB và pattern đọc/cập nhật phù hợp, nhúng binary hoặc lưu text/document trực tiếp có thể đơn giản hơn. Cân nhắc bảo mật và schema.

### Bài 18. File PDF có cùng tên

Một user upload `invoice.pdf` v1 rồi v2. API download bằng filename và luôn chọn “file mới nhất” nhưng nghiệp vụ cần tái hiện đúng hóa đơn đã ký của năm trước. Thiết kế sai ở đâu?

**Đáp án:** Filename không chỉ định phiên bản bất biến. Business record phải lưu **file ID/version** của bản đã ký; v2 là một file entry khác.

## 33. Checklist triển khai GridFS trong dự án

Trước khi quyết định, hãy kiểm tra:

1. **Bài toán có thật sự cần lưu bytes trong MongoDB?** So với BSON binary hoặc object storage.
2. **Kích thước file và số lượng file:** dự báo vượt 16 MiB, tổng chunks, dung lượng và throughput.
3. **Đường upload/download:** streaming, timeout, quota và concurrency.
4. **Phương thức truy xuất:** toàn file, HTTP Range, video, CDN hoặc backend nội bộ.
5. **Bucket naming:** `fs` hay bucket nghiệp vụ, thống nhất trong driver/tools.
6. **Metadata schema:** tenant, owner, content type, checksum, file version, retention.
7. **Business reference:** lưu file ID trong record nghiệp vụ; không dùng filename như khóa duy nhất.
8. **Index:** giữ indexes GridFS cần thiết, thêm index metadata theo query thực.
9. **Write concern và replication:** chọn mức độ bền phù hợp và tính vào latency.
10. **Tính nguyên tử:** không giả định upload nhiều chunks là một transaction.
11. **Retry/idempotency:** uploadRequestId, unique constraints và phát hiện duplicate.
12. **Cleanup:** orphan chunks, orphan files, upload thất bại và grace period.
13. **Versioning:** file immutable, upload version mới, cập nhật pointer an toàn.
14. **Checksum:** lưu SHA-256 và kiểm tra khi cần, tránh dữ liệu source thay đổi lúc upload.
15. **Security:** AuthN/AuthZ, tenant isolation, TLS, encryption, malware scanning.
16. **Retention:** dùng GridFS delete workflow, không xóa trực tiếp files metadata bằng TTL.
17. **Backup/restore:** cả `files` và `chunks` cùng business references, có restore test.
18. **Monitoring:** storage/index, upload failures, replication lag, p95/p99 OLTP.
19. **Scaling:** cân nhắc sharding GridFS theo version và workload, hoặc tách object storage.
20. **Benchmark:** đo cùng file corpus, concurrency và mục tiêu SLA; không chọn bằng cảm tính.

## 34. Tổng kết

**GridFS** giúp MongoDB lưu tệp lớn bằng cách chia bytes thành nhiều **chunk documents** trong `<bucket>.chunks` và lưu một **file metadata document** trong `<bucket>.files`. Nó khắc phục giới hạn **16 MiB trên mỗi BSON document** đối với toàn bộ file và cung cấp **upload/download theo stream** qua MongoDB drivers.

Nhưng việc một file **có thể lưu trong GridFS** không có nghĩa GridFS **là nơi phù hợp nhất để lưu file đó**. Với tệp nhỏ cần đi cùng một document, BSON binary có thể đơn giản hơn. Với video, ảnh/public downloads quy mô lớn, CDN, byte ranges và archive lâu dài, object storage + MongoDB metadata thường đáng ưu tiên đánh giá. Với tài liệu lớn truy cập qua backend, cần metadata/query tích hợp và lượng tải vừa phải, GridFS là ứng viên hợp lý.

Khi chọn GridFS, phải coi **file ID, chunks, metadata, business reference, checksum, version và retention** là một hệ thống có vòng đời. Upload/delete có thể thất bại giữa nhiều documents; write concern không thay thế idempotency hay cleanup. Bằng cách dự báo số chunks, benchmark I/O, dùng stream, giữ quyền truy cập chặt chẽ và thử restore đầy đủ, ứng dụng có thể tận dụng GridFS đúng phạm vi mà không biến MongoDB thành một file server quá tải.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Java Sync Driver — Store and Retrieve Files with GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Database Tools — mongofiles](https://www.mongodb.com/docs/database-tools/mongofiles/)
- [MongoDB Manual — BSON Document Size](https://www.mongodb.com/docs/manual/reference/limits/#bson-documents)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
