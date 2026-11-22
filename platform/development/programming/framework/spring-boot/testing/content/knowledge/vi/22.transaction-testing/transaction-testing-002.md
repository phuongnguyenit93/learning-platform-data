# @Transactional trên test và phạm vi rollback mặc định

## 1. Vấn đề: test chạy xanh nhưng dữ liệu đã được commit hay chưa?

Trong một ứng dụng Spring Boot, bạn có thể thêm `@Transactional` lên **phương thức nghiệp vụ** để quản lý transaction, hoặc thêm chính annotation đó lên **JUnit test class/test method** để tổ chức một *test-managed transaction*. Hai nơi dùng cùng annotation nhưng **vòng đời, chính sách commit/rollback và mục đích không giống nhau**.

Ví dụ quen thuộc:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void createsOrder() {
        jdbc.update(
                "insert into orders(code) values (?)",
                "ORDER-001");
        // Test kết thúc -> mặc định Spring TestContext rollback.
    }
}
```

Đây là **đoạn minh họa** (giả định bảng `orders` tồn tại và đã import các class). Nếu ứng dụng có `PlatformTransactionManager` phù hợp và Spring TestContext đang quản lý test, dữ liệu được thêm trong test transaction thường bị **rollback mặc định sau mỗi test method**. Vì thế, một câu INSERT trả thành công và một SELECT cùng transaction đọc được dòng mới **không chứng minh database đã commit**.

Điểm dễ gây lỗi hơn: từ test đó bạn chuyển sang gửi HTTP thật đến embedded server, gọi một service có `REQUIRES_NEW`, tạo thread phụ, hoặc dùng một hệ thống ngoài. Những thao tác đó có thể nằm **ngoài** test-managed transaction và được commit dù JUnit test sau đó rollback.

### Bạn sẽ học được

- Chính xác `@Transactional` trên test làm gì, khi nào Spring TestContext bắt đầu/kết thúc transaction.
- Rollback mặc định và cách thay đổi bằng `@Rollback`, `@Commit`, `TestTransaction`.
- Phân biệt test-managed transaction, Spring-managed service transaction và application-managed transaction.
- Tác động của `@BeforeTransaction`, `@BeforeEach`, `@AfterEach`, `@AfterTransaction`.
- Các giới hạn của `@Transactional` **trên test**: thuộc tính nào được listener dùng và thuộc tính nào không.
- Sự khác nhau giữa `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest`, `@DataR2dbcTest`.
- Vì sao thread khác, `@SpringBootTest(RANDOM_PORT)`, `REQUIRES_NEW` hoặc `@Sql(ISOLATED)` có thể để lại dữ liệu.
- Cách dùng Java 17+, Spring Boot 3.x, H2, JUnit Jupiter và JDBC để **đo trạng thái sau khi transaction kết thúc**.
- Cách tránh test xanh giả do JPA persistence context, SQL chưa flush, database isolation hoặc cleanup không đầy đủ.

**Trọng tâm:** Spring TestContext của Spring Framework 6.x / Spring Boot 3.x. Các ví dụ mã đầy đủ bên dưới dùng **Servlet MVC + JDBC/H2** để minh họa transaction boundary một cách trực tiếp, không cần production database. R2DBC/Reactive và Spring Boot 4.x được phân biệt riêng; không suy luận chúng có cùng quy trình rollback.

## 2. Ba loại transaction cần phân biệt

Spring Framework mô tả ba phạm vi thường gặp:

1. **Test-managed transaction:** do `TransactionalTestExecutionListener` của Spring TestContext tạo cho một test method, thường rollback sau test.
2. **Spring-managed transaction:** do Spring transaction AOP/interceptor quản lý khi gọi bean/method `@Transactional`, với các chính sách propagation và rollback của application.
3. **Application-managed transaction:** do code chủ động mở/kết thúc, ví dụ `TransactionTemplate` hoặc APIs transaction manager.

Chúng có thể **tham gia cùng database transaction** khi dùng cùng resource/manager và propagation tương thích; nhưng không mặc định là một transaction cho mọi tác động.

```text
SpringExtension / TestContext
    |
    +-- TransactionalTestExecutionListener
    |      |
    |      +-- BEGIN test-managed transaction (thread test)
    |      |
    |      +-- @BeforeEach
    |      +-- @Test
    |      |     |
    |      |     +-- JdbcTemplate JDBC operation
    |      |     +-- @Transactional service (REQUIRED)
    |      |     +-- @Transactional service (REQUIRES_NEW) [khác tx!]
    |      |
    |      +-- @AfterEach
    |      |
    |      +-- ROLLBACK (mặc định) / COMMIT (nếu yêu cầu)
    |
    +-- @AfterTransaction (ngoài transaction)
```

Với JDBC transaction thông thường, Spring giữ transaction state trên **thread hiện tại** (qua ThreadLocal). Khi một service `@Transactional(propagation=REQUIRED)` được gọi từ test thread trong cùng datasource/manager, nó có thể tham gia test transaction đó. Nếu service dùng `REQUIRES_NEW`, Spring có thể tạm ngưng transaction đang có và **mở một transaction độc lập**, commit hoặc rollback theo chính nó.

### 2.1. Test-managed rollback không đồng nghĩa production service rollback

Ở production, một service `@Transactional` thông thường **commit khi method hoàn tất thành công** và rollback khi exception khớp rollback rules hoặc transaction được đánh dấu rollback-only.

Trên JUnit test, `@Transactional` kết hợp Spring TestContext tạo một transaction có **chính sách rollback cuối test mặc định**, ngay cả khi method test không ném lỗi. Lý do là test cần cô lập dữ liệu để chạy lại.

| Trường hợp | Quyết định cuối transaction |
|---|---|
| JUnit test `@Transactional`, không ghi đè | Spring TestContext **rollback mặc định** |
| Test `@Transactional @Commit` | Spring TestContext **cố commit** transaction khi kết thúc test |
| Test `@Transactional @Rollback(false)` | Tương đương yêu cầu không rollback mặc định, tức **commit** |
| Test `@Transactional @Rollback(true)` | Yêu cầu rollback, cũng là mặc định |
| Service production `@Transactional(REQUIRED)` bên trong test tx | Thường tham gia transaction test; cuối test rollback |
| Service `@Transactional(REQUIRES_NEW)` bên trong test tx | Transaction độc lập, có thể **commit** và sống sót sau test rollback |
| HTTP request tới `RANDOM_PORT` | Xử lý ở server thread/transaction khác; test rollback không tự rollback server |
| JDBC operation bên ngoài test-managed transaction | Theo service manager hoặc JDBC auto-commit, không được listener rollback tự động |

**Lưu ý:** một yêu cầu `@Commit` không bảo đảm commit thành công nếu database exception, rollback-only flag hoặc lỗi transaction xảy ra. Tốt nhất xác minh dữ liệu sau boundary bằng một query khác.

### 2.2. “Trong cùng transaction” phải bao gồm connection, manager và thread

Một lần kiểm tra:

```java
jdbc.update("insert into ledger_entries(code, amount) values (?, ?)",
        "T-1", 100);
assertThat(count("T-1")).isEqualTo(1);
```

chỉ chứng minh INSERT và SELECT mà test dùng nhìn thấy dữ liệu **trong ngữ cảnh truy cập hiện tại**. Nếu cả hai cùng tham gia test transaction, chúng có thể nhìn thấy dữ liệu chưa commit. Muốn chứng minh rollback/commit, hãy kiểm tra ở **sau khi transaction test kết thúc**, như qua `@AfterTransaction` hoặc `TestTransaction.end()` rồi query lại.

Đừng coi `count=1` bên trong test là bằng chứng “dữ liệu đã persisted vĩnh viễn”. Cũng đừng coi một entity JPA có ID là bằng chứng transaction đã commit.

## 3. Spring TestContext kích hoạt @Transactional trên test thế nào?

### 3.1. TransactionalTestExecutionListener

Spring TestContext có `TransactionalTestExecutionListener`, mặc định tham gia bộ test listeners theo cấu hình thông thường. Để một JUnit test chạy trong transaction, cần:

- Tạo Spring TestContext (ví dụ `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest` hoặc `@SpringJUnitConfig`).
- Có bean `PlatformTransactionManager` phù hợp trong `ApplicationContext`.
- Khai báo Spring `org.springframework.transaction.annotation.Transactional` trên test method hoặc class, **hoặc** dùng một test slice đã meta-annotated transactional.
- Test execution được SpringExtension/TestContext quản lý; không chỉ chạy một class JUnit thuần không có Spring extension.
- Không cố ý tắt test transaction bằng propagation đặc biệt.

**Không cần** thêm `@ExtendWith(SpringExtension.class)` thủ công khi đang dùng những annotation Spring Boot test đã tích hợp SpringExtension.

### 3.2. Import đúng @Transactional

Với Spring Framework 6.x/Spring Boot 3.x:

```java
import org.springframework.transaction.annotation.Transactional;
```

Bài này dùng **Spring @Transactional**, không phải tự động đồng nhất với mọi annotation giao dịch từ `jakarta.transaction.*` hoặc annotations do framework khác cung cấp. TestContext transaction listener nhận diện/diễn giải các annotation mà nó hỗ trợ. Nếu dùng nhiều transaction annotations/managers, kiểm tra tài liệu của nhánh đang dùng.

### 3.3. Có nhiều PlatformTransactionManager thì sao?

Nếu ứng dụng có nhiều database hoặc nhiều manager, một test có thể không chọn được manager mong muốn. Nêu rõ:

```java
@Transactional(transactionManager = "ordersTransactionManager")
class OrdersTransactionTest {
    // ...
}
```

Đây là đoạn minh họa: bean tên `ordersTransactionManager` phải thật sự tồn tại, có datasource/repository đúng và đủ khả năng quản lý các thao tác đang test.

**Không** suy luận chỉ vì transaction active mà tất cả JDBC/JPA/Redis/Kafka/HTTP resources đều nằm trong cùng giao dịch. Việc đồng bộ các resources cần cấu hình/transaction architecture thích hợp.

### 3.4. @SpringBootTest không mặc định mở test transaction

```java
@SpringBootTest
class PlainIntegrationTest {
    @Test void example() {
        // Không có test-managed tx chỉ nhờ @SpringBootTest.
    }
}
```

Đây là snippet minh họa. Trong một full-context test, nếu bạn cần rollback tự động, phải khai báo `@Transactional` lên test hoặc class, hoặc dùng một cấu hình khác tạo test-managed transaction có chủ đích.

Ngược lại, nhiều test slices **đã có chính sách transactional**, dù bạn không đặt `@Transactional` trực tiếp.

## 4. Những annotation test phổ biến và rollback mặc định

| Test style trên Spring Boot 3.x | Transaction mặc định? | Ghi chú |
|---|---|---|
| `@SpringBootTest` | Không do annotation này tự kích hoạt | Thêm `@Transactional` khi cần test-managed tx |
| `@JdbcTest` | **Có**, rollback cuối mỗi test | Dành cho JDBC, `JdbcTemplate`, DataSource |
| `@DataJdbcTest` | **Có**, rollback cuối mỗi test | Dành cho Spring Data JDBC repository/aggregate |
| `@DataJpaTest` | **Có**, rollback cuối mỗi test | Dành cho JPA repository/entity, có persistence context |
| `@JooqTest` | **Có**, rollback mặc định | Dành cho jOOQ, dùng đúng DataSource/manager |
| `@DataR2dbcTest` | **Không có test-managed reactive transaction mặc định** | R2DBC cần quản lý Publisher + ReactiveTransactionManager |
| `@WebMvcTest` | Không mặc nhiên là JPA/JDBC transactional test | Thường chỉ nạp web slice; đừng suy đoán có manager |
| JUnit thuần, không Spring TestContext | Không | `@Transactional` không tự biến Java class thành Spring bean/proxy |

Dù một slice có auto rollback, thao tác chạy trong **service transaction khác**, trong thread khác hoặc kết nối khác vẫn có thể commit. Ngược lại, `@SpringBootTest` với test-managed tx có thể cho cảm giác “mọi service luôn rollback” dù production behavior khác.

### 4.1. Vì sao @DataJpaTest thường không cần @Transactional tường minh?

Theo Spring Boot 3.5, `@DataJpaTest` được thiết kế để kiểm tra JPA repositories trong môi trường cách ly, mặc định transactional và rollback. Viết:

```java
@DataJpaTest
class ProductRepositoryTest {
    @Autowired ProductRepository repository;

    @Test
    void savesProduct() {
        // Có test-managed tx trong cấu hình mặc định.
    }
}
```

đã đủ để sử dụng rollback mặc định (snippet giả định repository có thật). Thêm `@Transactional` có thể giúp người đọc thấy rõ ý định, nhưng không nên nghĩ nó đang “bật một tính năng thiếu” ở default slice.

Trong JPA, **flush chưa commit**: để phát hiện constraint violation hoặc listener/mapping error, đôi khi cần `entityManager.flush()` hoặc `repository.flush()` trong test. Nếu không flush mà test rollback, các lỗi chỉ xuất hiện khi SQL được gửi có thể không bị phát hiện.

### 4.2. Đừng chuyển thói quen sang @DataR2dbcTest

`@DataR2dbcTest` của Spring Boot 3.x **không tự rollback mỗi test**. Một Publisher ghi dữ liệu có thể được subscribe và commit ngoài transaction nếu bạn không bọc nó bằng `TransactionalOperator` hoặc proxied reactive `@Transactional` phù hợp. `@Transactional` trên JUnit test method kiểu `void` không tự tạo một Reactor transaction cho mọi Publisher của test.

Bài này tập trung imperative test-managed tx; reactive transaction phải được kiểm tra qua **Publisher/subscription và Reactor Context**, không giả lập ThreadLocal rollback.

## 5. Vòng đời một phương thức test transactional

Spring TestContext tổ chức các giai đoạn sau:

```text
@BeforeAll                       (không thuộc test-managed tx)
  |
@BeforeTransaction               (ngoài transaction)
  |
BEGIN test-managed transaction
  |
@BeforeEach                      (trong transaction)
  |
@Test                            (trong transaction)
  |
@AfterEach                       (trong transaction)
  |
ROLLBACK mặc định / COMMIT nếu cấu hình
  |
@AfterTransaction                (ngoài transaction)
  |
@AfterAll                        (không thuộc test-managed tx)
```

Sơ đồ theo trường hợp JUnit Jupiter/SpringExtension thông thường. `@BeforeTransaction` và `@AfterTransaction` **chỉ chạy cho transactional test methods**. Nếu method bị `Propagation.NOT_SUPPORTED` hoặc `NEVER`, TestContext không mở test-managed transaction cho method đó, nên các callback before/after-transaction tương ứng không áp dụng.

### 5.1. @BeforeEach và @AfterEach ở bên trong transaction

Khi một test method được TestContext quản lý transaction:

- `@BeforeEach` setup fixture có thể INSERT dữ liệu trong chính transaction test.
- `@Test` được chạy sau setup.
- `@AfterEach` thường cũng chạy **trước rollback/commit**, do đó vẫn có thể đọc dữ liệu trong transaction.
- Sau đó TestContext rollback mặc định.

Vì thế nếu bạn muốn test “sau rollback có còn row không”, **đừng đặt assertion ấy trong `@AfterEach`**. Sử dụng `@AfterTransaction` hoặc `TestTransaction.end()` rồi thực hiện query ngoài transaction đã kết thúc.

### 5.2. @BeforeTransaction và @AfterTransaction

Spring hỗ trợ:

```java
@BeforeTransaction
void beforeTransaction() {
    // Verify committed baseline/fixtures ngoài test transaction.
}

@AfterTransaction
void afterTransaction() {
    // Verify state ngoài test transaction sau rollback/commit.
}
```

Đây là snippet lifecycle, không phải file runnable độc lập. Với JUnit Jupiter/SpringExtension trên Spring Framework 6.1+, một số arguments có thể được resolver inject; code sample của bài dùng zero-argument methods để tương thích và dễ hiểu.

Hai hook này đặc biệt hữu ích:

- Xác nhận baseline không có dữ liệu trước khi test bắt đầu.
- Chứng minh dữ liệu được rollback sau method.
- Chứng minh `@Commit` khiến dữ liệu vẫn còn sau test.
- Xóa có kiểm soát dữ liệu đã commit trong các test thử transaction boundary.

Không nên tạo fixture production-like nhạy cảm trong các hook; dùng dữ liệu giả và isolated database.

### 5.3. @BeforeAll không tự nằm trong test transaction

Nếu tạo fixture bằng `@BeforeAll`, đừng mong rollback của từng test xóa fixture ấy. `@BeforeAll` chạy ngoài test-managed transaction tương ứng với từng method; có thể cần `TransactionTemplate` nếu bạn muốn tổ chức transaction riêng trong class-level setup.

Tương tự, `@AfterAll` không phải nơi được TestContext tự rollback theo transaction của một test method đã kết thúc.

## 6. @Rollback, @Commit và TestTransaction

### 6.1. @Rollback(true): explicit nhưng thường không cần

```java
@Test
@Transactional
@Rollback
void rollbackAtEnd() {
    // @Rollback mặc định value=true.
}
```

Trong Spring Test, nếu `@Transactional` đã có và không cấu hình gì khác, rollback đã là mặc định. `@Rollback(true)` có thể được viết để ghi rõ ý định hoặc ghi đè một `@Commit` ở mức class.

### 6.2. @Rollback(false): yêu cầu commit

```java
@Test
@Transactional
@Rollback(false)
void commitAtEnd() {
    // Test transaction sẽ được commit khi test kết thúc,
    // nếu không bị rollback-only hoặc lỗi transaction.
}
```

`@Rollback(false)` **không** đổi mọi service method thành `REQUIRES_NEW`; nó chỉ thay **chính sách kết thúc test-managed transaction**. Cần cleanup dữ liệu đã commit nếu database được dùng lại giữa tests.

### 6.3. @Commit: cách viết ngắn của @Rollback(false)

```java
@Test
@Transactional
@Commit
void commitsTestTransaction() {
    // Tương đương yêu cầu @Rollback(false).
}
```

Nếu `@Commit` ở class level, method-level `@Rollback` có thể ghi đè để yêu cầu rollback riêng. Annotation method có mức ưu tiên thích hợp so với class-level default; đừng đặt đồng thời `@Commit` và `@Rollback` mâu thuẫn trên cùng element.

### 6.4. TestTransaction: điều khiển transaction đang chạy

Spring Test có helper `org.springframework.test.context.transaction.TestTransaction`:

| Phương thức | Ý nghĩa |
|---|---|
| `isActive()` | Có test-managed transaction đang active trên thread hiện tại? |
| `isFlaggedForRollback()` | Transaction hiện tại dự kiến rollback khi kết thúc? |
| `flagForRollback()` | Đánh dấu current test-managed transaction rollback khi kết thúc |
| `flagForCommit()` | Đánh dấu current test-managed transaction commit khi kết thúc |
| `end()` | Kết thúc ngay transaction test hiện tại theo flag |
| `start()` | Mở transaction test mới, khi không có test transaction active |

**Điểm cần nhớ:** `flagForRollback()` và `flagForCommit()` chỉ đặt **ý định**, không tự commit/rollback ngay. `end()` mới kết thúc transaction. Sau `end()`, bạn có thể mở `start()` để tiếp tục test trong transaction mới; việc start phải theo điều kiện test-managed transaction được Spring cấu hình.

Ví dụ minh họa:

```java
assertThat(TestTransaction.isActive()).isTrue();
TestTransaction.flagForRollback();
TestTransaction.end();
assertThat(TestTransaction.isActive()).isFalse();
// Thực hiện query để thấy trạng thái sau rollback.
TestTransaction.start();
// Transaction test mới active; cuối test rollback theo policy.
```

Dùng TestTransaction trong code **kiểm thử**, không phải trong service production. Nếu dùng `flagForCommit()` rồi kết thúc, có thể để lại dữ liệu thật trên test database; cần cleanup rõ ràng.

### 6.5. Đừng nhầm annotation rollbackFor với TestContext rollback rule

Một khác biệt dễ bỏ sót từ tài liệu Spring Framework 6.2:

**Test-managed transactions không hỗ trợ toàn bộ thuộc tính của @Transactional như service transaction.**

| Thuộc tính `@Transactional` trên test | TestContext listener có dùng cho test-managed transaction? |
|---|---|
| `value` / `transactionManager` | **Có**, chọn transaction manager |
| `propagation` | Chỉ xử lý tường minh `NOT_SUPPORTED` và `NEVER` để **không mở** test-managed transaction |
| `isolation` | **Không** áp như bạn tưởng ở listener |
| `timeout` | **Không** áp như bạn tưởng ở listener |
| `readOnly` | **Không** áp như bạn tưởng ở listener |
| `rollbackFor` / `rollbackForClassName` | **Không**; dùng TestTransaction/@Rollback |
| `noRollbackFor` / `noRollbackForClassName` | **Không**; dùng TestTransaction/@Commit |

Đừng viết:

```java
@Transactional(noRollbackFor = IllegalArgumentException.class)
@Test
void shouldCommitAfterException() {
    throw new IllegalArgumentException("invalid");
}
```

rồi nghĩ Spring Test sẽ tự commit vì `noRollbackFor`. Đây là **phản ví dụ**: test-managed rollback policy khác declarative service rollback rules. Với test transaction, dùng `@Commit`/`@Rollback(false)` hoặc `TestTransaction.flagForCommit()` theo mục tiêu, và kiểm tra transaction status thực tế. Một assertion failure của JUnit cũng không biến rollback mặc định thành commit.

Nếu cần test isolation/timeout/readOnly như **service policy**, hãy kiểm thử một Spring bean có `@Transactional` thật với manager phù hợp, thay vì suy đoán những attributes trên JUnit test annotation đã được listener áp dụng.

## 7. Ví dụ runnable Java 17+ / Spring Boot 3.x với JDBC và H2

Ta dùng cùng một application nhỏ có:

- Một bảng SQL `ledger_entries`.
- `JdbcTemplate` cho các SELECT/INSERT/DELETE kiểm tra được.
- Service có method `@Transactional(REQUIRED)` và method `@Transactional(REQUIRES_NEW)`.
- HTTP endpoint cho phép quan sát khác biệt server thread với test-managed thread.
- **Năm test classes, sáu phương thức @Test**. Mỗi test có một mã key riêng để tránh xung đột.
- Một database H2 in-memory được cấu hình **chỉ cho test**, không dùng DB production.
- Fixture đã commit được cleanup ngay sau test; fixture thuộc rollback transaction không cần giữ lại.

**Môi trường:** Spring Boot **3.x** (ví dụ Boot 3.5), Java 17+, Spring JDBC, Spring MVC, JUnit Jupiter, H2. Mẫu dùng import Boot 3.x; Boot 4 có một số package/starter khác, cần đối chiếu theo BOM khi migrate.

### 7.1. Build dependencies

**Gradle Groovy DSL:** trích đoạn của `build.gradle` đã có Spring Boot plugin, repositories, dependency management và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven:** trích đoạn dependencies của `pom.xml` đã có Spring Boot parent/BOM, compiler Java 17 và Surefire hỗ trợ JUnit Platform:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **snippets**, không phải build files hoàn chỉnh. Không thêm trực tiếp Spring/H2 versions nếu Boot BOM đã quản lý. Dùng wrapper của project thay vì lệnh build tool version khác trong CI.

### 7.2. Cấu trúc tệp

```text
src/
├── main/java/com/example/testtx/
│   ├── TestTxApplication.java
│   ├── LedgerService.java
│   └── LedgerController.java
└── test/
    ├── java/com/example/testtx/
    │   ├── RollbackLifecycleTest.java
    │   ├── CommitOverrideTest.java
    │   ├── TestTransactionBoundaryTest.java
    │   ├── RequiresNewBoundaryTest.java
    │   └── RealHttpRollbackBoundaryTest.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

Các class trong cùng package giúp Spring Boot tìm configuration qua `@SpringBootApplication`; mỗi lớp test sử dụng `@SpringBootTest(classes = TestTxApplication.class)` để chỉ rõ application.

### 7.3. Application entry point

**File `src/main/java/com/example/testtx/TestTxApplication.java`:**

```java
package com.example.testtx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestTxApplication.class, args);
    }
}
```

Class này dùng component scan mặc định. Không khai báo thủ công PlatformTransactionManager; Spring Boot có thể auto-configure JDBC transaction manager khi có một DataSource hợp lệ và transaction infrastructure trên classpath.

### 7.4. Service thật — REQUIRED và REQUIRES_NEW

**File `src/main/java/com/example/testtx/LedgerService.java`:**

```java
package com.example.testtx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {

    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeRequired(String code) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 1);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeRequiresNew(String code) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 1);
    }
}
```

Hai method thực hiện cùng loại INSERT, khác **transaction propagation**.

- `writeRequired(...)` mặc định `Propagation.REQUIRED`: khi gọi trong test-managed transaction cùng manager/resource, thường **tham gia transaction test**. Khi gọi từ server thread không có transaction, Spring tạo transaction mới và commit khi method kết thúc thành công.
- `writeRequiresNew(...)`: tạm ngưng transaction hiện tại (nếu có), tạo transaction riêng. Nếu method hoàn thành thành công, giao dịch riêng có thể được commit **trước khi** JUnit test transaction rollback.
- Cả hai public methods được gọi từ **Spring-managed bean proxy** trong ví dụ. Nếu tự tạo service bằng `new` hoặc self-invoke `this.writeRequiresNew(...)` trong cùng instance, proxy semantics sẽ khác.

**Không đưa method này vào repository mock** nếu bạn muốn thật sự kiểm chứng transaction/DB. Ví dụ dùng JDBC/H2 thật để quan sát dữ liệu sau transaction.

### 7.5. HTTP controller dùng service REQUIRED

**File `src/main/java/com/example/testtx/LedgerController.java`:**

```java
package com.example.testtx;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ledger")
public class LedgerController {

    private final LedgerService service;

    public LedgerController(LedgerService service) {
        this.service = service;
    }

    @PostMapping("/{code}")
    @ResponseStatus(HttpStatus.CREATED)
    public void add(@PathVariable String code) {
        service.writeRequired(code);
    }
}
```

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP request đi qua embedded server và gọi service từ server thread. Giao dịch được mở cho `writeRequired(...)` trong **server thread**, không tự tham gia transaction gắn trên JUnit test thread. Controller trả 201 khi service thành công.

### 7.6. H2 schema riêng cho tests

**File `src/test/resources/schema.sql`:**

```sql
CREATE TABLE IF NOT EXISTS ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

Cú pháp `IF NOT EXISTS` được dùng cho H2 để script idempotent khi Spring khởi tạo nhiều test application contexts cùng trỏ tới named in-memory database. Không mặc định copy SQL này sang mọi RDBMS mà không kiểm tra cú pháp/DDL semantics.

**File `src/test/resources/application.properties`:**

```properties
spring.datasource.url=jdbc:h2:mem:test_transaction_boundary;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

File properties chỉ có trong **test resources**. Named H2 in-memory DB giúp hai Spring test contexts trong cùng JVM có thể dùng lại schema; mọi test dùng code riêng và những rows đã commit được dọn ngay.

**Quan trọng:** `DB_CLOSE_DELAY=-1` có nghĩa H2 giữ named memory database trong vòng đời JVM, do đó cleanup/isolated keys càng quan trọng. Nếu CI chạy parallel tests hoặc context lifecycle khác, dùng database/schema riêng từng worker thay vì dựa vào test order.

### 7.7. Test 1 — @BeforeEach/@AfterEach bên trong rollback transaction

**File `src/test/java/com/example/testtx/RollbackLifecycleTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class RollbackLifecycleTest {

    private static final String CODE = "TEST-LIFECYCLE";

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(count()).isZero();
    }

    @BeforeEach
    void setUpInsideTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                CODE, 10);
        assertThat(count()).isEqualTo(1);
    }

    @Test
    void defaultRollbackIsScheduledForThisTest() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count()).isEqualTo(1);
    }

    @AfterEach
    void afterEachStillRunsInsideTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void afterTransactionSeesRolledBackState() {
        assertThat(count()).isZero();
    }
}
```

**Kỳ vọng:** một test pass. Vòng đời:

1. `@BeforeTransaction`: chưa mở transaction test; database chưa có key `TEST-LIFECYCLE`.
2. `@BeforeEach`: đã ở trong test transaction; INSERT, SELECT thấy 1.
3. `@Test`: `TestTransaction.isFlaggedForRollback() == true`; count vẫn 1.
4. `@AfterEach`: vẫn ở transaction, nên count vẫn 1.
5. Spring TestContext rollback transaction.
6. `@AfterTransaction`: query ngoài transaction vừa kết thúc, count trở lại 0.

**Đây là cách chứng minh rollback chính xác hơn** việc chỉ assert dữ liệu ở `@Test` hoặc `@AfterEach`. Không cần gọi manual delete ở đây vì fixture được tạo trong transaction đã rollback.

### 7.8. Test 2 — @Commit ghi đè rollback mặc định, phải cleanup

**File `src/test/java/com/example/testtx/CommitOverrideTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class CommitOverrideTest {

    private static final String CODE = "TEST-COMMIT";

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @Test
    @Commit
    void commitOverridesTheDefaultRollback() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isFalse();

        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                CODE, 20);

        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void verifyCommittedRowAndCleanItUp() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Kỳ vọng:** một test pass. `@Commit` trên method là yêu cầu **commit test-managed transaction**. `@AfterTransaction` đọc được row ở một operation khác sau boundary, sau đó xóa row trong `finally` để không ảnh hưởng các test tiếp theo.

Nếu bạn bỏ cleanup, dữ liệu `TEST-COMMIT` vẫn tồn tại trong named H2 database cho đến khi DB được hủy; trong một dự án dùng database persistent/shared, nó còn gây vấn đề nghiêm trọng hơn.

Nếu DB constraint hoặc transaction error khiến commit thất bại, đừng báo test thành công chỉ vì `@Commit` có mặt. Đây là lý do test có assertion sau transaction.

### 7.9. Test 3 — TestTransaction.end/start và NOT_SUPPORTED

**File `src/test/java/com/example/testtx/TestTransactionBoundaryTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class TestTransactionBoundaryTest {

    @Autowired
    JdbcTemplate jdbc;

    private int count(String code) {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, code);
    }

    @Test
    void canEndWithRollbackThenStartAnotherTestTransaction() {
        String code = "TEST-EXPLICIT-ROLLBACK";

        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 30);

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count(code)).isEqualTo(1);

        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(count(code)).isZero();

        TestTransaction.start();

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count(code)).isZero();
        // Transaction mới sẽ rollback khi test kết thúc.
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void notSupportedDisablesTestManagedTransaction() {
        String code = "TEST-NOT-SUPPORTED";

        assertThat(TestTransaction.isActive()).isFalse();

        try {
            jdbc.update(
                    "insert into ledger_entries(code, amount) values (?, ?)",
                    code, 40);

            // Không có outer test-managed transaction.
            // H2 JDBC statement autocommit theo cấu hình này.
            assertThat(count(code)).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    code);
        }

        assertThat(count(code)).isZero();
    }
}
```

**Kỳ vọng:** hai tests pass, tổng của ví dụ tới đây là bốn tests.

Ở method thứ nhất, `TestTransaction.end()` kết thúc ngay transaction ban đầu theo flag rollback. Một SELECT sau `end()` thấy row đã biến mất. `TestTransaction.start()` tạo test-managed transaction mới theo default rollback policy để test kết thúc bình thường.

Ở method thứ hai, class có `@Transactional` nhưng annotation method-level với `Propagation.NOT_SUPPORTED` làm listener **không mở test-managed transaction** cho method đó. Lệnh SQL chạy theo datasource/JDBC autocommit trong cấu hình H2 sample; do vậy phải cleanup bằng `finally`. Không coi NOT_SUPPORTED là một “transaction sẽ rollback cuối test”.

**Cẩn thận:** `Propagation.NEVER` cũng nằm trong các giá trị khiến TestContext không mở test-managed transaction, nhưng đó không cho phép bạn suy đoán tất cả propagation attributes trên test được áp dụng như trên service method. Khi cần kiểm tra `REQUIRES_NEW`, hãy đặt nó lên **Spring service bean** và gọi qua proxy như test kế tiếp.

### 7.10. Test 4 — REQUIRES_NEW có thể commit dù test sẽ rollback

**File `src/test/java/com/example/testtx/RequiresNewBoundaryTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class RequiresNewBoundaryTest {

    private static final String CODE = "TEST-REQUIRES-NEW";

    @Autowired
    LedgerService service;

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(count()).isZero();
    }

    @Test
    void nestedNewTransactionCanCommitIndependently() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        service.writeRequiresNew(CODE);

        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void committedInnerRowSurvivesOuterRollback() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Kỳ vọng:** một test pass. Đây là minh họa của **transaction propagation khác REQUIRED**, không phải lời khuyên sử dụng `REQUIRES_NEW` khắp nơi.

Timeline:

```text
JUnit test thread:
  BEGIN TX-TEST (rollback by default)
  |
  +-- call Spring proxy LedgerService.writeRequiresNew()
        SUSPEND TX-TEST
        BEGIN TX-INNER
        INSERT TEST-REQUIRES-NEW
        COMMIT TX-INNER
        RESUME TX-TEST
  |
  SELECT sees committed row (H2 READ_COMMITTED)
  ROLLBACK TX-TEST
  |
  @AfterTransaction:
      row vẫn tồn tại -> delete cleanup
```

**Hậu quả thực tế:** một transactional test có thể để lại database rows nếu service dùng `REQUIRES_NEW`, kể cả khi test tự báo rollback và tất cả assertions xanh. Cần cleanup hoặc test database/schema riêng.

Trường hợp service dùng transaction manager/datasource khác còn phức tạp hơn; mã sample dùng một DataSource và một manager để chỉ minh họa propagation.

### 7.11. Test 5 — HTTP thật không nằm trong rollback của JUnit test

**File `src/test/java/com/example/testtx/RealHttpRollbackBoundaryTest.java`:**

```java
package com.example.testtx;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = TestTxApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpRollbackBoundaryTest {

    private static final String CODE = "TEST-HTTP-SERVER";

    @LocalServerPort
    int port;

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @Test
    void realHttpServerWorkDoesNotJoinTestThreadTransaction()
            throws Exception {

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(port).isGreaterThan(0);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(
                        "http://127.0.0.1:" + port
                        + "/api/ledger/" + CODE))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void serverCommittedRowSurvivesTestRollback() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Kỳ vọng:** một test pass; tổng **6 JUnit tests** của ví dụ.

Mặc dù JUnit test có `@Transactional` và rollback cuối method, HTTP client gửi request tới embedded server đang lắng nghe cổng ngẫu nhiên, server xử lý request trên thread khác, gọi `LedgerService.writeRequired(...)` ở server thread và **commit theo service transaction**. Rollback của JUnit test thread **không tự hoàn tác** row do server đã commit.

`@AfterTransaction` chứng minh row vẫn còn sau test rollback và dọn nó. Đây là điểm rất quan trọng khi chuyển từ `mockMvc.perform(...)` sang live HTTP tests.

**Giới hạn:** sample chạy HTTP loopback/H2; nó chưa chứng minh proxy/TLS, multi-instance routing hay production DB isolation. Nếu có Spring Security hoặc filters khác trong project thật, cần gửi credentials/CSRF phù hợp. Test không cố ý log secret hoặc gọi production endpoints.

## 8. Chạy bộ ví dụ và đọc kết quả

### 8.1. Gradle (Linux/macOS)

```bash
./gradlew test --tests "com.example.testtx.RollbackLifecycleTest"
./gradlew test --tests "com.example.testtx.CommitOverrideTest"
./gradlew test --tests "com.example.testtx.TestTransactionBoundaryTest"
./gradlew test --tests "com.example.testtx.RequiresNewBoundaryTest"
./gradlew test --tests "com.example.testtx.RealHttpRollbackBoundaryTest"

# Hoặc chạy tất cả test của module:
./gradlew test
```

### 8.2. Maven (Linux/macOS)

```bash
./mvnw -Dtest=RollbackLifecycleTest test
./mvnw -Dtest=CommitOverrideTest test
./mvnw -Dtest=TestTransactionBoundaryTest test
./mvnw -Dtest=RequiresNewBoundaryTest test
./mvnw -Dtest=RealHttpRollbackBoundaryTest test

# Hoặc chạy toàn bộ module:
./mvnw test
```

### 8.3. Windows PowerShell

```powershell
.\gradlew.bat test --tests "com.example.testtx.RollbackLifecycleTest"
.\gradlew.bat test --tests "com.example.testtx.CommitOverrideTest"
.\gradlew.bat test --tests "com.example.testtx.TestTransactionBoundaryTest"
.\gradlew.bat test --tests "com.example.testtx.RequiresNewBoundaryTest"
.\gradlew.bat test --tests "com.example.testtx.RealHttpRollbackBoundaryTest"

# Nếu dùng Maven Wrapper:
.\mvnw.cmd "-Dtest=RollbackLifecycleTest" test
.\mvnw.cmd "-Dtest=CommitOverrideTest" test
.\mvnw.cmd "-Dtest=TestTransactionBoundaryTest" test
.\mvnw.cmd "-Dtest=RequiresNewBoundaryTest" test
.\mvnw.cmd "-Dtest=RealHttpRollbackBoundaryTest" test
```

Chỉ chạy lệnh tương ứng build system của dự án; wrapper có sẵn và test platform phù hợp là điều kiện cần. **Không trộn lệnh Gradle/Maven trong một module không hỗ trợ cả hai**. Không cần đặt cổng 8080 cố định vì test real HTTP dùng RANDOM_PORT.

**Kết quả mong đợi theo thiết kế:** 6/6 JUnit methods thành công, các callbacks @AfterTransaction hoàn tất. Source không chủ động in stdout; log khởi động Spring, SQL initialization và summary phụ thuộc IDE/Gradle/Maven/version. Đọc test report để xác nhận tests thực sự được chạy (không skipped, excluded hoặc cached giả).

### 8.4. Ma trận từng test và trạng thái database sau boundary

| Test | Trong test method | Sau transaction | Cleanup |
|---|---|---|---|
| `RollbackLifecycleTest` | Count = 1, rollback flag true | Count = 0 | Không cần, rollback |
| `CommitOverrideTest` | Count = 1, commit flag | Count = 1 | @AfterTransaction xóa |
| `TestTransactionBoundaryTest.canEnd...` | Count = 1 trước `end()` | Count = 0 sau `end()` | Không cần |
| `TestTransactionBoundaryTest.notSupported...` | Không có test tx; count = 1 | Không có rollback listener | `finally` xóa |
| `RequiresNewBoundaryTest` | Inner tx commit, count = 1 | Outer test rollback, count vẫn 1 | @AfterTransaction xóa |
| `RealHttpRollbackBoundaryTest` | Server tx commit, count = 1 | Test thread rollback, count vẫn 1 | @AfterTransaction xóa |

Các trạng thái là **kỳ vọng trong môi trường H2 được cấu hình**; nếu project thật dùng isolation khác hoặc tác vụ chạy song song, phải xác minh transaction visibility trước khi cứng hóa assertion.

## 9. Khi @Transactional trên test tạo test xanh giả

### 9.1. Service vô tình dựa vào transaction của test

Một service production không có `@Transactional` có thể gọi hai repository operations. Trong `@DataJpaTest @Transactional`, các thao tác đó vô tình chạy trong transaction bao ngoài của test. Test pass, nhưng ở production mỗi repository method có thể dùng transaction riêng và không bảo đảm atomicity toàn bộ nghiệp vụ.

Phản mẫu về kết luận:

```java
@DataJpaTest
@Transactional
class TransferRepositoryTest {
    @Test
    void transferIsAtomic() {
        // Gọi hai repository methods ở đây và thấy cùng rollback
        // không chứng minh production service tạo đúng transaction.
    }
}
```

Đây là **snippet cảnh báo**, không phải chương trình chạy độc lập. Muốn chứng minh service transaction boundary, test qua **Spring-managed service bean/proxy** trong môi trường có application transaction infrastructure và tạo tình huống một operation lỗi sau operation khác. Cần quan sát state sau service transaction, không chỉ dựa vào outer test-managed transaction.

### 9.2. JPA có thể chưa flush SQL trước khi test rollback

Với JPA, `repository.save(entity)` hoặc việc sửa managed entity có thể mới thay đổi persistence context. Hibernate thường flush pending SQL trước commit hoặc query cần đồng bộ, nhưng **test rollback có thể không flush mọi thay đổi**. Một test không gọi flush có thể pass dù constraint/SQL mapping thực sẽ lỗi khi commit production.

Ví dụ:

```java
repository.save(new OrderEntity(/* fields */));
entityManager.flush(); // chủ động buộc SQL chạy khi cần đo DB constraint
```

Đây là **đoạn minh họa**, không có DTO/repository đầy đủ. Khi cần test generated values, unique constraints, cascade, callbacks, hoặc database triggers, chọn đúng flush/readback boundary.

Cần phân biệt:

- `flush()`: đồng bộ SQL trong transaction.
- `clear()`: detach entities khỏi persistence context; **không tự flush**.
- `commit()`: xác nhận transaction, có thể flush trước commit.
- `rollback()`: hoàn tác changes thuộc transaction.

Không dùng `findById(id)` trong cùng persistence context để kết luận một SELECT mới đã đọc row từ DB; nó có thể trả lại managed instance trong first-level cache.

### 9.3. @DirtiesContext không xóa dữ liệu đã commit

`@DirtiesContext` giúp đánh dấu Spring ApplicationContext cần đóng/loại khỏi test context cache, **không bảo đảm xóa rows đã commit** ở H2 named DB, PostgreSQL, Redis hoặc broker. Với dữ liệu đã commit từ `@Commit`, `REQUIRES_NEW` hoặc HTTP server, vẫn cần cleanup/schema reset/isolated database.

### 9.4. @Transactional(readOnly=true) trên test không đảm bảo toàn bộ test chỉ đọc

Spring TestContext không áp dụng `readOnly` attribute của test `@Transactional` như một service transaction contract. Ngay trên service, `readOnly=true` thường là hint/optimization theo transaction manager/provider, không nên coi nó là security control tuyệt đối cấm mọi DML.

Muốn thử read-only behavior của DB hoặc repository, kiểm tra đúng database/manager và assert effect thực. Không suy luận từ annotation đơn lẻ.

## 10. MockMvc đồng bộ và real HTTP có thể khác rollback

### 10.1. MockMvc thông thường chạy trong test thread

Với `@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc`, lời gọi `mockMvc.perform(...)` xử lý request bằng mock Servlet request/response trong JVM, thường đồng bộ trên test thread. Nếu controller/service/JDBC code tham gia transaction ThreadLocal hiện tại, work có thể nằm trong test-managed transaction và rollback theo test.

Ví dụ dạng minh họa:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class MockMvcTransactionTest {

    @Autowired MockMvc mvc;

    @Test
    void postWithinMockRequest() throws Exception {
        mvc.perform(post("/api/ledger/MOCK-ENTRY"))
                .andExpect(status().isCreated());
        // Nếu request xử lý đồng bộ và service tham gia tx test,
        // row này sẽ rollback theo test transaction.
    }
}
```

Snippet này giả định endpoint trong phần 7 có sẵn và imports từ MockMvc. Không tự suy ra `MockMvc` luôn cùng thread cho mọi async case: `Callable`, `DeferredResult`, `@Async` hoặc custom executors có thể chuyển work sang thread khác.

### 10.2. RANDOM_PORT thực thi trên server thread

Khi dùng:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpTest {
}
```

test-managed transaction nằm trên JUnit test thread. Client HTTP thật gửi request tới server thread khác; service trên server có thể mở/commit transaction của nó. **Rollback của JUnit test không tự rollback server work**, theo Spring Boot reference documentation.

Dù test gọi `@LocalServerPort` hoặc client giả lập browser, điều quan trọng là **đường request**. Nếu bạn mở server ở RANDOM_PORT nhưng vẫn gọi `mockMvc.perform(...)`, lời gọi MockMvc vẫn có khả năng là in-process, không tự chuyển thành HTTP network path.

### 10.3. Async, @Scheduled và @TransactionalEventListener

Các tác vụ sau có thể nằm ngoài transaction của test thread hoặc diễn ra **sau** test method:

- `@Async` hoặc `CompletableFuture.supplyAsync/runAsync`.
- Scheduled jobs hoặc message listeners.
- Background queue consumers.
- `@TransactionalEventListener(phase = AFTER_COMMIT)`: một event listener chỉ chạy khi transaction thật sự commit có thể **không chạy trong test rollback mặc định**.
- External broker/email/webhook/object storage side effects.

Khi test event listener hoặc outbox, đừng “sửa” bằng cách bật `@Commit` cho mọi test mà không cleanup. Xác định event phase và transaction boundary, test riêng với fake/outbox/DB fixture phù hợp. Nếu cần kiểm tra AFTER_COMMIT listener, có thể tạo transaction commit có kiểm soát và dọn state.

## 11. @Sql: fixture có được rollback cùng test không?

Spring TestContext hỗ trợ `@Sql` để chạy SQL scripts trước/sau test. Nhưng dữ liệu do script tạo **có thể** tham gia test-managed transaction hoặc được commit độc lập, tùy `@SqlConfig.transactionMode` và thời điểm thực thi.

### 11.1. Mặc định có thể tham gia test transaction

Ví dụ:

```java
@SpringBootTest
@Transactional
@Sql(statements =
        "insert into ledger_entries(code, amount) values ('SQL-FIXTURE', 1)")
class SqlFixtureTest {
}
```

Đây là snippet, không phải một test class hoàn chỉnh; khi `@Sql` được thực thi trong test-managed transaction theo default inference mode và đúng transaction manager, INSERT fixture có thể bị rollback cùng test.

Không áp dụng kết luận này cho scripts chạy ở `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` hoặc khi `@SqlConfig(ISOLATED)` được yêu cầu.

### 11.2. ISOLATED thường tạo transaction riêng và commit

```java
@Sql(
    statements =
        "insert into ledger_entries(code, amount) values ('SQL-ISOLATED', 1)",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
```

Đây là snippet annotation, cần đúng imports và DB schema. Với isolated mode, Spring Test chạy script trong transaction **độc lập và được commit**. Dữ liệu có thể còn lại sau rollback của test method, nên phải cleanup ở đúng boundary.

Có thể khai báo thêm `@Sql(executionPhase=AFTER_TEST_METHOD, config=ISOLATED)` để dọn fixture, nhưng phải đảm bảo script cleanup chạy đúng, idempotent và không xóa dữ liệu của test khác. Đừng chạy script destructive trên production database.

### 11.3. SQL schema initialization khác transaction của một test method

File `schema.sql` mà Spring Boot SQL initializer chạy lúc khởi động test context là **database setup**, không phải từng lần test-managed transaction. Vì vậy một table được tạo lúc startup không biến mất sau mỗi test rollback. Còn rows được INSERT trong test transaction thì có thể rollback. Phân biệt **schema lifecycle** với **fixture data lifecycle**.

## 12. ThreadLocal, preemptive timeouts và test chạy song song

### 12.1. JDBC transaction state gắn với thread

Spring TestContext gắn transaction state với thread được dùng để chạy test method. Nếu test code chuyển sang worker thread thì JDBC work trên worker **không tự tham gia** test transaction của JUnit thread.

Phản mẫu:

```java
CompletableFuture<Void> task =
        CompletableFuture.runAsync(() ->
                jdbc.update(
                        "insert into ledger_entries(code, amount) values (?, ?)",
                        "ASYNC-ENTRY", 1));

task.join();
```

Đây là snippet, không phải test runnable độc lập. Dù `join()` đợi task hoàn tất, task thực hiện trên thread khác và có thể dùng connection/autocommit khác. Rollback ở test thread không tự hoàn tác row. Nếu không `join()`, còn có rủi ro test kết thúc trước khi work hoàn tất.

Không dùng ThreadLocal transaction test làm cơ chế atomicity cho các tác vụ background. Cần mở transaction riêng ở đúng executor/service boundary và cleanup.

### 12.2. JUnit assertTimeoutPreemptively là bẫy có tài liệu chính thức

Spring Framework TestContext docs cảnh báo `assertTimeoutPreemptively(...)` của JUnit có thể thực thi đoạn code trên **thread khác**. Nếu bạn dựa vào test-managed transaction để rollback JDBC work trong lambda, work ấy có thể chạy **ngoài transaction**, commit và để lại dữ liệu.

Phản mẫu:

```java
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    jdbc.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "PREEMPTIVE", 1);
});
```

Đây là snippet minh họa lỗi tiềm ẩn, không nên copy vào test transaction của project. Nếu cần kiểm tra timeout mà không thay thread, cân nhắc `assertTimeout(...)` không preemptive hoặc một transaction explicit trong worker thread với cleanup rõ ràng.

### 12.3. Parallel tests cần cô lập transaction resources

Rollback mặc định **không phải phép màu** loại mọi race:

- Hai tests có thể dùng cùng row/key ở các transactions khác nhau, gây lock/duplicate key.
- Một test tạo row đã commit từ `REQUIRES_NEW` và test khác đọc được.
- Test chạy HTTP server hoặc background worker có thể commit giữa lúc test khác đọc.
- @Sql(ISOLATED) scripts có thể thay shared fixtures.
- Context cache giữ Spring bean state, nhưng transaction rollback chỉ quản lý DB resource.
- H2 in-memory named DB có thể được chia sẻ giữa contexts trong cùng JVM, tùy URL.

Với CI chạy song song, ưu tiên database/schema riêng theo worker hoặc test suite, keys unique, setup/cleanup idempotent và không phụ thuộc test order. Hạn chế dùng fixed global IDs khi database shared.

### 12.4. Không coi @TestMethodOrder là cách sửa data leakage

Sắp xếp test để “test A tạo dữ liệu, test B xóa” khiến suite phụ thuộc thứ tự và khó chạy độc lập. Test đã commit dữ liệu cần cleanup trong chính fixture/lifecycle tương ứng hoặc environment reset. `@TestMethodOrder` không thay thế isolation.

## 13. @Transactional trên test và service: kiểm chứng propagation thật

### 13.1. REQUIRED

Một service `@Transactional(propagation = REQUIRED)` gọi từ test đang active transaction thường **join** test transaction nếu cùng PlatformTransactionManager. Điều này tốt khi test repository/service code phối hợp, nhưng có thể che việc service production đang thiếu transaction boundary cho toàn bộ nghiệp vụ.

Khi mục tiêu là kiểm tra atomicity của service ở production, có thể để test method **không transactional** để service tự mở/kết thúc transaction, rồi kiểm tra dữ liệu sau service call. Khi đó phải chủ động xóa dữ liệu thành công trong fixture cleanup.

### 13.2. REQUIRES_NEW

Đã minh họa trong phần 7: inner transaction commit riêng, có thể sống sót outer rollback. Với JDBC connection pools, REQUIRES_NEW còn có yêu cầu lấy **connection thứ hai** trong khi outer transaction giữ connection cũ; cần lưu ý pool size/độ song song, tránh deadlock do thiếu connections.

Không dùng REQUIRES_NEW chỉ để né rollback trong test: nó thay đổi semantics nghiệp vụ và production behavior.

### 13.3. NESTED, SUPPORTS, NOT_SUPPORTED và NEVER

- `NESTED` có thể sử dụng savepoint trong JDBC khi manager/driver hỗ trợ; semantics không giống một transaction commit độc lập như REQUIRES_NEW.
- `SUPPORTS` tham gia transaction nếu đang có, chạy không transaction nếu không có.
- `NOT_SUPPORTED` trên **service** có thể suspend transaction hiện tại; trên **test method**, listener không mở test-managed transaction.
- `NEVER` trên **service** từ chối nếu có transaction hiện tại; với test listener, `NEVER` là một trường hợp không mở test-managed transaction.

Đừng suy luận chỉ từ annotation trên test rằng mọi propagation mode được TestContext listener mô phỏng như Spring TransactionInterceptor của service. Spring Framework 6.2 chỉ hỗ trợ một tập **rất hạn chế** các attributes cho test-managed transaction.

### 13.4. Self-invocation và proxy

Spring `@Transactional` trên service thường được thực thi thông qua Spring AOP proxy. Nếu method `this.innerRequiresNew()` được gọi từ cùng instance, proxy interception có thể bị bỏ qua, nên không mở transaction mới như mong đợi. Muốn test propagation, gọi public method thông qua Spring-managed bean/proxy hoặc thiết kế boundary phù hợp.

Mẫu phần 7 inject `LedgerService` vào test/controller, không tạo bằng `new`, để giao dịch được quản lý đúng.

## 14. Test rollback và database isolation

### 14.1. “Một query thấy row” phụ thuộc transaction nào

Giả sử TX-A INSERT một row rồi chưa commit:

```text
TX-A: BEGIN
TX-A: INSERT code='A'
TX-A: SELECT code='A' -> thấy 1
TX-B: SELECT code='A' -> có thể chưa thấy 1
TX-A: ROLLBACK
TX-B: SELECT code='A' -> không có 1
```

Dưới `READ_COMMITTED`, TX-B thường không thấy uncommitted row của TX-A; trong DB khác có thể có lock/snapshot behavior. Vì vậy:

- SELECT cùng TX-A thấy row **không chứng minh commit**.
- SELECT TX-B không thấy row **không chứng minh INSERT chưa chạy**.
- Một connection dùng `READ_UNCOMMITTED` nhìn thấy dirty row cũng không biến row thành committed.
- Một @AfterTransaction query hoặc TestTransaction.end + query giúp kiểm tra **hậu quả sau boundary**, nhưng cần xác định connection/isolation và manager đúng.

### 14.2. H2 khác production databases

H2 thuận tiện cho demo transaction và rollback, nhưng không đại diện mọi behavior của PostgreSQL/MySQL/Oracle:

- Isolation/snapshot semantics khác.
- Transactional DDL và constraint checking khác.
- Generated keys/sequence/identity và trigger có thể khác.
- Lock waits/deadlocks/timeout/pool behavior khác.
- SQL dialect có thể khác.
- FK/unique constraint timing có thể khác.

Nếu production phụ thuộc locking/transaction isolation, chạy thêm Testcontainers với **database engine thật** và transaction lifecycle được kiểm soát.

### 14.3. Test commit thành công phải quan sát sau transaction

Một `@Commit` test chỉ có assertion ở giữa method chưa chứng minh final state đã commit thành công. `@AfterTransaction` được gọi sau khi framework cố commit/rollback nên là điểm quan sát tốt; một alternative là chủ động `TestTransaction.flagForCommit(); TestTransaction.end();` rồi đọc lại ở ngoài transaction.

Trong trường hợp database commit lỗi, test phải fail và root cause cần được giữ trong report. Đừng catch rồi bỏ qua commit exception chỉ để suite xanh.

## 15. Reactive transaction và giới hạn của test-managed @Transactional

### 15.1. Vì sao R2DBC không giống JDBC?

Imperative JDBC transaction gắn với thread/connection. R2DBC transaction dùng `ReactiveTransactionManager` và Reactor subscriber `Context`. Một `Mono`/`Flux` thường chỉ thực thi database operation khi được subscribe.

Ví dụ reactive service concept:

```java
@Transactional
public Mono<Void> createOrder() {
    return databaseClient.sql(
            "insert into orders(code) values ('R-1')")
            .fetch()
            .rowsUpdated()
            .then();
}
```

Snippet này cần class Spring bean, database client/connection factory và imports đầy đủ; không phải file runnable độc lập. Chỉ gọi `createOrder()` rồi `assertNotNull(publisher)` không chứng minh transaction đã diễn ra. Dùng StepVerifier hoặc subscribe-aware integration test để kiểm tra.

### 15.2. TransactionalOperator bọc Publisher, không bọc JUnit method void

Với R2DBC, có thể dùng:

```java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Long> work = databaseClient.sql(
        "insert into orders(code) values ('R-2')")
        .fetch()
        .rowsUpdated()
        .as(operator::transactional);

StepVerifier.create(work)
        .expectNext(1L)
        .verifyComplete();
```

Đây là snippet có `reactor-test` và R2DBC transaction manager; không phải code JDBC/H2 hoàn chỉnh phần 7. Khi Publisher thành công, reactive operator commit; khi `onError` xảy ra trong transaction scope, thường rollback. Cancellation cũng có semantics rollback theo Spring Framework ReactiveTransactionManager.

**Không** thêm `@Transactional` lên JUnit `void` method rồi tin ReactiveTransactionManager sẽ tự rollback mọi Publishers khi method kết thúc. Muốn kiểm thử reactive transaction thật, hãy tạo Publisher transactional, subscribe và query kết quả sau khi terminal.

### 15.3. Không đưa JDBC trong Mono rồi nghĩ đã được R2DBC rollback

`Mono.fromRunnable(() -> jdbc.update(...)).as(operator::transactional)` không tự chuyển JDBC connection thành R2DBC connection đang được ReactiveTransactionManager quản lý. Hai SPIs khác nhau; muốn atomicity xuyên resources, cần kiến trúc rõ, không dựa vào một annotation/test.

## 16. Mẹo thiết kế fixtures và cleanup đáng tin

### 16.1. Ưu tiên dữ liệu được rollback khi đúng mục tiêu

Với repository slice hoặc full-context test giao dịch thuần:

- Mỗi test tạo own fake fixture bên trong test-managed transaction.
- Không dùng same global identifiers.
- Có thể dùng `@BeforeEach` để seed nếu mọi test ở class đều transactional.
- Rely vào default rollback để dọn những changes thuộc chính transaction đó.
- Không để asynchronous work hoặc REQUIRES_NEW tự commit ngoài ý định.
- Khi test JPA, flush nếu cần đo database constraints hoặc persisted SQL.

### 16.2. Với test cần commit, cleanup phải tường minh

Các trường hợp cần commit thật:

- Test `@Commit`/`@Rollback(false)`.
- Test service `REQUIRES_NEW`.
- Test HTTP server qua `RANDOM_PORT`.
- @Sql(ISOLATED) fixtures.
- Test scheduled/background operations đã commit.
- Test transaction tại database engine thật với propagation/constraint timing.

Cleanup có thể đặt trong `@AfterTransaction`, `finally`, test teardown ở transaction khác hoặc database/container reset. Dùng phương thức idempotent nếu có thể và giữ data test riêng biệt để không xóa nhầm dữ liệu khác.

**Không dùng production DB hoặc data khách hàng thật** cho test rollback/commit. Đừng đưa secrets/password vào SQL logs hoặc repository examples.

### 16.3. Sau commit không nhất thiết @AfterEach nhìn thấy trạng thái cuối

Nhớ rằng `@AfterEach` còn **nằm trong test transaction**. Với `@Commit`, commit diễn ra **sau** @AfterEach. Nếu mục tiêu là test SQL commit constraint, @AfterEach không đủ; quan sát ở @AfterTransaction hoặc TestTransaction.end sau khi yêu cầu commit.

### 16.4. Dùng test names đúng thứ đã chứng minh

Tên dễ sai:

- `savedPermanently()` nhưng chỉ gọi repository.save và assert getter.
- `rollsBackEverything()` nhưng test có HTTP call sang server.
- `transactionalServiceIsAtomic()` nhưng outer test transaction đã bao toàn bộ các operations.
- `cleanupRuns()` nhưng reactive delete Publisher chưa được subscribe.

Tên nên phản ánh **boundary và assertion** thực, ví dụ `testManagedTransactionIsRolledBackAfterMethod()` hoặc `requiresNewCommitSurvivesOuterTestRollback()`.

## 17. Bảng lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
|---|---|---|
| `@Transactional` test vẫn để lại row | REQUIRES_NEW, async thread, HTTP server, SQL isolated hoặc datasource khác | Xác định transaction manager/thread/connection; cleanup riêng |
| `@SpringBootTest` viết SQL rồi dữ liệu còn | Test không có `@Transactional`; service tự commit | Thêm test-managed tx nếu phù hợp, hoặc cleanup |
| `@DataJpaTest` row biến mất sau test | Slice rollback mặc định | Hành vi đúng; không nhầm với save thất bại |
| `@JdbcTest` thấy INSERT trong method nhưng không còn sau | Same-transaction read và rollback cuối test | TestTransaction/@AfterTransaction để chứng minh |
| `@DataR2dbcTest` để lại data | Không có reactive test-managed rollback mặc định | TransactionalOperator + cleanup |
| `TestTransaction.isActive()` false | Không có tx test, propagation NOT_SUPPORTED/NEVER hoặc khác thread | Kiểm tra annotation/listener/manager |
| Test `@Commit` vẫn không commit | Transaction rollback-only, constraint, manager/config lỗi | Đọc exception/transaction status, xác nhận sau boundary |
| `@AfterEach` còn thấy row trước rollback | Lifecycle callback vẫn trong transaction | Dùng @AfterTransaction |
| `@BeforeAll` tạo fixture không bị rollback | Không thuộc transaction của mỗi method | Cleanup hoặc transaction/template riêng |
| `findById` thấy managed state, DB constraint không ném | JPA chưa flush | entityManager.flush/repository.flush |
| HTTP POST trong `RANDOM_PORT` để lại data | Server transaction khác test thread | HTTP integration cleanup, test DB riêng |
| `mockMvc.perform` rollback nhưng HTTP không | Đường in-process vs server thread/connection khác | Ghi rõ type of test, assert đúng boundary |
| Preemptive timeout làm DB bẩn | Callback chạy thread khác, không có tx ThreadLocal | Nonpreemptive timeout/explicit worker transaction |
| `@Transactional(noRollbackFor=...)` trên test không commit như tưởng | Listener không hỗ trợ rollbackFor/noRollbackFor attrs | @Commit/@Rollback/TestTransaction |
| `@Rollback(false)` test ảnh hưởng test sau | Dữ liệu đã được commit | Cleanup trong after transaction |
| `@Sql` fixture không rollback | TransactionMode.ISOLATED/class-level phases | Kiểm tra SQL config, scripts, cleanup |
| JDBC `@Async` ghi row ngoài test transaction | Thread khác không kế thừa tx state | Transaction/cleanup trên worker thread |
| `@DirtiesContext` nhưng row vẫn còn | Context cache khác database persistent state | Reset DB/schema hoặc explicit delete |
| Tests pass riêng, fail theo suite | Shared schema, committed leftovers, parallel conflicts | Unique fixture keys, isolation, deterministic cleanup |
| Multi-manager test kết nối sai DB | Transaction manager không khớp DataSource | Chọn manager bằng qualifier, kiểm tra wiring |
| DB thật fail, H2 pass | Dialect/isolation/constraint khác | Test thêm với production database engine |
| `@Transactional` trên service không chạy | Service tạo bằng new/self-invocation hoặc proxy bị bypass | Gọi qua Spring-managed proxy/bean |
| Transaction readOnly không cấm write như mong | ReadOnly không phải hard security guarantee | Test actual manager/DB enforcement |

### 17.1. Debug theo thứ tự hiệu quả

1. Xác nhận class có chạy qua SpringExtension/TestContext không.
2. Xác nhận `PlatformTransactionManager` đang tồn tại/chọn đúng.
3. Xác nhận `@Transactional` trên test class/method hoặc slice auto transactional.
4. Xác nhận method có `NOT_SUPPORTED/NEVER`, `@Commit` hay `@Rollback(false)` không.
5. Trong test, kiểm tra `TestTransaction.isActive()` và `isFlaggedForRollback()`.
6. Xác định operations nằm trên **cùng thread**, cùng DataSource/manager hay không.
7. Với Spring service, kiểm tra propagation và proxy interception.
8. Với web test, xác định MockMvc in-process hay real HTTP RANDOM_PORT.
9. Với JPA, xác định pending state đã flush hay chưa.
10. Với @Sql, kiểm tra transaction mode, execution phase và scripts.
11. Đo database state sau transaction boundary, không chỉ trong method.
12. Nếu còn data, cleanup; nếu khác giữa môi trường, thử đúng database engine.
13. Đọc reports, log connection/transaction ở mức an toàn, không dump secrets.

## 18. Bài tập và đáp án

### Bài A — Vì sao @SpringBootTest không tự rollback?

Một test chỉ có `@SpringBootTest` và gọi service ghi dữ liệu. Sau test row vẫn còn. Có phải Spring Test rollback lỗi?

**Đáp án:** không. `@SpringBootTest` tự nạp application context, nhưng không mặc định tạo test-managed transaction. Service có thể tự mở/commit transaction. Nếu cần default rollback, đặt `@Transactional` trên test class/method với PlatformTransactionManager phù hợp hoặc dùng transactional test slice. Nếu test mục tiêu production commit, đừng bọc outer test transaction chỉ để khiến row biến mất; thay vào đó kiểm tra service boundary và cleanup.

### Bài B — @BeforeEach khác @BeforeTransaction thế nào?

Trong một `@Transactional` test, @BeforeEach INSERT row, @AfterEach SELECT vẫn thấy row. Có thể kết luận rollback không chạy không?

**Không.** Cả hai lifecycle methods chạy trong transaction test. Rollback diễn ra **sau @AfterEach**. Để chứng minh row đã rollback, dùng `@AfterTransaction` hoặc `TestTransaction.end()` rồi query lại.

### Bài C — Muốn commit một test

Một class có `@Transactional` và 20 test rollback mặc định. Chỉ một test cần commit để kiểm tra AFTER_COMMIT. Dùng gì?

**Đáp án:** đặt `@Commit` hoặc `@Rollback(false)` lên đúng **test method** đó; xác minh effect sau transaction và cleanup dữ liệu đã commit. Không đặt @Commit lên cả class nếu 19 test còn lại phải rollback.

### Bài D — TestTransaction.flagForCommit đã đủ chưa?

Một method gọi `TestTransaction.flagForCommit()`, rồi ngay sau đó assert DB query. Có biết transaction đã commit không?

**Chưa.** Flag chỉ thay kế hoạch kết thúc. Muốn kiểm tra commit ngay, `TestTransaction.end()` để kết thúc transaction rồi đọc ở boundary mới. Khi muốn tiếp tục với test-managed tx khác, gọi `start()` theo đúng lifecycle.

### Bài E — REQUIRES_NEW tạo leak

JUnit test `@Transactional` gọi một Spring service dùng `REQUIRES_NEW`. Sau test outer rollback, row từ service vẫn còn. Tại sao?

**Đáp án:** inner transaction được commit độc lập. Rollback của outer test transaction không hoàn tác inner commit. Bài test cần @AfterTransaction/finally cleanup hoặc isolated database. Đồng thời phải xác minh service method thật sự được gọi qua Spring proxy.

### Bài F — HTTP thật khác MockMvc

Một POST với MockMvc được rollback sau test, nhưng khi chuyển sang `RANDOM_PORT` + HTTP client thì row còn lại. Vì sao?

**Đáp án:** MockMvc đồng bộ thường xử lý trong test thread; live HTTP được server xử lý ở thread/transaction khác. `@Transactional` trên JUnit test không tự bao trùm server transaction. Cần cleanup và test thực tế transaction boundary.

### Bài G — JPA không flush

Test `@DataJpaTest` gọi `repository.save(...)`, assert entity ID, rồi kết thúc. Production lại gặp unique constraint violation. Vì sao test không phát hiện?

**Đáp án:** JPA có thể chỉ giữ pending insert/update trong persistence context, còn transaction test rollback trước khi provider thực hiện một đường flush giống production. Test phải gọi `entityManager.flush()` hoặc repository.flush nếu mục tiêu kiểm chứng DB constraints, và cân nhắc ID generator/DB engine.

### Bài H — @Transactional(noRollbackFor=...) trên test

Bạn muốn commit một test ngay cả khi assertion ném exception, nên đặt `@Transactional(noRollbackFor = AssertionError.class)`. Có chắc điều đó thay test-managed rollback không?

**Không.** Spring TestContext listener không áp dụng `noRollbackFor` cho test-managed tx. Dùng `@Commit`/`@Rollback(false)` theo transaction policy test, nhưng **đừng dùng commit để che một test assertion failure**; kiểm tra transaction status và làm sạch data.

### Bài I — Một task CompletableFuture ngoài test transaction

Test thread có transaction, nhưng asynchronous task thực hiện JDBC update và commit. Vì sao mặc định rollback không cứu được?

**Đáp án:** transaction state imperative gắn với thread; worker thread không tự kế thừa. Quản lý transaction/cleanup ở executor/service phù hợp, và đợi task hoàn tất trước khi assert.

### Bài J — R2DBC Mono không có dữ liệu

Một test `@DataR2dbcTest` tạo Mono insert nhưng không subscribe; row không xuất hiện. Có phải test-managed rollback đã xóa?

**Đáp án:** chưa chắc đã có SQL nào chạy. Reactive Publisher thường lazy; phải subscribe/verify mới phát sinh DB work. Sau đó kiểm tra transaction scope bằng TransactionalOperator/proxied reactive service; không suy diễn từ default JDBC rollback.

### Bài K — @Sql ISOLATED

Bạn dùng `@SqlConfig(transactionMode=ISOLATED)` để thêm fixture vào DB, nhưng cuối test @Transactional rollback thì fixture vẫn còn. Là lỗi Spring?

**Không.** ISOLATED tạo transaction riêng và commit; outer test rollback không hoàn tác. Dùng isolated cleanup script hoặc database/schema riêng.

### Bài L — Bật @Rollback(false) cho toàn bộ suite?

Một nhóm muốn bật `@Rollback(false)` cho mọi integration test để “giống production”. Rủi ro?

**Đáp án:** data leakage, test order dependence, flakiness, database growth, unique key collision và cleanup khó. Nên chỉ bật commit khi cần chứng minh boundary; còn phần lớn repository tests dùng rollback mặc định và có nhóm riêng kiểm tra commit/rollback thực tế.

## 19. Checklist QA trước khi kết luận rollback test đúng

- [ ] Xác định test đang dùng `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest` hay `@DataR2dbcTest`.
- [ ] Biết annotation có tự tạo test transaction hay không.
- [ ] `PlatformTransactionManager` phù hợp hiện diện cho test-managed JDBC/JPA.
- [ ] Dùng Spring `org.springframework.transaction.annotation.Transactional` đúng import.
- [ ] Không nhầm test-managed rollback với service declarative rollback rules.
- [ ] Đã phân biệt transaction đang active với rollback flag.
- [ ] Không suy luận @Transactional rollbackFor/noRollbackFor trên test có tác dụng như service.
- [ ] @BeforeEach/@AfterEach và @BeforeTransaction/@AfterTransaction được dùng đúng lifecycle.
- [ ] Không dùng @BeforeAll để tạo fixture rồi tưởng rollback theo từng test.
- [ ] Nếu @Commit/@Rollback(false), có query sau boundary và cleanup.
- [ ] Nếu TestTransaction.end/start, biết rõ transaction nào vừa kết thúc.
- [ ] Nếu NOT_SUPPORTED/NEVER, không dựa vào auto rollback.
- [ ] Nếu service REQUIRES_NEW, có test chứng minh inner commit/rollback độc lập.
- [ ] Nếu test qua HTTP RANDOM_PORT, quản lý server-side committed data.
- [ ] Với MockMvc, xác nhận request đồng bộ hay có async thread.
- [ ] Với JPA, flush khi cần bắt DB constraint và không nhầm first-level cache với row thật.
- [ ] Nếu SQL scripts @Sql(ISOLATED), biết chúng commit riêng.
- [ ] Không dùng JUnit assertTimeoutPreemptively khi tin thread-bound rollback.
- [ ] Không dùng CompletableFuture/@Async mà mặc định kế thừa test tx.
- [ ] Không dùng @DirtiesContext như một database cleanup mechanism.
- [ ] Không trộn JDBC với R2DBC và kỳ vọng chúng chung transaction theo annotation.
- [ ] Với parallel CI, có database/schema/keys riêng, cleanup deterministic.
- [ ] Không dùng production DB/secrets hoặc fixture dữ liệu thật.
- [ ] Với DB-specific isolation/constraints, test bằng production engine.
- [ ] Test thật sự được JUnit chạy, kết quả report có pass/fail/skipped.
- [ ] Tên test/assertions phản ánh transaction boundary mà nó chứng minh.

## 20. Tổng kết

**@Transactional trên một Spring test method là công cụ quản lý một test-managed transaction với rollback mặc định, không phải lời hứa mọi tác động của ứng dụng đều sẽ được rollback.**

Cơ chế mặc định có ý nghĩa nhất với JDBC/JPA work trên cùng transaction manager, connection và test thread. Test-managed transaction bao gồm `@BeforeEach`, `@Test` và `@AfterEach`; `@BeforeTransaction` và `@AfterTransaction` chạy ngoài ranh giới ấy.

Khi cần đổi policy, dùng `@Commit`, `@Rollback(false)` hoặc `TestTransaction`. Khi cần kiểm tra production behavior, phải chú ý `REQUIRES_NEW`, service proxy, HTTP server thread, async work, test SQL fixtures, database constraints và isolation. **Rollback mặc định chỉ hoàn tác những công việc thực sự thuộc transaction đó.**

Một test tốt không chỉ nói “transaction active”, mà **đo dữ liệu sau khi transaction kết thúc** và dọn chính xác những thay đổi đã commit. Giữ test suites nhanh/độc lập bằng rollback phù hợp, thêm một tập commit/boundary tests có cleanup chủ đích, và dùng database engine thực khi các quy tắc phụ thuộc RDBMS.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): Test-managed transactions, supported attributes, default rollback, lifecycle, TestTransaction, timeout thread caveats.
- [Spring Framework — @Rollback annotation](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-rollback.html): rollback mặc định, @Rollback(false), method/class override.
- [Spring Framework — @Commit annotation](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-commit.html): commit test-managed transaction.
- [Spring Framework — @BeforeTransaction / @AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html): lifecycle hooks ngoài test transaction.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): flagForRollback, flagForCommit, end/start, active.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, RANDOM_PORT thread caveat, JDBC/JPA slices transactional default.
- [Spring Framework — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): @Sql and @SqlConfig(TransactionMode.ISOLATED).
- [Spring Framework — Declarative @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): service transaction rules and propagation.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED/REQUIRES_NEW/NESTED and resource implications.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): schema.sql, embedded DataSource initialization.
