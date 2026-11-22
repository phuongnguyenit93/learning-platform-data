# Các overload stream không bắt buộc truyền độ dài trong JDBC

## 1. Tại sao JDBC cần overload stream không có length?

Trong một ứng dụng Java, một giá trị SQL đôi khi là chuỗi ngắn hoặc một `byte[]` đã nằm sẵn trong bộ nhớ. Nhưng với ảnh, tệp PDF, bản ghi log, văn bản dài, dữ liệu từ pipeline hay nội dung được sinh dần, việc **đọc toàn bộ để đếm byte hoặc ký tự trước khi lưu** có thể tốn RAM, chậm hoặc không khả thi.

JDBC có thể nhận dữ liệu qua:

- `java.io.InputStream` — nguồn **bytes**: ảnh, PDF, file nhị phân; cũng có dạng bytes ASCII chuyên biệt.
- `java.io.Reader` — nguồn **ký tự Unicode đã giải mã**: dữ liệu text, CLOB/NCLOB.
- `java.sql.PreparedStatement` — bind dữ liệu vào dấu hỏi `?` của SQL.
- `java.sql.CallableStatement` — bind tham số của stored procedures/functions nếu driver và DB hỗ trợ.
- `java.sql.ResultSet` — cập nhật giá trị của các cột trong **updatable result set**.

**JDBC 4.0 (Java SE 6)** bổ sung những overload cho phép truyền stream/reader **mà không khai báo sẵn số bytes/characters**. Các API này **vẫn được hỗ trợ ở Java SE 26** và dùng được từ Java 17+.

~~~java
// Khi biết độ dài nguồn:
ps.setBinaryStream(2, input, knownByteCount);

// Khi không biết hoặc không muốn tính trước độ dài:
ps.setBinaryStream(2, input);
~~~

Đây là **đoạn trích**, các biến `ps` (PreparedStatement), `input` (InputStream) và `knownByteCount` (long) phải được cung cấp ở code gọi.

Bản thứ hai là **overload hai tham số**, không phải một tùy chọn đặc biệt cho `length=-1`. Driver có thể tiêu thụ dữ liệu cho tới **EOF**. Tuy nhiên **không có length không có nghĩa không có giới hạn, không dùng bộ đệm hoặc luôn nhanh hơn**. Driver có thể buffer toàn bộ stream tùy giao thức và implementation.

### Kết quả học tập

Sau bài này, bạn sẽ:

1. Nhận ra đúng các overload không có length trong `PreparedStatement`, `CallableStatement` và `ResultSet`.
2. Chọn `InputStream` hoặc `Reader` theo data type, SQL column type và encoding.
3. Dùng `setBinaryStream`/`setBlob` hoặc `setCharacterStream`/`setClob`/`setNClob` đúng hoàn cảnh.
4. Giữ stream mở cho tới khi driver đã thực thi xong, đóng đúng tài nguyên và xử lý lỗi.
5. Hiểu các rủi ro về EOF, timeout, nguồn vô hạn, batch, driver hỗ trợ không đầy đủ và transaction.
6. Chạy một mock JDBC test **Java 17+** và biên dịch ví dụ dùng `DataSource` thực.

## 2. Lịch sử API còn áp dụng

Các overload no-length trong `PreparedStatement` như `setAsciiStream(int, InputStream)`, `setBinaryStream(int, InputStream)`, `setCharacterStream(int, Reader)`, `setNCharacterStream(int, Reader)`, `setBlob(int, InputStream)`, `setClob(int, Reader)` và `setNClob(int, Reader)` được Oracle Javadoc ghi **Since: 1.6**, tức **Java 6/JDBC 4.0**.

| Hợp đồng | Thời điểm | Dùng hiện nay |
| --- | --- | --- |
| Các stream setters có `int length` | Đã có ở những đời JDBC trước 4.0 | Vẫn tồn tại |
| Nhiều stream setters có `long length` và **không có length** | **JDBC 4.0/Java 6** | Tiếp tục dùng trong Java hiện đại |
| JDBC `Connection/Statement/ResultSet` là `AutoCloseable` để try-with-resources | **JDBC 4.1/Java 7** | Nên dùng ở Java 17+ |
| `InputStream.readAllBytes`, `transferTo` | **Java 9+** | Hữu ích cho kiểm thử/download, không phải điều kiện của JDBC |
| `Reader.transferTo` | **Java 10+** | Hữu ích cho mock test |
| JDBC hiện hành trong Java SE 26 | JDBC 4.5 | Bao gồm những API hợp lệ từ JDBC 4.0 |

**Không dùng `PreparedStatement.setUnicodeStream` trong code mới.** Nó đã deprecated; để đưa Unicode text vào SQL, nên dùng `Reader` được giải mã đúng charset và `setCharacterStream`/`setClob` phù hợp với schema.

**Phân biệt timeline:** ví dụ Java 17+ trong bài dùng try-with-resources, nhưng không tuyên bố đây là tính năng của Java 6. Việc dùng API mới cho quản lý tài nguyên không làm thay đổi nguồn gốc JDBC 4.0 của các overload no-length.

## 3. Những overload quan trọng của PreparedStatement

| Chữ ký không có length | Nguồn | Ý nghĩa SQL |
| --- | --- | --- |
| `setAsciiStream(int, InputStream)` | Bytes ASCII | Gửi ký tự ASCII, thường cho kiểu text dài |
| `setBinaryStream(int, InputStream)` | Bytes nhị phân | Stream nhị phân tổng quát; driver ánh xạ theo kiểu SQL |
| `setCharacterStream(int, Reader)` | Ký tự Java | Stream text Unicode |
| `setNCharacterStream(int, Reader)` | Ký tự Java | Dữ liệu SQL national-character |
| `setBlob(int, InputStream)` | Bytes nhị phân | Chỉ rõ SQL `BLOB` |
| `setClob(int, Reader)` | Ký tự Java | Chỉ rõ SQL `CLOB` |
| `setNClob(int, Reader)` | Ký tự Java | Chỉ rõ SQL `NCLOB` |

Đối số `int` đầu tiên là **parameter index bắt đầu từ 1**, tương ứng thứ tự dấu `?` trong `PreparedStatement`. Không phải index 0 của mảng Java.

Ví dụ minh họa ba dạng:

~~~java
ps.setBlob(2, blobInput);                   // Không cần length.
ps.setBlob(2, blobInput, exactByteCount);   // Biết length (long).
ps.setCharacterStream(3, textReader);       // Không cần character length.
~~~

**Đây là đoạn trích**, các biến đã khai báo bên ngoài. Đừng gọi hai lời gọi `setBlob` trên cùng tham số 2 như hai phần của một insert; chúng là **các cách chọn overload khác nhau**.

### 3.1. setBinaryStream hay setBlob?

Cả hai nhận `InputStream`, nhưng mục tiêu khác nhau:

- `setBinaryStream` gửi stream nhị phân tổng quát cho các kiểu binary/long binary.
- `setBlob` nói rõ với driver rằng tham số thuộc loại SQL **BLOB**. Driver có thể tránh suy đoán kiểu và chọn cách gửi phù hợp với BLOB.
- Với cột BLOB, thường chọn `setBlob` nếu driver hỗ trợ. Với cột binary/VARBINARY có thể chọn `setBinaryStream`.
- Không có đảm bảo hiệu năng/compatibility giống nhau trên mọi database. Một driver có thể hỗ trợ phương thức này nhưng không hỗ trợ phương thức kia.

Để biết đúng mapping cần xem **SQL column type và tài liệu driver**, không suy chỉ từ Java `InputStream`.

### 3.2. setCharacterStream, setClob và setNClob

Ba overload nhận `Reader` nhưng khác SQL semantics:

- `setCharacterStream` là cách truyền text qua Reader, driver chọn mapping dựa trên schema.
- `setClob` chỉ rõ SQL CLOB.
- `setNClob` chỉ rõ SQL NCLOB; `setNCharacterStream` dành cho national-character data tương ứng.

**Tiếng Việt/emoji không bắt buộc phải dùng NClob.** Nhiều DBMS có cột text/CLOB với Unicode encoding. Chọn theo schema, driver và kiểm thử dữ liệu thật, không theo việc ký tự thuộc ngôn ngữ nào.

### 3.3. setAsciiStream chỉ dành cho ASCII

Không gửi UTF-8 có dấu/emoji qua ASCII setter chỉ vì nó cũng nhận bytes. Giả sử chuỗi `Tiếng Việt` được mã hóa UTF-8: dữ liệu có nhiều byte lớn hơn 0x7F, không còn là ASCII thuần.

Cách xử lý văn bản Unicode phù hợp:

~~~java
try (Reader reader = new java.io.StringReader("Tiếng Việt 🎯")) {
    ps.setCharacterStream(1, reader);
    ps.executeUpdate();  // Driver xử lý Reader trước khi nguồn đóng.
}
~~~

Đây là **đoạn trích**. `ps` phải còn mở và được đóng ở phạm vi ngoài. Với file UTF-8, dùng `Files.newBufferedReader(file, StandardCharsets.UTF_8)` thay vì tự chuyển sang ASCII.

### 3.4. setNull khác stream rỗng

- SQL NULL: `ps.setNull(2, java.sql.Types.BLOB)` (hoặc SQL type tương ứng).
- Stream rỗng: `ps.setBlob(2, new ByteArrayInputStream(new byte[0]))`.

Đó **không phải cùng một giá trị**. Hành vi chấp nhận zero-length BLOB/CLOB cũng phải được kiểm tra theo DBMS. Với `null` Java literal, các overload `setBlob(index, Blob)` và `setBlob(index, InputStream)` có thể gây vấn đề overload resolution; hãy dùng `setNull` cho SQL NULL.

## 4. No-length nghĩa là đọc dữ liệu từ vị trí hiện tại đến EOF

Dữ liệu stream **có trạng thái vị trí**. Sau khi bạn đọc một số bytes/chars, chúng không tự xuất hiện trở lại khi bind với JDBC.

~~~text
InputStream / Reader (vị trí hiện tại)
              |
       ps.setBlob(2, source)
              |
       ps.executeUpdate()
              |
       Driver có thể đọc/chunk/buffer
              |
              v
           Stream EOF
              |
              v
        SQL parameter value
~~~

JDBC **không cam kết driver bắt đầu đọc ở cùng một thời điểm** trong mọi implementation: một số đọc ngay lúc setter, một số đọc khi `execute/executeUpdate/executeBatch`. Vì thế code portable nên **giữ nguồn mở cho tới khi việc thực thi đã xong**.

### Quy tắc lifetime

1. Mở nguồn trước khi bind, giữ nguồn tới lúc thực thi thành công/thất bại và driver không còn cần nó.
2. Không gọi `close` ngay sau `setBlob` rồi mới `executeUpdate`.
3. Không đếm bytes bằng cách đọc một lượt rồi truyền nguồn đang ở EOF.
4. Không dùng lại cùng một stream cho hai tham số hoặc nhiều batch entries nếu không tạo nguồn mới/reset hợp lệ.
5. Application chịu trách nhiệm đóng `InputStream`/`Reader` bằng try-with-resources; không giả định driver tự đóng chúng.
6. Khi đọc dữ liệu từ `ResultSet.getBinaryStream/getCharacterStream`, xử lý khi ResultSet/Connection còn mở.
7. Stream lỗi giữa chừng phải dẫn đến xử lý error/transaction rõ, không ngầm ghi thiếu dữ liệu mà vẫn báo thành công.

**Phản ví dụ:**

~~~java
InputStream in = java.nio.file.Files.newInputStream(path);
ps.setBlob(2, in);
in.close();             // Sai: có thể đóng trước khi driver đọc.
ps.executeUpdate();
~~~

Đây là đoạn trích **cố ý sai**. `path`/`ps` do caller cung cấp. Việc có thể chạy được với driver eager-buffer không làm nó thành hợp đồng portable.

**Cách đúng:**

~~~java
try (InputStream in = java.nio.file.Files.newInputStream(path)) {
    ps.setBlob(2, in);
    ps.executeUpdate();       // Nguồn còn mở lúc thực thi.
}
~~~

Đây là đoạn trích với `ps` đang mở và được đóng ở bên ngoài. Trong code repository hoàn chỉnh ở mục 7, connection, statement và stream đều được đóng chính xác.

## 5. Java 17+ runnable: kiểm tra cả bảy overload không length

Để tập trung vào chữ ký API, ta dùng **dynamic proxy mô phỏng `PreparedStatement`**. Mock lưu đúng các nguồn được bind và chỉ đọc chúng tại `executeUpdate()`. Nó **không kết nối database**, không có SQL thật và **không chứng minh** vendor driver hỗ trợ BLOB/CLOB/NCLOB.

Lưu file `LengthlessStreamsDemo.java`:

~~~java
import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.*;

public final class LengthlessStreamsDemo {
    static final class Binding {
        final String method;
        final Object source;

        Binding(String method, Object source) {
            this.method = method;
            this.source = source;
        }
    }

    static final class FakeStatement implements InvocationHandler {
        final Map<Integer, Binding> inputs = new LinkedHashMap<>();
        final Map<Integer, Object> saved = new LinkedHashMap<>();
        boolean closed;

        PreparedStatement proxy() {
            return (PreparedStatement) Proxy.newProxyInstance(
                    PreparedStatement.class.getClassLoader(),
                    new Class<?>[]{PreparedStatement.class}, this);
        }

        @Override public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String name = method.getName();
            switch (name) {
                case "setAsciiStream":
                case "setBinaryStream":
                case "setCharacterStream":
                case "setNCharacterStream":
                case "setBlob":
                case "setClob":
                case "setNClob":
                    require(!closed, "statement closed");
                    require(args != null && args.length == 2,
                            name + " must be the no-length overload");
                    inputs.put((Integer) args[0], new Binding(name, args[1]));
                    return null;
                case "executeUpdate":
                    require(!closed, "statement closed");
                    for (Map.Entry<Integer, Binding> entry : inputs.entrySet()) {
                        Object source = entry.getValue().source;
                        Object value;
                        if (source instanceof InputStream stream) {
                            value = stream.readAllBytes();
                        } else if (source instanceof Reader reader) {
                            StringWriter writer = new StringWriter();
                            reader.transferTo(writer);
                            value = writer.toString();
                        } else {
                            throw new SQLFeatureNotSupportedException("Unknown source");
                        }
                        saved.put(entry.getKey(), value);
                    }
                    return 1;
                case "close": closed = true; return null;
                case "isClosed": return closed;
                default:
                    throw new SQLFeatureNotSupportedException("Fixture: " + name);
            }
        }
    }

    static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        byte[] binary = {0, 1, (byte) 255, 10};
        String unicode = "Tiếng Việt 🎯";
        FakeStatement fake = new FakeStatement();

        try (PreparedStatement ps = fake.proxy();
             InputStream raw = new ByteArrayInputStream(binary);
             InputStream blob = new ByteArrayInputStream(binary);
             Reader text = new StringReader(unicode);
             Reader clob = new StringReader(unicode);
             InputStream ascii = new ByteArrayInputStream(
                     "ASCII only".getBytes(StandardCharsets.US_ASCII));
             Reader national = new StringReader(unicode);
             Reader nclob = new StringReader(unicode)) {
            ps.setBinaryStream(1, raw);
            ps.setBlob(2, blob);
            ps.setCharacterStream(3, text);
            ps.setClob(4, clob);
            ps.setAsciiStream(5, ascii);
            ps.setNCharacterStream(6, national);
            ps.setNClob(7, nclob);
            require(ps.executeUpdate() == 1, "executeUpdate");
        }

        require(fake.inputs.size() == 7, "wrong number of overloads");
        require(Arrays.equals(binary, (byte[]) fake.saved.get(1)), "binary");
        require(Arrays.equals(binary, (byte[]) fake.saved.get(2)), "blob");
        require(unicode.equals(fake.saved.get(3)), "character");
        require(unicode.equals(fake.saved.get(4)), "clob");
        require("ASCII only".equals(new String((byte[]) fake.saved.get(5),
                StandardCharsets.US_ASCII)), "ascii");
        require(unicode.equals(fake.saved.get(6)), "ncharacter");
        require(unicode.equals(fake.saved.get(7)), "nclob");
        require(fake.closed, "PreparedStatement not closed");

        System.out.println("no-length-setters=" + fake.inputs.size());
        System.out.println("binary-bytes=" + ((byte[]) fake.saved.get(1)).length);
        System.out.println("blob-bytes=" + ((byte[]) fake.saved.get(2)).length);
        System.out.println("character-utf16-units=" + unicode.length());
        System.out.println("clob-text=" + fake.saved.get(4));
        System.out.println("ascii-text=" + new String(
                (byte[]) fake.saved.get(5), StandardCharsets.US_ASCII));
        System.out.println("national-text=" + fake.saved.get(6));
        System.out.println("nclob-text=" + fake.saved.get(7));
        System.out.println("statement-closed=" + fake.closed);
        System.out.println("tests=PASS");
    }
}
~~~

### 5.1. Chạy ví dụ

~~~bash
javac -encoding UTF-8 --release 17 LengthlessStreamsDemo.java
java LengthlessStreamsDemo
~~~

**Stdout chính xác** đã chạy trên OpenJDK 24 với `--release 17`:

~~~text
no-length-setters=7
binary-bytes=4
blob-bytes=4
character-utf16-units=13
clob-text=Tiếng Việt 🎯
ascii-text=ASCII only
national-text=Tiếng Việt 🎯
nclob-text=Tiếng Việt 🎯
statement-closed=true
tests=PASS
~~~

### 5.2. Vì sao mock vẫn có giá trị?

- Dòng `no-length-setters=7` cộng assertions kiểm tra **bảy setters nhận đúng hai đối số** (`parameterIndex` + nguồn).
- `binary` lưu đúng 4 bytes, kể cả 0 và 255; không có text conversion.
- Giá trị Unicode `Tiếng Việt 🎯` được kiểm tra bằng `String.equals`. `unicode.length()==13` là **UTF-16 code units**, không phải UTF-8 bytes hoặc số graphemes.
- ASCII được đọc theo `StandardCharsets.US_ASCII`.
- Mock chỉ đọc nguồn tại lúc `executeUpdate`, minh họa rõ lý do không nên đóng sớm.
- `statement-closed=true` chứng minh try-with-resources gọi `close()`.

**Giới hạn bắt buộc ghi nhớ:** mock cố tình dùng `InputStream.readAllBytes` và `Reader.transferTo` để dễ assert, **không phải gợi ý đọc hết BLOB production vào RAM**. Driver thật có thể gửi chunks hoặc buffer theo chiến lược khác. Không có database, transaction, SQL schema, mạng hay vendor-specific error trong test này.

## 6. InputStream, Reader và số byte so với số ký tự

Với file UTF-8:

~~~text
File bytes (UTF-8)  -- Files.newBufferedReader(file, UTF_8) --> Reader
                                      |
                                      v
                             setCharacterStream / setClob
                                      |
                                      v
                           SQL text column (driver mapping)
~~~

Các khái niệm cần phân biệt:

| Cách đo | Đếm cái gì? | Có dùng làm length cho InputStream? |
| --- | --- | --- |
| `Files.size(path)` | **Bytes** của file | Có thể, nếu file ổn định và length contract tính bằng byte |
| `String.length()` | **UTF-16 code units** | Không |
| `String.codePointCount(...)` | Unicode code points | Không |
| `Reader` đọc ký tự Java | Characters/chars từ Reader | Không tương đương byte count |
| `InputStream.available()` | Ước lượng bytes có thể đọc ngay không block | **Không phải tổng số byte** |
| Grapheme clusters | Ký tự người dùng nhìn thấy | Không phải length JDBC |

Ví dụ `Tiếng Việt 🎯` có emoji ngoài BMP nên `String.length()` có thể khác số code points; số bytes UTF-8 còn khác nữa. **Không dùng `Files.size(path)` làm `length` cho `setCharacterStream(..., Reader, long)`** trên văn bản UTF-8.

Overload không length giúp tránh phép đếm sai hoặc phải đọc trước nguồn chỉ để tính length. Tuy nhiên nếu driver tối ưu nhờ length và biết length chính xác, vẫn có thể chọn overload có length theo `InputStream` byte count hoặc `Reader` character count đúng contract.

### 6.1. Không tự dùng available() để truyền length

~~~java
int wrongLength = input.available(); // Không phải tổng số byte trong stream.
ps.setBinaryStream(1, input, wrongLength);
~~~

Đây là **đoạn phản ví dụ**. `available()` không trả total length và có thể là 0 với stream vẫn còn data. Với nguồn không biết length, dùng no-length overload khi driver hỗ trợ.

### 6.2. ASCII không thay thế UTF-8

Một `InputStream` có bytes UTF-8 chứa tiếng Việt **không phải** stream ASCII. Nếu muốn lưu văn bản:

~~~java
try (Reader reader = java.nio.file.Files.newBufferedReader(
        file, java.nio.charset.StandardCharsets.UTF_8)) {
    ps.setCharacterStream(1, reader);
    ps.executeUpdate();
}
~~~

Đây là **đoạn trích**; `ps` phải được khai báo/đóng bên ngoài. Nếu muốn lưu **đúng những bytes UTF-8 gốc** mà không chuyển đổi text, dùng binary column và `setBinaryStream/setBlob`, với khác biệt rằng cột sẽ không mang semantics của SQL text.

### 6.3. National character type không mặc định cần thiết

`setNCharacterStream` và `setNClob` phù hợp với cột national types khi DB/driver hỗ trợ. Nhiều DB hiện đại dùng UTF-8 hoặc Unicode native cho text/CLOB thường. Hãy xem schema, tài liệu driver và kiểm thử. **Không biến lời khuyên “hỗ trợ tiếng Việt” thành “bắt buộc setNClob”**.

## 7. Ví dụ repository sử dụng DataSource và file thật

`RealStreamRepository` là code production-oriented sử dụng những API JDBC còn hỗ trợ. Nó:

- Upload tệp binary bằng `setBlob(index, InputStream)` không length.
- Upload tệp UTF-8 đã giải mã bằng `setClob(index, Reader)` không length.
- Download BLOB bằng `ResultSet.getBinaryStream` khi cursor đang mở.

**Chú ý:** ví dụ chỉ **biên dịch**, không thể thực thi SQL nếu chưa có `DataSource` của vendor và schema phù hợp. `documents(id, payload)` phải có một cột kiểu BLOB tương thích; `notes(id, body)` phải có cột CLOB/text tương thích. DDL cụ thể tùy DBMS.

File `RealStreamRepository.java`:

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.util.Objects;
import javax.sql.DataSource;

public final class RealStreamRepository {
    private final DataSource source;

    public RealStreamRepository(DataSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public int uploadBlob(long id, Path path) throws SQLException, IOException {
        try (Connection c = source.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "INSERT INTO documents(id, payload) VALUES (?, ?)");
             InputStream in = Files.newInputStream(path)) {
            ps.setLong(1, id);
            ps.setBlob(2, in);       // JDBC 4.0, no declared length
            return ps.executeUpdate();
        }
    }

    public int uploadClob(long id, Path path) throws SQLException, IOException {
        try (Connection c = source.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "INSERT INTO notes(id, body) VALUES (?, ?)");
             Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            ps.setLong(1, id);
            ps.setClob(2, reader);   // JDBC 4.0, no character length
            return ps.executeUpdate();
        }
    }

    public void downloadBlob(long id, Path destination)
            throws SQLException, IOException {
        try (Connection c = source.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT payload FROM documents WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new SQLException("Document not found");
                try (InputStream in = rs.getBinaryStream("payload")) {
                    if (in == null) throw new SQLException("Payload is SQL NULL");
                    try (OutputStream out = Files.newOutputStream(destination)) {
                        in.transferTo(out);
                    }
                }
            }
        }
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 --release 17 RealStreamRepository.java
~~~

**Đã biên dịch thành công bằng OpenJDK 24 với `--release 17`.** Tệp không có `main`; **không có stdout cố định** và không tuyên bố đã kiểm thử với database thật.

### 7.1. Thứ tự đóng tài nguyên

Với:

~~~java
try (Connection c = source.getConnection();
     PreparedStatement ps = c.prepareStatement(sql);
     InputStream in = Files.newInputStream(path)) {
    ps.setBlob(2, in);
    ps.executeUpdate();
}
~~~

Java đóng theo thứ tự ngược **in → ps → c**, sau khi method body đã kết thúc. Vì vậy nguồn còn mở lúc execute. Nếu `source` là DataSource có pool, `c.close()` có thể trả logical connection về pool thay vì đóng physical socket; không giữ nó sau scope.

Đây là đoạn trích, `source`/`sql`/`path` đến từ caller. Ở production, hạn chế quyền đọc file và kích thước payload, kiểm soát exceptions/transaction và timeout.

### 7.2. Download cần xử lý khi ResultSet còn mở

`ResultSet.getBinaryStream("payload")` trả `InputStream` phụ thuộc ResultSet/Connection. Không được trả stream đó từ repository sau khi đóng cursor. Phải đọc hết khi `ResultSet` còn mở; đó là lý do code `downloadBlob` dùng nested try-with-resources.

Khi `getBinaryStream` trả `null`, cột có thể là SQL NULL. Khi `rs.next()==false`, không có hàng. Hai trạng thái này khác nhau.

**An toàn file đích:** `Files.newOutputStream(destination)` mặc định có thể tạo hoặc truncate file. Code sản phẩm cần xác thực đường dẫn, quyền ghi, chính sách không ghi đè và sử dụng temp file/atomic publish khi download lớn có thể bị ngắt giữa chừng.

### 7.3. Cần cùng một transaction nếu có nhiều insert

Hai methods upload trong ví dụ mỗi method tự lấy một Connection và dùng transaction behavior mặc định; **không phải một giao dịch chung cho cả hai**. Nếu nghiệp vụ cần ghi đồng thời tài liệu, metadata và log thành một transaction, truyền một Connection/transaction context chung theo thiết kế hoặc dùng transaction manager. Xử lý commit/rollback trước khi close và bảo đảm idempotency khi retry.

## 8. CallableStatement và ResultSet cũng có overload no-length

### 8.1. CallableStatement theo tên tham số

`CallableStatement` kế thừa `PreparedStatement`. Ngoài các setter theo index, nó có các overload nhận **String parameterName**, ví dụ:

| CallableStatement | Ý nghĩa |
| --- | --- |
| `setAsciiStream(String, InputStream)` | ASCII |
| `setBinaryStream(String, InputStream)` | Binary |
| `setCharacterStream(String, Reader)` | Text |
| `setNCharacterStream(String, Reader)` | National character text |
| `setBlob(String, InputStream)` | BLOB |
| `setClob(String, Reader)` | CLOB |
| `setNClob(String, Reader)` | NCLOB |

Named parameters có được hỗ trợ hay không còn tùy driver/stored procedure. Không tự suy rằng mọi DB hỗ trợ tên tham số và mọi overload có semantics như nhau.

### 8.2. ResultSet.update... với index hoặc column label

Với **updatable ResultSet** có thể dùng `updateAsciiStream`, `updateBinaryStream`, `updateCharacterStream`, `updateNCharacterStream`, `updateBlob`, `updateClob` và `updateNClob` **không truyền length**. Đối số đầu tiên là column index (`int`) hoặc column label (`String`).

Khác với binding `PreparedStatement`, cập nhật qua cursor cần ResultSet được tạo **CONCUR_UPDATABLE**, cursor ở hàng hợp lệ và gọi `updateRow()` (hoặc `insertRow()` khi thêm hàng) để ghi thay đổi. `DatabaseMetaData.supportsResultSetConcurrency(type, mode)` có thể hướng dẫn feature gate, nhưng SQL query cụ thể/driver vẫn có thể không cho update.

Đừng gọi `rs.updateBlob("payload",stream)` rồi đóng ResultSet mà bỏ `updateRow()` và cho rằng dữ liệu đã lưu. Nếu updatable cursors khó portable, dùng SQL `UPDATE ... WHERE id = ?` qua `PreparedStatement` với parameterized SQL thường dễ quản lý hơn.

### 8.3. File compile-only kiểm tra hai họ API

Tệp `MoreStreamOverloads.java`:

~~~java
import java.io.InputStream;
import java.io.Reader;
import java.sql.*;

public final class MoreStreamOverloads {
    public static void bindNamed(CallableStatement cs, InputStream bytes,
                                 Reader text) throws SQLException {
        cs.setAsciiStream("ascii_param", bytes);
        cs.setBinaryStream("binary_param", bytes);
        cs.setCharacterStream("text_param", text);
        cs.setNCharacterStream("national_param", text);
        cs.setBlob("blob_param", bytes);
        cs.setClob("clob_param", text);
        cs.setNClob("nclob_param", text);
    }

    public static void updateCursor(ResultSet rs, InputStream bytes,
                                    Reader text) throws SQLException {
        rs.updateAsciiStream("ascii_column", bytes);
        rs.updateBinaryStream("binary_column", bytes);
        rs.updateCharacterStream("text_column", text);
        rs.updateNCharacterStream("national_column", text);
        rs.updateBlob("blob_column", bytes);
        rs.updateClob("clob_column", text);
        rs.updateNClob("nclob_column", text);
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 --release 17 MoreStreamOverloads.java
~~~

**PASS** khi biên dịch bằng OpenJDK 24 với `--release 17`. **Không có `main()`, không gọi stored procedure và không dùng database thật.**

**Đặc biệt quan trọng:** file này **cố tình dùng lại cùng stream/reader cho nhiều setters chỉ để compiler xác nhận chữ ký**, không phải một workflow thực thi hợp lệ. Trong production, hãy truyền **nguồn độc lập, còn mở và đúng vị trí** cho từng tham số/cột. Không áp dụng `executeBatch()/updateRow()` cho fixture trên vì cùng stream dễ bị tiêu thụ nhiều lần.

### 8.4. Đọc từ ResultSet khác cập nhật bằng ResultSet

~~~text
Ghi bằng PreparedStatement:
InputStream/Reader -> set... -> executeUpdate() -> Database

Ghi bằng updatable ResultSet:
InputStream/Reader -> update... -> updateRow() -> Database

Đọc dữ liệu:
Database -> ResultSet.getBinaryStream()/getCharacterStream()
         -> InputStream/Reader -> ứng dụng / file
~~~

`ResultSet.getBinaryStream` và `getCharacterStream` đã là **getter không yêu cầu length**; đừng nhầm chúng với no-length setter overloads được bổ sung trong JDBC 4.0.

## 9. Có length hay không: chọn theo khả năng driver và workload

Oracle Javadoc lưu ý rằng **driver đôi khi hoạt động hiệu quả hơn khi biết length**. Ví dụ với file nhị phân ổn định:

~~~java
long byteCount = java.nio.file.Files.size(path);
try (InputStream in = java.nio.file.Files.newInputStream(path)) {
    ps.setBinaryStream(2, in, byteCount);
    ps.executeUpdate();
}
~~~

Đây là đoạn trích, `ps` là PreparedStatement còn mở. Truyền length đáng tin có thể giúp driver pre-allocate hoặc chọn giao thức thuận lợi, nhưng **file có thể thay đổi** giữa `Files.size` và lúc đọc, nên cần điều kiện nguồn bất biến hoặc kiểm tra integrity.

### 9.1. Khi không biết length

Dùng no-length overload nếu driver hỗ trợ:

~~~java
ps.setBlob(2, input);
ps.executeUpdate();
~~~

Nguồn có thể đến từ producer/pipe hoặc Reader sau decode UTF-8; đừng chỉ vì muốn có length mà đọc hết vào `byte[]`, `String` hoặc temp file không cần thiết.

### 9.2. Nhưng no-length không bảo đảm tiết kiệm bộ nhớ

Driver có thể:

- Buffer toàn bộ nguồn để tính length.
- Gửi chunks nếu database protocol cho phép.
- Dùng file tạm trong JVM/driver/server.
- Chuyển đổi encoding giữa Reader/SQL text column.
- Không hỗ trợ overload và ném `SQLFeatureNotSupportedException`.
- Có performance khác nhau giữa `setBlob` và `setBinaryStream`.

**Không khẳng định “no-length = zero-copy” hay “luôn nhanh hơn”.** Benchmark driver thật với payload lớn, đo heap, native memory, disk temp, network throughput, latency và giới hạn LOB DB.

### 9.3. Dữ liệu nhỏ có thể dùng setString/setBytes

Với dữ liệu nhỏ đã có trong RAM, `setString` hoặc `setBytes` thường đơn giản hơn. Không bắt buộc tạo `StringReader`/`ByteArrayInputStream` cho vài ký tự chỉ để dùng stream overload. Chọn theo schema/driver và ràng buộc memory.

## 10. Bảo mật, giới hạn kích thước và lỗi stream

### 10.1. Unknown length không được biến thành unlimited upload

Đối với nguồn không tin cậy, cần:

1. Giới hạn kích thước theo nghiệp vụ, ngay ở HTTP/file ingestion và có cơ chế cắt/abort nếu stream vượt mức.
2. Quota số uploads/tenant và giới hạn concurrency.
3. Timeout theo từng tầng (source I/O, DB statement, connection, network), không giả định JDBC query timeout tự ngắt mọi InputStream.
4. Kiểm tra loại dữ liệu, content, schema và quyền đọc file; đừng chỉ tin filename/Content-Type.
5. Lưu checksum/hash hoặc đếm bytes đã thực sự gửi khi cần bảo đảm toàn vẹn.
6. Atomic publish/transaction/rollback và xử lý idempotency nếu upload bị gián đoạn.
7. Tránh log BLOB contents, PII, secrets hoặc JDBC credentials.
8. Giới hạn file temp nếu driver hoặc application phải spool dữ liệu.

### 10.2. IOException và SQLException

- `Files.newInputStream/newBufferedReader` có thể ném `IOException` ngay khi mở.
- Stream có thể ném `IOException` giữa chừng. Driver có thể bọc lỗi nguồn thành `SQLException` với cause.
- Driver/DB có thể ném `SQLException` do data type, length, quota, connection, SQL hoặc transaction.
- Overload không hỗ trợ có thể ném `SQLFeatureNotSupportedException`.

**Không nuốt lỗi:**

~~~java
try {
    ps.setNClob(1, reader);
} catch (java.sql.SQLFeatureNotSupportedException ignored) {
    // SAI: bỏ qua lỗi rồi vẫn execute có thể ghi dữ liệu sai/thiếu.
}
ps.executeUpdate();
~~~

Đây là phản ví dụ, không phải source file độc lập. Nếu cần tính năng national CLOB mà driver không hỗ trợ, hãy chọn một fallback **được đặc tả và kiểm thử với đúng schema**, hoặc trả lỗi rõ ràng.

### 10.3. EOF sớm hoặc stream đã tiêu thụ

No-length setter đọc đến EOF. Nếu file bị rút ngắn hoặc stream đã đọc mất phần đầu, JDBC không thể biết “đáng lẽ còn 20 MB” nếu application không cung cấp contract khác. Với uploads quan trọng, so sánh expected size/checksum, xác nhận dữ liệu **đọc lại** từ database.

Nếu chương trình upload thành công nhưng downstream phát hiện hash khác, đừng chỉ tin `executeUpdate()==1`; kiểm tra dữ liệu thật và cleanup/rollback theo transaction.

### 10.4. Không tái sử dụng stream cho executeBatch

`PreparedStatement` có thể giữ nhiều batch entries đến `executeBatch`. Một stream duy nhất có thể đã ở EOF khi driver đọc entry thứ hai. Hãy tạo **nguồn mới** cho từng record, đảm bảo lifetime đến lúc driver tiêu thụ, hoặc tổ chức batch theo dữ liệu nhỏ. Không giả định `mark/reset` luôn hỗ trợ.

### 10.5. File đầu ra khi download

`Files.newOutputStream(destination)` mặc định có thể **tạo hoặc truncate** file, và nếu download thất bại file có thể chỉ chứa một phần. Với nội dung quan trọng, tải vào **file tạm**, kiểm tra checksum, sau đó publish/rename khi hoàn chỉnh. Kiểm soát path traversal và quyền file.

## 11. Kế hoạch kiểm thử với vendor database

Mock ở mục 5 kiểm tra Java signatures; để xác nhận behavior thật, cần database và JDBC driver chính thức/còn được hỗ trợ.

| Test | Mục đích |
| --- | --- |
| **Binary round-trip** | Upload bytes 0, 255, random, download rồi so SHA-256 |
| **Unicode round-trip** | Tiếng Việt, emoji, combining marks qua Reader/CLOB |
| **Empty vs SQL NULL** | Stream độ dài 0 khác `setNull` |
| **Driver support** | `setBlob/setClob/setNClob` và `SQLFeatureNotSupportedException` |
| **Length known vs unknown** | Cùng payload, đo latency/memory và kiểm tra dữ liệu |
| **Source I/O failure** | Stream ném IOException giữa chừng: lỗi, rollback, cleanup |
| **Very large payload** | Đo heap, file temp, disk quota, statement/network timeouts |
| **Updatable ResultSet** | `update...` + `updateRow()` + SELECT đọc lại |
| **Batch** | Nguồn độc lập theo entry, exception/partial update handling |
| **Transactions** | Commit/rollback nhiều uploads liên quan, retry idempotent |
| **Download** | `getBinaryStream`/`getCharacterStream` trong ResultSet lifetime |
| **Security** | Max size, quyền đọc/ghi path, concurrent upload quotas |

### 11.1. Phân biệt test mock và integration

- `LengthlessStreamsDemo`: **đã thực thi**, assert bảy overload và dữ liệu mock.
- `RealStreamRepository`: **đã biên dịch**, code cần vendor database và schema mới chạy SQL.
- `MoreStreamOverloads`: **đã biên dịch**, chỉ kiểm chứng chữ ký `CallableStatement` và `ResultSet`.
- **Không có kết quả database round-trip được tạo trong bài này**; không dùng mock để khẳng định driver hỗ trợ stream zero-copy hay SQL NCLOB.

### 11.2. Không chỉ assert số hàng cập nhật

`executeUpdate()==1` không chứng minh payload không bị sai charset, truncation hoặc conversion. Hãy `SELECT` lại, dùng `ResultSet.getBinaryStream()/getCharacterStream()`, kiểm tra content/hash và SQL NULL vs stream rỗng.

## 12. Lỗi phổ biến

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` | Driver chưa hỗ trợ no-length/national type | Driver docs, đúng schema, fallback được test |
| Text tiếng Việt bị lỗi | Dùng ASCII setter hoặc Reader decode sai | `Reader` với UTF-8 và column Unicode tương thích |
| Upload rỗng | Stream đã đọc đến EOF trước khi bind | Mở nguồn mới/giữ position đúng |
| Lỗi "stream closed" lúc execute | Nguồn đóng sau setter | Đóng sau execute bằng try-with-resources |
| Upload lớn tăng RAM | Driver buffer unknown-length value | Đo thực tế, đặt giới hạn, cân nhắc length-known overload |
| Length sai | Dùng `available()` hoặc byte size cho Reader | Dùng đúng metric hoặc no-length |
| BLOB bị hỏng | Chuyển bytes qua String | Giữ binary InputStream/SQL type |
| CLOB tiếng Việt không đúng | Charset/DB conversion không phù hợp | `Files.newBufferedReader(..., UTF_8)` và test DB |
| Update ResultSet không thay đổi DB | Chưa gọi `updateRow`, cursor read-only | Dùng updatable cursor hoặc SQL UPDATE |
| Batch ghi dữ liệu lặp/rỗng | Reuse một stream | Nguồn riêng cho mỗi batch entry |
| ResultSet stream bị đóng sớm | Đóng ResultSet/connection trước khi đọc xong | Tiêu thụ trong scope đang mở |
| SQL NULL nhầm với empty | Dùng stream rỗng cho giá trị null | `setNull` theo column type |
| Upload thiếu mà vẫn được báo thành công | EOF sớm, không kiểm tra hash | Kích thước, hash, readback |
| Gọi `setNClob` vì text tiếng Việt | Nhầm Unicode với national SQL type | Chọn theo schema/driver, thường CLOB/text đủ |
| Mock PASS bị coi là chứng minh DB | Mock không gửi SQL | Vendor integration test |
| Nói try-with-resources là Java 6 | JDBC 4.1/Java 7 mới hỗ trợ | Giải thích đúng timeline |
| Code dùng `setUnicodeStream` | API deprecated | Thay bằng Reader-based methods |

## 13. Câu hỏi tự đánh giá

**1.** `setBlob(index, InputStream)` khác `setBlob(index, InputStream, long)`? — Một bản không cần caller cung cấp độ dài, bản còn lại có byte count. Driver có thể tối ưu tốt hơn khi biết length.

**2.** Có thể lấy `Files.size(file)` làm length của `Reader` UTF-8? — Không: đó là bytes, không phải characters. Dùng no-length Reader overload hoặc tính đúng characters.

**3.** `setAsciiStream` có thể thay mọi `setCharacterStream` không? — Không: ASCII không phải Unicode/UTF-8 tổng quát. Text có dấu/emoji nên dùng Reader và SQL text column phù hợp.

**4.** Vì sao phải giữ stream mở đến `executeUpdate`? — Driver có thể tiêu thụ nguồn vào lúc execute; đóng sau setter có thể làm đọc lỗi hoặc thiếu dữ liệu.

**5.** `setBlob` và `setBinaryStream` giống nhau hoàn toàn không? — Không. `setBlob` báo SQL BLOB, `setBinaryStream` là binary generic; mapping/hiệu năng có thể khác theo driver.

**6.** `setNClob` luôn cần thiết cho tiếng Việt? — Không. Tùy SQL column type/driver, nhiều DB lưu Unicode đúng với CLOB/text thông thường.

**7.** `ResultSet.updateBinaryStream` tự lưu row ngay không? — Không; cần updatable ResultSet, cursor hợp lệ và `updateRow`/`insertRow` theo mode, cùng transaction xử lý đúng.

**8.** Unknown length có nghĩa được upload vô hạn? — Không. Application phải giới hạn bytes, timeout/quota và kiểm tra integrity.

**9.** Stream rỗng có giống SQL NULL? — Không. SQL NULL cần `setNull` hoặc API null tương ứng.

**10.** Một InputStream có thể dùng lại cho hai executions? — Không portable. Sau tiêu thụ nó có thể ở EOF; mở lại/tạo nguồn độc lập.

**11.** Vì sao `LengthlessStreamsDemo` PASS không chứng minh PostgreSQL/MySQL hỗ trợ `NCLOB`? — Vì đó chỉ là dynamic proxy mock tự đọc nguồn, không có driver/database.

**12.** Tại sao Javadoc vẫn đề cập overload có length? — Vì driver đôi khi hiệu quả hơn khi biết length; nên so sánh theo driver/schema/workload thực.

### Bài tập

1. Thêm dữ liệu nhị phân 1 MiB vào mock, assert đủ bytes và không qua character encoding.
2. Dùng `"Cộng hòa Việt Nam 🌏"`, so sánh UTF-8 bytes, UTF-16 units và code points; thử Reader no-length.
3. Cho stream đọc mất n bytes trước khi bind, quan sát dữ liệu mock chỉ còn phần còn lại.
4. Thiết kế `InputStream` có giới hạn bytes/timeout để bảo vệ upload nguồn không tin cậy.
5. Với database sandbox, upload BLOB rồi download và đối chiếu SHA-256.
6. Upload CLOB tiếng Việt + emoji và kiểm tra text round-trip.
7. Benchmark no-length vs length-known overload khi file không đổi.
8. Thử DB không hỗ trợ `NCLOB` và xử lý feature unsupported đúng.
9. Dùng ResultSet updatable nếu vendor hỗ trợ, update stream + updateRow rồi SELECT lại.
10. Thử SQL NULL khác empty BLOB, kiểm tra với `ResultSet.wasNull()`.

## 14. Tài liệu chính thức còn áp dụng

- [Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): mọi overload no-length, length-known, BLOB/CLOB và lưu ý hiệu suất theo driver.
- [Java SE 26 — CallableStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/CallableStatement.html): các overload theo tên tham số.
- [Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `update...` no-length và `getBinaryStream/getCharacterStream`.
- [Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): lifecycle, transaction và statement creation.
- [Java SE 26 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): capability của updatable ResultSet.
- [Java SE 26 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): hợp đồng unsupported.
- [Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, exception chaining.
- [Java SE 26 — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): connection factory phổ biến.
- [Java SE 26 — java.sql package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): lịch sử các đời JDBC.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): tham chiếu nguồn cho `javac --release 17`.
- [Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `newInputStream`, `newBufferedReader`, `size`.
- [Java SE 26 — InputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html): `available`, `transferTo` và stream lifecycle.
- [Java SE 26 — Reader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Reader.html): ký tự Java, `transferTo`.

**Ghi nhớ:** Overload JDBC **không bắt buộc truyền độ dài** là một công cụ cho việc bind `InputStream`/`Reader` vào SQL khi byte/character count chưa biết. Chọn method theo **loại dữ liệu/SQL column**, giữ nguồn mở qua execution, đóng tài nguyên đúng, giới hạn upload và xử lý lỗi. Không coi “không truyền length” là lời hứa không buffer hoặc hỗ trợ mọi database; hãy thực hiện **round-trip integration test** trên driver/DBMS cụ thể.
