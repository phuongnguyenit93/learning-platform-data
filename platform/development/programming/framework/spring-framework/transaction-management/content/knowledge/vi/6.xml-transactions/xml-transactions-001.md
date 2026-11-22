# Bật annotation bằng `<tx:annotation-driven>` trong Spring Framework (cấu hình XML)

Trong Spring Framework, `@Transactional` cho phép khai báo ranh giới giao dịch ngay trên class hoặc method Java. Nhưng **chỉ viết `@Transactional` không đủ**: container phải bật hạ tầng đọc annotation, tạo transaction advice/proxy và biết dùng transaction manager nào. Khi ứng dụng cấu hình bằng XML, phần tử **`<tx:annotation-driven/>`** là cách trực tiếp để bật cơ chế đó.

Đây là một bài về **cấu hình XML trong Spring transaction management**. Trọng tâm là cách khai báo đúng namespace `tx`, kết nối với `PlatformTransactionManager`, cách Spring tạo proxy và khi nào `@Transactional` thực sự có hiệu lực. Ví dụ hoàn chỉnh dùng Spring Framework 6.2, Java 17, JDBC và H2 để bạn có thể tự quan sát commit/rollback.

## 1. `<tx:annotation-driven/>` giải quyết vấn đề nào?

Xét một service nghiệp vụ:

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // ghi bản ghi thanh toán
        // cập nhật số dư
    }
}
```

Đây là **mã minh họa**, chưa phải chương trình chạy độc lập. Ý nghĩa dự định là hai thao tác DB nằm trong cùng giao dịch. Tuy nhiên:

- `@Transactional` chỉ cung cấp **metadata**: propagation, isolation, `readOnly`, timeout, rollback rules và transaction manager tùy chọn.
- Spring phải đăng ký hạ tầng nhận biết annotation, tạo advisor/interceptor và quyết định bean nào cần proxy.
- Phải tồn tại một **transaction manager phù hợp** với hạ tầng truy cập dữ liệu. Với JDBC local transaction, ví dụ `JdbcTransactionManager`/`DataSourceTransactionManager`; với JPA, thường là `JpaTransactionManager`.
- Lời gọi method phải **đi qua Spring proxy** khi dùng chế độ mặc định `proxy`.
- DAO/repository phải truy cập tài nguyên tương thích để thao tác thực sự tham gia cùng transaction.

`<tx:annotation-driven/>` giải quyết phần **kích hoạt giao dịch khai báo theo annotation** ở cấp application context. Nó không thay thế transaction manager, không tự tạo datasource, không tự ghi SQL và không biến mọi lời gọi method trực tiếp thành lời gọi có transaction.

Luồng khái quát:

```text
XML ApplicationContext
   |
   +-- <tx:annotation-driven/>: đăng ký transaction infrastructure
   |         |
   |         +-- transaction attribute source: đọc @Transactional
   |         +-- transaction advisor + TransactionInterceptor
   |         +-- auto-proxy cho Spring bean phù hợp
   |
   +-- <bean id="transactionManager" .../>
   |         |
   |         +-- quản lý DataSource/EntityManager/transaction backend
   |
   +-- @Service/@Repository hoặc bean khai báo trong XML
             |
Caller --> service proxy --> TransactionInterceptor
                                 |
                                 +-- getTransaction(...)
                                 +-- gọi method đích
                                 +-- commit / rollback
                                 +-- resource cleanup
```

Phần tử này cần cho **hạ tầng transaction annotation**; nó không đồng nghĩa với `<context:annotation-config/>` (tiêm phụ thuộc và các annotation cấu hình bean) hoặc `<aop:aspectj-autoproxy/>` (bật cơ chế xử lý aspect). Những phần tử đó **không tự thay thế** transaction interceptor mà `<tx:annotation-driven/>` đăng ký.

## 2. Cấu hình XML tối thiểu và ý nghĩa từng mảnh

Một file XML có thể có cấu trúc như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.tx"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <tx:annotation-driven transaction-manager="transactionManager"/>
</beans>
```

Ví dụ minh họa một **application context duy nhất** với JDBC/H2. Các thành phần:

1. **`xmlns:tx` và `spring-tx.xsd`** đăng ký cú pháp namespace transaction để XML parser hiểu phần tử `tx:annotation-driven`. Prefix `tx` phải trỏ đúng URI `http://www.springframework.org/schema/tx`; tên prefix là quy ước, namespace URI mới quyết định ý nghĩa.
2. **`xmlns:context` cùng `<context:component-scan>`** yêu cầu container tìm những class được đánh dấu `@Component`, `@Service`, `@Repository`, ... trong package `demo.tx`. Có thể dùng `<bean .../>` thay component scanning để đăng ký từng service; `<tx:annotation-driven/>` không phụ thuộc việc bean xuất hiện bằng cách nào.
3. **`dataSource`** cung cấp JDBC connection. `DriverManagerDataSource` thích hợp cho ví dụ nhỏ, không có connection pool; ứng dụng production nên dùng pool/cấu hình thích hợp.
4. **`transactionManager`** là bean Spring thực thi giao thức `PlatformTransactionManager`. Ở đây `JdbcTransactionManager` quản lý local transaction cho chính `dataSource` nói trên.
5. **`jdbcTemplate`** lấy connection qua hạ tầng JDBC của Spring và có thể dùng connection gắn với transaction hiện tại.
6. **`<tx:annotation-driven transaction-manager="transactionManager"/>`** bật hạ tầng xử lý `@Transactional` và chỉ định bean manager được dùng mặc định.

Điểm không thể bỏ qua: `transactionManager` và `jdbcTemplate` ở cấu hình này **tham chiếu cùng một bean `dataSource`**. Nếu DAO lấy một connection riêng từ nguồn khác hoặc dùng manager không phù hợp, annotation có thể tồn tại mà thao tác dữ liệu không nằm trong transaction bạn tưởng.

### Có thể rút ngắn thành `<tx:annotation-driven/>` không?

Có, khi bean transaction manager mặc định có tên **`transactionManager`**:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="dataSource"/>
</bean>

<tx:annotation-driven/>
```

Theo tài liệu namespace, giá trị mặc định của thuộc tính `transaction-manager` là tên bean `transactionManager`. Nếu bạn đặt tên khác (ví dụ `ordersTxManager`), nên khai báo rõ:

```xml
<bean id="ordersTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="ordersDataSource"/>
</bean>

<tx:annotation-driven transaction-manager="ordersTxManager"/>
```

Hai đoạn trên là **fragment cấu hình**; bạn phải định nghĩa `dataSource`/`ordersDataSource` và phần `<beans>`/namespace tương ứng trong file thực tế.

> Không suy luận rằng việc đặt `id="transactionManager"` tự tạo ra transaction: bean manager phải có class, dependency và tài nguyên hợp lệ; `<tx:annotation-driven/>` chỉ kết nối hạ tầng annotation với manager đó.

## 3. Ví dụ chạy độc lập: XML kích hoạt commit và rollback

Ví dụ dùng **JDK 17+**, **Maven 3.9+**, **Spring Framework 6.2.14** và H2 in-memory. Không dùng Spring Boot auto-configuration để thấy rõ chính `<tx:annotation-driven/>` là cấu hình bật transaction; dữ liệu minh họa chỉ nằm trong database bộ nhớ.

Mục tiêu: một service thực hiện trừ tiền A rồi cộng cho B. Khi ném `IllegalStateException` giữa hai lệnh, transaction rollback. Khi thành công, cả hai thay đổi được commit.

Cấu trúc chính xác:

```text
tx-xml-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── tx/
        │           ├── Main.java
        │           └── TransferService.java
        └── resources/
            └── spring-tx.xml
```

### 3.1. Maven dependencies

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>tx-xml-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
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

`spring-context` cung cấp XML container/component scanning; `spring-jdbc` cung cấp `JdbcTemplate`, `DriverManagerDataSource` và JDBC transaction manager, kéo theo các Spring module cần thiết cho transaction. H2 là JDBC driver/database chỉ dùng lúc chạy. Một ứng dụng thực tế nên để dependency management/BOM nhất quán nếu sử dụng nhiều Spring module.

### 3.2. XML cấu hình đầy đủ

File `src/main/resources/spring-tx.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.tx"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:transfer_demo;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <tx:annotation-driven transaction-manager="transactionManager"/>
</beans>
```

`DB_CLOSE_DELAY=-1` giữ H2 in-memory database tồn tại trong vòng đời JVM dù các connection dùng ngoài transaction được đóng sau từng thao tác. Điều này giúp đọc lại số dư bằng `JdbcTemplate` mà không cần một connection cố định. Trong production, hãy quản lý connection pool và lifecycle phù hợp thay cho `DriverManagerDataSource`.

### 3.3. Service có annotation

File `src/main/java/demo/tx/TransferService.java`:

```java
package demo.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount, boolean fail) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debitRows = jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, fromId);

        if (debitRows != 1) {
            throw new IllegalArgumentException("source account missing");
        }

        if (fail) {
            throw new IllegalStateException("simulated failure");
        }

        int creditRows = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);

        if (creditRows != 1) {
            throw new IllegalArgumentException("destination account missing");
        }
    }
}
```

`@Service` làm class được `component-scan` phát hiện. Chỉ một constructor nên Spring có thể thực hiện constructor injection mà không cần `@Autowired`. `@Transactional` trên public method yêu cầu Spring tạo transaction boundary bao quanh lời gọi qua proxy.

### 3.4. Chương trình gọi service qua Spring container

File `src/main/java/demo/tx/Main.java`:

```java
package demo.tx;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("spring-tx.xml")) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 2, 50);

            TransferService service = context.getBean(TransferService.class);

            printBalances(jdbc, "BEFORE");

            try {
                service.transfer(1, 2, 30, true);
            } catch (IllegalStateException expected) {
                System.out.println("THROW=" + expected.getMessage());
            }
            printBalances(jdbc, "AFTER_ROLLBACK");

            service.transfer(1, 2, 30, false);
            printBalances(jdbc, "AFTER_COMMIT");
        }
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);

        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Chạy tại thư mục `tx-xml-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.tx.Main
```

Các dòng **do chương trình tự in ra**, không tính log thư viện/Maven:

```text
BEFORE: A=100, B=50
THROW=simulated failure
AFTER_ROLLBACK: A=100, B=50
AFTER_COMMIT: A=70, B=80
```

Giải thích theo đúng đường thực thi:

1. `Main` khởi tạo `ClassPathXmlApplicationContext`, khiến Spring parse `spring-tx.xml`, đăng ký service, datasource, JDBC template và manager; `<tx:annotation-driven/>` bật transaction infrastructure.
2. Hai lệnh `INSERT` thiết lập dữ liệu ban đầu. `context.getBean(TransferService.class)` lấy **Spring-managed service bean**, đối tượng mà transaction auto-proxy có thể bao quanh.
3. Lần `service.transfer(..., true)`: interceptor mở transaction; `JdbcTemplate` thực hiện debit qua connection thuộc transaction; `IllegalStateException` thoát khỏi method trước khi credit. Spring mặc định rollback với `RuntimeException`, nên số dư vẫn 100 và 50.
4. Lần `service.transfer(..., false)`: cả debit và credit chạy bình thường, interceptor yêu cầu manager commit, số dư thành 70 và 80.
5. Service **không hề gọi `begin()`, `commit()` hay `rollback()` thủ công**: annotation metadata + XML infrastructure + transaction manager giải quyết phần đó.

Trong demo, `TransferService` không implements interface; khi cần tạo proxy, Spring có thể sử dụng proxy dựa trên class cho đối tượng này dù `proxy-target-class` không được bật. Không kiểm thử bằng cách ép kiểu/so sánh tên class proxy; hãy quan sát hành vi rollback hoặc dùng `AopUtils.isAopProxy(bean)` ở môi trường chẩn đoán.

**Giới hạn của ví dụ:** chưa kiểm tra đủ số dư, khóa đồng thời, optimistic locking hay duplicate transfer. Đây là ví dụ để hiểu transaction activation, không phải mã nghiệp vụ chuyển tiền triển khai production.

### 3.5. Thử tắt `<tx:annotation-driven/>` để thấy khác biệt

Trong **bản sao demo** dùng DB H2 mới, xóa hoặc comment đúng một dòng:

```xml
<tx:annotation-driven transaction-manager="transactionManager"/>
```

Lúc này method vẫn có `@Transactional`, nhưng XML context không còn bật transaction annotation infrastructure. Trong cấu hình `DriverManagerDataSource` + `JdbcTemplate` của demo, từng câu `UPDATE` bên ngoài Spring transaction dùng connection với JDBC auto-commit mặc định. Khi exception xảy ra giữa hai `UPDATE`, debit có thể đã commit riêng, còn credit chưa chạy; tổng số dư không còn nhất quán. Đó là minh họa rõ nhất cho sự khác biệt giữa **annotation metadata** và **hạ tầng thực thi annotation**.

Lưu ý: nếu ứng dụng còn một cấu hình transaction khác (Java `@EnableTransactionManagement`, proxy/transaction advice khác, Spring Boot auto-configuration, container-managed transaction), việc bỏ một dòng XML **không bảo đảm** tắt toàn bộ transaction. Thí nghiệm trên chỉ có kết luận xác định trong context tối giản đã trình bày.

## 4. Spring xử lý `<tx:annotation-driven>` như thế nào?

Khi đọc XML, Spring dùng cơ chế namespace handler/parser để đăng ký hạ tầng xử lý transaction annotation. Ở chế độ mặc định `proxy`, về mặt khái niệm có:

- **Transaction annotation attribute source:** đọc metadata trên class/method, như `@Transactional(propagation=..., rollbackFor=...)`.
- **Transaction advisor:** xác định lời gọi nào cần áp dụng advice theo metadata.
- **`TransactionInterceptor`:** bao quanh invocation, tương tác với transaction manager trước/sau khi method được gọi.
- **Auto-proxy creator:** tạo proxy cho những bean phù hợp, để caller đi qua interceptor.
- **Transaction manager:** làm việc với transaction và tài nguyên dữ liệu thực tế; hạ tầng thường chọn manager mặc định XML hoặc manager được qualifier trong `@Transactional`.

Đây là **mô hình logic**, không có nghĩa mỗi method `@Transactional` tương ứng một transaction vật lý hoặc Spring bắt buộc tạo một proxy duy nhất cho mỗi annotation. Manager còn phải xét propagation và có transaction nào đang tồn tại không.

Dòng thời gian một lời gọi `REQUIRED` chưa có transaction trước đó:

```text
1. caller -> proxy.placeOrder()
2. interceptor tìm @Transactional cho method
3. manager.getTransaction(definition)
4. manager mở local JDBC transaction hoặc làm việc với resource backend thích hợp
5. interceptor -> target.placeOrder()
6. target -> repository/JdbcTemplate -> thao tác DB trong transaction
7. method return: manager.commit(status)
   method ném exception khớp rollback rule: manager.rollback(status)
8. manager giải phóng transaction resource, proxy trả kết quả/exception
```

Nếu transaction đã có và `@Transactional` dùng `Propagation.REQUIRED`, scope mới **tham gia transaction hiện có**. `@Transactional` không tự cam kết rằng mỗi method có transaction độc lập. Đây là đặc điểm của transaction model, không phải một thuộc tính riêng của XML.

Đối với JDBC, `JdbcTemplate` làm việc thông qua cơ chế `DataSourceUtils` để nhận connection phù hợp với transaction đang gắn trong thread. Nếu code lấy connection từ datasource khác hoặc tạo connection ngoài hạ tầng của Spring, thao tác đó có thể không thuộc transaction vừa mở.

## 5. Thuộc tính của `<tx:annotation-driven>` và giá trị mặc định

Đây là nhóm thuộc tính quan trọng của element XML; cần tách biệt chúng với **thuộc tính của chính `@Transactional`**.

| Thuộc tính XML | Mặc định | Dùng để làm gì? |
| --- | --- | --- |
| `transaction-manager` | `transactionManager` | Chỉ tên bean transaction manager dùng mặc định cho các annotation không chỉ định manager cụ thể. |
| `mode` | `proxy` | Chọn xử lý bằng Spring AOP proxy hoặc `aspectj` weaving. |
| `proxy-target-class` | `false` | Trong `proxy` mode, quyết định ưu tiên proxy dựa trên class khi `true`; `false` thường ưu tiên JDK interface proxy nếu target có interface phù hợp. |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Thứ tự transaction advice so với các advisor khác trong chuỗi AOP. |

Các ví dụ cấu hình tùy nhu cầu:

```xml
<tx:annotation-driven
    transaction-manager="ordersTxManager"
    mode="proxy"
    proxy-target-class="true"
    order="100"/>
```

Đây là fragment XML, yêu cầu bean `ordersTxManager` có thật. Nó yêu cầu class-based proxy. **Không cần chủ động bật `proxy-target-class="true"` chỉ vì đang dùng `@Transactional`**; hãy chọn dựa trên giao diện bean, cách gọi và các giới hạn của proxy.

### 5.1. `mode="proxy"` và `mode="aspectj"`

**Proxy mode** là mặc định:

- Spring bao quanh bean bằng proxy khi bean có transactional method phù hợp.
- Chỉ những lời gọi **đi vào qua proxy** mới được transaction advice chặn.
- Lời gọi `this.someMethod()` trong cùng bean không tạo thêm proxy invocation.
- Final method không thể bị override bởi class-based proxy; private method không phải điểm interception qua proxy theo cách thông thường.
- Gọi annotation method trong constructor hoặc quá trình `@PostConstruct` thường không có proxy hoàn chỉnh để đảm bảo transaction.

**AspectJ mode** có thể dùng bytecode weaving để áp dụng transaction aspect mà không dựa vào việc caller đi qua proxy. Nhưng chỉ đặt:

```xml
<tx:annotation-driven mode="aspectj"/>
```

**chưa đủ** để có weaving hoạt động: cần module `spring-aspects` và cấu hình compile-time hoặc load-time weaving cùng AspectJ setup thích hợp. Nó là lựa chọn kiến trúc riêng, không phải “công tắc sửa mọi lỗi transaction” trong ứng dụng XML thông thường.

### 5.2. JDK proxy so với class-based proxy

Nếu bean implements interface, `proxy-target-class="false"` thường chọn **JDK dynamic proxy**, giao diện proxy chủ yếu là các interface được expose. Điều này ảnh hưởng việc inject theo kiểu concrete class và kiểu method có thể gọi. Nếu cần inject theo concrete class, có thể chọn class-based proxy (`proxy-target-class="true"`) khi class có thể proxy hoặc điều chỉnh client phụ thuộc interface.

Nếu target không có interface phù hợp, Spring AOP có thể dùng proxy dựa trên class dù giá trị mặc định là `false`. Không suy ra “đặt false thì chắc chắn không hỗ trợ class không implements interface”.

**Chú ý cấu hình toàn cục:** nhiều khai báo `<aop:config>`, `<aop:aspectj-autoproxy>` và `<tx:annotation-driven>` trong cùng context có thể hợp nhất vào auto-proxy creator chung. Bật class-based proxy trong một phần cấu hình có thể ảnh hưởng proxy của những phần khác. Hãy kiểm tra thiết kế AOP tổng thể trước khi thay đổi cờ này.

### 5.3. Thuộc tính `order` không thay đổi logic commit của DB

`order` quyết định thứ tự advice khi có logging, security, retry, monitoring hoặc aspect khác. Thứ tự khác nhau sẽ làm “transaction bắt đầu trước hay sau advice khác” khác nhau trong một số call stack. Nó không tự đổi isolation, propagation hoặc cấu hình datasource.

Ví dụ nếu retry advice ở ngoài transaction interceptor, mỗi lần retry có thể đi vào **một transaction mới**; nếu retry advice nằm trong một transaction advice bên ngoài, các lần thử có thể chia sẻ trạng thái transaction không còn commit được sau lỗi. Thiết kế AOP advice order phải xét semantics đó, không chỉ đặt một số tùy ý.

## 6. Thuộc tính `@Transactional` vẫn nằm trên Java class/method

`<tx:annotation-driven>` bật **cơ chế đọc annotation**; còn chi tiết transaction cho từng operation được khai báo như sau:

```java
@Service
@Transactional(readOnly = true)
public class AccountQueryService {
    @Transactional(
        readOnly = false,
        propagation = Propagation.REQUIRES_NEW,
        rollbackFor = BusinessCheckedException.class
    )
    public void updateAccount() throws BusinessCheckedException {
        // thao tác cập nhật và quy tắc rollback riêng
    }
}
```

Đây là **snippet minh họa**, cần `BusinessCheckedException`, imports và logic DAO thực tế. Annotation trên method **cụ thể** có thể ưu tiên hơn cấu hình annotation trên class. Dùng `@Transactional` của `org.springframework.transaction.annotation.Transactional`, hoặc trong một số trường hợp annotation chuẩn Jakarta Transaction được Spring hỗ trợ; không nhầm với annotation của thư viện khác.

Giá trị mặc định thường gặp:

| Thuộc tính của `@Transactional` | Mặc định và ý nghĩa |
| --- | --- |
| `propagation` | `REQUIRED`: tham gia transaction hiện có hoặc tạo mới nếu chưa có. |
| `isolation` | `DEFAULT`: dùng mức isolation mặc định của backend nếu tạo transaction mới. |
| `readOnly` | `false`; khi `true` thường là hint tối ưu/kiểm tra do manager/provider thực hiện, không phải hàng rào cấm ghi mọi hệ DB. |
| `timeout` | Theo transaction system hoặc không giới hạn nếu không hỗ trợ. |
| `rollbackFor` | Không thêm quy tắc checked exception đặc biệt nếu không chỉ định. |
| rollback mặc định | `RuntimeException` và `Error` yêu cầu rollback; checked `Exception` thông thường không. |
| `transactionManager` hoặc `value` | Qualifier chọn manager cụ thể khi cần. |

Có thể chỉ định manager ở từng method nếu ứng dụng có nhiều manager:

```java
@Transactional("ordersTxManager")
public void placeOrder() {
    // dùng transaction manager được xác định bằng qualifier/bean name
}
```

Đây là **snippet minh họa**, không phải chương trình độc lập. Tên `ordersTxManager` phải trỏ tới một manager thật, quản lý chính tài nguyên mà DAO của operation sử dụng.

**Không trộn hai lớp thuộc tính:** `mode`, `order`, `proxy-target-class` nằm trong cấu hình kích hoạt advice; còn `propagation`, `readOnly`, `isolation`, `rollbackFor` nằm trong transaction metadata của method.

## 7. Hai cách đăng ký service: XML bean và component scanning

`<tx:annotation-driven>` hoạt động với bean do container quản lý, không yêu cầu mọi bean đều khai báo `@Service`.

### Cách A: Đăng ký service bằng XML

```xml
<bean id="paymentService" class="demo.tx.PaymentService">
    <constructor-arg ref="jdbcTemplate"/>
</bean>

<tx:annotation-driven transaction-manager="transactionManager"/>
```

Các bean `jdbcTemplate`, `transactionManager` và class `PaymentService` phải được định nghĩa tương ứng. Spring vẫn đọc `@Transactional` từ `PaymentService` khi bean được tạo trong cùng context.

### Cách B: Đăng ký bằng component scanning trong XML

```xml
<context:component-scan base-package="demo.tx"/>
<tx:annotation-driven transaction-manager="transactionManager"/>
```

Khi `PaymentService` được đánh dấu `@Service` và nằm dưới package được scan, Spring tạo bean rồi áp dụng transaction advice phù hợp. Không bắt buộc thêm `<context:annotation-config/>` nếu `component-scan` đã đăng ký những annotation post-processor cần thiết trong cấu hình bình thường.

Ngược lại, object được tạo bằng `new PaymentService(...)` ngoài container không tự được Spring AOP bao quanh chỉ vì class có `@Transactional`. Mấu chốt là **bean được quản lý và caller lấy đúng proxy**.

## 8. ApplicationContext và WebApplicationContext: đặt tag ở đâu?

Một giới hạn dễ bỏ sót: `<tx:annotation-driven/>` **chỉ tìm các bean transactional trong cùng application context nơi element được khai báo**. Đặc biệt trong Spring MVC kiểu XML truyền thống, có thể có context cha cho service/repository và context con thuộc `DispatcherServlet` cho controller.

Ví dụ cấu trúc:

```text
Root WebApplicationContext
   |-- services
   |-- repositories
   |-- dataSource
   |-- transactionManager
   |-- <tx:annotation-driven/>  <-- hợp lý cho service tại root
   |
   +-- DispatcherServlet child WebApplicationContext
          |-- controllers
          |-- view resolvers / MVC configuration
```

Nếu service bean được định nghĩa ở **root context** nhưng bạn chỉ đặt `<tx:annotation-driven/>` trong **child DispatcherServlet context**, transaction advice của child không tự đi lên wrap các service root bean. Kết quả có thể là controller gọi service nhưng `@Transactional` của service không được kích hoạt.

Đây là tình huống tạo ảo giác “đã khai báo `<tx:annotation-driven/>` mà không rollback” rất phổ biến trong dự án XML cũ. Cách giải quyết là đặt element trong context thật sự tạo/đăng ký service cần transactional, cùng manager phù hợp. Đừng chữa bằng cách copy toàn bộ service vào nhiều context vì có thể tạo nhiều bean instance, nhiều datasource hoặc nhiều transaction infrastructure khó kiểm soát.

Trong ứng dụng có nhiều context, hãy kiểm tra **chính xác file XML nào được load vào context nào**. Việc một file XML tồn tại trong `resources/` hoặc có mặt trên classpath chưa có nghĩa nó đã được load.

## 9. Nhiều transaction manager: chọn đúng tài nguyên

Một XML có thể chứa nhiều nguồn dữ liệu:

```xml
<bean id="ordersDataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <!-- cấu hình JDBC riêng cho đơn hàng -->
</bean>

<bean id="reportingDataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <!-- cấu hình JDBC riêng cho báo cáo -->
</bean>

<bean id="ordersTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="ordersDataSource"/>
</bean>

<bean id="reportingTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="reportingDataSource"/>
</bean>

<tx:annotation-driven transaction-manager="ordersTxManager"/>
```

Đây là **fragment để đọc cấu trúc, không phải cấu hình chạy độc lập**: phần bean datasource phải có các thuộc tính kết nối thực. `ordersTxManager` là manager mặc định cho annotation không qualifier trong XML này; một method cần manager khác có thể dùng `@Transactional("reportingTxManager")` nếu tên/qualifier đó tồn tại.

Các câu hỏi bắt buộc phải trả lời trước khi tin rằng rollback hoạt động:

1. Service thực sự dùng transaction manager nào sau khi resolve annotation?
2. Repository/JDBC template/JPA persistence unit sử dụng datasource nào?
3. Manager và DAO có cùng resource/backend phù hợp không?
4. Có một thao tác ngoài DB (HTTP, email, file I/O) mà ta đang **nhầm** rằng cùng bị rollback không?

`<tx:annotation-driven/>` không tự tạo distributed transaction giữa hai datasource. Một `JdbcTransactionManager` cho datasource A không tự rollback dữ liệu trên datasource B. Trường hợp cần atomicity nhiều resource phải có hạ tầng điều phối phù hợp (ví dụ JTA/XA khi cần và hỗ trợ) hoặc chiến lược tích hợp như outbox/saga theo yêu cầu nghiệp vụ.

Với JPA, khai báo `JpaTransactionManager` cho `EntityManagerFactory` phù hợp thay cho JDBC manager được chọn theo thói quen. Với R2DBC/reactive, cần transaction manager và cách quản lý context tương thích với reactive execution; ví dụ JDBC ở bài này không chứng minh hành vi reactive.

## 10. Các lỗi thường gặp khi bật annotation bằng XML

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| Spring báo không nhận ra prefix `tx`/lỗi parse XML | Thiếu `xmlns:tx` hoặc dòng `spring-tx.xsd` sai | Đọc lại URI namespace và `xsi:schemaLocation`; đặt element bên trong `<beans>`. |
| Không tìm được `transactionManager` | Manager bean không tồn tại, sai id, XML chưa load | Đặt `id="transactionManager"` hoặc cấu hình `transaction-manager="idPhuHop"`, chắc chắn bean được tạo trong context áp dụng. |
| Method có annotation nhưng không rollback | Chưa load XML có `<tx:annotation-driven/>`, method không qua proxy, sai context/manager | Kiểm tra context đang sử dụng, bean proxy và datasource thực sự; làm test ném unchecked exception giữa hai UPDATE. |
| Bean được tạo bằng `new` | Không phải Spring-managed bean | Đăng ký qua `<bean>` hoặc `component-scan`; inject/lấy bean từ context. |
| `this.process()` tự gọi method cùng class | Self-invocation bỏ qua proxy transaction advice | Chuyển boundary lên method được gọi từ ngoài hoặc tách method cần transaction sang bean khác. |
| `@Transactional` trên private/final method | Method không được proxy intercept theo cách mong muốn | Đặt transaction boundary trên public method có thể proxy; kiểm tra kiểu proxy thực tế. |
| Chỉ khai báo ở child servlet context | Service nằm trong parent/root context | Đặt `<tx:annotation-driven/>` tại context quản lý service, tránh đăng ký nhầm. |
| Có transaction nhưng thay đổi SQL vẫn commit riêng | DAO lấy connection/resource không tham gia manager | Kiểm tra datasource identity và dùng `JdbcTemplate`/`DataSourceUtils` hoặc JPA integration tương thích. |
| Interface bean không inject được theo concrete class | JDK dynamic proxy chỉ expose interface | Inject theo interface hoặc chọn class-based proxy khi phù hợp. |
| Checked exception không rollback | Quy tắc rollback mặc định không bao gồm checked exception | Dùng `rollbackFor`, hoặc thiết kế exception policy rõ ràng. |
| Exception bị bắt rồi return bình thường | Transaction interceptor không nhìn thấy exception thoát ra | Propagate exception hoặc chủ động đánh dấu rollback-only theo đúng contract. |
| Thêm `mode="aspectj"` nhưng không có transaction | Thiếu `spring-aspects`/weaving | Hoàn thiện AspectJ setup hoặc quay về proxy mode thông thường. |
| Giao dịch không lan qua `@Async`/thread mới | Imperative transaction thường gắn với execution thread | Đặt transaction ở phía thread thực hiện công việc hoặc thiết kế boundary riêng. |
| Gọi `@Transactional` lúc `@PostConstruct` | Proxy chưa sẵn sàng cho self-invocation của bean | Chuyển việc khởi tạo sang coordinator gọi qua bean proxy sau khi context sẵn sàng. |

### 10.1. Self-invocation: ví dụ rất dễ tưởng đã bật thành công

```java
@Service
public class InvoiceService {
    public void submit() {
        saveInvoice(); // gọi nội bộ: không đi qua proxy
    }

    @Transactional
    public void saveInvoice() {
        // thao tác DB
    }
}
```

Đây là đoạn minh họa, chưa có DAO implementation. Với `mode="proxy"`, caller gọi `submit()` từ ngoài qua proxy **không khiến** annotation trên `saveInvoice()` được áp dụng cho lời gọi nội bộ. Nếu `submit()` chưa có transaction, không có transaction mới chỉ nhờ annotation trên `saveInvoice()`.

Có thể sửa bằng cách khai báo `@Transactional` trên public `submit()` (khi toàn bộ use case cần transaction), hoặc chuyển `saveInvoice()` sang bean riêng và inject bean đó, để call đi qua proxy. Nếu outer method đã nằm trong transaction, lời gọi nội bộ có thể tiếp tục dùng transaction **đang có**, nhưng annotation riêng của inner method vẫn không tạo boundary/propagation mới.

### 10.2. Chỉ nhìn thấy SQL chạy không chứng minh commit

Khi dùng JPA, thao tác `flush()` gửi SQL tới DB mà chưa chắc transaction đã commit. Với JDBC, `UPDATE` trả row count cũng chỉ cho biết SQL được thực thi trong ngữ cảnh hiện tại. Cần xác nhận trạng thái dữ liệu **sau khi transaction boundary kết thúc** để kiểm tra rollback thật.

### 10.3. Read-only không phải cơ chế cấm ghi tuyệt đối

`@Transactional(readOnly = true)` có thể giúp framework/provider tối ưu và truyền read-only hint xuống connection hoặc persistence context; không nên trông chờ mọi DB luôn từ chối `INSERT`/`UPDATE` trong mọi trường hợp. Muốn thực thi quyền đọc/ghi hãy dùng DB permissions, thiết kế API và cơ chế thích hợp.

## 11. Phân biệt với cấu hình transaction bằng XML thuần và bằng Java

Spring hỗ trợ các cách khai báo giao dịch sau:

| Cách | Khai báo quy tắc giao dịch ở đâu? | Kích hoạt như thế nào? |
| --- | --- | --- |
| XML + annotation | `@Transactional` trên Java class/method | `<tx:annotation-driven/>` trong XML context. |
| Java config + annotation | `@Transactional` trên Java class/method | `@EnableTransactionManagement` trên Java configuration hoặc auto-configuration tương thích. |
| XML advice theo pattern | `<tx:advice>` với `<tx:attributes>/<tx:method>` và AOP pointcut | `<aop:config>` gắn transaction advice vào method pattern. |
| Programmatic | `TransactionTemplate` hoặc `PlatformTransactionManager` trong code | Code chủ động điều phối transaction bằng API. |

**Điểm nổi bật của `<tx:annotation-driven/>` là bật giao dịch dựa trên annotation trong một ứng dụng XML.** Bạn không cần đồng thời viết `<tx:advice>`/`<aop:config>` chỉ để khiến `@Transactional` hoạt động.

Ví dụ XML declarative theo method pattern (chỉ để phân biệt, không cần cho demo ở trên):

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="save*" rollback-for="java.lang.Exception"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* demo.tx.*Service.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceMethods"/>
</aop:config>
```

Đây là **fragment XML**, cần namespace `aop`, datasource/manager và target class hợp lệ. Nó minh họa cách đặt rule **trong XML** thay vì annotation; không nên tùy tiện bật cùng lúc cả hai advisor lên đúng cùng method mà chưa hiểu chúng sẽ tương tác thế nào.

Trong Spring Boot thường có auto-configuration cho transaction management và infrastructure khi có đủ dependency/transaction manager; nhiều ứng dụng Boot dùng `@Transactional` mà không viết `<tx:annotation-driven/>`. Khi bảo trì ứng dụng XML, đừng sao chép máy móc cách bật của Boot và kết luận XML tag là thừa hoặc luôn bắt buộc. Cần xem context và cơ chế activation thật của ứng dụng đang chạy.

## 12. Debug và kiểm chứng cấu hình

Một quy trình xác minh có bằng chứng:

1. **Kiểm tra XML thật sự được load:** dùng `ClassPathXmlApplicationContext("spring-tx.xml")`, cấu hình root context hoặc cơ chế Spring phù hợp; chỉ để file XML trong resources chưa đủ.
2. **Xác nhận service là Spring bean:** lấy từ `ApplicationContext` hoặc inject bean; không tạo `new` trong caller.
3. **Xác nhận bean có AOP proxy:** trong môi trường debug, `AopUtils.isAopProxy(service)` có thể cho biết đối tượng nhận được là proxy AOP. Nó không tự chứng minh transaction rule đang đúng nhưng rất hữu ích để kiểm tra điều kiện proxy.
4. **Xác nhận manager:** kiểm tra tên bean trong XML và resource mà manager đang quản lý; chú ý khi có nhiều transaction manager.
5. **Xác nhận lời gọi đúng boundary:** public method được gọi **từ bên ngoài qua proxy**, không chỉ từ `this.method()`.
6. **Cố ý ném unchecked exception giữa hai write:** đọc kết quả sau method trả về/throw; nếu toàn bộ transaction đúng, cả hai write chưa commit sẽ rollback.
7. **Xem log transaction theo lớp thích hợp:** tìm dấu hiệu manager bắt đầu/tham gia và kết thúc transaction, chú ý call stack/exception.
8. **Kiểm tra tính nhất quán của resource:** DAO phải dùng datasource/persistence unit được manager điều phối; quan sát qua integration test.

Ví dụ một phép kiểm tra proxy nhỏ:

```java
import org.springframework.aop.support.AopUtils;

Object service = context.getBean("transferService");
System.out.println(AopUtils.isAopProxy(service));
```

Đây là **snippet minh họa**, `context` phải là Spring context đã khởi tạo. `true` xác nhận object là AOP proxy; cần phân tích thêm advisor/transaction và kết quả DB để chứng minh `@Transactional` thật sự hoạt động. Tên lớp proxy có thể thay đổi giữa môi trường/phiên bản, nên không assert theo chuỗi tên lớp.

Để chẩn đoán transaction trong một ứng dụng thực, có thể cấu hình log ở cấp `TRACE`/`DEBUG` cho `org.springframework.transaction` và `org.springframework.jdbc.datasource` trong môi trường thử nghiệm. Hạn chế log chi tiết trên production vì chi phí và dữ liệu nhạy cảm.

**Không dùng việc test method được gắn `@Transactional` làm bằng chứng duy nhất:** Spring Test có thể tự bắt đầu/rollback transaction của test, che giấu việc service chưa được proxy như dự kiến. Hãy kiểm tra service boundary và DB state ngoài test transaction thích hợp.

## 13. Bài tập tự kiểm tra

**Tình huống A — Chỉ thêm annotation.** Một project XML đã có `<context:component-scan>`, `JdbcTemplate`, `transactionManager`, nhưng chưa có `<tx:annotation-driven/>`. Developer thêm `@Transactional` vào service. Có chắc rollback xảy ra khi method ném exception?

**Đáp án:** Không. Trong context tối giản này, annotation chỉ là metadata; chưa đăng ký hạ tầng transaction annotation. Cần bật `<tx:annotation-driven/>` hoặc một cơ chế activation tương đương đang có thật.

**Tình huống B — Đổi tên transaction manager.** XML khai báo `<bean id="paymentTxManager" .../>` nhưng chỉ dùng `<tx:annotation-driven/>`. Vấn đề có thể là gì?

**Đáp án:** Element tìm bean manager mặc định tên `transactionManager` khi annotation không chỉ định manager. Nên khai báo `<tx:annotation-driven transaction-manager="paymentTxManager"/>`, kiểm tra manager tồn tại và khớp tài nguyên DAO.

**Tình huống C — Self-invocation.** `checkout()` gọi `this.pay()` cùng class, `pay()` gắn `@Transactional`, XML đã bật annotation-driven. Có tự động tạo transaction cho `pay()` không?

**Đáp án:** Với proxy mode mặc định, không vì `this.pay()` bỏ qua proxy. Chuyển transaction lên boundary ngoài hoặc tách sang bean khác.

**Tình huống D — Sai context.** `<tx:annotation-driven/>` nằm trong DispatcherServlet child context, service bean nằm trong root context. Service có được advice của child tự động wrap không?

**Đáp án:** Không. Hạ tầng chỉ xử lý bean thuộc context tương ứng. Cần cấu hình ở context tạo service.

**Tình huống E — Chọn `proxy-target-class="true"`.** Điều này có tự làm private method transactional không?

**Đáp án:** Không. Class-based proxy không thể override private method để intercept như public service method; đồng thời nó vẫn là proxy mode, nên self-invocation tiếp tục bỏ qua advice.

**Tình huống F — `mode="aspectj"`.** Có thể chỉ thêm thuộc tính này vào XML để làm self-invocation transactional không?

**Đáp án:** Không. Cần thực hiện AspectJ weaving và thêm dependency/config cần thiết; nếu chưa sẵn sàng, thiết kế service boundaries phù hợp với proxy mode thường đơn giản hơn.

**Tình huống G — Giao dịch nhiều datasource.** Có một manager của DB A, annotation được bật, nhưng service dùng JDBC template cho DB B. Spring có rollback cả hai DB không?

**Đáp án:** Không tự động. Manager local của A không điều phối B chỉ vì cùng một method `@Transactional`; cần cấu hình manager/resource chính xác và chiến lược nhiều tài nguyên riêng.

## 14. Tổng kết nguyên tắc cần nhớ

- `@Transactional` khai báo **điều kiện transaction**; `<tx:annotation-driven/>` bật **hạ tầng xử lý annotation** trong **đúng Spring context**.
- Element XML cần namespace `tx`/`spring-tx.xsd` và một `TransactionManager` thích hợp với hạ tầng data access; mặc định tên manager là `transactionManager`.
- `mode="proxy"` là mặc định: **chỉ lời gọi đi qua proxy** được chặn; self-invocation, constructor/init code và các giới hạn proxy không biến mất vì bật XML.
- `proxy-target-class` điều khiển loại proxy; `mode="aspectj"` là một cơ chế weaving riêng cần cấu hình bổ sung.
- Thuộc tính transaction của từng method nằm trên `@Transactional`; rollback mặc định dành cho unchecked exception/Error, không mặc định cho mọi checked exception.
- Với JDBC/JPA, phải dùng đúng datasource/persistence unit và manager; annotation không hợp nhất các resource độc lập.
- Cách xác minh chắc chắn nhất là một **integration scenario có cả commit và rollback**, đọc DB state sau khi transaction boundary kết thúc.

Nhớ sơ đồ: **XML namespace + `<tx:annotation-driven/>` → transaction proxy/interceptor → `@Transactional` metadata → đúng transaction manager → DAO dùng đúng tài nguyên → commit/rollback**.

## Nguồn tham khảo chính thức

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)