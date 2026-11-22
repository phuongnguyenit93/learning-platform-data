# Điều kiện hỗ trợ của manager, driver và cơ sở dữ liệu đối với NESTED và savepoint

## 1. Học đúng bản chất trước khi bật PROPAGATION_NESTED

Trong Spring Framework, `Propagation.NESTED` cho phép một nhánh công việc được rollback **về một savepoint** bên trong **cùng transaction vật lý** do công việc bên ngoài mở. Nhờ vậy, các thay đổi trước savepoint có thể được giữ lại và outer transaction có thể tiếp tục, nếu toàn bộ hạ tầng thực sự hỗ trợ và rollback đến savepoint thành công.

Tuy nhiên, chỉ viết `@Transactional(propagation = Propagation.NESTED)` **không bảo đảm** nested transaction chạy được ở mọi hệ thống. Tính năng này phụ thuộc đồng thời vào:

1. **Spring transaction manager:** loại manager có triển khai nested transaction/savepoint phù hợp và cho phép `nestedTransactionAllowed`.
2. **JDBC driver/connection:** connection thực sự hỗ trợ API tạo, rollback tới và khi cần release savepoint.
3. **Cơ sở dữ liệu và loại thao tác:** engine có transaction/savepoint hiệu lực với các câu SQL đang chạy; không có DDL implicit commit hoặc thao tác ngoài transaction phá vỡ kỳ vọng.

Bài này trình bày cách nhận diện ba điều kiện, thực hiện kiểm tra từ metadata tới behavior thực, cấu hình Spring JDBC, ví dụ Java 17+ chạy được với H2, integration test cho manager tắt `NESTED`, cùng các giới hạn với JPA, JTA, DDL, nhiều DataSource và transaction propagation.

Sau bài, bạn có thể trả lời những câu hỏi thực tế: "Vì sao cùng annotation NESTED chạy với H2 nhưng lỗi trên DB khác?", "`supportsSavepoints() == true` đã đủ chưa?", "Vì sao inner rollback vẫn làm outer commit được?", "Vì sao có lúc NESTED hành xử giống REQUIRED?", "Tại sao bật nestedTransactionAllowed trên JpaTransactionManager vẫn nguy hiểm cho JPA state?".

## 2. NESTED dùng một physical transaction, không phải transaction độc lập

Sơ đồ một giao dịch JDBC:

```text
Connection A / physical transaction T
|
| BEGIN
| INSERT order-header (outer)
|
| SAVEPOINT S1                    <- inner NESTED bắt đầu
| INSERT optional-line (inner)
| phát sinh lỗi nghiệp vụ
| ROLLBACK TO SAVEPOINT S1        <- hủy phần sau S1
|
| INSERT audit-log (outer)
| COMMIT T                        <- commit header + audit-log
|
+--> Dữ liệu optional-line không có trong kết quả cuối
```

Trong Spring, thông thường:

- Outer `@Transactional(REQUIRED)` tạo physical transaction T trên JDBC connection.
- Inner `@Transactional(NESTED)` được gọi **qua Spring transactional proxy**, nhận biết T đang tồn tại và tạo savepoint trên **chính connection** đó.
- Nếu inner thành công, savepoint được hoàn tất/release theo khả năng của resource; chưa có commit vật lý riêng.
- Nếu inner ném exception kích hoạt rollback rule, interceptor của nested scope rollback đến savepoint. Outer có thể catch exception và tiếp tục.
- **Chỉ outermost transaction** mới commit hoặc rollback toàn bộ T. Outer rollback về sau vẫn hủy tất cả ghi bên trong T, kể cả phần inner từng "thành công".

### So sánh ba propagation thường dễ nhầm

| Propagation của inner khi outer đã mở transaction | Physical transaction | Khi inner rollback | Nếu outer rollback sau đó |
| --- | --- | --- | --- |
| `REQUIRED` | Dùng chung, không tự tạo savepoint | Thường đánh dấu transaction chung rollback-only; outer commit có thể ném `UnexpectedRollbackException` | Mọi ghi của outer/inner mất |
| `NESTED` | Dùng chung **với savepoint** khi được hỗ trợ | Rollback phần nested scope về savepoint; outer có thể tiếp tục | Mọi ghi của transaction vật lý mất |
| `REQUIRES_NEW` | Mở transaction vật lý riêng, suspend outer | Chỉ transaction mới rollback; outer tiếp tục | Inner đã commit độc lập có thể **không** bị outer rollback hủy |

`NESTED` không phải cách để "commit sớm" nhánh con. Nó là **rollback một phần trong cùng physical transaction**. Do dùng cùng connection, inner `NESTED` thường thừa hưởng isolation, timeout và các thuộc tính của transaction vật lý outer thay vì có một transaction riêng với bộ thuộc tính độc lập.

### Khi không có transaction ngoài

Một phương thức `PROPAGATION_NESTED` được gọi khi **không có physical transaction hiện hành** sẽ hoạt động tương tự `REQUIRED`: tạo transaction mới và commit/rollback toàn bộ transaction đó khi method kết thúc. Không tồn tại outer transaction để đặt savepoint bên trong. Vì thế, test "gọi thẳng nested method" không đủ để kết luận hệ thống có hỗ trợ savepoint.

## 3. Điều kiện 1 — Spring transaction manager phải hỗ trợ NESTED

### 3.1. DataSourceTransactionManager và JdbcTransactionManager

Trong trường hợp **JDBC transaction cục bộ một DataSource**, Spring `DataSourceTransactionManager` hỗ trợ `PROPAGATION_NESTED` dựa trên JDBC savepoints. Thuộc tính `nestedTransactionAllowed` của manager này mặc định là **`true`**. `JdbcTransactionManager` mở rộng `DataSourceTransactionManager` và có cơ chế tương tự, đồng thời hỗ trợ dịch exception khi commit/rollback.

Ví dụ cấu hình Java:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
    manager.setNestedTransactionAllowed(true);
    return manager;
}
```

Đây là fragment; `@Bean`, `DataSource` và tên class/import nằm trong dự án hoàn chỉnh ở phần 8. Đặt `true` minh bạch để bài thực hành dễ kiểm chứng, không có nghĩa luôn cần gọi setter bởi mặc định manager JDBC đã cho phép nested.

Cấu hình XML tương đương về ý tưởng:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
    <property name="nestedTransactionAllowed" value="true"/>
</bean>
```

`dataSource` phải được định nghĩa và được DAO/`JdbcTemplate` sử dụng đúng cách. Khi manager và DAO dùng hai DataSource không tương thích, savepoint của một connection **không thể kiểm soát** các câu lệnh đã chạy trên connection kia.

**Điều kiện bắt buộc tiếp theo:** JDBC driver và database vẫn phải thực sự hỗ trợ savepoint; `nestedTransactionAllowed=true` chỉ cho phép Spring thử tạo nested scope, **không làm xuất hiện tính năng ở backend**.

### 3.2. Tắt NESTED để kiểm tra lỗi fail-fast

Có thể chủ động tắt:

```java
manager.setNestedTransactionAllowed(false);
```

Khi inner yêu cầu `NESTED` và đang có transaction ngoài, Spring transaction manager kiểu JDBC sẽ từ chối nested scope, thông thường bằng `NestedTransactionNotSupportedException`, thay vì tự âm thầm chuyển sang `REQUIRED`.

**Đặc biệt:** nếu không có outer transaction, lời gọi `NESTED` có thể vẫn tạo transaction mới giống `REQUIRED`, nên test chỉ gọi nested method độc lập **không phát hiện** manager đã tắt nested. Hãy thử **NESTED bên trong một transaction đang mở**.

### 3.3. JpaTransactionManager không đồng nghĩa "nested JPA"

`JpaTransactionManager` có thể hỗ trợ **JDBC savepoints cho JDBC access** tham gia JPA transaction với cấu hình phù hợp, nhưng `nestedTransactionAllowed` của manager này mặc định **`false`**. Việc bật `true` **không biến JPA thành hệ thống hỗ trợ nested persistence-context transaction**.

Savepoint tác động lên trạng thái JDBC connection/database, **không tự rollback trạng thái trong JPA `EntityManager` và các entity đang được cache/quản lý**. Ví dụ sau rollback về savepoint, entity đã thay đổi trong persistence context vẫn có thể mang giá trị không khớp database. Nếu tiếp tục flush mà không xử lý trạng thái phù hợp, có thể đưa thay đổi đáng lẽ rollback quay lại DB.

Do đó:

- **Không suy luận** `@Transactional(NESTED)` trên repository/service JPA sẽ cho ngữ nghĩa rollback một phần an toàn giống JDBC.
- Nếu thật sự cần JDBC nested/savepoint trong ứng dụng JPA, phải chứng minh manager, `JpaDialect`, JDBC driver, connection và code truy cập JDBC cùng tài nguyên hỗ trợ; hiểu rõ ranh giới giữa persistence context và savepoint.
- Phương án thay thế có thể là thay đổi boundary, sử dụng transaction độc lập `REQUIRES_NEW` khi nghiệp vụ cho phép, hoặc tách thao tác JDBC với thiết kế cụ thể. Đây **không phải** thao tác bật một cờ rồi xong.

### 3.4. JTA và các manager khác

`JtaTransactionManager` làm việc với JTA/global transaction. **Không nên giả định** `PROPAGATION_NESTED` có cơ chế JDBC savepoint khả dụng trong JTA: JTA chuẩn không cung cấp cùng ngữ nghĩa savepoint JDBC cục bộ. Hãy dựa trên tài liệu transaction provider/manager và kiểm thử thật; khi không có hỗ trợ, phải xem `NESTED` là không khả dụng.

Tương tự, không suy diễn từ `PlatformTransactionManager` (một interface) rằng **mọi implementation** đều có savepoint semantics. Reactive transaction sử dụng API khác JDBC đồng bộ; phải xác minh manager/provider cụ thể thay vì áp dụng máy móc nội dung JDBC ở đây.

### 3.5. Khác biệt giữa "cho phép" và "thực hiện được"

Một cấu hình hoàn chỉnh cần **tất cả các điều kiện**:

```text
@Transactional(NESTED)
        |
        v
Có outer transaction hiện hành?
  | Không -> tạo transaction mới giống REQUIRED
  | Có
  v
Manager hỗ trợ và nestedTransactionAllowed=true?
  | Không -> không thể tạo nested scope
  | Có
  v
Connection hỗ trợ savepoint?
  | Không -> không thể tạo savepoint
  | Có
  v
DB/engine và câu SQL thực sự có ngữ nghĩa rollback-to-savepoint?
  | Không -> không thể tin kết quả rollback một phần
  | Có
  v
NESTED có thể vận hành như thiết kế
```

Nếu bất kỳ điều kiện nào không đạt, đừng mặc định dùng `REQUIRES_NEW` như một "bản thay thế tương đương"; đó là **semantics khác** (transaction vật lý độc lập).

## 4. Điều kiện 2 — JDBC driver/connection hỗ trợ savepoint thực

### 4.1. API JDBC liên quan

Các API chuẩn của JDBC:

```java
Connection connection = dataSource.getConnection();
boolean supported = connection.getMetaData().supportsSavepoints();

// Khi đã nằm trong một transaction JDBC thực sự:
Savepoint savepoint = connection.setSavepoint("after_header");
connection.rollback(savepoint);
connection.releaseSavepoint(savepoint);
```

Đây là **fragment minh họa**, không được chạy trực tiếp như một ứng dụng hoàn chỉnh. Các import thông dụng: `java.sql.Connection`, `java.sql.Savepoint` và `javax.sql.DataSource`.

Ý nghĩa:

- `DatabaseMetaData.supportsSavepoints()` là cờ khả năng mà **JDBC driver báo cáo**.
- `Connection.setSavepoint()` yêu cầu tạo savepoint trên connection hiện tại.
- `Connection.rollback(savepoint)` yêu cầu quay lại điểm đã lưu, không rollback toàn transaction.
- `Connection.releaseSavepoint(savepoint)` giải phóng savepoint khi hỗ trợ/cần thiết.

Thông thường phải ở trong một transaction JDBC với `autoCommit=false` để tạo savepoint. Gọi `setSavepoint()` trên connection đang `autoCommit=true` có thể ném `SQLException` theo JDBC contract. Trong ứng dụng Spring, `DataSourceTransactionManager` xử lý `autoCommit` và resource binding trong lúc mở transaction; **đừng tự thay autoCommit của connection đang do Spring quản lý**.

### 4.2. supportsSavepoints() cần nhưng chưa đủ

`supportsSavepoints()==true` là **tín hiệu hỗ trợ** theo metadata, chưa phải bằng chứng end-to-end. Các nguyên nhân metadata đúng nhưng ứng dụng vẫn thất bại:

- Lấy metadata từ **một DataSource/connection khác** với connection thực sự được transaction manager dùng.
- Driver khai báo hỗ trợ nhưng có hạn chế theo phiên bản/server/engine hoặc một câu SQL cụ thể.
- Transaction chưa được mở đúng; connection đang `autoCommit=true`.
- Database có thao tác implicit commit làm savepoint mất hiệu lực.
- Có SQL chạy qua connection khác, khiến savepoint không thể rollback phần đó.
- JPA persistence context hoặc các side effect ngoài database không được JDBC savepoint rollback.

Do đó nên kết hợp **hai tầng xác minh**:

1. Kiểm tra `DatabaseMetaData.supportsSavepoints()` trên DataSource thực.
2. Thực hiện **smoke test tạo savepoint -> ghi dữ liệu -> rollback(savepoint) -> commit outer -> SELECT xác minh** và integration test dùng chính Spring `@Transactional(NESTED)`.

Nếu `supportsSavepoints()==false`, đừng tuyên bố backend hỗ trợ. Nếu `true` nhưng test thực tế thất bại, hãy dựa vào kết quả runtime và phân tích lỗi ở từng tầng.

### 4.3. Các lỗi có thể gặp từ driver

JDBC có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException` khi thao tác savepoint không hợp lệ hoặc backend không hỗ trợ. Spring có thể bọc/chuyển đổi chúng thành các exception thuộc hệ transaction; loại chính xác phụ thuộc nơi lỗi xảy ra và implementation.

`NestedTransactionNotSupportedException` thường gắn với manager từ chối nested transaction; **không nên dùng một loại exception duy nhất để suy luận mọi lỗi savepoint**. Trong log, ghi lại root cause, tên driver, DB product/version, URL đã loại bỏ thông tin bí mật và transaction manager cụ thể.

## 5. Điều kiện 3 — database/engine và câu lệnh SQL phải rollback được

### 5.1. Engine phải có transaction thực

Phép rollback savepoint dựa trên khả năng của database duy trì transaction, undo log/snapshot hoặc cơ chế tương đương. Ví dụ:

- **H2** hỗ trợ transactions và lệnh `SAVEPOINT`/`ROLLBACK TO SAVEPOINT`, thích hợp làm môi trường thực hành.
- **PostgreSQL** có savepoints nhưng cần hiểu transaction semantics của từng câu lệnh và lỗi SQL.
- **MySQL** phải đặc biệt quan tâm storage engine: InnoDB hỗ trợ transaction/savepoint, còn các bảng không hỗ trợ transaction (như MyISAM) không cho rollback thay đổi theo kỳ vọng.
- Các hệ quản trị khác cũng có savepoint hoặc cơ chế tương tự, nhưng SQL dialect, giới hạn và semantics có thể khác.

Không coi mọi "SQL database" như nhau. Kiểm tra sản phẩm/version/engine và chạy test trên **chính môi trường deploy** thay vì chỉ dựa vào H2.

### 5.2. DDL và implicit commit là rủi ro lớn

Một số DB tự commit khi chạy các câu lệnh DDL hoặc quản lý DDL transaction khác DML. Ví dụ `CREATE TABLE`, `ALTER TABLE`, `TRUNCATE` tùy database có thể gây implicit commit hoặc không rollback được như INSERT/UPDATE thông thường.

Trong ví dụ Java của bài:

- Tạo bảng **trước** khi mở transaction nghiệp vụ.
- Test NESTED chủ yếu bằng **DML** (`INSERT`), một thao tác rollback được trong H2.
- Không đặt các migration schema hoặc câu DDL không xác định bên trong nested scope.
- Với DB thật, xác minh hành vi DDL/trigger/procedure riêng bằng tài liệu và test thực tế.

### 5.3. Không được "rollback" connection khác

Savepoint thuộc **một connection và transaction**. Nếu outer ghi trên connection A nhưng inner tự mở `DriverManager.getConnection(...)` trên connection B rồi auto-commit, rollback savepoint trên A **không thể** hủy ghi đã commit trên B.

Trong Spring JDBC, `JdbcTemplate` dùng `DataSourceUtils` để nhận connection gắn với transaction của thread. Dùng cùng `DataSource` cho transaction manager và DAO. Với connection pool, đối tượng `Connection` có thể là wrapper/proxy, nhưng phải cùng transaction-bound resource.

### 5.4. Giới hạn thực tiễn khác

- Transaction dài và các savepoint có thể giữ khóa/tài nguyên. Rollback về savepoint **không đồng nghĩa** mọi lock đã được nhả tức thì trên mọi database.
- Database có thể giới hạn số lượng savepoint hoặc độ sâu nested; nhiều nested scope lồng nhau có thể ảnh hưởng bộ nhớ và latency.
- Database constraints, stored procedures, trigger và trạng thái transaction sau lỗi SQL có thể khác nhau. Có lỗi làm cả transaction unusable; rollback về savepoint có thể không cứu được một transaction đã bị backend abort theo quy tắc riêng.
- File, HTTP request, email, Kafka message và cache ngoài DB không tự rollback cùng JDBC savepoint.
- Các lệnh ghi vào nhiều database/cùng dữ liệu qua replica không được một savepoint JDBC quản lý thống nhất.

**Kết luận:** Có support metadata và annotation đúng vẫn chưa đủ. Hãy kiểm tra **kết quả sau khi outer transaction commit** để biết các hàng trước/sau savepoint còn và hàng thuộc nhánh rollback đã mất.

## 6. Bảng quyết định: manager × driver × database

| Manager | Driver | Database/engine | Kỳ vọng với outer transaction + NESTED |
| --- | --- | --- | --- |
| `DataSourceTransactionManager`, nested allowed | JDBC savepoints hỗ trợ | Transactional DML hỗ trợ savepoint | **Có thể** rollback về savepoint; cần integration test |
| `JdbcTransactionManager`, nested allowed | JDBC savepoints hỗ trợ | Transactional DML hỗ trợ savepoint | Tương tự, có thêm exception translation |
| `DataSourceTransactionManager`, nested **disabled** | Có | Có | Manager từ chối nested scope |
| `DataSourceTransactionManager`, nested allowed | Không hỗ trợ savepoint | Bất kỳ | Không thể tạo nested savepoint |
| `DataSourceTransactionManager`, nested allowed | Có | Nontransactional engine / implicit commit | Không đảm bảo rollback một phần |
| `JpaTransactionManager` mặc định | Có | Có | Nested disabled mặc định; **không suy ra nested JPA** |
| `JpaTransactionManager` bật nested | Có | Có | Chỉ có thể hữu ích cho JDBC access được tích hợp; JPA persistence context **không rollback theo savepoint** |
| `JtaTransactionManager` / provider không hỗ trợ nested | Có | Có | Không có ngữ nghĩa JDBC nested chuẩn để mặc định dựa vào |
| Bất kỳ manager, nhưng **không có outer transaction** | Phù hợp | Phù hợp | `NESTED` xử lý giống transaction mới (`REQUIRED`), **không** phải partial savepoint |

Mỗi ô "có thể" nghĩa là **điều kiện cần** đã có chứ không thay thế kiểm chứng thực tế.

## 7. Cách kiểm tra đúng theo từng tầng

Dùng một checklist theo thứ tự, để khi thất bại biết đang gặp vấn đề ở tầng nào.

### Tầng Spring / bean

1. Lấy đúng Spring-managed `PlatformTransactionManager`; kiểm tra class thực tế bằng log/inspection.
2. Nếu dùng `DataSourceTransactionManager`, xác nhận `isNestedTransactionAllowed()` là `true`, hoặc cố ý tắt để kiểm thử negative case.
3. Xác nhận bean service `@Transactional(NESTED)` được gọi **qua Spring proxy**, không phải `this.inner()`.
4. Xác nhận lúc gọi nested đã có outer transaction vật lý; nếu không, `NESTED` tạo transaction mới và không chứng minh savepoint support.

### Tầng JDBC connection

5. Dùng **cùng DataSource** với manager để đọc `connection.getMetaData().supportsSavepoints()`.
6. Kiểm tra driver name/version cùng database product/version khi cần: `getDriverName()`, `getDriverVersion()`, `getDatabaseProductName()`, `getDatabaseProductVersion()`.
7. Chạy một smoke test JDBC với `setAutoCommit(false)`, `setSavepoint`, `rollback(savepoint)`, `commit` (trên connection mới dành riêng test, **không** thay autoCommit của connection đang do Spring quản lý).
8. Không chỉ nhìn metadata; thử thật những SQL và schema có liên quan.

### Tầng Spring end-to-end

9. Outer ghi một hàng A; inner `NESTED` ghi B rồi ném unchecked exception.
10. Catch exception ở outer, ghi thêm C, để outer commit.
11. SELECT sau khi outer proxy trả về; kết quả phải là **A và C**, không có B.
12. Thử tiếp inner thành công rồi outer rollback: tất cả hàng của cùng physical transaction phải biến mất.
13. Thử gọi nested trực tiếp không có outer: nó sẽ mở transaction mới; ném lỗi thì rollback toàn bộ công việc trong method đó.

## 8. Ví dụ Java 17+ chạy được với Spring Boot, H2 và NESTED

Dự án Spring Boot sau có chủ đích:

- Tạo `DataSourceTransactionManager` rõ ràng với `nestedTransactionAllowed=true`.
- Dùng một `JdbcTemplate` trỏ tới **cùng DataSource**.
- Phân tách outer và inner thành **hai bean** để Spring AOP áp dụng `NESTED`.
- Chạy success, partial rollback, outer rollback và nested khi không có outer.
- Kiểm tra metadata `supportsSavepoints()`.
- Viết integration test chứng minh kết quả thật và thử manager **tắt** nested.

**Môi trường:** JDK 17+, Maven, Spring Boot **3.5.6**, H2 in-memory. H2 không đại diện mọi engine production, nhưng phù hợp để chứng minh cơ chế JDBC savepoint.

### 8.1. Cấu trúc thư mục

```text
nested-support-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── NestedSupportApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── OuterWorkService.java
    │   │   └── InnerNestedService.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── NestedSupportIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>nested-support-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:nested_support;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

H2 in-memory **có tên** `nested_support` cho các connection trong cùng JVM dùng cùng database. `DB_CLOSE_DELAY=-1` giữ database tồn tại dù connection pool đóng/mở connection trong quá trình demo. Dữ liệu sẽ mất khi JVM thực sự kết thúc.

### 8.4. TransactionConfig.java — khai báo manager

**`src/main/java/demo/TransactionConfig.java`**

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
public class TransactionConfig {

    @Bean
    public DataSourceTransactionManager transactionManager(
            DataSource dataSource) {
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
```

Khai báo transaction manager chính tên `transactionManager` đảm bảo service `@Transactional` dùng manager này trong demo. Spring Boot tự cấu hình H2 `DataSource` và `JdbcTemplate`. Với Spring Boot có bean `PlatformTransactionManager` tự tạo, không cần khai báo bổ sung manager nếu không muốn tùy chỉnh, nhưng ở đây khai báo tường minh để kiểm tra **đúng loại manager và flag**.

### 8.5. InnerNestedService.java — nested scope thực sự

**`src/main/java/demo/InnerNestedService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerNestedService {
    private final JdbcTemplate jdbc;

    public InnerNestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void accepted(long id) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, "nested-accepted");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void rejected(long id) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, "nested-rejected");

        throw new IllegalStateException("inner rejected");
    }
}
```

Khi outer transaction đang có, interceptor của `accepted`/`rejected` tạo một **savepoint** trên connection đang tham gia transaction. `rejected` ném `IllegalStateException`, vì unchecked exception mặc định khiến nested scope rollback đến savepoint trước khi exception tới outer. `accepted` hoàn tất nested scope bình thường; dữ liệu vẫn chưa commit vật lý cho đến khi outer commit.

Nếu gọi `rejected` **mà không có outer transaction**, `NESTED` hoạt động như `REQUIRED`: tự mở transaction mới, ném lỗi thì rollback toàn bộ transaction mới đó.

### 8.6. OuterWorkService.java — kiểm chứng rollback một phần

**`src/main/java/demo/OuterWorkService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterWorkService {
    private final JdbcTemplate jdbc;
    private final InnerNestedService inner;

    public OuterWorkService(JdbcTemplate jdbc, InnerNestedService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void partialRollback(long beforeId, long nestedId, long afterId) {
        insert(beforeId, "outer-before");

        try {
            inner.rejected(nestedId);
        } catch (IllegalStateException expected) {
            System.out.println("outer handled nested error");
        }

        insert(afterId, "outer-after");
    }

    @Transactional
    public void allSuccess(long beforeId, long nestedId, long afterId) {
        insert(beforeId, "outer-before");
        inner.accepted(nestedId);
        insert(afterId, "outer-after");
    }

    @Transactional
    public void outerFailure(long beforeId, long nestedId) {
        insert(beforeId, "outer-before");
        inner.accepted(nestedId);
        throw new IllegalStateException("outer rejected");
    }

    private void insert(long id, String note) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, note);
    }
}
```

`OuterWorkService` và `InnerNestedService` là **hai Spring beans** khác nhau. Lời gọi `inner.rejected(...)` đi qua Spring proxy của bean inner, nên transaction interceptor có cơ hội tạo savepoint rồi rollback về savepoint. Nếu dồn mọi thứ vào một bean và gọi `this.rejected(...)`, proxy mode có thể bỏ qua transactional advice cho method inner; kết quả sẽ khác.

### 8.7. NestedSupportApplication.java — probe driver và đối chiếu sau commit

**`src/main/java/demo/NestedSupportApplication.java`**

```java
package demo;

import java.sql.Connection;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class NestedSupportApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedSupportApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            DataSource dataSource,
            JdbcTemplate jdbc,
            OuterWorkService outer,
            InnerNestedService inner) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE IF NOT EXISTS nested_event (
                        id BIGINT PRIMARY KEY,
                        note VARCHAR(80) NOT NULL
                    )
                    """);

            // Chỉ báo khả năng của driver, chưa thay thế integration test.
            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                        "driver savepoints: "
                                + connection.getMetaData().supportsSavepoints());
            }

            outer.partialRollback(1L, 2L, 3L);
            System.out.println("partial rows: " + ids(jdbc, 1L, 3L));

            outer.allSuccess(11L, 12L, 13L);
            System.out.println("success rows: " + ids(jdbc, 11L, 13L));

            try {
                outer.outerFailure(21L, 22L);
            } catch (IllegalStateException ex) {
                System.out.println("outer error: " + ex.getMessage());
            }
            System.out.println("outer rollback rows: " + ids(jdbc, 21L, 22L));

            try {
                inner.rejected(31L);
            } catch (IllegalStateException ex) {
                System.out.println("standalone error: " + ex.getMessage());
            }
            System.out.println("standalone rows: " + ids(jdbc, 31L, 31L));
        };
    }

    private static List<Long> ids(
            JdbcTemplate jdbc, long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM nested_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

**Vì sao thiết kế đối chiếu đúng?**

1. `CommandLineRunner` không được đánh dấu `@Transactional`: mỗi lời gọi outer service có boundary transaction thật, không bị runner giữ transaction ngoài.
2. Bảng được tạo **trước khi** gọi transaction nghiệp vụ, tránh ảnh hưởng DDL implicit commit đến phép thử.
3. Truy vấn `ids(...)` được gọi **sau khi outer proxy đã commit/rollback**, không dựa vào khả năng "read your own writes" trong transaction chưa commit.
4. Các case dùng ID riêng, tránh nhầm bản ghi do case khác tạo.
5. `inner.rejected(31L)` được gọi không có outer transaction và bị rollback toàn bộ, kiểm tra semantics `NESTED` khi không có parent.

### 8.8. Chạy, stdout và ý nghĩa

Trong thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Các dòng do **chính chương trình** in (không tính log Spring/Maven):

```text
driver savepoints: true
outer handled nested error
partial rows: [1, 3]
success rows: [11, 12, 13]
outer error: outer rejected
outer rollback rows: []
standalone error: inner rejected
standalone rows: []
```

Giải thích:

| Luồng | Điều kiện | Kết quả DB sau boundary |
| --- | --- | --- |
| `partialRollback(1,2,3)` | Outer T đang mở; inner `NESTED` ghi 2 rồi lỗi; rollback về savepoint | Chỉ có **1, 3** |
| `allSuccess(11,12,13)` | Inner và outer hoàn tất, không lỗi | Có **11, 12, 13** |
| `outerFailure(21,22)` | Inner hoàn tất nested, nhưng outer ném lỗi | **Không có 21 hoặc 22** |
| `inner.rejected(31)` gọi độc lập | Không có outer T; NESTED mở transaction mới, ném lỗi | **Không có 31** |

Kết quả `partial rows: [1, 3]` là bằng chứng quan trọng nhất rằng **Spring NESTED đã rollback một phần thành công trên actual JDBC connection**, thay vì chỉ dựa vào metadata. Nếu dùng `REQUIRED` cho inner, lỗi của inner participant thường đánh dấu shared transaction rollback-only và outer commit có thể gặp `UnexpectedRollbackException`.

## 9. Integration test: chứng minh manager, driver và DB cùng hoạt động

Thêm file **`src/test/java/demo/NestedSupportIntegrationTest.java`**:

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.NestedTransactionNotSupportedException;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class NestedSupportIntegrationTest {
    @Autowired
    private DataSource dataSource;

    @Autowired
    private DataSourceTransactionManager transactionManager;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private OuterWorkService outer;

    @Autowired
    private InnerNestedService inner;

    @Test
    void managerAndDriverAdvertiseSupport() throws SQLException {
        assertTrue(transactionManager.isNestedTransactionAllowed());

        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.getMetaData().supportsSavepoints());
        }
    }

    @Test
    void nestedRollbackPreservesOnlyOuterWrites() {
        outer.partialRollback(1001L, 1002L, 1003L);
        assertEquals(List.of(1001L, 1003L),
                ids(1001L, 1003L));
    }

    @Test
    void successfulNestedScopeStillDependsOnOuterCommit() {
        outer.allSuccess(1011L, 1012L, 1013L);
        assertEquals(List.of(1011L, 1012L, 1013L),
                ids(1011L, 1013L));

        assertThrows(IllegalStateException.class,
                () -> outer.outerFailure(1021L, 1022L));
        assertEquals(List.of(), ids(1021L, 1022L));
    }

    @Test
    void nestedWithoutOuterBehavesLikeNewTransaction() {
        assertThrows(IllegalStateException.class,
                () -> inner.rejected(1031L));
        assertEquals(List.of(), ids(1031L, 1031L));
    }

    @Test
    void managerWithNestedDisabledRejectsNestedInsideOuter() {
        DataSourceTransactionManager disabledManager =
                new DataSourceTransactionManager(dataSource);
        disabledManager.setNestedTransactionAllowed(false);

        TransactionTemplate outerTemplate =
                new TransactionTemplate(disabledManager);
        TransactionTemplate nestedTemplate =
                new TransactionTemplate(disabledManager);
        nestedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_NESTED);

        assertThrows(NestedTransactionNotSupportedException.class,
                () -> outerTemplate.executeWithoutResult(
                        outerStatus ->
                                nestedTemplate.executeWithoutResult(
                                        nestedStatus -> {
                                            // Chỉ kiểm tra khả năng tạo nested scope.
                                        })));
    }

    private List<Long> ids(long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM nested_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** 5 test pass trong H2 và cấu hình này. `@SpringBootTest` khởi động application context, chạy `CommandLineRunner` tạo bảng và sử dụng các ID 1–31; test sử dụng ID 1001–1031 để không trùng. Test không có `@Transactional` ở class/method, nên không vô tình tạo outer test transaction.

### 9.1. Test âm tính có ý nghĩa gì?

`managerWithNestedDisabledRejectsNestedInsideOuter` tạo một `DataSourceTransactionManager` riêng **chỉ dùng trong test này**, cấu hình `nestedTransactionAllowed=false`. `outerTemplate` mở physical transaction và `nestedTemplate` cố tạo nested scope bên trong nó. Manager từ chối, test kỳ vọng `NestedTransactionNotSupportedException`.

Đây là test cho **lớp manager**, không phải lời khẳng định H2/driver thiếu savepoint. Cùng H2 và cùng DataSource vẫn hỗ trợ savepoints trong test khác.

### 9.2. Test metadata và test behavior khác nhau

- `managerAndDriverAdvertiseSupport` xác nhận **flag manager** và **metadata JDBC**.
- `nestedRollbackPreservesOnlyOuterWrites` xác nhận **hành vi thực** qua Spring proxy + savepoint + SQL + commit.
- `successfulNestedScopeStillDependsOnOuterCommit` xác nhận savepoint không có commit độc lập.
- `nestedWithoutOuterBehavesLikeNewTransaction` cho thấy test thiếu outer transaction **không chứng minh** savepoint được tạo.

Chỉ nên tuyên bố môi trường hỗ trợ thật khi các test hành vi trên **database thực tế** đã pass. Nếu CI dùng H2 còn production dùng PostgreSQL/MySQL/Oracle/SQL Server, hãy có integration test riêng chạy trên DB production tương ứng (ví dụ dùng Testcontainers) và đúng driver/engine.

## 10. Smoke test thuần JDBC để phân lập vấn đề driver/database

Khi `@Transactional(NESTED)` thất bại, hãy tách Spring khỏi phép thử bằng một connection JDBC riêng. Đây là **phương pháp chẩn đoán**, không phải cách thao tác trực tiếp với Spring-managed connection trong production.

Ví dụ **fragment minh họa** dùng bảng `nested_event` đã được tạo:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean initialAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)")) {
            ps.setLong(1, 8001L);
            ps.setString(2, "outer-jdbc");
            ps.executeUpdate();

            Savepoint point = connection.setSavepoint("before_optional");

            ps.setLong(1, 8002L);
            ps.setString(2, "nested-jdbc");
            ps.executeUpdate();

            connection.rollback(point);
            connection.commit();
        }
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.setAutoCommit(initialAutoCommit);
    }
}
```

Cần import `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.Savepoint`, `java.sql.SQLException`; có sẵn `DataSource`. Fragment chưa khai báo bao quanh class/method. Nó tạo **connection riêng cho test** và tự quản lý transaction; **không sử dụng trong một Spring-managed transaction đang mở**.

Sau khi chạy thành công, SELECT sau commit sẽ thấy id=8001 nhưng **không thấy** id=8002. Nếu test thuần JDBC fail, vấn đề có thể nằm tại **driver, database, engine, SQL hoặc transaction mode**, không nhất thiết ở Spring AOP. Nếu JDBC test pass nhưng Spring NESTED fail, quay lại kiểm tra manager, DataSource sharing, cấu hình proxy và outer transaction.

### Tránh biến smoke test thành lỗi dữ liệu

Dùng DB thử nghiệm có thể reset, ID riêng, và không chạy đoạn này song song với các test khác dùng chung ID. Trong ứng dụng thật, đừng tự gọi `setAutoCommit(false)`/`commit()` trên connection đã được Spring transaction manager bind, vì sẽ phá lifecycle transaction.

## 11. Tình huống lỗi phổ biến và hướng xử lý

### 11.1. NestedTransactionNotSupportedException ngay lúc vào inner

Đầu tiên xác định manager nào thực sự chạy. `nestedTransactionAllowed=false` có thể là nguyên nhân, hoặc manager/backend chưa hỗ trợ savepoint. Đừng chỉ nhìn annotation. Kiểm tra bean manager, flag, outer transaction và root cause.

### 11.2. Annotation NESTED nhưng thực tế không có savepoint

Kiểm tra inner có được gọi **qua Spring proxy** không, hay `this.inner()` trong cùng bean. Kiểm tra có outer transaction đang hoạt động không: nếu không có outer, NESTED khởi tạo transaction mới như REQUIRED. Hai trường hợp này tạo kết quả "không thấy savepoint" vì **không có điều kiện cần** để tạo nested scope.

### 11.3. Driver báo supportsSavepoints true nhưng rollback thất bại

Chạy raw JDBC smoke test với `autoCommit=false`, cùng DB/engine và cùng schema. Kiểm tra DDL implicit commit, SQL đã làm transaction aborted, savepoint mất hiệu lực hoặc exception từ driver. Đừng suy ra "metadata false" khi thực tế driver nói true nhưng transaction state không phù hợp.

### 11.4. Inner NESTED rollback nhưng outer cũng rollback

Kiểm tra exception có được outer **bắt sau khi nested interceptor rollback tới savepoint** hay còn thoát qua outer interceptor và kích hoạt rollback toàn transaction. Đồng thời kiểm tra inner có thực sự `NESTED`; nếu nó `REQUIRED` thì lỗi participant có thể làm shared transaction rollback-only.

### 11.5. Inner NESTED đã return, nhưng outer rollback làm mất tất cả

Đây là behavior **đúng**: nested scope không commit độc lập. Chỉ outermost transaction có thể commit physical transaction. Nếu nghiệp vụ thật sự yêu cầu ghi audit riêng vẫn tồn tại sau outer rollback, cần cân nhắc `REQUIRES_NEW` hoặc outbox/thiết kế khác, không dùng NESTED để hy vọng commit riêng.

### 11.6. SQL chạy trên connection khác

Inner code tự lấy JDBC connection khác hoặc gọi API bên ngoài database. Savepoint của connection outer không quản lý hoạt động đó. Đảm bảo JDBC work dùng `JdbcTemplate` cùng `DataSource`, hoặc công khai tách transaction khi cần.

### 11.7. Cố dùng nested JPA như nested JDBC

`EntityManager` lưu state trong first-level cache/persistence context. Rollback JDBC savepoint không tự reset state JPA. Bật nested flag trên `JpaTransactionManager` không giải quyết tất cả. Ưu tiên tránh coi JPA nested transaction là tương đương với savepoint JDBC.

### 11.8. DDL hoặc nontransactional storage engine

Một số DDL gây implicit commit; một số engine không rollback DML. Cấu hình Spring đúng vẫn không sửa được giới hạn backend. Test behavior thực trên DB/engine production và tách schema migration khỏi transaction nghiệp vụ.

### 11.9. Test chỉ dùng H2 và kết luận production cũng hỗ trợ

H2 là công cụ học và kiểm chứng cơ chế, không bảo đảm tương thích 100% với mọi DB. Cần kiểm thử driver version, DB version, SQL dialect và transaction engine thật. Với các câu SQL quan trọng, chạy integration test trên backend mục tiêu.

### 11.10. Test method tự có @Transactional

Spring TestContext có thể tạo transaction ngoài khi test được gắn `@Transactional`, khiến service `NESTED` tạo savepoint trong **test-managed transaction** thay vì physical transaction do application service mở. Trạng thái commit và nơi rollback sẽ khác; test mặc định rollback ở cuối. Để kiểm chứng boundary của service, viết test **không có `@Transactional` ở test**.

### 11.11. Nhiều manager không có transaction chung

Nếu outer dùng `transactionManagerA` còn inner dùng `transactionManagerB`, bạn không có bằng chứng cả hai cùng một physical transaction. `NESTED` không vượt qua nhiều database/resource bằng cách đặt savepoint trên một connection. Chọn manager và DataSource có chủ đích, xác minh actual resource binding.

### 11.12. Hiểu nhầm savepoint release với commit

`releaseSavepoint` chỉ bỏ một điểm đánh dấu; không commit dữ liệu. NESTED success không tự phát sinh một durable commit. Nếu outer rollback, các thay đổi vẫn bị hủy.

## 12. Checklist trước khi dùng NESTED trong dự án thật

- [ ] Manager là implementation có hỗ trợ nested/savepoints phù hợp; không chỉ dựa vào `PlatformTransactionManager`.
- [ ] `nestedTransactionAllowed=true` khi cần và đúng bean manager thực tế được proxy sử dụng.
- [ ] Outer đã mở **physical transaction**; inner được gọi **qua Spring proxy**.
- [ ] Manager và mọi JDBC DAO dùng cùng transaction-bound `DataSource`.
- [ ] JDBC metadata `supportsSavepoints()` trả true trên connection mục tiêu.
- [ ] Raw JDBC smoke test tạo/rollback savepoint thành công với SQL và DB/engine tương ứng.
- [ ] Integration test Spring NESTED rollback phần inner, giữ phần outer sau outer commit.
- [ ] Test outer rollback hủy cả các thay đổi nested success.
- [ ] Test dùng đúng database/driver/engine production, không chỉ H2.
- [ ] Không dùng NESTED để mong "commit riêng" hoặc rollback JPA persistence context.
- [ ] Đã xét DDL implicit commit, nontransactional engine, side effects ngoài database và transaction dài.
- [ ] Có chiến lược thay thế rõ ràng nếu backend không hỗ trợ: đổi transaction boundary/thiết kế workflow thay vì silent fallback.

## 13. Bài tập và câu hỏi tự kiểm tra

**Bài 1:** Manager là `DataSourceTransactionManager` với `nestedTransactionAllowed=true`, JDBC driver hỗ trợ savepoints, nhưng bảng dùng engine không có transaction. Spring annotation có đảm bảo rollback dữ liệu inner không?

**Đáp án:** Không. Database/engine phải thực sự rollback được DML; manager và driver đúng vẫn không thể biến thao tác không transactional thành atomic.

**Bài 2:** `supportsSavepoints()` trả true. Có thể bỏ qua integration test không?

**Đáp án:** Không. Cờ metadata chỉ phản ánh khả năng được driver báo cáo. Phải thử actual `setSavepoint`/`rollback(savepoint)` và `@Transactional(NESTED)` trên DB/SQL/engine mục tiêu.

**Bài 3:** Gọi `inner.rejected(31)` từ caller không có transaction ngoài. Có tạo nested savepoint không?

**Đáp án:** Không có outer transaction để lưu savepoint bên trong; `NESTED` xử lý như transaction mới `REQUIRED` và rollback toàn transaction của method khi ném exception.

**Bài 4:** Outer ghi A, inner `NESTED` ghi B rồi lỗi, outer catch và ghi C, outer commit. Backend hỗ trợ savepoint đúng. Bản ghi nào còn?

**Đáp án:** A và C còn; B bị rollback về savepoint.

**Bài 5:** Inner `NESTED` thành công, sau đó outer rollback. Inner có giữ được dữ liệu vì "đã hoàn tất" không?

**Đáp án:** Không. Inner vẫn nằm trong cùng physical transaction. Outer rollback hủy tất cả.

**Bài 6:** Vì sao bật `nestedTransactionAllowed=true` trên `JpaTransactionManager` chưa chứng minh có nested JPA semantics?

**Đáp án:** Savepoint ảnh hưởng JDBC connection/database, không tự rollback entity state trong JPA persistence context. Cần rất thận trọng nếu JDBC/JPA dùng chung transaction.

**Bài 7:** Manager flag false nhưng gọi `@Transactional(NESTED)` trực tiếp không có outer transaction và method vẫn chạy. Có mâu thuẫn không?

**Đáp án:** Không. Không có outer transaction thì nested có thể hoạt động giống REQUIRED. Muốn kiểm tra flag, phải gọi NESTED trong một outer transaction đang hoạt động.

**Bài 8:** Vì sao không nên tự gọi `connection.rollback(savepoint)` trên Spring-managed connection khi service đang chạy?

**Đáp án:** Điều đó bỏ qua transaction manager và có thể phá quản lý resource/lifecycle của Spring. Dùng `@Transactional(NESTED)` hoặc API transaction status/savepoint thích hợp trong một thiết kế được kiểm soát.

**Bài 9:** Bạn cần inner commit độc lập để dữ liệu vẫn còn sau outer rollback. NESTED phù hợp chứ?

**Đáp án:** Không. Cần xem `REQUIRES_NEW` hoặc một cơ chế lưu trữ/đối soát riêng phù hợp, đồng thời xem xét nhất quán nghiệp vụ và tài nguyên connection pool.

**Bài 10:** Trên production, JDBC metadata báo true nhưng chạy một DDL trong nested scope làm savepoint biến mất. Trọng tâm chẩn đoán là tầng nào?

**Đáp án:** Database/SQL semantics, đặc biệt implicit commit và loại DDL. Đừng quy hết lỗi về `@Transactional` hoặc driver metadata.

## 14. Tài liệu tham khảo

- Spring Framework — Transaction propagation và `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — JDBC connections, `DataSourceTransactionManager` và savepoints: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceTransactionManager` Javadoc, `nestedTransactionAllowed` mặc định true: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JpaTransactionManager` Javadoc, nested JDBC-only và flag mặc định false: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- Spring Framework — `NestedTransactionNotSupportedException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/NestedTransactionNotSupportedException.html
- JDBC API — `DatabaseMetaData.supportsSavepoints()`, `Connection.setSavepoint()`, `Connection.rollback(Savepoint)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html
- H2 Database — hỗ trợ transaction: https://h2database.com/html/features.html
- H2 Database — câu lệnh `SAVEPOINT` và `ROLLBACK TO SAVEPOINT`: https://h2database.com/html/commands.html

**Tóm lại:** `PROPAGATION_NESTED` hoạt động dựa trên **savepoint trong một physical transaction**, không phải một transaction độc lập. Chỉ dùng khi **manager cho phép**, **driver/connection hỗ trợ**, và **database/engine/SQL có rollback-to-savepoint thực sự**. Hãy kiểm tra cả metadata lẫn behavior bằng transaction ngoài + nested rollback + SELECT sau commit. Nếu tầng nào thiếu hỗ trợ, cần thiết kế giải pháp thay thế rõ ràng thay vì giả định annotation sẽ tự xử lý.