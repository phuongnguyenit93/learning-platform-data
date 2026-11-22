# Thực thi thay đổi bằng update

Trong chương **Kiểm tra và cập nhật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, lệnh **update** là thao tác cốt lõi đưa những changeset Liquibase **chưa được ghi nhận** vào database đích. Người học cần hiểu không chỉ cách gọi lệnh, mà còn cách Liquibase xác định changeset đang chờ, kiểm tra checksum và precondition, sử dụng khóa triển khai, ghi lịch sử vào DATABASECHANGELOG, xử lý lỗi, phối hợp rollback và bảo vệ nhiều môi trường khi tích hợp Spring Boot hoặc CI/CD.

Mục tiêu thực hành là **triển khai có kiểm chứng**: cùng một bộ changelog được dùng từ development sang staging rồi production, mỗi lần chạy đều biết chính xác đối tượng sẽ thay đổi, điều kiện nào phải đạt, SQL nào có thể được thực thi và sau đó có bằng chứng nào chứng minh kết quả.

> **Ý chính:** `update` không phải lệnh “đồng bộ database với mọi thứ trong file” theo kiểu tự động sửa mọi sai lệch. Nó xử lý các changeset đủ điều kiện theo changelog và **lịch sử của chính database đích**. Nếu schema bị sửa thủ công hoặc changeset cũ bị thay đổi, không thể chỉ gọi update để mặc định chữa lành mọi khác biệt.

## 1. Lệnh update giải quyết vấn đề gì?

Trong mô hình migration có phiên bản, nhóm phát triển lưu các thay đổi vào changelog:

~~~text
db/changelog/db.changelog-master.yaml
    ├── changeset A: tạo bảng
    ├── changeset B: thêm cột
    ├── changeset C: thêm ràng buộc
    └── changeset D: cập nhật dữ liệu tham chiếu
~~~

Database đích giữ lịch sử Liquibase trong bảng **DATABASECHANGELOG**, thường có các thông tin ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE, MD5SUM và thứ tự triển khai. Khi gọi update, Liquibase đối chiếu danh sách changeset trong changelog với bảng lịch sử rồi xử lý những changeset đang chờ, có xét đến bộ lọc và các thuộc tính như runAlways/runOnChange.

| Trạng thái | Kết quả thông thường khi gọi update |
|---|---|
| Changeset mới, chưa được ghi nhận | Được xem xét để thực thi nếu bộ lọc và điều kiện cho phép |
| Changeset đã ghi EXECUTED, không có quy tắc chạy lại | Không thực thi lại |
| Changeset đã ghi nhận nhưng nội dung bị sửa | Có thể gặp lỗi xác minh checksum |
| Changeset có runOnChange hoặc runAlways | Có thể được thực thi lại theo quy tắc của thuộc tính |
| Changeset bị loại bởi context, label hoặc dbms | Không được thực thi trong lần chạy đó |
| Changeset có precondition không đạt | Dừng, cảnh báo, bỏ qua hoặc đánh dấu đã chạy tùy chính sách hợp lệ |

**Update thường là thao tác tăng tiến, không phải reset database.** Khi một changeset được ghi nhận thành công, việc gọi cùng lệnh lần nữa thông thường không nhân đôi các thao tác CREATE TABLE hoặc INSERT của changeset đó. Đây là khả năng tiếp tục triển khai dựa trên lịch sử, không phải bảo đảm mọi câu SQL tự thân đều idempotent.

## 2. Các thành phần tham gia một lần update

Có bốn thành phần cần xác định trước khi chạy:

1. **Changelog nguồn:** tệp gốc và các changelog con được include; xác định trình tự thay đổi.
2. **Cấu hình kết nối:** JDBC URL, driver, tài khoản migration, schema/catal​og và các tham số liên quan.
3. **Lịch sử database:** DATABASECHANGELOG chứa danh tính và trạng thái của changeset đã được ghi nhận.
4. **Khóa điều phối:** DATABASECHANGELOGLOCK giúp phối hợp các tiến trình Liquibase cùng sử dụng cơ chế khóa trên một database.

Sơ đồ khái niệm:

~~~text
                  Changelog + cấu hình triển khai
                               |
                         liquibase update
                               |
                 Đúng database và schema đích?
                               |
                   Đọc lịch sử DATABASECHANGELOG
                               |
              Chọn changeset chưa chạy / cần chạy lại
                               |
                Kiểm tra bộ lọc, checksum, điều kiện
                               |
                   Thực thi các change phù hợp
                               |
                 Ghi trạng thái vào DATABASECHANGELOG
                               |
                   Kiểm chứng schema và dữ liệu
~~~

Sơ đồ này diễn tả **logic nghiệp vụ**, không phải cam kết thứ tự gọi hàm nội bộ hay thứ tự lấy khóa của mọi phiên bản Liquibase. Trong thực thi thực tế, Liquibase có thể chuẩn bị changelog, kiểm tra lỗi và điều phối khóa theo cách cụ thể của phiên bản và bộ thực thi.

Điều đặc biệt quan trọng: **DATABASECHANGELOGLOCK không khóa tất cả truy vấn ứng dụng**. Nó là cơ chế phối hợp migration Liquibase; việc một câu ALTER TABLE có khóa truy vấn hay gây chờ đọc/ghi còn phụ thuộc DBMS và loại DDL.

## 3. Ví dụ changelog đầy đủ để thực hành update

Giả sử một ứng dụng quản lý thông báo triển khai cần bảng `deployment_note` có ba trường id, title và state. Tệp changelog YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-deployment-note"
      author: "team-db"
      comment: "Tạo bảng ghi chú triển khai"
      changes:
        - createTable:
            tableName: deployment_note
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_deployment_note
                    nullable: false
              - column:
                  name: title
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: deployment_note

  - changeSet:
      id: "20261119-002-add-deployment-state"
      author: "team-db"
      comment: "Bổ sung trạng thái ghi chú"
      changes:
        - addColumn:
            tableName: deployment_note
            columns:
              - column:
                  name: state
                  type: VARCHAR(24)
      rollback:
        - dropColumn:
            tableName: deployment_note
            columnName: state

  - changeSet:
      id: "20261119-003-insert-demo-note"
      author: "team-db"
      comment: "Thêm dữ liệu minh họa cho môi trường thử nghiệm"
      contextFilter: "dev"
      changes:
        - insert:
            tableName: deployment_note
            columns:
              - column:
                  name: id
                  valueNumeric: 100
              - column:
                  name: title
                  value: "First deployment"
              - column:
                  name: state
                  value: "DRAFT"
      rollback:
        - delete:
            tableName: deployment_note
            where: "id = 100"
~~~

Các điểm quan trọng:

- Mỗi changeset có **id** và **author** riêng; đường dẫn changelog hoàn thiện khóa nhận diện **ID + AUTHOR + FILENAME**.
- Thứ tự chạy được xác định bởi changelog, nên bảng được tạo trước khi thêm cột; cột state tồn tại trước khi INSERT sử dụng nó.
- Changeset thứ ba gắn contextFilter=dev để phục vụ ví dụ thử nghiệm, **không phải** cơ chế bảo vệ production đủ mạnh khi đứng độc lập. Phải cấu hình context của lệnh và có kiểm soát môi trường rõ ràng; với dữ liệu demo nên tách hoặc bảo vệ thêm ở pipeline.
- Rollback ở ví dụ nhằm minh họa cách khai báo. DROP TABLE/DROP COLUMN/DELETE có thể làm mất dữ liệu nếu database đã được sử dụng thật.
- Đừng chạy ví dụ này trên bảng production đã tồn tại. Dùng database thử nghiệm mới, có thể xóa và khôi phục.

Nếu dự án tách thành nhiều tệp, có thể dùng **include** từ changelog gốc; khi đó phải kiểm tra thứ tự include và đường dẫn định danh. Không đổi tên hoặc di chuyển changelog đã triển khai mà không kiểm soát tác động đến FILENAME trong lịch sử.

## 4. Cấu hình đúng database trước khi chạy

Liquibase cần biết ít nhất:

- **Changelog file:** nơi chứa định nghĩa changeset gốc.
- **JDBC URL:** database đích cụ thể, ví dụ một database development.
- **Tài khoản và quyền:** quyền đọc lịch sử, khóa, thực thi DDL/DML và ghi DATABASECHANGELOG.
- **Driver/DBMS:** driver tương thích với database đích.
- **Schema/catal​og và changelog parameters:** nếu dự án sử dụng nhiều schema hoặc tham số theo môi trường.

Ví dụ một cấu hình Liquibase CLI **minh họa**, trong đó thông tin xác thực thật được cung cấp bằng secret store hoặc biến môi trường được hỗ trợ:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
url=jdbc:postgresql://localhost:5432/learning_dev
username=migration_user
~~~

Không commit mật khẩu vào liquibase.properties hoặc lệnh mẫu. Khi sử dụng CLI, tên biến môi trường và cách ghi đè cấu hình có thể phụ thuộc phiên bản Liquibase; nên thống nhất một nguồn cấp credentials chính thức và kiểm tra cấu hình có hiệu lực trước khi chạy.

Ví dụ các lệnh sau giả định URL/username/password được cấp đúng bởi cấu hình runtime:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Trong production, **tên database và schema phải được xác minh độc lập với tên file cấu hình**. Việc file có tên prod.properties không chứng minh JDBC URL hiện tại đang trỏ vào production đúng dự kiến. Dùng bước kiểm tra cấu hình của job, quyền DB, thông tin host/database và phép thử chỉ đọc.

Không nhầm **default schema của đối tượng ứng dụng** với schema mà Liquibase lưu các bảng DATABASECHANGELOG/DATABASECHANGELOGLOCK khi có cấu hình riêng. Nếu cấu hình sai, migration có thể thay đổi schema A nhưng kiểm tra lịch sử ở schema B, gây nhầm trạng thái triển khai.

## 5. Preflight trước update: validate, status, update-sql

Một quy trình chuẩn thường gồm ba phép kiểm tra trước khi chạy update.

### 5.1. validate

~~~bash
liquibase validate
~~~

Lệnh validate giúp phát hiện lỗi cấu trúc changelog, thiếu thuộc tính cần thiết, changeset trùng định danh và những vấn đề mà phiên bản Liquibase có thể kiểm tra được. Tùy cấu hình và trạng thái database, việc kiểm tra checksum của changeset đã chạy cũng có thể được báo ở giai đoạn validation/triển khai.

**Giới hạn:** validate thành công không chứng minh dữ liệu hiện tại phù hợp để thêm UNIQUE/FK, không đảm bảo đủ quyền DDL và không bảo đảm một thao tác DDL sẽ không khóa bảng lâu.

### 5.2. status --verbose

~~~bash
liquibase status --verbose
~~~

Lệnh status cho biết changeset nào đang chờ đối với database và bộ lọc được dùng. Khi chưa có dữ liệu trong DATABASECHANGELOG, các changeset phù hợp thường được xem là chưa triển khai. Sau khi update thành công, chúng thông thường sẽ không còn nằm trong danh sách pending.

**Giới hạn:** status không phải bằng chứng toàn bộ schema đã đúng; một bảng có thể bị DBA xóa thủ công sau khi changeset đã được ghi nhận, nhưng Liquibase vẫn có lịch sử.

### 5.3. update-sql

~~~bash
liquibase update-sql
~~~

Lệnh update-sql tạo SQL dự kiến phục vụ review, thay vì áp dụng các thay đổi DDL/DML của update. Đọc bản SQL được sinh trên đúng DBMS để kiểm tra tên schema, bảng, kiểu dữ liệu, thứ tự thao tác và nguy cơ xóa dữ liệu.

**Giới hạn quan trọng:** bản SQL dự kiến không nhất thiết phản ánh mọi điều kiện runtime trong môi trường thay đổi liên tục. Việc đánh giá precondition, thay thế tham số hoặc xử lý SQL đặc thù có thể chịu ảnh hưởng bởi phiên bản Liquibase, cấu hình và trạng thái DB. Không coi update-sql là bảo đảm tuyệt đối rằng lần chạy update sau đó sẽ thành công.

Đối với production, cả validate, status, update-sql và update cần dùng **cùng artifact, cùng changelog revision, cùng kết nối, cùng bộ lọc và cùng parameters**. Nếu SQL được review trên staging nhưng update trỏ sang production với cấu hình khác, phải review thêm khác biệt đúng mục tiêu đó.

## 6. Chạy update bằng Liquibase CLI

Khi các kiểm tra đạt yêu cầu và thông tin kết nối đã được xác nhận, gọi:

~~~bash
liquibase update
~~~

Nếu cấu hình không khai báo changelog file, có thể chỉ định tường minh:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Trong ví dụ development ở phần 3, có thể dùng bộ lọc context phù hợp:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml   --context-filter=dev update
~~~

Cú pháp tùy chọn dòng lệnh có thể thay đổi giữa các phiên bản Liquibase. Cần kiểm tra phiên bản thực tế và cấu hình `--context-filter`/`--label-filter` thay vì sao chép nguyên một lệnh sang các release không tương thích.

Sau khi lệnh thành công, cần kiểm tra **output thực thi, lịch sử và schema thật**, không chỉ kiểm tra process exit code bằng 0. Có thể chạy:

~~~bash
liquibase status --verbose
liquibase history
~~~

Và truy vấn trực tiếp DATABASECHANGELOG (bằng tài khoản chỉ đọc nếu phù hợp):

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Nếu bảng DATABASECHANGELOG được đặt trong schema riêng, hãy dùng tên schema đúng hoặc cấu hình search path tương ứng. Không mặc định tên schema là public.

### Dùng update nhiều lần có nguy hiểm không?

Với changeset thông thường đã ghi nhận EXECUTED và giữ nguyên nội dung, lần gọi update tiếp theo sẽ không chạy lại chúng. Nhưng điều đó **không có nghĩa gọi update luôn vô hại**, vì:

- Changelog có thể vừa thêm changeset mới.
- Có changeset có **runAlways** hoặc **runOnChange**.
- Một lần chạy trước thất bại giữa chừng; trạng thái thực tế có thể khác lịch sử.
- Thông tin kết nối hoặc schema đã thay đổi.
- Có thay đổi context/label làm tập changeset được chọn khác.
- Một changeset từng bị MARK_RAN có thể không tạo đối tượng như người đọc log lầm tưởng.

Vì vậy, mỗi lần update phải là một thao tác triển khai có phạm vi và bằng chứng xác nhận riêng.

## 7. Quy tắc xác định changeset đang chờ

Liquibase nhận diện một changeset bằng bộ ba:

~~~text
(ID, AUTHOR, FILENAME)
~~~

Bộ ba này được so sánh với lịch sử trong DATABASECHANGELOG. Nếu tệp changelog được đổi đường dẫn vật lý, FILENAME dùng để nhận diện có thể thay đổi. Khi cần tổ chức lại thư mục, có thể cân nhắc **logicalFilePath** theo cú pháp/phạm vi mà phiên bản Liquibase hỗ trợ và phải đối chiếu với giá trị lịch sử đã lưu.

Ví dụ:

~~~text
changes/001-customer.yaml : id=20261119-001, author=team-db
changes/002-order.yaml    : id=20261119-001, author=team-db
~~~

Hai thay đổi trên có thể có định danh khác nhau vì FILENAME khác nhau, nhưng tái sử dụng id như vậy làm việc tra cứu khó hơn. Nên chọn id duy nhất và mô tả rõ ý định trên toàn module nếu có thể.

Nếu một changeset cũ đã ghi nhận được sửa thành id khác hoặc author khác, Liquibase có thể coi đó là một changeset **mới**, dẫn tới cố chạy lại CREATE TABLE/ALTER TABLE. Không sửa id, author, FILENAME hay nội dung của changeset đã phát hành để chỉ “sắp xếp lại” changelog.

**Update không sắp xếp changeset theo id số hoặc timestamp.** Trình tự chính do vị trí khai báo và cơ chế include/includeAll xác định. Một id như 20261119-999 không tự bảo đảm nó chạy sau id 20261120-001 nếu tệp được nạp theo thứ tự khác.

## 8. Filter: context, label và DBMS

Không phải mọi changeset trong một changelog đều nhất thiết phải chạy trên mọi database. Liquibase hỗ trợ:

- **contextFilter:** nhóm changeset theo ngữ cảnh triển khai, chẳng hạn dev/test/prod hoặc các tính năng.
- **labels:** gắn nhãn cho changeset và chọn qua label filter.
- **dbms:** giới hạn changeset vào loại hệ quản trị cơ sở dữ liệu nhất định.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-test-seed"
      author: "team-db"
      contextFilter: "dev"
      labels: "test-data"
      changes:
        - insert:
            tableName: deployment_note
            columns:
              - column:
                  name: id
                  valueNumeric: 200
              - column:
                  name: title
                  value: "Development only"
~~~

Cần rất thận trọng: **không nên xem chỉ việc gắn contextFilter=dev là lớp bảo mật tự động ngăn chạy trong production**. Quy tắc chọn changeset khi người gọi không cung cấp filter hoặc khi dùng các toán tử context/label có thể khác điều trực giác mong đợi. Muốn bảo vệ dữ liệu demo, hãy kết hợp cấu hình filter tường minh, kiểm tra môi trường, phân tách changelog phù hợp và cổng phê duyệt pipeline.

Khi review update-sql và chạy update, phải dùng **chính xác cùng context/label filters**. Một changeset ở trạng thái pending vì bị lọc ra trong lần này vẫn có thể được chọn ở một lần chạy sau với filter khác. Filter không phải một thay thế cho giới hạn quyền database.

## 9. Preconditions và cách thay đổi quyết định của update

Precondition kiểm tra giả định trước khi chạy changeset. Ví dụ bảng `deployment_note` phải tồn tại trước khi thêm cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-add-owner-column"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: deployment_note
      changes:
        - addColumn:
            tableName: deployment_note
            columns:
              - column:
                  name: owner_code
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: deployment_note
            columnName: owner_code
~~~

Có hai loại vấn đề:

- **Fail:** kiểm tra chạy được nhưng kết quả không thỏa điều kiện, ví dụ bảng không tồn tại.
- **Error:** lỗi xảy ra trong khi kiểm tra, ví dụ không đọc được metadata hoặc SQL kiểm tra không hợp lệ.

Bảng hành vi ở cấp changeset:

| Chính sách | Tác động thường gặp |
|---|---|
| HALT | Dừng triển khai khi điều kiện không đạt hoặc gặp lỗi tương ứng |
| WARN | Ghi cảnh báo và tiếp tục theo ngữ nghĩa của chính sách |
| CONTINUE | Bỏ qua changeset trong lần chạy hiện tại, không ghi nhận là đã chạy |
| MARK_RAN | Không thực thi changes, nhưng ghi nhận changeset đã được xử lý với EXECTYPE tương ứng |

**CONTINUE và MARK_RAN chỉ áp dụng cho precondition ở cấp changeset**, không đặt tùy tiện trong precondition cấp changelog. Cần phân biệt onFail với onError và kiểm tra hỗ trợ của phiên bản Liquibase.

MARK_RAN có thể hợp lý trong một quy trình baseline đã xác minh đối tượng/dữ liệu thực sự đúng, nhưng không nên sử dụng chỉ vì gặp lỗi “table already exists”. Nếu đối tượng trùng tên mà thiếu cột, việc đánh dấu đã chạy sẽ che giấu schema drift và khiến các changeset sau có thể thất bại khó chẩn đoán.

## 10. Checksum: vì sao sửa changeset cũ có thể chặn update?

Liquibase lưu **MD5SUM** cùng lịch sử để nhận diện những thay đổi nội dung của changeset. Sau khi một changeset đã triển khai, việc sửa nội dung change, SQL hoặc một số thuộc tính có thể khiến checksum tính lại không trùng với lịch sử.

Ví dụ, changeset từng tạo cột state VARCHAR(24). Sau đó có người sửa trực tiếp nó thành VARCHAR(50) trong cùng id/author/filename. Trên database đã chạy:

- Thay đổi vật lý ban đầu đã được áp dụng.
- Changelog mới mô tả khác với nội dung từng chạy.
- Liquibase có thể báo lỗi checksum thay vì tự ALTER COLUMN.

Cách xử lý thường đúng:

1. Xem diff source và MD5SUM/hồ sơ phát hành.
2. Khôi phục changeset đã chạy về nội dung ban đầu.
3. Viết **changeset mới** để đổi độ dài state từ 24 lên 50.
4. Chạy validate/status/update-sql rồi update qua các môi trường.

Không xem **clear-checksums**, **validCheckSum** hay sửa tay DATABASECHANGELOG là lựa chọn đầu tiên khi update bị chặn. Những cơ chế đó có mục đích hợp lệ trong một số tình huống nhưng có thể che khuất việc changelog và schema thật đang lệch nhau.

### runOnChange và runAlways

Có những changeset được thiết kế có chủ đích để chạy lại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-create-summary-view"
      author: "team-db"
      runOnChange: true
      changes:
        - createView:
            viewName: v_deployment_note_summary
            replaceIfExists: true
            selectQuery: |
              SELECT state, COUNT(*) AS total
              FROM deployment_note
              GROUP BY state
~~~

Ví dụ phù hợp hơn với view có thể tái tạo so với các DDL/DML không idempotent. Phải kiểm tra DBMS hỗ trợ replace view và khả năng chạy lại của change type này.

**runOnChange** có thể khiến changeset được chạy lại khi nội dung thay đổi theo quy tắc checksum; **runAlways** làm changeset được chạy ở mỗi lần xử lý changelog theo điều kiện phù hợp. Không dùng các thuộc tính này như cách ép Liquibase áp dụng lại một migration addColumn hoặc INSERT đã chạy và có thể tạo trùng dữ liệu.

## 11. DATABASECHANGELOGLOCK và chạy đồng thời

Một database có thể có nhiều tiến trình muốn thực thi Liquibase:

~~~text
CI/CD job A    ──┐
                 ├── Liquibase ──> cùng database
Spring Boot B  ──┘
~~~

Liquibase sử dụng **DATABASECHANGELOGLOCK** để điều phối việc nhiều tiến trình Liquibase cố chạy migration cùng lúc. Một tiến trình giữ lock, những tiến trình khác có thể phải chờ hoặc thất bại theo cấu hình/timeout.

Lợi ích:

- Giảm nguy cơ hai tiến trình Liquibase đồng thời chọn cùng changeset đang pending.
- Giữ tính tuần tự của quá trình cập nhật lịch sử Liquibase.
- Hỗ trợ triển khai từ nhiều instance hoặc job nhưng không phải cơ chế phát hành ứng dụng đầy đủ.

Giới hạn:

- Khóa Liquibase không ngăn một DBA chạy SQL ngoài Liquibase.
- Nó không bảo đảm bảng ứng dụng không bị khóa bởi ALTER TABLE hoặc CREATE INDEX.
- Nó không làm hai phiên bản ứng dụng tự tương thích khi đổi tên/xóa cột.
- Nếu tiến trình bị hủy đột ngột, trạng thái khóa có thể cần điều tra; không giải phóng khóa cưỡng bức khi còn tiến trình migration đang thực thi.

Khi gặp “could not acquire change log lock”, kiểm tra các job đang chạy, kết nối, log, lock owner và thời gian giữ khóa. Chỉ cân nhắc lệnh **release-locks** sau khi xác minh không còn một tiến trình Liquibase hợp lệ đang triển khai. Tháo khóa không sửa những thay đổi schema từng phần.

## 12. Giao dịch, runInTransaction và DDL từng phần

Một changeset thường được Liquibase thực thi trong phạm vi giao dịch khi **runInTransaction** được bật và DBMS/driver hỗ trợ. Điều này giúp các bước trong một changeset có cơ hội thành công hoặc rollback giao dịch cùng nhau.

Tuy nhiên, các DBMS khác nhau đáng kể:

- Một số loại DDL được thực thi trong transaction và có thể rollback.
- Một số loại DDL có thể tạo implicit commit hoặc không được hỗ trợ trong transaction.
- CREATE INDEX CONCURRENTLY trên PostgreSQL có quy tắc transaction riêng.
- Thao tác dữ liệu lớn có thể giữ lock và transaction log trong thời gian dài.
- Một changeset nhiều câu lệnh có thể thất bại sau khi một số thao tác đã có hiệu lực nếu DBMS không bảo đảm atomic DDL.

Đối với thay đổi có yêu cầu ngoài transaction, một số changeset có thể cần:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-021-special-ddl"
      author: "team-db"
      runInTransaction: false
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_deployment_note_title
              ON deployment_note(title);
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY ix_deployment_note_title;
~~~

Đây là **ví dụ PostgreSQL để giải thích yêu cầu transaction**, không phải cấu hình dùng nguyên văn cho mọi database hoặc mọi phiên bản Liquibase. Phải thử cách Liquibase/driver xử lý câu lệnh và đánh giá rủi ro của việc tắt transaction trước production. Với một changeset chứa nhiều câu lệnh và runInTransaction=false, kết quả có thể bị áp dụng một phần trong trường hợp lỗi.

**Không coi changeset, transaction và lần chạy update là ba ranh giới nguyên tử giống nhau.** Một lệnh update gồm nhiều changeset thường không có nghĩa toàn bộ thay đổi từ A đến Z sẽ được rollback tự động khi Z thất bại.

## 13. Một lỗi giữa chừng ảnh hưởng đến lần update tiếp theo thế nào?

Giả sử database mới và changelog có ba changeset A, B, C:

~~~text
A: createTable       -> thành công
B: addColumn         -> thành công
C: addForeignKey     -> thất bại vì dữ liệu mồ côi
~~~

Khi đó có thể xảy ra:

- A và B đã được ghi vào DATABASECHANGELOG.
- C chưa được ghi nhận thành công.
- Những thay đổi của C có thể đã rollback, hoặc có phần DDL đã tồn tại tùy DBMS/transaction.
- Ứng dụng có thể chưa tương thích với schema mới.
- Gọi update lại sẽ xử lý tập changeset đang chờ theo lịch sử lúc đó, **không nhất thiết chạy lại A và B**.

Quy trình xử lý:

1. **Ngừng tự động retry** nếu chưa rõ trạng thái schema.
2. Đọc log và xác định changeset đầu tiên thất bại.
3. Kiểm tra DATABASECHANGELOG để biết changeset nào đã ghi nhận.
4. Kiểm tra metadata/data thực tế của database đích, đặc biệt phần C có thể bị áp dụng một phần.
5. Xác định nguyên nhân gốc: dữ liệu, quyền, cú pháp, trạng thái ngoài Liquibase, timeout hoặc transaction.
6. Tạo changeset sửa tiến hoặc phương án khôi phục được review; không sửa changeset đã chạy tùy tiện.
7. Chạy lại validate, status, update-sql với cùng database và cấu hình.
8. Chỉ retry update khi trạng thái đã rõ ràng và được phê duyệt.

Ví dụ foreign key thất bại vì bảng con có khóa không được tham chiếu, cần làm sạch/mapping dữ liệu hoặc điều chỉnh migration phù hợp. Không xóa các dòng giao dịch chỉ để FK tạo thành công nếu chưa có quyết định nghiệp vụ.

**Lệnh update không tự động rollback toàn bộ những changeset đã chạy thành công trước lỗi.** Cần có chiến lược rollback hoặc forward fix độc lập.

## 14. Update khác rollback và cập nhật có giới hạn

Phân biệt các nhóm lệnh:

| Lệnh/nhóm lệnh | Mục tiêu |
|---|---|
| validate | Kiểm tra tính hợp lệ của changelog theo khả năng công cụ |
| status | Xem changeset đang chờ đối với database hiện tại |
| update-sql | Xem SQL dự kiến của update để review |
| update | Thực thi các changeset chưa chạy/đủ điều kiện |
| rollback | Hoàn tác changeset theo điểm đích hoặc chiến lược rollback |
| history | Xem lịch sử triển khai Liquibase |
| update-count/update-to-tag (khi phiên bản hỗ trợ) | Giới hạn phạm vi cập nhật theo số lượng hoặc mốc tag |

**Rollback không tự xảy ra chỉ vì update thất bại.** Nó phải được thiết kế, kiểm tra và thực thi riêng. Một số change type hỗ trợ rollback tự động; SQL tùy ý và thay đổi dữ liệu có thể cần rollback tường minh.

Các lệnh cập nhật theo số lượng hoặc tag có thể hữu ích khi muốn kiểm soát một phần changelog, nhưng cú pháp và hành vi có thể khác theo phiên bản Liquibase. Cần hiểu rõ mốc dừng và cách các changeset được lọc, nhất là khi có includeAll, context hoặc label. Không áp dụng một số lượng changeset dự đoán sẵn mà không xem status và generated SQL của đúng database.

Khi thực thi rollback, phải kiểm tra **thứ tự phụ thuộc, phiên bản code đang chạy, dữ liệu đã sinh ra và giá trị changelog parameters**. Ví dụ rollback dropColumn có thể xóa dữ liệu đã được ứng dụng ghi sau khi update thành công.

## 15. Đọc DATABASECHANGELOG để xác minh kết quả

DATABASECHANGELOG là lịch sử **Liquibase ghi nhận**, không phải bản sao toàn bộ cấu trúc DBMS. Những giá trị EXECTYPE thường gặp:

| EXECTYPE | Diễn giải thực tế |
|---|---|
| EXECUTED | Changeset đã được thực thi và ghi nhận theo quy tắc Liquibase |
| RERAN | Changeset được chạy lại theo cấu hình phù hợp |
| MARK_RAN | Changeset được đánh dấu đã chạy mà không cần thực thi phần thay đổi trong lần ghi nhận đó |

Không kết luận rằng tất cả cột/bảng đều tồn tại đúng chỉ vì thấy EXECTYPE=EXECUTED. Có thể có thay đổi SQL ngoài Liquibase sau đó, hoặc DBMS đã xử lý một số DDL khác dự kiến.

Ví dụ truy vấn:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED,
    MD5SUM
FROM DATABASECHANGELOG
WHERE ID LIKE '20261119-%'
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Sau đó kiểm tra schema thực tế với metadata DBMS và truy vấn dữ liệu:

~~~sql
-- Ví dụ PostgreSQL: xác minh cột của bảng sau update.
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'deployment_note'
ORDER BY ordinal_position;
~~~

Câu SQL trên chỉ minh họa PostgreSQL khi bảng nằm trong public; nếu migration dùng schema app hoặc DBMS khác, phải thay điều kiện/catal​og phù hợp.

Nếu DATABASECHANGELOG có thay đổi nhưng bảng không đúng, đây là tín hiệu cần điều tra **schema drift**, thay vì tự xóa dòng lịch sử hoặc ép chạy lại changeset.

## 16. Cấu hình update trong Spring Boot

Spring Boot có thể khởi chạy Liquibase thông qua tích hợp ứng dụng:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Đây là ví dụ **cấu hình Spring Boot**, không phải file liquibase.properties của CLI. Spring Boot giải quyết các placeholder ${DB_URL}, ${DB_USERNAME}, ${DB_PASSWORD} qua cơ chế externalized configuration của nó, còn Liquibase dùng datasource và changelog được cấu hình.

Khi ứng dụng khởi động, tích hợp Liquibase có thể chạy update trước khi ứng dụng hoạt động bình thường. Lợi ích là schema migration đi cùng artifact ứng dụng, nhưng phải lưu ý:

- Nếu startup migration thất bại, ứng dụng có thể không khởi động thành công.
- Với nhiều instance, DATABASECHANGELOGLOCK giúp ngăn các Liquibase instance đồng thời triển khai, nhưng có thể làm tăng thời gian khởi động và không thay thế phối hợp phát hành.
- Một instance cũ đang phục vụ request có thể chưa tương thích với schema mới, nhất là khi đổi tên hoặc xóa cột.
- Cấu hình Liquibase có thể sử dụng datasource riêng qua các thuộc tính Spring Boot phù hợp; phải xác minh không vô tình trỏ đến database khác.
- Đối với production và migration nguy cơ cao, nhiều đội chọn chạy job Liquibase độc lập trong pipeline trước khi đưa ứng dụng mới vào traffic.

Có thể tắt Liquibase startup tại một profile được quản lý riêng bằng cấu hình tương ứng, nhưng cần bảo đảm migration lúc đó được thực hiện bởi job chính thức. Không để startup migration và pipeline migration cùng có quyền tự động triển khai mà không có nguyên tắc ownership rõ ràng.

### Quản lý schema và parameters trong Spring Boot

Nếu changeset cần property substitution, có thể truyền tham số thông qua:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    parameters:
      appSchema: ${APP_SCHEMA}
~~~

Khi làm vậy, phải kiểm tra rằng APP_SCHEMA đúng với database đích và nhất quán trong generated SQL, update và rollback. Tham số cho tên schema không phải cơ chế phân quyền: tài khoản migration vẫn cần chỉ có quyền cần thiết.

## 17. Pipeline CI/CD: update có cổng kiểm soát

Một quy trình triển khai điển hình:

~~~text
Build artifact và đóng băng changelog revision
       |
Kiểm tra định dạng / validate
       |
Chạy migration thử trên database đại diện
       |
Kiểm tra pending changesets và tạo update-sql
       |
Review SQL, dữ liệu, quyền, thời gian khóa, rollback
       |
Phê duyệt theo môi trường
       |
Chạy update bằng một migration job được ủy quyền
       |
Đối chiếu DATABASECHANGELOG + schema/dữ liệu thực tế
       |
Triển khai / mở traffic phiên bản ứng dụng tương thích
~~~

Ví dụ pipeline shell **mang tính minh họa** khi đã inject kết nối và secret an toàn:

~~~bash
set -e

liquibase validate
liquibase status --verbose
liquibase update-sql

# Cổng phê duyệt và xác nhận database đích phải nằm ngoài phần mẫu.
liquibase update

liquibase status --verbose
liquibase history
~~~

Trong production, không nên chỉ có chuỗi lệnh trong một script rồi tự coi như đã có review. Cần có cơ chế kiểm tra **actual generated SQL**, phê duyệt của người chịu trách nhiệm và lưu lại artifact, kết quả, commit/changelog revision của lần chạy.

Một pipeline mạnh cần thực hiện:

1. Xác nhận môi trường đích bằng tên hệ thống và thông tin DB đọc được.
2. Chặn deploy nhầm production từ nhánh không được phép.
3. Inject credentials từ secret manager, tránh in secret ra console.
4. Bảo đảm chỉ một job có trách nhiệm migration cho cùng database tại một thời điểm.
5. Đảm bảo validate/status/update-sql/update cùng artifact và bộ lọc.
6. Dừng ngay nếu phát hiện checksum khác, schema drift hoặc dữ liệu không đạt precondition.
7. Kiểm soát thay đổi phá tương thích bằng expand–migrate–contract.
8. Lưu bằng chứng SQL đã review và lịch sử DATABASECHANGELOG.
9. Có thủ tục rollback hoặc forward fix, sao lưu và phương án vận hành khi lỗi.
10. Không tự retry vô hạn nếu job fail ở giữa migration.

## 18. Triển khai nhiều môi trường nhưng không sửa changelog

Một changelog giống nhau có thể có trạng thái khác nhau trên từng database:

| Môi trường | Ví dụ trạng thái |
|---|---|
| Development | Changeset A, B, C đã chạy |
| Staging | Changeset A, B đã chạy; C đang chờ |
| Production | Chỉ A đã chạy; B, C đang chờ |

Khi chạy update trên staging, Liquibase dựa vào DATABASECHANGELOG của staging. Khi chạy trên production, nó dựa vào lịch sử production; hai môi trường **không chia sẻ lịch sử chỉ vì cùng dùng một repo Git**.

Cần giữ nguyên changeset đã phát hành qua các môi trường. Nếu thay đổi id, author, filename, tên cột hoặc SQL của changeset cũ giữa staging và production, bạn sẽ phá vỡ tính tái lập và có thể gây lỗi checksum.

Khi cần SQL riêng theo DBMS hoặc seed riêng theo môi trường, dùng bộ lọc và changelog parameters có kiểm soát, nhưng phải kiểm tra **cả tính đúng của SQL và trạng thái dữ liệu**. Không thiết kế production bằng cách tùy tiện sao chép bản dump từ development rồi tin DATABASECHANGELOG sẽ hợp lệ.

Điều kiện cốt lõi để promote đáng tin cậy:

- Cùng version Liquibase/extension phù hợp.
- Cùng commit hoặc artifact changelog đã được review.
- JDBC URL/schema/credentials đúng môi trường.
- Bộ lọc context/label/dbms được khai báo và kiểm chứng.
- Schema baseline tương thích với changeset pending.
- Mọi khác biệt dữ liệu có thể ảnh hưởng precondition hoặc constraint đã được xử lý.

## 19. Các thay đổi cần đặc biệt thận trọng khi update

Không phải changeset nào cũng có cùng rủi ro. Trước khi cho chạy update, phân loại:

| Thao tác | Nguy cơ | Hướng kiểm soát |
|---|---|---|
| createTable bảng mới | Trùng tên hoặc quyền/schema sai | Kiểm tra bảng chưa tồn tại và schema đích |
| addColumn nullable | Ảnh hưởng DDL/lock, mapping ứng dụng | Đánh giá phiên bản ứng dụng và DBMS |
| addColumn NOT NULL có dữ liệu cũ | Dữ liệu không có giá trị hợp lệ | Dùng expand, backfill, sau đó siết ràng buộc |
| addUniqueConstraint | Dữ liệu trùng gây thất bại | Truy vấn phát hiện trùng trước update |
| addForeignKeyConstraint | Dữ liệu tham chiếu mồ côi | Kiểm tra dữ liệu và thứ tự migrate |
| createIndex bảng lớn | Lock, dung lượng đĩa và replication lag | Thử thời gian, cân nhắc online/concurrent |
| renameTable/renameColumn | Ứng dụng cũ/mới không tương thích | Thiết kế rolling deploy hoặc maintenance window |
| dropColumn/dropTable | Mất dữ liệu và phá contract | Backup, xác nhận không còn consumer, kế hoạch rollback |
| update/delete dữ liệu hàng loạt | Lock lâu, mất dữ liệu, log lớn | Theo lô, checkpoint, audit và forward fix |
| seed reference data | Trùng khóa hoặc đổi nghĩa mã | Dùng code ổn định, UNIQUE/FK và changeset phiên bản mới |

Không phải mọi thay đổi dữ liệu lớn đều nên thực hiện trong một changeset update duy nhất. Với backfill hàng triệu bản ghi, có thể phù hợp hơn khi tách job dữ liệu có checkpoint, quan sát và chạy lại an toàn. Liquibase vẫn quản lý các mốc schema/constraint, còn job dữ liệu thực hiện chuyển đổi theo lô dưới quy trình được điều phối.

## 20. Chẩn đoán sự cố update

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
|---|---|---|
| Could not acquire change log lock | Có job khác giữ khóa hoặc lock cũ chưa được giải phóng | Xác minh tiến trình, lock owner và trạng thái database; không force unlock khi còn job đang chạy |
| Checksum validation failed | Changeset đã chạy bị sửa, hoặc cấu hình/nội dung ảnh hưởng checksum | Đối chiếu history và Git; giữ changeset cũ, tạo changeset mới |
| Relation/table already exists | Đối tượng được tạo ngoài Liquibase hoặc changeset bị nhận diện thành mới | So sánh schema, ID/AUTHOR/FILENAME và DATABASECHANGELOG |
| Column already exists | Đã alter tay hoặc migration áp dụng một phần | Kiểm tra metadata và precondition, không tự MARK_RAN |
| Permission denied | Tài khoản migration thiếu quyền DDL hoặc quyền trên schema/history | Kiểm tra roles/grants tại database đích |
| SQL syntax error | DBMS không hỗ trợ change type/SQL, delimiter hoặc driver khác | Đọc generated SQL và phiên bản DBMS/driver |
| FK/UNIQUE creation failed | Dữ liệu hiện hữu vi phạm ràng buộc | Kiểm tra trùng/mồ côi, lập kế hoạch sửa dữ liệu |
| Command thành công nhưng app lỗi | Schema mới không tương thích ứng dụng đang chạy | Kiểm tra thứ tự deploy, ORM, native SQL và consumer |
| Update treo hoặc quá lâu | DDL lock, transaction dài, quét index hoặc dữ liệu lớn | Quan sát lock, query plan, thời gian xử lý và timeout |
| Unexpected changesets | Sai URL/schema, changelog, context/label hoặc mới đổi filename | Đối chiếu input của job và lịch sử DB |
| Status không còn pending nhưng schema thiếu | Drift do thao tác ngoài Liquibase hoặc MARK_RAN | Đọc EXECTYPE, metadata, truy vấn và kế hoạch sửa tiến |
| Job fail nhưng vài bảng đã thay đổi | DDL không rollback nguyên tử hoặc changeset trước đã commit | Xác định từng changeset đã ghi nhận và tác động vật lý |

Khi lỗi xảy ra, phân biệt **lỗi kết nối**, **lỗi parse/validate changelog**, **lỗi trạng thái/định danh**, **lỗi dữ liệu**, **lỗi SQL/DBMS**, **lỗi điều phối phiên bản ứng dụng**. Không sửa trực tiếp DATABASECHANGELOG để làm pipeline có màu xanh nếu chưa xử lý được nguyên nhân gốc.

## 21. Bài thực hành: chạy update và kiểm tra vòng đời changeset

**Bối cảnh:** bạn có một database thử nghiệm PostgreSQL mới, quyền tạo bảng và một changelog gồm ba changeset ở phần 3. Mục tiêu là quan sát một lần update đầu tiên, lần update lặp và sự khác biệt khi thay đổi source.

### Phần A — Chạy lần đầu

1. Tạo database thử nghiệm hoặc schema riêng theo quy trình được cấp phép.
2. Cấu hình kết nối và changelog gốc; xác nhận username, database và default schema.
3. Chạy validate và kiểm tra có lỗi cấu trúc không.
4. Chạy status --verbose để thấy các changeset đang chờ theo context đã chọn.
5. Chạy update-sql, kiểm tra thứ tự: CREATE TABLE, ADD COLUMN, INSERT có điều kiện chọn đúng môi trường.
6. Chạy update trên database thử nghiệm.
7. Truy vấn DATABASECHANGELOG để thấy ID, AUTHOR, FILENAME, EXECTYPE và MD5SUM.
8. Kiểm tra bảng deployment_note, cột state và hàng demo nếu đã chọn context phù hợp.

### Phần B — Chạy lần hai

1. Giữ nguyên changelog và cấu hình.
2. Chạy status --verbose; các changeset thông thường đã ghi nhận sẽ không còn pending.
3. Chạy update lần hai.
4. Xác minh không có bảng/cột bị tạo thêm và hàng demo không bị nhân đôi.
5. Đối chiếu DATABASECHANGELOG để hiểu lịch sử đã giúp Liquibase tránh chạy lại như thế nào.

### Phần C — Thêm một changeset mới

Thay vì sửa changeset 002, hãy bổ sung:

~~~yaml
  - changeSet:
      id: "20261120-001-add-created-by"
      author: "team-db"
      changes:
        - addColumn:
            tableName: deployment_note
            columns:
              - column:
                  name: created_by
                  type: VARCHAR(50)
      rollback:
        - dropColumn:
            tableName: deployment_note
            columnName: created_by
~~~

Đoạn này là một mục mới được nối vào **cùng danh sách databaseChangeLog**, không phải một changelog YAML độc lập. Sau đó:

1. Chạy validate/status và thấy **chỉ changeset mới** đang chờ.
2. Chạy update-sql; xác nhận SQL dự kiến chỉ thêm created_by.
3. Chạy update, kiểm tra bảng và lịch sử.
4. Không sửa id, author hoặc nội dung những changeset cũ đã chạy.

### Phần D — Thử lỗi có kiểm soát

**Chỉ trên database học tập có thể khôi phục**, thử sửa kiểu cột của một changeset đã được ghi nhận trong source, rồi chạy validate hoặc update tùy phiên bản để quan sát phản ứng checksum. **Không xóa hoặc sửa DATABASECHANGELOG** để vượt qua lỗi. Hoàn nguyên changeset cũ và viết changeset mới mô tả thay đổi muốn thực hiện.

Một thí nghiệm khác: tạo một changeset mới cố thêm constraint vi phạm dữ liệu đã có. Quan sát rằng update có thể thất bại sau khi các changeset trước đã được ghi nhận. Dùng lịch sử và metadata để hiểu trạng thái, không retry liên tục.

### Câu hỏi tự kiểm tra

- Vì sao update lần hai thường không chạy lại createTable? **Vì Liquibase nhận diện changeset đã ghi nhận bằng ID, AUTHOR và FILENAME.**
- Vì sao update-sql hữu ích nhưng chưa đủ cho production? **Vì điều kiện runtime, dữ liệu, quyền và các thay đổi đồng thời vẫn có thể làm kết quả khác.**
- DATABASECHANGELOGLOCK có ngăn mọi client sửa database không? **Không.** Nó điều phối các tiến trình Liquibase, không thay thế khóa DDL hoặc chính sách quyền.
- Nếu changeset C thất bại sau A/B thành công, update có tự rollback A/B không? **Không mặc định.**
- Tại sao không đổi nội dung changeset đã chạy? **Vì lịch sử, checksum và tính tái lập giữa môi trường.**
- Khi muốn thêm cột trên production, làm gì trước update? **Xác nhận kết nối, validate, status, SQL dự kiến, dữ liệu/phụ thuộc, quyền, kế hoạch rollback và tương thích ứng dụng.**

## 22. Checklist trước và sau mỗi lệnh update

**Trước khi chạy:**

- [ ] Changelog được đọc từ đúng commit/artifact phát hành.
- [ ] SERVICE_NAME và phạm vi module được hiểu rõ; chỉ những changeset thuộc release được chọn.
- [ ] URL, DBMS, database, schema, user và quyền đã được xác nhận.
- [ ] Credentials lấy từ nguồn an toàn, không lộ trong source hoặc log.
- [ ] Context, label, dbms và changelog parameters được đặt tường minh và được kiểm tra.
- [ ] Không chỉnh id/author/filename/nội dung changeset đã chạy.
- [ ] Đã chạy validate và xem status --verbose.
- [ ] Đã đọc update-sql với đúng cấu hình/DBMS.
- [ ] Đã kiểm tra trạng thái dữ liệu hiện hữu trước FK/UNIQUE/NOT NULL.
- [ ] Đã xem xét lock DDL, thời gian chạy và khả năng transaction/rollback.
- [ ] Đã phối hợp phiên bản ứng dụng để tránh thay đổi phá tương thích.
- [ ] Đã xác định job nào có quyền chạy migration và cơ chế khóa/điều phối.
- [ ] Đã có phương án rollback hoặc forward fix, backup nếu thay đổi có thể phá dữ liệu.

**Sau khi chạy:**

- [ ] Đã kiểm tra exit code, log và changeset thực sự được xử lý.
- [ ] DATABASECHANGELOG có ID/AUTHOR/FILENAME, EXECTYPE và MD5SUM phù hợp.
- [ ] Đã kiểm tra schema và dữ liệu thực tế; không chỉ dựa vào lịch sử.
- [ ] Đã xác nhận không có changeset ngoài phạm vi được chạy.
- [ ] Đã chạy smoke test hoặc integration test cho mã ứng dụng đang dùng schema mới.
- [ ] Các job, báo cáo, API hoặc dịch vụ phụ thuộc tiếp tục hoạt động.
- [ ] Đã lưu bằng chứng phát hành và các tham số không nhạy cảm.
- [ ] Nếu có lỗi, đã kiểm tra trạng thái từng phần trước khi quyết định retry/rollback.

**Kết luận:** `liquibase update` là bước thực thi thay đổi có lịch sử, không phải chỉ là câu lệnh chạy SQL. Sự an toàn đến từ việc hiểu **changeset nào đang chờ**, xác minh đúng database đích, review SQL và precondition, quản lý khóa và transaction, giữ bất biến các changeset đã phát hành và kiểm chứng kết quả bằng cả DATABASECHANGELOG lẫn schema/dữ liệu thật. Khi đưa update vào Spring Boot hoặc CI/CD, hãy xem nó như một bước phát hành độc lập có cổng kiểm soát, giám sát và kế hoạch rollback hoặc sửa tiến phù hợp.
