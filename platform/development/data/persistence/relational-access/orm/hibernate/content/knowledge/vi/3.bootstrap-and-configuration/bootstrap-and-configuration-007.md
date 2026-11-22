# Kết nối qua DataSource và bộ kết nối dùng chung

Khi ứng dụng Java dùng Hibernate/JPA để lưu dữ liệu vào cơ sở dữ liệu quan hệ, cấu hình kết nối là một phần quan trọng của bước **khởi tạo và cấu hình**. Một hệ thống phục vụ nhiều yêu cầu đồng thời thường không nên tạo một kết nối TCP/JDBC hoàn toàn mới cho mọi truy vấn. Cách phổ biến là cấu hình `DataSource` và **connection pool** (bộ kết nối dùng chung) để các thao tác mượn rồi trả lại kết nối.

Bài này giải thích `DataSource` là gì, pool hoạt động như thế nào, cách tích hợp với Hibernate, Spring Boot hoặc application server, cách chọn thông số và những vấn đề transaction, tài nguyên, hiệu năng thường gặp.

## 1. Từ JDBC Connection đến DataSource

### 1.1. Kết nối JDBC có chi phí

Với JDBC trực tiếp, ứng dụng có thể mở một kết nối mới như sau:

~~~java
try (Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/shop",
        dbUsername,
        dbPassword)) {

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT name FROM products WHERE id = ?")) {
        ps.setLong(1, productId);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                System.out.println(rs.getString("name"));
            }
        }
    }
}
~~~

`DriverManager.getConnection(...)` thường yêu cầu thiết lập kết nối mới qua driver: mở kết nối mạng, xác thực với database và thiết lập session phía server. Khi lặp lại nhiều lần, chi phí này có thể đáng kể. Database cũng phải quản lý tài nguyên cho từng kết nối đang mở.

Đoạn ví dụ phù hợp với một chương trình rất nhỏ, nhưng với ứng dụng có nhiều request, thường cần **tái sử dụng kết nối vật lý**.

### 1.2. DataSource là giao diện lấy kết nối

`javax.sql.DataSource` là giao diện chuẩn trong Java, cung cấp phương thức:

~~~java
Connection connection = dataSource.getConnection();
~~~

**DataSource không đồng nghĩa với pool.** Một implementation của `DataSource` có thể tạo kết nối mới mỗi lần, hoặc có thể quản lý pool để tái sử dụng connection. Cơ chế tùy vào thư viện/container đứng sau nó.

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `DriverManager` | Lấy kết nối JDBC theo URL và thông tin đăng nhập | `DriverManager.getConnection(...)` |
| `DataSource` | Giao diện cung cấp `Connection` | `javax.sql.DataSource` |
| JDBC driver | Giao tiếp với từng loại database | PostgreSQL JDBC Driver, MySQL Connector/J |
| Connection pool | Giữ và phân phối connection có thể tái sử dụng | HikariCP hoặc pool do application server quản lý |
| Hibernate | Dùng JDBC connection để thực thi SQL do ORM sinh ra hoặc native SQL | Hibernate `SessionFactory` và `Session` |

Lưu ý: JDBC `Connection` là phiên làm việc với database; Hibernate `Session` hoặc JPA `EntityManager` là ngữ cảnh ORM quản lý trạng thái entity. Hai đối tượng này có nhiệm vụ và vòng đời khác nhau.

## 2. Connection pool hoạt động như thế nào?

Khi ứng dụng khởi tạo pool, pool tạo hoặc chuẩn bị connection theo cấu hình. Khi có yêu cầu:

1. Service hoặc Hibernate yêu cầu `Connection` từ `DataSource`.
2. Pool cho mượn connection đang rảnh. Nếu chưa đủ, pool có thể tạo thêm connection đến giới hạn được cấu hình.
3. Hibernate hoặc code JDBC gửi SQL, đọc kết quả và hoàn tất transaction.
4. Khi kết thúc, gọi `connection.close()` trên connection do pool cấp thường là **trả connection về pool**.
5. Pool kiểm tra, tái sử dụng hoặc loại bỏ các connection không còn dùng được theo chính sách của nó.

~~~mermaid
flowchart LR
    A["Request A"] --> H["Hibernate / JDBC"]
    B["Request B"] --> H
    H --> D["DataSource"]
    D --> P["Connection pool"]
    P --> C1["Connection 1"]
    P --> C2["Connection 2"]
    P --> C3["Connection ..."]
    C1 --> DB[("Database")]
    C2 --> DB
    C3 --> DB
~~~

Giả sử pool cho phép tối đa 10 connection và 100 request đến cùng lúc: không có nghĩa database mở 100 connection. Những tác vụ chưa mượn được connection sẽ chờ đến khi có connection rảnh hoặc hết thời gian chờ.

### 2.1. Kết nối logic và kết nối vật lý

Với HikariCP, `dataSource.getConnection()` thường trả về một wrapper/proxy đại diện cho connection vật lý. Vì thế:

- `close()` trên connection được mượn thường trả connection về pool, thay vì ngắt socket vật lý ngay.
- Không nên giữ connection được mượn trong biến toàn cục để sử dụng qua nhiều request.
- Không chia sẻ cùng một `Connection` cho nhiều thread đồng thời; connection mang trạng thái transaction và driver thường không bảo đảm cách dùng đó an toàn.
- DataSource của một pool được thiết kế cho nhiều thread cùng yêu cầu connection; nên khởi tạo một lần ở cấp ứng dụng, thay vì một lần cho mỗi request.

### 2.2. Pool cải thiện điều gì?

Pool chủ yếu giúp giảm chi phí tạo/hủy kết nối và giới hạn số kết nối đồng thời tới database. Pool **không tự tối ưu SQL**: câu `SELECT` thiếu index vẫn chậm, transaction giữ lock lâu vẫn gây chặn, và pool quá lớn có thể làm database quá tải.

## 3. Tạo DataSource với HikariCP trong Java thuần

`HikariCP` là implementation pool phổ biến. Với PostgreSQL, runtime cần thư viện HikariCP và PostgreSQL JDBC driver. Trong dự án Spring Boot Data JPA, HikariCP thường đã được đưa vào qua dependency và do Spring tự cấu hình.

### 3.1. Cấu hình HikariDataSource

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {

    private DataSourceFactory() {}

    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(requireEnv("APP_DB_URL"));
        config.setUsername(requireEnv("APP_DB_USERNAME"));
        config.setPassword(requireEnv("APP_DB_PASSWORD"));

        config.setPoolName("shop-db-pool");
        config.setMaximumPoolSize(10);
        config.setConnectionTimeout(30_000);
        config.setMaxLifetime(1_700_000);

        return new HikariDataSource(config);
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

Ví dụ các biến môi trường cho môi trường phát triển:

~~~text
APP_DB_URL=jdbc:postgresql://localhost:5432/shop
APP_DB_USERNAME=shop_app
APP_DB_PASSWORD=<mat-khau-duoc-quan-ly-an-toan>
~~~

Đây là cấu hình minh họa. Trong thực tế, credentials nên được cấp qua cơ chế quản lý secret của môi trường triển khai, không ghi mật khẩu thật vào mã nguồn hoặc log. Với database ngoài mạng tin cậy, cấu hình TLS theo yêu cầu hạ tầng và JDBC driver.

### 3.2. Mượn và trả connection đúng cách

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductReader {
    private final DataSource dataSource;

    public ProductReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long id) throws SQLException {
        String sql = "SELECT name FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("name") : null;
            }
        }
    }
}
~~~

`try-with-resources` bảo đảm `ResultSet`, `PreparedStatement` và `Connection` được đóng khi bình thường lẫn khi có exception. Nếu `DataSource` dùng pool, việc đóng `Connection` thường đưa nó về pool để có thể cấp lại.

**Không tạo `new HikariDataSource(...)` trong mỗi phương thức xử lý request.** Các lớp truy cập dữ liệu nên nhận cùng DataSource qua constructor hoặc dependency injection. Nếu ứng dụng kết nối nhiều database độc lập, có thể cần nhiều DataSource, mỗi cái gắn với pool riêng.

### 3.3. Vòng đời pool

Mở pool khi ứng dụng khởi động và đóng khi ứng dụng dừng, sau khi những thành phần cần connection đã dừng. Ví dụ chương trình chạy ngắn:

~~~java
public static void main(String[] args) throws Exception {
    try (HikariDataSource dataSource = DataSourceFactory.create()) {
        ProductReader reader = new ProductReader(dataSource);
        System.out.println(reader.findName(42L));
    } // Pool được đóng khi công việc hoàn tất.
}
~~~

Trong web application hoặc service dài hạn, hãy để Spring hoặc application container quản lý vòng đời pool. Đóng pool trong khi vẫn còn request hoạt động sẽ khiến các thao tác cần connection thất bại.

## 4. Cho Hibernate sử dụng DataSource chung

Hibernate có thể lấy connection từ `DataSource` đã tạo thay vì tự tạo connection dựa trên URL, user và password. Khi dùng Hibernate ORM trực tiếp, có thể truyền DataSource vào cấu hình lúc dựng `SessionFactory`:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.hibernate.SessionFactory;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

HikariDataSource dataSource = DataSourceFactory.create();

StandardServiceRegistry registry =
    new StandardServiceRegistryBuilder()
        .applySetting("hibernate.connection.datasource", dataSource)
        .build();

SessionFactory sessionFactory = new MetadataSources(registry)
    .addAnnotatedClass(Product.class)
    .buildMetadata()
    .buildSessionFactory();
~~~

`Product.class` là entity Hibernate/JPA do dự án định nghĩa, chẳng hạn lớp gắn `@Entity`. Ví dụ trình bày bước khởi tạo: ứng dụng thực tế phải quản lý xử lý lỗi khi tạo factory, đóng `SessionFactory` và pool vào lúc shutdown. Nếu khởi tạo SessionFactory thất bại, phải giải phóng registry/pool đã tạo thành công trước đó.

Khi đã cấu hình xong:

~~~java
try (var session = sessionFactory.openSession()) {
    var tx = session.beginTransaction();
    try {
        Product product = session.find(Product.class, 42L);
        if (product != null) {
            product.setName("Updated name");
        }
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Vòng đời của các thành phần:

| Đối tượng | Thời gian tồn tại thường gặp | Cách dùng |
| --- | --- | --- |
| `DataSource` dạng pool | Cả vòng đời ứng dụng | Dùng chung, cung cấp connection cho nhiều luồng |
| `SessionFactory` / `EntityManagerFactory` | Cả vòng đời ứng dụng | Được thiết kế để chia sẻ và mở session/entity manager |
| `Session` / `EntityManager` | Theo đơn vị công việc/transaction | Không chia sẻ giữa nhiều thread đồng thời |
| JDBC `Connection` được mượn | Theo nhu cầu truy vấn/transaction | Dùng trong phạm vi phù hợp rồi trả pool |
| `PreparedStatement` / `ResultSet` | Theo thao tác SQL | Đóng ngay sau khi dùng |

Hibernate có thể mượn connection trễ hơn thời điểm `openSession()` và trả nó tùy chiến lược connection handling, loại transaction và cấu hình. **Một Session không nhất thiết giữ một connection vật lý suốt vòng đời**. Dù vậy, transaction kéo dài hoặc kết quả đang đọc có thể làm connection bị giữ lâu.

Không nên cấu hình nhiều cách lấy connection có xung đột, chẳng hạn vừa đưa `hibernate.connection.datasource` vừa đặt connection provider custom không tương thích. Cần xác định thành phần nào thực sự sở hữu pool.

## 5. Spring Boot + Spring Data JPA

Trong ứng dụng Spring Boot dùng Hibernate làm JPA provider, đường đi thường là:

~~~text
Controller / Service
         |
    @Transactional
         |
Repository / EntityManager
         |
       Hibernate
         |
Spring-managed DataSource
         |
       HikariCP
         |
     JDBC Driver
         |
       Database
~~~

Các dependency Gradle điển hình:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Với hệ thống dependency management phù hợp, Spring Boot quản lý phiên bản phụ thuộc. File `application.yml` minh họa:

~~~yaml
spring:
  datasource:
    url: ${APP_DB_URL}
    username: ${APP_DB_USERNAME}
    password: ${APP_DB_PASSWORD}
    hikari:
      pool-name: shop-db-pool
      maximum-pool-size: 10
      connection-timeout: 30000
      max-lifetime: 1700000

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
~~~

- `spring.datasource.*` cung cấp cấu hình kết nối.
- `spring.datasource.hikari.*` cấu hình HikariCP khi Spring Boot dùng HikariCP.
- `open-in-view: false` tránh giữ persistence context trong suốt quá trình render web response; các truy cập lazy phải được giải quyết qua transaction/fetch plan phù hợp ở service.
- `ddl-auto: validate` yêu cầu schema đã tồn tại và phù hợp entity. Nó không tạo bảng. Nếu schema chưa được migration hoặc không khớp, ứng dụng có thể không khởi động.

Với cấu hình tự động của Spring Boot, thông thường không cần tự viết thêm một bean `HikariDataSource`. Nếu phải tự cấu hình DataSource bean, cần hiểu cách auto-configuration chọn bean để không vô tình tạo hai pool.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public void rename(long id, String newName) {
        Product product = productRepository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sản phẩm"));

        product.setName(newName);
    }
}
~~~

`ProductRepository` là repository cho entity `Product`. Hibernate sẽ đồng bộ thay đổi theo transaction do Spring quản lý. Service không cần gọi `dataSource.getConnection()` hoặc `commit()` thủ công.

## 6. DataSource do application server quản lý và JNDI

Trong Jakarta EE hoặc ứng dụng triển khai trên application server, container có thể tạo pool, quản lý tài khoản kết nối và cung cấp DataSource qua **JNDI**. Ứng dụng chỉ dùng tên tài nguyên.

Ví dụ `META-INF/persistence.xml` cho JPA transaction kiểu JTA:

~~~xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.0">
    <persistence-unit name="shopPU" transaction-type="JTA">
        <jta-data-source>java:comp/env/jdbc/ShopDB</jta-data-source>
        <class>com.example.shop.Product</class>
    </persistence-unit>
</persistence>
~~~

Tên `java:comp/env/jdbc/ShopDB` chỉ là ví dụ và phải được bind trong môi trường triển khai. Pool thuộc quyền sở hữu application server, vì vậy ứng dụng **không tự đóng DataSource do container cấp**.

Nếu persistence unit sử dụng transaction kiểu local, có thể cấu hình phần tử `<non-jta-data-source>` cùng `transaction-type="RESOURCE_LOCAL"` theo mô hình triển khai. Không đổi tùy ý JTA thành RESOURCE_LOCAL: khác biệt này quyết định ai quản lý transaction và cách connection tham gia giao dịch.

JNDI giúp tách thông tin kết nối của từng môi trường khỏi mã ứng dụng. Kích thước pool, tài khoản và chính sách bảo mật có thể được cấu hình tại server.

## 7. Các thông số connection pool quan trọng

| Thông số HikariCP | Vai trò | Lưu ý |
| --- | --- | --- |
| `maximumPoolSize` | Giới hạn tổng số connection trong pool (đang rảnh và đang dùng) | Không tự động tăng tốc SQL; quá lớn có thể gây quá tải DB |
| `minimumIdle` | Số connection rảnh pool cố duy trì | Có thể để mặc định nếu không cần điều chỉnh riêng |
| `connectionTimeout` | Thời gian tối đa một tác vụ chờ mượn connection | Không phải thời gian thực thi SQL |
| `idleTimeout` | Thời gian connection rảnh có thể bị loại bỏ theo điều kiện pool | Ảnh hưởng phụ thuộc `minimumIdle` và cấu hình khác |
| `maxLifetime` | Tuổi tối đa dự kiến của connection trong pool | Connection đang sử dụng không bị cưỡng bức đóng chỉ vì đến tuổi |
| `keepaliveTime` | Chu kỳ kiểm tra/duy trì connection rảnh khi được bật | Phối hợp với giới hạn DB/proxy/network |
| `validationTimeout` | Giới hạn thời gian cho kiểm tra connection | Khác query timeout |
| `leakDetectionThreshold` | Ngưỡng phát cảnh báo khi connection bị giữ lâu | Chẩn đoán; không tự động thu hồi tại ngưỡng |

Ví dụ `maximumPoolSize = 10` và `connectionTimeout = 30.000ms` chỉ mang tính minh họa, không phải giá trị chuẩn cho mọi hệ thống.

### 7.1. Tính tổng connection trên nhiều instance

Giả sử ứng dụng triển khai 4 replica, mỗi replica có pool tối đa 15 connection. Tổng số connection mà riêng ứng dụng này có thể cần là:

\[
4 \times 15 = 60
\]

Phải tính cả connection từ service khác, job nền, công cụ quản trị và số kết nối dự phòng. Nếu tổng cao hơn giới hạn database hoặc vượt khả năng xử lý thực tế, tăng pool ở từng instance có thể khiến hệ thống kém ổn định.

Chọn pool dựa vào mức truy cập database đồng thời, thời gian giữ connection, khả năng xử lý của database và số replica. **Số HTTP request đồng thời không nhất thiết bằng số connection cần dùng**, vì không phải mọi request đều truy cập DB cùng lúc.

### 7.2. Các timeout có vai trò khác nhau

- **Connection timeout của pool:** chờ tối đa bao lâu để *mượn connection*.
- **Query/statement timeout:** thời gian được phép cho *thực thi SQL*, tùy API và JDBC driver.
- **Transaction timeout:** thời gian tối đa của toàn bộ transaction, nếu transaction manager hỗ trợ/cấu hình.
- **Connect/socket timeout của driver:** giới hạn ở tầng mạng khi kết nối hoặc đọc/ghi socket.

Tăng `connectionTimeout` sẽ không chữa một truy vấn chậm do thiếu index. `maxLifetime` cũng không phải giới hạn thời gian của transaction.

## 8. Transaction và việc dùng connection

### 8.1. Với JDBC trực tiếp

Khi không có transaction manager đứng ngoài, JDBC có thể quản lý transaction thủ công:

~~~java
public void transferStock(DataSource ds,
                          long sourceId,
                          long destinationId,
                          int quantity) throws SQLException {
    try (Connection connection = ds.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement dec = connection.prepareStatement(
                    "UPDATE inventory SET stock = stock - ? " +
                    "WHERE product_id = ? AND stock >= ?")) {
                dec.setInt(1, quantity);
                dec.setLong(2, sourceId);
                dec.setInt(3, quantity);
                if (dec.executeUpdate() != 1) {
                    throw new IllegalStateException("Không đủ hàng");
                }
            }

            try (PreparedStatement inc = connection.prepareStatement(
                    "UPDATE inventory SET stock = stock + ? " +
                    "WHERE product_id = ?")) {
                inc.setInt(1, quantity);
                inc.setLong(2, destinationId);
                if (inc.executeUpdate() != 1) {
                    throw new IllegalStateException("Không có nơi nhận");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        }
    }
}
~~~

Ví dụ mô tả hai lệnh UPDATE trong **cùng một connection/transaction**. Để thành nghiệp vụ kho hàng hoàn chỉnh còn cần xét tính cạnh tranh, lock, giới hạn số lượng và idempotency. Ứng dụng phải kết thúc transaction đúng cách trước khi trả connection về pool.

### 8.2. Với transaction do Hibernate hoặc Spring quản lý

Trong ứng dụng JPA/Spring `@Transactional`, transaction manager quản lý kết nối và commit/rollback. Nếu mã tự gọi `dataSource.getConnection()` không qua cơ chế tham gia transaction, SQL mới **có thể dùng một transaction khác**.

Để chạy JDBC trên connection đang gắn với Hibernate session, có thể dùng API riêng của Hibernate:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE products SET last_checked_at = ? WHERE id = ?")) {
        ps.setTimestamp(1, timestamp);
        ps.setLong(2, productId);
        ps.executeUpdate();
    }
});
~~~

`doWork()` cung cấp connection thuộc session; không tự đóng connection và không tự commit/rollback trong callback. Việc quản lý transaction vẫn thuộc phần bên ngoài. Với Spring JDBC, `JdbcTemplate` cũng có thể tham gia transaction Spring khi DataSource và transaction manager được cấu hình phù hợp.

**Lưu ý:** Native SQL hoặc JDBC trực tiếp có thể thay đổi dữ liệu trong database mà entity đang được quản lý vẫn giữ giá trị cũ trong persistence context. Khi phối hợp nhiều cách truy cập, cân nhắc `flush()` trước SQL và `refresh()`, `clear()` hay chiến lược đồng bộ sau SQL để tránh đọc dữ liệu cũ. Cùng connection/transaction không có nghĩa entity tự cập nhật.

## 9. Các lỗi kết nối thường gặp

### 9.1. Hết thời gian chờ lấy connection

Thông báo kiểu `Connection is not available, request timed out` có thể xuất hiện khi pool đã dùng hết connection và không có connection rảnh trước `connectionTimeout`.

Nguyên nhân có thể gồm:

- Transaction giữ connection lâu, ví dụ gọi API bên ngoài trong khi transaction database vẫn mở.
- Quên đóng `Connection` ở một nhánh code.
- SQL chậm, lock wait hoặc DB quá tải.
- Lưu lượng tăng bất thường hoặc pool nhỏ hơn nhu cầu đồng thời.
- Mạng/database không cấp được connection mới.

Nên quan sát active, idle, pending/waiting, thời gian giữ connection và độ trễ SQL trước khi tăng pool.

### 9.2. `Too many connections`

Database chạm giới hạn kết nối, có thể do nhiều replica, nhiều pool hoặc pool được tạo lặp trong request/repository. Tính tổng connection trên toàn bộ ứng dụng và service khác trước khi thay đổi cấu hình.

### 9.3. Connection bị đóng sau thời gian rảnh

Database, proxy, load balancer hoặc thiết bị mạng có thể đóng socket khi idle hoặc quá tuổi. Cần đối chiếu chính sách mạng/DB với `maxLifetime`, `keepaliveTime` và timeout của JDBC driver. Không tăng mọi timeout một cách tùy ý.

### 9.4. Sai driver, URL hoặc quyền kết nối

Các lỗi như `No suitable driver`, sai credentials hoặc không thể kết nối thường xuất hiện trước khi ORM chạy query. Kiểm tra runtime classpath của driver, JDBC URL, hostname/port, tài khoản, quyền schema, DNS, firewall và TLS.

### 9.5. Connection leak hoặc giữ quá lâu

Một connection bị giữ lâu chưa chắc là leak: truy vấn lớn, lock wait hoặc transaction dài cũng có thể có cùng biểu hiện. `leakDetectionThreshold` chỉ tạo log chẩn đoán, không tự động đóng connection. Cần đối chiếu call stack, thời gian transaction và metrics.

## 10. Metrics cần theo dõi

| Chỉ số | Cách diễn giải |
| --- | --- |
| Active connections | Nhiều tác vụ đang giữ connection |
| Idle connections | Số connection sẵn có để cho mượn |
| Pending threads/waiting requests | Tác vụ đang xếp hàng chờ connection |
| Connection acquisition time | Độ trễ từ lúc yêu cầu đến lúc mượn được connection |
| Connection usage/hold time | Thời gian connection bị giữ; liên quan transaction và SQL |
| Connection creation/failures | Lỗi driver, network, database hoặc giới hạn connection |
| SQL latency/lock wait | Nút thắt có thể nằm ở database |

HikariCP hỗ trợ xuất metrics qua những cơ chế tích hợp tùy ứng dụng. Trong Spring Boot, Actuator/Micrometer có thể cung cấp các chỉ số pool khi được cấu hình phù hợp. Nên kiểm tra log SQL và thời gian query, nhưng tránh log mật khẩu hoặc dữ liệu nhạy cảm trong bind parameters.

## 11. Nguyên tắc thiết kế để tránh lỗi

### 11.1. Chỉ một nơi sở hữu mỗi pool

- **Java SE:** ứng dụng tạo HikariDataSource và đóng nó khi shutdown.
- **Spring Boot:** Spring tự tạo/quản lý DataSource và Hibernate sử dụng bean đó.
- **Jakarta EE:** container tạo pool; JPA tham chiếu JNDI.

Không tự tạo thêm pool riêng trong mỗi repository nếu cùng dùng một database và một chính sách truy cập.

### 11.2. Chọn đúng scope

DataSource và SessionFactory là các thành phần hạ tầng dùng chung. Session/EntityManager mang trạng thái entity theo đơn vị công việc; Connection mang trạng thái giao dịch; PreparedStatement/ResultSet nằm trong một thao tác SQL. **Dùng chung connection pool không có nghĩa mọi request dùng chung cùng một đối tượng Connection hay Session.**

### 11.3. Pool không thay transaction

Một connection có thể phục vụ nhiều request tại các thời điểm khác nhau, nhưng transaction phải kết thúc đúng trước khi connection được trả và dùng lại. Cần đặt ranh giới transaction rõ trong service, tránh giữ transaction khi làm network I/O không cần thiết và xử lý rollback nhất quán.

### 11.4. Đóng tài nguyên theo thứ tự sở hữu

Nếu ứng dụng tạo tất cả tài nguyên, khi shutdown nên ngừng nhận công việc mới, hoàn tất các transaction đang chạy, đóng SessionFactory và các thành phần phụ thuộc, rồi đóng DataSource/pool. Nếu container sở hữu pool, chỉ đóng thành phần do ứng dụng sở hữu.

## 12. Kịch bản thực hành từ Java thuần sang Spring Boot

Giả sử xây dựng API sản phẩm bằng PostgreSQL:

**Giai đoạn A — Java thuần:** tạo một HikariDataSource lúc startup, inject vào lớp đọc dữ liệu, dùng `try-with-resources` cho connection và statement. Đóng pool khi dừng chương trình.

**Giai đoạn B — Thêm Hibernate:** khởi tạo SessionFactory sử dụng DataSource có sẵn; repository thao tác entity qua Session. Cần thiết kế transaction cho từng đơn vị công việc.

**Giai đoạn C — Chuyển sang Spring Boot:** đưa URL, credentials và cấu hình pool vào `application.yml`/biến môi trường. Dùng Spring Data JPA cùng `@Transactional` ở service. Xác nhận không còn pool tự tạo trùng lặp.

**Giai đoạn D — Tăng tải:** triển khai 5 replica, mỗi replica tối đa 10 connection, nghĩa là riêng service này có thể cần tối đa 50 connection. Đo active, waiting, thời gian mượn, thời gian giữ connection và độ trễ SQL trước khi chỉnh pool. Đồng thời kiểm tra giới hạn phía database và các ứng dụng khác.

### Bài tập tự kiểm tra

1. Vì sao tạo `new HikariDataSource(...)` mỗi request có thể gây quá tải database dù mỗi request chỉ gọi một query?
2. Với DataSource dạng pool, điều gì thường xảy ra khi kết thúc `try (Connection c = dataSource.getConnection())`?
3. Nếu service có 6 replica, mỗi replica có tối đa 12 connection, riêng service đó có thể cần bao nhiêu connection?
4. API báo timeout chờ lấy connection. Cần xem những metrics nào trước khi tăng `maximumPoolSize`?
5. Vì sao tự mượn `DataSource.getConnection()` trong một transaction do Spring/JPA quản lý có thể làm SQL không thuộc cùng transaction?
6. Vì sao Hibernate `SessionFactory` và `Session` không nên có cùng scope?

**Gợi ý:** (1) nhiều pool tạo ra tổng connection vượt dự kiến; (2) `close()` thường trả connection về pool; (3) `6 × 12 = 72`; (4) active, waiting, thời gian giữ connection và SQL latency; (5) connection mới có thể không được enlist đúng cách; (6) factory là hạ tầng dùng chung còn session giữ trạng thái ORM theo đơn vị công việc.

---

Khi khởi tạo Hibernate/JPA, hãy xác định rõ **ai tạo DataSource, ai quản lý pool, ai quản lý transaction và khi nào từng connection được trả lại**. Một DataSource quản lý tập trung giúp tái sử dụng kết nối, kiểm soát tải lên database và ổn định vận hành; mã nghiệp vụ cần giữ transaction, Session/EntityManager và tài nguyên JDBC trong phạm vi phù hợp.
