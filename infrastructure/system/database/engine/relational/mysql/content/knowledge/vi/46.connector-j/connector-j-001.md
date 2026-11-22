# Chọn Connector/J theo JDK, JDBC và ma trận tương thích MySQL

MySQL Connector/J là JDBC Type 4 driver chính thức để ứng dụng Java kết nối MySQL qua giao thức mạng của MySQL. Chọn phiên bản driver cần xét đồng thời Java runtime, mức JDBC mà driver triển khai, phiên bản MySQL Server, framework đang dùng và yêu cầu bảo mật. Một JDK mới không tự động làm mọi phương thức JDBC mới được driver hỗ trợ; tương tự, một driver mới không nhất thiết phù hợp với mọi phiên bản server cũ.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào kết nối MySQL từ ứng dụng Java: đọc ma trận tương thích, chọn artifact, quản lý dependency, xác minh driver đang chạy và kiểm thử trước khi nâng cấp production.

## 1. Connector/J nằm ở đâu trong kiến trúc Java và MySQL?

Một ứng dụng JDBC thường có các thành phần:

1. Ứng dụng gọi API chuẩn trong java.sql và javax.sql.
2. JDBC DriverManager hoặc DataSource chọn driver phù hợp.
3. MySQL Connector/J chuyển lời gọi JDBC thành thông điệp giao thức MySQL.
4. MySQL Server xác thực kết nối, thực thi SQL và trả kết quả.

Connector/J là driver **Type 4**: phần triển khai giao thức được viết bằng Java thuần và không cần thư viện native của MySQL client. Ứng dụng có thể dùng cùng API JDBC chuẩn mà không phải tự triển khai giao thức database.

Connector/J hỗ trợ hai hướng API:

- **JDBC API** dùng với Connection, PreparedStatement, ResultSet, DataSource và các framework như Spring JDBC, Hibernate hoặc MyBatis.
- **X DevAPI** là API riêng của MySQL, sử dụng X Protocol và mô hình collection/table. Đây không phải JDBC API và không thay thế driver JDBC trong ứng dụng đang dùng java.sql.

Một ứng dụng Spring Boot dùng JDBC URL jdbc:mysql://... đang dùng Connector/J qua giao thức MySQL classic. X DevAPI là lựa chọn riêng khi ứng dụng chủ động sử dụng API đó.

## 2. Phân biệt JDK, JRE và phiên bản JDBC

Ba khái niệm này có quan hệ nhưng không đồng nghĩa:

| Thành phần | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| JDK | Bộ công cụ phát triển Java, gồm compiler và runtime | Phiên bản dùng để biên dịch và target bytecode của ứng dụng |
| JRE/runtime | Môi trường chạy ứng dụng Java | Phiên bản Java thực tế của container, máy chủ hoặc tiến trình |
| JDBC API | Hợp đồng API Java dành cho truy cập database | Driver triển khai JDBC ở mức nào và có hỗ trợ phương thức ứng dụng cần không |

Một driver có thể chạy trên JRE mới hơn nhưng chỉ triển khai một mức JDBC cũ hơn. Ví dụ, Connector/J 26.10 triển khai JDBC 4.2. Nếu ứng dụng hoặc thư viện gọi phương thức chỉ có trong JDBC 4.3, driver có thể ném SQLFeatureNotSupportedException, dù ứng dụng đang chạy bằng một JDK mới.

Vì vậy, cần kiểm tra cả:

- Java runtime tối thiểu của driver.
- Mức JDBC được driver triển khai.
- Các API cụ thể mà framework hoặc ứng dụng gọi.
- Java bytecode target của chính ứng dụng.

Không chọn driver chỉ dựa trên kết quả java -version. Hãy đối chiếu với tài liệu tương thích của đúng phiên bản Connector/J và kiểm thử các API thực sự được dùng.

## 3. Đọc ma trận tương thích Connector/J

Tại thời điểm biên soạn bài học (tháng 11/2026), dòng phát hành hiện hành là Connector/J **26.10.0**, được công bố GA ngày 21/10/2026 và thay thế dòng 9.7. Tài liệu tương thích của 26.10 ghi:

- JRE 8 trở lên.
- JDK 8 trở lên nếu tự biên dịch Connector/J từ source.
- JDBC 4.2.
- MySQL Server 8.4 trở lên theo chương tương thích phiên bản.

Dòng Connector/J **9.7.0** được phát hành GA trước đó và release notes ghi hỗ trợ MySQL Server 8.0 trở lên, cũng triển khai JDBC 4.2. Vì vậy, nếu server đang ở MySQL 8.0, cần đọc kỹ ma trận của nhánh driver được chọn thay vì chỉ nhìn tên phiên bản mới nhất.

| Driver | Java runtime theo tài liệu | JDBC | MySQL Server theo tài liệu phiên bản |
|---|---|---|---|
| Connector/J 26.10.0 | JRE 8+ | 4.2 | Chương tương thích ghi 8.4+ |
| Connector/J 9.7.0 | Kiểm tra tài liệu nhánh 9.x và gói phát hành | 4.2 | 8.0+ |
| Connector/J 8.0.x | JRE 8+ theo tài liệu nhánh 8.0 | 4.2 | Đối chiếu patch và server mục tiêu; tài liệu nhánh 8.0 mô tả hỗ trợ MySQL 8.0+ |
| Connector/J 5.1.x | Java cũ theo tài liệu legacy | JDBC cũ hơn | Chỉ dùng khi phải duy trì nền tảng legacy đã được kiểm thử |

**Lưu ý về tài liệu phiên bản 26.10:** phần giới thiệu và phần What's New mô tả 26.10 dùng được với MySQL Server 8.0 trở lên, trong khi chương Compatibility with MySQL and Java Versions ghi 8.4 trở lên. Khi có khác biệt giữa mô tả tổng quan và ma trận chi tiết, không tự suy diễn khả năng hỗ trợ cho production. Đối chiếu release notes, ma trận hỗ trợ cập nhật và chính sách hỗ trợ của server đích; thử nghiệm với đúng cặp phiên bản trước khi triển khai.

### Chọn theo server trước, rồi kiểm tra Java

Một cách chọn thực tế:

- **MySQL Server 8.4 trở lên:** đánh giá Connector/J 26.10.0 trước, sau đó kiểm tra Java runtime, JDBC API và thay đổi tương thích.
- **MySQL Server 8.0:** Connector/J 9.7.0 được release notes ghi hỗ trợ 8.0 trở lên. Nếu muốn dùng 26.10.0, cần làm rõ khác biệt trong tài liệu chính thức và xác nhận bằng kiểm thử.
- **MySQL Server cũ hơn:** dùng ma trận và release notes của đúng nhánh driver. Không mặc định driver mới nhất hỗ trợ mọi server cũ.
- **Java runtime cũ:** chọn nhánh driver còn hỗ trợ runtime đó và có bản vá phù hợp. Nếu không có nhánh còn được hỗ trợ, lập kế hoạch nâng cấp Java/server thay vì kéo dài vô thời hạn một driver legacy.

Một cặp phiên bản được tài liệu ghi là tương thích vẫn cần kiểm tra authentication plugin, TLS, SQL mode, timezone, kiểu dữ liệu, prepared statement và các tính năng mà ứng dụng thực sự dùng.

## 4. JDBC 4.x và tự động nạp driver

Connector/J hiện đại hỗ trợ cơ chế tự đăng ký JDBC driver thông qua Service Provider. Khi JAR có trên classpath hoặc module path thích hợp, DriverManager có thể tìm driver mà không cần gọi Class.forName().

Tên lớp driver hiện hành:

~~~java
com.mysql.cj.jdbc.Driver
~~~

Ví dụ kết nối:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class MySqlConnectionExample {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:mysql://db.example.com:3306/app";
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            System.out.println("Connected: " + !connection.isClosed());
        }
    }
}
~~~

Class.forName("com.mysql.cj.jdbc.Driver") chỉ còn cần trong một số môi trường legacy có cơ chế class loading đặc biệt. Nếu DriverManager báo không tìm thấy driver, hãy kiểm tra JAR có thực sự nằm trong runtime classpath, dependency có bị exclude hoặc đóng gói sai hay không trước khi thêm lệnh Class.forName.

Không dùng tên lớp cũ com.mysql.jdbc.Driver trong ứng dụng mới. Đây là tên legacy của Connector/J 5.1; ứng dụng hiện đại nên dùng cơ chế auto-registration hoặc tên com.mysql.cj.jdbc.Driver khi cần khai báo rõ.

## 5. Khai báo dependency Maven và Gradle

Connector/J được phát hành trên Maven Central với:

- groupId: com.mysql
- artifactId: mysql-connector-j

Ví dụ Maven cho Connector/J 26.10.0:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>26.10.0</version>
    <scope>runtime</scope>
</dependency>
~~~

Ví dụ Gradle:

~~~kotlin
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j:26.10.0")
}
~~~

Nếu server mục tiêu là MySQL 8.0 và đã chọn nhánh 9.7 sau khi kiểm tra compatibility, thay version bằng một patch 9.7.x đã được phê duyệt trong dự án. Không dùng version động như dấu cộng hoặc latest.release trong production vì lần build sau có thể kéo về một driver khác mà không có thay đổi mã nguồn rõ ràng.

### Chọn scope

- **runtime** phù hợp khi mã nguồn chỉ dùng API JDBC chuẩn có sẵn trong JDK và driver chỉ cần khi ứng dụng chạy.
- **compile** có thể cần nếu mã nguồn trực tiếp tham chiếu lớp hoặc extension riêng của Connector/J.
- Trong Spring Boot, kiểm tra dependency được quản lý bởi BOM hoặc parent version nào. Không thêm một phiên bản Connector/J thứ hai nếu starter đã kéo driver vào dependency graph.

Kiểm tra dependency thực tế:

~~~bash
# Maven
mvn dependency:tree -Dincludes=com.mysql:mysql-connector-j

# Gradle
./gradlew dependencies --configuration runtimeClasspath
~~~

Chỉ nên có một phiên bản Connector/J trong runtime. Nếu đồng thời có JAR mysql-connector-java cũ và mysql-connector-j mới, classloader có thể nạp driver không như mong đợi hoặc gây lỗi khó chẩn đoán.

## 6. Kiểm tra driver và server thực tế lúc chạy

Không chỉ tin vào file pom.xml hoặc build.gradle. Ứng dụng có thể chạy với JAR khác do container, application server, plugin, shaded JAR hoặc thư viện được đóng gói sẵn.

Đọc metadata từ connection:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;

public class DriverDiagnostics {
    public static void printInfo(String url, String user, String password)
            throws Exception {
        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData metadata = connection.getMetaData();

            System.out.println("Driver: "
                    + metadata.getDriverName());
            System.out.println("Driver version: "
                    + metadata.getDriverVersion());
            System.out.println("Database: "
                    + metadata.getDatabaseProductName());
            System.out.println("Server version: "
                    + metadata.getDatabaseProductVersion());
            System.out.println("JDBC: "
                    + metadata.getJDBCMajorVersion() + "."
                    + metadata.getJDBCMinorVersion());
        }
    }
}
~~~

Có thể kiểm tra phiên bản Java đang chạy bằng:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
~~~

Các thông tin này giúp xác nhận runtime thực tế, driver thực tế và server thực tế trong cùng một lần kiểm tra. Tránh ghi URL chứa mật khẩu hoặc dữ liệu nhạy cảm vào log.

## 7. Những khác biệt cần thử khi nâng cấp driver

Nâng cấp từ Connector/J 5.1 lên 8.x, 9.x hoặc 26.x không chỉ là thay tên artifact. Các thay đổi có thể ảnh hưởng:

- Tên lớp driver và package.
- Tên hoặc giá trị mặc định của connection properties.
- Cách xử lý authentication plugin.
- TLS, chứng thư và xác minh hostname.
- Múi giờ, DATE, TIME, TIMESTAMP và ánh xạ java.time.
- Kiểu dữ liệu MySQL sang kiểu Java.
- Server-side prepared statements và client-side prepared statements.
- Metadata, warning, exception và SQLState.
- Hành vi của connection pool khi phát hiện connection không còn hợp lệ.

### Authentication

MySQL hiện đại thường dùng caching_sha2_password làm authentication plugin mặc định. Chọn driver đủ mới để hỗ trợ cơ chế xác thực của server; kiểm tra tài khoản ứng dụng và cách trao đổi thông tin xác thực trong môi trường có TLS.

Không khắc phục lỗi xác thực bằng cách hạ plugin tài khoản database trên production một cách tùy tiện. Trước tiên xác định driver, server, plugin của tài khoản và thông báo lỗi thực tế.

### TLS

Kết nối production nên xác minh chứng thư máy chủ và tên máy chủ. Với Connector/J, có thể cấu hình sslMode=VERIFY_IDENTITY cùng trust store phù hợp:

~~~text
jdbc:mysql://db.example.com:3306/app?sslMode=VERIFY_IDENTITY
~~~

Chứng thư phải được cấp cho hostname mà ứng dụng dùng để kết nối và chuỗi CA phải được runtime tin cậy. Nếu dùng Java 8 cũ, cần kiểm tra JSSE provider và phiên bản update; Oracle Java 8 trước 8u261 chỉ hỗ trợ TLS đến 1.2 theo tài liệu Connector/J, trong khi 8u261 trở lên hỗ trợ TLS 1.3.

Không dùng sslMode=DISABLED để xử lý nhanh lỗi chứng thư trên production. Hãy sửa trust chain, hostname hoặc cấu hình TLS.

### Timezone và kiểu thời gian

Thay đổi phiên bản driver có thể làm lộ ra giả định cũ về timezone. Kiểm tra:

- serverTimezone trong cấu hình legacy và thuộc tính thay thế được hỗ trợ ở phiên bản đang dùng.
- connectionTimeZone và cách driver đồng bộ timezone của session.
- Kiểu Java dùng cho DATE, TIME, DATETIME và TIMESTAMP.
- Hành vi khi daylight saving time thay đổi ở hệ thống có timezone.

Tạo kiểm thử round-trip: ghi giá trị thời gian đại diện, đọc lại và so sánh instant hoặc local date-time theo đúng ngữ nghĩa cột. Không chỉ kiểm tra chuỗi hiển thị.

## 8. Chọn driver trong Spring, Hibernate và connection pool

Framework không thay thế Connector/J. Spring JDBC, Hibernate, MyBatis hoặc HikariCP vẫn cần một JDBC driver để kết nối MySQL.

Khi dùng Spring Boot:

- Xác định starter hoặc BOM nào quản lý phiên bản driver.
- Kiểm tra dependency tree để tránh hai driver hoặc một driver bị override.
- Cấu hình URL, username, password và TLS trong secret/configuration management.
- Dùng DataSource/connection pool được framework quản lý; không tạo một DriverManager connection mới cho từng request trong ứng dụng web.

Khi dùng Hibernate:

- Kiểm tra phiên bản Hibernate hỗ trợ Java và JDBC API của dự án.
- Dùng dialect tương ứng với phiên bản Hibernate; không giả định driver tự chọn dialect chính xác trong mọi phiên bản.
- Kiểm tra ánh xạ kiểu dữ liệu, generated keys, batch update và transaction.

Khi dùng HikariCP hoặc pool khác:

- Kiểm tra validation và timeout.
- Kiểm tra connection lifetime, idle timeout và server wait timeout.
- Xác nhận connection bị lỗi được loại khỏi pool.
- Đo thời gian lấy connection, tạo connection mới và thực thi truy vấn.

## 9. Ma trận kiểm thử trước khi chọn phiên bản

Tạo một ma trận tối thiểu gồm các trục:

| Trục | Giá trị cần đưa vào kiểm thử |
|---|---|
| Java runtime | Phiên bản Java tối thiểu và phiên bản production |
| Connector/J | Phiên bản hiện tại và phiên bản dự kiến nâng cấp |
| MySQL Server | Phiên bản production, staging và phiên bản nâng cấp kế tiếp |
| JDBC/framework | Mức JDBC và phiên bản Spring/Hibernate/MyBatis |
| Authentication | Plugin của tài khoản ứng dụng |
| TLS | CA, hostname, TLS protocol và trust store |
| Connection pool | HikariCP hoặc pool đang dùng, timeout và validation |
| Dữ liệu | Unicode, decimal, binary, JSON và các kiểu thời gian |

Các ca kiểm thử nên bao gồm:

1. Kết nối mới và xác minh server identity qua TLS.
2. Đăng nhập bằng authentication plugin production.
3. Chạy SELECT, INSERT, UPDATE, DELETE và PreparedStatement có bind parameter.
4. Commit và rollback transaction.
5. Lấy generated key và đọc metadata.
6. Đọc/ghi Unicode, DECIMAL, BLOB, JSON và thời gian.
7. Kiểm tra batch update và số hàng cập nhật.
8. Kiểm tra connection pool khi server restart hoặc network gián đoạn.
9. Kiểm tra timeout, retry và exception mapping.
10. Chạy integration test với đúng phiên bản MySQL Server dự kiến.

Không chỉ kiểm thử một kết nối thành công. Một driver có thể kết nối được nhưng vẫn có khác biệt về timezone, prepared statement, kiểu dữ liệu hoặc pool khiến ứng dụng lỗi ở workload thật.

## 10. Quy trình nâng cấp Connector/J

**Bước 1 — Ghi nhận baseline**

Thu thập phiên bản Java, Connector/J, MySQL Server, JDBC API, framework, connection pool, URL properties và authentication plugin hiện tại. Lưu dependency tree để biết JAR nào đang được đóng gói.

**Bước 2 — Đọc release notes**

Đọc compatibility matrix và release notes từ phiên bản hiện tại đến phiên bản mục tiêu. Tập trung vào connection properties bị đổi, hành vi mặc định, authentication, TLS, timezone và các lỗi đã được sửa.

**Bước 3 — Nâng trong môi trường kiểm thử**

Chỉ đổi một phiên bản driver trong dependency management. Chạy integration test trên cùng Java runtime và cùng phiên bản server như production. Không đồng thời nâng Java, framework, server và driver nếu chưa có kế hoạch tách nguyên nhân khi lỗi.

**Bước 4 — Kiểm tra runtime artifact**

Xem dependency tree, nội dung JAR đóng gói và metadata JDBC khi ứng dụng chạy. Xác nhận không còn driver cũ bị nạp từ thư mục lib của application server hoặc container base image.

**Bước 5 — Triển khai có kiểm soát**

Triển khai theo nhóm instance nhỏ, theo dõi lỗi kết nối, authentication, SQL exception, latency và pool saturation. Giữ phiên bản artifact cũ và phương án quay lại đã kiểm thử.

**Bước 6 — Hoàn tất**

Sau khi các chỉ số ổn định, cập nhật tài liệu phiên bản, dependency lock và quy trình build. Loại bỏ JAR cũ khỏi môi trường triển khai để tránh bị nạp lại ngoài ý muốn.

## 11. Xử lý lỗi tương thích thường gặp

### No suitable driver

Driver không được tìm thấy hoặc URL không được driver nhận diện. Kiểm tra dependency runtime, classpath, artifact bị exclude và tiền tố URL jdbc:mysql:.

### ClassNotFoundException: com.mysql.cj.jdbc.Driver

JAR không có trong classloader đang chạy, dependency chưa được đóng gói hoặc ứng dụng đang nạp từ classloader khác. Kiểm tra runtime artifact thay vì chỉ xem dependency trong IDE.

### SQLFeatureNotSupportedException

Ứng dụng hoặc framework gọi phương thức JDBC mà driver không triển khai. Đối chiếu mức JDBC thực tế của driver và xem có thể dùng API tương thích hay cần nâng driver.

### Lỗi authentication

Kiểm tra plugin xác thực của user, phiên bản Connector/J, TLS và quyền tài khoản. Không thay đổi cơ chế xác thực server trước khi xác định nguyên nhân.

### Lỗi TLS hoặc chứng thư

Kiểm tra hostname trên certificate, trust store, CA chain, phiên bản Java/JSSE và sslMode. Tránh tắt xác minh danh tính để bỏ qua lỗi.

### Lỗi timezone hoặc dữ liệu thời gian lệch

Kiểm tra timezone server, timezone session, cấu hình driver và kiểu Java dùng để đọc/ghi. Tạo kiểm thử round-trip với instant và local date-time đại diện.

### Ứng dụng chạy nhưng dùng sai driver version

Kiểm tra DatabaseMetaData.getDriverVersion(), dependency tree, thư mục thư viện của application server và các JAR được đóng gói trong ứng dụng.

## 12. Checklist chọn Connector/J

- [ ] Đã biết phiên bản Java runtime thực tế của ứng dụng.
- [ ] Đã phân biệt JDK dùng build với JRE/runtime dùng chạy.
- [ ] Đã biết JDBC API mà framework hoặc ứng dụng yêu cầu.
- [ ] Đã đối chiếu Connector/J với đúng phiên bản MySQL Server.
- [ ] Đã đọc compatibility matrix và release notes của nhánh driver.
- [ ] Đã chọn một phiên bản driver cụ thể và pin dependency.
- [ ] Runtime chỉ có một phiên bản Connector/J.
- [ ] Driver được xác minh bằng DatabaseMetaData khi chạy.
- [ ] Authentication và TLS được thử với cấu hình production.
- [ ] Đã kiểm tra timezone, kiểu dữ liệu, transaction và prepared statement.
- [ ] Đã chạy integration test với đúng server version.
- [ ] Đã có phương án rollback driver đã kiểm thử.

## Tài liệu tham khảo

- [MySQL Connector/J Developer Guide — Overview](https://dev.mysql.com/doc/connector-j/en/connector-j-overview.html)
- [MySQL Connector/J — Compatibility with MySQL and Java Versions](https://dev.mysql.com/doc/connector-j/en/connector-j-versions.html)
- [MySQL Connector/J — Installing Using Maven](https://dev.mysql.com/doc/connector-j/en/connector-j-installing-maven.html)
- [MySQL Connector/J — Driver/Datasource Class Name](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-driver-name.html)
- [MySQL Connector/J 26.10 Release Notes](https://dev.mysql.com/doc/relnotes/connector-j/en/news-26-10-0.html)
- [MySQL Connector/J 9.7 Release Notes](https://dev.mysql.com/doc/relnotes/connector-j/en/news-9-7-0.html)

## Kết luận

Chọn Connector/J là bài toán tương thích giữa Java runtime, JDBC API, MySQL Server và framework của ứng dụng. Connector/J 26.10.0 là dòng GA hiện hành tại thời điểm biên soạn và triển khai JDBC 4.2; dòng 9.7.0 có release notes ghi hỗ trợ MySQL Server 8.0 trở lên. Hãy đọc ma trận của đúng nhánh, kiểm tra khác biệt giữa mô tả tổng quan và bảng tương thích khi có, pin dependency và xác minh driver thực tế lúc chạy. Một kết nối thành công là bước đầu; kiểm thử authentication, TLS, timezone, kiểu dữ liệu, transaction và connection pool mới cho thấy driver phù hợp với ứng dụng.
