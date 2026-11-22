# JDBC dữ liệu: Đọc ghi LOB qua stream và giải phóng bằng free

## Mục tiêu học tập

**LOB (Large Object)** trong JDBC là cách làm việc với dữ liệu lớn lưu ở cột database, chủ yếu là **BLOB** (binary large object), **CLOB** (character large object) và **NCLOB** (national character large object). Thay vì nạp toàn bộ ảnh, tài liệu hoặc đoạn văn bản nhiều MB/GB vào một **byte[]** hay **String**, JDBC cung cấp **InputStream, OutputStream, Reader và Writer** để truyền dữ liệu thành từng phần. Khi API trả về một đối tượng **Blob/Clob/NClob**, ứng dụng còn phải quản lý **tài nguyên locator/bộ nhớ phía driver** bằng **free()** khi không cần nữa.

Chủ đề của bài là **“Đọc ghi LOB qua stream và giải phóng bằng free”**, thuộc nhóm **JDBC dữ liệu**. Sau bài, bạn có thể:

1. Phân biệt **Blob**, **Clob**, **NClob**, byte stream, character stream và những phương thức JDBC liên quan.
2. Đọc BLOB bằng **Blob.getBinaryStream()** hoặc **ResultSet.getBinaryStream(...)**; đọc CLOB bằng **Clob.getCharacterStream()** hoặc **ResultSet.getCharacterStream(...)** mà không gọi getBytes/getSubString lên toàn bộ dữ liệu lớn.
3. Ghi vào cột LOB bằng **PreparedStatement.setBlob(..., InputStream)**, **setClob(..., Reader)**, các overload có **length**, và các biến thể stream nếu driver hỗ trợ.
4. Dùng **Connection.createBlob/createClob** cùng **Blob.setBinaryStream(1)**, **Clob.setCharacterStream(1)** khi cần tạo đối tượng LOB phía client/driver, và biết khi nào phương án đó không cần thiết.
5. Quản lý đúng thứ tự **mở stream → đọc/ghi → đóng stream → gọi free() → đóng ResultSet/Statement/Connection**.
6. Hiểu **free() không xóa dữ liệu đã lưu trong database** và sau khi free thì đối tượng LOB không còn hợp lệ.
7. Phân biệt **byte count** với **character count**, xử lý Unicode tiếng Việt đúng loại stream và encoding.
8. Phát hiện các lỗi production: locator không còn hợp lệ sau transaction, resource leak, OOM do materialization, sai length, driver không hỗ trợ stream overload hoặc cleanup che lỗi ban đầu.
9. Chạy một chương trình **Java 17+ hoàn chỉnh** dùng SerialBlob/SerialClob để kiểm chứng đọc tuần tự, checksum, Unicode và free() mà không cần database thật; hiểu giới hạn của test này.
10. Thiết kế integration tests trên JDBC driver/server thật để xác nhận streaming, transaction, memory, hiệu năng và cleanup.

**Phạm vi:** Chỉ dùng JDBC API và kiến thức còn được hỗ trợ hiện nay. Ví dụ chính đã được biên dịch trên **OpenJDK 24.0.2** với **javac --release 17** và chạy thành công. Các đoạn mô tả database driver được đánh dấu rõ là **mảnh mã cần Connection thật**, không bịa kết quả DB cụ thể.

## 1. LOB là gì?

Một bảng tài liệu có thể có cấu trúc SQL minh họa:

~~~sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    payload BLOB,
    body CLOB
);
~~~

Cú pháp DDL, hỗ trợ BLOB/CLOB và giới hạn kích thước khác nhau giữa DBMS; đoạn trên chỉ mô tả mô hình dữ liệu để hiểu ví dụ, **không phải SQL được bảo đảm chạy trên mọi database**.

- **BLOB**: dữ liệu **nhị phân**. Phù hợp ảnh, PDF, ZIP, các blob mã hóa hoặc binary payload đã xác định rõ semantics.
- **CLOB**: dữ liệu **ký tự**, ví dụ nội dung văn bản Unicode dài. JDBC dùng **Reader/Writer** để ứng dụng thao tác với characters.
- **NCLOB**: dữ liệu character large object thuộc **national character set** ở DBMS có phân biệt kiểu này. Java interface **NClob** kế thừa **Clob**; hỗ trợ phụ thuộc driver/database.

So sánh:

| Đặc điểm | BLOB | CLOB | NCLOB |
| --- | --- | --- | --- |
| SQL type | BLOB | CLOB | NCLOB |
| Java interface | java.sql.Blob | java.sql.Clob | java.sql.NClob |
| Đọc dạng stream | **InputStream** | **Reader** | **Reader** |
| Ghi qua PreparedStatement | setBlob | setClob | setNClob |
| Đọc qua ResultSet | getBlob | getClob | getNClob |
| Dữ liệu chính | Bytes | Characters | Characters ở national charset |
| Tài nguyên phải giải phóng | Blob.free() | Clob.free() | NClob.free() qua Clob |
| Độ dài logic | **Bytes** | **Characters** | **Characters** |

**Không dùng Blob cho mọi nội dung chỉ vì nó “lớn”.** Với văn bản tiếng Việt, nếu schema có CLOB phù hợp, API Reader tránh việc tự đoán encoding của dữ liệu SQL character. Ngược lại, khi cần giữ **byte-for-byte** một file hoặc tài liệu có chữ ký, BLOB là lựa chọn rõ ràng hơn.

### 1.1. LOB có thể là locator thay vì toàn bộ dữ liệu

Theo JDBC Javadoc, driver thường có thể biểu diễn Blob/Clob bằng **locator**: một logical pointer tới LOB trong database thay vì tải ngay toàn bộ nội dung xuống Java heap.

~~~text
ResultSet.getBlob("payload")
            │
            ▼
     Blob object / locator
            │
      getBinaryStream()
            │
            ▼
    [chunks of bytes] ──> OutputStream
            │
           free()
            │
            ▼
      driver/server resources released
~~~

Một locator có thể cần connection/transaction còn sống để đọc dữ liệu. **Không giữ Blob/Clob/streams sau khi transaction kết thúc hoặc connection/result set đã đóng rồi mặc định vẫn truy cập được.** Tài liệu JDBC mô tả các đối tượng LOB theo locator là hợp lệ trong transaction nơi chúng được tạo; implementation chi tiết, buffering và khả năng đọc sau commit phụ thuộc driver.

### 1.2. Stream API không bảo đảm server streaming thật

Việc ứng dụng dùng **getBinaryStream** hoặc **setBlob(InputStream)** không tự bảo đảm driver sẽ giữ mức dùng RAM hằng số và stream từng chunk trực tiếp trên network. Một driver có thể buffer một phần/toàn bộ giá trị, tạo temporary LOB hoặc dùng giao thức riêng.

Những gì ứng dụng kiểm soát:

- Không chủ động gọi **readAllBytes()** hoặc đưa mọi dữ liệu vào **byte[]** nếu không cần.
- Duy trì stream mở đủ lâu để driver sử dụng.
- Dùng buffer hữu hạn khi tự copy.
- Đóng stream và giải phóng LOB.
- Benchmark/integration test với **driver + DBMS + server config** thật để xác nhận memory/throughput/cancellation behavior.

## 2. Những API đọc LOB qua stream

### 2.1. BLOB từ ResultSet

Khi câu SQL trả cột **payload** dạng BLOB:

~~~java
// Mảnh code minh họa khi ResultSet rs đang ở đúng dòng.
Blob blob = rs.getBlob("payload");
if (blob != null) {
    try {
        try (InputStream in = blob.getBinaryStream()) {
            // Đọc dữ liệu nhị phân theo chunks vào một sink.
        }
    } finally {
        blob.free();
    }
}
~~~

**getBlob** có thể trả **null** nếu giá trị SQL là NULL. Kiểm tra trước khi mở stream hoặc gọi free.

**Blob.getBinaryStream()** trả **java.io.InputStream** chứa bytes. Đọc bằng **InputStream.read(byte[])** hoặc **transferTo(...)** trong Java 17+, tránh đưa cả giá trị lên heap nếu nó rất lớn.

### 2.2. CLOB từ ResultSet

~~~java
// Mảnh code minh họa khi ResultSet rs đang ở đúng dòng.
Clob clob = rs.getClob("body");
if (clob != null) {
    try {
        try (Reader reader = clob.getCharacterStream()) {
            // Đọc ký tự Unicode theo từng đoạn.
        }
    } finally {
        clob.free();
    }
}
~~~

**Clob.getCharacterStream()** trả **Reader**, không phải InputStream. JDBC driver chịu trách nhiệm chuyển representation SQL character sang ký tự mà Java Reader cung cấp; caller không tự dùng bytes/UTF-8 ở giữa nếu chỉ cần xử lý text.

### 2.3. Lấy stream trực tiếp từ ResultSet

Ngoài Blob/Clob objects, JDBC còn có:

~~~java
// Mảnh minh họa, không phải file độc lập.
try (InputStream bytes = rs.getBinaryStream("payload")) {
    if (bytes != null) {
        bytes.transferTo(binaryOutput);
    }
}

try (Reader chars = rs.getCharacterStream("body")) {
    if (chars != null) {
        chars.transferTo(characterWriter);
    }
}
~~~

Đây là cách **không tạo Blob/Clob object trong code**, nên không có biến Blob/Clob để gọi free(). Bạn **vẫn phải đóng InputStream/Reader** và giữ ResultSet/Connection hợp lệ trong lúc đọc. Hãy xem contract của driver về cột type và streaming của ResultSet; một số driver quản lý stream theo current row và có thể đóng stream khi chuyển cursor hoặc đọc một cột khác.

**Không dùng ResultSet.next() trước khi đọc hết stream của dòng hiện tại.** Khi cần hai LOB columns, đọc trọn vẹn từng stream trong khi ResultSet đang ở dòng đó. Không gọi getBytes/getString lên toàn bộ LOB chỉ để biết nó có dữ liệu.

### 2.4. Lấy một phần LOB

JDBC có các overload:

~~~java
InputStream partOfBlob = blob.getBinaryStream(longPosition, longLength);
Reader partOfClob = clob.getCharacterStream(longPosition, longLength);
~~~

**Position bắt đầu ở 1**, không phải 0, và **length** không âm. Với BLOB, length tính theo **bytes**; với CLOB, theo **characters**. Không tự chuyển một offset byte của file UTF-8 thành offset ký tự CLOB và mong đúng.

Các methods partial có thể báo **SQLFeatureNotSupportedException** ở driver không hỗ trợ. Luôn kiểm tra phần tử và giới hạn hợp lệ, không cast một LOB lớn xuống int nếu không cần.

## 3. Ghi vào LOB qua PreparedStatement

### 3.1. Ghi BLOB bằng InputStream

Giả sử đã có bảng documents(id, payload, body) phù hợp với schema của database:

~~~java
// Mảnh minh họa với Connection conn, Path file và long id đã có.
try (InputStream input = Files.newInputStream(file);
     PreparedStatement ps = conn.prepareStatement(
             "INSERT INTO documents(id, payload) VALUES (?, ?)")) {
    ps.setLong(1, id);
    ps.setBlob(2, input, Files.size(file));
    ps.executeUpdate();
}
~~~

**setBlob(parameterIndex, InputStream, long length)** nói rõ rằng parameter nên được gửi như SQL **BLOB**, với **length là số bytes**. InputStream có thể được driver đọc trong **executeUpdate()**, không nhất thiết trong lúc gọi setBlob. Vì vậy **giữ input mở đến khi execute hoàn tất**.

Không đặt InputStream trong một try-with-resources kết thúc **trước** ps.executeUpdate(). Nếu driver đọc lazy, binding trước đó chỉ lưu stream reference; đóng stream quá sớm gây dữ liệu thiếu/lỗi.

### 3.2. Ghi CLOB bằng Reader

Với file văn bản UTF-8:

~~~java
// Mảnh minh họa với Connection conn, Path textFile và long id.
try (Reader reader =
             Files.newBufferedReader(textFile, StandardCharsets.UTF_8);
     PreparedStatement ps = conn.prepareStatement(
             "INSERT INTO documents(id, body) VALUES (?, ?)")) {
    ps.setLong(1, id);
    ps.setClob(2, reader);
    ps.executeUpdate();
}
~~~

**setClob(parameterIndex, Reader)** báo driver rằng parameter là SQL **CLOB**. Bản overload không có length giúp tránh phải đếm trước toàn bộ ký tự; hiệu quả thực tế tùy driver. **File input được mở dưới dạng UTF-8** vì đây là encoding của file ngoài; sau khi đi vào Reader, dữ liệu là ký tự và driver xử lý chuyển đổi sang CLOB SQL.

Nếu driver hỗ trợ/ưu tiên overload có length, hãy dùng **setClob(index, reader, longCharacterLength)** với số **characters**, không phải **Files.size(textFile)** (bytes). File UTF-8 có dấu tiếng Việt thường có byte size khác character count.

### 3.3. Các overload với length và không length

| API | Nội dung được truyền | Có cần length? |
| --- | --- | --- |
| **setBlob(i, InputStream, long)** | BLOB bytes | Có, length tính bytes |
| **setBlob(i, InputStream)** | BLOB bytes | Không |
| **setClob(i, Reader, long)** | CLOB characters | Có, length tính characters |
| **setClob(i, Reader)** | CLOB characters | Không |
| **setNClob(i, Reader, long)** | NCLOB characters | Có |
| **setNClob(i, Reader)** | NCLOB characters | Không |
| **setBinaryStream(i, InputStream, long)** | Binary stream param | Có; driver quyết định/chuyển theo SQL parameter type |
| **setCharacterStream(i, Reader, long)** | Character stream param | Có; driver quyết định/chuyển theo SQL parameter type |

JDBC docs lưu ý **setBlob/setClob** có thể giảm ambiguity so với setBinaryStream/setCharacterStream khi driver cần biết phải gửi **BLOB/CLOB** thay vì **LONGVARBINARY/LONGVARCHAR**. Khi schema là BLOB/CLOB, overload được đặt tên tương ứng thường rõ mục đích hơn.

Các overload length có contract về số bytes/characters. Với **setBlob(i, input, length)**, nếu stream không cung cấp đúng số bytes, driver có thể báo SQLException khi execute. Với **setClob(i, reader, length)**, nếu Reader không có đúng số characters được khai báo, việc execute cũng có thể báo lỗi. **Không truyền -1 làm “unknown length”** cho overload yêu cầu length không âm; dùng overload không length nếu phù hợp.

### 3.4. Đừng đóng stream trước executeBatch

Nếu bind stream rồi gọi **addBatch()** và chỉ sau đó **executeBatch()**, driver có thể chờ đến executeBatch mới đọc dữ liệu. Không dùng một stream đã đóng/reused cho nhiều batch entries nếu chưa xác minh behavior của driver. Nếu batch rất lớn, cần quản lý nguồn lực/throughput rõ ràng và có test với driver thật.

### 3.5. Ghi SQL NULL

Một cột LOB có thể là **NULL**, khác với BLOB dài 0 bytes hoặc CLOB dài 0 characters. Khi cần ghi NULL theo schema:

~~~java
ps.setNull(2, java.sql.Types.BLOB);
ps.setNull(3, java.sql.Types.CLOB);
~~~

Đây là mảnh minh họa trong một PreparedStatement đã có đúng parameter indexes. Đừng dùng InputStream null mà không hiểu overload/driver semantics; explicit setNull giúp ý nghĩa rõ.

## 4. Khi nào dùng createBlob/createClob và stream ghi trên đối tượng?

Ngoài bind trực tiếp InputStream/Reader, JDBC có thể tạo LOB object qua Connection:

~~~java
Blob blob = conn.createBlob();
Clob clob = conn.createClob();
~~~

Sau đó:

~~~java
try {
    try (OutputStream out = blob.setBinaryStream(1L);
         InputStream in = Files.newInputStream(binaryFile)) {
        in.transferTo(out);
    }

    try (Writer out = clob.setCharacterStream(1L);
         Reader in = Files.newBufferedReader(
                 textFile, StandardCharsets.UTF_8)) {
        in.transferTo(out);
    }

    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO documents(id, payload, body) VALUES (?, ?, ?)")) {
        ps.setLong(1, id);
        ps.setBlob(2, blob);
        ps.setClob(3, clob);
        ps.executeUpdate();
    }
} finally {
    try {
        blob.free();
    } finally {
        clob.free();
    }
}
~~~

**Đây là mảnh code cần Connection, id, binaryFile, textFile có thật**, không phải chương trình chạy độc lập. Các declarations/imports cần có ở scope gọi.

**Vì sao position=1L?** Những methods như Blob.setBinaryStream(pos) và Clob.setCharacterStream(pos) dùng **vị trí bắt đầu 1-based**. Trên một LOB mới rỗng, ghi từ vị trí 1 là cách đơn giản nhất.

**Thứ tự quan trọng:**

1. Tạo LOB objects.
2. Mở stream ghi trên LOB, copy dữ liệu.
3. Đóng OutputStream/Writer để kết thúc ghi.
4. Bind Blob/Clob vào PreparedStatement và **execute** trong khi object còn hợp lệ.
5. Đóng statement.
6. **free()** cả Blob và Clob kể cả khi có lỗi.

Phương án này phù hợp khi driver yêu cầu LOB objects hoặc API của bạn cần chỉnh sửa qua Blob/Clob. Nhưng **không có bảo đảm createBlob/createClob sẽ stream trực tiếp**; driver có thể cấp temporary LOB, buffer nội dung hoặc chỉ hỗ trợ một phần chức năng. Với yêu cầu ghi từ file/reader đơn giản, **setBlob(InputStream)/setClob(Reader)** thường ít bước và dễ quản lý hơn.

**Cẩn thận cleanup khi một lời gọi tạo LOB thất bại.** Đoạn minh họa khởi tạo cả hai ở ngoài try; trong code production nên thiết kế để Blob đã tạo được vẫn được free nếu createClob thất bại, và giữ primary exception khi một free() cũng thất bại. Xem phần xử lý lỗi.

### 4.1. Không sửa LOB sau khi free

~~~java
blob.free();
// blob.length(), blob.getBytes(...), blob.getBinaryStream() không còn hợp lệ.
~~~

Sau **free()**, JDBC quy định các method khác trên đối tượng Blob/Clob sẽ phát sinh SQLException. Gọi **free()** lần nữa không làm gì; free là idempotent theo contract.

**free() không chạy DELETE, không làm mất giá trị đã INSERT/UPDATE trong cột database.** Nó giải phóng những tài nguyên mà đối tượng Java/driver đang giữ; dữ liệu database chỉ thay đổi theo SQL và transaction đã thực hiện.

### 4.2. Phiên bản JDK và AutoCloseable

Một khác biệt API cần nêu rõ khi viết code có **--release 17**:

- Trong **Java SE 17**, interface **Blob** và **Clob** có **free()**, nhưng **chưa extends AutoCloseable**. Do đó code kiểu **try (Blob b = ...)** **không compile với --release 17**. Hãy gọi **free() trong finally** như ví dụ chính.
- Trong **Java SE 26**, tài liệu **Blob** và **Clob** khai báo **extends AutoCloseable** và có default **close()** giải phóng LOB. Khi target runtime/API mới phù hợp, try-with-resources trực tiếp cho LOB là lựa chọn được hỗ trợ.
- Cả trong API mới, **free() vẫn còn và hợp lệ**. Code dùng explicit free() có thể giữ khả năng tương thích Java 17+ và thể hiện rõ vòng đời tài nguyên.

Đừng copy ví dụ dùng try-with-resources trên Blob/Clob của một tài liệu JDK mới rồi biên dịch bằng --release 17 mà nghĩ lỗi compiler là do driver.

## 5. Đọc file LOB ra đĩa với Connection thật

Với bảng documents và đúng driver, hai phương thức sau được cung cấp trong code Java hoàn chỉnh ở phần 6:

~~~java
// Mảnh code: Connection conn do ứng dụng mở; Path output do caller cung cấp.
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT payload, body FROM documents WHERE id = ?")) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Blob blob = rs.getBlob("payload");
            if (blob != null) {
                try {
                    try (InputStream in = blob.getBinaryStream();
                         OutputStream out = Files.newOutputStream(binaryOut)) {
                        in.transferTo(out);
                    }
                } finally {
                    blob.free();
                }
            }

            Clob clob = rs.getClob("body");
            if (clob != null) {
                try {
                    try (Reader in = clob.getCharacterStream();
                         Writer out = Files.newBufferedWriter(
                                 textOut, StandardCharsets.UTF_8)) {
                        in.transferTo(out);
                    }
                } finally {
                    clob.free();
                }
            }
        }
    }
}
~~~

**Code trên giữ ResultSet và Connection hợp lệ trong suốt lúc sử dụng Blob/Clob streams**. Output file nhị phân được tạo bằng OutputStream; output văn bản được tạo bằng Writer UTF-8. **Reader.transferTo(Writer)** và **InputStream.transferTo(OutputStream)** có mặt trong Java 17, nên ví dụ compile được với --release 17.

Trong hệ thống production, cần kiểm soát **output path, quyền ghi, tính atomic của file**, và dọn file dở dang nếu streaming lỗi giữa chừng. Đừng để người dùng đưa arbitrary path lên server rồi ghi đè tệp ngoài phạm vi được phép.

### 5.1. SQL NULL và file output

Nếu giá trị một cột là SQL NULL, **getBlob/getClob** trả null. Ví dụ trên sẽ **không tạo file tương ứng**. Đây là một policy minh họa; sản phẩm cần định nghĩa việc NULL có nghĩa “không có file”, “file rỗng”, hay một trường hợp lỗi dữ liệu. **Không tự đánh đồng NULL với empty BLOB/CLOB**.

### 5.2. Kết thúc transaction đúng lúc

Nếu Connection đang trong transaction, tránh gọi **commit/rollback** hoặc đóng Connection trước khi hoàn tất mọi reads từ locator, trừ khi driver tài liệu hóa hỗ trợ. JDBC mô tả LOB locator thường hợp lệ trong transaction được tạo.

Để an toàn và dễ kiểm chứng:

~~~text
open Connection / transaction
      │
      ▼
execute SELECT → ResultSet row
      │
      ▼
get Blob / Clob
      │
      ▼
read all needed stream bytes/chars
      │
      ▼
close stream
      │
      ▼
free Blob / Clob
      │
      ▼
close ResultSet / Statement
      │
      ▼
commit/rollback/close Connection theo transaction ownership
~~~

Nếu caller sở hữu transaction, helper đọc LOB **không tự commit**; nó chỉ trả về sau khi đã hoàn tất công việc. Không đóng Connection bên trong helper nếu Connection được caller/pool quản lý.

### 5.3. Lưu lượng và memory

**InputStream.transferTo** dùng copy theo stream mà không cần đưa toàn bộ nội dung vào một mảng trong code caller; nhưng nó không giới hạn kích thước dữ liệu, không có built-in quota cho tệp đích và không có bảo đảm network buffering của driver.

Với file upload/download lớn, nên:

- Giới hạn kích thước ở tầng API.
- Theo dõi bytes/chars đã đọc, phát hiện dữ liệu vượt quota.
- Xử lý cancellation, timeout, network failure và client disconnect.
- Có chính sách retry riêng; không retry mù quáng một stream đã tiêu thụ.
- Lưu checksum/length khi nghiệp vụ yêu cầu toàn vẹn.
- Benchmark memory của chính JDBC driver và DBMS, không đo mỗi vòng lặp Java.

## 6. Ví dụ Java 17+ hoàn chỉnh: đọc streams, checksum và free()

Để minh họa một cách **thực sự runnable** không cần dựng server/database, chương trình sử dụng **javax.sql.rowset.serial.SerialBlob/SerialClob**. Đây là các implementation chuẩn của module **java.sql.rowset**, tạo từ **byte[]/char[]** và giữ dữ liệu trong RAM. Chúng thích hợp để kiểm thử **API đọc và free**, nhưng **không phải ví dụ tiết kiệm RAM ở backend cho LOB cực lớn**.

Đồng thời, class khai báo hai helper **insert(...)** và **export(...)** cần Connection thật. Compiler kiểm tra các chữ ký JDBC của helper đó, nhưng **main() không gọi** vì không có driver/SQL server trong test. Chỉ phần SerialBlob/SerialClob được thực thi.

### 6.1. File duy nhất: LobStreamDemo.java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Blob;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HexFormat;
import javax.sql.rowset.serial.SerialBlob;
import javax.sql.rowset.serial.SerialClob;

public final class LobStreamDemo {
    // A real JDBC driver and a documents(id, payload, body) table
    // are required to execute these two methods.
    static void insert(Connection conn, long id, Path binary, Path utf8Text)
            throws SQLException, IOException {
        try (InputStream bytes = Files.newInputStream(binary);
             Reader chars = Files.newBufferedReader(
                     utf8Text, StandardCharsets.UTF_8);
             PreparedStatement ps = conn.prepareStatement(
                     "INSERT INTO documents(id, payload, body) VALUES (?, ?, ?)")) {
            ps.setLong(1, id);
            ps.setBlob(2, bytes, Files.size(binary));
            ps.setClob(3, chars);
            ps.executeUpdate(); // The streams stay open through execution.
        }
    }

    static boolean export(Connection conn, long id, Path binaryOut,
                          Path textOut) throws SQLException, IOException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT payload, body FROM documents WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return false;
                }
                Blob blob = rs.getBlob("payload");
                if (blob != null) {
                    try {
                        try (InputStream in = blob.getBinaryStream();
                             OutputStream out = Files.newOutputStream(binaryOut)) {
                            in.transferTo(out);
                        }
                    } finally {
                        blob.free();
                    }
                }
                Clob clob = rs.getClob("body");
                if (clob != null) {
                    try {
                        try (Reader in = clob.getCharacterStream();
                             Writer out = Files.newBufferedWriter(
                                     textOut, StandardCharsets.UTF_8)) {
                            in.transferTo(out);
                        }
                    } finally {
                        clob.free();
                    }
                }
                return true;
            }
        }
    }

    // Self-contained test: real JDK SerialBlob/SerialClob objects in RAM.
    // They are not DB-backed or proof that a vendor driver will stream.
    public static void main(String[] args)
            throws SQLException, IOException, NoSuchAlgorithmException {
        byte[] source = new byte[100_003];
        for (int i = 0; i < source.length; i++) {
            source[i] = (byte) (i * 31 + 7);
        }

        Blob blob = new SerialBlob(source);
        long blobLength = blob.length();
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        long bytesRead = 0;
        try {
            try (InputStream in = blob.getBinaryStream()) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    sha256.update(buffer, 0, n);
                    bytesRead += n;
                }
            }
        } finally {
            blob.free();
        }
        System.out.println("blobLength=" + blobLength);
        System.out.println("blobBytesRead=" + bytesRead);
        System.out.println("blobSHA256=" +
                HexFormat.of().formatHex(sha256.digest()));
        boolean blobInvalid = false;
        try {
            blob.length();
        } catch (SQLException expected) {
            blobInvalid = true;
        }
        System.out.println("blobInvalidAfterFree=" + blobInvalid);

        String vietnamese = "Tiếng Việt: ắ, Đặng; emoji 😀";
        Clob clob = new SerialClob(vietnamese.toCharArray());
        long clobLength = clob.length();
        StringWriter sink = new StringWriter();
        long charsRead = 0;
        try {
            try (Reader in = clob.getCharacterStream()) {
                char[] buffer = new char[7];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    sink.write(buffer, 0, n);
                    charsRead += n;
                }
            }
        } finally {
            clob.free();
        }
        System.out.println("clobLength=" + clobLength);
        System.out.println("clobCharsRead=" + charsRead);
        System.out.println("clobRoundTrip=" + vietnamese.equals(sink.toString()));
        boolean clobInvalid = false;
        try {
            clob.length();
        } catch (SQLException expected) {
            clobInvalid = true;
        }
        System.out.println("clobInvalidAfterFree=" + clobInvalid);
    }
}
~~~

### 6.2. Biên dịch và chạy

Ở thư mục có file **LobStreamDemo.java**, dùng **JDK 17+**:

~~~bash
javac -encoding UTF-8 --release 17 LobStreamDemo.java
java LobStreamDemo
~~~

Trên PowerShell, hai lệnh cũng giống như trên:

~~~powershell
javac -encoding UTF-8 --release 17 LobStreamDemo.java
java LobStreamDemo
~~~

Vì **java.sql.rowset** là module chuẩn trong JDK, ví dụ không cần dependency thư viện JDBC vendor. Java launcher từ một JDK đầy đủ có thể sử dụng module này qua classpath code như chương trình trên.

### 6.3. Stdout chính xác đã kiểm chứng

~~~text
blobLength=100003
blobBytesRead=100003
blobSHA256=2a1683cff214df29e77df156a515258190a1bc11526d41cd2b34e72a23b6b7d6
blobInvalidAfterFree=true
clobLength=29
clobCharsRead=29
clobRoundTrip=true
clobInvalidAfterFree=true
~~~

**Đã kiểm chứng 8 dòng output trên OpenJDK 24.0.2** sau khi compile bằng **--release 17**.

### 6.4. Giải thích kết quả

- **blobLength=100003**: BLOB của test có 100.003 bytes; kích thước cố ý lớn hơn vài buffer 8192 bytes để vòng lặp đọc nhiều lần.
- **blobBytesRead=100003**: vòng lặp InputStream.read(...) đã nhận đủ bytes, không bị cắt đoạn.
- **blobSHA256=...**: kiểm chứng một checksum xác định của dữ liệu test. Mã dùng **HexFormat** và **MessageDigest** chuẩn Java 17.
- **blobInvalidAfterFree=true**: gọi Blob.length() sau free() ném SQLException như contract.
- **clobLength=29**: test SerialClob được tạo từ char[] dài 29 (có chữ Việt và emoji).
- **clobCharsRead=29**: vòng lặp Reader.read(...) đọc đủ characters theo biểu diễn được test dùng.
- **clobRoundTrip=true**: nội dung sau khi đọc khớp chính xác **String** nguồn, gồm dấu tiếng Việt và emoji.
- **clobInvalidAfterFree=true**: Clob.length() sau free() ném SQLException.

**Đừng suy từ ví dụ này rằng các driver DBMS luôn trả đúng một số char units cho cùng văn bản, hoặc rằng dùng SerialBlob là cách lưu nội dung file lớn.** Serial classes dùng RAM và không thể đại diện cho driver locators, network streaming, transaction validity hay database charset behavior.

### 6.5. Vì sao dùng buffer và checksum?

Với BLOB lớn, tạo **byte[] có kích thước vừa phải** (8192 bytes trong demo) để đọc lặp; chỉ đưa từng đoạn vào **MessageDigest**. Như vậy không cần tạo một mảng bằng toàn bộ file chỉ để kiểm tra checksum.

Trong ví dụ CLOB, **StringWriter** cố tình materialize **đoạn văn ngắn** để dễ so sánh sau đọc. **Không sao chép cách này cho CLOB nhiều GB**: hãy chuyển data vào Writer file hoặc pipeline xử lý streaming có quota.

### 6.6. Thực thi helper với database thật

Khi bạn có Connection và schema đúng, app có thể gọi:

~~~java
// Mảnh minh họa. Connection conn đã được mở bởi caller.
LobStreamDemo.insert(conn, 42L,
        Path.of("input.dat"), Path.of("article.txt"));

boolean found = LobStreamDemo.export(conn, 42L,
        Path.of("download.dat"), Path.of("article-out.txt"));
~~~

Đây là hướng dẫn sử dụng API, **không phải kết quả đã chạy**. Helper **không commit hoặc close Connection**, vì transaction ownership do caller quyết định. Nếu một row không tồn tại, export trả false; nếu một cột NULL, helper không xuất file tương ứng.

Trong sản phẩm thực tế, cần validate input files, output paths, quy tắc transactional commit/rollback và cleanup khi lỗi I/O/SQL.

## 7. Thứ tự đóng tài nguyên và free()

Một lỗi rất phổ biến là đọc xong nhưng chỉ đóng ResultSet/Connection, còn Blob/Clob locator không được free rõ ràng.

### 7.1. Đối với LOB từ getBlob/getClob

~~~text
Connection + transaction mở
   │
   ├── PreparedStatement mở
   │      └── ResultSet ở một row
   │             ├── Blob/Clob object được lấy ra
   │             │      └── stream được mở
   │             │           └── consume đầy đủ
   │             │      └── đóng stream
   │             └── gọi free() trên Blob/Clob
   │
   └── đóng ResultSet và Statement
   │
   └── commit/rollback/close Connection theo owner
~~~

**Không gọi free() trước khi đọc xong.** Nếu đang giữ InputStream/Reader phụ thuộc vào locator, giải phóng Blob/Clob quá sớm có thể làm stream không còn hợp lệ. Cũng không kéo locator ra khỏi transaction rồi gọi sau đó.

### 7.2. try-with-resources áp dụng trực tiếp cho stream

Trong Java 17:

~~~java
Blob blob = rs.getBlob("payload");
if (blob != null) {
    try {
        try (InputStream in = blob.getBinaryStream()) {
            in.transferTo(out);
        }
    } finally {
        blob.free();
    }
}
~~~

**InputStream** implement AutoCloseable, nên try-with-resources giải phóng stream cả khi đọc lỗi. **Blob** trong Java 17 cần free() riêng; khác với Java SE 26 nơi Blob/Clob cũng extends AutoCloseable.

### 7.3. Nếu free() cũng ném SQLException?

**free() có thể ném SQLException** khi driver gặp lỗi giải phóng tài nguyên. Một lệnh free() trong **finally** có thể che IOException/SQLException trước đó trong một số cấu trúc xử lý lỗi đơn giản.

Trong môi trường production quan trọng, cần giữ **primary exception** (thường là lỗi SQL/I/O đầu tiên) và ghi lỗi cleanup dưới dạng **suppressed exception** hoặc báo riêng. Với nhiều LOB, nếu free của Blob fail, không được bỏ qua free của Clob.

Một hướng tiếp cận là khai báo helper cleanup rõ ràng và quản lý failures ở scope mà app có quyền quyết định có phải invalidate pooled connection hay không. Ví dụ giáo dục ưu tiên cấu trúc nested finally đơn giản, còn production cần policy cleanup/observability đầy đủ.

### 7.4. free() không thay close() của stream

Đừng viết:

~~~java
// Ví dụ SAI nếu ứng dụng dựa vào việc free tự đóng mọi stream.
// Không sử dụng như một pattern chuẩn.
InputStream in = blob.getBinaryStream();
consume(in);
blob.free();
~~~

Hãy đóng **in** rõ ràng sau consume, rồi mới free Blob. **Cùng lúc đó**, close() của InputStream không thay thế **Blob.free()**; chúng là hai đối tượng tài nguyên khác nhau.

### 7.5. Không dùng đối tượng sau free

Theo contract, sau khi free, các method khác của Blob/Clob sẽ ném SQLException. Vì vậy:

- Không return Blob/Clob object ra ngoài helper đã free nó.
- Không cache một locator để truy cập sau khi Connection bị trả pool.
- Không giữ reference dùng về sau rồi giả định nó còn hợp lệ.
- Không gọi getBinaryStream/getCharacterStream sau khi free.
- Không coi free() xóa SQL row hoặc có tác dụng rollback.
- Gọi free lần thứ hai là no-op theo contract, nhưng không nên cố lạm dụng để che ownership lỏng lẻo.

## 8. Byte length, character length và Unicode

### 8.1. Blob.length() trả bytes

**Blob.length()** trả **long số bytes** của BLOB. Với file nhị phân, đây là đơn vị thường cần cho setBlob(InputStream,long) và kiểm tra checksum/transfer size.

**Files.size(path)** cũng trả số bytes của file trên filesystem, nên phù hợp với **setBlob(index, Files.newInputStream(path), size)** khi file không thay đổi trong quá trình bind/execute.

**Không dùng InputStream.available() làm tổng kích thước LOB**: available() ước tính số bytes có thể đọc mà không block, không phải tổng length của stream.

### 8.2. Clob.length() trả characters

**Clob.length()** trả long theo đơn vị characters trong CLOB. Với Java Reader, bạn đọc **characters**, không phải bytes của UTF-8. Trong ví dụ, Clob chứa chữ tiếng Việt và emoji; **SerialClob** dựa trên char[] nên length bằng số Java char code units trong test.

**Không giả định mọi khái niệm “một chữ nhìn thấy” tương ứng một character hay một byte**. Unicode có combining marks và supplementary code points; đo độ dài theo nghiệp vụ/DBMS phải hiểu encoding/character semantics của backend.

Nếu API **setClob(index, reader, length)** yêu cầu length, **Files.size(utf8TextFile)** là sai khi text có dấu tiếng Việt vì nó là số bytes. Cần đếm character units mà driver xác định, hoặc dùng overload **không length** khi driver hỗ trợ.

### 8.3. Vì sao getAsciiStream không phù hợp tiếng Việt?

**Clob.getAsciiStream()** đưa CLOB ra như ASCII stream. Với text Unicode có dấu, cách đó có thể không biểu diễn đúng các characters ngoài ASCII hoặc phụ thuộc conversion behavior.

**Dùng Clob.getCharacterStream()** để giữ Unicode ở tầng Java Reader. Khi ghi text ra file UTF-8, sử dụng **Files.newBufferedWriter(path, UTF_8)** để có encoding rõ.

Tương tự, không lấy BLOB chứa bytes rồi tự tạo **new String(bytes)** với charset mặc định của máy khi không có contract dữ liệu. Nếu BLOB thực chất chứa UTF-8 text và bạn muốn decode, hãy dùng charset được protocol định nghĩa, xử lý invalid byte sequences phù hợp, và cân nhắc liệu schema CLOB có đúng hơn không.

### 8.4. NClob và national character set

**NClob** extends Clob và dùng **Reader/Writer**. JDBC có **ResultSet.getNClob**, **PreparedStatement.setNClob** và **Connection.createNClob**.

Support **NCLOB/NCHAR/NVARCHAR** phụ thuộc DBMS, JDBC driver và schema. Nếu không hỗ trợ, driver có thể báo **SQLFeatureNotSupportedException**. Đừng chuyển toàn bộ text tiếng Việt sang NCLOB mặc định: cần dựa vào collation/charset capabilities và chuẩn dữ liệu của database.

## 9. Không materialize toàn bộ LOB nếu không cần

Các API khác của JDBC bao gồm:

| API | Kết quả | Rủi ro nếu LOB rất lớn |
| --- | --- | --- |
| **Blob.getBytes(pos, int length)** | byte[] | Materialize dữ liệu vào heap |
| **Clob.getSubString(pos, int length)** | String | Materialize dữ liệu vào heap |
| **ResultSet.getBytes(...)** | byte[] | Có thể cấp phát mảng lớn |
| **ResultSet.getString(...)** | String | Có thể cấp phát String lớn |
| **InputStream.readAllBytes()** | byte[] | Tăng memory theo kích thước dữ liệu |
| **Blob.getBinaryStream()** | InputStream | Caller có thể xử lý chunks |
| **Clob.getCharacterStream()** | Reader | Caller có thể xử lý chars theo chunks |

Với tệp 2GB, một **byte[]** không chỉ nguy hiểm vì memory footprint mà còn vì những giới hạn array index và JVM heap. API **Blob.length()** dùng **long** chính là để có thể biểu diễn kích thước vượt phạm vi int.

**Không cast length xuống int nếu không có kiểm tra giới hạn.** Với LOB thực sự lớn, thiết kế xử lý chunks hoặc lưu external object storage theo yêu cầu hệ thống; JDBC LOB streaming không phải lúc nào cũng là lựa chọn tối ưu cho mọi loại lưu trữ blob.

### 9.1. Buffer size và backpressure

Buffer 8 KiB hoặc 64 KiB chỉ là điểm khởi đầu để đo, không phải một chuẩn tối ưu cho mọi driver/network. Kích thước buffer quá bé tạo nhiều calls, quá lớn làm tăng memory/latency. Nếu có nhiều request chạy đồng thời, tổng memory của các buffers/driver internals phải được tính cùng số connections.

Một pipeline upload/download cần theo dõi bytes processed và có cơ chế cancellation/backpressure hoặc quota phù hợp. Khi downstream file write/người dùng disconnect, đừng tiếp tục hút dữ liệu vô hạn từ database nếu đã biết output không còn cần thiết.

### 9.2. Checksum và integrity

Với BLOB binary, **SHA-256** hoặc checksum khác có thể giúp phát hiện dữ liệu thay đổi trong lúc upload/download. Nhưng checksum cần được so sánh với nguồn tin cậy và được version hóa đúng, không chỉ in ra log.

Nếu dữ liệu từ file được dùng để tạo chữ ký hoặc hash, cần giữ **byte-for-byte**; không tự biến BLOB thành String rồi encode lại. Với CLOB, cần định nghĩa rõ encoding trước khi tính hash từ bytes nếu hash là contract giao thức.

## 10. Transaction, driver support và tính di động

### 10.1. Một LOB có thể tồn tại nhờ locator của transaction

Đọc Blob/Clob sau commit hoặc rollback có thể không được hỗ trợ. Nếu object hợp lệ chỉ trong transaction gốc, stream cũng phải được consume trong scope đó. Đừng thiết kế một API trả về **Blob** từ method đã đóng Connection.

Khi app cần trả nội dung cho HTTP client, thường phải copy stream trong khi connection còn được giữ, hoặc chủ động chuyển content sang nơi lưu trữ trung gian có lifecycle độc lập. Cân nhắc thời gian giữ database connection nếu download rất chậm.

### 10.2. Không phải mọi driver hỗ trợ cùng API overload

**SQLFeatureNotSupportedException** có thể xảy ra với phương thức streaming, partial reads, createBlob/createClob hoặc các method LOB khác nếu driver không hỗ trợ. Driver-specific limits cũng có thể phụ thuộc vào:

- DBMS version và kích thước tối đa BLOB/CLOB.
- Statement type, transaction mode hoặc auto-commit.
- Server-side LOB locator implementation.
- Cách driver streaming/buffering.
- Network packet size và batch execution.
- Binding có hoặc không length.
- Charset, national character set và text conversion.
- Resource cleanup khi statement/result set đóng.

**Không khẳng định một đoạn code đã compile với JDK thì chắc chắn chạy trên mọi JDBC driver**. Compiler xác nhận Java API signatures, không chứng minh backend hỗ trợ semantics/hiệu năng cụ thể.

### 10.3. Auto-commit và scope stream

Nhiều JDBC Connection mặc định có **autoCommit=true**. Tùy driver, LOB locator validity có thể gắn với transaction kết thúc khi statement hoàn tất/commit. Nếu cần xử lý một LOB lớn qua stream, hãy kiểm tra cách driver quản lý transaction và stream lifetime khi auto-commit bật.

Không vô điều kiện **setAutoCommit(false)** trong helper nếu Connection đang được caller/pool quản lý; transaction policy phải có owner rõ. Khi cần, thiết kế service có transaction scope bao toàn bộ read/write LOB rồi commit/rollback ở tầng điều phối.

### 10.4. File ghi ra ngoài không tự rollback cùng SQL

Nếu app đọc CLOB/BLOB từ DB và ghi ra file, **rollback database không tự xóa file** đã ghi. Nếu app upload file vào DB rồi có thêm side effects khác, cần xác định transaction boundaries và compensation logic để tránh file/DB bị lệch.

Khi xuất file cho người dùng, có thể ghi vào **temporary file** trong một thư mục được phép rồi atomic move sau khi stream hoàn tất và checksum xác nhận; điều này tùy filesystem và app policy. Không tự động ghi đè file đích khi chưa validate path/quota.

## 11. Một biến thể: setBlob(Blob) và setClob(Clob)

Ngoài stream overload, PreparedStatement hỗ trợ:

~~~java
// Mảnh minh họa, khi các biến ps/blob/clob tồn tại và còn hợp lệ.
ps.setBlob(2, blob);
ps.setClob(3, clob);
ps.executeUpdate();
~~~

Ưu điểm: caller có LOB object đã tạo hoặc lấy từ nơi khác. Rủi ro: nếu bạn **free() trước executeUpdate()**, driver có thể không còn đọc được giá trị. Ngược lại, nếu không bao giờ free, driver giữ tài nguyên quá lâu.

Không nhầm **setBlob(index, InputStream)** với **setBlob(index, Blob)**. Overload đầu nhận stream nguồn; overload sau nhận JDBC LOB object có lifecycle riêng.

### 11.1. Ghi vào đối tượng LOB đã tồn tại

Blob có **setBinaryStream(long pos)**, Clob có **setCharacterStream(long pos)**; có thể ghi từ vị trí 1-based, cập nhật nội dung và sau đó dùng LOB theo contract driver.

Tuy nhiên **việc sửa LOB thông qua locator có tự cập nhật cột DB, cần UPDATE riêng, hay chỉ tạo một giá trị tạm** phụ thuộc driver/DBMS. Đừng giả định mọi mutation của Blob/Clob object tự commit nội dung vào hàng đã SELECT. Hãy thử đúng database và chọn một chiến lược update rõ ràng.

### 11.2. Đọc partial stream khi cần

**getBinaryStream(pos,length)** hoặc **getCharacterStream(pos,length)** có thể tiết kiệm I/O nếu bạn chỉ cần một vùng. Nhưng position bắt đầu ở 1 và length có đơn vị khác nhau; kiểm tra bounds, driver support và transaction validity.

Không giả định một partial read luôn rẻ: driver có thể phải seek/scanning bên trong locator hoặc materialize một phần nhiều hơn. Benchmark với dữ liệu đại diện.

## 12. Xử lý lỗi và dọn tài nguyên trong production

### 12.1. Những loại lỗi thường thấy

| Triệu chứng | Nguyên nhân có thể | Hành động nên làm |
| --- | --- | --- |
| **SQLException** khi mở stream | LOB locator không hợp lệ/transaction kết thúc | Đọc trong đúng Connection/transaction scope |
| **SQLException** sau free() | Đối tượng đã bị giải phóng | Không dùng lại Blob/Clob, tạo/đọc lại theo scope mới |
| **SQLFeatureNotSupportedException** | Driver không hỗ trợ overload/method | Xem tài liệu driver, chọn API fallback có kiểm chứng |
| **IOException** giữa lúc copy | File/network bị lỗi, client disconnect | Đóng stream, free LOB, dọn file dở |
| **OutOfMemoryError** với getBytes/getSubString | Materialize LOB quá lớn | Chuyển sang chunk/stream processing |
| **Dữ liệu nhị phân bị thiếu** | Sai length hoặc đóng nguồn quá sớm | Giữ stream đến execute và xác minh số bytes |
| **Tiếng Việt sai dấu** | Lấy ASCII stream hoặc charset sai | Dùng Clob.getCharacterStream và Writer UTF-8 |
| **Kết quả khác sau commit** | Driver locator lifetime giới hạn bởi transaction | Truy cập trước transaction end, test theo driver |
| **Connection pool bị giữ lâu** | Download qua client rất chậm | Cân nhắc temp/object storage, timeout, quota |
| **Partial file còn trên disk** | Copy fail nhưng file đã mở/ghi một phần | Dọn temp output và có atomic publish policy |
| **free() ném khi cleanup** | Lỗi driver/server hoặc connection đã hỏng | Giữ primary failure và theo dõi cleanup error |
| **BLOB NULL gây NPE** | Không kiểm tra rs.getBlob(...) | Xử lý SQL NULL riêng |
| **CLOB length khác Files.size** | Bytes UTF-8 khác characters | Dùng đúng đơn vị và Reader |
| **Stream đọc được một lần** | Forward-only/non-resettable source | Không retry/rebind cùng source nếu đã tiêu thụ |
| **Chậm bất ngờ với streaming** | Driver vẫn buffer hoặc chuyển qua network nhiều lần | Benchmark driver/memory, kiểm soát batch/size |

### 12.2. Nguyên tắc xử lý cleanup failure

Nếu việc đọc stream đã ném IOException, và **blob.free()** cũng ném SQLException, code production nên giữ IOException làm primary error và ghi SQLException làm suppressed hoặc theo pipeline báo lỗi riêng. Với nhiều tài nguyên, phải cố gắng dọn tất cả thay vì dừng ở lỗi free đầu tiên.

try-with-resources tự quản lý suppressed exceptions cho những tài nguyên mà nó trực tiếp sở hữu (InputStream/Writer/ResultSet/Statement), nhưng **trong Java 17 Blob/Clob không phải AutoCloseable**, nên phương án **finally + free()** cần chính sách riêng nếu muốn giữ đúng exception causality.

### 12.3. Không dùng một LOB ở nhiều thread một cách tùy tiện

BLOB/CLOB locator có thể gắn với Connection/ResultSet và driver không đảm bảo thread-safe cho mọi thao tác. Đừng chia sẻ một Blob object/stream cho nhiều threads rồi cho một thread gọi free trong khi thread khác đang đọc.

Nếu muốn xử lý song song các phần, cần có contract concurrency/partial stream và resource ownership rõ ràng; đa số ứng dụng đơn giản nên stream tuần tự trong một scope.

## 13. Bảo mật và quyền truy cập

LOB thường chứa tài liệu, ảnh, hồ sơ hoặc nội dung có thể nhạy cảm. Những nguyên tắc quan trọng:

1. **Không log nội dung LOB** hoặc in cả byte[]/String ra stdout trong production.
2. Dùng **PreparedStatement parameters**, không ghép binary/text user input vào SQL string.
3. Kiểm tra **authorization** trước khi cho phép download/upload LOB theo id; client biết id không có nghĩa có quyền đọc.
4. Giới hạn upload/download size, MIME/type theo policy, và kiểm tra content khi nghiệp vụ yêu cầu; file extension không phải chứng cứ tin cậy.
5. Kiểm tra checksum và validation trên những tài liệu cần đảm bảo integrity.
6. Tránh arbitrary file paths; với export, chỉ cho phép ghi vào vùng đã được ứng dụng cấp quyền.
7. Đảm bảo temp files được cleanup kể cả khi lỗi; đặt permission và retention phù hợp.
8. Nếu LOB có PII/secrets, xử lý encryption/access control và lifetime dữ liệu theo quy định của sản phẩm.
9. Tránh vô tình biến BLOB chứa bytes đã được ký thành String rồi encode lại; có thể làm sai hash/signature.
10. Phân biệt **free() giải phóng JDBC object** với **xóa/xóa an toàn dữ liệu**: free không làm an toàn việc xóa bytes trong DB, file trên disk hoặc những bản sao trong heap.

**Bảo vệ nguồn tài nguyên:** Không thực hiện transferTo vô hạn vào một sink có thể hết quota mà không có giới hạn ở tầng ứng dụng. InputStream/Reader có thể được driver đọc theo yêu cầu; request cancellation phải đóng stream và thực hiện cleanup đúng policy.

## 14. Thiết kế integration test với JDBC driver thật

Một test tốt cần kiểm chứng cả **đúng dữ liệu** và **đúng lifecycle**:

| Test | Điều cần xác minh |
| --- | --- |
| BLOB nhỏ | Write rồi read, bytes khớp toàn bộ |
| BLOB lớn hơn nhiều buffers | Không mất byte, checksum/length đúng |
| CLOB tiếng Việt | Dấu tiếng Việt/emoji/Unicode giữ nguyên qua round-trip |
| CLOB length và UTF-8 size | Không nhầm char length với byte count |
| Cột SQL NULL | getBlob/getClob trả null, policy đúng |
| BLOB/CLOB rỗng | Khác với NULL, không lỗi khi stream 0 bytes/chars |
| setBlob/setClob không length | Driver hỗ trợ và dùng tài nguyên ra sao |
| setBlob/setClob có length | Khớp độ dài; sai length báo lỗi theo contract |
| Streaming memory | Dùng heap profiler/metrics trong tải thực; không phụ thuộc giả định |
| createBlob/createClob | Support, behavior temporary LOB và free đúng |
| Partial stream | Position 1-based, bounds, driver support |
| SQL transaction/autoCommit | Locator hợp lệ trong thời gian cần dùng |
| free() trước đọc xong | Xác minh lỗi và cleanup, không leak |
| Driver error giữa stream | Statement/ResultSet/stream/LOB được dọn |
| Connection pool reuse | Không giữ stream/locator qua borrow/return |
| Concurrency/load | Không giữ quá nhiều connections hoặc buffers |
| File output failure | Temp file dở được dọn, DB transaction policy đúng |

### 14.1. Dùng data tự tạo trong môi trường test

Tạo binary payload xác định, ví dụ chuỗi bytes từ một công thức hoặc random seed đã ghi lại. Với CLOB, thử các chuỗi:

~~~text
Xin chào Việt Nam
Đặng, ắ, ơ, ư, ộ
Emoji 😀 và dấu tổ hợp
Nhiều dòng
~~~

Đừng chỉ dùng ASCII text như "hello": nó không phát hiện lỗi chuyển encoding/national charset. Nếu không có driver server test, dùng SerialBlob/SerialClob chỉ kiểm chứng Java-level handling như demo, không thay thế driver integration.

### 14.2. Test với transaction và pool

Khi driver dùng locator theo transaction:

1. Mở connection và transaction theo cách được app quản lý.
2. INSERT BLOB/CLOB qua stream.
3. Query lại trong transaction hoặc transaction mới phù hợp schema.
4. Đọc trọn stream trước commit/close của transaction đang dùng locator.
5. free từng Blob/Clob trong finally.
6. Xác minh không còn active resources/connections bị giữ.
7. Lặp lại với lỗi giữa streaming, rollback hoặc cancellation.
8. Thử nhiều request song song để đo throughput, memory và pool utilization.

**Không nên chạy test kích thước rất lớn trực tiếp trên production database.** Dùng database thử nghiệm và áp quota cho artifact/test data.

## 15. Bài tập tự luyện

1. Trong LobStreamDemo, đổi BLOB size từ 100003 sang 1_000_003 bytes và xác minh blobBytesRead trùng blobLength; checksum sẽ đổi.
2. Thử một buffer size 1, 1024, 8192 và 65536 bytes; kết quả checksum phải giống nhau cho cùng binary input.
3. Thay StringWriter bằng Files.newBufferedWriter để xuất CLOB ra file UTF-8 mà không materialize full text trong heap; kiểm tra file bằng Reader.
4. Tạo SerialBlob rỗng và SerialClob rỗng, kiểm tra length=0 và cách đọc stream.
5. Đọc partial Blob.getBinaryStream(2,3) từ một Blob chứa ASCII bytes "ABCDE"; dự đoán "BCD" (vị trí bắt đầu ở 1).
6. Dùng Clob.getCharacterStream(1, length) để đọc một phần text; tránh nhầm offsets với UTF-8 bytes.
7. Viết helper **copyBlob(Blob, OutputStream)** có try-with-resources cho stream và finally free; xử lý null Blob.
8. Viết helper **copyClob(Clob, Writer)** tương tự; test tiếng Việt với dấu tổ hợp và emoji.
9. Dùng test JDBC driver thật và schema phù hợp để thử PreparedStatement.setBlob(InputStream,long), setClob(Reader) và so sánh round-trip.
10. Truyền length sai vào setBlob/setClob có length (trong môi trường test), kiểm tra exception driver trả khi execute.
11. So sánh cách dùng Blob.setBinaryStream(1) với PreparedStatement.setBlob(InputStream); đo xem driver có buffer hay tạo temporary LOB.
12. Viết transaction test để hiểu khi nào locator hết hạn sau commit/rollback/close.
13. Mô phỏng IOException sau khi đã ghi file dở; thiết kế cleanup và atomic publish policy.
14. Nâng toolchain sang Java SE 26 rồi thử Blob/Clob với try-with-resources trực tiếp; giải thích vì sao không compile với --release 17.
15. Thêm limit số bytes/chars tối đa mà ứng dụng chấp nhận, bảo đảm stream bị dừng và dọn khi vượt quota.

## 16. Checklist production

- [ ] Chọn đúng BLOB/CLOB/NCLOB theo dữ liệu, schema và database capability.
- [ ] Không dùng getBytes/getSubString/readAllBytes cho LOB lớn nếu không cần.
- [ ] Dùng InputStream cho bytes, Reader/Writer cho Unicode text.
- [ ] Dùng PreparedStatement parameter binding, không nối LOB vào SQL text.
- [ ] Với setBlob(InputStream,long), length đúng **bytes**.
- [ ] Với setClob(Reader,long), length đúng **characters**, không lấy Files.size UTF-8 thay thế.
- [ ] Giữ input stream/reader mở đến khi execute hoàn tất.
- [ ] Nếu dùng createBlob/createClob, quản lý temporary LOB và free().
- [ ] Đóng stream trong try-with-resources, rồi free Blob/Clob trước khi đóng transaction/connection.
- [ ] Không dùng Blob/Clob sau free; không return locator qua scope đã đóng.
- [ ] Đọc/truyền hoàn tất trước khi chuyển ResultSet row hoặc đóng cursor.
- [ ] Xử lý SQL NULL khác với LOB rỗng.
- [ ] Có policy cho lỗi free/close, giữ primary error, theo dõi cleanup failure.
- [ ] Có test trên driver/DBMS thật về support, locator lifetime và buffering.
- [ ] Kiểm thử Unicode tiếng Việt/emoji nếu lưu CLOB.
- [ ] Có giới hạn upload/download và kiểm tra checksum khi cần.
- [ ] Không ghi file ngoài path được phép hoặc để temp files chứa PII tồn tại mãi.
- [ ] Giữ đúng ownership giữa helper, transaction manager và connection pool.
- [ ] Không coi free() là DELETE hoặc xóa an toàn dữ liệu.
- [ ] Ghi nhớ trong Java 17 Blob/Clob cần free() rõ ràng; JDK mới có thể hỗ trợ AutoCloseable.
- [ ] Đo memory/latency với tải thực, không suy diễn rằng JDBC stream luôn có buffering nhỏ.

## Kết luận

**Đọc ghi LOB qua stream** giúp ứng dụng xử lý bytes/characters theo từng đoạn thay vì chủ động materialize toàn bộ trong bộ nhớ. Với **Blob**, đọc bằng InputStream và ghi bằng setBlob(InputStream) hoặc Blob.setBinaryStream; với **Clob**, đọc bằng Reader và ghi bằng setClob(Reader) hoặc Clob.setCharacterStream. **NClob** mở rộng cách làm text cho national character set nếu driver hỗ trợ.

**free() là bước quản lý vòng đời bắt buộc khi sử dụng đối tượng Blob/Clob**, tách biệt với việc đóng InputStream/Reader và với việc xóa SQL row. Sau free, object không còn hợp lệ. Trong Java 17, dùng **finally + free()**; trong API Java SE 26 còn có **AutoCloseable/close()**, nhưng free vẫn là cách tương thích và rõ ràng.

Cuối cùng, **JDBC streams không phải lời bảo đảm driver luôn streaming trực tiếp từ server**. Hãy đo trên DBMS/driver thật, giữ transaction/ResultSet/Connection hợp lệ khi đọc, kiểm soát bytes/chars/encoding, và thiết kế cleanup/limit/checksum cho từng luồng upload/download.

**Tài liệu tham khảo chính thức, hiện hành:**

- [Blob — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html)
- [Clob — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Clob.html)
- [Blob — Java SE 26 (free và AutoCloseable)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Blob.html)
- [Clob — Java SE 26 (free và AutoCloseable)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Clob.html)
- [NClob — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/NClob.html)
- [PreparedStatement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html)
- [ResultSet — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html)
- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html)
- [SerialBlob — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql.rowset/javax/sql/rowset/serial/SerialBlob.html)
- [SerialClob — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql.rowset/javax/sql/rowset/serial/SerialClob.html)