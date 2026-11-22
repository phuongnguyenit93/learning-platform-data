# Rollback mặc định sau một phương thức kiểm thử

Khi kiểm thử tầng persistence hoặc service có ghi dữ liệu, ta thường muốn mỗi test bắt đầu từ một trạng thái cơ sở dữ liệu xác định và không để dữ liệu của test trước ảnh hưởng test sau. Spring TestContext hỗ trợ **test-managed transaction**: nếu một test method hoặc test class được đánh dấu `@Transactional`, Spring có thể mở transaction trước khi test chạy và rollback transaction đó sau khi method kết thúc.

Với test-managed transaction, **rollback là hành vi mặc định**. Test vẫn rollback khi assertion thành công; rollback không chỉ xảy ra khi test thất bại. Nhờ vậy, test có thể insert, update hoặc delete dữ liệu trong transaction rồi kiểm tra kết quả ngay trong test mà không để các thay đổi đã thực hiện trong transaction đó tồn tại sau khi test hoàn tất.

Điều quan trọng là hiểu đúng phạm vi của transaction này. Nó quản lý các thao tác tham gia cùng transaction manager và transaction context của test. Nó không tự hoàn tác mọi side effect bên ngoài, chẳng hạn request được xử lý trên server thread khác, transaction `REQUIRES_NEW`, message đã gửi, file đã ghi hoặc thay đổi trong hệ thống ngoài.

## 1. Test-managed transaction là gì?

Spring TestContext Framework tích hợp transaction thông qua `TransactionalTestExecutionListener`. Listener này đọc metadata `@Transactional` trên test class hoặc test method, tìm transaction manager phù hợp và quản lý vòng đời transaction cho test.

Một test-managed transaction thường có trình tự:

```text
Spring TestContext chuẩn bị test
              |
              v
Mở transaction cho test method
              |
              v
JUnit @BeforeEach
              |
              v
Test method
              |
              v
JUnit @AfterEach
              |
              v
Commit hoặc rollback theo cấu hình test
              |
              v
Spring @AfterTransaction
```

Với chính sách mặc định, bước kết thúc là rollback. Các callback `@BeforeTransaction` và `@AfterTransaction` của Spring được thiết kế để chạy ngoài test-managed transaction; chúng hữu ích khi cần chuẩn bị hoặc xác minh dữ liệu trước/sau transaction. Trong khi đó, các callback JUnit như `@BeforeEach` và `@AfterEach` được thực thi bên trong transaction của test khi transaction đã được mở.

Test-managed transaction khác với transaction do mã ứng dụng tự tạo ở chỗ Spring TestContext bắt đầu và kết thúc transaction bao quanh test method. Khi service gọi phương thức `@Transactional` với propagation mặc định `REQUIRED` trên cùng transaction manager và cùng thread, thao tác thường tham gia transaction của test.

## 2. Bật transaction cho test

Để Spring quản lý transaction cho test, đánh dấu `@Transactional` ở cấp class hoặc method. Cần có transaction manager phù hợp trong ApplicationContext.

Ví dụ với JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void insertsAccountInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into account(email) values (?)",
                "rollback@example.test");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                "rollback@example.test");

        assertEquals(1, count);
    }
}
```

Ví dụ giả định `TestDatabaseConfiguration` cấu hình datasource, `JdbcTemplate` và một `PlatformTransactionManager` dùng cùng datasource. Trong test, bản ghi có thể được đọc ngay trong transaction và assertion xác nhận câu lệnh insert đã có hiệu lực đối với transaction hiện tại. Sau khi method kết thúc, Spring rollback transaction theo mặc định, vì vậy bản ghi không được commit vào database.

Nếu không có `@Transactional` ở class hoặc method, Spring TestContext không tự động mở transaction chỉ vì test đang dùng Spring. Một test thông thường không được rollback tự động; các thao tác ghi dữ liệu có thể commit theo transaction của ứng dụng hoặc cơ chế auto-commit của datasource.

### 2.1. @Transactional ở cấp class

Đặt `@Transactional` trên class để các test method trong class tham gia test-managed transaction theo mặc định:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Transactional
class OrderRepositoryTests {

    @Test
    void savesOrder() {
        // Transaction được mở cho method này.
    }

    @Test
    void updatesOrder() {
        // Transaction riêng cho method này.
    }
}
```

Mỗi test method có transaction riêng. Spring không mở một transaction duy nhất cho toàn bộ class rồi giữ nó xuyên suốt mọi method.

### 2.2. @Transactional ở cấp method

Nếu chỉ một số test cần transaction, có thể đặt annotation trực tiếp lên method:

```java
@SpringJUnitConfig(TestConfiguration.class)
class AccountServiceTests {

    @Test
    @Transactional
    void createsAccountAndRollsBackAfterTest() {
        // Test chạy trong test-managed transaction.
    }

    @Test
    void checksPureCalculationWithoutTransaction() {
        // Không có test-managed transaction.
    }
}
```

Annotation ở method có thể được dùng để xác định hành vi transaction cho method đó. Nếu class đã có `@Transactional`, method có thể dùng metadata riêng để ghi đè cấu hình phù hợp.

### 2.3. Chọn transaction manager

Nếu context chỉ có một `PlatformTransactionManager` phù hợp, Spring có thể tìm transaction manager đó theo quy tắc mặc định. Nếu ứng dụng có nhiều transaction manager, hãy chỉ rõ bean cần dùng:

```java
@Transactional(transactionManager = "ordersTransactionManager")
@Test
void updatesOrderDatabase() {
    // Các thao tác tham gia transaction của ordersTransactionManager.
}
```

Thuộc tính `value` là alias của `transactionManager`, nên có thể viết ngắn `@Transactional("ordersTransactionManager")`. Việc chọn đúng transaction manager rất quan trọng: rollback của transaction manager cho database A không tự rollback thao tác được thực hiện qua transaction manager của database B.

## 3. Vì sao mặc định là rollback?

Test thường tạo dữ liệu tạm để kiểm tra hành vi. Nếu mọi test đều commit, dữ liệu có thể tích tụ, gây trùng khóa, làm thay đổi kết quả truy vấn hoặc khiến test phụ thuộc thứ tự chạy.

Rollback mặc định đem lại một số lợi ích:

- **Cô lập dữ liệu:** các thay đổi trong transaction của một test không trở thành dữ liệu đã commit cho test sau.
- **Có thể chạy lặp lại:** cùng một test có thể chạy nhiều lần mà không cần xóa thủ công mọi bản ghi đã tạo.
- **Giảm phụ thuộc thứ tự:** test không cần giả định test trước đã tạo hoặc chưa tạo dữ liệu.
- **Đơn giản hóa cleanup:** database tự hoàn tác các thay đổi thuộc transaction thay vì phải viết câu lệnh xóa cho từng trường hợp.
- **Kiểm tra được trạng thái trung gian:** test có thể ghi dữ liệu rồi truy vấn lại trong cùng transaction trước khi rollback.

Rollback không có nghĩa test không được ghi dữ liệu. Test vẫn có thể thực hiện đầy đủ thao tác ghi, cập nhật và xóa trong transaction; những thay đổi đó chỉ không được commit khi test kết thúc theo chính sách mặc định.

## 4. @Rollback và @Commit

Spring TestContext cung cấp hai annotation để điều khiển kết quả của test-managed transaction:

- `@Rollback`: chỉ định transaction có rollback khi kết thúc hay không.
- `@Commit`: yêu cầu commit transaction khi test hoàn tất.

`@Rollback` có giá trị mặc định là `true`. Do đó, `@Rollback` không cần ghi tham số vẫn thể hiện rollback. Đây cũng là hành vi mặc định của test-managed transaction khi test có `@Transactional`.

### 4.1. Ghi rõ rollback

```java
@Test
@Transactional
@Rollback(true)
void createsTemporaryAccount() {
    // Dữ liệu được ghi trong transaction và rollback sau test.
}
```

Khai báo này tương đương với hành vi mặc định. Có thể dùng khi muốn tài liệu hóa ý định của test hoặc ghi đè cấu hình class-level đang yêu cầu commit.

### 4.2. Commit bằng @Commit

```java
@Test
@Transactional
@Commit
void storesReferenceDataForLaterTests() {
    // Thay đổi được commit khi test method hoàn tất.
}
```

`@Commit` là cách viết rõ ý định commit, tương đương về mục đích với `@Rollback(false)`. Chỉ dùng khi test thực sự cần để dữ liệu tồn tại sau khi method kết thúc, chẳng hạn một test chuyên biệt tạo fixture lâu dài cho một quy trình tích hợp được kiểm soát.

### 4.3. Dùng @Rollback(false)

```java
@Test
@Transactional
@Rollback(false)
void commitsAccount() {
    // Transaction được commit khi test kết thúc.
}
```

`@Rollback(false)` làm transaction commit thay vì rollback. `@Commit` thường dễ đọc hơn vì diễn đạt trực tiếp mục đích.

### 4.4. Khai báo ở cấp class và ghi đè ở method

Có thể đặt chính sách cho cả class rồi thay đổi ở một method:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Transactional
@Rollback(false)
class AccountPersistenceTests {

    @Test
    void commitsReferenceAccount() {
        // Commit theo cấu hình class-level.
    }

    @Test
    @Rollback
    void rollsBackTemporaryAccount() {
        // Rollback được yêu cầu riêng cho method này.
    }
}
```

Trong ví dụ, class-level `@Rollback(false)` yêu cầu commit theo mặc định cho các test method có transaction. Method thứ hai dùng `@Rollback` mặc định `true` để ghi đè và rollback riêng. Hãy hạn chế tạo test phụ thuộc dữ liệu do method khác commit; nếu có dependency như vậy, suite sẽ khó chạy độc lập và khó chạy song song.

## 5. Thời điểm kiểm tra dữ liệu trước và sau rollback

Trong test-managed transaction, test method có thể thấy các thay đổi của chính nó. Muốn xác minh rollback thực sự xảy ra sau khi method kết thúc, có thể dùng `@AfterTransaction`, callback của Spring chạy sau khi transaction đã kết thúc.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class RollbackAfterMethodTest {

    private static final String EMAIL = "rollback-check@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void rowExistsInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into account(email) values (?)", EMAIL);

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                EMAIL);

        assertEquals(1, count);
    }

    @AfterTransaction
    void rowDoesNotExistAfterRollback() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                EMAIL);

        assertEquals(0, count);
    }
}
```

Ví dụ giả định bảng `account` tồn tại, email test chưa có trước khi chạy và `JdbcTemplate` dùng cùng datasource/transaction manager với test. `@AfterTransaction` chạy sau khi Spring đã rollback transaction, vì vậy truy vấn xác minh trạng thái ngoài transaction test. Trong một bộ test dùng dữ liệu chung, nên tạo định danh duy nhất hoặc chuẩn bị/xóa fixture để tránh xung đột với test khác.

`@BeforeTransaction` có thể được dùng tương tự để kiểm tra hoặc chuẩn bị trạng thái trước khi transaction bắt đầu:

```java
@BeforeTransaction
void verifyInitialState() {
    // Chạy trước khi Spring mở test-managed transaction.
}
```

Các callback này chỉ được gọi cho test có test-managed transaction. Chúng không thay thế `@BeforeEach`/`@AfterEach`; hai nhóm callback phục vụ các vị trí khác nhau trong vòng đời test.

## 6. Vòng đời transaction và callback JUnit

Với JUnit Jupiter và `SpringExtension`, các callback JUnit method như `@BeforeEach` và `@AfterEach` được chạy trong phạm vi test-managed transaction khi transaction đã được mở. `@BeforeAll` và `@AfterAll` chạy ngoài transaction của từng test method.

| Callback | Vị trí tương đối với test-managed transaction | Mục đích |
|---|---|---|
| `@BeforeTransaction` | Trước khi mở transaction | Kiểm tra hoặc chuẩn bị dữ liệu ngoài transaction |
| `@BeforeEach` | Sau khi transaction bắt đầu | Chuẩn bị fixture thuộc transaction test |
| `@Test` | Trong transaction | Thực hiện hành vi và assertion |
| `@AfterEach` | Trước khi transaction kết thúc | Assertion/cleanup trong transaction |
| Rollback/commit | Kết thúc transaction | Áp dụng chính sách kết thúc |
| `@AfterTransaction` | Sau khi transaction kết thúc | Kiểm tra trạng thái đã commit/rollback |

Điều này có ý nghĩa khi chọn nơi đặt cleanup. Nếu xóa dữ liệu trong `@AfterEach` mà thao tác xóa cũng nằm trong transaction sắp rollback, câu lệnh xóa có thể không được commit. Thường không cần xóa dữ liệu test được tạo trong cùng transaction vì rollback đã xử lý. Nếu cần cleanup ngoài transaction, dùng callback thích hợp và cân nhắc `REQUIRES_NEW` hoặc một cơ chế riêng có chủ đích.

## 7. Kiểm soát transaction bằng TestTransaction

`TestTransaction` là API của Spring TestContext cho phép test kiểm tra và điều khiển test-managed transaction trong lúc test đang chạy.

Các thao tác chính:

- `isActive()`: kiểm tra test-managed transaction hiện tại có đang hoạt động không.
- `flagForRollback()`: đánh dấu transaction hiện tại sẽ rollback khi kết thúc.
- `flagForCommit()`: đánh dấu transaction hiện tại sẽ commit khi kết thúc.
- `end()`: kết thúc transaction hiện tại theo cờ commit/rollback đã đặt.
- `start()`: bắt đầu một test-managed transaction mới nếu test được cấu hình để hỗ trợ.

Ví dụ:

```java
@Test
@Transactional
void commitsFirstTransactionAndStartsAnother() {
    jdbcTemplate.update(
            "insert into account(email) values (?)",
            "committed@example.test");

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    TestTransaction.start();
    jdbcTemplate.update(
            "insert into account(email) values (?)",
            "temporary@example.test");
}
```

Transaction đầu tiên được commit khi `end()` được gọi. Transaction thứ hai được mở lại và, nếu không đổi cờ kết thúc, sẽ rollback theo chính sách mặc định khi test method hoàn tất. Ví dụ giả định `jdbcTemplate` đã được inject và sử dụng transaction manager của test.

`TestTransaction` hữu ích khi cần xác minh trạng thái sau commit hoặc cần tạo nhiều giai đoạn transaction trong cùng một test. Với test thông thường, để Spring tự rollback sau method thường đơn giản và dễ hiểu hơn.

## 8. Flush persistence context trước khi assertion

Rollback chỉ xảy ra khi transaction kết thúc; nó không bảo đảm mọi thao tác ghi đã được gửi xuống database ngay tại thời điểm gọi repository. Với JPA/Hibernate, entity có thể vẫn nằm trong persistence context và SQL được trì hoãn đến lúc flush hoặc commit.

Điều này có thể khiến test tưởng rằng thao tác lưu thành công trong khi database chưa kiểm tra constraint hoặc chưa thực thi câu lệnh SQL.

Ví dụ với Spring Data JPA:

```java
@Test
@Transactional
void persistsEntityAndChecksDatabaseConstraint() {
    accountRepository.save(new Account("user@example.test"));

    entityManager.flush();

    assertEquals(1, accountRepository.countByEmail("user@example.test"));
}
```

`flush()` buộc persistence context đồng bộ các thay đổi đang chờ với database trong transaction hiện tại. Nó không commit transaction. Sau test, Spring vẫn rollback theo mặc định.

Nếu muốn chứng minh dữ liệu thực sự được đọc từ database thay vì chỉ từ first-level cache, có thể flush rồi clear persistence context trước khi truy vấn lại:

```java
accountRepository.save(account);
entityManager.flush();
entityManager.clear();

Account reloaded = accountRepository.findById(account.getId()).orElseThrow();
assertEquals("user@example.test", reloaded.getEmail());
```

`flush()` và `clear()` không thay thế rollback. Chúng phục vụ kiểm tra tương tác giữa persistence context và database trước khi transaction kết thúc.

## 9. Phạm vi rollback: những gì được hoàn tác và những gì không

Rollback mặc định chỉ có hiệu lực với các thao tác tham gia đúng transaction được Spring quản lý. Không nên hiểu nó như một cơ chế snapshot toàn bộ hệ thống.

| Thao tác | Có được rollback cùng test transaction? | Điều kiện/giải thích |
|---|---|---|
| JDBC insert/update/delete | Có | Dùng cùng datasource và transaction manager, trên transaction context hiện tại |
| JPA/Hibernate write | Có | EntityManager tham gia cùng transaction; flush không phải commit |
| Service `@Transactional(REQUIRED)` | Thường có | Tham gia transaction hiện tại nếu cùng transaction manager và thread |
| Service `REQUIRES_NEW` | Không nhất thiết | Tạo transaction độc lập; có thể commit trước khi test rollback |
| Database khác với transaction manager khác | Không tự động | Mỗi transaction manager quản lý tài nguyên riêng |
| HTTP request đến embedded server | Không | Server xử lý request trên thread và transaction riêng |
| `@Async` hoặc task chạy thread khác | Không tự động | Transaction thread-bound không được truyền tự động sang thread mới |
| Gửi email/message đến hệ thống ngoài | Không | Side effect bên ngoài database không được transaction JDBC/JPA hoàn tác |
| Ghi file hoặc gọi API bên ngoài | Không | Cần cleanup hoặc test double riêng |
| Sequence/identity của database | Tùy database | Một số bộ sinh số không quay lại giá trị trước rollback |
| DDL hoặc thao tác quản trị database | Tùy database | Một số DDL tự commit hoặc không nằm trong transaction như DML thông thường |

Nếu test cần xác minh nhiều tài nguyên cùng thay đổi, cần cơ chế phối hợp transaction phù hợp hoặc thiết kế cleanup riêng. Một transaction JDBC đơn không tự bảo đảm rollback email đã gửi hoặc request HTTP đã được xử lý ở một server thread khác.

### 9.1. REQUIRES_NEW

Một service method dùng `Propagation.REQUIRES_NEW` yêu cầu transaction độc lập. Transaction hiện tại của test có thể bị suspend trong lúc transaction mới chạy. Nếu transaction mới commit, rollback transaction ngoài không tự hoàn tác phần đã commit đó.

Vì vậy, khi test một service có `REQUIRES_NEW`, hãy xác định rõ mục tiêu: kiểm tra transaction độc lập có commit đúng không, hay cần dữ liệu được cleanup sau test. Đừng mặc định rollback của test sẽ xóa mọi bản ghi mà service tạo.

### 9.2. HTTP request qua embedded server

Trong test `@SpringBootTest(webEnvironment = RANDOM_PORT)`, request HTTP được xử lý bởi server trên thread riêng. Transaction của test method không tự bao trùm transaction của request server.

Ví dụ, test method có `@Transactional` gửi `POST /orders` qua `TestRestTemplate`. Server có thể tạo và commit order trong transaction riêng. Khi test method kết thúc, transaction phía test rollback nhưng order do server tạo vẫn còn.

Với server integration test, hãy dùng dữ liệu test có định danh riêng và cleanup qua repository/API hoặc reset database/schema theo chiến lược của dự án. Không dựa vào `@Transactional` trên test method để tự động rollback request được xử lý từ xa.

## 10. Lưu ý về timeout chạy trên thread khác

Spring TestContext thường gắn transaction với thread đang thực thi test. Một số API timeout chạy phần test trong thread khác để có thể ngắt khi hết thời gian. Khi đó, thao tác database trong thread phụ có thể không tham gia transaction của test.

Ví dụ nguy hiểm:

```java
assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    accountRepository.save(account);
});
```

JUnit Jupiter `assertTimeoutPreemptively` thực thi callback trong thread riêng. Transaction được Spring gắn với thread test ban đầu không tự truyền sang thread đó. Nếu repository mở transaction độc lập hoặc datasource hoạt động ngoài transaction test, thay đổi có thể được commit và tồn tại sau test.

Khi test cần bảo đảm rollback, hãy tránh đưa thao tác database vào callback preemptive timeout. Có thể dùng `assertTimeout` không preemptive nếu phù hợp, hoặc thiết kế test và transaction rõ ràng để mọi thao tác cần rollback chạy trên thread quản lý transaction. Nếu phải dùng thread khác, cần cleanup riêng.

## 11. Khi nào không nên dùng @Transactional cho test?

Không phải test nào cũng cần transaction:

- Unit test chỉ kiểm tra logic thuần không cần database.
- Test HTTP server thật cần quan sát dữ liệu đã commit ở transaction server.
- Test kiểm tra commit/rollback của service cần điều khiển transaction một cách tường minh.
- Test kiểm tra behavior của transaction propagation có thể cần nhiều transaction hoặc kiểm tra trạng thái bên ngoài transaction.
- Test dùng tài nguyên không tham gia transaction database cần cleanup riêng.

Nếu cần kiểm tra dữ liệu sau commit, có thể dùng `@Commit`, `TestTransaction.flagForCommit()` hoặc một integration test không bọc toàn bộ method trong test-managed transaction, tùy mục tiêu. Hãy tránh dùng `@Transactional` theo thói quen nếu nó làm test che mất hành vi commit thực tế của ứng dụng.

## 12. Một số thuộc tính @Transactional trong test

`@Transactional` trong Spring TestContext dùng transaction manager để quản lý transaction cho test. Không phải mọi thuộc tính của `@Transactional` đều có ý nghĩa giống hệt khi annotation được đặt trên service method.

Một số điểm cần lưu ý:

- `transactionManager` hoặc `value` giúp chọn transaction manager.
- `propagation = NOT_SUPPORTED` hoặc `NEVER` có thể được dùng để yêu cầu test không chạy trong test-managed transaction.
- Các thuộc tính khác cần được đối chiếu với tài liệu Spring TestContext của phiên bản đang sử dụng; không nên mặc định mọi propagation, timeout hoặc isolation setting của service method đều được áp dụng như trong luồng ứng dụng.
- `@Transactional` trên test class/method được xử lý bởi TestContext listener, còn annotation trên service method được xử lý bởi transaction infrastructure của ứng dụng.

Nếu mục tiêu là kiểm tra isolation level, timeout hoặc propagation của service, hãy kiểm tra hành vi qua service và transaction manager thực tế thay vì suy ra từ cấu hình test method. Một test-managed transaction có thể làm thay đổi bối cảnh transaction mà service nhận được.

## 13. Các lỗi thường gặp

**Cho rằng mọi test đều tự động rollback.** Chỉ test có test-managed transaction mới có chính sách rollback của Spring TestContext. Nếu không có `@Transactional`, không có transaction test tự động.

**Cho rằng test chỉ rollback khi thất bại.** Mặc định transaction rollback sau method ngay cả khi test thành công. `@Commit` hoặc `@Rollback(false)` mới yêu cầu commit.

**Dùng nhầm transaction manager.** Repository và test có thể sử dụng các transaction manager khác nhau. Hãy chỉ rõ `transactionManager` khi có nhiều manager và bảo đảm chúng quản lý cùng tài nguyên cần rollback.

**Cho rằng rollback xóa dữ liệu do server thread tạo.** HTTP request tới embedded server có transaction độc lập. Test cần cleanup dữ liệu do server ghi.

**Bỏ qua `REQUIRES_NEW`.** Transaction độc lập có thể commit dù transaction test bên ngoài rollback.

**Dùng preemptive timeout quanh thao tác database.** Callback chạy ở thread khác có thể không tham gia transaction của test và để lại dữ liệu đã commit.

**Không flush persistence context.** JPA có thể trì hoãn SQL đến cuối transaction. Hãy flush khi cần xác minh câu lệnh hoặc constraint database trước khi test kết thúc.

**Dùng `@AfterEach` để xóa dữ liệu trong transaction sắp rollback.** Thao tác cleanup đó cũng có thể bị rollback. Dùng rollback mặc định hoặc callback ngoài transaction theo mục tiêu.

**Commit dữ liệu dùng chung giữa các test.** Test sau có thể phụ thuộc dữ liệu từ test trước, khiến suite khó chạy riêng lẻ và khó chạy song song. Ưu tiên fixture độc lập.

**Cho rằng rollback hoàn tác mọi side effect.** Email, message, file, HTTP call và sequence database có thể không được hoàn tác. Cần test double, transaction coordination hoặc cleanup riêng.

## 14. Quy trình thiết kế test có rollback

Khi viết test persistence hoặc service cần transaction, hãy xác định:

1. Test có thật sự cần Spring-managed transaction không?
2. Transaction manager nào quản lý datasource hoặc tài nguyên được kiểm tra?
3. `@Transactional` được đặt ở class hay method?
4. Test có cần rollback mặc định hay phải commit để xác minh hành vi sau commit?
5. Các method `@BeforeEach`/`@AfterEach` có thao tác dữ liệu trong cùng transaction không?
6. Có service nào dùng `REQUIRES_NEW`, `NOT_SUPPORTED` hoặc chạy trên thread khác không?
7. Có request HTTP đến embedded server, `@Async`, timeout preemptive hoặc callback bất đồng bộ không?
8. Với JPA, có cần `flush()`/`clear()` để assertion phản ánh trạng thái database không?
9. Side effect ngoài transaction được cleanup hoặc cô lập thế nào?
10. Test có chạy độc lập, lặp lại và không phụ thuộc thứ tự không?

Với một test persistence thông thường, `@Transactional` ở cấp class hoặc method cùng rollback mặc định thường là đủ. Dùng `@Commit` hoặc `@Rollback(false)` chỉ khi cần giữ thay đổi sau method. Khi cần kiểm soát giữa chừng, dùng `TestTransaction`; khi cần xác minh trạng thái sau khi transaction kết thúc, dùng `@AfterTransaction`. Luôn nhớ rằng rollback chỉ hoàn tác những thao tác thực sự tham gia transaction test.

## 15. Tài liệu tham khảo

- [Spring Framework Reference — Transaction Management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): mô tả test-managed transaction, rollback mặc định, `@Commit`, `@Rollback`, callback và giới hạn transaction test.
- [Spring Framework Javadoc — @Transactional](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Transactional.html): mô tả annotation transaction và các thuộc tính.
- [Spring Framework Javadoc — TestTransaction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): API điều khiển transaction trong test.

Rollback mặc định là cơ chế giúp Spring TestContext giữ cho test persistence độc lập và có thể chạy lặp lại. Khi một test method có `@Transactional`, Spring mở transaction cho method và rollback sau khi method hoàn tất trừ khi test yêu cầu commit. Muốn dựa vào cơ chế này một cách an toàn, cần bảo đảm các thao tác cần hoàn tác tham gia cùng transaction, đồng thời quản lý riêng những side effect chạy ngoài transaction đó.
