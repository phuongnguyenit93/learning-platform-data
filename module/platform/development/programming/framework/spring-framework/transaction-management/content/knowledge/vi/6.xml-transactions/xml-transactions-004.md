# Chính sách giao dịch theo tên phương thức và mức ưu tiên mẫu trong cấu hình XML

## 1. Bài toán: cùng một service, nhiều chính sách transaction

Trong Spring Framework, có thể đặt chính sách transaction cho **nhóm phương thức theo tên** mà không cần gắn `@Transactional` lên từng method Java. Cách cấu hình XML truyền thống dùng:

- `<aop:pointcut>` để xác định **lời gọi method của bean nào** có thể nhận advice.
- `<aop:advisor>` để gắn pointcut đó với transaction advice.
- `<tx:advice>` và `<tx:attributes>` để khai báo **thuộc tính transaction**.
- Mỗi `<tx:method name="...">` định nghĩa một luật khớp tên method, ví dụ `get*`, `save*`, `*` hoặc một tên chính xác.

Điểm khó của bài này là: **nếu nhiều mẫu cùng khớp tên một method, Spring chọn luật nào?** Và liệu thứ tự các dòng XML có quyết định độ ưu tiên hay không?

Ví dụ một service gồm:

```java
public class AccountService {
    public long getBalance() { /* đọc */ return 0; }
    public void getAndChangeBalance(long delta) { /* ghi */ }
    public void saveAccount() { /* ghi */ }
    public void updateBalance(long delta) { /* ghi */ }
}
```

Ta muốn `getBalance` là read-only, `saveAccount` có chính sách rollback riêng, mọi thao tác khác nhận giao dịch mặc định. Nhưng `getAndChangeBalance` **vừa khớp `get*` vừa thực sự ghi dữ liệu**, nên cần một luật chính xác để ghi đè cấu hình đọc.

Để hiểu đúng, cần phân biệt **hai tầng lựa chọn**:

1. **Pointcut của AOP** có chọn lời gọi hay không? Nếu không, transaction advice này không được thực thi.
2. **TransactionAttributeSource** chọn cấu hình `<tx:method>` nào cho tên method? Một luật được chọn sẽ xác định toàn bộ bộ thuộc tính của transaction ấy.

Cú pháp `name` là mẫu tên method, **không phải** biểu thức chính quy Java, không phải Spring bean name, không phải đường dẫn endpoint và cũng không phải tên table.

## 2. Cấu trúc XML và vai trò của từng phần

Một cấu hình đọc/ghi cơ bản:

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="save*" propagation="REQUIRED"
                   rollback-for="com.example.BusinessException"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* com.example.service.*Service.*(..))"/>
    <aop:advisor pointcut-ref="serviceOps" advice-ref="txAdvice"/>
</aop:config>
```

Đây là **mảnh XML minh họa**, chưa phải một file `<beans>` độc lập: các bean `txManager` và service phải tồn tại, namespace/XSD của `tx` và `aop` phải được khai báo. Một ví dụ chạy đầy đủ sẽ xuất hiện ở phần 7.

Giải nghĩa:

| Phần | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `<aop:pointcut expression="...">` | Những join point/lời gọi nào được chọn | Method trong lớp service thuộc package chỉ định |
| `<aop:advisor>` | Advice nào áp dụng cho pointcut nào | `txAdvice` cho `serviceOps` |
| `<tx:advice transaction-manager="txManager">` | Transaction interceptor sử dụng manager nào | `JdbcTransactionManager`, `JpaTransactionManager` tùy tài nguyên |
| `<tx:attributes>` | Danh sách quy tắc transaction theo tên method | `get*`, `save*`, `*` |
| `<tx:method name="get*">` | Cấu hình cho nhóm tên khớp pattern | Read-only, propagation, rollback rules... |

**Hai kiểu dấu `*` không có cùng vai trò:** dấu `*` trong `execution(* ... )` thuộc cú pháp AspectJ của pointcut; dấu `*` trong `<tx:method name="get*">` là wildcard đơn giản của tên method. Không lấy cú pháp pointcut đầy đủ làm giá trị của `name`.

Nếu một method tên `getBalance` thuộc đối tượng bên ngoài pointcut, việc `getBalance` khớp `get*` **chưa đủ** để tạo transaction advice. Ngược lại, nếu lời gọi khớp pointcut nhưng không khớp bất kỳ `<tx:method>` nào, advice này không cung cấp transaction attribute cho lời gọi đó. Một transaction đang có từ caller vẫn có thể tồn tại do code bên ngoài tạo, nhưng **không phải do luật không khớp này mở ra**.

## 3. Cú pháp mẫu tên method: exact, wildcard, fallback

`name` của `<tx:method>` được so với **tên method Java**. Spring sử dụng kiểu match đơn giản với wildcard `*`, có phân biệt chữ hoa/chữ thường.

| Mẫu | Khớp | Không khớp |
| --- | --- | --- |
| `getBalance` | Chỉ tên `getBalance` | `getBalanceById`, `GetBalance` |
| `get*` | `get`, `getBalance`, `getById` | `findBalance`, `GETBalance` |
| `*Account` | `saveAccount`, `deleteAccount` | `saveAccountById` |
| `*ById` | `findById`, `deleteById` | `findAll` |
| `*Order*` | `getOrder`, `updateOrderStatus` | `getAccount` |
| `*` | Mọi tên method trong phạm vi advice | Không có tên method nào bị loại bởi mẫu này |

Vì đây là **simple wildcard**, `get.*` không được hiểu như regex “get rồi tới ký tự bất kỳ”; dấu chấm là ký tự thông thường, nên nó không thay thế `get*`. Cú pháp `?`, lớp ký tự `[a-z]` hoặc `^get` cũng không phải các phép regex mà `name` hỗ trợ. Các overload như `getBalance()` và `getBalance(long)` có cùng tên `getBalance`, vì vậy **không thể chọn chính sách riêng theo số/kiểu tham số chỉ bằng `<tx:method name>`**. Muốn chọn kiểu tham số, cần thể hiện ở pointcut AOP hoặc thiết kế API/cấu hình khác.

Thông thường một nhóm luật dễ đọc sẽ gồm: mẫu **exact cho ngoại lệ**, các mẫu **prefix/suffix có mục đích rõ**, và mẫu `*` làm **fallback** nếu muốn tất cả method được pointcut chọn đều có transaction.

Ví dụ:

```xml
<tx:attributes>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" rollback-for="com.example.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Ở đây `getAndChangeBalance` phải được đọc theo luật **exact**, dù tên bắt đầu bằng `get`. Đây là một trong những lý do nên kiểm tra tên method thực tế thay vì giả định mọi tên bắt đầu bằng `get` chỉ đọc dữ liệu.

## 4. Quy tắc ưu tiên: exact trước, sau đó mẫu khớp cụ thể nhất

Spring triển khai nhóm luật tên method qua `NameMatchTransactionAttributeSource`. Quy tắc quan trọng của nguồn thuộc tính này là:

1. **Ưu tiên khớp chính xác:** nếu tên method tồn tại đúng bằng một khóa trong danh sách, dùng luật đó ngay.
2. **Nếu không có exact:** duyệt các mẫu wildcard khớp và chọn mẫu **cụ thể nhất theo độ dài của chuỗi mẫu** (trong implementation, mẫu có `length` lớn hơn có ưu thế).
3. **Fallback `*`** có độ dài 1 nên chỉ thắng khi không có mẫu khớp dài hơn.
4. **Khi hai mẫu wildcard khác nhau cùng khớp và có cùng độ dài**, không nên xây dựng logic phụ thuộc vào thứ tự “dòng trên thắng” hay “dòng dưới thắng”. Hãy sửa cấu hình để tránh xung đột hoặc thêm exact match.

Đây là **độ ưu tiên khi chọn một luật tên method**, không phải `order` của AOP advisor, không phải độ ưu tiên rollback exception, cũng không phải độ ưu tiên giữa hai transaction manager.

### 4.1. Exact luôn thắng wildcard

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="*" read-only="false"/>
</tx:attributes>
```

Kết quả:

- `getBalance` chọn `get*` → `read-only=true`.
- `getAndChangeBalance` chọn exact `getAndChangeBalance` → `read-only=false`.
- `updateBalance` chọn `*` → `read-only=false`.

Ở ví dụ trên, luật exact đặt **sau** `get*` vẫn thắng. Không nên diễn giải theo mô hình firewall “first match wins”: đó **không phải** cơ chế của `NameMatchTransactionAttributeSource`.

### 4.2. Các wildcard giao nhau: xét độ dài mẫu

Giả sử các luật:

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="*Balance" read-only="false"/>
    <tx:method name="*" read-only="false"/>
</tx:attributes>
```

Method `getBalance` khớp cả `get*` (4 ký tự) và `*Balance` (8 ký tự). Vì không có exact, `*Balance` dài hơn, nên **`read-only=false`** được chọn. Điều này có thể bất ngờ nếu người viết tưởng prefix `get*` luôn quan trọng hơn suffix.

Bổ sung:

```xml
<tx:method name="getBalance" read-only="true"/>
```

thì exact `getBalance` thắng cả hai wildcard. Độ dài chuỗi mẫu là quy tắc lựa chọn của implementation Spring hiện dùng, **không phải phép chấm điểm ngữ nghĩa “đọc” quan trọng hơn “ghi”**.

### 4.3. Mẫu chồng lấn có cùng độ dài

Ví dụ `get*` và `*By` cùng có 4 ký tự; với method `getBy`, cả hai có thể khớp. Không nên dựa vào vị trí hai element XML để suy ra một luật sẽ luôn thắng qua mọi thay đổi cấu hình/phiên bản. Chọn một trong hai cách an toàn:

- Thêm `<tx:method name="getBy" .../>` với policy rõ ràng.
- Đổi pattern/service naming để các nhóm không giao nhau về mặt nghiệp vụ.

**Lưu ý:** không coi “mẫu dài nhất” là “mẫu có ít wildcard nhất”. Một tên mẫu dài không tự bảo đảm ngữ nghĩa hẹp hơn trong tất cả trường hợp; khi các wildcard chồng lấn, nên chọn exact hoặc chia lại nhóm.

### 4.4. Một method nhận toàn bộ chính sách từ luật được chọn

Nếu cấu hình:

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="getAccount" propagation="REQUIRES_NEW"/>
    <tx:method name="*" rollback-for="java.lang.Exception"/>
</tx:attributes>
```

thì method `getAccount` được chọn theo **luật exact**, với `propagation=REQUIRES_NEW`. Không được suy luận “Spring sẽ ghép `read-only=true` của `get*` và `rollback-for` của `*` lên exact”. Các attribute không được kế thừa hoặc cộng gộp qua các `<tx:method>` cùng khớp. Mỗi luật có giá trị riêng và các phần thiếu dùng **giá trị mặc định của transaction attribute**, ví dụ `read-only=false`, thay vì lấy từ luật wildcard bên dưới.

Đây là lý do cần khai đủ thuộc tính quan trọng trong một luật chuyên biệt, đặc biệt khi nó có thể thay đổi ngữ nghĩa so với nhóm mặc định.

## 5. Các thuộc tính transaction gắn vào từng mẫu

Các thuộc tính thường dùng trong `<tx:method>`:

| Thuộc tính | Giá trị / ý nghĩa | Mặc định phổ biến |
| --- | --- | --- |
| `name` | Tên method hoặc mẫu wildcard; **bắt buộc** | Không có |
| `propagation` | `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`, `NESTED` | `REQUIRED` |
| `isolation` | `DEFAULT`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, ... | `DEFAULT` |
| `read-only` | Hint cho giao dịch đọc; không phải cơ chế phân quyền | `false` |
| `timeout` | Số giây, khi transaction manager/loại transaction hỗ trợ | `-1` (dùng mặc định hệ thống) |
| `rollback-for` | Các exception type name/pattern cần rollback, cách nhau dấu phẩy | RuntimeException và Error theo mặc định; checked Exception không mặc định rollback |
| `no-rollback-for` | Các exception type name/pattern không dẫn đến rollback | Không có luật bổ sung |

Với `propagation=REQUIRED`, nếu chưa có transaction, Spring mở mới; nếu đã có transaction phù hợp, method thường tham gia transaction đó. `REQUIRES_NEW` tạo transaction độc lập và có thể tạm ngưng transaction ngoài; không nên chọn chỉ vì muốn “lưu ngay”. `SUPPORTS` có thể chạy **không có transaction thực** nếu caller không có transaction. `read-only=true` là hint cho tối ưu hoặc áp dụng quy tắc phía DB tùy manager/driver, **không bảo đảm cấm tuyệt đối mọi câu SQL ghi**.

Các thuộc tính `isolation`, `timeout`, `read-only` thường có ý nghĩa cấu hình cho **transaction được tạo mới** và có những giới hạn cụ thể khi method chỉ tham gia transaction hiện hữu. Khi muốn đổi isolation hoặc timeout, phải xác định transaction thực sự được mở ở scope nào.

### 5.1. Rollback rules không phải method-name precedence

Có **hai phép chọn khác nhau**:

1. Spring chọn **một** luật `<tx:method name="...">` theo exact/wildcard.
2. Khi method ném exception, trong chính luật đã chọn, Spring quyết định rollback theo exception rules: `rollback-for`, `no-rollback-for` và quy tắc mặc định.

Ví dụ:

```xml
<tx:attributes>
    <tx:method name="save*" rollback-for="demo.xmltx.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

`saveThenFail` ném checked `BusinessException` thì luật `save*` ra quyết định rollback. Luật `*` **không tiếp tục được xem xét để “bù” thuộc tính rollback**.

Khác biệt về wildcard:

- `name="save*"`: `*` là wildcard cho **tên method**.
- `rollback-for="demo.xmltx.BusinessException"`: biểu thức khớp **tên loại exception** theo cơ chế Spring rollback rule; **không** dùng ký tự `*` để tạo glob. Ưu tiên tên exception đầy đủ để tránh khớp nhầm một class có tên chứa chuỗi giống nhau.
- Nếu vừa có `rollback-for` vừa có `no-rollback-for` trong **cùng luật**, quy tắc exception khớp mạnh hơn quyết định kết quả. Đây là một hệ ưu tiên **khác** thứ tự các mẫu method.

Nếu không cấu hình ngoại lệ, Spring mặc định rollback với `RuntimeException` và `Error`; checked `Exception` thông thường không mặc định kích hoạt rollback. Nuốt exception trong method cũng có thể khiến transaction kết thúc bình thường, trừ khi transaction đã bị đánh dấu rollback-only.

## 6. Bảng kết quả của một bộ quy tắc có ngoại lệ

Xét cấu hình xuyên suốt bài:

```xml
<tx:attributes>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" rollback-for="demo.xmltx.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Giả định các lời gọi **đều đi qua proxy** và khớp pointcut service. Ta thu được:

| Method | Mẫu được chọn | Propagation | Read-only | Chính sách rollback |
| --- | --- | --- | --- | --- |
| `getSnapshot()` | `get*` | `REQUIRED` (mặc định) | `true` | Mặc định |
| `getAndChangeBalance(5)` | `getAndChangeBalance` (exact) | `REQUIRED` | `false` | Mặc định |
| `saveThenFail(20)` | `save*` | `REQUIRED` | `false` | Rollback cả `BusinessException` |
| `updateBalance(3)` | `*` | `REQUIRED` | `false` | Mặc định |
| `deleteAccount()` | `*` | `REQUIRED` | `false` | Mặc định |

Các dòng ghi rõ **đặc tính transaction**, không nói method đã thật sự ghi DB hay chưa. `read-only=true` không biến method thành lệnh SELECT; nếu đặt nhầm cho một method ghi, hành vi phụ thuộc resource/transaction manager, có thể bị ngăn hoặc tối ưu sai hướng.

Một cách tự kiểm chứng policy là quan sát trong method:

```java
TransactionSynchronizationManager.isActualTransactionActive();
TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

Hai API trên cho biết trạng thái transaction mà Spring nhìn thấy trên thread tại thời điểm gọi. Chúng hữu ích để test cấu hình imperative JDBC/JPA, nhưng không thay thế kiểm thử commit/rollback thật. Ở reactive transaction, ngữ cảnh không đơn giản là thread-local tương tự.

## 7. Ví dụ đầy đủ: Spring XML, JDBC, H2 và quy tắc ưu tiên

Ví dụ dưới đây là **một project Gradle độc lập**, dùng **Java 17 + Spring Framework 6.2.12 + H2** và cấu hình bằng XML thuần, không cần Spring Boot, không gắn `@Transactional` lên service. Điểm cần thấy là chính XML đã điều khiển transaction.

Cấu trúc:

```text
xml-transaction-policy/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/xmltx/
    │   ├── App.java
    │   ├── AccountService.java
    │   └── BusinessException.java
    └── resources/
        └── tx-context.xml
```

### 7.1. Dependency và bản Java

**`settings.gradle`**

```groovy
rootProject.name = 'xml-transaction-policy'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-aop:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    implementation 'org.springframework:spring-tx:6.2.12'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.xmltx.App'
}
```

`spring-context` đọc XML và tạo bean; `spring-tx` cung cấp transaction advice; `spring-jdbc` hỗ trợ `JdbcTemplate` và `JdbcTransactionManager`; `spring-aop` cùng `aspectjweaver` xử lý biểu thức `execution(...)`. H2 là database in-memory cho demo. Nếu dự án quản lý phiên bản Spring qua BOM hoặc version catalog, giữ các phiên bản module Spring đồng bộ.

### 7.2. XML configuration hoàn chỉnh

**`src/main/resources/tx-context.xml`**

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

    <!-- Chỉ dùng DriverManagerDataSource trong ví dụ nhỏ. -->
    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xmlpolicy;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbc"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="accountService" class="demo.xmltx.AccountService">
        <constructor-arg ref="jdbc"/>
    </bean>

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <!-- Exact: một method get* thực tế lại ghi dữ liệu. -->
            <tx:method name="getAndChangeBalance"
                       propagation="REQUIRED" read-only="false"/>

            <!-- Mọi get* khác chỉ đọc. -->
            <tx:method name="get*" read-only="true"/>

            <!-- Checked exception nghiệp vụ cũng rollback. -->
            <tx:method name="save*"
                       rollback-for="demo.xmltx.BusinessException"/>

            <!-- Mọi method khác có transaction mặc định. -->
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="accountServiceOps"
                      expression="execution(* demo.xmltx.AccountService.*(..))"/>
        <aop:advisor pointcut-ref="accountServiceOps"
                     advice-ref="txAdvice"/>
    </aop:config>
</beans>
```

**Lưu ý về namespace và wiring:**

- `transaction-manager="txManager"` phải trỏ đến đúng bean. Nếu bỏ thuộc tính này, `<tx:advice>` mặc định tìm tên `transactionManager`; bean trong ví dụ lại tên `txManager` nên cần khai rõ.
- `<aop:advisor>` gắn lời gọi service với `txAdvice`. Chỉ `<tx:advice>` mà thiếu advisor/pointcut thì service không tự nhận transaction từ cấu hình này.
- `AccountService` trong demo là lớp public, không final, các method giao dịch public; Spring có thể tạo class-based proxy vì service không implement interface. Tạo service bằng `new` ngoài container sẽ bỏ qua advice.
- `DriverManagerDataSource` không dùng connection pooling; demo ngắn phù hợp, nhưng production nên dùng pool như HikariCP.
- Không cần `<tx:annotation-driven/>` trong ví dụ vì policy được chỉ định **bằng XML theo tên method**, không phải metadata annotation.

### 7.3. Java service và checked exception

**`src/main/java/demo/xmltx/BusinessException.java`**

```java
package demo.xmltx;

public class BusinessException extends Exception {
    public BusinessException(String message) {
        super(message);
    }
}
```

**`src/main/java/demo/xmltx/AccountService.java`**

```java
package demo.xmltx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String getSnapshot() {
        Long balance = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1", Long.class);
        return "balance=" + balance + ", " + txState();
    }

    public void getAndChangeBalance(long delta) {
        System.out.println("exact getAndChangeBalance: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
    }

    public void saveThenFail(long delta) throws BusinessException {
        System.out.println("saveThenFail: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
        throw new BusinessException("checked failure");
    }

    public void updateBalance(long delta) {
        System.out.println("fallback updateBalance: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
    }

    private String txState() {
        return "tx="
            + TransactionSynchronizationManager.isActualTransactionActive()
            + ", readOnly="
            + TransactionSynchronizationManager.isCurrentTransactionReadOnly();
    }
}
```

Method `txState()` là private helper để **quan sát trạng thái**, không cần advice riêng; lời gọi từ các public methods diễn ra khi transaction tương ứng đang mở. Method `saveThenFail()` cố ý ném **checked exception** sau SQL để chứng minh tác dụng của `rollback-for` trong mẫu `save*`.

### 7.4. Tạo bảng, gọi proxy và kiểm tra output

**`src/main/java/demo/xmltx/App.java`**

```java
package demo.xmltx;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class App {
    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("tx-context.xml")) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE accounts (id BIGINT PRIMARY KEY, balance BIGINT NOT NULL)");
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (1, 100)");

            AccountService service = context.getBean(AccountService.class);

            System.out.println("initial: " + service.getSnapshot());

            service.getAndChangeBalance(5);
            System.out.println("after exact: " + service.getSnapshot());

            try {
                service.saveThenFail(20);
            } catch (BusinessException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
            System.out.println("after rollback: " + service.getSnapshot());

            service.updateBalance(3);
            System.out.println("after fallback: " + service.getSnapshot());
        }
    }
}
```

Nếu project có Gradle Wrapper (chạy `gradle wrapper` bằng một Gradle phù hợp nếu chưa có), lệnh thực thi trên Linux/macOS:

```bash
./gradlew run
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run
```

**Các dòng in từ chương trình, theo thứ tự** (các log của Spring/Gradle có thể xuất hiện thêm):

```text
initial: balance=100, tx=true, readOnly=true
exact getAndChangeBalance: tx=true, readOnly=false
after exact: balance=105, tx=true, readOnly=true
saveThenFail: tx=true, readOnly=false
caught: checked failure
after rollback: balance=105, tx=true, readOnly=true
fallback updateBalance: tx=true, readOnly=false
after fallback: balance=108, tx=true, readOnly=true
```

Diễn giải từng bước:

1. `getSnapshot` khớp `get*`: Spring tạo read-only transaction; `tx=true, readOnly=true`. Số dư 100.
2. `getAndChangeBalance` khớp exact: transaction read-write dù tên có tiền tố `get`; cập nhật cộng 5, commit khi proxy method kết thúc. Số dư thành 105.
3. `saveThenFail` khớp `save*`, chạy UPDATE cộng 20 rồi ném `BusinessException`. Vì `rollback-for` được cấu hình cho checked exception này, transaction rollback; số dư sau đó vẫn là 105.
4. `updateBalance` không khớp exact/get*/save*, nên nhận `*`: transaction read-write và commit thành công; số dư cuối cùng 108.

Đây là một ví dụ **XML policy thực thi được** với dependency và cấu trúc project đã nêu; `jdbc.execute` khởi tạo schema ở đầu main, nên không cần công cụ migration trong ví dụ ngắn. Nếu chỉ copy riêng các đoạn Java mà chưa có XML và dependency, chương trình sẽ không chạy.

### 7.5. Vì sao kết quả khác khi gọi sai cách?

- Nếu gọi `new AccountService(jdbc).saveThenFail(...)` ngoài Spring context, service không được proxy, `@Transactional` cũng không có trong code, nên không có XML transaction advice; JDBC có thể chạy autocommit và UPDATE không được rollback như kỳ vọng.
- Nếu một method trong `AccountService` gọi trực tiếp `this.saveThenFail(...)`, self-invocation không đi qua proxy của Spring AOP; **không** áp dụng lời khuyên transaction riêng của tên method được gọi. Nếu đang trong transaction của method ngoài, SQL vẫn có thể tham gia transaction đó, nhưng policy `save*` không tự được áp dụng cho lời gọi nội bộ.
- Nếu xóa `<aop:advisor>` hay viết sai pointcut, các `<tx:method>` có thể vẫn parse hợp lệ nhưng không áp dụng lên lời gọi mong muốn.
- Nếu đặt `<tx:method name="get*" read-only="true"/>` mà quên exact `getAndChangeBalance`, method ghi sẽ nhận read-only hint; hành vi có thể khác theo DB/driver. Không viết method ghi dưới tên có vẻ đọc nếu có thể tránh.

## 8. Phân biệt thứ tự XML, độ đặc hiệu mẫu và thứ tự AOP advisor

Ba khái niệm thường bị trộn lẫn:

| Cơ chế | Điều khiển | Có phải `<tx:method>` phía trên thắng? |
| --- | --- | --- |
| Exact/wildcard name matching | Chọn một transaction attribute cho **tên method** | Không; exact trước, wildcard cụ thể hơn |
| `<aop:advisor order="...">` | Thứ tự áp dụng **nhiều advisor/aspect** trên cùng join point | Không liên quan cách chọn `name` |
| `rollback-for` và `no-rollback-for` | Quyết định rollback khi exception xuất hiện trong **luật đã được chọn** | Không; exception rule khớp mạnh hơn quyết định |

Nếu có hai advisor khác nhau đều chọn cùng method, có thể có hai chuỗi advice với transaction semantics khác nhau. Không nên nghĩ XML của advisor A có `get*` thì sẽ được “trộn” với `save*` của advisor B thành một chính sách duy nhất. Hãy giới hạn pointcut, điều phối thứ tự advisor và giảm chính sách chồng chéo. Khi kết hợp `<tx:annotation-driven/>`/`@Transactional` với XML `<tx:advice>` trên cùng bean, cần kiểm thử rõ cơ chế nào thực sự chặn lời gọi; đừng tự giả định một phía tự động ghi đè phía kia.

Nếu dùng `<tx:annotation-driven/>`, transaction attributes thường đến từ annotation trên class/method; cú pháp `<tx:method>` **không phải tên một trường của `@Transactional`**. Bài này chỉ nói về **XML declarative transaction policy by method name**.

## 9. Một số tình huống dễ sai

### 9.1. Bỏ fallback làm một số method không được cấu hình transaction

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" propagation="REQUIRED"/>
</tx:attributes>
```

`deleteAccount` không khớp luật nào, vì vậy advice này không mở transaction cho method đó. Nếu yêu cầu tất cả method service đều transactional, thêm `<tx:method name="*"/>` hoặc làm pointcut/nhóm policy tương ứng. Nếu chủ ý có method không giao dịch, việc bỏ fallback là một lựa chọn thiết kế hợp lý nhưng cần test.

### 9.2. Một mẫu quá rộng khiến method bị đổi semantics ngoài dự định

`get*` có thể chọn nhầm một method ghi như `getOrCreateUser`; `save*` có thể tác động đến một method chỉ kiểm tra/cập nhật cache. Hãy ưu tiên **đặt tên method thể hiện hành vi thực**, dùng exact cho ngoại lệ và kiểm thử policy khi refactor tên API.

### 9.3. Dựa vào thứ tự XML để giải quyết pattern overlap

Đổi thứ tự giữa `get*` và `*Balance` không phải một cách giải quyết đáng tin. Hãy nhìn độ dài mẫu, thêm exact khi cần, và tránh cùng độ dài khớp chồng lấn. Việc sửa tên method có thể làm đổi luật áp dụng mà không gây lỗi compile.

### 9.4. Nghĩ `read-only=true` là cơ chế ngăn mọi lệnh UPDATE

`read-only` là một hint/config của transaction; một số manager/driver/database có thể áp dụng enforcement khác nhau. Nó không phải security boundary. Kiểm soát quyền ở DB, kiểm thử hành vi ghi và sử dụng transaction read-write cho các method thật sự thay đổi dữ liệu.

### 9.5. Đọc chính sách trên một method nhưng gọi qua nội bộ bean

Spring AOP proxy thông thường áp dụng advice cho lời gọi **đi vào qua proxy**. `this.saveAccount()` trong cùng object không tự chọn lại luật `save*`. Tách service, gọi qua Spring bean phù hợp hoặc thiết kế transaction boundary rõ ràng thay vì dựa vào self-invocation.

### 9.6. Đặt `rollback-for` ở wildcard nhưng mong exact được kế thừa

Nếu exact match xuất hiện và không có `rollback-for`, exact nhận rollback semantics mặc định của nó; luật wildcard không “cấp thêm” rollback rule. Muốn một checked exception khiến cả exact và fallback rollback, phải khai rõ cho từng luật liên quan hoặc thiết kế lại nhóm cấu hình.

### 9.7. Dùng XML cho nhiều layer cùng lúc

Pointcut như `execution(* com.example..*(..))` quá rộng có thể bọc cả controller, repository và utility; nhiều nested transaction scope tạo ra hành vi khó kiểm soát. Nên chọn **service boundary** làm nơi khai báo transaction nghiệp vụ, với pointcut rõ. Chỉ mở rộng khi có lý do kỹ thuật được kiểm chứng.

### 9.8. Chọn sai transaction manager hoặc resource

`<tx:advice transaction-manager="txManager">` không tự tạo `DataSource` hay `EntityManagerFactory`. Với JDBC dùng manager tương thích DataSource; với JPA cần manager phù hợp JPA. Có nhiều DB/manager thì phải xác định rõ advisor dùng bean nào. Một `@Transactional`/`<tx:advice>` đơn lẻ không tạo distributed transaction cho nhiều resource không có cơ chế điều phối.

## 10. Quy trình thiết kế và kiểm thử policy XML

Trước khi đưa bộ luật vào một module thực tế:

1. **Liệt kê các public service methods** thuộc pointcut, bao gồm method sau khi đổi tên/refactor.
2. **Phân nhóm hành vi:** đọc, ghi, thao tác đặc biệt cần propagation/timeout/rollback khác.
3. **Đặt fallback có chủ đích:** `*` nếu muốn mọi method được pointcut chọn có transaction; không đặt nếu các method còn lại chủ ý không thuộc advice.
4. **Thêm exact match** cho ngoại lệ có thể khớp nhiều mẫu hoặc tên đánh lừa như `getAndChangeBalance`.
5. **Kiểm tra overlap wildcard:** mẫu nào dài hơn; có hai mẫu cùng độ dài cùng khớp không; nếu có, loại bỏ tính mơ hồ.
6. **Ghi rõ các attr khác mặc định:** propagation, read-only, rollback-for và những thuộc tính cần áp dụng, không dựa vào “kế thừa” từ `*`.
7. **Kiểm thử bằng proxy thật** và một database có transaction: quan sát transaction active, readOnly, commit và rollback sau exception; kiểm tra method ngoài pointcut.
8. **Kiểm thử sau đổi tên method** hoặc sửa thứ tự/loại advisor; những thay đổi này không nhất thiết tạo lỗi compile dù semantics transaction đã khác.

Có thể lập bảng expected policy trong tài liệu hoặc test tích hợp:

| Method | Mong đợi | Bằng chứng |
| --- | --- | --- |
| `getSnapshot` | `get*` read-only | `tx=true, readOnly=true` |
| `getAndChangeBalance` | Exact read-write | `readOnly=false` và ghi commit |
| `saveThenFail` | `save*` rollback checked `BusinessException` | Sau exception, DB giữ số dư 105 |
| `updateBalance` | Fallback `*` read-write | Sau return, DB có số dư 108 |

Trong test Spring, cần cẩn thận nếu test method tự được bọc trong `@Transactional`: dữ liệu có thể bị rollback bởi transaction **của test** sau khi assertion chạy, làm lệch quan sát commit của service. Muốn kiểm tra commit thật, hãy gọi service từ scope không có transaction ngoài hoặc thiết kế test transaction boundary rõ ràng.

## 11. Câu hỏi kiểm tra hiểu bài

**1. `getAccount` khớp `get*`, `*Account` và `*`. Luật nào thắng khi không có exact?**  
`*Account` có chuỗi mẫu dài hơn `get*` và `*`, nên được chọn trong `NameMatchTransactionAttributeSource`.

**2. Nếu thêm `<tx:method name="getAccount" read-only="true"/>` ở cuối danh sách thì sao?**  
Exact match thắng các wildcard. Không phụ thuộc vị trí cuối.

**3. Luật exact chỉ ghi `propagation=REQUIRES_NEW` có tự lấy `read-only=true` từ `get*` không?**  
Không. Spring chọn một transaction attribute; thuộc tính thiếu nhận mặc định, không được ghép từ wildcard khác.

**4. Hai mẫu cùng độ dài cùng khớp tên method thì nên làm gì?**  
Không dựa vào thứ tự XML như một hợp đồng nghiệp vụ. Thêm luật exact hoặc thiết kế lại mẫu để không xung đột.

**5. Tại sao method khớp `save*` nhưng không rollback như mong đợi?**  
Kiểm tra pointcut, lời gọi có đi qua proxy không, manager đúng không, exception bị nuốt hay không và checked exception đã được khai `rollback-for` chưa.

**6. `name="save*"` có khớp mọi method Java tên bất kỳ chữ hoa/chữ thường không?**  
Không; simple match phân biệt chữ hoa/chữ thường, nên `SaveAccount` không khớp `save*`.

**7. Nếu method khớp AOP pointcut nhưng không khớp luật tên method nào thì sao?**  
Advice này không cung cấp transaction attribute cho method; không tự mở giao dịch chỉ nhờ pointcut.

## 12. Ghi nhớ

**Cấu hình XML giao dịch theo tên method là phép giao của AOP pointcut và chính sách `<tx:method>`.** Khi method nằm trong phạm vi advice, Spring ưu tiên **tên chính xác**, sau đó **mẫu wildcard khớp dài nhất**, và `*` là fallback. Một khi đã chọn được luật, Spring sử dụng **toàn bộ transaction attributes của luật đó** với giá trị mặc định cho các thuộc tính chưa khai; không ghép chính sách từ nhiều luật.

Bởi vậy, bộ chính sách dễ bảo trì thường có **naming convention rõ**, một số **exact exception rules**, các **wildcard nhóm** không mơ hồ, **fallback được lựa chọn có chủ đích** và test qua **Spring proxy + database thật sự có transaction**.

## Tài liệu tham khảo

- Spring Framework 6.2, *Example of Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/first-example.html
- Spring Framework 6.2, *`<tx:advice/>` Settings*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework 6.2, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework, *Understanding Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *Using `@Transactional`*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework API, *NameMatchTransactionAttributeSource*: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/interceptor/NameMatchTransactionAttributeSource.html
- Spring Framework API, *TransactionSynchronizationManager*: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
