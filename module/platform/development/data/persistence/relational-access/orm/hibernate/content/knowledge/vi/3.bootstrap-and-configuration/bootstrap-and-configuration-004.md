# Cấu hình bằng thuộc tính, tệp cấu hình và môi trường triển khai

## 1. Vì sao cấu hình Hibernate phải được thiết kế có chủ đích?

Trong ứng dụng Java sử dụng cơ sở dữ liệu quan hệ, cùng một tập entity có thể chạy trên máy lập trình viên, môi trường kiểm thử, staging và production. Mỗi môi trường có địa chỉ cơ sở dữ liệu, thông tin xác thực, chính sách tạo schema, cấu hình pool kết nối và mức độ ghi log khác nhau. Việc **khởi tạo Hibernate ORM** vì vậy không chỉ là khai báo URL JDBC: ta cần xác định **ai tạo `EntityManagerFactory`/`SessionFactory`, cấu hình được đọc từ đâu, giá trị nào có hiệu lực cuối cùng và ai quản lý tài nguyên**.

Trong mô hình này:

- **Jakarta Persistence (JPA)** định nghĩa API chuẩn như `EntityManagerFactory`, `EntityManager` và định dạng `META-INF/persistence.xml`.
- **Hibernate ORM** là một provider của Jakarta Persistence, đồng thời có API và tùy chọn cấu hình riêng, thường mang tiền tố `hibernate.`.
- **Spring Boot hoặc Jakarta EE** có thể quản lý quá trình khởi tạo, `DataSource`, transaction và vòng đời tài nguyên thay cho code Java SE tự khởi tạo.

Luồng cấu hình khái quát:

```text
        File cấu hình              Biến môi trường / secrets
      (XML, properties, YAML)          / tham số triển khai
                 \                         /
                  \                       /
                   v                     v
                 Lớp khởi tạo / framework
                           |
                           v
                Hibernate / JPA provider
                           |
                  EntityManagerFactory
                    hoặc SessionFactory
                           |
                       DataSource
                           |
                    JDBC / Database
```

**Mục tiêu bài học:** đọc được các loại cấu hình phổ biến; chọn được cách khởi tạo phù hợp với Java SE, Spring Boot hoặc Jakarta EE; tách cấu hình theo môi trường; nắm cách ghi đè thuộc tính và quản lý bí mật; nhận biết lỗi cấu hình trước khi đi vào logic ORM.

## 2. Ba mô hình khởi tạo phổ biến

| Mô hình | Điểm khởi tạo | Nguồn cấu hình tiêu biểu | Ai quản lý tài nguyên? |
|---|---|---|---|
| Java SE qua Jakarta Persistence | `Persistence.createEntityManagerFactory(...)` | `META-INF/persistence.xml`, `Map` thuộc tính truyền khi bootstrap | Ứng dụng đóng `EntityManager` và `EntityManagerFactory` |
| Java SE qua Hibernate native API | `Configuration` hoặc bootstrapping API của Hibernate tạo `SessionFactory` | `hibernate.cfg.xml`, `hibernate.properties`, `Properties`, `Map`/builder | Ứng dụng đóng `Session` và `SessionFactory` |
| Spring Boot / Jakarta EE | Framework/container khởi tạo provider | `application.properties`/`.yml`, cấu hình deploy, `DataSource` do container quản lý | Framework quản lý factory, transaction, pool và shutdown |

Đây là **những cách cấu hình cùng một ORM**, không phải ba cơ sở dữ liệu hay ba hệ thống ORM khác nhau. Trong một ứng dụng Spring Boot bình thường, không cần tạo thêm `SessionFactory` riêng bằng `new Configuration().buildSessionFactory()`: việc đó có thể sinh thêm pool kết nối, persistence context và chính sách transaction ngoài kiểm soát của framework.

### Hai khái niệm cần phân biệt

**Persistence unit** là đơn vị cấu hình JPA: tên, provider, entity, nguồn dữ liệu và các thuộc tính liên quan. **`EntityManagerFactory`** được tạo theo cấu hình persistence unit và dùng để tạo các `EntityManager`.

Trong Hibernate native API, **`SessionFactory`** là factory tương ứng và chứa các metadata mapping, tài nguyên cần dùng để tạo `Session`. Một factory thường có vòng đời dài, trong khi `EntityManager`/`Session` có vòng đời ngắn, gắn với transaction hoặc đơn vị công việc. Không chia sẻ `EntityManager` hay `Session` như một singleton dùng đồng thời giữa nhiều thread.

## 3. Nhận diện đúng tên thuộc tính

Có nhiều lớp cấu hình có tên khá giống nhau nhưng không thể tùy tiện thay thế:

| Mục đích | Thuộc tính Jakarta Persistence | Thuộc tính Hibernate native | Thuộc tính Spring Boot |
|---|---|---|---|
| JDBC URL | `jakarta.persistence.jdbc.url` | `hibernate.connection.url` | `spring.datasource.url` |
| JDBC driver | `jakarta.persistence.jdbc.driver` | `hibernate.connection.driver_class` | `spring.datasource.driver-class-name` |
| Tên người dùng DB | `jakarta.persistence.jdbc.user` | `hibernate.connection.username` | `spring.datasource.username` |
| Mật khẩu DB | `jakarta.persistence.jdbc.password` | `hibernate.connection.password` | `spring.datasource.password` |
| Hành động tạo/xóa schema theo JPA | `jakarta.persistence.schema-generation.database.action` | Không có cặp đối ứng hoàn toàn tương đương | Có thể truyền thuộc tính JPA qua `spring.jpa.properties.*` |
| Quản lý schema kiểu Hibernate | Không có giá trị chuẩn `validate` tương ứng | `hibernate.hbm2ddl.auto` | `spring.jpa.hibernate.ddl-auto` |
| In SQL ra console | Không có thuộc tính JPA chuẩn phổ biến cho việc này | `hibernate.show_sql` | `spring.jpa.show-sql` hoặc `spring.jpa.properties.hibernate.show_sql` |
| Format SQL khi in | Không có | `hibernate.format_sql` | `spring.jpa.properties.hibernate.format_sql` |
| JDBC batch size | Không có | `hibernate.jdbc.batch_size` | `spring.jpa.properties.hibernate.jdbc.batch_size` |

**Cách đọc bảng:** tên `spring.datasource.url` được Spring Boot dùng để cấu hình `DataSource` rồi đưa nguồn kết nối đó cho JPA/Hibernate. Nó không phải một khóa Hibernate native. Tương tự, `spring.jpa.hibernate.ddl-auto` là tiện ích cấu hình của Spring Boot, không phải property chuẩn Jakarta Persistence.

Trong hệ sinh thái cũ, bạn có thể gặp `javax.persistence.jdbc.url`, `javax.persistence.EntityManager` và Hibernate 5. Những ví dụ của bài này dùng thế hệ **Jakarta** với `jakarta.persistence.*`. Khi nâng cấp cần đồng bộ phiên bản Hibernate, Jakarta Persistence, framework và JDBC driver; không được trộn các thế hệ thư viện tùy ý.

## 4. Cấu hình JPA bằng `META-INF/persistence.xml`

Đối với Java SE sử dụng API Jakarta Persistence, một bố cục thông dụng là:

```text
project/
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Product.java
        │       └── Main.java
        └── resources/
            └── META-INF/
                └── persistence.xml
```

Tệp `persistence.xml` nằm trên **runtime classpath** dưới `META-INF`, không chỉ nằm ở một vị trí tùy ý trong thư mục gốc dự án. Ví dụ tối thiểu dùng cơ sở dữ liệu H2 trong bộ nhớ để học và thử nghiệm:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="inventory-pu" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Product</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:inventory;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>

            <!-- Chỉ dùng cho bài học: tạo rồi hủy schema thử nghiệm. -->
            <property name="hibernate.hbm2ddl.auto" value="create-drop"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Giải thích:

- `inventory-pu` là **tên persistence unit** mà ứng dụng sẽ yêu cầu khởi tạo.
- `<provider>` chọn Hibernate làm implementation; tùy môi trường, provider cũng có thể được phát hiện tự động từ dependency.
- `<class>` liệt kê entity tham gia persistence unit; cơ chế quét entity còn phụ thuộc môi trường đóng gói và provider.
- `RESOURCE_LOCAL` nghĩa transaction do ứng dụng quản lý trực tiếp trong ví dụ Java SE. Trong môi trường dùng JTA, cách khai báo và quản lý transaction khác.
- Các thuộc tính `jakarta.persistence.jdbc.*` đến từ đặc tả; `hibernate.hbm2ddl.auto`, `hibernate.show_sql` và `hibernate.format_sql` là thuộc tính riêng của Hibernate.
- `create-drop` được đưa vào chỉ để tạo dữ liệu thử nghiệm có thể xóa đi; không áp dụng cho cơ sở dữ liệu cần lưu trữ lâu dài.

Phiên bản XML (`3.1` trong ví dụ) cần khớp với họ thư viện Jakarta Persistence được chọn. Với dự án dùng phiên bản khác, tra tài liệu đặc tả để chọn schema tương ứng.

### 4.1. Một entity nhỏ cho các ví dụ

```java
package demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.math.BigDecimal;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;
    private BigDecimal price;

    protected Product() {} // Constructor cho JPA

    public Product(String sku, BigDecimal price) {
        this.sku = sku;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
}
```

Để thực hiện ví dụ cần Hibernate ORM, Jakarta Persistence API phù hợp và JDBC driver H2 trên runtime classpath. Dự án thực tế có thể sử dụng Maven hoặc Gradle để quản lý các dependency này. Nếu dùng Spring Boot, nên theo BOM/dependency management tương thích do Spring Boot quản lý, tránh tự trộn nhiều phiên bản Hibernate.

### 4.2. Khởi tạo và đóng tài nguyên

```java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.math.BigDecimal;

public class Main {
    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("inventory-pu");

        try {
            EntityManager em = emf.createEntityManager();
            try {
                em.getTransaction().begin();
                em.persist(new Product("P-001", new BigDecimal("49.90")));
                em.getTransaction().commit();
            } catch (RuntimeException ex) {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
                throw ex;
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
```

`Persistence.createEntityManagerFactory("inventory-pu")` tra tên persistence unit trong cấu hình. Nếu file không nằm trên classpath, tên không khớp hoặc không có provider tương thích, quá trình bootstrap có thể thất bại **trước khi chương trình chạy bất kỳ truy vấn nghiệp vụ nào**.

`EntityManagerFactory` nên được sử dụng lại trong thời gian ứng dụng hoạt động; tạo factory mới cho từng truy vấn là tốn kém. `EntityManager` thì cần phạm vi ngắn và phải được đóng. Khi transaction thất bại, rollback trước khi đóng. Không tái sử dụng một `EntityManager` có trạng thái lỗi một cách tùy tiện.

## 5. Ghi đè cấu hình JPA bằng thuộc tính Java

File XML phù hợp để định nghĩa cấu trúc persistence unit. Tuy nhiên địa chỉ DB và bí mật triển khai thường không nên ghi trực tiếp trong file được commit vào repository. API chuẩn cho phép truyền map thuộc tính khi tạo factory:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.util.HashMap;
import java.util.Map;

Map<String, Object> overrides = new HashMap<>();
overrides.put("jakarta.persistence.jdbc.driver", "org.postgresql.Driver");
overrides.put("jakarta.persistence.jdbc.url", requiredEnv("DB_URL"));
overrides.put("jakarta.persistence.jdbc.user", requiredEnv("DB_USER"));
overrides.put("jakarta.persistence.jdbc.password", requiredEnv("DB_PASSWORD"));
overrides.put("hibernate.hbm2ddl.auto", "validate");
overrides.put("hibernate.show_sql", "false");

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("inventory-pu", overrides);
try {
    // Tạo EntityManager và thực hiện công việc tại đây.
} finally {
    emf.close();
}

// Helper đặt trong class chứa hàm main hoặc lớp cấu hình.
private static String requiredEnv(String name) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
        throw new IllegalStateException("Missing environment variable: " + name);
    }
    return value;
}
```

Đoạn code minh họa các mảnh trong một class Java thích hợp; method `requiredEnv` không được đặt tự do ở ngoài class. Khi triển khai cùng file `persistence.xml` ở phần trước, map truyền vào factory **ghi đè những thuộc tính trùng tên** trong persistence unit. Mức ưu tiên và cách xử lý các khóa của từng provider cần được kiểm tra nếu cùng giá trị còn xuất hiện trong nhiều nguồn riêng của framework.

Ví dụ yêu cầu PostgreSQL JDBC driver tương thích xuất hiện trong dependency. Không nên thực hiện `System.out.println(overrides)` vì map có mật khẩu. `DB_URL`, `DB_USER`, `DB_PASSWORD` ở đây là **tên biến do ứng dụng tự quy ước**, không phải tên tự động được chuẩn JPA đọc.

> **Điểm dễ nhầm:** đặt `${DB_PASSWORD}` trong thuộc tính `persistence.xml` không có nghĩa một ứng dụng Java SE thuần JPA sẽ tự thay bằng biến môi trường. Khả năng nội suy placeholder phụ thuộc công cụ/framework đang đọc file. Cách minh bạch trong Java SE là đọc biến môi trường và truyền property map hoặc cung cấp `DataSource` đã cấu hình.

## 6. Cấu hình Hibernate native bằng `hibernate.cfg.xml`

Khi dùng Hibernate trực tiếp qua `SessionFactory`, bạn có thể sử dụng tệp `hibernate.cfg.xml` ở thư mục `src/main/resources`:

```text
src/main/resources/
└── hibernate.cfg.xml
```

Ví dụ dành cho môi trường học tập:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE hibernate-configuration PUBLIC
        "-//Hibernate/Hibernate Configuration DTD 3.0//EN"
        "https://hibernate.org/dtd/hibernate-configuration-3.0.dtd">
<hibernate-configuration>
    <session-factory>
        <property name="hibernate.connection.driver_class">org.h2.Driver</property>
        <property name="hibernate.connection.url">
            jdbc:h2:mem:inventory;DB_CLOSE_DELAY=-1
        </property>
        <property name="hibernate.connection.username">sa</property>

        <property name="hibernate.hbm2ddl.auto">create-drop</property>
        <property name="hibernate.show_sql">true</property>
        <property name="hibernate.format_sql">true</property>

        <mapping class="demo.Product"/>
    </session-factory>
</hibernate-configuration>
```

Và quá trình bootstrap bằng native API:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.cfg.Configuration;

try (SessionFactory factory = new Configuration()
        .configure("hibernate.cfg.xml")
        .buildSessionFactory()) {
    try (Session session = factory.openSession()) {
        // Làm việc với entity và transaction ở đây.
    }
}
```

Các thao tác `Configuration.configure()`, mapping và `buildSessionFactory()` thuộc Hibernate. Chúng không được Jakarta Persistence bảo đảm cho các provider khác. Nếu đổi provider, cách bootstrap này phải được thay đổi.

Tệp XML có thể hữu ích khi ứng dụng cần liệt kê mapping và cấu hình Hibernate trong một nơi; nhưng không bắt buộc phải dùng nếu Java code, JPA hoặc framework đã quản lý cấu hình. Giữ **một luồng bootstrap thống nhất** để tránh tạo nhiều factory không chủ đích.

## 7. Cấu hình Hibernate bằng `Properties` và Java code

Khi cấu hình được lấy từ hệ thống quản lý secrets, biến môi trường hoặc đối tượng `DataSource`, code Java có thể xây dựng properties tại thời điểm khởi động:

```java
import java.util.Properties;
import org.hibernate.SessionFactory;
import org.hibernate.cfg.Configuration;

Properties props = new Properties();
props.setProperty("hibernate.connection.driver_class", "org.h2.Driver");
props.setProperty("hibernate.connection.url",
                  "jdbc:h2:mem:inventory;DB_CLOSE_DELAY=-1");
props.setProperty("hibernate.connection.username", "sa");
props.setProperty("hibernate.hbm2ddl.auto", "create-drop");
props.setProperty("hibernate.show_sql", "false");

try (SessionFactory factory = new Configuration()
        .addAnnotatedClass(Product.class)
        .addProperties(props)
        .buildSessionFactory()) {
    // Dùng factory mở Session khi cần.
}
```

Trong ví dụ, metadata entity được khai báo qua `addAnnotatedClass()` thay vì `<mapping>` trong file. Bạn cũng có thể kết hợp file và các thuộc tính điều chỉnh ở runtime, nhưng cần xác định rõ thứ tự gọi `configure()`, `addProperties()`, `setProperty()` hoặc các builder tương ứng: giá trị cung cấp về sau có thể thay đổi giá trị đã nạp trước đó.

Hibernate còn có cơ chế đọc tệp `hibernate.properties` trên classpath trong một số luồng bootstrap. Tệp này có cú pháp Java properties:

```properties
# hibernate.properties - chỉ chứa giá trị không nhạy cảm trong ví dụ
hibernate.show_sql=false
hibernate.format_sql=true
hibernate.jdbc.batch_size=25
```

**Không giả định tất cả các đường bootstrap đều đọc `hibernate.properties` giống nhau.** Nếu dùng `Persistence.createEntityManagerFactory`, Spring Boot hoặc container, hãy ưu tiên cơ chế cấu hình mà môi trường đó tài liệu hóa và xác nhận giá trị nào thực sự được áp dụng. Một số API bootstrap hiện đại của Hibernate còn dùng `StandardServiceRegistryBuilder` và `MetadataSources` để khai báo các setting và metadata tường minh, phù hợp các ứng dụng cần kiểm soát sâu.

### Khi nào chọn XML, khi nào chọn Java code?

| Cách cấu hình | Điểm mạnh | Điểm cần quản lý |
|---|---|---|
| `persistence.xml` | Chuẩn JPA, rõ persistence unit và provider | Path classpath; thuộc tính riêng vẫn phụ thuộc Hibernate |
| `hibernate.cfg.xml` | Tập trung mapping và thông số Hibernate | Phụ thuộc native API, không tự giải quyết secret deployment |
| `hibernate.properties` | Ngắn gọn, dễ khai báo thông số đơn giản | Cơ chế tải và thứ tự ưu tiên phụ thuộc bootstrap |
| Java `Properties`/`Map` | Dễ ghép giá trị từ runtime, secret manager | Tránh hard-code bí mật và bootstrap rải rác |
| Spring Boot config | Kết nối với profile, DataSource, pool, transaction và lifecycle | Phải hiểu cơ chế auto-configuration, property binding và precedence |

## 8. Cấu hình bằng Spring Boot

Trong một ứng dụng Spring Boot có Spring Data JPA, thông thường Spring Boot khởi tạo `DataSource`, `EntityManagerFactory` và transaction manager từ cấu hình ứng dụng. Hibernate là JPA provider được lựa chọn theo dependency. Ví dụ `src/main/resources/application.properties`:

```properties
# Kết nối cơ sở dữ liệu lấy từ môi trường triển khai
spring.datasource.url=${DB_URL}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}

# Tầng JPA/Hibernate
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
spring.jpa.open-in-view=false

# Chuyển trực tiếp các setting riêng sang Hibernate
spring.jpa.properties.hibernate.format_sql=false
spring.jpa.properties.hibernate.jdbc.batch_size=30
spring.jpa.properties.hibernate.default_batch_fetch_size=20
```

Ý nghĩa:

- `spring.datasource.*` định nghĩa cách Spring Boot tạo hoặc cấu hình một `DataSource`; trong dự án có connection pool (thường là HikariCP), pool quản lý mở/tái sử dụng kết nối.
- `spring.jpa.hibernate.ddl-auto=validate` yêu cầu Hibernate đối chiếu mapping với schema hiện có; nó không phải công cụ tạo migration.
- `spring.jpa.open-in-view=false` đóng cách sử dụng persistence context xuyên suốt việc render HTTP response theo mô hình Open Session in View. Khi tắt, phải chủ động thiết kế fetch và DTO trong phạm vi transaction phù hợp.
- `spring.jpa.properties.*` chuyển các thuộc tính còn lại cho provider. Với Hibernate, phần tên sau tiền tố phải đúng theo tên key Hibernate yêu cầu.

Ở đây, `${DB_URL}`, `${DB_USER}` và `${DB_PASSWORD}` được **Spring Environment** xử lý. Chúng không phải tính năng nội suy mặc định của Jakarta Persistence XML thuần. Với ví dụ trên, không cần thêm `persistence.xml` nếu không có yêu cầu cấu hình JPA đặc biệt mà Spring Boot chưa đáp ứng.

### 8.1. Ví dụ YAML tương đương

`src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}

  jpa:
    open-in-view: false
    show-sql: false
    hibernate:
      ddl-auto: validate
```

YAML có lợi khi cấu trúc sâu và cần đọc các nhóm cấu hình. Với khóa Hibernate chứa dấu chấm hoặc dấu gạch dưới như `hibernate.jdbc.batch_size`, nên kiểm tra cách Spring Boot bind `Map` thuộc tính theo phiên bản đang dùng. File `.properties` với tên key tường minh thường dễ đối chiếu với tài liệu Hibernate hơn khi cần thiết lập nhiều setting vendor-specific.

### 8.2. Dependency và auto-configuration

Một Spring Boot application dùng JPA thường cần starter tương ứng (ví dụ `spring-boot-starter-data-jpa`), database driver, cùng cấu hình `DataSource`. Nếu starter/framework đã quản lý phiên bản Hibernate, tự ép một bản Hibernate khác có thể dẫn đến lỗi tương thích Jakarta Persistence, transaction, query hoặc bytecode enhancement.

Trong code nghiệp vụ, dùng `@Transactional` và repository/`EntityManager` được inject theo cơ chế Spring; không tự gọi `entityManager.getTransaction().begin()` hoặc tạo một factory mới chỉ để thực hiện cùng giao dịch do Spring quản lý.

## 9. Tách cấu hình dev, test, staging và production

Không có một bộ cấu hình kết nối và schema phù hợp cho mọi môi trường. Quy ước hữu ích:

| Khía cạnh | Development | Automated test | Staging | Production |
|---|---|---|---|---|
| Nguồn DB | DB local / container | DB cô lập, dễ reset | DB riêng gần giống production | DB được quản trị, sao lưu và giám sát |
| Schema | Có thể `create-drop` cho DB thử nghiệm ngắn hạn | Tạo mới hoặc migration trên DB test | Migration + `validate` | Migration có kiểm soát + `validate`/`none` |
| Secrets | Giá trị dev riêng, không commit | Credential test chỉ trong môi trường test | Secret manager/deployment | Secret manager/deployment, quyền tối thiểu |
| SQL logging | Bật khi gỡ lỗi có mục tiêu | Giữ đủ thông tin khi test lỗi | Theo nhu cầu chẩn đoán | Tối thiểu, tránh bind values nhạy cảm |
| Pool | Nhỏ, phù hợp số luồng local | Cô lập cho từng test context | Tương đương cách dùng production | Giám sát số kết nối và giới hạn DB |

### 9.1. Spring profiles

Spring Boot hỗ trợ tách cấu hình theo profile. Ví dụ:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
├── application-test.properties
└── application-prod.properties
```

`application.properties` chứa giá trị chung, chẳng hạn:

```properties
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
```

`application-dev.properties` dùng DB local **chỉ để phát triển**:

```properties
spring.datasource.url=jdbc:h2:mem:localdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.jpa.hibernate.ddl-auto=create-drop
```

`application-prod.properties` lấy nguồn kết nối từ deployment:

```properties
spring.datasource.url=${DB_URL}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
```

Kích hoạt một profile có thể thông qua biến môi trường `SPRING_PROFILES_ACTIVE=prod` hoặc tham số khởi động `--spring.profiles.active=prod`. Chú ý việc ưu tiên nguồn property của Spring Boot phụ thuộc thứ tự hệ thống cấu hình (file, profile, biến môi trường, tham số dòng lệnh, v.v.); phải xem quy tắc cho phiên bản Boot thực tế, nhất là khi có nhiều file hoặc cấu hình được import.

**Đừng nhầm profile là cơ chế bảo mật.** Profile chỉ chọn cấu hình; quyền DB, network policy, secret manager và quy trình deploy vẫn phải bảo vệ môi trường production. Profile `prod` không bảo đảm an toàn nếu URL trỏ nhầm đến DB khác hoặc tài khoản DB có quyền quá rộng.

### 9.2. Khi không dùng Spring Boot

Java SE vẫn có thể tách cấu hình bằng cách:

1. Giữ thông tin chung về entity và provider trong `persistence.xml` hoặc cấu hình Hibernate native.
2. Cung cấp endpoint và credential qua biến môi trường, secret manager hay file được mount khi deploy.
3. Đọc các giá trị đó khi bootstrap, kiểm tra giá trị bắt buộc, sau đó truyền `Map`/`Properties` hoặc cấu hình `DataSource`.
4. Chỉ chọn hành động schema cho phép trong môi trường đang chạy.

Nếu cần tên tệp riêng theo môi trường (ví dụ `db-dev.properties`), ứng dụng phải có code tải tệp và cơ chế ưu tiên rõ ràng; **đừng mặc định Hibernate sẽ tự biết** các tên tùy ý đó.

## 10. Biến môi trường, external configuration và secret management

Một cấu hình deployment tốt cho phép cùng một build chạy ở nhiều môi trường mà không chỉnh sửa artifact. Các biến môi trường ví dụ:

```text
DB_URL=jdbc:postgresql://db.example.internal:5432/inventory
DB_USER=inventory_app
DB_PASSWORD=<do-deployment-secret-manager-cung-cap>
```

Giá trị trên chỉ là **placeholder minh họa**, không phải thông tin đăng nhập sử dụng được. `DB_URL` cần chỉ đến đúng server/database mà deployment dự kiến. Có thể đặt bí mật qua biến môi trường, file secret được mount hoặc cơ chế truy xuất secret manager. Lựa chọn cụ thể phụ thuộc môi trường triển khai và chính sách tổ chức.

Khi dùng Docker/Compose/Kubernetes hoặc hệ thống CI/CD, luồng mong muốn thường là:

```text
Build ứng dụng một lần
        |
        v
Artifact (jar/image) có cấu hình chung
        |
        +-- Dev deployment  --> DB dev  + secrets dev
        |
        +-- Test deployment --> DB test + secrets test
        |
        +-- Prod deployment --> DB prod + secrets prod
```

### 10.1. Quy tắc cho dữ liệu bí mật

- Không commit mật khẩu DB, token hoặc URL có embedded password vào `application.properties`, `persistence.xml`, `hibernate.cfg.xml`, script hay ảnh chụp log.
- Cấp cho ứng dụng một tài khoản DB riêng với quyền phù hợp; tài khoản chạy migration có thể cần quyền khác tài khoản xử lý request.
- Không log toàn bộ property map, connection string nhạy cảm, environment dump hoặc tham số bind chứa dữ liệu cá nhân.
- Xác định cách rotation và cách ứng dụng nhận secret mới; nhiều pool kết nối giữ kết nối đã tạo nên cần xem xét tác động khi đổi credential.
- Đừng coi việc che mật khẩu trong UI là đã bảo vệ secret: cần kiểm soát nơi lưu, nơi truyền, quyền đọc và log của hệ thống triển khai.

### 10.2. Biến môi trường Java và Spring Boot khác nhau thế nào?

Trong Java thuần, `System.getenv("DB_URL")` trả về chuỗi hoặc `null`; không có cơ chế tự đổi mọi tên biến thành thuộc tính Hibernate. Trong Spring Boot, `SPRING_DATASOURCE_URL` có thể được ánh xạ theo cơ chế externalized configuration của Spring, còn `${DB_URL}` là một placeholder tham chiếu biến do deployment cung cấp. Hai cách đều hợp lệ, nhưng phải chọn quy ước nhất quán và tránh tạo hai biến cùng mục đích nhưng giá trị khác nhau.

## 11. `DataSource`, JDBC pool và quyền quản lý kết nối

Một ứng dụng hoạt động dài hạn không nên mở `DriverManager.getConnection()` mới cho mỗi thao tác ORM rồi bỏ qua quản lý pool. Hibernate có thể nhận cấu hình kết nối trực tiếp trong demo, nhưng trong ứng dụng production nên ưu tiên **`DataSource` có connection pool được quản lý**.

```text
    Business service
          |
    @Transactional
          |
 EntityManager / Session
          |
      Hibernate
          |
     DataSource
          |
      JDBC Pool
      /  |  \
    Conn Conn Conn
          |
        Database
```

Trong Spring Boot, `spring.datasource.*` và cấu hình `spring.datasource.hikari.*` (khi dùng HikariCP) là nơi điều khiển kết nối/pool thông dụng:

```properties
# Chỉ là ví dụ cần điều chỉnh theo sức chứa DB và tải thực tế
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=30000
```

Đơn vị `connection-timeout` của HikariCP là **mili giây**. Pool quá lớn có thể làm nghẽn database; pool quá nhỏ có thể khiến request chờ kết nối. Không có một con số chung tối ưu cho mọi hệ thống. Cần quan sát số transaction đồng thời, thời gian giữ kết nối, ngưỡng DB và đặc điểm tải.

Khi container cung cấp `DataSource` qua JNDI hoặc inject vào framework, **không đồng thời ép Hibernate mở một nguồn kết nối khác** bằng `hibernate.connection.url` nếu không có chủ đích. Điều đó dễ làm Hibernate dùng sai database, tạo tài nguyên song song hoặc khiến transaction không tham gia môi trường đang quản lý.

## 12. Transaction: `RESOURCE_LOCAL`, JTA và framework-managed

Thiết lập transaction liên quan trực tiếp đến mô hình deployment, không chỉ là chọn tên thuộc tính.

### 12.1. Java SE dùng resource-local

```xml
<persistence-unit name="inventory-pu" transaction-type="RESOURCE_LOCAL">
    ...
</persistence-unit>
```

Ứng dụng sử dụng `EntityTransaction`:

```java
EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();
    // persist / update / remove / query cần tính nhất quán
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) em.getTransaction().rollback();
    throw ex;
} finally {
    em.close();
}
```

### 12.2. Container dùng JTA

Một ứng dụng Jakarta EE có thể sử dụng persistence unit kiểu JTA và `DataSource` được đăng ký trong container:

```xml
<persistence-unit name="orders-pu" transaction-type="JTA">
    <jta-data-source>java:comp/DefaultDataSource</jta-data-source>
</persistence-unit>
```

Địa chỉ JNDI trên là ví dụ: datasource thực tế phụ thuộc server, quyền truy cập và cấu hình triển khai. Với transaction được container quản lý, ứng dụng dùng phương thức container/JTA thích hợp thay vì tự `getTransaction().begin()` trên container-managed `EntityManager`.

### 12.3. Spring dùng transaction manager

Spring Boot thường cung cấp cơ chế transaction qua `@Transactional`:

```java
@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void register(Product product) {
        products.save(product);
    }
}
```

Ở đây `ProductRepository` là repository của ứng dụng, ví dụ một Spring Data JPA repository được khai báo phù hợp. Transaction do Spring xử lý qua proxy/transaction manager; hành vi cụ thể còn phụ thuộc cách gọi method (như self-invocation), cấu hình rollback và việc truy cập DB ngoài transaction. Không nên tạo transaction JPA thủ công trong một luồng đã do framework quản lý.

## 13. Các chế độ tạo, cập nhật và kiểm tra schema

Một trong những nhóm cấu hình có tác động lớn nhất đến dữ liệu là schema management.

### 13.1. Thuộc tính Hibernate `hibernate.hbm2ddl.auto`

| Giá trị | Hành vi khái quát | Môi trường thường phù hợp |
|---|---|---|
| `none` | Không yêu cầu Hibernate tự thao tác schema | Khi schema được quản lý bên ngoài |
| `validate` | Kiểm tra một phần sự tương thích giữa mapping và schema, báo lỗi nếu có sai khác được phát hiện | Staging/production đi cùng migration |
| `update` | Cố gắng cập nhật schema để phù hợp mapping | Demo hoặc trường hợp có kiểm soát; không phải công cụ migration an toàn |
| `create` | Tạo schema theo mapping, có thể xóa/recreate các đối tượng hiện có | DB thử nghiệm có thể xóa |
| `create-drop` | Tạo schema khi khởi tạo và cố gắng xóa khi đóng factory | Test hoặc demo cần DB tạm |

Không nên đặt `create`, `create-drop` hoặc `update` vào cấu hình production chỉ để “đỡ phải viết migration”. `update` không thay thế được kiểm soát đổi tên cột, chuyển đổi dữ liệu, index đặc thù, rollback, migration có thứ tự hay thay đổi được audit. `validate` giúp phát hiện một số sai khác, **không phải trình kiểm chứng đầy đủ mọi index, constraint và đặc tả nghiệp vụ**.

### 13.2. Thuộc tính chuẩn Jakarta Persistence

Jakarta Persistence có nhóm cấu hình schema-generation, trong đó:

```properties
jakarta.persistence.schema-generation.database.action=none
```

Các giá trị chuẩn thường gặp là `none`, `create`, `drop` và `drop-and-create`. Chúng **không tương đương một-một** với toàn bộ giá trị riêng của Hibernate: ví dụ `validate` là chế độ của `hibernate.hbm2ddl.auto`, không phải giá trị chuẩn của `jakarta.persistence.schema-generation.database.action`.

Không cấu hình hai cơ chế cùng lúc với ý định trái ngược, chẳng hạn một nơi yêu cầu `create-drop` còn nơi khác yêu cầu `validate`. Khi gặp tình huống đó, cần xác định cấu hình thực sự đang được provider áp dụng, sửa lại nguồn cấu hình thay vì dựa vào một giả định precedence.

### 13.3. Migration được quản lý độc lập

Quy trình production phổ biến:

```text
Thay đổi mapping/entity
         |
         v
Viết và review migration SQL / công cụ migration
         |
         v
Triển khai migration có kiểm soát
         |
         v
Khởi động ứng dụng Hibernate với validate hoặc none
         |
         v
Theo dõi truy vấn, lỗi dữ liệu và trạng thái ứng dụng
```

Flyway hoặc Liquibase là các công cụ migration thường được dùng; lựa chọn và quy trình triển khai tùy hệ thống. Việc Hibernate tự sinh DDL có thể hữu ích để tham khảo thiết kế ban đầu, nhưng schema production cần được kiểm soát như một phần của thay đổi cơ sở dữ liệu.

## 14. Dialect, SQL logging và thuộc tính tối ưu

### 14.1. Hibernate Dialect

Hibernate sử dụng dialect để tạo SQL phù hợp với hệ quản trị DB, ví dụ cách phân trang hoặc tên kiểu dữ liệu. Trong nhiều cấu hình Hibernate hiện đại, provider có thể tự nhận diện dialect từ JDBC metadata khi kết nối hợp lệ, nên **không cần luôn luôn đặt `hibernate.dialect`**.

Nếu cần chỉ định tường minh, hãy dùng lớp dialect tương ứng với **phiên bản Hibernate và DB đang chạy**. Đừng sao chép tên dialect từ một bài viết rất cũ mà chưa kiểm tra thư viện hiện tại. Cấu hình dialect cũng không sửa được URL sai, credential sai hoặc server DB không thể kết nối.

### 14.2. Log SQL với mức độ phù hợp

Hibernate cung cấp:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

`show_sql` chủ yếu phục vụ quan sát đơn giản trong lúc học; ứng dụng vận hành nên dùng logger có cấu trúc và mức log phù hợp. Ở Hibernate 6 trở lên, một số logger thường dùng là:

```text
org.hibernate.SQL           DEBUG  # câu SQL phát sinh
org.hibernate.orm.jdbc.bind TRACE  # giá trị tham số bind; chỉ bật có kiểm soát
```

Mức `TRACE` của tham số bind có thể ghi các giá trị nhạy cảm như email, định danh và dữ liệu nghiệp vụ, nên tránh bật trong production trừ khi đã kiểm soát phạm vi, thời gian và quyền xem log. Cú pháp cấu hình mức log phụ thuộc framework/logging backend (Spring Boot thường dùng `logging.level...`).

### 14.3. Một số tùy chọn hiệu năng

| Thuộc tính Hibernate | Vai trò | Điểm cần lưu ý |
|---|---|---|
| `hibernate.jdbc.batch_size` | Gộp các thao tác JDBC phù hợp thành batch | Một số chiến lược sinh khóa như `IDENTITY` hạn chế insert batching |
| `hibernate.order_inserts` | Sắp xếp thao tác insert để hỗ trợ batch | Có thêm chi phí sắp xếp, chỉ nên bật khi có lý do |
| `hibernate.order_updates` | Sắp xếp thao tác update để hỗ trợ batching | Phải đo hiệu quả và chú ý hành vi transaction |
| `hibernate.default_batch_fetch_size` | Gợi ý kích thước gom các lần tải lazy liên quan | Giúp giảm một số trường hợp N+1, không thay thế thiết kế query |
| `hibernate.generate_statistics` | Thu thập thống kê nội bộ của Hibernate | Tốt cho chẩn đoán, có thể phát sinh overhead |

Không bật mọi tùy chọn hiệu năng đồng loạt với kỳ vọng ứng dụng sẽ nhanh hơn. Số bản ghi, khóa chính, quan hệ, query plan, đặc điểm DB và cách sử dụng transaction quyết định mức hiệu quả thực tế.

## 15. Thứ tự ưu tiên cấu hình và cách xử lý xung đột

Các nguồn cấu hình khác nhau có thể cùng định nghĩa một thuộc tính:

```text
persistence.xml:                hibernate.show_sql=true
Java bootstrap overrides:       hibernate.show_sql=false
Spring application.properties:  spring.jpa.show-sql=false
Deployment environment:         DB_URL=...
```

Không có một **thứ tự ưu tiên duy nhất** áp dụng chung cho mọi tổ hợp Java SE JPA, Hibernate native, Spring Boot và Jakarta EE. Các quy tắc thực hành:

1. **Chọn một chủ sở hữu cấu hình:** nếu dùng Spring Boot, để Spring Environment và auto-configuration quản lý những giá trị thuộc Spring; nếu dùng Java SE thuần, xác định rõ file và map bootstrap.
2. **Tách nhóm thuộc tính:** JPA tiêu chuẩn, Hibernate vendor-specific, DataSource/pool và deployment secrets. Tránh đặt URL DB ở nhiều lớp không cần thiết.
3. **Quy định một nơi cho mỗi giá trị nhạy cảm hoặc có tác động mạnh:** DB URL, schema action, transaction mode, SQL bind logging và kích thước pool.
4. **Xác minh tại điểm khởi tạo:** cấu hình cần thể hiện đúng persistence unit, provider, datasource và schema mode dự kiến. Khi cần quan sát, log tên môi trường và tên cấu hình không nhạy cảm; không dump password hay toàn bộ property map.
5. **Ưu tiên cấu hình tường minh khi có xung đột:** bỏ bản khai báo trùng thay vì dựa vào thứ tự override phức tạp khó bảo trì.

Riêng với API `Persistence.createEntityManagerFactory(name, properties)`, map được truyền khi bootstrap thường ghi đè thuộc tính trùng tên đã khai báo trong `persistence.xml`. Với Hibernate `Configuration`, thứ tự `configure()`, `addProperties()` hoặc `setProperty()` có thể tác động đến kết quả. Với Spring Boot, hệ thống `PropertySource`, profile và nguồn cấu hình deployment có quy tắc precedence riêng cần tra theo phiên bản Boot.

### Ví dụ lỗi khó phát hiện: hai nguồn DB khác nhau

Giả sử `hibernate.cfg.xml` trỏ đến H2 local, còn Spring `application-prod.properties` trỏ đến PostgreSQL production. Nếu một class tự chạy `new Configuration().configure().buildSessionFactory()` bên trong ứng dụng Spring, class đó có thể kết nối H2, trong khi các repository Spring dùng PostgreSQL. Kết quả là các thao tác dữ liệu có vẻ “mất” hoặc không nhất quán. Cách sửa đúng là thống nhất luồng bootstrap và nguồn `DataSource` theo kiến trúc đã chọn.

## 16. Lỗi cấu hình thường gặp khi khởi động

| Biểu hiện | Nguyên nhân hay gặp | Hướng kiểm tra |
|---|---|---|
| `No Persistence provider for EntityManager named ...` | `persistence.xml` không trên classpath, sai tên unit, thiếu provider tương thích | Kiểm tra `META-INF/persistence.xml`, tên unit, dependency và họ `jakarta`/`javax` |
| Không nạp được `org.h2.Driver` hoặc `org.postgresql.Driver` | Thiếu JDBC driver khi chạy | Kiểm tra runtime dependency và classpath |
| `Unable to determine Dialect without JDBC metadata` hoặc lỗi metadata | Không thiết lập/không kết nối được JDBC, URL hoặc datasource sai | Xác nhận URL, driver, thông tin DB; chỉ đặt dialect tường minh khi có lý do |
| `Connection refused`, timeout, authentication failed | DB không sẵn sàng, network/DNS/port sai, mật khẩu sai, thiếu quyền | Kiểm tra kết nối từ đúng môi trường triển khai và quyền của tài khoản DB |
| Schema validation failure | Entity và bảng/cột/kiểu dữ liệu thực tế không khớp | Xem migration, naming strategy, schema/catalog và dialect |
| Hibernate tạo/xóa bảng ngoài dự kiến | `hbm2ddl.auto=create` hoặc `create-drop` bị áp vào DB lâu dài | Kiểm tra effective config, ngăn schema action nguy hiểm ở production |
| `No CurrentSessionContext configured` | Gọi `getCurrentSession()` nhưng chưa cấu hình context/transaction phù hợp | Sử dụng session/transaction theo cơ chế framework hoặc native bootstrap đã chọn |
| Nhiều kết nối/pool xuất hiện | Khởi tạo nhiều factory, cấu hình connection riêng song song `DataSource` | Xác định owner của factory và pool; chỉ tạo những tài nguyên thật sự cần |
| SQL không xuất hiện ở nơi mong đợi | Cấu hình log SQL ở sai tầng hoặc log level không phù hợp | Kiểm tra `show_sql`, backend logger, category, profile hiện hành |

Khi debug lỗi khởi động, nên kiểm tra theo thứ tự **cấu hình được tải → tên persistence unit/provider → JDBC driver → URL, quyền và kết nối DB → transaction/data source → schema và dialect**. Thứ tự này giúp khoanh vùng lỗi trước khi sửa entity hoặc truy vấn nghiệp vụ.

## 17. Bài tập thực hành: cùng một mô hình chạy ở hai môi trường

### Bối cảnh

Ứng dụng dùng entity `Product` và Hibernate làm JPA provider. Mục tiêu là cùng một code nghiệp vụ chạy ở local để thử nghiệm, rồi triển khai trên PostgreSQL mà không đưa mật khẩu vào source code.

### Giai đoạn A: local development

1. Tạo `Product` và `META-INF/persistence.xml` như phần 4.
2. Dùng H2 in-memory, `RESOURCE_LOCAL` và `hibernate.hbm2ddl.auto=create-drop` trên DB thử nghiệm.
3. Khởi tạo `EntityManagerFactory("inventory-pu")`, mở transaction, `persist()` một sản phẩm, commit, sau đó truy vấn lại.
4. Đóng `EntityManager` và `EntityManagerFactory` đúng vòng đời.

Ở giai đoạn này, mục tiêu là nhìn thấy entity được lưu và tránh nhầm lỗi cấu hình với lỗi CRUD. Không dùng database có dữ liệu quan trọng cho thử nghiệm với `create-drop`.

### Giai đoạn B: môi trường có PostgreSQL

1. Cấp quyền truy cập PostgreSQL và JDBC driver tương thích cho ứng dụng.
2. Đặt `DB_URL`, `DB_USER`, `DB_PASSWORD` từ cơ chế triển khai.
3. Tạo `Map<String,Object>` và truyền qua overload `createEntityManagerFactory("inventory-pu", overrides)` như phần 5.
4. Ghi đè schema mode thành `validate`; chuẩn bị schema bằng migration trước khi ứng dụng khởi chạy.
5. Kiểm tra kết nối, transaction, cấu trúc bảng/cột, thứ tự migration và chỉ giữ logging cần thiết.

Nếu thay bằng Spring Boot, sử dụng `spring.datasource.*`, `spring.jpa.hibernate.ddl-auto`, profile và `@Transactional` thay cho việc khởi tạo factory thủ công. Kết quả cuối cùng cần bảo đảm **logic nghiệp vụ không phải thay đổi chỉ vì môi trường có URL và secret khác**.

### Câu hỏi tự kiểm tra

1. Vì sao `hibernate.hbm2ddl.auto=validate` không thể thay thế Flyway/Liquibase?
2. Một chuỗi `${DB_PASSWORD}` trong `persistence.xml` của Java SE có tự đọc được environment variable không? Nếu không, làm thế nào để truyền giá trị?
3. Tại sao `spring.datasource.url` không tương đương với `hibernate.connection.url`, dù cả hai đều liên quan JDBC?
4. Khi Spring đã tạo `EntityManagerFactory`, điều gì có thể xảy ra nếu code khác tự tạo thêm `SessionFactory` từ `hibernate.cfg.xml`?
5. Nếu ứng dụng chạy được trên H2 nhưng thất bại trên PostgreSQL, những khác biệt nào về driver, dialect, schema, constraint và kiểu dữ liệu cần kiểm tra?

## 18. Tóm lược kiến thức và tài liệu tra cứu

Hibernate cho phép khai báo cấu hình từ thuộc tính Java, tệp XML/properties và các nguồn của môi trường triển khai. Điểm quyết định là **chọn một cơ chế bootstrap nhất quán**: JPA với `persistence.xml` và `EntityManagerFactory`; native Hibernate với `Configuration`/`SessionFactory`; hoặc framework quản lý `DataSource`, transaction và factory.

Các setting quan trọng thường nằm ở bốn nhóm: **kết nối**, **lifecycle/transaction**, **schema management** và **logging/hiệu năng**. Giữ URL và bí mật bên ngoài source code, tách cấu hình theo môi trường, thận trọng với `create`/`create-drop`/`update`, và kiểm tra nguồn thuộc tính có hiệu lực trước khi chẩn đoán lỗi entity.

Tài liệu gốc nên dùng để đối chiếu theo đúng phiên bản:

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — API chuẩn và `persistence.xml`.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/) — bootstrapping, settings, schema generation, logging và native API.
- [Hibernate ORM Configuration properties](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/cfg/AvailableSettings.html) — danh mục setting của Hibernate và tên khóa chính xác.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — placeholder, profile, property source và precedence.
- [Spring Boot Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html) — cấu hình `DataSource`, SQL và JPA/Hibernate.

> **Ghi chú phiên bản:** các ví dụ thuộc họ Jakarta Persistence và Hibernate ORM hiện đại. Tên property, hỗ trợ driver, cách bootstrap, quy tắc xử lý native settings và mặc định framework có thể thay đổi giữa Hibernate 5/6/7 và các đời Spring Boot. Hãy thống nhất dependency, namespace `jakarta.persistence.*` và tài liệu tham chiếu của phiên bản thực tế trước khi đưa cấu hình vào hệ thống đang vận hành.
