# SQLFeatureNotSupportedException và giới hạn driver

## 1. Vấn đề: Java có API nhưng database driver không hỗ trợ

`java.sql.SQLFeatureNotSupportedException` là một subclass của `SQLException` báo rằng **JDBC driver không hỗ trợ một tính năng tùy chọn, một overload hoặc một mode cụ thể**. Đây không nhất thiết là lỗi Java code thiếu phương thức: code có thể **biên dịch thành công**, nhưng lúc chạy driver/DBMS từ chối một capability.

Trong nhóm **SQLXML**, những đường gọi sau có từ JDBC 4.0/Java 6 và vẫn có trong Java SE 26:

~~~java
SQLXML xml = connection.createSQLXML();
xml.setString("<doc>Tiếng Việt</doc>");
preparedStatement.setSQLXML(1, xml);
~~~

Đây là **đoạn trích**, không phải file độc lập: `connection` là `Connection` đang mở, `preparedStatement` là `PreparedStatement` với tham số SQL XML phù hợp và phải thực thi/đóng tài nguyên ở phạm vi đầy đủ. `createSQLXML()` có thể ném `SQLFeatureNotSupportedException` khi driver không có SQL XML data type; `setSQLXML(...)` có thể ném ngay cả khi tạo SQLXML đã thành công.

**Nguyên tắc:** tồn tại method trong JDK **không đảm bảo** driver, database và SQL column thực sự thực thi được method ấy.

### Kết quả học tập

1. Hiểu vị trí của `SQLFeatureNotSupportedException` trong hệ phân cấp `SQLException` và SQLState class `0A`.
2. Phân biệt lỗi **optional feature**, **optional overload** và **unsupported mode**, không nhầm với syntax/network/constraint error.
3. Nhận biết giới hạn ở `Connection.createSQLXML`, `PreparedStatement.setSQLXML`, `ResultSet.getSQLXML`, `SQLXML.getSource`, conversion và cleanup.
4. Xây cơ chế phát hiện capability đúng: metadata chỉ là dấu hiệu, integration test thật mới xác minh từng operation.
5. **Fail rõ ràng** hoặc chọn storage path khác được chủ động thiết kế; không biến XML typed column thành text fallback tùy tiện.
6. Chạy demo Java 17+ độc lập và biên dịch repository sử dụng `DataSource`/`SQLXML`.
7. Hiểu `SQLXML.free()` trên Java 17, `AutoCloseable` mới ở Java 26/JDBC 4.5, và kiểm tra an toàn XML đầu vào.

## 2. Quan hệ với JDBC 4.0 và API còn áp dụng

`SQLFeatureNotSupportedException` được giới thiệu từ **Java SE 6/JDBC 4.0**. Java hiện đại vẫn dùng exception này. `SQLXML` cũng xuất hiện trong JDBC 4.0 để biểu diễn SQL XML data type.

| Thành phần | Vai trò | Điểm cần phân biệt |
| --- | --- | --- |
| `SQLException` | Lỗi JDBC chung | Không đồng nghĩa thiếu capability |
| `SQLNonTransientException` | Nhóm lỗi không tạm thời | Retry ngay thường không giúp |
| `SQLFeatureNotSupportedException` | Unsupported optional JDBC capability | Class con của `SQLNonTransientException` |
| `SQLXML` | Giá trị SQL XML theo JDBC | Type support vẫn phụ thuộc driver/DB |
| `Connection.createSQLXML` | Tạo SQLXML object | Có thể không hỗ trợ SQL XML type |
| `PreparedStatement.setSQLXML` | Bind SQLXML vào parameter | Có thể từ chối overload/column type |
| `ResultSet.getSQLXML` | Đọc SQL XML cột kết quả | Có thể không hỗ trợ read mapping |
| `SQLXML.free()` | Giải phóng tài nguyên SQLXML | Dùng rõ ràng trên Java17 |
| `SQLXML.close()` / `AutoCloseable` | Tự đóng qua try-with-resources | **JDBC 4.5/Java 26**, không dùng ở `--release 17` |

**Không khôi phục các kỹ thuật đã lỗi thời:** không dựa vào driver cổ, không coi `Class.forName` bắt buộc trong mọi app JDBC hiện đại, không cố nuốt lỗi unsupported để ứng dụng tiếp tục như thể dữ liệu đã lưu. Ví dụ dùng Java 17+, các API có trong Java SE 26 hiện hành.

## 3. Hệ phân cấp exception và SQLState class 0A

~~~text
java.lang.Exception
       |
       v
java.sql.SQLException
       |
       v
java.sql.SQLNonTransientException
       |
       v
java.sql.SQLFeatureNotSupportedException
~~~

Oracle Javadoc mô tả ba nhóm unsupported:

- **Optional feature không được triển khai**: chẳng hạn SQL XML type không có.
- **Optional overloaded method không được triển khai**: driver chỉ hỗ trợ một số overload chứ không hỗ trợ một chữ ký cụ thể.
- **Optional mode không được triển khai**: ví dụ result-set type/concurrency mode mà driver không có.

### 3.1. SQLState lớp 0A

Theo SQLState, class `0A` mô tả **feature not supported**; `0A000` là mã phổ biến. Đừng khẳng định **mọi** instance `SQLFeatureNotSupportedException` đều có `getSQLState() == "0A000"`: constructor và driver có thể cung cấp state khác hoặc null.

Ví dụ tạo error với state rõ:

~~~java
SQLFeatureNotSupportedException unsupported =
        new SQLFeatureNotSupportedException(
                "Driver does not support SQL XML", "0A000");
System.out.println(unsupported.getSQLState()); // 0A000
~~~

Đây là **đoạn trích**, cần import `java.sql.SQLFeatureNotSupportedException`. Trong chương trình test ở phần 6, fixture cố tình dùng `"0A000"`, do đó stdout có thể được assert chính xác. Trên driver thật, chỉ báo lại state do chính driver trả.

### 3.2. Vì sao non-transient rất quan trọng?

Một feature không được driver triển khai **thường không trở nên hỗ trợ chỉ vì retry ngay**. Retry vòng lặp có thể làm treo request và tăng tải nhưng không giải quyết gốc.

~~~java
// Sai: thử không giới hạn một feature đang thiếu.
while (true) {
    try {
        connection.createSQLXML();
        break;
    } catch (SQLFeatureNotSupportedException ignored) {
        // Không có chính sách thay driver/schema/configuration.
    }
}
~~~

Đây là **phản ví dụ**, không phải chương trình đầy đủ. Với một exception mang tính không tạm thời, giải pháp thường là **thay đổi implementation/configuration hoặc chọn đường hoạt động khác theo yêu cầu nghiệp vụ**.

### 3.3. Đừng coi mọi SQLException là unsupported

| Loại exception | Tình huống | Cách tiếp cận |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` | Feature/overload/mode không có | Không retry mù; feature gate/fail rõ |
| `SQLSyntaxErrorException` | Sai syntax hoặc SQL object | Sửa SQL/schema |
| `SQLIntegrityConstraintViolationException` | Lỗi PK/FK/unique constraint | Kiểm tra dữ liệu nghiệp vụ |
| `SQLTimeoutException` | Statement/operation timeout | Xem timeout, trạng thái transaction, idempotency |
| `SQLTransientConnectionException` | Vấn đề kết nối có thể phục hồi | Retry có giới hạn nếu operation an toàn |
| `SQLRecoverableException` | Lỗi cần bước phục hồi, có thể phải thay connection | Kiểm tra driver/docs và transaction |
| `SQLException` chung | Các lỗi khác, vendor-specific details | Phân loại SQLState, vendor code, cause |

Đoạn phản ví dụ:

~~~java
try {
    ps.setSQLXML(1, xml);
} catch (SQLException e) {
    ps.setString(1, xml.getString()); // Không có căn cứ schema.
}
~~~

Đây không phải cách fallback portable. Nó **che mất lỗi xác thực/mạng/SQL**, tự thay đổi kiểu dữ liệu và giả định SQLXML object vẫn đọc được. Với SQLXML read/write state, việc gọi `getString` sau `setString` không phải một quyền được đảm bảo ở mọi implementation.

## 4. SQLXML có nhiều điểm có thể không được driver hỗ trợ

~~~text
Connection
    |
    | createSQLXML()           [có thể unsupported]
    v
SQLXML object
    |
    | setString / setResult    [có thể lỗi format, conversion]
    v
PreparedStatement.setSQLXML()   [có thể unsupported overload]
    |
    | executeUpdate()          [có thể lỗi DB/column/schema/size]
    v
SQL XML column
    |
    | SELECT / ResultSet.getSQLXML()  [có thể unsupported read]
    v
SQLXML.getString/getSource/getCharacterStream
    |
    | free() trước khi rời transaction/scope
    v
Đóng ResultSet, Statement, Connection
~~~

Một driver có thể tạo SQLXML thành công nhưng không bind được trong một cột hoặc operation. Một driver khác có thể bind được nhưng không hỗ trợ một dạng XML Source/Result thuận tiện; hoặc DB có XML type vendor-specific không ánh xạ qua `Types.SQLXML`.

**SQLXML là hợp đồng API về SQL XML value**, không đồng nghĩa với một `VARCHAR` chứa đoạn text có dấu ngoặc XML. Chuyển cột XML typed sang text có thể làm thay đổi validation, indexing, XPath/XQuery support, storage layout, transaction semantics và security policy.

### 4.1. Các operations cụ thể

| API | Cần kiểm tra |
| --- | --- |
| `Connection.createSQLXML()` | Driver có tạo object XML không? |
| `SQLXML.setString(String)` | Có chấp nhận value representation? Lỗi có thể tới lúc bind/execute |
| `SQLXML.setCharacterStream()/setBinaryStream()` | Source/encoding/Writer lifecycle |
| `SQLXML.setResult(Class<T>)` | JAXP result format và driver conversion |
| `PreparedStatement.setSQLXML(int, SQLXML)` | Method + SQL column type support |
| `ResultSet.getSQLXML(int/String)` | Reading XML type, row/NULL và cursor lifetime |
| `SQLXML.getSource(Class<T>)` | XML parser Source support, bảo mật và memory |
| `SQLXML.free()` | Giải phóng tài nguyên sau khi driver dùng xong |

**Lưu ý:** một số lỗi được phát hiện muộn ở `executeUpdate` thay vì `setSQLXML`. Vì vậy chỉ catch quanh setter chưa đủ để đảm bảo toàn bộ thao tác lưu đã thành công.

### 4.2. Khi nào cần SQLXML native?

Chỉ khi sản phẩm/DB thực sự cần SQL XML type (ví dụ query XML trong DB, indexed XML paths hoặc validation ở database), việc thiếu SQLXML API có thể là blocker. Nếu ứng dụng chỉ muốn lưu raw XML text, một **text/CLOB column được thiết kế chủ động** có thể phù hợp hơn; nhưng phải định nghĩa chính sách validation/encoding/size và **không coi hai loại lưu trữ là tương đương**.

## 5. DatabaseMetaData không phải cờ hỗ trợ SQLXML tuyệt đối

`DatabaseMetaData.getTypeInfo()` trả metadata về các SQL data types mà database/driver công bố. Bạn có thể quan sát `DATA_TYPE` bằng `Types.SQLXML`:

~~~java
try (ResultSet types = connection.getMetaData().getTypeInfo()) {
    boolean reported = false;
    while (types.next()) {
        if (types.getInt("DATA_TYPE") == Types.SQLXML) {
            reported = true;
            break;
        }
    }
    System.out.println("reported-sqlxml-type=" + reported);
}
~~~

Đây là đoạn trích, cần `import java.sql.*;` và `connection` hợp lệ. **Không có stdout cố định**: kết quả phụ thuộc DB/driver. Nếu `reported==true` thì vẫn **chưa chứng minh** `createSQLXML`, `setSQLXML`, `getSQLXML` hoặc `getSource` chạy trên mọi SQL statement/cột. Nếu false, DB vẫn có thể cung cấp XML qua **vendor-specific type** hoặc text schema nhưng không được công bố như `Types.SQLXML`.

**Không có `DatabaseMetaData.supportsSQLXML()` để thay thế toàn bộ các bước test.**

### 5.1. Thang mức độ tin cậy

| Kiểm tra | Có ý nghĩa gì? | Giới hạn |
| --- | --- | --- |
| Compile source Java 17+ | Các API nằm trong JDK | Không có database |
| Driver version + DB product | Xác định tổ hợp môi trường | Không đủ quyết định từng method |
| `getTypeInfo()` có `Types.SQLXML` | Driver công bố SQL XML type | Chưa xác nhận operations |
| Tạo object SQLXML | Test creation | Chưa xác nhận binding/read |
| Bind và `executeUpdate` trên XML column | Test đường ghi | Chưa xác nhận đường đọc |
| SELECT + `getSQLXML` + round-trip | Test được workload cụ thể | Chưa chứng minh mọi encoding/size/schema |
| Large/XML security/integration tests | Đánh giá vận hành và rủi ro | Phụ thuộc dữ liệu, version, load |

Nếu chức năng bắt buộc SQL XML, **đánh giá ở startup/CI với database sandbox** và feature gate rõ ràng. Không ghi test payload vào bảng production có triggers/audit chỉ để thăm dò.

## 6. Ví dụ Java 17+ runnable: hỗ trợ, thiếu create và thiếu bind

Chương trình độc lập sử dụng **Java dynamic proxies** cho `Connection`, `PreparedStatement` và `SQLXML` để test các nhánh mà **không cần database server**. Có ba modes:

- `SUPPORTED`: mock hỗ trợ tạo/bind XML và lưu payload vào biến kiểm tra.
- `CREATE_UNSUPPORTED`: mock ném `SQLFeatureNotSupportedException` từ `Connection.createSQLXML()`.
- `BIND_UNSUPPORTED`: mock tạo XML được nhưng ném exception từ `PreparedStatement.setSQLXML(...)`.

Với `CREATE_UNSUPPORTED`, code xác nhận **không có silent fallback**; sau đó gọi riêng đường text column **được khai báo chủ động**. Với `BIND_UNSUPPORTED`, code xác nhận `SQLXML.free()` và JDBC close xảy ra dù lỗi.

**Không hiểu sai:** mock không chứa SQL parser, giao thức JDBC mạng hay XML type thật, và không phải bản mẫu để tự viết vendor JDBC driver. Kết quả chỉ kiểm thử **logic handling của ứng dụng**.

### 6.1. File UnsupportedSqlXmlDemo.java

~~~java
import java.lang.reflect.*;
import java.sql.*;

public final class UnsupportedSqlXmlDemo {
    private static final String XML = "<doc>Tiếng Việt</doc>";

    private enum Mode { SUPPORTED, CREATE_UNSUPPORTED, BIND_UNSUPPORTED }

    private static void check(boolean ok, String detail) {
        if (!ok) throw new AssertionError(detail);
    }

    private static SQLFeatureNotSupportedException unsupported(String operation) {
        return new SQLFeatureNotSupportedException(
                "Fixture does not support " + operation, "0A000");
    }

    private static final class XmlValue implements InvocationHandler {
        String value;
        boolean written;
        boolean freed;

        SQLXML proxy() {
            return (SQLXML) Proxy.newProxyInstance(
                    SQLXML.class.getClassLoader(), new Class<?>[]{SQLXML.class}, this);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            switch (method.getName()) {
                case "setString":
                    if (freed || written) throw new SQLException("XML no longer writable");
                    value = (String) args[0];
                    written = true;
                    return null;
                case "free":
                    freed = true;
                    return null;
                case "getString":
                    if (freed) throw new SQLException("XML has been freed");
                    return value;
                default:
                    throw unsupported("SQLXML." + method.getName());
            }
        }
    }

    private static final class Session implements InvocationHandler {
        final Mode mode;
        XmlValue xmlValue;
        String savedXml;
        String savedText;
        boolean connectionClosed;
        boolean statementClosed;

        Session(Mode mode) {
            this.mode = mode;
        }

        Connection connection() {
            return (Connection) Proxy.newProxyInstance(
                    Connection.class.getClassLoader(),
                    new Class<?>[]{Connection.class}, this);
        }

        private PreparedStatement statement(String sql) {
            InvocationHandler h = new InvocationHandler() {
                boolean bound;
                String localValue;

                @Override
                public Object invoke(Object proxy, Method method, Object[] args)
                        throws Throwable {
                    switch (method.getName()) {
                        case "setSQLXML":
                            if (mode == Mode.BIND_UNSUPPORTED)
                                throw unsupported("PreparedStatement.setSQLXML");
                            check(sql.startsWith("INSERT INTO xml_docs"), "wrong XML table");
                            check(((Integer) args[0]) == 1, "wrong index");
                            check(xmlValue != null && xmlValue.written, "XML missing");
                            localValue = xmlValue.value;
                            bound = true;
                            return null;
                        case "setString":
                            check(sql.startsWith("INSERT INTO text_docs"), "wrong text table");
                            check(((Integer) args[0]) == 1, "wrong index");
                            localValue = (String) args[1];
                            bound = true;
                            return null;
                        case "executeUpdate":
                            check(bound, "SQL parameter not bound");
                            if (sql.startsWith("INSERT INTO xml_docs"))
                                savedXml = localValue;
                            else
                                savedText = localValue;
                            return 1;
                        case "close":
                            statementClosed = true;
                            return null;
                        case "isClosed":
                            return statementClosed;
                        default:
                            throw unsupported("PreparedStatement." + method.getName());
                    }
                }
            };
            return (PreparedStatement) Proxy.newProxyInstance(
                    PreparedStatement.class.getClassLoader(),
                    new Class<?>[]{PreparedStatement.class}, h);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            switch (method.getName()) {
                case "createSQLXML":
                    if (mode == Mode.CREATE_UNSUPPORTED)
                        throw unsupported("Connection.createSQLXML");
                    xmlValue = new XmlValue();
                    return xmlValue.proxy();
                case "prepareStatement":
                    return statement((String) args[0]);
                case "close":
                    connectionClosed = true;
                    return null;
                case "isClosed":
                    return connectionClosed;
                default:
                    throw unsupported("Connection." + method.getName());
            }
        }
    }

    static int insertTypedXml(Connection c, String xmlText) throws SQLException {
        SQLXML xml = c.createSQLXML();
        try {
            xml.setString(xmlText);
            try (PreparedStatement ps =
                         c.prepareStatement("INSERT INTO xml_docs(body) VALUES (?)")) {
                ps.setSQLXML(1, xml);
                return ps.executeUpdate();
            }
        } finally {
            xml.free(); // Java 17: SQLXML is not AutoCloseable.
        }
    }

    static int insertExplicitTextColumn(Connection c, String xmlText)
            throws SQLException {
        // Only for a schema deliberately defined with a text column.
        try (PreparedStatement ps =
                     c.prepareStatement("INSERT INTO text_docs(body_text) VALUES (?)")) {
            ps.setString(1, xmlText);
            return ps.executeUpdate();
        }
    }

    public static void main(String[] args) throws Exception {
        Session full = new Session(Mode.SUPPORTED);
        try (Connection c = full.connection()) {
            int count = insertTypedXml(c, XML);
            check(count == 1, "full insert");
        }
        check(XML.equals(full.savedXml), "full payload");
        check(full.xmlValue.freed, "SQLXML not released");
        check(full.connectionClosed && full.statementClosed, "JDBC resources not closed");
        System.out.println("typed-xml-insert=1");
        System.out.println("typed-xml-value=" + full.savedXml);
        System.out.println("typed-xml-freed=true");

        Session cannotCreate = new Session(Mode.CREATE_UNSUPPORTED);
        try (Connection c = cannotCreate.connection()) {
            try {
                insertTypedXml(c, XML);
                throw new AssertionError("createSQLXML should fail");
            } catch (SQLFeatureNotSupportedException expected) {
                check("0A000".equals(expected.getSQLState()), "SQLState lost");
                check(expected instanceof SQLNonTransientException, "exception hierarchy");
                System.out.println("create-unsupported-state=" + expected.getSQLState());
            }
            check(cannotCreate.savedXml == null
                    && cannotCreate.savedText == null, "unexpected hidden fallback");
            System.out.println("silent-fallback=false");

            int rows = insertExplicitTextColumn(c, XML);
            check(rows == 1 && XML.equals(cannotCreate.savedText),
                    "explicit text schema path");
        }
        System.out.println("explicit-text-insert=1");
        System.out.println("text-column-value=" + cannotCreate.savedText);

        Session cannotBind = new Session(Mode.BIND_UNSUPPORTED);
        try (Connection c = cannotBind.connection()) {
            try {
                insertTypedXml(c, XML);
                throw new AssertionError("setSQLXML should fail");
            } catch (SQLFeatureNotSupportedException expected) {
                check("0A000".equals(expected.getSQLState()), "bind SQLState");
                System.out.println("bind-unsupported-state=" + expected.getSQLState());
            }
        }
        check(cannotBind.xmlValue != null && cannotBind.xmlValue.freed,
                "SQLXML must be freed even if binding fails");
        check(cannotBind.statementClosed && cannotBind.connectionClosed,
                "failed resources not closed");
        check(cannotBind.savedXml == null, "failed write should not execute");
        System.out.println("failed-bind-freed=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 6.2. Biên dịch và chạy

Ở thư mục chứa `UnsupportedSqlXmlDemo.java`:

~~~bash
javac -encoding UTF-8 --release 17 UnsupportedSqlXmlDemo.java
java UnsupportedSqlXmlDemo
~~~

Stdout **chính xác** đã kiểm chứng trên OpenJDK 24 với `--release 17`:

~~~text
typed-xml-insert=1
typed-xml-value=<doc>Tiếng Việt</doc>
typed-xml-freed=true
create-unsupported-state=0A000
silent-fallback=false
explicit-text-insert=1
text-column-value=<doc>Tiếng Việt</doc>
bind-unsupported-state=0A000
failed-bind-freed=true
tests=PASS
~~~

### 6.3. Giải thích kết quả

- `typed-xml-insert=1` và `typed-xml-value=...`: proxy giả lập successful typed XML binding; không có INSERT vào database.
- `typed-xml-freed=true`: gọi `SQLXML.free()` sau đường thành công.
- `create-unsupported-state=0A000`: proxy ném exception **có SQLState do mock định nghĩa** ở bước tạo.
- `silent-fallback=false`: chương trình **không** tự chuyển typed XML operation sang text khi exception xuất hiện.
- `explicit-text-insert=1`: **sau khi được quyết định rõ**, chương trình gọi đường lưu text khác, giả định schema text được thiết kế từ trước.
- `bind-unsupported-state=0A000`: tạo SQLXML thành công nhưng bind bị từ chối; hai bước phải được kiểm tra riêng.
- `failed-bind-freed=true`: `SQLXML.free()` được gọi trong `finally` dù statement bind thất bại.
- `tests=PASS`: fixture assertions và cleanup checks hoàn tất. Đây là **mock contract test**, không phải vendor compatibility report.

### 6.4. Không suy ra điều gì từ mock?

Mock không xác minh XML type thật, XML validation tại DB, commit/rollback, SQL syntax của bất kỳ vendor, size limits, charset conversion, network timeout, parser XXE hay hiệu năng. Nó **chỉ xác minh code Java xử lý đúng exception và lifetime**. Muốn khẳng định production hỗ trợ SQLXML, phải chạy **integration test với DB thật**.

## 7. SQLXML lifecycle trên Java 17 và Java 26

### 7.1. Tạo, set, bind, execute, free

Mẫu tương thích Java17:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<doc>Tiếng Việt</doc>");
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_docs(body) VALUES (?)")) {
        ps.setSQLXML(1, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
~~~

**Đoạn trích**: database phải hỗ trợ SQL XML column và caller quản lý Connection/transaction. `free()` ở `finally` là quan trọng để release cả khi setter/execution ném SQLException. Không gọi `free` trước lúc driver tiêu thụ XML xong; driver có thể trì hoãn đọc/conversion tới execute.

### 7.2. SQLXML chưa AutoCloseable ở Java 17

- **Java 17:** `SQLXML` **không extends `AutoCloseable`**; dùng `xml.free()`, không viết `try (SQLXML xml = ...)` với `--release 17`.
- **Java 26/JDBC 4.5:** `SQLXML` và các SQL data objects như `Blob/Clob/NClob/Array` đã extends `AutoCloseable` với `close()`, cho phép dùng try-with-resources khi build/run theo JDK tương ứng.
- `Connection`/`PreparedStatement`/`ResultSet` đã AutoCloseable từ **Java 7/JDBC 4.1**, nên ví dụ Java17 sử dụng try-with-resources cho chúng bình thường.

Đừng dạy SQLXML AutoCloseable như tính năng Java 6; đây là thay đổi mới hơn. Nếu cần code **cùng chạy dưới Java17**, hãy dùng `free()`.

### 7.3. SQLXML có read/write state và transaction lifetime

SQLXML object có thể là **logical pointer** tới dữ liệu DB, thường hợp lệ trong transaction mà nó được tạo. Các đường `getString/getSource/getCharacterStream` và `setString/setResult/setCharacterStream` có quy tắc state; không tự do đọc/ghi lặp nhiều lần và dùng sau `free`. Một số driver có thể đánh dấu object không còn readable/writable sau một operation.

Nếu dùng `setCharacterStream()`, **đóng Writer** trước khi `setSQLXML` để bảo đảm XML hoàn chỉnh. Nếu dùng `getSource`, parser/XSLT phải được cấu hình an toàn; không tự tin rằng XML được bảo vệ XXE chỉ vì nó đi qua JDBC.

### 7.4. Cleanup error và lỗi gốc

`xml.free()` cũng khai báo `throws SQLException`. Nếu `setSQLXML` thất bại và `free` tiếp tục thất bại, một khối `finally` đơn giản có thể làm mất dấu lỗi ban đầu; trong framework nghiêm ngặt cần bảo tồn primary exception/suppressed cleanup error hoặc log cả hai theo policy. **Không bỏ qua cleanup errors** khi chúng báo khả năng rò rỉ tài nguyên DB.

## 8. Repository thật: DataSource, SQLXML và metadata

Khi có `javax.sql.DataSource` đã cấu hình với driver/database, repository có thể ghi XML bằng `createSQLXML`/`setSQLXML`, đọc XML bằng `getSQLXML` và dùng `getTypeInfo()` như một tín hiệu hỗ trợ kiểu.

### 8.1. File RealSqlXmlRepository.java

~~~java
import java.sql.*;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class RealSqlXmlRepository {
    private final DataSource dataSource;

    public RealSqlXmlRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int insertXml(long id, String xmlText) throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            SQLXML xml = c.createSQLXML();
            try {
                xml.setString(xmlText);
                try (PreparedStatement ps = c.prepareStatement(
                        "INSERT INTO xml_docs(id, body) VALUES (?, ?)")) {
                    ps.setLong(1, id);
                    ps.setSQLXML(2, xml);
                    return ps.executeUpdate();
                }
            } finally {
                xml.free();
            }
        }
    }

    public Optional<String> findXml(long id) throws SQLException {
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT body FROM xml_docs WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return Optional.empty();
                SQLXML xml = rs.getSQLXML("body");
                if (xml == null) return Optional.empty();
                try {
                    return Optional.ofNullable(xml.getString());
                } finally {
                    xml.free();
                }
            }
        }
    }

    public boolean reportsSqlXmlType() throws SQLException {
        try (Connection c = dataSource.getConnection();
             ResultSet types = c.getMetaData().getTypeInfo()) {
            while (types.next()) {
                if (types.getInt("DATA_TYPE") == Types.SQLXML) return true;
            }
            return false;
        }
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 --release 17 RealSqlXmlRepository.java
~~~

**Đã biên dịch thành công bằng OpenJDK 24 với `--release 17`.** Tệp không có `main()`; code **chưa được chạy với vendor DB**, vì cần driver, `DataSource`, DB credentials/permissions và bảng `xml_docs(id, body)` với kiểu cột XML tương thích. DDL/XML type khác nhau giữa DBMS nên không tự đưa ra SQL CREATE TABLE portable giả.

### 8.2. Optional.empty trong findXml

Code trả `Optional.empty()` khi **không có row** hoặc khi row có XML SQL NULL. Đây là **lựa chọn của repository mẫu**, không phải yêu cầu của JDBC. Nếu domain phải phân biệt “row không tồn tại” và “row có body NULL”, xây DTO/result type riêng.

### 8.3. XML lớn không nên gọi getString vô điều kiện

`SQLXML.getString()` có thể tạo String lớn; nếu XML tài liệu cỡ hàng trăm MB, nên xem `getCharacterStream/getBinaryStream/getSource`, parser streaming và giới hạn tài nguyên theo driver. Đừng trả SQLXML object/Reader phụ thuộc ResultSet sau khi đã đóng connection hoặc kết thúc transaction.

### 8.4. Transactions và connection pool

Hai lời gọi `insertXml`/`findXml` trong code mỗi lần mở một Connection riêng, không đảm bảo thuộc **cùng một transaction**. Nếu workflow cần atomicity, quản lý ở tầng transaction manager hoặc truyền Connection đang trong transaction. Với DataSource có pool, `close` thường trả logical Connection vào pool; SQLXML không được giữ qua phạm vi ấy.

## 9. Chính sách fallback an toàn

### 9.1. Không có silent fallback cho SQL XML typed semantics

Khi sản phẩm bắt buộc có SQL XML type (validation trong DB, XML SQL operators, indexed XML paths), driver thiếu `createSQLXML` là **blocker**. Không chuyển ngay sang `setString` trên cột XML rồi coi như bảo đảm tính tương đương.

### 9.2. Khi text storage là một thiết kế hợp lệ

Nếu sản phẩm **chỉ lưu một XML document như text**, bạn có thể chủ động thiết kế `VARCHAR/CLOB/TEXT` column (theo DBMS), dùng `PreparedStatement.setString/setCharacterStream` và tự chịu trách nhiệm XML validation/security. Nhưng đây là **một storage contract khác**:

- DB có thể không tự kiểm tra XML well-formedness hoặc XSD.
- XML-specific operators/indexes không được bảo đảm.
- Charset, collation, size và truncation khác XML native.
- Parser phía ứng dụng phải chống XXE/DTD resource abuse.
- Việc đổi schema/đường query cần migration/test, không thể do catch block quyết định ngầm.

**Chỉ dùng fallback khi có quyết định rõ từ trước**, đã thiết kế schema và test round-trip. Nếu không, báo lỗi thiếu capability.

### 9.3. Phản ví dụ nguy hiểm

~~~java
try {
    xmlStmt.setSQLXML(1, xml);
} catch (SQLException ignored) {
    xmlStmt.setString(1, xml.getString()); // Sai: schema và XML state chưa rõ.
}
xmlStmt.executeUpdate();                  // Có thể ghi dữ liệu sai.
~~~

Đây là đoạn phản ví dụ. Nó che mọi `SQLException`, dùng lại một SQLXML state có thể không đọc hợp lệ, tự thay data type và có nguy cơ ghi sai vào cột. Hướng đúng là không execute nếu bind thất bại, phân loại lỗi, rollback/cleanup và chọn policy phù hợp.

## 10. Chẩn đoán thiếu driver capability

Không nên chỉ log một chuỗi “DB error”. Tập thông tin hữu ích (đã lọc secrets):

| Trường | Ý nghĩa |
| --- | --- |
| Operation | `createSQLXML`, `setSQLXML`, `getSQLXML`, `getSource` hay execute |
| Exception class | `SQLFeatureNotSupportedException` hay `SQLException` subclass khác |
| SQLState | Có thể null; class `0A` nếu có |
| Vendor error code | `SQLException.getErrorCode()` |
| Cause / next exceptions | `getCause()`, `getNextException()`, chained SQLExceptions |
| Driver/DB product version | Giúp lập capability matrix chính xác |
| SQL column type | Native SQL XML, vendor-specific XML, text/CLOB? |
| Environment | JDK version, driver artifact version, connection config (không log credentials) |
| Payload limits | Kích thước lớn/encoding/schema validation có thể liên quan |

### 10.1. Catch theo kiểu cụ thể

~~~java
try {
    writeXml();
} catch (SQLFeatureNotSupportedException unsupported) {
    // Dừng đường SQLXML typed; báo feature unsupported theo policy.
    throw unsupported;
} catch (SQLException databaseError) {
    // Lỗi DB khác: syntax, constraint, timeout, connection...
    throw databaseError;
}
~~~

Đây là đoạn trích; `writeXml()` cần được định nghĩa và method chứa code phải cho phép `throws SQLException`. Nhánh **subclass** phải đặt trước `SQLException`. Trên driver không trả chính xác subclass, có thể cần đọc SQLState/vendor code để chẩn đoán, nhưng **không ép cast** hoặc assume mọi `SQLException` là unsupported.

### 10.2. SQLState có thể null

Không viết `e.getSQLState().startsWith("0A")` nếu không kiểm tra null. Khi kiểm tra, nên dựa trên **exception class + SQLState + operation + version**, không chỉ một field. Một `SQLFeatureNotSupportedException` không có state vẫn mang ý nghĩa unsupported theo class, và ngược lại một SQLException với SQLState 0A có thể đến từ implementation vendor riêng.

### 10.3. Không log XML raw hoặc JDBC URL chứa secrets

XML có thể chứa PII/tài liệu kinh doanh; JDBC URL/SQLException có thể chứa host, username hoặc credentials. Log correlation ID, operation và metadata đã được loại bỏ bí mật. Trên UI, hiển thị thông báo khả năng không hỗ trợ thay vì raw stacktrace.

## 11. Bảo mật XML: SQLXML không tự chặn XXE

`SQLXML` chỉ là API chuyển SQL XML data. Nếu ứng dụng parse XML từ user hoặc từ DB, còn phải lo:

- **XXE**: external entity có thể truy cập file/network không được phép.
- **DTD/entity expansion**: CPU/memory/resource exhaustion.
- **Payload quá lớn, XML depth quá sâu, số element/attribute quá nhiều**.
- **XML schema validation**: app-level business rules vẫn cần.
- **Encoding**: Byte stream XML và Java String/Reader khác nhau.
- **Reader/Writer/Source/Result lifecycle**: dữ liệu phải hoàn tất trước bind/parse.
- **SQL injection**: XML text phải bind qua `PreparedStatement`, không nối vào SQL.

Nếu ứng dụng dùng DOM/SAX/StAX/JAXP, cấu hình hạn chế external DTD/schema/network, dùng `XMLConstants.FEATURE_SECURE_PROCESSING` và parser-specific flags để chặn external entity, giới hạn kích thước/độ sâu và **fail-closed nếu parser không hỗ trợ security settings bắt buộc**.

`xml.setString(...)` thành công **không chứng minh** XML đã được DB validate theo XSD, không chứng minh app không bị XXE và không chứng minh mọi XML operators hoạt động. Cần test đúng luồng parse/validation và DB vendor.

## 12. Ngoài SQLXML: những trường hợp driver unsupported còn gặp

| Feature | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| National character types | `setNClob`, `setNCharacterStream` | Có SQL national type/overload không? |
| Large objects | `createBlob/createClob/createNClob` | DB/driver hỗ trợ LOB type không? |
| Row identifier | `ResultSet.getRowId` | DBMS có ROWID mapping không? |
| Scrollable/updatable result sets | `TYPE_SCROLL_SENSITIVE`, `CONCUR_UPDATABLE` | Cặp type/concurrency có hỗ trợ, query có updatable không? |
| Generated keys | `RETURN_GENERATED_KEYS` | Driver/schema/statement có trả key không? |
| SQLType overloads | `setObject(..., SQLType)` | JDBC 4.2+, default method có thể throw |
| Sharding | `setShardingKeyIfValid` | JDBC 4.3+, default có thể throw unsupported |
| SQL XML | `createSQLXML/setSQLXML/getSQLXML` | Test từng operation + column type |

**Lịch sử phải đúng:** `SQLXML` và `SQLFeatureNotSupportedException` ra đời JDBC4.0/Java6, nhưng `SQLType` và sharding được bổ sung sau này. Trình bày chúng ở đây vì cách xử lý exception vẫn hữu ích trong Java hiện đại, không phải để dạy API lỗi thời.

**Không nhầm với `UnsupportedOperationException`** của Java Collections hoặc các APIs khác. JDBC dùng `SQLFeatureNotSupportedException` cho những optional JDBC capabilities được mô tả bằng `SQLException` contract.

## 13. Kiểm thử trên driver/database thật

Mock trong mục 6 chỉ test xử lý exception, cần integration test với vendor và DB server cụ thể.

| Test case | Hành động | Kết quả cần xác minh |
| --- | --- | --- |
| Create | `Connection.createSQLXML()` | Tạo được hay unsupported rõ? |
| Write object | `SQLXML.setString/setCharacterStream` | Dữ liệu đúng, errors được phân loại |
| Bind | `PreparedStatement.setSQLXML` | Driver nhận XML |
| Execute & commit | INSERT vào XML column thử nghiệm | Lưu đúng SQL XML semantics |
| Read | SELECT và `ResultSet.getSQLXML` | Round-trip nội dung và SQL NULL |
| Source | `SQLXML.getSource(...)` | Hỗ trợ parser/source class cần dùng |
| Free | `SQLXML.free()` cả thành công/thất bại | Không leak resource |
| Metadata | `getTypeInfo()` có/không `Types.SQLXML` | Hiểu đây chỉ là metadata |
| Error class/state | SQLState class `0A`, vendor code, cause | Không đánh đồng mọi SQLException |
| UTF-8/Unicode | Tiếng Việt, emoji, XML namespaces | Không mất ký tự |
| Malformed XML | Invalid XML declaration/structure | DB/app validation xử lý hợp lệ |
| Large XML | Nhiều MB, streaming | Memory/timeout/quota đáp ứng |
| Security | XXE/DTD/large entity inputs | Parser an toàn, không external access |
| Cross-version | Nâng JDK/driver/DBMS | Capability matrix được kiểm tra lại |

### 13.1. Không đưa probe vào dữ liệu production tùy tiện

INSERT thử có thể kích hoạt triggers/transaction commits/audit. Dùng schema riêng, dữ liệu không nhạy cảm, rollback/cleanup an toàn. Nếu dùng auto-commit, probe có thể để lại row; không tự gọi thử rồi mặc định mọi thử nghiệm đều vô tác động.

### 13.2. Không xem một test PASS là chứng nhận vĩnh viễn

Một tính năng có thể hỗ trợ trên driver A + DB version X nhưng không hỗ trợ trên driver B hoặc khi đổi SQL column type. Ghi rõ:

- JDK release.
- Driver artifact/version, pool wrappers.
- DB product/version/edition.
- SQL column type/schema.
- Operation đã test: create, bind, execute, read, stream.
- XML size, namespaces, encoding và security.
- Transaction behavior và permissions.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Java compile nhưng `createSQLXML` fail | Driver thiếu XML type | Fail rõ, kiểm tra vendor/schema |
| `setSQLXML` fail sau create thành công | Support không đồng nhất giữa operations | Free object, không execute partial write |
| Retry liên tục unsupported | Exception non-transient | Dừng và chọn feature policy |
| `getSQLState()==null` gây NPE | Driver/constructor không có state | Kiểm tra null |
| Coi mọi `SQLException` là unsupported | Lỗi network/syntax/constraint khác | Phân loại class/state/cause |
| `getTypeInfo` có SQLXML là kết luận đủ | Metadata chưa xác minh runtime | Test round-trip |
| Coi JDBC4.x driver hỗ trợ mọi XML | XML optional capability | Test per vendor/schema |
| `setString` fallback tự động trên XML column | SQL type semantics không rõ | Explicit text design hoặc báo lỗi |
| `free` trước execute | SQLXML object bị release quá sớm | Free trong finally sau execute |
| Giữ SQLXML qua connection close | Object có thể là logical pointer | Dùng trong transaction/scope |
| Dùng `try(SQLXML)` với `--release 17` | Java17 SQLXML không AutoCloseable | Dùng `free()` |
| `getString` nhiều lần trên object đã tiêu thụ | SQLXML có read/write states | Chọn một đường đọc đúng |
| Gọi setSQLXML khi Writer chưa đóng | XML content chưa hoàn tất | Đóng Writer trước bind |
| XML lớn gây OOM | `getString`/DOM buffer toàn bộ | Stream khi supported và size limits |
| XML chứa XXE | Parser không khóa external entities | Secure JAXP, fail-closed |
| Mock PASS bị hiểu là DB support | Proxy không chạy SQL | Vendor integration tests |

## 15. Câu hỏi và bài tập

**Câu 1.** `SQLFeatureNotSupportedException` thuộc nhóm transient hay non-transient?

**Đáp án:** Nó kế thừa `SQLNonTransientException`; retry ngay cùng một unsupported feature thường không giúp.

**Câu 2.** SQLState `0A` nghĩa gì?

**Đáp án:** Nhóm “feature not supported”. `0A000` là một mã thường gặp, nhưng SQLState thực có thể null hoặc khác theo driver.

**Câu 3.** Java có `Connection.createSQLXML()` thì có chắc driver hỗ trợ SQL XML không?

**Đáp án:** Không. Có API compile-time không chứng minh runtime capabilities.

**Câu 4.** Tạo được SQLXML nhưng `setSQLXML` ném lỗi thì sao?

**Đáp án:** Dừng typed XML operation, cleanup `SQLXML.free()`, xử lý exception. Không tự convert sang text trên cùng column.

**Câu 5.** Tại sao không dùng `getJDBCMajorVersion() >= 4` làm feature flag?

**Đáp án:** Version không bảo đảm các optional features/overloads/modes. Cần integration test theo operation và schema.

**Câu 6.** Java 17 có thể `try(SQLXML xml = ...)` không?

**Đáp án:** Không. `SQLXML` chưa AutoCloseable; gọi `free()` trong `finally`. Java26/JDBC4.5 có AutoCloseable/close.

**Câu 7.** Text column có tương đương SQL XML native không?

**Đáp án:** Không. XML validation, SQL operators, indexes, encoding/size policies khác; phải có thiết kế riêng.

**Câu 8.** `SQLXML.setString` có chặn XXE tự động không?

**Đáp án:** Không. An toàn XML parser/XXE và business validation cần xử lý riêng.

**Câu 9.** `getTypeInfo()` báo `Types.SQLXML` có đủ chứng minh `ResultSet.getSQLXML` không lỗi không?

**Đáp án:** Không. Metadata chỉ là dấu hiệu, cần test đọc với dữ liệu/cột thật.

**Câu 10.** Mock ở phần 6 PASS nói gì?

**Đáp án:** Logic exception handling, SQLState fixture và resource cleanup đúng như đã lập trình; không chứng minh driver/DB thực hỗ trợ.

### Bài tập thực hành

1. Đổi mode của fixture, assert cả lỗi create và bind trong hai test độc lập.
2. Thêm counter kiểm tra `xml.free()` được gọi đúng một lần khi bind thất bại.
3. Thay SQLState fixture bằng `"0A123"` và viết classifier theo **class 0A** chứ không hardcode `0A000`.
4. Khởi tạo `new SQLFeatureNotSupportedException("unsupported")` không truyền state rồi xử lý null an toàn.
5. Bổ sung mock `ResultSet.getSQLXML` unsupported để test đường đọc riêng.
6. Dùng `RealSqlXmlRepository` trên database sandbox có XML type và so sánh INSERT/SELECT round-trip.
7. Với database chỉ hỗ trợ text, định nghĩa **cột text riêng** và viết XML validation/parsing được khóa XXE.
8. Thử `SQLXML` trên Java17 và Java26 theo đúng compilation target, kiểm chứng khác biệt AutoCloseable.
9. Test XML Unicode có tiếng Việt/emoji, namespace và payload lớn với driver vendor.
10. Lập capability matrix per driver version gồm creation, binding, reading, Source/Result, cleanup, limits.

## 16. Tài liệu chính thức hiện hành

- [Java SE 26 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): quan hệ `SQLNonTransientException` và SQLState class `0A`.
- [Java SE 26 — SQLNonTransientException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientException.html): non-transient classification.
- [Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, chained exceptions.
- [Java SE 26 — SQLXML](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): read/write states, `free`/`close`, Source/Result.
- [Java SE 17 — SQLXML](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): `free()` và Java17 lifecycle.
- [Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createSQLXML` và exceptions.
- [Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML`.
- [Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML`.
- [Java SE 26 — CallableStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/CallableStatement.html): XML parameters.
- [Java SE 26 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getTypeInfo`.
- [Java SE 26 — Types](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): `Types.SQLXML`.
- [Java SE 26 — DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): kết nối cho ứng dụng.
- [Java SE 26 — java.sql package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.0, JDBC 4.5 và SQLXML AutoCloseable.
- [Java SE 26 — java.xml module](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/module-summary.html): XML/JAXP APIs và security configuration.

**Ghi nhớ:** `SQLFeatureNotSupportedException` biểu thị **một JDBC optional feature/overload/mode không được driver hỗ trợ**, thường không sửa được bằng retry mù quáng. Với SQLXML, khả năng **tạo, bind, execute, đọc và xử lý XML** phải được xác minh riêng trên driver/database/schema thật. Nếu thiếu capability, báo lỗi rõ ràng hoặc chọn một storage design khác **được chủ động thiết kế và kiểm thử**. Trên Java 17 dùng `SQLXML.free()` sau khi driver đã tiêu thụ giá trị, kể cả khi lỗi; quản lý XML security/XXE và resource limits ở application.
