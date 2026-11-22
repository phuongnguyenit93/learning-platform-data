# Quyền truy cập, sao lưu và tính nhất quán giữa metadata với nội dung trong MongoDB GridFS

## 1. Bài toán: lưu file lớn không chỉ là lưu các byte

Giả sử một ứng dụng quản lý hồ sơ cho phép người dùng tải lên hợp đồng PDF, hình ảnh, video hoặc tệp dữ liệu. Ứng dụng muốn lưu file trong MongoDB bằng **GridFS** và cung cấp các chức năng:

- Người dùng chỉ tải được file mà họ có quyền xem.
- Một file thuộc tenant A không được xuất hiện trong kết quả của tenant B.
- File chưa upload xong hoặc chưa được kiểm tra bảo mật không được công bố.
- Một lần backup/restore phải giữ nguyên **nội dung file, metadata và các tham chiếu nghiệp vụ**.
- Sau lỗi mạng, lỗi ứng dụng, restore hoặc thao tác xóa, hệ thống phát hiện được **chunk còn sót**, **chunk bị thiếu** và **metadata trỏ sai nội dung**.
- Thao tác thay file hoặc thu hồi quyền không khiến người dùng khác đọc nhầm phiên bản.
- Có thể kiểm tra tính toàn vẹn bằng chiều dài, số chunks và checksum.

Ví dụ một tài liệu nghiệp vụ:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  filename: "contract-2026.pdf",
  gridFsFileId: ObjectId("65a000000000000000000001"),
  status: "READY",
  visibility: "PRIVATE"
}
~~~

Trường **gridFsFileId** không chứa dữ liệu nhị phân: nó là khóa liên kết tới một file GridFS. Nếu metadata này được restore nhưng dữ liệu GridFS không có, ứng dụng sẽ thấy một “file” trên giao diện nhưng không tải được nội dung.

Ngược lại, nếu những chunks của file đã được backup nhưng document mô tả file chưa có, hàng triệu byte vẫn chiếm dung lượng mà không có file hợp lệ được ứng dụng tìm thấy.

**Trọng tâm của bài** là ba vấn đề có liên quan chặt chẽ nhưng không giống nhau:

1. **Access control:** Ai được upload, đọc, đổi metadata và xóa file?
2. **Backup và restore:** Làm thế nào bảo toàn dữ liệu nhị phân, metadata và tham chiếu tại một trạng thái có thể phục hồi?
3. **Consistency:** Làm thế nào bảo đảm file được công bố là file có đầy đủ chunks, đúng nội dung và đúng business metadata?

### 1.1. Kết quả mong đợi

Sau bài này, bạn có thể:

- Giải thích vai trò của **fs.files** và **fs.chunks**, các collection theo bucket name.
- Phân biệt **MongoDB RBAC** ở cấp database/collection với **ủy quyền theo từng file** ở ứng dụng.
- Thiết kế quy trình upload, kiểm tra, publish, download, replace và delete an toàn.
- Hiểu vì sao file GridFS không có tính nguyên tử đa tài liệu như một MongoDB document đơn lẻ.
- Thiết kế **backup nhất quán theo thời điểm** và kịch bản restore có kiểm chứng.
- Phát hiện orphan chunks, missing chunks, chiều dài sai, duplicate sequence và mismatch checksum.
- Viết ví dụ **mongosh, MongoDB Java Sync Driver, Spring Data MongoDB**.
- Tạo runbook xử lý lỗi và kiểm tra định kỳ trước khi hệ thống phục vụ file production.

## 2. Cấu trúc GridFS: một file là nhiều documents

MongoDB có giới hạn kích thước một BSON document thông thường là **16 MiB**. GridFS chia nội dung file thành nhiều khối nhỏ để lưu trữ và đọc theo luồng thay vì đặt mọi byte vào một document.

Một **GridFS bucket** có hai collections:

| Collection | Chức năng |
|---|---|
| **fs.files** | Một document mô tả mỗi file đã upload thành công: tên, chiều dài, kích thước chunk, ngày upload và metadata. |
| **fs.chunks** | Những documents chứa dữ liệu nhị phân của file, mỗi document là một chunk. |

Prefix mặc định là **fs**. Nếu tạo bucket có tên **assets**, hai collections tương ứng là **assets.files** và **assets.chunks**.

~~~text
GridFS bucket "assets"

+----------------------------+
| assets.files               |
| _id: F-100                 |
| filename: contract.pdf     |
| length: 600000             |
| chunkSize: 261120          |
| metadata: {...}            |
+-------------+--------------+
              |
              | chunks.files_id = files._id
              v
+---------------------------------------------------+
| assets.chunks                                     |
| files_id=F-100, n=0, data=Binary(261120 bytes)    |
| files_id=F-100, n=1, data=Binary(261120 bytes)    |
| files_id=F-100, n=2, data=Binary(77760 bytes)     |
+---------------------------------------------------+

Nội dung file = chunk 0 + chunk 1 + chunk 2
                theo thứ tự n tăng dần.
~~~

### 2.1. Document trong assets.files

Ví dụ rút gọn:

~~~javascript
{
  _id: ObjectId("65a000000000000000000001"),
  length: NumberLong(600000),
  chunkSize: 261120,
  uploadDate: ISODate("2026-08-12T09:00:00Z"),
  filename: "contract-2026.pdf",
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    status: "SCANNING",
    mediaType: "application/pdf",
    applicationFileId: "DOC-100"
  }
}
~~~

Các field cốt lõi của GridFS:

| Field | Ý nghĩa |
|---|---|
| **_id** | ID của file GridFS, được chunks tham chiếu qua files_id. |
| **length** | Số byte của nội dung file. |
| **chunkSize** | Kích thước tối đa của mỗi chunk ngoại trừ chunk cuối. |
| **uploadDate** | Thời điểm upload được ghi nhận bởi GridFS. |
| **filename** | Tên file dùng để tra cứu/hiển thị theo nhu cầu. |
| **metadata** | Dữ liệu tùy chỉnh, ví dụ tenantId, ownerId, trạng thái, checksum hoặc loại tài liệu. |

GridFS có thể có các field bổ sung tùy driver và phiên bản. Không dùng một field **md5** cũ làm cơ chế bảo vệ nội dung hiện đại; thiết kế checksum riêng bằng **SHA-256** nếu cần xác thực tính toàn vẹn.

### 2.2. Document trong assets.chunks

~~~javascript
{
  _id: ObjectId("65a000000000000000000002"),
  files_id: ObjectId("65a000000000000000000001"),
  n: 0,
  data: BinData(0, "...")
}
~~~

| Field | Ý nghĩa |
|---|---|
| **_id** | ID của riêng chunk document. |
| **files_id** | Trỏ về _id của file trong assets.files. |
| **n** | Thứ tự chunk, bắt đầu từ 0 và tăng liên tục. |
| **data** | BSON binary data. |

**Thứ tự n** là thiết yếu. Ghép chunks theo thứ tự _id hoặc thứ tự kết quả truy vấn không phải cách khôi phục file đúng.

### 2.3. Chunk size và công thức kiểm tra

Kích thước mặc định thường là **255 KiB = 261.120 bytes**, có thể điều chỉnh khi upload.

Với:

~~~text
length = 600000 bytes
chunkSize = 261120 bytes
~~~

số chunks dự kiến:

~~~text
expectedChunks = ceil(length / chunkSize)
               = ceil(600000 / 261120)
               = 3
~~~

Kích thước:

~~~text
chunk 0: 261120 bytes
chunk 1: 261120 bytes
chunk 2:  77760 bytes
total:   600000 bytes
~~~

Khi file có **length=0**, số chunks dự kiến bằng 0; document trong files vẫn có thể mô tả một file rỗng hợp lệ. Các ứng dụng có thể chủ động từ chối file rỗng theo business policy, nhưng không nên kết luận mọi file rỗng đều corrupt.

### 2.4. Các index quan trọng

Theo GridFS specification, các index thông dụng:

~~~javascript
db.getCollection("assets.files").createIndex(
  { filename: 1, uploadDate: 1 }
);

db.getCollection("assets.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);
~~~

Index **{files_id:1,n:1} unique** giúp mỗi file không có hai chunks có cùng số thứ tự n. Tuy nhiên **unique index không đảm bảo đủ tất cả chunks**: n=0,2 vẫn có thể tồn tại mà n=1 bị thiếu.

Các drivers/buckets có thể tạo các GridFS indexes cần thiết khi khởi tạo/kiểm tra bucket. Trong production, nên **provision indexes trước** bằng tài khoản quản trị thích hợp để runtime account không cần quyền tạo index.

### 2.5. Hai collection không phải một document

MongoDB bảo đảm nguyên tử cho **một document write**. Một GridFS file có thể trải qua hàng chục, hàng nghìn hoặc hàng triệu documents, nên không thể suy rằng upload hoặc delete toàn bộ file là một write nguyên tử chỉ vì đang dùng MongoDB.

Điều này ảnh hưởng trực tiếp đến **quyền đọc, backup/restore và khôi phục sau lỗi**.

## 3. Ba tầng nhất quán cần phân biệt

Trong một hệ thống thực tế, thông tin của file thường xuất hiện ở ba tầng:

~~~text
             Business application
         +-------------------------+
         | asset_catalog           |
         | assetId, tenant, owner  |
         | status, gridFsFileId    |
         +-----------+-------------+
                     |
                     v
               GridFS metadata
         +-------------------------+
         | assets.files            |
         | _id, length, filename   |
         | uploadDate, metadata    |
         +-----------+-------------+
                     |
                     v
               GridFS content
         +-------------------------+
         | assets.chunks           |
         | files_id, n, data       |
         +-------------------------+
~~~

### 3.1. Tính nhất quán giữa files và chunks

Một file chỉ có thể đọc đầy đủ khi:

- Document **assets.files** hợp lệ.
- Có đúng số chunks dự kiến.
- Chunks có sequence n **0..N-1** không thiếu, không trùng.
- Tổng số byte của chunks bằng **length**.
- Nội dung thực tế đúng checksum được lưu/trusted nếu có.

Chỉ có **assets.files** chưa chứng minh nội dung file đủ byte.

### 3.2. Tính nhất quán giữa GridFS và business catalog

Một business record có thể tham chiếu file:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  gridFsFileId: ObjectId("65a000000000000000000001"),
  status: "READY"
}
~~~

Các bất biến mong muốn:

1. Record **READY** phải trỏ tới một GridFS file tồn tại và có thể đọc.
2. GridFS metadata về **tenantId** phải tương ứng tenant của business record.
3. Chỉ một phiên bản file hiện hành được công bố cho một asset ID tại một thời điểm theo business rule.
4. Quyền đọc business record phải được kiểm tra trước khi gọi GridFS download.
5. Không xóa chunks của file còn được business record đang sử dụng.

### 3.3. Tính nhất quán giữa backup và trạng thái ứng dụng

Nếu restore **asset_catalog** về thời điểm T2 nhưng GridFS về T1:

~~~text
T1: GridFS có file F1
T2: asset_catalog đã trỏ sang file F2

Restore:
  asset_catalog tại T2 -> trỏ F2
  GridFS tại T1        -> không có F2
~~~

Kết quả là metadata nghiệp vụ hợp lệ về cú pháp nhưng **nội dung không còn**.

Đây là lý do backup phải xét **cùng một trạng thái nhất quán của tất cả collections liên quan**, không chỉ sao chép file binary.

## 4. Vòng đời upload, download và delete: giới hạn tính nguyên tử

### 4.1. Upload thường có nhiều thao tác ghi

Về nguyên tắc, GridFS driver ghi dữ liệu nhị phân thành các documents trong **assets.chunks**, rồi ghi document mô tả vào **assets.files** khi upload hoàn tất.

~~~text
Upload contract.pdf
       |
       v
Write chunk n=0
       |
       v
Write chunk n=1
       |
       v
Write chunk n=2
       |
       v
Create assets.files document
       |
       v
GridFS upload successful
~~~

Từ góc nhìn API:

- Khi driver báo upload thành công, ứng dụng có thể sử dụng file ID được trả về để truy cập file.
- Trước khi document trong **assets.files** được ghi, các chunks đã được ghi có thể tồn tại nhưng chưa có file hoàn chỉnh được liệt kê.
- Nếu upload lỗi giữa chừng, có thể xuất hiện chunks chưa được gắn với file document.
- Nếu mạng mất ngay sau khi server nhận một thao tác ghi, kết quả mà client quan sát có thể không rõ; không được mặc định server đã rollback mọi dữ liệu.

### 4.2. Không dựa vào transaction nhiều documents cho toàn bộ GridFS upload

**GridFS không hỗ trợ multi-document transactions** theo cách biến một file upload thành một commit nguyên tử của tất cả **files** và **chunks**. Không viết:

~~~text
startTransaction()
  write all chunks
  write file document
commitTransaction()

=> chắc chắn mọi thứ được GridFS bảo vệ như một write nguyên tử
~~~

Đây **không phải** bảo đảm GridFS cung cấp.

Nếu nghiệp vụ cần atomicity khi *công bố* file, hãy tách:

1. Upload toàn bộ bytes vào GridFS.
2. Kiểm tra nội dung và metadata cần thiết.
3. Cập nhật **một document nghiệp vụ** hoặc trạng thái công bố bằng một atomic update.
4. Chỉ cho download file đã ở trạng thái **READY**.

Việc công bố có thể thực hiện bằng **một document update nguyên tử**, dù bước ghi bytes trước đó trải qua nhiều documents.

### 4.3. Tình huống upload dở dang

~~~text
T0: Bắt đầu upload F100
T1: Ghi chunk 0
T2: Ghi chunk 1
T3: Network disconnect trước khi ghi chunk 2
T4: Không có assets.files document cho F100

Kết quả:
  Có chunks files_id=F100
  Không có files._id=F100
~~~

Các chunks đó là **orphan candidates**, nhưng không nên xóa chúng ngay khi nhìn thấy. Trong khi một upload khác đang chạy bình thường, các chunks chưa có files record cũng có thể tồn tại tạm thời. Cần **upload lease, grace period hoặc workflow reconciliation** để phân biệt.

### 4.4. File document không phải bằng chứng checksum

Nếu **assets.files.length = 600000**, metadata này mô tả chiều dài kỳ vọng, không tự chứng minh rằng tất cả binary data đang có là đúng phiên bản mong muốn.

Hai files có cùng length vẫn có thể có nội dung khác nhau. Để xác minh toàn vẹn, có thể so **SHA-256 của bytes sau khi tải lại** với digest được tạo từ nguồn tin cậy.

### 4.5. Xóa file cũng có nhiều thao tác

GridFS delete cần loại bỏ cả **file document** và các **chunk documents** liên quan. Vì đó là nhiều documents, không nên coi delete là một phép xóa atomically tất cả bytes và metadata trong một bước.

Nếu process bị dừng giữa chừng, có thể phát sinh:

- File document đã mất, chunks vẫn còn.
- Một số chunks đã mất trong khi thao tác delete chưa hoàn tất.
- Business catalog còn trỏ file nhưng GridFS nội dung đã bị xóa.

Không sửa dữ liệu GridFS bằng cách xóa chỉ **assets.files** hoặc chỉ **assets.chunks** nếu mong muốn một lifecycle nhất quán.

### 4.6. Download có thể gặp race với delete

~~~text
Reader: kiểm tra file F100 là READY
                      |
                      v
Cleaner: bắt đầu xóa F100
                      |
                      v
Reader: tải chunk n=2 -> không còn
~~~

Kiểm tra quyền trước khi download là cần thiết nhưng **không tự khóa toàn bộ bytes** chống lại thao tác xóa đồng thời.

Với file quan trọng hoặc download dài, dùng **lifecycle state, reference counting/lease hoặc grace period trước khi xóa bytes**; đồng thời chuẩn bị xử lý lỗi stream nếu file bị thay đổi trong lúc đọc.

### 4.7. Một phiên bản mới nên có file ID mới

Khi người dùng thay hợp đồng:

~~~text
Old file F100 (READY)
       |
       v
Upload new file F101
       |
       v
Validate F101
       |
       v
Atomic update asset_catalog.currentFileId = F101
       |
       v
Schedule delete F100 after grace period
~~~

Không nên ghi đè trực tiếp bytes của những chunks thuộc F100. Tạo file ID mới giúp quá trình thay file có thể rollback/publish rõ ràng, giảm nguy cơ reader nhận nội dung bị pha trộn.

## 5. Các lớp quyền truy cập

Một ứng dụng GridFS có thể có nhiều lớp bảo vệ:

~~~text
HTTP / API caller
      |
      v
Authentication
      |
      v
Application authorization
 (tenant, owner, role, sharing policy)
      |
      v
MongoDB service account
      |
      v
MongoDB RBAC
 (database, collection, actions)
      |
      v
GridFS files/chunks
~~~

**Không được bỏ qua application authorization** chỉ vì MongoDB đã bật username/password.

### 5.1. MongoDB RBAC thường ở mức collection, không phải từng file

MongoDB RBAC có thể cấp quyền:

- **find** trong **assets.files** và **assets.chunks**.
- **insert** để ghi documents mới.
- **update** để thay metadata được phép.
- **remove** để xóa documents.
- **createIndex**, **listIndexes** cho setup/kiểm tra indexes.

Nhưng hai file thuộc cùng assets.files/assets.chunks vẫn nằm trong **cùng phạm vi quyền collection**. Một user DB có quyền đọc hai collections đó có khả năng truy vấn dữ liệu của nhiều file, không chỉ file mà app định cho họ xem.

Vì vậy không nên cấp **MongoDB credentials trực tiếp cho từng end user** và mong GridFS tự thực thi ACL ở mức file.

### 5.2. Các vai trò ứng dụng thường cần

| Vai trò | Có thể làm gì | Điều cần giới hạn |
|---|---|---|
| **Uploader** | Tải file mới lên thuộc tenant của mình. | File size/type, quota, ownerId, idempotency. |
| **Reader** | Tải file đã được công bố và được chia sẻ. | tenant, owner, trạng thái READY, hạn truy cập. |
| **Editor** | Thay metadata nghiệp vụ hoặc gửi phiên bản mới. | Chỉ fields cho phép, optimistic concurrency. |
| **Deleter** | Yêu cầu xóa/thu hồi file. | Phải kiểm tra quyền, retention/legal hold. |
| **Security scanner** | Đọc bytes ở vùng chưa công bố, đánh dấu kết quả scan. | Không tự thay owner/tenant. |
| **Backup operator** | Sao lưu/khôi phục collections cần thiết. | Quyền nâng cao và thủ tục kiểm soát. |

Không phải mọi vai trò ứng dụng đều cần một MongoDB DB user riêng; có thể xây application service account với quyền tối thiểu và xác thực từng request ở service layer.

### 5.3. Có ba khái niệm khác nhau

- **Authentication:** ai đang gọi API?
- **Authorization:** người đó có được xem/chỉnh file này không?
- **Integrity:** file đọc được có phải bytes đã upload và xác minh không?

Thành công ở một khâu không tự chứng minh hai khâu còn lại.

### 5.4. File ID không phải quyền truy cập

Một endpoint nguy hiểm:

~~~text
GET /files/65a000000000000000000001

Server:
  bucket.downloadToStream(fileId, response)
~~~

Nếu không kiểm tra tenant, owner hoặc sharing policy, người dùng chỉ cần biết/đoán file ID để đọc tài liệu không thuộc quyền mình. ObjectId khó đoán **không phải** cơ chế kiểm soát truy cập.

Một API đúng cần kiểm tra quyền trước:

~~~text
GET /assets/DOC-100/download
   |
   v
Authenticate caller
   |
   v
Find business asset by assetId + tenant policy
   |
   v
Assert READY and access granted
   |
   v
Lookup GridFS file ID from verified asset
   |
   v
Stream bytes with controlled response headers
~~~

### 5.5. Xác thực qua business record thay vì filename

Tên file có thể trùng nhau:

~~~text
tenant-a/contract.pdf
tenant-b/contract.pdf
tenant-a/contract.pdf (version 2)
~~~

Không sử dụng **filename** như khóa quyền duy nhất. Dùng một **business asset ID** có scoping theo tenant và một **GridFS file ID** chính xác cho phiên bản nội dung.

### 5.6. Bảo vệ quyền khi nhiều người chia sẻ

Một file có thể có:

~~~javascript
{
  ownerId: "user-21",
  visibility: "TEAM",
  allowedUserIds: ["user-21", "user-35"],
  tenantId: "tenant-a"
}
~~~

Đừng cho client tự chọn **allowedUserIds** của một file đang bị người khác sở hữu. Kiểm tra người gọi có quyền đổi sharing policy và ghi audit events cho việc cấp/thu hồi quyền.

## 6. MongoDB RBAC cho hai collections của GridFS bucket

### 6.1. Bucket và namespace thực tế

Ví dụ sử dụng:

~~~text
Database:  gridfs_security_lab
Bucket:    assets

Collections:
  gridfs_security_lab.assets.files
  gridfs_security_lab.assets.chunks
~~~

Trong mongosh:

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").getIndexes();
db.getCollection("assets.chunks").getIndexes();
~~~

Không nhầm cú pháp **db.assets.files** là một collection lồng nhau của JavaScript; cách rõ ràng khi tên chứa dấu chấm là **db.getCollection("assets.files")**.

### 6.2. Custom role đọc GridFS

Một ví dụ role cho service chỉ được đọc file:

~~~javascript
use gridfs_security_lab

db.createRole({
  role: "gridfsAssetReader",
  privileges: [
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.files"
      },
      actions: ["find"]
    },
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.chunks"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
~~~

Role trên mô tả **quyền đọc dữ liệu**, không nhất thiết đáp ứng mọi thao tác khởi tạo/check index của mọi driver. Nếu driver cần kiểm tra index khi bucket mới hoặc collection chưa tồn tại, hãy **chuẩn bị collections/indexes trước** bằng provisioning account thay vì cấp bừa createIndex cho reader. Kiểm tra hành vi driver/version cụ thể.

### 6.3. Upload cần quyền ghi đúng collections

Một service upload có thể cần:

- **insert** vào assets.chunks.
- **insert** vào assets.files sau khi upload hoàn tất.
- **find** cần thiết cho tra cứu/kiểm tra.
- **update** đối với assets.files nếu cập nhật custom metadata/status.
- **remove** khi cần dọn dẹp upload lỗi hoặc xóa file; chỉ cấp nếu workflow thực sự yêu cầu.

Ví dụ role cho một service upload có khả năng dọn file theo workflow được phép:

~~~javascript
db.createRole({
  role: "gridfsAssetWriter",
  privileges: [
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.files"
      },
      actions: ["find", "insert", "update", "remove"]
    },
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.chunks"
      },
      actions: ["find", "insert", "remove"]
    }
  ],
  roles: []
});
~~~

**Tên action xóa trong MongoDB privilege là remove**, không phải một action tùy ý tên delete. Hãy giới hạn user nào được cấp role writer này: nó có thể xóa bất kỳ file nào trong bucket nếu truy cập MongoDB trực tiếp.

### 6.4. Tách quyền provisioning index khỏi runtime

Provisioning account có thể cần:

~~~text
createCollection, createIndex, listIndexes
~~~

và quyền tương ứng trên namespace/DB theo cơ chế MongoDB. Ứng dụng chỉ upload/download nên không tự có quyền tạo/xóa index mỗi khi khởi động.

Một quy trình tốt:

1. DBA/deployment migration tạo hai collections và indexes cần thiết.
2. Kiểm tra unique index trên **assets.chunks(files_id,n)**.
3. Kiểm tra indexes phục vụ metadata/tenant queries.
4. Sau đó chạy service với credentials có quyền dữ liệu tối thiểu.

### 6.5. Không cấp quyền đọc trực tiếp khi cần ACL theo file

Nếu tenant A và tenant B đều lưu dữ liệu trong **assets.files/chunks** của một bucket, một role MongoDB có find trên hai collections **không tự giới hạn mỗi user ở một tenant**.

Hai kiến trúc:

| Kiến trúc | Cách bảo vệ | Đánh đổi |
|---|---|---|
| **Bucket dùng chung** | MongoDB app service credential + API authorization tenant/owner. | Đơn giản schema, nhưng backend phải lọc quyền tuyệt đối. |
| **Bucket/database tách riêng theo tenant** | RBAC theo collection hoặc database. | Cách ly mạnh hơn ở namespace, nhưng số collections/indexes và quản trị tăng. |

Nếu cho bên thứ ba kết nối thẳng MongoDB, thường cần **tách namespace** hoặc một cơ chế thực sự áp giới hạn dữ liệu ở DB. Không kỳ vọng mỗi document chứa metadata.tenantId sẽ tự được MongoDB RBAC lọc.

### 6.6. Quyền của backup/restore không giống quyền upload

Một tài khoản chạy **mongodump/mongorestore** cần các quyền sao lưu/khôi phục theo MongoDB Database Tools và deployment topology. Không tái sử dụng service account chỉ có find/insert vào GridFS, cũng không cấp quyền restore vào production cho API server.

Phân biệt:

- **Application runtime credential:** ít quyền.
- **Migration/provisioning credential:** quản lý indexes.
- **Backup credential:** đọc toàn bộ namespaces cần sao lưu.
- **Restore credential:** chỉ được dùng trong quy trình vận hành có kiểm soát.

### 6.7. Audit việc thay quyền

Việc cập nhật owner, visibility, allowed user list, retention hoặc legal hold có thể ảnh hưởng bảo mật nhiều hơn thao tác đổi filename.

Ứng dụng nên ghi:

~~~text
who
when
tenantId
assetId
action (GRANT/REVOKE/DELETE/REPLACE)
oldPolicyVersion
newPolicyVersion
requestId
~~~

Không để audit record chỉ tồn tại trong log ngắn hạn nếu đây là yêu cầu tuân thủ bắt buộc. Cần xác định retention, encryption và quyền truy cập audit data riêng.

## 7. Metadata nào thuộc GridFS, metadata nào thuộc nghiệp vụ?

GridFS cho phép lưu custom fields trong **assets.files.metadata**:

~~~javascript
{
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    mediaType: "application/pdf",
    status: "SCANNING",
    sha256: "...",
    applicationFileId: "DOC-100"
  }
}
~~~

Nhưng một ứng dụng có thể cần thêm **asset_catalog**:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  currentFileId: ObjectId("65a000000000000000000001"),
  status: "READY",
  displayName: "Hợp đồng thuê nhà",
  visibility: "PRIVATE",
  policyVersion: NumberLong(5),
  version: NumberLong(3),
  createdAt: ISODate("2026-08-12T09:00:00Z"),
  updatedAt: ISODate("2026-08-12T09:05:00Z")
}
~~~

### 7.1. Phân chia trách nhiệm gợi ý

| Nơi lưu | Thông tin phù hợp |
|---|---|
| **assets.files** | _id, filename, length, chunkSize, uploadDate, metadata để nhận diện và kiểm chứng file. |
| **assets.chunks** | Binary chunks; không nhúng business ACL vào từng chunk. |
| **asset_catalog** | Trạng thái publish, currentFileId, owner, ACL, version, retention, audit linkage. |
| **Upload job/lease** | requestId, trạng thái tác vụ, bắt đầu/kết thúc, lỗi, thời hạn dọn dẹp. |

**Không nên giữ nhiều bản sao của cùng một quyền truy cập mà không xác định nguồn sự thật.** Nếu asset_catalog và assets.files cùng có ownerId, phải quy định field nào là authoritative và cách reconciliation khi chúng khác nhau.

### 7.2. metadata trong GridFS không tự bảo đảm tính toàn vẹn

Ví dụ:

~~~javascript
{
  metadata: {
    sha256: "abc...",
    mediaType: "application/pdf"
  }
}
~~~

Chỉ là các field dữ liệu. Người có quyền cập nhật assets.files.metadata có thể sửa chúng; không phải chữ ký mật mã.

Nếu cần chống sửa đổi có chủ đích:

- Hạn chế quyền update metadata.
- Lưu digest trong hệ thống tin cậy, có thể dùng chữ ký số/HMAC phù hợp.
- Dùng immutable versioning hoặc append-only audit cho các thay đổi quan trọng.
- Kiểm tra checksum bằng bytes đã đọc, không chỉ so metadata với chính nó.

### 7.3. filename không phải filesystem path

Một GridFS filename có thể là:

~~~text
../../private/secret.pdf
~~~

Trong GridFS, đây là một tên string; nó không có nghĩa được phép ghi một file lên filesystem với path đó.

Khi download/backup ra local filesystem:

1. Không nối filename user gửi thẳng vào đường dẫn ghi file.
2. Sử dụng tên server-generated hoặc sanitize/normalize.
3. Ngăn path traversal, reserved names và collisions.
4. Giữ original filename ở metadata để hiển thị khi cần.

### 7.4. MIME type và mediaType

Một user có thể upload mã thực thi với header:

~~~text
Content-Type: application/pdf
~~~

Metadata chứa mediaType="application/pdf" không chứng minh bytes đúng định dạng PDF. Nếu ứng dụng có chính sách file types, hãy:

- Kiểm tra magic bytes và parser phù hợp.
- Quét malware khi cần.
- Giới hạn file size và compression bombs.
- Không preview dữ liệu không tin cậy dưới origin có quyền cao.
- Mặc định **Content-Disposition: attachment** khi không muốn browser render.

### 7.5. Định nghĩa trạng thái READY rõ ràng

Không coi:

~~~text
assets.files document exists
~~~

là điều kiện duy nhất để công bố file. READY có thể yêu cầu:

~~~text
GridFS upload completed
AND asset linked to verified tenant
AND size limit satisfied
AND checksum verified
AND content scan passed
AND business policy permits publish
~~~

Mỗi điều kiện phải có nguồn dữ liệu và trạng thái failure/retry rõ ràng.

## 8. State machine cho upload và công bố file

Một workflow có thể dùng:

~~~text
NEW
  |
  v
UPLOADING
  |       \
  |        +--> FAILED / CANCELLED
  v
SCANNING
  |       \
  |        +--> REJECTED
  v
READY
  |
  +--> REPLACING --> READY(newFileId)
  |
  +--> DELETE_REQUESTED
          |
          v
       DELETING
          |
          v
       DELETED
~~~

Các tên trạng thái do ứng dụng định nghĩa, không phải các giá trị bắt buộc của GridFS API.

### 8.1. Bắt đầu upload

Ứng dụng tạo catalog record:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  uploadRequestId: "REQ-100",
  status: "UPLOADING",
  currentFileId: null,
  createdAt: ISODate("2026-08-12T09:00:00Z")
}
~~~

Nên đặt unique index phù hợp cho **tenantId + uploadRequestId** nếu API có idempotency key.

### 8.2. Ghi bytes với GridFS

Ghi file qua driver, đặt metadata:

~~~javascript
{
  tenantId: "tenant-a",
  applicationFileId: "DOC-100",
  status: "SCANNING",
  uploadRequestId: "REQ-100"
}
~~~

Chỉ sau khi **upload stream đóng thành công** mới coi file GridFS đã hoàn thành theo API driver. Nếu lỗi ở giữa, không ghi catalog READY.

### 8.3. Xác minh trước công bố

Sau upload thành công:

1. Nhận fileId, length, metadata.
2. Kiểm tra file size và checksum.
3. Nếu cần, đọc bytes để chạy antivirus/MIME checks.
4. Kiểm tra owner/tenant từ context đã xác thực.
5. Cập nhật catalog **SCANNING** hoặc **READY** theo điều kiện nghiệp vụ.

Không đặt status READY trong upload options ngay từ đầu khi file còn chờ scan hoặc approval.

### 8.4. Atomic publish bằng một update có điều kiện

~~~javascript
db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "SCANNING",
    uploadRequestId: "REQ-100"
  },
  {
    $set: {
      currentFileId: ObjectId("65a000000000000000000001"),
      status: "READY",
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
~~~

Điều kiện trong filter giúp tránh một worker upload cũ publish nhầm file khi catalog đã chuyển sang request/phiên bản khác. Kiểm tra **matchedCount/modifiedCount** để biết update có thành công theo kỳ vọng hay không.

Lệnh **updateOne trên một catalog document là nguyên tử ở mức document**, nhưng không biến cả quá trình upload GridFS và validation thành một transaction nguyên tử.

### 8.5. Không dùng hai nguồn READY mâu thuẫn

Nếu:

~~~text
asset_catalog.status = READY
assets.files.metadata.status = SCANNING
~~~

thì service cần biết trạng thái nào là nguồn quyết định. Một phương án:

- **asset_catalog.status** là trạng thái công bố authoritative.
- **assets.files.metadata.status** chỉ là thông tin hỗ trợ scanner/repair.
- Download luôn kiểm tra catalog và liên kết tới GridFS file ID tương ứng.

Nếu chọn chỉ dùng assets.files.metadata.status làm READY, phải thiết kế tương tự cho security, validation và update có điều kiện. Không trộn hai quy tắc giữa các endpoints.

### 8.6. Lỗi sau upload nhưng trước publish

~~~text
GridFS upload F100 success
  |
  X app crash before catalog READY
~~~

Khi khởi động lại, file F100 có thể tồn tại nhưng catalog vẫn **UPLOADING/SCANNING**. Recovery worker cần tìm theo **uploadRequestId/applicationFileId**, xác minh toàn vẹn và quyết định publish/cleanup dựa trên trạng thái, không tự tải lại và tạo file trùng một cách mù quáng.

## 9. Quy trình upload an toàn và xử lý lỗi

### 9.1. Các bước của một upload endpoint

~~~text
POST /assets
     |
     v
Authenticate and authorize uploader
     |
     v
Validate tenant, quota, length, type, requestId
     |
     v
Create catalog status=UPLOADING
     |
     v
Stream request bytes into GridFS
     |
     v
Close upload successfully -> get GridFS file ID
     |
     v
Verify content: size / SHA-256 / malware scan
     |
     v
Conditionally publish catalog status=READY
     |
     v
Return business assetId and version
~~~

Nếu upload thất bại ở bất kỳ bước nào, ứng dụng phải ghi trạng thái lỗi và để worker **quyết định cleanup/retry** theo đủ điều kiện. Không gửi response thành công khi chỉ mới tạo catalog record.

### 9.2. Giới hạn kích thước ngay khi đọc stream

Giả sử user gửi:

~~~http
Content-Length: 100000
~~~

Header này có thể thiếu hoặc không phản ánh đúng bytes thực nhận. API nên **đếm bytes của chính input stream** và dừng khi vượt giới hạn; không chỉ tin Content-Length.

Chẳng hạn:

~~~text
maximumAllowedBytes = 50 MiB
count bytes while reading
if readBytes > maximumAllowedBytes:
    cancel/abort upload
    mark failed
    schedule safe cleanup
~~~

GridFS giúp xử lý file vượt giới hạn BSON document, **không đồng nghĩa nên cho upload file không giới hạn**.

### 9.3. SHA-256 ở nguồn và nơi lưu

Một phép kiểm tra integrity:

~~~text
SHA256(input bytes) = H1
    |
    v
GridFS stores bytes
    |
    v
SHA256(downloaded stored bytes) = H2

H1 == H2 -> dữ liệu lưu trữ khớp nguồn theo SHA-256
~~~

Cần phân biệt:

- **H1** do backend tính từ input stream mà backend tin cậy.
- **H2** được tính từ bytes đọc lại trong GridFS.
- Nếu chỉ chép SHA-256 do client cung cấp vào metadata, đó là một **claim từ client**, không nhất thiết là kết quả backend xác minh.

Digest có thể được lưu ở asset_catalog hoặc metadata, nhưng nên biết **nguồn sự thật** của digest và ai có quyền cập nhật.

### 9.4. Kiểm tra media type

File có tên **report.pdf** không bảo đảm bytes là PDF. Một bước validation có thể:

1. Kiểm tra extension theo allowlist.
2. Kiểm tra content sniff/magic bytes.
3. Parse hoặc scan bằng công cụ đã được kiểm soát.
4. Dùng virus scanning/antimalware theo yêu cầu sản phẩm.
5. Đặt file vào trạng thái **REJECTED** nếu không đạt.

Không thực thi macro, script hoặc embedded code từ một file không tin cậy chỉ vì ứng dụng đang quét nội dung.

### 9.5. Idempotency khi client retry HTTP

Giả sử lần đầu:

~~~text
REQ-100 -> upload F100 thành công
         -> mất HTTP response
~~~

Client gửi lại cùng request:

~~~text
REQ-100 -> retry
~~~

Nếu backend luôn tạo F101 mới, có thể có hai files cho cùng ý định nghiệp vụ. Một **unique request key** trên asset_catalog giúp:

- Xác định request đã bắt đầu.
- Nếu READY, trả kết quả đã xác nhận.
- Nếu đang UPLOADING/SCANNING, trả trạng thái chờ hoặc tiếp tục workflow an toàn.
- Nếu FAILED, xử lý theo retry policy có version/lease.

Không tự coi một HTTP request lặp là một file hoàn toàn mới khi caller đã cung cấp idempotency key.

### 9.6. Retry GridFS upload không phải mặc định resume từ chunk cuối

Nếu upload bị ngắt ở chunk 7, không nên giả định gọi lại uploadFromStream là sẽ tự tiếp tục từ chunk 8. Trừ khi ứng dụng triển khai rõ một protocol resumable và driver/API hỗ trợ, **GridFS upload từ đầu có thể tạo một phiên bản file mới**.

Hãy phân biệt:

- **HTTP client retry**.
- **Driver retryable writes** của những thao tác đủ điều kiện.
- **Application-level resumable upload protocol**.

Ba cơ chế này có phạm vi và semantics khác nhau.

### 9.7. Timeout khi file đã ghi xong nhưng client chưa nhận ID

Một tình huống:

~~~text
Driver gửi thao tác hoàn tất upload
Server đã ghi assets.files
Network mất response
Caller thấy exception/timeout
~~~

Không khẳng định file chưa tồn tại chỉ vì client thấy lỗi. Nếu workflow đã có **fileId định trước, uploadRequestId hoặc applicationFileId**, recovery có thể truy vấn lại để xác định trạng thái.

Khi đối soát, không cho phép client tự thay tenantId hoặc ownerId để chiếm một file chưa công bố.

### 9.8. Không giữ toàn bộ file trong RAM

GridFS có lợi thế stream chunks. Tránh:

~~~text
read entire 2 GB file into byte[]
bucket.uploadFromStream(new ByteArrayInputStream(...))
~~~

Phương án này có thể làm Java process hết heap. Với input stream thực, cần kiểm soát buffering, rate, cancellation và tính checksum theo luồng.

## 10. Download đúng quyền, đúng file và đúng phiên bản

### 10.1. Kiểm tra business ACL trước khi lấy bytes

Một pattern mongosh minh họa:

~~~javascript
use gridfs_security_lab

const asset = db.asset_catalog.findOne({
  _id: "DOC-100",
  tenantId: "tenant-a",
  status: "READY"
});

if (!asset) {
  throw new Error("Asset not found or not available");
}

const file = db.getCollection("assets.files").findOne({
  _id: asset.currentFileId,
  "metadata.tenantId": asset.tenantId,
  "metadata.applicationFileId": asset._id
});

if (!file) {
  throw new Error("GridFS file metadata mismatch");
}
~~~

Đây **chỉ là bước đọc metadata trong mongosh**, chưa tải binary data. Trong ứng dụng thật, tenantId phải lấy từ **authenticated context**, còn quyền owner/sharing policy phải được kiểm tra đầy đủ.

### 10.2. Dùng business asset ID thay vì GridFS ID ở API public

Nên thiết kế:

~~~http
GET /assets/DOC-100/content
~~~

thay vì phơi lộ endpoint có thể download mọi GridFS file ID mà không cần lookup quyền. Bản thân việc sử dụng business ID không phải biện pháp bảo mật; nó chỉ tạo điểm chặn thuận tiện để backend kiểm tra quyền.

### 10.3. Tránh lỗi IDOR

**Insecure Direct Object Reference (IDOR)** xảy ra khi client đổi object ID trong request và truy cập tài nguyên của người khác.

Tình huống:

~~~text
User A có quyền DOC-100.
User B có quyền DOC-101.

User A thử GET /assets/DOC-101/content.
~~~

Nếu service chỉ tìm theo _id mà không kiểm tra tenant/owner/sharing, User A có thể tải file B.

Kiểm tra phải dựa trên **user đã xác thực và resource policy**, không dựa vào path đoán được hay mã hóa ID đơn giản.

### 10.4. Không trả dữ liệu metadata nhạy cảm không cần thiết

Một file document có thể chứa:

~~~javascript
{
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    securityLabel: "CONFIDENTIAL",
    internalWorkflowId: "WF-742",
    sha256: "..."
  }
}
~~~

API tải file thường chỉ cần trả:

~~~text
Content-Type
Content-Length
Content-Disposition
ETag/version nếu có
binary stream
~~~

Không gửi thẳng toàn bộ assets.files.metadata như JSON public nếu có internal IDs hoặc security labels.

### 10.5. Headers và an toàn trình duyệt

Các headers có thể cân nhắc:

~~~http
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
~~~

Đây chỉ là ví dụ. Cache-Control phải theo độ nhạy cảm và nhu cầu tải lại; Content-Disposition phải được tạo bằng thư viện/escaping an toàn để tránh header injection.

Nếu cho preview tài liệu không tin cậy, cân nhắc isolated origin/CSP và công cụ xử lý content theo chính sách an toàn.

### 10.6. Hỗ trợ Range requests

Một file video/PDF lớn có thể cần:

~~~http
Range: bytes=100000-199999
~~~

GridFS có khả năng đọc theo chunks và các APIs hỗ trợ seek/read tùy driver. Tuy nhiên **HTTP Range không tự được bật chỉ vì dữ liệu lưu trong GridFS**.

Backend cần:

- Parse và validate byte ranges.
- Dùng API đọc/seek phù hợp.
- Trả Content-Range và status 206/416 chính xác.
- Xác thực quyền trước khi phục vụ từng request.
- Kiểm soát việc nhiều concurrent range requests làm tăng database I/O.

### 10.7. Quyền đã bị thu hồi trong lúc tải

Nếu một file dài vài GB đang được stream thì admin thu hồi quyền:

~~~text
T1: API xác thực READY và quyền đọc
T2: Bắt đầu stream
T3: Admin revoke permission
T4: Stream có thể vẫn đang được gửi
~~~

Một lần kiểm tra quyền ở đầu request không bảo đảm cắt ngay stream đã bắt đầu. Chính sách bảo mật cần xác định liệu quyền thu hồi có hiệu lực:

- **Cho các request mới**; hoặc
- **Ngay lập tức cả những stream đang mở**, cần cơ chế cancellation/lease/revocation nâng cao.

Không tự hứa “revoke tức thì” nếu hệ thống không chủ động dừng active streams.

## 11. Thay phiên bản, xóa và retention

### 11.1. Không sửa chunks tại chỗ để thay file

Một cách thay file an toàn hơn:

~~~text
Asset DOC-100
  currentFileId = F100
         |
         v
Upload F101, verify, scan
         |
         v
Atomic compare-and-swap:
  currentFileId F100 -> F101
  version 3 -> 4
         |
         v
New requests read F101
Old F100 retained during grace/reader lease
         |
         v
Asynchronous cleanup of F100
~~~

Không vừa update metadata.length vừa ghi đè các chunks của F100 để “biến” nó thành file F101.

### 11.2. Optimistic concurrency ở catalog

~~~javascript
const expectedVersion = NumberLong(3);

const result = db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "READY",
    version: expectedVersion
  },
  {
    $set: {
      currentFileId: ObjectId("65a000000000000000000009"),
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Asset was modified concurrently");
}
~~~

Đây là cách tránh hai users cập nhật cùng catalog version rồi người thứ hai vô tình ghi đè kết quả của người thứ nhất.

### 11.3. Delete trước tiên là thay trạng thái

Với file nhạy cảm, nên bắt đầu từ:

~~~javascript
db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "READY"
  },
  {
    $set: {
      status: "DELETE_REQUESTED",
      updatedAt: new Date()
    }
  }
);
~~~

Kể từ khi status không còn READY, API phải từ chối **download mới**. Sau đó worker mới tiến hành xóa bytes an toàn, cập nhật status khi thành công và ghi audit.

### 11.4. Không xóa file còn được tham chiếu

Một fileId có thể còn được tham chiếu bởi:

- Asset hiện hành.
- Phiên bản lịch sử cần lưu.
- Một legal hold.
- Một job xử lý chưa hoàn tất.
- Một download stream đang hoạt động.
- Một backup/restore workflow.

Trước khi xóa, cần kiểm tra business reference policy và retention. Không chạy delete theo danh sách file IDs chỉ vì chúng không phải currentFileId của một document duy nhất.

### 11.5. Idempotent cleanup

Worker xóa có thể crash sau khi file đã bị xóa nhưng trước khi đánh dấu DELETED. Retry cần:

1. Tìm catalog trạng thái DELETING.
2. Kiểm tra GridFS file còn tồn tại không.
3. Nếu còn, tiếp tục xóa theo fileId.
4. Nếu đã mất, xác nhận chunks còn sót bằng quy trình riêng.
5. Đánh dấu DELETED khi đủ tiêu chí.

Không tự coi exception “file not found” là thất bại không thể khôi phục; cũng không coi nó là bằng chứng mọi chunks đã bị xóa.

### 11.6. Privacy deletion và backup

Nếu người dùng yêu cầu xóa dữ liệu:

~~~text
Xóa bản live
  !=
Xóa ngay mọi bản backup/snapshot
~~~

Retention của backup, bản archive và chính sách xóa theo pháp luật/hợp đồng phải được xác định trước. Có thể áp dụng **encryption key lifecycle/crypto-shredding** trong những kiến trúc phù hợp, nhưng điều đó cần thiết kế quản lý khóa từ đầu.

Đừng nói dữ liệu đã bị xóa khỏi mọi nơi nếu bản backup cũ vẫn có thể chứa file.

## 12. Sao lưu GridFS: không chỉ sao lưu assets.chunks

Một backup GridFS phục vụ phục hồi cần giữ:

1. **assets.files**: document mô tả file, _id, length, chunkSize, filename và metadata.
2. **assets.chunks**: binary chunks cùng files_id, n và data.
3. **asset_catalog** hoặc collections nghiệp vụ tham chiếu file.
4. Indexes và thông tin cấu hình cần để tái thiết lập quyền, validation hoặc application schemas.
5. Một **điểm nhất quán** về thời gian của các phần liên quan.

### 12.1. Các kiểu backup phổ biến

| Cách sao lưu | Điểm mạnh | Rủi ro cần giải quyết |
|---|---|---|
| **Managed snapshot / point-in-time backup** | Phù hợp backup nhất quán theo topology nếu nhà cung cấp hỗ trợ. | Cần retention, restore testing và hiểu phạm vi snapshot. |
| **mongodump / mongorestore** | Sao lưu/khôi phục BSON và metadata ở cấp database. | Cần xử lý snapshot consistency khi ghi đồng thời. |
| **Replica set mongodump --oplog** | Có cơ chế giữ/replay oplog để tạo bản dump nhất quán trong các điều kiện được hỗ trợ. | Không áp dụng tùy tiện cho sharded cluster hoặc dump chỉ một collection. |
| **Copy filesystem files trực tiếp** | Có thể nằm trong quy trình snapshot storage. | Copy nóng không có cơ chế nhất quán có thể sai; cần snapshot/lock/coordination đúng. |
| **mongofiles get từng file** | Tiện xuất một vài files để kiểm tra/chuyển giao. | Không thay cho backup đầy đủ, không tự giữ mọi metadata/index/ACL. |
| **mongoexport JSON/CSV** | Phù hợp export báo cáo dữ liệu có cấu trúc. | Không phải công cụ backup BSON/GridFS an toàn cho toàn bộ binary chunks. |

**Khuyến nghị:** với production, ưu tiên giải pháp snapshot/point-in-time backup do deployment hỗ trợ và thử restore định kỳ. Nếu dùng Database Tools, phải hiểu rõ giới hạn theo topology và thời điểm dữ liệu đang thay đổi.

### 12.2. Sao lưu chỉ assets.files là không đủ

Nếu có:

~~~text
assets.files:
  F100 -> length=600000, chunkSize=261120

assets.chunks:
  (chưa được backup)
~~~

Sau restore:

~~~text
find GridFS F100 -> thấy metadata
download F100 -> thiếu nội dung, lỗi dữ liệu
~~~

Ngược lại, chỉ sao lưu **assets.chunks** sẽ giữ bytes nhưng thiếu bảng mô tả file, filename, length và ACL linkage.

### 12.3. Không quên catalog và quyền

Nếu GridFS metadata có tenantId nhưng business catalog giữ owner/ACL/currentFileId, cả hai phải được backup theo một consistency model.

~~~text
Backup set cần đủ:

gridfs_security_lab.assets.files
gridfs_security_lab.assets.chunks
gridfs_security_lab.asset_catalog
gridfs_security_lab.asset_permissions (nếu tách riêng)
gridfs_security_lab.asset_audit (nếu nằm trong phạm vi phục hồi)
~~~

Nếu application records ở database/deployment khác, backup đồng nhất theo thời điểm phức tạp hơn. Phải định nghĩa cách phối hợp hoặc khôi phục bằng reconciliation/saga; không giả định hai MongoDB clusters tự có một điểm snapshot chung.

## 13. Point-in-time consistency: quan trọng hơn thứ tự dump hai collections

### 13.1. Một ví dụ backup không nhất quán

Giả sử tool backup chạy lần lượt:

~~~text
09:00:00  Dump assets.files
09:00:01  Upload F100 bắt đầu, ghi chunks
09:00:05  Upload F100 kết thúc, ghi files document
09:00:10  Dump assets.chunks
~~~

Bản backup có thể chứa:

~~~text
assets.files:  không có F100
assets.chunks: có chunks của F100
~~~

Nếu backup theo thứ tự ngược lại:

~~~text
09:00:00  Dump assets.chunks
09:00:05  Upload F100 hoàn thành
09:00:10  Dump assets.files
~~~

Bản backup có thể chứa:

~~~text
assets.files:  có F100
assets.chunks: không có chunks của F100
~~~

Trường hợp thứ hai đặc biệt nguy hiểm vì catalog có thể đánh dấu file READY nhưng bytes không còn đầy đủ.

### 13.2. Hai collections cùng database chưa đủ

Ngay cả khi **assets.files** và **assets.chunks** thuộc cùng database, việc dump chúng bằng hai lệnh riêng ở các thời điểm khác nhau **không tự tạo một snapshot nhất quán**.

Điều cần là một **consistent recovery point** hoặc một khoảng thời gian hệ thống được quiesce (không có uploads/deletes/metadata updates) và có cách xác nhận các writes đã hoàn tất.

### 13.3. Replica set: dùng cơ chế oplog được Database Tools hỗ trợ

Với một replica set và một bản dump đầy đủ, Database Tools hỗ trợ **mongodump --oplog** để ghi thêm những operations xảy ra trong thời gian dump; khi restore có thể replay oplog theo quy trình tương ứng.

Ví dụ lệnh **minh họa** từ máy vận hành đã cài MongoDB Database Tools:

~~~bash
mongodump \
  --uri="mongodb://backup-user@db1.example:27017,db2.example:27017/?replicaSet=rs0" \
  --archive="./replica-set-backup.archive.gz" \
  --gzip \
  --oplog
~~~

Khi chạy thật:

- Không đưa password vào shell history hay ví dụ công khai.
- Cần credential, network/TLS và quyền backup phù hợp.
- **--oplog** có ràng buộc với dump **toàn bộ mongod/replica set** và không được kết hợp tùy ý với **--db, --collection hoặc --query** theo phiên bản Database Tools.
- Có thể cân nhắc chạy trên secondary phù hợp để giảm tải primary theo chiến lược backup.
- Không tự dùng ví dụ replica set như một quy trình đảm bảo consistent backup của **sharded cluster**.

**Lưu ý:** câu lệnh shell trên chỉ phác họa option, không phải runbook đủ cho mọi MongoDB phiên bản, TLS/Atlas topology hay policy bảo mật.

### 13.4. Sharded cluster cần backup nhất quán trên các shards

Trong sharded cluster, một file hoặc các collections liên quan có thể phân bố qua shards. Một dump qua mongos trong khi writes đang diễn ra không tự đảm bảo **một mốc snapshot synchronized trên mọi shard**.

Ưu tiên:

1. Managed sharded-cluster snapshot/point-in-time backup được hỗ trợ.
2. Cơ chế backup chuyên dụng có coordination across shards.
3. Nếu không có, một maintenance window thực sự ngừng writes và xác minh trạng thái nhất quán trước dump.

Không coi **mongodump --oplog** trên một shard là backup toàn bộ sharded GridFS. Không tự ghép các snapshots từng shard chụp ở những thời điểm khác nhau rồi gọi là point-in-time consistent.

### 13.5. Backup snapshot có thể chứa chunks upload dở dang

Giả sử snapshot tại thời điểm:

~~~text
F100 chunk 0 đã được ghi
F100 chunk 1 đã được ghi
F100 upload chưa hoàn tất
assets.files chưa có F100
asset_catalog.status = UPLOADING
~~~

Bản snapshot này vẫn có thể phản ánh **đúng trạng thái hệ thống tại thời điểm chụp**. Nó không nhất thiết là backup hỏng.

Sau restore, recovery worker phải xử lý **in-progress uploads** theo trạng thái thời điểm đó, ví dụ đánh dấu FAILED/RETRYABLE và cleanup chunks sau grace period. Đừng kết luận mỗi orphan chunk trong backup chứng minh point-in-time backup thiếu nhất quán.

### 13.6. Định nghĩa recovery point cho metadata và bytes

Với business catalog và GridFS cùng một replica set, mục tiêu:

~~~text
Snapshot at T:

asset_catalog(T)
assets.files(T)
assets.chunks(T)
~~~

Nếu file **READY tại T**, backup kỳ vọng có đủ bytes đã được công bố tại T.

Nếu file mới **UPLOADING tại T**, backup có thể có catalog/chunks đang dở dang mà không có files record hoàn chỉnh. Recovery nên giữ file ẩn và xử lý lại workflow.

## 14. Restore GridFS: dữ liệu đúng chưa đủ, quyền cũng phải đúng

### 14.1. Quy trình restore có kiểm soát

~~~text
Restore request
      |
      v
Choose verified backup/recovery point
      |
      v
Restore into isolated staging environment
      |
      v
Verify collections and indexes
      |
      v
Reconcile files/chunks/business links
      |
      v
Verify sample SHA-256 + content reads
      |
      v
Validate app permissions/tenant isolation
      |
      v
Promote or re-point application traffic
      |
      v
Monitor and complete recovery
~~~

**Không restore một archive chưa kiểm chứng trực tiếp lên production đang chạy** khi có khả năng ghi đè dữ liệu hiện tại hoặc hồi sinh quyền truy cập đã bị thu hồi.

### 14.2. Ví dụ mongorestore có oplog replay

Với archive đã tạo bằng cách được hỗ trợ:

~~~bash
mongorestore \
  --uri="mongodb://restore-user@restore-host.example:27017/?replicaSet=rsRestore" \
  --archive="./replica-set-backup.archive.gz" \
  --gzip \
  --oplogReplay
~~~

Chỉ chạy trên **deployment khôi phục được phép**, với phiên bản Database Tools và quyền restore phù hợp. **--oplogReplay** có các giới hạn về cách archive được tạo và các options restore khác; cần đối chiếu tài liệu Database Tools hiện hành.

Không thêm **--drop** vào một lệnh restore production chỉ để “cho sạch” khi chưa biết chính xác nó sẽ xóa collections nào. Với nhiều hệ thống, restore vào environment mới rồi promote an toàn hơn restore đè.

### 14.3. Giữ nguyên _id, files_id và n

Khi restore:

~~~text
assets.files._id = F100
assets.chunks.files_id = F100
assets.chunks.n = 0,1,2
~~~

**Không tự sinh _id mới cho assets.files** mà quên cập nhật files_id trong chunks và currentFileId trong catalog. Việc đổi file ID là một migration tham chiếu toàn hệ thống, không phải một bước restore tùy tiện.

### 14.4. Verify indexes

Sau restore:

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").getIndexes();
db.getCollection("assets.chunks").getIndexes();
db.asset_catalog.getIndexes();
~~~

Kiểm tra tối thiểu:

- Unique index **{files_id:1,n:1}** trên chunks.
- Các GridFS indexes cần thiết cho driver và queries.
- Unique index của catalog theo business key/requestId khi có.
- Index theo tenant/owner/status nếu API dùng để list/filter.

Nếu một restore chỉ sao chép documents mà không giữ index definitions, dữ liệu có thể đọc được nhưng truy vấn chậm hoặc các ràng buộc unique không còn được bảo vệ.

### 14.5. Quyền sau restore có thể khác quyền hiện tại

Nếu backup tại T1:

~~~text
DOC-100 được chia sẻ với user-35
~~~

nhưng tại T2:

~~~text
Quyền user-35 đã bị thu hồi
~~~

thì restore về T1 có thể **đưa lại quyền cũ** nếu policy nằm trong snapshot.

Quy trình DR cần quyết định:

- Có lưu các revocations quan trọng ở hệ thống ngoài backup snapshot không?
- Khi restore, áp lại những thay đổi quyền sau recovery point bằng audit/event log phù hợp?
- Có tạm chặn download sensitive files trước khi hoàn tất policy reconciliation không?
- Ai có quyền approve việc mở lại dịch vụ?

Backup đúng bytes nhưng sai ACL có thể là một sự cố bảo mật nghiêm trọng.

### 14.6. Đồng bộ backup với các hệ thống bên ngoài

Một file có thể được tham chiếu từ:

- Search index.
- Một RDBMS quản lý hợp đồng.
- Message broker/outbox.
- CDN/cache.
- Object store hoặc archive bên ngoài.

Restore MongoDB về T1 **không tự restore các hệ thống này về T1**. Sau phục hồi có thể phải rebuild projections, invalidate CDN và reconciliation theo business IDs.

### 14.7. Chọn RPO và RTO có ý nghĩa

| Chỉ số | Câu hỏi |
|---|---|
| **RPO (Recovery Point Objective)** | Có thể mất tối đa bao nhiêu dữ liệu/tác vụ gần nhất khi khôi phục? |
| **RTO (Recovery Time Objective)** | Cần bao lâu để dịch vụ file hoạt động trở lại? |

Với GridFS, RTO không chỉ gồm thời gian restore bytes; còn có thời gian kiểm tra checksum, indexes, quyền và business catalog.

RPO phải bao gồm cả **file content lẫn thay đổi quyền/metadata**. Không chỉ đo RPO bằng số file mới tạo.

## 15. Kiểm tra tính toàn vẹn giữa assets.files và assets.chunks

Sau backup/restore hoặc sau một sự cố upload, cần phân biệt **metadata có tồn tại** với **file có thể đọc và đúng bytes**.

### 15.1. Các bất biến kỹ thuật

Với mỗi file document F:

~~~text
id        = F._id
length    = F.length
chunkSize = F.chunkSize

expectedChunks =
  length == 0 ? 0 : ceil(length / chunkSize)
~~~

Khi expectedChunks > 0:

1. Có chính xác số chunks dự kiến.
2. Sequence **n** chạy từ 0 đến expectedChunks-1, liên tục.
3. Mỗi chunk không phải cuối có data byte length bằng chunkSize.
4. Chunk cuối có độ dài phù hợp phần còn lại.
5. Tổng byte lengths đúng bằng F.length.
6. SHA-256 toàn bộ bytes khớp digest đã xác minh nếu có.

Không thể suy điều 2–6 chỉ từ **countDocuments**.

### 15.2. Công thức kiểm tra chunk cuối

Với file không rỗng:

~~~text
lastChunkBytes =
  length - (expectedChunks - 1) * chunkSize
~~~

Ví dụ:

~~~text
length        = 600000
chunkSize     = 261120
expectedChunks= 3
lastChunkBytes= 77760
~~~

Nếu chunk cuối có 12.000 bytes thay vì 77.760, metadata có thể vẫn ghi length=600000 nhưng content thực thiếu. Nếu có chunk đủ byte nhưng bị thay đổi một phần, chỉ có checksum/content verification mới phát hiện đáng tin cậy.

### 15.3. Kiểm tra một file trong mongosh

Giả sử biết GridFS file ID thực:

~~~javascript
use gridfs_security_lab

const fileId = ObjectId("65a000000000000000000001");

const file = db.getCollection("assets.files").findOne({
  _id: fileId
});

printjson(file);

if (file) {
  print("length=" + file.length);
  print("chunkSize=" + file.chunkSize);
}

db.getCollection("assets.chunks").aggregate([
  {
    $match: {
      files_id: fileId
    }
  },
  {
    $sort: {
      n: 1
    }
  },
  {
    $project: {
      _id: 0,
      n: 1,
      byteLength: {
        $binarySize: "$data"
      }
    }
  }
]);
~~~

Kết quả mong đợi với file ví dụ:

| n | byteLength |
|---:|---:|
| 0 | 261120 |
| 1 | 261120 |
| 2 | 77760 |

Nếu file thật chưa được upload trong lab, đoạn mã chỉ trả null hoặc một cursor rỗng. Các IDs ở bài mang tính minh họa, **không tự tạo nội dung binary chỉ vì đã có ví dụ metadata**.

### 15.4. Tổng số chunks và tổng bytes

~~~javascript
db.getCollection("assets.chunks").aggregate([
  {
    $match: {
      files_id: fileId
    }
  },
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 },
      totalBytes: {
        $sum: {
          $binarySize: "$data"
        }
      },
      minN: { $min: "$n" },
      maxN: { $max: "$n" }
    }
  }
]);
~~~

Nếu:

~~~text
chunkCount=3
minN=0
maxN=2
totalBytes=600000
~~~

đó là tín hiệu tốt, nhưng **chưa đủ kiểm tra sequence unique** nếu unique index bị thiếu và có nhiều bản ghi trùng n. Chưa đủ chứng minh bytes đúng về mặt nội dung nếu một chunk bị thay thế bởi binary data cùng kích thước.

### 15.5. Unique index và các lỗ hổng còn lại

~~~javascript
db.getCollection("assets.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);
~~~

Index ngăn duplicate sequence trong phạm vi file. Nhưng:

~~~text
n = 0, 2, 3
~~~

vẫn có thể thỏa uniqueness mà thiếu chunk n=1. Trên thực tế GridFS driver đọc có thể báo lỗi khi gặp sequence hoặc size không đúng. Hãy xử lý lỗi đọc như một integrity incident, không cố ghép các chunks một cách chắp vá.

### 15.6. Phát hiện file document không có đủ chunks

Một kiểm tra reconciliation có thể:

~~~text
For each published file:
  load GridFS file document
  calculate expectedChunks
  read related chunks in n order
  verify contiguous sequence and sizes
  stream data to SHA-256
  compare digest and expected length
  record verification result
~~~

Với hàng triệu files, không chạy verify toàn bộ bytes trong một HTTP request. Có thể:

- Kiểm tra counts/sequence trước.
- Chia theo tenant, thời gian upload hoặc những files mới.
- Verify full checksum theo lịch/rủi ro.
- Ưu tiên files từ backup mới restore hoặc từ upload có lỗi.

### 15.7. Không tự sửa length để khớp dữ liệu bị thiếu

Nếu:

~~~text
assets.files.length = 600000
actual chunks = 500000 bytes
~~~

thì cập nhật length=500000 chỉ che mất sự cố. File có thể bị cắt cụt ở phần giữa hoặc cuối và không còn hợp lệ về nghiệp vụ.

Hướng đúng: **quarantine file, đánh dấu CORRUPT/UNAVAILABLE, restore bytes từ backup hoặc yêu cầu reupload**, rồi kiểm tra checksum trước khi publish lại.

## 16. Orphan chunks và missing files

### 16.1. Hai dạng “mồ côi” khác nhau

**Orphan chunks**:

~~~text
assets.chunks có files_id=F100
assets.files không có _id=F100
~~~

**Orphan GridFS file / unreferenced file**:

~~~text
assets.files có _id=F101
assets.chunks của F101 có đủ
asset_catalog không còn tham chiếu F101
~~~

Loại thứ hai không nhất thiết là lỗi: F101 có thể là phiên bản lịch sử, file đang chờ scan hoặc file hợp pháp được upload nhưng chưa publish.

### 16.2. Truy vấn tìm orphan chunk candidates

Chỉ dùng để **khảo sát** trên môi trường nhỏ/lab vì phép group+lookup toàn bộ chunks có thể rất tốn tài nguyên:

~~~javascript
db.getCollection("assets.chunks").aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 }
    }
  },
  {
    $lookup: {
      from: "assets.files",
      localField: "_id",
      foreignField: "_id",
      as: "fileMatches"
    }
  },
  {
    $match: {
      "fileMatches.0": {
        $exists: false
      }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1
    }
  }
]);
~~~

Query này chỉ tìm **candidates**. Một GridFS upload đang chạy có thể hợp pháp tạo chunks trước khi files record xuất hiện.

### 16.3. Đừng xóa orphan candidate ngay

Một cleanup policy nên yêu cầu:

1. Không có upload lease/job còn active cho fileId/uploadRequestId.
2. Candidate đã quá **grace period** phù hợp với max upload duration.
3. Không có catalog record đang SCANNING/RECOVERING.
4. Không có backup/restore/cutover đang xử lý file đó.
5. Đã xác minh file thật sự không còn cần dùng.
6. Có audit và khả năng chạy cleanup idempotent.

Nếu thiếu các điều kiện này, một cleaner chạy cùng lúc uploader có thể xóa chunks của file đang được tạo, khiến upload thất bại và dữ liệu bị hỏng.

### 16.4. Cleanup orphan chunks

**Không chạy lệnh sau trên production chỉ vì nhìn thấy một candidate.** Khi đã xác minh đầy đủ trong môi trường lab/được phép, một thao tác xóa có thể là:

~~~javascript
const confirmedOrphanId = ObjectId(
  "65a000000000000000000099"
);

db.getCollection("assets.chunks").deleteMany({
  files_id: confirmedOrphanId
});
~~~

Mục đích minh họa là xóa đúng chunks theo một files_id đã xác minh. Trong production nên qua cleanup worker có lease, trạng thái, dry-run, audit và retry; không chạy deleteMany thủ công khi không rõ ai đang upload.

### 16.5. File đã xuất hiện nhưng thiếu chunks

~~~text
assets.files F100 exists
expected n = 0,1,2
actual n   = 0,2
~~~

Không giải quyết bằng cách tạo chunk n=1 chứa toàn số 0 hoặc copy n=2 thành n=1. Nội dung file đã mất chính xác và cần **khôi phục nguyên bản**.

Khi có backup nhất quán:

1. Tạm khóa khả năng download/publish file F100.
2. Tìm bản backup có file đã hoàn chỉnh.
3. Restore F100 vào staging hoặc extract theo quy trình.
4. So SHA-256 với digest tin cậy.
5. Phục hồi/đổi pointer theo quy trình có kiểm soát.
6. Ghi sự cố và phân tích nguyên nhân.

### 16.6. Catalog tham chiếu file không tồn tại

Một reconciliation query (mang tính khảo sát):

~~~javascript
db.asset_catalog.aggregate([
  {
    $match: {
      status: "READY"
    }
  },
  {
    $lookup: {
      from: "assets.files",
      localField: "currentFileId",
      foreignField: "_id",
      as: "gridFsMatches"
    }
  },
  {
    $match: {
      "gridFsMatches.0": {
        $exists: false
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      currentFileId: 1,
      status: 1
    }
  }
]);
~~~

**Không tự động xóa catalog record** khi không có GridFS file: đó có thể là bằng chứng của một sự cố cần phục hồi. Nên đưa asset vào trạng thái UNAVAILABLE và xác định recovery source.

### 16.7. Mismatch tenant hoặc business ID

Kể cả khi file tồn tại, vẫn có thể có:

~~~text
asset_catalog:
  assetId=DOC-100, tenantId=tenant-a, currentFileId=F100

assets.files:
  _id=F100, metadata.tenantId=tenant-b
~~~

Đây là lỗi liên kết nghiêm trọng. Không phục vụ file chỉ vì _id match. Cần quarantine hoặc điều tra, xác nhận authoritative metadata và kiểm tra logs trước khi chỉnh sửa.

## 17. Checksum: xác minh bytes, không chỉ số chunk

### 17.1. Vì sao SHA-256?

Hash mật mã như SHA-256 giúp phát hiện thay đổi nội dung với xác suất va chạm thực tế cực thấp. Nó phù hợp để kiểm tra integrity đối với file thông thường.

Không dùng **số byte** hoặc **tên file** thay checksum:

~~~text
File A length=600000, filename=contract.pdf
File B length=600000, filename=contract.pdf

Nội dung A và B vẫn có thể khác nhau.
~~~

### 17.2. Hash nên tính ở đâu?

Một pipeline:

~~~text
Client upload bytes
       |
       v
Backend computes SHA-256 while streaming
       |
       v
GridFS stores bytes
       |
       v
Backend verifies read-back SHA-256 when required
       |
       v
Publish verified digest
~~~

Hash của input được tính bởi backend có thể được dùng làm expected digest. Nếu cần mức bảo đảm cao khi backup/restore, hash thêm **file đọc lại**.

### 17.3. Khi nào phải đọc lại toàn bộ bytes?

- Sau một restore đáng kể.
- Sau sự cố missing/mismatch chunks.
- Khi dùng GridFS làm kho lưu trữ tài liệu có yêu cầu kiểm chứng dài hạn.
- Khi cần bằng chứng file được lưu đúng nguyên bản.
- Trong quá trình kiểm tra định kỳ theo chính sách integrity.

Lưu ý hash toàn bộ file 20 GB vẫn cần đọc 20 GB, nên phải dự trù I/O và throughput. Không hash toàn bộ kho vào giờ cao điểm nếu không có capacity.

### 17.4. Checksum và chữ ký số khác nhau

**SHA-256 digest** chứng minh bytes khớp expected digest nếu digest đáng tin.

**Digital signature** giúp xác minh digest hoặc tài liệu được ký bởi khóa xác định. Nếu attacker có quyền sửa cả bytes lẫn metadata.sha256, kiểm tra digest tự thân có thể vẫn “khớp”.

Với threat model chống giả mạo bởi người có quyền ghi database, hãy giữ digest/chữ ký trong một trust domain tách biệt, với quản lý khóa và audit phù hợp.

## 18. Java Sync Driver: GridFSBucket, metadata và stream

MongoDB Java Sync Driver có API **GridFSBucket** để upload/download/delete file theo luồng.

Một bucket tùy chỉnh:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

public final class GridFsConnectionExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "gridfs_security_lab"
            );

            GridFSBucket bucket = GridFSBuckets.create(
                    database,
                    "assets"
            );

            // Bucket "assets" dùng assets.files và assets.chunks.
            System.out.println(bucket.getBucketName());
        }
    }
}
~~~

**MongoClient** thường được tái sử dụng cho nhiều requests trong ứng dụng; ví dụ main đóng nó khi chương trình kết thúc. Không tạo MongoClient mới cho mỗi chunk hoặc mỗi lần tải một file.

### 18.1. Upload với custom metadata

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;

public final class GridFsUploadService {
    private final GridFSBucket bucket;

    public GridFsUploadService(GridFSBucket bucket) {
        this.bucket = bucket;
    }

    public ObjectId uploadPending(
            InputStream input,
            String filename,
            String assetId,
            String tenantId,
            String ownerId,
            String uploadRequestId) {

        Document metadata = new Document(
                "tenantId",
                tenantId
        ).append(
                "ownerId",
                ownerId
        ).append(
                "applicationFileId",
                assetId
        ).append(
                "uploadRequestId",
                uploadRequestId
        ).append(
                "status",
                "SCANNING"
        );

        GridFSUploadOptions options = new GridFSUploadOptions()
                .chunkSizeBytes(255 * 1024)
                .metadata(metadata);

        // Stream input phải đã được giới hạn size và kiểm tra quyền.
        return bucket.uploadFromStream(
                filename,
                input,
                options
        );
    }
}
~~~

Lưu ý:

1. API nhận **tenantId/ownerId từ backend đã xác thực**, không dùng thẳng tham số do caller tự khai.
2. **uploadFromStream** ghi file thành nhiều documents; lỗi có thể xảy ra giữa chừng.
3. Metadata status **SCANNING** nghĩa file chưa được công bố.
4. Sau khi upload thành công, trả **GridFS file ID**, nhưng business service cần verify và publish bằng bước riêng.
5. Ví dụ không giới hạn bytes ngay trong method; production phải có wrapper cho input stream, quota và cancellation.

### 18.2. Kiểm tra file metadata trước khi download

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.OutputStream;

public final class SecureGridFsDownloadService {

    private final GridFSBucket bucket;
    private final MongoCollection<Document> catalog;
    private final MongoCollection<Document> files;

    public SecureGridFsDownloadService(
            GridFSBucket bucket,
            MongoDatabase database) {

        this.bucket = bucket;
        this.catalog = database.getCollection("asset_catalog");
        this.files = database.getCollection("assets.files");
    }

    public void download(
            String assetId,
            String authenticatedTenantId,
            OutputStream output) {

        // Ví dụ đơn giản: chỉ kiểm tra tenant + trạng thái.
        // Production phải có ACL owner/share-role policy đầy đủ.
        Document asset = catalog.find(
                Filters.and(
                        Filters.eq("_id", assetId),
                        Filters.eq("tenantId", authenticatedTenantId),
                        Filters.eq("status", "READY")
                )
        ).first();

        if (asset == null) {
            throw new IllegalArgumentException(
                    "Asset is not available"
            );
        }

        ObjectId fileId = asset.getObjectId("currentFileId");
        if (fileId == null) {
            throw new IllegalStateException(
                    "READY asset has no GridFS file ID"
            );
        }

        Document file = files.find(
                Filters.and(
                        Filters.eq("_id", fileId),
                        Filters.eq(
                                "metadata.tenantId",
                                authenticatedTenantId
                        ),
                        Filters.eq(
                                "metadata.applicationFileId",
                                assetId
                        )
                )
        ).first();

        if (file == null) {
            throw new IllegalStateException(
                    "GridFS file metadata mismatch"
            );
        }

        bucket.downloadToStream(fileId, output);
    }
}
~~~

**Quan trọng:** đây là ví dụ tối thiểu cho nguyên tắc **authorization trước download + đối chiếu metadata**. Một service production cần thêm:

- Owner/group/sharing ACL thật, không chỉ tenant.
- Điều kiện status/version và tenant được giữ ổn định trong toàn workflow.
- Size/rate limiting, timeout, cancellation.
- Chính sách xử lý delete đồng thời với download.
- Content-Type, Content-Disposition và cache headers an toàn.
- Error mapping (not found/forbidden) tránh lộ thông tin file tồn tại ở tenant khác.

### 18.3. Không dùng find by filename làm nguồn quyền

~~~java
// Dễ sai nếu có nhiều tenant hoặc nhiều versions.
bucket.downloadToStreamByName("contract.pdf", output);
~~~

Download theo tên có thể có nhiều phiên bản hoặc nhiều owners. Với tài liệu cần ACL, nên xác định **business asset** và chính xác **GridFS file ID** đã được authorize.

### 18.4. Publish bằng conditional update

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;

public final class GridFsPublisher {

    private final MongoCollection<Document> catalog;

    public GridFsPublisher(MongoCollection<Document> catalog) {
        this.catalog = catalog;
    }

    public void publishVerified(
            String assetId,
            String tenantId,
            String uploadRequestId,
            ObjectId verifiedFileId) {

        UpdateResult result = catalog.updateOne(
                Filters.and(
                        Filters.eq("_id", assetId),
                        Filters.eq("tenantId", tenantId),
                        Filters.eq("status", "SCANNING"),
                        Filters.eq(
                                "uploadRequestId",
                                uploadRequestId
                        )
                ),
                Updates.combine(
                        Updates.set(
                                "currentFileId",
                                verifiedFileId
                        ),
                        Updates.set("status", "READY"),
                        Updates.inc("version", 1)
                )
        );

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Concurrent modification or invalid state"
            );
        }
    }
}
~~~

Method này giả định **verifiedFileId đã được một bước đáng tin cậy xác minh**. Không gọi publishVerified ngay sau upload nếu còn cần quét malware/checksum.

### 18.5. Java tính SHA-256 khi đọc GridFS file

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class GridFsIntegrityVerifier {

    public static String sha256(
            GridFSBucket bucket,
            ObjectId fileId)
            throws IOException, NoSuchAlgorithmException {

        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (
                GridFSDownloadStream stream =
                        bucket.openDownloadStream(fileId)
        ) {
            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Đoạn code dùng **java.util.HexFormat** (Java 17+). Nó tính hash từ bytes **đọc lại qua GridFS**, không phải từ metadata.sha256. So kết quả với expected digest đã lưu trong nguồn tin cậy.

GridFS driver có thể ném exception khi gặp chunks thiếu/hỏng; một integrity verifier phải **ghi trạng thái lỗi và không công bố file** thay vì nuốt exception rồi trả “verified”.

### 18.6. Java xử lý stream lớn

Với GridFSDownloadStream:

- Đọc theo buffer nhỏ, không cần load toàn file vào heap.
- Đóng stream trong **try-with-resources**.
- Có timeout/cancellation theo service architecture.
- Nếu HTTP client ngắt kết nối, phải đóng stream và không để database cursor bị bỏ quên.

### 18.7. GridFSBucket.delete không phải delete toàn application asset

~~~java
bucket.delete(fileId);
~~~

Lệnh này tác động tới file GridFS tương ứng, không tự cập nhật **asset_catalog**, xóa một legal hold, thông báo client hoặc đảm bảo các external references đã đổi trạng thái.

Chỉ gọi sau khi business service đã xác minh quyền delete và thực hiện lifecycle/retention tương ứng.

## 19. Spring Data MongoDB: GridFsTemplate và quyền truy cập

Spring Data MongoDB có **GridFsTemplate** cho các thao tác lưu/đọc/xóa GridFS trong imperative applications.

### 19.1. Chọn bucket name

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

@Configuration
public class GridFsConfig {

    @Bean
    GridFsTemplate assetsGridFsTemplate(
            MongoDatabaseFactory databaseFactory,
            MongoConverter converter) {

        return new GridFsTemplate(
                databaseFactory,
                converter,
                "assets"
        );
    }
}
~~~

Đảm bảo bean được cấu hình đúng database/bucket và application không vô tình ghi vào bucket mặc định **fs** trong khi các APIs đọc **assets**.

### 19.2. Lưu file với metadata

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

import java.io.InputStream;

public final class SpringGridFsUploadService {

    private final GridFsTemplate gridFsTemplate;

    public SpringGridFsUploadService(
            GridFsTemplate gridFsTemplate) {
        this.gridFsTemplate = gridFsTemplate;
    }

    public ObjectId uploadPending(
            InputStream input,
            String filename,
            String contentType,
            String tenantId,
            String assetId) {

        Document metadata = new Document(
                "tenantId",
                tenantId
        ).append(
                "applicationFileId",
                assetId
        ).append(
                "status",
                "SCANNING"
        );

        return gridFsTemplate.store(
                input,
                filename,
                contentType,
                metadata
        );
    }
}
~~~

**Lưu ý:** contentType trong ví dụ là metadata do ứng dụng quyết định, không tự xác thực nội dung. Nếu input lấy từ multipart request, phải áp dụng size limit và validation.

### 19.3. Đọc file bằng GridFsTemplate

~~~java
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

import java.io.InputStream;
import java.io.IOException;

public final class SpringGridFsReader {

    private final GridFsTemplate gridFsTemplate;

    public SpringGridFsReader(GridFsTemplate gridFsTemplate) {
        this.gridFsTemplate = gridFsTemplate;
    }

    public InputStream openStreamAfterAuthorization(
            ObjectId verifiedFileId) throws IOException {

        GridFSFile file = gridFsTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is(verifiedFileId)
                )
        );

        if (file == null) {
            throw new IllegalArgumentException(
                    "File not found"
            );
        }

        GridFsResource resource = gridFsTemplate.getResource(file);
        return resource.getInputStream();
    }
}
~~~

Method tên **openStreamAfterAuthorization** có chủ ý: caller phải đã kiểm tra tenant, owner, sharing policy và trạng thái READY từ business catalog. Nó **không tự thực hiện authorization** chỉ vì nhận một ObjectId.

Caller phải **đóng InputStream** sau khi stream response hoàn tất hoặc bị hủy.

### 19.4. Xóa bằng Spring Data

~~~java
gridFsTemplate.delete(
    Query.query(
        Criteria.where("_id").is(verifiedFileId)
    )
);
~~~

Đây là thao tác xóa GridFS theo query được framework cung cấp. Nó không tự giải quyết toàn bộ **asset_catalog lifecycle**, audit, retention và các concurrent downloads.

### 19.5. Vì sao @Transactional không giải quyết toàn bộ vấn đề?

Không nên viết:

~~~java
@Transactional
public void uploadBusinessAsset(...) {
    gridFsTemplate.store(...);
    assetRepository.markReady(...);
}
~~~

rồi suy rằng **mọi GridFS chunks, file document và catalog đều được commit atomically**. GridFS không hỗ trợ multi-document transactions theo mô hình này.

Giải pháp nên là **state machine + publish bằng atomic catalog update + recovery/reconciliation**.

### 19.6. Truy cập GridFS từ Spring controller

Một web controller nên:

1. Lấy principal/tenant từ security context.
2. Gọi service kiểm tra quyền ở catalog.
3. Xác minh GridFS file metadata/trạng thái theo policy.
4. Chuẩn bị response headers.
5. Stream nội dung với resource cleanup.
6. Log asset ID/correlation ID và lỗi; tránh log bytes hay dữ liệu nhạy cảm.

Không để controller đọc raw GridFsTemplate theo arbitrary fileId khi không có bước permission check.

## 20. Encryption, backup retention và bảo mật vận hành

### 20.1. Mã hóa khi truyền

Kết nối ứng dụng tới MongoDB và các dịch vụ backup nên dùng **TLS**. Khi GridFS chứa thông tin nhạy cảm, phải bảo đảm:

- Connection URI/driver được cấu hình TLS đúng.
- Certificate validation phù hợp, không bỏ xác minh chứng chỉ để “cho chạy”.
- Không truyền MongoDB credentials qua HTTP hay log.
- Secrets được lưu qua secret manager/môi trường bảo vệ, có quy trình rotation.

File download qua HTTPS cũng phải được bảo vệ ở proxy/gateway; không chỉ mã hóa đoạn ứng dụng tới database.

### 20.2. Mã hóa khi lưu trữ

MongoDB deployment có thể hỗ trợ encryption at rest thông qua nền tảng/Atlas hoặc storage engine/KMS theo cấu hình. Kiểm tra:

- Dữ liệu GridFS chunks và metadata có cùng policy encryption không?
- Key được quản lý và rotate ra sao?
- Backups/snapshots/archive có được mã hóa độc lập không?
- Ai có quyền lấy khóa để restore?

Mã hóa at rest giúp giảm rủi ro truy cập trái phép vào ổ đĩa/backup, nhưng **không thay thế application authorization**: một service có DB credentials hợp lệ vẫn có thể đọc dữ liệu giải mã theo quyền của nó.

### 20.3. Mã hóa ở tầng ứng dụng

Với threat model nghiêm ngặt, có thể **mã hóa file bytes trước khi upload vào GridFS**:

~~~text
Plaintext stream
      |
      v
Authenticated encryption
      |
      v
Encrypted bytes stored in GridFS
      |
      v
Download -> decrypt for authorized caller
~~~

Khi làm vậy cần:

- Quản lý khóa theo tenant/file/version.
- Nonce/IV và authenticated encryption đúng chuẩn.
- Lưu key identifiers và metadata giải mã trong trust domain phù hợp.
- Giải quyết antivirus/content scanning ở bước có plaintext hợp pháp.
- Hỗ trợ key rotation và restore backup kèm khóa.
- Không tự xây crypto protocol từ các thao tác ghép chuỗi hoặc XOR.

Nếu mất khóa, backup có thể phục hồi thành công nhưng **nội dung vẫn không giải mã được**. Vì vậy backup/DR phải kiểm tra cả khả năng khôi phục khóa.

### 20.4. Sao lưu an toàn với dữ liệu cá nhân

Một archive chứa GridFS chunks có thể chứa toàn bộ:

~~~text
hợp đồng
hình ảnh giấy tờ tùy thân
ảnh hồ sơ
thông tin tài chính
tệp nội bộ
~~~

Tuy bytes nằm trong BSON và archive nén, đó vẫn là dữ liệu nhạy cảm. Cần:

- Mã hóa backup trước khi lưu vào storage.
- Phân quyền read/list/delete backup tối thiểu.
- Bảo vệ khóa mã hóa riêng.
- Kiểm tra địa điểm lưu trữ và data residency khi có yêu cầu.
- Không dùng production backup không ẩn danh trên laptop cá nhân/staging mở.
- Thiết lập retention, immutability/offsite copy khi phù hợp threat model.

### 20.5. Backup restore drill không phải chỉ chạy lệnh thành công

Một lần restore test cần chứng minh:

1. Archive/snapshot truy cập được.
2. Database và indexes đã được khôi phục đúng.
3. Chọn nhóm files có kích thước và types khác nhau để download.
4. Checksum khớp digest tin cậy.
5. Quyền tenant/owner hoạt động như kỳ vọng.
6. Catalog không tham chiếu đến file không tồn tại ở những bản ghi READY được kiểm tra.
7. Có thể phục hồi kịp RTO và trong giới hạn RPO.

### 20.6. Không restore quyền production lên môi trường thử nghiệm không kiểm soát

Nếu backup có users/roles hoặc access policies cũ, cần kiểm tra trước khi mở kết nối ứng dụng. Môi trường khôi phục nên:

- Tách mạng và credentials khỏi production.
- Không gửi email/webhook/outbound side effects thật.
- Không để CDN hoặc public DNS trỏ nhầm.
- Chỉ mở quyền truy cập sau khi kiểm tra ACL và dữ liệu.

## 21. Monitoring, cảnh báo và reconciliation định kỳ

### 21.1. Những chỉ số nên theo dõi

| Metric gợi ý | Ý nghĩa |
|---|---|
| **gridfs_upload_started_total** | Số upload requests đã bắt đầu. |
| **gridfs_upload_completed_total** | Số GridFS uploads đóng thành công. |
| **gridfs_upload_failed_total** | Số upload lỗi, phân loại network/size/quota/scan. |
| **gridfs_pending_age_seconds** | Thời gian file ở UPLOADING/SCANNING. |
| **gridfs_ready_without_chunks_total** | Số files READY kiểm tra không có đủ chunks. |
| **gridfs_orphan_chunk_candidates_total** | Số file IDs có chunks nhưng thiếu files record. |
| **gridfs_orphan_bytes_estimate** | Dung lượng ước tính bị giữ bởi chunks candidates. |
| **gridfs_metadata_mismatch_total** | Số mismatches tenant/assetId/length/hash. |
| **gridfs_download_failed_total** | Tải thất bại, phân loại forbidden/not found/corrupt. |
| **gridfs_reconciliation_lag_seconds** | Tuổi của dữ liệu chưa được kiểm tra đối soát. |
| **gridfs_backup_age_seconds** | Khoảng thời gian từ backup thành công gần nhất. |
| **gridfs_restore_verification_failures** | Lỗi trong thử khôi phục/kiểm tra integrity. |

Đây là **application metrics gợi ý**, không phải các tên metric mặc định mà MongoDB tự cung cấp.

### 21.2. Tách lỗi quyền với lỗi corrupt

Một download bị từ chối có thể do:

~~~text
UNAUTHORIZED       -> chưa đăng nhập.
FORBIDDEN          -> không có quyền.
NOT_FOUND          -> asset không tồn tại hoặc bị ẩn theo policy.
NOT_READY          -> upload đang xử lý hoặc đã bị thu hồi.
CORRUPT            -> thiếu chunks/sai checksum.
DEPENDENCY_FAILED  -> MongoDB/network lỗi.
~~~

Trong API public, có thể trả 404 chung cho những resources không thuộc quyền để tránh leak existence. Nội bộ vẫn nên có **reason code** để phân biệt security incident với storage incident.

### 21.3. Reconciliation job theo lịch

~~~text
Scheduled reconciliation
  |
  +-- Scan recent READY assets
  |     |
  |     +-- Verify currentFileId exists
  |     +-- Compare tenant/applicationFileId
  |     +-- Check chunks count/sequence/length
  |     +-- Periodic checksum verification
  |
  +-- Scan stale UPLOADING/SCANNING jobs
  |     |
  |     +-- Check lease and current state
  |     +-- Retry verification or quarantine
  |
  +-- Find old orphan candidates
  |     |
  |     +-- Dry-run report
  |     +-- Confirm no active references/leases
  |     +-- Cleanup with audit
  |
  +-- Reconcile metadata/cross-system references
        |
        +-- Report mismatches
        +-- Queue manual/automatic safe repairs
~~~

Không chạy một job **deleteMany** toàn bucket dựa trên kết quả lookup đơn lẻ, vì một upload đang ghi có thể trông giống orphan trước khi file record được tạo.

### 21.4. Quarantine trước khi sửa

Khi phát hiện một READY file bị mismatch:

1. Đánh dấu catalog **CORRUPT** hoặc **UNAVAILABLE**.
2. Dừng phục vụ download mới.
3. Bảo toàn logs và metadata phục vụ điều tra.
4. Tìm source/backup đáng tin.
5. Verify restored bytes và metadata.
6. Publish phiên bản đã sửa theo workflow có điều kiện.

Không tự sửa âm thầm rồi xóa luôn bằng chứng, nhất là với tài liệu có giá trị pháp lý.

### 21.5. Rate limit reconciliation

Một file có 1.000 chunks và 1 triệu files tạo ra khối lượng I/O rất lớn nếu đọc toàn bộ bytes mỗi ngày.

Nên thiết kế:

- Batches và cursors có giới hạn.
- Ưu tiên assets mới, assets vừa được restore hoặc có sự cố.
- Checksum theo sampling và risk-based schedule nếu policy cho phép.
- Metrics về documents/bytes examined.
- Throttle theo tải MongoDB và giờ vận hành.

### 21.6. Alert theo bất biến nghiệp vụ

~~~text
Any READY asset with missing GridFS file:
  severity = critical

Checksum mismatch for published legal document:
  severity = critical; quarantine and investigate

Stale UPLOADING requests beyond max duration:
  severity = warning; review cleanup

Backup is older than RPO:
  severity = critical

Restore drill cannot complete within RTO:
  severity = reliability risk
~~~

Ngưỡng thực tế phụ thuộc SLO và mức độ nhạy cảm của nội dung. Không đánh đồng orphan candidates với một incident corrupt khi còn upload leases.

## 22. Runbook sự cố theo tình huống

### 22.1. Case A — Upload bị gián đoạn

~~~text
Client timeout during upload.
asset_catalog.status = UPLOADING.
Some chunks exist.
No GridFS file document.
~~~

Các bước:

1. Giữ asset ở trạng thái không public.
2. Xác minh uploadRequestId, fileId dự định và upload lease.
3. Nếu upload còn chạy, không cleanup.
4. Nếu lease hết hạn và không có writer, đánh dấu FAILED/RETRYABLE.
5. Khi retry, dùng cùng business request key để tránh duplicate catalog.
6. Cleanup chunks sau grace period và audit.

### 22.2. Case B — File document tồn tại, thiếu chunk

~~~text
assets.files.length = 600000
expected chunks = 3
actual chunks = 2
~~~

Các bước:

1. Mark asset UNAVAILABLE; không trả file đã cắt cụt.
2. Xác nhận index và query của chunks.
3. Kiểm tra logs, backup, restore và delete race.
4. Tìm backup có bytes hoàn chỉnh.
5. Verify checksum rồi phục hồi bằng phiên bản mới hoặc quy trình restore.
6. Chỉ publish READY khi đầy đủ.

### 22.3. Case C — Catalog trỏ file không tồn tại

~~~text
asset_catalog.status = READY
asset_catalog.currentFileId = F101
assets.files._id=F101 not found
~~~

Các bước:

1. Ẩn download với asset này.
2. Đối chiếu version history, audit và restore point.
3. Kiểm tra fileId có bị migration sai hay delete ngoài workflow không.
4. Tìm bản nội dung cũ/backup và verify hash.
5. Khôi phục pointer bằng conditional update, không tự chọn file chỉ cùng filename.

### 22.4. Case D — Sau restore, user cũ lại xem được file

~~~text
At T1: user-35 allowed.
At T2: permission revoked.
Restore snapshot T1.
~~~

Các bước:

1. Tạm ngừng downloads nhạy cảm hoặc áp deny policy tạm thời.
2. Reconcile revocations/ACL changes từ audit/recovery records phù hợp.
3. Kiểm tra tokens, caches, CDN đã được thu hồi.
4. Test quyền của user-35 trước khi mở dịch vụ.
5. Ghi lại kiểm soát và thời điểm cutover.

### 22.5. Case E — SHA-256 mismatch nhưng chunk count đúng

~~~text
expectedChunks = actualChunks
sumChunkBytes = assets.files.length
SHA-256 differs
~~~

Các bước:

1. Không coi đây là success chỉ vì counts khớp.
2. Kiểm tra expected digest được tạo từ nguồn nào.
3. Xác minh lại từ bytes đọc trong GridFS.
4. So với bản gốc/backup đáng tin.
5. Quarantine và bảo toàn bằng chứng về corruption/tampering.

### 22.6. Case F — Cleaner gây hỏng upload đang chạy

~~~text
Uploader writes chunk n=0.
Cleaner sees chunks without files record.
Cleaner removes chunks.
Uploader writes n=1,2 and file document.
Download now fails.
~~~

Khắc phục:

1. Ngừng cleaner và các uploads bị ảnh hưởng nếu cần.
2. Mark file versions thiếu chunks là CORRUPT/UNAVAILABLE.
3. Tìm source để reupload.
4. Thêm **upload lease, grace period và explicit upload job state** trước khi bật cleaner lại.
5. Thử nghiệm concurrency trước production.

### 22.7. Case G — Backup chỉ chứa một collection

~~~text
Backup assets.files only.
No assets.chunks.
~~~

Không thể tự tạo nội dung từ metadata.length và filename. Cần tìm backup khác chứa chunks tại recovery point phù hợp, hoặc yêu cầu source reupload/xử lý mất dữ liệu. Cập nhật runbook để backup cả bucket và business references.

### 22.8. Case H — Sau restore, index unique chunks bị mất

Nếu index **{files_id:1,n:1} unique** không còn:

1. Dừng writes có nguy cơ tạo duplicate n khi cần.
2. Kiểm tra dữ liệu hiện tại có duplicates không.
3. Khắc phục duplicates qua quy trình tin cậy, không tự chọn một chunk tùy ý.
4. Rebuild unique index.
5. Chạy integrity verification/reconciliation cho dữ liệu liên quan.

Chỉ tạo index lại có thể thất bại nếu dữ liệu đã có duplicate keys. Không xóa duplicate chunks tùy ý khi chưa xác định bytes đúng.

### 22.9. Case I — Backup thành công nhưng không còn khóa giải mã

~~~text
Backup archive restored
GridFS files/chunks available
Encryption key missing
File bytes cannot be decrypted
~~~

Với ứng dụng mã hóa file trước GridFS, cần đưa **key management** vào DR plan. Một backup chỉ chứa ciphertext không đáp ứng business recovery nếu khóa tương ứng không thể phục hồi.

Không lưu cùng một bản backup khóa ở nơi không kiểm soát với dữ liệu nhạy cảm; xây cơ chế escrow/KMS recovery có phân quyền.

## 23. Bảng lựa chọn giải pháp theo nhu cầu

| Yêu cầu | Giải pháp gợi ý | Không nên nhầm với |
|---|---|---|
| Quyền đọc theo từng file | Application ACL/tenant policy, xác minh catalog trước download. | MongoDB find trên collection. |
| Phân quyền theo tenant ở mức hạ tầng | Bucket/database tách riêng nếu cần DB-level isolation. | Chỉ thêm metadata.tenantId trong một bucket chung. |
| File lớn hơn BSON limit | GridFS split bytes thành chunks. | Một BSON document 16 MiB. |
| Upload không lộ file dở dang | State machine và chỉ publish READY sau verify. | assets.files tồn tại = công khai. |
| Thay file không gián đoạn | Upload fileId mới, atomic pointer swap, delayed cleanup. | Ghi đè chunks tại chỗ. |
| Backup không mất liên kết | Point-in-time snapshot của catalog + files + chunks. | Dump hai collections ở hai thời điểm. |
| Restore trên sharded cluster | Coordinated sharded backup/managed PIT. | Ghép snapshots từng shard không đồng bộ. |
| Kiểm tra dữ liệu đầy đủ | Sequence/chunk length/total bytes + SHA-256. | Chỉ đếm files documents. |
| Dọn orphan chunks | Lease + grace + reconciliation + audited cleanup. | Xóa tất cả chunks thiếu files record ngay. |
| Tuân thủ xóa dữ liệu | Live deletion + backup retention/key policy. | Chỉ bucket.delete(fileId). |
| Theo dõi sự cố | Metrics/checkpoints/audit/restore drills. | Chỉ quan sát CPU hoặc số file. |

## 24. Quy trình kiểm thử một GridFS bucket trong môi trường lab

Đây là một kế hoạch thực hành **không đụng tới production**.

### 24.1. Chuẩn bị

1. Kết nối MongoDB lab với database **gridfs_security_lab**.
2. Chọn GridFS bucket **assets**.
3. Tạo file nhỏ có nội dung đã biết.
4. Upload bằng Java GridFSBucket hoặc Spring Data GridFsTemplate.
5. Lưu file ID thực mà driver trả về.

### 24.2. Xem metadata

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").find(
  {},
  {
    filename: 1,
    length: 1,
    chunkSize: 1,
    uploadDate: 1,
    metadata: 1
  }
).limit(20);
~~~

Kiểm tra mỗi completed upload có file document; metadata tenantId/applicationFileId đến từ service; không công bố file trước catalog READY.

### 24.3. Xem chunks

~~~javascript
const id = ObjectId("65a000000000000000000001");

db.getCollection("assets.chunks").find(
  { files_id: id },
  { _id: 0, files_id: 1, n: 1 }
).sort({ n: 1 });
~~~

Thay **id** bằng file ID thật từ upload. Nếu file rỗng, chunk count có thể bằng 0.

### 24.4. Kiểm tra quyền trong ứng dụng

Tạo hai tenants/users:

~~~text
Tenant A:
  User A owns DOC-100.

Tenant B:
  User B owns DOC-200.
~~~

Test:

1. A download DOC-100 -> được phép nếu READY.
2. A download DOC-200 -> bị từ chối.
3. B download DOC-100 -> bị từ chối.
4. A thử gửi fileId trực tiếp -> API vẫn kiểm tra quyền.
5. User không đăng nhập -> bị từ chối theo policy.

### 24.5. Thử upload dở dang

Trên môi trường test và qua mock/fault injection:

1. Bắt đầu upload nhiều chunks.
2. Ngắt stream giữa chừng.
3. Quan sát catalog không trở thành READY.
4. Worker không xóa chunks khi upload còn lease active.
5. Khi lease hết hạn, cleanup theo protocol.

Không chủ động làm hỏng một GridFS bucket production để thử nghiệp vụ.

### 24.6. Thử backup/restore

1. Upload một file nhỏ, một file lớn nhiều chunks và một file zero-byte nếu policy cho phép.
2. Lưu expected size/SHA-256 từ bytes ban đầu.
3. Thực hiện backup consistent theo topology.
4. Restore vào database lab cách ly.
5. Xác minh files/chunks/indexes/catalog.
6. Download và so SHA-256.
7. Kiểm tra ACL theo tenant.
8. Thử file ở trạng thái SCANNING/FAILED không bị lộ.

### 24.7. Thử lỗi kết nối giữa lúc thay phiên bản

1. DOC-100 đang trỏ F100.
2. Upload F101.
3. Giả lập crash trước pointer swap: DOC-100 vẫn phục vụ F100.
4. Giả lập crash sau pointer swap nhưng trước cleanup: DOC-100 phục vụ F101, F100 còn và được cleanup sau.
5. Kiểm tra không có kết quả nửa file F100 + nửa file F101.

### 24.8. Thử tải đồng thời với xóa

1. Reader bắt đầu download F100.
2. User yêu cầu delete DOC-100.
3. Service chặn request tải mới sau chuyển trạng thái.
4. Tùy policy, stream cũ được hoàn tất hoặc chủ động dừng.
5. Cleanup chunks chỉ xảy ra khi phù hợp lease/grace/retention.

Kỳ vọng phải được xác định trong business requirements trước khi test.

## 25. Những sai lầm thường gặp

### 25.1. “GridFS là một document lớn nên upload nguyên tử”

**Sai.** GridFS chia file thành nhiều documents ở files/chunks, không có atomic commit của toàn bộ bytes và metadata như một document write duy nhất.

### 25.2. “Có assets.files nghĩa là chunks đầy đủ và nguyên vẹn”

**Không đủ.** Cần kiểm tra chunks count, n sequence, total bytes và checksum khi yêu cầu integrity. Backup/restore sai hoặc xóa đồng thời có thể khiến metadata và binary khác nhau.

### 25.3. “MongoDB RBAC đã đủ cho user chỉ xem file mình sở hữu”

**Sai khi bucket dùng chung.** DB roles giới hạn collection/actions, không tự lọc từng GridFS file theo metadata.ownerId. Application authorization bắt buộc.

### 25.4. “ObjectId không đoán được nên không cần kiểm tra quyền”

**Sai.** ID không phải authorization token. Khi bị lộ qua logs, browser history, email hoặc API response, file vẫn phải được bảo vệ.

### 25.5. “Chỉ cần backup assets.chunks”

**Sai.** Không có files record thì thiếu length, chunkSize, filename và linkage. Cũng cần business catalog và ACL.

### 25.6. “Dump assets.files trước rồi assets.chunks là một backup nhất quán”

**Sai khi có writes đồng thời.** Hai collections được dump tại những thời điểm khác nhau có thể dẫn đến file document không có đủ chunks hoặc orphan chunks.

### 25.7. “mongodump --oplog áp dụng như nhau cho standalone, replica set và sharded cluster”

**Sai.** --oplog có điều kiện và giới hạn theo topology/cách dump. Với sharded cluster, cần backup có coordination across shards hoặc managed PIT.

### 25.8. “Backup archive đọc được tức dữ liệu đã phục hồi thành công”

**Sai.** Cần restore drill, xác nhận indexes, ACL, catalog links, sample bytes và checksum. Nếu ứng dụng mã hóa riêng, cần phục hồi cả khóa.

### 25.9. “Chỉ cần đếm đúng số chunks”

**Sai.** Có thể thiếu n=1 nhưng có n=3; count không tự chứng minh sequence liên tục. Chunks cùng kích thước vẫn có thể chứa bytes khác.

### 25.10. “Nếu checksum không khớp thì sửa metadata.sha256”

**Nguy hiểm.** Có thể che hỏng dữ liệu. Phải xác định expected digest từ nguồn tin cậy và khôi phục bytes gốc hoặc version mới đúng.

### 25.11. “Xóa tất cả chunks thiếu files record ngay lập tức”

**Nguy hiểm.** Upload đang chạy có thể đã ghi chunks nhưng chưa tạo files record. Cần lease/grace/reconciliation.

### 25.12. “Xóa GridFS file tức đã xóa mọi business metadata”

**Sai.** GridFSBucket.delete không tự cập nhật asset_catalog, audit, external caches và backups. Cần lifecycle delete.

### 25.13. “Có thể ghi đè chunks để cập nhật phiên bản”

**Không nên.** Reader có thể gặp nội dung pha trộn hoặc mismatch. Tạo file ID mới, verify, rồi atomic swap pointer.

### 25.14. “metadata.mediaType là bằng chứng định dạng file”

**Sai.** MIME có thể do client khai báo. Cần content sniff/scan/parser khi có policy bảo mật.

### 25.15. “Restore backup cũ không ảnh hưởng quyền truy cập”

**Sai.** ACL trong snapshot có thể cũ hơn thay đổi thu hồi quyền. Cần policy reconciliation trước khi mở downloads.

### 25.16. “SHA-256 giống chữ ký số”

**Không hoàn toàn.** Digest chỉ giúp so bytes nếu expected hash được tin. Chữ ký/HMAC cần quản lý khóa để xác minh nguồn và chống chỉnh sửa digest.

### 25.17. “Mã hóa at rest làm application ACL trở nên không cần thiết”

**Sai.** DB credentials hợp lệ vẫn có thể đọc dữ liệu theo quyền của tài khoản. AuthN/AuthZ của API và key management có chức năng khác.

### 25.18. “Đổi trạng thái READY trong hai documents là một bước nguyên tử”

**Sai.** Hai updates thuộc hai documents riêng không tự nguyên tử cùng nhau trong GridFS workflow. Chọn **một authoritative publish pointer/state** và xử lý các bản sao metadata bằng eventual consistency/reconciliation.

### 25.19. “Xóa live file là xóa cả backup”

**Sai.** Backups có retention riêng. Quy trình xóa dữ liệu nhạy cảm phải xét backup lifecycle, archive và crypto key policy.

### 25.20. “Một lần kiểm tra quyền đầu stream bảo đảm revoke lập tức”

**Không mặc định.** Download đang chạy có thể tiếp tục nếu ứng dụng không có cancellation/revocation mechanism.

### 25.21. “File được upload thành công thì có thể phục vụ ngay”

**Chưa chắc.** Có thể cần malware scan, PDF validation, size/hash verification, tenant ownership và business approval trước khi publish.

### 25.22. “Tên file là khóa duy nhất để tải”

**Sai.** Nhiều tenants/versions có thể cùng filename. Dùng ID business đã authorize và GridFS file ID cho phiên bản tương ứng.

## 26. Bài thực hành

### Bài 1 — Phân biệt metadata và nội dung

Vẽ sơ đồ liên kết:

~~~text
asset_catalog -> assets.files -> assets.chunks
~~~

Giải thích field nào nối các tầng với nhau và điều gì xảy ra nếu thiếu một tầng.

### Bài 2 — Số lượng chunks

Một file có:

~~~text
length = 600000 bytes
chunkSize = 261120 bytes
~~~

Tính expectedChunks và byte length của từng chunk. Giải thích vai trò của n=0,1,2.

### Bài 3 — File rỗng

Một file length=0 có bao nhiêu chunks? Vì sao business có thể từ chối file rỗng dù GridFS có thể biểu diễn?

### Bài 4 — Unique index

Tạo unique index **{files_id:1,n:1}** trên assets.chunks. Index này ngăn được duplicate nào và không ngăn được missing chunks nào?

### Bài 5 — MongoDB RBAC

Viết custom role chỉ có quyền **find** trên assets.files và assets.chunks. Giải thích tại sao role này không bảo vệ từng ownerId trong bucket dùng chung.

### Bài 6 — Upload permission

Một service chỉ upload và đọc metadata nhưng không có quyền xóa file. Liệt kê actions có thể cần trên files/chunks và cách provision indexes riêng.

### Bài 7 — IDOR

API có endpoint **GET /files/{fileId}** và download trực tiếp theo ObjectId. Hãy mô tả cách attacker biết ID người khác có thể tải file và cách sửa bằng business ACL.

### Bài 8 — Tenant mismatch

Catalog của tenant-a trỏ tới GridFS file metadata.tenantId=tenant-b. Viết quy trình download để từ chối và phát cảnh báo thay vì trả file.

### Bài 9 — State machine

Thiết kế các trạng thái **UPLOADING, SCANNING, READY, REJECTED, DELETING, DELETED**. Với mỗi trạng thái, quyết định API có cho download không.

### Bài 10 — Idempotency

Client upload với requestId REQ-100, server ghi xong GridFS nhưng response bị mất. Retry cùng requestId cần xử lý thế nào để không tạo hai business assets?

### Bài 11 — Failure trước khi publish

GridFS upload F100 thành công nhưng process crash trước khi asset_catalog thành READY. Đề xuất recovery worker kiểm tra metadata/fileId và publish hoặc cleanup an toàn.

### Bài 12 — Thay phiên bản

DOC-100 đang trỏ F100. Upload F101 rồi dùng updateOne với điều kiện version=3 để đổi pointer. Nếu matchedCount=0, service phải xử lý sao?

### Bài 13 — Download đồng thời xóa

Một reader đã bắt đầu tải file 1 GB, admin yêu cầu xóa. Thiết kế policy về request mới, stream đang chạy, grace period và thời điểm delete chunks.

### Bài 14 — Backup không đồng nhất

Tạo timeline:

~~~text
T1: dump assets.chunks
T2: upload new file completes
T3: dump assets.files
~~~

Giải thích một file có thể xuất hiện trong metadata nhưng thiếu chunks sau restore.

### Bài 15 — Mongodump và oplog

Trong replica set, giải thích vì sao **mongodump --oplog** được dùng khi cần consistent backup trong điều kiện hỗ trợ. Vì sao không thể áp dụng nguyên mẫu backup này cho mọi sharded cluster?

### Bài 16 — Backup scope

Một ứng dụng có **assets.files**, **assets.chunks**, **asset_catalog**, **asset_permissions**. Liệt kê collections cần backup nhất quán và những hậu quả nếu bỏ sót asset_permissions.

### Bài 17 — Restore và old ACL

User bị thu hồi quyền ở T2 nhưng backup ở T1 còn cho quyền. Thiết kế bước policy reconciliation trước khi mở lại download.

### Bài 18 — Kiểm tra chunks bằng aggregation

Viết query dùng **$binarySize**, **$group** và files_id để tính chunkCount, totalBytes, minN, maxN. Tại sao query đó vẫn chưa thay thế checksum?

### Bài 19 — Orphan chunks

Viết $lookup tìm files_id có chunks nhưng không có files document. Đặt điều kiện nào trước khi cleanup để không xóa upload đang chạy?

### Bài 20 — Ready asset không có GridFS file

Viết aggregation từ asset_catalog READY lookup assets.files theo currentFileId và trả danh sách thiếu file. Quy trình xử lý recovery nào phù hợp?

### Bài 21 — Checksum

Thiết kế Java service đọc lại file GridFS bằng stream và tính SHA-256. So với expected digest từ nguồn tin cậy. Điều gì xảy ra nếu chunks đủ số lượng nhưng một byte bị thay đổi?

### Bài 22 — Hệ thống quét malware

Upload file có tên **report.pdf** nhưng bytes không phải PDF. Thiết kế bước validation trước khi chuyển READY. Vì sao không tin Content-Type user gửi?

### Bài 23 — Mã hóa file ở tầng ứng dụng

Một doanh nghiệp mã hóa mỗi file với khóa riêng trước khi lưu GridFS. Khi restore backup nhưng mất khóa, chuyện gì xảy ra? Cần bổ sung gì vào DR plan?

### Bài 24 — Spring Data GridFsTemplate

Viết Spring Data code dùng **GridFsTemplate.store()** với custom metadata chứa tenantId, assetId, status=SCANNING. Mô tả cách query GridFS file và trả InputStream sau bước authorization.

### Bài 25 — Quyền backup operator

Tại sao tài khoản chạy mongorestore không nên là MongoDB credential của một public API server? Đề xuất phân tách runtime/provisioning/backup/restore roles.

### Bài 26 — Kiểm tra restore định kỳ

Thiết kế một restore drill có:

~~~text
Một file nhỏ
Một file lớn nhiều chunks
Một file rỗng nếu policy cho phép
Một file private tenant-a
Một file private tenant-b
~~~

Test cả checksum và access control sau restore.

### Bài 27 — TTL và retention của backups

Một người dùng yêu cầu xóa file. File đã bị delete khỏi live GridFS nhưng backup giữ 90 ngày. Viết cách giải thích retention và lựa chọn policy tuân thủ.

### Bài 28 — Monitoring

Chọn tối thiểu năm metrics phát hiện upload lỗi, orphan candidates, checksum mismatch, stale READY links và backup quá hạn RPO.

### Bài 29 — Concurrent cleanup

Một cleaner thấy chunks chưa có files document và định xóa ngay. Viết pseudocode với upload lease + grace period + reconciliation để tránh hủy upload còn hoạt động.

### Bài 30 — Multi-tenant architecture

So sánh:

- Một bucket assets dùng chung, bảo vệ qua API.
- Mỗi tenant có bucket/database riêng.

Đánh giá security isolation, số collections/indexes, backup, operational complexity và những trường hợp phù hợp.

## 27. Câu hỏi ôn tập

1. GridFS chia một file thành hai collections nào?
2. Prefix mặc định của GridFS bucket là gì? Nếu bucket tên assets thì hai collections tên gì?
3. fs.files._id và fs.chunks.files_id liên hệ thế nào?
4. Field n trong chunks có vai trò gì?
5. Vì sao index unique trên files_id+n không đủ bảo đảm không thiếu chunk?
6. Mặc định một chunk GridFS thường có kích thước bao nhiêu?
7. Với length=0, GridFS file cần bao nhiêu chunks?
8. Vì sao không thể coi một file GridFS là một document write nguyên tử?
9. Các chunks tạm thời chưa có files document có luôn là dữ liệu hỏng không?
10. GridFS có hỗ trợ multi-document transaction như một cơ chế commit nguyên tử toàn upload không?
11. MongoDB RBAC bảo vệ collection khác với ACL từng file như thế nào?
12. Vì sao ObjectId không phải authorization token?
13. Tại sao API phải kiểm tra tenant, owner và trạng thái trước khi download?
14. Khi filename giống nhau, GridFS file ID và business asset ID khác nhau ra sao?
15. asset_catalog cần giữ những thông tin nào không nên chỉ phụ thuộc vào GridFS metadata?
16. Trạng thái READY nên được công bố lúc nào?
17. Vì sao cần tách UPLOADING, SCANNING và READY?
18. Idempotency key giải quyết rủi ro gì khi client retry upload?
19. Upload thành công nhưng crash trước publish để lại trạng thái nào?
20. Thay file theo kiểu pointer swap có lợi ích gì so với cập nhật chunks tại chỗ?
21. Khi delete GridFS file, asset_catalog có được driver tự cập nhật không?
22. Khi thu hồi quyền trong lúc stream đang mở, những chính sách nào cần xác định?
23. Vì sao chỉ sao lưu fs.files hoặc fs.chunks là không đủ?
24. Nếu backup hai collections ở hai thời điểm khác nhau, điều gì có thể xảy ra?
25. mongodump --oplog có giới hạn gì theo topology/cách dump?
26. Vì sao sharded cluster cần backup có coordination hoặc managed snapshot?
27. Một point-in-time snapshot có thể chứa chunks đang upload dở dang mà vẫn hợp lệ không?
28. Restore có cần giữ nguyên files._id, chunks.files_id và n không?
29. Sau restore, vì sao phải kiểm tra cả ACL và các revocations?
30. RPO và RTO được hiểu thế nào trong hệ thống file?
31. expectedChunks được tính từ length và chunkSize bằng công thức nào?
32. Vì sao tổng chunk bytes đúng vẫn chưa chứng minh nội dung đúng?
33. SHA-256 khác metadata length và chữ ký số ra sao?
34. Vì sao không sửa length để che việc mất chunks?
35. Orphan chunks khác unreferenced GridFS files thế nào?
36. Tại sao không được xóa orphan candidates khi upload còn lease active?
37. Cleanup worker cần những điều kiện nào trước khi xóa bytes?
38. Vì sao tên file không được nối thẳng vào filesystem path?
39. Làm thế nào bảo vệ việc trả file HTML/PDF không tin cậy qua trình duyệt?
40. Java GridFSBucket và Spring GridFsTemplate có thể dùng để upload/download theo stream thế nào?
41. Tại sao một backup có bytes nhưng không có encryption key có thể vô dụng?
42. Những metrics nào giúp phát hiện READY files bị thiếu nội dung?
43. Khi một catalog record trỏ file của tenant khác, dịch vụ phải làm gì?
44. Có thể kiểm thử restore thành công mà không tải lại ít nhất một số file mẫu không?
45. Những điều kiện nào phải đạt trước khi mở lại download sau khôi phục?

## 28. Checklist vận hành trước khi đưa GridFS vào production

### 28.1. Trước khi tạo service

- [ ] Xác định bucket/database name, tránh nhầm **fs** và **assets**.
- [ ] Xác định giới hạn file size, file types, quota và timeout.
- [ ] Provision indexes cần thiết, nhất là **unique(files_id,n)**.
- [ ] Tách quyền runtime với provisioning/backup/restore.
- [ ] Thiết kế business asset ID, tenant ID và owner/sharing policy.
- [ ] Chọn nơi chứa authoritative metadata/state.
- [ ] Định nghĩa uploadRequestId và idempotency.
- [ ] Định nghĩa SHA-256/content validation và scanner.
- [ ] Xác định cơ chế mã hóa dữ liệu/backup và key lifecycle.

### 28.2. Trước khi công bố file

- [ ] Upload stream hoàn tất theo GridFS driver.
- [ ] File ID liên kết đúng business asset/tenant.
- [ ] Kích thước file trong giới hạn.
- [ ] Nội dung có thể đọc lại và xác minh khi policy yêu cầu.
- [ ] Checksum/malware/media-type checks đạt yêu cầu.
- [ ] Catalog được cập nhật READY bằng conditional single-document update.
- [ ] File chưa READY không được phép download.
- [ ] Có audit/correlation ID cho thao tác upload.

### 28.3. Trước khi phục vụ download

- [ ] Caller được xác thực.
- [ ] Tenant/owner/share ACL được kiểm tra.
- [ ] Asset đang ở trạng thái READY.
- [ ] currentFileId đúng phiên bản, GridFS metadata không mismatch.
- [ ] Response headers được escape/sanitize an toàn.
- [ ] Stream có timeout, cancellation và cleanup.
- [ ] Quy tắc khi đang delete/revoke được xác định.
- [ ] Không log binary nội dung hoặc metadata nhạy cảm.

### 28.4. Trước khi xóa

- [ ] Caller có quyền delete.
- [ ] File không bị legal hold/retention policy cấm xóa.
- [ ] Catalog không còn công bố cho requests mới.
- [ ] Kiểm tra active references và in-flight readers theo policy.
- [ ] Cleanup worker có lease/grace/audit.
- [ ] File/chunks và catalog được reconcile sau delete.
- [ ] Backup retention/data deletion policy được xem xét.

### 28.5. Trước khi tuyên bố backup phục hồi được

- [ ] assets.files, assets.chunks và catalog nằm trong phạm vi backup.
- [ ] Có một recovery point nhất quán theo topology.
- [ ] Backup được mã hóa và lưu ở nơi có quyền kiểm soát.
- [ ] Có backup của cấu hình và khóa cần thiết.
- [ ] Đã thực hiện restore drill trong môi trường cách ly.
- [ ] Indexes được verify sau restore.
- [ ] Đã thử download files nhỏ/lớn và so checksum.
- [ ] Đã kiểm tra READY links, orphan candidates và missing chunks.
- [ ] Đã đối soát ACL/revocations và external integrations.
- [ ] RPO và RTO đạt yêu cầu.

## 29. Tổng kết: ba bất biến cần được bảo vệ

Khi dùng GridFS, không nên chỉ đặt câu hỏi “MongoDB đã lưu được file chưa?”. Một thiết kế an toàn phải bảo đảm ba bất biến:

### Bất biến 1 — Đúng quyền

~~~text
CanRead(user, asset)
  = authenticated
    AND authorized by tenant/owner/share policy
    AND asset is READY
    AND file is the verified current version
~~~

MongoDB RBAC bảo vệ phạm vi database/collection và actions; **application ACL bảo vệ từng file**. Không dùng ObjectId hoặc filename thay quyền truy cập.

### Bất biến 2 — Đúng nội dung

~~~text
ValidGridFSFile(file)
  = files record exists
    AND expected chunks exist
    AND chunk numbers are contiguous
    AND total bytes == files.length
    AND checksum matches trusted digest (when required)
~~~

Không thể xác nhận toàn vẹn chỉ bằng việc nhìn thấy file document hoặc đếm chunks.

### Bất biến 3 — Phục hồi cùng một trạng thái

~~~text
ConsistentRecoveryPoint(T)
  = business catalog at T
    + GridFS file records at T
    + GridFS chunks at T
    + relevant access policies at T
    + recovery procedure for in-progress workflows
~~~

Backup cần nhất quán theo thời điểm và topology, đặc biệt khi có uploads/deletes xảy ra đồng thời. Restore đúng bytes nhưng sai liên kết hoặc sai quyền vẫn là restore chưa an toàn.

### Những nguyên tắc cần nhớ

1. **GridFS lưu file ở nhiều documents**; không mặc định một file được upload/xóa atomically trong một multi-document transaction.
2. **Bucket gồm files và chunks**; phải backup/restore cả hai cùng metadata nghiệp vụ.
3. **MongoDB RBAC không tự lọc từng file** trong bucket dùng chung; service phải thực thi ACL.
4. **Chỉ công bố sau verify** qua một trạng thái hoặc pointer authoritative được cập nhật có điều kiện.
5. **Sử dụng version mới khi thay nội dung**, giữ file cũ đủ lâu cho reads/rollback rồi cleanup an toàn.
6. **Upload dở dang có thể để lại chunks chưa có files record**; không xóa khi chưa xác minh upload đã kết thúc.
7. **Orphan/missing chunks cần reconciliation**, không sửa bừa length hoặc binary data.
8. **Checksum từ bytes thật** là phép kiểm tra integrity quan trọng; digest phải có nguồn tin cậy.
9. **Backup/restore cần point-in-time consistency**, không phải hai lệnh dump tùy ý chạy nối tiếp.
10. **Quyền và khóa mã hóa phải được khôi phục đúng**, bao gồm revocations sau recovery point theo chính sách.
11. **Java GridFSBucket và Spring Data GridFsTemplate** hỗ trợ streaming API, còn business lifecycle/recovery vẫn là trách nhiệm ứng dụng.
12. **DR drill, audit, metrics và runbook** là phần của tính đúng đắn, không phải công việc chỉ làm khi có sự cố.

### Tài liệu tham khảo chính thức

- [MongoDB GridFS — tổng quan và schema](https://www.mongodb.com/docs/manual/core/gridfs/) — files/chunks, indexes, upload/download, giới hạn giao dịch.
- [MongoDB Database Tools: mongodump](https://www.mongodb.com/docs/database-tools/mongodump/) — BSON backup, --oplog và các ràng buộc.
- [MongoDB Database Tools: mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/) — restore và oplog replay.
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/) — backup strategies theo topology.
- [MongoDB Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/) — quyền và nguyên tắc least privilege.
- [MongoDB Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/) — find, insert, update, remove, createIndex và các actions.
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — bảo vệ uniqueness của chunk sequence.
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/) — GridFSBucket, uploadFromStream, downloadToStream và delete.
- [Spring Data MongoDB — GridFS](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html) — GridFsTemplate, GridFsResource và template APIs.
- [MongoDB TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/) — bảo vệ kết nối tới MongoDB.
- [MongoDB Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/) — cơ chế bảo vệ dữ liệu lưu trữ.

Hãy thiết kế GridFS như một **hệ thống quản lý vòng đời nội dung**, không chỉ là nơi lưu binary. Một file chỉ thực sự sẵn sàng phục vụ khi **đúng người được quyền đọc, đúng bytes được xác minh và có khả năng khôi phục metadata cùng nội dung về một trạng thái nhất quán**.










