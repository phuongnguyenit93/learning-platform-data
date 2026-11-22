# Chế độ AspectJ và yêu cầu dệt mã thay cho proxy trong Spring Transaction Management

## 1. Tại sao Spring cần chế độ AspectJ?

Khi dùng `@Transactional`, Spring Framework phải đặt logic bắt đầu, tham gia, commit hoặc rollback transaction quanh lời gọi phương thức nghiệp vụ. Cách mặc định là **Spring AOP proxy**: caller gọi một bean thông qua proxy, proxy chuyển lời gọi qua `TransactionInterceptor`, rồi mới tới method thực sự. Cơ chế này đơn giản và đủ cho hầu hết ứng dụng, nhưng có một giới hạn có chủ ý: **lời gọi nội bộ `this.method()` không đi qua proxy**.

Chế độ **AspectJ** đưa transaction advice vào **bytecode của class đích** thông qua kỹ thuật *weaving* (dệt mã). Khi class đã được weave đúng, advice được áp dụng tại điểm thực thi method phù hợp, kể cả lời gọi trong cùng object. Spring vẫn sử dụng transaction manager và các quy tắc `@Transactional` quen thuộc; thay đổi ở đây là **cơ chế chặn lời gọi**, không phải một loại database transaction khác.

Ví dụ vấn đề:

```java
@Service
public class InvoiceService {
    public void submit() {
        save(); // this.save(): không đi qua Spring proxy
    }

    @Transactional
    public void save() {
        // Hai thao tác DB cần cùng commit hoặc rollback
    }
}
```

Đây là **mã minh họa**, chưa có repository nên không biên dịch/chạy độc lập. Nếu chỉ bật `@EnableTransactionManagement` mặc định hoặc `<tx:annotation-driven/>` ở proxy mode, một caller gọi `submit()` qua proxy **không khiến annotation của `save()` được áp dụng** cho lời gọi nội bộ; nếu `submit()` không có transaction sẵn, hai thao tác trong `save()` có thể chạy ngoài transaction như mong đợi. Với **AspectJ mode và class đã được weave**, việc thực thi `save()` được advice chặn ngay cả từ `submit()`.

Bài này giải thích **cách AspectJ khác proxy**, **weaving thực sự cần gì**, **cách bật bằng Spring/XML hoặc Java configuration**, một ví dụ runnable Java 17 và cách chẩn đoán lỗi khi chỉ đổi `mode` nhưng transaction vẫn không hoạt động.

## 2. So sánh proxy và AspectJ theo đường thực thi

### 2.1. Proxy mode (mặc định)

```text
Caller bên ngoài
    |
    v
Spring bean proxy
    |
    +-- TransactionInterceptor
    |       +-- tìm @Transactional
    |       +-- transactionManager.getTransaction(...)
    |
    v
Target.method()
    |
    +-- this.anotherMethod()  --> gọi thẳng target
                                  (không đi lại qua proxy)
```

Proxy mode chỉ intercept các method invocation đi **qua proxy**. Nếu `anotherMethod()` có annotation riêng, annotation đó không tự tạo một transaction boundary mới khi nó được gọi bằng `this.anotherMethod()`.

Dù chuyển từ JDK dynamic proxy sang class-based proxy (`proxy-target-class=true`), **self-invocation vẫn bỏ qua proxy**. Class-based proxy không phải AspectJ weaving.

### 2.2. AspectJ mode (có weaving)

```text
Build-time weaving hoặc load-time weaving
       |
       v
Class bytecode đã được dệt transaction aspect
       |
       v
Caller --> Target.method()
              |
              +-- this.anotherMethod()
                     |
                     +-- advice đã được weave vào execution
                          +-- tìm @Transactional
                          +-- transactionManager.getTransaction(...)
                          +-- method body
                          +-- commit/rollback
```

Đây là **sơ đồ khái niệm**, không mô tả bytecode cụ thể của một phiên bản AspectJ. Khác biệt thiết yếu: advice không cần caller vượt qua một đối tượng proxy tại thời điểm gọi. Nó được weave vào các join point phù hợp của class đã biến đổi, vì vậy internal call và các method được annotation trực tiếp với visibility thích hợp có thể được xử lý.

Spring transaction vẫn có **phạm vi logic và phạm vi transaction vật lý**. Một method `REQUIRED` có thể tham gia transaction hiện tại; AspectJ không có nghĩa mỗi lời gọi method đều tạo một transaction độc lập.

| Tiêu chí | Spring AOP proxy | AspectJ weaving |
| --- | --- | --- |
| Cách đặt advice | Proxy intercept lời gọi bên ngoài | Bytecode được weave ở join point phù hợp |
| `this.inner()` | Không tạo thêm advice invocation | Có thể được intercept nếu `inner()` được weave và khớp transaction annotation |
| Public method được gọi ngoài bean | Có, nếu đi qua proxy thích hợp | Có, khi class/method đã được weave |
| Private method được annotation trực tiếp | Không phải điểm proxy interception | Có thể được advised trong AspectJ mode |
| Annotation chỉ khai trên interface | Có thể được Spring proxy mode nhận trong trường hợp phù hợp | **Không nên dựa vào đó**; AspectJ theo Java annotation inheritance, cần annotation trên implementation class/method |
| Bean tạo bằng `new` ngoài Spring | Thường không được proxy | Class đã weave vẫn chứa advice, nhưng transaction aspect **phải được cấu hình manager trước khi dùng** |
| Công cụ bắt buộc | Spring transaction AOP infrastructure | `spring-aspects`, AspectJ compiler/weaver và cấu hình weaving thật |
| Đổi bytecode ứng dụng | Không, theo cơ chế proxy thông thường | Có, tại build-time hoặc class-loading |
| Dễ vận hành/debug | Thường đơn giản hơn | Cần quản lý agent, classloader, weaving scope và build artifacts |

**Không được hiểu “AspectJ thay proxy” là toàn bộ ứng dụng chắc chắn không còn proxy nào**: những capability khác của Spring AOP, chẳng hạn cache hoặc security, vẫn có thể tạo proxy riêng. Ở đây chúng ta đang nói về **transaction advice** trong chế độ AspectJ.

## 3. Đổi `mode` chưa đủ: bốn điều kiện phải đồng thời đúng

Dòng cấu hình sau chỉ **chọn cơ chế AspectJ**:

```xml
<tx:annotation-driven mode="aspectj" transaction-manager="transactionManager"/>
```

Muốn transaction thật sự áp dụng cho các method đã annotation, cần đủ các điều kiện:

1. **Có transaction metadata hợp lệ.** `@Transactional` từ Spring được khai trên **implementation class hoặc method của implementation**, không dựa hoàn toàn vào annotation trên interface.
2. **Có Spring transaction aspect.** Dependency `org.springframework:spring-aspects` cung cấp `org.springframework.transaction.aspectj.AnnotationTransactionAspect`, aspect nhận biết `@Transactional`.
3. **Có weaving thực sự.** Dùng AspectJ compiler tại build-time hoặc AspectJ load-time weaver tại thời điểm JVM nạp class. Thêm JAR vào classpath mà không weave thì advice không tự xuất hiện trong method.
4. **Có transaction manager được cấu hình đúng.** `AnnotationTransactionAspect` phải nhận một `PlatformTransactionManager`/transaction manager thích hợp **trước khi transactional method được thực thi**; DAO/repository phải dùng resource mà manager đó điều phối.

Cần đảm bảo **class đích nằm trong phạm vi weaving**, chưa bị classloader nạp trước khi load-time transformer được đăng ký, và ứng dụng thật sự chạy bằng artifact/JVM đã có weaving.

Một checklist kiến trúc:

```text
@Transactional trên concrete method/class?
            |
            v
spring-aspects có AnnotationTransactionAspect?
            |
            v
AspectJ weaver đã biến đổi target class?
            |
            v
Spring đã inject transaction manager cho aspect?
            |
            v
DAO dùng cùng transaction resource?
            |
            v
Commit/rollback xảy ra khi method được thực thi
```

Nếu một bước thiếu, thay `proxy` bằng `aspectj` **không tạo phép màu**. Đặc biệt, `@EnableAspectJAutoProxy` và `<aop:aspectj-autoproxy/>` chỉ bật **Spring AOP proxy** cho các aspect khai báo theo cú pháp `@AspectJ`; chúng **không** tự kích hoạt bytecode weaving.

## 4. Hai con đường weave bytecode: build-time và load-time

### 4.1. Compile-time weaving (CTW)

AspectJ compiler (`ajc`) biên dịch source Java/AspectJ và weave advice vào class output. Điều này đòi hỏi build pipeline chọn đúng compiler/plugin và có các aspect cần thiết trên aspect path/classpath.

```text
.java / .aj  +  transaction aspect
             |
             v
        AspectJ compiler (ajc)
             |
             v
    .class đã được weave
             |
             v
           JVM chạy
```

Ưu điểm: lỗi weaving thường xuất hiện ngay trong build; production JVM không bắt buộc gắn LTW agent cho những class đã được weave. Cần kiểm tra plugin, phiên bản AspectJ và kết quả `.class` thực tế sau build. Dùng `javac` thông thường **không weave** transaction aspect chỉ vì class có annotation.

### 4.2. Post-compile / binary weaving

Nếu `.class` hoặc JAR đã được tạo bởi `javac`, AspectJ có thể weave **các bytecode đã biên dịch** ở một bước build bổ sung. Vẫn cần cung cấp aspect và cấu hình công cụ đúng. Cách này hữu ích khi code đã được biên dịch bởi toolchain khác nhưng bạn kiểm soát bước đóng gói.

```text
javac -> .class chưa weave -> ajc binary weaving -> .class đã weave
```

Hãy kiểm tra tránh double-weave nếu cùng class được weave thêm ở runtime, vì kết quả và tương tác advice có thể phức tạp.

### 4.3. Load-time weaving (LTW)

AspectJ LTW biến đổi class **khi JVM nạp class**, thông qua class-file transformer. Cách dễ nhìn nhất trong ứng dụng Java độc lập là Java agent:

```bash
java -javaagent:/duong-dan/aspectjweaver.jar -cp "..." demo.weaving.Main
```

Đường dẫn và classpath chỉ là minh họa; ví dụ chạy đầy đủ được trình bày ở phần 7. Tham số `-javaagent` phải được truyền **khi khởi động JVM**. Đặt nó sau tên main class không đúng. `java` chạy ứng dụng không có agent sẽ không weave theo cách này, dù Maven đã tải JAR.

AspectJ LTW đọc các file **`META-INF/aop.xml`** trên classpath để biết các aspect và các target class nào được weave. `spring-aspects` phân phối một `META-INF/aop.xml` với các Spring-provided aspects, bao gồm `AnnotationTransactionAspect`. Ứng dụng có thể bổ sung một `META-INF/aop.xml` để **giới hạn package cần weave** hoặc cấu hình thông tin chẩn đoán. Các file cấu hình AspectJ được kết hợp theo quy tắc LTW của AspectJ.

Lưu ý vai trò các JAR:

| Thư viện/công cụ | Mục đích |
| --- | --- |
| `spring-tx` / Spring JDBC/JPA dependency | Transaction API, manager, interceptor và tích hợp resource |
| `spring-aspects` | Spring transaction AspectJ aspect, trong đó có `AnnotationTransactionAspect` |
| `aspectjweaver` | AspectJ weaving runtime và Java instrumentation agent cho LTW |
| `aspectjtools` / AspectJ Maven plugin | Dùng khi biên dịch hoặc weave trong **build**, không phải điều kiện bắt buộc của LTW agent |
| `spring-instrument` | Java agent **khác** do Spring cung cấp cho một số cơ chế Spring LTW/classloader; không nên nhầm với `aspectjweaver` |

Khi đã chọn LTW agent `aspectjweaver`, **không mặc nhiên cần cả hai `-javaagent:spring-instrument` và `-javaagent:aspectjweaver`**. Spring cung cấp một đường LTW khác với `<context:load-time-weaver/>`, dùng `LoadTimeWeaver` tương thích với classloader; trong môi trường yêu cầu Java instrumentation, đường đó có thể dùng `spring-instrument` agent. Chọn **một cơ chế được cấu hình và kiểm chứng** phù hợp; đừng sao chép mọi tham số agent vào lệnh chạy.

### 4.4. Spring `LoadTimeWeaver` và lựa chọn theo classloader

Spring hỗ trợ `<context:load-time-weaver/>` (XML) hoặc `@EnableLoadTimeWeaving` (Java config) để bật hạ tầng LTW theo `ApplicationContext`/classloader phù hợp. Một ví dụ cấu hình Spring LTW:

```xml
<context:load-time-weaver aspectj-weaving="on"/>
```

Đây là **fragment**, cần khai báo namespace `context`, XSD và môi trường classloader/agent tương thích. Giá trị `aspectj-weaving` là `on`, `off` hoặc `autodetect`; `autodetect` dùng sự hiện diện của `META-INF/aop.xml` để quyết định. Không nhầm thẻ này với `<tx:annotation-driven mode="aspectj"/>`: một thẻ chọn **transaction advice implementation**, thẻ kia xử lý **hạ tầng weaving**.

Ở ứng dụng Java độc lập, dùng `-javaagent:aspectjweaver-...jar` với `META-INF/aop.xml` là đường minh họa trực tiếp, không cần thêm `<context:load-time-weaver/>` trong ví dụ của bài. Ở app server hoặc môi trường nhiều classloader, việc weave phải phù hợp với classloader thực sự nạp service, và có thể cần cơ chế tích hợp riêng của container.

## 5. Cấu hình Spring: XML và Java đều có AspectJ mode

### 5.1. XML transaction annotation

Cấu hình tối thiểu theo cấu trúc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd">

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <tx:annotation-driven mode="aspectj"
                          transaction-manager="transactionManager"/>
</beans>
```

Đây là **fragment XML**, không chạy độc lập: cần định nghĩa `dataSource`, Spring context, target bean và weaving tương ứng. Thuộc tính `transaction-manager` trỏ đến bean thật. Giá trị mặc định của tên manager trong cách cấu hình XML truyền thống là `transactionManager`, nhưng viết tường minh giúp giảm nhầm lẫn khi có nhiều manager.

Các thuộc tính `proxy-target-class` **chỉ có ý nghĩa trong `mode="proxy"`**, không chuyển AspectJ mode thành “class-based proxy mạnh hơn”. `order` chủ yếu là điều khiển thứ tự transaction advisor trong cơ chế proxy; thứ tự nhiều woven aspects và precedence trong AspectJ có quy tắc riêng, cần kiểm tra ở weaving configuration.

### 5.2. Java configuration tương đương

```java
@Configuration
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class TransactionConfiguration {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Đây là **snippet minh họa** với imports từ `org.springframework.context.annotation`, `org.springframework.transaction`, `org.springframework.jdbc.support` và `javax.sql.DataSource`. Cần thêm bean `DataSource`, dependency `spring-aspects` và weaving thực tế. `AdviceMode.ASPECTJ` là lựa chọn transaction advice, **không tự cài Java agent**.

### 5.3. Aspect ngoài Spring IoC container

Trong một ứng dụng không sử dụng Spring container để cấu hình aspect, Spring cho phép cấu hình `AnnotationTransactionAspect` bằng code, miễn class được weave:

```java
DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
AnnotationTransactionAspect.aspectOf().setTransactionManager(manager);
```

Đây là fragment minh họa; `dataSource` cần tồn tại và cần imports tương ứng. Dù AspectJ có thể advice đối tượng được tạo bằng `new`, **manager vẫn phải được cấu hình trước khi method được advice thực thi**. Trong ứng dụng Spring thông thường, `<tx:annotation-driven mode="aspectj"/>` hoặc `@EnableTransactionManagement(mode=AdviceMode.ASPECTJ)` xử lý phần cấu hình aspect này.

Không nên vừa tự gọi `aspectOf().setTransactionManager(...)` vừa để container tự quản lý cùng transaction aspect nếu không có yêu cầu rõ ràng: nhiều nơi sở hữu cấu hình gây khó hiểu.

## 6. Ngữ nghĩa `@Transactional` trong AspectJ mode

AspectJ thay đổi **cách interception**, còn Spring transaction rules vẫn tồn tại:

- **`REQUIRED` (mặc định):** tham gia transaction hiện có hoặc tạo transaction mới nếu chưa có.
- **`REQUIRES_NEW`:** tạm gác transaction đang dùng, bắt đầu transaction độc lập; có thể cần thêm JDBC connection.
- **`NESTED`:** dùng savepoint trong cùng transaction vật lý khi manager và resource hỗ trợ.
- **Rollback mặc định:** `RuntimeException` và `Error` làm rollback; checked exception thường cần `rollbackFor` để rollback.
- **`readOnly=true`:** hint dành cho manager/provider, không đảm bảo database từ chối mọi câu lệnh ghi.
- **Resource:** JDBC repository phải dùng connection gắn với transaction manager; file, email, HTTP call không tự được rollback cùng JDBC transaction.

AspectJ còn có các điểm cần đặc biệt chú ý:

1. **Đặt annotation trên implementation.** Khi weave, đừng chỉ annotation interface rồi kỳ vọng AspectJ nhìn thấy metadata như proxy mode. Java không tự kế thừa annotation từ interface method sang implementation.
2. **Class-level annotation khác method-level annotation.** `@Transactional` trên concrete class xác lập chính sách mặc định cho các public operation. Nếu cần transaction ở một **non-public method**, hãy đặt `@Transactional` **trực tiếp trên method đó**; đừng suy luận mọi private helper đều transactional chỉ vì class đã annotation.
3. **Self-invocation được xử lý khi class đã weave.** Ví dụ public `run()` gọi `this.save()`; `save()` với annotation trực tiếp có thể được advice chặn trong AspectJ mode.
4. **Không phải mọi hoạt động đều là method join point được `AnnotationTransactionAspect` chọn.** Truy cập field, constructor, việc ghi file, các thread khác và object lifecycle không đương nhiên có transaction chỉ nhờ weaving.
5. **Thread/reactive boundary vẫn tồn tại.** Imperative transaction thường gắn với execution thread. AspectJ không tự lan truyền transaction sang thread khác; R2DBC/reactive cần `ReactiveTransactionManager` và Reactor Context thích hợp.

Một ví dụ private method, **chỉ minh họa**:

```java
public void submit() {
    persistInternal(); // lời gọi trong cùng object
}

@Transactional
private void persistInternal() {
    // truy cập DB bằng resource do Spring transaction manager điều phối
}
```

Đối với aspect đã weave vào concrete class, method-level annotation trên `private persistInternal()` có thể tạo transaction boundary. Trong proxy mode, private method không phải interception point. Phần 7 dùng method public để cô lập rõ hiệu ứng **self-invocation**, tránh nhầm với khác biệt về visibility.

## 7. Ví dụ Java 17 hoàn chỉnh: self-invocation thật sự rollback bằng AspectJ

### 7.1. Mục tiêu và công nghệ

Ví dụ sử dụng:

- Java **17+** và Maven **3.9+**.
- Spring Framework **6.2.18**, dùng XML `ClassPathXmlApplicationContext`.
- `spring-aspects` **6.2.18** cùng AspectJ Weaver **1.9.25**.
- Spring JDBC và H2 in-memory **2.3.232**.
- Một service với method `runTransfer()` gọi trực tiếp `transfer()` trong cùng object. **Chỉ `transfer()` có `@Transactional`.**

Trong proxy mode mặc định, lời gọi nội bộ không vào transaction interceptor. Trong AspectJ mode **cộng weaving agent thật**, execution `transfer()` được dệt advice; khi có exception giữa hai thao tác, JDBC transaction rollback.

Cấu trúc thư mục:

```text
spring-tx-aspectj-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── weaving/
        │           ├── Main.java
        │           └── TransferService.java
        └── resources/
            ├── spring.xml
            └── META-INF/
                └── aop.xml
```

### 7.2. `pom.xml`: cả transaction và weaving

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-tx-aspectj-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <aspectj.version>1.9.25</aspectj.version>
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
            <artifactId>spring-aspects</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>${aspectj.version}</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích: `spring-context` cung cấp IoC/XML container; `spring-jdbc` cung cấp `JdbcTemplate` và JDBC transaction manager; `spring-aspects` chứa `AnnotationTransactionAspect`; `aspectjweaver` làm Java agent và weaving runtime; H2 chỉ dùng khi chạy. Đặt các module Spring về **cùng một version** để tránh dependency mismatch. Một ứng dụng Spring Boot có thể dùng BOM để quản lý phiên bản, nhưng ví dụ này cố ý không dùng Boot nhằm quan sát cấu hình AspectJ trực tiếp.

### 7.3. `spring.xml`: chọn `mode="aspectj"`

File `src/main/resources/spring.xml`:

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

    <context:component-scan base-package="demo.weaving"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:aspectj_tx;DB_CLOSE_DELAY=-1"/>
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

    <tx:annotation-driven mode="aspectj"
                          transaction-manager="transactionManager"/>
</beans>
```

Manager và `JdbcTemplate` tham chiếu **cùng một `dataSource`**. `DriverManagerDataSource` không tạo connection pool; nó đủ cho demo. `DB_CLOSE_DELAY=-1` giữ H2 database trong JVM khi những connection ngắn hạn được đóng. Khi triển khai ứng dụng thực, hãy dùng datasource/pool phù hợp.

`<tx:annotation-driven mode="aspectj"/>` yêu cầu Spring cấu hình transaction aspect, **không** tự chèn Java agent vào JVM. Bước 7.6 sẽ chạy JVM với `-javaagent`.

### 7.4. `META-INF/aop.xml`: giới hạn class nào được weave

File `src/main/resources/META-INF/aop.xml`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
                           "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo.weaving..*"/>
    </weaver>
</aspectj>
```

Giải thích: `include within="demo.weaving..*"` giới hạn target types trong package ứng dụng và các package con. `-showWeaveInfo` in thông tin join point/weaving hữu ích khi kiểm tra; có thể bỏ tùy chọn này trong production khi đã xác minh. File cấu hình ứng dụng này **không tự định nghĩa** `AnnotationTransactionAspect`; Spring phân phối aspect đó và cấu hình AspectJ liên quan trong **JAR `spring-aspects`**. AspectJ LTW kết hợp các `META-INF/aop.xml` có thể nhìn thấy trên classpath.

Không đặt một `aop.xml` khác ghi đè/lọc aspect tùy tiện mà chưa hiểu `include/exclude` semantics. Một số filter có thể tác động đến aspects được công bố từ **các file `aop.xml` khác**; phải kiểm tra danh sách aspect thực sự được weave.

### 7.5. Service: lời gọi cùng object vẫn có transaction

File `src/main/java/demo/weaving/TransferService.java`:

```java
package demo.weaving;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void runTransfer(boolean fail) {
        transfer(fail); // this.transfer(fail): self-invocation
    }

    @Transactional
    public void transfer(boolean fail) {
        System.out.println("TX_ACTIVE=" +
                TransactionSynchronizationManager.isActualTransactionActive());

        jdbc.update(
                "UPDATE account SET balance = balance - 30 WHERE id = 1");

        if (fail) {
            throw new IllegalStateException("planned failure");
        }

        jdbc.update(
                "UPDATE account SET balance = balance + 30 WHERE id = 2");
    }
}
```

`runTransfer()` **không có** `@Transactional`; nó chỉ gọi method `transfer()` trong cùng class. `transfer()` có annotation trên **concrete public method**. `TransactionSynchronizationManager.isActualTransactionActive()` chỉ được dùng để quan sát trong bài học; service nghiệp vụ thường không nên dựa vào nó để điều khiển flow.

Ở AspectJ mode, nếu bytecode `TransferService` được weave thành công, lệnh `transfer(fail)` nội bộ vẫn đi qua transaction aspect. Trong proxy mode, lời gọi nội bộ này bỏ qua transaction proxy; `@Transactional` trên `transfer()` không tự kích hoạt transaction cho lời gọi đó.

### 7.6. Main và lệnh chạy đúng với JVM agent

File `src/main/java/demo/weaving/Main.java`:

```java
package demo.weaving;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("spring.xml")) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE account (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO account (id, balance) VALUES (1, 100)");
            jdbc.update("INSERT INTO account (id, balance) VALUES (2, 50)");

            TransferService service = context.getBean(TransferService.class);

            print(jdbc, "BEFORE");

            try {
                service.runTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("FAIL=" + ex.getMessage());
            }

            print(jdbc, "AFTER_FAIL");

            service.runTransfer(false);
            print(jdbc, "AFTER_SUCCESS");
        }
    }

    private static void print(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);

        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Biên dịch và copy runtime dependency JARs vào thư mục tường minh:

```bash
mvn -q package dependency:copy-dependencies -DoutputDirectory=target/dependency
```

Trên **Windows PowerShell** (classpath dùng `;`):

```powershell
java -javaagent:target/dependency/aspectjweaver-1.9.25.jar -cp "target/classes;target/dependency/*" demo.weaving.Main
```

Trên **Linux/macOS** (classpath dùng `:`):

```bash
java -javaagent:target/dependency/aspectjweaver-1.9.25.jar -cp "target/classes:target/dependency/*" demo.weaving.Main
```

Đây là **JVM mới** chạy class và JARs vừa được build; khác với gọi `mvn exec:java` ngay trong Maven JVM mà không gắn agent từ lúc JVM khởi động. Nếu dùng IDE, đặt `-javaagent:...` trong **VM options** của run configuration và đảm bảo `META-INF/aop.xml` cùng `spring-aspects` có trên runtime classpath.

**Những dòng do chương trình in ra** (bỏ qua weaving info, logging và thông báo phụ thuộc môi trường):

```text
BEFORE: A=100, B=50
TX_ACTIVE=true
FAIL=planned failure
AFTER_FAIL: A=100, B=50
TX_ACTIVE=true
AFTER_SUCCESS: A=70, B=80
```

Giải thích:

1. Spring khởi tạo container XML, tạo `JdbcTemplate`, `JdbcTransactionManager`, `TransferService` và cấu hình `AnnotationTransactionAspect`.
2. AspectJ agent biến đổi class trong package `demo.weaving` khi chúng được nạp, sao cho `transfer()` có transaction advice.
3. Khi `runTransfer(true)` gọi nội bộ `transfer(true)`, aspect mở transaction; `TX_ACTIVE=true` cho biết imperative transaction của Spring đang hoạt động trong method.
4. Sau debit, `IllegalStateException` thoát khỏi `transfer()`; với rollback rule mặc định, Spring rollback debit. `Main` bắt exception ngoài scope, sau đó truy vấn lại và vẫn thấy A=100, B=50.
5. Lần `runTransfer(false)` có hai update thành công, transaction được commit, cuối cùng A=70, B=80.

Giá trị demo là **quan sát lời gọi nội bộ** được transaction hóa. Cờ `TX_ACTIVE=true` chỉ là tín hiệu phụ; bằng chứng chính là dữ liệu sau fail không đổi và sau success thay đổi đồng bộ. Demo không kiểm tra đủ tiền, khóa đồng thời hoặc idempotency chuyển tiền; không sử dụng trực tiếp như một ứng dụng ngân hàng.

### 7.7. Đối chứng: thiếu weaving hoặc trở về proxy mode

Nếu đổi XML thành:

```xml
<tx:annotation-driven mode="proxy"
                      transaction-manager="transactionManager"/>
```

và chạy theo thiết kế này, `runTransfer()` vẫn gọi `this.transfer()` nên annotation riêng của `transfer()` **không được Spring transaction proxy intercept**. Với `DriverManagerDataSource` và JDBC auto-commit mặc định trong demo, debit khi fail có thể commit riêng, cho thấy **không có atomicity như kỳ vọng**.

Một đối chứng khác: để `mode="aspectj"` nhưng **bỏ `-javaagent`** và không có build-time woven classes. Class `TransferService` không được biến đổi; self-invocation không có AspectJ advice. Vì vậy `mode="aspectj"` và sự hiện diện của dependency **không thể được dùng làm bằng chứng** rằng bytecode đã woven.

Khi so sánh, chạy mỗi cấu hình trong **JVM mới** với DB H2 in-memory mới. Đừng tái sử dụng cùng dữ liệu sau một lần chạy sai, vì những thay đổi auto-commit có thể khiến đầu vào của thí nghiệm kế tiếp khác đi.

## 8. Cách xác nhận class đã weave thực sự

Chỉ thấy bean khởi tạo hoặc file `aop.xml` trên classpath không đủ. Dùng bằng chứng ở cả build/runtime và database.

### 8.1. Kiểm tra runtime weaving

Trong LTW demo, thêm `-showWeaveInfo` vào `<weaver>` như ở phần 7.4. Quan sát log của AspectJ để tìm thông tin weaving cho method/class trong package ứng dụng, đặc biệt join point thuộc `TransferService`. Khi không thấy thông tin, kiểm tra:

- Agent có được truyền bằng `-javaagent` trước tên main class không?
- File JAR của agent có đúng phiên bản/path không?
- `spring-aspects` có trên runtime classpath không?
- `META-INF/aop.xml` có được copy vào `target/classes/META-INF/` không?
- `include within` có bao phủ **đúng package và class** không?
- Class có được nạp quá sớm trước khi transformer được đăng ký không?
- Classloader trong server/IDE có nhìn thấy cùng JAR và config không?

Log weaving vẫn không thay thế test commit/rollback. Nếu class có advisor khác, Spring có thể vẫn tạo proxy; `AopUtils.isAopProxy(bean)` **không phải phép thử cho AspectJ weaving**.

### 8.2. Kiểm tra transaction manager và resource

Giả sử AspectJ advice chạy nhưng JDBC vẫn auto-commit ngoài transaction. Hãy kiểm tra manager được aspect sử dụng có quản lý **cùng `DataSource`** mà `JdbcTemplate` lấy connection hay không. Với JPA, kiểm tra đúng `EntityManagerFactory`/`JpaTransactionManager`; với nhiều datasource, kiểm tra đúng manager hoặc qualifier.

`TransactionSynchronizationManager.isActualTransactionActive()` là tín hiệu chẩn đoán trạng thái thread-local trong giao dịch imperative; nó **không đảm bảo** một request HTTP, email hay connection từ datasource khác tự tham gia giao dịch.

### 8.3. Kiểm chứng bằng test hành vi

Một bài test hữu ích nên gồm:

1. Dữ liệu DB ban đầu đã được commit.
2. Gọi method wrapper không annotation, bên trong có `this.transactionalMethod()`.
3. Cố tình ném unchecked exception **sau thao tác DB thứ nhất, trước thao tác thứ hai**.
4. Để interceptor/aspect kết thúc transaction.
5. Đọc lại dữ liệu **sau scope** từ ngữ cảnh phù hợp; xác minh không có partial commit.
6. Gọi lại với đường thành công; kiểm tra cả hai thay đổi được commit.
7. So sánh với proxy mode hoặc chạy không weaving để chứng minh khác biệt.

Cẩn thận với test method được gắn `@Transactional` bởi Spring Test: test framework có thể tự rollback khi kết thúc, che giấu việc service transactional method không được weave. Hãy chắc chắn test quan sát đúng boundary cần kiểm tra.

## 9. Những giới hạn AspectJ không tự xóa bỏ

### 9.1. Weaving không thay thế transaction manager

AspectJ chỉ đảm nhiệm việc gắn advice. Nó không mở transaction bằng phép thuật nếu không có manager tương thích. Cơ chế thực hiện commit/rollback vẫn phụ thuộc vào database, JDBC/JPA/R2DBC provider và transaction infrastructure.

### 9.2. Không tự sửa mọi lỗi multi-thread

Imperative Spring transaction thường liên kết resource với thread hiện tại. Nếu method tạo thread khác bằng `new Thread`, executor hoặc `@Async`, việc weave method ở thread mới có thể tạo/join **transaction theo ngữ cảnh của thread đó**, nhưng không tự chuyển JDBC connection/transaction vật lý của parent thread sang thread mới. Phải thiết kế transaction scope rõ ràng tại nơi công việc thực thi.

### 9.3. Không biến side effect bên ngoài DB thành resource có rollback

Nếu method đã gửi email hoặc gọi dịch vụ ngoài, rollback database không hủy hiệu ứng đã diễn ra. Khi yêu cầu nhất quán giữa DB và message, cân nhắc outbox hoặc điều phối phù hợp. Đây là vấn đề transaction/resource, không phải proxy-versus-AspectJ.

### 9.4. Class chưa weave sẽ giữ semantics cũ

Với LTW, class đã được JVM nạp trước khi transformer xuất hiện thường không được dệt tự động bởi cấu hình LTW thông thường. Trong môi trường app server, plugin, hot reload, native image hoặc nhiều classloader, sự khác nhau giữa **class path hiện tại** và **class loader thực tế** ảnh hưởng phạm vi weaving. Java agent cần được thiết lập sớm, và build/test/deployment cần chạy cùng cấu hình weaving.

### 9.5. Reflection/final/private không phải “mọi thứ đều an toàn”

AspectJ có thể advice các method execution mà proxy không intercept, bao gồm non-public method khi được annotation trực tiếp; tuy nhiên transaction aspect chỉ áp dụng cho **join point phù hợp và class đã woven**. Nó không có nghĩa mọi constructor, field access, method synthetic hoặc thao tác phản chiếu đều tự động có transaction. Hãy kiểm tra test thực tế cho trường hợp của ứng dụng.

### 9.6. Advice ordering và performance

Weaving có thể làm tăng chi phí build hoặc class loading và phức tạp hóa debug/stack trace. Weave toàn bộ dependencies không cần thiết gây overhead và cảnh báo. Giới hạn `<include within="my.application..*"/>` vào các package cần thiết; khi có nhiều aspects, phải xem precedence/order tương ứng. Đừng mặc định thuộc tính `order` của transaction advisor trong proxy mode sẽ quyết định hết thứ tự của woven AspectJ aspects.

## 10. Lỗi cấu hình thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
| --- | --- | --- |
| Đặt `mode="aspectj"` nhưng self-invocation vẫn ngoài transaction | Chưa weave bytecode | Dùng `ajc` trong build hoặc LTW agent; kiểm tra `-showWeaveInfo` và test rollback |
| Spring báo thiếu `AnnotationTransactionAspect` | Thiếu `spring-aspects` | Thêm dependency `org.springframework:spring-aspects` cùng version Spring |
| Agent báo không tìm thấy JAR | Sai `-javaagent` path | Kiểm tra tên/version JAR và đường dẫn từ working directory |
| Agent chạy nhưng class không được weave | Sai `META-INF/aop.xml` hoặc include package | Kiểm tra `target/classes/META-INF/aop.xml`, package pattern, classloader |
| Weaving log chỉ có aspect khác | Transaction aspect không được đăng ký/đang bị filter | Kiểm tra cấu hình từ `spring-aspects` và `include/exclude` aspect rules |
| Runtime báo transaction manager chưa cấu hình | Aspect chưa được inject manager hoặc XML context chưa được load | Kiểm tra `<tx:annotation-driven mode="aspectj">`, bean `transactionManager`, thời điểm chạy |
| Annotation trên interface không có hiệu lực | AspectJ không kế thừa annotation từ interface | Đặt `@Transactional` trên concrete class hoặc implementation method |
| Chỉ thấy proxy dù bật AspectJ | Bean có advisor khác | Đừng lấy proxy flag làm bằng chứng; quan sát weaving log và hành vi |
| Method private chưa transactional | Annotation chỉ ở class-level hoặc class chưa weave | Annotation trực tiếp trên private method, xác nhận weaving |
| Checked exception không rollback | Rollback rule mặc định | Cấu hình `rollbackFor` phù hợp, hoặc dùng unchecked exception theo contract |
| Method catch exception rồi return bình thường | Advice không thấy exception thoát khỏi scope | Propagate exception hoặc đánh dấu rollback-only khi phù hợp |
| H2/JDBC update commit riêng | DAO dùng connection/resource không thuộc manager | Kiểm tra `DataSource` của JDBC template và manager |
| Chỉ lỗi ở production, test vẫn pass | Khác JVM arguments, JAR, classloader hoặc build artifact | Đối chiếu command-line/agent, dependency tree, tài nguyên và weaving log giữa môi trường |
| Có warning khi weave thư viện không liên quan | Quá rộng package weaving | Thêm `include within` giới hạn application packages |

Có thể dùng hai câu hỏi phân biệt nhanh:

- **Advice có đang chạy không?** Xem weaving log/transaction debug, kiểm chứng method nội bộ có transaction.
- **DB có đang tham gia đúng transaction không?** Xem manager, resource, trạng thái kết quả sau rollback.

Nếu câu thứ nhất đúng mà câu thứ hai sai, chỉnh proxy hay AspectJ tiếp thường không giải quyết nguyên nhân gốc.

## 11. Khi nào nên chọn AspectJ, khi nào nên giữ proxy?

Chọn **proxy mode** nếu bạn có thể đặt transaction ở các public service method rõ ràng và caller gọi qua Spring-managed bean. Đây là thiết kế phù hợp với hầu hết use case nghiệp vụ, dễ test và ít phụ thuộc JVM instrumentation hơn. Ví dụ thay vì `this.save()`, có thể đưa transaction boundary lên `submit()` hoặc tách `save()` thành bean khác được inject.

AspectJ đáng cân nhắc khi:

- Cần transaction boundary ở **self-invocation** mà kiến trúc không thể dễ dàng refactor.
- Thực sự cần intercept **non-public implementation method** được annotate trực tiếp.
- Phải áp dụng advice cho những đối tượng **không đi qua Spring proxy**, và team có khả năng quản lý weaving/transaction aspect lifecycle.
- Có sẵn quy trình AspectJ CTW/LTW đã được kiểm soát trong build và deployment.

Đánh đổi cần cân nhắc: bytecode weaving khiến build/run configuration chặt chẽ hơn; troubleshooting cần quan sát classloader và class đã woven; phối hợp nhiều aspects có thể phức tạp. Chỉ đổi mode vì “AspectJ mạnh hơn” thường không mang lại lợi ích nếu transaction boundary của service vốn đã rõ.

Một sơ đồ ra quyết định:

```text
Transactional method được gọi qua Spring proxy?
    |
    +-- Có --> proxy mode thường đủ
    |
    +-- Không --> có thể chuyển boundary lên public service
                     hoặc tách sang bean khác?
                    |
                    +-- Có --> cân nhắc sửa cấu trúc, tiếp tục proxy
                    |
                    +-- Không --> cần self/non-public interception?
                                    |
                                    +-- Có --> đánh giá AspectJ + weaving
                                    |
                                    +-- Không --> kiểm tra manager/resource/lifecycle
```

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Chỉ khai báo `<tx:annotation-driven mode="aspectj"/>` và thêm `@Transactional` lên method. Không có `spring-aspects` và weaving agent/build step. Self-invocation có transaction không?

**Giải thích:** Không. Chọn mode không tương đương bytecode đã được biến đổi. Cần `spring-aspects`, wiring manager và CTW/LTW thực sự.

**Câu 2.** Thêm `<aop:aspectj-autoproxy/>` rồi giữ `mode="proxy"`. `this.save()` có được transaction interceptor chặn không?

**Giải thích:** Không. `<aop:aspectj-autoproxy/>` vẫn tạo **Spring AOP proxies**; nó không thực hiện AspectJ bytecode weaving và không tự sửa self-invocation.

**Câu 3.** Interface có `@Transactional`, implementation không annotation. AspectJ có bắt buộc nhận transaction metadata đó không?

**Giải thích:** Không. AspectJ theo quy tắc annotation inheritance của Java; đặt annotation trên concrete implementation class/method khi dùng weaving.

**Câu 4.** Class-level `@Transactional` có làm mọi `private helper()` trở thành transactional method không?

**Giải thích:** Không. Với Spring-provided AspectJ transaction aspect, class-level annotation xác lập mặc định cho public operations; cần annotation **trực tiếp trên non-public method** nếu muốn nó là transactional join point.

**Câu 5.** `@Transactional` được weave, nhưng DAO dùng datasource khác với manager. Có chắc rollback cả hai database không?

**Giải thích:** Không. Weaving chỉ định nơi advice chạy; resource và transaction manager quyết định dữ liệu nào được quản lý.

**Câu 6.** Dùng LTW, thêm `aspectjweaver` vào Maven và gọi `mvn exec:java` mà không cấp `-javaagent` khi JVM khởi động. Class có chắc đã weave không?

**Giải thích:** Không. Thêm dependency vào classpath không đồng nghĩa đăng ký Java transformer. Cần agent hoặc một hạ tầng weaving khác được cấu hình/kiểm chứng.

**Câu 7.** `@Transactional(rollbackFor = IOException.class)` được weave đúng và IOException thoát khỏi method. Rollback rule có khác proxy mode không?

**Giải thích:** Không theo bản chất propagation/rollback rule của Spring; khác biệt nằm ở cách method được advice chặn. Nếu transaction manager/resource phù hợp, checked exception được cấu hình cũng dẫn đến rollback.

**Câu 8.** Một service dùng `@Async` để chạy thread khác. Bật AspectJ có tự chuyển transaction JDBC đang mở sang thread mới không?

**Giải thích:** Không. Transaction imperative có ngữ cảnh gắn với thread; cần đặt boundary hợp lệ tại nơi code chạy và kiểm tra việc điều phối giữa các thread.

## 13. Checklist triển khai đáng tin cậy

Trước khi xem AspectJ mode đã hoạt động, hãy kiểm tra:

1. `@Transactional` nằm trên implementation class/method cần intercept và metadata phù hợp business semantics.
2. `spring-aspects` tồn tại với version Spring tương thích, aspect `AnnotationTransactionAspect` không bị filter khỏi weaving.
3. Transaction manager được cấu hình cho aspect và quản lý **đúng resource**.
4. Một trong **CTW/binary weaving/LTW** đã được chọn, xây dựng và chạy thật; không chỉ thêm dependency.
5. Trong LTW, JVM/agent/classloader và `META-INF/aop.xml` đúng; package include chứa target class.
6. Artifact deployment không bị build lại hoặc chạy bằng JVM khác bỏ sót weaving.
7. Có test **self-invocation fail/success** và đọc hậu điều kiện dữ liệu ngoài scope transaction.
8. Các loại exception và propagation cần thiết có test rõ, đặc biệt khi có nested hoặc `REQUIRES_NEW`.
9. Không dựa vào AOP proxy flag như phép xác nhận bytecode weaving.
10. Log weaving và transaction có phạm vi an toàn trong production, không lộ dữ liệu nhạy cảm và tránh overhead không cần thiết.

## 14. Kết luận kiến thức

**Proxy mode** đặt transaction interceptor trước method qua một Spring proxy; self-invocation bypass proxy. **AspectJ mode** sử dụng Spring transaction AspectJ aspect để weave advice vào bytecode, nên có thể intercept lời gọi nội bộ và các non-public implementation method được annotation trực tiếp.

Điều kiện tối thiểu để điều đó đúng là: **annotation trên concrete target + `spring-aspects` + weaving thực sự + transaction manager được cấu hình đúng + data access dùng resource phù hợp**. `mode="aspectj"` chỉ chọn chiến lược advice; nó không chạy `ajc`, không chèn Java agent và không tự biến class đã load thành class woven.

## Tài liệu chính thức

- [Spring Framework 6.2 — Using @Transactional (proxy vs AspectJ mode)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Using @Transactional with AspectJ](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/aspectj.html)
- [Spring Framework — Using AspectJ with Spring Applications; load-time weaving](https://docs.spring.io/spring-framework/reference/6.2/core/aop/using-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [AspectJ Development Environment Guide](https://eclipse.dev/aspectj/doc/latest/devguide/devguide.html)
- [AspectJ Weaver agent artifact](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver/1.9.25)