# Spring Boot Testing: @SqlConfig, transaction mode và script dọn dữ liệu

## 1. Bài toán: có dữ liệu để test và không để lại dữ liệu sau test

Một bộ kiểm thử tích hợp cần dữ liệu có thể lặp lại. Thông thường ta muốn:

1. Tạo schema và **seed** các bản ghi cố định trước test.
2. Chạy code production với repository, `JdbcTemplate` hoặc HTTP thật.
3. Assert dữ liệu, lỗi và side effects.
4. **Dọn sạch** dữ liệu vừa tạo, kể cả khi test thất bại.
5. Không làm hỏng database hoặc dữ liệu của test khác.

Spring TestContext hỗ trợ `@Sql` và `@SqlConfig` để thực hiện các bước này. Tuy nhiên, việc chỉ thêm `@Sql(scripts = "...cleanup.sql", executionPhase = AFTER_TEST_METHOD)` **không bảo đảm script dọn dữ liệu sẽ được commit**. Nếu test có `@Transactional`, script cleanup mặc định có thể chạy **trong chính transaction của test** rồi bị rollback cùng mọi thao tác khác.

Điểm quan trọng nhất của bài:

**Chọn `transactionMode` theo transaction ownership, không chỉ theo tên script.**

- Seed chỉ phục vụ một test JDBC/JPA có rollback mặc định → thường dùng `INFERRED`, cho seed tham gia test-managed transaction.
- Seed cần được code chạy ở một **transaction/connection khác** nhìn thấy (ví dụ HTTP server thật, `REQUIRES_NEW`, process khác) → dùng `ISOLATED` hoặc một setup đã commit.
- Cleanup cần xóa các bản ghi **đã commit độc lập** → thường phải dùng `AFTER_TEST_METHOD` **và `ISOLATED`**.
- Code chỉ cần rollback test transaction mà không tạo committed side effects → không cần cleanup script để xóa chính những rows được rollback.

Bài gồm giải thích cơ chế, bảng quyết định, các lỗi khó gặp và bộ ví dụ Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2 / JUnit Jupiter / H2 để chứng minh các trường hợp bằng test thực.

### Kết quả học tập

- Biết `@Sql` khác `@SqlConfig` ở đâu, `SqlScriptsTestExecutionListener` chạy khi nào.
- Chọn đúng `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS`.
- Hiểu chính xác `TransactionMode.DEFAULT`, `INFERRED` và `ISOLATED`.
- Viết SQL fixtures có đường dẫn rõ, charset UTF-8, separator và comment rules hợp lệ.
- Biết `@SqlMergeMode(MERGE)` để class-level cleanup không bị method-level seed vô hiệu hóa.
- Phân biệt cleanup script và rollback test, tránh script dọn dữ liệu bị rollback.
- Biết chọn `ErrorMode` an toàn, không giấu lỗi SQL làm test PASS giả.
- Test HTTP server thật với dữ liệu đã commit và kiểm sau `@AfterTransaction`.
- Dùng schema/test database cô lập, tránh chạm production và tránh flaky parallel tests.

## 2. @Sql là gì và ai thực thi nó?

`@Sql` là annotation của **Spring TestContext Framework** tại package:

~~~java
import org.springframework.test.context.jdbc.Sql;
~~~

Ví dụ:

~~~java
@Test
@Sql("/sql/seed-users.sql")
void loadsUsers() {
    // Test code nhìn thấy dữ liệu từ SQL script.
}
~~~

Đây là **mẫu minh họa**, chưa phải file test độc lập.

`@Sql` khai báo:

- `scripts` hoặc `value`: một hay nhiều SQL files/resource paths.
- `statements`: các SQL statements khai báo trực tiếp trong annotation.
- `executionPhase`: script chạy trước/sau method hoặc trước/sau class.
- `config`: một `@SqlConfig` cục bộ cho parsing, datasource và transaction.
- Multiple/repeatable `@Sql`: một test có thể có nhiều nhóm scripts với phases và configs khác nhau.

`SqlScriptsTestExecutionListener` thực thi các scripts. Listener này là một TestExecutionListener mặc định của Spring TestContext, không cần tự gọi `Files.readString()`, `Connection.createStatement()` hay mở Hibernate Session chỉ để chạy fixture.

**Không nhầm với Boot SQL initialization:** Spring Boot có thể đọc `schema.sql`/`data.sql` khi **ApplicationContext/DataSource khởi tạo**, còn `@Sql` chạy theo **vòng đời từng test class/method**. Chúng có thể cùng tồn tại, nhưng phải phân định việc tạo schema và seed dữ liệu rõ ràng.

### 2.1 Ví dụ tạo dữ liệu trước và dọn sau

~~~java
@Test
@Sql(
    scripts = "/sql/seed-example.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-example.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
void shouldWorkWithCommittedFixture() {
    // Code được kiểm có thể chạy ở connection/thread khác.
}
~~~

Đây là **mẫu chú giải**, chưa gồm scripts/DB/test class. Cả seed và cleanup đều dùng `ISOLATED` để **commit độc lập**; không trông cậy test-managed rollback.

Nếu mọi thao tác seed và test chỉ chạy trong một transaction do test mở và không có independent commits, seed `ISOLATED` không cần thiết, thậm chí gây thêm dữ liệu đã commit phải cleanup.

## 3. Thứ tự vòng đời: BEFORE, AFTER và transaction của test

Trong JUnit Jupiter + Spring TestContext, một test có `@Transactional` thường đi qua:

~~~text
ApplicationContext khởi tạo; Boot schema.sql nếu được cấu hình
           |
           v
@Sql BEFORE_TEST_CLASS       (nếu khai báo; một lần/class)
           |
           v
@BeforeTransaction            (nếu có test-managed transaction)
           |
           v
TransactionalTestExecutionListener BEGIN test transaction
           |
           v
@Sql BEFORE_TEST_METHOD       (theo transactionMode)
           |
           v
JUnit @BeforeEach             (đang trong test transaction)
           |
           v
JUnit @Test                   (đang trong test transaction)
           |
           v
JUnit @AfterEach              (đang trong test transaction)
           |
           v
@Sql AFTER_TEST_METHOD        (theo transactionMode)
           |
           v
TransactionalTestExecutionListener ROLLBACK hoặc COMMIT
           |
           v
@AfterTransaction             (đã ra khỏi test transaction)
           |
           v
@Sql AFTER_TEST_CLASS        (nếu khai báo; một lần/class)
~~~

**Chú ý thứ tự quan trọng:** `SqlScriptsTestExecutionListener` có order **5000**, chạy sau `TransactionalTestExecutionListener` order **4000** ở chiều “before”; ở chiều “after”, thứ tự đảo ngược. Vì thế `@Sql AFTER_TEST_METHOD` chạy khi test-managed transaction **vẫn có thể đang hoạt động**, trước khi listener transaction rollback. Đây chính là bẫy của cleanup `INFERRED`.

Thời điểm `@BeforeEach`/`@AfterEach` của JUnit là trong test-managed transaction, không phải một cách tự động dọn rows đã commit ở transaction khác.

### 3.1 Script class-level

Spring Framework 6.1+ hỗ trợ:

~~~java
@Sql(
    scripts = "/sql/create-shared-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
@Sql(
    scripts = "/sql/drop-shared-schema.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
class SharedSchemaTests {
    // ...
}
~~~

Đây là **mẫu minh họa**, không thuộc project runnable phía dưới. Class-level phases chạy một lần/class, không phải trong test-managed transaction của từng test method. Các declaration `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` **không bị method-level @Sql override**. Với schema dùng chung, tuyệt đối tránh DROP table/schema mà test class khác đang sử dụng.

### 3.2 Khi test không có @Transactional

Nếu test không có test-managed transaction, `INFERRED` có thể tạo một Spring-managed transaction ngắn để chạy script rồi commit khi có transaction manager; nếu chỉ có datasource và không có manager, script được chạy trực tiếp trên datasource. Vì vậy không được quy giản `INFERRED` thành “luôn rollback” hoặc “luôn commit”: nó **phụ thuộc** context đang có transaction hay không.

## 4. @SqlConfig cấu hình những gì?

Annotation:

~~~java
import org.springframework.test.context.jdbc.SqlConfig;
~~~

Có thể đặt **toàn cục ở test class**:

~~~java
@SqlConfig(encoding = "UTF-8", errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
@JdbcTest
class RepositorySqlTests {
    // ...
}
~~~

Hoặc **cục bộ ngay trong @Sql**:

~~~java
@Sql(
    scripts = "/sql/custom-format.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = "@@"))
~~~

Bảng các thuộc tính quan trọng:

| Thuộc tính | Tác dụng |
| --- | --- |
| `dataSource` | Tên DataSource bean nếu có nhiều datasource hoặc discovery không rõ |
| `transactionManager` | Tên PlatformTransactionManager dùng chạy scripts |
| `transactionMode` | `DEFAULT`, `INFERRED`, `ISOLATED` |
| `encoding` | Encoding của SQL resource, ví dụ `UTF-8` |
| `separator` | Dấu tách SQL statements, mặc định ngầm định `;` |
| `commentPrefix` | Tiền tố comment một dòng; mặc định `--` |
| `commentPrefixes` | Nhiều tiền tố comment một dòng, thay cho `commentPrefix` |
| `blockCommentStartDelimiter` | Dấu mở block comment; mặc định `/*` |
| `blockCommentEndDelimiter` | Dấu đóng block comment; mặc định `*/` |
| `errorMode` | Fail/continue/ignore failed drops theo policy |

### 4.1 Global và local @SqlConfig được merge như thế nào?

Mỗi thuộc tính `@SqlConfig` có **explicit default**:

- String: `""`.
- String array: `{}`.
- Enum: `DEFAULT`.

Khi có config global ở class và local trong `@Sql`, các thuộc tính local có giá trị tường minh **khác default** ghi đè global; các thuộc tính local còn default sẽ **kế thừa global**.

Ví dụ:

~~~java
@SqlConfig(
    encoding = "UTF-8",
    errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class Example {
    @Test
    @Sql(
        scripts = "/sql/custom.sql",
        config = @SqlConfig(separator = "@@"))
    void customSql() {
        // separator = "@@" (local)
        // encoding = "UTF-8" (global)
        // errorMode = FAIL_ON_ERROR (global)
    }
}
~~~

Đoạn này là mẫu, chưa có Spring test annotation và file thực. Nếu muốn một local attribute trở về default khác global, không thể coi `DEFAULT` là “ép xóa global”; cần thiết kế cấp khai báo phù hợp.

### 4.2 Không trộn commentPrefix và commentPrefixes

`commentPrefix` và `commentPrefixes` là **hai cách thay thế**, không dùng cùng lúc. Nếu script có `--` và `#`, dùng:

~~~java
@SqlConfig(commentPrefixes = {"--", "#"})
~~~

Đoạn này là cấu hình minh họa. Với SQL thực, phải xác định comment syntax do parser hỗ trợ và dialect của DB; tránh cắt SQL sai chỉ vì một ký tự xuất hiện trong string literal.

### 4.3 Nếu có nhiều DataSource hoặc TransactionManager

Một ứng dụng có primary datasource và reporting datasource. Nếu `@Sql` tự chọn nhầm primary, seed có thể chạy trên DB A trong khi repository under test đọc DB B.

~~~java
@Sql(
    scripts = "/sql/report-fixture.sql",
    config = @SqlConfig(
        dataSource = "reportingDataSource",
        transactionManager = "reportingTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

Mẫu trên chỉ đúng khi **cả hai beans thực sự có những tên đó** và transaction manager quản lý đúng datasource. Đừng tự đặt tên bừa; đối chiếu cấu hình ứng dụng rồi test bằng readback trên cùng datasource. `ISOLATED` cần một transaction manager phù hợp để commit transaction mới.

## 5. transactionMode = DEFAULT, INFERRED và ISOLATED

Đây là phần cốt lõi của bài.

`@SqlConfig.TransactionMode` có ba enum values:

### DEFAULT

`DEFAULT` là giá trị annotation mặc định, kế thừa cấu hình global khi có. Nếu không có override, hành vi hiệu lực là **INFERRED**. Nó **không** có nghĩa “bỏ qua transaction” hoặc “chắc chắn commit”.

### INFERRED

Spring suy ra cách chạy từ context:

1. Không có datasource và cũng không có transaction manager → lỗi.
2. Có datasource, không có manager → chạy trực tiếp trên datasource, không dùng Spring-managed transaction.
3. Có manager, có datasource thích hợp và **đã có transaction** → chạy script **bên trong transaction đó**.
4. Có manager nhưng **chưa có transaction** → chạy trong transaction mới và **commit sau script**.

Do đó, với `@JdbcTest`/`@DataJpaTest` mặc định transactional, `@Sql INFERRED BEFORE_TEST_METHOD` thường tham gia transaction test, và seed được rollback sau test. Còn cùng script chạy trong một test không có @Transactional có thể được commit.

### ISOLATED

`ISOLATED` yêu cầu script chạy trong **một transaction mới, độc lập**, commit ngay sau thực thi thành công. Nếu đang có test transaction, nó được suspend trong khi script chạy isolated. Nếu chưa có transaction, script vẫn mở transaction riêng.

Điểm cần lưu ý:

- `ISOLATED` **không** đảm bảo một DB hoàn toàn mới; nó dùng cùng datasource/schema nhưng một transaction khác.
- `ISOLATED` cần transaction manager được xác định; không chỉ DataSource trần.
- Nó không rollback khi test sau đó fail; vì đã commit trước/sau ở thời điểm script chạy.
- Nếu script thao tác row bị test transaction khác giữ lock, isolated script có thể block/timeout. Chọn fixture IDs riêng và tránh update xung đột.

### 5.1 Ma trận quyết định

| Test context | Phase | Mode | SQL thường nằm ở đâu? | Điều xảy ra khi test rollback |
| --- | --- | --- | --- | --- |
| `@JdbcTest` mặc định TX | BEFORE | INFERRED | Test transaction | Seed rollback |
| `@JdbcTest` mặc định TX | AFTER | INFERRED | Test transaction vẫn mở | Cleanup cũng rollback; không xóa committed row ngoài TX |
| Test có TX | BEFORE | ISOLATED | Transaction mới, commit | Seed vẫn còn nếu chưa có cleanup riêng |
| Test có TX | AFTER | ISOLATED | Transaction mới, commit | Cleanup committed độc lập, không bị test rollback |
| Test không có TX, có manager | BEFORE | INFERRED | Transaction mới, commit | Không có test rollback để dọn |
| Test không có TX, có manager | AFTER | INFERRED | Transaction mới, commit | Cleanup thường commit, nhưng logic phụ thuộc context |
| Test không có TX, có manager | BEFORE/AFTER | ISOLATED | Transaction mới, commit | Có commit rõ ràng |
| Chỉ có DataSource, không manager | BEFORE/AFTER | INFERRED | Chạy trực tiếp trên datasource | Theo auto-commit/DB behavior |
| Chỉ có DataSource, không manager | BEFORE/AFTER | ISOLATED | Không thể tạo isolated Spring transaction hợp lệ | Cần manager; báo lỗi |

**Đừng thiết kế cleanup dựa vào giả định “@Sql chạy sau test nên chắc chắn đã commit”.** Phase điều khiển **thời điểm**; transactionMode điều khiển **transaction**. Hai trục độc lập.

## 6. Ba kịch bản thường dùng

### 6.1 Repository test, mọi thao tác cùng test-managed transaction

~~~java
@JdbcTest
class RepositoryTest {
    @Test
    @Sql("/sql/seed-rows.sql")
    void query() {
        // INFERRED + transactional @JdbcTest
        // seed và các writes của test rollback cùng nhau.
    }
}
~~~

Không nhất thiết cần `@Sql cleanup` nếu tất cả thao tác tham gia transaction test và không có side effects khác. Cleanup thừa có thể gây lỗi nếu cố xóa committed fixture cùng tên hoặc làm test phức tạp không cần thiết.

### 6.2 Test có external/server/inner transaction cần đọc committed fixture

~~~java
@Test
@Sql(
    scripts = "/sql/seed-committed.sql",
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-committed.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void externalCallerNeedsFixture() {
    // HTTP server hoặc REQUIRES_NEW nhìn thấy seed đã commit.
}
~~~

Nếu seed vẫn `INFERRED` trong test TX, server thread/`REQUIRES_NEW` dưới READ_COMMITTED có thể **không nhìn thấy dữ liệu** hoặc đợi lock. Không tăng isolation tùy tiện chỉ để lách vấn đề dữ liệu chưa commit.

### 6.3 Test không có test-managed transaction

~~~java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJdbcTests {
    // Chạy SQL bằng JDBC mà không có outer test-managed TX.
    // Phải cleanup committed writes.
}
~~~

Khi tắt test transaction, test database không còn tự rollback mọi writes. Dùng `@Sql AFTER_TEST_METHOD` với ISOLATED, cleanup trong `@AfterEach` ngoài transaction, truncate/reset schema hoặc tạo database riêng, tùy phạm vi.

## 7. Cần dùng errorMode nào?

`SqlConfig.ErrorMode` có các chế độ:

| Mode | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `DEFAULT` | Sử dụng default/inherited config, ngầm định FAIL_ON_ERROR | Thích hợp hầu hết tests |
| `FAIL_ON_ERROR` | SQL error làm script fail | **Nên dùng** cho seed/cleanup quan trọng |
| `CONTINUE_ON_ERROR` | Log lỗi nhưng tiếp tục chạy các statements | Nguy hiểm: có thể tạo dữ liệu thiếu/partial |
| `IGNORE_FAILED_DROPS` | Bỏ qua lỗi của lệnh DROP thất bại; lỗi khác vẫn fail | Chỉ cân nhắc cho cleanup/schema reset thật sự có thể không tồn tại |

Tránh `CONTINUE_ON_ERROR` để “test xanh” khi cleanup không có quyền delete hoặc seed bị unique violation. Test cần biết fixture không đúng để không tạo false positives.

Nếu cleanup dùng SQL an toàn:

~~~sql
DELETE FROM demo_item WHERE item_id LIKE 'CASE-%';
~~~

thì việc không có row tương ứng **không phải lỗi**; DELETE 0 row thường thành công. Không cần `IGNORE_FAILED_DROPS` hoặc `CONTINUE_ON_ERROR`.

Với DDL tùy engine, ưu tiên `DROP TABLE IF EXISTS` khi được hỗ trợ. ErrorMode không thay quyền DB hoặc schema isolation.

### 7.1 FAIL_ON_ERROR với AFTER script

Nếu test đã fail rồi cleanup SQL cũng fail, test report có thể chứa cả assertion failure và cleanup failure. Đó là tín hiệu quan trọng. Không che cleanup failure bằng `CONTINUE_ON_ERROR` vì những rows đã commit có thể làm test sau sai.

Khi cleanup critical, log rõ tên script, datasource, id/prefix và transaction mode; tuyệt đối không log secrets/production credentials.

## 8. Script resource paths, encoding, separator và comment syntax

### 8.1 Đường dẫn

Giả sử test class `example.sqldemo.SampleSqlTest`:

| @Sql path | Cách Spring hiểu |
| --- | --- |
| `"setup.sql"` | Tương đối package class: `example/sqldemo/setup.sql` |
| `"/sql/setup.sql"` | Absolute classpath: `src/test/resources/sql/setup.sql` |
| `"classpath:/sql/setup.sql"` | Spring classpath resource cùng vị trí |
| `"file:/..."` | File system resource; không nên phụ thuộc path máy cá nhân |

Ưu tiên `"/sql/seed-xyz.sql"` để test không hỏng khi đổi package Java. Khi không truyền scripts/statements, Spring thử tìm script mặc định theo tên class hoặc method; nếu không tìm thấy thì fail. Với bài Knowledge và CI, nên ghi resource path rõ.

Spring Framework 6.2 hỗ trợ property placeholders trong script paths dựa trên Environment. Đừng đưa dữ liệu không đáng tin thành đường dẫn SQL hoặc tên file tùy ý.

### 8.2 Encoding UTF-8

SQL scripts có tiếng Việt:

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('VI-282', 'Cà phê sữa', TRUE);
~~~

Đảm bảo lưu file UTF-8, và cấu hình:

~~~java
@SqlConfig(encoding = "UTF-8")
~~~

Thuộc tính đúng là `encoding` (không phải `charset`). Nếu platform encoding khác và bỏ qua cấu hình, test có thể đọc sai ký tự hoặc so sánh title thất bại.

### 8.3 Custom separator

Một script có thể dùng delimiter `@@`:

~~~sql
-- Script dùng separator @@ thay vì ;
INSERT INTO demo_item(item_id, title, active)
VALUES ('X-282', 'Dữ liệu đặc biệt', TRUE)@@
~~~

Annotation:

~~~java
@Sql(
    scripts = "/sql/seed-custom.sql",
    config = @SqlConfig(separator = "@@", encoding = "UTF-8"))
~~~

Parser của Spring TestContext tách statements theo separator. Đây là **separator của script reader**, không đổi SQL dialect trong DB. Nếu script chứa stored procedure có nhiều semicolons bên trong body, phải dùng migration tool/parser phù hợp (Flyway/Liquibase) hoặc một separator có thiết kế phù hợp; không giả định mọi script delimiter tùy ý đều phân tích đúng PostgreSQL dollar-quoted PL/pgSQL.

### 8.4 Comment rules

Mặc định `--` cho single-line comments, `/* ... */` cho block comments. Khi cần nhiều prefixes khác nhau, `commentPrefixes={"--","#"}` thay cho `commentPrefix`.

Không tự tách SQL bằng `String.split(";")`, vì semicolons có thể nằm trong quoted strings hoặc stored routine bodies.

## 9. @SqlMergeMode: tránh vô hiệu hóa cleanup

Mặc định, method-level `@Sql` **override** các class-level `@Sql` cho execution phases thông thường. Điều này có thể gây lỗi kín:

~~~java
@Sql(
    scripts = "/sql/cleanup-every-test.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
class Example {

    @Test
    @Sql(
        scripts = "/sql/seed-one-case.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
    void caseOne() {
        // Chú ý: @Sql method có thể override cleanup class!
    }
}
~~~

Nếu không cấu hình merge, cleanup ở class có thể không được chọn cho method có `@Sql` riêng. Để hai sets cùng chạy, dùng:

~~~java
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
~~~

Ở cấp class hoặc method. `MERGE` kết hợp class-level và method-level declarations; có thể dùng `@SqlMergeMode(OVERRIDE)` cho một method thật sự muốn thay thế (phải có cleanup thay thế).

**Ngoại lệ:** class-level `@Sql` với `BEFORE_TEST_CLASS` hoặc `AFTER_TEST_CLASS` chạy một lần và không bị method-level SQL override như phase per-method.

### 9.1 @SqlConfig global khác @SqlMergeMode

Hai cơ chế **khác nhau**:

- `@SqlConfig` global/local: merge **các thuộc tính parsing/transaction**.
- `@SqlMergeMode`: merge hoặc override **những tập @Sql declarations** giữa class và method.

Bạn có thể có global encoding UTF-8 được kế thừa **mà** class-level cleanup vẫn bị method-level seed override nếu thiếu `@SqlMergeMode(MERGE)`. Test cần kiểm cả hai.

## 10. Chiến lược dọn dữ liệu: chọn theo nơi dữ liệu được commit

| Nguồn dữ liệu | Ai giữ transaction? | Cleanup phù hợp |
| --- | --- | --- |
| Seed `@Sql INFERRED` + repository test rollback mặc định | TestContext | Rollback đủ, không nhất thiết cần SQL DELETE |
| Seed `@Sql ISOLATED` để REQUIRES_NEW đọc | SQL listener mở TX riêng | `@Sql AFTER_TEST_METHOD ISOLATED` |
| HTTP server `RANDOM_PORT` tự commit | Server service | Cleanup committed riêng; `AFTER_TEST_METHOD ISOLATED` hoặc reset DB |
| `@Transactional(REQUIRES_NEW)` ghi audit | Spring service TX độc lập | Cleanup riêng đã commit |
| Test `@Commit` hoặc `@Rollback(false)` | TestContext commit | Cleanup sau commit bằng TX riêng |
| Test không có `@Transactional` | Application/JDBC autocommit | Cleanup committed độc lập |
| Dữ liệu seed bằng `schema.sql`/`data.sql` ở context startup | Boot initializer | DB riêng/fixture reset; không xóa shared schema tùy tiện |
| Test class tạo schema riêng | Phụ thuộc DB DDL transaction | DROP/reset sau class khi cô lập, hoặc container mới |
| Dữ liệu ở object storage/Redis/Kafka | Không cùng JDBC TX | Cleanup qua service riêng hoặc test container/namespace |
| Parallel tests dùng chung DB | Nhiều connections đồng thời | Fixture keys/tenant/schema độc lập, tránh TRUNCATE chung |

### 10.1 DELETE theo ID ổn định thay vì TRUNCATE bừa bãi

Ví dụ:

~~~sql
DELETE FROM order_line WHERE order_id LIKE 'TEST282-%';
DELETE FROM customer_order WHERE order_id LIKE 'TEST282-%';
~~~

Đây là SQL minh họa giả định có foreign key order_line → customer_order. Thứ tự xóa child rồi parent tránh FK violation. Đừng dùng `TRUNCATE customer_order` trên shared test database nếu một suite khác đang chạy, và tuyệt đối không chạy cleanup này trên production.

### 10.2 Idempotency của cleanup

Script cleanup lý tưởng chạy nhiều lần vẫn thành công và chỉ xóa dữ liệu của test:

~~~sql
DELETE FROM demo_item WHERE item_id IN ('S-282', 'HTTP-282');
~~~

Nếu không có row, DELETE 0 row vẫn thành công. Khi test fail giữa chừng, cleanup vẫn nên xử lý cả trường hợp chỉ có seed mà chưa có HTTP write. Hạn chế hard-coded table-wide DELETE.

### 10.3 Cleanup chạy khi test failed?

`@Sql AFTER_TEST_METHOD` thuộc lifecycle callback và thông thường chạy cả khi `@Test` assertion thất bại, trừ lỗi nghiêm trọng trước khi listener/test lifecycle khởi động hoặc process bị kill. Nó **không phải cơ chế bảo đảm 100%** trước JVM crash hoặc mất kết nối DB. Testcontainers/ephemeral DB giúp tránh rò lâu dài khi process hỏng.

## 11. Ví dụ runnable Java 17+ / Spring Boot 3.5.x

Phần này là mini-project minh họa **đủ các Java classes và SQL scripts**. Bài dùng:

- Spring Boot 3.5.x và Spring Framework 6.2.
- `spring-boot-starter-jdbc` + `spring-boot-starter-web`.
- H2 in-memory chỉ cho tests; không có DB production.
- JUnit Jupiter + Spring Boot starter-test.
- `@JdbcTest` cho query/fixture/transaction tests.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` cho request HTTP chạy trên server thread.
- **Tám phương thức @Test** thuộc năm classes.

Dữ liệu từng class dùng ID/prefix riêng để không phụ thuộc thứ tự test. Test-level `@Transactional` ở `@JdbcTest` mặc định; class HTTP có `@Transactional` để minh họa sự khác biệt thread, và sử dụng cleanup `ISOLATED`.

### 11.1 Cây thư mục

~~~text
src/
  main/java/example/sqldemo/
    SqlDemoApplication.java
    ItemGateway.java
    ItemService.java
    ItemController.java
  test/java/example/sqldemo/
    InferredSqlTest.java
    IsolatedSqlTest.java
    MergedSqlTest.java
    NoTestTransactionSqlTest.java
    HttpSqlCleanupTest.java
  test/resources/
    application.properties
    schema.sql
    sql/
      seed-rollback.sql
      seed-custom.sql
      seed-isolated.sql
      cleanup-isolated.sql
      seed-merge.sql
      cleanup-merge.sql
      seed-nontx.sql
      cleanup-nontx.sql
      seed-http.sql
      cleanup-http.sql
~~~

Không có Flyway/Liquibase trong demo để tập trung vào `@SqlConfig`. Khi production có migrations, hãy dùng migrations thật để tạo schema trên DB test riêng; không duy trì DDL test khác production một cách vô ý.

### 11.2 Đoạn Gradle dependency

Trong project đã khai báo Spring Boot plugin/version, dependency management và Java toolchain 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn build.gradle**, không phải file standalone có plugins và toolchain. H2 chỉ là test runtime; ứng dụng standalone ngoài test cần datasource/driver được cấu hình riêng.

### 11.3 src/test/resources/application.properties

~~~properties
spring.datasource.generate-unique-name=true
spring.datasource.hikari.maximum-pool-size=8
spring.sql.init.mode=always

logging.level.org.springframework.test.context.jdbc=DEBUG
logging.level.org.springframework.jdbc.datasource.init=DEBUG
~~~

Giải thích:

- `generate-unique-name=true` giúp embedded database của những ApplicationContexts khác nhau không trùng tên.
- Pool 8 đủ cho test transactional và HTTP server/ISOLATED script khi cần nhiều connections (cấu hình Hikari chỉ có hiệu lực nếu datasource dùng Hikari).
- `spring.sql.init.mode=always` nạp `schema.sql` từ test resources khi context khởi tạo.
- Logging DEBUG giúp chẩn đoán scripts/SQL execution, không bắt buộc cho assertions; trong CI lớn có thể tắt để giảm noise.

Đừng đặt production credentials ở đây. Đừng bật logging bind parameters có secrets trên CI công khai.

### 11.4 src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS demo_item (
    item_id VARCHAR(40) PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL
);
~~~

Schema được Boot SQL initializer tạo khi test context khởi động. `@Sql` sẽ chỉ seed/cleanup data trong bảng có sẵn. Không dùng `data.sql` để seed toàn bộ records dùng chung, vì nó có lifecycle khác `@Sql` và dễ tạo fixture chưa cleanup.

### 11.5 src/main/java/example/sqldemo/SqlDemoApplication.java

~~~java
package example.sqldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlDemoApplication.class, args);
    }
}
~~~

### 11.6 ItemGateway.java — SQL adapter thật

~~~java
package example.sqldemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ItemGateway {

    private final JdbcTemplate jdbc;

    public ItemGateway(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void create(String id, String title) {
        jdbc.update("""
                INSERT INTO demo_item(item_id, title, active)
                VALUES (?, ?, TRUE)
                """, id, title);
    }

    public int count(String id) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_item
                WHERE item_id = ?
                """, Integer.class, id);
        return result.intValue();
    }

    public int countPrefix(String prefix) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_item
                WHERE item_id LIKE ?
                """, Integer.class, prefix + "%");
        return result.intValue();
    }

    public String title(String id) {
        return jdbc.queryForObject("""
                SELECT title FROM demo_item WHERE item_id = ?
                """, String.class, id);
    }

    public boolean exists(String id) {
        return count(id) == 1;
    }
}
~~~

`@JdbcTest` không tự scan mọi application `@Repository` như full `@SpringBootTest`, nên các slice tests dùng `@Import(ItemGateway.class)`. Lệnh `count` dùng SQL parameter binding và đọc trạng thái DB thật, không mock repository.

### 11.7 ItemService.java — tạo dữ liệu theo transaction của ứng dụng

~~~java
package example.sqldemo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ItemService {

    private final ItemGateway gateway;

    public ItemService(ItemGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void create(String id, String title) {
        gateway.create(id, title);
    }
}
~~~

`ItemService.create` khi được gọi từ controller trên HTTP server thread sẽ tự mở/commit transaction vì không có transaction JUnit test thread truyền sang. Đó là điểm then chốt để minh họa cleanup committed.

### 11.8 ItemController.java — endpoint phục vụ live HTTP test

~~~java
package example.sqldemo;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    private final ItemService service;
    private final ItemGateway gateway;

    public ItemController(
            ItemService service,
            ItemGateway gateway) {
        this.service = service;
        this.gateway = gateway;
    }

    @GetMapping("/api/items/{id}/exists")
    public ResponseEntity<Void> exists(
            @PathVariable("id") String id) {
        return gateway.exists(id)
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    @PostMapping("/api/items/{id}")
    public ResponseEntity<Void> create(
            @PathVariable("id") String id) {
        service.create(id, "created by HTTP");
        return ResponseEntity
                .created(URI.create("/api/items/" + id))
                .build();
    }
}
~~~

Không cấu hình Spring Security trong mini-project. Production phải validate ID, auth, rate limits, ownership và error mapping khi primary key trùng.

## 12. Các SQL scripts đầy đủ

Mọi file nằm trong `src/test/resources/sql/`, được lưu UTF-8.

### 12.1 seed-rollback.sql

~~~sql
-- Dữ liệu sẽ được rollback cùng transaction test.
INSERT INTO demo_item(item_id, title, active)
VALUES ('R-282-A', 'Học Spring', TRUE);

INSERT INTO demo_item(item_id, title, active)
VALUES ('R-282-B', 'Tài liệu Tiếng Việt', TRUE);
~~~

### 12.2 seed-custom.sql

Script **dùng separator @@**, không dùng dấu `;`:

~~~sql
-- SQL parser của @SqlConfig(separator = "@@")
INSERT INTO demo_item(item_id, title, active)
VALUES ('X-282', 'Cà phê dữ liệu', TRUE)@@
~~~

### 12.3 seed-isolated.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('C-282', 'Committed fixture', TRUE);
~~~

### 12.4 cleanup-isolated.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'C-282';
~~~

### 12.5 seed-merge.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('M-282', 'Merged SQL fixture', TRUE);
~~~

### 12.6 cleanup-merge.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'M-282';
~~~

### 12.7 seed-nontx.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('N-282', 'No test transaction', TRUE);
~~~

### 12.8 cleanup-nontx.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'N-282';
~~~

### 12.9 seed-http.sql

~~~sql
-- Seed đã commit để HTTP server thread nhìn thấy.
INSERT INTO demo_item(item_id, title, active)
VALUES ('S-282', 'Seed visible to server', TRUE);
~~~

### 12.10 cleanup-http.sql

~~~sql
-- Dọn cả seed và row do HTTP server service đã commit.
DELETE FROM demo_item
WHERE item_id IN ('S-282', 'HTTP-282');
~~~

Điểm thiết kế: mỗi cleanup chỉ đụng IDs của đúng test, không xóa toàn bảng. Nếu test fail trước khi insert `HTTP-282`, cleanup vẫn chạy thành công và xóa `S-282`. Các IDs chỉ dùng để học; suite production nên có prefixes/namespace riêng khi test chạy song song.

## 13. InferredSqlTest: seed tham gia test TX và rollback

File `src/test/java/example/sqldemo/InferredSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(ItemGateway.class)
@SqlConfig(encoding = "UTF-8")
@DisplayName("@Sql INFERRED tham gia test-managed transaction")
class InferredSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    @Sql("/sql/seed-rollback.sql")
    void seededRowsAreVisibleInsideTest() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1, gateway.count("R-282-A"));
        assertEquals(1, gateway.count("R-282-B"));
        assertEquals("Tài liệu Tiếng Việt",
                gateway.title("R-282-B"));
    }

    @Test
    @Sql(
        scripts = "/sql/seed-custom.sql",
        config = @SqlConfig(separator = "@@"))
    void localSeparatorInheritsGlobalUtf8() {
        assertTrue(TestTransaction.isActive());
        assertEquals("Cà phê dữ liệu",
                gateway.title("X-282"));
    }

    @Test
    @Sql(statements = """
            INSERT INTO demo_item(item_id, title, active)
            VALUES ('I-282', 'Inline SQL', TRUE)
            """)
    void inlineSqlStatementAlsoRollsBack() {
        assertEquals(1, gateway.count("I-282"));
    }

    @AfterTransaction
    void allInferredSeedsAreRolledBack() {
        assertEquals(0, gateway.countPrefix("R-282-"));
        assertEquals(0, gateway.count("X-282"));
        assertEquals(0, gateway.count("I-282"));
    }
}
~~~

**Ba phương thức `@Test`**.

Phân tích:

- `@JdbcTest` mặc định tạo test-managed transaction và rollback sau method.
- Không ghi `transactionMode`: `DEFAULT` suy ra `INFERRED`; SQL seed chạy bên trong test transaction.
- `@SqlConfig(encoding="UTF-8")` ở class được kế thừa trong method có local `separator="@@"`.
- `@AfterTransaction` chạy **sau** rollback, nên kiểm đúng rằng những rows từ SQL scripts đã biến mất.
- Không cần cleanup script riêng cho `R-282-`/`X-282`/`I-282` vì không có independent commits trong class này.

**Không nên rút ra:** “@Sql luôn rollback”; ở những contexts không có test transaction hoặc khi dùng `ISOLATED`, behavior khác.

## 14. IsolatedSqlTest: seed và cleanup đều commit độc lập

File `src/test/java/example/sqldemo/IsolatedSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Import(ItemGateway.class)
@Sql(
    scripts = "/sql/seed-isolated.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-isolated.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@DisplayName("@Sql ISOLATED: dữ liệu seed/cleanup đã commit")
class IsolatedSqlTest {

    @Autowired ItemGateway gateway;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager txManager;

    @Test
    void committedSeedIsVisibleToTest() {
        assertEquals(1, gateway.count("C-282"));

        // LOCAL-282 do test tạo; mặc định sẽ bị rollback.
        gateway.create("LOCAL-282", "uncommitted local");
        assertEquals(1, gateway.count("LOCAL-282"));
    }

    @Test
    void committedSeedIsVisibleToRequiresNewTransaction() {
        TransactionTemplate inner =
                new TransactionTemplate(txManager);
        inner.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Integer visible = inner.execute(status ->
                jdbc.queryForObject("""
                        SELECT COUNT(*) FROM demo_item
                        WHERE item_id = ?
                        """, Integer.class, "C-282"));

        assertEquals(1, visible.intValue());
    }

    @AfterTransaction
    void isolatedCleanupCommittedAndTestWritesRolledBack() {
        // @Sql AFTER_TEST_METHOD ISOLATED đã commit DELETE C-282.
        assertEquals(0, gateway.count("C-282"));

        // LOCAL-282 nằm ở test-managed TX và đã rollback.
        assertEquals(0, gateway.count("LOCAL-282"));
    }
}
~~~

**Hai phương thức `@Test`**.

Ở **mỗi method**, class-level scripts chạy:

1. `seed-isolated.sql` tạo `C-282` trong TX mới và commit.
2. Transaction test chính chạy JUnit test body.
3. `cleanup-isolated.sql` chạy trước rollback TestContext nhưng ở **TX mới** và commit DELETE.
4. Test-managed transaction rollback; `LOCAL-282` (nếu có) biến mất.
5. `@AfterTransaction` xác minh cả hai loại dữ liệu đều vắng mặt.

Test thứ hai mở `REQUIRES_NEW` để minh họa **một connection/transaction khác vẫn đọc được seed đã commit**. Nếu seed là INFERRED trong test TX, inner TX dưới READ_COMMITTED thường không thấy nó. Pool phải có đủ connections.

**Quan trọng:** `ISOLATED` không phải một DataSource mới hoặc schema mới. Đây là transaction mới trên cùng database; các concurrent tests vẫn có thể ảnh hưởng nhau nếu dùng cùng key.

## 15. MergedSqlTest: method-level seed không làm mất class cleanup

File `src/test/java/example/sqldemo/MergedSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Import(ItemGateway.class)
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
@Sql(
    scripts = "/sql/cleanup-merge.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class MergedSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    @Sql(
        scripts = "/sql/seed-merge.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED))
    void methodSeedMergesWithClassCleanup() {
        assertEquals(1, gateway.count("M-282"));
    }

    @AfterTransaction
    void classCleanupWasNotOverridden() {
        assertEquals(0, gateway.count("M-282"));
    }
}
~~~

**Một phương thức `@Test`**. `@SqlMergeMode(MERGE)` bảo đảm class-level cleanup (`AFTER_TEST_METHOD`) và method-level seed (`BEFORE_TEST_METHOD`) đều được chọn. `@AfterTransaction` xác nhận cleanup đã commit.

Nếu bỏ `@SqlMergeMode`, method-level `@Sql` có thể override class-level scripts và **cleanup không chạy**, khiến `M-282` tồn tại sau test rollback. Đây là lý do cần phân biệt merge của `@Sql` với global/local merge của `@SqlConfig`.

## 16. NoTestTransactionSqlTest: không có rollback để dọn hộ

File `src/test/java/example/sqldemo/NoTestTransactionSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@JdbcTest
@Import(ItemGateway.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Sql(
    scripts = "/sql/seed-nontx.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-nontx.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class NoTestTransactionSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    void explicitIsolatedScriptsWorkWithoutTestTransaction() {
        assertFalse(TestTransaction.isActive());
        assertEquals(1, gateway.count("N-282"));
    }
}
~~~

**Một phương thức `@Test`**. `@JdbcTest` thường transactional, nhưng `@Transactional(propagation=NOT_SUPPORTED)` ở class **tắt test-managed transaction**. Vì vậy không có rollback TestContext để tự dọn dữ liệu. `seed-nontx.sql` và `cleanup-nontx.sql` được chạy/commit riêng qua ISOLATED.

Ở môi trường có transaction manager, `INFERRED` khi không có transaction hiện hành cũng thường mở transaction mới rồi commit; việc dùng `ISOLATED` ở đây làm **ý định committed fixture/cleanup** rõ ràng, không phụ thuộc nhầm lẫn về context.

## 17. HttpSqlCleanupTest: HTTP thật và cleanup committed

Đây là test quan trọng nhất nếu dùng `@Sql` trong integration test có server thật. `@SpringBootTest(RANDOM_PORT)` tạo embedded HTTP server; client JUnit gửi request qua TCP; controller và service chạy trên server thread **khác thread của test-managed transaction**.

~~~text
JUnit thread                           Server thread
-----------                           -------------
TestContext begins TX A
@Sql BEFORE ISOLATED:
  TX B INSERT S-282; COMMIT
       |
       +-- HTTP GET /api/items/S-282/exists -->
                                      TX server sees S-282
       |
       +-- HTTP POST /api/items/HTTP-282 ----->
                                      ItemService @Transactional
                                      TX C INSERT HTTP-282; COMMIT
       |
Test assertions pass
@Sql AFTER ISOLATED:
  TX D DELETE S-282 and HTTP-282; COMMIT
TestContext ROLLBACK TX A
@AfterTransaction:
  assert both rows absent
~~~

Nếu script cleanup dùng `INFERRED` và tham gia TX A, lệnh DELETE có thể bị rollback khi TX A rollback, **làm `HTTP-282` và `S-282` còn nguyên**. Đây là bug test isolation phổ biến.

File `src/test/java/example/sqldemo/HttpSqlCleanupTest.java`:

~~~java
package example.sqldemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
@Sql(
    scripts = "/sql/seed-http.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-http.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class HttpSqlCleanupTest {

    @LocalServerPort int port;
    @Autowired ItemGateway gateway;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    void isolatedSeedVisibleToServerAndCleanupAfterRequest()
            throws Exception {

        URI committedSeed = url("/api/items/S-282/exists");

        HttpResponse<Void> lookup = http.send(
                HttpRequest.newBuilder(committedSeed)
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(204, lookup.statusCode());

        HttpResponse<Void> created = http.send(
                HttpRequest.newBuilder(
                                url("/api/items/HTTP-282"))
                        .timeout(Duration.ofSeconds(20))
                        .POST(HttpRequest.BodyPublishers.noBody())
                        .build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(201, created.statusCode());
        assertEquals(1, gateway.count("HTTP-282"));
        assertEquals(1, gateway.count("S-282"));
    }

    @AfterTransaction
    void cleanupCommittedEvenThoughTestTransactionRolledBack() {
        // @Sql AFTER_TEST_METHOD ISOLATED đã commit DELETE.
        assertEquals(0, gateway.count("S-282"));
        assertEquals(0, gateway.count("HTTP-282"));
    }

    private URI url(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }
}
~~~

**Một phương thức `@Test`**. Kết quả dự kiến:

- HTTP GET thấy seed đã commit → `204`.
- HTTP POST vào service production → `201`.
- Trong test method, JDBC query thấy hai rows.
- `@Sql AFTER_TEST_METHOD ISOLATED` commit DELETE.
- Test transaction rollback sau đó **không undo cleanup**.
- `@AfterTransaction` kiểm hai rows không còn.

Đây là ví dụ có thể phát hiện trực tiếp lỗi **cleanup chạy đúng phase nhưng sai transaction mode**.

**Lưu ý:** không dùng MockMvc để chứng minh khác thread/physical transaction. MockMvc thường chạy MVC flow trong mock servlet environment cùng test thread. Khi muốn kiểm transaction qua TCP, dùng `RANDOM_PORT` và client thật.

## 18. Tổng hợp tám phương thức kiểm thử

| Class | Số @Test | Bằng chứng |
| --- | ---: | --- |
| `InferredSqlTest` | 3 | INFERRED seed rollback; inline SQL; local separator kế thừa global encoding |
| `IsolatedSqlTest` | 2 | ISOLATED seed/cleanup commit; REQUIRES_NEW nhìn thấy committed seed |
| `MergedSqlTest` | 1 | @SqlMergeMode(MERGE) giữ class-level cleanup |
| `NoTestTransactionSqlTest` | 1 | Tắt test TX, sử dụng ISOLATED seed/cleanup |
| `HttpSqlCleanupTest` | 1 | HTTP server commit và AFTER_TEST_METHOD ISOLATED cleanup |
| **Tổng** | **8** | Không phụ thuộc test order; mỗi case có scope data riêng |

### Chạy Gradle

Trên Linux/macOS:

~~~bash
./gradlew test --tests example.sqldemo.InferredSqlTest --tests example.sqldemo.IsolatedSqlTest --tests example.sqldemo.MergedSqlTest --tests example.sqldemo.NoTestTransactionSqlTest --tests example.sqldemo.HttpSqlCleanupTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.sqldemo.InferredSqlTest --tests example.sqldemo.IsolatedSqlTest --tests example.sqldemo.MergedSqlTest --tests example.sqldemo.NoTestTransactionSqlTest --tests example.sqldemo.HttpSqlCleanupTest
~~~

**Kết quả kỳ vọng:** tám phương thức JUnit Jupiter được phát hiện và **PASS** trên project đã có plugin Boot 3.5.x/Java 17+, đúng file/class/SQL trong bài và test database độc lập. Đây là kết quả thiết kế, **không phải log hoặc stdout từ một lần chạy Gradle đã thực thi**. Test không có `System.out.println(...)`; ngoài test report, log Boot/SQL có thể thay đổi.

Nếu test HTTP bị 401/403 vì ứng dụng thật đã cài Spring Security, hãy cấu hình security test credentials/CSRF đúng contract; không gỡ security filter chỉ để test xanh. Nếu thêm production migrations, phải điều chỉnh setup schema test để tránh SQL init tạo trùng bảng.

## 19. Vì sao AFTER_TEST_METHOD + INFERRED có thể làm cleanup vô hiệu?

Giả sử test `@Transactional`, script seed `ISOLATED` đã commit `S-282`, HTTP server commit thêm `HTTP-282`. Sau đó test:

~~~java
@Sql(
    scripts = "/sql/cleanup-http.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
~~~

Annotation này có `transactionMode=DEFAULT` → effective `INFERRED`. Ở thời điểm afterTestMethod listener chạy, **test-managed transaction có thể vẫn đang mở**. Vì vậy cleanup DELETE chạy trong test transaction.

Diễn biến:

~~~text
Seed independent:   INSERT S-282     -> COMMIT
Server independent: INSERT HTTP-282  -> COMMIT
Test transaction:   DELETE S-282 and HTTP-282  (CHƯA COMMIT)
Test ends:          ROLLBACK test transaction
DB final:           S-282 và HTTP-282 vẫn còn!
~~~

**Cách sửa:** khai báo `config = @SqlConfig(transactionMode = ISOLATED)` cho cleanup. Khi đó DELETE được commit trong một transaction riêng, không bị rollback cùng test.

Nếu test SQL chạy hoàn toàn trong transaction test, một cleanup `INFERRED` trước rollback thường **không cần thiết**: rollback tự dọn cả seed và writes trong transaction. Chỉ sử dụng isolated cleanup khi có **committed state bên ngoài** cần xóa.

## 20. @Sql BEFORE_TEST_CLASS / AFTER_TEST_CLASS: khi nào sử dụng?

Từ Spring Framework 6.1 có thể tạo data/schema một lần cho cả test class:

~~~java
@Sql(
    scripts = "/sql/class-setup.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
@Sql(
    scripts = "/sql/class-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
class BatchDatabaseTests {
    // ...
}
~~~

Đây là mẫu minh họa. Dùng khi:

- Setup expensive (schema/routines/lookup data) và không phụ thuộc test method.
- Test database/schema cô lập riêng cho class.
- Không có concurrent test cùng sửa một state chung.

Không dùng khi:

- Mỗi method cần fixture riêng; chạy chung dẫn tới test order dependency.
- Cleanup DROP schema có nguy cơ xóa bảng của test class khác.
- Test context/shared datasource được cache và đã có migration quản lý schema.
- Muốn seed visible trong method nhưng quên xác định transaction/commit semantics của class-level script.

Class-level phases không được method-level `@Sql` override; scripts per-method vẫn chịu `@SqlMergeMode` như bình thường. Khi kiểm thời điểm commit, nhớ phase class-level không nằm trong test-managed transaction của từng method; `INFERRED` thường chạy và commit nếu transaction manager có sẵn.

## 21. @Sql và @Transactional: bẫy với REQUIRES_NEW, MANDATORY và NOT_SUPPORTED

### 21.1 Inner REQUIRES_NEW không thấy fixture chưa commit

~~~text
Test-managed TX A:
    @Sql BEFORE INFERRED -> INSERT user A (uncommitted)
    service.inner() @Transactional(REQUIRES_NEW):
        TX B SELECT user A -> không thấy dưới READ_COMMITTED
~~~

Giải pháp là `@Sql BEFORE ISOLATED` tạo fixture committed hoặc seed bằng transaction độc lập trước khi bắt đầu test TX. Không thử “fix” bằng cách cho query đọc dirty data chỉ để làm test PASS.

### 21.2 MANDATORY có thể bị test transaction che lỗi

Một service `@Transactional(MANDATORY)` khi gọi từ test `@JdbcTest` mặc định transactional có thể chạy thành công dù production caller không có transaction. Việc seed bằng `@Sql` không phải bằng chứng production call có transaction. Thêm test không có test-managed transaction khi cần xác minh MANDATORY enforcement.

### 21.3 NOT_SUPPORTED và JDBC auto-commit

Nếu method hoặc test chạy không có transaction Spring, JDBC operations có thể auto-commit. Rollback ở test transaction khác không xóa được chúng. Với dữ liệu test viết ở NOT_SUPPORTED, phải cleanup committed riêng.

### 21.4 NESTED không tương đương ISOLATED

`@Transactional(NESTED)` thường dùng savepoint **trong cùng physical transaction**; outer rollback hủy cả nested writes. `@SqlConfig(transactionMode=ISOLATED)` là giao dịch **độc lập** của script. Hai khái niệm khác mục đích và không thay nhau.

## 22. Clean database nhưng không clean “ngoài database”

`@Sql` chỉ chạy SQL trên datasource. Nó không tự xóa:

- File đã được ghi ra filesystem.
- Object đã lưu vào S3/MinIO.
- Redis cache keys.
- Kafka messages, mail đã gửi.
- Search index (Elasticsearch/OpenSearch).
- External API side effects.

Nếu nghiệp vụ có những side effects này, cleanup phải mở rộng bằng fixture/test container/namespace và API dọn tài nguyên thích hợp. Không dựa vào database rollback để chứng minh mọi side effect đã biến mất.

Một nguyên tắc tốt là dùng **test correlation ID** và thực hiện cleanup ở đúng hệ thống sở hữu tài nguyên; xóa chính xác keys của test, không wipe shared services.

## 23. Những lỗi phổ biến

**1. @Sql AFTER_TEST_METHOD nhưng không khai báo transactionMode, tưởng DELETE chắc chắn commit.**  
Khi test TX còn hoạt động, INFERRED có thể join rồi rollback. Dùng ISOLATED cho committed cleanup.

**2. Seed bằng INFERRED rồi HTTP server không nhìn thấy fixture.**  
Server dùng connection khác, không thấy uncommitted row. Dùng ISOLATED hoặc committed seed.

**3. Dùng ISOLATED seed nhưng quên cleanup.**  
Test rollback không xóa committed seed; dễ gây unique constraint trong test kế tiếp.

**4. Đặt class-level cleanup rồi method-level @Sql override mất nó.**  
Dùng `@SqlMergeMode(MERGE)` hoặc khai báo cả seed/cleanup ở method.

**5. Nhầm @SqlConfig global/local merge với @SqlMergeMode.**  
Một cơ chế merge options, một cơ chế merge declarations.

**6. Dùng CONTINUE_ON_ERROR để bỏ qua fixture/cleanup SQL lỗi.**  
Có thể test PASS giả với dataset thiếu. Dùng FAIL_ON_ERROR mặc định.

**7. Dùng IGNORE_FAILED_DROPS cho mọi SQL errors.**  
Chế độ này không dành để bỏ qua mọi failure. Ưu tiên idempotent DELETE/DROP IF EXISTS.

**8. Không chỉ định encoding cho script chứa tiếng Việt.**  
Có thể sinh mojibake trên CI. Lưu UTF-8, đặt `encoding="UTF-8"` khi cần.

**9. Giả định dấu ; luôn tách stored procedure body đúng.**  
Script parser đơn giản không nhất thiết hiểu mọi vendor-specific DDL. Dùng migration runner phù hợp.

**10. Dùng tương đối "data.sql" rồi đổi package test, script không tìm thấy.**  
Dùng absolute classpath path như `/sql/seed-data.sql`.

**11. Dùng @Sql với default script detection mà không tạo đúng file.**  
Spring có thể báo không tìm thấy script. Khai báo paths rõ.

**12. Dùng @JdbcTest với @Repository custom mà không @Import.**  
Slice không tự quét mọi bean production; import gateway cần test.

**13. Tưởng @Sql đọc và ghi vào DataSource mà repository đang dùng dù có nhiều DBs.**  
Khai báo `dataSource`/`transactionManager` phù hợp, kiểm readback.

**14. TRUNCATE toàn bảng trên shared test DB.**  
Dễ phá test khác hoặc foreign key. Dùng IDs/tenant/schema riêng.

**15. Dùng @DirtiesContext rồi nghĩ database external đã sạch.**  
Context cache reset không xóa committed rows khỏi DB bên ngoài.

**16. Kiểm dữ liệu trong test thread rồi kết luận cleanup đã commit.**  
Kiểm sau TestContext rollback bằng `@AfterTransaction` hoặc connection khác/cleanup probe.

**17. Viết @AfterEach kiểm sau rollback.**  
`@AfterEach` chạy trước test rollback; dùng `@AfterTransaction`.

**18. Chạy tests song song trên cùng IDs/schema.**  
Có nguy cơ race/duplicate/locks. Dùng fixture keys duy nhất hoặc cô lập DB.

**19. Để schema.sql, data.sql và Flyway cùng tạo/seed dữ liệu mà không quy hoạch.**  
Có thể trùng schema, thay đổi thứ tự migration hoặc duplicate rows.

**20. H2 test PASS rồi tin rằng PostgreSQL DDL/lock/SQLSTATE giống hệt.**  
Dùng Testcontainers engine tương ứng cho behavior phụ thuộc dialect.

**21. Script cleanup không chạy khi JVM bị kill và dataset rò.**  
AFTER hook không đảm bảo chạy nếu process crash. Dùng ephemeral test DB/container.

**22. Không có logging khi @Sql script fail.**  
Bật `org.springframework.test.context.jdbc` và `org.springframework.jdbc.datasource.init` ở DEBUG trong test environment để thấy resource và statement.

**23. Cleanup gây lock timeout vì test transaction còn giữ row lock.**  
ISOLATED dùng transaction mới; không thể xóa row mà outer TX đang lock dễ dàng. Thiết kế fixture IDs và transaction boundaries hợp lý.

**24. Gửi scripts chứa secrets/production data tới test runner công khai.**  
Dùng dữ liệu giả, cấu hình datasource riêng, không log password.

## 24. Quy trình thiết kế seed/cleanup đáng tin cậy

1. **Định nghĩa đối tượng test:** repository query, business transaction, HTTP endpoint, DB migration hay async job.
2. **Xác định database engine:** H2 cho ví dụ đơn giản, Testcontainers PostgreSQL/MySQL khi cần semantics thật.
3. **Quyết định ai tạo schema:** Boot SQL init, Hibernate DDL, Flyway/Liquibase; tránh chạy chồng chéo.
4. **Chọn fixture scope:** mỗi method, mỗi class, mỗi container hoặc test suite; tránh shared mutable data.
5. **Chọn seed transaction mode:** INFERRED nếu chỉ cần test thread trong rollback TX; ISOLATED nếu caller khác cần committed data.
6. **Chọn cleanup:** rollback tự động nếu đủ; AFTER_TEST_METHOD + ISOLATED cho committed state.
7. **Viết script idempotent, targeted:** DELETE IDs của test, theo thứ tự FK, không truncate chung.
8. **Nếu class-level và method-level @Sql cùng tồn tại,** đánh giá @SqlMergeMode MERGE/OVERRIDE.
9. **Cấu hình parser:** encoding=UTF-8, separator đúng, comment syntax đúng, tránh SQL dialect không được hỗ trợ.
10. **Chọn ErrorMode:** FAIL_ON_ERROR trừ khi có lý do và tests kiểm partial state.
11. **Bật TestContext transaction awareness:** xác định @Transactional ở test, service, HTTP server thread và REQUIRES_NEW.
12. **Kiểm dữ liệu trong test:** assert rows, values, count và query thật, không chỉ script ran without error.
13. **Kiểm sau cleanup:** @AfterTransaction hoặc probe phù hợp, không chỉ @AfterEach.
14. **Đảm bảo cleanup cả khi test fail:** lifecycle hooks, finally/isolated scripts, ephemeral database.
15. **Chạy CI độc lập:** IDs/schema riêng, test không dựa vào thứ tự, không chạm production credentials.

### Checklist cuối

- [ ] Script path được chỉ rõ, nằm trong test resources và CI đọc được.
- [ ] Đã phân biệt Boot `schema.sql`/`data.sql` initializer và TestContext `@Sql`.
- [ ] Đã hiểu BEFORE/AFTER_TEST_METHOD xảy ra ở đâu so với test transaction rollback.
- [ ] Biết `DEFAULT` hiệu lực là `INFERRED` nếu không có global override.
- [ ] Seed transactional test chỉ cần INFERRED khi không có external committed writes.
- [ ] Seed cho HTTP server/REQUIRES_NEW được commit bằng ISOLATED hoặc setup riêng.
- [ ] Committed rows được xóa bằng cleanup thực sự commit.
- [ ] AFTER_TEST_METHOD cleanup không vô tình join test TX rồi rollback.
- [ ] Class-level cleanup không bị method-level @Sql override ngoài ý muốn.
- [ ] @SqlConfig global/local inheritance đúng với encoding/separator/transactionMode.
- [ ] ErrorMode không che dữ liệu thiếu hoặc permission/SQL lỗi.
- [ ] Cleanup DELETE chỉ xóa IDs của test và chạy thành công khi rows không tồn tại.
- [ ] Không dùng TRUNCATE toàn bảng trên DB chia sẻ.
- [ ] Tests đọc state sau rollback/cleanup ở thời điểm phù hợp.
- [ ] Không chạy song song trên cùng fixture IDs/schema khi chưa có isolation.
- [ ] Có test trên DB production-like khi migration, trigger, transaction hoặc vendor SQL quan trọng.
- [ ] Không trỏ SQL scripts vào database production.

**Ghi nhớ:** `@Sql` định nghĩa **chạy cái gì và khi nào**, còn `@SqlConfig(transactionMode=...)` quyết định **nó tham gia transaction nào và có được commit độc lập hay không**. Với test transaction đơn giản, `INFERRED` và rollback mặc định rất tiện. Với dữ liệu đã được một HTTP server, REQUIRES_NEW hoặc seed isolated commit, cleanup **AFTER_TEST_METHOD + ISOLATED** là cơ chế minh bạch hơn. Kết hợp script scope chính xác, MERGE khi cần, error handling nghiêm ngặt và post-cleanup verification sẽ giúp test lặp lại được, không làm rò dữ liệu.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): `@Sql`, script paths, execution phases, transactions, MERGE/OVERRIDE, TestExecutionListener.
- [Spring Framework 6.2 — @SqlConfig API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html): thuộc tính encoding, separator, errorMode, dataSource, transactionManager.
- [Spring Framework 6.2 — TransactionMode API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.TransactionMode.html): INFERRED inference rules và ISOLATED.
- [Spring Framework 6.2 — SqlScriptsTestExecutionListener](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/test/context/jdbc/SqlScriptsTestExecutionListener.html): listener order 5000 và before/after test phases.
- [Spring Framework 6.2 — @SqlMergeMode](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-sqlmergemode.html): method-level override vs MERGE.
- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): rollback, @AfterTransaction, test vs server threads.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @JdbcTest/@DataJpaTest, RANDOM_PORT.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql/data.sql, initialization mode, Flyway/Liquibase cautions.
