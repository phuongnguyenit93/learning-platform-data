# Tạo bản nháp migration từ diff-changelog

Khi phát triển ứng dụng, schema trong database tham chiếu và database cần triển khai có thể khác nhau. Nhóm phát triển đã thêm bảng, cột, index hoặc constraint ở môi trường tham chiếu; môi trường đích vẫn đang ở phiên bản cũ. Thay vì viết lại toàn bộ thay đổi bằng tay, Liquibase có thể **so sánh hai database và sinh một bản nháp changelog** từ những khác biệt mà công cụ nhận diện được.

Lệnh **diff-changelog** được dùng cho mục đích này. Cần xác định đúng chiều so sánh: **reference database là trạng thái schema mong muốn**, còn **target database là database cần được cập nhật**. Changelog sinh ra nhằm mô tả các thay đổi đưa target tiến gần tới reference. Đảo nhầm hai đầu kết nối có thể tạo bản nháp theo chiều ngược lại và dẫn tới thay đổi nguy hiểm.

Bài thuộc chương **So sánh lược đồ** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào quy trình tạo bản nháp migration từ diff-changelog, cách chuẩn bị hai database, đọc kết quả so sánh, review SQL được sinh, loại bỏ khác biệt ngoài phạm vi và kiểm thử trước khi đưa bản nháp vào lịch sử phát hành.

## 1. diff-changelog giải quyết bài toán gì?

Giả sử nhóm có hai database PostgreSQL:

- **reference:** schema đã được nhóm phát triển cập nhật và được xem là trạng thái mong muốn.
- **target:** schema ở staging hoặc một môi trường cần đồng bộ.

Reference có thêm bảng customer_profile, cột customer.email_verified và index hỗ trợ truy vấn; target chưa có những đối tượng này. diff-changelog có thể đọc metadata của cả hai database, xác định khác biệt được hỗ trợ và tạo changelog chứa những change type tương ứng.

~~~text
Reference database (mong muốn)
  customer
    - id
    - email
    - email_verified
  customer_profile
  index mới

             │
             │ Liquibase diff-changelog
             ▼

Generated changelog (bản nháp)
  - tạo cột còn thiếu
  - tạo bảng còn thiếu
  - tạo index còn thiếu
  - các thay đổi khác được nhận diện và cấu hình cho phép

             │
             │ review / validate / test
             ▼

Target database (sau migration)
  schema tiến gần tới reference
~~~

Kết quả là **bản nháp migration**, không phải bằng chứng rằng target đã được cập nhật. Lệnh diff-changelog so sánh và sinh nội dung changelog; việc thực thi thay đổi là một bước riêng, thường qua Liquibase update sau khi bản nháp đã được review và kiểm thử.

### 1.1. Khi nào nên dùng?

- Đồng bộ schema giữa một database nguồn đã được chuẩn hóa và database đích.
- Tạo bản nháp baseline khi tiếp nhận một database đã tồn tại.
- Phát hiện những thay đổi cấu trúc được thực hiện ngoài quy trình changelog.
- Hỗ trợ review khác biệt giữa môi trường phát triển và môi trường kiểm thử.
- Tạo điểm khởi đầu cho một migration thủ công có nhiều đối tượng.

### 1.2. Khi nào không nên coi diff-changelog là giải pháp đầy đủ?

- Khi cần chuyển đổi dữ liệu nghiệp vụ hoặc backfill hàng triệu dòng.
- Khi cần quyết định logic nghiệp vụ cho việc đổi tên hoặc gộp cột.
- Khi cần bảo toàn dữ liệu đang tồn tại trong đối tượng bị thay thế.
- Khi hai database có DBMS/version/cấu hình khác nhau đến mức metadata không thể so sánh tương đương.
- Khi cần chứng minh toàn bộ quyền, trigger, extension, job, cấu hình hoặc hành vi runtime đã giống nhau.

Diff-changelog chỉ có thể sinh các thay đổi mà Liquibase, JDBC driver và loại đối tượng được chọn nhận diện. Không nên hiểu “không còn diff” là mọi khía cạnh vận hành của hai database đã giống hệt.

## 2. Hiểu đúng chiều reference và target

Đây là quyết định quan trọng nhất trước khi chạy lệnh.

| Tham số | Vai trò | Cách hiểu |
|---|---|---|
| reference-url | Kết nối database tham chiếu | Nơi có trạng thái schema mong muốn |
| url | Kết nối database đích | Nơi sẽ nhận migration khi changelog được áp dụng |
| changelog-file | Đường dẫn bản nháp đầu ra | Nơi Liquibase ghi changelog được sinh |
| reference username/password | Thông tin truy cập reference | Nên có quyền đọc metadata cần thiết |
| username/password | Thông tin truy cập target | Dùng để so sánh metadata; khi triển khai phải có quyền phù hợp |

**Reference → Target** là chiều mong muốn: thay đổi target để phù hợp với reference.

Ví dụ:

- Reference có bảng orders, target chưa có: bản nháp có thể chứa thay đổi tạo bảng orders.
- Reference có cột orders.status, target chưa có: bản nháp có thể chứa thay đổi thêm cột.
- Target có một index mà reference không có: tùy loại diff, phiên bản và cấu hình, kết quả có thể biểu diễn việc loại bỏ đối tượng dư thừa. Đây là nhóm thay đổi có thể phá hủy, phải xem xét đặc biệt cẩn thận.

Không dùng các tên “source” và “destination” một cách mơ hồ trong tài liệu nội bộ. Hãy ghi rõ database nào là reference, database nào là target và target nào sẽ được cập nhật.

### 2.1. Ví dụ sơ đồ chiều so sánh

~~~mermaid
flowchart LR
    R["Reference DB<br/>Schema mong muốn"] --> D["Liquibase diff-changelog"]
    T["Target DB<br/>Schema hiện tại"] --> D
    D --> C["Generated changelog<br/>Bản nháp"]
    C --> V["Review / validate / test"]
    V --> U["Liquibase update"]
    U --> T
~~~

Reference được dùng để xác định trạng thái mong muốn; target là đối tượng được mô tả trong bản nháp. Sau khi review và kiểm thử, update mới thực sự tác động lên target.

## 3. Phân biệt diff, diff-changelog và generate-changelog

Ba lệnh có liên quan nhưng không thay thế nhau.

| Lệnh | Mục tiêu | Đầu ra chính |
|---|---|---|
| diff | So sánh reference và target | Báo cáo các đối tượng khác biệt |
| diff-changelog | So sánh reference và target, sinh thay đổi thành changelog | Bản nháp migration nhằm đưa target về gần reference |
| generate-changelog | Đọc một database hiện có và tạo changelog mô tả cấu trúc database đó | Changelog mô tả trạng thái hiện tại, thường dùng cho baseline |

**diff** phù hợp để xem và phân loại chênh lệch trước khi quyết định làm gì. **diff-changelog** chuyển một phần chênh lệch được nhận diện thành các change type. **generate-changelog** không cần một cặp reference/target; nó tạo changelog từ một database đang có.

Ví dụ:

- Có một database legacy cần bắt đầu quản lý bằng Liquibase: cân nhắc generate-changelog để tạo bản mô tả baseline.
- Có database reference đã được phê duyệt và database target cần đồng bộ: cân nhắc diff trước, sau đó diff-changelog.
- Chỉ muốn biết môi trường nào đang thiếu index hoặc cột: diff có thể đủ; không cần tự động sinh migration.

Không dùng generate-changelog để thay thế quy trình so sánh hai môi trường nếu câu hỏi thực tế là “target khác reference ở đâu?”.

## 4. Chuẩn bị hai database trước khi so sánh

Kết quả diff chỉ có ý nghĩa nếu hai kết nối được xác định đúng và có thể nhìn thấy những đối tượng cần so sánh.

### 4.1. Cùng DBMS và phiên bản tương thích

Tốt nhất so sánh hai database cùng loại hệ quản trị và cùng phiên bản hoặc các phiên bản tương thích đã được kiểm chứng. Nếu reference là PostgreSQL nhưng target là MySQL, kiểu dữ liệu, sequence, identity, index, constraint và metadata không có quan hệ một-một đơn giản. Diff có thể phản ánh khác biệt của DBMS thay vì thay đổi mà nhóm muốn triển khai.

Nếu mục tiêu là chuyển DBMS, đó là một dự án migration riêng: cần mapping kiểu, SQL, sequence/identity, function/procedure, collation, transaction và kiểm thử ứng dụng. Không coi diff-changelog là bộ chuyển đổi cross-DBMS tự động.

### 4.2. Cùng phạm vi schema

Kiểm tra:

- Database name và schema mặc định.
- Search path hoặc default schema.
- Những schema được include trong phép so sánh.
- Tên đối tượng có phân biệt hoa/thường theo DBMS hay không.
- User có đủ quyền đọc metadata ở cả hai phía.
- Các bảng nội bộ hoặc schema hệ thống cần loại khỏi phạm vi.

Nếu reference sử dụng schema app còn target tìm trong public, công cụ có thể báo hàng loạt đối tượng thiếu/dư dù hai môi trường thực tế tương đương về ý nghĩa.

### 4.3. Trạng thái ổn định trong lúc so sánh

Không nên để một pipeline khác tạo bảng hoặc thay đổi constraint trong lúc diff đang lấy metadata. Nếu hai database thay đổi liên tục, kết quả có thể phản ánh hai thời điểm khác nhau.

Một quy trình ổn định nên:

1. Chọn artifact/reference snapshot đã được review.
2. Hạn chế thay đổi schema trong khoảng thời gian so sánh.
3. Ghi nhận thời điểm và phiên bản của cả hai database.
4. Chạy diff trên đúng schema và bộ lọc.
5. Lưu báo cáo để review cùng bản nháp changelog.

### 4.4. Quyền kết nối

Tài khoản reference thường chỉ cần quyền đọc metadata cần thiết; tài khoản target khi chỉ so sánh cũng nên được giới hạn ở mức đọc nếu công cụ hỗ trợ. Chỉ tiến trình update sau phê duyệt mới cần quyền DDL/DML.

Không ghi password thật vào command history, repository hoặc log pipeline. Dùng secret store hoặc cơ chế cấp thông tin xác thực được tổ chức phê duyệt.

## 5. Chuẩn bị artifact và cấu hình CLI

Liquibase cần biết:

- JDBC driver tương ứng DBMS.
- Reference URL và thông tin kết nối reference.
- Target URL và thông tin kết nối target.
- Changelog output path.
- Schema mặc định hoặc danh sách schema cần so sánh.
- Bộ lọc loại đối tượng và phạm vi include/exclude nếu dự án cần.

Có thể cấu hình kết nối bằng properties hoặc cơ chế secrets của môi trường. Ví dụ khung command cho PostgreSQL:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-host:5432/app_target" \
  --username="$TARGET_DB_USER" \
  --password="$TARGET_DB_PASSWORD" \
  --reference-url="jdbc:postgresql://db-host:5432/app_reference" \
  --reference-username="$REFERENCE_DB_USER" \
  --reference-password="$REFERENCE_DB_PASSWORD" \
  --changelog-file="build/generated/schema-diff.yaml" \
  diff
~~~

Lệnh trên tạo báo cáo diff, chưa sinh changelog. Sau khi đã xem báo cáo, có thể chạy:

~~~bash
liquibase \
  --url="jdbc:postgresql://db-host:5432/app_target" \
  --username="$TARGET_DB_USER" \
  --password="$TARGET_DB_PASSWORD" \
  --reference-url="jdbc:postgresql://db-host:5432/app_reference" \
  --reference-username="$REFERENCE_DB_USER" \
  --reference-password="$REFERENCE_DB_PASSWORD" \
  --changelog-file="build/generated/schema-diff.yaml" \
  diff-changelog
~~~

Đây là command minh họa theo cú pháp CLI phổ biến; tên tùy chọn và cách nạp cấu hình có thể khác theo Liquibase version. Không đưa password thật vào ví dụ lưu trong repository hoặc tài liệu chạy production. Nếu dùng file cấu hình, phải xác minh file đó trỏ đúng hai database và không bị nhầm URL.

**Quan trọng:** đường dẫn changelog đầu ra phải được kiểm tra trước để tránh ghi đè một changelog đang được quản lý. Chỉ định một tên output mới, nằm trong workspace thử nghiệm, rồi review nội dung trước khi đưa vào source control. Trong bài học này, command chỉ là ví dụ; không chạy trên database thật.

## 6. Các loại đối tượng có thể được so sánh

Phạm vi đối tượng được nhận diện phụ thuộc Liquibase version, JDBC driver, DBMS, quyền metadata và diff types được cấu hình. Những nhóm thường gặp:

| Nhóm đối tượng | Ví dụ | Câu hỏi review |
|---|---|---|
| Catalog/schema | Schema app | Có so sánh đúng namespace không? |
| Table | customer, orders | Có thiếu bảng hay chỉ khác owner/metadata? |
| Column | email, created_at | Kiểu, nullability, default có đúng không? |
| Primary key | PK_customer | Thứ tự cột và tên constraint có tương đương? |
| Foreign key | FK_orders_customer | Cột tham chiếu, hành vi update/delete có đúng? |
| Unique constraint | UQ_customer_email | Quy tắc uniqueness có tương đương? |
| Check constraint | CK_order_amount | Biểu thức và DBMS semantics có giống? |
| Index | idx_orders_created | Cột, thứ tự, unique, predicate, expression có đúng? |
| View | active_customers | Định nghĩa SQL và dependency có được nhận diện? |
| Sequence | order_seq | Giá trị hiện tại và cấu hình sequence có cần đồng bộ? |
| Trigger/function/procedure | Trigger cập nhật audit | Có được hỗ trợ bởi phiên bản/extension đang dùng? |

Không phải mọi đối tượng trong DBMS đều được Liquibase diff nhận diện như nhau. Một số loại cần extension, snapshot support hoặc câu lệnh SQL thủ công. Một số thuộc tính cũng không được so sánh hoặc sinh change type theo cách người vận hành kỳ vọng.

### 6.1. Diff schema không phải data synchronization

Diff-changelog thường được dùng để tạo migration cho **cấu trúc database**. Không mặc định rằng nó sẽ chuyển toàn bộ bản ghi của bảng, so sánh nội dung dữ liệu hoặc tạo ETL. Dữ liệu tham chiếu và data migration cần được quản lý bằng loadData, loadUpdateData, SQL hoặc quy trình chuyên biệt phù hợp.

Nếu công cụ hỗ trợ một số loại diff liên quan dữ liệu ở phiên bản/edition nhất định, phải kiểm tra phạm vi và giới hạn cụ thể. Không dùng một kết quả schema diff để kết luận dữ liệu hai môi trường đã đồng nhất.

## 7. Đọc báo cáo diff trước khi sinh changelog

Không nên bỏ qua bước diff và nhảy ngay sang diff-changelog. Báo cáo giúp phân loại:

- Đối tượng có trong reference nhưng thiếu ở target.
- Đối tượng có trong target nhưng không có ở reference.
- Đối tượng cùng tên nhưng khác thuộc tính.
- Đối tượng không thể so sánh hoặc không được nhận diện.
- Khác biệt có thể chỉ là tên schema, owner hoặc cấu hình mặc định.

Một bảng phân loại nội bộ có thể như sau:

| Kết quả so sánh | Câu hỏi cần trả lời | Quyết định có thể có |
|---|---|---|
| Missing object | Reference có, target thiếu? | Tạo đối tượng nếu thuộc phạm vi migration |
| Unexpected object | Target có, reference không có? | Giữ lại, loại khỏi phạm vi hoặc xem xét xóa |
| Changed object | Cùng đối tượng nhưng định nghĩa khác? | Tạo thay đổi có chủ đích hoặc xử lý thủ công |
| Unknown/unsupported | Không đủ metadata để so sánh? | Điều tra driver, quyền, extension và công cụ |
| Khác schema/name | Có phải cùng đối tượng logic? | Chuẩn hóa schema mapping trước khi sinh changelog |

Không phải mọi khác biệt đều cần được “sửa” để hai database giống nhau. Ví dụ target có bảng audit do nhóm vận hành quản lý, nhưng reference không có; xóa bảng đó để làm cho diff sạch có thể gây mất dữ liệu hoặc phá hệ thống khác.

## 8. Sinh bản nháp diff-changelog

Sau khi báo cáo diff đã được review, chạy diff-changelog với cùng reference, target, schema và filter. Output thường là changelog ở định dạng đã chọn hoặc định dạng Liquibase sinh theo cấu hình/runtime.

Bản nháp có thể chứa các change type như:

- createTable, addColumn.
- addPrimaryKey, addForeignKeyConstraint.
- addUniqueConstraint, addNotNullConstraint.
- createIndex.
- createView hoặc SQL tương ứng nếu được hỗ trợ.
- Các thao tác khác theo đối tượng và loại diff.

Danh sách này chỉ là ví dụ. Changelog thực tế phụ thuộc các khác biệt được phát hiện và khả năng sinh change của phiên bản Liquibase.

**Không giả định mọi khác biệt đều sinh ra migration hoàn chỉnh.** Với đối tượng không được hỗ trợ, định nghĩa SQL đặc thù, function, trigger hoặc dữ liệu, có thể cần bổ sung changeset SQL riêng hoặc tách thành công việc migration thủ công.

### 8.1. Ví dụ changelog được sinh

Giả sử reference có bảng customer_profile còn target chưa có. Bản nháp có thể có cấu trúc tương tự:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: generated-001
      author: liquibase
      changes:
        - createTable:
            tableName: customer_profile
            columns:
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(120)
~~~

Đây là ví dụ minh họa cấu trúc, không phải cam kết ID, author, tên file hay cú pháp chính xác mà mọi phiên bản diff-changelog sẽ sinh. Hãy đọc output thực tế.

Sau khi sinh, cần review:

1. Bảng có schemaName chính xác không?
2. Các cột có đúng kiểu, default, nullable và auto-increment/identity không?
3. Primary key và foreign key có được mô tả đúng?
4. Index có đúng tên, cột và thứ tự?
5. Có thao tác DROP hoặc thay đổi phá hủy không?
6. Thứ tự changeset có tôn trọng dependency?
7. Có đối tượng hoặc thuộc tính quan trọng bị thiếu?
8. Rollback được sinh có đủ và có an toàn không?

## 9. Rủi ro khi sinh thao tác DROP hoặc thay đổi phá hủy

Một bản nháp diff có thể chứa thay đổi xóa hoặc thay thế đối tượng tùy loại diff, phiên bản và cấu hình. Những thao tác này cần được xem xét kỹ hơn tạo mới.

Ví dụ target có bảng legacy_report nhưng reference không có. Sự khác biệt này không chứng minh bảng legacy_report là rác. Có thể:

- Target có dữ liệu lịch sử chỉ tồn tại ở môi trường đó.
- Một dịch vụ khác đang dùng bảng.
- Bảng do nhóm vận hành hoặc hệ thống bên thứ ba quản lý.
- Reference chưa được cập nhật hoặc thiếu một phần schema.
- Khác biệt đến từ schema mapping hoặc quyền metadata.

Trước khi chấp nhận DROP TABLE, DROP COLUMN, DROP INDEX hoặc DROP CONSTRAINT, phải xác định owner, dependency, dữ liệu và tác động ứng dụng. Không đưa các lệnh destructive vào production chỉ vì diff-changelog sinh ra chúng.

### 9.1. Nguyên tắc review destructive changes

| Thay đổi | Rủi ro | Câu hỏi bắt buộc |
|---|---|---|
| DROP TABLE | Mất toàn bộ dữ liệu và đối tượng phụ thuộc | Bảng có còn được ứng dụng/job dùng? Có backup? |
| DROP COLUMN | Mất giá trị cột | Dữ liệu có cần giữ? Phiên bản app nào còn đọc? |
| DROP INDEX | Query chậm hoặc ảnh hưởng constraint | Index có phục vụ workload/constraint không? |
| DROP CONSTRAINT | Giảm bảo vệ toàn vẹn | Có dữ liệu vi phạm sau khi bỏ? |
| ALTER TYPE | Có thể lỗi chuyển đổi hoặc mất độ chính xác | Dữ liệu hiện tại có chuyển được? |
| RENAME | Mã ứng dụng cũ có còn dùng tên cũ? | Có cần giai đoạn tương thích? |

Với production, thường nên dùng chiến lược expand–migrate–contract: thêm cấu trúc mới, chuyển ứng dụng/dữ liệu, quan sát, rồi mới xóa cấu trúc cũ trong một phát hành riêng.

## 10. Diff-changelog không tự nhận diện ý định đổi tên

Một khác biệt giữa hai database có thể là:

- Reference có cột email_address.
- Target có cột email.

Con người có thể hiểu đây là cùng một trường đã được đổi tên. Nhưng nếu công cụ chỉ thấy một cột thiếu và một cột dư, bản nháp có thể biểu diễn thành thêm cột mới và xóa cột cũ, tùy khả năng nhận diện/định nghĩa đối tượng.

Hệ quả:

1. Cột mới được tạo nhưng dữ liệu không được chuyển.
2. Ứng dụng có thể đọc cột mới toàn NULL.
3. Cột cũ bị xóa và dữ liệu bị mất nếu thao tác DROP được chấp nhận.
4. Migration trông đúng theo cấu trúc nhưng sai về ý nghĩa dữ liệu.

Đối với rename, người thiết kế thường cần changeset có chủ đích như renameColumn, hoặc quy trình thêm cột mới, backfill, xác minh và xóa cột cũ sau. Không coi diff-changelog là công cụ suy luận ý nghĩa nghiệp vụ của tên cột.

Ví dụ rename có chủ đích bằng YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-rename-customer-email
      author: database-team
      changes:
        - renameColumn:
            tableName: customer
            oldColumnName: email
            newColumnName: email_address
            columnDataType: VARCHAR(255)
      rollback:
        - renameColumn:
            tableName: customer
            oldColumnName: email_address
            newColumnName: email
            columnDataType: VARCHAR(255)
~~~

Đây là ví dụ minh họa cho một rename thực sự; cần kiểm tra ứng dụng, view, procedure, index, trigger và DBMS. Trên hệ thống đang phục vụ traffic, việc đổi tên trực tiếp có thể phá tương thích với phiên bản ứng dụng cũ.

## 11. Lọc phạm vi so sánh: schema, object và diff types

Hai database có thể chứa nhiều schema, bảng và đối tượng ngoài phạm vi của ứng dụng. So sánh tất cả có thể tạo báo cáo nhiễu hoặc bản nháp chứa những thay đổi không thuộc trách nhiệm của nhóm.

Những phạm vi cần xác định:

- Schema ứng dụng nào cần so sánh.
- Những loại đối tượng nào được quan tâm: tables, columns, indexes, constraints, views, sequences...
- Đối tượng nào do extension hoặc nền tảng quản lý.
- Có cần loại trừ schema hệ thống hoặc bảng nội bộ của công cụ không.
- Có cần include/exclude đối tượng theo pattern hay không.

Liquibase có các tùy chọn phạm vi/schema/diff types trong các phiên bản phù hợp. Tên và cú pháp cụ thể cần kiểm tra trong help của runtime. Ví dụ một số cấu hình thường gặp có thể liên quan tới default schema, reference default schema, schemas, reference schemas, diff types hoặc include/exclude objects. Không sao chép chuỗi filter từ dự án khác mà không kiểm tra cách parser hiểu pattern.

### 11.1. Loại trừ đối tượng không thuộc migration

Ví dụ target chứa:

- Schema hệ thống.
- Bảng audit do nền tảng quản lý.
- Bảng nội bộ Liquibase.
- Đối tượng tạm do một extension tạo.
- Bảng của một dịch vụ khác dùng chung database.

Nếu đưa tất cả vào diff, bản nháp có thể chứa thao tác không thuộc module hiện tại. Trước khi lọc, lập danh sách owner và phạm vi được phép; không loại bỏ một đối tượng chỉ vì nó tạo ra khác biệt khó xử lý.

### 11.2. Không loại trừ một đối tượng chỉ để báo cáo sạch

Nếu bảng orders có FK bị thiếu ở target, loại trừ foreign keys sẽ làm báo cáo bớt khác biệt nhưng không sửa tính toàn vẹn. Filter phải phản ánh phạm vi sở hữu, không được dùng để che giấu lỗi schema cần xử lý.

## 12. Default schema, tên đối tượng và metadata không đồng nhất

Một nguồn gây false positive là cùng đối tượng logic nhưng được tạo trong schema khác nhau hoặc khác quy tắc đặt tên.

Ví dụ:

- Reference có app.customer.
- Target có public.customer.
- Cả hai đều là bảng customer nhưng ứng dụng dùng search_path khác nhau.

Nếu so sánh không chỉ định schema đúng, công cụ có thể báo missing/unexpected thay vì nhận diện một đối tượng tương ứng.

Các thuộc tính khác cũng có thể khác:

- Identifier case folding.
- Default value được lưu dưới biểu diễn SQL khác.
- Kiểu dữ liệu alias theo DBMS.
- Collation và character set.
- Identity/sequence strategy.
- Storage parameters.
- Owner và grant.
- Constraint/index naming convention.

Không phải mọi khác biệt metadata đều có cùng ý nghĩa runtime. Cần xác định thuộc tính nào là contract của schema ứng dụng, thuộc tính nào là khác biệt môi trường có chủ đích. Nếu cần chuyển đổi giữa các cách biểu diễn khác nhau, viết migration thủ công hoặc điều chỉnh chuẩn hóa trước khi sinh diff.

## 13. Vì sao không nên so sánh hai database đang thay đổi liên tục?

Giả sử diff-changelog đọc reference lúc 10:00:00. Một migration khác thêm cột lúc 10:00:02, còn target được đọc lúc 10:00:05. Bản nháp có thể phản ánh một tập đối tượng không thuộc cùng một trạng thái logic.

Các cách giảm rủi ro:

1. Dùng reference database đã đóng băng theo artifact/release cụ thể.
2. Không chạy đồng thời migration khác trên hai database trong thời gian diff.
3. Lưu phiên bản ứng dụng/changelog tạo ra reference.
4. Nếu có thể, so sánh các snapshot/clone được tạo tại thời điểm xác định.
5. Chạy diff lại sau khi có thay đổi đầu vào để kiểm tra bản nháp còn phản ánh trạng thái hiện tại không.

Đối với database production có tải cao, không tạo snapshot hoặc clone bằng cách làm ảnh hưởng dịch vụ mà chưa có quy trình vận hành. Dùng cơ chế backup/clone được tổ chức hỗ trợ.

## 14. Từ bản nháp tới changeset có thể review

Generated changelog là đầu vào cho kỹ sư, không phải artifact được chấp nhận tự động.

Một quy trình review hữu ích:

**Bước 1 — Xác minh chiều:** reference là trạng thái mong muốn, target là database sẽ nhận thay đổi.

**Bước 2 — Phân loại thay đổi:** thêm mới, thay đổi thuộc tính, xóa, đổi tên có thể có ý nghĩa dữ liệu.

**Bước 3 — Loại bỏ nhiễu có lý do:** bỏ qua khác biệt môi trường ngoài phạm vi, nhưng ghi rõ lý do và owner.

**Bước 4 — Bổ sung ngữ nghĩa:** viết rename, backfill, precondition, context/label, rollback hoặc SQL đặc thù khi bản nháp không đủ.

**Bước 5 — Chia changeset:** mỗi bước có mục tiêu và khả năng kiểm chứng rõ. Tách DDL lớn, data migration và thao tác destructive.

**Bước 6 — Chuẩn hóa định danh:** ID, author, path và quy ước tên phải ổn định trước khi triển khai.

**Bước 7 — Lưu vào source control:** review diff như code; ghi nguồn reference, target, phiên bản Liquibase và phạm vi đối tượng.

### 14.1. Đừng sửa changelog đã triển khai

Trước khi áp dụng vào bất kỳ môi trường dùng chung nào, nhóm có thể review và điều chỉnh bản nháp. Nhưng khi changeset đã được ghi nhận trên môi trường, không nên sửa nội dung đã triển khai để làm bản diff “đẹp hơn”. Liquibase dùng lịch sử và checksum để nhận diện thay đổi; hãy thêm changeset mới cho điều chỉnh tiếp theo.

## 15. Kiểm tra changelog được sinh bằng validate và update-sql

Sau review, cần kiểm tra parser và SQL được tạo ra.

Các lệnh thường dùng:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **validate:** kiểm tra một số vấn đề về changelog, định dạng, tham chiếu và cấu hình mà runtime có thể phát hiện.
- **status --verbose:** cho biết changeset nào còn chờ áp dụng trên database được cấu hình.
- **update-sql:** hiển thị SQL dự kiến cho update để review trước khi thực thi.

Cú pháp và hành vi cụ thể phụ thuộc Liquibase version. Những lệnh này không chứng minh migration sẽ thành công trên dữ liệu thật. Ví dụ, SQL thêm unique constraint có thể hợp lệ nhưng khi chạy vẫn thất bại vì target đang có dữ liệu trùng.

### 15.1. Xem xét SQL phá hủy

Trong output, tìm các thay đổi như:

- DROP TABLE / DROP COLUMN.
- DROP INDEX / DROP CONSTRAINT.
- ALTER TYPE có khả năng chuyển đổi mất dữ liệu.
- Thay đổi default hoặc nullability.
- Recreate view/function có dependency.
- Xóa sequence hoặc đổi identity.

Đánh giá xem thao tác có cần backup, backfill, tách release hoặc precondition hay không. Không triển khai chỉ vì validate và update-sql không báo lỗi.

## 16. Kiểm thử trên database mới và database nâng cấp

Một bản nháp diff có thể đưa target hiện tại về gần reference nhưng vẫn chưa đủ cho toàn bộ vòng đời database.

Cần ít nhất hai loại kiểm thử:

### 16.1. Fresh install

Tạo database sạch và chạy toàn bộ changelog chính thức từ đầu. Kiểm tra:

- Thứ tự changeset.
- Bảng/cột/constraint/index cuối cùng.
- View, sequence và object liên quan.
- Dữ liệu seed cần thiết.
- Rollback ở phạm vi phù hợp.

### 16.2. Upgrade từ target cũ

Clone database target trước migration, chạy bản nháp đã review rồi kiểm tra:

- Dữ liệu cũ còn nguyên theo yêu cầu.
- Các cột/kiểu được chuyển đổi chính xác.
- Constraint không thất bại vì dữ liệu legacy.
- Index được tạo và có trạng thái hợp lệ.
- Ứng dụng phiên bản cũ/mới tương thích trong quá trình rollout.
- DATABASECHANGELOG ghi đúng changeset.

Không kiểm tra chỉ trên database rỗng. Diff-changelog sinh từ hai schema có thể bỏ qua các quy tắc dữ liệu hoặc hành vi cần thiết khi nâng cấp từ một database thực đã có hàng triệu bản ghi.

## 17. Rollback của generated changelog

Không giả định mọi changeset do diff-changelog sinh đều có rollback phù hợp với dữ liệu và dependency.

Một số change type chuẩn có thể hỗ trợ rollback tự động hoặc được Liquibase tạo logic tương ứng; những thay đổi SQL tùy chỉnh, đối tượng không hỗ trợ hoặc thao tác destructive có thể cần rollback viết tay. Phải kiểm tra rollback thực tế của từng changeset theo Liquibase version.

Các câu hỏi:

- Tạo bảng mới thì rollback có DROP TABLE không? Bảng có dữ liệu mới phát sinh chưa?
- Thêm cột rồi rollback xóa cột: có mất dữ liệu được ghi sau deploy không?
- Thay đổi kiểu cột: dữ liệu cũ có thể phục hồi chính xác không?
- Rename: rollback có khôi phục tên cũ và dependency không?
- Drop đối tượng: có backup định nghĩa và dữ liệu không?
- Unique/FK constraint: rollback có ảnh hưởng toàn vẹn dữ liệu hay ứng dụng không?

Với thay đổi không thể đảo ngược chính xác, chuẩn bị backup/restore hoặc forward-fix. Rollback SQL hợp lệ về cú pháp chưa chắc phục hồi được trạng thái nghiệp vụ trước migration.

## 18. Diff-changelog và lịch sử DATABASECHANGELOG

Diff-changelog so sánh trạng thái schema của hai database. Nó **không tự đồng bộ lịch sử changeset** của target với reference.

Sau khi chạy diff-changelog:

- Changelog mới là một file migration được sinh.
- Target chưa bị thay đổi chỉ vì bản nháp đã được tạo.
- DATABASECHANGELOG của target chưa được cập nhật cho những changeset trong bản nháp.
- Khi bản nháp được thực thi bằng update, Liquibase mới ghi nhận changeset theo quy trình thông thường.
- Reference không tự được coi là đã có cùng lịch sử changeset với target.

Nếu reference đã được quản lý bằng một changelog chính thức, bản diff sinh ra không tự động thay thế changelog gốc hoặc mang theo lịch sử đó. Khi hợp nhất vào dự án, phải xác định bản nháp là migration bổ sung, baseline hay một artifact tạm phục vụ review.

Không thêm generated changelog vào production chỉ vì nó phản ánh một schema snapshot. Cần thống nhất ID/author/path, checksum và quan hệ với lịch sử đã triển khai.

## 19. Những hạn chế và false positive thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Nhiều bảng báo missing/unexpected | Sai schema/default schema hoặc search path | Chuẩn hóa schema và kết nối |
| Khác biệt kiểu dữ liệu hàng loạt | DBMS/version khác nhau hoặc alias kiểu | So sánh cùng DBMS/version; review mapping |
| Diff sinh DROP đối tượng đang dùng | Target có object ngoài reference | Xác minh owner/dependency, loại trừ có lý do hoặc giữ lại |
| Không thấy trigger/function | Driver hoặc diff support không nhận diện | Kiểm tra khả năng hỗ trợ, bổ sung SQL thủ công |
| Generated changelog thiếu rename | Công cụ thấy object cũ mất và object mới xuất hiện | Thiết kế rename/backfill có chủ đích |
| Changelog tạo unique constraint nhưng update lỗi | Dữ liệu target đang trùng | Kiểm tra và làm sạch dữ liệu trước constraint |
| Update lỗi do dependency | Thứ tự changeset không đúng hoặc đối tượng không được nhận diện | Sắp xếp lại trước deploy, bổ sung precondition |
| Chạy diff nhiều lần ra kết quả khác | Database thay đổi trong lúc so sánh | Dùng snapshot ổn định và ghi nhận phiên bản |
| Generated SQL khác môi trường | DBMS/version/schema config không giống | Test trên đúng đích và quản lý filter |
| Validate pass nhưng migration thất bại | Dữ liệu, quyền, lock hoặc DBMS runtime | Kiểm thử update trên clone có dữ liệu |
| Changelog mới xung đột lịch sử | ID/path/author không theo quy ước | Hợp nhất và chuẩn hóa trước khi triển khai |

Đừng cố làm báo cáo diff trống bằng cách bỏ qua những đối tượng chưa hiểu. Hãy phân loại từng khác biệt và ghi quyết định: cần migrate, giữ lại, loại khỏi phạm vi hay xử lý thủ công.

## 20. Quy trình thực hành: tạo bản nháp từ hai PostgreSQL database

Dùng hai database lab riêng biệt:

- app_reference: chứa schema đích mong muốn.
- app_target: chứa schema cũ cần cập nhật.

### Bước 1 — Tạo hai trạng thái khác nhau

Trong reference, tạo bảng customer và thêm cột email_verified cùng index phù hợp. Trong target, chỉ tạo phiên bản cũ của bảng customer.

Không dùng dữ liệu thật; chỉ dùng database lab có thể xóa và tạo lại.

### Bước 2 — Xác minh kết nối và phạm vi

Kiểm tra database name, schema, user, DBMS/version và quyền đọc metadata. Xác nhận reference là phía mong muốn, target là phía sẽ được cập nhật.

### Bước 3 — Chạy diff

~~~bash
liquibase \
  --url="jdbc:postgresql://localhost:5432/app_target" \
  --username="$TARGET_DB_USER" \
  --password="$TARGET_DB_PASSWORD" \
  --reference-url="jdbc:postgresql://localhost:5432/app_reference" \
  --reference-username="$REFERENCE_DB_USER" \
  --reference-password="$REFERENCE_DB_PASSWORD" \
  diff
~~~

Đọc báo cáo và phân loại từng khác biệt. Nếu báo cáo chỉ ra đối tượng ngoài phạm vi, tìm nguyên nhân trước khi lọc.

### Bước 4 — Sinh bản nháp

~~~bash
liquibase \
  --url="jdbc:postgresql://localhost:5432/app_target" \
  --username="$TARGET_DB_USER" \
  --password="$TARGET_DB_PASSWORD" \
  --reference-url="jdbc:postgresql://localhost:5432/app_reference" \
  --reference-username="$REFERENCE_DB_USER" \
  --reference-password="$REFERENCE_DB_PASSWORD" \
  --changelog-file="build/generated/schema-diff.yaml" \
  diff-changelog
~~~

Đường dẫn build/generated chỉ là ví dụ output. Trong dự án thật, chọn nơi lưu phù hợp và không ghi đè changelog đã được phát hành.

### Bước 5 — Review và hoàn thiện

Đọc bản nháp, kiểm tra schemaName, kiểu, constraint, index, dependency, destructive changes và rollback. Nếu công cụ không suy luận được rename hoặc data migration, bổ sung changeset có chủ đích.

### Bước 6 — Validate và xem SQL

~~~bash
liquibase validate
liquibase update-sql
~~~

Đảm bảo hai lệnh dùng đúng changelog output và target config. Không chỉ kiểm tra cú pháp; đọc từng câu SQL có thể làm thay đổi hoặc xóa dữ liệu.

### Bước 7 — Thử trên clone target

Chạy update trong database lab, sau đó đối chiếu schema với reference. Kiểm tra dữ liệu, constraint và query quan trọng. Thử rollback nếu có thể, rồi đánh giá việc reapply khi phù hợp.

### Bước 8 — Kiểm tra lại diff

Sau khi update hoàn tất, chạy diff lại giữa reference và target với cùng phạm vi và filter. Những khác biệt còn lại phải được giải thích: đối tượng ngoài phạm vi, thuộc tính không hỗ trợ, dữ liệu, quyền hoặc sai lệch thực sự.

Mục tiêu không nhất thiết là báo cáo trống bằng mọi giá; mục tiêu là hiểu và xử lý đúng những khác biệt thuộc phạm vi quản lý.

## 21. Tích hợp vào Spring Boot và CI/CD

Spring Boot có thể dùng changelog được quản lý trong resources. Tuy nhiên, diff-changelog thường phù hợp hơn với một bước chuẩn bị migration trong pipeline hoặc quy trình kỹ sư database, thay vì tự động chạy mỗi khi ứng dụng khởi động.

Một quy trình CI/CD có thể tổ chức:

1. Chọn reference artifact/database đã được phê duyệt.
2. Chuẩn bị target clone hoặc môi trường thử nghiệm.
3. Chạy diff để tạo báo cáo.
4. Review các khác biệt và xác định phạm vi.
5. Sinh diff-changelog vào thư mục output tạm.
6. Review/chuẩn hóa changelog, thêm logic rename/data migration/rollback.
7. Commit changelog chính thức vào source control qua quy trình review.
8. Validate và tạo update SQL.
9. Thử fresh install và upgrade trên dữ liệu đại diện.
10. Sau phê duyệt, triển khai artifact changelog bất biến qua staging/production.

**Không nên tự động lấy database development hiện tại làm reference cho mọi production deployment.** Development có thể chứa thay đổi chưa review, bảng thử nghiệm hoặc dữ liệu/extension chỉ phục vụ cá nhân. Reference nên là trạng thái đã được phê duyệt, gắn với release cụ thể và có thể tái tạo.

Nếu nhiều replica Spring Boot cùng tự chạy migration, vẫn cần điều phối như các bài về DATABASECHANGELOGLOCK. Diff-changelog không thay thế khóa triển khai hoặc kế hoạch release.

## 22. Bảo mật và quản lý thông tin kết nối

Một quy trình diff thường cần kết nối tới hai database. Đây là điểm dễ vô tình làm lộ thông tin:

- Không commit password reference/target trong changelog hoặc script.
- Không in JDBC URL chứa credentials vào log.
- Không chia sẻ báo cáo diff nếu tên schema/object hoặc metadata có tính nhạy cảm.
- Dùng tài khoản read-only khi chỉ so sánh nếu quyền metadata cho phép.
- Tách quyền đọc reference, đọc target và quyền update target.
- Không kết nối nhầm production khi chỉ muốn thử sinh bản nháp.

Bản nháp có thể chứa tên bảng, cột và định nghĩa nội bộ. Hãy quản lý quyền truy cập artifact output tương tự source code database.

## 23. Checklist trước khi chấp nhận generated changelog

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Reference và target có được xác định đúng chiều? | Reference là trạng thái mong muốn, target là đích cần cập nhật |
| Hai DBMS/version có tương thích để so sánh? | Phiên bản và driver đã xác minh |
| Schema/default schema/search path chính xác? | Danh sách schema và kết nối được review |
| Phạm vi object/diff type có đúng? | Include/exclude có lý do, không che giấu khác biệt |
| Có đối tượng ngoài phạm vi? | Owner và quyết định giữ/bỏ rõ ràng |
| Có DROP hoặc thay đổi phá hủy? | Đánh giá dữ liệu, dependency và phê duyệt |
| Rename có được hiểu đúng? | Có migration rename/backfill thủ công nếu cần |
| Constraint/index có phù hợp dữ liệu target? | Kiểm tra NULL, duplicate, FK và query |
| Changeset order có đúng dependency? | Review thứ tự và precondition |
| Rollback có an toàn? | Đã thử trên database có dữ liệu đại diện |
| Changelog có giữ lịch sử/ID/path ổn định? | Được review trước lần triển khai đầu |
| Validate/update-sql đã được kiểm tra? | Kết quả parser và SQL preview |
| Fresh install và upgrade đều thành công? | Test trên database mới và clone target cũ |
| Sau update đã diff lại? | Những khác biệt còn lại được giải thích |
| Artifact và secrets được bảo vệ? | Output được quản lý, credentials không lộ |

**Nguyên tắc cuối cùng:** diff-changelog là công cụ tạo bản nháp migration từ khác biệt giữa một database tham chiếu và một database đích. Hãy giữ đúng chiều reference → target, chuẩn hóa phạm vi và metadata, đọc báo cáo diff trước khi sinh changelog, review mọi thao tác phá hủy và bổ sung logic nghiệp vụ mà công cụ không thể suy luận. Chỉ sau validate, xem SQL, thử trên database mới lẫn database đã có dữ liệu và xác minh kết quả, bản nháp mới nên trở thành changeset chính thức trong lịch sử Liquibase.

