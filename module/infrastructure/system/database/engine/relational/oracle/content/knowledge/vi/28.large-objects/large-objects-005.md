# Streaming dữ liệu lớn thay vì tải toàn bộ vào bộ nhớ ứng dụng

Khi một ứng dụng đọc hoặc ghi file, ảnh, video, tài liệu, JSON lớn hay dữ liệu văn bản dài trong Oracle Database, việc tải toàn bộ nội dung vào một biến hoặc mảng byte có thể làm bộ nhớ tăng theo kích thước dữ liệu. Nếu nhiều request chạy đồng thời, ứng dụng có thể thiếu heap, tăng garbage collection, chậm hoặc hết bộ nhớ.

Streaming xử lý dữ liệu theo từng phần nhỏ có kích thước giới hạn. Ứng dụng đọc một chunk từ nguồn, chuyển chunk đó tới đích, rồi tiếp tục cho tới khi hết dữ liệu. Bộ nhớ dùng cho nội dung thường tỷ lệ với kích thước buffer thay vì kích thước toàn bộ LOB.

Trong Oracle, các kiểu dữ liệu lớn thường gặp là:

- BLOB: dữ liệu nhị phân như ảnh, PDF, file nén và nội dung media.
- CLOB: dữ liệu ký tự lớn theo database character set.
- NCLOB: dữ liệu ký tự lớn theo national character set.
- BFILE: locator tới file nhị phân bên ngoài database, được Oracle đọc theo quyền directory object và chỉ đọc qua cơ chế LOB.

Để streaming hiệu quả, cần phối hợp cả ba tầng: cách Oracle lưu LOB, cách driver cung cấp LOB locator/stream và cách ứng dụng chuyển dữ liệu theo chunk. Chỉ thay một mảng byte lớn bằng một chuỗi lớn vẫn là tải toàn bộ dữ liệu vào bộ nhớ.

## 1. Vì sao không nên tải toàn bộ LOB vào bộ nhớ?

Giả sử một ứng dụng tải một file BLOB 500 MB. Nếu code gọi API trả về toàn bộ nội dung thành byte array, heap cần giữ ít nhất khoảng 500 MB cho mảng đó, chưa kể object, buffer trung gian, bản sao khi xử lý và bộ nhớ của các request khác.

Nếu có 20 request đồng thời, chỉ riêng nội dung đã có thể cần khoảng 10 GB nếu mỗi request giữ toàn bộ 500 MB.

Với streaming, mỗi request có thể chỉ cần một buffer 64 KB hoặc 256 KB:

| Cách xử lý | Bộ nhớ cho nội dung một request |
|---|---:|
| Đọc toàn bộ file 500 MB vào byte array | Xấp xỉ 500 MB hoặc hơn |
| Streaming với buffer 64 KB | Xấp xỉ 64 KB cộng overhead |
| Streaming với buffer 256 KB | Xấp xỉ 256 KB cộng overhead |

Đây là ước lượng khái niệm. Driver, framework, compression, TLS và các buffer khác cũng sử dụng bộ nhớ. Tuy vậy, streaming giúp giới hạn bộ nhớ theo cấu hình thay vì theo kích thước file.

### 1.1 Công thức bộ nhớ khi có nhiều request

Nếu mỗi request dùng buffer B và có N request đang stream, bộ nhớ buffer xấp xỉ:

~~~text
Memory for buffers ≈ N × B
~~~

Ví dụ 100 request × 64 KB ≈ 6,4 MB cho buffer ứng dụng. Con số thực tế sẽ cao hơn vì mỗi stream còn có object, driver buffer, connection, TLS và framework.

Nếu mỗi request giữ nguyên file 500 MB, 100 request có thể cần khoảng 50 GB chỉ cho nội dung.

### 1.2 Streaming không có nghĩa dữ liệu không được buffer

Streaming vẫn cần buffer ở nhiều tầng:

- Buffer trong ứng dụng.
- Buffer của JDBC driver.
- Buffer network/socket.
- Buffer của Oracle và hệ điều hành.
- Buffer của HTTP server hoặc client.

Mục tiêu là kiểm soát dung lượng buffer và tránh materialize toàn bộ nội dung. Không cần loại bỏ mọi buffering; cần tránh bộ nhớ tăng không giới hạn theo kích thước dữ liệu.

## 2. Hiểu LOB locator trước khi đọc dữ liệu

Một LOB column không đơn giản là một giá trị VARCHAR2 dài. Oracle quản lý LOB bằng locator và vùng lưu trữ LOB tương ứng.

LOB locator là một tham chiếu cho phép chương trình truy cập nội dung LOB. Khi query một cột BLOB/CLOB, driver có thể trả về locator hoặc một đối tượng đại diện cho LOB; nội dung có thể được đọc dần qua stream.

Ví dụ bảng lưu tài liệu:

~~~sql
CREATE TABLE documents (
    document_id   NUMBER PRIMARY KEY,
    file_name     VARCHAR2(255 CHAR) NOT NULL,
    content_type  VARCHAR2(100 CHAR),
    payload       BLOB,
    text_content  CLOB,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);
~~~

Trong ứng dụng:

- Lấy BLOB/CLOB object không đồng nghĩa phải lấy toàn bộ nội dung vào byte array/String.
- Dùng getBinaryStream hoặc getCharacterStream để đọc nội dung theo luồng.
- Giữ connection, statement và result set còn mở trong lúc stream đang được tiêu thụ.
- Không giữ locator hoặc stream lâu hơn vòng đời connection/transaction mà driver yêu cầu.

### 2.1 Locator khác nội dung

| Đối tượng | Vai trò |
|---|---|
| BLOB/CLOB column | Lưu nội dung LOB trong database |
| LOB locator | Tham chiếu tới LOB để đọc/ghi |
| InputStream | Đọc dữ liệu nhị phân từng phần |
| Reader | Đọc dữ liệu ký tự từng phần |
| OutputStream | Ghi dữ liệu nhị phân từng phần |
| Writer | Ghi dữ liệu ký tự từng phần |

Không nên giả định rằng gọi getBlob hoặc getClob luôn materialize toàn bộ LOB. Thường đối tượng trả về là locator. Điều cần tránh là gọi các API như getBytes cho toàn bộ BLOB hoặc getSubString cho toàn bộ CLOB rồi giữ kết quả lớn trong heap.

## 3. Chọn đúng kiểu LOB

### 3.1 BLOB

BLOB dùng cho nội dung nhị phân:

- Ảnh.
- PDF.
- Video/audio.
- File ZIP.
- File Office.
- Payload nhị phân.

BLOB không diễn giải encoding ký tự. Ứng dụng phải tự biết định dạng file và content type.

### 3.2 CLOB

CLOB dùng cho văn bản lớn theo database character set:

- Nội dung bài viết.
- Tài liệu text.
- XML/JSON dạng văn bản.
- Nội dung HTML.
- Văn bản nhiều ngôn ngữ.

CLOB lưu ký tự, không phải byte thô của file. Khi đọc/ghi qua JDBC, dùng Reader/Writer để driver xử lý chuyển đổi character set.

### 3.3 NCLOB

NCLOB dùng national character set. Chỉ chọn khi schema và yêu cầu character set thực sự cần kiểu này. Trong nhiều hệ thống dùng AL32UTF8 làm database character set, CLOB đã hỗ trợ Unicode đầy đủ.

### 3.4 BFILE

BFILE là locator tới file nhị phân ở hệ thống file phía database server thông qua DIRECTORY object. Oracle có thể đọc file BFILE nhưng không ghi nội dung vào file đó qua BFILE locator.

BFILE khác BLOB:

- BLOB được lưu trong database.
- BFILE trỏ tới file bên ngoài database.
- BFILE cần DIRECTORY object và quyền tương ứng.
- File BFILE có thể thay đổi ngoài database, nên nội dung không được quản lý transaction giống BLOB.

### 3.5 Không dùng VARCHAR2 để lưu file lớn

VARCHAR2 trong PL/SQL và SQL có giới hạn độ dài riêng; nó không thay thế BLOB/CLOB cho nội dung lớn. Dùng LOB khi dữ liệu vượt miền phù hợp của kiểu chuỗi thông thường hoặc cần thao tác stream.

## 4. Mẫu chống streaming: materialize toàn bộ dữ liệu

Với JDBC, cách dễ viết nhưng không phù hợp cho LOB rất lớn:

~~~java
Blob blob = resultSet.getBlob("payload");
long length = blob.length();
byte[] bytes = blob.getBytes(1, (int) length);
~~~

getBytes trả về byte array. Toàn bộ phần dữ liệu được yêu cầu phải nằm trong bộ nhớ ứng dụng. Ép length sang int còn có nguy cơ tràn với dữ liệu lớn hơn giới hạn int.

Với CLOB:

~~~java
Clob clob = resultSet.getClob("text_content");
long length = clob.length();
String text = clob.getSubString(1, (int) length);
~~~

getSubString trả về String lớn. Đây vẫn là materialization toàn bộ nội dung.

Các API sau thường tạo dữ liệu trong bộ nhớ:

- Blob.getBytes(pos, length).
- Clob.getSubString(pos, length).
- InputStream.readAllBytes().
- Files.readAllBytes().
- Reader đọc toàn bộ vào StringBuilder/String.
- Chuyển BLOB thành Base64 String toàn bộ.

Các API streaming:

- ResultSet.getBinaryStream().
- ResultSet.getCharacterStream().
- Blob.getBinaryStream().
- Clob.getCharacterStream().
- PreparedStatement.setBinaryStream().
- PreparedStatement.setCharacterStream().
- Blob.setBinaryStream().
- Clob.setCharacterStream() nếu driver hỗ trợ.

## 5. Đọc BLOB bằng JDBC InputStream

Ví dụ tải BLOB từ Oracle xuống file mà không tạo byte array toàn bộ:

~~~java
String sql = """
    SELECT payload
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        try (InputStream input = resultSet.getBinaryStream("payload");
             OutputStream output = Files.newOutputStream(destination)) {

            byte[] buffer = new byte[64 * 1024];
            int count;

            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        }
    }
}
~~~

Luồng xử lý:

1. Query chỉ lấy hàng cần thiết.
2. Lấy InputStream từ cột BLOB.
3. Đọc tối đa 64 KB mỗi lượt.
4. Ghi chunk vào file đích.
5. Lặp tới EOF.
6. Đóng stream, ResultSet, Statement và Connection theo thứ tự vòng đời.

Kích thước 64 KB là ví dụ, không phải giá trị tối ưu cho mọi ứng dụng. Có thể thử 32 KB, 64 KB, 128 KB hoặc 256 KB bằng benchmark.

### 5.1 Giữ ResultSet và Connection mở trong lúc stream

Không nên làm như sau:

~~~java
InputStream input;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {

    resultSet.next();
    input = resultSet.getBinaryStream(1);
}

// Không nên tiếp tục đọc ở đây:
// ResultSet/Statement/Connection đã đóng.
~~~

Stream/LOB locator có thể phụ thuộc vào connection và ResultSet. Hãy đọc xong trước khi đóng các resource sở hữu nó, trừ khi driver/framework có cơ chế materialize hoặc detach được tài liệu hóa rõ.

### 5.2 Kiểm tra NULL LOB

Nếu cột BLOB là NULL, getBinaryStream có thể trả NULL. Phải xử lý trường hợp đó:

~~~java
InputStream input = resultSet.getBinaryStream("payload");
if (input == null) {
    throw new IllegalStateException("Document has no payload");
}
~~~

Phân biệt:

- Không có hàng: resultSet.next() trả false.
- Có hàng nhưng LOB NULL: stream có thể là null.
- Có hàng và LOB rỗng: LOB tồn tại nhưng length bằng 0.

Ba trạng thái này có ý nghĩa nghiệp vụ khác nhau.

## 6. Đọc CLOB bằng JDBC Reader

CLOB là dữ liệu ký tự, nên dùng Reader thay vì InputStream khi ứng dụng cần nội dung text:

~~~java
String sql = """
    SELECT text_content
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        try (Reader reader = resultSet.getCharacterStream("text_content");
             Writer writer = Files.newBufferedWriter(
                 destination,
                 StandardCharsets.UTF_8
             )) {

            char[] buffer = new char[8 * 1024];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }
    }
}
~~~

Reader trả dữ liệu ký tự. Writer ghi ra file UTF-8 trong ví dụ. Oracle JDBC thực hiện chuyển đổi character set từ CLOB sang Java character stream; không tự chuyển CLOB thành byte array.

### 6.1 Không nhầm byte length với character length

Đối với BLOB:

- Độ dài thường được tính bằng byte.
- InputStream/OutputStream truyền byte.

Đối với CLOB:

- Độ dài LOB và offset trong API LOB được tính theo đơn vị ký tự theo quy tắc CLOB.
- Reader/Writer truyền ký tự.
- Số byte của file UTF-8 sau khi encode có thể khác số ký tự.

Không dùng độ dài byte của file UTF-8 làm số ký tự khi gọi API CLOB. Ngược lại, không dùng số ký tự làm độ dài byte của BLOB.

### 6.2 Unicode và surrogate pairs

Java String/Reader làm việc với UTF-16 code units; một số Unicode code point nằm ngoài Basic Multilingual Plane được biểu diễn bằng cặp surrogate. Reader xử lý luồng ký tự và JDBC thực hiện chuyển đổi encoding. Tránh tự cắt chuỗi theo byte hoặc cắt một cặp surrogate ở giữa chunk.

Khi tự xử lý ký tự, dùng Reader/Writer và để chúng quản lý biên buffer. Khi chuyển đổi sang byte, chỉ dùng charset đã xác định, ví dụ UTF-8.

## 7. Upload BLOB bằng PreparedStatement.setBinaryStream

Nếu ứng dụng nhận file từ client hoặc filesystem, có thể bind InputStream trực tiếp vào BLOB:

~~~java
String sql = """
    INSERT INTO documents (
        document_id,
        file_name,
        content_type,
        payload
    )
    VALUES (?, ?, ?, ?)
    """;

long fileSize = Files.size(source);

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (InputStream input = Files.newInputStream(source);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, fileName);
        statement.setString(3, contentType);
        statement.setBinaryStream(4, input, fileSize);

        statement.executeUpdate();
        connection.commit();
    } catch (SQLException | IOException error) {
        connection.rollback();
        throw error;
    }
}
~~~

setBinaryStream truyền luồng byte cho JDBC driver. Overload nhận length dùng kiểu long trong JDBC hiện đại. Kiểm tra phiên bản JDBC driver và API được hỗ trợ trong ứng dụng mục tiêu; một số môi trường cũ chỉ có overload nhận int hoặc yêu cầu length.

### 7.1 Upload khi không biết trước độ dài

JDBC hiện đại có overload không yêu cầu khai báo length:

~~~java
statement.setBinaryStream(4, input);
~~~

Driver sẽ đọc stream cho tới EOF theo hợp đồng JDBC. Hãy kiểm tra hỗ trợ của driver đang dùng và giới hạn upload ở tầng ứng dụng. Không nên tin rằng một request có thể gửi lượng dữ liệu không giới hạn.

### 7.2 Dùng stream từ HTTP request

Trong ứng dụng web, có thể lấy InputStream từ multipart upload và bind trực tiếp vào PreparedStatement. Tránh gọi API lấy toàn bộ multipart thành byte array trước khi lưu.

Luồng:

~~~text
HTTP request body
       |
       v
Multipart InputStream
       |
       v
JDBC setBinaryStream
       |
       v
Oracle BLOB
~~~

Giới hạn kích thước upload, kiểm tra quyền, loại nội dung, checksum và thời gian xử lý. Đọc stream trực tiếp không thay thế kiểm tra an toàn file.

## 8. Upload CLOB bằng Reader

Nếu nguồn là file text UTF-8, mở Reader với charset tường minh:

~~~java
String sql = """
    INSERT INTO documents (
        document_id,
        file_name,
        text_content
    )
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (Reader reader = Files.newBufferedReader(
             source,
             StandardCharsets.UTF_8
         );
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, documentId);
        statement.setString(2, fileName);
        statement.setCharacterStream(3, reader);

        statement.executeUpdate();
        connection.commit();
    } catch (SQLException | IOException error) {
        connection.rollback();
        throw error;
    }
}
~~~

setCharacterStream truyền ký tự cho CLOB. Driver chuyển đổi từ Java character data sang character set của database.

### 8.1 Không dùng setString cho văn bản rất lớn

setString nhận một String đã nằm trong heap. Nếu ứng dụng đã đọc toàn bộ file vào String, streaming đã bị mất trước khi gọi JDBC.

Với CLOB lớn, hãy tạo Reader từ nguồn và dùng setCharacterStream. Với dữ liệu nhỏ, setString có thể đơn giản và phù hợp hơn; chọn theo kích thước và giới hạn thực tế.

## 9. Upload bằng LOB locator và SELECT FOR UPDATE

Một cách khác là tạo hàng với EMPTY_BLOB/EMPTY_CLOB, lấy locator rồi ghi stream vào locator.

SQL tạo hàng:

~~~sql
INSERT INTO documents (
    document_id,
    file_name,
    payload
)
VALUES (
    :document_id,
    :file_name,
    EMPTY_BLOB()
);
~~~

Sau đó query locator để update:

~~~sql
SELECT payload
FROM documents
WHERE document_id = :document_id
FOR UPDATE;
~~~

Trong JDBC, lấy Blob rồi dùng setBinaryStream trên locator:

~~~java
connection.setAutoCommit(false);

try (PreparedStatement statement = connection.prepareStatement(
         "SELECT payload FROM documents WHERE document_id = ? FOR UPDATE"
     )) {
    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new IllegalArgumentException("Document not found");
        }

        Blob blob = resultSet.getBlob(1);
        try (InputStream input = Files.newInputStream(source);
             OutputStream output = blob.setBinaryStream(1)) {

            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        } finally {
            blob.free();
        }
    }
}

connection.commit();
~~~

Đây là mẫu minh họa locator-based write. Hãy xác nhận hỗ trợ của Oracle JDBC driver cho Blob.setBinaryStream và cách quản lý locator trên phiên bản đang dùng. Row phải được khóa FOR UPDATE trong lúc cập nhật LOB; transaction phải còn mở cho tới khi ghi xong và commit.

Với nhiều ứng dụng, bind stream trực tiếp bằng setBinaryStream trong INSERT/UPDATE đơn giản hơn. Locator-based write hữu ích khi cần thao tác LOB đã tồn tại hoặc dùng API LOB object.

## 10. Ghi LOB trong PL/SQL theo từng chunk

Trong PL/SQL, có thể dùng DBMS_LOB.READ để đọc một phần LOB và DBMS_LOB.WRITE/WRITEAPPEND để ghi từng phần.

### 10.1 Đọc BLOB bằng DBMS_LOB.READ

~~~sql
DECLARE
    l_blob    BLOB;
    l_length  INTEGER;
    l_offset  INTEGER := 1;
    l_amount  INTEGER;
    l_buffer  RAW(32767);
BEGIN
    SELECT payload
    INTO l_blob
    FROM documents
    WHERE document_id = 1001;

    l_length := DBMS_LOB.GETLENGTH(l_blob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_blob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Xử lý chunk trong l_buffer tại đây.
        -- l_amount là số byte thực tế được đọc.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

Đặc điểm:

- BLOB offset tính theo byte và bắt đầu từ 1.
- BLOB amount tính theo byte.
- RAW trong PL/SQL có giới hạn tối đa 32.767 byte.
- Không tăng offset theo kích thước buffer cố định nếu lần đọc cuối chỉ đọc ít byte; dùng amount thực tế.

### 10.2 Đọc CLOB bằng DBMS_LOB.READ

~~~sql
DECLARE
    l_clob    CLOB;
    l_length  INTEGER;
    l_offset  INTEGER := 1;
    l_amount  INTEGER;
    l_buffer  VARCHAR2(8000);
BEGIN
    SELECT text_content
    INTO l_clob
    FROM documents
    WHERE document_id = 1001;

    l_length := DBMS_LOB.GETLENGTH(l_clob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(8000, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_clob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Xử lý chunk ký tự trong l_buffer tại đây.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

Với CLOB:

- Offset và amount được tính theo ký tự.
- Buffer là VARCHAR2.
- Kích thước buffer tính theo byte và chịu giới hạn PL/SQL; chọn amount đủ nhỏ cho character set nhiều byte.
- DBMS_LOB.READ có thể điều chỉnh amount thành số ký tự thực tế đọc.

Giá trị 8.000 trong ví dụ là mức chunk thận trọng cho buffer VARCHAR2; cần xét character set và nội dung thực tế.

### 10.3 DBMS_LOB.SUBSTR không phải cách tải toàn bộ LOB

DBMS_LOB.SUBSTR trả về một phần LOB với giới hạn kích thước buffer của kiểu trả về. Nó hữu ích cho đoạn text nhỏ hoặc hiển thị preview, không phù hợp để lấy toàn bộ LOB lớn vào một VARCHAR2/RAW.

Nếu cần xử lý toàn bộ dữ liệu, dùng vòng lặp chunk với DBMS_LOB.READ hoặc stream qua driver.

## 11. Ghi BLOB theo chunk trong PL/SQL

Có thể khởi tạo BLOB rỗng rồi ghi từng phần:

~~~sql
DECLARE
    l_blob    BLOB;
    l_chunk   RAW(32767);
    l_amount  PLS_INTEGER;
BEGIN
    INSERT INTO documents(document_id, file_name, payload)
    VALUES (2001, 'sample.bin', EMPTY_BLOB())
    RETURNING payload INTO l_blob;

    -- Ví dụ chunk dữ liệu nhị phân.
    l_chunk := HEXTORAW('010203040506');
    l_amount := UTL_RAW.LENGTH(l_chunk);

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => l_amount,
        buffer  => l_chunk
    );

    -- Ghi các chunk tiếp theo bằng cùng cách.
    COMMIT;
END;
/
~~~

WRITEAPPEND thêm buffer vào cuối LOB. Với BLOB, amount là số byte. Với CLOB, amount là số ký tự.

### 11.1 Ghi tại một offset

DBMS_LOB.WRITE ghi dữ liệu tại vị trí xác định:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_blob,
    amount  => UTL_RAW.LENGTH(l_chunk),
    offset  => 1,
    buffer  => l_chunk
);
~~~

Offset LOB bắt đầu từ 1. WRITE có thể ghi đè một vùng hiện có hoặc mở rộng LOB tùy vị trí và nội dung.

### 11.2 Không ghép toàn bộ BLOB thành RAW

Không tạo một RAW khổng lồ hoặc nối mọi chunk vào một biến để cuối cùng ghi một lần. Điều đó quay lại mô hình materialization và vướng giới hạn kích thước biến PL/SQL.

Hãy đọc/nhận chunk, xử lý chunk, ghi chunk và bỏ tham chiếu tới chunk trước khi xử lý phần tiếp theo.

## 12. Ghi CLOB theo chunk trong PL/SQL

Ví dụ tạo CLOB rỗng rồi append text:

~~~sql
DECLARE
    l_clob   CLOB;
    l_chunk  VARCHAR2(8000);
BEGIN
    INSERT INTO documents(document_id, file_name, text_content)
    VALUES (2002, 'notes.txt', EMPTY_CLOB())
    RETURNING text_content INTO l_clob;

    l_chunk := 'First text segment';
    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    l_chunk := 'Second text segment';
    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_chunk),
        buffer  => l_chunk
    );

    COMMIT;
END;
/
~~~

Với CLOB, amount là số ký tự trong buffer, không phải LENGTHB. Nếu dữ liệu có nhiều byte cho mỗi ký tự, không thay LENGTH bằng LENGTHB.

## 13. Temporary LOB

PL/SQL có thể tạo LOB tạm bằng DBMS_LOB.CREATETEMPORARY:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    lob_loc => l_temp_clob,
    cache   => TRUE,
    dur     => DBMS_LOB.CALL
);
~~~

Temporary LOB hữu ích khi cần xây dựng nội dung lớn trong bộ nhớ LOB của database trước khi ghi hoặc trả kết quả.

### 13.1 Vòng đời temporary LOB

Các bước thường gặp:

1. Khai báo locator.
2. Gọi CREATETEMPORARY.
3. Ghi hoặc nối chunk.
4. Dùng LOB trong câu SQL hoặc xử lý tiếp.
5. Gọi FREETEMPORARY khi không còn dùng.

Ví dụ:

~~~sql
DECLARE
    l_temp_clob CLOB;
    l_chunk     VARCHAR2(4000);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_temp_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    l_chunk := 'Header text';
    DBMS_LOB.WRITEAPPEND(
        l_temp_clob,
        LENGTH(l_chunk),
        l_chunk
    );

    -- Dùng l_temp_clob cho thao tác cần thiết.

    DBMS_LOB.FREETEMPORARY(l_temp_clob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_temp_clob);
        END IF;
        RAISE;
END;
/
~~~

FREETEMPORARY giải phóng tài nguyên LOB tạm. Không để temporary LOB tồn tại lâu hơn cần thiết, đặc biệt trong session chạy lâu hoặc xử lý nhiều request.

### 13.2 CALL và SESSION duration

DBMS_LOB.CALL tạo temporary LOB với thời hạn theo lời gọi PL/SQL; DBMS_LOB.SESSION giữ temporary LOB trong phạm vi session cho tới khi được giải phóng hoặc session kết thúc.

Chọn duration phù hợp:

- CALL khi LOB chỉ dùng trong một lần gọi.
- SESSION khi cần chia sẻ giữa nhiều lời gọi trong cùng session và có quản lý vòng đời rõ.

Không chọn SESSION chỉ vì tiện; cần gọi FREETEMPORARY đúng lúc.

### 13.3 Temporary LOB vẫn dùng tài nguyên

Temporary LOB không phải bộ nhớ miễn phí. Nó có thể sử dụng temporary tablespace, cache và tài nguyên session. Theo dõi lượng temporary LOB và bảo đảm cleanup trong cả success lẫn exception.

## 14. Transaction, khóa hàng và thời gian sống của LOB stream

Đọc LOB:

- Thực hiện SELECT và tiêu thụ stream khi connection/result set còn mở.
- Không trả InputStream ra khỏi tầng repository nếu tầng trên sẽ dùng sau khi connection đã được trả về pool.
- Tránh commit hoặc đóng connection trước khi stream hoàn tất.

Ghi LOB:

- Nếu cập nhật locator, thường cần SELECT ... FOR UPDATE.
- Giữ transaction mở trong suốt quá trình ghi.
- Đóng stream trước khi COMMIT.
- Rollback khi lỗi theo transaction contract.

### 14.1 Stream lâu giữ connection lâu

Streaming 2 GB qua mạng chậm có thể giữ một connection database trong thời gian dài. Điều này ảnh hưởng connection pool:

- Một request chiếm connection cho tới khi đọc xong.
- Client chậm làm connection bị giữ lâu.
- Nhiều download đồng thời có thể làm pool cạn.
- Transaction/row lock trong trường hợp ghi có thể tồn tại lâu hơn mong muốn.

Với download, không nên giữ transaction write hoặc row lock không cần thiết. Với upload qua SELECT FOR UPDATE, giới hạn thời gian upload và cân nhắc staging để không khóa hàng quá lâu.

### 14.2 Không đóng stream quá sớm

Driver có thể đọc dữ liệu từ database khi ứng dụng gọi read, chứ không nhất thiết tải hết tại thời điểm getBinaryStream. Vì vậy, connection, statement và result set phải còn hợp lệ trong suốt quá trình stream.

### 14.3 Connection pool và streaming HTTP

Nếu HTTP client tải rất chậm, servlet có thể giữ database connection lâu. Một số kiến trúc có thể:

- Stream trực tiếp nếu dung lượng và thời gian được kiểm soát.
- Dùng asynchronous response nhưng vẫn quản lý connection/LOB lifetime rõ.
- Chép sang object storage hoặc file staging theo quy trình có kiểm soát, rồi phục vụ file từ storage.
- Dùng URL download có thời hạn nếu hệ thống lưu trữ hỗ trợ.

Không thể đóng connection rồi tiếp tục đọc locator một cách tùy tiện.

## 15. Backpressure và buffer có giới hạn

Streaming tốt phải tôn trọng tốc độ của bên nhận. Nếu nguồn đọc nhanh hơn đích ghi, ứng dụng không nên tích lũy chunk vô hạn trong queue.

Ví dụ luồng:

~~~text
Oracle LOB stream
       |
       v
Fixed-size read buffer
       |
       v
Application processing
       |
       v
HTTP/file/object-storage output
~~~

Mỗi bước chỉ yêu cầu chunk tiếp theo sau khi bước trước đã xử lý đủ. Đây là backpressure ở mức ứng dụng.

### 15.1 Queue không giới hạn phá hỏng lợi ích streaming

Nếu code đọc liên tục từ Oracle rồi đưa chunk vào queue không giới hạn trong khi network output chậm, bộ nhớ vẫn tăng theo tổng kích thước dữ liệu.

Hãy dùng queue có giới hạn và cơ chế producer-consumer có backpressure. Không tạo thread riêng cho từng chunk nếu không có lý do và giới hạn concurrency.

### 15.2 Chọn buffer size

Buffer nhỏ:

- Giảm bộ nhớ mỗi request.
- Tăng số lần read/write và overhead gọi hàm.

Buffer lớn:

- Giảm số lần gọi.
- Tăng bộ nhớ trên mỗi request.
- Có thể không cải thiện throughput nếu bottleneck nằm ở network/storage.

Thử nghiệm với một số kích thước hợp lý. Đo throughput, latency, CPU, heap, GC và số request đồng thời. Chọn buffer theo tổng ngân sách bộ nhớ của dịch vụ.

## 16. Streaming BLOB từ Oracle tới HTTP response

Một endpoint download có thể đọc trực tiếp BLOB và ghi vào response output stream:

~~~java
String sql = """
    SELECT file_name, content_type, payload
    FROM documents
    WHERE document_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, documentId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            response.sendError(404);
            return;
        }

        String fileName = resultSet.getString("file_name");
        String contentType = resultSet.getString("content_type");
        InputStream input = resultSet.getBinaryStream("payload");

        if (input == null) {
            response.sendError(404);
            return;
        }

        response.setContentType(
            contentType != null ? contentType : "application/octet-stream"
        );
        response.setHeader(
            "Content-Disposition",
            buildSafeAttachmentHeader(fileName)
        );

        try (InputStream in = input) {
            OutputStream out = response.getOutputStream();
            byte[] buffer = new byte[64 * 1024];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }

            out.flush();
        }
    }
}
~~~

buildSafeAttachmentHeader là helper ứng dụng cần tự triển khai an toàn, xử lý tên file theo quy tắc HTTP header và tránh CR/LF injection. Ví dụ chỉ minh họa luồng streaming; cách đóng response stream tùy servlet container/framework sở hữu output stream.

### 16.1 Không đặt Content-Length bằng cách đoán

Nếu biết chính xác độ dài BLOB, có thể lấy độ dài từ metadata/LOB locator trước khi stream. Nếu không, có thể để HTTP server dùng chunked transfer hoặc cơ chế streaming của framework.

Không đọc toàn bộ BLOB chỉ để tính Content-Length. Không chuyển long sang int nếu kích thước có thể vượt miền int.

### 16.2 Client ngắt kết nối

Nếu client hủy download, write vào response có thể phát sinh IOException. Hãy dừng đọc LOB, đóng stream và trả connection về pool. Không tiếp tục tải toàn bộ LOB sau khi đích đã đóng.

### 16.3 Range request

Nếu cần hỗ trợ HTTP Range cho file lớn, ứng dụng phải đọc đúng vùng byte:

- Xác thực range.
- Xác định offset và length trong đơn vị byte.
- Dùng API hỗ trợ đọc một vùng LOB hoặc seek phù hợp.
- Trả status/header Content-Range chính xác.
- Không dùng CLOB character offset cho BLOB byte range.

Range request là một tính năng riêng cần kiểm thử; không phải cứ streaming là tự động hỗ trợ resume.

## 17. Streaming CLOB tới HTTP response

CLOB là text. Khi gửi ra HTTP, cần xác định charset và content type:

~~~java
response.setContentType("text/plain; charset=UTF-8");

try (Reader reader = resultSet.getCharacterStream("text_content")) {
    Writer writer = response.getWriter();
    char[] buffer = new char[8 * 1024];
    int count;

    while ((count = reader.read(buffer)) != -1) {
        writer.write(buffer, 0, count);
    }

    writer.flush();
}
~~~

Không gọi getSubString để tạo String toàn bộ trước khi ghi response. Cũng không dùng byte count của CLOB làm character count.

Nếu CLOB chứa HTML, JSON hoặc XML, hãy xác định content type, encoding và chính sách escaping/validation. Streaming không tự bảo đảm nội dung an toàn khi render trong trình duyệt.

## 18. LOB prefetch và ResultSet fetch size

JDBC có fetch size để gợi ý số hàng lấy mỗi lần từ database:

~~~java
statement.setFetchSize(100);
~~~

Fetch size giúp điều chỉnh việc lấy nhiều hàng trong ResultSet. Nó không có nghĩa toàn bộ LOB của mỗi hàng được đọc dần hoặc bị giới hạn ở 100 hàng × một buffer cố định.

Phân biệt:

- Fetch size: số hàng driver lấy theo batch.
- LOB stream: cách nội dung BLOB/CLOB được đọc.
- LOB prefetch: một số driver Oracle có thể lấy trước metadata hoặc một phần nhỏ LOB để giảm round trip.

LOB prefetch là tùy chọn driver-specific và có thể làm tăng bộ nhớ nếu đặt quá lớn. Kiểm tra tài liệu Oracle JDBC đúng phiên bản và đo với kích thước LOB thực tế.

Nếu đọc nhiều hàng có LOB:

- Đặt fetch size phù hợp với số hàng.
- Chỉ SELECT LOB khi thực sự cần nội dung.
- Đọc và đóng stream của một hàng trước khi tiến tới hàng khác nếu driver yêu cầu.
- Không giữ nhiều locator/stream cùng lúc nếu không cần.

## 19. Xử lý dữ liệu theo chunk trong ứng dụng

Một pipeline streaming có thể thực hiện xử lý trên mỗi chunk:

- Tính checksum.
- Đếm byte.
- Nén hoặc giải nén.
- Mã hóa/giải mã.
- Chuyển đổi encoding.
- Ghi sang file hoặc object storage.

Ví dụ tính SHA-256 khi copy BLOB:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");

try (InputStream input = resultSet.getBinaryStream("payload");
     OutputStream output = Files.newOutputStream(destination)) {

    byte[] buffer = new byte[64 * 1024];
    int count;

    while ((count = input.read(buffer)) != -1) {
        digest.update(buffer, 0, count);
        output.write(buffer, 0, count);
    }
}

byte[] checksum = digest.digest();
~~~

Checksum được tính tăng dần, không cần giữ toàn bộ nội dung. Có thể so sánh với checksum đã lưu để phát hiện dữ liệu truyền sai.

### 19.1 Nén và mã hóa

Các stream wrapper như GZIPOutputStream hoặc CipherOutputStream có thể được nối vào pipeline. Hãy xác định thứ tự nén/mã hóa:

- Khi upload: nguồn → nén (nếu cần) → mã hóa (nếu cần) → database.
- Khi download: database → giải mã → giải nén → đích.

Thứ tự cần khớp với định dạng đã lưu. Không ghi đè content type hoặc kích thước gốc bằng metadata không chính xác sau khi nén/mã hóa.

### 19.2 Kiểm tra dữ liệu đầu vào

Streaming không thay thế kiểm tra:

- Kích thước tối đa.
- MIME type thực tế và file signature.
- Tên file và đường dẫn.
- Virus/malware scan theo chính sách.
- Checksum.
- Quyền người dùng đối với document ID.
- Nội dung text/HTML khi hiển thị.

Có thể kiểm tra signature theo chunk đầu tiên rồi tiếp tục copy. Nếu cần scan toàn file, dùng pipeline streaming hoặc staging có giới hạn.

## 20. Lưu file lớn ở Oracle hay object storage?

Không phải mọi file lớn đều nên lưu trong BLOB. Hãy xem:

| Tiêu chí | BLOB trong Oracle | Object/file storage |
|---|---|---|
| Transaction với dữ liệu nghiệp vụ | Có thể cùng transaction | Thường cần outbox/saga hoặc quy trình hai bước |
| Backup/restore | Theo chính sách database | Theo chính sách storage riêng |
| Streaming | JDBC LOB stream | SDK/file stream |
| Quản lý metadata | SQL và constraint | Thường qua database + object metadata |
| File rất lớn, số lượng nhiều | Có thể tăng database storage/backup | Có thể phù hợp hơn tùy kiến trúc |
| Quyền truy cập | Database authorization | IAM/presigned URL/ACL |
| Chi phí | Database storage và I/O | Storage/network/egress |

Nếu file là một phần dữ liệu nghiệp vụ cần tính nguyên tử cùng row, BLOB có thể phù hợp. Nếu file cực lớn, số lượng cao hoặc cần CDN/download phân tán, object storage có thể phù hợp hơn.

Không có lựa chọn chung cho mọi hệ thống. Cần tính transaction consistency, chi phí, retention, backup, compliance và cách truy cập.

### 20.1 Mẫu metadata trong database, file trong object storage

Một mô hình phổ biến:

1. Tạo document metadata ở trạng thái PENDING.
2. Stream upload lên object storage với object key duy nhất.
3. Xác minh checksum/size.
4. Cập nhật metadata thành READY.
5. Nếu upload thất bại, dọn object tạm và cập nhật trạng thái lỗi.

Vì database và object storage không chung transaction ACID, cần idempotency, retry và reconciliation để xử lý trạng thái một bên thành công, bên kia thất bại.

## 21. SecureFiles và lưu trữ LOB

Oracle hỗ trợ SecureFiles cho LOB trong tablespace phù hợp. SecureFiles có các tính năng như compression, deduplication và encryption tùy phiên bản, cấu hình và quyền/licensing.

Ví dụ tạo bảng LOB:

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    payload BLOB
)
LOB (payload) STORE AS SECUREFILE (
    ENABLE STORAGE IN ROW
);
~~~

STORAGE IN ROW chỉ phù hợp với LOB nhỏ theo giới hạn Oracle; LOB lớn được lưu ngoài row. Streaming qua JDBC vẫn có ý nghĩa với cả LOB in-row và out-of-row.

### 21.1 Streaming và SecureFiles là hai lớp khác nhau

- SecureFiles quyết định cách Oracle lưu trữ và quản lý LOB.
- Streaming quyết định cách ứng dụng đọc/ghi nội dung.
- Một LOB dùng SecureFiles vẫn có thể bị tải toàn bộ vào byte array nếu ứng dụng gọi getBytes.
- Một LOB dùng BasicFiles vẫn có thể được đọc qua stream nếu driver hỗ trợ.

Không kỳ vọng đổi storage format tự động sửa code materialize toàn bộ nội dung.

## 22. BFILE và đọc file bên ngoài

BFILE cho phép Oracle truy cập file ở thư mục phía database server qua DIRECTORY object.

Ví dụ:

~~~sql
CREATE OR REPLACE DIRECTORY document_dir AS '/u01/app/documents';
GRANT READ ON DIRECTORY document_dir TO app_user;
~~~

Khai báo BFILE:

~~~sql
CREATE TABLE external_documents (
    document_id NUMBER PRIMARY KEY,
    external_file BFILE
);
~~~

Đọc bằng PL/SQL:

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
    l_offset INTEGER := 1;
    l_amount INTEGER;
    l_buffer RAW(32767);
BEGIN
    SELECT external_file
    INTO l_file
    FROM external_documents
    WHERE document_id = 100;

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);
        DBMS_LOB.READ(l_file, l_amount, l_offset, l_buffer);

        -- Xử lý chunk.

        l_offset := l_offset + l_amount;
    END LOOP;

    DBMS_LOB.FILECLOSE(l_file);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.FILEISOPEN(l_file) = 1 THEN
            DBMS_LOB.FILECLOSE(l_file);
        END IF;
        RAISE;
END;
/
~~~

Ví dụ minh họa vòng đọc; cần xử lý trường hợp locator NULL hoặc FILEOPEN lỗi trước khi gọi FILEISOPEN. BFILE không được ghi qua DBMS_LOB.WRITE; muốn đưa nội dung vào database, có thể dùng DBMS_LOB.LOADFROMFILE hoặc streaming từ ứng dụng theo quy trình phù hợp.

## 23. Lỗi thường gặp khi streaming

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| OutOfMemoryError khi tải file | getBytes/readAllBytes hoặc String toàn bộ | Dùng InputStream/Reader theo chunk |
| Stream lỗi sau khi method repository trả về | Connection/ResultSet đã đóng | Tiêu thụ stream trong phạm vi resource còn mở |
| Upload chậm bất thường | Buffer quá nhỏ, network hoặc database bottleneck | Đo throughput và thử buffer size |
| Connection pool cạn | Download chậm giữ connection lâu | Giới hạn stream đồng thời, timeout hoặc staging |
| CLOB bị lỗi ký tự | Dùng byte stream/charset không rõ | Dùng Reader/Writer và charset tường minh |
| Nội dung bị cắt | Giới hạn biến hoặc dùng getSubString không đúng | Dùng stream hoặc chunk API |
| Sai offset | Nhầm byte và ký tự, hoặc quên offset bắt đầu từ 1 | BLOB dùng byte, CLOB dùng ký tự |
| Upload BLOB bị tràn kiểu length | Ép file size long sang int | Dùng JDBC overload hỗ trợ long |
| Temporary LOB tăng liên tục | Không FREETEMPORARY | Giải phóng trong cả success/exception |
| LOB write lỗi khóa | Không SELECT FOR UPDATE khi dùng locator update | Giữ transaction và khóa hàng theo yêu cầu |
| Client hủy download nhưng DB vẫn đọc | Không dừng pipeline khi output lỗi | Hủy đọc, đóng stream và trả connection |
| Heap vẫn tăng dù dùng stream | Queue không giới hạn hoặc buffer trung gian toàn bộ | Dùng bounded queue và backpressure |
| Content-Length sai | Dùng character count cho byte hoặc ngược lại | Xác định đơn vị và metadata đúng |
| Lỗi khi dùng JDBC stream | Driver/API overload không tương thích | Kiểm tra phiên bản JDBC driver và tài liệu Oracle |

## 24. Quy trình triển khai streaming

Một quy trình thực tế:

1. Xác định nguồn dữ liệu: BLOB, CLOB, file upload, object storage hay BFILE.
2. Xác định kích thước tối đa và số stream đồng thời.
3. Chọn API stream phù hợp: InputStream/OutputStream cho binary, Reader/Writer cho text.
4. Đặt buffer cố định và giới hạn concurrency.
5. Xác định vòng đời connection, ResultSet, locator và transaction.
6. Xử lý lỗi giữa chừng, timeout và client cancellation.
7. Kiểm tra checksum, content type và quyền truy cập.
8. Đo heap, GC, throughput, latency và connection pool.
9. Kiểm thử dữ liệu rỗng, dữ liệu lớn, Unicode và lỗi network.
10. Triển khai theo dõi và giới hạn tài nguyên.

## 25. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm và dùng file test có kích thước khác nhau.

### Bài 1 — So sánh materialize và stream

Tạo BLOB vài chục MB. Đọc bằng getBytes và getBinaryStream. So sánh heap, GC và thời gian. Tăng kích thước file để quan sát mức tăng bộ nhớ.

### Bài 2 — Stream BLOB xuống file

Viết JDBC code dùng getBinaryStream, buffer 64 KB và Files.newOutputStream. So sánh checksum file đích với checksum nguồn.

### Bài 3 — Stream CLOB xuống file UTF-8

Tạo CLOB có tiếng Việt và ký tự Unicode ngoài BMP. Đọc bằng getCharacterStream và ghi UTF-8 bằng Writer. Xác nhận nội dung không mất ký tự.

### Bài 4 — Upload BLOB

Dùng setBinaryStream để INSERT file vào BLOB. Không gọi Files.readAllBytes. Đo heap và thời gian.

### Bài 5 — Upload CLOB

Dùng Reader và setCharacterStream để lưu file text UTF-8 vào CLOB. So sánh với cách đọc toàn bộ file thành String rồi setString.

### Bài 6 — DBMS_LOB.READ

Viết PL/SQL đọc BLOB theo RAW(32767) và CLOB theo VARCHAR2 chunk. Ghi nhận offset, amount và độ dài cuối.

### Bài 7 — WRITEAPPEND

Tạo EMPTY_BLOB/EMPTY_CLOB, ghi nhiều chunk bằng DBMS_LOB.WRITEAPPEND. Xác nhận nội dung và độ dài.

### Bài 8 — Temporary LOB

Tạo temporary CLOB, append nhiều đoạn, kiểm tra ISTEMPORARY và gọi FREETEMPORARY cả trong nhánh thành công lẫn exception.

### Bài 9 — Backpressure

Giả lập output chậm hơn input. Đưa chunk vào bounded queue và so sánh với queue không giới hạn. Theo dõi heap.

### Bài 10 — Connection lifetime

Thử đọc stream sau khi đóng ResultSet/Connection. Quan sát lỗi và sửa để tiêu thụ stream trong phạm vi resource.

### Bài 11 — HTTP download

Tạo endpoint stream BLOB tới response. Thử client tải chậm và client ngắt kết nối. Xác nhận connection được trả về pool.

### Bài 12 — Benchmark concurrency

Chạy 1, 10, 50 và 100 download đồng thời với buffer khác nhau. Theo dõi throughput, p95 latency, heap, GC và connection pool.

## 26. Checklist trước khi đưa streaming vào production

**Dữ liệu**

- Đã chọn BLOB/CLOB/NCLOB/BFILE đúng ngữ nghĩa?
- Có giới hạn kích thước và loại file?
- Đã phân biệt LOB NULL, LOB rỗng và không có hàng?
- CLOB có charset/encoding rõ ràng?

**Ứng dụng**

- Dùng InputStream/Reader thay cho byte[]/String toàn bộ?
- Buffer có giới hạn?
- Queue có bounded và có backpressure?
- Có dừng đọc khi client hủy?
- Không giữ nhiều LOB stream không cần thiết?

**JDBC và transaction**

- Driver hỗ trợ overload stream đang dùng?
- Connection/Statement/ResultSet còn mở trong lúc stream?
- Locator được dùng đúng transaction và row lock?
- Stream đóng trước khi commit/đóng connection?
- Exception có rollback theo contract?

**Tài nguyên**

- Connection pool đủ cho stream lâu?
- Có timeout và concurrency limit?
- Đã đo heap, GC, PGA, throughput và latency?
- Temporary LOB được giải phóng?

**Bảo mật**

- Kiểm tra quyền đọc tài liệu?
- Kiểm tra kích thước, MIME type và file signature?
- Tên file được encode an toàn trong HTTP header?
- Có checksum/scan theo yêu cầu?
- Không ghi dữ liệu nhạy cảm vào log?

## 27. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| BLOB | Dữ liệu nhị phân lớn |
| CLOB | Văn bản lớn theo database character set |
| NCLOB | Văn bản lớn theo national character set |
| BFILE | Locator tới file ngoài database, chỉ đọc |
| LOB locator | Tham chiếu tới LOB, không đồng nghĩa toàn bộ nội dung đã ở heap |
| getBytes/getSubString | Materialize phần dữ liệu được yêu cầu vào bộ nhớ |
| getBinaryStream | Đọc BLOB theo byte stream |
| getCharacterStream | Đọc CLOB theo character stream |
| setBinaryStream | Upload BLOB từ InputStream |
| setCharacterStream | Upload CLOB từ Reader |
| DBMS_LOB.READ | Đọc LOB theo chunk |
| DBMS_LOB.WRITE/WRITEAPPEND | Ghi LOB tại offset hoặc cuối LOB |
| Temporary LOB | Phải quản lý vòng đời và FREETEMPORARY |
| BLOB offset | Tính theo byte, bắt đầu từ 1 |
| CLOB offset | Tính theo ký tự, bắt đầu từ 1 |
| Backpressure | Không tích lũy chunk vô hạn khi đích chậm |
| Connection lifetime | Giữ connection/locator hợp lệ trong lúc stream |
| Fetch size | Điều khiển batch hàng, không thay thế LOB streaming |
| SecureFiles | Lớp lưu trữ LOB, độc lập với cách ứng dụng stream |

Streaming dữ liệu lớn là một thiết kế xuyên suốt từ Oracle LOB tới driver và ứng dụng. Hãy dùng locator cùng InputStream/Reader để đọc, setBinaryStream/setCharacterStream để ghi, hoặc DBMS_LOB theo chunk khi xử lý trong PL/SQL. Giữ buffer và queue có giới hạn, quản lý connection/transaction trong suốt thời gian truyền, và đo tải đồng thời. Như vậy, bộ nhớ ứng dụng được kiểm soát theo kích thước chunk thay vì phải tăng theo toàn bộ kích thước file.
