# Đặt ranh giới giao dịch ở dịch vụ điều phối thay vì từng thao tác nhỏ — Spring REQUIRED

## 1. Vấn đề cần giải quyết

Một yêu cầu nghiệp vụ thường gồm **nhiều thao tác dữ liệu**, nhưng người dùng kỳ vọng chúng là **một kết quả nhất quán**. Ví dụ, chuyển 10 đơn vị từ tài khoản A sang B đòi hỏi hai câu lệnh: trừ A và cộng B. Nếu trừ A thành công rồi cộng B thất bại, hệ thống không được lưu một nửa giao dịch chuyển tiền.

Trong Spring Framework, giải pháp thông dụng là đặt **@Transactional(propagation = Propagation.REQUIRED)** tại phương thức của **dịch vụ điều phối (orchestration/application service)** thực hiện trọn một ca sử dụng. Các repository/DAO được dịch vụ gọi sẽ tham gia transaction đang hoạt động nếu dùng đúng resource và transaction manager.

Điều quan trọng không phải “mọi method đều có @Transactional”, mà là **ranh giới transaction phải bao toàn bộ những thao tác cần cùng commit hoặc cùng rollback**.

Bài học này thuộc phần **REQUIRED** trong module Spring transaction management. Sau khi học, bạn cần:

- Nhận diện một **đơn vị nghiệp vụ cần nguyên tử** (atomic business operation).
- Phân biệt transaction ở **service điều phối** với nhiều transaction ở **các thao tác repository nhỏ lẻ**.
- Hiểu vì sao nhiều method REQUIRED có thể dùng **một physical transaction**, hoặc tạo **nhiều physical transactions** nếu thiếu outer boundary.
- Chọn nơi gắn @Transactional, xác định rollback rules và tránh lỗi self-invocation.
- Chạy một ví dụ Java 17+ minh họa cùng hai lệnh SQL nhưng **kết quả khác nhau khi đặt ranh giới sai**.
- Biết khi nào cần thu hẹp giao dịch, tách side effects hoặc dùng giải pháp nhất quán ngoài DB.

## 2. Ranh giới nghiệp vụ khác ranh giới phương thức kỹ thuật

Giả sử hệ thống có các thao tác kỹ thuật:

1. **debit(A, 10):** trừ 10 từ A.
2. **credit(B, 10):** cộng 10 vào B.
3. **transfer(A, B, 10):** điều phối 1 và 2, đồng thời kiểm tra các điều kiện của nghiệp vụ.

Từng debit/credit có thể là một method hợp lệ ở tầng repository. Nhưng **đơn vị nhất quán** mà người dùng yêu cầu là **transfer**, không phải từng câu UPDATE.

| Tiêu chí | Transaction quanh từng thao tác nhỏ | Transaction quanh dịch vụ điều phối |
| --- | --- | --- |
| Ranh giới | debit() mở/commit riêng; credit() mở/commit riêng nếu không có transaction ngoài | transfer() mở transaction; debit() và credit() cùng tham gia |
| Số transaction vật lý khi gọi debit rồi credit | Thường 2 local transactions khi mỗi method REQUIRED được gọi riêng qua proxy | Thường 1 transaction vật lý với cùng DataSource và manager |
| Nếu credit lỗi sau khi debit đã commit | Không thể tự rollback debit đã commit | Có thể rollback cả debit và credit chưa commit |
| Nơi mô tả quy tắc “cùng thành công/thất bại” | Bị phân mảnh; phụ thuộc trình tự bên ngoài | Nằm ở service thực thi ca sử dụng |
| Khả năng tái sử dụng repository | Mỗi method chỉ bảo đảm transaction riêng | Repository vẫn tái sử dụng được nhưng tham gia outer transaction khi có |
| Độ rõ ràng | Dễ nhầm rằng có nhiều @Transactional là an toàn | Thể hiện rõ ranh giới của nghiệp vụ |

**Nguyên tắc:** transaction thường gắn với **một use case bảo vệ một tập bất biến nghiệp vụ**, trong phạm vi tài nguyên ACID được quản lý. Đừng chọn ranh giới chỉ vì method ngắn hoặc một class chứa nhiều SQL.

### Ví dụ bất biến

Với tài khoản A=100 và B=100, tổng tiền trong hai tài khoản trước và sau một lần chuyển nội bộ 10 phải luôn là 200.

~~~text
Trạng thái đầu:
  A=100, B=100, tổng=200

Đúng — một transaction bao cả hai UPDATE:
  begin
  A := A - 10       (90)
  B := B + 10       (110)
  commit
  => A=90, B=110, tổng=200

Có lỗi sau bước A:
  begin
  A := A - 10       (90 trong transaction)
  ERROR
  rollback
  => A=100, B=100, tổng=200

Sai — mỗi bước tự commit:
  begin debit
  A := A - 10
  commit debit      (A=90)
  ERROR trước credit
  => A=90, B=100, tổng=190 — bất biến bị phá vỡ
~~~

Rollback chỉ có tác dụng lên thay đổi **chưa commit của transaction liên quan**. Nó không “đi ngược thời gian” để hủy transaction debit độc lập đã commit.

## 3. REQUIRED hoạt động như thế nào?

**PROPAGATION_REQUIRED** là propagation mặc định của @Transactional. Khi một method được Spring transaction interceptor quản lý:

- **Chưa có transaction phù hợp:** Spring bắt đầu một physical transaction mới.
- **Đã có transaction phù hợp:** method tham gia transaction đang tồn tại.
- Các scope có thể có **logical transaction boundary riêng**, nhưng khi chúng cùng tham gia REQUIRED, chúng dùng **một physical transaction**.
- Transaction chỉ commit thật khi chủ sở hữu physical transaction hoàn tất thành công; inner method tham gia không được tự commit độc lập.

Dạng gọi tốt:

~~~text
Caller
  |
  v
TransferService.transfer()   @Transactional(REQUIRED)
  |                           |
  |                           +-- Spring tạo JDBC transaction T1
  |
  +-- AccountRepository.debit()  REQUIRED -> tham gia T1
  |
  +-- AccountRepository.credit() REQUIRED -> tham gia T1
  |
  +-- transfer() trả về thành công -> COMMIT T1
      hoặc exception phù hợp -> ROLLBACK T1
~~~

Dạng thiếu service boundary:

~~~text
Caller
  |
  v
TransferService.transferWithoutBoundary()   (không @Transactional)
  |
  +-- AccountRepository.debit()  REQUIRED -> tạo T1 -> COMMIT T1
  |
  +-- logic điều phối gặp exception
  |
  X-- AccountRepository.credit() không được gọi
      Không còn transaction T1 để rollback
~~~

Vì vậy, **REQUIRED không có nghĩa tất cả method trong cùng request HTTP sẽ tự động thuộc cùng một transaction**. Nó chỉ nói mỗi lần lời gọi được intercept sẽ **tham gia transaction đang có hoặc mở transaction mới**. Muốn có “transaction đang có” cho toàn ca sử dụng, phải tạo nó ở tầng điều phối.

### Logical scope và physical transaction

Giả sử outer transfer() và inner debit() đều gắn REQUIRED. Khi gọi đúng qua proxy:

- Scope **transfer** là một logical transaction boundary.
- Scope **debit** có metadata và trạng thái logic riêng; nó tham gia physical transaction của transfer.
- Hai scope không có hai lần commit vật lý.
- Nếu inner scope đánh dấu rollback-only, transaction chung không thể commit mặc dù outer bắt exception và tiếp tục. Tùy cách diễn ra, outer có thể nhận **UnexpectedRollbackException** khi cố commit.

Cần phân biệt **phương thức return** với **physical commit**. debit() return không đồng nghĩa tiền đã được lưu bền vững nếu transfer() vẫn đang giữ transaction.

## 4. Nên đặt @Transactional ở đâu?

### 4.1. Ranh giới khuyến nghị: public application service method

Ví dụ kiến trúc:

~~~java
// Snippet: các repository là Spring beans, cùng DataSource/manager.
@Service
public class TransferService {
    private final AccountRepository accounts;
    private final TransferPolicy policy;

    public TransferService(AccountRepository accounts, TransferPolicy policy) {
        this.accounts = accounts;
        this.policy = policy;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void transfer(long from, long to, long amount) {
        policy.validate(from, to, amount);
        accounts.debit(from, amount);
        accounts.credit(to, amount);
    }
}
~~~

Đây là **mã minh họa, không phải chương trình độc lập**: cần định nghĩa AccountRepository, TransferPolicy, imports và transaction infrastructure. Ý nghĩa: method transfer() đại diện **một ca sử dụng**, còn hai lời gọi repository thực thi các bước trong ca sử dụng đó.

**Không bắt buộc repository phải có @Transactional** nếu chính method service đã mở transaction và repository truy cập đúng resource qua Spring JDBC/JPA. JdbcTemplate/JPA trong cấu hình chuẩn sẽ dùng transaction-bound resource tương ứng.

### 4.2. Nếu repository cũng có REQUIRED thì sao?

~~~java
@Repository
public class AccountRepository {
    @Transactional(propagation = Propagation.REQUIRED)
    public void debit(long id, long amount) {
        // SQL UPDATE ...
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void credit(long id, long amount) {
        // SQL UPDATE ...
    }
}
~~~

Đây cũng là snippet minh họa. Nếu transfer() đã mở transaction T1, hai method repository được gọi qua proxy sẽ **tham gia T1**. Nhưng nếu transfer() **không** có transaction và mỗi repository method là một lời gọi top-level, debit() và credit() thường **mỗi method mở một physical transaction mới**. Annotate từng DAO không tự tạo atomicity cho chuỗi gọi của service.

Có thể đặt REQUIRED ở repository nhằm hỗ trợ những nơi gọi repository trực tiếp; điều đó không thay thế thiết kế service boundary. Ở nhiều dự án, transaction policy tập trung tại service sẽ dễ hiểu và kiểm soát nhất. Chọn và thống nhất cách dùng để tránh các scope khó theo dõi.

### 4.3. Vì sao không đặt @Transactional ở Controller?

Controller nhận HTTP request, mapping input và xác định response. Nếu gắn transaction ở toàn controller, giao dịch có thể bị kéo dài qua deserialize, validation, gọi API khác, tạo response hoặc các bước không liên quan DB. Transaction service thường là ranh giới sạch hơn: đủ rộng để bảo vệ một use case, nhưng không bao các công việc web không cần ACID.

Điều này không phải cấm tuyệt đối transaction ở mọi controller; đây là **khuyến nghị về thiết kế ranh giới**. Hãy đặt policy nơi thể hiện tốt nhất bất biến và nơi Spring proxy thực sự được gọi.

### 4.4. Tại sao không chỉ bọc đúng một câu SQL?

Một SQL UPDATE đơn lẻ đã có tính nguyên tử ở database. Nhưng ca sử dụng nhiều bước có thể cần:
- Ghi đơn hàng, nhiều order lines và cập nhật inventory.
- Ghi payment record và cập nhật trạng thái invoice.
- Đánh dấu một công việc completed và ghi kết quả tương ứng.
- Chuyển số dư giữa hai tài khoản cùng database.

Transaction của từng SQL không đủ bảo đảm **tính nguyên tử xuyên nhiều bước**. Ngược lại, cũng không nên gom mọi việc của một request vào một transaction nếu chúng không cùng một bất biến hoặc dùng nhiều hệ thống ngoài database.

## 5. Sơ đồ trình tự: một transaction với REQUIRED

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as TransferService proxy
    participant TM as JdbcTransactionManager
    participant Repo as Repository proxy
    participant DB as Database
    Caller->>Proxy: transfer()
    Proxy->>TM: getTransaction(REQUIRED)
    TM->>DB: Mở transaction T1
    Proxy->>Repo: debit()
    Repo->>TM: REQUIRED, tham gia T1
    Repo->>DB: UPDATE account A
    Repo-->>Proxy: return (không commit riêng)
    Proxy->>Repo: credit()
    Repo->>TM: REQUIRED, tham gia T1
    Repo->>DB: UPDATE account B
    alt transfer() thành công
        Proxy->>TM: commit outer T1
        TM->>DB: COMMIT T1
    else Lỗi phù hợp rollback
        Proxy->>TM: rollback outer T1
        TM->>DB: ROLLBACK T1
    end
    TM-->>Caller: Cleanup, release connection
~~~

Đường đi thực tế là Spring AOP TransactionInterceptor gọi TransactionManager; manager dùng DataSource và JDBC Connection phù hợp. DBMS mới là nơi thi hành commit/rollback. Một implementation có thể không gửi chuỗi SQL “BEGIN” tường minh; với JDBC, connection thường được chuyển sang chế độ manual commit khi cần.

**Điều kiện cùng một physical transaction:** các lời gọi cần chạy trên transaction context phù hợp (thường là cùng thread với PlatformTransactionManager), sử dụng đúng manager và resource được quản lý. Nếu một repository dùng DataSource khác, connection mở thủ công hoặc method @Async chạy ở thread khác, lời khẳng định “tất cả cùng T1” có thể không đúng.

## 6. Demo Java 17+: cùng SQL, khác vị trí @Transactional

Thực hành sau dùng **Spring Framework 6.2.12 + Spring JDBC + H2 2.3.232**, chạy một Java main. Ta cố ý đặt **@Transactional(REQUIRED)** lên hai method repository để chứng minh một điều quan trọng:

- Khi service điều phối cũng có REQUIRED, repository **tham gia chung transaction ngoài**.
- Khi service điều phối không có transaction, repository tự mở và commit từng transaction riêng.

Mã có ba tình huống: **atomic failure** (rollback an toàn), **fragmented failure** (commit từng bước để lộ trạng thái sai), và **atomic success** (commit đủ hai bước).

### 6.1. Tạo cấu trúc dự án

~~~text
required-boundary-demo/
├── pom.xml
└── src/main/java/demo/RequiredBoundaryDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-boundary-demo</artifactId>
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
            <artifactId>spring-aop</artifactId>
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
                <configuration>
                    <mainClass>demo.RequiredBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven Compiler Plugin dùng Java 17; Spring 6.x yêu cầu Java 17+. H2 in-memory phù hợp học tập nhưng không thay thế integration tests trên DBMS thật khi có yêu cầu concurrency/locking.

### 6.2. Java main đầy đủ

**src/main/java/demo/RequiredBoundaryDemo.java**

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class RequiredBoundaryDemo {
    private RequiredBoundaryDemo() {}

    private static void show(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransferService service = context.getBean(TransferService.class);
            BalanceRepository repo = context.getBean(BalanceRepository.class);

            jdbc.execute("CREATE TABLE account (" +
                    "id INT PRIMARY KEY, " +
                    "balance INT NOT NULL CHECK (balance >= 0))");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 100);

            show(jdbc, "start");
            System.out.println("service proxied=" + AopUtils.isAopProxy(service)
                    + ", repository proxied=" + AopUtils.isAopProxy(repo));

            try {
                service.atomicTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("atomic failure caught: " + ex.getMessage());
            }
            show(jdbc, "after atomic failure");

            try {
                service.fragmentedTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("fragmented failure caught: " + ex.getMessage());
            }
            show(jdbc, "after fragmented failure");

            // Đặt lại dữ liệu để chạy nhánh thành công từ cùng đầu vào.
            jdbc.update("UPDATE account SET balance = 100");
            show(jdbc, "after reset");

            service.atomicTransfer(false);
            show(jdbc, "after atomic success");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:required_boundary;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public BalanceRepository balanceRepository(JdbcTemplate jdbc) {
            return new BalanceRepository(jdbc);
        }

        @Bean
        public TransferService transferService(BalanceRepository repo) {
            return new TransferService(repo);
        }
    }

    public static class BalanceRepository {
        private final JdbcTemplate jdbc;

        public BalanceRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void debit(int amount) {
            int updated = jdbc.update(
                    "UPDATE account SET balance = balance - ? WHERE id = 1",
                    amount);
            if (updated != 1) {
                throw new IllegalStateException("debit row missing");
            }
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void credit(int amount) {
            int updated = jdbc.update(
                    "UPDATE account SET balance = balance + ? WHERE id = 2",
                    amount);
            if (updated != 1) {
                throw new IllegalStateException("credit row missing");
            }
        }
    }

    public static class TransferService {
        private final BalanceRepository repo;

        public TransferService(BalanceRepository repo) {
            this.repo = repo;
        }

        // Đúng: service tạo outer transaction chứa cả hai thao tác.
        @Transactional(propagation = Propagation.REQUIRED)
        public void atomicTransfer(boolean failBetweenSteps) {
            repo.debit(10);
            if (failBetweenSteps) {
                throw new IllegalStateException("simulated failure");
            }
            repo.credit(10);
        }

        // Sai cho use case chuyển tiền: không có outer transaction.
        // Mỗi repository method REQUIRED tự mở/commit khi được gọi.
        public void fragmentedTransfer(boolean failBetweenSteps) {
            repo.debit(10);
            if (failBetweenSteps) {
                throw new IllegalStateException("simulated failure");
            }
            repo.credit(10);
        }
    }
}
~~~

**Tại sao demo có thể phân biệt chính xác ranh giới?**

- ApplicationContext tạo **TransferService** và **BalanceRepository** thành Spring beans; main lấy chúng từ context.
- **@EnableTransactionManagement(proxyTargetClass=true)** kích hoạt giao dịch declarative bằng class-based Spring AOP proxy. Hai class public, method public và không final.
- Cả **JdbcTemplate** và **JdbcTransactionManager** dùng cùng **DataSource**. Không có connection tự mở ngoài quản lý của Spring.
- **atomicTransfer(true)** được gọi qua service proxy nên Spring mở outer transaction. Hai repository method là REQUIRED; debit() tham gia outer. Exception sau debit() làm outer rollback, chưa có commit vật lý.
- **fragmentedTransfer(true)** không có transaction advice ở outer. debit() gọi qua repository proxy nên tự tạo local transaction REQUIRED rồi commit khi debit() trả về. Exception tại coordinator xuất hiện **sau lần commit đó**, không thể hoàn tác debit() đã commit.
- Nhánh thành công **atomicTransfer(false)** thực thi đủ hai UPDATE rồi commit chung.
- Mỗi lệnh show(...) chạy **sau khi lời gọi service đã kết thúc**; nó đọc trạng thái DB được nhìn thấy ở thời điểm đó.

### 6.3. Chạy và đọc stdout

Trên máy có **JDK 17+** và Maven, đứng tại thư mục required-boundary-demo:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến từ các System.out của chương trình** (không tính logging riêng của Spring/Maven):

~~~text
start: A=100, B=100
service proxied=true, repository proxied=true
atomic failure caught: simulated failure
after atomic failure: A=100, B=100
fragmented failure caught: simulated failure
after fragmented failure: A=90, B=100
after reset: A=100, B=100
after atomic success: A=90, B=110
~~~

**Phân tích từng hàng:**

1. **start:** A=100 và B=100.
2. **service proxied=true, repository proxied=true:** hai bean được Spring AOP bọc. Đây là tín hiệu cần thiết để annotation được intercept trong ví dụ; một proxy có thể chứa advice khác nên vẫn phải kiểm chứng behavior.
3. **atomic failure:** debit() thực thi UPDATE nhưng chưa commit riêng; service ném IllegalStateException và transaction manager rollback T1. Số dư vẫn 100/100.
4. **fragmented failure:** debit() mở T2 và commit thành công khi trở ra repository proxy. Service không có transaction nên lỗi sau đó không hủy được T2. A=90, B=100 — tổng chỉ còn 190, sai yêu cầu chuyển tiền.
5. **reset:** một lệnh UPDATE bên ngoài kịch bản nghiệp vụ đưa A và B về 100 để phép thử cuối độc lập với tình huống sai trước đó.
6. **atomic success:** cả debit() và credit() tham gia cùng outer transaction T3 và commit khi service kết thúc. A=90, B=110; tổng vẫn 200.

**Thông điệp quan trọng:** cùng một repository, cùng hai SQL, cùng REQUIRED trên repository, nhưng **vị trí của outer boundary quyết định atomicity của ca sử dụng**.

### 6.4. Lệnh quan sát transaction log (tùy chọn)

Trong ứng dụng Spring Boot có cấu hình logging, bật tạm:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Các dấu hiệu có thể thấy:

~~~text
Creating new transaction ...
Participating in existing transaction
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Initiating transaction commit
Committing JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

Đối với **atomicTransfer(true)**, kỳ vọng một physical transaction bị rollback; với **fragmentedTransfer(true)**, repo.debit tạo physical transaction tự commit rồi mới có exception tại service. Câu chữ log và thứ tự giữa các logger thay đổi theo Spring version, transaction manager, DataSource và cấu hình log. Không xem log “Initiating transaction commit” là bảo đảm DBMS đã commit thành công nếu sau đó có exception.

Đây là mẫu logging cho ứng dụng có Spring Boot; Java main ở ví dụ không mặc nhiên đọc application.properties như Boot. Để kiểm chứng demo, **stdout và trạng thái DB sau lời gọi** là bằng chứng chính.

## 7. Điều gì xảy ra nếu repository KHÔNG có @Transactional?

Với Spring JDBC, repository có thể dùng JdbcTemplate và để toàn bộ policy ở service:

~~~java
// Snippet: repository là Spring bean; không yêu cầu @Transactional tại đây.
public void debit(int amount) {
    jdbcTemplate.update(
            "UPDATE account SET balance = balance - ? WHERE id = 1", amount);
}

public void credit(int amount) {
    jdbcTemplate.update(
            "UPDATE account SET balance = balance + ? WHERE id = 2", amount);
}
~~~

Nếu service gọi hai method ở trên từ **outer @Transactional**, JdbcTemplate nhận connection đã gắn với transaction qua infrastructure Spring, nên hai lệnh vẫn nằm trong một local transaction. **Transaction boundary không bắt buộc đặt ở mọi tầng**.

Nếu gọi repository trực tiếp **ngoài** service transaction, mỗi câu SQL có thể chạy theo chế độ autocommit hoặc cơ chế của DataSource; vì vậy khi nghiệp vụ cần chuỗi atomic, caller cần gọi service transactional.

Với JPA, nguyên tắc kiến trúc tương tự: đặt @Transactional trên application service dùng đúng **JpaTransactionManager** để nhiều repository thao tác cùng persistence context/transaction thích hợp. JPA có thể flush SQL trước khi commit; **flush không phải commit**. Đừng chọn JdbcTransactionManager cho JPA một cách máy móc.

## 8. Khi service gọi nhiều service con

Nhiều ứng dụng có orchestration service gọi các domain/application services khác nhau:

~~~text
CheckoutService.placeOrder()    REQUIRED, tạo T1
   |
   +-- InventoryService.reserve()   REQUIRED -> tham gia T1
   +-- OrderService.create()        REQUIRED -> tham gia T1
   +-- PaymentRecordService.save()  REQUIRED -> tham gia T1
   |
   +-- kết thúc -> commit/rollback T1
~~~

Cách tổ chức này có thể phù hợp nếu ba bước sử dụng cùng database và cùng transaction manager. Các service con vẫn có trách nhiệm riêng, nhưng **orchestrator sở hữu ranh giới nhất quán** cho use case.

Một public method của service con khi được gọi từ use case khác mà không có outer transaction vẫn có thể mở transaction của chính nó do REQUIRED. Đó là đặc tính tái sử dụng của propagation. Tuy nhiên, nếu use case khác đòi hỏi nhiều bước atomic, caller của nó cũng cần một outer boundary đúng.

### 8.1. Nếu service con đặt REQUIRES_NEW thì sao?

REQUIRES_NEW mở một physical transaction độc lập (khi manager hỗ trợ), thường suspend transaction ngoài. Nếu một service con commit bằng REQUIRES_NEW rồi outer rollback, thay đổi của con **có thể vẫn được giữ**.

Ví dụ:
- CheckoutService REQUIRED.
- InventoryService.reserve() lại REQUIRES_NEW và commit.
- OrderService.create() thất bại, outer rollback.
- Hàng có thể đã bị trừ nhưng đơn hàng không tồn tại.

Vì vậy, đừng đổi sang REQUIRES_NEW chỉ để “chắc chắn inner có transaction”. Nếu yêu cầu nghiệp vụ là cùng rollback, **REQUIRED mới là sự lựa chọn tự nhiên**. REQUIRES_NEW chỉ nên dùng khi việc commit độc lập là yêu cầu có chủ đích, và phải đánh giá ảnh hưởng lên resource pool/consistency.

### 8.2. Nếu service con ném lỗi rồi outer bắt lại?

Một inner REQUIRED scope có thể **đánh dấu rollback-only** khi exception thoát qua proxy của nó. Nếu outer bắt exception và return bình thường, đến lúc outer cố commit, physical transaction có thể phải rollback; Spring khi đó thường báo **UnexpectedRollbackException** để caller không tưởng đã commit.

~~~text
Outer REQUIRED T1
  -> Inner REQUIRED T1 ném RuntimeException
  -> Inner interceptor đánh dấu T1 rollback-only
  -> Outer catch và tiếp tục
  -> Outer kết thúc bình thường nhưng cố commit
  -> rollback T1 + UnexpectedRollbackException
~~~

Không phải cứ catch là làm transaction “khỏe lại”. Nếu một operation bên trong đã đánh dấu rollback-only hoặc DBMS transaction không còn dùng được sau lỗi, cần xử lý ở mức boundary thích hợp. Đừng nuốt lỗi rồi trả success khi toàn bộ use case đã không thể commit.

Nếu outer bắt exception phát sinh **trong cùng body** trước khi nó thoát qua bất kỳ transactional inner scope nào, interceptor ngoài có thể không thấy exception và vẫn commit nếu không có rollback-only khác. Cần xét chính xác **exception đi qua proxy nào** chứ không chỉ nhìn try/catch bằng mắt.

## 9. Các yếu tố làm ranh giới tưởng đúng nhưng không hoạt động

### 9.1. Self-invocation bỏ qua proxy

~~~java
// Snippet minh họa — không phải chương trình chạy độc lập.
public void handleRequest() {
    this.transfer(1L, 2L, 10L);
}

@Transactional
public void transfer(long a, long b, long amount) {
    // Hai thao tác dữ liệu ...
}
~~~

Ở chế độ Spring AOP proxy mặc định, lời gọi **this.transfer(...)** bên trong cùng object không đi qua proxy, nên @Transactional trên transfer() có thể không được áp dụng. Nếu handleRequest() không mở transaction, mỗi repository call có thể chạy riêng. Giải pháp phổ biến là gọi transactional method qua **Spring-managed bean khác**, đặt @Transactional ở public entry method hoặc dùng TransactionTemplate khi điều khiển boundary trong code.

### 9.2. @Transactional trên private/final hoặc object tự new

Chỉ đặt annotation không đủ; method cần được transaction infrastructure intercept thật sự. Cách proxy, visibility, class final và phiên bản Spring có ảnh hưởng. Spring 6.x hỗ trợ một số non-public methods với class-based proxy, nhưng **public service method được gọi qua Spring proxy** vẫn là lựa chọn rõ ràng và dễ test cho ranh giới nghiệp vụ. Một object tạo bằng new ngoài Spring context không tự được proxy.

### 9.3. Sai TransactionManager hoặc DataSource

Nếu TransferService dùng transaction manager của DataSource A nhưng repository truy cập DataSource B hoặc tự lấy DriverManager Connection mới, giao dịch ngoài **không tự bao được** thao tác của B. Hai câu UPDATE ở hai database độc lập cần cơ chế phối hợp tài nguyên phù hợp hoặc kiến trúc consistency khác.

Khi có nhiều transaction managers, khai báo rõ:
~~~java
// Snippet: manager "billingTxManager" và repository phù hợp phải tồn tại.
@Transactional(transactionManager = "billingTxManager")
public void settleInvoice() {
    // Ghi vào billing database.
}
~~~

Một annotation chỉ có hiệu lực trong phạm vi resource mà manager quản lý, không phải “transaction toàn cục của cả ứng dụng”.

### 9.4. @Async, Executor và thread khác

Transaction imperative của PlatformTransactionManager thường gắn với thread hiện tại. Nếu service mở transaction T1 rồi giao một việc JDBC cho @Async/Executor chạy ở worker thread, công việc đó **không tự tham gia T1**. Worker cần boundary riêng hoặc kiến trúc bất đồng bộ có thiết kế consistency. Đừng giả định vòng đời HTTP request bao được mọi task con.

Với reactive stack (R2DBC), transaction context được truyền qua Reactor Context và ReactiveTransactionManager; cần dùng nguyên tắc tương ứng của reactive pipeline, không sao chép mù quáng mô hình ThreadLocal JDBC.

### 9.5. Checked exception và rollback rules

Theo mặc định @Transactional thường yêu cầu rollback với RuntimeException hoặc Error, không mặc nhiên rollback checked Exception. Nếu nghiệp vụ ném checked exception sau bước trừ tiền, cần khai báo policy phù hợp:

~~~java
// Snippet: BusinessCheckedException là checked exception của ứng dụng.
@Transactional(rollbackFor = BusinessCheckedException.class)
public void transferWithCheckedRule() throws BusinessCheckedException {
    accounts.debit(...);
    throw new BusinessCheckedException("rejected");
}
~~~

Ở Spring Framework 6.2, dự án còn có thể thay đổi mặc định rollback bằng rollbackOn=ALL_EXCEPTIONS khi bật annotation transaction management. Khi chẩn đoán hãy xác minh chính sách thực tế, không tự cho rằng mọi Exception đều rollback. Phần mã bên trên **không độc lập**; dấu ... chỉ ký hiệu đối số cần được thay bằng dữ liệu hợp lệ của ứng dụng, không phải lệnh chạy.

## 10. Đặt transaction đủ rộng, nhưng không quá rộng

**Đúng ranh giới** không có nghĩa cứ càng dài càng an toàn. Nếu method transaction bao cả gọi HTTP, gửi email, tải file lớn hoặc xử lý tính toán nặng, connection và DB locks có thể bị giữ lâu, gây giảm throughput hoặc deadlock.

So sánh:

| Phạm vi | Vấn đề | Hướng thiết kế |
| --- | --- | --- |
| Chỉ một SQL, trong khi use case có nhiều SQL cần atomic | Transaction quá hẹp, partial commit | Mở outer REQUIRED ở service điều phối |
| Toàn request, bao cả remote API và xử lý lâu | Transaction quá rộng, giữ connection/lock | Chuẩn bị dữ liệu trước, mở transaction sát nhóm DB writes, kết thúc sớm |
| Một use case ghi nhiều bảng cùng database | Thường phù hợp với outer REQUIRED | Service boundary bao các repository calls |
| Một use case ghi hai DB/messaging system | Một local transaction không bao được tất cả | Xác định JTA/XA hay outbox/saga/idempotency |
| Một batch gồm hàng nghìn item độc lập | Transaction quá lớn, rollback tốn kém | Chia chunk theo tính nguyên tử nghiệp vụ; ghi rõ consistency giữa chunks |
| Một đơn hàng và các dòng chi tiết bắt buộc đi cùng nhau | Không nên chia thành nhiều commits | Một transaction bao order header + lines + inventory update cần liên quan |

Có thể tách phần **thu thập đầu vào/đọc dữ liệu ít rủi ro hoặc gọi mạng** ra khỏi transaction, nhưng cần xét lại race conditions: dữ liệu được validate trước transaction có thể thay đổi trước khi ghi. Với những điều kiện cần được bảo đảm, kiểm tra lại dưới transaction, dùng constraint, locking hoặc optimistic version phù hợp.

Một workflow có thể chia thành nhiều use cases độc lập: mỗi use case có transaction riêng. Điều cần tránh là **tách một bất biến đơn nhất thành các commits không thể phối hợp**.

### 10.1. Thiết kế một use case đặt hàng

~~~text
HTTP request
  |
  +-- Parse và validate cấu trúc payload (ngoài transaction)
  |
  +-- CheckoutApplicationService.placeOrder()   @Transactional(REQUIRED)
        |
        +-- Kiểm tra tồn kho bằng dữ liệu/khóa thích hợp
        +-- Reserve inventory
        +-- Insert order header
        +-- Insert order lines
        +-- Insert outbox event trong cùng DB (nếu cần)
        +-- COMMIT hoặc ROLLBACK tất cả DB changes
  |
  +-- Sau commit: publish/retry outbox event bằng worker riêng
  |
  +-- HTTP response
~~~

Điểm mạnh: các thay đổi cùng DB và outbox event nằm trong một local transaction. **Việc gửi message ra broker** sau đó thường không nằm trong transaction JDBC; outbox + worker xử lý retry/idempotency giúp quản lý sự khác biệt này. Cũng không nên gửi email trong transaction rồi mong rollback xóa email đã phát.

### 10.2. Không làm transaction dài do remote call

Nếu phải gọi cổng thanh toán trước khi ghi đơn hàng, cần thiết kế consistency theo nghiệp vụ. Không có một annotation @Transactional nào làm lời gọi HTTP đến provider bên ngoài tham gia JDBC commit/rollback. Tùy yêu cầu, có thể chọn reservation, retry idempotent, state machine, outbox/saga hoặc giao dịch phân tán có kiểm chứng khả năng hỗ trợ; tránh giả định rollback DB cũng rollback hệ thống ngoài.

## 11. Isolation, timeout và readOnly: ai định nghĩa khi inner REQUIRED tham gia?

Một scope inner REQUIRED có thể khai báo isolation, timeout hay readOnly riêng. Nhưng nếu outer đã mở **physical transaction** thì những thuộc tính đặc trưng ở mức connection/transaction thường theo **outer boundary**; Spring mặc định có thể **bỏ qua** thuộc tính inner khác biệt khi tham gia.

Ví dụ:

~~~java
// Snippet minh họa policy; phải gọi đúng qua Spring proxy.
@Transactional(isolation = Isolation.READ_COMMITTED, timeout = 15)
public void placeOrder() {
    reserveInventory(); // Method trong có REQUIRED khác isolation.
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE,
    timeout = 3
)
public void reserveInventory() {
    // ...
}
~~~

Nếu reserveInventory() chỉ tham gia outer transaction, không nên suy đoán isolation tự đổi sang SERIALIZABLE hoặc timeout thành 3 giây. Nếu thiết kế yêu cầu strict match, AbstractPlatformTransactionManager có **validateExistingTransaction=true** để phát hiện một số mismatch khi tham gia. Cách đúng vẫn là đặt **chính sách cấp transaction vật lý** ở owner boundary phù hợp.

readOnly=true chỉ là hint mà JDBC/JPA/DBMS có thể hỗ trợ khác nhau; không dùng nó thay quyền truy cập DB. Isolation cao có thể giảm concurrency; hãy kiểm chứng bằng tích hợp với DB thật.

## 12. Các kiểu lỗi và dấu hiệu cần quan sát

| Hiện tượng | Giải thích có thể | Hành động kiểm tra |
| --- | --- | --- |
| Trừ A thành công, cộng B lỗi nhưng A vẫn giảm | Debit commit riêng vì không có outer service transaction | Bật transaction log; xác nhận proxy/manager, đặt REQUIRED ở service |
| Service có @Transactional mà không rollback | Self-invocation, bean tạo bằng new, exception bị catch hoặc checked exception không khớp | Kiểm tra entry qua proxy, rollback rules, exception thoát ra |
| Repository có REQUIRED nhưng mỗi câu SQL vẫn commit | Mỗi method được gọi như top-level khi không có transaction ngoài | Xác định transaction owner và vị trí caller |
| Outer ném UnexpectedRollbackException | Inner REQUIRED đã set rollback-only rồi outer cố commit | Theo dõi inner exception và logical scopes |
| Có hai transaction managers và dữ liệu lệch | Sai manager/DataSource/entity manager | Kiểm tra tên manager và resource thực tế |
| REQUIRES_NEW lưu dấu phụ dù outer rollback | Đây là independent physical transaction, không còn REQUIRED đồng bộ | Xác định độc lập commit là chủ đích hay lỗi thiết kế |
| Không nhìn thấy transaction trên method | AOP proxy chưa bật, method không thể intercept hoặc gọi nội bộ | Kiểm tra @EnableTransactionManagement, bean/proxy, method signature |
| Database deadlock/pool timeout | Transaction giữ lock quá lâu hoặc nhiều REQUIRES_NEW | Xem thời lượng transaction, locks, pool metrics |
| Đã flush JPA nhưng outer rollback | Flush chưa phải commit; transaction cuối bị rollback | Đọc lại dữ liệu bằng transaction/EntityManager mới |
| Local commit xong nhưng message publish thất bại | Broker không nằm trong JDBC transaction | Dùng outbox/retry/idempotency hoặc thiết kế thích hợp |

Có thể bật logger:
~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Quan sát việc **Creating new transaction** hay **Participating in existing transaction**, sau đó **Initiating transaction commit/rollback** và **Releasing JDBC Connection**. Log là dấu vết, không thay thế kiểm tra trạng thái DB sau transaction. Trong nhiều request đồng thời cần correlation ID để ghép đúng các dòng.

## 13. Kiểm thử ranh giới thật sự

Một integration test tốt phải chứng minh transaction không bị chia nhỏ, thay vì chỉ mock các repository:

1. Khởi tạo DB với A=100, B=100.
2. Gọi service qua Spring bean proxy với failBetweenSteps=true.
3. Đọc số dư sau khi exception được bắt **ngoài transaction boundary**.
4. Khẳng định A=100 và B=100 — không có partial commit.
5. Gọi nhánh thành công; khẳng định A=90, B=110.
6. Thử một nhánh repository riêng để nhìn thấy sự khác biệt khi không có service boundary.
7. Nếu dùng JPA, kiểm tra bằng EntityManager/transaction mới thay vì đọc entity cũ trong persistence context.
8. Nếu điều kiện concurrency quan trọng, chạy integration tests với DBMS thật, các transaction độc lập và dữ liệu trùng lặp/locking phù hợp.

Ví dụ bảng kỳ vọng:

| Ca kiểm thử | Bắt đầu | Tình huống | Trạng thái sau kết thúc |
| --- | --- | --- | --- |
| Atomic success | A=100 B=100 | Service REQUIRED, 2 bước đều thành công | A=90 B=110 |
| Atomic rollback | A=100 B=100 | Service REQUIRED, lỗi sau debit | A=100 B=100 |
| Fragmented rollback không thể hồi tố | A=100 B=100 | Service không transaction, debit repository tự commit, sau đó lỗi | A=90 B=100 |
| Checked exception | A=100 B=100 | Service ném checked exception | Phụ thuộc rollbackFor/default policy |
| Inner REQUIRED đánh dấu rollback-only | A=100 B=100 | Outer định commit nhưng inner yêu cầu rollback | DB rollback; caller có thể nhận UnexpectedRollbackException |

**Cảnh báo về @Transactional ở test:** Spring TestContext có thể mặc định rollback transaction của test ở cuối; việc đọc dữ liệu trong cùng test transaction không chứng minh đã có physical commit. Để kiểm tra transaction của service, thiết kế test boundary hoặc dùng TestTransaction/transaction độc lập phù hợp. Chạy demo main ở phần 6 giúp tránh nhầm lẫn này.

### Kiểm thử trước/sau thay đổi kiến trúc

Khi chuyển @Transactional từ DAO lên service, không chỉ sửa annotation. Cần:

- Ghi lại những **use cases** đang gọi nhiều repository methods.
- Xác định điểm commit hiện tại và những partial updates đã có thể xảy ra.
- Chọn service boundary mới, bảo đảm repository và manager cùng resource.
- Giữ rollback rules cho checked/business exception nếu có.
- Tạo regression tests cho lỗi sau bước đầu, giữa các bước và khi commit.
- Test các lệnh gọi service qua Spring bean/proxy, không gọi new object trong unit test rồi kết luận transaction chạy.
- Nếu có nhiều managers và database, phải phân loại rõ use cases không thể nằm trong một local transaction.

## 14. Những câu hỏi tự kiểm tra

**Câu 1.** Hai repository methods đều có @Transactional(REQUIRED). Có bảo đảm transfer() gọi chúng sẽ atomic không?  
**Trả lời:** Không nếu transfer() không có outer transaction. Mỗi repository method có thể tự tạo và commit physical transaction riêng.

**Câu 2.** Nếu TransferService.transfer() có REQUIRED, còn repository methods KHÔNG có annotation, JdbcTemplate có tham gia transaction không?  
**Trả lời:** Có, khi chúng dùng đúng Spring-managed DataSource/JdbcTemplate, thực thi trong transaction context của service và transaction manager phù hợp. Repository không cần tạo boundary mới.

**Câu 3.** Nếu outer transfer() và inner debit() cùng REQUIRED, debit() return có nghĩa debit đã commit không?  
**Trả lời:** Không. Inner tham gia cùng physical transaction; outer owner quyết định commit/rollback cuối cùng.

**Câu 4.** Nếu inner debit() dùng REQUIRES_NEW rồi commit, outer rollback có hủy debit không?  
**Trả lời:** Thông thường không. Inner REQUIRES_NEW là physical transaction độc lập; đây là lý do phải lựa chọn propagation theo yêu cầu nghiệp vụ.

**Câu 5.** Vì sao @Transactional tại controller thường không phải lựa chọn đầu tiên?  
**Trả lời:** Controller có thể bao cả các bước web/IO không cần giữ DB transaction. Application service boundary rõ hơn và dễ tối ưu thời gian giữ connection/locks.

**Câu 6.** Vì sao outer bắt exception từ inner REQUIRED vẫn có thể nhận UnexpectedRollbackException?  
**Trả lời:** Inner transactional scope có thể đã đánh dấu physical transaction rollback-only. Outer cố commit nhưng DB phải rollback, Spring báo caller không thể coi đó là commit thành công.

**Câu 7.** Đặt annotation ở service rồi gọi this.transfer() trong cùng object có vấn đề gì?  
**Trả lời:** Trong proxy mode, self-invocation thường không đi qua proxy nên metadata trên transfer() không tạo transaction mới. Cần thiết kế entrypoint qua Spring bean proxy.

**Câu 8.** Một use case ghi đơn hàng ở DB A và gửi email. @Transactional ở service có thể rollback email khi DB lỗi không?  
**Trả lời:** Không. Email là side effect ngoài local JDBC transaction; cần quy trình gửi sau commit, outbox, retry hoặc bù trừ tùy yêu cầu.

**Câu 9.** Có phải transaction càng bao nhiều method càng tốt?  
**Trả lời:** Không. Ranh giới phải bao những DB operations cần cùng ACID, nhưng không nên giữ transaction xuyên network call hoặc xử lý lâu không cần thiết.

**Câu 10.** Inner REQUIRED khai báo SERIALIZABLE còn outer đã mở READ_COMMITTED; isolation nào thường áp dụng?  
**Trả lời:** Thuộc tính của transaction vật lý ngoài thường giữ nguyên. Spring mặc định có thể bỏ qua isolation khai báo ở inner khi tham gia; cần xem validateExistingTransaction nếu muốn phát hiện mismatch.

## 15. Kết luận: chọn boundary theo tính nhất quán

- **Phương thức điều phối use case là nơi tự nhiên để đặt REQUIRED** nếu nhiều thao tác trên cùng transaction resource phải cùng commit/rollback.
- **Repository là đơn vị truy cập dữ liệu**, không tự quyết định điểm kết thúc của toàn bộ nghiệp vụ; REQUIRED ở repository chỉ *tham gia transaction đang có hoặc tạo mới khi không có*.
- **Một physical transaction cho một bất biến nghiệp vụ** giúp tránh trạng thái “đã trừ nhưng chưa cộng”.
- **Không chỉ nhìn annotation:** cần đảm bảo lời gọi qua proxy, đúng manager/resource, rollback rules và transaction context.
- **Không mở transaction quá rộng:** tránh giữ locks/connection qua HTTP hoặc công việc dài; hệ thống nhiều tài nguyên cần thiết kế consistency riêng.
- **Xác minh bằng integration test:** cố ý lỗi sau bước đầu rồi đọc DB sau transaction để chứng minh không có partial commit.

Trong ví dụ Java, cùng hai repository methods đã cho hai kết quả khác nhau: outer REQUIRED rollback an toàn, còn outer không transaction để lại partial commit. Đó là minh họa trực tiếp lý do **đặt ranh giới ở dịch vụ điều phối, không chỉ ở từng thao tác nhỏ**.

## Tài liệu tham khảo

- [Spring Framework — Transaction Propagation, đặc biệt PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
