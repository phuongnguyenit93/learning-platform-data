# Migration và việc xác nhận schema khởi tạo được

**Ngữ cảnh:** Spring Framework Testing → Kiểm thử tầng dữ liệu.

Migration là cơ chế đưa cấu trúc cơ sở dữ liệu từ một phiên bản đã biết sang phiên bản mới. Trong kiểm thử tầng dữ liệu, cần chứng minh rằng một cơ sở dữ liệu mới có thể được khởi tạo từ đầu, các migration được áp dụng theo đúng thứ tự, và schema sau khi khởi tạo đáp ứng hợp đồng mà ứng dụng cần.

Một ứng dụng khởi động thành công chưa đủ để kết luận migration đúng. Ứng dụng có thể đang kết nối nhầm database, dùng schema đã tồn tại từ lần chạy trước, hoặc Hibernate tự tạo bảng khiến migration bị bỏ sót. Vì vậy, bài kiểm thử phải kiểm soát trạng thái ban đầu của database và quan sát trực tiếp kết quả sau migration.

## 1. Mục tiêu của kiểm thử migration

Một bài kiểm thử migration tốt trả lời được các câu hỏi sau:

1. Khi database chưa có bảng nghiệp vụ, ứng dụng có khởi tạo được schema không?
2. Tất cả migration cần thiết có được thực thi theo thứ tự không?
3. Schema cuối cùng có đủ bảng, cột, kiểu dữ liệu, khóa, ràng buộc và index quan trọng không?
4. Khi nâng cấp từ một phiên bản schema cũ, dữ liệu hiện có có được giữ lại hoặc chuyển đổi đúng không?
5. Cấu hình ORM có đang che giấu lỗi migration bằng cách tự tạo hoặc sửa schema không?

Các câu hỏi này thuộc những mức kiểm thử khác nhau. Kiểm tra trạng thái migration giúp biết công cụ đã áp dụng những phiên bản nào; kiểm tra metadata hoặc truy vấn SQL giúp xác nhận cấu trúc thực tế; khởi tạo Spring ApplicationContext giúp kiểm tra toàn bộ quá trình tích hợp khi ứng dụng bắt đầu.

## 2. Migration và schema là gì?

Schema mô tả cấu trúc database mà ứng dụng sử dụng, ví dụ:

- Bảng và cột.
- Kiểu dữ liệu, độ dài và khả năng nhận giá trị NULL.
- Primary key và foreign key.
- Unique constraint, check constraint.
- Index và các quy tắc liên quan đến dữ liệu.

Migration là một thay đổi có thể quản lý và tái thực hiện theo lịch sử phiên bản. Ví dụ, một ứng dụng bắt đầu với bảng khách hàng, sau đó bổ sung trạng thái khách hàng:

~~~text
V1: tạo bảng customer
V2: thêm cột status vào customer
V3: tạo index cho customer.status
~~~

Khi database mới được tạo, công cụ migration áp dụng V1, V2 rồi V3. Khi database đã ở V2, công cụ chỉ cần áp dụng V3. Nhờ vậy, các môi trường phát triển, kiểm thử và triển khai có thể tiến đến cùng một trạng thái schema từ những điểm xuất phát khác nhau.

Migration thường được lưu trong source control cùng mã nguồn. Lịch sử migration là một phần của hợp đồng triển khai: cùng một tập migration phải tạo ra cùng một cấu trúc database trên các môi trường tương thích.

### Migration khác với việc tự tạo schema của ORM

Có ba cơ chế thường bị nhầm lẫn:

| Cơ chế | Vai trò | Phù hợp để làm gì |
|---|---|---|
| Flyway hoặc Liquibase | Quản lý thay đổi schema theo phiên bản | Tạo mới và nâng cấp database có kiểm soát |
| Hibernate DDL | Tạo, cập nhật hoặc kiểm tra schema từ mapping entity | Hỗ trợ phát triển và kiểm tra tương thích mapping |
| SQL initialization như schema.sql | Chạy các script khởi tạo theo cấu hình | Cơ sở dữ liệu đơn giản hoặc dữ liệu khởi tạo có phạm vi rõ ràng |

Nếu migration là nguồn sự thật của schema, không nên để Hibernate dùng chế độ tự cập nhật schema trong bài kiểm thử migration. Ví dụ, cấu hình Hibernate với **ddl-auto: update** có thể tạo cột còn thiếu và làm bài kiểm thử vẫn thành công dù migration chưa đầy đủ.

Trong môi trường kiểm thử tích hợp, có thể đặt:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

**validate** yêu cầu Hibernate kiểm tra mapping entity có tương thích với schema hiện tại hay không. Nó không chạy migration và không tự sửa schema. Đây là một lớp kiểm tra bổ sung hữu ích, nhưng không thay thế việc xác nhận migration.

Nếu dự án không dùng JPA/Hibernate, không cần cấu hình phần này. Khi dùng Flyway hoặc Liquibase làm chủ schema, cũng cần tránh cấu hình thêm một cơ chế SQL initialization khác để cùng tạo một bảng theo hai cách khác nhau.

## 3. Công cụ quản lý migration

Hai công cụ thường gặp trong ứng dụng Spring là Flyway và Liquibase. Chọn công cụ theo cách dự án đang quản lý database; một ứng dụng thông thường chỉ cần một công cụ làm chủ lịch sử migration.

### 3.1. Flyway

Flyway thường lưu migration dạng SQL hoặc Java. Với versioned SQL migration, tên file có dạng:

~~~text
src/main/resources/
└── db/
    └── migration/
        ├── V1__create_customer_table.sql
        ├── V2__add_customer_status.sql
        └── V3__index_customer_status.sql
~~~

Ví dụ nội dung migration đầu tiên:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
~~~

Migration tiếp theo:

~~~sql
ALTER TABLE customer
    ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE';
~~~

Flyway nhận diện migration dựa trên phiên bản và tên file. Khi chạy migration, Flyway ghi nhận lịch sử thực thi trong bảng metadata của nó, thường là **flyway_schema_history**. Bảng này giúp công cụ biết phiên bản nào đã chạy và kiểm tra checksum của migration.

Các nguyên tắc cần giữ:

- Migration versioned đã chạy trên một môi trường dùng chung cần được xem là bất biến.
- Khi cần đổi schema, tạo migration phiên bản mới thay vì sửa nội dung migration cũ.
- Phiên bản migration phải tăng theo thứ tự hợp lệ và không bị trùng.
- Migration cần có khả năng chạy trên database mục tiêu thực tế, bao gồm đúng dialect và phiên bản database.
- Không dùng lệnh xóa schema của Flyway trên database dùng chung chỉ để làm bài kiểm thử chạy lại.

Flyway còn hỗ trợ repeatable migration, thường dùng tiền tố **R__**. Loại migration này được chạy lại khi checksum thay đổi và phù hợp với một số đối tượng cần đồng bộ lại như view hoặc procedure. Nó có quy tắc vòng đời khác với versioned migration; không nên dùng repeatable migration để thay thế lịch sử nâng cấp schema thông thường.

### 3.2. Liquibase

Liquibase quản lý thay đổi qua changelog và các changeset. Changelog có thể được viết bằng YAML, XML, JSON hoặc SQL. Ví dụ rút gọn bằng YAML:

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
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(150)
                  constraints:
                    nullable: false
~~~

Liquibase ghi lại các changeset đã áp dụng trong các bảng lịch sử của nó, thường gồm **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK**. Changeset đã được áp dụng cũng cần được quản lý cẩn thận: thay đổi lịch sử có thể làm checksum không còn khớp hoặc khiến các môi trường có lịch sử khác nhau.

### 3.3. Kiểm tra lịch sử migration có ý nghĩa gì?

Lịch sử migration cho biết công cụ đã nhận diện và ghi nhận các thay đổi nào. Đây là bằng chứng cần thiết nhưng chưa đủ để xác nhận schema.

Ví dụ, lịch sử có thể cho thấy V1 và V2 đã chạy, nhưng bài kiểm thử vẫn cần xác nhận bảng và cột mà ứng dụng sử dụng thực sự tồn tại. Ngược lại, chỉ thấy bảng đã tồn tại cũng không chứng minh migration đã chạy: bảng đó có thể được tạo thủ công hoặc bởi Hibernate.

Do đó nên kết hợp hai loại bằng chứng:

- **Bằng chứng từ công cụ migration:** không còn migration đang chờ, lịch sử hợp lệ, checksum không sai lệch.
- **Bằng chứng từ database:** bảng, cột, constraint và index cần thiết thực sự hiện diện.

## 4. Spring tích hợp migration khi khởi tạo ứng dụng

### 4.1. Với Spring Boot

Khi có dependency Flyway hoặc Liquibase phù hợp trên classpath và cấu hình datasource hợp lệ, Spring Boot có thể tự cấu hình công cụ migration. Trong quá trình khởi tạo ApplicationContext, migration được thực thi trước khi các thành phần phụ thuộc vào schema cần sử dụng database.

Ví dụ cấu hình Flyway:

~~~yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Với Liquibase:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Đường dẫn changelog hoặc migration phải khớp với tài nguyên thực tế trong ứng dụng. Nếu dùng profile kiểm thử, hãy kiểm tra cấu hình profile đó có vô tình tắt migration hoặc trỏ sang một vị trí khác không.

Một bài kiểm thử sử dụng **@SpringBootTest** sẽ khởi tạo context theo cấu hình ứng dụng. Nếu migration thất bại trong quá trình khởi động, bài kiểm thử thường thất bại ngay khi Spring tạo các bean phụ thuộc vào database. Đây là tín hiệu quan trọng để phát hiện lỗi tích hợp.

### 4.2. Với Spring Framework không dùng Spring Boot

Spring TestContext có thể tạo ApplicationContext thông qua **@ContextConfiguration** hoặc **@SpringJUnitConfig**. Tuy nhiên, việc dùng Spring Framework Testing tự nó không đồng nghĩa Flyway hay Liquibase sẽ tự chạy.

Ứng dụng cần đăng ký và cấu hình bean migration tương ứng, cung cấp datasource, changelog hoặc vị trí migration, đồng thời bảo đảm migration hoàn tất trước khi khởi tạo repository, ORM hoặc thành phần cần truy cập schema.

Khi viết bài kiểm thử cho cấu hình Spring thuần, cần xác định rõ bean nào chịu trách nhiệm chạy migration và vòng đời bean đó. Không nên giả định hành vi tự động của Spring Boot xuất hiện trong một ApplicationContext chỉ dùng Spring Framework.

## 5. Thiết kế môi trường kiểm thử có thể lặp lại

Điều kiện quan trọng nhất là biết chính xác trạng thái database trước khi test.

### 5.1. Ưu tiên database dùng riêng cho bài kiểm thử

Có thể dùng database tạm thời trong container hoặc một database kiểm thử được tạo riêng cho từng lượt chạy. Mỗi lượt kiểm thử migration nên bắt đầu từ trạng thái xác định, thường là database rỗng.

Không chạy migration test trên database dùng chung với dữ liệu phát triển hoặc dữ liệu thật. Việc reset schema, xóa bảng hoặc chạy lệnh clean trên một database dùng chung có thể làm mất dữ liệu của người khác.

### 5.2. Chọn đúng loại database

H2 hoặc một database nhúng có thể giúp test nhanh, nhưng SQL migration có thể phụ thuộc vào dialect của PostgreSQL, MySQL hoặc một hệ quản trị khác. Một migration chạy được trên H2 chưa chắc chạy được trên database triển khai.

Nếu migration sử dụng cú pháp, kiểu dữ liệu, sequence, function, JSON, index hoặc constraint đặc thù của database, hãy chạy kiểm thử tích hợp với đúng engine. Testcontainers là một cách phổ biến để tạo database thật trong container cho thời gian kiểm thử.

### 5.3. Không để dữ liệu cũ che giấu lỗi

Một database đã có schema từ lần chạy trước có thể khiến test không phát hiện migration khởi tạo bị thiếu. Hãy bảo đảm database của test thực sự mới, hoặc chủ động tạo một trạng thái phiên bản cũ khi kiểm tra nâng cấp.

Cần phân biệt:

- Test khởi tạo mới: database bắt đầu không có schema nghiệp vụ.
- Test nâng cấp: database bắt đầu ở một phiên bản migration đã xác định và có thể chứa dữ liệu cũ.
- Test repository: database có schema hợp lệ và dữ liệu phục vụ kịch bản truy vấn.

Ba mục tiêu này có thể dùng chung hạ tầng nhưng cần trạng thái đầu vào khác nhau.

## 6. Ví dụ kiểm thử migration với PostgreSQL và Testcontainers

Ví dụ sau minh họa bài kiểm thử Spring Boot khởi động trên một PostgreSQL container mới, sau đó xác nhận Flyway đã áp dụng migration và bảng nghiệp vụ tồn tại.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DatabaseMigrationIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    Flyway flyway;

    @Test
    void appliesMigrationsAndCreatesExpectedSchema() {
        // Không còn migration nào đang chờ áp dụng.
        assertThat(flyway.info().pending()).isEmpty();

        // Có migration hiện hành trong lịch sử.
        assertThat(flyway.info().current()).isNotNull();

        // Bảng nghiệp vụ được tạo trên database mới.
        Integer tableCount = jdbcTemplate.queryForObject("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'customer'
                """, Integer.class);

        assertThat(tableCount).isEqualTo(1);
    }

    @Test
    void createsRequiredColumns() {
        var columns = jdbcTemplate.queryForList("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'customer'
                """, String.class);

        assertThat(columns)
                .contains("id", "name", "status");
    }
}
~~~

Ví dụ giả định dự án đã có dependency test phù hợp, driver PostgreSQL, Flyway và các migration tạo bảng **customer** với những cột được kiểm tra. Container được tạo mới nên test không phụ thuộc vào database phát triển đang có sẵn.

**@DynamicPropertySource** đăng ký URL, username và password của container vào cấu hình Spring trước khi context được tạo. Nhờ vậy, datasource mà Spring Boot sử dụng trỏ đến database do test sở hữu.

Hai test trong ví dụ có mục đích khác nhau:

- Test thứ nhất kiểm tra trạng thái migration và xác nhận bảng đã tồn tại.
- Test thứ hai kiểm tra các cột mà ứng dụng mong đợi.

Trong dự án thực tế, nên kiểm tra thêm kiểu dữ liệu, khả năng NULL, khóa ngoại, unique constraint hoặc index nếu chúng là một phần quan trọng của hợp đồng dữ liệu.

Lưu ý: tên schema và cách truy vấn metadata có thể khác nhau giữa các hệ quản trị. Trên PostgreSQL, **current_schema()** trả về schema hiện hành của kết nối. Nếu ứng dụng đặt bảng trong schema riêng, hãy cấu hình search path hoặc chỉ rõ schema tương ứng trong truy vấn.

## 7. Kiểm tra nâng cấp từ schema cũ

Kiểm tra database rỗng chứng minh chuỗi migration có thể tạo schema mới. Nó chưa chứng minh quá trình nâng cấp giữ được dữ liệu đang tồn tại.

Giả sử:

- V1 tạo bảng customer với id và name.
- V2 thêm status với giá trị mặc định ACTIVE.
- Database của người dùng đã chạy V1 và có một số bản ghi.
- Khi triển khai phiên bản mới, V2 phải được áp dụng mà không làm mất bản ghi cũ.

Bài kiểm thử nâng cấp có thể thực hiện theo trình tự:

1. Tạo database riêng.
2. Dùng Flyway giới hạn migration đến phiên bản V1.
3. Chèn một bản ghi theo cấu trúc V1.
4. Chạy Flyway không giới hạn phiên bản để áp dụng các migration còn lại.
5. Đọc lại bản ghi và xác nhận cột mới có giá trị mong đợi.

Ví dụ phần thiết lập hai giai đoạn với Flyway:

~~~java
Flyway.configure()
        .dataSource(jdbcUrl, username, password)
        .locations("classpath:db/migration")
        .target("1")
        .load()
        .migrate();

// Ở thời điểm này database đang ở schema V1.
jdbcTemplate.update(
        "INSERT INTO customer (id, name) VALUES (?, ?)",
        100L,
        "An"
);

// Chạy các migration còn lại để nâng cấp đến phiên bản mới nhất.
Flyway.configure()
        .dataSource(jdbcUrl, username, password)
        .locations("classpath:db/migration")
        .load()
        .migrate();
~~~

Sau đó xác nhận dữ liệu:

~~~java
String status = jdbcTemplate.queryForObject(
        "SELECT status FROM customer WHERE id = ?",
        String.class,
        100L
);

assertThat(status).isEqualTo("ACTIVE");
~~~

Đây là ví dụ rút gọn: **jdbcTemplate**, **jdbcUrl**, **username** và **password** phải được lấy từ database test riêng. Nếu migration V2 chuyển đổi dữ liệu thay vì chỉ thêm cột mặc định, hãy chèn dữ liệu đại diện cho trạng thái cũ rồi xác nhận kết quả chuyển đổi chính xác.

Với Liquibase, có thể thiết lập database đến một tag hoặc trạng thái changeset cũ, tạo dữ liệu tại trạng thái đó rồi chạy update đến changelog hiện hành. Cách cụ thể phụ thuộc vào cách dự án tổ chức changelog và đánh dấu phiên bản.

### Những gì cần xác nhận sau khi nâng cấp

Không chỉ kiểm tra rằng migration không ném exception. Hãy xác nhận:

- Bản ghi cũ vẫn tồn tại nếu yêu cầu nghiệp vụ là giữ dữ liệu.
- Giá trị mới được gán đúng cho dữ liệu cũ.
- Kiểu dữ liệu hoặc định dạng được chuyển đổi đúng.
- Constraint mới không làm hỏng dữ liệu hợp lệ.
- Các truy vấn của ứng dụng vẫn đọc được dữ liệu sau nâng cấp.

Một migration có thể chạy thành công nhưng tạo ra kết quả dữ liệu sai. Vì thế, kiểm tra dữ liệu sau nâng cấp là một phần của kiểm thử migration.

## 8. Xác nhận schema ở mức cấu trúc

Bảng tồn tại chỉ là điều kiện ban đầu. Schema cần được xác nhận theo các yêu cầu mà ứng dụng phụ thuộc.

### 8.1. Bảng và cột

Dùng metadata của JDBC hoặc các view chuẩn như **information_schema** để kiểm tra tên bảng và cột. Truy vấn metadata thường dễ đọc và ít phụ thuộc vào chi tiết nội bộ của công cụ migration.

Ví dụ kiểm tra cột:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'customer';
~~~

Có thể xác nhận cột bắt buộc phải tồn tại, kiểu dữ liệu phù hợp và cột không cho phép NULL nếu hợp đồng yêu cầu.

### 8.2. Primary key và foreign key

Kiểm tra khóa giúp phát hiện migration tạo bảng nhưng thiếu quan hệ hoặc ràng buộc quan trọng. Với PostgreSQL, có thể xem metadata constraint qua **information_schema.table_constraints**, **key_column_usage** và **constraint_column_usage**.

Ví dụ xác nhận bảng có primary key:

~~~sql
SELECT COUNT(*)
FROM information_schema.table_constraints
WHERE table_schema = current_schema()
  AND table_name = 'customer'
  AND constraint_type = 'PRIMARY KEY';
~~~

Kết quả mong đợi thường là một primary key cho bảng này. Nếu thiết kế cho phép khóa ghép, cần kiểm tra cả tập cột tham gia khóa thay vì chỉ đếm constraint.

### 8.3. Unique constraint và check constraint

Unique constraint bảo đảm dữ liệu không trùng theo quy tắc nghiệp vụ. Check constraint bảo đảm giá trị nằm trong miền cho phép.

Ngoài kiểm tra metadata, có thể thực hiện một thao tác ghi dữ liệu có chủ đích để xác nhận database thực thi constraint. Ví dụ, chèn hai bản ghi có cùng email nếu email phải duy nhất; lần ghi thứ hai cần thất bại với lỗi constraint tương ứng.

Bài kiểm thử kiểu này cần chạy trong transaction hoặc database cô lập để dữ liệu kiểm tra không ảnh hưởng các test khác.

### 8.4. Index

Index có thể quan trọng với hiệu năng hoặc yêu cầu kỹ thuật. Kiểm tra index cần xác định rõ:

- Index thuộc bảng nào.
- Index bao gồm những cột nào.
- Thứ tự cột trong index ghép.
- Index có unique hay không.
- Index có predicate hoặc điều kiện đặc biệt hay không.

Tên index tồn tại chưa chắc chứng minh định nghĩa đúng. Với PostgreSQL có thể truy vấn **pg_indexes** hoặc metadata hệ thống tương ứng để kiểm tra định nghĩa. Các truy vấn này mang tính đặc thù database, nên đặt trong test dành riêng cho engine đó.

Không nên kiểm tra mọi index một cách máy móc. Chỉ nên xác nhận những index có ý nghĩa với hợp đồng schema, tính toàn vẹn dữ liệu hoặc truy vấn quan trọng.

## 9. Phân biệt migration test và repository test

Migration test tập trung vào khả năng tạo và nâng cấp schema. Repository test tập trung vào hành vi truy cập dữ liệu trên schema đã có.

Ví dụ:

| Loại test | Trọng tâm | Bằng chứng |
|---|---|---|
| Migration từ database rỗng | Tạo schema mới | Migration thành công, bảng và cột tồn tại |
| Migration nâng cấp | Chuyển phiên bản schema | Dữ liệu cũ được giữ hoặc chuyển đổi đúng |
| Schema contract | Cấu trúc database | Kiểu cột, khóa, constraint, index |
| Repository integration | Truy vấn và ghi dữ liệu | Kết quả truy vấn, mapping và transaction |
| Spring context startup | Tích hợp cấu hình ứng dụng | ApplicationContext khởi tạo thành công với database mới |

Có thể dùng chung PostgreSQL Testcontainer cho nhiều test, nhưng phải quản lý vòng đời và trạng thái database rõ ràng. Nếu Spring TestContext cache ApplicationContext, datasource trong context có thể tiếp tục giữ kết nối đến container. Cấu hình container và context phải có vòng đời tương thích để tránh test sau dùng một datasource trỏ đến container đã dừng.

Đối với **@DataJpaTest**, cần nhớ đây là test slice dành cho JPA. Cấu hình mặc định có thể thay datasource bằng database nhúng nếu có sẵn. Nếu mục tiêu là kiểm tra migration trên PostgreSQL container, hãy cấu hình để test slice giữ datasource đã cung cấp, ví dụ dùng **@AutoConfigureTestDatabase(replace = Replace.NONE)** khi phù hợp. Nếu cần kiểm tra toàn bộ quá trình khởi động ứng dụng, **@SpringBootTest** thường thể hiện mục tiêu rõ hơn.

## 10. Những lỗi thường gặp và cách điều tra

### Migration không được tìm thấy

Dấu hiệu là ứng dụng khởi động nhưng bảng không xuất hiện, hoặc công cụ báo không có migration cần chạy.

Kiểm tra:

- File có nằm đúng thư mục migration hoặc changelog không?
- Tên file có đúng quy ước của Flyway không?
- Resource có được đóng gói vào classpath không?
- Profile test có ghi đè vị trí migration không?
- Cấu hình có vô tình tắt Flyway hoặc Liquibase không?

### Database test không phải database dự kiến

Test có thể kết nối vào database mặc định, database nhúng hoặc một datasource khác với container.

Kiểm tra URL, username, profile, datasource bean và các thuộc tính được ghi đè trong **@DynamicPropertySource**. Đừng kết luận migration đúng chỉ dựa trên việc ứng dụng khởi động.

### Hibernate tạo bảng thay migration

Nếu Hibernate dùng **create**, **create-drop** hoặc **update**, bảng có thể xuất hiện dù migration thiếu hoặc sai.

Đặt cấu hình ORM phù hợp với chiến lược quản lý schema. Khi migration là nguồn sự thật, thường dùng **validate** để kiểm tra mapping mà không tự sửa cấu trúc.

### Checksum không khớp

Lỗi checksum thường xuất hiện khi nội dung migration đã được áp dụng bị sửa sau đó.

Không nên xử lý bằng cách tùy tiện xóa lịch sử hoặc sửa checksum trong database. Trước hết xác định migration đã chạy ở môi trường nào, nội dung ban đầu là gì và vì sao file bị thay đổi. Với versioned migration đã phát hành, cách sửa thông thường là tạo migration mới.

### Migration thành công trên H2 nhưng thất bại trên database triển khai

Nguyên nhân thường nằm ở khác biệt dialect, kiểu dữ liệu, cú pháp SQL, sequence, function hoặc constraint.

Chạy migration test với cùng loại database và phiên bản tương thích với môi trường mục tiêu. H2 có thể tiếp tục hữu ích cho các test không phụ thuộc tính năng đặc thù, nhưng không nên là bằng chứng duy nhất cho migration PostgreSQL hoặc MySQL.

### Test chạy được khi chạy riêng nhưng thất bại khi chạy cả bộ

Nguyên nhân có thể là các test dùng chung schema, thứ tự chạy, dữ liệu còn sót hoặc transaction không được rollback như kỳ vọng.

Mỗi test cần có dữ liệu đầu vào xác định. Với migration test, database cô lập theo class hoặc theo test giúp tránh trạng thái do test trước để lại. Không dùng một database dùng chung rồi dựa vào thứ tự test để có schema đúng.

### Migration có chạy nhưng dữ liệu sau nâng cấp sai

Kiểm tra riêng phần chuyển đổi dữ liệu. Hãy tạo dữ liệu đầu vào đại diện cho trạng thái cũ, chạy migration, rồi xác nhận từng trường hợp quan trọng: giá trị NULL, dữ liệu trùng, chuỗi rỗng, giá trị ngoài miền và bản ghi liên quan qua khóa ngoại.

## 11. Tổ chức bài kiểm thử trong dự án

Một bộ kiểm thử rõ ràng có thể tách theo mục tiêu:

~~~text
src/test/
└── java/
    └── .../
        ├── DatabaseMigrationIT.java
        ├── DatabaseUpgradeIT.java
        ├── DatabaseSchemaContractIT.java
        └── CustomerRepositoryIT.java
~~~

Đây là cách phân chia theo trách nhiệm, không phải yêu cầu phải tạo đủ bốn class trong mọi dự án.

- **DatabaseMigrationIT:** khởi tạo database mới và xác nhận migration chạy hết.
- **DatabaseUpgradeIT:** tạo schema ở phiên bản cũ, thêm dữ liệu cũ và kiểm tra nâng cấp.
- **DatabaseSchemaContractIT:** kiểm tra các cấu trúc quan trọng như khóa, constraint và index.
- **CustomerRepositoryIT:** kiểm tra truy vấn và ghi dữ liệu của repository.

Nếu bộ kiểm thử nhỏ, các kiểm tra có thể nằm trong ít class hơn. Điều quan trọng là tên test và dữ liệu đầu vào thể hiện đúng mục tiêu, để khi lỗi xảy ra có thể xác định lỗi thuộc khởi tạo schema, nâng cấp hay truy cập dữ liệu.

Trong CI, migration test nên chạy như một phần của kiểm thử tích hợp. Database test phải được tạo và hủy có kiểm soát. Kết quả test cần làm rõ migration nào thất bại và lỗi gốc đến từ SQL, kết nối, quyền truy cập hay cấu hình Spring.

## 12. Nguyên tắc thực hành

Khi xây dựng kiểm thử migration và schema, hãy áp dụng các nguyên tắc sau:

1. Dùng database mới hoặc trạng thái đầu vào được kiểm soát.
2. Để công cụ migration thực sự chạy trong quá trình khởi tạo Spring.
3. Không cho Hibernate tự sửa schema khi mục tiêu là kiểm tra migration.
4. Kiểm tra cả lịch sử migration và cấu trúc database thực tế.
5. Kiểm tra nâng cấp từ phiên bản cũ nếu ứng dụng cần bảo toàn dữ liệu đã triển khai.
6. Dùng đúng hệ quản trị database khi migration phụ thuộc dialect hoặc tính năng riêng.
7. Xác nhận dữ liệu sau migration, đặc biệt với thay đổi có chuyển đổi dữ liệu.
8. Không chạy lệnh xóa/reset schema trên database dùng chung.
9. Tách lỗi migration khỏi lỗi repository để việc điều tra rõ ràng.
10. Giữ migration đã áp dụng bất biến và sửa schema bằng migration mới.

Một migration được xem là đáng tin cậy khi nó có thể khởi tạo database mới, nâng cấp database cũ theo đúng quy tắc và để lại schema cùng dữ liệu phù hợp với yêu cầu ứng dụng. Bài kiểm thử cần tạo được bằng chứng cho cả ba điều đó, thay vì chỉ xác nhận rằng Spring ApplicationContext đã khởi động thành công.

