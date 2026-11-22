# Tách chính sách giao dịch cho các nhóm dịch vụ bằng XML trong Spring Framework

## 1. Bài toán: nhiều nhóm service không nhất thiết dùng một chính sách

Trong một ứng dụng Spring, các service thường phục vụ những loại công việc khác nhau:

- **Order/Command service** thay đổi dữ liệu và cần rollback khi bất kỳ bước nghiệp vụ bắt buộc nào thất bại, kể cả một số checked exception.
- **Report/Query service** chủ yếu đọc dữ liệu, cần phạm vi transaction đọc rõ ràng và có thể khai báo `read-only="true"` để hạ tầng được phép tối ưu.
- **Batch/Import service** xử lý từng lô dài hơn, có thể cần timeout và ranh giới transaction theo từng batch thay vì một giao dịch khổng lồ.

Nếu gắn một policy duy nhất lên toàn bộ package `service`, những yêu cầu trên dễ xung đột. Spring cung cấp cấu hình **declarative transaction bằng XML**: định nghĩa nhiều `<tx:advice>` khác nhau, chọn các phương thức cần áp dụng bằng **AOP pointcut**, rồi nối mỗi pointcut với advice bằng `<aop:advisor>`.

**Mục tiêu bài học:** hiểu cách **tách chính sách giao dịch cho các nhóm dịch vụ** bằng XML, biết policy nào áp dụng ở đâu, tránh advisor trùng lặp hoặc không bao phủ, và kiểm chứng bằng dữ liệu thực tế.

Sau bài này, bạn sẽ biết:

1. Phân biệt **chọn đối tượng áp dụng** (pointcut), **quy tắc giao dịch** (`tx:advice`) và **người thực thi giao dịch** (transaction manager).
2. Viết XML khai báo hai nhóm có chính sách khác nhau mà không bắt buộc dùng `@Transactional` trên từng method.
3. Hiểu ranh giới của `read-only`, `rollback-for`, `timeout`, `propagation` và cách policy phụ thuộc transaction bên ngoài.
4. Chạy ví dụ Java 17+, Spring Boot, JDBC và H2 cho thấy nhóm ghi rollback `IOException` trong khi nhóm báo cáo được đánh dấu read-only.
5. Chẩn đoán lỗi package pointcut quá rộng, phương thức bypass proxy, transaction manager không khớp và nhiều advisor cùng intercept.

Bài thuộc mục **Cấu hình XML** của module Spring Framework — transaction management. Phần Java dùng để kiểm chứng cách XML tác động lên bean Spring; XML mới là nơi khai báo transaction policy.

## 2. Mô hình ba thành phần: pointcut, advice và transaction manager

Hãy nghĩ về mỗi nhóm như một cặp **“ai” + “làm thế nào”**.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `<aop:pointcut>` | Chọn những lời gọi phương thức thuộc nhóm nào | Mọi public method của `orders.*Service` |
| `<tx:advice>` | Định nghĩa propagation, readOnly, timeout, rollback rule cho method name | Nhóm order: `REQUIRED` và rollback checked `Exception` |
| `<aop:advisor>` | Nối pointcut với đúng advice | `ordersPointcut` → `ordersTxAdvice` |
| `PlatformTransactionManager` | Mở, tham gia, commit hoặc rollback trên tài nguyên cụ thể | `DataSourceTransactionManager` cho `DataSource` JDBC |
| Spring AOP proxy | Chặn lời gọi phù hợp để transaction advice chạy | Bean được inject vào caller |

Luồng hoạt động:

```text
Caller gọi Spring bean qua proxy
               |
               v
AOP pointcut kiểm tra method/class/package
       |                           |
       v                           v
  Nhóm orders                 Nhóm reports
  ordersTxAdvice              reportsTxAdvice
  REQUIRED, read-write        REQUIRED, read-only
  rollback checked Exception  thời hạn ngắn hơn
       |                           |
       +-------------+-------------+
                     v
             TransactionInterceptor
                     |
                     v
           PlatformTransactionManager
                     |
                     v
             JDBC / JPA / tài nguyên
                     |
                     v
           Commit hoặc rollback
```

**Phân biệt hai cấp độ chọn lọc:**

- Biểu thức AspectJ trong `<aop:pointcut>` chọn *những lời gọi nào* có khả năng được advice xử lý, theo package, class, method và chữ ký.
- Các thẻ `<tx:method name="...">` **bên trong advice** chỉ chọn *quy tắc nào* cho tên method đã được pointcut bắt được. `name="find*"` không tự mở rộng advisor ra toàn ứng dụng.

Ví dụ, có `<tx:method name="find*" read-only="true"/>` nhưng pointcut chỉ match package `orders`, thì service ở package `reports` **không** được advice đó xử lý chỉ vì method tên `findById`.

Hạ tầng phải có một transaction manager thích hợp. Advice không trực tiếp quản lý JDBC connection hoặc EntityManager; nó gọi manager để làm việc đó.

## 3. Thiết kế nhóm trước khi viết XML

Một cách có kiểm soát là chia theo **ý nghĩa và ranh giới công việc**, không chỉ dựa vào tên file hoặc phương thức:

| Nhóm | Method tiêu biểu | Policy gợi ý | Mục tiêu |
| --- | --- | --- | --- |
| `orders` | `createSuccess`, `createThenFail`, `submit` | `REQUIRED`, read-write, `rollback-for="java.lang.Exception"` | Nhiều bước ghi cùng thành công; cả checked exception quy định rollback |
| `reports` | `findCount`, `findSummary`, `getTotals` | `REQUIRED`, `read-only="true"` | Có transaction đọc và thể hiện rõ chủ ý truy vấn |
| `imports` (tùy hệ thống) | `importChunk` | `REQUIRED`, timeout phù hợp từng chunk | Không giữ một transaction cho toàn bộ file lớn |

**Trước khi cấu hình**, cần quyết định hai việc: service nào thực sự thuộc nhóm và policy ấy có hợp lý cho **toàn bộ các method** trong nhóm không. Nếu cùng một class chứa cả lệnh ghi và truy vấn, chỉ tách theo package có thể chưa đủ; nên chuyển thành các service chuyên trách hoặc thêm quy tắc tên method cụ thể trong cùng advice.

Không mặc định rằng:

- Một method HTTP GET luôn cần transaction.
- `read-only="true"` sẽ khiến database chắc chắn từ chối INSERT/UPDATE.
- Mỗi nhóm có advisor riêng tức là các lời gọi từ nhóm này sang nhóm khác tự tạo hai transaction độc lập.
- Một XML `transaction-manager` có thể tạo nguyên tử xuyên hai CSDL hoặc một broker nằm ngoài tài nguyên manager.

**Chính sách transaction là thiết kế nghiệp vụ và khả năng tài nguyên**, XML chỉ là cách mô tả/áp dụng.

## 4. Cấu hình XML chính: hai advice, hai pointcut, hai advisor

Giả sử các service đặt trong:

```text
lesson.xmltx.orders.OrderService
lesson.xmltx.reports.ReportService
```

Đặt policy vào `src/main/resources/transaction-policies.xml`:

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

    <!-- Nhóm ghi: rollback cả checked Exception đã thoát khỏi method. -->
    <tx:advice id="ordersTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="*"
                       propagation="REQUIRED"
                       read-only="false"
                       timeout="10"
                       rollback-for="java.lang.Exception"/>
        </tx:attributes>
    </tx:advice>

    <!-- Nhóm báo cáo: transaction đọc khi gọi từ ngoài. -->
    <tx:advice id="reportsTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="*"
                       propagation="REQUIRED"
                       read-only="true"
                       timeout="5"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="ordersOperations"
            expression="execution(* lesson.xmltx.orders.*Service.*(..))"/>
        <aop:pointcut id="reportsOperations"
            expression="execution(* lesson.xmltx.reports.*Service.*(..))"/>

        <aop:advisor advice-ref="ordersTxAdvice"
                     pointcut-ref="ordersOperations"/>
        <aop:advisor advice-ref="reportsTxAdvice"
                     pointcut-ref="reportsOperations"/>
    </aop:config>
</beans>
```

**Đọc cấu hình theo thứ tự:**

1. `ordersTxAdvice` định nghĩa quy tắc cho mọi tên method (`name="*"`) *nếu* pointcut của nhóm order match. `rollback-for="java.lang.Exception"` mở rộng rollback tới checked exception như `IOException`, ngoài hành vi rollback mặc định với unchecked exception.
2. `reportsTxAdvice` tạo transaction có read-only hint cho các method của nhóm báo cáo và timeout khởi tạo mới là 5 giây.
3. `execution(* lesson.xmltx.orders.*Service.*(..))` match thực thi method có kiểu trả về bất kỳ trên class có tên kết thúc bằng `Service` trong **package trực tiếp** `lesson.xmltx.orders`. Biểu thức tương ứng cho `reports`.
4. Hai `<aop:advisor>` gắn riêng policy với hai nhóm. Method ở `OrderService` không tự lấy `reportsTxAdvice`, và ngược lại.
5. `transaction-manager="transactionManager"` tham chiếu bean có tên đó trong Spring container. Với ví dụ bên dưới, nó là một `DataSourceTransactionManager` dùng chung H2 `DataSource`.
6. `proxy-target-class="true"` yêu cầu class-based proxy trong ví dụ. Class/method cần có khả năng được proxy intercept; nên dùng public method trên bean Spring, tránh final/private cho entry point transaction.

**Chú ý quy tắc matching:** mẫu trên chỉ match các class trong package trực tiếp, chưa bao gồm subpackage `orders.internal`. Nếu cấu trúc dự án yêu cầu các package con, có thể cân nhắc `execution(* lesson.xmltx.orders..*Service.*(..))` rồi xác minh phạm vi match trong test. Đừng thay bằng `execution(* lesson.xmltx..*.*(..))` một cách tùy tiện vì nó có thể mở transaction cho cả controller, utility hoặc lớp điều phối ngoài phạm vi thiết kế.

### 4.1. Vì sao không dùng chung một advice?

Một advice duy nhất có thể chứa nhiều dòng `tx:method`, nhưng các dòng này chủ yếu phân biệt **theo tên method**. Nếu cả hai nhóm đều có `execute`, `find` hoặc `process` nhưng chính sách khác nhau theo **vai trò service**, một advice gắn lên toàn bộ service layer dễ tạo cấu hình không rõ ràng.

Tách theo nhóm cho phép xem và sửa mỗi policy riêng, ví dụ nhóm order được phép ghi và rollback checked exception, nhóm report chuyên đọc; đồng thời điểm giới hạn phạm vi được thể hiện rõ ở pointcut.

Tuy nhiên, không nên nhân bản advice chỉ vì code nằm ở package khác. Nếu hai nhóm có cùng chính sách và cùng lifecycle, chúng có thể chia sẻ một advice với các pointcut được tổ chức hợp lý. Mục tiêu là **phản ánh khác biệt thực**, không tăng số XML element.

### 4.2. XML policy và @Transactional khác nhau ở đâu?

`<tx:advice>` + `<aop:advisor>` là cách gắn transaction attribute **từ bên ngoài Java source** bằng XML. Các method trong ví dụ **không có `@Transactional`**.

`<tx:annotation-driven/>` lại bật hạ tầng đọc annotation `@Transactional` trên bean. Đây là hai cách khai báo metadata; chúng đều có thể tạo transactional advice nhưng không phải hai thẻ đồng nghĩa. Tránh thêm cả hai rồi để cùng method bị hai advisor áp dụng mà không thiết kế rõ thứ tự/cấu hình. Với Spring Boot, annotation-driven transaction có thể được auto-config khi điều kiện phù hợp; XML advisor trong ví dụ vẫn có thể hoạt động độc lập vì có pointcut và `tx:advice` riêng.

## 5. Các tham số trên <tx:method> và cách chọn

`<tx:method name="...">` áp dụng transaction attribute cho mẫu tên method **đã qua pointcut**. Một vài thuộc tính:

| XML attribute | Mặc định thông dụng | Khi nào cân nhắc |
| --- | --- | --- |
| `name` | Bắt buộc | `find*`, `get*` hoặc `*` |
| `propagation` | `REQUIRED` | Join transaction hiện tại hoặc tạo mới nếu chưa có |
| `isolation` | `DEFAULT` | Chỉ định khi hiểu dữ liệu và yêu cầu đồng thời; với transaction mới |
| `read-only` | `false` | Đánh dấu thao tác đọc khi transaction manager/driver/ORM hỗ trợ |
| `timeout` | Thời hạn mặc định manager hoặc không giới hạn | Giới hạn thời gian transaction mới theo giây |
| `rollback-for` | Mặc định rollback unchecked exception và `Error` | Bổ sung checked exception cần rollback |
| `no-rollback-for` | Không có rule bổ sung | Một loại lỗi vẫn cho phép commit theo yêu cầu nghiệp vụ |

Với cùng một advice, có thể khai báo chính sách riêng cho nhóm tên method rồi có wildcard fallback:

```xml
<tx:advice id="mixedServiceAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

Đây là **minh họa lựa chọn policy trong một advice**, không phải cấu hình dùng thêm vào ví dụ hai nhóm ở trên. Spring chọn rule tên phù hợp nhất khi có nhiều pattern match, nên hãy kiểm tra method naming và test các method quan trọng; một phương thức tên `loadAndUpdate` sẽ không tự thành read-only chỉ vì nó “trông như truy vấn”.

**Ranh giới của các thuộc tính:**

- `read-only="true"` là chỉ dẫn cho hạ tầng, có thể dẫn đến tối ưu hóa hoặc hạn chế từ driver/DB tùy môi trường; **không coi đó là bảo mật hay ràng buộc chống ghi tuyệt đối**.
- `timeout` và `isolation` chủ yếu có ý nghĩa khi transaction vật lý mới được tạo. Nếu method chỉ tham gia transaction đã có theo `REQUIRED`, không nên kỳ vọng mọi thuộc tính inner policy sẽ tự ghi đè cấu hình transaction ngoài.
- `rollback-for` tác động khi ngoại lệ thoát qua transaction interceptor; nếu method bắt exception rồi trả bình thường, policy có thể xem thao tác đã thành công.
- `REQUIRES_NEW` tạo transaction vật lý độc lập và dùng thêm tài nguyên; chỉ chọn nếu cần kết quả commit độc lập theo nghiệp vụ, không dùng để giải quyết pointcut quá rộng.

## 6. Dự án chạy được để xác minh chính sách của hai nhóm

Ta tạo một ví dụ nhỏ với **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, **Spring AOP**, **H2**. Boot cung cấp cấu hình `DataSource` embedded và tải các bean; XML là nơi gắn transaction policy. Để tránh phụ thuộc vào tên transaction manager tự sinh, ta khai báo bean `transactionManager` rõ ràng bằng Java.

Hai nhóm có hành vi kiểm chứng được:

- `OrderService.createSuccess` insert thành công và commit.
- `OrderService.createThenFail` insert rồi ném **checked `IOException`**. XML `rollback-for` khiến insert bị rollback.
- `ReportService.findCount` truy vấn số dòng và in trạng thái transaction: transaction active và read-only true khi được gọi trực tiếp từ runner.

### 6.1. Cấu trúc tệp

```text
xml-transaction-groups/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/xmltx/
    │   ├── XmlPolicyApplication.java
    │   ├── orders/OrderService.java
    │   └── reports/ReportService.java
    └── resources/
        ├── schema.sql
        └── transaction-policies.xml
```

Tệp `transaction-policies.xml` **chính là XML ở phần 4**. Không thay đổi điểm nối các advisor khi chạy demo.

**`settings.gradle`**

```groovy
rootProject.name = 'xml-transaction-groups'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'lesson'
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
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` cung cấp JDBC, Spring transaction infrastructure và các dependency cần thiết; `spring-boot-starter-aop` cung cấp Spring AOP/AspectJ pointcut support. H2 là CSDL in-memory dùng cho bài học. Gradle 8.x tương thích Spring Boot 3.3 và JDK 17+ phù hợp cho ví dụ.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE purchase_order (
    id INT PRIMARY KEY,
    description VARCHAR(120) NOT NULL
);
```

Spring Boot tự khởi tạo `schema.sql` với H2 embedded lúc chạy. Ví dụ không cần web controller hay REST endpoint.

### 6.2. OrderService — nhóm ghi và rollback checked exception

**`src/main/java/lesson/xmltx/orders/OrderService.java`**

```java
package lesson.xmltx.orders;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void createSuccess(int id) {
        showTransaction("order success");

        jdbc.update(
            "INSERT INTO purchase_order(id, description) VALUES (?, ?)",
            id, "created"
        );
    }

    public void createThenFail(int id) throws IOException {
        showTransaction("order failure");

        jdbc.update(
            "INSERT INTO purchase_order(id, description) VALUES (?, ?)",
            id, "should rollback"
        );

        // Checked exception: XML rollback-for phải có hiệu lực.
        throw new IOException("checked failure");
    }

    private static void showTransaction(String label) {
        System.out.println(label + " txActive=" +
            TransactionSynchronizationManager.isActualTransactionActive() +
            " readOnly=" +
            TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }
}
```

**Không có `@Transactional` trong service này.** Transaction vẫn được áp dụng vì XML pointcut match public method của class `OrderService` và advisor gắn `ordersTxAdvice`. `showTransaction` là private helper được gọi từ method đang có transaction; helper không cần bị proxy intercept riêng.

Nếu `createThenFail` không có policy rollback checked exception, Spring mặc định thường **commit** khi method ném checked `IOException`. Bài demo chứng minh XML `rollback-for="java.lang.Exception"` thay đổi quyết định đó: insert của lần lỗi được rollback.

### 6.3. ReportService — nhóm truy vấn read-only

**`src/main/java/lesson/xmltx/reports/ReportService.java`**

```java
package lesson.xmltx.reports;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReportService {
    private final JdbcTemplate jdbc;

    public ReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int findCount() {
        System.out.println("report find txActive=" +
            TransactionSynchronizationManager.isActualTransactionActive() +
            " readOnly=" +
            TransactionSynchronizationManager.isCurrentTransactionReadOnly());

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM purchase_order",
            Integer.class
        );
        return count;
    }
}
```

Method `findCount` không mang annotation nhưng được pointcut `reportsOperations` match. Với lời gọi từ runner bên ngoài transaction, `reportsTxAdvice` tạo transaction mới với `read-only="true"`. Phép đọc `isCurrentTransactionReadOnly()` xác nhận **metadata của transaction hiện tại** trong Spring; nó không chứng minh H2 từ chối mọi câu lệnh ghi. Không dùng một flag này để khẳng định DB luôn chạy ở mức isolation cụ thể.

### 6.4. Main application: load XML và tạo transaction manager phù hợp

**`src/main/java/lesson/xmltx/XmlPolicyApplication.java`**

```java
package lesson.xmltx;

import java.io.IOException;

import javax.sql.DataSource;

import lesson.xmltx.orders.OrderService;
import lesson.xmltx.reports.ReportService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ImportResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
@ImportResource("classpath:transaction-policies.xml")
public class XmlPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(XmlPolicyApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(OrderService orders, ReportService reports) {
        return args -> {
            orders.createSuccess(101);
            System.out.println("count after success=" + reports.findCount());

            try {
                orders.createThenFail(102);
            } catch (IOException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("count after failure=" + reports.findCount());
        };
    }
}
```

**Tại sao cách cấu hình này có hiệu lực?**

- `@SpringBootApplication` quét hai `@Service` dưới package `lesson.xmltx`; vì vậy Spring sở hữu các bean và có thể tạo proxy.
- `@ImportResource` nạp chính xác file XML trong `src/main/resources`, đăng ký hai transaction advice và hai advisor.
- `transactionManager` là tên bean được hai `<tx:advice>` tham chiếu. Nó sử dụng cùng `DataSource` mà `JdbcTemplate` đã được Boot cấu hình.
- `CommandLineRunner` nhận service qua dependency injection, nên caller gọi proxy. Không sử dụng `new OrderService(...)`, không gọi method có transaction qua `this.method()` trong cùng bean.
- Mỗi lần `reports.findCount()` chạy sau khi method order đã kết thúc qua proxy, nên phép đọc diễn ra sau commit hoặc rollback của giao dịch order. Điều đó giúp kiểm tra kết quả cuối cùng.

### 6.5. Chạy ứng dụng và đối chiếu kết quả

Từ thư mục dự án, với JDK 17+ và Gradle 8.x phù hợp:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper tương thích, có thể chạy `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Không dùng `javac` thuần cho dự án có thư viện Spring/H2 ngoài JDK; Gradle cung cấp classpath.

Bỏ qua log startup Spring Boot/Gradle. Các dòng in bởi chương trình sẽ theo thứ tự:

```text
order success txActive=true readOnly=false
report find txActive=true readOnly=true
count after success=1
order failure txActive=true readOnly=false
caught=checked failure
report find txActive=true readOnly=true
count after failure=1
```

**Giải thích từng kết quả:**

1. `createSuccess(101)` được orders advisor mở transaction read-write; INSERT thành công và commit. Truy vấn báo cáo đầu tiên thấy một dòng.
2. `findCount` được reports advisor mở transaction mới read-only; vì runner không có transaction ngoài, flag Spring là `txActive=true readOnly=true`.
3. `createThenFail(102)` insert id 102 rồi ném checked `IOException`. Advice order match rule rollback-for `java.lang.Exception` nên Spring rollback transaction của method này.
4. Runner bắt exception **ở phía ngoài proxy**, sau khi transaction interceptor đã xử lý rollback. Truy vấn tiếp theo vẫn thấy một dòng, chứng minh id 102 không được commit.
5. Không có annotation trên hai service. Hành vi khác nhau hoàn toàn đến từ **pointcut + advice + transaction manager** trong XML.

Nếu bỏ riêng thuộc tính `rollback-for="java.lang.Exception"` của orders advice rồi khởi chạy lại với H2 mới, một checked `IOException` thông thường không gây rollback theo mặc định; số dòng có thể tăng thành 2. Đây là cách đối chiếu chính sách XML, nhưng **không phải cấu hình chuẩn của bài chạy ban đầu**.

## 7. Tách theo tên method bên trong cùng nhóm

Không phải lúc nào một package đồng nghĩa một policy. Ví dụ, nhóm `customer` vừa có truy vấn vừa có ghi. Khi tách package chưa thực tế, có thể dùng rule theo tên:

```xml
<tx:advice id="customerTxAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" propagation="REQUIRED" read-only="true"/>
        <tx:method name="get*" propagation="REQUIRED" read-only="true"/>
        <tx:method name="calculate*" propagation="SUPPORTS" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"
                   rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

Đây là một **biến thể độc lập**, không đưa vào XML dự án demo. Muốn áp dụng, phải tạo pointcut/advisor riêng cho `customer` và xác nhận nó không đè phạm vi các advisor khác.

Bộ chọn `name` có thể dùng `*` làm fallback. Tuy nhiên, method tên `getAndCreate` mà thực chất ghi dữ liệu sẽ bị xem là read-only nếu chỉ dựa tên; cách bền vững là **thiết kế API phù hợp ý nghĩa** và thêm kiểm thử cho nhóm policy. Nếu số exception hoặc timeout khác nhau theo case quan trọng, tách bean hoặc thêm rule chính xác hơn thay vì một glob khó hiểu.

**`propagation="SUPPORTS"` không tương đương `REQUIRED`:** khi không có transaction ngoài, SUPPORTS không mở transaction vật lý mới. Vì thế, nếu mục tiêu là có một transaction đọc thực sự để xác định snapshot, `REQUIRED` là lựa chọn cần cân nhắc. `read-only="true"` trên cấu hình SUPPORTS không biến một method không có physical transaction thành một DB transaction.

## 8. Điều gì xảy ra khi hai nhóm gọi lẫn nhau?

Một lỗi thiết kế phổ biến là xem mỗi advisor là một transaction “độc lập” cho từng method. Thực tế, propagation điều khiển quan hệ giữa các transaction:

| Luồng gọi | Với `REQUIRED` ở cả hai nhóm | Kết luận |
| --- | --- | --- |
| Runner → `orders.createSuccess` | Order mở một transaction read-write | Commit khi order proxy kết thúc |
| Runner → `reports.findCount` | Report mở một transaction read-only | Query trong transaction đọc mới |
| Order method → report method qua Spring proxy | Report thường **tham gia transaction read-write hiện có** | `read-only="true"` ở method report không biến transaction vật lý đã mở thành read-only |
| Report method → order method qua Spring proxy | Order thường tham gia transaction đọc hiện có | Cấu hình inner read-write không bảo đảm “nâng cấp” transaction vật lý; tránh ghi trong scope đọc |
| Outer method → inner method cùng bean qua `this.inner()` | Lời gọi inner bypass AOP proxy | XML advisor cho inner không chạy riêng; vẫn có thể dùng transaction của outer |

Nếu nhóm báo cáo cần snapshot tách biệt thực sự khỏi một transaction đang ghi, có thể cần thiết kế ranh giới khác, manager/propagation phù hợp và chi phí tài nguyên tương ứng. Không thêm `REQUIRES_NEW` theo thói quen, vì nó có thể tạo commit riêng ngay cả khi use case bên ngoài rollback, dùng thêm connection và làm rối invariant nghiệp vụ.

Tương tự, nếu code gọi HTTP, gửi email, queue hoặc CSDL khác, local transaction manager không tự điều khiển các tài nguyên đó. Cấu hình nhiều policy XML **không phải giải pháp atomicity xuyên hệ thống**.

## 9. Cách chọn pointcut để các nhóm không chồng lấn

### 9.1. Match theo package ổn định

Giả sử cấu trúc:

```text
lesson.xmltx.orders.OrderService
lesson.xmltx.orders.internal.ValidationService
lesson.xmltx.reports.ReportService
lesson.xmltx.shared.AuditService
```

`execution(* lesson.xmltx.orders.*Service.*(..))` match các class `*Service` thuộc package `orders` trực tiếp, không tự match `orders.internal`. `execution(* lesson.xmltx.orders..*Service.*(..))` có thể match thêm các package con. Cần xem `ValidationService` có nên là transaction entry point hay chỉ là helper chạy trong transaction của `OrderService`; không mở rộng pointcut chỉ vì muốn “bao phủ hết”.

**Kiểm tra bằng test** các method quan trọng đã được advice match, nhất là sau khi chuyển package, đổi tên service hoặc tách class.

### 9.2. Tránh nhiều advisor cùng match một lời gọi

Nếu thêm một pointcut tổng quát như `execution(* lesson.xmltx..*Service.*(..))` và gắn một advice khác, một `OrderService` có thể bị cả advisor tổng quát lẫn advisor nhóm order intercept. Tùy thứ tự advice và propagation, kết quả có thể là nhiều scope logic, tham gia cùng transaction vật lý hoặc có transaction mới độc lập. **Không giả định advisor khai báo sau sẽ ghi đè advisor trước.**

Cách làm an toàn:

1. Thiết kế package/class pattern sao cho các nhóm policy không giao nhau.
2. Nếu bắt buộc có nhiều advice, xác định thứ tự `order` trên `<aop:advisor>` và ý nghĩa về transaction boundary; kiểm thử kỹ exception/commit.
3. Dùng một transaction policy làm chủ ranh giới use case; chỉ thêm policy thứ hai khi có mục đích rõ ràng, tránh vô tình chồng `REQUIRES_NEW`.

### 9.3. Scope hẹp giúp tránh áp dụng transaction vào controller

Một pointcut quá rộng có thể proxy controller, utility, mapper hoặc method điều phối dài hạn. Kết quả là transaction bắt đầu sớm, giữ DB connection lâu trong khi gọi dịch vụ ngoài, tăng lock contention và khó biết scope commit thực tế.

Nên đặt **transaction boundary** ở application/service use case; pointcut theo nhóm chỉ là công cụ thể hiện ranh giới đó trong cấu hình XML.

## 10. Nếu muốn cấu hình toàn bộ transaction manager bằng XML

Trong ví dụ Spring Boot, `DataSource` được auto-config và `transactionManager` là Java bean để bài gọn, dễ chạy. Với ứng dụng Spring Framework thuần, có thể khai báo cả manager bằng XML, ví dụ:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
</bean>
```

Đây chỉ là **mảnh cấu hình**: còn cần bean `dataSource` hợp lệ, Spring context, JDBC driver và bean service trong cùng context. Không thêm bean trên vào dự án demo khi `transactionManager` Java bean đã tồn tại; hai định nghĩa cùng tên sẽ xung đột hoặc phụ thuộc quy tắc bean overriding.

Với một manager khác tên, phải đổi tất cả tham chiếu XML tương ứng:

```xml
<tx:advice id="ordersTxAdvice" transaction-manager="ordersTransactionManager">
    <tx:attributes>
        <tx:method name="*" rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

Nếu hệ thống có hai `DataSource`, mỗi manager phải được gắn đúng tài nguyên. Gán service vào “nhóm khác” mà advisor vẫn tham chiếu manager của DB cũ sẽ khiến việc đọc/ghi không tham gia như mong muốn. Hai manager local cũng không tự kết hợp thành một distributed atomic transaction.

## 11. Những lỗi cấu hình XML thường gặp

**Lỗi 1 — Có `<tx:advice>` nhưng không có advisor.** Advice khai báo policy, nhưng không được nối vào pointcut nên không có lời gọi nào được nó intercept. Cần `<aop:advisor advice-ref="..." pointcut-ref="..."/>` và Spring AOP runtime.

**Lỗi 2 — Sai package hoặc tên class trong pointcut.** XML vẫn có thể load, nhưng service không match nên không có transaction. Kiểm tra tên package đầy đủ, tên method/class, matcher và proxy.

**Lỗi 3 — Chỉ cấu hình `<tx:annotation-driven/>` rồi mong XML `tx:method` tự áp dụng.** Annotation-driven chỉ xử lý annotation; muốn rule XML theo group phải có `tx:advice`, pointcut và advisor tương ứng.

**Lỗi 4 — Nghĩ `name="find*"` match method ở mọi package.** `tx:method` chỉ chọn attribute của lời gọi đã thỏa pointcut. Xác định từng tầng chọn lọc.

**Lỗi 5 — Gọi service bằng `new` hoặc `this.inner()`.** Với proxy mode mặc định, lời gọi không đi qua proxy tương ứng, nên advisor XML không chạy riêng. Gọi qua Spring bean được inject; nếu outer đã có transaction, inner có thể chỉ tham gia transaction đó.

**Lỗi 6 — Đặt policy cho private/final method.** Class-based proxy không thể override private/final method để can thiệp. Chọn public non-final method làm điểm bắt đầu transaction hoặc thiết kế lại bean boundary.

**Lỗi 7 — Tin `read-only="true"` là khóa chống ghi tuyệt đối.** Đây là hint hoặc mức enforcement tùy driver/manager/DB. Không dùng nó thay constraint, quyền DB và kiểm thử.

**Lỗi 8 — Bắt checked exception rồi không rethrow.** `rollback-for` chỉ làm việc nếu transaction interceptor thấy exception phù hợp hoặc transaction đã được đánh dấu rollback-only. Nuốt lỗi rồi return có thể dẫn tới commit.

**Lỗi 9 — Cùng method match nhiều advisor có policy khác nhau.** Chúng có thể lồng nhau, không có semantics “advisor cuối thắng”. Kiểm soát phạm vi, order và propagation.

**Lỗi 10 — Chọn nhầm transaction manager.** Service dùng `JdbcTemplate` của DB A nhưng advice mở transaction trên DB B không cho kết quả atomic của DB A. Phải kiểm tra bean `DataSource`, manager, repository thực tế.

**Lỗi 11 — Bài test có `@Transactional` bao ngoài.** Spring Test có thể rollback mặc định cuối test, che việc service không rollback đúng trong môi trường chạy thực. Kiểm tra trạng thái DB **sau khi scope của method kết thúc**, tránh transaction test làm sai tín hiệu.

**Lỗi 12 — Transaction bao quanh mạng và batch quá dài.** Policy dùng một timeout cho mọi method có thể làm job lớn timeout, trong khi request ngắn hoạt động tốt. Tách ranh giới theo chunk hoặc use case; không chỉ nới timeout toàn hệ thống.

## 12. Kiểm thử và quan sát policy đang áp dụng

Để xác minh **đúng nhóm, đúng policy, đúng dữ liệu**, kiểm tra ba tầng:

1. **Pointcut và proxy:** bean được Spring inject, method thật có đi qua proxy, advisor nào match? Có self-invocation hoặc class/method không thể proxy?
2. **Transaction attribute:** ngay trong method, `TransactionSynchronizationManager.isActualTransactionActive()` và `isCurrentTransactionReadOnly()` có phù hợp với mục đích test không? Timeout/propagation có đúng khi method mở transaction mới?
3. **Kết quả dữ liệu:** với một transaction có INSERT rồi ném lỗi, đọc lại DB từ scope ngoài sau khi method kết thúc; có rollback đúng theo checked/unchecked rule không?

Có thể bật tạm log giao dịch để quan sát Spring tạo/hoàn thành transaction:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Đây là các thuộc tính hỗ trợ debug, không cần thêm vào dự án để có output minh họa phía trên. Tránh dùng mỗi log “Getting transaction for method” làm bằng chứng mọi thao tác của DB cùng tham gia transaction; kết quả SQL sau commit/rollback vẫn là phép kiểm mạnh nhất.

Kiểm thử gợi ý cho code production:

- **Nhóm order:** insert thành công; RuntimeException rollback; checked exception theo policy rollback; exception bị swallow theo chủ ý có thể commit.
- **Nhóm report:** đọc bình thường; flag Spring read-only khi gọi trực tiếp; không suy diễn rằng DB cấm write.
- **Luồng xuyên nhóm:** order gọi report và report gọi order qua proxy; xác nhận propagation `REQUIRED` không đổi read-only của transaction vật lý bên ngoài.
- **Boundary:** self-invocation, bean do `new`, method final/private hoặc class mới chuyển package; bảo đảm test phát hiện mất interception.
- **Overlapping advisor:** nếu thực sự có, test thứ tự advice/transaction manager và kết quả rollback ở từng scope.

## 13. Checklist quyết định trước khi triển khai

Đặt những câu hỏi này khi thêm một service mới vào XML:

- Service mới có cùng **ý định nghiệp vụ** và chính sách giao dịch với nhóm đã có không?
- Pointcut nào match method đó? Có match nhầm các service khác hoặc bỏ sót subpackage?
- `tx:advice` nào áp dụng? Có `tx:method name="*"` fallback, rollback và timeout đúng không?
- Có một advisor khác cũng match method ấy không? Nếu có, đó là thiết kế chủ ý hay lỗi?
- Method được gọi qua Spring proxy và dùng đúng transaction manager/tài nguyên hay không?
- Method tham gia transaction ngoài hay mở transaction mới? `read-only`, timeout và isolation có thật sự hiệu lực trong trường hợp đó không?
- Đã có kiểm thử trạng thái dữ liệu sau commit/rollback với lỗi xảy ra giữa các thao tác chưa?

**Nguyên tắc:** tách chính sách theo **loại công việc và ranh giới tài nguyên**, dùng pointcut để khoanh đúng nhóm, dùng `tx:advice` để mô tả hành vi, rồi kiểm thử hậu quả thực tế trên DB.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `<tx:advice>` có đủ để mọi service tự có transaction không?

**Trả lời:** Chưa. Còn cần advisor/pointcut kết nối với lời gọi thực tế qua Spring AOP proxy, manager phù hợp và bean nằm trong Spring context.

**Câu 2.** Hai service đều có method `process()` nhưng nhóm order cần rollback checked exception, nhóm report chỉ đọc. Có tách bằng `tx:method name="process"` trong một advice chung được không?

**Trả lời:** Một rule tên method chung không phân biệt được nhóm; nên dùng pointcut theo package/class và hai advice riêng (hoặc tổ chức service API/rule khác phù hợp), để mỗi nhóm có chính sách rõ.

**Câu 3.** Trong demo, vì sao `IOException` từ `createThenFail` rollback được?

**Trả lời:** Vì XML orders advice match method qua pointcut và quy định `rollback-for="java.lang.Exception"`. Checked `IOException` thoát ra ngoài method qua proxy, được transaction interceptor xử lý rollback.

**Câu 4.** `ReportService.findCount()` có `read-only="true"`, nếu được gọi trong transaction read-write đã có của nhóm order thì physical transaction có trở thành read-only không?

**Trả lời:** Không. Với `REQUIRED`, report thường tham gia transaction hiện có và không tự ghi đè đặc tính transaction vật lý phía ngoài.

**Câu 5.** Thêm một advisor tổng quát match mọi `*Service` với `REQUIRES_NEW` có làm “policy thứ hai thay thế policy cũ” không?

**Trả lời:** Không. Nhiều advice có thể cùng chạy quanh một lời gọi, tạo các scope transaction lồng nhau tùy thứ tự/propagation. Phải chủ động kiểm soát điểm match và thứ tự; tránh tạo advisor chồng chéo ngoài ý định.

**Câu 6.** Có nên cấu hình `read-only="true"` cho mọi method `find*` rồi xem đó là bảo đảm an toàn dữ liệu?

**Trả lời:** Không. Read-only có ý nghĩa khác nhau tùy manager/DB và chỉ là một phần của thiết kế; cần kiểm soát quyền DB, constraint và API phù hợp.

## 15. Tài liệu tham khảo

- Spring Framework — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring Framework — Understanding Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `<tx:advice/>` Settings: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Ghi nhớ:** XML có thể phân chia transaction policy thành nhiều nhóm rõ ràng: **pointcut quyết định ai được intercept, advice quyết định xử lý transaction ra sao, manager quyết định tài nguyên được commit/rollback**. Khi một method được gọi trong transaction đã tồn tại, propagation mới là yếu tố xác định chính sách thực sự có tác dụng đến mức nào.