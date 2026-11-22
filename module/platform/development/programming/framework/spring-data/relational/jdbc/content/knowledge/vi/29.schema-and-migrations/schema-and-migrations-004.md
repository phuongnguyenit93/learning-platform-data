# Quản lý thay đổi schema bằng Flyway hoặc Liquibase

Trong ứng dụng **Spring Data Relational JDBC**, entity và repository phụ thuộc trực tiếp vào cấu trúc bảng, cột, khóa chính, khóa ngoại và kiểu dữ liệu trong database. Khi ứng dụng phát triển, schema cũng thay đổi: thêm cột, tạo index, tách bảng, đổi kiểu dữ liệu hoặc chuyển đổi dữ liệu cũ. Nếu mỗi môi trường tự sửa schema bằng tay, các database sẽ dần khác nhau và ứng dụng có thể chạy được ở máy lập trình viên nhưng lỗi ở staging hoặc production.

**Database migration** là cách quản lý những thay đổi schema theo từng phiên bản, lưu chúng trong source control và áp dụng theo một thứ tự xác định. Hai công cụ phổ biến trong hệ sinh thái Spring là **Flyway** và **Liquibase**. Cả hai theo dõi lịch sử migration trong database, phát hiện thay đổi đã áp dụng và giúp triển khai schema nhất quán qua các môi trường.

Spring Data JDBC không tự quản lý lịch sử thay đổi schema. Repository cần một schema đã được chuẩn bị đúng. Flyway hoặc Liquibase đảm nhiệm phần tiến hóa schema; mapping của Spring Data JDBC sau đó sử dụng các bảng và cột tương ứng.

## 1. Vì sao cần migration?

Giả sử phiên bản đầu của ứng dụng có bảng sản phẩm:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL
);
~~~

Phiên bản tiếp theo cần trạng thái và giá:

~~~sql
ALTER TABLE product
    ADD COLUMN status VARCHAR(24);

ALTER TABLE product
    ADD COLUMN price DECIMAL(19, 2);
~~~

Sau đó ứng dụng cần đặt giá trị mặc định, thêm constraint và index. Nếu lập trình viên chạy các câu SQL thủ công theo trí nhớ, một số môi trường có thể thiếu cột hoặc có kiểu dữ liệu khác nhau.

Migration giải quyết vấn đề bằng cách lưu thay đổi thành file có phiên bản:

~~~text
src/main/resources/db/migration/
  V1__create_product.sql
  V2__add_product_status.sql
  V3__add_product_price.sql
  V4__add_product_indexes.sql
~~~

Khi triển khai, công cụ đọc lịch sử trong database, xác định migration nào chưa chạy và áp dụng chúng theo thứ tự. Một database mới có thể chạy từ V1; database đã ở V2 chỉ cần chạy V3 và V4.

### 1.1. Migration đem lại điều gì?

- **Tái lập được:** có thể dựng schema từ đầu bằng cùng một chuỗi migration.
- **Có lịch sử:** biết thay đổi nào đã được áp dụng và vào thời điểm nào.
- **Có thể review:** thay đổi schema đi cùng code trong pull request.
- **Nhất quán môi trường:** dev, test, staging và production dùng cùng định nghĩa schema.
- **Triển khai có kiểm soát:** migration được chạy theo thứ tự và có thể kiểm tra checksum/trạng thái.
- **Hỗ trợ phối hợp:** nhiều người phát triển có thể bổ sung migration mới mà không sửa lại lịch sử đã phát hành.

### 1.2. Migration là một phần của source code

File migration cần được commit vào version control cùng thay đổi entity/repository liên quan. Khi thêm field Java mà quên migration, ứng dụng có thể lỗi khi truy vấn hoặc ghi. Khi chỉ sửa schema production mà không lưu migration, môi trường tiếp theo không thể tái tạo thay đổi đó.

Một thay đổi hoàn chỉnh thường gồm:

1. Migration thay đổi schema hoặc dữ liệu.
2. Mapping/entity phù hợp với schema mới.
3. Repository/query sử dụng cột hoặc bảng mới.
4. Test xác nhận ứng dụng hoạt động trên schema được tạo từ migration.

## 2. Flyway và Liquibase hoạt động như thế nào?

Cả hai công cụ đều lưu trạng thái migration trong database, nhưng cách mô tả thay đổi khác nhau.

| Khía cạnh | Flyway | Liquibase |
| --- | --- | --- |
| Cách mô tả phổ biến | SQL migration có phiên bản | Changelog và changeset bằng XML, YAML, JSON hoặc SQL |
| Đơn vị lịch sử | Versioned migration và repeatable migration | Changeset có id, author và file path |
| Bảng theo dõi | Thường là `flyway_schema_history` | Thường là `DATABASECHANGELOG` |
| Đồng bộ khi chạy | Áp dụng migration chưa chạy theo thứ tự version | Áp dụng changeset chưa được ghi nhận |
| Kiểm tra thay đổi | Checksum và trạng thái migration | Checksum, id/author/path và trạng thái changeset |
| Rollback | Thường ưu tiên migration mới sửa trạng thái; undo có giới hạn theo edition/cấu hình | Có thể khai báo rollback cho changeset; khả năng tự sinh rollback phụ thuộc loại change |
| Mô tả database | SQL trực tiếp, rõ ràng và gần database | Change types có cấu trúc, có thể trừu tượng hóa một phần SQL |

Không có công cụ nào tự làm cho mọi migration an toàn. Chất lượng migration phụ thuộc cách thiết kế, review, kiểm thử và quy trình triển khai.

### 2.1. Chọn một công cụ làm nguồn sự thật

Một ứng dụng thông thường nên dùng Flyway hoặc Liquibase để quản lý schema. Không nên để cả hai cùng quản lý một schema nếu không có thiết kế phân chia ownership rõ ràng. Khi cả hai cùng thay đổi một bảng, lịch sử và thứ tự triển khai có thể trở nên khó hiểu.

Nếu dự án đã có một công cụ và lịch sử migration, hãy tiếp tục theo công cụ đó. Chuyển công cụ là một dự án migration riêng: cần xác định trạng thái hiện tại, baseline lịch sử, ngăn hai công cụ cùng chạy và kiểm tra từng môi trường.

## 3. Flyway: versioned SQL migrations

Flyway phù hợp khi nhóm muốn mô tả schema bằng SQL trực tiếp và quản lý thứ tự migration theo version.

### 3.1. Cấu trúc thư mục

Vị trí mặc định thường dùng:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_product.sql
      V2__add_product_status.sql
      V3__add_product_price.sql
      V4__create_category.sql
~~~

Tên file versioned migration theo mẫu:

~~~text
V<version>__<description>.sql
~~~

Ví dụ:

- `V1__create_product.sql`
- `V2__add_product_status.sql`
- `V2_1__add_product_price.sql`
- `V3__create_product_category_index.sql`

Hai dấu gạch dưới phân cách version và description. Version được so sánh theo quy tắc của Flyway; nên chọn cách đánh số nhất quán và tránh tạo hai migration có cùng version.

### 3.2. Ví dụ migration đầu tiên

File `V1__create_product.sql`:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_product_sku UNIQUE (sku)
);
~~~

Migration tạo bảng và constraint. Cú pháp identity trong ví dụ phù hợp với một số database hiện đại; nếu dùng PostgreSQL, MySQL, SQL Server hoặc Oracle, hãy chọn cú pháp đúng với database mục tiêu. Flyway không biến SQL vendor-specific thành SQL portable.

### 3.3. Thêm cột qua migration mới

File `V2__add_product_status.sql`:

~~~sql
ALTER TABLE product
    ADD COLUMN status VARCHAR(24);

UPDATE product
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE product
    ALTER COLUMN status SET NOT NULL;
~~~

Cú pháp `ALTER COLUMN ... SET NOT NULL` không giống nhau trên mọi database. Ví dụ minh họa ý tưởng ba bước:

1. Thêm cột cho phép null.
2. Backfill dữ liệu cũ.
3. Áp dụng NOT NULL sau khi mọi hàng đã có giá trị.

Với database khác, dùng cú pháp tương ứng. Không thêm NOT NULL trực tiếp cho bảng đã có dữ liệu nếu chưa bảo đảm mọi hàng hiện tại nhận được giá trị hợp lệ.

### 3.4. Flyway schema history

Flyway tạo bảng lịch sử, mặc định thường có tên `flyway_schema_history`. Bảng này ghi nhận version, description, type, script, checksum, thời điểm chạy, trạng thái thành công và các thông tin liên quan.

Khi chạy migrate:

1. Flyway đọc lịch sử.
2. So sánh migration có trong classpath với version đã áp dụng.
3. Xác định migration pending.
4. Chạy theo thứ tự version.
5. Ghi nhận kết quả vào schema history.

Nếu migration đã áp dụng bị sửa nội dung, checksum có thể không khớp. Đây là tín hiệu lịch sử source code không còn giống lịch sử database.

### 3.5. Không sửa versioned migration đã áp dụng

Giả sử `V2__add_product_status.sql` đã chạy trên staging và production. Không chỉnh sửa file V2 để thêm một cột mới. Hãy tạo V5:

~~~text
V1__create_product.sql
V2__add_product_status.sql
V3__add_product_price.sql
V4__create_category.sql
V5__add_product_status_index.sql
~~~

Database đã áp dụng V2 giữ nguyên checksum của V2. Database mới chạy cả chuỗi. Nếu sửa V2, các môi trường đã áp dụng có thể báo checksum mismatch, còn môi trường mới lại nhận nội dung khác với môi trường cũ.

Quy tắc này giúp lịch sử migration bất biến sau khi phát hành.

### 3.6. Repeatable migrations

Flyway còn hỗ trợ repeatable migration, thường đặt tên theo mẫu:

~~~text
R__refresh_product_search_view.sql
~~~

Repeatable migration được áp dụng lại khi checksum thay đổi, sau các versioned migration pending. Chúng thường phù hợp với đối tượng có thể thay thế theo định nghĩa mới, chẳng hạn view, function hoặc procedure, tùy database và cách nhóm quản lý.

Không dùng repeatable migration để thay thế versioned migration cho mọi thay đổi schema. Một thay đổi có ý nghĩa lịch sử cần version rõ ràng và thứ tự xác định.

## 4. Cấu hình Flyway trong Spring Boot

Thêm dependency Flyway tương ứng với phiên bản Spring Boot và database driver của dự án. Với nhiều phiên bản hiện đại, core dependency và database-specific module có thể được tách riêng; cần dùng tài liệu tương thích với phiên bản đang chạy.

Ví dụ Gradle minh họa:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
}
~~~

Các tọa độ dependency và việc cần module database riêng phụ thuộc phiên bản Flyway. Dùng dependency management/BOM của Spring Boot khi có thể để tránh chọn phiên bản không tương thích.

### 4.1. Cấu hình application properties

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=$DB_PASSWORD

spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
spring.flyway.schemas=public
spring.flyway.table=flyway_schema_history
~~~

Trong môi trường thực tế, lấy mật khẩu từ secret manager hoặc environment variable; không commit credential vào source control.

Các thuộc tính Flyway thường dùng:

| Property | Mục đích |
| --- | --- |
| `spring.flyway.enabled` | Bật/tắt Flyway auto-configuration |
| `spring.flyway.locations` | Vị trí migration |
| `spring.flyway.schemas` | Schema được Flyway quản lý |
| `spring.flyway.default-schema` | Schema mặc định cho Flyway |
| `spring.flyway.table` | Tên bảng lịch sử |
| `spring.flyway.baseline-on-migrate` | Baseline database không rỗng khi chưa có history, cần dùng thận trọng |
| `spring.flyway.validate-on-migrate` | Kiểm tra trạng thái/checksum trước khi migrate |
| `spring.flyway.clean-disabled` | Ngăn thao tác clean phá hủy schema |

Tên property và mặc định có thể thay đổi theo Spring Boot version. Kiểm tra configuration metadata hoặc reference của release trong dự án.

### 4.2. Migration chạy khi nào?

Với Spring Boot auto-configuration, Flyway thường chạy trong quá trình khởi tạo application context khi datasource sẵn sàng. Boot điều phối thứ tự khởi tạo các thành phần database để migration được thực hiện trước những bean phụ thuộc schema trong các cấu hình thông thường.

Nếu dự án có nhiều datasource, nhiều transaction manager hoặc custom initialization, cần cấu hình rõ datasource và thứ tự migration. Không giả định migration chạy trên đúng database chỉ vì ứng dụng có một bean Flyway.

### 4.3. Tách quyền migration và quyền runtime

Trong production, tài khoản chạy migration thường cần quyền DDL như CREATE/ALTER/INDEX, còn tài khoản runtime của ứng dụng chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ. Tách hai quyền giúp giảm tác động nếu credential ứng dụng bị lộ hoặc code runtime gặp lỗi.

Có thể cấu hình tài khoản migration riêng qua deployment pipeline hoặc cấu hình Flyway riêng, tùy cách tổ chức ứng dụng. Không cấp quyền DDL cho runtime chỉ vì tiện nếu quy trình vận hành cho phép tách.

## 5. Liquibase: changelog và changeset

Liquibase mô tả lịch sử thay đổi trong changelog. Một changelog chứa nhiều changeset; mỗi changeset được định danh bằng `id`, `author` và đường dẫn file.

### 5.1. Cấu trúc thư mục

Ví dụ:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-product.yaml
        002-add-product-status.yaml
        003-add-product-price.yaml
~~~

Master changelog include các file changeset:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-product.yaml
  - include:
      file: db/changelog/changes/002-add-product-status.yaml
  - include:
      file: db/changelog/changes/003-add-product-price.yaml
~~~

Thứ tự include là một phần của lịch sử triển khai. Không đổi thứ tự các changeset đã áp dụng theo cách làm thay đổi ý nghĩa database.

### 5.2. Changeset tạo bảng

File `001-create-product.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-product
      author: team
      changes:
        - createTable:
            tableName: product
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
                  type: VARCHAR(80)
                  constraints:
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
        - addUniqueConstraint:
            tableName: product
            columnNames: sku
            constraintName: uk_product_sku
~~~

Change types giúp mô tả cấu trúc có mức trừu tượng cao hơn SQL. Liquibase sinh SQL phù hợp với database được cấu hình trong phạm vi change type hỗ trợ. Với chức năng vendor-specific, có thể dùng SQL change hoặc precondition phù hợp.

### 5.3. Changeset thêm cột và backfill

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-product-status
      author: team
      changes:
        - addColumn:
            tableName: product
            columns:
              - column:
                  name: status
                  type: VARCHAR(24)
        - update:
            tableName: product
            columns:
              - column:
                  name: status
                  value: ACTIVE
            where: status IS NULL
        - addNotNullConstraint:
            tableName: product
            columnName: status
            columnDataType: VARCHAR(24)
~~~

Ví dụ minh họa thứ tự thêm cột, backfill và đặt NOT NULL. Khả năng sinh SQL và tính nguyên tử phụ thuộc database; với bảng lớn, backfill có thể cần chia batch thành migration riêng để tránh transaction/lock kéo dài.

### 5.4. Bảng lịch sử Liquibase

Liquibase thường dùng hai bảng:

- `DATABASECHANGELOG`: ghi nhận changeset đã áp dụng, checksum, author, file path, thời điểm và trạng thái.
- `DATABASECHANGELOGLOCK`: quản lý lock để tránh nhiều Liquibase process đồng thời thay đổi schema.

Khi khởi động, Liquibase đọc changelog, so sánh với bảng lịch sử và áp dụng changeset chưa chạy. Nếu changeset đã chạy bị sửa nội dung, checksum validation có thể phát hiện khác biệt.

### 5.5. Changeset đã chạy cũng cần bất biến

Khi một changeset đã được triển khai ở bất kỳ môi trường dùng chung nào, không sửa nội dung để tạo thay đổi mới. Hãy thêm changeset mới.

Không xóa changeset khỏi changelog hoặc đổi id/author/path tùy tiện sau khi áp dụng. Các thông tin đó tham gia định danh changeset trong bảng lịch sử.

## 6. Rollback trong Liquibase và Flyway

Rollback schema phức tạp hơn rollback một transaction nghiệp vụ. DDL có thể không transactional trên một số database; thay đổi cấu trúc cũng có thể phá hủy dữ liệu không thể khôi phục bằng một câu lệnh ngược.

### 6.1. Rollback trong Liquibase

Liquibase cho phép khai báo rollback cho changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-display-label
      author: team
      changes:
        - addColumn:
            tableName: product
            columns:
              - column:
                  name: display_label
                  type: VARCHAR(200)
      rollback:
        - dropColumn:
            tableName: product
            columnName: display_label
~~~

Với một số change type, Liquibase có thể tự suy ra rollback; với thao tác phức tạp hoặc dữ liệu bị biến đổi, cần khai báo rollback rõ hoặc có kế hoạch forward-fix. Không giả định mọi change đều có rollback tự động an toàn.

### 6.2. Rollback trong Flyway

Flyway truyền thống tập trung vào versioned migrations theo hướng tiến lên. Undo migrations có khả năng và giới hạn phụ thuộc edition/cấu hình. Trong nhiều quy trình production, chiến lược được khuyến nghị là tạo migration mới để sửa lỗi hoặc đưa schema về trạng thái tương thích thay vì sửa file cũ đã chạy.

Ví dụ nếu V5 thêm một cột sai:

~~~text
V5__add_wrong_column.sql
V6__remove_wrong_column.sql
~~~

V6 tạo thay đổi tiếp theo có thể kiểm soát được. Tuy nhiên, nếu cột đã chứa dữ liệu có giá trị, xóa cột có thể mất dữ liệu; cần đánh giá trước khi rollback hoặc forward-fix.

### 6.3. Vì sao forward-fix thường an toàn hơn?

Sau khi migration đã chạy ở production:

- Có thể có application version mới đã ghi dữ liệu vào schema mới.
- Các bảng/cột mới có thể đã nhận dữ liệu quan trọng.
- Một số DDL không thể đảo ngược mà không mất dữ liệu.
- Các instance ứng dụng cũ/mới có thể đang chạy song song.

Migration mới cho phép sửa trạng thái có chủ đích và giữ lịch sử. Rollback vẫn cần cho tình huống phù hợp, nhưng không nên xem mọi DDL đều có một thao tác ngược tương đương.

## 7. Baseline cho database đã tồn tại

Một hệ thống có thể đã chạy lâu trước khi bắt đầu dùng Flyway hoặc Liquibase. Khi đó database không còn trống, nhưng chưa có bảng lịch sử migration.

### 7.1. Flyway baseline

Flyway hỗ trợ baseline để đánh dấu một database hiện hữu là đã ở một version nhất định. Những migration có version thấp hơn hoặc bằng baseline sẽ được xem là đã nằm trong trạng thái ban đầu; migration mới hơn tiếp tục được áp dụng.

`baseline-on-migrate` có thể giúp tự động baseline database không rỗng, nhưng bật bừa bãi rất nguy hiểm. Nếu Flyway nhận nhầm một database mới hoặc schema chưa hoàn chỉnh là baseline, các migration tạo bảng ban đầu có thể bị bỏ qua.

Quy trình an toàn:

1. Backup database.
2. Kiểm kê schema hiện tại.
3. Tạo baseline version phản ánh đúng trạng thái thực tế.
4. Xác nhận bảng lịch sử và version baseline.
5. Tạo migration tiếp theo cho thay đổi mới.
6. Thử trên bản sao database trước khi chạy production.

### 7.2. Liquibase changelog sync

Liquibase có các lệnh/operation để đồng bộ changelog history mà không chạy lại changeset, thường được dùng khi nhận quyền quản lý một database đã có schema tương ứng. Cần xác nhận schema hiện tại thực sự khớp với các changeset được đánh dấu đã chạy.

Nếu sync một changelog không tương ứng schema thực tế, Liquibase sẽ tin rằng các thay đổi đã được áp dụng dù database có thể thiếu bảng hoặc constraint. Hãy kiểm tra schema và thử trên bản sao trước khi thực hiện.

## 8. Thay đổi schema an toàn khi ứng dụng vẫn đang chạy

Production thường có rolling deployment: instance cũ và mới có thể cùng phục vụ request trong một khoảng thời gian. Migration cần tương thích với cả hai phiên bản trong giai đoạn chuyển tiếp.

Ví dụ cần đổi cột `name` thành `display_name`. Đổi tên trực tiếp rồi deploy app mới có thể làm app cũ lỗi vì app cũ vẫn đọc `name`.

Một chiến lược phổ biến là **expand-and-contract**.

### 8.1. Giai đoạn expand

Thêm cấu trúc mới mà code cũ vẫn hoạt động:

~~~sql
ALTER TABLE product
    ADD COLUMN display_name VARCHAR(200);
~~~

Chưa xóa cột `name`. Cả schema cũ và mới cùng tồn tại.

### 8.2. Backfill dữ liệu

Copy dữ liệu từ cột cũ sang cột mới:

~~~sql
UPDATE product
SET display_name = name
WHERE display_name IS NULL;
~~~

Với bảng lớn, backfill có thể cần job theo batch, theo ID range hoặc theo checkpoint để tránh một transaction rất dài.

### 8.3. Deploy code tương thích cả hai

Phiên bản ứng dụng mới có thể đọc cột mới và tạm thời ghi cả hai cột nếu cần hỗ trợ instance cũ. Cần thiết kế rõ nguồn dữ liệu có thẩm quyền trong giai đoạn dual-write và xử lý lỗi khi một lần ghi không cập nhật được cả hai.

### 8.4. Giai đoạn contract

Sau khi:

- Tất cả instance cũ đã được thay thế.
- Code không còn đọc/ghi cột cũ.
- Dữ liệu mới đã được backfill và xác minh.
- Không còn consumer hoặc job phụ thuộc cột cũ.

mới tạo migration xóa cột cũ.

~~~sql
ALTER TABLE product DROP COLUMN name;
~~~

Đây là migration phá hủy dữ liệu; phải xác nhận backup, retention và khả năng khôi phục trước khi chạy.

### 8.5. Không ghép thay đổi phá vỡ tương thích vào cùng một lần deploy

Tránh một release vừa xóa cột cũ vừa deploy code chỉ hiểu cột mới nếu rolling deployment có thể còn instance cũ. Tách thay đổi schema và thay đổi code thành nhiều bước tương thích để giảm downtime và tránh lỗi khi rollback application.

## 9. Migration cho bảng lớn và dữ liệu lớn

Một câu ALTER hoặc UPDATE có thể khóa bảng, tạo transaction dài hoặc làm tăng replication lag. Trước khi chạy migration trên bảng lớn, hãy đánh giá:

- Số hàng và kích thước bảng.
- Index hiện có và chi phí tạo index.
- Database có hỗ trợ tạo index online/concurrently không.
- DDL có transactional không.
- Thời gian lock dự kiến.
- Replication lag và thời gian backup/restore.
- Ảnh hưởng tới connection pool và latency ứng dụng.

### 9.1. Thêm cột nullable trước

Thêm cột nullable thường ít rủi ro hơn thêm cột NOT NULL cần backfill ngay, nhưng behavior vật lý vẫn phụ thuộc database và default expression.

Quy trình:

1. Thêm cột nullable.
2. Deploy code có thể đọc cả trạng thái null và non-null.
3. Backfill theo batch.
4. Xác minh không còn null.
5. Thêm NOT NULL constraint trong migration riêng.

### 9.2. Backfill theo batch

Không nhất thiết chạy một câu UPDATE trên hàng chục triệu dòng trong migration startup. Có thể dùng job có checkpoint:

~~~text
while còn bản ghi cần backfill:
    lấy một batch ID
    cập nhật batch
    commit
    ghi checkpoint
~~~

Job cần idempotent để chạy lại sau khi process dừng. Migration schema có thể chỉ thêm cột và index; data backfill được triển khai thành một bước vận hành riêng nếu cần thời gian dài.

### 9.3. Index và lock

Một số database hỗ trợ tạo index không khóa ghi trong toàn bộ thời gian xây dựng, nhưng cú pháp có thể yêu cầu chạy ngoài transaction. Flyway/Liquibase cần được cấu hình phù hợp với DDL đó. Không giả định mọi migration đều chạy trong một transaction duy nhất.

## 10. Data migration và schema migration

Hai loại thay đổi có liên quan nhưng khác mục tiêu:

- **Schema migration:** tạo/sửa bảng, cột, constraint, index, view.
- **Data migration:** chuyển đổi hoặc backfill giá trị dữ liệu hiện có.

Ví dụ chuyển trạng thái:

~~~sql
UPDATE product
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Đây là data migration dù được đặt trong một file schema migration.

Trước khi chạy data migration:

- Xác định dữ liệu nào cần chuyển.
- Định nghĩa giá trị cũ và mới.
- Kiểm tra số hàng dự kiến bị ảnh hưởng.
- Xác định cách chạy lại an toàn.
- Đánh giá thời gian và lock.
- Có cách đối soát sau khi chạy.

Không để data migration phụ thuộc vào dữ liệu ngẫu nhiên hoặc môi trường cụ thể. Nếu cần giá trị cấu hình theo môi trường, hãy truyền qua cơ chế được kiểm soát thay vì hard-code secret vào migration.

## 11. Tổ chức migration trong dự án Spring Data JDBC

Một cấu trúc gọn:

~~~text
src/main/java/
  com/example/catalog/
    product/
      Product.java
      ProductRepository.java
      ProductService.java

src/main/resources/
  db/
    migration/
      V1__create_product.sql
      V2__add_product_status.sql
      V3__add_product_price.sql
~~~

Hoặc với Liquibase:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-product.yaml
        002-add-product-status.yaml
~~~

Migration không nhất thiết phải nằm cạnh entity trong package Java. Hãy giữ một vị trí chuẩn để công cụ và người phát triển dễ tìm.

### 11.1. Mapping phải theo schema sau migration

Ví dụ migration thêm cột:

~~~sql
ALTER TABLE product
    ADD COLUMN description VARCHAR(1000);
~~~

Entity:

~~~java
@Table("product")
public record Product(
        @Id Long id,
        String sku,
        String name,
        String description
) {
}
~~~

Nếu tên cột không theo naming strategy, dùng `@Column`:

~~~java
@Column("product_description")
private String description;
~~~

Với Spring Data JDBC, mapping dựa trên metadata entity và schema thực tế. Migration phải được áp dụng trước khi code dùng cột mới chạy trên database.

### 11.2. Không dựa vào schema tự tạo từ entity

Không nên xem entity Java là nguồn duy nhất để tự động cập nhật production schema. Spring Data JDBC tập trung vào persistence mapping, không có cơ chế ORM schema auto-update tương đương một số cấu hình JPA.

Dùng migration tool làm nguồn sự thật cho schema. Nếu môi trường local/test có script tạo schema riêng, phải bảo đảm script đó không tạo ra cấu trúc khác với chuỗi migration chính.

### 11.3. Tắt cơ chế khởi tạo schema cạnh tranh

Nếu dự án dùng Flyway hoặc Liquibase làm schema manager, tránh để một script khởi tạo khác cũng tự tạo cùng bảng theo cách độc lập. Kiểm tra cấu hình Spring Boot liên quan đến SQL initialization, test schema scripts và các công cụ provisioning để chỉ có một quy trình chịu trách nhiệm cho thay đổi schema.

## 12. Cấu hình Liquibase trong Spring Boot

Thêm dependency Liquibase core và database driver tương ứng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
    implementation("org.liquibase:liquibase-core")
}
~~~

Ví dụ cấu hình:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=$DB_PASSWORD

spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml
spring.liquibase.default-schema=public
~~~

Các thuộc tính thường gặp:

| Property | Mục đích |
| --- | --- |
| `spring.liquibase.enabled` | Bật/tắt Liquibase |
| `spring.liquibase.change-log` | Đường dẫn master changelog |
| `spring.liquibase.default-schema` | Schema mặc định |
| `spring.liquibase.contexts` | Chọn changeset theo context |
| `spring.liquibase.labels` | Chọn changeset theo label |
| `spring.liquibase.drop-first` | Xóa schema trước khi chạy; rất nguy hiểm nếu bật nhầm |
| `spring.liquibase.liquibase-schema` | Schema lưu bảng quản lý Liquibase |

Tên property có thể khác theo phiên bản Spring Boot; tham khảo configuration metadata của release đang dùng.

### 12.1. Context và label

Liquibase có thể gắn context hoặc label cho changeset để chọn nhóm thay đổi. Ví dụ một changeset chỉ dành cho dữ liệu demo hoặc một nhóm database cụ thể.

Không dùng context để che giấu migration bắt buộc của production hoặc làm cho các môi trường có schema khác nhau mà không có lý do rõ. Những thay đổi cốt lõi cần được áp dụng nhất quán.

### 12.2. Preconditions

Liquibase hỗ trợ precondition để kiểm tra điều kiện trước khi chạy changeset, chẳng hạn database type, schema hoặc sự tồn tại của bảng/cột. Preconditions hữu ích khi cần xác nhận giả định, nhưng không thay thế việc kiểm kê schema và thử migration trên bản sao.

Nếu dùng `onFail: MARK_RAN`, cần rất thận trọng: Liquibase có thể đánh dấu changeset là đã chạy dù change không được thực thi. Chỉ dùng khi điều kiện chứng minh schema đã ở trạng thái đích và điều đó được kiểm tra đáng tin cậy.

## 13. Kiểm tra và vận hành migration

Migration là một phần của deployment, không chỉ là tác vụ lúc lập trình viên chạy ứng dụng.

### 13.1. Kiểm tra trước khi áp dụng

Trước production:

- Review SQL/changelog như review code.
- Chạy trên database sạch để xác nhận tạo mới.
- Chạy nâng cấp từ schema của phiên bản trước.
- Kiểm tra checksum và trạng thái migration.
- Đánh giá lock, thời gian và dung lượng.
- Xác nhận backup/restore.
- Kiểm tra quyền của tài khoản migration.
- Xác nhận application version mới tương thích schema trong giai đoạn rollout.

### 13.2. Flyway validate và info

Flyway cung cấp các thao tác quản trị như info, validate và migrate. Tùy cách tích hợp, có thể dùng API, Maven/Gradle plugin hoặc CLI:

- `info`: xem migration đã chạy, pending hoặc trạng thái.
- `validate`: kiểm tra migration hiện có có khớp lịch sử/checksum không.
- `migrate`: áp dụng migration pending.
- `repair`: sửa metadata lịch sử trong trường hợp được hiểu rõ.

`repair` không phải cách sửa file migration đã phát hành. Chỉ dùng sau khi đã xác định nguyên nhân và đồng bộ có chủ đích giữa schema thực tế với history. Không chạy repair chỉ để làm biến mất checksum mismatch mà chưa biết database đã nhận thay đổi nào.

### 13.3. Liquibase status, validate và update

Liquibase có các lệnh tương ứng:

- `status`: xem changeset còn pending.
- `validate`: kiểm tra changelog và cấu trúc changeset.
- `update`: áp dụng changeset chưa chạy.
- `rollback`: rollback theo tag/count/date nếu changeset có rollback khả dụng.
- `changelogSync`: đồng bộ history mà không chạy change, dùng trong baseline có kiểm soát.

Các lệnh thực tế có thể được chạy qua plugin, CLI hoặc API. Kiểm tra trạng thái và nội dung SQL dự kiến trước khi chạy production.

### 13.4. Không để mọi application instance tự đua nhau migrate

Trong deployment nhiều instance, cần bảo đảm migration chỉ được thực hiện theo cơ chế lock/coordination của công cụ và quy trình rollout. Flyway và Liquibase có cơ chế quản lý lịch sử/đồng bộ riêng, nhưng pipeline production thường đáng tin cậy hơn khi chạy migration như một bước có chủ đích trước hoặc trong giai đoạn triển khai, rồi mới rollout application.

Nếu ứng dụng tự migrate khi mỗi instance khởi động, kiểm tra behavior khi nhiều instance start đồng thời, timeout, quyền database và khả năng rollback deployment. Với môi trường production nghiêm ngặt, cân nhắc một migration job duy nhất trong pipeline.

## 14. Kiểm thử migration

Một test application chỉ chạy với schema được tạo thủ công có thể bỏ sót lỗi migration. Hãy kiểm tra chính chuỗi migration.

### 14.1. Test từ database trống

Tạo database mới và chạy toàn bộ migration. Sau đó xác nhận:

- Các bảng, cột và index tồn tại.
- Primary key, foreign key, unique và CHECK constraint đúng.
- Repository có thể insert/read/update aggregate.
- Column type và nullability tương thích mapping.

### 14.2. Test nâng cấp từ phiên bản cũ

Không chỉ test từ database trống. Cần dựng schema tại một version trước, chèn dữ liệu đại diện rồi chạy migration mới:

~~~text
Create database
  -> apply V1
  -> insert legacy rows
  -> apply V2, V3, V4
  -> verify schema and transformed data
~~~

Điều này phát hiện lỗi backfill, default, constraint và đổi kiểu trên dữ liệu thực tế.

### 14.3. Test với Testcontainers

Testcontainers giúp chạy database cùng loại với production trong integration test. Ví dụ khung test Spring Data JDBC:

~~~java
@DataJdbcTest
@Testcontainers
class ProductRepositoryMigrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }

    @Autowired
    ProductRepository products;

    @Test
    void repositoryWorksWithMigratedSchema() {
        // Insert/read/update một aggregate trên schema do migration tạo.
    }
}
~~~

Đây là khung minh họa; dependency Testcontainers, database image, cấu hình migration và repository cần được khai báo trong dự án. Kiểm tra Spring Boot test slice có bật đúng migration auto-configuration. Nếu test slice tắt một số auto-configuration, cấu hình rõ để migration chạy trước test.

### 14.4. Test nhiều dialect nếu ứng dụng hỗ trợ nhiều database

SQL migration viết cho PostgreSQL có thể không chạy trên MySQL hoặc SQL Server. Nếu ứng dụng tuyên bố hỗ trợ nhiều database, cần có bộ migration và test tương ứng cho từng dialect, hoặc dùng Liquibase change type portable ở nơi có thể.

Không lấy H2 làm bằng chứng duy nhất cho PostgreSQL/MySQL production; khác biệt DDL, kiểu dữ liệu, locking và function có thể làm test xanh nhưng production lỗi.

## 15. Chiến lược triển khai production

Một pipeline triển khai có thể gồm:

~~~text
Build application artifact
        |
        v
Review and validate migration
        |
        v
Backup / verify recovery plan
        |
        v
Run migration job
        |
        v
Verify schema and migration history
        |
        v
Deploy compatible application version
        |
        v
Monitor errors and database health
~~~

Thứ tự chính xác phụ thuộc loại migration và chiến lược rollout. Với expand-and-contract, migration mở rộng có thể chạy trước app mới; migration xóa cấu trúc cũ phải chờ mọi consumer cũ đã được loại bỏ.

### 15.1. Migration trước hay sau application deploy?

Không có một thứ tự duy nhất cho mọi thay đổi:

- **Thêm cột nullable:** thường có thể migrate trước, vì code cũ bỏ qua cột mới.
- **Thêm cột NOT NULL không có default:** cần backfill hoặc thay đổi tương thích trước.
- **Đổi tên/xóa cột:** thường cần nhiều release expand-and-contract.
- **Thêm constraint:** cần xác minh dữ liệu hiện tại hợp lệ trước khi bật.
- **Đổi kiểu dữ liệu:** có thể cần shadow column và backfill.

Hãy xác định compatibility matrix giữa schema và application version cũ/mới trước khi chọn thứ tự.

### 15.2. Backup và restore

Migration phá hủy dữ liệu hoặc đổi kiểu có rủi ro cao cần backup và quy trình restore đã thử. Một backup chưa từng restore thử không phải bằng chứng đủ về khả năng phục hồi.

Rollback migration không thay thế backup. Nếu migration xóa cột, rollback thêm lại cột rỗng không thể khôi phục giá trị đã mất.

### 15.3. Giám sát sau migration

Theo dõi:

- Trạng thái migration history.
- Startup error của ứng dụng.
- Lỗi SQL như missing column/table hoặc type mismatch.
- Latency và lock wait.
- Connection pool và replication lag.
- Số lượng hàng sau backfill.
- Error rate của repository/query liên quan.

Giữ lại log migration để có thể điều tra phiên bản nào đã chạy và mất bao lâu.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Sửa migration đã chạy | Checksum/history lệch giữa môi trường | Thêm migration mới |
| Chỉ chạy SQL thủ công trên production | Môi trường khác không tái tạo được schema | Lưu mọi thay đổi vào migration source control |
| Thêm NOT NULL khi bảng còn null | Migration thất bại | Add nullable, backfill, validate rồi add constraint |
| Dùng baseline tùy tiện | Bỏ qua migration cần thiết | Kiểm kê schema và baseline đúng version |
| Dùng repair/changelogSync để che lỗi | History không còn phản ánh schema thật | Xác minh trạng thái thực tế trước khi sửa metadata |
| Dùng cả Flyway và Liquibase cho cùng schema | Hai lịch sử và thứ tự thay đổi cạnh tranh | Chọn một công cụ quản lý |
| Chỉ test database sạch | Không phát hiện lỗi nâng cấp dữ liệu cũ | Test từ schema phiên bản trước |
| Dùng H2 thay cho DB production | Khác biệt dialect/DDL bị bỏ sót | Test bằng database mục tiêu |
| Migration update hàng triệu dòng trong một transaction | Lock dài, timeout, replication lag | Backfill theo batch/job có checkpoint |
| Xóa cột ngay trong release đổi code | Instance cũ lỗi khi rolling deploy | Dùng expand-and-contract |
| Tạo index lớn trong transaction không phù hợp | Lock hoặc migration thất bại | Dùng cơ chế online/concurrent theo database |
| Cho mọi app instance tự migrate | Khởi động đồng thời và quyền DDL khó kiểm soát | Dùng migration job/pipeline có coordination |
| Runtime user có quyền DDL không cần thiết | Tăng phạm vi tác động khi credential bị lộ | Tách migration user và application user |
| Nghĩ rollback DDL luôn khôi phục dữ liệu | Dữ liệu đã xóa không tự xuất hiện lại | Forward-fix, backup và restore plan |

## 17. Khi nào nên chọn Flyway, khi nào chọn Liquibase?

Chọn theo nhu cầu và cách làm của nhóm:

| Nhu cầu | Flyway thường phù hợp | Liquibase thường phù hợp |
| --- | --- | --- |
| Nhóm thích viết SQL trực tiếp | Rất phù hợp | Có thể dùng SQL changeset |
| Muốn migration version đơn giản, dễ đọc | Phù hợp | Cũng hỗ trợ nhưng cấu trúc changelog nhiều lớp hơn |
| Muốn mô tả change bằng cấu trúc portable | Ít tập trung vào trừu tượng hóa | Phù hợp với change types |
| Cần preconditions, contexts, labels | Có cơ chế tương ứng nhưng mô hình khác | Là thế mạnh của Liquibase |
| Cần rollback khai báo theo changeset | Phụ thuộc edition/chiến lược | Có rollback blocks và hỗ trợ sinh rollback cho một số change |
| Database dùng nhiều SQL đặc thù | SQL migration trực tiếp thuận tiện | Có thể dùng SQL changeset/precondition |
| Dự án đã có lịch sử migration | Tiếp tục nếu đang dùng Flyway | Tiếp tục nếu đang dùng Liquibase |

Đừng chọn chỉ theo số lượng tính năng. Hãy cân nhắc khả năng review, kiến thức SQL của nhóm, database mục tiêu, cách pipeline triển khai và chi phí vận hành lịch sử migration.

## 18. Checklist cho một migration mới

Trước khi commit migration, người phát triển nên trả lời:

1. Migration có tên và version/id duy nhất không?
2. File đã áp dụng ở môi trường dùng chung chưa? Nếu có, có đang sửa file cũ không?
3. Thay đổi có tương thích với application version đang chạy không?
4. Bảng có dữ liệu cũ cần backfill không?
5. Nullability, default, unique và foreign key có đúng semantics không?
6. Có cần index không; chi phí tạo index trên bảng lớn ra sao?
7. DDL có transactional trên database mục tiêu không?
8. Migration có thể chạy lại hoặc phục hồi khi thất bại theo cách nào?
9. Có cần backup, restore hoặc forward-fix plan không?
10. Integration test có chạy chuỗi migration từ đầu và nâng cấp từ version cũ không?
11. Mapping Spring Data JDBC có khớp schema sau migration không?
12. Quyền database và deployment order đã được xác định chưa?

## 19. Quy trình làm việc từ local đến production

Một workflow thực tế:

1. **Xác định thay đổi schema:** cột, bảng, constraint, index hoặc data conversion.
2. **Tạo migration mới:** dùng version Flyway hoặc changeset Liquibase mới; không sửa lịch sử đã áp dụng.
3. **Cập nhật mapping:** sửa entity, repository và query theo schema đích.
4. **Chạy migration trên database local sạch:** bảo đảm schema được tạo từ đầu.
5. **Test nâng cấp:** dựng schema cũ có dữ liệu rồi chạy migration mới.
6. **Kiểm tra compatibility:** code cũ và mới có thể cùng chạy trong giai đoạn rollout không?
7. **Review hiệu năng/lock:** nhất là ALTER, backfill và tạo index trên bảng lớn.
8. **Chạy CI integration test:** dùng database mục tiêu hoặc Testcontainers.
9. **Triển khai qua migration job:** xác minh history và schema trước khi rollout application.
10. **Giám sát sau deploy:** theo dõi startup, query errors, latency và dữ liệu đã backfill.

## Ghi nhớ

Flyway và Liquibase giúp quản lý schema như một lịch sử thay đổi có version, được lưu trong source control và áp dụng theo thứ tự. Flyway thường dùng các SQL migration như `V1__create_product.sql` và bảng `flyway_schema_history`; Liquibase dùng changelog/changeset với id, author, checksum và các bảng `DATABASECHANGELOG`, `DATABASECHANGELOGLOCK`.

Trong Spring Data JDBC, migration chuẩn bị schema để entity và repository sử dụng; nó không thay thế mapping hoặc domain logic. Chọn một công cụ làm nguồn sự thật, không sửa migration đã áp dụng, baseline database cũ có kiểm kê, và kiểm thử cả database sạch lẫn đường nâng cấp từ dữ liệu cũ. Khi production chạy rolling deployment, dùng expand-and-contract để code cũ và mới cùng tương thích. Với bảng lớn hoặc thay đổi phá hủy dữ liệu, đánh giá lock, backfill theo batch, backup và forward-fix trước khi triển khai. Cuối cùng, chạy migration có kiểm soát trong pipeline và xác minh schema history trước khi đưa application version mới vào phục vụ.
