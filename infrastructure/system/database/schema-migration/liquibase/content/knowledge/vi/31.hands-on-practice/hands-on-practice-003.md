# Nạp dữ liệu tham chiếu và kiểm tra chạy lại an toàn

Nhiều ứng dụng cần một tập dữ liệu nhỏ, ổn định để hoạt động đúng: mã quốc gia, loại tiền tệ, trạng thái đơn hàng, nhóm quyền, loại tài liệu hoặc danh mục cấu hình. Đây là **dữ liệu tham chiếu**. Nó thường được triển khai cùng schema vì ứng dụng cần các mã và quan hệ đó ngay sau khi database được khởi tạo hoặc nâng cấp.

Liquibase hỗ trợ nạp dữ liệu từ CSV bằng `loadData` và đồng bộ theo khóa chính bằng `loadUpdateData`. Tuy nhiên, việc một changeset đã được ghi nhận trong DATABASECHANGELOG không đồng nghĩa câu lệnh nạp dữ liệu có thể chạy lại tùy ý. Cần phân biệt tính an toàn của lệnh `update` ở cấp changeset với tính idempotent của thao tác ghi dữ liệu. Nếu dùng sai `runAlways`, `runOnChange`, khóa định danh hoặc rollback, dữ liệu tham chiếu có thể bị trùng, ghi đè hoặc mất.

Bài thuộc chương **Thực hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này hướng dẫn thiết kế bộ CSV tham chiếu, lựa chọn `loadData` hay `loadUpdateData`, tổ chức changeset bất biến, xác minh dữ liệu và kiểm tra các lần chạy lại trên database mới lẫn database đã có lịch sử.

## 1. Dữ liệu tham chiếu là gì?

Dữ liệu tham chiếu mô tả tập mã hoặc danh mục được nhiều phần của ứng dụng dùng chung. Nó thường thay đổi ít hơn dữ liệu giao dịch.

Ví dụ:

| Nhóm | Ví dụ | Đặc điểm |
|---|---|---|
| Quốc gia | VN, JP, US | Mã ổn định, tên hiển thị có thể cập nhật |
| Tiền tệ | VND, USD, EUR | Mã ISO, số chữ số thập phân |
| Trạng thái | PENDING, APPROVED, REJECTED | Ứng dụng phụ thuộc mã |
| Loại tài liệu | PASSPORT, INVOICE | Danh mục dùng cho validation |
| Nhóm quyền | ADMIN, AUDITOR, SUPPORT | Có thể liên kết tới role/permission |
| Phương thức vận chuyển | AIR, SEA, ROAD | Danh mục dùng cho nghiệp vụ |

Dữ liệu tham chiếu thường có các đặc điểm:

- Số lượng nhỏ hoặc vừa, có thể đóng gói trong source control.
- Có khóa ổn định như code hoặc mã nghiệp vụ.
- Được nhiều môi trường sử dụng cùng một định nghĩa.
- Cần có mặt trước khi ứng dụng xử lý dữ liệu giao dịch phụ thuộc.
- Có thể cần cập nhật mô tả hoặc thuộc tính theo release.
- Không nên bị ghi đè bởi dữ liệu người dùng ngoài ý muốn.

Không phải mọi bảng ít thay đổi đều là dữ liệu tham chiếu. Dữ liệu do người dùng tạo, dữ liệu giao dịch, cấu hình riêng từng khách hàng và dữ liệu được đồng bộ từ hệ thống bên ngoài thường cần vòng đời riêng. Không đưa toàn bộ dữ liệu production vào CSV migration.

## 2. Chọn loadData hay loadUpdateData

Hai change type đều đọc CSV nhưng có mục tiêu khác nhau.

| Change type | Hành vi khái quát | Khi phù hợp |
|---|---|---|
| `loadData` | Nạp các dòng từ CSV vào bảng | Seed dữ liệu ban đầu hoặc một tập dữ liệu chỉ cần chèn một lần |
| `loadUpdateData` | Dùng khóa chính để cập nhật dòng đã có và chèn dòng chưa có | Đồng bộ một tập dữ liệu tham chiếu có thể cần cập nhật giá trị theo release |

Với `loadUpdateData`, khai báo khóa chính hoặc khóa định danh tương ứng là thiết yếu. Giá trị khóa trong CSV phải xác định duy nhất dòng đích. Nếu khóa trùng trong CSV, hoặc không khớp với mô hình khóa của bảng, kết quả có thể lỗi hoặc không đáp ứng ý định.

Cả hai change type vẫn nằm trong changeset và được quản lý bởi lịch sử Liquibase. Trong lần `update` thông thường, changeset đã được ghi nhận sẽ không tự chạy lại chỉ vì CSV đã thay đổi trên filesystem.

**Không chọn `loadUpdateData` chỉ vì tên có chữ Update.** Nếu dữ liệu là một lần seed bất biến và không có ý định đồng bộ lại, `loadData` với changeset một lần có thể rõ ràng hơn. Nếu cần cập nhật bản ghi đã tồn tại theo khóa ổn định, `loadUpdateData` thường phù hợp hơn.

## 3. Thiết kế bảng tham chiếu trước khi tạo CSV

Ví dụ bảng country:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-country
      author: database-team
      changes:
        - createTable:
            tableName: country
            columns:
              - column:
                  name: code
                  type: VARCHAR(3)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: true
                  constraints:
                    nullable: false
~~~

Khóa chính `code` là mã quốc gia ổn định. Tên hiển thị có thể được cập nhật mà không thay đổi định danh. Cột `active` biểu diễn trạng thái sử dụng; việc ngừng sử dụng mã thường an toàn hơn xóa hẳn nếu các bảng giao dịch đang tham chiếu.

Trước khi nạp dữ liệu, xác định:

- Khóa chính hoặc khóa tự nhiên nào nhận diện một dòng.
- Giá trị khóa có duy nhất và ổn định qua các release không.
- Cột nào do migration quản lý và cột nào do người dùng quản lý.
- Có cho phép NULL hay không.
- Default nào được áp dụng khi CSV thiếu cột hoặc giá trị.
- Có foreign key từ bảng nghiệp vụ tới bảng tham chiếu không.
- Cách ngừng sử dụng một mã đã được tham chiếu.

Không dùng tên hiển thị làm khóa nếu tên có thể đổi hoặc trùng. Ưu tiên mã nghiệp vụ ổn định.

## 4. Tổ chức CSV và đường dẫn tài nguyên

Một cấu trúc dễ quản lý:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-country.yaml
        002-load-country-reference.yaml
        003-update-country-names.yaml
      data/
        countries-v1.csv
        countries-v2.csv
~~~

Changelog con có thể tham chiếu CSV tương đối với chính nó:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-load-country-reference
      author: database-team
      changes:
        - loadData:
            file: ../data/countries-v1.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8
            separator: ","
            quotchar: '"'
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
~~~

Nếu file changeset nằm trong `db/changelog/changes`, đường dẫn `../data/countries-v1.csv` trỏ tới `db/changelog/data/countries-v1.csv`.

Dùng `relativeToChangelogFile: true` giúp đường dẫn không phụ thuộc thư mục hiện hành của shell. Khi chạy từ IDE, CLI, executable JAR hoặc container, phải bảo đảm CSV được đóng gói cùng changelog. Tên file và thư mục cần đúng chữ hoa/thường, nhất là khi build trên Windows nhưng chạy trên Linux.

## 5. Định nghĩa header và ánh xạ cột

CSV ví dụ:

~~~csv
code,name,active
VN,Viet Nam,true
JP,Japan,true
US,United States,true
~~~

Trong khai báo `columns`:

- `header` là tên cột trong dòng tiêu đề CSV.
- `name` là tên cột đích trong database.
- `type` chỉ định kiểu dữ liệu Liquibase dùng khi đọc giá trị.

Có thể ánh xạ header khác tên cột database. Ví dụ CSV dùng `country_code` nhưng bảng dùng `code`; khi đó khai báo header và name tương ứng. Không dựa vào thứ tự cột nếu có thể khai báo header rõ ràng, vì việc đổi thứ tự CSV có thể gây nhầm dữ liệu.

Nếu bỏ qua cấu hình columns, Liquibase có thể suy ra mapping theo header trong những trường hợp hỗ trợ. Với migration quan trọng, khai báo tường minh giúp reviewer thấy dữ liệu đi vào cột nào.

## 6. Encoding, delimiter, quote và giá trị rỗng

CSV là định dạng đơn giản nhưng rất dễ sai khi dữ liệu có Unicode, dấu phẩy, dấu nháy hoặc xuống dòng.

Ví dụ:

~~~csv
code,name,active
VN,"Việt Nam",true
US,"United States, of America",true
JP,"Japan ""Nihon""",true
~~~

Các điểm cần thống nhất:

- **encoding:** dùng UTF-8 nhất quán cho source và runtime.
- **separator:** dấu phân tách cột, thường là dấu phẩy.
- **quotchar:** ký tự bao giá trị có separator hoặc ký tự đặc biệt.
- **header:** tên cột trong dòng đầu nếu file có tiêu đề.
- **newline:** thống nhất định dạng xuống dòng khi tạo CSV.
- **BOM:** tránh BOM ngoài ý muốn làm sai header đầu tiên.
- **giá trị rỗng/NULL:** xác định rõ cách biểu diễn và kiểm tra hành vi của Liquibase version đang dùng.

Không mặc định ô CSV trống luôn có cùng ý nghĩa trên mọi cấu hình. Chuỗi rỗng, NULL và giá trị không được cung cấp có thể khác nhau. Nếu cần biểu diễn NULL tường minh, dùng cơ chế placeholder được phiên bản Liquibase hỗ trợ hoặc thiết kế file/changeset riêng, sau đó kiểm tra dữ liệu thực tế bằng SQL.

Với dữ liệu tiếng Việt, kiểm tra cả byte UTF-8 và nội dung sau khi nạp. Một file nhìn đúng trong editor nhưng được build hoặc đọc bằng encoding khác có thể lưu ký tự sai.

## 7. Nạp dữ liệu lần đầu bằng loadData

Ví dụ changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-seed-country
      author: database-team
      changes:
        - loadData:
            file: ../data/countries-v1.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8
            separator: ","
            quotchar: '"'
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
~~~

Khi changeset được thực thi lần đầu, Liquibase đọc CSV và nạp các dòng vào bảng. Sau khi changeset được ghi nhận trong DATABASECHANGELOG, các lần `update` bình thường sẽ bỏ qua changeset đó.

Đây là cơ chế giúp seed data không bị chèn lại ở mỗi lần ứng dụng khởi động. Tuy nhiên, nó cũng có nghĩa là **sửa CSV cũ không tự động cập nhật dữ liệu trên database đã triển khai**. Nếu danh mục cần thay đổi, hãy tạo changeset mới với file dữ liệu phiên bản mới hoặc thao tác update có chủ đích.

Không đặt `runAlways: true` lên changeset `loadData` chỉ để CSV được đọc lại mỗi lần update. Khi chạy lặp, dữ liệu có thể bị chèn trùng hoặc vi phạm khóa chính.

## 8. Cập nhật và chèn theo khóa bằng loadUpdateData

Khi cần cập nhật dữ liệu tham chiếu hiện có theo mã ổn định, dùng `loadUpdateData`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-sync-country-reference
      author: database-team
      changes:
        - loadUpdateData:
            file: ../data/countries-v2.csv
            relativeToChangelogFile: true
            tableName: country
            primaryKey: code
            encoding: UTF-8
            separator: ","
            quotchar: '"'
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
~~~

Theo ngữ nghĩa của `loadUpdateData`, Liquibase dùng giá trị khóa đã khai báo để xác định dòng:

- Khóa đã tồn tại: cập nhật các giá trị được cung cấp trong dữ liệu nạp theo hành vi change type.
- Khóa chưa tồn tại: chèn dòng mới.
- Dòng đang có trong database nhưng không có trong CSV: không nên giả định sẽ bị xóa tự động.

Ví dụ CSV phiên bản mới:

~~~csv
code,name,active
VN,Viet Nam,true
JP,Japan,true
US,United States of America,true
SG,Singapore,true
~~~

Nếu bảng đã có VN, JP và US, changeset có thể cập nhật tên US và thêm SG. Các dòng khác không nằm trong file không nên được xem là đã bị xóa; muốn ngừng mã, hãy biểu diễn bằng một thay đổi tường minh như `active=false` nếu đó là quy tắc nghiệp vụ.

### 8.1. Khóa phải thực sự duy nhất

Nếu `primaryKey: code` nhưng bảng không có unique/primary-key constraint tương ứng, dữ liệu trùng có thể khiến việc xác định dòng cập nhật không rõ ràng hoặc gây lỗi. Khóa khai báo phải phản ánh một định danh duy nhất được database bảo vệ.

Với khóa ghép, xác minh cú pháp và khả năng hỗ trợ của Liquibase version đang dùng; không tự giả định một chuỗi tên cột phân tách bằng dấu phẩy hoạt động giống nhau ở mọi version. Kiểm thử trên DBMS thực tế.

## 9. Phân biệt idempotency của update và idempotency của dữ liệu

Đây là điểm quan trọng nhất khi nói về “chạy lại an toàn”.

**Ở cấp Liquibase:** `update` thông thường so sánh changeset với DATABASECHANGELOG. Changeset đã được ghi nhận sẽ không chạy lại như một changeset mới.

**Ở cấp dữ liệu:** nếu phần nạp dữ liệu được thực thi lại, kết quả có thể khác. `loadData` thường chèn dòng và có thể gặp duplicate key. `loadUpdateData` cập nhật/chèn theo khóa, phù hợp hơn cho một số quy trình đồng bộ có chủ đích, nhưng vẫn có thể ghi đè giá trị mà ứng dụng hoặc người vận hành đã sửa.

Ví dụ:

| Tình huống | loadData | loadUpdateData |
|---|---|---|
| Lần đầu, khóa chưa tồn tại | Chèn dòng | Chèn dòng |
| Thực thi lại cùng dữ liệu | Có thể trùng khóa | Có thể cập nhật lại theo khóa |
| Giá trị mô tả thay đổi trong CSV | Không tự chạy lại changeset đã hoàn tất | Không tự cập nhật nếu changeset không được thực thi lại |
| Dòng có trong DB nhưng vắng CSV | Không xóa | Không nên coi là bị xóa tự động |
| Người dùng đã sửa một trường | Lần chạy lại có thể xung đột | Có thể ghi đè trường được đồng bộ |

Không dùng từ “idempotent” mà không nói rõ cấp nào. Một lệnh update có thể không chạy lại changeset, trong khi thao tác dữ liệu bên trong changeset nếu bị thực thi lại vẫn có thể không an toàn.

## 10. runAlways và runOnChange có thể làm thay đổi hành vi

Hai thuộc tính này cần được hiểu trước khi gắn vào changeset nạp dữ liệu:

- `runAlways: true`: changeset được thực thi lại trong mỗi lần update phù hợp, theo hành vi Liquibase.
- `runOnChange: true`: changeset được chạy lại khi checksum của nội dung changeset thay đổi theo cơ chế Liquibase.

Nếu đặt `runAlways` trên `loadData`, mỗi lần update có thể cố nạp lại CSV và tạo duplicate. Nếu đặt trên `loadUpdateData`, dữ liệu từ CSV có thể được áp lại và ghi đè giá trị đã thay đổi ở database. Chỉ dùng khi đây là chính sách đồng bộ được thiết kế và kiểm thử.

Với `runOnChange`, không giả định việc sửa một CSV bên ngoài luôn làm changeset được nhận diện là thay đổi theo cách mong muốn. Cách tính checksum đối với resource ngoài và behavior cụ thể cần được xác minh trên Liquibase version đang dùng. Một chiến lược dễ truy vết là dùng file CSV bất biến theo phiên bản và tạo changeset mới cho mỗi đợt cập nhật dữ liệu.

Không chỉnh sửa changeset đã triển khai chỉ để buộc chạy lại. Điều đó có thể tạo checksum mismatch hoặc khác biệt lịch sử giữa môi trường.

## 11. Quản lý phiên bản CSV bất biến

Thay vì liên tục sửa `countries.csv`, dùng tên có version hoặc release:

~~~text
data/
  countries-v1.csv
  countries-v2.csv
  countries-v3.csv
~~~

Mỗi file gắn với changeset tương ứng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-load-country-v1
      author: database-team
      changes:
        - loadData:
            file: ../data/countries-v1.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8

  - changeSet:
      id: 020-update-country-v2
      author: database-team
      changes:
        - loadUpdateData:
            file: ../data/countries-v2.csv
            relativeToChangelogFile: true
            tableName: country
            primaryKey: code
            encoding: UTF-8
~~~

Ví dụ này minh họa việc giữ lại file cũ và tạo file mới. Trong dự án thực tế, khai báo columns, separator, quote và kiểu dữ liệu đầy đủ theo CSV.

Ưu điểm:

- Có thể truy vết chính xác dữ liệu của từng release.
- Không làm thay đổi đầu vào của changeset đã triển khai.
- Có thể so sánh diff giữa hai phiên bản danh mục.
- Dễ tái tạo fresh install.
- Dễ điều tra khác biệt giữa staging và production.

CSV đã phát hành nên được xem như một phần bất biến của artifact migration.

## 12. Không đồng bộ xóa bằng cách bỏ dòng khỏi CSV

Một hiểu lầm thường gặp là xóa một mã khỏi CSV mới sẽ làm Liquibase xóa dòng tương ứng khỏi database. `loadUpdateData` không nên được xem như một phép mirror toàn bảng tự động.

Nếu một mã không còn được sử dụng, cần quyết định:

- Có thể đánh dấu inactive không?
- Có bản ghi giao dịch đang tham chiếu không?
- Có foreign key ngăn xóa không?
- Ứng dụng cũ có còn gửi mã đó không?
- Có cần giữ lại để hiển thị lịch sử không?

Ví dụ changeset ngừng sử dụng một mã:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-deactivate-obsolete-country
      author: database-team
      changes:
        - update:
            tableName: country
            columns:
              - column:
                  name: active
                  valueBoolean: false
            where: code = 'XX'
~~~

Đây là thay đổi tường minh. Hãy xác minh mã XX có tồn tại và ý nghĩa inactive phù hợp với ứng dụng. Nếu cần xóa vật lý, thiết kế changeset riêng có precondition, kiểm tra dependency và rollback/backup.

## 13. Precondition trước khi nạp dữ liệu

Precondition giúp tránh nạp dữ liệu vào bảng chưa được tạo hoặc sai cấu trúc. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-load-country-v1
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: country
      changes:
        - loadData:
            file: ../data/countries-v1.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8
~~~

Precondition này xác nhận bảng tồn tại. Nó không chứng minh:

- Cột code có kiểu và constraint đúng.
- CSV không có khóa trùng.
- Dữ liệu đã tồn tại chưa.
- Foreign key từ các bảng khác sẽ hợp lệ.
- Mọi mã trong CSV phù hợp quy tắc nghiệp vụ.

Với dữ liệu quan trọng, có thể cần kiểm tra thêm cấu trúc và tính hợp lệ trước khi load. Nhưng tránh viết sqlCheck quét toàn bộ bảng nếu chỉ cần xác minh một invariant nhỏ. Đo chi phí trên dữ liệu đại diện và giữ điều kiện có ý nghĩa.

Không dùng `onFail: MARK_RAN` chỉ để bỏ qua seed data khi bảng chưa tồn tại hoặc dữ liệu không hợp lệ. Khi MARK_RAN, lịch sử có thể ghi nhận changeset đã chạy dù dữ liệu không được nạp. Điều đó dễ tạo lỗi khó phát hiện ở các changeset phụ thuộc.

## 14. Kiểm tra dữ liệu CSV trước khi triển khai

Trước khi đưa CSV vào changelog, kiểm tra:

1. Header có đủ cột bắt buộc.
2. Không có khóa chính rỗng.
3. Không có khóa trùng.
4. Kiểu dữ liệu đúng với schema.
5. Giá trị Boolean/Date/Number theo định dạng được Liquibase/DBMS hỗ trợ.
6. Chuỗi có dấu phẩy, quote và Unicode được escape đúng.
7. Giá trị NULL/rỗng có quy ước rõ.
8. Độ dài không vượt giới hạn cột.
9. Foreign key tham chiếu tới mã đã tồn tại.
10. Không có dòng trùng hoặc mâu thuẫn về ý nghĩa nghiệp vụ.

Ví dụ các lỗi dữ liệu:

~~~csv
code,name,active
VN,Viet Nam,true
VN,Vietnam,true
,Unknown,true
JP,Japan,yes
~~~

File trên có mã VN lặp, một khóa rỗng và giá trị Boolean không theo quy ước đã chọn. Không nên chờ tới lúc update production mới phát hiện. Hãy kiểm tra CSV trong bước review/build và vẫn xác minh lại trên database test.

## 15. Kiểm tra sau khi nạp bằng SQL assertion

Sau migration, xác minh cả số lượng lẫn nội dung.

Kiểm tra các mã bắt buộc:

~~~sql
SELECT code, name, active
FROM country
WHERE code IN ('VN', 'JP', 'US')
ORDER BY code;
~~~

Kiểm tra số lượng mã duy nhất:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT code) AS distinct_codes
FROM country;
~~~

Kiểm tra khóa rỗng:

~~~sql
SELECT COUNT(*)
FROM country
WHERE code IS NULL OR code = '';
~~~

Kiểm tra dữ liệu tham chiếu bị thiếu:

~~~sql
SELECT DISTINCT o.country_code
FROM customer_order o
LEFT JOIN country c ON c.code = o.country_code
WHERE o.country_code IS NOT NULL
  AND c.code IS NULL;
~~~

Các truy vấn cần điều chỉnh theo DBMS, schema và quy tắc nghiệp vụ. COUNT tổng không đủ chứng minh dữ liệu đúng; cần so sánh các mã và giá trị cụ thể. Với danh mục lớn, có thể dùng tập mã mong đợi hoặc hash được quản lý để phát hiện sai lệch, nhưng vẫn phải có cách điều tra từng dòng.

## 16. Kiểm tra chạy lại an toàn ở cấp changeset

Một kịch bản test nên phân biệt các trường hợp:

### Lần chạy đầu trên database sạch

- Tạo schema và bảng tham chiếu.
- Chạy `update`.
- Xác nhận số dòng và giá trị.
- Xác nhận changeset load data có trong DATABASECHANGELOG.

### Chạy update lần thứ hai

- Chạy cùng artifact và cùng database.
- Xác nhận changeset đã hoàn tất không bị thực thi lại trong update thông thường.
- Xác nhận không có dòng trùng hoặc thay đổi ngoài dự kiến.
- Đối chiếu DATABASECHANGELOG.

### Nâng cấp CSV ở release mới

- Tạo changeset mới và file CSV version mới.
- Chạy update.
- Xác nhận mã mới được chèn và thuộc tính được cập nhật theo mục tiêu.
- Xác nhận dữ liệu người dùng không bị ghi đè ngoài phạm vi.
- Xác nhận mã vắng trong CSV không bị xóa tự động.

### Thử thực thi lặp có chủ đích

Nếu thiết kế dùng `runAlways` hoặc một quy trình gọi lại loadUpdateData, hãy chạy test riêng để chứng minh:

- Khóa định danh không tạo duplicate.
- Giá trị được cập nhật đúng.
- Trường không nằm trong CSV có hành vi đúng như mong muốn.
- Dữ liệu do người dùng quản lý không bị ghi đè.
- Retry sau lỗi không để lại trạng thái nửa hoàn tất.

Không mô phỏng “chạy lại” bằng cách xóa DATABASECHANGELOG trên một database đã có schema. Điều đó phá vỡ quan hệ giữa history và trạng thái thật.

## 17. DATABASECHANGELOG và dấu vết nạp dữ liệu

Liquibase ghi nhận changeset trong DATABASECHANGELOG. Có thể kiểm tra:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
WHERE id IN (
    '010-load-country-v1',
    '020-update-country-v2'
)
ORDER BY orderexecuted;
~~~

Cần xác minh:

- Đúng ID và author.
- Đúng filename/logical path.
- EXECTYPE phù hợp với lần chạy.
- Checksum không bị thay đổi ngoài chủ đích.
- Thời điểm và thứ tự phù hợp release.

Bản ghi history chứng minh Liquibase đã ghi nhận changeset theo cơ chế của nó; nó không chứng minh mọi dòng CSV đã được nạp đúng. Hãy kết hợp history với SQL assertion trên bảng dữ liệu.

Nếu changeset bị MARK_RAN, dữ liệu có thể chưa được nạp. Nếu changeset thất bại giữa chừng, history có thể chưa ghi nhận hoàn tất nhưng database có thể đã có một phần dữ liệu tùy transaction/DBMS. Điều tra cả hai phía trước khi retry.

## 18. Rollback dữ liệu tham chiếu

Rollback dữ liệu cần thận trọng hơn rollback một bảng mới tạo. Mã tham chiếu có thể đã được giao dịch hoặc bảng khác sử dụng sau khi migration chạy.

Trước khi rollback, xác định:

- Dòng nào do changeset tạo.
- Dòng nào đã tồn tại trước migration.
- Dòng nào được changeset cập nhật.
- Có foreign key hoặc dữ liệu giao dịch đang tham chiếu không.
- Có thay đổi thủ công sau deploy không.
- Có thể phục hồi giá trị cũ chính xác không.

Không xóa toàn bộ bảng country để rollback một CSV nếu bảng đã chứa dữ liệu được tạo sau đó.

Với dữ liệu seed mới và chưa có consumer, có thể viết rollback xóa đúng tập mã do changeset tạo, nhưng phải kiểm tra dependency. Với changeset cập nhật tên hoặc trạng thái của dòng đã tồn tại, rollback cần biết giá trị cũ; nếu không lưu lại, không thể khôi phục chính xác chỉ từ CSV mới.

Có trường hợp forward-fix an toàn hơn rollback, ví dụ sửa lại một tên hiển thị sai bằng changeset mới. Hãy thử rollback trên database có dữ liệu đại diện trước khi áp dụng trong môi trường quan trọng.

## 19. Thứ tự triển khai và foreign key

Nếu dữ liệu tham chiếu được bảng nghiệp vụ tham chiếu bằng foreign key, phải nạp bảng cha trước khi nạp dữ liệu con.

Ví dụ:

~~~text
country
  |
  +-- customer
        |
        +-- customer_address
~~~

Thứ tự hợp lý:

1. Tạo bảng country.
2. Nạp mã country.
3. Tạo bảng customer và foreign key nếu dependency yêu cầu.
4. Nạp dữ liệu customer.
5. Nạp customer_address tham chiếu customer.

Nếu thêm foreign key sau khi đã có dữ liệu, kiểm tra mọi giá trị tham chiếu trước khi bật constraint. Không dùng precondition để bỏ qua FK chỉ vì một môi trường có dữ liệu thiếu; cần xác định cách làm sạch hoặc ánh xạ dữ liệu.

## 20. Dữ liệu tham chiếu theo môi trường

Một số dữ liệu có thể giống nhau ở mọi môi trường; một số khác là dữ liệu riêng:

- Mã quốc gia, tiền tệ, loại trạng thái: thường dùng chung.
- Tài khoản service test: chỉ dùng trong test.
- URL endpoint, secret, API key: không nên đóng gói thành CSV tham chiếu chung.
- ID tenant hoặc cấu hình khách hàng: có thể khác theo môi trường/khách hàng.
- Dữ liệu demo: chỉ nạp theo context phù hợp.

Có thể dùng context/label để tách dữ liệu chỉ dành cho dev/test:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 090-load-demo-categories
      author: database-team
      context: dev
      changes:
        - loadData:
            file: ../data/demo-categories.csv
            relativeToChangelogFile: true
            tableName: category
            encoding: UTF-8
~~~

Không để dữ liệu demo chạy ở production do pipeline truyền nhầm context. Kiểm tra effective context/label và DATABASECHANGELOG ở từng môi trường.

## 21. Kiểm thử với Testcontainers

Testcontainers giúp chạy changeset trên đúng DBMS, kiểm tra CSV encoding, kiểu dữ liệu, unique key và hành vi transaction.

Một bộ test nên có:

- Database mới hoàn toàn.
- Database đã có một phần mã tham chiếu.
- Dòng có khóa trùng.
- CSV có Unicode và quote.
- CSV có giá trị rỗng/NULL theo quy ước.
- Foreign key tham chiếu mã chưa tồn tại.
- Lần update thứ hai.
- Release mới dùng CSV version mới.
- Retry sau lỗi.
- Rollback hoặc forward-fix trên dữ liệu có consumer.

Với PostgreSQL, test có thể dùng PostgreSQLContainer và Spring Boot DynamicPropertySource để cấu hình datasource. Assertion nên kiểm tra cả row values, unique constraints và DATABASECHANGELOG.

Không chỉ kiểm tra test chạy xanh trên H2. Kiểu dữ liệu Boolean, collation, constraint, SQL và driver behavior có thể khác DBMS production.

## 22. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Duplicate key khi loadData | CSV trùng khóa hoặc changeset bị thực thi lại | Kiểm tra khóa và history; không bật runAlways tùy tiện |
| loadUpdateData không cập nhật dòng mong đợi | primaryKey/header mapping sai | Đối chiếu giá trị khóa và mapping |
| Dữ liệu CSV thay đổi nhưng DB không đổi | Changeset đã được ghi nhận, update không chạy lại | Tạo changeset mới với file version mới |
| Dòng cũ không bị xóa | loadUpdateData không phải mirror/delete sync | Tạo changeset deactivate/delete tường minh nếu hợp lệ |
| Unicode bị lỗi | Encoding/BOM không đúng | Chuẩn hóa UTF-8 và test artifact |
| Giá trị rỗng thành NULL hoặc chuỗi rỗng ngoài ý muốn | Chưa xác định semantics CSV | Dùng quy ước rõ và assertion trên DBMS thật |
| FK violation | Nạp dữ liệu con trước bảng tham chiếu | Sắp xếp changeset và kiểm tra khóa |
| Unique violation | Dữ liệu CSV hoặc database có mã trùng | Làm sạch và kiểm tra trước load |
| Retry báo object/data đã tồn tại | Lần trước đã commit một phần | Kiểm tra schema/data/history trước retry |
| Rollback xóa dữ liệu đang được dùng | Xóa cả dòng seed đã phát sinh consumer | Thiết kế rollback có điều kiện hoặc forward-fix |
| Production có dữ liệu khác test | CSV ghi đè trường ngoài dự kiến | Phân quyền sở hữu cột và test upgrade trên dữ liệu đại diện |

## 23. Bài thực hành: nạp danh mục quốc gia an toàn

Dùng database lab hoặc Testcontainers. Không dùng production.

### Bước 1 — Tạo bảng

Tạo bảng country với code làm primary key, name và active. Xác minh constraint trong DBMS.

### Bước 2 — Tạo CSV v1

Tạo countries-v1.csv gồm VN, JP và US. Dùng UTF-8, header rõ và mã duy nhất.

### Bước 3 — Nạp bằng loadData

Tạo changeset 010-load-country-v1 với relativeToChangelogFile=true, encoding UTF-8 và mapping cột tường minh. Chạy update.

### Bước 4 — Xác minh dữ liệu

Truy vấn từng mã, so sánh tên và active. Kiểm tra số dòng và distinct code. Kiểm tra DATABASECHANGELOG.

### Bước 5 — Chạy update lần hai

Chạy cùng artifact lần nữa. Xác nhận changeset 010 không chạy lại trong update thông thường và không phát sinh duplicate.

### Bước 6 — Tạo CSV v2 và changeset mới

Tạo countries-v2.csv có tên US được cập nhật và mã SG mới. Dùng loadUpdateData với primaryKey: code trong changeset 020.

### Bước 7 — Kiểm tra cập nhật và chèn

Xác nhận US được cập nhật, SG được thêm, VN/JP giữ đúng giá trị. Thêm một mã chỉ có trong database và chứng minh nó không tự bị xóa vì vắng trong CSV.

### Bước 8 — Mô phỏng dữ liệu lỗi

Tạo CSV có code trùng hoặc giá trị sai kiểu. Chạy trên database lab, ghi nhận lỗi, kiểm tra history và dữ liệu sau thất bại. Khôi phục fixture và chạy lại sau khi sửa.

### Bước 9 — Kiểm tra rollback

Xem SQL rollback hoặc cơ chế rollback tương ứng phiên bản Liquibase. Thử trên database lab có dữ liệu tham chiếu đã được bảng khác sử dụng. Xác định rollback nào an toàn, trường hợp nào cần forward-fix.

### Bước 10 — Viết báo cáo

Ghi lại artifact CSV version, changeset ID, số dòng mong đợi/thực tế, mã được cập nhật/chèn, lần update thứ hai, kết quả lỗi và rollback.

Tiêu chí hoàn thành: người học giải thích được khác biệt loadData/loadUpdateData, thiết kế khóa ổn định, chứng minh update lần hai không nạp lại changeset đã hoàn tất, và xử lý được CSV version mới mà không xóa hoặc ghi đè dữ liệu ngoài ý muốn.

## 24. Checklist trước khi phát hành dữ liệu tham chiếu

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Đây thực sự là dữ liệu tham chiếu? | Owner, vòng đời và consumer đã xác định |
| Khóa định danh ổn định và duy nhất? | Primary/unique key và kiểm tra CSV |
| Chọn đúng loadData hay loadUpdateData? | Mục tiêu insert-only hay update/insert rõ ràng |
| CSV bất biến theo release? | File version và changeset mới |
| Header/mapping/type chính xác? | Changelog columns được review |
| UTF-8, delimiter và quote đúng? | Đọc lại artifact và test Unicode |
| NULL/empty có quy ước? | Test dữ liệu biên trên DBMS thật |
| Không có khóa trùng hoặc dòng lỗi? | Validation CSV |
| Foreign key được nạp đúng thứ tự? | Dependency và assertion |
| runAlways/runOnChange có chủ đích? | Phân tích tác động khi chạy lặp |
| Dữ liệu người dùng có bị ghi đè? | Phân quyền sở hữu cột và test upgrade |
| Dòng vắng trong CSV có bị hiểu nhầm là delete? | Chính sách deactivate/delete tường minh |
| DATABASECHANGELOG ghi đúng? | ID/author/path/EXECTYPE |
| Update lần hai có an toàn? | Kết quả test rerun |
| Rollback có giữ dữ liệu đang được tham chiếu? | Test rollback/forward-fix |
| Fresh install và upgrade đều đạt? | Testcontainers trên DBMS production-like |
| Artifact đóng gói đủ CSV? | Kiểm tra resource trong JAR/container |

**Nguyên tắc cuối cùng:** dữ liệu tham chiếu phải có khóa ổn định, file CSV bất biến theo release và changeset được quản lý bằng lịch sử Liquibase. Dùng `loadData` cho lần seed có chủ đích; dùng `loadUpdateData` khi cần cập nhật/chèn theo khóa và đã kiểm soát quyền ghi đè. Kiểm tra rõ semantics của NULL, encoding, khóa trùng, foreign key và rollback. Đừng nhầm việc `update` bỏ qua changeset đã chạy với việc thao tác nạp dữ liệu tự nó an toàn khi bị thực thi lại. Chỉ phát hành sau khi đã thử fresh install, upgrade, lần update thứ hai và CSV phiên bản mới trên DBMS thực tế.

