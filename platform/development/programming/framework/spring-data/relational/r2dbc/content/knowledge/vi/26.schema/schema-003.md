# Quản lý phiên bản schema bằng Flyway hoặc Liquibase

Trong ứng dụng Spring Data R2DBC, entity Java và cấu trúc bảng trong database phải thay đổi đồng bộ. Khi thêm cột, đổi kiểu dữ liệu, tạo index hoặc bổ sung bảng mới, chỉ sửa class Java là chưa đủ: database đang chạy vẫn giữ schema cũ. Quản lý phiên bản schema (database schema migration) giải quyết việc này bằng các thay đổi có thứ tự, có thể theo dõi và được áp dụng tự động trong quá trình triển khai.

Flyway và Liquibase là hai công cụ phổ biến để quản lý migration. Cả hai lưu lại lịch sử những thay đổi đã áp dụng, phát hiện trạng thái schema không khớp và giúp các môi trường development, test, staging, production tiến dần qua cùng một chuỗi phiên bản.

Một điểm cần hiểu rõ trong dự án R2DBC: Flyway và Liquibase thường thực thi migration qua JDBC. Điều đó không buộc phần truy cập dữ liệu nghiệp vụ phải chuyển sang JDBC. Ứng dụng vẫn có thể dùng R2DBC cho repository và DatabaseClient, đồng thời dùng một JDBC connection riêng để công cụ migration chạy DDL/DML khi khởi động hoặc trong pipeline triển khai.

## 1. Vì sao cần version hóa schema?

Giả sử entity Customer ban đầu có các trường id và name. Sau một phiên bản, ứng dụng cần lưu thêm email:

~~~java
@Table("customer")
public record Customer(
        @Id Long id,
        String name,
        String email
) {}
~~~

Nếu production database chưa có cột email, truy vấn do Spring Data R2DBC sinh ra có thể thất bại. Ngược lại, nếu database đã có cột mới nhưng ứng dụng cũ vẫn chạy, ứng dụng cũ có thể tiếp tục hoạt động hoặc gặp lỗi tùy cách schema được thay đổi.

Migration biến thay đổi schema thành một artifact có phiên bản:

1. Tạo migration mô tả thay đổi.
2. Đưa migration vào source control cùng code.
3. Công cụ xác định migration nào chưa chạy.
4. Áp dụng migration theo thứ tự.
5. Ghi nhận phiên bản và kết quả trong database.
6. Kiểm thử ứng dụng trên schema sau migration.

Nhờ vậy, một database mới có thể được tạo từ đầu bằng toàn bộ lịch sử migration, còn database đang tồn tại chỉ cần áp dụng những thay đổi chưa chạy.

## 2. Schema migration khác với thay đổi entity

Entity mô tả cách ứng dụng ánh xạ dữ liệu; migration mô tả cách cấu trúc database được thay đổi. Hai phần phải nhất quán nhưng có trách nhiệm khác nhau.

| Thành phần | Trách nhiệm |
| --- | --- |
| Entity / record | Mô tả thuộc tính Java và mapping sang bảng/cột |
| Repository | Truy vấn và lưu entity qua R2DBC |
| DatabaseClient | Thực thi SQL tùy chỉnh trong ứng dụng |
| Flyway / Liquibase | Theo dõi và áp dụng thay đổi schema |
| Migration SQL/changelog | Định nghĩa thay đổi cụ thể của database |

Ví dụ thêm thuộc tính:

~~~java
@Column("email")
String email
~~~

Migration tương ứng có thể là:

~~~sql
ALTER TABLE customer
ADD COLUMN email VARCHAR(320);
~~~

Nếu chỉ thêm thuộc tính Java mà không thêm cột, ứng dụng có thể gặp lỗi khi đọc hoặc ghi. Nếu chỉ thêm cột mà không cập nhật mapping, cột có thể chưa được sử dụng. Vì thế, một thay đổi schema thường gồm cả migration, cập nhật entity/query và kiểm thử tương thích.

## 3. Flyway và Liquibase hoạt động như thế nào?

Hai công cụ có cùng mục tiêu nhưng cách mô tả thay đổi khác nhau:

| Tiêu chí | Flyway | Liquibase |
| --- | --- | --- |
| Mô tả migration | Thường dùng SQL versioned hoặc repeatable; cũng hỗ trợ Java migration | Changelog XML, YAML, JSON hoặc SQL có định dạng Liquibase |
| Lịch sử | Bảng schema history của Flyway | Bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| Định danh thay đổi | Version và checksum | ChangeSet với id, author và checksum |
| Rollback | Phụ thuộc loại migration, edition và hỗ trợ database; thường ưu tiên migration tiến về trước | Có thể khai báo rollback cho từng changeSet; khả năng tự sinh rollback tùy change |
| Phù hợp | Quy trình migration đơn giản, SQL rõ ràng, version tuyến tính | Cần changelog có cấu trúc, preconditions, contexts, labels và rollback được mô tả |

Không cần dùng đồng thời cả Flyway và Liquibase cho cùng một schema. Hãy chọn một công cụ làm nguồn sự thật cho lịch sử migration để tránh hai hệ thống cùng thay đổi database và không hiểu lịch sử của nhau.

## 4. Vai trò của JDBC trong dự án Spring Data R2DBC

Spring Data R2DBC dùng R2DBC driver để truy cập database theo mô hình reactive. Flyway và Liquibase trong cấu hình Spring Boot phổ biến lại sử dụng JDBC để thực thi migration.

Một ứng dụng có thể có cả hai cấu hình kết nối:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: app_user
    password: app_password

  flyway:
    url: jdbc:postgresql://localhost:5432/shop
    user: migration_user
    password: migration_password
    locations: classpath:db/migration
~~~

Ví dụ trên minh họa hai protocol khác nhau tới cùng database:

- R2DBC URL dùng cho repository và DatabaseClient.
- JDBC URL dùng riêng cho Flyway.

Để cấu hình này chạy được, runtime cần R2DBC driver và JDBC driver tương ứng. Với các phiên bản Flyway mới có thể cần thêm module database-specific, ví dụ module PostgreSQL, theo tài liệu của đúng phiên bản Flyway. Liquibase cũng cần JDBC driver để kết nối tới database trong cấu hình thông thường.

Việc dùng JDBC trong giai đoạn migration không làm các truy vấn nghiệp vụ trở thành blocking JDBC. Migration thường chạy lúc khởi động hoặc trong deployment stage, trước khi ứng dụng phục vụ request.

## 5. Cấu hình dependency cho Flyway với PostgreSQL

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.postgresql:postgresql")
    // Với Flyway phiên bản tách module database:
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
}
~~~

Ví dụ này minh họa nhóm dependency, không phải bộ version cố định. Nên để Spring Boot dependency management quản lý version tương thích, đồng thời kiểm tra hướng dẫn Flyway tương ứng với version được chọn. Không thêm module database nếu version Flyway đang dùng đã đóng gói hỗ trợ đó.

Với Maven, khai báo các dependency tương đương trong pom.xml và để Spring Boot BOM quản lý version khi phù hợp.

Không nên tự chọn version Flyway, JDBC driver và Spring Boot độc lập mà không kiểm tra compatibility. Một bản Flyway mới có thể tách hỗ trợ database thành module riêng hoặc thay đổi yêu cầu Java.

## 6. Cấu hình Flyway trong Spring Boot

Flyway có thể được cấu hình bằng application.yml:

~~~yaml
spring:
  flyway:
    enabled: true
    url: jdbc:postgresql://localhost:5432/shop
    user: migration_user
    password: migration_password
    locations:
      - classpath:db/migration
    validate-on-migrate: true
~~~

Không commit mật khẩu thật vào source control. Trong các môi trường triển khai, lấy thông tin kết nối từ environment variable, secret manager hoặc cơ chế cấu hình bảo mật của nền tảng.

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| enabled | Bật/tắt Flyway auto migration |
| url | JDBC URL dùng cho migration |
| user / password | Tài khoản migration |
| locations | Nơi chứa migration |
| schemas | Schema database mà Flyway quản lý |
| default-schema | Schema mặc định |
| baseline-on-migrate | Cho phép baseline database đã tồn tại khi chưa có history table |
| validate-on-migrate | Kiểm tra migration đã áp dụng có còn khớp checksum |
| clean-disabled | Ngăn thao tác clean xóa schema, thường nên giữ bật ở môi trường quan trọng |

Tên thuộc tính và mặc định cụ thể phụ thuộc phiên bản Spring Boot/Flyway. Kiểm tra configuration metadata và tài liệu của phiên bản dự án.

## 7. Cấu trúc thư mục migration của Flyway

Flyway mặc định thường tìm migration tại:

~~~text
src/main/resources/
└── db/
    └── migration/
        ├── V1__create_customer.sql
        ├── V2__create_product.sql
        ├── V3__add_customer_email.sql
        └── R__refresh_reporting_view.sql
~~~

Tên file versioned migration có dạng:

~~~text
V<version>__<description>.sql
~~~

Ví dụ:

- V1__create_customer.sql
- V2__add_customer_email.sql
- V2_1__add_customer_status.sql

Hai dấu gạch dưới phân cách version và description. Version phải theo quy tắc so sánh của Flyway; không dùng hai file có cùng version.

Repeatable migration dùng tiền tố R__ và được áp dụng lại khi checksum của nội dung thay đổi, thường phù hợp với view, function hoặc procedure cần cập nhật theo định nghĩa mới. Không dùng repeatable migration để thay thế lịch sử versioned schema change thông thường.

## 8. Viết versioned migration đầu tiên

File V1__create_customer.sql:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Migration này tạo bảng customer với:

- ID do database sinh.
- Tên không được null.
- Thời điểm tạo có timezone semantics theo database.

Một migration nên mô tả thay đổi có mục đích rõ ràng và đủ nhỏ để người review hiểu được. Nếu cần tạo nhiều bảng có quan hệ khóa ngoại, có thể đặt chúng trong cùng migration khi chúng tạo thành một thay đổi logic không thể tách rời; nếu không, chia theo phiên bản riêng.

## 9. Thêm cột trong migration tiếp theo

Khi cần email:

~~~sql
ALTER TABLE customer
ADD COLUMN email VARCHAR(320);
~~~

Lưu thành V2__add_customer_email.sql. Nếu migration V1 đã chạy ở bất kỳ môi trường nào, không sửa nội dung V1 để thêm email. Hãy tạo V2.

Flyway lưu version, description, checksum, trạng thái và thông tin thực thi trong bảng schema history, thường là flyway_schema_history. Khi chạy migrate, Flyway so sánh migration trong artifact với lịch sử database, rồi áp dụng các version chưa chạy theo thứ tự.

## 10. Không sửa migration versioned đã áp dụng

Sau khi migration versioned đã chạy trên môi trường dùng chung, hãy coi file đó là bất biến:

- Không đổi nội dung V1 để sửa lỗi.
- Không đổi tên hoặc version đã phát hành.
- Tạo migration V2/V3 mới để sửa hoặc bổ sung schema.
- Giữ migration đã phát hành trong source control.

Lý do: database đã lưu checksum của migration cũ. Nếu file bị sửa, Flyway có thể báo checksum mismatch khi validate/migrate. Nếu một môi trường đã chạy file cũ còn môi trường khác chạy file mới, lịch sử schema không còn nhất quán.

Lệnh repair có thể điều chỉnh metadata lịch sử trong một số trường hợp, nhưng không phải công cụ để hợp thức hóa việc tùy tiện sửa migration đã chạy. Chỉ dùng repair khi đã hiểu chính xác trạng thái database và có quy trình phục hồi được kiểm soát.

## 11. Repeatable migration trong Flyway

Repeatable migration dùng tên dạng R__description.sql:

~~~sql
CREATE OR REPLACE VIEW active_customer AS
SELECT id, name, email
FROM customer
WHERE status = 'ACTIVE';
~~~

Flyway so sánh checksum của repeatable migration với lịch sử. Khi nội dung thay đổi, migration được chạy lại sau các versioned migration pending theo quy tắc của Flyway.

Các trường hợp thường phù hợp:

- Tạo hoặc thay thế view.
- Định nghĩa function/procedure.
- Các đối tượng database có thể tái tạo từ toàn bộ định nghĩa.

Hãy bảo đảm script repeatable có thể chạy lại an toàn theo database dialect. Không dùng nó để thêm cột hoặc thay đổi dữ liệu từng bước mà không có chiến lược lặp lại rõ ràng.

## 12. Baseline cho database đã tồn tại

Nếu database đã có schema và dữ liệu trước khi bắt đầu dùng Flyway, không thể luôn áp dụng V1 tạo lại toàn bộ bảng. Cần xác định database hiện tại tương ứng với phiên bản schema nào.

Flyway baseline ghi nhận một mốc lịch sử để các migration có version thấp hơn hoặc bằng mốc đó được coi là đã được bao phủ. Có thể cấu hình baseline version và baseline description, hoặc chạy lệnh baseline qua Flyway CLI/API.

Quy trình nên gồm:

1. Sao lưu database.
2. Kiểm tra schema thực tế so với schema mà migration lịch sử mô tả.
3. Chọn baseline version phù hợp.
4. Chạy baseline trên đúng database mục tiêu.
5. Chạy migrate để áp dụng những migration sau baseline.
6. Kiểm tra schema và ứng dụng.

Thuộc tính baseline-on-migrate có thể tiện cho database không có history table, nhưng bật nó tùy tiện có thể đánh dấu nhầm một schema chưa đúng là đã ở baseline. Không dùng baseline để bỏ qua việc so sánh schema hiện tại.

## 13. Cấu hình Liquibase trong Spring Boot

Liquibase sử dụng changelog làm nguồn mô tả thay đổi. Với cấu hình JDBC thông thường:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    url: jdbc:postgresql://localhost:5432/shop
    user: migration_user
    password: migration_password
~~~

Spring Boot có thể tự cấu hình Liquibase khi dependency và JDBC datasource phù hợp đã có. Với ứng dụng chỉ cấu hình R2DBC, cần cung cấp JDBC URL/driver hoặc datasource dành riêng cho migration theo cấu hình của phiên bản Boot.

Các thuộc tính phổ biến:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| enabled | Bật/tắt Liquibase |
| change-log | Đường dẫn changelog gốc |
| url | JDBC URL cho migration |
| user / password | Tài khoản migration |
| default-schema | Schema mặc định |
| contexts | Lọc changeSet theo context |
| labels | Lọc changeSet theo label |
| drop-first | Xóa schema trước khi chạy; rất nguy hiểm ngoài môi trường test |

Không bật drop-first trong production. Cũng như Flyway, hãy quản lý thông tin xác thực bằng secret/environment thay vì lưu password thật trong repository.

## 14. Cấu trúc changelog của Liquibase

Một cấu trúc thường gặp:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── changes/
            ├── 001-create-customer.yaml
            ├── 002-add-customer-email.yaml
            └── 003-create-product.yaml
~~~

File master changelog kết nối các file thay đổi:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-email.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-create-product.yaml
      relativeToChangelogFile: true
~~~

Liquibase cũng hỗ trợ includeAll để nạp các file trong một thư mục. Khi dùng includeAll, hãy kiểm soát thứ tự file và quy ước tên rõ ràng để thứ tự áp dụng không thay đổi ngoài ý muốn.

## 15. ChangeSet là đơn vị thay đổi của Liquibase

Mỗi changeSet có định danh gồm id, author và đường dẫn changelog. Ví dụ:

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
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP WITH TIME ZONE
                  constraints:
                    nullable: false
~~~

Liquibase ghi nhận changeSet đã chạy trong DATABASECHANGELOG cùng checksum và thông tin thực thi. DATABASECHANGELOGLOCK được dùng để điều phối việc một tiến trình Liquibase thay đổi schema tại một thời điểm.

Khi changeSet đã chạy, không nên sửa nội dung của nó. Nếu cần thay đổi schema, tạo changeSet mới. Việc sửa changeSet cũ có thể gây checksum validation error hoặc khiến các môi trường có lịch sử khác nhau.

## 16. Thêm cột bằng Liquibase

ChangeSet tiếp theo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-email
      author: team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email
                  type: VARCHAR(320)
~~~

Có thể khai báo rollback:

~~~yaml
      rollback:
        - dropColumn:
            tableName: customer
            columnName: email
~~~

Rollback chỉ nên được khai báo khi thao tác ngược thật sự an toàn. Nếu cột email đã nhận dữ liệu, dropColumn sẽ làm mất dữ liệu đó. Rollback kỹ thuật không đồng nghĩa với rollback nghiệp vụ an toàn.

Với thay đổi phá hủy dữ liệu hoặc không thể đảo ngược, cần có kế hoạch backup, phục hồi hoặc migration tiến về trước thay vì dựa vào rollback tự động.

## 17. SQL changelog trong Liquibase

Nếu nhóm phát triển quen SQL, Liquibase hỗ trợ formatted SQL changelog:

~~~sql
--liquibase formatted sql

--changeset team:001-create-customer
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

--rollback DROP TABLE customer;
~~~

Đầu file khai báo formatted SQL; mỗi changeSet có id và author. Rollback có thể được khai báo bằng comment đặc biệt. Cú pháp SQL và khả năng rollback phụ thuộc database.

Không nhầm SQL changelog của Liquibase với SQL migration của Flyway. Flyway thường xác định version từ tên file; Liquibase xác định changeSet từ metadata trong changelog.

## 18. Preconditions, contexts và labels của Liquibase

Precondition cho phép kiểm tra trạng thái database trước khi áp dụng changeSet:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-status
      author: team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(30)
~~~

Precondition hữu ích khi migration phụ thuộc đối tượng đã tồn tại. Chọn onFail/onError có chủ đích: HALT dừng migration khi điều kiện không thỏa; MARK_RAN hoặc CONTINUE có semantics khác và có thể che giấu schema sai nếu dùng không cẩn thận.

Contexts và labels có thể lọc changeSet theo môi trường hoặc mục đích, ví dụ dữ liệu tham chiếu cho test. Không nên dùng context để làm schema production khác biệt ngoài ý muốn. Hãy xác định rõ changeSet nào bắt buộc ở mọi môi trường.

## 19. Chọn Flyway hay Liquibase?

Chọn theo quy trình và nhu cầu của nhóm:

**Flyway phù hợp khi:**

- Nhóm muốn viết SQL trực tiếp và kiểm soát câu lệnh database.
- Lịch sử schema đi theo chuỗi version đơn giản.
- Cần quy trình dễ hiểu: thêm file V mới, chạy migrate.
- Repeatable migration hữu ích cho view hoặc procedure.

**Liquibase phù hợp khi:**

- Nhóm muốn mô tả schema bằng changelog có cấu trúc.
- Cần preconditions, contexts, labels hoặc include nhiều file.
- Muốn khai báo rollback cho changeSet khi có thể.
- Cần nhiều định dạng changelog và khả năng xem/so sánh thay đổi.

Không có công cụ nào tự làm migration an toàn nếu script có lỗi hoặc không tương thích với dữ liệu production. Review SQL, kiểm thử trên database cùng loại và kế hoạch triển khai vẫn rất quan trọng.

## 20. Quản lý thứ tự migration và lịch sử

Migration phải có thứ tự xác định. Khi một versioned migration đã chạy, hãy thêm version mới thay vì chèn một file có version cũ vào giữa lịch sử.

Ví dụ Flyway:

~~~text
V1__create_customer.sql
V2__add_customer_email.sql
V3__create_order.sql
V4__add_order_status.sql
~~~

Ví dụ Liquibase:

~~~text
001-create-customer
002-add-customer-email
003-create-order
004-add-order-status
~~~

Không đổi tên hoặc xóa migration đã được môi trường dùng chung áp dụng. Nếu nhiều nhánh phát triển tạo migration đồng thời, cần hợp nhất version trước khi phát hành và xác nhận không có hai migration trùng version hoặc phụ thuộc thứ tự không rõ.

## 21. Migration transaction và DDL khác nhau theo database

Một số database hỗ trợ DDL transactional cho nhiều loại câu lệnh; một số câu lệnh DDL có thể tự commit hoặc không thể rollback như DML. Flyway và Liquibase có thể điều chỉnh transaction behavior theo database và loại change.

Không giả định một migration gồm nhiều câu lệnh luôn nguyên tử trên mọi hệ quản trị. Nếu bước thứ ba thất bại sau khi hai bước đầu đã thay đổi schema, database có thể ở trạng thái một phần tùy dialect.

Hãy:

- Kiểm tra tài liệu database về transactional DDL.
- Chia migration thành bước nhỏ có thể quan sát.
- Test migration từ schema trước đó trên database thực tế.
- Chuẩn bị backup và phương án phục hồi cho thay đổi rủi ro.
- Kiểm tra trạng thái migration history sau khi thất bại trước khi chạy lại.

## 22. Expand-and-contract cho triển khai không gián đoạn

Thay đổi schema có thể phá vỡ ứng dụng cũ đang chạy. Ví dụ đổi tên cột name thành full_name rồi xóa name ngay lập tức sẽ khiến instance ứng dụng cũ còn truy vấn name bị lỗi.

Chiến lược expand-and-contract chia thay đổi thành nhiều lần triển khai:

~~~mermaid
flowchart TD
    A[Hiện trạng: chỉ có name]
    B[Expand: thêm full_name nullable]
    C[Ứng dụng mới đọc/ghi tương thích cả hai]
    D[Backfill dữ liệu name sang full_name]
    E[Chuyển ứng dụng sang full_name]
    F[Contract: bỏ name ở release sau]
    A --> B --> C --> D --> E --> F
~~~

Một trình tự thường dùng:

1. Thêm cột mới theo cách tương thích với ứng dụng cũ.
2. Deploy code có thể đọc/ghi cả cấu trúc cũ và mới.
3. Backfill dữ liệu cũ sang cột mới theo batch.
4. Chuyển mọi instance sang dùng cột mới.
5. Xác nhận không còn code đọc/ghi cột cũ.
6. Trong một release sau, mới xóa cột cũ.

Chiến lược này đặc biệt quan trọng khi deployment rolling có nhiều phiên bản ứng dụng chạy đồng thời. Migration không nên làm ứng dụng cũ ngừng hoạt động trước khi phiên bản mới đã sẵn sàng.

## 23. Thay đổi cột NOT NULL và dữ liệu hiện có

Thêm cột NOT NULL vào bảng có dữ liệu có thể thất bại nếu không có giá trị cho hàng cũ hoặc database phải thực hiện thao tác tốn kém.

Một cách an toàn hơn:

1. Thêm cột nullable.
2. Deploy ứng dụng ghi giá trị cho bản ghi mới.
3. Backfill bản ghi cũ theo batch.
4. Kiểm tra không còn giá trị NULL.
5. Thêm constraint NOT NULL trong migration riêng.

Ví dụ:

~~~sql
ALTER TABLE customer
ADD COLUMN status VARCHAR(30);
~~~

Backfill:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Sau khi xác nhận dữ liệu:

~~~sql
ALTER TABLE customer
ALTER COLUMN status SET NOT NULL;
~~~

Cú pháp thay đổi cột khác nhau theo database. Với bảng lớn, backfill một UPDATE duy nhất có thể tạo transaction dài, lock và lượng WAL/transaction log lớn; hãy cân nhắc xử lý theo batch và theo dõi tải.

## 24. Migration dữ liệu (data migration)

Migration không chỉ tạo bảng hoặc cột. Đôi khi cần chuyển đổi dữ liệu:

- Chuẩn hóa trạng thái từ mã cũ sang mã mới.
- Tách một trường thành nhiều cột.
- Gộp dữ liệu từ bảng cũ sang bảng mới.
- Điền giá trị mặc định cho bản ghi lịch sử.

Ví dụ:

~~~sql
UPDATE customer
SET status = CASE
    WHEN enabled = TRUE THEN 'ACTIVE'
    ELSE 'INACTIVE'
END
WHERE status IS NULL;
~~~

Với bảng lớn, không nhất thiết chạy toàn bộ data migration trong một lần startup. Có thể triển khai một job riêng theo batch, ghi checkpoint và có khả năng tiếp tục sau lỗi. Schema cần ở trạng thái tương thích trong suốt thời gian backfill.

Data migration cần kiểm tra số lượng hàng trước/sau, quy tắc chuyển đổi, giá trị không hợp lệ và khả năng chạy lại. Không đưa dữ liệu nghiệp vụ phụ thuộc môi trường vào migration schema nếu có thể nạp bằng bước seed riêng có kiểm soát.

## 25. Quyền database cho migration và ứng dụng

Tài khoản chạy migration thường cần quyền DDL như CREATE, ALTER, DROP hoặc quyền thay đổi schema. Tài khoản runtime của ứng dụng R2DBC thường chỉ cần các quyền DML tối thiểu cho nghiệp vụ.

Có thể tách:

- Migration user: được phép thay đổi schema và quản lý bảng lịch sử migration.
- Application user: được phép SELECT/INSERT/UPDATE/DELETE trên các bảng cần thiết.

Tách quyền giúp giảm tác động nếu ứng dụng runtime bị khai thác hoặc có lỗi. Không chạy ứng dụng production bằng tài khoản owner/superuser chỉ để Flyway hoặc Liquibase có thể tạo bảng.

Tài khoản migration phải được quản lý bằng secret và chỉ cấp quyền cần thiết. Nếu migration chạy trong pipeline riêng, credentials có thể chỉ tồn tại ở stage migration thay vì được đưa vào mọi application pod.

## 26. Chạy migration khi khởi động hay trong CI/CD?

Có hai cách triển khai thường gặp:

**Migration lúc ứng dụng khởi động**

- Spring Boot chạy Flyway/Liquibase trước khi application context sẵn sàng.
- Phù hợp hệ thống nhỏ hoặc môi trường có một instance.
- Nhiều replica có thể cùng khởi động và cùng thử migrate; công cụ có cơ chế lock lịch sử nhưng deployment vẫn cần kiểm soát.
- Một migration lâu có thể làm chậm readiness của ứng dụng.

**Migration trong deployment pipeline hoặc job riêng**

- Pipeline chạy migration một lần trước khi rollout ứng dụng.
- Dễ tách quyền migration khỏi runtime.
- Có thể kiểm tra trạng thái và phê duyệt migration trước khi mở traffic.
- Cần đảm bảo ứng dụng chỉ được rollout khi migration thành công.

Với production có nhiều replica, một migration job riêng thường giúp kiểm soát thứ tự triển khai rõ hơn. Dù chọn cách nào, công cụ migration vẫn cần lock để ngăn nhiều tiến trình áp dụng schema đồng thời.

Không chạy migration thủ công song song với pipeline nếu không có kế hoạch điều phối. Hãy chỉ định một chủ thể chịu trách nhiệm áp dụng schema cho mỗi lần phát hành.

## 27. Cấu hình môi trường development, test và production

Các môi trường có thể dùng cùng một chuỗi migration nhưng kết nối và dữ liệu khác nhau:

| Môi trường | Mục tiêu |
| --- | --- |
| Local | Developer có thể tạo database mới và chạy toàn bộ migration |
| Test | Khởi tạo schema sạch từ migration và chạy integration test |
| Staging | Diễn tập migration trên dữ liệu có hình dạng gần production |
| Production | Áp dụng migration có kiểm soát, backup và quan sát |

Không nên duy trì một bộ migration riêng cho từng môi trường chỉ vì schema khác nhau. Nếu cần dữ liệu mẫu, tách seed data hoặc dùng Liquibase contexts/labels có chủ đích. Schema cốt lõi nên nhất quán.

Trong test, Testcontainers có thể khởi chạy đúng loại database, sau đó Flyway/Liquibase áp dụng migration trước khi repository integration test chạy. Cách này giúp kiểm tra SQL dialect và constraint thật thay vì chỉ dựa trên mock hoặc embedded database khác engine.

## 28. Tích hợp migration với Spring Data R2DBC

Sau khi migration tạo bảng, entity R2DBC phải ánh xạ đúng tên bảng/cột và kiểu dữ liệu:

~~~java
@Table("customer")
public record Customer(
        @Id Long id,
        @Column("full_name") String fullName,
        String email,
        String status
) {}
~~~

Migration tương ứng:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320),
    status VARCHAR(30) NOT NULL
);
~~~

Kiểm tra các điểm sau:

- Tên bảng và cột đúng với @Table/@Column hoặc naming strategy.
- Kiểu SQL tương thích với kiểu Java và R2DBC driver.
- Cột nullable khớp với domain model và validation.
- Generated ID/default value được driver/Spring Data đọc đúng.
- Foreign key, unique constraint và index đã được tạo.
- Custom conversion phù hợp nếu dùng kiểu domain đặc biệt.

Spring Data R2DBC không phải Hibernate schema generation. Đừng dựa vào thuộc tính JPA như spring.jpa.hibernate.ddl-auto để quản lý schema cho R2DBC. Dùng Flyway hoặc Liquibase làm nguồn sự thật cho schema.

## 29. Xác minh migration trong pipeline

Một pipeline cơ bản có thể gồm:

1. Compile và unit test.
2. Khởi tạo database kiểm thử.
3. Chạy Flyway migrate hoặc Liquibase update.
4. Kiểm tra migration status/validate.
5. Chạy repository integration test trên schema đã migrate.
6. Tạo artifact ứng dụng.
7. Chạy migration production trong stage được kiểm soát.
8. Rollout ứng dụng tương thích với schema mới.

Với Flyway, lệnh validate giúp phát hiện migration đã áp dụng bị thay đổi checksum hoặc trạng thái không hợp lệ. Với Liquibase, validate giúp kiểm tra changelog và cấu hình trước khi update. Các lệnh cụ thể phụ thuộc plugin/CLI hoặc cách tích hợp Spring Boot.

Không chỉ kiểm tra rằng migration command trả exit code 0. Hãy chạy truy vấn repository thật để xác nhận mapping, constraint và hành vi đọc/ghi.

## 30. Test migration từ nhiều trạng thái schema

Migration nên được kiểm thử từ trạng thái ban đầu mà nó dự kiến hỗ trợ:

- Database mới hoàn toàn: toàn bộ migration chạy lần lượt.
- Database ở phiên bản cũ: chỉ các migration mới được áp dụng.
- Database đã migrate: chạy lại không thay đổi lịch sử ngoài dự kiến.
- Migration lỗi giữa chừng: xác định trạng thái schema và history table sau lỗi.
- Database có dữ liệu cũ: backfill không làm mất hoặc biến dạng dữ liệu.
- Schema có khác biệt do thao tác thủ công: validate hoặc precondition phát hiện được sai lệch quan trọng.

Với Flyway, có thể dùng validate và kiểm tra schema history. Với Liquibase, dùng validate/status và kiểm tra DATABASECHANGELOG. Cũng nên có test phục hồi/backup cho migration phá hủy hoặc chuyển đổi dữ liệu lớn.

## 31. Baseline, repair và clean: dùng đúng mục đích

Flyway có một số thao tác quản trị cần hiểu rõ:

- **baseline:** đánh dấu một database hiện có ở một version nhất định khi bắt đầu quản lý bằng Flyway.
- **validate:** kiểm tra migration và lịch sử có khớp không.
- **repair:** sửa metadata history trong các trường hợp được xác định rõ, ví dụ loại bỏ entry failed hoặc đồng bộ checksum theo quy trình đã kiểm soát.
- **clean:** xóa đối tượng trong schema được quản lý; rất nguy hiểm với dữ liệu thật.

Không chạy clean trên production. Nên cấu hình clean bị vô hiệu hóa ở môi trường quan trọng. Repair không thay thế việc sửa schema bằng migration mới và không nên dùng để che giấu việc file migration đã bị thay đổi.

Liquibase có các lệnh update, validate, status, rollback và clearCheckSums; chúng cũng cần được dùng theo đúng tình huống. clearCheckSums chỉ xóa checksum đã lưu để tính lại, không sửa nội dung hoặc trạng thái schema thực tế.

## 32. Quy trình xử lý khi migration thất bại

Khi migration lỗi, không nên chạy lặp lại một cách mù quáng:

1. Dừng rollout ứng dụng mới.
2. Lưu log đầy đủ của công cụ và database.
3. Xác định câu lệnh nào đã chạy thành công và câu nào thất bại.
4. Kiểm tra transaction/DDL behavior của database.
5. Kiểm tra bảng history và schema thực tế.
6. Quyết định có thể chạy lại, cần sửa trạng thái migration hay cần migration phục hồi.
7. Backup trước khi thực hiện thao tác sửa chữa có rủi ro.
8. Chạy lại validate/status và kiểm thử ứng dụng.

Không xóa history table hoặc xóa migration file để “làm sạch” trạng thái. Việc đó có thể khiến công cụ hiểu sai phiên bản schema và chạy lại DDL phá hủy dữ liệu.

## 33. Những lỗi thường gặp

1. **Chỉ sửa entity mà không tạo migration.** Runtime query có thể tham chiếu cột chưa tồn tại.
2. **Dùng R2DBC URL cho Flyway JDBC.** Migration tool cần JDBC URL trong cấu hình thông thường.
3. **Thiếu JDBC driver.** R2DBC driver không thay thế JDBC driver cho Flyway/Liquibase.
4. **Dùng cả Flyway và Liquibase trên cùng schema.** Hai lịch sử migration không tự đồng bộ với nhau.
5. **Sửa migration versioned đã chạy.** Checksum giữa môi trường sẽ lệch.
6. **Thêm cột NOT NULL ngay vào bảng đã có dữ liệu.** Migration có thể thất bại hoặc gây thao tác tốn kém.
7. **Đổi tên/xóa cột ngay trong một release rolling.** Instance ứng dụng cũ có thể bị lỗi.
8. **Bật baseline-on-migrate hoặc baseline không kiểm tra schema.** Database sai có thể bị đánh dấu nhầm là đã đúng version.
9. **Dùng clean hoặc drop-first trên production.** Có thể xóa schema và dữ liệu.
10. **Chạy data backfill khổng lồ trong một transaction startup.** Có thể giữ lock và làm ứng dụng không sẵn sàng lâu.
11. **Để mọi application replica cùng tự quản lý migration không có điều phối.** Có thể làm startup cạnh tranh và khó quan sát.
12. **Dùng migration user làm tài khoản runtime.** Cấp quyền DDL quá rộng cho ứng dụng.
13. **Không kiểm thử trên đúng database engine.** SQL type, DDL transaction và index syntax có thể khác.
14. **Chỉ kiểm tra migration thành công mà không test repository.** Schema có thể được tạo nhưng mapping R2DBC vẫn sai.

## Quy trình lựa chọn và triển khai

- Chọn một công cụ làm nguồn lịch sử schema: Flyway hoặc Liquibase.
- Xác nhận công cụ và phiên bản dùng JDBC; bổ sung JDBC driver/module database phù hợp bên cạnh R2DBC driver.
- Đặt migration/changelog trong source control cùng ứng dụng.
- Tạo migration mới cho mỗi thay đổi schema; giữ nguyên migration đã áp dụng.
- Kiểm thử từ database mới và từ phiên bản schema trước đó.
- Dùng expand-and-contract cho thay đổi phá vỡ tương thích hoặc triển khai rolling.
- Tách migration credentials khỏi runtime credentials khi có thể.
- Chạy migration trước khi rollout code phụ thuộc schema mới.
- Xác minh schema bằng validate/status và repository integration test.
- Chuẩn bị backup, quan sát và kế hoạch phục hồi cho thay đổi rủi ro.

Quản lý phiên bản schema giúp database tiến hóa cùng ứng dụng mà không phụ thuộc vào thao tác SQL thủ công ở từng môi trường. Trong dự án Spring Data R2DBC, Flyway hoặc Liquibase thường dùng JDBC để chạy migration, còn repository và DatabaseClient vẫn dùng R2DBC cho truy cập dữ liệu nghiệp vụ. Hãy lưu migration trong source control, không sửa lịch sử đã áp dụng, kiểm thử trên đúng database và triển khai thay đổi theo hướng tương thích nhiều phiên bản. Khi migration, entity mapping và deployment sequence được quản lý cùng nhau, các môi trường có thể giữ schema nhất quán và ứng dụng giảm nguy cơ lỗi khi phát hành phiên bản mới.
