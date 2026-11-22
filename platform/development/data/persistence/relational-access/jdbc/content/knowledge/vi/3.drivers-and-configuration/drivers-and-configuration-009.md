# Kiểm tra phiên bản driver và khả năng tương thích máy chủ trong JDBC

Trong chương **Driver và cấu hình**, một việc quan trọng trước khi đưa ứng dụng vào vận hành là xác định **driver JDBC nào đang thực sự được sử dụng** và **driver đó có tương thích với máy chủ cơ sở dữ liệu (DBMS) hay không**. Một dự án có thể khai báo đúng dependency nhưng khi chạy lại tải phiên bản JAR khác; hoặc driver kết nối được nhưng không hỗ trợ tính năng mà ứng dụng cần.

**JDBC (Java Database Connectivity)** là API Java dùng để truy cập cơ sở dữ liệu quan hệ. JDBC cung cấp cơ chế lấy thông tin driver và máy chủ qua `java.sql.DatabaseMetaData`, đồng thời cho phép kiểm tra một số khả năng thực tế của kết nối. Bài học hướng dẫn quy trình xác minh, cách đọc kết quả và cách đánh giá tương thích mà không dựa vào suy đoán từ tên file JAR.

## 1. Những loại phiên bản cần phân biệt

Khi nói “phiên bản JDBC”, cần xác định đang hỏi loại nào:

| Thành phần | Ví dụ về thông tin | Cách kiểm tra | Vai trò |
|---|---|---|---|
| **Phiên bản driver** | Tên nhà cung cấp, số phiên bản JAR driver | `DatabaseMetaData.getDriverName()`, `getDriverVersion()` | Cho biết thư viện hiện đang xử lý kết nối |
| **Phiên bản API JDBC mà driver công bố** | JDBC 4.x | `getJDBCMajorVersion()`, `getJDBCMinorVersion()` | Cho biết mức API JDBC driver báo hỗ trợ |
| **Phiên bản máy chủ DBMS** | PostgreSQL, MySQL, SQL Server, Oracle... cùng phiên bản máy chủ | `getDatabaseProductName()`, `getDatabaseProductVersion()` | Xác định hệ quản trị mà kết nối đang làm việc |
| **Phiên bản Java runtime** | JDK/JRE 11, 17, 21... | `java.version` hoặc `Runtime.version()` | Quyết định driver có nạp/chạy được trên JVM hay không |
| **Phiên bản thư viện khi triển khai** | Driver trên classpath/runtimeClasspath | Dependency tree, JAR thực tế | Phát hiện lệch giữa khai báo và mã chạy |

Các lớp phiên bản này **không đồng nghĩa với nhau**. Ví dụ, một driver hỗ trợ JDBC 4.x không mặc nhiên tương thích với mọi phiên bản máy chủ DBMS, và phiên bản driver mới hơn không bảo đảm chạy trên Java runtime quá cũ.

Quan hệ cần kiểm tra:

```text
Ứng dụng Java
    |
    +-- Java runtime/JDK -------------- chạy được bytecode của driver?
    |
    +-- JDBC API ---------------------- driver có API/tính năng cần dùng?
    |
    +-- Driver JDBC thực tế ----------- đúng loại, đúng phiên bản?
    |
    +-- Giao thức kết nối, TLS, auth -- tương thích cấu hình máy chủ?
    |
    +-- Máy chủ DBMS ------------------ phiên bản/SQL/tính năng phù hợp?
```

Đánh giá tương thích tốt cần kiểm tra **cả tài liệu hỗ trợ chính thức của nhà cung cấp lẫn hành vi thực tế của ứng dụng trên môi trường đích**.

## 2. Kiểm tra dependency và Java runtime trước khi kết nối

### 2.1. Xác định loại driver được khai báo

Trong các dự án hiện đại, driver thường được đưa vào dự án qua Maven hoặc Gradle. Ví dụ sau chỉ minh họa tọa độ artifact, ký hiệu `<version>` là giá trị phải chọn theo tài liệu nhà cung cấp:

```xml
<!-- PostgreSQL JDBC driver: ví dụ dependency Maven -->
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>PHIEN_BAN_DA_KIEM_TRA</version>
</dependency>
```

```groovy
// Gradle Groovy DSL: ví dụ cấu hình JDBC driver lúc chạy.
dependencies {
    runtimeOnly 'org.postgresql:postgresql:PHIEN_BAN_DA_KIEM_TRA'
}
```

Một số họ driver thường gặp:

| DBMS | Artifact/driver thường dùng | Tiền tố JDBC URL điển hình |
|---|---|---|
| PostgreSQL | `org.postgresql:postgresql` | `jdbc:postgresql:` |
| MySQL | `com.mysql:mysql-connector-j` | `jdbc:mysql:` |
| Microsoft SQL Server | `com.microsoft.sqlserver:mssql-jdbc` | `jdbc:sqlserver:` |
| Oracle Database | Driver Oracle JDBC thuộc họ `ojdbc` | `jdbc:oracle:` |

Tên artifact và cách phát hành có thể thay đổi theo thời gian. Với Oracle, SQL Server và những nhà cung cấp có nhiều bản JAR, cần chọn đúng artifact/bản đóng gói tương ứng với Java runtime. URL cũng phải phù hợp chính xác với driver đang dùng; **JDBC không quy định một cú pháp URL duy nhất cho tất cả DBMS**.

Trong dự án thực tế, hãy xem **dependency được giải quyết cuối cùng tại runtime** chứ không chỉ đọc `pom.xml` hoặc `build.gradle`:

```bash
# Maven: xem cây phụ thuộc và các phiên bản thực tế.
mvn dependency:tree

# Gradle: xem classpath chạy ứng dụng.
./gradlew dependencies --configuration runtimeClasspath
```

Đây là các lệnh tham khảo để chạy trong môi trường dự án thích hợp; tên cấu hình Gradle có thể khác nếu dự án không dùng plugin Java thông thường. Nếu có nhiều driver cùng loại xuất hiện dưới các phiên bản khác nhau, cần làm rõ phiên bản mà bộ nạp lớp chọn.

### 2.2. Kiểm tra Java runtime thực sự

```bash
java -version
```

Trong ứng dụng:

```java
System.out.println("Java runtime: " + System.getProperty("java.version"));
System.out.println("Java vendor : " + System.getProperty("java.vendor"));
```

Lưu ý rằng phiên bản JDK dùng để **biên dịch** có thể khác phiên bản JVM dùng để **chạy** ứng dụng ở container/server. Hãy kiểm tra trên đúng môi trường chạy.

Các lỗi như `UnsupportedClassVersionError` thường cho thấy bytecode của thư viện được biên dịch cho phiên bản Java mới hơn JVM hiện tại. Việc hạ số phiên bản dependency không nên thực hiện tùy ý: cần đối chiếu danh sách Java runtime mà nhà cung cấp driver còn hỗ trợ và các yêu cầu bảo mật của dự án.

## 3. Lấy phiên bản driver và DBMS bằng DatabaseMetaData

Sau khi đã kết nối, đối tượng `Connection` có thể cung cấp `DatabaseMetaData`:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("Driver: " + meta.getDriverName());
    System.out.println("Driver version: " + meta.getDriverVersion());

    System.out.println("JDBC API: "
            + meta.getJDBCMajorVersion() + "."
            + meta.getJDBCMinorVersion());

    System.out.println("Database: " + meta.getDatabaseProductName());
    System.out.println("Server version: " + meta.getDatabaseProductVersion());
}
```

Trong đoạn này, `dataSource` là một `javax.sql.DataSource` đã được cấu hình sẵn. Phải có kết nối thành công trước khi đọc metadata từ server; nếu handshake hoặc xác thực thất bại thì đoạn mã không thể lấy được phiên bản server.

### 3.1. Các phương thức quan trọng

| Phương thức `DatabaseMetaData` | Nội dung trả về |
|---|---|
| `getDriverName()` | Tên driver JDBC do driver cung cấp |
| `getDriverVersion()` | Chuỗi phiên bản đầy đủ của driver |
| `getDriverMajorVersion()` / `getDriverMinorVersion()` | Thành phần major/minor của phiên bản driver |
| `getJDBCMajorVersion()` / `getJDBCMinorVersion()` | Thành phần major/minor của phiên bản đặc tả JDBC driver công bố hỗ trợ |
| `getDatabaseProductName()` | Tên sản phẩm DBMS |
| `getDatabaseProductVersion()` | Chuỗi phiên bản DBMS do driver báo cáo |
| `getDatabaseMajorVersion()` / `getDatabaseMinorVersion()` | Thành phần major/minor của phiên bản DBMS |

Ba thông tin dễ nhầm nhất:

1. `getDriverVersion()` phản ánh **bản driver** chứ không phải phiên bản máy chủ.
2. `getDatabaseProductVersion()` phản ánh **DBMS mà kết nối nhận diện** chứ không phải bản JAR.
3. `getJDBCMajorVersion()` và `getJDBCMinorVersion()` phản ánh **mức đặc tả API JDBC**, không phải driver hay DBMS.

Thông tin DBMS có thể bị ảnh hưởng bởi gateway/proxy hoặc cách driver diễn giải thông tin giao thức. Nếu sử dụng proxy kết nối, sản phẩm DB tương thích giao thức hoặc dịch vụ database dạng managed, cần đối chiếu metadata với thông tin phiên bản do nền tảng vận hành công bố.

### 3.2. Chương trình chẩn đoán có thể chạy độc lập

Ví dụ sau nhận cấu hình từ biến môi trường, mở kết nối qua `DriverManager`, in thông tin các lớp phiên bản và kiểm tra một số khả năng JDBC. Nó **không** thực thi SQL thay đổi dữ liệu.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JdbcCompatibilityCheck {

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu biến môi trường bắt buộc: " + key);
        }
        return value;
    }

    public static void main(String[] args) throws SQLException {
        String url = requireEnv("JDBC_URL");
        String user = requireEnv("JDBC_USER");
        // Mật khẩu có thể rỗng ở môi trường demo được cấu hình như vậy.
        String password = System.getenv("JDBC_PASSWORD");
        if (password == null) {
            throw new IllegalArgumentException("Thiếu JDBC_PASSWORD");
        }

        System.out.println("Java runtime: "
                + System.getProperty("java.version"));

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            DatabaseMetaData meta = connection.getMetaData();

            System.out.printf("Driver        : %s%n", meta.getDriverName());
            System.out.printf("Driver version: %s%n", meta.getDriverVersion());
            System.out.printf("Driver major/minor: %d.%d%n",
                    meta.getDriverMajorVersion(),
                    meta.getDriverMinorVersion());

            System.out.printf("JDBC API      : %d.%d%n",
                    meta.getJDBCMajorVersion(),
                    meta.getJDBCMinorVersion());

            System.out.printf("DBMS          : %s%n",
                    meta.getDatabaseProductName());
            System.out.printf("Server version: %s%n",
                    meta.getDatabaseProductVersion());
            System.out.printf("Server major/minor: %d.%d%n",
                    meta.getDatabaseMajorVersion(),
                    meta.getDatabaseMinorVersion());

            System.out.printf("Transactions  : %s%n",
                    meta.supportsTransactions());
            System.out.printf("Savepoints    : %s%n",
                    meta.supportsSavepoints());
            System.out.printf("Batch updates : %s%n",
                    meta.supportsBatchUpdates());
            System.out.printf("Generated keys: %s%n",
                    meta.supportsGetGeneratedKeys());
            System.out.printf("Scroll-insensitive ResultSet: %s%n",
                    meta.supportsResultSetType(
                            ResultSet.TYPE_SCROLL_INSENSITIVE));
            System.out.printf("READ_COMMITTED isolation: %s%n",
                    meta.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_READ_COMMITTED));

        } catch (SQLException error) {
            // SQLState và vendor error code hữu ích khi tìm nguyên nhân.
            System.err.println("Không kiểm tra được JDBC/DBMS.");
            System.err.println("SQLState: " + error.getSQLState());
            System.err.println("Vendor code: " + error.getErrorCode());
            throw error;
        }
    }
}
```

Đoạn mã sử dụng `String.isBlank()` (Java 11 trở lên) và các lớp thuộc `java.sql`. Để chạy, phải có driver JDBC phù hợp trên classpath/runtimeClasspath, cơ sở dữ liệu có thể truy cập được và các biến môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD` được cấu hình. Không ghi mật khẩu hoặc URL chứa secret vào log.

Ví dụ **dạng kết quả** (giá trị bên dưới chỉ để minh họa, không đại diện cho một bản driver hoặc DBMS cụ thể):

```text
Java runtime: <java-version>
Driver        : <driver-name>
Driver version: <driver-version>
Driver major/minor: <driver-major>.<driver-minor>
JDBC API      : <jdbc-major>.<jdbc-minor>
DBMS          : <database-product>
Server version: <database-version>
Server major/minor: <database-major>.<database-minor>
Transactions  : true
Savepoints    : true
Batch updates : true
Generated keys: true
Scroll-insensitive ResultSet: false
READ_COMMITTED isolation: true
```

Không được hiểu các giá trị `true`/`false` của ví dụ là cam kết của một driver cụ thể; cần chạy chương trình trên đúng driver, máy chủ và cấu hình sẽ dùng khi triển khai.

## 4. Kiểm tra khả năng hoạt động, không chỉ so sánh số phiên bản

Một kết nối thành công chỉ xác nhận rằng driver và máy chủ có thể hoàn tất bước kết nối trong cấu hình hiện tại. Nó **chưa chứng minh** rằng mọi truy vấn, kiểu dữ liệu, stored procedure hoặc chức năng JDBC đều hoạt động đúng.

`DatabaseMetaData` cung cấp một số phép kiểm tra tính năng:

| Tính năng ứng dụng cần | Kiểm tra ban đầu |
|---|---|
| Transaction | `supportsTransactions()` |
| Savepoint trong transaction | `supportsSavepoints()` |
| Batch update | `supportsBatchUpdates()` |
| Khóa được sinh từ INSERT | `supportsGetGeneratedKeys()` |
| ResultSet cuộn/di chuyển con trỏ | `supportsResultSetType(...)` |
| ResultSet có thể cập nhật | `supportsResultSetConcurrency(type, concurrency)` |
| Stored procedure | `supportsStoredProcedures()` |
| Isolation level cụ thể | `supportsTransactionIsolationLevel(level)` |

Chẳng hạn, ứng dụng sử dụng savepoint có thể bảo vệ nhánh thao tác:

```java
DatabaseMetaData meta = connection.getMetaData();
if (!meta.supportsTransactions() || !meta.supportsSavepoints()) {
    throw new SQLException(
            "Kết nối hiện tại không đáp ứng yêu cầu transaction/savepoint");
}

// Chỉ tạo savepoint khi đang quản lý transaction thủ công.
connection.setAutoCommit(false);
// Savepoint sp = connection.setSavepoint("before_optional_step");
```

Các phương thức `supports...` là thông tin năng lực **driver báo cáo**. Với chức năng trọng yếu, phải bổ sung kiểm thử tích hợp trên máy chủ đích để xác minh:

- Driver trả dữ liệu đúng với kiểu SQL thực tế (ví dụ `DECIMAL`, `TIMESTAMP`, JSON/UUID nếu hệ quản trị có hỗ trợ).
- Câu SQL của ứng dụng chạy được với phiên bản server, schema và quyền hiện hành.
- Transaction, commit/rollback, isolation, locking và generated keys có hành vi phù hợp.
- Batch, stored procedure, ResultSet type/concurrency và các extension hoạt động khi ứng dụng thực sự sử dụng.
- TLS, cơ chế xác thực, timeout và connection pooling làm việc ổn định trong cùng cấu hình với môi trường triển khai.

Không phải mọi driver hoặc DBMS đều hỗ trợ toàn bộ API JDBC. Nếu một tính năng không hỗ trợ, driver có thể báo `false` trong metadata hoặc ném `SQLFeatureNotSupportedException` (một dạng `SQLException`), tùy thao tác và hợp đồng API.

## 5. Đối chiếu ma trận tương thích chính thức

Muốn kết luận “tương thích”, nên thực hiện các bước sau theo một thứ tự rõ ràng.

### Bước 1: Ghi lại bộ phiên bản đang chạy

Tối thiểu cần biết:

```text
Java runtime đang chạy  : _______________________
Driver JDBC thực tế     : _______________________
Phiên bản driver        : _______________________
JDBC API driver báo cáo : _______________________
DBMS/server thực tế     : _______________________
Phiên bản DBMS          : _______________________
TLS/auth/proxy đặc biệt : _______________________
Tính năng cần sử dụng   : _______________________
```

Nếu ứng dụng dùng connection pool, framework hoặc app server, cần ghi nhận cả cấu hình datasource và nguồn JAR thực tế. Một số môi trường nạp driver từ thư viện dùng chung thay vì classpath của ứng dụng.

### Bước 2: Tra đúng tài liệu nhà cung cấp

Đọc **support matrix**, tài liệu cài đặt và release notes của **đúng phiên bản driver**. Xác minh:

1. Phiên bản Java thấp nhất/cao nhất được driver hỗ trợ; một số nhà cung cấp phân phối nhiều biến thể JAR theo Java.
2. Dải phiên bản máy chủ DBMS được hỗ trợ chính thức, kể cả phiên bản mới vừa nâng cấp hoặc phiên bản cũ sắp hết hỗ trợ.
3. Những tính năng đặc thù cần dùng: kiểu dữ liệu, phương thức xác thực, TLS, Kerberos, stored procedure, bulk operation, high availability.
4. Các lỗi đã biết, bản vá bảo mật và thay đổi cấu hình mặc định giữa các bản driver.

Có thể bắt đầu từ tài liệu chính thức của PostgreSQL JDBC, MySQL Connector/J, Microsoft JDBC Driver for SQL Server hoặc Oracle JDBC, tương ứng với hệ quản trị mà ứng dụng sử dụng. **Không thể suy ra ma trận tương thích chỉ từ phiên bản JDBC API**, vì mỗi nhà cung cấp có phạm vi hỗ trợ riêng và thay đổi theo thời gian.

### Bước 3: Kiểm tra trực tiếp trên máy chủ đích

Đọc metadata qua `DatabaseMetaData` như ví dụ ở trên, rồi chạy integration test với những SQL và API mà ứng dụng dùng.

Nếu cần kiểm tra phiên bản bằng câu SQL đặc thù DBMS (ví dụ các hàm báo phiên bản máy chủ), hãy dùng cú pháp được nhà cung cấp xác nhận. **Không có một câu `SELECT VERSION()` tiêu chuẩn áp dụng cho mọi hệ quản trị**; `DatabaseMetaData.getDatabaseProductVersion()` là điểm bắt đầu mang tính JDBC hơn.

### Bước 4: Ghi kết quả và đưa vào quy trình nâng cấp

Nên lưu lại “phiên bản mong đợi” cùng thông tin kiểm thử, thay vì chỉ xác định được rằng kết nối hiện tại không lỗi. Khi thay driver, nâng Java, đổi máy chủ hoặc cấu hình TLS/auth, cần chạy lại phép kiểm tra.

| Thành phần | Đã kiểm tra? | Bằng chứng |
|---|---|---|
| Driver được nạp tại runtime | □ | `getDriverName()` / `getDriverVersion()` |
| Driver hỗ trợ Java đang dùng | □ | Support matrix và `java -version` |
| Server nằm trong dải hỗ trợ | □ | Phiên bản DBMS và tài liệu driver |
| Tính năng JDBC bắt buộc | □ | Metadata và integration test |
| Giao thức/TLS/xác thực | □ | Kết nối thử trên môi trường đích |
| SQL/transaction của ứng dụng | □ | Integration test |

## 6. Tránh nhầm lẫn khi kiểm tra driver được nạp

### 6.1. Nhiều driver có thể cùng xuất hiện

JDBC 4.0 trở lên hỗ trợ cơ chế đăng ký driver tự động thông qua service provider nếu thư viện driver được đóng gói đúng cách và có thể được classloader tìm thấy. Vì vậy, với driver hiện đại, thường **không cần** gọi thủ công `Class.forName("...Driver")`.

Có thể hỏi `DriverManager` về driver phù hợp với một URL:

```java
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.SQLException;

String url = System.getenv("JDBC_URL");
Driver candidate = DriverManager.getDriver(url);

System.out.println("Driver class: " + candidate.getClass().getName());
System.out.println("Reported major/minor: "
        + candidate.getMajorVersion() + "."
        + candidate.getMinorVersion());
```

`getDriver(url)` trả về driver đã đăng ký đầu tiên mà `DriverManager` thấy phù hợp với URL theo quy tắc nạp lớp hiện hành. Đây là kiểm tra **ứng viên**, không phải bằng chứng chắc chắn về phiên kết nối nếu ứng dụng thực tế lấy connection qua một `DataSource` khác. Để biết thông tin về kết nối đang mở, ưu tiên `connection.getMetaData()`.

### 6.2. Phân biệt phiên bản khai báo và phiên bản thực thi

Các nguyên nhân thường gây chênh lệch:

- Dependency bắc cầu (*transitive dependency*) kéo thêm driver khác.
- Server ứng dụng cung cấp JAR JDBC riêng; thư viện bị xếp thứ tự nạp khác với dự kiến.
- JAR cũ còn trong container image, thư mục plugin hoặc `lib/`.
- Build cache hay artifact triển khai không phải bản mới nhất.
- Một ứng dụng có nhiều `DataSource`, mỗi datasource trỏ đến một loại máy chủ/driver khác nhau.

Khi có nhiều datasource, phải **kiểm tra trên từng kết nối**, không lấy thông tin của một kết nối đại diện cho toàn bộ hệ thống.

Nếu cần truy tìm JAR định nghĩa lớp driver ở runtime, có thể xem vị trí nguồn mã Java:

```java
Class<?> driverClass = DriverManager.getDriver(url).getClass();
var source = driverClass.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "<không xác định>" : source.getLocation());
```

Thông tin này phục vụ chẩn đoán nội bộ. Nó có thể không hiện đầy đủ với module image, app server hoặc classloader đặc biệt; không nên đưa đường dẫn triển khai nhạy cảm vào log công khai.

## 7. Những lỗi thường gặp và hướng xác minh

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| `No suitable driver found for jdbc:...` | Thiếu JAR tại runtime, URL sai, driver không được đăng ký/không hiện với classloader | Kiểm tra URL, dependency thực tế, nạp driver |
| `ClassNotFoundException` khi gọi `Class.forName(...)` | Không có lớp driver được yêu cầu hoặc dùng tên lớp lỗi thời | Xác minh artifact và tài liệu driver hiện tại |
| `UnsupportedClassVersionError` | Driver biên dịch cho Java mới hơn JVM đang chạy | So `java -version` với yêu cầu Java của JAR |
| `NoSuchMethodError` / `AbstractMethodError` | Xung đột phiên bản thư viện hoặc API không khớp khi chạy | So classpath biên dịch/chạy; kiểm tra JAR bị trùng |
| Không kết nối được sau nâng server | Thay đổi giao thức, TLS, auth, endpoint hoặc dải hỗ trợ của driver | Kiểm tra server log, release notes, cấu hình mạng, TLS |
| Kết nối được nhưng SQL lỗi | SQL dialect, kiểu dữ liệu, quyền hoặc tính năng khác giữa server versions | Chạy lại query nhỏ, kiểm tra SQLState và tính năng DBMS |
| `SQLFeatureNotSupportedException` | Tính năng API không có trong driver/DBMS hiện tại | Xem `supports...` và tài liệu tính năng |
| Kết nối được nhưng sai timezone/encoding | Cấu hình phiên kết nối, kiểu dữ liệu hoặc quy tắc chuyển đổi | Kiểm thử round-trip dữ liệu trên DBMS đích |

Khi có `SQLException`, nên ghi nhận **SQLState**, mã lỗi nhà cung cấp và chuỗi ngoại lệ lồng nhau:

```java
try {
    // Thao tác JDBC cần chẩn đoán.
} catch (SQLException error) {
    for (SQLException current = error;
         current != null;
         current = current.getNextException()) {
        System.err.printf(
                "SQLState=%s, vendorCode=%d, message=%s%n",
                current.getSQLState(),
                current.getErrorCode(),
                current.getMessage());
    }
    throw error;
}
```

Nhóm SQLState `08` thường liên quan đến kết nối, `28` thường liên quan đến xác thực/ủy quyền và `0A` thường báo tính năng không hỗ trợ theo quy ước SQLState. Tuy nhiên, các hệ quản trị có mã lỗi riêng: hãy tra đúng tài liệu nhà cung cấp và tránh suy đoán chỉ từ phần đầu thông báo lỗi.

Không log mật khẩu, token hoặc toàn bộ JDBC URL nếu URL có thông tin bí mật. Việc bật JDBC trace/driver debug cũng cần kiểm soát vì log có thể chứa SQL, tham số hoặc metadata nội bộ.

## 8. Nâng cấp driver hoặc máy chủ một cách có kiểm soát

Ví dụ ứng dụng đang chạy ổn định và nhóm muốn nâng phiên bản PostgreSQL server, MySQL server hoặc driver của một DBMS khác. Một quy trình hợp lý:

1. **Lập baseline:** ghi lại Java runtime, phiên bản driver, JDBC API, phiên bản máy chủ và các tính năng đang dùng.
2. **Tra hỗ trợ:** đối chiếu ma trận driver ↔ Java ↔ DBMS, đọc release notes, đặc biệt các mục về TLS, auth và SQL/type mapping.
3. **Cập nhật dependency:** chọn một phiên bản driver đã được nhà cung cấp hỗ trợ, loại bỏ bản trùng/không mong muốn khỏi classpath.
4. **Chạy chẩn đoán trên staging:** xác nhận `getDriverVersion()` và `getDatabaseProductVersion()` cho thấy đúng thành phần mới.
5. **Chạy integration tests:** tập trung vào SQL thực tế, transactions, batch, generated keys, timestamp, lỗi đồng thời và kết nối khi pool phục hồi.
6. **Triển khai có quan sát:** theo dõi lỗi kết nối, timeout, số lần retry và SQLState; có kế hoạch rollback cấu hình/bản phát hành nếu cần.

Ví dụ ma trận theo dõi nội bộ (điền bằng thông tin từ nhà cung cấp và môi trường thực tế):

| Môi trường | Java runtime | Driver JDBC | DBMS/server | Kết nối | SQL & transaction |
|---|---|---|---|---|---|
| Local | [phiên bản] | [phiên bản] | [phiên bản] | [PASS/FAIL] | [PASS/FAIL] |
| Test/Staging | [phiên bản] | [phiên bản] | [phiên bản] | [PASS/FAIL] | [PASS/FAIL] |
| Production | [phiên bản] | [phiên bản] | [phiên bản] | [đã xác nhận] | [đã xác nhận] |

Kết quả **kết nối thành công tại local không thay cho kiểm tra trên staging/production**, vì phiên bản DBMS, chính sách TLS, proxy và cơ chế xác thực có thể khác nhau.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** `getDriverVersion()` và `getDatabaseProductVersion()` khác nhau thế nào?

**Đáp án:** Phương thức đầu báo phiên bản thư viện driver JDBC; phương thức thứ hai báo phiên bản hệ quản trị cơ sở dữ liệu mà kết nối nhận diện.

**Câu 2.** Driver báo JDBC API 4.x có đủ để khẳng định hỗ trợ mọi bản máy chủ PostgreSQL/MySQL/Oracle/SQL Server không?

**Đáp án:** Không. JDBC API và giao thức/phiên bản DBMS là hai lớp tương thích khác nhau. Phải đối chiếu ma trận hỗ trợ chính thức và kiểm thử thực tế.

**Câu 3.** Khi ứng dụng dùng savepoint, trước tiên nên kiểm tra khả năng nào?

**Đáp án:** `DatabaseMetaData.supportsSavepoints()` cùng `supportsTransactions()`, rồi kiểm thử thao tác trong transaction thực tế trên DBMS đích.

**Câu 4.** Vì sao thay JAR JDBC trên máy phát triển chưa bảo đảm ứng dụng server dùng phiên bản mới?

**Đáp án:** Classpath/runtimeClasspath, dependency bắc cầu, server library hoặc container image có thể vẫn nạp bản khác. Cần kiểm tra metadata của kết nối trong môi trường đang chạy.

**Câu 5.** Nếu Java runtime không đủ mới để nạp driver, lỗi nào thường xuất hiện?

**Đáp án:** `UnsupportedClassVersionError`; đối chiếu JVM thực tế với yêu cầu Java của bản JAR.

**Câu 6.** Kết nối thành công, nhưng ứng dụng báo `SQLFeatureNotSupportedException` khi dùng tính năng cụ thể. Có thể kết luận driver/server tương thích hoàn toàn không?

**Đáp án:** Không. Cần kiểm tra tài liệu và metadata cho tính năng đó, chọn cách thay thế hoặc phiên bản tương thích đã kiểm thử.

## 10. Ghi nhớ khi làm việc với JDBC

Để xác định tính tương thích trong JDBC, hãy bắt đầu bằng **chứng cứ runtime**: `Connection.getMetaData()` xác định driver, phiên bản đặc tả JDBC và máy chủ đang kết nối; `supports...` đánh giá sơ bộ tính năng. Sau đó kiểm tra **tài liệu hỗ trợ chính thức của đúng phiên bản driver** và **integration test trên DBMS đích**. Khi lưu đủ thông tin Java runtime, driver thực tế, DBMS/server và các tính năng thiết yếu, nhóm phát triển có thể phát hiện lệch cấu hình sớm và nâng cấp an toàn hơn.
