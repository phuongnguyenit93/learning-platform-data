# So sánh độ ghép nối của `TransactionTemplate` với quản lý giao dịch khai báo

## Kết luận trước: sự khác biệt nằm ở đâu?

Trong Spring Framework, **`TransactionTemplate` (programmatic transaction management)** khiến đoạn code **trực tiếp gọi API transaction của Spring** để xác định ranh giới giao dịch. Ngược lại, **quản lý giao dịch khai báo** — phổ biến nhất là `@Transactional` — đặt *metadata* bên ngoài luồng xử lý nghiệp vụ; transaction interceptor và transaction manager điều phối begin/commit/rollback mà phương thức nghiệp vụ không phải tự viết callback quản lý transaction.

Theo tài liệu Spring, `TransactionTemplate` **liên kết trực tiếp** (*couples*) code ứng dụng với hạ tầng và API transaction của Spring. Đây là nhược điểm về ghép nối nguồn mã, nhưng không có nghĩa cách này sai hoặc luôn khó bảo trì. Nó đổi lại khả năng chủ động đặt transaction boundary rất rõ, điều khiển rollback bằng `TransactionStatus`, gán tên transaction và lựa chọn chính sách riêng cho một đoạn code.

**`@Transactional` không hoàn toàn “không ghép nối” với Spring.** Annotation `org.springframework.transaction.annotation.Transactional` vẫn là một import của Spring, và hệ thống vẫn cần `TransactionManager`, AOP proxy hoặc AspectJ weaving phù hợp. Điểm khác là **mức độ ghép nối trong thân phương thức và mô hình tổ chức code**:

- Với `TransactionTemplate`, service phải biết khái niệm callback, template và có thể cả `TransactionStatus`.
- Với `@Transactional`, service chủ yếu mô tả transaction semantics qua annotation; thân method tập trung vào logic.
- Với cấu hình khai báo bằng **XML advice/pointcut** hoặc một façade do ứng dụng định nghĩa, business class có thể không cần import cả API transaction lẫn annotation Spring, nhưng việc này phải trả chi phí cấu hình và quy ước boundary ở nơi khác.
- **Cả hai cách đều cần Spring transaction infrastructure ở runtime.** Đổi cú pháp không khiến JDBC/JPA/DB transaction tự vận hành nếu không có transaction manager.

Bài này thuộc chủ đề cha **TransactionTemplate**, tập trung vào **độ ghép nối với quản lý khai báo**: ghép nối ở source code, hạ tầng, khả năng kiểm thử, refactor, AOP/self-invocation, sự linh hoạt và các tiêu chí chọn giải pháp. Ví dụ đầy đủ Java 17/Spring JDBC/H2 dùng **cùng một core xử lý nghiệp vụ**, lần lượt chạy với `TransactionTemplate` và `@Transactional`, để chứng minh sự khác nhau chủ yếu nằm ở **cách tổ chức transaction boundary**, không ở bản chất commit/rollback của database.

---

## 1. “Độ ghép nối” (coupling) trong transaction management là gì?

**Coupling** là mức độ một thành phần cần biết hoặc phụ thuộc vào thành phần khác để biên dịch, thực thi, kiểm thử và thay đổi hành vi. Trong ngữ cảnh transaction, ta nên tách ít nhất bốn chiều thay vì chỉ đếm số annotation.

| Chiều ghép nối | Câu hỏi cần trả lời |
| --- | --- |
| **Source/API coupling** | Business class có import `TransactionTemplate`, `TransactionStatus`, `@Transactional` hay trực tiếp gọi `PlatformTransactionManager` không? |
| **Configuration coupling** | Ranh giới và thuộc tính transaction được khai báo trong method, trong adapter, trong XML, hay trong configuration riêng? |
| **Runtime/infrastructure coupling** | Code dựa vào một `TransactionManager`, datasource/JPA persistence unit, Spring context và AOP proxy thế nào? |
| **Behavioral coupling** | Logic nghiệp vụ có giả định caller đã có transaction, hoặc một inner call được proxy advice chặn, hay đang giữ transaction trong callback không? |

Ví dụ service triển khai một bước nhập kho:

```java
@Transactional
public void receiveStock(Shipment shipment) {
    warehouse.updateQuantity(shipment);
    auditRepository.recordReceipt(shipment);
}
```

Đây là **fragment minh họa**, cần khai báo các dependency và types. Method import annotation của Spring, nhưng không tự biết cách bắt đầu hoặc commit transaction; những việc đó là trách nhiệm của infrastructure.

So với:

```java
public void receiveStock(Shipment shipment) {
    transactionTemplate.executeWithoutResult(status -> {
        warehouse.updateQuantity(shipment);
        auditRepository.recordReceipt(shipment);
    });
}
```

Đây cũng là **fragment minh họa**. Method có thêm một đối tượng `TransactionTemplate` và callback API của Spring. Điều đó làm **transaction concern lộ rõ hơn trong flow**, vừa có lợi khi cần boundary cục bộ, vừa tạo source-level dependency trực tiếp vào Spring trong class.

Không thể chỉ đọc hai fragment và kết luận “cách thứ hai chạy chậm hơn” hay “cách thứ nhất tuyệt đối độc lập với framework”; hiệu năng phụ thuộc DB, AOP, SQL, contention và kiến trúc.

## 2. `TransactionTemplate`: transaction được lập trình trực tiếp

`TransactionTemplate` nằm trong package:

```java
org.springframework.transaction.support.TransactionTemplate
```

Cách dùng thông thường:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

String result = template.execute(status -> {
    repository.insert();
    return "created";
});
```

Đây là **fragment**, cần `transactionManager`, `repository` và imports. Khi gọi `execute(...)`, template lấy transaction theo các thuộc tính cấu hình, chạy callback và điều phối commit/rollback/cleanup. Nếu callback ném `RuntimeException` hoặc `Error`, template xử lý rollback theo contract của nó rồi cho exception thoát ra.

Khi không cần trả kết quả:

```java
template.executeWithoutResult(status -> {
    repository.update();
});
```

Callback có thể dùng `status.setRollbackOnly()` trong một tình huống nghiệp vụ đã quyết định không được commit:

```java
String outcome = template.execute(status -> {
    boolean canReserve = repository.isAvailable();
    if (!canReserve) {
        status.setRollbackOnly();
        return "NOT_AVAILABLE";
    }
    repository.reserve();
    return "RESERVED";
});
```

Các fragment chưa phải chương trình độc lập. Trong nhánh `NOT_AVAILABLE`, template được yêu cầu rollback và trả về một kết quả bình thường. **Caller phải hiểu kết quả này không đại diện cho một transaction đã commit.** Ngoài ra, nếu template dùng propagation `REQUIRED` và đang tham gia transaction của caller, rollback-only có thể ảnh hưởng transaction chung; không nên tự coi nó là “rollback riêng của callback”.

### 2.1. API coupling cụ thể

Một service dùng template thường giữ:

```java
private final TransactionTemplate transactionTemplate;
```

và nhận `PlatformTransactionManager` hoặc chính template bằng constructor injection. Điều đó đặt các type của Spring transaction API vào source code service. Nếu sau này ứng dụng chuyển sang một runtime không dùng Spring, phải thay hoặc bọc những lệnh gọi đó.

Tuy nhiên, **không nhất thiết toàn bộ domain model phải phụ thuộc Spring**: có thể đặt template ở lớp application coordinator/adapter, còn core nghiệp vụ dùng interface repository hoặc abstraction riêng. Đây là một quyết định về kiến trúc chứ không phải một giới hạn bắt buộc của template.

### 2.2. Template khác tự gọi `getTransaction`, `commit`, `rollback`

Có thể quản lý thủ công bằng `PlatformTransactionManager`, `TransactionDefinition` và `TransactionStatus`, nhưng như vậy business code phải xử lý lifecycle và exception an toàn:

```java
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

Đây là **fragment minh họa**, `manager`, `definition`, `executeBusinessLogic()` cần được định nghĩa. Một mã thủ công đầy đủ còn phải xử lý exception ở commit/rollback đúng cách để tránh rollback lặp hoặc che lỗi ban đầu. `TransactionTemplate` loại bỏ nhiều boilerplate đó; so sánh với `@Transactional` nên dùng **template**, không dùng mã quản lý `PlatformTransactionManager` bằng tay như đại diện bắt buộc của programmatic management.

## 3. Quản lý khai báo: `@Transactional` đặt policy bên ngoài method body

Trong cấu hình Spring Java, kiểu khai báo thường là:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Đây là **fragment**, cần `DataSource` được cấu hình và các imports. Hạ tầng `@EnableTransactionManagement` nhận metadata `@Transactional`, tạo transaction advisor/interceptor và proxy phù hợp. Ở XML application context, có thể bật bằng `<tx:annotation-driven/>`.

Service khai báo:

```java
@Service
public class BookingService {
    private final BookingRepository bookings;

    public BookingService(BookingRepository bookings) {
        this.bookings = bookings;
    }

    @Transactional
    public void book(long seatId) {
        bookings.reserve(seatId);
        bookings.recordReservation(seatId);
    }
}
```

Đây là fragment, chưa có repository implementation. Không có `TransactionTemplate` hoặc `TransactionStatus` trong thân `book()`. Transaction semantics thuộc annotation, còn interceptor và manager thực thi.

Luồng khái quát:

```text
Caller
  |
  +--> Spring-managed proxy của BookingService
          |
          +--> TransactionInterceptor
          |       +-- đọc @Transactional metadata
          |       +-- manager.getTransaction(definition)
          |
          +--> target.book(seatId)
          |
          +--> manager.commit(...) hoặc rollback(...)
```

Code nghiệp vụ ít phải biết transaction API, nhưng nó có một **implicit precondition**: method phải được gọi theo cách hạ tầng advice thực sự intercept.

### 3.1. Annotation vẫn là một dạng ghép nối

`@Transactional` của Spring mang import và thuộc tính đặc thù như `Propagation.REQUIRES_NEW`, `Isolation.SERIALIZABLE`, `rollbackFor`, `readOnly`, `timeout`, `transactionManager`. Chúng là dependency nguồn mã nếu bạn khai báo trực tiếp trong business service.

Có thể sử dụng `jakarta.transaction.Transactional` trong một số mô hình Spring phù hợp, nhưng semantics và hệ thuộc tính không hoàn toàn giống mọi lựa chọn của annotation Spring. Không nên xem thay annotation là bước di chuyển framework hoàn toàn miễn phí.

Nếu muốn **source-level framework neutrality** tối đa cho domain logic, hãy để annotation bên ngoài domain core hoặc cấu hình transaction advice theo method pointcut (phần 10). Khi đó coupling được **di chuyển ra configuration/adapter**, chứ không biến mất.

### 3.2. Runtime coupling vẫn tồn tại

Không có transaction manager hợp lệ, không có datasource/persistence resource được điều phối, hoặc method không đi qua Spring proxy, thì `@Transactional` không tự cung cấp commit/rollback. Cả template và khai báo đều dựa vào hạ tầng transaction của Spring và DB backend.

Đổi sang declarative không bảo đảm vận hành với hai datasource độc lập trong một distributed transaction. Manager nào được chọn và resource nào được điều phối vẫn là trách nhiệm thiết kế.

## 4. Ma trận so sánh theo các chiều coupling

| Tiêu chí | `TransactionTemplate` | `@Transactional` khai báo |
| --- | --- | --- |
| Dependency trong source code | Dùng `TransactionTemplate` và có thể `TransactionStatus`, `PlatformTransactionManager` | Thường chỉ import annotation; không trực tiếp gọi API lifecycle trong body |
| Ranh giới transaction nhìn từ method | **Tường minh** quanh khối `execute(...)` | **Khai báo** ở method/class, thực thi bởi AOP advice |
| Mức trộn transaction với nghiệp vụ | Cao hơn nếu viết template ngay trong business flow | Thường thấp hơn vì transaction code nằm ngoài method body |
| Dễ đọc nếu phần lớn method transactional | Nhiều callback/lặp lại template usage | Nhìn annotation và đọc business flow tự nhiên |
| Dễ đặt boundary cho một khối nhỏ | Thuận lợi, có thể đặt trước/sau nhiều bước phi transactional | Cần chọn một annotated method phù hợp hoặc tách bean/boundary |
| Dựa vào AOP proxy cho transaction | Không, `template.execute()` trực tiếp là boundary | Có với `proxy` mode mặc định; có thể dùng AspectJ khi weave |
| Self-invocation | Callback vẫn thực thi nếu lời gọi nội bộ thực sự chạy `execute()` | `this.otherMethod()` không trigger inner advice ở proxy mode |
| `rollback-only` theo điều kiện nội bộ | Có `status.setRollbackOnly()` ngay trong callback | Có thể dùng API trực tiếp nhưng làm body ghép Spring; thông dụng hơn là exception/rollback rules |
| Quy tắc rollback checked exception | Cần thể hiện rõ bằng cách ném lỗi phù hợp, wrap hoặc đánh dấu rollback-only | Khai báo `rollbackFor`/`noRollbackFor`; vẫn cần exception thoát advice |
| Configuration tái sử dụng | Template có cấu hình propagation/isolation/timeout; dùng các instance ổn định phù hợp | Metadata annotation/class/composed annotation, hoặc XML advice/pointcut |
| Transaction name tùy ý | Có thể đặt programmatically | Tên declarative thường tự sinh `fully.qualified.Class.method` |
| Tác động tới unit test service | Cần template/manager hoặc đặt transaction orchestration ngoài core | Logic body có thể unit test như POJO, nhưng unit test không kiểm chứng transaction thật |
| Integration testing | Phải kiểm tra transaction resource/rollback, như declarative | Phải kiểm tra proxy/context/rollback, ngoài resource |
| Chi phí setup | Không cần bật annotation proxy cho chính template | Cần bật annotation-driven advice / AOP configuration |
| Trường hợp thích hợp | Ít operation, boundary động/cục bộ, rõ từng callback | Nhiều use cases transactional, policy ổn định ở service method |

**Đọc bảng đúng cách:** Đây là so sánh **cách tổ chức**, không phải khẳng định một hướng luôn “tốt hơn” hay về performance. Nếu đặt `TransactionTemplate` trong một transaction adapter riêng, phần domain core có thể rất ít coupling. Nếu `@Transactional` được gắn khắp domain entity hoặc dùng self-invocation không đúng, declarative cũng có thể gây rối.

## 5. Vì sao Spring khuyên dùng cách nào trong từng tình huống?

Tài liệu Spring về lựa chọn programmatic và declarative nêu hướng dẫn:

- **Ít transactional operations:** programmatic `TransactionTemplate` có thể là lựa chọn hợp lý, nhất là khi không muốn thiết lập transaction proxies chỉ để xử lý vài đoạn cập nhật.
- **Nhiều transactional operations:** declarative thường đáng đầu tư vì tách transaction management khỏi business logic và chi phí cấu hình trong Spring tương đối thấp.

Đây là **heuristic**, không phải ngưỡng tuyệt đối kiểu “dưới 10 method phải dùng template”. Mức độ thay đổi policy, team familiarity, kiến trúc domain, khả năng test và yêu cầu rollback đặc biệt cũng quan trọng.

### 5.1. Ứng dụng nhiều service có contract ổn định

Ví dụ hàng chục service methods chỉ cần `REQUIRED`, `readOnly=true` cho query và rollback theo rule thống nhất: dùng `@Transactional` ở application service giúp nhận diện boundary nhanh và giảm callback lặp lại. Logic business không phải biết `TransactionStatus`.

### 5.2. Một operation có boundary đặt giữa method

Ví dụ ứng dụng có một luồng dài:

```text
Validate request (không giữ DB transaction)
   |
   v
Gọi API báo giá ngoài (không giữ DB transaction)
   |
   v
Chỉ một khối INSERT/UPDATE phải atomic
   |
   v
Sau commit mới gửi thông báo
```

Với template, đặt `execute(...)` chỉ quanh khối DB rất trực tiếp. Với declarative, vẫn có thể tách thành một Spring bean method `@Transactional` để được cùng kết quả. Phương án nào rõ hơn phụ thuộc kiến trúc; không nên kết luận annotation không thể đặt một transaction boundary nhỏ.

### 5.3. Domain thuần và adapter kiến trúc

Một domain core nên tập trung vào những quy tắc như tính giá, hạn mức, phân bổ kho; nó có thể dùng các interface thuần Java. `TransactionTemplate` có thể nằm ở application coordinator gọi domain, hoặc `@Transactional` ở application service, không phải ở entity/value object. Cả hai đều có thể đạt mục tiêu domain purity nếu tổ chức đúng.

## 6. Transaction semantics có khác nhau về bản chất không?

**Không.** Khi được cấu hình tương đương và gọi qua đúng boundary, cả hai cách đều tương tác với `PlatformTransactionManager` và resource backend, nên các semantics cơ bản như `REQUIRED`, `REQUIRES_NEW`, isolation, timeout, read-only, commit/rollback có thể giống nhau.

Ví dụ programmatic:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(20);
template.setReadOnly(false);
```

Và declarative:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 20,
    readOnly = false
)
public void updateStock() {
    // ...
}
```

Đây là **hai fragment minh họa**. Chúng có thể yêu cầu tương đương khi manager/resource giống nhau, nhưng không bảo đảm mọi tình huống runtime giống hệt: `@Transactional` cần được advice intercept; template cần callback thực sự được gọi; cấu hình mặc định và vị trí gọi phải tương thích.

### 6.1. `REQUIRED` không luôn mở transaction mới

Dù gọi template hay annotation, `REQUIRED` tham gia transaction có sẵn nếu có. `TransactionTemplate` **không tự tạo transaction độc lập** chỉ vì nó được gọi programmatically. Nếu thật sự muốn một physical transaction khác khi đã có T1, cần chọn `REQUIRES_NEW` và hiểu suspend/resource requirements.

### 6.2. Exception và commit timing

- Với template, exception có thể thoát ra từ `execute(...)` khi callback chạy hoặc ở giai đoạn commit.
- Với declarative, exception có thể thoát khỏi **lời gọi proxy** khi target method chạy hoặc khi interceptor commit sau khi target đã return.
- Cả hai có thể phát sinh `UnexpectedRollbackException` nếu transaction chung đã bị đánh dấu rollback-only nhưng outer scope vẫn cố commit.
- Trong một callback tham gia transaction của outer, `status.setRollbackOnly()` có thể làm outer không commit được; template không tự tạo một điểm commit riêng khi đang join.

Vì vậy, không nên retry trong cùng physical transaction đã bị rollback-only ở **bất kỳ cách** nào. Retry coordinator thường cần ở **ngoài** transaction boundary để mỗi attempt tạo transaction mới phù hợp.

## 7. Ví dụ độc lập Java 17: cùng logic, hai cách đặt boundary

### 7.1. Mục tiêu minh họa

Để so sánh coupling công bằng, chúng ta giữ **cùng một class thực hiện SQL**, tên `TransferCore`, rồi tạo hai coordinator:

- `TemplateTransferService` giữ `TransactionTemplate` và gọi `executeWithoutResult(...)`.
- `DeclarativeTransferService` khai `@Transactional` trên method, còn body chỉ gọi `TransferCore`.

Mỗi cách sẽ chạy một lần **thất bại sau UPDATE thứ nhất** và một lần **thành công**. Với cùng `JdbcTransactionManager` và `DataSource`, kết quả DB sau rollback/commit phải tương đương.

Ví dụ dùng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19**, **Spring JDBC** và **H2 in-memory 2.3.232**. Không dùng Spring Boot để thấy rõ annotation-driven infrastructure. Chương trình là một minh họa transaction; nó chưa xử lý chống chi tiêu âm, khóa đồng thời hoặc idempotency chuyển tiền, nên không phải mã nghiệp vụ tài chính production.

### 7.2. Cấu trúc dự án

```text
tx-coupling-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── TxCouplingDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>tx-coupling-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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

`spring-context` cung cấp IoC/Java configuration; `spring-jdbc` cung cấp `JdbcTemplate`, datasource và `JdbcTransactionManager`; H2 chỉ dùng tại runtime. `@EnableTransactionManagement` và Spring transaction interceptor được đăng ký thông qua Java configuration.

### 7.3. Toàn bộ source `TxCouplingDemo.java`

File `src/main/java/demo/TxCouplingDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
@EnableTransactionManagement
public class TxCouplingDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:tx_coupling;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    TransferCore transferCore(JdbcTemplate jdbc) {
        return new TransferCore(jdbc);
    }

    @Bean
    TemplateTransferService templateTransferService(
            PlatformTransactionManager manager, TransferCore core) {
        return new TemplateTransferService(manager, core);
    }

    @Bean
    DeclarativeTransferService declarativeTransferService(TransferCore core) {
        return new DeclarativeTransferService(core);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             TxCouplingDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES(1, 100)");
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES(2, 50)");

            TemplateTransferService template =
                    context.getBean(TemplateTransferService.class);
            DeclarativeTransferService declarative =
                    context.getBean(DeclarativeTransferService.class);

            System.out.println("BEFORE=" + balances(jdbc));

            try {
                template.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("TEMPLATE_FAILURE=" + ex.getMessage());
            }
            System.out.println(
                    "AFTER_TEMPLATE_ROLLBACK=" + balances(jdbc));

            template.transfer(20, false);
            System.out.println(
                    "AFTER_TEMPLATE_COMMIT=" + balances(jdbc));

            jdbc.update(
                    "UPDATE accounts SET balance = 100 WHERE id = 1");
            jdbc.update(
                    "UPDATE accounts SET balance = 50 WHERE id = 2");
            System.out.println("RESET=" + balances(jdbc));

            try {
                declarative.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("DECLARATIVE_FAILURE=" + ex.getMessage());
            }
            System.out.println(
                    "AFTER_DECLARATIVE_ROLLBACK=" + balances(jdbc));

            declarative.transfer(20, false);
            System.out.println(
                    "AFTER_DECLARATIVE_COMMIT=" + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);

        return "A=" + a + ", B=" + b;
    }

    public static final class TransferCore {
        private final JdbcTemplate jdbc;

        public TransferCore(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void move(int amount, boolean fail) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            int debit = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? "
                    + "WHERE id = 1", amount);

            if (debit != 1) {
                throw new IllegalStateException("source missing");
            }

            if (fail) {
                throw new IllegalStateException("simulated");
            }

            int credit = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? "
                    + "WHERE id = 2", amount);

            if (credit != 1) {
                throw new IllegalStateException("destination missing");
            }
        }
    }

    // Programmatic: dependency trực tiếp vào Spring transaction API.
    public static class TemplateTransferService {
        private final TransactionTemplate tx;
        private final TransferCore core;

        public TemplateTransferService(
                PlatformTransactionManager manager, TransferCore core) {
            this.tx = new TransactionTemplate(manager);
            this.core = core;
        }

        public void transfer(int amount, boolean fail) {
            tx.executeWithoutResult(status -> core.move(amount, fail));
        }
    }

    // Declarative: metadata ở method, body chỉ xử lý nghiệp vụ.
    public static class DeclarativeTransferService {
        private final TransferCore core;

        public DeclarativeTransferService(TransferCore core) {
            this.core = core;
        }

        @Transactional
        public void transfer(int amount, boolean fail) {
            core.move(amount, fail);
        }
    }
}
```

**Vì sao hai nhánh có thể so sánh được?**

- Cả hai dùng **cùng `TransferCore`**, cùng `JdbcTemplate`, cùng `JdbcTransactionManager` và một datasource H2.
- Hai transaction boundaries mặc định đều dùng `PROPAGATION_REQUIRED`, read-write và rollback đối với `IllegalStateException` chưa được bắt trong phạm vi transactional invocation.
- `TemplateTransferService` là Spring bean nhưng **không cần proxy transaction** cho method `transfer()`: callback `tx.executeWithoutResult` trực tiếp tạo transaction scope.
- `DeclarativeTransferService` là Spring bean được container trả về **dưới dạng transactional proxy** nhờ `@EnableTransactionManagement`; lời gọi từ `main` phải đi qua bean đó, không được tạo trực tiếp bằng `new DeclarativeTransferService(...)` ngoài Spring.
- `TransferCore` không tự mở/commit transaction. Nó thực hiện những SQL trên connection do Spring JDBC đồng bộ với transaction hiện có.

### 7.4. Chạy và đọc stdout

Trong thư mục `tx-coupling-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxCouplingDemo
```

Các dòng **do chương trình tự in**, bỏ qua log của Maven/Spring:

```text
BEFORE=A=100, B=50
TEMPLATE_FAILURE=simulated
AFTER_TEMPLATE_ROLLBACK=A=100, B=50
AFTER_TEMPLATE_COMMIT=A=80, B=70
RESET=A=100, B=50
DECLARATIVE_FAILURE=simulated
AFTER_DECLARATIVE_ROLLBACK=A=100, B=50
AFTER_DECLARATIVE_COMMIT=A=80, B=70
```

Giải thích chính xác:

1. H2 nhận hai hàng ban đầu: tài khoản 1 có 100, tài khoản 2 có 50.
2. `template.transfer(20,true)` mở transaction; debit thành công, rồi `IllegalStateException("simulated")` thoát khỏi callback. Template rollback. Số dư vẫn 100/50.
3. `template.transfer(20,false)` debit 20, credit 20 và commit. Số dư thành 80/70.
4. Chương trình reset hai số dư về 100/50 bằng SQL ngoài hai test transactions.
5. `declarative.transfer(20,true)` gọi qua transactional proxy. Method target ném exception sau debit, interceptor rollback. Số dư vẫn 100/50.
6. `declarative.transfer(20,false)` return bình thường, interceptor commit. Số dư lại thành 80/70.

**Đáp án bài học:** Kết quả transaction ở DB **giống nhau** khi boundary và manager tương đương. Khác biệt thấy rõ trong code: template yêu cầu trường `TransactionTemplate` và callback; declarative chỉ có annotation ở method, còn body gọi `core.move(...)`.

**Giới hạn:** Ví dụ không mô phỏng concurrent transfers, insufficient funds, lock isolation, transaction propagation phức tạp hay nhiều datasource. Không dùng như hệ thống thanh toán production.

## 8. Testability: unit test và integration test phải được phân biệt

Tuyên bố “`@Transactional` dễ test hơn template” chỉ đúng nếu định nghĩa rõ **đang test phần nào**.

### 8.1. Unit test phần core nghiệp vụ

Trong ví dụ, `TransferCore` vẫn phụ thuộc `JdbcTemplate`. Để test domain rules hoàn toàn không cần Spring, có thể tách SQL ra một interface `AccountPort` rồi inject fake implementation. Điều này làm được **ở cả hai lựa chọn**.

```java
public interface AccountPort {
    int balance(long accountId);
    void debit(long accountId, int amount);
    void credit(long accountId, int amount);
}
```

Đây là **fragment interface**. Domain service chỉ biết `AccountPort`, không cần `JdbcTemplate` hay transaction. Ở application adapter:

- Có thể dùng template quanh `domain.transfer(...)`.
- Hoặc dùng annotated application service `@Transactional` gọi `domain.transfer(...)`.

Tính độc lập khỏi Spring của **domain core** là kết quả của dependency inversion và vị trí đặt transaction boundary, không phải hệ quả tự động từ việc chọn `@Transactional`.

### 8.2. Unit test method có annotation

Nếu bạn tạo trực tiếp `new DeclarativeTransferService(fakeCore)` trong unit test, annotation là metadata: nó **không tự mở transaction** khi không có Spring AOP infrastructure. Unit test đó có thể kiểm tra flow/exception, nhưng không chứng minh rollback.

Để kiểm chứng transaction thật, test cần một Spring context, transaction manager thích hợp, datasource và **gọi qua proxy**. Đọc DB state sau transactional boundary, đặc biệt sau một lỗi giữa hai SQL.

### 8.3. Unit test method dùng template

Một `TemplateTransferService` trực tiếp yêu cầu `TransactionTemplate`/`PlatformTransactionManager`. Bạn có thể mock hoặc dùng một fake coordinator để kiểm tra callback được gọi, nhưng việc mock transaction lifecycle không thay integration test.

Nếu architecture đặt template trong adapter và để core là POJO, unit test core vẫn độc lập. Chọn cách test theo layer, không gộp business logic test và transaction integration test.

### 8.4. Test dùng `@Transactional` trên test method

Spring Test có thể tự mở transaction và rollback cuối test. Điều này có thể che lỗi:

- Method dưới test thiếu proxy vẫn chạy trong transaction do test tạo sẵn.
- `TransactionTemplate(REQUIRED)` có thể join test transaction thay vì bắt đầu mới như bạn tưởng.
- Read-only/isolation từ inner annotation có thể không có hiệu lực do join transaction ngoài.

Khi kiểm tra commit/rollback boundary của **service**, cần gọi từ ngữ cảnh test không có transaction tương ứng hoặc quan sát kết quả sau khi test transaction kết thúc. Dùng rollback/commit integration tests có hai trường hợp fail/success rõ ràng.

## 9. AOP proxy, self-invocation và yếu tố coupling ẩn

`@Transactional` ở proxy mode mặc định chỉ chặn lời gọi **đi qua Spring proxy**. Nếu class có:

```java
@Service
public class OrderService {
    public void submit() {
        persist(); // this.persist() -> bỏ qua Spring proxy
    }

    @Transactional
    public void persist() {
        // Ghi DB
    }
}
```

Đây là **fragment minh họa**, chưa có repository. Caller gọi `submit()` qua proxy không khiến `persist()` bên trong được advice chặn thêm. Do đó transaction boundary mà developer nghĩ có ở `persist()` có thể không tồn tại.

Trong programmatic version:

```java
public void submit() {
    persist();
}

public void persist() {
    tx.executeWithoutResult(status -> {
        // Ghi DB
    });
}
```

Đây là fragment. Dù `submit()` và `persist()` cùng class, khi code thực sự chạy tới `tx.execute...`, template vẫn điều phối transaction. Không cần một AOP proxy cho callback. Đó là một lợi thế của explicit boundary, **không** có nghĩa template luôn bắt đầu transaction mới: với propagation `REQUIRED`, nó vẫn join transaction hiện có nếu có.

### 9.1. Không kết luận “@Transactional chỉ dùng được với public method” cho mọi cấu hình

Với Spring 6.0+, class-based proxies có thể hỗ trợ method package-visible/protected trong một số tình huống. Nhưng interface-based JDK proxies chỉ expose public methods trên interface và self-invocation vẫn bỏ qua advice. Để giảm bất ngờ giữa các kiểu proxy và dễ test, transaction boundary công khai ở application service thường là lựa chọn đơn giản nhất.

AspectJ weaving có thể intercept self-invocation nếu cấu hình đúng `spring-aspects`/weaving. Chỉ viết `mode="aspectj"` hoặc `@EnableAspectJAutoProxy` không tự biến mã chưa woven thành mã đã có transaction aspect.

### 9.2. Cái giá của sự tường minh

`TransactionTemplate` khiến developer nhìn thấy boundary ngay trong method, dễ tránh lỗi self-invocation. Đổi lại, business/application code phải quyết định lúc nào mở transaction, cấu hình nào cần dùng và lúc nào đặt rollback-only. Cùng một concern có thể bị lặp ở nhiều service nếu không gom thành abstraction.

Declarative giúp giảm boilerplate nhưng có **coupling vào cơ chế gọi bean/proxy** và convention transaction placement. Vì thế cần thiết kế đúng boundary, test proxy và có cơ chế debug.

## 10. Declarative không nhất thiết phải dùng Spring annotation trong source

Có một lựa chọn declarative theo cấu hình XML: đặt transaction advice theo method pattern và AOP pointcut. Business class **không cần `@Transactional`**:

```java
package demo;

public class AccountApplicationService {
    public void transfer() {
        // SQL/repository nghiệp vụ
    }
}
```

Ở Spring XML (fragment cần datasource, transactionManager và namespace tương ứng):

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="transfer" rollback-for="java.lang.Exception"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceCalls"
        expression="execution(* demo.AccountApplicationService.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceCalls"/>
</aop:config>
```

Hai đoạn là **fragment minh họa**, không thành một ứng dụng độc lập nếu chưa khai bean, datasource, transaction manager, `xmlns:tx`/`xmlns:aop` và schema. Ưu điểm: service không import transaction API hoặc annotation Spring; policy ở một nơi khác.

Đánh đổi:

- Transaction boundary không còn hiện ngay cạnh method trong source; developer phải biết XML/pointcut nào áp dụng.
- Đổi tên class, package hoặc method có thể làm pointcut miss nếu không test.
- Vẫn dựa vào Spring AOP proxy/manager ở runtime, và vẫn có hạn chế self-invocation trong proxy mode.

Vì vậy, “declarative ít coupling hơn” chính xác nhất khi nói về **application code không điều khiển transaction API trực tiếp**. Không nên nói nó **xóa hết mọi dependency** của hệ thống tới Spring.

## 11. Một transaction façade để giảm coupling của `TransactionTemplate`

Trong codebase cần dùng programmatic boundaries thường xuyên, có thể định nghĩa abstraction riêng ở application layer:

```java
package app.port;

import java.util.function.Supplier;

public interface UnitOfWork {
    <T> T execute(Supplier<T> work);
}
```

Và adapter Spring:

```java
package app.adapter;

import app.port.UnitOfWork;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringUnitOfWork implements UnitOfWork {
    private final TransactionTemplate template;

    public SpringUnitOfWork(PlatformTransactionManager manager) {
        this.template = new TransactionTemplate(manager);
    }

    @Override
    public <T> T execute(Supplier<T> work) {
        return template.execute(status -> work.get());
    }
}
```

Đây là **hai fragment biên dịch được khi có các dependency/imports và cấu hình Java package tương ứng**, nhưng chưa phải chương trình runnable một mình. Application service có thể inject `UnitOfWork`:

```java
public final class RegistrationUseCase {
    private final UnitOfWork tx;

    public RegistrationUseCase(UnitOfWork tx) {
        this.tx = tx;
    }

    public String register() {
        return tx.execute(() -> {
            // Gọi persistence ports/domain logic.
            return "registered";
        });
    }
}
```

Đây là fragment cần class `UnitOfWork` ở package được import, bean injection và collaborators. `RegistrationUseCase` không cần import `TransactionTemplate`. Tuy nhiên, nó vẫn biết *khái niệm UnitOfWork*, tức **business orchestration còn ghép với transaction semantics ở mức abstraction ứng dụng**. Abstraction này có thể giúp thay adapter/test, nhưng nếu mọi service chỉ có một `@Transactional` đơn giản, việc tạo thêm façade có thể gây phức tạp không cần thiết.

### 11.1. Chi phí của façade

`Supplier<T>` không cho phép ném checked exception trực tiếp; nếu domain flow cần lỗi checked, phải thiết kế functional interface và exception policy phù hợp, không wrap mọi lỗi một cách tùy tiện. Cũng cần xem propagation/timeout/read-only được cấu hình ở façade ở đâu. Một abstraction chung có thể quá hẹp cho use case phức tạp; một abstraction quá nhiều tùy chọn thì chỉ lặp lại API của Spring.

### 11.2. Không tạo một framework nội bộ chỉ để tránh một import

Mục tiêu là giảm coupling **có giá trị** cho ranh giới module và kiểm thử, không phải giấu mọi type tên Spring bất kể độ phức tạp tăng. Nếu codebase hoàn toàn là Spring và transaction template xuất hiện ở vài điểm, giữ API Spring có thể đơn giản, dễ đọc và đúng hơn một façade tự tạo.

## 12. Checked exception và rollback: so sánh quyết định đặt ở đâu

Declarative `@Transactional` (với cấu hình rollback mặc định thông thường) rollback cho `RuntimeException`/`Error`, nhưng không mặc định rollback cho mọi checked exception. Có thể khai:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importFile() throws java.io.IOException {
    // Nếu IOException thoát transactional advice, rollback rule áp dụng.
}
```

Đây là fragment minh họa, cần logic file/repository thực tế. Spring 6.2 có khả năng thay global rollback defaults (ví dụ `@EnableTransactionManagement(rollbackOn=ALL_EXCEPTIONS)`), nên hãy biết cấu hình version thực tế.

`TransactionTemplate.execute` nhận callback không khai `throws` checked exception. Vì vậy, nếu code bên trong gặp checked exception và cần rollback, phải **thể hiện policy rõ**:

```java
String outcome = template.execute(status -> {
    try {
        legacyOperationThatMayThrow();
        return "SUCCESS";
    } catch (java.io.IOException ex) {
        status.setRollbackOnly();
        return "IO_FAILURE";
    }
});
```

Đây là fragment, `legacyOperationThatMayThrow()` và template phải tồn tại. Cách này chỉ phù hợp nếu business contract cho phép trả failure outcome. Nếu caller phải thấy exception, có thể wrap có chủ đích trong một runtime exception chứa cause hoặc thiết kế một abstraction riêng; không nuốt lỗi rồi báo thành công.

**Coupling perspective:**

- Declarative: rollback policy được mô tả bằng annotation; thân method có thể ném checked exception bình thường.
- Programmatic template: policy có thể xuất hiện trong callback dưới dạng exception handling/status, nên concern transaction được lộ rõ ngay trong logic.
- Cả hai phải xét transaction participation: một rollback-only ở inner `REQUIRED` có thể làm outer commit thất bại với `UnexpectedRollbackException`.

## 13. Conditional transaction boundary và transaction name

### 13.1. Một method có đoạn không cần transaction

Trong một use case chuẩn bị dữ liệu và gọi API ngoài trước khi ghi DB, template có thể giữ connection/locks chỉ trong khối ngắn:

```java
public Result process(Request req) {
    Quote quote = externalPricingClient.fetch(req);  // ngoài transaction

    Result saved = txTemplate.execute(status -> {
        // INSERT/UPDATE phải atomic
        return saveInDatabase(quote);
    });

    notifyAfterCommitOrUseOutbox(saved);              // bên ngoài callback
    return saved;
}
```

Đây là fragment, các types/collaborators cần được cung cấp. Tên method `notifyAfterCommitOrUseOutbox` **không bảo đảm email/message rollback hoặc exactly-once**; outbox/idempotency cần thiết kế riêng, nhất là khi caller có transaction ngoài hoặc template tham gia một T1 vẫn chưa commit.

Với declarative, có thể tách method ghi DB sang **bean riêng `@Transactional`** và gọi từ coordinator; transaction boundary vẫn ngắn và không cần template. Sự khác nhau là **cách biểu diễn boundary trong code**.

### 13.2. Gán transaction name

Programmatic definition/template có thể đặt tên phục vụ monitoring:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setName("reporting.dailyAggregation");
```

Đây là fragment. Trong declarative `@Transactional`, transaction name thường được Spring tạo từ `fully.qualified.ClassName.methodName`, không có một `@Transactional(name="...")` phổ thông để đặt tùy ý. Đây là một lợi thế cụ thể của programmatic management khi transaction naming là yêu cầu chẩn đoán.

### 13.3. Template là thread-safe khi cấu hình ổn định

Tài liệu Spring xác nhận `TransactionTemplate` không giữ **conversational state** giữa các lần thực thi và có thể được chia sẻ giữa nhiều threads nếu **cấu hình không bị chỉnh đồng thời**.

Cách dùng hợp lý:

```java
private final TransactionTemplate readOnlyTemplate;
private final TransactionTemplate writeTemplate;
```

Hai template được khởi tạo một lần với policy khác nhau; mỗi call dùng instance phù hợp. Đừng gọi `setTimeout(...)`/`setPropagationBehavior(...)` trên **một template dùng chung** ở mỗi request để thay policy động rồi mong các request đồng thời không ảnh hưởng nhau. Với nhiều policy, có thể tạo các instance bất biến về cấu hình sau khi thiết lập, hoặc tạo definition/template cục bộ phù hợp trước khi execute.

## 14. Có thể kết hợp programmatic và declarative không?

Có. Chúng cùng dựa vào Spring transaction infrastructure và có thể tương tác qua propagation, nhưng phải hiểu **ai sở hữu physical transaction**.

Ví dụ outer declarative:

```java
@Transactional
public void submit() {
    txTemplate.executeWithoutResult(status -> {
        // Công việc được thực hiện dưới propagation của template.
    });
}
```

Đây là fragment. Với template mặc định `REQUIRED`, callback **tham gia** transaction ngoài, không tạo T2 riêng. `status.setRollbackOnly()` hoặc lỗi phù hợp trong callback có thể khiến outer T1 không commit được.

Ngược lại outer programmatic:

```java
template.executeWithoutResult(status -> {
    otherSpringBean.transactionalMethod();
});
```

Đây là fragment. Nếu `otherSpringBean.transactionalMethod()` gọi qua Spring proxy và dùng `REQUIRED`, nó sẽ tham gia transaction do template bắt đầu. Nếu gọi một method cùng class bằng `this.method()`, annotation có thể không được advice chặn.

### 14.1. `REQUIRES_NEW` không phải savepoint

Nếu template dùng `PROPAGATION_REQUIRES_NEW` bên trong outer `@Transactional`, manager suspend T1 và mở T2 độc lập (khi resource hỗ trợ). Điều này có thể cần thêm JDBC connection và làm T2 commit riêng ngay cả khi T1 sau đó rollback. Đây là **thay đổi semantics**, không chỉ là chuyển cú pháp.

`NESTED`, khi manager/database hỗ trợ, thường dùng savepoint **trong cùng physical transaction**. Không xem việc dùng template là một cơ chế “né” các hạn chế resource/propagation của manager.

### 14.2. Đừng dùng hai transaction managers rồi giả định chung atomicity

Một callback có manager A và method `@Transactional` chọn manager B không tự tạo transaction toàn cục. Dù cả hai đều dùng Spring, local JDBC managers chỉ điều phối resource tương ứng. Nếu phải đảm bảo atomicity đa tài nguyên, cần transaction coordinator thích hợp hoặc kiến trúc outbox/saga tùy use case.

## 15. Quan sát, test và migration

### 15.1. Khi migrate `TransactionTemplate` sang `@Transactional`

Checklist tối thiểu:

1. Xác định chính xác khối code **bên trong** template callback; không vô tình kéo network call hoặc CPU work dài vào transaction mới.
2. Ghi lại propagation, isolation, timeout, read-only, transaction manager, name và behavior rollback-only hiện có.
3. Chọn public Spring-managed service method được **caller bên ngoài gọi qua proxy**.
4. Chuyển cấu hình template tương ứng sang annotation hoặc advice XML, hiểu những khác biệt về rollback checked exception.
5. Kiểm tra các đoạn `status.setRollbackOnly()` và business failure result; annotation không tự tái tạo behavior đó nếu chỉ return bình thường.
6. Kiểm tra caller có transaction ngoài không; `REQUIRED` có thể join theo cùng semantics nhưng thời điểm begin/commit phải được xác minh.
7. So sánh exception xuất hiện ở callback vs proxy commit và đường xử lý lỗi/retry.
8. Kiểm tra việc dùng transaction name tùy ý: annotation thông thường tự sinh name.
9. Viết integration test cả success và failure giữa hai SQL, kiểm tra dữ liệu sau boundary.
10. Nếu có test-level `@Transactional`, loại bỏ ảnh hưởng làm test luôn có transaction ngoài.

### 15.2. Khi migrate `@Transactional` sang `TransactionTemplate`

Kiểm tra tương tự theo chiều ngược:

1. Đừng bọc **toàn bộ** method bằng template nếu annotation trước đó áp dụng một propagation rất cụ thể mà bạn chưa tái tạo.
2. Dùng `TransactionTemplate` được cấu hình cùng manager/resource như annotated service cũ.
3. Đặt phần nghiệp vụ cần atomicity trong callback, giữ các side effects ngoài DB ở vị trí hợp lý.
4. Chuyển rollback rules checked exception thành handling/status/exception policy rõ ràng.
5. Đảm bảo đoạn code từng chạy do AOP advice (ví dụ security/retry aspects) không đổi thứ tự đáng kể khi loại bỏ transaction advisor.
6. Xác nhận không có inner `@Transactional(REQUIRES_NEW)` tự bị thay thành `REQUIRED` khi chuyển sang template mặc định.
7. Xem xét template dùng chung và cấu hình state; không mutate policy trên singleton giữa các requests.

### 15.3. Logging

Trong môi trường dev/test có logging backend tương ứng, có thể quan sát:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Đây là fragment cấu hình thường gặp trong Spring Boot, **không phải** yêu cầu của chương trình `AnnotationConfigApplicationContext` ở phần 7. Log hỗ trợ nhìn begin/join, suspend/resume, commit/rollback. Với cả hai cách, **kết quả DB sau transaction boundary** mới là bằng chứng cuối cùng cho một operation có rollback/commit đúng hay không.

## 16. Tình huống thiết kế và lựa chọn phù hợp

### A. CRUD service với 40 thao tác ghi tương tự

**Ưu tiên cân nhắc khai báo.** Annotation trên service methods hoặc các composed annotations giúp giảm callback trùng lặp. Việc dùng nhiều `TransactionTemplate` có thể làm transaction API rải khắp code, tăng coupling và chi phí đọc.

### B. Một batch import gồm nhiều bước phi transactional, chỉ một đoạn ghi cần commit

**`TransactionTemplate` có lợi** nhờ thể hiện ranh giới ngay cạnh code. Khai báo vẫn có thể phù hợp nếu tách transactional writer thành bean riêng; nên chọn giải pháp dễ review hơn theo kiến trúc hiện có.

### C. Domain model muốn không phụ thuộc Spring

**Cả hai đều làm được** nếu transaction concern nằm ngoài domain model. Với template, bọc bằng application adapter/facade. Với declarative, gắn annotation ở Spring application service hoặc dùng XML advice, tránh annotation trong domain entities.

### D. Retry serialization failure ở commit

Cần retry coordinator **ngoài transaction boundary** để mỗi attempt dùng transaction mới. `TransactionTemplate.execute(...)` trong một vòng retry ngoài transaction dễ đặt đúng. Declarative cũng đạt được nếu retry coordinator gọi Spring-managed transactional worker qua proxy, với advisor order đúng. Không đặt retry trong transaction đã rollback-only.

### E. Cần `setRollbackOnly()` nhưng vẫn trả business outcome

Template cho phép xử lý trực tiếp trong callback. Declarative có thể truy cập `TransactionAspectSupport.currentTransactionStatus()` nhưng điều đó đưa source-level dependency vào body, làm giảm lợi thế tách concern; hoặc tái thiết kế exception/return policy phù hợp. Đừng biến mọi failure thành checked exception rồi mặc định rollback.

### F. Một method cùng class gọi helper `@Transactional`

Proxy declarative có nguy cơ self-invocation bỏ qua advice. Template tường minh vẫn điều phối khi callback được chạy. Nếu muốn giữ declarative, đặt helper trên bean khác, chuyển boundary lên outer method, hoặc đánh giá AspectJ weaving khi thực sự cần.

## 17. Những ngộ nhận cần tránh

**Ngộ nhận 1: “`@Transactional` không ghép nối với Spring.”**  
Không đúng nếu dùng annotation Spring trực tiếp; chỉ là coupling trong method body thấp hơn. Nếu dùng XML advice, source của business class có thể không import transaction framework, nhưng runtime vẫn cần Spring/AOP/manager.

**Ngộ nhận 2: “`TransactionTemplate` bắt buộc viết `try/commit/rollback` thủ công.”**  
Không đúng. Template xử lý lifecycle, callback chỉ thể hiện công việc cần thực hiện. Manual `PlatformTransactionManager` là một cách programmatic khác.

**Ngộ nhận 3: “Annotation luôn tốt hơn vì ít code hơn.”**  
Không đúng. Một boundary nhỏ, có điều kiện trong một luồng dài có thể rõ hơn với template. Chất lượng phụ thuộc khả năng đọc và kiểm thử trên codebase thật.

**Ngộ nhận 4: “Template không có vấn đề propagation.”**  
Không đúng. Template mặc định có thể dùng `REQUIRED` và join transaction ngoài. Nó không bảo đảm mỗi `execute` có transaction vật lý mới.

**Ngộ nhận 5: “Thêm `@Transactional` chắc chắn method được rollback.”**  
Không đúng nếu bean tạo bằng `new`, annotation infrastructure chưa bật, caller bỏ qua proxy hoặc datasource/manager không khớp. Phải kiểm tra boundary thực.

**Ngộ nhận 6: “Nếu tự gọi method cùng class, dùng template cũng mất transaction.”**  
Không đúng nếu code thật sự thực thi `template.execute(...)`. Đây là điểm khác với proxy intercept của `@Transactional`.

**Ngộ nhận 7: “`readOnly=true` là DB permission tuyệt đối.”**  
Không đúng. Manager/driver/provider có thể dùng hint hoặc enforcement riêng; annotation không thay phân quyền DB.

**Ngộ nhận 8: “Gắn annotation rồi catch exception bên trong method vẫn tự rollback.”**  
Chưa chắc. Exception bị nuốt trước khi thoát advice có thể dẫn đến commit nếu không có rollback-only; phải thiết kế policy rõ ràng.

**Ngộ nhận 9: “Migrate cú pháp không thể đổi hành vi.”**  
Có thể đổi nếu boundary, propagation, transaction name, rollback rules, timing hoặc AOP order khác. Cần test commit/rollback sau migration.

**Ngộ nhận 10: “Unit test không cần Spring chứng minh transaction được áp dụng.”**  
Không đúng. Unit test chỉ chứng minh business method; transaction semantics cần integration test với manager/resource/proxy phù hợp.

**Ngộ nhận 11: “`TransactionTemplate` không thread-safe.”**  
Không đúng theo tài liệu: nó có thể được chia sẻ khi cấu hình ổn định, nhưng không nên mutate shared policy giữa các requests.

**Ngộ nhận 12: “Reactive transaction cũng dùng y nguyên `TransactionTemplate`.”**  
Không đúng. Với reactive flows, Spring khuyên dùng `TransactionalOperator` và `ReactiveTransactionManager`/Reactor Context; không dùng thread-local JDBC semantics để suy luận transaction reactive.

## 18. Tự kiểm tra và bài tập

**Câu 1.** Về source-level coupling, sự khác nhau căn bản giữa `TransactionTemplate` và `@Transactional` là gì?

**Đáp án:** Template khiến code gọi API transaction trực tiếp; declarative đưa policy vào metadata/annotation và transaction lifecycle nằm ở interceptor. Annotation Spring vẫn là dependency, nhưng body method không cần template/status.

**Câu 2.** Có phải `@Transactional` cho phép bỏ hoàn toàn Spring transaction manager không?

**Đáp án:** Không. Cần transaction infrastructure và manager/resource phù hợp; annotation chỉ là metadata nếu chưa được xử lý.

**Câu 3.** `TransactionTemplate` có thể dùng trong self-invocation không?

**Đáp án:** Có. Nếu internal method thực thi callback `template.execute`, template vẫn điều phối transaction; self-invocation chỉ là vấn đề khi phụ thuộc proxy advice.

**Câu 4.** Một service `@Transactional` được khởi tạo bằng `new` ngoài Spring rồi gọi method. Có chắc transaction không?

**Đáp án:** Không chắc; ở proxy mode thông thường, không có proxy/infrastructure bao quanh object đó, nên annotation không tự mở transaction.

**Câu 5.** Đặt `@Transactional(readOnly=true)` lên method có bảo đảm DB luôn cấm ghi không?

**Đáp án:** Không. Read-only thường là hint; enforcement tùy manager/provider/database.

**Câu 6.** `TransactionTemplate` dùng `REQUIRED` bên trong outer transaction có mở T2 mới không?

**Đáp án:** Thường không. Nó tham gia T1; muốn transaction độc lập cần `REQUIRES_NEW` và cân nhắc resource.

**Câu 7.** Vì sao template có lợi khi chỉ một đoạn SQL ngắn cần transaction?

**Đáp án:** Boundary được biểu đạt ngay trong code, không bắt buộc tách thành một annotated method/bean; phần không cần transaction có thể nằm ngoài callback.

**Câu 8.** Nếu nhiều service methods đều transactional tương tự nhau thì chọn gì?

**Đáp án:** Declarative thường giảm boilerplate và coupling trực tiếp vào transaction API trong các method; tuy nhiên cần hiểu proxy và cấu hình.

**Câu 9.** Nếu cần transaction name tùy ý để theo dõi batch, cách nào thuận lợi?

**Đáp án:** Programmatic definition/template có thể `setName`, còn declarative method name thường được Spring tự sinh.

**Câu 10.** `TransactionTemplate` có thể dùng làm một singleton shared object với policy thay đổi theo từng request không?

**Đáp án:** Không nên mutate policy của cùng một template được chia sẻ đồng thời. Template thread-safe khi cấu hình ổn định; dùng nhiều instances/policies rõ ràng.

**Câu 11.** Trong callback template, `status.setRollbackOnly()` rồi return `"FAIL"` có phải là đã commit giao dịch không?

**Đáp án:** Không. Đây là yêu cầu rollback; `"FAIL"` chỉ là business result và caller phải hiểu ý nghĩa đó. Khi tham gia T1, rollback-only có thể ảnh hưởng outer transaction.

**Câu 12.** Unit test gọi `new DeclarativeTransferService(core)` và thấy exception. Điều đó đã chứng minh rollback DB chưa?

**Đáp án:** Chưa. Không có transaction proxy/manager, test đó không xác minh Spring transaction. Cần integration test gọi bean qua context và đọc DB sau boundary.

**Câu 13.** Có thể dùng XML declarative để class nghiệp vụ không import `@Transactional` không?

**Đáp án:** Có, cấu hình `<tx:advice>` + AOP pointcut trên method phù hợp. Đổi lại, coupling chuyển sang XML và cần test pointcut/rename.

**Câu 14.** Với một hệ thống Spring thuần, có nên tạo abstraction `UnitOfWork` chỉ để tránh import `TransactionTemplate` ở một service duy nhất?

**Đáp án:** Không nhất thiết. Abstraction chỉ có ích khi tạo ra ranh giới module/test/portability rõ ràng hơn chi phí bổ sung.

## 19. Checklist áp dụng khi review code

Khi quyết định giữa template và declarative, hãy kiểm tra:

- Transaction boundary hiện tại nằm ở đâu? Có bao cả network call, xử lý file hoặc tính toán lâu không?
- Một operation có **ít hay nhiều** transactional methods cần policy tương tự?
- Business method có import `TransactionTemplate`, `TransactionStatus`, `PlatformTransactionManager` không? Những import đó có phù hợp layer hiện tại không?
- Nếu dùng `@Transactional`, method có được gọi qua Spring-managed bean/proxy chưa? Có self-invocation không?
- Transaction manager/data source/persistence unit có khớp với DAO/repository không?
- `REQUIRED` có join outer transaction không? Nếu không muốn join, propagation đã được thiết kế đúng chưa?
- Rollback rule cho checked exception/return outcome đã rõ chưa? Có dùng `status.setRollbackOnly()` không?
- Có nhiều transaction managers, retry mechanism hoặc AOP advice làm thứ tự thực thi khác dự kiến không?
- Có cần gán **transaction name** tùy ý hoặc thay transaction settings cho một khối nhỏ không?
- Một template singleton có bị mutate config khi nhiều threads cùng gọi không?
- Phần domain core có cần độc lập Spring không? Có thể đẩy transaction concern lên application service/adapter mà không tạo abstraction thừa không?
- Test có phân biệt **logic unit test** với **transaction integration test** không? Đã thử rollback giữa hai SQL và đọc dữ liệu sau transaction chưa?
- Nếu chuyển từ cách này sang cách kia, đã so sánh phạm vi begin/commit và propagation thực tế chưa?
- Tài liệu vận hành/logging có cho biết rõ transaction failures và timeout không?

**Tóm lại:** `TransactionTemplate` **ghép code trực tiếp với transaction API Spring** nhưng đổi lại boundary linh hoạt và hiện rõ; quản lý khai báo **giảm transaction boilerplate trong thân nghiệp vụ** và thường hợp với nhiều service operations, nhưng dựa vào metadata/proxy và vẫn cần hạ tầng Spring. Chọn theo vị trí boundary, độ phức tạp điều phối và khả năng kiểm thử — không dựa vào quan niệm rằng một cách luôn tốt hơn cách kia.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Programmatic Transaction Management (`TransactionTemplate`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework 6.2 — Choosing Between Programmatic and Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-decl-vs-prog.html)
- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 API — `TransactionTemplate`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework 6.2 API — `TransactionStatus`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — Transaction Resource Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)