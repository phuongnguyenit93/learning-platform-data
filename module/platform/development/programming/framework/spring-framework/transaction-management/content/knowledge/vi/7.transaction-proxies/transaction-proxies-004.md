# Proxy dựa trên giao diện và proxy dựa trên lớp trong Spring transaction management

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **JDK dynamic proxy** (proxy dựa trên interface) và **CGLIB proxy** (proxy dựa trên lớp) trong Spring AOP.
2. Giải thích cách Spring chọn loại proxy, đối tượng mà caller thực sự nhận được, và mối liên hệ với `@Transactional`.
3. Hiểu ảnh hưởng của loại proxy tới **kiểu dữ liệu được phép inject/cast**, phương thức có thể được gọi và phương thức có thể nhận transaction advice.
4. Nhận diện giới hạn của `final`, `private`, method không khai báo trong interface và **self-invocation**.
5. Chủ động chọn `proxyTargetClass` khi có lý do, đồng thời phân biệt mặc định của Spring Framework và cấu hình thường gặp của Spring Boot.
6. Chạy một ví dụ **Java 17+** so sánh JDK proxy với CGLIB proxy trên cùng một service, kiểm chứng begin/commit/rollback và điều kiện gọi qua proxy.

Bài tập trung vào **cơ chế proxy của Spring và hệ quả đối với quản lý transaction**. Hai cách tạo proxy không phải hai mức ACID khác nhau; chúng là hai kỹ thuật đưa interceptor quanh lời gọi phương thức.

## 1. Proxy đứng ở đâu trong giao dịch?

Giả sử bean có phương thức:

```java
@Transactional
public void transfer(long fromId, long toId, long amount) {
    // Trừ tài khoản nguồn rồi cộng tài khoản đích.
}
```

Chỉ gắn annotation không tự thêm lệnh `BEGIN` và `COMMIT` vào bytecode của phương thức. Trong chế độ Spring transaction **proxy mode**, caller sử dụng một đối tượng **proxy** do container cung cấp. Khi caller gọi qua proxy, Spring AOP đưa `TransactionInterceptor` vào quá trình gọi, đọc metadata `@Transactional`, chọn `PlatformTransactionManager` hoặc `ReactiveTransactionManager` phù hợp, rồi quản lý vòng đời transaction theo mô hình đang sử dụng.

```text
Controller / Service khác / ApplicationRunner
                   |
                   v
            Spring AOP proxy
                   |
            TransactionInterceptor
                   |
       TransactionManager (begin/join)
                   |
        Service thực hiện nghiệp vụ
                   |
       success -> commit (nếu là owner)
       error   -> rollback theo chính sách
                   |
                Caller
```

Với nghiệp vụ JDBC đồng bộ, interceptor thường điều phối `PlatformTransactionManager`. Với các publisher reactive, cơ chế transaction khác dùng `ReactiveTransactionManager` và subscriber context, nhưng khác biệt JDK/CGLIB vẫn liên quan đến việc **lời gọi nào đi qua proxy**.

Có hai hình thức proxy chính:

- **JDK dynamic proxy:** JVM tạo một đối tượng **triển khai interface** của service; nó chuyển các lời gọi interface tới cơ chế invocation handler của Spring AOP.
- **CGLIB proxy:** Spring tạo một **lớp con sinh động lúc chạy** của concrete target class; có thể override các phương thức đủ điều kiện để áp dụng interceptor.

Các loại proxy khác nhau ở cách biểu diễn object và khả năng bao method; khi transaction advice thực sự chạy với cùng policy, cả hai đều có thể cung cấp cùng một hành vi commit/rollback.

## 2. JDK dynamic proxy: dựa trên interface

Giả sử có hợp đồng:

```java
public interface PaymentService {
    void pay(long invoiceId);
}
```

và một implementation:

```java
public class PaymentServiceImpl implements PaymentService {
    @Override
    @Transactional
    public void pay(long invoiceId) {
        // Thao tác dữ liệu tham gia transaction.
    }

    public void recalculateInternalIndex() {
        // Method này không nằm trong PaymentService.
    }
}
```

Hai đoạn này minh họa cấu trúc, chưa phải ứng dụng độc lập. Trong chế độ interface-based proxy, runtime object mà Spring đưa cho caller có dạng khái niệm:

```text
                implements
JDK Proxy ------------------------> PaymentService
   |
   | InvocationHandler / advice chain
   v
PaymentServiceImpl (target thực tế)
```

Proxy **triển khai** `PaymentService`, nhưng **không mở rộng** `PaymentServiceImpl`. Vì thế:

```java
PaymentService service = context.getBean(PaymentService.class);
service.pay(10L); // Có thể được transaction interceptor xử lý.
```

Là cách dùng hợp lệ, còn điều này không được bảo đảm:

```java
PaymentServiceImpl concrete = (PaymentServiceImpl) service;
// Khi bean là JDK proxy: thường ClassCastException.
```

`recalculateInternalIndex()` không có trên interface nên không thể gọi qua biến `PaymentService` và không được phơi ra như một method của JDK proxy đó. Dù method implementation có `@Transactional`, nếu nó **không phải method callable trên interface của proxy**, caller không thể dùng chính proxy này để gọi vào method đó.

**Điểm dễ nhầm:** JDK proxy không đòi `@Transactional` phải được đặt **trên interface**. Với Spring Framework hiện đại, Spring có thể tìm annotation trên concrete implementation method khi thực hiện lời gọi từ proxy. Nên ưu tiên đặt transaction metadata trên **concrete class/method** để dễ bảo trì và phù hợp với nhiều cơ chế áp dụng advice khác nhau.

### Ưu điểm và giới hạn

- Phù hợp với thiết kế **program to interface**, dependency injection qua hợp đồng.
- Không cần tạo subclass của implementation, nên tránh các giới hạn subclassing như `final class` theo cơ chế proxy dựa trên interface, miễn lời gọi thuộc interface phù hợp.
- Chỉ phơi ra method của các interface mà proxy triển khai; việc inject/cast theo concrete class không còn đúng.
- Phương thức transactional dùng với interface-based proxy phải là **`public` và được khai báo trong proxied interface**.
- Interface proxy không phải một lớp con thực sự của target; không dựa vào tên class runtime để xác định business type.

## 3. CGLIB proxy: dựa trên concrete class

Khi dùng class-based proxy, Spring tạo subclass động của service:

```text
PaymentServiceImpl
        ^
        | extends
PaymentServiceImpl$$SpringCGLIB$$... (proxy)
        |
        v
Caller gọi method đủ điều kiện
        |
   AOP advice chain
        |
   target implementation
```

Object proxy **có thể gán cho concrete class**, ngoài các interface mà class triển khai:

```java
PaymentServiceImpl concrete =
    context.getBean(PaymentServiceImpl.class);

concrete.pay(10L);
concrete.recalculateInternalIndex();
```

Nếu method `recalculateInternalIndex` đủ điều kiện để Spring advice và có metadata phù hợp, nó cũng có thể được intercept dù không có mặt trong interface.

Tuy nhiên, vì proxy phải mở rộng concrete class và override method nên CGLIB có giới hạn quan trọng:

- **`final class` không thể được subclass** để làm class-based proxy.
- **`final method` không thể override**, vì vậy không thể áp dụng Spring AOP advice bằng override cho method đó.
- **`private method` không thể override**, nên không thể được proxy-intercept theo mô hình này.
- Method không hiển thị cho subclass, ví dụ package-private method được kế thừa qua khác package nhưng không accessible, cũng không thể advice.
- Những ràng buộc đặc biệt của Java Platform Module System hoặc việc không thể mở package có thể gây khó cho việc sinh subclass/proxy.

Trong Spring Framework **6.0 trở lên**, `@Transactional` trên `protected` hoặc package-visible method có thể được xử lý **mặc định với class-based proxy** nếu method đủ điều kiện. Đây là khác biệt với việc chỉ hiểu mọi transactional method đều phải public ở các phiên bản cũ. Dù vậy, dùng `public` service method là khuyến nghị thực hành dễ dự đoán nhất; các proxy dựa trên interface vẫn chỉ hỗ trợ public method được khai báo trên interface.

### CGLIB không đồng nghĩa “mọi lời gọi đều được intercept”

Một proxy CGLIB không sửa chính mã nguồn của target. Nó chỉ intercept các lời gọi **đi vào object proxy**, và chỉ với các method có thể được override/advised. Nếu logic bên trong target trực tiếp gọi `this.otherMethod()` thì lời gọi đó thường đi thẳng đến implementation, không qua interceptor bên ngoài. Đây là vấn đề self-invocation chung của cả JDK lẫn CGLIB.

## 4. So sánh có hệ thống

| Tiêu chí | JDK dynamic proxy | CGLIB proxy |
| --- | --- | --- |
| Cách tạo | Object JVM triển khai một/nhiều interface | Subclass sinh lúc chạy của concrete class |
| Điều kiện cơ bản | Target có interface phù hợp | Class có thể được subclass |
| Runtime type | Gán được cho interface | Gán được cho concrete class và interface |
| Injection khuyến nghị | Injection bằng interface | Có thể injection bằng class hoặc interface |
| Method chỉ có trong implementation | Không phơi ra qua JDK proxy | Có thể gọi/advice nếu đủ điều kiện |
| `final class` | Có thể proxy qua interface | Không thể subclass class `final` |
| `final method` trên target | Interface call có thể được advice vì không cần override target | Không thể override/advice method final |
| `private method` | Không phải method công khai của interface | Không thể override/advice |
| `protected`/package-visible transaction method (Spring 6+) | Không thể gọi như interface public method | Có thể advice khi đủ điều kiện và metadata |
| Self-invocation `this.method()` | Bỏ qua advice của method được gọi | Cũng bỏ qua advice của method được gọi |
| Mức isolation/rollback | Theo transaction metadata/manager | Theo cùng transaction metadata/manager |
| `@Transactional` bắt buộc? | Không phải mọi proxy đều là transaction proxy | Tương tự; có thể dùng cho các advice AOP khác |

**Ý quan trọng nhất:** khác biệt nằm ở **giao diện object và phương thức có thể intercept**, không nằm ở việc JDK proxy có transaction “yếu hơn” CGLIB. Cùng một service, cùng một DB, cùng `@Transactional` và cùng transaction manager có thể cho kết quả giao dịch giống hệt nhau.

## 5. Spring chọn loại proxy như thế nào?

### 5.1. Mặc định của Spring Framework AOP

Trong mô hình proxy-based thông dụng của Spring Framework:

1. Nếu target triển khai một hoặc nhiều interface và không có cấu hình bắt buộc dùng class proxy, framework thường chọn **JDK dynamic proxy**.
2. Nếu target không có interface để proxy, framework phải dùng **class-based proxy** (nếu target đủ điều kiện).
3. Khi đặt `proxyTargetClass = true`, Spring yêu cầu **class-based proxy** ngay cả khi target có interface.

Ví dụ cấu hình Java cho transaction management:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = false)
public class JdkFriendlyConfiguration {
}
```

và:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class ClassProxyConfiguration {
}
```

Đây là **hai phương án cấu hình thay thế nhau**, không đặt cả hai vào cùng một ApplicationContext. `proxyTargetClass = false` nghĩa là cho phép chọn JDK nếu có interface, **không ép JDK cho class không có interface**.

Một chú ý thực tế: Spring có thể hợp nhất thiết lập từ nhiều cơ chế tạo AOP proxy trong cùng context. Chỉ một cấu hình khác bật `proxyTargetClass = true` cũng có thể khiến các proxy liên quan dùng CGLIB. Vì thế, khi thấy runtime proxy không đúng dự kiến, hãy kiểm tra **cấu hình AOP/transaction của toàn context**, đừng chỉ nhìn một annotation.

### 5.2. Spring Boot thường có mặc định khác

Spring Boot AOP auto-configuration thông thường ưu tiên **CGLIB class-based proxy**. Khi cần chuyển sang JDK interface proxy, có thể cấu hình:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Đặt `true` để ưu tiên class-based proxy. Tuy nhiên, nếu có các cấu hình proxy khác ép class-based, một property riêng lẻ không nhất thiết thắng tất cả. Hãy quan sát proxy runtime hoặc viết test thay vì suy đoán từ file cấu hình.

Ví dụ chạy ở phần sau sử dụng **plain Spring Framework**, không dùng Spring Boot auto-configuration, để quan sát được trực tiếp ảnh hưởng của `@EnableTransactionManagement(proxyTargetClass = ...)` mà không bị một default từ Boot can thiệp.

### 5.3. Khi nào thật sự cần đổi loại proxy?

Chọn **JDK proxy** khi API được thiết kế tốt qua interface, caller không cần inject implementation class và các method transactional đều được công khai trong interface.

Chọn **CGLIB proxy** khi không có interface, cần inject concrete class, hoặc cần advice một public method hợp lệ nhưng không nằm trên interface. Hãy bảo đảm target class không final và method cần advice có thể override.

Không đổi toàn application sang CGLIB chỉ để che một lỗi self-invocation; chuyển loại proxy **không sửa được** nguyên nhân đó.

## 6. Ví dụ Java 17+ chạy được: cùng một transaction service, hai loại proxy

Ví dụ dưới đây tạo **hai Spring ApplicationContext riêng biệt**. Context thứ nhất cho phép JDK interface proxy, context thứ hai yêu cầu CGLIB class proxy. Cả hai dùng cùng một service implementation, `JdbcTemplate`, H2 và `DataSourceTransactionManager`, chỉ khác `proxyTargetClass`.

Ta dùng một file Java với các lớp lồng `static`, vì vậy có thể sao chép chính xác rồi chạy. Ở thời điểm kiểm tra, Spring Framework 6.1.x tương thích Java 17+; dùng một bản 6.1 cụ thể để ví dụ có dependency xác định.

### 6.1. Cấu trúc thư mục

```text
tx-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── txproxy/
                    └── ProxyTransactionsDemo.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'tx-proxy-demo'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.14')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.springframework:spring-jdbc'
    implementation 'org.springframework:spring-tx'

    runtimeOnly 'com.h2database:h2:2.2.224'
}

application {
    mainClass = 'example.txproxy.ProxyTransactionsDemo'
}
```

Giải thích dependencies: `spring-context` khởi tạo bean và cấu hình; `spring-aop` xây dựng proxy/advice; `spring-tx` cung cấp transaction annotations/interceptor; `spring-jdbc` hỗ trợ `JdbcTemplate` và `DataSourceTransactionManager`; H2 là database in-memory. Các dependency Spring cùng BOM tránh lệch phiên bản.

### 6.4. `src/main/java/example/txproxy/ProxyTransactionsDemo.java`

```java
package example.txproxy;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class ProxyTransactionsDemo {

    public interface TransferOperations {
        void transfer(long from, long to, long amount);
        boolean transactionActive();
        boolean callInternally();
    }

    public static class TransferService implements TransferOperations {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        @Transactional
        public void transfer(long from, long to, long amount) {
            if (amount <= 0 || from == to) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            int debited = jdbc.update(
                "UPDATE wallets SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, from, amount
            );
            if (debited != 1) {
                throw new IllegalStateException(
                    "Source missing or insufficient funds"
                );
            }

            int credited = jdbc.update(
                "UPDATE wallets SET balance = balance + ? WHERE id = ?",
                amount, to
            );
            if (credited != 1) {
                throw new IllegalStateException("Destination missing");
            }
        }

        @Override
        @Transactional(readOnly = true)
        public boolean transactionActive() {
            return TransactionSynchronizationManager
                .isActualTransactionActive();
        }

        @Override
        public boolean callInternally() {
            return this.transactionActive();
        }

        @Transactional(readOnly = true)
        public boolean classOnlyTransactional() {
            return TransactionSynchronizationManager
                .isActualTransactionActive();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Infrastructure {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_proxy_demo;DB_CLOSE_DELAY=-1");
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
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbc) {
            return new TransferService(jdbc);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = false)
    @Import(Infrastructure.class)
    public static class JdkMode {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    @Import(Infrastructure.class)
    public static class CglibMode {
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void demonstrate(Class<?> configuration) {
        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext(configuration)) {

            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("DROP TABLE IF EXISTS wallets");
            jdbc.execute(
                "CREATE TABLE wallets (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL CHECK (balance >= 0))"
            );
            jdbc.update(
                "INSERT INTO wallets (id, balance) VALUES (?, ?)",
                1L, 1000L
            );
            jdbc.update(
                "INSERT INTO wallets (id, balance) VALUES (?, ?)",
                2L, 500L
            );

            Object bean = ctx.getBean("transferService");
            TransferOperations service = (TransferOperations) bean;

            String proxyType = AopUtils.isJdkDynamicProxy(bean) ? "JDK"
                : AopUtils.isCglibProxy(bean) ? "CGLIB" : "NONE";

            System.out.println("Proxy=" + proxyType);
            System.out.println(
                "Assignable to TransferService=" +
                (bean instanceof TransferService)
            );
            System.out.println(
                "External transaction=" + service.transactionActive()
            );
            System.out.println(
                "Self-invocation transaction=" + service.callInternally()
            );

            if (bean instanceof TransferService concrete) {
                System.out.println(
                    "Class-only method transaction=" +
                    concrete.classOnlyTransactional()
                );
            } else {
                System.out.println(
                    "Class-only method transaction=not exposed"
                );
            }

            service.transfer(1L, 2L, 200L);
            System.out.println("After commit=" + balances(jdbc));

            try {
                service.transfer(1L, 999L, 50L);
            } catch (IllegalStateException expected) {
                System.out.println(
                    "Expected error=" + expected.getMessage()
                );
            }
            System.out.println("After rollback=" + balances(jdbc));
        }
    }

    public static void main(String[] args) {
        demonstrate(JdkMode.class);
        demonstrate(CglibMode.class);
    }
}
```

### 6.5. Cách chạy

Dùng Gradle wrapper của project bạn đã khởi tạo, hoặc Gradle đã cài với JDK/toolchain tương thích:

```bash
./gradlew run
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run
```

Nếu bạn tự dựng project mới và chưa có wrapper, có thể dùng `gradle run` sau khi đã cài Gradle, hoặc tạo wrapper trước. Lệnh này thực thi `application.mainClass` ở trên; **không dùng `javac`/`java` trực tiếp khi chưa có Spring và H2 trên classpath**.

Phần stdout có ý nghĩa của chương trình, bỏ qua log Spring/Gradle, dự kiến là:

```text
Proxy=JDK
Assignable to TransferService=false
External transaction=true
Self-invocation transaction=false
Class-only method transaction=not exposed
After commit=1=800, 2=700
Expected error=Destination missing
After rollback=1=800, 2=700
Proxy=CGLIB
Assignable to TransferService=true
External transaction=true
Self-invocation transaction=false
Class-only method transaction=true
After commit=1=800, 2=700
Expected error=Destination missing
After rollback=1=800, 2=700
```

### 6.6. Giải thích kết quả theo từng dòng

**`Proxy=JDK` rồi `Proxy=CGLIB`:** Trong mỗi context, `AopUtils` nhận ra runtime proxy tương ứng. Không dựa vào chuỗi tên class nội bộ như `$Proxy42` hoặc `$$SpringCGLIB$$0`; các tên sinh tự động có thể thay đổi.

**`Assignable to TransferService`:** JDK proxy chỉ triển khai `TransferOperations`, nên `instanceof TransferService` là false. CGLIB proxy là subclass, nên gán được cho `TransferService`. Cả hai có thể ép kiểu `TransferOperations`.

**`External transaction=true`:** `service.transactionActive()` được gọi từ caller qua proxy, interceptor mở transaction read-only và `TransactionSynchronizationManager.isActualTransactionActive()` nhìn thấy một transaction đang active. Read-only ở đây là hint, không phải lời khẳng định rằng DB không thể ghi.

**`Self-invocation transaction=false`:** `service.callInternally()` đi qua proxy nhưng method này **không có `@Transactional`**; nó gọi `this.transactionActive()` bên trong target. Lời gọi trực tiếp không đi lại qua proxy, nên annotation của `transactionActive()` không được interceptor xử lý. Vì không có transaction bên ngoài trong demo, kết quả false ở cả hai chế độ.

**`Class-only method transaction`:** `classOnlyTransactional()` có `@Transactional` nhưng **không được khai báo trong interface**. JDK proxy không phơi method này. CGLIB proxy là subclass và method public không final nên có thể gọi qua concrete type; interceptor mở transaction, trả true.

**`After commit`:** Trừ 200 ở ví 1 và cộng 200 ở ví 2 trong **một transaction**; vì cả hai câu SQL thành công, transaction commit, số dư là 800 và 700.

**`Expected error` rồi `After rollback`:** Thao tác chuyển đến ví 999 phát sinh `IllegalStateException` sau khi đã tạm trừ 50 ở ví nguồn. Mặc định Spring rollback khi unchecked exception thoát qua transactional interceptor; số dư sau rollback giữ nguyên 800 và 700. Điều này đúng trong cả hai chế độ proxy.

**Vì sao khởi tạo lại bảng hai lần?** `demonstrate(...)` thực thi với hai `ApplicationContext` riêng biệt để minh họa từng proxy mode, và mỗi lần `DROP`/`CREATE` bảng rồi insert dữ liệu ban đầu. H2 in-memory được giữ tồn tại trong tiến trình bằng `DB_CLOSE_DELAY=-1`, nên reset fixture bảo đảm stdout ở hai lượt so sánh chính xác.

### 6.7. Bốn chi tiết kỹ thuật giúp demo thực sự có ý nghĩa

1. **`@Transactional` nằm trên implementation method** để Spring transaction metadata source có thể tìm thấy với cả hai loại proxy.
2. **Caller lấy bean bằng tên rồi ép về interface**, do nếu cố lấy `TransferService.class` trong JDK mode sẽ không phù hợp runtime type của bean.
3. **Hai context cấu hình loại proxy khác nhau** qua `@EnableTransactionManagement`, tránh việc nhiều auto-proxy configuration ép cùng một global setting.
4. **Có JDBC transaction manager và kiểm tra DB thật**, nên kết quả commit/rollback là một hành vi giao dịch, không chỉ là `instanceof` trên object.

## 7. Tại sao `this.method()` bỏ qua transaction ở cả hai proxy?

Giả sử service như sau:

```java
@Service
public class BillingService {

    public void invoiceAndCharge() {
        charge(); // Lời gọi nội bộ qua this, không qua proxy.
    }

    @Transactional
    public void charge() {
        // Những câu SQL cần giao dịch.
    }
}
```

Đoạn code minh họa chỉ ra một lỗi thiết kế, không phải một chương trình chạy độc lập. Nếu caller bên ngoài gọi `invoiceAndCharge()` qua proxy và method ngoài **không transactional**, target bên trong gọi trực tiếp `charge()` thì `@Transactional` ở `charge()` không tự bật transaction. CGLIB cũng không chữa được điều đó, vì advice của method được gọi không được kích hoạt bởi self-invocation.

Có ba phương án tùy kiến trúc:

- **Đặt `@Transactional` trên entrypoint phù hợp:** nếu toàn bộ `invoiceAndCharge()` phải là một đơn vị nguyên tử thì đặt annotation tại đó.
- **Tách sang một Spring bean khác:** `InvoiceService` gọi `ChargeService.charge()` qua bean được inject; lời gọi tới `ChargeService` đi qua proxy riêng.
- **Dùng `TransactionTemplate` khi cần biên transaction ngay trong cùng class:** gọi một callback có transaction explicit, thay vì kỳ vọng self-invocation được proxy chặn.

Không khuyến khích tự gọi `((BillingService) AopContext.currentProxy()).charge()` như giải pháp mặc định. Cách đó gắn logic nghiệp vụ chặt vào AOP framework, cần bật exposeProxy và sẽ còn rắc rối nếu proxy runtime dựa trên interface.

### Khi đã có transaction bên ngoài thì sao?

Nếu `invoiceAndCharge()` **đã** mở transaction, `this.charge()` vẫn có thể thực hiện SQL bên trong transaction **đang tồn tại**, vì JDBC connection được Spring ràng buộc theo thread. Nhưng metadata riêng của `charge()` (như `REQUIRES_NEW`, isolation, rollback rule) **không được đánh giá ở lời gọi nội bộ**. Do đó kết luận đúng là “self-invocation không kích hoạt advice của method được gọi”, không phải “mọi self-invocation đều chạy ngoài mọi transaction”.

## 8. `final`, `private` và method visibility: giới hạn theo loại proxy

Ví dụ Java:

```java
public final class FinalPaymentService {
    @Transactional
    public void pay() {
        // ...
    }
}
```

CGLIB không thể tạo subclass của `FinalPaymentService` vì lớp `final`. Một JDK proxy vẫn có thể triển khai **interface** mà một final class hiện thực; điều đó không đòi subclass final class. Nhưng nếu class không có interface phù hợp, JDK proxy không giải quyết được.

Một method `final`:

```java
public class PaymentService {
    @Transactional
    public final void pay() {
        // ...
    }
}
```

CGLIB không thể override `pay()` nên không thể áp dụng interceptor theo cách đó. Nếu `pay()` là public method của interface được proxy bằng JDK, lời gọi qua interface có thể được advice vì JDK proxy intercept **ở object interface proxy**, không bằng override method `final` trên target.

Một `private` method:

```java
public class PaymentService {
    @Transactional
    private void persist() {
        // ...
    }
}
```

Cả JDK interface proxy lẫn CGLIB class proxy đều không thể intercept direct call vào `private persist()` theo mô hình Spring AOP proxy. Đừng cố cứu transaction chỉ bằng đổi `proxyTargetClass=true`. Đặt transactional boundary ở một method có thể được gọi từ bên ngoài qua proxy.

**Lưu ý phiên bản:** Spring Framework 6+ cho phép xử lý một số `protected`/package-visible transaction methods với class-based proxy, còn JDK interface proxy giới hạn public method khai báo ở interface. Nếu muốn quy tắc “chỉ public” nhất quán với cả hai dạng, Spring có API `AnnotationTransactionAttributeSource(true)` để cấu hình `publicMethodsOnly`. Tránh dựa vào method non-public khi code cần chuyển đổi linh hoạt loại proxy.

## 9. Annotation đặt trên interface hay implementation?

Có thể gắn `@Transactional` trên interface method:

```java
public interface LedgerOperations {
    @Transactional
    void settle(long ledgerId);
}
```

Spring Framework hiện đại có thể nhận ra transaction metadata từ interface trong các cấu hình proxy tương ứng. Tuy nhiên, trong Java, annotation của interface **không được thừa kế theo cơ chế `@Inherited` dành cho class**, và khi đổi sang AspectJ weaving có thể phát sinh khác biệt về nhận diện metadata.

Vì thế, tài liệu Spring khuyến nghị ưu tiên gắn `@Transactional` lên **concrete implementation class/method**:

```java
public interface LedgerOperations {
    void settle(long ledgerId);
}

@Service
public class LedgerService implements LedgerOperations {

    @Override
    @Transactional
    public void settle(long ledgerId) {
        // ...
    }
}
```

Đây là ví dụ minh họa riêng. `@Transactional` trên implementation method không ngăn JDK proxy làm việc: khi invocation bắt nguồn từ interface method, Spring transaction attribute resolution vẫn có thể tìm metadata trên **target method cụ thể**.

Khi thấy một refactor từ interface proxy sang class proxy làm thay đổi behavior, cần kiểm tra cả việc đặt annotation, method visibility, có `final` hay không, chính sách AOP và test rollback. Không nên kết luận ngay rằng annotation trên interface “chỉ luôn hoạt động với JDK proxy”; hành vi cụ thể phụ thuộc phiên bản/cơ chế, đặc biệt nếu so với AspectJ weaving.

## 10. Injection, cast, reflection và kiểm tra runtime proxy

Với code phụ thuộc interface:

```java
@Service
public class CheckoutController {
    private final PaymentService service;

    public CheckoutController(PaymentService service) {
        this.service = service;
    }
}
```

Ý tưởng trên hỗ trợ cả JDK proxy và CGLIB proxy, miễn Spring có một bean phù hợp.

Ngược lại, nếu thành phần khác yêu cầu concrete implementation:

```java
@Service
public class CheckoutController {
    private final PaymentServiceImpl service;

    public CheckoutController(PaymentServiceImpl service) {
        this.service = service;
    }
}
```

Trong JDK proxy mode, bean đại diện có thể không gán được cho `PaymentServiceImpl`. Tùy đường lookup và context, bạn có thể gặp lỗi không tìm thấy bean theo type hoặc lỗi bean runtime không đúng type. Giải pháp đầu tiên là **inject interface** mà thành phần thật sự cần. Chỉ chuyển sang CGLIB nếu yêu cầu phụ thuộc concrete class là chủ đích.

### Kiểm tra bằng Spring API

```java
Object bean = applicationContext.getBean("transferService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đây là snippet đặt trong application đã có `ApplicationContext`; cần import `org.springframework.aop.support.AopUtils`. `isAopProxy` trả true khi là Spring AOP proxy; hai phương thức còn lại giúp phân loại JDK/CGLIB. **Có proxy chưa chứng minh transaction hoạt động**: phải quan sát lời gọi thực, transaction context và DB commit/rollback.

Có thể quan sát thêm:
- `bean instanceof PaymentService` và `bean instanceof PaymentServiceImpl`;
- log `org.springframework.transaction` mức DEBUG/TRACE khi cần điều tra begin/commit/rollback;
- thông tin bean definitions và transaction manager được chọn;
- transaction active ở bên trong method thông qua `TransactionSynchronizationManager.isActualTransactionActive()` với JDBC.

Khi kiểm tra trong test, tránh assert tên runtime class cụ thể vì suffix sinh động có thể thay đổi. Ưu tiên `AopUtils` và kết quả giao dịch.

## 11. Tránh nhầm giữa Spring AOP proxy và AspectJ weaving

Cùng một annotation `@Transactional`, Spring có thể vận hành theo hai chế độ lớn:

| Chế độ | Cơ chế | Hệ quả |
| --- | --- | --- |
| `mode = AdviceMode.PROXY` | Spring AOP proxy, dùng JDK hoặc CGLIB | Chỉ method call đi qua proxy mới được transactional advice |
| `mode = AdviceMode.ASPECTJ` | Compile-time/load-time weaving với AspectJ | Bytecode target được weave, có thể áp dụng advice cả lời gọi nội bộ theo thiết lập thích hợp |

Đối với câu hỏi “JDK proxy hay CGLIB proxy”, ta đang ở nhánh **PROXY**. `proxyTargetClass` không phải công tắc bật AspectJ weaving. Nếu thật sự cần intercept self-invocation mà không thay kiến trúc service, AspectJ là một hướng kỹ thuật riêng, có phụ thuộc `spring-aspects` và cấu hình weaving; không thể thay thế chỉ bằng `proxyTargetClass=true`.

Trong đa số service CRUD/transaction thông thường, ranh giới nghiệp vụ rõ ràng qua public method trên Spring bean và khả năng test là đủ. Việc chuyển cả hệ thống sang weaving nên có lý do kiến trúc và kiểm thử riêng.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `@Autowired MyServiceImpl` lỗi khi JDK proxy | Bean proxy triển khai interface nhưng không kế thừa implementation | Inject `MyService` interface hoặc chọn class proxy có chủ đích |
| Một method chỉ trong implementation không gọi được | JDK proxy không phơi method ngoài proxied interface | Đưa method vào interface nếu là API, hoặc dùng class proxy |
| Đặt `proxyTargetClass=false` nhưng vẫn thấy CGLIB | Target không có interface hoặc cấu hình AOP khác ép class proxy | Xem toàn bộ proxy creator settings và runtime `AopUtils` |
| Class `final` không tạo được CGLIB proxy | Không thể subclass target | Bỏ `final` nếu phù hợp, hoặc dùng interface proxy |
| `@Transactional` trên final method không có hiệu lực với CGLIB | Không thể override method | Bỏ `final` trên advised method hoặc chuyển ranh giới |
| `@Transactional` trên private method không hoạt động | Private không intercept được qua proxy | Đặt transaction ở public service entrypoint |
| Gọi method transaction qua `this` không có begin mới | Self-invocation bỏ qua advice | Tách bean, đặt annotation lên entrypoint, hoặc dùng template |
| JDBC update đã chạy rồi lỗi nhưng không rollback | Transaction interceptor không chạy; hai lệnh auto-commit | Kiểm tra proxy, manager, lời gọi và test rollback |
| Có proxy nhưng kết quả DB không như mong muốn | Lỗi nghiệp vụ, SQL/constraint/rollback rule khác proxy type | Kiểm tra transaction metadata, exception và DB thực |
| Chọn `CGLIB` vì “an toàn hơn” | Proxy type không thay thế transaction logic | Chọn theo hợp đồng API và method visibility |
| Chỉ quan sát `getClass().getName()` | Tên runtime generated không phải API ổn định | Dùng `AopUtils`, `instanceof` và kiểm thử hành vi |

## 13. Câu hỏi tự kiểm tra

1. Service có interface và `@EnableTransactionManagement(proxyTargetClass=false)`, thường Spring tạo gì? **JDK dynamic proxy** nếu không có cấu hình proxy khác ép CGLIB.
2. Một implementation không có interface nhưng đặt `proxyTargetClass=false` sẽ ra sao? **Spring vẫn có thể dùng class-based proxy**, nếu class đủ điều kiện.
3. `PaymentServiceImpl` có method `rebuild()` không thuộc `PaymentService`. Caller đang giữ JDK proxy kiểu `PaymentService` có gọi được `rebuild()` không? **Không qua interface proxy đó**.
4. Vì sao injection theo concrete class có thể lỗi với JDK proxy? **JDK proxy không extends implementation class**.
5. CGLIB có thể intercept `final method` không? **Không**, vì không thể override.
6. Đổi từ JDK sang CGLIB có làm `this.method()` tự đi qua proxy không? **Không**.
7. `@Transactional` đặt trên implementation method có hoạt động khi Spring dùng JDK proxy không? **Có**, với method public được khai báo ở interface và transaction infrastructure được bật.
8. Tại sao `@Transactional` không bảo đảm đủ ACID chỉ bằng việc có proxy? **Proxy chỉ đưa transaction advice vào lời gọi; DB, transaction manager, tài nguyên tham gia, isolation, rollback rules và invariant mới quyết định hành vi dữ liệu**.
9. `AopUtils.isCglibProxy(bean) == true` có chứng minh commit/rollback đúng không? **Không**. Cần kiểm thử DB.
10. Spring Boot thường chọn loại proxy nào trong AOP auto-config? **CGLIB**, trừ khi cấu hình hoặc cơ chế AOP khác thay đổi.

## 14. Checklist chọn proxy cho transaction service

1. Xác định các public business method là API thật sự của service; có thể khai báo hợp đồng bằng interface không?
2. Kiểm tra caller đang inject interface hay concrete implementation; tránh phụ thuộc ngẫu nhiên vào kiểu proxy.
3. Xác nhận `@Transactional` được đặt trên concrete class/method đủ điều kiện, transaction management đang bật và manager được chọn đúng.
4. Với JDK proxy, bảo đảm method cần advice **public và nằm trong interface được proxy**.
5. Với CGLIB, kiểm tra class/method `final`, `private`, package visibility và Java Module System constraints.
6. Rà soát self-invocation, gọi qua `new`, `@PostConstruct` và các tác vụ không đi qua bean proxy.
7. Xem toàn bộ `@EnableTransactionManagement`, `@EnableAspectJAutoProxy`, các cấu hình AOP liên quan và `spring.aop.proxy-target-class` của Boot.
8. Kiểm tra loại proxy thật bằng `AopUtils`; sau đó kiểm tra transaction active trong method và commit/rollback trên DB.
9. Giữ ranh giới transaction ngắn và đúng nghiệp vụ; dùng DB constraint/conditional SQL để bảo vệ tính nhất quán, không lệ thuộc vào proxy type.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — Understanding AOP Proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html#proxying-introduction-understanding-aop-proxies
- Spring Framework 6.2 — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html