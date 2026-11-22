# REQUIRED — Tham gia giao dịch vật lý đang có trong Spring Framework

## 1. Mục tiêu và ý tưởng quan trọng nhất

`Propagation.REQUIRED` là **chế độ propagation mặc định** của transaction declarative trong Spring Framework. Khi một phương thức có `@Transactional` được gọi qua transaction infrastructure:

- Nếu **chưa có transaction thích hợp**, nó khởi tạo một transaction vật lý mới.
- Nếu **đã có transaction vật lý do manager tương ứng quản lý**, nó **tham gia transaction đang có**. Phương thức được gọi bên trong có **phạm vi giao dịch logic riêng**, nhưng không sở hữu commit vật lý độc lập.

Điểm cần nhớ là: **hai phương thức `@Transactional(REQUIRED)` không có nghĩa có hai transaction vật lý**. Chúng thường là hai transaction scope logic cùng điều khiển một transaction vật lý. Chỉ khi scope tạo ra transaction ngoài cùng hoàn tất thành công, thay đổi thuộc transaction chung mới thực sự được commit.

Ví dụ trong đơn hàng:

```text
OrderService.placeOrder()  [REQUIRED — mở transaction T]
  ├─ INSERT orders          [transaction T]
  ├─ InventoryService.reserve() [REQUIRED — tham gia T]
  │    └─ UPDATE stock      [transaction T]
  └─ INSERT order_items     [transaction T]
Kết thúc outer scope        [COMMIT hoặc ROLLBACK transaction T]
```

Nếu thao tác tồn kho thất bại theo rule rollback, cả đơn hàng và tồn kho trong transaction T thường bị hủy. Nếu tồn kho đã “tham gia” T, nó **không thể tự commit một phần của T** trong khi outer transaction vẫn đang tiếp tục.

Học xong bài này, bạn sẽ:

1. Phân biệt **transaction vật lý**, **logical transaction scope** và connection/tài nguyên DB.
2. Hiểu `REQUIRED` hành xử khác nhau khi có hoặc không có transaction hiện hữu.
3. Giải thích tại sao inner method kết thúc bình thường chưa chắc dữ liệu đã commit.
4. Phân tích `rollback-only` và nguyên nhân `UnexpectedRollbackException` khi inner scope lỗi nhưng outer đã bắt exception.
5. Chạy ví dụ Java 17+, Spring JDBC và H2 cho bốn trường hợp: outer/inner thành công, inner thất bại và outer bắt lỗi, outer thất bại, inner chạy độc lập.
6. Dùng `REQUIRED` đúng ranh giới nghiệp vụ và tránh nhầm lẫn với `REQUIRES_NEW`, `NESTED`, self-invocation, `readOnly` hay transaction khác manager.

Phạm vi bài là **Spring Framework — transaction management**, nhóm **REQUIRED**. Các ví dụ chính dùng một transaction manager imperative quản lý **một DataSource**. Các trường hợp đa tài nguyên hoặc reactive có cơ chế riêng.

## 2. “Tham gia giao dịch vật lý đang có” nghĩa là gì?

### 2.1. Transaction vật lý

Transaction vật lý (*physical transaction*) là transaction thật do tài nguyên quản lý: ví dụ trên JDBC, một connection đang nằm giữa `BEGIN`/các thao tác SQL/`COMMIT` hoặc `ROLLBACK` theo cách driver/DB triển khai. Spring `DataSourceTransactionManager` hoặc `JdbcTransactionManager` điều phối connection từ `DataSource` và transaction ấy.

Khi một service gọi một service khác, Spring có thể tạo **hai phạm vi transaction logic**, nhưng giữ cùng transaction vật lý T:

```text
                 Thread thực hiện request
    ┌───────────────────────────────────────────┐
    │ OuterService.execute()                     │
    │ @Transactional(REQUIRED)                   │
    │    logical scope A — chủ T                 │
    │    ┌──────────────────────────────────┐    │
    │    │ InnerService.apply()             │    │
    │    │ @Transactional(REQUIRED)         │    │
    │    │    logical scope B — tham gia T   │    │
    │    └──────────────────────────────────┘    │
    └───────────────────────────────────────────┘
                       |
                       v
             Một transaction vật lý T
             trên cùng JDBC DataSource
                       |
                COMMIT hoặc ROLLBACK
                   do scope A
```

Đây là **một tài nguyên transaction chung**, chứ không phải B mở transaction mới rồi “gộp” kết quả vào A sau đó.

### 2.2. Transaction scope logic

Mỗi phương thức đi qua Spring transaction interceptor với `REQUIRED` tạo **logical transaction scope**. Scope này có thể:

- Khai báo transaction attributes của riêng mình.
- Tham gia transaction vật lý hiện có.
- Quan sát transaction đang active và sử dụng tài nguyên đã bind.
- Đánh dấu rollback-only khi exception phù hợp đi qua advice hoặc khi ứng dụng yêu cầu.
- Kết thúc invocation của nó trước scope ngoài.

Phạm vi logic bên trong **không đồng nghĩa** một commit vật lý riêng. Một inner method return thành công chỉ có nghĩa nó đã hoàn thành phần Java và transaction advice của nó xử lý xong phạm vi logic. Outer method vẫn có thể lỗi ở bước sau, khiến **toàn bộ T rollback**.

### 2.3. Ma trận: có hay không có transaction hiện tại?

| Trước khi gọi method `REQUIRED` | Method làm gì? | Có tạo transaction vật lý mới? | Ai quyết định commit cuối? |
| --- | --- | --- | --- |
| Không có transaction | Tạo transaction T | **Có** | Scope này, trừ trường hợp đặc biệt về manager/outer infrastructure |
| Có transaction T của cùng manager/tài nguyên thích hợp | Tham gia T | **Không** | Scope đã mở T |
| Có một scope khác đang tham gia T | Tiếp tục tham gia T | **Không** | Scope chủ T |
| Có transaction của tài nguyên/manager khác | Phải phân tích manager và resource thực tế | Không thể suy ra chỉ từ annotation | Từng manager/tài nguyên theo cấu hình |
| Gọi trực tiếp target không qua proxy (proxy mode) | Transaction advice cho method không chạy riêng | Không do annotation method đó | Transaction sẵn có nếu có; nếu không là ngoài transaction Spring |

Bảng này giả định propagation `REQUIRED` được áp dụng thật sự qua Spring AOP hoặc cơ chế advice tương ứng; một annotation trên method không được intercept thì không tự tạo scope logic mới.

## 3. Spring thực thi REQUIRED như thế nào?

`@Transactional` là metadata. Hạ tầng Spring dùng `TransactionInterceptor` cùng `PlatformTransactionManager` và transaction attributes để mở/tham gia transaction.

Một luồng chuẩn:

```text
Caller → Spring AOP proxy của OuterService
   |
   v
TransactionInterceptor của outer
   |
   +-- getTransaction(REQUIRED), chưa có T
   +-- tạo transaction vật lý T, bind resource vào thread
   |
   v
OuterService.execute()
   |
   +-- SQL của outer dùng T
   |
   +-- gọi Spring AOP proxy của InnerService
        |
        v
      TransactionInterceptor của inner
        |
        +-- getTransaction(REQUIRED), đã có T
        +-- tham gia T (không BEGIN/connection transaction thứ hai)
        |
        v
      InnerService.apply()
        |
        +-- SQL của inner dùng T
        +-- return hoặc exception
        |
        v
      Inner advice kết thúc logical scope B
   |
   +-- OuterService tiếp tục
   |
   v
Outer advice kết thúc logical scope A
   |
   +-- T chưa rollback-only và không lỗi → COMMIT T
   +-- T rollback-only / lỗi cần rollback → ROLLBACK T
   |
   v
Caller nhận return hoặc exception
```

Trong mô hình JDBC imperative thông dụng, Spring bind connection/resource với thread thông qua `TransactionSynchronizationManager`. `JdbcTemplate` và `DataSourceUtils` biết cách lấy connection đang được quản lý. Vì thế outer và inner thường thực hiện SQL trên **cùng connection trong một physical transaction**, nếu đều dùng đúng `DataSource`.

**Một connection không có nghĩa mọi thao tác đều transaction-safe:** nếu code tự mở connection qua API không tuân theo cách Spring bind resource, sử dụng `DataSource` khác, gọi hệ thống ngoài, hoặc chuyển thread, chúng có thể không tham gia T. Điều cần kiểm chứng là **manager và resource** chứ không chỉ bean có `@Transactional`.

### 3.1. REQUIRED là mặc định

Các khai báo sau thường tương đương về propagation:

```java
@Transactional
public void updateInvoice() {
    // ...
}

@Transactional(propagation = Propagation.REQUIRED)
public void updatePayment() {
    // ...
}
```

Đây là minh họa về annotation; không phải class độc lập. `Propagation.REQUIRED` thuộc package `org.springframework.transaction.annotation`. Ngoài propagation còn có rollback rules, read-only, isolation, timeout; chúng được phân tích sau.

### 3.2. Khái niệm isNewTransaction()

Với Spring imperative, bên trong method được transaction advice intercept, có thể kiểm tra:

```java
boolean newPhysical =
    TransactionAspectSupport.currentTransactionStatus()
        .isNewTransaction();
```

Trong ví dụ đơn giản với `DataSourceTransactionManager`:

- Outer bắt đầu transaction T: `isNewTransaction() == true`.
- Inner `REQUIRED` tham gia T: `isNewTransaction() == false`.
- Inner được gọi trực tiếp từ caller không có transaction: `isNewTransaction() == true`.

Đây là một chỉ báo tiện lợi về vai trò của transaction scope hiện tại đối với manager, không phải kết luận rằng một database transaction có thể bao trùm mọi hệ thống bên ngoài.

Cẩn thận: `TransactionAspectSupport.currentTransactionStatus()` yêu cầu có transaction status được gắn với invocation của Spring transaction aspect; gọi ở một method không được advice quản lý có thể ném `NoTransactionException`.

## 4. Ví dụ nghiệp vụ: một commit chung cho hai service

Giả sử đặt đơn hàng cần ghi record đơn và trừ tồn kho:

```java
@Service
public class OrderService {
    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder() {
        saveOrder();
        inventory.reserveStock();
    }
}

@Service
public class InventoryService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void reserveStock() {
        decreaseStock();
    }
}
```

Mã trên là **minh họa kiến trúc**, thiếu implementation của `saveOrder`, `decreaseStock` và các import. Khi hai bean được Spring quản lý, caller đi qua proxy, và hai thao tác DB dùng cùng transaction manager/DataSource:

- `placeOrder` khởi tạo T.
- `reserveStock` gia nhập T, không tạo transaction vật lý mới.
- Nếu cả hai method thành công, T commit khi `placeOrder` kết thúc qua interceptor.
- Nếu `reserveStock` lỗi runtime thoát qua proxy, T thường bị đánh dấu rollback-only; khi scope ngoài kết thúc, T không được commit.
- Nếu `reserveStock` thành công nhưng `placeOrder` lỗi về sau, phần trừ tồn kho **vẫn rollback** cùng đơn hàng.

Điểm thiết kế quan trọng: **transaction boundary ở cấp use case** giúp bảo vệ invariant “đơn hợp lệ và tồn kho đồng bộ”. Để unit of work này atomic, không tự thay inner sang `REQUIRES_NEW`: nó có thể commit tồn kho riêng dù outer thất bại.

## 5. Demo chạy được: REQUIRED dùng chung physical transaction

Ta sử dụng **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, **H2 in-memory**. Bài chạy là một dự án Gradle nhỏ, không yêu cầu server. Nó cố ý gọi service qua Spring proxy và dùng một `DataSourceTransactionManager` để kết quả rõ ràng.

### 5.1. Cấu trúc thư mục

```text
required-join-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/required/
    │   ├── RequiredApplication.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'required-join-demo'
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
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và Spring transaction infrastructure. H2 là database embedded, Spring Boot sẽ sử dụng `schema.sql` để khởi tạo bảng. Version trong ví dụ phục vụ tái hiện; triển khai production nên cập nhật theo phiên bản Spring Boot còn được hỗ trợ.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

Từng scenario dùng id khác nhau. Chúng ta đọc lại số record **sau khi scope transaction kết thúc**, tránh kết luận từ dữ liệu đang chưa commit.

### 5.2. InnerService — REQUIRED có thể join hoặc tự mở transaction

**`src/main/java/lesson/required/InnerService.java`**

```java
package lesson.required;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(int id) {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("inner newTx=" + newTransaction);
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, "inner"
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeAndFail(int id) {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("innerFail newTx=" + newTransaction);
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, "inner-fail"
        );

        throw new IllegalStateException("inner boom");
    }
}
```

Cả hai method được đánh dấu `REQUIRED`. **Chúng không tự quyết định luôn có transaction mới.** Khi được gọi từ outer transaction, `isNewTransaction()` là `false`. Khi được gọi từ runner không có transaction bên ngoài, `write(7)` tự tạo transaction và `isNewTransaction()` là `true`.

Trong ca lỗi, `writeAndFail` INSERT trước rồi mới ném `IllegalStateException`. Exception runtime đi qua inner interceptor theo rollback rule mặc định.

### 5.3. OuterService — tạo transaction cho cả unit of work

**`src/main/java/lesson/required/OuterService.java`**

```java
package lesson.required;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            1, "outer-success"
        );

        inner.write(2);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchesInner() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            3, "outer-before-inner-failure"
        );

        try {
            inner.writeAndFail(4);
        } catch (IllegalStateException ex) {
            System.out.println("outer caught=" + ex.getMessage());
        }

        System.out.println("outer reached return");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void failsOuter() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            5, "outer-before-own-failure"
        );

        inner.write(6);
        throw new IllegalStateException("outer boom");
    }

    private static void showOuterTransaction() {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("outer newTx=" + newTransaction);
    }
}
```

Trong cả ba method public được gọi từ runner, outer là chủ sở hữu transaction vật lý mới. `inner` là **bean khác được inject**, nên lời gọi `inner.write(...)` hoặc `inner.writeAndFail(...)` đi qua proxy riêng và tạo logical scope của inner.

Không được thay lời gọi này bằng `this.innerMethod()` rồi giả định vẫn có một advice riêng: self-invocation trong Spring proxy mode không chạy transactional advice cho inner method, dù nó có thể tiếp tục dùng transaction đã mở ở outer.

### 5.4. Application — tạo manager, gọi đúng proxy, đọc kết quả DB

**`src/main/java/lesson/required/RequiredApplication.java`**

```java
package lesson.required;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class RequiredApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            OuterService outer, InnerService inner, JdbcTemplate jdbc) {
        return args -> {
            // 1. Outer thành công; inner cùng tham gia và commit chung.
            outer.success();
            System.out.println("successRows=" + count(jdbc, 1, 2));

            // 2. Inner đánh dấu rollback-only, outer bắt lỗi rồi return.
            try {
                outer.catchesInner();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "caughtOutcome=" + ex.getClass().getSimpleName());
            }
            System.out.println("caughtRows=" + count(jdbc, 3, 4));

            // 3. Inner thành công nhưng outer thất bại: rollback cả hai.
            try {
                outer.failsOuter();
            } catch (IllegalStateException ex) {
                System.out.println("outerError=" + ex.getMessage());
            }
            System.out.println("outerFailureRows=" + count(jdbc, 5, 6));

            // 4. Không có outer transaction; REQUIRED của inner tự mở.
            inner.write(7);
            System.out.println("standaloneRows=" + count(jdbc, 7, 7));
        };
    }

    private static int count(JdbcTemplate jdbc, int fromId, int toId) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id BETWEEN ? AND ?",
            Integer.class, fromId, toId
        );
        return value;
    }
}
```

**Tại sao cấu hình này rõ ràng?**

- `@SpringBootApplication` quét các service cùng package `lesson.required`.
- `@EnableTransactionManagement(proxyTargetClass = true)` bật annotation-driven transaction management với class-based proxy phù hợp cho các service không khai báo interface.
- Bean `transactionManager` sử dụng cùng `DataSource` với `JdbcTemplate`. Cả outer và inner thực hiện câu SQL dưới sự quản lý của **một transaction manager**.
- `CommandLineRunner` được Spring tạo và inject các service đã được proxy. Runner không có `@Transactional`, nên mỗi lần gọi outer là một transaction mới, và khi gọi `inner.write(7)` trực tiếp thì inner tự mở transaction mới.
- Các phép `count` chạy **sau khi** từng lần gọi service đã kết thúc qua proxy, cho thấy trạng thái đã commit hoặc rollback.

Để tránh suy luận sai, không đặt `@Transactional` lên phương thức `demo` trong bài này. Nếu runner có transaction bao ngoài, trạng thái `isNewTransaction()` và thời điểm commit sẽ thay đổi.

### 5.5. Chạy và đối chiếu stdout

Yêu cầu JDK 17+ và Gradle 8.x tương thích. Trong thư mục `required-join-demo`, chạy:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper tương thích, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Vì code phụ thuộc Spring/H2, không biên dịch bằng `javac` với JDK classpath thuần.

Bỏ qua log của Spring Boot/Gradle; các dòng do chương trình in ra theo thứ tự sẽ là:

```text
outer newTx=true
inner newTx=false
successRows=2
outer newTx=true
innerFail newTx=false
outer caught=inner boom
outer reached return
caughtOutcome=UnexpectedRollbackException
caughtRows=0
outer newTx=true
inner newTx=false
outerError=outer boom
outerFailureRows=0
inner newTx=true
standaloneRows=1
```

**Diễn giải các trường hợp:**

| Trường hợp | Scope outer | Scope inner | Commit/rollback vật lý | Kết quả query |
| --- | --- | --- | --- | --- |
| `outer.success()` | Tạo T1 | Tham gia T1 | Commit T1 sau outer return | Hai record id 1, 2 tồn tại |
| `outer.catchesInner()` | Tạo T2 | Tham gia T2, ném runtime | Inner đánh dấu T2 rollback-only; outer cố commit → rollback | Cả id 3, 4 đều vắng mặt |
| `outer.failsOuter()` | Tạo T3, ném runtime | Tham gia T3, return bình thường | Outer rollback T3 | Cả id 5, 6 đều vắng mặt |
| `inner.write(7)` độc lập | Không có | Tạo T4 | Commit T4 khi inner return | Id 7 tồn tại |

### 5.6. Ca lỗi đặc biệt: outer bắt exception nhưng vẫn bị rollback

Trong `catchesInner()`, outer đã xử lý `IllegalStateException` do inner ném:

```text
Outer mở T2, INSERT id=3
   |
Inner tham gia T2, INSERT id=4
   |
Inner ném IllegalStateException
   |
Inner transaction advice xét rollback rule
   |
T2 bị đánh dấu GLOBAL rollback-only
   |
Outer catch IllegalStateException, return bình thường
   |
Outer interceptor cố commit T2
   |
T2 rollback → UnexpectedRollbackException tới runner
```

**Tại sao Spring cố ý ném `UnexpectedRollbackException`?** Bởi caller không nên nhận một kết quả thành công từ outer method khi transaction vật lý cuối cùng **đã rollback**. Đây là một cơ chế tránh “commit giả” dù outer code đã return bình thường. Exception có thể xuất hiện **tại boundary outer**, không phải trong `catch` của outer.

Ở đây `rollback-only` là cờ trạng thái transaction, không phải một INSERT/UPDATE bị undo sớm. Inner scope **không** rollback phần id 4 như một transaction độc lập rồi cho outer id 3 commit; cả T2 bị rollback chung.

Mặc định thông thường của `AbstractPlatformTransactionManager` là khi một scope tham gia transaction bị lỗi và yêu cầu rollback, nó đánh dấu transaction vật lý rollback-only. Trạng thái cuối vẫn phụ thuộc rollback rules, transaction manager, propagation và việc lỗi có đi qua advice hay không.

### 5.7. Vì sao inner thành công vẫn có thể mất dữ liệu?

Trong `outer.failsOuter()`, inner return bình thường, nhưng outer tiếp tục rồi ném `IllegalStateException`. Inner chưa commit riêng: nó chỉ hoàn tất logical scope. Khi outer rollback T3, **cả id 5 lẫn id 6 biến mất**. Điều này bảo toàn ý nghĩa “một đơn vị công việc” ở cấp outer.

**Quan sát đáng giá nhất:** inner `REQUIRED` có thể thành công cục bộ, nhưng kết quả **chỉ bền vững khi transaction vật lý được commit ở scope sở hữu nó**.

### 5.8. Gọi inner độc lập

Ở lần gọi `inner.write(7)`, runner chưa có transaction và không có outer scope. `REQUIRED` bây giờ **tự tạo T4**, nên `inner newTx=true`. Khi lời gọi method kết thúc thành công qua proxy, Spring commit T4.

Không có gì “khác” ở annotation inner giữa lần id 2 và id 7; chỉ khác **bối cảnh transaction trước khi gọi**.

## 6. Transaction status: phân biệt local và global rollback-only

Khi Spring quản lý propagation, có thể có các cấp trạng thái:

- **Local rollback-only:** một logical scope yêu cầu rollback, ví dụ code gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` trong scope của nó.
- **Global rollback-only:** transaction vật lý chung đã được đánh dấu không thể commit, ví dụ do một scope tham gia bị exception và manager áp dụng rollback-on-participation-failure, hoặc tài nguyên báo transaction đã aborted.

Một outer scope có thể chưa đánh dấu local rollback-only nhưng transaction chung đã global rollback-only vì inner. Vì thế `outer.return` không đồng nghĩa `commit` sẽ thành công.

### 6.1. Catch lỗi ở đâu quyết định kết quả

So sánh hai mẫu:

**Mẫu A — Inner exception đi qua proxy rồi outer catch:**

```java
@Transactional
public void outer() {
    try {
        innerService.doWork(); // doWork() có @Transactional(REQUIRED)
    } catch (IllegalStateException ex) {
        // Inner interceptor đã xử lý lỗi, có thể mark rollback-only.
    }
}
```

Nếu `doWork` thực sự bị inner interceptor thấy RuntimeException, transaction vật lý chung thường đã rollback-only. Outer return vẫn có thể dẫn đến `UnexpectedRollbackException`.

**Mẫu B — Inner tự catch exception trước khi return:**

```java
@Transactional
public void doWork() {
    try {
        performStep();
    } catch (IllegalStateException ex) {
        // Không rethrow, không setRollbackOnly.
    }
}
```

Nếu không có lỗi transaction resource hoặc một scope khác đã đánh dấu rollback-only, advice của `doWork` thấy return bình thường, nên **không tự mark rollback-only vì exception đã bị nuốt**.

Hai ví dụ chỉ minh họa cơ chế; thiếu định nghĩa `innerService` và `performStep`. Không nên nuốt lỗi chỉ để ép commit. Hãy thiết kế thông điệp lỗi, rollback rule và business invariant rõ ràng.

### 6.2. Chủ động đánh dấu rollback-only

Trong imperative transaction, một method có thể gọi:

```java
TransactionAspectSupport.currentTransactionStatus()
    .setRollbackOnly();
```

Đây là lời gọi API Spring trong một transaction-advised invocation. Nếu scope đang tham gia T, khi scope kết thúc, rollback-only có thể lan lên transaction chung. Nó phù hợp khi muốn trả kết quả business từ method nhưng **không thể cho transaction commit**.

Tuy nhiên, thao tác này kết dính business code với transaction framework, và với multi-scope `REQUIRED` có thể làm outer bị `UnexpectedRollbackException` dù outer return bình thường. Nếu không cần giữ một response kiểu result, ném exception domain đúng loại và xử lý ở bên ngoài boundary có thể rõ hơn.

### 6.3. Checked exception không đương nhiên mark rollback-only

Theo rule mặc định của Spring declarative transaction, `RuntimeException` và `Error` dẫn đến rollback; checked `Exception` như `IOException` thông thường **không**.

Nếu inner `REQUIRED` ném `IOException` mà không có `rollbackFor`, interceptor có thể **không đánh dấu rollback-only** cho T. Outer catch checked exception rồi tiếp tục, T có thể commit nếu không có vấn đề khác. Nếu ý nghĩa nghiệp vụ là phải rollback cả đơn hàng, hãy cấu hình `@Transactional(rollbackFor = IOException.class)` trên transaction boundary thích hợp, hoặc dùng exception runtime/domain với rollback policy nhất quán.

Không nên suy đoán “mọi exception tại inner service luôn rollback cả transaction”; cần biết **exception class thực tế**, **rule**, và **nó có thoát qua advice hay không**.

## 7. Đặc tính của transaction bên ngoài được giữ như thế nào?

Một ngộ nhận là inner `@Transactional(REQUIRED)` có thể thay isolation, read-only hoặc timeout của transaction vật lý đã mở. Trong cấu hình mặc định, khi inner tham gia T, các đặc tính vật lý của T **chủ yếu được quyết định lúc T bắt đầu**.

| Đặc tính khai báo ở inner REQUIRED | Khi inner tự tạo transaction mới | Khi inner tham gia T đã có |
| --- | --- | --- |
| `propagation = REQUIRED` | Tạo T | Tham gia T |
| `isolation = READ_COMMITTED` | Manager có thể áp dụng mức isolation | Không tự đổi isolation của T; mặc định khai báo inner được bỏ qua ở cấp physical |
| `readOnly = true` | Có thể áp dụng read-only hint/enforcement tùy manager/DB | Không tự biến T read-write thành read-only |
| `timeout = 5` | Có thể thiết lập timeout cho transaction mới | Không tự thay deadline của T đã mở |
| `rollbackFor = ...` | Quyết định khi lỗi thoát qua inner advice | Vẫn được xét, có thể đánh dấu T chung rollback-only |
| `noRollbackFor = ...` | Có thể cho phép commit dù throwable phù hợp | Không tự xóa rollback-only do scope khác đã đặt |

Ví dụ:

```java
@Transactional(readOnly = false)
public void updateAndReport() {
    updateData();
    reportService.readReport(); // @Transactional(readOnly = true)
}
```

Với `REQUIRED`, report service thường **tham gia transaction read-write đang có**. Read-only annotation ở inner không tự “hạ cấp” transaction vật lý. Ngược lại, một inner writer cố tham gia outer read-only transaction không được hiểu là sẽ được nâng cấp thành read-write; tùy driver/DB có thể bị từ chối ghi.

### 7.1. validateExistingTransactions

Một số transaction manager của Spring (kế thừa `AbstractPlatformTransactionManager`) có cấu hình `validateExistingTransaction(s)`. Khi đặt `validateExistingTransaction=true`, manager có thể **từ chối** những khai báo isolation không phù hợp khi một scope mới tham gia transaction có sẵn; trong chế độ kiểm tra nghiêm, một inner read-write cố tham gia outer read-only cũng có thể bị từ chối.

Ví dụ Java configuration minh họa:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

Mã trên là mảnh cấu hình, cần import và một `DataSource` hợp lệ; không đưa thêm bean này vào project demo nếu đã có bean cùng tên. **Chỉ dùng cấu hình nghiêm khi ứng dụng hiểu rõ những service nào tham gia transaction ngoài**; nó có thể làm lộ ra lỗi thiết kế read-only/isolation vốn đang bị bỏ qua ngầm.

### 7.2. Đừng lấy readOnly làm ràng buộc bảo mật

`@Transactional(readOnly = true)` không nhất thiết khiến mọi database từ chối INSERT. Tác dụng phụ thuộc transaction manager, JDBC driver, ORM và DB; có thể chỉ tối ưu flush hoặc cung cấp hint. Hãy dùng quyền DB/constraint và thiết kế service để bảo vệ dữ liệu.

## 8. REQUIRED so với REQUIRES_NEW và NESTED

Đặt đúng propagation là yêu cầu của **business invariant**, không chỉ cách chữa lỗi khi thấy rollback-only.

| Propagation | Khi outer đã có T | Connection/physical transaction | Inner thành công, outer về sau rollback |
| --- | --- | --- | --- |
| `REQUIRED` | Tham gia T | Một physical transaction chung | Phần inner cũng rollback |
| `REQUIRES_NEW` | Suspend T và mở T2 độc lập (khi manager hỗ trợ) | T2 riêng, thường cần connection khác | T2 đã commit thường vẫn giữ kết quả |
| `NESTED` | Tham gia transaction vật lý T, tạo savepoint nếu được hỗ trợ | Một transaction vật lý và savepoint | Outer rollback T vẫn hủy mọi thay đổi, kể cả phần inner đã release savepoint |

### 8.1. Vì sao không dùng REQUIRES_NEW để “tránh UnexpectedRollbackException”?

Nếu inventory reserve bằng `REQUIRES_NEW`, nó có thể commit tồn kho trong transaction riêng, dù đặt hàng outer rollback. Điều này **không giữ nguyên** điều kiện “đơn và tồn kho cùng thành công”; nó thay đổi business semantics. `REQUIRES_NEW` đôi khi thích hợp cho audit log phải giữ độc lập hoặc thông tin hệ thống, nhưng vẫn cần hiểu partial success, connection pool và deadlock risk.

Ngoài ra, một outer transaction giữ connection đang hoạt động và inner `REQUIRES_NEW` cần thêm connection có thể làm cạn connection pool khi nhiều request đồng thời. Không bật chỉ để “thấy kết quả ổn”.

### 8.2. NESTED khác REQUIRED như thế nào?

Với JDBC transaction manager hỗ trợ savepoint, `NESTED` có thể tạo điểm đánh dấu để rollback một phần thay đổi inner đến savepoint mà không buộc rollback toàn transaction ngoài trong một số trường hợp xử lý lỗi phù hợp. Nhưng **vẫn chỉ có một transaction vật lý**, nên outer rollback cuối cùng xóa toàn bộ. `NESTED` không được hỗ trợ giống nhau trên mọi manager hoặc driver; với JPA phải đặc biệt kiểm tra khả năng savepoint/JDBC.

**Tóm lại:** `REQUIRED` = tham gia cùng T; `REQUIRES_NEW` = T2 độc lập; `NESTED` = savepoint trong T nếu được hỗ trợ. Chọn dựa trên việc inner có cần commit riêng hay không và mức độ nhất quán nghiệp vụ.

## 9. Trường hợp inner method không đi qua proxy

Một lời gọi `this.method()` trong cùng Spring bean **không** đi qua proxy của method đó ở chế độ Spring AOP proxy mặc định:

```java
@Service
class BillingService {
    @Transactional
    public void createInvoice() {
        this.reserve(); // Không kích hoạt advice riêng của reserve().
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // SQL ...
    }
}
```

Mã này chỉ minh họa. Nếu `createInvoice()` đã được gọi từ ngoài qua proxy, nó có thể mở T, và code bên trong `reserve()` vẫn thực hiện SQL trong T dù không có inner advice. Nhưng:

- `reserve()` không tạo **logical transaction scope riêng** qua proxy.
- Các thuộc tính riêng như `rollbackFor`/`REQUIRES_NEW` trên `reserve()` không được áp dụng bởi lời gọi nội bộ.
- Nếu `createInvoice()` không có transaction và chỉ `reserve()` có annotation, self-invocation có thể khiến `reserve()` chạy **không có transaction Spring**.

Vì thế, khi muốn quan sát hai logical scope `REQUIRED` như demo, hãy gọi **bean khác được inject**. Sử dụng class public method không final và cấu hình proxy phù hợp. Không dùng self-invocation như một ví dụ chứng minh có inner transaction advice.

## 10. Thread, tài nguyên và manager: khi nào không thể tự động “tham gia”?

### 10.1. Thread-bound imperative transaction

Một Spring imperative transaction thông thường được gắn vào thread qua `TransactionSynchronizationManager`. Chuyển sang `@Async` hoặc tự tạo thread khác không tự mang theo transaction context.

Ví dụ minh họa:

```java
@Transactional
public void process() {
    repository.save();
    executor.execute(() -> otherService.saveMore());
}
```

Đây là pseudocode Java thiếu biến/implementation. `saveMore` chạy trong thread khác, thường không tự tham gia transaction vật lý của `process`, dù method ấy cũng là `REQUIRED`. Nó có thể tự mở transaction mới nếu được proxy intercept ở thread mới. Ngoài ra, khi task bất đồng bộ chạy thì outer transaction có thể chưa commit hoặc đã rollback.

### 10.2. Multiple DataSource

Nếu outer và inner sử dụng hai `DataSource`/hai transaction manager khác nhau, một annotation `REQUIRED` không tự biến thao tác trên hai DB thành một transaction XA. Cần thiết kế manager, distributed transaction hoặc workflow giao dịch cuối phù hợp. Với hai local transaction độc lập, kết quả có thể partial commit. Kiểm tra từng repository đang dùng connection nào.

### 10.3. Reactive transaction

Với Spring reactive và `ReactiveTransactionManager`, transaction context được truyền qua Reactor context thay vì thread-local kiểu imperative, và method phải tham gia đúng reactive pipeline. Quy tắc `REQUIRED` về việc tham gia transaction có sẵn vẫn có ý nghĩa, nhưng cách triển khai và kiểm chứng khác demo JDBC. Không dùng `TransactionAspectSupport.currentTransactionStatus()` như bằng chứng phổ quát cho reactive transaction.

## 11. Exceptions, commit và “đã lưu” cần được xác minh đúng thời điểm

### 11.1. Sau khi inner return, dữ liệu chưa chắc đã bền vững

Nếu inner `REQUIRED` đã gửi UPDATE thành công, kết quả vẫn có thể là dữ liệu **chưa commit**. Một query trong cùng T có thể đọc thấy chính thay đổi ấy (*read-your-writes*) nhưng nó không chứng minh dữ liệu đã commit. Khi outer rollback, thay đổi biến mất.

Do đó, test chỉ assert giá trị ngay bên trong outer transaction rất dễ cho false positive. Cần để outer scope kết thúc rồi đọc lại bằng transaction/kết nối độc lập phù hợp.

### 11.2. Một exception tại commit không luôn đồng nghĩa rollback

`UnexpectedRollbackException` trong kịch bản inner mark rollback-only có ý nghĩa rõ: outer cố commit nhưng transaction đã bị đánh dấu rollback; manager rollback và báo cho caller. Nó không nên bị đồng nhất với **mọi** exception ngay lúc commit.

Nếu connection mất trước khi caller nhận xác nhận từ DB, kết quả commit có thể không rõ. Cần operation ID, idempotency và đối soát. `REQUIRED` không tự giải quyết sự không chắc chắn ở boundary DB/network.

### 11.3. Flush và constraint xuất hiện muộn

Với JPA/Hibernate, nhiều INSERT/UPDATE có thể được trì hoãn đến `flush` hoặc commit. Inner method return bình thường không bảo đảm mọi constraint đã được DB chấp nhận, đặc biệt khi outer transaction chưa kết thúc. Với JDBC, SQL thường được gửi sớm hơn, nhưng commit vẫn là sự kiện cuối để thay đổi bền vững. Kiểm thử phải xác định dùng JDBC hay JPA và tránh giả định tất cả thao tác ghi xảy ra cùng một thời điểm.

## 12. Kiểm thử REQUIRED và các bẫy thường gặp

### 12.1. Bộ test nên có

- **Không có outer transaction:** gọi inner `REQUIRED` độc lập, xác nhận nó tạo và commit transaction của mình.
- **Outer + inner cùng thành công:** xác nhận inner `isNewTransaction=false`, cả hai record cùng được commit.
- **Inner ném RuntimeException, outer bắt:** xác nhận T global rollback-only, outer trả bình thường ở tầng Java nhưng proxy báo `UnexpectedRollbackException`, các thay đổi cả hai scope không còn.
- **Outer ném RuntimeException sau inner thành công:** xác nhận cả hai thay đổi rollback.
- **Inner ném checked exception:** xác định đã khai báo `rollbackFor` hay chưa và kiểm thử trạng thái cuối.
- **Outer read-only/inner read-write hoặc isolation khác:** xác định manager có bỏ qua sự khác biệt hay bật `validateExistingTransaction`; test đúng resource.
- **Self-invocation:** bảo đảm không nhầm việc SQL đang nằm trong outer T với việc inner annotation đã được intercept riêng.
- **Thread mới/tài nguyên khác:** xác định chúng không tự gia nhập transaction imperative T.

### 12.2. @Transactional trên test có thể che vấn đề

Trong Spring TestContext, test method có `@Transactional` có thể tự tạo transaction và rollback sau test. Nếu test gọi inner `REQUIRED`, inner sẽ **tham gia transaction của test** thay vì tự mở; kết quả khác với thực tế khi controller không có transaction. Kiểm tra `isNewTransaction` và DB state sau test có thể sai kỳ vọng.

Để chứng minh commit/rollback khi transaction outer thật kết thúc, dùng integration test không tự bọc toàn bộ trong test transaction hoặc sử dụng `TestTransaction` để điều khiển scope hợp lý. Đừng chỉ dựa vào việc test cuối cùng không còn record để kết luận service đã rollback đúng.

### 12.3. Bật log transaction khi cần

Có thể tạm bật:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Log có thể cho thấy thời điểm transaction manager tạo transaction mới, tham gia transaction hiện có, đánh dấu rollback-only, rollback/commit. Tuy nhiên, “tham gia transaction” trong log phải được đối chiếu với connection/resource và kết quả DB; không dùng log thay thế kiểm thử dữ liệu sau khi outer scope hoàn tất.

## 13. Các ngộ nhận thường gặp về REQUIRED

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Mỗi `@Transactional(REQUIRED)` là một transaction DB khác nhau.” | Có thể nhiều logical scope dùng chung một physical transaction. |
| “Inner return nghĩa là inner đã commit.” | Nếu tham gia T, inner không commit riêng; outer có thể rollback tất cả. |
| “Outer catch RuntimeException từ inner thì T vẫn commit được.” | Inner advice có thể đánh dấu T rollback-only, khiến outer gặp `UnexpectedRollbackException`. |
| “Outer rollback không ảnh hưởng inner vì inner đã hoàn tất.” | Với cùng T, outer rollback hủy cả thay đổi inner. |
| “Đặt `readOnly = true` ở inner sẽ biến transaction outer thành read-only.” | Thuộc tính physical của T được quyết định khi T bắt đầu; inner không tự thay đổi T. |
| “Đặt timeout/isolation riêng ở inner chắc chắn ghi đè outer.” | Inner tham gia T thường không làm lại cấu hình physical, có thể bị validate từ chối nếu không tương thích. |
| “REQUIRED luôn mở connection mới.” | Khi T đã có, inner thường dùng cùng resource/connection được quản lý. |
| “REQUIRES_NEW là cách sửa hoàn hảo cho lỗi rollback-only.” | Nó thay đổi atomicity, có thể khiến inner commit dù outer rollback. |
| “NESTED và REQUIRED như nhau.” | NESTED có thể tạo savepoint; REQUIRED không tạo savepoint độc lập. |
| “Self-invocation có đầy đủ inner transaction advice.” | Với proxy mode mặc định, `this.method()` bỏ qua interception của inner. |
| “Một manager REQUIRED bao được hai DB và email.” | Chỉ tài nguyên transaction manager thực sự quản lý mới tham gia. |

## 14. Checklist thiết kế trước khi dùng REQUIRED

Trước khi đặt `@Transactional(propagation = REQUIRED)`:

1. Xác định **business unit of work** có cần các bước cùng commit hoặc cùng rollback không?
2. Method outer nào **sở hữu boundary** thực và khi nào transaction vật lý kết thúc?
3. Inner service có được gọi qua Spring proxy và dùng đúng manager/DataSource không?
4. Nếu inner lỗi, outer có được phép xử lý lỗi để tiếp tục, hay bắt buộc hủy cả unit of work?
5. Exception type và rollback policy có phản ánh kết quả nghiệp vụ không?
6. Có bất kỳ bước nào dùng `REQUIRES_NEW`, connection riêng, thread khác hoặc hệ thống ngoài không?
7. Nếu inner khai báo isolation/read-only/timeout riêng, có thật cần transaction vật lý riêng hay nên kiểm tra cấu hình outer?
8. Test đã đọc trạng thái DB **sau outer commit/rollback** và kiểm tra `UnexpectedRollbackException` chưa?

Với một use case yêu cầu atomicity giữa nhiều bước trên **cùng database**, mặc định `REQUIRED` thường rất phù hợp: outer tạo T; các service bên trong tham gia T; kết quả commit/rollback là của **cả unit of work**. Nếu cần kết quả độc lập, hãy thay đổi thiết kế giao dịch có chủ đích, thay vì nghĩ rằng mỗi annotation tương ứng một COMMIT.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Outer `@Transactional(REQUIRED)` gọi inner `@Transactional(REQUIRED)` qua proxy. Có bao nhiêu transaction vật lý?

**Trả lời:** Thường chỉ **một**, nếu cả hai dùng cùng transaction manager/tài nguyên và outer đã mở T. Có hai logical scope nhưng inner tham gia T.

**Câu 2.** Inner `REQUIRED` return bình thường, outer ném `IllegalStateException` sau đó. Dữ liệu inner có commit không?

**Trả lời:** Không, nếu inner tham gia cùng T và outer rollback T thành công. Inner chưa commit riêng.

**Câu 3.** Inner `REQUIRED` ném `IllegalStateException`, outer catch rồi return bình thường. Vì sao caller có thể nhận `UnexpectedRollbackException`?

**Trả lời:** Inner interceptor đã đánh dấu physical T rollback-only. Khi outer cố commit, Spring rollback T và ném exception để caller không nhầm transaction đã commit.

**Câu 4.** Cùng một inner `REQUIRED` được gọi không có transaction bên ngoài. Nó có làm gì khác không?

**Trả lời:** Có. Nó có thể tự tạo physical transaction mới và sở hữu việc commit/rollback khi method kết thúc.

**Câu 5.** Inner khai báo `@Transactional(readOnly = true)` và tham gia outer read-write T. T có tự chuyển sang read-only không?

**Trả lời:** Không. Physical characteristics của T được thiết lập khi outer mở transaction; inner `REQUIRED` không tự thay đổi chúng.

**Câu 6.** Có nên sửa `UnexpectedRollbackException` bằng cách đổi inner sang `REQUIRES_NEW`?

**Trả lời:** Chỉ nếu nghiệp vụ thực sự muốn inner commit/rollback độc lập. Nếu không, điều đó phá atomicity và có thể gây partial state.

**Câu 7.** Vì sao self-invocation không phải ví dụ tốt để chứng minh có hai transaction scope?

**Trả lời:** Vì `this.inner()` không đi qua Spring proxy riêng ở proxy mode; annotation của inner không được intercept, dù code có thể chạy bên trong outer transaction đã mở.

**Câu 8.** Nếu inner checked exception không được cấu hình rollback, outer catch rồi return thì T có chắc rollback không?

**Trả lời:** Không. Checked exception thường không đánh dấu rollback-only theo default rule. T có thể commit nếu không có lỗi hoặc rollback-only từ nguồn khác.

## Tài liệu tham khảo

- Spring Framework — Transaction Propagation, `PROPAGATION_REQUIRED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Javadoc — `AbstractPlatformTransactionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html

**Tóm tắt:** `REQUIRED` **không tạo transaction vật lý mới khi đã có transaction thích hợp**. Nó mở một logical scope tham gia T, dùng chung commit/rollback với outer. Lỗi của inner có thể đánh dấu T rollback-only; outer bắt exception chưa đủ để “cứu” T. Hãy xác minh scope, transaction manager, resource và trạng thái DB sau outer boundary để dùng `REQUIRED` đúng cách.