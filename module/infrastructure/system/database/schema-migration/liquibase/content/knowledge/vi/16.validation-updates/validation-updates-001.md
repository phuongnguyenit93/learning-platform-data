# Kiểm tra cấu trúc changelog bằng `validate` trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một migration chỉ đáng tin cậy khi đội ngũ có thể xác nhận changelog được tổ chức đúng, tài nguyên được tìm thấy, các changeset có định danh hợp lệ và lịch sử đã triển khai không bị sửa ngoài ý muốn.

Lệnh **`liquibase validate`** là bước kiểm tra sớm phục vụ mục tiêu đó. Nó phân tích changelog và thực hiện những quy tắc validation mà Liquibase hỗ trợ, **không áp dụng các thay đổi schema/dữ liệu được mô tả trong changeset**. Tuy vậy, thông báo “validation thành công” **không có nghĩa** migration chắc chắn chạy được, dữ liệu hiện tại đáp ứng mọi ràng buộc hoặc rollback an toàn. Bài học thuộc phần **Kiểm tra và cập nhật**, giải thích cách dùng `validate` đúng phạm vi, đọc lỗi và kết hợp với quy trình thử migration thực tế.

## 1. `validate` làm gì, khác `update` như thế nào?

Liquibase nhận vào một changelog gốc, đọc các file được tham chiếu và xây dựng mô hình các changeset. Khi chạy `validate`, công cụ thực hiện những bước kiểm tra mà phiên bản Liquibase và các change type hỗ trợ, nhằm phát hiện lỗi **trước khi thực thi migration**.

| Lệnh | Mục đích | Có áp dụng các thay đổi trong changelog không? |
|---|---|---|
| `validate` | Kiểm tra changelog, các cấu trúc/thuộc tính có thể xác thực và tính nhất quán lịch sử | **Không** chạy DDL/DML của changeset |
| `status` | Xem các changeset chưa được ghi nhận hoàn thành, theo bộ lọc được cấu hình | Không thực thi migration |
| `update-sql` | Sinh SQL dự kiến cho các changeset đủ điều kiện chạy | Không thực thi chính SQL migration được preview |
| `update` | Áp dụng changeset chưa chạy, theo context/label/DBMS/precondition và lịch sử | **Có**, thay đổi database thật |
| Lệnh rollback tương ứng | Hoàn tác một số changeset theo chiến lược đã chọn | **Có thể thay đổi hoặc xóa dữ liệu/schema** |

`validate` hữu ích khi một tác giả vừa sửa YAML, XML, JSON hoặc formatted SQL changelog; khi pull request thay đổi cấu trúc thư mục; hoặc khi CI/CD cần chặn một bản release có changelog không thể phân tích. Lệnh này có thể dùng sớm, nhưng kết quả cần được bổ sung bởi `update-sql` và thử `update` trên database dùng riêng.

**Giới hạn về tác động:** `validate` không chạy các câu SQL thay đổi dữ liệu của changeset. Tuy nhiên, tùy phiên bản, cấu hình và cách kết nối, quá trình sử dụng Liquibase vẫn có thể truy cập metadata hoặc khởi tạo thành phần phục vụ quản lý lịch sử. Không tuyên bố một cách tuyệt đối rằng mọi lần chạy `validate` là “không hề tương tác với database”; luôn thử bằng quyền và môi trường phù hợp.

## 2. Ba lớp kiểm tra cần phân biệt

Một changelog có thể hợp lệ về YAML nhưng sai về cấu trúc Liquibase; cũng có thể hợp lệ với Liquibase nhưng chạy SQL thất bại trên database thực tế.

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Cú pháp định dạng** | YAML/XML/JSON/SQL formatted changelog có được parser đọc không? | YAML thụt dòng sai, chuỗi có dấu `:` không được quote |
| **Cấu trúc và định danh Liquibase** | `databaseChangeLog`, `changeSet`, các change type, thuộc tính và đường dẫn có phù hợp không? | Thiếu `id`, trùng bộ định danh, `include` trỏ tới file không tồn tại |
| **Ngữ nghĩa trên DBMS/dữ liệu** | SQL cuối cùng có hợp lệ và có thực thi được trên trạng thái database đích không? | Bảng đã tồn tại, có dữ liệu trùng khi thêm `UNIQUE`, thiếu quyền `ALTER` |

Lệnh `validate` tập trung vào các kiểm tra **mà Liquibase triển khai cho lớp 1–2** và một phần kiểm tra liên quan đến lịch sử/DBMS. Nó không thay thế một phép thử SQL trên database thật cho lớp 3. Mức độ xác thực thuộc tính và file phụ trợ có thể khác theo **phiên bản Liquibase, loại changelog và extension**; không nên giả định mọi lỗi cấu trúc đều bị `validate` chặn.

Ví dụ: `validate` có thể đọc được một changeset `addUniqueConstraint` hợp lệ, trong khi lần `update` sau thất bại vì bảng đang có hai hàng cùng email. Ràng buộc UNIQUE được database cưỡng chế ở thời điểm thực thi, không chỉ bằng việc phân tích YAML.

## 3. Cấu trúc changelog hợp lệ để thực hành

Sử dụng một dự án Java với tài nguyên Liquibase:

```text
src/main/resources/
└── db/
    └── changelog/
        ├── master.yaml
        └── changes/
            ├── 001-create-category.yaml
            └── 002-add-category-code.yaml
```

File `master.yaml` khai báo hai file con theo thứ tự:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-category.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-category-code.yaml
      relativeToChangelogFile: true
```

File `changes/001-create-category.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-category"
      author: "db-team"
      changes:
        - createTable:
            tableName: demo_category
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: demo_category
```

File `changes/002-add-category-code.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "002-add-category-code"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_category
            columns:
              - column:
                  name: code
                  type: VARCHAR(40)
      rollback:
        - dropColumn:
            tableName: demo_category
            columnName: code
```

Những đặc điểm cần nhận diện:

- `databaseChangeLog` là cấu trúc gốc và bên dưới là danh sách các phần tử.
- `include` trỏ tới file phụ; `relativeToChangelogFile: true` làm đường dẫn tương đối với file chứa include.
- Mỗi `changeSet` có `id` và `author`. Đường dẫn changelog còn góp phần tạo định danh lịch sử.
- `changes` là danh sách change type, ở đây `createTable` và `addColumn`.
- `columns` là danh sách các `column`, mỗi cột có tên và kiểu.
- `rollback` đã được mô tả tường minh để minh họa, nhưng **sự hiện diện của rollback trong YAML không chứng minh rollback an toàn với dữ liệu thật**.

`validate` phải tìm được master và các file include. Nếu cố tình bỏ file `002-add-category-code.yaml` khỏi artifact nhưng vẫn giữ tham chiếu, bước phân tích changelog sẽ gặp lỗi đường dẫn. Trên bản build đã đóng gói, kiểm tra thêm rằng tài nguyên dưới `src/main/resources` thực sự có trong JAR.

## 4. Chuẩn bị môi trường CLI cho phép validate

Để chạy `validate` trong tình huống thông dụng, cần:

1. Một phiên bản **Liquibase CLI** được thống nhất trong dự án.
2. Một **changelog gốc** hợp lệ, với các file include có thể được ResourceAccessor tìm thấy.
3. Cấu hình database khi CLI/phiên bản/changeset yêu cầu: JDBC URL, tài khoản có quyền cần thiết và JDBC driver.
4. Quy tắc môi trường nhất quán về search path, schema mặc định và tên tài nguyên changelog.

Giả sử bạn đứng ở thư mục gốc dự án, có file `liquibase.properties` với nội dung minh họa:

```properties
changeLogFile=src/main/resources/db/changelog/master.yaml
url=jdbc:postgresql://localhost:5432/liquibase_training
username=liquibase_runner
```

Ở đây `liquibase_training` là **database thử nghiệm** mà người thực hành tự chuẩn bị. Mật khẩu không được hardcode trong ví dụ: cung cấp qua secret manager hoặc biến môi trường phù hợp với phiên bản Liquibase/CI đang dùng. Trong môi trường thực tế, cần bảo vệ cả URL nếu nó chứa thông tin nhạy cảm, giới hạn quyền và tránh in credential trong log.

Lệnh cơ bản:

```bash
liquibase --defaults-file=liquibase.properties validate
```

Nếu dùng cách truyền changelog trực tiếp, một cách minh họa là:

```bash
liquibase --changelog-file=src/main/resources/db/changelog/master.yaml validate
```

Các lệnh giả định Liquibase tìm được JDBC driver và thông tin kết nối còn thiếu. Vị trí cú pháp option, tên tham số hoặc yêu cầu kết nối có thể khác nhau giữa phiên bản Liquibase; kiểm tra `liquibase --help` của bản đang dùng. Nếu CLI có cấu hình search path để coi `src/main/resources` là root, có thể dùng đường dẫn tài nguyên `db/changelog/master.yaml` thay vì tiền tố thư mục source; điều quan trọng là **giữ cách phân giải đường dẫn ổn định giữa các lần chạy**.

### 4.1. Khi chạy Spring Boot

Trong Spring Boot, cấu hình changelog gốc thông dụng:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Khi Spring Boot khởi động, tích hợp Liquibase có thể thực hiện luồng cập nhật schema theo cấu hình ứng dụng. **Đó không phải là việc chạy riêng lệnh CLI `validate`**. Dù Liquibase có các bước kiểm tra khi thực thi, không nên coi việc ứng dụng khởi động thành công là thay thế hoàn toàn cho một bước validation chuyên biệt trong CI và phép thử migration độc lập.

Muốn kiểm tra artifact được triển khai, phải xác nhận file `master.yaml` và các file con có trong classpath/JAR của bản build đó. Đường dẫn `src/main/resources` chỉ là vị trí trong source, không nhất thiết tồn tại trên máy chạy production.

## 5. `validate` có thể phát hiện những lỗi nào?

Nhóm lỗi phổ biến và cách hiểu:

| Nhóm lỗi | Tình huống | Lưu ý |
|---|---|---|
| Không parse được changelog | YAML sai cấu trúc hoặc XML không hợp lệ | Thường thất bại ngay khi đọc file |
| File changelog không tồn tại | `master.yaml` hoặc file `include` không được tìm thấy | Kiểm tra relative path, search path, classpath và đóng gói |
| Cấu trúc changeset sai | Thiếu khóa/thuộc tính bắt buộc, sai tên change type | Khả năng phát hiện phụ thuộc parser, change type và phiên bản |
| Định danh changeset bị trùng | Cùng `id`, `author` và đường dẫn định danh trong bộ changelog | Có thể dẫn tới lỗi validation trùng changeset |
| Tham chiếu hoặc thuộc tính không phù hợp | Một số change type có cấu hình thiếu hoặc không được hỗ trợ | Không phải mọi lỗi SQL đều được phát hiện |
| Checksum/history không tương thích | Một changeset đã chạy bị thay đổi nội dung hoặc danh tính lịch sử bị đổi | Cần đối chiếu `DATABASECHANGELOG`, cấu hình và bản changelog đã triển khai |
| Extension/schema validation | Định dạng hoặc extension có quy tắc riêng | Cần kiểm tra thông báo lỗi thực tế của đúng phiên bản |

**Điểm quan trọng:** kết quả `validate` phụ thuộc khả năng đọc được changelog và ngữ cảnh của lệnh. Nếu database chưa tồn tại hoặc URL/JDBC driver sai, lệnh có thể thất bại **trước cả khi đến phần phân tích cấu trúc**. Khi đó không thể kết luận changelog hợp lệ hay không; phải phân loại đúng nguyên nhân.

## 6. Các ví dụ lỗi cần nhận ra khi đọc YAML

Mỗi ví dụ trong phần này mô tả **một phiên bản cố ý sai**, không phải những phần cần ghép vào cùng changelog hợp lệ.

### 6.1. Sai cấp thụt dòng

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-category"
      author: "db-team"
      changes:
        - createTable:
            tableName: demo_category
          columns:
            - column:
                name: id
                type: BIGINT
```

Ở đây `columns` nằm cùng cấp với `createTable` trong item, **không** nằm bên trong `createTable`. YAML parser có thể vẫn tạo ra một cấu trúc mapping hợp lệ; Liquibase lại không nhận được `columns` ở vị trí mong đợi. Sửa bằng cách thụt `columns` vào cùng cấp với `tableName` của `createTable`. Đây là ví dụ tiêu biểu cho khác biệt giữa **YAML syntactically valid** và **Liquibase structurally valid**.

### 6.2. Thiếu dấu `-` ở danh sách

```yaml
columns:
  column:
    name: id
    type: BIGINT
  column:
    name: name
    type: VARCHAR(120)
```

Phần trên đặt hai khóa `column` trùng nhau trong một mapping. Một số parser từ chối, một số parser có thể ghi đè hoặc bỏ qua; dù cách nào, đó không phải cấu trúc danh sách cột đúng. Cần viết:

```yaml
columns:
  - column:
      name: id
      type: BIGINT
  - column:
      name: name
      type: VARCHAR(120)
```

### 6.3. Sai thuộc tính Liquibase

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-rename-category"
      author: "db-team"
      changes:
        - renameColumn:
            tableName: demo_category
            oldColumnName: name
            newColumn: display_name
```

`newColumn` trong ví dụ là tên thuộc tính **không đúng mục đích**: change type `renameColumn` sử dụng thuộc tính như `newColumnName` để chỉ tên cột mới. Tùy cơ chế parser/schema validation, công cụ có thể báo thuộc tính không được nhận diện hoặc thiếu thuộc tính bắt buộc. Sửa thành:

```yaml
        - renameColumn:
            tableName: demo_category
            oldColumnName: name
            newColumnName: display_name
            columnDataType: VARCHAR(120)
```

`columnDataType` có thể cần thiết hoặc được khuyến nghị tùy DBMS/change type; việc đặt nó trong ví dụ không chứng minh SQL rename là portable với mọi hệ quản trị.

### 6.4. Trùng định danh changeset

Hai changeset cùng `id`, `author` và **cùng đường dẫn định danh changelog** được xem là trùng trong mô hình thông thường:

```yaml
databaseChangeLog:
  - changeSet:
      id: "004-fix-code"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_category
            columns:
              - column:
                  name: code
                  type: VARCHAR(40)
  - changeSet:
      id: "004-fix-code"
      author: "db-team"
      changes:
        - addColumn:
            tableName: demo_category
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
```

Đừng giải quyết bằng cách tùy tiện đổi `author` hoặc chuyển file để che sự trùng lặp. Hãy đặt định danh mới phản ánh thay đổi thực sự, giữ nguyên các changeset đã chạy. Một số phiên bản/cấu hình Liquibase có cơ chế riêng liên quan tới trùng định danh; chính sách dự án vẫn nên là mỗi changeset có bộ định danh ổn định và không mơ hồ.

### 6.5. Include thiếu tài nguyên

```yaml
databaseChangeLog:
  - include:
      file: changes/099-does-not-exist.yaml
      relativeToChangelogFile: true
```

Nếu file chưa có trong source, hoặc được tạo trong source nhưng không được copy vào artifact runtime, Liquibase không thể dựng đầy đủ cây changelog. Đối chiếu đường dẫn **từ file cha**, kiểm tra đúng dấu `/` và nội dung artifact, không mặc định working directory của CI giống máy local.

### 6.6. Sai kiểu scalar có thể dẫn tới lỗi khó nhận ra

```yaml
databaseChangeLog:
  - changeSet:
      id: "001"
      author: "db-team"
      comment: "Mã: 001, giữ nguyên chữ số đầu"
      changes:
        - sql:
            sql: "SELECT 1"
```

Với `id`, `author` hoặc mã dữ liệu, chủ động đặt dấu nháy nếu giá trị có hình dạng số, ngày, boolean hoặc ký tự đặc biệt. Không mặc định các chuỗi trần như `001`, `2026-11-19` hay `false` được parser giữ đúng ý nghĩa văn bản. `validate` không phải công cụ kiểm tra đầy đủ ý nghĩa nghiệp vụ của từng scalar: một giá trị bị đổi kiểu đôi khi vẫn tạo ra changelog có thể parse được.

## 7. Validation với checksum và lịch sử `DATABASECHANGELOG`

Định danh thông thường của một changeset gồm:

```text
id + author + đường dẫn file changelog
```

Đường dẫn có thể được xác định bằng `logicalFilePath` khi cấu hình. Bảng `DATABASECHANGELOG` lưu định danh, thời điểm/kết quả thực thi, checksum và metadata khác. Vì vậy, `validate` không chỉ liên quan đến văn bản hiện tại: khi có kết nối và lịch sử được truy cập, nó còn có thể phát hiện khác biệt giữa changeset đã triển khai với phiên bản đang đưa vào chạy.

Giả sử một changeset đã được chạy:

```yaml
databaseChangeLog:
  - changeSet:
      id: "010-create-audit"
      author: "db-team"
      changes:
        - createTable:
            tableName: demo_audit
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
```

Sau khi triển khai, một người sửa `tableName: demo_audit` thành `tableName: audit_event` **trong chính changeset cũ**. Khi so sánh với lịch sử, Liquibase có thể báo checksum khác và chặn quá trình. Một số thuộc tính như `runOnChange` hoặc cấu hình chấp nhận checksum có cơ chế riêng, nhưng chúng không biến việc tự ý sửa lịch sử thành quy trình an toàn.

### 7.1. Quy tắc sửa lỗi sau khi đã chạy

Nếu changeset **chưa từng chạy ở bất kỳ môi trường nào**, có thể sửa trực tiếp trong nhánh đang phát triển, rồi validation lại.

Nếu changeset **đã chạy ở ít nhất một môi trường**, ưu tiên:

1. Khôi phục nội dung changelog đã phát hành cho bộ định danh cũ.
2. Tạo **changeset mới** để thay đổi schema/dữ liệu mong muốn.
3. Kiểm tra thứ tự migration và ảnh hưởng ở các môi trường đã triển khai.
4. Dùng `validate`, `status`, `update-sql` và thử trên bản sao database có lịch sử giống thực tế.

Không xóa bảng `DATABASECHANGELOG`, sửa thủ công `MD5SUM` hoặc gọi thao tác reset checksum hàng loạt chỉ để lệnh `validate` báo thành công. Nếu cần xử lý ngoại lệ có chủ đích, phải hiểu lý do, xác định đúng changeset và bảo toàn khả năng kiểm toán.

### 7.2. Thay đổi đường dẫn cũng quan trọng

Ví dụ một changeset từng được chạy từ `src/main/resources/db/changelog/changes/010.yaml`, nhưng sau khi chuyển sang classpath/JAR được nhận diện là `db/changelog/changes/010.yaml`. Nội dung có thể không đổi nhưng **đường dẫn định danh** đã khác, dẫn tới việc Liquibase nhận diện như một changeset khác nếu không có quy tắc `logicalFilePath` nhất quán.

`validate` không thay thế việc chủ động đối chiếu `FILENAME` trong lịch sử. Trước khi đổi layout hoặc chuyển cách chạy giữa CLI và Spring Boot, xác nhận định danh hiện có trên database của các môi trường, không tự phát sinh thêm bản ghi mới bằng cách chạy `update` để “thử xem”.

Ví dụ truy vấn (PostgreSQL với tên metadata không quote):

```sql
SELECT id, author, filename, md5sum, exectype, dateexecuted
FROM databasechangelog
WHERE id = '010-create-audit';
```

## 8. Những vấn đề `validate` không bảo đảm

Đây là ranh giới quan trọng nhất để tránh cảm giác an toàn giả:

| Vấn đề | Vì sao `validate` chưa đủ? | Cần bổ sung |
|---|---|---|
| SQL chạy được trên DBMS cụ thể | SQL hoặc change type có thể chỉ thất bại lúc engine thực thi | `update-sql` + chạy trên database cùng loại/phiên bản |
| Dữ liệu hiện tại đáp ứng constraint | Duplicate, `NULL` hoặc foreign key lỗi chỉ lộ ở DDL/DML | Query kiểm tra dữ liệu + precondition + migration test |
| Quyền DDL/DML đầy đủ | Tài khoản có thể đọc metadata nhưng thiếu quyền thay schema | Thử bằng đúng vai trò migration trong staging |
| Tác động lock/hiệu năng | Tạo index hoặc backfill có thể khóa bảng hoặc sinh log lớn | Đo trên dữ liệu/khối lượng tương đương |
| Rollback thực sự an toàn | Nội dung rollback có thể xóa dữ liệu hoặc không phục hồi giá trị cũ | Preview và diễn tập rollback trên database có thể khôi phục |
| Thứ tự nghiệp vụ đúng | Changelog hợp lệ vẫn có thể thiếu bước backfill | Review thiết kế, test theo trạng thái dữ liệu thật |
| Context/label phù hợp với môi trường | Bộ lọc phụ thuộc cấu hình runtime và nội dung changelog | `status`/`update-sql` với **cùng filter** sẽ dùng khi cập nhật |
| Không có race condition | Kết quả kiểm tra có thể lỗi thời khi nhiều ứng dụng ghi cùng lúc | Constraint, transaction, kế hoạch đồng bộ triển khai |
| Không chứa dữ liệu bí mật | Parser không đánh giá chính sách dữ liệu nhạy cảm | Secret scanning và code review |
| An toàn khi chuyển artifact | Tài nguyên trong IDE có thể khác JAR/container | Validate/test artifact cuối cùng |

Ví dụ, đoạn sau có thể hợp lệ về cấu trúc:

```yaml
databaseChangeLog:
  - changeSet:
      id: "020-make-email-unique"
      author: "db-team"
      changes:
        - addUniqueConstraint:
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
```

Nhưng nếu `customer` đã chứa hai hàng cùng email, database sẽ từ chối tạo ràng buộc. Hãy truy vấn dữ liệu trùng và có kế hoạch làm sạch trước. Tương tự, `validate` đọc được một changeset `sql` không có nghĩa rằng mọi câu SQL đặc thù DBMS của changeset đều có cú pháp hợp lệ khi thực thi.

## 9. Quy trình kiểm chứng từ local đến CI/CD

Một quy trình đáng tin cậy thực hiện kiểm tra theo thứ tự tăng dần mức tác động:

```text
Sửa changelog trong Git
        |
        v
YAML/XML lint + kiểm tra file được include
        |
        v
Liquibase validate (cùng phiên bản phát hành)
        |
        v
status và update-sql với đúng context/label
        |
        v
update trên database tạm có schema/lịch sử gần thực tế
        |
        v
Kiểm tra dữ liệu + thử rollback khi có thể
        |
        v
Review, approval, deploy bằng artifact đã kiểm chứng
```

### 9.1. Trên máy phát triển

Với `liquibase.properties` đã cấu hình:

```bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status
liquibase --defaults-file=liquibase.properties update-sql
```

Chỉ sau khi đã xem SQL và xác minh database dùng riêng:

```bash
liquibase --defaults-file=liquibase.properties update
```

Không chạy `update` vào database production bằng lệnh sao chép từ bài học. Cần chắc chắn URL, schema, credential và quyền là những giá trị của môi trường mà mình được phép thao tác.

### 9.2. Trong CI/CD

Pipeline nên pin phiên bản Liquibase, DBMS driver và extension; dựng cùng changelog/artifact sẽ được triển khai, thay vì validate một bản khác trong workspace. Bước `validate` phải **chặn** pipeline nếu thoát với mã lỗi; không chạy tiếp `update` chỉ vì log có một vài dòng “OK”.

Ví dụ logic shell:

```bash
set -e
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status
liquibase --defaults-file=liquibase.properties update-sql
# Kiểm tra hoặc phê duyệt SQL trước job triển khai riêng
```

Chú ý: `set -e` thuộc shell trong ví dụ, không phải tham số Liquibase. Trên Windows/PowerShell, cơ chế bắt mã thoát của tiến trình khác; pipeline phải xử lý exit code đúng môi trường đang chạy. Không lộ mật khẩu trong output của job hay artifact đã lưu.

### 9.3. Chọn database kiểm chứng

- Database **mới tinh** giúp phát hiện lỗi chạy từ trạng thái trống.
- Database **có lịch sử `DATABASECHANGELOG` từ release trước** giúp phát hiện vấn đề checksum, định danh, thứ tự nâng cấp và dữ liệu hiện hữu.
- Database **có cùng DBMS/phiên bản/cấu hình gần production** giúp phát hiện khác biệt cú pháp SQL, collation, permission và kiểu dữ liệu.

Một bài kiểm tra tốt có cả đường đi từ trống và đường nâng cấp từ phiên bản cũ. Chỉ chạy `validate` trên database mới có thể không phát hiện sự khác biệt với checksum của một changeset đã chạy trên production.

## 10. Xem lỗi validation và xác định nguyên nhân gốc

Thông báo thực tế thay đổi theo phiên bản, nhưng có thể dùng bảng định hướng sau:

| Biểu hiện | Nguyên nhân cần kiểm tra trước | Cách khắc phục |
|---|---|---|
| Không đọc được `master.yaml` | Tên file, path CLI, search path hoặc JAR thiếu resource | Sửa cấu hình root, kiểm tra nội dung artifact |
| Không tìm được file `include` | `relativeToChangelogFile`, path tương đối, sai chữ hoa trên Linux | Kiểm tra vị trí từ changelog cha và case-sensitive filename |
| YAML parser báo lỗi mapping/sequence | Sai thụt dòng, dấu `-`, `:`, tab hoặc quote | Sửa cú pháp, chạy lint và validate lại |
| Thuộc tính change type không hợp lệ | Sai tên key, không hỗ trợ trong phiên bản hiện tại | Đối chiếu change type reference cho đúng Liquibase version |
| Changeset identifier bị trùng | Hai phần tử cùng bộ `id`/`author`/đường dẫn | Đặt identifier duy nhất; không sửa changeset đã chạy tùy tiện |
| Checksum khác lịch sử | Changeset đã thực thi bị thay đổi hoặc khác nội dung resource được đọc | So sánh với bản đã release và `DATABASECHANGELOG` |
| Kết nối JDBC thất bại | URL, DNS, driver, credential, TLS hoặc quyền truy cập | Kiểm tra kết nối ở môi trường được phép; chưa kết luận nội dung changelog |
| `validate` thành công nhưng `update` lỗi | Trạng thái DB khác, thiếu quyền, SQL không hợp DBMS, dữ liệu vi phạm | Review `update-sql`, precondition và test database thật |
| Local chạy tốt, CI/JAR thất bại | Khác classpath, file không đóng gói hoặc version Liquibase/extension khác | Pin version, so sánh artifact và resource loader |
| Báo không có pending changeset khi kỳ vọng có | Context/label, `dbms`, lịch sử hoặc định danh không như dự kiến | Dùng `status` với filter tương ứng và kiểm tra `DATABASECHANGELOG` |

**Quy tắc điều tra:** bắt đầu từ lỗi đầu tiên và phân loại thành lỗi đọc file, lỗi parse, lỗi validation, lỗi lịch sử hay lỗi kết nối. Một lỗi đường dẫn có thể tạo ra nhiều thông báo sau đó; sửa lỗi đầu tiên rồi chạy lại thay vì chỉnh nhiều phần không liên quan cùng lúc.

Không dùng các cách “chữa nhanh” nguy hiểm như xóa lịch sử, đổi `id`/`author` đã triển khai, đánh dấu changeset chưa chạy là đã chạy hoặc reset checksum hàng loạt để che một vấn đề chưa hiểu.

## 11. Validation với context, label, precondition và DBMS

Một changelog có thể chứa nhiều thay đổi theo mục đích hoặc nền tảng:

```yaml
databaseChangeLog:
  - changeSet:
      id: "030-create-core-table"
      author: "db-team"
      changes:
        - createTable:
            tableName: core_setting
            columns:
              - column:
                  name: setting_key
                  type: VARCHAR(80)
                  constraints:
                    primaryKey: true
                    nullable: false
  - changeSet:
      id: "031-insert-test-setting"
      author: "db-team"
      contextFilter: "@test-fixtures"
      changes:
        - insert:
            tableName: core_setting
            columns:
              - column:
                  name: setting_key
                  value: "TEST_MODE"
```

Changeset đầu là schema cơ bản, changeset sau chỉ nạp fixture khi bật context `test-fixtures` tường minh. Khi chạy `validate`, Liquibase cần đọc changelog theo khả năng của lệnh và phiên bản, nhưng **`validate` không phải báo cáo chính xác mọi changeset sẽ được chọn để chạy với context/label của lần `update` tương lai**.

Muốn xác định thực thi thực tế, hãy dùng `status` và `update-sql` **với cùng context/label/DBMS và thông tin kết nối** mà job triển khai sẽ dùng. Precondition cũng phải được thử trên trạng thái database thích hợp; không nên mặc định `validate` sẽ đánh giá mọi điều kiện runtime theo cách `update` thực hiện.

Chẳng hạn, một changeset có thể khai báo đoạn `preConditions` sau để yêu cầu bảng đích tồn tại trước khi chèn dữ liệu:

```yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      tableName: core_setting
```

Đoạn trên phải nằm **bên trong một `changeSet`**, không phải một file changelog độc lập. Cấu trúc YAML có thể được đọc hợp lệ trong bước validation, nhưng kết quả kiểm tra `tableExists` phụ thuộc database đích tại thời điểm thực thi. Nếu database chưa có bảng, chiến lược `HALT` dừng migration; đó là hành vi cần diễn tập khi chạy thử, không phải một đảm bảo tự động từ việc `validate` trả về thành công.

Trong mọi trường hợp, tên context như `prod` không chứng minh JDBC đang trỏ đến production. Context là bộ lọc do người vận hành chọn; database đích phải được xác minh độc lập bằng URL/schema/tài khoản.

## 12. Thực hành có chủ đích: từ changelog đúng đến từng loại lỗi

Hãy thực hiện trên một database thử nghiệm riêng hoặc hệ thống có thể tạo lại. Không thay đổi files changelog đã triển khai trên database dùng chung chỉ để tạo lỗi.

1. **Tạo bộ changelog đúng** ở mục 3: master và hai file con, thêm cấu hình CLI/JDBC phù hợp.
2. **Chạy `validate`**, ghi nhận kết quả và mã thoát tiến trình; sau đó chạy `status` và `update-sql` để xác nhận các bước khác nhau.
3. **Lỗi YAML**: trên bản sao changelog dành cho thực hành, thụt `columns` sai cấp. Chạy `validate`, ghi nhận thông báo và khôi phục nội dung đúng.
4. **Lỗi thiếu tài nguyên**: trong bản sao thực hành, thay đường dẫn include thành `changes/099-does-not-exist.yaml`; xác định lỗi thuộc nhóm path/resource thay vì lỗi database.
5. **Lỗi định danh**: thêm một changeset trùng bộ `id`/`author`/đường dẫn trong một file thử; xem Liquibase báo gì ở phiên bản đang dùng.
6. **Lỗi thuộc tính**: thay `newColumnName` thành `newColumn` trong một `renameColumn` mẫu; kiểm tra validator có báo được hay cần thêm bước review reference.
7. **Thử chạy thật**: quay về changelog đúng, dùng `update` trên database thử nghiệm; kiểm tra bảng, cột, dữ liệu và `DATABASECHANGELOG`.
8. **Kiểm tra checksum**: chỉ trên database thực hành, thay nội dung changeset **đã chạy** để thấy phản ứng của `validate`; sau đó khôi phục nội dung ban đầu, không sửa metadata lịch sử tùy tiện.
9. **Thử khác biệt SQL/dữ liệu**: viết changeset hợp lệ về cấu trúc nhưng tạo unique cho cột có duplicate; nhận xét vì sao `validate` chưa đủ và `update` có thể lỗi.
10. **So sánh CLI với JAR**: nếu dùng Spring Boot, xác nhận bộ changelog và tài nguyên có trong artifact, không chỉ trong IDE.

Mục tiêu của bài thực hành không phải tạo ra càng nhiều lỗi càng tốt, mà là **biết lỗi thuộc lớp nào, sửa tại đâu, và khi nào phải dừng trước khi áp dụng migration**.

## 13. Checklist trước khi cho phép cập nhật database

- [ ] Đã xác định chính xác changelog gốc, đường dẫn include và classpath của artifact sẽ được chạy.
- [ ] Phiên bản Liquibase, extension và JDBC driver được cố định, thống nhất giữa local, CI/CD và môi trường triển khai.
- [ ] YAML/XML/JSON hoặc formatted SQL được lint/review; các cấu trúc, id, author và attributes được kiểm tra.
- [ ] `validate` chạy thành công với exit code đạt yêu cầu trên cấu hình và database phù hợp.
- [ ] Những thay đổi đã chạy giữ nguyên danh tính và nội dung; không tự sửa `DATABASECHANGELOG` hay checksum.
- [ ] `status` được chạy với cùng context/label dự định sử dụng khi cập nhật.
- [ ] `update-sql` đã được review về DDL/DML, schema, quyền, default, ràng buộc và thứ tự thay đổi.
- [ ] Đã kiểm thử trên database có lịch sử từ phiên bản trước, không chỉ trên database trống.
- [ ] Các precondition cần thiết được xem xét và kiểm chứng trên trạng thái database dự kiến.
- [ ] Dữ liệu hiện có được kiểm tra trước các thay đổi như `UNIQUE`, `NOT NULL`, foreign key và backfill.
- [ ] Có kế hoạch backup, rollback hoặc forward-fix đã được xem xét về mất dữ liệu và phụ thuộc.
- [ ] CI/CD chặn triển khai khi validation thất bại và không tiết lộ credential trong log.
- [ ] Đã xác minh JDBC URL, schema và tài khoản đích trước khi chạy bất kỳ lệnh `update` nào.

**Kết luận:** `validate` là bước đầu tiên quan trọng để kiểm tra cấu trúc changelog và phát hiện sớm nhiều lỗi định dạng, tham chiếu, định danh hoặc lịch sử. Tuy nhiên, đó là **một lớp xác thực**, không phải giấy bảo đảm migration sẽ thành công hoặc không gây hại. Kết hợp `validate` với `status`, `update-sql`, thử `update` và rollback trên database tương đương, cùng kiểm tra checksum và `DATABASECHANGELOG`, sẽ giúp quy trình `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` nhất quán và có thể kiểm chứng ở local, Spring Boot và CI/CD.
