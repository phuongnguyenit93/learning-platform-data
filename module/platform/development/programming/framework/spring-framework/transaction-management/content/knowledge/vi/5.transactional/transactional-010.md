# Phạm vi phát hiện `@Transactional` trong `ApplicationContext`

## 1. Mục tiêu của bài học

Một phương thức có `@Transactional` vẫn có thể chạy **không có transaction** dù ứng dụng đã khai báo `@EnableTransactionManagement`. Nguyên nhân đôi khi không nằm ở annotation, transaction manager hay JDBC, mà ở **`ApplicationContext` nào sở hữu bean và `ApplicationContext` nào bật xử lý annotation**.

Sau bài này, bạn có thể:

- Phân biệt `@Transactional` (metadata trên phương thức/lớp) với `@EnableTransactionManagement` (kích hoạt hạ tầng xử lý metadata).
- Giải thích quy tắc **cùng `ApplicationContext`**: transaction advisor/proxy được áp dụng cho các bean do context tương ứng quản lý, không tự lan xuống hoặc leo lên mọi context trong hệ phân cấp.
- Chỉ ra lỗi thường gặp ở Spring MVC truyền thống có **root `WebApplicationContext`** và **child `WebApplicationContext` của `DispatcherServlet`**.
- Tạo hai context cha–con để kiểm tra sự khác biệt giữa «bean nhìn thấy được» và «bean đã được tạo transaction proxy».
- Xác thực bằng ba bằng chứng: vị trí bean, `AopUtils.isAopProxy(...)`, và trạng thái cơ sở dữ liệu sau một exception.
- Sửa lỗi bằng cách đặt cấu hình transaction ở đúng context chứa service hoặc đăng ký bean cần bảo vệ ở context đã kích hoạt transaction advice.

**Ý chính:** `@EnableTransactionManagement` và cấu hình XML `<tx:annotation-driven/>` trong chế độ proxy thông thường chỉ xử lý `@Transactional` trên **các bean thuộc cùng `ApplicationContext`**. Nếu kích hoạt chúng trong context con của `DispatcherServlet` nhưng các service nằm ở context cha, annotation trên service cha sẽ không tự được context con xử lý.

## 2. «Phát hiện annotation» thực chất là gì?

Xét phương thức:

```java
@Transactional
public void placeOrder() {
    debitInventory();
    saveOrder();
}
```

Đây là **mã minh họa**, chưa định nghĩa `debitInventory()` và `saveOrder()`. `@Transactional` cho biết một phương thức cần transaction semantics; tự nó **không mở transaction** chỉ vì JVM đọc thấy annotation.

Trong **proxy mode** mặc định của Spring, quá trình diễn ra như sau:

1. `@EnableTransactionManagement` trên một class `@Configuration` nhập các bean hạ tầng quản lý giao dịch vào **ApplicationContext chứa cấu hình đó**. Bản XML `<tx:annotation-driven/>` có vai trò tương tự.
2. Hạ tầng đăng ký advisor/interceptor cùng auto-proxy mechanism. Khi context tạo và hoàn thiện các Spring bean của nó, bean phù hợp với metadata `@Transactional` có thể được trả về dưới dạng **AOP proxy**.
3. Caller phải gọi qua proxy. Transaction interceptor quyết định transaction manager và áp dụng begin/join, commit/rollback quanh lời gọi.
4. Gọi qua target object trực tiếp, hoặc gọi method nội bộ bằng `this.`, có thể bỏ qua interceptor trong proxy mode.

Sơ đồ:

```text
Bean definition ở Context A
    |
    v
Context A tạo bean
    |
    +-- Context A đã bật transaction annotation advice?
    |       |
    |       +-- Có, method đủ điều kiện -> tạo transaction-aware proxy
    |       |
    |       +-- Không -> bean trả về không có transaction proxy từ cơ chế này
    |
    v
Caller gọi object đã được Context A tạo
    |
    +-- Qua proxy -> có thể mở/join transaction
    +-- Qua target trực tiếp -> không có interception của proxy đó
```

**Không nhầm với component scanning:** `@ComponentScan` tìm class để đăng ký bean definition. `@EnableTransactionManagement` kích hoạt việc áp dụng transaction advice cho các bean trong context. Việc một package được scan, một annotation tồn tại trong bytecode, hay một child context nhìn thấy một bean cha **không đồng nghĩa** transaction proxy đã được tạo cho bean đó.

Cũng không nên hiểu «cùng context» là cùng **package Java**, cùng source module, hay cùng thư mục cấu hình. Hai class ở package khác nhau nhưng được cùng một context đăng ký có thể được áp dụng chung transaction advice. Ngược lại, hai context khác nhau cùng quét một package vẫn là hai miền bean lifecycle khác nhau.

## 3. Quy tắc sở hữu bean trong context cha–con

`ApplicationContext` có thể hình thành **hierarchy**: context con có khả năng tìm bean trong context cha khi không có bean tương ứng ở local scope. Hướng nhìn thấy thông thường là **con → cha**, chứ cha không tự nhìn thấy bean chỉ được khai báo trong con.

```text
Root ApplicationContext
  ├─ accountService         [@Transactional]
  ├─ accountRepository
  ├─ dataSource
  └─ transactionManager
           ^
           | Child có thể lookup/inject bean ở parent
           |
Child ApplicationContext
  ├─ webController
  └─ @EnableTransactionManagement
```

Nếu `@EnableTransactionManagement` **chỉ có trong Child**:

- `child.getBean("accountService")` có thể trả về bean do **Root** đã tạo; khả năng truy xuất này là **bean visibility**.
- Hạ tầng proxy của **Child** chỉ xử lý các bean được **Child** quản lý khi chúng được khởi tạo; nó **không quay lại thay thế bean đã do Root tạo**.
- Vì vậy `accountService` ở Root có thể vẫn là object không được transaction proxy bảo vệ, dù Child có đủ cấu hình và nhìn thấy bean ấy.
- `child.containsBean("accountService")` có thể trả `true`, trong khi `child.containsLocalBean("accountService")` trả `false`. Hai hàm trả lời **hai câu hỏi khác nhau**.

### 3.1. Ba cấu hình cần phân biệt

| Service `@Transactional` nằm ở | `@EnableTransactionManagement` nằm ở | Kết quả trong proxy mode thông thường |
| --- | --- | --- |
| Root | Root | Service ở Root được xét tạo transaction proxy. |
| Root | Chỉ Child | Service ở Root **không** được Child tự động tạo proxy. |
| Child | Child | Service ở Child được xét tạo proxy. |
| Root và Child đều có service riêng | Chỉ Root | Chỉ các bean của Root được hạ tầng Root xử lý; bean chỉ ở Child không tự được Root xử lý. |
| Root và Child đều có service riêng | Cả hai | Mỗi context có hạ tầng riêng xử lý bean **thuộc chính nó**. |

Bảng diễn tả phạm vi xử lý mặc định; **không bảo đảm** mọi lời gọi sẽ có transaction vì còn phụ thuộc proxy visibility, cách gọi, transaction manager, rollback policy, và resource participation.

### 3.2. Không nhầm bean kế thừa với proxy kế thừa

Nếu Root **đã tạo proxy** cho `accountService`, Child lookup bean đó sẽ nhận **chính proxy từ Root**. Vì thế nó vẫn thực thi transaction khi được gọi qua proxy. Điều này **khác hoàn toàn** với việc Child tự quét lại annotation trên bean parent.

Nếu Root **chưa tạo proxy**, Child lookup thường nhận bean parent chưa được proxy; việc bật hạ tầng trong Child không sửa lại object đó. Nói cách khác, context hierarchy truyền được **tham chiếu bean**, nhưng không truyền một vòng xử lý bean hậu khởi tạo xuống/lên các context khác.

## 4. Tình huống thực tế: Spring MVC root và `DispatcherServlet` child

Trong một số ứng dụng Spring MVC truyền thống (đặc biệt khi tự tổ chức nhiều `WebApplicationContext`), có cấu trúc:

```text
Root WebApplicationContext
  ├─ Services: OrderService, PaymentService
  ├─ Repositories, DataSource
  └─ PlatformTransactionManager

DispatcherServlet WebApplicationContext (child)
  ├─ Controllers: OrderController
  ├─ HandlerMapping / ViewResolver
  └─ MVC configuration
```

**Cấu hình dễ sai:** đặt `@EnableTransactionManagement` chỉ vào cấu hình web/MVC, khiến nó được load **chỉ vào DispatcherServlet child**; `OrderService` thực tế được root context tạo. Khi đó annotation trên service ở root **không được áp dụng chỉ nhờ cấu hình child**. Controller có thể inject service vì child lookup thấy parent, nên ứng dụng vẫn khởi chạy bình thường; lúc gặp exception mới lộ ra dữ liệu không rollback như kỳ vọng.

**Cấu hình đúng theo ownership:** đăng ký hạ tầng transaction trong **root context sở hữu service**:

```java
@Configuration
@EnableTransactionManagement
public class RootTransactionConfig {
    // Đặt class này vào ROOT context cùng các service cần @Transactional.
    // TransactionManager có thể được cung cấp bởi cấu hình root khác.
}
```

Đoạn trên là **cấu hình minh họa**, không phải ứng dụng đầy đủ. Hãy bảo đảm nó **thực sự được root context register/import**, thay vì chỉ xuất hiện trong package nhưng được child scan. Với hệ thống có service do child quản lý, child cũng có thể kích hoạt transaction management cho bean của nó.

Spring Boot MVC phổ biến thường dùng một application context chính và auto-configuration của Boot có thể bật hạ tầng transaction khi điều kiện thỏa mãn. Tuy nhiên, khi ứng dụng tạo thêm child context, nhiều `DispatcherServlet`, parent/child modular context hoặc tự import cấu hình web, vẫn phải xác định **bean nào do context nào tạo**. Không nên khẳng định rằng vì dùng Boot nên scope issue không thể xảy ra.

## 5. Thực hành chạy được: một bean ở Root, kích hoạt transaction ở Child hay Root

Ta sẽ xây một project **Java 17+, Spring Framework 6.2.8, Spring JDBC, H2 in-memory** chỉ dùng **một file Java và một file Maven**. Không cần Spring Boot hoặc servlet container. Hai kịch bản sử dụng cùng một service nằm ở Root:

1. **CHILD_ONLY:** Child bật transaction annotation processing, Root không bật. Service gắn `@Transactional` nhưng không được Root proxy; hai lệnh `UPDATE` tự commit trước khi exception xuất hiện.
2. **ROOT_AND_CHILD:** Root cũng bật transaction annotation processing. Service Root được proxy; cùng exception khiến **cả hai lệnh ghi rollback**.

Ta dùng lỗi giả lập **sau khi đã chạy cả hai lệnh ghi**. Sau đó đọc lại dữ liệu để biết chúng có thực sự được rollback hay không. Chỉ kiểm tra annotation trên class là chưa đủ.

### 5.1. Cấu trúc project

```text
context-transaction-scope/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ScopeDemo.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>context-transaction-scope</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
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
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.ScopeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` hỗ trợ các `ApplicationContext` và cấu hình `@Bean`; `spring-jdbc` cung cấp `JdbcTemplate`/`DataSourceTransactionManager`; `spring-tx` chứa `@Transactional`; H2 cho database trong bộ nhớ. Ví dụ dùng trực tiếp `org.h2.jdbcx.JdbcDataSource`, nên dependency H2 phải có mặt **lúc biên dịch**, không chỉ ở runtime.

### 5.3. `ScopeDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class ScopeDemo {

    public static void main(String[] args) {
        runCase(false);
        runCase(true);
    }

    private static void runCase(boolean enableTransactionsInRoot) {
        // 1. ROOT sở hữu DataSource, TransactionManager và TransferService.
        try (var root = new AnnotationConfigApplicationContext()) {
            root.register(RootBeans.class);

            if (enableTransactionsInRoot) {
                root.register(RootTransactionConfig.class);
            }
            root.refresh();

            // 2. CHILD có cùng parent trong cả hai trường hợp.
            //    Chỉ CHILD bật transaction thì không proxy lại bean ROOT.
            try (var child = new AnnotationConfigApplicationContext()) {
                child.setParent(root);
                child.register(ChildTransactionConfig.class);
                child.refresh();

                JdbcTemplate jdbc = root.getBean(JdbcTemplate.class);
                initializeDatabase(jdbc);

                TransferService fromRoot =
                    root.getBean("transferService", TransferService.class);
                TransferService fromChild =
                    child.getBean("transferService", TransferService.class);

                System.out.println(
                    enableTransactionsInRoot ? "ROOT_AND_CHILD" : "CHILD_ONLY"
                );
                System.out.println(
                    "Child sees bean: " + child.containsBean("transferService")
                );
                System.out.println(
                    "Child owns bean: " + child.containsLocalBean("transferService")
                );
                System.out.println(
                    "Same bean: " + (fromRoot == fromChild)
                );
                System.out.println(
                    "Root service proxied: " + AopUtils.isAopProxy(fromRoot)
                );

                try {
                    fromChild.transferThenFail();
                } catch (IllegalStateException expected) {
                    System.out.println("Caught: " + expected.getMessage());
                }

                Integer a = jdbc.queryForObject(
                    "SELECT balance FROM wallets WHERE id = 1",
                    Integer.class
                );
                Integer b = jdbc.queryForObject(
                    "SELECT balance FROM wallets WHERE id = 2",
                    Integer.class
                );
                System.out.println("Balances: A=" + a + ", B=" + b);
            }
        }
    }

    private static void initializeDatabase(JdbcTemplate jdbc) {
        // Dùng cùng database H2 cho hai runCase, reset dữ liệu trước mỗi case.
        jdbc.execute("DROP TABLE IF EXISTS wallets");
        jdbc.execute(
            "CREATE TABLE wallets (id INT PRIMARY KEY, balance INT NOT NULL)"
        );
        jdbc.update("INSERT INTO wallets (id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO wallets (id, balance) VALUES (2, 50)");
    }

    // Bean được tạo và hậu xử lý bởi ROOT context.
    @Configuration(proxyBeanMethods = false)
    public static class RootBeans {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:tx_scope;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
            DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbcTemplate) {
            return new TransferService(jdbcTemplate);
        }
    }

    // Được register vào ROOT trong trường hợp thứ hai.
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class RootTransactionConfig {
    }

    // Được register vào CHILD trong CẢ HAI trường hợp.
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class ChildTransactionConfig {
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transferThenFail() {
            System.out.println(
                "Transaction active: " +
                TransactionSynchronizationManager.isActualTransactionActive()
            );

            int debited = jdbc.update(
                "UPDATE wallets SET balance = balance - 20 WHERE id = 1"
            );
            int credited = jdbc.update(
                "UPDATE wallets SET balance = balance + 20 WHERE id = 2"
            );

            if (debited != 1 || credited != 1) {
                throw new IllegalStateException("invalid wallet");
            }
            throw new IllegalStateException("forced failure");
        }
    }
}
```

**Tại sao demo này kiểm tra đúng phạm vi context?**

- `RootBeans` luôn được đăng ký **trước khi Root refresh**. Do đó `TransferService` thuộc Root trong cả hai kịch bản.
- `ChildTransactionConfig` luôn được đăng ký trong Child. Điều thay đổi duy nhất là Root có nhận `RootTransactionConfig` hay không.
- `child.containsBean(...)` và `child.containsLocalBean(...)` phân biệt **lookup qua parent** với **ownership trong child**.
- `AopUtils.isAopProxy(fromRoot)` kiểm tra Root thực sự trả về proxy hay target thông thường.
- `TransactionSynchronizationManager.isActualTransactionActive()` được gọi **ngay trong method**; với demo này nó phản ánh transaction JDBC do interceptor áp dụng tại thời điểm thực thi.
- `transferThenFail()` thực hiện **hai SQL UPDATE**, rồi cố ý ném unchecked exception. Khác biệt về số dư sau lỗi chứng minh transaction có hay không.
- Cấu hình H2 `DB_CLOSE_DELAY=-1` giữ database in-memory sống đến hết JVM; `initializeDatabase` tạo lại bảng và dữ liệu trước mỗi case để kết quả so sánh độc lập.

`TransferService` không cần `@Service` vì đã được khai báo bằng `@Bean` trong `RootBeans`. Điều quyết định không phải annotation stereotype, mà là Spring context **nào khởi tạo bean**.

### 5.4. Chạy và đọc đúng kết quả

Đứng trong thư mục `context-transaction-scope`, dùng **JDK 17+** và **Maven 3.9+**:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng do **chương trình** in ra theo đúng thứ tự (bỏ qua log từ Maven/Spring nếu có):

```text
CHILD_ONLY
Child sees bean: true
Child owns bean: false
Same bean: true
Root service proxied: false
Transaction active: false
Caught: forced failure
Balances: A=80, B=70
ROOT_AND_CHILD
Child sees bean: true
Child owns bean: false
Same bean: true
Root service proxied: true
Transaction active: true
Caught: forced failure
Balances: A=100, B=50
```

Ở **CHILD_ONLY**, hai `UPDATE` thành công và connection không được transaction manager bao lại trong service call, nên với `JdbcDataSource`/JDBC mặc định chúng được auto-commit. Ngoại lệ phát sinh **sau hai ghi** không thể tự đảo ngược chúng; dữ liệu là `A=80, B=70`.

Ở **ROOT_AND_CHILD**, Root áp dụng transaction advisor lên `TransferService` khi tạo bean. Caller lấy bean qua Child nhưng thực tế nhận **proxy từ Root**. Interceptor tạo transaction trước method; exception `IllegalStateException` thoát khỏi method nên mặc định rollback, kết quả vẫn `A=100, B=50`. Các điều kiện đầu vào giống nhau, khác nhau ở **context bật annotation-driven transaction processing**.

Lưu ý: demo chứng minh hành vi của một service cố ý ném lỗi. Trong mã nghiệp vụ thật, hai lệnh ghi cần kiểm tra số hàng cập nhật, tiền hợp lệ, xử lý đồng thời và tính nguyên tử theo yêu cầu; không dùng exception mô phỏng trong production.

## 6. Sửa lỗi context scope trong dự án thật

Khi phát hiện method có `@Transactional` nhưng không rollback, kiểm tra theo trình tự sau.

### Bước 1. Xác định nơi bean được tạo

Quan sát các `@Configuration`/`@Bean`, `@ComponentScan`, `@Import` hoặc XML bean definitions được **register vào context nào**. Trong hệ MVC truyền thống, tìm cấu hình root và cấu hình do `DispatcherServlet` tạo. **File cấu hình nằm gần controller không có nghĩa nó được load vào root.**

Nếu bạn có tham chiếu root/child trong code chẩn đoán, có thể dùng:

```java
System.out.println(root.containsLocalBean("transferService"));
System.out.println(child.containsLocalBean("transferService"));
System.out.println(child.containsBean("transferService"));
```

Đây là **đoạn chẩn đoán minh họa**, giả định đã có các biến `root`, `child`. `containsBean` có thể thấy bean ở cha; `containsLocalBean` chỉ kiểm tra bean local.

### Bước 2. Xác định transaction infrastructure đang ở context nào

Tìm nơi đăng ký:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
}
```

hoặc phần tử XML:

```xml
<tx:annotation-driven transaction-manager="transactionManager"/>
```

Hai đoạn là **cấu hình minh họa**, với XML còn cần namespace/schema/manager bean đầy đủ. Chúng cần được load ở **context sở hữu bean cần bảo vệ**. Nếu có nhiều context, có thể kích hoạt riêng cho từng context chứa các transactional beans tương ứng. Không bật tùy tiện trong mọi context như biện pháp che dấu ownership chưa rõ.

### Bước 3. Kiểm tra Spring bean được inject là proxy hay không

```java
Object service = context.getBean("transferService");
System.out.println(AopUtils.isAopProxy(service));
```

Đoạn trên giả định đã có `context` và import `org.springframework.aop.support.AopUtils`. `false` trong cấu hình **dự kiến tạo proxy** là tín hiệu cần kiểm tra (ví dụ sai context, không đăng ký advice, method không đủ điều kiện). `true` chỉ cho biết object là một AOP proxy; **chưa chứng minh riêng transaction advice đã chạy**, vì proxy cũng có thể phục vụ một advice khác. Nên kết hợp quan sát transaction active và kết quả rollback.

### Bước 4. Kiểm tra lời gọi có đi qua proxy

Một bean đã được proxy đúng vẫn có thể bị bỏ qua interception nếu tự gọi `this.inner()` trong cùng target instance:

```java
public void outer() {
    inner(); // Self-invocation: không đi qua proxy.
}

@Transactional
public void inner() {
    // Ghi dữ liệu cần transaction.
}
```

Đây là **mã minh họa**, không phải class hoàn chỉnh. Cách sửa thường là đặt annotation trên public entry method được caller gọi qua proxy, hoặc tách `inner` sang bean khác rồi inject/gọi bean đó. **Self-invocation** và **context scope** là hai lỗi độc lập; sửa context không tự chữa self-invocation.

### Bước 5. Xác định transaction manager, data source, rollback rule

Một proxy có thể hoạt động nhưng tài nguyên truy cập dữ liệu lại dùng connection ngoài transaction hoặc một manager khác. Kiểm tra `JdbcTemplate`/JPA repositories, datasource dùng chung, bean manager được chọn (đặc biệt khi nhiều manager), propagation và transaction đang tham gia. Với method ném checked exception, mặc định Spring transaction declaration có thể **commit** trừ khi cấu hình `rollbackFor` hoặc chính sách tương ứng. Khi method bắt ngoại lệ rồi trả về bình thường, interceptor không luôn biết nghiệp vụ thất bại.

Đừng vội quy mọi lỗi rollback vào context: nếu `AopUtils.isAopProxy(...)` đúng, transaction active đúng, hãy chuyển sang kiểm tra **resource participation, propagation, timeout và rollback semantics**.

## 7. Những tình huống dễ nhầm về phạm vi

### 7.1. Dùng `@ComponentScan` có đủ không?

Không. `@ComponentScan` chỉ quyết định **bean nào được đăng ký vào context đang scan**. Nếu scan service trong child thay vì root, bạn đang thay **ownership** và có thể tạo trùng bean. Chuyển component scan phải được đánh giá cùng dependency injection, bean scopes và các bean cùng tên. Cách sửa thường là kích hoạt transaction advice **tại đúng context đã sở hữu service**, ít gây thay đổi kiến trúc hơn.

### 7.2. Nếu Child nhìn thấy transaction manager của Root thì sao?

Child có thể resolve manager bean từ Root khi transaction advice của **Child** cần sử dụng nó. Nhưng chỉ nhìn thấy manager **không** có nghĩa Root service được proxy. Cần phân biệt ba lớp:

1. **Bean lookup:** Child có thấy `transactionManager` và `service` ở parent?
2. **Bean post-processing:** Context nào tạo proxy cho `service`?
3. **Runtime:** Lời gọi cụ thể có qua proxy và dùng đúng transaction manager/resource không?

Thiếu bước 2, có manager cũng không giúp annotation trên bean Root có tác dụng.

### 7.3. Có cần đặt `@EnableTransactionManagement` cạnh từng `@Transactional`?

Không. Nó là cấu hình hạ tầng của **một ApplicationContext**, không phải annotation bắt buộc gắn lên từng service. Có thể đặt ở một `@Configuration` được import vào cùng context với các service. Một context thường chỉ cần cấu hình transaction management phù hợp, không phải lặp lại trên mỗi class.

### 7.4. Nếu bean ở Child, cấu hình chỉ ở Root thì sao?

Hạ tầng auto-proxy của Root không đi xuống và hậu xử lý bean chỉ được Child tạo. Dù Child có thể thấy các bean manager/repository của Root, nó vẫn cần transaction annotation processing trong **Child** nếu muốn tự tạo transactional proxy cho service Child (hoặc một cơ chế weaving/proxy khác được cấu hình riêng).

### 7.5. Vai trò của `proxyTargetClass`, `AdviceMode.ASPECTJ` và phương thức không public?

`@EnableTransactionManagement` mặc định dùng `AdviceMode.PROXY`. `proxyTargetClass=true` thay cách tạo proxy theo class thay vì interface trong trường hợp thích hợp, **không thay đổi phạm vi context**. Spring cũng hỗ trợ `AdviceMode.ASPECTJ` với weaving/dependency và setup riêng, có semantics khác proxy mode; bài này mô tả **proxy mode mặc định**, không áp dụng nguyên xi mọi kết luận proxy cho AspectJ weaving.

Method `private` không thể được proxy intercept theo lối gọi thông thường. Khả năng của method package-private/protected thay đổi theo phiên bản và loại proxy, vì vậy ưu tiên public service methods được gọi từ bên ngoài bean. Đừng lẫn hạn chế method/proxy với việc infrastructure đặt sai context.

### 7.6. Nếu ứng dụng Spring Boot không khai báo `@EnableTransactionManagement`?

Spring Boot có transaction auto-configuration theo các điều kiện về dependency và transaction manager. Trong ứng dụng thông dụng nó có thể tự bật annotation-driven transaction management. Điều đó **không có nghĩa** mọi custom `ApplicationContext` hay `DispatcherServlet` child đều đã được cấu hình tương đương. Khi xử lý lỗi hãy kiểm tra **hạ tầng đang thực sự tồn tại trong từng context**, không chỉ suy luận từ dependency có trong `pom.xml`.

### 7.7. Khi có nhiều `DispatcherServlet` hoặc nhiều module context?

Mỗi child `WebApplicationContext` có thể có controller/bean riêng. Nếu cấu hình transaction chỉ nằm ở child của một servlet, những bean riêng ở child khác không tự được xử lý. Có thể đặt các service dùng chung ở Root với transaction infrastructure của Root và để các controller child inject proxy Root, hoặc cấu hình advice độc lập tại những child thực sự sở hữu transactional beans. Giữ ownership dễ kiểm tra sẽ giảm những lỗi tưởng chừng ngẫu nhiên giữa từng endpoint.

## 8. Bảng tự kiểm tra và bài tập

| Triệu chứng | Nguyên nhân cần ưu tiên xác minh | Quan sát hữu ích |
| --- | --- | --- |
| Service Root có `@Transactional` nhưng rollback không chạy | Advice chỉ được bật trong Child | Kiểm tra parent/child registration và `AopUtils.isAopProxy` |
| Child `getBean(...)` trả về service nhưng nó không được proxy | Bean thuộc Root; Child chỉ resolve tham chiếu | `containsBean` true nhưng `containsLocalBean` false |
| Service proxy đúng nhưng gọi nội bộ không mở transaction | `this.method()` bỏ qua interceptor | Đặt boundary ở caller hoặc gọi qua bean khác |
| Bean được proxy nhưng lỗi vẫn commit | Exception bị bắt, checked exception, resource/manager sai | Xem rollback rules, active transaction, datasource |
| Controller trong Child có annotation hoạt động nhưng service Root không | Hai bean thuộc hai context khác nhau | So sánh bean ownership và nơi bật infrastructure |
| Bật `proxyTargetClass=true` nhưng service vẫn không có transaction | Context sở hữu bean không có transaction advice | Cấu hình cùng context trước khi đổi proxy type |

**Bài tập thực hành trên một bản sao của demo:**

1. Xóa `child.register(ChildTransactionConfig.class)` ở cả hai case và chạy lại. Ở case Root có transaction, dự đoán `TransferService` có còn proxy không; giải thích dựa trên **owner context**.
2. Chuyển `TransferService` từ Root sang một `@Bean` trong Child rồi chỉ bật transaction ở Child. Dự đoán kết quả `AopUtils.isAopProxy(...)` và rollback. Khi sửa, bảo đảm không giữ hai bean trùng tên giữa root/child.
3. Đổi lỗi unchecked thành checked exception với `@Transactional(rollbackFor = IOException.class)` trong một phương thức phù hợp; ghi rõ vì sao rollback policy cần thay đổi.
4. Viết một service method gọi `this.transferThenFail()` và xem vì sao lời gọi nội bộ có thể không qua proxy. Tách sang bean khác hoặc nâng boundary lên entry point, rồi kiểm tra lại.
5. Vẽ sơ đồ context của dự án thực tế: service do ai tạo, configuration transaction ở đâu, caller lấy bean từ context nào, transaction manager nằm ở đâu. Chỉ khi bốn câu hỏi có câu trả lời mới kết luận rằng annotation sẽ được intercept.

**Kết luận cần nhớ:** trong proxy mode, **hạ tầng `@EnableTransactionManagement` hoạt động theo `ApplicationContext` nơi nó được cấu hình**. Context con có thể **nhìn thấy bean cha**, nhưng điều đó không có nghĩa nó sẽ **tạo proxy cho bean cha**. Khi đặt `@Transactional` lên service, hãy kiểm tra nơi bean được khởi tạo, nơi kích hoạt transaction annotation processing, và luồng gọi thực tế qua proxy.

## 9. Tham khảo chính thức

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html) — giải thích rõ giới hạn cùng `ApplicationContext` và ví dụ `DispatcherServlet` child.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — `@EnableTransactionManagement` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — BeanFactory/ApplicationContext Hierarchies](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
