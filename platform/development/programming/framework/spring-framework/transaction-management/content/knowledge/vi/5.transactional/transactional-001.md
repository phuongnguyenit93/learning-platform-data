# Annotation chỉ là metadata cần hạ tầng xử lý: hiểu đúng @Transactional của Spring

## 1. Mục tiêu

Khi nhìn thấy `@Transactional` trên một phương thức, nhiều người hình dung JVM sẽ tự động mở giao dịch trước phương thức đó, commit khi kết thúc và rollback nếu gặp lỗi. **Đó không phải cách Java annotation hoạt động.** Annotation là thông tin mô tả; tác dụng giao dịch chỉ xuất hiện khi có hạ tầng đọc thông tin ấy và thực sự can thiệp vào lời gọi phương thức.

Sau bài này, bạn có thể:

- Giải thích chính xác `@Transactional` là **metadata khai báo ý định giao dịch**, không phải mã Java tự chạy.
- Trình bày vai trò của Spring container, transaction management configuration, AOP proxy, `TransactionInterceptor`, `TransactionAttributeSource` và `PlatformTransactionManager`.
- Nhận ra các trường hợp có annotation nhưng transaction advice không được thực thi: đối tượng tạo bằng `new`, self-invocation, phương thức không thể được proxy intercept hoặc gọi sai application context.
- Phân biệt “annotation được phát hiện”, “lời gọi đi qua interceptor” và “thao tác dữ liệu tham gia đúng transaction”.
- Chạy ví dụ Java 17+ quan sát ba trường hợp: gọi qua Spring proxy được rollback; tự gọi trong cùng bean và gọi trên đối tượng tạo thủ công không được rollback.

Bài đặt trong ngữ cảnh **Spring Framework — transaction management**, nhóm `@Transactional`. Nội dung tập trung vào cơ chế kích hoạt annotation, không xem mọi cấu hình giao dịch hoặc mọi kiểu persistence đều giống nhau.

## 2. Annotation trong Java: mô tả, không phải câu lệnh thực thi

Annotation là metadata đính kèm lớp, phương thức hoặc thành phần chương trình. Java compiler/JVM có thể giữ, kiểm tra hoặc công bố metadata tùy annotation và retention policy. **Bản thân annotation không tự chèn lệnh `begin`, `commit`, `rollback` vào thân phương thức.**

Ví dụ:

```java
import org.springframework.transaction.annotation.Transactional;

public class PaymentService {
    @Transactional
    public void charge() {
        System.out.println("Charging...");
    }
}
```

Đoạn trên là **minh họa cú pháp**, cần thư viện `spring-tx` để biên dịch, và chưa phải ứng dụng độc lập. Nếu chỉ chạy:

```java
new PaymentService().charge();
```

Java thực thi `charge()` như lời gọi phương thức bình thường. Không có Spring bean/proxy/transaction manager nào được tạo chỉ bởi annotation. Spring có thể đọc annotation lúc runtime để lấy quy tắc giao dịch, nhưng đọc được không đồng nghĩa đã can thiệp vào lời gọi.

Một annotation có thể có `@Retention(RetentionPolicy.RUNTIME)` để truy cập bằng reflection. Ngay cả trong trường hợp ấy, cần **một chủ thể tiêu thụ metadata**: framework, annotation processor, bytecode weaver hoặc mã do bạn viết. `@Transactional` của Spring là ví dụ điển hình về annotation được hạ tầng Spring diễn giải.

Đừng đồng nhất với mọi annotation khác: `@Override` giúp compiler kiểm tra hợp đồng override; `@Deprecated` mang thông tin cảnh báo; `@Transactional` mô tả quy tắc nghiệp vụ cần Spring thực thi tại runtime. Mỗi annotation có hiệu lực theo công cụ xử lý tương ứng, không theo tên bắt đầu bằng `@`.

## 3. @Transactional khai báo gì?

`org.springframework.transaction.annotation.Transactional` biểu diễn quy tắc giao dịch cho một phương thức hoặc kiểu được áp dụng. Những thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa trong metadata | Ví dụ |
| --- | --- | --- |
| `propagation` | Cách tham gia/tạo transaction khi đã hoặc chưa có transaction | `REQUIRED` (mặc định), `REQUIRES_NEW` |
| `isolation` | Yêu cầu mức cô lập từ transaction manager/tài nguyên | `Isolation.READ_COMMITTED` |
| `readOnly` | Chỉ dẫn tối ưu hoặc ngữ nghĩa đọc cho manager/driver có hỗ trợ | `readOnly = true` |
| `timeout` | Thời hạn giao dịch theo đơn vị giây khi áp dụng được | `timeout = 5` |
| `rollbackFor` | Thêm kiểu exception phải rollback | `rollbackFor = IOException.class` |
| `noRollbackFor` | Ngoại lệ không yêu cầu rollback theo quy tắc đã khai báo | `noRollbackFor = BusinessException.class` |
| `transactionManager` | Chọn manager theo tên/qualifier khi có nhiều manager | `transactionManager = "ordersTxManager"` |

Ví dụ minh họa:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false,
    rollbackFor = IOException.class
)
public void publishInvoice() throws IOException {
    // Thao tác dữ liệu thuộc một use case.
}
```

Đoạn này chỉ mô tả **cấu hình mong muốn**. Nếu lời gọi không được transaction advice intercept, các thuộc tính vẫn nằm trong metadata nhưng không tự tạo transaction. `readOnly` cũng không có nghĩa JVM tự cấm câu lệnh ghi; tác dụng của nó tùy hạ tầng/tài nguyên.

Trong cơ chế mặc định của Spring Framework 6.1, `@Transactional` dùng propagation `REQUIRED`, isolation `DEFAULT`, giao dịch read-write, rollback với `RuntimeException` hoặc `Error`; checked exception không yêu cầu rollback trừ khi cấu hình khác. Quy tắc cụ thể có thể được tùy biến bởi phiên bản/configuration. **Đó là quy tắc mà hạ tầng sử dụng**, không phải Java annotation tự bắt exception.

## 4. Hạ tầng nào biến metadata thành hành vi?

Một ứng dụng Spring imperative dùng declarative transaction thường có các thành phần sau:

1. **Spring ApplicationContext** quản lý bean nghiệp vụ. Đây là cơ sở để Spring tạo/wrap bean phù hợp.
2. **Bộ kích hoạt xử lý transaction annotation**, ví dụ `@EnableTransactionManagement`, XML `<tx:annotation-driven/>` hoặc cấu hình tự động thích hợp trong Spring Boot.
3. **`TransactionAttributeSource`**, thường là `AnnotationTransactionAttributeSource`, đọc metadata `@Transactional` và chuyển thành transaction attributes.
4. **Advisor và Spring AOP proxy** áp dụng transactional advice cho những lời gọi thuộc phạm vi proxy.
5. **`TransactionInterceptor`** thực thi điều phối giao dịch xung quanh invocation.
6. **`PlatformTransactionManager`** phù hợp với mô hình imperative và tài nguyên dữ liệu: `JdbcTransactionManager`/`DataSourceTransactionManager` cho JDBC, `JpaTransactionManager` cho JPA, hoặc implementation khác.
7. **Thư viện truy cập dữ liệu tham gia transaction**, chẳng hạn `JdbcTemplate` dùng đúng `DataSource`, hoặc repository/JPA sử dụng cùng manager. Nếu thao tác sử dụng tài nguyên riêng không được manager đó quản lý, annotation không tự bao phủ nó.

Sơ đồ:

```text
Caller (bean khác, controller, listener)
             |
             v
Spring AOP proxy của Service
             |
             v
TransactionInterceptor
  +-- TransactionAttributeSource đọc @Transactional
  +-- PlatformTransactionManager lấy/khởi tạo transaction
             |
             v
Service thực thi nghiệp vụ (target method)
             |
       JDBC/JPA/repositories
       cùng transaction resource
             |
             v
Interceptor commit hoặc rollback theo kết quả
             |
             v
Caller nhận return/exception
```

**Cơ chế then chốt**: proxy là đối tượng đại diện mà caller thực sự gọi; proxy có cơ hội chạy logic trước/sau/ngoại lệ quanh lời gọi đến target. Nếu caller giữ reference trực tiếp tới đối tượng target không qua proxy, transaction interceptor không được thực thi.

### 4.1. Vì sao cần transaction manager?

Proxy biết *khi nào* nên quản lý giao dịch, nhưng không tự biết *cách* mở và commit giao dịch trên tài nguyên thực. Transaction manager thực hiện việc đó. Ví dụ, `DataSourceTransactionManager` điều phối JDBC connection từ `DataSource`; `JpaTransactionManager` điều phối EntityManager và transaction tài nguyên tương ứng.

Có `@Transactional` và proxy mà thiếu/không tìm được manager phù hợp thì lời gọi có thể thất bại do cấu hình, thay vì âm thầm chuyển thành giao dịch hợp lệ. Ngược lại, chỉ tạo transaction manager bean **không tự biến** mọi lời gọi Java thành lời gọi qua proxy.

### 4.2. @EnableTransactionManagement có ý nghĩa gì?

Trong Spring Framework thuần, thường sử dụng:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần `DataSource` đã được cấu hình và các import tương ứng. `@EnableTransactionManagement` đăng ký hạ tầng xử lý `@Transactional` trong application context. Khi kết hợp bean và manager phù hợp, transaction advice có thể được áp dụng.

**Lưu ý với Spring Boot:** auto-configuration có thể cung cấp cả manager lẫn xử lý declarative transaction khi điều kiện thỏa mãn; không bắt buộc mọi ứng dụng Boot đều phải viết `@EnableTransactionManagement` bằng tay. Ngược lại, việc xóa annotation này khỏi một ứng dụng Boot **không phải phép thử đáng tin để vô hiệu hóa transaction** vì Boot có thể vẫn tự kích hoạt. Phải kiểm tra configuration/context thực tế.

### 4.3. Proxy không phải bản thân @Transactional

Một bean có thể được proxy vì transaction advice hoặc các advice khác; `AopUtils.isAopProxy(bean)` kiểm tra proxy nhưng **không chứng minh một phương thức cụ thể sẽ được chạy trong transaction**. Để chứng minh, kiểm tra transaction active bên trong đúng phương thức, trạng thái commit/rollback sau lời gọi và resource thật.

Với proxy mode, Spring có thể dùng JDK interface proxy hoặc class-based proxy (CGLIB). Lựa chọn phụ thuộc cấu hình, loại bean và môi trường; không nên đoán chỉ từ việc có `@Transactional`. Trong ví dụ bên dưới, service không khai báo interface nên Spring sử dụng class-based proxy.

## 5. Khi nào annotation “có mặt” mà không phát huy tác dụng?

### 5.1. Đối tượng tạo bằng new không thuộc bean lifecycle

```java
PaymentService service = new PaymentService();
service.charge();
```

Nếu không có Spring proxy/interceptor nào bọc đối tượng, `charge` chỉ là phương thức Java bình thường. Metadata vẫn có thể đọc được qua reflection, nhưng transaction không tự khởi tạo. Tương tự, tự tạo instance trong mã thay vì inject bean có thể bỏ qua hạ tầng Spring.

### 5.2. Self-invocation: this.method() đi thẳng vào target

```java
@Service
class OrderService {
    public void handle() {
        this.save();
    }

    @Transactional
    public void save() {
        // Ghi dữ liệu
    }
}
```

Đây là mã minh họa (không bao gồm repository). Trong **proxy mode mặc định**, dù bên ngoài gọi `orderService.handle()` qua proxy, lời gọi `this.save()` diễn ra bên trong target và không đi qua proxy một lần nữa. Nếu `handle()` chưa nằm trong transaction, `save()` sẽ không tự tạo transaction vì annotation trên nó.

**Điểm tinh tế:** nếu `handle()` đã mở một transaction, `this.save()` có thể thực thi **bên trong transaction sẵn có** do luồng đang tham gia, nhưng những thuộc tính riêng trên `save()` (chẳng hạn `REQUIRES_NEW`) không được áp dụng qua self-invocation. Vì vậy, “self-invocation luôn không có transaction” là kết luận quá mạnh; kết luận chính xác là **lời gọi nội bộ không được interception riêng**.

Cách sửa thông thường: đưa thao tác cần ranh giới độc lập sang bean khác rồi inject/call bean đó, hoặc tái thiết kế nơi đặt transaction boundary. Không nên dựa vào `AopContext.currentProxy()` như một cách mặc định để cứu thiết kế.

### 5.3. Không thể intercept một số phương thức

Spring AOP proxy có giới hạn của proxy Java: phương thức `private` không thể được override/intercept bởi class-based proxy; `final` không thể được subclass override, vì vậy transaction advice kiểu class proxy không chặn được lời gọi tương ứng. Với JDK proxy, các method trên interface có thể được ủy quyền qua proxy theo interface; những method chỉ tồn tại trên class target không được đưa vào JDK proxy như method của interface.

Trong Spring Framework 6.x, class-based proxy có thể hỗ trợ một số phương thức `protected` hoặc package-private theo cấu hình, nhưng phương thức **public, non-final trên Spring bean cụ thể** là lựa chọn dễ dự đoán và dễ kiểm thử nhất. Không coi mọi phương thức non-public là giống nhau ở mọi phiên bản.

Một method ở `@PostConstruct` hoặc trong quá trình khởi tạo bean cũng không phải nơi an toàn để kỳ vọng proxy hoàn chỉnh đã intercept. Cần di chuyển logic khởi động sang lời gọi qua bean đã được khởi tạo hoàn toàn.

### 5.4. Annotation và context không khớp

Hạ tầng transaction được đăng ký trong một `ApplicationContext` cụ thể. Nếu service bean ở context cha nhưng chỉ bật xử lý annotation trong một servlet child context, Spring có thể chỉ quét bean của context con. Tương tự, thiếu `@ComponentScan`, cấu hình tự động bị loại hoặc thiếu transaction manager đúng tên có thể dẫn tới không được intercept hoặc lỗi cấu hình.

### 5.5. Annotation đặt trên interface

Spring có thể nhận metadata `@Transactional` trên interface trong các tình huống proxy nhất định. Tuy nhiên, Java annotation không tự kế thừa từ interface theo nghĩa `@Inherited`, và AspectJ weaving không nhận annotation interface theo cách tương tự. Để tránh phụ thuộc khác biệt cơ chế, Spring khuyến nghị đánh dấu **phương thức trên concrete class**.

### 5.6. Đổi thread hoặc dùng Reactive

`PlatformTransactionManager` thường gắn transaction imperative với thread hiện tại. Gọi `@Async` hay tạo thread mới không tự chuyển transaction đang có sang thread đó. Với reactive pipeline, Spring dùng cơ chế khác (`ReactiveTransactionManager` và Reactor context) và lời gọi phải nằm trong reactive pipeline đúng cách. Một annotation giống nhau **không có nghĩa runtime context giống nhau**.

## 6. Ví dụ chạy được: cùng @Transactional nhưng ba kết quả khác nhau

Ví dụ Java 17+ sử dụng Spring Boot 3.3.13, Spring JDBC, H2 in-memory và một bảng đơn giản. Version Spring Boot được ghim để tái hiện bài học; với ứng dụng sản xuất hãy chọn phiên bản còn được hỗ trợ.

Ba lần ghi dữ liệu đều cố tình ném `IllegalStateException` **sau câu INSERT**:

- Gọi `service.writeThenFail(...)` từ bên ngoài qua Spring proxy: transaction active, INSERT bị rollback.
- Gọi `service.selfCall()` rồi method đó gọi `this.writeThenFail(...)`: annotation ở lời gọi nội bộ không được intercept, INSERT đã auto-commit.
- Tạo `new PlainWriter(jdbc)` và gọi method có `@Transactional`: không phải Spring bean/proxy, INSERT đã auto-commit.

### 6.1. Cấu trúc dự án

```text
transaction-metadata-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/metadata/
    │   ├── MetadataApplication.java
    │   └── EventService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-metadata-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Ứng dụng chỉ dùng starter JDBC, không khai báo `spring-boot-starter-web` nên không cần web server. Starter cung cấp Spring transaction support và `JdbcTemplate`, H2 cung cấp database in-memory, Boot khởi tạo schema từ `schema.sql`.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE lesson_event (
    id INT PRIMARY KEY,
    source VARCHAR(32) NOT NULL
);
```

**`src/main/java/demo/metadata/EventService.java`**

```java
package demo.metadata;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class EventService {
    private final JdbcTemplate jdbc;

    public EventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeThenFail(int id, String label) {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();
        System.out.println(label + " txActive=" + active);

        jdbc.update(
            "INSERT INTO lesson_event(id, source) VALUES (?, ?)",
            id, label
        );

        throw new IllegalStateException("demo-error");
    }

    public void selfCall() {
        // Lời gọi này không đi qua Spring proxy lần thứ hai.
        this.writeThenFail(2, "self");
    }
}
```

Phương thức `writeThenFail` public, non-final, được gọi qua proxy ở lần đầu. Lần `selfCall` gọi nội bộ thì giao dịch không được kích hoạt riêng. `TransactionSynchronizationManager.isActualTransactionActive()` là phép quan sát tiện lợi với mô hình imperative, **không thay thế kiểm tra commit/rollback trên DB**.

**`src/main/java/demo/metadata/MetadataApplication.java`**

```java
package demo.metadata;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableTransactionManagement
public class MetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(EventService service, JdbcTemplate jdbc) {
        return args -> {
            boolean annotated = EventService.class
                .getMethod("writeThenFail", int.class, String.class)
                .isAnnotationPresent(Transactional.class);
            System.out.println("annotationPresent=" + annotated);
            System.out.println("serviceProxied=" + AopUtils.isAopProxy(service));

            try {
                service.writeThenFail(1, "external");
            } catch (IllegalStateException ex) {
                System.out.println("external exception=" + ex.getMessage());
            }
            System.out.println("rows#1=" + count(jdbc, 1));

            try {
                service.selfCall();
            } catch (IllegalStateException ex) {
                System.out.println("self exception=" + ex.getMessage());
            }
            System.out.println("rows#2=" + count(jdbc, 2));

            try {
                new PlainWriter(jdbc).writeThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("new exception=" + ex.getMessage());
            }
            System.out.println("rows#3=" + count(jdbc, 3));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM lesson_event WHERE id = ?",
            Integer.class, id
        );
        return value;
    }

    static class PlainWriter {
        private final JdbcTemplate jdbc;

        PlainWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void writeThenFail() {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
            System.out.println("new txActive=" + active);

            jdbc.update(
                "INSERT INTO lesson_event(id, source) VALUES (?, ?)",
                3, "new"
            );

            throw new IllegalStateException("demo-error");
        }
    }
}
```

**Các chi tiết cần quan sát**:

- `EventService` là Spring bean. `@EnableTransactionManagement` bật hạ tầng transaction, bean `PlatformTransactionManager` quản lý `DataSource` đang được `JdbcTemplate` sử dụng. Để bài minh họa tự chứa, ta khai báo manager tường minh, dù Boot trong nhiều cấu hình có thể tự cấu hình manager.
- `demo(EventService service, ...)` nhận Spring bean đã được post-process/proxy, không tự `new EventService(...)`.
- `AopUtils.isAopProxy(service)` xác nhận service đang được proxy; `isAnnotationPresent` chỉ xác nhận **metadata tồn tại** trên class method. Hai phép kiểm này không tương đương nhau.
- Ba case dùng id 1, 2, 3 riêng; tất cả exception đều bị caller bắt **sau** khi method đã kết thúc; `count` chạy ngoài transaction của service nên thấy trạng thái DB sau commit/rollback.
- `PlainWriter` là nested class không được đăng ký thành bean. Dù method có `@Transactional`, gọi bằng `new` không có advice.

### 6.2. Chạy và đối chiếu stdout

Yêu cầu JDK 17+ và Gradle 8.x. Từ thư mục `transaction-metadata-demo`:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, trên Linux/macOS chạy `./gradlew bootRun` hoặc trên Windows chạy `gradlew.bat bootRun`. Không dùng `javac` trực tiếp cho dự án trên vì code phụ thuộc các thư viện Spring/H2 ngoài JDK; Gradle đảm nhiệm tải classpath, compile và khởi chạy.

Bỏ qua log startup của Spring Boot/Gradle; những dòng `System.out.println` của chương trình, theo đúng thứ tự, là:

```text
annotationPresent=true
serviceProxied=true
external txActive=true
external exception=demo-error
rows#1=0
self txActive=false
self exception=demo-error
rows#2=1
new txActive=false
new exception=demo-error
rows#3=1
```

**Giải thích kết quả**:

1. `annotationPresent=true`: reflection tìm được `@Transactional` trên `EventService.writeThenFail`. Chỉ riêng điều này **không** chứng minh transaction hoạt động.
2. `serviceProxied=true`: Spring đã tạo AOP proxy cho service.
3. `external txActive=true`: lời gọi ngoài qua proxy vào `writeThenFail`, interceptor bắt đầu transaction. Exception runtime thoát ra khiến transaction manager rollback. `rows#1=0` chứng minh không còn bản ghi id 1.
4. `self txActive=false`: `selfCall` không được `@Transactional` đánh dấu và `this.writeThenFail` bypass proxy. Vì connection không có transaction do Spring mở cho lần này, JDBC/H2 auto-commit câu INSERT thành công; exception Java phía sau không tự rollback. `rows#2=1`.
5. `new txActive=false`: `PlainWriter` không phải bean/proxy. Annotation vẫn có trong class file, nhưng không có interceptor. INSERT auto-commit; `rows#3=1`.

Lưu ý kết quả `rows#2` và `rows#3` dựa trên mặc định auto-commit của H2 connection do pool cung cấp trong ví dụ. Một transaction bên ngoài do người gọi mở, hoặc một `DataSource`/connection tùy biến, có thể thay đổi kết quả. Vì thế không diễn giải thành “self-invocation **luôn** tự commit”; kết luận bền vững là **hạ tầng của method được gọi nội bộ không được kích hoạt**.

### 6.3. Điều gì sẽ xảy ra nếu đổi annotation?

Nếu bạn đặt `@Transactional` trực tiếp lên `selfCall` (đảm bảo gọi `service.selfCall()` từ bean khác qua proxy), transaction được mở **trước khi** code trong `selfCall` chạy; `this.writeThenFail` lúc đó tham gia transaction đã có. Như vậy bản ghi id 2 sẽ rollback dù lời gọi nội bộ không được intercept riêng. Đây là khác biệt then chốt giữa:

- **“Lời gọi cụ thể được intercept”**: xác định advice có áp dụng chính method đó hay không.
- **“Hiện đang có transaction”**: có thể do lời gọi bao ngoài tạo trước.
- **“Dữ liệu có rollback không”**: còn phụ thuộc manager/tài nguyên/ngoại lệ/commit scope.

Không áp dụng thay đổi này khi đối chiếu stdout gốc, vì nó thay đổi mục đích bài thử.

## 7. Ba tầng kiểm chứng trong ứng dụng thực

### Tầng A — Metadata có tồn tại và đúng nơi không?

Kiểm tra:

- Annotation là `org.springframework.transaction.annotation.Transactional` hay biến thể có cơ chế xử lý khác?
- Đặt trên concrete method/class mà Spring thực sự thấy? Có annotation trên interface, phương thức kế thừa hoặc metadata bị override?
- Các thuộc tính `propagation`, `readOnly`, `rollbackFor` khai báo đúng ý định?
- Trong trường hợp dùng composed annotation, hạ tầng có đọc meta-annotation và alias đúng không?

Reflection `isAnnotationPresent` chỉ phù hợp cho một kiểu kiểm tra đơn giản; Spring có cơ chế truy vấn annotation/meta-annotation riêng. Reflection dương tính **chưa** chứng minh transaction chạy.

### Tầng B — Lời gọi có thật đi qua Spring transaction advice?

Kiểm tra:

- Instance là Spring-managed bean, do inject/context cung cấp?
- Bean có AOP proxy hoặc cơ chế AspectJ weaving tương ứng không?
- Caller đến từ bean khác qua proxy, hay `this.method()`/`new`/constructor/`@PostConstruct`?
- Method có thể được proxy intercept không? Có `final/private` hoặc JDK proxy không expose method?
- Có bật transaction management trong đúng `ApplicationContext` không?
- Có nhiều bean cùng tên/tương tự, khiến code dùng nhầm instance ngoài container không?

Có proxy không đồng nghĩa mọi method đều được advice; cần kiểm tra pointcut/transaction attribute cho method thực tế.

### Tầng C — Transaction có hiệu lực lên đúng tài nguyên và kết quả không?

Kiểm tra:

- Manager nào được chọn, và có đúng `DataSource` / `EntityManagerFactory` mà repository sử dụng?
- Một method được đánh dấu transaction active, nhưng thư viện truy cập dữ liệu có tự mở connection độc lập hay gửi I/O sang hệ thống khác không?
- Exception có thoát tới interceptor theo rollback rule không? Exception checked có cần `rollbackFor` không?
- Scope này **tạo mới** transaction hay chỉ **tham gia** transaction ngoài (`REQUIRED`)? Commit cuối nằm ở scope nào?
- Có lời gọi `@Async`/thread mới làm mất thread-bound context không?
- Sau khi method kết thúc, DB thực tế đã commit/rollback như mong đợi chưa?

**Bằng chứng mạnh nhất** là kiểm thử có tình huống ghi dở rồi ném lỗi, sau đó đọc lại trạng thái DB khi transaction đã kết thúc. Kiểm tra `TransactionSynchronizationManager.isActualTransactionActive()` giúp chẩn đoán nhưng chưa đủ để kết luận tất cả thao tác cùng một transaction.

## 8. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế | Cách kiểm chứng |
| --- | --- | --- |
| “Có `@Transactional` tức là luôn rollback khi exception.” | Annotation chỉ là metadata; còn cần hạ tầng và lời gọi được intercept. | Chạy case `new` và self-invocation. |
| “Chỉ cần `spring-tx` trên classpath.” | Thư viện cung cấp API/hạ tầng, nhưng phải cấu hình manager và nơi áp dụng advice. | Kiểm tra bean/configuration và đường đi lời gọi. |
| “`@EnableTransactionManagement` tự cấu hình mọi database.” | Annotation này bật xử lý transaction annotation; manager/resource phù hợp vẫn cần được cung cấp hoặc auto-config. | Xem manager bean và `DataSource` được dùng. |
| “Trong Spring Boot phải luôn viết `@EnableTransactionManagement`.” | Boot có thể bật transaction management tự động khi điều kiện đúng. | Kiểm tra auto-configuration/runtime của phiên bản Boot. |
| “Bỏ `@EnableTransactionManagement` là chắc chắn tắt transaction.” | Boot có thể tự kích hoạt transaction management. | Kiểm tra runtime thay vì suy luận từ một annotation. |
| “Bean có proxy nghĩa là mọi method đều transactional.” | Proxy có thể áp dụng advice chọn lọc theo method/metadata. | Kiểm tra method được gọi và kết quả DB. |
| “`this.inner()` tự tạo `REQUIRES_NEW` nếu inner có annotation.” | Trong proxy mode, self-invocation không được advice intercept riêng. | Tách bean và gọi qua proxy nếu cần boundary riêng. |
| “Annotation có thể rollback email/HTTP call.” | Local DB transaction không điều khiển side effect ngoài DB. | Xác định tài nguyên được manager quản lý. |
| “Annotation có sẵn nhưng ném checked exception vẫn mặc định rollback.” | Quy tắc mặc định có thể không rollback checked exception, tùy phiên bản/cấu hình. | Dùng `rollbackFor` và test trạng thái DB. |
| “Method đánh dấu `readOnly=true` chắc chắn không thể ghi.” | Đây là hint/quy tắc tùy khả năng enforcement của driver/manager/ORM. | Kiểm tra tài nguyên và constraint thực. |

Lỗi nguy hiểm nhất trong thực tế không nhất thiết là ứng dụng crash. Có thể ứng dụng **vẫn chạy**, câu `INSERT` vẫn thành công, nhưng lỗi sau đó không rollback vì lời gọi bỏ qua proxy. Nếu chỉ test đường thành công, vấn đề khó lộ ra.

## 9. Thiết kế lại để annotation có đường chạy rõ ràng

Một cấu trúc hợp lý:

```java
@Service
public class CheckoutService {
    private final InventoryService inventory;

    public CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    public void placeOrder() {
        inventory.reserveStock(); // Qua bean được inject.
    }
}

@Service
public class InventoryService {
    @Transactional
    public void reserveStock() {
        // Ghi dữ liệu vào tài nguyên mà transaction manager quản lý.
    }
}
```

Đây là **mã kiến trúc minh họa**, thiếu phần repository và không phải chương trình chạy độc lập. Khi `CheckoutService` và `InventoryService` đều là Spring-managed beans và transaction infrastructure được kích hoạt, lời gọi `inventory.reserveStock()` có thể đi qua proxy của `InventoryService`. Nếu toàn bộ đặt hàng phải atomic, có thể cần **một transaction bao quanh use case ở `CheckoutService`** thay vì transaction nhỏ chỉ cho từng bước; ranh giới phải dựa vào nghiệp vụ và tài nguyên.

Nếu cần transaction độc lập, hãy làm rõ mục đích và propagation; không tự “vá” bằng cách thêm annotation lên mọi helper. Không truyền entity manager hoặc connection ngoài transaction rồi mặc định rằng nó tham gia scope.

### 9.1. Khi cần AspectJ thay proxy

Spring có thể dùng `@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` cùng dependency/weaving phù hợp để áp dụng transaction advice bằng bytecode weaving, nhờ đó self-invocation có thể được intercept. Đây là một cơ chế khác, không phải hành vi mặc định và đòi hỏi hạ tầng riêng (ví dụ `spring-aspects` và compile-time/load-time weaving). Không bật AspectJ chỉ để tránh việc thiết kế lại vài lời gọi nội bộ nếu nhu cầu giao dịch không đòi hỏi.

### 9.2. Khi dùng Spring Test

Một test method mang `@Transactional` trong Spring TestContext có thể được framework mở transaction và rollback sau test. Nó có thể khiến test pass dù cấu hình giao dịch của service ngoài production sai. Hãy bổ sung test gọi service qua bean ở một boundary thực tế, tạo lỗi giữa các bước ghi, kết thúc scope và đọc DB từ một transaction độc lập; đừng dựa vào rollback mặc định của test như bằng chứng service có proxy đúng.

## 10. Quy trình debug nhanh khi @Transactional “không hoạt động”

1. **Tái hiện có kiểm soát** với bản ghi duy nhất: insert, ném `RuntimeException`, quan sát DB sau lời gọi.
2. **Xác nhận instance:** in/log `AopUtils.isAopProxy(service)`, xác định đối tượng đang dùng có từ Spring context hay do `new`.
3. **Xem call graph:** có `this.method()`, private/final method, constructor/`@PostConstruct` hoặc lời gọi thread mới không?
4. **Kiểm tra configuration:** `@EnableTransactionManagement` hoặc Boot auto-config đã bật đúng context chưa; transaction manager bean nào sẵn có?
5. **Kiểm tra resource:** JDBC/JPA/repository dùng đúng manager và connection/entity manager cùng transaction không?
6. **Kiểm tra rule:** exception có thoát ra ngoài không, có bị catch rồi return, là checked hay unchecked, có `rollbackFor` hay `noRollbackFor` không?
7. **Kiểm tra propagation:** method tham gia transaction ngoài hay tạo transaction riêng, ai sở hữu commit cuối cùng?
8. **Quan sát kết quả:** transaction active là tín hiệu; readback DB sau commit/rollback mới kết luận tác dụng nghiệp vụ.

Có thể bật log `org.springframework.transaction.interceptor` ở mức TRACE và log của transaction manager khi điều tra; dùng log để xác định advice có chạy, đồng thời tránh ghi secrets/payload nhạy cảm. Với proxy mode, stack trace hoặc debug có thể thấy các lớp interceptor quanh method; chúng là dấu hiệu cơ chế hoạt động, không thay thế kiểm thử dữ liệu.

## 11. Tự kiểm tra

**Câu 1.** Vì sao gắn `@Transactional` lên method Java chưa đủ để mở transaction?  
**Trả lời:** Vì annotation chỉ lưu metadata. Cần hạ tầng như `TransactionAttributeSource`, transaction advisor/proxy, `TransactionInterceptor` và transaction manager phù hợp thực sự xử lý lời gọi.

**Câu 2.** `EventService.writeThenFail` có annotation; tại sao lời gọi từ `selfCall` không rollback trong ví dụ?  
**Trả lời:** Vì `this.writeThenFail` bỏ qua proxy; `selfCall` không mở transaction ngoài, nên JDBC ghi theo auto-commit và exception sau INSERT không đảo ngược được nó.

**Câu 3.** Nếu `selfCall` cũng được `@Transactional` và được bean khác gọi qua proxy, `writeThenFail` có cần tự được intercept để cùng rollback không?  
**Trả lời:** Không nhất thiết. Nó có thể chạy trong transaction **đã được lời gọi ngoài mở**; nhưng metadata riêng trên inner method không được áp dụng bởi self-invocation.

**Câu 4.** Tại sao `AopUtils.isAopProxy(service) == true` vẫn chưa chứng minh lời gọi `service.someMethod()` có transaction?  
**Trả lời:** Proxy có thể áp dụng advice cho tập method cụ thể. Method đang xét có thể không có transaction attribute, không nằm trong pointcut hoặc logic truy cập dữ liệu không tham gia đúng tài nguyên giao dịch.

**Câu 5.** Spring Boot có phải luôn yêu cầu người dùng thêm `@EnableTransactionManagement`?  
**Trả lời:** Không. Boot có auto-configuration khi điều kiện và dependencies phù hợp; cần xác nhận hạ tầng/runtime thực tế.

**Câu 6.** Khi lỗi rollback không hoạt động, chỉ thêm `rollbackFor = Exception.class` có chắc sửa được?  
**Trả lời:** Không. Nếu không có proxy/interceptor/manager phù hợp hoặc method bị self-invocation, metadata rollbackFor vẫn không được xử lý. Phải sửa nguyên nhân kích hoạt trước.

## Tài liệu đối chiếu

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot 3.3 — System requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html

**Ghi nhớ:** `@Transactional` diễn tả **transaction nên có ngữ nghĩa nào**; Spring runtime phải thực thi ngữ nghĩa ấy bằng hạ tầng đúng, trên lời gọi đúng và tài nguyên đúng. Ba việc “có annotation”, “có interceptor” và “dữ liệu được commit/rollback đúng” là ba điều khác nhau cần kiểm chứng độc lập.