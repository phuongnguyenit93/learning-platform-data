# Lộ trình từ cơ chế commit, rollback đến kiểm chứng hành vi

## 1. Đích đến của bài học

Trong Spring Framework, hiểu transaction không dừng ở việc đặt `@Transactional` lên một phương thức. Điều cần chứng minh là: **khi một thao tác nghiệp vụ kết thúc, những thay đổi dữ liệu nào được giữ lại, những thay đổi nào bị hủy, và vì sao**.

Bài này dẫn người học từ khái niệm commit/rollback đến cách thiết lập ranh giới transaction, tạo tình huống lỗi có kiểm soát, viết integration test và quan sát kết quả thực tế. Ví dụ dùng **Spring Boot 3.x, Java 17+, Spring JDBC và cơ sở dữ liệu H2** để tập trung vào giao dịch; các quy tắc chính cũng áp dụng với Spring Data JPA, nhưng thời điểm SQL được gửi xuống database có thể khác do cơ chế flush.

Sau bài học, bạn có thể:

1. Mô tả vòng đời `begin → thực thi → commit/rollback → giải phóng tài nguyên`.
2. Chỉ ra phương thức và lời gọi nào thực sự nằm trong một transaction do Spring quản lý.
3. Dự đoán kết quả với `RuntimeException`, checked exception và ngoại lệ bị bắt bên trong phương thức.
4. Phân biệt rollback thật với việc *test tự rollback* rồi tưởng rằng ứng dụng đúng.
5. Viết kiểm thử đo trạng thái dữ liệu **sau khi lời gọi qua transactional proxy đã kết thúc**.
6. Nhận diện thời điểm cần học tiếp về propagation, isolation, rollback-only và giao dịch nhiều tài nguyên.

## 2. Bản đồ học tập: từ cơ chế đến bằng chứng

| Chặng | Câu hỏi phải trả lời | Bằng chứng hoàn thành |
| --- | --- | --- |
| 1. Mô hình | Commit và rollback làm gì? | Vẽ được vòng đời transaction và trạng thái trước/sau |
| 2. Ranh giới | Ai mở/kết thúc transaction trong Spring? | Xác định được proxy, service, transaction manager, database |
| 3. Quy tắc lỗi | Lỗi nào gây rollback theo mặc định? | Dự đoán đúng bảng tình huống ở mục 5 |
| 4. Thực nghiệm | Làm thế nào tạo ca thành công và thất bại? | Chạy được service có chủ đích tạo lỗi |
| 5. Kiểm chứng | Dữ liệu thực sự được giữ hay bị hủy? | Integration test truy vấn sau khi lời gọi kết thúc |
| 6. Mở rộng | Điều gì thay đổi khi lồng transaction hoặc thêm tài nguyên? | Biết đặt câu hỏi về propagation, isolation và giới hạn nguyên tử |

Đừng chuyển thẳng từ chặng 1 sang các thuộc tính nâng cao. Nếu chưa chứng minh được một lệnh `INSERT` được commit hoặc rollback trong một transaction đơn giản, việc tranh luận `REQUIRES_NEW` hay `NESTED` rất dễ dựa trên giả định sai.

## 3. Commit, rollback và tính nguyên tử

Một transaction gom nhiều thao tác với cơ sở dữ liệu thành một đơn vị làm việc. Thuộc tính **atomicity** trong ACID yêu cầu nhóm thao tác được chấp nhận như một khối hoặc bị hủy theo khả năng của transaction manager và database. **Consistency** phụ thuộc cả ràng buộc dữ liệu lẫn quy tắc nghiệp vụ; transaction không tự bảo đảm chương trình đã viết đúng nghiệp vụ. **Isolation** chi phối tương tác với transaction đồng thời; **durability** liên quan việc thay đổi đã commit được hệ quản trị cơ sở dữ liệu duy trì theo cam kết của nó.

- **Commit**: yêu cầu database hoàn tất transaction; các thay đổi hợp lệ trở thành kết quả được chấp nhận của giao dịch.
- **Rollback**: yêu cầu database hủy các thay đổi **chưa commit** thuộc transaction đó.
- **Transaction boundary**: điểm bắt đầu và điểm kết thúc phạm vi transaction; trong Spring thường đặt tại một thao tác nghiệp vụ của tầng service.
- **Rollback-only**: trạng thái một transaction đã bị đánh dấu phải rollback; lời gọi commit sau đó không thể biến nó thành commit thành công.

Ví dụ chuyển tiền giữa hai tài khoản trong cùng một database:

```text
BEGIN
  UPDATE account SET balance = balance - 100 WHERE id = 'A';
  UPDATE account SET balance = balance + 100 WHERE id = 'B';
COMMIT            ← cả hai cập nhật được giữ

BEGIN
  UPDATE account SET balance = balance - 100 WHERE id = 'A';
  UPDATE account ...  ← lỗi trước bước cộng tiền
ROLLBACK          ← cập nhật trừ tiền chưa commit bị hủy
```

Điều kiện quan trọng: cả hai câu lệnh phải tham gia **cùng transaction của cùng hệ thống quản lý tài nguyên**. Nếu lệnh đầu tự commit trước khi lệnh hai thất bại, rollback của transaction thứ hai không quay ngược được commit trước đó. Một email, HTTP request hay sự kiện đã gửi ra hệ thống khác cũng không tự được database rollback.

## 4. Spring đưa transaction vào lời gọi như thế nào?

Với cấu hình transaction **imperative** thông thường, `@Transactional` là metadata. Spring sử dụng hạ tầng transaction và thường là **AOP proxy** để áp dụng metadata đó khi phương thức của Spring bean được gọi từ bên ngoài qua proxy.

```text
Caller / Controller
       |
       v
Transactional proxy
       |
       +--> TransactionManager: bắt đầu hoặc tham gia transaction
       |
       v
Service method ---> JdbcTemplate / Repository ---> Database
       |
       +--> Trở về bình thường?       -> xét commit
       +--> Ném lỗi ra qua proxy?     -> xét rollback rule
       |
       v
TransactionManager: commit / rollback, dọn tài nguyên
       |
       v
Caller nhận kết quả hoặc exception
```

Trong ứng dụng JDBC, `PlatformTransactionManager` tương ứng (ví dụ `JdbcTransactionManager`/`DataSourceTransactionManager`) điều phối transaction trên `DataSource`. Spring gắn tài nguyên JDBC vào luồng thực thi tương ứng để các lời gọi `JdbcTemplate` sử dụng đúng connection trong transaction. Bạn thường không phải tự gọi `setAutoCommit(false)`, `commit()` hay `rollback()` khi dùng `@Transactional`.

Quy tắc áp dụng thực tế:

- Đặt `@Transactional` trên **phương thức service có tính nghiệp vụ**, thường là public, do Spring quản lý và được bean khác gọi qua proxy.
- Nếu `this.innerMethod()` gọi một phương thức cũng mang `@Transactional` trong cùng đối tượng, lời gọi đó **không đi qua proxy** theo proxy mode mặc định; thuộc tính transaction riêng của `innerMethod` không tự có hiệu lực.
- `@Transactional` không có tác dụng chỉ vì annotation tồn tại: ứng dụng cần transaction manager và cơ chế quản lý transaction đã được kích hoạt. Với dự án Spring Boot JDBC/JPA được cấu hình đúng, Boot thường tự cấu hình các thành phần này.
- Transaction imperative gắn với ngữ cảnh thực thi của luồng hiện tại. Tự mở thread mới hoặc gọi `@Async` không có nghĩa giao dịch ban đầu tự lan sang thread mới. Reactive transaction có cơ chế ngữ cảnh khác và cần học riêng.
- Thành công ở mức gọi phương thức **chưa đủ bằng chứng** commit thành công: lỗi có thể xuất hiện khi flush hoặc lúc transaction manager thực hiện commit.

### 4.1. Mặc định quan trọng của `@Transactional`

| Thuộc tính | Giá trị thông thường | Ý nghĩa |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Tham gia transaction hiện có, hoặc tạo mới nếu chưa có |
| `isolation` | `DEFAULT` | Theo mức mặc định của database/transaction manager |
| `readOnly` | `false` | Transaction đọc/ghi thông thường |
| `rollback rule` | `RuntimeException` và `Error` | Mặc định đánh dấu rollback khi lỗi không kiểm tra này thoát ra qua interceptor |
| Checked `Exception` | Không tự rollback theo mặc định | Cần cấu hình `rollbackFor` khi nghiệp vụ yêu cầu |
| `timeout` | Mặc định của hạ tầng | Không mặc định bảo đảm một giới hạn thời gian cố định trên mọi hệ thống |

Các quyết định trên không thay thế quy tắc về khóa, độ bền dữ liệu hay hỗ trợ thực tế từ database.

## 5. Dự đoán hành vi trước khi chạy mã

Xét một phương thức `@Transactional` đã thực hiện `INSERT` vào database. Bảng sau giả định chỉ có **một transaction Spring độc lập**, dùng JDBC và không bị đánh dấu rollback-only bởi cơ chế khác:

| Kịch bản | Diễn biến tại ranh giới proxy | Kết quả dự kiến |
| --- | --- | --- |
| Kết thúc bình thường | Không có lỗi buộc rollback | **Commit**; bản ghi tồn tại |
| Ném `IllegalStateException` ra ngoài | `RuntimeException` thoát qua interceptor | **Rollback**; bản ghi không tồn tại |
| Ném `IOException` ra ngoài | Checked exception, chưa có rollback rule riêng | **Commit** mặc định, dù caller nhận exception |
| Ném `IOException` với `rollbackFor = IOException.class` | Rule yêu cầu rollback | **Rollback** |
| Ném rồi tự `catch` bên trong, sau đó return bình thường | Interceptor không thấy lỗi đó | Thường **commit**, trừ khi transaction đã rollback-only hoặc có lỗi khác |
| Lỗi từ transaction tham gia khiến outer transaction rollback-only | Caller ngoài có thể bắt lỗi, nhưng trạng thái rollback-only còn đó | **Rollback**; lúc outer định commit có thể phát sinh `UnexpectedRollbackException` |

Điểm cần nhớ: "có exception" và "đã rollback" **không đồng nghĩa**. Phải biết loại exception, nơi exception bị bắt, rollback rule và transaction thực tế đang tham gia.

### 5.1. Ranh giới transaction là một quyết định nghiệp vụ

Giả sử nghiệp vụ `placeOrder` phải lưu đơn và trừ tồn kho. Nếu cả hai phải thành công cùng nhau, transaction thường bao quanh **toàn bộ thao tác** thay vì chỉ quanh từng lệnh lưu:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.items());
    }
}
```

Đây là **mã minh họa cấu trúc**, không phải chương trình độc lập: `Order`, `OrderRepository`, `InventoryRepository` và `reserve` cần được định nghĩa trong dự án thực tế. Khi hai repository dùng cùng transaction manager/database, nếu `reserve` ném runtime exception ra ngoài, các thay đổi chưa commit của `save` cũng được rollback. Nếu `reserve` gọi dịch vụ qua HTTP hoặc ghi sang database do transaction manager khác quản lý, cam kết nguyên tử này không còn tự động đúng.

## 6. Thực hành: tạo bằng chứng commit và rollback bằng Spring JDBC

Ta dựng một ví dụ nhỏ: mỗi thao tác ghi một bản ghi vào bảng `tx_events`. Việc lưu "thành công" hay "lỗi" có thể được kiểm tra qua số bản ghi **sau** khi service trả về hoặc ném exception.

### 6.1. Cấu trúc và phụ thuộc

Tạo dự án Gradle với Java 17+ và các file sau:

```text
tx-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txlab/
    │   │   ├── TxLabApplication.java
    │   │   └── LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txlab/
        └── TransactionFlowTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-lab'
```

`build.gradle` (một tổ hợp Spring Boot 3.x/Java 17 cụ thể để ví dụ có thể chạy lặp lại):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Có thể tạo dự án tương đương bằng Spring Initializr và thay phiên bản plugin theo bản Spring Boot đang được duy trì trong môi trường của bạn. Ví dụ chỉ phụ thuộc các starter, JDBC và H2; không cần web server. Để dùng lệnh `./gradlew`, dự án phải có Gradle Wrapper do Initializr cung cấp hoặc do bạn tạo với Gradle cài sẵn.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txlab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

H2 chạy trong bộ nhớ, thích hợp cho thực nghiệm kiểm soát được. `spring.sql.init.mode=always` bảo đảm Spring Boot chạy script khởi tạo khi tạo context. Bảng là cấu trúc tối giản, tránh các hành vi flush phức tạp của JPA trong bài đầu tiên.

### 6.2. Ứng dụng và service có các nhánh kết quả

`src/main/java/com/example/txlab/TxLabApplication.java`:

```java
package com.example.txlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }
}
```

`src/main/java/com/example/txlab/LedgerService.java`:

```java
package com.example.txlab;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveSuccessfully(String label) {
        insert(label);
    }

    @Transactional
    public void saveThenThrowRuntime(String label) {
        insert(label);
        throw new IllegalStateException("Simulated runtime failure");
    }

    @Transactional
    public void saveThenThrowChecked(String label) throws IOException {
        insert(label);
        throw new IOException("Simulated checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void saveThenThrowCheckedWithRollback(String label) throws IOException {
        insert(label);
        throw new IOException("Simulated checked failure");
    }

    @Transactional
    public void saveThenCatchInside(String label) {
        insert(label);
        try {
            throw new IllegalStateException("Handled inside method");
        } catch (IllegalStateException ignored) {
            // Ví dụ chủ động nuốt lỗi: proxy chỉ thấy return bình thường.
        }
    }

    private void insert(String label) {
        jdbc.update("INSERT INTO tx_events (label) VALUES (?)", label);
    }
}
```

Tất cả phương thức công khai trên được **một bean bên ngoài gọi**, thông qua proxy của Spring; `insert` là hàm trợ giúp private chạy trong transaction đã mở của phương thức bao ngoài. Với `saveThenCatchInside`, thông điệp là mô tả quan sát transaction, **không khuyến khích bỏ qua lỗi nghiệp vụ**.

### 6.3. Integration test xác minh trạng thái thật

`src/test/java/com/example/txlab/TransactionFlowTest.java`:

```java
package com.example.txlab;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionFlowTest {
    @Autowired
    private LedgerService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clearTable() {
        jdbc.update("DELETE FROM tx_events");
    }

    private long countRows() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalReturnCommits() {
        service.saveSuccessfully("ok");
        assertEquals(1L, countRows());
    }

    @Test
    void runtimeExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> service.saveThenThrowRuntime("runtime"));
        assertEquals(0L, countRows());
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThrows(IOException.class,
                () -> service.saveThenThrowChecked("checked"));
        assertEquals(1L, countRows());
    }

    @Test
    void rollbackForMakesCheckedExceptionRollback() {
        assertThrows(IOException.class,
                () -> service.saveThenThrowCheckedWithRollback("checked-rollback"));
        assertEquals(0L, countRows());
    }

    @Test
    void caughtRuntimeExceptionDoesNotAutomaticallyRollback() {
        service.saveThenCatchInside("caught");
        assertEquals(1L, countRows());
    }
}
```

**Điểm quyết định của kiểm thử:** class test này **không gắn `@Transactional`**. Mỗi lời gọi service đi qua Spring proxy để transaction nghiệp vụ hoàn thành. Sau đó, câu `SELECT COUNT(*)` từ test chạy ngoài transaction của service, cho phép đo kết quả commit/rollback đã quan sát được. `@BeforeEach` xóa dữ liệu của ca trước để các kiểm thử độc lập trong cấu hình JUnit chạy tuần tự mặc định.

Chạy ở thư mục `tx-lab`, với JDK 17+ và Gradle Wrapper đã được tạo:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Kết quả kỳ vọng:** cả **5 test pass**. Bảng dữ liệu quan sát ngay sau lời gọi tương ứng là `1, 0, 1, 0, 1` theo thứ tự các phương thức kiểm thử được liệt kê ở trên. JUnit **không bảo đảm thứ tự chạy test** và không có stdout ứng dụng cố định cho 5 test này; vì vậy không được suy diễn thứ tự log để chứng minh kết quả. Báo cáo chi tiết nằm trong `build/reports/tests/test/index.html`.

Nếu thiếu Gradle Wrapper, có thể cài Gradle tương thích rồi chạy `gradle test` hoặc tạo wrapper trước. Không dùng `javac` trần cho ví dụ Spring này vì các class phải được biên dịch với dependency Spring/JUnit/H2 trên classpath; Gradle thực hiện việc đó.

### 6.4. Vì sao bộ test này chứng minh được nhiều hơn "không có exception"?

- `normalReturnCommits` kiểm tra **dữ liệu tồn tại**, không chỉ kiểm tra phương thức kết thúc.
- `runtimeExceptionRollsBack` kiểm tra cả exception **và** việc bản ghi biến mất; `assertThrows` một mình không chứng minh rollback.
- `checkedExceptionCommitsByDefault` là phản ví dụ cho niềm tin "cứ lỗi là rollback".
- `rollbackForMakesCheckedExceptionRollback` chứng minh một thay đổi khai báo làm đổi kết quả dữ liệu.
- `caughtRuntimeExceptionDoesNotAutomaticallyRollback` cho thấy **vị trí bắt exception** quan trọng tương đương kiểu exception.

Đây là một ví dụ xác minh behavior ở ranh giới application/database. Nó chưa chứng minh tính đúng đắn của toàn bộ nghiệp vụ, không thay thế kiểm thử concurrency, và không có nghĩa H2 có mọi hành vi khóa hoặc isolation như PostgreSQL/MySQL đang dùng trong production.

## 7. Quy trình kiểm chứng có thể tái sử dụng

Khi gặp một service có giao dịch thật, làm theo chuỗi sau thay vì suy đoán từ annotation:

1. **Định nghĩa invariant nghiệp vụ**: ví dụ "không được giữ bản ghi thanh toán nếu trừ kho thất bại".
2. **Khoanh vùng tài nguyên và boundary**: database nào, transaction manager nào, phương thức bean nào được caller gọi qua proxy.
3. **Chọn điểm gây lỗi**: sau thao tác ghi đầu tiên nhưng trước khi kết thúc nghiệp vụ; nêu rõ runtime hay checked exception.
4. **Chụp baseline**: số hàng, số dư, trạng thái trước khi chạy; dữ liệu test phải độc lập.
5. **Gọi qua đường đi thật**: caller → service bean → repository/JDBC, không gọi trực tiếp một method nội bộ qua `this` để thử annotation.
6. **Để lời gọi kết thúc**: nhận thành công hoặc bắt exception bên ngoài transaction.
7. **Đọc lại bằng ngữ cảnh độc lập**: dùng truy vấn sau transaction để xác minh bản ghi nào tồn tại. Với JPA, cân nhắc `flush`/`clear` hoặc truy vấn ở transaction mới để tránh đọc lại persistence context cũ.
8. **So sánh với invariant**: nếu trạng thái sai, xem transaction manager, quy tắc exception, transaction boundary và propagation trước khi sửa annotation theo cảm tính.
9. **Kiểm tra cả trường hợp đối chứng**: một ca thành công có dữ liệu được giữ và một ca thất bại có dữ liệu bị hủy.

Khi kiểm tra qua HTTP, controller không nên được giả định là transaction boundary chỉ vì request bắt đầu ở đó. Hãy lần theo các service thực sự được proxy và lưu ý lời gọi ngoài database (HTTP, email, messaging, filesystem) không nằm trong transaction JDBC thông thường.

## 8. Bẫy phổ biến khiến kiểm chứng sai

### 8.1. `@Transactional` trên test che khuất commit thật

Trong Spring TestContext, một test gắn `@Transactional` thường được mở **test-managed transaction** và **rollback mặc định sau test**. Service với `REQUIRED` có thể tham gia chính transaction của test, khiến dữ liệu nhìn thấy trong test nhưng chưa từng được commit bởi boundary mà bạn muốn đánh giá. `@Commit`, `@Rollback(false)` hoặc `TestTransaction` có thể điều khiển test-managed transaction trong các trường hợp cần thiết; chúng **không thay thế** việc thiết kế điểm quan sát phù hợp.

Ví dụ phản chứng:

```java
@SpringBootTest
@Transactional
class MisleadingTest {
    // Service REQUIRED có thể chỉ tham gia transaction do test quản lý.
    // assertEquals(1, count()) bên trong test chưa chứng minh service tự commit.
}
```

Đoạn trên chỉ minh họa anti-pattern, **không phải một test đầy đủ**. Với Hibernate/JPA, cần `flush` đúng lúc để lỗi ràng buộc database xuất hiện trong test thay vì bị hoãn đến cuối transaction.

### 8.2. Gọi nội bộ và phương thức không được proxy

`this.saveWithNewTransaction()` trong cùng bean không đi qua proxy mặc định. Đặt `@Transactional(propagation = REQUIRES_NEW)` trên phương thức bị gọi nội bộ rồi kỳ vọng một transaction độc lập là sai. Tách hành vi cần transaction riêng sang **bean khác**, hoặc dùng `TransactionTemplate` khi cần điều khiển programmatic rõ ràng. Không dùng `@PostConstruct` để kiểm tra transaction proxy trước khi bean khởi tạo xong.

### 8.3. Bắt lỗi quá sớm hoặc đánh dấu rollback-only

`catch` và tiếp tục là quyết định nghiệp vụ; nó có thể khiến transaction vẫn commit. Nếu thật sự cần rollback sau khi xử lý lỗi, có thể **ném lại exception phù hợp**, đặt rollback rule, hoặc trong ca đặc biệt đánh dấu rollback-only qua `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`. Cách cuối ràng buộc code vào hạ tầng Spring và chỉ hợp lệ khi đang có transaction context do interceptor quản lý; không nên lạm dụng cho luồng bình thường.

### 8.4. Nhầm scope của propagation

- **`REQUIRED`**: scope con có thể tham gia cùng *physical transaction* với bên ngoài. Nếu inner scope đánh dấu rollback-only, outer không thể commit thành công dù đã bắt exception; có thể nhận `UnexpectedRollbackException`.
- **`REQUIRES_NEW`**: tạm treo transaction ngoài và mở physical transaction độc lập; inner commit có thể còn hiệu lực ngay cả khi outer rollback. Cần chú ý thêm connection trong pool.
- **`NESTED`**: dùng savepoint trong cùng physical transaction khi transaction manager và tài nguyên JDBC hỗ trợ; có thể rollback về savepoint mà không hủy toàn bộ công việc bên ngoài. Không giả định mọi JPA/JTA hoặc database đều hỗ trợ giống nhau.

Chỉ sau khi kiểm tra được `REQUIRED` cơ bản mới thêm test cho từng chính sách propagation, vì kết quả phụ thuộc quan hệ caller/inner, manager và database.

### 8.5. Nhầm `readOnly`, isolation hoặc cache với kết quả transaction

`@Transactional(readOnly = true)` chủ yếu là chỉ dẫn tối ưu hóa cho hạ tầng; **không mặc định là cơ chế chặn mọi lệnh ghi** ở mọi database/driver. `isolation` giúp điều chỉnh mức nhìn thấy dữ liệu đồng thời, không tự xử lý race condition nghiệp vụ. Với ORM, cache cấp một có thể trả về entity đang được quản lý; muốn chứng minh kết quả đã commit thì phải đọc ở ngữ cảnh có khả năng thấy dữ liệu bền vững sau transaction.

### 8.6. Ngoại tác không thuộc database

Rollback JDBC không thu hồi email đã gửi, thông báo đã đẩy lên message broker hay HTTP call đã trả thành công. Với nghiệp vụ có nhiều hệ thống, cân nhắc **transactional outbox**, idempotency và saga/compensation tùy nhu cầu. Chúng là bài tiếp theo, không phải một thuộc tính `@Transactional` có thể tự giải quyết.

## 9. Quan sát và chẩn đoán khi kết quả lệch dự đoán

Có thể bật log có chọn lọc trong môi trường thực nghiệm:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log có thể giúp tìm lúc bắt đầu/tham gia/kết thúc transaction và nơi rollback được quyết định; tên logger hoặc thông điệp chi tiết thay đổi theo transaction manager và phiên bản Spring. **Bằng chứng cuối cùng vẫn là trạng thái dữ liệu được truy vấn sau transaction**, không phải một dòng log kiểu "Executing rollback".

Nếu test thất bại, kiểm tra có hệ thống:

| Triệu chứng | Giả thuyết cần xác minh | Cách kiểm tra |
| --- | --- | --- |
| Ném runtime exception nhưng bản ghi vẫn còn | Lời gọi không qua proxy; ghi ngoài transaction; có transaction khác đã commit | Kiểm tra bean/call path, manager, SQL connection và commit trước đó |
| Checked exception nhưng bản ghi được giữ | Đây là mặc định, nếu chưa khai báo rollback rule | Thêm `rollbackFor` theo yêu cầu nghiệp vụ và so lại test |
| Test đọc thấy bản ghi nhưng môi trường khác không thấy | Test đang ở transaction riêng hoặc đang đọc persistence context | Đọc sau khi transaction hoàn thành, bằng truy vấn/ngữ cảnh độc lập |
| Outer bắt được lỗi nhưng vẫn không thể commit | Inner `REQUIRED` đã đánh dấu rollback-only | Tìm transaction tham gia và nguyên nhân `UnexpectedRollbackException` |
| Test chỉ fail khi chạy song song | Dữ liệu test/connection/schema dùng chung hoặc transaction đồng thời | Cô lập fixture, database và thời điểm quan sát |
| Lỗi ràng buộc chỉ xuất hiện ở cuối | JPA chưa flush, hoặc lỗi phát sinh khi commit | Chủ động flush ở điểm cần kiểm tra và kiểm thử sau boundary |

Tránh dùng debugger hoặc trace để suy ra atomicity khi test dữ liệu mâu thuẫn với suy luận: trước tiên xác minh mình đang quan sát **đúng database, đúng bản ghi, đúng transaction**.

## 10. Tiêu chí hoàn thành và hướng đi tiếp

Tự kiểm tra bằng ba câu hỏi:

1. Phương thức A lưu một hàng rồi ném `IOException`; vì sao mặc định dữ liệu có thể vẫn tồn tại? Thay đổi nhỏ nhất trong khai báo để rollback là gì?
2. Tại sao một test gắn `@Transactional` rồi `assertEquals(1, countRows())` **không đủ** để chứng minh service đã commit?
3. Tại sao outer `@Transactional` đã bắt exception của inner `REQUIRED` vẫn có thể nhận `UnexpectedRollbackException` khi kết thúc?

Đáp án đối chiếu: **(1)** checked exception không nằm trong rollback rule mặc định; dùng `rollbackFor = IOException.class` khi cần. **(2)** test có thể đang sở hữu transaction chưa commit và mặc định rollback cuối test. **(3)** inner scope tham gia cùng physical transaction đã đánh dấu rollback-only; outer không thể ghi đè quyết định đó bằng một commit.

Sau khi toàn bộ 5 integration test ở mục 6 pass và bạn giải thích được từng trạng thái `1/0`, hãy chuyển theo thứ tự: **propagation** (`REQUIRED` → `REQUIRES_NEW` → `NESTED` và savepoint), **isolation/concurrency**, **JPA flush và khóa**, **rollback khi qua nhiều tài nguyên**, cuối cùng **kiểm thử với database thật bằng Testcontainers**. Mỗi bước nên có ít nhất một ca commit thành công và một ca rollback hoặc failure path được xác minh.

### Tài liệu chính thức

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Management trong TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
