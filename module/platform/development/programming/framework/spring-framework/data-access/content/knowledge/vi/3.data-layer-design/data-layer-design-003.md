# @Repository và đăng ký thành phần trong Spring IoC Container

## 1. Bài học giải quyết vấn đề gì?

Trong một ứng dụng Spring, tầng dữ liệu thường có các lớp phụ trách truy cập cơ sở dữ liệu: thực thi SQL bằng Spring JDBC, gọi JPA `EntityManager` hoặc dùng một repository do Spring Data tạo ra. Một lớp viết đúng logic truy vấn vẫn **chưa đủ** để ứng dụng tự động sử dụng được lớp đó: Spring phải biết lớp cần quản lý, tạo bean và cung cấp bean cho các thành phần phụ thuộc.

Ví dụ, `CustomerService` cần `CustomerRepository` để tìm khách hàng:

~~~text
CustomerService
      │ phụ thuộc vào CustomerRepository
      ▼
CustomerRepository (giao diện)
      ▲
      │ triển khai
JdbcCustomerRepository ----> JdbcTemplate ----> DataSource ----> Database
      ^
      │ @Repository + component scanning
Spring IoC Container tạo, quản lý và tiêm bean
~~~

Hai câu hỏi quan trọng:

1. **Vai trò của `@Repository` là gì?** Annotation này biểu thị một thành phần của tầng truy cập dữ liệu, là một chuyên biệt của `@Component` và có thể là điểm nhận diện cho cơ chế chuyển đổi ngoại lệ persistence.
2. **Làm thế nào đối tượng đó thực sự trở thành Spring bean?** Cần có cơ chế đăng ký bean, thường là component scanning hoặc khai báo rõ bằng `@Bean`. Việc viết `@Repository` trên một class mà Spring không quét/đăng ký **không tự tạo ra bean**.

Sau bài này, bạn cần phân biệt được annotation metadata, bean definition, bean instance, dependency injection, exception translation và repository do Spring Data sinh ra.

## 2. `@Repository` là gì và khác gì `@Component`?

`@Repository` thuộc package `org.springframework.stereotype`. Nó thường được đặt trên **lớp triển khai truy cập dữ liệu** (DAO/repository), ví dụ:

~~~java
@Repository
public class JdbcCustomerRepository implements CustomerRepository {
    // Các phương thức dùng JdbcTemplate để truy cập dữ liệu
}
~~~

Về mặt stereotype, `@Repository` được meta-annotate bằng `@Component`. Nhờ đó, component scanner mặc định có thể nhận diện lớp gắn `@Repository` giống như các lớp gắn `@Component`. Tuy nhiên tên annotation còn biểu đạt **trách nhiệm kiến trúc**: đây là thành phần ở tầng persistence/data access.

| Annotation | Thông thường dùng cho | Liên quan đến đăng ký bean |
| --- | --- | --- |
| `@Component` | Thành phần Spring chung không thuộc stereotype chuyên biệt | Có thể được component scan tìm thấy |
| `@Repository` | Tầng truy cập dữ liệu, DAO, persistence adapter | Là `@Component` chuyên biệt; có vai trò trong exception translation |
| `@Service` | Nghiệp vụ, điều phối use case | Là `@Component` chuyên biệt |
| `@Controller` / `@RestController` | Tầng web/controller | Được Spring nhận diện và có thêm semantics cho web |
| `@Bean` | Phương thức factory cung cấp một bean | Đăng ký qua cấu hình có phương thức đó |
| `@Entity` (JPA) | Kiểu dữ liệu thực thể được ORM ánh xạ | **Không** biến entity thành component bean theo cách của `@Repository` |

Không dùng `@Repository` chỉ để “Spring tìm ra class” khi đó là logic nghiệp vụ. Sử dụng đúng stereotype giúp người đọc và các công cụ/AOP phân biệt vai trò. Bản thân `@Repository` **không** triển khai SQL, tự kết nối database, mở transaction, tạo bảng, tự động xây CRUD hoặc bảo đảm phương thức thread-safe.

**Ba lớp ý nghĩa khác nhau:**

- **Annotation trên mã nguồn:** metadata mô tả vai trò của class.
- **Bean definition trong container:** thông tin Spring lưu về cách tạo bean, phạm vi, tên, dependencies.
- **Bean instance:** đối tượng thực tế được Spring khởi tạo/quản lý, có thể được bọc proxy tùy cấu hình.

Gắn annotation là một điều kiện nhận diện thông dụng; có bean definition là điều kiện để container quản lý đối tượng. Không nên suy luận “có annotation = đã được inject ở mọi chỗ”.

## 3. Đăng ký `@Repository` vào container bằng component scanning

### 3.1. Cơ chế từ class đến bean

Khi cấu hình `@ComponentScan` bao gồm package chứa lớp repository, Spring tìm các class thích hợp trên classpath, áp dụng bộ lọc mặc định, đăng ký bean definition và sau đó tạo bean khi cần theo lifecycle/scope.

~~~java
@Configuration
@ComponentScan(basePackages = "com.example.shop")
public class AppConfig {
}
~~~

Nếu `JdbcCustomerRepository` nằm dưới `com.example.shop.data`, nó là ứng viên được scan. Nếu nó nằm ngoài các package được quét, chỉ gắn `@Repository` sẽ không giúp Spring tự thấy lớp.

Một cách cấu hình ít phụ thuộc chuỗi package hơn là dùng marker class:

~~~java
@Configuration
@ComponentScan(basePackageClasses = JdbcCustomerRepository.class)
class AppConfig {
}
~~~

Ở đây Spring lấy package của `JdbcCustomerRepository` làm gốc quét. Nếu service ở package khác không nằm bên dưới package này, cần mở rộng phạm vi quét hoặc đăng ký service riêng. Chọn gói gốc có chủ đích để tránh quét những class không liên quan.

**Quy trình logic:**

~~~text
Ứng dụng khởi tạo ApplicationContext
    │
    ├─ đọc @Configuration / các nguồn cấu hình
    │
    ├─ xử lý @ComponentScan
    │      └─ phát hiện class @Repository (qua meta-annotation @Component)
    │
    ├─ đăng ký BeanDefinition, ví dụ "jdbcCustomerRepository"
    │
    ├─ giải quyết phụ thuộc constructor (JdbcTemplate, ...)
    │
    └─ khởi tạo/hoàn thiện bean, áp dụng post-processor/proxy khi có
           └─ CustomerService nhận một CustomerRepository bean
~~~

Đây là mô hình khái niệm; thời điểm tạo bean có thể thay đổi bởi lazy initialization, scope hoặc cấu hình cụ thể.

### 3.2. Trong Spring Boot

`@SpringBootApplication` bao gồm component scanning. Mặc định, package của class ứng dụng và các subpackage là vùng quét tự nhiên.

~~~text
com.example.shop
├── ShopApplication.java        // @SpringBootApplication
├── service
│   └── CustomerService.java    // @Service
└── data
    └── JdbcCustomerRepository.java // @Repository
~~~

Tổ chức này thường hoạt động mà không cần ghi `@ComponentScan` tường minh. Nếu đặt `ShopApplication` trong `com.example.shop.web` nhưng repository ở `com.example.shop.data` (package anh em), scanning mặc định có thể bỏ sót repository. Cách khắc phục phù hợp thường là đặt ứng dụng trong package gốc chung hoặc khai báo phạm vi scan rõ ràng, thay vì thêm annotation lặp lại trên repository.

`@ComponentScan` chỉ quyết định ứng viên component được phát hiện; nó **không** tự cấu hình `DataSource`, tạo schema hay bật JPA. Trong Boot, việc cung cấp `DataSource`, `JdbcTemplate`, entity manager... phụ thuộc vào starter, auto-configuration và properties tương ứng.

### 3.3. Tên bean và phạm vi sống

Với lớp:

~~~java
@Repository
public class JdbcCustomerRepository {
}
~~~

tên bean mặc định thường là `jdbcCustomerRepository` khi dùng bean-name generator chuẩn. Có thể đặt tên rõ ràng:

~~~java
@Repository("customerSqlRepository")
public class JdbcCustomerRepository {
}
~~~

Tên chỉ là định danh bean; chức năng truy cập dữ liệu do code và các collaborator quyết định. Scope mặc định của stereotype component là `singleton` **trong mỗi Spring container**, không có nghĩa một instance dùng chung cho mọi JVM hoặc mọi deployment.

Một singleton repository nên giữ các dependency ổn định (chẳng hạn `final JdbcTemplate`) thay vì giữ trạng thái riêng của từng request trong field mutable. `JdbcTemplate` được thiết kế để chia sẻ sau khi cấu hình; `Connection` hoặc JPA `EntityManager` có yêu cầu vòng đời khác và không nên tùy tiện giữ trong field của singleton repository.

Có thể đặt `@Scope("prototype")` khi thật sự cần, nhưng đó không phải giải pháp mặc định cho truy cập dữ liệu hoặc đồng thời. Thay đổi scope cũng làm thay đổi cách quản lý vòng đời và phụ thuộc.

## 4. Đăng ký bean tường minh bằng `@Bean`

Component scanning không phải con đường duy nhất. Một class repository có thể không có `@Repository` nhưng vẫn trở thành bean nếu được một phương thức `@Bean` trả về và configuration được nạp:

~~~java
public final class JdbcCustomerRepository implements CustomerRepository {
    private final JdbcTemplate jdbc;

    public JdbcCustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Triển khai các phương thức CustomerRepository...
}
~~~

~~~java
@Configuration
public class RepositoryConfig {
    @Bean
    public CustomerRepository customerRepository(JdbcTemplate jdbc) {
        return new JdbcCustomerRepository(jdbc);
    }
}
~~~

**Hai đoạn trên minh họa hình thức đăng ký tường minh; class đầy đủ có thể chạy được ở mục 7.** Spring gọi factory method để tạo bean `customerRepository` và tự cung cấp `JdbcTemplate` nếu có bean phù hợp. Lưu ý: trong trường hợp class triển khai **không có** `@Repository`, chỉ dùng `@Bean` để đăng ký thì bean không tự mang stereotype `@Repository` phục vụ các cơ chế nhắm vào annotation đó. Muốn cơ chế exception translation dựa trên stereotype thì cần cấu hình và đánh dấu phù hợp.

Trường hợp nên chọn `@Bean`: tạo đối tượng từ thư viện bên thứ ba không sửa được annotation, tạo adapter cần cấu hình đặc biệt, hoặc muốn kiểm soát cụ thể factory. Không cần ép mọi thành phần qua scanning.

**Tránh đăng ký trùng:** nếu vừa scan `@Repository JdbcCustomerRepository` vừa khai báo `@Bean` tạo một `JdbcCustomerRepository` khác, container có thể có **hai bean cùng kiểu**. Khi inject một `CustomerRepository` mà không có tiêu chí phân biệt, Spring có thể báo lỗi không xác định được ứng viên. Đăng ký bean theo một chiến lược rõ ràng cho mỗi implementation, hoặc chỉ định bean khi có nhiều implementation có chủ đích.

Các cơ chế đăng ký khác như `@Import`, cấu hình XML, API đăng ký bean definition hay đăng ký lập trình cũng tồn tại. Chúng đều cần được tích hợp vào đúng `ApplicationContext`; không nên nhầm với việc tạo đối tượng bằng `new` trong mã nghiệp vụ.

## 5. Dependency injection: vì sao service nhận được repository?

Giả sử có giao diện:

~~~java
public interface CustomerRepository {
    Customer findById(long id);
}
~~~

và một implementation đã được đăng ký bằng `@Repository` hoặc `@Bean`. Service nên phụ thuộc vào abstraction:

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer load(long id) {
        return repository.findById(id);
    }
}
~~~

Spring nhìn vào tham số constructor và chọn bean tương thích với kiểu `CustomerRepository`. Với **một constructor duy nhất**, Spring không yêu cầu ghi `@Autowired` trên constructor. Constructor injection có ưu điểm: dependency bắt buộc hiển thị rõ, có thể lưu trong field `final`, và dễ tạo service trong unit test bằng fake repository.

Nếu làm:

~~~java
CustomerService service = new CustomerService(new JdbcCustomerRepository(...));
~~~

thì đối tượng tạo bằng `new` nằm ngoài quy trình Spring quản lý (trừ trường hợp bạn chủ động đăng ký/đưa nó vào container). Nó vẫn là Java object bình thường nhưng không được Spring tự động áp dụng các cơ chế bean post-processing/proxy cho instance ấy.

### Nhiều bean cùng giao diện

Giả sử có `JdbcCustomerRepository` và `CachedCustomerRepository` đều là Spring beans thực thi `CustomerRepository`. Nếu Spring không chọn được một ứng viên duy nhất, injection theo kiểu đơn thuần không đủ.

**Chọn bằng qualifier:**

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(
            @Qualifier("jdbcCustomerRepository") CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

Đoạn này minh họa và giả định tên bean thực tế đúng `jdbcCustomerRepository`. Ngoài `@Qualifier`, có thể đánh dấu một implementation bằng `@Primary` nếu đó là mặc định hợp lý. Tránh dựa vào thứ tự scan; không dùng tên bean như cách sửa tạm cho kiến trúc dependency mơ hồ.

**Phân biệt lỗi thường gặp:**

- `NoSuchBeanDefinitionException`: không tìm thấy bean tương ứng ở điểm tra cứu trực tiếp, hoặc không có ứng viên cho dependency.
- `UnsatisfiedDependencyException`: bean cần khởi tạo không được đáp ứng dependency; nguyên nhân sâu hơn có thể là repository không được scan hoặc `JdbcTemplate` chưa được cung cấp.
- `NoUniqueBeanDefinitionException`: nhiều bean cùng kiểu, không đủ thông tin để chọn một.
- Lỗi tạo bean do SQL/DB khi khởi tạo: repository đã có thể được đăng ký đúng, nhưng dependency hoặc logic initialization gặp lỗi; không quy mọi lỗi startup thành lỗi component scan.

Khi debug, xác định package được scan, tên/kiểu bean, có `@Bean` nào khác, dependency sẵn có và stack trace gốc trước khi đổi annotation.

## 6. `@Repository` và cơ chế chuyển đổi ngoại lệ truy cập dữ liệu

Một lợi ích kiến trúc của `@Repository` là nó là **điểm đánh dấu** để Spring có thể áp dụng cơ chế chuyển đổi ngoại lệ từ công nghệ lưu trữ sang họ `DataAccessException`.

Ví dụ một nhà cung cấp ORM có thể ném ngoại lệ đặc thù. Nếu tầng service luôn phải catch loại exception của từng provider, service bị phụ thuộc trực tiếp vào công nghệ persistence. Spring hỗ trợ abstraction `DataAccessException`, trong đó có các kiểu như `DataIntegrityViolationException`, `DuplicateKeyException`, `DataAccessResourceFailureException`...

Tuy nhiên cần hiểu chính xác **điều kiện áp dụng**, tránh khẳng định `@Repository` tự làm mọi thứ:

1. Có bean repository được Spring quản lý.
2. Có hạ tầng exception translation thích hợp, ví dụ `PersistenceExceptionTranslationPostProcessor`.
3. Có một hoặc nhiều `PersistenceExceptionTranslator` phù hợp có thể hiểu exception do provider ném.
4. Lời gọi đi qua bean/proxy được hạ tầng đó áp dụng; không phải một đối tượng tự tạo bằng `new` nằm ngoài container.
5. Exception có thể chuyển đổi được mới được chuyển sang `DataAccessException`. Exception nghiệp vụ `IllegalArgumentException` bất kỳ không tự biến thành lỗi database.

Với Java config, cơ chế post-processor có thể được khai báo như sau khi chưa có hạ tầng tương ứng:

~~~java
@Configuration
class PersistenceConfig {
    @Bean
    static PersistenceExceptionTranslationPostProcessor translationPostProcessor() {
        return new PersistenceExceptionTranslationPostProcessor();
    }
}
~~~

*Đây là đoạn cấu hình riêng dùng `org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor`; nó chỉ có tác dụng mong muốn khi có translator phù hợp. Không thêm trùng nếu framework/starter đã cấu hình cơ chế này.*

**Phân biệt trường hợp Spring JDBC:** `JdbcTemplate` đã có cơ chế dịch lỗi `SQLException` sang `DataAccessException` trong chính quá trình thực thi JDBC, **kể cả khi class gọi nó không mang `@Repository`**. Bởi vậy, thấy exception đã được dịch trong demo JDBC không chứng minh `@Repository` tự thực hiện việc dịch. Trong demo, `@Repository` chủ yếu làm rõ vai trò và cho component scanning phát hiện class.

**Phân biệt với giao dịch:** được đăng ký `@Repository` không tự tạo transaction bao quanh toàn bộ use case. `@Transactional` và transaction manager xử lý ranh giới commit/rollback; việc exception là checked/unchecked hoặc có bị catch cũng có thể ảnh hưởng quy tắc rollback. Một database exception có thể được dịch, nhưng phần thay đổi dữ liệu vẫn cần transaction boundary phù hợp.

## 7. Demo đầy đủ: scan `@Repository`, inject vào `@Service` và gọi database

Demo này sử dụng **Java 17+**, **Maven 3.9+**, Spring Framework 6.1.14, Spring JDBC và H2 in-memory. Đây là một ứng dụng Spring Framework tối giản, **không dùng Spring Boot**, để thấy rõ bean đến từ đâu. Spring context khởi tạo từ `@Configuration` và quét package của implementation.

### 7.1. Cấu trúc

~~~text
repository-container-demo/
├── pom.xml
└── src/main/java/demo/
    ├── AppConfig.java
    ├── Customer.java
    ├── CustomerRepository.java
    ├── JdbcCustomerRepository.java
    ├── CustomerService.java
    └── RepositoryDemo.java
~~~

### 7.2. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>repository-container-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File `AppConfig.java`: cung cấp bean nền và bật scanning

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
@ComponentScan(basePackageClasses = JdbcCustomerRepository.class)
public class AppConfig {

    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:repository_demo;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource source) {
        return new JdbcTemplate(source);
    }
}
~~~

Hai phương thức `@Bean` tạo `DataSource` và `JdbcTemplate`. Annotation `@ComponentScan` lấy package `demo` (từ `JdbcCustomerRepository.class`) và tìm `@Repository`/`@Service` trong đó. `DriverManagerDataSource` chỉ thích hợp cho demo vì không pool connection; trong ứng dụng thực tế thường cần pool.

### 7.4. File `Customer.java`: model Java

~~~java
package demo;

public record Customer(long id, String name) {
}
~~~

`Customer` ở đây là Java record đơn giản. Nó không được chú thích `@Repository` hoặc `@Entity`; repository chịu trách nhiệm tạo đối tượng này từ dữ liệu truy vấn.

### 7.5. File `CustomerRepository.java`: abstraction của tầng dữ liệu

~~~java
package demo;

import java.util.Optional;

public interface CustomerRepository {
    void save(Customer customer);
    Optional<Customer> findById(long id);
    int count();
}
~~~

Giao diện này **không** tự động trở thành Spring bean chỉ vì đặt tên là `CustomerRepository`. Demo sẽ đăng ký **implementation** qua `@Repository`. Điều này khác với một giao diện mở rộng `JpaRepository`/`CrudRepository` được Spring Data hạ tầng chuyên dụng sinh proxy.

### 7.6. File `JdbcCustomerRepository.java`: implementation do Spring quét

~~~java
package demo;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcCustomerRepository implements CustomerRepository {

    private final JdbcTemplate jdbc;

    public JdbcCustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void save(Customer customer) {
        jdbc.update(
                "INSERT INTO customer(id, full_name) VALUES (?, ?)",
                customer.id(),
                customer.name());
    }

    @Override
    public Optional<Customer> findById(long id) {
        List<Customer> customers = jdbc.query(
                "SELECT id, full_name FROM customer WHERE id = ?",
                (rs, rowNum) -> new Customer(
                        rs.getLong("id"),
                        rs.getString("full_name")),
                id);
        return customers.stream().findFirst();
    }

    @Override
    public int count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer", Integer.class);
    }
}
~~~

Điểm cần quan sát:

- `@Repository` giúp Spring scan và đăng ký class theo stereotype data access.
- Constructor nhận bean `JdbcTemplate`, không tự `new JdbcTemplate`.
- `JdbcTemplate` xử lý vòng đời JDBC và dịch ngoại lệ SQL; code repository chỉ viết SQL/mapping.
- `RowMapper` chuyển một hàng thành `Customer`; việc mapping là trách nhiệm khác với đăng ký bean.
- Tham số `?` cho phép bind giá trị thay vì nối chuỗi SQL.

### 7.7. File `CustomerService.java`: inject repository theo giao diện

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public String customerName(long id) {
        return repository.findById(id)
                .orElseThrow()
                .name();
    }
}
~~~

Không cần `@Autowired` trên constructor duy nhất. Service không phụ thuộc trực tiếp `JdbcCustomerRepository` hay `JdbcTemplate`, nên có thể thay implementation và viết unit test riêng dễ hơn.

### 7.8. File `RepositoryDemo.java`: khởi động Spring container và quan sát

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

public class RepositoryDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "CREATE TABLE customer (" +
                    "id BIGINT PRIMARY KEY, " +
                    "full_name VARCHAR(100) NOT NULL)");

            CustomerRepository repository = context.getBean(CustomerRepository.class);
            CustomerService service = context.getBean(CustomerService.class);

            repository.save(new Customer(1L, "An"));
            System.out.println("Repository bean: " +
                    String.join(", ",
                            context.getBeanNamesForType(CustomerRepository.class)));
            System.out.println("Customer: " + service.customerName(1L));

            try {
                repository.save(new Customer(1L, "Duplicate"));
            } catch (DataAccessException expected) {
                System.out.println("Duplicate key: caught DataAccessException");
            }

            System.out.println("Count: " + repository.count());
        }
    }
}
~~~

Tại thư mục có `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RepositoryDemo
~~~

**Các dòng do ứng dụng in ra:**

~~~text
Repository bean: jdbcCustomerRepository
Customer: An
Duplicate key: caught DataAccessException
Count: 1
~~~

H2 từ chối `INSERT` trùng primary key. `JdbcTemplate` chuyển lỗi SQL sang ngoại lệ thuộc họ `DataAccessException`, vì vậy nhánh `catch` in dòng thông báo và chương trình tiếp tục. Bảng chỉ có một dòng.

Giải thích theo đúng thứ tự chạy:

1. `AnnotationConfigApplicationContext(AppConfig.class)` nạp cấu hình.
2. `@ComponentScan` tìm `JdbcCustomerRepository` và `CustomerService`; Spring có bean `jdbcCustomerRepository` (tên mặc định).
3. Spring tạo `DataSource`, `JdbcTemplate` theo `@Bean` và tiêm `JdbcTemplate` cho repository.
4. Spring tiêm repository (qua interface `CustomerRepository`) cho service.
5. `RepositoryDemo` lấy các bean từ context, tạo bảng và gọi service/repository. `getBeanNamesForType` xác nhận implementation đã được đăng ký, còn `Count: 1` cho thấy không có bản ghi duplicate.
6. `try-with-resources` đóng Spring context khi hoàn tất. Mẫu khởi động context thủ công này phục vụ việc học; ứng dụng Boot thường do `SpringApplication.run(...)` khởi động và quản lý lifecycle.

**Tính chất của ví dụ:** bản demo không thiết lập transaction cho nhiều thao tác nghiệp vụ, không xử lý trường hợp đồng thời và không nhằm mô phỏng kiến trúc production. Nó minh họa chính xác việc scan/register/inject repository và cách `JdbcTemplate` phát sinh `DataAccessException`.

## 8. Thử nghiệm thay đổi cấu hình để hiểu cơ chế

### Thử nghiệm A: bỏ `@Repository`

Bỏ annotation trên `JdbcCustomerRepository`, giữ `@ComponentScan` và không thêm `@Bean` nào thay thế. Class thông thường không còn được mặc định nhận diện như component; `CustomerService` vẫn cần `CustomerRepository`. Khi khởi động context, Spring sẽ không thể thỏa mãn dependency đó và báo lỗi tạo bean (thường `UnsatisfiedDependencyException`, với nguyên nhân sâu hơn là thiếu ứng viên `CustomerRepository`).

**Bài học:** annotation đóng vai trò nhận diện **khi đang sử dụng scanning**. Class có constructor hợp lệ chưa đủ để Spring tạo bean.

### Thử nghiệm B: dùng `@Bean` thay cho quét implementation

Giả sử muốn chọn cấu hình tường minh. Bỏ `@Repository` khỏi implementation và thay phần đăng ký implementation bằng phương thức trong `@Configuration`:

~~~java
@Bean
public CustomerRepository customerRepository(JdbcTemplate jdbc) {
    return new JdbcCustomerRepository(jdbc);
}
~~~

Đồng thời bảo đảm `CustomerService` vẫn được scan hoặc đăng ký bằng cách khác. Trong cấu hình này bean `customerRepository` được tạo từ factory method, dù implementation không còn stereotype annotation. Đừng bật song song đường đăng ký scan implementation cũ và `@Bean` nếu chỉ muốn một bean.

**Bài học:** **đăng ký bean** là kết quả cần đạt; `@Repository` là một cách giúp scanner nhận diện implementation và mang semantics của tầng dữ liệu.

### Thử nghiệm C: đặt implementation ngoài package quét

Chuyển repository sang `com.example.external.data` nhưng vẫn chỉ quét `demo`. Dù vẫn gắn `@Repository`, scanner không duyệt package ngoài phạm vi. Khôi phục bằng cách cấu hình package đúng hoặc `@Import`/`@Bean`/cơ chế đăng ký tường minh. Đừng chữa bằng cách tăng phạm vi scan lên toàn bộ classpath một cách vô tội vạ.

**Bài học:** **phạm vi scan** là đầu vào của phát hiện component; annotation không thay đổi phạm vi scan.

### Thử nghiệm D: thêm implementation thứ hai

Có thêm một bean khác cùng triển khai `CustomerRepository`. Constructor `CustomerService(CustomerRepository)` lúc này có thể không phân giải được ứng viên. Quyết định rõ implementation nào là mặc định bằng `@Primary` hoặc chỉ định `@Qualifier` tại injection point. Nếu muốn có cả hai, có thể inject `List<CustomerRepository>` hoặc `Map<String, CustomerRepository>` và thiết kế logic lựa chọn rõ ràng.

**Bài học:** việc inject theo type cần một ứng viên có thể xác định, không phải cứ có hai bean là Spring tự chọn đúng theo tên class.

### Thử nghiệm E: ngoại lệ persistence và annotation

Nếu code repository dùng `JdbcTemplate`, bỏ `@Repository` nhưng đăng ký repository qua `@Bean`, SQL duplicate vẫn có thể sinh `DataAccessException`: đây là cơ chế của `JdbcTemplate`. Ngược lại, một repository tự ném `RuntimeException` bất kỳ sẽ không được tự động chuyển đổi chỉ vì bạn gắn `@Repository`. Phải có post-processor và translator thích hợp, và translator chỉ xử lý loại ngoại lệ nó hiểu.

**Bài học:** đừng kiểm tra exception translation bằng cách chỉ đếm annotation; kiểm tra hạ tầng và ngoại lệ gốc.

## 9. `@Repository` thường bị nhầm với Spring Data repository

Trong Spring Data, có thể khai báo:

~~~java
public interface CustomerJpaRepository
        extends JpaRepository<CustomerEntity, Long> {
}
~~~

Đây là **mã minh họa**; cần `spring-data-jpa`, entity `CustomerEntity` hợp lệ, entity manager, transaction/persistence configuration và hạ tầng bật repository scanning. Cơ chế của Spring Data tìm repository interface và tạo một proxy bean triển khai giao diện. Nó khác với component scanning một implementation tự viết như `JdbcCustomerRepository` trong demo.

| Trường hợp | Cái được phát hiện/đăng ký | Ai cung cấp implementation? |
| --- | --- | --- |
| Class `@Repository JdbcCustomerRepository` | Concrete component qua `@ComponentScan` | Chính class do lập trình viên viết |
| Phương thức `@Bean CustomerRepository ...` | Bean definition do factory method cung cấp | Lập trình viên tạo đối tượng |
| Interface mở rộng `JpaRepository` | Spring Data repository infrastructure nhận diện interface | Spring Data tạo repository proxy |
| JPA `@Entity CustomerEntity` | Metadata ánh xạ ORM | JPA provider quản lý entity, không phải tự động Spring component bean |
| Chỉ viết interface tên `CustomerRepository` | Không đủ để tạo bean | Chưa có cơ chế cung cấp |

`@EnableJpaRepositories` (hoặc cấu hình tương đương từ Spring Boot auto-configuration) nhằm bật/tùy biến việc tạo Spring Data JPA repository; không phải annotation bắt buộc cho mọi class `@Repository` dùng JDBC hoặc DAO thủ công.

Không suy luận rằng một class chỉ vì tên có hậu tố `Repository` thì Spring Data sẽ viết sẵn `save`, `findAll` hoặc tạo bảng. Các phương thức đó đến từ giao diện Spring Data và hạ tầng tương ứng, hoặc từ code bạn tự viết.

## 10. Lỗi phổ biến và cách xử lý

| Hiện tượng | Câu hỏi kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `CustomerService` không khởi tạo vì thiếu repository | Implementation có `@Repository` hoặc `@Bean`? Có nằm trong scan base package? | Đăng ký bean bằng đúng cơ chế, sửa phạm vi scan |
| Có `@Repository` nhưng `getBean(...)` không tìm thấy | Class có nằm trên runtime classpath? Context đang hỏi có phải context đăng ký nó? | Xác minh packaging, cấu hình và context đang hoạt động |
| Nhiều bean type `CustomerRepository` | Vừa scan vừa có `@Bean`, hoặc nhiều implementation? | Bỏ đăng ký trùng không mong muốn, dùng `@Qualifier`/`@Primary` nếu nhiều bean có chủ đích |
| `@Autowired` field trong object tự `new` là null | Object được container tạo hay mã ứng dụng tạo trực tiếp? | Dùng constructor injection và lấy bean qua context/DI |
| Ném ngoại lệ native persistence | Có `PersistenceExceptionTranslationPostProcessor` và translator phù hợp? Lời gọi đi qua Spring bean? | Cấu hình translation cho công nghệ đang dùng |
| `JdbcTemplate` ném `DataAccessException` dù không có `@Repository` | Có phải exception được dịch bởi chính `JdbcTemplate`? | Phân biệt nguồn exception translation |
| Truy vấn chạy nhưng dữ liệu commit sai phạm vi | Có transaction boundary nghiệp vụ và transaction manager đúng không? | Thiết kế giao dịch riêng ở service; `@Repository` không thay thế transaction |
| Bean được tạo nhưng lỗi kết nối DB | `DataSource`, credentials, URL, schema, migration có đúng không? | Chẩn đoán tầng cấu hình database thay vì đổi stereotype |
| Repository singleton gây lỗi đồng thời | Có giữ dữ liệu request/`Connection` trong mutable field không? | Giữ dependency thread-safe, xử lý state theo scope đúng |
| Injection phụ thuộc implementation cụ thể và khó test | Service có thể phụ thuộc interface không? | Tách interface, inject qua constructor, dùng fake khi unit test |

**Nguyên tắc thiết kế ở tầng dữ liệu:**

- Đặt repository vào package có thể tìm được qua scan, có trách nhiệm truy cập dữ liệu rõ ràng.
- Dùng `@Repository` cho class persistence adapter; dùng `@Service` cho use case/transaction orchestration.
- Ưu tiên constructor injection; để service phụ thuộc abstraction có ý nghĩa.
- Đăng ký các đối tượng hạ tầng (`DataSource`, `JdbcTemplate`, JPA-related beans) một cách rõ ràng; không cho rằng `@Repository` tạo chúng.
- Hạn chế mutable state trong singleton repository; giữ vòng đời connection/session đúng theo công nghệ.
- Không nhầm exception translation, rollback, validation và mapping. Mỗi cơ chế giải quyết một trách nhiệm riêng.
- Kiểm thử ứng dụng khởi động được và service thực sự gọi được repository; không chỉ kiểm tra annotation tồn tại trong source.

## 11. Câu hỏi tự kiểm tra

**1. Đã thêm `@Repository` nhưng Spring không inject được. Nguyên nhân đầu tiên nên tìm ở đâu?**  
Kiểm tra scanning/bean registration, package và dependency cần thiết. `@Repository` không đăng ký bean nếu không có cơ chế đưa class vào context.

**2. Có bắt buộc phải dùng `@Repository` để Spring inject class truy cập dữ liệu không?**  
Không. Một bean do `@Bean` tạo ra vẫn được inject bình thường. Tuy nhiên stereotype `@Repository` có ý nghĩa kiến trúc và cho hạ tầng exception translation nhận diện khi được cấu hình.

**3. Một interface `CustomerRepository` tự viết có được Spring tự tạo implementation như `JpaRepository` không?**  
Không. Phải có concrete implementation/`@Bean`, hoặc dùng đúng giao diện và hạ tầng Spring Data được hỗ trợ.

**4. `@Repository` tự biến mọi exception của lớp thành `DataAccessException`?**  
Không. Cần hạ tầng post-processor và translator thích hợp; chỉ những ngoại lệ được translator nhận diện mới có thể được chuyển đổi. `JdbcTemplate` có cơ chế dịch ngoại lệ riêng.

**5. Vì sao constructor injection thường phù hợp với repository?**  
Nó làm rõ dependency bắt buộc, hỗ trợ field `final`, giảm phụ thuộc vào container trong unit test và giúp lỗi thiếu bean xuất hiện khi khởi tạo.

**6. Lớp `@Repository` mặc định có bean scope gì?**  
Thường là `singleton` trong mỗi context. Điều đó không làm mọi đối tượng kết nối hoặc state mà repository sử dụng trở thành thread-safe.

**7. Nếu có hai implementation của `CustomerRepository`, Spring có tự chọn implementation JDBC không?**  
Không nhất thiết. Hãy kiểm tra quy tắc phân giải dependency, dùng `@Primary` hoặc `@Qualifier` khi cần chọn rõ ràng.

**8. Nếu thêm `@Transactional` trên service, có thể bỏ `@Repository` được không?**  
Đây là hai trách nhiệm khác nhau. Transaction quản lý ranh giới commit/rollback; repository bean vẫn phải được đăng ký theo một trong các cơ chế hợp lệ.

## 12. Tài liệu tham khảo

- [Spring Framework – Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): stereotype, `@ComponentScan`, tên và scope của bean.
- [Spring Framework – General ORM Integration Considerations](https://docs.spring.io/spring-framework/reference/data-access/orm/general.html): `@Repository` và persistence exception translation.
- [Spring Boot – Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): đặt main class tại package gốc để scan phù hợp.
- [Spring Boot – Spring Beans and Dependency Injection](https://docs.spring.io/spring-boot/reference/using/spring-beans-and-dependency-injection.html): constructor injection và bean discovery.

**Kết luận:** `@Repository` cho biết class có vai trò truy cập dữ liệu và có thể được nhận diện bởi component scanning/exception translation. Container chỉ quản lý class khi đã đăng ký **bean definition** qua scanning, `@Bean` hoặc cơ chế tương đương. Khi Spring đã quản lý bean, dependency injection mới cung cấp repository cho service; khả năng chạy SQL, mapping, transaction và chuyển đổi ngoại lệ tiếp tục phụ thuộc vào các thành phần chuyên trách.
