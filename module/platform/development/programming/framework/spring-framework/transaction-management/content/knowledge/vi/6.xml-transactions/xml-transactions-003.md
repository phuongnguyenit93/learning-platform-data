# Gắn transaction advice vào pointcut bằng AOP

## 1. Bài toán và mục tiêu

Trong Spring Framework, **declarative transaction management** cho phép khai báo ranh giới transaction bên ngoài code nghiệp vụ. Ngoài cách dùng `@Transactional`, ta có thể cấu hình toàn bộ transaction bằng **XML + Spring AOP**. Một service không cần có annotation vẫn được Spring bao bằng transaction nếu cấu hình AOP chính xác và lời gọi đi qua bean của Spring.

Bài học tập trung vào ba thành phần không thể nhầm lẫn:

- **Transaction advice:** `<tx:advice>` định nghĩa cách quản lý transaction và quy tắc propagation, isolation, read-only, timeout, rollback cho các method.
- **Pointcut:** `<aop:pointcut>` dùng biểu thức AspectJ `execution(...)` để chọn **method execution nào** được chặn.
- **Advisor:** `<aop:advisor>` **nối** transaction advice vào pointcut bằng `advice-ref` và `pointcut-ref`.

Có thêm **transaction manager** (ví dụ `DataSourceTransactionManager`) thực hiện commit/rollback với database. Nếu thiếu manager hoặc service dùng nhầm data source, advisor không thể tự bảo đảm tính nguyên tử.

Hình dung:

~~~text
           applicationContext.xml
    +------------------------------------+
    | <tx:advice id="txAdvice">          |
    |   <tx:method name="transfer".../>  |
    | </tx:advice>                       |
    |              |                     |
    |              v                     |
    | <aop:advisor                       |
    |   advice-ref="txAdvice"            |
    |   pointcut-ref="servicePointcut"/> |
    |              ^                     |
    |              |                     |
    | <aop:pointcut id="servicePointcut" |
    |   expression="execution(...)"/>    |
    +------------------------------------+
                  |
                  v
          Spring AOP proxy
                  |
    caller --> proxy.transfer(...)
                  |
         BEGIN hoặc join transaction
                  |
              target method
                  |
          COMMIT hoặc ROLLBACK
~~~

**Pointcut** là điều kiện “ở đâu?”, **advice** là quy tắc “làm gì?”, **advisor** là mối nối “áp dụng quy tắc vào đâu?”. Spring AOP mặc định dựa trên **proxy**; điểm gọi phải đi qua proxy do container quản lý.

## 2. Chọn phương thức và gắn advice: hai phép khớp riêng biệt

Ví dụ service chuyển 200 từ tài khoản A có 1.000 sang tài khoản B có 500. Hai lệnh SQL trừ A và cộng B phải cùng thành công hoặc cùng thất bại.

Cấu hình khái niệm:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="transfer" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="transferOperation"
        expression="execution(* com.example.xmltx.TransferService.transfer(..))"/>
    <aop:advisor advice-ref="txAdvice"
                 pointcut-ref="transferOperation"/>
</aop:config>
~~~

Để transaction được áp đúng:

1. **Pointcut** phải khớp method `TransferService.transfer(...)` được gọi qua proxy.
2. Trong `txAdvice`, phải có `tx:method` khớp **tên method** `transfer` để chọn transaction attributes.
3. `aop:advisor` phải trỏ đúng ID của cả advice và pointcut.
4. Advice phải chỉ đến transaction manager đúng, và manager phải quản lý đúng resource.

Hai cơ chế chọn này **khác nhau**. `execution(...)` kiểm tra chữ ký và loại Java; `tx:method name="transfer"` kiểm tra tên method để gán policy. Một advice chỉ có `<tx:method name="find*"/>` không cung cấp rule cho `transfer`. Một advice có `<tx:method name="*"/>` cũng không thể “cứu” lời gọi không khớp pointcut.

Khác với `<aop:before>` dùng cho logging, `tx:advice` cung cấp interceptor giao dịch chuyên biệt có hành vi **bao quanh** lời gọi: chuẩn bị transaction, gọi method, commit khi kết thúc đúng hoặc rollback theo rule khi xảy ra exception. Không cần tự viết `@Around` gọi JDBC `commit()`.

## 3. Ví dụ hoàn chỉnh chạy được bằng Java 17 và Maven

Ta tạo ứng dụng Spring Framework thuần, không cần Spring Boot, dùng Spring XML, Spring JDBC và H2 in-memory. Ví dụ chọn bộ phiên bản đã phát hành: Spring Framework **6.2.9**, AspectJ Weaver **1.9.24**, H2 **2.3.232**. Các khái niệm AOP/transaction vẫn áp dụng khi dự án dùng bản khác tương thích.

Cấu trúc thư mục:

~~~text
xml-transaction-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/xmltx/
        │   ├── TransferService.java
        │   └── XmlTxDemo.java
        └── resources/
            └── applicationContext.xml
~~~

### 3.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>xml-transaction-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.xmltx.XmlTxDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp Spring container và các module AOP/bean cần thiết thông qua dependency transitives; `spring-jdbc` cung cấp `JdbcTemplate` cùng transaction manager cho JDBC; `aspectjweaver` cho phép phân tích biểu thức AspectJ trong Spring AOP. **Thêm `aspectjweaver` không có nghĩa ứng dụng đang dùng bytecode weaving**: bài này vẫn hoạt động bằng proxy. H2 là database thử nghiệm chạy trong bộ nhớ JVM.

### 3.2. Java service không có annotation transaction

Tệp `src/main/java/com/example/xmltx/TransferService.java`:

~~~java
package com.example.xmltx;

import org.springframework.jdbc.core.JdbcTemplate;

public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void transfer(long fromId, long toId,
                         long amount, boolean failAfterDebit) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source missing or insufficient balance"
            );
        }

        // Chỉ phục vụ học: lỗi giữa hai UPDATE.
        if (failAfterDebit) {
            throw new IllegalStateException(
                "simulated error after debit"
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException(
                "Destination account does not exist"
            );
        }
    }
}
~~~

Service chỉ có constructor injection và mã nghiệp vụ. Nó **không sử dụng `@Transactional`**. Nếu XML áp đúng, cả hai `UPDATE` tham gia cùng transaction. Lỗi cố tình tạo **sau khi lệnh trừ A đã chạy**, vì vậy rollback phải đưa A trở lại 1.000; đây là phép thử thực tế cho transaction advice.

`JdbcTemplate.update` trả về số hàng cập nhật. Các điều kiện kiểm tra nguồn, đích và `balance >= ?` giúp tránh chấp nhận một thao tác chuyển tiền bị thiếu hàng hoặc trừ vượt số dư. Demo dùng đơn vị nguyên cho tiền, không phải thiết kế tài chính production.

### 3.3. XML đầy đủ: transaction manager, tx:advice, pointcut, advisor

Tệp `src/main/resources/applicationContext.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- Cùng DataSource được dùng trong cả service và transaction. -->
    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url"
                  value="jdbc:h2:mem:xml_tx_lab;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="transferService"
          class="com.example.xmltx.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <!-- Quy tắc giao dịch cho method tên transfer. -->
    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="transfer" propagation="REQUIRED"
                       isolation="DEFAULT"/>
        </tx:attributes>
    </tx:advice>

    <!-- AOP pointcut và advisor gắn transaction advice. -->
    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
            expression="execution(public * com.example.xmltx.TransferService.transfer(..))"/>
        <aop:advisor pointcut-ref="transferOperation"
                     advice-ref="txAdvice"/>
    </aop:config>
</beans>
~~~

Đọc từng phần:

1. `dataSource` dùng H2 in-memory. `DriverManagerDataSource` phù hợp bài demo, nhưng môi trường thực tế nên có connection pool.
2. `jdbcTemplate` dùng `dataSource` để truy cập dữ liệu.
3. `txManager` là `DataSourceTransactionManager`, **quản lý cùng bean `dataSource`**. Transaction advice tham chiếu đúng ID `txManager` bằng `transaction-manager="txManager"`.
4. `transferService` được tạo bởi Spring container. Nếu caller tự dùng `new TransferService(...)` thì sẽ không qua AOP proxy.
5. `txAdvice` có rule `name="transfer"`: trong transaction context, `REQUIRED` tham gia transaction hiện hữu hoặc tạo mới; `DEFAULT` dùng isolation mặc định của database.
6. `transferOperation` là pointcut chọn đúng public method `transfer(...)` trong class được đặt tên đầy đủ.
7. `aop:advisor` gắn `txAdvice` vào `transferOperation`. Đây chính là bước nối trọng tâm bài.
8. `proxy-target-class="true"` yêu cầu class-based proxy, nên có thể lấy bean bằng `TransferService.class`. Class và method không được đặt `final` nếu muốn class proxy can thiệp.

**Cần ghi nhớ:** `<tx:advice>` là phần tử thuộc namespace `tx` ở cấp `beans`, còn `<aop:pointcut>` và `<aop:advisor>` đặt bên trong `<aop:config>`. Các ID là **tên bean/phần tử cấu hình**, không phải tên Java class.

### 3.4. Chương trình quan sát commit và rollback

Tệp `src/main/java/com/example/xmltx/XmlTxDemo.java`:

~~~java
package com.example.xmltx;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class XmlTxDemo {
    public static void main(String[] args) {
        try (var context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {
            JdbcTemplate jdbc = context.getBean(
                "jdbcTemplate", JdbcTemplate.class
            );
            TransferService service = context.getBean(
                "transferService", TransferService.class
            );

            if (!AopUtils.isAopProxy(service)) {
                throw new AssertionError("Service is not AOP-proxied");
            }

            jdbc.execute(
                "CREATE TABLE account (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL CHECK (balance >= 0))"
            );
            jdbc.update(
                "INSERT INTO account(id, balance) VALUES (?, ?)",
                1L, 1000L
            );
            jdbc.update(
                "INSERT INTO account(id, balance) VALUES (?, ?)",
                2L, 500L
            );

            printBalances(jdbc, "Initial");

            try {
                service.transfer(1L, 2L, 200L, true);
                throw new AssertionError("Expected failure");
            } catch (IllegalStateException expected) {
                if (!"simulated error after debit"
                        .equals(expected.getMessage())) {
                    throw expected;
                }
                System.out.println("Caught: " + expected.getMessage());
            }

            assertBalances(jdbc, 1000L, 500L);
            printBalances(jdbc, "After rollback");

            service.transfer(1L, 2L, 200L, false);
            assertBalances(jdbc, 800L, 700L);
            printBalances(jdbc, "After commit");
        }
    }

    private static long balance(JdbcTemplate jdbc, long id) {
        Long v = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class, id
        );
        if (v == null) {
            throw new IllegalStateException("Missing account " + id);
        }
        return v;
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        System.out.printf(
            "%s: A=%d, B=%d%n",
            label, balance(jdbc, 1L), balance(jdbc, 2L)
        );
    }

    private static void assertBalances(JdbcTemplate jdbc,
                                       long expectedA, long expectedB) {
        long a = balance(jdbc, 1L);
        long b = balance(jdbc, 2L);
        if (a != expectedA || b != expectedB) {
            throw new AssertionError(
                "Expected A=" + expectedA + ", B=" + expectedB +
                "; actual A=" + a + ", B=" + b
            );
        }
    }
}
~~~

Lệnh `AopUtils.isAopProxy(service)` kiểm tra bean có proxy, nhưng **chỉ kiểm tra proxy là chưa đủ** để chứng minh riêng method `transfer` được transaction-advised. Phép thử exception xảy ra **sau một SQL ghi thành công**, tiếp theo là đọc dữ liệu sau lời gọi service, mới là bằng chứng chính xác.

### 3.5. Chạy với Maven

Yêu cầu JDK 17+ và Maven 3.9+:

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

Nếu Maven tải dependency và ứng dụng chạy đúng, các dòng do chương trình in sẽ là:

~~~text
Initial: A=1000, B=500
Caught: simulated error after debit
After rollback: A=1000, B=500
After commit: A=800, B=700
~~~

Thời gian, thông báo Maven và log nội bộ có thể thay đổi; bốn dòng trên là phần output **do Java code quy định**. Các `assertBalances` sẽ ném `AssertionError` nếu dữ liệu không khớp.

Tại lần thử lỗi, A đã bị trừ thành 800 **bên trong transaction** trước khi exception xuất hiện. Sau khi advice yêu cầu rollback, đọc từ ngoài method thấy A trở lại 1.000. Lần sau không có lỗi, cả hai lệnh chạy rồi transaction commit: A = 800, B = 700.

## 4. Phân tích đầy đủ lời gọi AOP

Luồng cho `service.transfer(1L, 2L, 200L, true)`:

~~~text
XmlTxDemo lấy transferService từ Spring context
             |
             v
Spring AOP proxy nhận lời gọi transfer(...)
             |
             +-- Pointcut execution(...) khớp
             +-- Advisor dẫn tới txAdvice
             +-- tx:method name="transfer" chọn quy tắc
             |
             v
TransactionInterceptor gọi txManager
             |
             +-- REQUIRED: bắt đầu transaction mới
             |              (vì demo chưa có transaction ngoài)
             v
Target TransferService.transfer(...)
             |
             +-- JdbcTemplate UPDATE tài khoản A
             |      (A=800, chưa commit)
             +-- throw IllegalStateException
             |
             v
Interceptor xác định exception thuộc rule rollback
             |
             v
DataSourceTransactionManager.rollback(...)
             |
             v
Caller nhận exception; đọc lại A=1000, B=500
~~~

Với lời gọi `failAfterDebit=false`, target trả về bình thường và transaction interceptor yêu cầu commit.

Trong ứng dụng thực tế, `REQUIRED` cũng có thể **tham gia transaction đã tồn tại**. Khi đó service method trả về chưa chắc là thời điểm commit: ranh giới transaction phía ngoài quyết định. Transaction manager JDBC quản lý connection và ngữ cảnh transaction; `JdbcTemplate` tham gia nhờ dùng cùng `DataSource`.

**Quan hệ với tính nguyên tử:** advisor/pointcut chỉ quyết định transaction **có bao quanh method không**; engine database mới thực thi cơ chế commit/rollback, logging và lock thực tế. AOP không thay thế ACID của database.

## 5. Hiểu cú pháp pointcut execution(...)

Biểu thức trong XML:

~~~xml
expression="execution(public * com.example.xmltx.TransferService.transfer(..))"
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `execution(...)` | Chọn join point tại việc thực thi method. |
| `public` | Chỉ method có phạm vi public. |
| `*` | Bất kỳ kiểu trả về nào, kể cả `void`. |
| `com.example.xmltx.TransferService` | Tên đầy đủ của class Java. |
| `transfer` | Tên method cần bắt. |
| `(..)` | Bất kỳ số lượng và kiểu tham số. |

Đổi tên package, class hoặc method mà không sửa biểu thức sẽ làm advisor không còn khớp như dự định.

Một số pointcut khác, **chỉ dùng như minh họa, không thêm đồng thời vào cấu hình lab**:

~~~xml
<!-- Tất cả public method của class tên *Service trong package service -->
<aop:pointcut id="serviceMethods"
    expression="execution(public * com.example.app.service.*Service.*(..))"/>

<!-- Bao gồm cả package con bên dưới service -->
<aop:pointcut id="nestedServices"
    expression="execution(* com.example.app.service..*Service.*(..))"/>

<!-- Chỉ method tên save* trong một tầng package -->
<aop:pointcut id="saveOperations"
    expression="execution(* com.example.app.service.*.save*(..))"/>
~~~

Dấu `..` ở phần package có thể bao gồm nhiều cấp subpackage; `(..)` trong danh sách tham số có nghĩa là chấp nhận mọi tham số. Đừng chọn vô tình cả lớp repository, utility và getter khi nghiệp vụ chỉ cần transaction ở service layer.

Nếu phải kết hợp điều kiện trong một thuộc tính XML, dùng từ khóa AspectJ `and` hoặc escape `&&` thành `&amp;&amp;` để XML hợp lệ.

### Interface proxy và class proxy

Spring AOP có thể tạo **JDK dynamic proxy** khi bean có interface hoặc **class-based proxy**. Trong lab, `proxy-target-class="true"` được dùng để proxy class `TransferService`, do đó caller lấy bean bằng class này được. Với JDK proxy, caller nên lấy bean qua interface do proxy triển khai; cast về implementation có thể thất bại.

Dù loại proxy nào, self-invocation (`this.someMethod()`) trong cùng target **không đi qua proxy** ở mô hình Spring AOP thông thường. Class/method final cũng là giới hạn đối với proxy dựa trên subclassing. Khi chọn pointcut, luôn đối chiếu với loại proxy thực tế và đường đi của lời gọi.

## 6. Transaction attributes: điều gì có thể cấu hình trong tx:method?

Một service lớn có thể có nhiều quy tắc method. Ví dụ **thay thế** `txAdvice` trong lab bằng cấu hình:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"
                   propagation="SUPPORTS"/>
        <tx:method name="get*" read-only="true"
                   propagation="SUPPORTS"/>
        <tx:method name="transfer*" propagation="REQUIRED"
                   rollback-for="java.lang.Exception"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
~~~

| Thuộc tính | Vai trò |
| --- | --- |
| `name` | Mẫu tên method (`transfer*`, `get*`, `*`); đây là rule **bên trong advice**. |
| `propagation` | Cách tham gia hoặc tạo transaction, ví dụ `REQUIRED` và `SUPPORTS`. |
| `isolation` | Mức cô lập yêu cầu khi transaction mới được tạo, ví dụ `DEFAULT`, `READ_COMMITTED`. |
| `read-only` | Hint cho transaction manager/driver/engine; không phải bảo đảm cấm mọi câu UPDATE. |
| `rollback-for` | Loại exception cần rollback bổ sung, đặc biệt checked exception. |
| `no-rollback-for` | Loại exception không yêu cầu rollback dù có lỗi; chỉ dùng khi nghiệp vụ cho phép. |
| `timeout` | Giới hạn thời gian transaction khi manager/engine hỗ trợ. |

Spring mặc định yêu cầu rollback khi `RuntimeException` hoặc `Error` thoát khỏi transaction method; checked exception không mặc định kích hoạt rollback. Nếu nghiệp vụ muốn rollback khi có `IOException`, cấu hình `rollback-for="java.io.IOException"` hoặc một loại cha phù hợp. Đừng thêm `rollback-for="java.lang.Exception"` chỉ vì muốn “mọi thứ chắc chắn”: hãy xác định rõ trạng thái mong muốn khi checked exception xảy ra.

**Lưu ý hai cấp chọn:** `name="get*"` không tự thêm `getBalance()` vào pointcut. Nếu pointcut hiện tại chỉ match `transfer`, getter vẫn nằm ngoài advisor đó, ngay cả khi advice khai báo rule `get*`. Ngược lại, pointcut có thể match method nhưng rule advice không khớp tên method.

**Propagation:** `REQUIRED` (mặc định) tham gia transaction hiện hữu nếu có, hoặc tạo mới. `SUPPORTS` tham gia nếu đã có, còn không thì không tự tạo transaction. `REQUIRES_NEW` tạo một transaction độc lập (khi manager hỗ trợ); commit độc lập có thể làm mất tính nguyên tử tổng thể nếu dùng sai trong use case chuyển tiền.

## 7. XML AOP advice khác cấu hình tx:annotation-driven

**Cấu hình đang học** tự định nghĩa pointcut và advisor:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="transfer" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
<aop:config proxy-target-class="true">
    <aop:pointcut id="transferOperation"
        expression="execution(public * com.example.xmltx.TransferService.transfer(..))"/>
    <aop:advisor pointcut-ref="transferOperation"
                 advice-ref="txAdvice"/>
</aop:config>
~~~

**Cấu hình dựa trên annotation** là cơ chế khác:

~~~xml
<tx:annotation-driven transaction-manager="txManager"/>
~~~

~~~java
@Transactional
public void transfer(/* tham số */) {
    // Method thuộc Spring bean.
}
~~~

Đoạn Java annotation trên chỉ minh họa ý tưởng, không phải chương trình độc lập có thể biên dịch. Với `tx:annotation-driven`, Spring đọc transaction attributes từ `@Transactional`. Với `tx:advice + aop:advisor`, Spring dùng pointcut và rule XML; **Java service có thể hoàn toàn không có annotation**.

Không bật đồng thời hai cơ chế cho cùng service một cách tùy tiện: advisor ordering và việc bao transaction nhiều lớp có thể gây hành vi khó hiểu. Khi hệ thống đã dùng XML transaction advice, hãy xác định source of truth cho transaction policy trước khi thêm `@Transactional` hoặc `tx:annotation-driven`.

## 8. Thử thay đổi XML để xác nhận advisor có tác dụng

Chỉ thực hiện các phản chứng trong **bản sao lab**:

| Thay đổi | Kết quả/ý nghĩa dự kiến |
| --- | --- |
| Bỏ `<aop:advisor .../>`, giữ nguyên `txAdvice` | Advice tồn tại nhưng không được nối với pointcut; `transfer` không có transaction do advisor đó áp vào. |
| Đổi pointcut thành một tên method không tồn tại | Không match `transfer`, nên lời gọi có thể không được proxy bởi advisor này. |
| Giữ pointcut nhưng thay `tx:method name="transfer"` thành chỉ `name="find*"` | Lời gọi match pointcut nhưng thiếu transaction attribute cho `transfer`. |
| Khôi phục XML chuẩn | Lỗi sau UPDATE A được rollback; A = 1.000, B = 500. |
| Mở rộng pointcut lên toàn service layer | Nhiều method có thể được chọn hơn; kiểm tra riêng từng rule và ranh giới nghiệp vụ. |

**Điểm thận trọng trong phản chứng:** `XmlTxDemo` cố ý kiểm tra `AopUtils.isAopProxy(service)`. Nếu bỏ advisor làm mất proxy, chương trình dừng trước khi chạy SQL. Muốn tận mắt nhìn hậu quả auto-commit, chỉ trên bản sao lab hãy tạm bỏ phép kiểm tra proxy đó rồi thực thi lại; sau đó khôi phục cả assertion lẫn advisor. Trong cấu hình H2 của lab, nếu `UPDATE` đầu đã commit riêng trước exception, A sẽ còn 800, B = 500 và phép kiểm tra sau lỗi thất bại. Không thử kiểu này trên dữ liệu thật.

Không dùng riêng việc context khởi động thành công làm bằng chứng transaction đã đúng. Test tốt phải gây lỗi **sau ít nhất một UPDATE**, rồi đọc lại database **sau khi lời gọi proxy kết thúc**.

## 9. Lỗi phổ biến và cách sửa nguyên nhân

### 9.1. Sai ID hoặc bỏ transaction-manager

`transaction-manager="txManager"` phải trỏ đúng bean transaction manager. Nếu bỏ thuộc tính này, tên manager mặc định mà XML transaction advice tìm là `transactionManager`. Trong lab bean tên `txManager` nên không được bỏ phần tham chiếu đó. Dùng `DataSourceTransactionManager` với **cùng DataSource** mà `JdbcTemplate` sử dụng.

### 9.2. Thiếu dependency AOP hoặc namespace XML

`<tx:advice>` cần namespace `tx` và schema `spring-tx.xsd`; `<aop:config>` cần namespace `aop` và schema `spring-aop.xsd`. Biểu thức `execution(...)` cần khả năng phân tích pointcut AspectJ. Lỗi phân giải XML, thiếu class hoặc parse pointcut thường do namespace, classpath, dependencies hoặc biểu thức sai.

### 9.3. Advice, pointcut và advisor không khớp

Khi transaction không kích hoạt, kiểm tra **cùng lúc** tên class/method trong pointcut, tên method trong `tx:method`, `pointcut-ref`, `advice-ref`, transaction manager và đường đi proxy. Đây là lỗi điển hình khi người ta đã khai báo transaction advice nhưng quên gắn advisor.

### 9.4. Tạo service bằng new hoặc self-invocation

~~~java
// Minh họa việc bỏ qua Spring AOP proxy; không phải tệp của lab.
TransferService s = new TransferService(jdbc);
s.transfer(1L, 2L, 200L, true);
~~~

Dùng `new` tạo instance ngoài container nên advice không được áp qua proxy. Tương tự, lời gọi `this.transfer(...)` từ method khác trong cùng target thường bypass interceptor. Hãy để bean khác gọi public service method thông qua Spring.

### 9.5. Nuốt exception giữa transaction

Nếu method bắt `RuntimeException` sau khi ghi SQL rồi kết thúc bình thường, advice có thể commit dữ liệu trung gian nếu transaction chưa bị đánh dấu rollback-only. Thực tế cần ném lại exception hoặc chủ động đánh dấu rollback theo policy nghiệp vụ. Không giả định “đã có exception trong try-catch” là đủ.

### 9.6. Nhầm read-only và isolation

`read-only="true"` chủ yếu là thuộc tính/hint mà transaction manager và driver/engine có thể tận dụng; nó không thay thế quyền truy cập database. `isolation="READ_COMMITTED"` chỉ yêu cầu mức cô lập khi mở transaction mới; nếu method tham gia transaction có sẵn, không thể kết luận nó tự đổi isolation hiện hành. Các hành vi locking/MVCC còn phụ thuộc database.

### 9.7. Transaction ngoài database

Một local JDBC transaction không tự hoàn tác email, HTTP call, message đã publish hay ghi ở database khác. Nếu use case cần phối hợp nhiều tài nguyên, phải thiết kế riêng, ví dụ transactional outbox, idempotency hoặc saga khi phù hợp. AOP advisor không tự biến một giao dịch đơn nguồn thành distributed transaction.

## 10. Kiểm tra và debug cho hệ thống hiện hữu

Ngoài kết quả chạy lab, các kiểm tra có ích trong một ứng dụng thực tế:

1. Xác nhận bean được lấy từ đúng Spring application context và có proxy nếu cần: `AopUtils.isAopProxy(bean)`.
2. Đặt breakpoint tại service method; quan sát caller có đi qua proxy hay gọi trực tiếp bằng `this/new`.
3. Kiểm tra pointcut match signature (đúng package, class, tên method, public/final), rồi kiểm tra `tx:method` match tên.
4. Xác nhận transaction manager được advice tham chiếu và `DataSource` của service giống resource manager quản lý.
5. Trong môi trường thử nghiệm, có thể quan sát `TransactionSynchronizationManager.isActualTransactionActive()` ở bên trong method; đây là tín hiệu debug, không thay cho test rollback.
6. Chủ động tạo exception sau lệnh ghi đầu tiên; **đọc lại giá trị từ ngoài transaction** sau khi proxy hoàn tất. Nếu dữ liệu gốc được khôi phục, bạn có bằng chứng về rollback thực tế.
7. Khi nhiều advisor/aspect cùng áp vào một method, kiểm tra thứ tự advice (`order`) và ranh giới transaction. Không suy đoán chỉ dựa trên tên proxy.

Một proxy có thể tồn tại mà method cụ thể chưa được áp `txAdvice`. Vì vậy **kết quả rollback sau lỗi mới là phép thử có giá trị quyết định**.

## 11. Tự kiểm tra

1. **Khai báo `tx:advice` và `aop:pointcut` nhưng không khai báo `aop:advisor` được không?** — Các thành phần chưa được nối; cấu hình đó không tự áp transaction vào method.
2. **Pointcut `execution(...)` khác `tx:method name="..."` ở đâu?** — Pointcut chọn lời gọi method theo chữ ký; `tx:method` chọn transaction attributes dựa trên tên method đã được advice xử lý.
3. **Ai gọi commit hoặc rollback?** — Transaction interceptor phối hợp với transaction manager, ví dụ `DataSourceTransactionManager`.
4. **Tại sao class Java ở ví dụ không cần `@Transactional`?** — XML transaction advice + AOP advisor đã mô tả policy bao quanh lời gọi qua Spring proxy.
5. **Nếu chỉ sửa package Java và quên pointcut, điều gì có thể xảy ra?** — Pointcut không còn khớp method, transaction advice không được áp vào lời gọi.
6. **Vì sao dùng `aspectjweaver` nhưng nói ví dụ không dùng weaving?** — Spring AOP proxy dùng thư viện để phân tích pointcut expression; không phải bật compile/load-time bytecode weaving.
7. **Lời gọi `this.transfer(...)` từ cùng target có qua transaction interceptor không?** — Thông thường không trong proxy mode, nên không tự tạo ranh giới transaction mới.
8. **`REQUIRED` có chắc commit khi method con trả về không?** — Không nếu đang tham gia transaction của caller; transaction ngoài quyết định commit.
9. **Vì sao test lỗi phải chạy sau một UPDATE?** — Để chứng minh dữ liệu đã thay đổi trung gian được hoàn tác; lỗi trước mọi SQL chưa chứng minh rollback có hiệu quả.
10. **Có thể chỉ cần `read-only="true"` để bảo vệ không cho update không?** — Không. Cần quyền database và quy tắc nghiệp vụ; read-only là một transaction attribute/hint.

## 12. Kết luận và bảng ghi nhớ

| Cấu hình | Trả lời câu hỏi |
| --- | --- |
| `<bean id="txManager">` | Ai quản lý transaction trên resource nào? |
| `<tx:advice id="txAdvice">` | Transaction có propagation/isolation/rollback rule nào? |
| `<tx:method name="transfer">` | Rule nào áp cho tên method? |
| `<aop:pointcut expression="execution(...)">` | Method execution nào được chọn? |
| `<aop:advisor pointcut-ref="..." advice-ref="...">` | Nối advice với tập method đã chọn ra sao? |
| Spring AOP proxy | Lời gọi vào service có đi qua interceptor không? |

**Ghi nhớ:** XML transaction management hoạt động khi **pointcut chọn đúng method**, **transaction advice có rule phù hợp**, **advisor nối hai thành phần**, và **transaction manager sử dụng đúng resource**. Khi caller gọi qua proxy, Spring bao quanh method bằng transaction, còn database bảo đảm commit/rollback. Đây là cách gắn transaction advice vào pointcut bằng AOP một cách tường minh, kiểm chứng được bằng dữ liệu sau lỗi.

### Tài liệu tham khảo chính thức

- [Spring Framework — Example of Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/applying-more-than-just-tx-advice.html)