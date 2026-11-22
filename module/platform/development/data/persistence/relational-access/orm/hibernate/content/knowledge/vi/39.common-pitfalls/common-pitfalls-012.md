# Dùng hbm2ddl update làm toàn bộ quy trình chuyển đổi dữ liệu

## 1. Vì sao hbm2ddl update không phải migration strategy?

Hibernate có thể đọc entity mappings rồi tạo hoặc điều chỉnh một phần cấu trúc database. Vì vậy, khi một developer thêm field vào entity và thấy cột mới xuất hiện sau khi ứng dụng khởi động, rất dễ nghĩ rằng `hibernate.hbm2ddl.auto=update` đã giải quyết việc nâng cấp database.

Ví dụ:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String name;

    private String loyaltyLevel;
}
~~~

Nếu schema cũ chưa có `loyalty_level`, Hibernate có thể phát hiện khác biệt và yêu cầu database thêm cột tương ứng. Nhưng thay đổi schema mới chỉ là một phần của một lần nâng cấp dữ liệu.

Giả sử business yêu cầu:
- Thêm `loyalty_level`.
- Gán giá trị `STANDARD` cho mọi customer hiện tại.
- Chuẩn hóa các giá trị cũ.
- Bảo đảm cột không còn NULL.
- Tạo index phục vụ truy vấn.
- Chuyển ứng dụng sang đọc và ghi field mới.
- Xóa cột cũ sau khi tất cả instances đã chuyển đổi.

Một thao tác schema update không biết đầy đủ ý nghĩa nghiệp vụ của các bước này. Nó không thể tự suy ra cách chuyển dữ liệu cũ sang mô hình mới, kiểm tra chất lượng dữ liệu, phối hợp nhiều phiên bản ứng dụng hoặc lên kế hoạch rollback.

**Schema evolution và data migration là hai công việc liên quan nhưng khác nhau.** Hibernate schema generation hỗ trợ tạo/điều chỉnh schema theo mapping trong một số tình huống; migration tool và quy trình phát hành chịu trách nhiệm chuyển đổi schema lẫn dữ liệu có kiểm soát.

Bài học thuộc chương **Lỗi thường gặp** trong module *Data Persistence Relational Access ORM Hibernate*. Trọng tâm là hiểu vì sao dùng `hbm2ddl update` làm toàn bộ quy trình chuyển đổi dữ liệu tạo rủi ro, và cách thay thế bằng migrations có version, có thể kiểm tra và vận hành an toàn.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt schema generation, schema validation và data migration.
2. Hiểu phạm vi của `hibernate.hbm2ddl.auto=update` / `spring.jpa.hibernate.ddl-auto=update`.
3. Nhận diện các thay đổi mà Hibernate không thể suy luận an toàn từ entity mappings.
4. Thiết kế migrations cho rename, backfill, type conversion, constraints, indexes và cleanup.
5. Dùng Flyway hoặc Liquibase làm source of truth cho schema evolution.
6. Tránh nhiều application instances cùng thay đổi schema khi khởi động.
7. Áp dụng expand-and-contract cho deployment nhiều phiên bản và zero-downtime.
8. Kiểm thử migration trên database thật, quản lý rollback/recovery và quyền DDL.
9. Xác định khi nào `validate`, `none` và schema generation phù hợp.

## 2. Ba khái niệm cần tách biệt

### 2.1. Schema generation

Schema generation là việc ORM tạo DDL dựa trên mapping metadata.

Ví dụ mapping:

~~~java
@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(nullable = false, length = 30)
    private String status;
}
~~~

Hibernate có thể suy ra cấu trúc tương tự:

~~~sql
CREATE TABLE orders (
    id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    PRIMARY KEY (id)
);
~~~

DDL thực tế phụ thuộc dialect, identifier strategy, naming strategy, annotations, type mappings và database.

Schema generation phù hợp với:
- Prototype hoặc ứng dụng nhỏ chưa có dữ liệu quan trọng.
- Schema dùng tạm trong integration tests.
- Tạo schema ban đầu có kiểm soát.
- Một số workflow development/local.

Nó không tự tạo ra một lịch sử migration có version và không biết cách chuyển dữ liệu business.

### 2.2. Schema validation

Validation kiểm tra mapping có tương thích với schema hiện tại ở mức Hibernate hỗ trợ hay không.

Trong Spring Boot:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Nếu entity mong đợi một column hoặc type mà schema không đáp ứng, application startup có thể fail. Đây là tín hiệu hữu ích để phát hiện migration chưa chạy hoặc mapping/schema bị lệch.

Nhưng `validate` không chứng minh:
- Mọi index và predicate có đúng.
- Trigger/function có tồn tại và hoạt động.
- Dữ liệu cũ đã được backfill.
- Constraint nghiệp vụ đã enforce đúng.
- Collation/permissions/partitioning đúng.
- Query plan đạt yêu cầu.
- Migration có thể rollback.

Validation là một lớp kiểm tra, không phải migration engine.

### 2.3. Data migration

Data migration là chuyển schema và/hoặc dữ liệu từ trạng thái cũ sang trạng thái mới theo một kế hoạch có version.

Ví dụ đổi một field `full_name` thành `given_name` và `family_name`:
- Thêm hai cột mới.
- Tách dữ liệu hiện có theo quy tắc nghiệp vụ.
- Xử lý tên không thể tách chắc chắn.
- Chuyển code đọc/ghi.
- Xác minh dữ liệu.
- Sau thời gian tương thích, xóa cột cũ.

Một migration cần mô tả **đích đến, cách chuyển dữ liệu, điều kiện thành công và cách phục hồi**. ORM mapping đơn lẻ không thể biểu đạt đầy đủ những quyết định đó.

### 2.4. So sánh nhanh

| Công việc | Mục đích | Công cụ/phương pháp |
|---|---|---|
| Schema generation | Tạo DDL từ mapping | Hibernate schema tooling |
| Schema validation | Kiểm tra mapping/schema tương thích | Hibernate `validate`, startup checks |
| Schema migration | Thay đổi cấu trúc có version | Flyway/Liquibase/SQL migration |
| Data migration | Chuyển đổi dữ liệu hiện có | SQL, migration code, batch job có kiểm soát |
| Deployment compatibility | Giữ nhiều app versions cùng hoạt động trong lúc chuyển đổi | Expand-and-contract |
| Data verification | Chứng minh chuyển đổi đạt yêu cầu | Counts, constraints, checksums, reconciliation |

## 3. hbm2ddl.auto và ddl-auto có nghĩa gì?

Hibernate sử dụng thuộc tính `hibernate.hbm2ddl.auto`. Spring Boot cung cấp property `spring.jpa.hibernate.ddl-auto` để cấu hình hành vi schema management của Hibernate.

Ví dụ:

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

Một số giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát | Cách sử dụng thường thấy |
|---|---|---|
| `none` | Không yêu cầu Hibernate quản lý schema | Production khi migration tool sở hữu DDL |
| `validate` | Kiểm tra schema so với mapping | Production/staging sau migrations |
| `update` | Cố gắng điều chỉnh schema hiện có theo mappings | Development/prototype có kiểm soát |
| `create` | Tạo schema mới, có thể loại bỏ schema objects hiện có theo lifecycle | Test/dev dữ liệu có thể xóa |
| `create-drop` | Tạo schema khi khởi động và drop khi SessionFactory đóng | Test/dev ephemeral |

Chi tiết và default phụ thuộc Hibernate version, JPA bootstrap mode và Spring Boot configuration. Không dựa vào default ngầm định; cấu hình rõ theo môi trường.

### 3.1. `update` cố gắng làm gì?

Ở mức khái quát, Hibernate:
1. Đọc mapping metadata.
2. Lấy thông tin schema hiện tại qua JDBC/database metadata.
3. So sánh một phần cấu trúc cần thiết.
4. Tạo DDL để bổ sung/điều chỉnh những đối tượng mà schema tooling hỗ trợ.
5. Gửi DDL tới database theo dialect.

Đây không phải một migration plan được author theo nghiệp vụ. Hibernate không có đủ thông tin để hiểu một column cũ đại diện cho business concept nào, cách chuyển các giá trị đã lưu, hoặc thứ tự deployment cần thiết.

### 3.2. `update` không phải một lịch sử thay đổi

Hibernate schema update không cung cấp:
- Migration version được commit vào repository.
- Người viết và mục đích từng thay đổi.
- Một tập SQL reviewable trước khi chạy.
- Checksum để phát hiện migration bị sửa.
- Quy trình chạy một lần và ghi nhận đã chạy.
- Lịch sử ai/phiên bản nào đã áp dụng migration.
- Rollback/compensation plan.
- Backfill progress và retry strategy.
- Coordination giữa nhiều application instances.
- Precondition/postcondition nghiệp vụ.

Một lần startup thành công chỉ nói rằng schema tooling đã hoàn tất thao tác mà nó thực hiện; không chứng minh toàn bộ data transition đã hoàn thành.

### 3.3. DDL khác nhau giữa database

Cùng một entity mapping có thể sinh DDL khác nhau:
- PostgreSQL dùng `BIGSERIAL`, identity hoặc sequence tùy mapping/version.
- MySQL dùng `AUTO_INCREMENT`.
- SQL Server dùng `IDENTITY`.
- Oracle dùng identity/sequence theo version và dialect.
- Kiểu boolean, timestamp, JSON, enum và generated columns có semantics khác nhau.

Hibernate Dialect giúp tạo SQL phù hợp cho provider/database, nhưng không thay thế việc DBA/developer thiết kế migration đặc thù. Một DDL được tạo tự động vẫn cần được đánh giá trong context database thật.

## 4. Vì sao Hibernate không thể tự chuyển đổi dữ liệu?

Mapping cho biết ứng dụng muốn đọc/ghi state dưới dạng nào. Mapping không chứa đầy đủ quy tắc chuyển đổi business data từ schema cũ.

### 4.1. Thêm column không đồng nghĩa có dữ liệu đúng

Entity cũ:

~~~java
@Entity
class Customer {
    @Id
    Long id;

    String name;
}
~~~

Entity mới:

~~~java
@Entity
class Customer {
    @Id
    Long id;

    String name;

    String status;
}
~~~

Schema update có thể thêm `status`. Nhưng 5 triệu rows hiện tại sẽ có giá trị NULL nếu không có database default hoặc một migration backfill.

Ứng dụng mới có thể:
- Ném lỗi khi code giả định status luôn có giá trị.
- Trả kết quả sai khi filter `status = 'ACTIVE'`.
- Không thể thêm NOT NULL constraint.
- Tạo dữ liệu inconsistent nếu chỉ một số code paths set field mới.

Hibernate không biết giá trị mặc định nào đúng cho từng customer.

### 4.2. Rename column không thể suy ra an toàn từ tên Java

Mapping cũ:

~~~java
@Column(name = "customer_name")
private String name;
~~~

Mapping mới:

~~~java
@Column(name = "display_name")
private String displayName;
~~~

Hibernate có thể nhìn thấy `customer_name` không còn được mapping và `display_name` chưa tồn tại. Nếu schema tooling tạo column mới, dữ liệu ở `customer_name` vẫn nằm nguyên đó.

Hai column có thể cùng tồn tại:
- `customer_name` chứa dữ liệu lịch sử.
- `display_name` rỗng.
- Ứng dụng mới chỉ đọc `display_name`.
- Người dùng nhìn thấy dữ liệu như bị mất.

Rename là một thao tác **giữ lại và chuyển dữ liệu**, cần migration tường minh.

### 4.3. Một field có thể được tách thành nhiều fields

Ví dụ từ `address`:

~~~text
"12 Nguyen Hue, District 1, Ho Chi Minh City"
~~~

sang:
- `street`
- `district`
- `city`

Hibernate không biết delimiter, cách xử lý địa chỉ thiếu thành phần, viết tắt, dữ liệu lỗi hoặc địa chỉ nước ngoài. Cần parser/business rules, review dữ liệu không thể tự động chuyển và có thể cần manual remediation.

### 4.4. Một field có thể được gộp thành một field

Từ `first_name`, `last_name` sang `display_name` cũng cần quy tắc:
- Tên đệm nằm ở đâu?
- Có giữ whitespace không?
- Người dùng có tên một phần không?
- Có locale/script khác nhau không?
- Dữ liệu đã được user chỉnh sửa ở cột mới chưa?

DDL không thể trả lời các câu hỏi này.

### 4.5. Thay đổi semantics không phải chỉ đổi SQL type

Đổi `status VARCHAR(20)` thành enum hoặc đổi `amount` từ floating point sang decimal có thể cần:
- Map các legacy values.
- Làm tròn/scale theo quy tắc tài chính.
- Chọn behavior cho unknown enum values.
- Kiểm tra giá trị ngoài miền.
- Xử lý NULL.
- Kiểm tra độ dài overflow.
- Duy trì compatibility với old application instances.

Schema tooling không thể tự quyết định những quy tắc đó.

## 5. Các tình huống update dễ gây hỏng hoặc mất dữ liệu

### 5.1. Rename field/column

Nếu mapping mới đổi column name, Hibernate có thể tạo column mới nhưng không tự hiểu đó là rename cần copy dữ liệu. Cột cũ có thể còn tồn tại, chứa dữ liệu không còn được application đọc.

Migration cần thực hiện thao tác rename phù hợp DB hoặc add-copy-verify-drop theo deployment strategy.

### 5.2. Drop column

Một field bị xóa khỏi entity không có nghĩa dữ liệu trong column cũ được phép xóa. Nó có thể:
- Còn được dùng bởi ứng dụng version cũ.
- Được báo cáo/ETL đọc.
- Được trigger hoặc view tham chiếu.
- Cần retention/audit.
- Là nguồn cho backfill sau này.

Không giả định `update` sẽ dọn tất cả objects không còn mapping, và cũng không dùng sự không dọn đó như một chiến lược retention.

### 5.3. Đổi type hoặc độ dài

Ví dụ:
- `VARCHAR(255)` thành `VARCHAR(80)`.
- `BIGINT` thành `INTEGER`.
- `TIMESTAMP` thành `DATE`.
- `DOUBLE` thành `DECIMAL(19,2)`.

Các thay đổi này có thể:
- Cần cast/rewrite toàn bảng.
- Bị từ chối nếu dữ liệu vượt giới hạn.
- Làm mất precision/time information.
- Thay đổi query/index behavior.
- Khóa table lâu.
- Tốn transaction log/disk.

Không để schema update tự quyết định chuyển đổi type cho dữ liệu quan trọng.

### 5.4. Thêm NOT NULL

Entity:

~~~java
@Column(nullable = false)
private String status;
~~~

Nếu database đã có rows với `status IS NULL`, thêm NOT NULL có thể fail. Nếu một DDL tool thêm default, default đó có thể không đúng cho mọi row hoặc không phù hợp với app versions đang chạy.

Một quy trình an toàn thường:
1. Thêm nullable column.
2. Deploy code có thể đọc cả state cũ/mới.
3. Backfill dữ liệu.
4. Verify không còn NULL/invalid rows.
5. Enforce NOT NULL bằng migration riêng.

### 5.5. Thêm UNIQUE constraint

Mapping:

~~~java
@Column(unique = true)
private String externalCode;
~~~

Nếu dữ liệu cũ đã có duplicates, unique constraint creation fail. Nếu business key cần normalize hoặc scope theo tenant, annotation đơn giản còn có thể mô tả sai uniqueness rule.

Cần:
- Xác định duplicate rows.
- Chọn owner hợp lệ.
- Remediate dữ liệu.
- Tạo index/constraint theo database.
- Kiểm thử concurrency.
- Map constraint violations trong application.

### 5.6. Foreign key và relationship changes

Thêm `@ManyToOne`/`@JoinColumn` có thể dẫn đến column/FK DDL, nhưng không tự tìm ra:
- Giá trị FK cho rows cũ.
- Cách xử lý orphan records.
- Cách merge duplicate parent records.
- Referential actions phù hợp.
- Có nên validate toàn bộ dữ liệu ngay lập tức hay dùng staged constraint.

Các quyết định này cần migration và data cleanup.

### 5.7. Index và performance

Entity mapping có thể mô tả một số indexes/unique constraints, nhưng việc thêm index trên bảng lớn cần cân nhắc:
- DDL locking.
- Online/concurrent index build support.
- Disk/temporary space.
- Replication lag.
- Write amplification.
- Query workload.
- Rollback/drop cost.

Một lần startup application không nên bất ngờ tạo index nặng trên production traffic. Dùng migration có chủ đích, có thời gian chạy và monitoring.

### 5.8. Sequence, identity và generated columns

Thay identifier strategy hoặc generated columns có thể ảnh hưởng:
- Existing sequence values.
- Identity values và next generated key.
- Default expressions.
- Trigger-generated IDs.
- Hibernate identifier generator expectations.
- Multi-writer/replication behavior.

Phải đồng bộ database object state với Hibernate mapping; không giả định schema update tự reconcile mọi generator metadata.

### 5.9. Naming strategy và mapping refactor

Đổi implicit naming strategy, entity/property names hoặc table naming có thể khiến Hibernate nhận diện column/table khác với schema cũ. Một refactor Java tưởng như rename nội bộ có thể làm DDL generator tạo object mới.

Với production schema, nên map tên table/column tường minh hoặc kiểm soát naming strategy và migrations trong version control.
+
## 6. Vì sao chạy update lúc application startup nguy hiểm?

### 10.1. Nhiều instances có thể cùng sửa schema

Một production deployment thường có nhiều replicas. Nếu mỗi instance đều khởi động Hibernate với schema update:
- Instance A đọc schema metadata.
- Instance B cũng đọc schema metadata gần cùng lúc.
- Cả hai cùng quyết định cần tạo column/index.
- DDL có thể đụng nhau hoặc một instance fail.
- Startup readiness có thể không nhất quán.
- Một instance có thể phục vụ traffic trong khi instance khác đang thay đổi schema.

Kết quả phụ thuộc database DDL semantics, locking và cách schema tool phát hiện object. Không nên coi Hibernate schema update là distributed migration coordinator.

### 10.2. DDL có thể commit khác DML

Nhiều database có implicit commit hoặc giới hạn transaction đối với một số DDL operations. Ví dụ behavior của `ALTER TABLE`, index creation và constraint changes khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle.

Không thể giả định:
- Một migration gồm 5 câu DDL luôn rollback nguyên tử.
- DDL chạy trong cùng transaction với backfill DML.
- Application startup thất bại thì schema tự trở về trạng thái cũ.
- Database lock sẽ được giải phóng ngay khi app process bị kill.

Phải đọc transaction/DDL behavior của database mục tiêu và thiết kế recovery phù hợp.

### 10.3. Schema update có thể làm startup thành điểm nghẽn

Trên schema lớn, metadata inspection hoặc DDL operation có thể kéo dài. Nếu mọi replica đều thực hiện:
- Rolling deployment mất thời gian.
- Readiness probes fail.
- Autoscaler tạo thêm instances khiến nhiều schema checks lặp.
- DDL locks ảnh hưởng traffic.
- Một migration dài làm deploy timeout.

Migration nên chạy trong một stage có chủ đích, trước khi application instances mới nhận traffic.

### 10.4. Migration tool cũng cần lifecycle rõ

Flyway/Liquibase giúp version và tracking migration, nhưng việc chạy migration từ mọi application instance cũng cần được cân nhắc. Nhiều deployment chọn:
1. Một migration job/step chạy trước.
2. Job báo success/failure rõ.
3. Application deployment chỉ bắt đầu khi migration hoàn tất.
4. App startup dùng `validate` hoặc `none`.

Spring Boot có thể auto-run migration khi application context khởi động. Điều đó tiện cho app nhỏ, nhưng với production nhiều replicas hoặc migration dài, tách migration thành deployment job thường dễ kiểm soát hơn.

### 10.5. Migration lock không thay thế deployment planning

Migration tools có cơ chế quản lý lịch sử và concurrency/locking theo tool/database. Nhưng chúng không giải quyết:
- Old app có tương thích schema mới không.
- Hai migrations khác nhau có được deploy cùng lúc không.
- Data backfill có an toàn khi app tiếp tục ghi không.
- DDL lock có gây outage không.
- Rollback application có còn tương thích schema không.

Cần một orchestration/deployment plan bao quanh migration tool.
+
## 7. Quyền database: application runtime không nên tự có toàn quyền DDL

### 11.1. Tách quyền migration và quyền ứng dụng

Một thiết kế an toàn thường có:
- **Migration principal:** được quyền tạo/sửa table, index, sequence, constraint theo migration policy.
- **Application principal:** chỉ có quyền cần thiết để SELECT/INSERT/UPDATE/DELETE trên schema đã tạo.

Ví dụ PostgreSQL ở mức khái niệm:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO app_runtime;
~~~

Role migration được cấp quyền DDL phù hợp riêng theo ownership/CREATE/ALTER policy của database. Câu lệnh quyền cụ thể phụ thuộc owner, schema, sequences, functions và database policy. Ví dụ chỉ minh họa separation of duties.

### 11.2. Vì sao tách quyền?

Nếu application account có DDL quyền rộng:
- Lỗi cấu hình hoặc compromised application có thể thay schema.
- `ddl-auto=update` có thể vô tình chạy ở production.
- Application instance nào cũng có khả năng thay đổi cấu trúc dữ liệu.
- Khó audit ai thực hiện schema change và từ release nào.

Một migration job riêng có thể dùng credential tạm thời/secret scope hẹp rồi kết thúc sau khi migration thành công.

### 11.3. Schema drift phải được phát hiện, không tự sửa ngầm

Nếu application startup phát hiện mapping khác schema:
- `validate` có thể fail và buộc deployment xử lý.
- Migration pipeline phải áp đúng version.
- DBA/manual change cần được phản ánh lại vào migration history/source control.
- Không tự bật `update` để làm mất dấu drift.

Schema drift là tín hiệu cần điều tra: migration bị thiếu, hotfix không được ghi lại, môi trường sai version hoặc mapping đã đổi ngoài quy trình.

## 8. Cấu hình Hibernate/Spring Boot cho production

### 12.1. Dùng migration tool, sau đó validate

Ví dụ Spring Boot:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Flyway chịu trách nhiệm schema changes; Hibernate kiểm tra mapping/schema ở mức hỗ trợ khi application khởi động.

Nếu project dùng Liquibase:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.liquibase.enabled=true
~~~

Chỉ bật migration tool thực sự được sử dụng. Không bật cả Flyway và Liquibase để cùng quản lý một schema nếu không có kiến trúc ownership rõ.

### 12.2. Khi nào dùng none?

Có thể dùng:

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

khi migration/DBA pipeline là nguồn schema authority và team không muốn Hibernate thực hiện schema validation ở startup. Khi đó cần một schema compatibility check khác trong deployment pipeline.

`none` không có nghĩa schema đúng; nó chỉ có nghĩa Hibernate không tự quản lý schema qua property đó.

### 12.3. Tách profile development và production

Ví dụ cấu hình minh họa:

`application-dev.properties`:

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

`application-prod.properties`:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Đây chỉ là ví dụ profile. Với dự án có dữ liệu local quan trọng, development cũng nên dùng migrations để tránh drift. `update` có thể tiện cho prototype, nhưng không nên trở thành cách tạo schema duy nhất của team.

### 12.4. Không để default phụ thuộc embedded database

Spring Boot có thể chọn default `ddl-auto` khác nhau tùy embedded DB và cách datasource được cấu hình. Đặt explicit property theo profile để tránh:
- Test vô tình create-drop.
- Production vô tình dùng một behavior khác dự kiến.
- Developer local có schema tự sinh không khớp migrations.

### 12.5. Hibernate validation không thay thế migration verification

`validate` không bảo đảm mọi database objects. Migration pipeline vẫn cần:
- Xác nhận schema version.
- Kiểm tra required indexes/constraints.
- Kiểm tra backfill completeness.
- Kiểm tra permissions.
- Chạy repository/integration tests.
- Theo dõi query plan sau thay đổi lớn.
+
## 9. Dùng migration tool làm source of truth

Migration tool quản lý các thay đổi database như những artifacts có version, được lưu trong source control và áp dụng theo thứ tự.

Hai lựa chọn phổ biến:
- **Flyway:** migration thường là SQL scripts hoặc Java migrations, được áp dụng theo version và ghi nhận trong schema history table.
- **Liquibase:** changesets có thể viết bằng XML, YAML, JSON hoặc SQL; theo dõi bằng changelog metadata.

Cả hai đều giúp team biết database đang ở version nào và những thay đổi nào đã được áp dụng. Tool không tự quyết định business transformation; developer vẫn phải viết migration đúng.

### 6.1. Ví dụ cấu trúc Flyway

~~~text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__add_loyalty_level.sql
  V3__backfill_loyalty_level.sql
  V4__require_loyalty_level.sql
~~~

Migration file được version hóa. Khi ứng dụng khởi động hoặc pipeline chạy migration command, Flyway so sánh migration files với schema history table, rồi chạy các version chưa được áp dụng theo quy tắc của Flyway.

Một migration đã được áp dụng ở shared environment không nên sửa nội dung tại chỗ. Nếu cần thay đổi kết quả, tạo migration mới để lịch sử vẫn có thể giải thích và tái lập.

### 6.2. Thêm column bằng migration

`V2__add_loyalty_level.sql`:

~~~sql
ALTER TABLE customers
ADD COLUMN loyalty_level VARCHAR(20);
~~~

Để column nullable trước giúp old rows và old application code tiếp tục hoạt động trong giai đoạn đầu. Bước này chỉ thay schema, chưa backfill.

### 6.3. Backfill dữ liệu

`V3__backfill_loyalty_level.sql`:

~~~sql
UPDATE customers
SET loyalty_level = 'STANDARD'
WHERE loyalty_level IS NULL;
~~~

Đây là ví dụ đơn giản khi cùng một giá trị mặc định đúng cho mọi customer. Thực tế có thể cần mapping từ field cũ, join bảng khác hoặc business rules phức tạp hơn.

Trên bảng lớn, một UPDATE toàn bảng có thể:
- Giữ locks và transaction lâu.
- Tạo lượng lớn WAL/transaction log.
- Tăng replication lag.
- Tạo dead tuples/bloat hoặc undo pressure.
- Tăng disk usage.
- Ảnh hưởng latency của ứng dụng.

Khi đó nên dùng batch backfill có giới hạn theo primary key, checkpoint/progress, retry và metric thay vì một transaction khổng lồ.

### 6.4. Enforce constraint sau khi backfill

Sau khi kiểm tra dữ liệu không còn NULL:

~~~sql
ALTER TABLE customers
ALTER COLUMN loyalty_level SET NOT NULL;
~~~

Cú pháp trên dành cho PostgreSQL. MySQL/SQL Server/Oracle có syntax và locking behavior khác. Migration phải được viết cho dialect/database mục tiêu và thử trên version production.

### 6.5. Thêm index trong migration

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX ix_customers_loyalty_level
ON customers (loyalty_level);
~~~

Trên bảng lớn, PostgreSQL có thể hỗ trợ `CREATE INDEX CONCURRENTLY` để giảm thời gian chặn writes, nhưng câu lệnh này có giới hạn transaction và không thể chạy trong transaction block thông thường. Flyway migration chứa lệnh này cần cấu hình transaction phù hợp theo version/tool; Liquibase cũng cần cách thực thi tương ứng.

Không áp dụng `CONCURRENTLY` một cách máy móc cho database khác; mỗi engine có online index build syntax/limitations riêng.

## 10. Ví dụ một lần đổi tên column có bảo toàn dữ liệu

Giả sử schema cũ có `customers.customer_name`. Mô hình mới muốn dùng `display_name`.

### 7.1. Cách đổi trực tiếp

Với hệ thống nhỏ có downtime và không có app version cũ chạy đồng thời, một migration có thể rename column theo DB:

~~~sql
ALTER TABLE customers
RENAME COLUMN customer_name TO display_name;
~~~

Cú pháp trên là ví dụ PostgreSQL. Sau đó entity mapping đổi sang:

~~~java
@Column(name = "display_name")
private String displayName;
~~~

Cách này giữ dữ liệu nhưng old application version có thể không chạy được sau rename. Nó chỉ an toàn khi deployment/maintenance window đảm bảo không còn consumer cần tên cũ.

### 7.2. Expand-and-contract cho deployment nhiều phiên bản

Với ứng dụng cần hoạt động trong lúc deploy, thực hiện nhiều bước:

**Expand**
1. Thêm column mới `display_name`, giữ column cũ.
2. Deploy application version tương thích cả hai columns.
3. Dual-write hoặc ghi theo chiến lược đồng bộ được thiết kế.
4. Backfill dữ liệu cũ sang column mới.
5. Verify dữ liệu hai cột nhất quán.

**Switch**
6. Chuyển reads sang `display_name`.
7. Theo dõi lỗi và so sánh dữ liệu.
8. Chờ toàn bộ old instances, jobs, ETL và consumers ngừng đọc/ghi cột cũ.

**Contract**
9. Ngừng dual-write.
10. Xóa column `customer_name` bằng migration riêng khi đã xác nhận không còn dependency.

Sơ đồ:

~~~text
Schema v1:
  customer_name
       |
       | add nullable display_name
       v
Expanded schema:
  customer_name + display_name
       |
       | compatible app dual-write
       | backfill + verify
       v
Switch reads to display_name
       |
       | old app/jobs no longer depend on customer_name
       v
Contract schema:
  display_name only
~~~

### 7.3. Tại sao phải giữ compatibility giữa các bước?

Trong rolling deployment có thể đồng thời tồn tại:
- Instance A chạy application version cũ.
- Instance B chạy version mới.
- Worker background chưa restart.
- Scheduled job đang dùng query cũ.
- Consumer ETL/BI đọc schema trực tiếp.

Nếu migration drop/rename column ngay lúc version mới khởi động, old instance có thể lỗi. Expand-and-contract tạo một khoảng tương thích để các thành phần chuyển đổi dần.

### 7.4. Dual-write có rủi ro riêng

Khi ghi cả old/new columns:
- Hai giá trị có thể lệch nếu chỉ một code path cập nhật.
- Một write có thể thành công một phần nếu dùng hai systems không cùng transaction.
- Background jobs có thể chỉ ghi cột cũ.
- Trigger đồng bộ có thể gây recursion hoặc write amplification.
- Concurrent updates cần một nguồn sự thật và quy tắc conflict.

Hãy chọn một chiến lược đồng bộ rõ ràng. Có thể dùng application dual-write trong cùng DB transaction, database trigger được kiểm thử, hoặc outbox/CDC cho hệ phân tán. Không để hai columns trở thành hai nguồn dữ liệu độc lập.

## 11. Backfill lớn: không nên mặc định chạy một UPDATE khổng lồ

### 8.1. Khi nào SQL backfill đơn giản là đủ?

Một migration SQL một lần có thể phù hợp nếu:
- Bảng nhỏ.
- Thời gian lock/transaction thấp.
- Dữ liệu có quy tắc chuyển đổi đơn giản.
- Có maintenance window.
- Database có đủ disk/log capacity.
- Có thể chạy lại an toàn hoặc xác định rõ failure handling.

Ví dụ:

~~~sql
UPDATE customers
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

### 8.2. Batch backfill theo key range

Với bảng lớn, có thể xử lý theo từng chunk. Ví dụ PostgreSQL dùng CTE để giới hạn batch:

~~~sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE loyalty_level IS NULL
    ORDER BY id
    LIMIT 1000
)
UPDATE customers c
SET loyalty_level = 'STANDARD'
FROM batch
WHERE c.id = batch.id;
~~~

Chạy lặp đến khi không còn rows phù hợp. Cách điều phối vòng lặp có thể là migration runner riêng hoặc operational job, tùy lượng dữ liệu và thời gian cần thiết.

Cần:
- Checkpoint hoặc xác định progress bằng query.
- Giới hạn batch size và commit boundary.
- Retry có giới hạn.
- Metrics về rows processed/failed/duration.
- Idempotent predicate để chạy lại không ghi đè dữ liệu đã được user cập nhật.
- Throttle để bảo vệ primary database.
- Quy tắc dừng/tiếp tục khi latency hoặc replication lag tăng.

### 8.3. Tránh ghi đè dữ liệu mới

Giả sử application đã bắt đầu ghi `loyalty_level` cho customer mới. Backfill không nên ghi đè giá trị đã có:

~~~sql
UPDATE customers
SET loyalty_level = 'STANDARD'
WHERE loyalty_level IS NULL;
~~~

Predicate `IS NULL` giúp ví dụ chỉ điền các rows chưa có giá trị. Nếu backfill phải derive từ old column, hãy thêm điều kiện kiểm tra version/timestamp hoặc source state phù hợp để không overwrite concurrent user updates.

### 8.4. Tách schema migration và data backfill khi cần

Một cách tổ chức:
- Flyway/Liquibase thêm column và các cấu trúc nhỏ.
- Một batch job riêng backfill hàng triệu rows.
- Job ghi checkpoint/progress.
- Verification query chứng minh hoàn tất.
- Migration tiếp theo enforce constraint/drop old column.

Không cần ép một migration transaction duy nhất xử lý hàng tỷ rows. Migration history có thể ghi nhận schema steps; job state có thể có bảng tracking riêng.

### 8.5. Idempotency và retry

Một backfill tốt có thể chạy lại mà không làm hỏng dữ liệu:
- Chỉ xử lý rows chưa chuyển.
- Ghi progress theo stable key.
- Không tạo duplicate side effects.
- Có thể resume sau process crash.
- Dùng transaction boundaries có giới hạn.
- Phát hiện rows không thể chuyển và đưa vào error/review queue.

Nếu một bước không idempotent, phải lưu state đủ để biết bước nào đã hoàn tất trước khi retry.

## 12. Liquibase changesets và preconditions

Liquibase mô tả migration dưới dạng changesets. Ví dụ XML đơn giản:

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.27.xsd">

    <changeSet id="2026-01-add-loyalty-level" author="team">
        <addColumn tableName="customers">
            <column name="loyalty_level" type="varchar(20)"/>
        </addColumn>
    </changeSet>

    <changeSet id="2026-02-backfill-loyalty-level" author="team">
        <sql>
            UPDATE customers
            SET loyalty_level = 'STANDARD'
            WHERE loyalty_level IS NULL
        </sql>
    </changeSet>
</databaseChangeLog>
~~~

Đây là ví dụ minh họa; schema location, Liquibase version, DB support và syntax cần phù hợp dependency thực tế.

### 9.1. Preconditions

Liquibase preconditions có thể kiểm tra:
- Table/column tồn tại.
- DBMS đúng.
- Một query trả về kết quả mong muốn.
- Migration chỉ chạy khi schema/data ở trạng thái đã dự kiến.

Preconditions giúp phát hiện môi trường lệch trước khi thực hiện changeset. Chúng không thay thế việc kiểm tra data quality hoặc thiết kế rollback.

### 9.2. Checksum và lịch sử changeset

Liquibase lưu changeset metadata/checksum. Nếu sửa một changeset đã được áp dụng, checksum mismatch có thể được báo khi chạy update. Flyway cũng theo dõi version/checksum cho versioned migrations.

Đây là lợi ích quan trọng so với để ORM tự so sánh mapping mỗi lần startup: migration history ghi lại **các bước thay đổi đã thực hiện**, không chỉ schema trông như thế nào tại thời điểm hiện tại.

### 9.3. Rollback không tự động có nghĩa phục hồi dữ liệu

Một số changesets có thể rollback tự động; SQL/data transformations phức tạp thường cần rollback script hoặc compensating migration được thiết kế riêng.

Ví dụ, sau khi tách `full_name` thành `given_name`/`family_name`, xóa dữ liệu cũ rồi mới phát hiện parser sai có thể không khôi phục được nguyên bản. Giữ source column hoặc backup/retention trong giai đoạn chuyển đổi có thể cần thiết.
+
## 13. Quy trình phát hành schema an toàn

Một release có thay đổi database nên đi theo chuỗi có thể review:

~~~text
Developer changes entity + migration
                 |
                 v
Review SQL / data transformation / compatibility
                 |
                 v
Test on clean target DB version
                 |
                 v
Test upgrade from previous schema + representative data
                 |
                 v
Backup / recovery readiness
                 |
                 v
Run migration job once
                 |
                 v
Verify schema + data postconditions
                 |
                 v
Deploy compatible application version
                 |
                 v
Observe errors, locks, latency, replication
                 |
                 v
Contract old schema only after all consumers switch
~~~

### 13.1. Review migration như review code

Reviewer nên hiểu:
- Migration thay đổi objects nào?
- Có drop/truncate/rewrite dữ liệu không?
- Có thể chạy lâu/lock table không?
- Có phụ thuộc DB version hoặc extension không?
- Có thể retry không?
- Có rollback/compensation không?
- App version cũ/mới có cùng hoạt động không?
- Có precondition/postcondition nào?
- Có cần maintenance window hoặc online DDL không?

SQL migration là production code. Nó cần review, tests và operational plan.

### 13.2. Kiểm thử từ nhiều starting states

Chạy migration ít nhất trên:
- Database trống, áp tất cả migrations.
- Snapshot schema version trước migration.
- Dataset có NULL/duplicates/edge cases.
- Dataset đại diện về volume nếu DDL/backfill nặng.
- Schema đã có hotfix/manual drift nếu môi trường từng xảy ra.

Test chỉ từ database trống không chứng minh migration upgrade từ production data cũ hoạt động.

### 13.3. Precondition và postcondition

Ví dụ precondition:
- Không còn duplicate active emails trước khi tạo unique index.
- Tất cả source values thuộc domain đã biết.
- Column cũ tồn tại.
- Migration version trước đã được áp dụng.

Ví dụ postcondition:
- Không còn NULL trong field bắt buộc.
- Không có orphan foreign keys.
- Tất cả rows đã có normalized key.
- Index/constraint tồn tại.
- Count rows trước/sau phù hợp với transformation.

Có thể thực hiện bằng SQL assertions trong pipeline hoặc một verification job riêng.

### 13.4. Backup không thay thế migration test

Backup giúp phục hồi khi migration gây sự cố, nhưng restore có thể tốn thời gian và làm mất writes phát sinh sau snapshot. Trước migration rủi ro cao:
- Kiểm tra backup gần nhất.
- Thử restore trong môi trường phù hợp.
- Biết recovery point/recovery time objectives.
- Chuẩn bị plan nếu rollback không khả thi.
- Cân nhắc forward-fix hoặc compensating migration.

## 14. Rollback, forward-fix và migration history

### 14.1. Không phải migration nào cũng có rollback đơn giản

Ví dụ:
- Add nullable column: có thể drop nếu chưa có app phụ thuộc và dữ liệu mới chưa cần giữ.
- Rename column: có thể rename ngược nếu không có writes mới gây conflict.
- Backfill: rollback chỉ an toàn nếu giữ được old values và biết row nào đã chuyển.
- Delete old column: dữ liệu đã mất nếu không backup/copy.
- Merge records: thường không thể tự tách lại chính xác.
- Type conversion có rounding: thông tin precision có thể đã mất.

Vì vậy, rollback cần được thiết kế cùng migration chứ không thể suy ra sau sự cố.

### 14.2. Forward-fix

Trong production, một số lỗi được sửa bằng migration mới:
- Migration V12 tạo column đúng nhưng backfill sai một subset.
- V13 sửa dữ liệu theo source-of-truth.
- V14 thêm constraint sau khi verify.

Forward-fix giữ lịch sử migration append-only và tránh giả vờ rằng migration đã chạy chưa từng tồn tại.

### 14.3. Không sửa migration đã áp dụng

Flyway versioned migrations và Liquibase changesets có checksum/history. Sửa file đã chạy có thể:
- Làm checksum mismatch.
- Làm môi trường mới và cũ diverge.
- Khiến người khác không tái lập được schema production.
- Phá audit trail.

Tạo migration mới. Các lệnh `repair` hoặc checksum override của tool chỉ dùng theo hướng dẫn vận hành cụ thể, không phải cách che lỗi migration file bị sửa.

### 14.4. Rollback application khác rollback database

Nếu application version mới deploy thất bại:
- Có thể rollback app về version cũ.
- Schema mới phải còn tương thích với version cũ.
- Nếu migration đã drop/rename column cũ, app rollback có thể không chạy.
- Data writes từ version mới có thể không biểu diễn được trong schema/app cũ.

Expand-and-contract giữ backward compatibility trong giai đoạn deploy để app rollback dễ hơn. Destructive contract step nên được phát hành sau khi rollback window đã qua và có quyết định riêng.

## 15. Multi-tenant và nhiều schema/database

Một ứng dụng Hibernate có thể dùng:
- Một database, tenant discriminator column.
- Một schema per tenant.
- Một database per tenant.
- Nhiều database theo region/customer.

Không thể mặc định migration một schema là đủ.

Cần xác định:
- Migration chạy trên bao nhiêu tenant schemas/databases?
- Tenant mới được tạo có nhận schema version mới nhất không?
- Một tenant migration fail thì xử lý thế nào?
- Có giới hạn concurrency để không overload DB không?
- Schema history table nằm ở đâu?
- Có tenant nào offline lâu và schema tụt version không?
- Application có route tenant tới schema chưa được nâng cấp không?

Một migration orchestration service/job có thể cần track tenant-level status, retry, rate limit và báo cáo progress. Hibernate `update` khi tenant đầu tiên khởi động không phải cơ chế rollout schema toàn fleet.

## 16. Kiểm thử migrations bằng database thật

### 16.1. Testcontainers với DB production engine

Nếu production dùng PostgreSQL, test migration trên PostgreSQL container cùng major/version tương ứng. Nếu dùng MySQL, dùng MySQL container phù hợp.

Mục tiêu:
- Kiểm tra cú pháp DDL thực tế.
- Kiểm tra NULL/collation/index semantics.
- Kiểm tra lock/transaction behavior ở mức cần thiết.
- Chạy Flyway/Liquibase migrations từ schema trống.
- Nâng từ schema version trước với fixture dữ liệu cũ.
- Assert dữ liệu sau backfill.

### 16.2. Test từ database trống

Một test migration pipeline:
1. Khởi tạo container database sạch.
2. Chạy toàn bộ migrations từ đầu.
3. Kiểm tra migration history.
4. Khởi động Hibernate với `ddl-auto=validate`.
5. Chạy repository smoke tests.
6. Kiểm tra constraints/indexes quan trọng.

Điều này chứng minh một environment mới có thể được dựng lại từ source-controlled migrations.

### 16.3. Test upgrade từ schema cũ

Tạo schema version N với fixture thể hiện dữ liệu thực tế:
- Rows có NULL.
- Legacy enum values.
- Duplicates.
- Boundary values.
- Orphan references nếu lịch sử có thể có.
- Large strings/numeric ranges.
- Timestamps/timezones.

Sau đó áp migrations N+1..latest và kiểm tra:
- Rows có được giữ lại không?
- Values có được chuyển đúng không?
- Invalid rows được xử lý/ghi nhận không?
- Constraints có thể enforce không?
- App mappings có hoạt động không?

### 16.4. Test idempotency và retry

Versioned migrations thường được tool ghi nhận chỉ chạy một lần; không phải mọi script đều nên chạy lại tùy tiện. Tuy nhiên batch backfill/operational jobs cần retry-safe.

Test:
- Chạy batch lần đầu.
- Kill/giả lập lỗi giữa chừng.
- Resume.
- Chạy lại sau khi hoàn tất.
- Xác nhận không overwrite data mới hoặc tạo duplicate side effects.

### 16.5. Test DDL concurrency khi cần

Nếu production có online migration hoặc migration coordination, dùng DB thật và nhiều connections để xác minh:
- DDL lock behavior.
- Query/write đang chạy ảnh hưởng migration ra sao.
- Migration job có độc quyền/schema lock đúng không.
- Application startup trong thời gian migration có fail/serve không.
- Timeout/retry semantics.

Không nên dùng unit tests mock `JdbcTemplate` để tuyên bố DDL concurrency an toàn.
+
## 17. Những hiểu lầm thường gặp

### 17.1. “Application start thành công nghĩa là database đã migrate đúng”

Không đúng. Hibernate update có thể hoàn tất các DDL mà nó nhận diện, nhưng không biết business backfill, data validation, rename semantics, compatibility với old instances hoặc postconditions. Một application context khởi động thành công không phải bằng chứng dữ liệu đã chuyển đúng.

### 17.2. “Hibernate thấy field mới thì tự điền giá trị cho rows cũ”

Mapping không chứa quy tắc backfill. Column mới có thể NULL hoặc có default ở database, nhưng default đó phải được thiết kế và áp dụng rõ ràng. Giá trị đúng có thể phụ thuộc trạng thái customer/order, lịch sử giao dịch hoặc bảng liên quan.

### 17.3. “Xóa field khỏi entity sẽ xóa column cũ”

Không dựa vào assumption này. Schema update không phải công cụ dọn dẹp database objects một cách đầy đủ và an toàn. Ngay cả khi một tool có thể drop object trong một mode nào đó, việc drop column production phải là quyết định migration riêng vì dữ liệu và consumers có thể còn phụ thuộc.

### 17.4. “@Column(nullable=false) sẽ backfill NULL trước khi thêm constraint”

Annotation mô tả mapping/DDL expectation. Nó không cung cấp business value cho từng row cũ. Migration phải điền dữ liệu và verify trước khi enforce NOT NULL.

### 17.5. “Đã thêm @Index là index production được tạo an toàn”

Mapping annotation có thể mô tả index cho schema generation, nhưng việc đó không mô tả đủ online build strategy, lock budget, concurrent index creation, progress monitoring hoặc rollback. Index lớn cần migration chuyên biệt.

### 17.6. “Chạy update ở mỗi instance giúp database luôn đồng bộ”

Nhiều instances có thể cùng kiểm tra/chạy DDL và không có một versioned migration sequence được review. Schema drift nên được phát hiện qua migration history/validation, không nên tự sửa ngầm ở mọi startup.

### 17.7. “Dùng validate nghĩa là migration đã đúng”

Validation chỉ kiểm tra phần schema mapping mà Hibernate hỗ trợ. Nó không xác nhận dữ liệu backfill, partial index predicate, trigger, stored procedure, grants, partitioning hay performance. Cần postcondition tests và DB-specific assertions.

### 17.8. “Flyway/Liquibase tự làm mọi migration an toàn”

Migration tool quản lý execution/history. Người viết vẫn phải thiết kế:
- DDL có lock bao lâu.
- Data conversion có đúng không.
- Script có retry-safe không.
- Old/new application versions có tương thích không.
- Rollback/compensation như thế nào.
- Khi nào chạy backfill và verify.

Tool không thay thế database engineering.

## 18. Một mẫu cấu hình và workflow tham khảo

### 18.1. Dependency và cấu hình

Trong Spring Boot project, dùng dependency management của Boot hoặc BOM tương thích để quản lý Flyway/Liquibase và JDBC driver. Ví dụ Flyway dependency ở Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Artifact starter cụ thể phụ thuộc Spring Boot version; ở một số version/module setup, dependency là flyway-core cùng database-specific module cần thiết. Dùng dependency catalog/BOM của dự án và docs đúng release train thay vì copy version tùy ý.

Production properties:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Nếu migration được chạy bởi deployment job độc lập và app chỉ cần kết nối schema đã chuẩn bị:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=false
~~~

Chỉ disable auto-run trong application nếu pipeline có stage migration chắc chắn đã chạy trước. Nếu không, application startup sẽ fail validation hoặc query runtime có thể fail vì schema thiếu.

### 18.2. Tách migration job khỏi runtime application

Một pipeline có thể tổ chức:

~~~text
Build application artifact
       |
       v
Build/test migration bundle
       |
       v
Start ephemeral target database
       |
       v
Apply migrations + verify
       |
       v
Test application against migrated schema
       |
       v
Deploy migration job to target environment
       |
       v
Wait for migration success
       |
       v
Deploy application replicas
~~~

Tách migration job giúp:
- Chạy đúng một lần theo deployment orchestration.
- Dùng credential DDL riêng.
- Có logs và exit status độc lập.
- Không làm mọi replica cùng chạy schema changes.
- Cho phép migration hoàn tất trước readiness của app.

### 18.3. Khi application startup tự chạy Flyway vẫn hợp lý?

Với ứng dụng nhỏ, một instance duy nhất, migrations ngắn và database DDL behavior đã được kiểm chứng, auto-run khi startup có thể đơn giản và phù hợp.

Khi hệ thống có nhiều replicas, migrations nặng, tenant fleet hoặc zero-downtime requirements, migration job độc lập thường dễ điều phối hơn. Đây là quyết định deployment architecture, không phải quy tắc tuyệt đối cho mọi ứng dụng.

### 18.4. Kiểm tra schema version khi app khởi động

Có thể kiểm tra migration history table hoặc dùng health/deployment check phù hợp để xác nhận schema version đáp ứng application version. Đừng chỉ kiểm tra một column tồn tại; app release có thể yêu cầu nhiều migrations và data backfill đã hoàn tất.

Nếu app version yêu cầu schema version tối thiểu N:
- Deployment pipeline bảo đảm migration N đã thành công.
- Startup validation kiểm tra mappings.
- Health/readiness không nhận traffic khi schema incompatible.
- Operational dashboard ghi nhận current migration version.

## 19. Troubleshooting khi dùng hbm2ddl update

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Field mới có column nhưng giá trị NULL | Schema update chỉ thêm column | Viết backfill migration và verify |
| Đổi tên Java field nhưng dữ liệu cũ biến mất khỏi UI | Column mới được tạo, old column còn dữ liệu | Rename/copy migration; kiểm tra old/new mapping |
| App mới fail vì NOT NULL | Rows cũ còn NULL | Add nullable, backfill, verify, enforce constraint |
| Tạo unique index thất bại | Existing duplicates hoặc key semantics sai | Remediate duplicates, xác định normalized/tenant key |
| Startup một replica thành công, replica khác fail | Concurrent DDL/startup race hoặc timing | Chạy migration một lần trước app rollout |
| Production startup bị treo | DDL lock, metadata inspection hoặc table rewrite | Kiểm tra DB locks/DDL duration; migration job và online DDL |
| Schema local khác production | Mỗi môi trường chạy update từ mappings khác nhau | Dùng versioned migrations và schema history |
| Field bị xóa nhưng column còn tồn tại | Update không phải cleanup migration | Viết migration drop sau khi xác nhận consumers |
| Column cũ bị drop thủ công, app version cũ lỗi | Contract trước khi hết old consumers | Expand-and-contract, giữ compatibility |
| Backfill chạy quá lâu | UPDATE toàn bảng/transaction lớn | Batch theo key, throttle, checkpoint |
| Migration fail giữa DDL steps | Database DDL transaction semantics | Kiểm tra trạng thái thật, recovery/forward-fix |
| Flyway checksum mismatch | Migration đã áp dụng bị sửa | Khôi phục file gốc hoặc tạo migration mới; dùng repair theo runbook |
| Liquibase checksum mismatch | Changeset đã chạy bị thay đổi | Tạo changeset mới; chỉ clear/override theo policy |
| Hibernate validate pass nhưng query vẫn lỗi | Validation không bao phủ mọi DB objects/data | Test constraints, indexes, functions và postconditions |
| Hibernate validate fail sau migration | Mapping/schema chưa đồng bộ hoặc migration thiếu | So sánh column/type/nullability, migration history |
| Index build ảnh hưởng traffic | DDL locking/online build chưa phù hợp | Dùng DB-specific online strategy, lịch chạy và monitoring |
| Old app rollback không chạy | Migration đã contract/drop column cần thiết | Giữ schema backward-compatible qua rollback window |
| Tenant này chạy, tenant khác lỗi | Tenant schema/version/data khác nhau | Track migration per tenant và retry có kiểm soát |
| App runtime không thể tạo sequence/table | Runtime account thiếu DDL privileges | Tách migration principal và application principal |
| Hibernate tự tạo schema trong test | ddl-auto create/update hoặc embedded DB default | Cấu hình rõ test profile và chạy migrations |
| Migration pass H2 nhưng fail PostgreSQL | Dialect/DDL semantics khác | Testcontainers với production DB engine |
| Migration job pass nhưng app lỗi | Backfill/postcondition hoặc mapping chưa được test | Chạy app smoke tests trên schema đã migrate |
| Startup pass nhưng data sai | Không có business data verification | Reconciliation queries và data quality assertions |

## 20. Bài tập thực hành

### Bài 1 — Thêm column

Entity mới thêm status, Hibernate update tạo column.

**Hỏi:** Các rows cũ có tự nhận giá trị ACTIVE không?

**Đáp án:** Không. Cần default/backfill được thiết kế rõ; mapping không tự biết business value cho từng row.

### Bài 2 — Rename field

Đổi customer_name thành display_name.

**Hỏi:** Vì sao chỉ đổi property/column name không đủ?

**Đáp án:** Database có thể tạo column mới trong khi dữ liệu vẫn ở column cũ. Cần rename hoặc add-copy-verify migration.

### Bài 3 — Thêm NOT NULL

Bảng có 1 triệu rows, column mới đang NULL.

**Hỏi:** Có thể enforce NOT NULL ngay không?

**Đáp án:** Không trước khi backfill và xác nhận không còn NULL. Dùng các bước expand, backfill, verify, contract.

### Bài 4 — Unique constraint

Một email xuất hiện ở ba rows lịch sử, trong đó hai rows active.

**Hỏi:** Thêm unique index có thành công không?

**Đáp án:** Không nếu index bao gồm cả hai active duplicate. Cần remediation và xác định uniqueness predicate/scope.

### Bài 5 — Xóa field

Entity bỏ property legacyCode.

**Hỏi:** Có nên dựa vào hbm2ddl update để drop column không?

**Đáp án:** Không. Drop column cần migration riêng sau khi xác nhận old app, ETL, reports và audit không còn phụ thuộc.

### Bài 6 — Type narrowing

Column VARCHAR(255) đổi thành VARCHAR(80).

**Hỏi:** Rủi ro chính?

**Đáp án:** Rows có giá trị dài hơn 80 có thể khiến DDL fail hoặc bị truncate tùy DB/operation. Phải đo dữ liệu, remediation và test migration.

### Bài 7 — Backfill default

Mọi customer mới có loyalty level STANDARD nhưng customers VIP phải giữ VIP.

**Hỏi:** Một UPDATE đặt toàn bộ rows thành STANDARD có đúng không?

**Đáp án:** Không. Backfill phải dựa vào business state/source-of-truth; chỉ điền rows chưa có giá trị hoặc map theo điều kiện.

### Bài 8 — Startup nhiều replicas

Deployment có 8 application instances cùng bật update.

**Hỏi:** Vì sao nguy hiểm?

**Đáp án:** Nhiều instances có thể cùng inspect và phát DDL, tạo race/lock/startup inconsistency. Chạy migration job có điều phối trước khi rollout.

### Bài 9 — DDL rollback

Migration đã chạy ALTER TABLE rồi lỗi ở câu tiếp theo.

**Hỏi:** Database chắc chắn rollback toàn bộ không?

**Đáp án:** Không. DDL transaction semantics phụ thuộc engine/statement. Kiểm tra trạng thái thực và recovery plan.

### Bài 10 — Flyway checksum

Một developer sửa file versioned migration đã áp dụng ở staging.

**Hỏi:** Có nên sửa trực tiếp để production dùng file mới?

**Đáp án:** Không. Tạo migration mới để giữ lịch sử và checksum integrity; xử lý mismatch theo runbook.

### Bài 11 — Liquibase changeset

Một changeset đã chạy bị thay đổi nội dung.

**Hỏi:** Tại sao checksum mismatch hữu ích?

**Đáp án:** Nó cảnh báo lịch sử migration không còn khớp source-controlled changeset; không nên che cảnh báo bằng clear-checksums tùy tiện.

### Bài 12 — Hibernate validate

Application khởi động với ddl-auto=validate.

**Hỏi:** Có chứng minh backfill hoàn tất không?

**Đáp án:** Không. Validation chủ yếu kiểm tra mapping/schema; cần data postcondition query riêng.

### Bài 13 — none

Application dùng ddl-auto=none.

**Hỏi:** Có nghĩa schema chắc chắn đúng không?

**Đáp án:** Không. Hibernate không kiểm tra/tạo schema qua property này; deployment pipeline phải có migration và validation khác.

### Bài 14 — Backfill bảng lớn

Một UPDATE dự kiến sửa 200 triệu rows.

**Hỏi:** Nên cân nhắc gì?

**Đáp án:** Batch size, transaction boundaries, WAL/undo, locks, replication lag, throttling, checkpoints, retries và monitoring.

### Bài 15 — Dual-write

App mới ghi cả old/new columns.

**Hỏi:** Rủi ro?

**Đáp án:** Hai columns có thể lệch nếu một path bỏ sót hoặc concurrent writes xung đột. Cần một nguồn sự thật, atomicity và verification.

### Bài 16 — Contract migration

Đã deploy app mới nhưng còn background worker cũ.

**Hỏi:** Có thể drop old column chưa?

**Đáp án:** Chưa. Phải xác nhận mọi consumers/jobs/ETL đã chuyển và rollback window phù hợp.

### Bài 17 — Migration quyền DDL

App runtime user không có quyền CREATE TABLE.

**Hỏi:** Có nên cấp DDL quyền rộng cho mọi replica?

**Đáp án:** Không nhất thiết. Tách migration principal/job có quyền DDL và application principal chỉ có quyền runtime cần thiết.

### Bài 18 — Migration Testcontainers

Migration tạo PostgreSQL partial index.

**Hỏi:** H2 test có đủ chứng minh không?

**Đáp án:** Không. Chạy migration trên PostgreSQL container cùng version mục tiêu và assert behavior của index.

### Bài 19 — Test database trống

Tất cả migrations chạy thành công trên DB mới.

**Hỏi:** Đã đủ chứng minh upgrade production không?

**Đáp án:** Chưa. Cần test từ schema version cũ với dữ liệu đại diện, edge cases và volume phù hợp.

### Bài 20 — Rollback app

Migration thêm column nullable và app mới dual-write, nhưng deploy lỗi.

**Hỏi:** Có thể rollback app cũ không?

**Đáp án:** Có thể nếu schema mới vẫn tương thích old app và new writes không tạo state old app không hiểu. Đây là lý do expand-and-contract.

### Bài 21 — Multi-tenant

Có 500 tenant schemas, một tenant offline lâu.

**Hỏi:** Một migration chạy trên tenant đầu tiên có bảo đảm tất cả tenant sẵn sàng không?

**Đáp án:** Không. Cần migration orchestration và trạng thái/version theo tenant, retry và policy cho tenant offline.

### Bài 22 — Index lớn

Thêm index làm production write latency tăng.

**Hỏi:** Vì sao không nên để Hibernate update tự tạo index lúc startup?

**Đáp án:** Index build có thể lock/consume I/O và ảnh hưởng writes. Cần DB-specific online strategy, lịch chạy và monitoring.

### Bài 23 — Backfill retry

Job chết sau 70% dữ liệu.

**Hỏi:** Làm sao resume an toàn?

**Đáp án:** Checkpoint stable key, predicate idempotent, batch commits, metrics và không overwrite values đã được user/application cập nhật.

### Bài 24 — Mapping và schema drift

DBA hotfix column trực tiếp trên production nhưng không có migration file.

**Hỏi:** Team nên làm gì?

**Đáp án:** Ghi nhận drift, đối chiếu schema, tạo migration history tương thích với trạng thái đã áp dụng và kiểm tra các environment khác. Không để update âm thầm che sự khác biệt.

## 21. Checklist trước khi thay đổi schema

Trước khi phát hành một thay đổi entity/database, hãy xác nhận:

1. Đây là schema-only change hay còn cần data transformation?
2. Có thể mô tả migration bằng một versioned, reviewable script không?
3. Có rename/drop/type conversion mà Hibernate không thể suy ra không?
4. Existing rows có NULL, duplicates, invalid values hoặc orphan references không?
5. Có cần backfill theo batch/checkpoint không?
6. Migration có idempotent/retry-safe ở các bước vận hành không?
7. DDL có thể lock/rewrite table hoặc tăng replication lag không?
8. Database production/version có hỗ trợ syntax/online DDL tương ứng không?
9. App version cũ và mới có thể cùng hoạt động trong rolling deployment không?
10. Có expand-and-contract và thời điểm contract rõ ràng không?
11. Migration chạy một lần bởi job hay tự động trong mọi app startup?
12. Migration principal và application principal có được tách quyền không?
13. Có preconditions/postconditions và data verification không?
14. Có test từ database trống và schema/data version cũ không?
15. Test có chạy trên DB engine thật bằng Testcontainers khi cần không?
16. Rollback/forward-fix và backup/restore plan đã rõ chưa?
17. Migration file đã áp dụng có bị sửa không?
18. Schema history và tenant/database version có được theo dõi không?
19. Production app dùng validate hoặc none theo policy rõ ràng không?
20. Deployment có chờ migration hoàn tất trước khi đưa app version mới vào traffic không?

## 22. Tổng kết

### 22.1. Điều hbm2ddl update có thể và không thể làm

| Việc | Hibernate update có thể hỗ trợ? | Cần migration/business plan? |
|---|---|---|
| Thêm một column đơn giản | Có thể | Có, nếu rows cũ cần giá trị |
| Tạo một số schema objects theo mapping | Có thể, tùy dialect/version | Cần review trên DB thật |
| Rename column có giữ dữ liệu | Không thể suy luận an toàn | Có |
| Backfill hàng triệu rows theo business rules | Không | Có |
| Merge/split/normalize values | Không | Có |
| Remediate duplicates trước UNIQUE | Không | Có |
| Thay đổi online index strategy | Không đủ để điều phối | Có |
| Rolling deployment tương thích old/new apps | Không | Có |
| Version/checksum/audit migration history | Không | Có |
| Verify dữ liệu chuyển đổi | Không | Có |
| Phối hợp migration cho nhiều tenants | Không | Có |

### 22.2. Năm nguyên tắc cần nhớ

1. **Hibernate mapping mô tả trạng thái mong muốn của entity; migration mô tả cách database và dữ liệu đi từ trạng thái cũ sang mới.**
2. update không biết business semantics của rename, split/merge, defaults, data cleanup hay backfill.
3. Dùng Flyway/Liquibase và migrations versioned làm source of truth cho schema changes.
4. Với rolling deployment, dùng expand-and-contract để old/new application versions cùng hoạt động trong thời gian chuyển đổi.
5. Production nên cấu hình Hibernate validate hoặc none theo deployment policy; không để mọi app instance tự sửa schema bằng update.

### 22.3. Quy trình ghi nhớ

~~~text
Entity mapping thay đổi
        |
        v
Xác định schema + data changes
        |
        v
Viết versioned migration
        |
        v
Test DB trống + dữ liệu phiên bản cũ
        |
        v
Expand schema tương thích
        |
        v
Backfill + verify
        |
        v
Deploy/switch application
        |
        v
Chờ mọi consumers chuyển đổi
        |
        v
Contract/drop old schema bằng migration riêng
        |
        v
Hibernate validate mapping
~~~

Một câu hỏi hữu ích trước khi bật schema update là:

> “Nếu database đã có hàng triệu rows và nhiều application instances đang chạy, Hibernate có đủ thông tin để thực hiện đúng thay đổi này mà không làm mất dữ liệu hoặc phá compatibility không?”

Với mọi thay đổi có dữ liệu nghiệp vụ, câu trả lời cần được chứng minh bằng migration và test, không dựa vào việc application startup thành công.

## Tài liệu chính thức

- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — schema generation, schema tooling và configuration.
- [Hibernate ORM Javadocs](https://docs.hibernate.org/orm/current/javadocs/) — APIs/configuration theo Hibernate version.
- [Hibernate SchemaTooling documentation](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html#schema-generation) — schema generation actions và tooling.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html) — datasource initialization, Hibernate DDL và migration tools.
- [Spring Boot — Data JPA](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data) — JPA/Hibernate configuration.
- [Flyway Documentation](https://documentation.red-gate.com/fd) — versioned migrations, schema history, validation và repair.
- [Flyway SQL Migration](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/sql-based-migrations) — tổ chức SQL migration files.
- [Liquibase Documentation](https://docs.liquibase.com/) — changesets, changelog, preconditions và rollback.
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — DDL behavior và lock notes.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index build và concurrent option.
- [MySQL ALTER TABLE](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html) — online DDL và algorithm/lock options.
- [Testcontainers for Java](https://java.testcontainers.org/) — database containers cho integration tests.

> Ví dụ SQL trong bài chủ yếu minh họa PostgreSQL; cú pháp, DDL transaction behavior, online index build, lock duration và type conversion khác nhau theo database engine/version. hbm2ddl.auto=update có phạm vi và khả năng thay đổi theo Hibernate release. Trước khi phát hành migration production, xác nhận trên đúng Hibernate, database, JDBC driver và deployment topology của hệ thống.
