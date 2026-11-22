# Đọc ghi TEXT/BLOB hoặc JSON và giới hạn max_allowed_packet

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này hướng dẫn ứng dụng Java dùng MySQL Connector/J để lưu và đọc dữ liệu văn bản lớn, dữ liệu nhị phân và JSON; đồng thời xử lý giới hạn kích thước gói tin giữa JDBC client và MySQL server.

Khi xử lý nội dung lớn, cần chọn đúng kiểu cột và đúng API JDBC. Văn bản nên đi qua `String` hoặc `Reader`, dữ liệu nhị phân nên đi qua `byte[]` hoặc `InputStream`, còn JSON có thể được tuần tự hóa thành chuỗi rồi bind vào cột `JSON`. Với dữ liệu lớn, streaming giúp giảm áp lực bộ nhớ trong JVM. Tuy nhiên, streaming không loại bỏ giới hạn packet, chi phí transaction, binary log hoặc lưu trữ ở phía MySQL.

## 1. Phân biệt TEXT, BLOB và JSON

MySQL có các kiểu lưu văn bản và dữ liệu nhị phân với giới hạn dung lượng khác nhau:

| Kiểu | Dung lượng tối đa theo kiểu dữ liệu | Mục đích |
|---|---:|---|
| `TINYTEXT` / `TINYBLOB` | 255 byte | Văn bản hoặc dữ liệu nhị phân rất nhỏ. |
| `TEXT` / `BLOB` | 65.535 byte | Nội dung văn bản hoặc nhị phân cỡ nhỏ/trung bình. |
| `MEDIUMTEXT` / `MEDIUMBLOB` | 16.777.215 byte | Nội dung lớn hơn, ví dụ tài liệu hoặc ảnh. |
| `LONGTEXT` / `LONGBLOB` | 4.294.967.295 byte | Nội dung rất lớn, trong giới hạn thực tế của server, packet và tài nguyên. |
| `JSON` | Phụ thuộc giới hạn tài liệu, packet và tài nguyên MySQL | Dữ liệu có cấu trúc JSON cần kiểm tra hợp lệ và truy vấn theo path. |

Các giới hạn của TEXT/BLOB được tính theo byte. Với TEXT, số ký tự thực tế phụ thuộc charset: một ký tự UTF-8 có thể chiếm từ một đến bốn byte. Dùng `OCTET_LENGTH()` để đo số byte và `CHAR_LENGTH()` để đo số ký tự.

```sql
SELECT
    OCTET_LENGTH(description) AS bytes_used,
    CHAR_LENGTH(description) AS characters_used
FROM article
WHERE id = 1001;
```

`TEXT` lưu chuỗi theo character set và collation của cột. `BLOB` lưu byte thô, không có ngữ nghĩa charset/collation. Không dùng `BLOB` để lưu văn bản UTF-8 rồi chuyển đổi tùy tiện qua `String`; việc giải mã phải dùng đúng charset. Ngược lại, không dùng `TEXT` cho file nhị phân như ảnh, PDF hoặc archive.

### Khi nào dùng JSON?

MySQL có kiểu `JSON` native. Khi insert hoặc update, MySQL phân tích và từ chối tài liệu JSON không hợp lệ; giá trị được lưu ở định dạng nội bộ tối ưu cho việc truy cập thành phần. Nếu chỉ lưu một chuỗi JSON trong `TEXT`, MySQL không tự áp dụng các đặc tính xác thực và lưu trữ của kiểu JSON.

Ví dụ schema:

```sql
CREATE TABLE document_archive (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body MEDIUMTEXT,
    file_content LONGBLOB,
    metadata JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Trong ví dụ, `body` chứa văn bản dài, `file_content` chứa byte của file và `metadata` chứa thuộc tính có cấu trúc như loại tài liệu, nhãn hoặc thông tin nguồn. Không nên đặt toàn bộ file lớn vào JSON dạng Base64: cách đó làm tăng kích thước dữ liệu và tốn công mã hóa/giải mã. Với file rất lớn hoặc cần phân phối qua CDN/object storage, cân nhắc lưu file ở object storage và chỉ lưu object key, checksum, MIME type, kích thước cùng metadata trong MySQL.

## 2. Ánh xạ kiểu MySQL sang Java qua Connector/J

Connector/J hỗ trợ chuyển đổi nhiều kiểu MySQL sang các kiểu Java. Những ánh xạ thường dùng:

| Kiểu MySQL | Kiểu Java thường dùng | API JDBC nên chọn |
|---|---|---|
| `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | `String` hoặc `Reader` | `setString()`, `setCharacterStream()`, `getString()`, `getCharacterStream()` |
| `BLOB`, `MEDIUMBLOB`, `LONGBLOB` | `byte[]`, `InputStream`, `Blob` | `setBytes()`, `setBinaryStream()`, `setBlob()`, `getBinaryStream()`, `getBlob()` |
| `JSON` | `String` | `setString()`, `getString()` rồi parse bằng thư viện JSON của ứng dụng |

Với dữ liệu nhỏ, `String` và `byte[]` thuận tiện. Với dữ liệu lớn, tránh gọi `getBytes()` hoặc `getString()` nếu không cần giữ toàn bộ giá trị trong heap. Dùng stream để đọc hoặc ghi theo từng phần.

MySQL JSON được Connector/J ánh xạ thành `String` trong bảng chuyển đổi kiểu. JDBC không có kiểu chuẩn `java.sql.JSON`; ứng dụng thường dùng Jackson, Gson hoặc thư viện tương đương để chuyển giữa object Java và chuỗi JSON.

## 3. Ghi TEXT lớn bằng PreparedStatement

Với văn bản vừa phải, dùng `setString()`:

```java
String sql = "INSERT INTO article (title, body) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, title);
    ps.setString(2, bodyText);
    ps.executeUpdate();
}
```

Connector/J chuyển chuỗi Java Unicode sang character encoding của kết nối. Hãy xác minh charset/collation của database, bảng và cột, đặc biệt khi lưu tiếng Việt hoặc ký tự ngoài BMP. Trên MySQL hiện đại, `utf8mb4` là lựa chọn phổ biến để hỗ trợ đầy đủ Unicode.

Khi nội dung lớn, đọc từ file bằng `Reader` và bind bằng `setCharacterStream()`:

```java
String sql = "INSERT INTO article (title, body) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql);
     Reader bodyReader = Files.newBufferedReader(
         Path.of("article-body.txt"), StandardCharsets.UTF_8)) {

    ps.setString(1, "Hướng dẫn sử dụng");
    ps.setCharacterStream(2, bodyReader);
    ps.executeUpdate();
}
```

Giữ `Reader` mở cho đến khi `executeUpdate()` hoàn tất. Với overload có độ dài, độ dài truyền cho `setCharacterStream()` là số ký tự, không phải số byte. Không dùng `Files.size()` làm số ký tự vì UTF-8 có độ dài byte thay đổi theo ký tự.

Nếu cần điều khiển encoding riêng cho TEXT/CLOB, Connector/J có thuộc tính `clobCharacterEncoding`; nếu không, driver dùng encoding kết nối theo cấu hình. Cần kiểm thử dữ liệu có dấu và ký tự đặc biệt sau khi ghi rồi đọc lại để phát hiện lỗi chuyển mã.

## 4. Ghi BLOB lớn bằng InputStream

Với file nhị phân, dùng `setBinaryStream()` hoặc `setBlob()` để truyền dữ liệu theo stream. Ví dụ:

```java
String sql = "INSERT INTO document_archive (title, file_content) VALUES (?, ?)";
Path file = Path.of("manual.pdf");

try (PreparedStatement ps = connection.prepareStatement(sql);
     InputStream input = Files.newInputStream(file)) {

    ps.setString(1, "Manual PDF");
    ps.setBinaryStream(2, input, Files.size(file));
    ps.executeUpdate();
}
```

Overload nhận độ dài `long` cho phép truyền kích thước file lớn hơn giới hạn của `int`. Độ dài phải khớp với số byte thực tế mà stream cung cấp. Nếu độ dài không đúng, dữ liệu có thể bị cắt hoặc thao tác ghi thất bại. Giữ stream mở đến khi câu lệnh hoàn tất; sau đó đóng tài nguyên bằng try-with-resources.

Không chuyển file thành `byte[]` chỉ để gọi `setBytes()` khi file lớn. Cách đó thường tạo một bản sao lớn trong heap, có thể gây `OutOfMemoryError` khi nhiều request đồng thời tải file. Streaming giảm nhu cầu giữ toàn bộ payload ở phía ứng dụng, nhưng server vẫn phải nhận, xử lý và ghi toàn bộ dữ liệu.

### Đọc BLOB ra file

```java
String sql = "SELECT file_content FROM document_archive WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream input = rs.getBinaryStream("file_content");
                 OutputStream output = Files.newOutputStream(
                     Path.of("downloaded-manual.pdf"))) {
                input.transferTo(output); // Java 9+
            }
        }
    }
}
```

Đọc stream trước khi chuyển sang dòng kế tiếp hoặc đóng `ResultSet`/`Statement`. Nếu cần tương thích Java 8, thay `InputStream.transferTo()` bằng vòng lặp đọc buffer rồi ghi ra `OutputStream`.

### Đọc TEXT lớn bằng Reader

```java
String sql = "SELECT body FROM article WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, articleId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("body");
                 Writer writer = Files.newBufferedWriter(
                     Path.of("article-copy.txt"), StandardCharsets.UTF_8)) {
                char[] buffer = new char[8192];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                }
            }
        }
    }
}
```

## 5. Đọc nhiều dòng có BLOB lớn: streaming cột và streaming ResultSet

Hai việc thường bị nhầm lẫn:

- `getBinaryStream()` hoặc `getCharacterStream()` cung cấp cách đọc giá trị của một cột dưới dạng stream.
- Streaming ResultSet điều khiển cách driver lấy nhiều dòng từ server, tránh tải toàn bộ tập kết quả vào bộ nhớ trước khi ứng dụng xử lý.

Nếu truy vấn trả về hàng nghìn dòng, mỗi dòng có BLOB lớn, chỉ dùng `getBinaryStream()` chưa chắc đã giới hạn bộ nhớ cho toàn bộ ResultSet. Connector/J có `useCursorFetch` để dùng cursor-based fetching với server-side prepared statements. Bật `useCursorFetch=true` và đặt fetch size dương trên statement:

```java
String url = "jdbc:mysql://db.example.com:3306/shop?useCursorFetch=true";

try (Connection connection = DriverManager.getConnection(url, properties);
     PreparedStatement ps = connection.prepareStatement(
         "SELECT id, file_content FROM document_archive ORDER BY id")) {

    ps.setFetchSize(50);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            Path target = Path.of("export", id + ".bin");

            try (InputStream input = rs.getBinaryStream("file_content");
                 OutputStream output = Files.newOutputStream(target)) {
                input.transferTo(output);
            }
        }
    }
}
```

Khi `useCursorFetch=true`, Connector/J tự bật `useServerPrepStmts=true` vì cursor fetching cần server-side prepared statements. `setFetchSize(50)` là số dòng driver lấy mỗi lượt, không phải giới hạn kích thước BLOB. Chọn fetch size dựa trên kích thước dòng và bộ nhớ có thể dùng; nếu mỗi dòng có BLOB lớn, giảm fetch size.

Nếu ứng dụng chỉ đọc một bản ghi theo primary key, cursor fetch thường không cần thiết. Cần đo thử trên đúng phiên bản Connector/J và workload thực tế. Một stream vẫn tiêu thụ network, connection và thời gian; không giữ connection pool slot lâu hơn cần thiết.

## 6. Ghi và đọc JSON

MySQL kiểm tra JSON khi ghi vào cột `JSON`. Ứng dụng nên tuần tự hóa object Java bằng thư viện JSON thay vì tự nối chuỗi hoặc tự escape dấu nháy.

Ví dụ dùng Jackson:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(metadataObject);

String sql = "INSERT INTO document_archive (title, metadata) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "Báo cáo tháng");
    ps.setString(2, json);
    ps.executeUpdate();
}
```

Đọc JSON bằng `getString()` rồi chuyển thành object hoặc `JsonNode`:

```java
String sql = "SELECT metadata FROM document_archive WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String json = rs.getString("metadata");
            JsonNode metadata = mapper.readTree(json);
        }
    }
}
```

JSON sai định dạng sẽ bị MySQL từ chối với lỗi JSON tương ứng. Có thể kiểm tra kiểu và nội dung bằng SQL:

```sql
SELECT
    JSON_TYPE(metadata) AS root_type,
    JSON_STORAGE_SIZE(metadata) AS storage_bytes
FROM document_archive
WHERE id = 1001;
```

Truy vấn hoặc cập nhật một thuộc tính bằng hàm JSON:

```sql
UPDATE document_archive
SET metadata = JSON_SET(metadata, '$.status', ?)
WHERE id = ?;
```

Bind giá trị status bằng `PreparedStatement.setString()`. JSON path trong ví dụ là hằng số của câu SQL; nếu path do người dùng cung cấp, cần xác thực theo quy tắc ứng dụng và không ghép dữ liệu tùy ý vào SQL. Khi cần lọc thường xuyên theo một trường JSON, cân nhắc generated column và index thay vì quét toàn bộ tài liệu.

## 7. max_allowed_packet là gì?

`max_allowed_packet` giới hạn kích thước tối đa của một packet, một chuỗi trung gian được tạo trong MySQL hoặc tham số được gửi qua cơ chế truyền dữ liệu dài của prepared statement. Giá trị này ảnh hưởng đến truy vấn có chuỗi lớn, BLOB, JSON lớn và một số thao tác truyền dữ liệu khác.

Trong MySQL 8.4, giá trị mặc định của server là 64 MiB (`67.108.864` byte), giá trị nhỏ nhất là 1.024 byte và giá trị tối đa là 1 GiB (`1.073.741.824` byte). Phiên bản khác có thể có mặc định khác, vì vậy hãy đọc giá trị runtime thay vì giả định.

Kiểm tra cấu hình:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW SESSION VARIABLES LIKE 'max_allowed_packet';
```

`max_allowed_packet` có phạm vi GLOBAL và SESSION, có thể thay đổi động. Giá trị SESSION là chỉ đọc và được khởi tạo từ giá trị GLOBAL tại thời điểm kết nối. Khi thay đổi GLOBAL, các kết nối đang tồn tại không tự nhận session value mới; connection pool cần tạo lại physical connection để dùng giá trị mới. Server cũng không gửi cho client packet lớn hơn giá trị GLOBAL hiện tại.

Giới hạn của kiểu cột và giới hạn packet là hai khái niệm khác nhau. `LONGBLOB` có giới hạn lưu trữ theo kiểu dữ liệu rất lớn, nhưng điều đó không có nghĩa một request JDBC có thể gửi payload lớn tùy ý. Cần tính đến `max_allowed_packet`, giới hạn phía client, kích thước chunk, tài nguyên server và cách driver gửi dữ liệu.

## 8. Điều chỉnh max_allowed_packet ở server

Nếu workload hợp lệ cần packet lớn hơn cấu hình hiện tại, có thể tăng giá trị GLOBAL:

```sql
SET GLOBAL max_allowed_packet = 268435456;
```

Giá trị trên tương ứng 256 MiB. Cần quyền quản trị biến hệ thống phù hợp. Để lưu cấu hình qua lần restart, có thể dùng `SET PERSIST` trên phiên bản hỗ trợ:

```sql
SET PERSIST max_allowed_packet = 268435456;
```

Hoặc cấu hình trong option file:

```ini
[mysqld]
max_allowed_packet=256M
```

Giá trị nên là bội số của 1.024; MySQL làm tròn giá trị không chia hết xuống bội số gần nhất. Giới hạn giao thức là 1 GiB. Không đặt 1 GiB theo thói quen: packet buffer có thể tăng theo nhu cầu trên mỗi kết nối, nên giá trị quá lớn kết hợp nhiều kết nối đồng thời có thể làm tăng nguy cơ tiêu thụ bộ nhớ đáng kể.

Sau khi thay đổi, xác minh:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
```

Sau đó tạo kết nối JDBC mới và kiểm tra lại session value. Nếu dùng connection pool, recycle pool hoặc đảm bảo các physical connection cũ được thay thế theo quy trình an toàn.

## 9. Điều chỉnh giới hạn phía Connector/J

Connector/J có thuộc tính kết nối `maxAllowedPacket`. Nếu không cấu hình riêng, driver dùng giá trị `max_allowed_packet` của server để khởi tạo giới hạn gửi khi kết nối. Nếu đặt rõ, giá trị này không có tác dụng khi lớn hơn giới hạn server.

Ví dụ JDBC URL:

```text
jdbc:mysql://db.example.com:3306/shop?maxAllowedPacket=268435456&useServerPrepStmts=true
```

Có thể cấu hình bằng `Properties`:

```java
Properties properties = new Properties();
properties.setProperty("user", dbUser);
properties.setProperty("password", dbPassword);
properties.setProperty("maxAllowedPacket", "268435456");
properties.setProperty("useServerPrepStmts", "true");
```

Không đặt client lớn hơn server và cho rằng driver sẽ tự nâng giới hạn server. Hãy phối hợp giá trị server, client và cấu hình pool. Nếu `max_allowed_packet` ở server tăng nhưng pool giữ kết nối cũ, session cũ có thể vẫn dùng giới hạn trước đó.

### Các thuộc tính Connector/J liên quan đến stream

| Thuộc tính | Mặc định theo tài liệu Connector/J | Tác dụng |
|---|---:|---|
| `useServerPrepStmts` | `false` | Dùng server-side prepared statements nếu server hỗ trợ. |
| `useStreamLengthsInPrepStmts` | `true` | Tôn trọng độ dài được truyền vào các phương thức `set*Stream()`. |
| `blobSendChunkSize` | 1 MiB | Kích thước chunk khi gửi BLOB/CLOB bằng server-prepared statements; không được lớn hơn `maxAllowedPacket`, nếu vượt driver tự điều chỉnh. |
| `useCursorFetch` | `false` | Dùng cursor fetching khi bật và có fetch size dương; tự bật server-side prepared statements. |

Ví dụ cấu hình cho upload stream:

```text
jdbc:mysql://db.example.com:3306/shop?useServerPrepStmts=true&maxAllowedPacket=268435456&blobSendChunkSize=1048576
```

`blobSendChunkSize` là kích thước chunk gửi BLOB/CLOB qua server-prepared statements, không phải giới hạn tổng dung lượng của cột. Khi tái sử dụng server-prepared statement đã bind một stream lớn rồi chuyển tham số đó sang giá trị nhỏ hơn, hãy gọi `clearParameters()` và bind lại tất cả tham số trước lần execute tiếp theo để reset trạng thái long data của prepared statement.

## 10. Vì sao streaming không thay thế max_allowed_packet?

Streaming giúp ứng dụng không phải giữ toàn bộ nội dung trong một mảng byte hoặc chuỗi lớn. Connector/J có thể gửi BLOB/CLOB theo các chunk trong trường hợp server-side prepared statement. Tuy nhiên, mỗi packet/chunk vẫn phải tuân thủ giới hạn giao thức và cấu hình client/server. Một câu SQL quá dài, một tham số quá lớn hoặc một kết quả lớn vẫn có thể vượt giới hạn.

Ngoài packet, cần xem xét:

- **Heap JVM:** tránh tạo nhiều bản sao của cùng payload bằng `readAllBytes()`, `getBytes()` hoặc chuyển toàn bộ file sang Base64.
- **Số kết nối đồng thời:** nhiều request lớn có thể làm tăng bộ nhớ buffer, network và tài nguyên server.
- **Transaction:** ghi BLOB lớn kéo dài transaction, tăng redo/undo và có thể giữ khóa lâu hơn.
- **Binary log và replication:** transaction lớn tạo log lớn, tăng thời gian truyền và áp dụng ở replica.
- **Backup/restore:** dữ liệu lớn làm tăng dung lượng backup, thời gian restore và chi phí truyền giữa vùng.
- **Timeout mạng:** truyền file lâu có thể cần điều chỉnh timeout phù hợp, nhưng không dùng timeout lớn để che lỗi mạng hoặc server.

Với batch insert, tính tổng kích thước byte của từng batch thay vì chỉ giới hạn số dòng. Một batch 100 dòng metadata nhỏ khác hoàn toàn 100 dòng chứa BLOB vài MiB. Thu nhỏ batch hoặc chia lô khi cần; tránh bật `rewriteBatchedStatements` mà không đo kích thước câu lệnh được rewrite và tác động lên packet.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Packet for query is too large` / lỗi `ER_NET_PACKET_TOO_LARGE` | Packet hoặc tham số vượt `max_allowed_packet` phía server. | Kiểm tra GLOBAL và SESSION value; tăng hợp lý nếu payload hợp lệ; tạo lại kết nối. |
| `Communications link failure` hoặc mất kết nối khi upload | Server đóng kết nối sau packet quá lớn, timeout mạng hoặc stream bị lỗi. | Kiểm tra error log server, kích thước payload, timeout và trạng thái stream; không chỉ tăng timeout. |
| Connector/J báo packet lớn dù server đã tăng | Client `maxAllowedPacket` thấp hoặc physical connection vẫn giữ session value cũ. | Kiểm tra thuộc tính Connector/J, mở kết nối mới và recycle pool. |
| File lưu vào BLOB bị hỏng | Dùng API ký tự cho dữ liệu nhị phân, chuyển qua String, sai độ dài stream hoặc encoding gây biến đổi byte. | Dùng `setBinaryStream()` với byte length chính xác; so sánh checksum trước/sau. |
| TEXT có dấu bị lỗi | Charset/collation hoặc `clobCharacterEncoding` không phù hợp. | Kiểm tra charset kết nối, cột và encoding stream; thử dữ liệu UTF-8 có dấu. |
| JSON insert báo lỗi cú pháp | Chuỗi JSON không hợp lệ hoặc serialize thủ công sai escaping. | Dùng thư viện JSON để serialize; lưu chuỗi qua `setString()` và kiểm tra lỗi server trả về. |
| JVM tăng heap mạnh khi export | Dùng `getBytes()`/`getString()` hoặc tải toàn bộ ResultSet trước khi xử lý. | Dùng stream cho cột lớn; bật cursor fetch và fetch size dương khi đọc nhiều dòng. |
| Prepared statement chạy lại với stream cũ bị lỗi | Stream đã bị đọc/đóng sau execute hoặc trạng thái long data chưa reset. | Mở stream mới; khi đổi tham số lớn sang nhỏ với server-prepared statement, gọi `clearParameters()` và bind lại toàn bộ tham số. |

Nếu server báo packet quá lớn, kết nối có thể bị đóng. Ứng dụng có thể nhận exception giao tiếp thay vì chỉ nhận một lỗi SQL đơn giản. Hãy kiểm tra error log MySQL cùng exception chain của JDBC để xác định nguyên nhân. Không retry mù một payload vượt giới hạn vì retry không làm thay đổi kích thước packet.

## 12. Bài tập thực hành

Tạo một bảng lưu tài liệu gồm văn bản, file nhị phân và metadata JSON. Dùng ứng dụng Java và MySQL Connector/J để thực hiện:

1. Tạo bảng `document_archive` với `MEDIUMTEXT`, `LONGBLOB` và `JSON`.
2. Đọc một file UTF-8 bằng `Reader`, ghi nội dung vào cột TEXT bằng `setCharacterStream()`.
3. Đọc một file PDF bằng `InputStream`, ghi vào BLOB bằng `setBinaryStream()` và truyền đúng độ dài byte.
4. Serialize một object Java thành JSON bằng Jackson, ghi bằng `setString()` rồi đọc lại bằng `getString()` và parse thành `JsonNode`.
5. Đọc BLOB ra file bằng `getBinaryStream()`; so sánh SHA-256 của file gốc và file đã tải về.
6. Đọc nhiều dòng có BLOB với `useCursorFetch=true` và `setFetchSize(10)`; quan sát heap và thời gian xử lý.
7. Kiểm tra `max_allowed_packet` ở GLOBAL và SESSION; thử upload một payload lớn hơn giới hạn hiện tại trong môi trường thử nghiệm để quan sát lỗi.
8. Tăng giới hạn server lên một giá trị hợp lý, điều chỉnh `maxAllowedPacket` nếu cần, tạo kết nối mới và xác nhận upload thành công.
9. Chạy thử với nhiều kích thước batch khác nhau, ghi nhận packet size, thời gian, heap JVM và độ trễ replica nếu có.
10. Viết kết luận nêu rõ khi nào dùng TEXT, BLOB hoặc JSON; khi nào cần streaming; và cách xác định giới hạn packet thực tế của hệ thống.

Sau bài tập, người học cần giải thích được vì sao BLOB phải dùng API nhị phân, vì sao JSON được bind như chuỗi qua JDBC, vì sao giới hạn cột không đồng nghĩa giới hạn packet, và vì sao thay đổi GLOBAL `max_allowed_packet` cần tạo lại physical connection để session nhận giá trị mới. Đây là nền tảng để xử lý dữ liệu lớn qua Connector/J mà vẫn kiểm soát bộ nhớ, độ tin cậy và hiệu năng.

## Tài liệu tham khảo chính thức

- [MySQL Connector/J: Java, JDBC, and MySQL Types](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-type-conversions.html)
- [MySQL Connector/J: BLOB/CLOB Processing Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-blob-clob-processing.html)
- [MySQL Connector/J: Networking Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html)
- [MySQL Connector/J: Prepared Statement Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-prepared-statements.html)
- [MySQL Connector/J: Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL 8.4 Reference Manual: max_allowed_packet](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual: JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
