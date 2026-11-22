# Đọc theo phạm vi, quản lý tên tệp và nhiều phiên bản với MongoDB GridFS

## Mục tiêu bài học

**MongoDB GridFS** là một quy ước lưu trữ và truy xuất nội dung tệp bằng cách chia byte thành nhiều **chunks** và giữ metadata trong những document riêng. Người dùng thường biết đến GridFS khi cần lưu tệp lớn hơn giới hạn BSON document **16 MiB**, nhưng ba tính năng làm GridFS đặc biệt hữu ích cho ứng dụng thực tế là:

1. **Đọc theo phạm vi byte** (partial/range read): phát video, nghe audio, tải tiếp tệp bị ngắt, chỉ đọc header hoặc một đoạn tài liệu.
2. **Quản lý tên tệp**: tìm theo tên, đổi tên, tránh nhầm tên hiển thị với định danh tệp, xử lý nhiều tệp trùng tên.
3. **Quản lý nhiều phiên bản**: lưu các bản upload của cùng một tên, chọn revision cũ/mới hoặc pin vào đúng `fileId`, phục hồi và xóa theo chính sách.

Bài thuộc **Database Engine Document MongoDB → GridFS → Đọc theo phạm vi, quản lý tên tệp và nhiều phiên bản**.

Sau bài học, bạn có thể:

- Mô tả cấu trúc `fs.files`/`fs.chunks` và mối quan hệ `files_id + n`.
- Tính chunk chứa một khoảng byte và xử lý biên đầu/cuối tệp.
- Dùng stream GridFS để bỏ qua những byte phía trước và đọc chính xác số byte yêu cầu, thay vì tải cả tệp vào RAM.
- Ánh xạ HTTP `Range` sang GridFS và phân biệt phản hồi `200`, `206`, `416`.
- Dùng `GridFSBucket`, `GridFSDownloadStream` và `GridFSDownloadOptions` của Java Sync Driver.
- Tải theo `fileId` hoặc theo `filename`, chọn revision `0`, `1`, `-1`, `-2`.
- Đổi tên và xóa đúng một bản bằng ID, không xóa nhầm tất cả các bản cùng tên.
- Thiết kế logical asset + immutable file versions + active pointer để tránh ghi đè khi hai người upload đồng thời.
- Xây indexes tìm kiếm metadata, chính sách retention, integrity và authorization.
- Nhận diện các rủi ro upload dang dở, xóa khi có người đang đọc, chunk hỏng và giới hạn transaction của GridFS.
- So sánh GridFS với BSON BinData, object storage, CDN và các trường hợp không nên dùng GridFS.
- Kiểm thử range request, concurrency, zero-length file, revision ordering và cache/ETag.

> **Nguyên tắc quan trọng nhất:** `filename` là **nhãn hiển thị, không phải khóa duy nhất**. Mỗi lần upload phải có một `fileId` riêng. Khi cần đọc đúng một bản hoặc xóa/đổi tên có kiểm soát, ưu tiên làm việc bằng `fileId`.

---

## 1. Vì sao GridFS chia tệp thành chunks?

### 1.1. Giới hạn BSON document

MongoDB giới hạn kích thước một BSON document ở **16 MiB**. Một tệp PDF, video hoặc file archive có thể vượt xa giới hạn đó. Không thể tùy ý đặt toàn bộ tệp 200 MiB vào một field `BinData` trong một document.

GridFS lưu:

~~~text
user file: video.mp4 (nhiều MiB)
              |
              v
       GridFS upload API
              |
       +------+------+
       |             |
       v             v
   fs.files       fs.chunks
   1 document     N documents
   metadata       binary pieces
~~~

### 1.2. Bucket là gì?

Bucket là một cặp collection có cùng prefix:

| Bucket name | Collection metadata | Collection dữ liệu |
|---|---|---|
| `fs` (mặc định) | `fs.files` | `fs.chunks` |
| `attachments` | `attachments.files` | `attachments.chunks` |
| `videos` | `videos.files` | `videos.chunks` |

Một database có thể có nhiều buckets. Bucket name là cách tổ chức, **không phải tự động là lớp phân quyền tenant**.

### 1.3. Chunk size mặc định

GridFS dùng kích thước chunk mặc định **255 KiB**:

\[
C = 255 \times 1024 = 261\,120\text{ bytes}
\]

Mọi chunk đầy đủ trừ chunk cuối; chunk cuối chỉ giữ số byte còn lại. Tệp rỗng có document `fs.files` với `length:0`, **không cần chunk rỗng**.

### 1.4. Metadata trong `fs.files`

Ví dụ (ObjectId minh họa):

~~~javascript
{
  _id: ObjectId("6914a9aa0000000000000001"),
  length: NumberLong("600000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T02:30:00Z"),
  filename: "training.mp4",
  metadata: {
    tenantId: "tenant-a",
    assetId: "ASSET-101",
    logicalVersion: 1,
    contentType: "video/mp4",
    sha256: "hash-do-ung-dung-tinh",
    uploadedBy: "user-101"
  }
}
~~~

Các field cốt lõi:

| Field | Vai trò |
|---|---|
| `_id` | Định danh duy nhất **một nội dung GridFS đã upload** |
| `length` | Kích thước logic của tệp, tính bằng byte |
| `chunkSize` | Số byte mục tiêu mỗi chunk |
| `uploadDate` | Thời điểm upload metadata được tạo |
| `filename` | Tên tệp; có thể **trùng** trên nhiều documents |
| `metadata` | Thông tin mở rộng do ứng dụng định nghĩa |

**Lưu ý:** Các field legacy như `md5`, top-level `contentType`, `aliases` đã bị GridFS spec xem là deprecated. Nên dùng `metadata.contentType`/`metadata.aliases` và checksum mạnh do ứng dụng quản lý nếu cần.

### 1.5. Chunks trong `fs.chunks`

~~~javascript
{
  _id: ObjectId("6914b0bb0000000000000001"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 0,
  data: BinData(0, "...")
}

{
  _id: ObjectId("6914b0bb0000000000000002"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 1,
  data: BinData(0, "...")
}

{
  _id: ObjectId("6914b0bb0000000000000003"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 2,
  data: BinData(0, "...")
}
~~~

`files_id` liên kết tới `fs.files._id`; `n` là số thứ tự **bắt đầu từ 0**. GridFS driver ghép các chunk theo `n` để tái tạo dòng byte.

### 1.6. Chunk GridFS khác chunk sharding

Từ “chunk” ở đây là **mảnh dữ liệu của một tệp**. Nó **không phải** khái niệm chunk/range dùng cho phân mảnh dữ liệu trong MongoDB sharded cluster.

---

## 2. Một tệp 600.000 bytes được chia ra sao?

Với chunk size mặc định:

~~~text
File length L = 600000 bytes
Chunk size C = 261120 bytes

Chunk n=0: bytes 0      .. 261119   => 261120 bytes
Chunk n=1: bytes 261120 .. 522239   => 261120 bytes
Chunk n=2: bytes 522240 .. 599999   =>  77760 bytes
~~~

Tổng:

\[
261120 + 261120 + 77760 = 600000
\]

### 2.1. Số chunk cần lưu

Với `L > 0`:

\[
N = \left\lceil \frac{L}{C} \right\rceil
\]

Với `L=0`, số chunk là 0.

Ví dụ:

| Kích thước tệp | Số chunk, nếu C=261120 |
|---:|---:|
| 0 B | 0 |
| 1 B | 1 |
| 261119 B | 1 |
| 261120 B | 1 |
| 261121 B | 2 |
| 522240 B | 2 |
| 600000 B | 3 |

### 2.2. Tệp lớn không cần nạp tất cả vào RAM

Khi đọc stream, ứng dụng có thể lấy từng chunk và trả dần ra HTTP response/output stream. Cách này tránh:

~~~java
byte[] entireFile = new byte[(int) fileLength];
~~~

Đoạn code trên vừa tiêu thụ RAM theo kích thước tệp, vừa có rủi ro overflow/cấp phát không hợp lệ nếu tệp vượt giới hạn `int`.

### 2.3. Mỗi tệp có chunkSize riêng

`fs.files.chunkSize` được lưu cho **mỗi tệp**. Nếu ứng dụng đổi default chunk size, những tệp upload trước đó không tự chia lại. Khi tính range, luôn đọc `chunkSize` từ document tệp thực tế, không hard-code global 255 KiB.

---

## 3. Đọc theo phạm vi byte là gì?

Giả sử người dùng muốn xem giây thứ 20 của video nhưng trình phát chỉ cần một đoạn byte tương ứng. Hoặc một file viewer cần 4 KiB đầu để đọc header.

Không cần tải toàn bộ:

~~~text
File: [..................................................]
      0                                               L-1

Range cần đọc:
                [==========]
                start       end
~~~

### 3.1. Hai quy ước khoảng thường gặp

Trong xử lý byte nội bộ, dùng khoảng **nửa mở**:

\[
[start,\ endExclusive)
\]

Số byte:

\[
length = endExclusive - start
\]

Trong HTTP `Range: bytes=a-b`, đầu và cuối đều **bao gồm**:

\[
[a,\ b]
\]

Số byte:

\[
length = b - a + 1
\]

### 3.2. Ví dụ một range

~~~http
GET /files/6914a9aa0000000000000001 HTTP/1.1
Range: bytes=1000-1999
~~~

Nếu hợp lệ, response:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 1000-1999/600000
Content-Length: 1000
Content-Type: video/mp4
~~~

Backend phải gửi **đúng 1.000 bytes** ở offsets 1000 đến 1999. Không gửi 1.001 bytes do nhầm điều kiện biên.

### 3.3. Ba dạng Range thường gặp

| Header | Ý nghĩa |
|---|---|
| `bytes=0-1023` | 1.024 byte đầu |
| `bytes=500-` | Từ byte 500 đến hết |
| `bytes=-500` | 500 byte cuối |
| `bytes=0-0` | Chỉ byte đầu |

`bytes=-500` **không phải** offset âm; đó là dạng suffix-range.

### 3.4. HTTP Range khác `skip` ở mức API

HTTP biểu diễn yêu cầu của client. GridFS driver cung cấp **stream đọc dữ liệu**; ứng dụng HTTP phải chuyển đổi header thành offset và số byte đọc, đồng thời tự xây status/headers tương ứng.

---

## 4. Công thức xác định các chunks chứa range

Giả sử:

- `L` = kích thước file.
- `C` = `chunkSize` trong `fs.files`.
- `a` = offset đầu **inclusive**.
- `b` = offset cuối **inclusive**.

Điều kiện với tệp không rỗng:

\[
0 \leq a \leq b < L
\]

Chunk đầu tiên:

\[
firstChunk = \left\lfloor \frac{a}{C} \right\rfloor
\]

Chunk cuối:

\[
lastChunk = \left\lfloor \frac{b}{C} \right\rfloor
\]

Offset bên trong chunk đầu:

\[
offsetInFirst = a \bmod C
\]

### 4.1. Ví dụ cắt qua ranh giới chunk

Với tệp 600.000 B và C=261120:

~~~text
Yêu cầu: bytes=260000-263000

Chunk 0: [0 ........ 261119]
                  ^ từ 260000
Chunk 1: [261120 ......... 522239]
          ^ đến 263000

firstChunk = floor(260000 / 261120) = 0
lastChunk  = floor(263000 / 261120) = 1

Chunk 0 lấy: 261120 - 260000 = 1120 bytes
Chunk 1 lấy: 263000 - 261120 + 1 = 1881 bytes

Tổng = 3001 bytes
~~~

### 4.2. Ví dụ nằm trong một chunk

~~~text
Range: bytes=270000-275000

firstChunk = 1
lastChunk  = 1
offsetInFirst = 270000 - 261120 = 8880
length = 5001 bytes
~~~

Nếu không hiểu ranh giới, dễ lấy nhầm chunk hoặc có lỗi off-by-one.

### 4.3. Cách truy xuất trực tiếp ở mức mô hình

Về mặt dữ liệu:

~~~javascript
db.fs.chunks.find({
  files_id: fileId,
  n: {
    $gte: firstChunk,
    $lte: lastChunk
  }
}).sort({ n: 1 });
~~~

Ví dụ này giúp hiểu chunk math, **không phải lời khuyên tự viết lại toàn bộ GridFS driver**. Driver còn kiểm tra thứ tự, kích thước chunk, lỗi đọc và nhiều chi tiết tương thích. Với code ứng dụng bình thường, ưu tiên API stream của driver.

### 4.4. Chỉ đọc một phần không kiểm tra toàn bộ tệp

Nếu client chỉ đọc đến byte 1023 rồi đóng stream, driver có thể chưa phát hiện corruption ở những chunks sau. GridFS spec yêu cầu kiểm tra thứ tự/kích thước các chunks **đã được đọc**, nhưng range read một đoạn không tự chứng minh toàn bộ tệp còn nguyên vẹn.

---

## 5. Java GridFSDownloadStream và `skip(long)`

### 5.1. Tạo GridFS bucket

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

MongoDatabase db = mongoClient.getDatabase("media_lab");

GridFSBucket bucket = GridFSBuckets.create(
    db,
    "media"
);
~~~

Bucket tên `media` dùng hai collection `media.files` và `media.chunks`.

### 5.2. Mở stream theo ID

~~~java
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

ObjectId fileId =
    new ObjectId("6914a9aa0000000000000001");

try (GridFSDownloadStream input =
         bucket.openDownloadStream(fileId)) {

    long fileLength =
        input.getGridFSFile().getLength();

    System.out.println("File length: " + fileLength);
}
~~~

`GridFSDownloadStream` là một stream đọc; phải đóng sau khi xong, kể cả khi client ngắt kết nối.

### 5.3. `skip` có thể không bỏ đủ số byte trong một lần

Hợp đồng `InputStream.skip(n)` cho phép kết quả nhỏ hơn n. Code đúng không chỉ viết:

~~~java
input.skip(start); // Chưa chắc đã skip đủ start bytes.
~~~

rồi đọc.

Hãy kiểm tra số byte thực sự đã bỏ.

### 5.4. Hàm `skipFully`

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static void skipFully(
        InputStream input,
        long bytesToSkip) throws IOException {

    if (bytesToSkip < 0) {
        throw new IllegalArgumentException(
            "Offset không được âm"
        );
    }

    long remaining = bytesToSkip;

    while (remaining > 0) {
        long moved = input.skip(remaining);

        if (moved <= 0) {
            // Fallback để tiến thêm đúng một byte.
            if (input.read() == -1) {
                throw new EOFException(
                    "EOF trước offset cần đọc"
                );
            }

            moved = 1;
        }

        remaining -= moved;
    }
}
~~~

Code đảm bảo stream tiến tới offset khi dữ liệu đủ. Tối ưu tìm chunk ở driver phụ thuộc implementation; không tự tuyên bố `skip` luôn là O(1) hoặc không chạm các chunks phía trước. Đo lượng I/O thật nếu workload thường xuyên đọc offset rất lớn.

### 5.5. Hàm đọc chính xác số byte

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

static void copyExactly(
        InputStream input,
        OutputStream output,
        long count) throws IOException {

    if (count < 0) {
        throw new IllegalArgumentException(
            "Số byte cần đọc không hợp lệ"
        );
    }

    byte[] buffer = new byte[64 * 1024];
    long remaining = count;

    while (remaining > 0) {
        int wanted = (int) Math.min(
            buffer.length,
            remaining
        );

        int read = input.read(
            buffer, 0, wanted
        );

        if (read == -1) {
            throw new EOFException(
                "GridFS thiếu bytes trong đoạn yêu cầu"
            );
        }

        if (read == 0) {
            continue;
        }

        output.write(buffer, 0, read);
        remaining -= read;
    }
}
~~~

### 5.6. Kết hợp để đọc range

~~~java
import com.mongodb.client.gridfs.GridFSDownloadStream;
import java.io.IOException;
import java.io.OutputStream;
import org.bson.types.ObjectId;

static void streamRange(
        GridFSBucket bucket,
        ObjectId fileId,
        long start,
        long endInclusive,
        OutputStream output) throws IOException {

    if (start < 0 || endInclusive < start) {
        throw new IllegalArgumentException(
            "Khoảng đọc không hợp lệ"
        );
    }

    try (GridFSDownloadStream input =
             bucket.openDownloadStream(fileId)) {

        long total =
            input.getGridFSFile().getLength();

        if (start >= total
                || endInclusive >= total) {
            throw new IllegalArgumentException(
                "Range nằm ngoài tệp"
            );
        }

        skipFully(input, start);

        long count =
            endInclusive - start + 1;

        copyExactly(input, output, count);
    }
}
~~~

Điểm quan trọng:

- Dùng `long` cho offset/length.
- Không cấp phát byte array kích thước cả tệp.
- Kiểm tra `endInclusive < total`.
- Đếm đúng số byte.
- Mỗi request mở stream riêng.
- `try-with-resources` đóng stream khi xong/lỗi.
- Lỗi giữa stream HTTP có thể khiến response đã gửi headers rồi không thể đổi thành `500`; cần metrics và kết thúc kết nối đúng.

### 5.7. `downloadToStream` khác `openDownloadStream`

`bucket.downloadToStream(id, output)` là cách thuận tiện để tải **toàn bộ** tệp ra output stream. Khi cần partial range, `openDownloadStream` với stream position/reading thường linh hoạt hơn.

Không dùng `downloadToStream` rồi tải cả file vào `ByteArrayOutputStream` để cắt vài byte cuối: điều đó phá lợi ích streaming.

---

## 6. HTTP Range: ánh xạ đúng 200, 206 và 416

### 6.1. Full file: HTTP 200

Request không có `Range`:

~~~http
GET /api/files/6914a9aa0000000000000001 HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Length: 600000
Content-Type: application/octet-stream
ETag: "6914a9aa0000000000000001"
~~~

Body là toàn bộ 600.000 byte.

### 6.2. Partial file: HTTP 206

~~~http
GET /api/files/6914a9aa0000000000000001 HTTP/1.1
Range: bytes=260000-263000
~~~

Response:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 260000-263000/600000
Content-Length: 3001
Content-Type: application/octet-stream
~~~

### 6.3. Range không thể thỏa: HTTP 416

Nếu tệp dài 600.000 B:

~~~http
Range: bytes=700000-800000
~~~

phải tránh cố skip tới offset vượt EOF. Một phản hồi chuẩn cho unsatisfiable byte range:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */600000
~~~

### 6.4. Tệp rỗng

`length=0`:

- Không có byte hợp lệ để đáp ứng `bytes=0-0`.
- Request không có range → `200` với `Content-Length:0`.
- Request range không thể thỏa → `416` với `Content-Range: bytes */0`.

### 6.5. Open-ended range

Với `Range: bytes=500-`:

~~~text
start = 500
endInclusive = L - 1
count = L - 500
~~~

Nếu `start >= L`, range không thể thỏa.

### 6.6. Suffix range

`Range: bytes=-500`:

~~~text
count = min(500, L)
start = L - count
endInclusive = L - 1
~~~

Với tệp 600.000 B, lấy byte 599500–599999.

### 6.7. Nếu end lớn hơn file length

`Range: bytes=500-999999` với `L=600000` vẫn có thể trả đoạn từ 500 đến 599999, tức clamp end theo tệp. Không báo 416 chỉ vì end vượt length nếu start còn hợp lệ.

### 6.8. Multiple ranges

~~~http
Range: bytes=0-99,200-299
~~~

Đây là **multi-range request**. Để đáp ứng đầy đủ, server cần `multipart/byteranges` với boundary, nhiều `Content-Range` và body đúng định dạng.

Nếu gateway chỉ hỗ trợ single range, có thể **bỏ qua Range và trả toàn bộ `200`** theo HTTP semantics, thay vì giả vờ hỗ trợ nhiều range nhưng chỉ gửi một đoạn. Cần tránh trả `206` sai chuẩn.

---

## 7. Java: lập kế hoạch một HTTP Range an toàn

Hàm này minh họa parser cho một range hợp lệ. Tách phần **parse + validate** khỏi phần **đọc GridFS** để dễ kiểm thử.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

record ByteRange(
    long start,
    long endInclusive,
    long total
) {
    long contentLength() {
        return endInclusive - start + 1;
    }

    String contentRange() {
        return "bytes " + start
            + "-" + endInclusive
            + "/" + total;
    }
}

static final Pattern SINGLE_RANGE =
    Pattern.compile("^bytes=(\\d*)-(\\d*)$");

static ByteRange parseSingleRange(
        String header,
        long total) {

    if (total < 0) {
        throw new IllegalArgumentException(
            "Metadata length không hợp lệ"
        );
    }

    Matcher matcher =
        SINGLE_RANGE.matcher(header.trim());

    if (!matcher.matches()) {
        throw new IllegalArgumentException(
            "Range syntax không hỗ trợ"
        );
    }

    String left = matcher.group(1);
    String right = matcher.group(2);

    if (left.isEmpty() && right.isEmpty()) {
        throw new IllegalArgumentException(
            "Range không có offset"
        );
    }

    if (total == 0) {
        throw new IllegalArgumentException(
            "Tệp rỗng không có byte range hợp lệ"
        );
    }

    if (left.isEmpty()) {
        long suffix = Long.parseLong(right);

        if (suffix <= 0) {
            throw new IllegalArgumentException(
                "Suffix length phải dương"
            );
        }

        long count = Math.min(suffix, total);

        return new ByteRange(
            total - count,
            total - 1,
            total
        );
    }

    long start = Long.parseLong(left);

    if (start >= total) {
        throw new IllegalArgumentException(
            "Start vượt cuối tệp"
        );
    }

    long end;

    if (right.isEmpty()) {
        end = total - 1;
    } else {
        long requestedEnd =
            Long.parseLong(right);

        if (requestedEnd < start) {
            throw new IllegalArgumentException(
                "End nhỏ hơn start"
            );
        }

        end = Math.min(
            requestedEnd,
            total - 1
        );
    }

    return new ByteRange(start, end, total);
}
~~~

### 7.1. Phân loại lỗi parser

- `IllegalArgumentException` có thể do range không hợp lệ hoặc không hỗ trợ.
- `NumberFormatException` phát sinh khi số quá lớn để lưu trong `long`.
- Không gom mọi lỗi thành HTTP 416 một cách mù quáng: header sai cú pháp có thể bị bỏ qua/400 theo chính sách, còn **valid but unsatisfiable** mới là trường hợp 416 điển hình.
- Code parser chỉ xử lý **single range**, không hỗ trợ multi-range.
- `Range` header có thể rất dài/được cố ý tạo để DoS; giới hạn độ dài trước khi parse.
- Khi client gửi `If-Range`, server phải kiểm tra validator; không tự trả `206` từ bản khác nếu ETag/Last-Modified không khớp.

### 7.2. Tách parser khỏi HTTP framework

Một test có thể gọi `parseSingleRange("bytes=-500", 600000)` mà không cần MongoDB hay web server. Đây là cách kiểm tra off-by-one và overflow dễ hơn so với test toàn bộ controller.

---

## 8. Spring MVC: skeleton trả HTTP Partial Content

Ví dụ sau minh họa cách ghép **GridFS stream + HTTP Range** với Spring MVC. Đây là skeleton cho **single range**; trong production cần hoàn thiện If-Range, multi-range policy, authorization và MIME type. Để tập trung đúng logic, helper `parseSingleRange` và `streamRange` dùng các hàm ở phần trên.

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation
    .StreamingResponseBody;

import static com.mongodb.client.model.Filters.eq;

@RestController
@RequestMapping("/api/files")
public class FileDownloadController {

    private final GridFSBucket bucket;

    public FileDownloadController(
            GridFSBucket bucket) {
        this.bucket = bucket;
    }

    @GetMapping("/{fileId}")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String fileId,
            @RequestHeader(
                value = "Range",
                required = false
            ) String rangeHeader) {

        // 1. Validate ObjectId format.
        if (!ObjectId.isValid(fileId)) {
            return ResponseEntity
                .badRequest()
                .build();
        }

        ObjectId id = new ObjectId(fileId);

        // 2. Trong production: kiểm tra auth + tenant,
        // visibility/quyền của logical asset trước đọc.
        // Không chỉ dựa vào ObjectId khó đoán.
        GridFSFile file = bucket
            .find(eq("_id", id))
            .first();

        if (file == null) {
            return ResponseEntity
                .notFound()
                .build();
        }

        long total = file.getLength();

        HttpHeaders headers = new HttpHeaders();

        headers.set(
            HttpHeaders.ACCEPT_RANGES,
            "bytes"
        );

        headers.setContentType(
            MediaType.APPLICATION_OCTET_STREAM
        );

        // ETag bằng ID chỉ phù hợp khi nội dung được
        // xem là immutable cho chính ID đó.
        headers.setETag(
            "\"" + id.toHexString() + "\""
        );

        if (rangeHeader == null
                || rangeHeader.isBlank()
                || rangeHeader.contains(",")) {

            // Không hỗ trợ multi-range: trả toàn bộ 200.
            headers.setContentLength(total);

            StreamingResponseBody body = output ->
                bucket.downloadToStream(id, output);

            return new ResponseEntity<>(
                body, headers, HttpStatus.OK
            );
        }

        final ByteRange range;

        try {
            range = parseSingleRange(
                rangeHeader,
                total
            );
        } catch (IllegalArgumentException error) {
            headers.set(
                HttpHeaders.CONTENT_RANGE,
                "bytes */" + total
            );

            // Sản phẩm cần phân biệt syntax lỗi / range
            // unsatisfiable để chọn status chính xác.
            return new ResponseEntity<>(
                null,
                headers,
                HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE
            );
        }

        headers.set(
            HttpHeaders.CONTENT_RANGE,
            range.contentRange()
        );

        headers.setContentLength(
            range.contentLength()
        );

        StreamingResponseBody body = output ->
            streamRange(
                bucket,
                id,
                range.start(),
                range.endInclusive(),
                output
            );

        return new ResponseEntity<>(
            body,
            headers,
            HttpStatus.PARTIAL_CONTENT
        );
    }
}
~~~

### 8.1. Những phần phải hoàn thiện trước production

1. Kiểm tra permission/tenant theo logical asset; `fileId` không phải token quyền.
2. Xác thực `If-Range` và `If-None-Match`/conditional requests.
3. Định nghĩa policy với malformed ranges/multiple ranges/HEAD.
4. Giới hạn body streaming resource và concurrent requests.
5. MIME metadata được tin cậy/đã kiểm chứng; không tin hoàn toàn giá trị client upload.
6. `Content-Disposition` an toàn, chuẩn hóa filename, tránh CRLF/path injection.
7. Timeout, cancellation và metrics khi client đóng kết nối.
8. ETag dựa trên immutable version hoặc content hash.
9. Đảm bảo source file không bị xóa trong lúc stream, hoặc có retention/lease.
10. Logging audit không lộ sensitive filename hoặc PII.

### 8.2. Vì sao phải xác minh quyền **trước** khi streaming?

HTTP server có thể bắt đầu gửi bytes sớm. Sau khi bắt đầu response, phát hiện user không có quyền thì đã quá muộn: dữ liệu có thể đã bị lộ một phần.

### 8.3. Nếu client bỏ tải giữa chừng

Streaming API sẽ bị lỗi ghi output hoặc ngừng khi client đóng socket. Đừng cố tiếp tục tải tệp từ MongoDB sau khi client ngắt; đóng input stream, ghi metrics và giải phóng tài nguyên.

---

## 9. `Content-Range`, `ETag` và cache với nhiều phiên bản

### 9.1. Tại sao ETag quan trọng?

Một video có thể có bản v1, v2. Nếu client tải 5 MiB đầu từ v1 rồi tải tiếp 5 MiB sau từ v2 **qua cùng URL filename**, nội dung ghép có thể hỏng.

Dùng validator:

~~~http
ETag: "v1-file-id-or-sha256"
~~~

Khi tiếp tục tải, client có thể gửi:

~~~http
Range: bytes=5242880-
If-Range: "v1-file-id-or-sha256"
~~~

Nếu bản hiện tại vẫn là v1, server có thể trả partial v1. Nếu validator không khớp, server nên bỏ Range và trả toàn bộ bản hiện tại với `200` theo HTTP semantics.

### 9.2. Pin version vào URL

Một phương án an toàn:

~~~text
GET /assets/ASSET-101           -> redirect/lookup currentFileId
GET /files/<fileId-of-v1>       -> bytes của v1
GET /files/<fileId-of-v2>       -> bytes của v2
~~~

`/files/{fileId}` trở thành đường dẫn tới **một nội dung bất biến**. CDN/browser có thể cache với validator ổn định, trong khi `/assets/{assetId}` luôn trỏ về bản hiện tại theo chính sách.

### 9.3. Filename không phải ETag

`"training.mp4"` có thể trỏ tới nhiều phiên bản, vì thế dùng filename làm ETag là sai. ETag nên dựa trên fileId bất biến/sha256/version ID; không dựa trên tên hiển thị dễ đổi.

### 9.4. Header trả về nên phản ánh file cụ thể

Một response tốt có:

- `Content-Type` đã xác thực/được phép.
- `Content-Length` chính xác theo range hoặc file.
- `Content-Range` khi status 206.
- `Accept-Ranges: bytes` khi có hỗ trợ.
- `ETag` của nội dung cụ thể.
- `Last-Modified` nếu có metadata time đáng tin và semantics phù hợp.
- `Content-Disposition` tên tải xuống đã làm sạch.

### 9.5. Không cache bản private công khai

Nếu nội dung thuộc tenant hoặc user riêng, `Cache-Control` và CDN key phải bảo đảm không chia sẻ bytes giữa những người không có quyền. ETag ổn định không đồng nghĩa nội dung được phép public cache.

---

## 10. Quản lý tên tệp: `filename` không duy nhất

### 10.1. Hai tệp cùng tên là hợp lệ

Ví dụ:

~~~javascript
{
  _id: ObjectId("6914a9aa0000000000000001"),
  filename: "contract.pdf",
  uploadDate: ISODate("2026-11-10T09:00:00Z")
}

{
  _id: ObjectId("6914a9aa0000000000000002"),
  filename: "contract.pdf",
  uploadDate: ISODate("2026-11-11T09:00:00Z")
}
~~~

GridFS cho phép hai documents cùng `filename`. Chúng là **hai file IDs**, có thể được driver coi là các **revisions** của cùng tên.

### 10.2. Định danh đúng

| Khái niệm | Dùng để làm gì | Có unique mặc định? |
|---|---|---|
| `fileId` / `fs.files._id` | Nhận diện một bản nội dung | Có |
| `filename` | Hiển thị, tìm kiếm, download by name | **Không** |
| `uploadDate` | Thời điểm upload, hỗ trợ revision order | Không |
| `assetId` | ID logic một tài liệu trong ứng dụng | Do ứng dụng quy định |
| `logicalVersion` | Version nghiệp vụ 1,2,3... | Do ứng dụng cấp |
| `sha256` | Dấu kiểm tra nội dung/đối soát | Không mặc định do GridFS tính |

### 10.3. Tìm các files theo tên bằng mongosh

~~~javascript
use media_lab

db.media.files.find(
  { filename: "contract.pdf" },
  {
    _id: 1,
    filename: 1,
    length: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({
  uploadDate: -1,
  _id: -1
});
~~~

Đây là cách **liệt kê metadata**. Để tải bytes, dùng GridFS driver/API.

### 10.4. Không dựa vào tên để xác nhận quyền

Nếu tenant-a và tenant-b đều upload `report.pdf`, câu truy vấn chỉ theo filename có thể tìm cả hai. Ứng dụng phải dùng trusted `tenantId`/asset ownership, không dùng filename làm security boundary.

### 10.5. Đừng biến filename thành đường dẫn filesystem

Tên như `../../private.txt` hoặc chứa slash/backslash có thể gây path traversal nếu server ghép thẳng vào đường dẫn local.

Nếu cần lưu file trên disk:

- Dùng tên nội bộ/temporary path được tạo an toàn.
- Chỉ dùng filename đã sanitize cho Content-Disposition.
- Tránh dùng tên upload làm đường dẫn thực.
- Không lấy tên file từ HTTP header mà không validate encoding, control chars và độ dài.

---

## 11. GridFS revisions: số dương và số âm

### 11.1. Quy tắc chọn revision

GridFS spec quy định revisions theo các files có **cùng filename**, sắp theo `uploadDate`.

| Revision | Ý nghĩa |
|---:|---|
| `0` | Bản upload đầu tiên/cũ nhất |
| `1` | Bản tiếp theo theo upload time |
| `2` | Bản thứ ba |
| `-1` | Bản mới nhất |
| `-2` | Bản mới thứ hai |
| `-3` | Bản mới thứ ba |

Mặc định download by filename chọn **revision `-1`**.

### 11.2. Ví dụ ba bản

~~~text
filename = report.pdf

2026-11-01  fileId=A   revision 0  / -3
2026-11-05  fileId=B   revision 1  / -2
2026-11-12  fileId=C   revision 2  / -1

Tải theo filename mặc định -> C
Tải theo revision(0)         -> A
Tải theo revision(1)         -> B
Tải theo revision(-2)        -> B
~~~

### 11.3. Revision không phải field lưu trong `fs.files`

`revision` là **vị trí tương đối** khi nhìn danh sách cùng filename. Nó không phải số version cố định được GridFS lưu như `metadata.logicalVersion`.

Khi xóa bản A, các revision số dương của B/C có thể thay đổi vì danh sách đã thay đổi. Khi upload D, `-1` chuyển sang D. Vì thế một URL:

~~~text
/download?filename=report.pdf&revision=-1
~~~

không tham chiếu bất biến qua thời gian.

### 11.4. Nếu hai uploads có cùng uploadDate?

`uploadDate` có độ phân giải thời gian hữu hạn. Nếu hai bản ghi trùng uploadDate, không nên dựa vào revision ordering như một **business sequence tuyệt đối** nếu ứng dụng cần tie-break nghiêm ngặt.

Có thể gán `logicalVersion` do app cấp bằng transaction/CAS trong metadata riêng. Khi cần chính xác, dùng `fileId` của bản đã được chọn.

### 11.5. Đổi tên có ảnh hưởng nhóm revisions

Nếu đổi filename của một file từ `report.pdf` thành `summary.pdf`, bản đó chuyển sang nhóm tên mới. Việc tính revision theo tên cũ/mới thay đổi.

Đừng dùng `revision(-1)` như business identity bất biến cho một hợp đồng đã ký.

---

## 12. Java Sync Driver: download theo filename và revision

### 12.1. Mặc định mới nhất

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf")) {

    // Đây là bản mới nhất theo revision semantics
    // của download-by-name ở GridFS.
    input.transferTo(outputStream);
}
~~~

Ví dụ dùng `InputStream.transferTo` (Java 9+). Không đóng `outputStream` nếu nó thuộc HTTP framework; framework quản lý lifecycle output.

### 12.2. Chọn bản cũ nhất

~~~java
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(0);

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf", options)) {

    input.transferTo(outputStream);
}
~~~

### 12.3. Chọn bản mới thứ hai

~~~java
GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(-2);

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf", options)) {

    input.transferTo(outputStream);
}
~~~

### 12.4. Tải cả file ra một OutputStream

~~~java
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(-1);

bucket.downloadToStream(
    "report.pdf",
    outputStream,
    options
);
~~~

`downloadToStream` thuận tiện cho full download; stream được gọi với **filename + revision**. Khi cần range, dùng `openDownloadStream` rồi `skipFully/copyExactly`.

### 12.5. Không lạm dụng download-by-name trong API public

Nếu user chọn tài liệu theo asset ID, phương án an toàn thường:

1. Resolve asset ID theo quyền.
2. Lấy `currentFileId` hoặc `versionFileId`.
3. Download chính xác file ID đó.

Download by filename rất tiện cho lab/CLI, nhưng với production multi-tenant/versioned assets, filename dễ trùng và không ổn định.

---

## 13. Java: liệt kê revisions rồi tải theo ID

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import java.util.ArrayList;
import java.util.List;

List<GridFSFile> revisions = new ArrayList<>();

bucket.find(
        Filters.eq("filename", "report.pdf")
    )
    .sort(
        Sorts.orderBy(
            Sorts.ascending("uploadDate"),
            Sorts.ascending("_id")
        )
    )
    .into(revisions);

for (GridFSFile file : revisions) {
    System.out.println(
        file.getId() + " "
        + file.getFilename() + " "
        + file.getUploadDate()
    );
}
~~~

### 13.1. Vì sao liệt kê metadata trước?

Ứng dụng có thể cho user thấy:

- Thời gian upload.
- Người upload.
- File length.
- Version nghiệp vụ.
- Checksum.
- Trạng thái virus scan.
- Quyền truy cập.
- Ghi chú phiên bản.

### 13.2. Sắp theo `_id` ở ví dụ để tie-break

Sorting theo `uploadDate` là cơ chế revision của GridFS, nhưng nếu ứng dụng muốn deterministic UI ordering khi thời gian bằng nhau, có thể thêm `_id` **nếu các file IDs có cùng kiểu sắp xếp hợp lệ**. Cách này là quy ước UI của ứng dụng, không có nghĩa GridFS driver luôn dùng cùng tie-break khi resolve `revision(-1)`.

### 13.3. Chọn ID đã xác định

~~~java
GridFSFile chosen = revisions.get(0);

try (GridFSDownloadStream input =
         bucket.openDownloadStream(
             chosen.getId()
         )) {

    input.transferTo(outputStream);
}
~~~

Đây là cách pin vào một version cụ thể. Nếu file bị xóa giữa lúc liệt kê và lúc download, download có thể lỗi; ứng dụng phải xử lý race.

### 13.4. Chọn business version, không chọn list position

Trong ứng dụng dùng `metadata.logicalVersion` hoặc collection `assetVersions`, khi user chọn “phiên bản 7”, tra mapping version 7 → `fileId`, rồi đọc theo ID. Không suy rằng revision index 6 luôn là version 7.

---

## 14. Đổi tên tệp: `rename(fileId, newFilename)`

### 14.1. Rename không đổi bytes

~~~java
import org.bson.types.ObjectId;

ObjectId fileId =
    new ObjectId("6914a9aa0000000000000001");

bucket.rename(
    fileId,
    "training-final.mp4"
);
~~~

GridFS rename cập nhật `filename` của file metadata được chọn bằng ID; chunks và nội dung không thay đổi.

### 14.2. Không dùng rename để “ghi đè” nội dung

Rename không thay `fs.chunks.data`. Nếu người dùng upload tệp mới với tên cũ, đó là **một fileId mới**. Rename bản cũ thành tên mới không biến bản cũ thành bản có bytes mới.

### 14.3. Rename một file trong nhiều bản cùng tên

Giả sử ba files đều tên `report.pdf`. `bucket.rename(fileIdB, "report-old.pdf")` chỉ đổi tên bản B, không động đến A/C.

### 14.4. Rename all by name

GridFS spec có optional advanced operations quản lý nhiều tệp cùng tên. Không mặc định Java Sync Driver version đang dùng cung cấp `renameByName`; khi cần đổi tất cả:

1. Liệt kê các file IDs theo `filename`.
2. Xác minh quyền và tập revisions.
3. Gọi `rename(fileId, newName)` cho từng ID.
4. Chấp nhận/giải quyết partial success vì operations có thể không atomic trên toàn bộ files.

### 14.5. Naming policy

Có thể quy định:

- Filename chỉ dùng để hiển thị.
- Tên hiển thị không chứa control characters.
- Có giới hạn độ dài.
- Không yêu cầu unique trên toàn bucket.
- Có displayName độc lập với `filename` nếu cần.
- Logic path/folder lưu trong metadata app riêng (ví dụ `folderId`), không encode toàn bộ hierarchy vào filename.

---

## 15. Xóa tệp: theo fileId và rủi ro concurrent reads

### 15.1. Xóa đúng một bản

~~~java
ObjectId oldFileId =
    new ObjectId("6914a9aa0000000000000001");

bucket.delete(oldFileId);
~~~

GridFS delete xóa metadata file và các chunks liên quan. Nó nhắm theo **file ID**, không tự xóa mọi bản có cùng filename.

### 15.2. Không xóa theo tên tùy tiện

Nếu user chọn “xóa bản v2 của contract.pdf”, hệ thống nên resolve `versionId→fileId` rồi xóa đúng ID. Một lệnh thủ công:

~~~javascript
db.fs.chunks.deleteMany({
  files_id: someFileId
});
~~~

khi metadata vẫn còn sẽ làm tệp bị hỏng. Không xóa chunks/files riêng lẻ trừ khi bạn đang làm một quy trình quản trị/recovery có kiểm soát và hiểu GridFS invariant.

### 15.3. Race giữa delete và download

~~~text
Reader A: lấy metadata fileId=X
           |
Writer B: delete(X)
           |
Reader A: đọc chunks của X
           |
           v
Reader A có thể gặp chunk thiếu
~~~

GridFS spec nêu rõ có race inherent giữa metadata/chunks khi file bị xóa đồng thời với read. Driver không thể biến việc delete hai collections thành một atomic operation đơn giản cho mọi trường hợp.

### 15.4. Chính sách hạn chế xóa sớm

Nếu file đang được trả cho client:

- Dùng soft-delete logical asset trước.
- Chặn phát sinh download mới.
- Chờ thời gian đủ cho active downloads hoặc active-reader leases.
- Sau retention/grace period mới gọi `bucket.delete(fileId)`.
- Theo dõi lỗi tải và orphan cleanup.

Đây là **quy tắc ứng dụng**, không phải tính năng lock có sẵn của GridFS.

### 15.5. Xóa all revisions

Nếu cần xóa toàn bộ lịch sử cùng filename:

1. Tìm các `_id` theo tenant/asset, không chỉ filename.
2. Kiểm tra legal hold/retention và quyền xóa.
3. Xóa từng file ID qua GridFS API.
4. Ghi audit cho mỗi kết quả.
5. Có cách retry nếu dừng giữa chừng.

Một số drivers cung cấp advanced delete-by-name, nhưng không thể mặc định API đó có trên mọi phiên bản hoặc đáp ứng chính sách tenant/version app.

### 15.6. Không nhầm drop bucket với xóa một file

`bucket.drop()` hoặc drop cả `fs.files`/`fs.chunks` **xóa toàn bộ bucket**, không phải thao tác quản lý một phiên bản. Không dùng trong production workflow bình thường.

---

## 16. GridFS không hỗ trợ multi-document transactions cho các thao tác tệp

MongoDB Manual ghi rõ **GridFS không hỗ trợ multi-document transactions**. GridFS upload/delete thường thao tác nhiều documents/chunks/files; không được thiết kế như một atomic write của tất cả chunks trong MongoDB transaction.

### 16.1. Một lần upload có nhiều bước

~~~text
Bắt đầu upload
     |
     v
Insert chunk n=0
     |
     v
Insert chunk n=1
     |
     v
Insert chunk n=2
     |
     v
Insert metadata vào fs.files
     |
     v
Upload hoàn tất
~~~

Nếu process/network chết giữa upload, có thể tồn tại **orphan chunks** hoặc trạng thái dang dở.

### 16.2. Không bọc upload + app metadata trong transaction rồi kỳ vọng atomic

Sai về mặt thiết kế:

~~~text
startTransaction()
  GridFS upload toàn bộ tệp 2 GB
  insert appAsset
commit()
~~~

GridFS không hỗ trợ kiểu transaction này; transaction dài cũng không phù hợp với file streaming lớn.

### 16.3. Cách phối hợp đúng: upload trước, publish con trỏ sau

~~~text
1. Upload GridFS file mới (fileId=Y).
2. Chờ upload hoàn tất.
3. Tính/đối chiếu checksum và scan content nếu cần.
4. Transaction/atomic update app metadata:
     asset.currentFileId = Y
     asset.currentVersion += 1
     assetVersions insert (assetId,version,Y)
5. Nếu bước 4 thất bại:
     Y chưa active, có thể cleanup theo chính sách.
~~~

App metadata transaction **không bao gồm GridFS upload**. Nó chỉ quản lý **khi nào bản đã upload được công bố là current**.

### 16.4. Upload chưa hoàn tất không được cho đọc

Đừng đưa fileId mới vào public asset pointer trước khi upload success và validation passes. Đặt trạng thái `UPLOADING`/`SCANNING`/`READY` trong application metadata.

---

## 17. Thiết kế logical asset và immutable versions

### 17.1. Vấn đề filename/revision

Nếu một tài liệu có tên `contract.pdf` và user upload lại 4 lần, GridFS có thể chọn bản mới nhất theo `uploadDate`. Nhưng ứng dụng cần:

- Một URL ổn định cho tài liệu logic.
- ID bất biến cho từng bản.
- Lịch sử gồm author/comment/time/hash.
- Quyền tenant.
- “Restore v2” mà không mất v3/v4.
- Audit khi rename/delete.
- Tránh lost update khi hai người upload cùng lúc.

Đừng giao mọi thứ cho `filename + revision(-1)`.

### 17.2. Collection `assets`

~~~javascript
{
  _id: "ASSET-101",
  tenantId: "tenant-a",
  displayName: "contract.pdf",
  currentVersion: 3,
  currentFileId: ObjectId(
    "6914a9aa0000000000000003"
  ),
  generation: NumberLong("3"),
  status: "ACTIVE",
  updatedAt: ISODate("2026-11-14T05:00:00Z")
}
~~~

### 17.3. Collection `assetVersions`

~~~javascript
{
  _id: "ASSET-101:v3",
  assetId: "ASSET-101",
  tenantId: "tenant-a",
  version: 3,
  fileId: ObjectId(
    "6914a9aa0000000000000003"
  ),
  originalFilename: "contract.pdf",
  contentType: "application/pdf",
  length: NumberLong("600000"),
  sha256: "hash-do-ung-dung-tinh",
  uploadedBy: "user-101",
  createdAt: ISODate("2026-11-14T05:00:00Z"),
  status: "READY"
}
~~~

### 17.4. Index cho business versions

~~~javascript
db.assetVersions.createIndex(
  {
    tenantId: 1,
    assetId: 1,
    version: 1
  },
  {
    unique: true,
    name: "uk_asset_version"
  }
);

db.assetVersions.createIndex(
  {
    fileId: 1
  },
  {
    unique: true,
    name: "uk_asset_file_id"
  }
);
~~~

Nếu nhiều assets cố ý tham chiếu cùng fileId để deduplicate physical storage, unique `fileId` không còn phù hợp. Thiết kế index theo policy sở hữu/dedup thực tế.

### 17.5. Tách hai loại định danh

| URL/API | Resolve | Ổn định nội dung? |
|---|---|---|
| `/assets/ASSET-101` | currentFileId | **Không**; nội dung current có thể thay |
| `/assets/ASSET-101/versions/3` | fileId của v3 | Có nếu không xóa/thay bytes |
| `/files/6914...` | exact GridFS fileId | Có nếu file immutable |
| `/download?filename=contract.pdf` | driver chọn theo tên/revision | Không đảm bảo ổn định |

### 17.6. “Restore v2” có thể làm gì?

Có hai lựa chọn:

- Chuyển pointer current về fileId của v2 (đi kèm revision/generation mới trong audit).
- Tạo bản business version mới v5 có content giống v2 rồi đặt current v5.

Cách hai thường dễ audit hơn nếu mỗi lần publish/restore phải tạo một state transition mới. Không tự đánh tụt `currentVersion` từ 4 về 2 nếu hệ thống dùng version monotonic để ngăn concurrency lỗi.

---

## 18. Hai upload đồng thời và optimistic concurrency

### 18.1. Race

~~~text
Asset generation = 3

User A đọc gen=3
User B đọc gen=3

User A upload fileId=A4
User B upload fileId=B4

A muốn set currentFileId=A4
B muốn set currentFileId=B4
~~~

Nếu update vô điều kiện, kết quả cuối phụ thuộc thứ tự ghi; có thể mất một version trong lịch sử hoặc ghi version 4 hai lần.

### 18.2. Conditional update / compare-and-swap

Sau khi GridFS upload file xong, app metadata có thể thử:

~~~javascript
const expectedGeneration = NumberLong("3");

const result = db.assets.updateOne(
  {
    _id: "ASSET-101",
    tenantId: "tenant-a",
    generation: expectedGeneration
  },
  {
    $set: {
      currentFileId: newFileId,
      updatedAt: new Date()
    },
    $inc: {
      generation: NumberLong("1"),
      currentVersion: 1
    }
  }
);

if (result.modifiedCount !== 1) {
  throw new Error("VERSION_CONFLICT");
}
~~~

Đây là core CAS demo. **Nếu app còn phải insert `assetVersions` cùng logic change**, nên thực hiện các writes trên **application metadata collections** trong transaction được MongoDB hỗ trợ hoặc dùng một design có atomic invariant tương đương.

Không bọc GridFS upload vào transaction.

### 18.3. Khi CAS thất bại

File `newFileId` đã upload xong nhưng chưa được publish; có thể cần:

- Retain as unreferenced draft trong thời hạn ngắn.
- Retry publication sau khi user refresh/merge, không tự ghi đè.
- Cleanup theo policy.
- Audit về upload xảy ra và conflict.

### 18.4. Không tái sử dụng một `fileId` để ghi đè bytes

GridFS xem tệp là nội dung đã lưu; **không hỗ trợ chỉnh sửa/append tùy ý các chunks của một tệp đã hoàn tất như một file mutable**. Muốn bản mới, upload mới với ID mới và chuyển pointer. Không sửa `fs.chunks.data` trực tiếp.

### 18.5. Checkpoint của ứng dụng

Khi cập nhật current pointer, cần kiểm tra current generation và quyền. Nếu upload về sau không active do conflict, không nên xóa bản đang được người dùng khác sử dụng.

---

## 19. Tìm kiếm và quản lý filename ở quy mô lớn

### 19.1. Index chuẩn của GridFS

Theo GridFS:

~~~javascript
db.fs.files.createIndex(
  {
    filename: 1,
    uploadDate: 1
  }
);

db.fs.chunks.createIndex(
  {
    files_id: 1,
    n: 1
  },
  {
    unique: true
  }
);
~~~

Driver tuân theo GridFS spec thường đảm bảo indexes này theo hành vi riêng của phiên bản/driver. Nếu bucket dùng prefix `media`, tên collections tương ứng là `media.files` và `media.chunks`.

### 19.2. Vì sao index files cần `filename, uploadDate`?

Một lookup by filename/revision thường:

~~~javascript
db.fs.files.find({
  filename: "report.pdf"
}).sort({
  uploadDate: 1
});
~~~

Index hỗ trợ tìm các files cùng tên và sắp theo uploadDate.

### 19.3. Vì sao chunks index phải unique?

Một tệp không được có hai chunk cùng `n`. Index:

~~~javascript
{
  files_id: 1,
  n: 1
}
~~~

với `unique:true` bảo vệ invariant và cho phép driver lấy các chunks liên tiếp hiệu quả.

### 19.4. Index bổ sung cho tenant/asset metadata

Nếu thường tìm:

~~~javascript
db.media.files.find({
  "metadata.tenantId": "tenant-a",
  "metadata.assetId": "ASSET-101"
}).sort({
  uploadDate: -1
});
~~~

có thể xem xét:

~~~javascript
db.media.files.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.assetId": 1,
    uploadDate: -1
  },
  {
    name: "idx_media_tenant_asset_date"
  }
);
~~~

Đây là index ứng viên; dùng `explain` và workload thực tế để quyết định. Không tạo quá nhiều indexes khi upload volume lớn.

### 19.5. Tìm kiếm tên bằng regex

Nếu UI tìm `report` trong mọi filenames:

~~~javascript
db.media.files.find({
  filename: /report/i
});
~~~

regex không có anchor và case-insensitive có thể khó tối ưu trên index B-tree thông thường. Với quy mô lớn, cân nhắc search metadata collection chuyên dụng, normalized filename, prefix search hoặc MongoDB Search tùy yêu cầu.

### 19.6. Không coi tên tệp là đường dẫn duy nhất

Nếu nhiều folder hoặc tenant có cùng `invoice.pdf`, logical identity nên là `assetId` và folder/tenant metadata. Unique `filename` global sẽ sai với đa số hệ thống quản lý tài liệu đa người dùng.

---

## 20. Quản lý metadata: MIME type, checksum, uploader

### 20.1. Dùng `metadata` để mở rộng

~~~java
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;

GridFSUploadOptions options =
    new GridFSUploadOptions()
        .chunkSizeBytes(256 * 1024)
        .metadata(
            new Document(
                "tenantId", "tenant-a"
            )
                .append(
                    "assetId", "ASSET-101"
                )
                .append(
                    "contentType",
                    "application/pdf"
                )
                .append(
                    "uploadedBy",
                    "user-101"
                )
        );
~~~

Ví dụ chọn `256 KiB` theo cấu hình upload, khác default **255 KiB**. `chunkSizeBytes` chỉ áp dụng cho file mới, không re-chunk những file cũ.

### 20.2. Không tin MIME từ client

Client có thể gửi `application/pdf` nhưng payload là một file thực thi. Nếu cho phép xem trực tiếp trong browser, phải xác thực loại nội dung, scan malware và chọn `Content-Disposition`/`Content-Security-Policy` phù hợp.

### 20.3. Checksum

Trường legacy `md5` trong GridFS không nên được coi là cơ chế integrity/security hiện đại. Nếu cần:

1. Hash bytes khi upload, ví dụ SHA-256.
2. Lưu checksum trong application metadata.
3. Kiểm tra lại khi cần audit/download/backup restore.
4. Không thay checksum sau khi nội dung đã publish.

### 20.4. SHA-256 của full file không được chứng minh từ một range

Nếu client chỉ đọc bytes 1000–1999, không thể xác nhận full-file SHA-256 chỉ từ đoạn đó trừ khi có cấu trúc proof/merkle phù hợp. Có thể kiểm tra checksum từng chunk riêng hoặc xác minh full file khi ingest/đối soát.

### 20.5. Metadata do user đặt cần validation

- Content type whitelist.
- Filename length/Unicode normalization.
- Tenant/owner từ authenticated context.
- Business version cấp server-side.
- Không nhận arbitrary update cho core fields `length`, `chunkSize`, `uploadDate`, `_id`.

---

## 21. Upload streaming và lưu phiên bản mới bằng Java

### 21.1. Tải một file vào GridFS

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;

static ObjectId uploadDocument(
        GridFSBucket bucket,
        String safeFilename,
        InputStream input,
        String assetId,
        String tenantId) {

    GridFSUploadOptions options =
        new GridFSUploadOptions()
            .metadata(
                new Document(
                    "tenantId", tenantId
                )
                    .append(
                        "assetId", assetId
                    )
                    .append(
                        "contentType",
                        "application/pdf"
                    )
            );

    return bucket.uploadFromStream(
        safeFilename,
        input,
        options
    );
}
~~~

`uploadFromStream` đọc nguồn theo streaming và trả ObjectId của file mới. Source `InputStream` do caller quản lý: code gọi nên đóng nguồn bằng try-with-resources.

### 21.2. Mỗi upload có ID riêng

~~~java
ObjectId v1 = uploadDocument(
    bucket, "contract.pdf",
    inputV1, "ASSET-101", "tenant-a"
);

ObjectId v2 = uploadDocument(
    bucket, "contract.pdf",
    inputV2, "ASSET-101", "tenant-a"
);
~~~

`v1` và `v2` có thể cùng filename nhưng là hai files với bytes riêng.

### 21.3. Khi thay nội dung

Không sửa chunks của v1; upload v2 rồi cập nhật logical asset pointer sau khi:

- Upload success.
- Malware/content validation nếu cần.
- SHA-256/length xác nhận.
- Business permissions hợp lệ.
- Expected generation không conflict.

### 21.4. Không tự đánh đồng upload success với publish success

Nếu upload GridFS thành công nhưng transaction app metadata update thất bại, nội dung đã tồn tại nhưng chưa active. Cần cleanup hoặc retry publication theo runbook.

---

## 22. Tải theo ID và theo filename: nên chọn gì?

### 22.1. Bảng so sánh

| Nhu cầu | Tải theo ID | Tải theo filename |
|---|---|---|
| Trả về đúng bản đã ký | **Tốt** | Rủi ro chọn bản khác |
| Tải tiếp HTTP Range | **Tốt** vì URL ổn định | Cần If-Range/ETag để chống trộn phiên bản |
| Khôi phục revision cũ | Resolve ID từ metadata version | Có thể dùng revision nhưng không cố định |
| Lab đơn giản | Phù hợp | Thuận tiện |
| Multi-tenant | Kết hợp asset authorization | Filename dễ trùng |
| Audit download | ID rõ ràng | Dễ mơ hồ |
| Cache/CDN | Có thể tạo immutable URL | Filename URL biến đổi nội dung |
| Rename | ID không đổi | Lookup tên cũ có thể hết hiệu lực |

### 22.2. Rule đề xuất

- **Business API:** dùng `assetId` và `versionId`.
- **Physical bytes API:** dùng `fileId`.
- **GridFS filename:** dùng cho hiển thị, công cụ quản trị và download-by-name khi phù hợp.

---

## 23. Đọc range song song và giới hạn tài nguyên

### 23.1. Video player có thể mở nhiều requests

Một trình phát có thể gọi:

~~~http
Range: bytes=0-1023
Range: bytes=1048576-2097151
Range: bytes=5242880-
~~~

Các requests có thể đồng thời. Không chia sẻ một `GridFSDownloadStream` giữa nhiều HTTP requests; mỗi request nên mở stream riêng theo fileId đã xác thực.

### 23.2. Giới hạn concurrent streams

Nếu 1.000 clients tải file lớn, mỗi stream có thể giữ cursor/buffer/network resources. Cần:

- Connection pooling/driver settings.
- Giới hạn concurrency của server.
- Timeouts/read deadlines.
- Rate limits theo user/tenant.
- Kích thước read buffer hợp lý.
- CDN hoặc reverse proxy khi phù hợp.
- Monitoring bytes streamed và client abort.

### 23.3. Nếu range rất nhỏ nhưng request rất nhiều

Một client ác ý có thể yêu cầu hàng chục nghìn ranges nhỏ để tăng overhead. Rate limit, normalize requests, reject quá nhiều connections và cache các tệp phổ biến theo chính sách.

### 23.4. Chunk size trade-off

| Chunk nhỏ hơn | Chunk lớn hơn |
|---|---|
| Đọc một đoạn nhỏ ít dư hơn khi driver truy xuất chunk-level | Ít documents hơn cho file lớn |
| Nhiều chunk documents/index entries | Ít metadata overhead |
| Tốn nhiều round trips hơn nếu đọc toàn file | Có thể tăng peak memory/buffer per chunk |
| Phù hợp một số workloads random reads | Phù hợp một số workloads sequential reads |

Không có chunkSize tốt nhất cho mọi file. Benchmark với real file sizes và range patterns. Lưu `chunkSize` theo từng tệp nên không cần migration tất cả files cũ khi thay cấu hình cho upload mới.

---

## 24. GridFS và streaming HTTP không giống object storage CDN

### 24.1. Khi GridFS hợp lý

- Ứng dụng đã dùng MongoDB và muốn quản lý files cùng hạ tầng.
- Cần query metadata bằng MongoDB.
- Cần lưu nhiều revisions và stream từng đoạn.
- File lớn hơn BSON document limit.
- Số lượng download/traffic phù hợp khả năng cluster.

### 24.2. Khi cần cân nhắc object storage

- Video/file download rất lớn ở quy mô public toàn cầu.
- Cần direct CDN integration, object lifecycle/storage class.
- Data egress quá cao gây áp lực MongoDB.
- Cần multipart upload/resume upload có semantics riêng.
- Không cần join/search metadata trong database.

Một kiến trúc khác:

~~~text
Application metadata: MongoDB
Binary objects: S3/GCS/Azure Blob
Signed URLs/CDN: trực tiếp object store
~~~

Không khẳng định GridFS luôn nhanh/hay rẻ hơn object storage. Quyết định theo workload, availability, backup và chi phí.

### 24.3. GridFS không tự tạo thumbnails/transcoding

Đối với video streaming, GridFS chỉ lưu bytes và cho phép đọc từng đoạn. Nó không tự:

- Tạo HLS/DASH renditions.
- Transcode video.
- Sinh thumbnails.
- Tính codec/bitrate.
- Bảo đảm browser phát được nội dung ở mọi định dạng.
- Tạo CDN cache/prefetch.

Các xử lý đó thuộc media pipeline ngoài GridFS.

---

## 25. Khả năng khôi phục upload hỏng và orphan chunks

### 25.1. Upload đang dở

Giả sử chunks n=0,1 đã lưu nhưng process chết trước khi ghi xong files metadata. Có thể còn chunks với `files_id` không có document tương ứng trong `fs.files`.

### 25.2. Không tự xóa mọi chunks “không tìm thấy file” ngay lập tức

Một upload **đang diễn ra** cũng có thể đã tạo chunks trước khi ghi metadata file. Nếu cleanup job quét và xóa tất cả chunks “orphan” ngay, nó có thể phá upload đang hợp lệ.

Cần:

- Thời gian ân hạn.
- Theo dõi upload sessions/states.
- Kiểm tra hoạt động gần đây.
- Giới hạn phạm vi tenant/bucket.
- Cơ chế mark/sweep hoặc 2-phase cleanup.
- Cảnh báo và dry-run khi vận hành.

### 25.3. File metadata tồn tại nhưng chunk thiếu

Có thể do xóa trực tiếp collection, lỗi vận hành hoặc race. Driver thường phát hiện chunk sequence/length không hợp lệ khi đọc qua vùng bị hỏng.

Không coi một `fs.files` document tồn tại là bằng chứng tất cả chunks còn nguyên.

### 25.4. Xác minh integrity

Một quy trình kiểm tra:

1. Đọc `fs.files.length` và `chunkSize`.
2. Tính số chunk kỳ vọng.
3. Dùng GridFS API stream toàn bộ file để phát hiện chunk thiếu.
4. Tính SHA-256 và so với metadata app (nếu lưu).
5. Ghi audit/trạng thái lỗi.
6. Khôi phục từ backup hoặc yêu cầu re-upload nếu không thể sửa.

### 25.5. Backup và restore

Backup phải giữ **cả files và chunks** (và app metadata/assetVersions nếu có), với consistency policy phù hợp. Chỉ backup `fs.files` mà bỏ `fs.chunks` là không có nội dung binary.

### 25.6. Restore cần đồng bộ version pointers

Nếu phục hồi bucket ở thời điểm T1 nhưng `assets.currentFileId` ở T2, pointer có thể trỏ tới file không tồn tại. Backup/recovery plan phải phối hợp MongoDB data và app metadata, rồi reconciliation.

---

## 26. Xóa version cũ có điều kiện

### 26.1. Retention policy

Giả sử cần:

- Giữ mọi bản trong 30 ngày.
- Giữ current và 3 previous versions.
- Không xóa bản đang bị legal hold.
- Chỉ xóa sau khi không còn active download.
- Thực hiện audit.

Chính sách này **không có sẵn chỉ bằng filename/revision**. Cần metadata ứng dụng.

### 26.2. Ví dụ liệt kê candidates

~~~javascript
db.assetVersions.find({
  tenantId: "tenant-a",
  assetId: "ASSET-101",
  status: "READY",
  createdAt: {
    $lt: ISODate("2026-10-01T00:00:00Z")
  },
  legalHold: {
    $ne: true
  }
}).sort({
  version: 1
});
~~~

Lệnh chỉ liệt kê; trước khi xóa cần so với currentVersion, reference count và retention policy. Không copy thành `deleteMany()` production.

### 26.3. Quy trình xóa an toàn

~~~text
1. Chọn old version candidates.
2. Kiểm tra authorization/legal hold/current pointer.
3. Đánh dấu DELETING ở app metadata.
4. Ngăn new reads nếu policy yêu cầu.
5. Đợi grace period/active readers.
6. bucket.delete(fileId).
7. Ghi trạng thái DELETED/audit.
8. Retry khi mạng lỗi và xử lý partial deletion.
~~~

### 26.4. Khi delete thất bại một phần

Vì GridFS delete không được bao toàn bộ trong multi-document transaction, network lỗi có thể khiến trạng thái không rõ. Reconciliation phải kiểm tra files/chunks và có idempotent cleanup theo fileId, không chỉ trả 500 rồi bỏ quên.

### 26.5. Soft delete khác physical delete

Soft delete ẩn asset khỏi UI nhưng bytes có thể vẫn còn để phục hồi/tranh chấp pháp lý. Physical delete loại bỏ chunks; không thể “undo” nếu không có backup.

---

## 27. Versioning và đổi tên trong tài liệu có chữ ký

### 27.1. Rủi ro chọn `revision(-1)` khi ký

Nếu user ký `contract.pdf` lúc 10:00, nhưng một user khác upload bản mới cùng tên lúc 10:01, request download theo revision(-1) tại 10:02 có thể trả **nội dung khác** bản đã ký.

### 27.2. Cách pin nội dung

Khi tạo bản ký:

~~~javascript
{
  _id: "SIGN-101",
  assetId: "ASSET-101",
  signedFileId: ObjectId(
    "6914a9aa0000000000000002"
  ),
  signedSha256: "hash-v2",
  signedAt: ISODate("2026-11-14T10:00:00Z"),
  signerId: "user-101"
}
~~~

Sau đó download theo `signedFileId`, không theo filename/current/revision(-1).

### 27.3. Rename không thay chữ ký nội dung

Nếu chữ ký/approval gắn với **hash và fileId**, đổi tên hiển thị không làm bytes thay đổi. Nhưng audit/legal documents có thể yêu cầu lưu tên ở thời điểm ký, nên giữ `originalFilename` trong version metadata.

### 27.4. Đổi tên tất cả các bản hay chỉ bản current?

Cần quyết định rõ:

- Global asset displayName có thể đổi một lần cho tất cả UI.
- Physical GridFS filename của các bản lịch sử có thể giữ nguyên để audit.
- Có thể không cần gọi `bucket.rename` cho mọi revision.
- Bản lịch sử giữ tên gốc, bản current hiển thị tên mới qua `assets.displayName`.

Tách business displayName khỏi GridFS filename giúp tránh rename hàng trăm versions không cần thiết.

---

## 28. Quyền truy cập: file ID không phải token quyền

### 28.1. ObjectId không chứng minh người gọi có quyền

URL:

~~~text
GET /files/6914a9aa0000000000000001
~~~

có fileId hợp lệ, nhưng server vẫn phải kiểm tra:

- User đã đăng nhập/chứng thực chưa?
- Tenant có sở hữu asset không?
- User có role cho phép đọc không?
- Asset còn ACTIVE hay đã bị thu hồi?
- Version có được phép xem không?
- File có quét malware/validation hoàn tất chưa?
- Có restriction theo hợp đồng, thời hạn hoặc tổ chức?

### 28.2. Metadata GridFS không nhất thiết là nguồn quyền cuối

Bạn có thể lưu `metadata.tenantId` trong `fs.files`, nhưng authorization có thể cần đọc `assets`/`assetVersions` vì quyền và trạng thái thay đổi theo thời gian.

### 28.3. Tránh IDOR

IDOR là rủi ro người dùng thay `fileId` trong URL và tải file của người khác nếu backend chỉ kiểm tra ID tồn tại. Cần kiểm tra quyền **trước khi mở download stream**.

### 28.4. Không expose raw GridFS collections

Không cấp quyền truy cập trực tiếp `fs.chunks` cho user clients. API service chịu trách nhiệm auth, range validation, rate limiting và audit.

### 28.5. Signed download URLs

Nếu có signed URL:

- Gắn fileId/version/tenant/resource scope.
- Hết hạn nhanh, dùng signature mạnh.
- Không cho thay range/fileId nếu signature không bao phủ những phần cần bảo vệ.
- Có policy revoke nếu ứng dụng yêu cầu.
- Không log toàn bộ token hoặc secret.

---

## 29. Khi nào nên đổi chunk size?

### 29.1. Workload tải toàn bộ file

Nếu chủ yếu tải file PDF/archive lớn toàn bộ, chunk lớn có thể giảm số documents và overhead. Nhưng driver có thể sử dụng nhiều bộ nhớ trên mỗi chunk.

### 29.2. Workload đọc range nhỏ

Nếu thường đọc 4 KiB/16 KiB ngẫu nhiên, chunk nhỏ có thể giúp giảm dữ liệu chunk phải tải, tùy implementation và cache. Nhưng nhiều documents hơn tăng overhead.

### 29.3. Không thay default tùy tiện giữa upload lớn

Kích thước chunk là thuộc tính được lưu trong metadata từng file. Một upload đã bắt đầu không nên đổi chunkSize giữa chừng theo API. Upload mới có thể dùng khác.

### 29.4. Benchmark có ý nghĩa

Đo với tập dữ liệu thật:

- Tệp 1 MiB, 50 MiB, 2 GiB.
- HTTP ranges 4 KiB, 1 MiB, suffix 100 KiB.
- Sequential full download.
- 1, 10, 100 concurrent clients.
- MongoDB index size.
- Peak RAM/JVM GC.
- Chunks fetched/request.
- Network bandwidth.
- p95/p99 response latency.

Không chỉ so số bytes của một file rồi kết luận chunk size tối ưu.

---

## 30. GridFS indexes và explain

### 30.1. Kiểm tra indexes trong đúng bucket

~~~javascript
use media_lab

db.media.files.getIndexes();
db.media.chunks.getIndexes();
~~~

Khi bucket name là `media`, không nhìn `fs.files` rồi kết luận index của bucket media thiếu.

### 30.2. Query metadata nhiều revisions

~~~javascript
db.media.files.find({
  filename: "report.pdf"
}).sort({
  uploadDate: -1
}).explain("executionStats");
~~~

### 30.3. Query chunk range

~~~javascript
db.media.chunks.find({
  files_id: someFileId,
  n: {
    $gte: 10,
    $lte: 20
  }
}).sort({
  n: 1
}).explain("executionStats");
~~~

### 30.4. Metric cần xem

- Winning plan/index.
- Total keys examined.
- Total docs examined.
- nReturned.
- Query latency.
- Bytes đọc qua network.
- Disk/CPU khi nhiều concurrent streams.

### 30.5. Không lạm dụng direct chunk queries

Chúng phù hợp để **quan sát/diagnose**. Application code nên dùng GridFS driver vì driver còn kiểm tra integrity, xử lý ordered chunks và giữ compatibility.

---

## 31. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Download by filename trả bản khác | Tên trùng; default newest revision | Dùng fileId hoặc revision rõ |
| Download partial bị thiếu 1 byte | Nhầm end exclusive/inclusive | Dùng `end-start+1` |
| Range vượt EOF | Header không thỏa | Trả 416 + `Content-Range: bytes */L` |
| Suffix range không đúng | Hiểu `-500` là offset âm | Lấy 500 byte cuối |
| `skip(start)` dừng sớm | Skip trả ít hơn yêu cầu | Dùng `skipFully` |
| Tốn RAM khi download | Load entire file vào byte array | Streaming bounded buffer |
| HTTP 206 sai Content-Length | Đếm nhầm hoặc code gửi cả tệp | Copy đúng range length |
| Resume download ghép hai phiên bản | Download bằng filename/current không pin | FileId URL và `If-Range` |
| File tồn tại nhưng đọc lỗi chunk | Chunk thiếu/sai thứ tự/hỏng | Driver validation, audit, restore |
| Upload crash để lại chunks | Không commit toàn upload | Orphan cleanup có grace |
| Rename không đổi content | Rename chỉ đổi metadata filename | Upload version mới |
| Xóa một tên làm mất nhiều bản | Xóa theo filename rộng | Chọn fileId cụ thể |
| Tên trùng tenant khác | Filename không unique | Authorization + tenant filter |
| Tìm filename chậm | Thiếu index/regex khó tối ưu | Metadata index/search |
| Hash MD5 không có | Legacy field deprecated | SHA-256 app quản lý |
| Đang download thì file bị xóa | Race files/chunks | Retention/active reader grace |
| “Transaction” GridFS upload lỗi | GridFS không hỗ trợ multi-document transactions | Upload rồi publish app pointer |
| Nâng current version bị lost update | Hai upload cùng lúc | CAS/generation, transaction metadata |
| App pointer trỏ file không tồn tại | Publish trước upload hoặc restore lệch | Chỉ active sau success, reconciliation |

---

## 32. Kiểm thử HTTP Range thực tế

### 32.1. Test tệp rỗng

- Full GET trả 200, body 0 byte.
- `Range: bytes=0-0` không có byte để đọc; response 416 theo policy.

### 32.2. Test một byte

Tệp một byte:

- `Range: bytes=0-0` → 206, một byte.
- `bytes=1-1` → 416.
- `bytes=-1` → một byte.
- `bytes=0-` → một byte.

### 32.3. Test đúng ranh giới chunk

C=261120:

- `bytes=261119-261119`: byte cuối chunk 0.
- `bytes=261120-261120`: byte đầu chunk 1 (khi L>C).
- `bytes=261119-261120`: hai byte, hai chunks.
- `bytes=0-261119`: đúng một chunk đầy.

### 32.4. Test cuối file

Với L=600000:

- `bytes=599999-599999` → một byte.
- `bytes=599000-999999` → clamp end thành 599999.
- `bytes=600000-600100` → 416.

### 32.5. Test suffix

- `bytes=-500` → 500 bytes cuối.
- `bytes=-700000` với L=600000 → toàn bộ 600000 bytes trong response 206 hợp lệ.
- `bytes=-0` → không có range thỏa theo policy.
- `bytes=-999999999999999999999` → parser cần chống numeric overflow/DoS.

### 32.6. Test multiple range

`bytes=0-99,200-299`:

- Nếu API implement multipart, kiểm tra boundary/headers của từng phần.
- Nếu API không implement, có thể trả `200` full file, không giả vờ trả một phần bằng 206.

### 32.7. Test binary equality

Với file bytes ngẫu nhiên, so:

~~~text
response bytes == source[start .. endInclusive]
~~~

Không chỉ so Content-Length. Test across chunks và với nhiều chunk sizes khác nhau.

### 32.8. Test If-Range và ETag

- Download v1 first part.
- Upload v2/current pointer đổi.
- Client gửi Range kèm ETag v1 tới URL current.
- Response phải không ghép v2 với v1.
- URL fileId v1 có thể tiếp tục v1 nếu nội dung còn và được phép.

---

## 33. Kiểm thử tên tệp và revisions

### Test A — Hai files cùng filename

Upload `report.pdf` hai lần, kiểm tra `fs.files` có hai `_id` khác nhau.

### Test B — Revision 0 và -1

Tải `revision(0)` và `revision(-1)`; xác minh bytes lần lượt của bản đầu/cuối.

### Test C — Revision -2

Upload ba phiên bản và tải `-2`; kiểm tra là bản mới thứ hai.

### Test D — Rename một bản

Đổi tên chỉ fileId của v2. Đảm bảo v1/v3 vẫn ở nhóm tên cũ và v2 chuyển sang nhóm mới.

### Test E — Delete bản cũ

Xóa bằng ID v1. Bảo đảm v2 vẫn tải được; lưu ý revision numbering theo tên có thể thay đổi.

### Test F — Timestamp trùng

Tạo records có cùng uploadDate trong môi trường lab và kiểm tra UI cần tie-break/explicit logicalVersion; không dựa vào revision ordering như sequence bảo đảm.

### Test G — Tenant isolation

Hai tenants cùng upload `invoice.pdf`. User tenant-a không được tải fileId của tenant-b dù biết ID.

### Test H — Concurrent upload

Hai user upload khi asset generation=3. Kiểm tra CAS chỉ cho một thao tác publish current thành công, bên còn lại nhận conflict/merge policy.

### Test I — FileId pinning

Người dùng tải v1 qua `/files/{fileIdV1}`, sau đó v2 được tạo. URL v1 vẫn trả bytes v1 nếu retention cho phép.

### Test J — Retention/legal hold

Version cũ bị đánh dấu legal hold; cleanup không được physical delete.

---

## 34. Kịch bản ứng dụng: lưu video nhiều phiên bản

### 34.1. Data model

~~~javascript
{
  _id: "VIDEO-101",
  title: "Khoá học MongoDB",
  currentFileId: ObjectId("6914a9aa0000000000000002"),
  currentVersion: 2,
  status: "PUBLISHED"
}
~~~

### 34.2. Upload bản mới

- Video editor upload file v3 qua GridFS.
- Chờ upload/virus scan/transcode pipeline thành công.
- Tạo business version v3.
- Cập nhật current pointer có CAS.
- Giữ v2 trong thời gian rollback.
- Browser dùng URL v3 cho playback, tránh ghép ranges giữa v2/v3.

### 34.3. HTTP Range

Video player yêu cầu `bytes=...` tùy container/video codec. Server trả 206 với Content-Range chính xác, có ETag của v3 và cache policy phù hợp.

### 34.4. Đừng coi GridFS là adaptive streaming pipeline

Nếu muốn HLS/DASH, phải tạo các rendition/segment files riêng bằng media service. GridFS có thể lưu những segments đó, nhưng không tự encode video.

---

## 35. Kịch bản ứng dụng: hợp đồng cần lịch sử và audit

### 35.1. Nghiệp vụ

Một hợp đồng có v1 draft, v2 chỉnh sửa, v3 đã ký:

~~~text
Asset: CONTRACT-101
  v1 -> fileId=A, status=DRAFT
  v2 -> fileId=B, status=REVIEWED
  v3 -> fileId=C, status=SIGNED
  currentFileId=C
~~~

### 35.2. API nên dùng

~~~text
GET /contracts/CONTRACT-101
GET /contracts/CONTRACT-101/versions
GET /contracts/CONTRACT-101/versions/3/download
POST /contracts/CONTRACT-101/versions
POST /contracts/CONTRACT-101/restore?version=2
~~~

API không nên trả raw filename là định danh duy nhất.

### 35.3. Nguyên tắc ký

- Gắn signature/approval với `fileId` và SHA-256.
- Giữ immutable signed bytes.
- Rename displayName không được coi là content update.
- Retention/legal hold.
- Audit mọi attempt download/delete/version publish.
- Nếu restore v2, tạo event hoặc business revision mới theo policy.

---

## 36. Runbook khi một file GridFS tải lỗi

### Bước 1 — Xác định ID cụ thể

Đừng chỉ ghi “report.pdf lỗi”; ghi fileId, bucket, tenant, logical asset ID, requested range và HTTP status.

### Bước 2 — Kiểm tra metadata

~~~javascript
db.media.files.findOne({
  _id: suspectedFileId
});
~~~

Xác minh `length`, `chunkSize`, `filename`, `uploadDate` và metadata.

### Bước 3 — Kiểm tra indexes

~~~javascript
db.media.chunks.getIndexes();
db.media.files.getIndexes();
~~~

### Bước 4 — Kiểm tra chunks

~~~javascript
db.media.chunks.find(
  {
    files_id: suspectedFileId
  },
  {
    n: 1
  }
).sort({
  n: 1
});
~~~

Nếu số chunk hoặc sequence không phù hợp, cần phân loại corruption/partial deletion.

### Bước 5 — Reproduce bằng driver

Đọc full stream trong môi trường bảo mật, so checksum ứng dụng lưu, xác định lỗi ở chunk nào.

### Bước 6 — Kiểm tra race deletion

Có cleanup job hoặc user delete đúng lúc client tải không? Có legal hold/grace period không?

### Bước 7 — Khôi phục

Nếu bytes hỏng/thiếu, dùng backup/nguồn upload gốc. Không tự ghép chunk tùy ý khi không có nguồn dữ liệu xác thực.

### Bước 8 — Phòng tránh

Thêm retention, active download protection, metrics, orphan cleanup và failover tests.

---

## 37. Những hiểu lầm thường gặp

**“GridFS chỉ dùng được cho file lớn hơn 16 MiB.”** Không bắt buộc; file nhỏ cũng có thể lưu, nhưng overhead chunks/metadata có thể không đáng.

**“GridFS tự nén video và tạo thumbnails.”** Sai. Nó lưu bytes, không transcode.

**“Mỗi filename là duy nhất.”** Sai. Nhiều files có thể cùng tên.

**“`revision(-1)` luôn là cùng một bản.”** Sai. Bản mới được upload sẽ thay đổi latest.

**“`revision(0)` luôn là version 1 của business.”** Không nếu đã xóa/rename revisions hoặc thay chính sách; đó là vị trí theo uploadDate trong nhóm filename.

**“Rename thay đổi bytes của file.”** Sai. Chỉ đổi tên trong metadata.

**“Delete theo tên sẽ chỉ xóa bản mới nhất.”** Không nên suy luận; GridFS delete chuẩn dùng fileId, các helpers by-name tùy driver.

**“Đọc 100 byte phải tải toàn bộ file vào RAM.”** Sai. Có stream/partial retrieval.

**“`InputStream.skip(n)` chắc chắn skip đủ n.”** Sai. Kiểm tra giá trị trả về và lặp.

**“HTTP Range end là exclusive.”** Sai. `bytes=a-b` bao gồm cả a và b.

**“`Content-Range` không cần khi trả 206.”** Sai. Cần truyền đoạn bytes và tổng size chính xác.

**“Range vượt cuối file luôn là 416.”** Không đúng nếu start hợp lệ và chỉ end vượt; có thể clamp end.

**“`bytes=-500` là từ byte âm.”** Sai. Là 500 byte cuối.

**“Tệp rỗng có chunk data rỗng.”** GridFS chỉ cần files metadata length=0, không tạo empty chunks.

**“Tạo MongoDB transaction quanh upload sẽ làm tất cả chunks atomic.”** Sai. GridFS không hỗ trợ multi-document transactions như vậy.

**“Xóa file khi có reader vẫn an toàn tuyệt đối.”** Sai. Có race giữa files/chunks.

**“MD5 của GridFS là checksum chuẩn bảo mật hiện đại.”** Sai. Legacy/deprecated; ứng dụng có thể dùng SHA-256.

**“`fs.files` có là chunks chắc chắn đủ.”** Sai. Metadata tồn tại không chứng minh không có chunk thiếu.

**“Có fileId nên khỏi cần phân quyền.”** Sai. FileId không phải credential.

**“Đổi `chunkSizeBytes` sẽ re-chunk files cũ.”** Sai. Chỉ các uploads sau có cấu hình đó.

**“ETag chỉ cần filename.”** Sai. Filename có thể trỏ nội dung khác; ETag phải gắn với bytes/version.

**“Chỉ backup `fs.files` là có đủ file.”** Sai. Cần cả `fs.chunks` và app metadata.

**“Quét và xóa orphan chunks ngay lập tức không nguy hiểm.”** Sai. Có thể xóa chunks của upload đang chạy.

---

## 38. Checklist thiết kế production

### 38.1. Đọc theo phạm vi

- [ ] Dùng `long` cho length/offset.
- [ ] Phân biệt inclusive HTTP end và exclusive internal end.
- [ ] Xử lý `bytes=a-b`, `bytes=a-`, `bytes=-n`.
- [ ] Xử lý tệp rỗng.
- [ ] Trả `206` đúng `Content-Range` và `Content-Length`.
- [ ] Trả `416` cho unsatisfiable ranges.
- [ ] Có chính sách malformed/multiple ranges.
- [ ] Đóng GridFS streams khi client ngắt.
- [ ] Không tải toàn file vào memory.
- [ ] Có ETag/If-Range/HEAD policy.
- [ ] Kiểm thử tại chunk boundaries.

### 38.2. Filename/revisions

- [ ] Filename không là unique identity.
- [ ] Mỗi upload tạo fileId mới.
- [ ] App lưu assetId/logicalVersion nếu cần lịch sử bất biến.
- [ ] Download by ID cho signed/approved versions.
- [ ] Rename theo ID.
- [ ] Delete theo ID, không theo tên tùy tiện.
- [ ] Có policy rename nhóm revisions.
- [ ] Có tie-break khi uploadDate bằng nhau.
- [ ] Không dùng `-1` cho URL cache immutable.

### 38.3. Integrity, bảo mật và retention

- [ ] Quyền tenant/owner/visibility được kiểm tra.
- [ ] MIME/filename được sanitize.
- [ ] Malware/content validation phù hợp.
- [ ] SHA-256 nếu cần integrity.
- [ ] Có policy xử lý upload dang dở/orphans.
- [ ] Không delete khi active readers theo policy.
- [ ] Legal hold và retention theo app metadata.
- [ ] Backup đủ files/chunks/app metadata.
- [ ] Audit downloads/version changes.
- [ ] Không để user truy cập raw chunks.

### 38.4. Hiệu năng

- [ ] Chunk size được benchmark.
- [ ] Có compound unique index `files_id,n`.
- [ ] Có index `filename,uploadDate`.
- [ ] Có metadata index nếu workload cần.
- [ ] Quan sát database I/O và HTTP bandwidth.
- [ ] Giới hạn concurrent streams/range abuse.
- [ ] Dùng CDN/object storage khi workload phù hợp.

---

## 39. Bài tập thực hành

### Bài tập 1 — Giải thích GridFS structure

Tạo sơ đồ `fs.files` và `fs.chunks` cho tệp 600.000 B. Nêu số chunks, `files_id` và `n`.

### Bài tập 2 — Chunk math

Với C=261120 và L=600000, xác định firstChunk, lastChunk và số byte lấy từ mỗi chunk cho `bytes=260000-263000`.

### Bài tập 3 — Biên chunk

Giải thích `bytes=261119-261120` đi qua bao nhiêu chunks. Vì sao range dài 2 byte chứ không phải 1?

### Bài tập 4 — Java skip

Viết `skipFully(InputStream,long)` và test với InputStream giả có `skip()` mỗi lần chỉ trả tối đa 7 byte.

### Bài tập 5 — Java copyExactly

Viết `copyExactly` với buffer 64 KiB, test EOF sớm, count=0, count lớn hơn `Integer.MAX_VALUE`.

### Bài tập 6 — HTTP Range parser

Xây parser cho single-range. Test `bytes=0-0`, `bytes=500-`, `bytes=-500`, `bytes=599999-999999`, tệp rỗng và overflow.

### Bài tập 7 — Response HTTP đúng

Với L=600000 và `Range:bytes=1000-1999`, viết status/headers chính xác. Tại sao không dùng `200` nếu gửi chỉ một đoạn?

### Bài tập 8 — Multi-range

Phân tích `bytes=0-99,200-299`. Nếu gateway không hỗ trợ multipart, nên chọn response strategy nào?

### Bài tập 9 — ETag khi version đổi

Client tải nửa đầu từ v1, current chuyển sang v2. Thiết kế `If-Range` để không ghép bytes của hai bản.

### Bài tập 10 — Upload hai bản trùng filename

Upload v1 và v2 của `report.pdf` bằng Java GridFSBucket. Kiểm tra hai file IDs khác nhau.

### Bài tập 11 — Revision semantics

Upload ba versions cùng tên. Tải bằng `revision(0)`, `revision(1)`, `revision(-1)`, `revision(-2)`; so SHA-256 hoặc bytes.

### Bài tập 12 — Rename

Rename chỉ fileId v2 thành `report-reviewed.pdf`. Kiểm tra revisions nhóm tên cũ/mới thay đổi thế nào.

### Bài tập 13 — Delete

Xóa fileId v1, bảo đảm v2/v3 vẫn tải được. Khi nào cần retention/legal hold trước delete?

### Bài tập 14 — Metadata index

Tạo index `metadata.tenantId,metadata.assetId,uploadDate`. Chạy explain với query danh sách revisions theo tenant.

### Bài tập 15 — Business version vs revision

Mô hình hóa `assets` và `assetVersions` cho một tài liệu 5 versions. Giải thích vì sao `revision(-1)` không tương đương `currentVersion=5` trong mọi tình huống.

### Bài tập 16 — CAS conflict

Hai users upload cùng lúc khi `generation=3`. Viết conditional update bảo đảm chỉ một user publish version mới thành current.

### Bài tập 17 — Không transaction GridFS

Giải thích vì sao không đặt file upload 2 GB vào multi-document transaction và đề xuất upload-then-pointer pattern.

### Bài tập 18 — Orphan cleanup

Thiết kế job phát hiện orphan chunks mà không xóa chunks của upload đang hoạt động. Nêu grace period, dry-run và kiểm soát concurrency.

### Bài tập 19 — File checksum

Upload file và lưu SHA-256. Tải full stream để đối soát. Vì sao download range 1 KiB không xác minh full file?

### Bài tập 20 — Tenant security

Tạo hai tenants cùng upload `invoice.pdf`. Viết API resolution theo trusted tenant + assetId + versionId trước khi mở GridFS stream.

### Bài tập 21 — Video player

Thiết kế URL versioned, Range, ETag, CDN cache policy cho video nhiều versions. Nêu phần việc GridFS không tự làm (transcoding/HLS).

### Bài tập 22 — Backup/restore

Giả sử restore `media.files` mà quên `media.chunks`, điều gì xảy ra? Thiết kế reconciliation giữa `assetVersions.fileId` và GridFS metadata/chunks.

### Bài tập 23 — Stress test

Cho 100 concurrent range downloads và 50 full downloads. Đo latency, RAM, chunk fetch, MongoDB CPU và client abort rate.

### Bài tập 24 — Policy lưu 3 bản gần nhất

Thiết kế retention giữ current + 3 previous, không xóa legal hold và không xóa file đang được stream. Viết runbook xử lý partial deletion.

---

## 40. Câu hỏi ôn tập

1. Vì sao GridFS chia file thành chunks?
2. GridFS bucket mặc định dùng hai collections nào?
3. Chunk size mặc định hiện nay là bao nhiêu?
4. `fs.files.length` có đơn vị gì?
5. `fs.files.chunkSize` giúp tính điều gì?
6. `fs.chunks.files_id` trỏ tới field nào?
7. `fs.chunks.n` bắt đầu từ số nào?
8. Tệp rỗng có chunk rỗng không?
9. GridFS chunks có liên quan trực tiếp đến sharding chunks không?
10. HTTP `bytes=100-199` chứa bao nhiêu bytes?
11. HTTP Range end inclusive hay exclusive?
12. Chỉ số chunk chứa offset p được tính thế nào?
13. Range cắt qua hai chunks khác range nằm trong một chunk ra sao?
14. `InputStream.skip` có đảm bảo skip hết một lần không?
15. Tại sao nên dùng buffer giới hạn khi download?
16. `downloadToStream` và `openDownloadStream` khác nhau ở use case nào?
17. Khi nào trả HTTP 200 và khi nào 206?
18. `Content-Range` dùng để làm gì?
19. Khi nào trả 416?
20. `Range:bytes=-500` có nghĩa gì?
21. Nếu end requested vượt file length nhưng start hợp lệ, có phải 416 không?
22. Multiple range cần content type gì nếu được hỗ trợ?
23. Vì sao ETag cần gắn với đúng version?
24. `If-Range` giúp tránh lỗi nào?
25. `filename` có unique trong GridFS không?
26. Hai files cùng tên được phân biệt bằng gì?
27. Revision `0` là bản nào?
28. Revision `-1` là bản nào?
29. Tại sao revision index không là logical version bất biến?
30. Rename fileId thay đổi chunks không?
31. `bucket.delete(fileId)` có xóa các bản cùng tên khác không?
32. Xóa đồng thời với download có rủi ro gì?
33. Vì sao GridFS không hỗ trợ multi-document transactions?
34. Upload crash giữa chừng để lại dạng rác nào?
35. Vì sao orphan cleaner cần grace period?
36. GridFS `md5` có nên là checksum bảo mật hiện đại không?
37. Làm sao lưu SHA-256 và kiểm tra integrity?
38. Vì sao cần backup cả files và chunks?
39. Tại sao app nên có `assetId` và `assetVersions`?
40. Khi upload concurrent, CAS giúp gì?
41. Vì sao user không được đọc file chỉ vì biết ObjectId?
42. Khi đổi tên hiển thị, có nhất thiết rename mọi bản GridFS không?
43. Tại sao không tự chỉnh `fs.chunks.data` để sửa tệp?
44. Những indexes chuẩn của GridFS là gì?
45. Khi nào cần index metadata tenant/asset?
46. Chunk size nhỏ/lớn ảnh hưởng gì đến throughput và memory?
47. GridFS có tự tạo HLS/transcode video không?
48. Khi nào dùng object storage thay GridFS?
49. Nếu client ngắt HTTP download, phải đóng tài nguyên nào?
50. Tại sao một range read thành công chưa chứng minh toàn bộ file nguyên vẹn?

---

## 41. Tổng kết

**GridFS** chia nội dung file thành nhiều documents trong `<bucket>.chunks` và lưu thông tin mỗi file trong `<bucket>.files`. Điều này cho phép lưu tệp lớn hơn giới hạn BSON document và sử dụng streaming để truy cập dữ liệu.

Ba nhóm kiến thức quan trọng:

**1. Đọc theo phạm vi**

- Dùng `length` và `chunkSize` để xác định những chunks liên quan.
- HTTP `Range: bytes=a-b` có cả hai đầu **inclusive**.
- Với Java Sync Driver, dùng `openDownloadStream`, `skipFully` và `copyExactly`.
- Trả `206` kèm `Content-Range`/`Content-Length` đúng; `416` khi range không thể thỏa.
- Tránh tải cả file vào RAM; quản lý ETag/If-Range, tệp rỗng và nhiều ranges.

**2. Quản lý tên tệp**

- `filename` chỉ là nhãn, **không unique**.
- `fileId` nhận diện chính xác một bản.
- `rename(fileId,newName)` chỉ đổi metadata, không sửa chunks.
- Khi dùng URL public hoặc audit, xác thực quyền và ưu tiên fileId/versionId.
- Filename không phải security boundary, checksum hoặc cache validator.

**3. Nhiều phiên bản**

- GridFS revisions theo filename và `uploadDate`: `0` là cũ nhất, `-1` mới nhất, `-2` gần mới nhất.
- Revision position có thể thay đổi khi upload/delete/rename, không phải business version bất biến.
- Nên có `assets.currentFileId`, `assetVersions` và `generation` cho versioning nghiêm túc.
- Mỗi lần đổi bytes nên upload fileId mới, validate rồi publish pointer.
- GridFS không hỗ trợ multi-document transactions cho file operations; cần xử lý orphan upload, concurrent readers/deletion, backup và cleanup có kiểm soát.

**Quy tắc vận hành đáng nhớ:** Khi client yêu cầu “tải 1.000 bytes của **phiên bản đã chọn**”, ứng dụng phải biết **chính xác fileId nào, byte range nào, quyền truy cập nào và trạng thái file nào**, thay vì chỉ nhận một filename rồi đoán bản mới nhất.

## Tài liệu tham khảo

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — GridFS Indexes](https://www.mongodb.com/docs/manual/core/gridfs/#gridfs-indexes)
- [MongoDB GridFS Specification — Data Model, Revisions, Partial Reads](https://specifications.readthedocs.io/en/latest/gridfs/gridfs-spec/)
- [MongoDB Java Sync Driver — Large File Storage with GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Java Sync Driver — GridFS API](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/driver-sync/com/mongodb/client/gridfs/package-summary.html)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Manual — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MDN — HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)
- [MDN — Content-Range](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Range)
- [RFC 9110 — HTTP Semantics, Range Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests)
