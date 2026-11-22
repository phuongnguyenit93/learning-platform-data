
# Changeset chạy lại ngoài dự kiến

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Bình thường, khi một changeset đã được ghi nhận trong lịch sử của database, những lần \`update\` tiếp theo sẽ bỏ qua changeset đó. Nếu một thay đổi cũ bất ngờ xuất hiện trong danh sách pending hoặc SQL preview cho thấy DDL/DML được thực thi lần nữa, cần xác định vì sao Liquibase không nhận ra lịch sử trước đó hoặc vì sao changeset được cấu hình để chạy lại.

Bài thuộc chương **Xử lý sự cố** này hướng dẫn chẩn đoán tình huống **changeset chạy lại ngoài dự kiến**. Trọng tâm là phân biệt định danh changeset với checksum, kiểm tra DATABASECHANGELOG và vị trí bảng lịch sử, tìm thay đổi ở \`id\`, \`author\`, \`filename\` hoặc \`logicalFilePath\`, đánh giá \`runAlways\` và \`runOnChange\`, context/label/precondition, rollback rồi reapply, nhiều database và tình huống thực thi một phần. Bài kết thúc bằng quy trình khoanh vùng, phục hồi và phòng ngừa trong Spring Boot/CI/CD.

Phạm vi được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Hành vi bình thường của Liquibase

Liquibase đọc changelog, xác định changeset áp dụng cho database đích và so sánh với lịch sử đã ghi nhận. Trong cấu hình thông thường, bảng **DATABASECHANGELOG** lưu các changeset đã được xử lý. Khi một changeset đã có bản ghi khớp định danh, Liquibase không chạy lại nó trong một lần update bình thường.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: customer-team
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

Sau khi changeset được thực thi thành công và lịch sử được ghi, những lần update sau sẽ xem changeset này là đã xử lý, miễn là Liquibase kết nối đúng database/history, nhận diện đúng identity và không có cấu hình yêu cầu chạy lại.

Nếu \`001-create-customer\` xuất hiện pending sau khi đã triển khai, đó là tín hiệu cần điều tra. Đừng chạy update để “thử xem có lỗi không”: câu lệnh có thể tạo lại bảng hoặc thực hiện DML lần nữa.

## 2. Phân biệt “pending”, “checksum mismatch” và “rerun”

Ba hiện tượng có cách xử lý khác nhau:

| Hiện tượng | Điều Liquibase đang báo hiệu | Rủi ro |
|---|---|---|
| **Pending** | Không tìm thấy bản ghi lịch sử khớp changeset identity trong history hiện tại | Changeset cũ có thể được thực thi như thay đổi mới |
| **Checksum mismatch** | Tìm thấy changeset đã ghi nhận nhưng checksum hiện tại không được chấp nhận | Validation có thể dừng update; không đồng nghĩa tự chạy lại |
| **Rerun** | Changeset được cấu hình hoặc được đưa trở lại trạng thái cần thực thi | SQL/DML có thể chạy thêm lần nữa |
| **History missing/wrong target** | Liquibase đang đọc một bảng lịch sử khác hoặc database khác | Nhiều changeset có thể xuất hiện pending hàng loạt |
| **Partial execution** | SQL đã tác động nhưng lịch sử chưa phản ánh đầy đủ | Retry có thể lặp lại một phần thay đổi |

Một thay đổi nội dung không mặc nhiên khiến changeset chạy lại. Với changeset thông thường, sửa nội dung đã triển khai thường dẫn đến checksum validation error. Các thuộc tính như \`runOnChange\` hoặc \`runAlways\` thay đổi hành vi thực thi theo cách riêng.

**Bước đầu tiên là phân loại đúng triệu chứng**, sau đó mới chọn cách xử lý.

## 3. Changeset identity: id, author và filename

Liquibase nhận diện một changeset thông thường bằng tổ hợp:

~~~text
id + author + filename
~~~

Trong đó:

- **id:** giá trị \`id\` khai báo trong changeset.
- **author:** giá trị \`author\` khai báo trong changeset.
- **filename:** đường dẫn changelog logic được Liquibase ghi nhận.

Ví dụ changeset:

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

Nếu một trong ba thành phần thay đổi sau khi changeset đã chạy, Liquibase có thể xem phiên bản hiện tại là một changeset mới. Row cũ trong DATABASECHANGELOG vẫn còn, nhưng bộ định danh mới không khớp row đó.

Đây là nguyên nhân phổ biến khiến changeset cũ xuất hiện pending và bị thực thi lần nữa dù nội dung SQL gần như giống hệt.

## 4. Đổi id sau khi triển khai

Giả sử database đã ghi nhận:

~~~yaml
- changeSet:
    id: 003-create-order
    author: order-team
    changes:
      - createTable:
          tableName: orders
          columns:
            - column:
                name: id
                type: bigint
                constraints:
                  primaryKey: true
                  nullable: false
~~~

Developer đổi id thành \`003-create-orders-table\` để tên dễ hiểu hơn. Liquibase không tự suy ra rằng hai id này là cùng một thay đổi. Changeset mới có thể xuất hiện pending.

Nếu chạy update, Liquibase có thể cố tạo lại bảng orders và DBMS báo table already exists. Với changeset insert, lỗi có thể là duplicate key; với update/delete, hậu quả có thể là dữ liệu bị thay đổi thêm lần nữa.

**Không đổi id của changeset đã triển khai chỉ để chỉnh tên.** Giữ id cũ trong lịch sử. Nếu cần thay đổi cấu trúc hoặc logic, tạo changeset mới với id mới và mục đích rõ ràng.

## 5. Đổi author cũng làm thay đổi identity

Author là metadata do nhóm phát triển khai báo, không phải danh tính đã được Liquibase xác thực của người chạy migration.

Ví dụ đổi:

~~~yaml
author: developer-a
~~~

thành:

~~~yaml
author: platform-team
~~~

dù id và SQL giữ nguyên, tổ hợp identity vẫn khác. Liquibase có thể coi đó là changeset mới.

Chọn author ổn định theo quy ước nhóm ngay từ đầu, chẳng hạn domain team hoặc platform team. Sau khi triển khai, không thay author hàng loạt để phản ánh người tiếp quản. Có thể ghi nhận ownership mới trong Git, pull request, release record hoặc comment của changeset mới.

## 6. Đổi tên hoặc di chuyển file làm thay đổi filename logic

Ví dụ changeset ban đầu nằm ở:

~~~text
db/changelog/changes/003-create-order.yaml
~~~

Sau đó file được chuyển sang:

~~~text
db/changelog/order/003-create-order.yaml
~~~

Nếu Liquibase ghi nhận đường dẫn mới khác FILENAME cũ, identity có thể thay đổi dù id và author không đổi.

Các trường hợp dễ gây ra thay đổi filename:

- Đổi tên file.
- Di chuyển file sang thư mục khác.
- Thay đổi cách include hoặc đường dẫn tương đối.
- Chuyển resource từ filesystem sang classpath/JAR.
- Khác biệt cách chuẩn hóa separator hoặc chữ hoa/chữ thường giữa môi trường.
- Dùng một master changelog mới trỏ tới bản sao file ở đường dẫn khác.

Trước khi tái cấu trúc, truy vấn FILENAME thực tế trong DATABASECHANGELOG của database đã triển khai. Nếu cần giữ đường dẫn logic cũ, xem xét \`logicalFilePath\` theo đúng phiên bản và định dạng Liquibase. Không đoán FILENAME từ đường dẫn hiển thị trong IDE.

## 7. logicalFilePath chỉ bảo toàn thành phần filename

\`logicalFilePath\` cho phép chỉ định đường dẫn logic mà Liquibase sử dụng trong định danh changeset, hữu ích khi di chuyển file nhưng muốn giữ identity cũ.

Ví dụ minh họa:

~~~yaml
databaseChangeLog:
  - logicalFilePath: db/changelog/changes/003-create-order.yaml
  - changeSet:
      id: 003-create-order
      author: order-team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Cú pháp, phạm vi áp dụng và khả năng kế thừa của logicalFilePath phụ thuộc phiên bản Liquibase và định dạng changelog. Cần xác minh với phiên bản dự án đang chạy và thử trên bản sao database có lịch sử thật.

logicalFilePath không sửa id hoặc author. Nếu hai thành phần đó cũng đổi, identity vẫn khác. Giá trị logic cần khớp chính xác FILENAME đã được ghi nhận, bao gồm quy tắc chuẩn hóa đường dẫn của môi trường.

## 8. Kiểm tra DATABASECHANGELOG trước khi sửa file

Bảng **DATABASECHANGELOG** là bằng chứng quan trọng nhất về identity mà Liquibase đã ghi nhận ở database đích.

Truy vấn tham khảo:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED,
    DESCRIPTION
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tên bảng, schema và tập cột chi tiết có thể khác theo cấu hình/phiên bản. Nếu dự án đặt history table trong schema riêng hoặc đổi tên bảng, hãy truy vấn đúng vị trí.

Đối với changeset nghi ngờ chạy lại, lọc theo ID và AUTHOR nhưng vẫn phải xem FILENAME. Chỉ tìm theo ID có thể trả về nhiều row. Đối chiếu cả ba thành phần identity với changelog hiện tại.

Không sửa trực tiếp ID, AUTHOR, FILENAME hoặc MD5SUM trong bảng history để “làm cho khớp”. Sửa tay có thể làm mất bằng chứng lịch sử và khiến update sau diễn giải sai trạng thái.

## 9. Kết nối nhầm database hoặc schema history

Một nguyên nhân nghiêm trọng là Liquibase kết nối đúng server nhưng sai database, catalog hoặc schema chứa bảng history.

Ví dụ:

- Release trước chạy trên \`customer_prod\`.
- Job hiện tại trỏ tới \`customer_staging\`.
- Cả hai cùng có schema tên \`customer\`.
- Database staging chưa có DATABASECHANGELOG tương ứng.

Liquibase có thể tạo bảng history mới và xem các changeset là pending. Điều này không có nghĩa production đã quên lịch sử; job đang nhìn một đích khác.

Các cấu hình cần xác minh:

- JDBC URL và database/catalog.
- Default schema.
- \`liquibaseSchemaName\` và schema của DATABASECHANGELOG.
- Tên DATABASECHANGELOG và DATABASECHANGELOGLOCK tùy chỉnh.
- User/session hiện tại.
- Master changelog và resource path.
- Target ID trong CI/CD.

Trước update, truy vấn thông tin database hiện tại bằng SQL phù hợp DBMS. Không chỉ dựa vào tên job hoặc biến environment hiển thị.

## 10. History table bị đổi tên, di chuyển hoặc mất

Nếu bảng DATABASECHANGELOG được chuyển schema, đổi tên hoặc không được truy cập, Liquibase có thể không tìm thấy lịch sử cũ. Một history table mới có thể được tạo ở vị trí mới tùy cấu hình và quyền.

Hệ quả:

- Nhiều changeset đã triển khai xuất hiện pending.
- SQL preview có thể chứa DDL/DML cũ.
- Pipeline có thể tưởng database mới được khởi tạo.
- Hai bộ history có thể cùng tồn tại ở hai schema.
- Các job dùng cấu hình khác nhau có thể quan sát lịch sử khác nhau.

Trước khi đổi vị trí history, phải lập kế hoạch chuyển bảng và cấu hình cùng nhau, giữ nguyên dữ liệu và xác minh tất cả runner dùng cùng location. Không drop history cũ để “dọn dẹp” cho đến khi đã xác minh mọi target và artifact.

Nếu history bị mất, ưu tiên phục hồi từ backup hoặc audit source đã được kiểm chứng. Không dùng changelog-sync trên production một cách hàng loạt để che việc mất lịch sử.

## 11. Checksum mismatch không đồng nghĩa changeset chạy lại

Liquibase lưu checksum (thường hiển thị trong cột MD5SUM) để phát hiện thay đổi nội dung changeset đã ghi nhận.

Khi identity vẫn khớp nhưng checksum hiện tại không được chấp nhận, Liquibase thường báo lỗi validation và dừng update đối với changeset đó. Nó không tự động chạy lại changeset thông thường chỉ vì checksum khác.

Cần phân biệt:

| Identity | Checksum | Hành vi thường gặp |
|---|---|---|
| Khớp | Khớp | Changeset đã xử lý được bỏ qua |
| Khớp | Không được chấp nhận | Checksum validation error |
| Khác | Không liên quan tới row cũ | Changeset mới có thể pending và chạy |
| Khớp + runOnChange | Thay đổi theo quy tắc checksum | Changeset có thể được chạy lại |
| Khớp + runAlways | Mỗi lần update thích hợp | Changeset được chạy lại theo cấu hình |

Checksum được tính theo quy tắc Liquibase và phiên bản, không nên coi là hash byte-for-byte đơn giản của toàn bộ file. Không tự tính MD5 của file rồi so trực tiếp với MD5SUM.

## 12. runOnChange: chủ động chạy lại khi nội dung thay đổi

\`runOnChange: true\` phù hợp với một số changeset định nghĩa đối tượng có thể thay thế, chẳng hạn view hoặc stored procedure, khi nhóm muốn thay đổi định nghĩa và để Liquibase chạy lại changeset đó khi checksum thay đổi theo quy tắc công cụ.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-refresh-active-customer-view
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

\`replaceIfExists\` và cách thay thế view phụ thuộc DBMS/phiên bản. Cần kiểm thử cả lần tạo đầu và lần cập nhật định nghĩa trên database thật hoặc clone tương đương.

Nếu changeset chứa INSERT, UPDATE hoặc thao tác không idempotent, runOnChange có thể gây hậu quả dữ liệu khi nội dung được sửa. Không bật thuộc tính này chỉ để “sửa checksum” hoặc tránh tạo changeset mới cho thay đổi nghiệp vụ.

## 13. runAlways: changeset được thực thi trong mỗi lần update thích hợp

\`runAlways: true\` yêu cầu Liquibase chạy changeset trong các lần update thích hợp, ngay cả khi changeset đã có bản ghi lịch sử. Đây là hành vi chủ động, không phải lỗi nhận diện.

Một số use case có thể cần tác vụ lặp lại như cập nhật một đối tượng được quản lý thường xuyên hoặc thực hiện một thao tác được thiết kế an toàn khi chạy nhiều lần. Tuy nhiên, phải bảo đảm câu lệnh có tính idempotent hoặc có điều kiện rõ ràng.

Ví dụ minh họa một thao tác thiết lập giá trị chuẩn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-ensure-system-setting
      author: platform-team
      runAlways: true
      changes:
        - sql:
            sql: |
              UPDATE system_setting
              SET value = 'enabled'
              WHERE setting_key = 'new-search'
                AND value <> 'enabled'
~~~

Ví dụ chỉ phù hợp nếu bảng và khóa đã tồn tại, câu lệnh đúng DBMS và việc ép giá trị về enabled ở mọi lần update là chủ đích. Không dùng runAlways cho DML cộng dồn, insert không kiểm soát hoặc thao tác gửi side effect.

Khi thấy changeset xuất hiện lại trong log mỗi lần update, kiểm tra runAlways trước khi kết luận identity/history bị lỗi.

## 14. Phân biệt runAlways và runOnChange

| Thuộc tính | Điều kiện chạy lại | Use case thường gặp | Rủi ro |
|---|---|---|---|
| Không khai báo | Chỉ chạy khi chưa có identity trong history | Migration một lần | Sửa identity có thể khiến nó bị xem là mới |
| runOnChange | Chạy lại khi checksum thay đổi theo quy tắc | View/procedure được quản lý theo định nghĩa | Sửa nội dung có thể kích hoạt DDL lại |
| runAlways | Chạy trong mỗi lần update thích hợp | Tác vụ lặp lại có chủ đích | DML/side effect lặp lại |
| runAlways + runOnChange | Có hành vi kết hợp theo semantics phiên bản | Chỉ khi có lý do cụ thể | Khó dự đoán nếu không kiểm thử |

Đừng bật cả hai thuộc tính theo thói quen. Hãy đọc tài liệu đúng phiên bản và thử hành vi với một changeset mẫu trên database disposable.

Nếu một migration chỉ cần chạy một lần, hãy giữ mặc định và tạo changeset mới cho thay đổi tiếp theo. Đừng dùng runAlways để bù cho quy trình phát hành thiếu lịch sử.

## 15. MARK_RAN: changeset được ghi nhận mà không thực thi changes

Precondition có thể được cấu hình \`onFail: MARK_RAN\`. Khi điều kiện không đạt theo semantics của precondition, Liquibase có thể đánh dấu changeset là đã xử lý mà không chạy nội dung changes.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 006-baseline-existing-customer-archive
      author: database-team
      preConditions:
        - onFail: MARK_RAN
        - not:
            - tableExists:
                tableName: customer_archive
      changes:
        - createTable:
            tableName: customer_archive
            columns:
              - column:
                  name: id
                  type: bigint
~~~

Trong ví dụ, nếu bảng customer_archive đã tồn tại thì điều kiện not/tableExists không đạt và Liquibase đánh dấu changeset là MARK_RAN mà không chạy createTable. Trước khi dùng cách này, phải xác minh bảng hiện có đúng cấu trúc, constraint, index và dữ liệu mà baseline yêu cầu; tableExists đơn thuần chỉ kiểm tra sự tồn tại, không chứng minh các thuộc tính đó tương đương.

MARK_RAN có thể làm changeset không chạy SQL như người vận hành kỳ vọng, nhưng vẫn được ghi nhận trong history. Khi kiểm tra EXECTYPE, cần phân biệt MARK_RAN với EXECUTED. Không dùng MARK_RAN để che một migration chưa hoàn tất hoặc để dập danh sách pending mà không xác minh schema/data.

## 16. Context và label làm thay đổi tập changeset được xét

Liquibase có thể lọc changeset bằng **context**, **label** và thuộc tính DBMS. Một changeset không xuất hiện trong một lần chạy có thể chưa được xét vì filter, chứ không nhất thiết đã chạy hoặc bị mất lịch sử.

Những điều cần kiểm tra:

- Changeset có khai báo context/label không?
- Lệnh update truyền context/label filter nào?
- Cú pháp filter của phiên bản Liquibase đang dùng là gì?
- Có profile Spring Boot hoặc property môi trường ghi đè filter không?
- Job preview và job update có dùng cùng filter không?
- Changeset có \`dbms\` giới hạn database không?

Một filter sai có thể khiến changeset cần thiết bị bỏ qua trong môi trường này, rồi xuất hiện pending trong một lần deploy sau với filter khác. Ngược lại, bỏ filter có thể làm chạy thêm changeset chỉ dành cho môi trường khác.

Không coi context/label là cơ chế phân quyền hoặc thay thế việc tách changelog. Ghi rõ filter trong release record và dùng cùng cấu hình cho status, SQL preview và update.

## 17. include/includeAll và việc nạp cùng changeset nhiều lần

Master changelog có thể dùng \`include\` hoặc \`includeAll\` để nạp các file con. Việc tái cấu trúc include hoặc thêm bản sao file có thể khiến một changeset được nạp với filename logic khác.

Ví dụ:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Nếu file được copy sang folder mới và include bằng path mới, cùng id/author nhưng filename khác có thể tạo identity mới. Với includeAll, thứ tự và tập file được nạp có thể thay đổi khi thêm/di chuyển file.

Kiểm tra master changelog thực tế được dùng trong artifact, không chỉ file trên working tree. Trước khi đổi include, chạy validate/status và xem SQL preview trên database clone có lịch sử cũ.

## 18. Rollback rồi update lại: chạy lại có thể là hành vi đúng

Khi Liquibase rollback một changeset thành công trong phạm vi được chọn, lịch sử changeset tương ứng có thể được điều chỉnh để nó không còn được xem là đã áp dụng theo trạng thái hiện tại. Nếu sau đó chạy update, changeset có thể được thực thi lại vì nó trở thành pending.

Đây không nhất thiết là bug. Đó là vòng đời rollback/reapply.

Cần kiểm tra:

- Có release hoặc operator vừa chạy rollback không?
- Rollback tới tag/count/date nào?
- Changeset identity nào đã bị rollback?
- Rollback SQL có thực sự hoàn tất không?
- Dữ liệu được tạo sau migration có bị xóa không?
- Update tiếp theo có dùng cùng revision changelog không?

Không nhầm việc reapply sau rollback có chủ đích với việc changeset tự nhiên chạy lại trong một update bình thường. Nếu mục tiêu là giữ thay đổi schema nhưng sửa logic, forward fix bằng changeset mới thường phù hợp hơn rollback rồi sửa file cũ.

## 19. clearCheckSums không làm changeset thông thường chạy lại

Lệnh \`clear-checksums\` xóa checksum đã lưu trong DATABASECHANGELOG để Liquibase tính lại checksum trong lần chạy thích hợp tiếp theo.

~~~text
liquibase clear-checksums
~~~

Cú pháp có thể khác theo CLI/plugin/version. Lệnh này:

- Không đổi id.
- Không đổi author.
- Không đổi filename.
- Không phục hồi row history đã xóa.
- Không tự chạy lại mọi changeset đã được ghi nhận.
- Không sửa schema hoặc dữ liệu.
- Không giải quyết identity mismatch.

Nếu identity vẫn khớp, việc tính lại checksum không đồng nghĩa changeset thường sẽ chạy lại. Tuy nhiên, với runOnChange hoặc các trường hợp checksum được chấp nhận khác nhau, hành vi có thể khác; cần kiểm thử trước.

Không dùng clearCheckSums như nút “reset Liquibase”. Chỉ chạy khi có lý do rõ, biết ảnh hưởng tới toàn bộ checksum được quản lý và có phê duyệt.

## 20. validCheckSum chỉ xử lý việc chấp nhận checksum

\`validCheckSum\` có thể cho phép một changeset chấp nhận một checksum cũ/cụ thể đã được xác minh, tùy phiên bản và cấu hình.

Ví dụ minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 007-create-report-view
      author: reporting-team
      validCheckSum:
        - "8:previous-checksum-value"
      changes:
        - createView:
            viewName: v_customer_report
            selectQuery: SELECT id, email FROM customer
~~~

Chuỗi checksum là placeholder, không dùng nguyên văn. Phải lấy checksum thực tế từ thông báo Liquibase hoặc history và xác minh lý do chấp nhận.

validCheckSum không sửa identity, không bảo toàn filename khi di chuyển file, không làm changeset mới trở thành changeset cũ và không chứng minh schema đúng. Tránh chấp nhận mọi checksum bằng wildcard nếu không có chính sách kiểm soát chặt, vì điều đó có thể che thay đổi ngoài dự kiến.

## 21. runInTransaction và thay đổi một phần

Liquibase thường cố gắng thực thi changeset trong transaction nếu DBMS và loại lệnh hỗ trợ. Tuy nhiên, một số DDL có implicit commit hoặc không thể chạy trong transaction; \`runInTransaction: false\` cũng cho phép changeset chạy ngoài transaction.

Khi job lỗi, có thể xảy ra:

- SQL đã thay đổi schema nhưng DATABASECHANGELOG chưa ghi nhận changeset.
- Một phần statement trong changeset đã chạy.
- Kết nối bị mất sau khi DBMS thực thi nhưng trước khi client nhận kết quả.
- Liquibase lock còn lại do process bị dừng bất thường.
- Retry gặp object already exists hoặc duplicate key.

Không giả định exit code non-zero có nghĩa database không thay đổi gì. Trước retry, kiểm tra schema, data, DBMS session và DATABASECHANGELOG.

Với thay đổi lớn hoặc khó rollback, tách thành changeset nhỏ, có precondition rõ, kiểm thử transaction behavior trên đúng DBMS và có recovery plan.

## 22. Nhiều database: history của từng target độc lập

Một changeset đã chạy trên database A không tự được ghi nhận trên database B. Mỗi target có DATABASECHANGELOG riêng (theo cấu hình history tương ứng).

Các nguyên nhân khiến changeset chỉ chạy lại ở một số môi trường:

- URL trỏ nhầm database.
- Schema history khác nhau.
- Một môi trường bị restore từ backup cũ.
- Bảng DATABASECHANGELOG bị đổi vị trí hoặc tạo mới.
- Changelog artifact khác revision.
- File path hoặc logicalFilePath khác giữa môi trường.
- Một lần deploy trước thất bại hoặc chỉ chạy ở một phần target.

Khi một changeset xuất hiện pending ở production nhưng không pending ở staging, so sánh identity, FILENAME, history location và artifact revision của từng database. Không suy luận trạng thái production từ staging.

## 23. Spring Boot startup và nhiều instance

Nếu Spring Boot bật Liquibase lúc startup, nhiều replica có thể cùng khởi tạo Liquibase. Các process sử dụng cùng DATABASECHANGELOGLOCK sẽ được điều phối qua bảng khóa, nhưng vẫn có thể tạo startup delay và log cạnh tranh.

Nếu một process dùng history schema khác, hoặc một deployment dùng changelog path khác, chúng có thể không chia sẻ cùng identity/lock. Vì vậy cần xác minh:

- \`spring.liquibase.enabled\`.
- \`spring.liquibase.change-log\`.
- Datasource/URL và default schema.
- Tên/schema history và lock table.
- Liquibase version trong từng artifact.
- Context/label/DBMS filter.
- Pod/runner nào thực sự chạy migration.

Trong production nhiều replica, migration job riêng thường giúp có một migration owner rõ ràng. Khi pipeline là owner, tắt startup auto-run trong runtime profile phù hợp và bảo đảm mọi replica dùng cùng release revision.

## 24. Chẩn đoán bằng status, history, validate và SQL preview

Một chuỗi kiểm tra điển hình:

~~~text
liquibase status --verbose
liquibase history
liquibase validate
liquibase update-sql
~~~

Các lệnh và option có thể khác theo phiên bản CLI/plugin. Dùng đúng connection profile, changelog master, context/label và target.

- **status:** xem changeset pending theo database/filter hiện tại.
- **history:** xem lịch sử migration được Liquibase hỗ trợ trong phiên bản đang dùng.
- **validate:** kiểm tra cấu trúc changelog và một số vấn đề tham chiếu/checksum.
- **update-sql:** sinh SQL dự kiến mà không thực thi migration.

SQL preview là bằng chứng quan trọng: nếu một createTable cũ xuất hiện trong updateSQL, dừng trước update và tìm identity/history mismatch. Nếu changeset không pending nhưng có log chạy lại, kiểm tra runAlways/runOnChange và lịch sử EXECTYPE.

Không chỉ nhìn dashboard tổng hợp. Lấy log chi tiết của đúng target và đúng artifact.

## 25. Đối chiếu schema thực tế với changelog

Nếu identity/history cho thấy changeset đã chạy nhưng schema không đúng, có thể database đã drift hoặc migration trước chỉ thực hiện một phần.

Kiểm tra:

- Bảng/cột có tồn tại không?
- Kiểu dữ liệu, nullable, default có đúng không?
- Index có đúng cột, thứ tự, uniqueness và predicate không?
- Constraint có được tạo và validate không?
- View/procedure/function có đúng định nghĩa không?
- Dữ liệu có đạt invariant không?
- Có DBA hotfix hoặc công cụ ngoài Liquibase sửa object không?

Có thể dùng metadata của DBMS hoặc công cụ diff/reference database phù hợp để so sánh. Không chạy changelog-sync hoặc MARK_RAN chỉ vì object cùng tên tồn tại; phải xác minh định nghĩa và dữ liệu tương đương.

## 26. Quy trình xử lý khi changeset cũ xuất hiện pending

**Bước 1 — Dừng:** không chạy update và không sửa history.

**Bước 2 — Xác minh target:** database, schema, connection profile, history table và lock table.

**Bước 3 — So sánh identity:** id, author, filename/logicalFilePath trong file hiện tại với DATABASECHANGELOG.

**Bước 4 — Kiểm tra artifact:** commit SHA, changelog master, include path, context/label/dbms và Liquibase version.

**Bước 5 — Phân loại checksum:** identity có khớp không; nếu khớp, checksum có mismatch không; có runOnChange/runAlways không?

**Bước 6 — Kiểm tra lịch sử:** có rollback, restore, changelog-sync, MARK_RAN hoặc chỉnh history gần đây không?

**Bước 7 — Kiểm tra thực tế:** schema/data đã có thay đổi chưa, có DDL autocommit hay partial execution không?

**Bước 8 — Preview:** chạy status/updateSQL trên đúng target sau khi đã xác định cấu hình.

**Bước 9 — Chọn phục hồi:** khôi phục identity/history location, tạo changeset sửa tiếp, forward fix hoặc restore theo runbook.

**Bước 10 — Hậu kiểm:** xác nhận changeset không còn pending ngoài ý muốn và schema/data đạt invariant.

## 27. Cách xử lý theo nguyên nhân

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Đổi id/author | Bộ ba identity khác history | Khôi phục identity cũ; thay đổi mới tạo changeset mới |
| Di chuyển file | FILENAME khác | Xác minh logicalFilePath và resource path |
| Kết nối nhầm DB | Target fingerprint sai | Dừng job, sửa connection mapping |
| History table sai vị trí | Không tìm thấy row cũ | Khôi phục cấu hình/location history đã quản lý |
| runAlways | Changeset chạy mỗi update | Xác nhận chủ đích; làm thao tác idempotent hoặc sửa thiết kế cho thay đổi mới |
| runOnChange | Checksum thay đổi và changeset chạy lại | Review nội dung mới, xác nhận đây là hành vi mong muốn |
| Rollback/reapply | Row history đã bị rollback | Xác nhận phạm vi rollback và dữ liệu trước khi update |
| MARK_RAN | EXECTYPE cho thấy đã đánh dấu | Xác minh precondition và trạng thái object |
| Partial execution | Object/data đã đổi nhưng history thiếu | Reconcile thực tế, không retry mù quáng |
| Restore database | History quay về snapshot cũ | Đối chiếu thời điểm backup và changeset sau backup |
| Context/label khác | Filter làm tập changeset thay đổi | Đồng nhất filter giữa preview và update |
| Hai tool cùng chạy | SQL/log từ nhiều runner | Thiết lập single-writer và migration owner |

Không có một lệnh “fix rerun” áp dụng cho tất cả nguyên nhân. Phải sửa đúng nguyên nhân gốc.

## 28. Phòng ngừa changeset chạy lại ngoài dự kiến

- Giữ ổn định id, author và filename logic sau khi triển khai.
- Không di chuyển changelog lịch sử nếu chưa có kế hoạch logicalFilePath.
- Ghim cùng artifact/revision qua dev, test, staging và production.
- Không sửa changeset đã chạy; tạo changeset mới cho thay đổi mới.
- Dùng runOnChange chỉ cho đối tượng có thể thay thế và đã kiểm thử.
- Dùng runAlways chỉ khi thực sự cần chạy mỗi lần update.
- Thiết kế DML idempotent, có khóa duy nhất và điều kiện WHERE rõ.
- Giữ một migration owner cho mỗi database/history.
- Không để Flyway, Spring Boot startup và CI/CD cùng thay đổi schema ngoài chính sách.
- Bảo vệ DATABASECHANGELOG và DATABASECHANGELOGLOCK khỏi sửa tay.
- Lưu history/backup và log triển khai theo chính sách retention.
- Chạy status/updateSQL trong pipeline trước production.
- Kiểm tra target, schema history, context/label và DBMS filter.
- Diễn tập rollback/reapply và partial failure trên database clone.
- Theo dõi pending changeset bất thường như một release gate.

## 29. Bài thực hành: tái hiện và chẩn đoán identity mismatch

Thực hiện trên database disposable, không dùng production.

### Bước 1 — Tạo và triển khai changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-product
      author: lab-team
      changes:
        - createTable:
            tableName: lab_product
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Chạy update, sau đó truy vấn DATABASECHANGELOG và lưu ID, AUTHOR, FILENAME, MD5SUM.

### Bước 2 — Đổi id trên bản thử nghiệm

Đổi id thành \`lab-001-create-products\`, giữ nguyên author, filename và SQL. Chạy status. Quan sát changeset có thể xuất hiện pending vì identity mới. Không chạy update vì nó có thể cố tạo lại bảng.

### Bước 3 — Khôi phục id, đổi author

Đổi author thành \`platform-lab\`. Chạy status và đối chiếu. Kết quả minh họa việc author cũng là một phần identity.

### Bước 4 — Khôi phục identity, di chuyển file

Di chuyển file vào folder mới trên bản thử nghiệm. Kiểm tra FILENAME và status. Thử logicalFilePath phù hợp với phiên bản Liquibase để bảo toàn đường dẫn cũ, sau đó xác minh changeset không còn pending ngoài ý muốn.

### Bước 5 — Thử checksum mismatch

Giữ identity, thay đổi nội dung được checksum theo dõi. Chạy validate/update trên clone và quan sát lỗi checksum validation của changeset thông thường. Không dùng clearCheckSums để che kết quả.

### Bước 6 — Thử runOnChange và runAlways

Tạo hai changeset độc lập trên database disposable: một changeset view dùng runOnChange, một changeset thao tác idempotent dùng runAlways. Chạy update nhiều lần, ghi nhận log/EXECTYPE và số lần SQL thực thi. Xác nhận mỗi thuộc tính tạo hành vi khác nhau.

### Bước 7 — Khôi phục và viết kết luận

Trả file changelog về revision đã được kiểm chứng hoặc tạo database disposable mới. Ghi lại nguyên nhân, dấu hiệu, cách phòng ngừa và bằng chứng. Không sửa trực tiếp DATABASECHANGELOG.

## 30. Checklist khi điều tra changeset chạy lại

- [ ] Đã dừng update trước khi xác định nguyên nhân.
- [ ] Đã xác minh đúng target, database/catalog, schema và connection profile.
- [ ] Đã xác nhận đúng DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- [ ] Đã so sánh id, author và filename/logicalFilePath.
- [ ] Đã phân biệt pending với checksum validation error.
- [ ] Đã kiểm tra runAlways và runOnChange.
- [ ] Đã kiểm tra context, label và dbms filter.
- [ ] Đã xem precondition, onFail và EXECTYPE MARK_RAN.
- [ ] Đã kiểm tra có rollback/reapply, restore hoặc changelog-sync gần đây không.
- [ ] Đã xác minh artifact revision và master/include paths.
- [ ] Đã kiểm tra nhiều database có history độc lập hay không.
- [ ] Đã đối chiếu schema/data thực tế và phát hiện partial execution.
- [ ] Đã xem log, pipeline, Pod/process và DBMS session liên quan.
- [ ] Không sửa tay DATABASECHANGELOG hoặc DATABASECHANGELOGLOCK.
- [ ] Không dùng clearCheckSums/validCheckSum để che identity mismatch.
- [ ] Đã chạy status, validate và updateSQL với cùng target/filter.
- [ ] Đã chọn khôi phục identity, changeset mới, forward fix hoặc restore theo nguyên nhân.
- [ ] Đã thử cách xử lý trên database clone.
- [ ] Đã xác minh changeset không còn pending ngoài dự kiến.
- [ ] Đã lưu incident/release record và biện pháp ngăn tái diễn.

**Ghi nhớ:** Changeset chạy lại ngoài dự kiến thường bắt nguồn từ việc Liquibase không tìm thấy đúng identity trong DATABASECHANGELOG, history/target bị lệch, changeset được cấu hình runAlways/runOnChange, hoặc migration đã rollback/thi hành một phần. **Identity là id + author + filename; checksum là kiểm tra nội dung.** Hãy dừng trước update, xác minh đúng database và bảng history, so sánh identity/filter/configuration, rồi kiểm tra schema và dữ liệu thực tế. Không xóa history hoặc retry mù quáng. Tạo changeset mới cho thay đổi mới, giữ identity cũ ổn định và dùng status/SQL preview cùng hậu kiểm để bảo vệ lịch sử migration qua các môi trường.

