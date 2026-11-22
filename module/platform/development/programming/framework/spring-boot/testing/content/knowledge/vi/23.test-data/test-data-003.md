# @Sql, @SqlGroup và thời điểm chạy SQL script trong kiểm thử Spring Boot

## 1. Vấn đề: dữ liệu test được chuẩn bị lúc nào và có thật sự được dọn không?

Một kiểm thử repository thường cần dữ liệu SQL nhất quán để xác minh một truy vấn hoặc một quy tắc nghiệp vụ. Việc tự gọi `jdbcTemplate.update(...)` trong từng method có thể nhanh, nhưng nếu nhiều test cần cùng một bộ dữ liệu, câu lệnh trùng lặp sẽ khó quản lý. Ngược lại, nếu chỉ tạo dữ liệu một lần khi application khởi động, các test có thể phụ thuộc thứ tự, ảnh hưởng lẫn nhau, hoặc không biết khi nào dữ liệu được rollback.

Spring TestContext có **`@Sql`**, **`@SqlGroup`** và **`@SqlConfig`** để định nghĩa chính xác SQL statement hoặc file script cần chạy **trước/sau test method** hoặc **trước/sau toàn test class**. `SqlScriptsTestExecutionListener` thực hiện các annotation này trong lifecycle của Spring TestContext.

Một khai báo tối thiểu:

~~~java
@Test
@Sql(scripts = "/sql/books.sql")
void findBooks() {
    // SQL được chạy trước method theo mặc định.
}
~~~

Đây là snippet minh họa. `/sql/books.sql` là đường dẫn tài nguyên trên classpath, không phải đường dẫn trên đĩa bắt đầu bằng thư mục root của hệ điều hành. Method chỉ chạy được khi test context có `DataSource` phù hợp và script thật tồn tại.

**Sau bài học, bạn có thể:**

1. Giải thích ai thực thi `@Sql` và các thời điểm `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS`, `AFTER_TEST_CLASS`.
2. Hiểu khác biệt giữa Spring Boot **`schema.sql`/`data.sql`** chạy lúc khởi tạo DataSource/ApplicationContext và Spring Test **`@Sql`** chạy theo test lifecycle.
3. Kết hợp nhiều `@Sql` bằng repeatable annotation hoặc **`@SqlGroup`**.
4. Phân biệt method-level `@Sql` mặc định **OVERRIDE** class-level `@Sql`, và **`@SqlMergeMode(MERGE)`** khi cần ghép cả hai.
5. Biết ngoại lệ: class-level `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` **không bị method-level `@Sql` ghi đè**.
6. Chọn `@SqlConfig(transactionMode = INFERRED)` hoặc `ISOLATED` theo mục tiêu rollback hay commit dữ liệu.
7. Hiểu **`AFTER_TEST_METHOD` thường chạy trước rollback của test-managed transaction**, do thứ tự listener; nó không tự bảo đảm dọn dữ liệu đã commit riêng.
8. Dùng `@AfterTransaction` để kiểm tra dữ liệu **sau rollback**, thay vì chỉ kiểm tra trong method.
9. Viết ví dụ Java 17 + **Spring Boot 3.3.5** + Gradle + `@JdbcTest` + H2 với các SQL files và **9 JUnit Jupiter `@Test` methods**.
10. Tránh SQL scripts chạy nhầm schema, rò dữ liệu khi dùng `ISOLATED`, lỗi resource path, tranh chấp thứ tự và test flaky trong CI.

**Ngữ cảnh cha “Dữ liệu kiểm thử”:** Bài này chỉ tập trung vào cơ chế tạo, nạp và dọn **SQL fixtures** trong Spring Boot testing. Không cần HTTP server, Spring MVC controller, Hibernate/JPA, R2DBC hoặc Testcontainers để hiểu lifecycle cơ bản. Những công nghệ khác có thể sử dụng `@Sql` nếu test context đáp ứng yêu cầu DataSource/transaction manager, nhưng bản mẫu cố định ở JDBC/H2 để quan sát rõ.

**Phiên bản cố định:** Java 17, Spring Boot **3.3.5**, Spring Framework **6.1.x** do Boot BOM chọn, Gradle, H2 và JUnit Jupiter. Đặc biệt, `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` xuất hiện từ **Spring Framework 6.1**; đừng lấy ví dụ này áp nguyên vào một dự án Spring 5.x rồi giả định có cùng enum constants.

## 2. Ai thực thi @Sql và vì sao annotation có hiệu lực?

`@Sql` thuộc package `org.springframework.test.context.jdbc`, không phải `org.springframework.boot` và không phải annotation của JUnit. Spring TestContext đăng ký `SqlScriptsTestExecutionListener` trong bộ listener mặc định khi tích hợp Spring testing. Listener đọc annotation trên test class và test method, giải quyết paths/configuration, rồi thực thi script thông qua hạ tầng Spring JDBC.

~~~text
Spring TestContext
  |
  | SqlScriptsTestExecutionListener
  +-- beforeTestClass()   -> @Sql BEFORE_TEST_CLASS
  |
  +-- beforeTestMethod()  -> @Sql BEFORE_TEST_METHOD
  |                          (mặc định khi không khai báo phase)
  |
  +-- JUnit @BeforeEach, @Test, @AfterEach
  |
  +-- afterTestMethod()   -> @Sql AFTER_TEST_METHOD
  |
  +-- afterTestClass()    -> @Sql AFTER_TEST_CLASS
~~~

Mỗi `@Sql` có thể chỉ định:
- **`scripts`**: một hoặc nhiều file `.sql`.
- **`statements`**: một hoặc nhiều SQL statements inline.
- **`executionPhase`**: giai đoạn thực thi.
- **`config = @SqlConfig(...)`**: parsing, error handling và transaction mode cho bộ script đó.

**Bắt buộc có hạ tầng database:** Listener cần `DataSource`, và có thể cần `PlatformTransactionManager` tùy `transactionMode`. Trong dự án mẫu, `@JdbcTest` + Spring Boot Starter JDBC + H2 tạo DataSource, JdbcTemplate và transaction manager phù hợp. Nếu ứng dụng có nhiều database/transaction managers, cần chọn đúng bean thông qua `@SqlConfig(dataSource = "...", transactionManager = "...")` thay vì mặc định để Spring tìm.

**Không gọi JDBC resources bằng tay trong annotation.** File ở test classpath, việc thực thi do listener thực hiện. Nếu resource không có, SQL syntax sai hoặc DataSource không tồn tại, test setup/teardown có thể thất bại trước khi code trong `@Test` chạy, hoặc sau khi code hoàn thành.

### 2.1. Vị trí đặt annotation và đường dẫn tài nguyên

~~~java
// Trên class: mặc định chạy trước MỖI method trong class.
@Sql(scripts = "/sql/base-books.sql")
class BookRepositoryTest {

    @Test
    void testOne() { }

    @Test
    void testTwo() { }
}
~~~

Đây là snippet mô tả annotation. `@Sql` đặt trên **class** với phase mặc định không có nghĩa “chỉ chạy một lần trước cả class”; nó được áp dụng **trước từng test method**. Muốn một lần trước cả class, dùng `executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS` và Spring Framework 6.1+.

Đường dẫn script:
- `"/sql/base-books.sql"`: **tuyệt đối trong classpath**, tương ứng file `src/test/resources/sql/base-books.sql`.
- `"base-books.sql"` không có `/`: tài nguyên **tương đối với package của test class**. Với package `demo.sql`, đó thường là `demo/sql/base-books.sql` trong classpath.
- `"classpath:sql/base-books.sql"`: resource có prefix classpath rõ.
- Dùng đường dẫn `file:` đến một file ngoài project chỉ khi có lý do và môi trường chạy ổn định; đường dẫn tuyệt đối trên máy cá nhân thường làm CI fail.

**Đường dẫn mặc định khi không có `scripts` và `statements`:** Nếu đặt `@Sql` trên class `demo.sql.BookTest`, Spring tìm resource dạng `classpath:demo/sql/BookTest.sql`. Nếu đặt trên method `findBook()` của class đó, Spring tìm `classpath:demo/sql/BookTest.findBook.sql`. Không tìm thấy default script thì báo `IllegalStateException`; tốt nhất với bài học và dự án nhiều người dùng là ghi đường dẫn tường minh để dễ tìm lỗi.

## 3. Bốn thời điểm thực thi: method và class không giống nhau

### 3.1. BEFORE_TEST_METHOD — mặc định

~~~java
@Test
@Sql(
    scripts = "/sql/base-books.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
void hasSeededBooks() {
    // Test nhìn thấy dữ liệu seed trước lúc chạy.
}
~~~

Annotation có thể bỏ `executionPhase` vì **BEFORE_TEST_METHOD là mặc định**. Với transactional test (`@JdbcTest`, `@DataJpaTest`, hoặc test `@Transactional` có transaction manager), script ở phase này thường chạy **bên trong transaction đã mở của test** và được rollback sau method. Nó giúp mỗi test có cùng fixture mà không cần viết `@BeforeEach` với nhiều câu INSERT.

**Thứ tự trong JUnit Jupiter:** Spring `beforeTestMethod` callbacks xảy ra trước `@BeforeEach` và trước code `@Test`. Vì thế nếu `@BeforeEach` query database, dữ liệu do `BEFORE_TEST_METHOD` seed đã có thể được nhìn thấy trong test transaction.

### 3.2. AFTER_TEST_METHOD — sau method nhưng thường trước rollback

~~~java
@Test
@Sql(
    scripts = "/sql/after-method.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void businessTest() {
    // Sau method, listener mới chạy file after-method.sql.
}
~~~

**Đây là điểm dễ nhầm nhất.** Trong Spring TestContext, `TransactionalTestExecutionListener` có order **4000**, còn `SqlScriptsTestExecutionListener` có order **5000**. Các listener `beforeTestMethod` chạy theo thứ tự tăng (transaction mở trước, SQL chạy sau), còn `afterTestMethod` chạy theo **thứ tự ngược** (SQL after chạy trước, rồi test transaction mới kết thúc/rollback).

Do đó, với `@JdbcTest` mặc định transactional và `@SqlConfig` mặc định `INFERRED`, một `AFTER_TEST_METHOD` SQL script có thể được thực thi **vẫn trong transaction của test**, rồi bị rollback cùng tất cả DML của test. Đừng kết luận rằng vì phase có chữ AFTER nên nó chạy *sau rollback*. Dùng `@AfterTransaction` để quan sát dữ liệu sau khi rollback thật sự hoàn tất.

**`@AfterEach` và `AFTER_TEST_METHOD`:** JUnit `@AfterEach` chạy trước Spring TestContext `afterTestMethod` callback. Vì vậy `@AfterEach` không phải nơi để khẳng định SQL script có `executionPhase=AFTER_TEST_METHOD` đã chạy. Nó cũng vẫn nằm trong transaction của test nếu test transactional.

### 3.3. BEFORE_TEST_CLASS — một lần trước toàn class (Spring 6.1+)

~~~java
@Sql(
    scripts = "/sql/class-before.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
)
class ClassPhaseExample {
    // Script chạy một lần trước mọi test method.
}
~~~

Phase class được dùng khi muốn chuẩn bị một trạng thái chung cho cả class, chẳng hạn reference data hoặc bảng phụ. **Nó không có test-managed transaction của một method để tự rollback**. Nếu có transaction manager và `INFERRED` nhưng chưa có transaction hiện hành, Spring có thể mở **transaction mới được commit ngay**. Vì vậy dữ liệu này thường tồn tại qua nhiều method trong class, không tự biến mất sau rollback từng method.

**Không dùng class-phase seed như một fixture thay đổi tùy method.** Với các bản ghi có thể bị test update, nên dùng method-phase và transaction rollback hoặc database isolation. Class phase thường phù hợp với dữ liệu reference bất biến/được cleanup rõ.

### 3.4. AFTER_TEST_CLASS — một lần sau toàn class (Spring 6.1+)

~~~java
@Sql(
    scripts = "/sql/class-after.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
)
class ClassPhaseExample {
    // Script chạy khi các method của class đã hoàn tất.
}
~~~

Phase này có thể dọn dữ liệu được commit trong BEFORE_TEST_CLASS. Nhưng **không** bảo đảm lớp test khác chạy sau sẽ thấy trạng thái đã dọn nếu test classes được chạy song song hoặc dùng chung database/schema mà không cô lập. Khi test class setup có side effects trên external database, phải bảo đảm cleanup, dùng namespace/keys riêng, và không dựa vào thứ tự suite.

**Ngoại lệ quan trọng:** Class-level `@Sql` với `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` **không bị một method-level `@Sql` OVERRIDE**; các phase class vẫn chạy một lần trước/sau class. Các quy tắc ghi đè thông thường áp dụng cho SQL declarations phase method.

### 3.5. Bảng timeline tổng hợp

| Phase | Chạy mấy lần? | Thời điểm | Khi test @JdbcTest transactional? |
|---|---:|---|---|
| `BEFORE_TEST_CLASS` | Một lần mỗi class | Trước các test methods | Không có TX test method; thường commit riêng |
| `BEFORE_TEST_METHOD` | Trước từng method | Sau khi test transaction bắt đầu, trước JUnit @BeforeEach | Thường ở trong TX test; rollback cuối method |
| `AFTER_TEST_METHOD` | Sau từng method | Sau JUnit @AfterEach, trước transaction rollback theo listener mặc định | Thường trong TX test; rollback cuối method |
| `AFTER_TEST_CLASS` | Một lần mỗi class | Sau tất cả test methods | Không có TX test method; thường commit riêng |

Không đưa ra kết luận chung cho mọi project không có transaction manager hoặc có `@SqlConfig(ISOLATED)`: lúc đó hành vi commit/rollback khác. Bảng trên mô tả Spring TestContext với mặc định áp dụng cho JDBC test có transaction manager.

## 4. @SqlGroup, @Sql repeatable và cách sắp xếp script

### 4.1. @Sql có thể xuất hiện nhiều lần

Trong Java, `@Sql` là annotation có thể lặp lại. Hai cách viết sau cùng thể hiện nhiều tập SQL với các cấu hình/phase riêng.

**Repeatable @Sql:**

~~~java
@Test
@Sql(
    scripts = "/sql/seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void testWithTwoPhases() {
    // Không phải file đầy đủ; seed.sql và cleanup.sql cần tồn tại.
}
~~~

**@SqlGroup:**

~~~java
@Test
@SqlGroup({
    @Sql(
        scripts = "/sql/seed.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    ),
    @Sql(
        scripts = "/sql/cleanup.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
})
void testWithGroup() {
    // Tương đương cấu trúc lặp phía trên.
}
~~~

`@SqlGroup` là **container annotation** cho các `@Sql`, không phải cơ chế “giao dịch chung mới”. Mỗi phần tử `@Sql` có thể chỉ định script, inline statement, phase và config riêng. Các mục cùng phase được xử lý theo khai báo tương ứng; script cần bảng mà script khác tạo ra nên được sắp xếp có chủ đích. Một nhóm có `BEFORE` và `AFTER` được phân vào đúng lifecycle phase chứ không chạy liền nhau trước method chỉ vì đứng cạnh nhau trong mảng.

Nếu cùng phase cần một chuỗi nhiều script, bạn cũng có thể viết:

~~~java
@Sql(scripts = {
    "/sql/create-reference-data.sql",
    "/sql/create-test-orders.sql"
})
~~~

Spring thực thi các scripts đã liệt kê theo thứ tự cấu hình; nên tránh phụ thuộc vào thứ tự không xác định của tập tin glob hay test methods. Để khởi tạo schema trong ứng dụng, cân nhắc Flyway/Liquibase; `@Sql` phù hợp để tạo test-specific data.

### 4.2. Ghi đè theo mặc định: method-level OVERRIDE class-level

Xét:

~~~java
@Sql("/sql/base-books.sql")
class BookTest {

    @Test
    void normalTest() {
        // base-books.sql chạy trước.
    }

    @Test
    @Sql("/sql/one-book.sql")
    void specialTest() {
        // Mặc định class-level script bị OVERRIDE.
        // Chỉ one-book.sql được chạy trước method này.
    }
}
~~~

Đừng tưởng method-level script **tự động được thêm** vào class-level script. Mặc định Spring dùng `SqlMergeMode.MergeMode.OVERRIDE`. Khi thêm `@Sql` vào method, class-level BEFORE/AFTER method-phase declarations có thể không chạy cho method đó. Nếu bạn trông chờ dữ liệu nền vẫn có, test sẽ báo thiếu row hoặc foreign-key violation.

### 4.3. Gộp rõ ràng bằng @SqlMergeMode(MERGE)

~~~java
@Sql("/sql/base-books.sql")
class BookTest {

    @Test
    @Sql("/sql/one-book.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void specialTest() {
        // class-level base-books.sql + method-level one-book.sql.
    }
}
~~~

`MERGE` cho phép fixture chung của class được thực thi **cùng với** fixture riêng của method. Class-level scripts trong cùng method-phase được áp dụng trước method-level scripts, thích hợp khi script bổ sung có foreign key trỏ tới dữ liệu nền. Bạn có thể khai báo `@SqlMergeMode(MERGE)` trên class để làm mặc định cho các methods, rồi đặt `@SqlMergeMode(OVERRIDE)` trên method cụ thể cần thay thế. Method-level merge mode có độ ưu tiên hơn class-level.

**Lưu ý:** `@SqlMergeMode` không thay đổi quy tắc `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` nêu ở phần 3; hai phase class là độc lập và không bị method-level scripts bỏ qua.

## 5. Transaction mode: INFERRED, ISOLATED và nguy cơ dữ liệu rò

Một `@Sql` không tự mặc định “commit tất cả”, cũng không tự mặc định “rollback tất cả”; nó hỏi Spring TestContext xem có transaction hiện hành và transaction manager phù hợp hay không.

### 5.1. INFERRED — lựa chọn mặc định

`SqlConfig.TransactionMode.INFERRED` suy luận:
1. Không có DataSource lẫn transaction manager → không thể thực thi script.
2. Có DataSource nhưng không có transaction manager → thực thi trực tiếp qua DataSource, không có Spring-managed transaction.
3. Có transaction manager và đang có transaction (ví dụ test-managed TX) → script thường **tham gia transaction hiện có**.
4. Có transaction manager nhưng chưa có transaction → mở **transaction mới**, chạy script, rồi **commit ngay**.

Đối với `@JdbcTest` mặc định transactional, **BEFORE_TEST_METHOD** script chạy trong transaction test và dữ liệu seed được rollback cuối method. **AFTER_TEST_METHOD** script theo listener mặc định cũng thường chạy trước rollback, nên các DML của nó cùng bị rollback. Đối với **BEFORE_TEST_CLASS** và **AFTER_TEST_CLASS**, không có test-managed transaction của một method, nên scripts thường commit.

### 5.2. ISOLATED — giao dịch độc lập và commit

~~~java
@Sql(
    scripts = "/sql/seed-for-external-client.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    ),
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

Đây là snippet annotation, không phải source class hoàn chỉnh. ISOLATED yêu cầu transaction manager và DataSource có thể phân giải được; Spring mở **transaction độc lập**, thực thi và commit, kể cả khi test method có transaction riêng. Nó có ích khi một HTTP server thread/async worker cần nhìn thấy fixture đã commit, nhưng **dữ liệu committed không tự bị test rollback xóa**.

Một cặp BEFORE/AFTER script `ISOLATED` có thể được dùng để seed rồi dọn dữ liệu đã commit:

~~~java
@SqlGroup({
    @Sql(
        scripts = "/sql/seed-committed.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        ),
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    ),
    @Sql(
        scripts = "/sql/delete-committed.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        ),
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
})
~~~

Hai scripts trong snippet chỉ để minh họa cấu hình; cần định nghĩa và thử với database disposable. Nếu test bỏ qua callback teardown vì JVM chết, SQL fails hoặc thread tiếp tục ghi sau cleanup, dữ liệu vẫn có thể tồn tại. Không dùng pattern này trên database chia sẻ khi có cách cô lập tốt hơn.

**Không trộn một INSERT ISOLATED với DELETE INFERRED rồi mặc định rằng cleanup sẽ bền vững.** Nếu DELETE chạy trong test-managed transaction và rollback, dữ liệu committed bởi INSERT ISOLATED **sẽ trở lại** sau rollback. Mọi cleanup của dữ liệu được commit riêng cũng phải có transaction/teardown rõ ràng.

### 5.3. @SqlConfig: thiết lập parsing và error policy

Ngoài transaction mode, `@SqlConfig` cho phép cấu hình encoding, statement separator, comment delimiters, error handling, DataSource và transaction manager names. Ví dụ:

~~~java
@Sql(
    scripts = "/sql/seed-utf8.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";"
    )
)
~~~

Đây là snippet, không thuộc files runnable ở mục 7. Với script có cú pháp đặc thù stored procedures hoặc SQL dialect, dấu `;` có thể không đủ làm separator; hãy kiểm tra config phù hợp thay vì cố làm script parser bỏ qua syntax errors. Đừng đặt `errorMode` bỏ qua mọi lỗi chỉ để test xanh; một script bị lỗi giữa chừng có thể để lại fixture không đầy đủ.

**Cấu hình toàn class và cục bộ:** `@SqlConfig` đặt trên class là global config cho các `@Sql` trong class hierarchy, còn `@Sql(config=@SqlConfig(...))` có thể override thuộc tính rõ ràng. Các giá trị `DEFAULT`/rỗng trong local config thường thừa hưởng từ global theo quy tắc Spring. Nếu project nhiều DataSource, cấu hình tên bean cụ thể và test rằng script vào đúng database.

## 6. Project hoàn chỉnh: Spring Boot 3.3.5, Java 17, Gradle, H2

Ví dụ được thiết kế để **chạy độc lập, không cần PostgreSQL, Redis hay HTTP server**. Để phân biệt các phases, ta dùng ba bảng:
- **books**: fixture trước từng method; các INSERT trong transaction được rollback sau method.
- **phase_events**: marker mà một AFTER_TEST_METHOD script `ISOLATED` cố ý commit để chứng minh nó chạy ở phase sau; `@AfterTransaction` kiểm và dọn bằng `finally`.
- **class_events**: marker được BEFORE_TEST_CLASS tạo một lần, AFTER_TEST_CLASS xóa một lần.

**Không dùng test database production.** Ví dụ chỉ dùng H2 embedded, IDs riêng cho từng demo, không cần shared database. Hầu hết fixture chỉ tồn tại trong transaction test; mọi side effect commit độc lập có cleanup.

### 6.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/java/demo/sql/SqlLessonApplication.java
src/test/resources/schema.sql
src/test/resources/sql/base-books.sql
src/test/resources/sql/one-book.sql
src/test/resources/sql/after-method-marker.sql
src/test/resources/sql/class-before.sql
src/test/resources/sql/class-after.sql
src/test/java/demo/sql/SqlMergeModeTest.java
src/test/java/demo/sql/SqlGroupTimingTest.java
src/test/java/demo/sql/SqlClassPhasesTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'sql-test-script-lifecycle'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Lý giải Gradle:** starter-jdbc cung cấp Spring JDBC và transaction support; H2 nằm trên test runtime classpath; starter-test có JUnit Jupiter, Spring Test, AssertJ và công cụ test. Spring Boot dependency management chọn versions của Spring Framework 6.1/H2 tương thích. Không thêm Spring Data JPA để tránh pha trộn khái niệm entity flush/persistence context vào bài @Sql cơ bản.

**src/main/java/demo/sql/SqlLessonApplication.java**

~~~java
package demo.sql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(SqlLessonApplication.class, args);
    }
}
~~~

Spring Boot application class ở package demo.sql giúp `@JdbcTest` tìm được `@SpringBootConfiguration` trong package hierarchy, dù slice không tải toàn ứng dụng. Không có REST endpoint hay service business trong ví dụ.

### 6.2. Schema SQL tạo một lần khi test context khởi động

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(100) NOT NULL
);

CREATE TABLE phase_events (
    code VARCHAR(40) PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);

CREATE TABLE class_events (
    code VARCHAR(40) PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);
~~~

`schema.sql` được Spring Boot SQL initialization xử lý lúc tạo H2 embedded DataSource/ApplicationContext, **không phải vì annotation @Sql**. Điều này khác hoàn toàn với `/sql/base-books.sql` chỉ chạy theo test lifecycle. Bài không cung cấp `data.sql` mặc định, vì dữ liệu cố tình được nạp bằng `@Sql`.

**Không nhầm thứ tự:**
1. Boot khởi tạo H2 DataSource, chạy schema.sql.
2. Spring TestContext chạy class-level BEFORE_TEST_CLASS (nếu class có).
3. Trước mỗi test method, Spring mở test-managed transaction rồi chạy @Sql BEFORE_TEST_METHOD.
4. Sau method, @Sql AFTER_TEST_METHOD chạy theo listener order.
5. Spring rollback test transaction.
6. Sau toàn class, @Sql AFTER_TEST_CLASS chạy nếu có.

Nếu dùng Flyway/Liquibase để tạo schema, không để `schema.sql` và migrations cùng tạo một bảng rồi tranh chấp. Với database thật, chọn một nguồn schema migration được kiểm soát.

### 6.3. Các fixture SQL

**src/test/resources/sql/base-books.sql**

~~~sql
INSERT INTO books (id, title) VALUES (1, 'Spring Testing');
INSERT INTO books (id, title) VALUES (2, 'SQL Fixtures');
~~~

**src/test/resources/sql/one-book.sql**

~~~sql
INSERT INTO books (id, title) VALUES (90, 'Method Only');
~~~

**src/test/resources/sql/after-method-marker.sql**

~~~sql
INSERT INTO phase_events (code, note)
VALUES ('AFTER_METHOD', 'committed after-method marker');
~~~

**src/test/resources/sql/class-before.sql**

~~~sql
INSERT INTO class_events (code, note)
VALUES ('CLASS_READY', 'created once before test class');
~~~

**src/test/resources/sql/class-after.sql**

~~~sql
DELETE FROM class_events
WHERE code = 'CLASS_READY';
~~~

**Giải thích cấu trúc fixture:**
- base-books.sql và one-book.sql chỉ INSERT, không DROP bảng.
- Một test với OVERRIDE chỉ thấy book id=90; test với MERGE thấy cả 1,2,90.
- after-method-marker.sql ghi vào bảng khác với fixture books, tránh test-managed transaction T1 giữ lock trên cùng hàng mà isolated script T2 cần sửa.
- class-before.sql và class-after.sql là một cặp setup/teardown theo class. Chúng dùng cùng marker với PK ổn định; chạy trên H2 disposable và không bật parallel execution với shared schema.
- Tất cả SQL resource paths trong annotation bắt đầu bằng `/sql/`, trỏ tới tệp bên dưới `src/test/resources/sql/`.

### 6.4. Test 1 — @Sql mặc định OVERRIDE và @SqlMergeMode(MERGE)

**src/test/java/demo/sql/SqlMergeModeTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Sql(
        scripts = "/sql/base-books.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class SqlMergeModeTest {

    @Autowired
    JdbcTemplate jdbc;

    long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }

    @Test
    void classLevelSqlRunsBeforeEachMethod() {
        assertEquals(2L, countBooks());
        assertEquals(
                "Spring Testing",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 1L));
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    void methodSqlOverridesClassSqlByDefault() {
        // Method-level @Sql -> default OVERRIDE.
        assertEquals(1L, countBooks());
        assertEquals(
                "Method Only",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 90L));
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void mergeRunsClassFixtureBeforeMethodFixture() {
        assertEquals(3L, countBooks());
        assertEquals(
                "SQL Fixtures",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 2L));
        assertEquals(
                "Method Only",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 90L));
    }

    @Test
    @Sql(statements = {
            "INSERT INTO books (id, title) VALUES (91, 'Inline SQL')"
    })
    void inlineStatementsAlsoOverrideClassScript() {
        assertEquals(1L, countBooks());
        assertEquals(
                "Inline SQL",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 91L));
    }
}
~~~

**Bốn điều test class này xác nhận:**

1. Khi không có method-level `@Sql`, class-level fixture seed hai hàng **trước mỗi test method**, không chỉ một lần cho cả class.
2. Khi method có riêng `@Sql("/sql/one-book.sql")`, mặc định `OVERRIDE`, nên **chỉ** có id=90 và không có hai row nền.
3. Khi method thêm `@SqlMergeMode(MERGE)`, class-level scripts được thực thi trước method-level scripts, nên **có ba row** id=1,2,90.
4. `statements` inline cũng là một method-level `@Sql`: nó OVERRIDE class-level fixture theo mặc định và tạo id=91.

Những rows của từng method được INSERT trong **test-managed transaction** của @JdbcTest và rollback sau method. Bộ test không phụ thuộc thứ tự method; nếu id=90 còn từ một method trước, assert count sẽ bắt sai. Trong project mẫu, cơ chế rollback chính xác nên data luôn độc lập.

**Góc kỹ thuật quan trọng:** Việc có `@Sql` class-level không yêu cầu đặt `@BeforeEach` để gọi script. `SqlScriptsTestExecutionListener` chạy script trước JUnit lifecycle `@BeforeEach`; tests chỉ cần đọc dữ liệu.

### 6.5. Test 2 — @SqlGroup BEFORE/AFTER_METHOD, ISOLATED và @AfterTransaction

Class này minh họa sự khác nhau giữa **mốc chạy** và **transaction mode**. `base-books.sql` chạy trước method trong test-managed transaction nên rollback. `after-method-marker.sql` chạy sau method nhưng với `@SqlConfig(ISOLATED)` nên tạo một transaction riêng và **commit**. `@AfterTransaction` kiểm marker **sau rollback**, rồi dọn marker ở `finally`.

**src/test/java/demo/sql/SqlGroupTimingTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.jdbc.SqlGroup;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@SqlGroup({
        @Sql(
                scripts = "/sql/base-books.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD),
        @Sql(
                scripts = "/sql/after-method-marker.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
                config = @SqlConfig(
                        transactionMode =
                                SqlConfig.TransactionMode.ISOLATED))
})
class SqlGroupTimingTest {

    @Autowired
    JdbcTemplate jdbc;

    long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }

    long countMarker() {
        return jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM phase_events
                WHERE code = 'AFTER_METHOD'
                """,
                Long.class);
    }

    @Test
    void beforeMethodDataIsVisibleButAfterMarkerIsNotYetThere() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertEquals(2L, countBooks());
        assertEquals(0L, countMarker());
    }

    @Test
    void methodWritesAreRolledBackEvenWhenAfterScriptCommits() {
        assertEquals(2L, countBooks());
        jdbc.update(
                "INSERT INTO books (id, title) VALUES (?, ?)",
                3L, "Only During Test");

        assertEquals(3L, countBooks());
        assertEquals(0L, countMarker());
    }

    @AfterTransaction
    void verifyStateAfterTestRollbackAndAlwaysRemoveMarker() {
        assertFalse(TestTransaction.isActive());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());

        try {
            // AFTER_TEST_METHOD + ISOLATED đã commit.
            assertEquals(1L, countMarker());

            // BEFORE_TEST_METHOD và các writes trong test đã rollback.
            assertEquals(0L, countBooks());
        } finally {
            // Cleanup độc lập: không nằm trong transaction đã rollback.
            jdbc.update(
                    "DELETE FROM phase_events WHERE code = ?",
                    "AFTER_METHOD");
        }
    }
}
~~~

**Thứ tự thực tế của một method trong class này:**

~~~text
(1) Spring Test mở TX-A cho @JdbcTest.
(2) @Sql BEFORE_TEST_METHOD -> base-books.sql trong TX-A.
(3) JUnit @Test -> thấy 2 books; không thấy AFTER_METHOD marker.
(4) JUnit @AfterEach (nếu có) -> vẫn trước after-method SQL.
(5) @Sql AFTER_TEST_METHOD -> marker script trong TX-B ISOLATED.
(6) TX-B commit -> phase_events có marker.
(7) Spring Test rollback TX-A -> base books và test insert biến mất.
(8) @AfterTransaction -> thấy marker=1, books=0; finally DELETE marker.
~~~

**Vì sao không dùng DELETE cùng books trong ISOLATED AFTER script?** Book rows ở bước (2) vẫn chưa commit trong TX-A. Một transaction độc lập không thể mặc nhiên nhìn thấy hoặc xóa các rows uncommitted đó, và có thể chờ lock. Để demo chắc chắn, AFTER script ghi **bảng marker riêng**, không tranh chấp rows với TX-A.

**Đây không phải mô hình cleanup mặc định cho mọi dự án.** Nó cố ý cho thấy `ISOLATED` có side effect committed mà @JdbcTest rollback không thu hồi. Nếu không cần fixture committed, nên để `INFERRED`/transaction test rollback tự dọn, không tạo marker riêng. Nếu cần seed committed cho HTTP integration test, cleanup phải cùng transaction scope phù hợp hoặc dùng disposable database.

**Tính độc lập của tests:** `@AfterTransaction` chạy sau mỗi method có test-managed transaction. Code dùng `finally` để dọn marker kể cả khi assertion thất bại; nhưng nếu JVM bị kill hoặc script/connection bị lỗi trước cleanup, marker có thể tồn tại. Vì vậy project phải chạy trên H2 disposable, không trên database chia sẻ, không bật parallel tests cùng marker ID.

### 6.6. Test 3 — @SqlGroup BEFORE_TEST_CLASS và AFTER_TEST_CLASS

Hai class phases có từ Spring Framework 6.1. Trong `SqlClassPhasesTest`, BEFORE_TEST_CLASS insert một marker CLASS_READY đã commit, các methods có thể nhìn thấy marker đó. Rollback từng method **không** xóa marker committed. AFTER_TEST_CLASS xóa marker sau khi cả class kết thúc.

**src/test/java/demo/sql/SqlClassPhasesTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlGroup;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@SqlGroup({
        @Sql(
                scripts = "/sql/class-before.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS),
        @Sql(
                scripts = "/sql/class-after.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
})
class SqlClassPhasesTest {

    @Autowired
    JdbcTemplate jdbc;

    long classMarkerCount() {
        return jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM class_events
                WHERE code = 'CLASS_READY'
                """,
                Long.class);
    }

    @Test
    void classSetupIsVisibleInsideFirstTransactionalMethod() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1L, classMarkerCount());
    }

    @Test
    void classMarkerIsSeparateFromMethodLocalWrites() {
        assertEquals(1L, classMarkerCount());

        jdbc.update(
                "INSERT INTO books (id, title) VALUES (?, ?)",
                500L, "Temporary Book");

        long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE id = ?",
                Long.class, 500L);

        assertEquals(1L, count);
        // Method insert sẽ rollback; class marker thì vẫn committed.
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    void methodSqlDoesNotOverrideClassPhases() {
        assertEquals(1L, classMarkerCount());

        long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE id = ?",
                Long.class, 90L);

        assertEquals(1L, count);
    }
}
~~~

**Ba tests không dựa vào thứ tự chạy**: tên test đầu có chữ “First” chỉ là tên diễn giải, không cần JUnit sắp thứ tự. Cả ba đều mong class marker đã được tạo **trước bất kỳ test method nào**. Một method INSERT book 500, nhưng row được rollback cuối method nên không gây ảnh hưởng cho test khác. Method-level @Sql one-book chạy riêng trong transaction của method; nó **không vô hiệu** class-level BEFORE_TEST_CLASS hoặc AFTER_TEST_CLASS.

**Tại sao AFTER_TEST_CLASS không có assertion trực tiếp trong class?** Nó chạy **sau toàn bộ methods và JUnit @AfterAll**, nên không thể assert “đã cleanup” ngay bên trong một @Test method mà không đi ngược lifecycle. Nếu cần chứng minh cleanup ở cấp độ suite, dùng test harness/extension hoặc database disposable được kiểm soát, không dựa vào class B “may mắn chạy sau class A”. Ví dụ tập trung vào kiến thức về phase và việc tránh test-order coupling.

**Cảnh báo về class-level data:** Nếu test classes chạy song song trên cùng schema và dùng cùng class marker key, class-before có thể đụng khóa hoặc class-after dọn dữ liệu của class khác. Trong CI lớn hãy dùng unique namespace/schema/DB per test class hoặc giữ dữ liệu ở transaction method thay vì shared committed state.

## 7. Tổng số tests và lệnh chạy

Project có chính xác **9 phương thức `@Test`**:

| Test class | Số method | Nội dung |
|---|---:|---|
| `SqlMergeModeTest` | **4** | class fixture, method OVERRIDE, MERGE, inline statements |
| `SqlGroupTimingTest` | **2** | BEFORE/AFTER_METHOD, ISOLATED marker, rollback và @AfterTransaction |
| `SqlClassPhasesTest` | **3** | BEFORE/AFTER_CLASS, phạm vi class và method-level SQL |
| **Tổng** | **9** | Không có method @Disabled trong ví dụ hoàn chỉnh |

**Kết quả dự kiến:** cả 9 tests PASS khi chạy theo source, SQL files và dependencies đã nêu; rollback/teardown để lại bảng rỗng ở cuối các test classes trong môi trường H2 disposable. Đây là kết quả **dự kiến từ thiết kế và phân tích**, không phải tuyên bố rằng tests đã được chạy trong máy của người đọc.

Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu vừa chép source mà chưa tạo Gradle Wrapper scripts/JAR, `./gradlew` chưa tồn tại; dùng Gradle tương thích để tạo wrapper hoặc tạm chạy `gradle test`. Xem báo cáo ở:

~~~text
build/reports/tests/test/index.html
~~~

Chạy riêng lớp để kiểm phạm vi:

~~~bash
./gradlew test --tests demo.sql.SqlMergeModeTest
./gradlew test --tests demo.sql.SqlGroupTimingTest
./gradlew test --tests demo.sql.SqlClassPhasesTest
~~~

**Nếu test group fail do marker trùng PK:** hãy xác nhận chỉ chạy trên H2 mới/đã được dọn, rằng @AfterTransaction có chạy và class/suite không chạy song song với key chung. Không xóa dữ liệu tùy tiện trong database dùng chung để ép test pass. Một fixture có side effects committed phải được làm sạch đúng transaction và đúng test scope.

### 7.1. Kiểm tra đúng thứ tự mà không phụ thuộc tên method

Hãy quan sát:
- `SqlMergeModeTest.classLevelSqlRunsBeforeEachMethod()` thấy **2** rows.
- `methodSqlOverridesClassSqlByDefault()` thấy **1** row (90).
- `mergeRunsClassFixtureBeforeMethodFixture()` thấy **3** rows (1,2,90).
- `inlineStatementsAlsoOverrideClassScript()` thấy **1** row (91).
- `SqlGroupTimingTest` thấy **2** books và **0** after marker trong method, rồi **1** marker trong @AfterTransaction, cuối hook xóa marker.
- `SqlClassPhasesTest` thấy class marker **1** trong cả ba methods; `class-after.sql` dọn marker khi class kết thúc.

Đây là mô tả expected assertions trong source; không đưa ra stdout tùy ý. JUnit không bảo đảm thứ tự chạy các method trừ khi yêu cầu cơ chế order; ví dụ được thiết kế **không cần order**.

## 8. @BeforeEach, @AfterEach, @BeforeTransaction, @AfterTransaction đặt ở đâu?

Nhiều người dùng JUnit lifecycle annotations để chạy SQL trực tiếp, rồi nhầm chúng với `@Sql` phases. Với transactional Spring test, timeline phổ biến là:

~~~text
[Trước class]      @Sql BEFORE_TEST_CLASS (một lần)
[Trước method]     @BeforeTransaction
                    Spring mở test-managed transaction
                    @Sql BEFORE_TEST_METHOD
                    JUnit @BeforeEach
                    JUnit @Test
                    JUnit @AfterEach
                    @Sql AFTER_TEST_METHOD
                    Spring rollback hoặc commit transaction test
                    @AfterTransaction
[Lặp lại methods]
[Sau class]        @Sql AFTER_TEST_CLASS (một lần)
~~~

**Chú ý:** `@BeforeTransaction` chạy trước mỗi transaction test, còn `@AfterTransaction` sau nó; chúng không nên được dùng như `@BeforeEach`/`@AfterEach` khi test không transactional. Spring TestContext quyết định khi nào gọi hooks theo listener. `@BeforeAll` và `@AfterAll` thuộc JUnit class lifecycle, nhưng không phải chính là `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` của @Sql.

Đoạn minh họa đúng ngữ cảnh:

~~~java
@BeforeTransaction
void beforeTx() {
    assertFalse(TestTransaction.isActive());
}

@BeforeEach
void beforeEach() {
    assertTrue(TestTransaction.isActive());
}

@AfterEach
void afterEach() {
    // TX test thường vẫn mở ở đây.
    assertTrue(TestTransaction.isActive());
}

@AfterTransaction
void afterTx() {
    assertFalse(TestTransaction.isActive());
}
~~~

Đây là snippet phụ trợ trong class `@JdbcTest` và có imports tương ứng, **không phải source file độc lập**. Nếu test được đánh dấu `@Commit`, `@Rollback(false)`, sử dụng propagation đặc biệt, hoặc bị callback đổi thread, quy tắc và expected state sẽ khác. Đừng dựa vào `@AfterEach` để khẳng định AFTER_TEST_METHOD script đã chạy hoặc data đã rollback.

### 8.1. Nếu cần xác nhận AFTER script ở thời điểm nào

Có ba cách phù hợp, tùy mức độ cần:
1. Kiểm bảng marker bằng `@AfterTransaction` như ví dụ, với AFTER script chạy `ISOLATED` rồi cleanup trong finally.
2. Tạo một custom TestExecutionListener ghi trace sự kiện vào bộ nhớ, nhưng cần quản lý thứ tự listener và test instance rõ.
3. Dùng logs DEBUG của `org.springframework.test.context.jdbc` và `org.springframework.jdbc.datasource.init` để quan sát script/statement execution.

Đừng chỉ nhìn kết quả SELECT ở cuối @Test method rồi kết luận AFTER_TEST_METHOD chưa/chắc chắn đã chạy: callback AFTER xảy ra **sau code test**.

## 9. @Sql khác schema.sql, data.sql, @BeforeEach và migration tools

| Công cụ | Khi chạy | Trường hợp phù hợp | Rủi ro |
|---|---|---|---|
| Boot `schema.sql` | Lúc DataSource/context initialization | Tạo embedded schema nền | Trùng migrations hoặc schema production |
| Boot `data.sql` | Lúc initialization (theo config) | Seed reference data đơn giản | Fixture chia sẻ, không reset theo method |
| Spring Test `@Sql BEFORE_TEST_METHOD` | Trước từng method | Rows/fixtures cô lập, rollback thuận tiện | Có thể bị method-level OVERRIDE |
| Spring Test `@Sql AFTER_TEST_METHOD` | Sau từng method, trước rollback mặc định | Cleanup/custom state trong transaction; ISOLATED nếu cần commit riêng | Cleanup trong TX có thể bị rollback |
| Spring Test `@Sql BEFORE_TEST_CLASS` | Trước toàn class | Reference data/schema theo class | Dữ liệu commit tồn tại qua methods |
| Spring Test `@Sql AFTER_TEST_CLASS` | Sau toàn class | Teardown class-level committed fixture | Không giúp tránh parallel collisions một mình |
| JUnit `@BeforeEach` | Trước test code | Setup object/mocks và data rất nhỏ | Code setup lặp nhiều |
| Flyway/Liquibase | Schema migration theo runtime/context | Evolution schema có version | Không tự seed fixture cho từng test method |
| Testcontainers | Vòng đời container do test setup | Production DB/dialect-specific tests | Khởi động/chạy chậm hơn H2 |

**Không đặt cùng một `CREATE TABLE` trong `schema.sql`, migration Flyway và `@Sql(BEFORE_TEST_CLASS)` mà không phối hợp**, vì nó có thể chạy nhiều lần trên cùng DataSource gây “table already exists”. Nếu schema thực sự cần migration versioned, cho Flyway/Liquibase tạo schema và dùng `@Sql` cho data fixtures chuyên biệt từng test.

**Không tự seed mọi thứ trong @BeforeEach nếu @Sql phù hợp hơn:** Script dễ tái sử dụng và có thể kiểm soát phase/transaction mode. Ngược lại, một vài rows đơn giản hoặc dynamic test data tùy method có thể dễ đọc hơn khi dùng JdbcTemplate hoặc test data builders bằng Java. Chọn công cụ cho rõ intent.

## 10. Tình huống sai thường gặp và cách sửa

### 10.1. Dùng AFTER_TEST_METHOD DELETE nhưng dữ liệu vẫn còn

Giả sử:

~~~java
@Test
@Sql(
    scripts = "/sql/seed-committed.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/sql/cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void testExternalClient() {
    // Script seed đã commit riêng; cleanup mặc định INFERRED.
}
~~~

Nếu test có test-managed TX, AFTER cleanup với INFERRED có thể chạy **trong TX test và rollback**, còn dữ liệu seed đã commit riêng vẫn tồn tại. Phải chọn cleanup `ISOLATED` tương ứng hoặc dùng DB disposable có teardown đáng tin, không tưởng rằng AFTER tự đồng nghĩa commit.

### 10.2. Thêm method @Sql làm mất fixture class

~~~java
@Sql("/sql/base-books.sql")
class FixtureTest {

    @Test
    @Sql("/sql/one-book.sql")
    void specialCase() {
        // Mặc định class fixture không chạy.
    }
}
~~~

Nếu cần cả hai, thêm `@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)` ở method/class. Nếu cần thay thế hoàn toàn, giữ OVERRIDE nhưng viết assertion chính xác cho dữ liệu riêng.

### 10.3. Dùng class-level @Sql tưởng chỉ chạy một lần

~~~java
@Sql("/sql/base-books.sql")
class ManyMethodsTest {
    // BEFORE_TEST_METHOD mặc định: chạy trước từng test.
}
~~~

Nếu script chứa `INSERT` trên primary key mà dữ liệu không rollback/cleanup được, method thứ hai có thể fail vì duplicate key. Với transactional @JdbcTest, inserts được rollback nên ổn; với non-transactional tests có thể cần cleanup hoặc đổi thành BEFORE_TEST_CLASS (nếu dữ liệu là class-level immutable và có teardown).

### 10.4. `@Sql` không tìm được file

- Kiểm `src/test/resources/sql/...` có được đưa vào test classpath.
- Kiểm đường dẫn bắt đầu `/` hay tương đối theo package.
- Nếu dùng `@Sql` không script/statement, kiểm default script name của class/method.
- Không trông chờ `schema.sql` từ Boot SQL init được Spring Test tự suy ra như `@Sql("/sql/...")`.
- Kiểm encoding nếu script có Unicode/SQL string, và separator nếu dùng procedure/block nhiều lệnh.

### 10.5. AFTER_TEST_CLASS cleanup không chạy như kỳ vọng

Nếu test process bị kill hoặc JVM crash, teardown listener không phải cơ chế bảo đảm dữ liệu ngoài đời luôn dọn. Nếu app kết nối database chung, một class khác có thể đang chạy song song. Dùng database/schema riêng cho suite, Testcontainers, unique test keys, cleanup có thể chạy lại an toàn, và tránh dùng tài nguyên shared production.

### 10.6. Multiple DataSources hoặc transaction managers

`@Sql` cần chạy trên đúng DataSource. Nếu context có nhiều bean cùng loại, Spring có thể không quyết định được hoặc chọn bean khác mong muốn. Cấu hình `@SqlConfig(dataSource = "reportingDataSource", transactionManager = "reportingTransactionManager")` khi cần. Không tự sửa mọi test thành `@SpringBootTest` chỉ để che một lỗi chọn bean.

### 10.7. SQL dialect khác nhau

H2 phù hợp học lifecycle, nhưng PostgreSQL/MySQL/Oracle có cú pháp, transaction DDL, locking, identity, JSON/UUID khác nhau. Nếu script chứa cú pháp production riêng, chạy trên Testcontainers với chính driver/schema phù hợp. `@Sql` không tự chuyển SQL dialect.

## 11. Checklist thiết kế fixture SQL có thể tin cậy

1. **Chọn phase đúng:** dữ liệu theo từng test -> BEFORE_TEST_METHOD; dữ liệu theo cả class -> BEFORE_TEST_CLASS với cleanup; cần after hook -> AFTER_TEST_METHOD/CLASS.
2. **Chọn rollback/commit policy rõ:** test-managed transaction + INFERRED để rollback; ISOLATED chỉ khi thực sự cần dữ liệu committed cho worker bên ngoài.
3. **Chọn annotation class/method:** method-level mặc định OVERRIDE class-level; dùng MERGE nếu cần cả hai.
4. **Đặt đường dẫn tuyệt đối classpath rõ** như `/sql/base-books.sql`, tránh phụ thuộc thư mục làm việc.
5. **Giữ script đơn giản và thứ tự có chủ đích:** schema được tạo trước data; bảng reference trước bảng có foreign key.
6. **Test ít nhất 0/1/nhiều rows** và trường hợp dữ liệu không tồn tại hoặc vi phạm unique constraint khi nghiệp vụ cần.
7. **Giữ IDs/namespace riêng:** dữ liệu shared across class có thể gây collision nếu JUnit chạy parallel.
8. **Tránh DB sản xuất và DB chung:** chỉ dùng embedded H2 hoặc database test riêng; scripts cleanup có thể chứa DELETE/DROP nguy hiểm.
9. **Không dựa vào order của test methods:** fixture phải được thiết kế để mỗi test chạy độc lập.
10. **Kiểm sau rollback nếu đó là contract:** dùng @AfterTransaction, không chỉ @AfterEach.
11. **Theo dõi logs khi fail:** `org.springframework.test.context.jdbc=DEBUG`, `org.springframework.jdbc.datasource.init=DEBUG`.
12. **Nếu dùng ISOLATED, cleanup phải thật sự commit** và nên có finally/teardown ngoài transaction hoặc database disposable.
13. **Không lạm dụng errorMode bỏ qua lỗi:** SQL script fail phải làm test fail để tránh false positives.
14. **Kiểm thực tế với production database** nếu dùng SQL-specific syntax hoặc type conversion.
15. **Xác định mối quan hệ với schema migration** để không tạo schema hai lần.

## 12. Bài tập tự luyện

**Bài 1 — Mặc định:** Đặt class-level `@Sql("/sql/base-books.sql")` lên một test class có ba methods. Vì sao script chạy trước từng method? Nếu class non-transactional, điều gì có thể gây trùng key?

**Bài 2 — OVERRIDE/MERGE:** Tạo một method với `@Sql("/sql/one-book.sql")`, kiểm count=1. Thêm `@SqlMergeMode(MERGE)` và kiểm count=3. Tại sao đây không phải một thay đổi “cú pháp trang trí”?

**Bài 3 — Group hai phase:** Tạo `@SqlGroup` chứa BEFORE_METHOD seed và AFTER_METHOD cleanup. Với @JdbcTest mặc định, liệu AFTER cleanup có được commit riêng không? Hãy giải thích listener order.

**Bài 4 — Isolated:** Đổi AFTER cleanup sang `ISOLATED`; trong H2 disposable, ghi marker vào bảng riêng, dùng `@AfterTransaction` kiểm và xóa marker. Vì sao không nên update cùng row đang bị TX-A khóa?

**Bài 5 — Class phase:** Dùng `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` để tạo/dọn reference row. Thêm method-level @Sql và xác nhận class-phase scripts không bị OVERRIDE.

**Bài 6 — Default resource:** Bỏ scripts/statement khỏi @Sql trên class và method; tìm tên file Spring sẽ tìm theo package + class/method. Tạo file đúng, rồi cố tình đổi tên để quan sát setup error.

**Bài 7 — Inline statements:** Viết `@Sql(statements = "...")` cho một trường hợp đơn giản. Khi nào inline code dễ đọc hơn một SQL file dài?

**Bài 8 — Schema migration:** Thêm Flyway migration tạo bảng. Khi nào nên bỏ schema.sql để tránh chạy DDL hai lần? Khi test cần seed data riêng, @Sql phù hợp ở phase nào?

**Bài 9 — Two datasources:** Có reader/writer DataSource hoặc tenant databases. Cấu hình `@SqlConfig(dataSource,transactionManager)` ra sao để script không chạm nhầm DB?

**Bài 10 — Parallel tests:** Cho hai classes sử dụng cùng class-phase marker ID. Nếu chạy song song có thể phát sinh lỗi nào? Hãy thiết kế unique IDs/schema hoặc container riêng.

**Bài 11 — Database cụ thể:** Chạy cùng SQL scripts trên PostgreSQL Testcontainers. So sánh DDL, transaction isolation và script separator với H2.

**Bài 12 — Kiểm lifecycle:** Bật logging DEBUG cho Spring Test JDBC và đọc sequence BEFORE_METHOD → test → AFTER_METHOD → transaction rollback. Dùng @AfterTransaction để kiểm trạng thái cuối.

## 13. Tham khảo chính thức

- [Spring Framework 6.1 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/executing-sql.html): @Sql, @SqlGroup, script paths, default detection, execution phases, merge và transaction.
- [Spring Framework 6.1 — SqlScriptsTestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/jdbc/SqlScriptsTestExecutionListener.html): listener methods, class phases, order 5000.
- [Spring Framework 6.1 — SqlConfig.TransactionMode API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.TransactionMode.html): INFERRED, ISOLATED và điều kiện commit/rollback.
- [Spring Framework — @SqlMergeMode](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-sqlmergemode.html): OVERRIDE/MERGE theo class/method.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction, @AfterTransaction, listener ordering và rollback.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @JdbcTest, transactional rollback và embedded database.
- [Spring Boot 3.3 — Test Slice Auto-configurations](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): @JdbcTest và SQL initialization.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql, data.sql và tương tác với migrations.
- [Spring Framework — @AfterTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): chạy sau transactional test.

**Ghi nhớ:** `@Sql` có **phase**, **scope class/method**, **quy tắc merge** và **transaction mode** — phải xem đủ cả bốn, không chỉ tên file `.sql`. Mặc định nó chạy trước test method; method-level script có thể OVERRIDE class fixture; `@SqlMergeMode(MERGE)` nối chúng. `@SqlGroup` chỉ nhóm nhiều `@Sql`, không tự tạo transaction. `AFTER_TEST_METHOD` trong test transactional thường chạy **trước rollback**, còn `ISOLATED` commit riêng và cần cleanup rõ. Với Spring 6.1+, class phases chạy một lần trước/sau class và không bị method-level OVERRIDE.
