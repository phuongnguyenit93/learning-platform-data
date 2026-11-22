# Quan hệ giữa AOP, truy cập dữ liệu và quản lý tài nguyên trong Spring Transaction Management

## 1. Bức tranh tổng thể

Trong một nghiệp vụ như chuyển tiền, đặt hàng hoặc cập nhật tồn kho, nhiều thao tác dữ liệu phải được xem là **một đơn vị công việc**: hoặc các thay đổi cần thiết được commit, hoặc chúng được rollback theo chính sách giao dịch. Trong Spring, ba cơ chế phối hợp để làm việc đó:

1. **AOP (Aspect-Oriented Programming)** xác định *khi nào* một lời gọi phương thức cần được bao quanh bởi logic giao dịch. Với cách khai báo thông dụng, Spring tạo proxy và gắn `TransactionInterceptor` vào lời gọi phù hợp.
2. **Transaction management** xác định *giao dịch nào* cần bắt đầu/tham gia/kết thúc. `PlatformTransactionManager` điều phối transaction và trạng thái của những tài nguyên có liên quan; chính hệ thống lưu trữ thực hiện commit/rollback thực tế.
3. **Data access và resource management** thực hiện SQL/JPA và dùng đúng tài nguyên đang tham gia giao dịch, ví dụ JDBC `Connection` hoặc JPA `EntityManager`. Spring giúp lấy, liên kết, tái sử dụng và giải phóng các tài nguyên đó đúng vòng đời.

Ba lớp có trách nhiệm khác nhau. Annotation `@Transactional` **không tự chạy SQL, tự tạo kết nối hoặc tự đảm bảo tính nguyên tử**. Nó cung cấp metadata để hạ tầng giao dịch, thường thông qua AOP, thiết lập ranh giới transaction; việc thay đổi dữ liệu vẫn do DAO/repository và database thực hiện.

| Thành phần | Trách nhiệm chính | Ví dụ điển hình |
| --- | --- | --- |
| AOP proxy + `TransactionInterceptor` | Chặn lời gọi đi qua proxy, đọc metadata `@Transactional`, bao quanh phương thức bằng advice | Gọi `orderService.placeOrder()` |
| `PlatformTransactionManager` | Chọn begin/join, commit/rollback, điều phối trạng thái giao dịch và tài nguyên | `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager` |
| Tầng data access | Thực hiện truy vấn/cập nhật, chuyển ngoại lệ, làm việc qua API phù hợp | `JdbcTemplate`, Spring Data JPA repository |
| Tài nguyên thực | Chứa trạng thái vật lý của transaction và áp dụng commit/rollback | JDBC `Connection`, JPA `EntityManager` cùng transaction backend, transaction của DB |
| Hạ tầng đồng bộ tài nguyên | Gắn tài nguyên với ngữ cảnh thực thi và dọn chúng khi kết thúc | `TransactionSynchronizationManager`, `DataSourceUtils` |

> Phạm vi bài này là **mối liên hệ** giữa các lớp. Các chủ đề như isolation, propagation nâng cao, distributed transaction và tối ưu hiệu năng được giới thiệu vừa đủ để hiểu cách các lớp tương tác.

## 2. Đường đi của một lời gọi có `@Transactional`

Giả sử một HTTP controller gọi một Spring bean tên `transferService`; bean này có phương thức `transfer()` được đánh dấu `@Transactional`. Với transaction kiểu imperative thông thường, đường đi khái niệm là:

```text
Controller / caller
       |
       v
Spring AOP proxy của TransferService
       |
       v
TransactionInterceptor (đọc @Transactional)
       |
       v
PlatformTransactionManager
       |-- xác định transaction hiện có / tạo transaction mới
       |-- chuẩn bị và liên kết tài nguyên cần thiết
       |
       v
TransferService.transfer()  <-- method nghiệp vụ thực sự
       |
       +--> AccountRepository.debit()
       |            |
       |            +--> JdbcTemplate / JPA
       |
       +--> AccountRepository.credit()
                    |
                    +--> cùng ngữ cảnh transaction phù hợp
       |
       v
Method trả về hoặc phát sinh exception
       |
       v
TransactionInterceptor / TransactionManager
       |-- commit nếu thành công và transaction có thể commit
       |-- rollback / đánh dấu rollback-only nếu quy tắc yêu cầu
       +-- giải phóng đồng bộ và tài nguyên, trả connection về pool
```

Diễn giải từng giai đoạn:

1. **Caller lấy bean từ Spring container.** Khi cấu hình transaction đã được kích hoạt, caller thường tương tác với proxy thay vì gọi trực tiếp một đối tượng tự khởi tạo bằng `new`.
2. **Proxy đi vào interceptor.** Interceptor đọc thuộc tính transaction áp dụng cho phương thức, như `propagation`, `readOnly`, `isolation`, `timeout` và quy tắc rollback.
3. **Transaction manager xác định phạm vi.** Với mặc định `Propagation.REQUIRED`, nó tham gia giao dịch hiện tại nếu có; nếu chưa có thì bắt đầu giao dịch mới. Không phải mỗi method `@Transactional` đều tạo một transaction vật lý khác nhau.
4. **Hạ tầng quản lý tài nguyên.** Với JDBC điển hình, transaction manager làm việc với connection từ `DataSource`, thiết lập đặc tính transaction cần thiết và gắn connection với luồng thực thi. Thời điểm thực sự lấy connection có thể phụ thuộc cách cấu hình và cơ chế lazy acquisition.
5. **Mã nghiệp vụ gọi data-access API.** `JdbcTemplate` hoặc repository dùng tài nguyên tương thích với transaction hiện tại. Nhiều câu SQL trong cùng phạm vi có thể dùng chung JDBC connection và cùng transaction vật lý.
6. **Khi phương thức kết thúc, interceptor quyết định kết cục theo transaction scope.** Nếu đây là phạm vi sở hữu transaction vật lý và đủ điều kiện commit, manager gọi commit; nếu cần rollback, manager gọi rollback. Phạm vi tham gia transaction của caller có thể chỉ đánh dấu rollback-only để transaction ngoài quyết định kết thúc.
7. **Spring dọn trạng thái.** Callback đồng bộ được thực hiện theo vòng đời; tài nguyên bị gỡ khỏi ngữ cảnh và connection được release. Với connection pool, “đóng” ở phía ứng dụng thường có nghĩa là **trả connection về pool**, không phải hủy kết nối vật lý tới DB.

**Điểm mấu chốt:** AOP đứng ở ranh giới lời gọi phương thức; transaction manager đứng ở ranh giới giao dịch; data-access API và tài nguyên giúp từng thao tác dữ liệu thực sự tham gia giao dịch đó.

## 3. Vì sao dùng AOP thay vì tự viết `commit()` trong mỗi service?

Không có hỗ trợ khai báo, một nghiệp vụ JDBC thủ công phải lấy `Connection`, tắt auto-commit, thực hiện nhiều thao tác, gọi `commit()` hoặc `rollback()`, rồi khôi phục trạng thái và release connection. Lặp logic này trong nhiều service gây rối, dễ quên cleanup và khó thay đổi chính sách nhất quán.

AOP tách **logic hạ tầng xuyên suốt** khỏi **logic nghiệp vụ**:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.items());
    }
}
```

Đoạn trên là **mã minh họa**, giả định `Order`, hai repository và các method đã được định nghĩa. Nó mô tả một ranh giới nghiệp vụ: nếu hai repository sử dụng những tài nguyên tương thích với **cùng transaction manager**, và lỗi làm transaction rollback, thao tác lưu đơn cùng giữ hàng được rollback theo transaction DB. AOP không cần chặn riêng từng câu SQL; nó bao quanh *toàn bộ* lời gọi `placeOrder`.

Spring AOP có thể dùng JDK dynamic proxy (dựa trên interface) hoặc proxy dựa trên lớp. Ở chế độ mặc định `proxy`, chỉ lời gọi **đi qua proxy** được advice chặn. Khả năng interception phụ thuộc phương thức/lớp và kiểu proxy; cách ổn định, dễ hiểu nhất là đặt `@Transactional` trên **public method của Spring-managed service bean**, được gọi từ bean khác hoặc caller bên ngoài.

`@Transactional` chỉ là metadata. Cần có hạ tầng transaction management hoạt động, ví dụ cấu hình `@EnableTransactionManagement` trong ứng dụng Spring thuần hoặc auto-configuration phù hợp trong Spring Boot, cùng một transaction manager được chọn chính xác.

## 4. Data access dùng chung transaction bằng cách nào?

### 4.1 JDBC: `DataSource`, `Connection`, `JdbcTemplate`

Trong luồng JDBC imperative thông thường:

- `DataSource` là nguồn cung cấp connection, thường backed by pool. `DataSource` **không đồng nghĩa** với một transaction.
- Một JDBC `Connection` là đối tượng gắn với transaction vật lý cho database đó. Các câu lệnh chạy qua connection này có thể thuộc cùng transaction.
- `DataSourceTransactionManager` (hoặc biến thể JDBC phù hợp) quản lý local JDBC transaction cho một `DataSource`; `JdbcTransactionManager` bổ sung cơ chế dịch ngoại lệ commit/rollback theo kiểu Spring.
- `TransactionSynchronizationManager` quản lý trạng thái và tài nguyên gắn với luồng thực thi ở tầng hạ tầng. Với imperative transaction, một connection holder có thể được liên kết theo khóa là `DataSource`.
- `JdbcTemplate` gọi qua `DataSourceUtils` để lấy/release connection theo ngữ cảnh Spring. Bởi vậy các lần `jdbc.update(...)` trong cùng transaction do Spring quản lý có thể chia sẻ connection mà mã nghiệp vụ không phải truyền `Connection` thủ công.
- `JdbcTemplate` cũng quản lý tài nguyên ngắn hạn như `Statement` và `ResultSet`; việc đó **khác** với kết thúc transaction hay trả connection đang bị giữ bởi transaction.

Ví dụ trong một lời gọi service có transaction:

```java
@Transactional
public void renameAndActivate(long id, String name) {
    jdbcTemplate.update("UPDATE account SET display_name = ? WHERE id = ?", name, id);
    jdbcTemplate.update("UPDATE account SET active = TRUE WHERE id = ?", id);
}
```

Đây là **method minh họa**, giả định đã có `jdbcTemplate` và bảng `account`. Nếu dùng cùng `DataSource`/manager và kết nối đang tham gia transaction, hai `UPDATE` thuộc cùng local JDBC transaction. Chạy hai lệnh độc lập ngoài phạm vi transaction thường không có đảm bảo nguyên tử xuyên suốt cả hai lệnh; nhiều cấu hình JDBC mặc định sử dụng auto-commit cho từng câu lệnh.

Khi phải dùng JDBC thuần bên trong Spring transaction, cần tôn trọng cơ chế connection binding:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE account SET active = TRUE WHERE id = ?")) {
    statement.setLong(1, id);
    statement.executeUpdate();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Đây cũng là **đoạn minh họa** cần các biến `dataSource`/`id`, imports JDBC và ngữ cảnh thực thi. Không gọi `connection.commit()` hoặc `connection.rollback()` trong đoạn DAO nếu transaction đang do Spring điều phối. `releaseConnection` tránh đóng connection đang được transaction nắm giữ; khi không có transaction, nó xử lý release thích hợp. Thường nên dùng `JdbcTemplate` để tránh phải xử lý chi tiết này.

Gọi trực tiếp `dataSource.getConnection()` từ code tùy ý có thể lấy một connection khác, không tự động tham gia connection mà Spring đã gắn theo luồng (trừ khi dùng adapter nhận biết transaction, chẳng hạn `TransactionAwareDataSourceProxy`). Đó là nguyên nhân phổ biến của lỗi “đã có `@Transactional` nhưng một thao tác vẫn commit riêng”.

### 4.2 JPA/Hibernate: `EntityManager` và persistence context

Khi dùng JPA, `JpaTransactionManager` quản lý local transaction JPA và sự tham gia của `EntityManager`/persistence context. `@PersistenceContext` và Spring Data JPA repository cung cấp cách truy cập `EntityManager` phù hợp với transaction mà không buộc service tự mở/đóng nó. Hibernate `Session` là tầng triển khai bên dưới khi Hibernate làm JPA provider.

Phải tách rõ hai khái niệm:

- **`flush`** đồng bộ các thay đổi đang chờ trong persistence context thành thao tác SQL tới database; nó **không đồng nghĩa** với commit.
- **`commit`** kết thúc giao dịch thành công theo cơ chế của transaction manager/database. SQL đã flush vẫn có thể bị rollback nếu transaction chưa commit.

Đừng suy ra cứ có một `DataSource` là mọi API JDBC, JPA và công cụ ngoài Spring tự động dùng cùng transaction. Việc phối hợp JDBC và JPA phụ thuộc cấu hình `JpaTransactionManager`, `DataSource` thống nhất và việc lấy connection qua cơ chế phù hợp. Khi có nhiều database hoặc nhiều transaction manager, phải xác định rõ tài nguyên nào thuộc transaction nào.

### 4.3 Bảng ánh xạ các kiểu tài nguyên

| Công nghệ | API truy cập thường dùng | Manager thường gặp | Ngữ cảnh/tài nguyên |
| --- | --- | --- | --- |
| JDBC | `JdbcTemplate`, Spring JDBC repository | `JdbcTransactionManager` / `DataSourceTransactionManager` | JDBC `Connection` liên kết với `DataSource` |
| JPA/Hibernate | Spring Data JPA, `EntityManager` | `JpaTransactionManager` | JPA transaction, `EntityManager` / persistence context |
| Nhiều tài nguyên có coordinator | API theo môi trường/JTA | `JtaTransactionManager` | Transaction do JTA coordinator quản lý; cần hạ tầng tương ứng |
| R2DBC reactive | `DatabaseClient`, reactive repository | `R2dbcTransactionManager` | Reactive `Connection`, trạng thái theo Reactor Context |

**Không đánh đồng `Resource` interface của Spring** (trừu tượng truy cập classpath/file/URL) với “transactional resource”. Đọc/ghi file qua `Resource` không tự trở thành thao tác có thể rollback cùng DB.

## 5. Ví dụ hoàn chỉnh: hai lệnh JDBC cùng commit hoặc rollback

Ví dụ nhỏ này dùng **Java 17**, **Spring Boot 3.3.5**, **Spring JDBC** và H2 in-memory. Spring Boot tự cấu hình `DataSource`, `JdbcTemplate` và JDBC transaction manager phù hợp trong cấu hình một database này. Có thể chạy độc lập với Maven 3.9+ và JDK 17+.

Tạo hai file theo cấu trúc:

```text
transaction-demo/
├── pom.xml
└── src/main/java/example/TxDemoApplication.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>transaction-demo</artifactId>
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
```

File `src/main/java/example/TxDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class TxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService service) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE accounts (
                        id VARCHAR(20) PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO accounts(id, balance) VALUES (?, ?)", "A", 100);
            jdbc.update("INSERT INTO accounts(id, balance) VALUES (?, ?)", "B", 50);

            try {
                service.transfer("A", "B", 30, true);
            } catch (IllegalStateException expected) {
                System.out.println("Da rollback sau loi gia lap");
            }
            printBalances(jdbc, "Sau loi");

            service.transfer("A", "B", 30, false);
            printBalances(jdbc, "Thanh cong");
        };
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?", Integer.class, "A");
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?", Integer.class, "B");
        System.out.println(label + ": A=" + a + ", B=" + b);
    }

    @Service
    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(String from, String to, int amount, boolean failAfterDebit) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int updated = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                    amount, from);
            if (updated != 1) {
                throw new IllegalArgumentException("source account not found");
            }

            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }

            updated = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (updated != 1) {
                throw new IllegalArgumentException("destination account not found");
            }
        }
    }
}
```

Chạy từ thư mục `transaction-demo`:

```bash
mvn -q spring-boot:run
```

Trong output (ngoài các thông báo khởi động tùy môi trường), chương trình in đúng những dòng sau:

```text
Da rollback sau loi gia lap
Sau loi: A=100, B=50
Thanh cong: A=70, B=80
```

Tại sao?

1. Hai lệnh `INSERT` ban đầu tạo dữ liệu thử nghiệm. Đối tượng `TransferService` là **Spring bean** được inject vào `CommandLineRunner`; lời gọi `service.transfer(...)` đi qua proxy.
2. Lần gọi đầu trừ `30` khỏi A, sau đó ném `IllegalStateException` trước khi cộng cho B. `TransactionInterceptor` thấy unchecked exception thoát khỏi method, yêu cầu rollback: số dư vẫn là `100` và `50`.
3. Lần gọi sau thực hiện cả debit và credit rồi trả về bình thường: transaction manager commit; số dư thành `70` và `80`.
4. Cả hai lời gọi `jdbc.update` trong một `transfer` dùng transaction JDBC do Spring quản lý. Service không tự tạo `Connection` hay gọi `commit()`.

**Giới hạn có chủ ý của demo:** chưa có kiểm tra đủ số dư, kiểm soát cập nhật đồng thời hoặc chính sách khóa; không sử dụng trực tiếp làm mã chuyển tiền sản xuất. Mục tiêu là quan sát ranh giới AOP, data access và transaction resource.

## 6. `@Transactional` được đặt ở đâu, và các thao tác tham gia thế nào?

Đặt ranh giới transaction ở **service/use case** khi nhiều bước phải là một đơn vị nghiệp vụ. Repository tập trung vào truy cập dữ liệu và không cần biết logic phối hợp toàn bộ nghiệp vụ.

```text
PlaceOrderService.placeOrder()  @Transactional(REQUIRED)
    |-- OrderRepository.save(order)
    |-- InventoryRepository.reserve(items)
    +-- PaymentRecordRepository.save(record)
           \--> các thao tác DB cùng manager/resource tương thích
```

Nếu các repository đều tham gia cùng transaction hiện tại, một rollback của transaction này có thể hủy mọi thay đổi chưa commit của chúng. Nếu repository gọi tài nguyên khác, manager khác hoặc connection mở độc lập, **không tự động có atomicity chung**.

Một method repository cũng có `@Transactional(REQUIRED)` không nhất thiết mở một transaction vật lý thứ hai; khi được gọi bên trong service có transaction, nó thường **tham gia** transaction đang hoạt động. `REQUIRES_NEW` thì khác: yêu cầu transaction độc lập, có thể lấy thêm connection trong lúc transaction ngoài vẫn giữ tài nguyên.

Các thuộc tính `@Transactional` cần hiểu trong mối liên hệ này:

| Thuộc tính | Ý nghĩa tại ranh giới AOP/transaction | Lưu ý về tài nguyên |
| --- | --- | --- |
| `propagation=REQUIRED` (mặc định) | Tham gia transaction hiện tại hoặc bắt đầu transaction mới | Các scope logic có thể cùng một transaction vật lý |
| `propagation=REQUIRES_NEW` | Tạm gác transaction ngoài và dùng transaction vật lý mới | Có thể cần connection bổ sung; pool nhỏ dễ bị cạn |
| `propagation=NESTED` | Nested scope bằng savepoint khi manager và DB hỗ trợ | Thường gắn với JDBC savepoint; không phải transaction độc lập |
| `readOnly=true` | Đưa ra ý định chỉ đọc/hint tối ưu cho manager và provider | Không phải hàng rào cấm mọi lệnh ghi trên mọi DB |
| `isolation`, `timeout` | Yêu cầu isolation/timeout cho transaction mới theo hỗ trợ thực tế | Không tự thay isolation của transaction đã tham gia |
| `rollbackFor` | Bổ sung loại exception gây rollback | Hữu ích với checked exception |
| `transactionManager` | Chỉ rõ manager cần dùng khi có nhiều manager | Sai manager có thể không quản lý tài nguyên của DAO |

Với `REQUIRED`, nếu một lời gọi bên trong đánh dấu transaction là **rollback-only** rồi caller ngoài vẫn cố commit, Spring có thể báo `UnexpectedRollbackException`. Điều này ngăn caller hiểu lầm rằng việc ghi dữ liệu đã được commit.

## 7. Những ranh giới mà AOP không tự vượt qua

### 7.1 Tự gọi method trong cùng bean (self-invocation)

```java
@Service
class BillingService {
    public void checkout() {
        charge(); // this.charge(): không đi lại qua Spring proxy
    }

    @Transactional
    public void charge() {
        // thao tác database
    }
}
```

Đây là đoạn **minh họa**, không phải chương trình chạy độc lập. Nếu caller chỉ gọi `checkout()` qua proxy, annotation trên `charge()` **không được interceptor áp dụng cho lời gọi nội bộ này**. Cách sửa thường là chuyển `charge()` sang Spring bean khác rồi gọi qua bean đó, hoặc đặt transaction boundary tại `checkout()`, hoặc dùng `TransactionTemplate` khi cần điều phối bằng code.

Tinh tế cần nhớ: nếu `checkout()` vốn đã nằm trong một transaction khác, lệnh gọi nội bộ vẫn có thể chạy **trong transaction sẵn có**, nhưng thuộc tính `@Transactional` riêng của `charge()` không được áp dụng độc lập qua self-invocation.

### 7.2 Không qua Spring proxy hoặc không thể interception

- `new TransferService(...)` tạo đối tượng không do container quản lý: annotation trên instance đó không tự kích hoạt Spring AOP.
- Private method không phải điểm giao tiếp proxy để áp dụng transaction như một public service method. Final class/method có giới hạn với proxy theo lớp vì không thể subclass/override tương ứng.
- `@PostConstruct`, lời gọi trực tiếp bên trong constructor hoặc mã khởi tạo sớm không phải nơi nên trông cậy vào proxy transaction đã sẵn sàng.
- Trạng thái transaction imperative thường gắn với **thread hiện tại**. Tạo thread mới, chạy `@Async` hoặc chuyển execution context không tự mang JDBC transaction đang tồn tại sang thread đó.
- Trong pipeline reactive, `ReactiveTransactionManager` dùng **Reactor Context**, không dùng quy tắc thread-bound JDBC; các thao tác phải ở cùng reactive chain/context thích hợp. Với reactive return type cần cấu hình manager tương thích, không suy luận từ ví dụ JDBC imperative.

### 7.3 Ngoại lệ bị bắt, loại exception và rollback

Mặc định với cấu hình `@Transactional` thông thường, `RuntimeException` và `Error` làm rollback; **checked exception** không tự làm rollback nếu chưa cấu hình phù hợp. `JdbcTemplate` thường chuyển lỗi truy cập DB thành `DataAccessException` (unchecked), nên đa số lỗi SQL sẽ kích hoạt quy tắc mặc định.

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // checked IOException thoát khỏi method cũng yêu cầu rollback DB
}
```

Đây là snippet minh họa; `IOException` cần import `java.io.IOException`. Cấu hình `rollbackFor` giải quyết **quy tắc rollback DB**, không làm việc đã xảy ra bên ngoài DB (ví dụ ghi file) tự đảo ngược.

Nếu service **nuốt exception** và trả về bình thường, interceptor có thể xem phạm vi là thành công và commit, trừ khi transaction đã được đánh dấu rollback-only hoặc có điều kiện rollback khác. Ngược lại, một inner scope đã đánh dấu rollback-only có thể khiến commit ngoài thất bại dù caller bắt được exception.

## 8. “Quản lý tài nguyên” bao gồm những gì, và không bao gồm gì?

Một transaction JDBC có nhiều loại vòng đời khác nhau:

| Đối tượng | Ai thường chịu trách nhiệm? | Khi nào kết thúc? |
| --- | --- | --- |
| Transaction scope | `TransactionInterceptor` + `PlatformTransactionManager` | Khi lời gọi/scope transaction hoàn tất theo propagation |
| JDBC `Connection` thuộc transaction | Transaction manager + hạ tầng binding/release | Khi transaction kết thúc và connection được release |
| `PreparedStatement`, `ResultSet` | `JdbcTemplate` hoặc `try-with-resources` của DAO | Khi thao tác SQL tương ứng hoàn tất |
| Connection vật lý trong pool | Connection pool / datasource implementation | Được tái sử dụng; đóng vật lý theo chính sách pool |
| JPA `EntityManager` theo transaction | JPA transaction infrastructure | Theo lifecycle transaction/persistence context |
| File, HTTP call, email, message không enlist | Thư viện/hệ thống riêng | **Không** rollback theo local DB transaction |

Ví dụ: `@Transactional` bao quanh việc ghi vào bảng `orders` rồi gửi email. Nếu gửi email thành công nhưng transaction DB rollback, email **không bị “thu hồi”**. Tương tự, ghi file vào ổ đĩa, gọi REST API hoặc publish message không tự nằm trong local JDBC transaction.

Khi cần hiệu ứng đáng tin cậy sau commit, có thể cân nhắc **transactional outbox** (ghi bản ghi event cùng DB transaction, xử lý gửi sau đó) hoặc event listener ở giai đoạn phù hợp như `@TransactionalEventListener(phase = AFTER_COMMIT)`. Callback sau commit không thay thế cơ chế retry/durable delivery của outbox khi cần độ tin cậy cao.

Với nhiều database hoặc tài nguyên cần commit atomically, một local `DataSourceTransactionManager` đơn lẻ không tự biến chúng thành distributed transaction; cần chiến lược phù hợp (JTA/XA khi điều kiện cho phép, saga/outbox/compensation tùy bài toán). Giới hạn đó thuộc **tài nguyên và hệ thống giao dịch**, không phải do thiếu annotation AOP.

## 9. Cách điều tra khi giao dịch “không có tác dụng”

Đi theo đường gọi từ ngoài vào trong, thay vì chỉ nhìn thấy `@Transactional`:

1. **Đúng bean và proxy chưa?** Service được Spring tạo/inject? Lời gọi đi từ caller qua proxy hay chỉ là `this.method()`? Có method/class không thể proxy không?
2. **Interceptor và manager có hiệu lực không?** Transaction management được bật? Có `PlatformTransactionManager` hoặc `ReactiveTransactionManager` tương thích? Khi nhiều manager, annotation có chọn đúng không?
3. **DAO lấy đúng tài nguyên chứ?** `JdbcTemplate` có cùng `DataSource` với manager? JDBC thuần có dùng `DataSourceUtils` hoặc adapter phù hợp? JPA repository có thuộc đúng persistence unit/manager?
4. **Có đúng transaction scope không?** `REQUIRED` có tham gia transaction ngoài? `REQUIRES_NEW` có tạo transaction độc lập? Có async/thread switch hay reactive context khác?
5. **Quy tắc rollback có thực sự kích hoạt?** Exception nào thoát khỏi method? Có bị catch và nuốt? Có checked exception cần `rollbackFor`? Có scope đánh dấu rollback-only?
6. **Quan sát kết quả sau commit/rollback.** Dùng integration test với DB thật/H2, cố tình phát sinh lỗi giữa hai thao tác rồi đọc lại số liệu từ transaction khác hoặc sau khi transaction kết thúc. Không dùng việc thấy SQL được gửi đi làm bằng chứng đã commit.

Có thể bật logging có chọn lọc ở môi trường thử nghiệm để nhìn thấy begin/join/commit/rollback và hoạt động JDBC; ví dụ `logging.level.org.springframework.transaction=TRACE` và `logging.level.org.springframework.jdbc.datasource=DEBUG` trong Spring Boot. Tránh bật log quá chi tiết ở production vì tốn tài nguyên và có thể lộ dữ liệu nhạy cảm.

Với code imperative, `TransactionSynchronizationManager.isActualTransactionActive()` hữu ích cho **chẩn đoán** xem execution hiện tại có transaction Spring thực sự hay không. Nó không tự chứng minh một DAO đang dùng đúng `Connection` hoặc một thao tác ở hệ thống khác có khả năng rollback; đừng ràng buộc nghiệp vụ thường ngày vào API nội bộ này.

Một lỗi dễ gây ngộ nhận trong kiểm thử: `@Transactional` trên **test method** do Spring Test quản lý có thể thiết lập transaction rồi rollback cuối test, khác với việc gọi service trong application bình thường. Hãy kiểm tra transaction boundary thật của nghiệp vụ khi đánh giá khả năng commit.

## 10. Tự kiểm tra hiểu bài

**Tình huống A.** Service có `@Transactional`; bên trong gọi hai repository JDBC dùng cùng `DataSource` và `JdbcTemplate`. Lệnh thứ hai ném `DataAccessException` chưa bị bắt. Dữ liệu lệnh đầu ra sao?

**Giải thích:** nếu service được gọi qua proxy, transaction thực sự hoạt động và hai repository dùng cùng transaction, unchecked exception khiến transaction rollback theo mặc định; thay đổi chưa commit của lệnh đầu không tồn tại sau rollback. Nếu service không đi qua proxy hoặc các DAO dùng connection độc lập, không thể mặc nhiên kết luận như vậy.

**Tình huống B.** `placeOrder()` gọi `this.saveOrder()` có `@Transactional(REQUIRES_NEW)`. Transaction mới có chắc được tạo không?

**Giải thích:** không. Trong proxy mode, self-invocation không được advice trên `saveOrder()` intercept; thuộc tính `REQUIRES_NEW` của method đó không được áp dụng. Tách bean hoặc thay đổi transaction boundary.

**Tình huống C.** Hai lệnh SQL đã chạy thành công rồi JPA thực hiện `flush()`. Có thể khẳng định chúng đã commit chưa?

**Giải thích:** chưa. `flush()` và commit là hai mốc khác nhau; transaction vẫn có thể rollback sau flush.

**Tình huống D.** Trong transaction DB, service gửi email rồi ném exception. Email có bị rollback cùng DB không?

**Giải thích:** không. Một email đã gửi là hiệu ứng bên ngoài local DB transaction; cần thiết kế cơ chế phối hợp riêng.

## 11. Ghi nhớ mô hình

- **AOP:** “Chặn lời gọi *ở đâu* để đặt ranh giới giao dịch?”
- **Transaction manager:** “Giao dịch nào đang hoạt động, phải commit hay rollback, và tài nguyên nào thuộc về nó?”
- **Data access:** “DAO/repository thực hiện nghiệp vụ dữ liệu bằng tài nguyên nào để tham gia đúng transaction?”
- **Resource management:** “Connection/EntityManager được lấy, gắn ngữ cảnh, dùng lại, cleanup và release đúng lúc ra sao?”
- **Database/resource manager:** “Ai thực sự đảm bảo atomic commit/rollback cho các thay đổi thuộc transaction vật lý?”

Nhớ đường đi: **caller → Spring proxy/AOP → transaction interceptor/manager → service → data-access API → tài nguyên DB → manager commit/rollback và cleanup**. Hiểu đủ đường đi này giúp giải thích cả tình huống hoạt động đúng lẫn phần lớn lỗi “có annotation nhưng không rollback”.

## Tài liệu chính thức để đào sâu

- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)