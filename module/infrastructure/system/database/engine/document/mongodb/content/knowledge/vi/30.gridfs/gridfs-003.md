# Tải lên, tải xuống theo luồng và metadata của tệp với MongoDB GridFS

## 1. GridFS giải quyết bài toán gì?

MongoDB thường lưu một thực thể nghiệp vụ dưới dạng **BSON document**. Một document có giới hạn kích thước **16 MiB**. Khi ứng dụng cần quản lý các tệp như ảnh gốc, PDF nhiều trang, video, tệp sao lưu, báo cáo xuất dữ liệu hoặc tài liệu người dùng tải lên, không thể cứ đưa toàn bộ dữ liệu nhị phân lớn vào một field `BinData` của một document.

**GridFS** là một đặc tả và bộ API driver giúp chia tệp thành nhiều **chunk** nhỏ, ghi chúng vào MongoDB và ghép lại khi tải xuống. Dữ liệu nhị phân và metadata được lưu trong hai collection riêng, cùng nằm trong một **bucket**.

Ví dụ hệ thống lưu tài liệu hợp đồng:

- Người dùng tải lên PDF có dung lượng 70 MiB.
- Server không đọc toàn bộ 70 MiB vào RAM.
- Java driver đọc lần lượt từ `InputStream`, chia thành các chunks và ghi vào GridFS.
- Một document metadata mô tả file ID, tên tệp, kích thước, thời điểm tải lên và thông tin nghiệp vụ.
- Khi tải về, server đọc các chunks theo thứ tự rồi ghi vào `OutputStream` của HTTP response.
- Bộ nhớ ứng dụng có thể giữ ở mức gần kích thước buffer/chunk, thay vì tăng theo kích thước tệp.

> **Điểm cốt lõi:** GridFS cho phép lưu và phục hồi một tệp lớn qua **nhiều documents**, còn streaming cho phép ứng dụng **đọc/ghi từng phần** thay vì đưa cả tệp vào RAM.

### 1.1. Khi nào nên dùng GridFS?

GridFS phù hợp khi:

1. Tệp vượt 16 MiB.
2. Muốn tải lên/tải xuống theo luồng để tránh giữ toàn bộ tệp trong memory.
3. Muốn quản lý nội dung nhị phân và metadata cùng hệ MongoDB.
4. Muốn tận dụng khả năng backup, replication, quyền truy cập và hạ tầng MongoDB.
5. Cần đọc những phần của tệp lớn theo quy trình được driver hỗ trợ.
6. Số tệp lớn khiến việc quản lý trực tiếp qua thư mục hệ điều hành khó khăn.

### 1.2. Khi nào không nên dùng?

Cân nhắc lựa chọn khác nếu:

- Mọi tệp đều nhỏ hơn 16 MiB và chỉ cần lưu nhị phân đơn giản trong một document `BinData`.
- Cần **cập nhật toàn bộ nội dung tệp một cách nguyên tử**. GridFS không hỗ trợ multi-document transactions.
- Hệ thống đã có object storage/CDN phù hợp cho ảnh, video, tệp tĩnh khổng lồ; có thể chỉ cần MongoDB giữ metadata và object key.
- Ứng dụng cần các tính năng chuyên biệt như multipart upload của object storage, lifecycle transition sang cold storage, edge caching hoặc video transcoding.
- Tệp là dữ liệu tạm rất nhỏ, không có yêu cầu persistence như một tài sản nghiệp vụ.

GridFS không phải là “object storage thay thế tất cả hệ thống khác”. Cần đánh giá latency, backup cost, replication traffic, CDN, durability, truy cập Internet và vận hành dữ liệu.

---

## 2. Bucket, files và chunks: sơ đồ kiến trúc

Một bucket GridFS có tên mặc định `fs`, gồm hai collections:

```text
Database: files_demo

GridFS bucket "fs"
   |
   +-- fs.files
   |     1 document / 1 phiên bản tệp hoàn chỉnh
   |     _id, filename, length, chunkSize, uploadDate, metadata
   |
   +-- fs.chunks
         nhiều documents / 1 tệp
         _id, files_id, n, data
```

Nếu đặt tên bucket là `attachments` thì cặp collection thành:

```text
attachments.files
attachments.chunks
```

**Bucket** là cách driver tổ chức hai collections. Không phải một kiểu collection đặc biệt của MongoDB server; người dùng vẫn nhìn thấy các collections bằng `mongosh`.

### 2.1. Luồng tải lên

```text
HTTP request / local file / network source
                    |
                    v
               InputStream
                    |
                    v
           GridFSBucket upload
                    |
              chia thành chunks
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
    chunk n=0   chunk n=1   chunk n=2 ...
        |           |           |
        +-----------+-----------+
                    |
                    v
               fs.chunks
                    |
                    v
          ghi document fs.files
          sau khi upload hoàn tất
                    |
                    v
                file ID
```

### 2.2. Luồng tải xuống

```text
Client yêu cầu fileId
           |
           v
    GridFSBucket
           |
           +--> đọc fs.files metadata
           |
           +--> đọc fs.chunks theo n tăng dần
                     |
                     v
                GridFSDownloadStream
                     |
                     v
                 OutputStream
                     |
                     v
              HTTP response / file
```

Java driver thực hiện những việc chia/ghép chunks. **Không cần tự split bytes thành BSON documents** ở code ứng dụng thông thường.

---

## 3. Cấu trúc document trong fs.files

Một document metadata minh họa:

```javascript
{
  _id: ObjectId("6917a0000000000000000001"),
  length: NumberLong("73400320"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  filename: "hop-dong.pdf",
  metadata: {
    tenantId: "TENANT-001",
    documentId: "DOC-100",
    originalFilename: "Hợp đồng thuê nhà.pdf",
    contentType: "application/pdf",
    uploadedBy: "USER-42",
    sha256: "f2ca1bb6c7e907d06dafe4687e579fce...",
    lifecycle: "READY",
    schemaVersion: 1
  }
}
```

Đây là cấu trúc ví dụ, không phải record thật. Trường `sha256` đã rút gọn cho dễ đọc; checksum SHA-256 thực tế ở dạng hex gồm 64 ký tự.

| Field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `_id` | Định danh duy nhất của phiên bản file | Driver thường sinh `ObjectId`, có thể dùng kiểu BSON ID tương thích theo API. |
| `filename` | Tên hiển thị/tên lưu trong GridFS | **Không unique** theo mặc định; nhiều file có thể trùng tên. |
| `length` | Kích thước dữ liệu tệp tính bằng **bytes** | Long/int64, không phải số lượng documents. |
| `chunkSize` | Kích thước mỗi chunk, trừ chunk cuối | Mặc định **255 KiB = 261.120 bytes**. |
| `uploadDate` | Ngày upload, kiểu BSON Date | Thời gian metadata, không phải version ID bền vững. |
| `metadata` | Thông tin do ứng dụng định nghĩa | Có thể là document chứa tenant, MIME, checksum, quyền, mô tả. |
| `md5` | Checksum cũ | **Deprecated**, không dựa vào để bảo mật hoặc toàn vẹn. |
| `contentType` top-level | MIME field cũ | **Deprecated**; dùng `metadata.contentType`. |
| `aliases` top-level | Bí danh cũ | **Deprecated**; dùng `metadata`. |

### 3.1. File ID khác filename

Với hai lần upload:

```text
ID = A, filename = "invoice.pdf", uploadDate = 10:00
ID = B, filename = "invoice.pdf", uploadDate = 11:00
```

Đó là **hai phiên bản độc lập**, không phải B tự động ghi đè nội dung A.

Nếu API cần “đúng file mà người dùng được phép xem”, tốt nhất dùng **ID được lưu trong document nghiệp vụ** và xác nhận quyền tương ứng, không chỉ dựa vào tên file.

### 3.2. Metadata không tự xác minh giá trị

Có thể lưu:

```javascript
metadata: {
  contentType: "application/pdf"
}
```

nhưng GridFS **không kiểm tra tệp thật có phải PDF hay không** chỉ vì bạn ghi chuỗi ấy. Xác minh MIME, file signature, malware và kích thước là trách nhiệm của ứng dụng.

---

## 4. Cấu trúc document trong fs.chunks

Một chunk minh họa:

```javascript
{
  _id: ObjectId("6917a0000000000000000101"),
  files_id: ObjectId("6917a0000000000000000001"),
  n: 0,
  data: BinData(0, "JVBERi0xLjcK...")
}
```

| Field | Ý nghĩa |
| --- | --- |
| `_id` | ID duy nhất của **chunk document** |
| `files_id` | ID của file cha trong `fs.files` |
| `n` | Thứ tự chunk, bắt đầu bằng **0** |
| `data` | Bytes của chunk dưới dạng BSON Binary |

**Thứ tự tải xuống** được xác định bởi `n`, không phải thứ tự ObjectId, upload time hoặc thứ tự documents tự nhiên trong collection.

### 4.1. Một file có bao nhiêu chunks?

Công thức cho file có kích thước dương:

```text
chunkCount = ceil(fileLengthBytes / chunkSizeBytes)
```

Ví dụ file **600 KiB**, dùng chunk mặc định **255 KiB**:

```text
File = 600 KiB

Chunk n=0: 255 KiB
Chunk n=1: 255 KiB
Chunk n=2:  90 KiB
------------------
Total    : 600 KiB
```

File nhỏ hơn một chunk vẫn có thể có một chunk chứa đúng số bytes cần thiết. Với **file rỗng**, có thể có metadata của file độ dài 0 mà không có chunk data nào.

### 4.2. Chunk khác chunk của sharding

Trong GridFS, **chunk** là đoạn dữ liệu nhị phân của file.

Trong MongoDB sharding, **chunk/range** là đơn vị phân vùng shard key. Hai thuật ngữ **không cùng đối tượng** dù có tên giống nhau.

---

## 5. Các chỉ mục GridFS bắt buộc

GridFS dùng hai chỉ mục thông dụng:

### 5.1. Index của chunks

```javascript
db.getSiblingDB("files_demo")
  .fs.chunks
  .createIndex(
    { files_id: 1, n: 1 },
    { unique: true }
  );
```

Index này giúp đọc chunks của một file theo thứ tự và ngăn hai chunks có cùng cặp `(files_id, n)`.

Truy vấn tương ứng:

```javascript
db.getSiblingDB("files_demo")
  .fs.chunks
  .find({ files_id: fileId })
  .sort({ n: 1 });
```

### 5.2. Index của files

```javascript
db.getSiblingDB("files_demo")
  .fs.files
  .createIndex({
    filename: 1,
    uploadDate: 1
  });
```

Index hỗ trợ tìm các revision theo tên và thời gian. **Không phải unique index**, vì GridFS cho phép nhiều versions dùng chung filename.

### 5.3. Driver có tự tạo index?

Java Sync Driver có hành vi tạo bucket collections ở **lần ghi đầu tiên** khi cần. Nó tạo các GridFS indexes mặc định khi chúng chưa có và **bucket còn rỗng**.

Không hiểu lời này là “driver luôn sửa mọi index bị hỏng trong bucket đã có dữ liệu”. Khi legacy bucket đã tồn tại hoặc có dữ liệu bất thường, cần kiểm tra/chỉnh index theo kế hoạch quản trị.

Kiểm tra:

```javascript
const dbFiles = db.getSiblingDB("files_demo");

dbFiles.fs.files.getIndexes();
dbFiles.fs.chunks.getIndexes();
```

Đừng xóa hai index này chỉ để “giảm write overhead”: GridFS dùng chúng để truy xuất và kiểm soát thứ tự/chunks.

---

## 6. Kích thước chunk: 255 KiB mặc định và cách chọn

GridFS mặc định dùng **255 KiB**:

```text
255 × 1024 = 261120 bytes
```

Có thể thay kích thước chunk cho từng file qua `GridFSUploadOptions.chunkSizeBytes(...)`.

### 6.1. Chọn chunk lớn hơn có ích gì?

Giả sử cần lưu 1 GiB dữ liệu:

- Chunk nhỏ → nhiều chunk documents hơn, nhiều entries ở `chunks` index.
- Chunk lớn → ít chunk documents hơn, giảm overhead cho metadata/index/round trips trong một số trường hợp.
- Chunk lớn cũng tăng buffer/memory dành cho từng stream và lượng data cần xử lý khi đọc một phần nhỏ.

Không có con số tốt cho mọi workload. Các yếu tố:

- Kích thước file trung bình và cực đại.
- Số upload/download đồng thời.
- Access pattern chủ yếu stream toàn file hay đọc từng phần.
- Tốc độ network và MongoDB.
- Memory budget mỗi service instance.
- Chi phí lưu trữ/index và phân phối dữ liệu.

### 6.2. Không dùng chunk lớn hơn BSON document limit

Mỗi chunk là **một BSON document**. Cần giữ `chunkSizeBytes` **dưới giới hạn document 16 MiB**, chừa overhead cho các field khác. Ví dụ 1 MiB là tùy chọn hợp lý để thử benchmark nhưng không là mặc định bắt buộc.

### 6.3. Chunk size không phải HTTP request buffer

`chunkSizeBytes` điều khiển cách **GridFS lưu chunks trong MongoDB**. HTTP response buffer hoặc buffer copy trong Java có thể là 8 KiB, 32 KiB hoặc một giá trị khác. Không cần tạo byte array 255 KiB chỉ để phục vụ đọc từng lần nếu driver nhận `InputStream`/`OutputStream`.

---

## 7. Java Sync Driver: khởi tạo GridFSBucket

Dùng dependency `mongodb-driver-sync` phù hợp với phiên bản MongoDB Server. Ví dụ dưới đây tập trung vào API GridFS, không cung cấp secrets thực.

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

public final class GridFSConnection {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI is not configured"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client
                .getDatabase("files_demo")
                .withWriteConcern(WriteConcern.MAJORITY);

            GridFSBucket bucket = GridFSBuckets.create(
                database,
                "attachments"
            );

            System.out.println("Bucket name: attachments");
            // Bucket collections are created on the first write.
        }
    }
}
```

Nếu chỉ dùng:

```java
GridFSBucket bucket = GridFSBuckets.create(database);
```

thì tên bucket mặc định là `fs`, nên collections là `fs.files` và `fs.chunks`.

### 7.1. Vì sao chọn WriteConcern.MAJORITY?

Tài liệu Java Sync Driver **khuyến nghị `WriteConcern.MAJORITY` khi lưu file GridFS**. Nếu dùng write concern yếu và primary election xảy ra khi upload, một số chunks có thể bị rollback, gây tệp thiếu dữ liệu.

`MAJORITY` không làm mọi failure biến mất, nhưng cải thiện bảo đảm durability theo topology và replication health. Cần có retry/recovery khi upload thất bại.

### 7.2. Không mở MongoClient cho từng file

`MongoClient` quản lý connection pools. Trong service backend, thường tạo MongoClient theo vòng đời ứng dụng, rồi tạo/tái sử dụng `GridFSBucket` tương ứng database/bucket.

Không mở và đóng connection pool cho mỗi request upload/download; chi phí bắt tay, connection churn và timeouts có thể tăng.

---

## 8. Upload một file qua InputStream

Đây là con đường đơn giản nhất để tải file từ ổ đĩa, HTTP multipart hoặc một InputStream bất kỳ mà không cần giữ toàn bộ trong RAM.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GridFSUploader {

    public static ObjectId uploadPdf(
            GridFSBucket bucket,
            Path source,
            String tenantId,
            String uploaderId
    ) throws IOException {

        Document metadata = new Document()
            .append("tenantId", tenantId)
            .append("uploadedBy", uploaderId)
            .append("contentType", "application/pdf")
            .append("schemaVersion", 1);

        GridFSUploadOptions options =
            new GridFSUploadOptions()
                .chunkSizeBytes(1024 * 1024)
                .metadata(metadata);

        try (InputStream input = Files.newInputStream(source)) {
            return bucket.uploadFromStream(
                source.getFileName().toString(),
                input,
                options
            );
        }
    }
}
```

### 8.1. Điều gì xảy ra trong code?

1. Java mở file dưới dạng `InputStream`.
2. Driver đọc luân phiên các bytes.
3. Driver lưu nhiều chunk documents vào `attachments.chunks`.
4. Upload thành công, driver hoàn tất file document trong `attachments.files`.
5. Method trả `ObjectId` để ứng dụng liên kết file với hồ sơ nghiệp vụ.
6. `try-with-resources` đóng input stream dù upload thất bại.

### 8.2. Ưu điểm của streaming

Không viết:

```java
byte[] allBytes = Files.readAllBytes(source);
bucket.uploadFromStream(
    "huge.pdf",
    new java.io.ByteArrayInputStream(allBytes)
);
```

nếu file có thể rất lớn. Cách đó tạo một array tỷ lệ trực tiếp với file size. Với nhiều request đồng thời, bộ nhớ rất dễ tăng mạnh.

Dùng `Files.newInputStream`, `FileInputStream` hoặc multipart `InputStream` thích hợp để file được đọc theo luồng.

### 8.3. Metadata và MIME

`contentType` ở ví dụ là một **giá trị do ứng dụng khai báo**. Trong production:

- Không tin hoàn toàn header `Content-Type` do client gửi.
- Kiểm tra MIME bằng file signature/định dạng hoặc scanner thích hợp.
- Ràng buộc loại file được phép theo nghiệp vụ.
- Có thể giữ `metadata.originalFilename`, nhưng tránh dùng nó trực tiếp làm filesystem path.

---

## 9. Upload qua GridFSUploadStream (OutputStream)

Đường ngược lại: ứng dụng muốn **tự viết dần bytes** vào GridFS, ví dụ vừa nhận các blocks dữ liệu vừa chuyển đổi đơn giản.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSUploadStream;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.InputStream;

public final class GridFSPipeUpload {

    public static ObjectId upload(
            GridFSBucket bucket,
            String filename,
            InputStream source,
            Document metadata
    ) throws IOException {

        GridFSUploadOptions options =
            new GridFSUploadOptions()
                .chunkSizeBytes(1024 * 1024)
                .metadata(metadata);

        // Source ownership do caller quản lý.
        try (GridFSUploadStream target =
                 bucket.openUploadStream(filename, options)) {

            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = source.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                target.write(buffer, 0, read);
            }

            // GridFSUploadStream đóng sẽ finalize file
            // và thực hiện các bước cần thiết để hoàn tất upload.
            return target.getObjectId();
        }
    }
}
```

**Lưu ý về thời điểm hoàn tất:** trong code trên `return target.getObjectId()` được đánh giá **trước khi** `try-with-resources` gọi `close()`, nhưng giá trị chỉ thực sự trả ra khỏi method sau khi đóng stream thành công. Nếu `close()` lỗi, method không trả success.

### 9.1. Vì sao dùng output stream?

- Ứng dụng nhận nguồn dưới dạng các bytes được cung cấp từng phần.
- Muốn tính toán, transform hoặc mã hóa luồng trước khi ghi.
- Muốn kiểm soát số bytes đọc ở mỗi vòng.
- Không muốn materialize toàn bộ nội dung trước khi upload.

### 9.2. Khi nào đơn giản hơn bằng uploadFromStream?

Nếu đã có `InputStream` và không cần logic xử lý trên từng block, `bucket.uploadFromStream(...)` thường ngắn gọn hơn. Cả hai dùng GridFS và đều có thể tránh tải cả tệp vào RAM.

---

## 10. Tải trực tiếp từ HTTP multipart input stream

Giả sử tầng web framework cung cấp `InputStream` của một multipart file. Cách tối giản ở service:

```java
public ObjectId saveAttachment(
        InputStream requestBodyStream,
        String safeFilename,
        String tenantId,
        String ownerId,
        GridFSBucket bucket
) {
    Document metadata = new Document()
        .append("tenantId", tenantId)
        .append("ownerId", ownerId)
        .append("contentType", "application/octet-stream")
        .append("state", "UPLOADED");

    GridFSUploadOptions options =
        new GridFSUploadOptions()
            .chunkSizeBytes(255 * 1024)
            .metadata(metadata);

    return bucket.uploadFromStream(
        safeFilename,
        requestBodyStream,
        options
    );
}
```

Đoạn minh họa giả định request body đã được xác thực, giới hạn và validate ở tầng HTTP. **Không dùng trực tiếp tên file/raw MIME từ request** để đưa vào storage hoặc response mà không kiểm soát.

### 10.1. Không chắc request Content-Length là sự thật

Một client có thể:

- Không gửi Content-Length.
- Gửi Content-Length sai.
- Dùng chunked transfer encoding.
- Cố gắng truyền file cực lớn để làm đầy disk/index.
- Ngắt kết nối giữa chừng.

Cần **giới hạn tổng bytes thực sự đọc** ngay cả khi request header nói file nhỏ.

### 10.2. Ví dụ InputStream giới hạn kích thước

Một wrapper Java đơn giản (đếm bytes khi driver đọc):

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class SizeLimitedInputStream
        extends FilterInputStream {

    private final long maxBytes;
    private long consumed;

    public SizeLimitedInputStream(
            InputStream input,
            long maxBytes
    ) {
        super(input);
        if (maxBytes < 0) {
            throw new IllegalArgumentException(
                "maxBytes must be non-negative"
            );
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            consumed++;
            if (consumed > maxBytes) {
                throw new IOException("Upload too large");
            }
        }
        return value;
    }

    @Override
    public int read(
            byte[] bytes,
            int offset,
            int length
    ) throws IOException {
        int maxToRead = (int) Math.min(
            (long) length,
            maxBytes - consumed + 1L
        );
        if (maxToRead <= 0 && length > 0) {
            throw new IOException("Upload too large");
        }
        int read = in.read(bytes, offset,
            Math.max(maxToRead, 0));
        if (read > 0) {
            consumed += read;
            if (consumed > maxBytes) {
                throw new IOException("Upload too large");
            }
        }
        return read;
    }
}
```

Mẫu trên nhằm giải thích ý tưởng đếm bytes. Trong production, cần xem xét kỹ `skip()`, `mark/reset()` và mọi cách đọc khác hoặc dùng wrapper đã được kiểm chứng; một wrapper chỉ override một vài method có thể bị bypass nếu caller gọi các method khác. Framework upload limit và reverse-proxy limits vẫn nên được bật như lớp bảo vệ bổ sung.

---

## 11. Tải lên thất bại: GridFS không có commit một-document duy nhất

Đây là điểm rất quan trọng.

Một upload phải ghi **nhiều chunk documents** rồi ghi metadata file. GridFS **không hỗ trợ multi-document transactions** để bao toàn bộ chuỗi ấy trong một ACID transaction.

Tình huống:

```text
Upload file 5 MiB
    |
    +-- chunk 0: success
    +-- chunk 1: success
    +-- chunk 2: success
    +-- chunk 3: network error
    |
    X metadata file có thể chưa được finalize
```

Có thể còn lại **orphaned chunks**: chunk documents có `files_id` mà không có document cha trong `fs.files`.

### 11.1. Các lỗi phổ biến

- Client/người dùng ngắt upload.
- InputStream throw `IOException`.
- Primary election, connection reset, timeout.
- Disk quota/collection/storage problem.
- Write concern timeout.
- Process bị kill trước khi hoàn tất.
- Lỗi ở lần ghi metadata file cuối cùng.

Không mặc định rằng một exception **luôn** đã dọn mọi chunk; theo tài liệu driver, upload thất bại có thể để lại orphaned chunks cần cleanup.

### 11.2. Tác động đến file ID

Khi upload thành công, driver trả file ID. Nếu upload throw, **không tạo pointer READY trong document nghiệp vụ** như thể file đã hoàn chỉnh.

Nếu dùng ID tự cung cấp trước upload, ID đó có thể đã được dùng cho một phần chunks; retry mù quáng cùng ID có thể gặp duplicate keys hoặc trạng thái không nhất quán. Cần strategy rõ ràng theo việc upload đã hoàn tất, chưa hoàn tất hoặc không xác định.

### 11.3. Cleanup orphaned chunks

Một chunk có orphan nếu:

```text
fs.chunks.files_id không tồn tại trong fs.files._id
```

Tuy nhiên **không được xóa ngay** mọi orphan đang thấy: upload hợp lệ **đang diễn ra** cũng có thể đã ghi chunks nhưng chưa finalize `fs.files`.

Một quy trình an toàn hơn:

1. Chạy dưới quyền quản trị đã được phê duyệt.
2. Chọn **candidate orphan chunks đủ cũ** so với ngưỡng thời gian upload tối đa.
3. Đối chiếu `files_id` với `fs.files` và trạng thái upload/lease trong application.
4. Đảm bảo không có uploader còn hoạt động cho ID đó.
5. Ghi log/metric và xóa có giới hạn batch nếu xác định chắc là orphan.
6. Kiểm tra kết quả ở staging trước khi áp dụng production.

Không chạy một lệnh `deleteMany` “mọi chunk thiếu file” trong khi upload đồng thời đang diễn ra.

---

## 12. Một API upload nên trả về gì?

Sau thành công:

```json
{
  "fileId": "6917a0000000000000000001",
  "filename": "report.pdf",
  "status": "READY"
}
```

Đây là response API do ứng dụng thiết kế, **không phải response mặc định của GridFS**.

### 12.1. Đặt trạng thái nghiệp vụ

Một mô hình:

```text
REQUEST_RECEIVED
     |
     v
VALIDATING
     |
     v
UPLOADING
     |
     +-- failure --> FAILED / cleanup
     |
     v
GRIDFS_COMPLETED
     |
     v
SCANNING / VERIFYING
     |
     +-- rejected --> QUARANTINED / cleanup
     |
     v
READY
```

Không đưa file vào trạng thái public `READY` trước khi driver upload thành công và business verification hoàn tất.

### 12.2. Metadata status không thay transaction

Nếu application ghi:

1. Nội dung vào GridFS.
2. Một document nghiệp vụ liên kết `fileId`.

thì **hai bước không tự atomic**. Nếu bước 2 lỗi, file có thể tồn tại nhưng không có pointer nghiệp vụ; cần reconciliation/cleanup. Nếu business yêu cầu hiển thị phiên bản hiện hành nhất quán, có thể tải phiên bản mới trước rồi dùng một **atomic update trên pointer document** để chuyển sang file ID mới sau khi sẵn sàng.

---

## 13. Download file theo ID vào OutputStream

Nếu API đã biết file ID, đây là cách thẳng nhất:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GridFSDownloader {

    public static void download(
            GridFSBucket bucket,
            ObjectId fileId,
            Path outputPath
    ) throws IOException {

        try (OutputStream output =
                 Files.newOutputStream(outputPath)) {
            bucket.downloadToStream(fileId, output);
            output.flush();
        }
    }
}
```

`bucket.downloadToStream(...)` đọc tệp từ GridFS và ghi trực tiếp vào stream đích. Ứng dụng không cần tạo `byte[]` bằng toàn bộ file length.

### 13.1. Tránh bug ghi tệp lỗi trực tiếp vào tên đích

Nếu download fail giữa chừng, `outputPath` có thể chứa **file dở dang**. Trong ứng dụng có yêu cầu toàn vẹn, nên:

1. Ghi vào temp path trong cùng filesystem.
2. Tải xong, đóng stream.
3. Xác minh kích thước/checksum nếu có.
4. Atomic move/rename temp thành đường dẫn chính nếu platform/filesystem hỗ trợ.
5. Dọn temp khi lỗi.

Không coi việc bắt đầu download là đủ để đánh dấu file đã được phục hồi thành công.

---

## 14. Download theo InputStream với GridFSDownloadStream

Nếu muốn **tự điều khiển từng block** để truyền qua HTTP, tính SHA-256 hoặc xử lý theo luồng, dùng `openDownloadStream`:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;

public final class GridFSStreamCopy {

    public static void copyFile(
            GridFSBucket bucket,
            ObjectId fileId,
            OutputStream destination
    ) throws IOException {

        try (GridFSDownloadStream input =
                 bucket.openDownloadStream(fileId)) {

            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = input.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                destination.write(buffer, 0, read);
            }

            destination.flush();
        }
    }
}
```

### 14.1. Memory footprint

Nếu file dài 1 GiB, đoạn code chỉ tạo buffer copy 64 KiB (ngoài buffers và tài nguyên do driver/HTTP framework quản lý). Nó **không** tạo array 1 GiB.

### 14.2. Vì sao không dùng một lần read?

Sai:

```java
byte[] bytes = new byte[(int) file.getLength()];
input.read(bytes);
```

Vấn đề:

- `length` là long; ép thành int có thể overflow.
- Một lần `InputStream.read(byte[])` **không được đảm bảo đọc đủ** buffer.
- File lớn có thể gây `OutOfMemoryError`.
- HTTP client ngắt giữa chừng vẫn lãng phí bộ nhớ.

Nếu cần đọc đầy đủ một số bytes vào buffer nhỏ, dùng vòng lặp đúng semantics stream hoặc các API đọc đủ được hỗ trợ.

### 14.3. getGridFSFile()

`GridFSDownloadStream` cung cấp:

```java
GridFSFile fileInfo = input.getGridFSFile();

long length = fileInfo.getLength();
String filename = fileInfo.getFilename();
Document metadata = fileInfo.getMetadata();
```

Đây là metadata của file được chọn để download, hữu ích khi thiết lập HTTP headers trước khi chuyển nội dung.

---

## 15. Download theo filename và revision

GridFS **cho phép nhiều file trùng filename**, vì vậy tải theo tên phải xác định revision.

Ví dụ:

```text
filename = "contract.pdf"

Upload 1: 2026-01-10, ID=A
Upload 2: 2026-02-10, ID=B
Upload 3: 2026-03-10, ID=C
```

Revision semantics:

| Revision | Kết quả |
| --- | --- |
| `0` | Phiên bản cũ nhất, ID=A |
| `1` | Phiên bản kế tiếp, ID=B |
| `2` | Phiên bản tiếp theo, ID=C |
| `-1` | Phiên bản mới nhất, ID=C |
| `-2` | Phiên bản mới thứ hai, ID=B |

Java API:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

import java.io.IOException;
import java.io.OutputStream;

public final class GridFSRevisions {

    public static void downloadOriginal(
            GridFSBucket bucket,
            String filename,
            OutputStream output
    ) throws IOException {

        GridFSDownloadOptions options =
            new GridFSDownloadOptions()
                .revision(0);

        bucket.downloadToStream(
            filename,
            output,
            options
        );
    }

    public static void downloadLatest(
            GridFSBucket bucket,
            String filename,
            OutputStream output
    ) throws IOException {

        GridFSDownloadOptions options =
            new GridFSDownloadOptions()
                .revision(-1);

        bucket.downloadToStream(
            filename,
            output,
            options
        );
    }
}
```

Theo mặc định, khi nhiều file cùng tên, GridFS tải **phiên bản gần đây nhất** dựa theo `uploadDate`.

### 15.1. Tại sao download theo ID thường an toàn hơn?

- Filename không unique.
- Người dùng có thể upload nhiều lần cùng tên.
- Tên có thể đổi qua `rename()`.
- Cùng lúc upload/rename/delete có thể làm lựa chọn “latest” thay đổi.
- Metadata `uploadDate` không nên thay thế business version number trong các workflow đòi ordering tuyệt đối.

Đối với API tài liệu nghiệp vụ, lưu ID vào document `documents.currentFileId` và download đúng ID được chỉ định. Nếu muốn “latest”, ứng dụng cần định nghĩa rõ chính sách cập nhật pointer.

---

## 16. GridFSBucket.find(): tìm file qua metadata

Bạn có thể tìm metadata bằng GridFS Bucket API thay vì đọc raw `fs.files` trong mọi tình huống.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.conversions.Bson;

public final class GridFSMetadataQuery {

    public static void listTenantPdfs(
            GridFSBucket bucket,
            String tenantId
    ) {
        Bson filter = Filters.and(
            Filters.eq("metadata.tenantId", tenantId),
            Filters.eq(
                "metadata.contentType",
                "application/pdf"
            )
        );

        bucket.find(filter)
            .sort(Sorts.descending("uploadDate"))
            .limit(50)
            .forEach((GridFSFile file) -> {
                System.out.println(
                    file.getObjectId().toHexString()
                    + " " + file.getFilename()
                    + " " + file.getLength()
                );
            });
    }
}
```

`GridFSFile` thường cung cấp:

- `getId()` (BsonValue) và convenience `getObjectId()` khi ID là ObjectId.
- `getFilename()`.
- `getLength()`.
- `getChunkSize()`.
- `getUploadDate()`.
- `getMetadata()`.

### 16.1. Metadata filter và tenant isolation

Chỉ hiển thị danh sách file của tenant đã xác thực. `tenantId` phải đến từ **server-side authenticated context**, không từ query param do client tùy chọn.

Khi download trực tiếp qua ID, vẫn phải **xác minh file ID thuộc tenant và user được quyền đọc**; chỉ filter list page theo tenant là chưa đủ.

### 16.2. GridFSFile.getObjectId() có giới hạn kiểu ID

Nếu bạn tạo GridFS file với _id là BSON type khác ObjectId, convenience `getObjectId()` có thể không phù hợp. Trong code hỗ trợ nhiều kiểu ID, dùng `getId()` dạng `BsonValue` cùng overload bucket tương ứng.

---

## 17. Truy vấn metadata trực tiếp với mongosh

MongoDB không giấu các collections của GridFS. Ví dụ:

```javascript
const d = db.getSiblingDB("files_demo");

d.attachments.files.find(
  {
    "metadata.tenantId": "TENANT-001",
    "metadata.contentType": "application/pdf"
  },
  {
    filename: 1,
    length: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({
  uploadDate: -1
}).limit(20);
```

Xem chunks của một file:

```javascript
const fileId = ObjectId("6917a0000000000000000001");

d.attachments.chunks.find(
  { files_id: fileId },
  { n: 1, _id: 1, data: 0 }
).sort({ n: 1 });
```

**Không dùng** `find()` trực tiếp trên chunks để tải tệp xuống rồi tùy ý nối `BinData` nếu đã có GridFS driver; driver xử lý thứ tự, EOF và validation phù hợp.

### 17.1. Query metadata không tải binary

Khi list files qua `attachments.files`, MongoDB chỉ trả **metadata documents**; không phải tự tải chunks của mọi file. Đây là lợi ích lớn khi app hiển thị danh sách tài liệu, dung lượng, MIME, ngày upload.

### 17.2. Đừng dựa vào uploadDate làm authorization

`uploadDate` có thể cho biết thời điểm upload, nhưng không chứng minh user được phép xem file hay file đang READY. Dùng metadata và business ACL phù hợp.

---

## 18. Thiết kế metadata hữu ích cho hệ thống thực tế

Có thể chia metadata thành các nhóm:

| Nhóm | Fields gợi ý |
| --- | --- |
| Tenant/ownership | `tenantId`, `ownerId`, `uploadedBy` |
| Loại file | `contentType`, `extension`, `originalFilename` |
| Business references | `documentId`, `caseId`, `contractId` |
| Integrity | `sha256`, `hashAlgorithm` |
| Lifecycle | `state`, `verifiedAt`, `deletedAt` |
| Search/filtering | `tags`, `category`, `classification` |
| Versioning | `businessVersion`, `replacesFileId` |
| Security | `scanStatus`, `sensitivity`, `retentionUntil` |
| Governance | `schemaVersion`, `sourceSystem` |

Ví dụ:

```javascript
{
  metadata: {
    schemaVersion: 2,
    tenantId: "T100",
    ownerId: "USER-42",
    originalFilename: "report Q4.pdf",
    contentType: "application/pdf",
    sha256: "full-64-character-sha256-hex",
    businessVersion: 3,
    state: "READY",
    scanStatus: "CLEAN",
    labels: ["finance", "q4"]
  }
}
```

Giá trị sha256 trong ví dụ mô tả schema, không phải digest hợp lệ.

### 18.1. Metadata là application schema, không phải đặc tả cố định

GridFS không tự enforce `metadata.tenantId` hoặc `metadata.state`; đây là lựa chọn của ứng dụng. Bạn có thể dùng MongoDB schema validation phù hợp cho `attachments.files`, nhưng phải thận trọng tránh xung đột với cấu trúc GridFS driver.

### 18.2. Không lưu dữ liệu nhạy cảm không cần thiết

Tránh đưa password, access tokens, đầy đủ địa chỉ cá nhân hoặc nội dung tệp vào metadata nếu không có nhu cầu. Metadata có thể được query, index, backup và log khác với binary.

---

## 19. MIME type: contentType ở metadata, không tin client

MongoDB GridFS có field `files.contentType` lịch sử nhưng **deprecated**. Nên đặt MIME trong:

```javascript
metadata: {
  contentType: "application/pdf"
}
```

### 19.1. Phân biệt ba nguồn MIME

1. **Client-declared MIME**: HTTP header, có thể sai hoặc bị giả mạo.
2. **Filename extension**: `.pdf`, `.png`, `.exe`; cũng không đáng tin.
3. **Detected MIME**: dựa vào file signature/parser được phép, thường đáng tin hơn nhưng không tự loại bỏ malware.

Ví dụ request báo `image/png` nhưng bytes thực là một executable. GridFS sẽ lưu bytes; bảo vệ là trách nhiệm của ứng dụng.

### 19.2. Khi trả file qua HTTP

Gợi ý:

- `Content-Type` theo metadata đã kiểm chứng.
- `Content-Length` từ `GridFSFile.getLength()` nếu khả dụng và chưa compression/tranformation thay đổi bytes.
- `Content-Disposition: attachment` với tên file đã sanitize/encode theo RFC.
- `X-Content-Type-Options: nosniff`.
- Chính sách cache, authorization và range requests phù hợp.

Không đặt header `Content-Type: text/html` chỉ vì client upload một file tự xưng HTML nếu business chỉ cho phép file attachment.

---

## 20. SHA-256, kiểm tra toàn vẹn và vì sao md5 đã deprecated

GridFS historically có thể có field `md5` được tạo từ `filemd5`. MongoDB đã **deprecated** MD5 support và khuyến nghị ứng dụng tính checksum riêng, lưu trong `metadata`.

MD5 không phù hợp để chống collision có chủ đích và không phải lựa chọn hiện đại cho file integrity/security. Dùng **SHA-256** hoặc giải pháp digest phù hợp với chính sách tổ chức.

### 20.1. Tính SHA-256 khi streaming upload

Có thể bọc InputStream bằng `DigestInputStream`:

```java
import java.io.DigestInputStream;
import java.io.InputStream;
import java.security.MessageDigest;

MessageDigest sha256 =
    MessageDigest.getInstance("SHA-256");

try (InputStream raw = Files.newInputStream(path);
     DigestInputStream input =
         new DigestInputStream(raw, sha256)) {

    ObjectId id = bucket.uploadFromStream(
        "report.pdf",
        input,
        options
    );

    byte[] digest = sha256.digest();
    String hex = java.util.HexFormat
        .of()
        .formatHex(digest);

    // Tới đây đã có fileId và digest.
    // Có thể cập nhật metadata checksum sau upload.
}
```

`java.util.HexFormat` có từ Java 17. Nếu project dùng Java cũ hơn, cần chuyển bytes sang hex bằng code tương thích.

### 20.2. Vấn đề thời điểm có checksum

Trong streaming, checksum đầy đủ chỉ biết **sau khi đọc toàn bộ tệp**. Nhưng `GridFSUploadOptions.metadata` phải được cung cấp trước khi upload.

Các cách xử lý:

- **Hai lượt đọc**: tính hash trước, rồi upload ở lượt thứ hai; tốn thêm I/O nhưng metadata có checksum khi tạo.
- **Một lượt streaming**: tính hash trong lúc upload, sau khi thành công cập nhật `metadata.sha256` trong `*.files`; cần xử lý khoảng hở giữa upload hoàn tất và metadata update.
- **Staging/READY**: chỉ cho file hiển thị/tải về khi checksum và scan đã được ghi nhận hoàn tất.
- **Server trusted digest**: nhận checksum client gửi để so sánh, nhưng không coi checksum client là bằng chứng nội dung an toàn.

Nếu HTTP request body không thể đọc lại, hai lượt không khả thi nếu chưa spool ra ổ đĩa tạm. Khi dùng spool, vẫn phải giới hạn storage và dọn temp.

### 20.3. Xác minh khi download

Tính SHA-256 trên bytes **thực sự tải xuống**, so với metadata digest đáng tin. Nếu không khớp, coi file có vấn đề và không publish nội dung đã tải như file hoàn chỉnh.

Checksum giúp phát hiện corruption, nhưng không thay authorization, malware scanning hoặc encryption.

---

## 21. Cập nhật metadata sau upload

Metadata GridFS nằm trong `attachments.files`. Có thể cập nhật field ứng dụng thông qua MongoCollection thông thường:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.bson.types.ObjectId;

public final class GridFSMetadataUpdate {

    public static void markVerified(
            MongoDatabase database,
            ObjectId fileId,
            String sha256Hex
    ) {
        MongoCollection<Document> files =
            database.getCollection("attachments.files");

        files.updateOne(
            Filters.eq("_id", fileId),
            Updates.combine(
                Updates.set(
                    "metadata.sha256",
                    sha256Hex
                ),
                Updates.set(
                    "metadata.scanStatus",
                    "CLEAN"
                ),
                Updates.set(
                    "metadata.state",
                    "READY"
                )
            )
        );
    }
}
```

### 21.1. Chỉ thay trường metadata ứng dụng

**Không sửa trực tiếp** các field hệ thống như:

- `length`.
- `chunkSize`.
- `_id`.
- `files_id` và `n` trong chunks.

Nếu chỉnh sai `length` hoặc `chunkSize`, GridFS reader có thể báo lỗi thiếu/corrupt chunks hoặc đọc sai nội dung. Đừng “sửa độ dài” bằng cập nhật metadata mà không đồng bộ đúng dữ liệu.

### 21.2. Tránh ghi đè state do race

Nếu một scanner chậm cập nhật `scanStatus: CLEAN` sau khi file đã bị revoked, không nên cho scanner ghi state READY mù quáng.

Dùng conditional update:

```javascript
db.getSiblingDB("files_demo")
  .attachments.files
  .updateOne(
    {
      _id: fileId,
      "metadata.state": "SCANNING"
    },
    {
      $set: {
        "metadata.state": "READY",
        "metadata.scanStatus": "CLEAN"
      }
    }
  );
```

Kiểm tra `matchedCount`/`modifiedCount` theo contract của application.

---

## 22. Tạo index phụ cho metadata và list API

Các default indexes giúp GridFS vận hành, nhưng nếu application thường list files theo tenant/owner/status thì có thể cần index riêng.

```javascript
const d = db.getSiblingDB("files_demo");

d.attachments.files.createIndex({
  "metadata.tenantId": 1,
  "metadata.state": 1,
  uploadDate: -1
});

d.attachments.files.createIndex({
  "metadata.documentId": 1,
  uploadDate: -1
});
```

Một query:

```javascript
d.attachments.files.find({
  "metadata.tenantId": "T100",
  "metadata.state": "READY"
}).sort({
  uploadDate: -1
}).limit(20);
```

### 22.1. Tại sao nên index metadata được dùng nhiều?

Không có index phù hợp, hệ thống có thể scan nhiều file metadata documents khi người dùng mở danh sách. Dù binary nằm ở collection khác, một collection `attachments.files` với hàng triệu entries vẫn cần query planning.

### 22.2. Đừng tạo index cho mọi field

Mỗi index tăng storage/write maintenance và chi phí backup. Tạo index dựa trên query shapes thực tế: tenant/status/date, documentId, filename/version hoặc checksum nếu dedup cần.

### 22.3. TTL không thay GridFS delete

**Không đặt TTL index trực tiếp trên `attachments.files.uploadDate` rồi tưởng sẽ xóa cả dữ liệu file**. TTL chỉ xóa document trong `*.files`, không tự gọi GridFSBucket.delete để xóa các chunks liên quan; dễ để lại orphaned chunks.

Muốn retention, nên có **job lifecycle** tìm file cần xóa, sau đó gọi GridFS `delete(fileId)` có kiểm soát, kèm cleanup và audit.

---

## 23. Rename và delete theo file ID

GridFS driver có API:

```java
bucket.rename(fileId, "report-2026.pdf");
bucket.delete(fileId);
```

### 23.1. Rename

`rename(fileId, newFilename)` đổi tên của **một file ID cụ thể**. Nó không đổi bytes và không đổi tên cho tất cả các revisions cùng filename cũ.

Vì nhiều file có thể trùng tên, **không nên rename theo tên không xác định**.

### 23.2. Delete

`delete(fileId)` xóa file metadata và các chunks của một file ID theo cơ chế GridFS.

Vì GridFS không có multi-document transaction, nếu delete bị gián đoạn có thể phát sinh orphaned chunks hoặc trạng thái dở dang. Cần:

- Ghi nhận intent xóa (audit).
- Không retry vô hạn mà không phân loại kết quả.
- Đối soát chunks nếu operation thất bại.
- Xác minh authorization trước khi xóa.
- Tránh xóa theo filename khi nhiều versions trùng tên.

### 23.3. Không drop bucket để xóa một file

`bucket.drop()` xóa **cả bucket** (hai collections tương ứng). Đây là thao tác phá hủy lớn, chỉ dành cho quy trình quản trị/test có xác nhận, không dùng cho endpoint `DELETE /files/{id}`.

---

## 24. HTTP download theo luồng: thiết kế API

Một endpoint khái niệm:

```text
GET /api/files/{fileId}
Authorization: Bearer ...
```

Quy trình nên là:

```text
1. Authenticate request.
2. Parse/validate fileId.
3. Kiểm tra file thuộc tenant/owner và trạng thái READY.
4. Lấy metadata và kiểm tra MIME/length/filename.
5. Set HTTP response headers.
6. Đọc GridFSDownloadStream -> response output stream.
7. Đóng stream và xử lý lỗi client disconnect.
```

### 24.1. Ví dụ với Jakarta Servlet

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import com.mongodb.client.gridfs.model.GridFSFile;
import jakarta.servlet.http.HttpServletResponse;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;

public final class DownloadController {

    public static void send(
            GridFSBucket bucket,
            ObjectId fileId,
            HttpServletResponse response
    ) throws IOException {

        // GỌI TRƯỚC KHI PHỤC VỤ RESPONSE:
        // authenticate + authorize fileId + tenant + READY.
        // Ví dụ chỉ mô tả streaming.

        try (GridFSDownloadStream input =
                 bucket.openDownloadStream(fileId)) {

            GridFSFile info = input.getGridFSFile();
            Document metadata = info.getMetadata();

            String mime = "application/octet-stream";
            if (metadata != null) {
                String validated = metadata
                    .getString("contentType");
                if (validated != null &&
                    !validated.isBlank()) {
                    // Production phải validate allowlist MIME.
                    mime = validated;
                }
            }

            response.setContentType(mime);
            response.setHeader(
                "X-Content-Type-Options",
                "nosniff"
            );
            response.setContentLengthLong(
                info.getLength()
            );

            // Download filename cần được sanitize/encode
            // riêng theo RFC 6266/5987 trước khi set header.

            byte[] buffer = new byte[64 * 1024];

            try (OutputStream output =
                     response.getOutputStream()) {

                int read;
                while ((read = input.read(buffer)) != -1) {
                    if (read > 0) {
                        output.write(
                            buffer, 0, read
                        );
                    }
                }
                output.flush();
            }
        }
    }
}
```

**Đoạn code không bao gồm authentication/authorization thực tế**, vì chúng thuộc framework và business context. Không triển khai endpoint download public chỉ bằng ví dụ streaming.

### 24.2. Tránh trả lỗi JSON sau khi đã bắt đầu stream

Nếu đọc chunk thứ 100 bị lỗi nhưng HTTP response đã gửi 99 chunks, server **không thể quay lại** trả một JSON response lỗi chuẩn ở đầu body. Thường phải abort connection và ghi metrics; client sẽ thấy download dở.

Để phát hiện tệp hỏng sớm hơn, có thể kiểm tra metadata/chunks trước hoặc dùng checksum khi hoàn tất, nhưng vẫn phải thiết kế client xử lý partial download.

### 24.3. HTTP headers phải an toàn

Không ghi trực tiếp:

```text
Content-Disposition: attachment; filename=<client-supplied-name>
```

nếu tên chứa CRLF, dấu nháy, đường dẫn hoặc Unicode chưa encode. Dùng thư viện header escaping/encoding và policy filename của ứng dụng.

### 24.4. Nên dùng streaming HTTP framework nào?

- Servlet/Spring MVC: `OutputStream` hoặc `StreamingResponseBody`.
- Reactive stack: cần dùng **Reactive Streams driver/GridFS APIs** phù hợp; không bọc blocking Sync Driver trong event-loop thread rồi gọi là non-blocking.
- Với object storage ngoài MongoDB, có thể trả signed URL nếu kiến trúc cho phép, nhưng đó là workflow khác.

---

## 25. HTTP Range requests và tải một phần tệp

Trình duyệt/video player có thể gửi:

```http
Range: bytes=1000000-1999999
```

Đây là yêu cầu tải **một đoạn bytes** của tệp, không phải yêu cầu tải file hoàn chỉnh.

GridFS cung cấp khả năng truy cập các phần của file mà không bắt buộc load toàn bộ file. Tuy nhiên:

- Không tự coi một endpoint GridFS streaming đơn giản là đã hỗ trợ **HTTP 206 Partial Content**.
- Phải parse/validate Range, hỗ trợ một hoặc nhiều ranges theo policy, xử lý `416 Range Not Satisfiable`.
- Phải trả `Content-Range`, `Content-Length`, `Accept-Ranges` đúng.
- Đảm bảo chỉ trả đúng số bytes được yêu cầu.
- Tính toán vị trí chunk và offset hoặc dùng API stream/seek được driver hỗ trợ trong phiên bản đang dùng.
- Xem cost của việc skip/seek nhiều lần, đặc biệt khi chunk size lớn.
- Nếu dùng ETag/If-Range, phải có file identity/checksum semantics rõ.

### 25.1. Công thức chunk index

Với chunk size `C` và byte offset `B` (0-based):

```text
chunkIndex      = floor(B / C)
offsetWithinChunk = B % C
```

Ví dụ `C = 261120` bytes, `B = 600000`:

```text
chunkIndex = floor(600000 / 261120) = 2
offset     = 600000 - (2 * 261120) = 77760
```

Đây là công thức để hiểu cấu trúc file. **Không nên tự truy xuất raw chunks trong endpoint thông thường** khi driver đã có API đọc file; chỉ áp dụng custom range logic nếu thật sự cần và đã kiểm thử.

### 25.2. Khi nào nên dùng CDN hoặc object storage?

Nếu ứng dụng phục vụ video lớn với nhiều clients đồng thời, cần streaming, partial range, CDN, cache invalidation và bandwidth cao, một object storage/CDN chuyên dụng có thể phù hợp hơn. GridFS vẫn có thể là nguồn dữ liệu trong những hệ thống cần lưu trên MongoDB, nhưng cần benchmark thực tế.

---

## 26. Độ bền, replication và failover

GridFS file là **nhiều MongoDB documents**. Điều này có tác động:

- Từng chunk insert là một thao tác ghi MongoDB.
- Metadata file ghi sau khi upload hoàn tất theo driver.
- Primary election có thể diễn ra giữa quá trình.
- Read/write concerns ảnh hưởng durability và visibility.
- Không có một transaction bao toàn bộ chunks + file metadata.

### 26.1. Majority write concern

MongoDB Java Sync Driver khuyến nghị upload với:

```java
MongoDatabase majorityDatabase =
    database.withWriteConcern(
        com.mongodb.WriteConcern.MAJORITY
    );

GridFSBucket durableBucket =
    GridFSBuckets.create(
        majorityDatabase,
        "attachments"
    );
```

Không coi một file upload với `w:1` là chắc chắn bền sau failover. Đặc biệt với GridFS, một số chunks có thể rollback độc lập khi failover xảy ra trong chuỗi ghi.

### 26.2. Read concern

Metadata có thể đã tồn tại theo một mức visibility, nhưng nếu các chunks thiếu do lỗi hoặc rollback thì stream download có thể fail. Đừng chỉ kiểm tra `fs.files` tồn tại rồi mặc định binary luôn toàn vẹn trong mọi failure mode.

### 26.3. Không đưa GridFS operations vào multi-document transaction

MongoDB Manual nói rõ GridFS **không hỗ trợ multi-document transactions**. Một upload lớn sẽ vượt nhiều document và thời gian, nên không cố mở transaction rồi ghi từng chunk qua driver để “atomic hóa” theo cách không được hỗ trợ.

Thay vào đó, dùng **immutable file versions + atomic pointer switch** trong một document nghiệp vụ sau khi phiên bản mới upload/verify xong.

---

## 27. Thiết kế versioning và atomic pointer

Giả sử hợp đồng `CONTRACT-100` có một file PDF hiện hành.

Thay vì upload mới đè file cũ:

```javascript
{
  _id: "CONTRACT-100",
  tenantId: "T100",
  currentFileId: ObjectId("6917a0000000000000000001"),
  businessVersion: 3
}
```

Khi cần cập nhật file:

1. Upload bản PDF mới vào GridFS, nhận `newFileId`.
2. Virus scan/verify/checksum bản mới.
3. Nếu thành công, cập nhật **một document contract** chuyển `currentFileId` sang `newFileId`.
4. Cho phép các readers mới dùng version mới.
5. Xử lý file cũ theo retention policy bằng job riêng.

Ví dụ atomic update có điều kiện:

```javascript
db.contracts.updateOne(
  {
    _id: "CONTRACT-100",
    currentFileId: oldFileId,
    businessVersion: 3
  },
  {
    $set: {
      currentFileId: newFileId,
      updatedAt: new Date()
    },
    $inc: {
      businessVersion: 1
    }
  }
);
```

Nếu `matchedCount === 0`, một writer khác có thể đã thay version; không nên xóa ngay file mới hoặc ghi đè pointer thiếu điều kiện.

**Điểm mạnh:** pointer switch là atomic ở cấp document, dù upload GridFS trước đó không atomic toàn file.

### 27.1. Không xóa file cũ quá sớm

Các readers cũ có thể đã lấy `oldFileId` và đang download. Xóa ngay có thể khiến download dở. Cần retention hoặc lease/reference counting phù hợp.

---

## 28. Metadata và business version khác nhau

GridFS filename revision:

```text
fileA name=contract.pdf time=10:00
fileB name=contract.pdf time=11:00
```

cho một cơ chế chọn “file mới nhất theo tên”.

Nhưng **business version** có thể là:

```text
contract version 3: Đã ký
contract version 4: Sửa phụ lục
contract version 5: Bị hủy
```

Không mặc định thứ tự upload trùng thứ tự trạng thái nghiệp vụ. Một file cũ có thể được upload lại để phục hồi; `uploadDate` khi đó mới hơn nhưng business version thấp hơn.

Vì vậy nên lưu business version trong document nghiệp vụ hoặc `metadata.businessVersion`, và dùng file ID chính xác cho mỗi version.

---

## 29. Sharding và GridFS

MongoDB GridFS có hai collections độc lập: `*.files` và `*.chunks`. Nếu sharded cluster, cần đánh giá sharding của từng collection.

### 29.1. Chunks collection

MongoDB Manual nêu các shard key pattern thường phù hợp cho `chunks`:

```javascript
{ files_id: 1, n: 1 }
```

hoặc:

```javascript
{ files_id: 1 }
```

Vì `files_id` thường là ObjectId tăng theo thời gian ở mức thô, ranged sharding có thể gây hotspot. Hashed sharding `files_id` có điều kiện phù hợp với driver behavior (đặc biệt nếu driver không dùng `filemd5` trong upload).

**Không tự chọn hashed shard key rồi cho rằng mọi driver/version đều tương thích**; kiểm tra ràng buộc trong MongoDB Manual.

### 29.2. Files collection

`*.files` chỉ chứa metadata nên thường nhỏ hơn nhiều so với `*.chunks`. MongoDB Manual khuyến nghị cân nhắc **để unsharded** nếu quy mô phù hợp; nếu bắt buộc shard files, có thể dùng `_id` hoặc kết hợp với field ứng dụng theo hướng dẫn.

### 29.3. Không nhầm sharding với chia file thành chunks

- GridFS chunks: chia **một file** thành nhiều BSON documents.
- Shard key: quyết định **document nào** nằm ở shard nào.
- Một file có thể có các chunks phân bố trên các shards tùy shard key/placement.
- Việc download phải lấy đủ chunks theo thứ tự; latency có thể tăng nếu đọc nhiều shards.

---

## 30. Hiệu năng: nhiều tệp đồng thời và memory budget

Giả sử một service có:

```text
Concurrent uploads:   30
Chunk size:            1 MiB
Java copy buffer:     64 KiB
MongoDB connections:  theo pool/driver
```

Tổng bộ nhớ không đơn thuần bằng `30 × 64 KiB`, vì driver, buffering, BSON decoding, HTTP framework và GC đều tiêu thụ thêm. Tuy nhiên, streaming cho phép **giới hạn bộ nhớ theo số kết nối/buffer**, thay vì tỷ lệ với tổng kích thước mọi file đang xử lý.

### 30.1. Những bottlenecks thường gặp

- Disk I/O của primary/shards.
- Replication bandwidth và majority acknowledgment.
- Network bandwidth giữa app và MongoDB.
- Chunk document/index write amplification.
- Connection pool quá nhỏ.
- GC vì ứng dụng dùng quá nhiều byte arrays.
- Chunk size quá lớn hoặc quá nhỏ.
- Concurrent uploads vượt quotas.
- Dữ liệu binary compress kém, tốn storage.
- Download chậm do HTTP client, không phải MongoDB.
- Backup/restore phải xử lý lượng chunks lớn.

### 30.2. Giới hạn concurrency

Nên có semaphore/rate limiting theo tenant và global limit. Không để một user mở hàng trăm upload streams rồi giữ connection pool của cả service.

### 30.3. CSOT và InputStream

Java Sync Driver hỗ trợ **Client-Side Operation Timeout (CSOT)** cho GridFS, ví dụ bucket có thể cấu hình `withTimeout(...)` trong phiên bản hỗ trợ.

Tài liệu lưu ý: khi `uploadFromStream()` đọc từ `InputStream`, Java `InputStream` không mặc định có read timeout; một stream block có thể làm thao tác vượt giới hạn thời gian dự tính trước khi timeout được ném.

Điều này có nghĩa cần **timeout ở nguồn HTTP/input**, không chỉ timeout ở MongoDB operation.

---

## 31. Download integrity: nhận diện tệp thiếu chunk

Một GridFS file theo cấu trúc hợp lệ cần:

1. Metadata `length` và `chunkSize` phù hợp.
2. Các chunk indices `n = 0, 1, ..., N-1` liên tiếp theo yêu cầu.
3. Các chunks, trừ cuối, có kích thước tương ứng `chunkSize`.
4. Tổng bytes ghép ra đúng `length`.

### 31.1. Tình huống lỗi

Giả sử metadata nói:

```text
length = 600 KiB
chunkSize = 255 KiB
Expected n = 0, 1, 2
```

Nhưng trong `chunks` chỉ có `n=0` và `n=2`. Đó là tệp thiếu chunk `n=1`. Driver download có thể báo lỗi/chunk corruption.

Không “chữa” bằng cách giảm `length` xuống 345 KiB; đó sẽ thay đổi ý nghĩa file và có thể vẫn sai thứ tự.

### 31.2. Phát hiện và xử lý

- Ghi metric GridFS download failures.
- Xác minh có đủ chunks và kiểm tra checksum SHA-256.
- Nếu đã có source of truth/backup, restore file hoặc reupload theo quy trình.
- Nếu file đã phục vụ client, đánh dấu integrity incident.
- Không tự tái tạo bytes thiếu bằng chuỗi zero hoặc nối chunks sai thứ tự.

---

## 32. Hệ thống nhiều tenant: bucket chung hay bucket riêng?

### 32.1. Bucket chung

```text
attachments.files
attachments.chunks
  metadata.tenantId = T1/T2/T3
```

Ưu điểm:

- Quản trị ít bucket/collections.
- Query/index metadata tập trung.
- Dễ dùng một service GridFS chung.

Nhược điểm:

- Phải **kiểm tra authorization ở mọi endpoint**.
- Một query chỉ theo file ID không tự lọc tenant.
- Retention/backup theo tenant khó hơn nếu yêu cầu tách biệt mạnh.

### 32.2. Bucket riêng theo tenant

```text
tenantA.files, tenantA.chunks
tenantB.files, tenantB.chunks
```

Có thể hỗ trợ tách vật lý ở mức collection naming, nhưng rất nhiều tenants tạo rất nhiều collections/indexes, tăng overhead quản trị. Bucket name do user cung cấp trực tiếp cũng dễ gây injection/tạo collection không kiểm soát.

**Không có một lựa chọn đúng cho tất cả hệ thống.** Cần đánh giá số tenant, quotas, isolation, compliance, backup và chi phí indexes.

### 32.3. File ID không phải authorization token

Không nên suy ra một ObjectId khó đoán là đủ bảo mật. Với:

```text
GET /files/6917a0000000000000000001
```

server vẫn phải xác minh user có quyền đọc file thuộc tenant tương ứng và file đang ở trạng thái được phép phục vụ.

---

## 33. Bảo mật upload/download

Checklist an toàn tối thiểu:

1. Giới hạn file size ở reverse proxy, web framework và streaming layer.
2. Giới hạn đồng thời số uploads theo user/tenant.
3. Validate file type và signature.
4. Quét malware nếu domain cần.
5. Không tin tên tệp do client cung cấp.
6. Không dùng filename như local filesystem path.
7. Phân quyền đọc/ghi GridFS bucket và metadata.
8. Không dùng file ID thay access control.
9. Dùng TLS, authentication và secret management.
10. Có quotas/disk alerts và retention policy.
11. Không log raw file content hoặc dữ liệu nhạy cảm.
12. Dùng `Content-Disposition`/MIME và `nosniff` an toàn.
13. Bảo vệ trước path traversal, CRLF injection và malicious filenames.
14. Cân nhắc encryption at rest và encryption in transit theo yêu cầu.
15. Chỉ publish trạng thái READY sau verification.
16. Có idempotency và retry budget cho upload.
17. Có audit cho download/delete và metadata changes.
18. Giữ backup/restore plan cho cả `files` và `chunks`.

### 33.1. Mã hóa file

MongoDB có các cơ chế bảo vệ dữ liệu ở tầng storage và connection. Nếu business yêu cầu **end-to-end encryption**, có thể mã hóa bytes ở application trước khi upload, lưu metadata về algorithm/key reference. Cần kế hoạch key rotation và streaming decrypt/download.

Đừng lưu raw encryption key trong `metadata` của cùng file.

### 33.2. Quét malware và ZIP bombs

Một ZIP nhỏ có thể giải nén thành dữ liệu cực lớn. Không chỉ kiểm tra byte length của file upload mà bỏ qua kiểm soát unpacking ở downstream. Nếu hệ thống cho preview PDF/ảnh hoặc giải nén, scanner/converter nên chạy trong môi trường sandbox với memory/CPU/time limits.

---

## 34. Idempotency khi client retry upload

Một HTTP client có thể retry vì timeout ở cuối upload:

```text
Client gửi POST /upload
Server hoàn tất GridFS upload, nhận fileId
Network đứt trước response
Client retry cùng request
Server lại upload file mới
```

Kết quả: hai file IDs với bytes giống nhau. GridFS **không tự phát hiện đây là cùng một HTTP request**.

### 34.1. Idempotency key

Một thiết kế:

```text
POST /uploads
Idempotency-Key: 8b7f...

Server:
  - ghi upload request record có unique (tenantId, key)
  - kiểm tra trạng thái PENDING/READY/FAILED
  - upload file
  - lưu fileId và kết quả
  - trả kết quả cũ khi nhận request cùng key
```

Nếu client retry cùng key nhưng nội dung khác, không được âm thầm trả “success” cho file cũ; phải so content fingerprint/parameters theo contract.

### 34.2. Không nhầm idempotency với dedup theo hash

Hai request có cùng SHA-256 có thể:

- Là cùng tài liệu bị gửi lại.
- Là hai attachment độc lập cùng nội dung nhưng thuộc hai hợp đồng khác nhau.
- Có chính sách retention/ownership khác.

Hash giống nhau không nhất thiết nghĩa là có thể bỏ một file business record. Dedup nếu dùng phải có reference counting, tenant isolation và lifecycle phù hợp.

---

## 35. Quản lý thời hạn lưu và xóa dữ liệu

Một tài liệu có thể cần:

- Lưu 7 năm theo chính sách.
- Xóa theo yêu cầu chủ thể dữ liệu.
- Bảo toàn legal hold.
- Giữ phiên bản cũ 30 ngày sau upload bản mới.
- Xóa tạm sau upload thất bại.

### 35.1. Job lifecycle theo metadata

```javascript
db.getSiblingDB("files_demo")
  .attachments.files
  .find({
    "metadata.state": "EXPIRED",
    "metadata.legalHold": { $ne: true }
  });
```

Job lấy file ID rồi gọi:

```java
bucket.delete(fileId);
```

Đừng gọi TTL index trên `*.files` như một cách tự động xóa chunks. Nếu delete fail, job cần retry/reconcile.

### 35.2. Soft delete vs physical delete

Một file có thể được đánh dấu:

```javascript
metadata: {
  state: "DELETED",
  deletedAt: ISODate("2026-11-14T08:00:00Z")
}
```

Soft delete chỉ chặn truy cập theo application; binary **vẫn còn tồn tại** cho đến khi gọi `delete(fileId)`. Với yêu cầu xóa thực sự, phải có physical cleanup, backup retention consideration và audit.

---

## 36. Sao lưu/khôi phục GridFS

Một backup đúng cần giữ **cả hai collections** của bucket:

```text
attachments.files
attachments.chunks
```

Nếu chỉ backup `attachments.files`:

- Có tên file, length, metadata.
- **Không có bytes** để download.

Nếu chỉ backup `attachments.chunks`:

- Có binary chunks.
- Thiếu metadata file để xác định file hoàn chỉnh, filename và length theo GridFS contract.

### 36.1. Backup consistency

Vì uploads ghi chunks rồi metadata qua nhiều operations, snapshot/backup phải được thực hiện bằng cơ chế nhất quán của MongoDB được hỗ trợ để tránh các trạng thái dở dang. Khi restore, cần kiểm tra random sample file lengths/checksums, số lượng file metadata và trạng thái orphan.

### 36.2. Restore sang môi trường khác

Nếu chuyển backup giữa environments, phải khôi phục đúng bucket name, IDs, metadata, indexes và phân quyền; không giả định collection `fs.files` là bucket `attachments`. Sau restore, chạy integrity checks và ứng dụng không được public file chưa verification.

---

## 37. Quan sát vận hành: metrics cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Uploads started/succeeded/failed | Tỉ lệ thành công upload |
| Download started/succeeded/failed | Tỉ lệ thành công download |
| Upload/download bytes per second | Băng thông |
| File size distribution | Dung lượng và chunk strategy |
| Average chunks per file | Tác động chunkSize |
| Upload/download p50/p95/p99 | Latency thực tế |
| Active upload/download streams | Áp lực concurrency |
| Connection pool utilization | Nguy cơ nghẽn pool |
| GridFS chunks collection size | Storage growth |
| Orphaned chunk candidates | Cleanup/backlog |
| Metadata state age | File bị kẹt PENDING/SCANNING |
| SHA-256 verification failures | Khả năng dữ liệu hỏng |
| Retry/idempotency conflicts | Request lặp hoặc không nhất quán |
| Files missing business pointer | Dangling files |
| Business pointer to missing file | Broken references |
| Replica lag/write concern timeouts | Durability/availability |
| Quota utilization | Rủi ro hết tài nguyên |

### 37.1. Đừng coi số file đủ để đo dung lượng

Một bucket có 10 triệu file 1 KiB khác hoàn toàn một bucket có 10.000 file 10 GiB. Theo dõi **bytes, chunk count và retention**, không chỉ `countDocuments()` trên `*.files`.

---

## 38. Các câu hỏi vận hành hay gặp

### 38.1. Upload success nhưng tìm không thấy file trong danh sách?

Kiểm tra:

- Bucket name đúng không (`fs` hay `attachments`)?
- Database đúng không?
- File metadata đã được finalize?
- Query metadata.tenantId/status có phù hợp không?
- Application đang filter READY trong khi metadata còn SCANNING?
- Read preference/replication visibility có chênh lệch không?
- FileId có thuộc kiểu BSON đúng không?

### 38.2. Không download được file dù có record metadata?

Có thể:

- File ID sai.
- Chunks thiếu/corrupt.
- Bucket name/database sai.
- Metadata record bị sửa trực tiếp.
- Authorization chặn.
- Dữ liệu bị rollback/missing do lỗi write concern.
- Restore thiếu `*.chunks`.

### 38.3. Vì sao cùng tên có nhiều file?

Đó là behavior bình thường của GridFS; mỗi upload là một file ID/version mới. Dùng `find` và `GridFSDownloadOptions.revision(...)` hoặc lưu business pointer.

### 38.4. Có thể thêm metadata sau upload?

Có. Update `metadata.<field>` trong `*.files`, nhưng không sửa field hệ thống `length`/`chunkSize`. Nếu cần checksum từ stream một lượt, có thể thêm sau và chuyển state READY khi verification hoàn tất.

### 38.5. Đổi tên có chuyển/mã hóa lại bytes không?

Không. GridFS `rename(fileId, name)` đổi metadata filename của một file, không phải upload nội dung mới.

### 38.6. Xóa fs.files bằng deleteOne là đủ?

Không. Nó không chạy logic GridFS để xóa tất cả chunks. Hãy dùng `GridFSBucket.delete(fileId)`; nếu đã xóa raw metadata, cần quy trình cleanup orphan an toàn.

---

## 39. Bài tập thực hành

### Bài 1 — Xác định số chunks

Một file 600 KiB được upload với chunkSize 255 KiB.

**Hỏi:** Có bao nhiêu chunks và kích thước từng chunk?

**Đáp án:** 3 chunks: 255 KiB, 255 KiB và 90 KiB.

### Bài 2 — Hai collection

Bucket mặc định tên `fs` được lưu trong database `training`.

**Hỏi:** Tên hai collections?

**Đáp án:** `training.fs.files` và `training.fs.chunks`.

### Bài 3 — Tên bucket tùy chỉnh

Java:

```java
GridFSBuckets.create(database, "documents");
```

**Hỏi:** Các collection?

**Đáp án:** `documents.files` và `documents.chunks` trong database đó.

### Bài 4 — Số thứ tự chunk

Một chunk có `n: 0`.

**Hỏi:** Nó là chunk thứ mấy?

**Đáp án:** Chunk đầu tiên; numbering bắt đầu từ 0.

### Bài 5 — Download file lớn

Developer viết:

```java
byte[] data = new byte[(int) gridFSFile.getLength()];
```

**Hỏi:** Rủi ro?

**Đáp án:** Overflow khi length > int max, OOM, không streaming. Dùng `openDownloadStream` và buffer nhỏ.

### Bài 6 — Metadata MIME

Team ghi `contentType` ở top-level `fs.files`.

**Hỏi:** Khuyến nghị hiện đại?

**Đáp án:** Top-level contentType deprecated; dùng `metadata.contentType` và validate MIME.

### Bài 7 — MD5

File cần checksum để phát hiện dữ liệu hỏng.

**Hỏi:** Có nên chỉ dùng `fs.files.md5`?

**Đáp án:** Không. MD5 deprecated; ứng dụng tính SHA-256 hoặc digest phù hợp, lưu trong metadata.

### Bài 8 — Revision

Ba lần upload `"report.pdf"` theo thời gian. Lấy revision 0 và -1 là file nào?

**Đáp án:** Revision 0 là bản cũ nhất; -1 là bản mới nhất.

### Bài 9 — Cập nhật file

Muốn user mới thấy file bản 4 nhưng readers cũ vẫn tải được bản 3.

**Gợi ý:** Upload bản 4 dưới file ID mới, verify, cập nhật atomic pointer trong document nghiệp vụ, giữ bản 3 theo retention.

### Bài 10 — Lỗi giữa upload

Upload fail sau ba chunks và trước khi có `fs.files` metadata.

**Hỏi:** Điều gì có thể còn?

**Đáp án:** Orphaned chunks; phải cleanup an toàn, không xóa các chunks của upload đang chạy.

### Bài 11 — TTL

Team tạo TTL index trên `fs.files.uploadDate` để xóa file sau 7 ngày.

**Hỏi:** Vấn đề?

**Đáp án:** Chỉ metadata documents bị TTL delete; chunks không tự được xóa theo GridFS API. Dùng lifecycle job gọi bucket.delete.

### Bài 12 — Đổi tên

Hai file IDs A/B có cùng tên. Developer gọi `rename(A, "new.pdf")`.

**Hỏi:** B có đổi tên không?

**Đáp án:** Không; chỉ file A.

### Bài 13 — Index chunks

Cần giữ thứ tự và tính duy nhất của chunk theo file.

**Đáp án:** Index unique `{files_id:1,n:1}`.

### Bài 14 — Index metadata

UI list file theo tenant/status/newest.

**Gợi ý:** Thử compound index `{"metadata.tenantId":1, "metadata.state":1, uploadDate:-1}` rồi explain workload.

### Bài 15 — Tenant isolation

User biết ObjectId của file thuộc tenant khác.

**Hỏi:** Có được download chỉ vì ID đúng?

**Đáp án:** Không. Phải xác minh quyền từ authenticated context và metadata/business ACL.

### Bài 16 — Checksum một lượt

Input stream chỉ đọc được một lần; checksum chỉ hoàn tất sau upload.

**Gợi ý:** Tính digest khi streaming, cập nhật metadata sau thành công, chỉ READY sau verify; xử lý khoảng hở update.

### Bài 17 — HTTP response lỗi giữa chừng

Server đã ghi 3 MiB bytes tới client rồi phát hiện chunk tiếp theo thiếu.

**Hỏi:** Có thể trả một JSON status 500 hoàn chỉnh không?

**Đáp án:** Không thể thay thế body đã gửi. Abort/close connection, log, client xử lý partial download.

### Bài 18 — Empty file

Một file có 0 bytes.

**Hỏi:** Có bắt buộc tạo chunk data size 255 KiB không?

**Đáp án:** Không. File rỗng có metadata length 0 và không cần dữ liệu chunk.

### Bài 19 — Sharding

Team muốn dùng `location: "2dsphere"` làm shard key cho `fs.chunks`.

**Đáp án:** Không phù hợp. GridFS chunks có key pattern riêng; xem `files_id` và `n` theo hướng dẫn sharding GridFS.

### Bài 20 — File storage so với object storage

Ứng dụng phục vụ video 10 GiB cho nhiều người dùng toàn cầu, có CDN, range requests và transcoding.

**Gợi ý:** Đánh giá object storage/CDN chuyên dụng so với GridFS; không chọn chỉ vì MongoDB đã có sẵn.

---

## 40. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “GridFS là một collection duy nhất.” | Là bucket gồm `files` và `chunks` collections. |
| “File GridFS vẫn phải dưới 16 MiB.” | Một chunk document chịu giới hạn BSON, file tổng có thể lớn hơn nhiều. |
| “Mỗi file luôn chia thành chunks 255 KiB đầy đủ.” | Chunk cuối có thể nhỏ hơn; file rỗng có thể không có chunks. |
| “Driver trả ID khi bắt đầu upload tức đã thành công.” | Cần đợi upload/finalization hoàn tất và xử lý exception. |
| “GridFS hỗ trợ multi-document transactions.” | Không; cần application consistency patterns. |
| “Upload fail luôn được rollback toàn bộ.” | Có thể còn orphaned chunks. |
| “Xóa fs.files sẽ xóa fs.chunks theo cascade.” | Không; phải dùng GridFS delete/cleanup. |
| “TTL trên fs.files tự xóa binary.” | Không; TTL chỉ xóa metadata document. |
| “Filename là khóa duy nhất.” | Nhiều versions có thể cùng filename. |
| “Revision 0 là mới nhất.” | Revision 0 là cũ nhất; -1 là mới nhất. |
| “MD5 luôn được GridFS tạo và đủ an toàn.” | MD5 deprecated; dùng hash ứng dụng như SHA-256. |
| “contentType phải nằm top-level.” | Field cũ deprecated; lưu trong metadata. |
| “Content-Type từ client chứng minh file là PDF.” | Phải validate bytes/file signature theo policy. |
| “InputStream streaming luôn giữ cả file trong RAM.” | Có thể xử lý theo chunks/buffer nhỏ. |
| “Một lần InputStream.read(bytes) luôn đọc đủ.” | Không; phải loop. |
| “DownloadToStream trả dữ liệu theo thứ tự ObjectId chunk.” | GridFS sắp theo `n`. |
| “Cập nhật length là cách sửa file hỏng.” | Không; có thể khiến GridFS corruption tệ hơn. |
| “WriteConcern w:1 luôn an toàn sau election.” | Có thể rollback chunks; driver khuyến nghị majority. |
| “Có metadata file nghĩa mọi chunks chắc chắn còn.” | Phải xét lỗi partial/rollback/corruption. |
| “Mọi request download by ID được phép.” | ID không thay authorization. |
| “GridFS Bucket là object storage/CDN toàn năng.” | Cần benchmark so với nhu cầu stream/range/global delivery. |
| “Đổi filename làm thay đổi file bytes.” | Rename chỉ đổi tên. |
| “Tạo MongoClient mỗi request không sao.” | Gây connection churn/pool overhead. |
| “Tăng chunk size luôn nhanh hơn.” | Đánh đổi memory, index docs, range access, concurrency. |
| “Số file là metric dung lượng.” | Cần bytes/chunk count và retention. |
| “Checksum bằng nhau nghĩa hai business files chắc chắn cùng một bản ghi.” | Cần lifecycle/ownership/tenant chính sách dedup. |
| “Soft delete là đã xóa binary.” | Chưa; phải physical delete theo retention. |
| “Backup fs.files đủ để restore.” | Cần cả files và chunks nhất quán. |
| “Chỉ có upload thành công là asset READY.” | Có thể còn scan/checksum/approval. |
| “Sync Driver upload từ InputStream là non-blocking.” | Sync Driver blocking; reactive cần API khác. |

---

## 41. Checklist production

1. GridFS có phù hợp file sizes và access patterns không?
2. Có cần object storage/CDN thay cho hoặc phối hợp với GridFS?
3. Đã chọn database và bucket name rõ chưa?
4. Có bảo đảm `*.files` và `*.chunks` indexes mặc định?
5. Chunk size phù hợp workload và memory budget?
6. Upload thực sự streaming, không `readAllBytes` file lớn?
7. Download thực sự streaming và xử lý partial output?
8. Input size limit được kiểm soát bằng bytes thực nhận?
9. File type/signature và malware scan phù hợp?
10. Filename được sanitize và không dùng làm path trực tiếp?
11. MIME đặt trong `metadata.contentType` và validate?
12. Có SHA-256/checksum và quy trình verify?
13. Có phân biệt file ID với filename/revision?
14. Có policy versioning và atomic business pointer?
15. Có trạng thái UPLOADING/SCANNING/READY/FAILED?
16. Có retry/idempotency cho HTTP upload timeout?
17. Có cleanup orphan chunks với grace period an toàn?
18. Delete theo GridFSBucket.delete, không TTL trực tiếp files?
19. Có retention/legal hold/backup/restore plan?
20. Có majority write concern trên GridFS upload?
21. Có xử lý primary election/replica lag/timeout?
22. Có authorization khi list lẫn download by ID?
23. Có tenant isolation và quotas cho data/throughput?
24. Có metadata indexes phục vụ query/list?
25. Có monitor file/chunks count, bytes, upload/download p99?
26. Có concurrency limits và connection pool sizing?
27. Nếu HTTP Range cần hỗ trợ, đã implement 206/416 đúng contract?
28. Có bảo vệ response headers, nosniff và filename encoding?
29. Có kiểm tra restore file checksum sau backup?
30. Có test lỗi giữa upload/download và crash/failover?

Sơ đồ tổng thể:

```text
User sends file
      |
      v
Authenticate + authorize
      |
      v
Validate size/type/name
      |
      v
InputStream -> GridFSBucket
      |
      +--> *.chunks n=0,1,2,...
      |
      +--> *.files metadata
      |
      v
Upload success -> fileId
      |
      v
Scan/checksum/verify
      |
      v
Update state READY
      |
      v
Atomic business pointer
      |
      v
Download by authorized fileId
      |
      v
GridFSDownloadStream -> HTTP OutputStream
      |
      v
Client receives bytes
```

---

## 42. Tài liệu chính thức và tham khảo

- [GridFS — MongoDB Manual](https://www.mongodb.com/docs/manual/core/gridfs/): cơ chế, hai collections, chunk mặc định, indexes, transactions và lựa chọn sử dụng.
- [Large File Storage with GridFS — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/): tạo GridFSBucket, upload/download theo stream, metadata, revision, rename/delete.
- [GridFS Specification](https://github.com/mongodb/specifications/tree/master/source/gridfs): hợp đồng giữa các drivers và định dạng files/chunks.
- [Java GridFSBucket API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/GridFSBucket.html): overloads của upload/download và cấu hình bucket; chọn phiên bản API khớp dependency.
- [Java GridFSUploadOptions API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/model/GridFSUploadOptions.html): chunk size và metadata.
- [Java GridFSDownloadOptions API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/model/GridFSDownloadOptions.html): revision khi tải theo filename.
- [Client-Side Operation Timeout — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): GridFS timeout và giới hạn InputStream timeout.
- [Write Concern — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/write-concern/): `w: "majority"` và durability.
- [BSON Document Size](https://www.mongodb.com/docs/manual/reference/limits/#bson-document-size): giới hạn 16 MiB mỗi BSON document.
- [ObjectId](https://www.mongodb.com/docs/manual/reference/bson-types/#objectid): ID, kiểu BSON và các lưu ý về uniqueness.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/): nguyên tắc compound index và cost index maintenance.
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/): bảo toàn dữ liệu collections ở trạng thái có thể phục hồi.

Tài liệu MongoDB Server/Java Sync Driver có thể thay đổi giữa các bản. Trước khi production, đối chiếu chính xác **server version, driver version, topology, GridFS bucket name và write/read concern** của hệ thống đang vận hành.

## 43. Kết luận

**GridFS** lưu file lớn dưới dạng nhiều `chunks` và một document metadata trong `files`. Bucket mặc định `fs` tạo `fs.files` và `fs.chunks`; chunk mặc định **255 KiB**, thứ tự đọc theo `n` và file được định danh bằng `_id` chứ không phải filename.

Với **Java Sync Driver**, có thể upload bằng `uploadFromStream(InputStream)` hoặc tự ghi vào `GridFSUploadStream`, rồi download bằng `downloadToStream(OutputStream)` hoặc đọc `GridFSDownloadStream`. Thiết kế theo luồng cho phép xử lý file rất lớn mà không load toàn bộ bytes vào heap.

**Metadata** nên lưu tenant/owner, MIME type, business ID, checksum SHA-256, version và trạng thái READY trong `metadata`, tránh những fields cũ deprecated như top-level `contentType` hoặc `md5`. Tải theo filename cần hiểu revision: `0` là bản cũ nhất và `-1` là mới nhất.

Cuối cùng, vì GridFS **không hỗ trợ multi-document transactions**, upload hoặc delete giữa chừng có thể để lại chunks dở dang. Hệ thống production cần **majority write concern**, idempotency, checksum, scan, orphan cleanup, immutable file versions và atomic business pointer. Download còn cần authorization, MIME/header safety và xử lý HTTP partial response.

**GridFS giải quyết bài toán lưu/truyền tệp theo chunks; ứng dụng phải thiết kế thêm vòng đời, tính nhất quán, quyền truy cập và khả năng phục hồi để tệp thực sự đáng tin cậy.**
