# Phân biệt tạo schema bằng JPA và quản lý migration trong Spring Data JPA

## 1. Schema database và vai trò của JPA

Schema database mô tả cấu trúc lưu trữ mà ứng dụng sử dụng: table, column, kiểu dữ liệu, primary key, foreign key, unique constraint, index, view và các đối tượng liên quan.

Trong ứng dụng Spring Data JPA, entity mô tả cách Java ánh xạ tới cấu trúc database. Ví dụ:

~~~java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(String email, Instant createdAt) {
        this.email = email;
        this.createdAt = createdAt;
    }
}
~~~

Các annotation như **@Entity**, **@Table**, **@Column**, **@Id** và **@JoinColumn** mô tả mapping giữa object và database. Chúng không tự biến mọi thay đổi trong Java thành một quy trình nâng cấp database có kiểm soát.

Có hai nhóm việc cần phân biệt:

- **Schema generation:** tạo, thay đổi, kiểm tra hoặc xóa cấu trúc database dựa trên mapping entity.
- **Database migration:** quản lý các thay đổi schema và dữ liệu theo từng phiên bản, lưu lịch sử đã áp dụng và triển khai cùng mã nguồn qua nhiều môi trường.

JPA provider như Hibernate có thể sinh DDL từ entity. Flyway và Liquibase quản lý migration theo lịch sử thay đổi. Hai cách giải quyết các bài toán liên quan nhưng có mục tiêu và mức độ kiểm soát khác nhau.

## 2. Tạo schema tự động bằng JPA/Hibernate

Hibernate có thể đọc entity metadata rồi tạo câu lệnh DDL để khởi tạo schema. Trong Spring Boot, cấu hình phổ biến nhất là:

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

Thuộc tính này là shortcut cho Hibernate schema management, tương ứng với thuộc tính nội bộ **hibernate.hbm2ddl.auto**.

Các giá trị thường dùng trong Spring Boot:

| Giá trị | Hành vi |
|---|---|
| **none** | Không tự tạo hoặc thay đổi schema |
| **validate** | Kiểm tra mapping với schema hiện có; không sửa schema |
| **update** | Cố gắng điều chỉnh schema hiện có theo mapping |
| **create** | Tạo schema mới khi khởi động; các đối tượng cũ có thể bị loại bỏ trước khi tạo |
| **create-drop** | Tạo schema khi khởi động và xóa khi SessionFactory/ứng dụng kết thúc |

Mặc định của Spring Boot phụ thuộc môi trường và schema manager: với embedded database như H2, HSQL hoặc Derby, Boot có thể chọn create-drop khi không phát hiện schema manager; nếu không, mặc định thường là none. Vì vậy, nên khai báo rõ ddl-auto theo từng profile thay vì dựa vào default.

### Ví dụ cho môi trường phát triển

~~~properties
# application-dev.properties
spring.jpa.hibernate.ddl-auto=update
~~~

Cấu hình này tiện khi thử nghiệm entity mới trên database phát triển có thể tạo lại. Tuy nhiên, schema được Hibernate cập nhật không có lịch sử migration chi tiết để triển khai nhất quán qua nhiều môi trường.

### Ví dụ cho test dùng database tạm

~~~properties
# application-test.properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Nếu test dùng database riêng, tạo schema lúc bắt đầu và xóa khi kết thúc giúp mỗi lần chạy có trạng thái sạch. Không dùng cấu hình này cho database chứa dữ liệu cần giữ lại.

## 3. Tạo schema, validate và update khác nhau thế nào?

### create và create-drop

**create** thích hợp để dựng schema mới trong môi trường có thể xóa bỏ. Nếu database đang có dữ liệu, việc tái tạo schema có thể làm mất dữ liệu hiện hữu.

**create-drop** còn xóa schema khi Hibernate đóng SessionFactory. Đây là lựa chọn phổ biến cho database kiểm thử tạm thời, không phải chiến lược triển khai production.

### update

**update** cố gắng điều chỉnh cấu trúc database để khớp entity metadata. Nó hữu ích cho prototype hoặc môi trường phát triển đơn giản, nhưng không phải một migration engine.

Hibernate không quản lý lịch sử thay đổi theo từng phiên bản như Flyway/Liquibase. Việc đổi tên cột, chuyển đổi dữ liệu, chia cột, gộp bảng hoặc triển khai nhiều phiên bản ứng dụng đồng thời cần kế hoạch cụ thể mà tự động update không thể thay thế.

Không nên giả định update sẽ nhận ra ý định nghiệp vụ khi một property bị đổi tên. Tùy provider, dialect và khác biệt mapping, thao tác có thể dẫn tới tạo cột mới trong khi dữ liệu cũ vẫn nằm ở cột trước đó.

### validate

**validate** kiểm tra mapping entity với schema hiện có và báo lỗi nếu cấu trúc cần thiết không phù hợp. Nó không tạo bảng, không thêm cột và không chuyển đổi dữ liệu.

Validate là bước kiểm tra hữu ích sau khi migration đã chạy. Tuy nhiên, nó không phải công cụ phát hiện mọi dạng schema drift: không nên coi validate là bản so sánh đầy đủ của tất cả index, trigger, procedure, quyền truy cập hoặc các đối tượng database không được mapping entity mô tả.

## 4. JPA schema-generation properties

Ngoài shortcut Hibernate ddl-auto, Jakarta Persistence định nghĩa các thuộc tính schema generation chuẩn. Ví dụ:

- **jakarta.persistence.schema-generation.database.action**: chỉ định hành động DDL trực tiếp trên database.
- **jakarta.persistence.schema-generation.scripts.action**: chỉ định hành động xuất DDL ra script.
- **jakarta.persistence.schema-generation.scripts.create-target**: đích lưu script tạo schema.
- **jakarta.persistence.schema-generation.scripts.drop-target**: đích lưu script xóa schema.

Các action chuẩn gồm những lựa chọn như none, create, drop và drop-and-create. Chi tiết hỗ trợ có thể phụ thuộc JPA provider và phiên bản.

Ví dụ, có thể yêu cầu provider xuất DDL ra file để review:

~~~properties
spring.jpa.properties.jakarta.persistence.schema-generation.scripts.action=create
spring.jpa.properties.jakarta.persistence.schema-generation.scripts.create-target=target/generated-schema.sql
spring.jpa.properties.jakarta.persistence.schema-generation.database.action=none
~~~

Ví dụ này yêu cầu xuất script tạo schema và không thực thi DDL trực tiếp lên database. Đường dẫn output và khả năng thực thi phụ thuộc provider/build configuration; hãy kiểm tra log và file thực tế.

Script sinh từ entity có thể giúp tạo bản nháp ban đầu, nhưng cần review thủ công trước khi dùng làm migration. Các quy tắc nghiệp vụ, dữ liệu hiện hữu, index tối ưu, partition, trigger và thứ tự rollout có thể không được thể hiện đầy đủ trong entity mapping.

## 5. Vì sao cần database migration?

Database migration ghi lại từng thay đổi schema hoặc dữ liệu theo một trình tự có thể lặp lại.

Ví dụ, một ứng dụng ban đầu có bảng customer với email. Sau đó nghiệp vụ cần thêm trạng thái, thêm index và chuyển đổi dữ liệu cũ. Thay vì để mỗi môi trường tự suy ra cấu trúc từ entity hiện tại, migration mô tả rõ từng bước:

1. Tạo bảng customer.
2. Thêm cột status.
3. Gán giá trị cho dữ liệu đã tồn tại.
4. Bổ sung constraint.
5. Tạo index phù hợp.
6. Thực hiện các thay đổi tiếp theo bằng migration mới.

Migration được lưu cùng source code trong version control. Development, test, staging và production áp dụng cùng chuỗi migration theo thứ tự. Công cụ migration lưu lịch sử để biết phiên bản nào đã được chạy.

Lợi ích:

- Có lịch sử schema và data change.
- Review DDL/DML trong pull request.
- Triển khai lặp lại qua nhiều môi trường.
- Phát hiện migration bị sửa sau khi đã áp dụng thông qua checksum.
- Kiểm soát thứ tự, baseline và trạng thái triển khai.
- Có thể chuẩn bị rollback hoặc forward-fix theo kế hoạch.
- Dễ dựng database kiểm thử tương ứng với phiên bản ứng dụng.

## 6. Flyway hoạt động như thế nào?

**Flyway** quản lý migration chủ yếu qua file SQL hoặc Java migration. Với SQL migration dạng versioned, tên file thường theo cấu trúc:

~~~text
V<VERSION>__<DESCRIPTION>.sql
~~~

Ví dụ:

~~~text
src/main/resources/db/migration/
    V1__create_customer.sql
    V2__add_customer_status.sql
    V3__create_customer_email_index.sql
    R__refresh_customer_views.sql
~~~

- **V1**, **V2**, **V3** là version migration; mỗi version phải duy nhất.
- Phần sau hai dấu gạch dưới là mô tả.
- **R__...** là repeatable migration, được chạy lại khi checksum thay đổi.

Flyway tạo bảng lịch sử, mặc định là **flyway_schema_history**, để lưu migration đã áp dụng, version, checksum, thời điểm và trạng thái. Khi chạy migrate, Flyway tìm migration hiện có, so sánh với lịch sử rồi thực thi những migration còn thiếu theo thứ tự.

### Versioned migration

Versioned migration được áp dụng đúng một lần cho một database. Đây là nơi phù hợp để tạo/đổi bảng, thêm cột, constraint, index và chuyển đổi dữ liệu.

Sau khi một versioned migration đã được triển khai xuống môi trường dùng chung hoặc production, hãy xem file đó là bất biến. Nếu cần sửa cấu trúc, tạo migration version mới thay vì chỉnh sửa file cũ. Nếu file cũ thay đổi, checksum validation có thể thất bại vì nội dung không còn khớp với lịch sử.

### Repeatable migration

Repeatable migration không có version. Flyway chạy lại khi checksum của file thay đổi. Chúng thường phù hợp với view, procedure, function hoặc reference data có thể tạo lại theo cách idempotent.

Ví dụ:

~~~sql
-- R__refresh_customer_view.sql
CREATE OR REPLACE VIEW active_customer AS
SELECT id, email
FROM customer
WHERE status = 'ACTIVE';
~~~

Câu lệnh trên cần cú pháp phù hợp với database mục tiêu. Một repeatable migration phải được thiết kế để có thể chạy lại an toàn.

## 7. Ví dụ Flyway migration

Migration đầu tiên tạo bảng:

~~~sql
-- V1__create_customer.sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);
~~~

Migration thứ hai thêm cột status theo cách có thể xử lý dữ liệu hiện có:

~~~sql
-- V2__add_customer_status.sql
ALTER TABLE customer
    ADD COLUMN status VARCHAR(20);

UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Sau khi ứng dụng đã được triển khai và dữ liệu cũ được backfill, một migration tiếp theo có thể đặt NOT NULL:

~~~sql
-- V3__require_customer_status.sql
ALTER TABLE customer
    ALTER COLUMN status SET NOT NULL;
~~~

Câu lệnh ALTER COLUMN trong ví dụ này dùng cú pháp PostgreSQL. MySQL, SQL Server, Oracle và các database khác có thể dùng cú pháp khác. Migration cần được viết và kiểm thử theo database thật mà ứng dụng sử dụng.

Cách chia bước giúp ứng dụng có thể tương thích trong giai đoạn chuyển tiếp: thêm cột nullable, deploy code đọc/ghi status, backfill dữ liệu, rồi mới đặt constraint bắt buộc. Với bảng lớn, UPDATE toàn bảng có thể tạo lock và transaction log lớn; hãy lập kế hoạch batch/backfill phù hợp.

## 8. Tích hợp Flyway với Spring Boot

Thêm Flyway dependency tương thích với phiên bản Spring Boot và database driver của dự án. Ví dụ Maven dùng dependency management của Spring Boot:

~~~xml
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
</dependency>
~~~

Một số database cần module Flyway riêng theo phiên bản Flyway, chẳng hạn module hỗ trợ MySQL. Kiểm tra tài liệu và dependency management của phiên bản đang dùng thay vì thêm tùy ý một version khác với BOM.

Cấu hình:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration

# Migration tạo schema; Hibernate chỉ kiểm tra mapping
spring.jpa.hibernate.ddl-auto=validate
~~~

Khi Spring Boot phát hiện Flyway trên classpath và được bật, Flyway tự tìm migration tại location rồi áp dụng migration đang chờ trong quá trình khởi động ứng dụng. Boot quản lý thứ tự khởi tạo để schema được chuẩn bị trước khi JPA cần sử dụng.

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.flyway.enabled | Bật/tắt Flyway |
| spring.flyway.locations | Vị trí tìm migration |
| spring.flyway.schemas | Schema Flyway quản lý |
| spring.flyway.default-schema | Schema mặc định |
| spring.flyway.baseline-on-migrate | Cho phép tự baseline schema không rỗng trong tình huống được cấu hình |
| spring.flyway.validate-on-migrate | Kiểm tra migration khi migrate |
| spring.flyway.clean-disabled | Vô hiệu hóa lệnh clean; mặc định Spring Boot hiện hành là true |

Không bật lệnh clean trên database quan trọng. Lệnh clean có thể xóa đối tượng schema và dữ liệu; chỉ dùng trên database tạm trong môi trường kiểm thử được kiểm soát.

## 9. Flyway baseline và validate

### Baseline database hiện có

Nếu ứng dụng đã có database trước khi bắt đầu dùng Flyway, không thể giả định database đó là database trống. Cần xác định schema hiện tại tương ứng với phiên bản nào, đối chiếu cấu trúc và chọn baseline version phù hợp.

Flyway baseline đánh dấu database hiện có ở một version xác định để các migration mới hơn được áp dụng. Việc dùng baseline-on-migrate cần rất thận trọng: nếu cấu hình sai, một database không đúng trạng thái mong đợi có thể bị đánh dấu như đã có baseline.

Nên tạo baseline có chủ đích, kiểm tra schema và dữ liệu hiện có, thử trên bản sao trước rồi mới triển khai.

### Validate

Lệnh **flyway validate** so sánh các migration đã áp dụng với migration hiện có, bao gồm checksum, tên và loại migration. Nó giúp phát hiện file đã chạy bị sửa, file bị thiếu hoặc migration chưa khớp.

Ví dụ:

~~~bash
# Kiểm tra migration so với lịch sử database
./mvnw flyway:validate

# Áp dụng migration đang chờ
./mvnw flyway:migrate
~~~

Tên goal Maven và cách gọi phụ thuộc plugin đã cấu hình trong build. Có thể dùng Flyway CLI hoặc Gradle task tương ứng.

Nếu validate thất bại, hãy xác định môi trường nào đã chạy migration, file nào bị thay đổi và lịch sử nào đang khác. Không tùy tiện sửa checksum hoặc chạy repair chỉ để làm pipeline xanh; repair phải dựa trên trạng thái database đã được kiểm tra.

## 10. Liquibase hoạt động như thế nào?

**Liquibase** quản lý database change bằng changelog. Changelog chứa các changeset, mỗi changeset mô tả một thay đổi logic. Có thể viết changelog bằng XML, YAML, JSON hoặc formatted SQL.

Một changeset được định danh bởi tổ hợp **id**, **author** và đường dẫn changelog. Liquibase ghi lịch sử vào các bảng như **DATABASECHANGELOG** và dùng **DATABASECHANGELOGLOCK** để kiểm soát việc cập nhật đồng thời.

Ví dụ changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: created_at
                  type: timestamp
                  constraints:
                    nullable: false
~~~

Đây là ví dụ cấu trúc changelog; kiểu auto increment, identity và timestamp có thể cần điều chỉnh theo database mục tiêu.

### Changeset và checksum

Khi Liquibase áp dụng changeset, nó tính checksum và ghi nhận vào DATABASECHANGELOG. Khi chạy lại, checksum được so sánh để phát hiện changeset đã chạy bị chỉnh sửa.

Sau khi changeset đã triển khai, hãy giữ nó bất biến. Tạo changeset mới để sửa schema hoặc dữ liệu. Một số changeset có thể dùng runOnChange cho đối tượng như view/procedure cần cập nhật lại khi nội dung thay đổi; chỉ dùng khi câu lệnh được thiết kế để chạy lại an toàn.

### Preconditions, contexts và labels

Liquibase hỗ trợ preconditions để kiểm tra điều kiện database trước khi chạy changeset. Ví dụ kiểm tra table hoặc column đã tồn tại, database vendor có đúng không, hoặc dữ liệu thỏa giả định trước khi drop/alter.

Contexts và labels giúp chọn nhóm changeset theo mục đích hoặc môi trường. Hãy dùng chúng có quy ước rõ ràng; đừng dùng filter môi trường để che giấu một migration bắt buộc.

### Rollback

Liquibase hỗ trợ rollback theo tag, thời gian hoặc số changeset và có thể khai báo rollback logic tùy loại changelog. Tuy nhiên, không phải mọi thao tác đều có thể đảo ngược an toàn. Khi migration đã xóa hoặc biến đổi dữ liệu, rollback cần logic phục hồi dữ liệu hoặc backup phù hợp.

## 11. Tích hợp Liquibase với Spring Boot

Thêm dependency do Spring Boot dependency management quản lý:

~~~xml
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
~~~

Tạo changelog master, ví dụ:

~~~text
src/main/resources/db/changelog/db.changelog-master.yaml
~~~

Cấu hình:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml

spring.jpa.hibernate.ddl-auto=validate
~~~

Spring Boot tự cấu hình Liquibase khi dependency có trên classpath và feature được bật. Liquibase đọc master changelog, theo các file được include rồi áp dụng changeset còn thiếu.

Không cấu hình Flyway và Liquibase cùng quản lý một schema. Chọn một công cụ làm migration authority để tránh hai lịch sử và hai quy trình cạnh tranh nhau.

## 12. So sánh JPA schema generation, Flyway và Liquibase

| Tiêu chí | JPA/Hibernate DDL | Flyway | Liquibase |
|---|---|---|---|
| Nguồn mô tả | Entity mapping | Migration file | Changelog/changeset |
| Mục tiêu chính | Khởi tạo hoặc kiểm tra schema | Quản lý migration theo version | Quản lý thay đổi qua changeset |
| Lịch sử triển khai | Không có migration history chuẩn | flyway_schema_history | DATABASECHANGELOG |
| Phát hiện file đã sửa | Không có checksum migration | Có checksum validation | Có changeset checksum |
| Data migration | Không phải workflow quản lý dữ liệu có version | Có thể dùng SQL/Java migration | Có thể dùng change type hoặc SQL |
| Rollback | Không có lịch sử rollback theo version | Chủ yếu tạo migration mới để tiến về trước; undo phụ thuộc phiên bản/edition | Có rollback support nhưng vẫn cần kiểm tra khả năng đảo ngược |
| Đa database | Phụ thuộc JPA provider/dialect | SQL migration thường gắn với dialect; có Java migration | Có change type trừu tượng và SQL tùy chỉnh |
| Phù hợp nhất | Dev/test, bootstrap, validate mapping | SQL-first, migration tuần tự rõ ràng | Changelog có cấu trúc, preconditions, contexts và rollback metadata |

Không có một công cụ phù hợp cho mọi dự án. Nếu nhóm muốn kiểm soát DDL bằng SQL rõ ràng và version tuần tự, Flyway thường đơn giản. Nếu cần changelog có cấu trúc, preconditions, contexts/labels và rollback metadata, Liquibase có thể phù hợp hơn.

## 13. Không để nhiều công cụ cùng sở hữu schema

Một lỗi cấu hình phổ biến là đồng thời dùng Hibernate update, schema.sql, data.sql và Flyway/Liquibase để tạo hoặc thay đổi cùng một schema.

Ví dụ không nên dùng trong môi trường migration-managed:

~~~properties
spring.jpa.hibernate.ddl-auto=update
spring.flyway.enabled=true
spring.sql.init.mode=always
~~~

Khi nhiều công cụ cùng thay đổi schema, thứ tự khởi tạo có thể tạo xung đột: Hibernate thêm cột, migration cố thêm lại cột, script chạy trước khi bảng tồn tại hoặc môi trường có trạng thái khác nhau.

Spring Boot khuyến nghị dùng Flyway hoặc Liquibase làm công cụ cấp cao để tạo và khởi tạo schema. Không nên kết hợp chúng với schema.sql/data.sql như một quy trình song song cho cùng database.

Cấu hình thường dùng khi migration tool là nguồn quản lý schema:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Hoặc dùng none nếu không muốn Hibernate thực hiện cả bước validation lúc khởi động. Với validate, mapping được kiểm tra sau khi migration đã chuẩn bị schema.

## 14. Entity mapping phải khớp với migration

Migration tạo cấu trúc vật lý. Entity mapping mô tả cách ứng dụng sử dụng cấu trúc đó. Hai phần phải nhất quán.

Ví dụ migration tạo cột:

~~~sql
ALTER TABLE customer
    ADD COLUMN created_at TIMESTAMP NOT NULL;
~~~

Entity mapping:

~~~java
@Column(name = "created_at", nullable = false)
private Instant createdAt;
~~~

Một số điểm cần đồng bộ:

- Tên table và column.
- Kiểu dữ liệu, precision và scale.
- Nullability và default value.
- Primary key, foreign key và unique constraint.
- Index cần cho truy vấn.
- Enum storage strategy.
- Join column và association mapping.
- Naming strategy và schema name.

Không cho rằng **@Column(nullable = false)** tự tạo constraint trên database nếu Hibernate không quản lý DDL. Với migration-managed schema, phải có DDL tương ứng trong migration.

Đặc biệt chú ý naming strategy: Hibernate có thể chuyển property camelCase thành snake_case theo cấu hình. Hãy kiểm tra tên SQL thực tế trong migration và database thay vì đoán tên cột.

## 15. Schema migration và data migration

Schema migration thay đổi cấu trúc. Data migration chuyển đổi dữ liệu đã tồn tại để phù hợp cấu trúc hoặc nghiệp vụ mới.

Ví dụ đổi từ full_name thành first_name và last_name. Chỉ thêm hai cột là chưa đủ; cần chuyển dữ liệu cũ, cập nhật code đọc/ghi, rồi mới xóa cột cũ.

Một chiến lược triển khai an toàn thường gồm:

1. **Expand:** thêm cột hoặc bảng mới theo cách tương thích ngược; giữ cấu trúc cũ.
2. **Deploy compatible code:** ứng dụng mới có thể đọc/ghi cả cấu trúc cũ và mới hoặc ghi song song trong giai đoạn chuyển tiếp.
3. **Backfill:** chuyển dữ liệu cũ theo batch, có thể chạy lại an toàn và theo dõi tiến độ.
4. **Switch reads:** chuyển ứng dụng sang dùng cấu trúc mới sau khi dữ liệu đã đầy đủ.
5. **Contract:** sau khi mọi instance cũ đã ngừng dùng cấu trúc cũ, xóa cột hoặc bảng cũ bằng migration riêng.

Mẫu expand-and-contract đặc biệt hữu ích khi deploy rolling hoặc blue/green, nơi phiên bản ứng dụng cũ và mới có thể cùng hoạt động trong một khoảng thời gian.

Không gộp một thay đổi phá vỡ tương thích vào cùng thời điểm với code deploy nếu ứng dụng cũ vẫn có thể truy cập database. Kiểm tra thời gian backfill, lock, dung lượng transaction log và khả năng rollback/forward-fix.

## 16. Migration trên bảng lớn

ALTER TABLE, tạo index hoặc backfill hàng triệu dòng có thể gây lock và ảnh hưởng truy vấn đang chạy. Cú pháp và mức độ lock phụ thuộc database/version.

Trước khi migration bảng lớn:

- Kiểm tra execution plan và index hiện có.
- Xác định DDL có lock table hay không và thời gian dự kiến.
- Dùng concurrent/online index build nếu database hỗ trợ và phù hợp.
- Chia data backfill thành batch theo khóa hoặc khoảng dữ liệu.
- Lưu checkpoint để tác vụ có thể tiếp tục sau lỗi.
- Giới hạn transaction size và theo dõi log/replication lag.
- Chuẩn bị thời gian triển khai, giám sát và phương án forward-fix.
- Thử trên bản sao có kích thước gần production.

Không giả định mọi DDL đều transactional. Một số database tự commit hoặc không thể rollback một số thao tác DDL. Kiểm tra hành vi của database thật và Flyway/Liquibase configuration trước khi dựa vào rollback tự động.

## 17. Kiểm thử migration trong CI/CD

Pipeline nên kiểm tra cả migration và mapping:

1. Khởi tạo database sạch đúng loại và version gần production.
2. Chạy toàn bộ migration từ đầu.
3. Chạy validate/checksum của công cụ migration.
4. Khởi động Spring Boot với Hibernate ddl-auto=validate.
5. Chạy integration test repository/service.
6. Kiểm tra các constraint, index và dữ liệu sau migration.
7. Kiểm tra nâng cấp từ schema version cũ nếu cần hỗ trợ upgrade.
8. Lưu log và migration report để truy vết.

Có thể dùng Testcontainers để chạy cùng database engine với production. H2 không phải lúc nào cũng thay thế được PostgreSQL, MySQL hoặc SQL Server vì cú pháp DDL, kiểu dữ liệu, constraint và transaction behavior khác nhau.

Migration test cần bao gồm:

- Database trống chạy lên phiên bản mới nhất.
- Database cũ có dữ liệu được nâng cấp thành công.
- Data backfill cho bản ghi null/legacy.
- Unique/foreign key constraint không làm mất dữ liệu hợp lệ.
- Migration lỗi dừng pipeline và không đánh dấu thành công sai.
- Hibernate validate phát hiện mapping không khớp.
- Chạy lại ứng dụng không thực thi lại versioned migration đã thành công.

## 18. Quản lý database đã tồn tại và schema drift

Một dự án chuyển sang Flyway/Liquibase có thể đã có nhiều database được tạo thủ công. Cần kiểm kê trước khi baseline:

- Phiên bản ứng dụng và schema thực tế từng môi trường.
- Bảng, cột, constraint và index.
- Dữ liệu đặc biệt hoặc dữ liệu lịch sử.
- Những thay đổi thủ công chưa được ghi vào source control.
- Khác biệt về collation, timezone, sequence và schema owner.

Sau khi chọn baseline, chạy migration trên bản sao của từng môi trường, đối chiếu schema và xác nhận không có thay đổi ngoài dự kiến.

Schema drift là tình trạng database thực tế khác với schema mà migration history hoặc source code mô tả. Có thể phát sinh do thao tác thủ công, script ngoài pipeline, migration bị bỏ qua hoặc environment được tạo từ một snapshot cũ.

Migration history và checksum giúp phát hiện một số sai lệch, nhưng không thay thế việc so sánh schema thực tế, backup và quy trình change control.

## 19. Rollback và forward-fix

Rollback là khôi phục trạng thái trước đó. Không phải migration nào cũng đảo ngược được.

Ví dụ:

- Thêm cột nullable thường có thể rollback bằng cách drop column nếu chưa có dữ liệu cần giữ.
- Xóa cột có dữ liệu không thể phục hồi chỉ bằng cách thêm lại cột.
- Chuyển đổi dữ liệu có thể mất thông tin nếu phép biến đổi không thuận nghịch.
- Tạo index thường dễ rollback hơn thay đổi dữ liệu nghiệp vụ.

Trước migration có nguy cơ cao, cần backup/snapshot và kiểm tra khả năng restore. Việc có file rollback không đảm bảo rollback an toàn khi ứng dụng mới đã ghi dữ liệu theo schema mới.

Trong production, forward-fix thường an toàn hơn việc cố đảo ngược một migration phá hủy dữ liệu: tạo migration mới để sửa trạng thái hiện tại và giữ lịch sử triển khai nhất quán.

## 20. Lỗi thường gặp

### 20.1. Dùng ddl-auto=create hoặc create-drop trên production

Có thể làm mất bảng/dữ liệu hoặc xóa schema khi ứng dụng kết thúc. Dùng migration tool và đặt ddl-auto phù hợp, thường là validate hoặc none.

### 20.2. Coi update là migration hoàn chỉnh

Hibernate update không cung cấp lịch sử migration có version, checksum, data transformation và quy trình rollout. Dùng Flyway/Liquibase cho schema evolution cần kiểm soát.

### 20.3. Sửa file migration đã chạy

Thay đổi versioned migration hoặc changeset đã triển khai làm checksum validation thất bại hoặc khiến môi trường khác nhau. Tạo migration mới để sửa.

### 20.4. Chạy cả Flyway và Liquibase trên cùng schema

Hai công cụ có lịch sử riêng và có thể cạnh tranh thay đổi cấu trúc. Chọn một migration authority cho schema.

### 20.5. Dùng schema.sql/data.sql song song với migration tool

Các script có thể chạy sai thứ tự hoặc tạo thay đổi ngoài lịch sử migration. Dùng migration tool làm quy trình tạo schema và dữ liệu nhất quán.

### 20.6. Migration chỉ thay đổi schema mà quên dữ liệu cũ

Thêm cột NOT NULL hoặc đổi kiểu có thể thất bại với dữ liệu hiện có. Tách bước add nullable, backfill, validate dữ liệu rồi enforce constraint.

### 20.7. Dùng một DDL cho mọi database

Identity, sequence, index, ALTER COLUMN và online DDL có khác biệt theo vendor. Viết migration theo database mục tiêu hoặc cung cấp migration riêng khi cần.

### 20.8. Dựa vào H2 để xác nhận production migration

H2 có thể chấp nhận cú pháp hoặc kiểu dữ liệu khác database thật. Chạy migration integration test với database engine mục tiêu.

### 20.9. Baseline không kiểm tra schema thực tế

Baseline sai có thể đánh dấu một database chưa đúng cấu trúc như đã ở phiên bản mong muốn. So sánh schema và dữ liệu trước khi baseline.

### 20.10. Cho rằng rollback luôn phục hồi được dữ liệu

Drop column hoặc update phá hủy dữ liệu có thể không đảo ngược. Lập kế hoạch backup, forward-fix và kiểm tra restore trước khi deploy.

## 21. Quy trình lựa chọn công cụ

Khi thiết kế schema cho ứng dụng Spring Data JPA:

1. Dùng entity mapping để mô tả cấu trúc object-relational.
2. Chọn JPA/Hibernate schema generation cho prototype, database tạm hoặc xuất DDL ban đầu.
3. Với schema dùng chung và production, chọn một migration tool làm nguồn quản lý lịch sử.
4. Chọn Flyway nếu muốn migration SQL/version rõ ràng; chọn Liquibase nếu cần changelog có cấu trúc, preconditions, contexts/labels hoặc rollback metadata.
5. Lưu migration trong version control và không sửa migration đã áp dụng.
6. Đặt Hibernate ddl-auto=validate hoặc none khi migration tool sở hữu schema.
7. Viết data migration và rollout tương thích khi thay đổi cấu trúc có dữ liệu hiện hữu.
8. Chạy migration và integration test trên database tương đương production.
9. Baseline database cũ sau khi kiểm kê và đối chiếu trạng thái thực tế.
10. Backup, giám sát và chuẩn bị forward-fix cho migration production.

## 22. Ghi nhớ

- Entity mapping mô tả cách Java ánh xạ tới database; nó không tự thay thế migration history.
- Hibernate ddl-auto có các lựa chọn none, validate, update, create và create-drop.
- create/create-drop phù hợp với database tạm; không dùng để triển khai production có dữ liệu cần giữ.
- update tiện cho phát triển nhưng không phải công cụ quản lý schema evolution có version.
- validate kiểm tra mapping với schema hiện tại, không tạo hoặc sửa database và không kiểm tra mọi đối tượng database.
- Jakarta Persistence có các schema-generation properties để tạo DDL trực tiếp hoặc xuất script.
- Flyway quản lý versioned và repeatable migrations, lưu lịch sử/checksum trong flyway_schema_history.
- Liquibase quản lý changelog/changeset, định danh bằng id, author và path; lưu lịch sử/checksum trong DATABASECHANGELOG.
- Không sửa migration/changeset đã áp dụng; tạo migration mới để sửa.
- Chọn một công cụ duy nhất làm migration authority; tránh trộn Hibernate update, Flyway, Liquibase và schema.sql/data.sql trên cùng schema.
- Dùng ddl-auto=validate để kiểm tra mapping sau khi migration đã chạy.
- Data migration cần backfill, batch và rollout tương thích; với ứng dụng chạy nhiều phiên bản, dùng expand-and-contract.
- DDL có thể gây lock hoặc không transactional; kiểm thử theo database vendor.
- CI cần chạy migration trên database thật hoặc Testcontainers tương đương production.
- Backup, restore và forward-fix là một phần của kế hoạch triển khai schema.

JPA/Hibernate schema generation giúp dựng hoặc kiểm tra cấu trúc từ entity mapping. Flyway và Liquibase quản lý sự thay đổi của schema và dữ liệu theo lịch sử có thể review, kiểm chứng và triển khai lặp lại. Khi database trở thành tài sản dùng chung giữa nhiều phiên bản ứng dụng và môi trường, migration có version là nền tảng để triển khai an toàn.

## Tài liệu tham khảo

- [Spring Boot — SQL Databases and JPA Schema Creation](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization and Migration Tools](https://docs.spring.io/spring-boot/4.2-SNAPSHOT/how-to/data-initialization.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Redgate Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Redgate Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Redgate Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Liquibase — Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html)
- [Liquibase — Preconditions](https://docs.liquibase.com/community/user-guide-5-0-2/what-are-preconditions)
- [Liquibase — Changeset Checksums](https://docs.liquibase.com/community/user-guide-5-0-3/what-is-a-changeset-checksum)