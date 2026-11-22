# Đối chiếu cấu hình XML với annotation cho cùng hành vi giao dịch trong Spring Framework

Một ứng dụng Spring có thể dùng **XML** hoặc **annotation Java** để khai báo ranh giới giao dịch. Hai cấu hình chỉ thật sự tương đương khi cùng **chọn một nhóm method**, cùng **TransactionManager và tài nguyên dữ liệu**, cùng **propagation/isolation/timeout/read-only/rollback rule**, và cho kết quả **commit hoặc rollback giống nhau** khi chạy qua Spring proxy.

Bài này tập trung vào cơ chế transaction declarative của **Spring Framework**, với chủ đề chính là **đối chiếu XML và annotation cho cùng hành vi**. Phần thực hành sử dụng Java 17+, Spring JDBC, H2 và một service chuyển tiền để so sánh hai hướng cấu hình mà không cần server database bên ngoài.

## 1. Có ba cấp độ cấu hình cần phân biệt

| Mục đích | XML | Java/annotation | Mối quan hệ |
| --- | --- | --- | --- |
| Khai báo bean và dependency | bean, constructor-arg, property | @Configuration, @Bean, constructor injection | Tạo cùng đối tượng |
| Khai báo transaction manager | Bean JdbcTransactionManager/DataSourceTransactionManager | @Bean PlatformTransactionManager | Chỉ định cùng một transaction resource |
| Chỉ định transaction policy theo pointcut | tx:advice, tx:method, aop:pointcut và aop:advisor | @Transactional trên method/class | Hai cách mô tả cùng hành vi giao dịch |
| Bật xử lý annotation | tx:annotation-driven | @EnableTransactionManagement | Hai cách kích hoạt việc đọc @Transactional |
| Chọn class-based proxy | proxy-target-class="true" trong cấu hình AOP/tx XML | proxyTargetClass=true trên @EnableTransactionManagement | Chọn cách tạo proxy trong proxy mode |

Điểm dễ nhầm: **tx:annotation-driven tương đương với @EnableTransactionManagement ở nhiệm vụ kích hoạt xử lý annotation**, chứ **không phải** một cách viết khác của chính @Transactional. Ngược lại, **tx:advice** khai báo policy trong XML; **aop:advisor** gắn policy đó với một pointcut chọn method. Không cần có @Transactional trên source Java nếu XML advice thuần đã được cấu hình đúng.

Sơ đồ:

~~~text
Caller -> Spring AOP proxy -> TransactionInterceptor
                                  |
                       transaction attributes
                         /               \
                   XML tx:method     @Transactional
                         \               /
                          TransactionManager
                                |
                  DataSource -> JDBC Connection -> DBMS
                                |
                       commit / rollback / cleanup
~~~

Spring AOP có thể tạo proxy và gọi cùng một TransactionInterceptor cho hai nguồn metadata. **Database thực thi transaction thực tế**; XML/annotation chỉ điều khiển cách Spring chọn và áp dụng transaction policy.

## 2. Đặt chuẩn so sánh: cùng bài toán, cùng chính sách

Giả sử có bảng wallet:

| id | balance ban đầu |
| --- | ---: |
| 1 (A) | 100 |
| 2 (B) | 100 |

Phương thức **transfer(boolean fail)** sẽ:

1. Trừ 10 từ A bằng SQL UPDATE.
2. Cộng 10 vào B bằng SQL UPDATE.
3. Nếu fail=false, kết thúc bình thường để Spring commit.
4. Nếu fail=true, ném IllegalStateException sau cả hai UPDATE để Spring rollback.

Hợp đồng mong muốn:

| Thuộc tính | Giá trị giống nhau cho cả hai |
| --- | --- |
| TransactionManager | Bean tên transactionManager, kiểu JdbcTransactionManager |
| DataSource | H2 JDBC; manager và JdbcTemplate dùng cùng DataSource trong từng context |
| Transaction boundary | Method public transfer(boolean) được gọi qua bean proxy |
| Propagation | REQUIRED |
| Isolation | READ_COMMITTED |
| Timeout | 10 giây |
| Read-only | false |
| Rollback rule | IllegalStateException làm rollback khi thoát khỏi method |
| Proxy | Class-based proxy |
| Quan sát thành công | A=90, B=110 |
| Quan sát sau lỗi | A=90, B=110 vì lần cập nhật bị rollback |

Timeout/READ_COMMITTED ở đây phục vụ ví dụ; chúng chỉ có hiệu lực theo manager và DBMS hỗ trợ. Trong thực tế hãy chọn policy theo yêu cầu nhất quán của nghiệp vụ.

## 3. Cách thứ nhất: cấu hình thuần XML bằng tx:advice và aop:advisor

File XML sau khai báo bốn bean và một advisor:

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

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xml_demo;DB_CLOSE_DELAY=-1"/>
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

    <bean id="transferService" class="demo.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="transferTxAdvice"
               transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="transfer"
                       propagation="REQUIRED"
                       isolation="READ_COMMITTED"
                       timeout="10"
                       read-only="false"
                       rollback-for="java.lang.IllegalStateException"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
                      expression="execution(* demo.TransferService.transfer(..))"/>
        <aop:advisor advice-ref="transferTxAdvice"
                     pointcut-ref="transferOperation"/>
    </aop:config>
</beans>
~~~

Để hiểu cấu hình:

- **bean dataSource** cung cấp JDBC Connection; **jdbcTemplate** và **transactionManager** cùng tham chiếu tới nó. Đây là điều kiện để JDBC statements tham gia local transaction do Spring quản lý.
- **tx:advice** định nghĩa *thao tác transaction cần áp dụng* (propagation, isolation, timeout, rollback...). Nó chưa chọn nơi áp dụng.
- **tx:method name="transfer"** chọn nhóm method theo **tên** trong các method mà pointcut đã lựa chọn. Có thể dùng name="get*", name="save*" hay name="*" khi thật sự muốn bao phủ các nhóm đó.
- **aop:pointcut** quy định *method execution nào* được chọn; biểu thức ở đây chỉ nhắm tới **demo.TransferService.transfer(..)**.
- **aop:advisor** liên kết advice với pointcut. Nếu thiếu nó, khai báo transaction attributes không tự tạo bao bọc method được yêu cầu.
- **proxy-target-class="true"** chọn class-based proxy (CGLIB) để tương thích với service không dựa trên interface; proxy mode vẫn có giới hạn self-invocation.

Đặc biệt, policy nằm trong XML, nên lớp demo.TransferService được viết như POJO **không có @Transactional**. Nhưng phải thực sự nạp file XML vào ApplicationContext và gọi service từ bean do Spring quản lý.

## 4. Cách thứ hai: @Transactional và @EnableTransactionManagement

Thay vì chọn method qua pointcut trong XML, ta gắn policy trên method Java:

~~~java
@Transactional(
        transactionManager = "transactionManager",
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = false,
        rollbackFor = IllegalStateException.class)
public void transfer(boolean fail) {
    // Thực thi cùng logic UPDATE như bản XML.
}
~~~

Đây là **đoạn trích**; muốn code độc lập phải có class, imports, DataSource và Spring context. Tham số của annotation tương đương:

| XML tx:method | Annotation Java |
| --- | --- |
| propagation="REQUIRED" | propagation = Propagation.REQUIRED |
| isolation="READ_COMMITTED" | isolation = Isolation.READ_COMMITTED |
| timeout="10" | timeout = 10 |
| read-only="false" | readOnly = false |
| rollback-for="java.lang.IllegalStateException" | rollbackFor = IllegalStateException.class |
| transaction-manager="transactionManager" trên tx:advice | transactionManager = "transactionManager" trên @Transactional |

Bean được tạo bằng @Configuration/@Bean; @EnableTransactionManagement kích hoạt annotation-driven proxy:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(proxyTargetClass = true)
public class JavaConfig {
    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:annotation_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public AnnotatedTransferService transferService(JdbcTemplate jdbc) {
        return new AnnotatedTransferService(jdbc);
    }
}
~~~

Đoạn cấu hình này được trình bày đầy đủ cùng imports ở phần chạy thực tế. **@EnableTransactionManagement là bước bật hạ tầng**, còn **@Transactional là policy**. Nếu ứng dụng dùng Spring Boot, transaction infrastructure có thể đã được tự cấu hình; cần kiểm tra thực tế trước khi thêm cấu hình chồng lên.

Hai URL H2 dùng tên database khác nhau để chạy hai lần độc lập với dữ liệu khởi tạo giống nhau. Đây không phải khác biệt transaction cần so sánh.

## 5. Ví dụ chạy được bằng Java 17+, Maven và H2

Phần này tạo một chương trình Spring Framework không cần Spring Boot. Dùng cùng **thân code nghiệp vụ** cho hai cấu hình bằng cách cho class annotated kế thừa class không annotation và gọi super.transfer(...). Vì vậy chỉ nguồn transaction metadata thay đổi.

Cấu trúc thư mục:

~~~text
transaction-config-compare/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── TransferService.java
    │   ├── AnnotatedTransferService.java
    │   ├── JavaConfig.java
    │   └── ComparisonDemo.java
    └── resources/
        └── tx-xml.xml
~~~

### 5.1. Dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-config-compare</artifactId>
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
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                    <mainClass>demo.ComparisonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**AspectJ Weaver** ở classpath phục vụ xử lý biểu thức pointcut XML trong cơ chế Spring AOP; ví dụ vẫn đang ở **proxy mode**, không yêu cầu bytecode weaving AspectJ cho transaction.

### 5.2. Logic nghiệp vụ duy nhất

**src/main/java/demo/TransferService.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void transfer(boolean fail) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("No active Spring transaction");
        }

        int debited = jdbc.update(
                "UPDATE wallet SET balance = balance - 10 WHERE id = ?", 1);
        int credited = jdbc.update(
                "UPDATE wallet SET balance = balance + 10 WHERE id = ?", 2);

        if (debited != 1 || credited != 1) {
            throw new IllegalStateException("Wallet row missing");
        }

        if (fail) {
            throw new IllegalStateException("simulated failure");
        }
    }
}
~~~

Ở XML context, advisor chọn method **TransferService.transfer** này. Trong annotation context, method được override có @Transactional, sau đó gọi chính phần code trên qua super.transfer(fail). Cả hai biến thể vì vậy dùng hai SQL giống nhau.

Lệnh isActualTransactionActive() giúp phát hiện method chạy ngoài Spring transaction trong demo; nó **không** thay thế việc kiểm chứng DB sau commit. Chú ý với JDBC imperative, transaction context thường gắn với thread. Không giả định gọi qua thread @Async sẽ tự tham gia transaction.

### 5.3. File XML chạy thật

Lưu đúng file **src/main/resources/tx-xml.xml**:

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

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xml_demo;DB_CLOSE_DELAY=-1"/>
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

    <bean id="transferService" class="demo.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="transferTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="transfer"
                       propagation="REQUIRED"
                       isolation="READ_COMMITTED"
                       timeout="10"
                       read-only="false"
                       rollback-for="java.lang.IllegalStateException"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
                      expression="execution(* demo.TransferService.transfer(..))"/>
        <aop:advisor advice-ref="transferTxAdvice"
                     pointcut-ref="transferOperation"/>
    </aop:config>
</beans>
~~~

### 5.4. Service annotation

**src/main/java/demo/AnnotatedTransferService.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public class AnnotatedTransferService extends TransferService {
    public AnnotatedTransferService(JdbcTemplate jdbc) {
        super(jdbc);
    }

    @Override
    @Transactional(
            transactionManager = "transactionManager",
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED,
            timeout = 10,
            readOnly = false,
            rollbackFor = IllegalStateException.class)
    public void transfer(boolean fail) {
        super.transfer(fail);
    }
}
~~~

Phương thức override là **public, không final** và được gọi từ ngoài thông qua Spring bean; interceptor mở transaction trước khi nó gọi logic ở lớp cha. Không cần gắn @Transactional lên lớp cha trong nhánh XML.

### 5.5. Java configuration hoàn chỉnh

**src/main/java/demo/JavaConfig.java**

~~~java
package demo;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(proxyTargetClass = true)
public class JavaConfig {
    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:annotation_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public AnnotatedTransferService transferService(JdbcTemplate jdbc) {
        return new AnnotatedTransferService(jdbc);
    }
}
~~~

### 5.6. Chạy hai phương án

**src/main/java/demo/ComparisonDemo.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public final class ComparisonDemo {
    private ComparisonDemo() {}

    public static void main(String[] args) {
        try (var xml = new ClassPathXmlApplicationContext("tx-xml.xml")) {
            run("XML", xml);
        }

        try (var javaConfig =
                new AnnotationConfigApplicationContext(JavaConfig.class)) {
            run("Annotation", javaConfig);
        }
    }

    private static void run(String label, ConfigurableApplicationContext context) {
        JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
        TransferService service =
                context.getBean("transferService", TransferService.class);

        jdbc.execute("CREATE TABLE wallet ("
                + "id INT PRIMARY KEY, "
                + "balance INT NOT NULL CHECK (balance >= 0))");
        jdbc.update("INSERT INTO wallet(id, balance) VALUES (?, ?)", 1, 100);
        jdbc.update("INSERT INTO wallet(id, balance) VALUES (?, ?)", 2, 100);

        System.out.println(label + " proxy=" + AopUtils.isAopProxy(service));
        show(label + " initial", jdbc);

        service.transfer(false);
        show(label + " after commit", jdbc);

        try {
            service.transfer(true);
        } catch (IllegalStateException expected) {
            System.out.println(label + " caught: " + expected.getMessage());
        }
        show(label + " after rollback", jdbc);
    }

    private static void show(String label, JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?", Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?", Integer.class, 2);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }
}
~~~

Từ thư mục **transaction-config-compare**, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Các dòng stdout do chính chương trình in** (không bao gồm log riêng của framework hoặc Maven):

~~~text
XML proxy=true
XML initial: A=100, B=100
XML after commit: A=90, B=110
XML caught: simulated failure
XML after rollback: A=90, B=110
Annotation proxy=true
Annotation initial: A=100, B=100
Annotation after commit: A=90, B=110
Annotation caught: simulated failure
Annotation after rollback: A=90, B=110
~~~

Giải thích:

1. **AopUtils.isAopProxy(service)=true** cho thấy cả hai cách tạo Spring proxy. Đây là dấu hiệu cần nhưng chưa đủ chứng minh đúng transaction; vì vậy method còn kiểm tra isActualTransactionActive().
2. **transfer(false)** chạy hai UPDATE trên đúng connection do transaction manager điều phối, rồi commit. Số dư mới A=90, B=110.
3. **transfer(true)** thực thi hai UPDATE rồi ném IllegalStateException; XML rollback-for và annotation rollbackFor đều yêu cầu rollback, nên số dư sau đó vẫn A=90, B=110.
4. Hai ApplicationContext dùng hai DB H2 **khác tên** để mỗi lần đều khởi tạo dữ liệu giống nhau. Đó là cách tránh hai lần chạy đè bảng của nhau khi so sánh.
5. Dữ liệu được đọc lại **sau khi method giao dịch kết thúc**. Điều này kiểm chứng trạng thái bền vững trong ví dụ tốt hơn chỉ nhìn log có chữ "commit" hoặc "rollback".

**DriverManagerDataSource không phải connection pool** và chỉ được dùng để giảm phụ thuộc trong demo. Trong môi trường production, dùng DataSource có pool phù hợp; transaction manager và repository vẫn phải cùng trỏ đến đúng tài nguyên.

## 6. Cặp tương đương khác: XML bật @Transactional

Có hai mô hình XML cần phân biệt:

**Mô hình A — policy trong XML:** tx:advice + tx:method + aop:pointcut + aop:advisor. Service Java không cần @Transactional.

**Mô hình B — policy vẫn là @Transactional, XML chỉ bật cơ chế đọc annotation:**

~~~xml
<!-- Đặt trong <beans> có namespace tx, đồng thời khai báo transactionManager
     và service bean trong cùng ApplicationContext thích hợp. -->
<tx:annotation-driven transaction-manager="transactionManager"
                      proxy-target-class="true"/>
~~~

Mô hình B gần tương đương với Java:

~~~java
@EnableTransactionManagement(proxyTargetClass = true)
// Annotation này nằm trên class @Configuration đã khai báo manager phù hợp.
~~~

Nếu service đã có @Transactional mà dự án vẫn quản lý bean bằng XML, mô hình B cho phép **kết hợp XML bean wiring và annotation method policy**. Không cần viết lại toàn bộ XML bằng @Bean chỉ để bật annotation. Nhưng chỉ thêm tx:annotation-driven mà không có @Transactional trên method thì không tạo ranh giới transaction giống XML advisor ở mô hình A.

Bảng:

| Nguồn policy | Hạ tầng cần bật | Có thể dùng khi |
| --- | --- | --- |
| XML tx:method | XML tx:advice + AOP advisor | Muốn điều khiển policy ngoài mã nguồn Java |
| Java @Transactional | XML tx:annotation-driven | Cấu hình bean XML nhưng policy đặt trên method |
| Java @Transactional | @EnableTransactionManagement | Cấu hình Java/annotation |
| Java @Transactional | Spring Boot transaction auto-configuration phù hợp | Boot đã cấu hình transaction management |

Trong proxy mode, tất cả vẫn cần lời gọi đi qua bean proxy. **Từ khóa annotation trên source code tự nó không làm một object được tạo bằng new trở thành transactional.**

## 7. Các thuộc tính XML và annotation phải đối chiếu đầy đủ

| XML tx:method / tx:advice | Java @Transactional | Ghi chú |
| --- | --- | --- |
| name="transfer" | Gắn lên method transfer | XML còn cần pointcut matching |
| name="get*" read-only="true" | @Transactional(readOnly=true) trên các getter phù hợp | Phải liệt kê/định vị đúng các method được XML áp dụng |
| propagation="REQUIRED" | propagation=Propagation.REQUIRED | Tham gia transaction hiện có hoặc mở mới |
| propagation="REQUIRES_NEW" | propagation=Propagation.REQUIRES_NEW | Transaction độc lập nếu manager hỗ trợ suspend |
| propagation="NESTED" | propagation=Propagation.NESTED | Savepoint nếu transaction manager/driver hỗ trợ |
| isolation="READ_COMMITTED" | isolation=Isolation.READ_COMMITTED | Áp dụng khi mở physical transaction mới; DBMS quyết định chi tiết |
| timeout="10" | timeout=10 | Giây, mức enforcement phụ thuộc tài nguyên |
| read-only="false" | readOnly=false | Không dùng readOnly thay quyền DB |
| rollback-for="com.example.BusinessCheckedException" | rollbackFor=BusinessCheckedException.class | Bổ sung rollback cho checked exception |
| no-rollback-for="com.example.ExpectedException" | noRollbackFor=ExpectedException.class | Ngoại lệ có thể thoát ra mà không yêu cầu rollback |
| transaction-manager="billingTxManager" | transactionManager="billingTxManager" | Chỉ định đúng manager và resource |

**Không chuyển XML name pattern thành class-level @Transactional một cách máy móc.** Ví dụ XML có get* read-only và method khác read-write, chuyển cả class thành readOnly=true sẽ thay đổi policy của lệnh ghi.

**Không bỏ qua rollback rules.** Mặc định @Transactional trong trường hợp phổ biến rollback cho RuntimeException và Error, nhưng checked Exception thường không tự làm rollback. Nếu XML có rollback-for cho ngoại lệ checked, bản annotation tương ứng phải có rollbackFor, hoặc một cấu hình mặc định rollback tương đương. Các rule theo exception cụ thể cần kiểm tra khi có kế thừa exception.

**Không nhầm propagation và isolation.** Propagation giải quyết quan hệ method lồng nhau; isolation điều chỉnh cách transaction đồng thời đọc/ghi dữ liệu. Một method REQUIRED tham gia transaction bên ngoài thường không thể áp dụng lại isolation mới lên physical transaction đã tồn tại.

**Không coi readOnly=true là lệnh cấm ghi chắc chắn.** Tác động phụ thuộc Spring manager, JDBC driver và DBMS; cần quyền DB hoặc ràng buộc thực tế nếu yêu cầu cấm ghi.

## 8. Phạm vi pointcut là khác biệt lớn nhất khi migrate

XML có thể cấu hình giao dịch cho cả một nhóm bean mà không sửa mã Java:

~~~xml
<tx:advice id="serviceTx" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* com.example.service.*.*(..))"/>
    <aop:advisor advice-ref="serviceTx" pointcut-ref="serviceMethods"/>
</aop:config>
~~~

**Phạm vi thực tế** là giao của hai điều kiện: method khớp **aop:pointcut** và khớp một **tx:method**. Trong ví dụ, find*/get* nhận readOnly và các tên khác nhận policy chung. Nếu chuyển sang annotation, hãy liệt kê method đang được chọn, xác định method read-only và đặt @Transactional chính xác (trên class với override ở method khi phù hợp). Một annotation đặt lên class có thể vô tình bao bọc method trước đây XML không match.

Với nhiều module, tên package, subclass, interface, method overloaded hoặc bean dùng JDK dynamic proxy, cần test lại phạm vi method thực tế. Không suy diễn rằng một biểu thức pointcut tương đương với @Transactional đặt trên mọi service.

### XML còn hữu ích ở đâu?

XML hữu ích khi người cấu hình muốn áp dụng policy từ bên ngoài source Java (ví dụ áp dụng cho class thư viện có thể được Spring quản lý) hoặc cần một tập quy tắc theo pattern lớn. Annotation gần code thuận tiện để đọc chính sách từng method và phát hiện tác động khi refactor tên. Cả hai đều có thể đúng nếu xác định rõ contract.

## 9. Proxy, ApplicationContext và cấu hình trùng lặp

### 9.1. Self-invocation

Trong chế độ proxy, lời gọi ngoài tới bean có thể bị intercept, nhưng:

~~~java
// Snippet minh họa, không phải chương trình độc lập.
public void outer() {
    this.inner();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // ...
}
~~~

Nếu outer() gọi inner() trực tiếp trên this, metadata transaction ở inner thường **không được intercept** như một lời gọi qua proxy. Với XML advice cũng vậy nếu chỉ lời gọi nội bộ trong cùng target object không đi qua proxy. Hãy thiết kế service boundary qua bean/proxy khác khi cần transaction độc lập.

Các method private/final và bean không do container quản lý cũng có rủi ro không được chặn tùy proxy type; kiểm tra khả năng intercept theo version/framework thực tế.

### 9.2. Context chứa service

@EnableTransactionManagement hoặc tx:annotation-driven phát hiện transactional beans trong **ApplicationContext được cấu hình**. Đặt chúng trong một child context dành cho controller khi service nằm ở parent context có thể khiến service không được áp dụng đúng. Khi migrate XML, hãy biết service bean và transaction infrastructure được nạp ở context nào.

### 9.3. Đừng vô tình có hai advisors cho cùng một method

Nếu giữ XML tx:advice + aop:advisor rồi thêm @Transactional và kích hoạt annotation-driven cho cùng một nhóm method, hệ thống có thể xuất hiện **hai transactional advisors** cùng intercept một lời gọi. Thứ tự advisor, logical transaction scope và log có thể thay đổi. Hãy xác định rõ nguồn policy cuối cùng và test, thay vì bật tất cả vì muốn an toàn.

Trong ứng dụng có security, cache, custom AOP, hãy xem xét **advice order** nếu behavior phụ thuộc phần nào chạy trước. Class-based proxy và JDK proxy cũng có khác biệt về type/casting nên cần kiểm chứng API mà client dùng.

## 10. Khi có nhiều transaction managers

XML advice có thể chỉ định:

~~~xml
<tx:advice id="billingAdvice" transaction-manager="billingTxManager">
    <tx:attributes>
        <tx:method name="settle" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
~~~

Annotation tương ứng:

~~~java
// Snippet trong Spring-managed service.
@Transactional(transactionManager = "billingTxManager")
public void settle() {
    // Truy cập billing repository.
}
~~~

Hai cách chỉ tương đương khi **billingTxManager** trỏ cùng tài nguyên với repository. Nếu Java annotation bỏ qualifier và chọn default manager của DataSource khác, transaction có thể mở trên DB khác dù log vẫn thể hiện “Creating new transaction”.

Với hai DataSource độc lập, một local manager không tự tạo atomic transaction qua cả hai. Nếu thực sự cần phối hợp nhiều tài nguyên, đánh giá JTA/XA hoặc thiết kế consistency như transactional outbox/saga theo yêu cầu hệ thống.

## 11. Kiểm thử hành vi sau chuyển đổi

Đừng chỉ xác minh XML file parse thành công hay @Transactional xuất hiện trong source. Một kiểm thử có giá trị nên chứng minh:

1. **Bean proxy:** gọi Spring bean, kiểm tra AopUtils.isAopProxy(...) hoặc log TransactionInterceptor.
2. **Entry boundary:** trong method, Spring transaction context đang active khi kỳ vọng.
3. **Commit thực:** sau lần ghi thành công, mở connection/transaction khác để đọc dữ liệu đã lưu.
4. **Rollback thực:** cố ý ném exception sau thao tác thứ hai rồi xác minh cả hai thay đổi chưa commit không còn.
5. **Checked exception:** khi policy có rollback-for/rollbackFor, test checked exception tương ứng.
6. **Propagation lồng nhau:** nếu có REQUIRED, REQUIRES_NEW hoặc NESTED, đối chiếu physical transaction và savepoint behavior.
7. **Đúng manager:** test bean manager, DataSource, JPA provider thực sự được dùng.
8. **Không mở transaction thừa:** phương thức không match pointcut XML trước đó phải giữ đúng trạng thái sau chuyển đổi.

Có thể bật log trong Spring Boot ở môi trường thử nghiệm:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Các dòng như *Creating new transaction*, *Getting transaction for*, *Initiating transaction commit*, *Initiating transaction rollback* và *Releasing JDBC Connection* giúp nối bối cảnh. **Log commit khởi phát không phải chứng cứ cuối cùng nếu commit ném exception**; hãy đọc lại database.

Nếu test class itself @Transactional và test framework tự rollback cuối bài, đừng dùng những truy vấn chỉ nằm trong cùng test transaction để tuyên bố physical commit thành công. Thiết kế integration test đọc từ transaction hoặc connection độc lập khi cần.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Lý do có thể | Kiểm tra |
| --- | --- | --- |
| XML hoạt động, annotation bị bỏ qua | Quên bật annotation transaction, bean ngoài context, self-invocation | @EnableTransactionManagement/tx:annotation-driven, AOP proxy, call stack |
| Annotation rollback nhưng XML commit | XML thiếu rollback-for, pointcut match sai method | Policy + exception thật sự thoát khỏi boundary |
| XML rollback nhưng annotation commit | Bỏ sót rollbackFor khi chuyển checked exception | So khớp exception class và rollback rules |
| XML advisor không hoạt động | Thiếu aop:advisor, thiếu aspectjweaver hoặc pointcut không match | Context load, advisor, AOP expression, proxy |
| Hai cách chọn DB khác nhau | Nhầm TransactionManager bean hoặc DataSource wiring | So khớp bean name, JDBC URL, repository |
| Annotation có transaction cho quá nhiều method | Gắn @Transactional ở class quá rộng | Lập danh sách XML pointcut matches trước migration |
| UnexpectedRollbackException | Inner REQUIRED đã đánh dấu rollback-only | Xem transaction propagation và nơi setRollbackOnly |
| NESTED không hỗ trợ | Transaction manager/driver không hỗ trợ savepoint | Kiểm tra manager và JDBC savepoint capability |
| Transaction mới không bắt đầu | Method internal call không qua proxy hoặc đang tham gia REQUIRED | Quan sát proxy/advisor, transaction owner |
| Một request bị intercept hai lần | XML advice và annotation advice cùng áp dụng | Liệt kê advisors, làm rõ policy owner |
| Có log commit nhưng số dư không như kỳ vọng | SQL/DB khác, lock/race hoặc kết quả commit không xác định | SQL update count và database readback độc lập |

**Luồng phân tích hữu ích:** service bean → AOP proxy/advisor → metadata policy → TransactionManager → DataSource/Connection → SQL → commit/rollback → dữ liệu được đọc sau transaction. Mỗi mắt xích đều phải khớp nếu muốn tuyên bố “XML và annotation có cùng hành vi”.

## 13. Tự kiểm tra kiến thức

**1. tx:annotation-driven có phải chính là @Transactional không?**  
Không. Nó là cách XML bật xử lý @Transactional, tương đương chức năng @EnableTransactionManagement. XML tx:advice/tx:method + AOP advisor mới là mô hình khai báo policy từ XML.

**2. XML tx:method name="transfer" có áp dụng cho mọi bean có method transfer không?**  
Không mặc nhiên. Nó chỉ được áp dụng nơi advisor/pointcut khớp, dùng manager đúng và bean được Spring proxy.

**3. Tại sao ví dụ có XML policy nhưng class TransferService không gắn @Transactional vẫn rollback?**  
Vì XML advisor bao quanh lời gọi từ caller tới Spring proxy và chuyển policy cho TransactionInterceptor; method chạy trong transaction do manager mở.

**4. Có thể dùng XML khai báo bean nhưng method vẫn dùng @Transactional không?**  
Có. Dùng tx:annotation-driven với transaction manager và service bean đúng context, hoặc một cách kích hoạt annotation transaction tương đương.

**5. Tại sao phải so khớp rollbackFor và rollback-for khi có checked exception?**  
Vì Spring mặc định thường không rollback checked Exception. Nếu một bên khai báo rule và bên kia bỏ qua, một bên có thể rollback còn bên kia commit.

**6. AopUtils.isAopProxy(bean)=true đã chứng minh giao dịch của method hoạt động chưa?**  
Chưa. Proxy có thể phục vụ advice khác hoặc pointcut không chọn method. Cần xác minh interceptor/context và commit/rollback qua database.

**7. Nếu cùng policy nhưng hai cấu hình dùng hai DataSource khác nhau thì có tương đương?**  
Không về resource. Hai database có thể cho kết quả demo giống nhau từ dữ liệu giống nhau, nhưng trong ứng dụng thật cần kiểm tra rằng manager và repository dùng đúng tài nguyên dự định.

**8. Có thể chuyển XML name="get*" read-only=true thành @Transactional(readOnly=true) trên cả service không?**  
Chỉ khi toàn bộ service thực sự có chính sách tương đương. Nếu method ghi cũng nằm trong class, class-level readOnly=true có thể thay đổi behavior.

## 14. Kết luận thực hành

Đối chiếu XML và annotation ở Spring transaction không dừng ở cú pháp:

- **Bean và tài nguyên:** XML bean/ref ↔ Java @Bean/injection, cùng DataSource và TransactionManager.
- **Policy:** XML tx:method + AOP pointcut/advisor ↔ @Transactional tại đúng method/class; giữ nguyên propagation, isolation, timeout, rollback.
- **Kích hoạt annotation:** XML tx:annotation-driven ↔ Java @EnableTransactionManagement.
- **Hành vi:** xác nhận Spring proxy, transaction active, commit/rollback và readback từ DB.
- **Migrate an toàn:** khảo sát toàn bộ pointcut matches, tránh tự mở rộng annotation scope, tránh advisors trùng nhau và xác minh trên DBMS thực tế.

Trong ví dụ chạy đầy đủ, cả hai cấu hình cùng commit khi không có lỗi và cùng rollback khi IllegalStateException thoát khỏi method. Điều này chứng minh cùng behavior đối với contract đã đặt, dù nguồn policy là XML hay annotation.

## Tài liệu tham khảo

- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Declarative Transaction XML Example](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
