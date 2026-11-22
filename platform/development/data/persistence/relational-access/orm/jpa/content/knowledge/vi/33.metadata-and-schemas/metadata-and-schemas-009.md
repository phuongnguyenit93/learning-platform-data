# Phân biệt sinh lược đồ phục vụ thử nghiệm và di trú lược đồ có kiểm soát

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Siêu dữ liệu và lược đồ  
> **Bài học:** Phân biệt sinh lược đồ phục vụ thử nghiệm và di trú lược đồ có kiểm soát

Khi xây dựng ứng dụng Jakarta Persistence (JPA), ta thường khai báo `@Entity`, `@Table`, `@Column`, `@Id`, `@ManyToOne`, `@JoinColumn`, `@Index` rồi để JPA provider, chẳng hạn Hibernate ORM, tạo bảng và khóa ngoại cho một database rỗng. Cách này rất hữu ích khi viết demo hoặc automated tests: chỉ cần khởi động persistence unit là có thể có schema phù hợp để bắt đầu kiểm tra ánh xạ.

Nhưng hệ thống production lại có một yêu cầu khác: **database đã chứa dữ liệu thật, các phiên bản ứng dụng có thể cùng chạy trong một giai đoạn triển khai và mọi thay đổi cấu trúc phải có lịch sử, quyền kiểm soát, kế hoạch kiểm chứng lẫn phục hồi**. Việc để ORM tự “đồng bộ schema” không thay thế được quy trình di trú (*database migration*) có kiểm soát.

Hai nhu cầu phải được phân biệt:

- **Sinh lược đồ phục vụ thử nghiệm** (*schema generation for tests*): tạo mới hoặc xóa/tạo lại schema, thường từ metadata JPA, trong môi trường tạm thời. Tối ưu cho tốc độ phát triển, test isolation và khả năng khởi tạo từ trạng thái sạch.
- **Di trú lược đồ có kiểm soát** (*controlled schema migration*): biến đổi schema **từ phiên bản đã triển khai sang phiên bản mới**, bằng các bước có định danh/phiên bản, được review, chạy đúng thứ tự, bảo toàn dữ liệu, có thể tái lập và quan sát được. Thường dùng Flyway hoặc Liquibase.
- **Schema validation**: kiểm tra mapping hiện tại có phù hợp với schema đang tồn tại ở một mức độ nhất định, mà **không tự sửa schema**. Đây là một lớp bảo vệ hữu ích khi kết hợp migrations, không phải bằng chứng tuyệt đối rằng mọi index/constraint/data invariant đều chính xác.

Quy tắc quan trọng nhất của bài:

> **Tạo schema mới từ model hiện tại không giống với nâng cấp một schema cũ chứa dữ liệu lên model hiện tại.**

Ví dụ, Hibernate có thể tạo bảng `customers` mới chứa cột `status NOT NULL`. Nhưng nếu production đã có một triệu Customer records không có cột `status`, migration phải trả lời thêm: thêm cột thế nào, giá trị cũ được backfill ra sao, API cũ có còn ghi được không, lệnh có khóa bảng không, phải rollback/roll-forward thế nào và cách chứng minh dữ liệu không mất.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa **metadata JPA**, **DDL/schema generation**, **schema validation** và **versioned database migration**.
2. Nhận biết những tác vụ phù hợp với `create`, `create-drop`, `update`, `validate` và `none` của Hibernate.
3. Hiểu các cấu hình chuẩn JPA như `jakarta.persistence.schema-generation.database.action` và `jakarta.persistence.schema-generation.scripts.action`.
4. Phân biệt thuộc tính **Jakarta Persistence portable** với thuộc tính **Hibernate-specific** và cấu hình Spring Boot.
5. Giải thích vì sao `hbm2ddl.auto=update` không phải migration engine an toàn cho production.
6. Thiết kế một database test được tạo lại từ đầu để kiểm tra entity mappings.
7. Thiết kế integration test **chạy migrations thực tế** trên database tương thích production.
8. Hiểu vai trò Flyway/Liquibase, migration version, ordering, history table, checksum và lock phối hợp chạy migration.
9. Viết các migrations SQL cho tiến hóa schema `customers` theo các bước **expand → backfill → contract**.
10. Thiết kế thay đổi tương thích giữa nhiều phiên bản ứng dụng trong rolling deployment.
11. Phân biệt tạo bảng mới với thay đổi bảng cũ có dữ liệu.
12. Biết cách thêm cột, đổi tên, xóa cột, thay kiểu dữ liệu, thêm unique/FK/NOT NULL với ít rủi ro hơn.
13. Biết tại sao cần backfill dữ liệu có kiểm soát trước khi áp constraint.
14. Hiểu ảnh hưởng database locks, transaction semantics và cú pháp DDL đặc thù từng DBMS.
15. Phân biệt schema drift và migration history integrity.
16. Chọn chiến lược rollback, restore, forward-fix và backup phù hợp với kiểu thay đổi.
17. Đưa migrations vào CI/CD có bước kiểm tra trên môi trường test/staging.
18. Tách quyền runtime application khỏi quyền DDL của migration runner.
19. Tránh giả định H2 luôn mô phỏng chính xác PostgreSQL, MySQL, Oracle hoặc SQL Server.
20. Kiểm tra dữ liệu sau migration, không chỉ kiểm tra app startup.
21. Hiểu ảnh hưởng `@Column(nullable=false)`, `@Index` và `@Version` đến yêu cầu migration.
22. Thiết kế kiểm thử hai chiều: **fresh install** và **upgrade từ version cũ**.
23. Biết lúc nào migration cần tách thành nhiều releases và lúc nào có thể chạy một lần.
24. Xây checklist phê duyệt để không đưa schema-generation destructive mode lên production.

---

## 2. Các thuật ngữ nền tảng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| JPA mapping metadata | Thông tin ánh xạ giữa Java model và cấu trúc lưu trữ | `@Entity`, `@Column`, `@JoinColumn` |
| DDL | Ngôn ngữ định nghĩa cấu trúc database | `CREATE TABLE`, `ALTER TABLE`, `DROP INDEX` |
| Schema generation | Sinh/thi hành DDL từ ORM metadata hoặc script | Hibernate tạo `customers` trong test |
| Schema validation | So sánh một phần mapping với schema đã tồn tại, không sửa | Hibernate `validate` |
| Schema migration | Chuyển schema/version dữ liệu hiện hữu qua các bước có kiểm soát | Flyway `V2__add_status.sql` |
| Data migration | Biến đổi dữ liệu để khớp schema/domain mới | Backfill `status='ACTIVE'` |
| Migration history | Nhật ký các migration đã được áp dụng | Flyway schema history |
| Checksum | Dấu vân tay nội dung migration để phát hiện script thay đổi | Modified `V2` bị báo không khớp |
| Schema drift | Khác biệt giữa database thực tế và trạng thái kỳ vọng | DBA thêm column thủ công |
| Repeatable migration | Migration được chạy lại theo policy khi nội dung thay đổi | Flyway `R__...` cho view/function phù hợp |
| Baseline | Điểm khởi đầu quản lý một DB có sẵn | Đưa legacy DB vào migration tracking |
| Expand/contract | Thay đổi theo giai đoạn để code cũ/mới cùng hoạt động | Thêm cột trước, xóa cột cũ sau |
| Forward-fix | Migration tiếp theo sửa vấn đề thay vì sửa script đã chạy | `V4__fix_status.sql` |

Không đồng nhất “metadata có field” với “DB đã có column”. ORM metadata là **đầu vào mô tả mong muốn**; database schema là **trạng thái thực tế**; migration là **lộ trình thay đổi trạng thái đó**.

---

## 3. Hai câu hỏi khác nhau cần hai công cụ khác nhau

### 3.1. Câu hỏi của schema generation

> “Từ những entity mappings hiện tại, làm sao tạo nhanh một database sạch để thử code?”

Đầu vào:

```text
Entity classes
  @Entity
  @Table(name="customers")
  @Id
  @Column(...)
  @ManyToOne
  @JoinColumn(...)
        |
        v
JPA provider / SQL dialect
        |
        v
CREATE TABLE / constraints / indexes
        |
        v
Test database mới
```

Đây là cách phù hợp khi chấp nhận việc **không giữ lại dữ liệu test cũ**.

### 3.2. Câu hỏi của migration

> “Database đang ở phiên bản N với dữ liệu thật. Làm thế nào chuyển an toàn sang phiên bản N+1 mà không làm hỏng ứng dụng hay mất dữ liệu?”

Đầu vào:

```text
Current production schema + rows
        |
        v
Known migration history
        |
        v
Reviewed SQL changes
        |
        v
Compatibility/locking/backup plan
        |
        v
Apply exactly pending migrations
        |
        v
Verify new schema and data invariants
```

Quá trình này cần **lịch sử trạng thái** chứ không chỉ entity classes hiện tại.

### 3.3. Ví dụ đơn giản về sự khác nhau

Model mới:

```java
@Column(name = "status", nullable = false, length = 20)
private String status;
```

Sinh schema mới:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
```

Nâng schema cũ:

```sql
-- Database đã có bảng customers và 1 triệu rows.
-- Không thể chỉ tạo bảng mới đè lên dữ liệu cũ.
ALTER TABLE customers ADD COLUMN status VARCHAR(20);
-- Phải xác định/backfill giá trị cho rows đã tồn tại.
-- Sau đó mới enforce NOT NULL khi hệ thống sẵn sàng.
```

Đó là khoảng cách mà migration giải quyết.

---

## 4. Metadata JPA có thể sinh ra cấu trúc gì?

Một provider đọc annotations và mapping declarations:

```java
@Entity
@Table(
    name = "customers",
    indexes = @Index(
        name = "idx_customers_email",
        columnList = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email",
            nullable = false,
            unique = true,
            length = 255)
    private String email;

    @Column(name = "full_name",
            nullable = false,
            length = 200)
    private String fullName;

    protected Customer() {}
}
```

Provider có thể suy ra:

- Bảng `customers`.
- Cột `id`, primary key và ID generation strategy.
- Cột `email` với nullability và unique constraint.
- Cột `full_name` với length.
- Index trên email nếu mapping yêu cầu.
- Các khóa ngoại/join tables/collection tables của associations.
- Version column, discriminator hoặc inheritance tables nếu có mapping tương ứng.

### 4.1. Annotation là mô tả logic, không phải DDL tuyệt đối

`@Column(length=255)` không bảo đảm mọi DBMS sinh chính xác cùng kiểu SQL. Provider/dialect có thể chọn `VARCHAR(255)`, một type tương ứng hoặc một cơ chế khác.

`@GeneratedValue(strategy=IDENTITY)` có cú pháp khác giữa PostgreSQL, MySQL, SQL Server và các engines khác.

### 4.2. Không phải mọi yêu cầu DB nằm trong JPA metadata

Ví dụ:

- Check constraints phức tạp hoặc partial indexes.
- PostgreSQL expression indexes hoặc `CREATE INDEX CONCURRENTLY`.
- Database functions, triggers, views, materialized views.
- Row-level security policies.
- Grants/roles.
- Table partitioning.
- Custom domains/types và extensions.
- Online index rebuild strategies.
- Data backfill/cleanup.
- Những ràng buộc phụ thuộc dữ liệu cũ hoặc thời gian triển khai.

Các nhu cầu này thường hợp lý hơn khi quản lý bằng migration scripts.

### 4.3. JPA schema generation không thay thế DBA/data-architecture review

DDL tự sinh có thể đúng để bootstrap schema nhưng chưa phản ánh các quyết định hiệu năng, backup, permissions, monitoring hoặc tương thích trong rolling upgrade.

---

## 5. Jakarta Persistence có schema-generation properties chuẩn

Jakarta Persistence định nghĩa tập properties schema generation có thể cấu hình khi boot persistence unit.

Ví dụ:

```xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit
        name="testPU"
        transaction-type="RESOURCE_LOCAL">

        <class>demo.domain.Customer</class>

        <properties>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ở ví dụ này, provider có thể xóa rồi tạo schema objects phù hợp metadata trong môi trường thử nghiệm. Đây là thiết lập **destructive**, không phù hợp trỏ nhầm tới database chứa dữ liệu cần giữ.

### 5.1. database.action

Các giá trị thường được chuẩn hóa:

| Giá trị | Ý nghĩa tổng quát | Môi trường phù hợp |
|---|---|---|
| `none` | Không tự áp DDL theo thuộc tính này | Production/migration-managed |
| `create` | Tạo các schema objects | Database mới/sạch |
| `drop-and-create` | Xóa rồi tạo lại | Test database dùng một lần |
| `drop` | Xóa schema objects | Cleanup chuyên dụng, rất nguy hiểm với DB chứa dữ liệu |

**Không có `update` và `validate` là các giá trị portable của property `jakarta.persistence.schema-generation.database.action`.** Chúng thường xuất hiện ở cấu hình Hibernate, không phải cùng một API chuẩn.

### 5.2. Cấu hình có thể khác giữa các phiên bản JPA

Trong dự án dùng `javax.persistence.*` đời cũ, property prefix tương ứng có thể là `javax.persistence.*`. Không trộn cùng hai bộ tên property/namespace nếu provider không hỗ trợ.

### 5.3. Tạo schema phải có quyền DDL

Dù cấu hình đúng, database account vẫn phải có quyền tạo/xóa tables/constraints tương ứng. Một app runtime account được giới hạn quyền DML có thể không thực hiện được schema generation, và đó là giới hạn quyền **có chủ đích** trong production.

---

## 6. Sinh SQL script thay vì chạy trực tiếp lên DB

Schema generation có thể dùng để **xuất DDL** để xem xét, không nhất thiết thi hành ngay.

Ví dụ:

```xml
<properties>
    <property
        name="jakarta.persistence.schema-generation.database.action"
        value="none"/>

    <property
        name="jakarta.persistence.schema-generation.scripts.action"
        value="create"/>

    <property
        name="jakarta.persistence.schema-generation.scripts.create-target"
        value="generated-schema.sql"/>
</properties>
```

Đường dẫn target, resource resolution và quyền ghi tùy runtime/provider; cấu hình production/build phải dùng vị trí cụ thể và xác minh file đầu ra.

### 6.1. scripts.action khác database.action

- `database.action`: tác động trực tiếp database nếu được cấu hình.
- `scripts.action`: tạo các SQL scripts tương ứng ở các targets.

Một project có thể chọn **chỉ xuất script** để review. Không tự giả định file đó là migration sẵn sàng chạy trên production.

### 6.2. DDL tạo mới khác DDL upgrade

Một generated create script thường mô tả **đích là database sạch**. Nó không có đầy đủ thông tin:

- Schema production đang có version nào?
- Rows cũ cần backfill thế nào?
- Có object nào bị đổi tên chứ không phải drop/create?
- API cũ/new chạy đồng thời ra sao?
- Quyền/trigger/index vendor-specific nào phải giữ?
- Deployment window và lock limits là gì?

Có thể dùng generated DDL làm **tư liệu tham khảo**, sau đó viết/review migration khác với mục tiêu nâng cấp thực tế.

---

## 7. Script sources và metadata sources trong JPA

Ngoài việc phát DDL từ annotations, Jakarta Persistence có properties như:

```properties
jakarta.persistence.schema-generation.create-source=metadata
jakarta.persistence.schema-generation.drop-source=metadata
```

Các chế độ nguồn thường gồm `metadata`, `script` và các biến thể kết hợp metadata/script theo thứ tự phù hợp. Khi dùng script, có thể chỉ ra script sources thông qua properties như:

```properties
jakarta.persistence.schema-generation.create-script-source=...
jakarta.persistence.schema-generation.drop-script-source=...
```

### 7.1. Không nhầm script-source với migration history

Một tập SQL scripts được cấu hình làm nguồn schema generation không tự có:

- Version numbering.
- Checksum history cho scripts đã áp dụng.
- Logic chạy pending migrations đúng một lần.
- Cơ chế baseline.
- Coordination lock của Flyway/Liquibase.
- Quy trình review/approval và deployment ordering.

Nó vẫn thuộc cơ chế tạo/drop schema, không phải tự động thay thế công cụ migrations.

### 7.2. SQL load scripts phục vụ seed test data

Có các thuộc tính liên quan load script để chuẩn bị dữ liệu sau create schema theo capability tương ứng. Hibernate cũng hỗ trợ một số cơ chế import SQL riêng tùy version.

Dùng cho test data chỉ khi bạn hiểu khi nào script được chạy. Không đặt dữ liệu seed test hoặc tài khoản giả vào cấu hình có thể vô tình chạy production.

---

## 8. Hibernate `hbm2ddl.auto`: cấu hình thường gặp

Hibernate ORM có cấu hình schema tooling riêng, thường thấy dưới tên:

```properties
hibernate.hbm2ddl.auto=create-drop
```

Các giá trị quen thuộc:

| Giá trị | Tác dụng chung | Cảnh báo |
|---|---|---|
| `none` | Không tự tạo/sửa/xóa schema | Phù hợp khi schema do migrations quản lý |
| `validate` | Kiểm tra mapping/schema ở startup | Không sửa schema, không kiểm tra mọi invariant |
| `create` | Tạo lại cấu trúc theo Hibernate schema tooling | Có thể phá hủy objects/data cũ tùy mode/version |
| `create-drop` | Tạo schema khi khởi động và drop khi shutdown SessionFactory theo lifecycle | Chỉ test DB dùng một lần |
| `update` | Cố thay đổi schema hiện có để tương thích với mapping | **Không phải versioned migration** |
| `create-only` | Trong một số phiên bản Hibernate có mode tạo objects mà không thực hiện drop trước | Cần kiểm tra version/config thực tế |

Không xem các tên mode trên là chuẩn portable JPA; tài liệu và hành vi cụ thể phụ thuộc Hibernate version.

### 8.1. Sơ đồ lựa chọn

```text
Database test dùng một lần?
    |
    +-- Có --> Có thể create/create-drop để kiểm tra mapping

Database có dữ liệu cần giữ?
    |
    +-- Có --> Flyway/Liquibase migrations
                  +
               Hibernate validate/none

Muốn tự thêm cột vào DB production?
    |
    +-- Không chọn hbm2ddl.auto=update làm chiến lược migration
```

### 8.2. Hạn chế của `update`

Một ORM schema updater không biết đầy đủ ý định nghiệp vụ:

- `old_name` chuyển thành `new_name` là rename hay drop/add?
- Cột `status` mới nhận giá trị nào cho các rows cũ?
- Cần chạy data correction trước khi thêm unique constraint?
- Index cần tạo online để tránh blocking?
- Có phải giữ compatibility giữa app old/new?
- Có migration đã từng chạy ở production nhưng không còn trong source?
- Có stored procedure hoặc trigger sử dụng cột cũ?

Do đó `update` có thể hữu ích cho một số sandbox cases, nhưng **không phải công cụ thay đổi schema đáng tin cậy cho production**.

### 8.3. `validate` cũng có giới hạn

`validate` có thể phát hiện thiếu bảng/cột, sai types hoặc các lỗi mapping quan trọng tùy Hibernate version/dialect. Nhưng nó không phải database schema diff engine bảo đảm phát hiện **mọi index, unique/check constraint, trigger, grant, partition, collation, data invariant**.

Một startup validate thành công là **tín hiệu tốt**, không phải chứng nhận toàn diện của migration correctness.

---

## 9. Spring Boot và thuộc tính `ddl-auto`

Với Spring Boot dùng Hibernate:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
```

Property này là **Spring Boot configuration** được đưa tới Hibernate schema management. Nó không phải `jakarta.persistence.schema-generation.database.action`.

### 9.1. Giá trị cấu hình có thể phụ thuộc environment

Một ví dụ cho test profile:

```yaml
# application-test-schema.yml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1
  jpa:
    hibernate:
      ddl-auto: create-drop
  flyway:
    enabled: false
```

Đây là một **test-only configuration minh họa**, không phải lời khuyên dùng H2 cho mọi test. Nếu dùng Liquibase thay Flyway, cũng phải xử lý cấu hình Liquibase tương ứng để tránh hai nguồn cùng tạo schema.

### 9.2. Production profile

```yaml
# application-prod.yml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
```

Trong cấu hình này, Flyway là nguồn áp dụng schema migrations còn Hibernate xác nhận mapping ở startup theo mức validation có sẵn.

### 9.3. Đừng dựa hoàn toàn vào “default của Boot”

Spring Boot có auto-configuration khác nhau theo database nhúng/không nhúng và có/không migration tooling; phiên bản Boot cũng có thể thay đổi defaults. Trong hệ thống có dữ liệu thật, **khai báo rõ chính sách schema** và xác minh effective configuration trước khi deploy.

### 9.4. Bảo vệ profile

Nếu một production deployment vô tình bật test profile, `ddl-auto=create-drop` có thể gây mất dữ liệu nghiêm trọng nếu account có quyền DDL. Các lớp bảo vệ nên gồm:

- Tách credentials test/prod.
- Production DB user không có DROP/CREATE quyền không cần thiết.
- Startup policy ngăn destructive modes ở production.
- Review deploy configuration.
- Kiểm tra runtime effective settings và connection target.

---

## 10. Khi nào schema generation là công cụ hợp lý?

Phù hợp:

1. Unit/integration tests dùng database tạm thời.
2. Demo/tutorial không cần bảo toàn dữ liệu.
3. Spike nghiên cứu mapping mới.
4. Test entity inheritance, join columns và naming.
5. Test repository CRUD cơ bản trên schema sạch.
6. Snapshot/so sánh một cách tham khảo DDL phát ra từ metadata.
7. Kiểm tra provider có thể boot persistence unit hợp lệ.
8. Local development environment mà mọi dữ liệu đều có thể xóa.

### 10.1. Một lợi ích đáng kể

Thử một mapping mới:

```java
@OneToMany(mappedBy = "customer")
private List<Order> orders;
```

bạn có thể tạo DB sạch, kiểm tra SQL/foreign keys mà không cần viết migration production ngay. Đây là vòng feedback nhanh để thiết kế model.

### 10.2. Tuy nhiên chỉ kiểm tra schema mới

Nếu test nào cũng tạo lại database từ zero, bạn sẽ không phát hiện chuyện:

- Production table cũ có một cột legacy phải giữ.
- Có null data trước khi thêm NOT NULL.
- Cần chuyển giá trị enum/string đã tồn tại.
- Tên constraint/index cũ gây collision.
- Dữ liệu duplicate làm unique constraint thất bại.
- Old application code vẫn phải hoạt động khi schema mở rộng.

Muốn phát hiện những vấn đề đó, cần **migration upgrade tests**.

---

## 11. Vì sao “test create-drop pass” chưa chứng minh migration an toàn?

Giả sử release đầu có bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
```

Release mới entity:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false, length = 255)
    private String email;

    @Column(nullable = false, length = 20)
    private String status;
}
```

Test với `create-drop` tạo ngay bảng có status, rồi INSERT dữ liệu mới luôn có status. Tất cả tests có thể pass.

Nhưng schema production cũ **chưa có status**. Nếu deploy app mới và `ddl-auto=validate`, app có thể từ chối startup vì thiếu cột. Nếu cho ORM `update` tự thêm cột NOT NULL, dữ liệu cũ/schema constraints có thể không phù hợp hoặc behavior không được kiểm soát.

Một migration đúng phải chuẩn bị dữ liệu cũ:

```text
V1 DB:
  customers(id,email)
  có 1.000.000 rows

V2 requirement:
  customers(id,email,status)
  status cần có giá trị hợp lệ

Plan:
  add nullable column
  handle old writers
  backfill old rows
  verify
  enforce constraints
```

**Test tạo schema mới** và **test nâng từ schema cũ** là hai loại test bổ sung nhau.

---

## 12. Flyway: versioned migrations

Flyway quản lý migration files theo quy tắc naming/versioning và một schema history table.

Ví dụ thư mục:

```text
src/main/resources/
  db/
    migration/
      V1__create_customers.sql
      V2__add_customer_status.sql
      V3__enforce_customer_status.sql
      V4__add_customer_status_index.sql
```

Trong cấu hình mặc định thường gặp, các migration chưa áp dụng được Flyway thực thi theo thứ tự version và ghi kết quả vào schema history.

### 12.1. Tại sao cần version?

Vì database đã áp dụng V1 thì release mới **không chạy lại V1 như một lần create schema mới**. Nó cần biết những migration nào pending.

### 12.2. Checksum để làm gì?

Nếu file V2 đã chạy thành công và sau đó bị sửa nội dung trong repository, Flyway có thể phát hiện checksum không khớp giữa file hiện tại và migration history. Đây là cơ chế bảo vệ **lịch sử đã áp dụng**.

Một nguyên tắc nhóm:

> **Không sửa hoặc xóa versioned migration đã áp dụng ở các môi trường chia sẻ/production chỉ để làm cho model mới đẹp hơn.** Hãy tạo migration mới để chỉnh trạng thái tiếp theo.

### 12.3. Flyway không thay thế code review

Một script có tên V5 hợp lệ vẫn có thể chứa `DROP TABLE customers` nhầm. Versioning và checksum không tự bảo đảm câu SQL an toàn. Cần review nội dung, đánh giá locks, data migration và test.

### 12.4. Một migration runner tại một thời điểm

Flyway có cơ chế phối hợp migrations/history theo khả năng platform, nhưng pipeline vẫn phải thiết kế để tránh nhiều app instances cùng chạy DDL bừa bãi, đặc biệt trên môi trường deploy song song. Một phương án là chạy migration từ một deployment job trước app rollout.

---

## 13. Liquibase: changeSets và database changelog

Liquibase cũng quản lý database changes có lịch sử, thường biểu diễn bằng YAML/XML/JSON/SQL formatted changelogs.

Ví dụ minh họa YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: database-team
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
```

Liquibase theo dõi changeSets đã áp dụng, checksums và trạng thái thông qua tables quản lý riêng; capabilities cụ thể còn có preconditions, contexts/labels và các thay đổi structured.

### 13.1. Flyway và Liquibase là hai lựa chọn, không phải luôn dùng cùng lúc

Một dự án thường chọn một công cụ schema migration làm **nguồn lịch sử có thẩm quyền**. Nếu cấu hình cả hai cùng áp migrations lên một schema mà không có kế hoạch phối hợp, có nguy cơ trùng DDL, conflict và hai history tables đưa ra trạng thái khác nhau.

### 13.2. Không nên chọn công cụ chỉ theo cú pháp SQL/YAML

Tiêu chí còn gồm:

- Cách review migration.
- Mức hỗ trợ DBMS của tổ chức.
- Transactional DDL limitations.
- Preconditions/rollback facilities.
- Schema history/audit trail.
- CI integration.
- Khả năng vận hành khi migration thất bại.
- Quy định cấp quyền/approval.

### 13.3. Học nguyên tắc chung

Trong cả hai hệ thống, điều cốt lõi là **kiểm soát lịch sử thay đổi**, không phải chỉ “chạy một folder SQL bất kỳ lúc startup”.

---

## 14. Ví dụ xuyên suốt: ứng dụng Customer

Giả sử bản đầu tiên lưu thông tin khách hàng:

```text
Customer
  id
  email
  fullName
  version
```

Sau một release, nghiệp vụ muốn thêm trạng thái:

```text
status = ACTIVE | BLOCKED
```

Sau đó mới enforce `NOT NULL` và cho phép query theo status.

Chúng ta sẽ giải quyết bằng **PostgreSQL-oriented Flyway SQL**. Các câu lệnh bên dưới không được coi là portable nguyên xi sang MySQL/Oracle/SQL Server; khi dùng DBMS khác cần biên soạn dialect-specific migrations và chạy trên database mục tiêu.

### 14.1. Entity ban đầu

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email",
            nullable = false,
            unique = true,
            length = 255)
    private String email;

    @Column(name = "full_name",
            nullable = false,
            length = 200)
    private String fullName;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Customer() {}

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getFullName() { return fullName; }
    public long getVersion() { return version; }
}
```

### 14.2. Version 1 của schema

File `V1__create_customers.sql`:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_customers_email UNIQUE (email)
);
```

PostgreSQL sẽ có bảng và constraints tương ứng.

### 14.3. Vì sao V1 cố ý tách khỏi schema generation?

V1 là **migration có review và history**. Hibernate có thể tạo DDL tương tự từ entity, nhưng migration được giữ làm artifact xác định trạng thái schema theo release.

Nếu muốn đổi unique constraint name, column default hoặc chọn loại index, ta có nơi chỉ rõ ý định.

---

## 15. Migration V2: thêm status theo hướng mở rộng

Mục tiêu: thêm cột mới mà chưa làm ứng dụng cũ bị lỗi.

File `V2__add_customer_status.sql`:

```sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20);

ALTER TABLE customers
ALTER COLUMN status SET DEFAULT 'ACTIVE';
```

### 15.1. Vì sao chưa SET NOT NULL ngay?

Vì database có các rows cũ. Cột vừa thêm là NULL ở các rows đã tồn tại (trước khi backfill, tùy câu lệnh/default semantics và DBMS). Nếu áp NOT NULL quá sớm, migration có thể thất bại hoặc tạo lock/rewrite lớn.

### 15.2. DEFAULT phục vụ old writers

Một phiên bản app cũ không biết cột status nên khi INSERT không liệt kê status, database có thể áp default `'ACTIVE'`. Điều này giúp compatibility trong giai đoạn hai phiên bản ứng dụng cùng chạy.

**Nhưng DEFAULT không bảo vệ trường hợp writer chủ động gửi `status=NULL`.** Những write paths như vậy cần được kiểm tra trước khi enforce NOT NULL.

### 15.3. Mới thêm cột chưa có nghĩa app mới đã an toàn để deploy

Nếu app mới map:

```java
@Column(name = "status", nullable = false)
private String status;
```

nhưng V2 chưa backfill records cũ, app có thể đọc NULL và gặp business invariant violations. Cần migration hoặc application logic ở giai đoạn chuyển tiếp chấp nhận/diễn giải null trước khi enforce.

---

## 16. Migration V2 tiếp theo: backfill data

Với bảng nhỏ có thể thêm một câu lệnh trong migration:

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE status IS NULL;
```

Sau đó kiểm tra:

```sql
SELECT COUNT(*) AS null_status_rows
FROM customers
WHERE status IS NULL;
```

Kỳ vọng bằng 0 **tại thời điểm kiểm tra**.

### 16.1. Vì sao backfill quan trọng?

Nếu không backfill, schema mới chứa dữ liệu không thỏa domain invariant. Annotation `@Column(nullable=false)` trong Java không tự đi cập nhật hàng triệu rows cũ thành trạng thái hợp lệ.

### 16.2. Không nên UPDATE cả bảng lớn trong một transaction vô hạn

Với hàng chục triệu records, một `UPDATE` hàng loạt có thể:

- Tạo nhiều WAL/redo logs.
- Tăng replication lag.
- Giữ row locks lâu.
- Tạo bloat, IO pressure.
- Làm ứng dụng gặp timeout.
- Tăng chi phí rollback nếu bị hủy.

Trong trường hợp đó, nên tách **online backfill job** theo batches có checkpoint/progress, đo throughput, có giới hạn tài nguyên và xác định điều kiện chuyển sang bước contract.

### 16.3. Một batch pattern mang tính minh họa

```text
repeat:
  select bounded IDs with status IS NULL
  update those IDs to ACTIVE
  commit small batch
  record progress
until no eligible rows

then:
  verify no null rows
  check concurrent writers
  move to constraint enforcement phase
```

Không lấy một snippet SQL batch cho PostgreSQL rồi áp nguyên vào mọi DBMS. Cách chọn rows/lock/commit hiệu quả phụ thuộc engine và mức load.

---

## 17. Migration V3: enforce NOT NULL và domain constraint

Khi tất cả active writers tuân thủ contract, có thể thêm constraints.

File `V3__enforce_customer_status.sql`:

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE customers
ALTER COLUMN status SET NOT NULL;

ALTER TABLE customers
ADD CONSTRAINT ck_customers_status
CHECK (status IN ('ACTIVE', 'BLOCKED'));
```

### 17.1. Đây là giai đoạn contract

Database giờ từ chối status NULL và giá trị nằm ngoài tập cho phép. Việc thêm constraint có thể cần scan/validation/locks, đặc biệt với bảng lớn. Không chạy thiếu đánh giá production workload.

### 17.2. Đồng bộ JPA mapping

Ở phiên bản application tương ứng, có thể map:

```java
public enum CustomerStatus {
    ACTIVE,
    BLOCKED
}

@Enumerated(EnumType.STRING)
@Column(
    name = "status",
    nullable = false,
    length = 20)
private CustomerStatus status;
```

Đây là đoạn thêm vào entity Customer, không phải một class Customer thứ hai.

### 17.3. EnumType.STRING vẫn cần migration khi đổi enum

Nếu sau này đổi `BLOCKED` thành `SUSPENDED` trong Java, những rows cũ chứa `BLOCKED` có thể không còn map được. Migration data cần được thiết kế, kể cả khi không đổi SQL column type.

### 17.4. Schema constraints và app validation bổ sung nhau

Application nên validate nghiệp vụ trước khi insert/update. Database constraint là lớp bảo vệ cho tất cả writers, kể cả scripts/JDBC. Dùng cả hai nếu mức độ quan trọng của dữ liệu yêu cầu.

---

## 18. Lưu ý về expand–migrate–contract qua nhiều releases

Không phải lúc nào V2 và V3 cũng nên chạy trong cùng một lần deploy.

Một rollout an toàn hơn với nhiều app instances:

```text
Release A:
  App v1 đọc/ghi (id,email,full_name,...)

Migration expand:
  ADD status NULL + DEFAULT

Release B:
  App v2 bắt đầu ghi status rõ ràng
  App v1 vẫn hoạt động trong rolling deploy
  Code v2 tạm chịu được dữ liệu legacy null

Backfill:
  Chuyển rows cũ sang ACTIVE theo policy
  Theo dõi remaining NULL và writer behavior

Release C:
  App v1 đã ngừng hoàn toàn
  App v2 tuân thủ invariant mới

Migration contract:
  SET NOT NULL
  ADD CHECK constraint
  Sau đó bỏ compatibility fallback
```

### 18.1. Vì sao tách releases?

Giả sử thêm column mới và ngay lập tức yêu cầu mọi writer điền nó, nhưng trong cụm còn app cũ không biết column. Default có thể giảm lỗi, nhưng nếu thay đổi phức tạp hơn như rename/drop column, app cũ có thể hỏng ngay. Expand/contract tạo **giai đoạn tương thích**.

### 18.2. Migration order phụ thuộc dependency

Quy tắc phổ biến:

1. Deploy mở rộng schema tương thích.
2. Deploy code hỗ trợ cả schema cũ/mới hoặc đã có cột mới.
3. Chạy data migration/backfill.
4. Quan sát correctness.
5. Bỏ old code paths.
6. Enforce constraints/drop old columns.

Không máy móc áp cho mọi change. Những thay đổi requiring code-before-DDL cũng tồn tại; hãy lập compatibility matrix cụ thể.

### 18.3. Migration version và app version là hai chiều khác nhau

Database migration V3 không nhất thiết trùng app release 3. Một release có thể có nhiều migrations; một migration có thể được áp trước một số app versions để giữ compatibility. Ghi rõ mapping ở deployment manifest/runbook.

---

## 19. Bảng compatibility trong rolling deployment

| App version | Schema v1 | Schema expanded v2 | Schema contracted v3 |
|---|---|---|---|
| App v1 (không biết status) | Hoạt động | Có thể hoạt động nhờ default/nếu SQL cũ tương thích | Cần xác nhận vẫn tương thích hoặc đã ngừng |
| App v2 transitional | Cần schema mới? có thể fail nếu tham chiếu status | Hoạt động với NULL-tolerant logic | Hoạt động |
| App v3 strict status | Không phù hợp | Có thể gặp nulls legacy | Phù hợp khi migration đã hoàn tất |

### 19.1. Không “đoán tương thích” từ annotation

App v1 có native `INSERT INTO customers VALUES (...)` không liệt kê tên cột có thể hỏng ngay khi thêm status, dù SQL default tồn tại. Dạng SQL này là anti-pattern cho schema evolution: nên liệt kê cột khi INSERT.

### 19.2. Đọc/ghi theo cả hai chiều

Kiểm tra:

- Old app có còn INSERT/UPDATE được?
- New app có đọc records legacy chưa backfill được?
- New app có tạo giá trị mà old app không hiểu không?
- Existing indexes/triggers có hoạt động?
- Serialization/API contracts có giữ tương thích?

### 19.3. Không cần giữ app v1 mãi mãi

Khi migration contract đã áp và old app rút khỏi hệ thống, có thể loại compatibility logic. Nhưng phải có bằng chứng old writer không còn hoạt động (deployment inventory, logs, connection owner, job schedule).

---

## 20. Vì sao rename column nguy hiểm hơn tưởng tượng?

Giả sử cần đổi `full_name` thành `display_name`.

Phương pháp dễ nghĩ:

```sql
ALTER TABLE customers
RENAME COLUMN full_name TO display_name;
```

Trên database, thao tác có thể nhanh trong một số engine, nhưng mọi app versions/query/job dùng `full_name` sẽ bị lỗi sau rename.

### 20.1. Expand–contract cho rename

Một lộ trình:

```text
Phase 1: ADD display_name nullable.
Phase 2: App ghi cả full_name và display_name.
Phase 3: Backfill display_name = full_name.
Phase 4: App đọc display_name, có fallback khi cần.
Phase 5: Dừng mọi readers/writers full_name.
Phase 6: Enforce display_name constraint.
Phase 7: DROP full_name ở migration sau.
```

### 20.2. Dual-write phải có consistency policy

Ghi cả hai cột có thể thất bại một nửa nếu các write paths không đồng nhất. Nên ghi trong cùng DB transaction và kiểm tra với triggers/other writers. Nếu cột mới là derived value, một trigger hoặc data pipeline cũng là phương án, nhưng cần trade-off rõ.

### 20.3. Không dùng ORM auto-update để đoán rename

Khi Java field đổi tên, một updater có thể coi đó là “cột cũ không dùng, cột mới cần thêm”, chứ không biết rằng đây là rename giữ dữ liệu. Một migration explicit nói rõ intent là cách kiểm soát tốt hơn.

---

## 21. Đổi kiểu dữ liệu cần khảo sát data trước

Ví dụ cột cũ:

```sql
status VARCHAR(100)
```

muốn thành:

```sql
status VARCHAR(20)
```

Nếu có dữ liệu dài hơn 20 ký tự, câu ALTER có thể lỗi hoặc truncate tùy engine/mode. Cần khảo sát:

```sql
SELECT MAX(LENGTH(status)) AS max_status_length
FROM customers;
```

Với dữ liệu thật còn phải kiểm tra encoding, collation, enum values và application query behavior.

### 21.1. Từ VARCHAR sang INTEGER còn phức tạp hơn

Nếu source chứa `"0007"`, `"7A"`, NULL, whitespace, việc chuyển kiểu cần một transform rule rõ. Test trên dữ liệu giả “toàn 123” không phản ánh production.

### 21.2. Không đoán cast behavior

PostgreSQL, MySQL, Oracle và SQL Server có cú pháp casting, implicit conversion và error handling khác nhau. Migration phải được viết/test cho target DBMS.

### 21.3. Với bảng lớn, cân nhắc shadow column

Thêm cột mới, backfill theo batches, dual-read/write rồi chuyển dần có thể giảm downtime so với một ALTER rewrite lớn, tùy DBMS.

---

## 22. Unique constraint: cần dọn dữ liệu trước

Giả sử email đang cho duplicates, release mới muốn unique.

Trước khi thêm constraint:

```sql
SELECT LOWER(email) AS normalized_email,
       COUNT(*) AS duplicate_count
FROM customers
GROUP BY LOWER(email)
HAVING COUNT(*) > 1;
```

Đây là một kiểm tra normalization theo ví dụ; case-sensitivity/collation semantics cần được quyết định rõ.

### 22.1. Dữ liệu duplicate phải có policy

- Giữ record nào?
- Merge hồ sơ nào?
- Có foreign keys trỏ tới records bị merge không?
- Có xóa dữ liệu hoặc đổi email không?
- Có cần báo người dùng?
- Migration có cần audit/log hay manual review?

Không thể giải quyết bằng một `@Column(unique=true)` đơn thuần.

### 22.2. Unique index có thể khóa hoặc ảnh hưởng ghi

Cách tạo unique index online/concurrently phụ thuộc DBMS/version. Bảng lớn cần đánh giá lock levels và feature hỗ trợ.

### 22.3. Check trước vẫn có race

Trong lúc bạn đang kiểm tra duplicates, app có thể tạo duplicate mới. Muốn enforce, cần chuẩn bị writer behavior, constraint/index creation và concurrency plan đúng.

---

## 23. Foreign keys và dữ liệu mồ côi

Giả sử thêm `orders.customer_id` foreign key đến `customers.id`.

Trước migration:

```sql
SELECT o.id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

Đây là bước tìm orphan records.

### 23.1. Việc thêm FK không tự sửa orphan rows

JPA `@ManyToOne` và `@JoinColumn` mô tả relationship. Migration phải quyết định sửa/xóa các orphan records nếu DB đang có.

### 23.2. Hành vi xóa phải được quyết định rõ

`ON DELETE CASCADE`, `RESTRICT` hoặc `SET NULL` có semantics database riêng. Không nhầm JPA `CascadeType.REMOVE` với database ON DELETE CASCADE; một cái là provider-managed entity lifecycle, một cái là FK behavior ở database.

### 23.3. Large tables cần đánh giá validation cost

Thêm FK có thể cần scan dữ liệu và giữ locks. Một số DBMS hỗ trợ tạo constraint ở trạng thái chưa validate rồi validate sau; syntax/capability vendor-specific.

---

## 24. Index migration và DDL online

Một migration thêm index:

```sql
CREATE INDEX idx_customers_status
ON customers(status);
```

có thể hữu ích nếu query thường lọc status. Nhưng index creation trên bảng lớn có thể làm ảnh hưởng concurrent reads/writes tùy engine, version, index type và strategy.

### 24.1. PostgreSQL CONCURRENTLY

PostgreSQL hỗ trợ:

```sql
CREATE INDEX CONCURRENTLY idx_customers_status
ON customers(status);
```

Lệnh này có ràng buộc transaction đặc biệt: không chạy trong một transaction block thông thường. Migration tool phải được cấu hình để thực hiện migration đó theo chế độ transaction phù hợp.

### 24.2. Không áp cùng cú pháp cho MySQL/Oracle/SQL Server

Các DBMS có giải pháp online DDL riêng, có thể kèm edition/license/version limits. Không coi `CONCURRENTLY` là SQL portable.

### 24.3. Index là một phần của migration history

Đừng chỉ đặt `@Index` trong entity mới và kỳ vọng production index sẽ luôn được Hibernate tạo nếu `ddl-auto=validate`. Migration phải chứa lệnh index cần thiết.

### 24.4. Kiểm tra hiệu năng sau migration

Ngoài schema đúng, cần EXPLAIN/query plan, index usage, write overhead và ảnh hưởng đến replication/storage. Một index có thể tạo thành công nhưng không có lợi cho workload.

---

## 25. Transactional DDL khác nhau giữa DBMS

Một migration chứa nhiều câu SQL:

```sql
ALTER TABLE ...;
UPDATE ...;
CREATE INDEX ...;
```

có thể có transaction behavior khác nhau theo database engine.

### 25.1. PostgreSQL

Nhiều thao tác DDL ở PostgreSQL có thể được thực thi trong transaction và rollback nếu fail, nhưng có **ngoại lệ** như `CREATE INDEX CONCURRENTLY` không chạy trong transaction block thông thường.

### 25.2. MySQL/InnoDB

Nhiều thao tác DDL trong MySQL có implicit commit/atomic DDL behavior riêng; không mặc định rằng toàn bộ migration nhiều statements có thể rollback như một user transaction trên PostgreSQL.

### 25.3. Oracle và SQL Server

Cú pháp và transaction/lock semantics khác nhau; một số DDL có implicit commits hoặc special rules. Cần đọc behavior của DBMS/version thật.

### 25.4. Hệ quả cho rollback

Một migration thất bại giữa chừng có thể để lại **schema thay đổi một phần** trên DBMS/config nhất định. Migration tool history có thể phản ánh failed state; quy trình recovery phải biết database thực tế đang ở đâu, không chỉ “script báo failed nên chưa có gì thay đổi”.

---

## 26. Vì sao cần migration history table?

Một hệ thống có migrations:

```text
V1 create customers
V2 add status
V3 enforce status
V4 add index
```

Cần biết database đã áp dụng đến đâu.

Ví dụ conceptual:

```text
migration_history
  version | description              | success
  ------------------------------------------------
  1       | create customers         | true
  2       | add customer status      | true
  3       | enforce customer status  | true
```

Khi triển khai release có V4, migration runner chạy **V4 pending**, không chạy lại V1–V3.

### 26.1. Không dùng app version làm thay thế DB history

Một database có thể được cập nhật trước app, hoặc app fail deploy sau khi migration chạy xong. Database version và app version không luôn đồng bộ 1:1.

### 26.2. Checksum phát hiện sửa lịch sử

Nếu có người sửa V2 sau khi đã áp, lịch sử checksum không khớp với artifact. Đây là dấu hiệu cần điều tra, không phải “lỗi nhỏ cứ tắt validation”.

### 26.3. Đừng tự xóa history table để “chạy lại”

Xóa history trên database đã có dữ liệu khiến migration runner không biết trạng thái thật; chạy lại CREATE TABLE có thể lỗi, hoặc tệ hơn nếu scripts có destructive actions. Phải xử lý theo quy trình baseline/repair được kiểm soát.

---

## 27. Vì sao không sửa migration đã chạy?

Giả sử V2 đã chạy ở staging/production:

```sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20);
```

Một developer muốn đổi V2 thành:

```sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(30);
```

Nếu sửa V2, database cũ vẫn có VARCHAR(20) còn repository giờ mô tả V2 khác. History checksum có thể báo lệch.

### 27.1. Đúng hơn: thêm V4

```sql
-- V4__widen_customer_status.sql
ALTER TABLE customers
ALTER COLUMN status TYPE VARCHAR(30);
```

Ví dụ cú pháp PostgreSQL. Lịch sử rõ:

```text
V2: add VARCHAR(20)
V4: widen to VARCHAR(30)
```

### 27.2. “Migration bất biến” có ngoại lệ do policy quản lý

Trong local sandbox chưa chia sẻ, có thể reset database và sửa migrations chưa áp ở môi trường chung. Nhưng một khi migration đã được sử dụng bởi các môi trường/teammates, thay đổi lịch sử cần quy trình rõ; mặc định **new migration thay vì edit applied migration**.

### 27.3. Flyway repair không phải nút xóa lỗi logic

Một số công cụ hỗ trợ repair history/checksum theo policy. Chỉ dùng sau khi biết database thực tế, reason và tác động; không dùng để hợp thức hóa việc sửa migration làm dữ liệu production khác khỏi expected state.

---

## 28. Repeatable migrations dùng cho loại artifact nào?

Một số objects như views/functions có thể được quản lý bằng repeatable migration theo công cụ.

Ví dụ tên Flyway:

```text
R__create_customer_summary_view.sql
```

Khi nội dung repeatable migration thay đổi, công cụ có thể chạy lại theo chính sách version/checksum, tùy cấu hình.

### 28.1. Không dùng repeatable để backfill dữ liệu tùy tiện

Một `UPDATE customers SET status=...` có thể làm thay dữ liệu hiện tại mỗi lần chạy lại. Repeatable migrations phù hợp hơn với những objects định nghĩa có khả năng recreate/idempotent theo thiết kế.

### 28.2. View/function definitions cũng cần compatibility

Nếu app cũ dùng một column của view bị loại bỏ trong repeatable migration, rolling deployment vẫn có thể lỗi. “Repeatable” không loại bỏ nhu cầu expand/contract.

---

## 29. Baseline một database legacy

Nhiều dự án đã có production DB trước khi áp Flyway/Liquibase.

### 29.1. Vấn đề

Database hiện có:

```text
customers
orders
order_lines
indexes
constraints
triggers
dữ liệu vài năm
```

Nếu migration runner mới thấy schema không rỗng mà lịch sử chưa có, không thể giả định database này tương đương V1. Cần thiết lập **baseline** có kiểm chứng.

### 29.2. Quy trình baseline

1. Chụp inventory schema hiện hữu.
2. Xác định state/phiên bản production thực tế.
3. So sánh các môi trường production/staging/dev.
4. Tạo baseline migration hoặc baseline marker theo tool policy.
5. Kiểm tra fresh install từ lịch sử tương ứng.
6. Test pending migrations trên bản sao database.
7. Ghi lại lý do và evidence cho baseline.
8. Không để baseline bỏ qua ngẫu nhiên các migrations cần chạy.

### 29.3. Tránh bật baseline-on-migrate vô điều kiện

Một property tự baseline schema có thể hữu ích khi onboarding legacy DB, nhưng nếu trỏ nhầm database hoặc schema sai, nó có thể che lỗi định danh môi trường. Cần điều kiện và review chặt.

### 29.4. Baseline không phải xóa database rồi dựng lại

Mục tiêu là đưa database chứa dữ liệu vào lịch sử migrations **mà không mất dữ liệu**. Không chuyển mọi production rows về zero chỉ để có lịch sử đẹp.

---

## 30. Schema drift: thay đổi ngoài migration history

Tình huống:

```text
Git migrations: V1-V4
Staging DB:    V1-V4 + một column DBA thêm thủ công
Production DB: V1-V4, không có column thêm
```

Cả hai có thể báo migration history version 4, nhưng physical schemas khác nhau.

### 30.1. Drift làm test sai kết luận

Nếu staging có index được tạo thủ công, benchmark query rất nhanh; production không có index nên latency tăng. Migration history không tự nhận diện mọi drift nếu thay đổi ngoài tool.

### 30.2. Phòng ngừa

- Hạn chế quyền DDL trực tiếp.
- Đưa mọi change qua PR migration.
- So sánh schema snapshots/diffs ở các môi trường.
- Kiểm tra migration history lẫn physical objects.
- Thiết lập incident procedure nếu cần hotfix trực tiếp DB.
- Sau hotfix, cập nhật migration history bằng thay đổi có kiểm soát thay vì bỏ mặc drift.

### 30.3. Hibernate validate không bảo đảm hết drift

Hibernate có thể không phát hiện một index dư hoặc trigger khác. Nếu drift là mối lo lớn, cần schema diff tool/DB metadata inspection ngoài ORM validate.

---

## 31. Hai tuyến test nên cùng tồn tại

Một dự án JPA trưởng thành thường có **ít nhất hai mục đích test** khác nhau:

```text
A. Mapping-focused tests
   start empty disposable DB
   ORM creates schema
   exercise entity mapping/CRUD

B. Migration-focused integration tests
   start empty DB or old-schema snapshot
   run actual Flyway/Liquibase migrations
   boot ORM with ddl-auto=validate/none
   run repositories/services
   verify schema and data
```

### 31.1. Test A nhanh và cô lập

Dùng một database tạm thời, `create-drop` được cấu hình trong môi trường test. Mục tiêu là phát hiện mapping conflicts, missing IDs, associations, cascade behavior.

### 31.2. Test B phản ánh deployment

Không cho ORM tự dựng schema. Database phải được dựng bằng **migrations như production** rồi ứng dụng mới chạy. Mục tiêu là phát hiện migration file thiếu, order sai, columns/types mismatch.

### 31.3. Không dùng kết quả A thay cho B

Nếu chỉ có A, một annotation mới được Hibernate đưa vào schema sạch có thể pass dù migration file tương ứng chưa tồn tại.

### 31.4. Không cần mọi unit test chạy migrations

Unit tests thuần Java không cần DB. Chọn test slice phù hợp để giữ tốc độ CI mà vẫn có integration suite đủ mạnh cho thay đổi persistence.

---

## 32. H2 tiện nhưng không đồng nghĩa production DBMS

H2 là lựa chọn phổ biến cho repository tests vì khởi động nhanh. Tuy nhiên H2 có khác biệt về:

- SQL dialect/DDL syntax.
- Identity/sequence behavior.
- JSON/array/enum types.
- Timestamp precision/timezone.
- Identifier quoting và case-sensitivity.
- Indexes và constraints.
- Transactions/isolation/locking.
- Query planner và pagination.
- Generated columns, triggers, functions.

### 32.1. “PostgreSQL mode” không biến H2 thành PostgreSQL

Compatibility mode có thể hỗ trợ một số cú pháp, nhưng không mô phỏng đầy đủ PostgreSQL engine/transaction/DDL capabilities.

### 32.2. Chọn test theo rủi ro

H2 có thể phù hợp khi test model đơn giản và muốn tốc độ. Với migrations PostgreSQL-specific, bắt buộc có tests trên PostgreSQL thật hoặc môi trường tương thích đã xác minh, ví dụ disposable PostgreSQL container.

### 32.3. Testcontainers/ephemeral DB giúp giảm khác biệt

Chạy cùng DB engine/version family trong CI giúp phát hiện migration SQL không portable và schema constraints khác với H2.

### 32.4. Vẫn phải chú ý version cụ thể

Một PostgreSQL 12 container không nhất thiết có mọi DDL feature/performance/lock behavior như PostgreSQL 16 production. Chọn version có chủ đích và kiểm tra upgrade path.

---

## 33. Testcontainers với PostgreSQL migration test

Ví dụ Spring Boot + JUnit 5 + Testcontainers:

```java
package demo.persistence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class CustomerMigrationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username", postgres::getUsername);
        registry.add(
            "spring.datasource.password", postgres::getPassword);

        registry.add("spring.flyway.enabled", () -> "true");
        registry.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "validate");
    }

    @Autowired
    CustomerRepository customers;

    @Test
    void migrated_schema_supports_repository() {
        Customer customer = new Customer(
            "test@example.com", "Example Customer");

        Customer saved = customers.saveAndFlush(customer);

        assertNotNull(saved.getId());
    }
}
```

Đây là **sườn test cho môi trường Flyway + Spring Boot**: cần dependency Testcontainers PostgreSQL/JUnit, PostgreSQL JDBC driver, Flyway integration phù hợp phiên bản, CustomerRepository và entity fields tương ứng với schema đã áp dụng. Nếu entity phiên bản mới yêu cầu status, constructor/factory trong test cũng cần gán status; test cuối chỉ minh họa cách container/migration được nối với Boot.

### 33.1. Đừng để @DataJpaTest thay container bằng embedded DB

Nếu dùng `@DataJpaTest` và test database auto-replacement, cần cấu hình không thay DataSource Testcontainers bằng H2, ví dụ `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` theo version Spring Boot.

### 33.2. Bản Boot mới có cách @ServiceConnection

Một số Spring Boot versions hỗ trợ integration Testcontainers `@ServiceConnection`, nhưng không cần trộn các kiểu wiring trong cùng ví dụ. Chọn một cách phù hợp version.

### 33.3. Flyway phải chạy trước JPA validate

Mục tiêu: migration tạo schema; sau đó Hibernate validate mapping. Trong Spring Boot auto-configuration phù hợp, migration initializer được phối hợp trước JPA setup. Nếu tự cấu hình DataSource/EntityManagerFactory/initializers, phải xác nhận dependency/order thực tế.

### 33.4. Validate không thay data assertions

Bài test trên chưa kiểm tra legacy data backfill. Cần viết test upgrade riêng.

---

## 34. Fresh-install migration test

Fresh-install test bắt đầu từ database hoàn toàn rỗng:

```text
Empty database
    |
    v
Run V1
    |
    v
Run V2
    |
    v
Run V3
    |
    v
Validate schema
    |
    v
JPA repository CRUD
```

Đây là test cho khả năng dựng một môi trường mới từ **toàn bộ migration history**.

### 34.1. Dễ nhầm với create-drop test

Fresh-install test dùng **Flyway/Liquibase scripts**, không dùng Hibernate `create-drop`. Kết quả có thể cùng là một schema mới, nhưng nguồn tạo ra khác nhau.

### 34.2. Nếu schema từ migration khác metadata

Hibernate `validate` có thể phát hiện một số mismatch. Ngoài ra nên kiểm tra các constraints/indexes/SQL features mà Hibernate không validate đầy đủ.

### 34.3. Test chạy migrations lần hai

Migration runner thường cần xác định không có pending migration sau khi đã áp hết versions. Một integration test có thể gọi migration check/re-run phù hợp tool và xác minh không tự DROP/CREATE lại tables hoặc mất records.

---

## 35. Upgrade-path test quan trọng hơn khi database đã lớn

Một upgrade test bắt đầu từ **schema V1 đã có dữ liệu**, không phải database rỗng:

```text
Create DB at V1
    |
    v
Insert representative legacy records
    |
    v
Run pending V2/V3 migrations
    |
    v
Check schema + transformed data
    |
    v
Boot application model mới
    |
    v
Read/update/create records
```

### 35.1. Test case mẫu

Trước migration:

```sql
INSERT INTO customers (email, full_name, version)
VALUES
    ('alice@example.com', 'Alice', 0),
    ('bob@example.com', 'Bob', 0);
```

Sau V2/V3:

```sql
SELECT id, email, status
FROM customers
ORDER BY id;
```

Kỳ vọng:

```text
alice@example.com -> ACTIVE
bob@example.com   -> ACTIVE
```

Đồng thời:

```sql
SELECT COUNT(*)
FROM customers
WHERE status IS NULL;
```

phải trả 0 trong schema đã contract.

### 35.2. Không chỉ dùng một row mẫu

Thêm test data chứa:

- Nulls/empty strings legacy.
- Duplicate candidates.
- Special Unicode characters.
- Bản ghi có FK đến records khác.
- Min/max lengths.
- Enum values cũ.
- Large numeric/timestamp values.
- Soft-deleted và inactive rows nếu liên quan.

### 35.3. Migration lớn cần performance rehearsal

CI test với vài trăm rows không dự đoán được migration backfill 100 triệu rows mất bao lâu và khóa bao lâu. Cần staging rehearsal với quy mô/đặc tính dữ liệu đại diện, metrics và time budget.

---

## 36. Test rollback bằng database transaction và backup khác nhau

Một migration failure có ít nhất hai chiều:

1. **DDL transaction rollback** trong DBMS.
2. **Application release rollback** (deploy lại app version cũ).

Chúng không đồng nhất.

### 36.1. DDL rollback

Nếu DBMS hỗ trợ transactional DDL cho statement tương ứng, migration fail có thể rollback thay đổi DDL. Nhưng không bảo đảm mọi DBMS/statement có cùng capability.

### 36.2. Application rollback

Bạn có thể deploy lại app v1 sau khi DB đã ở schema v2. Nếu v2 được thiết kế backward-compatible, app v1 vẫn chạy. Nếu migration đã DROP column v1 dùng, rollback app không cứu được.

### 36.3. Data rollback có thể khó hoặc bất khả thi

Nếu migration gộp hai fields thành một, làm mất thông tin cũ, không phải lúc nào cũng viết được DOWN migration hoàn hảo. Backup/snapshot hoặc forward-fix có thể là lựa chọn thực tế.

### 36.4. Đừng tự động DROP column khi rollback deploy

Một pipeline “rollback app -> chạy DROP COLUMN ngay” có thể xóa dữ liệu do app mới đã ghi, gây mất dữ liệu. Migrations cần runbook riêng cho rollback/restore.

---

## 37. Forward-only migrations và roll-forward

Nhiều nhóm ưu tiên **forward-only migrations**:

```text
V1 -> V2 -> V3
            |
            +-- phát hiện bug
            |
            v
            V4 fix
```

Ưu điểm:

- Lịch sử tiến triển rõ.
- Không dựa vào việc đảo ngược một phép chuyển dữ liệu có thể mất mát.
- Dễ phối hợp với nhiều app versions trong rolling deployment.

### 37.1. Không phải “không cần backup”

Forward-only là chiến lược phần mềm, không thay thế backups, PITR (point-in-time recovery), rehearsals và incident response.

### 37.2. Khi nào cần restore?

Nếu migration làm hỏng/xóa dữ liệu không thể tái tạo, có thể cần khôi phục từ backup hoặc replay transaction logs, kèm kế hoạch xử lý writes xảy ra sau backup. Đây là operation rủi ro cao, phải được luyện tập và phê duyệt.

### 37.3. Một migration fix cũng phải review

Thêm V4 không tự bảo đảm dữ liệu đúng. Test V4 trên bản sao của trạng thái hỏng/thực tế trước khi áp production.

---

## 38. Quyền database: runtime app khác migration runner

Một mô hình an toàn:

```text
Migration runner:
  CREATE / ALTER / DROP theo quyền giới hạn
  Chạy trong deployment stage có phê duyệt

Application runtime:
  SELECT / INSERT / UPDATE / DELETE phù hợp
  Không có quyền DROP TABLE/ALTER TABLE tùy ý
```

### 38.1. Vì sao tách quyền?

Nếu app runtime credentials không có quyền DDL, lỗi cấu hình `ddl-auto=create-drop` ở production khó gây xóa bảng hơn. Đây là defense-in-depth, không thay việc kiểm soát config.

### 38.2. DDL permissions cũng phải giới hạn

Migration account không nhất thiết cần superuser. Chỉ cấp quyền cần cho schema objects và operations cụ thể.

### 38.3. Không lưu secrets trong migrations

Migration SQL không nên chứa passwords/API tokens thật hoặc embedded secrets. Credentials được cung cấp qua secrets manager/CI environment phù hợp.

---

## 39. Khi nào nên chạy migration?

Các cách phổ biến:

1. Flyway/Liquibase chạy khi application startup.
2. Migration chạy trong deployment job độc lập trước app rollout.
3. Một migration service/job có quyền riêng.
4. Pipeline có approval gate trước production DDL.

### 39.1. Chạy tại app startup

Đơn giản cho dịch vụ nhỏ, nhưng khi có nhiều replicas startup đồng thời, phải hiểu cơ chế coordination/locks và quyền DDL. Một migration lâu có thể làm rollout chậm/failed startup.

### 39.2. Job độc lập

Phù hợp khi cần:

- Tách credentials DDL.
- Approval/maintenance window.
- Theo dõi migration progress.
- Kiểm soát chỉ chạy một migration executor.
- Khóa deployment nếu migration thất bại trước khi app mới chạy.

### 39.3. Phải xác nhận compatibility trước khi chạy DDL

Migrations cần đúng thứ tự với app versions. Có những changes không thể triển khai trong một bước, dù migration job chạy chính xác.

---

## 40. Một pipeline CI/CD có kiểm soát

```text
Developer changes entity model
         |
         v
Add versioned migration(s)
         |
         v
Peer review SQL + risk assessment
         |
         v
CI:
  - lint migration naming
  - create clean DB
  - apply all migrations
  - Hibernate validate
  - repository/service tests
  - upgrade tests from old schema
         |
         v
Staging rehearsal:
  - representative data
  - timing/locks
  - rollback/forward-fix drill
         |
         v
Production deployment:
  - backup/restore plan verified
  - migration applied
  - app rollout
  - health/data checks
         |
         v
Monitoring and post-deploy verification
```

### 40.1. Không tách entity và migration thành hai deploy ngẫu nhiên

Nếu app version mới đòi cột mới mà migration chưa chạy, startup hoặc request sẽ lỗi. Trong PR/release, mapping changes và migration artifacts nên được review cùng nhau, dù thứ tự apply khi deploy có thể tách theo expand/contract.

### 40.2. DB migration failure phải block rollout phù hợp

Nếu migration cần thiết cho app mới thất bại, không tiếp tục deploy app mới bằng cách tắt validation mà không điều tra.

### 40.3. Health check không chỉ là HTTP 200

Một service có thể khởi động nhưng query path mới sai do missing index, stale view hoặc data migration chưa hoàn tất. Cần smoke tests và data integrity metrics.

---

## 41. Data migration nên có các phép đo nào?

Ví dụ backfill Customer.status:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE status IS NULL) AS null_rows,
    COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_rows,
    COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked_rows
FROM customers;
```

Đây là cú pháp PostgreSQL với `FILTER`; DBMS khác có thể cần `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

### 41.1. Đếm trước và sau

Ghi baseline counts, target counts và invariant expected. Không chỉ dựa vào “migration statement completed”.

### 41.2. Row count không đủ cho mọi transform

Nếu migration hợp nhất/cắt cột, cần checksum/sample reconciliation/business rules:

- Số records không được mất.
- Total monetary amounts không đổi theo yêu cầu.
- FK integrity.
- Email normalization correctness.
- Các trạng thái không hợp lệ = 0.
- Histories/timestamps còn nguyên.

### 41.3. Backfill progress

Nếu dùng batches, log:

```text
rows processed
remaining rows
elapsed time
average batch latency
DB lock waits
replication lag
errors/retries
```

Đừng log PII không cần thiết.

---

## 42. Giao dịch và locking khi migration chạy

DDL/long UPDATE có thể ảnh hưởng production traffic.

### 42.1. Các rủi ro

- Table locks hoặc metadata locks.
- Row locks giữ lâu.
- Query timeout/deadlocks.
- WAL/redo/undo growth.
- Replication lag.
- Connection exhaustion.
- Long transaction blocking VACUUM/purge.
- Cache invalidation/plan changes.

### 42.2. Trước khi chạy

Đánh giá:

1. Table size và traffic.
2. DBMS/version/engine.
3. DDL lock modes.
4. Existing long transactions.
5. Index/constraint creation algorithm.
6. Estimated migration runtime.
7. Timeout/lock wait policy.
8. Batch size.
9. Maintenance window hoặc online strategy.
10. Cancel/retry/cleanup plan.

### 42.3. Timeout phải có ý nghĩa

Một `lock_timeout` ở PostgreSQL khác timeout query/transaction/connection pool. Cần biết failure semantics của database và migration runner; không gộp tất cả là “script chạy quá lâu”.

### 42.4. Migration có thể giữ lock kể cả nếu SQL nhìn ngắn

`ALTER TABLE` một dòng có thể yêu cầu lock mạnh. Đánh giá execution semantics thật, không suy từ số dòng SQL.

---

## 43. Backfill dữ liệu lớn: tách schema và data deployments

Ví dụ 50 triệu customers:

```text
Phase A:
  ADD COLUMN status NULL
  DEFAULT for future rows
  commit DDL nhanh nếu engine hỗ trợ path phù hợp

Phase B:
  Application safely reads/writes with transitional logic

Phase C:
  Background job updates status in batches
  progress + retries + metrics
  do not hold single massive transaction

Phase D:
  Verify 0 remaining nulls
  check writer compatibility

Phase E:
  Enforce NOT NULL/CHECK with DBMS-specific plan
```

### 43.1. Tại sao không để migration runner chạy 6 giờ trong một transaction?

Một migration runner phù hợp với schema changes không nhất thiết là công cụ tốt nhất cho online backfill dài. Tùy hệ thống, data migration có thể là idempotent application job hoặc chuyên dụng batch process, với checkpoints và observability.

### 43.2. Nhưng phải ghi lại “phase complete”

Nếu backfill nằm ngoài Flyway migration history, cần có cách ghi version/progress và điều kiện tiếp tục contract migration. Không nên chỉ tin một người nói “job đã chạy”.

### 43.3. Concurrency với writes mới

Trong lúc backfill, ứng dụng vẫn ghi dữ liệu. Job phải tránh ghi đè những trạng thái đã được user chuyển thành `BLOCKED`:

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE status IS NULL;
```

Điều kiện WHERE làm update chỉ những rows chưa có giá trị, nhưng cần hiểu transaction isolation, worker concurrency và retry behavior.

---

## 44. Idempotency trong migrations

Một migration đã được Flyway quản lý thường không cần chạy lại nếu history nói đã applied. Nhưng các **backfill jobs** và recovery operations nên được thiết kế idempotent khi có thể.

### 44.1. Ví dụ idempotent data update

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE status IS NULL;
```

Chạy lại sau khi đã hoàn thành không thay đổi rows có status khác NULL.

### 44.2. Không nhầm IF NOT EXISTS với migration history

`CREATE TABLE IF NOT EXISTS` có thể tránh một lỗi khi bảng đã có, nhưng cũng có thể che schema drift: bảng tên đúng nhưng thiếu columns/constraints. Không sử dụng mọi nơi chỉ để migration “không lỗi”.

### 44.3. Tiêu chí idempotency

Một operation idempotent nên đạt cùng kết quả khi lặp lại trong giới hạn contract, không gây double-charge, double-copy hoặc duplicate history rows. Với các backfill có side effects, cần idempotency key/checkpoint riêng.

---

## 45. Migration failure giữa chừng: xử lý ra sao?

Giả sử:

```text
V5:
  add column A -> succeeded
  copy values -> partially succeeded
  create constraint -> failed
```

Trên DBMS không hỗ trợ rollback toàn migration như mong muốn, schema có thể ở trạng thái một phần.

### 45.1. Không tự chạy lại nguyên file ngay lập tức

Nếu câu `ADD COLUMN A` đã thành công, chạy lại có thể lỗi duplicate column hoặc phát tác động khác. Đầu tiên phải:

1. Kiểm tra migration history.
2. Kiểm tra actual schema.
3. Kiểm tra data mutation status.
4. Xác định transaction boundaries.
5. Đọc error/vendor code.
6. Lập recovery script/repair plan.
7. Review/approval trước khi tiếp tục.

### 45.2. Backup và restore không chỉ là có file backup

Cần biết:

- Backup gần nhất có hợp lệ không?
- Restore mất bao lâu?
- Có PITR không?
- Writes sau backup xử lý thế nào?
- Recovery được luyện tập trên staging chưa?
- Ai chịu trách nhiệm quyết định restore?

### 45.3. Checksum mismatch là sự kiện cần điều tra

Đừng dùng tool repair/tắt validation chỉ để làm pipeline xanh mà không hiểu vì sao mã migration thay đổi so với history.

---

## 46. Môi trường database cần được nhận diện rõ

Một câu lệnh migration chạy đúng nhưng vào **sai database** vẫn là incident.

### 46.1. Fingerprint trước khi chạy

Ghi:

```text
Environment: staging / production
DBMS + version
Host/cluster/instance identity
Database/schema name
Migration account
Expected previous version
Pending migration list
Application release
Backup/snapshot reference
Approval ticket/change ID
```

### 46.2. Không tin mỗi connection URL string

DNS, secret rotation, proxy routing và database aliases có thể khiến environment target khác dự kiến. Trong hệ thống nghiêm ngặt, xác minh thêm DB identity/version/schema bằng read-only queries phù hợp.

### 46.3. Tách schema khi multi-tenancy

Nếu mỗi tenant có schema riêng, migration runner cần biết:

- Có bao nhiêu tenant schemas?
- Chạy tuần tự/song song ra sao?
- Tenant nào migration failed?
- History tracking per schema hay shared?
- App rollout có cần đợi tất cả tenants?
- Tenant mới được bootstrap từ version nào?

Không suy một migration history table toàn cụm tự đại diện chính xác cho mọi tenant schemas.

---

## 47. Migration naming và repository conventions

Ví dụ Flyway:

```text
V1__create_customers.sql
V2__add_customer_status.sql
V3__enforce_customer_status.sql
V4__add_index_customers_status.sql
R__refresh_customer_reporting_view.sql
```

### 47.1. Tên nên mô tả intent

`V2__fix.sql` khó review hơn `V2__add_customer_status.sql`.

### 47.2. Mỗi migration nên có phạm vi hợp lý

Một migration 2.000 dòng trộn customer status, payment schema và full data cleanup rất khó rollback/debug. Tách khi cần để đánh giá dependency/locking và owner.

### 47.3. Không chia nhỏ đến mức mất transaction intent

Một data transform có các bước phải atomic có thể nên nằm cùng một migration/transaction khi DBMS hỗ trợ. Tách file chỉ vì “ít dòng” không phải tiêu chí chính.

### 47.4. Không thay đổi thứ tự theo filename ngẫu nhiên

Migration tools có rules về versions/order/locations. Cần tuân thủ naming conventions chính thức của tool và version đang dùng, không viết script ad hoc làm cùng một directory chứa những file không được nhận.

---

## 48. So sánh các chế độ triển khai thực tế

| Môi trường | Nguồn schema | DDL tự động từ ORM | Migration runner | ORM validate |
|---|---|---|---|---|
| Unit tests thuần Java | Không cần DB | Không | Không | Không |
| Demo disposable DB | JPA/Hibernate metadata | Có thể `create-drop` | Tùy mục đích | Không bắt buộc |
| Repository mapping tests | Disposable schema | Có thể `create-drop` | Có thể tắt cho test này | Tùy |
| Migration integration test | Versioned SQL/changeSets | **Không** | Có | Có |
| Staging | Migrations | Không | Có | Có |
| Production | Migrations | **Không create/update/drop** | Có, kiểm soát quyền | `validate` hoặc `none` theo policy |
| Historical upgrade rehearsal | Old DB snapshot + pending migrations | Không | Có | Có sau upgrade |

Đây là một mô hình kiến trúc điển hình, không phải bắt buộc cho mọi sản phẩm. Với project nhỏ, cấu hình có thể đơn giản hơn, nhưng vẫn phải tránh destructive schema generation trên database cần giữ.

---

## 49. Hibernate validate và khả năng “mismatch”

Giả sử entity mới:

```java
@Column(name = "status", nullable = false, length = 20)
private String status;
```

nhưng migration chưa chạy.

Với Hibernate `ddl-auto=validate`, startup có thể báo thiếu cột `status`. Đây là điều tốt: ứng dụng mới không chạy với schema chưa sẵn sàng.

### 49.1. Hành vi validation có giới hạn

Một số mismatches về column type/name sẽ được phát hiện tùy provider/dialect; nhưng đừng dùng validate thay cho:

- Kiểm tra index performance.
- Kiểm tra foreign key violations.
- Kiểm tra unique/partial constraints.
- Kiểm tra default values.
- Kiểm tra data backfill.
- Kiểm tra trigger/function/view definitions.
- Kiểm tra row-level security.

### 49.2. Validate trong CI tạo guardrail

Chạy migrations rồi boot JPA validate trong CI giúp đảm bảo ít nhất model và schema có cơ hội tương thích. Nếu fail, nên sửa migration hoặc mapping, **không đổi validate thành update** để test pass.

### 49.3. Migrations là source of truth, annotations là contract của code

Migrations mô tả cách database biến đổi. Entity mappings mô tả cách code mong đợi đọc/ghi. Chúng phải tương thích, nhưng không cần được sinh tự động 100% từ cùng một nguồn.

---

## 50. Thêm @Version sau khi hệ thống đã có dữ liệu

Model cũ chưa có optimistic version:

```java
@Entity
public class Product {
    @Id
    private Long id;

    private String name;
}
```

Model mới:

```java
@Version
@Column(name = "version", nullable = false)
private long version;
```

### 50.1. Sinh schema mới không thấy vấn đề

Hibernate có thể tạo cột `version` ngay trong test DB sạch.

### 50.2. Migration phải backfill

Ví dụ PostgreSQL:

```sql
ALTER TABLE products
ADD COLUMN version BIGINT;

UPDATE products
SET version = 0
WHERE version IS NULL;

ALTER TABLE products
ALTER COLUMN version SET NOT NULL;
```

Sau đó, mọi ORM writers cần tuân thủ version check/increment semantics.

### 50.3. Native/bulk updates

Nếu external writers sửa Products mà không cập nhật version, optimistic locking có thể không bảo vệ toàn bộ write paths. Migration thêm cột chỉ là bước đầu; application data access strategy cũng phải được điều chỉnh.

---

## 51. Di trú dữ liệu enum và mapping JPA

Một trường hợp:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status")
private OrderStatus status;
```

Nếu enum thay từ `NEW, DONE` thành `PENDING, COMPLETED`, database cũ chứa `NEW/DONE`.

### 51.1. Tạo schema mới không kiểm tra legacy enum values

Test create-drop insert chỉ `PENDING/COMPLETED` sẽ pass; production SELECT row chứa `NEW` có thể fail khi provider convert string thành enum.

### 51.2. Migration data cần rõ

```sql
UPDATE orders
SET status = 'PENDING'
WHERE status = 'NEW';

UPDATE orders
SET status = 'COMPLETED'
WHERE status = 'DONE';
```

Đây là ví dụ cùng một cột string; kiểm tra mọi writer, query và old application compatibility trước khi đổi enums thật.

### 51.3. Expand nếu app old/new đồng thời

Một số trường hợp cần code tạm chấp nhận cả old/new values rồi mới chuyển data; không thể luôn đổi enum và UPDATE trong một lệnh mà mọi app version cũ vẫn hoạt động.

---

## 52. Di trú quan hệ @ManyToOne và foreign key

Giả sử thêm:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "preferred_store_id",
    nullable = false)
private Store preferredStore;
```

Một database có Customers cũ không có `preferred_store_id`.

### 52.1. Migration cần quyết định dữ liệu hợp lệ

Không thể gán mọi Customer vào Store ID=1 nếu nghiệp vụ không cho phép. Cần default business rule, manual reconciliation hoặc trạng thái tạm nullable.

### 52.2. Phương án tuần tự

1. Thêm `preferred_store_id` nullable.
2. Tạo/index các Store records cần thiết.
3. Backfill theo business mapping.
4. Kiểm tra orphan/non-null coverage.
5. Thêm FK.
6. Enforce NOT NULL khi dữ liệu và old writers đã sẵn sàng.
7. Cập nhật JPA mapping/repository queries.

### 52.3. Cascades không phải migration

Thêm `cascade=CascadeType.PERSIST` không tự chuyển dữ liệu cũ hoặc sửa foreign keys. Mapping lifecycle và schema evolution là hai trách nhiệm khác.

---

## 53. Một schema test có thể giữ dữ liệu từ lần chạy trước?

Nếu test local muốn chạy nhanh, có thể dùng database cố định với migration runner thay vì tạo lại mỗi lần. Nhưng phải kiểm soát:

- Test isolation.
- Dữ liệu được reset thế nào.
- Migration history có nhất quán không.
- Fixtures có cạnh tranh giữa parallel tests không.
- Schema version có bị lệch giữa developers không.

### 53.1. Không dùng chung staging DB cho automated destructive tests

Một test `create-drop` có thể xóa tables mà người khác đang dùng. Dùng database/schema tạm thời, unique name hoặc container riêng.

### 53.2. Test parallelism

Nếu nhiều test suites cùng drop/create cùng database, dễ race. Dùng contexts/containers/schemas tách biệt hoặc lock test database có kiểm soát.

### 53.3. Test data fixtures không phải migration production

Seed data như 10 Customers giả nên ở test fixture; dữ liệu reference bắt buộc của production cần migration/seed policy khác. Không trộn account test vào database production.

---

## 54. Kiểm thử DDL được sinh từ metadata

Một bài thực hành có thể:

1. Khởi động EntityManagerFactory trên test database mới.
2. Cấu hình schema create/drop.
3. Inspect bảng/cột bằng database metadata.
4. Persist entity.
5. Thử constraints.
6. Đóng EntityManagerFactory để cleanup.
7. So sánh quan sát với annotations.

### 54.1. Những trường hợp đáng thử

- `@Column(nullable=false)`.
- `@Column(unique=true)`.
- `@JoinColumn`/FK.
- `@ElementCollection`/collection table.
- `@Embedded`/`@AttributeOverride`.
- `@Version`.
- `@Inheritance` strategy.
- Naming strategies.
- Enum/Instant/BigDecimal mapping.

### 54.2. Không chấm schema quality chỉ bằng “Hibernate tạo được”

Một provider tạo thành công table không bảo đảm constraints/indexes/business-specific requirements đủ cho production. Test này xác nhận **mapping generatability**, không chứng nhận migration production.

---

## 55. Kiểm thử migrations bằng assertions

Sau khi Flyway/Liquibase chạy, test cần không chỉ gọi repository.

Ví dụ kiểm tra null coverage:

```java
Long nullCount = em.createQuery(
    """
    SELECT COUNT(c)
    FROM Customer c
    WHERE c.status IS NULL
    """,
    Long.class)
    .getSingleResult();

assertEquals(0L, nullCount);
```

Đoạn code này thuộc entity phiên bản mới có `status` mapped.

### 55.1. Có thể dùng SQL trực tiếp để test constraints

Nếu muốn biết NOT NULL thực sự tồn tại ở DB, một JPA query “không tìm thấy null row” chưa đủ: database vẫn có thể cho phép INSERT NULL sau này. Cần:

- Query metadata/DDL catalog.
- Negative insert test trong transaction riêng và rollback.
- Schema assertion library hoặc SQL theo DBMS.

### 55.2. Negative tests

Thử cố INSERT một Customer thiếu status bằng JDBC trong DB test đã migrate và xác nhận DB từ chối theo constraint. Không chạy thử kiểu này trên production data.

### 55.3. Test mutation path

Sau migration, còn cần thử INSERT/UPDATE từ application mới, optimistic versioning, relations và rollback. Schema đúng nhưng mapping sai vẫn có thể tạo SQL lỗi.

---

## 56. Một test nâng cấp theo nhiều releases

Giả lập:

```text
Step 1:
  Apply migrations only up to V1.
  Insert legacy Customers.
  Assert V1 app works.

Step 2:
  Apply V2.
  Assert V1 app still works if compatibility required.
  Assert new column/default present.

Step 3:
  Run backfill.
  Assert legacy rows have status.

Step 4:
  Boot transitional app mapping.
  Insert/update data.

Step 5:
  Apply V3 after old writers retired.
  Assert constraints.

Step 6:
  Boot strict app version.
  Run repository/service tests.

Step 7:
  Run migration runner again.
  Assert no pending changes/repeated data mutation.
```

### 56.1. Thứ tự này cần test tool phù hợp

Flyway có khả năng chỉ apply tới một target version theo cấu hình/API, Liquibase có contexts/tags/labels/other mechanisms. Cách gọi cụ thể phụ thuộc version/tool, nhưng **test upgrade path** là mục tiêu chính.

### 56.2. Không phải mọi migration đều backward-compatible

Một số changes buộc downtime/maintenance window. Khi không thể giữ rolling compatibility, phải nói rõ và đưa kế hoạch shutdown/migrate/start có backup/verification phù hợp.

---

## 57. Multi-service cùng dùng một database

Nếu nhiều microservices dùng chung schema, migrations cần ownership rõ.

### 57.1. Mỗi service tự ALTER cùng bảng là rủi ro

Service A xóa cột Service B vẫn dùng; mỗi service có migration history riêng nhưng physical schema chung. Một deployment thành công riêng lẻ có thể phá service khác.

### 57.2. Ownership contract

Có thể:

- Một service/database owner chịu trách nhiệm schema.
- Dùng migration repository chung.
- Chia schema per service.
- Có cross-team compatibility review.
- Quản lý data contracts khi chia sẻ tables.

### 57.3. Rollout theo producer/consumer order

Nếu Service A ghi dữ liệu mới, Service B đọc, cần đảm bảo B có thể đọc schema/value mới. Migration DDL không tự quản lý mọi API/data contract.

---

## 58. Các yếu tố vận hành production

Một migration có thể đúng về SQL nhưng vẫn gây incident vận hành.

### 58.1. Backup

Xác minh backup/PITR phù hợp trước destructive operations. “Backup enabled” không có nghĩa restore đã được kiểm chứng.

### 58.2. Monitoring

Theo dõi DB CPU, IO, replication lag, locks, active transactions, connection pool, query latency, errors.

### 58.3. Migration duration

Đo trên representative data size. Không suy từ developer laptop có 100 rows sang production có hàng triệu rows.

### 58.4. Abort/continue decision

Định nghĩa trước khi nào stop migration, ai phê duyệt, xử lý incomplete state thế nào. Không để pipeline tự retry destructive SQL vô hạn.

### 58.5. Deployment markers

Ghi timestamp, migration version, app version và change ticket vào observability system để điều tra sau deploy.

---

## 59. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test pass nhưng production startup lỗi missing column | Chỉ dùng ORM create-drop, quên migration | Thêm migration integration tests |
| Production mất tables sau restart | Destructive ddl-auto mode trỏ nhầm DB | Ngừng destructive modes, tách quyền và profiles |
| `hbm2ddl.auto=update` không rename được cột | Không biết intent/data transform | Migration explicit |
| Hibernate validate fail sau Flyway | Mapping/schema khác hoặc migrations chưa chạy | Kiểm tra order/history/DDL |
| Migration V2 checksum mismatch | Có người sửa file đã áp dụng | Điều tra, dùng new version |
| Chạy lại V1 tạo table lỗi | History bị mất hoặc baseline sai | Khôi phục history/baseline có kiểm chứng |
| App cũ lỗi sau rename column | Không có expand/contract | Tách releases/dual-write |
| Thêm NOT NULL trên bảng có nulls lỗi | Chưa backfill | Backfill + verify trước |
| Add UNIQUE constraint fail | Dữ liệu duplicate | Data cleanup + integrity tests |
| FK creation fail | Orphan rows | Reconcile trước khi enforce |
| Migration chạy quá lâu | Massive update/index lock | Batch/online DDL plan |
| “Có migration” nhưng SQL fail ở production | Test trên H2 khác dialect | Test target DBMS |
| App version mới đọc enum cũ lỗi | Chưa data migrate values | Transitional code + data conversion |
| Staging nhanh hơn production nhiều | Schema drift/index thủ công | Schema diff/standardize |
| Migration job báo failed nhưng cột đã có | DBMS DDL không rollback như dự kiến | Kiểm tra actual state trước retry |
| Rolling deploy lỗi dù migration chạy thành công | App compatibility chưa thiết kế | Compatibility matrix |
| Tắt validate để app lên được | Che mapping/schema mismatch | Sửa migrations/mapping |
| Liquibase/Flyway cùng sửa cùng schema | Hai sources of truth | Chọn/điều phối một migration owner |
| App không có quyền ALTER | Quyền runtime bị hạn chế | Đúng chủ đích; chạy migration bằng account phù hợp |
| Production chạy config test | Profile/secret/environment isolation sai | Startup guardrails + least privilege |
| DB schema khác migration history | Manual hotfix/drift | Review/schema diff và migration reconciliation |
| Migration lớn tạo replication lag | Backfill/DDL nặng | Throttle, batch, monitor |
| Rollback deploy không chạy được | DB schema đã contract quá sớm | Expand/contract + rollback plan |
| SQL default không gán cho writer explicit NULL | Default chỉ khi column omitted theo semantics | Fix write paths/backfill/constraint |
| Tạo table bằng ORM nhưng view/function mất | ORM metadata không quản lý mọi DB object | Migrations chứa DB objects khác |
| Insert test users vào prod | Seed script lẫn môi trường | Separate test fixtures/reference data |

---

## 60. Bài thực hành A — Hibernate schema generation cho test

1. Tạo một persistence unit với Customer entity.
2. Dùng database tạm thời.
3. Cấu hình Hibernate `ddl-auto=create-drop`.
4. Boot EntityManagerFactory.
5. Kiểm tra bảng customers xuất hiện.
6. Persist một Customer.
7. Flush/commit và đọc lại.
8. Đóng EntityManagerFactory.
9. Kiểm tra schema được cleanup theo cơ chế provider/test DB.
10. Giải thích vì sao không chạy mode này trên production.

## 61. Bài thực hành B — Standard Jakarta schema-generation properties

1. Cấu hình `jakarta.persistence.schema-generation.database.action`.
2. Thử `create` trên DB trống.
3. Thử `drop-and-create` trong DB **chỉ chứa dữ liệu test**.
4. Cấu hình `scripts.action=create` và `create-target`.
5. Quan sát SQL được sinh.
6. So sánh DB action với script action.
7. Phân biệt các mode chuẩn JPA với Hibernate `update/validate`.
8. Giải thích vì sao generated create SQL không phải upgrade script.

## 62. Bài thực hành C — Flyway fresh install

1. Thêm Flyway vào project Spring Boot.
2. Tạo `V1__create_customers.sql`.
3. Dùng database trống, tắt ORM schema generation.
4. Chạy Flyway migrate.
5. Kiểm tra history table.
6. Boot Hibernate `ddl-auto=validate`.
7. Persist/đọc Customer.
8. Chạy migration runner lại và quan sát không có pending version.
9. Không sửa V1 đã áp dụng.

## 63. Bài thực hành D — Thêm cột status

1. Tạo database với V1 và hai Customer rows.
2. Thêm `V2__add_customer_status.sql`.
3. Thực thi ALTER ADD COLUMN nullable.
4. Đặt DEFAULT cho future rows.
5. Backfill Customers cũ.
6. Kiểm tra số rows status NULL.
7. Thử old writer INSERT không liệt kê status.
8. Viết application transitional logic.
9. Thử constraint enforcement ở V3.
10. Giải thích vì sao một DDL mới không đủ.

## 64. Bài thực hành E — Test upgrade từ V1

1. Tạo PostgreSQL container.
2. Áp migration tới V1.
3. Insert legacy rows có giá trị đặc biệt.
4. Áp V2, chạy backfill.
5. Đọc lại rows; xác nhận status đúng.
6. Áp V3.
7. Kiểm tra NOT NULL và CHECK constraint.
8. Boot JPA mapping mới, validate.
9. Test insert/update.
10. So sánh với create-drop test và ghi điểm khác biệt.

## 65. Bài thực hành F — Chứng minh `update` không giải quyết rename

1. Tạo entity V1 có `fullName`/column `full_name`.
2. Tạo database và dữ liệu.
3. Đổi mapping sang `displayName`/column `display_name`.
4. Quan sát Hibernate schema update trong sandbox.
5. Xem dữ liệu cũ có được di chuyển đúng không.
6. Viết migration explicit kiểu expand/dual-write/backfill/contract.
7. Kiểm tra old/new application compatibility.
8. Giải thích vì sao metadata không diễn đạt rename intent.

## 66. Bài thực hành G — Checksum và lịch sử

1. Apply V1/V2 vào DB test.
2. Ghi migration history.
3. Cố sửa nội dung V2.
4. Chạy migration validation.
5. Quan sát checksum mismatch theo tool/version.
6. Khôi phục V2 nguyên bản.
7. Tạo V3 mới để thực hiện change tiếp.
8. Ghi quy tắc không edit applied versioned migrations.

## 67. Bài thực hành H — Constraint migration

1. Tạo records có status NULL.
2. Thử thêm NOT NULL trực tiếp.
3. Ghi failure.
4. Backfill.
5. Thêm NOT NULL.
6. Thử insert NULL bằng JDBC trong DB test.
7. Thử value không thuộc CHECK constraint.
8. Kiểm tra rollback của negative tests.
9. Giải thích khác biệt validation ứng dụng và database constraint.

## 68. Bài thực hành I — Unique email migration

1. Tạo bảng Customer chưa có unique constraint.
2. Thêm hai emails trùng nhau.
3. Chạy query phát hiện duplicate.
4. Định nghĩa business rule xử lý duplicates.
5. Thực hiện cleanup bằng script/test data.
6. Thêm unique constraint.
7. Kiểm tra INSERT duplicate bị từ chối.
8. So sánh raw uniqueness và case-insensitive uniqueness.
9. Ghi ảnh hưởng indexes/collation.

## 69. Bài thực hành J — Foreign key và orphan rows

1. Tạo Customers và Orders.
2. Insert Order tham chiếu Customer ID không tồn tại trong DB test.
3. Query phát hiện orphan rows.
4. Thử thêm FK.
5. Ghi failure.
6. Chọn cleanup/reconciliation policy.
7. Thêm FK thành công.
8. Test DELETE parent behavior.
9. Phân biệt database FK actions với JPA cascade.

## 70. Bài thực hành K — PostgreSQL index concurrently

1. Tạo bảng đủ lớn trong database test.
2. Thử index creation thông thường.
3. Đo blocking/latency.
4. Thử `CREATE INDEX CONCURRENTLY`.
5. Quan sát yêu cầu non-transactional execution.
6. Cấu hình migration runner phù hợp cho statement này.
7. Ghi failure/cleanup plan.
8. Không áp cú pháp PostgreSQL cho các DBMS khác.

## 71. Bài thực hành L — Rollback app trong schema expanded

1. Giữ schema v1 và app v1.
2. Apply migration thêm cột status với default.
3. Deploy app v2 transitional.
4. Giả lập lỗi app v2.
5. Rollback app về v1 nhưng **không drop status**.
6. Kiểm tra app v1 còn hoạt động.
7. Sửa app v2 rồi deploy lại.
8. Enforce constraint sau khi old writers đã ngừng.
9. Ghi compatibility matrix.

## 72. Bài thực hành M — Schema drift

1. Apply V1–V3.
2. Tạo index bằng SQL thủ công trong một DB test.
3. So sánh migration history của hai DB test giống version.
4. So sánh physical schema metadata.
5. Ghi drift.
6. Đưa index thay đổi thành migration được review.
7. Đánh giá cách reconcile nếu index đã tồn tại ở một environment.
8. Giải thích vì sao history version giống nhau chưa đủ.

## 73. Bài thực hành N — Multi-tenant schema migration

1. Tạo hai schemas tenant_a và tenant_b.
2. Apply V1 cho mỗi tenant.
3. Ghi migration history per tenant theo cấu hình tool.
4. Áp V2 cho tenant_a.
5. Giả lập failure khi áp V2 cho tenant_b.
6. Xác định per-tenant status.
7. Kiểm thử app routing tới tenant tương ứng.
8. Thiết kế retry/recovery không chạy lại bừa bãi.
9. Ghi coordination và rollout policy.

## 74. Bài thực hành O — Quy trình CI tổng hợp

1. Unit tests không DB.
2. Mapping tests dùng disposable create-drop schema.
3. Migration fresh-install suite dùng PostgreSQL container.
4. Migration upgrade suite từ V1 legacy snapshot.
5. Hibernate validate sau migrations.
6. Data invariant assertions.
7. Migration checksum validation.
8. SQL schema/index checks.
9. Staging rehearsal với representative data.
10. Production approval checklist và post-deploy monitoring.

---

## 75. Checklist trước khi merge migration PR

| Câu hỏi | Cần xác nhận |
|---|---|
| Thay đổi entity đã có migration tương ứng? | Có |
| Migration có version/tên rõ? | Có |
| Applied migration có bị sửa? | Không, hoặc xử lý theo policy có review |
| Schema hiện tại của từng environment được biết? | Có |
| Fresh install từ empty DB chạy được? | Có |
| Upgrade từ schema cũ chạy được? | Có |
| Dữ liệu legacy đã được xét? | Có |
| Backfill có invariant rõ? | Có |
| Backfill có idempotency/batch strategy? | Nếu cần |
| App old/new compatibility đã xét? | Có |
| Có cần expand/contract? | Đánh giá |
| Có destructive DDL? | Phải review đặc biệt |
| Thay cột có làm mất data? | Đã có plan |
| Lock level/duration đã được đánh giá? | Có |
| Index creation có online strategy phù hợp? | Nếu cần |
| Transactional DDL semantics được biết? | Có |
| DBMS/version/dialect được xác nhận? | Có |
| Migration tested trên production-like DB? | Có |
| Unique/FK/NOT NULL data validation? | Có |
| Migrations chạy trước JPA validate? | Có |
| Hibernate `ddl-auto` không destructive ở prod? | Xác nhận |
| Migration runner credentials giới hạn? | Có |
| App runtime credentials không DDL tùy tiện? | Có |
| History/checksum được theo dõi? | Có |
| Schema drift được xem xét? | Có |
| Có backup/restore plan? | Có |
| Rollback/forward-fix plan? | Có |
| DB metrics/alerts sẵn sàng? | Có |
| Release rollout order rõ? | Có |
| Multi-tenant/shared DB ownership rõ? | Nếu liên quan |
| Post-deploy smoke test/data checks có? | Có |
| Truy vấn JPA/SQL mới có test? | Có |

---

## 76. Các ngộ nhận phổ biến

### 76.1. “Hibernate đã có update, vậy không cần Flyway”

Không. Hibernate update không lưu lịch sử migration có kiểm soát và không biết đầy đủ ý định data transformation, rename, backfill, rolling compatibility hay rollback.

### 76.2. “create-drop chỉ ảnh hưởng test vì tên mode có drop lúc kết thúc”

Không. Nó có thể gây mất dữ liệu nếu trỏ vào DB cần giữ. Mode không biết môi trường của bạn là production hay test.

### 76.3. “Entity @Column(nullable=false) tự tạo dữ liệu cho rows cũ”

Không. Mapping annotation không phải data backfill policy.

### 76.4. “Hibernate validate bảo đảm mọi constraint/index đều đúng”

Không. Schema validation có phạm vi nhất định, không thay thế physical schema/data integrity checks.

### 76.5. “Thêm enum value trong Java không cần migration”

Chưa chắc. Database có thể có CHECK constraint/native enum type cần cập nhật; data cũ có thể chứa values đã bị rename.

### 76.6. “Migration tạo table mới và migration ALTER table chỉ khác SQL”

Không. ALTER trên bảng có dữ liệu còn liên quan availability, locks, legacy rows và compatibility.

### 76.7. “Một migration thành công ở H2 chắc chạy trên PostgreSQL”

Không. DDL syntax, transactional behavior, types và constraints khác nhau.

### 76.8. “Migrations nên chạy ở mọi app replica cùng lúc cho nhanh”

Không nên giả định như vậy. Migration runner cần coordination/ownership; nhiều replicas thực thi DDL đồng thời có thể gây contention và race tùy setup.

### 76.9. “Sửa script V1 là đủ, các database cũ sẽ tự áp lại”

Không. Versioned migrations đã áp thường không chạy lại như một script mới; checksum/history có thể báo lỗi.

### 76.10. “Backup tồn tại nghĩa rollback được ngay”

Không. Restore phải được kiểm thử, có RTO/RPO và xử lý writes sau snapshot.

### 76.11. “DROP old column ngay sau deploy app mới là an toàn”

Không nếu còn old replicas, background jobs, reporting queries hoặc external consumers sử dụng cột đó.

### 76.12. “Data backfill cần chạy trong một transaction duy nhất”

Không phải luôn đúng. Bảng lớn có thể cần batches để giảm locks/log/replication impact, kèm checkpoint/invariants.

### 76.13. “Unique constraint sẽ tự sửa duplicate data”

Không. Constraint sẽ thường từ chối dữ liệu vi phạm; cleanup cần business policy.

### 76.14. “Migration version đúng nghĩa physical schema không có drift”

Không. Manual DDL, tool misconfig hoặc partial failures có thể tạo drift.

### 76.15. “SQL generated từ JPA là production migration tốt nhất”

Chưa chắc. SQL tạo schema rỗng không chứa toàn bộ lộ trình data transformation, zero-downtime và vendor-specific tuning.

### 76.16. “Nếu cần rollback app thì chạy DOWN migration luôn”

Không mặc nhiên. DOWN có thể làm mất dữ liệu do app mới đã ghi hoặc không đảo ngược data transform. Expand/contract + forward-fix/restore policy phải được lập kế hoạch.

### 76.17. “DEFAULT tự áp khi writer gửi NULL”

Không. Trong SQL thông thường, default được áp khi cột omitted hoặc dùng DEFAULT expression; explicit NULL vẫn có thể là NULL, phụ thuộc constraint/DB semantics.

### 76.18. “App startup thành công là migration đúng”

Không. Data invariants, index performance, constraints, permissions và business queries vẫn cần test.

### 76.19. “Một database thật dùng Testcontainers thì không cần staging”

Không. CI container giúp kiểm tra dialect/migrations, nhưng không thay thế rehearsal với dữ liệu lớn, topology và production-like load.

### 76.20. “Một annotation @Index mới sẽ tự tạo index ở production khi ddl-auto=validate”

Không. Validate không thực thi CREATE INDEX; migration phải quản lý thay đổi physical schema.

---

## 77. Câu hỏi ôn tập

1. Schema generation và schema migration khác nhau ở mục tiêu nào?
2. Vì sao tạo schema rỗng không giải quyết data backfill?
3. JPA mapping metadata bao gồm những loại thông tin gì?
4. Những database features nào thường cần SQL migration ngoài JPA annotations?
5. `jakarta.persistence.schema-generation.database.action` có các mode nào?
6. `update` có phải giá trị chuẩn của database.action không?
7. `scripts.action` khác `database.action` ở đâu?
8. Vì sao generated DDL không tự là migration upgrade?
9. `hibernate.hbm2ddl.auto=create-drop` có phù hợp production không?
10. `hibernate.hbm2ddl.auto=validate` làm gì?
11. Vì sao `update` không thể đoán rename column intent?
12. Spring Boot `spring.jpa.hibernate.ddl-auto` thuộc tầng nào?
13. Tại sao nên khai báo rõ schema policy ở production?
14. Flyway versioned migration có lợi ích gì?
15. Checksum migration phát hiện vấn đề gì?
16. Vì sao không sửa V2 đã chạy production?
17. Liquibase changeSet khác một file SQL tùy ý thế nào?
18. Nên dùng cả Flyway và Liquibase trên cùng schema không?
19. Migration history có ý nghĩa gì?
20. Schema drift là gì?
21. Baseline legacy database cần khảo sát điều gì?
22. Vì sao baseline không đồng nghĩa drop/create schema?
23. Add status NOT NULL vào bảng nhiều rows phải xử lý thế nào?
24. DEFAULT có thay thế backfill không?
25. Vì sao explicit NULL vẫn có thể vi phạm NOT NULL dù đã có DEFAULT?
26. Expand/migrate/contract gồm các bước chính nào?
27. Tại sao app old/new compatibility quan trọng trong rolling deployment?
28. Một rename column có thể phá app cũ thế nào?
29. Dual-write khi chuyển cột có rủi ro gì?
30. Data migration từ enum values cũ sang mới cần làm gì?
31. Khi đổi VARCHAR(100) thành VARCHAR(20), cần khảo sát dữ liệu gì?
32. Trước unique constraint cần chạy những queries nào?
33. Vì sao thêm FK có thể fail trên dữ liệu hiện có?
34. @ManyToOne có tự sửa orphan rows không?
35. @Version mới yêu cầu migration gì?
36. Vì sao bulk/native writers cần tuân thủ version policy?
37. Index creation có thể ảnh hưởng production writes ra sao?
38. PostgreSQL CREATE INDEX CONCURRENTLY có restriction transaction nào?
39. Transactional DDL có portable giống nhau giữa các DBMS không?
40. Vì sao migration fail giữa chừng có thể để lại partial schema?
41. Forward-fix và DOWN migration khác nhau như thế nào?
42. Vì sao rollback app không đồng nghĩa rollback database?
43. Khi nào cần restore từ backup?
44. Fresh-install test kiểm chứng điều gì?
45. Upgrade-path test kiểm chứng điều gì?
46. Vì sao create-drop test vẫn pass khi migration file thiếu?
47. H2 compatibility mode có thay thế PostgreSQL test không?
48. Testcontainers giúp ích như thế nào?
49. Spring `@DataJpaTest` có thể thay DataSource ngoài ý muốn ở đâu?
50. Vì sao cần apply migrations trước Hibernate validate?
51. Vì sao cần test data integrity sau migration?
52. Bảng lớn cần backfill theo batches lúc nào?
53. Backfill job idempotent có đặc tính gì?
54. Migration repeatable nên được dùng cho loại objects nào?
55. Chạy schema generation và Flyway cùng quản lý một bảng có rủi ro gì?
56. Runtime app nên có quyền DROP TABLE không?
57. Migration runner nên có quyền gì?
58. Một production migration runbook cần environment fingerprint nào?
59. Vì sao không thể chỉ dựa vào migration history để phát hiện mọi drift?
60. Multi-tenant schemas cần theo dõi migration version ra sao?
61. Khi app dùng shared DB, ai nên sở hữu migrations?
62. Một migration có thể đúng SQL nhưng gây outage vì sao?
63. Monitoring nào cần theo dõi khi index/backfill chạy?
64. Vì sao số dòng SQL không phản ánh lock severity?
65. Migration checksum mismatch cần xử lý theo thứ tự nào?
66. Những loại dữ liệu cũ nào nên có trong upgrade fixtures?
67. Một migration chạy lần hai có nên lặp data mutation không?
68. Cách phân biệt schema validate success và business invariant success?
69. Sau rollback app, schema nên giữ expanded columns vì sao?
70. Hãy thiết kế một migration từ V1 Customer đến V3 Customer mà dữ liệu không mất và các old writers được kiểm chứng.

---

## 78. Bảng ghi nhớ

| Nhu cầu | Công cụ/chiến lược thích hợp | Cần nhớ |
|---|---|---|
| Tạo database sạch cho test mapping | JPA/Hibernate `create/create-drop` | Chỉ DB disposable |
| Xuất DDL từ metadata để xem | JPA scripts generation | Không tự là upgrade migration |
| Không động đến schema ở runtime | `none` | Schema phải do nguồn khác quản lý |
| Kiểm tra mapping/schema khi boot | Hibernate `validate` | Không kiểm tra mọi constraint |
| Thay đổi schema có dữ liệu | Flyway/Liquibase | Version/history/checksum |
| Đưa legacy DB vào migration tracking | Baseline | Không bỏ qua khảo sát schema |
| Thêm cột bắt buộc | Expand → backfill → enforce | Old writers và NULLs |
| Rename/drop column không downtime | Expand/dual-write/contract | Compatibility matrix |
| Tạo index trên bảng lớn | Online DDL theo DBMS | Locks/transaction semantics |
| Dữ liệu lớn cần chuyển đổi | Batch backfill + checkpoints | Throttle/replication lag |
| Tạo schema từ zero bằng migrations | Fresh-install integration test | Khác ORM create-drop |
| Nâng schema cũ lên bản mới | Upgrade-path integration test | Legacy data fixtures |
| Test đúng SQL production | Target DBMS/Testcontainers | H2 không tương đương |
| Lược đồ bị sửa thủ công | Schema drift detection | History có thể vẫn báo đúng |
| Migrations đã áp | Immutable versioned scripts | Thêm migration mới |
| Migration fail giữa chừng | Inspect actual state + recovery plan | DDL rollback khác nhau |
| Cần quay lại ứng dụng cũ | Backward-compatible schema | Không DROP cột quá sớm |
| Chọn chiến lược lỗi | Roll-forward/backup/PITR | Kiểm thử restore |
| Bảo vệ production data | Least-privilege + profile guardrails | Không destructive auto-DDL |
| Đánh giá correctness | Schema + constraints + data checks | App boot chưa đủ |
| Đánh giá availability | Lock/time/perf rehearsal | Đừng chỉ xem SQL syntax |

### Sơ đồ quyết định cuối bài

```text
        Có database cần giữ dữ liệu không?
                 /                 \
               KHÔNG               CÓ
                |                   |
                v                   v
      Disposable test DB       Production/staging/
                |              shared persistent DB
                v                   |
       Có thể dùng ORM              v
      create / create-drop     Versioned migration
                |              Flyway / Liquibase
                |                   |
                v                   v
      Mapping/CRUD test      Review + compatibility
                |            + data migration
                |                   |
                v                   v
        Tạo lại từ zero       Apply pending steps
                |                   |
                v                   v
      Xóa test data OK       Validate schema/data
                |                   |
                +---------+---------+
                          |
                          v
              Integration tests cần gì?
                /                  \
                v                  v
       Kiểm tra mapping       Kiểm tra upgrade
       từ model hiện tại      từ schema cũ có data
                |                  |
                v                  v
       ORM schema test        Real migrations test
                |                  |
                +---------+--------+
                          |
                          v
            Production deployment gate
           backup / locks / approvals /
             health checks / monitoring
```

**Nguyên tắc cuối bài:** **Sinh lược đồ từ JPA metadata** tối ưu cho việc tạo nhanh cấu trúc mới, đặc biệt trong test database có thể xóa và dựng lại. **Di trú lược đồ có kiểm soát** tối ưu cho quá trình thay đổi database đã tồn tại, bảo toàn dữ liệu, lịch sử và khả năng vận hành qua nhiều phiên bản ứng dụng. `Hibernate ddl-auto=create-drop` và `update` không phải migration framework; `validate` là lớp kiểm tra bổ trợ, không phải lệnh sửa schema; Flyway/Liquibase giúp quản lý **các bước chuyển trạng thái có version/checksum**. Một pipeline JPA đáng tin nên có cả **mapping tests trên schema tạm** lẫn **integration tests chạy migrations thật từ schema cũ**, và chỉ đưa migration lên production sau khi đã đánh giá dữ liệu, tính tương thích, locks, backfill, backup và quy trình khắc phục sự cố.

