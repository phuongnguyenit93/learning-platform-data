# Khả năng áp dụng @Transactional cho public, protected và package-visible theo phiên bản Spring

> **Chủ đề:** Spring Framework — transaction management, phần **Cơ chế proxy**. Bài học tập trung vào **phạm vi method visibility** của `org.springframework.transaction.annotation.Transactional` trong **proxy mode**: Spring 5.3 trở về trước so với Spring 6.0 trở lên, JDK interface proxy so với class-based proxy (CGLIB), và các trường hợp annotation có mặt nhưng transaction advice không chạy.

## 1. Câu trả lời cần ghi nhớ

**Theo tài liệu tham chiếu của Spring Framework 6.2:**

- Với **Spring Framework 5.3 trở về trước**, cấu hình transaction proxy mặc định chỉ xét phương thức `public`. Đánh dấu `@Transactional` trên `protected` hoặc **package-visible/package-private** thường không làm phương thức đó trở thành transaction boundary qua proxy.
- **Từ Spring Framework 6.0**, **class-based proxy** có thể xử lý `@Transactional` trên phương thức **`protected` và package-visible theo mặc định**, ngoài `public`, miễn lời gọi thực sự đi từ bên ngoài vào qua proxy và phương thức có thể được proxy override/intercept.
- **JDK interface-based proxy** vẫn chỉ intercept các phương thức **`public` được khai báo trên interface mà proxy phơi bày**. Một phương thức `public` chỉ nằm trên lớp triển khai nhưng không có trong interface proxied sẽ không phải điểm gọi được qua interface proxy đó.
- **`private` không được intercept bởi Spring AOP proxy**. Phương thức `final` hoặc lớp `final` cũng hạn chế/không cho phép cơ chế subclass proxy hoạt động tương ứng.
- **Self-invocation** — một method của target gọi method khác bằng `this.method()` hoặc gọi ngầm trên chính target — **bỏ qua proxy**. Sự thay đổi của Spring 6.0 **không loại bỏ quy tắc này**.
- Nếu cần giữ chính sách chỉ xét `public` trên Spring 6.x, có thể cấu hình `AnnotationTransactionAttributeSource(true)`, tương ứng `publicMethodsOnly = true`.

Đừng hiểu “Spring 6 hỗ trợ `protected`” thành “bất kỳ lời gọi `protected` nào cũng có transaction”. **Version + loại proxy + khả năng override + đường đi của lời gọi + transaction manager** mới quyết định kết quả.

## 2. Các mức truy cập trong Java

Trong Java, method có bốn mức truy cập thường gặp:

```java
public class LedgerService {
    public void publicOperation() {
        // Gọi được từ mọi nơi nếu class và method có thể truy cập.
    }

    protected void protectedOperation() {
        // Gọi từ cùng package; ngoài package có quy tắc kế thừa.
    }

    void packageOperation() {
        // Không ghi modifier: chỉ truy cập trong cùng package.
    }

    private void privateOperation() {
        // Chỉ truy cập bên trong lớp khai báo.
    }
}
```

**Package-visible**, **package-private** và **default access** trong ngữ cảnh này chỉ cùng một mức truy cập: **không có từ khóa `public`/`protected`/`private`** trước method. Không có modifier Java tên `package`.

Phân biệt hai khái niệm:

1. **Java cho phép gọi method hay không?** Đây là quy tắc ngôn ngữ về access modifier và package.
2. **Spring có chặn được lời gọi đó để bao transaction hay không?** Đây là khả năng của proxy và transaction interceptor.

Một method có thể **hợp lệ theo Java** nhưng **không được transaction advice xử lý**, ví dụ `private` có `@Transactional` và chỉ được gọi từ bên trong bean.

## 3. Ma trận theo phiên bản và loại proxy

Bảng dưới giả định: Spring quản lý bean, annotation đúng loại Spring, transaction infrastructure hoạt động, caller gọi **qua proxy**, method không `final` và class-based proxy có thể nhìn thấy/override method.

| Method | Spring 5.3 trở về trước — class-based proxy mặc định | Spring 6.0+ — class-based proxy mặc định | JDK interface proxy ở cả hai thế hệ |
| --- | --- | --- | --- |
| `public`, có trên interface nếu dùng JDK proxy | Có | Có | Có, nếu được khai báo trên interface proxied |
| `public`, chỉ có trên implementation | Có | Có | Không có entry point tương ứng trên interface proxy |
| `protected` | Không, theo mặc định cũ | **Có thể có** | Không |
| Package-visible / package-private | Không, theo mặc định cũ | **Có thể có** | Không |
| `private` | Không | Không | Không |
| `final` method (class proxy) | Không thể override/intercept | Không thể override/intercept | JDK proxy có cơ chế khác, nhưng chỉ các method trên interface được gọi qua proxy |

**Phạm vi bảng:** chỉ nói về Spring **transaction proxy mode**. `AspectJ` weaving không tuân theo đúng ma trận proxy vì có thể weave bytecode thay vì tạo lớp proxy. Các phiên bản Spring 6.x khác nhau có thể có khác biệt triển khai/tài liệu ở bản vá cụ thể; khi nâng cấp một ứng dụng đang chạy thực tế, hãy kiểm chứng trên **bản framework đang đóng gói** bằng integration test và trang tài liệu tương ứng. Tài liệu tham chiếu Spring 6.2 nêu thay đổi mặc định bắt đầu ở Spring 6.0.

### Ví dụ nhỏ

```java
@Service
class BillingService {
    @Transactional
    public void pay() {
    }

    @Transactional
    protected void reserve() {
    }

    @Transactional
    void register() {
    }

    @Transactional
    private void auditInternally() {
    }
}
```

Đây là **đoạn minh họa**, giả định có import `@Service`, `@Transactional`, một Spring context và transaction manager phù hợp. Trong Spring 6.2 dùng class-based proxy:

- `pay()` là điểm có thể intercept nếu được gọi qua proxy.
- `reserve()` và `register()` **có thể** được intercept khi caller bên ngoài nhìn thấy và gọi method **trên chính proxy**.
- `auditInternally()` không trở thành một điểm intercept chỉ nhờ annotation, vì CGLIB không override được `private`.
- Nếu `pay()` gọi `reserve()` trực tiếp trên `this` thì lời gọi **nội bộ** đó vẫn không chạy qua interceptor riêng của `reserve()`. Nếu `pay()` đã mở transaction, code trong `reserve()` có thể thấy **transaction đang tồn tại**; điều đó **không chứng minh annotation của `reserve()` đã được xử lý**.

## 4. Tại sao JDK proxy và class-based proxy khác nhau?

### 4.1. JDK dynamic proxy

JDK proxy tạo một object triển khai interface do bean phơi bày:

```text
Caller
  |
  | gọi InvoicePort.create()
  v
JDK proxy implements InvoicePort
  |
  | TransactionInterceptor, nếu method có transaction attribute
  v
InvoiceService implements InvoicePort
  |
  v
Database
```

JDK proxy không kế thừa `InvoiceService`; nó phơi bày **interface methods**, vốn là `public`. Vì vậy:

```java
public interface InvoicePort {
    void create();
}

@Service
public class InvoiceService implements InvoicePort {
    @Override
    @Transactional
    public void create() {
        // Public method được công bố qua InvoicePort.
    }

    @Transactional
    public void reindex() {
        // Public method thêm ở implementation, không thuộc InvoicePort.
    }

    @Transactional
    protected void internalProcess() {
        // Không thuộc interface proxy.
    }
}
```

Đây là **trích đoạn minh họa**, không phải ba top-level types trong cùng một file. Khi ép dùng **JDK interface proxy**, caller inject `InvoicePort` và gọi `create()` qua proxy: đây có thể là transaction boundary. Caller không có `reindex()` hay `internalProcess()` trên kiểu `InvoicePort`. Nếu cố inject concrete `InvoiceService` trong tình huống proxy chỉ triển khai interface, ứng dụng có thể báo lỗi tiêm bean không tương thích; không được khắc phục bằng cách lấy target thực rồi gọi trực tiếp, vì như vậy lại bỏ qua proxy.

Điều quan trọng là **public thôi chưa đủ đối với JDK proxy**: method cần thuộc interface thực sự được proxy, và call phải đi qua object proxy đó.

### 4.2. Class-based proxy (CGLIB)

Class-based proxy là một subclass được tạo khi chạy:

```text
Caller
  |
  | gọi proxy.protectedOperation() từ nơi Java cho phép truy cập
  v
BillingService$$SpringCGLIB... extends BillingService
  |
  | override/intercept method có thể thấy được
  v
TransactionInterceptor
  |
  v
BillingService (target)
```

Vì subclass có thể override nhiều method ngoài `public`, Spring 6.0+ đã mở rộng xử lý transaction theo mặc định cho `protected` và package-visible trong class-based proxy.

Tuy nhiên, khả năng của subclass vẫn bị giới hạn bởi Java:

- `private` không thể override, nên không thể intercept qua subclass.
- `final` method không thể override.
- `final` class không thể được subclass để tạo class proxy.
- Một package-private method khai báo trong superclass thuộc **package khác** có thể không thấy được ở subclass proxy, về thực chất giống private đối với lớp đó.
- Các hạn chế Java Module System hoặc cơ chế tạo proxy cũng có thể ảnh hưởng khả năng tạo proxy.

Class-based proxy **không làm mọi method tự động có transaction**. Chỉ những method đủ điều kiện với transaction metadata và được gọi **qua proxy** mới được transaction interceptor xử lý.

### 4.3. Chọn proxy bằng cấu hình

Trong Spring Framework thuần:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfiguration {
}
```

Cần import `org.springframework.context.annotation.Configuration` và `org.springframework.transaction.annotation.EnableTransactionManagement`. `proxyTargetClass = true` yêu cầu **class-based proxy** cho transaction proxy mode. Nếu để `false` thì Spring AOP thường dùng JDK proxy khi target có interface, hoặc class-based proxy khi không có interface thích hợp.

**Lưu ý Spring Boot:** Boot có các mặc định và properties AOP riêng, thường ưu tiên class-based proxy trong cấu hình quen thuộc. Đừng suy đoán loại proxy chỉ từ việc thấy bean có interface. Ví dụ hoàn chỉnh bên dưới **ép rõ class-based proxy** để kết quả không phụ thuộc mặc định của môi trường.

## 5. Cơ chế interceptor và lời gọi từ bên ngoài

`@Transactional` cung cấp **metadata**; hiệu lực thực tế cần Spring cấu hình transaction advice/transaction manager và bean được gọi qua proxy.

Sơ đồ lời gọi hợp lệ:

```text
CheckoutController hoặc CommandLineRunner
    |
    | tham chiếu đã inject từ Spring
    v
Spring proxy của BillingService
    |
    +-- kiểm tra metadata method và transaction manager
    +-- mở/tham gia transaction nếu thích hợp
    +-- gọi target method
    +-- commit hoặc rollback theo kết quả
```

Self-invocation:

```java
@Service
class StockService {

    public void start() {
        reserve(); // Tương đương this.reserve(): không qua proxy.
    }

    @Transactional
    protected void reserve() {
        // Annotation không được intercept riêng trong lời gọi trên.
    }
}
```

Đây là **trích đoạn**, không chạy độc lập. Dù Spring 6.2 hỗ trợ `protected` trên class-based proxy, `start()` gọi `reserve()` **trên target**, không đi qua proxy để thực hiện transaction advice của `reserve()`.

Nếu `start()` không có transaction trước đó, `reserve()` có thể chạy **không có transaction**. Nếu `start()` vốn đang có transaction thì `reserve()` được thực thi **bên trong transaction đang có**, nhưng không vì thế mà annotation của `reserve()` được kích hoạt riêng (ví dụ `REQUIRES_NEW` hay `timeout` riêng không áp dụng qua self-invocation).

Một cách thiết kế đơn giản, dễ kiểm thử:

```java
@Service
class StockReserveService {
    @Transactional
    public void reserve() {
        // Transaction boundary rõ ràng trên public method.
    }
}

@Service
class StockWorkflowService {
    private final StockReserveService reservation;

    StockWorkflowService(StockReserveService reservation) {
        this.reservation = reservation;
    }

    public void start() {
        reservation.reserve(); // Gọi qua Spring bean proxy khác.
    }
}
```

Đây là các class minh họa trong cùng package của ứng dụng. Cách tách bean giúp transaction boundary hiển thị rõ và tránh phụ thuộc quá nhiều vào method không public khi không cần thiết.

## 6. Ví dụ hoàn chỉnh: chứng minh bằng rollback thật trên H2

Bài demo dùng **Spring Boot 3.5.7**, Spring Framework 6.2, **Java 17**, Maven, Spring JDBC và H2. Ta cố tình ném `IllegalStateException` sau khi ghi database để kiểm chứng transaction advice có chạy hay không:

- Khi lời gọi **được proxy intercept** và tạo transaction, insert sẽ **rollback** → không còn bản ghi.
- Khi lời gọi **không được intercept**, `JdbcTemplate` thực hiện insert với connection dùng auto-commit trong cấu hình demo → bản ghi **còn lại** dù Java method sau đó ném exception.

So sánh gồm `public`, `protected`, package-private, `private` và **self-invocation**. Runner và service nằm **cùng một Java package** để Java cho phép runner gọi `protected`/package-private trên bean proxy.

### 6.1. Cấu trúc dự án

```text
method-visibility-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/visibility/
        │       ├── VisibilityApplication.java
        │       └── VisibilityService.java
        └── resources/
            └── application.properties
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>method-visibility-demo</artifactId>
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

`spring-boot-starter-jdbc` cung cấp JDBC/transaction infrastructure và pool kết nối. Dependency H2 cung cấp cơ sở dữ liệu in-memory để quan sát rollback không cần cài đặt database ngoài.

### 6.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:visibility_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
```

`DB_CLOSE_DELAY=-1` giúp database in-memory tồn tại trong thời gian JVM chạy dù connection được trả về pool. Đây chỉ là cấu hình phục vụ demo.

### 6.4. `src/main/java/vn/example/visibility/VisibilityService.java`

```java
package vn.example.visibility;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class VisibilityService {
    private final JdbcTemplate jdbc;

    public VisibilityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void publicFail() {
        insertAndFail(1, "public");
    }

    @Transactional
    protected void protectedFail() {
        insertAndFail(2, "protected");
    }

    @Transactional
    void packageFail() {
        insertAndFail(3, "package");
    }

    @Transactional
    private void privateFail() {
        insertAndFail(4, "private");
    }

    public void callPrivate() {
        privateFail();
    }

    @Transactional
    void selfTargetFail() {
        insertAndFail(5, "self");
    }

    public void callSelf() {
        selfTargetFail();
    }

    private void insertAndFail(int id, String label) {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();

        System.out.printf("%s active=%s%n", label, active);
        jdbc.update(
            "INSERT INTO audit_items(id, label) VALUES (?, ?)",
            id, label
        );
        throw new IllegalStateException("Demo failure: " + label);
    }
}
```

Giải thích từng nhóm method:

1. `publicFail()` có `@Transactional`, được caller gọi từ ngoài bean qua proxy. Bắt đầu transaction → insert rồi exception → rollback.
2. `protectedFail()` cũng được gọi từ **bean khác trong cùng package**, qua class-based proxy. Với Spring 6.2 mặc định, transaction interceptor xử lý → rollback.
3. `packageFail()` không có access modifier, cũng gọi từ bean khác **cùng package** qua class-based proxy → rollback trong Spring 6.2 mặc định.
4. `privateFail()` có annotation nhưng **không override được trong CGLIB**. `callPrivate()` không có transaction và gọi private method trực tiếp → không được transaction interceptor bao riêng.
5. `selfTargetFail()` là package-private và có annotation, nhưng `callSelf()` gọi nó từ **cùng target object** → không có lời gọi qua proxy cho inner method.
6. `insertAndFail()` là helper private, không có annotation và được gọi từ cả năm đường đi. Việc helper có thấy transaction hay không phụ thuộc **transaction boundary của caller**, không phụ thuộc visibility riêng của helper.

Tất cả method `@Transactional` có thể xuất hiện hợp lệ trong source. Bản thân việc Java compile và chạy không xác nhận annotation đã có hiệu lực.

### 6.5. `src/main/java/vn/example/visibility/VisibilityApplication.java`

```java
package vn.example.visibility;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class VisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(VisibilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(VisibilityService service, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_items (" +
                "id INT PRIMARY KEY, label VARCHAR(20) NOT NULL)"
            );

            runCase("public", service::publicFail, jdbc);
            runCase("protected", service::protectedFail, jdbc);
            runCase("package", service::packageFail, jdbc);
            runCase("private", service::callPrivate, jdbc);
            runCase("self", service::callSelf, jdbc);
        };
    }

    private static void runCase(String label,
                                Runnable operation,
                                JdbcTemplate jdbc) {
        try {
            operation.run();
        } catch (IllegalStateException expected) {
            // Chỉ bắt exception cố ý của ví dụ.
        }

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_items WHERE label = ?",
            Integer.class,
            label
        );
        System.out.printf("%s rows=%d%n", label, count);
    }
}
```

Vì `VisibilityApplication` và `VisibilityService` cùng package `vn.example.visibility`, các method references `service::protectedFail` và `service::packageFail` **được Java cho phép biên dịch**. Nếu di chuyển runner sang package khác, `packageFail` không còn truy cập được, và `protectedFail` cũng chịu quy tắc truy cập `protected` của Java.

`@EnableTransactionManagement(proxyTargetClass = true)` làm rõ rằng bean `VisibilityService` cần class-based proxy. Class và các method cần intercept không có `final`.

### 6.6. Chạy

Từ thư mục `method-visibility-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/method-visibility-demo-1.0.0.jar
```

Với Spring Boot 3.5.7 / Spring Framework 6.2 và cấu hình trên, các dòng **do code demo tự in** là:

```text
public active=true
public rows=0
protected active=true
protected rows=0
package active=true
package rows=0
private active=false
private rows=1
self active=false
self rows=1
```

Spring Boot còn có thể in log khởi động; bảng ở trên chỉ là **stdout có chủ đích của demo**, theo đúng thứ tự runner gọi. Không cần chờ console HTTP vì ứng dụng chỉ có `CommandLineRunner`, không chứa Spring Web starter.

### 6.7. Vì sao `rows=0` hoặc `rows=1`?

| Lần gọi | Có transaction ở điểm thực thi? | Sau `IllegalStateException` | Số bản ghi tồn tại |
| --- | --- | --- | --- |
| `publicFail()` | Có, qua proxy | Rollback | 0 |
| `protectedFail()` | Có, Spring 6.2 + class proxy + external call | Rollback | 0 |
| `packageFail()` | Có, Spring 6.2 + class proxy + external call | Rollback | 0 |
| `callPrivate()` → `privateFail()` | Không, vì private không được proxy intercept | JDBC auto-commit theo config demo | 1 |
| `callSelf()` → `selfTargetFail()` | Không, vì self-invocation | JDBC auto-commit theo config demo | 1 |

`TransactionSynchronizationManager.isActualTransactionActive()` chứng minh có một **actual transaction** đang gắn với thread ở thời điểm chạy code. Để kiểm chứng chính xác hơn, demo còn kiểm tra **kết quả rollback trên database** sau khi exception thoát khỏi method. Một phép kiểm tra chỉ nhìn `active=true` trong một ngữ cảnh đã có transaction bên ngoài có thể gây ngộ nhận rằng annotation ở inner method đã được intercept.

**Quan trọng:** các dòng `rows=1` chỉ mô tả **demo đơn luồng không có transaction bao bên ngoài**, `JdbcTemplate`/H2 auto-commit và exception sau INSERT. Trong ứng dụng thật, phương thức không được intercept vẫn có thể đang thực thi bên trong transaction đã mở ở nơi khác. Khi đó số bản ghi cuối cùng phụ thuộc transaction thực tế; không được coi private/self-invocation **luôn** khiến dữ liệu commit.

## 7. Cấu hình `publicMethodsOnly`: giữ chính sách chỉ public

Spring 6.2 cho phép đăng ký `TransactionAttributeSource` custom để **bỏ qua phương thức không public** trong metadata transaction, kể cả khi class-based proxy có thể intercept method về mặt Java.

Cấu hình độc lập:

```java
package vn.example.visibility;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionAttributeSource;

@Configuration
class PublicOnlyTransactionConfiguration {

    @Bean
    TransactionAttributeSource transactionAttributeSource() {
        return new AnnotationTransactionAttributeSource(true);
    }
}
```

`true` chính là `publicMethodsOnly = true`. Nó đưa cách xét visibility trở về chính sách public-only giống mặc định trước thời Spring 6.0.

Đây là **biến thể cấu hình**, không phải file bắt buộc cho demo ở phần 6. Nếu thêm vào dự án demo, Spring 6.2 class-based proxy vẫn có thể tồn tại, nhưng transaction metadata cho `protectedFail()` và `packageFail()` sẽ bị lọc theo policy public-only. Khi chạy lại, với điều kiện không có transaction bên ngoài, bạn sẽ thấy các phương thức đó không còn rollback insert giống cấu hình mặc định ở phần 6.

Có thể khôi phục cách xét method không public trong các cấu hình hỗ trợ bằng:

```java
@Bean
TransactionAttributeSource transactionAttributeSource() {
    return new AnnotationTransactionAttributeSource(false);
}
```

Tham số `false` cho phép metadata xét method không public; nó **không biến method private/final thành thứ có thể được proxy intercept**. Tương tự, nó không khiến JDK proxy phơi bày thêm method không thuộc interface, và không sửa vấn đề self-invocation.

Khi dùng Spring Boot/JPA/multi-manager, cần hiểu rõ transaction infrastructure được framework tạo ra. Không nên thêm bean tùy biến chỉ vì “tài liệu có ví dụ”: việc thay đổi `TransactionAttributeSource` ảnh hưởng đến các transaction annotations trong application context tương ứng.

## 8. Khi nâng cấp từ Spring 5.3 sang Spring 6.x

Một thay đổi visibility mặc định có thể tạo **hành vi mới** mà code cũ chưa từng có.

Giả sử code legacy:

```java
@Service
class LegacyReportService {

    @Transactional
    protected void updateSnapshot() {
        // Ghi nhiều bảng.
    }
}
```

Trước khi nâng cấp, với transaction proxy mặc định ở Spring 5.3, annotation trên `protected` có thể bị bỏ qua. Khi lên Spring 6.2 và dùng class-based proxy, một lời gọi hợp lệ **qua proxy** đến `updateSnapshot()` có thể bắt đầu transaction thật. Điều này thường tốt cho atomicity nhưng cũng có thể thay đổi:

- Thời điểm lock và connection được giữ.
- Cách rollback nếu `RuntimeException` hoặc `Error` thoát ra.
- Tương tác với transaction đã tồn tại (`REQUIRED` mặc định), propagation và `rollbackOnly`.
- Số lượng transaction phát sinh, nhu cầu connection pool và quan sát logging.
- Những test trước đây vô tình dựa vào auto-commit hoặc không xác nhận rollback.

**Cách rà soát có trọng tâm:**

1. Xác nhận phiên bản `spring-tx` **đang chạy thực tế**, không chỉ version trong pom gốc; dependency management và transitive dependencies có thể thay đổi.
2. Xác nhận proxy type theo cấu hình runtime: JDK interface hay class-based.
3. Tìm các `@Transactional` đặt trên method `protected` và package-visible, kể cả trong superclass.
4. Xác định lời gọi đến chúng **qua proxy từ bean khác** hay qua self-invocation, private/final/Java access path.
5. Kiểm chứng commit/rollback bằng integration test trên cùng database và transaction manager được deploy.
6. Nếu cần giữ chính sách public-only cũ để migration an toàn, cân nhắc `AnnotationTransactionAttributeSource(true)` và lên kế hoạch thay đổi thiết kế có chủ đích.

Không nên chuyển mọi method sang `public` một cách máy móc: public hóa API ảnh hưởng tới encapsulation. Với các ranh giới nghiệp vụ được gọi từ nhiều bean, `public` thường dễ hiểu và ít phụ thuộc cơ chế proxy hơn; còn protected/package-private có thể hợp lý cho API nội bộ package nếu được kiểm thử rõ.

## 9. Những trường hợp annotation có nhưng không được intercept

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@Transactional` ở `protected` không có hiệu lực khi chạy Spring 5.3 | Policy mặc định public-only | Dùng public boundary hoặc xem xét phiên bản/cấu hình được hỗ trợ. |
| Spring 6.x, `protected` vẫn không có transaction | Proxy là JDK interface, self-invocation, method final hoặc method không đủ điều kiện | Kiểm tra proxy type, call path và visibility. |
| Method package-visible từ superclass khác package không được intercept | Proxy không thể nhìn thấy/override hợp lệ method đó | Đặt boundary ở nơi truy cập phù hợp hoặc tách service. |
| `private` annotated nhưng rollback không xảy ra | Proxy không override/intercept private method | Đặt transaction ở public service method hoặc dùng cơ chế phù hợp khác. |
| Bean tự tạo bằng `new` không có transaction | Không qua Spring container/proxy | Inject Spring-managed bean. |
| `this.method()` không kích hoạt transaction attribute riêng | Self-invocation bỏ qua proxy | Gọi qua bean khác hoặc cấu trúc lại boundary. |
| `public` trên implementation nhưng JDK proxy không phơi bày | Method không có trong interface proxied | Khai báo API trên interface hoặc dùng class proxy khi thích hợp. |
| Có transaction active nhưng `REQUIRES_NEW`/`timeout` ở inner method không chạy | Annotation inner method không được intercept hoặc inner tham gia transaction cũ | Kiểm tra call graph và propagation. |
| Test rollback dù service không có transaction | Test method có transaction do Spring TestContext tự mở | Chạy test bên ngoài test-managed transaction để kiểm tra boundary của service. |

### 9.1. Annotation trên interface và implementation

Spring cho phép đặt `@Transactional` ở interface hoặc implementation trong nhiều cấu hình; tuy nhiên, Spring khuyến nghị **đặt ở concrete class/method** để tránh phụ thuộc cơ chế tìm metadata và đặc biệt tránh khác biệt với AspectJ weaving. Annotation Java trên interface không tự được kế thừa như annotation trên class. Nếu chuyển giữa proxy mode và AspectJ hoặc giữa JDK và class proxy, hãy kiểm tra lại transaction attributes thay vì dựa vào assumptions.

### 9.2. Cùng method được gọi trong transaction cũ

Ví dụ:

```java
@Transactional
public void outer() {
    helper(); // helper được gọi nội bộ.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
protected void helper() {
    // Không được REQUIRES_NEW nếu self-invocation bỏ qua proxy.
}
```

Đây là trích đoạn; cần import `Propagation`. `helper()` có thể chạy **trong transaction của outer** vì outer đã mở giao dịch, nhưng **không tạo transaction mới** như annotation inner yêu cầu. Khi chỉ kiểm tra `isActualTransactionActive() == true`, bạn có thể kết luận sai rằng inner annotation hoạt động. Hãy kiểm tra ranh giới vật lý và kết quả commit/rollback trong thử nghiệm riêng.

### 9.3. Method trong `@PostConstruct` hoặc constructor

Proxy phải được tạo và khởi tạo xong trước khi caller dùng. Gọi method annotated trong constructor hoặc callback initialization như `@PostConstruct` có thể không đi qua transaction proxy như bạn nghĩ. Khởi tạo dữ liệu nên có cơ chế Spring startup thích hợp gọi bean qua proxy sau khi context sẵn sàng, hoặc dùng transaction API chương trình nếu có nhu cầu đặc biệt.

### 9.4. Method `final`, class `final` và Java modules

CGLIB dùng subclassing; do đó `final` chặn subclass/override. Trong Kotlin, class/method mặc định final nếu không mở bằng `open` hoặc plugin thích hợp. Trong Java module có giới hạn truy cập, proxy có thể gặp hạn chế tạo lớp. Cần xác nhận lỗi startup và proxy thực tế thay vì suy luận rằng tăng visibility sẽ tự sửa mọi trường hợp.

## 10. AspectJ mode: khác bản chất proxy mode

Có thể dùng Spring transaction management với `AdviceMode.ASPECTJ` thay vì `AdviceMode.PROXY`. AspectJ weave transaction advice vào bytecode nên không chịu cùng hạn chế “phải gọi qua object proxy”. Theo tài liệu Spring, aspect có thể xử lý self-invocation và các dạng method không public khi weave đúng, tùy annotation placement và cách build.

Cấu hình minh họa:

```java
@Configuration
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
class AspectJTransactionConfiguration {
}
```

Đây là **trích đoạn cấu hình**, cần import `org.springframework.context.annotation.AdviceMode` và `@EnableTransactionManagement`. Dùng AspectJ thực tế cần dependency `spring-aspects` và cấu hình compile-time hoặc load-time weaving đúng. Chỉ thêm `mode = ASPECTJ` mà không bật weaving **không đủ**.

Quan trọng về phạm vi:

- Bài này phân tích **proxy mode**, là cách mặc định phổ biến.
- **“Private không hoạt động”** là kết luận về **proxy advice**. Với weaving, hành vi có thể khác; phải kiểm tra annotation và weaving setup cụ thể.
- Không chuyển sang AspectJ chỉ để “sửa nhanh” một self-invocation: nó tăng chi phí cấu hình, build, debug và runtime. Thường có thể giải quyết bằng cách tách boundary sang bean khác.

## 11. Cách kiểm chứng ở runtime và trong test

### 11.1. Xác nhận bạn đang cầm proxy

Trong test/chẩn đoán có thể dùng:

```java
boolean proxy = AopUtils.isAopProxy(service);
boolean jdk = AopUtils.isJdkDynamicProxy(service);
boolean cglib = AopUtils.isCglibProxy(service);

System.out.printf(
    "proxy=%s, jdk=%s, cglib=%s%n",
    proxy, jdk, cglib
);
```

Đây là **trích đoạn**, cần import `org.springframework.aop.support.AopUtils` và biến `service` do Spring inject. Nó giúp thấy proxy type, nhưng **không chứng minh mỗi method đều có transaction advice**. Để xác minh hãy gọi method qua proxy với test commit/rollback và kiểm tra transaction manager.

### 11.2. Đo có transaction bằng API Spring

Bên trong method được gọi:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("tx active: " + active);
```

Đây là trích đoạn; cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. `active=true` cho biết có transaction hiện tại trong thread, **không khẳng định** annotation của chính method đó được intercept. Một inner method không được advice vẫn có thể chạy khi caller đã mở transaction.

### 11.3. Integration test đúng mục tiêu

Một test để so sánh visibility nên:

1. Sử dụng framework version/transaction manager/proxy mode thực sự cần đánh giá.
2. Tạo Spring context và gọi **bean đã inject**, không `new` service.
3. Kiểm tra cả `public`, `protected` và package-visible từ **caller hợp lệ theo Java** và nằm ngoài target.
4. Để thấy sự khác biệt, bắt đầu bài test **không có transaction bên ngoài**; nếu test đã có `@Transactional`, mọi method có thể thấy transaction tồn tại trước đó.
5. Dùng database thật hoặc H2/testcontainers phù hợp; cố ý ném `RuntimeException` sau ghi và đọc lại từ transaction/connection khác để thấy rollback.
6. Thêm test riêng cho `this.method()`, `private` và `final`.
7. Kiểm tra các transaction attributes như `propagation`, `readOnly` hoặc `timeout` khi cần: có transaction active không đủ để khẳng định cấu hình cụ thể được áp dụng.

**Cẩn thận với Spring TestContext:** test method annotated `@Transactional` thường được TestContext mở transaction và rollback tự động. Điều này có thể tạo **false positive** cho kiểm thử service boundary. Muốn đánh giá proxy method độc lập, hãy dùng test method không `@Transactional` hoặc tách bước khởi tạo/đọc kết quả ra ngoài test-managed transaction.

### 11.4. Logging và quan sát

Trong môi trường dev/test, có thể bật logging transaction interceptor:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
```

Kiểm tra log có transaction advice áp dụng cho method nào; kết hợp với database assertion. Đừng suy ra transaction đúng chỉ từ một dòng log, và tránh bật logging chi tiết ở production khi không cần.

## 12. Bảng quyết định thực hành

| Bạn muốn gì? | Cách làm có thể duy trì tốt |
| --- | --- |
| Một public service operation luôn có transaction | `@Transactional` trên `public` method, gọi qua Spring bean proxy, manager được cấu hình đúng. |
| Dùng protected/package-private với Spring 6.2 | Class-based proxy, caller ngoài target có quyền truy cập Java, method có thể override; test rollback trên database. |
| Bắt buộc JDK interface proxy | Đưa nghiệp vụ transaction vào `public` methods được khai báo trên interface; đặt annotation trên concrete implementation để rõ ràng. |
| Giữ behavior public-only khi nâng Spring 5.3 → 6.x | Custom `AnnotationTransactionAttributeSource(true)` và test lại phạm vi toàn ứng dụng. |
| Có helper nội bộ cần giao dịch riêng | Tách helper thành một Spring service/bean có public transactional operation, gọi qua proxy. |
| Muốn self-invocation thật sự được advice mà không đổi cách gọi | Nghiên cứu AspectJ weaving, vận hành/test đầy đủ; không xem là thay thế miễn phí. |
| Đang gặp transaction active nhưng rollback riêng không đúng | Truy dấu actual caller, proxy type, propagation, exception rules và transaction manager. |

## 13. Checklist trước khi tin rằng `@Transactional` có hiệu lực

- [ ] Xác nhận **Spring Framework version** ở runtime, đặc biệt mốc **5.3 → 6.0+**.
- [ ] Xác nhận đang dùng **Spring proxy mode** hay **AspectJ weaving**.
- [ ] Xác nhận **JDK interface proxy** hay **class-based proxy**.
- [ ] Với JDK proxy, method là **public** và được khai báo trên interface proxied.
- [ ] Với class proxy, method public/protected/package-visible nằm trong phạm vi Spring version và **có thể override/intercept**.
- [ ] Không dùng `private`/`final` như một transaction boundary kỳ vọng CGLIB intercept.
- [ ] Caller gọi qua **Spring-injected proxy**, không qua `new` hoặc `this`.
- [ ] Java access rules cho phép external caller thật sự gọi method.
- [ ] Transaction infrastructure/manager đã được cấu hình, không chỉ có annotation.
- [ ] Nếu dùng `AnnotationTransactionAttributeSource(true)`, đã tính tới việc **non-public methods bị bỏ qua**.
- [ ] Kiểm thử bằng **database commit/rollback**, đồng thời quan sát transaction active để chẩn đoán.
- [ ] Các test không bị transaction do TestContext mở trước che giấu behavior cần đo.
- [ ] Khi nâng cấp, rà soát những method không public có thể **bắt đầu nhận advice mới**.

## 14. Câu hỏi ôn tập

**Câu 1.** Spring 6.2 có class-based proxy, `@Transactional` đặt trên `protected void reserve()`, caller là bean khác cùng package và gọi `proxy.reserve()`. Annotation có thể hoạt động không?

**Đáp án:** **Có**, nếu bean/proxy/transaction manager đúng và method có thể intercept. Đó là thay đổi quan trọng từ Spring 6.0.

**Câu 2.** Cùng method trên nhưng được gọi từ `this.reserve()` bên trong target, không có transaction ngoài. Có transaction riêng không?

**Đáp án:** **Không**, self-invocation bỏ qua proxy. Việc method là `protected` và Spring 6.2 hỗ trợ visibility đó không thay đổi đường đi của lời gọi.

**Câu 3.** Spring 6.2 dùng JDK proxy; implementation có thêm `public void reindex()` không thuộc interface proxied. Caller chỉ inject interface. Có thể gọi `reindex()` và mong advice chạy không?

**Đáp án:** **Không thể gọi method này qua interface proxy**. Phải dùng interface API phù hợp hoặc thiết kế class proxy khi cần; không lấy target trực tiếp để vượt qua proxy.

**Câu 4.** `@Transactional` trên `private void save()`, Spring 6.2 class proxy. Có rollback độc lập khi gọi private method không?

**Đáp án:** **Không phải transaction boundary do proxy tạo**. Private method không thể được CGLIB override/intercept; nếu method chạy trong một outer transaction khác thì nó vẫn có thể tham gia transaction đang mở.

**Câu 5.** Sau nâng cấp, muốn mặc định chỉ xét public methods. Dùng gì?

**Đáp án:** Bean `TransactionAttributeSource` cấu hình `new AnnotationTransactionAttributeSource(true)` và test lại các transaction boundaries.

## Tài liệu chính thức

1. Spring Framework 6.2 — [Using `@Transactional`: method visibility trong proxy mode](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html). Nêu thay đổi của Spring 6.0, JDK vs class proxy và `publicMethodsOnly`.
2. Spring Framework 5.3 — [Data Access / Transaction Management](https://docs.spring.io/spring-framework/docs/5.3.31/reference/html/data-access.html): mô tả chính sách `public` trong thế hệ cũ.
3. Spring Framework 6.2 — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): giới hạn `private`, `final`, package-private method từ superclass ở package khác, và self-invocation.
4. Spring Framework 6.2 — [`@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
5. Spring Framework 6.2 — [`AnnotationTransactionAttributeSource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html): tham số `publicMethodsOnly`.
6. Spring Framework 6.2 — [TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): transaction trên test method khác với transaction boundary của service.

**Thông điệp quan trọng nhất:** **Spring 5.3 mặc định public-only; Spring 6.0+ mở rộng protected/package-visible cho class-based proxy; JDK proxy vẫn public trên interface.** Dù phiên bản nào, transaction advice chỉ chạy nếu lời gọi thực sự đi **qua proxy đủ khả năng intercept**. `private`, `final`, self-invocation và Java access rules là những giới hạn riêng phải kiểm tra.
