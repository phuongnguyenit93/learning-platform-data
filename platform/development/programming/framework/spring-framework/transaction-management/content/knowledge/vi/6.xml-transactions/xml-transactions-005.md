# Cấu hình manager, rollback-for và no-rollback-for bằng XML trong Spring Framework

## 1. Học được gì và dùng khi nào?

Trong Spring Framework, **declarative transaction management** cho phép tách việc quản lý transaction khỏi code nghiệp vụ. Thay vì gọi `commit()` và `rollback()` thủ công, ta khai báo quy tắc trong XML; Spring AOP áp dụng quy tắc cho lời gọi phương thức service.

Bài này thuộc phần **Cấu hình XML** của Spring transaction management, tập trung vào ba yêu cầu:

1. **Manager:** cấu hình một `PlatformTransactionManager` phù hợp với nguồn dữ liệu, đặt đúng tên bean và liên kết với transaction advice.
2. **`rollback-for`:** buộc rollback với một số exception cụ thể, đặc biệt **checked exception** vốn không làm Spring rollback theo mặc định.
3. **`no-rollback-for`:** loại trừ việc rollback do một exception cụ thể, kể cả **unchecked exception** vốn mặc định gây rollback.

Mục tiêu sau bài học là đọc được cấu hình `<tx:advice>`, `<tx:method>` và `<aop:advisor>`; biết lúc nào transaction được commit hay rollback; tự chạy ví dụ Java 17+ có các case dễ so sánh; và tránh sai sót về pattern exception, pointcut, manager, scope transaction.

**Tình huống mẫu:** Một dịch vụ ghi bản ghi vào database. Lỗi nghiệp vụ kiểm tra đầu vào `BusinessFailureException` là checked exception nhưng yêu cầu rollback. Ngược lại, một cảnh báo `NonFatalOperationException` là unchecked exception nhưng dữ liệu đã ghi trước đó có thể được giữ lại. Hai chính sách nằm trong XML, còn service Java không cần annotation `@Transactional`.

## 2. Cơ chế kết nối giữa manager, advice và AOP

```text
Caller
  |
  v
Spring AOP proxy
  |  <aop:advisor> liên kết pointcut + txAdvice
  v
TransactionInterceptor
  |
  +-- <tx:advice transaction-manager="txManager">
  |     <tx:method name="..." rollback-for="..." no-rollback-for="...">
  |
  +-- txManager: PlatformTransactionManager
  |     DataSourceTransactionManager / JpaTransactionManager / ...
  |
  +-- bắt đầu hoặc tham gia transaction
  |
  +-- gọi phương thức service nghiệp vụ
  |
  +-- method trả về / exception thoát ra
  |
  +-- commit hoặc rollback theo rule và trạng thái thực tế
  v
Caller nhận kết quả hoặc exception
```

Đọc vai trò từng phần:

| XML / thành phần | Trách nhiệm |
| --- | --- |
| `<bean id="dataSource">` | Cung cấp connection tới database |
| `<bean id="txManager">` | Quản lý transaction vật lý phù hợp nguồn dữ liệu |
| `<tx:advice id="txAdvice" transaction-manager="txManager">` | Khai báo transaction metadata gắn với manager nào |
| `<tx:attributes>` và `<tx:method>` | Chọn chính sách transaction theo tên phương thức |
| `<aop:pointcut>` | Chọn những lời gọi service nào được áp dụng advice |
| `<aop:advisor>` | Gắn pointcut với `txAdvice` để tạo proxy |

**Chỉ khai báo transaction manager không tự biến mọi method thành transactional.** Tương tự, chỉ khai báo `<tx:advice>` mà thiếu advisor/pointcut thì vẫn chưa xác định lời gọi nào được can thiệp. `TransactionInterceptor` chỉ có cơ hội quyết định rollback khi phương thức được gọi **qua proxy**.

## 3. Cấu hình transaction manager bằng XML

### 3.1. Cấu hình JDBC đơn giản

```xml
<bean id="dataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <property name="driverClassName" value="org.h2.Driver"/>
    <property name="url" value="jdbc:h2:mem:xml_tx;DB_CLOSE_DELAY=-1"/>
    <property name="username" value="sa"/>
    <property name="password" value=""/>
</bean>

<bean id="txManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
</bean>

<bean id="jdbcTemplate"
      class="org.springframework.jdbc.core.JdbcTemplate">
    <constructor-arg ref="dataSource"/>
</bean>
```

Trong ví dụ:

- `dataSource` tạo JDBC connection. `DriverManagerDataSource` phù hợp bài thực hành vì không cần cấu hình connection pool; hệ thống production thường sử dụng một pool như HikariCP.
- `txManager` là `DataSourceTransactionManager`, phù hợp transaction cục bộ của **một JDBC DataSource**. Nó điều khiển lifecycle của connection đang tham gia transaction.
- `jdbcTemplate` được cấu hình với **cùng bean `dataSource`**. Vì thế các lệnh SQL của service tham gia transaction mà Spring manager điều khiển.
- Nếu `txManager` dùng DataSource A nhưng DAO/JdbcTemplate dùng DataSource B không liên quan, rollback ở A không tự rollback câu SQL ở B.
- `JdbcTransactionManager` là biến thể nâng cao của `DataSourceTransactionManager` hỗ trợ dịch ngoại lệ commit/rollback. Dùng `DataSourceTransactionManager` ở đây để thấy mẫu XML cơ bản.

### 3.2. Chọn manager phù hợp với công nghệ

| Trường hợp | Manager thường dùng | Lưu ý |
| --- | --- | --- |
| JDBC với một `DataSource` | `DataSourceTransactionManager` hoặc `JdbcTransactionManager` | Cần DAO tham gia connection do Spring quản lý |
| JPA | `JpaTransactionManager` | Gắn với `EntityManagerFactory` thích hợp |
| JTA/XA | `JtaTransactionManager` | Cần hạ tầng transaction tương ứng |
| Reactive transaction | `ReactiveTransactionManager` thích hợp | Không dùng semantics thread-bound JDBC của ví dụ này |

Các manager không thể hoán đổi tùy ý chỉ vì cùng được khai báo bằng XML. Với nhiều nguồn dữ liệu, hai JDBC manager cục bộ **không tự tạo một distributed transaction**; cần thiết kế riêng nếu nghiệp vụ đòi hỏi atomicity xuyên nhiều resource.

### 3.3. Tên bean manager có ý nghĩa

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

`transaction-manager="txManager"` phải trùng `id` của transaction manager bean. Nếu bean tên `transactionManager`, thường có thể **bỏ** thuộc tính `transaction-manager` trong `<tx:advice>` vì đó là tên mặc định mà namespace kỳ vọng. Nếu manager tên `txManager`, phải chỉ rõ như trên. Sai tên bean có thể khiến `ApplicationContext` không tạo được advice; chọn nhầm manager với database khác còn nguy hiểm hơn vì transaction không bao phủ dữ liệu mong muốn.

## 4. Khai báo tx:advice và aop:advisor

Một đoạn XML đủ để thấy cơ chế chọn phương thức:

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

    <!-- Các bean txManager, dataSource, orderService cần được khai báo thêm. -->

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="get*" read-only="true"/>
            <tx:method name="save*" propagation="REQUIRED"/>
            <tx:method name="*"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="serviceMethods"
                      expression="execution(* demo.OrderService.*(..))"/>
        <aop:advisor advice-ref="txAdvice"
                     pointcut-ref="serviceMethods"/>
    </aop:config>
</beans>
```

Đây là **fragment minh họa**, không chạy độc lập cho đến khi thêm các bean còn thiếu. Bản hoàn chỉnh ở mục 7.

Giải thích:

- `<tx:method name="get*" read-only="true"/>` áp dụng metadata cho method bắt đầu bằng `get`.
- `name="save*"` áp dụng cho các tên bắt đầu bằng `save`.
- `name="*"` là rule dự phòng cho các tên còn lại.
- `<aop:pointcut>` chọn execution của các method trên interface `demo.OrderService`.
- `<aop:advisor>` gắn transaction advice vào các method mà pointcut chọn.
- Advice được áp dụng khi caller lấy bean service từ Spring và gọi qua proxy. Gọi một đối tượng tạo bằng `new` không đi qua interceptor; self-invocation bằng `this.otherMethod()` trong cùng bean cũng có thể bỏ qua proxy.

Các thuộc tính của `<tx:method>` thường dùng:

| Thuộc tính | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `name` | `save*`, `get*`, `*` | Mẫu tên method, hỗ trợ ký tự wildcard `*` |
| `propagation` | `REQUIRED`, `REQUIRES_NEW`, `NESTED` | Quan hệ transaction với caller |
| `isolation` | `DEFAULT`, `READ_COMMITTED` | Mức cô lập |
| `timeout` | `30` | Timeout tính theo giây, tùy transaction manager |
| `read-only` | `true` | Hint cho thao tác đọc, không phải lệnh cấm ghi tuyệt đối |
| `rollback-for` | `demo.BusinessFailureException` | Exception pattern cần rollback |
| `no-rollback-for` | `demo.NonFatalOperationException` | Exception pattern cần tránh rollback |

Đối với transaction đã tồn tại trong outer scope, `REQUIRED` sẽ tham gia transaction đó. Khi ấy isolation/timeout/read-only của inner metadata thường không thay đổi những đặc tính đã được quyết định lúc tạo transaction vật lý. Muốn kiểm chứng policy ở ví dụ, ta gọi service từ caller không có outer transaction.

## 5. Rollback mặc định khi chưa khai báo rule

Spring declarative transaction thông thường quyết định dựa trên exception **thoát ra khỏi transactional interceptor**:

| Kết thúc method | Default nếu manager sở hữu transaction |
| --- | --- |
| Return bình thường | Commit, trừ khi đã rollback-only hoặc gặp lỗi khác |
| Ném `RuntimeException` | Rollback |
| Ném `Error` | Rollback |
| Ném checked exception, ví dụ `IOException` | Thường commit, sau đó truyền exception cho caller |
| Checked exception bị cấu hình `rollback-for` | Rollback |
| Unchecked exception bị cấu hình `no-rollback-for` | Có thể commit, sau đó vẫn truyền exception cho caller |

Mặc định của `<tx:advice>`: propagation `REQUIRED`, isolation `DEFAULT`, read-write, timeout phụ thuộc underlying transaction system; unchecked runtime/error rollback, checked exception không rollback.

Điểm cần nhớ: **exception không đồng nghĩa rollback**. Một method có thể INSERT thành công rồi ném checked exception; interceptor vẫn commit theo default và sau đó ném lại exception. Đây là lý do Spring khuyên khai báo rollback policy khớp với ý nghĩa nghiệp vụ, không chỉ kiểu exception.

Nếu exception bị bắt và xử lý bên trong method trước khi quay về interceptor, transaction interceptor chỉ thấy **return bình thường**; các rule trong XML sẽ không tự kích hoạt bởi exception đã bị nuốt. Khi cần rollback trong tình huống đó, có thể ném lại exception phù hợp hoặc chủ động đánh dấu rollback-only với API Spring, sau khi cân nhắc ảnh hưởng đến outer transaction.

## 6. Cú pháp rollback-for và no-rollback-for

### 6.1. rollback-for: hủy cả khi gặp checked exception

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveCheckedRollback"
                   rollback-for="demo.BusinessFailureException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

Nếu `saveCheckedRollback()` thực hiện INSERT rồi ném `BusinessFailureException` (checked) ra khỏi proxy, XML rule chỉ định rollback. Khi không có rule này, checked exception thường dẫn đến commit vì default chỉ rollback với `RuntimeException`/`Error`.

### 6.2. no-rollback-for: giữ dữ liệu dù gặp exception

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveUncheckedNoRollback"
                   no-rollback-for="demo.NonFatalOperationException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

`NonFatalOperationException` kế thừa `RuntimeException` nhưng được loại trừ rollback ở method này. Nếu interceptor sở hữu transaction và không có cờ rollback-only/lỗi commit khác, Spring **commit**, sau đó **vẫn ném exception** cho caller. `no-rollback-for` không có nghĩa "bỏ qua ngoại lệ" hoặc "bắt lỗi thay cho caller".

Chỉ cấu hình như vậy cho lỗi có tính chất **cảnh báo chấp nhận được**, nơi thay đổi trước đó thực sự được phép giữ. Nếu dữ liệu đã mất tính nhất quán, commit có thể làm lỗi kéo dài trong database.

### 6.3. Khi có cả hai: rule mạnh nhất thắng

```xml
<tx:method name="saveUncheckedNoRollback"
           rollback-for="java.lang.Throwable"
           no-rollback-for="demo.NonFatalOperationException"/>
```

Đây là cách diễn đạt "mọi lỗi khác rollback; riêng cảnh báo này không rollback". Với `NonFatalOperationException`, no-rollback pattern cụ thể hơn khớp ngay trên exception thực tế; rollback pattern `Throwable` chỉ khớp ở một tổ tiên trong hierarchy. Vì vậy **no-rollback rule mạnh hơn được chọn**. Với exception khác không nằm trong rule ngoại lệ, rollback rule rộng có thể được chọn.

Spring **không** đơn giản chọn rule xuất hiện trước/sau trong XML, cũng không mặc định `no-rollback-for` luôn thắng. Khi nhiều rule cùng khớp, nó ưu tiên rule được đánh giá **mạnh nhất** với loại exception đã ném.

### 6.4. XML dùng exception *pattern*, không dùng cú pháp Java Class

Các thuộc tính nhận danh sách tên ngoại lệ phân tách bằng dấu phẩy:

```xml
<tx:method name="import*"
           rollback-for="demo.BusinessFailureException,java.io.IOException"
           no-rollback-for="demo.NonFatalOperationException"/>
```

Các pattern có thể là tên class đầy đủ hoặc một phần tên class. Vì đây là **substring pattern matching** trên tên class trong chuỗi hierarchy, mẫu `Exception` hoặc `RuntimeException` có thể khớp rất rộng. Pattern `demo.BusinessFailureException` cũng có thể khớp `demo.BusinessFailureExceptionV2` do tên chứa cùng đoạn.

**Không có wildcard `*` trong exception patterns.** Ký tự `*` được phép trong `tx:method name="save*"` để chọn tên method, nhưng `rollback-for="*Exception"` không có nghĩa "mọi Exception". Nên dùng tên đầy đủ duy nhất cho exception nghiệp vụ, tránh các chuỗi quá ngắn gây nhầm lẫn.

Khi dùng annotation Java, `@Transactional(rollbackFor = BusinessFailureException.class, noRollbackFor = NonFatalOperationException.class)` là rule **theo class type**; `rollbackForClassName` và `noRollbackForClassName` mới là dạng pattern tương tự XML. Không suy ra quy tắc XML là type-safe như `.class`.

### 6.5. Hai tầng khớp khác nhau

Spring xác định method transaction metadata theo `<tx:method name="...">` trước, sau đó mới quyết định rollback dựa trên exception rules **của metadata đã chọn**.

```xml
<tx:attributes>
    <tx:method name="saveCritical"
               rollback-for="demo.BusinessFailureException"/>
    <tx:method name="save*"
               no-rollback-for="demo.NonFatalOperationException"/>
    <tx:method name="*"/>
</tx:attributes>
```

`saveCritical` khớp quy tắc tên cụ thể hơn `save*`. Spring không mặc định cộng dồn tất cả exception rules của các `tx:method` khác nhau thành một tập. Khi debug, phải xem **method mapping nào đang được áp dụng** rồi mới phân tích exception.

## 7. Dự án Java 17+ chạy được chỉ với XML, Maven, Spring JDBC và H2

Bài thực hành dưới đây dùng Spring Framework **6.2.19** và Java 17+. Mục đích là thấy cùng một thao tác INSERT có thể commit/rollback khác nhau chỉ do XML rules.

Năm ca:

1. `saveOk` trả về bình thường → commit.
2. `saveCheckedDefault` ném checked exception, không có rollback rule riêng → commit.
3. `saveCheckedRollback` ném checked exception, XML `rollback-for` → rollback.
4. `saveUncheckedDefault` ném unchecked exception, default → rollback.
5. `saveUncheckedNoRollback` ném unchecked exception cụ thể, XML `no-rollback-for` thắng rollback rộng → commit.

### 7.1. Cấu trúc thư mục

```text
xml-tx-rules/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── Main.java
    │   ├── OrderService.java
    │   ├── OrderServiceImpl.java
    │   ├── BusinessFailureException.java
    │   └── NonFatalOperationException.java
    └── resources/
        └── applicationContext.xml
```

### 7.2. File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-tx-rules</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp XML context, `spring-jdbc` cung cấp `JdbcTemplate` và manager, `spring-tx` cung cấp abstraction, `spring-aop` + `aspectjweaver` hỗ trợ pointcut; H2 là database in-memory chạy trong JVM.

### 7.3. File applicationContext.xml

**`src/main/resources/applicationContext.xml`**

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
        <property name="url" value="jdbc:h2:mem:xml_tx;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate" class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
        <property name="dataSource" ref="dataSource"/>
    </bean>

    <bean id="orderService" class="demo.OrderServiceImpl">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="saveCheckedRollback"
                       propagation="REQUIRED"
                       rollback-for="demo.BusinessFailureException"/>

            <tx:method name="saveUncheckedNoRollback"
                       propagation="REQUIRED"
                       rollback-for="java.lang.Throwable"
                       no-rollback-for="demo.NonFatalOperationException"/>

            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="orderServiceMethods"
                      expression="execution(* demo.OrderService.*(..))"/>
        <aop:advisor advice-ref="txAdvice"
                     pointcut-ref="orderServiceMethods"/>
    </aop:config>
</beans>
```

Đối chiếu cấu hình: `txManager` và `JdbcTemplate` trỏ cùng `dataSource`; `txAdvice.transaction-manager` trỏ đúng `txManager`; `<aop:advisor>` gắn `txAdvice` với pointcut; rule cụ thể áp dụng cho tên method thật; `name="*"` áp dụng cho các method còn lại.

`<tx:advice>` là metadata, `<aop:config>` mới khiến Spring tạo AOP proxy. Không cần `<tx:annotation-driven>` hoặc `@Transactional` cho dự án này.

### 7.4. Interface service

**`src/main/java/demo/OrderService.java`**

```java
package demo;

public interface OrderService {
    void saveOk(long id);
    void saveCheckedDefault(long id) throws BusinessFailureException;
    void saveCheckedRollback(long id) throws BusinessFailureException;
    void saveUncheckedDefault(long id);
    void saveUncheckedNoRollback(long id);
}
```

**`src/main/java/demo/BusinessFailureException.java`**

```java
package demo;

public class BusinessFailureException extends Exception {
    public BusinessFailureException(String message) {
        super(message);
    }
}
```

**`src/main/java/demo/NonFatalOperationException.java`**

```java
package demo;

public class NonFatalOperationException extends RuntimeException {
    public NonFatalOperationException(String message) {
        super(message);
    }
}
```

`BusinessFailureException` là checked exception do kế thừa trực tiếp `Exception`; `NonFatalOperationException` là unchecked exception vì kế thừa `RuntimeException`. Các class đặt cùng package `demo` để khớp XML exception pattern và pointcut.

### 7.5. Implementation: chỉ xử lý nghiệp vụ, không khai báo transaction

**`src/main/java/demo/OrderServiceImpl.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;

public class OrderServiceImpl implements OrderService {
    private final JdbcTemplate jdbc;

    public OrderServiceImpl(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void insert(long id, String note) {
        jdbc.update(
                "INSERT INTO tx_event(id, note) VALUES (?, ?)",
                id, note);
    }

    @Override
    public void saveOk(long id) {
        insert(id, "normal");
    }

    @Override
    public void saveCheckedDefault(long id) throws BusinessFailureException {
        insert(id, "checked-default");
        throw new BusinessFailureException("checked default");
    }

    @Override
    public void saveCheckedRollback(long id) throws BusinessFailureException {
        insert(id, "checked-rollback");
        throw new BusinessFailureException("checked rollback");
    }

    @Override
    public void saveUncheckedDefault(long id) {
        insert(id, "unchecked-default");
        throw new IllegalStateException("runtime default");
    }

    @Override
    public void saveUncheckedNoRollback(long id) {
        insert(id, "unchecked-no-rollback");
        throw new NonFatalOperationException("non-fatal");
    }
}
```

Mỗi method đều chạy `INSERT` trước khi kết thúc hoặc ném exception. Vì Java không tự điều khiển commit/rollback, trạng thái database sau lời gọi phản ánh **XML transaction rule**.

### 7.6. Main kiểm tra trạng thái đã commit

**`src/main/java/demo/Main.java`**

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("applicationContext.xml")) {

            JdbcTemplate jdbc = context.getBean("jdbcTemplate", JdbcTemplate.class);
            OrderService service = context.getBean("orderService", OrderService.class);

            jdbc.execute("""
                    CREATE TABLE tx_event (
                        id BIGINT PRIMARY KEY,
                        note VARCHAR(80) NOT NULL
                    )
                    """);

            service.saveOk(1L);
            System.out.println("saveOk committed=" + exists(jdbc, 1L));

            try {
                service.saveCheckedDefault(2L);
            } catch (BusinessFailureException expected) {
                System.out.println("caught checked-default");
            }
            System.out.println("checkedDefault committed=" + exists(jdbc, 2L));

            try {
                service.saveCheckedRollback(3L);
            } catch (BusinessFailureException expected) {
                System.out.println("caught checked-rollback");
            }
            System.out.println("checkedRollback committed=" + exists(jdbc, 3L));

            try {
                service.saveUncheckedDefault(4L);
            } catch (IllegalStateException expected) {
                System.out.println("caught unchecked-default");
            }
            System.out.println("uncheckedDefault committed=" + exists(jdbc, 4L));

            try {
                service.saveUncheckedNoRollback(5L);
            } catch (NonFatalOperationException expected) {
                System.out.println("caught unchecked-no-rollback");
            }
            System.out.println("uncheckedNoRollback committed=" + exists(jdbc, 5L));
        }
    }

    private static boolean exists(JdbcTemplate jdbc, long id) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_event WHERE id = ?",
                Integer.class, id);
        return count != null && count > 0;
    }
}
```

`Main` lấy `orderService` từ Spring container nên lời gọi đi qua AOP proxy. Caller không có outer transaction. Khi method trả về hoặc exception thoát ra, interceptor đã hoàn thành commit/rollback trước khi `Main` thực hiện `SELECT COUNT(*)`. Truy vấn đối chiếu vì vậy quan sát dữ liệu sau transaction.

### 7.7. Chạy và kết quả dự kiến

Cần JDK 17+ và Maven; ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng **`Main` in** (không tính log thư viện/Maven):

```text
saveOk committed=true
caught checked-default
checkedDefault committed=true
caught checked-rollback
checkedRollback committed=false
caught unchecked-default
uncheckedDefault committed=false
caught unchecked-no-rollback
uncheckedNoRollback committed=true
```

| ID | Method | Exception | Rule quyết định | Sau khi proxy call kết thúc |
| --- | --- | --- | --- | --- |
| 1 | `saveOk` | Không | Trả về bình thường | Có bản ghi |
| 2 | `saveCheckedDefault` | `BusinessFailureException` | Checked exception mặc định không rollback | Có bản ghi |
| 3 | `saveCheckedRollback` | `BusinessFailureException` | XML `rollback-for` | Không có bản ghi |
| 4 | `saveUncheckedDefault` | `IllegalStateException` | Runtime exception mặc định rollback | Không có bản ghi |
| 5 | `saveUncheckedNoRollback` | `NonFatalOperationException` | XML `no-rollback-for` cụ thể nhất | Có bản ghi |

Nếu XML sai tên method khiến một quy tắc đặc biệt không được chọn, method rơi vào fallback `name="*"`, dẫn đến kết quả khác. Nếu không có advisor/pointcut khớp, INSERT có thể auto-commit vì service bị gọi không qua transaction interceptor; đây là lỗi đặc biệt cần phát hiện bằng test.

## 8. Phân biệt với tx:annotation-driven

Đừng nhầm hai cách cấu hình:

**A. XML advice, không cần annotation trên service:**

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveCheckedRollback"
                   rollback-for="demo.BusinessFailureException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* demo.OrderService.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceOps"/>
</aop:config>
```

**B. XML bật cơ chế đọc annotation `@Transactional`:**

```xml
<tx:annotation-driven transaction-manager="txManager"/>
```

Khi chọn B, method có thể khai báo trong Java:

```java
@Transactional(
    rollbackFor = BusinessFailureException.class,
    noRollbackFor = NonFatalOperationException.class
)
public void operation() throws BusinessFailureException {
    // Logic nghiệp vụ nằm ở đây.
}
```

Đoạn Java trên **chỉ minh họa annotation**, không phải class chạy độc lập. `rollbackFor`/`noRollbackFor` dùng type-safe class reference; `rollbackForClassName`/`noRollbackForClassName` dùng pattern. Còn XML `rollback-for`/`no-rollback-for` là pattern.

`<tx:annotation-driven>` tự cấu hình transaction advisor tương ứng cho annotation. Với `<tx:advice>`, phải liên kết bằng `<aop:advisor>` rõ ràng. Khi chuyển từ XML sang annotations, đối chiếu manager, pointcut, propagation và exception rules; tránh vô tình áp dụng hai advisor chồng lên cùng method.

## 9. Nhiều manager: một ví dụ minh họa

```xml
<bean id="primaryTxManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="primaryDataSource"/>
</bean>

<bean id="auditTxManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="auditDataSource"/>
</bean>

<tx:advice id="primaryAdvice" transaction-manager="primaryTxManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<tx:advice id="auditAdvice" transaction-manager="auditTxManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

Đây là **fragment**, chưa chứa bean DataSource và các advisor. Một advice gắn với một manager cụ thể, nên phải liên kết tới **đúng pointcut** và **đúng DAO/DataSource**. Hai JDBC manager không bảo đảm atomicity giữa hai database; không dùng manager của database A để hy vọng rollback thao tác đã auto-commit trên B.

Nếu áp dụng nhiều transactional advisor cho cùng method, thứ tự xử lý, manager và transaction scope có thể ảnh hưởng kết quả. Hãy xác định ownership và tránh pointcut quá rộng tạo behavior khó dự đoán.

## 10. Hạn chế và lỗi phổ biến

### 10.1. no-rollback-for không ép commit khi transaction hỏng

`no-rollback-for` chỉ nói rằng exception đang xét **không phải lý do để Spring yêu cầu rollback**. Nó không xóa cờ `rollback-only` trước đó, không cứu transaction đã thất bại ở database, và không ngăn outer transaction rollback. Nếu manager không sở hữu transaction vật lý vì đã tham gia outer `REQUIRED`, commit cuối cùng vẫn do outer boundary quyết định.

### 10.2. Dùng pattern exception quá rộng

`rollback-for="Exception"` có thể khớp nhiều loại exception ngoài dự kiến. `no-rollback-for="RuntimeException"` có thể dẫn tới commit những lỗi vốn cần rollback. Dùng tên class đầy đủ, tránh pattern trùng với các class mang hậu tố khác hoặc nested class, và kiểm thử exception hierarchy.

### 10.3. Pointcut không khớp method

`execution(* demo.OrderService.*(..))` chọn các method của `OrderService`. Nếu package/interface thay đổi hoặc method không nằm trên interface, proxy có thể không xử lý như mong muốn. Kiểm tra thực tế bean đã được proxied và caller gọi method công khai qua Spring bean, thay vì tự tạo đối tượng.

### 10.4. Manager và DAO không cùng DataSource

Một manager chỉ quản lý tài nguyên mà nó được cấu hình đúng. Nếu DAO lấy connection độc lập rồi tự commit, manager không rollback được thay đổi đó. Dùng `JdbcTemplate`/`DataSourceUtils` đúng cách để tham gia transaction-bound resources.

### 10.5. Catch exception trong chính method

`try/catch` nội bộ có thể khiến interceptor nhìn thấy trả về bình thường. Để yêu cầu rollback sau khi bắt lỗi, có thể dùng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, nhưng điều đó ràng buộc business code với Spring; ưu tiên đưa quyết định vào transaction boundary/rule khi phù hợp.

### 10.6. Self-invocation hoặc method không được proxy

Gọi `this.someTransactionalMethod()` trong cùng object thường không chạy qua Spring proxy. Tách phương thức cần transaction boundary sang bean Spring khác, hoặc bảo đảm lời gọi ngoài đi qua proxy.

### 10.7. Inner REQUIRED tham gia outer transaction

Nếu inner interceptor đã đánh dấu transaction chung rollback-only, outer bắt exception rồi tiếp tục **không chắc commit thành công**; tại cuối outer có thể gặp `UnexpectedRollbackException`. Rule `no-rollback-for` ở inner không cho phép vượt qua quyết định rollback đã có của outer.

### 10.8. Checked exception bất ngờ commit

Đổi một exception nghiệp vụ từ subclass `RuntimeException` thành subclass `Exception` có thể thay đổi default rollback thành commit. Khi thay đổi exception hierarchy, cần review XML rules và test kết quả database.

### 10.9. Transactional behavior không bao phủ side effect ngoài DB

Rollback JDBC không thể thu hồi email, HTTP request hay message đã publish. Chúng cần thiết kế outbox, idempotency hoặc compensation riêng; `rollback-for` chỉ quyết định transaction Spring đang quản lý.

### 10.10. Read-only, timeout và isolation bị hiểu sai

`read-only="true"` thường chỉ là hint, không phải luôn cấm SQL ghi. `timeout`, `isolation` bị giới hạn bởi manager/driver và thời điểm tạo transaction mới. Khi một method `REQUIRED` tham gia transaction ngoài, metadata inner không mặc định thay thế đặc tính đã tồn tại.

## 11. Gỡ lỗi có hệ thống

Nếu dữ liệu sau khi ném exception **không giống kỳ vọng**:

1. **XML có nạp thành công?** Kiểm tra namespace, schemaLocation, bean IDs, tên package/class và dependency AOP/AspectJ.
2. **Service có được proxy không?** Lấy bean từ Spring context. Trong code debug có thể dùng `org.springframework.aop.support.AopUtils.isAopProxy(service)`.
3. **Pointcut có khớp lời gọi không?** Kiểm tra signature, interface, public method và self-invocation.
4. **Advisor có tham chiếu advice đúng không?** Kiểm tra `advice-ref` và `pointcut-ref`.
5. **Manager nào được chọn?** `txAdvice.transaction-manager` phải đúng bean, cùng DataSource với JdbcTemplate/DAO.
6. **Method nào khớp `tx:method name`?** Xác định exact method, wildcard và fallback. Không giả định mọi rule của nhiều method được cộng dồn.
7. **Exception thực tế thuộc kiểu gì?** Kiểm tra checked/unchecked và tên class/hierarchy với pattern XML.
8. **Có outer transaction hay rollback-only trước đó không?** Inner rule không quyết định kết quả của toàn outer transaction.
9. **Test database sau khi method hoàn tất:** Chạy SELECT bằng connection ngoài transaction đã kết thúc. Đừng chỉ kiểm tra method ném exception hoặc đọc dữ liệu chưa commit trong cùng transaction.

Nếu dùng Spring Boot, có thể tăng log trong file `application.properties`:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

**Lưu ý:** Dự án `ClassPathXmlApplicationContext` của bài không tự sử dụng các thuộc tính logging Boot; muốn trace bằng XML thuần phải cấu hình backend logging phù hợp. Log chỉ giúp chẩn đoán, không thay thế truy vấn xác minh dữ liệu đã commit.

## 12. Bài tập ngắn có đáp án

**Bài 1.** Gỡ `rollback-for` khỏi `saveCheckedRollback` trong XML, chạy lại database mới. Bản ghi id=3 còn không?

**Đáp án:** Có. `BusinessFailureException` là checked exception, nên mặc định Spring không rollback chỉ vì exception đó.

**Bài 2.** Gỡ `no-rollback-for` khỏi `saveUncheckedNoRollback` nhưng giữ `rollback-for="java.lang.Throwable"`. Bản ghi id=5 còn không?

**Đáp án:** Không. Rule rollback rộng khớp exception này, khiến transaction bị rollback.

**Bài 3.** Bỏ cả hai rule khỏi `saveUncheckedNoRollback`. Có rollback không?

**Đáp án:** Có. Method ném subclass `RuntimeException`, nên default rule rollback.

**Bài 4.** Đổi `name="saveCheckedRollback"` thành `name="saveWrong"`; kết quả gì?

**Đáp án:** Method thực tế rơi vào fallback `name="*"`; checked exception lại không rollback theo mặc định và id=3 được commit.

**Bài 5.** Có thể dùng `rollback-for="*Exception"` như wildcard không?

**Đáp án:** Không. `tx:method name` hỗ trợ `*` để match tên method, còn exception pattern không có semantics wildcard kiểu đó.

**Bài 6.** `no-rollback-for="demo.NonFatalOperationException"` có nuốt lỗi và trả về bình thường không?

**Đáp án:** Không. Caller vẫn nhận exception; policy chỉ quyết định cách xử lý transaction.

**Bài 7.** Outer transaction đã được đánh dấu `rollback-only`. Có thể đặt `no-rollback-for` ở inner để ép outer commit không?

**Đáp án:** Không. Rule inner không xóa trạng thái rollback-only của transaction vật lý.

**Bài 8.** Chỉ có `<tx:advice>`, chưa khai báo `<aop:advisor>`. Có tự chặn mọi service call không?

**Đáp án:** Không. Cần gắn advice vào pointcut để tạo proxy áp dụng metadata.

## 13. Tài liệu tham khảo

- Spring Framework — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Settings của `<tx:advice>`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework — Using `@Transactional` và `<tx:annotation-driven>`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative transaction implementation/proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — JDBC connections và DataSource transaction manager: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html

**Ghi nhớ:** **Manager** chọn và điều khiển tài nguyên transaction; **pointcut/advisor** xác định lời gọi nào được intercept; **`tx:method`** mang rollback policy. `rollback-for` bổ sung rollback cho exception cần hủy dữ liệu, `no-rollback-for` loại trừ rollback cho exception được phép giữ dữ liệu. Khi các rule cùng khớp, Spring chọn **rule mạnh nhất theo exception thực tế**, chứ không đơn giản chọn theo thứ tự XML.