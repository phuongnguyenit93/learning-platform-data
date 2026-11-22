# Classpath JDBC, driver và nguồn dữ liệu nhúng trong các nhánh cấu hình

## 1. Mục tiêu: hiểu vì sao Spring Boot chọn một DataSource cụ thể

Khi thêm dependency JDBC vào ứng dụng Spring Boot, nhiều người mong rằng Spring sẽ “tự kết nối database”. Thực tế, Spring Boot phải đánh giá nhiều điều kiện trước khi đăng ký bean DataSource:

- API JDBC và Spring JDBC có mặt trên classpath hay không?
- Ứng dụng có khai báo một DataSource/XADataSource riêng hay chưa?
- Có bean R2DBC ConnectionFactory khiến cấu hình JDBC tự động phải nhường quyền không?
- Class của connection pool nào có mặt: HikariCP, Tomcat JDBC, Commons DBCP2 hay Oracle UCP?
- Driver của database có trong runtime classpath không?
- Có URL kết nối tường minh hay Spring cần suy ra một URL cho database nhúng?
- Nếu có nhiều engine nhúng, H2, HSQL hay Derby được chọn?

Bài học thuộc nhóm **Ví dụ JDBC**, tập trung vào quan hệ giữa **classpath**, **JDBC driver**, **connection pool**, **embedded database** và các nhánh bên trong **DataSourceAutoConfiguration** của Spring Boot 3.3.

Sau bài này, bạn có thể đọc điều kiện để biết vì sao Boot đi vào nhánh pooled hoặc embedded, hiểu vì sao H2 có thể chạy bên dưới HikariCP, nhận diện lỗi thiếu driver và kiểm chứng bằng một ứng dụng Java 17+ chạy được.

## 2. Phân biệt bốn thành phần: JDBC API, driver, database engine và pool

Bốn khái niệm này có liên quan nhưng không thay thế nhau.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| JDBC API | Hợp đồng Java để ứng dụng làm việc với kết nối, câu lệnh và kết quả SQL | javax.sql.DataSource, java.sql.Connection, java.sql.Driver |
| JDBC driver | Cài đặt giao thức để Java nói chuyện với một hệ quản trị database cụ thể | org.h2.Driver, org.postgresql.Driver |
| Database engine | Phần mềm thực sự lưu trữ và thực thi SQL | H2, PostgreSQL, MySQL, SQL Server |
| Connection pool / DataSource implementation | Quản lý và cấp phát kết nối cho ứng dụng | HikariCP, Tomcat JDBC Pool, Commons DBCP2 |

Ví dụ với PostgreSQL:

- Ứng dụng gọi JdbcTemplate hoặc JDBC API.
- HikariCP quản lý pool và cấp Connection.
- PostgreSQL JDBC Driver chuyển các lời gọi JDBC thành giao tiếp với server.
- PostgreSQL server thực thi SQL và lưu dữ liệu.

**HikariCP không phải PostgreSQL driver.** Thêm HikariCP không tự thêm driver PostgreSQL; thêm driver PostgreSQL cũng không tự tạo connection pool.

Với H2 nhúng, database engine và JDBC driver nằm trong cùng dependency H2. H2 có thể chạy trong tiến trình Java, thường dùng URL dạng jdbc:h2:mem:... để tạo database trong bộ nhớ.

### Classpath cần những gì?

- **DataSource** thuộc API Java, nằm trong module java.sql của JDK.
- **EmbeddedDatabaseType**, **JdbcTemplate**, **EmbeddedDatabaseBuilder** thuộc Spring JDBC (artifact spring-jdbc).
- **HikariDataSource** thuộc HikariCP.
- **org.h2.Driver** và engine H2 thuộc artifact com.h2database:h2.
- Driver của PostgreSQL thuộc artifact org.postgresql:postgresql.

Một điểm quan trọng của Spring Boot 3.3: DataSourceAutoConfiguration có điều kiện classpath trên cả DataSource và EmbeddedDatabaseType. Vì EmbeddedDatabaseType thuộc Spring JDBC, chỉ có JDBC API và một vendor driver mà thiếu spring-jdbc thì auto-configuration JDBC chuẩn của Boot không thỏa điều kiện classpath này.

Với ứng dụng thông thường, dùng spring-boot-starter-jdbc là cách thuận tiện vì starter mang theo Spring JDBC và HikariCP. Driver của database bên ngoài vẫn phải được thêm riêng.

## 3. DataSourceAutoConfiguration: điều kiện ở lớp ngoài

Trong Spring Boot 3.3.13, DataSourceAutoConfiguration có các điều kiện quan trọng:

    @AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
    @ConditionalOnClass({
        DataSource.class,
        EmbeddedDatabaseType.class
    })
    @ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
    @EnableConfigurationProperties(DataSourceProperties.class)

Có thể đọc theo từng bước:

1. **DataSource.class có trên classpath:** JDK cung cấp JDBC DataSource API.
2. **EmbeddedDatabaseType.class có trên classpath:** ứng dụng có Spring JDBC.
3. **Không có bean R2DBC ConnectionFactory:** nếu context đã có ConnectionFactory cho R2DBC, JDBC DataSource auto-configuration mặc định nhường quyền. Đây là cách Boot tránh tự động bật thêm JDBC blocking trong một ứng dụng đã dùng R2DBC.
4. **DataSourceProperties được bind:** các thuộc tính chuẩn dưới prefix spring.datasource được đưa vào object cấu hình.
5. **Thứ tự trước SQL initialization:** DataSource được xử lý trước cấu hình khởi tạo database bằng script.

Lưu ý: điều kiện ở lớp ngoài chỉ xác định DataSourceAutoConfiguration có đủ điều kiện tham gia hay không. Việc tạo bean DataSource thực tế nằm trong các cấu hình lồng nhau và còn phụ thuộc vào pool, driver, URL và bean do người dùng cung cấp.

### Khi nào JDBC auto-configuration không chạy?

| Tình huống | Hệ quả |
|---|---|
| Thiếu spring-jdbc nên không có EmbeddedDatabaseType | Điều kiện classpath của DataSourceAutoConfiguration không khớp |
| Có bean R2DBC ConnectionFactory | JDBC DataSource auto-configuration mặc định back off |
| Chỉ thiếu H2 nhưng đã có URL và PostgreSQL driver | Vẫn có thể tạo DataSource pooled cho PostgreSQL |
| Có DataSource bean do ứng dụng tự khai báo | Các nhánh embedded/pooled mặc định không tạo thêm DataSource |
| Có XADataSource bean | Các nhánh embedded/pooled cũng back off theo điều kiện missing-bean |

Nếu ứng dụng reactive có R2DBC ConnectionFactory nhưng vẫn chủ ý muốn dùng JDBC, tài liệu Spring Boot cho phép import DataSourceAutoConfiguration một cách tường minh. Chỉ nên làm khi kiến trúc chấp nhận sử dụng JDBC blocking bên cạnh R2DBC.

## 4. Hai nhánh chính bên trong DataSourceAutoConfiguration

Boot 3.3.13 có hai nested configuration chính:

- **PooledDataSourceConfiguration**
- **EmbeddedDatabaseConfiguration**

Cả hai đều có điều kiện không tạo DataSource mặc định khi đã tồn tại bean DataSource hoặc XADataSource phù hợp.

Sơ đồ khái quát:

    DataSourceAutoConfiguration
        |
        |-- điều kiện classpath + không có R2DBC ConnectionFactory
        |
        +--> PooledDataSourceConfiguration
        |       |
        |       |-- spring.datasource.type được đặt
        |       |       HOẶC
        |       |-- DataSourceBuilder tìm được pool được hỗ trợ
        |       |
        |       +--> Hikari / Tomcat / DBCP2 / Oracle UCP / Generic
        |
        +--> EmbeddedDatabaseConfiguration
                |
                |-- spring.datasource.url không có giá trị có text
                |-- nhánh pooled không khớp
                |-- tìm thấy engine nhúng H2/HSQL/Derby
                |
                +--> EmbeddedDataSourceConfiguration

Đây là mô hình quyết định hai nhánh mặc định. Một DataSource bean do người dùng cung cấp có thể khiến cả hai nhánh không được áp dụng.

## 5. Nhánh pooled: chọn connection pool theo classpath

PooledDataSourceConfiguration được xét khi PooledDataSourceCondition khớp. Trong Spring Boot 3.3.13, condition này khớp nếu:

- Thuộc tính **spring.datasource.type** có giá trị; hoặc
- DataSourceBuilder tìm được một DataSource implementation được hỗ trợ trên classpath.

Đây là phép OR. Chỉ cần một trong hai nhánh con khớp.

### 5.1. Thứ tự chọn pool mặc định

Nếu không đặt spring.datasource.type, Spring Boot chọn theo thứ tự ưu tiên:

| Ưu tiên | Connection pool | Điều kiện |
|---:|---|---|
| 1 | HikariCP | Hikari có trên classpath |
| 2 | Tomcat JDBC Pool | Hikari không có, Tomcat pool có |
| 3 | Commons DBCP2 | Hai pool trên không có, DBCP2 có |
| 4 | Oracle UCP | Các lựa chọn trước không có, UCP có |

Nếu dùng spring-boot-starter-jdbc hoặc spring-boot-starter-data-jpa, HikariCP thường đã được kéo vào dependency tree. Vì vậy, khi dùng các starter này, Hikari thường là lựa chọn mặc định.

Nếu muốn chọn pool cụ thể, có thể cấu hình:

    spring.datasource.type=com.zaxxer.hikari.HikariDataSource

Giá trị type là tên class của DataSource implementation. Class tương ứng phải tồn tại trên runtime classpath. Nếu đặt một class không có mặt, ứng dụng sẽ lỗi khi tạo DataSource.

Các thuộc tính dành riêng cho từng pool có namespace riêng:

    spring.datasource.hikari.maximum-pool-size=20
    spring.datasource.hikari.minimum-idle=2
    spring.datasource.tomcat.max-active=50
    spring.datasource.dbcp2.max-total=30

Chỉ dùng thuộc tính của pool đang thực sự được chọn. Đặt spring.datasource.hikari.* không khiến Hikari xuất hiện trên classpath và cũng không ép Boot chọn Hikari nếu class Hikari không có.

### 5.2. Pool có mặt không đồng nghĩa driver đã có

PooledDataSourceCondition kiểm tra khả năng tìm thấy một DataSource implementation, không thay thế việc kiểm tra driver database.

Ví dụ:

- HikariCP có trên classpath.
- spring.datasource.url là jdbc:postgresql://localhost:5432/inventory.
- Nhưng dependency org.postgresql:postgresql bị thiếu.

Boot vẫn có thể chọn nhánh pooled vì Hikari tồn tại. Đến lúc xác định driver hoặc khởi tạo DataSource, ứng dụng không tìm được driver phù hợp và startup thất bại.

**Pool quản lý kết nối; driver kết nối tới database.** Cần cả hai khi dùng nhánh pooled với database JDBC thông thường.

## 6. Nhánh embedded: điều kiện để tạo EmbeddedDatabase

EmbeddedDatabaseConfiguration có EmbeddedDatabaseCondition. Trong Spring Boot 3.3.13, condition này kiểm tra theo thứ tự:

1. Nếu spring.datasource.url có giá trị chứa text, embedded branch không khớp.
2. Nếu PooledDataSourceCondition đã khớp, embedded branch không khớp.
3. Nếu không tìm thấy embedded database engine phù hợp trên classpath, condition không khớp.
4. Nếu tìm thấy engine nhúng, condition khớp và Boot import EmbeddedDataSourceConfiguration.

Spring Boot 3.3 hỗ trợ các engine nhúng:

| Engine | Dependency thường dùng | Driver |
|---|---|---|
| H2 | com.h2database:h2 | org.h2.Driver |
| HSQLDB | org.hsqldb:hsqldb | org.hsqldb.jdbc.JDBCDriver |
| Apache Derby | org.apache.derby:derby | org.apache.derby.iapi.jdbc.AutoloadedDriver |

Derby được Spring Boot 3.3 ghi nhận là deprecated trong tài liệu SQL database. Với ví dụ mới, H2 thường là lựa chọn đơn giản.

Nếu có nhiều engine nhúng trên classpath, chọn engine bằng:

    spring.datasource.embedded-database-connection=h2

Các giá trị tương ứng có thể là h2, hsqldb, derby hoặc none. Đặt none để tắt việc phát hiện embedded database.

Nếu không có pool và không có spring.datasource.url, nhưng H2 có trên classpath, Boot có thể tạo EmbeddedDatabase thông qua Spring JDBC EmbeddedDatabaseBuilder. Bạn không cần tự cung cấp JDBC URL.

### 6.1. Embedded database không đồng nghĩa luôn là bean EmbeddedDatabase

Đây là điểm rất dễ nhầm:

**Database engine nhúng** và **loại DataSource bean** là hai khái niệm khác nhau.

Khi H2 nằm trên classpath nhưng HikariCP cũng có mặt, PooledDataSourceCondition khớp. EmbeddedDatabaseCondition thấy nhánh pooled đã khớp nên không chạy nhánh EmbeddedDatabaseConfiguration. Tuy nhiên DataSourceProperties vẫn có thể xác định URL H2 trong bộ nhớ; HikariDataSource được tạo và kết nối tới engine H2 đó.

Kết quả là:

- Database engine: H2 nhúng.
- DataSource bean: HikariDataSource.
- Connection pool: HikariCP.
- JDBC driver: H2 Driver.

Chỉ khi nhánh pooled không khớp và engine nhúng có mặt, Boot mới đi vào nhánh trực tiếp EmbeddedDatabaseConfiguration để tạo EmbeddedDatabase.

### 6.2. Tác dụng của spring.datasource.url

Một URL không rỗng làm EmbeddedDatabaseCondition không khớp. Khi đó:

- Nếu có pool hoặc spring.datasource.type hợp lệ, Boot có thể dùng nhánh pooled với URL đã khai báo.
- Nếu không có pool và cũng không có type, nhánh pooled không khớp; embedded branch cũng bị URL chặn. Khi ấy Boot không thể tự tạo DataSource theo hai nhánh mặc định.

Ví dụ cấu hình:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory

có nghĩa ứng dụng đang chỉ định một đích JDBC bên ngoài. Cần driver PostgreSQL và một DataSource implementation phù hợp trên classpath hoặc được chỉ định bằng type.

### 6.3. Database nhúng và tên database

H2 in-memory thường có URL dạng:

    jdbc:h2:mem:demo

Database bộ nhớ thường không giữ dữ liệu sau khi tiến trình kết thúc. Nếu cấu hình URL embedded thủ công, cần chú ý vòng đời database. Tài liệu Spring Boot khuyến nghị kiểm soát hành vi tự đóng của H2 bằng DB_CLOSE_ON_EXIT=FALSE trong những trường hợp tự cấu hình URL, để Spring Boot điều khiển thời điểm đóng database sau khi ứng dụng ngừng sử dụng.

Trong test, nhiều application context có thể vô tình dùng lại cùng embedded database. Đặt:

    spring.datasource.generate-unique-name=true

để tạo tên database riêng cho từng context khi phù hợp.

## 7. JDBC driver: phát hiện, khai báo và lỗi classpath

Driver là lớp triển khai java.sql.Driver. Spring Boot dùng DataSourceProperties để xác định driver dựa trên cấu hình và Environment.

### 7.1. Có cần khai báo driver-class-name không?

Thông thường **không cần** nếu JDBC URL thuộc loại mà Spring Boot có thể nhận diện và driver tương ứng có trên classpath.

Ví dụ PostgreSQL:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
    spring.datasource.username=app_user
    spring.datasource.password=local-dev-password

Với dependency driver PostgreSQL có mặt, Boot có thể suy ra driver từ URL. Nếu cần khai báo tường minh:

    spring.datasource.driver-class-name=org.postgresql.Driver

H2 có driver:

    spring.datasource.driver-class-name=org.h2.Driver

Việc khai báo driver-class-name không tải dependency từ Maven/Gradle. Nó chỉ chỉ ra class mà ứng dụng cần tải; nếu class không tồn tại, ứng dụng vẫn lỗi.

### 7.2. Vai trò của DataSourceProperties

DataSourceProperties có prefix spring.datasource và cung cấp các phương thức như:

- determineUrl(): xác định URL kết nối.
- determineDriverClassName(): xác định class driver.
- determineUsername() / determinePassword(): xác định thông tin đăng nhập.
- initializeDataSourceBuilder(): khởi tạo DataSourceBuilder từ các thuộc tính đã bind.
- getEmbeddedDatabaseConnection(): cho biết lựa chọn embedded database connection.

Quy tắc thực hành:

1. Nếu URL được cấu hình, Boot sử dụng URL đó.
2. Nếu driver class được cấu hình tường minh, class phải loadable.
3. Nếu driver class không được cấu hình, Boot cố suy ra driver từ JDBC URL hoặc embedded database được chọn.
4. Nếu không thể xác định URL/driver phù hợp, việc tạo DataSource thất bại với lỗi cấu hình/driver.

Không nên thêm driver-class-name chỉ để “thử cho chạy”. Hãy kiểm tra URL và dependency trước; khai báo class tường minh khi cần hoặc khi dùng driver đặc biệt.

### 7.3. Driver phải ở runtime classpath

Trong Maven, driver database thường được khai báo với scope runtime:

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

H2:

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

Nếu driver chỉ được khai báo ở scope test, ứng dụng có thể chạy test được nhưng không có driver khi chạy thật.

Driver JDBC hiện đại thường tự đăng ký thông qua cơ chế service provider của JDBC. Ứng dụng thông thường không cần gọi Class.forName(driver) thủ công; quan trọng là driver JAR có trên classpath và URL phù hợp.

### 7.4. Driver và pool là hai dependency riêng

| Trường hợp | Pool | Driver | Kết quả |
|---|---|---|---|
| Hikari + PostgreSQL driver + PostgreSQL URL | Có | Có | Có thể tạo pooled DataSource |
| Hikari + PostgreSQL URL nhưng thiếu driver | Có | Không | Không thể kết nối; tạo DataSource/connection thất bại |
| PostgreSQL driver nhưng không có pool và không có type | Không | Có | Không đủ điều kiện cho pooled branch; embedded branch không phù hợp với URL ngoài |
| H2 engine + Hikari + không URL | Có | H2 driver có cùng dependency | Thường tạo HikariDataSource kết nối H2 in-memory |
| H2 engine + không pool + không URL | Không | H2 driver có | Có thể đi vào EmbeddedDatabaseConfiguration |

## 8. Các thuộc tính quan trọng và chúng điều khiển điều gì

| Thuộc tính | Điều khiển | Không có nghĩa là |
|---|---|---|
| spring.datasource.url | Đích JDBC | Không chọn connection pool |
| spring.datasource.driver-class-name | Class JDBC driver | Không thêm driver JAR vào classpath |
| spring.datasource.type | Class DataSource implementation | Không chọn database engine |
| spring.datasource.username/password | Thông tin xác thực | Không quyết định embedded hay pooled branch |
| spring.datasource.embedded-database-connection | Engine nhúng được chọn hoặc none | Không ép dùng EmbeddedDatabase bean nếu pool có mặt |
| spring.datasource.generate-unique-name | Tên embedded database được sinh | Không tự tạo một database server bên ngoài |
| spring.datasource.jndi-name | Lấy DataSource từ JNDI | Khi dùng JNDI, URL/driver/username/password thông thường bị bỏ qua |
| spring.datasource.hikari.* | Cấu hình riêng HikariCP | Không có tác dụng nếu pool khác được chọn |

Đừng nhầm lẫn ba thuộc tính sau:

- **url** chọn đích database.
- **driver-class-name** chọn driver.
- **type** chọn implementation của DataSource/connection pool.

## 9. Ví dụ chạy được: Spring Boot 3.3, Java 17 và H2

Ví dụ này dùng spring-boot-starter-jdbc và H2. Starter JDBC kéo HikariCP vào classpath. Không khai báo URL để Boot tự chọn H2 in-memory. Vì Hikari có mặt, nhánh pooled được chọn; DataSource được tạo là HikariDataSource và kết nối tới H2.

### 9.1. Cấu trúc dự án

    jdbc-classpath-demo/
    ├── pom.xml
    └── src/
        └── main/
            ├── java/demo/jdbc/
            │   └── JdbcClasspathDemo.java
            └── resources/
                └── application.properties

### 9.2. pom.xml

    <?xml version="1.0" encoding="UTF-8"?>
    <project xmlns="http://maven.apache.org/POM/4.0.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                                 https://maven.apache.org/xsd/maven-4.0.0.xsd">
        <modelVersion>4.0.0</modelVersion>

        <parent>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-parent</artifactId>
            <version>3.3.13</version>
            <relativePath/>
        </parent>

        <groupId>demo</groupId>
        <artifactId>jdbc-classpath-demo</artifactId>
        <version>1.0.0</version>

        <properties>
            <java.version>17</java.version>
        </properties>

        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-jdbc</artifactId>
            </dependency>

            <dependency>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
                <scope>runtime</scope>
            </dependency>
        </dependencies>

        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                </plugin>
            </plugins>
        </build>
    </project>

### 9.3. application.properties

    spring.datasource.embedded-database-connection=h2
    spring.datasource.generate-unique-name=true

Không đặt spring.datasource.url trong ví dụ này. Boot có thể nhận ra engine H2 trên classpath và tạo URL in-memory. Vì starter-jdbc kéo HikariCP vào, DataSource implementation là Hikari.

### 9.4. JdbcClasspathDemo.java

    package demo.jdbc;

    import java.sql.Connection;
    import java.sql.DatabaseMetaData;
    import javax.sql.DataSource;

    import org.springframework.boot.CommandLineRunner;
    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;
    import org.springframework.jdbc.core.JdbcTemplate;

    @SpringBootApplication
    public class JdbcClasspathDemo implements CommandLineRunner {

        private final DataSource dataSource;
        private final JdbcTemplate jdbcTemplate;

        public JdbcClasspathDemo(
                DataSource dataSource,
                JdbcTemplate jdbcTemplate) {
            this.dataSource = dataSource;
            this.jdbcTemplate = jdbcTemplate;
        }

        public static void main(String[] args) {
            SpringApplication.run(JdbcClasspathDemo.class, args);
        }

        @Override
        public void run(String... args) throws Exception {
            jdbcTemplate.execute(
                    "create table demo_item (" +
                    "id bigint generated by default as identity primary key, " +
                    "name varchar(100) not null)");

            jdbcTemplate.update(
                    "insert into demo_item(name) values (?)",
                    "JDBC works");

            String value = jdbcTemplate.queryForObject(
                    "select name from demo_item where id = 1",
                    String.class);

            try (Connection connection = dataSource.getConnection()) {
                DatabaseMetaData metadata = connection.getMetaData();

                System.out.println(
                        "dataSourceType=" +
                        dataSource.getClass().getSimpleName());
                System.out.println(
                        "databaseProduct=" +
                        metadata.getDatabaseProductName());
                System.out.println(
                        "driverName=" +
                        metadata.getDriverName());
            }

            System.out.println("queryResult=" + value);
        }
    }

### 9.5. Chạy chương trình

Từ thư mục có pom.xml, cần JDK 17+ và Maven:

    mvn -q spring-boot:run

Các dòng do chương trình in ra:

    dataSourceType=HikariDataSource
    databaseProduct=H2
    driverName=H2 JDBC Driver
    queryResult=JDBC works

Spring Boot cũng có thể ghi log startup. Bốn dòng trên là output do các lệnh System.out.println của chương trình tạo ra.

### 9.6. Vì sao kết quả là HikariDataSource chứ không phải EmbeddedDatabase?

1. spring-boot-starter-jdbc đưa HikariCP vào classpath.
2. PooledDataSourceCondition khớp vì DataSourceBuilder tìm được Hikari.
3. EmbeddedDatabaseCondition không khớp vì pooled condition đã khớp.
4. DataSourceProperties nhận ra embedded engine H2 và xác định URL in-memory.
5. DataSourceConfiguration.Hikari tạo HikariDataSource.
6. Hikari lấy kết nối qua H2 JDBC driver; JdbcTemplate thực hiện SQL qua DataSource.

Ví dụ chứng minh rằng **engine H2 nhúng có thể được sử dụng bên dưới một pooled DataSource**. “Database nhúng” không tự động đồng nghĩa với “bean DataSource kiểu EmbeddedDatabase”.

## 10. Khi nào đi vào nhánh EmbeddedDatabaseConfiguration trực tiếp?

Để Boot dùng nhánh EmbeddedDatabaseConfiguration, cần đồng thời thỏa:

- Có spring-jdbc để DataSourceAutoConfiguration đủ điều kiện classpath.
- Có engine nhúng phù hợp, ví dụ H2.
- spring.datasource.url không có giá trị chứa text.
- Không có pool được hỗ trợ trên classpath và không đặt spring.datasource.type.
- Chưa có DataSource hoặc XADataSource bean do người dùng cung cấp.

Trong ứng dụng demo, nếu muốn thử nhánh này, có thể bỏ dependency spring-boot-starter-jdbc (vốn kéo Hikari vào) và dùng spring-boot-starter cùng spring-jdbc trực tiếp, đồng thời giữ H2 trên runtime classpath. Cần bảo đảm dependency tree không kéo vào một pool khác qua starter hoặc thư viện khác.

Khi đó PooledDataSourceCondition không khớp; EmbeddedDatabaseCondition có thể khớp và Boot tạo EmbeddedDatabase bằng Spring JDBC.

Đây là cấu hình minh họa để hiểu nhánh nội bộ. Với ứng dụng cần pool để xử lý tải thực tế, thường giữ starter-jdbc và sử dụng pooled DataSource.

## 11. Ví dụ cấu hình database bên ngoài: PostgreSQL

Khi chuyển từ H2 sang PostgreSQL, cần thay engine/driver và URL. Ví dụ dependency:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

Cấu hình:

    spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
    spring.datasource.username=app_user
    spring.datasource.password=local-dev-password

Với dependency driver PostgreSQL có mặt, Boot có thể suy ra driver từ URL. Nếu muốn khai báo tường minh:

    spring.datasource.driver-class-name=org.postgresql.Driver

Khi có Hikari trên classpath, Boot chọn pooled branch. URL PostgreSQL không rỗng cũng làm embedded branch không khớp. Hikari quản lý kết nối, PostgreSQL driver giao tiếp với PostgreSQL server.

Không đưa password thật vào source control. Dùng biến môi trường, secret store hoặc cơ chế quản lý bí mật phù hợp.

### 11.1. Đổi URL nhưng quên driver

Triệu chứng phổ biến:

- Đã thêm spring-boot-starter-jdbc.
- Đã đặt jdbc:postgresql://...
- Ứng dụng báo không thể xác định hoặc không tải được driver class.

Nguyên nhân thường là dependency org.postgresql:postgresql bị thiếu, chỉ có ở test scope hoặc không được đóng gói trong runtime classpath. Thêm driver đúng phiên bản tương thích với dependency management của Spring Boot.

### 11.2. Đặt driver class sai

Nếu cấu hình:

    spring.datasource.driver-class-name=com.mysql.jdbc.Driver

nhưng dependency/driver hiện tại không cung cấp class đó, Spring Boot không thể tải class. Với MySQL Connector/J hiện đại, class thường dùng là com.mysql.cj.jdbc.Driver. Tốt nhất để Boot suy ra driver từ URL khi có thể.

## 12. Bảng quyết định các nhánh theo classpath và cấu hình

| Classpath / cấu hình | Nhánh dự kiến | DataSource kết quả |
|---|---|---|
| spring-jdbc + H2, không URL, không pool | Embedded | EmbeddedDatabase |
| spring-boot-starter-jdbc + H2, không URL | Pooled | HikariDataSource trỏ H2 in-memory |
| spring-boot-starter-jdbc + PostgreSQL driver + PostgreSQL URL | Pooled | HikariDataSource trỏ PostgreSQL |
| Hikari có, URL PostgreSQL, thiếu PostgreSQL driver | Pooled được chọn nhưng khởi tạo/kết nối lỗi | Không có kết nối thành công |
| H2 có, URL H2, không pool và không type | Embedded bị URL chặn; pooled không khớp | Boot không tạo DataSource theo hai nhánh mặc định |
| Có spring.datasource.type và class DataSource hợp lệ | Pooled | Implementation được chỉ định |
| Có DataSource bean do ứng dụng tự tạo | Hai nhánh mặc định back off | DataSource người dùng |
| Có R2DBC ConnectionFactory bean | DataSourceAutoConfiguration mặc định back off | Không có JDBC DataSource tự động từ nhánh này |
| Có H2 và PostgreSQL driver cùng lúc, không URL | Cần xác định embedded engine phù hợp | Dùng spring.datasource.embedded-database-connection để chọn engine nhúng |
| Có spring.datasource.embedded-database-connection=none và không URL | Không có embedded engine được chọn | Cần URL/driver hoặc cấu hình DataSource riêng |

Bảng là dự đoán theo các điều kiện mặc định của Boot 3.3.13. Một auto-configuration khác, JNDI, custom DataSource, XADataSource hoặc điều kiện classpath khác có thể làm kết quả thay đổi.

## 13. JNDI và DataSource do người dùng tự cung cấp

Không phải ứng dụng nào cũng để Boot tự tạo DataSource.

### 13.1. JNDI DataSource

Khi chạy trong application server, có thể dùng DataSource được server quản lý:

    spring.datasource.jndi-name=java:jboss/datasources/inventory

Với JNDI, Boot tra cứu DataSource theo tên. Các thuộc tính URL, driver-class-name, username và password thông thường bị bỏ qua vì server đã quản lý cấu hình kết nối.

JndiDataSourceAutoConfiguration là nhánh riêng; không nhầm nó với EmbeddedDatabaseConfiguration hoặc PooledDataSourceConfiguration.

### 13.2. Tự khai báo DataSource bean

Ví dụ minh họa:

    @Configuration(proxyBeanMethods = false)
    public class CustomJdbcConfiguration {

        @Bean
        DataSource dataSource() {
            return DataSourceBuilder.create()
                    .url("jdbc:h2:mem:custom")
                    .username("sa")
                    .password("")
                    .driverClassName("org.h2.Driver")
                    .build();
        }
    }

Đoạn này cần import DataSourceBuilder, DataSource, Configuration và H2 driver có trên classpath. Trong ứng dụng thực tế, nên dùng DataSourceProperties/ConfigurationProperties khi cần binding chuẩn và quản lý default nhất quán.

Khi có DataSource bean phù hợp, điều kiện ConditionalOnMissingBean ở các nhánh mặc định khiến Boot không tạo thêm DataSource. Điều đó giúp tránh hai DataSource cạnh tranh cùng một vai trò.

## 14. Gỡ lỗi: đọc Condition Evaluation Report và dependency tree

Nếu không thấy DataSource bean, kiểm tra theo trình tự:

1. **Classpath:** có spring-jdbc không? Có embedded engine hoặc vendor driver tương ứng không? Có Hikari/Tomcat/DBCP2/UCP không?
2. **Dependency scope:** driver nằm ở runtime hoặc compile classpath, không chỉ test scope?
3. **Properties:** spring.datasource.url, driver-class-name, type và embedded-database-connection có giá trị nào?
4. **Custom beans:** ứng dụng đã có DataSource/XADataSource bean hoặc R2DBC ConnectionFactory bean chưa?
5. **Condition Evaluation Report:** chạy ứng dụng với --debug để xem DataSourceAutoConfiguration, PooledDataSourceConfiguration và EmbeddedDatabaseConfiguration khớp hay không.
6. **Lỗi khởi tạo:** nếu condition đã khớp, đọc exception về driver, URL, pool hoặc kết nối; condition match không bảo đảm database server có thể truy cập.
7. **Dependency tree:** dùng mvn dependency:tree hoặc Gradle dependencies để xem driver/pool thực tế có trong runtime graph không.

Một số condition message hữu ích:

| Condition | Ý nghĩa cần tìm |
|---|---|
| ConditionalOnClass trên DataSourceAutoConfiguration | JDBC API và EmbeddedDatabaseType có trên classpath không |
| ConditionalOnMissingBean type io.r2dbc.spi.ConnectionFactory | Có R2DBC ConnectionFactory khiến JDBC auto-config back off không |
| PooledDataSourceCondition | Có spring.datasource.type hoặc pool hỗ trợ trên classpath không |
| EmbeddedDatabaseCondition | URL có được đặt không, pooled branch có khớp không, engine nhúng có được tìm thấy không |
| ConditionalOnMissingBean DataSource/XADataSource | Ứng dụng đã tự đăng ký DataSource hoặc XADataSource chưa |

Bật --debug không biến mọi logger thành DEBUG; nó bổ sung Condition Evaluation Report để giải thích quyết định auto-configuration. Nếu dùng Actuator và đã expose endpoint, /actuator/conditions cũng giúp xem positive/negative matches.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Có H2 dependency nhưng không có DataSource | Thiếu spring-jdbc hoặc điều kiện khác không khớp | Kiểm tra starter và Condition Evaluation Report |
| Có Hikari nhưng lỗi không tìm thấy driver | Pool có nhưng vendor driver thiếu | Thêm driver JAR vào runtime |
| Đã đặt driver-class-name nhưng ClassNotFound | Tên class sai hoặc dependency không có | Kiểm tra driver artifact và class name |
| Dùng starter-jdbc + H2 nhưng mong bean EmbeddedDatabase | Hikari có mặt nên pooled branch ưu tiên | Kiểm tra bean type; HikariDataSource có thể dùng H2 in-memory |
| Đặt URL H2 nhưng embedded branch không khớp | EmbeddedDatabaseCondition bỏ qua khi URL có text | Nếu dùng pool, pooled branch xử lý URL; nếu muốn direct embedded branch thì không đặt URL và bỏ pool |
| Có H2 và HSQL cùng classpath, chọn nhầm engine | Boot phát hiện nhiều embedded database | Đặt spring.datasource.embedded-database-connection |
| Đặt embedded-database-connection=none rồi không có URL | Đã tắt embedded detection, không còn URL để kết nối | Khai báo external URL/driver hoặc tự cấu hình DataSource |
| Đặt spring.datasource.type nhưng class không có | Type không thể load | Thêm dependency hoặc sửa class name |
| Có DataSource tự tạo nhưng Boot vẫn không tạo bean mặc định | Đây là hành vi back-off dự kiến | Dùng bean tự tạo hoặc bỏ bean nếu muốn Boot quản lý |
| Có R2DBC ConnectionFactory và mong Boot tự tạo JDBC DataSource | Outer DataSourceAutoConfiguration back off | Quyết định rõ có muốn dùng cả JDBC blocking và R2DBC hay không |
| Ứng dụng test chia sẻ cùng H2 database giữa context | Database name không duy nhất | Đặt spring.datasource.generate-unique-name=true |
| DataSource bean tạo được nhưng query lỗi | Server không chạy, URL/credential sai hoặc network bị chặn | Kiểm tra kết nối thật và metadata exception |

## 16. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng có spring-boot-starter-jdbc và H2, không khai báo URL. DataSource bean thường là EmbeddedDatabase hay HikariDataSource?

**Đáp án:** HikariDataSource trong cấu hình mặc định, vì starter-jdbc kéo HikariCP vào classpath và pooled branch được ưu tiên. H2 vẫn là database engine được dùng bên dưới.

**Câu 2.** HikariCP có mặt nhưng thiếu PostgreSQL driver, Boot có thể chọn pooled branch không?

**Đáp án:** Có. Pool classpath có thể làm PooledDataSourceCondition khớp, nhưng khi xác định driver hoặc tạo kết nối PostgreSQL, ứng dụng thất bại vì thiếu driver.

**Câu 3.** Chỉ thêm org.postgresql:postgresql nhưng không có spring-jdbc và không tự tạo DataSource, Boot có đủ điều kiện cho DataSourceAutoConfiguration không?

**Đáp án:** Không. DataSourceAutoConfiguration còn cần EmbeddedDatabaseType trên classpath; lớp này đến từ Spring JDBC.

**Câu 4.** Có H2 trên classpath, không URL, không pool, không type. Nhánh nào có thể khớp?

**Đáp án:** EmbeddedDatabaseConfiguration, miễn là chưa có DataSource/XADataSource bean và engine H2 được phát hiện.

**Câu 5.** spring.datasource.url đã có giá trị nhưng không có pool và không đặt spring.datasource.type. Embedded branch có tạo database không?

**Đáp án:** Không. URL có text làm EmbeddedDatabaseCondition không khớp; pooled branch cũng không khớp nếu không có pool/type. Cần bổ sung pool/type hoặc tự cấu hình DataSource.

**Câu 6.** Thuộc tính spring.datasource.type có chọn driver không?

**Đáp án:** Không. Nó chọn DataSource implementation. Driver được xác định từ driver-class-name, JDBC URL hoặc embedded database phù hợp.

**Câu 7.** Ứng dụng đã có R2DBC ConnectionFactory bean. Vì sao không thấy JDBC DataSource auto-config?

**Đáp án:** DataSourceAutoConfiguration có ConditionalOnMissingBean với type io.r2dbc.spi.ConnectionFactory, nên mặc định back off khi bean R2DBC có mặt.

**Câu 8.** Dùng H2 trong test với nhiều application context, làm sao tránh vô tình chia sẻ database cùng tên?

**Đáp án:** Đặt spring.datasource.generate-unique-name=true để mỗi context có tên embedded database riêng.

## 17. Ghi nhớ

- **JDBC API, driver, database engine và connection pool là bốn thành phần khác nhau.**
- DataSourceAutoConfiguration cần DataSource API và Spring JDBC EmbeddedDatabaseType trên classpath, đồng thời back off khi có R2DBC ConnectionFactory.
- Pooled branch khớp khi có spring.datasource.type hoặc pool được hỗ trợ trên classpath.
- Embedded branch cần URL trống, pooled branch không khớp và engine nhúng được phát hiện.
- Với spring-boot-starter-jdbc, Hikari thường có mặt; H2 có thể được dùng làm engine nhưng DataSource bean vẫn là HikariDataSource.
- Driver thường được suy ra từ JDBC URL; driver JAR phải tồn tại ở runtime classpath.
- spring.datasource.url chọn đích database, driver-class-name chọn driver, type chọn DataSource implementation.
- Nếu condition match nhưng không kết nối được, kiểm tra driver, URL, credential, network và database server.

### Tài liệu chính thức

- Spring Boot 3.3 — SQL Databases: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot 3.3 — DataSourceAutoConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.3 — DataSourceProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot 3.3 — EmbeddedDatabaseConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.EmbeddedDatabaseConfiguration.html
- Spring Boot 3.3 — PooledDataSourceConfiguration API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.PooledDataSourceConfiguration.html
- Spring Framework — Embedded Database Support: https://docs.spring.io/spring-framework/reference/data-access/jdbc/embedded-database-support.html
