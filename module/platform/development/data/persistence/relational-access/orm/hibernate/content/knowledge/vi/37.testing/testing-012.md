# Kiểm thử migration, Envers và các khả năng phụ thuộc Dialect

Một ứng dụng Hibernate có thể chạy ổn trên database phát triển nhưng thất bại khi triển khai production vì schema migration không tạo đúng bảng audit, kiểu dữ liệu khác nhau giữa các DBMS, sequence/identity được khai báo sai, hoặc một truy vấn Envers dựa vào khả năng SQL mà Dialect và phiên bản database không hỗ trợ.

Khi dùng Hibernate Envers, schema không chỉ gồm các bảng nghiệp vụ. Nó còn có revision table (thường là `REVINFO`), các audit tables (`*_AUD`), audit join tables cho một số collection/association, cột revision metadata, index và constraint liên quan. Mỗi thay đổi mapping có thể kéo theo thay đổi ở nhiều bảng. Một migration chỉ sửa bảng chính nhưng bỏ quên audit schema có thể khiến ứng dụng chạy được một số thao tác rồi mới lỗi khi persist, xóa entity hoặc truy vấn lịch sử.

**Kiểm thử migration, Envers và Dialect cần kiểm tra ba hợp đồng cùng lúc:**

1. **Hợp đồng schema:** Flyway/Liquibase tạo đúng cấu trúc bảng, khóa, index, kiểu dữ liệu và revision metadata.
2. **Hợp đồng ORM/audit:** Hibernate và Envers ghi, đọc, truy vấn lịch sử đúng với mapping đang triển khai.
3. **Hợp đồng DBMS/Dialect:** SQL, generator, kiểu dữ liệu, locking, constraints và DDL thực sự được database production hỗ trợ.

Bài học hướng dẫn cách kiểm tra schema Envers qua nhiều lần nâng cấp, thay đổi audit strategy, revision entity, quan hệ và kiểu dữ liệu; cách kiểm tra những tính năng phụ thuộc Dialect; cách dùng Testcontainers và migrations thật; và cách tránh những test chỉ pass vì H2 hoặc Hibernate tự tạo schema trong môi trường thử nghiệm.

---

## 1. Phân biệt bốn thành phần trong một persistence deployment

Một hệ thống thường có các lớp:

```text
Java entities + Hibernate mappings
              |
              v
        Hibernate ORM
          + Envers
              |
              v
     SQL generation / Dialect
              |
              v
     JDBC driver + DBMS version
              |
              v
  Schema created by Flyway/Liquibase
```

Mỗi lớp có thể đúng riêng nhưng không tương thích với lớp còn lại.

Ví dụ:
- Entity khai báo `@Audited` nhưng migration chưa tạo `purchase_orders_AUD`.
- Migration tạo audit table nhưng thiếu `REV` hoặc khóa ghép đúng.
- Mapping dùng UUID native nhưng DBMS/schema đang lưu `CHAR(36)`.
- Envers chuyển sang `ValidityAuditStrategy` nhưng audit tables không có `REVEND`.
- Một test chạy trên H2 thành công trong khi production PostgreSQL dùng partial index, JSONB hoặc deferred constraints.
- Hibernate tự tạo schema cho test nên test không kiểm tra Flyway migration.

Vì vậy, integration test phải khởi động từ **database trống hoặc schema ở phiên bản cũ**, chạy migrations thật, bootstrap Hibernate/Envers với đúng Dialect và thực hiện thao tác ORM thực tế.

## 2. Envers tạo thêm những đối tượng schema nào?

Giả sử entity:

```java
@Entity
@Table(name = "purchase_orders")
@Audited
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;
    private BigDecimal total;
}
```

Một schema Envers phổ biến có dạng:

```text
purchase_orders
  id
  status
  total

purchase_orders_AUD
  id
  REV
  REVTYPE
  status
  total

REVINFO
  REV
  REVTSTMP
```

Tên thực tế phụ thuộc:
- `@AuditTable`.
- `org.hibernate.envers.audit_table_suffix` và prefix.
- Naming strategy.
- Schema/catalog mapping.
- Revision entity custom.
- Audit strategy.
- Hibernate/Envers version.

Không hard-code `_AUD` hoặc `REVINFO` vào tooling nếu dự án đã cấu hình tên khác.

### 2.1. Vai trò các cột thường gặp

| Cột | Vai trò |
| --- | --- |
| Entity ID columns | Nhận diện entity được audit |
| `REV` | Revision bắt đầu có hiệu lực của audit row |
| `REVTYPE` | Loại thay đổi: add, modify hoặc delete |
| Audited property columns | Giá trị các thuộc tính được audit |
| `REVEND` | Revision kết thúc hiệu lực khi dùng Validity strategy |
| Modified flags | Đánh dấu property thay đổi nếu bật `withModifiedFlag` |
| Revision metadata | Timestamp, actor/tenant metadata nếu custom revision entity |

`REVTYPE` thường được biểu diễn bằng mã Envers, không nên dựa vào một chuỗi tự đặt. API Envers cung cấp `RevisionType` để diễn giải.

### 2.2. Audit primary key thường là khóa ghép

Một audit table thường có primary key gồm entity identifier và revision:

```sql
PRIMARY KEY (id, REV)
```

Nếu entity có composite ID, audit primary key có thể gồm tất cả ID components cộng revision.

Không tạo PK chỉ trên `id`: một entity cần nhiều audit rows ở các revisions khác nhau.

### 2.3. Revision foreign key

Audit row thường tham chiếu revision metadata table qua `REV`. DDL và constraint cụ thể cần được kiểm tra theo Envers version, audit strategy và schema-generation settings.

Đừng tự giả định mọi association FK trong bảng live đều được tái tạo y hệt trong audit table. Audit schema có mục đích temporal riêng; một số historical references không nên bị FK ràng buộc vào live table có thể bị xóa.

## 3. Thống nhất phiên bản Hibernate ORM và Envers

Dependency phải được quản lý đồng bộ:

```kotlin
dependencies {
    implementation("org.hibernate.orm:hibernate-core")
    implementation("org.hibernate.orm:hibernate-envers")
}
```

Trong ứng dụng thật, dùng Hibernate BOM hoặc dependency management của Spring Boot để hai modules có version tương thích. Không nâng `hibernate-envers` độc lập lên một version khác `hibernate-core` chỉ để lấy một annotation hoặc bug fix.

Một test có thể in ra version runtime để hỗ trợ chẩn đoán:

```java
String hibernateVersion =
    org.hibernate.Version.getVersionString();

System.out.println(hibernateVersion);
```

Đừng dùng một số version trong test assertion nếu build cho phép patch upgrade; thay vào đó, ghi nhận version và chạy compatibility suite trên version được pin trong build.

### 3.1. Kiểm tra dependency graph

Trong Gradle:

```shell
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency hibernate-envers \
  --configuration runtimeClasspath
```

Mục tiêu là xác nhận:
- Một version runtime được chọn cho core.
- Envers cùng dòng version.
- Không có dependency transitively kéo một Hibernate version cũ.
- CI và production artifact dùng cùng dependency resolution.

Các lệnh chỉ phục vụ kiểm tra dependency; worker STEP 4 không chạy Gradle task cho dự án.

## 4. Flyway/Liquibase phải sở hữu schema production

Nếu dự án quản lý schema bằng migrations, cấu hình Hibernate thường dùng:

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
```

Hoặc dùng Liquibase theo dự án.

Tránh dùng `ddl-auto=update` để tự sửa schema production. Với Envers, schema audit có thể thay đổi cùng mapping và audit strategy; một thay đổi tự động không được review có thể gây mất dữ liệu hoặc tạo cấu trúc không nhất quán.

Trong integration test:
1. Khởi động DBMS đúng loại.
2. Chạy migrations.
3. Bootstrap Hibernate với `ddl-auto=validate`.
4. Persist/modify/delete audited entities.
5. Đọc lịch sử bằng `AuditReader`.
6. Kiểm tra constraints, indexes và dữ liệu audit.

### 4.1. `validate` không thay thế migration tests

Hibernate schema validation hữu ích để phát hiện một số khác biệt mapping/schema, nhưng không nên coi nó là bộ xác minh đầy đủ cho:
- Tất cả index và partial index.
- Mọi FK/unique constraint.
- Check constraints và deferrable behavior.
- Partitioning.
- Trigger/function.
- Extension của DBMS.
- Dữ liệu lịch sử và backfill.
- Các đối tượng schema do ứng dụng tự quản lý.

Hãy kiểm tra DDL bằng database metadata hoặc truy vấn catalog của DBMS khi invariant quan trọng.

## 5. Tạo reference schema Envers để đối chiếu

Một cách thực tế là dùng đúng Hibernate/Envers version, mapping và Dialect để tạo schema reference trong một database test riêng. Có thể dùng Hibernate schema tooling/export hoặc bootstrap test schema theo quy trình dự án.

Mục tiêu:
- Biết Hibernate/Envers mong đợi audit tables/cột nào.
- So sánh với Flyway/Liquibase migrations.
- Nhận diện thay đổi sau khi nâng Hibernate.
- Kiểm tra naming strategy và custom revision entity.

Không lấy DDL do Hibernate sinh tự động làm migration production mà không review. Generated DDL là **đầu vào để đối chiếu**, còn migrations cần được version-control và kiểm soát rõ.

### 5.1. Schema diff phải dùng cùng điều kiện

Khi so sánh reference schema với migration schema, giữ giống:
- Hibernate ORM và Envers version.
- Dialect và database version.
- Naming strategy.
- Default schema/catalog.
- `@AuditTable`, `@SecondaryTable`, collection mappings.
- Audit strategy và modified flags.
- Revision entity.
- Custom types/converters.

Nếu một trong các yếu tố khác nhau, diff có thể phản ánh configuration drift thay vì lỗi migration.

## 6. Migration thêm một entity vào Envers

Giả sử trước đây `Customer` chưa được audit:

```java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;
    private String displayName;
}
```

Sau đó bật:

```java
@Entity
@Audited
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;
    private String displayName;
}
```

Migration cần tạo audit table và bảo đảm revision table tồn tại:

```sql
CREATE TABLE customers_AUD (
    id BIGINT NOT NULL,
    REV INTEGER NOT NULL,
    REVTYPE SMALLINT,
    displayName VARCHAR(255),
    PRIMARY KEY (id, REV)
);
```

Đây chỉ là DDL minh họa; kiểu `REV`, tên cột và FK cần khớp revision entity, generator, naming strategy và database cụ thể.

### 6.1. Bật audit không tạo lịch sử quá khứ

Nếu Customer đã có 5 năm dữ liệu nhưng Envers chỉ được bật hôm nay, các thay đổi trước thời điểm đó không tự xuất hiện trong `_AUD`.

Có thể:
- Chấp nhận audit bắt đầu từ deployment mới.
- Tạo baseline revision cho current state với quy trình có kiểm soát.
- Backfill từ một nguồn lịch sử độc lập đáng tin cậy.

Không tạo hàng loạt revision giả bằng cách copy current row vào mọi revision cũ. Điều đó sẽ trình bày sai lịch sử.

## 7. Thêm một audited property: cập nhật cả live và audit schema

Entity:

```java
@Audited
@Entity
public class Customer {
    @Id
    private Long id;

    private String displayName;

    private String preferredLanguage;
}
```

Migration thường cần thêm column vào cả:
- `customers.preferred_language`.
- `customers_AUD.preferred_language`.

Ví dụ:

```sql
ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(20);

ALTER TABLE customers_AUD
ADD COLUMN preferred_language VARCHAR(20);
```

Nếu field có NOT NULL/default:
- Xác định giá trị cho rows live cũ.
- Xác định ý nghĩa lịch sử của các audit rows cũ.
- Không tự điền giá trị hiện tại vào mọi revision nếu giá trị đó chưa được biết ở thời điểm lịch sử.

### 7.1. Không bịa historical values khi backfill

Giả sử `preferredLanguage` chỉ được thêm vào năm 2026. Việc backfill `"vi"` vào tất cả audit rows từ năm 2020 khiến lịch sử trông như người dùng luôn có preference đó.

Các lựa chọn trung thực:
- Giữ `NULL` cho revisions trước thời điểm field được biết.
- Dùng một trạng thái “unknown” nếu domain phân biệt rõ.
- Tạo một baseline revision.
- Lưu metadata về thời điểm bắt đầu thu thập thuộc tính.

Schema migration có thể đúng kỹ thuật nhưng vẫn làm sai ý nghĩa dữ liệu nếu backfill không đúng.

## 8. Rename, remove và thay đổi `@NotAudited`

Khi rename field:

```java
private String displayName;
```

thành:

```java
private String legalName;
```

hãy xem:
- Live column có rename hay copy/backfill?
- Audit column có rename tương ứng?
- Các historical rows có cần giữ giá trị cũ?
- Envers naming strategy có thay đổi column name không?
- Code đọc revisions cũ có cần compatibility mapping?

Khi bỏ `@Audited` hoặc thêm `@NotAudited`, Envers có thể ngừng ghi field đó trong các revisions tương lai, nhưng các cột/giá trị lịch sử cũ không tự biến mất. Việc xóa cột audit là quyết định retention và compatibility, không chỉ là refactor Java.

### 8.1. Thay đổi mapping của association

Nếu chuyển relation từ audited target sang:

```java
@Audited(targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
```

hoặc ngược lại, hãy kiểm tra:
- Historical FK values đã có.
- Target audit tables có đầy đủ history hay chưa.
- Target bị hard-delete có được resolve không.
- Hibernate version có thay đổi semantics.
- API trả historical graph có chấp nhận current target không.

Một thay đổi annotation có thể thay đổi kết quả truy vấn lịch sử dù không có migration DDL lớn.

## 9. Migration audit strategy: Default và Validity

Envers có hai audit strategies phổ biến:

- `DefaultAuditStrategy`: truy vấn phiên bản có hiệu lực bằng revision bắt đầu, thường cần tìm revision lớn nhất không vượt quá revision mục tiêu.
- `ValidityAuditStrategy`: lưu thêm revision kết thúc để biểu diễn khoảng hiệu lực của audit row.

Minh họa:

```text
Default:
  id=42, REV=1, status=NEW
  id=42, REV=8, status=PAID

Validity:
  id=42, REV=1, REVEND=8,  status=NEW
  id=42, REV=8, REVEND=NULL, status=PAID
```

Cấu hình audit strategy qua Envers settings, ví dụ:

```properties
org.hibernate.envers.audit_strategy=\
org.hibernate.envers.strategy.ValidityAuditStrategy
```

Tên class và setting cần khớp Envers version đang dùng.

### 9.1. Bật Validity cần schema mới

Audit tables phải có cột revision-end theo mapping/configuration, thường là `REVEND`; nếu bật lưu timestamp của revision kết thúc, có thể cần thêm `REVEND_TSTMP`.

Migration phải:
1. Thêm cột với kiểu tương ứng revision ID.
2. Tạo index phù hợp nếu cần.
3. Xác định cách backfill các khoảng hiệu lực cũ.
4. Xác minh row cuối mỗi entity có end revision null.
5. Kiểm tra các audit queries ở revision trước/sau chuyển đổi.

Chỉ đổi property mà không đổi schema sẽ dẫn tới lỗi SQL khi Envers cố cập nhật revision kết thúc.

### 9.2. Backfill REVEND không phải điền một hằng số

Với mỗi entity identifier, audit rows cần được sắp theo `REV`; một row kết thúc tại revision bắt đầu của row tiếp theo, theo semantics Validity strategy.

Pseudo SQL:

```sql
-- Pseudocode: syntax differs by DBMS
UPDATE entity_AUD current_row
SET REVEND = (
    SELECT MIN(next_row.REV)
    FROM entity_AUD next_row
    WHERE next_row.id = current_row.id
      AND next_row.REV > current_row.REV
);
```

Với composite IDs, partition/group condition phải chứa **mọi ID components**. Nếu có delete revisions hoặc nhiều bảng/association audit, backfill phải theo đúng audit strategy semantics và kiểm thử trước trên bản sao dữ liệu.

Không chạy một update chung chỉ dựa trên `id` nếu entity có composite key.

### 9.3. Chi phí write khác nhau

Default strategy thường thêm audit rows khi entity thay đổi. Validity strategy còn cập nhật audit row trước đó để đặt `REVEND`. Điều này có thể tăng write work, lock contention và deadlock scenarios trên entities thay đổi nhiều.

Test concurrency và query plans trước khi đổi strategy vì lý do performance.

## 10. Custom revision entity và migration REVINFO

Envers mặc định dùng revision metadata entity/table. Ứng dụng có thể custom revision entity để thêm actor, tenant hoặc correlation metadata.

Ví dụ:

```java
@Entity
@Table(name = "audit_revision")
@RevisionEntity(UserRevisionListener.class)
public class AuditRevision {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    private String actorReference;
    private String requestId;
}
```

Imports annotation Envers cần dùng đúng package/version. `UserRevisionListener` phải implement contract revision listener tương ứng.

Khi chuyển từ revision table mặc định sang custom:
- Cập nhật mapping revision entity.
- Migration tạo bảng/cột mới.
- Kiểu revision number phải tương thích với `REV` trong mọi audit table.
- Generator/sequence phải được tạo đúng.
- Foreign keys hoặc revision lookups phải trỏ đúng table.
- Existing revisions cần được migrate hoặc giữ compatibility.

### 10.1. Không đổi revision ID type tùy tiện

Nếu audit tables dùng `REV INTEGER` mà custom revision entity chuyển sang `Long/BIGINT`, phải migrate toàn bộ audit tables, sequence và foreign keys có liên quan. Kiểm tra overflow và database generator semantics.

Revision number là khóa được tham chiếu rộng; thay đổi nó có thể ảnh hưởng toàn bộ lịch sử.

### 10.2. Actor metadata phải có fallback

Background jobs, batch imports và system operations không có logged-in user. Revision listener cần biểu diễn actor system/job một cách rõ ràng, không dereference request context null.

Không ghi token hoặc PII không cần thiết vào revision table. Revision metadata thường được giữ lâu và có thể được truy cập qua nhiều audit queries.

## 11. Thêm modified flags

Envers có thể lưu flags cho biết property nào thay đổi:

```java
@Audited(withModifiedFlag = true)
@Entity
public class Customer {
    @Id
    private Long id;
    private String displayName;
    private String status;
}
```

Audit table có thể có các columns tương tự:

```text
displayName
displayName_MOD
status
status_MOD
```

Tên suffix có thể cấu hình. Khi bật global hoặc per-entity/per-property modified flags, migration phải thêm đúng columns cho các audit tables tương ứng.

Test:
- Thay đổi `displayName`, xác nhận flag đúng.
- Chỉ thay `status`, xác nhận flag khác.
- Không thay field, xác nhận semantics flag.
- Test null-to-value và value-to-null.
- Test collection changes nếu dựa vào modified flags cho collection.

Không chỉ kiểm tra column tồn tại; hãy query revisions và xác nhận flag có ý nghĩa đúng.

## 12. Delete revisions và `store_data_at_delete`

Khi audited entity bị xóa, Envers ghi revision có loại DELETE (`DEL`). Setting phổ biến:

```properties
org.hibernate.envers.store_data_at_delete=true
```

có thể lưu các property values ở delete revision theo behavior Envers.

Migration/test cần xem:
- Audit columns có tồn tại.
- Delete row có đúng `REVTYPE`.
- Property values có null hay giữ dữ liệu theo setting.
- Historical `AuditReader.find()` trước/sau delete.
- Associations tới target bị xóa.
- Storage/PII implications.

Đừng mặc định xóa live row đồng nghĩa audit row chứa đầy đủ snapshot của entity bị xóa; behavior phụ thuộc setting và version.

## 13. Audit join tables và collection tables

Các mapping:
- `@ManyToMany`.
- `@ElementCollection`.
- Unidirectional `@OneToMany` với `@JoinColumn`.
- Embeddable collections.
- Secondary tables.

có thể tạo audit tables riêng hoặc audit join tables theo Envers mapping.

Ví dụ live table:

```text
customer_roles
  customer_id
  role_id
```

Audit storage có thể là:

```text
customer_roles_AUD
  customer_id
  role_id
  REV
  REVTYPE
```

Schema thực tế phụ thuộc association mapping, naming strategy, collection type và Envers version.

### 13.1. Kiểm thử membership, không chỉ kiểm thử entity fields

Scenario:
1. Tạo Customer và Role.
2. Gán Role A.
3. Commit và lưu revision.
4. Thêm Role B.
5. Commit và lưu revision.
6. Xóa Role A khỏi collection.
7. Commit.
8. Đọc Customer tại ba revisions và assert tập role IDs.

Nếu chỉ assert `Customer_AUD` có row mà không kiểm tra audit join table, test có thể bỏ sót lỗi collection history.

### 13.2. `@AuditJoinTable` cần migration tương ứng

Một số unidirectional collection mappings cần audit join table. Nếu đặt tên/schema tùy chỉnh qua `@AuditJoinTable`, migration phải dùng đúng tên và columns. Đừng nhầm audit join table với live JPA `@JoinTable`.

## 14. Secondary tables và inheritance

Nếu entity dùng:
- `@SecondaryTable`.
- `@Inheritance`.
- `@MappedSuperclass`.
- `@Embeddable`.
- Joined inheritance hoặc table-per-class.

Envers schema có thể phức tạp hơn một bảng `_AUD` đơn giản.

Test cần:
- Mỗi bảng live có audit representation phù hợp.
- PK columns tương ứng được giữ.
- Inheritance discriminator/joins được xử lý đúng.
- Audit queries cho subclass và base type trả kết quả mong đợi.
- Migration thêm field ở superclass/embeddable cập nhật đúng audit tables.
- Không xóa audit column dùng chung khi chỉ một subclass bỏ audit.

Không suy schema audit chỉ từ tên class entity; hãy dùng generated reference schema và integration test.

## 15. Composite identifiers trong audit schema

Entity có:

```java
@EmbeddedId
private CustomerDocumentId id;
```

thì audit table cần chứa mọi ID components và revision:

```text
customer_document_AUD
  tenant_id
  customer_no
  document_no
  REV
  REVTYPE
  ...
```

Primary key thường tương ứng:

```sql
PRIMARY KEY (
    tenant_id,
    customer_no,
    document_no,
    REV
)
```

Test:
- Hai entities cùng một component nhưng khác component còn lại.
- Query history bằng toàn bộ ID.
- Audit rows không ghi đè nhau.
- Revision join đúng.
- Validity backfill partition đúng theo toàn bộ composite ID.

Composite ID migration dễ sai khi chỉ thêm một key column vào live table mà quên `_AUD`, join tables hoặc indexes.

## 16. Dialect là gì và nó quyết định những gì?

Hibernate `Dialect` mô tả cách Hibernate giao tiếp SQL với một họ database. Nó ảnh hưởng tới:
- SQL syntax.
- Identity/sequence support.
- Limit/offset syntax.
- Locking clauses.
- Type mappings.
- Generated key retrieval.
- Functions/operators.
- DDL capabilities.
- Batch/returning behavior.
- Null ordering và một số query transformations.

Dialect không thay thế việc biết **DBMS product và version cụ thể**. Một database cùng họ nhưng khác version có thể hỗ trợ feature khác nhau; extension/plugin cũng có thể làm thay đổi capabilities.

### 16.1. Không dùng H2 làm đại diện cho mọi Dialect

H2 có thể chạy một số SQL tương tự PostgreSQL/Oracle/MySQL, nhưng compatibility mode không biến nó thành database đó.

Khác biệt thường xuất hiện ở:
- UUID, JSON, ARRAY.
- Identity/sequence.
- Partial/functional indexes.
- Deferred constraints.
- DDL transactional behavior.
- Locking/isolation.
- `RETURNING`.
- Timestamp/time zone.
- Quoted identifiers.
- Collation/case sensitivity.
- Generated columns.

Dùng Testcontainers với đúng DBMS cho những behavior phụ thuộc Dialect.

## 17. Chọn Dialect theo runtime database

Hibernate hiện đại thường có thể suy ra Dialect từ JDBC metadata. Nếu phải cấu hình thủ công, dùng class phù hợp với DBMS/version và Hibernate line đang chạy.

Không copy một class Dialect cũ từ Hibernate 5 vào Hibernate 6/7 chỉ vì tên tương tự. Một số dialect-specific classes đã thay đổi, bị deprecated hoặc được hợp nhất theo version.

Test startup phải xác nhận:
- JDBC URL trỏ đúng DBMS.
- Driver version phù hợp.
- Hibernate nhận đúng Dialect.
- Database server version đúng expectation.
- Migration và schema dùng cùng database.
- Không có test profile override vô tình ép Dialect khác.

### 17.1. Không chỉ assert tên Dialect

Một assertion về class name không chứng minh DB server hỗ trợ một extension hoặc feature. Kiểm tra capability thực tế bằng DDL/query trên server version đang chạy.

Ví dụ, PostgreSQL JSONB support còn phụ thuộc:
- PostgreSQL server version.
- JDBC driver.
- Hibernate JSON mapping.
- Schema column type.
- Migrations.
- Query operators/indexes.

## 18. Kiểm thử ID generators theo Dialect

Các DBMS có khác biệt về:
- `IDENTITY`/auto-increment syntax.
- Sequence creation/next value syntax.
- Pooled sequence allocation.
- Generated key retrieval.
- Batch insert support.
- Sequence cache and gaps.

Migration có thể tạo sequence:

```sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 50;
```

Nếu mapping:

```java
@SequenceGenerator(
    name = "orderSeq",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
```

thì generator increment và optimizer assumptions phải tương thích.

Test trên DBMS thật:
1. Persist nhiều entities.
2. Flush/commit.
3. Kiểm tra IDs unique.
4. Restart EntityManagerFactory.
5. Persist tiếp, xác nhận không trùng.
6. Dùng hai transactions/instances đồng thời nếu throughput quan trọng.
7. Rollback và chấp nhận sequence gaps.

Không yêu cầu IDs liên tục vì sequence caching/allocation/rollback có thể để gaps.

## 19. Kiểu UUID và migration audit columns

Java UUID có thể được lưu bằng:
- Native UUID type.
- Binary representation.
- Character string.

Ví dụ entity:

```java
@Id
private UUID id;
```

Kiểu column được chọn theo Hibernate version, Dialect và mapping configuration. Live table và audit table phải dùng type tương thích.

Test:
- Insert UUID.
- Đọc lại bằng `find`.
- Đọc historical revision.
- Kiểm tra schema metadata.
- Test index/PK.
- Kiểm tra native SQL binding nếu dùng.
- Kiểm tra migration upgrade từ kiểu cũ.

Không đổi `CHAR(36)` sang native UUID chỉ bằng cách đổi Java mapping; cần migration chuyển dữ liệu và update audit schema cùng lúc.

## 20. Boolean và converter phụ thuộc DBMS

Một Java boolean có thể map thành:
- Native `BOOLEAN`.
- `BIT`.
- Numeric.
- `CHAR` qua converter.

Nếu entity có:

```java
@Convert(converter = YesNoConverter.class)
private Boolean active;
```

audit table cũng phải lưu biểu diễn tương thích converter. Migration phải thêm cột đúng SQL type/length và test cả true/false/null nếu mapping cho phép null.

Đừng giả định `BOOLEAN` là SQL type được mọi DBMS hỗ trợ giống nhau. Một số hệ thống dùng `NUMBER(1)` hoặc `CHAR(1)`.

## 21. Decimal precision và scale trong lịch sử

Một property:

```java
@Column(precision = 19, scale = 4)
private BigDecimal amount;
```

cần audit column có precision/scale phù hợp. Nếu live table dùng `NUMERIC(19,4)` nhưng audit table chỉ `NUMERIC(10,2)`, lịch sử có thể:
- Tràn giá trị.
- Làm tròn.
- Báo lỗi khi insert audit row.
- Khác kết quả giữa DBMS.

Test:
- Giá trị biên lớn nhất theo domain.
- Số chữ số thập phân tối đa.
- Rounding policy.
- Null handling.
- Đọc lại historical values bằng `BigDecimal.compareTo` hoặc assertion phù hợp scale contract.

Không dùng `double` để xác nhận dữ liệu tài chính.

## 22. Timestamp, timezone và độ chính xác

Java types:
- `Instant`.
- `LocalDateTime`.
- `OffsetDateTime`.
- `ZonedDateTime`.

có semantics khác nhau. Dialect có thể map chúng vào timestamp without time zone, timestamp with time zone hoặc representation khác theo Hibernate settings.

Revision timestamp của Envers cũng cần được kiểm tra:
- Unit milliseconds/epoch semantics.
- DB column type.
- Timezone normalization.
- Precision (seconds/millis/micros).
- Clock source.
- DST boundary.
- Serialization khi đọc revision metadata.

### 22.1. Test round-trip, không chỉ test column type

Tạo timestamp có offset khác UTC, persist, commit, đọc lại bằng context mới và assert **instant semantics** nếu domain yêu cầu instant. Đừng so sánh `toString()` nếu format/offset representation khác nhưng instant tương đương.

Test lịch sử:
1. Persist entity tại một timestamp.
2. Update timestamp.
3. Đọc revision cũ.
4. So sánh với giá trị mong đợi sau round-trip DB.

### 22.2. Envers revision timestamp khác entity timestamp

`@RevisionTimestamp` ghi thời điểm revision theo Envers. Nó không tự bằng `createdAt` hoặc `updatedAt` của entity. Không dùng hai field thay thế nhau trong báo cáo pháp lý nếu semantics khác nhau.

## 23. JSON, ARRAY và custom JDBC types

Hibernate có thể hỗ trợ JSON mapping theo version/Dialect, ví dụ:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb")
private Map<String, Object> metadata;
```

Đoạn này minh họa một mapping PostgreSQL-oriented; `columnDefinition` và `SqlTypes.JSON` phải phù hợp DBMS/version.

Test:
- Live table column type.
- Audit table column type.
- Insert JSON object.
- Modify nested content.
- Commit và đọc revision cũ/mới.
- Query JSON operators nếu application dùng.
- Index GIN/functional indexes nếu cần.
- Migration thay đổi JSON shape.
- Null JSON vs SQL NULL semantics.

### 23.1. Không chỉ test serialize/deserialize

Envers phải lưu giá trị type đó vào audit table. Một custom type có thể hoạt động với live entity nhưng không hoạt động như kỳ vọng khi copy value sang audit entity/table.

Kiểm tra end-to-end qua `AuditReader`, không chỉ Jackson unit test.

### 23.2. ARRAY và database-specific types

SQL ARRAY, enum types, spatial types, ranges hoặc vendor-specific types phụ thuộc Dialect, driver và custom mapping. Testcontainers phải dùng DBMS hỗ trợ thật; H2 compatibility mode không chứng minh production type behavior.

## 24. LOB, binary và large text trong audit schema

Nếu entity có:
- `@Lob byte[]`.
- `Blob`/`Clob`.
- Large text.
- Document content.

audit history có thể làm dữ liệu tăng nhanh. Test:
- Live/audit column types.
- Streaming vs eager materialization.
- JDBC driver limits.
- Transaction duration.
- Revision read behavior.
- Retention/partitioning.
- Storage duplication.

Không mặc định Envers là kho lưu file tối ưu. Thường nên audit metadata, content hash/version và object storage reference theo thiết kế; nội dung file cần retention riêng.

## 25. Identifier quoting, reserved words và naming strategy

Một entity field tên `order`, `user`, `group` có thể xung đột reserved words của DBMS. Tên được tạo ra có thể cần quoting.

Hibernate naming strategies cũng có thể chuyển:
- `purchaseOrder` thành `purchase_order`.
- `REVTYPE` theo configured audit naming.
- Join columns thành tên khác.
- Schema/catalog names.

Migration viết thủ công phải khớp tên thực tế sau physical naming strategy.

Test nên kiểm tra:
- Tên bảng/cột qua JDBC metadata.
- Schema/catalog đúng.
- Case sensitivity và quoted identifiers.
- Audit table/column naming.
- Index/constraint names trong giới hạn DBMS.

Không đổi naming strategy giữa các release mà không có migration tương ứng.

## 26. Giới hạn độ dài tên index và constraint

Một số DBMS giới hạn identifier length. Hibernate-generated names hoặc migration-generated names có thể bị truncate/đụng nhau.

Hãy đặt tên constraint/index tường minh và ngắn, ổn định trong migrations. Test trên đúng DBMS:
- Tên index thực tế.
- Constraint uniqueness.
- FK names.
- Schema diff sau migration.
- Không có hai tên sau truncate bị trùng.

Không dựa vào generated random names nếu migration sau cần drop/alter constraint.

## 27. Partial index, functional index và Dialect-specific DDL

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_customer_aud_revision
ON customers_AUD (id, REV DESC);
```

Hoặc partial index:

```sql
CREATE INDEX idx_orders_active_created
ON purchase_orders (tenant_id, created_at DESC, id DESC)
WHERE deleted = FALSE;
```

Một số DBMS hỗ trợ partial indexes, một số dùng filtered indexes hoặc function-based indexes với syntax khác.

Envers audit queries có thể cần indexes theo:
- Entity identifier.
- `REV`.
- `REVEND`.
- Association key columns.
- Tenant key nếu custom revision/audit model có tenant scope.

Không tạo index chỉ vì một ví dụ trên internet; đo query plans trên audit tables có cardinality tương đương production.

### 27.1. Index của audit table không phải index của live table

Query `AuditReader.find()` có access pattern khác query current entity. Audit table có thể tăng nhiều rows trên một ID. Cần index theo query shape thực tế, không sao chép toàn bộ live indexes vào `_AUD` một cách máy móc.

## 28. Deferrable constraints và khác biệt transaction

PostgreSQL có thể hỗ trợ deferrable FK/unique constraints:

```sql
CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id)
DEFERRABLE INITIALLY DEFERRED
```

Một số DBMS không có cùng semantics hoặc syntax.

Điều này ảnh hưởng:
- Khi lỗi được phát hiện (statement/flush/commit).
- Thứ tự insert trong graph.
- Migration và data backfill.
- Integration test transaction outcome.

Không viết test portable giả định mọi DBMS kiểm tra FK ở cùng thời điểm. Nếu ứng dụng phụ thuộc deferred constraints, đó là một capability cần ghi rõ trong DBMS support matrix.

## 29. DDL transactional behavior khác nhau

Một migration gồm:

```sql
ALTER TABLE ...
CREATE INDEX ...
UPDATE ...
```

có thể được rollback nguyên khối trên một DBMS, nhưng DBMS khác có DDL statement tự commit hoặc hạn chế transactional DDL.

Flyway/Liquibase có cấu hình và hành vi khác theo database. Một migration thất bại có thể để lại một phần DDL đã áp dụng trên DBMS không hỗ trợ transactional DDL như mong đợi.

Test migration:
- Thành công trên database trống.
- Thành công từ schema phiên bản cũ.
- Failure injection nếu migration phức tạp.
- Kiểm tra trạng thái schema sau failure.
- Xác minh retry/repair procedure theo tool và DBMS.
- Không giả định mọi DDL được rollback giống DML.

## 30. Partitioning audit tables

Audit tables có thể tăng rất lớn. Partitioning theo revision/time có thể hữu ích, nhưng cần kiểm tra:
- Primary key có bao gồm partition key theo yêu cầu DBMS không.
- Unique constraints trên partitioned table.
- Revision FK.
- Envers-generated SQL.
- `AuditReader` query predicates có pruning partition không.
- Retention/drop partition có làm mất historical graph cần giữ không.
- Index/local vs global indexes theo DBMS.

Không partition `_AUD` chỉ vì bảng lớn; cần benchmark và kiểm thử Envers queries với đúng partition scheme.

## 31. Migration thay đổi entity identifier

Thay đổi:
- `Long` sang `UUID`.
- Một ID đơn sang composite ID.
- Thành phần composite key.
- Column type/precision.
- PK/FK column names.

là thay đổi có ảnh hưởng tới:
- Live table PK.
- Foreign keys.
- Mọi audit table của entity.
- Audit join tables tham chiếu entity.
- Revision queries.
- Cache keys.
- External references.
- Import/export jobs.

Migration phải giữ được lịch sử hoặc định nghĩa rõ điểm bắt đầu lịch sử mới. Không drop/recreate audit table để làm mapping mới khởi động được.

## 32. Kiểm thử migration từ version cũ, không chỉ database trống

Hai luồng CI khác nhau:

```text
Fresh install:
  Empty DB
    -> all migrations
    -> latest schema
    -> Hibernate validate
    -> ORM + Envers tests

Upgrade:
  DB at version N
    -> seed representative live/audit data
    -> migrate N to N+1
    -> Hibernate validate
    -> read old revisions
    -> write new revision
    -> verify constraints/data
```

Fresh install bắt lỗi migration chain tổng thể. Upgrade test bắt lỗi mất dữ liệu hoặc backfill sai ở schema đã tồn tại.

Một migration có thể pass trên DB trống nhưng fail khi table có rows, indexes, FKs hoặc audit history thật.

## 33. Giữ historical data khi migration

Một quy trình upgrade:
1. Snapshot/backup test database có dữ liệu đại diện.
2. Chạy migration mới.
3. Kiểm tra row counts và key values.
4. Dùng `AuditReader` đọc một số revisions cũ.
5. Tạo thay đổi mới qua Hibernate.
6. Đọc revision mới.
7. So sánh lịch sử trước/sau migration.
8. Kiểm tra các entity đã delete và association history.
9. Xác minh audit strategy metadata.
10. Kiểm tra rollback/recovery plan.

Đừng chỉ assert `SELECT COUNT(*)` trên `_AUD` không đổi. Một migration hợp lệ có thể thêm metadata/columns; điều quan trọng là historical semantics không bị phá.

## 34. Test `REVINFO` và revision sequence

Khi custom revision entity hoặc đổi generator:
- Insert nhiều revisions.
- Kiểm tra revision number unique.
- Kiểm tra timestamp.
- Kiểm tra actor/request metadata.
- Restart factory/process.
- Chạy hai transactions tạo revisions đồng thời.
- Xác nhận không trùng revision IDs.
- Kiểm tra revision FK từ nhiều audit tables.

Không yêu cầu revision numbers liên tục. Sequence gaps do rollback/concurrency/allocation có thể bình thường.

### 34.1. Revision không nhất thiết bằng một revision cho mỗi entity

Một transaction thay đổi nhiều audited entities có thể chia sẻ revision. Test phải kiểm tra transaction-level grouping, không assert mỗi entity có một revision number riêng.

## 35. Test Envers history bằng `AuditReader`

Ví dụ:

```java
AuditReader reader =
    AuditReaderFactory.get(entityManager);

List<Number> revisions =
    reader.getRevisions(PurchaseOrder.class, orderId);

PurchaseOrder atCreation =
    reader.find(
        PurchaseOrder.class,
        orderId,
        revisions.get(0)
    );
```

Test:
1. Persist entity và commit.
2. Update một field và commit.
3. Delete entity và commit.
4. Lấy revisions.
5. Assert revision count/types phù hợp.
6. Đọc historical snapshots trước/sau update.
7. Đọc trạng thái trước delete.
8. Kiểm tra behavior tại/sau delete theo API semantics.

Dùng EntityManager mới sau mỗi transaction để tránh L1 state làm nhiễu historical reads.

### 35.1. Test đúng revision type

Dùng API `forRevisionsOfEntity()` để lấy entity snapshot, revision entity và `RevisionType` khi cần. Không hard-code số nguyên mã revision type vào test nếu API enum đã có.

## 36. Test rollback của audit rows

Một test quan trọng:

```java
tx.begin();

PurchaseOrder order = new PurchaseOrder(...);
em.persist(order);
em.flush();

tx.rollback();
```

Sau đó:
- Order live row không tồn tại.
- Audit row thuộc transaction rollback không tồn tại.
- Revision metadata được tạo trong transaction đó cũng không được commit theo cùng DB transaction.
- Sequence/revision IDs có thể có gaps.

Nếu audit data vẫn còn, kiểm tra:
- Envers có đang dùng cùng datasource/transaction không.
- Có custom listener ghi audit bằng transaction khác không.
- Có trigger hoặc CDC riêng không.
- Có outbox/event consumer độc lập không.

## 37. Test bulk DML và native SQL không đi qua Envers entity lifecycle

Ví dụ:

```java
em.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    where o.status = :oldStatus
    """)
    .setParameter("status", OrderStatus.CANCELLED)
    .setParameter("oldStatus", OrderStatus.DRAFT)
    .executeUpdate();
```

Bulk JPQL/HQL và native SQL không đi qua vòng đời managed entity từng row như việc load entity rồi thay field. Vì vậy Envers không tự tạo đầy đủ per-entity revisions cho những writes đó.

Test nên xác nhận behavior này trong thiết kế hiện tại, hoặc chứng minh một audit mechanism khác bao phủ bulk writer.

Đừng dùng bulk UPDATE trong migration rồi mong Envers tự ghi lịch sử của từng row; migration DDL/DML thường là một hoạt động ngoài ORM.

## 38. Test association target và historical graph

Với quan hệ audited:
- Tạo owner và target.
- Commit.
- Thay target association.
- Update target fields.
- Commit các bước riêng.
- Đọc owner ở từng revision.
- Assert FK và target snapshot đúng theo `RelationTargetAuditMode`.

Với `NOT_AUDITED` target:
- Xác nhận owner association được lưu theo audit mapping.
- Thay target live row.
- Đọc historical owner.
- Xác nhận target hiện tại theo semantics đã chọn.
- Xóa target và test missing-target behavior.

Khi nâng Hibernate, đặc biệt kiểm tra thay đổi version-specific về `NOT_AUDITED` target mode.

## 39. Test Envers migration khi thêm collection audit

Nếu thêm:

```java
@OneToMany(mappedBy = "order")
@Audited
private List<OrderLine> lines;
```

migration có thể cần audit table/association metadata tương ứng.

Test:
1. Migrate schema.
2. Persist Order + Line.
3. Commit.
4. Add Line mới, commit.
5. Remove Line, commit.
6. Đọc collection ở các revisions.
7. Assert membership.
8. Kiểm tra composite PK/index/FK của audit collection table.
9. Test orphanRemoval và cascade riêng.
10. Xác nhận native/bulk collection changes có semantics khác.

Không chỉ kiểm tra bảng `_AUD` của parent có tồn tại.

## 40. Testcontainers với đúng DBMS production

Ví dụ PostgreSQL:

```java
@Testcontainers
@SpringBootTest
class EnversMigrationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        registry.add("spring.flyway.enabled", () -> "true");
    }
}
```

Đây là skeleton; cần dependencies, imports, migrations và application configuration thực tế.

Lợi ích:
- Chạy migration thật.
- Dùng PostgreSQL dialect/driver thật.
- Kiểm tra sequence, UUID, JSONB, partial indexes, constraints.
- Thực thi Envers audit queries trên đúng DBMS.
- Phát hiện SQL khác H2.

Pin image version/digest phù hợp CI policy. Không dùng tag `latest` cho một integration suite cần reproducibility.

## 41. Test nhiều Dialects bằng một test matrix

Nếu ứng dụng chính thức hỗ trợ nhiều DBMS, mỗi dialect cần một test suite riêng:

| Capability | PostgreSQL | MySQL | Oracle | SQL Server |
| --- | --- | --- | --- | --- |
| Sequence/identity | Theo version/config | Auto-increment và sequence theo version | Identity/sequence | Identity/sequence |
| Partial/filtered index | Partial index | Khác cách hỗ trợ | Function-based/conditional pattern | Filtered index |
| JSON | JSON/JSONB | JSON | JSON types theo version | JSON support theo version |
| Boolean | Native boolean | Kiểu phụ thuộc DB/version | Thường numeric/char mapping | BIT |
| Deferred FK | Có | Khác/giới hạn | Có semantics riêng | Khác |
| DDL transaction | Có giới hạn theo statement | Nhiều DDL implicit commit | DDL transaction khác | Transactional DDL với caveats |
| UUID | Native UUID | Binary/char/native theo version | Raw/char mapping | Uniqueidentifier |

Bảng là định hướng, không thay thế kiểm tra version cụ thể. Một DBMS có thể thay đổi khả năng qua major release.

### 41.1. Không giả lập nhiều Dialects trên cùng H2

Chạy Hibernate với class Dialect khác trong khi JDBC URL vẫn là H2 không chứng minh tương thích database. Driver, SQL parser, server functions, constraints và DDL vẫn là H2.

Phải chạy container/instance thật cho từng DBMS được hỗ trợ.

## 42. Kiểm tra schema bằng JDBC metadata

JDBC `DatabaseMetaData` có thể kiểm tra:
- Tables.
- Columns.
- Types.
- Primary keys.
- Imported/exported keys.
- Index metadata (mức độ chi tiết tùy driver).

Ví dụ:

```java
DatabaseMetaData meta =
    connection.getMetaData();

try (ResultSet columns = meta.getColumns(
        connection.getCatalog(),
        schemaName,
        "purchase_orders_AUD",
        null
)) {
    while (columns.next()) {
        String columnName = columns.getString("COLUMN_NAME");
        int sqlType = columns.getInt("DATA_TYPE");
        String typeName = columns.getString("TYPE_NAME");
        int precision = columns.getInt("COLUMN_SIZE");
        int scale = columns.getInt("DECIMAL_DIGITS");
    }
}
```

Tên table/schema và chữ hoa/thường phụ thuộc driver/DBMS. JDBC metadata có thể chuẩn hóa tên; test nên dùng quy tắc case của database.

### 42.1. Catalog queries cho invariant đặc thù

Đối với PostgreSQL, có thể truy vấn `pg_catalog`/`information_schema` để xác nhận:
- Partial index predicate.
- Constraint deferrability.
- Partitioning.
- Index method.
- Column native types.
- Sequence increment/cache.
- FK definitions.

Những assertions này là DB-specific và nên đặt trong test module tương ứng, không giả vờ portable.

## 43. Test query plans cho historical reads

Một số Envers queries có thể trở nên đắt khi audit table lớn.

Đo:
- `AuditReader.find()` theo entity ID/revision.
- `getRevisions()`.
- `forRevisionsOfEntity()` có filters.
- Association traversal.
- Collection history.
- Validity strategy queries.
- Historical queries qua composite IDs.

Với PostgreSQL, dùng `EXPLAIN (ANALYZE, BUFFERS)` trên SQL tương đương để xem index usage, rows scanned, sort và buffer reads.

Không assert toàn bộ plan text trong test đơn giản vì plan có thể thay đổi theo statistics/version. Thay vào đó, có benchmark/performance test với ngưỡng và dataset ổn định, còn functional test kiểm tra kết quả đúng.

## 44. Test concurrent revisions và locking

Hai transactions cùng sửa một audited entity có thể:
- Cạnh tranh optimistic version.
- Tạo revisions theo thứ tự commit/ID allocation khác nhau.
- Cập nhật `REVEND` trong Validity strategy.
- Tạo lock contention trên revision sequence/table.
- Gặp deadlocks khi nhiều entities được update theo thứ tự khác nhau.

Test:
1. Dùng hai EntityManagers/connections.
2. Load cùng entity/version.
3. Cập nhật từ cả hai.
4. Đồng bộ bằng barrier.
5. Commit một transaction.
6. Xác nhận transaction còn lại theo optimistic locking policy.
7. Đọc revisions sau cùng.
8. Xác nhận historical order và validity ranges không chồng lấn ngoài semantics.

Không assert revision number phải tăng theo thứ tự thread bắt đầu; transaction concurrency và sequence allocation có thể làm thứ tự đó khác.

## 45. Test migration khi đổi audit strategy hoặc Hibernate version

Quy trình nâng cấp:
1. Tạo database fixture từ schema/Envers version cũ.
2. Seed entity revisions, deletes, collections và composite IDs.
3. Backup/dump fixture.
4. Chạy migrations mới.
5. Nâng Hibernate/Envers dependency.
6. Bootstrap với đúng Dialect.
7. Đọc các revisions cũ.
8. Tạo một revision mới.
9. Đọc revision mới và cũ.
10. Kiểm tra strategy-specific columns/indexes.
11. Kiểm tra custom revision entity.
12. Chạy concurrency/rollback tests.

Nếu đổi Default sang Validity strategy, migration phải backfill revision-end metadata. Nếu chỉ nâng patch version mà không đổi schema, vẫn nên có smoke suite cho Envers bootstrap và historical query.

## 46. Migration ordering và rolling deployment

Trong rolling deployment, old và new application versions có thể cùng chạy một thời gian. Migration phải tương thích với cả hai nếu deploy strategy yêu cầu.

Một mẫu expand-contract:
1. Thêm cột/bảng audit mới tương thích version cũ.
2. Deploy application version mới có thể ghi schema mới.
3. Backfill dữ liệu nếu cần.
4. Xác nhận mọi instances đã nâng.
5. Chuyển reads sang field mới.
6. Sau thời gian an toàn mới drop cột cũ.

Với Envers, cần xem cả audit tables. Một application cũ có thể không hiểu column/mapping mới nếu schema thay đổi theo cách phá compatibility. Không xóa audit columns trước khi các binaries cũ không còn sử dụng.

### 46.1. Revision schema là shared contract

Nếu một revision entity custom được nhiều service/module dùng chung, thay đổi column type/table name phải được triển khai đồng bộ. Một service ghi revisions bằng schema mới trong khi service khác đọc theo schema cũ có thể lỗi ngay cả khi từng module build riêng.

## 47. Migration failure và recovery

Một migration có thể thất bại giữa:
- `ALTER TABLE`.
- Backfill audit columns.
- Create index.
- Add FK.
- Update revision metadata.

Recovery phụ thuộc DBMS và migration tool:
- Migration transactional có thể rollback.
- Một số DDL đã commit riêng.
- Index concurrently có thể cần repair state.
- Flyway có thể cần `repair` sau khi kiểm tra thủ công; không chạy repair chỉ để xóa trạng thái lỗi.
- Liquibase có changelog/checksum semantics riêng.

Test failure path trên database disposable:
1. Tạo fixture.
2. Chèn dữ liệu gây lỗi migration.
3. Chạy migration.
4. Xác định schema còn lại.
5. Thực hiện recovery theo runbook.
6. Chạy lại migration hoặc forward-fix.
7. Xác nhận dữ liệu lịch sử không mất.

## 48. Kiểm tra migration data, không chỉ DDL

Một migration có thể tạo đúng columns nhưng backfill sai:
- Gán cùng revision cho nhiều thay đổi không liên quan.
- Đặt `REVEND` sai.
- Đảo tenant ID.
- Chuyển UUID sai format.
- Cắt decimal precision.
- Đổi timezone/offset.
- Bỏ các audit rows của composite IDs.
- Tạo duplicate revision metadata.
- Làm mất `REVTYPE=DEL` rows.

Hãy dùng fixture đại diện và assertions theo business semantics. Row counts là một phần, không phải toàn bộ bằng chứng.

## 49. Test custom types/converters trong Envers

Nếu entity có:
- `AttributeConverter`.
- `@Enumerated`.
- `@JdbcTypeCode`.
- Custom `UserType`/`JavaType`/`JdbcType`.
- JSON/ARRAY/spatial types.

cần test cả:
1. Live insert/update.
2. Audit row insert/update.
3. Historical read.
4. Null handling.
5. Schema column type.
6. Migration từ kiểu cũ.
7. Query/filter nếu type được dùng trong điều kiện.
8. DBMS/dialect khác nhau nếu hỗ trợ.

Một converter hoạt động trong entity hiện tại không tự chứng minh audit table có đúng type/column hoặc Envers có thể hydrate historical values.

## 50. Kiểm tra Dialect capability theo feature, không theo tên

Thay vì chỉ hỏi “đang dùng PostgreSQL Dialect phải không?”, hãy viết feature tests:
- Sequence allocation có hoạt động?
- Insert returning/generated keys có đúng?
- JSON type round-trip có đúng?
- Partial unique index được tạo?
- Lock clause thực thi?
- Deferred constraint được kiểm tra đúng thời điểm?
- Batch inserts có hiệu quả?
- Timestamp precision có giữ đúng?
- Audit query dùng SQL hợp lệ?
- DDL migration có thể chạy transactional?

Một DBMS có thể có Dialect class đúng nhưng server version/extension/driver không có capability mong đợi.

## 51. Troubleshooting: migration, Envers và Dialect

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Hibernate báo thiếu `_AUD` table | Migration không tạo audit table | Tạo migration theo mapping/Envers schema reference |
| Live insert được nhưng audit insert lỗi | Audit column/type/constraint không khớp | So sánh live và audit mappings |
| `REV` FK lỗi | Revision table/ID type/generator sai | Kiểm tra custom revision entity và DDL |
| Validity strategy lỗi thiếu `REVEND` | Đổi strategy nhưng chưa migrate | Thêm/backfill end revision metadata |
| Historical query trả sai sau migration | Backfill hoặc strategy semantics sai | So sánh fixture revisions trước/sau |
| `REVTYPE` mapping lỗi | Column type/metadata không tương thích | Dùng schema theo Envers version |
| Composite ID audit rows ghi đè | PK audit thiếu ID component | Sửa composite PK và migration dữ liệu |
| Collection history rỗng | Thiếu audit join/collection table | Kiểm tra mapping và membership test |
| Hibernate validate pass nhưng index thiếu | Validator không bao phủ mọi index | JDBC metadata/catalog assertions |
| H2 pass, PostgreSQL fail | Khác SQL/type/constraint/Dialect | Testcontainers PostgreSQL |
| UUID audit insert lỗi | Live/AUD SQL types khác | Đồng bộ UUID mapping và migrations |
| JSON live chạy nhưng Envers lỗi | Audit column/custom type không tương thích | Test historical JSON round-trip |
| Timestamp lịch sử lệch | Precision/timezone mapping khác | Test Instant semantics và column types |
| Sequence trùng sau restart | Increment/allocation mismatch | Kiểm tra generator DDL và Hibernate config |
| Constraint name bị truncate/trùng | DBMS identifier length | Đặt tên index/constraint ngắn, tường minh |
| Migration thất bại để lại DDL một phần | DBMS không rollback DDL như giả định | Recovery runbook và failure-path test |
| Upgrade mất history | Drop/recreate audit table hoặc backfill sai | Fixture upgrade test, backup và forward migration |
| Revision IDs không liên tục | Sequence gaps/rollback/concurrency | Không yêu cầu contiguous IDs |
| Custom revision listener null actor | Background thread thiếu request context | Có system actor/fallback rõ |
| Audit rows tăng quá nhanh | Scope audit quá rộng/collection churn | Review retention, indexes và partition strategy |
| Query Envers chậm | Thiếu index theo ID/REV/REVEND | EXPLAIN trên audit data đại diện |
| Native bulk update không tạo revision | Bypass entity lifecycle | Audit path riêng hoặc cấm bulk writes |
| Target association không đọc được | Target history/missing row/target mode | Test relation semantics và retention |
| Schema mới không tương thích old app | Breaking migration trong rolling deploy | Expand-contract và version compatibility |
| Migration checksum mismatch | Chỉnh file migration đã chạy | Forward-fix, không sửa lịch sử migration đã áp dụng |
| Test revision order flaky | Assert thứ tự start thread thay vì DB outcome | Assert transaction/revision semantics, không giả định scheduling |

## 52. Quy trình CI cho Envers và Dialect

Một pipeline kiểm thử có thể chia:

```text
Build dependency graph
        |
        v
Start DBMS container (pinned version)
        |
        v
Run Flyway/Liquibase from empty schema
        |
        v
Hibernate + Envers bootstrap (ddl-auto=validate)
        |
        v
Schema metadata assertions
        |
        v
Entity + revision CRUD tests
        |
        v
Association/collection history tests
        |
        v
Migration upgrade tests from previous version
        |
        v
Rollback/concurrency/deferred constraint tests
        |
        v
Optional query-plan/performance suite
```

Nếu hỗ trợ nhiều DBMS, lặp lại pipeline theo từng DBMS/version được cam kết hỗ trợ. Có thể tách functional matrix và performance suite để CI thường ngày không quá chậm.

### 52.1. Tách fresh-install và upgrade suites

- Fresh-install kiểm tra toàn bộ migration chain.
- Upgrade suite bắt đầu từ một schema cũ có dữ liệu đại diện.
- Hibernate validate kiểm tra mapping tương thích.
- Envers historical reads kiểm tra dữ liệu audit cũ.
- Write test tạo revision mới để chứng minh hệ thống tiếp tục hoạt động.

Không thay upgrade suite bằng một test tạo schema mới mỗi lần.

## 53. Checklist trước khi phát hành migration Envers

- [ ] Hibernate core và Envers version tương thích.
- [ ] Dialect và JDBC driver đúng môi trường triển khai.
- [ ] Migration tạo/cập nhật mọi `_AUD` tables cần thiết.
- [ ] Revision table và generator tương thích.
- [ ] Composite audit primary keys chứa đủ components.
- [ ] `REVTYPE`, `REV`, `REVEND` có type đúng.
- [ ] Modified flag columns được tạo nếu bật.
- [ ] Collection/audit join tables được cập nhật.
- [ ] Custom revision entity metadata được migrate.
- [ ] Decimal, UUID, JSON, timestamp và converter types được round-trip.
- [ ] Index/constraint names hợp lệ trên DBMS.
- [ ] Dữ liệu lịch sử được backfill trung thực.
- [ ] Default/Validity strategy migration được kiểm thử.
- [ ] Bulk/native write paths có audit policy riêng.
- [ ] Fresh-install và upgrade-from-previous tests pass.
- [ ] Rollback/concurrency tests pass trên DBMS thật.
- [ ] Old/new application compatibility được đánh giá nếu rolling deploy.
- [ ] Retention/PII policy cho audit data được xác định.
- [ ] Backup/recovery procedure có thể thực hiện.

## 54. Bài tập tình huống

### Bài 1 — Bật Envers

Một entity mới được thêm `@Audited`, nhưng migration chỉ tạo bảng live. Điều gì xảy ra?

**Đáp án:** Envers cần audit schema/revision metadata tương ứng; thao tác ghi có thể lỗi vì thiếu audit tables hoặc revision table.

### Bài 2 — Thêm property

Thêm `preferredLanguage` vào audited entity. Chỉ ALTER bảng live đã đủ chưa?

**Đáp án:** Không. Audit table cũng cần column tương ứng, và phải quyết định historical values cũ là unknown/null hay có nguồn backfill đáng tin cậy.

### Bài 3 — Backfill

Migration điền `"vi"` vào tất cả audit rows từ 2020 dù field chỉ xuất hiện năm 2026. Sai ở đâu?

**Đáp án:** Nó bịa historical values, làm sai ý nghĩa revision history.

### Bài 4 — Validity strategy

Chỉ đổi setting sang `ValidityAuditStrategy` nhưng audit table không có `REVEND`. Kết quả?

**Đáp án:** Envers có thể phát SQL dùng column không tồn tại; cần migration và backfill phù hợp trước khi bật.

### Bài 5 — Composite ID

Audit entity có ID `(tenantId, documentNo)` nhưng PK `_AUD` chỉ gồm `documentNo, REV`. Rủi ro?

**Đáp án:** Hai entities khác tenant có thể đụng khóa audit; PK phải chứa tất cả ID components cộng revision.

### Bài 6 — Custom revision entity

Đổi revision number từ Integer sang Long nhưng chỉ ALTER `REVINFO`. Đủ chưa?

**Đáp án:** Không. Mọi audit tables, FK, sequence/generator và mapping revision ID phải tương thích.

### Bài 7 — Modified flags

Bật `withModifiedFlag=true` nhưng migration thiếu `_MOD` columns. Cần test gì?

**Đáp án:** Tạo/update entity, kiểm tra schema và modified flags qua historical queries.

### Bài 8 — Delete snapshot

Entity bị xóa, audit DEL row không giữ fields như mong đợi. Setting nào cần xem?

**Đáp án:** `org.hibernate.envers.store_data_at_delete` cùng semantics/version Envers.

### Bài 9 — H2 compatibility

Integration test pass trên H2 PostgreSQL mode nhưng PostgreSQL production lỗi partial index. Vì sao?

**Đáp án:** Compatibility mode không biến H2 thành PostgreSQL; phải chạy container DBMS thật.

### Bài 10 — UUID

Live UUID column là native UUID, audit column là VARCHAR. Có thể gây lỗi gì?

**Đáp án:** JDBC binding/hydration type mismatch hoặc historical insert/read lỗi; đồng bộ type và test round-trip.

### Bài 11 — JSON

Custom JSON mapping persist được entity nhưng `AuditReader` lỗi khi đọc. Cần kiểm tra đâu?

**Đáp án:** Envers audit column type, custom JDBC type/converter và historical round-trip, không chỉ live serialization.

### Bài 12 — Sequence allocation

Mapping `allocationSize=50`, migration tạo sequence increment 1 trong một optimizer configuration yêu cầu increment khác. Rủi ro?

**Đáp án:** Generator mismatch có thể gây cảnh báo/lỗi hoặc allocation behavior sai; đồng bộ DDL và Hibernate optimizer.

### Bài 13 — Revision gaps

Revision numbers có gaps sau rollback. Có phải dữ liệu audit mất không?

**Đáp án:** Không nhất thiết; sequence values có thể không rollback. Kiểm tra committed revision rows và history, không yêu cầu liên tục.

### Bài 14 — Bulk update

Flyway migration update 1 triệu rows live. Envers có tự tạo 1 triệu revisions không?

**Đáp án:** Không. Migration SQL không đi qua Hibernate per-entity lifecycle; nếu cần lịch sử phải có backfill/audit design riêng.

### Bài 15 — Migration upgrade

Migration pass trên DB trống nhưng fail khi nâng schema cũ có audit data. Test nào còn thiếu?

**Đáp án:** Upgrade-from-previous fixture test với dữ liệu live/audit thực tế và historical reads.

### Bài 16 — DDL rollback

Migration tạo index concurrently rồi thất bại ở bước sau. Có thể giả định toàn migration rollback không?

**Đáp án:** Không. DDL transaction semantics phụ thuộc DBMS/statement; cần inspect schema và recovery procedure.

### Bài 17 — Revision listener

Batch job tạo revision nhưng actor metadata null. Cách xử lý?

**Đáp án:** Có system/job actor fallback rõ ràng, không phụ thuộc HTTP request context.

### Bài 18 — Audit query chậm

`AuditReader.find()` chậm khi có hàng triệu revisions. Nên làm gì?

**Đáp án:** Kiểm tra query plan và indexes theo entity ID/REV/REVEND/association keys; benchmark với dữ liệu đại diện.

### Bài 19 — Dialect class đúng

Hibernate dùng PostgreSQL Dialect nhưng DB server thiếu extension JSON/index mà migration yêu cầu. Vì sao Dialect không cứu được?

**Đáp án:** Dialect không tự cài extension hoặc bảo đảm mọi capability của server; test feature trên DBMS version thật.

### Bài 20 — Thay đổi `@NotAudited`

Bỏ audit một field hôm nay. Audit rows cũ có tự xóa field data không?

**Đáp án:** Không. Annotation ảnh hưởng mapping/audit behavior tương lai; dữ liệu lịch sử cũ cần retention/migration decision riêng.

## 55. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Envers](https://docs.hibernate.org/orm/7.2/userguide/html_single/#envers): audit model, revision entity, audit strategy, relation/collection mappings và settings.
- [Hibernate Envers project documentation](https://hibernate.org/orm/envers/): module overview và version alignment.
- [Hibernate ORM Javadocs — `Audited`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/Audited.html): audit annotations và target audit mode.
- [Hibernate ORM Javadocs — `AuditTable`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/AuditTable.html): tên audit table.
- [Hibernate ORM Javadocs — `RevisionEntity`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/RevisionEntity.html): custom revision entity.
- [Hibernate ORM Javadocs — `RevisionNumber`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/RevisionNumber.html): revision identifier.
- [Hibernate ORM Javadocs — `RevisionTimestamp`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/RevisionTimestamp.html): revision timestamp.
- [Hibernate ORM Javadocs — `ValidityAuditStrategy`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/strategy/ValidityAuditStrategy.html): validity strategy behavior.
- [Hibernate ORM Javadocs — `EnversSettings`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/envers/configuration/EnversSettings.html): Envers configuration settings.
- [Hibernate ORM User Guide — Dialects and database-specific features](https://docs.hibernate.org/orm/7.2/userguide/html_single/): identifier generation, SQL types, locking, functions and database interaction.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): entity mapping, identifiers, converters, transactions and persistence semantics.
- [Flyway documentation — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations): versioned migrations, validation and execution model.
- [Liquibase documentation — Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html): changeset identity, execution and rollback concepts.
- [Testcontainers Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL integration test container.
- [PostgreSQL Documentation — Data Types](https://www.postgresql.org/docs/current/datatype.html): native types and precision.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary, unique, foreign key and check constraints.
- [PostgreSQL Documentation — Indexes](https://www.postgresql.org/docs/current/indexes.html): index types, expressions and partial indexes.
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): transaction snapshots and concurrency.
- [PostgreSQL Documentation — DDL](https://www.postgresql.org/docs/current/ddl.html): schema changes and database object definitions.

**Ghi chú phiên bản:** Envers schema, audit strategy, revision metadata, Dialect classes, type mappings và SQL generation có thể thay đổi giữa Hibernate major/minor versions. Các DDL snippets chỉ minh họa; dùng đúng Hibernate/Envers version, JDBC driver, database server version, naming strategy và migration tool của dự án. Những tính năng như JSONB, partial indexes, deferrable constraints và DDL transaction behavior trong ví dụ là DBMS-specific, không được suy ra từ tên Dialect đơn thuần.

## Kết luận

Kiểm thử migration và Envers phải chứng minh **cả schema hiện tại lẫn khả năng đọc lịch sử đã tồn tại**. Khi mapping thay đổi, hãy cập nhật đúng live tables, audit tables, revision metadata, collection/join tables, keys và indexes; khi đổi audit strategy, cần migration dữ liệu lịch sử chứ không chỉ thay property. Đặc biệt, không backfill các giá trị lịch sử mà hệ thống chưa từng biết.

Dialect là lớp chuyển đổi SQL và type behavior, nhưng không thay thế kiểm tra DBMS/version thật. Hãy dùng migrations production trong Testcontainers, bootstrap Hibernate/Envers với `ddl-auto=validate`, kiểm tra metadata/constraints, ghi và đọc revisions qua `AuditReader`, rồi chạy upgrade tests từ schema cũ có dữ liệu. Nếu ứng dụng hỗ trợ nhiều database, mỗi database cần capability tests riêng cho sequence, types, indexes, constraints, locking và DDL.

Một migration chỉ đáng tin khi nó vừa nâng schema thành công, vừa giữ nguyên ý nghĩa lịch sử cũ, vừa cho phép Hibernate/Envers tiếp tục ghi và truy vấn đúng trên database mà ứng dụng thực sự triển khai.
