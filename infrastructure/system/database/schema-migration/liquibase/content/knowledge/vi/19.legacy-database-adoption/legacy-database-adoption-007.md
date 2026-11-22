# Kiểm chứng cùng changelog trên cơ sở dữ liệu rỗng

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Tiếp nhận CSDL**, việc chạy cùng một changelog trên một cơ sở dữ liệu rỗng là phép kiểm tra quan trọng để chứng minh dự án có thể dựng mới database từ đầu bằng lịch sử migration đã quản lý.

Một hệ thống có thể chạy ổn trên database cũ nhưng thất bại khi tạo mới vì changelog thiếu bước khởi tạo, thứ tự include sai, dữ liệu tham chiếu chưa được seed, precondition giả định đối tượng đã tồn tại hoặc một thay đổi chỉ từng được thực hiện thủ công. Kiểm chứng trên database rỗng giúp phát hiện những khoảng trống này trước khi tiếp nhận khách hàng mới, dựng môi trường test, khôi phục hệ thống hoặc chuyển sang một database mới.

**Mục tiêu của bài:** dùng đúng root changelog và artifact được quản lý để dựng một database sạch, xác minh mọi changeset cần thiết được thực thi theo thứ tự, đối chiếu schema và dữ liệu cuối cùng, sau đó kiểm tra lần update thứ hai không tạo thay đổi ngoài dự kiến.

## 1. Database rỗng là gì?

Trong ngữ cảnh kiểm thử Liquibase, **database rỗng** là database đích đã tồn tại và có thể kết nối, nhưng chưa có schema nghiệp vụ, bảng dữ liệu ứng dụng hoặc lịch sử migration của ứng dụng cần kiểm chứng.

Không nhất thiết database server phải mới cài đặt. Cần phân biệt:

| Khái niệm | Ý nghĩa | Có thể dùng làm fresh-install test? |
|---|---|---|
| Database server mới | Instance DBMS vừa được cài hoặc tạo | Có, nếu tạo database đích và quyền phù hợp |
| Database đã tồn tại nhưng chưa có schema ứng dụng | Database/catalog có sẵn, vùng schema ứng dụng chưa có đối tượng | Có, nếu xác nhận đúng phạm vi rỗng |
| Schema ứng dụng mới | Schema đã được tạo nhưng chưa có bảng nghiệp vụ | Có, nếu metadata và đối tượng ứng dụng chưa có lịch sử |
| Database đã có DATABASECHANGELOG | Liquibase đã ghi lịch sử cho một root/metadata scope | Không còn là trạng thái rỗng ban đầu |
| Database đã có bảng thủ công | Đối tượng đã tồn tại ngoài lịch sử Liquibase | Không phải fresh database thuần; cần kiểm thử adoption/drift riêng |
| Database test được tái sử dụng | Có thể còn dữ liệu, sequence, view hoặc lock từ lần chạy trước | Chỉ dùng sau khi xác minh và reset an toàn |

Liquibase thường cần một database/catalog đã được tạo trước và một tài khoản có quyền kết nối. Tùy kiến trúc, schema ứng dụng có thể được provisioning bởi DBA hoặc được tạo trong migration. **Không giả định Liquibase tự tạo database server hoặc database catalog** chỉ vì changelog có createTable.

### 1.1. Metadata Liquibase không phải schema nghiệp vụ

Khi lần đầu thực hiện update, Liquibase quản lý hai bảng metadata:

- **DATABASECHANGELOG:** lưu lịch sử changeset đã được ghi nhận.
- **DATABASECHANGELOGLOCK:** điều phối lock để tránh nhiều tiến trình cùng cập nhật một bộ metadata.

Vì vậy, sau lần update đầu tiên, database không còn “rỗng tuyệt đối”: hai bảng quản lý có thể đã được tạo. Điều cần xác nhận là **schema và dữ liệu nghiệp vụ được dựng từ changelog**, còn metadata phản ánh đúng lịch sử.

Nếu metadata được đặt trong schema riêng qua liquibaseSchemaName, schema đó cần tồn tại hoặc được chuẩn bị theo quy trình provisioning phù hợp. Tài khoản migration phải có quyền tạo và thao tác trên các bảng metadata.

### 1.2. Xác định phạm vi rỗng trước khi chạy

Trước khi gọi Liquibase, xác nhận:

1. Database/catalog và schema đích đúng môi trường thử nghiệm.
2. Không có bảng nghiệp vụ, view, sequence, trigger hoặc constraint từ lần chạy trước.
3. Không có DATABASECHANGELOG/DATABASECHANGELOGLOCK thuộc cùng cấu hình metadata.
4. Không có tiến trình migration khác đang chạy trên database.
5. Tài khoản dùng trong test là tài khoản migration dành riêng cho database thử nghiệm.
6. Không có dữ liệu production hoặc dữ liệu cá nhân thật trong database.
7. Có thể xóa và tạo lại database test theo quy trình được phép nếu migration thất bại giữa chừng.

Đừng chỉ kiểm tra một bảng. Một schema có thể không có bảng orders nhưng vẫn còn sequence, function hoặc view do lần thử trước để lại.

## 2. Vì sao phải kiểm chứng cùng changelog trên database rỗng?

Một changelog có hai nhiệm vụ liên quan nhưng khác nhau:

- **Nâng cấp database đã có lịch sử:** chỉ áp dụng changeset chưa được ghi nhận.
- **Dựng mới database:** áp dụng toàn bộ changeset được chọn theo cấu hình, từ trạng thái ban đầu đến trạng thái hiện tại.

Một dự án có thể hoàn thành nhiệm vụ thứ nhất nhưng thất bại ở nhiệm vụ thứ hai nếu các thay đổi trước đây không được ghi vào changelog hoặc chỉ được thực hiện thủ công.

Các nguyên nhân thường gặp:

- Bảng nền tảng được tạo thủ công từ trước nhưng không có changeset tương ứng.
- Một changeset insert dữ liệu tham chiếu dựa vào bảng mà changelog không tạo.
- File changelog con bị thiếu khỏi root include.
- Thứ tự changeset không phù hợp dependency giữa bảng, foreign key, view và trigger.
- Precondition dùng MARK_RAN vì giả định một đối tượng đã tồn tại; trên database rỗng, SQL tạo đối tượng bị bỏ qua.
- Một file sqlFile không được đóng gói vào artifact.
- Một changeset chỉ chạy với context/label đã không được truyền trong lệnh fresh install.
- SQL phụ thuộc DBMS khác với engine đang test.
- Một sequence hoặc identity được giả định đã tồn tại.
- Dữ liệu khởi tạo được nạp ngoài Liquibase nhưng không có trong quy trình dựng mới.

**Fresh-install test kiểm tra tính đầy đủ của lịch sử migration.** Nó bổ sung cho upgrade-path test trên database cũ; không thay thế kiểm thử nâng cấp, rollback hoặc dữ liệu production.

## 3. Dùng đúng một root changelog cho mọi lần dựng

Một root changelog thường nạp các file con theo thứ tự dependency. Ví dụ cấu trúc minh họa:

~~~text
db/changelog/
  db.changelog-master.yaml
  schema/
    001-create-reference-tables.yaml
    002-create-customers.yaml
    003-create-orders.yaml
    004-add-order-constraints.yaml
  data/
    010-seed-reference-data.yaml
  objects/
    020-create-views.yaml
    021-create-functions.yaml
~~~

Root changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/schema/001-create-reference-tables.yaml
  - include:
      file: db/changelog/schema/002-create-customers.yaml
  - include:
      file: db/changelog/schema/003-create-orders.yaml
  - include:
      file: db/changelog/schema/004-add-order-constraints.yaml
  - include:
      file: db/changelog/data/010-seed-reference-data.yaml
  - include:
      file: db/changelog/objects/020-create-views.yaml
  - include:
      file: db/changelog/objects/021-create-functions.yaml
~~~

Đây là cấu trúc minh họa cho một dự án có nhiều nhóm đối tượng. Các đường dẫn phải khớp với vị trí resource thực tế và cách Liquibase resolve relative path. Không cần tách file chỉ vì muốn có nhiều file; điều quan trọng là root changelog nạp đủ các changeset cần thiết và thứ tự có thể giải thích.

### 3.1. Thứ tự include là một phần của thiết kế

Ví dụ:

- Bảng customer phải tồn tại trước khi bảng orders tạo foreign key tham chiếu customer.
- Bảng danh mục trạng thái phải tồn tại trước khi seed dữ liệu tham chiếu.
- Bảng và cột phải tồn tại trước khi tạo view/index/trigger phụ thuộc.
- Sequence phải tồn tại trước khi một cột dùng sequence làm default.
- Function phải tồn tại trước khi trigger gọi function đó.

Không dựa vào thứ tự filesystem không rõ ràng khi includeAll. Nếu thứ tự có ý nghĩa, dùng include tường minh hoặc quy ước đặt tên và thứ tự đã được kiểm chứng theo phiên bản Liquibase đang sử dụng.

### 3.2. Giữ định danh logic ổn định

Liquibase nhận diện changeset bằng id, author và đường dẫn changelog được sử dụng làm định danh, có thể điều chỉnh với logicalFilePath khi cần. Cùng một root changelog nên được sử dụng nhất quán giữa fresh install và upgrade path.

Không đổi tên file, di chuyển thư mục hoặc sửa định danh changeset chỉ để test fresh install. Nếu cần refactor cấu trúc file, hãy xử lý định danh lịch sử như một thay đổi riêng có kiểm chứng trên database đã triển khai.

## 4. Phân biệt schema ứng dụng và schema metadata

Trong môi trường nhiều schema, cần phân biệt:

| Tham số/khái niệm | Phạm vi |
|---|---|
| defaultSchemaName | Schema mặc định cho các đối tượng ứng dụng do changelog tạo khi không chỉ định rõ |
| liquibaseSchemaName | Schema chứa bảng metadata DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| liquibaseCatalogName | Catalog chứa bảng metadata khi DBMS và cấu hình hỗ trợ |
| schemaName trong change type | Schema cụ thể của đối tượng đang được tạo hoặc thay đổi |

Ví dụ:

~~~properties
defaultSchemaName=app
liquibaseSchemaName=platform_meta
~~~

Trong ví dụ, bảng nghiệp vụ được tạo ở schema app theo mặc định; hai bảng quản lý lịch sử nằm trong platform_meta. Schema platform_meta có thể được provisioning trước bằng DBA. Tài khoản migration cần quyền phù hợp ở cả hai phạm vi.

Không coi việc database rỗng là lý do để bỏ qua provisioning. Nếu schema metadata chưa tồn tại và Liquibase không có quyền tạo schema, lần update đầu tiên có thể thất bại trước khi changeset nghiệp vụ được thực thi.

## 5. Ví dụ changelog tối thiểu có thể dựng từ đầu

Ví dụ dưới đây tạo bảng customer và orders, sau đó thêm dữ liệu tham chiếu. Nó minh họa quan hệ dependency và cách tổ chức một changeset chạy một lần.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fresh-001-create-customer
      author: database-team
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
                  name: customer_code
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: display_name
                  type: VARCHAR(160)
                  constraints:
                    nullable: false

  - changeSet:
      id: fresh-002-create-orders
      author: database-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: NEW
        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_orders_customer

  - changeSet:
      id: fresh-003-seed-order-status
      author: database-team
      changes:
        - createTable:
            tableName: order_status
            columns:
              - column:
                  name: code
                  type: VARCHAR(20)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: description
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: NEW
              - column:
                  name: description
                  value: Newly created
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: PAID
              - column:
                  name: description
                  value: Payment confirmed
~~~

Đây là ví dụ học tập; một dự án thực tế có thể tách bảng order_status thành changeset tạo bảng và changeset seed để quản lý riêng. Cần kiểm tra SQL autoIncrement trên DBMS đích, kiểu dữ liệu foreign key tương thích, tên constraint và schema thực tế.

### 5.1. Dữ liệu tham chiếu phải được dựng cùng schema

Nếu ứng dụng cần các mã trạng thái NEW và PAID, fresh-install test phải xác nhận chúng tồn tại sau update. Chỉ có bảng order_status nhưng không có dữ liệu cần thiết vẫn có thể khiến ứng dụng khởi động nhưng lỗi khi xử lý nghiệp vụ.

Dữ liệu tham chiếu production phải được quản lý trong changelog chung. Dữ liệu fixture chỉ dùng cho test nên nằm ở root test riêng và không được include vào root production.

### 5.2. Fixture test không phải một phần của fresh install production

Không thêm khách hàng giả, tài khoản demo hoặc đơn hàng mô phỏng vào root changelog dùng chung nếu chúng không được phép xuất hiện ở production. Nếu cần fixture cho integration test, quản lý bằng changelog test hoặc công cụ test setup riêng, dùng dữ liệu synthetic và database cách ly.

## 6. Chuẩn bị database thử nghiệm rỗng

Một database test mới cần được chuẩn bị bằng hạ tầng hoặc quy trình DBA. Ví dụ thông tin cấu hình minh họa:

~~~text
DBMS: PostgreSQL
Database: commerce_fresh_test
Application schema: app
Liquibase metadata schema: platform_meta
Migration user: commerce_test_migrator
Runtime user: commerce_test_runtime
Root changelog: db/changelog/db.changelog-master.yaml
~~~

Các tên trên chỉ là ví dụ. Không đưa mật khẩu thật vào command line, source control hoặc báo cáo.

Trước khi chạy, xác nhận:

- Database/catalog đã tồn tại và kết nối được.
- Schema app được tạo sẵn hoặc migration role có quyền tạo theo thiết kế.
- Schema platform_meta được chuẩn bị nếu dùng riêng.
- Không có bảng nghiệp vụ, sequence, view, function hoặc trigger còn sót.
- Không có DATABASECHANGELOG/LOCK của lần chạy trước.
- Migration user có quyền tạo và thay đổi đối tượng cần thiết.
- Runtime user có quyền tối thiểu cần thiết sau migration.
- URL và credentials thuộc database test, không phải staging/production.
- DBMS và version tương ứng với môi trường đích mà bài test muốn đại diện.

### 6.1. Phân quyền migration và runtime

Tài khoản migration thường cần quyền DDL và DML trên schema ứng dụng, cùng quyền thao tác bảng metadata. Tài khoản runtime thường chỉ cần quyền SELECT/INSERT/UPDATE/DELETE theo chức năng ứng dụng.

Không dùng tài khoản DBA toàn quyền cho mọi pipeline nếu không cần. Một fresh-install test chạy được bằng DBA nhưng thất bại bằng migration role production là chưa đạt yêu cầu vận hành.

## 7. Lần chạy đầu tiên: validate, status, update-sql và update

Với CLI đã cấu hình đúng URL, credentials, changelog và filter, chuỗi lệnh phổ biến:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Mỗi lệnh có mục đích khác nhau:

| Lệnh | Mục tiêu | Kết quả mong đợi trên database rỗng |
|---|---|---|
| validate | Kiểm tra cấu trúc changelog và validation liên quan | Không có lỗi parse/validation |
| status --verbose | Xem changeset được chọn còn pending | Liệt kê các changeset áp dụng cho cấu hình hiện tại |
| update-sql | Xem SQL dự kiến | Có DDL/DML theo thứ tự dự kiến, không nhắm nhầm schema |
| update | Thực thi migration | Các changeset được chọn chạy theo thứ tự |
| history | Xem lịch sử đã ghi nhận | Có bản ghi tương ứng sau update |

Không coi validate thành công là bằng chứng SQL chạy được. Cũng không coi update-sql là migration đã thực thi. Fresh-install test chỉ hoàn thành sau khi update thực sự chạy trên database thử nghiệm và hậu điều kiện được kiểm tra.

### 7.1. Status rỗng trên database mới là dấu hiệu cần giải thích

Với một root changelog có nhiều changeset áp dụng trong cấu hình hiện tại, database thực sự chưa có lịch sử thường sẽ hiển thị các changeset đó là pending.

Nếu status không liệt kê gì dù dự kiến phải có migration, hãy kiểm tra:

- Có đang dùng nhầm database đã có history không?
- Root changelog có thực sự include các file cần thiết không?
- Context/label có lọc hết changeset không?
- Bộ lọc dbms có loại các changeset khỏi DBMS hiện tại không?
- Changelog path hoặc cấu hình profile có trỏ đến một root khác không?
- Có baseline hoặc changelogSync nào đã được chạy trước không?

Không chạy update chỉ để thử khi chưa hiểu vì sao status rỗng.

### 7.2. Review update-sql trước khi thực thi

Đọc SQL dự kiến và đối chiếu:

1. Bảng/sequence/view được tạo đủ và đúng thứ tự.
2. Primary key, unique, foreign key và index có mặt.
3. Schema/catalog là đúng.
4. Các câu INSERT chỉ nạp reference data hợp lệ.
5. Không có fixture test hoặc dữ liệu thật được nhúng sai.
6. Không có DROP/DELETE hoặc thao tác phá hủy ngoài kế hoạch.
7. SQL đặc thù DBMS được gửi đúng engine.
8. Không có placeholder/property chưa phân giải.
9. Các thao tác cần runInTransaction: false được tách và review riêng.

Nếu SQL preview khác với kế hoạch, dừng để điều tra root changelog, filter và properties.

## 8. Precondition phải phù hợp với database rỗng

Một lỗi thường gặp là changeset được viết cho database cũ, nơi bảng đã tồn tại. Ví dụ:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - tableExists:
      tableName: customer
~~~

Nếu bảng customer chưa tồn tại trên database rỗng, precondition thất bại và Liquibase có thể ghi nhận changeset là MARK_RAN mà không chạy SQL tạo bảng. Kết quả là lịch sử có bản ghi nhưng bảng vẫn thiếu.

Đối với fresh install, hãy thiết kế điều kiện đúng với trạng thái mong đợi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fresh-010-create-customer
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - not:
            - tableExists:
                tableName: customer
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
                  name: display_name
                  type: VARCHAR(160)
                  constraints:
                    nullable: false
~~~

Ví dụ này diễn đạt: nếu bảng đã tồn tại trong lúc changeset được kỳ vọng tạo mới, dừng để điều tra; nếu database sạch, điều kiện not tableExists đạt và createTable chạy. Cần xem xét default schema, schemaName và quyền truy vấn metadata của DBMS.

### 8.1. HALT, CONTINUE và MARK_RAN không thể thay thế nhau

| onFail | Hành vi khái quát | Cách cân nhắc khi fresh install |
|---|---|---|
| HALT | Dừng migration khi điều kiện không đạt | Phù hợp khi tiếp tục có thể tạo trạng thái sai |
| CONTINUE | Bỏ qua changeset trong lần update hiện tại theo quy tắc của Liquibase | Chỉ dùng khi bỏ qua là hành vi có chủ đích và sẽ được xử lý ở lần sau |
| MARK_RAN | Ghi nhận changeset đã xử lý mà không chạy nội dung changes | Không dùng để che việc đối tượng cần tạo chưa tồn tại |
| WARN | Cảnh báo và tiếp tục theo quy tắc | Chỉ dùng khi điều kiện thất bại không làm mất tính đúng đắn |

Hành vi chi tiết và vị trí khai báo cần đối chiếu phiên bản Liquibase. Với thay đổi bắt buộc để dựng schema, precondition nên **fail-closed**: dừng nếu giả định không đúng, thay vì đánh dấu đã chạy.

### 8.2. Precondition không thay thế thiết kế migration

Nếu một changeset có thể chạy trên cả database cũ đã có bảng và database mới chưa có bảng, cần xác định rõ hai trạng thái:

- Database mới cần createTable.
- Database legacy cần xác minh bảng có cấu trúc đúng và có thể baseline/adopt theo quy trình riêng.

Đừng dùng một precondition MARK_RAN chung để biến hai trạng thái thành một mà không kiểm tra cấu trúc. Bảng tồn tại chưa chắc có đúng cột, constraint, index, kiểu dữ liệu hoặc dữ liệu tham chiếu.

## 9. Chạy lại cùng changelog: kiểm tra tính ổn định

Sau lần update đầu tiên, chạy lại:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Kỳ vọng đối với changeset chạy một lần bình thường:

- Không còn changeset pending thuộc cùng root/filter.
- update-sql không đề xuất thực thi lại các changeset đã hoàn tất.
- update không tạo lại bảng hoặc chèn trùng reference data.
- History vẫn phản ánh những changeset đã được xử lý.
- Schema/data không có thay đổi ngoài ý muốn.

Một số changeset có runOnChange hoặc runAlways được thiết kế để chạy lại theo quy tắc riêng. Phải nhận diện chúng khi so sánh. Không dùng điều kiện “lần update thứ hai phải có 0 log” vì Liquibase vẫn có thể ghi log kết nối, kiểm tra, lock hoặc báo không có thay đổi.

### 9.1. Tính lặp lại không đồng nghĩa sửa changeset cũ

Nếu muốn cập nhật reference data, tạo changeset mới hoặc sử dụng một cơ chế đồng bộ dữ liệu được thiết kế rõ. Không sửa changeset seed lịch sử rồi mong Liquibase tự chạy lại trên database đã có history.

Đối với dữ liệu test cần tạo lại, ưu tiên database test mới hoặc quy trình fixture cleanup riêng. Không bật runAlways cho các INSERT không idempotent.

## 10. Xác minh schema cuối cùng bằng catalog DBMS

Sau update, cần đối chiếu **schema vật lý** với mô hình dự kiến. Có thể dùng truy vấn catalog hoặc công cụ diff/snapshot phù hợp DBMS.

Ví dụ PostgreSQL, kiểm tra bảng trong schema app:

~~~sql
SELECT table_schema,
       table_name
FROM information_schema.tables
WHERE table_schema = 'app'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
~~~

Kiểm tra cột:

~~~sql
SELECT table_name,
       column_name,
       data_type,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'app'
ORDER BY table_name, ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT tc.table_name,
       tc.constraint_name,
       tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'app'
ORDER BY tc.table_name, tc.constraint_name;
~~~

Kiểm tra index:

~~~sql
SELECT schemaname,
       tablename,
       indexname,
       indexdef
FROM pg_indexes
WHERE schemaname = 'app'
ORDER BY tablename, indexname;
~~~

Các truy vấn trên dành cho PostgreSQL hoặc metadata tương thích. Với MySQL, Oracle, SQL Server và DBMS khác, dùng catalog tương ứng; không sao chép nguyên truy vấn mà không xác minh tên schema, case và quyền.

### 10.1. So sánh expected objects với actual objects

Nên lập danh sách đối tượng dự kiến từ thiết kế migration hoặc artifact được review:

| Đối tượng | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| Bảng customer | Có trong schema app | Catalog tables |
| Bảng orders | Có trong schema app | Catalog tables |
| Primary key | Đúng cột id | Constraint metadata |
| Foreign key orders.customer_id | Tham chiếu customer.id | Constraint metadata |
| Sequence/identity | Đúng cơ chế sinh ID | Column metadata/sequence catalog |
| Index | Đúng tên, cột và predicate | Index catalog |
| View/function/trigger | Có định nghĩa tương ứng | Catalog đối tượng |
| Reference data | Có đủ mã nghiệp vụ | Truy vấn dữ liệu |

Không chỉ kiểm tra số lượng bảng. Một bảng có thể tồn tại nhưng thiếu foreign key, default, index hoặc cột quan trọng.

## 11. Xác minh dữ liệu khởi tạo và quan hệ

Schema đúng nhưng dữ liệu tham chiếu thiếu vẫn có thể khiến ứng dụng lỗi khi khởi động hoặc xử lý nghiệp vụ.

Ví dụ kiểm tra reference data:

~~~sql
SELECT code, description
FROM app.order_status
ORDER BY code;
~~~

Kiểm tra khóa ngoại mồ côi (nếu DBMS không enforce FK hoặc cần kiểm tra bổ sung):

~~~sql
SELECT COUNT(*) AS orphan_order_count
FROM app.orders o
LEFT JOIN app.customer c ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Kiểm tra dữ liệu bắt buộc không NULL:

~~~sql
SELECT COUNT(*) AS missing_status_count
FROM app.orders
WHERE status IS NULL;
~~~

Các câu truy vấn chỉ minh họa hậu điều kiện. Trên database mới có thể chưa có đơn hàng, vì vậy số dòng bằng 0 có thể là đúng; cần diễn giải theo tập dữ liệu dự kiến chứ không mặc định mọi bảng phải có dữ liệu.

### 11.1. Tách reference data và fixture

Dữ liệu tham chiếu cần cho production nên được include trong root changelog chung. Ví dụ mã trạng thái đơn hàng, loại tiền tệ hoặc cấu hình nghiệp vụ mặc định đã phê duyệt.

Dữ liệu fixture như khách hàng demo, đơn hàng giả, email kiểm thử hoặc tài khoản thử nghiệm chỉ thuộc môi trường test. Nếu dùng Liquibase để nạp, fixture phải nằm trong root test riêng, sử dụng synthetic data và không được include vào root production.

Fresh-install test production-equivalent không được phụ thuộc vào fixture test để hoàn tất schema.

## 12. Cùng changelog nhưng khác DBMS: kiểm chứng đúng ma trận

Cùng một root changelog có thể chứa change type chung và changeset SQL riêng cho từng DBMS:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fresh-020-create-index-postgresql
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX idx_orders_open
              ON app.orders (created_at)
              WHERE status = 'OPEN';

  - changeSet:
      id: fresh-021-create-index-mysql
      author: database-team
      dbms: mysql
      changes:
        - createIndex:
            schemaName: app
            tableName: orders
            indexName: idx_orders_created
            columns:
              - column:
                  name: created_at
~~~

Đây là ví dụ minh họa hai chiến lược index khác nhau; không nhất thiết hai index có ngữ nghĩa tương đương. Nếu ứng dụng yêu cầu cùng một tính năng trên nhiều DBMS, phải xác định cách đạt cùng invariant và test từng engine.

Cần kiểm chứng:

- DBMS và version thật của database.
- JDBC driver và Liquibase version.
- Changeset nào được chọn bởi dbms.
- SQL preview trên đúng engine.
- Tính năng DDL có tương đương về hành vi không.
- Transaction/rollback và catalog hậu kiểm.
- Các thay đổi bị bỏ qua trên engine khác có được thay thế bằng changeset tương ứng không.

**Test bằng H2 không đủ để chứng minh PostgreSQL/MySQL/Oracle/SQL Server sẽ chạy đúng** nếu changelog chứa SQL hoặc DDL phụ thuộc engine. Dùng DBMS production-equivalent trong CI hoặc một ma trận kiểm thử phù hợp.

## 13. SQL file, function, trigger và tài nguyên ngoài

Một root changelog có thể tham chiếu sqlFile, CSV loadData hoặc tài nguyên khác. Fresh-install test cần xác nhận tất cả tài nguyên này thực sự có trong artifact triển khai.

Ví dụ sqlFile:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fresh-030-create-report-view
      author: database-team
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/create_order_report_view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
~~~

Nếu file SQL không được đóng gói, path resolve sai hoặc splitStatements/endDelimiter không phù hợp, database cũ có thể vẫn chạy do đối tượng đã được tạo thủ công, nhưng database mới sẽ thất bại.

Checklist cho resource ngoài:

- Đường dẫn được resolve theo đúng root changelog.
- File được đưa vào JAR/container/artifact.
- Encoding đúng.
- Nội dung file trùng với commit được phát hành.
- SQL phù hợp DBMS.
- Delimiter và statement splitting phù hợp.
- Có rollback hoặc forward-fix rõ.
- Không chứa secret hoặc dữ liệu thật trong literal.

## 14. Fresh install khác với tiếp nhận database legacy

Đây là điểm cần hiểu kỹ trong chương **Tiếp nhận CSDL**.

### 14.1. Database rỗng: phải thực thi migration

Trên database rỗng, Liquibase cần chạy các changeset để tạo schema và dữ liệu tham chiếu. Một lệnh update bình thường sẽ áp dụng các changeset được chọn theo changelog, context, label và dbms.

### 14.2. Database legacy: có thể cần baseline/adoption

Database legacy có thể đã có bảng và dữ liệu được tạo trước khi Liquibase quản lý. Sau khi kiểm kê và chứng minh cấu trúc thực tế tương ứng với một phiên bản changelog cụ thể, nhóm có thể sử dụng quy trình baseline/adoption được thiết kế phù hợp. Một cơ chế như **changelogSync** có thể ghi nhận các changeset được chọn là đã xử lý mà không thực thi SQL của chúng.

Điều kiện quan trọng:

- Chỉ baseline khi schema/data đã được kiểm tra tương ứng với trạng thái changelog.
- Có snapshot/catalog evidence, dữ liệu và constraint được đối chiếu.
- Phân biệt changeset đã thực sự chạy với changeset được baseline.
- Lưu lại quyết định và commit/artifact làm mốc.
- Kiểm thử các changeset tiếp theo trên database legacy sau khi adoption.

### 14.3. Không dùng changelogSync trên database rỗng

Nếu chạy changelogSync trên một database chưa có schema nghiệp vụ, Liquibase có thể ghi nhận changeset như đã xử lý **mà không chạy các lệnh tạo bảng/cột/index**. Lịch sử sẽ trông như đã baseline, nhưng database vẫn rỗng.

Do đó:

| Loại database | Chiến lược chính |
|---|---|
| Database mới/rỗng | Chạy update để thực thi toàn bộ changeset được chọn |
| Database legacy đã có cấu trúc khớp | Kiểm kê, so sánh, baseline/adopt có kiểm chứng |
| Database legacy lệch một phần | Lập repair migration hoặc kế hoạch chuyển đổi; không baseline mù |
| Database test đã chạy trước đó | Xác định trạng thái, reset an toàn hoặc dùng database mới |

Đừng dùng cùng một thao tác cho mọi trạng thái chỉ để có bảng DATABASECHANGELOG.

## 15. Lỗi thường gặp khi chạy cùng changelog trên database rỗng

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Không kết nối được trước khi tạo bảng | Database/catalog chưa tồn tại, sai URL hoặc thiếu quyền | Kiểm tra provisioning, URL, driver, TLS, credentials |
| Không tạo được DATABASECHANGELOG | Thiếu quyền trên schema metadata hoặc schema chưa tồn tại | Kiểm tra liquibaseSchemaName, owner/grants |
| Changeset tạo bảng bị bỏ qua | Context/label/dbms filter hoặc precondition MARK_RAN | Xem status, log, EXECTYPE và cấu hình |
| Tạo foreign key thất bại | Bảng/cột tham chiếu chưa được tạo hoặc kiểu không tương thích | Kiểm tra thứ tự include và catalog |
| Seed dữ liệu bị lỗi unique | Dữ liệu đã tồn tại hoặc changeset chạy trước sai thứ tự | Xác minh database có thực sự rỗng, unique constraint và history |
| Không tìm thấy sqlFile | Path/encoding/đóng gói artifact sai | Kiểm tra relativeToChangelogFile và nội dung artifact |
| Function/procedure bị tách sai | splitStatements/endDelimiter không phù hợp | Kiểm tra delimiter và DBMS executor |
| SQL chạy trên test nhưng không chạy production | Khác DBMS/version hoặc changeset bị lọc | Kiểm tra ma trận engine và update-sql |
| Chạy lần hai tạo trùng dữ liệu | runAlways hoặc seed không idempotent | Kiểm tra EXECTYPE và thiết kế fixture/reference |
| Status không có pending trên database được cho là mới | Có metadata cũ, nhầm database, filter hoặc root sai | Xác minh URL, DATABASECHANGELOG và effective root |
| Update thất bại nhưng có bảng đã tạo | DDL auto-commit hoặc changeset không transactional | Kiểm tra catalog, transaction và log trước retry |
| Ứng dụng khởi động nhưng lỗi nghiệp vụ | Thiếu reference data, view/function hoặc quyền runtime | Smoke test và truy vấn hậu điều kiện |

### 15.1. Không tự xóa metadata để làm database “trống lại”

Nếu một lần update thất bại giữa chừng, không chỉ xóa DATABASECHANGELOG rồi chạy lại. Một số DDL có thể đã commit, trong khi lịch sử không ghi nhận changeset hoàn tất. Việc xóa metadata có thể khiến Liquibase chạy lại CREATE TABLE/INDEX trên đối tượng đã tồn tại hoặc thực thi DML trùng.

Cách an toàn trong một database test dùng một lần là **loại bỏ và tạo lại toàn bộ database/schema thử nghiệm theo quy trình được phép**, hoặc xác định trạng thái thực tế rồi sửa chữa bằng changeset có kiểm chứng. Không dùng cách reset này trên production.

## 16. Kiểm thử tính ổn định qua lần update thứ hai

Một fresh install tốt không chỉ chạy được một lần. Cần chứng minh cùng artifact không tiếp tục thay đổi database ngoài dự kiến ở lần chạy tiếp theo.

Quy trình:

1. Chạy update lần đầu trên database rỗng.
2. Kiểm tra lịch sử, schema và dữ liệu.
3. Không sửa changelog, properties hoặc filter.
4. Chạy validate và status lần nữa.
5. Xem update-sql lần thứ hai.
6. Chạy update lần thứ hai.
7. Kiểm tra history, schema và dữ liệu không phát sinh trùng lặp.

Nếu có changeset runOnChange hoặc runAlways, đọc rõ hành vi được thiết kế; không kỳ vọng tuyệt đối không có SQL nào được chạy. Với changeset thông thường, update lần hai không nên tạo lại bảng, seed trùng hoặc thay đổi cấu trúc.

### 16.1. So sánh trước và sau lần chạy thứ hai

| Kiểm tra | Sau update lần 1 | Sau update lần 2 |
|---|---|---|
| DATABASECHANGELOG | Có các changeset được ghi nhận | Không có thay đổi lịch sử ngoài dự kiến |
| Tables/columns | Đúng thiết kế | Không tạo trùng hoặc thay đổi ngoài ý muốn |
| Reference data | Đúng số dòng/mã | Không có duplicate |
| Sequence/identity | Cấp ID hợp lệ | Không bị reset ngoài ý muốn |
| View/function/index | Đúng định nghĩa | Không đổi nếu không có runOnChange chủ đích |
| Lock table | Không còn lock sau kết thúc bình thường | Tương tự |
| Ứng dụng | Smoke test đạt | Smoke test vẫn đạt |

## 17. Kiểm thử cùng changelog trong Spring Boot

Spring Boot có thể chạy Liquibase tự động khi ứng dụng khởi động. Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/commerce_fresh_test
    username: commerce_test_runtime
    password: ${TEST_DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    user: commerce_test_migrator
    password: ${TEST_LIQUIBASE_PASSWORD}
~~~

Tên host, database, user và biến môi trường là minh họa. Cần kiểm tra cấu hình cuối cùng sau khi Spring hợp nhất application.yml, profile, environment và secret source.

Các điểm cần xác nhận:

- Spring Boot nạp đúng root changelog như pipeline CLI.
- Changelog resource và sqlFile được đóng gói trong artifact.
- Phiên bản Liquibase trong ứng dụng tương thích với CLI dùng ở CI.
- Datasource và Liquibase migration connection trỏ cùng database logic.
- Tài khoản migration có quyền DDL; runtime user có quyền ứng dụng cần.
- Context/label và properties giống cấu hình được dùng trong kiểm thử.
- Không có nhiều instance đồng thời chạy các artifact khác nhau vào cùng database trong lúc rollout.

### 17.1. Migration job riêng hay chạy lúc ứng dụng khởi động?

Có hai mô hình phổ biến:

| Mô hình | Đặc điểm | Cần kiểm chứng |
|---|---|---|
| Spring Boot tự chạy Liquibase | Mỗi lần khởi động có thể kiểm tra và chạy migration | Lock, profile, nhiều instance, quyền và log startup |
| CI/CD chạy migration job riêng | Pipeline thực hiện update trước khi rollout ứng dụng | Cùng artifact/config với ứng dụng; runtime không chạy migration ngoài dự kiến |

Fresh-install test nên kiểm tra **cùng root changelog và bộ tham số hiệu lực** của mô hình triển khai thực tế. Nếu CLI chạy được nhưng Spring Boot không tìm thấy resource, bài test chưa chứng minh artifact ứng dụng có thể dựng database.

## 18. CI/CD: tự động tạo database rỗng và kiểm chứng

Một pipeline có thể tạo database test tạm thời cho mỗi commit hoặc pull request:

~~~text
Commit / Pull request
        |
        v
Tạo database test mới
        |
        v
Provision schema + migration role
        |
        v
Nạp đúng artifact + root changelog
        |
        v
validate
        |
        v
status --verbose
        |
        v
update-sql + review/check
        |
        v
update
        |
        v
Kiểm tra history + schema + reference data
        |
        v
Chạy update lần hai
        |
        v
Smoke test ứng dụng
        |
        v
Hủy database test theo lifecycle
~~~

### 18.1. Các kiểm tra tự động nên có

- **Fresh database assertion:** xác nhận database/schema thực sự mới, không có metadata hoặc đối tượng ứng dụng cũ.
- **Artifact assertion:** root changelog và các file include/sqlFile thuộc đúng commit/artifact.
- **Pending assertion:** changeset được chọn ban đầu khớp danh sách dự kiến.
- **SQL preview check:** không có DROP/DELETE hoặc SQL ngoài kế hoạch.
- **Update assertion:** tiến trình trả exit code thành công.
- **History assertion:** các changeset cần chạy có trạng thái phù hợp; không có MARK_RAN ngoài chủ đích.
- **Schema assertion:** bảng, cột, constraint, index, sequence, view và function có đủ.
- **Data assertion:** reference data có đủ, foreign key không mồ côi, fixture không lẫn production.
- **Repeat assertion:** update lần hai không tạo thay đổi ngoài ý muốn.
- **Application assertion:** ứng dụng khởi động và smoke test trên database mới.
- **Cleanup assertion:** database test và artifact tạm được thu hồi theo lifecycle.

### 18.2. Không dùng quyền production để dựng fresh test

Pipeline test chỉ cần kết nối tới database test và quyền trong phạm vi test. Không cấp credentials production cho runner chỉ vì muốn tái sử dụng một bước script. Dùng secret scope tách biệt, network allowlist và service account riêng.

Không ghi credentials trong command line hoặc log. Nếu SQL preview có literal dữ liệu nhạy cảm, giới hạn quyền đọc artifact và dùng dữ liệu synthetic.

### 18.3. Ma trận kiểm thử nhiều DBMS/version

Nếu module hỗ trợ nhiều DBMS, nên xây ma trận:

| Trục kiểm thử | Ví dụ |
|---|---|
| DBMS | PostgreSQL, MySQL, Oracle, SQL Server |
| Version | Phiên bản production và phiên bản được hỗ trợ |
| Liquibase | Phiên bản CLI và dependency ứng dụng |
| Java/JDBC | JDK và driver thực tế |
| Cấu hình | Schema, context, label, properties |
| Cách chạy | CLI job và Spring Boot startup |
| Trạng thái ban đầu | Database rỗng và database legacy đã baseline |

Không cần chạy mọi tổ hợp nếu tổ chức đã có ma trận hỗ trợ tối thiểu được xác định. Nhưng không được tuyên bố hỗ trợ một DBMS chỉ dựa trên test H2 hoặc một phiên bản engine khác.

## 19. Đối chiếu fresh install và upgrade path của database legacy

Để chứng minh một changelog dùng được trong cả tiếp nhận database cũ và dựng database mới, cần hai bài kiểm thử riêng:

### Fresh install

- Database mới không có schema nghiệp vụ và lịch sử.
- Liquibase chạy update để thực thi các changeset được chọn.
- Hậu điều kiện schema/data đạt.
- Lần update thứ hai không có thay đổi ngoài ý muốn.

### Legacy adoption/upgrade

- Database đã có schema/dữ liệu từ hệ thống cũ.
- Kiểm kê và so sánh cấu trúc thực tế với trạng thái changelog.
- Nếu baseline bằng changelogSync, chỉ thực hiện sau khi chứng minh database đã khớp những changeset được đánh dấu.
- Sau baseline, các changeset mới phải được thực thi đúng.
- Hậu điều kiện và dữ liệu legacy phải được giữ nguyên theo yêu cầu.

**Không dùng changelogSync trên database rỗng.** Lệnh này có thể ghi nhận changeset là đã chạy mà không thực thi SQL, khiến history trông hoàn tất trong khi schema vẫn chưa được tạo.

Một dự án tốt cần chứng minh cả hai đường đi hội tụ về trạng thái tương thích: dựng mới từ đầu và nâng cấp từ phiên bản legacy.

## 20. Rollback và phục hồi trong fresh-install test

Trong database test dùng một lần, khi migration thất bại có thể chọn tạo lại database sạch theo lifecycle của pipeline. Đây thường là cách kiểm tra fresh install dễ tái tạo hơn so với sửa thủ công một database đã ở trạng thái nửa chừng.

Tuy nhiên, vẫn cần kiểm tra rollback nếu ứng dụng yêu cầu khả năng quay về phiên bản trước:

1. Xác định tag hoặc phạm vi changeset cần rollback.
2. Review rollback SQL.
3. Xác minh thao tác có thể đảo ngược và không làm mất dữ liệu cần giữ.
4. Thử trên database tương đương.
5. Kiểm tra schema, dữ liệu và lịch sử sau rollback.
6. Thử triển khai lại nếu đó là một phần của quy trình hỗ trợ.

Không giả định mọi DDL/DML có rollback tự động. SQL tùy chỉnh, DDL auto-commit, thao tác không transactional và backfill dữ liệu có thể cần rollback tường minh hoặc forward-fix.

Không dùng dropAll trên database dùng chung hoặc production. Nếu dùng để reset lab/CI, phải chắc chắn URL trỏ database tạm được tạo riêng cho job và quyền không thể tác động database khác.

## 21. Checklist nghiệm thu fresh-install

- [ ] Database/catalog đích được tạo mới và kết nối đúng.
- [ ] Không còn schema nghiệp vụ, metadata Liquibase hoặc đối tượng sót từ lần thử trước.
- [ ] Schema metadata và schema ứng dụng được provision đúng.
- [ ] Dùng đúng artifact, root changelog và các file include/sqlFile.
- [ ] Giữ định danh changeset và logicalFilePath nhất quán.
- [ ] Cấu hình context, label, dbms và properties đúng với môi trường mục tiêu.
- [ ] validate không có lỗi.
- [ ] status --verbose hiển thị tập changeset pending như dự kiến.
- [ ] update-sql đúng thứ tự, đúng schema và không có thao tác phá hủy ngoài kế hoạch.
- [ ] update chạy với exit code thành công.
- [ ] DATABASECHANGELOG ghi nhận changeset phù hợp; mọi MARK_RAN được giải thích.
- [ ] DATABASECHANGELOGLOCK được giải phóng sau lần chạy bình thường.
- [ ] Catalog xác nhận đủ bảng, cột, constraint, index, sequence, view, function và trigger cần thiết.
- [ ] Dữ liệu tham chiếu bắt buộc có đủ và đúng.
- [ ] Không có fixture test hoặc dữ liệu nhạy cảm trong database production-equivalent.
- [ ] Tài khoản runtime truy cập được những đối tượng cần thiết với quyền tối thiểu.
- [ ] Ứng dụng khởi động và smoke test đạt.
- [ ] Update lần thứ hai không tạo thay đổi ngoài dự kiến.
- [ ] Đã test trên DBMS/version đại diện cho môi trường triển khai.
- [ ] Có bằng chứng rollback/forward-fix hoặc quy trình reset an toàn.
- [ ] CI/CD lưu artifact, commit, phiên bản Liquibase, exit code và kết quả hậu kiểm.

## 22. Kết luận

**Kiểm chứng cùng changelog trên cơ sở dữ liệu rỗng** chứng minh hệ thống có thể được dựng mới từ lịch sử migration đã quản lý, không phụ thuộc vào thao tác thủ công hoặc trạng thái vô hình của một database cũ. Cần chuẩn bị đúng database, schema metadata, quyền, root changelog và bộ lọc thực thi; sau đó validate, kiểm tra changeset pending, review update-sql, chạy update và xác minh schema/data thực tế.

Fresh-install test phải đi cùng upgrade-path test cho database legacy. Với database rỗng, chạy update để thực thi changeset; với database legacy, chỉ baseline/adopt sau khi chứng minh trạng thái hiện có tương ứng với lịch sử được ghi nhận. Kết hợp kiểm tra lần update thứ hai, Spring Boot/CI/CD dùng cùng artifact và hậu điều kiện rõ ràng sẽ giúp migration có thể tái tạo, kiểm toán và vận hành nhất quán qua nhiều môi trường.
