# JDBC dữ liệu: Tạo Blob, Clob, NClob từ Connection

## Mục tiêu học tập

Trong ứng dụng Java kết nối cơ sở dữ liệu, một trường có thể chứa hình ảnh, file PDF, văn bản dài hoặc dữ liệu ký tự theo bộ chữ quốc gia. JDBC cung cấp các đối tượng **LOB (Large Object)** và ba factory methods trên `java.sql.Connection` để tạo chúng:

- `Connection.createBlob()` → một `java.sql.Blob` rỗng cho **binary large object**.
- `Connection.createClob()` → một `java.sql.Clob` rỗng cho **character large object**.
- `Connection.createNClob()` → một `java.sql.NClob` rỗng cho **national character large object**.

Sau bài này, bạn có thể:

1. Phân biệt **BLOB**, **CLOB**, **NCLOB** và quyết định khi nào cần từng kiểu SQL/JDBC.
2. Nắm cơ chế factory: đối tượng mới **chưa chứa dữ liệu**, phải ghi dữ liệu rồi liên kết với câu SQL thích hợp; chỉ gọi `create...` **không tự tạo một hàng trong database**.
3. Ghi dữ liệu bằng `Blob.setBytes(...)`/`setBinaryStream(...)`, `Clob.setString(...)`/`setCharacterStream(...)` và các phương thức tương ứng được `NClob` kế thừa.
4. Đọc dữ liệu bằng `getBytes(...)`, `getBinaryStream()`, `getSubString(...)` và `getCharacterStream()`; chú ý **vị trí SQL LOB bắt đầu từ 1**.
5. Sử dụng `PreparedStatement.setBlob`, `setClob` và `setNClob` khi driver và SQL schema hỗ trợ, thay vì ghép nội dung lớn vào câu lệnh SQL.
6. Quản lý **transaction, vòng đời LOB, tài nguyên stream, `free()` và `SQLException`**, phân biệt hành vi của các driver.
7. Biết sự khác biệt hiện hành quan trọng: từ **JDK 26**, `Blob`, `Clob`, `NClob` tham gia `AutoCloseable`, có `close()`; code tương thích Java 17–25 vẫn dùng `free()`.
8. Biên dịch/chạy một chương trình **Java 17+ tự chứa** mô phỏng `Connection` bằng dynamic proxy để kiểm thử cả ba factory methods, dữ liệu tiếng Việt, stream và giải phóng LOB, không đòi cài một database.

**Phạm vi:** nhóm *JDBC dữ liệu*. Chỉ trình bày API còn được hỗ trợ hiện nay; không khuyến nghị các giải pháp hoặc kiến thức đã lỗi thời. Các ví dụ được đối chiếu với Javadoc Java SE 26 và giữ tính tương thích Java 17 khi được nêu là runnable Java 17+.

## 1. LOB là gì và có những dạng nào?

LOB là cơ chế biểu diễn **dữ liệu lớn** trong cơ sở dữ liệu. Về phía Java, `java.sql.Blob`, `Clob` và `NClob` là **interfaces**, không phải các class mà bạn thường gọi constructor trực tiếp.

| Giao diện Java | Kiểu SQL tương ứng | Nội dung | Ví dụ |
| --- | --- | --- | --- |
| `Blob` | `BLOB` | **Dãy byte**; không áp một charset lên nội dung | File ảnh, chữ ký số dạng byte, file nén, dữ liệu nhị phân |
| `Clob` | `CLOB` | **Chuỗi ký tự** dài | Nội dung bài viết, văn bản lớn, XML/text lưu ở cột CLOB |
| `NClob` | `NCLOB` | **Chuỗi ký tự** dài theo **national character set** của database | Trường NCLOB mà schema/driver hỗ trợ, ví dụ một số hệ DB tách national character types |

`NClob` **extends `Clob`**, nên có các thao tác character như `setString`, `setCharacterStream` và `getCharacterStream`. Nó không phải kiểu mới chỉ dùng cho tiếng Việt; **có cần NCLOB hay không phụ thuộc schema, database và driver**.

### 1.1. BLOB không tự hiểu UTF-8

`Blob` là dãy byte; JDBC không tự mặc định những byte ấy là UTF-8 text. Nếu nội dung là ảnh hoặc PDF, nên giữ nguyên bytes, không chuyển bừa qua `String`.

```java
byte[] bytes = {0x00, (byte) 0xFE, 0x41};
// Dãy byte nhị phân, không phải văn bản.
```

Đây là đoạn khai báo mẫu trong method; `(byte) 0xFE` biểu diễn một byte có bit pattern FE bất kể khi Java hiển thị signed byte thì giá trị số là âm.

### 1.2. CLOB lưu ký tự, không phải “byte[] dài”

`Clob` là nội dung dạng ký tự. Từ góc nhìn Java, bạn thao tác qua `String` hoặc `Reader`/`Writer`. Driver chịu trách nhiệm chuyển đổi sang encoding/collation của database khi cần.

**Không dùng `Clob.setAsciiStream` cho văn bản tiếng Việt có dấu** khi muốn bảo toàn Unicode. Dùng `setString` hoặc `setCharacterStream`. `setAsciiStream` chỉ dành cho nội dung ASCII theo hợp đồng.

### 1.3. NCLOB là một lựa chọn của schema

`NClob` biểu diễn **SQL NCLOB**. Nhiều hệ DB có cách lưu Unicode riêng, và một số không cần kiểu NCLOB để lưu các chuỗi Unicode thông thường trong CLOB. Vì vậy:

- Nếu cột là `NCLOB` và driver hỗ trợ, dùng `createNClob`/`setNClob` thích hợp.
- Nếu cột là `CLOB` và database/driver lưu Unicode đúng, `Clob` có thể hoàn toàn đủ.
- **Không khẳng định:** “Muốn lưu tiếng Việt thì bắt buộc chọn NClob”; đây là một quy tắc sai trên nhiều nền tảng.
- Tương thích loại cột, encoding và capability cần được kiểm thử với database thực tế. `java.sql.NClob` là interface Java chuẩn, không đồng nghĩa mọi driver thực hiện mọi phương thức.

## 2. Ba factory methods hiện hành trên `Connection`

Theo Java SE 26, chữ ký:

```java
Blob createBlob() throws SQLException;
Clob createClob() throws SQLException;
NClob createNClob() throws SQLException;
```

**Đây là chữ ký API**, không phải methods cần tự cài đặt trong project. `Connection` và các interfaces LOB ở package `java.sql` thuộc module `java.sql` của Java SE.

### 2.1. Điểm chung của ba method

1. Được gọi trên **một Connection đang mở** do JDBC driver/pool cung cấp.
2. Trả một object implement interface tương ứng, **ban đầu chưa có dữ liệu**.
3. Cho phép ghi vào LOB qua methods riêng: bytes cho Blob, character data cho Clob/NClob.
4. Có thể ném `SQLException` vì connection đã đóng, lỗi database hoặc không thể khởi tạo LOB.
5. Có thể ném `SQLFeatureNotSupportedException` nếu driver không hỗ trợ loại dữ liệu/method đó.
6. Việc khởi tạo **không đồng nghĩa INSERT/UPDATE đã chạy**. Muốn lưu vào cột, cần bind LOB vào `PreparedStatement` hoặc thao tác driver thích hợp.
7. LOB có thể dùng **locator** gắn với database thay vì sao chép toàn bộ payload vào heap, nên có vòng đời và tài nguyên riêng.

### 2.2. Minh họa tạo rỗng rồi ghi

```java
Blob blob = connection.createBlob();
blob.setBytes(1, fileBytes);

Clob clob = connection.createClob();
clob.setString(1, longText);

NClob nclob = connection.createNClob();
nclob.setString(1, nationalText);
```

Đoạn này **không độc lập**: `connection` phải là `Connection` hoạt động, `fileBytes` là `byte[]`, `longText` và `nationalText` là `String`, và cần giải phóng tài nguyên sau sử dụng. Đừng copy ba dòng rồi bỏ qua `free()`/close hoặc vòng đời transaction.

### 2.3. Thứ tự đúng trong luồng ghi dữ liệu

```text
Connection (đang mở)
    |
    +--> createBlob()  --> Blob rỗng  --> setBytes / setBinaryStream
    +--> createClob()  --> Clob rỗng  --> setString / setCharacterStream
    +--> createNClob() --> NClob rỗng --> setString / setCharacterStream
                                      |
                                      v
                       PreparedStatement.setBlob / setClob / setNClob
                                      |
                                      v
                              executeUpdate()
                                      |
                                      v
                             giải phóng LOB (free)
                                      |
                                      v
                       kết thúc transaction/đóng Connection
```

Đây là quy trình điển hình; **chi tiết resource lifetime và hỗ trợ tính năng do driver/database quyết định**. Không nên `free` LOB **trước khi** JDBC driver đã tiêu thụ dữ liệu ở bước execute.

## 3. BLOB: ghi/đọc dữ liệu nhị phân

### 3.1. `Blob.setBytes(long pos, byte[] bytes)`

```java
byte[] data = {0x00, (byte) 0xFE, 0x41};

Blob blob = connection.createBlob();
try {
    int written = blob.setBytes(1, data); // Ghi bắt đầu tại byte thứ nhất.
    byte[] copied = blob.getBytes(1, written);
    // copied có nội dung tương ứng data nếu driver thực hiện thành công.
} finally {
    blob.free();
}
```

Đây là đoạn tích hợp, cần `connection` thực tế và `throws SQLException` hoặc catch phù hợp. `setBytes` trả **số byte đã ghi**, không trả `Blob`. Ghi vào vị trí bắt đầu **1**, không phải 0 như chỉ số Java array.

- `pos = 1`: byte đầu tiên của LOB.
- `getBytes(1, length)`: lấy `length` byte từ vị trí SQL LOB đầu tiên.
- `Blob.length()`: số byte của BLOB, trả `long`.
- `setBytes(pos, bytes, offset, len)`: có overload ghi một phần của mảng, với `offset` trong Java array là **0-based**, còn `pos` trong LOB là **1-based**.

### 3.2. `Blob.setBinaryStream(long pos)`

Đối với nội dung lớn hoặc dữ liệu được tạo theo luồng, có thể dùng:

```java
Blob blob = connection.createBlob();
try {
    try (OutputStream out = blob.setBinaryStream(1)) {
        out.write(binaryPayload);
    }
    // Có thể bind blob vào PreparedStatement sau khi writer đã được đóng.
} finally {
    blob.free();
}
```

Đây là đoạn minh họa, cần import `java.io.OutputStream` và có `binaryPayload` kiểu `byte[]`. Đối với payload thật sự lớn, code thường đọc từng buffer từ source stream và chuyển sang output stream; **đừng tải toàn bộ file vào một mảng** rồi gọi `out.write(binaryPayload)` nếu mục tiêu là streaming để giảm bộ nhớ.

`Blob.setBinaryStream` trả `OutputStream` có thể ghi vào BLOB bắt đầu tại vị trí 1; nguồn dữ liệu cần được copy và stream nên được **flush/close đúng lúc** trước khi execute SQL. Driver có thể áp dụng cơ chế buffering/chunking khác nhau.

### 3.3. `Blob.getBinaryStream()`

Để đọc:

```java
try (InputStream in = blob.getBinaryStream()) {
    byte[] smallSample = in.readNBytes(1024);
    // Với dữ liệu lớn: xử lý qua buffer hoặc chuyển sang output stream.
}
```

Đây là snippet trong method, cần `blob` đã có dữ liệu, import `java.io.InputStream`, và exception handling (`IOException`, `SQLException`).

**Không mặc định `Blob.getBytes(1, (int)blob.length())` phù hợp mọi BLOB.** `length()` là `long`, có thể vượt `Integer.MAX_VALUE` hoặc làm tràn bộ nhớ. Dùng stream cho payload lớn và giới hạn kích thước theo nghiệp vụ.

### 3.4. Lưu binary bằng prepared statement

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO files (file_bytes) VALUES (?)")) {
    ps.setBlob(1, blob);
    ps.executeUpdate();
}
```

Đây là **snippet tích hợp**, cần bảng `files` có cột tương thích, connection và Blob còn hợp lệ. `?` là parameter marker; dùng `setBlob` thay vì nối byte/data vào SQL string.

## 4. CLOB: ghi/đọc văn bản dài

### 4.1. `Clob.setString`

```java
Clob clob = connection.createClob();
try {
    String text = "Tài liệu tiếng Việt: Xin chào.";
    int written = clob.setString(1, text);
    String returned = clob.getSubString(1, written);
} finally {
    clob.free();
}
```

`setString(1,text)` ghi vào đầu CLOB; `getSubString(1, written)` đọc ký tự từ vị trí đầu tiên. `Clob.length()` trả `long` đo chiều dài character data theo JDBC, **không phải số bytes của UTF-8**.

Đối với một `String` Java chứa code points ngoài BMP, `String.length()` đếm **UTF-16 code units**, không phải grapheme clusters. Driver/database có thể có đơn vị đếm ký tự theo hệ thống của nó; khi dữ liệu lớn hoặc cần chính xác với supplementary characters, ưu tiên Reader/Writer và test theo schema/driver.

### 4.2. `Clob.setCharacterStream`

```java
Clob clob = connection.createClob();
try {
    try (Writer writer = clob.setCharacterStream(1)) {
        writer.write("Nội dung bài viết có dấu tiếng Việt.");
    }
    // Bind clob sau khi kết thúc writer.
} finally {
    clob.free();
}
```

Đây là đoạn tích hợp, cần import `java.io.Writer`; không phải mã độc lập. `setCharacterStream(1)` nhận Unicode characters qua `Writer`. Không nhầm với `setAsciiStream` nếu payload chứa ký tự ngoài ASCII.

### 4.3. `Clob.getCharacterStream`

```java
try (Reader reader = clob.getCharacterStream()) {
    // Đọc từng buffer ký tự từ reader.
    char[] buffer = new char[4096];
    int n;
    while ((n = reader.read(buffer)) != -1) {
        // Xử lý buffer[0..n).
    }
}
```

Đây là snippet đọc, cần import `java.io.Reader` và code xử lý thực tế ở phần loop. Với CLOB lớn, Reader tránh tải toàn bộ nội dung vào `String` nếu pipeline thực sự xử lý theo stream.

### 4.4. Lưu text bằng `setClob`

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO articles (body_text) VALUES (?)")) {
    ps.setClob(1, clob);
    ps.executeUpdate();
}
```

Đây là đoạn tích hợp; SQL table/column phải tồn tại. Không gọi `clob.free()` trước `ps.executeUpdate()`.

## 5. NCLOB: dạng character LOB theo national character set

`NClob` kế thừa `Clob`, nên cú pháp ghi giống CLOB:

```java
NClob nclob = connection.createNClob();
try {
    nclob.setString(1, "Tài liệu đa ngôn ngữ: Việt Nam, 日本語.");
    try (Reader reader = nclob.getCharacterStream()) {
        // Đọc nội dung sau khi ghi.
    }
} finally {
    nclob.free();
}
```

Và khi lưu:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO translations (national_text) VALUES (?)")) {
    ps.setNClob(1, nclob);
    ps.executeUpdate();
}
```

Hai đoạn trên là **snippets tích hợp**, cần một Connection còn mở và một SQL schema hỗ trợ `NCLOB`. `NClob` không cung cấp bộ methods hoàn toàn riêng cho đọc ký tự; các methods như `getCharacterStream`, `setString` và `free` **được kế thừa từ `Clob`**.

### 5.1. Khác với `Clob` thế nào?

- `Clob` ánh xạ SQL `CLOB`.
- `NClob` ánh xạ SQL `NCLOB` sử dụng national character set.
- Cả hai được thao tác từ Java qua chuỗi/stream ký tự.
- Database/driver quyết định encoding, conversion và kiểu cột thực tế.
- **Không khẳng định** cứ truyền tiếng Việt vào `Clob` sẽ sai hoặc mất dấu; nhiều database dùng Unicode cho cả `CLOB`.
- **Không khẳng định** `createNClob` bắt buộc thành công: driver có thể không hỗ trợ NCLOB, ném `SQLFeatureNotSupportedException`.

### 5.2. `setNCharacterStream` và `setNClob` không giống nhau

`PreparedStatement` còn có `setNCharacterStream(index, reader[, length])` để truyền text qua Reader cho trường national character types, không cần tạo riêng đối tượng `NClob` trong một số workflow. Điều này hữu ích khi dữ liệu được đọc theo luồng.

So sánh:

| Cách | Đầu vào | Lúc nào chọn |
| --- | --- | --- |
| `ps.setNClob(1, nclob)` | `NClob` đã tạo bằng `createNClob` hoặc lấy từ DB | Khi cần một đối tượng NCLOB để thao tác/bind |
| `ps.setNClob(1, reader)` | `Reader`, nếu overload/driver hỗ trợ | Truyền character data qua reader |
| `ps.setNCharacterStream(1, reader)` | `Reader` | Truyền stream ký tự national theo hợp đồng |
| `ps.setClob(1, clob)` | `Clob` | Cột CLOB theo schema |
| `ps.setCharacterStream(1, reader)` | `Reader` | Truyền character data dạng stream cho kiểu phù hợp |

**Lưu ý khả năng tương thích:** Dùng `setNClob`/`setNCharacterStream` hay `setClob`/`setCharacterStream` phải căn cứ JDBC driver và cột SQL. Các overload nhận Reader có thể yêu cầu giữ stream mở đến khi driver thực sự tiêu thụ dữ liệu ở `executeUpdate`/`execute`.

## 6. Ví dụ Java 17+ hoàn chỉnh, không cần cài database

Ví dụ sau tạo một `Connection` bằng **dynamic proxy** và mô phỏng ba phương thức `createBlob`, `createClob`, `createNClob`. Mỗi LOB là một proxy lưu dữ liệu **trong bộ nhớ**. Mã cho phép kiểm thử việc sử dụng interface JDBC, `setBytes`, `setBinaryStream`, `setString`, `setCharacterStream`, `getBinaryStream`, `getCharacterStream`, `free`.

**Giới hạn minh bạch:** Đây là một **test double**. Nó **không phải JDBC driver**, không kết nối DB, không thực thi SQL và không chứng minh database nào hỗ trợ `NClob`. Các methods ngoài phạm vi minh họa ném `SQLFeatureNotSupportedException`. Hành vi thật của LOB locator, transaction, SQL binding và buffering phải được kiểm chứng với JDBC driver thực tế.

### 6.1. Tạo file `LobCreationDemo.java`

Toàn bộ mã dưới đây được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24. Nó không phụ thuộc external JAR.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.Blob;
import java.sql.Clob;
import java.sql.Connection;
import java.sql.NClob;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Arrays;

public final class LobCreationDemo {
    private static final class MemoryLob implements InvocationHandler {
        private final boolean binary;
        private byte[] bytes = new byte[0];
        private String text = "";
        private boolean freed;

        MemoryLob(boolean binary) { this.binary = binary; }

        private void ensureOpen() throws SQLException {
            if (freed) throw new SQLException("LOB was freed");
        }

        private void ensurePos(Object[] args) throws SQLException {
            if ((Long) args[0] != 1L) {
                throw new SQLException("Mock only supports position 1");
            }
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Exception {
            String name = method.getName();
            if (name.equals("toString")) return "MemoryLob(" + (binary ? "binary" : "text") + ")";
            if (name.equals("free")) {
                freed = true;
                bytes = null;
                text = null;
                return null;
            }
            ensureOpen();
            if (name.equals("length")) return binary ? (long) bytes.length : (long) text.length();
            if (binary) {
                if (name.equals("setBytes") && args.length == 2) {
                    ensurePos(args);
                    bytes = ((byte[]) args[1]).clone();
                    return bytes.length;
                }
                if (name.equals("getBytes")) {
                    ensurePos(args);
                    int length = (Integer) args[1];
                    return Arrays.copyOf(bytes, Math.min(length, bytes.length));
                }
                if (name.equals("getBinaryStream") && args == null) {
                    return new ByteArrayInputStream(bytes);
                }
                if (name.equals("setBinaryStream")) {
                    ensurePos(args);
                    return new ByteArrayOutputStream() {
                        @Override public void close() throws IOException {
                            super.close();
                            bytes = toByteArray();
                        }
                    };
                }
            } else {
                if (name.equals("setString") && args.length == 2) {
                    ensurePos(args);
                    text = (String) args[1];
                    return text.length();
                }
                if (name.equals("getSubString")) {
                    ensurePos(args);
                    int len = (Integer) args[1];
                    return text.substring(0, Math.min(len, text.length()));
                }
                if (name.equals("getCharacterStream") && args == null) {
                    return new StringReader(text);
                }
                if (name.equals("setCharacterStream")) {
                    ensurePos(args);
                    return new StringWriter() {
                        @Override public void close() {
                            text = toString();
                        }
                    };
                }
            }
            throw new SQLFeatureNotSupportedException("Mock does not implement " + name);
        }
    }

    private static final class MemoryConnection implements InvocationHandler {
        private boolean closed;

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws SQLException {
            String name = method.getName();
            if (name.equals("close")) {
                closed = true;
                return null;
            }
            if (name.equals("isClosed")) return closed;
            if (closed) throw new SQLException("Connection was closed");
            if (name.equals("createBlob")) {
                return lob(Blob.class, true);
            }
            if (name.equals("createClob")) {
                return lob(Clob.class, false);
            }
            if (name.equals("createNClob")) {
                return lob(NClob.class, false);
            }
            throw new SQLFeatureNotSupportedException("Mock does not implement " + name);
        }
    }

    private static <T> T lob(Class<T> type, boolean binary) {
        return type.cast(Proxy.newProxyInstance(
                LobCreationDemo.class.getClassLoader(),
                new Class<?>[] {type},
                new MemoryLob(binary)));
    }

    private static Connection connection() {
        return (Connection) Proxy.newProxyInstance(
                LobCreationDemo.class.getClassLoader(),
                new Class<?>[] {Connection.class},
                new MemoryConnection());
    }

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        Connection c = connection();
        try (c) {
            Blob blob = c.createBlob();
            try {
                check("blobInitiallyEmpty", blob.length() == 0);
                byte[] payload = {0, (byte) 0xFE, 65};
                check("blobSetBytes", blob.setBytes(1, payload) == payload.length);
                check("blobExact", Arrays.equals(blob.getBytes(1, 3), payload));
                try (InputStream in = blob.getBinaryStream()) {
                    check("blobInputStream", Arrays.equals(in.readAllBytes(), payload));
                }
                try (OutputStream out = blob.setBinaryStream(1)) {
                    out.write("XYZ".getBytes(StandardCharsets.UTF_8));
                }
                check("blobOutputStream", Arrays.equals(
                        blob.getBytes(1, 3), "XYZ".getBytes(StandardCharsets.UTF_8)));
            } finally {
                blob.free();
            }
            boolean freedThrows = false;
            try {
                blob.length();
            } catch (SQLException expected) {
                freedThrows = true;
            }
            check("blobFree", freedThrows);

            Clob clob = c.createClob();
            try {
                check("clobInitiallyEmpty", clob.length() == 0);
                String value = "Xin chào";
                check("clobSetString", clob.setString(1, value) == value.length());
                check("clobExact", clob.getSubString(1, value.length()).equals(value));
                try (Reader reader = clob.getCharacterStream()) {
                    StringWriter out = new StringWriter();
                    reader.transferTo(out);
                    check("clobReader", out.toString().equals(value));
                }
            } finally {
                clob.free();
            }

            NClob nclob = c.createNClob();
            try {
                check("nclobInitiallyEmpty", nclob.length() == 0);
                check("nclobIsClob", nclob instanceof Clob);
                String value = "Tiếng Việt 🌏";
                try (Writer writer = nclob.setCharacterStream(1)) {
                    writer.write(value);
                }
                check("nclobWriter", nclob.getSubString(1, value.length()).equals(value));
                try (Reader reader = nclob.getCharacterStream()) {
                    StringWriter out = new StringWriter();
                    reader.transferTo(out);
                    check("nclobReader", out.toString().equals(value));
                }
            } finally {
                nclob.free();
            }
        }
        check("connectionClosed", c.isClosed());
    }
}
```

### 6.2. Biên dịch và chạy

Từ thư mục chứa file `LobCreationDemo.java`:

```bash
javac --release 17 LobCreationDemo.java
java LobCreationDemo
```

Không cần thêm thư viện ngoài JDK. `java.sql` thuộc Java SE và sẽ được javac/java tìm theo module mặc định của classpath app. Khi chạy trên Java 17–25, cú pháp quản lý LOB bằng `free()` như chương trình vẫn hợp lệ.

### 6.3. Stdout chính xác đã kiểm chứng trên OpenJDK 24

```text
blobInitiallyEmpty=true
blobSetBytes=true
blobExact=true
blobInputStream=true
blobOutputStream=true
blobFree=true
clobInitiallyEmpty=true
clobSetString=true
clobExact=true
clobReader=true
nclobInitiallyEmpty=true
nclobIsClob=true
nclobWriter=true
nclobReader=true
connectionClosed=true
```

**Tất cả 15 dòng được xác nhận bằng assertions.** Helper `check` ném `AssertionError` nếu điều kiện sai, nên mỗi `=true` thực sự đến từ một phép kiểm thử đạt. Dữ liệu `Blob` có byte `0xFE` ngoài phạm vi ASCII; `NClob` có chữ tiếng Việt và emoji (code point ngoài BMP). Ví dụ đã biên dịch/thi hành thành công trên JDK 24 bằng `--release 17`.

### 6.4. Kiến thức rút ra từ chương trình

| Kết quả | Điều chứng minh |
| --- | --- |
| `blobInitiallyEmpty` | Factory `createBlob` trả đối tượng ban đầu chưa có data trong mock. |
| `blobSetBytes` | `setBytes(1, payload)` ghi từ vị trí 1, trả số byte đã ghi. |
| `blobExact` | `getBytes` đọc đúng byte, bao gồm byte không phải text. |
| `blobInputStream` | `getBinaryStream` trả `InputStream` đọc data binary. |
| `blobOutputStream` | `setBinaryStream` nhận bytes; sau khi đóng stream, mock chứa dữ liệu đã ghi. |
| `blobFree` | Sau `free`, mock từ chối tiếp tục truy cập dữ liệu. |
| `clobInitiallyEmpty` | Factory `createClob` trả text LOB rỗng. |
| `clobSetString` | `setString(1, value)` ghi nội dung Unicode từ vị trí đầu tiên. |
| `clobExact` | `getSubString` trả về chính xác văn bản tiếng Việt. |
| `clobReader` | `getCharacterStream` trả `Reader` để đọc theo luồng. |
| `nclobInitiallyEmpty` | Factory `createNClob` trả NClob rỗng. |
| `nclobIsClob` | `NClob` extends `Clob`. |
| `nclobWriter` | `setCharacterStream` chấp nhận nội dung tiếng Việt và emoji. |
| `nclobReader` | Đọc `NClob` qua `Reader`, không qua byte stream. |
| `connectionClosed` | `Connection` được đóng tự động bởi `try-with-resources`. |

**Không suy rộng hành vi mock sang driver thật.** `MemoryLob` trong chương trình chỉ cho phép `pos=1`, một tập phương thức nhỏ và giữ toàn bộ dữ liệu trong heap. Nó không mô tả transaction, locator, memory allocation hay byte encoding của một RDBMS.

### 6.5. Tại sao dùng dynamic proxy?

Một JDBC `Connection` có rất nhiều methods. Nếu tự implement thủ công chỉ để trả LOB giả, ví dụ sẽ chứa hàng trăm dòng methods không liên quan. `Proxy.newProxyInstance` tạo object implement interface với `InvocationHandler`; các methods không được mock hỗ trợ cố ý ném `SQLFeatureNotSupportedException`.

Một mock giúp **học và test cách sử dụng API**, nhưng không thay thế driver thật. Nếu đưa ứng dụng vào production, nên dùng driver/database integration test, không xây một “JDBC driver” từ handler này.

## 7. Ghi ba loại LOB vào SQL bằng PreparedStatement

Phần này minh họa **cách tích hợp**, không thể chạy độc lập vì cần driver, `DataSource` và bảng database thật.

Giả sử schema có:

```sql
-- Minh họa khái niệm; cú pháp khai báo NCLOB khác nhau theo DBMS.
CREATE TABLE documents (
    file_content BLOB,
    body_text CLOB,
    national_text NCLOB
);
```

**Không mặc định đoạn SQL tương thích mọi DBMS.** Một số hệ quản trị dùng `BLOB`/`CLOB`/`NCLOB` khác nhau hoặc không có national type riêng. Khi triển khai, dùng đúng DDL của database và driver đang sử dụng.

Một method dùng `Connection` có sẵn:

```java
static int insertDocument(Connection connection,
                          byte[] file, String body, String national)
        throws SQLException {
    Blob b = connection.createBlob();
    Clob c = null;
    NClob n = null;
    try {
        c = connection.createClob();
        n = connection.createNClob();

        b.setBytes(1, file);
        c.setString(1, body);
        n.setString(1, national);

        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO documents " +
                "(file_content, body_text, national_text) " +
                "VALUES (?, ?, ?)")) {
            ps.setBlob(1, b);
            ps.setClob(2, c);
            ps.setNClob(3, n);
            return ps.executeUpdate();
        }
    } finally {
        try {
            if (n != null) n.free();
        } finally {
            try {
                if (c != null) c.free();
            } finally {
                b.free();
            }
        }
    }
}
```

Đây là **method snippet**, cần các imports `java.sql.Blob`, `Clob`, `NClob`, `Connection`, `PreparedStatement`, `SQLException`. Nó không có `main`; chỉ chạy khi connection thật và DB schema phù hợp. Các `finally` lồng nhau bảo đảm mỗi `free()` đều **được thử gọi**, dù lần giải phóng trước có lỗi.

**Quan trọng về exception:** Ví dụ này ưu tiên dọn sạch tài nguyên. Trong code production có nhiều lỗi đồng thời, một `SQLException` từ `free` có thể che mất exception chính từ `executeUpdate`. Có thể dùng một utility quản lý suppressed exceptions, hoặc với JDK 26+ dùng `AutoCloseable`/try-with-resources theo phiên bản runtime; cần thử với driver thực tế. Không lờ lỗi release nhưng cũng không làm mất nguyên nhân chính.

### 7.1. Tại sao bind trước khi execute?

`ps.setBlob(1, b)`, `ps.setClob(2, c)` và `ps.setNClob(3, n)` **gán tham số**. Câu SQL thực sự thực thi ở `ps.executeUpdate()`. Thời điểm driver đọc dữ liệu từ LOB có thể phụ thuộc driver; vì vậy không gọi `free` trên đối tượng cần dùng **trước execute**.

### 7.2. LOB có được lưu chỉ vì đã gọi create?

**Không.** `connection.createBlob()` hoặc `createNClob()` tạo một đối tượng JDBC có thể cần tài nguyên tạm thời, nhưng không tự thực hiện `INSERT` vào bảng nghiệp vụ của bạn. Cần thao tác SQL và transaction thành công theo contract.

### 7.3. Transaction và đóng Connection

`Connection` có chế độ auto-commit và transaction như JDBC thông thường. Một LOB có thể sử dụng locator sống trong phạm vi transaction được tạo. Do đó:

- Giữ Connection còn hợp lệ trong khi ghi, bind, execute và khi thực hiện thao tác cần locator.
- Nếu dùng `setAutoCommit(false)`, thực hiện `commit`/`rollback` rõ ràng theo chính sách nghiệp vụ.
- Không giữ một `Blob` hoặc `Clob` để đọc sau khi Connection/transaction đã kết thúc nếu driver không bảo đảm.
- Với connection pool, đóng **logical handle** đúng vòng đời; đừng tách LOB locator khỏi transaction hoặc giữ trong cache toàn cục.
- `free()` giải phóng tài nguyên LOB; **không phải `commit()` hoặc `rollback()`**.

## 8. Một thay đổi quan trọng ở Java SE 26: LOB hỗ trợ AutoCloseable

**Đây là kiến thức hiện hành dễ bị thiếu nếu chỉ đọc tutorial Java 17 hoặc cũ hơn.** Trong **JDK 26/JDBC 4.5 MR**, các interfaces `Blob`, `Clob`, `NClob` (cùng một số JDBC SQL types khác) được cập nhật để hỗ trợ `AutoCloseable`. Methods `close()` mặc định gọi `free()`.

| JDK target | `Blob/Clob/NClob` là AutoCloseable? | Quản lý tài nguyên phù hợp |
| --- | --- | --- |
| **Java 17–25** | **Chưa** (không thể compile try-with-resources trực tiếp trên biến `Blob`/`Clob`) | Gọi `free()` tường minh trong `finally` |
| **Java 26+** | **Có**; `close()` gọi `free()` theo default implementation | Có thể dùng `try-with-resources` trực tiếp; hoặc vẫn dùng `free()` |
 
### 8.1. Mã đúng cho Java 17+

```java
Blob blob = connection.createBlob();
try {
    blob.setBytes(1, data);
    // Dùng blob theo contract JDBC.
} finally {
    blob.free();
}
```

Đoạn minh họa trên tương thích Java 17 và JDK 26. Nó không giả định `Blob` đã implement `AutoCloseable` ở Java 17.

### 8.2. Mã chỉ compile khi target JDK 26+

```java
// Chỉ dùng khi biên dịch với --release 26 / target Java 26+.
try (Blob blob = connection.createBlob();
     Clob clob = connection.createClob();
     NClob nclob = connection.createNClob()) {
    blob.setBytes(1, bytes);
    clob.setString(1, text);
    nclob.setString(1, nationalText);
    // Bind và execute SQL trước khi kết thúc scope này.
}
```

Đây là **snippet Java 26+**, không nằm trong chương trình Java 17+ đã kiểm thử. `blob`, `clob`, `nclob` được tự động gọi `close()` theo thứ tự ngược lúc rời scope; JDK 26 `close` mặc định gọi `free`. Dùng `--release 17` sẽ **không biên dịch** snippet này với các interface LOB; đó là sự khác biệt phiên bản có chủ đích.

**Cảnh báo:** `try-with-resources` giúp dọn dẹp, nhưng không tự làm INSERT, COMMIT hoặc xử lý compatibility NCLOB cho database. Chỉ sử dụng khi runtime/driver và target compilation thực sự hỗ trợ.

### 8.3. Vì sao bài vẫn dùng `free()` trong ví dụ chính?

Chương trình độc lập đặt mục tiêu chạy từ **Java 17 trở lên**. `free()` là API còn hiệu lực và tương thích từ nhiều phiên bản JDBC. Vì vậy sử dụng `free` cho bài thực hành không phải dạy một kỹ thuật lỗi thời: đó là cách quản lý LOB hợp lệ trên Java 17–25, và vẫn hợp lệ trên Java 26+.

Tham khảo **[Oracle JDK 26 Release Notes — Add JDBC 4.5 MR Support](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)** và Javadoc Java SE 26 phần `Blob.close`/`Clob.close`.

## 9. Streaming hay buffer toàn bộ LOB?

Việc chọn API ghi ảnh hưởng trực tiếp **bộ nhớ, thời gian thực thi và hiệu năng**.

| Nhu cầu | Cách trực tiếp | Cách streaming |
| --- | --- | --- |
| Binary nhỏ đã có `byte[]` | `blob.setBytes(1, bytes)` | `blob.setBinaryStream(1)` |
| Text nhỏ đã có `String` | `clob.setString(1, text)` | `clob.setCharacterStream(1)` |
| National text nhỏ | `nclob.setString(1, text)` | `nclob.setCharacterStream(1)` |
| Insert binary source rất lớn | Tránh `Files.readAllBytes` nếu giới hạn RAM | `PreparedStatement.setBinaryStream(...)` hoặc stream ghi vào Blob |
| Insert text source lớn | Tránh tải toàn bộ vào một `String` | `setCharacterStream`, `setClob(index,Reader)` hoặc `setNCharacterStream` theo DB |
| Đọc dữ liệu BLOB lớn | Tránh cast `(int) blob.length()` rồi cấp phát mảng khổng lồ | `getBinaryStream()` và xử lý theo buffer |
| Đọc CLOB/NCLOB lớn | Tránh `getSubString(1,(int)clob.length())` | `getCharacterStream()` và xử lý từng phần |

### 9.1. Ví dụ ghi file qua OutputStream

```java
try (InputStream source = Files.newInputStream(file);
     OutputStream target = blob.setBinaryStream(1)) {
    source.transferTo(target);
}
```

Đây là **snippet tích hợp** cần biến `file` kiểu `Path`, `blob` còn mở và imports `java.io.*`, `java.nio.file.Files`. `InputStream.transferTo` (Java 9+) chuyển dữ liệu theo luồng. Bộ nhớ nội bộ, số lần gửi xuống database và tốc độ phụ thuộc driver.

### 9.2. Có cần gọi createBlob trước nếu chỉ có InputStream?

Không nhất thiết. JDBC `PreparedStatement` có overload nhận stream trực tiếp:

```java
try (InputStream in = Files.newInputStream(file);
     PreparedStatement ps = connection.prepareStatement(
             "INSERT INTO files(file_bytes) VALUES (?)")) {
    ps.setBinaryStream(1, in);
    ps.executeUpdate();
}
```

Đây là **snippet tích hợp**; cần driver/database và các imports. Khi source đã là stream, cách này có thể ít bước hơn so với tạo một Blob trung gian. Driver có thể hỗ trợ/đòi overload có độ dài, có thể buffer nội bộ và thường chỉ đọc stream khi execute.

**Không mặc định “streaming API” luôn thực hiện truyền dữ liệu không buffer.** Đo/quan sát với driver cụ thể khi dữ liệu rất lớn.

### 9.3. Ký tự tiếng Việt và encoding

`Writer`/`Reader` làm việc với **characters** ở phía Java. Tầng JDBC driver chịu trách nhiệm convert sang encoding/national charset của database. Với `InputStream`/`OutputStream` của `Blob`, bạn làm việc với **bytes thô**, không có chuyển đổi ngôn ngữ.

Vì vậy khi lưu văn bản từ file UTF-8, một pipeline có thể là `Files.newBufferedReader(file, StandardCharsets.UTF_8)` rồi `setCharacterStream`/`setNCharacterStream`. Không đọc file UTF-8 thành bytes rồi đưa vào CLOB như dữ liệu nhị phân mà kỳ vọng database tự giải mã chính xác.

## 10. Vị trí 1-based và kích thước dữ liệu

### 10.1. Các cặp tham số dễ nhầm

```java
blob.setBytes(1, bytes);           // 1-based LOB position
blob.getBytes(1, numberOfBytes);   // 1-based LOB position

clob.setString(1, text);           // 1-based LOB position
clob.getSubString(1, count);       // 1-based LOB position

nclob.setString(1, unicodeText);   // 1-based LOB position
nclob.getSubString(1, count);      // 1-based LOB position
```

Ngược lại `byte[]`/`char[]` có chỉ số `0-based`. `Blob.setBytes(pos, bytes, offset, len)` trộn **LOB position** và **array offset**, cần kiểm tra mỗi đơn vị.

### 10.2. Khi `length()` lớn hơn int

`Blob.length()` và `Clob.length()` trả `long`. `Blob.getBytes`/`Clob.getSubString` có tham số chiều dài `int`. Với LOB rất lớn:

```java
long lobLength = blob.length();
// Không cast không kiểm tra: int bytes = (int) lobLength;
```

Nên stream theo buffer thay vì đọc hết vào RAM. Nếu nghiệp vụ thật sự cần mảng, kiểm tra dữ liệu nằm trong giới hạn bộ nhớ và chiều dài `int` trước khi cấp phát.

### 10.3. Chuỗi có emoji, dấu tiếng Việt

Một `String` Java có thể chứa supplementary code points (emoji) biểu diễn bằng **hai UTF-16 code units**. `String.length()` không phải số ký tự người dùng nhìn thấy. Trong mock, `String.length()` được dùng để đo chiều dài nội bộ theo implementation của mock. Với database thật, hãy kiểm thử quy tắc length/substring của driver và tránh dùng số code points thay thế tùy ý cho JDBC character offsets.

## 11. Vòng đời và ownership của LOB

### 11.1. LOB thường gắn với Connection và transaction

Javadoc mô tả các LOB dạng locator (con trỏ logic tới dữ liệu DB) thường chỉ hợp lệ trong transaction nơi chúng được tạo. Một số driver có thể materialize dữ liệu trong bộ nhớ, nhưng **không được xem đó là bảo đảm chung**.

Ví dụ không nên làm:

```java
static Blob getBlobAndCloseConnection(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection()) {
        return connection.createBlob();
    }
}
```

Đây là **anti-pattern minh họa**: hàm trả LOB được tạo từ một Connection đã đóng. Đối tượng có thể trở nên không hợp lệ ngay khi caller sử dụng. Mã chỉ trình bày điểm sai, không nên áp dụng.

### 11.2. `free()` không giống `close()` của Connection

- `Blob.free()`: giải phóng tài nguyên do **Blob** giữ.
- `Clob.free()`/`NClob.free()`: giải phóng tài nguyên **character LOB**.
- `Connection.close()`: kết thúc logical JDBC connection handle; với pool, nó có thể trả connection về pool.
- `PreparedStatement.close()`: giải phóng statement resources.
- `InputStream.close()`/`Writer.close()`: giải phóng stream I/O.

**Không gộp** các loại resource này thành một đối tượng và mặc định đóng một loại sẽ dọn sạch tất cả loại còn lại ngay lập tức. Dọn LOB theo contract, rồi đóng statement/connection đúng vòng đời.

### 11.3. Nên giải phóng khi nào?

Khi đã hoàn tất các thao tác cần LOB, sau khi stream liên quan và SQL statement đã được driver tiêu thụ:

```text
create LOB
  -> ghi data
  -> đóng output stream/writer
  -> bind parameter
  -> execute statement
  -> không cần LOB nữa
  -> free LOB
  -> transaction commit/rollback theo ứng dụng
  -> trả connection về pool
```

Chi tiết giữa free/commit phụ thuộc driver và pattern sử dụng; phải kiểm thử khi LOB có locator hoặc dữ liệu được đọc/ghi sau execute.

### 11.4. LOB không dùng chung giữa nhiều requests

Không giữ một `Blob`/`Clob` tạo từ request A trong singleton rồi đưa sang request B đang dùng Connection khác. LOB có thể mang state, locator và tài nguyên gắn với session/transaction ban đầu. Tương tự, không để client API nhận trực tiếp đối tượng `Blob` mà hệ thống đã đóng Connection.

Với service boundary, nên chuyển dữ liệu qua stream có vòng đời xác định, lưu file/object storage nếu nghiệp vụ phù hợp, hoặc trích xuất payload theo contract trước khi giải phóng JDBC resources.

## 12. Xử lý SQLException và trường hợp driver không hỗ trợ

Cả ba `Connection.create...` đều có thể ném `SQLException`. Theo Javadoc, nếu JDBC driver **không hỗ trợ** loại LOB tương ứng, có thể ném `SQLFeatureNotSupportedException`.

```java
try {
    NClob nclob = connection.createNClob();
    try {
        nclob.setString(1, text);
        // Bind vào cột NCLOB thích hợp.
    } finally {
        nclob.free();
    }
} catch (SQLFeatureNotSupportedException unsupported) {
    // Driver/schema không hỗ trợ hành vi được yêu cầu.
    // Chọn giải pháp theo contract và loại cột thực tế.
}
```

Đây là snippet tích hợp, cần `connection`, `text` và imports tương ứng. Không nên catch exception rồi âm thầm chuyển nội dung Unicode sang bytes ASCII: có thể làm mất dữ liệu.

### 12.1. Không có driver là một lỗi riêng

`DriverManager.getConnection(...)` hoặc `dataSource.getConnection()` có thể thất bại vì URL/credentials/network hoặc thiếu driver. Đó **không phải** cùng lỗi với `createNClob()` không hỗ trợ data type. Trình tự debug:

1. Đã lấy được Connection thật chưa?
2. Connection còn mở không?
3. Driver đang dùng phiên bản nào?
4. DB có cột/data type `BLOB`, `CLOB`, `NCLOB` tương ứng không?
5. `createBlob/Clob/NClob` có được driver triển khai không?
6. `setBlob/Clob/NClob` có hỗ trợ cách binding hiện tại không?
7. Stream đã ghi/đóng đúng thời điểm trước execute chưa?
8. Transaction/locator chưa hết lifetime chứ?
9. Giới hạn kích thước của DB/column và storage quota có phù hợp không?

### 12.2. Fallback có điều kiện

Nếu driver không hỗ trợ `createBlob` nhưng có `PreparedStatement.setBinaryStream`, ứng dụng **có thể** chuyển sang stream binding nếu data type và driver hỗ trợ. Nếu `createNClob` không hỗ trợ nhưng schema dùng một CLOB Unicode bình thường, **có thể** dùng `Clob` hoặc `setCharacterStream` tùy contract.

**Không thay `NCLOB` bằng `BLOB` hoặc tự chuyển text sang mã hóa bất kỳ** chỉ để loại exception. Việc thay đổi loại dữ liệu đòi hiểu rõ schema, encoding và yêu cầu nghiệp vụ.

### 12.3. Dọn dẹp khi có exception

Với Java 17–25, `Blob`/`Clob`/`NClob` không phải `AutoCloseable` trực tiếp. Vì thế dùng `finally` để `free` là cần thiết. Nếu một phương thức `free` có thể ném, code production nên bảo toàn exception chính và thêm lỗi release dưới dạng **suppressed exceptions** hoặc sử dụng utility dọn dẹp được kiểm thử. Một vòng lặp `free` “best effort” tự nuốt mọi lỗi cũng có thể che leak trong môi trường nhạy cảm.

## 13. So sánh `createBlob` với `ResultSet.getBlob`

| API | Khi dùng | Ý nghĩa |
| --- | --- | --- |
| `connection.createBlob()` | Tạo LOB rỗng để ghi data mới | Tạo đối tượng BLOB mới, chưa chứa dữ liệu |
| `resultSet.getBlob(index)` | Đọc BLOB từ một cột trong hàng kết quả | Nhận giá trị BLOB đã lưu |
| `connection.createClob()` | Tạo character LOB rỗng | Chuẩn bị data text để ghi |
| `resultSet.getClob(index)` | Đọc CLOB từ query result | Nhận text LOB đã lưu |
| `connection.createNClob()` | Tạo national character LOB rỗng | Chuẩn bị NCLOB nếu có support |
| `resultSet.getNClob(index)` | Đọc NCLOB từ query result | Nhận national text LOB |

Hai hướng **tạo** và **đọc từ DB** không hoán đổi. Ví dụ:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT file_content FROM documents WHERE id = ?")) {
    ps.setLong(1, documentId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Blob saved = rs.getBlob(1);
            if (saved != null) {
                try {
                    try (InputStream in = saved.getBinaryStream()) {
                        // Đọc/stream nội dung vào đích phù hợp.
                    }
                } finally {
                    saved.free();
                }
            }
        }
    }
}
```

Đây là đoạn **tích hợp** với bảng `documents` có cột BLOB. Nó không chạy nếu không có DB, và kiểm tra `saved != null` vì cột SQL có thể là `NULL`. Không gọi `getBlob` trên một kết quả NULL rồi truy cập stream.

## 14. Thực hành với image, tài liệu và dữ liệu tiếng Việt

### 14.1. Lưu ảnh/file

Nếu file đã có dạng `byte[]` nhỏ, `createBlob`/`setBytes` tiện lợi. Nếu file lớn, dùng `Files.newInputStream` và `setBinaryStream` hoặc bind stream trực tiếp. Không convert ảnh sang `String` chỉ để lưu vào CLOB.

### 14.2. Lưu nội dung bài viết

Nếu text đã có trong `String` và kích thước hợp lý, `createClob`/`setString` trực tiếp. Nếu text có thể rất lớn hoặc do một Reader cung cấp, cân nhắc `setCharacterStream` hay `PreparedStatement.setClob(index, Reader)`.

### 14.3. Lưu tên/tài liệu đa ngôn ngữ

Đối với dữ liệu Unicode tiếng Việt, tiếng Nhật hoặc ngôn ngữ khác, chọn CLOB hay NCLOB theo **loại cột, driver encoding và database**. Trong nhiều hệ thống hiện đại, CLOB dùng Unicode đúng cách. Trong hệ khác, national character types là yêu cầu của schema. `NClob` hỗ trợ character stream và kế thừa Clob API, không cần chuyển chuỗi sang byte thủ công.

### 14.4. Khi nào không nên dùng LOB?

Đối với tiêu đề ngắn hoặc một mô tả nhỏ, một `VARCHAR`/`NVARCHAR` theo khả năng DB có thể phù hợp hơn một LOB; tùy DBMS và yêu cầu index/query. Không tạo Blob/Clob chỉ vì mọi kiểu chuỗi đều có thể biểu diễn ở đó. Với file lớn và yêu cầu CDN/object storage, có thể cần đánh giá lưu metadata trong DB và payload trong object storage thay vì LOB.

**Bài này hướng dẫn JDBC LOB API**, không áp đặt một kiến trúc lưu trữ cho mọi hệ thống.

## 15. Checklist trước khi dùng trong production

1. **Xác nhận cột SQL:** `BLOB`, `CLOB` hay `NCLOB` thật sự tồn tại và được DB hỗ trợ.
2. **Kiểm tra driver:** `Connection.createBlob/Clob/NClob` và `PreparedStatement.setBlob/Clob/NClob` hoạt động với version triển khai.
3. **Định dạng dữ liệu:** binary giữ nguyên bytes; text dùng characters/encoding phù hợp.
4. **Đừng mặc định NCLOB là bắt buộc cho mọi Unicode.**
5. **LOB mới ban đầu rỗng:** phải ghi data trước khi bind/execute.
6. **SQL phải parameterized:** không ghép byte/text dài trực tiếp vào SQL literals.
7. **Vị trí JDBC LOB bắt đầu từ 1:** phân biệt với Java array offset 0.
8. **Đóng writer/output stream trước execute** để dữ liệu đã được hoàn tất trước khi driver tiêu thụ.
9. **Đọc LOB lớn bằng stream** thay vì cấp phát mảng/string dựa vào `(int)length()`.
10. **Giới hạn tải và kiểm tra size:** tránh file vô hạn hoặc payload vượt quota.
11. **Giải phóng LOB:** `free()` cho Java 17–25 và Java 26+; `close()` qua `AutoCloseable` chỉ dùng khi target Java 26+.
12. **Connection/statement/result set có vòng đời riêng:** đóng đúng tài nguyên của chúng.
13. **Không giữ locator qua transaction/connection đã đóng** trừ khi driver có contract rõ ràng.
14. **Xử lý SQLException:** phân biệt lỗi driver capability với DB access/transaction.
15. **Kiểm tra cột NULL:** `ResultSet.getBlob/Clob/NClob` có thể trả `null`.
16. **Test dữ liệu Unicode thực:** tiếng Việt, ký tự supplementary, và text dài.
17. **Test binary không phải text:** dữ liệu chứa 0x00, 0xFF và các byte có bit cao.
18. **Đo hiệu năng/memory:** có thể có buffering nội bộ dù dùng streaming API.
19. **Test với connection pool thật:** không tách tài nguyên LOB khỏi logical connection được mượn.
20. **Đánh giá migration JDK:** JDK26 có AutoCloseable LOB mới; không copy code try-with-resources vào project target Java17.

## 16. Các lỗi lập trình thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi `createBlob()` rồi nghĩ data đã được lưu trong bảng | Chỉ mới tạo LOB rỗng | Ghi data, bind `setBlob` và execute SQL |
| `blob.setBytes(0, bytes)` | LOB position là 1-based | Dùng `setBytes(1,bytes)` |
| Dùng `clob.setAsciiStream` cho text có dấu | ASCII stream không đại diện Unicode đầy đủ | Dùng `setString`/`setCharacterStream` |
| Dùng `NClob` chỉ vì text là tiếng Việt | Phụ thuộc database national charset và schema | Chọn loại cột theo DB/driver |
| Quên `free()` trên Java17 | LOB có thể giữ resource tạm thời/locator | `finally { lob.free(); }` |
| Dùng `try(Blob b=...)` khi `--release 17` | Blob chưa implement AutoCloseable ở Java17 | Dùng `free`; chỉ try-with-resources LOB ở JDK26+ |
| `free` LOB trước `ps.executeUpdate()` | Driver có thể vẫn cần đọc LOB | Giữ LOB hợp lệ tới khi execute hoàn tất |
| `connection.close()` trước khi đọc `ResultSet.getClob` | Locator có thể hết hiệu lực | Đọc trong phạm vi connection/transaction |
| `(int)blob.length()` rồi cấp phát lớn | Tràn int hoặc OutOfMemoryError | Dùng `getBinaryStream` và buffer |
| Lưu file bằng `new String(bytes)` không charset | Đổi bytes, mất dữ liệu nhị phân | Dùng BLOB và raw bytes |
| Bỏ qua `SQLFeatureNotSupportedException` | Driver không hỗ trợ loại LOB/method | Kiểm tra schema/driver, chọn fallback hợp lệ |
| Chuyển NCLOB sang ASCII khi không hỗ trợ | Có thể mất chữ và thông tin | Dùng Unicode-capable column/driver hoặc báo lỗi |
| Không đóng InputStream/Writer | Resource và buffering không được giải phóng | Dùng try-with-resources cho streams |
| Giữ LOB trên singleton sau request | Locator hết transaction, connection khác | Không lưu LOB object xuyên request |
| Giả định SQL type giống nhau trên mọi DBMS | DDL/charset khác nhau | Test schema và driver cụ thể |
| Không phân biệt bytes/characters | Sai encoding/length | Dùng BLOB byte stream, CLOB/NCLOB Reader/Writer |

## 17. Câu hỏi tự kiểm tra

**1. `Connection.createBlob()` trả gì và có tự INSERT dữ liệu không?**

Nó trả một `Blob` **rỗng**. Muốn lưu, ghi data rồi bind vào `PreparedStatement` và execute một câu lệnh SQL hợp lệ.

**2. BLOB và CLOB khác nhau ở đâu?**

`Blob` lưu **binary bytes**; `Clob` lưu **text characters**. Không tự ép một file nhị phân thành String để đưa vào CLOB.

**3. NClob có phương thức `getNCharacterStream()` riêng không?**

Không. `NClob extends Clob` và dùng các character methods như `getCharacterStream()`/`setCharacterStream()`. `PreparedStatement` có các methods `setNClob`/`setNCharacterStream` phù hợp ở tầng binding.

**4. Vì sao `clob.setString(0,text)` sai?**

Vì vị trí JDBC LOB là **1-based**; ký tự đầu ở pos=1.

**5. Nếu có một file 1 GB, có nên `Files.readAllBytes` rồi `setBytes` không?**

Thường không nên: tải cả file vào một mảng có thể gây áp lực bộ nhớ. Cân nhắc stream và giới hạn kích thước, kiểm thử driver có thật sự streaming.

**6. `Blob.free()` có phải rollback transaction không?**

Không. `free` giải phóng tài nguyên LOB, không thay `commit/rollback` của Connection.

**7. Java 17 có thể viết `try (Blob b = connection.createBlob())` không?**

Không, `Blob` chưa là AutoCloseable ở Java 17. Java 26 bổ sung hỗ trợ này; code Java17 dùng `free()`.

**8. CLOB có thể lưu Unicode không?**

Có thể, nếu database/driver dùng character encoding hỗ trợ dữ liệu đó. Không có quy tắc toàn cục “Unicode phải là NCLOB”. Phải xét schema và driver cụ thể.

**9. Khi nào `createNClob()` ném `SQLFeatureNotSupportedException`?**

Khi JDBC driver không hỗ trợ loại dữ liệu/method tương ứng theo contract; phải kiểm tra DB/driver/cột SQL, không ép fallback làm mất dữ liệu.

**10. Tại sao ví dụ không kết nối database vẫn cho phép kiểm thử method calls?**

Vì nó dùng **dynamic proxy mock** của JDBC interfaces, minh họa cách gọi, dữ liệu và vòng đời. Nó không xác minh driver hoặc DB thật có hỗ trợ NCLOB.

**11. Vì sao đọc dữ liệu lớn nên dùng stream thay vì `getSubString(1,(int)length())`?**

Vì `length` là long, payload có thể rất lớn và một mảng/String duy nhất gây áp lực memory hoặc không nằm trong phạm vi int. Reader/InputStream hỗ trợ xử lý từng phần.

**12. Nên đóng stream ghi vào LOB trước hay sau `ps.executeUpdate()`?**

Thông thường hoàn thành và đóng output stream/writer trước execute để dữ liệu đã được ghi xong; sau đó bind/execute, rồi giải phóng LOB khi driver không cần nữa. Chi tiết cần test theo driver.

## Tài liệu chính thức đang có hiệu lực

- [Oracle Java SE 26 — `Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createBlob`, `createClob`, `createNClob`, điều kiện và exceptions.
- [Oracle Java SE 26 — `Blob`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Blob.html): binary LOB, `setBytes`, binary streams, `free` và `close`.
- [Oracle Java SE 26 — `Clob`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Clob.html): text LOB, `setString`, character streams, `free` và `close`.
- [Oracle Java SE 26 — `NClob`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/NClob.html): national character set SQL type, inherited Clob methods và resource lifetime.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setBlob`, `setClob`, `setNClob` và stream bindings.
- [Oracle Java SE 26 — `ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getBlob`, `getClob`, `getNClob` và SQL NULL.
- [Oracle Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): xử lý lỗi JDBC.
- [Oracle Java SE 26 — `SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): driver không hỗ trợ tính năng.
- [Oracle JDK 26 Release Notes — JDBC 4.5 MR](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): `Blob/Clob/NClob` hỗ trợ `AutoCloseable` kể từ Java 26.
- [Oracle Java SE 17 — `Blob`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Blob.html): đối chiếu lý do Java17-compatible code vẫn dùng `free()`.

**Ghi nhớ:** `Connection.createBlob()`, `createClob()` và `createNClob()` tạo **ba loại LOB rỗng** để ứng dụng ghi bytes hoặc characters, rồi bind vào SQL khi driver và schema hỗ trợ. **BLOB ≠ CLOB ≠ NCLOB** về loại dữ liệu; vị trí JDBC LOB bắt đầu từ **1**; chỉ tạo LOB không tự INSERT; cần quản lý streams, `free()`, transaction và connection lifetime. Với **JDK 26+**, LOB thêm `AutoCloseable.close()`; khi cần tương thích **Java 17+**, `free()` vẫn là lựa chọn chuẩn xác và hiện hành.
