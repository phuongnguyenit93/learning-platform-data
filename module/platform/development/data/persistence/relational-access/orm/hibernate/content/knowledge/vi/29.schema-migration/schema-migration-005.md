# Tích hợp Flyway hoặc Liquibase theo một quy trình có kiểm soát

Khi phát triển ứng dụng Java dùng Hibernate/JPA, entity mapping và database schema phải tương thích. Nhưng một database đã chứa dữ liệu thật không thể được xử lý như database tạm trong bài demo: chúng ta không được tùy tiện xóa bảng, đổi kiểu cột, thêm ràng buộc hoặc áp dụng thay đổi schema theo thứ tự ngẫu nhiên ở từng môi trường.

**Flyway** và **Liquibase** là hai công cụ database migration giúp quản lý những thay đổi này theo lịch sử có thể theo dõi. Chúng không thay thế Hibernate để đọc/ghi entity; chúng chịu trách nhiệm đưa schema và một số dữ liệu tham chiếu từ phiên bản cũ sang phiên bản mới bằng các bước có kiểm soát.

Tư duy quan trọng nhất:

> **Migration là một phần của quy trình phát hành phần mềm, không phải tác dụng phụ tùy ý của việc khởi động ứng dụng.** Mỗi thay đổi cần có nguồn trong version control, được review, thực thi theo thứ tự xác định, kiểm tra trước khi triển khai, có phương án xử lý lỗi và tương thích với các phiên bản ứng dụng đang chạy.

Ví dụ, khi thêm thuộc tính vào entity:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "description")
    private String description;
}
~~~

việc sửa code Java **không tự bảo đảm** cột `description` đã tồn tại ở database production. Cột đó phải được tạo qua migration trước khi phần mềm phụ thuộc vào nó.

Bài thuộc chương **Lược đồ và chuyển đổi** trong module *Data Persistence Relational Access ORM Hibernate*. Ví dụ dùng PostgreSQL, SQL, YAML, Spring Boot và Jakarta Persistence. Một số cú pháp và dependency khác nhau theo phiên bản Flyway, Liquibase, Spring Boot và hệ quản trị; hãy đối chiếu tài liệu đúng phiên bản trước khi áp dụng.

## 1. Vì sao Hibernate tự quản schema không đủ cho production?

Hibernate có khả năng tạo hoặc so sánh lược đồ từ entity metadata. Trong Spring Boot, một cấu hình quen thuộc là:

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

Nó hữu ích trong một số tình huống học tập hoặc prototype, nhưng **không phải hệ thống migration production đáng tin cậy**.

Các giới hạn:

- Hibernate nhìn mapping hiện tại, không biết đầy đủ ý định và lịch sử thay đổi schema.
- Đổi tên thuộc tính có thể bị hiểu thành thêm cột mới chứ không phải rename và chuyển dữ liệu.
- Xóa bảng/cột có thể làm mất dữ liệu hoặc không được thực hiện như mong muốn.
- Thêm unique constraint trên dữ liệu duplicate cần dọn dữ liệu trước.
- Đổi kiểu dữ liệu có thể cần backfill, kiểm tra overflow và xử lý NULL.
- Index, trigger, view, procedure, quyền truy cập và DB-specific objects không được JPA mapping mô tả đầy đủ.
- Không có quy trình approval, review và release cho từng thay đổi.
- Không có lịch sử version rõ để biết database môi trường nào đã chạy bước nào.

| Giá trị `ddl-auto` | Tác dụng tổng quát | Phạm vi nên dùng |
| --- | --- | --- |
| `none` | Không tự sửa schema | Production khi migration tool sở hữu schema |
| `validate` | Kiểm tra mapping tương thích schema ở mức Hibernate hỗ trợ | Kiểm tra bổ sung sau migration |
| `update` | Cố thay đổi schema theo mapping | Dev/prototype có kiểm soát |
| `create` | Tạo lại schema, có thể làm mất dữ liệu | Test/demo với DB tạm |
| `create-drop` | Tạo và drop theo lifecycle của ứng dụng | Test/demo với DB tạm |

**`validate` không kiểm chứng toàn bộ schema.** Nó không bảo đảm index, trigger, quyền, check constraint, data migration và business invariant đều đúng.

Mô hình trách nhiệm:

~~~text
Java entity mapping
       |
       v
Hibernate/JPA
  - Map object ↔ row
  - JPQL/HQL/Criteria
  - Dirty checking
  - Transaction participation
  - Schema validation nếu cấu hình
       |
       v
Relational Database
       ^
       |
Flyway hoặc Liquibase
  - Schema evolution
  - DDL/DML migrations theo lịch sử
  - Applied history/checksum
  - Deployment control
~~~

Không để Hibernate `update` và Flyway/Liquibase cùng sửa schema production. Chỉ định **một chủ thể quản lý thay đổi lược đồ**.

## 2. Migration là gì và nằm ở đâu?

Một migration là một bước thay đổi có chủ đích:

~~~sql
ALTER TABLE products
ADD COLUMN description VARCHAR(1000);
~~~

Nó có thể gồm:

- DDL: tạo/đổi bảng, cột, index, constraint, view.
- DML: sửa dữ liệu cũ, nạp reference data.
- Dọn dữ liệu trước khi thêm ràng buộc.
- Chuyển dữ liệu từ schema cũ sang schema mới.
- Định nghĩa lại stored procedure/function.

Migration nên được lưu **cùng source code trong version control**, review và triển khai theo pipeline.

~~~text
repository/
  src/main/java/.../Product.java
  src/main/resources/
    db/migration/                 # Nếu chọn Flyway
      V1__create_products.sql
      V2__add_description.sql
      V3__backfill_description.sql

    db/changelog/                 # Nếu chọn Liquibase thay thế
      db.changelog-master.yaml
      changes/
        001-create-products.yaml
        002-add-description.yaml
~~~

Hai thư mục trên là **hai hướng thay thế**, không phải chỉ thị chạy đồng thời hai công cụ trên cùng schema.

### Quy tắc ownership

Một schema nên có **một migration history và cơ chế điều phối chính**. Hai dịch vụ có thể sở hữu các schema khác nhau, nhưng nếu cả Flyway và Liquibase cùng tự quản những bảng dùng chung mà không có ranh giới, việc đổi schema sẽ va chạm và khó kiểm soát.

## 3. Chọn Flyway hay Liquibase?

| Tiêu chí | Flyway | Liquibase |
| --- | --- | --- |
| Đơn vị thay đổi | Versioned/repeatable migration | Changeset trong changelog |
| Định dạng thường dùng | SQL script; có Java migration | XML, YAML, JSON, formatted SQL |
| Bảng history mặc định | `flyway_schema_history` | `DATABASECHANGELOG` |
| Khóa phối hợp thực thi | Lock/cơ chế coordination của Flyway theo DB | `DATABASECHANGELOGLOCK` |
| Phát hiện file đã sửa | Checksum/history validation | Checksum changeset |
| Chọn môi trường | Config/locations/placeholders | Contexts/labels/parameters |
| Tính portable | SQL phụ thuộc dialect | DSL change type có thể dịch; SQL vẫn phụ thuộc DB |
| Rollback | Thường roll forward; undo tùy phiên bản/edition | Có rollback definitions/auto-rollback cho một số change types |
| Phong cách đội nhóm | SQL-centric | Changelog/DSL-centric |

Không có công cụ nào tự tạo zero downtime, khôi phục data đã mất hoặc bảo đảm mọi script transactional. Việc chọn công cụ cần xét phiên bản, license, database, năng lực đội và quy trình vận hành.

**Flyway phù hợp** nếu đội quen SQL, muốn lịch sử theo version dễ xem. **Liquibase phù hợp** nếu đội muốn changeset/precondition/context/rollback metadata và các change types có tính khai báo.

## 4. Quy trình migration có kiểm soát

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ mới"] --> B["Thiết kế schema + compatibility"]
    B --> C["Tạo migration trong source control"]
    C --> D["Code review SQL/changelog"]
    D --> E["Test DB mới trống"]
    E --> F["Test nâng cấp DB cũ có dữ liệu"]
    F --> G{"Lỗi hoặc mất dữ liệu?"}
    G -- "Có" --> B
    G -- "Không" --> H["Backup / recovery / rollout plan"]
    H --> I["Apply staging và quan sát"]
    I --> J["Apply production bằng một executor"]
    J --> K["Hibernate validate, deploy app"]
    K --> L["Smoke test, metrics, change record"]
~~~

Các nguyên tắc:

1. Có **source migration** và người review.
2. Có **thứ tự áp dụng** rõ.
3. Có **history/checksum** để phát hiện chỉnh sửa trái phép hoặc nhầm lẫn.
4. Có test trên **database cũ có dữ liệu**, không chỉ DB mới.
5. Có **migration owner/credential**.
6. Có kế hoạch backup, roll-forward, rollback hoặc restore.
7. Có compatibility giữa ứng dụng cũ/mới trong rolling deploy.
8. Có giám sát lock, duration, row counts và lỗi.
9. Không thay đổi schema production thủ công ngoài quy trình.

## 5. Flyway: versioned migrations

Các script Flyway versioned thường được đặt tên:

~~~text
V1__create_products.sql
V2__add_description.sql
V3__backfill_product_description.sql
~~~

Ý nghĩa:

- `V`: prefix mặc định cho versioned migration.
- `1`, `2`, `3`: version duy nhất và tăng dần.
- `__`: separator giữa version và description.
- Phần cuối: mô tả và `.sql`.

`V1__create_products.sql`:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_created_at
ON products(created_at);
~~~

`V2__add_description.sql`:

~~~sql
ALTER TABLE products
ADD COLUMN description VARCHAR(1000);
~~~

`V3__backfill_product_description.sql`:

~~~sql
UPDATE products
SET description = name
WHERE description IS NULL;
~~~

Khi Flyway chạy trên DB mới, nó áp dụng các versioned migrations theo thứ tự version. Trên DB đã migrate, các bước đã applied không tự chạy lại như mới.

### Không sửa migration đã applied

Nếu V2 đã chạy trên staging hoặc production, đừng đổi nội dung V2 từ:

~~~sql
ALTER TABLE products ADD COLUMN description VARCHAR(1000);
~~~

sang:

~~~sql
ALTER TABLE products ADD COLUMN description TEXT;
~~~

rồi tưởng Flyway sẽ tự chuyển kiểu cột. Script đã applied có checksum/history; sửa file có thể làm validation thất bại.

Thay bằng migration mới:

~~~text
V4__alter_description_type.sql
~~~

~~~sql
-- PostgreSQL-specific example
ALTER TABLE products
ALTER COLUMN description TYPE TEXT;
~~~

**Versioned migrations đã áp dụng ở môi trường chia sẻ là lịch sử bất biến.** Chỉ sửa file cũ ở giai đoạn chưa phát hành và khi toàn đội có quy trình rebuild test/dev thống nhất.

## 6. Flyway schema history và validation

Flyway mặc định quản lý bảng:

~~~text
flyway_schema_history
~~~

Bảng này lưu metadata migration, version, description, checksum, status và thời điểm theo schema/version của Flyway.

Ví dụ logic:

| version | description | checksum | success |
| --- | --- | --- | --- |
| 1 | create products | ... | true |
| 2 | add description | ... | true |
| 3 | backfill description | ... | true |

Một đợt migrate:

1. Tìm migrations ở locations đã cấu hình.
2. Đọc schema history.
3. Xác định pending migrations.
4. Kiểm tra consistency/validation theo config.
5. Chạy pending migrations đúng thứ tự.
6. Ghi metadata applied/history.

Các lệnh thường gặp:

~~~text
flyway info
flyway validate
flyway migrate
flyway repair
~~~

- `info`: xem trạng thái.
- `validate`: kiểm tra applied history so với file nguồn.
- `migrate`: chạy những bước pending.
- `repair`: xử lý metadata/history sau khi xác minh vấn đề.

Đây là ví dụ CLI; **không thực thi các lệnh trên một database thật nếu chưa cấu hình đúng môi trường và quyền**.

### Vì sao không repair checksum một cách mù quáng?

Nếu V2 cũ tạo VARCHAR còn V2 mới ghi TEXT, chạy `repair` để history chấp nhận checksum mới **không chuyển database schema sang TEXT**.

`repair` không tự sửa DDL đã apply hoặc khôi phục dữ liệu. Quy trình đúng là đối chiếu file cũ–mới, xác định schema state và tạo migration mới. Chỉ dùng repair với approval và lý do rõ.

## 7. Flyway repeatable migrations

Flyway hỗ trợ migration không có version, thường đặt tên:

~~~text
R__refresh_product_catalog_view.sql
~~~

Repeatable migration chạy lại khi checksum nội dung đổi, thông thường sau pending versioned migrations trong một đợt migrate.

Ví dụ PostgreSQL:

~~~sql
CREATE OR REPLACE VIEW product_catalog_view AS
SELECT
    id,
    sku,
    name,
    description
FROM products;
~~~

Khi sửa view definition, script có checksum mới và được thực thi lại.

Các tình huống thường dùng:

- View definition.
- Function/procedure definition.
- Một số reference data có thể tái tạo idempotently.
- Database objects mà trạng thái mong muốn được mô tả bởi một script.

**Không đặt DML không idempotent vào repeatable**:

~~~sql
INSERT INTO catalog_categories(code, name)
VALUES ('BOOK', 'Book');
~~~

Nếu chạy lại không có conflict handling, có thể tạo duplicate hoặc lỗi unique constraint. Repeatable cần thiết kế để chạy lại an toàn.

| Loại | Khi nào chạy | Phù hợp |
| --- | --- | --- |
| Versioned | Một lần theo version đã applied | Thay đổi DDL/DML incremental |
| Repeatable | Khi checksum thay đổi | View/function/reference definition có thể tạo lại |

Không dùng repeatable như lối tắt để sửa lịch sử versioned migrations.

## 8. Java migration trong Flyway

Flyway có khả năng viết Java-based migration trong phiên bản/cấu hình hỗ trợ. Chọn khi:

- Chuyển dữ liệu cần logic Java đặc thù.
- Cần JDBC/driver-specific operations.
- Một quy trình khó biểu diễn bằng SQL đơn giản.

Trade-off:

- Phụ thuộc runtime/library version.
- Migration Java cũ có thể không compile hoặc chạy khi domain model đổi.
- Không nên dùng entity mới nhất để deserialize schema của version cũ một cách tùy tiện.
- Backfill hàng triệu dòng trong một transaction có thể giữ lock rất lâu.
- Cần idempotency, checkpoint, retry và kiểm soát memory.

Với DDL đơn giản, versioned SQL thường dễ đọc/review hơn.

## 9. Tích hợp Flyway với Spring Boot

Spring Boot hỗ trợ Flyway startup migrations khi dependency/config phù hợp.

Ví dụ Gradle Kotlin DSL cho **Spring Boot phiên bản có starter Flyway** và PostgreSQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-flyway")

    runtimeOnly("org.postgresql:postgresql")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
}
~~~

**Tùy Spring Boot major version:** Một số dự án dùng `org.flywaydb:flyway-core` trực tiếp, trong khi các bản mới có starter. Database-specific Flyway modules cũng phụ thuộc version. Hãy dùng BOM/dependency management của Spring Boot tương thích, không ép version tùy tiện.

Cấu hình minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: FROM_SECRET_MANAGER

  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true

  jpa:
    hibernate:
      ddl-auto: validate
~~~

`FROM_SECRET_MANAGER` là placeholder minh họa, không phải mật khẩu. Production cần inject qua environment/secret store.

Thư mục:

~~~text
src/main/resources/db/migration/
    V1__create_products.sql
    V2__add_description.sql
    V3__backfill_description.sql
~~~

Khi phù hợp auto-configuration, Flyway migrations chạy trước khi Hibernate EntityManagerFactory dùng schema. `ddl-auto=validate` sau đó kiểm tra mức tương thích mapping.

### Startup migration hay deployment job?

Với ứng dụng nhỏ, migration lúc startup tiện. Với nhiều replicas hoặc DDL lớn, nên xem xét **migration job riêng**:

~~~text
CI/CD approval
    ↓
migration job chạy một lần
    ↓
Flyway history updated
    ↓
rollout new application pods
~~~

Nếu pipeline đã chạy migration độc lập, có thể tắt startup migration của runtime:

~~~properties
spring.flyway.enabled=false
~~~

Không tắt mà quên tạo job. Nếu startup migration vẫn bật trên nhiều pod, công cụ có cơ chế coordination, nhưng pod có thể phải chờ lock, timeout hoặc fail startup.

## 10. Liquibase: changelog và changeset

Liquibase dùng **changelog** chứa một chuỗi **changeset**.

Ví dụ:

~~~text
src/main/resources/db/changelog/
    db.changelog-master.yaml
    changes/
        001-create-products.yaml
        002-add-description.yaml
        003-backfill-description.yaml
~~~

Một changeset thường có:

- `id`: định danh changeset.
- `author`: tác giả hoặc nhóm.
- File path: một phần của identity đầy đủ.
- `changes`: DDL/DML operations.
- `preConditions`: điều kiện phải thỏa trước khi chạy.
- Context/label: chọn changeset theo môi trường/mục đích.
- `rollback`: khai báo hướng hoàn tác nếu thích hợp.

Định danh thay đổi thường là **file path + author + id**. ID không được sắp tăng dần theo version như Flyway; thứ tự trong changelog là quan trọng.

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-products.yaml
  - include:
      file: db/changelog/changes/002-add-description.yaml
~~~

`001-create-products.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-products"
      author: "catalog-team"
      changes:
        - createTable:
            tableName: products
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: sku
                  type: VARCHAR(60)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
~~~

`002-add-description.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "002-add-description"
      author: "catalog-team"
      changes:
        - addColumn:
            tableName: products
            columns:
              - column:
                  name: description
                  type: VARCHAR(1000)
~~~

Các change types trên được Liquibase dịch thành SQL theo database target. Cần kiểm tra generated SQL, nhất là `autoIncrement`, identity/sequence, index và constraint trên DB thật.

## 11. Liquibase history và locking

Liquibase mặc định có:

~~~text
DATABASECHANGELOG
DATABASECHANGELOGLOCK
~~~

- `DATABASECHANGELOG` lưu changesets đã chạy và metadata/checksum.
- `DATABASECHANGELOGLOCK` điều phối để tránh chạy migration đồng thời không kiểm soát trong cùng phạm vi.

Ví dụ hai pod:

~~~text
Pod A ──► Liquibase update
Pod B ──► Liquibase update trên cùng database
~~~

Lock giúp điều phối, nhưng startup của một pod có thể bị chờ hoặc timeout. Với sản phẩm lớn, migration job độc lập thường dễ vận hành hơn.

**Không xóa `DATABASECHANGELOGLOCK` hoặc “release locks” khi chưa xác minh không còn migration đang thực thi.** Một lock hợp lệ có thể thuộc job DDL dài; phá lock tùy tiện có thể gây hai executor thao tác đồng thời.

## 12. Preconditions trong Liquibase

Precondition kiểm tra giả định database trước khi changeset chạy.

Ví dụ: bảng phải tồn tại và cột chưa tồn tại.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "004-add-external-code"
      author: "catalog-team"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: products
        - not:
            - columnExists:
                tableName: products
                columnName: external_code
      changes:
        - addColumn:
            tableName: products
            columns:
              - column:
                  name: external_code
                  type: VARCHAR(100)
~~~

Ý nghĩa: khi giả định không đúng, **dừng** thay vì thực thi mù quáng.

Trong Liquibase, `onFail` có thể có các cách xử lý như `HALT`, `WARN`, `CONTINUE` hoặc `MARK_RAN` theo phạm vi hỗ trợ. Không dùng `MARK_RAN` để che việc schema thật chưa đúng: history có thể ghi nhận changeset dù DDL không được thực hiện.

Preconditions có thể hỗ trợ:

- Xác nhận bảng/cột/constraint đã có hoặc chưa.
- Kiểm tra DBMS/version.
- Kiểm tra một tập dữ liệu trước khi chuyển đổi.
- Chặn thay đổi phá vỡ giả định domain.

Chúng **không thay thế test, backup hoặc review**, vì không thể dự đoán mọi lỗi runtime, transaction và concurrency.

## 13. Contexts và labels

Một hệ thống có thể cần seed test data nhưng không muốn đưa dữ liệu giả vào production.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "900-seed-demo-products"
      author: "qa-team"
      contextFilter: "@test"
      changes:
        - insert:
            tableName: products
            columns:
              - column:
                  name: sku
                  value: "DEMO-001"
              - column:
                  name: name
                  value: "Demo Product"
~~~

Trong môi trường test:

~~~properties
spring.liquibase.contexts=test
~~~

`contextFilter`/`context` và cú pháp `@test` phụ thuộc phiên bản Liquibase; ý tưởng là yêu cầu context được kích hoạt một cách tường minh. Nên dùng đúng convention của dự án.

**Không đặt một migration schema bắt buộc trong context chỉ dành cho test** nếu production cần schema ấy để chạy ứng dụng.

Labels có thể dùng để nhóm theo feature/release, còn contexts thường dùng cho môi trường hoặc kịch bản. Đó là quy ước sử dụng; quan trọng hơn là filter configuration được review và không bỏ sót thay đổi production.

## 14. Liquibase checksum, runOnChange và runAlways

Liquibase ghi checksum của changeset đã applied. Nếu file cũ bị sửa, tool có thể báo checksum validation error.

Các tùy chọn liên quan:

- `runOnChange`: cho chạy lại nếu định nghĩa changeset thay đổi; thích hợp cho một số view/procedure definitions.
- `runAlways`: chạy ở mỗi update theo semantics cấu hình.
- `validCheckSum`: chấp nhận checksum được chỉ định khi đã xác minh lý do.
- `clearCheckSums`: điều chỉnh metadata/checksum, không tự nâng cấp schema.

Không bật `runAlways` trên một changeset `CREATE TABLE` hoặc một INSERT không idempotent rồi kỳ vọng chạy lại luôn an toàn.

Quy tắc chung: **changeset đã chạy là lịch sử**. Nếu cần thay đổi bảng tiếp, tạo changeset mới. Chỉ dùng runOnChange cho đối tượng có thể cập nhật lại một cách xác định và an toàn.

## 15. Liquibase rollback không phải bảo đảm không mất dữ liệu

Liquibase cho phép khai báo rollback:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "005-add-product-label"
      author: "catalog-team"
      changes:
        - addColumn:
            tableName: products
            columns:
              - column:
                  name: label
                  type: VARCHAR(80)
      rollback:
        - dropColumn:
            tableName: products
            columnName: label
~~~

Rollback được định nghĩa có thể xóa cột `label`. Nhưng nếu người dùng đã nhập dữ liệu vào cột đó, **xóa cột sẽ mất dữ liệu mới**.

Cần phân biệt:

1. **Rollback application code:** quay về phiên bản ứng dụng cũ.
2. **Rollback schema:** đảo một thay đổi DDL nếu có thể và phù hợp.
3. **Data restore:** phục hồi dữ liệu đã mất từ backup/nguồn đối chiếu.

Một số Liquibase change types có auto-generated rollback; những loại khác cần khai báo SQL/changeset rollback riêng hoặc không thể đảo ngược đầy đủ. Vì vậy không giả định mọi migration đều có rollback an toàn chỉ vì dùng Liquibase.

Trong production, khi có lỗi nhiều khi **roll forward bằng migration mới** hoặc tận dụng expand-contract an toàn hơn việc đảo DDL.

## 16. Tích hợp Liquibase vào Spring Boot

Ví dụ Gradle Kotlin DSL cho Spring Boot phiên bản có starter Liquibase:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-liquibase")

    runtimeOnly("org.postgresql:postgresql")
}
~~~

Với Spring Boot versions khác, có thể dùng `org.liquibase:liquibase-core` trực tiếp. Phải kiểm tra BOM và documentation của major version.

Cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: FROM_SECRET_MANAGER

  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml

  jpa:
    hibernate:
      ddl-auto: validate
~~~

Khi dùng migration job riêng và có cơ chế điều phối khác:

~~~properties
spring.liquibase.enabled=false
~~~

Chỉ tắt startup migration khi job khác chắc chắn chạy. Không để cả Flyway và Liquibase tự tạo/sửa cùng schema bằng hai history độc lập nếu chưa có kiến trúc ownership rõ.

## 17. Thứ tự khởi động Spring Boot, migration và Hibernate

Một chuỗi mong muốn:

~~~text
Load configuration / DataSource
               |
               v
Flyway hoặc Liquibase migrate
               |
               v
Hibernate EntityManagerFactory startup
               |
               v
Hibernate schema validate
               |
               v
Repositories và services hoạt động
~~~

Spring Boot có cơ chế dependency ordering cho database initialization, nhưng khi tự cấu hình nhiều DataSource, nhiều EntityManagerFactory hoặc custom startup bean, cần kiểm tra thứ tự thực tế.

Không để các cơ chế sau cùng tạo schema production:

- Hibernate `ddl-auto=create/update`.
- Flyway/Liquibase migrations.
- `schema.sql` hoặc `data.sql` chạy ngoài ý muốn.
- `import.sql` gắn với Hibernate schema creation.

**Một chủ thể sở hữu thay đổi schema.** Hibernate validate chỉ kiểm chứng một phần mapping sau khi migrations đã áp dụng.

## 18. Đưa database đang tồn tại vào migration management

Một database production đã có bảng từ lâu nhưng chưa dùng migration tool. Không thể chạy lại `CREATE TABLE products` như DB trống.

Cần onboarding:

1. Khảo sát schema hiện có: tables, columns, indexes, views, triggers, constraints, permissions.
2. Backup và xác nhận restore procedure.
3. Chụp schema state, đối chiếu giữa staging và production.
4. Chọn baseline version/changesets tương ứng thực tế.
5. Chỉ đánh dấu đã applied những bước mà database **đã thực sự tương đương**.
6. Test migration tiếp theo trên bản sao DB đã baseline.
7. Chạy Hibernate validate và integration tests.
8. Apply production theo approval.

### Flyway baseline

Flyway có `baseline` và `baselineOnMigrate`.

- Baseline operation: ghi nhận DB hiện tại bắt đầu được quản lý từ một version.
- Baseline migration: một loại script dùng cho workflow baseline ở version/tool hỗ trợ.
- `baselineOnMigrate`: tự baseline trong những tình huống cấu hình; nếu bật sai có thể che việc trỏ nhầm DB/schema.

**Không đặt `baselineOnMigrate=true` tùy tiện trên production.** Cần xác minh environment, schema, history và version chính xác.

### Liquibase changelogSync

Liquibase có workflow `changelogSync` để ghi nhận changesets là đã thực thi mà không chạy SQL của chúng trong trường hợp onboarding tương ứng. Điều này **chỉ sửa metadata**, không tạo bảng/cột còn thiếu.

Nếu DB không thực sự có schema tương đương, đánh dấu tất cả applied sẽ khiến history sai với thực tế.

## 19. Transaction và DDL khác nhau theo database

Một migration:

~~~sql
ALTER TABLE products ADD COLUMN status VARCHAR(20);

UPDATE products
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Nếu câu thứ hai thất bại, database có rollback cả DDL lẫn DML không?

**Phụ thuộc database, operation và cấu hình migration tool.**

- PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác nhưng có ngoại lệ.
- MySQL có DDL với implicit commit hoặc cơ chế atomic DDL riêng; không có nghĩa mọi transaction chứa nhiều DDL/DML đều rollback hoàn toàn.
- Oracle và các hệ DB khác có quy tắc DDL riêng.
- Một số online index operations không được chạy trong transaction block thông thường.

Flyway/Liquibase điều phối transaction theo khả năng DB nhưng không thể biến mọi DDL thành transactional.

Với Liquibase, `runInTransaction=false` có thể cần cho một số thao tác riêng nhưng có nguy cơ partial failure. Với Flyway, migration cũng có thể cần cấu hình execution ngoài transaction tùy dialect. Không bật chung cho mọi script chỉ để “chạy được”.

**Test migration failure trên cùng DB engine/version với production**, không chỉ trên H2.

## 20. Tạo index trên bảng lớn là thay đổi vận hành

Câu SQL:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders(created_at);
~~~

có thể giữ lock hoặc tạo I/O lớn trên bảng nhiều dữ liệu.

PostgreSQL có:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON orders(created_at);
~~~

nhưng lệnh đó không chạy trong transaction block thông thường. Vì vậy migration tool cần cấu hình phù hợp khi dùng cú pháp này.

Cần đánh giá:

- DB có hỗ trợ thao tác online/concurrently không?
- Index build có ảnh hưởng writers không?
- Có cần unique index nhưng dữ liệu đang duplicate không?
- Có thể build trong thời gian maintenance không?
- Nếu index build thất bại, DB có để lại object chưa valid không?
- Có đủ disk/WAL/replication capacity không?

**Một migration tạo index cũng là một thay đổi vận hành**, không chỉ thêm một dòng vào SQL file.

## 21. Backfill dữ liệu lớn không nên chặn deployment quá lâu

Thêm cột:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_customer_name VARCHAR(200);
~~~

rồi:

~~~sql
UPDATE orders
SET normalized_customer_name = UPPER(customer_name);
~~~

trên hàng chục triệu rows có thể tạo long transaction, lock contention, nhiều WAL/redo log và ảnh hưởng replication.

Một kế hoạch an toàn:

1. Thêm cột nullable.
2. Deploy code ghi cột mới cho dữ liệu phát sinh.
3. Backfill dữ liệu cũ theo batch, có checkpoint.
4. Theo dõi DB latency, lock và replication lag.
5. Kiểm chứng không còn rows sai/NULL.
6. Chuyển read path/siết constraint vào release phù hợp.
7. Chỉ xóa cấu trúc cũ sau khi toàn bộ writer/reader đã chuyển.

Với dataset nhỏ, một DML migration versioned có thể đủ. Với dataset lớn, backfill job riêng thường dễ dừng/resume và tránh migration startup kéo dài.

Backfill job nên có idempotency, batch size, bounded transaction, checkpoint, retry và kiểm soát race với concurrent writers.

## 22. Expand–migrate–contract cho rolling deployment

Đổi cột `name` thành `display_name`:

~~~mermaid
flowchart LR
    A["App A và schema cũ"] --> B["Expand: thêm display_name nullable"]
    B --> C["App B: đọc/ghi tương thích"]
    C --> D["Backfill dữ liệu"]
    D --> E["Kiểm tra dữ liệu đầy đủ"]
    E --> F["App C: đọc cột mới"]
    F --> G["Không còn app cũ"]
    G --> H["Contract: bỏ cột cũ"]
~~~

**Expand:**

~~~sql
ALTER TABLE products
ADD COLUMN display_name VARCHAR(200);
~~~

Ứng dụng cũ vẫn chạy vì cột `name` chưa mất.

**Migrate:**

- Code mới có thể dual-write hai cột trong một transaction.
- Readers có fallback rõ cho bản ghi chưa backfill.
- Backfill dữ liệu cũ theo batch khi cần.

~~~sql
UPDATE products
SET display_name = name
WHERE display_name IS NULL;
~~~

**Contract:**

Chỉ khi chắc chắn không còn app cũ và dữ liệu đã được đồng bộ:

~~~sql
ALTER TABLE products
DROP COLUMN name;
~~~

Đây là bước phá vỡ compatibility và có thể làm mất data. Tách khỏi expand migration, review và backup kỹ.

Không siết `NOT NULL` quá sớm nếu writer cũ vẫn insert bản ghi không điền cột mới.

## 23. Một migration version không nhất thiết tương ứng một app release

Ví dụ:

~~~text
App 1.10 cần schema >= V12
App 1.11 cần schema >= V13
App 1.12 tương thích V13 và V14
~~~

Không phải mỗi release đều cần migration. Nhưng cần matrix compatibility rõ:

| App release | Schema V12 | Schema V13 | Schema V14 |
| --- | --- | --- | --- |
| 1.10 | Hỗ trợ | Có thể nếu expand-compatible | Có thể không |
| 1.11 | Không | Hỗ trợ | Có thể nếu expand-compatible |
| 1.12 | Không | Hỗ trợ | Hỗ trợ |

Đây là bảng minh họa. Trạng thái phải được xác định từ code và tests cụ thể.

Đặc biệt khi rolling deploy, ở một thời điểm có thể tồn tại nhiều phiên bản ứng dụng dùng chung database. Không viết migration phá vỡ old version nếu chưa có migration/release plan cho nó.

## 24. CI/CD pipeline cho migration

Pseudo-pipeline:

~~~yaml
stages:
  - build
  - migration-check
  - integration-test
  - deploy-schema
  - deploy-application
  - smoke-test
~~~

Đây không phải file CI vendor chạy nguyên trạng, chỉ minh họa thứ tự.

**Bước 1 — Build/migration check**

- Kiểm tra format/naming/version/changeset IDs.
- Tìm duplicate version hoặc changeset identity.
- Phát hiện migration đã applied bị sửa.
- Review SQL nguy hiểm: DROP, TRUNCATE, ALTER TYPE, NOT NULL, index lớn.
- Kiểm tra dependency Flyway/Liquibase và DB dialect.

**Bước 2 — Integration test**

~~~text
Start fresh PostgreSQL container
    ↓
Apply migrations
    ↓
Start Hibernate ddl-auto=validate
    ↓
Run repository/service tests
    ↓
Assert constraints and data
~~~

Đồng thời test nâng cấp từ snapshot/schema cũ:

~~~text
Restore sanitized old DB state
    ↓
Apply pending migrations
    ↓
Verify data preserved and transformed
    ↓
Run compatibility tests with old/new app versions
~~~

Test trên DB mới có thể bỏ sót duplicate, NULL, FK, index và data volume của production.

**Bước 3 — Production deploy**

- Chọn đúng DB/schema.
- Có approval nếu rủi ro.
- Backup/restore plan đã xác minh.
- Chỉ một migration executor.
- Log migration ID/version, duration, status.
- Monitor DB latency, locks và replication lag.
- Deploy app sau khi schema đã tương thích.

## 25. Tách migration user khỏi runtime user

Runtime app thường cần DML permissions thích hợp; migration job cần DDL permissions.

~~~text
migration_user:
  CREATE / ALTER / DROP trong schema cho phép
  thực thi qua CI/CD hoặc job được kiểm soát

app_user:
  SELECT / INSERT / UPDATE / DELETE cần thiết
  không có quyền DROP tùy ý
~~~

Tùy DB, quyền sở hữu schema, sequence, view và routine cần cấu hình thêm.

Không commit:

~~~yaml
spring:
  datasource:
    password: production-password-plaintext
~~~

Dùng secret manager/environment injection. Không log mật khẩu, token hoặc JDBC URL chứa credential.

**Least privilege và separation of duties** giúp giảm rủi ro một lỗi ứng dụng runtime vô tình thay đổi schema production.

## 26. Nhiều database và multi-tenant schemas

Một ứng dụng có thể dùng:

- Database nghiệp vụ chính.
- Database báo cáo.
- Schema riêng theo bounded context.
- Nhiều schema theo tenant.

Cần trả lời:

1. Flyway/Liquibase dùng DataSource nào?
2. History table nằm ở schema nào?
3. Migration nào thuộc schema nào?
4. Các schema có dependency gì?
5. Một executor có thể migrate nhiều tenant không?
6. Hibernate EntityManagerFactory nào đòi schema version nào?

Spring Boot hỗ trợ dùng DataSource riêng cho migration như `@FlywayDataSource` hoặc `@LiquibaseDataSource` trong versions hỗ trợ, hoặc cấu hình URL/username riêng.

Ví dụ multi-tenant:

~~~text
tenant_a -> schema V12
tenant_b -> schema V12
tenant_c -> schema V11
~~~

Nếu từng tenant có schema riêng, migration cần được điều phối và báo cáo trạng thái theo từng tenant. Không mặc định một schema history table chung phản ánh toàn bộ tenants.

## 27. Schema drift: database khác với lịch sử mong đợi

Schema drift có thể do một người sửa trực tiếp:

~~~sql
ALTER TABLE products
ADD COLUMN emergency_flag BOOLEAN;
~~~

mà không có file migration.

Hậu quả:

- Staging chạy được nhưng production khác.
- Migration mới đụng cột/index đã tồn tại.
- Fresh DB không tái tạo được production schema.
- Hibernate validate không phát hiện mọi object thừa.
- Thiếu audit ai sửa và lý do.

Cần:

- Kiểm soát DDL thủ công.
- Audit log/changelog và change management.
- So sánh schema thực với schema kỳ vọng.
- Hoàn nguyên hoặc đưa emergency change vào migration source có kiểm chứng.
- Không chạy `repair`/metadata sync mù quáng.

**History checksum phát hiện thay đổi ở script, không tự phát hiện mọi direct DDL trong database.**

## 28. Unique constraint và dữ liệu cũ

Giả sử `products.sku` có duplicate:

~~~sql
SELECT sku, COUNT(*)
FROM products
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Migration:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uq_products_sku UNIQUE (sku);
~~~

có thể thất bại.

Quy trình đúng:

1. Kiểm tra duplicate trên snapshot/staging.
2. Xác định business rule dọn/hợp nhất.
3. Kiểm tra foreign keys và nguồn tham chiếu.
4. Viết cleanup migration/job có review.
5. Xác nhận không còn duplicate.
6. Thêm unique constraint.
7. Test application xử lý constraint violation.

Không xóa record chỉ để migration qua được khi chưa xác định bản ghi có ý nghĩa nghiệp vụ gì.

## 29. Migration thất bại giữa chừng

Ví dụ:

~~~sql
ALTER TABLE products ADD COLUMN status VARCHAR(20);

UPDATE products SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE products
ALTER COLUMN status SET NOT NULL;
~~~

Nếu câu cuối lỗi, database có thể rollback toàn bộ hoặc để lại partial changes tùy transactional DDL.

Quy trình xử lý:

1. **Dừng rollout app mới** nếu schema chưa tương thích.
2. Lưu lỗi, migration ID, SQLState, database/version.
3. Xác định transaction đã rollback hay partial commit.
4. Đọc history table và schema state.
5. Kiểm tra dữ liệu thực.
6. Quyết định restore/forward fix/manual cleanup có approval.
7. Tạo migration mới khi cần; tránh sửa applied history tùy tiện.
8. Chỉ repair metadata sau khi database state đã được hòa giải.
9. Chạy lại validation/integration tests trước khi deploy tiếp.

**Không lặp lại migrate vô hạn trong khi chưa hiểu vì sao nó thất bại.**

## 30. Rollback code khác rollback database

Ví dụ migration:

~~~sql
UPDATE users
SET email = LOWER(email);
~~~

Sau commit, dữ liệu chữ hoa ban đầu đã mất nếu không lưu lại. Không có SQL đảo ngược đơn giản để biết ký tự nào từng viết hoa.

Tương tự:

~~~sql
DROP COLUMN legacy_status;
~~~

có thể làm mất dữ liệu. Một rollback chỉ `ADD COLUMN legacy_status` không lấy lại dữ liệu cũ.

Phải phân biệt:

- **Code rollback:** quay phiên bản ứng dụng.
- **Schema rollback:** đảo thay đổi lược đồ nếu khả thi.
- **Data restore:** khôi phục từ backup/audit/checkpoint.
- **Roll forward:** migration mới sửa trạng thái lỗi.
- **Expand-contract:** tránh phải rollback destructive DDL trong một release.

Không xem công cụ migration có hỗ trợ lệnh rollback là bằng chứng rằng mọi dữ liệu có thể được phục hồi.

## 31. Hibernate `ddl-auto=validate` sau migration

Cấu hình:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Hữu ích để phát hiện một số lỗi:

- Thiếu bảng/cột mà entity mapping cần.
- Tên bảng/cột sai do naming strategy.
- Kiểu SQL không tương thích.
- Hibernate trỏ nhầm schema/DB.
- Migration đã không áp dụng như mong đợi.

Không sửa lỗi production bằng cách bật `ddl-auto=update` để Hibernate tự thêm cột. Cần xác định migration nào thiếu hoặc mapping nào sai rồi sửa đúng owner.

`validate` không bảo đảm:

- Mọi index/constraint đều đúng.
- Data migration đã hoàn tất.
- Trigger/procedure có hoạt động không.
- Quyền DB và row-level security.
- Rollback/compatibility của ứng dụng cũ.
- Không có drift hoặc history mismatch.

Nó là một **hàng rào bổ sung**, không thay toàn bộ migration validation.

## 32. Review entity mapping và migration cùng một pull request

Thay đổi:

~~~java
@Column(name = "display_name", nullable = false)
private String displayName;
~~~

cần đi cùng kế hoạch:

~~~sql
ALTER TABLE products
ADD COLUMN display_name VARCHAR(200);
~~~

rồi backfill và siết constraint đúng giai đoạn.

PR review nên bao gồm:

- Entity mapping diff.
- SQL/changelog mới.
- Constraint/index/data implications.
- Test nâng cấp dữ liệu cũ.
- Compatibility old/new app.
- Rollout và failure plan.
- Quan sát lock/performance theo workload.

Không chỉ review cú pháp SQL. Review migration như một thay đổi trạng thái hệ thống production.

## 33. Checklist code review migration

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| ID/version có duy nhất? | Tránh conflict |
| Có sửa migration đã chạy? | Tránh checksum mismatch |
| SQL đúng DB production? | Dialect khác nhau |
| Đúng schema/DataSource? | Tránh migrate nhầm |
| Có mất data? | DROP/TRUNCATE/type change |
| NOT NULL/UNIQUE đã có data cleanup? | Tránh failure |
| Index/build có lock lớn? | Tránh outage |
| Old app vẫn chạy được? | Rolling deployment |
| Backfill cần batch? | Tránh long transaction |
| Có quyền DDL đúng? | Least privilege |
| Có thể recover partial failure? | DDL transaction limits |
| Có backup và approval? | Restore |
| Test fresh và upgrade? | Coverage |
| Có metrics/stop condition? | Production safety |

## 34. Một thay đổi viết bằng Flyway và Liquibase

Mục tiêu: thêm `description` vào bảng `products`.

**Flyway V2__add_product_description.sql:**

~~~sql
ALTER TABLE products
ADD COLUMN description VARCHAR(1000);
~~~

**Liquibase changeset YAML:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "002-add-product-description"
      author: "catalog-team"
      changes:
        - addColumn:
            tableName: products
            columns:
              - column:
                  name: description
                  type: VARCHAR(1000)
~~~

Kết quả mong muốn tương đương nhưng:

- Flyway theo dõi version/script/checksum.
- Liquibase theo dõi changelog path/author/id/checksum.
- Cả hai cần chạy đúng schema với đúng quyền.
- Cả hai có thể phát hiện thay đổi metadata sau applied.
- Cả hai không tự bảo đảm data/backward compatibility.
- Cả hai không thay Hibernate entity mapping.

**Chọn một công cụ làm chủ schema**, không chạy hai thay đổi tương đương độc lập lên cùng bảng.

## 35. Kịch bản release thực tế: thêm display_code

Yêu cầu: thêm `display_code` cho Product có hàng triệu rows và vẫn cần rolling deploy.

**Release A — Expand:**

~~~sql
ALTER TABLE products
ADD COLUMN display_code VARCHAR(80);
~~~

Old application vẫn chạy vì cột cũ không mất.

**Release B — Write compatibility:**

- New application ghi `display_code` khi tạo/sửa Product.
- Read path có fallback cho rows cũ.
- Các writers/batch jobs được cập nhật.
- Test old/new app cùng dùng một schema trong giai đoạn chuyển tiếp.

**Backfill:**

~~~sql
UPDATE products
SET display_code = sku
WHERE display_code IS NULL
  AND id BETWEEN :startId AND :endId;
~~~

Các placeholder `:startId`/`:endId` là tham số được bind bởi job, không phải SQL chạy nguyên trạng. Job chạy theo batch có checkpoint.

**Release C — Switch reads:**

- Kiểm tra số NULL còn lại.
- Xác nhận không còn writer cũ.
- Đổi code đọc cột mới.
- Theo dõi errors/replication lag.

**Release D — Contract:**

~~~sql
ALTER TABLE products
ALTER COLUMN display_code SET NOT NULL;
~~~

Nếu cần drop cột cũ, làm ở migration sau khi không còn app phụ thuộc cột đó.

Quy trình này cho thấy migration tool chỉ thực thi một phần của release plan. Thành công cần cả code compatibility, backfill và vận hành.

## 36. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Hibernate thiếu bảng/cột | Migration chưa chạy/chạy nhầm DB | Kiểm tra history, DataSource, locations |
| Flyway checksum mismatch | Versioned script bị sửa | Khôi phục file hoặc tạo version mới; không repair mù |
| Liquibase checksum error | Changeset cũ bị sửa | Xác minh path/author/id/checksum |
| Flyway báo schema không rỗng nhưng thiếu history | Existing DB chưa baseline | Onboarding baseline có kiểm chứng |
| Flyway pending bỏ qua | Sai version/order/location | Xem info/validate/config |
| Liquibase changeset không chạy | Context/label/precondition/lock/path | Kiểm tra filters và DATABASECHANGELOG |
| Repeatable migration lỗi lần hai | SQL không idempotent | Sửa repeatable design |
| Liquibase lock lâu | Migration đang chạy/chậm hoặc stale | Xác minh job trước khi unlock |
| DDL partial applied | Nontransactional DDL | Điều tra state và cleanup có approval |
| Hibernate update tự sửa schema | Chưa tắt ddl-auto update | Dùng none/validate và migration owner |
| App cũ lỗi sau DDL | Drop/rename phá compatibility | Expand-contract |
| Index build gây latency | DDL lớn/lock | Online strategy, scheduling |
| Add NOT NULL thất bại | NULL data hoặc writer cũ | Backfill và chuyển writer |
| Unique constraint thất bại | Duplicate | Dọn dữ liệu có kiểm chứng |
| Staging pass, prod lỗi | Drift/dữ liệu thật/volume | Test upgrade snapshot |
| Schema rollback mất data | DROP/data transformation irreversible | Backup/roll-forward/recovery |
| Nhiều pod tranh migrate | Startup migrations đồng thời | Một migration job |
| H2 pass nhưng Postgres fail | Khác dialect/DDL | Testcontainers cùng engine |
| Runtime user thiếu quyền DDL | Phân quyền production | Migration credentials riêng |
| Migrate nhầm DB | URL/schema sai | Guardrails/approval/metadata verification |

## 37. Bài tập tình huống

**1. Vì sao không dùng Hibernate `ddl-auto=update` trên production thay migration tool?**

Vì không có lịch sử migration, data transformation, approval, zero-downtime plan và recovery phù hợp. Dùng Flyway/Liquibase làm chủ schema; Hibernate validate làm kiểm tra bổ sung.

**2. Flyway V2 đã chạy. Có nên sửa file V2 để đổi VARCHAR thành TEXT?**

Không. Tạo migration V3/V4 tiếp theo. Sửa file đã applied có thể làm history/checksum mismatch.

**3. Khi nào dùng Flyway repeatable?**

View/function/procedure definitions có thể chạy lại an toàn khi nội dung đổi. Tránh DML không idempotent.

**4. `flyway repair` có tự thay schema theo file vừa sửa?**

Không. Repair metadata/history không đồng nghĩa chạy DDL hoặc khôi phục data.

**5. Liquibase nhận diện changeset bằng gì?**

Changelog file path, author và id. ID không nhất thiết là số version.

**6. `DATABASECHANGELOGLOCK` để làm gì?**

Điều phối migration execution để tránh thay đổi schema đồng thời không kiểm soát.

**7. Thêm NOT NULL cho một cột mới ngay trên bảng hàng triệu rows có rủi ro gì?**

Dữ liệu cũ có NULL và writer cũ chưa cập nhật. Cần expand nullable, backfill, đổi writer rồi siết.

**8. Rollback YAML dùng dropColumn có khôi phục dữ liệu được nhập sau khi addColumn không?**

Không. Drop column xóa dữ liệu trong cột; rollback syntax không bảo đảm data recovery.

**9. Có nên cho nhiều pod tự chạy migration lúc startup?**

Có cơ chế coordination nhưng deployment job riêng thường dễ giám sát, phân quyền và retry hơn.

**10. Tại sao test trên DB trống chưa đủ?**

Production có NULL, duplicate, dữ liệu thật, FK, index và volume. Phải test upgrade từ schema/data cũ.

**11. Hibernate validate có kiểm tra mọi schema drift không?**

Không. Nó kiểm tra mapping compatibility ở mức hỗ trợ, không phát hiện mọi external changes.

**12. Seed demo data nên đi production migration chung không?**

Không nếu chỉ phục vụ test. Dùng test-only locations hoặc Liquibase context chỉ bật rõ ở test.

**13. DDL có luôn rollback cùng transaction không?**

Không. Phụ thuộc database, operation và tool config.

**14. Đổi tên cột trong rolling deploy nên làm gì?**

Expand–migrate–contract; giữ old/new compatibility cho tới khi mọi reader/writer chuyển xong.

**15. Production bị sửa DDL thủ công thì sao?**

Có drift. Cần đối soát DB state và source/history, không chỉ repair checksum.

**16. Có nên dùng một DB user cho runtime và migration?**

Nếu có thể, tách quyền theo least privilege để giảm rủi ro ứng dụng runtime vô tình thay schema.

## 38. Checklist vận hành

Trước khi tạo migration:

- Xác định DB engine/version và schema owner.
- Chọn Flyway **hoặc** Liquibase làm chủ schema.
- Đánh giá entity mapping và old/new app compatibility.
- Thiết kế expand/backfill/contract nếu có breaking change.
- Tạo source migration có tên/ID rõ.

Trước khi merge:

- Review DDL, data effects, lock/index risks.
- Không sửa migration đã applied.
- Test fresh schema và upgrade schema cũ.
- Chạy Hibernate validate sau migration.
- Kiểm chứng recovery/backup plan.

Trước production:

- Xác nhận DB/schema/tenant đúng.
- Kiểm tra migration history/changelog.
- Approval và migration credential đúng quyền.
- Backup/restore được kiểm chứng.
- Một executor duy nhất cho migration.
- Monitoring/timeout/stop condition.

Sau production:

- Xác minh version/changesets đã applied.
- Kiểm tra Hibernate startup và smoke tests.
- Quan sát errors, locks, replication lag, query latency.
- Ghi lại release/migration state.
- Chỉ contract khi không còn phụ thuộc cũ.

## 39. Tổng kết

**Tích hợp Flyway hoặc Liquibase với Hibernate không chỉ là chạy vài câu ALTER TABLE.** Mục tiêu là biến thay đổi database thành lịch sử có thể kiểm toán, được quản lý bằng source control, review/test/deploy theo thứ tự rõ ràng và không làm mất dữ liệu hoặc phá vỡ ứng dụng đang hoạt động.

Các nguyên tắc cốt lõi:

1. **Hibernate quản lý entity, migration tool quản lý schema evolution.** Production nên dùng `ddl-auto=none` hoặc `validate` tùy quy trình.
2. **Một schema có một migration owner.** Không để nhiều cơ chế initialization chồng lấn.
3. **Migration đã áp dụng là lịch sử.** Dùng version/changeset mới thay vì sửa file đã chạy.
4. **Checksum/history phát hiện lệch nhưng không tự sửa schema.** Repair và metadata sync không thay thế DDL.
5. **Test cả fresh DB và upgrade DB có dữ liệu cũ.** Đây là hai trường hợp khác nhau.
6. **DDL và rollback phụ thuộc database.** Không giả định mọi ALTER được rollback toàn bộ.
7. **Zero-downtime cần expand–migrate–contract.** Không drop cột mà ứng dụng cũ còn dùng.
8. **Backfill dữ liệu lớn cần batch/checkpoint và giám sát.** Không chặn deployment quá lâu.
9. **Migration production cần executor, credential và quyền rõ.** Startup migration chỉ là một lựa chọn.
10. **Hibernate validate không thay schema review, drift detection hoặc test dữ liệu.**
11. **Code rollback, schema rollback và data restore là ba chuyện khác nhau.**
12. **Source migrations, database state và application release phải được giữ nhất quán.**

Một quy trình tốt không chỉ hỏi **“script có chạy được không?”** mà còn hỏi **“nó chạy trên database nào, với dữ liệu nào, theo thứ tự nào, ứng dụng cũ còn chạy được không, nếu lỗi sẽ khôi phục thế nào và ai chịu trách nhiệm?”**.

## Tài liệu tham khảo

- [Spring Boot — Database initialization, Flyway và Liquibase](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Redgate Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Redgate Flyway — Versioned migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Redgate Flyway — Repeatable migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/repeatable-migrations)
- [Redgate Flyway — Schema history table](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table)
- [Redgate Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Redgate Flyway — Repair](https://documentation.red-gate.com/fd/repair-277578892.html)
- [Liquibase — What is a Changeset?](https://docs.liquibase.com/community/user-guide-5-0/what-is-a-changeset)
- [Liquibase — Preconditions](https://docs.liquibase.com/community/user-guide-5-0-2/what-are-preconditions)
