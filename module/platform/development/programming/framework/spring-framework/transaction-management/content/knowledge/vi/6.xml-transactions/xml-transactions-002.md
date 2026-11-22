# Định nghĩa `tx:advice` và các thuộc tính `tx:method` trong Spring Framework

## Mục tiêu

Sau bài học, bạn có thể đọc và tự viết cấu hình **quản lý transaction dạng XML** trong Spring, hiểu vai trò của `<tx:advice>`, `<tx:attributes>` và `<tx:method>`; biết cách nối transaction advice với AOP pointcut; lựa chọn chính xác các thuộc tính `name`, `propagation`, `isolation`, `timeout`, `read-only`, `rollback-for` và `no-rollback-for`; kiểm tra bằng ví dụ JDBC có cả commit lẫn rollback.

Phạm vi là **cấu hình XML của Spring Framework**. Ví dụ chính dùng Java 17, Spring JDBC, transaction manager kiểu imperative. Cùng các nguyên tắc transaction của Spring cũng xuất hiện trong cấu hình annotation, nhưng cú pháp XML và điểm áp dụng được giải thích riêng tại đây.

## 1. Vì sao cần `tx:advice`?

Giả sử service `transfer()` thực hiện hai câu SQL: trừ tài khoản nguồn, cộng tài khoản đích. Nếu lệnh cộng thất bại, lệnh trừ phải được hoàn tác. Thay vì viết `connection.setAutoCommit(false)`, `commit()`, `rollback()` và mã giải phóng tài nguyên trong từng service, ta khai báo quy tắc transaction trong XML. Spring dùng AOP proxy và transaction interceptor để quản lý vòng đời transaction quanh lời gọi phương thức.

Ba phần có nhiệm vụ khác nhau:

1. **`<tx:advice>`:** tạo một *transaction advice* có định danh và tham chiếu transaction manager. Advice này mô tả “cách quản lý transaction”.
2. **`<tx:attributes>` chứa các `<tx:method>`:** cho biết *phương thức tên gì* dùng chính sách transaction nào.
3. **`<aop:pointcut>` + `<aop:advisor>`:** xác định *bean/phương thức nào* được AOP chặn và liên kết điểm chặn với advice vừa định nghĩa.

```text
Client gọi phương thức trên Spring proxy
    │
    ├─ AOP pointcut có khớp class + method không?
    │    └─ Không → không áp dụng advice này
    │
    └─ Có → tra <tx:method name="..."> phù hợp
             │
             ├─ Không có rule phù hợp → advice không tạo transaction cho method đó
             │
             └─ Có → TransactionInterceptor dùng TransactionManager:
                       mở/tham gia transaction
                       gọi thân phương thức
                       trả về bình thường → commit (nếu chủ sở hữu transaction)
                       exception phải rollback → rollback/đánh dấu rollback-only
```

Cấu hình `<tx:advice>` **đơn lẻ chưa tự gắn** được vào service; cần `<aop:advisor>` và pointcut tương ứng. Ngược lại, pointcut chỉ chọn nơi can thiệp, không tự quy định `read-only` hay rollback nếu thiếu advice.

## 2. Cấu trúc XML chuẩn

Ví dụ cô đọng sau minh họa đủ bộ phận (`txManager` là một bean `PlatformTransactionManager` đã được khai báo trong context):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd">

    <tx:advice id="serviceTxAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="find*" read-only="true"/>
            <tx:method name="save*" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"/>
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="serviceMethods"
                      expression="execution(* com.example.service.*Service.*(..))"/>
        <aop:advisor pointcut-ref="serviceMethods"
                     advice-ref="serviceTxAdvice"/>
    </aop:config>
</beans>
```

Đây là **đoạn cấu hình minh họa**, chưa phải ứng dụng chạy độc lập vì các bean service, datasource và `txManager` được lược bỏ. Phần 7 có dự án Maven đầy đủ để chạy thử.

Cách đọc:

- `id="serviceTxAdvice"`: tên bean advice để `advice-ref` tham chiếu.
- `transaction-manager="txManager"`: tên bean có khả năng quản lý transaction, ví dụ `JdbcTransactionManager` hoặc `JpaTransactionManager`. Nếu bean có đúng tên `transactionManager`, có thể bỏ thuộc tính này; với tên khác phải chỉ rõ.
- `<tx:attributes>`: nhóm các quy tắc giao dịch theo tên phương thức.
- `<tx:method name="find*" .../>`: tất cả phương thức khớp tên `find*` nhận chính sách read-only.
- `<tx:method name="*"/>`: quy tắc mặc định cho các phương thức chưa khớp quy tắc cụ thể hơn.
- `expression="execution(* com.example.service.*Service.*(..))"`: AspectJ pointcut expression chọn method của class kết thúc bằng `Service` trong package trực tiếp `com.example.service`. Dấu `*` trong biểu thức AOP này thuộc cú pháp AspectJ; **khác** với việc dùng `*` để khớp *tên phương thức* ở thuộc tính `tx:method name`.

Khi muốn chọn cả package con, cần điều chỉnh pointcut (ví dụ dùng `com.example.service..*Service`) và xác nhận khớp chính xác đối tượng dự kiến. Không nên đặt pointcut quá rộng, vô tình bọc controller, DAO hoặc service không liên quan.

## 3. Bảng đầy đủ các thuộc tính `tx:method`

Theo tài liệu Spring Framework, `name` là thuộc tính **bắt buộc**; sáu thuộc tính còn lại đều tùy chọn.

| Thuộc tính | Giá trị / mặc định | Ý nghĩa |
|---|---|---|
| `name` | **Bắt buộc**; tên chính xác hoặc mẫu có `*` | Chọn tên phương thức nhận rule này, ví dụ `getById`, `get*`, `*Service`, `*` |
| `propagation` | `REQUIRED` | Cách phương thức tham gia hoặc tạo transaction khi caller đã/chưa có transaction |
| `isolation` | `DEFAULT` | Mức cô lập dữ liệu trong transaction mới; phụ thuộc DB/driver |
| `timeout` | `-1` (mặc định hạ tầng) | Giới hạn thời gian transaction, tính bằng **giây**, nếu manager/resource hỗ trợ |
| `read-only` | `false` | Gợi ý transaction chỉ đọc; có thể giúp tối ưu và có thể được driver/DB áp dụng |
| `rollback-for` | Không có rule bổ sung | Danh sách tên/mẫu tên exception, ngăn cách bởi dấu phẩy, **phải rollback** |
| `no-rollback-for` | Không có rule bổ sung | Danh sách tên/mẫu tên exception, ngăn cách bởi dấu phẩy, **không rollback theo rule này** |

Nếu không khai báo thêm: propagation = `REQUIRED`, isolation = `DEFAULT`, transaction read-write, timeout theo transaction system, `RuntimeException` và `Error` làm rollback còn checked `Exception` thường không. Các rule rollback tường minh có thể thay đổi hành vi mặc định.

Lưu ý: thuộc tính `isolation`, `timeout` và `read-only` có ý nghĩa khi transaction mới được bắt đầu, thông thường ở `REQUIRED` (khi chưa có transaction) hoặc `REQUIRES_NEW`. Khi `REQUIRED` tham gia một transaction đã tồn tại, nó thường dùng đặc tính thực tế của transaction bên ngoài. Các manager có thể kiểm tra/xử lý khác nhau tùy cấu hình.

### 3.1. `name`: chọn phương thức theo tên

```xml
<tx:attributes>
    <tx:method name="findById" read-only="true"/>
    <tx:method name="find*" read-only="true"/>
    <tx:method name="*Report" read-only="true"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Trong cùng advice, tên khớp chính xác được ưu tiên; với các mẫu, Spring chọn mẫu khớp cụ thể nhất (thông thường mẫu có chuỗi dài nhất). Do đó `findById` sẽ theo rule riêng, `findAll` theo `find*` và `generateReport` theo `*Report`. Việc có rule `*` tránh vô tình bỏ sót các method còn lại. Tránh tạo các mẫu chồng lấn mơ hồ có cùng độ cụ thể.

`name` chỉ xét **tên method**; không phân biệt hai overload `find(long)` và `find(String)` theo tham số. Nếu cần chọn theo kiểu/đối số/phạm vi class, dùng biểu thức pointcut AOP thích hợp và, khi cần, tách advice. Đây không phải regex; `*` là ký tự đại diện cho chuỗi ký tự trong tên phương thức.

### 3.2. `propagation`: quan hệ với transaction của caller

| Giá trị | Nếu đã có transaction | Nếu chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction đang có | Tạo transaction mới |
| `REQUIRES_NEW` | Tạm ngưng transaction cũ, tạo transaction độc lập | Tạo transaction mới |
| `SUPPORTS` | Tham gia nếu có | Chạy không có transaction |
| `MANDATORY` | Bắt buộc tham gia | Ném exception vì thiếu transaction |
| `NOT_SUPPORTED` | Tạm ngưng transaction, chạy không có transaction | Chạy không có transaction |
| `NEVER` | Ném exception nếu đang có transaction | Chạy không có transaction |
| `NESTED` | Thử tạo phạm vi lồng nhau với savepoint (nếu manager hỗ trợ) | Thường tương tự `REQUIRED` |

Ví dụ `REQUIRES_NEW` hữu ích khi bản ghi audit cần transaction riêng, nhưng có hệ quả: audit có thể commit trong khi transaction bên ngoài rollback. Nó có thể cần thêm connection; cần kiểm tra connection pool, đặc biệt khi nhiều lời gọi đồng thời. `NESTED` phụ thuộc savepoint và transaction manager, không mặc nhiên tương thích mọi hạ tầng.

### 3.3. `isolation`: mức cô lập

Các giá trị thông dụng: `DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`.

- `DEFAULT`: dùng mức isolation mặc định của DB.
- `READ_UNCOMMITTED`: mức yếu, có thể cho phép đọc dữ liệu chưa commit nếu database thực sự hỗ trợ.
- `READ_COMMITTED`: ngăn dirty read; vẫn có thể thấy thay đổi giữa hai câu truy vấn.
- `REPEATABLE_READ`: bảo đảm mạnh hơn cho lần đọc lại cùng một hàng; chi tiết phantom, khóa, snapshot tùy DB.
- `SERIALIZABLE`: hướng tới hiệu ứng như chạy tuần tự; có thể tăng xung đột và nhu cầu retry.

Ví dụ: `<tx:method name="settle*" isolation="SERIALIZABLE"/>` thể hiện yêu cầu, **không bảo đảm** mọi database/driver đều đáp ứng giống nhau. Hãy kiểm thử trên DB sản xuất và xử lý các lỗi deadlock/serialization theo chính sách retry an toàn.

### 3.4. `timeout` và `read-only`

```xml
<tx:method name="create*" propagation="REQUIRED"
           timeout="30" read-only="false"/>
<tx:method name="get*" propagation="REQUIRED"
           timeout="5" read-only="true"/>
```

`timeout="30"` là 30 giây, **không phải 30 ms**. Nó không bảo đảm tự cắt mọi thao tác CPU hoặc hủy mọi blocking call đúng tại giây thứ 30: thời điểm phát hiện/áp dụng tùy transaction manager, JDBC statement và tài nguyên đang dùng. `timeout="-1"` nghĩa là dùng mặc định hạ tầng, không có nghĩa luôn vô hạn.

`read-only="true"` là **hint**, không phải lớp phân quyền bảo mật. Một số DB/driver có thể chặn ghi hoặc tối ưu; một số không. Dù dùng rule chỉ đọc, ứng dụng vẫn cần quyền DB phù hợp và tránh ghi dữ liệu ở các method được đánh dấu đọc.

### 3.5. `rollback-for` và `no-rollback-for`

Mặc định lỗi unchecked (`RuntimeException`) và `Error` rollback; checked exception như `IOException` không mặc nhiên rollback. Cấu hình XML:

```xml
<tx:method name="importData"
           rollback-for="java.io.IOException,com.example.tx.ImportFailedException"/>

<tx:method name="confirmOrder"
           no-rollback-for="com.example.tx.NotificationWarningException"/>
```

- `rollback-for` yêu cầu rollback khi exception khớp, kể cả checked exception vốn không nằm trong mặc định.
- `no-rollback-for` yêu cầu không rollback vì exception đó; **công việc đã ghi trước khi exception thoát ra có thể được commit**. Chỉ dùng khi đó thực sự là kết quả nghiệp vụ cho phép.
- Các giá trị trong XML là **mẫu tên exception**, không phải Java `Class<?>` được kiểm tra tĩnh. Tên đầy đủ package giúp giảm khớp nhầm. Ví dụ `Exception` quá rộng, có thể vô tình khớp nhiều lớp khác; các mẫu rollback **không hỗ trợ wildcard `*`** như `name`.
- Nếu có nhiều rule rollback/no-rollback cùng khớp, rule *mạnh nhất/cụ thể nhất* quyết định. Không nên dựa vào thứ tự khai báo hai thuộc tính để đoán kết quả.
- Nếu code bắt exception rồi nuốt bên trong service, interceptor thấy phương thức trả về bình thường và thường commit; `rollback-for` không thể xử lý exception đã bị nuốt. Có thể ném lại exception hoặc đánh dấu rollback-only qua API Spring.

**Cảnh báo ngữ nghĩa:** `no-rollback-for="java.lang.IllegalArgumentException"` không có nghĩa “bỏ qua mọi lỗi đầu vào một cách an toàn”. Nếu có cập nhật DB trước khi exception xuất hiện, policy này có thể commit thay đổi dở dang.

## 4. Quy trình xử lý thực tế

Giả sử có hai bean `accountService` và `transactionManager`, cùng một datasource JDBC:

1. Client gọi phương thức trên **Spring proxy**, không gọi trực tiếp object tự `new`.
2. `<aop:pointcut>` quyết định method đó có nằm trong phạm vi AOP.
3. Transaction interceptor lấy cấu hình từ `<tx:method>` khớp tên, ví dụ `getBalance` → `get*`, `transfer` → `transfer*`.
4. `PlatformTransactionManager` mở transaction mới hoặc tham gia transaction hiện hành theo propagation. Với JDBC, Spring ràng buộc connection vào thread theo quy tắc `TransactionSynchronizationManager`.
5. Service dùng `JdbcTemplate`/repository phù hợp với transaction-bound datasource.
6. Thành công → chủ sở hữu transaction commit; exception cần rollback → rollback hoặc đánh dấu rollback-only nếu đang tham gia transaction bên ngoài.
7. Spring giải phóng resource theo vòng đời transaction.

Trong tình huống `REQUIRED` lồng nhau, một lời gọi bên trong có thể đánh dấu transaction chung là rollback-only; dù method bên ngoài bắt exception và trả về bình thường, lúc commit bên ngoài vẫn có thể nhận `UnexpectedRollbackException`. Đây là lý do cần hiểu ranh giới transaction thực tế thay vì chỉ nhìn tên method.

## 5. Ví dụ chạy được: Spring XML + Java 17 + H2

Dự án minh họa dùng cấu hình XML, **không dùng `@Transactional`**. Service chứa hai thao tác chuyển tiền và một thao tác cố tình ném checked exception để quan sát `rollback-for`. H2 là database trong bộ nhớ; ứng dụng khởi tạo dữ liệu trong `Main`.

Cấu trúc:

```text
tx-xml-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/tx/
    │   ├── AccountOperations.java
    │   ├── AccountServiceImpl.java
    │   └── Main.java
    └── resources/
        └── applicationContext.xml
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>tx-xml-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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

`spring-context` cung cấp XML application context, `spring-jdbc` cung cấp `JdbcTemplate` và `JdbcTransactionManager`, `aspectjweaver` phục vụ xử lý AspectJ pointcut expression trong AOP, H2 là DB chạy thử. Phiên bản được cố định để ví dụ có thể tái hiện; dự án thực nên quản lý phiên bản theo BOM và chính sách cập nhật của mình.

### 5.2. `AccountOperations.java`

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;

public interface AccountOperations {
    BigDecimal getBalance(long accountId);
    void transfer(long from, long to, BigDecimal amount);
    void transferChecked(long from, BigDecimal amount) throws IOException;
}
```

### 5.3. `AccountServiceImpl.java`

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;

public class AccountServiceImpl implements AccountOperations {
    private final JdbcTemplate jdbc;

    public AccountServiceImpl(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public BigDecimal getBalance(long accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?",
            BigDecimal.class,
            accountId
        );
    }

    @Override
    public void transfer(long from, long to, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || from == to) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("missing sender or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("missing recipient");
        }
    }

    @Override
    public void transferChecked(long from, BigDecimal amount)
            throws IOException {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, from
        );
        throw new IOException("checked failure");
    }
}
```

`transferChecked()` là **phương thức cố tình gây lỗi để kiểm chứng rollback**, không phải nghiệp vụ chuyển tiền hoàn chỉnh. Nó chỉ chạy trong ví dụ kiểm thử; trong ứng dụng thật không được làm trừ tiền rồi cố tình ném exception. `transfer()` mới là luồng nghiệp vụ có kiểm tra số dòng cập nhật và yêu cầu hai cập nhật nguyên tử.

### 5.4. `applicationContext.xml`

```xml
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
        <property name="url" value="jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1"/>
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

    <bean id="accountService" class="com.example.tx.AccountServiceImpl">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="accountTxAdvice"
               transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="get*" read-only="true"/>
            <tx:method name="transferChecked" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"
                       rollback-for="java.io.IOException"/>
            <tx:method name="transfer*" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"/>
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="accountOps"
                      expression="execution(* com.example.tx.AccountOperations.*(..))"/>
        <aop:advisor advice-ref="accountTxAdvice" pointcut-ref="accountOps"/>
    </aop:config>
</beans>
```

Các rule được chọn:

- `getBalance` → `get*`, read-only.
- `transfer` → `transfer*`, transaction mới hoặc tham gia transaction hiện hành; isolation `READ_COMMITTED` khi tạo transaction mới; timeout 15 giây.
- `transferChecked` → rule **khớp chính xác**, nên `rollback-for="java.io.IOException"` có hiệu lực. Rule này cũng khai báo riêng isolation/timeout vì nó **không kế thừa** tùy chọn của rule `transfer*`.
- `*` → dự phòng cho các method còn lại; trong demo không có method nào phải dùng fallback.

`DriverManagerDataSource` phù hợp cho demo/test nhỏ vì mỗi lần lấy connection có thể tạo connection mới; sản phẩm thực tế nên dùng datasource có connection pool và cấu hình bảo mật/khả năng chịu tải phù hợp.

### 5.5. `Main.java` và kết quả

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    private static String balances(AccountOperations service) {
        return "A=" + service.getBalance(1) +
               " B=" + service.getBalance(2);
    }

    public static void main(String[] args) {
        try (var context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id BIGINT PRIMARY KEY, balance DECIMAL(19, 2) NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (?, ?)",
                1, new BigDecimal("100.00")
            );
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (?, ?)",
                2, new BigDecimal("50.00")
            );

            // Lấy bean qua Spring context để lời gọi đi qua AOP proxy.
            AccountOperations service = context.getBean(AccountOperations.class);
            System.out.println("Ban dau: " + balances(service));

            service.transfer(1, 2, new BigDecimal("20.00"));
            System.out.println("Thanh cong: " + balances(service));

            try {
                service.transferChecked(1, new BigDecimal("5.00"));
            } catch (IOException ex) {
                System.out.println("Checked error: " + ex.getMessage());
            }
            System.out.println("Sau checked rollback: " + balances(service));

            try {
                service.transfer(1, 999, new BigDecimal("5.00"));
            } catch (IllegalStateException ex) {
                System.out.println("Runtime error: " + ex.getMessage());
            }
            System.out.println("Sau runtime rollback: " + balances(service));
        }
    }
}
```

Tại thư mục dự án (đã cài JDK 17+ và Maven), chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

Sáu dòng **do chương trình in ra** (Maven hoặc logging framework có thể thêm thông báo khác tùy môi trường):

```text
Ban dau: A=100.00 B=50.00
Thanh cong: A=80.00 B=70.00
Checked error: checked failure
Sau checked rollback: A=80.00 B=70.00
Runtime error: missing recipient
Sau runtime rollback: A=80.00 B=70.00
```

Vì sao kết quả đúng?

1. Lần đầu, `getBalance()` trả về 100.00 và 50.00.
2. `transfer(1, 2, 20.00)` thực hiện hai lệnh UPDATE rồi commit: 80.00 và 70.00.
3. `transferChecked()` đã trừ 5.00 nhưng ném checked `IOException`. Rule XML `rollback-for="java.io.IOException"` buộc rollback, nên số dư **không đổi**.
4. `transfer(1, 999, 5.00)` trừ tài khoản A trước, sau đó phát hiện người nhận không tồn tại và ném unchecked `IllegalStateException`. Quy tắc rollback mặc định hoàn tác lệnh trừ.

Nếu vô tình gọi `new AccountServiceImpl(jdbc)` trực tiếp thay vì lấy bean từ context, interceptor sẽ không chạy. Còn nếu xóa rule rollback dành cho checked exception, bước (3) có nguy cơ **commit phần trừ 5.00** vì `IOException` không được rollback theo quy tắc mặc định.

## 6. Các lỗi cấu hình và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Service chạy nhưng không có transaction | Khai báo `tx:advice` nhưng thiếu `aop:advisor`, pointcut không khớp, hoặc gọi ngoài proxy | Kiểm tra pointcut, `advice-ref`, bean lấy từ context và log của interceptor |
| Không tìm thấy transaction manager | `transaction-manager` trỏ sai bean; mặc định tìm bean tên `transactionManager` nếu không khai báo | Xác nhận bean id và datasource được manager quản lý |
| Method đọc bị tạo transaction ghi | `name` không khớp, thiếu `read-only="true"`, hoặc rule rộng `*` được áp dụng | Kiểm tra tên method thực tế và rule cụ thể |
| Checked exception không rollback | Chưa cấu hình `rollback-for` hoặc exception bị bắt bên trong method | Thêm rule có tên exception phù hợp và cho lỗi thoát qua transaction interceptor |
| Một lỗi vẫn commit | Dùng `no-rollback-for`, nuốt lỗi, hoặc rule mâu thuẫn | Rà soát chính sách rollback; chỉ cho phép commit khi đó là kết quả nghiệp vụ hợp lệ |
| Isolation/timeout không như mong đợi | Method tham gia transaction đã mở, manager/driver không hỗ trợ, hoặc timeout chưa được resource thực thi | Xem propagation, chủ sở hữu transaction và khả năng của DB |
| `this.method()` không kích hoạt transaction riêng | Self-invocation bỏ qua Spring proxy mặc định | Đặt ranh giới ở method đi qua proxy hoặc tách sang bean khác |
| Hành vi khác nhau giữa môi trường | DB hỗ trợ isolation/read-only khác nhau; cấu hình datasource/manager khác | Test tích hợp trên DB và driver thực tế; không chỉ unit test bằng mock |
| `NESTED` thất bại | Manager không hỗ trợ savepoint/nested transaction | Kiểm tra khả năng của manager và chọn propagation phù hợp |
| Hai lời gọi dùng hai datasource | Transaction manager và repository không cùng tài nguyên | Kiểm tra kết nối/bean, không giả định local transaction bao trùm nhiều datasource |

**Chủ động kiểm thử:** xác nhận advice thực sự được kích hoạt, rồi kiểm thử thành công/rollback. Một dấu hiệu hữu ích là bật DEBUG cho `org.springframework.transaction` và `org.springframework.aop`, nhưng log chi tiết và tên logger có thể khác giữa phiên bản. Kiểm chứng đáng tin hơn là đọc lại trạng thái DB sau mỗi ca.

**Phân biệt hai cơ chế XML:**

- `<tx:advice>` + `<aop:advisor>`: quy tắc được mô tả theo *tên method* trong XML, service có thể là POJO không gắn annotation.
- `<tx:annotation-driven>`: bật xử lý annotation `@Transactional` trên bean; đây là lựa chọn khác. Nếu cấu hình cả hai trên cùng method, cần xem kỹ phạm vi và thứ tự advice để tránh can thiệp lặp, thay vì coi chúng tự động hợp nhất thành một rule.

## 7. Bài tập tự kiểm tra

1. Với `<tx:method name="find*" read-only="true"/>` và `<tx:method name="*"/>`, method `findByCode()` chọn rule nào? **Đáp án:** `find*`.
2. Nếu xóa `<aop:advisor>` nhưng giữ `<tx:advice>`, giao dịch có tự áp vào service không? **Không**; cần advisor/pointcut để gắn advice.
3. `rollback-for="java.io.IOException"` để làm gì? **Bổ sung rollback cho exception dạng checked** khi nó đi ra khỏi method.
4. Hai overload `save(long)` và `save(String)` có thể nhận hai rule khác nhau chỉ bằng `name="save"` không? **Không**, vì `tx:method` khớp tên method chứ không khớp chữ ký.
5. `read-only="true"` có ngăn mọi lệnh `UPDATE` ở mọi database không? **Không**; đó là hint, cần kiểm tra DB/driver và quyền truy cập.
6. `REQUIRES_NEW` có thể commit khi transaction ngoài rollback không? **Có**, vì nó là transaction độc lập.
7. Vì sao `name="transferChecked"` cần khai báo lại timeout dù đã có `name="transfer*" timeout="15"`? **Rule cụ thể được chọn nguyên bộ; thuộc tính không được kế thừa từng phần từ rule rộng.**

## Tài liệu chính thức

- Spring — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring — `<tx:advice/>` Settings (bảng giá trị mặc định của `tx:method`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring — Understanding the Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
