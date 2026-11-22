# `readOnly` là chỉ dẫn có hiệu lực tùy transaction manager, JDBC driver và cơ sở dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `@Transactional(readOnly = true)` thật sự khai báo điều gì trong Spring Framework.
2. Phân biệt **Spring transaction metadata**, `Connection.setReadOnly(true)` của JDBC, cơ chế tối ưu của Hibernate/JPA và **quy tắc ghi dữ liệu thực tế do database thi hành**.
3. Hiểu vì sao `readOnly = true` **không phải lệnh cấm `INSERT`, `UPDATE` hay `DELETE` phổ quát**; hành vi phụ thuộc manager, driver, connection và DBMS.
4. Biết cách cấu hình chính sách read-only mạnh hơn trên database hỗ trợ, ví dụ `DataSourceTransactionManager#setEnforceReadOnly(true)`, và giới hạn của cách này.
5. Dự đoán điều gì xảy ra khi một method `REQUIRED` tham gia transaction có cờ read-only khác với annotation của chính nó.
6. Chạy ví dụ **Java 17+, Spring Boot 3.3.5, Spring JDBC và H2** để quan sát cờ Spring, trạng thái JDBC connection, `UPDATE`, commit và rollback.
7. Thiết kế query service an toàn, tránh nhầm read-only với phân quyền database, isolation level, timeout hoặc định tuyến đến read replica.

**Chủ đề chính:** `readOnly` là **một chỉ dẫn giao dịch** mà tầng hạ tầng có thể sử dụng để tối ưu hoặc thực thi ràng buộc, **không phải cam kết rằng mọi hệ quản trị sẽ chặn thao tác ghi**.

---

## 1. Câu trả lời ngắn và chính xác

Xét service:

```java
@Service
public class ProductQueryService {

    @Transactional(readOnly = true)
    public ProductView load(long productId) {
        return repository.findView(productId);
    }
}
```

Đây là snippet minh họa; `ProductView`, `repository` và các import nghiệp vụ thuộc ứng dụng thực tế. Khi Spring AOP intercept lời gọi `load()` từ một bean khác, transaction definition mang `readOnly=true`. Điều đó có nghĩa **“transaction này được kỳ vọng chủ yếu chỉ đọc”**.

Những điều **có thể xảy ra**:

- Spring transaction infrastructure công bố **read-only flag** cho mã đang tham gia transaction.
- Transaction manager JDBC có thể gọi `Connection.setReadOnly(true)` trên connection trước transaction để **gợi ý cho driver/DBMS tối ưu**.
- Một JPA/Hibernate transaction manager có thể điều chỉnh **flush mode** hoặc cơ chế dirty checking của ORM để giảm chi phí khi chỉ đọc.
- Nếu được **cấu hình thêm** và DBMS hỗ trợ, manager có thể gửi lệnh SQL như `SET TRANSACTION READ ONLY` để DBMS **từ chối một số thao tác thay đổi dữ liệu**.
- Có thể dùng cờ read-only trong một cơ chế **routing do ứng dụng tự thiết kế**, ví dụ chọn replica đọc khi bắt đầu transaction phù hợp.

Những điều **không được tự suy ra**:

- `readOnly=true` **không mặc định tương đương với quyền database chỉ được SELECT**.
- Nó **không** làm tất cả `jdbc.update(...)` thất bại ở mọi DBMS.
- Nó **không** bắt Spring tự rollback bất kỳ transaction nào đã thực hiện `UPDATE`.
- Nó **không** bảo đảm query dùng replica, không bảo đảm query chạy nhanh hơn.
- Nó **không** biến method đang nằm trong transaction read-write có sẵn thành một physical read-only transaction độc lập.
- Nó **không** thay thế transaction isolation, rollback rules, timeout, security hoặc kiểm soát quyền truy cập.

Câu trả lời chính xác cho câu hỏi **“`UPDATE` bên trong `@Transactional(readOnly=true)` có bị chặn không?”** là: **phụ thuộc transaction manager, JDBC driver, DBMS, cách cấu hình read-only và việc method có thật sự mở một transaction mới hay không**.

## 2. Đừng trộn lẫn bốn tầng của read-only

Bốn tầng cùng dùng từ “read-only” nhưng không có chung hợp đồng kỹ thuật.

| Tầng | Cờ hoặc API | Điều nó biểu thị | Có đảm bảo cấm mọi thao tác ghi? |
| --- | --- | --- | --- |
| Spring transaction definition | `@Transactional(readOnly = true)` | Ý định của phương thức về transaction | **Không** |
| Spring thread-bound transaction context | `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Cờ transaction hiện tại mà Spring công bố | **Không** |
| JDBC connection | `Connection.setReadOnly(true)`, `isReadOnly()` | Gợi ý/chế độ mà driver và DBMS xử lý | **Không một cách phổ quát** |
| DBMS transaction / quyền truy cập | SQL read-only transaction, quyền `GRANT`/`REVOKE`, read-only replica | Chính sách và cơ chế do engine áp dụng | **Tùy chính sách, lệnh SQL, DBMS và quyền thực tế** |

Trong ứng dụng dùng JPA/Hibernate còn một tầng khác: **hành vi của persistence context**, ví dụ chế độ flush hoặc dirty checking. Hibernate có thể bỏ qua một số việc đồng bộ entity trong transaction read-only, nhưng không biến annotation Spring thành “tường lửa chống ghi” cho mọi `nativeQuery`, `JdbcTemplate` hoặc câu SQL trực tiếp.

### Một ví dụ về sự khác nhau

```text
Spring @Transactional(readOnly=true)
             |
             +--> Thread transaction metadata: readOnly = true
             |
             +--> DataSourceTransactionManager
                       |
                       +--> JDBC Connection.setReadOnly(true)
                                 |
                                 +--> Driver/DBMS có thể tối ưu hoặc bỏ qua
                       |
                       +--> SQL UPDATE vẫn có thể được thực thi
                                 |
                                 +--> Có DBMS chấp nhận
                                 +--> Có DBMS/chế độ từ chối
```

Một người đọc log Spring thấy `"readOnly=true"` mới chỉ biết **declaration/transaction context**. Không thể từ đó kết luận chính xác `Connection.isReadOnly()` trả gì, database có đang ở SQL read-only transaction hay không, hoặc statement `UPDATE` đã bị chặn.

## 3. Mặc định của `@Transactional` là gì?

Trong Spring Framework, nếu không ghi `readOnly`, `@Transactional` mặc định dùng:

```java
@Transactional(readOnly = false)
public void updateSomething() {
    // ...
}
```

Tương tự `@Transactional` không đối số sẽ dùng propagation `REQUIRED`, isolation `DEFAULT`, read-write flag và rollback rules mặc định. Những thuộc tính là **các chiều khác nhau**.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT,
    readOnly = true,
    timeout = 30
)
public Report readReport() {
    // ...
}
```

Snippet trên khai báo bốn khía cạnh:

- `REQUIRED`: tạo transaction nếu chưa có, hoặc tham gia transaction phù hợp đã tồn tại.
- `DEFAULT`: không yêu cầu một isolation level JDBC cụ thể khác với resource mặc định.
- `readOnly=true`: báo ý định **chỉ đọc**, hạ tầng quyết định cách xử lý.
- `timeout=30`: yêu cầu timeout cho transaction mới, nếu transaction manager hỗ trợ. Timeout không làm read-only trở thành “cấm ghi”.

**Không được suy diễn rằng `readOnly=true` tự nâng isolation lên `SERIALIZABLE`.** Hai thuộc tính có mục tiêu riêng. Một read-only transaction có thể chạy ở `READ_COMMITTED` hoặc `REPEATABLE_READ` tùy resource.

## 4. Spring JDBC: `Connection.setReadOnly(true)` là một hint

Với `DataSourceTransactionManager`, khi bắt đầu một **transaction JDBC mới** và definition có `readOnly=true`, Spring thường chuẩn bị connection bằng `DataSourceUtils.prepareConnectionForTransaction(...)` và gọi `Connection.setReadOnly(true)` trước khi thực hiện transaction. Cuối transaction, Spring cố **phục hồi trạng thái connection** khi cần để tránh ảnh hưởng người mượn connection tiếp theo từ pool.

JDBC API mô tả `Connection.setReadOnly(boolean)` là **gợi ý cho driver** để database có thể tối ưu; hành vi thực tế **không được bảo đảm giống nhau** trên mọi driver. Một số driver/DBMS có thể từ chối statement ghi; số khác chỉ dùng flag để tối ưu, hoặc bỏ qua.

### H2 là phản ví dụ rõ ràng

Theo tài liệu Javadoc của H2 `JdbcConnection`:

- `setReadOnly(boolean)` nhận tham số nhưng **bỏ qua giá trị** khi database mở ở chế độ ghi bình thường.
- `isReadOnly()` phản ánh database thực tế có được mở ở chế độ read-only hay không.
- H2 document rõ: JDBC read-only hint **không tự làm cấm ghi**.

Vì thế trong H2 in-memory mặc định, một transaction Spring `@Transactional(readOnly=true)` có thể có:

```text
Spring transaction context: readOnly = true
JDBC connection: Connection.isReadOnly() = false
Database: UPDATE vẫn thực hiện được
```

Đây **không** phải Spring “quên annotation”; đây là hành vi cụ thể của JDBC driver/DBMS. Ví dụ hoàn chỉnh ở mục 8 sẽ chứng minh trạng thái này và kiểm tra dữ liệu sau khi commit.

### Lưu ý về `Connection.isReadOnly()`

Giá trị này do JDBC driver báo lại. Với H2, nó phản ánh **database-level read-only**, không phản ánh Spring metadata. Với driver khác, semantics có thể khác. Vì vậy:

- Dùng `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` để quan sát **Spring transaction flag**.
- Dùng `Connection.isReadOnly()` để quan sát **JDBC driver's read-only status**.
- Dùng **một thử nghiệm SQL an toàn trong môi trường test** để biết DBMS có thực sự chặn thao tác ghi hay không.

Không thực hiện thử nghiệm ghi phá hoại trên production chỉ để kiểm chứng một flag; dùng test schema, transaction rollback và user có quyền giới hạn.

## 5. Transaction manager có thể thực hiện read-only khác nhau

### 5.1. `DataSourceTransactionManager` và `JdbcTransactionManager`

Đối với JDBC, `DataSourceTransactionManager` dùng connection được Spring quản lý; `JdbcTransactionManager` kế thừa hướng tiếp cận đó và bổ sung khả năng dịch các JDBC exception trong một số đường commit/rollback.

Ở cấu hình thông dụng:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

`@Transactional(readOnly=true)` được chuyển thành JDBC hint `Connection.setReadOnly(true)` khi bắt đầu transaction mới. Mặc định **không nên coi flag này là cơ chế bắt buộc chặn DML**.

### 5.2. `DataSourceTransactionManager#setEnforceReadOnly(true)`

Spring JDBC có cấu hình **mạnh hơn**:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);

    manager.setEnforceReadOnly(true);
    return manager;
}
```

**Đây là phương án cấu hình thay thế**, không dùng cùng lúc với `@Bean transactionManager` của chương trình H2 mục 8. Với DBMS hiểu cú pháp tương ứng, Spring có thể gửi SQL **`SET TRANSACTION READ ONLY`** cho transaction mới được khai báo read-only.

Theo Javadoc Spring, cách này phù hợp với các DBMS như **PostgreSQL, Oracle, MySQL** trong những phiên bản/cấu hình hỗ trợ. Nó đi xa hơn **JDBC hint** và có thể yêu cầu database thực sự **từ chối DML trong transaction**.

Tuy nhiên:

- Chỉ bật nếu DBMS/driver và đường thực thi transaction hỗ trợ **đúng cú pháp, đúng timing và semantics**.
- Có thể gây lỗi khởi tạo transaction nếu database không hiểu SQL được gửi.
- Khi method chỉ tham gia transaction có sẵn, không thể giả định nó được phép chuyển physical transaction đó sang read-only mới.
- Cần test **trên DBMS đích**, kiểm tra câu `INSERT`/`UPDATE` bị từ chối như mong đợi và rollback dữ liệu đã thay đổi.
- **Không bật cấu hình này trong demo H2 phía dưới.** Mục đích demo là quan sát H2 bỏ qua JDBC hint, không phải thử một cú pháp SQL enforcement chưa chứng minh phù hợp với H2.

Đây là **database transaction policy**, không thay cho quyền truy cập an toàn của user DB. Nếu yêu cầu bảo mật là “tài khoản không được thay đổi dữ liệu”, hãy dùng quyền DB hạn chế hoặc database replica chỉ đọc.

### 5.3. `JpaTransactionManager` và Hibernate

Với JPA/Hibernate, Spring Data JPA ghi nhận `readOnly=true` có thể dẫn đến **tối ưu ở JPA provider**, ví dụ đặt Hibernate flush mode thành `MANUAL` để tránh công việc dirty checking/flush tự động không cần thiết trong các transaction chỉ đọc.

Ví dụ:

```java
@Service
public class CatalogQueryService {
    private final ProductRepository repository;

    public CatalogQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Product> findAvailable() {
        return repository.findByAvailableTrue();
    }
}
```

Đây là snippet Spring Data JPA, chưa khai báo các kiểu nghiệp vụ hay dependency JPA trong project JDBC demo. Với Hibernate, những tối ưu cụ thể còn phụ thuộc phiên bản và cách Spring thiết lập Session/EntityManager. Đừng đồng nhất “Hibernate không tự flush một số entity” với “mọi native SQL ghi sẽ bị database từ chối”.

Một số ngộ nhận cần tránh:

- `@Transactional(readOnly=true)` không tự cấm application gọi `repository.save(...)` ở mức Java API.
- Flush mode/dirty checking có thể thay đổi nên **không nên** trông cậy vào việc `save` hoặc sửa entity rồi transaction kết thúc sẽ có cùng hành vi ở mọi cấu hình.
- Native SQL, `JdbcTemplate`, stored procedure và những thành phần khác có thể đi qua những đường thực thi khác nhau.
- Nếu cần bảo đảm không ghi, phải áp dụng **DB-level read-only transaction hoặc quyền dữ liệu** phù hợp với stack thực tế, và kiểm thử.

**Spring Data JPA repositories:** các CRUD method được triển khai bởi `SimpleJpaRepository` có transaction configuration kế thừa; read operations thường được cấu hình read-only, còn modifying operations read-write. Declared query methods không mặc nhiên nhận mọi cấu hình transactional. Transaction ở **service boundary** thường quan trọng hơn annotation riêng của từng repository method, vì nó xác định transaction vật lý cuối cùng.

### 5.4. `JtaTransactionManager` và manager khác

JTA, reactive và custom transaction managers có những capability riêng. Một manager có thể nhận `TransactionDefinition.isReadOnly()` nhưng **không dịch cờ đó thành JDBC `Connection.setReadOnly(true)` hoặc SQL enforcement**. Không suy luận rằng một annotation có cùng tham số sẽ tạo cùng database behavior trên mọi nền tảng.

Với `ReactiveTransactionManager`, transaction context được truyền theo reactive pipeline, không dựa vào cùng thread-local JDBC connection như ví dụ này. Bài tập H2/JDBC ở mục 8 chứng minh **imperative JDBC behavior**; áp dụng vào R2DBC phải kiểm chứng driver và transaction manager riêng.

## 6. Nếu DB vẫn cho phép `UPDATE` trong read-only thì sao?

Ví dụ một service:

```java
@Transactional(readOnly = true)
public void updateByAccident() {
    jdbcTemplate.update(
        "UPDATE inventory SET quantity = quantity + 1 WHERE id = ?",
        1L
    );
}
```

Đây chỉ là snippet minh họa. Hậu quả phụ thuộc DBMS:

- Với H2 JDBC đang writable và `setReadOnly` bị bỏ qua, câu `UPDATE` có thể thành công và transaction **commit** bình thường.
- Với PostgreSQL transaction thực sự được đặt **`READ ONLY`** ở tầng SQL, thao tác ghi dữ liệu thuộc loại bị cấm có thể bị DB từ chối.
- Với user database chỉ có `SELECT`, `UPDATE` bị từ chối vì **quyền database**, bất kể flag Spring.
- Với JPA/Hibernate, một số thay đổi entity có thể không tự flush do read-only optimizations, nhưng điều này không có nghĩa mọi hình thức ghi đều bị chặn.

**Kết luận:** `readOnly=true` không tự **rollback** transaction khi nó chứa `UPDATE` hợp lệ. Nếu DB cho phép SQL và method trả về bình thường, Spring có thể commit.

### Khi method ném exception

`readOnly=true` không thay đổi rollback rules mặc định:

```java
@Transactional(readOnly = true)
public void writeThenFail() {
    jdbcTemplate.update(
        "UPDATE inventory SET quantity = quantity + 10 WHERE id = 1"
    );
    throw new IllegalStateException("Business failure");
}
```

Trong transaction JDBC mới, nếu `UPDATE` đã chạy thành công nhưng `IllegalStateException` thoát qua interceptor, Spring mặc định **rollback**. Đây là hậu quả của **rollback rules**, không phải do `readOnly=true` cấm ghi.

Bởi vậy cần phân biệt ba câu hỏi: **DB có chấp nhận statement không? Transaction interceptor có quyết định rollback không? Caller có đang ở transaction khác không?**

## 7. `REQUIRED` kế thừa transaction đang tồn tại; read-only không được áp riêng cho mỗi method

Một điểm gây nhiều bug là **annotation của method inner không nhất thiết trở thành mode mới cho physical transaction**.

Giả sử:

```java
@Service
public class ReportFacade {
    private final ReportRepository reports;

    public ReportFacade(ReportRepository reports) {
        this.reports = reports;
    }

    @Transactional(readOnly = true)
    public Report run() {
        return reports.buildReportAndMaybeUpdate();
    }
}
```

Trong một bean khác:

```java
@Service
public class ReportRepository {

    @Transactional(readOnly = false)
    public Report buildReportAndMaybeUpdate() {
        // ...
    }
}
```

Hai đoạn chỉ minh họa, không phải lớp Java chạy độc lập. Khi `run()` tạo transaction T với `readOnly=true`, method trong sử dụng `REQUIRED` mặc định **tham gia T**. Nó không tự mở một transaction read-write mới chỉ vì `readOnly=false`.

Nếu DB/driver không cưỡng chế read-only thì lệnh ghi ở inner vẫn có thể thực hiện được. Nếu DB đã cưỡng chế read-only cho T, inner thường **không thể** chỉ nhờ annotation `readOnly=false` mà phá được chính sách đó.

### Trường hợp ngược lại

Nếu outer có `@Transactional` read-write, còn inner có `@Transactional(readOnly=true)` và `REQUIRED`, inner cũng **tham gia transaction ngoài**. Không được kỳ vọng Spring luôn tạm đặt read-only chỉ cho một đoạn con của cùng physical T.

```text
Caller
  |
  v
Outer @Transactional(readOnly=false) -> BEGIN T read-write
  |
  v
Inner @Transactional(readOnly=true), REQUIRED -> join T
  |
  v
SQL sử dụng physical transaction T
  |
  v
Outer -> COMMIT/ROLLBACK T
```

Thông thường chính sách resource/connection được thiết lập **khi T bắt đầu**, không “chuyển chế độ” mỗi lần Java gọi một method khác.

### `validateExistingTransaction=true`

Một `AbstractPlatformTransactionManager` có tùy chọn:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);

manager.setValidateExistingTransaction(true);
```

Đây là snippet cấu hình thay thế. Khi validation bật, manager có thể **từ chối một method read-write tham gia transaction đang được Spring đánh dấu read-only**, thay vì lặng lẽ để nó chạy trong T. Ví dụ outer read-only, inner `REQUIRED` read-write có thể phát sinh `IllegalTransactionStateException` khi tham gia T.

Quan trọng:

- Đây là **hàng rào ở transaction infrastructure**, không phải chính sách quyền database toàn diện.
- Nó không chứng minh mọi statement phát ra từ **chính method read-only** sẽ bị chặn.
- Không mặc định bật ở mọi application; thay đổi flag có thể thay đổi logic của service lồng nhau.
- Việc xác nhận hạ tầng có hỗ trợ validation và đường đi exception cần test trong hệ thống thật.

### `REQUIRES_NEW` và `NESTED`

| Inner method | Khi outer đang có T | Read-only thực tế |
| --- | --- | --- |
| `REQUIRED`, `readOnly=false` | Join T | Thường dùng policy của T; không tự mở transaction mới |
| `REQUIRED`, `readOnly=true` | Join T | Thường dùng policy của T |
| `REQUIRES_NEW`, `readOnly=false` | Tạm đình chỉ T, mở transaction mới | Policy của transaction/connection mới |
| `REQUIRES_NEW`, `readOnly=true` | Mở transaction mới độc lập | Manager có cơ hội áp read-only hint/enforcement vào transaction mới |
| `NESTED`, `readOnly=true` | Với JDBC, tạo savepoint trong cùng T | Không có connection/physical transaction read-only độc lập |

Chọn `REQUIRES_NEW` chỉ để “bật read-write trong outer read-only” là một thay đổi lớn về atomicity: transaction con có thể commit độc lập ngay cả khi outer rollback. Phải cân nhắc nghiệp vụ và connection pool, không chỉ cờ read-only.

---

## 8. Demo chạy được: H2 bỏ qua JDBC read-only hint nhưng Spring vẫn quản lý transaction

Ví dụ này được thiết kế để chứng minh **ba sự thật độc lập**:

1. Spring transaction context biết `readOnly=true`.
2. H2 `JdbcConnection.setReadOnly(true)` **không biến connection của database writable thành database read-only**.
3. Trên H2, một câu `UPDATE` trong method read-only **có thể commit** khi method hoàn tất bình thường, hoặc **rollback** khi unchecked exception thoát ra.

Ngoài ra, service ngoài read-only gọi service trong `REQUIRED` read-write qua một **Spring bean khác**, cho thấy cờ ở inner không tự thay transaction policy của outer.

### 8.1. Cấu trúc project

```text
read-only-hint-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/readonly/
    │   │   ├── WriteService.java
    │   │   ├── ReadOnlyService.java
    │   │   └── ReadOnlyHintApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/
        └── java/example/readonly/
            └── ReadOnlyHintApplicationTest.java
```

Sử dụng Gradle có JDK 17+ và Spring Boot 3.3.5. Có thể tạo cấu trúc bằng Spring Initializr (Java 17, Spring Web không cần, JDBC và H2) rồi thay các file được nêu dưới đây. Chương trình là CLI, không chạy web server.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'read-only-hint-demo'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

Chúng ta dùng **Spring JDBC**, không dùng Hibernate trong demo. Điều này tránh cho flush mode của ORM tác động lên kết quả. H2 là database test in-memory. Việc sử dụng JDBC ở đây không có nghĩa kết luận về H2 cũng đúng cho PostgreSQL/MySQL/Oracle.

### 8.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:read_only_hint_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Không cấu hình `setEnforceReadOnly(true)` trên transaction manager. Đây là chủ ý: ta đang chứng minh **JDBC hint không đảm bảo chống ghi**. `DB_CLOSE_DELAY=-1` giữ H2 in-memory database tới khi JVM kết thúc. Mỗi kịch bản được reset về số lượng ban đầu để quan sát không bị cộng dồn.

### 8.5. `src/main/resources/schema.sql`

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    quantity BIGINT NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory (id, quantity) VALUES (1, 100);
```

Schema chỉ có một hàng. Sau mỗi method, caller đọc dữ liệu **ngoài service transaction** để kiểm tra mức `quantity` cuối. Nếu chỉ nhìn số hàng `jdbc.update(...)` giữa transaction, chưa thể kết luận commit đã diễn ra.

### 8.6. `src/main/java/example/readonly/WriteService.java`

```java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;

    public WriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = false
    )
    public boolean incrementRequired() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 5 WHERE id = 1"
        );
        return TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();
    }
}
```

Method này **khai báo read-write**. Nếu caller chưa có transaction, nó mở transaction read-write và Spring current transaction flag là `false`. Nếu method bị gọi qua bean proxy trong một transaction outer **đã đọc-only**, `REQUIRED` sẽ tham gia T ngoài; `readOnly=false` của method trong **không tự ghi đè** flag/resource policy của T.

`WriteService` tách thành Spring bean riêng để `ReadOnlyService` gọi **qua transaction proxy**, không bị lỗi self-invocation.

### 8.7. `src/main/java/example/readonly/ReadOnlyService.java`

```java
package example.readonly;

import java.sql.Connection;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReadOnlyService {
    private final JdbcTemplate jdbc;
    private final WriteService writer;

    public ReadOnlyService(JdbcTemplate jdbc, WriteService writer) {
        this.jdbc = jdbc;
        this.writer = writer;
    }

    private String flags() {
        Boolean jdbcReadOnly = jdbc.execute(
            (ConnectionCallback<Boolean>) Connection::isReadOnly
        );
        if (jdbcReadOnly == null) {
            throw new IllegalStateException(
                "JDBC connection returned no read-only status"
            );
        }

        boolean springReadOnly = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();

        return "spring=" + springReadOnly +
               ", jdbc=" + jdbcReadOnly +
               ", active=" + active;
    }

    @Transactional(readOnly = true)
    public String observe() {
        return flags();
    }

    @Transactional(readOnly = true)
    public String updateDespiteHint() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 10 " +
            "WHERE id = 1"
        );
        return flags();
    }

    @Transactional(readOnly = true)
    public void updateThenFail() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 20 " +
            "WHERE id = 1"
        );
        throw new IllegalStateException("demonstration rollback");
    }

    @Transactional(readOnly = true)
    public String outerReadOnlyCallsRequiredWriter() {
        boolean outerFlag = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        boolean innerFlag = writer.incrementRequired();

        return "outer=" + outerFlag + ", inner=" + innerFlag;
    }
}
```

**Điểm quyết định để đo đúng connection:** `flags()` dùng `JdbcTemplate.execute(ConnectionCallback)`. `JdbcTemplate` lấy connection từ `DataSourceUtils` nên khi transaction JDBC đang active, nó thao tác trên **connection đã được Spring bind vào transaction**. Nếu bạn tự mở connection thứ hai từ `DataSource`, kết quả có thể mô tả một session khác.

`flags()` không cần `@Transactional` riêng vì nó được gọi từ các method public mà proxy đã tạo transaction. `updateDespiteHint()` và `updateThenFail()` được chủ động đặt trong service query để minh họa **lỗi thiết kế cần tránh**, không phải khuyến nghị ứng dụng thường xuyên ghi trong read-only method.

### 8.8. `src/main/java/example/readonly/ReadOnlyHintApplication.java`

```java
package example.readonly;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ReadOnlyHintApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadOnlyHintApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE inventory SET quantity = 100 WHERE id = 1");
    }

    private static long quantity(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
            "SELECT quantity FROM inventory WHERE id = 1",
            Long.class
        );
        if (value == null) {
            throw new IllegalStateException("Inventory row missing");
        }
        return value;
    }

    @Bean
    ApplicationRunner demo(
            ReadOnlyService reader,
            WriteService writer,
            JdbcTemplate jdbc) {
        return args -> {
            reset(jdbc);
            System.out.println(
                "probe | " + reader.observe() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "write in readOnly | " + reader.updateDespiteHint() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            try {
                reader.updateThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("expected exception | " + ex.getMessage());
            }
            System.out.println(
                "after rollback | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "REQUIRED joined | " +
                reader.outerReadOnlyCallsRequiredWriter() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "standalone writer | spring=" +
                writer.incrementRequired() +
                " | quantity=" + quantity(jdbc)
            );
        };
    }
}
```

`@EnableTransactionManagement` bật Spring declarative transaction handling; một bean `PlatformTransactionManager` dùng chính H2 `DataSource` mà `JdbcTemplate` đang dùng. `ApplicationRunner` được inject **Spring bean proxies** rồi gọi qua chúng, không tự `new ReadOnlyService(...)`.

`reset()` thực thi từ ApplicationRunner **ngoài** service transaction và đặt quantity về 100 trước từng case. Vì tất cả method trong demo kết thúc trước khi `quantity(jdbc)` được gọi, số lượng in ra là **trạng thái sau commit/rollback**.

### 8.9. Chạy project

Trên macOS/Linux, nếu project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu mới tạo file mà chưa có wrapper, có thể chạy `gradle bootRun` với Gradle đã cài tương thích hoặc tạo wrapper bằng Gradle. Chương trình không thể chạy độc lập bằng `javac`/`java` mà không có Spring và H2 trên classpath.

**Những dòng do chương trình in**, bỏ qua startup logs của Boot/Gradle, dự kiến:

```text
probe | spring=true, jdbc=false, active=true | quantity=100
write in readOnly | spring=true, jdbc=false, active=true | quantity=110
expected exception | demonstration rollback
after rollback | quantity=100
REQUIRED joined | outer=true, inner=true | quantity=105
standalone writer | spring=false | quantity=105
```

Các dòng là **kết quả suy ra từ code, Spring JDBC và H2 driver behavior đã được tài liệu hóa**; không phải khẳng định đã biên dịch/chạy project trong môi trường này.

### 8.10. Diễn giải từng kết quả

**`probe`:** Spring đã tạo transaction với `readOnly=true`, nên `TransactionSynchronizationManager` báo `spring=true` và `active=true`. Nhưng H2 `Connection.isReadOnly()` trả `false` khi database writable; `Connection.setReadOnly(true)` là hint bị H2 bỏ qua. Không có SQL ghi nên quantity giữ 100.

**`write in readOnly`:** `@Transactional(readOnly=true)` vẫn có `spring=true`. `JdbcTemplate` chạy một `UPDATE` hợp lệ trên writable H2 và method trả về bình thường; transaction manager commit. Quantity tăng từ 100 lên **110**. Đây là minh họa trực tiếp rằng **read-only hint không phải cơ chế bắt buộc chặn ghi**.

**`expected exception`/`after rollback`:** Trong một read-only transaction khác, `UPDATE +20` được H2 chấp nhận nhưng method ném `IllegalStateException`. Vì unchecked exception thoát qua transaction interceptor, Spring mặc định rollback nên quantity trở về **100**. Read-only không hủy bỏ rollback rules.

**`REQUIRED joined`:** `outerReadOnlyCallsRequiredWriter()` tạo transaction read-only T, `WriteService.incrementRequired()` có `REQUIRED` và `readOnly=false` nhưng tham gia **chính T**. Cờ hiện hành mà inner nhìn thấy vẫn là `true`, vì transaction policy thuộc scope vật lý đã mở. H2 không chặn SQL nên quantity tăng thành **105**. Đây là lý do code không nên dựa vào annotation của riêng một repository method để đổi mode giao dịch trong cả call chain.

**`standalone writer`:** Không có outer transaction, `WriteService.incrementRequired()` tạo một transaction **read-write mới**. Spring context trả `false`, update thành công và quantity là **105**.

### 8.11. Tại sao demo không in `Connection.isReadOnly()=true`?

Trực giác dễ mắc là “Spring gọi `setReadOnly(true)`, vậy `isReadOnly()` phải trả `true`”. Với một driver JDBC, chỉ dẫn có thể bị bỏ qua. H2 Javadoc xác nhận `setReadOnly` được bỏ qua và `isReadOnly()` trả trạng thái database-level. Đây chính là lý do sử dụng H2 làm ví dụ về **sự khác nhau giữa intention và enforcement**.

Nếu thay H2 bằng database khác, **không sao chép kết quả stdout**. Driver có thể phản ánh `isReadOnly=true`, có thể thực thi read-only transaction hoặc từ chối ghi. Phải quan sát manager, driver và DBMS cụ thể.

## 9. Kiểm thử JUnit 5: không chỉ assert một flag

Tạo `src/test/java/example/readonly/ReadOnlyHintApplicationTest.java`:

```java
package example.readonly;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class ReadOnlyHintApplicationTest {
    @Autowired ReadOnlyService reader;
    @Autowired WriteService writer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE inventory SET quantity = 100 WHERE id = 1");
    }

    private long quantity() {
        Long value = jdbc.queryForObject(
            "SELECT quantity FROM inventory WHERE id = 1",
            Long.class
        );
        if (value == null) {
            throw new IllegalStateException("Inventory row missing");
        }
        return value;
    }

    @Test
    void springReadOnlyMetadataDiffersFromH2JdbcState() {
        assertEquals(
            "spring=true, jdbc=false, active=true",
            reader.observe()
        );
        assertEquals(100L, quantity());
    }

    @Test
    void jdbcReadOnlyHintDoesNotPreventH2Write() {
        assertEquals(
            "spring=true, jdbc=false, active=true",
            reader.updateDespiteHint()
        );
        assertEquals(110L, quantity());
    }

    @Test
    void uncheckedExceptionStillRollsBackReadOnlyTransaction() {
        assertThrows(
            IllegalStateException.class,
            reader::updateThenFail
        );
        assertEquals(100L, quantity());
    }

    @Test
    void participatingRequiredMethodUsesOuterReadOnlyPolicy() {
        assertEquals(
            "outer=true, inner=true",
            reader.outerReadOnlyCallsRequiredWriter()
        );
        assertEquals(105L, quantity());
    }

    @Test
    void standaloneWriterStartsReadWriteTransaction() {
        assertFalse(writer.incrementRequired());
        assertEquals(105L, quantity());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Giải thích thiết kế test:**

- Test class không được gắn `@Transactional` vì transaction do test framework mở có thể làm service **tham gia transaction test thay vì bắt đầu transaction mới**, khiến phép kiểm tra read-only/commit sai.
- `@BeforeEach` reset quantity để các case độc lập. `@SpringBootTest` có thể chạy `ApplicationRunner` khi khởi tạo context; reset trước mỗi test đảm bảo fixture vẫn đúng.
- Assert kiểm tra cả **Spring flag**, **JDBC status** lẫn **dữ liệu sau transaction boundary**. Chỉ `assertTrue(isCurrentTransactionReadOnly())` không đủ để nói DB cấm ghi.
- Nếu chuyển DB/driver, test dự kiến phải điều chỉnh theo contract thực sự cần: trên database có enforcement, test nên assert thao tác ghi bị từ chối và dữ liệu không đổi, thay vì assert H2 chấp nhận.
- Không chạy các test fixture chia sẻ một H2 schema đồng thời trên nhiều thread mà không có cô lập dữ liệu, vì `@BeforeEach` của test này có thể ảnh hưởng test khác.

## 10. `readOnly` không phải một policy bảo mật

Giả sử mục tiêu là **một ứng dụng phân tích không được phép thay đổi dữ liệu production**. Chỉ cấu hình:

```java
@Transactional(readOnly = true)
public List<ReportRow> analyze() {
    // ...
}
```

là **không đủ** để bảo vệ dữ liệu, vì một câu SQL từ code, native query, migration, stored procedure hoặc endpoint khác có thể đi qua connection/transaction không bị cấm ghi.

Những biện pháp ở **đúng tầng**:

- **Database privileges:** cấp user của ứng dụng quyền chỉ đọc cần thiết, thu hồi quyền `INSERT`, `UPDATE`, `DELETE`, DDL và các quyền nguy hiểm khác theo DBMS.
- **Dedicated read-only endpoint / replica:** connection thực sự đi tới database có policy read-only khi kiến trúc cho phép.
- **DB-level read-only transactions:** dùng cơ chế SQL/session của DBMS và kiểm thử câu lệnh bị từ chối.
- **Application architecture:** tách query service và command service, không trộn operation ghi vào code đọc.
- **Observability và tests:** theo dõi SQL thực tế, test kiểm chứng DB từ chối ghi bằng user/connection được deploy.

`@Transactional(readOnly=true)` vẫn có giá trị: nó truyền ý định cho infrastructure, giúp tối ưu trong các stack hỗ trợ và đóng vai trò tài liệu thiết kế. Nhưng nó **không được dùng như rào chắn bảo mật duy nhất**.

### Read replica và routing

Một số ứng dụng có `AbstractRoutingDataSource` dựa trên thông tin `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` để chọn datasource đọc. **Đây là cấu hình bổ sung do application/team xây dựng**, không phải hành vi mặc định của `@Transactional`.

Cần đặc biệt kiểm tra **thời điểm lấy JDBC connection**: nếu connection được lấy trước khi read-only flag được đặt, hoặc routing dùng connection cache/proxy không phù hợp, hướng route có thể không như dự kiến. `LazyConnectionDataSourceProxy` và thiết kế routing hợp lý có thể giúp trong một số kiến trúc, nhưng phải test bằng connection thật.

Đọc replica cũng có đặc tính **replication lag**, nên một query ngay sau khi ghi có thể chưa nhìn thấy dữ liệu mới. `readOnly=true` không giải quyết consistency của replica.

## 11. `readOnly` không bằng `timeout`, dù cùng nhóm cấu hình transaction

Cả hai là thuộc tính trong `@Transactional`:

```java
@Transactional(readOnly = true, timeout = 5)
public Report readReport() {
    // ...
}
```

Ý nghĩa khác nhau:

| Thuộc tính | Mục đích | Có mặc định cấm `UPDATE`? |
| --- | --- | --- |
| `readOnly=true` | Mô tả transaction dự kiến chỉ đọc, có thể được tối ưu/thực thi bởi tầng phù hợp | Không phổ quát |
| `timeout=5` | Yêu cầu giới hạn thời gian transaction, phụ thuộc manager/driver/statement | Không |
| `isolation=...` | Yêu cầu mức cô lập đối với transaction mới | Không |
| `rollbackFor=...` | Quy tắc rollback khi exception đi qua interceptor | Không |

`timeout` không phải bảo đảm rằng mọi câu SQL được cắt chính xác sau 5 giây ở mọi DB. Spring có thể phối hợp timeout của transaction với JDBC statement thông qua `JdbcTemplate`, nhưng khả năng cancel query hay rollback đúng thời điểm còn tùy driver/DBMS/manager.

Mặt khác, khi `timeout` hoặc `readOnly` được khai báo trên method **chỉ tham gia một physical transaction có sẵn** với `REQUIRED`, không nên suy ra chúng tạo một timeout/mode độc lập cho đoạn inner. Đặt policy quan trọng ở **boundary sở hữu transaction**.

## 12. JPA/Hibernate: tối ưu read-only không đồng nghĩa database enforcement

Hãy so sánh hai đường:

```text
Spring JDBC:
@Transactional(readOnly=true)
  -> DataSourceTransactionManager
  -> Connection.setReadOnly(true) hint
  -> JDBC SQL/driver/DBMS
```

```text
Spring Data JPA / Hibernate:
@Transactional(readOnly=true)
  -> JpaTransactionManager / JPA dialect
  -> Hibernate Session / flush mode / persistence context optimizations
  -> JDBC connection / database
```

Những chi tiết cần hiểu:

1. **Hibernate flush mode:** với read-only transaction, Spring Data JPA có thể đặt flush mode `MANUAL` để Hibernate không cần flush/dirty-check như transaction ghi thông thường. Đây là optimization, không phải một permission check.
2. **Managed entities:** thay đổi object Java trong persistence context không nhất thiết được đồng bộ xuống DB giống một read-write transaction. Nhưng không có cơ sở để khẳng định “mọi cách gọi `save`, `flush`, native DML đều luôn bị chặn” chỉ từ flag.
3. **Spring Data JPA method configuration:** các read query có thể được đánh dấu read-only; tùy method/annotation, query update dùng `@Modifying` và transaction read-write rõ nghĩa. Service-level transaction có thể override hoặc bao phủ repository calls.
4. **Hành vi của JPA provider:** thông tin `readOnly` có thể không có cùng ý nghĩa giữa Hibernate, EclipseLink hoặc provider khác.
5. **Database-level enforcement:** nếu yêu cầu kỹ thuật là DB phải từ chối DML, cấu hình giao dịch hoặc tài khoản DB thích hợp, không chỉ trông vào việc ORM bỏ flush.

Với application chứa cả Hibernate và JDBC direct access, một transaction read-only có thể hạn chế flush ORM nhưng câu native `JdbcTemplate.update(...)` vẫn đi xuống DB. Đó là lý do cần **end-to-end test trên stack thực tế**.

## 13. Đo read-only ở đúng ranh giới

### Spring transaction metadata

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Hai biến nói về **Spring thread-bound transaction context** trong mô hình imperative. Chúng không phải phép kiểm tra SQL đã được DB cấm ghi. Cùng method với `readOnly=true` nhưng bị gọi bằng self-invocation hoặc không qua bean Spring có thể không có transaction advice, dẫn đến kết quả khác dự kiến.

### JDBC driver status

```java
Boolean driverReadOnly = jdbcTemplate.execute(
    (ConnectionCallback<Boolean>) Connection::isReadOnly
);
```

Chỉ nên dùng connection mà transaction manager đang điều phối. `JdbcTemplate` trong một transaction Spring JDBC sẽ lấy connection tham gia transaction đó. Mượn connection mới thủ công từ pool có thể chỉ đo một session khác.

### DBMS transaction state

Trên một số DBMS có thể truy vấn session/transaction setting bằng SQL đặc thù:

```sql
-- PostgreSQL: kiểm tra transaction read-only của connection hiện tại
SHOW transaction_read_only;
```

Câu trên **dành cho PostgreSQL**, không chạy trên H2. Các DBMS khác dùng syntax/metadata riêng. Cần chạy trong đúng physical transaction/connection đang điều tra; chạy SQL client khác không chứng minh transaction của application.

### Thử nghiệm ghi an toàn

Trong integration test dành riêng cho database:

1. Bắt đầu transaction `readOnly=true` qua Spring proxy.
2. Thử một `UPDATE` trên bảng test không chứa dữ liệu thật.
3. Quan sát thành công hay lỗi từ database.
4. Kết thúc transaction theo mục đích test.
5. Đọc lại dữ liệu sau boundary, từ connection độc lập khi phù hợp.
6. Kiểm tra transaction manager, driver version, DB role và cấu hình SQL read-only.

Nếu test yêu cầu **write phải bị từ chối**, thì một lần chạy H2 với cấu hình mặc định sẽ **không đáp ứng yêu cầu**, vì H2 không cưỡng chế dựa vào `setReadOnly(true)` hint.

## 14. Một số tình huống dễ làm kết quả bất ngờ

### 14.1. Self-invocation làm `readOnly` không có hiệu lực ở method mong đợi

```java
@Service
public class ReportService {
    public void outer() {
        inner();
    }

    @Transactional(readOnly = true)
    public void inner() {
        // ...
    }
}
```

Trong Spring AOP **proxy mode** thông thường, `outer()` gọi `inner()` qua `this`, không đi lại qua transaction proxy. Vì vậy `@Transactional(readOnly=true)` ở `inner()` **không tự bật một transaction/read-only hint mới**. Đưa boundary lên method được caller bên ngoài gọi qua proxy hoặc tách `inner` sang bean khác.

### 14.2. Một inner `REQUIRES_NEW` đọc trong outer đang ghi

Với `REQUIRES_NEW`, Spring mở transaction vật lý riêng cho inner; nó có thể nhận read-only hint độc lập với outer. Nhưng transaction này thường cần **connection khác** và có thể đọc thấy dữ liệu **chưa bao gồm thay đổi chưa commit của outer**, tùy isolation và DB. Không chọn `REQUIRES_NEW(readOnly=true)` chỉ để mong có query nhanh mà không đánh giá consistency và pool capacity.

### 14.3. Connection pool và trạng thái tái sử dụng

Transaction manager JDBC thường cố phục hồi trạng thái `Connection.setReadOnly(false)` sau khi kết thúc read-only transaction có hint. Pool cũng có cơ chế quản lý connection state. Tuy nhiên, SQL `SET SESSION...` thủ công hoặc các flag database session-specific có thể cần xử lý riêng; không mặc nhiên tin pool nhận diện mọi thay đổi ngoài API JDBC.

Vì vậy, đừng đổi read-only state bằng những lệnh session SQL tùy tiện trong service khi chưa hiểu reset policy. Sự rò rỉ trạng thái connection giữa các request có thể gây lỗi ghi khó tái hiện.

### 14.4. DDL, stored procedures và tác vụ ngoài DB

Ngay cả khi database transaction read-only chặn phần lớn DML, loại statement, DDL, temporary tables, function và side effects có thể có luật riêng theo DBMS. Ngoài DB, gửi HTTP request, message broker, email hoặc ghi file **không được read-only flag của JDBC ngăn cản**. Một phương thức query có side effect ngoài database vẫn phải được thiết kế cẩn thận.

### 14.5. Đọc dữ liệu không có nghĩa là transaction rẻ hoặc không cần lock

Một read-only transaction dài vẫn có thể giữ connection, snapshot, MVCC retention và một số tài nguyên/lock theo DBMS. Bật read-only không tự giải quyết long-running transaction, connection pool starvation hay truy vấn không có index. Hiệu quả phụ thuộc ORM optimization, driver và database.

## 15. Khi nào dùng `@Transactional(readOnly=true)`?

### Nên dùng

- Public service method thực hiện một đơn vị đọc dữ liệu có ranh giới rõ.
- Spring Data JPA repository/service dùng Hibernate, nơi read-only có thể giúp giảm dirty checking và flush.
- Ứng dụng có transaction routing đúng và policy của read pool/replica rõ.
- Cần biểu thị ý định read-only nhất quán và kiểm thử rằng service không sửa dữ liệu ngoài dự kiến.
- Có DB-level enforcement/permission nếu yêu cầu thực sự là **không được phép ghi**.

### Không nên dựa vào riêng cờ này khi

- Muốn một hàng rào bảo mật chống thao tác ghi ở DB.
- Có SQL write trực tiếp, native query, stored procedure, side effect ngoài DB.
- Mong method readOnly nhỏ bên trong outer read-write tự đổi physical transaction mode.
- Dùng H2 test rồi suy ra kết quả enforcement của PostgreSQL/MySQL production.
- Cần giới hạn thời gian/chặn lock/serializability — đó là các cấu hình và công cụ khác.
- Muốn tự động chuyển datasource sang read replica mà chưa có routing infrastructure.

## 16. Bảng lỗi phổ biến và cách khắc phục

| Triệu chứng / kết luận | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Có `@Transactional(readOnly=true)` mà `UPDATE` vẫn commit | Driver/DBMS coi `setReadOnly` là hint; H2 bỏ qua | Không dùng flag làm rào chắn ghi; dùng DB policy/permission |
| Spring flag true, `Connection.isReadOnly()` false | JDBC driver báo trạng thái khác Spring metadata | Kiểm tra driver docs và SQL behavior thực tế |
| `@Transactional(readOnly=true)` rồi Hibernate không lưu entity sửa đổi | Flush mode/dirty-check optimization | Chuyển nghiệp vụ ghi sang transaction read-write, dùng service boundary rõ |
| `Connection.isReadOnly()` true nhưng vẫn nghi ngờ SQL | JDBC mode và DBMS semantics khác nhau | Test DML an toàn trên DB đích và xem SQL error |
| Method trong khai báo read-write nhưng chạy trong outer read-only | Inner `REQUIRED` tham gia physical T | Đặt boundary đúng; kiểm tra propagation/validation |
| `REQUIRES_NEW(readOnly=false)` sửa được lỗi nhưng transaction ngoài rollback | Inner commit độc lập | Đánh giá lại atomicity trước khi đổi propagation |
| SQL `SET TRANSACTION READ ONLY` lỗi trên H2/DB lạ | Bật enforcement với SQL không được hỗ trợ | Không bật mù; test DBMS cụ thể |
| Repository `save` trong read-only service cho kết quả không ổn định | ORM flush/dirty-check và manager/driver khác nhau | Không trộn read/write trong một read-only boundary |
| Annotation không có tác dụng | Self-invocation, bean tạo bằng `new`, method không được advice | Gọi qua Spring proxy và test thực |
| Query method dùng readOnly nhưng vẫn tốn tài nguyên | Query chưa tối ưu, long transaction, index/lock | Tối ưu SQL và giữ transaction ngắn |
| DB replica trả dữ liệu cũ | Replication lag, routing timing | Xây dựng consistency policy |
| Cờ readOnly của JPA không giống JDBC | Manager/provider translation khác nhau | Test trên stack thật |
| Test chỉ assert Spring metadata | Metadata không chứng minh DB behavior | Kiểm tra kết quả DML và post-transaction state |
| App nghĩ readOnly đồng nghĩa timeout | Hai thuộc tính độc lập | Cấu hình timeout, query timeout riêng |
| Tài khoản DB có toàn quyền ghi | `readOnly=true` không cấp/revoke quyền | Dùng least-privilege DB credentials |

## 17. Câu hỏi tự kiểm tra

1. `@Transactional(readOnly=true)` **luôn** khiến database từ chối `UPDATE` không? **Không**. Manager/driver/DBMS quyết định mức áp dụng.
2. H2 `JdbcConnection.setReadOnly(true)` trên database writable thường làm gì? **Bỏ qua hint**, không biến database thành read-only.
3. `TransactionSynchronizationManager.isCurrentTransactionReadOnly()==true` chứng minh điều gì? **Spring transaction context đang công bố readOnly=true**, không chứng minh DB cấm DML.
4. `Connection.isReadOnly()==false` trong H2 dưới Spring `readOnly=true` có phải lỗi annotation không? **Không**, vì hai API khác vai trò và H2 chỉ báo database-level read-only.
5. Nếu `UPDATE` chạy thành công trong read-only transaction rồi method trả về bình thường thì có thể commit không? **Có**, khi DB/driver cho phép và transaction không bị rollback-only.
6. Nếu method đó ném unchecked exception qua interceptor thì sao? **Spring mặc định rollback**, dù readOnly là true.
7. Có thể dùng `DataSourceTransactionManager#setEnforceReadOnly(true)` để làm gì? **Yêu cầu mạnh hơn qua SQL read-only transaction** trên những DBMS tương thích, cần test riêng.
8. Hibernate có thể sử dụng cờ này như thế nào? **Điều chỉnh flush mode/dirty checking hoặc Session**, là optimization chứ không phải quyền cấm DML phổ quát.
9. Method `REQUIRED(readOnly=false)` tham gia outer `readOnly=true` có tự mở read-write transaction mới không? **Không**. Nó tham gia T ngoài, trừ khi propagation/manager quyết định khác.
10. Nếu chỉ cần ứng dụng đọc và tuyệt đối không được ghi DB, nên dựa vào gì? **Quyền database tối thiểu và/hoặc read-only database/transaction enforcement thực sự**.
11. `readOnly` có bằng `timeout` hay `isolation` không? **Không**, đó là các chiều transaction metadata khác nhau.
12. Vì sao kết quả H2 không đủ bảo đảm behavior của PostgreSQL production? **JDBC driver, SQL enforcement, quyền và DB semantics khác nhau**.

## 18. Checklist thiết kế và kiểm thử production

1. Xác định transaction boundary nằm ở **public Spring service method được gọi qua proxy**.
2. Chọn `readOnly=true` cho thao tác đọc đúng nghĩa; không cố ghi dữ liệu và trông vào hint để kiểm soát lỗi.
3. Xác nhận `PlatformTransactionManager`/JPA provider thực tế xử lý readOnly theo cơ chế nào.
4. Kiểm tra kết nối được cấp bởi datasource/pool, JDBC driver và DBMS, đặc biệt session state read-only.
5. Với JDBC, phân biệt **Spring thread flag** với `Connection.isReadOnly()` và chính sách SQL read-only thật.
6. Với Hibernate, kiểm tra flush mode, dirty checking và các native/modifying queries trong read-only transaction.
7. Nếu cần DB từ chối ghi, triển khai DB privileges hoặc supported read-only transaction enforcement và test trên DBMS đích.
8. Đánh giá `REQUIRED` join và outer transaction trước khi trông vào cờ của method con.
9. Không thay `REQUIRES_NEW` chỉ để vượt read-only flag khi nghiệp vụ yêu cầu atomicity chung.
10. Viết integration tests quan sát giá trị DB **sau** khi transaction commit/rollback; không chỉ kiểm tra annotation.
11. Không suy ra khả năng tự động route replica từ `readOnly=true`; kiểm tra routing timing và replica consistency.
12. Đánh giá query timeout, DB locks, MVCC retention và connection pool tách biệt với read-only optimization.
13. Khi đổi DB/driver/Hibernate/Spring, chạy lại test readOnly/DB-level enforcement; đây là đặc tính phụ thuộc môi trường.
14. Giữ nguyên tắc **least privilege** cho user database, vì một transaction hint không phải security boundary.

## Tài liệu tham khảo chính thức

- Spring Framework — `@Transactional` settings (`readOnly`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `DataSourceTransactionManager` Javadoc, `setEnforceReadOnly`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `DataSourceUtils` Javadoc, prepare/reset connection: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `TransactionDefinition` (`isReadOnly`) Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Data JPA — Transactionality, readOnly và Hibernate flush optimization: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- H2 Database — `JdbcConnection` Javadoc, `setReadOnly` bị bỏ qua: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html
- JDBC — Java SE `Connection.setReadOnly`, hint và thời điểm gọi: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- PostgreSQL — Transaction Characteristics, `READ ONLY`/`READ WRITE`: https://www.postgresql.org/docs/current/sql-set-transaction.html