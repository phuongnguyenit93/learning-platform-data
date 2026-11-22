# NCHAR, NVARCHAR, LONGNVARCHAR và NClob trong JDBC

## 1. Bài toán: lưu và đọc văn bản Unicode bằng JDBC đúng kiểu dữ liệu

Một ứng dụng Java phải xử lý tên người dùng tiếng Việt, địa chỉ tiếng Nhật, mô tả sản phẩm đa ngôn ngữ hoặc tài liệu dài chứa emoji. Dữ liệu này đi qua nhiều lớp:

~~~text
Java String (các đơn vị mã UTF-16)
              |
              v
PreparedStatement + JDBC driver
              |
              v
DB parameter / cột ký tự theo schema, charset và collation
              |
              v
ResultSet + JDBC driver
              |
              v
Java String / Reader / NClob
~~~

Java có `String` biểu diễn nội dung Unicode nhưng **không có một kiểu Java `NString` riêng**. JDBC cung cấp một họ **SQL national character types** nhằm diễn đạt ý định làm việc với tập ký tự quốc gia/national character set của database:

- **`NCHAR`**: chuỗi quốc gia độ dài cố định.
- **`NVARCHAR`**: chuỗi quốc gia độ dài biến thiên.
- **`LONGNVARCHAR`**: chuỗi quốc gia biến thiên có dung lượng lớn.
- **`NCLOB`**: national character large object, thường dùng cho văn bản rất dài.

Đối tượng Java tương ứng thường là `String`, `Reader` hoặc `java.sql.NClob`. Chương trình có thể dùng các phương thức `setNString`, `setNCharacterStream`, `setNClob`, `getNString`, `getNCharacterStream` và `getNClob` để giao tiếp với JDBC driver.

**Đừng suy luận rằng không dùng tiền tố N thì văn bản không thể lưu Unicode.** Nhiều hệ quản trị lưu được Unicode trực tiếp trong `VARCHAR` hoặc `TEXT` nếu database/column dùng charset phù hợp (ví dụ PostgreSQL với UTF-8). Họ N-types là **khái niệm chuẩn trong JDBC**, còn tên kiểu SQL vật lý và cơ chế lưu trữ **phụ thuộc DBMS/driver**.

Bài học sử dụng Java 17+ và chỉ các API JDBC còn hiện hành. Phần ví dụ đầy đủ đầu tiên tự biên dịch/chạy với JDK để kiểm tra việc gọi API và xử lý `NClob` bằng test double; phần sau giải thích cách kiểm thử với database thật khi có driver và schema phù hợp.

## 2. Bảng phân biệt bốn kiểu JDBC

| JDBC type | Đặc trưng | Kiểu nhận trong Java | API thường dùng |
| --- | --- | --- | --- |
| `NCHAR` | Chuỗi national **cố định độ dài**; DB có thể padding khoảng trắng | `String` | `setNString`, `getNString` |
| `NVARCHAR` | Chuỗi national **độ dài thay đổi** trong giới hạn cột | `String` | `setNString`, `getNString` |
| `LONGNVARCHAR` | National character dữ liệu **dài**; cách lưu vật lý tùy DB | `String` hoặc `Reader` | `setNCharacterStream`, `getNCharacterStream` |
| `NCLOB` | National character **large object**, có lifecycle/resource riêng | `NClob` hoặc `Reader` | `setNClob`, `getNClob`, `createNClob` |

Tại sao có cả `LONGNVARCHAR` và `NCLOB`? Chúng đều có thể mang văn bản dài, nhưng `LONGNVARCHAR` biểu diễn dạng **long varying character value** ở mức kiểu JDBC, trong khi `NCLOB` thể hiện một **LOB** có API quản lý và đọc/ghi riêng. DBMS có thể map cả hai khái niệm vào cùng một kiểu vật lý hoặc chỉ hỗ trợ một phần. Không thể kết luận một cột chứa `NVARCHAR(MAX)` của SQL Server chính là native SQL `NCLOB`.

### 2.1. `NCHAR` — fixed-length national text

`NCHAR(n)` trong DBMS hỗ trợ nó có số lượng ký tự cố định theo quy tắc của hệ quản trị. Nếu giá trị ngắn hơn chiều dài khai báo, database có thể chèn **padding**. Điều này đặc biệt quan trọng khi:

- Đọc lại mã vùng/mã trạng thái và so sánh `String.equals`.
- Kiểm tra uniqueness, trailing spaces và collation.
- Định nghĩa business keys mà khoảng trắng cuối có thể có ý nghĩa.
- So sánh cột `NCHAR` với `NVARCHAR` trong một hệ DB cụ thể.

**Không tự động gọi `strip()` sau mọi `getNString`.** Việc xóa whitespace có thể phá dữ liệu mà nghiệp vụ muốn giữ, trong khi padding của DB cần được xử lý theo contract/schema. Nếu giá trị vốn không có kích thước cố định, thường chọn `NVARCHAR` phù hợp hơn.

### 2.2. `NVARCHAR` — variable-length national text

`NVARCHAR(n)` thường phù hợp với nhãn, tên, địa chỉ và đoạn text ngắn/trung bình cần national character representation. Tuy nhiên, ý nghĩa tham số `n` (ký tự, byte, UTF-16 code units hay quy tắc khác) và giới hạn tổng dung lượng **phải tra theo hệ quản trị**, không suy ra bằng `String.length()` một cách máy móc.

Ví dụ với SQL Server, `nvarchar(n)` và `nvarchar(max)` là lựa chọn hiện hành cho Unicode text. Với Oracle, cú pháp vật lý tương ứng có thể là `NVARCHAR2(n)`; không ép tên `NVARCHAR` chuẩn JDBC trở thành một loại DDL y hệt trên mọi DB.

### 2.3. `LONGNVARCHAR` — kiểu JDBC logic cho text dài

`LONGNVARCHAR` là một hằng thuộc `java.sql.Types` và `java.sql.JDBCType`. Nó thể hiện văn bản quốc gia dài theo JDBC, nhưng **không buộc DBMS phải có một câu DDL `LONGNVARCHAR`**.

Ví dụ SQL Server vẫn hỗ trợ Unicode text dài hiện hành bằng `nvarchar(max)`. Kiểu SQL Server `ntext` là loại **deprecated**, không nên đưa vào schema mới; các tài liệu driver có thể nhắc `ntext` như ánh xạ lịch sử, nhưng code hiện đại nên dùng large-value types. Hãy xem mapping thực tế của driver, thay vì suy luận từ tên `LONGNVARCHAR`.

Trong Java, streaming bằng `Reader` giúp không phải giữ toàn bộ chuỗi dài ở memory dưới dạng một `String` trước khi gửi.

### 2.4. `NCLOB` — national character large object

`java.sql.NClob` là interface mở rộng `java.sql.Clob`. Nó cung cấp các thao tác như:

- `length()`: chiều dài ký tự theo hợp đồng LOB/driver.
- `getCharacterStream()`: đọc ký tự qua `Reader`.
- `getSubString(long pos, int length)`: lấy một phần giá trị; **vị trí SQL LOB bắt đầu từ 1**.
- `setString(long pos, String str)` và `setCharacterStream(long pos)`: ghi dữ liệu khi driver và object hỗ trợ.
- `free()`: giải phóng tài nguyên LOB, chấm dứt việc sử dụng object.

Một `NClob` có thể là locator tới tài nguyên phía DB hoặc được driver materialize một phần/nhiều phần ở client. **Đừng mặc định nó chỉ là một `String` thuần bộ nhớ.** JavaDoc mô tả `NClob` nói chung có hiệu lực trong phạm vi transaction tạo nó; ứng dụng cần dùng và giải phóng đúng vòng đời. Với dữ liệu rất dài, ưu tiên stream thay vì gọi `getSubString(...)` để kéo toàn bộ vào RAM.

## 3. Các hằng SQL type hiện hành trong Java

`java.sql.Types` cung cấp các số nguyên dùng với JDBC metadata và một số API binding:

~~~java
int fixed = Types.NCHAR;
int varying = Types.NVARCHAR;
int longVarying = Types.LONGNVARCHAR;
int largeObject = Types.NCLOB;
~~~

Đây là **snippet**, cần import `java.sql.Types`. Enum `java.sql.JDBCType` cung cấp các hằng tương ứng dưới dạng `SQLType`:

~~~java
JDBCType.NCHAR
JDBCType.NVARCHAR
JDBCType.LONGNVARCHAR
JDBCType.NCLOB
~~~

Đây cũng là snippet, cần import `java.sql.JDBCType`. Những kiểu này đã tồn tại từ JDBC 4 (API national types từ Java 6) và **không phải API legacy**.

Dùng enum `JDBCType` tiện khi thao tác với `SQLType`, chẳng hạn một số overload `PreparedStatement.setObject(index, value, JDBCType.NVARCHAR)`. Nhưng **tính hỗ trợ của `setObject` theo đích N-type tùy driver**. Nếu mục tiêu là ghi national text và driver hỗ trợ API đúng chuẩn, `setNString` và `setNCharacterStream` thường thể hiện ý định rõ hơn.

### 3.1. Dùng metadata để biết driver thực sự báo loại gì

Có thể đọc loại cột qua `ResultSetMetaData`:

~~~java
ResultSetMetaData metadata = rs.getMetaData();
for (int col = 1; col <= metadata.getColumnCount(); col++) {
    System.out.println(metadata.getColumnLabel(col)
            + ": JDBC=" + metadata.getColumnType(col)
            + ", DB=" + metadata.getColumnTypeName(col));
}
~~~

Đây là **snippet** trong chương trình đã có `ResultSet rs` ở trạng thái hợp lệ; cần import `java.sql.ResultSetMetaData`. `getColumnType(...)` trả mã kiểu JDBC, trong khi `getColumnTypeName(...)` thường trả tên kiểu của DB.

Khi kiểm tra thực tế, bạn có thể thấy:

- JDBC type là `NVARCHAR` nhưng tên DB là `nvarchar`, `NVARCHAR2` hoặc tên vendor khác.
- Cột lưu text rất dài được JDBC driver báo dưới dạng `LONGNVARCHAR`, `NVARCHAR`, `CLOB`, `NCLOB` hoặc mapping phù hợp driver.
- Một DB dùng Unicode `VARCHAR/TEXT` nhưng không cung cấp N-types riêng.

**Không dùng một bảng mapping chung để ép mọi DBMS phải trả cùng mã metadata.** Đọc tài liệu driver và viết integration test cho schema thực tế của dự án.

## 4. Viết dữ liệu ngắn bằng `PreparedStatement.setNString`

Chữ ký chuẩn:

~~~java
void setNString(int parameterIndex, String value) throws SQLException;
~~~

JDBC yêu cầu driver chuyển `String` thành giá trị `NCHAR`, `NVARCHAR` hoặc `LONGNVARCHAR` phù hợp, tùy kích thước và giới hạn. Tham số SQL trong `PreparedStatement` **đánh số từ 1**, không phải 0.

Ví dụ trong chương trình có `Connection connection`:

~~~java
String sql = "INSERT INTO multilingual_label (id, title_n) VALUES (?, ?)";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 42L);
    statement.setNString(2, "Tiếng Việt – 日本語");
    statement.executeUpdate();
}
~~~

Đây là **snippet tích hợp DB**, không phải chương trình có thể chạy độc lập nếu chưa có bảng `multilingual_label`, driver, schema và DB server. Ưu điểm của `setNString`:

1. **Tham số hóa dữ liệu**, tránh nối input người dùng trực tiếp vào SQL.
2. Nêu rõ intention gửi national character data khi driver hỗ trợ.
3. Driver thực hiện conversion sang encoding/national character set của database.
4. Cho phép ứng dụng sử dụng `String` Java quen thuộc thay vì tự mã hóa byte.

### 4.1. `setString` có lưu Unicode được không?

Có thể **có**, tùy DB charset, kiểu cột và driver. Không đúng khi nói `setString` *luôn* làm mất Unicode. Ví dụ PostgreSQL database UTF-8 lưu Unicode trong `text`, `varchar` và `char` mà không cần một họ N-types riêng.

Trái lại, trên hệ quản trị phân biệt character set và national character set, dùng `setNString` có thể loại bỏ một số ambiguity khi gửi parameter vào cột national text.

**Quy tắc thực hành:** chọn schema dữ liệu trước, đọc mapping của driver, rồi dùng binding API phù hợp. Nếu driver không hỗ trợ national character set, chuyển sang kiểu Unicode được driver/DB hỗ trợ (chẳng hạn `VARCHAR/TEXT` UTF-8) **theo contract**, không try/catch mù quáng rồi âm thầm đổi kiểu.

### 4.2. SQL NULL và `setNString`

Để gửi SQL NULL cho cột national:

~~~java
statement.setNull(2, Types.NVARCHAR);
~~~

Đây là snippet trong context có `PreparedStatement statement` và import `java.sql.Types`. Với cột `NCLOB`, giá trị target type thường là `Types.NCLOB`, nếu driver có hỗ trợ.

Lưu ý phân biệt:

- `""`: chuỗi Java rỗng.
- `null` ở Java: không có object `String`.
- SQL `NULL`: marker vắng dữ liệu trong cột/parameter.

Một số DBMS có quy tắc biến chuỗi rỗng thành NULL cho những kiểu string cụ thể; phải kiểm thử theo DB. Không tự coi `""` và SQL NULL giống nhau trong mọi hệ thống.

## 5. Ghi văn bản dài với `setNCharacterStream`

Khi text rất dài, dùng `Reader` để tránh giữ một `String` lớn trong memory. JDBC có các overload:

~~~java
statement.setNCharacterStream(index, reader);
statement.setNCharacterStream(index, reader, length);
~~~

Đây là chữ ký **dùng trong snippet**, với `index` là chỉ số 1-based, `reader` là `java.io.Reader`, và `length` là số ký tự dạng `long`.

Ví dụ đọc text từ `Reader`:

~~~java
try (Reader input = Files.newBufferedReader(path, StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement(
             "INSERT INTO documents (id, content_n) VALUES (?, ?)")) {
    statement.setLong(1, documentId);
    statement.setNCharacterStream(2, input);
    statement.executeUpdate();
}
~~~

Đây là **snippet tích hợp DB**: các biến `path`, `connection`, `documentId` phải được cung cấp; cần import `java.io.Reader`, `java.nio.file.Files`, `StandardCharsets`, `java.sql.PreparedStatement`. Cột `content_n` phải được DB và JDBC driver cấu hình hỗ trợ dạng national text dài.

**Điều kiện quan trọng:** `Reader` vẫn mở khi `executeUpdate()` chạy. Driver có thể tiêu thụ stream **khi execute**, không nhất thiết đọc hết ngay lúc `setNCharacterStream(...)` được gọi. Đóng stream trước execute có thể gây lỗi, dữ liệu rỗng hoặc lỗi ngẫu nhiên.

### 5.1. Có hay không có tham số length?

Với overload có `length`:

~~~java
statement.setNCharacterStream(2, reader, expectedCharacters);
~~~

`expectedCharacters` là số ký tự mà contract JDBC yêu cầu, **không phải số byte UTF-8**. Nếu length không đúng, driver có thể thất bại, chờ thêm dữ liệu hoặc dùng quy tắc riêng được mô tả trong tài liệu API/driver.

Khi nguồn là stream mà ứng dụng không biết chính xác số ký tự, overload không length thường dễ dùng hơn nếu driver hỗ trợ. Đừng dùng `Files.size(path)` (số byte) làm `length` cho `Reader` UTF-8. Đừng đoán số ký tự SQL cần bằng cách lấy số code points mà không xem định nghĩa của driver/schema.

### 5.2. Khác `setCharacterStream` thế nào?

- `setCharacterStream(...)` biểu đạt character data chung, thường chuyển thành `LONGVARCHAR` hoặc `CLOB` theo database/driver.
- `setNCharacterStream(...)` biểu đạt **national character** data và quá trình chuyển đổi tới national character set.

Đối với PostgreSQL UTF-8, kiểu dữ liệu Unicode được dùng có thể là `text`/`varchar` và API `setCharacterStream` là lựa chọn portable hơn. Đối với hệ có cột national text, `setNCharacterStream` thể hiện chính xác intention.

Không tự chuyển `Reader` thành `InputStream` bằng charset tùy ý rồi dùng `setBinaryStream` để lưu text vào cột ký tự. Binary và character data có hợp đồng khác nhau.

## 6. Ghi `NCLOB` bằng `setNClob` và `Connection.createNClob`

Với cột SQL national large object, JDBC cung cấp ba cách phổ biến:

~~~java
statement.setNClob(2, nclobObject);
statement.setNClob(2, reader);
statement.setNClob(2, reader, numberOfCharacters);
~~~

Đây là snippet thể hiện overloads có trên `PreparedStatement`.

### 6.1. Dùng `Reader` trực tiếp

~~~java
try (Reader text = Files.newBufferedReader(path, StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement(
             "INSERT INTO articles (id, article_n) VALUES (?, ?)")) {
    statement.setLong(1, articleId);
    statement.setNClob(2, text);
    statement.executeUpdate();
}
~~~

Đây là **snippet** cần các biến đã nêu; không tự chạy nếu chưa có DB. Khác với `setNCharacterStream`, `setNClob` báo rõ cho driver rằng parameter cần được xử lý theo **SQL NCLOB**. Nhiều driver/DB dùng cơ chế streaming hoặc LOB locator riêng để quản lý dữ liệu này.

### 6.2. Tạo `NClob` từ connection

Nếu driver hỗ trợ:

~~~java
NClob nationalLob = connection.createNClob();
try {
    nationalLob.setString(1, text);
    try (PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO articles (id, article_n) VALUES (?, ?)")) {
        statement.setLong(1, articleId);
        statement.setNClob(2, nationalLob);
        statement.executeUpdate();
    }
} finally {
    nationalLob.free();
}
~~~

Đây là **snippet tích hợp DB**: cần `text`, `articleId` và `connection`; import `java.sql.NClob`. `setString(1, ...)` dùng vị trí **1-based của LOB**. `free()` được gọi trong `finally` để giải phóng tài nguyên kể cả khi execute thất bại.

**Không giả định mọi JDBC driver hỗ trợ `createNClob()`.** API cho phép ném `SQLFeatureNotSupportedException` nếu loại dữ liệu này không được hỗ trợ. Một DBMS dùng Unicode text mà không có national large object native có thể yêu cầu chọn cách lưu khác.

### 6.3. Không kết thúc vòng đời `NClob` quá sớm

Nếu bạn tạo `NClob` rồi đặt vào PreparedStatement, hãy giữ object còn hợp lệ cho tới khi driver hoàn tất execute. Sau đó gọi `free()` ở scope sở hữu thích hợp. Một số LOB resources có transaction-scoped lifetime; không cache `NClob` lâu hơn transaction/connection rồi cố đọc nó từ thread khác.

Một `NClob` không được xem như entity immutable hoặc value object có thể sống vô hạn. Nếu cần text sau khi đóng connection, hãy **materialize dữ liệu cần thiết trong lúc ResultSet/transaction còn hợp lệ** hoặc stream tới một destination được quản lý khác.

## 7. Đọc dữ liệu bằng ResultSet

Các getter tương ứng:

| API | Kết quả Java | Khi dùng |
| --- | --- | --- |
| `getNString(indexOrLabel)` | `String` hoặc `null` | Cột national string nhỏ/đủ để materialize |
| `getNCharacterStream(indexOrLabel)` | `Reader` hoặc `null` | Text national dài cần đọc theo luồng |
| `getNClob(indexOrLabel)` | `NClob` hoặc `null` | Cột national large object cần API LOB |
| `getString(...)` | `String` hoặc `null` | Text thông thường theo mapping driver |
| `getCharacterStream(...)` | `Reader` hoặc `null` | Stream character data chung |

Đối với ResultSet, **chỉ số cột cũng bắt đầu từ 1**. `getNString("title")` dùng label cột, không nhất thiết là tên cột gốc nếu SQL có `AS` alias.

### 7.1. Đọc national string

~~~java
String title = result.getNString("title_n");
if (title != null) {
    // Xử lý title.
}
~~~

Đây là snippet trong phạm vi có `ResultSet result`. Với SQL NULL, getter trả `null`. Không gọi `title.length()` khi chưa kiểm tra null.

Nếu cột `NCHAR` có padding, có thể cần business policy về khoảng trắng sau khi đọc. Không xóa dữ liệu vô điều kiện bằng `trim()` chỉ vì đã dùng fixed-length type.

### 7.2. Đọc national character stream

~~~java
try (Reader reader = result.getNCharacterStream("content_n")) {
    if (reader != null) {
        // Đọc Reader theo từng buffer hoặc chuyển tới Writer đích.
    }
}
~~~

Đây là snippet với import `java.io.Reader` và ResultSet hợp lệ. Khi API trả stream, hãy **đọc và đóng stream trước khi tiến ResultSet sang hàng khác hoặc đóng ResultSet** theo hợp đồng driver. Đừng giữ Reader sau khi cursor/transaction đã kết thúc.

Khi làm việc với file lớn, tránh `reader.transferTo(new StringWriter())` nếu mục tiêu là tiết kiệm RAM: cách đó vẫn materialize tất cả text vào memory. Dùng `BufferedWriter` hoặc cơ chế streaming sang output được quản lý, với giới hạn kích thước và xử lý lỗi I/O thích hợp.

### 7.3. Đọc và giải phóng `NClob`

~~~java
NClob nclob = result.getNClob("article_n");
if (nclob != null) {
    try {
        try (Reader characters = nclob.getCharacterStream()) {
            // Chuyển dữ liệu theo luồng.
        }
    } finally {
        nclob.free();
    }
}
~~~

Đây là snippet với `ResultSet result` và import `java.sql.NClob`, `java.io.Reader`. Nếu gọi `free()` rồi dùng `nclob.getCharacterStream()` hoặc `nclob.length()`, object có thể ném `SQLException` vì đã giải phóng tài nguyên. Đừng gọi `free` trước khi stream đã hoàn thành.

Đối với dữ liệu ngắn và driver có hỗ trợ, có thể dùng `getNString(...)` để lấy thẳng toàn bộ text. Nhưng với NCLOB nhiều MB/GB, **không** nên materialize một lúc chỉ để in vài ký tự đầu.

### 7.4. Phân biệt SQL NULL với chuỗi rỗng

Với `getNString` hoặc `getNClob`, SQL NULL có thể trả `null`. Nếu dùng một getter trả primitive, `ResultSet.wasNull()` hỗ trợ phân biệt SQL NULL. Với object getters, thường chỉ cần kiểm tra đối tượng null.

Không giả định mọi DB phân biệt `""` với `NULL` giống nhau. Hãy kiểm thử empty string/NULL theo DBMS và cột; ví dụ một số hệ quản trị có semantics khác nhau cho chuỗi rỗng.

## 8. Java String là UTF-16; chiều dài DB không giống số ký tự nhìn thấy

Một ví dụ Unicode:

~~~java
String name = "Caf\u00E9 \uD83D\uDE80";
System.out.println(name.length());
System.out.println(name.codePointCount(0, name.length()));
~~~

Đây là snippet Java đặt trong method; output:

~~~text
7
6
~~~

Chuỗi `Café 🚀` có **6 Unicode code points** nhưng **7 UTF-16 code units** vì rocket emoji dùng surrogate pair. Số ký tự người dùng nhận thức (grapheme clusters) lại là khái niệm riêng, đặc biệt với emoji tổ hợp và combining marks.

Điều này liên quan đến JDBC:

- Tham số `NVARCHAR(n)` có thể dùng đơn vị đo và quy tắc giới hạn riêng của DBMS.
- Một số DB dùng độ dài theo bytes, code units hoặc characters tùy charset/collation.
- `NClob.length()` báo số **ký tự LOB theo driver/DB**; không mặc định tương đương `String.length()` trên mọi driver.
- `Reader` trong Java phát ra ký tự UTF-16; length truyền vào overload stream là **đếm ký tự theo hợp đồng JDBC**, không phải số byte UTF-8 trên đĩa.
- Unicode normalization (NFC/NFD) **không tự xảy ra** chỉ vì dùng N-types. Hai chuỗi canonically equivalent có thể vẫn khác `String.equals` nếu DB/app không chuẩn hóa theo policy riêng.

Với business key như username, nên xác định rõ policy Unicode normalization và collation của database; chọn `NVARCHAR` không tự giải quyết tương đương `é` dựng sẵn và `e + combining acute`.

## 9. Ví dụ Java 17+ hoàn chỉnh: thao tác national JDBC APIs bằng test double

### 9.1. Tại sao ví dụ không cần database?

`java.sql.PreparedStatement`, `ResultSet` và `NClob` là **interface JDBC**. JDK không chứa sẵn một database server và driver bảo đảm có mặt trên mọi máy học. Để ví dụ biên dịch/chạy hoàn toàn bằng Java 17+, ta dùng **dynamic proxy** làm test double cho ba interface ấy.

Test double chỉ thực hiện:

- `setNString(1, title)`.
- `setNCharacterStream(2, Reader)`.
- `setNClob(3, Reader)`.
- `getNString(1)`, `getNCharacterStream(2)`, `getNClob(3)`.
- `NClob.length()`, `getCharacterStream()`, `free()`.
- `ResultSet.next()` và `close()`.

Dữ liệu được lưu vào **mảng String trong bộ nhớ**, không gửi tới DB. Điều đó giúp xác minh cách gọi API, thứ tự resource handling và Unicode trong chương trình; **không** xác nhận driver/DB thực sự có hỗ trợ N-types hoặc conversion chính xác. Phần 10 trình bày cách kiểm chứng với database thật.

### 9.2. Source hoàn chỉnh: `NationalTextDemo.java`

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.JDBCType;
import java.sql.NClob;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.concurrent.atomic.AtomicBoolean;

public class NationalTextDemo {
    static String readAll(Reader reader) throws SQLException {
        try {
            StringWriter output = new StringWriter();
            reader.transferTo(output);
            return output.toString();
        } catch (IOException e) {
            throw new SQLException("Reader failed", e);
        }
    }

    static PreparedStatement fakeStatement(String[] values) {
        InvocationHandler handler = (proxy, method, args) -> {
            switch (method.getName()) {
                case "setNString" -> {
                    values[(Integer) args[0] - 1] = (String) args[1];
                    return null;
                }
                case "setNCharacterStream", "setNClob" -> {
                    values[(Integer) args[0] - 1] = readAll((Reader) args[1]);
                    return null;
                }
                case "close" -> {
                    return null;
                }
                default -> throw new SQLFeatureNotSupportedException(
                        "Mock does not implement " + method.getName());
            }
        };
        return (PreparedStatement) Proxy.newProxyInstance(
                PreparedStatement.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class}, handler);
    }

    static NClob fakeNClob(String text) {
        AtomicBoolean freed = new AtomicBoolean();
        InvocationHandler handler = (proxy, method, args) -> {
            if ("free".equals(method.getName())) {
                freed.set(true);
                return null;
            }
            if (freed.get()) {
                throw new SQLException("NClob was freed");
            }
            return switch (method.getName()) {
                case "length" -> (long) text.length();
                case "getCharacterStream" -> new StringReader(text);
                default -> throw new SQLFeatureNotSupportedException(
                        "Mock does not implement " + method.getName());
            };
        };
        return (NClob) Proxy.newProxyInstance(
                NClob.class.getClassLoader(),
                new Class<?>[] {NClob.class}, handler);
    }

    static ResultSet fakeResultSet(String[] values) {
        AtomicBoolean advanced = new AtomicBoolean();
        InvocationHandler handler = (proxy, method, args) -> {
            return switch (method.getName()) {
                case "next" -> !advanced.getAndSet(true);
                case "getNString" -> values[(Integer) args[0] - 1];
                case "getNCharacterStream" ->
                        new StringReader(values[(Integer) args[0] - 1]);
                case "getNClob" -> fakeNClob(values[(Integer) args[0] - 1]);
                case "close" -> null;
                default -> throw new SQLFeatureNotSupportedException(
                        "Mock does not implement " + method.getName());
            };
        };
        return (ResultSet) Proxy.newProxyInstance(
                ResultSet.class.getClassLoader(),
                new Class<?>[] {ResultSet.class}, handler);
    }

    public static void main(String[] args) throws Exception {
        String title = "Caf\u00E9 \uD83D\uDE80";
        String longText = "D\u00F2ng 1: Ti\u1EBFng Vi\u1EC7t";
        String article = "N\u1ED9i dung \u4E2D\u6587 \uD83D\uDE80";
        String[] stored = new String[3];

        System.out.println("JDBC types: " + JDBCType.NCHAR + ","
                + JDBCType.NVARCHAR + "," + JDBCType.LONGNVARCHAR
                + "," + JDBCType.NCLOB);

        try (PreparedStatement statement = fakeStatement(stored);
             Reader longReader = new StringReader(longText);
             Reader nclobReader = new StringReader(article)) {
            statement.setNString(1, title);
            statement.setNCharacterStream(2, longReader);
            statement.setNClob(3, nclobReader);
        }

        try (ResultSet result = fakeResultSet(stored)) {
            if (!result.next()) {
                throw new AssertionError("Missing simulated row");
            }
            System.out.println("NString round-trip: "
                    + title.equals(result.getNString(1)));

            try (Reader reader = result.getNCharacterStream(2)) {
                System.out.println("NCharacterStream round-trip: "
                        + longText.equals(readAll(reader)));
            }

            NClob nclob = result.getNClob(3);
            try {
                try (Reader reader = nclob.getCharacterStream()) {
                    System.out.println("NClob round-trip: "
                            + article.equals(readAll(reader)));
                }
                System.out.println("NClob length equals UTF-16 units: "
                        + (nclob.length() == article.length()));
            } finally {
                nclob.free();
            }
            try {
                nclob.length();
                throw new AssertionError("Freed NClob still usable");
            } catch (SQLException expected) {
                System.out.println("Freed NClob rejected: true");
            }
        }
        System.out.println("Title UTF-16 units: " + title.length());
        System.out.println("Title code points: "
                + title.codePointCount(0, title.length()));
    }
}
~~~

**Giải thích code quan trọng:**

1. `JDBCType.NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB` dùng các enum JDBC chuẩn, không phải những kiểu SQL tự định nghĩa.
2. `fakeStatement` dùng `Proxy` để ghi nhận các lời gọi `setNString`/`setNCharacterStream`/`setNClob` vào mảng. **Đây không phải driver**; implementation không mở socket hay execute SQL.
3. `Reader.transferTo(StringWriter)` trong test double **materialize toàn bộ stream** vào RAM để có thể so sánh. Driver production có thể streaming/chunking khác; demo không được dùng để đo memory consumption của database LOB.
4. `fakeResultSet` trả cùng giá trị qua các getter national, cho phép so sánh nội dung sau “round trip” **trong bộ nhớ**.
5. `fakeNClob` chỉ implement các method dùng trong bài, mô phỏng `free()` và ngoại lệ nếu tiếp tục truy cập sau free. Không đưa class test double này vào production.
6. `NClob.length() == article.length()` là **kết quả của test double này**. Không suy rộng thành định luật cho độ dài LOB trên mọi DBMS.
7. Những literal `\uXXXX` giúp source có thể được lưu dưới dạng ASCII mà vẫn biên dịch thành văn bản Unicode đúng.
8. `try-with-resources` đóng `PreparedStatement`, `ResultSet`, `Reader`, còn `NClob.free()` được gọi ở `finally`.
9. Proxy ném `SQLFeatureNotSupportedException` với các method không mô phỏng để tránh giả vờ có khả năng JDBC khác.

### 9.3. Biên dịch/chạy trên Java 17+

Lưu đúng file `NationalTextDemo.java` rồi chạy từ thư mục chứa file:

~~~sh
javac --release 17 NationalTextDemo.java
java NationalTextDemo
~~~

**Stdout chính xác** (đã kiểm thử trên JDK 24 với `javac --release 17`):

~~~text
JDBC types: NCHAR,NVARCHAR,LONGNVARCHAR,NCLOB
NString round-trip: true
NCharacterStream round-trip: true
NClob round-trip: true
NClob length equals UTF-16 units: true
Freed NClob rejected: true
Title UTF-16 units: 7
Title code points: 6
~~~

Bài demo này **không cần driver JAR hoặc database server**. Vì vậy nó có thể chạy trong môi trường Java SE thuần. Muốn xác nhận conversion, storage và support trên DB thật, cần integration test riêng.

## 10. Dùng national text types trong các DBMS hiện hành

### 10.1. SQL Server: `nchar`, `nvarchar`, `nvarchar(max)`

Với SQL Server, một schema minh họa hiện hành:

~~~sql
CREATE TABLE dbo.multilingual_documents (
    id BIGINT PRIMARY KEY,
    short_code NCHAR(8),
    title NVARCHAR(200),
    content NVARCHAR(MAX)
);
~~~

Đây là **SQL Server DDL minh họa**, không phải SQL portable cho mọi DB. Microsoft JDBC Driver hỗ trợ các phương thức national character như `setNString`, `setNCharacterStream`, `getNString`, `getNCharacterStream` và một số phép làm việc với `NClob` tùy mapping/driver version. `nvarchar(max)` thích hợp cho Unicode text dài; không viết schema mới bằng `ntext` vì SQL Server **đã deprecated `ntext` từ lâu**.

**Quan trọng:** SQL Server không có cú pháp native `NCLOB` y hệt Oracle. Driver có thể ánh xạ giá trị Unicode dài hoặc JDBC LOB interface tới kiểu dữ liệu vendor-specific. `NClob` trong Java không tự bảo đảm bạn đã tạo cột SQL Server tên `NCLOB`.

Trong SQL Server, giới hạn `nchar(n)`/`nvarchar(n)` liên quan đến byte-pairs UTF-16; ký tự bổ sung có thể tốn hai cặp. Không dùng `String.codePointCount` làm thước đo trực tiếp cho số `n` được phép. Kiểm tra tài liệu SQL Server về `nvarchar(n)`, collation và supplementary characters.

### 10.2. Oracle: national columns và `NCLOB`

Oracle có những kiểu như `NCHAR`, `NVARCHAR2` và `NCLOB`. Schema minh họa:

~~~sql
CREATE TABLE multilingual_documents (
    id NUMBER(19) PRIMARY KEY,
    short_code NCHAR(8),
    title NVARCHAR2(200),
    content NCLOB
);
~~~

Đây là **Oracle DDL**, không phải lệnh đã thực thi trong môi trường kiểm thử. Trong JDBC vẫn dùng các interface/hằng national character chuẩn, nhưng mapping chi tiết phụ thuộc phiên bản Oracle JDBC driver, cấu hình national character set và database.

`LONGNVARCHAR` của JDBC **không đồng nghĩa phải tạo cột Oracle tên `LONGNVARCHAR`**. Đối với text rất dài, cân nhắc NCLOB khi chính DB và driver hỗ trợ; đừng sử dụng loại SQL `LONG` cũ như một lựa chọn mặc định cho schema mới.

### 10.3. PostgreSQL: Unicode qua `text` và `varchar`

PostgreSQL có các loại `character(n)`, `character varying(n)` và `text`. Trong database cấu hình UTF-8, chúng có thể lưu Unicode mà **không cần họ SQL N-types riêng**.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE multilingual_documents (
    id BIGINT PRIMARY KEY,
    short_code CHAR(8),
    title VARCHAR(200),
    content TEXT
);
~~~

Với PostgreSQL JDBC driver, ứng dụng thường dùng `setString`/`getString` và `setCharacterStream`/`getCharacterStream` theo mapping hỗ trợ. **Không mặc định `setNClob` hoặc `createNClob` hoạt động chỉ vì JDK có interface này.** Hãy kiểm tra PostgreSQL JDBC driver version và phép thử thực tế. Nếu driver ném `SQLFeatureNotSupportedException`, đó là tín hiệu phải dùng contract được driver hỗ trợ thay vì ép một N-type không tồn tại.

### 10.4. Bảng quyết định theo vendor

| Nhu cầu | SQL Server | Oracle | PostgreSQL |
| --- | --- | --- | --- |
| Chuỗi Unicode ngắn | `nvarchar(n)` | `NVARCHAR2(n)` | `varchar(n)` trên UTF-8 DB |
| National fixed text | `nchar(n)` | `NCHAR(n)` | `char(n)`, Unicode theo DB encoding |
| Unicode text rất dài | `nvarchar(max)` | `NCLOB` khi phù hợp | `text` |
| JDBC binding | `setNString` nếu driver hỗ trợ | `setNString`/`setNClob` theo cột | Thường `setString`/`setCharacterStream` |
| Resource large object | Kiểm tra mapping driver | `NClob`/LOB resource | JDBC mapping `text`/LOB đặc thù |

Đây là bảng **định hướng**, không thay tài liệu mapping của chính driver/version/schema mà ứng dụng đang dùng. Khả năng hỗ trợ N-types và LOB streaming có thể khác nhau đáng kể giữa các driver.

## 11. Ví dụ tích hợp JDBC thật: parameterized insert và đọc theo luồng

Ví dụ sau là **một method** có thể đặt trong repository/service đã sở hữu `Connection` từ pool hoặc `DataSource`. Nó cần bảng **`multilingual_documents(id, short_code, title, content)`** tương ứng DB/schema thực tế và driver có hỗ trợ national APIs.

~~~java
static void insertNationalText(
        Connection connection,
        long id,
        String code,
        String title,
        Reader content) throws SQLException {

    String sql = """
            INSERT INTO multilingual_documents
                    (id, short_code, title, content)
            VALUES (?, ?, ?, ?)
            """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);
        statement.setNString(2, code);
        statement.setNString(3, title);
        statement.setNClob(4, content);
        statement.executeUpdate();
    }
}
~~~

Đây là snippet **method hoàn chỉnh trong class**, nhưng không phải chương trình có `main`; cần import `java.sql.Connection`, `PreparedStatement`, `SQLException` và `java.io.Reader`. Caller chịu trách nhiệm **giữ `content` mở qua `executeUpdate()`**, sở hữu transaction và đóng `Connection` theo pool lifecycle.

**Không nên dùng method này với mọi vendor một cách mù quáng.** Với SQL Server `nvarchar(max)`, mapping national LOB cần được xác minh qua driver; với PostgreSQL `text`, API phù hợp thường là `setCharacterStream`. Nếu driver từ chối `setNClob`, dùng một implementation mapping đã được thiết kế cho driver ấy, không catch rồi bỏ lỗi silently.

Đọc một row với `NClob`:

~~~java
static void consumeNationalText(
        Connection connection, long id, Writer destination)
        throws SQLException, IOException {

    String sql = """
            SELECT content
            FROM multilingual_documents
            WHERE id = ?
            """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);
        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return;
            }

            NClob lob = rs.getNClob(1);
            if (lob == null) {
                return;
            }
            try {
                try (Reader source = lob.getCharacterStream()) {
                    source.transferTo(destination);
                }
            } finally {
                lob.free();
            }
        }
    }
}
~~~

Đây cũng là **method cho integration với driver thật**, không tự chạy nếu thiếu DB. Cần import `java.io.Writer`, `Reader`, `IOException`, `java.sql.NClob` và các JDBC classes. Caller sở hữu `destination`, nên method **không tự đóng Writer**. Với target DB không hỗ trợ `getNClob`, cần dùng API string/stream theo mapping của driver.

**Tài nguyên và transaction:** `Reader` từ LOB, `NClob` và `ResultSet` được dùng trong phạm vi còn hợp lệ rồi đóng/free theo thứ tự. Nếu stream rất lớn, dữ liệu đi tới `destination` theo luồng, không bắt buộc materialize vào `String`.

## 12. Null, padding, giới hạn chiều dài và chuyển mã

### 12.1. SQL NULL khác Java null và chuỗi rỗng

Phân biệt:

- `statement.setNString(index, "")`: cố ghi chuỗi rỗng (subject to DB semantics).
- `statement.setNull(index, Types.NVARCHAR)`: cố ghi SQL NULL national string.
- `statement.setNull(index, Types.NCLOB)`: cố ghi SQL NULL national LOB.
- `result.getNString(index) == null`: SQL NULL theo mapping và getter.
- `result.getNClob(index) == null`: cột LOB SQL NULL.

Một số DB biến empty string thành SQL NULL đối với những loại cột. Vì vậy đừng coi empty string luôn khác NULL sau database round trip nếu chưa test DB cụ thể.

### 12.2. NCHAR padding

Vì `NCHAR` fixed length, DBMS có thể thêm spaces ở bên phải. Khi dùng fixed-length codes, lưu ý:

- `equals` của Java có thể coi `"AB"` khác `"AB      "`.
- So sánh trong DB có thể áp quy tắc padding/collation riêng, kết quả không giống Java.
- Không tự xóa mọi whitespace rồi coi hai giá trị kinh doanh chắc chắn tương đương.
- Nếu định danh/nhãn vốn có độ dài thay đổi, chọn `NVARCHAR` thay vì `NCHAR` có thể dễ hơn.

### 12.3. Chuyển mã và lỗi mất dữ liệu

N-types báo ý định national-character conversion, nhưng việc lưu chính xác phụ thuộc:

- Charset/national character set của database.
- Driver và cấu hình session/connection.
- Hệ chữ/code points được database hỗ trợ.
- Kiểu vật lý, collation và giới hạn cột.
- Cách bind parameter và cách đọc kết quả.

Driver có thể báo `SQLException` hoặc `SQLFeatureNotSupportedException` khi national conversion không được hỗ trợ hay không thể thực hiện an toàn. **Không đổi tất cả lỗi conversion thành việc thay ký tự không biểu diễn được bằng dấu `?`** mà không có sự chấp thuận của sản phẩm.

### 12.4. Normalization và collation là chuyện riêng

`NCHAR` và `NVARCHAR` không mặc định chuẩn hóa NFC, không tự thực hiện accent-insensitive matching và không quyết định toàn bộ semantics case-folding. Hai Java strings:

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";
~~~

là canonically equivalent nhưng khác code-unit representation. Database collation có thể coi chúng bằng nhau hoặc khác nhau tùy cấu hình; nếu ứng dụng cần một normalized key ổn định, nên chọn policy normalization riêng và kiểm thử cùng collation của DB.

## 13. Hiệu năng: khi nào materialize, khi nào stream?

| Dữ liệu | Cách thường phù hợp | Rủi ro nếu chọn sai |
| --- | --- | --- |
| Tên/nhãn nhỏ | `setNString` / `getNString` | Rất ít, nhưng kiểm tra giới hạn cột |
| Mô tả dài vừa phải | `setNString` hoặc stream theo driver | Materialize không cần thiết |
| Nội dung rất lớn | `setNCharacterStream` / `getNCharacterStream` | Load toàn text vào heap |
| Large object national | `setNClob` / `getNClob` / stream | Quên `free()`, giữ locator sau transaction |
| Unicode text trên DB không có N-types | `setString` / `getString` hoặc `setCharacterStream` | Cố gọi unsupported API |

Streaming có thể giảm lượng memory phải cấp phát **ở phía ứng dụng**, nhưng không bảo đảm driver không buffer ở phía trong hoặc database không xử lý thêm. Với dữ liệu lớn, cần benchmark trên driver/DB/version thực tế, có test với nhiều MB và điều kiện network tương tự production.

Một số thực hành:

1. Dùng `Reader` có buffer hợp lý từ `Files.newBufferedReader(...)`.
2. Đảm bảo stream còn mở cho đến khi `executeUpdate/executeQuery` liên quan hoàn tất.
3. Đóng stream, statement, resultset trong `try-with-resources`; gọi `NClob.free()` khi không còn dùng.
4. Không giữ LOB locator vượt transaction và connection lifecycle.
5. Nếu cần copy kết quả tới file, `Reader.transferTo(Writer)` hoặc loop buffer có thể tránh `StringWriter` khổng lồ.
6. Không sử dụng `getNString` để load toàn bộ NCLOB hàng GB chỉ để tìm vài ký tự đầu.
7. Điều chỉnh fetch size/LOB prefetch theo tài liệu driver nếu đây là hot path đã được đo đạc.

### 13.1. Tránh đọc stream nhiều lần

Không phải mọi JDBC `Reader` đều reset/replay được. Nếu cần dùng lại một nội dung nhiều lần:

- Thiết kế nguồn phát lại được (file, stream factory) hoặc giữ một bản copy có chủ đích.
- Không tự giả định `markSupported() == true`.
- Không đóng stream sau bind rồi lại execute.
- Nếu statement bị retry sau lỗi mạng, cần tạo **Reader mới** trừ khi driver/source bảo đảm rewind đúng.

Đặc biệt với tác vụ ghi lớn, retry transaction có thể gây ghi trùng; cần idempotency key và chính sách recovery rõ, không chỉ “chạy lại stream”.

## 14. Kiểm tra khả năng driver, schema và dữ liệu thật

Trước khi dựa vào national APIs trong production:

1. Xác minh driver version hỗ trợ JDK 17+ và DB server hiện dùng.
2. Tạo bảng thử với national types **theo DDL của DBMS** (không dùng tên `LONGNVARCHAR` như tên cột nếu DB không hỗ trợ).
3. Chạy insert bằng `setNString` và đọc lại bằng `getNString`.
4. Chạy stream với `setNCharacterStream` và `getNCharacterStream` trên dữ liệu lớn.
5. Nếu DB có national LOB, test `createNClob/setNClob/getNClob/free`.
6. Test SQL NULL và empty string.
7. Test NCHAR padding, giới hạn length và chuỗi có supplementary characters.
8. Test emoji, chữ Việt có dấu, Japanese/Han characters và combining marks.
9. Test SQL injection được ngăn bằng parameter binding, không xây SQL từ input.
10. Test transaction/rollback, cursor/LOB lifetime và cleanup khi `SQLException` xảy ra.
11. Xem `ResultSetMetaData.getColumnType/getColumnTypeName` để kiểm chứng mapping.
12. Benchmark memory/latency với văn bản dài và xác nhận driver streaming hoặc buffering.

### 14.1. Test data Unicode gợi ý

| Dữ liệu | Mục tiêu |
| --- | --- |
| `"Tiếng Việt"` | Dấu tiếng Việt, encoding/normalization |
| `"日本語"` | Hệ chữ khác Latin |
| `"🚀"` | Supplementary code point/surrogate pair |
| `"e\u0301"` | Combining mark khác composed form |
| `""` | Empty string |
| SQL NULL | Không có giá trị |
| Chuỗi có dấu cách cuối | NCHAR padding vs dữ liệu thật |
| Text lớn nhiều MB | Streaming, timeouts, memory |

Với dữ liệu so sánh/khóa, chọn canonical equivalence policy riêng; đừng chỉ assert `String.length()` mà không xem các code points.

### 14.2. Xử lý `SQLFeatureNotSupportedException`

Các API national có thể ném exception này nếu driver không hỗ trợ. Chẳng hạn:

~~~java
try {
    statement.setNClob(2, reader);
} catch (SQLFeatureNotSupportedException unsupported) {
    // Driver không hỗ trợ operation này:
    // chọn mapping được hỗ trợ trong kiến trúc, không retry mù quáng.
}
~~~

Đây là **snippet** cần import `java.sql.SQLFeatureNotSupportedException` và các biến đã khởi tạo. Đừng xem đây là tín hiệu có thể an toàn “retry bằng `setString`” với bất kỳ schema nào; nếu cột là national LOB, một cách fallback sai có thể làm hỏng conversion hoặc gây lỗi ngầm.

Hãy quyết định mapping trên **khả năng driver/schema đã kiểm thử** thay vì fallback ad hoc cho mỗi request.

## 15. Một số lưu ý với `ResultSet.updateNString/updateNClob`

JDBC cũng cung cấp các updater methods:

~~~java
result.updateNString("title_n", "Tên mới");
result.updateNClob("article_n", reader);
// Nếu ResultSet updatable và driver hỗ trợ:
result.updateRow();
~~~

Đây là snippet **chỉ dành cho ResultSet có thể update**, với driver hỗ trợ các phương thức tương ứng. `ResultSet` mặc định thường `CONCUR_READ_ONLY`; gọi updater trên resultset read-only có thể ném `SQLException`. `updateNString`/`updateNClob` không có nghĩa mọi ResultSet từ SELECT đều được update.

Trong code ứng dụng hiện đại, thường dễ rõ semantics hơn khi dùng `UPDATE ... SET ... WHERE ...` với `PreparedStatement` và parameter binding. Việc dùng updatable ResultSet chỉ hợp lý khi ứng dụng cố ý dùng contract ấy và đã kiểm thử với driver.

## 16. Phân biệt `NClob` với `Blob`, `Clob`, byte stream và SQLXML

| Interface | Loại dữ liệu | Dùng cho |
| --- | --- | --- |
| `Blob` | Nhị phân lớn | Hình ảnh, tệp binary, payload không diễn giải theo charset |
| `Clob` | Văn bản ký tự lớn của SQL character set | Text/character LOB |
| `NClob` | Văn bản ký tự lớn của **national character set** | National text LOB |
| `SQLXML` | SQL XML value | Nội dung XML với API XML chuyên biệt |
| `Reader` | Luồng ký tự Java | Dữ liệu text, không nhất thiết là LOB |
| `InputStream` | Luồng byte Java | Dữ liệu binary hoặc byte stream với charset do ứng dụng tự quản lý |

**`NClob` không phải file binary**. Đừng dùng `getBinaryStream` chỉ vì dữ liệu nhiều MB. `Reader` cho phép driver giải mã và trả ký tự Java; `InputStream` cần contract encoding riêng nếu bạn dùng để chứa text.

Nếu cột là `JSON` native hoặc `XML`, chọn API/driver mapping tương ứng thay vì mặc định dồn vào NCLOB. Với dữ liệu đa ngôn ngữ JSON, một số DB có native JSON hỗ trợ Unicode; cách lưu tối ưu có thể khác national LOB.

## 17. SQL injection và an toàn dữ liệu

Sử dụng `PreparedStatement` với placeholders và `setNString`/**`setNClob`** là cách truyền **giá trị**, tránh ghép dữ liệu người dùng trực tiếp vào câu SQL.

Không viết:

~~~java
String sql = "INSERT INTO users(name_n) VALUES (N'" + userInput + "')";
~~~

Đây là **anti-pattern**, chưa có xử lý escape và dùng cú pháp national string literal `N'...'` phụ thuộc DBMS. Nó có nguy cơ SQL injection và sai escaping. Không dựa vào ký hiệu `N` trong literal như một cách “tự động an toàn”.

Nên:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO users(name_n) VALUES (?)")) {
    ps.setNString(1, userInput);
    ps.executeUpdate();
}
~~~

Đây là snippet tích hợp DB với `Connection connection`, `userInput` và bảng đã tồn tại. Nếu DB/driver không hỗ trợ national binding, chọn loại cột/binding chuẩn hóa đã được xác nhận; **không** quay lại nối chuỗi SQL.

### 17.1. Không log dữ liệu nhạy cảm hoặc toàn bộ LOB

Một `NClob` có thể chứa tài liệu nội bộ, dữ liệu cá nhân hoặc nội dung được kiểm soát. Tránh in toàn bộ `getNString`/`getNClob` ra log; dùng ID, kích thước, checksum đã được phê duyệt hoặc metadata phục vụ chẩn đoán. Khi log lỗi driver, chú ý một số exception messages có thể chứa SQL/parameter data.

Không giữ LOB locator trong cache toàn cục hoặc truyền qua serialization của API response. Thường cần chuyển dữ liệu thành cấu trúc application-level đã xác định, hoặc stream trong response khi transaction/resource còn hợp lệ.

## 18. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Nghĩ Java có class `NString` | Hiểu sai JDBC mapping | Dùng `String` và `setNString/getNString` |
| Nghĩ tất cả DB phải có DDL `LONGNVARCHAR` | SQL syntax fail | Xem JDBC type là loại logic, map theo DB |
| Dùng SQL Server `ntext` cho schema mới | Phụ thuộc kiểu **deprecated** | Dùng `nvarchar(max)` |
| Nghĩ Unicode chỉ lưu được trong N-types | Chọn schema không cần thiết | Xem charset/mapping: PostgreSQL UTF-8 `text` |
| Gọi `setNClob` trên driver không hỗ trợ | `SQLFeatureNotSupportedException` | Dùng driver/schema có khả năng phù hợp |
| Đóng Reader trước `executeUpdate` | Stream có thể chưa được driver đọc | Giữ Reader mở tới khi execute xong |
| Truyền byte length vào overload ký tự | Sai số length / conversion | Phân biệt byte, UTF-16 units và JDBC chars |
| `getNString` cho NCLOB cực lớn | RAM/GC tăng mạnh | `getNClob/getNCharacterStream` và stream |
| Quên `NClob.free()` | LOB resource tồn tại lâu, có thể leak | `try/finally` giải phóng |
| Gọi `NClob.getCharacterStream()` sau `free()` | `SQLException` | Đọc trước, free sau |
| Giữ `NClob` sau transaction | Locator/resource không còn hợp lệ | Consume trong transaction scope |
| Cho rằng `NVARCHAR(n)` luôn cho n Unicode code points | Truncation/limit sai | Xem length semantics của DB/driver |
| Dùng `String.length()` như số glyph | Sai với emoji/composing marks | Chọn code units/code points/graphemes |
| Tự `trim` mọi `NCHAR` khi đọc | Mất whitespace có nghĩa | Có business policy padding |
| Nghĩ `NVARCHAR` tự normalize NFC | Unique keys/so sánh sai | Normalization và collation riêng |
| Dùng `updateNClob` với read-only ResultSet | `SQLException` | PreparedStatement UPDATE hoặc updatable ResultSet |
| Dùng `setUnicodeStream` cũ | API **deprecated** | `setCharacterStream`/national APIs phù hợp |
| Tạo SQL bằng cách nối input Unicode | SQL injection/encoding lỗi | Parameterized `PreparedStatement` |
| Dùng mock và tuyên bố đã test DB thật | Kết luận sai về driver | Integration test với schema/DB/driver |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `NCHAR` khác `NVARCHAR` thế nào?

**Trả lời:** `NCHAR` là national character fixed-length, có thể padding; `NVARCHAR` là variable-length. Chi tiết độ dài và comparison/padding phụ thuộc DBMS.

**Câu 2.** `LONGNVARCHAR` có bắt buộc là tên kiểu SQL của mọi database không?

**Trả lời:** Không. Đây là kiểu JDBC logic. DBMS có thể dùng `nvarchar(max)`, `NCLOB` hoặc cách lưu khác tùy schema/driver.

**Câu 3.** Java dùng class nào để ghi national Unicode text ngắn?

**Trả lời:** Vẫn là `String`, thường bind qua `PreparedStatement.setNString(...)`; không có class `NString` chuẩn riêng.

**Câu 4.** Khi gửi một `Reader` lớn bằng `setNClob(index, reader)`, có thể đóng Reader ngay sau set nhưng trước execute không?

**Trả lời:** Không nên. Driver có thể tiêu thụ stream tại `executeUpdate()`. Giữ Reader còn mở qua execute và đóng khi hoàn tất.

**Câu 5.** `ResultSet.getNClob(...)` trả SQL NULL thì kết quả là gì?

**Trả lời:** `null`. Với non-null LOB, đọc trong lifetime hợp lệ rồi gọi `free()` để giải phóng resource.

**Câu 6.** Có thể gọi `NClob.getCharacterStream()` sau `free()` không?

**Trả lời:** Không. Object đã giải phóng có thể ném `SQLException` theo hợp đồng.

**Câu 7.** Vì sao `NClob.length()` không được tự giả định luôn bằng `String.length()` trong mọi DB?

**Trả lời:** JDBC và DBMS có khái niệm SQL character/LOB length; Java `String.length()` đếm UTF-16 code units. Test double có thể trùng, nhưng length semantics thực tế phải kiểm tra driver/DB.

**Câu 8.** PostgreSQL UTF-8 có nhất thiết dùng `NVARCHAR`/`NCLOB` mới lưu được tiếng Việt không?

**Trả lời:** Không. `varchar` và `text` trong database UTF-8 lưu Unicode. Chọn API JDBC theo driver/schema.

**Câu 9.** Khi đọc NCHAR xuất hiện dấu cách cuối, có nên `trim()` vô điều kiện không?

**Trả lời:** Không. Cần phân biệt padding của fixed-length column với whitespace hợp lệ của dữ liệu và theo business policy.

**Câu 10.** `setNString` có tự bảo vệ khỏi SQL injection không nếu mã nguồn vẫn nối giá trị vào câu SQL?

**Trả lời:** `setNString` chỉ bảo vệ khi dùng **parameter binding của PreparedStatement**. Nếu tự nối input để tạo SQL literal, injection vẫn có thể xảy ra.

**Câu 11.** Các phương thức `setNClob/getNClob` có được bảo đảm driver nào cũng hỗ trợ không?

**Trả lời:** Không. JDBC có chuẩn API nhưng driver/DB có thể không hỗ trợ national LOB và ném `SQLFeatureNotSupportedException`. Cần integration test.

**Câu 12.** Vì sao chương trình `NationalTextDemo` chạy không cần database mà không chứng minh driver của hệ thống production hoạt động?

**Trả lời:** Nó dùng dynamic proxies trong RAM để kiểm tra cách gọi API và vòng đời resource, **không có DB session/roundtrip/conversion thật**. Cần test với driver và database tương ứng.

**Tóm tắt:** `NCHAR`, `NVARCHAR`, `LONGNVARCHAR` và `NCLOB` là **kiểu national character trong JDBC**. Dùng `String` và `setNString/getNString` cho text ngắn; `Reader` và `setNCharacterStream/getNCharacterStream` cho text dài; `NClob` và `setNClob/getNClob/free` cho national LOB khi DB/driver hỗ trợ. Khác biệt SQL type logic với DDL vendor-specific, tránh kiểu deprecated như SQL Server `ntext`, quản lý stream/LOB đúng lifecycle và kiểm thử Unicode trên database thật trước khi đưa vào production.

### Tài liệu tham khảo chính thức, còn hiện hành

- [Oracle Java SE 26 — `Types`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): `NCHAR`, `NVARCHAR`, `LONGNVARCHAR`, `NCLOB`.
- [Oracle Java SE 26 — `JDBCType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/JDBCType.html): các `SQLType` enum.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setNString`, `setNCharacterStream`, `setNClob`.
- [Oracle Java SE 26 — `ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getNString`, `getNClob`, `getNCharacterStream`.
- [Oracle Java SE 26 — `Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createNClob`.
- [Oracle Java SE 26 — `NClob`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/NClob.html): national LOB, lifecycle và `free`.
- [Microsoft Learn — National Character Set Support in JDBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/jdbc/national-character-set-support): national JDBC getters/setters/updaters.
- [Microsoft Learn — Understanding Data Type Differences](https://learn.microsoft.com/en-us/sql/connect/jdbc/understanding-data-type-differences): `nchar`, `nvarchar` và tránh `ntext` deprecated.
- [PostgreSQL Documentation — Character Types](https://www.postgresql.org/docs/current/datatype-character.html): Unicode text trong `character varying` và `text`.
