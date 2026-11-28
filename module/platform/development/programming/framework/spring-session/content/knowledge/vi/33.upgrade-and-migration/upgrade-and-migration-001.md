# Đối chiếu phiên bản Spring Session với Boot, Security, Data Redis và driver JDBC

## Mục tiêu bài học

Spring Session là một phần của hệ sinh thái Spring. Khi dùng Spring Session trong ứng dụng Spring Boot, các thành phần như Spring Framework, Spring Security, Spring Data Redis, thư viện client Redis và driver JDBC phải tương thích với nhau. Một dependency có thể biên dịch riêng lẻ nhưng vẫn gây lỗi khi chạy nếu nó kéo theo API, namespace hoặc phiên bản thư viện nền khác với phần còn lại của ứng dụng.

Cách an toàn nhất với ứng dụng Spring Boot là để Spring Boot BOM quản lý các phiên bản mà Boot đã kiểm thử cùng nhau. Khi không dùng Boot, cần chủ động phối hợp BOM của Spring Session, Spring Framework, Spring Security và Spring Data. Driver Redis hoặc JDBC lại có thêm ràng buộc với Redis server, hệ quản trị cơ sở dữ liệu, Java runtime và giao thức kết nối.

Sau bài học, bạn có thể:

- Đọc version train và hiểu vì sao số phiên bản của các dự án Spring không nhất thiết giống nhau.
- Đối chiếu Spring Boot, Spring Framework, Spring Security, Spring Session và Spring Data Redis.
- Chọn đúng module Redis hoặc JDBC cho Spring Session.
- Phân biệt Spring Session module, Boot starter, Spring Data module và driver kết nối.
- Hiểu vai trò của Spring Boot BOM, Spring Session BOM và Spring Data BOM.
- Kiểm tra phiên bản thực tế trong Maven hoặc Gradle dependency graph.
- Chọn JDBC driver theo database server, JDK và yêu cầu JDBC.
- Nhận biết xung đột do ép phiên bản, dependency bắc cầu hoặc trộn javax/jakarta.
- Lập kế hoạch nâng cấp có kiểm thử repository, schema, serialization, SecurityContext và nhiều instance.
- Xác minh cấu hình sau nâng cấp bằng integration test và kiểm tra runtime.

## 1. Vì sao phải đối chiếu cả nhóm dependency?

Spring Session không hoạt động độc lập. Nó thay thế hoặc cung cấp implementation cho session API của ứng dụng, sau đó dùng một repository để lưu trạng thái phiên.

Với Servlet và Redis, các lớp chính thường gồm:

- Spring Boot: auto-configuration, dependency management và cấu hình ứng dụng.
- Spring Framework: Servlet integration, Web MVC, transaction và các API nền.
- Spring Security: lưu và khôi phục SecurityContext, xác thực, logout và session fixation protection.
- Spring Session: SessionRepository, filter, session events và module repository cụ thể.
- Spring Data Redis: Redis operations, serialization, connection abstraction và repository support.
- Redis client: Lettuce hoặc Jedis để mở kết nối tới Redis server.
- Spring Session JDBC: JDBC repository cho HttpSession.
- JDBC driver: PostgreSQL, MySQL, SQL Server, Oracle hoặc database vendor khác.
- Connection pool và Spring JDBC: quản lý DataSource, connection và thao tác SQL.

Sơ đồ phụ thuộc khái quát:

~~~mermaid
flowchart TD
    B[Spring Boot BOM] --> F[Spring Framework]
    B --> S[Spring Security]
    B --> SS[Spring Session]
    B --> SD[Spring Data]
    B --> D[Database / Redis drivers]
    SS --> SR[Redis hoặc JDBC repository]
    SR --> SD
    SD --> RC[Lettuce hoặc Jedis]
    SR --> J[Spring JDBC / JdbcTemplate]
    J --> P[HikariCP / DataSource]
    P --> JD[PostgreSQL / MySQL / SQL Server driver]
    S --> SC[SecurityContext trong session]
    SS --> SC
~~~

Khi một module được nâng cấp, các module phụ thuộc có thể cần nâng theo. Ví dụ, Spring Session mới có thể yêu cầu API Spring Framework mới; Spring Data Redis mới có thể yêu cầu Spring Framework generation mới; Spring Security mới có thể thay đổi API cấu hình hoặc hành vi lưu SecurityContext.

Vì vậy, không chỉ hỏi "Spring Session có chạy với Java hiện tại không?". Cần kiểm tra toàn bộ dependency graph và các thành phần lưu trữ thực tế.

## 2. Phân biệt version của từng dự án Spring

Các dự án trong hệ sinh thái Spring phát hành độc lập. Số phiên bản cùng một hàng không nhất thiết bằng nhau.

Ví dụ:

- Spring Boot 3.5.x quản lý Spring Framework 6.2.x.
- Spring Security 6.5.x có thể đi cùng Spring Session 3.5.x.
- Spring Data Redis 3.5.x thuộc Spring Data generation tương ứng.
- Spring Session 3.5.x có thể có patch version khác với Spring Boot 3.5.x.

Không suy luận rằng Spring Boot 3.5.16 phải đi cùng Spring Session 3.5.16 hoặc Spring Data Redis 3.5.16. Boot BOM quyết định các bản cụ thể mà release đó quản lý.

### Các thế hệ chính cần nhận biết

| Thế hệ ứng dụng | Spring Framework | Spring Security | Spring Session | Ghi chú |
|---|---|---|---|---|
| Boot 2.x | 5.x | 5.x | 2.x | Hệ sinh thái cũ, nhiều API javax |
| Boot 3.x | 6.x | 6.x | 3.x | Java 17 baseline; chuyển sang Jakarta |
| Boot 4.x | 7.x | 7.x | 4.x | Thế hệ Framework và Security mới hơn |

Bảng này thể hiện thế hệ lớn, không phải ma trận tương thích thay cho BOM. Patch/minor version phải lấy từ release cụ thể của Spring Boot hoặc các BOM được chọn.

### Mốc nền tảng quan trọng

Spring Session 3.0 yêu cầu Java 17 và Spring Framework 6.0 làm baseline. Đây là thay đổi lớn so với thế hệ Spring Session 2.x. Spring Boot 3 cũng chuyển sang Jakarta EE namespace, nên ứng dụng nâng từ Boot 2 phải rà soát import Servlet, filter, listener và thư viện bên thứ ba.

Spring Boot 4.x thuộc thế hệ Spring Framework 7 và Spring Security 7. Không ghép Spring Session 4.x vào một ứng dụng Boot 3 chỉ vì cả hai đều có thể tải được từ Maven Central. Phải xác minh dependency baseline và API tương ứng.

## 3. Đọc một ma trận phiên bản do Spring Boot quản lý

Bảng sau là ví dụ các bản stable được liệt kê trong tài liệu managed dependency của Spring Boot tại thời điểm biên soạn 26/11/2026. Các số này cho biết Boot BOM quản lý gì ở từng release; chúng không phải quy tắc ghép phiên bản thủ công.

| Spring Boot | Spring Framework | Spring Security | Spring Data Redis | Spring Session |
|---|---:|---:|---:|---:|
| 3.4.13 | 6.2.15 | 6.4.13 | 3.4.13 | 3.4.7 |
| 3.5.16 | 6.2.19 | 6.5.11 | 3.5.13 | 3.5.7 |
| 4.0.10 | 7.0.11 | 7.0.9 | 4.0.9 | 4.0.6 |
| 4.1.3 | 7.0.11 | 7.1.3 | 4.1.3 | 4.1.2 |
| 4.2.0 | 7.1.0 | 7.2.0 | 4.2.0 | 4.2.0 |

Cách đọc:

- Hàng Boot 3.5.16 cho biết dự án Boot đó đã quản lý Spring Framework 6.2.19, Spring Security 6.5.11, Spring Data Redis 3.5.13 và Spring Session 3.5.7.
- Hàng Boot 4.0.10 dùng Spring Session 4.0.6 cùng Spring Framework 7.0.11 và Security 7.0.9.
- Spring Data Redis và Spring Session có patch version khác nhau là bình thường.
- Khi nâng Boot patch/minor, hãy đọc lại BOM mới thay vì giữ các con số của release cũ.

Một lỗi phổ biến là chỉ nâng spring-session-core nhưng để spring-session-data-redis hoặc spring-session-jdbc ở bản khác. Các module Spring Session cùng một release train nên được quản lý đồng bộ. Boot BOM hoặc Spring Session BOM giúp tránh việc này.

## 4. Spring Boot BOM là điểm bắt đầu cho dependency management

Spring Boot cung cấp dependency management thông qua:

- Parent POM spring-boot-starter-parent.
- BOM spring-boot-dependencies khi dự án không dùng Boot parent.
- Gradle plugin và dependency management hoặc Gradle platform tương ứng.

BOM ghi nhận các phiên bản đã được chọn cho một release Boot. Khi dependency được quản lý bởi BOM, thường không khai báo version riêng ở từng dependency.

### Maven dùng Spring Boot parent

Ví dụ ứng dụng Servlet dùng Spring Session Redis:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ dùng Spring Boot 3.5.16. Version của Spring Session, Spring Security, Spring Data Redis, Lettuce và Spring Framework được quản lý bởi dependency management của Boot. Không cần ghi version cho từng artifact đã được quản lý.

Với Spring Boot 4.x, Boot cung cấp starter session riêng. Ví dụ Redis:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Với JDBC:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-jdbc</artifactId>
</dependency>
~~~

Tên starter khác nhau giữa các thế hệ Boot. Không sao chép tên starter của Boot 4 vào dự án Boot 3 nếu artifact đó không tồn tại trong release tương ứng.

### Maven không dùng Boot parent

Nếu dự án cần parent POM riêng, có thể import Boot BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo dependency mà không đặt version nếu Boot BOM đã quản lý artifact đó.

### Gradle

Với Gradle, dự án Spring Boot thường dùng Boot plugin và cơ chế dependency management tương ứng. Có thể khai báo dependency mà không chỉ định version:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.session:spring-session-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Nếu dự án dùng Gradle platform trực tiếp, import BOM phù hợp với cách quản lý dependency của dự án. Tránh đồng thời áp nhiều platform hoặc constraint mâu thuẫn mà không hiểu thứ tự ưu tiên.

## 5. Spring Session module và Boot starter không phải cùng một khái niệm

Spring Session cung cấp module theo repository:

| Module | Vai trò |
|---|---|
| spring-session-core | API session và thành phần lõi |
| spring-session-data-redis | Redis-backed session repository |
| spring-session-jdbc | JDBC-backed session repository |
| spring-session-data-mongodb | MongoDB-backed session repository |
| spring-session-hazelcast | Hazelcast-backed session repository |

Spring Boot starter là gói tích hợp ở tầng Boot. Nó giúp đưa các dependency cần thiết vào classpath và kích hoạt auto-configuration.

Ví dụ:

- Boot 3.x thường dùng module spring-session-data-redis hoặc spring-session-jdbc.
- Boot 4.x cung cấp starter spring-boot-starter-session-data-redis và spring-boot-starter-session-jdbc.
- Spring Data Redis starter cung cấp hạ tầng kết nối Redis như RedisConnectionFactory và client.
- Spring JDBC starter cung cấp DataSource, connection pool và hạ tầng JDBC.

Không thêm nhiều module session repository cùng lúc nếu không có ý định chọn store rõ ràng. Nếu Redis và JDBC đều có trên classpath, cần kiểm tra cách Boot chọn repository và cấu hình StoreType theo phiên bản. Không để ứng dụng tự chọn store theo thứ tự mặc định mà nhóm triển khai không biết.

## 6. Đối chiếu Spring Security với Spring Session

Spring Session có thể lưu SecurityContext trong session. Spring Security thực hiện authentication, authorization, session fixation protection và logout; Spring Session cung cấp session repository mà Security sử dụng.

Các điểm cần đối chiếu:

- Spring Security và Spring Session thuộc các generation tương thích với Spring Framework đang dùng.
- Không trộn Spring Security 7.x với Spring Framework 6.x chỉ bằng cách ép version.
- Kiểm tra API cấu hình SecurityFilterChain, SessionManagementConfigurer và logout khi nâng major.
- Kiểm tra SecurityContext serialization/deserialization khi dùng Redis hoặc JDBC.
- Kiểm tra session fixation protection và Session ID rotation.
- Kiểm tra concurrent session control, principal index và session events nếu ứng dụng sử dụng.
- Kiểm tra logout có invalidate session trong repository và thu hồi trạng thái ở các instance khác.

### Ví dụ dependency Security

Trong ứng dụng Boot, dùng starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Không khai báo riêng spring-security-core, spring-security-web và spring-security-config với các version khác nhau nếu Boot đã quản lý chúng. Nếu cần nâng Security độc lập khỏi Boot, phải đọc ma trận tương thích chính thức và kiểm thử toàn bộ stack; đó là thay đổi có chủ đích chứ không phải cách sửa nhanh một lỗi API.

### Kiểm tra SecurityContext sau nâng cấp

Một bộ test tối thiểu:

1. Đăng nhập và xác minh cookie session được phát.
2. Gửi request tiếp theo với cookie đó.
3. Xác minh principal và authorities được khôi phục.
4. Đổi Session ID sau authentication theo policy.
5. Xác minh ID cũ không còn được chấp nhận.
6. Logout và xác minh session bị invalidate.
7. Gửi cookie cũ đến instance khác và xác minh không còn xác thực.
8. Nếu dùng concurrent session control, kiểm thử số phiên tối đa và registry.
9. Nếu dùng remember-me hoặc OAuth2 login, kiểm thử luồng tương ứng.

Không kết luận tương thích chỉ vì ứng dụng khởi động thành công. Lỗi có thể xuất hiện ở bước serialize SecurityContext, khôi phục principal hoặc logout.

## 7. Đối chiếu Spring Data Redis và Redis client

Spring Session Redis dựa trên Spring Data Redis. Spring Data Redis cung cấp API thao tác Redis và quản lý kết nối; client thực tế thường là Lettuce hoặc Jedis.

Chuỗi phụ thuộc:

~~~text
Spring Session Data Redis
        |
Spring Data Redis
        |
RedisConnectionFactory
        |
Lettuce hoặc Jedis
        |
Redis Server
~~~

Các thành phần cần kiểm tra:

- Spring Session Data Redis có cùng release train với Spring Session core.
- Spring Data Redis thuộc generation tương thích với Spring Framework.
- Redis client được Spring Data Redis hỗ trợ.
- Version client được Boot BOM quản lý hoặc được kiểm tra theo tài liệu Spring Data Redis.
- Redis server hỗ trợ command, expiration, notification và tính năng mà repository đang sử dụng.
- TLS, authentication, cluster mode và connection pool tương thích môi trường production.

### Lettuce và Jedis

Lettuce và Jedis là Redis client, không phải Spring Session repository. Nếu ứng dụng dùng Lettuce, dependency graph cần có phiên bản Lettuce phù hợp với Spring Data Redis và Java runtime. Nếu đổi sang Jedis, phải kiểm tra Spring Data Redis version hỗ trợ client đó và cấu hình connection factory tương ứng.

Không thêm Lettuce/Jedis với version tùy ý chỉ để sửa lỗi kết nối. Trước tiên xem Boot BOM đang quản lý phiên bản nào.

### Redis server cũng có ma trận riêng

Spring Data Redis và Redis server là hai phía khác nhau. Cần xác minh:

- Phiên bản Redis server được hỗ trợ.
- Command được dùng bởi Spring Session repository.
- Redis Cluster có giới hạn hoặc khác biệt gì so với standalone.
- ACL user có đủ quyền trên key prefix và channel cần thiết.
- Keyspace notifications có được bật nếu ứng dụng cần session events.
- Redis persistence, replication và failover có phù hợp yêu cầu session durability.

Driver Redis mới không tự làm Redis server cũ hỗ trợ command mới. Ngược lại, Redis server mới cũng không bảo đảm client cũ hiểu mọi behavior mới.

## 8. JDBC driver là một trục tương thích riêng

Spring Session JDBC sử dụng Spring JDBC/JdbcOperations và một DataSource. JDBC driver do database vendor cung cấp. Driver phải tương thích với database server, Java runtime, JDBC API, TLS và các tính năng mà ứng dụng sử dụng.

Không có quy tắc rằng Spring Session 3.5 phải dùng PostgreSQL driver 3.5 hoặc MySQL driver 3.5. Driver version theo hệ quản trị cơ sở dữ liệu và vendor, không theo version number của Spring Session.

### Các lớp cần đối chiếu

| Thành phần | Cần xác minh |
|---|---|
| Spring Session JDBC | API repository, SQL query và schema |
| Spring Framework / Spring JDBC | JdbcOperations, transaction và DataSource integration |
| Spring Boot JDBC | Auto-configuration và dependency management |
| Connection pool | Java baseline, driver integration, timeout và validation |
| JDBC driver | JDK, JDBC specification, database server version và TLS |
| Database server | SQL dialect, BLOB/BINARY type, index, transaction và isolation |
| Schema Spring Session | Tên bảng, cột, index, khóa ngoại và script theo vendor |

### Ví dụ driver được Boot BOM quản lý

Các bảng managed dependency của Boot có thể chứa driver như:

- PostgreSQL JDBC driver: artifact org.postgresql:postgresql.
- MySQL Connector/J: artifact com.mysql:mysql-connector-j.
- Microsoft SQL Server JDBC: artifact com.microsoft.sqlserver:mssql-jdbc.
- Oracle JDBC: artifact com.oracle.database.jdbc:ojdbc11 hoặc artifact phù hợp JDK.
- H2: thường dùng cho test hoặc môi trường phát triển.

Ví dụ trong BOM Boot 3.5.16, PostgreSQL driver được quản lý ở bản 42.7.11 và MySQL Connector/J ở bản 9.7.0. Trong BOM Boot 4.2.0, các mục tương ứng được quản lý ở bản 42.7.14 và 26.10.0. Đây là phiên bản mà BOM cụ thể quản lý tại thời điểm tra cứu, không phải khuyến nghị nâng driver độc lập cho mọi database server.

Trước khi chọn driver, kiểm tra ma trận hỗ trợ của vendor cho:

- Phiên bản Java đang chạy.
- Phiên bản database server.
- JDBC API level.
- TLS protocol và certificate.
- Authentication plugin.
- Failover, connection timeout và pooling behavior.

Không dùng một driver chỉ vì nó biên dịch được. Một driver không tương thích server có thể chỉ lỗi khi tạo connection, chạy query đặc biệt hoặc xử lý transaction.

## 9. Chọn module JDBC và driver đúng cách

Với Servlet và JDBC, cấu trúc dependency thường gồm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ này dùng PostgreSQL và giả định Boot BOM quản lý cả Spring Session, Spring JDBC, pool và PostgreSQL driver. Với Boot 4.x, có thể dùng starter session JDBC tương ứng thay cho khai báo module trực tiếp.

Không thêm R2DBC driver vào cấu hình JDBC chỉ vì dự án có WebFlux ở một phần khác. JDBC driver và R2DBC driver triển khai hai API kết nối khác nhau.

### Schema phải đúng database vendor

Spring Session JDBC cung cấp SQL schema script theo database vendor. Không dùng script PostgreSQL cho MySQL hoặc SQL Server chỉ vì các cột trông tương tự.

Kiểm tra:

- Script schema đi cùng đúng Spring Session version.
- Kiểu dữ liệu BLOB/BINARY hoặc kiểu lưu attribute phù hợp.
- Index trên SESSION_ID, EXPIRY_TIME và PRINCIPAL_NAME theo schema tương ứng.
- Tên bảng và schema/database đã cấu hình.
- Quyền runtime có thể SELECT/INSERT/UPDATE/DELETE.
- Migration tool không vô tình chạy lại script khởi tạo trên dữ liệu đang tồn tại.

Nếu nâng Spring Session hoặc đổi database vendor, so sánh schema hiện tại với script mới. Không giả định driver mới tự cập nhật schema.

## 10. Dùng Spring Session BOM khi không dùng Spring Boot

Một ứng dụng Spring Framework thuần vẫn có thể dùng Spring Session, nhưng phải quản lý phiên bản nhiều module một cách rõ ràng.

Spring Session cung cấp Maven BOM để quản lý các module cùng release. Spring Data có Spring Data BOM để phối hợp các module như Spring Data Redis. Spring Security có BOM riêng; Spring Framework cũng có dependency management riêng.

Nguyên tắc:

1. Chọn generation Spring Framework phù hợp.
2. Chọn Spring Session generation tương thích với Framework đó.
3. Chọn Spring Security generation phù hợp nếu lưu SecurityContext.
4. Chọn Spring Data release train tương thích với Framework và Spring Data Redis cần dùng.
5. Chọn Redis client hoặc JDBC driver theo hệ thống thực tế.
6. Đọc release notes và migration guide của từng major.
7. Chạy integration test với dependency graph cuối cùng.

Không import một BOM chỉ vì version number lớn nhất. BOM phải cùng generation với các module trong ứng dụng.

### Vì sao không nên tự ghép các BOM tùy tiện?

Một dự án có thể import Spring Framework BOM, Spring Security BOM, Spring Session BOM và Spring Data BOM. Nếu các BOM thuộc những generation không tương thích, Maven có thể vẫn resolve được dependency nhưng runtime gặp NoSuchMethodError, ClassNotFoundException hoặc lỗi auto-configuration.

Hãy chọn các BOM có phiên bản được tài liệu dự án xác nhận tương thích. Nếu phải override một dependency, ghi rõ lý do, kiểm tra dependency tree và thêm test tương ứng.

## 11. Tránh ép version thủ công

Một dependency có thể được khai báo rõ version dù Boot BOM đã quản lý. Khi đó, phiên bản khai báo tại dependency hoặc dependencyManagement của dự án có thể ghi đè giá trị Boot đã chọn.

Ví dụ rủi ro:

~~~xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
    <version>4.2.0</version>
</dependency>
~~~

Nếu dự án vẫn dùng Boot 3.5.x, việc ép Spring Session 4.2.0 có thể kéo API yêu cầu Spring Framework 7 trong khi ứng dụng đang chạy Framework 6.2. Dependency resolution thành công không chứng minh stack tương thích.

Tương tự, ép spring-data-redis 4.x trong ứng dụng Framework 6.x có thể gây lỗi binary compatibility.

Chỉ override khi:

- Có hướng dẫn chính thức cho cặp phiên bản đó.
- Có yêu cầu security fix hoặc bug fix cụ thể.
- Các dependency liên quan đã được kiểm tra.
- Có integration test chứng minh repository hoạt động.
- Có kế hoạch quay lại BOM nếu phát sinh lỗi.

Không dùng force resolution hoặc exclusion hàng loạt để che giấu xung đột chưa được hiểu.

## 12. Những thay đổi lớn khi nâng từ Boot 2 lên Boot 3

Nâng từ Spring Boot 2.x lên 3.x là thay đổi nền tảng, không chỉ là nâng Spring Session 2.x lên 3.x.

Các điểm phải rà soát:

- Java 17 trở lên.
- Spring Framework 6.
- Spring Security 6.
- Spring Session 3.
- Jakarta EE namespace thay cho nhiều API javax.
- Servlet imports, listener, filter và container compatibility.
- Các thư viện bên thứ ba còn dùng javax.servlet.
- Serialization của session attributes.
- SecurityContext serialization và principal classes.
- JDBC schema và database driver.
- Redis client, serializer và key namespace.
- Configuration properties đã đổi hoặc bị loại bỏ.

Ví dụ import Servlet:

~~~java
import jakarta.servlet.http.HttpSession;
import jakarta.servlet.http.HttpServletRequest;
~~~

Ứng dụng còn import javax.servlet trong code hoặc thư viện tích hợp có thể không tương thích với container Jakarta của Boot 3.

Không giải quyết bằng cách trộn cả javax.servlet-api và jakarta.servlet-api vào một application classpath rồi hy vọng container tự chọn đúng. Hãy nâng các thành phần theo cùng nền tảng.

## 13. Những thay đổi khi nâng từ Boot 3 lên Boot 4

Boot 4 thuộc generation Spring Framework 7, Spring Security 7 và Spring Session 4. Ngoài thay đổi version, cách tổ chức starter và module của Boot có thể thay đổi.

Các việc cần kiểm tra:

- Java baseline và build tool theo system requirements của Boot 4.
- Spring Framework 7 và API đã bị deprecated/removed.
- Spring Security 7 migration guide.
- Spring Session 4 migration notes.
- Tên starter và auto-configuration của Boot 4.
- Spring Data Redis 4.x và Redis client tương ứng.
- JDBC driver hỗ trợ Java/database server.
- Test framework, Testcontainers và plugin build.
- Cấu hình security, session cookie và session timeout.
- Native image hoặc AOT nếu ứng dụng dùng.

Ví dụ, Boot 4 cung cấp starter session theo tên spring-boot-starter-session-data-redis và spring-boot-starter-session-jdbc. Ứng dụng Boot 3 thường khai báo module Spring Session trực tiếp. Hãy dùng dependency coordinate đúng với release Boot đang chạy.

Không lấy cấu hình từ một tài liệu Boot 4 rồi áp nguyên vào dự án Boot 3 mà không kiểm tra artifact và property metadata.

## 14. Kiểm tra dependency graph bằng Maven

Dependency graph là bằng chứng thực tế về version được resolve, thay vì chỉ nhìn file pom.xml.

### Xem dependency tree

~~~bash
mvn dependency:tree
~~~

Lọc các nhóm quan trọng:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.session,org.springframework.security,org.springframework.data,org.springframework,io.lettuce,redis.clients,org.postgresql,com.mysql
~~~

Tìm:

- Có nhiều version spring-session-core hay không.
- spring-session-data-redis và spring-session-core có cùng release hay không.
- Spring Data Redis thuộc generation phù hợp hay không.
- Spring Framework có bị kéo đồng thời nhiều minor generation không.
- Spring Security có cùng version train do Boot BOM quản lý không.
- Lettuce/Jedis có version bị override không.
- JDBC driver có đúng vendor và chỉ xuất hiện một version không.

### Xem effective POM

~~~bash
mvn help:effective-pom
~~~

Effective POM cho thấy dependencyManagement cuối cùng sau khi parent, BOM và override được áp dụng. Đây là nơi cần kiểm tra khi một version khác với giá trị kỳ vọng.

### Tìm dependency bị kéo bắc cầu

Nếu một thư viện bên thứ ba kéo một phiên bản Spring Session hoặc Spring Data cũ, dependency tree sẽ cho biết đường đi. Chỉ loại trừ dependency sau khi hiểu thư viện đó cần API nào và có thay thế phù hợp hay không.

Không exclude spring-session-core hoặc spring-data-redis chỉ để giảm số dòng dependency; module repository có thể phụ thuộc trực tiếp vào chúng.

## 15. Kiểm tra dependency graph bằng Gradle

Với Gradle, dùng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra một dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-session-core --configuration runtimeClasspath
~~~

Có thể kiểm tra riêng:

- spring-session-data-redis
- spring-session-jdbc
- spring-security-core
- spring-data-redis
- spring-framework
- lettuce-core hoặc jedis
- PostgreSQL/MySQL JDBC driver

Gradle có quy tắc chọn version dựa trên constraints, platforms, resolution strategy và dependency metadata. Nếu kết quả không giống Boot BOM, kiểm tra các platform đã import và constraint do plugin khác thêm vào.

Không dùng resolutionStrategy.force cho toàn bộ nhóm org.springframework nếu chưa biết vì sao các version khác nhau. Force có thể làm dependency graph trông đồng nhất nhưng API runtime không tương thích.

## 16. Kiểm tra driver và database sau khi nâng cấp

Đối với JDBC, dependency tree chỉ cho biết driver được resolve; nó không chứng minh driver tương thích với database server.

Một quy trình kiểm tra:

1. Ghi nhận Java runtime production.
2. Ghi nhận database vendor và server version.
3. Đọc driver compatibility matrix của vendor.
4. Kiểm tra driver version do Boot BOM quản lý.
5. Xác minh TLS và authentication plugin.
6. Kết nối bằng đúng driver trong môi trường test.
7. Chạy schema migration.
8. Tạo, đọc, cập nhật, expire và xóa session.
9. Chạy nhiều request và nhiều instance.
10. Kiểm tra connection pool, timeout và failover.

### Phân biệt lỗi driver với lỗi schema

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| No suitable driver | Thiếu driver hoặc JDBC URL sai |
| UnsupportedClassVersionError | Driver/library yêu cầu Java mới hơn runtime |
| Connection refused | Endpoint, port hoặc network |
| Authentication plugin error | Driver không hỗ trợ cơ chế xác thực server |
| SQL syntax error | Schema script/query không phù hợp database vendor/version |
| Table not found | Migration chưa chạy hoặc schema/search path sai |
| Column/type error | Schema cũ không tương thích repository mới |
| TLS handshake failure | Driver, truststore, certificate hoặc TLS policy |
| Connection pool timeout | Pool size, connection leak hoặc database quá tải |

Không đổi Spring Session version để sửa lỗi JDBC driver nếu nguyên nhân là driver hoặc database configuration.

## 17. Kiểm tra Redis client và Redis server sau nâng cấp

Đối với Redis, cần phân biệt:

- Spring Session Redis repository.
- Spring Data Redis.
- Lettuce hoặc Jedis.
- Redis server hoặc Redis-compatible service.

Quy trình kiểm tra:

1. Xác định Redis client đang được resolve.
2. Kiểm tra version client có trong Boot BOM.
3. Xác minh Redis server version và mode standalone/cluster.
4. Kiểm tra TLS và authentication.
5. Kiểm tra ACL command/key/channel.
6. Kiểm tra namespace của session.
7. Kiểm tra serializer tương thích dữ liệu hiện có.
8. Tạo, đọc, cập nhật và xóa session.
9. Kiểm tra TTL và expiration.
10. Kiểm tra session event nếu ứng dụng sử dụng.
11. Kiểm tra failover và nhiều instance.

### Kiểm tra serializer là phần bắt buộc

Một dependency graph có thể hoàn toàn đúng nhưng session cũ vẫn không deserialize được sau khi nâng cấp.

Rà soát:

- JDK serialization có class name/serialVersionUID thay đổi không.
- Jackson serializer có thay đổi type metadata không.
- SecurityContext hoặc Authentication class có đổi package/API không.
- Session attribute có object do thư viện bên thứ ba cung cấp không.
- Các instance cũ và mới có thể đọc dữ liệu của nhau trong rolling deployment không.

Không xóa toàn bộ session production để xử lý serialization error trước khi đánh giá tác động đăng xuất diện rộng. Nếu cần migration hoặc invalidation, hãy lên kế hoạch theo mức độ ảnh hưởng người dùng.

## 18. Kiểm tra cấu hình auto-configuration và repository

Spring Boot có thể auto-configure Spring Session khi module repository nằm trên classpath. Khi nhiều implementation cùng xuất hiện, lựa chọn store có thể phụ thuộc cấu hình và thứ tự ưu tiên của release Boot.

Kiểm tra:

- Đang dùng Servlet hay WebFlux.
- Store được chọn là Redis hay JDBC.
- Có annotation @EnableRedisHttpSession hoặc @EnableJdbcHttpSession tự khai báo không.
- Có bean SessionRepository hoặc SessionRepositoryFilter custom không.
- Có nhiều cấu hình session cùng bật không.
- Có cấu hình cookie resolver, namespace, timeout và flush mode không.
- Có nhiều DataSource hoặc RedisConnectionFactory không.

Nếu dùng annotation để tự cấu hình, auto-configuration của Boot có thể back off. Không vừa dựa vào auto-configuration vừa đăng ký một repository khác mà không kiểm tra bean thực tế.

### Kiểm tra runtime

Có thể bật condition evaluation report hoặc Actuator conditions trong môi trường phù hợp để xem auto-configuration nào đã match. Không expose endpoint chẩn đoán nội bộ ra Internet.

Kiểm tra bean thực tế và log khởi động để xác nhận repository, filter và connection factory đúng với store mong muốn.

## 19. Nâng cấp an toàn khi nhiều instance cùng dùng một kho session

Trong rolling deployment, node cũ và node mới có thể cùng truy cập Redis hoặc bảng JDBC. Hai phiên bản ứng dụng cần hiểu cùng một cấu trúc dữ liệu trong giai đoạn chuyển tiếp.

Các rủi ro:

- Node mới ghi session attribute mà node cũ không deserialize được.
- Serializer thay đổi giữa hai phiên bản.
- Spring Session mới thay đổi cách cập nhật key hoặc expiration metadata.
- JDBC schema được thay đổi trong khi node cũ còn chạy.
- Spring Security thay đổi serialization của SecurityContext.
- Một node dùng namespace hoặc cookie name khác với node còn lại.

### Quy trình expand-contract

1. Đọc migration guide của Boot, Security, Session và Data.
2. Xác định thay đổi schema, serializer và cấu trúc lưu trữ.
3. Nếu cần schema mới, thêm cấu trúc tương thích ngược trước.
4. Triển khai code có thể đọc dữ liệu cũ và mới trong giai đoạn chuyển tiếp.
5. Chạy canary trên một nhóm instance.
6. Kiểm tra login, request tiếp theo, logout và session expiration.
7. Nâng các instance còn lại.
8. Chỉ xóa cấu trúc cũ sau khi không còn node dùng version cũ.
9. Có kế hoạch rollback nếu session mới không thể đọc bởi ứng dụng cũ.

Không thực hiện migration schema phá hủy khi còn instance cũ đang chạy. Với Redis, không đổi namespace hoặc serializer đột ngột nếu chưa có chiến lược chuyển dữ liệu hoặc buộc người dùng đăng nhập lại.

### Kiểm tra session giữa hai version

Một test hữu ích:

1. Version A tạo session và lưu các thuộc tính đại diện.
2. Version B tải session đó.
3. Version B cập nhật thuộc tính.
4. Version A tải lại session nếu rolling deployment cho phép.
5. Xác minh dữ liệu được đọc đúng theo compatibility policy.
6. Lặp lại với SecurityContext và logout.

Nếu không thể duy trì tương thích dữ liệu giữa hai version, cần chọn một chiến lược rollout có kiểm soát như drain toàn bộ node cũ hoặc chấp nhận invalidation session với thông báo người dùng.

## 20. Kế hoạch nâng cấp theo từng lớp

Không nâng mọi dependency cùng lúc mà không biết thay đổi nào gây lỗi.

Một kế hoạch có thể chia thành:

| Giai đoạn | Việc thực hiện | Bằng chứng cần có |
|---|---|---|
| 1. Baseline | Ghi nhận Java, Boot, Framework, Security, Session, Data Redis, client và JDBC driver | Dependency tree hiện tại |
| 2. Tương thích | Đọc BOM, system requirements và migration guides | Danh sách version mục tiêu |
| 3. Build | Cập nhật Boot/BOM và module đúng generation | Build resolve thành công |
| 4. Storage | Kiểm tra Redis/JDBC, serializer, schema và driver | Integration test repository |
| 5. Security | Kiểm tra SecurityContext, login, fixation, logout và concurrent sessions | Security integration tests |
| 6. Cluster | Kiểm tra nhiều instance và dữ liệu chia sẻ | Multi-node tests |
| 7. Canary | Triển khai một phần workload và quan sát | Metrics, logs và session success rate |
| 8. Rollout | Nâng toàn bộ node và dọn cấu hình cũ | Health và smoke tests |
| 9. Closeout | Gỡ workaround, version override và migration tạm | Dependency graph sạch |

Nếu nâng major Boot, đọc migration guide của Boot trước. Nếu nâng Spring Security hoặc Spring Session độc lập, đọc migration guide của chính dự án đó và xác minh compatibility với Boot BOM.

## 21. Các lỗi thường gặp khi đối chiếu phiên bản

**Cho rằng mọi module Spring phải có cùng version number.**  
Không. Spring Framework, Spring Security, Spring Data và Spring Session phát hành theo release train riêng. Dùng BOM để lấy phiên bản tương thích.

**Chỉ nâng spring-session-core.**  
Module Redis/JDBC có thể còn ở bản cũ. Giữ các module Spring Session cùng release train.

**Dùng Spring Session 4.x với Boot 3.x mà không kiểm tra baseline.**  
Boot 3 dùng Spring Framework 6 generation; Spring Session 4 thuộc generation Framework 7. Hãy chọn cặp version được quản lý và hỗ trợ.

**Ép Spring Data Redis mới để lấy tính năng mới.**  
Có thể kéo yêu cầu Spring Framework mới hơn. Kiểm tra Spring Data release train và Boot BOM.

**Nghĩ Spring Security là dependency của mọi Spring Session application.**  
Spring Session có thể dùng mà không có Spring Security. Nếu lưu SecurityContext, phải căn chỉnh Security và kiểm thử integration.

**Coi JDBC driver là một module Spring.**  
Driver là thư viện vendor. Nó phải tương thích database server, JDK, JDBC API và TLS.

**Dùng R2DBC driver cho Spring Session JDBC.**  
JDBC repository dùng JDBC DataSource và driver JDBC. R2DBC driver là API khác.

**Chỉ chạy compile/test unit sau nâng cấp.**  
Không phát hiện lỗi Redis serialization, JDBC schema, SecurityContext hoặc session giữa các instance. Cần integration test với repository thật.

**Không kiểm tra dependency bắc cầu.**  
Một starter khác có thể kéo Spring Data hoặc Spring Security khác với BOM mong muốn. Dùng dependency tree.

**Đổi schema trong lúc node cũ còn chạy.**  
Node cũ có thể không đọc được schema mới. Dùng migration tương thích ngược và rollout theo giai đoạn.

**Dùng tài liệu snapshot hoặc milestone làm version production.**  
Chọn release stable, trừ khi có lý do thử nghiệm và quy trình kiểm soát rõ ràng.

## 22. Checklist đối chiếu trước khi merge

### Nền tảng Spring

- Boot version và Java version được hỗ trợ.
- Spring Framework thuộc generation tương thích.
- Spring Security thuộc release train phù hợp.
- Spring Session core và repository module cùng release train.
- Spring Data Redis tương thích với Framework và Boot.
- Không có version override không được giải thích.

### Redis

- Module/session starter đúng với Boot generation.
- Lettuce/Jedis được quản lý và hỗ trợ.
- Redis server version và topology được kiểm tra.
- Namespace và serializer tương thích dữ liệu đang tồn tại.
- ACL, TLS, timeout và expiration được kiểm thử.
- Nhiều instance đọc/ghi cùng session thành công.

### JDBC

- Spring Session JDBC đúng release train.
- Spring JDBC và DataSource được cấu hình đúng.
- Driver đúng vendor, server, JDK và JDBC level.
- Schema script đúng database vendor.
- Migration đã được review và có rollback plan.
- Connection pool, transaction và cleanup được kiểm thử.

### Security và runtime

- SecurityContext được lưu và khôi phục.
- Session fixation protection hoạt động.
- Logout invalidate session.
- Session timeout và expiration đúng.
- Cookie/session ID không thay đổi ngoài ý muốn.
- Không còn lỗi serialization.
- Test hai instance và rolling deployment đạt.
- Dependency graph không có nhiều generation Spring xung đột.

## 23. Tự kiểm tra

1. Vì sao version Spring Session không nhất thiết bằng version Spring Boot?
2. Spring Boot BOM quản lý những gì?
3. Spring Session BOM và Spring Data BOM có vai trò khác nhau ra sao?
4. Spring Session 3.x và 4.x gắn với thế hệ Spring Framework nào?
5. Vì sao không nên dùng Spring Session 4.x trong Boot 3 nếu chưa xác minh compatibility?
6. Spring Session module khác Boot starter như thế nào?
7. Khi dùng Redis, cần đối chiếu những dependency nào ngoài Spring Session?
8. Lettuce và Jedis đóng vai trò gì?
9. Redis server compatibility khác Redis client compatibility ra sao?
10. JDBC driver có phải dependency cùng version train với Spring Session không?
11. Vì sao phải kiểm tra database server version và JDK khi chọn JDBC driver?
12. Spring Session JDBC cần những thành phần nào để chạy?
13. Vì sao schema script phải đúng database vendor?
14. Maven dependency:tree giúp phát hiện vấn đề gì?
15. Gradle dependencyInsight dùng để làm gì?
16. Vì sao ép version thủ công có thể tạo NoSuchMethodError?
17. Điều gì cần kiểm tra khi nâng Boot 2 lên Boot 3?
18. Vì sao phải kiểm thử SecurityContext sau nâng cấp?
19. Rolling deployment có thể gây lỗi session theo những cách nào?
20. Khi nào nên dùng expand-contract thay vì thay schema trực tiếp?

### Gợi ý trả lời

1. Các dự án Spring phát hành độc lập, mỗi dự án có số version và patch cadence riêng.
2. Các phiên bản dependency được Boot chọn và kiểm thử cùng release, gồm Framework, Security, Session, Data, driver và nhiều thư viện khác.
3. Spring Session BOM quản lý các module Session; Spring Data BOM quản lý các module Data như Redis/JDBC.
4. Spring Session 3.x đi với Framework 6.x; Spring Session 4.x thuộc generation Framework 7.x.
5. Vì Boot 3 dựa trên Framework 6, trong khi Session 4 thuộc generation Framework 7; dependency có thể resolve nhưng không tương thích runtime.
6. Module chứa implementation/session repository; Boot starter tích hợp module đó với auto-configuration và dependency cần thiết.
7. Spring Data Redis, Redis client, Redis server, Boot BOM và serializer.
8. Chúng là client library để ứng dụng kết nối Redis thông qua Spring Data Redis.
9. Client cần tương thích API/command; server phải hỗ trợ command, protocol và feature mà repository sử dụng.
10. Không. Driver theo vendor database, JDK, JDBC API và server compatibility.
11. Driver có thể yêu cầu JDK mới, authentication/TLS mới hoặc không hỗ trợ server version cũ.
12. Spring Session JDBC, Spring JDBC/JdbcTemplate, DataSource/connection pool và JDBC driver.
13. Kiểu dữ liệu, binary column, index và SQL dialect khác nhau giữa database vendor.
14. Version thực tế, dependency bắc cầu, xung đột và đường dẫn dependency kéo vào thư viện.
15. Xem vì sao một version cụ thể được chọn trong Gradle graph và constraint nào tác động.
16. API giữa các generation có thể khác; code biên dịch hoặc chạy với class cũ nhưng method mới không tồn tại.
17. Java 17, Framework 6, Security 6, Session 3, Jakarta namespace, Servlet imports, schema và serialization.
18. Authentication có thể thành công nhưng context không được serialize hoặc khôi phục ở request tiếp theo.
19. Serializer khác nhau, schema thay đổi, SecurityContext incompatibility, namespace hoặc TTL khác nhau.
20. Khi node cũ và mới cùng truy cập kho session, cần duy trì schema tương thích trong giai đoạn chuyển tiếp.

## Kết luận

Đối chiếu phiên bản Spring Session phải nhìn toàn bộ dependency stack. Spring Boot BOM là điểm bắt đầu tốt nhất cho ứng dụng Boot vì nó quản lý Spring Framework, Spring Security, Spring Session, Spring Data Redis và nhiều driver theo release cụ thể. Khi không dùng Boot, cần phối hợp Spring Session BOM, Spring Data BOM, Spring Framework và Spring Security theo generation tương thích.

Spring Session 3.x thuộc thế hệ Spring Framework 6 và Spring Security 6; Spring Session 4.x thuộc thế hệ Framework 7 và Security 7. Spring Data Redis và Spring Session có thể có patch version khác nhau dù cùng một Boot BOM. Redis client cần tương thích Spring Data Redis và Redis server; JDBC driver phải tương thích database vendor, server version, Java runtime và JDBC API, không cần có cùng version number với Spring Session.

Sau khi thay dependency, hãy đọc dependency tree, kiểm tra schema và serializer, rồi chạy integration test bằng Redis/JDBC thật. Với hệ thống nhiều instance, kiểm thử SecurityContext, login, logout, expiration và rolling deployment trước khi rollout. Dependency graph resolve thành công chỉ chứng minh các artifact tải được; kiểm thử runtime mới chứng minh phiên bản thực sự phối hợp đúng.

## Tài liệu chính thức để tra cứu

- [Spring Boot managed dependency coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.0 managed dependency coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1 managed dependency coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot Spring Session configuration](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Data Redis dependency management](https://docs.spring.io/spring-data/redis/reference/data-commons/dependencies.html)
- [Spring Session upgrading guide](https://docs.spring.io/spring-session/reference/upgrading.html)
- [Spring Session modules and BOM](https://docs.spring.io/spring-session/reference/)
- [Spring Security migration guides](https://docs.spring.io/spring-security/reference/migration/index.html)
- [Spring Boot SQL database support](https://docs.spring.io/spring-boot/reference/data/sql.html)

