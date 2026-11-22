# Chọn API LOB phù hợp phiên bản Spring và trình điều khiển

Trong Spring Framework Data Access, **LOB (Large OBject)** là dữ liệu lớn được lưu trong cơ sở dữ liệu dưới dạng nhị phân hoặc văn bản. Khi ghi ảnh, PDF, tệp đính kèm hoặc tài liệu dài bằng Spring JDBC, câu hỏi không chỉ là “dùng `BLOB` hay `CLOB`?” mà còn là: **Spring đang ở phiên bản nào, cột SQL thực chất thuộc kiểu gì, JDBC driver hỗ trợ cách ghi/đọc nào và dữ liệu lớn cần truyền theo luồng hay nạp hết vào bộ nhớ?**

Một ví dụ từ tài liệu cũ có thể dùng `LobHandler`, `LobCreator` hoặc `SqlLobValue`. Ví dụ hiện đại từ Spring 6.1.4 trở lên có thể dùng `SqlBinaryValue` và `SqlCharacterValue`, hoặc trực tiếp các phương thức JDBC. Hai họ API này **không hoàn toàn thay thế theo kiểu đổi tên lớp**: cách chọn `Types.BLOB`, `Types.CLOB`, `Types.LONGVARBINARY` hay `Types.LONGVARCHAR`, cách xử lý stream và khác biệt của database vẫn phải được kiểm tra.

Mục tiêu bài học: xác định đúng API theo phiên bản Spring; phân biệt `BLOB/CLOB` thật với `BYTEA/TEXT/VARBINARY`; quyết định khi nào dùng byte[]/String, stream hoặc JDBC callback; giữ đúng vòng đời stream và transaction; và kiểm thử lựa chọn với driver thật.

## 1. Xác định loại LOB trước khi chọn API

| Dữ liệu và cột | API đọc/ghi thường gặp | Lưu ý |
| --- | --- | --- |
| Dữ liệu nhị phân: cột SQL `BLOB` | `PreparedStatement.setBlob(...)` hoặc `setBinaryStream(...)` khi driver chấp nhận; `ResultSet.getBlob(...)`, `getBinaryStream(...)`, `getBytes(...)` | `Blob` có thể là đối tượng/locator cần kết nối còn mở |
| Nhị phân dài dạng `VARBINARY`, `LONGVARBINARY`, PostgreSQL `BYTEA` | `setBytes(...)`, `setBinaryStream(...)` và `getBytes(...)`/`getBinaryStream(...)` | Không tự khai báo `Types.BLOB` nếu DB không dùng BLOB thật |
| Văn bản dài kiểu `CLOB` | `setClob(...)`, `setCharacterStream(...)`, `getClob(...)`, `getCharacterStream(...)`, `getString(...)` | Luồng ký tự là `Reader`, khác `InputStream` nhị phân |
| Văn bản dài kiểu `LONGVARCHAR`, `TEXT`/`LONGTEXT` | `setString(...)`, `setCharacterStream(...)`, `getString(...)`/`getCharacterStream(...)` | Kiểu của DB có thể là TEXT thay vì CLOB |
| Văn bản quốc tế kiểu `NCLOB` | Các API `NClob`, `setNCharacterStream(...)`, `getNCharacterStream(...)` nếu driver và cột yêu cầu | Đừng mặc định mọi DB/driver hỗ trợ `NCLOB` giống nhau |

**LOB là khái niệm dữ liệu; `java.sql.Blob` và `java.sql.Clob` là kiểu giao diện JDBC; kiểu cột vật lý mới quyết định API nào phù hợp.** Ví dụ PostgreSQL `BYTEA` và PostgreSQL Large Object tham chiếu bằng `OID` là **hai cơ chế lưu trữ khác nhau**. Một cột `TEXT` của MySQL có thể chứa chuỗi lớn nhưng không nhất thiết phải dùng JDBC `Clob`.

Với dữ liệu nhỏ và có giới hạn, `byte[]` hoặc `String` thường đơn giản hơn. Với tệp lớn, ưu tiên stream/callback để tránh giữ đồng thời nhiều bản sao của toàn bộ nội dung trong heap. “Dùng stream” cũng không tự bảo đảm driver sẽ không buffer: phải kiểm chứng tiêu thụ bộ nhớ và hành vi của driver.

## 2. Bảng phiên bản Spring: API nào nên dùng?

| Phiên bản Spring Framework | API khả dụng và trạng thái | Hướng sử dụng |
| --- | --- | --- |
| Spring 5.3.x và Spring 6.0.x | Các API lịch sử như `LobHandler`, `DefaultLobHandler`, `LobCreator`, `SqlLobValue` được dùng rộng rãi; JDBC trực tiếp luôn khả dụng | Duy trì khi hệ thống hiện có phụ thuộc vào cách xử lý riêng của driver; có thể dùng `JdbcTemplate` với `PreparedStatement`/`ResultSet` trực tiếp |
| Spring 6.1.0–6.1.3 | Các API LOB truyền thống vẫn có; **chưa có** `SqlBinaryValue`/`SqlCharacterValue` | Đừng copy mã dùng hai lớp mới vào project chưa nâng ít nhất lên 6.1.4 |
| Từ Spring **6.1.4** đến hết nhánh 6.1.x | Có `org.springframework.jdbc.core.support.SqlBinaryValue` và `SqlCharacterValue`; legacy API vẫn có | Ưu tiên thử hai giá trị mới cho thao tác ghi thông thường, kết hợp SQL type phù hợp |
| Spring **6.2.x** | `LobHandler`, `DefaultLobHandler`, `LobCreator`, `SqlLobValue`, các callback helper LOB cũ được đánh dấu `@Deprecated(since = "6.2")`; hai lớp mới vẫn được hỗ trợ | Chọn `SqlBinaryValue`/`SqlCharacterValue` hoặc JDBC trực tiếp cho mã mới; hạn chế phụ thuộc mới vào API đã deprecated |
| Spring 7.x | Kiểm tra Javadoc của **đúng phiên bản artifact đang chạy**: một số legacy API còn hiển thị nhưng ở trạng thái deprecated trong các bản đã công bố | Không giả định deprecated nghĩa là đã bị xóa, cũng không dựa vào nó để bảo đảm tương thích ở bản tương lai |

**Mốc cần ghi nhớ là 6.1.4 (có API mới) và 6.2 (deprecated API cũ).** Tên version của Spring Boot và version Spring Framework không đồng nhất; ứng dụng Boot thường quản lý phiên bản framework qua dependency management. Hãy xem cây dependency thực tế thay vì suy đoán từ bài hướng dẫn.

Có thể kiểm tra bản framework trong Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc
~~~

Trong Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-jdbc --configuration runtimeClasspath
~~~

Với ứng dụng nhiều module, chạy lệnh tại module có dependency JDBC phù hợp. Hai lệnh trên **kiểm tra dependency**, không chứng minh API đã hoạt động với database.

### Nhóm API hiện đại

- `SqlBinaryValue`: tạo từ `byte[]`, `InputStream + length`, `InputStreamSource + length` hoặc Spring `Resource`; nó triển khai `SqlTypeValue`, dùng làm tham số của `JdbcTemplate`/`JdbcClient`.
- `SqlCharacterValue`: tạo từ `CharSequence`, `char[]`, `Reader + length`, hoặc ASCII `InputStream + length`; cũng triển khai `SqlTypeValue`.
- `SqlParameterValue`: **tùy chọn** bọc thêm SQL type, ví dụ `new SqlParameterValue(Types.BLOB, new SqlBinaryValue(bytes))`. Chỉ đưa `Types.BLOB` khi cột/driver là BLOB thực sự; tương tự `Types.CLOB` cho CLOB thật.
- `JdbcTemplate` với `PreparedStatement` callback: dùng khi cần kiểm soát rõ phương thức `setBytes`, `setBinaryStream`, `setBlob`, `setClob`, stream length hoặc ngoại lệ driver.
- Khi đọc, `ResultSet.getBytes`, `getString`, `getBinaryStream`, `getCharacterStream` là đường đọc tự nhiên; callback Spring giúp đóng ResultSet/statement sau khi hoàn tất.

`JdbcClient` (xuất hiện trong Spring 6.1) cung cấp API truy vấn theo fluent style nhưng **không tự thay đổi quy tắc của JDBC driver đối với LOB**. Bài này tập trung `JdbcTemplate` để nhìn rõ thao tác; nguyên tắc chọn kiểu và quản lý tài nguyên vẫn áp dụng khi dùng `JdbcClient`.

## 3. Quy trình chọn API: hỏi đúng bốn câu

**Câu 1 — Spring Framework chạy bản nào?** Nếu thấp hơn 6.1.4, không sử dụng hai lớp `SqlBinaryValue`/`SqlCharacterValue`. Từ 6.1.4, ưu tiên chúng cho thao tác ghi thông thường. Từ 6.2, tránh viết mã mới gắn chặt `SqlLobValue`/`LobHandler` nếu không có lý do tương thích cụ thể.

**Câu 2 — Cột SQL thuộc kiểu gì?** Phân biệt `BLOB` thật với `BYTEA`/`VARBINARY`, `CLOB` thật với `TEXT`/`LONGVARCHAR`. Chỉ rõ SQL type theo DDL và theo driver. Tên “LOB” trong nghiệp vụ không đủ để suy ra `Types.BLOB`.

**Câu 3 — Dung lượng và đường truyền?** Với vài KB và dữ liệu sẵn trong memory, byte[]/String đơn giản. Với hàng chục/hàng trăm MB, xem xét stream và khả năng driver hỗ trợ `setBinaryStream`/`setBlob(InputStream, length)` hoặc `setCharacterStream`/`setClob(Reader,length)`. Chú ý kích thước là byte đối với binary stream nhưng là **số ký tự** đối với character stream.

**Câu 4 — Driver thật hỗ trợ API nào?** Nếu `SqlBinaryValue` gửi xuống một JDBC setter mà driver không xử lý đúng cho cột đó, dùng callback `PreparedStatement` để gọi setter cần thiết. Đo và kiểm thử với đúng database, JDBC driver, phiên bản, SQL type, chế độ transaction và kích thước thật.

~~~text
Spring < 6.1.4?
  ├─ Có → JDBC PreparedStatement / legacy LobHandler- SqlLobValue nếu phù hợp
  └─ Không → Ưu tiên SqlBinaryValue / SqlCharacterValue cho thao tác ghi
                |
                v
       DDL là BLOB/CLOB thật?
         ├─ Có → thử Types.BLOB / Types.CLOB + driver phù hợp
         └─ Không → dùng kiểu nhị phân/văn bản thật;
                     không ép BLOB/CLOB
                |
                v
     Driver xử lý stream/locator ổn?
         ├─ Có → giữ API đơn giản, kiểm thử round-trip
         └─ Không → PreparedStatement callback + setter thích hợp
~~~

Sơ đồ này là cách ra quyết định; bước **kiểm thử driver thực** luôn bắt buộc trước khi khẳng định tính tương thích.

## 4. Ví dụ Java 17 chạy được với Spring 6.2 và H2

Ta tạo một bảng thật chứa `BLOB` và `CLOB`, ghi bằng `SqlBinaryValue`/`SqlCharacterValue` với `SqlParameterValue` chỉ rõ loại SQL, rồi đọc lại bằng JDBC getters. H2 giúp ví dụ không cần máy chủ database riêng.

Cấu trúc:

~~~text
lob-api-demo/
├── pom.xml
└── src/main/java/example/LobApiDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>lob-api-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.LobApiDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/LobApiDemo.java`:

~~~java
package example;

import java.sql.Types;
import java.util.Arrays;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.support.SqlBinaryValue;
import org.springframework.jdbc.core.support.SqlCharacterValue;

public final class LobApiDemo {

    record Loaded(byte[] payload, String description) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:lob_api_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE lob_entry (
                    id BIGINT PRIMARY KEY,
                    payload BLOB NOT NULL,
                    description CLOB NOT NULL
                )
                """);

        byte[] bytes = {0, 1, 2, 127, (byte) 255, 42};
        String description = "Xin chào – LOB tiếng Việt";

        int affected = jdbc.update(
                "INSERT INTO lob_entry (id, payload, description) VALUES (?, ?, ?)",
                7L,
                new SqlParameterValue(
                        Types.BLOB,
                        new SqlBinaryValue(bytes)
                ),
                new SqlParameterValue(
                        Types.CLOB,
                        new SqlCharacterValue(description)
                )
        );

        Loaded loaded = jdbc.queryForObject(
                "SELECT payload, description FROM lob_entry WHERE id = ?",
                (rs, rowNum) -> new Loaded(
                        rs.getBytes("payload"),
                        rs.getString("description")
                ),
                7L
        );

        System.out.println("rows=" + affected);
        System.out.println("binaryBytes=" + loaded.payload().length);
        System.out.println("binaryMatches="
                + Arrays.equals(bytes, loaded.payload()));
        System.out.println("textMatches="
                + description.equals(loaded.description()));
    }
}
~~~

Với JDK 17+ và Maven trong thư mục `lob-api-demo`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình in ra trong môi trường H2 nêu trên:

~~~text
rows=1
binaryBytes=6
binaryMatches=true
textMatches=true
~~~

**Giải thích:** Bảng H2 có cột `BLOB`/`CLOB` thật nên trong ví dụ này `Types.BLOB`/`Types.CLOB` phù hợp. Hai giá trị Spring chuẩn bị tham số; `JdbcTemplate` tạo `PreparedStatement`, truyền sang H2, thực thi `INSERT`, rồi mapping `ResultSet` dùng `getBytes` và `getString`. `Arrays.equals` kiểm tra nội dung nhị phân từng byte, kể cả `0xFF` — không biến tệp nhị phân thành `String`. `String.equals` kiểm tra chính xác Unicode văn bản.

Đây là **round-trip nhỏ, nạp dữ liệu vào bộ nhớ** để làm rõ API. Kết quả chạy được trên H2 không chứng minh PostgreSQL, Oracle hay SQL Server sẽ tiếp nhận cùng cách đặt SQL type. Cần chạy integration test riêng trên database đích.

### Vì sao không luôn truyền `Types.BLOB`?

Khi cột có kiểu binary thông thường (không phải JDBC BLOB), driver có thể yêu cầu `setBytes` hoặc `setBinaryStream` và một SQL type như `Types.LONGVARBINARY`. Với cột văn bản kiểu `TEXT`/`LONGVARCHAR`, một SQL type như `Types.LONGVARCHAR` có thể phù hợp hơn `Types.CLOB`. `SqlBinaryValue` và `SqlCharacterValue` thường có thể hoạt động **không cần ép type** vì nhiều driver tự xử lý; nếu thêm type hint thì phải dựa vào DDL và driver. Không dùng cùng một `Types.BLOB` cho mọi DB chỉ vì nội dung là ảnh.

## 5. Streaming khi dữ liệu lớn hơn bộ nhớ thuận tiện

### 5.1. Ghi stream với lớp mới

Khi cần truyền nội dung của tệp, `SqlBinaryValue(InputStream, long length)` nhận một luồng byte và chiều dài byte. Với văn bản, `SqlCharacterValue(Reader, long length)` nhận một `Reader` và số **ký tự**. Có thể truyền `-1` nếu chưa biết độ dài, nhưng không phải driver nào cũng hỗ trợ overload không có length tốt như nhau.

Đoạn sau **minh họa trong ứng dụng đã có `JdbcTemplate jdbc`, bảng `lob_entry` và id 7**, không phải chương trình độc lập thứ hai:

~~~java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Types;

import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.support.SqlBinaryValue;
import org.springframework.jdbc.core.support.SqlCharacterValue;

// binaryFile và textFile là Path đã được ứng dụng kiểm soát.
try (InputStream binaryInput = Files.newInputStream(binaryFile);
     Reader textReader = Files.newBufferedReader(
             textFile, StandardCharsets.UTF_8)) {

    long bytes = Files.size(binaryFile);

    jdbc.update(
            "UPDATE lob_entry SET payload = ?, description = ? WHERE id = ?",
            new SqlParameterValue(
                    Types.BLOB, new SqlBinaryValue(binaryInput, bytes)),
            new SqlParameterValue(
                    Types.CLOB, new SqlCharacterValue(textReader, -1)),
            7L
    );
}
~~~

Đặt `try-with-resources` **bao quanh lúc gọi JDBC**, không đóng `InputStream`/`Reader` trước khi `update` thực thi. Chú ý `Files.size(textFile)` trả số **byte**, không phải số ký tự Unicode, nên không dùng nó trực tiếp làm `Reader length`. Nếu driver đòi độ dài ký tự chính xác, tính/biết trước số ký tự hoặc dùng chiến lược nạp theo yêu cầu nghiệp vụ. Với `-1`, hãy kiểm tra JDBC driver có hỗ trợ stream không biết độ dài hay không.

`SqlBinaryValue(Resource)` có thể lấy độ dài qua `Resource.contentLength()`. Tuy nhiên, không phải mọi `Resource` đều biết độ dài không tốn kém; ví dụ nguồn chỉ đọc một lần có thể bị tiêu thụ khi hỏi kích thước. Hãy dùng nguồn có thể mở lại hoặc truyền độ dài rõ ràng. Không mặc định `InputStreamSource` hay `Resource` luôn mở stream mới vô hạn.

### 5.2. Đọc stream: tiêu thụ khi ResultSet còn mở

Đoạn sau viết BLOB vào tệp kết quả; nó nằm trong một phương thức ứng dụng đã có `JdbcTemplate jdbc`, `long id` và `Path target`:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Boolean found = jdbc.query(
        "SELECT payload FROM lob_entry WHERE id = ?",
        rs -> {
            if (!rs.next()) {
                return false;
            }
            try (InputStream in = rs.getBinaryStream("payload")) {
                if (in == null) {
                    return false;
                }
                Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
                return true;
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        },
        id
);
~~~

`ResultSetExtractor` chủ động gọi `rs.next()` và đọc toàn bộ stream trong callback; `JdbcTemplate` có thể đóng ResultSet/statement khi callback kết thúc. **Không trả `InputStream` hoặc `Reader` lấy từ ResultSet ra ngoài callback** để bên ngoài đọc sau khi transaction/kết nối đã đóng. Với tệp đích thực, đường dẫn `target` phải được kiểm soát và chính sách ghi đè phải phù hợp ứng dụng. Nếu đọc CLOB, dùng `rs.getCharacterStream(...)` với `Reader` và `Writer` đúng bảng mã/encoding thay vì xem mọi dữ liệu là ASCII.

Các API `ResultSet.getBlob`/`getClob` có thể trả locator do DB quản lý; locator có thể cần transaction đang mở và việc giải phóng tài nguyên (`Blob.free()`/`Clob.free()`) theo khả năng driver. Nếu chỉ cần streaming thông thường và driver hỗ trợ, `getBinaryStream`/`getCharacterStream` trong callback thường dễ quản lý hơn.

## 6. Khi cần kiểm soát JDBC setter trực tiếp

Lớp Spring tiện dụng không thể bỏ qua sự khác biệt giữa driver. Nếu driver yêu cầu `setBlob` thay vì `setBinaryStream`, hoặc cần một kiểu đặc biệt, dùng `PreparedStatementCreator`/`PreparedStatementSetter`:

~~~java
// Minh họa: trong một method nhận JdbcTemplate jdbc,
// InputStream source còn mở và long byteLength đã xác định.
int updated = jdbc.update(connection -> {
    var ps = connection.prepareStatement(
            "UPDATE lob_entry SET payload = ? WHERE id = ?");
    ps.setBlob(1, source, byteLength);
    ps.setLong(2, 7L);
    return ps;
});
~~~

Đoạn này **phụ thuộc JDBC 4.x và khả năng `setBlob(int, InputStream, long)` của driver**. Với cột kiểu byte array, có thể thay bằng `ps.setBinaryStream(1, source, byteLength)` hoặc `ps.setBytes(1, bytes)` nếu driver yêu cầu. `source` phải còn mở trong thời gian gọi `jdbc.update`. `JdbcTemplate` quản lý việc đóng statement/connection theo hợp đồng của nó; ứng dụng quản lý tài nguyên bên ngoài (stream) theo vòng đời đã chọn.

Đối với `CLOB`, so sánh `setClob(index, reader, charLength)` với `setCharacterStream(index, reader, charLength)` và kiểm tra driver. Không “sửa” lỗi kiểu bằng cách chuyển tùy tiện từ `setCharacterStream` sang `setBinaryStream`: một bên là ký tự Unicode, bên kia là byte.

### Lưu ý về JDBC stream length

- `setBinaryStream(..., long length)`: độ dài byte; ghi ít/nhiều hơn kỳ vọng có thể gây lỗi hoặc dữ liệu thiếu tùy driver.
- `setCharacterStream(..., long length)`: độ dài ký tự; độ dài UTF-8 **không** bằng số ký tự với nhiều chuỗi tiếng Việt.
- Bản overload không truyền length có từ JDBC 4, nhưng phải kiểm thử với driver thực. Đừng giả định mọi driver/DB đã áp dụng đồng nhất.
- Không đọc toàn bộ file vào `byte[]` để gọi stream ngay sau đó nếu mục tiêu là tiết kiệm heap. Điều này vẫn giữ nội dung trong bộ nhớ.
- Stream không có nghĩa transaction có thể đóng trước khi ghi xong; đối với locator/large object cần tuân thủ ranh giới transaction.

## 7. Nếu dự án đang dùng `SqlLobValue`/`LobHandler` thì sao?

Đây là **mã tương thích cho dự án cũ**, không phải ví dụ khuyến nghị cho mã mới trên Spring 6.2+:

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.support.SqlLobValue;
import org.springframework.jdbc.support.lob.DefaultLobHandler;
import org.springframework.jdbc.support.lob.LobHandler;

// Đoạn minh họa, giả sử jdbc, bytes, text đã được khởi tạo.
LobHandler lobHandler = new DefaultLobHandler();

jdbc.update(
        "INSERT INTO lob_entry (id, payload, description) VALUES (?, ?, ?)",
        new Object[] {
                7L,
                new SqlLobValue(bytes, lobHandler),
                new SqlLobValue(text, lobHandler)
        },
        new int[] {Types.BIGINT, Types.BLOB, Types.CLOB}
);
~~~

Ở các phiên bản cũ, `LobHandler` cung cấp chiến lược đọc/ghi LOB và `LobCreator` có thể giữ tài nguyên cần dọn khi xong statement. `SqlLobValue` hoạt động cùng `LobCreator` và các tiện ích Spring có thể thực hiện cleanup sau lời gọi; không tùy tiện giữ một `LobCreator` lâu dài giữa các thread/transaction.

Trong Spring 6.2, nhóm lớp này bị deprecated vì API mới và JDBC trực tiếp đã đáp ứng nhiều nhu cầu LOB. **Deprecated không đồng nghĩa “đã xóa” hoặc “mọi mã cũ chạy sai”**. Nếu dự án đang sử dụng một chiến lược driver đặc biệt, hãy kiểm tra hành vi rồi mới thay, thay vì đổi hàng loạt chỉ để biến mất cảnh báo.

### Những tùy chọn legacy dễ thấy trong hướng dẫn cũ

`DefaultLobHandler` từng có các cờ khác nhau:

| Cấu hình cũ | Ý nghĩa thực tế | Điều cần kiểm tra trước khi thay |
| --- | --- | --- |
| Mặc định | Dùng `setBinaryStream`/`setCharacterStream` hoặc các accessor JDBC trực tiếp | Driver có hỗ trợ đúng với cột BLOB/CLOB mục tiêu không? |
| `setWrapAsLob(true)` | Bọc giá trị thành `Blob`/`Clob` và dùng setter LOB | Trước đây có ví dụ cho PostgreSQL **OID**; không áp cho PostgreSQL `BYTEA` |
| `setStreamAsLob(true)` | Dùng API JDBC 4 dạng `setBlob(InputStream, ...)`/`setClob(Reader, ...)` | Driver có triển khai các overload tương ứng không? |
| `setCreateTemporaryLob(true)` | Tạo một LOB tạm do JDBC/database quản lý khi cần | Có cần phương án này trên driver hiện tại không, cleanup thế nào? |

Nếu chuyển sang `SqlBinaryValue`/`SqlCharacterValue`, hãy đối chiếu xem driver còn cần dạng setter đặc thù hay không. Hai lớp mới **không phải bản sao mang đủ các cờ tùy biến của `DefaultLobHandler`**; khi gặp trường hợp đặc biệt, gọi JDBC setter tương ứng là lựa chọn rõ ràng.

## 8. Một số khác biệt quan trọng giữa database và JDBC driver

| Database / lưu trữ | Nên bắt đầu thế nào | Tránh nhầm lẫn |
| --- | --- | --- |
| **PostgreSQL `BYTEA`** | `setBytes`/`getBytes` hoặc `setBinaryStream`/`getBinaryStream`; có thể đánh giá `SqlBinaryValue` theo driver và SQL type thực | Đừng chuyển thành `Types.BLOB` một cách máy móc; `BYTEA` khác Large Object OID |
| **PostgreSQL Large Object/`OID`** | Dùng cơ chế Large Object của pgJDBC hoặc chiến lược `Blob` phù hợp; mở transaction thực sự | OID lưu tham chiếu đến Large Object riêng, cần transaction và có thể phải tự xóa LOB khi xóa hàng |
| **Oracle `BLOB`/`CLOB`** | Thử `SqlBinaryValue`/`SqlCharacterValue` với SQL type khớp và JDBC driver hiện đại; nếu cần, dùng `setBlob/setClob`, temporary LOB theo driver | Giới hạn, locator, stream support và hành vi của driver Oracle thay đổi theo phiên bản |
| **MySQL/MariaDB `BLOB/LONGBLOB`, `TEXT/LONGTEXT`** | Thử `setBytes`/`setBinaryStream` và `setString`/`setCharacterStream` hoặc wrappers thích hợp | Không suy luận TEXT là JDBC CLOB; giới hạn kích thước cột, encoding và packet size cũng có tác động |
| **H2 `BLOB/CLOB`** | Phù hợp cho demo, `SqlBinaryValue`/`SqlCharacterValue` + `Types.BLOB/CLOB` hoặc JDBC chuẩn | H2 test thành công không chứng minh tương thích production |
| **SQL Server `VARBINARY(MAX)`/`NVARCHAR(MAX)`** | Sử dụng API phù hợp binary/Unicode và đặc tính Microsoft JDBC driver | Không gán nhầm toàn bộ cột MAX thành CLOB/BLOB JDBC; cần thử các kích thước lớn thực tế |

PostgreSQL là ví dụ cho thấy **chọn sai API có thể sai cả mô hình lưu trữ**, không chỉ sai performance. pgJDBC phân biệt `BYTEA` với Large Object (OID): `getBytes/setBytes` hoạt động cho BYTEA, trong khi Large Object dùng API riêng hoặc dạng BLOB mà driver hỗ trợ và phải hoạt động trong transaction. Xóa hàng chứa OID **không nhất thiết** xóa đối tượng Large Object — cần lifecycle cleanup. Đây là lý do không copy `DefaultLobHandler.setWrapAsLob(true)` từ bài viết cũ rồi áp dụng cho mọi cột nhị phân PostgreSQL.

**Một chi tiết phiên bản:** Javadoc Spring 6.2 của `SqlBinaryValue` ghi rõ không dùng `Types.BLOB` cho cột PostgreSQL `BYTEA`; nếu bắt buộc khai báo kiểu theo cách wrapper này thì còn có quy tắc riêng được mô tả cho driver. Do đó lựa chọn ban đầu an toàn, rõ ràng với BYTEA thường là `PreparedStatement.setBytes` hoặc `setBinaryStream` theo pgJDBC, rồi mới thử wrapper với integration test. Tránh áp đặt một SQL type duy nhất cho mọi driver.

## 9. Vòng đời dữ liệu và transaction ảnh hưởng lựa chọn API

Một thao tác upload/download LOB không chỉ liên quan SQL type:

1. **Ranh giới ResultSet/Connection.** Stream/locator JDBC có thể ngừng hợp lệ sau khi đóng ResultSet, statement, transaction hoặc connection. Với `JdbcTemplate`, đọc hết trong callback nếu muốn stream.
2. **Transaction.** Một số database, đặc biệt PostgreSQL Large Object, yêu cầu transaction đang mở. `@Transactional` chỉ có tác dụng với lời gọi qua Spring proxy và transaction manager phù hợp; đặt annotation lên method không được Spring quản lý không bảo đảm gì.
3. **Nguồn stream đầu vào.** Giữ nguồn mở đến khi JDBC tiêu thụ xong; nếu provider đọc chậm, cần tính timeout, giới hạn kích thước và giải phóng file descriptor.
4. **Kích thước thực.** Chọn phương thức có length khi driver đòi; phân biệt byte count và character count. Truyền thiếu length không nên được “giải quyết” bằng số đo byte của UTF-8 cho `Reader`.
5. **Giải phóng locator.** Nếu sử dụng `Blob`/`Clob` object và driver có tài nguyên đặc biệt, gọi `free()` hợp lệ và tránh đưa locator qua ranh giới thread/transaction.
6. **Bộ nhớ và throughput.** Đo heap, GC, tốc độ và các bản sao buffer. API có chữ “stream” không bảo đảm zero-copy hoặc không giữ buffer nội bộ.
7. **Độ tin cậy nghiệp vụ.** Với upload tệp lớn, cân nhắc timeout, retry, kiểm tra checksum sau ghi; tránh retry mù khiến sinh bản ghi trùng hoặc bỏ sót xóa Large Object ngoài row.

Nếu dữ liệu lớn đến mức đặt trong database gây chi phí đáng kể, đó là bài toán kiến trúc lưu trữ khác. Trong phạm vi bài này, giả định database đã được chọn làm nơi lưu; ta chọn API JDBC đúng cách.

## 10. Checklist lỗi và hướng xử lý

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| IDE báo không có `SqlBinaryValue` hoặc `SqlCharacterValue` | Spring Framework phải từ **6.1.4**; kiểm tra dependency thật thay vì tin phiên bản từ hướng dẫn |
| Spring 6.2 báo deprecated khi dùng `LobHandler`/`SqlLobValue` | Đây là trạng thái API; cân nhắc nâng sang giá trị mới và chạy integration test theo driver |
| `Invalid column type`, lỗi ép kiểu từ binary sang OID/BLOB | Đối chiếu kiểu cột SQL và kiểu JDBC; với PostgreSQL phân biệt `BYTEA` và `OID` |
| `SQLFeatureNotSupportedException` khi gọi `setBlob`/`setClob` | Driver thiếu overload tương ứng; thử `setBinaryStream`, `setCharacterStream` hoặc cách driver hướng dẫn |
| Ghi stream thất bại/thiếu dữ liệu | Stream đã bị đóng, length sai, driver cần biết length, file thay đổi trong khi đo kích thước, timeout/giới hạn driver |
| CLOB chứa tiếng Việt thành dấu hỏi/ký tự sai | Sử dụng `Reader`/`Writer` và encoding phù hợp; đừng ép mọi văn bản thành ASCII; kiểm tra collation/charset |
| `LOB cannot be used after transaction ends` hoặc lỗi locator | Đọc/ghi ngoài vòng đời connection/transaction hoặc trả stream ngoài callback; tiêu thụ trong callback |
| Upload vài MB chạy nhưng vài trăm MB gây OOM | Có đường đọc toàn bộ vào `byte[]`/`String`, driver tự buffer, hoặc nhiều upload đồng thời; đo memory và giới hạn request |
| H2 test xanh nhưng production lỗi | DDL, JDBC driver, SQL type, setter và transaction khác; thêm integration test theo DB mục tiêu |
| Xóa row PostgreSQL OID nhưng dung lượng LO không giảm | Large Object riêng chưa được xóa; cần quy trình lifecycle phù hợp |
| Dùng `SqlParameterValue(Types.BLOB, ...)` cho cột `TEXT`/`BYTEA` | Hint không khớp kiểu lưu trữ; chọn đúng kiểu hoặc thử JDBC setter có chủ đích |

### Khi debug, thu thập thông tin nào?

- Framework version thực tế (`spring-jdbc` và các jar Spring liên quan), driver artifact + version, JDBC URL (không kèm thông tin bí mật).
- DDL thật của cột, đặc biệt `BLOB`/`CLOB` so với `BYTEA`/`OID`/`TEXT`.
- Setter được dùng (`setBlob`, `setBinaryStream`, `setBytes`…), type hint `Types.*`, dạng đầu vào byte[]/InputStream/Reader và độ dài truyền.
- SQLState, vendor error code, chain `SQLException`/`DataAccessException`; giữ log tránh lộ dữ liệu tệp.
- Có transaction không, stream có đóng sớm không, dung lượng vừa đủ và lớn bất thường có gây khác biệt không.
- Nếu driver có cấu hình stream/buffer/LO riêng, kiểm thử tổ hợp cấu hình đang dùng ở production.

Chẩn đoán bằng các thông tin đó thường hiệu quả hơn việc thử ngẫu nhiên nhiều cờ `DefaultLobHandler`.

## 11. Kiểm thử tương thích trước khi đổi API

Một integration test cho lựa chọn API LOB nên chạy trên **đúng database và JDBC driver mục tiêu**, không chỉ H2:

1. Tạo schema bằng migration thật; ghi nhận kiểu SQL của cột và phiên bản `spring-jdbc`.
2. Ghi và đọc lại **byte[] có 0x00, 0xFF và byte không phải ký tự**, so sánh từng byte/checksum. Không biến nhị phân thành chuỗi để so sánh.
3. Ghi và đọc lại văn bản có tiếng Việt, emoji, xuống dòng và dấu câu; đối chiếu Unicode/encoding.
4. Test dữ liệu `NULL`, dữ liệu rỗng `0 byte`, nhiều KB và nhiều MB; nếu cho phép, thử lớn hơn ngưỡng thường thấy ở driver/DB.
5. Với streaming, xác minh nguồn không bị đóng sớm, length đúng, stream được đọc trong callback, tài nguyên đóng sau success/error.
6. Với OID/locator, xác nhận transaction và cleanup; kiểm tra DB state sau commit/rollback.
7. Đo heap, thời gian ghi/đọc và giới hạn kết nối khi đồng thời nhiều yêu cầu. Không kết luận stream “không tốn RAM” chỉ vì gọi API stream.
8. Khi nâng 6.1.x lên 6.2.x, đổi `SqlLobValue` sang `SqlBinaryValue`/`SqlCharacterValue` có chọn lọc; so sánh cùng tập dữ liệu trên DB thực và giám sát lỗi driver.

Kết quả QA mong muốn không phải “không còn cảnh báo deprecated”, mà là **API không lệch phiên bản, cột SQL khớp cách bind, dữ liệu round-trip nguyên vẹn, memory và transaction phù hợp**.

## 12. Câu hỏi tự kiểm tra

**1. Dự án Spring 6.1.3 copy đoạn `new SqlBinaryValue(bytes)` rồi build lỗi vì không tìm thấy lớp. Tại sao?** — Vì `SqlBinaryValue` xuất hiện từ Spring **6.1.4**. Cần nâng đúng version framework hoặc chọn JDBC trực tiếp/API phù hợp phiên bản hiện có.

**2. Dự án Spring 6.2 dùng `SqlLobValue` còn chạy, nhưng IDE cảnh báo deprecated. Có phải API đã bị xóa?** — Không. “Deprecated từ 6.2” là tín hiệu nên chuyển API cho mã mới; mã cũ có thể vẫn hoạt động. Migration cần kiểm thử thực chất.

**3. PostgreSQL có cột `BYTEA`. Có nên ép mọi tham số nhị phân thành `Types.BLOB`?** — Không. `BYTEA` và Large Object `OID` khác nhau. Với BYTEA, pgJDBC hỗ trợ `setBytes/setBinaryStream` và `getBytes/getBinaryStream`; kiểm tra type hint của wrapper nếu dùng.

**4. Một tệp UTF-8 chiếm 1.200 byte. Có chắc truyền `length=1200` cho `SqlCharacterValue(Reader, length)` đúng?** — Không. Length của `Reader` đo **ký tự**, không phải byte của tệp. Với văn bản nhiều byte/Unicode, hai số có thể khác nhau.

**5. Có nên return `rs.getBinaryStream(...)` từ `JdbcTemplate.query(...)` để controller xử lý sau?** — Không nếu callback đã đóng ResultSet/connection trước khi controller đọc. Phải tiêu thụ stream trong lifecycle phù hợp, hoặc chủ động thiết kế streaming với quản lý tài nguyên rõ ràng.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — SqlBinaryValue Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/support/SqlBinaryValue.html) — có từ 6.1.4, constructors và quy tắc SQL type.
- [Spring Framework 6.2 — SqlCharacterValue Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/support/SqlCharacterValue.html) — CharSequence, Reader, length và SQL type.
- [Spring Framework 6.2 — Deprecated API List](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/deprecated-list.html) — `LobHandler`, `LobCreator`, `SqlLobValue` và helper cũ.
- [Spring Framework — JDBC Parameter Handling](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html) — cách xử lý BLOB/CLOB và legacy pattern.
- [pgJDBC — Storing Binary Data](https://jdbc.postgresql.org/documentation/binary-data/) — phân biệt `BYTEA` với Large Object/`OID`, giao dịch và cleanup.
