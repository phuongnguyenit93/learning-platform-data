
# Ảnh hưởng của đổi đường dẫn, tác giả hoặc id changeset trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase theo dõi thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Một changeset không chỉ là đoạn YAML hoặc SQL mô tả thao tác. Liquibase cần một **định danh ổn định** để biết thay đổi nào đã được áp dụng trên database. Khi đổi đường dẫn tệp, tác giả hoặc id của changeset sau khi đã triển khai, công cụ có thể nhận diện nó thành **một changeset khác** và cố gắng chạy lại.

Chủ đề thuộc chương **Checksum và lịch sử** này giải thích bộ ba định danh `id`, `author`, `filename`; vai trò riêng của checksum; ảnh hưởng của việc di chuyển/đổi tên tệp; cách dùng `logicalFilePath` để giữ định danh đường dẫn logic; và cách xử lý an toàn khi cần tái cấu trúc changelog. Bài cũng phân biệt các lỗi checksum với trường hợp changeset bị nhận diện thành mới, hướng dẫn truy vấn DATABASECHANGELOG, cùng những lưu ý khi dùng `validCheckSum`, `clearCheckSums`, `runOnChange` và `runAlways`.

Mục tiêu là giữ cho cùng một revision changelog có thể được tái sử dụng qua development, test, staging và production mà không vô tình chạy lại DDL/DML đã phát hành.

## 1. Changeset có định danh, không chỉ có nội dung

Một changeset Liquibase được nhận diện thông thường bằng ba thành phần:

1. **id** — mã changeset do người viết khai báo.
2. **author** — tác giả hoặc nhóm được khai báo trong changeset.
3. **filename** — đường dẫn changelog chứa changeset theo cách Liquibase ghi nhận, có thể chịu ảnh hưởng của định danh đường dẫn logic.

Có thể biểu diễn:

~~~text
changeset identity = id + author + filename
~~~

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Giả sử changeset nằm trong `db/changelog/001-create-customer.yaml`. Liquibase không chỉ nhìn thấy câu lệnh createTable; nó còn ghi nhận changeset có id là `001-create-customer`, author là `schema-team` và tệp changelog tương ứng.

**Bộ ba này là khóa nhận diện lịch sử.** Nếu một thành phần thay đổi, Liquibase có thể coi đó là một changeset mới, dù các câu lệnh bên trong giống hệt nhau.

Điều này giải thích vì sao thay tên tác giả cho đẹp, đổi id theo quy ước mới hoặc di chuyển tệp sau release có thể gây lỗi trùng bảng, trùng dữ liệu hay migration chạy lại ngoài ý muốn.

## 2. Checksum là dữ liệu khác với định danh changeset

Liquibase lưu checksum của changeset đã được xử lý, thường trong cột **MD5SUM** của DATABASECHANGELOG. Checksum dùng để đối chiếu nội dung changeset hiện tại với nội dung đã được ghi nhận trước đó, theo thuật toán và phiên bản Liquibase.

Cần phân biệt:

| Thành phần | Câu hỏi được trả lời | Vai trò |
|---|---|---|
| id | Đây là changeset nào theo mã do nhóm đặt? | Định danh |
| author | Ai/nhóm nào được khai báo là tác giả? | Định danh |
| filename | Changeset thuộc đường dẫn changelog logic nào? | Định danh |
| MD5SUM | Nội dung được Liquibase kiểm tra có còn tương thích với lịch sử không? | Kiểm tra nội dung |
| EXECTYPE | Changeset được ghi nhận thực thi theo kiểu nào? | Lịch sử thực thi |

**Checksum không thay thế bộ ba định danh.** Hai changeset có thể có nội dung giống nhau và checksum giống nhau, nhưng khác id hoặc author hoặc filename thì vẫn là hai định danh khác nhau.

Ngược lại, changeset giữ nguyên id/author/filename nhưng phần nội dung được Liquibase theo dõi thay đổi có thể gây lỗi checksum validation. Đây là hai loại sự cố khác nhau và cần cách xử lý khác nhau.

## 3. DATABASECHANGELOG lưu định danh như thế nào?

Liquibase dùng bảng lịch sử mặc định **DATABASECHANGELOG** trong database đích. Các cột quan trọng gồm:

| Cột | Ý nghĩa |
|---|---|
| ID | Giá trị id của changeset |
| AUTHOR | Giá trị author của changeset |
| FILENAME | Đường dẫn changelog được dùng làm thành phần định danh |
| MD5SUM | Checksum được ghi nhận |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận xử lý changeset |
| ORDEREXECUTED | Thứ tự thực thi được ghi nhận |
| EXECTYPE | Kiểu xử lý, ví dụ EXECUTED, MARK_RAN hoặc RERAN |
| DESCRIPTION | Mô tả change type được Liquibase tạo |
| COMMENTS | Comment metadata nếu được ghi nhận |
| LIQUIBASE | Phiên bản Liquibase liên quan đến lần ghi nhận |

Cấu trúc và tập cột chi tiết có thể thay đổi theo phiên bản Liquibase, cấu hình tên/schema bảng lịch sử và DBMS. Trong thiết kế mặc định, tổ hợp **ID + AUTHOR + FILENAME** được dùng để nhận diện changeset trong lịch sử.

Một truy vấn kiểm tra cụ thể:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
WHERE ID = '001-create-customer'
  AND AUTHOR = 'schema-team';
~~~

Khi điều tra một changeset có khả năng bị di chuyển, phải xem cả **FILENAME**. Chỉ lọc theo ID và AUTHOR có thể trả về nhiều hàng nếu cùng một bộ giá trị đó được dùng trong các tệp khác nhau.

Không sửa trực tiếp ID, AUTHOR, FILENAME hoặc MD5SUM trong DATABASECHANGELOG để làm cho lịch sử “khớp” với file mới. Bảng này là lịch sử do Liquibase quản lý; sửa tay có thể làm mất bằng chứng về thay đổi thực tế và khiến lần update sau diễn giải sai.

## 4. Đổi id: Liquibase có thể coi là changeset mới

Giả sử một changeset đã triển khai:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Sau khi database production đã ghi nhận changeset này, developer đổi id thành:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer-table
      author: schema-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Đối với Liquibase, `001-create-customer-table` có định danh khác với `001-create-customer`. Bản ghi cũ vẫn tồn tại trong DATABASECHANGELOG, còn changeset mới có thể được xem là pending.

Khi chạy update, Liquibase có thể cố tạo lại bảng customer và gặp lỗi đối tượng đã tồn tại. Với changeset INSERT, hậu quả có thể là duplicate key; với UPDATE hoặc DELETE, thay đổi có thể được thực hiện thêm lần nữa và làm sai dữ liệu.

**Đổi id sau khi triển khai không phải thao tác đổi nhãn vô hại.** Nếu chỉ muốn tên changeset dễ đọc hơn, hãy giữ id cũ và cải thiện comment/tài liệu bên ngoài theo chính sách của dự án. Nếu cần thay đổi cấu trúc hoặc nội dung, tạo changeset mới có id mới và mục đích rõ ràng.

## 5. Đổi author: thay đổi tác giả cũng thay đổi định danh

Author là chuỗi do người viết khai báo trong changeset, không phải danh tính đã xác thực của tài khoản thực thi migration.

Ví dụ changeset cũ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: nguyen-a
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
~~~

Một đợt chuẩn hóa muốn thay author thành tên nhóm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: customer-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
~~~

Dù id, đường dẫn và SQL không đổi, author đã đổi nên bộ ba định danh cũng đổi. Liquibase có thể xem đây là changeset chưa chạy.

Cách tổ chức tốt hơn là chọn **author ổn định ngay từ đầu**, ví dụ tên team, domain hoặc một định danh kỹ thuật theo quy ước tổ chức. Nếu dự án đã dùng tên cá nhân và changeset đã triển khai, không đổi author hàng loạt chỉ để đồng bộ phong cách.

Nếu muốn biết ai viết, review hay triển khai, hãy dùng Git, pull request, release record và log CI/CD. Author trong changelog chỉ là metadata của changeset; nó không thay thế audit danh tính thực tế.

## 6. Đổi đường dẫn tệp: FILENAME là một phần của định danh

Giả sử changeset ban đầu ở:

~~~text
db/changelog/changes/001-create-customer.yaml
~~~

Sau khi phát hành, nhóm tổ chức lại thư mục và di chuyển tệp sang:

~~~text
db/changelog/schema/customer/001-create-customer.yaml
~~~

Nếu Liquibase ghi nhận đường dẫn mới khác với FILENAME cũ, bộ ba định danh thay đổi. Changeset ở vị trí mới có thể được coi là changeset chưa chạy, dù id, author và SQL giống hệt.

Hậu quả thường thấy:

- CREATE TABLE bị chạy lại và lỗi vì bảng đã tồn tại.
- INSERT bị chạy lại và vi phạm unique constraint.
- UPDATE/DELETE có thể tác động thêm một lần trên dữ liệu hiện tại.
- Status báo changeset pending, khiến nhóm tưởng rằng release cũ chưa áp dụng.
- Database mới và database đã tồn tại có thể có lịch sử khác nhau.

Đổi tên file, đổi folder, thay cách include hoặc chuyển changelog giữa các resource path đều cần được đánh giá theo **đường dẫn hiệu lực Liquibase sử dụng**. Không chỉ nhìn path trong IDE hoặc đường dẫn tương đối trên máy developer.

## 7. Di chuyển master changelog khác với di chuyển tệp chứa changeset

Cần xác định đúng file nào chứa changeset:

~~~text
db/changelog/
  db.changelog-master.yaml
  changes/
    001-create-customer.yaml
    002-add-customer-status.yaml
~~~

Master chỉ include các tệp con:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Nếu chỉ di chuyển master nhưng các tệp con vẫn giữ nguyên đường dẫn logic, định danh của changeset trong tệp con có thể vẫn được giữ nguyên. Ngược lại, di chuyển chính `001-create-customer.yaml` có khả năng thay đổi thành phần FILENAME của changeset đó.

Tuy nhiên, cách Liquibase phân giải resource và đường dẫn được ghi nhận còn phụ thuộc định dạng changelog, ResourceAccessor, classpath, cấu hình và logicalFilePath. Vì thế, **không suy đoán FILENAME chỉ từ tên master hoặc include**. Hãy truy vấn DATABASECHANGELOG ở database đã triển khai và kiểm tra hành vi trên phiên bản Liquibase thật.

## 8. logicalFilePath: giữ định danh logic khi tái cấu trúc

Liquibase hỗ trợ cơ chế **logicalFilePath** để chỉ định đường dẫn logic dùng cho định danh changeset, thay vì buộc định danh phụ thuộc vào vị trí vật lý hiện tại của tệp. Đây là công cụ quan trọng khi cần di chuyển hoặc đổi tên changelog đã được triển khai.

Ý tưởng:

~~~text
Đường dẫn vật lý cũ:
db/changelog/changes/001-create-customer.yaml

Đường dẫn vật lý mới:
db/changelog/schema/customer/001-create-customer.yaml

Đường dẫn logic cần bảo toàn:
db/changelog/changes/001-create-customer.yaml
~~~

Nếu phiên bản và định dạng Liquibase đang dùng hỗ trợ, changelog có thể khai báo logicalFilePath để giữ giá trị FILENAME logic cũ. Ví dụ minh họa theo dạng YAML changelog:

~~~yaml
databaseChangeLog:
  - logicalFilePath: db/changelog/changes/001-create-customer.yaml
  - changeSet:
      id: 001-create-customer
      author: schema-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

**Cú pháp, phạm vi áp dụng và quy tắc kế thừa logicalFilePath phụ thuộc phiên bản Liquibase và định dạng changelog.** Trước khi dùng, phải kiểm tra tài liệu đúng phiên bản/edition và thử trên bản sao database có lịch sử cũ. Không copy ví dụ này vào dự án mà chưa xác nhận XSD/schema parser hoặc cấu trúc YAML được hỗ trợ.

Giá trị logic phải khớp với FILENAME đã ghi trong DATABASECHANGELOG, không chỉ là đường dẫn cũ mà developer nhớ. Có thể có sự khác biệt về dấu phân cách thư mục, chữ hoa/chữ thường hoặc cách chuẩn hóa đường dẫn giữa môi trường.

## 9. logicalFilePath không sửa được id hoặc author đã thay đổi

logicalFilePath chỉ xử lý thành phần **filename/path logic** của định danh. Nó không làm cho một changeset có id mới trở lại thành id cũ, cũng không biến author mới thành author cũ.

Ví dụ:

| Thành phần | DATABASECHANGELOG cũ | File hiện tại | Kết quả |
|---|---|---|---|
| id | 001-create-customer | 001-create-customer | Khớp |
| author | schema-team | schema-team | Khớp |
| filename | db/changelog/changes/001.yaml | logicalFilePath giữ giá trị cũ | Khớp nếu đúng chính xác |
| id | 001-create-customer | 001-create-customer-v2 | **Không khớp** |
| author | schema-team | platform-team | **Không khớp** |

Nếu id hoặc author đã đổi, dù logicalFilePath được giữ nguyên, Liquibase vẫn có thể nhận diện changeset thành mới. Không dùng logicalFilePath như một công cụ “alias” cho toàn bộ định danh.

## 10. Đổi identity và sửa nội dung tạo ra hai loại lỗi khác nhau

Đây là điểm quan trọng nhất khi chẩn đoán.

### Trường hợp A — Identity đổi

- ID, AUTHOR hoặc FILENAME hiện tại không khớp row lịch sử.
- Liquibase không tìm thấy changeset có cùng bộ định danh.
- Changeset mới có thể xuất hiện như pending.
- Khi update, phần changes có thể được thực thi lại.
- Lỗi có thể là bảng/cột đã tồn tại, duplicate key hoặc dữ liệu bị sửa lần nữa.

### Trường hợp B — Identity giữ nguyên nhưng nội dung đổi

- ID, AUTHOR và FILENAME vẫn khớp.
- Liquibase tìm thấy changeset đã được ghi nhận.
- Checksum hiện tại có thể không khớp checksum đã lưu.
- Validation có thể báo lỗi checksum mismatch và dừng update.
- Changeset thông thường không tự chạy lại chỉ vì nội dung thay đổi, trừ khi có cấu hình đặc biệt như runOnChange.

| Dấu hiệu | Identity đổi | Nội dung đổi |
|---|---|---|
| Bộ ba id/author/filename | Khác | Giữ nguyên |
| Row lịch sử tương ứng | Không khớp identity hiện tại | Tìm thấy row |
| Pending | Có thể xuất hiện như changeset mới | Thông thường không, nếu identity vẫn khớp |
| Lỗi thường gặp | Duplicate object/key khi chạy lại | Checksum validation failed |
| Hướng xử lý | Khôi phục identity hoặc giữ logical path phù hợp; không chạy lại mù quáng | So sánh revision, dùng changeset mới hoặc xử lý checksum có chủ đích |

Không nên dùng `clearCheckSums` để giải quyết lỗi identity đổi: nó không đổi id, author hoặc filename cũ trong lịch sử.

## 11. Checksum không phải hash của toàn bộ file theo cách đơn giản

Liquibase tạo checksum dựa trên nội dung changeset theo quy tắc của phiên bản. Không nên giả định MD5SUM là hash byte-for-byte của toàn bộ file YAML/SQL.

Những yếu tố như định dạng, cách chuẩn hóa, change type và phiên bản Liquibase có thể ảnh hưởng cách checksum được tính. Một số thuộc tính metadata hoặc cách biểu diễn có thể không tham gia checksum giống nhau. Vì vậy:

- Không tự tính hash file bằng công cụ ngoài rồi so trực tiếp với MD5SUM.
- Không kết luận mọi thay đổi khoảng trắng/comment đều gây checksum mismatch.
- Không kết luận thay đổi comment/author/id/path luôn chỉ ảnh hưởng checksum.
- Khi có lỗi, đọc thông báo Liquibase và kiểm tra đúng phiên bản đã ghi nhận trong lịch sử.

**ID, author và filename là định danh; checksum là phép kiểm tra nội dung theo quy tắc Liquibase.** Giữ hai khái niệm tách biệt sẽ giúp xử lý đúng sự cố.

## 12. clearCheckSums làm gì, và không làm gì?

Lệnh `clearCheckSums` xóa các giá trị checksum đã lưu trong bảng DATABASECHANGELOG để Liquibase tính lại checksum ở lần chạy thích hợp tiếp theo.

Ví dụ CLI minh họa:

~~~text
liquibase clear-checksums
~~~

Tên lệnh và cách gọi tùy phiên bản CLI/plugin. Đây là một thao tác quản trị có ảnh hưởng đến lịch sử checksum; phải chạy đúng database đích và theo quy trình được review.

**clearCheckSums không:**

- Sửa ID, AUTHOR hoặc FILENAME.
- Gộp hai changeset identity thành một.
- Tự động chạy lại mọi changeset đã thực thi.
- Phục hồi dữ liệu đã bị thay đổi.
- Sửa schema bị drift.
- Thay thế việc so sánh changelog hiện tại với revision đã phát hành.

Nếu changeset bị xem là mới vì path hoặc author đổi, xóa checksum không làm Liquibase tìm được row cũ theo định danh mới. Nếu nội dung bị sửa sai, clearCheckSums có thể khiến checksum mới được ghi nhận mà không giải quyết nguyên nhân gốc; điều này có thể làm mất tín hiệu phát hiện thay đổi ngoài dự kiến.

Chỉ dùng khi nhóm **cố ý muốn tính lại checksum** theo một kế hoạch đã đánh giá, có bản sao database và biết chính xác tác động. Không dùng như bước đầu tiên khi pipeline báo lỗi.

## 13. validCheckSum: chấp nhận checksum cụ thể, không đổi định danh

Liquibase hỗ trợ thuộc tính **validCheckSum** trong một số trường hợp cần chấp nhận một checksum cũ hoặc checksum cụ thể đã được đánh giá.

Ví dụ minh họa cấu trúc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 013-create-report-view
      author: reporting-team
      validCheckSum:
        - "8:example-previous-checksum"
      changes:
        - createView:
            viewName: v_customer_report
            selectQuery: SELECT id, email FROM customer
~~~

Chuỗi checksum trong ví dụ là giá trị giả, không dùng cho triển khai. Phải lấy giá trị thật từ thông báo Liquibase hoặc DATABASECHANGELOG, và xác nhận cú pháp theo phiên bản.

validCheckSum có thể hữu ích khi nhóm chủ động chấp nhận một phiên bản nội dung đã biết trong một tình huống có lý do. Nhưng nó **không**:

- Làm changeset có ID mới trở thành ID cũ.
- Làm author mới trở thành author cũ.
- Bảo toàn FILENAME khi tệp bị di chuyển.
- Chứng minh database có schema/dữ liệu đúng.
- Thay thế changeset sửa tiếp cho thay đổi nghiệp vụ mới.

Tránh `validCheckSum: ANY` như một cách bỏ qua mọi khác biệt. Chấp nhận mọi checksum có thể che giấu thay đổi ngoài dự kiến và làm giảm khả năng phát hiện drift trong changelog.

## 14. runOnChange và runAlways không phải công cụ sửa identity

Hai thuộc tính thường bị dùng nhầm:

- **runOnChange: true** cho phép changeset được chạy lại khi nội dung được Liquibase theo dõi thay đổi checksum theo quy tắc hỗ trợ. Thường phù hợp với các đối tượng có định nghĩa có thể thay thế như view hoặc stored procedure, nếu nhóm đã thiết kế việc thay thế an toàn.
- **runAlways: true** yêu cầu changeset được xét chạy mỗi lần update thích hợp, kể cả khi đã có lịch sử. Thích hợp cho một số tác vụ được thiết kế để chạy lặp lại, không phải cho mọi DDL/DML.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 014-refresh-customer-view
      author: reporting-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_active_customer
            replaceIfExists: true
            selectQuery: |
              SELECT id, email
              FROM customer
              WHERE status = 'ACTIVE'
~~~

Đây là ví dụ minh họa; replaceIfExists và cách thay thế view phụ thuộc DBMS/phiên bản. runOnChange không có nghĩa mọi changeset cũ có thể chỉnh tùy tiện.

Nếu ID, author hoặc filename đổi, Liquibase có thể coi changeset là **identity mới**. runOnChange không tự nối identity mới với row cũ. runAlways cũng không bảo đảm khôi phục lịch sử khi path/author/id đã thay đổi; nó có thể khiến một changeset mới được thực thi theo cấu hình mới, làm tăng nguy cơ lặp DDL/DML.

## 15. Di chuyển tệp changelog sau khi đã triển khai: quy trình an toàn

Giả sử nhóm muốn tổ chức lại thư mục mà không làm changeset chạy lại.

~~~text
Trước:
db/changelog/changes/001-create-customer.yaml

Sau:
db/changelog/schema/customer/001-create-customer.yaml
~~~

Quy trình nên làm:

1. **Xác định các database đã nhận changeset.** Không chỉ kiểm tra local; cần biết development, test, staging và production đã chạy revision nào.
2. **Truy vấn FILENAME cũ.** Lấy đúng giá trị trong DATABASECHANGELOG từ ít nhất một database đã triển khai và đối chiếu giữa các môi trường.
3. **Xác định phạm vi file chứa changeset.** Nếu chỉ đổi master, child changelog có thể giữ identity; nếu di chuyển child, cần xử lý path logic.
4. **Kiểm tra logicalFilePath.** Xác nhận phiên bản/format hỗ trợ và cách giữ FILENAME cũ.
5. **Giữ nguyên id và author.** Không thay đồng thời nhiều thành phần identity.
6. **Thử trên clone database có lịch sử thật.** Chạy validate/status trước khi update; changeset cũ không được xuất hiện như một thay đổi mới ngoài dự kiến.
7. **Kiểm tra DATABASECHANGELOG.** Không tạo thêm row trùng mục đích với FILENAME mới.
8. **Chạy thử database mới.** Xác nhận database sạch vẫn có thể dựng schema theo cây changelog sau khi tái cấu trúc.
9. **Review pull request và release.** Lưu ý migration file move có thể ảnh hưởng nhiều môi trường.
10. **Promote cùng revision.** Không dùng các biến thể đường dẫn khác nhau giữa local và production.

Nếu không thể bảo toàn logical path hoặc không chắc phiên bản hỗ trợ, hãy cân nhắc **giữ tệp cũ tại vị trí cũ** và chỉ tạo changelog mới cho thay đổi tiếp theo. Một vài file cũ nằm lại trong thư mục lịch sử thường ít rủi ro hơn việc làm thay đổi identity đã phát hành.

## 16. Thay đổi author/id có chủ đích thì xử lý thế nào?

Sau khi changeset đã được áp dụng, thông thường không nên đổi id hoặc author. Nếu vì lý do tổ chức bắt buộc phải di chuyển quyền sở hữu, hãy cân nhắc:

- Giữ nguyên author/id cũ trong changeset lịch sử; dùng comment hoặc tài liệu PR để ghi nhận nhóm hiện tại chịu trách nhiệm.
- Nếu cần sửa cấu trúc, tạo changeset mới với author/id mới và nêu rõ mục đích.
- Không copy nguyên changeset cũ thành một changeset mới có nội dung giống hệt để “đổi tên”.
- Không xóa row lịch sử cũ nhằm nhường chỗ cho row mới.
- Không chạy changelog-sync để ép changeset mới thành đã áp dụng nếu chưa có bằng chứng schema/data tương ứng.
- Nếu có một quy trình quản trị định danh đặc biệt, cần thử trên clone tất cả trạng thái lịch sử và được phê duyệt rõ ràng.

**Tác giả cũ là một phần của lịch sử.** Người tiếp quản có thể được ghi nhận trong Git, review hoặc release record, không cần sửa author đã triển khai.

## 17. Include/includeAll và đường dẫn định danh

Một master changelog có thể nạp tệp con bằng include:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
~~~

Hoặc dùng includeAll để nạp nhiều tệp trong thư mục. Các cách tổ chức này ảnh hưởng việc Liquibase tìm resource và xác định đường dẫn changelog hiệu lực.

Cần nhớ:

- Đổi **thứ tự include** không tự đổi id/author/filename của changeset.
- Đổi đường dẫn hoặc tên chính tệp chứa changeset có thể đổi FILENAME logic.
- Đổi vị trí master không nhất thiết đồng nghĩa mọi changeset con đổi identity.
- includeAll có thể làm việc thêm file mới thay đổi tập changeset được nạp, nhưng không tự sửa identity của các file con còn nguyên đường dẫn.
- Relative path được giải quyết theo cấu hình và vị trí parent; không dựa vào working directory để suy đoán FILENAME.
- Một số khác biệt resource path giữa classpath/JAR và filesystem cần được thử với cùng phiên bản Liquibase.

Khi tổ chức thư mục, phải tách câu hỏi **“Liquibase có tìm thấy tệp không?”** khỏi câu hỏi **“Liquibase nhận diện changeset trong tệp đó là changeset nào?”**. Một file có thể được tìm thấy thành công nhưng vẫn bị coi là identity mới.

## 18. Chẩn đoán qua status, validate và DATABASECHANGELOG

Khi đổi id/author/path hoặc nghi ngờ checksum, dùng một chuỗi kiểm tra có thứ tự.

~~~text
Đọc revision changelog đã triển khai
              |
              v
Truy vấn DATABASECHANGELOG
(id, author, filename, md5sum, exectype)
              |
              v
So sánh bộ ba identity hiện tại
              |
       +------+------+
       |             |
     Khác           Giống
       |             |
       v             v
Có thể bị nhận     So sánh checksum
diện là mới             |
       |          +-----+-----+
       |          |           |
       |        Khớp       Không khớp
       |          |           |
       v          v           v
Không update   Đã ghi nhận   Điều tra checksum
mù quáng       bình thường   validation
~~~

Các lệnh minh họa theo CLI:

~~~text
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Tên lệnh và option có thể khác giữa phiên bản Liquibase, Maven plugin, Gradle plugin và CLI. Các lệnh phải dùng đúng URL/database/schema, master changelog, context/label và revision dự kiến.

- **validate** kiểm tra cấu trúc changelog và một số vấn đề tham chiếu; không chứng minh identity khớp lịch sử ở mọi database.
- **status** giúp xem changeset pending theo database và bộ lọc hiện tại; nếu một changeset mới xuất hiện sau khi đổi identity, cần dừng để điều tra.
- **update-sql** giúp review SQL dự kiến; không thay thế kiểm thử thực thi.
- **DATABASECHANGELOG** là nơi đối chiếu chính xác identity và checksum đã ghi nhận.

Nếu thấy changeset tạo bảng cũ xuất hiện lại trong status sau một lần rename file, không chạy update chỉ để xem có lỗi không. Trước hết xác định FILENAME và giải pháp bảo toàn identity.

## 19. Những sai lầm dễ gặp khi xử lý lịch sử

| Triệu chứng/ý định | Cách làm sai thường gặp | Cách tiếp cận đúng |
|---|---|---|
| Muốn đổi tên changeset | Đổi id đã phát hành | Giữ id cũ; dùng comment/tài liệu hoặc changeset mới cho thay đổi mới |
| Muốn chuẩn hóa author | Thay author toàn bộ lịch sử | Giữ author cũ, ghi nhận ownership hiện tại trong Git/PR |
| Muốn dọn thư mục | Di chuyển file đã chạy mà không giữ logical path | Đối chiếu FILENAME, kiểm tra logicalFilePath và thử trên clone |
| Gặp pending sau rename | Chạy update để kiểm tra | Dừng, xác định identity và SQL có thể chạy lại |
| Gặp checksum mismatch | Xóa MD5SUM ngay | So sánh nội dung revision và tìm thay đổi ngoài ý muốn |
| Muốn bỏ qua checksum | validCheckSum: ANY | Chấp nhận checksum cụ thể khi có căn cứ và review |
| Muốn tính lại mọi checksum | clearCheckSums không đánh giá | Chỉ dùng theo kế hoạch có kiểm soát; nó không sửa identity |
| Muốn chạy lại changeset cũ | Đổi id để đánh lừa lịch sử | Tạo changeset sửa tiếp hoặc thiết kế runOnChange đúng mục đích |
| Muốn đánh dấu changeset mới là đã chạy | changelog-sync trên production thiếu kiểm tra | Chỉ baseline sau khi đối chiếu toàn bộ schema/dữ liệu và được phê duyệt |
| Muốn xóa dấu vết row cũ | Sửa trực tiếp DATABASECHANGELOG | Giữ lịch sử; dùng quy trình Liquibase được hỗ trợ |

Những cách làm sai thường có điểm chung: **làm cho Liquibase mất khả năng phân biệt thay đổi đã triển khai và thay đổi mới**. Điều này đặc biệt nguy hiểm với insert dữ liệu tham chiếu, tạo bảng, add constraint và các thao tác không idempotent.

## 20. Database mới và database đã triển khai có thể phản ứng khác nhau

Khi tổ chức lại changelog, phải thử hai trạng thái.

| Trạng thái | Chuyện có thể xảy ra nếu identity bị đổi |
|---|---|
| Database đã triển khai | Có row lịch sử với bộ ba cũ; changeset ở đường dẫn/id/author mới có thể được xem là pending và chạy lại |
| Database mới | Chỉ thấy changeset theo revision hiện tại; nó có thể chạy một lần và tạo schema mới |
| Database được baseline bằng MARK_RAN | Row có thể mang EXECTYPE=MARK_RAN; đổi identity có thể khiến changeset mới được chạy, dù đối tượng đã tồn tại |
| Database chưa triển khai changeset đó | Không có row lịch sử cũ; đổi tên trước release có thể ít rủi ro hơn, nhưng vẫn phải kiểm tra tất cả môi trường |

Ví dụ một database production đã chạy `001-create-customer` tại FILENAME cũ. Developer di chuyển file và đổi author. Production có thể xem changeset mới là pending. Database development vừa được tạo từ revision mới chỉ chạy changeset đó một lần và có vẻ bình thường. Hai môi trường sau đó có **cách ghi nhận lịch sử khác nhau**, mặc dù tên bảng customer tồn tại ở cả hai.

Đây là lý do cần test với clone database có lịch sử thực tế, không chỉ test database sạch.

## 21. Quy ước đặt id, author và đường dẫn bền vững

Một quy ước hữu ích:

**id:** tên mô tả thay đổi, duy nhất trong phạm vi phù hợp; có thể kết hợp số thứ tự/ngày và hành động. Không tái sử dụng id đã phát hành.

**author:** tên nhóm hoặc định danh ổn định theo chính sách dự án. Tránh thay đổi theo người luân phiên trực tiếp quản lý migration.

**filename:** cấu trúc thư mục ổn định, rõ domain hoặc release. Không đặt tệp cũ trong một thư mục tạm sẽ bị xóa sau khi merge.

Ví dụ:

~~~text
db/changelog/
  db.changelog-master.yaml
  changes/
    customer/
      2026-001-create-customer.yaml
      2026-002-add-customer-status.yaml
    order/
      2026-003-create-order.yaml
~~~

Cấu trúc này chỉ là gợi ý; điều quan trọng là **không đổi identity sau khi phát hành**. Có thể cải thiện quy ước cho các changeset tương lai, nhưng không áp dụng rename hàng loạt lên lịch sử đã triển khai.

## 22. Chính sách pull request khi có file move hoặc rename

Một pull request chỉ di chuyển file changelog cần được review như thay đổi ảnh hưởng lịch sử, không chỉ là refactor thư mục.

Reviewer nên yêu cầu:

- Danh sách changeset trong các file được di chuyển.
- Bằng chứng FILENAME hiện tại ở database đã triển khai.
- Cách bảo toàn logicalFilePath nếu phiên bản hỗ trợ.
- So sánh status trước/sau trên database có lịch sử.
- Xác nhận không xuất hiện changeset cũ dưới identity mới.
- SQL preview không có DDL/DML cũ bất ngờ.
- Kiểm tra database mới vẫn có thể khởi tạo từ đầu.
- Ghim phiên bản Liquibase và đường chạy CLI/Spring Boot/CI.
- Kế hoạch rollback cho chính lần tái cấu trúc nếu nó làm thay đổi nhận diện.

Có thể đánh dấu file move là **history-sensitive change** trong pull request template để buộc reviewer kiểm tra. Không cần sửa changeset đã triển khai chỉ vì IDE hoặc công cụ format đề xuất đổi tên.

## 23. Liên hệ với Spring Boot và CI/CD

Spring Boot có thể đọc master changelog từ classpath:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Nếu đổi đường dẫn file nhưng không đóng gói resource mới đúng cách, ứng dụng có thể không tìm thấy changelog. Nếu tìm thấy nhưng FILENAME logic thay đổi, nó có thể nhận diện changeset là mới. Đây là hai lỗi khác nhau:

1. **Resource not found:** lỗi tìm kiếm/đóng gói tệp.
2. **Changeset identity changed:** tệp được đọc thành công nhưng bộ ba định danh không khớp DATABASECHANGELOG.

CI/CD nên chạy cùng artifact/revision đã được review, không tạo các biến thể path tùy runner. Pipeline có thể kiểm tra:

1. Ghim phiên bản Liquibase và JDBC driver.
2. Kiểm tra changelog có mặt trong artifact/classpath.
3. Chạy validate và status trên database đại diện.
4. Đối chiếu các row ID/AUTHOR/FILENAME với revision đã phát hành.
5. Kiểm tra không có changeset cũ bất ngờ xuất hiện pending sau rename.
6. Sinh updateSQL và review mọi thao tác DDL/DML.
7. Thử trên database mới và clone database có lịch sử cũ.
8. Chỉ promote cùng revision qua staging/production.
9. Lưu commit SHA, artifact, log migration và kết quả kiểm chứng.

Không để Spring Boot nhiều replica tự chạy các revision khác nhau trong lúc một pipeline đang tái cấu trúc đường dẫn changelog. DATABASECHANGELOGLOCK có thể điều phối các tiến trình Liquibase cùng bảng khóa, nhưng không sửa lỗi identity hoặc giải quyết khác biệt artifact.

## 24. Bài thực hành: nhận biết ba loại thay đổi

Thực hiện trên **database disposable**, không dùng production.

### Bước 1 — Tạo changeset ban đầu

Tệp `db/changelog/001-create-customer.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      changes:
        - createTable:
            tableName: lab_customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Chạy update. Sau đó truy vấn DATABASECHANGELOG, ghi lại ID, AUTHOR, FILENAME và MD5SUM.

### Bước 2 — Chỉ đổi nội dung

Giữ nguyên id, author và filename; thay đổi một phần change theo cách được Liquibase tính vào checksum. Chạy validate/update trên bản sao có lịch sử. Quan sát lỗi checksum validation nếu thay đổi đó thuộc phần nội dung checksum theo phiên bản.

Khôi phục revision cũ hoặc tạo database disposable mới trước bước tiếp theo; không dùng clearCheckSums để che kết quả thực hành.

### Bước 3 — Chỉ đổi id

Giữ nguyên author, filename và SQL, đổi id thành `001-create-lab-customer`. Chạy status trên database đã chạy bước 1. Quan sát changeset mới có thể xuất hiện pending do identity khác. **Không chạy update**, vì nó có thể cố tạo lại bảng lab_customer.

### Bước 4 — Khôi phục id, đổi author

Giữ id ban đầu, đổi author từ schema-team sang lab-team. Chạy status và quan sát lại khả năng được xem là changeset mới. Tiếp tục không update trên database có bảng đã tạo.

### Bước 5 — Khôi phục identity, di chuyển file

Đổi tên/di chuyển tệp sang thư mục khác, giữ id/author. So sánh FILENAME lịch sử và status hiện tại. Thử cách giữ logicalFilePath theo tài liệu phiên bản đang dùng trên một bản sao database. Xác nhận changeset cũ không xuất hiện thành pending chỉ vì path mới.

### Bước 6 — So sánh database sạch

Tạo một database mới, chạy changelog ở revision hiện tại và ghi lại row lịch sử. So sánh với database đã triển khai từ trước. Bài học cần rút ra: database sạch có thể chạy revision mới bình thường, trong khi database cũ lại xem changeset đã đổi identity là mới.

## 25. Checklist trước khi thay đổi id, author hoặc path

- [ ] Đã xác định changeset đã được áp dụng ở những database/môi trường nào.
- [ ] Đã truy vấn đủ ID, AUTHOR, FILENAME và MD5SUM từ DATABASECHANGELOG.
- [ ] Đã phân biệt sự cố identity với checksum mismatch.
- [ ] Không đổi id đã phát hành chỉ để cải thiện tên.
- [ ] Không đổi author đã phát hành chỉ để chuyển quyền sở hữu.
- [ ] Không di chuyển tệp chứa changeset mà chưa đánh giá FILENAME.
- [ ] Nếu cần di chuyển, đã xác nhận logicalFilePath được hỗ trợ và giữ đúng giá trị lịch sử.
- [ ] Đã kiểm tra path normalization, chữ hoa/chữ thường, separator và classpath.
- [ ] Đã giữ nguyên các thành phần identity không cần thay đổi.
- [ ] Không dùng validCheckSum hoặc clearCheckSums để xử lý lỗi identity.
- [ ] Không dùng runOnChange/runAlways như công cụ sửa id/author/path.
- [ ] Không sửa trực tiếp DATABASECHANGELOG.
- [ ] Đã chạy validate/status trên database có lịch sử cũ.
- [ ] Không update nếu changeset cũ bất ngờ xuất hiện pending.
- [ ] Đã review updateSQL để phát hiện DDL/DML có thể chạy lại.
- [ ] Đã thử cả database sạch và database clone đã triển khai.
- [ ] CI/CD và Spring Boot dùng cùng revision, artifact và cấu hình đường dẫn.
- [ ] Pull request có người review hiểu tác động tới lịch sử migration.
- [ ] Nếu thay đổi đã phát hành cần sửa chức năng, tạo changeset mới có định danh mới và mục đích rõ.
- [ ] Lưu bằng chứng và quyết định trong release record.

**Ghi nhớ:** Liquibase nhận diện changeset bằng **id + author + filename**, còn **checksum** kiểm tra nội dung theo quy tắc của phiên bản công cụ. Đổi id hoặc author, hay di chuyển tệp làm thay đổi filename logic, có thể khiến changeset cũ bị xem là mới và chạy lại. Khi cần tái cấu trúc đường dẫn, hãy đối chiếu FILENAME thực tế và dùng logicalFilePath nếu được hỗ trợ; khi cần thay đổi schema/dữ liệu, hãy tạo changeset mới. Giữ định danh lịch sử ổn định là điều kiện quan trọng để changelog có thể tái lập an toàn qua mọi môi trường.

