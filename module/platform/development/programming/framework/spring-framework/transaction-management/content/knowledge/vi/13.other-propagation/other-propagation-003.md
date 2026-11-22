# NOT_SUPPORTED và thực thi khi giao dịch ngoài bị tạm ngưng trong Spring

## 1. Bài toán: muốn tạm thời chạy *ngoài* transaction hiện hành

Một ứng dụng Spring có phương thức xử lý nghiệp vụ đang chạy trong transaction T1. Trong lúc xử lý, nó gọi một chức năng khác: truy vấn thông tin chẩn đoán, thực hiện một thao tác không cần giao dịch, hoặc ghi nhận một sự kiện độc lập bằng JDBC. Nếu muốn chức năng được gọi **không tham gia transaction T1**, ta có thể dùng:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void doNonTransactionalWork() {
    // Chạy mà không tham gia physical transaction hiện hành.
}
```

Đây là **mã minh họa chữ ký**, chưa phải một chương trình Java độc lập.

Nếu lời gọi đi qua **Spring transaction proxy**, chính sách `Propagation.NOT_SUPPORTED` có ý nghĩa:

> **Không hỗ trợ chạy trong transaction hiện hành. Nếu đang có một transaction phù hợp, Spring tạm ngưng nó, thực thi phương thức trong phạm vi không có physical transaction đó, rồi nối lại transaction ngoài sau khi phương thức kết thúc.**

Điểm khác biệt quan trọng là `NOT_SUPPORTED` **không tạo một transaction mới**. Nó khác hẳn với `REQUIRES_NEW`, vốn yêu cầu mở transaction độc lập.

Ví dụ một phương thức ngoài ghi dữ liệu nghiệp vụ trong T1, gọi phương thức trong dùng `NOT_SUPPORTED` để INSERT vào bảng khác bằng JDBC và sau đó ném lỗi:

```text
CheckoutService.checkout()             @Transactional(REQUIRED)
    |
    | T1: INSERT business_record(id=1), chưa commit
    |
    +--> IndependentService.record()    @Transactional(NOT_SUPPORTED)
    |        |
    |        | Spring suspend T1
    |        | Không có actual transaction của T1 ở đây
    |        | JdbcTemplate INSERT independent_record(id=100)
    |        | Connection mới đang auto-commit: INSERT được commit riêng
    |        | Spring resume T1
    |        v
    |
    | throw IllegalStateException
    v
ROLLBACK T1

Kết quả sau lời gọi:
  business_record       = 0 hàng
  independent_record    = 1 hàng
```

Đây là **một kịch bản minh họa với JDBC auto-commit**. Nó **không** có nghĩa `NOT_SUPPORTED` tự commit tất cả những gì method làm: bởi vì không có transaction Spring bao quanh, từng thao tác DB có thể có commit riêng, hoặc thất bại, tùy công nghệ truy cập và cấu hình connection. Mục 6 cung cấp chương trình Java 17+ có thể chạy để chứng minh kết quả.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Giải thích đúng ý nghĩa của `NOT_SUPPORTED` khi có và khi không có transaction ngoài.
2. Mô tả trình tự **suspend → chạy non-transactionally → resume**.
3. Phân biệt `NOT_SUPPORTED` với `SUPPORTS`, `NEVER`, `REQUIRED` và `REQUIRES_NEW`.
4. Hiểu vì sao một INSERT JDBC trong khối `NOT_SUPPORTED` có thể **tồn tại dù transaction ngoài rollback**.
5. Hiểu vì sao không thể gọi `NOT_SUPPORTED` là “transaction độc lập”, và vì sao không nên dùng nó để bảo vệ nhiều bước ghi phải nguyên tử.
6. Tránh lỗi self-invocation, truy cập dữ liệu chưa commit của outer, tranh chấp connection/lock, sai transaction manager và cách bắt ngoại lệ.
7. Kiểm thử bằng **trạng thái database thực tế sau lời gọi**, không chỉ dựa vào annotation.

## 2. Định nghĩa chính xác của Propagation.NOT_SUPPORTED

Trong Spring, `org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED` có ngữ nghĩa **execute non-transactionally; suspend the current transaction if one exists**.

Hai tình huống phải phân biệt:

| Trạng thái khi Spring chặn lời gọi | Hành vi của `NOT_SUPPORTED` | Sau khi method hoàn tất |
| --- | --- | --- |
| Có transaction hiện hành T1 do manager tương ứng quản lý | Suspend ngữ cảnh T1; chạy phần thân **không tham gia T1** | Resume T1 để caller tiếp tục |
| Không có transaction hiện hành phù hợp | Chạy phần thân **không tạo physical transaction mới** | Trả về caller, không có T1 nào cần resume |

Cú pháp đầy đủ:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void readOrPerformIndependentStep() {
    // ...
}
```

Đây là snippet ở cấp method, chưa chứa lớp. Khác với `@Transactional` mặc định, ở đây bạn **phải chỉ rõ NOT_SUPPORTED** vì propagation mặc định là `REQUIRED`.

Một hiểu nhầm phổ biến là: “Có annotation `@Transactional` nghĩa là chắc chắn method chạy trong transaction.” Điều đó **sai** khi propagation là `NOT_SUPPORTED`. Annotation ở đây là **chỉ dẫn không dùng transaction hiện có**.

### Điều kiện để cơ chế hoạt động

- Bean được Spring quản lý và lời gọi thực sự đi qua proxy/advice có hỗ trợ transaction.
- Có transaction manager phù hợp và Spring xác định được chính sách `NOT_SUPPORTED`.
- Nếu cần suspend transaction ngoài, transaction manager phải hỗ trợ cơ chế đó. Không phải mọi transaction manager/kiểu hạ tầng đều suspend được trong mọi cấu hình.
- Nếu dùng JDBC/JPA imperative, phải xét **ngữ cảnh luồng hiện hành và tài nguyên thực tế**. Một transaction trên thread khác không tự là transaction hiện hành của method này.
- Nếu có nhiều managers/datasources, `NOT_SUPPORTED` không tự suspend mọi transaction thuộc mọi manager. Phải chỉ rõ **manager và resource** nào đang được điều phối.

## 3. Trình tự “suspend – thực thi – resume”

Giả sử `OuterService` và `IndependentService` là hai Spring beans, cả hai dùng cùng transaction manager JDBC, caller ban đầu không mở transaction:

1. Caller gọi `outerService.execute()` qua Spring proxy.
2. `OuterService.execute()` dùng `@Transactional(REQUIRED)`. Vì chưa có transaction, manager tạo **T1**.
3. Outer chạy SQL bằng `JdbcTemplate`; SQL tham gia T1 và chưa commit.
4. Outer gọi `independentService.doWork()` **qua Spring proxy thứ hai**.
5. Interceptor đọc chính sách `NOT_SUPPORTED`. Manager **tạm ngưng** transaction T1 và các tài nguyên/ngữ cảnh liên quan.
6. `doWork()` thực thi **không có physical transaction T1 đang active**.
7. Khi inner kết thúc hoặc ném lỗi, Spring dọn ngữ cảnh non-transactional và **resume T1**.
8. Outer tiếp tục trong T1. Nếu outer commit thì các thay đổi trong T1 commit; nếu outer rollback thì các thay đổi trong T1 rollback.
9. Các side effects đã diễn ra **ngoài T1** không được outer rollback tự động hoàn tác.

### Sơ đồ thứ tự

```mermaid
sequenceDiagram
    participant C as Caller
    participant OP as Outer proxy
    participant M as TransactionManager
    participant O as OuterService
    participant IP as Inner proxy
    participant I as IndependentService
    participant DB as Database

    C->>OP: checkout()
    OP->>M: REQUIRED; chưa có transaction
    M->>DB: Bắt đầu T1
    OP->>O: Thực thi outer
    O->>DB: INSERT business_record trong T1
    O->>IP: record() từ Spring bean khác
    IP->>M: NOT_SUPPORTED
    M->>M: Suspend T1 / unbind resource context
    IP->>I: Thực thi inner không có T1
    I->>DB: JDBC INSERT với auto-commit (ví dụ)
    DB-->>I: Statement được commit riêng
    I-->>IP: Return
    IP->>M: Kết thúc scope non-transactional
    M->>M: Resume T1
    IP-->>O: Return
    O--xOP: IllegalStateException
    OP->>M: Rollback T1
    M->>DB: ROLLBACK thay đổi thuộc T1
    OP--xC: Exception
```

Sơ đồ mô tả **JDBC với auto-commit trong khối không transaction**. Với JPA, R2DBC, driver hoặc cấu hình ngoài transaction khác, không nên tự suy diễn hành vi SQL chi tiết giống hệt.

### “Suspend” không phải “rollback”, “commit” hay “đóng transaction”

Khi Spring tạm ngưng T1:

- T1 **chưa commit**.
- T1 **chưa rollback**.
- Các thay đổi chưa commit của T1 thường vẫn chưa nhìn thấy từ kết nối khác ở mức isolation thông thường.
- Connection hoặc resource mà T1 đang giữ **có thể vẫn được giữ lại** để resume, và lock do T1 lấy thường vẫn còn tới khi T1 kết thúc.
- T1 tiếp tục sau khi inner kết thúc với những dữ liệu/khóa của chính nó, tùy tính hợp lệ của transaction.

Không hiểu “tạm ngưng” là “giải phóng hết connection và lock để làm việc khác”. Những tài nguyên đang bị giữ là lý do không nên lạm dụng NOT_SUPPORTED cho các tác vụ dài khi outer transaction vẫn mở.

## 4. Non-transactional không giống một transaction mới

Đây là điểm phân biệt trọng tâm của đề bài.

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void methodA() {
    // Không tham gia transaction ngoài,
    // cũng không tạo physical transaction mới.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void methodB() {
    // Yêu cầu mở một physical transaction mới, riêng biệt.
}
```

Hai method trên **không tương đương**, dù trong một demo đơn giản, một hàng ghi ra có thể còn lại sau outer rollback ở cả hai trường hợp.

| Đặc tính | `NOT_SUPPORTED` | `REQUIRES_NEW` |
| --- | --- | --- |
| Khi caller đang trong T1 | Suspend T1 | Suspend T1 |
| Phương thức trong có actual physical transaction mới? | **Không** | **Có**, khi tạo thành công |
| Hai câu SQL ghi bằng JDBC auto-commit | Có thể commit **từng câu** riêng biệt | Thường cùng thuộc T2, có thể commit/rollback như một đơn vị |
| Inner throw RuntimeException | Không có physical T2 để rollback | T2 thường rollback theo rollback rules |
| Outer T1 rollback về sau | Không hoàn tác side effects đã commit ngoài T1 | Không hoàn tác thay đổi T2 **đã commit** |
| Phù hợp cho một chuỗi DB writes phải nguyên tử | **Không** | Có thể, nếu nghiệp vụ cần transaction độc lập |
| Tài nguyên bổ sung | JDBC outside transaction thường cần connection khác nếu T1 còn giữ connection | T2 thường cần connection mới |

**Ví dụ cảnh báo:** Trong `NOT_SUPPORTED`, một method thực hiện:

```java
jdbc.update("INSERT INTO first_table(id) VALUES (?)", 1L);
jdbc.update("INSERT INTO second_table(id) VALUES (?)", 2L);
```

Nếu không có transaction bao quanh và JDBC connection auto-commit, lệnh thứ nhất có thể **commit** trước khi lệnh thứ hai gặp lỗi. Không có rollback transaction Spring chung để hủy câu lệnh thứ nhất. Nếu hai thao tác phải cùng thành công/cùng thất bại, **đừng dùng NOT_SUPPORTED** để bảo vệ chúng.

### JDBC auto-commit và JPA khác nhau

Với `JdbcTemplate` và `DataSource` cấu hình auto-commit mặc định trong nhiều ứng dụng, một statement ở ngoài transaction thường được DB **commit ngay sau khi thực thi thành công**. Mỗi statement có thể hình thành một database transaction ngắn ở phía DB, nhưng **không phải physical transaction được Spring mở để bao toàn bộ method**.

Với JPA/Hibernate, các thao tác ghi như `EntityManager.persist/flush` ngoài transaction có thể không được phép hoặc ném lỗi `TransactionRequiredException`, tùy API và provider. Vì thế không được nói “NOT_SUPPORTED tự động commit từng persist()” như một quy tắc áp dụng cho mọi công nghệ.

Với việc gọi HTTP API, gửi email hoặc ghi file, đây vốn không phải tác động được JDBC transaction manager rollback. `NOT_SUPPORTED` không đem lại đảm bảo atomicity cho những tác động đó.

## 5. Quan sát “có transaction không?” cho đúng

Spring có API:

```java
TransactionSynchronizationManager.isActualTransactionActive()
```

Trong mô hình JDBC imperative của bài thực hành, ở ngoài T1 nó trả `false`, bên trong outer REQUIRED trả `true`, và ở method NOT_SUPPORTED sau khi T1 được suspend nó trả `false`.

Hình dung:

```text
Trước outer:            actualTransactionActive = false
Trong outer REQUIRED:   actualTransactionActive = true
Trong inner NOT_SUPPORTED:
                        actualTransactionActive = false
Sau inner, trong outer: actualTransactionActive = true
Sau outer kết thúc:     actualTransactionActive = false
```

**Không đồng nhất** với `TransactionSynchronizationManager.isSynchronizationActive()`. Spring có các cơ chế transaction synchronization, scope và tài nguyên gắn với thread; việc có synchronization context không phải phép chứng minh rằng **physical transaction thực** đang hoạt động. Dùng `isActualTransactionActive()` để quan sát mục tiêu của ví dụ, rồi kết hợp với kết quả SQL thực tế.

Ngoài ra, `TransactionAspectSupport.currentTransactionStatus()` không nên được hiểu là “chỉ có object status khi có physical transaction”. Trong hạ tầng transaction advice, một lời gọi `NOT_SUPPORTED` có thể có transaction status cho việc quản lý scope mà **không sở hữu actual physical transaction**. Không lấy sự hiện diện của status làm bằng chứng về commit/rollback vật lý.

## 6. Ví dụ Java 17+ chạy được: inner chạy ngoài transaction, outer rollback

Ví dụ dùng **Spring Boot, Spring JDBC, H2 in-memory và Java 17+**. Hai bean service và hai bảng dữ liệu khác nhau giúp chứng minh ngữ nghĩa NOT_SUPPORTED mà không bị khóa trên cùng một hàng làm sai lệch thí nghiệm.

Chương trình có **hai kịch bản**:

- **Kịch bản A:** outer INSERT business, inner NOT_SUPPORTED INSERT independent record và trả về; outer ném lỗi, rollback T1. Bảng business rỗng nhưng independent record vẫn tồn tại do auto-commit.
- **Kịch bản B:** outer INSERT business, inner NOT_SUPPORTED INSERT independent record rồi ném lỗi; outer **bắt lỗi bên trong method transactional** và kết thúc bình thường. Inner record đã được auto-commit; outer commit business record. Điều này chứng minh ngoại lệ từ inner **không tự làm T1 rollback nếu outer xử lý nó và T1 không bị đánh dấu rollback-only vì nguyên nhân khác**.

### 6.1. Chuẩn bị dự án

Tạo project Maven từ Spring Initializr:

- Java **17** hoặc mới hơn.
- Spring Boot tương thích với phiên bản Java đã chọn.
- Dependencies: **Spring JDBC** (`spring-boot-starter-jdbc`) và **H2 Database**.
- Package gốc: `com.example.notsupported`.

Giữ `pom.xml` do Initializr sinh ra; trong phần dependencies cần có:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn dependencies**, không phải toàn bộ `pom.xml`. Không cần Spring Web: ứng dụng chạy logic kiểm chứng qua `CommandLineRunner`.

Cấu trúc file:

```text
src/main/
  java/com/example/notsupported/
    NotSupportedApplication.java
    CheckoutService.java
    IndependentService.java
  resources/
    schema.sql
    application.properties
```

### 6.2. Tạo database schema

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE business_record (
    id BIGINT PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);

CREATE TABLE independent_record (
    id BIGINT PRIMARY KEY,
    message VARCHAR(100) NOT NULL
);
```

Hai bảng **không có foreign key** nối với nhau. Đây là quyết định **cho môi trường học**: outer có thể giữ transaction và row lock; inner ở connection khác không nên cần đọc hay khóa row chưa commit của outer.

Trong hệ thống thật, không được bỏ ràng buộc ngoại chỉ để phương thức NOT_SUPPORTED chạy. Nếu bản ghi inner thực sự phải tham chiếu một bản ghi outer **đã commit**, cần thiết kế lại thời điểm ghi.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:not_supported_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.auto-commit=true
```

Khi dùng Spring Boot với embedded H2, cấu hình khởi tạo SQL mặc định thường chạy `schema.sql` khi ứng dụng khởi động. `auto-commit=true` được ghi tường minh cho **các connection lấy từ pool bên ngoài transaction** để thí nghiệm minh bạch. Khi Spring mở T1, transaction manager có thể thay đổi auto-commit trên connection đó theo nhu cầu rồi khôi phục khi hoàn tất.

Pool tối đa 4 connection đủ cho **demo đơn luồng**, nơi outer vẫn giữ một connection và inner cần một connection khác. Đây không phải khuyến nghị dung lượng pool production.

### 6.3. Service trong: NOT_SUPPORTED và JDBC auto-commit

File `src/main/java/com/example/notsupported/IndependentService.java`:

```java
package com.example.notsupported;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class IndependentService {

    private final JdbcTemplate jdbc;

    public IndependentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void record(long id, boolean fail) {
        boolean active =
                TransactionSynchronizationManager
                        .isActualTransactionActive();

        System.out.println("inner: actualTransactionActive=" + active);

        jdbc.update("""
            INSERT INTO independent_record (id, message)
            VALUES (?, ?)
            """, id, "observed");

        if (fail) {
            throw new IllegalStateException("inner failed");
        }
    }
}
```

**Giải thích:**

1. `IndependentService` là một Spring bean độc lập; khi được `CheckoutService` inject và gọi, transaction advice của nó có thể áp dụng.
2. `@Transactional(propagation = NOT_SUPPORTED)` chỉ thị **không tham gia physical transaction hiện hành**.
3. Khi outer đang trong T1, Spring suspend T1; `isActualTransactionActive()` của inner in `false`.
4. `JdbcTemplate` lấy JDBC connection phù hợp. Trong cấu hình thí nghiệm với auto-commit, INSERT vào `independent_record` **được commit riêng** khi SQL thành công.
5. Nếu `fail=true`, method ném `IllegalStateException` **sau khi INSERT đã thành công**. Không có physical Spring transaction cho inner để rollback thao tác vừa auto-commit.
6. Lỗi có thể lan tới outer; outer tiếp tục, commit hay rollback tùy cách xử lý lỗi và trạng thái T1.

Lưu ý quan trọng: nếu bạn đổi từ `JdbcTemplate` sang một công nghệ truy cập yêu cầu transaction bắt buộc để ghi, thí nghiệm này cần thiết kế lại. `NOT_SUPPORTED` không ép công nghệ đó phải auto-commit.

### 6.4. Service ngoài: transaction T1 vẫn được khôi phục

File `src/main/java/com/example/notsupported/CheckoutService.java`:

```java
package com.example.notsupported;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class CheckoutService {

    private final JdbcTemplate jdbc;
    private final IndependentService independentService;

    public CheckoutService(
            JdbcTemplate jdbc,
            IndependentService independentService) {
        this.jdbc = jdbc;
        this.independentService = independentService;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void rollbackAfterIndependentWrite() {
        System.out.println(
            "outer: actualTransactionActive=" +
            TransactionSynchronizationManager
                .isActualTransactionActive());

        jdbc.update("""
            INSERT INTO business_record (id, description)
            VALUES (?, ?)
            """, 1L, "pending checkout");

        independentService.record(100L, false);

        System.out.println(
            "outer resumed: actualTransactionActive=" +
            TransactionSynchronizationManager
                .isActualTransactionActive());

        throw new IllegalStateException("outer failed");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void handleInnerFailure() {
        jdbc.update("""
            INSERT INTO business_record (id, description)
            VALUES (?, ?)
            """, 2L, "accepted checkout");

        try {
            independentService.record(101L, true);
        } catch (IllegalStateException ex) {
            System.out.println(
                "outer handled: " + ex.getMessage());
        }

        // Không ném lỗi tiếp: T1 có thể commit.
    }
}
```

Điểm đáng chú ý:

- Hai method outer đều có `REQUIRED`, được gọi từ một caller không có transaction, vì thế tạo physical transaction T1 cho **từng lần gọi riêng**.
- `independentService.record(...)` là lời gọi **qua bean khác**, không phải self-invocation. Đây là điều kiện để policy NOT_SUPPORTED được thực thi.
- Trong `rollbackAfterIndependentWrite()`, câu SQL business tham gia T1 và chưa commit; INSERT inner lại nằm **ngoài T1**, có auto-commit riêng. Sau đó T1 được resume rồi bị rollback vì lỗi outer.
- Trong `handleInnerFailure()`, outer **bắt ngoại lệ của inner**. Khối NOT_SUPPORTED không có physical transaction của nó để đánh dấu T1 rollback-only. Nếu T1 còn hợp lệ, việc outer trả về bình thường làm nó commit.

Không nên suy luận rằng outer **luôn** commit chỉ vì đã bắt exception. SQL trong T1 có thể gặp lỗi riêng hoặc T1 đã bị đánh dấu rollback-only. Tình huống ở đây được kiểm soát: chỉ có lỗi Java cố tình ném sau khi INSERT JDBC inner đã auto-commit.

### 6.5. Điểm vào và bằng chứng database

File `src/main/java/com/example/notsupported/NotSupportedApplication.java`:

```java
package com.example.notsupported;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableTransactionManagement
public class NotSupportedApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotSupportedApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            CheckoutService checkoutService,
            JdbcTemplate jdbc) {
        return args -> {
            System.out.println(
                "caller: actualTransactionActive=" +
                TransactionSynchronizationManager
                    .isActualTransactionActive());

            try {
                checkoutService.rollbackAfterIndependentWrite();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
            printCounts("after outer rollback", jdbc);

            checkoutService.handleInnerFailure();
            printCounts("after handled inner error", jdbc);

            System.out.println(
                "caller ended: actualTransactionActive=" +
                TransactionSynchronizationManager
                    .isActualTransactionActive());
        };
    }

    private static void printCounts(String title, JdbcTemplate jdbc) {
        Integer business = jdbc.queryForObject(
            "SELECT COUNT(*) FROM business_record",
            Integer.class);
        Integer independent = jdbc.queryForObject(
            "SELECT COUNT(*) FROM independent_record",
            Integer.class);

        System.out.printf(
            "%s: business=%d, independent=%d%n",
            title, business, independent);
    }
}
```

Chương trình sử dụng Java 17 text blocks và Spring Boot dependency injection. Trong `CommandLineRunner`, không có annotation transaction bao ngoài, vì vậy caller thực thi **ngoài T1**.

Với cấu hình demo, Spring Boot thường tự thiết lập transaction manager cho một JDBC datasource. `@EnableTransactionManagement` được ghi rõ để thể hiện bật cơ chế annotation-driven transaction. Việc truy cập vào từng method service diễn ra qua Spring bean proxy.

### 6.6. Chạy chương trình

Trong thư mục có `pom.xml`:

```bash
./mvnw spring-boot:run
```

Trong Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Ngoài log Maven và Spring Boot, các dòng do **chính chương trình in** sẽ là:

```text
caller: actualTransactionActive=false
outer: actualTransactionActive=true
inner: actualTransactionActive=false
outer resumed: actualTransactionActive=true
caller caught: outer failed
after outer rollback: business=0, independent=1
inner: actualTransactionActive=false
outer handled: inner failed
after handled inner error: business=1, independent=2
caller ended: actualTransactionActive=false
```

### 6.7. Phân tích từng kết quả

**Kịch bản A — outer rollback, inner non-transactional write còn lại**

1. `caller: ... false`: caller không có physical transaction.
2. `outer: ... true`: `REQUIRED` khởi tạo T1 trước khi phần thân outer chạy.
3. Outer INSERT `business_record(id=1)` trong T1; record **chưa commit**.
4. Gọi bean `IndependentService.record(100, false)`. Proxy thấy NOT_SUPPORTED và **suspend T1**.
5. `inner: ... false`: không có actual transaction T1 trong inner.
6. JDBC INSERT `independent_record(id=100)` trên connection auto-commit; statement được commit ngoài T1.
7. Inner trả về, transaction infrastructure **resume T1**.
8. `outer resumed: ... true`: outer lại thấy actual transaction.
9. Outer ném `IllegalStateException("outer failed")`, interceptor của outer **rollback T1**.
10. Caller bắt exception **sau khi proxy đã rollback T1**, rồi query database. Kết quả: `business=0` nhưng `independent=1`.

**Kịch bản B — inner lỗi, outer xử lý và commit**

1. Outer lần hai tự tạo một transaction mới T1' và INSERT `business_record(id=2)`.
2. Inner `record(101, true)` chạy ngoài T1', INSERT `independent_record(id=101)` với auto-commit rồi ném `IllegalStateException("inner failed")`.
3. Spring dọn ngữ cảnh inner, **resume T1'**, exception truyền ngược vào khối `catch` của outer.
4. Outer **bắt ngoại lệ**, không ném tiếp, không chủ động đánh dấu rollback-only nên trả về bình thường.
5. Interceptor ngoài **commit T1'**. Lúc này `business_record(id=2)` tồn tại; independent có thêm id=101.
6. Kết quả tổng: `business=1` và `independent=2`.

Điều quan trọng nhất không phải độ dài call stack mà là **câu SQL nào tham gia T1, câu SQL nào thực thi ngoài T1 và ai quyết định kết thúc T1**.

## 7. Vì sao JDBC ghi ngoài transaction có thể sống sót sau rollback?

Trong demo, phương thức inner dùng `JdbcTemplate` với Hikari/JDBC connection ở chế độ `autoCommit=true`. Khi một câu `INSERT` thành công:

- JDBC driver/database thực hiện commit cho statement phù hợp với auto-commit.
- Không có Spring physical transaction T2 nào bao toàn bộ inner method.
- Khi code inner sau đó ném exception, Spring không thể rollback các statement đã auto-commit chỉ vì method dùng NOT_SUPPORTED.
- Khi outer rollback T1, rollback chỉ áp dụng cho connection/transaction T1, **không áp dụng cho statement đã commit ở connection ngoài T1**.

Không nên diễn đạt rằng “NOT_SUPPORTED làm INSERT vào DB theo kiểu không có transaction ở cấp DB”. Database có thể thực thi từng statement trong những transaction rất ngắn, được auto-commit theo chính sách connection. Điều Spring bảo đảm ở đây là **không tham gia physical transaction do Spring đang quản lý cho method này**.

### Nếu method inner chạy nhiều câu SQL

Ví dụ:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void writeTwoRows() {
    jdbc.update("INSERT INTO independent_record (id, message) VALUES (?, ?)",
                201L, "first");
    jdbc.update("INSERT INTO independent_record (id, message) VALUES (?, ?)",
                201L, "duplicate key");
}
```

Đây là đoạn method minh họa, giả định bảng có khóa chính như schema ở trên.

- Statement đầu INSERT id=201 thành công và **có thể auto-commit ngay**.
- Statement thứ hai vi phạm primary key và ném lỗi.
- Không có Spring transaction mới bao cả hai statement để rollback statement đầu.
- Cơ sở dữ liệu có thể còn record id=201 dù method kết thúc bằng exception.

Với `@Transactional(REQUIRES_NEW)` trên cùng method và nguồn dữ liệu, hai INSERT có thể cùng tham gia T2; lỗi runtime khiến T2 rollback và không còn record id=201. Đó là một lý do quan trọng để **không dùng NOT_SUPPORTED thay REQUIRES_NEW** khi muốn sự nguyên tử của nhiều bước ghi độc lập.

## 8. Vì sao NOT_SUPPORTED khác SUPPORTS và NEVER?

Các propagation types có tên khá giống nhưng lựa chọn hành vi khác nhau:

| Propagation | Khi có transaction ngoài T1 | Khi không có transaction ngoài |
| --- | --- | --- |
| `REQUIRED` | Tham gia T1 | Tạo transaction mới |
| `SUPPORTS` | **Tham gia T1** | Chạy không yêu cầu actual transaction |
| `NOT_SUPPORTED` | **Suspend T1, chạy ngoài T1** | Chạy không yêu cầu actual transaction |
| `NEVER` | **Báo lỗi** vì không chấp nhận transaction | Chạy không yêu cầu actual transaction |
| `REQUIRES_NEW` | Suspend T1, **tạo transaction T2 mới** | Tạo transaction mới |
| `MANDATORY` | Tham gia T1 | Báo lỗi vì thiếu transaction |

Điểm khó nhất:

- `SUPPORTS` là **có thì tham gia**, nên method có thể ghi SQL trong T1 nếu caller có transaction.
- `NOT_SUPPORTED` là **có thì tránh**, nên method phải chạy ngoài T1 dù caller đang có transaction.
- `NEVER` là **có thì từ chối**, nên được dùng khi muốn xem transaction ngoài là sai hợp đồng kỹ thuật.
- `REQUIRES_NEW` là **luôn cần T2 mới**, không phải “không giao dịch”.

Nếu muốn **đọc dữ liệu trong transaction ngoài** để đảm bảo cùng snapshot/consistency hoặc nhìn thấy thay đổi chưa commit của chính caller, không nên chọn NOT_SUPPORTED. Nếu method chỉ thực hiện thao tác không cần transaction, nhưng vẫn muốn tham gia khi caller đã mở, xem xét SUPPORTS với hiểu biết về synchronization.

## 9. Truy cập dữ liệu chưa commit của outer: một giới hạn quan trọng

Ví dụ T1 đang chạy:

```sql
INSERT INTO purchase_order (id, status)
VALUES (77, 'PENDING');
```

Outer chưa commit và ngay sau đó gọi inner NOT_SUPPORTED để truy vấn:

```sql
SELECT status FROM purchase_order WHERE id = 77;
```

Trong các mức isolation thông dụng như READ COMMITTED, inner chạy bằng connection/transaction khác thường **không nhìn thấy dòng chưa commit của T1**. Vì vậy:

- Inner có thể nhận `0 rows` hoặc thấy trạng thái **trước khi T1 cập nhật**.
- Nếu inner cố ghi một dòng có **foreign key** tham chiếu dữ liệu mới chưa commit, DB có thể chờ lock, từ chối hoặc timeout.
- Nếu inner cần cập nhật cùng hàng đang bị T1 khóa, nó có thể bị block cho đến khi T1 kết thúc; nhưng T1 đang tạm ngưng **đợi inner trả về**.
- Không nên “khắc phục” bằng cách tắt foreign key hay đọc dirty data trong production khi không phân tích invariant.

**Quan trọng:** `NOT_SUPPORTED` không tự giúp bạn nhìn thấy dữ liệu “mới nhất” của caller. Nó thường làm ngược lại: **tách khỏi context transaction của caller**. Nếu mục tiêu là kiểm tra dữ liệu vừa ghi bởi T1, hãy thực hiện trong cùng T1 hoặc điều chỉnh thời điểm đọc.

### Mất tính nhất quán giữa nhiều lần đọc

Khi inner chạy không có transaction Spring bao toàn bộ method, hai câu SELECT chạy nối tiếp có thể quan sát hai trạng thái committed khác nhau do một transaction khác commit ở giữa, tùy DB/connection và isolation. Không dựa vào NOT_SUPPORTED để cung cấp cùng một snapshot nhất quán qua nhiều truy vấn.

Với yêu cầu snapshot mạnh hơn, phải có transaction read-only với isolation phù hợp, nhưng nhớ rằng `readOnly=true` đơn lẻ không đồng nghĩa snapshot isolation hoặc cấm ghi tuyệt đối.

## 10. Rủi ro lock và connection pool khi suspend

Tạm ngưng transaction không nhất thiết giải phóng resource:

```text
Outer T1:
    giữ connection C1
    giữ row lock trên inventory(id=10)
    |
    +--> inner NOT_SUPPORTED:
            lấy connection C2 (ví dụ)
            UPDATE inventory(id=10)
            chờ lock của T1
    |
    Outer chờ inner trả về, không thể kết thúc T1.
```

Đây là tình huống tự chặn:

1. T1 giữ lock.
2. Inner cần lock đó qua một connection không thuộc T1.
3. Outer đã nhường call stack cho inner và không thể commit/rollback T1 trước khi inner kết thúc.
4. Inner chờ lock được thả, có thể dẫn tới timeout hoặc deadlock tùy DB.

### Vì sao có thể cần thêm connection?

Ngay cả khi inner **không tạo transaction mới**, câu SQL của inner vẫn có thể cần **một JDBC connection khác** vì connection của T1 đang được giữ lại để resume sau đó. Nếu connection pool quá nhỏ, inner có thể phải chờ connection rảnh.

Ví dụ tải đồng thời:

```text
N request đồng thời, mỗi request đang giữ một connection của T1.
Mỗi request gọi inner NOT_SUPPORTED có truy cập DB và cần connection nữa.
Nếu pool tối đa chỉ N connections, không request nào lấy được connection mới
cho inner; có thể xảy ra pool starvation và timeout.
```

Số connection chính xác phụ thuộc cách Spring quản lý datasource/transaction manager và driver. Với ứng dụng production, nên đo concurrency, thời gian giữ connection và các tầng call lồng nhau. Không áp dụng số `4` trong ví dụ như một công thức sizing.

### Không dùng NOT_SUPPORTED chỉ để “tránh giữ transaction khi gọi mạng”

Nếu outer T1 đã mở trước khi gọi NOT_SUPPORTED, T1 **vẫn tồn tại và thường vẫn giữ connection/lock** khi bị suspend. Một method inner chờ API ngoài 15 giây có thể khiến outer giữ tài nguyên lâu hơn. Tốt hơn là tổ chức lại ranh giới transaction: thực hiện I/O chậm trước khi mở T1 hoặc sau khi T1 commit, khi phù hợp nghiệp vụ.

## 11. Proxy: lời gọi nội bộ có thể khiến NOT_SUPPORTED không chạy

Xem code:

```java
@Service
class ReportService {

    @Transactional
    public void build() {
        jdbc.update("INSERT INTO business_record ...");
        readOutsideTransaction();
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void readOutsideTransaction() {
        // Mong muốn không dùng T1.
    }
}
```

Đây là **mã minh họa**, SQL chưa hoàn chỉnh và trường `jdbc` chưa khai báo.

Với Spring AOP **proxy mode thông thường**, lời gọi `readOutsideTransaction()` từ chính object của `ReportService` không đi qua proxy của method đó. Hệ quả:

- Transaction interceptor **không áp dụng chính sách NOT_SUPPORTED** cho lời gọi nội bộ.
- Các truy cập JDBC bên trong có thể **tiếp tục tham gia T1**, trái hoàn toàn với ý định “chạy ngoài transaction”.
- Khi outer rollback, các thay đổi có thể rollback cùng T1.

Đây là lý do ví dụ mục 6 dùng **hai class Spring beans**:

```text
CheckoutService (bean A)
       |
       +-- injected IndependentService (bean B, có proxy)
                    |
                    +-- @Transactional(NOT_SUPPORTED)
```

Nếu muốn một method thực sự có boundary NOT_SUPPORTED, hãy gọi nó qua Spring-managed proxy. Cũng không tự tạo bean bằng `new IndependentService(jdbc)` rồi mong annotation chạy.

### Visibility và final

Private method không thể là điểm advice của Spring proxy thông thường. Với class-based proxy, final method không thể bị override để intercept. Với JDK interface-based proxy, phải dùng method được expose qua interface. Cách an toàn cho bài này là public, non-final service method được bean khác gọi qua injection.

## 12. Ngoại lệ từ inner: ảnh hưởng đến transaction ngoài như thế nào?

**NOT_SUPPORTED không có một physical transaction riêng để rollback.** Nhưng exception từ inner vẫn là một Java exception có thể đi ngược call stack tới outer.

Hai trường hợp:

### Trường hợp A — Outer không bắt lỗi

```java
@Transactional
public void outer() {
    writeBusiness();          // Thuộc T1.
    innerNotSupported.work();  // Ngoài T1; có thể có side effect đã auto-commit.
    // Nếu work() ném RuntimeException và không catch,
    // ngoại lệ thoát qua outer transaction interceptor.
}
```

Đây là snippet minh họa. Inner transaction infrastructure **resume T1 ngay cả khi lời gọi inner thất bại**, rồi exception tiếp tục ném qua outer method. Interceptor của outer thấy `RuntimeException` và **rollback T1 theo mặc định**.

Những side effects đã commit ngoài T1 **không rollback theo**.

### Trường hợp B — Outer bắt lỗi và tiếp tục

```java
@Transactional
public void outer() {
    writeBusiness(); // Thuộc T1.
    try {
        innerNotSupported.work();
    } catch (IllegalStateException ex) {
        // Nghiệp vụ cho phép tiếp tục.
    }
}
```

Nếu T1 không bị rollback-only do nguyên nhân khác và outer trả về bình thường, T1 **có thể commit**. Inner NOT_SUPPORTED không có physical transaction T2 để tự đánh dấu T1 rollback-only.

Không áp dụng kết luận này một cách máy móc khi lỗi phát sinh từ câu SQL thuộc T1, hoặc có một interceptor khác đánh dấu rollback-only. Ngoài ra, checked exception theo rollback rules mặc định có cách xử lý khác khi thoát khỏi outer; cần thiết kế rõ nếu nghiệp vụ phải rollback.

### Hai kiểu thất bại độc lập

| Lỗi | Outer có thể rollback không? | Những gì inner đã commit ngoài T1 có bị outer hủy không? |
| --- | --- | --- |
| Inner ném unchecked exception, outer không catch | Có, thường rollback T1 | **Không** |
| Inner ném unchecked exception, outer catch và trả bình thường | T1 có thể commit | **Không** |
| Outer tự ném RuntimeException sau inner thành công | Có, rollback T1 | **Không** |
| Inner SQL thứ hai thất bại sau SQL thứ nhất auto-commit | Tùy exception có lan ra outer và rule của outer | **Không tự động** |
| Database/pool không cấp connection cho inner | Inner có thể chưa ghi gì; outer xử lý exception tùy thiết kế | Không thể giả định có side effect |

Đừng đồng nhất “exception” với “transaction rollback ở mọi nơi”. Phải xác định **physical transaction nào tồn tại và interceptor nào nhìn thấy exception**.

## 13. Thuộc tính readOnly, isolation, timeout trong NOT_SUPPORTED

Ví dụ:

```java
@Transactional(
    propagation = Propagation.NOT_SUPPORTED,
    readOnly = true,
    timeout = 10
)
public void readReport() {
    // ...
}
```

Đây là annotation minh họa. Vì NOT_SUPPORTED **không tạo physical transaction mới**, không được kỳ vọng `readOnly=true` sẽ bắt buộc database không ghi, hoặc timeout/isolation mới được áp như khi một transaction thực được mở. Một số hạ tầng có thể vẫn tạo scope cho synchronization và metadata, nhưng nó không thay đổi định nghĩa **thực thi non-transactionally**.

Nếu cần một transaction đọc có snapshot và timeout thực sự, nên cân nhắc `REQUIRED` hoặc `REQUIRES_NEW` với readOnly/isolation/timeout phù hợp, theo yêu cầu nghiệp vụ. Nếu chỉ cần đọc thông thường và muốn tránh transaction T1, NOT_SUPPORTED có thể là lựa chọn, nhưng cần hiểu giới hạn consistency.

## 14. Nhiều transaction manager: suspend cái gì?

Giả sử ứng dụng có:

- `ordersTxManager` quản lý `ordersDataSource`.
- `analyticsTxManager` quản lý `analyticsDataSource`.

Bạn viết:

```java
@Transactional(
    transactionManager = "analyticsTxManager",
    propagation = Propagation.NOT_SUPPORTED
)
public void readAnalytics() {
    // Truy vấn analyticsDataSource.
}
```

Policy này được áp dụng qua **analyticsTxManager**. Nó không mặc nhiên suspend mọi transaction đang tồn tại trên **ordersTxManager** hoặc mọi nguồn dữ liệu trong JVM.

Vì vậy khi nói “outer transaction bị tạm ngưng” phải kiểm tra:

1. Outer dùng manager nào?
2. Inner NOT_SUPPORTED chọn manager nào?
3. Transaction manager có tìm thấy một transaction hiện hành của **resource mà nó quản lý** không?
4. Repository/DAO/JdbcTemplate bên trong truy cập datasource nào?

**Nếu các manager khác nhau**, ngữ cảnh tài nguyên và synchronization có thể tương tác theo cấu hình; không kết luận rằng một annotation trên manager B bảo đảm mọi tác động của manager A đều được tạm ngưng. Với bài nhập môn, dùng cùng một manager và datasource như ví dụ chính để quan sát đúng bản chất propagation.

### Hỗ trợ suspension phụ thuộc manager

Spring document ghi chú rằng suspension thực tế không phải được mọi transaction manager hỗ trợ sẵn. Ví dụ JTA có thể cần cung cấp transaction manager native của server để suspend/resume được. Nếu môi trường không hỗ trợ, có thể nhận exception khi yêu cầu NOT_SUPPORTED với transaction hiện hành.

Không chữa lỗi bằng cách xóa exception và giả định method sẽ chạy không transaction. Hãy xác minh khả năng suspend/resume của transaction manager đang dùng.

## 15. Khi nào NOT_SUPPORTED hữu ích và khi nào nguy hiểm?

### Các trường hợp có thể hợp lý

- **Truy vấn phụ độc lập** mà bạn cố ý không muốn tham gia transaction outer và không cần đọc dữ liệu chưa commit của outer.
- **Thao tác không cần transaction**, trong những ranh giới được thiết kế rõ và không cần bảo đảm atomically commit một chuỗi SQL.
- **Ghi nhật ký thử nghiệm/chẩn đoán riêng lẻ** bằng JDBC, khi nghiệp vụ chủ đích cho phép record vẫn tồn tại nếu thao tác chính rollback, và hiểu rằng nhiều statement không có atomicity chung.

Ngay cả trong các trường hợp này, còn phải cân nhắc vấn đề lock, pool và độ trễ khi outer T1 đang suspend.

### Những trường hợp cần tránh

- Chuyển tiền, cập nhật nhiều bảng phải **cùng thành công hoặc cùng thất bại**.
- Phát `OrderCreated` hoặc `PaymentSucceeded` **trước khi outer transaction commit**; nếu outer rollback, sự kiện đã phát trở thành sai sự thật.
- Code đang phụ thuộc vào bản ghi/row lock hoặc trạng thái chưa commit của T1.
- Báo cáo cần **snapshot nhất quán** qua nhiều câu SELECT.
- Code JPA cần transaction để flush/persist, nhưng được đưa sang NOT_SUPPORTED chỉ vì “muốn nó chạy nhanh hơn”.
- Khối tác vụ dài làm outer tiếp tục giữ tài nguyên transaction trong thời gian chờ.

### Những lựa chọn thay thế theo mục tiêu

| Mục tiêu nghiệp vụ | Giải pháp thường phù hợp hơn |
| --- | --- |
| Nhiều thao tác DB phải nguyên tử cùng outer | Giữ trong `REQUIRED` / cùng transaction |
| Một nhóm thao tác DB cần transaction riêng và atomicity của chính nhóm đó | `REQUIRES_NEW`, sau khi phân tích side effects |
| Chạy không transaction dù outer đang có | `NOT_SUPPORTED`, với đánh đổi rõ ràng |
| Chạy không transaction nhưng muốn báo lỗi nếu caller có transaction | `NEVER` |
| Sự kiện chỉ tồn tại khi outer commit | Outbox trong cùng transaction hoặc after-commit workflow |
| Hoạt động remote I/O chậm | Di chuyển ra ngoài ranh giới transaction nếu có thể, không chỉ suspend |
| Kiểm thử sự hiện diện của transaction | `TransactionSynchronizationManager.isActualTransactionActive()` và kết quả DB |

**Chọn propagation theo hợp đồng nghiệp vụ**, không dựa vào ý muốn “đi tắt” các lỗi rollback.

## 16. Kiểm thử đúng: đọc dữ liệu sau khi transaction ngoài kết thúc

Cách kiểm thử tốt nhất cho case trong bài:

1. Tạo database test rỗng với hai bảng độc lập.
2. Gọi outer Spring bean từ caller **không có transaction**.
3. Outer REQUIRED INSERT một hàng trong T1.
4. Outer gọi inner NOT_SUPPORTED qua một Spring bean khác.
5. Inner quan sát `isActualTransactionActive() == false`, rồi JDBC INSERT trong connection auto-commit.
6. Outer resume T1 rồi ném runtime exception.
7. Bắt exception ở caller **sau khi outer transaction interceptor hoàn tất rollback**.
8. Query lại DB: hàng outer không còn; hàng inner đã auto-commit còn.
9. Lặp lại kịch bản inner ném lỗi rồi outer catch và hoàn tất; kiểm tra outer có thể commit nếu không rollback-only.

**Một bẫy của Spring Test:** nếu đặt `@Transactional` trên chính test method, framework test có thể tự tạo transaction bao quanh toàn bộ test và rollback khi kết thúc. Khi đó trạng thái “caller không có transaction” và việc đọc dữ liệu sau commit/rollback có thể không còn đúng như mô tả. Nên viết integration test cho tình huống này với lời gọi bên ngoài transaction của test, hoặc kiểm soát test transaction chủ động.

Dùng H2 để học khái niệm, nhưng nếu production chạy PostgreSQL/MySQL, nên có thêm integration test bằng database cùng loại (ví dụ Testcontainers), vì lock, auto-commit, isolation và hành vi khi SQL lỗi có thể khác.

### Bảng kỳ vọng

| Case | Outer T1 | Inner NOT_SUPPORTED | Sau lời gọi |
| --- | --- | --- | --- |
| A | INSERT rồi rollback | Một JDBC INSERT đã auto-commit | Outer mất, inner còn |
| B | INSERT rồi commit | Một JDBC INSERT đã auto-commit | Cả hai còn |
| C | Catch lỗi inner, sau đó commit | Inner INSERT thành công rồi ném lỗi | Outer và inner có thể cùng còn |
| D | Không catch lỗi inner; outer rollback | Inner INSERT rồi ném lỗi | Outer mất, inner đã commit có thể còn |
| E | Outer giữ lock inner cần | Inner chờ lock | Có thể timeout/deadlock |
| F | Inner gọi bằng self-invocation, advice không áp dụng | JDBC tham gia T1 | Outer rollback có thể hủy cả hai |
| G | Inner dùng JPA ghi yêu cầu transaction | Không có physical transaction | Có thể gặp `TransactionRequiredException` |

Điều cần kiểm chứng không chỉ là `active=false` mà còn là **các thay đổi thực tế đã commit ở đâu**.

### Logging hỗ trợ

Có thể bật log trong `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log có thể giúp tìm dấu vết suspend/resume và commit/rollback của outer. Thông điệp chính xác khác nhau theo phiên bản Spring và transaction manager; đừng phụ thuộc một chuỗi log nhất định. Kết quả đọc DB sau các lời gọi mới là bằng chứng chính.

## 17. Những lỗi tư duy thường gặp

**Sai 1 — NOT_SUPPORTED nghĩa là commit transaction outer trước khi chạy inner.** Không. Spring **suspend** T1, không commit T1. Khi inner xong, T1 được resume.

**Sai 2 — Inner có `@Transactional(NOT_SUPPORTED)` nên vẫn có transaction riêng.** Không. NOT_SUPPORTED chủ động tránh actual transaction. Nếu cần transaction T2 riêng, xem REQUIRES_NEW.

**Sai 3 — NOT_SUPPORTED rollback các câu SQL khi inner ném RuntimeException.** Không thể giả định như vậy. Với JDBC auto-commit, statement đã thành công có thể được commit độc lập và không có physical transaction Spring bao toàn bộ method.

**Sai 4 — Vì T1 suspend nên connection và row locks được giải phóng.** Không nhất thiết; chúng thường vẫn được giữ để T1 tiếp tục. Inner có thể thiếu connection hoặc chờ lock của outer.

**Sai 5 — NOT_SUPPORTED sẽ nhìn thấy những gì outer vừa INSERT.** Không, nếu outer chưa commit và inner dùng connection/transaction khác ở isolation thông thường.

**Sai 6 — Khối NOT_SUPPORTED ném lỗi thì outer nhất định rollback.** Chỉ nếu exception cuối cùng làm outer rollback hoặc T1 bị đánh dấu rollback-only. Outer có thể bắt lỗi và tiếp tục, như kịch bản B.

**Sai 7 — Có `@Transactional` trên method trong cùng class là đủ.** Với proxy mode, self-invocation bỏ qua advice của method được gọi, nên NOT_SUPPORTED không được áp dụng ở ranh giới đó.

**Sai 8 — Có `isSynchronizationActive() == true` thì chắc chắn actual transaction đang active.** Không. Synchronization scope và actual physical transaction không phải cùng một khái niệm.

**Sai 9 — NOT_SUPPORTED luôn làm mọi thư viện persistence tự auto-commit.** Không. Hành vi ghi ngoài transaction phụ thuộc JDBC auto-commit, JPA provider, resource và API.

**Sai 10 — NOT_SUPPORTED làm application nhanh hơn vì bỏ transaction.** Không có bảo đảm tốc độ; suspend/resume, pool bổ sung, lock và việc mất atomicity có thể làm hệ thống phức tạp hơn.

## 18. Bài tập tự kiểm tra

### Câu 1 — Trạng thái active của outer và inner

Một `OuterService.run()` dùng `@Transactional(REQUIRED)` được gọi từ controller không có transaction. Bên trong gọi `InnerService.work()` dùng `@Transactional(NOT_SUPPORTED)` qua proxy. Với cùng JDBC manager, `isActualTransactionActive()` lần lượt là gì?

**Đáp án:** Trong outer là `true`; trong inner là `false`; sau khi inner trả về và outer tiếp tục là `true`. Sau khi outer hoàn tất, caller lại không có transaction.

### Câu 2 — Một INSERT bên ngoài transaction

Outer INSERT business id=1 vào T1. Inner NOT_SUPPORTED dùng một JDBC connection auto-commit để INSERT audit id=100. Sau đó outer ném runtime exception và T1 rollback. Có thể còn gì?

**Đáp án:** Business id=1 bị rollback. Audit id=100 có thể vẫn tồn tại nếu statement inner đã auto-commit thành công, vì nó không tham gia T1.

### Câu 3 — Hai INSERT và statement thứ hai thất bại

Inner NOT_SUPPORTED dùng JDBC auto-commit để INSERT hai hàng. Lệnh đầu thành công; lệnh hai vi phạm UNIQUE. Spring có thể dùng rollback của inner để đảo ngược lệnh đầu không?

**Đáp án:** Không có một physical transaction Spring bao toàn bộ method inner. Statement đầu có thể đã commit. Nếu nghiệp vụ cần nguyên tử giữa hai lệnh, phải dùng một transaction phù hợp, chẳng hạn REQUIRES_NEW cho phạm vi độc lập.

### Câu 4 — So sánh NOT_SUPPORTED và REQUIRES_NEW

Cả hai đều có thể suspend T1. Điểm khác biệt thiết yếu là gì?

**Đáp án:** REQUIRES_NEW yêu cầu mở **transaction T2**; NOT_SUPPORTED yêu cầu chạy **không có actual transaction hiện hành**. REQUIRES_NEW có thể rollback nhiều câu SQL trong T2 như một đơn vị; NOT_SUPPORTED không tạo T2 để bảo vệ các câu lệnh.

### Câu 5 — Inner ném lỗi, outer catch

Outer T1 INSERT một hàng, gọi inner NOT_SUPPORTED. Inner INSERT độc lập rồi ném `IllegalStateException`. Outer catch và trả bình thường. Có bắt buộc T1 rollback không?

**Đáp án:** Không, nếu T1 không rollback-only và không có lỗi khác. Outer có thể commit. Bản ghi inner đã auto-commit không bị outer rollback tự hủy.

### Câu 6 — Self-invocation

Outer dùng `this.inner()`, trong đó inner có `@Transactional(NOT_SUPPORTED)`. Tại sao một thao tác inner có thể rollback cùng outer?

**Đáp án:** Trong proxy mode, `this.inner()` không qua transaction advice, nên Spring không suspend T1. JDBC của inner có thể vẫn dùng connection của T1.

### Câu 7 — Đọc dữ liệu chưa commit

Outer T1 INSERT order 77 nhưng chưa commit, rồi gọi NOT_SUPPORTED để SELECT order 77. Có chắc inner nhìn thấy bản ghi đó?

**Đáp án:** Không. Inner thường dùng connection ngoài T1, nên không nhìn thấy uncommitted changes ở isolation thông thường.

### Câu 8 — Connection pool

Pool có 8 connections, có 8 request đồng thời, mỗi request giữ 1 connection trong T1 rồi gọi NOT_SUPPORTED thực hiện JDBC query. Có rủi ro gì?

**Đáp án:** Inner có thể cần connection khác trong khi tất cả connection bị T1 giữ, dẫn đến pool starvation và timeout. Tùy implementation có thể khác, nhưng phải tính khả năng cần thêm connection khi suspend.

### Câu 9 — Cần dữ liệu chỉ tồn tại khi order commit

Ứng dụng ghi event `OrderCreated` trong inner NOT_SUPPORTED trước khi outer commit. Outer thất bại. Thiết kế này có phù hợp không?

**Đáp án:** Không nếu event chỉ đúng sau khi order đã commit. Nên lưu outbox record trong **cùng T1** với order hoặc tổ chức after-commit handling phù hợp, thay vì để event auto-commit trước.

## 19. Checklist áp dụng cho hệ thống thật

- [ ] Đã xác định **mục tiêu rõ ràng** là chạy non-transactionally, không phải tạo transaction riêng.
- [ ] Đã đọc chính xác `Propagation.NOT_SUPPORTED`: suspend transaction hiện có, sau đó resume.
- [ ] Service method là entry point được gọi qua Spring-managed proxy, không phải self-invocation.
- [ ] Transaction manager có khả năng suspend/resume trong hạ tầng đang dùng.
- [ ] Đã xác định manager/resource nào có transaction T1; nếu nhiều DataSource, không giả định mọi transaction đều suspend.
- [ ] Các thao tác JDBC/JPA ngoài transaction có hành vi được xác minh (auto-commit hoặc TransactionRequiredException).
- [ ] Không có yêu cầu atomicity nhiều câu SQL ở inner nếu dùng NOT_SUPPORTED.
- [ ] Inner không phụ thuộc dữ liệu T1 chưa commit và không cần khóa mà T1 đang giữ.
- [ ] Connection pool/timeout/concurrency đủ cho tình huống suspend và inner lấy connection khác.
- [ ] Mọi side effect độc lập có ý nghĩa nghiệp vụ hợp lệ nếu outer rollback.
- [ ] Đã kiểm tra ngoại lệ inner được catch hay lan ra outer và ảnh hưởng đến rollback T1 như thế nào.
- [ ] Đã test trên DB tương ứng production, đọc dữ liệu sau commit/rollback.
- [ ] Không dùng NOT_SUPPORTED để thay thế outbox/after-commit khi event chỉ hợp lệ sau outer commit.

## 20. Kết luận

**`Propagation.NOT_SUPPORTED` = không chạy trong transaction hiện hành; nếu đang có transaction thì tạm ngưng nó trong thời gian thực thi method, sau đó khôi phục.** Nó **không tạo physical transaction mới** như `REQUIRES_NEW`.

Khi JDBC connection chạy auto-commit trong scope non-transactional, các statement đã thành công có thể **được commit độc lập**, nên outer transaction rollback không tự đảo ngược chúng. Đây vừa là đặc tính có thể hữu ích với dữ liệu chẩn đoán, vừa là rủi ro đối với tính nguyên tử của nghiệp vụ. Hãy kiểm tra đúng proxy, manager, connection, lock, exception flow và trạng thái DB để biết chương trình thực sự làm gì.

### Tài liệu tham khảo

- Spring Framework — `Propagation.NOT_SUPPORTED` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework — `TransactionDefinition.PROPAGATION_NOT_SUPPORTED` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — Declarative Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Boot — SQL Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html
