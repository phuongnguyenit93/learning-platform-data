# Nguyên nhân checksum không khớp và cách điều tra trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Checksum và lịch sử**, một kỹ năng vận hành thiết yếu là xác định **vì sao Liquibase báo checksum không khớp** và chọn cách khôi phục tính nhất quán mà không làm hỏng dữ liệu hoặc che giấu lịch sử.

Checksum mismatch thường xuất hiện khi định nghĩa changeset mà Liquibase đọc **khác với định nghĩa đã được ghi nhận ở lần triển khai trước**. Một lỗi như vậy là **tín hiệu cần điều tra**, không phải hướng dẫn xóa checksum cho lệnh chạy tiếp. Cần đối chiếu source code, bản đã triển khai, bảng lịch sử và trạng thái database trước khi quyết định sửa.

## 1. Từ changeset đến checksum: mô hình nền tảng

Một **changeset** là đơn vị migration trong changelog. Liquibase dùng tổ hợp **id + author + đường dẫn changelog** để nhận diện một changeset trong lịch sử. Đường dẫn có thể được điều chỉnh ở mức định danh bằng **logicalFilePath** theo cấu hình phù hợp.

Ví dụ một changeset YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create-table
      author: database-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Khi thực thi thành công, Liquibase ghi thông tin changeset vào **DATABASECHANGELOG**, trong đó có trường **MD5SUM**. Ở lần chạy sau, Liquibase có thể tính lại checksum từ nội dung changeset đã được phân tích và đối chiếu với giá trị lưu trước đó.

Sơ đồ khái quát:

~~~text
Changelog hiện tại
     |
     v
Parse và nhận diện changeset
     |
     +--> id + author + filename ----------+
     |                                     |
     v                                     v
Tính checksum theo quy tắc          Tìm lịch sử trong
của Liquibase                      DATABASECHANGELOG
     |                                     |
     +-----------------+-------------------+
                       |
                       v
                Đối chiếu kết quả
                       |
             +---------+----------+
             |                    |
          Nhất quán           Không nhất quán
             |                    |
             v                    v
       Tiếp tục theo          Validation error
       quy tắc thực thi       hoặc cơ chế ngoại lệ
~~~

**Checksum không phải bản sao hash nguyên byte của toàn bộ file changelog.** Liquibase tính checksum từ cách nó biểu diễn những nội dung liên quan của changeset; những thay đổi về comment, định dạng, metadata hoặc thuộc tính có thể được xử lý khác nhau theo change type, định dạng file và phiên bản Liquibase. Một số thay đổi không ảnh hưởng checksum nhưng vẫn làm thay đổi hành vi chọn hoặc thực thi changeset.

Do đó, quy tắc thực hành là **giữ nguyên ý nghĩa và định nghĩa của changeset đã triển khai**, chứ không chỉ giữ nguyên phần nào được tính checksum.

### 1.1. Nhận diện changeset khác với kiểm tra checksum

Có hai câu hỏi riêng:

1. **Liquibase có đang nhận đúng changeset lịch sử không?** Điều này phụ thuộc id, author và filename/logicalFilePath.
2. **Định nghĩa của changeset đó còn nhất quán không?** Điều này liên quan checksum đã lưu và checksum hiện tại.

Nếu di chuyển changelog từ một đường dẫn sang đường dẫn khác mà không giữ định danh logic, Liquibase có thể coi changeset là **một mục lịch sử mới**. Khi đó biểu hiện có thể là một changeset xuất hiện pending và cố chạy lại, **không nhất thiết** là checksum mismatch.

Nếu id, author và đường dẫn vẫn khớp nhưng nội dung change bị sửa sau triển khai, tình huống thường gặp hơn là **checksum mismatch**.

### 1.2. MD5SUM không có chức năng chứng minh dữ liệu thật đúng

Một DBA có thể thêm/xóa cột bằng SQL trực tiếp mà không sửa changelog. Khi đó định nghĩa changeset vẫn như cũ, checksum vẫn có thể khớp trong khi schema thực tế đã lệch (**schema drift**).

Ngược lại, một file changelog được sửa khiến checksum không khớp nhưng database chưa có thay đổi mới nào. Cả hai tình huống cần điều tra khác nhau.

| Hiện tượng | Định nghĩa changelog | Lịch sử Liquibase | Database thực tế |
|---|---|---|---|
| Checksum mismatch | Có khác biệt thuộc phạm vi checksum | Có bản ghi với checksum cũ | Có thể vẫn giữ schema cũ |
| Đổi id/author/path | Định danh mới | Bản ghi cũ không khớp định danh mới | Đối tượng có thể đã tồn tại |
| Schema drift | Không nhất thiết đổi | Lịch sử có thể vẫn nhất quán | Đã thay đổi ngoài Liquibase |
| Changeset bị MARK_RAN | Có định nghĩa changeset | Ghi nhận đã xử lý mà không chạy SQL tương ứng | Phải kiểm tra riêng |
| Migration thất bại một phần | Định nghĩa có thể không đổi | Có thể chưa ghi hoàn tất | Có thể đã có một phần DDL/DML |

**Không được coi MD5SUM là công cụ chứng minh tính toàn vẹn bảo mật của database.** Nó là cơ chế nhất quán thay đổi trong Liquibase, không thay thế kiểm toán quyền, snapshot, kiểm tra catalog hay kiểm chứng dữ liệu.

## 2. Dấu hiệu nhận biết lỗi checksum không khớp

Khi chạy validate hoặc update, Liquibase có thể báo lỗi validation liên quan changeset đã chạy. Thông điệp tùy phiên bản và loại changelog, thường có ý nghĩa tương tự:

~~~text
Validation Failed:
  1 changeset has changed since it was run
  db/changelog/orders.yaml::orders-001-create-table::database-team
  was: <stored-checksum> but is now: <current-checksum>
~~~

Đây là **ví dụ mô phỏng thông điệp**, không phải một định dạng cố định và không chứa checksum thật. Cần lấy các giá trị từ lệnh hoặc log thực tế.

Những thông tin cần ghi nhận:

- **id** và **author** của changeset.
- **FILENAME/logicalFilePath** mà Liquibase dùng làm định danh.
- Checksum đã lưu và checksum tính hiện tại nếu log cung cấp.
- Lệnh nào phát hiện lỗi, exit code và thời điểm xảy ra.
- Database, schema metadata và phiên bản Liquibase đang sử dụng.
- Commit/artifact chứa changelog và runner/framework đã gọi Liquibase.
- Trạng thái schema và dữ liệu liên quan trên database đích.

### 2.1. Checksum có thể mang prefix phiên bản

Tùy phiên bản Liquibase, MD5SUM có thể có một **prefix thể hiện phiên bản cơ chế checksum**, sau đó là phần giá trị hash. Điều này giúp phân biệt định dạng checksum qua các thế hệ Liquibase.

Không tự suy luận rằng bất kỳ hai checksum có prefix khác nhau đều là do lập trình viên sửa SQL. Khi nâng cấp Liquibase, cần kiểm tra tài liệu/ghi chú phát hành của phiên bản liên quan và hành vi cập nhật checksum được hỗ trợ.

Đồng thời, không xem khác biệt prefix là lý do đủ để chạy clear-checksums: vẫn phải xác minh cả changeset, schema và quy trình nâng cấp.

## 3. Nguyên nhân phổ biến: sửa changeset đã chạy

Đây là nguyên nhân điển hình nhất trong dự án quản lý changelog bằng Git.

Giả sử một bản phát hành đã chạy changeset A:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create-table
      author: database-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Sau đó một lập trình viên sửa trực tiếp dòng type của status thành VARCHAR(40), giữ nguyên id/author/file path. Với những thay đổi được đưa vào checksum, lần validate sau có thể báo khác biệt giữa định nghĩa cũ đã ghi nhận và định nghĩa mới.

Nếu một database mới chạy bản changelog đã sửa, cột status có thể được tạo với VARCHAR(40). Database đã chạy bản cũ vẫn có VARCHAR(20), hoặc báo lỗi khi validate. Hai môi trường không còn chia sẻ một lộ trình migration rõ ràng.

**Cách sửa thông thường:**

1. Khôi phục định nghĩa A đúng như bản đã triển khai.
2. Tạo changeset B để chuyển trạng thái từ VARCHAR(20) sang VARCHAR(40).
3. Chạy validate, status và update-sql trên database đã có lịch sử A.
4. Kiểm thử thêm trên database mới để bảo đảm A rồi B tạo kết quả mong muốn.
5. Triển khai B theo quy trình và kiểm tra hậu điều kiện.

Ví dụ changelog sau khi sửa đúng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create-table
      author: database-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)

  - changeSet:
      id: orders-002-expand-status
      author: database-team
      changes:
        - modifyDataType:
            tableName: orders
            columnName: status
            newDataType: VARCHAR(40)
~~~

**Lưu ý:** change type modifyDataType, khả năng sinh SQL và rollback phụ thuộc DBMS. Ví dụ chỉ cho thấy chiến lược thêm changeset; cần kiểm tra SQL thật, lock và tác động đến dữ liệu trên DBMS đích.

### 3.1. Vì sao không chỉnh trực tiếp MD5SUM cho khớp?

Nếu sửa MD5SUM trong DATABASECHANGELOG để Liquibase bỏ qua lỗi, phần thay đổi mới trong changelog **không tự động được thực thi** trên database đã chạy A. Việc đó có thể tạo ảo giác lịch sử nhất quán nhưng schema vẫn giữ cột VARCHAR(20).

Hơn nữa, chỉnh bảng lịch sử thủ công làm mất dấu vết điều tra và có thể ảnh hưởng những lần chạy sau. Không coi việc đổi MD5SUM trực tiếp là thủ tục sửa lỗi thông thường.

### 3.2. Bất biến bắt đầu từ môi trường dùng chung đầu tiên

Không chỉ production mới cần giữ changeset bất biến. Nếu A đã chạy trên dev chung, staging, bản triển khai của khách hàng hoặc artifact phát hành, sửa A có thể làm các database đã chạy A gặp tình trạng khác nhau.

Một changeset chưa chạy ở production không có nghĩa được phép viết lại mà không xem xét các môi trường và nhóm khác đã dùng nó.

## 4. Nguyên nhân: SQL bên ngoài thay đổi sau triển khai

Đôi khi changeset khai báo bằng **sqlFile** trong YAML/XML, còn nội dung DDL/DML đặt trong file SQL riêng. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-003-create-view
      author: database-team
      changes:
        - sqlFile:
            path: sql/orders_view.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
~~~

Nếu file sql/orders_view.sql được chỉnh sau khi changeset đã chạy, nội dung được Liquibase dùng để tính checksum có thể thay đổi dù file YAML không đổi.

Những khả năng cần kiểm tra:

- Một commit chỉnh SQL trong file được tham chiếu bởi sqlFile.
- Script được build hoặc copy từ nguồn khác và nội dung trong artifact khác Git.
- Đường dẫn **relativeToChangelogFile** giải quyết sang file khác so với dự kiến.
- Template, placeholder hoặc quá trình đóng gói đã tạo SQL khác nhau giữa các môi trường.
- Đổi encoding, kiểu xuống dòng hoặc công cụ xử lý file làm thay đổi nội dung được parser nhận theo cách có ý nghĩa.
- Một script chứa nhiều statement đã bị chỉnh delimiter/statement splitting.

Không mặc định mọi đổi line ending hay comment đều tạo checksum khác nhau; cách chuẩn hóa phụ thuộc parser và phiên bản. Cách chắc chắn là so sánh **nội dung file đã triển khai với file hiện tại**, đồng thời kiểm tra cách Liquibase thực tế đọc file ở runtime.

### 4.1. File được đóng gói trong ứng dụng cũng có thể khác source

Trong Spring Boot, changelog có thể nằm trên classpath bên trong JAR. Một job Liquibase CLI có thể dùng changelog từ filesystem. Dù hai đường dẫn nhìn tương tự nhau, chúng có thể trỏ tới **hai bản artifact khác nhau**.

Khi một môi trường báo mismatch, cần kiểm tra bản JAR, container image, commit, resource path, checksum của artifact và cấu hình change-log thực tế. Không chỉ so sánh các file hiện tại trên nhánh main rồi kết luận bản đã deploy cũng giống như thế.

## 5. Nguyên nhân: chuyển đổi định dạng, refactor hoặc di chuyển changelog

Một nhóm có thể chuyển YAML sang XML, tách một changeset thành hai changeset, gom nhiều file hoặc di chuyển changelog vào thư mục mới để “dọn dự án”.

Cần phân biệt:

| Thao tác | Rủi ro điển hình | Triệu chứng có thể |
|---|---|---|
| Đổi id | Thay định danh | Liquibase coi là changeset chưa chạy |
| Đổi author | Thay định danh | Changeset cũ không khớp lịch sử |
| Di chuyển file mà không giữ logicalFilePath | Thay định danh đường dẫn | Changeset xuất hiện pending/chạy lại |
| Chuyển YAML sang XML với khác biệt cấu trúc được tính checksum | Định nghĩa được parser biểu diễn khác | Có thể phát sinh mismatch |
| Tách/gộp changeset đã chạy | Đổi ranh giới lịch sử | Khó nhận diện, có nguy cơ thực thi lại |
| Đổi nội dung của sqlFile khi refactor | SQL lịch sử bị sửa | Có thể checksum mismatch |
| Chỉ đổi cách trình bày không ảnh hưởng nội dung được tính checksum | Không nhất thiết gây mismatch | Vẫn phải kiểm tra ý nghĩa thực thi |

**logicalFilePath** có thể giúp ổn định định danh file khi tái cấu trúc, nhưng không phải công cụ tự sửa mọi trường hợp đổi id, author hay nội dung SQL. Hãy lập kế hoạch refactor riêng, kiểm chứng với database có lịch sử cũ trước khi triển khai rộng.

### 5.1. Vì sao đường dẫn là một phần vấn đề?

Một changeset được nhận diện theo **id/author/file path**. Khi path thay đổi, câu hỏi đầu tiên không phải “MD5SUM nào đúng?” mà là “Liquibase còn đối chiếu đúng bản ghi lịch sử hay đang nhìn một changeset mới?”.

Nếu changeset xuất hiện pending sau khi di chuyển file, không tự chạy update để thử. DDL có thể tạo lại bảng hoặc constraint đã tồn tại. Khôi phục định danh logic hoặc triển khai quy trình chuyển đổi được kiểm chứng.

## 6. Nguyên nhân: tham số hóa và khác biệt cấu hình runtime

Liquibase có thể dùng changelog properties để thay thế các giá trị trong changelog. Nếu cùng một changeset được thực thi với **giá trị tham số khác nhau**, nội dung mà Liquibase xử lý, SQL được tạo và đôi khi checksum có thể khác tùy change type, vị trí property và phiên bản.

Ví dụ: một changeset tạo bảng với schemaName được cung cấp từ cấu hình ứng dụng. Staging dùng schema commerce_stage, production dùng commerce. Nếu cơ chế checksum/định nghĩa của changeset bị ảnh hưởng bởi giá trị đã thay thế, hai môi trường có thể có khác biệt cần giải thích. Dù checksum không thay đổi, **hành vi triển khai vẫn khác nhau** và phải được thiết kế có chủ đích.

Cần đối chiếu:

- Property được khai báo trong changelog hay truyền từ CLI/CI/Spring Boot.
- Giá trị của từng môi trường, tránh in bí mật trong log.
- Thứ tự include và phạm vi property.
- Changelog path, context/label và dbms selection.
- Phiên bản Liquibase và cách parser giải quyết property.
- SQL preview và schema thực tế được tạo.

**Không sử dụng việc đổi giá trị property như một cách thay thế migration.** Nếu một changeset tạo cột với default ban đầu là PENDING rồi yêu cầu mới là NEW, hãy tạo changeset mới để đổi default trên database đã triển khai. Đổi property trong changeset lịch sử không tự làm database cũ cập nhật đúng.

### 6.1. Cấu hình Spring Boot cần đối chiếu từ giá trị cuối cùng

Một ứng dụng có thể có application.yml, profile riêng, biến môi trường và cấu hình ngoài. Chỉ đọc một file chưa chắc cho biết giá trị mà Spring Boot truyền vào Liquibase lúc chạy.

Khi điều tra mismatch giữa CLI và Spring Boot, phải xác định:

1. Root changelog từ **spring.liquibase.change-log**.
2. Các tham số từ **spring.liquibase.parameters** nếu dùng.
3. Profile active, datasource, schema metadata.
4. Context/label và cấu hình Liquibase ở từng runtime.
5. Phiên bản Liquibase được đóng gói trong ứng dụng.
6. Commit/JAR/container image được triển khai.

Không ghi giá trị bí mật hay connection string chứa password vào ticket điều tra.

## 7. Nguyên nhân: nâng cấp Liquibase hoặc thay đổi bộ xử lý

Checksum được tạo theo logic của Liquibase. Việc nâng cấp phiên bản Liquibase, thay đổi extension, JDBC integration hoặc cách phân tích changelog có thể tạo khác biệt trong một số trường hợp. Cũng có cơ chế nâng cấp định dạng checksum được Liquibase hỗ trợ.

Không nên kết luận theo kiểu:

- “Checksum khác chắc chắn là do SQL bị sửa.”
- “Vừa nâng Liquibase nên checksum nào khác cũng vô hại.”

Cả hai kết luận đều thiếu bằng chứng. Phải kiểm tra:

1. Phiên bản Liquibase trước và sau.
2. Tính năng, extension hoặc parser mới có ảnh hưởng loại changeset đang xét không.
3. Ghi chú phát hành/tài liệu nâng cấp checksum tương ứng.
4. Nguồn changelog trong artifact cũ và mới.
5. Database và bản ghi MD5SUM thực tế.
6. Kết quả thử nghiệm trên database staging có cùng lịch sử.

Nếu sự khác biệt được chứng minh chỉ là thay đổi thuật toán hoặc cách tính được Liquibase xử lý theo quy trình nâng cấp chính thức, hãy làm theo thủ tục được hỗ trợ. Không tự thay toàn bộ MD5SUM hoặc xóa lịch sử.

### 7.1. Không so sánh hash khi thiếu điều kiện tương đương

Hai kết quả checksum từ hai phiên bản, hai parser, hai tập property hoặc hai đường dẫn có thể không thể được giải thích chỉ bằng so sánh chuỗi hash.

Để kết luận một changeset thật sự đã bị sửa, cần **đặt hai định nghĩa trong cùng bối cảnh**: cùng bản changelog nguồn, cùng các resource được tham chiếu, cùng parser/Liquibase khi có thể, cùng tính năng liên quan.

## 8. Những thay đổi không nhất thiết làm checksum khác

Một nguyên nhân khác của việc chẩn đoán sai là tưởng bất kỳ chỉnh sửa nào của file đều gây mismatch. Cần hiểu rằng Liquibase không đơn thuần lấy raw bytes của toàn bộ YAML/XML để hash.

Tùy change type, format và phiên bản, những thay đổi sau **có thể không làm checksum khác**:

- Comment không được tính vào nội dung change.
- Khoảng trắng hoặc xuống dòng không làm thay đổi nội dung được parser chuẩn hóa.
- Một số metadata như context, label hoặc precondition theo cơ chế checksum hiện hành.
- Thứ tự khai báo không làm thay đổi biểu diễn đã chuẩn hóa.

Tuy nhiên, không nên biến danh sách trên thành quy tắc tuyệt đối. Ví dụ trong raw SQL, khoảng trắng hoặc comment có thể ảnh hưởng đến nội dung mà parser/cơ chế checksum dùng theo cách khác so với change type cấu trúc.

**Điểm quan trọng:** một thay đổi không làm checksum đổi **không có nghĩa an toàn về mặt triển khai**. Đổi context hoặc precondition có thể khiến một môi trường chọn hoặc bỏ qua changeset khác trước đây, dù checksum vẫn khớp. Code review phải kiểm tra cả hành vi, không chỉ kết quả validate.

## 9. Quy trình điều tra checksum mismatch theo thứ tự an toàn

Nên tiến hành điều tra theo hướng **quan sát trước, thay đổi sau**. Mục tiêu là xác định nguyên nhân mà không làm mất bằng chứng.

### Bước 1: Dừng deployment và bảo toàn bằng chứng

Khi validate hoặc update báo checksum mismatch:

- Dừng rollout và các job migration tiếp theo cho database liên quan.
- Không tự retry liên tục bằng các cờ khác nhau.
- Không chạy clear-checksums hoặc chỉnh MD5SUM để “vượt lỗi”.
- Không xóa hoặc sửa DATABASECHANGELOG.
- Ghi lại exit code, thông điệp lỗi, changeset id/author/file path và thời gian.
- Lưu bản artifact/changelog đã triển khai, cùng log có redaction phù hợp.
- Xác nhận không còn tiến trình migration khác đang chạy trước khi thực hiện bất kỳ thao tác sửa chữa nào.

Việc dừng sớm giúp giữ dữ kiện về trạng thái hiện tại và tránh một changeset chạy thêm khi nhóm vẫn đang tìm nguyên nhân.

### Bước 2: Xác định chính xác database và bảng metadata

Kiểm tra URL, host, database, catalog, schema business và schema chứa metadata Liquibase. Trong hệ thống nhiều schema, bảng **DATABASECHANGELOG** có thể nằm ở schema khác với các bảng nghiệp vụ.

Ví dụ truy vấn chỉ đọc (cần thay tên schema metadata theo cấu hình thật):

~~~sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM,
       DEPLOYMENT_ID
FROM platform_meta.DATABASECHANGELOG
WHERE ID = 'orders-001-create-table'
  AND AUTHOR = 'database-team';
~~~

Không chỉ lọc theo ID/author mà quên **FILENAME** khi một database có nhiều changelog. Cần đối chiếu cả đường dẫn trong bản ghi với đường dẫn Liquibase hiện tại.

Các cột phổ biến:

| Cột | Cách dùng khi điều tra |
|---|---|
| ID | Định danh changeset |
| AUTHOR | Người/nhóm khai báo |
| FILENAME | Đường dẫn changelog được dùng để nhận diện |
| MD5SUM | Checksum ghi nhận tại lần thực thi/xử lý tương ứng |
| DATEEXECUTED | Thời điểm ghi nhận |
| ORDEREXECUTED | Thứ tự ghi nhận changeset |
| EXECTYPE | Trạng thái như EXECUTED, RERAN, MARK_RAN |
| DEPLOYMENT_ID | Giúp liên kết những changeset cùng đợt chạy, nếu có |

Truy vấn minh họa cần điều chỉnh case/quoting của tên bảng và quyền đọc trên từng DBMS. Không thay đổi giá trị trong bảng khi đang điều tra.

### Bước 3: Tìm phiên bản changelog đã chạy

Dùng commit, tag, artifact hoặc log triển khai để tìm **bản nội dung thật** được Liquibase đọc tại thời điểm changeset chạy.

Cần so sánh những yếu tố sau:

- Định nghĩa changeset ở commit đã phát hành.
- Định nghĩa changeset ở commit hiện tại.
- SQL/file resource được include qua sqlFile, include hoặc includeAll.
- Các property và cấu hình của runtime ở hai thời điểm.
- Phiên bản Liquibase và extension/plugin có liên quan.

Không dựa duy nhất vào nhánh main. Container đang chạy hoặc JAR ở production có thể chứa artifact của commit khác với mã nguồn mà nhóm vừa checkout.

### Bước 4: Phân loại nguyên nhân

Một cách phân loại hữu ích:

~~~text
Có lỗi checksum trên changeset đã được ghi nhận?
                      |
                      v
Id/author/file path có khớp lịch sử?
           |                     |
         KHÔNG                  CÓ
           |                     |
           v                     v
Điều tra định danh /        So sánh định nghĩa
logicalFilePath             và resource ở hai bản
                                 |
                       +---------+----------+
                       |                    |
                   Có sửa nội dung      Không thấy sửa
                       |                    |
                       v                    v
                 Phục hồi change       So version Liquibase,
                 cũ + tạo change       parser, property,
                 mới nếu cần           artifact và checksum
~~~

Chỉ sau khi phân loại mới chọn hành động sửa. Nếu thay đường dẫn, xử lý định danh. Nếu sửa DDL cũ, khôi phục DDL và thêm changeset mới. Nếu đổi thuật toán checksum, xác minh bằng thủ tục nâng cấp đúng phiên bản.

### Bước 5: Đối chiếu schema và dữ liệu thật

Checksum mismatch là vấn đề nhất quán định nghĩa; không cho biết database đã chạy bao nhiêu phần của migration mong muốn.

Ví dụ với PostgreSQL:

~~~sql
SELECT column_name,
       data_type,
       character_maximum_length,
       is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Nếu changeset đáng lẽ tạo index:

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

Nếu là backfill dữ liệu, cần truy vấn hậu điều kiện nghiệp vụ, số dòng còn thiếu giá trị hoặc số dòng vi phạm ràng buộc.

Đối chiếu:

1. Định nghĩa bản đã chạy.
2. Lịch sử DATABASECHANGELOG.
3. Schema/data thực tế.
4. Định nghĩa bản hiện tại.
5. Trạng thái mà ứng dụng mới yêu cầu.

Không tự giả định tất cả các lớp này trùng nhau.

### Bước 6: Chọn phương án phục hồi có kiểm chứng

Phương án ưu tiên cho thay đổi chạy một lần là:

1. Khôi phục nội dung changeset đã triển khai.
2. Thêm changeset mới cho yêu cầu thực tế.
3. Tạo test nâng cấp từ database đã có lịch sử.
4. Chạy validate, status --verbose và update-sql với cùng cấu hình sẽ dùng khi update.
5. Review SQL và hậu điều kiện.
6. Thực thi migration trong môi trường thử nghiệm tương đương.
7. Áp dụng production theo quy trình có phê duyệt.
8. Kiểm tra DATABASECHANGELOG, schema và ứng dụng sau triển khai.

Với nguyên nhân khác như refactor đường dẫn hoặc nâng cấp parser, có thể cần quy trình kỹ thuật đặc thù. Hãy lưu quyết định, phạm vi, bằng chứng và rủi ro còn lại.

## 10. Bộ lệnh phục vụ điều tra

Giả sử CLI đã được cấu hình đúng URL, credentials, changelog và bộ lọc môi trường, các lệnh thường dùng gồm:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase history
~~~

**Ý nghĩa và giới hạn:**

| Lệnh | Giúp quan sát | Không tự chứng minh |
|---|---|---|
| validate | Changelog có hợp lệ theo các kiểm tra của Liquibase, có lỗi checksum hay không | SQL tương lai chắc chắn chạy đúng hoặc schema không drift |
| status --verbose | Những changeset pending theo cấu hình hiện tại | Đối tượng thực tế tồn tại/đúng định nghĩa |
| update-sql | SQL dự kiến khi update, trong phạm vi lệnh và cấu hình | SQL sẽ chạy thành công hoặc không ảnh hưởng lock/dữ liệu |
| history | Những changeset Liquibase đã ghi nhận | Mọi DDL/DML thực sự đã chạy hoặc không có drift |

Nếu validate đang thất bại vì checksum, **các lệnh sau cũng có thể bị chặn** theo quy tắc kiểm tra của Liquibase. Không xem việc status/update-sql không chạy được là lý do để vô hiệu hóa validation.

### 10.1. calculate-checksum

Một số phiên bản Liquibase có lệnh **calculate-checksum**, dùng để tính checksum của changeset được chọn từ changelog. Cú pháp xác định changeset và các tùy chọn đã thay đổi qua phiên bản, vì vậy hãy xem help của **chính phiên bản đang dùng** trước khi chạy.

Lệnh tính checksum có thể hỗ trợ quan sát giá trị hiện tại; nó **không tự khắc phục mismatch** và không thay thế việc so sánh nội dung giữa artifact cũ và mới.

Khi ghi nhận kết quả, lưu:

- Phiên bản Liquibase.
- ID, author, filename dùng để chọn changeset.
- Nguồn changelog và các resource được nạp.
- Bộ tham số runtime liên quan, đã loại bỏ secret.
- Giá trị checksum quan sát và thời điểm tính.

### 10.2. Tránh trộn nhiều cấu hình trong cùng cuộc điều tra

Không chạy validate với root changelog A rồi chạy update-sql với root B, hoặc dùng context dev cho status nhưng prod cho update. Phải giữ **đúng bộ cấu hình** khi so sánh và giải thích mọi thay đổi giữa các lần gọi.

Trên CI/CD, hãy cố định artifact, môi trường, cấu hình và phiên bản Liquibase cho cả chuỗi validate → status → update-sql → update.

## 11. Các cơ chế ngoại lệ: nên và không nên dùng khi mismatch

Liquibase cung cấp cơ chế cho một số trường hợp thay đổi hoặc chấp nhận lịch sử. Hiểu đúng ý nghĩa của từng cơ chế là điều kiện trước khi cân nhắc sử dụng.

### 11.1. runOnChange

Với changeset được thiết kế để **chạy lại khi định nghĩa đổi**, chẳng hạn một view/function có thể thay thế toàn phần, thuộc tính runOnChange cho phép Liquibase thực thi lại theo quy tắc phù hợp.

Ví dụ formatted SQL trên PostgreSQL:

~~~sql
--liquibase formatted sql

--changeset database-team:orders-view runOnChange:true
CREATE OR REPLACE VIEW app.orders_summary AS
SELECT id, status
FROM app.orders;
~~~

Ở đây changeset cần được review để chạy lại an toàn. Đổi định nghĩa view có thể hợp lý, trong khi bật runOnChange cho createTable, addColumn hoặc INSERT không idempotent chỉ để né checksum mismatch có thể gây lỗi hoặc thay đổi dữ liệu ngoài ý muốn.

**Không mặc định mọi chỉnh sửa comment/whitespace kích hoạt chạy lại.** Thay đổi phải được Liquibase nhận diện theo cơ chế checksum hiện hành và loại changeset liên quan.

### 11.2. runAlways

runAlways yêu cầu Liquibase thực thi lại changeset trong mỗi lần update phù hợp. Nó không phải một cách tổng quát để cho phép sửa nội dung một changeset đã chạy.

Khi sửa nội dung một changeset runAlways, vẫn cần hiểu quy tắc checksum và cách phối hợp với runOnChange theo phiên bản đang dùng. Không bật runAlways lên changeset cũ đang lỗi checksum chỉ để vượt validation.

### 11.3. validCheckSum

**validCheckSum** cho phép khai báo những checksum cụ thể được chấp nhận cho một changeset, hữu ích trong trường hợp có lịch sử cần tương thích và sự khác biệt đã được phân tích rõ.

Điều quan trọng:

- Nó chỉ thay đổi **cách Liquibase chấp nhận checksum**.
- Nó **không thực thi lại** phần DDL/DML đã sửa của một changeset được ghi nhận là hoàn tất.
- Nó **không cập nhật schema/database** để khớp định nghĩa mới.
- Nó không sửa drift, không phục hồi dữ liệu và không giải quyết thay đổi định danh.
- Một danh sách checksum chấp nhận quá rộng có thể làm yếu cơ chế phát hiện sửa lịch sử.

Chỉ dùng sau khi đã ghi rõ nguyên nhân, những checksum nào được cho phép, vì sao database hiện tại đã ở trạng thái đúng và kế hoạch kiểm chứng trên các môi trường.

### 11.4. clear-checksums

Lệnh:

~~~bash
liquibase clear-checksums
~~~

làm trống các checksum đã lưu trong bảng lịch sử để Liquibase tính lại ở lần chạy phù hợp sau đó. Lệnh **không tự tái thực thi các changeset đã ghi nhận hoàn tất và không sửa schema**.

Nếu một changeset cũ bị đổi từ VARCHAR(20) sang VARCHAR(40) mà chưa có migration chuyển cột, clear-checksums có thể khiến trạng thái checksum trông hợp lệ trong khi database vẫn giữ VARCHAR(20). Vì thế:

- **Không chạy ngay khi thấy lỗi checksum.**
- Không chạy trên production mà thiếu điều tra và phê duyệt.
- Chỉ áp dụng khi có nguyên nhân đã xác định và thủ tục tương ứng được hỗ trợ.
- Ghi lại trạng thái trước/sau và kiểm chứng schema thật.
- Hiểu rằng hành vi liên quan đến changeset chạy lại còn phụ thuộc cấu hình; không dựa vào clear-checksums như công cụ kích hoạt thay đổi mong muốn.

### 11.5. changelogSync, MARK_RAN và bảng lịch sử

Một precondition với onFail: MARK_RAN hoặc một quy trình baseline dùng changelogSync có thể ghi nhận changeset mà không thực thi SQL tương ứng. Những cơ chế này phục vụ các trường hợp database đã có trạng thái đúng nhưng cần đồng bộ lịch sử một cách có kiểm chứng.

Chúng **không được dùng để che mismatch chưa giải thích**. Lịch sử có dòng ghi nhận không chứng minh đối tượng vật lý tồn tại hoặc dữ liệu đã được chuyển đổi.

## 12. Bảng quyết định theo nguyên nhân

| Triệu chứng/chứng cứ | Nguyên nhân có khả năng | Hướng xử lý ưu tiên |
|---|---|---|
| Định nghĩa thay kiểu cột trong changeset đã chạy | Sửa lịch sử DDL | Khôi phục changeset cũ, thêm changeset đổi kiểu |
| SQL trong sqlFile khác bản đã phát hành | Sửa resource bên ngoài | Khôi phục file SQL lịch sử, tạo changeset mới hoặc runOnChange nếu đã thiết kế từ đầu |
| ID/author bị đổi | Định danh không khớp | Khôi phục định danh, tránh chạy lại |
| File bị di chuyển và changeset xuất hiện pending | FILENAME/logicalFilePath đổi | Giữ đường dẫn logic hoặc có kế hoạch chuyển đổi |
| Lỗi xuất hiện sau đổi phiên bản Liquibase | Có thể do parser/checksum version hoặc sửa changelog kèm theo | So changelog/artifact và tài liệu phiên bản, thử trên DB có lịch sử tương đương |
| Chỉ production lỗi, staging không | Có thể khác artifact, params, version hoặc lịch sử | Đối chiếu từng môi trường, không copy MD5SUM giữa database |
| Changelog có cùng ID nhưng SQL phụ thuộc property | Giá trị tham số/cách thay thế khác | Xác định cấu hình thật, ổn định định nghĩa, tạo changeset bổ sung nếu cần |
| Checksum khớp nhưng bảng/cột không đúng | Schema drift hoặc MARK_RAN/triển khai dở dang | Kiểm tra catalog/data, tạo repair migration phù hợp |
| Changeset runOnChange đổi định nghĩa view | Chạy lại có chủ đích | Kiểm tra SQL có thể chạy lại an toàn, dependency và hậu điều kiện |
| Một DDL thất bại giữa changeset không transactional | Database có thể thay đổi một phần | Đọc log, lịch sử, schema, lập forward-fix/rollback được kiểm chứng |

Bảng trên là hướng chẩn đoán, không thay thế kiểm chứng bằng source, lịch sử và database thực tế. Một lỗi có thể đồng thời có hai nguyên nhân, ví dụ di chuyển file **và** đổi SQL trong cùng PR.

## 13. Nhiều môi trường: không đồng bộ checksum bằng cách sao chép

Mỗi môi trường có bảng DATABASECHANGELOG riêng. Dev, staging và production có thể chạy cùng changelog tại các thời điểm khác nhau, với tập dữ liệu hoặc DBMS version khác nhau.

Nếu production gặp mismatch nhưng dev không gặp:

1. Kiểm tra bản đã chạy trên production là commit nào.
2. Kiểm tra dev có bị tái tạo từ database trống với changelog mới không.
3. So sánh checksum, EXECTYPE, DATEEXECUTED và đường dẫn logic ở mỗi môi trường.
4. Đối chiếu source artifact và phiên bản Liquibase.
5. Kiểm tra changeset có context/label/dbms hoặc property riêng không.
6. Quan sát schema thực tế tại cả hai nơi.

**Không sao chép MD5SUM, dòng DATABASECHANGELOG hoặc toàn bộ bảng lịch sử từ staging sang production** để “đồng bộ”. Chúng phản ánh lịch sử của từng database; việc sao chép có thể khiến Liquibase bỏ qua migration thật sự chưa chạy.

### 13.1. Database mới có thể trông đúng nhưng database nâng cấp lỗi

Một dự án có thể build database từ đầu hoàn toàn thành công nhờ changelog đã bị sửa, nhưng database cũ báo checksum mismatch. Đây là lý do CI/CD cần **hai loại test**:

- **Fresh install:** dựng database trống rồi chạy toàn bộ changelog.
- **Upgrade path:** lấy database thử nghiệm có lịch sử tương đương bản phát hành cũ, chạy changelog mới để xác minh nâng cấp.

Nếu chỉ test fresh install, nhiều lỗi sửa lịch sử không được phát hiện.

## 14. CI/CD: chặn sửa changeset đã triển khai

Một pipeline bảo vệ lịch sử nên có các bước:

~~~text
Pull request / commit
        |
        v
Đọc changelog hiện tại + bản đã phát hành
        |
        v
Phát hiện sửa/xóa/đổi tên changeset lịch sử
        |
        v
Review những ngoại lệ thực sự được thiết kế chạy lại
        |
        v
validate trên DB có lịch sử cũ
        |
        v
status --verbose + update-sql
        |
        v
Test nâng cấp + hậu điều kiện
        |
        v
Phê duyệt deploy
        |
        v
update + history + kiểm tra schema/data
~~~

### 14.1. Nguyên tắc review pull request

Reviewer cần xác minh:

- PR có sửa DDL/DML của changeset đã chạy không?
- Có đổi id/author/logicalFilePath hoặc di chuyển file không?
- Có thay sqlFile hoặc include resource đã phát hành không?
- Có thay context, label, precondition hoặc property gây thay đổi hành vi không?
- Nếu runOnChange/runAlways được dùng, thay đổi có chạy lại an toàn không?
- Database cũ và database mới có dẫn tới cấu trúc mong muốn không?
- Rollback/forward-fix có được thử với dữ liệu đại diện không?
- Artifact dùng trong CI là artifact dự kiến sẽ phát hành không?

Có thể yêu cầu các thay đổi đối với changeset đã phát hành phải qua review đặc biệt thay vì cấm mọi chỉnh sửa về mặt cú pháp. Điều quan trọng là thay đổi nào thực sự có tác động đến lịch sử và hành vi.

### 14.2. Giữ log đủ điều tra nhưng không lộ bí mật

Khi lỗi checksum xảy ra, CI nên ghi lại:

- Commit, artifact, phiên bản Liquibase và database đích đã redacted.
- Lệnh gây lỗi, exit code, timestamp và changeset liên quan.
- Hash/changelog checksum được báo nếu có.
- Kết quả so sánh artifact cũ/mới.
- Kết quả kiểm tra schema/data và người phê duyệt phương án phục hồi.

Không ghi password, token hoặc SQL chứa PII vào ticket công khai. SQL preview và log debug có thể chứa dữ liệu literal; phân quyền và thời hạn lưu phải phù hợp mức nhạy cảm.

### 14.3. Spring Boot và tính nhất quán artifact

Nếu Spring Boot chạy Liquibase khi ứng dụng khởi động, lỗi checksum thường khiến việc khởi tạo ứng dụng thất bại theo đường exception của Liquibase/JDBC và Spring context, trừ khi ứng dụng có xử lý riêng.

Vì thế:

- Xác định root changelog từ cấu hình Spring Boot đang thực sự active.
- Kiểm tra dependency Liquibase mà ứng dụng đóng gói, không giả định trùng CLI của máy phát triển.
- Không để nhiều instance triển khai các artifact mang changelog khác nhau cùng lúc.
- Với deployment nhiều instance, một migration job chuyên trách trước rollout có thể giúp cố định phiên bản và quyền.
- Bảo đảm job báo lỗi non-zero khi validate/update thất bại, không nuốt exception trong wrapper.
- Kiểm tra DATABASECHANGELOGLOCK nếu nhiều tiến trình cùng cố migration, nhưng không xem lock là cách giải quyết checksum mismatch.

## 15. Rollback và forward-fix khi có checksum mismatch

**Rollback không phải cách mặc định xử lý mismatch.** Nếu mới chỉ sửa file changelog còn database chưa thay đổi, khôi phục file cũ và tạo changeset mới có thể là đủ. Nếu migration dở dang hoặc schema đã đổi ngoài Liquibase, cần đánh giá riêng.

### 15.1. Khi không có thay đổi vật lý phát sinh

Ví dụ validate phát hiện sửa A trước khi update thực thi bất kỳ migration mới nào. Khi đó:

1. Dừng deploy.
2. Xác minh A đã chạy trên database.
3. Khôi phục A đúng lịch sử.
4. Thêm B cho nhu cầu mới.
5. Test cả nâng cấp và dựng mới.
6. Deploy B có kiểm chứng.

Không rollback A chỉ để có cơ hội sửa nó rồi chạy lại, nhất là khi A tạo bảng chứa dữ liệu thật.

### 15.2. Khi database đã bị sửa một phần

Nếu một DDL trước đó auto-commit hoặc changeset runInTransaction: false thực thi một phần, lịch sử và schema có thể lệch. Cần:

- Xác định SQL nào thực sự chạy.
- Xem transaction và lock của DBMS.
- Kiểm tra đối tượng, constraint và dữ liệu.
- Đánh giá rollback có khôi phục được dữ liệu không.
- Chọn forward-fix nếu việc lùi lại nguy hiểm hơn.
- Lập changeset sửa chữa có precondition/hậu điều kiện phù hợp.

Không xóa dòng lịch sử rồi chạy lại nguyên changeset khi chưa chứng minh thao tác đó idempotent và đúng trạng thái database hiện tại.

## 16. Bài thực hành: tái hiện mismatch và sửa bằng changeset mới

**Điều kiện:** database thử nghiệm riêng có thể tạo/xóa an toàn, Liquibase CLI được cấu hình đúng database test, không có dữ liệu production và không có người khác dùng chung database lab.

### Bước 1. Tạo changeset A

Tạo changelog YAML thử nghiệm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-orders
      author: learner
      changes:
        - createTable:
            tableName: lab_orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Thực hiện các bước:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Ghi lại: exit code, changeset đã chạy, định nghĩa cột status, id/author/file path và giá trị checksum trong bảng DATABASECHANGELOG.

### Bước 2. Cố ý sửa changeset đã chạy

Chỉ trong lab, thay type của status từ VARCHAR(20) thành VARCHAR(40) **ngay trong lab-001**, không tạo changeset mới.

Chạy:

~~~bash
liquibase validate
~~~

Đọc thông điệp và đối chiếu checksum cũ/mới nếu được cung cấp. Trong trường hợp thay đổi này được đưa vào checksum theo phiên bản Liquibase đang dùng, validation sẽ phát hiện không nhất quán.

Không chạy clear-checksums; không sửa trực tiếp bảng DATABASECHANGELOG. Quan sát cột status trong database có còn độ dài 20 hay không; validate không phải thao tác ALTER TABLE.

### Bước 3. Phục hồi A và thêm changeset B

Khôi phục lab-001 về VARCHAR(20). Thêm lab-002:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-orders
      author: learner
      changes:
        - createTable:
            tableName: lab_orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)

  - changeSet:
      id: lab-002-expand-status
      author: learner
      changes:
        - modifyDataType:
            tableName: lab_orders
            columnName: status
            newDataType: VARCHAR(40)
~~~

Kiểm tra:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Chỉ chạy update trên database lab khi SQL đổi kiểu hợp lệ với DBMS thử nghiệm và đã review. Sau update, kiểm tra lab-001 không bị thực thi lại, lab-002 được ghi nhận và cột status có độ dài 40.

### Bước 4. Thử lại trên database mới

Tạo một **database lab khác** hoặc xóa dựng lại database thử nghiệm theo quy trình an toàn. Chạy cùng changelog đã có A và B, rồi so sánh schema cuối cùng.

Đường nâng cấp A → B và đường fresh install A → B cần cho ra kết quả nhất quán trong phạm vi kiểm tra. Lưu ý: kết quả tương đương không tự chứng minh mọi dữ liệu nghiệp vụ đã đúng; với migration dữ liệu phải thêm hậu điều kiện tương ứng.

### Bước 5. Phân tích tình huống đổi đường dẫn

Trong một bản sao lab khác (không ảnh hưởng production), thử đổi path của changelog mà không thay id/author rồi quan sát status. Nếu Liquibase coi changeset như mới, giải thích sự khác biệt giữa **identity mismatch** và **checksum mismatch**.

Không thực thi update khi status cho thấy Liquibase muốn tạo lại bảng đang tồn tại. Tìm hiểu cơ chế logicalFilePath phù hợp phiên bản để giữ định danh lịch sử khi cần di chuyển file.

### Bước 6. Ghi biên bản

| Nội dung | Điều cần ghi |
|---|---|
| Database và Liquibase version | Giá trị thật, không chứa secret |
| Changeset | ID, author, filename |
| Changelog trước/sau | Diff của định nghĩa và resource liên quan |
| Stored/current checksum | Giá trị quan sát được |
| Lệnh và exit code | validate, status, update-sql, update nếu đã thực thi |
| Nguyên nhân gốc | Sửa DDL, đổi path, version, property hay resource |
| Phương án xử lý | Khôi phục A, thêm B hoặc thủ tục được hỗ trợ |
| Hậu điều kiện | Cột status, lịch sử, ứng dụng test |
| Bài học phòng ngừa | Quy tắc PR/CI để không viết lại history |

Không điền giá trị checksum hoặc exit code giả làm kết quả thực tế.

## 17. Các sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm? |
|---|---|
| Chạy clear-checksums ngay khi thấy lỗi | Có thể che việc sửa changeset mà không sửa schema |
| Sửa MD5SUM bằng SQL trực tiếp | Mất bằng chứng và khiến lịch sử không còn đáng tin |
| Xóa dòng DATABASECHANGELOG để chạy lại | Có thể tạo lại bảng/index hoặc chạy DML gây hỏng dữ liệu |
| Đổi id hoặc author để tránh mismatch | Liquibase có thể coi là một changeset hoàn toàn mới |
| Đổi file path mà không giữ logicalFilePath | Có thể xuất hiện changeset pending không mong muốn |
| Chấp nhận mọi checksum bằng cơ chế quá rộng | Làm yếu tín hiệu phát hiện thay đổi ngoài dự kiến |
| Bật runOnChange cho mọi changeset | Những thao tác không idempotent có thể chạy lại gây lỗi |
| Chỉ test database mới, bỏ qua database đã triển khai | Không phát hiện được nhiều lỗi sửa lịch sử |
| Copy bảng lịch sử hoặc MD5SUM giữa môi trường | Lịch sử và schema từng database không giống nhau |
| Kết luận checksum khớp thì không có drift | Database có thể bị sửa ngoài Liquibase |
| Không kiểm tra resource sqlFile/include | Bản SQL thực tế có thể khác dù YAML giống nhau |
| Để wrapper CI nuốt lỗi validation | Deployment có thể báo PASS giả |
| Bỏ qua EXECTYPE/MARK_RAN | Có bản ghi lịch sử nhưng SQL chưa thực thi |
| Sửa changelog production ngay để “thử” | Có thể làm các instance/runner khác dùng định nghĩa mâu thuẫn |

## 18. Checklist điều tra trước khi cho phép triển khai lại

- [ ] Đã xác định đúng database, schema business và schema chứa DATABASECHANGELOG.
- [ ] Đã ghi lệnh thất bại, exit code, thời điểm, Liquibase version và root changelog.
- [ ] Có id, author, FILENAME và stored/current checksum của changeset liên quan.
- [ ] Đã lưu commit/artifact đã triển khai và artifact hiện tại.
- [ ] Đã so sánh định nghĩa changeset và các file sqlFile/include được tham chiếu.
- [ ] Đã kiểm tra logicalFilePath, đổi id/author/path và cấu trúc include.
- [ ] Đã so sánh property, context, label, dbms, Spring Boot profile và phiên bản Liquibase.
- [ ] Đã xác định thay đổi nào thực sự có thể ảnh hưởng checksum, không suy luận từ tên file.
- [ ] Đã kiểm tra EXECTYPE, MD5SUM và trạng thái lịch sử trên database đích.
- [ ] Đã đối chiếu schema/data thực tế, phân biệt mismatch với drift hoặc MARK_RAN.
- [ ] Chưa xóa/sửa MD5SUM hoặc dòng DATABASECHANGELOG bằng tay để né validation.
- [ ] Không dùng clear-checksums hoặc validCheckSum khi chưa có nguyên nhân và phê duyệt.
- [ ] Nếu changeset chạy một lần đã sửa, đã khôi phục bản cũ và tạo changeset mới.
- [ ] Nếu có ngoại lệ runOnChange, đã thử tính an toàn khi chạy lại.
- [ ] Đã thử upgrade path từ database có lịch sử cũ và fresh install.
- [ ] validate, status --verbose, update-sql và hậu điều kiện đều được review bằng cấu hình nhất quán.
- [ ] Có rollback/forward-fix hoặc backup được kiểm chứng cho thay đổi rủi ro.
- [ ] CI/CD và Spring Boot sẽ báo thất bại thay vì nuốt lỗi migration.
- [ ] Bằng chứng điều tra được lưu an toàn, không có password/token/PII trong log công khai.
- [ ] Người có thẩm quyền đã xác nhận phương án trước khi chạy production.

## 19. Kết luận

**Checksum mismatch trong Liquibase là dấu hiệu định nghĩa changeset hiện tại không còn nhất quán với lịch sử đã ghi nhận**, hoặc có khác biệt về cách Liquibase đọc và tính checksum trong bối cảnh thực thi. Khi gặp lỗi, hãy phân biệt **thay đổi nội dung**, **thay đổi định danh**, **khác biệt runtime/parser** và **schema drift**, vì mỗi tình huống có hướng xử lý khác nhau.

Quy trình ưu tiên là dừng deployment, bảo toàn log và artifact, đối chiếu id/author/filename/MD5SUM trong DATABASECHANGELOG, so sánh định nghĩa ở commit cũ và mới, xác minh schema/data thực tế rồi mới chọn phương án. Với changeset chạy một lần đã triển khai, cách an toàn thông thường là **khôi phục lịch sử và tạo changeset mới**. Các cơ chế runOnChange, validCheckSum hay clear-checksums chỉ phục vụ những trường hợp được hiểu và kiểm chứng đầy đủ.

Kết hợp kiểm soát bất biến changeset trong Git, kiểm thử đường nâng cấp, hậu kiểm database và CI/CD/Spring Boot dùng đúng artifact sẽ giúp phát hiện lỗi sớm, tránh che giấu lịch sử và duy trì migration có thể kiểm toán trên nhiều môi trường.
