# Sinh Liquibase change set bằng LiquibaseChangeSetWriter trong Spring Data JDBC

## 1. Vai trò của LiquibaseChangeSetWriter

Spring Data JDBC cung cấp LiquibaseChangeSetWriter để tạo Liquibase change set từ metadata mapping của các aggregate. Class nằm trong package:

~~~java
org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter
~~~

Writer đọc MappingContext để xác định các entity được ánh xạ và cấu trúc bảng/cột tương ứng. Nó hỗ trợ hai chế độ:

1. **Initial schema creation:** tạo change set mô tả schema ban đầu cho database trống.
2. **Differential schema change creation:** so sánh schema mong muốn từ entity mapping với schema hiện có của một Liquibase Database rồi tạo change set mô tả phần khác biệt.

Writer tạo changelog để nhóm phát triển xem xét và quản lý bằng Liquibase. Nó không tự áp dụng migration vào database. Việc sinh file và việc thực thi migration là hai bước riêng biệt.

LiquibaseChangeSetWriter được bổ sung từ Spring Data Relational 3.2. Khi dùng phiên bản cũ hơn, cần kiểm tra API tương ứng vì class hoặc method có thể chưa tồn tại.

Tài liệu API: https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/schema/LiquibaseChangeSetWriter.html

## 2. Cách writer lấy schema từ domain model

Spring Data JDBC sử dụng RelationalMappingContext để lưu metadata về aggregate và relational mapping. Metadata này bao gồm thông tin như:

- Kiểu aggregate root và entity được ánh xạ.
- Tên bảng từ @Table hoặc quy tắc đặt tên mặc định.
- Tên cột từ property và @Column.
- Identifier từ @Id.
- Kiểu Java của property để suy ra kiểu SQL.
- Các thông tin mapping relational khác mà schema writer hỗ trợ.

Writer không quét toàn bộ source code Java để tự tìm mọi class. Nó sử dụng các entity đã có trong MappingContext. Mapping context thường được khởi tạo lười; khi tạo schema, cần bảo đảm các aggregate root mong muốn đã được đăng ký vào context.

Ví dụ entity:

~~~java
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String code;

    private String displayName;

    private LocalDate birthday;

    private boolean active;
}
~~~

Writer có thể suy ra bảng customers với các cột như id, customer_code, display_name, birthday và active. Kiểu SQL cụ thể phụ thuộc SqlTypeMapping và database/dialect mà ứng dụng hướng tới.

### 2.1. Đăng ký aggregate root

Nếu context chưa biết aggregate root, hãy đăng ký tập entity cần sinh schema:

~~~java
import java.util.Set;

import org.springframework.data.relational.core.mapping.RelationalMappingContext;

mappingContext.setInitialEntitySet(Set.of(
        Customer.class,
        PurchaseOrder.class,
        Product.class
));
~~~

Hãy đưa vào tập này các aggregate root thực sự thuộc schema cần quản lý. Nếu chỉ đăng ký Customer.class, writer không thể tự suy ra những aggregate độc lập khác mà context chưa biết.

Nếu ứng dụng đã cấu hình mapping context với tập entity ban đầu, hãy bảo đảm tập đó bao phủ đúng các aggregate cần đưa vào changelog. Không đưa class DTO, projection hoặc object chỉ dùng trong tầng service vào schema nếu chúng không phải relational entity.

## 3. Dependency cần thiết

LiquibaseChangeSetWriter tích hợp với Liquibase, do đó project cần dependency liquibase-core.

Gradle, nếu chỉ dùng writer trong test để sinh changelog:

~~~groovy
dependencies {
    testImplementation("org.liquibase:liquibase-core")
}
~~~

Nếu ứng dụng cũng thực thi Liquibase migration khi khởi động, dependency cần có ở runtime, thường dùng implementation hoặc cấu hình phù hợp với convention của project:

~~~groovy
dependencies {
    implementation("org.liquibase:liquibase-core")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
~~~

Khi dùng Spring Boot dependency management, để BOM quản lý version tương thích thay vì tự chọn một version Liquibase tùy ý. Đảm bảo phiên bản Spring Data JDBC và Liquibase trong project tương thích.

## 4. Sinh change set cho schema ban đầu

Chế độ initial phù hợp khi bắt đầu project hoặc cần tạo schema cho database trống. Constructor nhận một MappingContext, sau đó gọi writeChangeSet(Resource).

Ví dụ dùng trong test:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.data.relational.core.mapping.RelationalMappingContext;
import org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter;

@SpringBootTest(properties = "spring.liquibase.enabled=false")
class SchemaGenerationTest {

    @Autowired
    RelationalMappingContext mappingContext;

    @Test
    void generateInitialSchema() throws IOException {
        mappingContext.setInitialEntitySet(Set.of(
                Customer.class,
                PurchaseOrder.class
        ));

        LiquibaseChangeSetWriter writer =
                new LiquibaseChangeSetWriter(mappingContext);

        Path output = Path.of(
                "build/generated/liquibase/initial-schema.yaml"
        );

        Files.createDirectories(output.getParent());

        // Dùng file generated riêng; writer có thể append vào file có sẵn.
        Files.deleteIfExists(output);
        Files.createFile(output);

        writer.writeChangeSet(
                new FileSystemResource(output.toFile())
        );
    }
}
~~~

Trong ví dụ, spring.liquibase.enabled=false chỉ ngăn Spring Boot tự chạy Liquibase trong context dùng để sinh changelog. Đây là cấu hình phù hợp cho generator test khi chưa có changelog runtime. Khi ứng dụng thực sự cần chạy migration, hãy cấu hình Liquibase theo changelog đã được review và bật lại việc thực thi migration trong môi trường tương ứng.

### 4.1. Vì sao nên chạy việc sinh schema trong test?

Tạo schema là công việc phát triển và review. Đặt code generator trong test giúp:

- Tận dụng cấu hình mapping và custom conversions của ứng dụng.
- Tránh sinh migration ngoài ý muốn khi application khởi động.
- Tạo file ở thư mục build hoặc thư mục generated riêng.
- Dễ chạy lại khi domain model thay đổi.
- Không trộn thao tác sinh file với thao tác triển khai migration.

Tài liệu Spring khuyến nghị đặt logic sinh schema trong test để tránh việc nó chạy ngoài ý muốn trong production.

Tham khảo: https://spring.io/blog/2023/08/29/spring-data-jdbc-how-to-maintain-your-database-schema/

## 5. Đọc output YAML được sinh

Output là Liquibase changelog. Ví dụ rút gọn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "..."
      author: Spring Data Relational
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_code
                  type: VARCHAR(255)
              - column:
                  name: display_name
                  type: VARCHAR(255)
              - column:
                  name: birthday
                  type: DATE
              - column:
                  name: active
                  type: TINYINT
~~~

Đây là ví dụ minh họa cấu trúc; kiểu SQL, nullability, quoting và các thuộc tính cụ thể phụ thuộc mapping, SQL type mapping và database.

Một số điều cần kiểm tra trong output:

- Tên bảng và cột có khớp naming strategy mong muốn không?
- Kiểu SQL có phù hợp database đích không?
- Identifier có được khai báo primary key đúng không?
- Cột nào nullable và cột nào bắt buộc?
- Cột ID có tự tăng hay dùng cơ chế sinh ID khác?
- Tên schema, quoting và kiểu dữ liệu có phù hợp môi trường triển khai không?

Không nên xem YAML được sinh là schema hoàn chỉnh đã được phê duyệt. Hãy review trước khi đưa vào changelog chính thức.

## 6. Sinh change set khác biệt với database hiện tại

Khi project đã có schema và domain model thay đổi, có thể tạo differential change set. Chế độ này cần một Liquibase Database đại diện cho database hiện tại.

Luồng xử lý:

1. Khởi tạo mapping context với aggregate root mong muốn.
2. Tạo LiquibaseChangeSetWriter.
3. Mở JDBC connection tới database cần so sánh.
4. Tạo Liquibase Database phù hợp với JDBC connection.
5. Gọi writeChangeSet(resource, database).
6. Review changelog sinh ra trước khi dùng.

Ví dụ với Liquibase DatabaseFactory:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;

import javax.sql.DataSource;

import liquibase.database.Database;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;

import org.springframework.core.io.FileSystemResource;
import org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter;

public void generateDiff(
        RelationalMappingContext mappingContext,
        DataSource dataSource
) throws Exception {

    LiquibaseChangeSetWriter writer =
            new LiquibaseChangeSetWriter(mappingContext);

    Path output = Path.of(
            "build/generated/liquibase/schema-diff.yaml"
    );

    Files.createDirectories(output.getParent());
    Files.deleteIfExists(output);
    Files.createFile(output);

    Connection connection = dataSource.getConnection();

    Database database = DatabaseFactory.getInstance()
            .findCorrectDatabaseImplementation(
                    new JdbcConnection(connection)
            );

    try (database) {
        writer.writeChangeSet(
                new FileSystemResource(output.toFile()),
                database
        );
    }
}
~~~

DatabaseFactory nhận JDBC connection và chọn implementation Liquibase phù hợp với database thực tế. Nếu dùng database wrapper hoặc cấu hình đặc biệt, hãy tạo Database theo cách tương ứng với hệ quản trị đang chạy.

Trong ví dụ, Liquibase Database sở hữu connection được gắn vào nó và được đóng sau khi writer hoàn tất. Nếu quá trình tạo Database thất bại trước khi vào try-with-resources, cần đóng JDBC connection trong nhánh xử lý lỗi tương ứng để tránh rò rỉ connection.

Không dùng một implementation database giả định như HsqlDatabase khi DataSource thực tế kết nối PostgreSQL, MySQL hoặc hệ quản trị khác. Schema comparison phải đọc đúng database mà ứng dụng muốn đối chiếu.

### 6.1. Writer so sánh những gì?

Differential mode dùng schema hiện tại từ Liquibase Database và schema mong muốn từ mapped entities. Nó có thể tạo thay đổi để:

- Tạo bảng chưa tồn tại trong schema hiện tại.
- Thêm cột chưa tồn tại.
- Xóa bảng không còn nằm trong schema mong muốn nếu drop-table filter cho phép.
- Xóa cột không còn nằm trong schema mong muốn nếu drop-column filter cho phép.

Tên bảng và cột trong differential mode được so sánh không phân biệt hoa thường theo comparator mà API mô tả. Tuy nhiên, hãy duy trì naming convention nhất quán; không dựa vào việc so sánh case-insensitive để che giấu khác biệt naming giữa môi trường.

## 7. Kiểm soát việc xóa bằng drop filters

Điểm an toàn quan trọng: mặc định writer không xóa bảng hoặc cột. Các filter drop mặc định loại trừ tất cả bảng/cột khỏi việc xóa.

Có thể cấu hình:

~~~java
writer.setDropTableFilter(tableName ->
        tableName.equalsIgnoreCase("obsolete_import_staging")
);

writer.setDropColumnFilter((tableName, columnName) ->
        tableName.equalsIgnoreCase("legacy_customers")
                && columnName.equalsIgnoreCase("unused_code")
);
~~~

Predicate trả về true nghĩa là cho phép xóa bảng hoặc cột được truyền vào; false nghĩa là giữ lại.

Không bật filter kiểu “xóa tất cả bảng/cột không được mapping” nếu chưa hiểu đầy đủ schema thực tế. Một bảng có thể được dùng bởi báo cáo, stored procedure, hệ thống tích hợp hoặc một service khác dù không xuất hiện trong entity mapping hiện tại.

### 7.1. Schema filter khác drop filters

setSchemaFilter quyết định entity nào được đưa vào schema mong muốn:

~~~java
writer.setSchemaFilter(entity ->
        entity.getType() != LegacyReadModel.class
);
~~~

Trả về true nghĩa là bao gồm entity; false nghĩa là loại entity khỏi schema được sinh.

Trong differential mode, một bảng hiện có nhưng bị loại khỏi schema filter có thể được xem là không còn thuộc schema mong muốn. Tuy nhiên, bảng đó chỉ bị xóa nếu drop-table filter cho phép. Hai loại filter có vai trò khác nhau:

| Filter | Câu hỏi nó trả lời |
|---|---|
| Schema filter | Entity nào được xem là một phần của schema mong muốn? |
| Drop-table filter | Bảng hiện có nào được phép xóa? |
| Drop-column filter | Cột hiện có nào được phép xóa? |

Nếu chỉ muốn bỏ qua một entity khi sinh initial schema, schema filter có thể đủ. Nếu tạo diff, cần cân nhắc riêng tác động của entity bị loại đối với bảng hiện có.

## 8. Tùy chỉnh kiểu SQL bằng SqlTypeMapping

Writer dùng strategy SqlTypeMapping để chuyển Java property type thành kiểu dữ liệu database. Mặc định là DefaultSqlTypeMapping.

Nếu cần kiểu riêng, có thể cung cấp strategy tùy chỉnh và kết hợp với default mapping:

~~~java
import org.springframework.data.jdbc.core.mapping.schema.DefaultSqlTypeMapping;
import org.springframework.data.jdbc.core.mapping.schema.SqlTypeMapping;

writer.setSqlTypeMapping(((SqlTypeMapping) property -> {
    if (property.getType() == String.class
            && property.getName().equals("displayName")) {
        return "VARCHAR(500)";
    }

    return null;
}).and(new DefaultSqlTypeMapping()));
~~~

Ví dụ trên đặt cột của property displayName thành VARCHAR(500). Với các property khác, strategy trả về null để DefaultSqlTypeMapping xử lý.

Nên đặt quy tắc theo metadata có ý nghĩa, chẳng hạn annotation domain hoặc property cụ thể, thay vì chỉ đổi mọi property String. Nếu cần nhiều kiểu tùy chỉnh, tạo annotation riêng và đọc annotation từ RelationalPersistentProperty.

### 8.1. Dùng annotation để mô tả kiểu dữ liệu

Ví dụ annotation:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface VarcharLength {
    int value();
}
~~~

Đánh dấu property:

~~~java
@VarcharLength(500)
private String displayName;
~~~

Strategy có thể đọc annotation:

~~~java
writer.setSqlTypeMapping(((SqlTypeMapping) property -> {
    VarcharLength length =
            property.findAnnotation(VarcharLength.class);

    if (property.getType() == String.class && length != null) {
        return "VARCHAR(" + length.value() + ")";
    }

    return null;
}).and(new DefaultSqlTypeMapping()));
~~~

Kiểu SQL phải hợp lệ trên database mục tiêu. Nếu ứng dụng hỗ trợ nhiều database, strategy nên phân biệt dialect hoặc dùng mapping riêng cho từng môi trường.

## 9. Tùy chỉnh serializer và parser

Liquibase hỗ trợ nhiều định dạng changelog. LiquibaseChangeSetWriter mặc định dùng YAML serializer/parser và cho phép thay bằng implementation khác:

~~~java
writer.setChangeLogSerializer(customSerializer);
writer.setChangeLogParser(customParser);
~~~

Chỉ cần thay serializer/parser khi project có yêu cầu định dạng hoặc cách đọc changelog riêng. Nếu dùng YAML mặc định, không cần cấu hình thêm.

Hãy bảo đảm parser và serializer tương thích với định dạng changelog hiện có. Một file changelog có cấu trúc không tương thích có thể khiến việc đọc, append hoặc thực thi migration thất bại.

## 10. Resource đầu ra và hành vi append

Các method writeChangeSet nhận Spring Resource. API yêu cầu resource phải resolve được thành file hợp lệ qua Resource.getFile(). Vì vậy, FileSystemResource là lựa chọn rõ ràng khi sinh file local.

Ví dụ:

~~~java
Resource output = new FileSystemResource(
        new File("build/generated/liquibase/initial-schema.yaml")
);

writer.writeChangeSet(output);
~~~

Javadoc ghi rõ writer ghi changelog vào resource và có thể append vào file change set đã tồn tại. Vì vậy:

- Tạo file generated riêng cho mỗi lần chạy nếu muốn output sạch.
- Tạo thư mục cha trước khi ghi.
- Không trỏ generator vào changelog production đang được quản lý thủ công.
- Không chạy lặp nhiều lần trên cùng file mà không hiểu hành vi append.
- Không dùng resource nằm trong JAR hoặc một classpath resource không thể resolve thành file vật lý.

Đối với project thực tế, nên sinh file vào thư mục build/generated hoặc một thư mục tạm. Sau khi review, đưa changelog đã duyệt vào vị trí migration được version control quản lý.

## 11. Những gì schema writer không thể tự suy luận

Entity mapping mô tả trạng thái schema mong muốn hiện tại. Nó không lưu đầy đủ lịch sử schema trước đó và ý nghĩa nghiệp vụ của từng lần thay đổi.

Vì vậy, không thể chỉ nhìn hai phiên bản entity mà tự động biết mọi migration cần thiết.

Một số giới hạn quan trọng:

- Không thể suy ra ý định đổi tên cột; một cột cũ biến mất và một cột mới xuất hiện không chứng minh đó là rename.
- Không thể tự tạo data migration, ví dụ chuyển đổi giá trị hoặc ghép dữ liệu từ cột cũ sang cột mới.
- Không thể biết cách chuyển đổi dữ liệu an toàn khi kiểu cột thay đổi.
- Tài liệu schema generation nêu rằng relational references hiện không được hỗ trợ và có thể bị bỏ qua; hãy kiểm tra phiên bản đang dùng và bổ sung quan hệ cần thiết bằng Liquibase change set thủ công.
- Các thành phần như index, constraint nghiệp vụ, trigger, view hoặc stored procedure cần được kiểm tra trong output và bổ sung thủ công nếu writer không mô tả chúng theo yêu cầu ứng dụng.

Ví dụ đổi tên cột:

~~~text
Phiên bản cũ: customer_name
Phiên bản mới: display_name
~~~

Nếu chỉ tạo diff từ hai schema, writer có thể diễn giải thành drop cột cũ và add cột mới. Nếu dữ liệu trong customer_name cần được giữ lại, migration phải dùng change set có chủ đích như rename column hoặc add column, copy data, rồi drop cột cũ ở một release phù hợp.

Tương tự, khi đổi VARCHAR(100) thành VARCHAR(500), hãy xác nhận database có hỗ trợ thay đổi trực tiếp và dữ liệu hiện có không vi phạm quy tắc mới. Không giả định schema writer thay thế được thiết kế migration.

## 12. Từ generated change set đến migration được quản lý

Một workflow thường dùng:

~~~mermaid
flowchart TD
    A["Domain model và mapping"] --> B["RelationalMappingContext"]
    B --> C["LiquibaseChangeSetWriter"]
    C --> D["Generated YAML"]
    D --> E["Review schema và SQL dự kiến"]
    E --> F["Chỉnh sửa / bổ sung migration thủ công"]
    F --> G["Commit changelog vào version control"]
    G --> H["Khai báo changelog trong Liquibase"]
    H --> I["Liquibase thực thi migration ở môi trường triển khai"]
~~~

Các bước thực tế:

1. Sinh initial schema hoặc differential change set ở môi trường phát triển.
2. Đọc toàn bộ file YAML, kiểm tra bảng/cột/kiểu/constraint.
3. Bổ sung index, foreign key, rename, data migration hoặc SQL đặc thù nếu cần.
4. Đặt changelog vào thư mục Liquibase được project cấu hình, thường là src/main/resources/db/changelog.
5. Include file đó từ master changelog nếu project dùng changelog tổng.
6. Commit changelog đã review vào version control.
7. Cấu hình Spring Boot/Liquibase trỏ tới master changelog.
8. Chạy migration trên database kiểm thử trước khi triển khai các môi trường khác.

Liquibase quản lý lịch sử change set đã thực thi trong các bảng tracking của nó. Không sửa tùy tiện một change set đã chạy trên môi trường dùng chung; tạo change set mới để mô tả thay đổi tiếp theo.

## 13. Cấu hình Liquibase trong Spring Boot

Khi dependency Liquibase có mặt, Spring Boot có thể tự khởi chạy Liquibase lúc application context được tạo. Changelog mặc định thường được tìm trong vị trí chuẩn, hoặc cấu hình rõ bằng property:

~~~properties
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Master changelog có thể include file được sinh và review:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-initial-schema.yaml
      relativeToChangelogFile: false
  - include:
      file: db/changelog/002-add-customer-status.yaml
      relativeToChangelogFile: false
~~~

Đường dẫn include phải khớp cấu trúc resource thực tế trong project. Nếu file master nằm trong thư mục khác, hãy xác định rõ ý nghĩa của đường dẫn tương đối.

Trong generator test, có thể tắt auto-run Liquibase bằng:

~~~properties
spring.liquibase.enabled=false
~~~

Sau khi changelog đã được review và tích hợp, bật Liquibase ở môi trường cần thực thi migration. Không dùng việc tắt Liquibase trong test generator như một cấu hình triển khai vĩnh viễn.

## 14. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có bảng trong output | Mapping context chưa biết aggregate root | Đăng ký entity bằng setInitialEntitySet |
| Thiếu một số aggregate | Tập entity ban đầu chưa đầy đủ | Bổ sung các aggregate root cần quản lý |
| Không tìm thấy Liquibase class | Thiếu liquibase-core hoặc version dependency không phù hợp | Thêm dependency và kiểm tra dependency management |
| Spring Boot báo không tìm thấy changelog khi chạy generator test | Liquibase auto-configuration cố chạy migration | Tắt spring.liquibase.enabled trong test generator |
| Writer không ghi được file | Resource không resolve thành file vật lý hoặc thư mục cha chưa tồn tại | Dùng FileSystemResource và tạo thư mục |
| File có nhiều change set lặp | Writer append vào file đã có nội dung | Dùng file generated mới hoặc làm rỗng file output trước khi chạy |
| Diff đề xuất xóa bảng/cột | Entity bị loại khỏi schema mong muốn và drop filter cho phép xóa | Kiểm tra schema/drop filters và review diff |
| Bảng không bị xóa dù đã bỏ entity | Drop-table filter mặc định không cho xóa | Chỉ bật filter cho các bảng được phê duyệt |
| Cột không bị xóa | Drop-column filter mặc định giữ cột | Cấu hình predicate rõ ràng nếu thực sự cần drop |
| Kiểu SQL không đúng mong muốn | DefaultSqlTypeMapping không khớp quy ước database | Cung cấp SqlTypeMapping tùy chỉnh |
| Rename bị sinh thành drop/add | Writer không biết lịch sử và ý nghĩa rename | Viết rename/data migration thủ công |
| Foreign key/reference không xuất hiện | Schema generation không suy ra hoặc hỗ trợ reference theo yêu cầu | Bổ sung Liquibase changeset và kiểm tra version |
| Diff đọc nhầm database | Database object không khớp DataSource thực tế | Dùng DatabaseFactory với đúng JDBC connection |
| Changelog được sinh nhưng database không đổi | Writer chỉ ghi file, không thực thi migration | Cấu hình Liquibase để apply changelog sau review |

## 15. Quy trình triển khai

1. Kiểm tra version Spring Data JDBC; API LiquibaseChangeSetWriter có từ Spring Data Relational 3.2.
2. Thêm liquibase-core với version tương thích.
3. Lấy RelationalMappingContext đã cấu hình theo ứng dụng.
4. Đăng ký đủ aggregate root bằng setInitialEntitySet nếu context chưa có tập entity phù hợp.
5. Tạo LiquibaseChangeSetWriter từ mapping context.
6. Chọn initial mode cho schema trống hoặc differential mode với Liquibase Database cho schema hiện tại.
7. Dùng FileSystemResource trỏ tới file generated riêng.
8. Cấu hình schema filter, drop filters và SQL type mapping khi thật sự cần.
9. Sinh changelog, review và bổ sung các migration mà mapping không thể suy luận.
10. Đưa changelog đã duyệt vào version control và để Liquibase thực thi ở môi trường triển khai.

## 16. Bài tập thực hành

### Bài 1 — Initial schema

Tạo hai aggregate root Customer và PurchaseOrder. Đăng ký chúng trong RelationalMappingContext rồi dùng LiquibaseChangeSetWriter tạo YAML. Kiểm tra tên bảng, cột và kiểu SQL.

### Bài 2 — Mapping metadata

Thay tên bảng bằng @Table và đổi tên cột bằng @Column. Sinh lại initial schema và quan sát ảnh hưởng của mapping.

### Bài 3 — Differential schema

Tạo schema ban đầu, áp dụng vào database kiểm thử, sau đó thêm một property vào entity. Chạy differential mode và kiểm tra change set thêm cột.

### Bài 4 — Drop filters

Bỏ một entity khỏi tập schema mong muốn. Quan sát diff khi drop-table filter mặc định và khi bật filter cho một bảng được chọn. Không chạy migration drop trên database dùng chung.

### Bài 5 — Custom SQL type

Tạo annotation mô tả độ dài VARCHAR. Viết SqlTypeMapping đọc annotation và kết hợp DefaultSqlTypeMapping. Kiểm tra output với nhiều property.

### Bài 6 — Rename và data migration

Đổi tên một property đã có dữ liệu. Xem generated diff, sau đó viết Liquibase change set giữ dữ liệu bằng rename hoặc add/copy/drop theo chiến lược phù hợp.

### Bài 7 — Schema filter

Loại một entity khỏi schema bằng setSchemaFilter. So sánh kết quả ở initial và differential mode, đồng thời giải thích vai trò của drop-table filter.

### Bài 8 — Tích hợp Liquibase

Đưa changelog đã review vào master changelog. Chạy Liquibase trên database kiểm thử, xác nhận schema và lịch sử change set đã được ghi nhận.

## 17. Ghi nhớ

- LiquibaseChangeSetWriter tạo Liquibase changelog từ relational mapping metadata của Spring Data JDBC.
- Class thuộc package org.springframework.data.jdbc.core.mapping.schema và có từ Spring Data Relational 3.2.
- Initial mode tạo schema ban đầu; differential mode so sánh mapped entities với Liquibase Database hiện tại.
- RelationalMappingContext cần biết đầy đủ aggregate root trước khi sinh schema.
- writeChangeSet ghi file changelog; nó không tự apply migration vào database.
- Default SQL type mapping có thể thay bằng SqlTypeMapping; serializer/parser cũng có thể tùy chỉnh.
- Schema filter quyết định entity được đưa vào schema mong muốn; drop-table và drop-column filters quyết định những gì được phép xóa.
- Drop table/column bị tắt theo mặc định. Hãy bật có chọn lọc và review mọi destructive change.
- Writer không tự suy ra rename hoặc data migration; references cũng cần kiểm tra và bổ sung theo khả năng phiên bản.
- Dùng file generated riêng, review changelog, commit vào version control rồi để Liquibase quản lý việc thực thi migration.
- Test generator nên tránh Liquibase auto-run trước khi changelog sẵn sàng; cấu hình bật migration lại ở môi trường cần triển khai.
