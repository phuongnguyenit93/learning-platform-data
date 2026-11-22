# Tách hợp đồng truy cập dữ liệu khỏi cách triển khai

## 1. Vấn đề thiết kế: ai phải biết dữ liệu được lưu ở đâu?

Trong một ứng dụng Spring, tầng nghiệp vụ cần những thao tác như “tìm khách hàng theo mã”, “tạo đơn hàng”, “kiểm tra tài khoản có tồn tại”. Những thao tác đó có **ý nghĩa nghiệp vụ**, còn `SELECT`, `ResultSet`, `EntityManager`, tên bảng, lệnh gọi HTTP tới dịch vụ dữ liệu và cách mở kết nối chỉ là **cách hiện thực**.

Nếu service phụ thuộc trực tiếp vào chi tiết lưu trữ, thay đổi công nghệ hoặc cách tổ chức bảng thường kéo theo sửa logic nghiệp vụ:

```java
// Ví dụ phản diện: đoạn trích, không phải chương trình Java độc lập.
class CustomerService {
    private final JdbcTemplate jdbc;

    CustomerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    String greet(long id) {
        return jdbc.queryForObject(
            "SELECT name FROM customers WHERE id = ?",
            String.class,
            id
        );
    }
}
```

Dù `JdbcTemplate` đã giảm nhiều mã JDBC thủ công, service trên vẫn biết bảng `customers`, cột `name`, SQL và hợp đồng “đúng một hàng”. Nếu chuyển sang Spring Data JPA, đổi database schema hoặc lấy khách hàng từ API, chính service phải sửa.

**Mục tiêu của bài:** service chỉ biết *cần thao tác gì và kết quả có nghĩa thế nào*, còn chi tiết *làm bằng JDBC, JPA, bộ nhớ hay một gateway* thuộc về lớp triển khai truy cập dữ liệu. Việc tách này tạo một ranh giới có thể kiểm thử, thay thế và phát triển độc lập hơn.

## 2. Hợp đồng truy cập dữ liệu là gì?

**Hợp đồng (contract)** là tập hợp các thao tác, kiểu dữ liệu, điều kiện đầu vào, ý nghĩa kết quả và quy tắc lỗi mà bên gọi có thể dựa vào. Trong Java, hợp đồng thường được thể hiện bằng một `interface`, nhưng **chữ ký phương thức một mình chưa đủ**: cần mô tả hành vi.

Ví dụ tối giản:

```java
public interface CustomerRepository {
    Optional<Customer> findById(long id);
    void create(Customer customer);
}
```

Trong hợp đồng này, ta cần thống nhất:

- `findById(id)` trả một khách hàng nếu tồn tại, `Optional.empty()` nếu không có; không ném lỗi chỉ vì không tìm thấy.
- `create(customer)` thêm khách hàng mới; nếu mã đã tồn tại thì phát sinh một ngoại lệ nghiệp vụ thống nhất, chẳng hạn `CustomerAlreadyExistsException`.
- `Customer` là mô hình mà bên nghiệp vụ hiểu, không phải `ResultSet`, `Tuple`, proxy entity buộc phải có phiên làm việc đang mở, hay kiểu riêng của driver.
- Lỗi hạ tầng (DB không sẵn sàng, query timeout, kết nối hỏng) cần được báo đúng là lỗi truy cập dữ liệu; không đánh đồng với trường hợp “không tìm thấy”.
- Nếu phương thức yêu cầu thứ tự, phân trang, khóa đồng thời hoặc một số lượng bản ghi chính xác, các bảo đảm đó phải nằm trong mô tả hợp đồng.

**Hợp đồng được xác định bởi nhu cầu của người dùng nó.** Không nên tạo interface chỉ bằng cách sao chép tất cả phương thức của `JdbcTemplate` hoặc `JpaRepository`. Câu hỏi trước tiên là: service thật sự cần thao tác nghiệp vụ nào?

### 2.1. Hướng phụ thuộc trong thiết kế

```text
       Tầng ứng dụng / nghiệp vụ
                 |
                 | gọi phương thức của
                 v
       CustomerRepository (contract)
                 ^
                 | implements
        +--------+---------+
        |                  |
 JdbcCustomerRepository   InMemoryCustomerRepository
        |                  |
    JdbcTemplate        Map<Long, Customer>
        |
    DataSource / DB
```

Mũi tên `implements` cho thấy lớp cụ thể phải **tuân theo** hợp đồng. Để mã nguồn ít phụ thuộc công nghệ, interface thường được đặt ở package `domain` hoặc `application.port`; mã JDBC/JPA đặt ở `infrastructure.persistence`. Lúc chạy, Spring nối các phần bằng dependency injection.

Không nhất thiết phải áp dụng đầy đủ kiến trúc hexagonal để đạt điều này. Tư tưởng cốt lõi là **Dependency Inversion**: thành phần chứa quy tắc cấp cao phụ thuộc vào một abstraction ổn định do nhu cầu của nó định nghĩa, thay vì phụ thuộc trực tiếp vào lớp lưu trữ cấp thấp.

### 2.2. Phân biệt interface, implementation và cấu hình

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Contract (port/repository interface) | Nêu thao tác và ngữ nghĩa mà bên gọi cần | `CustomerRepository.findById` |
| Service/use case | Kiểm tra nghiệp vụ, phối hợp thao tác, định ranh giới transaction | `CustomerService.register` |
| Adapter/implementation | Chuyển thao tác trừu tượng thành câu lệnh/driver cụ thể | `JdbcCustomerRepository` |
| Mapping | Chuyển hàng dữ liệu/entity/response thành mô hình phù hợp hợp đồng | `RowMapper<Customer>` |
| Composition root | Chọn implementation và lắp dependency vào service | `@Configuration`, `@Bean` hoặc component scanning |

**Đừng nhầm “tách interface” với “mỗi lớp đều cần interface”.** Tạo abstraction có ích khi có ranh giới trách nhiệm rõ, cần thử nghiệm với fake, có khả năng đổi adapter hoặc muốn tránh lộ API persistence vào service. Với mã thử nhỏ chỉ có một đường gọi, interface chỉ chuyển tiếp không thêm ngữ nghĩa có thể làm tăng độ phức tạp.

## 3. Ví dụ Java 17+: đổi từ bộ nhớ sang JDBC mà service không đổi

Ví dụ dưới đây là **chương trình đầy đủ** dùng Java 17+, Spring Framework 6.2.x và H2 in-memory. Cả hai implementation dùng cùng một `CustomerRepository` và cùng một `CustomerService`. Ứng dụng cố ý chạy hai `ApplicationContext` khác nhau để minh họa lựa chọn implementation, nên không có hai bean cạnh tranh cùng lúc.

Cấu trúc thư mục:

```text
data-contract-demo/
├── pom.xml
└── src/main/java/example/ContractDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>data-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/ContractDemo.java`:

```java
package example;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;

public class ContractDemo {
    // Mô hình nghiệp vụ, độc lập với JDBC và H2.
    public record Customer(long id, String name) {}

    // Hợp đồng: ý nghĩa phương thức giống nhau ở mọi implementation.
    public interface CustomerRepository {
        Optional<Customer> findById(long id);
        void create(Customer customer);
    }

    public static class CustomerAlreadyExistsException extends RuntimeException {
        public CustomerAlreadyExistsException(long id) {
            super("Customer already exists: " + id);
        }

        public CustomerAlreadyExistsException(long id, Throwable cause) {
            super("Customer already exists: " + id, cause);
        }
    }

    // Service chỉ phụ thuộc vào contract, không import JDBC/JPA.
    public static class CustomerService {
        private final CustomerRepository repository;

        public CustomerService(CustomerRepository repository) {
            this.repository = repository;
        }

        public void register(long id, String name) {
            if (id <= 0 || name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid customer");
            }
            repository.create(new Customer(id, name));
        }

        public String greeting(long id) {
            return repository.findById(id)
                    .map(c -> "Xin chào, " + c.name())
                    .orElse("Không tìm thấy");
        }
    }

    // Adapter thứ nhất: lưu trong bộ nhớ. Phù hợp demo/test, không bền vững.
    public static class InMemoryCustomerRepository implements CustomerRepository {
        private final Map<Long, Customer> items = new HashMap<>();

        @Override
        public Optional<Customer> findById(long id) {
            return Optional.ofNullable(items.get(id));
        }

        @Override
        public void create(Customer customer) {
            if (items.putIfAbsent(customer.id(), customer) != null) {
                throw new CustomerAlreadyExistsException(customer.id());
            }
        }
    }

    // Adapter thứ hai: lưu vào database bằng Spring JDBC.
    public static class JdbcCustomerRepository implements CustomerRepository {
        private final JdbcTemplate jdbc;

        public JdbcCustomerRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public Optional<Customer> findById(long id) {
            List<Customer> rows = jdbc.query(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong("id"),
                            rs.getString("name")),
                    id);
            return rows.stream().findFirst();
        }

        @Override
        public void create(Customer customer) {
            try {
                jdbc.update(
                        "INSERT INTO customers (id, name) VALUES (?, ?)",
                        customer.id(),
                        customer.name());
            } catch (DuplicateKeyException e) {
                throw new CustomerAlreadyExistsException(customer.id(), e);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MemoryConfig {
        @Bean
        public CustomerRepository customerRepository() {
            return new InMemoryCustomerRepository();
        }

        @Bean
        public CustomerService customerService(CustomerRepository repository) {
            return new CustomerService(repository);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JdbcConfig {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:contracts;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            // Chỉ để demo. Ứng dụng thật nên quản lý schema bằng migration.
            jdbc.execute(
                    "CREATE TABLE customers (" +
                    "id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL)");
            return jdbc;
        }

        @Bean
        public CustomerRepository customerRepository(JdbcTemplate jdbc) {
            return new JdbcCustomerRepository(jdbc);
        }

        @Bean
        public CustomerService customerService(CustomerRepository repository) {
            return new CustomerService(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(MemoryConfig.class)) {
            CustomerService service = context.getBean(CustomerService.class);
            service.register(1L, "Lan");
            System.out.println("Memory: " + service.greeting(1L));
            System.out.println("Memory missing: " + service.greeting(99L));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            CustomerService service = context.getBean(CustomerService.class);
            service.register(1L, "Lan");
            System.out.println("JDBC: " + service.greeting(1L));
            System.out.println("JDBC missing: " + service.greeting(99L));
        }
    }
}
```

Tại thư mục chứa `pom.xml`, thực thi:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.ContractDemo
```

Các dòng do chương trình in ra (bỏ qua log ngoài chương trình nếu môi trường cấu hình khác):

```text
Memory: Xin chào, Lan
Memory missing: Không tìm thấy
JDBC: Xin chào, Lan
JDBC missing: Không tìm thấy
```

**Nhìn vào điểm thay đổi:** `CustomerService`, `CustomerRepository` và `Customer` giữ nguyên. Chỉ composition root chọn `InMemoryCustomerRepository` hay `JdbcCustomerRepository`. Bản JDBC tự chuyển SQL/`ResultSet` thành `Customer`; bản memory đọc/ghi `Map`. Cả hai trả `Optional.empty()` khi không tìm thấy và cùng phát sinh `CustomerAlreadyExistsException` khi tạo trùng mã (với H2 và translator Spring phân loại được lỗi khóa trùng).

Ví dụ dùng `HashMap` đơn giản cho minh họa, không phải một kho dữ liệu dùng đồng thời giữa nhiều thread, không bền vững khi tiến trình dừng và không cung cấp transaction. Việc khởi tạo bảng trong `@Bean` cũng chỉ phục vụ demo: production nên dùng Flyway/Liquibase hay migration được quản lý.

## 4. Hợp đồng tốt là hợp đồng có ngữ nghĩa ổn định

Giả sử service xử lý đăng ký khách hàng. Nếu contract trả về kiểu JDBC, nó đã rò rỉ chi tiết:

```java
// Không nên dùng làm hợp đồng tầng nghiệp vụ:
ResultSet getCustomer(long id);
SQLException saveCustomer(Customer customer);
```

`ResultSet` phụ thuộc connection còn mở; `SQLException` buộc caller hiểu lỗi driver. Đồng thời chữ ký `saveCustomer` ở ví dụ thứ hai là kiểu trả về vô nghĩa cho thao tác create.

Một hợp đồng phù hợp hơn là:

```java
// Đoạn interface minh họa; các kiểu miền đã được định nghĩa ở module ứng dụng.
interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
    Customer create(NewCustomer command);
    boolean existsByEmail(Email email);
}
```

**Lưu ý:** không nhất thiết phải tạo value object `CustomerId`/`Email` cho mọi dự án; kiểu `long`, `String` vẫn hợp lệ nếu validation và ý nghĩa đủ rõ. Điều quan trọng là interface mô tả nhu cầu của use case.

Để đánh giá chất lượng hợp đồng, trả lời năm câu hỏi:

1. **Người gọi cần gì?** Đọc một aggregate, tìm kiếm, tạo mới, cập nhật, xóa hay chỉ kiểm tra điều kiện?
2. **“Không có dữ liệu” nghĩa là gì?** `Optional.empty()`, danh sách rỗng, null (nên tránh nếu có thể) hay ngoại lệ nghiệp vụ?
3. **“Thành công” nghĩa là gì?** `create` phải đảm bảo tạo đúng một bản ghi hay cho phép idempotent upsert? `update` trả phiên bản mới, số dòng tác động hay không có kết quả?
4. **Lỗi nào ổn định giữa các implementation?** Trùng khóa, xung đột phiên bản, tham số không hợp lệ là quy tắc nghiệp vụ; kết nối DB hỏng thường là lỗi hạ tầng.
5. **Có bảo đảm nào về thứ tự, phân trang, đồng thời và transaction?** Nếu không định nghĩa rõ, hai adapter có thể trả kết quả “đúng kiểu” nhưng khác ý nghĩa.

### 4.1. Tránh hợp đồng quá rộng

Một interface `GenericRepository<T, ID>` có hàng chục phương thức CRUD, flush, lock, paging và query builder có thể phù hợp thư viện persistence, nhưng dễ buộc các use case nhận nhiều quyền và nhiều ý niệm DB hơn mức cần thiết.

Thay vì:

```java
interface GenericRepository<T, ID> {
    T save(T value);
    void delete(ID id);
    List<T> findAll();
    List<T> findByRawSql(String sql);
}
```

Một ranh giới dành cho use case đặt hàng có thể là:

```java
interface OrderStore {
    Optional<Order> findById(OrderId id);
    OrderId add(NewOrder order);
    boolean reserveIfAvailable(OrderId id, long expectedVersion);
}
```

Cách đặt tên `reserveIfAvailable` (nếu mô hình nghiệp vụ thật sự cần) bộc lộ một kết quả và điều kiện cạnh tranh đồng thời, thay vì bắt service ghép những câu update SQL không an toàn. Tuy nhiên điều kiện, phiên bản và thao tác nguyên tử vẫn cần được implement đúng ở DB; tên hàm tự nó không bảo đảm atomicity.

**Interface Segregation:** tách hợp đồng theo nhu cầu thực của bên gọi (read model, write operations, truy vấn chuyên biệt) nếu điều này giảm phụ thuộc. Không tách thành hàng chục interface một phương thức một cách máy móc.

### 4.2. Ngữ nghĩa lỗi phải nhất quán

Không nên để adapter A trả `null` khi không tìm thấy còn adapter B ném `EmptyResultDataAccessException` nếu contract quy định `Optional.empty()`. Trong mẫu ở trên, bản JDBC dùng `query(...)` + `Optional` để giữ cách xử lý “0 hàng” nhất quán.

Các ngoại lệ cần phân biệt:

- **Không tìm thấy:** tình huống thường gặp nếu contract cho phép; trả `Optional.empty()`.
- **Trùng khóa hoặc vi phạm điều kiện nghiệp vụ:** chuyển thành ngoại lệ/kết quả ở mức ứng dụng (như `CustomerAlreadyExistsException`) sau khi xác định được nguyên nhân.
- **Lỗi hệ thống:** `DataAccessException` có thể được phép lan lên tầng xử lý lỗi hạ tầng, hoặc được chuyển sang ngoại lệ ứng dụng riêng nếu kiến trúc yêu cầu. Không “giả” lỗi DB thành “khách hàng không tồn tại”.
- **Kết quả bất thường:** nếu kho dữ liệu có thể trả nhiều hàng cho truy vấn một định danh vốn phải duy nhất, hãy dùng ràng buộc DB và báo lỗi dữ liệu không hợp lệ; đừng lặng lẽ lấy một hàng ngẫu nhiên.

Bản demo bắt `DuplicateKeyException`; trong thực tế, phân loại từ driver không bảo đảm giống nhau với mọi database. Hãy kiểm thử đường lỗi và ràng buộc unique ở đúng hệ quản trị đang dùng.

## 5. Dùng Spring DI để nối hợp đồng với implementation

Service chỉ cần nhận interface qua constructor:

```java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    // Các phương thức nghiệp vụ...
}
```

Đây là đoạn trích minh họa trong ứng dụng dùng `@Service`; khi Spring tìm thấy bean `CustomerRepository` phù hợp, nó inject vào constructor. Thay implementation không buộc sửa constructor hay logic service.

Có hai cách phổ biến để đăng ký adapter:

**Cách A — stereotype + component scanning:**

```java
@Repository
public class JdbcCustomerRepository implements CustomerRepository {
    // Constructor nhận JdbcTemplate; thực thi hợp đồng.
}
```

**Cách B — cấu hình tường minh:**

```java
@Configuration(proxyBeanMethods = false)
class PersistenceConfiguration {
    @Bean
    CustomerRepository customerRepository(JdbcTemplate jdbc) {
        return new JdbcCustomerRepository(jdbc);
    }
}
```

Hai đoạn là **minh họa** và cần các class/import/bean liên quan để build. `@Repository` nêu vai trò persistence, có thể tham gia cơ chế exception translation cho một số API persistence khi được cấu hình; `JdbcTemplate` tự dịch `SQLException` của nó, không đòi `@Repository` để làm việc này.

### 5.1. Khi có nhiều bean cùng interface

Nếu `InMemoryCustomerRepository` và `JdbcCustomerRepository` cùng được đăng ký thành bean trong một context mà không có cách phân biệt, injection theo kiểu `CustomerRepository` thường không xác định được bean duy nhất (`NoUniqueBeanDefinitionException`).

Các lựa chọn:

- **Chỉ đăng ký một bean** theo cấu hình môi trường: production dùng JDBC, test dùng fake.
- **`@Qualifier`** chỉ rõ implementation khi có nhu cầu sử dụng cả hai trong cùng context.
- **`@Primary`** khai báo mặc định trong số nhiều bean; dùng thận trọng để tránh lựa chọn khó nhìn thấy.
- **`@Profile`** hoặc cấu hình theo properties cho adapter khác nhau; cấu hình phải bảo đảm đúng một bean thực sự được kích hoạt cho bên tiêu thụ.

Ví dụ profile (đoạn minh họa):

```java
@Bean
@Profile("dev")
CustomerRepository memoryRepository() {
    return new InMemoryCustomerRepository();
}

@Bean
@Profile("prod")
CustomerRepository jdbcRepository(JdbcTemplate jdbc) {
    return new JdbcCustomerRepository(jdbc);
}
```

Không dùng profile như biện pháp bảo mật. Tên `prod` hoặc `dev` không thay thế thông tin xác thực, phân quyền và kiểm soát môi trường triển khai. Trong nhiều ứng dụng, một adapter được cấu hình cho mọi môi trường, chỉ `DataSource` thay đổi là đủ.

### 5.2. Ai phụ thuộc vào ai khi biên dịch?

Một cách tổ chức package:

```text
com.example.app
├── domain
│   └── Customer.java
├── application
│   ├── CustomerService.java
│   └── port
│       └── CustomerRepository.java
├── infrastructure
│   └── persistence
│       └── jdbc
│           └── JdbcCustomerRepository.java
└── config
    └── PersistenceConfiguration.java
```

Theo cấu trúc này, `CustomerService` import `CustomerRepository` và `Customer`; `JdbcCustomerRepository` import ngược lại các kiểu hợp đồng để implement. `PersistenceConfiguration` được phép biết cả hai phía nhằm lắp ứng dụng. Dùng đa module build thì có thể enforce bằng dependency direction; dùng một module vẫn cần kỷ luật review và kiểm thử kiến trúc.

Không bắt buộc tên package trên: điều cần giữ là source code nghiệp vụ không bị buộc import `ResultSet`/`JdbcTemplate`/`EntityManager` chỉ để thực hiện use case.

## 6. Mapping: ngăn chi tiết dữ liệu rò rỉ ra hợp đồng

Cùng một khách hàng có thể có ba hình dạng:

```text
Bảng SQL: customers(id, full_name, status_code)
             |
       JDBC RowMapper
             v
Customer(id, name, status)   <- contract trả về
             ^
         JPA mapper
             |
CustomerJpaEntity(id, fullName, statusCode)
```

Nếu contract trả thẳng `CustomerJpaEntity` rồi caller truy cập lazy relationship sau khi transaction kết thúc, logic nghiệp vụ có thể phụ thuộc vào persistence context và bị lỗi lazy loading. Với JDBC, trả `ResultSet` khiến caller phụ thuộc connection vẫn mở.

Adapter nên chuyển dữ liệu sang mô hình phù hợp ranh giới:

```java
// Ví dụ RowMapper là một phần của JDBC adapter.
RowMapper<Customer> mapper = (rs, rowNum) ->
    new Customer(
        rs.getLong("id"),
        rs.getString("full_name")
    );
```

Không cần luôn nhân đôi mọi entity/DTO. Nếu mô hình đơn giản, không có lazy loading và tách rõ ownership, có thể cân nhắc dùng chung kiểu. Nhưng **không dùng chung chỉ vì tiện ban đầu** nếu hệ quả là API DB hoặc persistence annotations lan rộng qua tầng nghiệp vụ.

### 6.1. Ranh giới không loại bỏ mọi khác biệt công nghệ

Một implementation dùng JDBC SQL, implementation khác dùng JPA hoặc HTTP. Có thể giữ cùng interface, nhưng phải giải quyết riêng:

- SQL dialect, transaction semantics, mức isolation, khóa/optimistic locking.
- Lazy loading, fetch strategy và số lượng query.
- Giá trị `NULL`, conversion kiểu dữ liệu, precision và timezone.
- Phân trang/sắp xếp ổn định, consistency khi đọc từ cache hay remote API.
- Lỗi mạng, timeout, retry, tính idempotent và dữ liệu eventual consistency.

Thay thế adapter thành công khi **hành vi contract vẫn đúng**, chứ không chỉ vì class mới triển khai đủ method.

## 7. Transaction thuộc ranh giới use case, không tự sinh từ interface

Một hợp đồng repository giúp service không gắn với SQL, nhưng **interface không tự bảo đảm transaction**. Ví dụ use case cần tạo hóa đơn và trừ tồn kho như một đơn vị nhất quán:

```java
// Đoạn minh họa; các interface được thiết kế cho từng miền.
@Service
class CheckoutService {
    private final OrderRepository orders;
    private final StockRepository stock;

    CheckoutService(OrderRepository orders, StockRepository stock) {
        this.orders = orders;
        this.stock = stock;
    }

    @Transactional
    public void checkout(NewOrder order) {
        stock.reserve(order.items());
        orders.create(order);
    }
}
```

Để hoạt động đúng, cần transaction manager đã cấu hình, lời gọi đi qua Spring proxy (theo chế độ proxy mặc định), và cả hai adapter phải tham gia **cùng tài nguyên/transaction** thích hợp. Nếu `stock` gọi một HTTP service độc lập, `@Transactional` của JDBC không tự rollback được hệ thống từ xa; phải thiết kế cơ chế phối hợp như outbox, saga hoặc idempotency tùy bài toán.

Các điểm cần tránh:

- Đặt `@Transactional` trên interface rồi mặc nhiên nghĩ mọi cách proxy/weaving và mọi cấu hình đều nhận annotation như nhau. Thực tế hãy đặt trên phương thức service cụ thể, kiểm thử cấu hình proxy đang dùng.
- Gọi phương thức annotated thông qua `this.method()` khi dùng proxy mặc định: self-invocation không qua advice.
- Mặc định Spring rollback cho `RuntimeException` và `Error`; checked exception cần `rollbackFor` hoặc cấu hình khác. Catch rồi nuốt lỗi có thể khiến commit.
- Mở JDBC connection mới bên trong transaction mà không dùng cơ chế Spring-managed connection có thể khiến thao tác không tham gia cùng transaction.
- Dùng fake in-memory trong unit test rồi suy ra rollback thật được: `Map` không có giao dịch, vì vậy cần integration test transaction với DB.

**Quy tắc hữu ích:** service quyết định *những bước nào phải nguyên tử về nghiệp vụ*; adapter và cấu hình Spring bảo đảm cách thực thi transaction cho nguồn dữ liệu tương ứng.

## 8. Test theo ranh giới: service test khác adapter test

Tách hợp đồng có lợi khi cần kiểm tra nghiệp vụ mà không khởi động DB.

### 8.1. Unit test service với fake

Dùng implementation in-memory kiểm tra cách service dùng contract:

```java
// Đoạn trích JUnit 5, dùng các class trong ContractDemo.
@Test
void registerAndGreet() {
    CustomerRepository fake = new InMemoryCustomerRepository();
    CustomerService service = new CustomerService(fake);

    service.register(7L, "Hoa");

    assertEquals("Xin chào, Hoa", service.greeting(7L));
    assertEquals("Không tìm thấy", service.greeting(8L));
    assertThrows(CustomerAlreadyExistsException.class,
            () -> service.register(7L, "Trung"));
}
```

Đoạn này không nằm trong `ContractDemo.java` chạy độc lập; cần JUnit Jupiter, static import `Assertions.assertEquals`/`assertThrows` và import các kiểu lồng trong `ContractDemo`. Mục đích là cô lập service để test quy tắc nghiệp vụ nhanh, không khởi động Spring.

Fake có thể làm bài test sai lệch nếu trả kết quả khác DB thực tế. Ví dụ `Map` không tự enforce độ dài cột VARCHAR, collation, constraint DB, isolation hay thứ tự truy vấn. Vì vậy unit test chưa chứng minh adapter đúng hợp đồng.

### 8.2. Contract test cho các implementation

Viết một tập kiểm tra hành vi dùng chung, chạy lần lượt trên memory và JDBC:

| Tình huống | Kết quả contract cần thống nhất |
| --- | --- |
| Tìm mã chưa tồn tại | `Optional.empty()` |
| Tạo rồi tìm cùng mã | Đọc được đúng dữ liệu đã tạo |
| Tạo trùng mã | `CustomerAlreadyExistsException` |
| Dữ liệu đầu vào không hợp lệ | Bị service từ chối theo cùng quy tắc |
| Truy vấn trả nhiều kết quả | Thỏa hợp đồng cardinality/ordering |
| Cập nhật đồng thời | Phù hợp chính sách conflict nếu contract quy định |

Để test đúng, mỗi case cần dữ liệu độc lập và setup/cleanup rõ ràng. Contract test giúp phát hiện các adapter chỉ “giống chữ ký” nhưng không giống cách ứng xử.

### 8.3. Integration test adapter với DB

Tách ra test `JdbcCustomerRepository` bằng H2 hoặc test DB thật. Kiểm tra SQL syntax, column mapping, unique constraint, database-specific behavior, rollback và dữ liệu `NULL`. Khi SQL phụ thuộc PostgreSQL/MySQL/Oracle, test với DB tương ứng (ví dụ Testcontainers) đáng tin hơn giả lập hoàn toàn bằng H2.

Các test Spring có thể hỗ trợ: `@JdbcTest` cho slice JDBC, `@DataJpaTest` cho JPA. Đây là hai cơ chế phục vụ hai implementation khác nhau; không mặc nhiên dùng `@DataJpaTest` để test `JdbcTemplate`. Khi test bean wiring, cần test Spring context với cấu hình adapter thực tế để phát hiện thiếu bean, sai qualifier hoặc chọn nhầm profile.

## 9. Thiết kế nâng cao: đọc/ghi, pagination và nhất quán

Một interface không nhất thiết phải vừa truy vấn rộng vừa thực hiện mọi thao tác ghi. Khi hệ thống lớn dần, có thể có cổng đọc và cổng ghi khác nhau:

```java
interface CustomerReader {
    Optional<CustomerSummary> findSummaryById(long id);
    List<CustomerSummary> search(CustomerSearchFilter filter, int limit);
}

interface CustomerWriter {
    CustomerId create(NewCustomer command);
    boolean updateName(CustomerId id, String newName, long expectedVersion);
}
```

Đây là đoạn minh họa cần các kiểu miền tương ứng. `expectedVersion` biểu diễn optimistic concurrency: adapter cập nhật khi phiên bản hiện tại khớp, ví dụ SQL `UPDATE ... WHERE id = ? AND version = ?` và kiểm tra số hàng. Nếu trả `false`, service quyết định có phải xung đột hay đã bị xóa, dựa trên hợp đồng đã thống nhất. Không mặc nhiên giải thích mọi `update count = 0` là cùng một lỗi.

Khi contract trả một danh sách, phải làm rõ:

- **Thứ tự:** DB không đảm bảo mặc định nếu không có `ORDER BY`; memory fake cũng phải chọn thứ tự theo hợp đồng.
- **Giới hạn:** với collection lớn, không nên buộc `findAll()` tải toàn bộ vào bộ nhớ; dùng limit + cursor/page key phù hợp.
- **Trang dữ liệu:** offset pagination và keyset pagination có tính chất khác nhau khi dữ liệu thay đổi; interface nên mô tả cursor/sort đủ rõ.
- **Thời gian quan sát:** truy vấn qua cache/replica có thể stale; không đưa cam kết “đọc ngay sau ghi” nếu hạ tầng không bảo đảm.
- **Nhiều nguồn dữ liệu:** một interface có thể che việc gọi nhiều adapter, nhưng transaction phân tán, retry và nhất quán phải thiết kế riêng.

Nếu Spring Data đã phù hợp, có thể dùng `JpaRepository` hoặc `CrudRepository` như một abstraction sẵn có. Tuy nhiên các method, kiểu `Pageable`/`Page` và cơ chế entity có thể làm tầng ứng dụng phụ thuộc Spring Data. Chỉ dùng trực tiếp khi sự phụ thuộc đó là quyết định có chủ đích; nếu muốn cổng nghiệp vụ độc lập, thêm interface nhỏ do ứng dụng sở hữu rồi để adapter gọi repository Spring Data phía sau.

## 10. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao gây vấn đề | Hướng sửa |
| --- | --- | --- |
| Service import `JdbcTemplate`/`EntityManager` và viết SQL | Công nghệ dữ liệu lan vào logic nghiệp vụ | Chuyển câu truy vấn, mapping vào adapter |
| Interface trả `ResultSet` hoặc entity có lazy proxy | Bên gọi phụ thuộc tài nguyên/persistence context còn mở | Trả kiểu miền/DTO đã ánh xạ phù hợp |
| Tạo interface 1:1 cho mọi class mà không có nhu cầu | Tăng tầng chuyển tiếp nhưng không tạo ranh giới ngữ nghĩa | Chỉ trừu tượng ở điểm có người tiêu thụ và trách nhiệm rõ |
| Định nghĩa `save` nhưng không nói insert, update hay upsert | Adapter có thể xử lý khác nhau | Chọn tên và contract mô tả chính xác |
| Fake trả `null`, JDBC ném exception khi thiếu dữ liệu | Test service có thể qua nhưng production hỏng | Dùng contract test và `Optional` nhất quán |
| Bắt mọi `DataAccessException` rồi trả “không tồn tại” | Che mất lỗi DB/outage | Phân biệt lỗi hệ thống và trường hợp hợp lệ |
| Đăng ký nhiều bean cùng interface không chọn rõ | Injection lỗi hoặc chọn không như mong đợi | Chỉ đăng ký bean phù hợp, hoặc dùng `@Qualifier`/`@Primary` có chủ đích |
| Dùng `@Transactional` và tin fake cũng rollback | Test không chứng minh nguyên tử ở DB | Integration test với transaction manager và DB |
| Đưa câu SQL tùy ý thành tham số của repository interface | Hợp đồng rò rỉ tầng truy vấn | Nêu truy vấn theo mục đích nghiệp vụ, tiêu chí typed |
| Giả định adapter mới tương đương chỉ vì implements | Khác về order, isolation, lỗi, nullability | Ghi rõ postcondition và chạy contract test |

## 11. Quy trình áp dụng vào một dự án Spring đang có

1. **Chọn use case cụ thể** đang trộn SQL và logic: ví dụ đăng ký khách hàng, đọc hồ sơ, tạo đơn. Quan sát chính xác dữ liệu service cần.
2. **Viết hợp đồng phía người tiêu thụ**, với tên thao tác, input, output, hành vi khi không tìm thấy, duplicate và lỗi hệ thống. Không sao chép tự động toàn bộ API persistence.
3. **Chuyển truy cập DB sang adapter**: SQL, `JdbcTemplate`, `RowMapper`, JPA entity mapping và exception translation. Giữ service chỉ gọi hợp đồng.
4. **Đăng ký implementation ở Spring configuration** và dùng constructor injection. Kiểm tra mỗi context có implementation đúng một cách rõ ràng.
5. **Chọn transaction boundary ở service** nếu nhiều thao tác phải nhất quán; bảo đảm cùng transaction manager và resource, kiểm thử rollback.
6. **Tách kiểm thử**: unit test nghiệp vụ với fake, contract test hành vi dùng chung, integration test adapter trên DB.
7. **Đo hiệu quả trước khi mở rộng**: nếu abstraction trở thành lớp chuyển tiếp vô nghĩa, thu hẹp. Nếu phát sinh thêm nguồn dữ liệu, tập trung kiểm tra tương đương về hành vi.

### Khi nào nên ưu tiên cách này?

Đặc biệt hữu ích khi một use case có quy tắc nghiệp vụ cần bảo vệ khỏi thay đổi schema/driver, khi muốn kiểm thử service mà không cần DB, khi có thể dùng nhiều nguồn dữ liệu, hoặc khi nhóm muốn phân ranh giới ownership rõ giữa ứng dụng và persistence.

Không phải mọi thao tác đều đáng tách interface: trong hệ thống CRUD nhỏ, service gọi trực tiếp một Spring Data repository có thể đủ đơn giản và dễ bảo trì. Hãy dùng độ trừu tượng phù hợp với chi phí thay đổi dự kiến và nhu cầu kiểm thử.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ chuyển SQL từ service sang một class khác chưa chắc đã tạo ra hợp đồng truy cập dữ liệu tốt?
2. Khác biệt giữa “interface có đủ method” và “implementation tuân thủ ngữ nghĩa hợp đồng” là gì?
3. Vì sao `Optional.empty()` thường rõ nghĩa hơn việc để adapter tùy ý trả `null` hoặc ném lỗi khi tìm không thấy?
4. Khi có cả memory adapter và JDBC adapter, phần nào cần thay đổi để Spring chọn implementation?
5. Vì sao unit test dùng `Map` không thể chứng minh transaction rollback đúng trên database?
6. Nếu ứng dụng chuyển từ JDBC sang JPA, những yếu tố nào ngoài chữ ký method phải được kiểm tra lại?

**Kết luận:** tách hợp đồng truy cập dữ liệu khỏi cách triển khai nghĩa là tách *điều nghiệp vụ cần* khỏi *cách hạ tầng thực hiện*. Service phụ thuộc vào interface có ngữ nghĩa rõ; adapter dùng Spring JDBC/JPA hoặc nguồn khác để thực hiện cùng hành vi; cấu hình Spring kết nối hai phần. Lợi ích thật đến từ hợp đồng nhất quán, mapping đúng, transaction được thiết kế có chủ đích và kiểm thử ở cả phía service lẫn adapter.

### Tài liệu tham khảo chính thức

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Dependency Injection: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Data Commons — Repository Abstraction: https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html
