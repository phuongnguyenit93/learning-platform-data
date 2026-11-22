# Kiểm tra đồng bộ giữa migration, schema thực và metadata Hibernate

Trong dự án Java dùng JPA/Hibernate, cơ sở dữ liệu thường được thay đổi bằng **migration** (Flyway, Liquibase hoặc SQL migration tự quản lý), còn ứng dụng truy cập dữ liệu qua **entity mapping** và Hibernate metadata. Sau vài tháng phát triển, ba nơi mô tả cấu trúc dữ liệu có thể không còn đồng bộ:

1. **Migration scripts và migration history**: dự án dự định tạo, sửa, xóa bảng/cột/ràng buộc như thế nào, và các migration nào đã được áp dụng.
2. **Schema thực trong database**: những bảng, cột, kiểu dữ liệu, indexes, foreign keys, sequences, defaults, constraints đang tồn tại.
3. **Hibernate mapping metadata**: `@Entity`, `@Table`, `@Column`, `@JoinColumn`, `@Version`, `@Enumerated`, `@EmbeddedId`, naming strategy và các Hibernate-specific mappings mô tả điều ORM mong đợi.

Một ứng dụng có thể **khởi động thành công** nhưng vẫn có lỗi schema nghiêm trọng: cột đáng lẽ `NOT NULL` lại nullable, thiếu unique index, FK có hành vi xóa sai, sequence cấp ID không tương thích, enum lưu dưới representation khác, hoặc deployment A/B đang dùng những phiên bản schema khác nhau.

Vì vậy, kiểm tra đồng bộ không chỉ là bật:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Hibernate schema validation là lớp kiểm tra quan trọng nhưng **không phải bộ so sánh schema đầy đủ**. Flyway/Liquibase `validate` cũng không tự chứng minh schema thực đã giống hệt file migration. Bài học xây dựng một quy trình nhiều lớp: **kiểm tra migration history → áp migrations trên database trống tương đương production → Hibernate validate → kiểm tra constraints/indexes/defaults/sequence bằng metadata/SQL → chạy integration tests → giám sát drift trên môi trường thật**.

---

## 1. Hiểu ba nguồn thông tin khác nhau

Hình dung:

```text
Source code repository
  |
  +-- db/migration/V1__create_customers.sql
  |-- db/migration/V2__add_order_status.sql
  |-- db/migration/V3__add_fk.sql
  |
  +-- JPA entities:
      Customer.java
      PurchaseOrder.java
      OrderLine.java
          |
          v
    Hibernate Mapping Model
          |
          |      Migration runner (Flyway/Liquibase)
          |                  |
          v                  v
        Schema validation -> Database schema thực
                                  |
                                  +-- tables / columns
                                  +-- primary & foreign keys
                                  +-- nullability / unique
                                  +-- indexes / check constraints
                                  +-- sequences / identities
                                  +-- views / triggers / defaults
                                  +-- permissions / RLS / extensions
```

Ba khái niệm trả lời các câu hỏi khác nhau:

| Thành phần | Câu hỏi | Không tự bảo đảm |
| --- | --- | --- |
| Migration source | Chúng ta định thay đổi gì, theo thứ tự nào? | Database thật đã áp đúng và không bị sửa tay |
| Migration history | File/version nào được migration tool ghi nhận đã chạy? | Mọi table/index/constraint vẫn nguyên vẹn |
| Database schema thực | Cấu trúc vật lý đang có những gì? | ORM mapping và ứng dụng đang kỳ vọng giống vậy |
| Hibernate metadata | Entity/association/type mappings mong muốn điều gì? | Các constraint/index/default ngoài phạm vi validator đều đúng |
| Hibernate `validate` | Một phần mapping có khớp DB schema không? | Full semantic equivalence giữa migration, DB và code |
| Integration tests | Hành vi truy cập dữ liệu có đúng trên DB chạy thử không? | Môi trường production không có drift |

**Không có một lệnh duy nhất** thường đủ để xác nhận toàn bộ các góc nhìn này.

## 2. Những kiểu lệch schema thường gặp

Ví dụ đội phát triển đổi:

```java
@Column(name = "email", nullable = false, length = 320)
private String email;
```

nhưng database vẫn có:

```sql
email VARCHAR(255) NULL
```

Có ba khác biệt:

- Kỳ vọng Java cho phép tối đa 320 ký tự; DB chỉ có 255.
- Java mapping nói không nullable; DB lại cho `NULL`.
- Migration để đổi schema có thể chưa được chạy hoặc được viết không đầy đủ.

Một trường hợp khác:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", length = 30)
private OrderStatus status;
```

nhưng DB lưu `SMALLINT` từ mapping cũ `EnumType.ORDINAL`. Nếu runtime cố đọc một integer như tên enum, có thể lỗi conversion hoặc dữ liệu bị diễn giải sai.

Các loại drift tiêu biểu:

- Thiếu table/column/sequence.
- Sai column type, length, precision/scale, timezone.
- Sai `NULL`/`NOT NULL`.
- Thiếu/khác primary key, unique, FK, check constraint.
- Thiếu index, index columns/order, partial/expression index.
- Lệch sequence allocation/increment.
- Sai enum storage hoặc converter.
- Sai naming, schema/catalog, quoted identifiers.
- Trigger/default/generated columns khác kỳ vọng.
- Migration history bị chỉnh sửa, bỏ version hoặc áp ngoài thứ tự.
- Một database bị DBA/manual SQL sửa trực tiếp.
- Schema của test/H2 khác DB production.
- Rolling deployment khiến application version cũ và mới cùng truy cập schema đang thay đổi.

Mỗi nhóm cần phép kiểm chứng phù hợp; không phải nhóm nào cũng được `ddl-auto=validate` phát hiện.

## 3. Migration là lịch sử thay đổi, không phải ảnh chụp schema hiện tại

Migration kiểu Flyway thường có tên:

```text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__add_customer_status.sql
  V3__create_purchase_orders.sql
  V4__add_order_indexes.sql
```

Flyway quản lý trạng thái bằng schema history table, thông thường có tên `flyway_schema_history`.

Liquibase dùng changelog XML/YAML/JSON/SQL và các bảng metadata như `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.

Một migration history entry thường ghi:

- Version hoặc change set identifier.
- Tên script/description.
- Checksum.
- Thứ tự và thời điểm thực thi.
- Thành công/thất bại tùy tool/dialect.
- Context/label/author hoặc metadata tương ứng.

**History nói về việc đã chạy**, không phải mọi đối tượng schema còn nguyên vẹn sau đó.

Ví dụ: `V3` từng tạo FK, Flyway ghi nhận V3 đã áp dụng. Một DBA sau đó `ALTER TABLE ... DROP CONSTRAINT ...` trực tiếp. Flyway history vẫn có thể coi V3 hợp lệ; chỉ so checksums không phát hiện FK đã biến mất.

## 4. Một mô hình migration cụ thể

Giả sử PostgreSQL là production database.

**V1__create_customers.sql**

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_customers_email UNIQUE (email)
);
```

**V2__create_purchase_orders.sql**

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT pk_purchase_orders PRIMARY KEY (id),
    CONSTRAINT uk_purchase_orders_number
        UNIQUE (order_number),
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id),
    CONSTRAINT ck_purchase_orders_total_nonnegative
        CHECK (total >= 0)
);
```

**V3__add_order_lookup_indexes.sql**

```sql
CREATE INDEX idx_orders_customer_status
ON purchase_orders (customer_id, status);

CREATE INDEX idx_orders_status_id
ON purchase_orders (status, id);
```

Đây là PostgreSQL DDL minh họa: `GENERATED BY DEFAULT AS IDENTITY` và `TIMESTAMP WITH TIME ZONE` có cú pháp/semantics khác giữa DBMS.

Các entity sẽ được viết để phù hợp với những cột chính:

```java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Customer() {}

    public Long getId() { return id; }
}
```

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

enum OrderStatus {
    DRAFT, PAID, CANCELLED
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "order_number", nullable = false, length = 50)
    private String orderNumber;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Version
    @Column(nullable = false)
    private long version;

    protected PurchaseOrder() {}
}
```

**Lưu ý mapping:** `@Column(unique=true)` thể hiện unique intent cho schema generation, nhưng tên constraint thực tế do naming strategy/provider quyết định nếu không khai báo explicit `@UniqueConstraint`. Ví dụ DDL dùng tên `uk_customers_email`. `Instant` trên PostgreSQL/Hibernate hiện đại có JDBC mapping phụ thuộc Hibernate version, preferred SQL type và timezone settings; hãy xác nhận kiểu cột bằng integration test chứ không suy từ Java type một cách tuyệt đối.

## 5. Thay đổi entity phải có migration tương ứng

Một developer thêm field:

```java
@Column(name = "loyalty_tier", nullable = false, length = 20)
private String loyaltyTier;
```

Nếu chỉ merge code mà không tạo migration, database chưa có `loyalty_tier`.

Một migration phù hợp với bảng đã có dữ liệu phải xử lý cả **backfill**:

```sql
ALTER TABLE customers
ADD COLUMN loyalty_tier VARCHAR(20);

UPDATE customers
SET loyalty_tier = 'STANDARD'
WHERE loyalty_tier IS NULL;

ALTER TABLE customers
ALTER COLUMN loyalty_tier SET NOT NULL;
```

Với bảng cực lớn, việc thêm cột/backfill/constraint có thể cần triển khai nhiều pha để tránh lock kéo dài. Một migration đúng trên dataset test trống chưa chắc vận hành an toàn với hàng trăm triệu rows.

Không chỉ kiểm tra cột có tồn tại, mà phải xét:

- Existing rows có giá trị hợp lệ không?
- `NOT NULL` có áp được không?
- Business default là giá trị trong Java hay database default?
- Các phiên bản ứng dụng cũ có thể ghi data sau khi migration chạy không?
- Rollback/roll-forward khi deployment thất bại?

## 6. Database schema là nguồn sự thật khi thực thi

Khi SQL chạy, database thực thi ràng buộc vật lý:

```sql
INSERT INTO customers(email, display_name, created_at)
VALUES (NULL, 'An', CURRENT_TIMESTAMP);
```

Nếu column `email NOT NULL` trong DB, database từ chối dù entity Java không khai báo annotation gì.

Ngược lại, nếu mapping khai báo:

```java
@Column(nullable = false)
private String email;
```

nhưng DB column nullable, database vẫn có thể chấp nhận raw SQL ghi `NULL`, trừ khi có constraint thực sự.

**Annotation không thay thế DDL migration** trong kiến trúc migration-owned schema.

### 6.1. JPA mapping và database constraints có vai trò khác nhau

- Mapping giúp ORM dựng SQL, bind/extract values, quản lý quan hệ và một phần lifecycle.
- Database constraints bảo vệ integrity cho **mọi writers**, kể cả JDBC, ETL, admin scripts và services khác.
- Bean Validation như `@NotNull` được áp ở tầng validation theo cấu hình; không thay thế `NOT NULL` ở database.
- Hibernate schema validation không tự biến constraint mapping thành constraint DB.

Với dữ liệu quan trọng, phải dựa vào ràng buộc DB đúng và có test xác minh.

## 7. `ddl-auto=validate`: công cụ phát hiện drift ở tầng ORM

Với Spring Boot dùng Hibernate:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

hoặc Hibernate property ở môi trường tự bootstrap:

```properties
hibernate.hbm2ddl.auto=validate
```

Ý tưởng: khi Hibernate bootstrap `SessionFactory`, nó kiểm tra một số cấu trúc DB có tương thích với entity mappings không, thay vì tự tạo hoặc cập nhật schema.

Nếu thiếu table:

```text
Schema-validation: missing table [customers]
```

Nếu thiếu column:

```text
Schema-validation: missing column [loyalty_tier] in table [customers]
```

Nếu kiểu cột không khớp, có thể gặp lỗi dạng:

```text
Schema-validation: wrong column type encountered ...
```

Thông điệp và mức độ kiểm tra phụ thuộc Hibernate major version, dialect, JDBC metadata và naming strategy.

### 7.1. `validate` không sửa dữ liệu

```properties
spring.jpa.hibernate.ddl-auto=validate
```

không chạy ALTER TABLE để sửa DB. Nếu validation thất bại, ứng dụng có thể không khởi động, giúp phát hiện mismatch trước khi phục vụ traffic.

Đây là hành vi **fail-fast** hữu ích ở CI, staging và những môi trường production phù hợp.

### 7.2. Đừng dùng `update` làm cơ chế migration production

```properties
spring.jpa.hibernate.ddl-auto=update
```

cho phép Hibernate cố cập nhật schema dựa trên mapping. Nó không thay thế quy trình migration có lịch sử, review, backfill, rollback, locking, index migration và compatibility planning.

Đặc biệt, tự động `update` không phải một bộ diff ngữ nghĩa đầy đủ có thể xóa/sửa mọi constraint đúng cách. Trong production migration-owned:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

hoặc:

```properties
spring.jpa.hibernate.ddl-auto=none
```

với validation được chạy ở bước riêng tùy kiến trúc, thường hợp lý hơn.

### 7.3. So sánh các mode DDL

| Mode | Hành vi chính | Phù hợp |
| --- | --- | --- |
| `none` | Không schema management theo chế độ này | Production đã có migration pipeline |
| `validate` | Kiểm tra một phần schema theo metadata | Fail-fast khi startup/test |
| `create` | Tạo schema, có nguy cơ thay thế đối tượng hiện có | Database test tạm |
| `create-drop` | Tạo rồi drop khi SessionFactory đóng | Test cô lập, không dùng trên DB có dữ liệu quan trọng |
| `update` | Cố đồng bộ schema theo mapping bằng DDL | Development rất hạn chế; không thay migration production |

Chú ý: cấu hình Hibernate schema tooling còn có JPA schema-generation properties; tránh đặt hai nhóm cấu hình mâu thuẫn hoặc tự suy rằng một property của phiên bản khác có cùng precedence.

## 8. Hibernate `validate` không phải schema diff toàn diện

Đây là giới hạn quan trọng nhất của bài:

**Validator Hibernate chủ yếu phục vụ kiểm tra cấu trúc cần để ORM hoạt động**, không phải một bộ chứng minh mọi chi tiết database schema giống migration.

Tùy phiên bản/driver, validation có thể nhận ra:

- Bảng được mapping tồn tại hay không.
- Các cột cần thiết tồn tại hay không.
- Một số khác biệt kiểu JDBC/SQL.
- Sequence và increment/allocation tương thích trong một số cấu hình.

Nhưng không nên dựa vào `validate` như lớp duy nhất để bảo đảm:

- `NOT NULL`, `UNIQUE`, CHECK, foreign-key actions luôn đúng.
- Tên và cấu trúc đầy đủ của indexes.
- Triggers, views, row-level security policies.
- Database defaults và generated expressions.
- Collations, partial indexes, expression indexes.
- Privileges, grants, extensions.
- Migration checksum và thứ tự applied migrations.
- Dữ liệu cũ có phù hợp business invariants.
- Rolling upgrade compatibility giữa application versions.

Một startup `validate` xanh chỉ nghĩa là **những kiểm tra mà validator thực hiện đã qua**. Nó không có nghĩa DB chuẩn tuyệt đối.

## 9. Flyway `validate` kiểm tra lịch sử migration, không phải constraint hiện hữu

Với Flyway, khái niệm `validate` tập trung vào tính nhất quán giữa **migrations có trên classpath/filesystem** và **schema history**.

Những vấn đề có thể được phát hiện (tùy Flyway version/config):

- Migration đã apply nhưng file bị sửa làm checksum khác.
- File migration đã apply nhưng biến mất hoặc khác naming.
- Migration có version/metadata mâu thuẫn.
- Applied/pending/ignored/out-of-order trạng thái bất thường.
- Lịch sử migration có entry không tương ứng theo quy tắc tool.

Ví dụ luồng:

```text
Repository:
  V1, V2, V3
        |
        v
Flyway validate
        |
        +-- Đối chiếu scripts với flyway_schema_history
        |
        v
Flyway migrate (nếu có pending)
        |
        v
Database schema thực
```

**Flyway validate không đảm bảo** một DBA không DROP INDEX sau khi V3 đã thành công. History có thể vẫn hợp lệ trong khi schema đã drift.

### 9.1. Không sửa migration đã được áp dụng

Nếu một migration đã deploy:

```text
V2__create_purchase_orders.sql
```

thì sau đó không nên sửa nội dung V2 để “vá” lỗi trên production. Checksum mismatch là tín hiệu lịch sử đã bị thay đổi.

Thay vì sửa V2, thông thường tạo migration mới:

```text
V4__fix_order_status_constraint.sql
```

để mọi môi trường đi theo lịch sử tiến hóa có thể theo dõi.

### 9.2. Cẩn trọng với `repair`

Flyway `repair` có thể sửa metadata history/checksums trong một số tình huống. **Không dùng repair như lệnh mặc định khi checksum fail**, vì điều đó có thể che đi việc file migration bị chỉnh sửa trái phép hoặc môi trường đã drift.

Trước repair: xác định nguyên nhân, giữ audit trail, so migrations đã phát hành và schema thực; chỉ repair khi có quy trình review rõ ràng, hiểu chính xác tác dụng của lệnh theo Flyway version.

## 10. Liquibase validation và diff

Liquibase quản lý changelogs/changesets và bảng `DATABASECHANGELOG`.

Ví dụ changeset dạng XML:

```xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="add-loyalty-tier" author="team">
        <addColumn tableName="customers">
            <column name="loyalty_tier" type="varchar(20)"/>
        </addColumn>
    </changeSet>
</databaseChangeLog>
```

Thực tế còn phải backfill và áp `NOT NULL` sau khi có giá trị hợp lệ, theo DBMS/data volume.

Liquibase thường có:

- `validate` để xác nhận changelog có tính hợp lệ và các quy tắc changeset liên quan.
- `status` để xem pending changesets.
- `update` để apply changes.
- Các công cụ `diff`, `diff-changelog`/snapshot để so sánh hai database/schema theo khả năng hỗ trợ.

**Liquibase `validate` không đồng nghĩa luôn kiểm tra toàn bộ schema vật lý.** Nếu cần phát hiện drift thực giữa một reference database và target, cần chạy cơ chế schema diff/snapshot được cấu hình phù hợp, và review output.

### 10.1. Diff thường sinh nhiều “nhiễu”

Schema diff có thể thấy khác biệt không quan trọng do:

- Constraint names sinh tự động.
- Driver trả kiểu JDBC khác nhau.
- Default expressions tương đương nhưng viết khác.
- Schema/catalog khác.
- Index names thay đổi.
- Serial/identity/sequence representation.
- Collation/extension hoặc vendor metadata.

Do đó diff report là **đầu vào cho triage**, không phải migration script tự động an toàn 100%.

## 11. Startup order: migration trước, Hibernate validation sau

Khi chạy application, mong muốn:

```text
Acquire datasource
       |
       v
Run pending Flyway/Liquibase migrations
       |
       v
Validate Hibernate entity mapping against current DB schema
       |
       v
Build EntityManagerFactory successfully
       |
       v
Start serving requests
```

Trong Spring Boot, các auto-configuration hỗ trợ tích hợp với Flyway/Liquibase và các thành phần JPA theo lifecycle tương ứng. Cần kiểm tra configuration thật nếu ứng dụng tự cấu hình nhiều Datasources/EntityManagerFactories.

Ví dụ:

```properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
```

Khi migration runner phát hiện pending migration, nó áp dụng theo policy. Hibernate sau đó kiểm tra cấu trúc cần thiết. Nếu validation thất bại, startup fail-fast.

### 11.1. Không để Hibernate create schema trước Flyway

Nếu cấu hình sai:

```properties
spring.jpa.hibernate.ddl-auto=create
spring.flyway.enabled=true
```

Hibernate có thể tạo/đụng schema trong cùng lifecycle, gây xung đột quyền sở hữu giữa hai công cụ.

Chọn **một chủ sở hữu DDL** cho từng database/environment. Trong dự án migration-owned, Hibernate chỉ validate; migrations chịu trách nhiệm thay đổi schema.

### 11.2. Production có thể không chạy migration trong mỗi pod

Với nhiều replicas, có thể cần pipeline/job riêng chạy migrations trước app deployment, thay vì để tất cả pods tự cạnh tranh migration locks. Flyway/Liquibase có cơ chế lock riêng, nhưng kiến trúc deploy nên xác định ai là migration runner và lỗi migration làm hệ thống phản ứng thế nào.

Một lựa chọn:

```text
CI/CD:
  Build artifact
      -> Migration job (one controlled executor)
      -> Verify DB schema/version
      -> Deploy new application pods (ddl-auto=validate)
```

Cách khác dùng migration lúc startup cũng có thể phù hợp ở hệ thống nhỏ, miễn là locking, readiness và failure handling được thiết kế rõ.

## 12. Naming strategy: field Java không luôn bằng column DB

Entity:

```java
private String displayName;
```

có thể map thành `display_name` nếu dùng physical naming strategy phù hợp.

Nhưng chỉ thay đổi:

```properties
spring.jpa.hibernate.naming.physical-strategy=...
```

có thể khiến Hibernate kỳ vọng tên cột khác mà migrations không đổi.

Khái niệm:

```text
Java attribute
  displayName
       |
       v
Implicit logical name
       |
       v
PhysicalNamingStrategy
       |
       v
DB column
  display_name
```

Khi chuyển naming strategy hoặc Hibernate/Spring Boot major version, cần kiểm tra:

- Table/column names của tất cả entities.
- Join table/foreign-key columns.
- Embedded attribute names.
- Quoted identifiers và case folding.
- Schema/catalog defaults.
- Constraints/sequence names nếu tool generate chúng.

### 12.1. Dùng explicit names ở điểm dễ gây lệch

```java
@Column(name = "display_name", nullable = false)
private String displayName;

@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Không nhất thiết phải explicit mọi tên, nhưng với schema lâu đời/migrations SQL thủ công, explicit names giúp giảm phụ thuộc vào naming-strategy defaults.

## 13. Schema, catalog và `search_path`

Một table có thể tồn tại ở:

```text
public.customers
billing.customers
tenant_a.customers
```

Nếu Hibernate tìm sai default schema, validator có thể báo thiếu table dù bảng cùng tên tồn tại trong database.

Trong mapping:

```java
@Table(name = "customers", schema = "billing")
```

hoặc cấu hình:

```properties
hibernate.default_schema=billing
```

có thể chỉ rõ schema tùy kiến trúc. Với PostgreSQL, `search_path` cũng ảnh hưởng resolution của unqualified table names.

### 13.1. Không dùng schema khác ở Flyway và Hibernate một cách tình cờ

Flyway có thể apply migration vào `public`, còn Hibernate đang xác thực `billing.customers`. Cần thống nhất:

- Connection URL/schema.
- Flyway `schemas`, `defaultSchema` và history table location.
- Hibernate `default_schema`/`@Table(schema)`.
- Database user permissions.
- Multi-tenant schema mapping.

Một test có cùng JDBC URL nhưng khác `search_path` vẫn có thể tạo kết quả khó giải thích.

### 13.2. Quoted identifiers

PostgreSQL coi unquoted `CustomerData` là lowercase theo quy tắc identifier folding, nhưng `"CustomerData"` giữ chữ hoa/chữ thường.

Nếu migration viết:

```sql
CREATE TABLE "CustomerData" (...);
```

và Hibernate tìm `customerdata`, validator có thể không thấy table đúng.

Hạn chế dùng quoted mixed-case names nếu không có nhu cầu đặc biệt; trong dự án legacy cần khai báo mapping/quoting consistent.

## 14. Kiểu cột: tương thích ORM không chỉ là tên SQL

Một attribute:

```java
@Column(precision = 18, scale = 2)
private BigDecimal total;
```

có thể tương ứng:

```sql
NUMERIC(18, 2)
```

Nhưng nếu DB là:

```sql
NUMERIC(10, 0)
```

thì lưu tiền có phần lẻ có thể bị làm tròn/lỗi, và phạm vi số tiền nhỏ hơn dự kiến.

Các kiểu cần xét:

| Java/Hibernate mapping | DB representation thường gặp | Nguy cơ |
| --- | --- | --- |
| `String` + `length` | `VARCHAR(n)`, `TEXT`, `NVARCHAR` | Truncation, index length, encoding |
| `BigDecimal` + precision/scale | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Mất precision/scale, overflow |
| `Instant` | Timestamp, timestamp with timezone, UTC-normalized type | Offset/timezone interpretation |
| `LocalDate` | `DATE` | Timezone/conversion khi sai mapping |
| `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` hoặc tương đương | Mơ hồ timezone |
| `UUID` | UUID native, BINARY(16), VARCHAR(36) | Driver/dialect/extraction |
| `Boolean` | BOOLEAN/BIT/SMALLINT/CHAR | Representation/converter mismatch |
| `Enum` | String/ordinal/native enum | Giá trị cũ không tương thích |
| JSON mapping | JSON/JSONB/CLOB/VARCHAR | DDL/type/index/operator khác |
| LOB | BLOB/CLOB/OID | JDBC lifecycle và dialect |

Không coi hai cột cùng JDBC type code là ngữ nghĩa 100% giống nhau. Một `VARCHAR(255)` và `VARCHAR(1000)` có thể cùng kiểu JDBC cơ bản, nhưng giới hạn storage khác.

### 14.1. `columnDefinition` không phải cách sửa DB thật

```java
@Column(
    name = "payload",
    columnDefinition = "jsonb"
)
private String payload;
```

`columnDefinition` ảnh hưởng schema generation/type expectations theo provider, nhưng không trực tiếp thay đổi cột database nếu schema do migration sở hữu.

Nếu DB vẫn là `TEXT`, cần migration chuyển type (có thể phải `USING ...::jsonb` trên PostgreSQL), kiểm tra dữ liệu cũ hợp lệ và các indexes.

## 15. Enum: mapping và dữ liệu cũ phải tương thích

Có hai dạng phổ biến:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

lưu số thứ tự enum, và:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

lưu tên enum theo cách provider/dialect hỗ trợ.

Nếu migration chuyển `SMALLINT` sang `VARCHAR`, chỉ `ALTER COLUMN TYPE` có thể chưa đủ; cần **migrate dữ liệu**.

Ví dụ PostgreSQL (minh họa cho trạng thái cũ 0/1/2):

```sql
ALTER TABLE purchase_orders
ALTER COLUMN status TYPE VARCHAR(20)
USING CASE status
    WHEN 0 THEN 'DRAFT'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'CANCELLED'
    ELSE NULL
END;
```

Cần xử lý giá trị ngoài mapping và constraint, và kiểm tra output không null trước khi áp NOT NULL. Sử dụng thứ tự enum làm mã nghiệp vụ có rủi ro khi source code đổi thứ tự constants.

### 15.1. Native PostgreSQL enum khác VARCHAR

Hibernate version/dialect có thể hỗ trợ enum SQL type native trong những điều kiện nhất định. Một cột PostgreSQL enum và mapping `@Enumerated(STRING)` không tự bảo đảm tương thích trong mọi Hibernate version. Khi migration dùng native enum, nên kiểm thử actual binding/extraction và schema validator với đúng stack.

## 16. Sequence, identity và allocation

Schema drift không chỉ ở columns.

Ví dụ entity:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_id_gen"
)
@SequenceGenerator(
    name = "order_id_gen",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
private Long id;
```

Migration:

```sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 50;
```

Hibernate sequence optimizer/validation behavior phụ thuộc version. Nếu migration tạo `INCREMENT BY 1` nhưng mapping kỳ vọng allocation 50, một số cấu hình Hibernate sẽ báo mismatch khi boot; các cấu hình khác hoặc code legacy có thể gặp nguy cơ tạo ID sai nếu optimizer và sequence không khớp.

Cần xác minh:

- Sequence tồn tại ở đúng schema.
- Tên và increment phù hợp generator.
- Allocation size/mapping optimizer có khớp.
- Sequence hiện tại không cấp trùng IDs đã có.
- Initial value, max/min/cycle và quyền `USAGE`.
- Các writers khác có dùng chung sequence đúng convention không.

### 16.1. Không đổi `allocationSize` đơn lẻ trên production

Đổi `allocationSize` trong entity mà không lập kế hoạch migration sequence/optimizer có thể gây lỗi hoặc rủi ro ID uniqueness. Hãy review behavior theo Hibernate version, DB sequence current state và deployment có nhiều phiên bản pods chạy song song.

### 16.2. Identity cũng cần đúng DDL

Nếu entity dùng:

```java
@GeneratedValue(strategy = GenerationType.IDENTITY)
```

nhưng cột ID trong database không có default/identity generation phù hợp, INSERT có thể thất bại khi Hibernate cần DB sinh key.

Validator không nên là phép kiểm tra duy nhất; chạy integration test thật với `persist()` và đọc ID được sinh.

## 17. Nullability: mapping, DDL và dữ liệu

Entity:

```java
@Column(nullable = false)
private String email;
```

Database:

```sql
email VARCHAR(255) NULL
```

Đây là mismatch integrity; SQL từ ngoài Hibernate vẫn có thể ghi null.

Ngược lại:

```java
@Column(nullable = true)
private String nickname;
```

nhưng DB `NOT NULL`, một entity có nickname null có thể persist/flush thất bại.

### 17.1. Test constraint ở database

Đừng chỉ assert mapping annotation:

```java
assertNotNull(
    Customer.class.getDeclaredField("email")
);
```

Test reflection đó không chứng minh database thật có NOT NULL.

Hãy hỏi `information_schema` hoặc `DatabaseMetaData`, và thử transaction rollback khi insert null nếu cần behavioral guarantee.

### 17.2. Bean Validation không thay NOT NULL

```java
@jakarta.validation.constraints.NotNull
private String email;
```

thường được kiểm tra ở tầng Bean Validation khi tích hợp, nhưng SQL trực tiếp ngoài JPA bỏ qua Bean Validation. Với dữ liệu cần bảo vệ lâu dài, DDL constraint vẫn là nguồn kiểm soát cuối.

## 18. Foreign key và quan hệ JPA

Mapping:

```java
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Database cần FK:

```sql
CONSTRAINT fk_purchase_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id)
```

Nhưng có thể xảy ra:

- Column `customer_id` tồn tại nhưng FK đã bị drop.
- FK tham chiếu nhầm table/schema.
- FK cho phép `ON DELETE CASCADE` trong khi nghiệp vụ muốn `RESTRICT`.
- FK là `DEFERRABLE`/`NOT DEFERRABLE` khác với deployment assumptions.
- `customer_id` nullable ở DB dù mapping optional=false.
- FK composite thiếu một cột.

`ddl-auto=validate` **không nên được coi là bằng chứng đầy đủ** cho mọi đặc tính FK.

### 18.1. Cascade ORM khác ON DELETE CASCADE

```java
@OneToMany(cascade = CascadeType.REMOVE)
```

là hành vi Hibernate/JPA khi entity remove qua ORM.

```sql
ON DELETE CASCADE
```

là hành vi database FK. Chúng không tương đương hoàn toàn và có thể có cách xử lý/version/flush khác nhau.

Nếu migration thêm `ON DELETE CASCADE` mà entity/business không dự kiến, external SQL DELETE có thể xóa child dữ liệu ngoài đường đi ORM. Cần kiểm tra FK actions riêng.

## 19. Unique, indexes và check constraints

Entity có:

```java
@Table(
    name = "customers",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customers_email",
            columnNames = "email"
        )
    }
)
```

DDL tương ứng:

```sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_email UNIQUE (email);
```

Một query quan trọng có index:

```sql
CREATE INDEX idx_orders_customer_status
ON purchase_orders (customer_id, status);
```

Và business constraint:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_orders_total
CHECK (total >= 0);
```

Các đối tượng này rất quan trọng với **data integrity và hiệu năng**, nhưng Hibernate schema validation không phải một bộ kiểm toán tất cả unique/index/check definitions.

### 19.1. Thiếu unique constraint có thể tạo bug khó phát hiện

Nếu chỉ kiểm tra `@Column(unique=true)` hoặc `@NaturalId` trong Java mà DB thiếu UNIQUE, hai concurrent transactions có thể chèn cùng email do race.

Ngay cả khi application có query kiểm tra email trước khi insert:

```text
T1: SELECT email -> chưa tồn tại
T2: SELECT email -> chưa tồn tại
T1: INSERT email
T2: INSERT email
```

Chỉ DB UNIQUE constraint (hoặc cơ chế consistency mạnh tương đương được thiết kế) mới ngăn duplicate ở ranh giới database.

### 19.2. Index không có trong mapping vẫn là một phần schema cần bảo vệ

Một partial/expression index:

```sql
CREATE INDEX idx_paid_orders_recent
ON purchase_orders (id)
WHERE status = 'PAID';
```

là PostgreSQL-specific và có thể không có annotation JPA tương đương đầy đủ.

Kiểm tra indexes qua catalog/schema snapshot hoặc migration tests, không kỳ vọng Hibernate metadata tái dựng tất cả đặc tính vendor-specific đó.

## 20. Default, computed columns và triggers

Migration:

```sql
ALTER TABLE purchase_orders
ALTER COLUMN status SET DEFAULT 'DRAFT';
```

không có nghĩa Hibernate luôn bỏ cột `status` khỏi INSERT khi Java field null.

Ví dụ:

```java
private OrderStatus status;
```

nếu Hibernate gửi:

```sql
INSERT INTO purchase_orders (status, ...) VALUES (NULL, ...);
```

DB default **không được áp dụng**, vì cột được cung cấp rõ `NULL`.

Default thường được dùng khi cột bị **omitted** hoặc SQL dùng `DEFAULT`, theo DB semantics.

Các lựa chọn:

- Gán default ở Java constructor/domain method.
- Dùng `@PrePersist` nếu phù hợp.
- Cấu hình generated/dynamic insert theo Hibernate và test thực tế.
- Để DB default nhưng thiết kế ORM INSERT omit column một cách rõ ràng.

### 20.1. `@ColumnDefault` không phải migration

Hibernate `@ColumnDefault` giúp diễn đạt default khi generate DDL, nhưng **không tự sửa database đã tồn tại** nếu migration là owner. Và annotation đó không tự khởi tạo giá trị Java field trước INSERT.

### 20.2. Generated columns và triggers

Database có thể dùng:

- `GENERATED ALWAYS AS` computed columns.
- Triggers cập nhật `updated_at`.
- Server-side UUID generation.
- Row-level security policies.
- Audit triggers.

Những chi tiết này không được xác nhận đầy đủ bằng `ddl-auto=validate`. Cần kiểm tra catalog hoặc behavior tests, và mapping đọc generated values đúng.

## 21. Kiểm tra schema bằng JDBC `DatabaseMetaData`

JDBC cung cấp API introspection tương đối portable:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import javax.sql.DataSource;

public void inspectCustomers(DataSource dataSource)
        throws Exception {

    try (Connection con = dataSource.getConnection()) {
        DatabaseMetaData meta = con.getMetaData();

        try (ResultSet columns = meta.getColumns(
                con.getCatalog(),
                "public",
                "customers",
                "%"
        )) {
            while (columns.next()) {
                String name = columns.getString("COLUMN_NAME");
                int jdbcType = columns.getInt("DATA_TYPE");
                String typeName = columns.getString("TYPE_NAME");
                int size = columns.getInt("COLUMN_SIZE");
                int digits =
                    columns.getInt("DECIMAL_DIGITS");
                int nullable = columns.getInt("NULLABLE");

                System.out.printf(
                    "%s: %s typeCode=%d size=%d scale=%d nullable=%d%n",
                    name, typeName, jdbcType,
                    size, digits, nullable
                );
            }
        }
    }
}
```

Với PostgreSQL driver, `schemaPattern="public"` và `tableNamePattern="customers"` là ví dụ. Ở DB khác, case folding và catalog/schema parameters có thể khác.

### 21.1. Các API metadata hữu ích

`DatabaseMetaData` có:

```java
meta.getTables(catalog, schemaPattern, tableNamePattern, types);
meta.getColumns(catalog, schemaPattern, tableNamePattern, columnPattern);
meta.getPrimaryKeys(catalog, schema, table);
meta.getImportedKeys(catalog, schema, table);
meta.getExportedKeys(catalog, schema, table);
meta.getIndexInfo(catalog, schema, table, unique, approximate);
```

Có thể kiểm tra:
- Table tồn tại?
- Column name/type/length/nullable?
- PK columns?
- FK referenced table/columns và update/delete rules?
- Indexes được JDBC metadata nhận diện?

### 21.2. JDBC metadata cũng có giới hạn

Không mọi DBMS/driver trả:
- Partial index predicates.
- Expression indexes.
- Deferrability chi tiết.
- Check constraint text.
- Triggers.
- RLS policies.
- Extensions.
- Enum values.

Với PostgreSQL, đôi khi cần dùng `pg_catalog` thay vì chỉ dựa vào JDBC metadata.

## 22. SQL `information_schema` để xem schema thực

Trên PostgreSQL, có thể dùng:

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
```

Kết quả cho phép so:
- `customer_id` có `is_nullable = 'NO'`?
- `total` có precision/scale `(18,2)`?
- `status` có VARCHAR length 20?
- `version` có default 0?
- `created_at` kiểu gì?

`information_schema` khá portable về khái niệm, nhưng visibility và cách hiện kiểu database-specific có thể khác nhau. Đừng parse `data_type` rồi mong mọi dialect dùng cùng một chuỗi cho UUID/JSON/ENUM.

### 22.1. Query kiểm tra constraint trên PostgreSQL

```sql
SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.purchase_orders'::regclass
ORDER BY conname;
```

Có thể quan sát PK, FK, UNIQUE, CHECK. `contype` và `pg_get_constraintdef` là PostgreSQL-specific.

### 22.2. Kiểm tra indexes

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'purchase_orders'
ORDER BY indexname;
```

Một schema test có thể assert các index quan trọng tồn tại và có định nghĩa phù hợp, nhưng hãy tránh so nguyên văn SQL `indexdef` khi các version DB format khác nhau; normalize hoặc kiểm tra các đặc điểm quan trọng.

### 22.3. Kiểm tra sequences

```sql
SELECT
    schemaname,
    sequencename,
    increment_by,
    cache_size
FROM pg_sequences
WHERE schemaname = 'public'
ORDER BY sequencename;
```

Câu này chỉ áp dụng PostgreSQL version hỗ trợ view `pg_sequences`. Với IDENTITY-backed sequence hoặc schemas custom, cần xác định đúng object sở hữu.

## 23. Kiểm tra drift qua schema snapshot/reference database

Một quy trình mạnh:

1. Tạo database trống bằng cùng DBMS major version như production.
2. Áp **toàn bộ migrations trong repository** theo đúng thứ tự.
3. Chụp snapshot cấu trúc `tables, columns, constraints, indexes, sequences, views...`.
4. Chụp snapshot môi trường cần kiểm tra (staging/prod) bằng account read-only.
5. So sánh cấu trúc, bỏ qua những đối tượng system/ephemeral được whitelist.
6. Triage khác biệt và tạo migration mới khi cần.

Mô hình:

```text
Repository migrations
         |
         v
Ephemeral reference DB
         |
         +--------------------+
         |                    |
         v                    v
Reference schema         Target schema snapshot
         |                    |
         +---------diff-------+
                   |
                   v
           Drift report/review
```

**Reference database** tốt hơn việc suy đoán expected schema chỉ từ từng SQL file, vì migrations có thể có backfills, conditionals và vendor-specific behavior.

### 23.1. Không so schema prod bằng cách cấp quyền DDL cho CI

Một drift detector trên production nên có **read-only metadata access** thích hợp. Không để một bước “đồng bộ tự động” tự chạy destructive ALTER/DROP khi phát hiện khác biệt.

Diff report cần được review; remediation phải đi qua migration/release process.

## 24. Test migrations trên DB trống và DB đã có dữ liệu

Migration có thể thành công trên DB trống nhưng thất bại trên database thật.

Ví dụ:

```sql
ALTER TABLE customers
ADD COLUMN loyalty_tier VARCHAR(20) NOT NULL;
```

Trên bảng rỗng có thể thành công. Trên bảng có hàng cũ, có DBMS sẽ từ chối vì các rows hiện hữu không có giá trị cho cột mới.

Do đó CI nên có hai loại kiểm thử:

**Fresh-install test**
- Tạo DB sạch.
- Chạy tất cả migration từ đầu.
- Hibernate validate.
- Insert/load qua ORM.

**Upgrade-path test**
- Khởi tạo DB ở phiên bản schema trước.
- Seed dữ liệu có giá trị thật/edge cases.
- Chạy pending migrations.
- Hibernate validate.
- Kiểm tra dữ liệu preserved/backfilled và business behavior.

Một pipeline chỉ test fresh install có thể bỏ sót rất nhiều lỗi migration production.

## 25. Testcontainers với PostgreSQL và Flyway

Với Spring Boot, có thể dùng Testcontainers để chạy DBMS gần giống production:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class SchemaContractIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProps(DynamicPropertyRegistry props) {
        props.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        props.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        props.add(
            "spring.datasource.password",
            postgres::getPassword
        );

        props.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "validate"
        );
        props.add(
            "spring.flyway.enabled",
            () -> "true"
        );
    }

    @Autowired
    DataSource dataSource;

    @Test
    void customersEmailColumnIsNotNullable()
            throws Exception {

        try (Connection con = dataSource.getConnection();
             ResultSet rs =
                 con.getMetaData().getColumns(
                     con.getCatalog(),
                     "public",
                     "customers",
                     "email"
                 )) {

            assertTrue(rs.next(), "Missing customers.email");

            int nullable = rs.getInt("NULLABLE");

            assertEquals(
                java.sql.DatabaseMetaData.columnNoNulls,
                nullable
            );
        }
    }
}
```

Điều kiện để test thực sự có giá trị:

- `spring-boot-starter-data-jpa`/Hibernate và Flyway dependencies có mặt.
- `db/migration` được đóng gói trên test runtime classpath.
- Database image được pin version có kiểm soát.
- Container được tạo trước datasource bootstrap qua Testcontainers/JUnit integration.
- Spring Boot thực thi Flyway trước Hibernate metadata validation theo configuration.
- Test không dùng schema do `create-drop` tạo thay thế migrations.

### 25.1. Chú ý `@DataJpaTest` và embedded DB

Trong một số cấu hình, `@DataJpaTest` có thể thay datasource bằng database embedded theo mặc định nếu được auto-configure. Nếu dùng Testcontainers, phải bảo đảm test **thật sự kết nối tới container**, có thể cần:

```java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
```

tùy Spring Boot version và test annotation đang dùng.

Nếu test trỏ nhầm H2, kết quả `validate` xanh chỉ chứng minh mapping khớp H2 schema được tạo, không chứng minh migrations PostgreSQL đúng.

### 25.2. Không lấy Testcontainers làm toàn bộ kiểm thử migration

Container DB mới không chứa dữ liệu lịch sử thực. Cần thêm upgrade-path tests hoặc snapshot-based tests cho migrations rủi ro.

## 26. Một schema contract test cho index, FK và constraint

JDBC metadata có thể kiểm tra FK:

```java
try (Connection con = dataSource.getConnection();
     ResultSet keys =
         con.getMetaData().getImportedKeys(
             con.getCatalog(),
             "public",
             "purchase_orders"
         )) {

    boolean fkExists = false;

    while (keys.next()) {
        String fkColumn = keys.getString("FKCOLUMN_NAME");
        String pkTable = keys.getString("PKTABLE_NAME");

        if ("customer_id".equalsIgnoreCase(fkColumn)
                && "customers".equalsIgnoreCase(pkTable)) {
            fkExists = true;
        }
    }

    assertTrue(fkExists);
}
```

Đoạn code trên kiểm tra rằng FK column `customer_id` tham chiếu bảng `customers`; test production-grade còn nên xác nhận `PKCOLUMN_NAME`, delete/update rules, schema, multi-column key ordering và expected constraint name nếu tên là contract.

Với CHECK/partial index PostgreSQL-specific:

```java
String sql = """
    select conname, pg_get_constraintdef(oid)
    from pg_constraint
    where conrelid = 'public.purchase_orders'::regclass
    """;
```

Có thể dùng `JdbcTemplate`/JDBC để assert `ck_purchase_orders_total_nonnegative` tồn tại và chứa điều kiện tổng không âm, hoặc thực hiện **behavioral test** cố insert total âm trong một transaction rollback.

### 26.1. Metadata test và behavior test bổ sung cho nhau

- Metadata test chứng minh cấu trúc/constraint có mặt.
- Behavior test chứng minh DB từ chối dữ liệu vi phạm trong tình huống cụ thể.
- ORM integration test chứng minh Hibernate thực sự bind/extract được dữ liệu.

Nếu CHECK constraint viết sai biểu thức nhưng vẫn có cùng tên, chỉ assert tên chưa đủ.

## 27. Behavioral test cho các điểm dễ lệch

Những hành vi nên thử sau khi migration và Hibernate validate:

1. `persist(Customer)` có sinh ID đúng và INSERT thành công?
2. Lưu `BigDecimal("123.45")`, đọc lại có giữ scale/giá trị?
3. `Instant` qua DB/JDBC có đúng instant/timezone expectations?
4. Lưu/đọc enum STRING với các giá trị hiện hữu có đúng?
5. Insert duplicate email có bị UNIQUE constraint từ chối?
6. Insert order với `customer_id` không tồn tại có bị FK từ chối?
7. Insert `total = -1` có bị CHECK từ chối?
8. `@Version` có tăng đúng qua managed UPDATE?
9. Query theo index-critical columns có SQL plan hợp lý trên dữ liệu đủ lớn?
10. Entity mapping cùng secondary table/embedded attributes có đọc/ghi đủ cột?

### 27.1. Test lỗi constraint cần rollback/context mới

Nếu database ném exception ở flush vì UNIQUE/FK, transaction có thể bị đánh dấu rollback-only. Không tiếp tục dùng cùng EntityManager để chạy nhiều asserts như chưa có lỗi.

Tách test transaction, rollback và đóng context sau constraint violation; với Spring test-managed transactions, cẩn thận behavior khi exception đánh dấu rollback-only.

## 28. Drift phát sinh từ thao tác tay trên production

Một DBA sửa:

```sql
ALTER TABLE purchase_orders
DROP CONSTRAINT ck_purchase_orders_total_nonnegative;
```

Migration history không đổi. Hibernate có thể vẫn khởi động vì mapped fields còn đầy đủ.

Vì vậy cần:

- Quy định mọi schema changes phải qua migration code review.
- Hạn chế quyền DDL của runtime application user.
- Audit DDL events nếu DBMS hỗ trợ.
- Định kỳ snapshot/diff schema trên production.
- Cảnh báo drift về constraints/indexes/sequences quan trọng.
- Không tự sửa production bằng Hibernate `update`.

Nếu emergency hotfix thật sự cần SQL trực tiếp, phải backport thành migration có lịch sử phù hợp và có kế hoạch reconciliation, không để repo và DB khác nhau lâu dài.

## 29. Ba môi trường với ba schema version khác nhau

Ví dụ:

```text
development : migrations V1..V12
staging     : migrations V1..V11
production  : migrations V1..V10
```

Đây có thể là trạng thái release bình thường, không nhất thiết drift lỗi. Điều quan trọng là **mỗi application build đang deploy phải tương thích với schema version của môi trường đó**.

Khi kiểm tra:

- So script versions với release manifest.
- Biết migration target cho mỗi environment.
- Kiểm tra chưa có migration failed/partial.
- Không so staging V11 trực tiếp với production V10 rồi gắn nhãn drift mà thiếu release context.
- Kiểm tra đúng tenant/schema/database nếu hệ thống có nhiều DBs.

### 29.1. Nên ghi app build version cùng migration version

Ví dụ trong deployment metadata:

```text
app.version=2.7.0
db.migration.target=V12
hibernate.version=6.x
database=PostgreSQL 16
```

Các giá trị chỉ minh họa. Có version matrix giúp triage lỗi “app đã code mới nhưng migration chưa chạy” và điều phối rolling deploy.

## 30. Rolling deployment và expand-contract migration

Một hệ thống có nhiều pods không thể luôn đổi schema theo kiểu “đổi tên cột ngay lập tức” nếu old pods vẫn chạy.

Ví dụ muốn đổi `customer.name` thành `display_name`:

**Pha expand**
- Add `display_name` nullable.
- Deploy code đọc/ghi tương thích hoặc dual-write.
- Backfill từ `name`.
- Kiểm tra dữ liệu.

**Pha migrate traffic**
- Deploy tất cả pods dùng `display_name`.
- Theo dõi còn writer/reader nào dùng `name` không.

**Pha contract**
- Đảm bảo `display_name` NOT NULL/constraints.
- Drop `name` bằng migration sau khi old pods không còn.
- Bỏ dual-write.

Một sơ đồ:

```text
Schema V1           Schema V2 expand           Schema V3 contract
  name                  name                      display_name
                        display_name
    |                      |                            |
  App old          App old + App new                 App new
```

**Schema validation cần xét compatibility window.** Một Hibernate build mới có thể `validate` fail nếu cột mới chưa xuất hiện; một Hibernate build cũ có thể fail hoặc query lỗi nếu cột cũ bị drop quá sớm.

Không thiết kế rollout dựa trên giả định tất cả app instances chuyển phiên bản trong cùng một thời điểm nguyên tử.

## 31. Transaction và lock khi chạy migration

Một số DDL có thể:

- Chạy trong transaction và rollback được (tùy DBMS/operation).
- Không hỗ trợ chạy trong transaction.
- Lấy lock bảng gây block queries.
- Rebuild index lâu.
- Backfill hàng triệu rows tiêu tốn WAL/redo và I/O.
- Làm tăng replication lag.

Flyway/Liquibase quản lý migration history/locking theo tool và DB capabilities, nhưng **một migration hợp lệ về syntax vẫn có thể nguy hiểm vận hành**.

Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY ...
```

không được chạy trong một transaction block thông thường; pipeline migration cần cấu hình đúng theo tool và operation.

Một DB khác có thể có online index DDL khác. Không copy SQL CONCURRENTLY qua dialect khác.

### 31.1. Kiểm tra migration bằng dữ liệu production-like

Bên cạnh schema validation, đo:
- Thời gian migration.
- Lock durations và blocked sessions.
- Disk/log growth.
- Index build time.
- Replication lag.
- Backfill throughput.
- Rollback/roll-forward behavior.

Một migration thêm index trong 20 ms trên bảng trống không chứng minh nó an toàn cho production có hàng tỷ rows.

## 32. Snapshot và checksum không nên dùng nhầm mục đích

Có ít nhất ba dạng “checksum/snapshot”:

1. **Migration checksum**: phát hiện script đã thay đổi so với history.
2. **Schema snapshot fingerprint**: mô tả cấu trúc vật lý ở một thời điểm.
3. **Data checksum**: mô tả hoặc kiểm chứng giá trị data theo phép tính/ranh giới cụ thể.

Chúng khác nhau.

- Migration checksum bằng nhau không chứng minh schema hiện tại giống nhau.
- Schema fingerprint giống nhau không chứng minh dữ liệu nội dung giống nhau.
- Data checksum khớp không chứng minh FK/index/defaults đúng.

Một drift detector tốt gắn loại kiểm tra với yêu cầu thực tế, không dùng một chữ “validate OK” bao trùm mọi loại.

## 33. Multiple datasources và persistence units

Một ứng dụng có thể dùng:
- Database giao dịch chính.
- Database báo cáo.
- Một tenant database cho mỗi khách hàng.
- Một persistence unit cho catalog và một cho billing.

Khi đó cần kiểm tra **từng datasource và từng EntityManagerFactory** riêng:

```text
DataSource billing
  -> Flyway billing migrations
  -> Hibernate billing EMF
  -> billing schema validation

DataSource catalog
  -> Liquibase catalog changesets
  -> Hibernate catalog EMF
  -> catalog schema validation
```

Không được chỉ validate primary datasource rồi giả định secondary datasource cũng khớp.

### 33.1. Multi-tenant schema/database

Với schema-per-tenant/database-per-tenant, một tenant có thể thiếu V12 trong khi tenant khác đã áp. Cần:
- Danh sách tenants chính xác.
- Migration history và schema snapshot cho từng tenant target.
- Canary tenants / staged rollout.
- Error aggregation và retry.
- Thông tin tenant trong cảnh báo drift.
- Quy trình dừng deploy nếu tỷ lệ tenants fail vượt giới hạn.

Một `ddl-auto=validate` khởi động trên default tenant không nhất thiết đã xác minh toàn bộ các tenant schemas.

## 34. Không tự động tạo “migration sửa mọi khác biệt” từ metadata

Hibernate có schema generation và một số công cụ diff, Liquibase có diff-changelog, nhưng **diff output không đồng nghĩa một migration production-safe**.

Tình huống:

```text
Code mới:
  @Column(name="display_name")

DB cũ:
  name
```

Một schema diff không có business context có thể đề xuất:
- DROP `name`.
- ADD `display_name`.

Nếu apply thẳng, dữ liệu name cũ bị mất. Migration thực tế cần:
- ADD.
- BACKFILL.
- Dual-write/read migration.
- Validate.
- DROP sau.

Tương tự, đổi `NUMERIC(18,2)` thành `NUMERIC(8,2)` có thể làm dữ liệu lớn không còn hợp lệ. Một diff tool không thể tự suy ra quy tắc rounding hay business contract.

**Schema diff là tín hiệu cần xử lý có review**, không phải giấy phép tự động thay DB production.

## 35. Một workflow CI có nhiều lớp bảo vệ

Đề xuất pipeline:

```text
Code change
   |
   v
1. Check migration naming/history consistency
   |
   v
2. Build application and migration artifact
   |
   v
3. Start isolated production-like DB
   |
   v
4. Apply every migration from scratch
   |
   v
5. Bootstrap Hibernate with ddl-auto=validate
   |
   v
6. Assert critical DB metadata/contracts
   |
   v
7. Run ORM integration tests
   |
   v
8. Test upgrade from prior released schema
   |
   v
9. Generate reviewed schema snapshot/diff
   |
   v
10. Deploy with migration/rollback plan
```

Lợi ích của từng lớp:

| Lớp | Phát hiện tốt |
| --- | --- |
| Migration validate | Changelog/history checksum/version consistency |
| Fresh migrations | Thiếu script, lỗi DDL, dependencies |
| Hibernate validate | Thiếu mapped table/column, một số type/sequence mismatch |
| Metadata contract tests | FK, unique, not-null, indexes, defaults quan trọng |
| Behavioral integration tests | DML, converters, enum, FK/unique enforcement |
| Upgrade tests | Backfill và compatibility với dữ liệu có sẵn |
| Schema snapshot/diff | Drift ngoài migration pipeline |
| Production monitoring | Manual DDL, multi-node/tenant discrepancies |

### 35.1. Không dùng H2 làm production compatibility oracle

H2 hữu ích cho một số unit/integration tests nhẹ, nhưng PostgreSQL/MySQL/Oracle/SQL Server khác nhau ở:
- Data types.
- Identity/sequence.
- JSON/UUID.
- Enum.
- DDL transaction.
- Constraints/defaults.
- Collation/timezone.
- SQL dialect và index semantics.

Nếu production là PostgreSQL, ít nhất lớp schema contract quan trọng cần chạy trên PostgreSQL container/instance phù hợp.

## 36. Production startup và health checks

Một ứng dụng có `ddl-auto=validate` có thể fail startup khi mismatch. Đây là cơ chế fail-fast tốt, nhưng cần kế hoạch deploy:

- Migration phải chạy trước nếu app mới cần cột mới.
- Readiness chỉ bật sau khi EntityManagerFactory đã bootstrap thành công.
- Không cố restart liên tục khi lỗi schema không thể tự sửa.
- Log lỗi đủ chi tiết để xác định table/column/type.
- Không tự chuyển `ddl-auto=update` trong emergency chỉ để pod khởi động.
- Giữ app cũ phục vụ khi migration/deployment mới fail theo rollback strategy, nếu compatibility cho phép.

### 36.1. Một DB schema đúng vẫn có thể không đủ permission

Validator có thể nhìn thấy bảng, nhưng runtime user không có quyền SELECT/INSERT/UPDATE hoặc không được USAGE sequence. Để ứng dụng hoạt động cần thêm permission checks hoặc integration tests với **đúng database role** của production runtime.

Đừng chạy tất cả tests bằng superuser rồi kết luận application user luôn truy cập được.

## 37. Triage một lỗi validation khi khởi động

Giả sử log:

```text
Schema-validation: missing column [loyalty_tier]
in table [customers]
```

Quy trình:

1. Xác định application artifact/build và entity `Customer`.
2. Xác nhận JDBC URL, schema, user và tenant thực tế.
3. Kiểm tra migration nào dự định thêm `loyalty_tier`.
4. Kiểm tra Flyway/Liquibase history: migration pending/failed/applied?
5. Query `information_schema.columns` để xem cột thật có tồn tại không.
6. Nếu cột ở schema khác, sửa schema/naming config chứ không tạo thêm cột trùng.
7. Nếu migration chưa chạy, áp migration theo release process.
8. Nếu history báo đã chạy nhưng cột mất, điều tra manual DDL/drift.
9. Nếu mapping đổi tên nhưng migration thiếu backfill, tạo migration mới phù hợp.
10. Chạy lại Hibernate validate và integration tests.
11. Không sửa file migration đã được apply để che checksum issue.
12. Ghi lại nguyên nhân gốc và bổ sung CI kiểm tra tương ứng.

### 37.1. Lỗi “wrong column type”

Cần kiểm tra:
- SQL type và JDBC type code thật.
- Hibernate version/dialect và preferred SQL type configuration.
- Attribute annotations như `@JdbcTypeCode`, `@Enumerated`, converter.
- Migration target DBMS.
- Driver metadata behavior.
- Dữ liệu cũ có hợp lệ với kiểu mong muốn.

Không tự đổi `columnDefinition` cho đến khi validator im lặng mà chưa biết dữ liệu runtime sẽ được bind/extract đúng không.

### 37.2. Lỗi sequence increment mismatch

Cần so:
- `@SequenceGenerator(allocationSize=...)`.
- DB sequence increment.
- Hibernate ID optimizer/version.
- Existing ID range và concurrent deployments.

Sửa cả mapping/migration theo kế hoạch, không chỉ tắt validation.

## 38. Phân biệt schema drift và dữ liệu sai

Schema có thể đúng nhưng dữ liệu sai:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE total < 0;
```

Nếu DB không có CHECK constraint, tồn tại data xấu là dấu hiệu integrity gap. Nhưng kể cả CHECK tồn tại sau migration mới, dữ liệu legacy trước đó có thể cần remediation/backfill tùy DB constraint validation trạng thái.

Một schema drift detector kiểm tra column/index không xác nhận mọi domain invariant. Với các thay đổi có backfill, nên thêm data checks:

```sql
SELECT COUNT(*)
FROM customers
WHERE loyalty_tier IS NULL;
```

Kỳ vọng 0 trước khi thêm NOT NULL.

### 38.1. Không chạy data check quá nặng trên production hot path

`COUNT(*)` hoặc scan bảng lớn có thể tốn I/O. Dùng migration validation queries được đánh giá, index phù hợp, batch scanning hoặc offline checks. Không đặt scan toàn bảng vào mỗi request healthcheck.

## 39. Các lỗi và anti-pattern thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Flyway validate xanh nhưng thiếu FK | History hợp lệ, FK đã bị drop ngoài migration | DB metadata/schema diff |
| Hibernate validate xanh nhưng thiếu UNIQUE | Validator không kiểm toán toàn bộ constraints | Contract test/schema catalog |
| Hibernate báo missing table | Sai schema/search_path hoặc chưa migrate | Kiểm tra connection/schema/history |
| Hibernate báo missing column | Entity mới nhưng migration thiếu | Tạo/apply migration đúng |
| Hibernate báo wrong type | Enum/JSON/UUID/time/dialect mismatch | Kiểm tra mapping, JDBC metadata, migration |
| App test H2 pass, prod fail | DB dialect/DDL differences | Testcontainers production DB |
| `ddl-auto=update` sửa prod ngoài kiểm soát | DDL ownership lẫn lộn | Migration-owned schema, validate |
| Checksum mismatch | Sửa migration đã apply | Review lịch sử, migration mới; không repair tùy tiện |
| Migration trên DB trống pass, prod fail | Existing rows/backfill/locks | Upgrade-path và load tests |
| Runtime role không tạo sequence value | Thiếu USAGE/permissions | Test với đúng DB role |
| Email duplicate dù `unique=true` | DB thiếu unique constraint | Add/migrate UNIQUE, kiểm dữ liệu cũ |
| `@Version` không hoạt động đúng | Cột version/mapping/DML path lệch | Test optimistic locking, schema type |
| Bulk update làm L1 có state cũ | ORM state không sync | Refresh/clear transaction context phù hợp |
| Index mất sau DBA change | Manual drift | Snapshot diff và DDL audit |
| New pods fail khi old pods còn chạy | Migration không expand-contract | Thiết kế compatibility windows |
| Flyway và Hibernate cùng tạo bảng | Hai DDL owners | Disable create/update trong migration-owned app |
| Các tenants khác schema | Migration không chạy đủ tenants | Per-tenant history/validation |
| Test chạy bằng superuser | Permission drift không bị phát hiện | Test runtime DB role |
| Schema diff báo hàng trăm khác biệt giả | Default names/type rendering khác | Normalize/whitelist và manual triage |
| “Sửa” validation bằng đổi annotation tạm | Che mismatch thay vì sửa nguồn | Chốt expected schema rồi migration đúng |

## 40. Bài tập tình huống

### Bài 1 — Flyway xanh nhưng DB sai

Flyway `validate` thành công, nhưng bảng `purchase_orders` không còn FK `customer_id` tới `customers`.

**Đáp án:** Flyway đối chiếu scripts/history, không bảo đảm FK vẫn tồn tại. Dùng metadata/catalog/contract tests và tìm nguyên nhân manual DDL.

### Bài 2 — Hibernate validate có đủ không?

Ứng dụng có `ddl-auto=validate` và startup thành công. Có chắc `email` được database UNIQUE không?

**Đáp án:** Không. Validator không phải một full constraint auditor; test UNIQUE qua database metadata hoặc behavioral test.

### Bài 3 — Không có migration cho field mới

Dev thêm `@Column(name="loyalty_tier")`; app fail `missing column`.

**Đáp án:** Tạo migration mới để add column, backfill nếu cần và áp constraints; không bật `update` tùy tiện trên production.

### Bài 4 — `NULL` trước `NOT NULL`

Bảng có 10 triệu customers. Migration add `loyalty_tier VARCHAR(20) NOT NULL` không default thất bại.

**Đáp án:** Cần expand/backfill/validate/NOT NULL theo pha, với kế hoạch hiệu năng và locking.

### Bài 5 — Đổi migration cũ

V2 đã áp dụng prod; developer chỉnh nội dung V2 và Flyway báo checksum mismatch.

**Đáp án:** Không sửa historical migration đã phát hành. Tạo migration mới cho correction; chỉ dùng repair theo quy trình được review nếu có lý do chính đáng.

### Bài 6 — Wrong schema

Bảng `billing.customers` tồn tại nhưng Hibernate tìm `public.customers`.

**Đáp án:** Đồng bộ `@Table(schema)`, Hibernate default schema, Flyway schema settings và JDBC search_path.

### Bài 7 — BigDecimal mismatch

Entity `BigDecimal precision=18 scale=2` nhưng DB `NUMERIC(10,0)`. Có nguy cơ gì?

**Đáp án:** Mất phần lẻ/giới hạn số nhỏ hơn, binding/validation lỗi. Cần migration type đúng và kiểm dữ liệu hiện hữu.

### Bài 8 — Sequence mismatch

Entity `allocationSize=50`, DB sequence `INCREMENT BY 1`. Có nên tắt validate?

**Đáp án:** Không. Kiểm tra Hibernate optimizer/version và sửa mapping/sequence qua migration plan phù hợp, bảo đảm ID uniqueness.

### Bài 9 — UUID/JSON

Test H2 lưu JSON thành VARCHAR chạy tốt; PostgreSQL production dùng JSONB và báo type mismatch.

**Đáp án:** Test trên PostgreSQL cùng mapping/driver/DDL; H2 không chứng minh compatibility JSONB.

### Bài 10 — Unique nhưng không được bảo vệ

`@Column(unique=true)` có trong code, nhưng raw SQL ghi duplicate email thành công.

**Đáp án:** DB thiếu unique enforcement. Annotation không thay schema migration; cần tạo constraint sau khi xử lý dữ liệu duplicate.

### Bài 11 — CHECK constraint

Migration tạo `CHECK(total >= 0)` nhưng schema diff chỉ so columns. Có đủ không?

**Đáp án:** Không. Cần kiểm tra constraints qua catalog hoặc behavioral test với total âm.

### Bài 12 — DB default

DB có `status DEFAULT 'DRAFT'`. Hibernate INSERT `status=NULL`. Default có chạy không?

**Đáp án:** Không theo semantics thông thường; default áp khi cột bị omitted/DEFAULT. Cần gán giá trị Java hoặc cấu hình insert rõ.

### Bài 13 — Two versions rolling

App cũ đọc `name`, app mới đọc `display_name`. Có thể DROP `name` ngay khi deploy app mới không?

**Đáp án:** Không nếu pods cũ còn chạy. Dùng expand-contract và compatibility window.

### Bài 14 — Fresh-install pass, upgrade fail

V5 migration pass trên database trống nhưng fail trên production có dữ liệu.

**Đáp án:** Thiếu upgrade-path test với legacy rows; cần backfill, migration staging và load/lock plan.

### Bài 15 — Manual hotfix

DBA thêm index trực tiếp trên production để cứu latency. Làm sao tránh drift lâu dài?

**Đáp án:** Ghi nhận DDL, đồng bộ thành migration được review cho mọi môi trường và reconcile history/schema theo quy trình.

### Bài 16 — Multiple tenants

App validation chỉ chạy trên default tenant; tenant khác thiếu cột. Có thể coi hệ thống đã đồng bộ không?

**Đáp án:** Không. Cần migration history/validation cho từng tenant schema/database trong phạm vi vận hành.

### Bài 17 — App runtime privileges

CI dùng superuser pass, prod user không có quyền dùng sequence.

**Đáp án:** Thiếu role-permission contract tests; chạy behavioral tests với DB role tương đương production.

### Bài 18 — Schema diff có thể auto-apply không?

Diff đề xuất drop `name` và add `display_name` để khớp entity mới.

**Đáp án:** Không nên tự apply. Nó có thể làm mất dữ liệu; cần migration backfill/dual-read/write và contract phase đúng.

## 41. Tài liệu tham khảo

- [Hibernate ORM User Guide — Schema Generation](https://docs.hibernate.org/stable/orm/userguide/html_single/#schema-generation): schema tools, generation/validation và cấu hình.
- [Hibernate ORM User Guide — Mapping Types](https://docs.hibernate.org/stable/orm/userguide/html_single/#basic): basic type mapping, JDBC/Java types và mapping options.
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/stable/orm/userguide/html_single/#identifiers): ID generation, sequences, identity.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): schema generation, entity metadata, mapping, constraints và lifecycle.
- [Spring Boot Reference — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): Flyway/Liquibase/JPA schema initialization.
- [Flyway Documentation](https://documentation.red-gate.com/fd/): migrations, schema history, migrate/validate/repair và compatibility.
- [Liquibase Documentation](https://docs.liquibase.com/): changelogs, validate, update, status, diff và snapshots.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): integration tests dùng PostgreSQL container.
- [JDBC `DatabaseMetaData` Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html): introspection tables, columns, indexes và keys.
- [PostgreSQL Information Schema](https://www.postgresql.org/docs/current/information-schema.html): schema objects và metadata SQL.
- [PostgreSQL System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): `pg_constraint`, `pg_indexes`, `pg_sequences` và database metadata.

**Phạm vi phiên bản:** Hibernate validator behavior, metadata inspection, naming strategy, sequence validation, Flyway/Liquibase CLI và SQL syntax thay đổi theo major version, database driver/dialect và configuration. Đặc biệt, các ví dụ PostgreSQL không portable 100% sang MySQL, Oracle hay SQL Server. Hãy xem tài liệu và kiểm chứng trên đúng stack thực tế.

## Kết luận

**Migration history, database schema và Hibernate metadata là ba góc nhìn khác nhau**, vì vậy đồng bộ phải được xác minh bằng nhiều lớp. Flyway/Liquibase giúp quản lý lịch sử schema changes nhưng không tự chứng minh mọi constraint/index còn tồn tại; Hibernate `ddl-auto=validate` phát hiện một số lỗi table/column/type/sequence nhưng không phải full schema diff. Database metadata, integration tests và schema snapshots bổ sung những khoảng trống đó.

Quy trình đáng tin cậy là: **viết migration cho mỗi thay đổi mapping → áp migration lên database tương đương production → bootstrap Hibernate với validate → kiểm tra các constraints/indexes/defaults quan trọng → chạy ORM behavioral tests và upgrade-path tests → giám sát drift trên staging/production**. Trong môi trường nhiều pods/tenants, còn phải tính compatibility window, migration locks và version matrix.

Đừng dùng `ddl-auto=update`, sửa historical migrations, `repair` thiếu kiểm soát hoặc auto-apply schema diff như một cách che mismatch. Hãy dùng migration có review, fail-fast validation, introspection trên database thật và kiểm thử dữ liệu theo nghiệp vụ để giữ ba nguồn thông tin nhất quán qua mọi lần deploy.
