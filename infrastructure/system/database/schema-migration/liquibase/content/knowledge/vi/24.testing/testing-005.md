# Giới hạn khi dùng H2 thay cho cơ sở dữ liệu production

## 1. Vì sao kiểm thử Liquibase chỉ bằng H2 chưa đủ?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi tích hợp Spring Boot, nhóm cần kiểm chứng migration trên nhiều môi trường và trong CI/CD. H2 là cơ sở dữ liệu quan hệ chạy trên Java, nhẹ và khởi động nhanh, nên thường được dùng trong profile test để khởi tạo application context và chạy repository.

Tuy nhiên, nếu production dùng PostgreSQL, MySQL, Oracle hoặc SQL Server, migration chạy thành công trên H2 **không chứng minh migration sẽ chạy thành công trên DBMS production**. Mỗi hệ quản trị có cú pháp SQL, kiểu dữ liệu, cách quản lý DDL, transaction, khóa, metadata và hành vi mặc định riêng. H2 chỉ tương thích một phần với các hệ quản trị khác.

Ví dụ, changeset tạo cột kiểu JSONB, dùng partial index của PostgreSQL hoặc gọi function riêng của Oracle có thể chạy đúng trên production nhưng không chạy được trên H2. Chiều ngược lại cũng xảy ra: SQL được H2 chấp nhận nhưng DBMS production từ chối hoặc diễn giải khác.

Bài học này giải thích phạm vi phù hợp của H2, các khác biệt dễ làm sai kết quả migration, giới hạn của compatibility mode và cách bổ sung kiểm thử bằng đúng DBMS production. Sau bài học, bạn có thể:

- Chọn đúng loại kiểm thử cho H2 và database production.
- Nhận diện rủi ro về SQL, DDL, transaction, kiểu dữ liệu, constraint và locking.
- Thiết kế test Liquibase với Testcontainers hoặc database cùng engine.
- Kiểm tra cả database trống và quá trình nâng cấp từ phiên bản schema cũ.
- Tổ chức CI/CD để phát hiện migration lỗi trước khi phát hành.

## 2. H2 phù hợp với loại kiểm thử nào?

H2 có những ưu điểm rõ ràng:

- Khởi động nhanh, không cần cài đặt server database riêng cho từng developer.
- Có thể chạy in-memory, thuận tiện tạo database mới cho mỗi test.
- Tích hợp tốt với Java, JDBC và nhiều framework Spring.
- Hữu ích để kiểm tra wiring của Spring context, mapping ORM cơ bản và truy vấn SQL portable.
- Hỗ trợ kiểm thử nhanh một số changeset Liquibase dùng change type phổ biến, độc lập DBMS.

H2 phù hợp để kiểm tra:

1. Spring Boot có đọc đúng cấu hình root changelog hay không.
2. Root changelog và file include có nằm trong classpath không.
3. Changeset portable có tạo bảng/cột cơ bản không.
4. Repository có thực hiện CRUD thông thường không.
5. Service có xử lý đúng dữ liệu sau khi schema thử nghiệm được khởi tạo không.
6. Test có cô lập dữ liệu giữa các trường hợp hay không.

H2 hữu ích nhất khi câu hỏi là **logic ứng dụng có hoạt động với một database quan hệ tương thích cơ bản hay không**. Nếu câu hỏi là **Liquibase có tạo đúng schema và dữ liệu trên PostgreSQL/MySQL/Oracle/SQL Server hay không**, phải kiểm thử bằng chính engine đó.

### 2.1. Phân biệt kiểm thử ứng dụng với kiểm thử migration

| Mục tiêu | H2 có thể hỗ trợ? | Cần DBMS production? |
|---|---|---|
| Test service thuần, không phụ thuộc SQL cụ thể | Có | Thường không |
| Test repository dùng SQL portable | Có thể | Nên có kiểm thử bổ sung |
| Kiểm tra root changelog được nạp | Có thể | Cần kiểm tra artifact production |
| Kiểm tra createTable/addColumn đơn giản | Có thể | Có, trước khi chấp nhận release |
| Kiểm tra JSONB, sequence, function riêng DBMS | Không đủ | Có |
| Kiểm tra DDL transaction và implicit commit | Không đủ | Có |
| Kiểm tra lock/concurrency thực tế | Không đủ | Có |
| Kiểm tra execution plan, index và hiệu năng | Không đủ | Có |
| Kiểm tra migration từ schema phiên bản cũ | Mô phỏng một phần | Cần DBMS thật |
| Kiểm tra quyền, schema và metadata production | Không đủ | Có |

Không cần bỏ H2 chỉ vì nó không mô phỏng production hoàn hảo. Hãy dùng nó cho các test nhanh đúng phạm vi và có một tầng kiểm thử riêng trên DBMS thực tế.

## 3. H2 không phải bản mô phỏng đầy đủ của DBMS production

Một hệ quản trị database không chỉ là nơi thực thi câu SQL. Nó còn có parser, type system, transaction manager, optimizer, catalog metadata, locking và quy tắc tương thích riêng.

```text
Ứng dụng / Liquibase
        |
        v
JDBC driver + SQL / metadata API
        |
        v
DBMS thực tế
  - parser và type system
  - transaction / DDL
  - catalog / schema
  - lock / concurrency
  - optimizer / execution plan

H2 mode chỉ mô phỏng một phần hành vi
và không thay thế DBMS production.
```

Hai database có thể chấp nhận cùng một câu SQL nhưng tạo ra kết quả khác về kiểu dữ liệu, giá trị mặc định, khóa hoặc transaction. Test pass trên H2 là bằng chứng cho H2; nó chỉ là bằng chứng gián tiếp cho production.

## 4. Khác biệt về SQL và cú pháp DDL

Các DBMS khác nhau về:

- Cách khai báo identity/auto-increment.
- Cách tạo sequence và lấy giá trị sequence.
- Cú pháp đổi tên cột, bảng, index hoặc constraint.
- Cách tạo index có điều kiện hoặc index đồng thời.
- Cú pháp thêm constraint có kiểm tra ngay hay trì hoãn kiểm tra.
- Cách định nghĩa view, materialized view, trigger và stored procedure.
- Cách viết upsert/merge.
- Cách dùng schema, catalog và identifier có quote.

Một câu SQL được H2 chấp nhận không nhất thiết hợp lệ trên DBMS đích. SQL đặc thù PostgreSQL có thể không chạy trên H2 dù changelog chính xác cho production.

### 4.1. Ví dụ cú pháp riêng DBMS

PostgreSQL hỗ trợ kiểu và cú pháp riêng như JSONB, ON CONFLICT và một số tùy chọn index. MySQL có cách biểu diễn auto-increment, collation và DDL riêng. Oracle có type system, sequence và package riêng. SQL Server có cú pháp identity, schema và function riêng.

Liquibase change type chuẩn giúp trừu tượng hóa nhiều thay đổi phổ biến, nhưng không loại bỏ mọi khác biệt. Khi dùng change SQL, sql hoặc sqlFile, nhóm phải kiểm thử SQL trên DBMS đích.

### 4.2. Compatibility mode không chứng minh tương thích

Ví dụ URL H2:

```properties
spring.datasource.url=jdbc:h2:mem:liquibase-test;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
```

MODE=PostgreSQL có thể làm H2 chấp nhận thêm một số cú pháp hoặc thay đổi một số quy tắc. Nó không cung cấp đầy đủ parser, type, catalog, function, transaction hay optimizer của PostgreSQL. Hành vi tương tự áp dụng cho các compatibility mode khác.

Hãy xem mode là tiện ích giúp một số test ít phải chỉnh sửa, không phải lớp thay thế PostgreSQL trong CI.

## 5. Khác biệt về kiểu dữ liệu và chuyển đổi dữ liệu

Type system là nguồn lỗi phổ biến khi migration chuyển từ H2 sang DBMS production.

| Nhóm | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Chuỗi | VARCHAR, TEXT, CLOB, collation | Độ dài, so sánh, encoding và giới hạn |
| Số | NUMERIC, DECIMAL, NUMBER, BIGINT | Precision, scale, rounding và overflow |
| Thời gian | TIMESTAMP, TIMESTAMP WITH TIME ZONE, DATE | Time zone, độ chính xác và cách lưu |
| Boolean | BOOLEAN, BIT, kiểu thay thế | Giá trị và cách JDBC ánh xạ |
| JSON | JSON, JSONB | Kiểu native, operator và index |
| Binary | BLOB, BYTEA, VARBINARY | Giới hạn kích thước và cách đọc/ghi |
| UUID | UUID, CHAR(36), RAW | Kiểu native, format và index |
| Array/enum | Array, enum native hoặc bảng tham chiếu | Cú pháp, mapping và constraint |

Ví dụ, H2 có thể chấp nhận một kiểu dữ liệu gần tương đương trong khi PostgreSQL yêu cầu kiểu native cụ thể. Nếu migration dùng JSONB, test H2 có thể không kiểm tra được operator JSON hoặc index GIN của PostgreSQL.

Tương tự, test chỉ dùng ngày giờ đơn giản có thể bỏ qua lỗi timezone hoặc độ chính xác khi production dùng timestamp khác. Hãy tạo dữ liệu biên như giá trị null, số lớn, timestamp có offset và chuỗi Unicode để kiểm tra trên DBMS thật.

### 5.1. Kiểu dữ liệu không chỉ là tên

Ngay cả khi hai DBMS đều hỗ trợ VARCHAR(100), quy tắc collation, so sánh hoa thường, khoảng trắng và encoding có thể khác. NUMERIC(10,2) có thể xử lý rounding hoặc overflow khác trong một số biểu thức.

Không kết luận migration tương thích chỉ vì schema diff cho thấy tên và kiểu cột giống nhau. Hãy kiểm tra dữ liệu, constraint và kết quả truy vấn thực tế.

## 6. Khác biệt về DDL và transaction

Một thay đổi Liquibase thường được thực hiện theo changeset và có thể chạy trong transaction khi DBMS và loại câu lệnh hỗ trợ. Tuy nhiên, **không phải mọi DBMS đều có cùng hành vi transaction đối với DDL**.

Ví dụ:

- PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL, nhưng một số lệnh đặc biệt có giới hạn khi chạy trong transaction.
- MySQL có nhiều thao tác DDL gây implicit commit; không nên giả định có thể rollback DDL giống DML.
- Oracle có quy tắc commit ngầm cho nhiều DDL.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng hành vi vẫn phụ thuộc loại thao tác và trạng thái hệ thống.
- H2 có thể có hành vi khác DBMS production, nên test transaction trên H2 không chứng minh rollback DDL trên production.

### 6.1. runInTransaction không tạo transaction toàn bộ changelog

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 100-add-customer-status
      author: migration-team
      runInTransaction: true
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: varchar(20)
```

runInTransaction điều khiển transaction của changeset theo khả năng hỗ trợ. Nó không làm toàn bộ changelog trở thành một transaction duy nhất. Những changeset trước đó có thể đã commit khi một changeset sau thất bại.

Nếu dùng runInTransaction: false, phải hiểu chính xác lệnh nào có thể đã thực thi trước khi lỗi. Không dùng tùy chọn này để né một lỗi DDL chưa được điều tra.

### 6.2. Test partial failure trên đúng DBMS

Một bài test quan trọng là cố ý làm một changeset thất bại sau khi đã có một số thay đổi. Sau đó xác nhận:

- Changeset nào đã được ghi vào DATABASECHANGELOG.
- Schema thực tế còn lại những object nào.
- Dữ liệu có bị cập nhật một phần không.
- Lock có được giải phóng không.
- Lần chạy tiếp theo tiếp tục ở đâu và có an toàn không.

H2 có thể không tái hiện đúng partial DDL/implicit commit của production. Cần chạy bài test này trên engine đích hoặc môi trường thử nghiệm tương đương.

## 7. Khác biệt về constraint và tính toàn vẹn dữ liệu

Các DBMS có thể khác nhau về:

- Thời điểm kiểm tra foreign key và check constraint.
- Khả năng trì hoãn constraint đến cuối transaction.
- Hành vi với NULL trong unique index.
- Cách xử lý duplicate khi tạo unique constraint.
- Quy tắc cascade khi xóa/cập nhật.
- Khả năng validate constraint trên bảng lớn.
- Cách đặt tên và giới hạn độ dài tên constraint.

Một migration tạo unique index có thể pass trên H2 nhưng fail trên production vì dữ liệu thật có duplicate hoặc quy tắc NULL khác. Dữ liệu test nhỏ cũng có thể không bộc lộ vấn đề khi production có hàng triệu dòng.

Ví dụ precondition trước khi thêm unique constraint:

```yaml
databaseChangeLog:
  - changeSet:
      id: 110-add-unique-customer-email
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                SELECT email
                FROM customer_account
                WHERE email IS NOT NULL
                GROUP BY email
                HAVING COUNT(*) > 1
              ) duplicates
      changes:
        - addUniqueConstraint:
            tableName: customer_account
            columnNames: email
            constraintName: uq_customer_email
```

Câu truy vấn và change type cần được kiểm thử trên DBMS đích. Nếu semantics của NULL hoặc collation khác nhau, truy vấn duplicate cũng phải được điều chỉnh theo yêu cầu nghiệp vụ và engine thực tế.

## 8. Khác biệt về identifier, schema và metadata

Một vấn đề thường bị bỏ qua là cách DBMS lưu tên bảng/cột và metadata:

- Quy tắc viết hoa/thường và identifier có quote.
- Schema mặc định và search path.
- Tên constraint/index tự sinh.
- Giới hạn độ dài identifier.
- Catalog metadata được JDBC driver trả về.
- Quyền nhìn thấy bảng, view, sequence và constraint.
- Quyền tạo/sửa object trong schema cụ thể.

Một bảng được tạo không quote có thể được DBMS lưu tên theo quy tắc riêng. Một câu query dùng identifier có quote với chữ hoa có thể hoạt động trên H2 nhưng không tìm thấy object trên PostgreSQL hoặc ngược lại.

Liquibase snapshot, diff, status và việc tạo DATABASECHANGELOG/DATABASECHANGELOGLOCK đều phụ thuộc metadata database. Kiểm thử H2 không xác nhận quyền và schema metadata của tài khoản production.

### 8.1. Kiểm tra schema thực tế

Không chỉ kiểm tra bảng có tồn tại. Hãy xác nhận đúng schema/catalog, tên và kiểu cột, nullability và default, primary key, unique, foreign key, check, index và thứ tự cột trong index, view, sequence và đối tượng phụ thuộc, cùng vị trí/quyền của bảng Liquibase metadata.

Các truy vấn metadata như information_schema có thể khác nhau giữa DBMS. Viết test phù hợp engine đích hoặc dùng JDBC metadata khi phù hợp, nhưng vẫn xác minh kết quả thực trên database thật.

## 9. Index, locking và hiệu năng không thể suy ra từ H2

H2 không đại diện cho tải, concurrency hoặc execution plan production. Những khác biệt quan trọng:

- Cách tạo index và mức khóa bảng trong lúc tạo.
- Index có điều kiện, index expression hoặc index chuyên biệt.
- Lock escalation, deadlock và timeout.
- Isolation level và MVCC.
- Optimizer statistics và execution plan.
- Chi phí rewrite bảng khi thêm cột/default hoặc đổi kiểu.
- Khả năng thực hiện DDL online/concurrently.

Một migration thêm index trên bảng lớn có thể hoàn tất gần như tức thời trên H2 vì dữ liệu thử rất nhỏ, nhưng mất nhiều phút và giữ lock trên production. Vì vậy, kiểm thử hiệu năng migration cần dataset gần thực tế và DBMS thật.

Ví dụ PostgreSQL có CREATE INDEX CONCURRENTLY, nhưng lệnh này có giới hạn transaction riêng. Không thể kết luận cách dùng runInTransaction hoặc hành vi thất bại của lệnh này chỉ từ test H2.

## 10. Compatibility mode: lợi ích và giới hạn

H2 hỗ trợ một số mode mô phỏng cú pháp/hành vi phổ biến của database khác. Chúng có thể hữu ích khi di chuyển test suite cũ sang cấu hình gần production hơn, kiểm tra nhanh một phần cú pháp phổ biến hoặc giảm khác biệt hiển nhiên trong cách viết SQL.

Nhưng mode không tái tạo đầy đủ parser và cú pháp DBMS, native type/function/operator/extension, transaction/implicit commit của DDL, lock/concurrency, catalog/schema/JDBC metadata, optimizer/execution plan/hiệu năng, quyền/role/grant và hành vi bảo mật.

Do đó, không nên dùng mode như tiêu chí duy nhất để chứng minh tương thích. Nếu migration có SQL đặc thù, phải chạy trên DBMS thực tế.

### 10.1. Không làm changelog production phụ thuộc H2 chỉ để test pass

Một cách xử lý sai là thêm changeset riêng cho H2 để tránh lỗi test, trong khi production dùng changeset khác và không còn cùng logic migration. Điều này tạo ra hai đường schema khác nhau và khiến test xanh không kiểm tra được đường triển khai thật.

Nếu một thay đổi thực sự khác nhau theo DBMS, hãy khai báo thuộc tính dbms có chủ đích và kiểm thử từng nhánh trên DBMS tương ứng. Nếu chỉ khác cú pháp nhưng cùng ý nghĩa, dùng change type portable khi có thể hoặc tách SQL riêng có review.

## 11. Cấu hình H2 cho kiểm thử nhanh với Spring Boot

Ví dụ application-test.yaml:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:liquibase-test;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
    username: sa
    password:
    driver-class-name: org.h2.Driver
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
```

Ý nghĩa:

- jdbc:h2:mem tạo database in-memory.
- DB_CLOSE_DELAY=-1 giữ database tồn tại sau khi connection cuối đóng trong vòng đời JVM.
- DB_CLOSE_ON_EXIT=FALSE tránh H2 tự đóng theo hook exit trong những tình huống test cần kiểm soát vòng đời.
- Liquibase vẫn chạy changelog trên H2.
- Hibernate validate mapping với schema Liquibase đã tạo.

Cấu hình này hữu ích cho test nhanh, nhưng cần hiểu giới hạn:

1. Database có thể tồn tại lâu hơn một test nếu dùng chung tên trong cùng JVM.
2. Test song song có thể chia sẻ database nếu cùng URL.
3. H2 có thể chấp nhận SQL mà production từ chối.
4. Changeset có dbms: postgresql sẽ không chạy trên H2; test có thể thiếu object nếu không kiểm tra kỹ.
5. Test không chứng minh DDL, transaction và index có hành vi giống production.

Để cô lập test, dùng tên database riêng cho từng suite/context hoặc reset đúng cách. Tránh dùng chung một in-memory database giữa test không liên quan.

### 11.1. Không tắt Liquibase trong test migration

Nếu mục tiêu test là kiểm tra migration, không đặt spring.liquibase.enabled=false rồi chỉ tạo schema bằng Hibernate ddl-auto=create. Làm vậy test không chạy changelog và không kiểm tra đường triển khai thực tế.

Có thể tắt Liquibase trong test unit thuần không cần database, nhưng test migration phải bật Liquibase và xác minh kết quả của chính changelog.

## 12. Testcontainers: chạy đúng DBMS trong kiểm thử tích hợp

Testcontainers cho phép khởi chạy database thật trong container phục vụ test. Với PostgreSQL, test có thể dùng image PostgreSQL; với MySQL, dùng image MySQL tương ứng. Cách này kiểm tra Liquibase bằng cùng engine production và tự động hóa được trong CI.

Ưu điểm:

- SQL và DDL được thực thi bởi DBMS thật.
- Native type, constraint, sequence, function và metadata gần production hơn.
- Có thể kiểm tra lock, transaction và rollback trên engine tương ứng.
- Database được tạo mới cho test, giảm lệ thuộc môi trường developer.
- CI có thể chạy cùng quy trình như máy local nếu hỗ trợ container runtime.

Testcontainers vẫn không bảo đảm môi trường giống production tuyệt đối: version image, extensions, collation, config, memory, storage, network và data volume có thể khác. Hãy cố định image/version gần production và cấu hình extension cần thiết.

### 12.1. Ví dụ integration test với PostgreSQL

Ví dụ dùng JUnit 5, Spring Boot và Testcontainers:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class LiquibaseMigrationIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void migrationCreatesStatusColumn() {
        Integer count = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'customer_account'
              AND column_name = 'status_code'
            """,
            Integer.class
        );

        assertThat(count).isEqualTo(1);
    }
}
```

Đây là khung minh họa; dự án cần thêm dependency Testcontainers JUnit Jupiter và module PostgreSQL với version tương thích. @DynamicPropertySource được Spring Test hỗ trợ; Spring Boot mới có thể chọn cơ chế service connection phù hợp. Hãy pin image về đúng phiên bản production hoặc digest đã phê duyệt, không dùng tag trôi nổi latest.

### 12.2. Kiểm tra DATABASECHANGELOG cùng schema

Ngoài việc kiểm tra cột, test nên xác nhận changeset đã được ghi nhận:

```java
@Test
void liquibaseRecordsAppliedChangeset() {
    Integer count = jdbcTemplate.queryForObject(
        """
        SELECT COUNT(*)
        FROM databasechangelog
        WHERE id = '100-add-customer-status'
          AND author = 'migration-team'
        """,
        Integer.class
    );

    assertThat(count).isEqualTo(1);
}
```

Ví dụ giả định bảng metadata mặc định ở schema hiện hành. Nếu dự án cấu hình schema hoặc tên bảng khác, truy vấn phải điều chỉnh theo cấu hình thật. Chỉ kiểm tra history chưa đủ; phải kiểm tra cả hiệu ứng schema và dữ liệu.

## 13. Kiểm tra migration từ database trống và từ phiên bản cũ

Chạy changelog từ database trống là cần thiết nhưng chưa đủ. Production thường nâng cấp từ phiên bản schema đã có dữ liệu và lịch sử.

### 13.1. Fresh install

1. Khởi tạo DBMS production trống.
2. Chạy root changelog từ đầu.
3. Xác nhận mọi changeset cần thiết được áp dụng.
4. Kiểm tra schema, constraint, index, view và metadata.
5. Kiểm tra dữ liệu seed/reference nếu có.
6. Chạy truy vấn ứng dụng đại diện.

Fresh install phát hiện lỗi thứ tự include, thiếu file, dependency và giả định schema ban đầu.

### 13.2. Upgrade path

1. Khởi tạo database từ release trước hoặc snapshot đã chuẩn bị.
2. Nạp dữ liệu đại diện có NULL, duplicate, giá trị cũ và quan hệ tham chiếu.
3. Chạy Liquibase từ changelog của release mới.
4. Kiểm tra mapping và dữ liệu sau backfill.
5. Xác nhận constraints và index mới.
6. Kiểm tra lịch sử changeset và checksum.
7. Chạy smoke test ứng dụng tương thích.

Upgrade path thường phát hiện lỗi mà fresh install không thấy, như backfill không xử lý dữ liệu legacy, unique constraint gặp duplicate hoặc FK bị orphan.

### 13.3. Kiểm tra nhiều release

Với thay đổi lớn, nên test đường đi từ một vài phiên bản schema được hỗ trợ thay vì chỉ một baseline duy nhất. Nếu production có thể đang ở release N-2, cần xác nhận changelog mới nâng cấp được từ trạng thái đó hoặc tài liệu hóa điều kiện nâng cấp.

Không cần nhân bản mọi tổ hợp release vô hạn; chọn các trạng thái thực tế được hỗ trợ theo chính sách rollout.

## 14. Kiểm thử precondition và dữ liệu thực

Precondition là một phần logic migration. Test nên bao gồm:

- Precondition đạt: changeset chạy và tạo hiệu ứng đúng.
- Precondition không đạt với HALT: migration dừng và không đánh dấu changeset như đã thực thi thành công.
- CONTINUE hoặc MARK_RAN: hành vi đúng với chính sách đã thiết kế.
- Dữ liệu NULL, duplicate, orphan và mã ngoài mapping.
- Trường hợp dữ liệu biên lớn, chuỗi Unicode, timestamp và số precision cao.

Ví dụ precondition kiểm tra orphan trước khi tạo FK:

```yaml
databaseChangeLog:
  - changeSet:
      id: 120-add-customer-status-fk
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account c
              WHERE c.status_code IS NOT NULL
                AND NOT EXISTS (
                  SELECT 1
                  FROM account_status s
                  WHERE s.code = c.status_code
                )
      changes:
        - addForeignKeyConstraint:
            constraintName: fk_customer_status
            baseTableName: customer_account
            baseColumnNames: status_code
            referencedTableName: account_status
            referencedColumnNames: code
```

Truy vấn precondition phải chạy được trên DBMS đích. Nếu chỉ test trên H2, khác biệt SQL, schema hoặc collation có thể làm test cho kết quả khác. Với precondition SQL tùy chỉnh, hãy chạy test trên engine production.

## 15. Kiểm thử rollback và thất bại giữa chừng

Rollback cũng phụ thuộc DBMS. Một rollback DROP COLUMN, ALTER TABLE hoặc DML có thể có hành vi transaction khác nhau giữa H2 và production.

Bộ test rollback nên xác minh:

1. SQL rollback được sinh đúng bằng lệnh preview phù hợp.
2. Thao tác rollback chạy được trên DBMS đích.
3. Schema sau rollback có trạng thái mong muốn.
4. Dữ liệu có được khôi phục đúng hay có phần không thể đảo ngược.
5. DATABASECHANGELOG phản ánh lịch sử sau rollback theo cơ chế Liquibase.
6. Ứng dụng cũ có thể hoạt động với schema sau rollback nếu đó là mục tiêu.

Ngoài ra, hãy mô phỏng một changeset lỗi sau khi changeset trước đã thành công. Kiểm tra history, partial DDL/DML và lock. H2 không thể thay thế test này nếu production có implicit commit hoặc DDL-specific behavior.

Không giả định một lần rollback nhiều changeset là transaction toàn cục. Cần đánh giá từng changeset và DBMS.

## 16. Kiểm thử concurrency, lock và nhiều instance

H2 in-memory thường không phản ánh cách database production xử lý nhiều client, nhiều process, network interruption và lock trên server. Để kiểm tra migration concurrency:

- Dùng cùng DBMS production trong container hoặc môi trường thử nghiệm.
- Khởi chạy hai process Liquibase có kiểm soát cùng database.
- Quan sát DATABASECHANGELOGLOCK.
- Xác nhận một tiến trình không chạy cùng changeset đồng thời với tiến trình còn lại.
- Thử timeout hoặc dừng process trong môi trường lab.
- Xác minh lock còn lại được xử lý đúng sau khi chắc chắn không còn process hoạt động.

Test concurrency không chỉ xác nhận Liquibase lock; còn phải xem DBA/script bên ngoài có thể thay đổi schema song song hay không. Liquibase lock không điều phối công cụ không dùng cùng cơ chế.

Nếu hệ thống dùng nhiều replica Spring Boot, nên kiểm tra cả mô hình một migration job riêng trước rollout. Test H2 với một application context không chứng minh được hành vi lock và thời gian chờ của nhiều replica.

## 17. Chiến lược hai tầng database cho Spring Boot

Một chiến lược thực tế là giữ H2 cho kiểm thử nhanh và thêm integration test trên DBMS production:

| Tầng | Database | Phạm vi |
|---|---|---|
| Unit test | Không cần DB hoặc mock | Logic thuần, mapping nghiệp vụ |
| Fast integration | H2 | Wiring cơ bản, repository portable, startup nhanh |
| Migration integration | Testcontainers hoặc DBMS thật | Chạy changelog, precondition, DDL/DML |
| Upgrade/rollback test | DBMS production, dữ liệu đại diện | Nâng cấp release cũ, rollback, partial failure |
| Staging validation | Cấu hình gần production | Quyền, extension, dataset và thời gian triển khai |

Không cần chạy mọi test trên database thật. Hãy chạy các bài test engine-specific và migration ở tầng phù hợp để cân bằng tốc độ với độ tin cậy.

### 17.1. Profile test phải rõ ràng

Ví dụ application-test.yaml cho kiểm thử nhanh:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:fast-test;DB_CLOSE_DELAY=-1
    username: sa
    password:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Ví dụ application-migration-test.yaml:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Integration test với Testcontainers sẽ cung cấp URL, username và password của DBMS thật qua dynamic properties. Không nên để profile migration test âm thầm rơi về H2 nếu container không khởi động; test phải fail rõ ràng thay vì tự chuyển database.

### 17.2. Tránh H2 fallback không được nhận biết

Một cấu hình có thể khiến Spring Boot tự chọn H2 khi dependency có mặt và URL production test không được bind đúng. Khi đó, test báo pass nhưng thực chất chạy trên H2.

Trong test migration, hãy kiểm tra URL/driver/DBMS thực tế ngay từ log hoặc assertion. Nếu mục tiêu là PostgreSQL, test phải xác nhận product name/driver hoặc metadata database là PostgreSQL. Không chỉ dựa vào tên profile.

## 18. CI/CD: kiểm chứng đúng DBMS trước khi release

Một pipeline có thể triển khai các cổng sau:

```text
Commit changelog
      |
      v
Parse / validate / code review
      |
      v
Fast tests (H2)
      |
      v
Start DBMS production engine (ephemeral)
      |
      v
Fresh install + update path
      |
      v
Precondition / data migration / rollback tests
      |
      v
Verify schema + DATABASECHANGELOG
      |
      v
Review SQL / duration / lock / permissions
      |
      v
Approve release
      |
      v
Deploy to staging / production
```

Các nguyên tắc:

1. **Pin phiên bản DBMS:** dùng image/instance gần production, gồm extension và cấu hình cần thiết.
2. **Dùng đúng artifact:** test changelog cùng artifact sẽ deploy, không test một file khác với file đóng gói.
3. **Kiểm tra cả fresh và upgrade:** database trống và snapshot release cũ.
4. **Đo dữ liệu đại diện:** có duplicate, NULL, orphan và số lượng gần thực tế.
5. **Review SQL preview:** xem update-sql và rollback preview theo đúng phiên bản/config.
6. **Kiểm tra quyền:** tài khoản migration và tài khoản runtime có quyền đúng.
7. **Kiểm tra lock/timeout:** đặc biệt với DDL trên bảng lớn.
8. **Không fallback âm thầm:** nếu container DBMS thật không chạy, pipeline phải báo lỗi thay vì chuyển sang H2.
9. **Hậu kiểm:** kiểm tra schema, dữ liệu, history và readiness của ứng dụng.
10. **Giữ log an toàn:** không đưa credentials vào artifact hoặc output.

Nếu production dùng dịch vụ database được quản lý với extension/cấu hình riêng, container tiêu chuẩn có thể vẫn chưa đủ. Hãy có bước validation trên staging gần production hoặc database ephemeral được cấu hình tương đương.

## 19. Những lỗi thường gặp khi chỉ test bằng H2

| Triệu chứng | Nguyên nhân có thể | Cách cải thiện |
|---|---|---|
| Test H2 pass, production syntax error | SQL/DDL khác DBMS | Chạy migration integration trên engine thật |
| H2 không nhận JSONB hoặc function riêng | Native feature không được mô phỏng | Dùng Testcontainers DBMS đích |
| Migration pass nhưng production lock lâu | H2 dataset nhỏ và locking khác | Test với dữ liệu đại diện, đo thời gian và lock |
| Rollback H2 thành công nhưng production không rollback DDL | Transaction semantics khác | Kiểm tra rollback trên engine production |
| Test thiếu changeset dbms: postgresql | H2 không thỏa điều kiện DBMS | Có test riêng PostgreSQL; xác nhận expected schema |
| Test schema khác production | Hibernate ddl-auto=create hoặc Liquibase bị tắt | Bật Liquibase và xác minh changelog thật |
| Test pass dù kết nối nhầm H2 | Profile fallback/URL không bind | Assert database product và driver |
| Constraint fail ở production | Dữ liệu thật có duplicate/orphan/NULL | Upgrade test với dữ liệu legacy đại diện |
| Khác biệt tên bảng/cột | Quy tắc identifier/schema khác | Kiểm tra metadata trên DBMS thật |
| Migration chạy quá lâu | Index/rewrite/lock không được mô phỏng | Benchmark trên engine và quy mô dữ liệu gần production |
| Nhiều replica chờ lock | H2 test đơn instance | Kiểm thử concurrency bằng DBMS server |
| Staging khác production | Version, extension, collation hoặc config khác | Chuẩn hóa môi trường và ghi nhận sai khác |

H2 test pass là tín hiệu tốt cho tầng kiểm thử nhanh. Nó không nên được dùng làm tiêu chí duy nhất để phê duyệt migration production.

## 20. Bài thực hành: so sánh H2 và PostgreSQL cho cùng changelog

**Mục tiêu:** kiểm tra một root changelog trên H2 và PostgreSQL để thấy rõ khác biệt. Thực hiện trên database thử nghiệm, không dùng production.

### Bước 1. Tạo changeset portable

Tạo một changeset cơ bản dùng createTable, addColumn, primary key và unique constraint. Đảm bảo root changelog được đóng gói vào classpath.

### Bước 2. Chạy trên H2

- Cấu hình profile test dùng H2 in-memory.
- Bật Liquibase.
- Khởi động Spring context.
- Xác minh bảng, cột, constraint và record DATABASECHANGELOG.
- Ghi nhận những change type đã chạy.

### Bước 3. Chạy cùng artifact trên PostgreSQL

- Dùng Testcontainers hoặc PostgreSQL test instance.
- Pin image/version phù hợp production.
- Cấp URL/credentials qua dynamic properties.
- Chạy cùng root changelog.
- Kiểm tra schema và lịch sử.

### Bước 4. Thêm một thay đổi đặc thù DBMS

Ví dụ dùng kiểu JSONB, index hoặc function riêng PostgreSQL. Chạy trên PostgreSQL và quan sát H2 không thể chứng minh tính đúng đắn của thay đổi này. Nếu changelog dùng thuộc tính dbms, xác nhận changeset được chọn đúng trên từng engine.

### Bước 5. Kiểm tra dữ liệu legacy

Nạp dữ liệu có NULL, duplicate và mã trạng thái ngoài mapping. Chạy precondition và backfill. Xác nhận kết quả trên PostgreSQL và so sánh với kỳ vọng nghiệp vụ.

### Bước 6. Kiểm tra rollback và lỗi

Thử rollback trên PostgreSQL lab; tạo một changeset cố ý thất bại và kiểm tra partial apply, history, lock. Ghi lại khác biệt với H2 nếu có.

### Bước 7. Xác nhận CI

Đảm bảo pipeline không bỏ qua tầng PostgreSQL nếu container không sẵn sàng. Nếu production dùng DBMS khác, thêm engine tương ứng vào migration test.

**Tiêu chí hoàn thành:** giải thích được những gì H2 xác nhận và những gì nó không xác nhận; cùng changelog được kiểm thử trên DBMS production; migration, data, rollback và history có bằng chứng.

## 21. Checklist chọn H2 hay DBMS production

- [ ] H2 chỉ được dùng cho test nhanh có phạm vi rõ.
- [ ] Không dùng compatibility mode như bằng chứng đầy đủ về tương thích DBMS.
- [ ] Test migration bật Liquibase và dùng root changelog thực tế.
- [ ] Không để Hibernate tạo schema thay cho changelog trong test migration.
- [ ] Có test trên đúng DBMS production hoặc môi trường engine tương đương.
- [ ] DBMS, driver, extension, collation và cấu hình gần production được pin/ghi nhận.
- [ ] Đã kiểm tra DDL, transaction, partial apply và rollback trên engine đích.
- [ ] Đã kiểm tra type, identifier, schema, constraint, index và native feature.
- [ ] Có dữ liệu legacy đại diện để kiểm tra precondition và backfill.
- [ ] Có test fresh install và upgrade từ release cũ.
- [ ] Có test lock/concurrency khi kiến trúc cần nhiều process/replica.
- [ ] Test xác nhận đúng DBMS/driver, không fallback âm thầm sang H2.
- [ ] CI chạy migration test trước khi release; failure làm dừng rollout.
- [ ] Hậu kiểm schema, dữ liệu và DATABASECHANGELOG.
- [ ] Có staging hoặc môi trường tương đương để kiểm tra các khác biệt cấu hình còn lại.

**Kết luận:** H2 giúp kiểm thử nhanh Spring Boot, repository và một phần changeset portable, nhưng không mô phỏng đầy đủ DBMS production. Khác biệt về SQL, kiểu dữ liệu, DDL transaction, constraint, metadata, locking và hiệu năng có thể khiến migration pass trên H2 nhưng thất bại khi triển khai thật. Hãy giữ H2 ở tầng kiểm thử nhanh và bổ sung migration integration trên đúng engine production bằng Testcontainers hoặc database thử nghiệm tương đương. Chỉ khi kiểm tra fresh install, upgrade path, dữ liệu, rollback và lịch sử trên DBMS đích, nhóm mới có bằng chứng đủ mạnh để đưa migration vào release.

