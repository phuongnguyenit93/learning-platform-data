# Quản lý Cypher migration có phiên bản và lịch sử thực thi

Khi ứng dụng Spring Data Neo4j (SDN) phát triển, cấu trúc graph và dữ liệu thường phải thay đổi theo từng phiên bản: thêm constraint, tạo index, đổi tên property, chuẩn hóa dữ liệu hoặc chuyển đổi relationship. Nếu chỉ chạy các câu Cypher thủ công, rất khó biết môi trường nào đã được cập nhật, câu lệnh nào đã chạy và nội dung migration có bị sửa sau khi triển khai hay không.

Cypher migration giải quyết vấn đề đó bằng cách lưu các thay đổi database thành những script có phiên bản, quản lý trong source control và thực thi theo một thứ tự xác định. Một migration tool còn ghi nhận lịch sử đã áp dụng trong Neo4j, kiểm tra checksum của script và phát hiện môi trường lệch phiên bản.

Trong hệ sinh thái Neo4j, **Neo4j-Migrations** là một lựa chọn chuyên dụng cho công việc này. Công cụ sử dụng Neo4j Java Driver, hỗ trợ Cypher script, CLI, Maven plugin, Core API và Spring Boot starter. SDN tiếp tục đảm nhiệm mapping entity và truy cập dữ liệu trong ứng dụng; Neo4j-Migrations quản lý các thay đổi schema và data theo phiên bản.

## 1. Vì sao cần migration có phiên bản?

Giả sử ứng dụng quản lý `Person` và `Team`. Phiên bản đầu lưu tên người dùng trong property `name`. Sau đó hệ thống cần:

1. Bảo đảm mỗi người có `code` duy nhất.
2. Bổ sung `normalizedName` để tìm kiếm không phân biệt hoa thường.
3. Tạo index cho property mới.
4. Ghi lại cấu hình tìm kiếm dùng chung.

Nếu chạy thủ công, môi trường local có thể đã có index trong khi staging chưa có. Một thành viên có thể chạy script hai lần và tạo dữ liệu trùng; một người khác sửa script cũ khiến production không còn khớp với source code.

Migration có phiên bản tạo ra một lịch sử có thể kiểm tra:

```text
Database mới
    |
    v
V001 - Tạo constraint cho Person.code
    |
    v
V002 - Bổ sung và chuẩn hóa normalizedName
    |
    v
V003 - Tạo index cho normalizedName
    |
    v
R010 - Đồng bộ cấu hình tìm kiếm
```

Mỗi môi trường có thể được đưa tới cùng trạng thái bằng cách áp dụng những migration còn thiếu. Công cụ lưu thông tin các migration đã chạy để lần tiếp theo chỉ xử lý phần chưa áp dụng hoặc repeatable migration đã thay đổi.

## 2. Phân biệt trách nhiệm SDN và Neo4j-Migrations

SDN và migration tool làm hai công việc liên quan nhưng khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `@Node`, `@Relationship`, entity mapping | Mô tả cách object Java tương ứng với node và relationship |
| `Neo4jRepository`, `Neo4jTemplate`, `Neo4jClient` | Đọc và ghi dữ liệu trong quá trình ứng dụng hoạt động |
| Neo4j-Migrations | Quản lý thay đổi schema và dữ liệu theo phiên bản, kiểm tra lịch sử thực thi |
| Neo4j constraints và indexes | Bảo vệ các quy tắc và tăng tốc truy vấn ở tầng database |

Ví dụ, đổi entity từ:

```java
@Node("Person")
public class Person {
    @Id
    private String code;

    private String name;
}
```

sang entity có thêm `normalizedName` không tự động bảo đảm property đó đã tồn tại hoặc được backfill cho mọi node cũ. Migration phải thực hiện thay đổi dữ liệu cần thiết. Sau khi migration được triển khai, entity mapping mới có thể đọc và ghi property đó.

Callback như `BeforeBindCallback` cũng không thay thế migration. Callback chạy trong entity lifecycle của ứng dụng; migration chạy để đưa database hiện tại sang một trạng thái schema/data mới.

## 3. Cấu trúc thư mục migration

Neo4j-Migrations mặc định tìm Cypher script trong `classpath:neo4j/migrations` khi dùng Core API, Spring Boot starter hoặc Maven plugin.

Trong một ứng dụng Spring Boot, có thể tổ chức như sau:

```text
src/main/resources/
└── neo4j/
    └── migrations/
        ├── V001__Create_person_constraints.cypher
        ├── V002__Add_normalized_name.cypher
        ├── V003__Create_person_name_index.cypher
        └── R010__Maintain_search_configuration.cypher
```

Các script được lưu cùng source code để mọi thay đổi đều có thể review qua Git. Không lưu script migration duy nhất trên máy cá nhân hoặc chỉ chạy trực tiếp trong Neo4j Browser mà không đưa vào source control.

## 4. Quy tắc đặt tên migration

Neo4j-Migrations nhận diện Cypher migration theo quy tắc:

```text
V1_2_3__Add_last_name_index.cypher
```

Tên file gồm các phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `V` | Versioned migration | `V` |
| `R` | Repeatable migration | `R` |
| Version | Mã phiên bản, có thể dùng dấu gạch dưới để chia phần | `001`, `1_2_3` |
| `__` | Dấu phân cách giữa version và mô tả | Hai dấu gạch dưới |
| Description | Mô tả ngắn nội dung thay đổi | `Create_person_constraints` |
| `.cypher` | Phần mở rộng của script | `.cypher` |

Ví dụ hợp lệ:

```text
V001__Create_person_constraints.cypher
V002__Add_normalized_name.cypher
V010__Create_relationship_indexes.cypher
R010__Maintain_search_configuration.cypher
```

Prefix `V` dùng cho thay đổi có phiên bản và chỉ áp dụng một lần theo chuỗi migration. Prefix `R` dùng cho thay đổi có thể áp dụng lại khi nội dung thay đổi, chẳng hạn đồng bộ cấu hình hoặc một cấu trúc được thiết kế idempotent.

Phiên bản mặc định được sắp xếp theo thứ tự từ điển (lexicographic) trong cấu hình Neo4j-Migrations hiện hành. Vì vậy, nên dùng số có padding như `V001`, `V002`, `V010`, `V100` thay vì trộn `V1`, `V10`, `V2`; cách đặt tên này giúp thứ tự dễ đọc và tránh bất ngờ khi so sánh chuỗi. Giữ một quy ước version xuyên suốt dự án.

## 5. Versioned migration: thay đổi đã áp dụng thì giữ nguyên

Versioned migration được xem là bất biến sau khi đã chạy thành công. Neo4j-Migrations tính checksum của script và ghi lại cùng lịch sử migration. Nếu nội dung một migration `V` đã áp dụng bị sửa, lần validate hoặc migrate tiếp theo có thể phát hiện checksum không khớp và báo lỗi.

Ví dụ `V001__Create_person_constraints.cypher`:

```cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

Sau khi migration này được áp dụng ở môi trường đầu tiên, không chỉnh sửa nội dung `V001` để thêm constraint khác. Tạo file mới:

```text
V004__Create_person_email_constraint.cypher
```

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Quy tắc này giữ cho lịch sử có ý nghĩa: `V001` luôn đại diện cho đúng thay đổi ban đầu, `V002` đại diện cho thay đổi tiếp theo. Một người mới checkout repository vẫn có thể dựng lại database bằng cùng chuỗi script.

`IF NOT EXISTS` giúp câu lệnh DDL an toàn hơn khi đối tượng đã tồn tại, nhưng không thay thế quản lý phiên bản và checksum. Nó cũng không có nghĩa mọi thay đổi định nghĩa index/constraint sẽ tự động được cập nhật chỉ vì tên đã tồn tại.

## 6. Repeatable migration: áp dụng lại khi checksum thay đổi

Repeatable migration dùng prefix `R`. Công cụ có thể chạy lại nó khi checksum của script khác với lần thực thi trước. Vì vậy, nội dung phải được thiết kế để chạy nhiều lần mà không tạo dữ liệu trùng hoặc gây thay đổi ngoài dự kiến.

Ví dụ `R010__Maintain_search_configuration.cypher`:

```cypher
MERGE (config:SearchConfiguration {key: 'person-search'})
SET config.fields = ['name', 'normalizedName'],
    config.minimumQueryLength = 2;
```

`MERGE` bảo đảm chỉ có một node cấu hình theo key đã chọn; `SET` đồng bộ các giá trị mong muốn. Nếu thêm `email` vào danh sách field và cập nhật script, checksum thay đổi và migration repeatable có thể được chạy lại để cập nhật cấu hình.

Không dùng repeatable migration cho thao tác cộng dồn không idempotent, ví dụ:

```cypher
MATCH (p:Person)
SET p.loginCount = p.loginCount + 1;
```

Nếu script trên được chạy lại, `loginCount` lại tăng thêm. Với một lần chuyển đổi dữ liệu cần chạy đúng một lần, dùng versioned migration `V`.

| Nhu cầu | Loại migration phù hợp |
|---|---|
| Thêm constraint mới | `V` |
| Backfill property một lần | `V` |
| Đổi cấu trúc relationship một lần | `V` |
| Đồng bộ cấu hình bằng `MERGE`/`SET` idempotent | `R` |
| Chạy lại script mỗi khi nội dung thay đổi và thao tác được thiết kế an toàn | `R` |

## 7. Ví dụ chuỗi migration cho Person

Giả sử hệ thống đã có các node `Person` với property `name`. Ta cần chuẩn hóa tên để phục vụ tìm kiếm.

### V001 — Tạo constraint

`V001__Create_person_constraints.cypher`:

Các ví dụ DDL trong bài sử dụng cú pháp Neo4j 5+. Nếu ứng dụng hỗ trợ nhiều phiên bản server, cần chọn cú pháp phù hợp hoặc dùng precondition và migration thay thế theo phiên bản.

```cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

Trước khi áp dụng constraint, cần kiểm tra dữ liệu cũ đã có `code` và không có giá trị trùng. Nếu dữ liệu không hợp lệ, migration có thể thất bại khi tạo constraint.

### V002 — Bổ sung property và backfill dữ liệu

`V002__Add_normalized_name.cypher`:

```cypher
MATCH (p:Person)
WHERE p.name IS NOT NULL
SET p.normalizedName = toLower(trim(p.name));
```

Đây là một lần chuyển đổi dữ liệu có phiên bản. Sau khi chạy, các node hiện tại có `normalizedName` được tính từ `name`.

Với graph rất lớn, không nên mặc định backfill toàn bộ dữ liệu trong một transaction kéo dài. Hãy đo lượng dữ liệu, thời gian ghi và lock contention ở môi trường thử nghiệm. Có thể chia công việc thành các migration theo giai đoạn hoặc một job backfill có checkpoint, batch size và cơ chế tiếp tục an toàn. Nếu dùng `CALL { ... } IN TRANSACTIONS`, phải kiểm tra transaction mode và cách công cụ thực thi vì cú pháp này cần transaction semantics phù hợp, không thể lồng tùy ý vào explicit transaction.

### V003 — Tạo index

`V003__Create_person_name_index.cypher`:

```cypher
CREATE INDEX person_normalized_name IF NOT EXISTS
FOR (p:Person)
ON (p.normalizedName);
```

Index nên được tạo sau khi property và dữ liệu đã được chuẩn bị theo kế hoạch. Ứng dụng có thể chuyển query tìm kiếm sang `normalizedName` sau khi migration hoàn tất và index ở trạng thái sẵn sàng.

### R010 — Đồng bộ cấu hình tìm kiếm

`R010__Maintain_search_configuration.cypher`:

```cypher
MERGE (config:SearchConfiguration {key: 'person-search'})
SET config.fields = ['name', 'normalizedName'],
    config.minimumQueryLength = 2;
```

Ví dụ này cho thấy `V` quản lý các thay đổi theo lịch sử một lần, còn `R` quản lý một cấu hình có thể đồng bộ lại khi định nghĩa thay đổi.

## 8. Migration có thể thay đổi cả schema và dữ liệu graph

Trong Neo4j, migration không chỉ tạo index hoặc constraint. Nó còn có thể thay đổi cấu trúc graph và chuyển đổi dữ liệu.

Ví dụ, chuyển property `departmentName` trên `Person` thành relationship tới node `Department`:

```cypher
MATCH (p:Person)
WHERE p.departmentName IS NOT NULL
MERGE (d:Department {name: p.departmentName})
MERGE (p)-[:WORKS_IN]->(d);
```

Đây là ví dụ chuyển đổi dữ liệu. Trước khi chạy trong production, cần xác định rõ:

- Có cho phép nhiều `Person` dùng chung một `Department` hay không.
- `Department.name` có cần unique constraint không.
- Dữ liệu có khoảng trắng, khác biệt chữ hoa/thường hoặc alias không.
- Property cũ được giữ lại trong giai đoạn chuyển tiếp hay xóa ngay.
- Ứng dụng phiên bản cũ có còn đọc `departmentName` không.

Không xóa property cũ ngay nếu còn instance ứng dụng đang đọc nó. Một quy trình expand-and-contract an toàn thường gồm:

1. Thêm cấu trúc mới và giữ cấu trúc cũ.
2. Backfill dữ liệu sang cấu trúc mới.
3. Triển khai ứng dụng đọc/ghi cấu trúc mới, có thể tạm thời hỗ trợ cả hai.
4. Kiểm tra dữ liệu và chuyển toàn bộ traffic sang cấu trúc mới.
5. Ở một migration sau, xóa property hoặc relationship cũ khi không còn consumer sử dụng.

## 9. Lịch sử migration được lưu như một subgraph

Neo4j-Migrations lưu lịch sử thực thi trong database dưới dạng một subgraph. Các node lịch sử mang label `__Neo4jMigration` và được nối với nhau bằng relationship `MIGRATED_TO`, tạo thành chuỗi các migration đã áp dụng.

```text
(:__Neo4jMigration { ... })
        -[:MIGRATED_TO {by: ...}]->
(:__Neo4jMigration { ... })
        -[:MIGRATED_TO {by: ...}]->
(:__Neo4jMigration { ... })
```

Thông tin migration được lưu cùng chuỗi lịch sử để công cụ so sánh với các script tìm thấy ở local. Thuộc tính `by` trên relationship có thể ghi lại người cài đặt thông qua cấu hình `org.neo4j.migrations.installed-by`.

Điểm quan trọng:

- Lịch sử được quản lý bởi Neo4j-Migrations, không phải một bảng SQL.
- Không tự ý sửa, xóa hoặc nối lại các node `__Neo4jMigration` bằng Cypher nghiệp vụ.
- Không xóa relationship `MIGRATED_TO` để ép công cụ chạy lại script.
- Dùng các lệnh `info`, `validate`, `repair`, `delete` hoặc `clean` đúng mục đích của công cụ.

Nếu quản lý nhiều database, lịch sử có thể được lưu trong schema database riêng. Khi dùng schema database tách biệt, node migration có thể mang thêm `migrationTarget` để phân biệt database đích. Tính năng schema database riêng yêu cầu Neo4j Enterprise theo điều kiện phiên bản được tài liệu công cụ quy định; database lưu lịch sử phải tồn tại và user cần quyền ghi.

## 10. Checksum giúp phát hiện migration bị sửa

Checksum là dấu kiểm tra được tính từ nội dung migration. Khi một versioned migration đã chạy, checksum được ghi vào lịch sử. Khi công cụ phát hiện cùng version nhưng nội dung local đã đổi, nó có thể từ chối tiếp tục vì lịch sử không còn khớp với script.

Ví dụ:

```text
Database đã ghi nhận:
V002__Add_normalized_name.cypher
checksum = A

Source code hiện tại:
V002__Add_normalized_name.cypher
checksum = B
```

Nếu `A` khác `B`, cần điều tra thay đổi. Có thể file đã bị chỉnh sửa nhầm, source code bị checkout sai commit hoặc một môi trường đã chạy migration từ phiên bản artifact khác.

Quy tắc làm việc:

1. Không chỉnh sửa migration `V` đã áp dụng ở bất kỳ môi trường dùng chung nào.
2. Tạo version mới để sửa logic hoặc bổ sung thay đổi.
3. Không xóa file migration cũ khỏi repository chỉ vì muốn làm gọn thư mục.
4. Review checksum mismatch như một lỗi phát hành cần điều tra, không tự động bỏ qua.

Với repeatable migration, checksum thay đổi là tín hiệu để áp dụng lại theo thiết kế của loại migration đó. Điều này không có nghĩa mọi migration versioned đều được phép sửa.

## 11. Thứ tự thực thi và migration out-of-order

Neo4j-Migrations áp dụng các migration theo thứ tự phiên bản. Mặc định, công cụ không cho phép thêm một migration có version cũ hơn vào sau khi database đã chạy qua các version mới hơn.

Ví dụ database đã chạy tới `V005`. Sau đó một nhánh feature được merge và bổ sung `V003`. Khi validate hoặc migrate, công cụ có thể báo chuỗi migration không hợp lệ vì version cũ xuất hiện sau version mới đã áp dụng.

Để tránh tình huống này:

- Dành vùng version cho từng nhánh hoặc phối hợp version trước khi merge.
- Đặt version mới sau version cuối cùng đã được phát hành.
- Validate migration chain trong CI trước khi triển khai.
- Không bật `out-of-order` chỉ để bỏ qua lỗi thứ tự.

Neo4j-Migrations có tùy chọn cho phép out-of-order, nhưng mặc định là tắt. Chỉ bật khi đã hiểu tác động của việc chèn migration vào chuỗi lịch sử và có quy trình kiểm soát rõ ràng.

## 12. Transaction khi chạy một Cypher migration

Theo mặc định, các statement trong một Cypher migration được chạy trong cùng một transaction (`PER_MIGRATION`). Nếu một thao tác thất bại, toàn bộ migration có thể rollback theo transaction scope đó.

Ví dụ script có hai statement:

```cypher
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;

CREATE INDEX person_name_index IF NOT EXISTS
FOR (p:Person)
ON (p.name);
```

Mặc định, công cụ thực thi cả script như một đơn vị transaction. Trong một số trường hợp DDL, ví dụ tạo database hoặc thao tác không thể kết hợp với DML trong cùng transaction, cần chọn `PER_STATEMENT` để mỗi statement có transaction scope riêng.

| Transaction mode | Hành vi |
|---|---|
| `PER_MIGRATION` | Tất cả statement trong một script nằm trong một transaction; mặc định và thường an toàn hơn cho migration thông thường |
| `PER_STATEMENT` | Mỗi statement chạy trong transaction riêng; phù hợp với một số DDL yêu cầu tách transaction |

Catalog-based migration có cơ chế transaction riêng do cách tạo index/constraint qua API chuyên biệt. Không giả định mọi loại migration đều có cùng transaction semantics.

Một script có nhiều statement được phân tách bằng dấu `;` theo quy tắc parser của công cụ, thông thường dấu chấm phẩy theo sau bởi newline. Hãy giữ định dạng script rõ ràng để tránh vô tình nối nhiều statement thành một câu lệnh.

## 13. Preconditions: assert và assume

Neo4j-Migrations hỗ trợ precondition trong Cypher script bằng comment một dòng. Có hai loại:

- `// assert ...`: điều kiện bắt buộc. Nếu không thỏa, migration bị dừng với lỗi.
- `// assume ...`: điều kiện mềm. Nếu không thỏa, script được bỏ qua và không được thêm vào migration chain.

Ví dụ assert phiên bản tối thiểu:

```cypher
// assert that version is ge 5.0
CREATE CONSTRAINT person_code_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.code IS UNIQUE;
```

Ví dụ giới hạn theo phiên bản Neo4j:

```cypher
// assume that version is ge 5.0
CREATE INDEX person_name_index IF NOT EXISTS
FOR (p:Person)
ON (p.name);
```

Precondition hữu ích khi một migration chỉ phù hợp với một phiên bản hoặc edition cụ thể. Nếu điều kiện có thể thay đổi theo thời gian, cần thiết kế các script thay thế cùng version và precondition loại trừ nhau theo hướng dẫn công cụ; nếu không, một migration đã áp dụng có thể bị thay thế bằng script khác và gây checksum mismatch.

## 14. Cấu hình Neo4j-Migrations trong Spring Boot

Neo4j-Migrations cung cấp Spring Boot starter sử dụng Neo4j Driver do Spring Boot quản lý. Starter tự động tìm migration trong `classpath:neo4j/migrations` và chạy các migration pending khi ứng dụng khởi động, nếu migration được bật.

Dependency Maven:

```xml
<dependency>
    <groupId>eu.michael-simons.neo4j</groupId>
    <artifactId>neo4j-migrations-spring-boot-starter</artifactId>
    <version>${neo4j-migrations.version}</version>
</dependency>
```

Chọn phiên bản starter tương thích với Spring Boot, Neo4j Java Driver và Neo4j server của dự án. Không tự lấy version mới nhất mà bỏ qua ma trận tương thích.

Ví dụ `application.yml`:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}

org:
  neo4j:
    migrations:
      enabled: true
      locations-to-scan:
        - classpath:neo4j/migrations
      validate-on-migrate: true
      installed-by: ${MIGRATION_ACTOR:application-deployment}
      transaction-mode: PER_MIGRATION
```

Các thuộc tính quan trọng:

| Property | Ý nghĩa |
|---|---|
| `org.neo4j.migrations.enabled` | Bật/tắt migration tự động |
| `org.neo4j.migrations.locations-to-scan` | Danh sách vị trí Cypher/XML migration |
| `org.neo4j.migrations.packages-to-scan` | Package chứa Java-based migration |
| `org.neo4j.migrations.validate-on-migrate` | Kiểm tra lịch sử trước khi áp dụng migration; mặc định bật |
| `org.neo4j.migrations.installed-by` | Người hoặc tiến trình được ghi vào lịch sử migration |
| `org.neo4j.migrations.transaction-mode` | `PER_MIGRATION` hoặc `PER_STATEMENT` |
| `org.neo4j.migrations.database` | Database đích cần migrate |
| `org.neo4j.migrations.schema-database` | Database lưu lịch sử migration nếu dùng cấu hình tách biệt |
| `org.neo4j.migrations.out-of-order` | Cho phép hoặc từ chối migration sai thứ tự |

Nếu muốn chạy migration từ một vị trí khác, cập nhật `locations-to-scan`. Nếu tắt `enabled`, starter không tự áp dụng migration khi khởi động; ứng dụng vẫn có thể quản lý migration bằng CLI hoặc pipeline riêng.

## 15. Thực thi migration bằng CLI

Ngoài chạy khi Spring Boot khởi động, Neo4j-Migrations cung cấp CLI để kiểm tra và áp dụng migration độc lập. Cách này hữu ích khi muốn tách việc triển khai database khỏi việc khởi động application instance.

Các lệnh thường dùng:

| Lệnh | Mục đích |
|---|---|
| `info` | Xem migration local, migration đã áp dụng và migration pending |
| `validate` | Kiểm tra version, thứ tự và checksum của lịch sử |
| `migrate` hoặc `apply` | Áp dụng migration còn thiếu |
| `repair` | Sửa migration chain metadata trong tình huống cần phục hồi |
| `delete` | Xóa một migration entry khỏi lịch sử quản lý |
| `clean` | Xóa metadata do Neo4j-Migrations tạo trong schema database |
| `run` | Chạy script mà không ghi nó vào migration history |

Ví dụ quy trình kiểm tra:

```bash
neo4j-migrations info
neo4j-migrations validate
neo4j-migrations migrate
neo4j-migrations info
```

CLI có thể dùng `.migration.properties` để lưu các tùy chọn kết nối và vị trí migration thay vì truyền lặp lại trên command line. Thông tin đăng nhập cần lấy từ secret hoặc môi trường triển khai; không đưa password production vào Git hay log.

`info` mặc định so sánh local với remote, giúp phát hiện migration thiếu, dư hoặc checksum không khớp. Có thể chọn chế độ local hoặc remote để kiểm tra riêng một phía.

## 16. Validate, repair và clean có mục đích khác nhau

### Validate

`validate` so sánh migration đã phát hiện ở local với chain đã ghi trong database. Database hợp lệ khi các migration được áp dụng đúng version, đúng thứ tự và checksum khớp. Nên chạy validate trong CI trước khi cho phép deploy.

### Repair

`repair` là thao tác phục hồi lịch sử khi chain không còn khớp với local, ví dụ script bị sửa hoặc file migration bị xóa. Công cụ có thể sửa checksum trong metadata, loại entry không còn script tương ứng hoặc bổ sung entry placeholder theo quy tắc repair.

**Repair không thực thi migration.** Nó chỉ chỉnh sửa chain metadata để đồng bộ lịch sử được ghi nhận với migration local. Vì vậy, không dùng repair như một lệnh để chạy lại các thay đổi Cypher bị thiếu. Chỉ thực hiện sau khi hiểu chính xác trạng thái schema/data và có backup phù hợp.

### Clean

`clean` xóa metadata do Neo4j-Migrations quản lý trong schema database, bao gồm migration chain và các thành phần quản lý liên quan. Đây là thao tác có tính phá hủy đối với lịch sử migration. Khi metadata bị xóa, lần chạy sau có thể xem các migration như chưa được áp dụng và thực thi lại chúng.

Không dùng `clean` như rollback hoặc cách sửa nhanh lỗi checksum trên production. Nếu cần khôi phục lịch sử, xem xét `repair` hoặc `delete` đúng trường hợp sau khi kiểm tra trạng thái database.

## 17. Không có rollback tự động cho thay đổi graph

Migration có phiên bản ghi lại thay đổi đã áp dụng, nhưng không tự động tạo một script hoàn tác tương ứng. Một câu lệnh `DROP CONSTRAINT`, `DELETE` hoặc chuyển đổi dữ liệu có thể không đảo ngược được nếu không giữ bản sao dữ liệu cũ.

Khi phát hiện lỗi sau khi triển khai:

1. Xác định migration nào đã chạy ở từng môi trường qua `info` và lịch sử.
2. Đánh giá dữ liệu bị ảnh hưởng và khả năng khôi phục.
3. Nếu có thể sửa tiến về phía trước, tạo migration version mới để khắc phục.
4. Nếu cần khôi phục trạng thái trước đó, dùng backup/restore hoặc kế hoạch phục hồi dữ liệu đã được kiểm thử.
5. Không chỉnh sửa file versioned đã chạy để biến nó thành migration khác.

Ví dụ, nếu `V002` chuẩn hóa tên sai, hãy tạo `V005__Fix_normalized_name.cypher` để tính lại dữ liệu theo quy tắc đúng. Giữ `V002` nguyên trạng để database mới và database cũ có cùng lịch sử migration.

## 18. Quản lý migration cho database đã có dữ liệu

Khi đưa migration tool vào một Neo4j database đang hoạt động, không nên giả định rằng database trống. Nếu công cụ chưa có lịch sử migration nhưng các node, index hoặc constraint đã tồn tại, việc áp dụng lại toàn bộ migration có thể gây xung đột hoặc thực hiện data transformation không mong muốn.

Quy trình tiếp nhận database hiện hữu:

1. Sao lưu database và xác định trạng thái schema/data hiện tại.
2. Liệt kê các constraint, index và quy tắc dữ liệu đã tồn tại.
3. Xác định migration nào mô tả chính xác trạng thái đã có và migration nào thực sự cần chạy.
4. Thử nghiệm quy trình tiếp nhận trên bản sao của database.
5. Chỉ cập nhật migration history theo quy trình được tài liệu đúng phiên bản công cụ hỗ trợ; không tự tạo hoặc sửa node `__Neo4jMigration` bằng Cypher.
6. Chạy `info` và `validate` để xác nhận lịch sử khớp với script local.

Không nhầm `repair` với baseline. `repair` chỉnh sửa metadata chain và không tự xác minh rằng mọi thay đổi schema/data thực tế đã được thực hiện đúng. Nếu chưa có quy trình tiếp nhận được kiểm thử, hãy dừng trước khi chạy migrate trên production.

## 19. Tích hợp migration vào CI/CD

Migration là một phần của quá trình phát hành database. Một pipeline có thể tổ chức như sau:

```text
Commit source code và Cypher scripts
              |
              v
       Review migration
              |
              v
       Build và test app
              |
              v
  Tạo Neo4j database kiểm thử
              |
              v
       info + validate
              |
              v
        migrate/apply
              |
              v
    Integration test với SDN
              |
              v
      Validate sau migrate
              |
              v
      Deploy application
```

Một số nguyên tắc triển khai:

- Chạy migration trong một deployment job có quyền ghi schema, không cấp quyền đó rộng rãi cho mọi application instance nếu không cần.
- Chọn một nơi chịu trách nhiệm áp dụng migration: CLI/Maven job hoặc Spring Boot startup. Tránh cấu hình hai quy trình độc lập cùng chạy một lần phát hành.
- Dùng `validate` để phát hiện checksum mismatch và migration bị thiếu trước khi deploy.
- Kiểm thử migration trên database có dữ liệu đại diện, không chỉ database rỗng.
- Theo dõi log phiên bản đã áp dụng và lưu lại artifact chứa đúng migration scripts của bản phát hành.
- Có backup và kế hoạch phục hồi trước các migration xóa hoặc biến đổi dữ liệu lớn.

Neo4j-Migrations có cơ chế khóa khi quản lý chain, nhưng pipeline vẫn nên có một bước migration rõ ràng và có thể quan sát để tránh nhiều hệ thống triển khai cạnh tranh nhau.

## 20. Kiểm tra trạng thái migration bằng Cypher

Neo4j-Migrations cho phép truy vấn subgraph lịch sử, nhưng chain này do công cụ sở hữu và không nên bị thay đổi thủ công. Có thể dùng truy vấn đọc để quan sát các node metadata:

```cypher
MATCH (migration:__Neo4jMigration)
RETURN properties(migration) AS migration;
```

Tên property cụ thể và cấu trúc chain có thể phụ thuộc phiên bản công cụ và việc có dùng schema database riêng hay không. Trong vận hành thường ngày, nên ưu tiên lệnh `info` vì công cụ đã biết cách diễn giải chain, version, target database và trạng thái pending/applied.

Không viết Cypher cập nhật trực tiếp các node migration để sửa checksum hoặc đánh dấu một script là đã chạy. Thao tác đó có thể làm mất tính nhất quán giữa checksum, thứ tự và chain metadata.

## 21. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Migration không được tìm thấy | Sai thư mục hoặc tên file không đúng convention | Kiểm tra `locations-to-scan` và tên `V...__...cypher` |
| Migration chạy lại ngoài ý muốn | Xóa lịch sử hoặc dùng `run` không ghi metadata | Kiểm tra history; dùng `migrate/apply` cho migration được quản lý |
| Checksum mismatch | Script `V` đã bị sửa sau khi áp dụng | Khôi phục script cũ hoặc tạo migration mới; không sửa lịch sử tùy tiện |
| Version cũ xuất hiện sau version mới | Migration được merge out-of-order | Sắp xếp lại quy trình phát hành; không bật out-of-order để che lỗi |
| Constraint không tạo được | Dữ liệu hiện tại có giá trị trùng hoặc null không phù hợp | Kiểm tra và làm sạch dữ liệu trước migration |
| Repeatable migration tạo dữ liệu trùng | Script `R` không idempotent | Dùng `MERGE`, `SET` hoặc thiết kế lại để có thể chạy nhiều lần |
| Script có DDL và DML thất bại trong cùng transaction | Một số DDL yêu cầu transaction riêng | Xem xét `PER_STATEMENT` và kiểm thử trên phiên bản Neo4j mục tiêu |
| Spring Boot không tìm thấy migration | Resource không nằm trong classpath mặc định | Đặt dưới `src/main/resources/neo4j/migrations` hoặc cấu hình location |
| `repair` chạy xong nhưng schema vẫn sai | Repair chỉ chỉnh migration chain metadata | Thực hiện migration thật hoặc khắc phục schema/data bằng version mới |
| `clean` khiến migration chạy lại | Metadata chain đã bị xóa | Chỉ dùng clean có chủ đích trên môi trường được phép |

## 22. Quy trình triển khai một migration mới

1. Xác định thay đổi schema hoặc data mà ứng dụng cần.
2. Chọn version tiếp theo và loại `V` hoặc `R` phù hợp.
3. Tạo Cypher script đúng convention trong thư mục migration.
4. Thiết kế câu lệnh an toàn với trạng thái dữ liệu thực tế; kiểm tra uniqueness, null và relationship cũ.
5. Nếu là repeatable migration, bảo đảm script idempotent.
6. Chạy migration trên database kiểm thử có dữ liệu đại diện.
7. Chạy `info`, `validate` và integration test với entity/repository SDN.
8. Review tác động transaction, index build, thời gian backfill và khả năng tương thích ứng dụng cũ.
9. Phát hành migration cùng artifact ứng dụng hoặc qua migration job được kiểm soát.
10. Kiểm tra lịch sử sau triển khai và theo dõi log.

## 23. Tự kiểm tra

1. Vì sao SDN entity mapping không thay thế migration có phiên bản?
2. Cấu trúc tên `V001__Create_person_constraints.cypher` gồm những phần nào?
3. Vì sao không được sửa versioned migration sau khi đã áp dụng?
4. Repeatable migration `R` khác versioned migration `V` ở điểm nào?
5. Vì sao script repeatable phải idempotent?
6. Neo4j-Migrations lưu lịch sử thực thi dưới dạng cấu trúc gì trong database?
7. Checksum giúp phát hiện vấn đề nào?
8. Khác biệt giữa `validate`, `repair` và `clean` là gì?
9. Khi nào nên chọn `PER_MIGRATION` và khi nào cần `PER_STATEMENT`?
10. Vì sao không nên dùng `repair` như một cách thực thi lại migration?
11. Cần lưu ý gì khi áp dụng migration tool vào database đã tồn tại dữ liệu?
12. Làm thế nào tích hợp validate và migrate vào CI/CD?

## Tài liệu tham khảo

- [Neo4j-Migrations — Documentation](https://michael-simons.github.io/neo4j-migrations/current/)
- [Neo4j-Migrations — Concepts và naming conventions](https://neo4j.com/labs/neo4j-migrations/2.0/concepts/)
- [Neo4j-Migrations — Usage: migrate, info, validate và repair](https://neo4j.com/labs/neo4j-migrations/2.1/usage/)
- [Neo4j-Migrations — Spring Boot Starter](https://github.com/michael-simons/neo4j-migrations)
- [Spring Data Neo4j — Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)
