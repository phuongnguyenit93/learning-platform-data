# Vai trò và hệ quả của clear-checksums

## 1. Bối cảnh và mục tiêu

Liquibase dùng **checksum** để kiểm tra tính nhất quán giữa nội dung changeset trong changelog và lịch sử triển khai được lưu trong database. Khi một changeset đã chạy bị chỉnh sửa, checksum hiện tại có thể khác giá trị đã ghi trong **DATABASECHANGELOG**. Liquibase thường báo lỗi validation để cảnh báo lịch sử migration đã thay đổi.

Lệnh **clear-checksums** là một thao tác quản trị cho phép xóa các checksum đã lưu trong bảng lịch sử của database đích. Ở lần chạy update tiếp theo, Liquibase tính lại checksum từ changelog hiện tại và ghi lại các giá trị mới. Lệnh này hữu ích trong một số tình huống bảo trì hoặc nâng cấp, nhưng nếu dùng sai có thể **xóa dấu hiệu phát hiện changeset lịch sử đã bị sửa** mà không đưa schema database về đúng trạng thái của nội dung mới.

Bài thuộc chương **Checksum và lịch sử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **vai trò và hệ quả của clear-checksums**: hiểu chính xác lệnh tác động lên đâu, khi nào có thể cân nhắc, những gì lệnh không làm và cách vận hành an toàn trên dev, test, production.

Sau bài học, bạn cần có thể:

1. Giải thích checksum liên kết changeset với lịch sử DATABASECHANGELOG như thế nào.
2. Mô tả clear-checksums thay đổi trường nào và tác động tới lần update kế tiếp.
3. Phân biệt clear-checksums với rollback, changelogSync, markNextChangeSetRan và validCheckSum.
4. Nhận diện trường hợp checksum mismatch do chỉnh sửa lịch sử, sai đường dẫn changelog, thay đổi phiên bản hoặc cấu hình khác.
5. Lập quy trình kiểm tra trước/sau khi xóa checksum, bảo vệ đúng database và tránh chạy đồng thời.
6. Hiểu vì sao clear-checksums không phải cách sửa schema drift, không tự chạy lại toàn bộ migration và không khôi phục dữ liệu.
7. Xây dựng chính sách sử dụng lệnh trong CI/CD và quy trình phát hành có phê duyệt.

## 2. Checksum và bảng DATABASECHANGELOG

### 2.1. Changeset có danh tính và lịch sử

Một changeset thường được Liquibase nhận diện qua tổ hợp:

- **id**: định danh do người viết changelog đặt.
- **author**: tác giả hoặc nhóm chịu trách nhiệm.
- **Đường dẫn changelog**: vị trí tệp chứa changeset, có thể được chuẩn hóa bằng logicalFilePath theo thiết kế.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform-team
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(150)
~~~

Khi changeset được thực thi, Liquibase ghi lịch sử vào bảng **DATABASECHANGELOG**. Bảng này thường có các thông tin như ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE, MD5SUM và mô tả thay đổi, tùy phiên bản/cấu hình.

**DATABASECHANGELOG là lịch sử thực thi**, không phải bản sao đầy đủ của schema hoặc nội dung SQL cũ. Muốn khôi phục chính xác một định nghĩa đã triển khai, nhóm vẫn cần Git, artifact phát hành, bản sao lưu hoặc nguồn lưu trữ tương ứng.

### 2.2. Checksum có vai trò gì?

Liquibase tính checksum từ nội dung changeset theo quy tắc của phiên bản công cụ. Giá trị được lưu trong cột **MD5SUM** của DATABASECHANGELOG. Mặc dù tên cột có chữ MD5, không nên hiểu đây là hash của toàn bộ file changelog theo cách một công cụ checksum tệp thông thường làm.

Checksum phục vụ việc phát hiện một changeset đã ghi nhận có nội dung khác với nội dung hiện tại mà Liquibase đang đọc. Nó không chứng minh rằng:

- Database đang có đúng mọi đối tượng mà changelog mô tả.
- Không có DBA hoặc ứng dụng sửa schema thủ công.
- Dữ liệu nghiệp vụ chưa bị thay đổi.
- SQL đã chạy trên mọi môi trường đều tạo ra kết quả giống nhau.
- Một changeset đã được review hoặc an toàn để chạy lại.

Checksum là một phần của cơ chế kiểm tra lịch sử; cần kết hợp metadata database, kiểm tra schema/dữ liệu và quy trình quản lý mã nguồn.

### 2.3. Trạng thái minh họa

Giả sử changeset 001-create-customer đã chạy trên database shop_test:

| Thuộc tính | Giá trị minh họa |
|---|---|
| ID | 001-create-customer |
| AUTHOR | platform-team |
| FILENAME | db/changelog/customer.yaml |
| EXECTYPE | EXECUTED |
| MD5SUM | 9:abc... (giá trị minh họa, không phải checksum thực) |

Nếu nội dung changeset bị sửa sau khi đã chạy, checksum tính từ changelog hiện tại có thể khác giá trị đã lưu. Liquibase có thể báo **checksum validation failed** và dừng update, tùy loại changeset và quy tắc tương thích.

Lỗi này là một cảnh báo cần điều tra. Không nên xem nó như một trở ngại phải xóa đi để pipeline tiếp tục.

## 3. clear-checksums thực hiện điều gì?

Lệnh CLI:

~~~bash
liquibase --defaults-file=liquibase.properties clear-checksums
~~~

Ở mức khái quát, clear-checksums:

1. Kết nối tới database được xác định bởi cấu hình Liquibase hiện tại.
2. Xóa giá trị checksum đã lưu trong **MD5SUM** của các bản ghi phù hợp trong DATABASECHANGELOG tại database đó.
3. Không xóa bản ghi lịch sử changeset.
4. Không chạy lại câu lệnh SQL của các changeset đã thực thi chỉ vì checksum bị xóa.
5. Để lần chạy update tiếp theo tính lại checksum từ changelog đang được sử dụng và ghi giá trị mới.

Tên lệnh, cách xác định database/schema metadata và hành vi chi tiết cần được kiểm tra theo phiên bản Liquibase đang chạy. Điều quan trọng là phạm vi của thao tác: **clear-checksums tác động tới checksum lịch sử của database đích, không phải chỉ một dòng changeset do người vận hành chọn**.

### 3.1. Trước và sau khi clear-checksums

Trạng thái trước:

| ID | EXECTYPE | MD5SUM |
|---|---|---|
| 001-create-customer | EXECUTED | 9:abc... |
| 002-add-customer-email | EXECUTED | 9:def... |
| 003-create-customer-view | EXECUTED | 9:ghi... |

Sau clear-checksums, minh họa:

| ID | EXECTYPE | MD5SUM |
|---|---|---|
| 001-create-customer | EXECUTED | NULL |
| 002-add-customer-email | EXECUTED | NULL |
| 003-create-customer-view | EXECUTED | NULL |

Các bản ghi vẫn còn. Thông tin về ID, author, file, thời điểm và loại thực thi không bị xóa chỉ bởi thao tác clear checksum. Giá trị NULL cho biết checksum chưa được ghi lại; ở lần update kế tiếp, Liquibase có thể tính lại theo changelog hiện tại.

**Không nhầm “checksum bị xóa” với “changeset bị xóa”.** Hai thao tác có ý nghĩa hoàn toàn khác nhau.

### 3.2. Điều gì không xảy ra?

clear-checksums **không**:

- Xóa các hàng khỏi DATABASECHANGELOG.
- Xóa hoặc tạo lại bảng DATABASECHANGELOG.
- Tự động rollback thay đổi schema/dữ liệu.
- Tự động chạy lại tất cả changeset đã được đánh dấu EXECUTED.
- Sửa nội dung changelog trong Git.
- Sửa cột, bảng, constraint, view, function hoặc index đang sai trong database.
- Đồng bộ database drift với changelog.
- Tự giải phóng DATABASECHANGELOGLOCK.
- Xác minh database đang kết nối là dev, test hay production.
- Làm cho một changeset bị sửa trở nên an toàn hoặc đúng về nghiệp vụ.

Do đó, lệnh này không phải cách thay thế cho migration mới, rollback hoặc quy trình phục hồi.

## 4. Điều gì xảy ra ở lần update kế tiếp?

Sau khi checksum đã bị xóa, Liquibase đọc changelog và tính lại checksum theo quy tắc công cụ. Các changeset đã được ghi nhận trong lịch sử vẫn được nhận diện là đã chạy; lệnh clear-checksums không xóa trạng thái EXECUTED để biến chúng thành pending changeset.

Ví dụ đơn giản:

1. Changeset 001-create-customer đã tạo bảng customer.
2. Bản ghi lịch sử còn trong DATABASECHANGELOG.
3. clear-checksums đặt MD5SUM thành NULL.
4. Lần update tiếp theo tính checksum từ nội dung changelog hiện tại và cập nhật giá trị checksum.
5. Changeset thông thường đã chạy không tự chạy lại chỉ vì MD5SUM từng bị xóa.

Tuy nhiên, các loại changeset có hành vi riêng như **runOnChange** và **runAlways**, cùng khác biệt giữa các phiên bản Liquibase, cần được xem xét riêng. Không dùng clear-checksums làm cơ chế điều khiển chạy lại; hãy thử trên bản sao database và phiên bản công cụ chính xác trước khi dùng trong hệ thống có các changeset đặc biệt.

### 4.1. Vì sao việc tính lại có thể che giấu một chỉnh sửa nguy hiểm?

Giả sử changeset cũ đã tạo bảng customer:

~~~yaml
- changeSet:
    id: 001-create-customer
    author: platform-team
    changes:
      - createTable:
          tableName: customer
          columns:
            - column:
                name: customer_id
                type: BIGINT
                constraints:
                  primaryKey: true
~~~

Sau khi đã chạy trên production, một người sửa changeset lịch sử để thêm cột internal_flag. Database production chưa có cột này vì changeset cũ chỉ tạo customer_id.

Nếu người vận hành chạy clear-checksums rồi update, Liquibase có thể tính lại và ghi checksum mới cho nội dung đã sửa, trong khi changeset cũ vẫn được ghi nhận là đã chạy. **Việc tính lại checksum không đồng nghĩa lệnh CREATE TABLE được chạy lại để thêm cột internal_flag.**

Kết quả nguy hiểm: checksum mới được chấp nhận, nhưng schema thực tế vẫn không có cột mà changelog hiện tại mô tả. Lịch sử mất tín hiệu cảnh báo về việc thay đổi changeset cũ.

Cách xử lý đúng trong trường hợp này thường là khôi phục changeset lịch sử về nội dung đã phát hành và tạo **changeset mới** để thêm cột.

## 5. Khi nào có thể cân nhắc clear-checksums?

Đây là thao tác bảo trì có phạm vi ảnh hưởng rộng. Chỉ cân nhắc khi đã xác định nguyên nhân và có lý do được tài liệu/phiên bản Liquibase hỗ trợ.

Một số tình huống có thể cần đánh giá:

### 5.1. Bảo trì checksum sau thay đổi phiên bản Liquibase

Một lần nâng cấp Liquibase có thể liên quan tới thay đổi cách xử lý hoặc phiên bản checksum. Công cụ thường có cơ chế tương thích và nâng cấp checksum riêng; không nên mặc định mọi lần nâng phiên bản đều cần clear-checksums.

Trước khi chạy, hãy:

- Đọc hướng dẫn nâng cấp của đúng phiên bản nguồn và đích.
- Kiểm tra thông báo checksum thực tế.
- Xác định đó là lỗi nội dung changeset hay thay đổi thuật toán/định dạng checksum.
- Thử trên bản sao database có DATABASECHANGELOG tương đương.
- Chỉ thực hiện clear-checksums khi hướng dẫn của phiên bản hoặc kế hoạch vận hành yêu cầu.

### 5.2. Tính lại checksum sau một thay đổi có chủ đích được phê duyệt

Một tổ chức có thể có trường hợp đặc biệt cần tái lập checksum cho lịch sử hiện tại. Trước khi dùng, phải xác định:

- Những changeset nào đã được áp dụng.
- Nội dung hiện tại có tương ứng với schema/dữ liệu thực tế không.
- Việc chấp nhận checksum mới có làm mất cảnh báo thay đổi lịch sử hay không.
- Các môi trường khác sẽ được xử lý theo cùng một chính sách nào.

Nếu mục tiêu chỉ là thay đổi cấu trúc database, **hãy tạo changeset mới**. Không nên clear-checksums để chấp nhận chỉnh sửa lịch sử rồi hy vọng database tự nhận thay đổi.

### 5.3. Thao tác theo runbook sau khi database được kiểm tra

Nếu DBA/SRE có runbook bảo trì checksum cho một database cụ thể, lệnh có thể nằm trong quy trình đó. Runbook phải nêu rõ database/schema đích, người phê duyệt, bản backup lịch sử, điều kiện không có migration đồng thời và cách hậu kiểm.

Việc “pipeline đang báo đỏ” hoặc “muốn bỏ lỗi checksum để deploy tiếp” **không phải lý do đủ**.

## 6. Khi nào không nên dùng?

| Tình huống | Vì sao clear-checksums không giải quyết đúng vấn đề | Hướng xử lý phù hợp hơn |
|---|---|---|
| Sửa changeset đã chạy để thêm cột | Tính lại checksum không tự chạy ALTER TABLE | Khôi phục changeset cũ và tạo changeset mới |
| Database thiếu bảng dù lịch sử ghi EXECUTED | Đây là schema drift hoặc thao tác thủ công | Điều tra schema, so sánh môi trường, tạo migration hòa giải |
| Muốn chạy lại toàn bộ migration | Clear checksum không biến tất cả changeset thành pending | Thiết kế rollback/rebuild database hoặc quy trình replay riêng |
| Muốn đánh dấu changeset chưa chạy thành đã chạy | Đây là thay đổi trạng thái lịch sử, không phải checksum | Đánh giá changelogSync/markNextChangeSetRan theo quy trình chuyên biệt |
| Muốn sửa lỗi DDL thất bại một phần | Cần xác định trạng thái thực của DBMS | Điều tra schema/transaction, phục hồi hoặc forward fix |
| Muốn bỏ qua precondition thất bại | Checksum không liên quan tới điều kiện dữ liệu | Sửa nguyên nhân precondition hoặc dữ liệu |
| Muốn giải phóng khóa changelog | Clear-checksums không phải release-locks | Kiểm tra tiến trình và dùng lệnh quản trị khóa khi đủ điều kiện |
| Muốn đồng bộ các môi trường khác nhau | Mỗi database có lịch sử và trạng thái riêng | Kiểm tra từng database, cùng artifact và kế hoạch migration |
| Muốn chấp nhận thay đổi SQL chưa review | Lệnh có thể xóa tín hiệu phát hiện chỉnh sửa lịch sử | Review Git, tạo changeset mới và kiểm thử |

Một quy tắc dễ nhớ: **clear-checksums sửa trạng thái checksum đã lưu; nó không sửa nguyên nhân khiến checksum khác nhau**.

## 7. Phân biệt clear-checksums với các thao tác Liquibase khác

Các lệnh quản trị lịch sử dễ bị nhầm vì đều có thể xuất hiện khi xử lý database đã có trạng thái đặc biệt.

| Thao tác | Tác động chính | Có thực thi SQL migration không? | Rủi ro chính |
|---|---|---|---|
| **clear-checksums** | Xóa checksum đã lưu để tính lại ở lần update sau | Không chạy lại changeset thông thường chỉ vì xóa checksum | Chấp nhận nội dung hiện tại mà không xác minh schema tương ứng |
| **rollback** | Đưa database lùi theo rollback logic/tag/count/date | Có thể chạy SQL rollback được khai báo/sinh ra | Mất dữ liệu hoặc rollback không đầy đủ |
| **changelogSync** | Đánh dấu changeset chưa chạy là đã được áp dụng trong lịch sử | Không chạy các thay đổi của những changeset được đánh dấu | Lịch sử nói đã chạy trong khi schema chưa được tạo |
| **markNextChangeSetRan** | Đánh dấu changeset pending kế tiếp như đã chạy theo cơ chế lệnh | Không thực thi thay đổi của changeset đó | Đánh dấu sai trạng thái database |
| **validCheckSum** | Khai báo checksum được chấp nhận cho một changeset cụ thể | Không tự thực thi lại thay đổi lịch sử | Cho phép nội dung hiện tại qua validation dù cần đánh giá tác động |
| **release-locks** | Giải phóng trạng thái khóa changelog | Không chạy migration | Phá điều phối nếu job thực vẫn đang chạy |
| **update** | Thực thi changeset pending phù hợp | Có | Thay đổi schema/dữ liệu thật |

Tên lệnh, tùy chọn và hành vi chi tiết cần kiểm tra trên phiên bản Liquibase đang dùng. Các thao tác trên **không thể thay thế cho nhau**.

### 7.1. validCheckSum không phải clear-checksums

validCheckSum được khai báo trong changeset để cho phép một checksum cụ thể được xem là hợp lệ. Nó có phạm vi hẹp hơn việc xóa checksum của cả database, nhưng vẫn là một ngoại lệ cần giải thích và review.

Ví dụ minh họa vị trí:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 007-existing-view
      author: platform-team
      validCheckSum:
        - 9:checksum-value-approved
      changes:
        - sql:
            sql: SELECT 1;
~~~

Chuỗi checksum trên chỉ là giá trị giả để minh họa cú pháp, **không dùng trong dự án thật**. Trước khi thêm validCheckSum, phải xác minh giá trị được chấp nhận, lý do khác biệt và trạng thái database. Không thêm wildcard hoặc ngoại lệ rộng chỉ để bỏ cảnh báo.

### 7.2. changelogSync không phải cách sửa checksum

changelogSync có thể hữu ích khi cần đồng bộ lịch sử cho những thay đổi đã được áp dụng bằng một quy trình khác và có bằng chứng đầy đủ. Nó đánh dấu changeset như đã được thực thi trong lịch sử mà không chạy SQL tương ứng.

Nếu database chưa có bảng/cột nhưng changeset bị mark là đã chạy, ứng dụng có thể lỗi. Vì vậy, đây là thao tác quản trị trạng thái, cần so sánh schema thực tế trước và sau.

## 8. Phân tích checksum mismatch theo nguyên nhân

Không phải mọi checksum mismatch đều có cùng nguyên nhân.

| Dấu hiệu | Nguyên nhân có thể | Việc cần làm trước |
|---|---|---|
| Một changeset cũ khác checksum sau khi sửa YAML/SQL | Chỉnh sửa changeset đã triển khai | Đối chiếu Git và bản release, xác định thay đổi có phải migration mới |
| Nhiều changeset đồng loạt có khác biệt sau nâng cấp công cụ | Khác biệt phiên bản Liquibase hoặc cách tính checksum | Đọc tài liệu nâng cấp, thử trên bản sao cùng lịch sử |
| Chỉ một database báo lỗi | Changelog hoặc lịch sử môi trường đó khác các môi trường khác | Kiểm tra FILENAME, ID, AUTHOR, MD5SUM và artifact thực tế |
| Changeset cùng id nhưng FILENAME khác | Di chuyển/đổi tên file, logicalFilePath thay đổi | Xác định danh tính changeset và chính sách logicalFilePath |
| Chỉ thay đổi comment/whitespace nhưng checksum khác | Khác biệt định dạng hoặc phần nội dung được tính theo phiên bản | Kiểm tra thay đổi thật, không giả định mọi whitespace đều bị bỏ qua |
| Checksum khác sau khi resolve property | Giá trị cấu hình hoặc cách xử lý tham số khác | Kiểm tra parameter và SQL theo từng môi trường |
| Lịch sử nói đã chạy nhưng đối tượng không tồn tại | Schema drift, đánh dấu lịch sử sai hoặc DB restore không đầy đủ | So sánh schema và DATABASECHANGELOG, lập kế hoạch hòa giải |

Checksum không phải bằng chứng duy nhất để quyết định trạng thái migration. Cần so sánh **changelog trong Git**, **artifact được triển khai**, **DATABASECHANGELOG** và **schema/dữ liệu thật**.

## 9. Quy trình điều tra trước khi chạy clear-checksums

Khi gặp lỗi checksum, dừng quy trình deploy tự động và thực hiện theo thứ tự.

### Bước 1. Xác nhận đúng database đích

Kiểm tra JDBC URL, host, port, tên database, schema metadata và tài khoản. Một lệnh clear-checksums chạy trên nhầm database có thể làm mất tín hiệu checksum ở môi trường không liên quan.

Với PostgreSQL, có thể dùng truy vấn chỉ đọc:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS schema_name,
    current_user AS login_name;
~~~

Đây là thông tin phiên hiện tại; nếu metadata Liquibase được lưu ở schema khác, cần xác định rõ nơi chứa DATABASECHANGELOG.

### Bước 2. Ghi lại lịch sử trước khi thay đổi

Thu thập các bản ghi liên quan từ DATABASECHANGELOG:

~~~sql
SELECT
    id,
    author,
    filename,
    dateexecuted,
    orderexecuted,
    exectype,
    md5sum
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Truy vấn minh họa cho PostgreSQL với tên bảng mặc định. Hãy điều chỉnh schema/tên bảng theo cấu hình thực tế. Bảo vệ bản xuất vì lịch sử triển khai có thể tiết lộ tên đối tượng, thời điểm phát hành và thông tin nội bộ.

Lưu lại bản changelog và artifact đang được dùng, commit Git, phiên bản Liquibase, kết quả lỗi và trạng thái schema cần thiết để có thể đối chiếu.

### Bước 3. So sánh nội dung changeset

Với changeset bị báo lỗi:

- So sánh tệp hiện tại với commit đã triển khai gần nhất.
- Kiểm tra id, author và logicalFilePath.
- Xác định thay đổi nội dung có chủ đích hay là sửa nhầm lịch sử.
- Xem SQL dự kiến và đối tượng database đang có.
- Xác định các môi trường đã chạy phiên bản nội dung nào.

Nếu changeset lịch sử bị sửa ngoài ý muốn, thường khôi phục nội dung cũ và tạo changeset mới cho thay đổi thực tế.

### Bước 4. Kiểm tra schema và dữ liệu

Xác minh các bảng, cột, constraint, index, view, function hoặc dữ liệu mà changeset dự kiến tạo/sửa. Nếu database đã drift, clear-checksums không sửa drift.

Đối với thao tác DDL có thể phá hủy hoặc backfill, cần đánh giá backup, khả năng rollback và trạng thái giao dịch trước khi tiếp tục.

### Bước 5. Quyết định có cần clear-checksums không

Chỉ tiếp tục khi có một lý do cụ thể, được phê duyệt và có tài liệu phù hợp với phiên bản Liquibase. Nếu không xác định được nguyên nhân, dừng để điều tra thêm; không xóa checksum để “thử xem có hết lỗi không”.

## 10. Quy trình thực hiện clear-checksums có kiểm soát

Nếu đã xác nhận thao tác là cần thiết:

1. **Xác định phạm vi:** database/schema cụ thể và tất cả bản ghi checksum sẽ bị ảnh hưởng.
2. **Chọn thời điểm:** tránh các job Liquibase đồng thời; thông báo chủ sở hữu database.
3. **Sao lưu bằng chứng:** lưu bản ghi DATABASECHANGELOG và artifact/changelog đang triển khai theo chính sách.
4. **Kiểm tra quyền:** dùng tài khoản migration/quản trị được phê duyệt, không tự nâng quyền thành superuser.
5. **Xác minh cấu hình:** JDBC URL, database, schema lịch sử, context/label và phiên bản CLI.
6. **Chạy lệnh:** dùng đúng database đích.
7. **Kiểm tra kết quả:** xác nhận checksum đã được xóa theo phạm vi dự kiến, lịch sử changeset còn nguyên.
8. **Chạy validate:** kiểm tra changelog và checksum theo phiên bản công cụ.
9. **Chạy status:** xác nhận changeset pending phù hợp với kế hoạch.
10. **Chỉ chạy update khi được phê duyệt:** xem SQL dự kiến, xác minh schema và theo dõi log.
11. **Hậu kiểm:** so sánh DATABASECHANGELOG, checksum mới, schema và dữ liệu thật.
12. **Lưu dấu vết:** ghi lý do, người thực hiện, thời điểm, môi trường, phiên bản và kết quả.

Lệnh CLI minh họa:

~~~bash
liquibase --defaults-file=liquibase.properties clear-checksums
~~~

Sau đó, có thể chạy:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
~~~

Nếu kế hoạch phát hành cần áp dụng changeset pending và đã qua phê duyệt:

~~~bash
liquibase --defaults-file=liquibase.properties update
~~~

**Không chạy update chỉ vì vừa chạy clear-checksums.** Hãy xác nhận rằng update là bước cần thiết của quy trình phát hành hiện tại. Tùy phiên bản, validate có thể cần kết nối database và kiểm tra checksum; cần quan sát thông báo thực tế.

## 11. Ảnh hưởng theo từng môi trường

Mỗi database có bảng DATABASECHANGELOG riêng. Nếu cùng một ứng dụng có dev, test, staging và production, clear-checksums trên dev **không tự xóa checksum** ở các database khác.

| Môi trường | Hành động | Kiểm soát cần có |
|---|---|---|
| Dev | Có thể thử trên database cá nhân/nhóm | Bảo đảm không nhầm shared dev và ghi nhận nguyên nhân |
| Test/QA | Chỉ chạy theo quy trình kiểm thử và artifact đã chọn | Giữ lịch sử tái lập để kiểm chứng migration |
| Staging | Thử quy trình giống production | Đánh giá đúng phiên bản DBMS, Liquibase và dữ liệu đại diện |
| Production | Thao tác quản trị được phê duyệt | Backup bằng chứng, không có job đồng thời, xác minh đích và hậu kiểm |

Không nên thực hiện clear-checksums ở mọi môi trường chỉ để làm cho MD5SUM “giống nhau”. Các checksum được tính từ nội dung mà từng database nhận ở lần update kế tiếp; lịch sử của mỗi database có thể khác nhau vì tiến độ triển khai khác nhau.

Khi promote một release, hãy dùng **cùng artifact changelog đã kiểm thử** qua các môi trường. Nếu một database có lịch sử khác, giải quyết nguyên nhân riêng thay vì xóa checksum hàng loạt để che khác biệt.

## 12. Tương tác với runOnChange và runAlways

Hai thuộc tính này thay đổi cách Liquibase xử lý changeset đã chạy:

- **runOnChange: true** cho phép chạy lại changeset khi nội dung có ảnh hưởng đến checksum thay đổi.
- **runAlways: true** yêu cầu changeset được thực thi ở mỗi lượt update phù hợp.

clear-checksums không phải cách kích hoạt hai cơ chế trên. Khi checksum bị xóa, việc so sánh nội dung và quyết định chạy lại của changeset có thuộc tính đặc biệt có thể phụ thuộc trạng thái lịch sử, phiên bản và loại thay đổi. Vì vậy, nếu changelog có runOnChange hoặc runAlways, **hãy thử trên bản sao database với đúng phiên bản Liquibase** trước khi thao tác trên môi trường quan trọng.

Một số nguyên tắc:

- Không dùng clear-checksums để buộc view/function chạy lại.
- Không dùng runAlways cho DDL phá hủy hoặc DML không idempotent.
- Không sửa changeset runOnChange lịch sử từ một release cũ rồi chạy artifact cũ sau release mới.
- Không coi việc checksum được tính lại là bằng chứng định nghĩa database đã được thay thế.

Nếu mục tiêu là thay định nghĩa view/function, hãy quản lý changeset runOnChange theo đúng thiết kế và kiểm tra SQL được sinh ra. Nếu mục tiêu là thay đổi dữ liệu/schema, tạo changeset mới.

## 13. Checksum, precondition và schema drift

**Precondition** kiểm tra điều kiện trước khi changeset thực thi, ví dụ bảng tồn tại hoặc số dòng vi phạm bằng 0. **Checksum** kiểm tra nội dung changeset đã ghi nhận có còn phù hợp với changelog hiện tại. Hai cơ chế bổ sung nhau, không thay thế nhau.

Ví dụ một changeset yêu cầu bảng customer đã tồn tại và không có email NULL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-add-customer-email-index
      author: platform-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.customer
              WHERE email IS NULL
      changes:
        - createIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_email
            columns:
              - column:
                  name: email
~~~

Ví dụ giả định bảng có cột email và dữ liệu đáp ứng điều kiện. Nếu schema đã thay đổi ngoài Liquibase, precondition có thể phát hiện một số sai khác; nhưng không phải một công cụ so sánh toàn bộ schema.

**Schema drift** là trạng thái database khác với trạng thái mong đợi theo mã nguồn/chuẩn triển khai. Ví dụ DBA thêm cột thủ công, một bảng bị xóa, index bị thay đổi hoặc quyền bị cấp ngoài changelog. clear-checksums không phát hiện và không sửa những sai khác này.

Cách xử lý drift cần:

1. Thu thập schema thực tế.
2. So sánh với changelog và lịch sử.
3. Xác định thay đổi thủ công có hợp lệ không.
4. Quyết định hòa giải bằng changeset mới, restore hoặc quy trình đặc biệt.
5. Kiểm thử trước khi cập nhật lịch sử Liquibase.

Không dùng clear-checksums như một bước “đồng bộ schema”.

## 14. Rủi ro vận hành và bảo mật

### 14.1. Xóa checksum trên nhầm database

Vì lệnh tác động theo cấu hình kết nối hiện tại, sai JDBC URL hoặc profile có thể làm xóa checksum ở production trong khi người vận hành nghĩ đang thao tác trên test. Trước lệnh, xác minh host, database, schema metadata, user và environment allowlist.

### 14.2. Nhiều job chạy đồng thời

Một job update và một job clear-checksums cùng truy cập lịch sử có thể gây xung đột hoặc tạo kết quả khó giải thích. Chỉ định một chủ sở hữu migration, kiểm tra trạng thái DATABASECHANGELOGLOCK và điều phối cửa sổ thao tác.

Không giải phóng khóa changelog bằng tay chỉ vì clear-checksums đang chờ. Phải xác nhận job giữ khóa đã kết thúc trước mọi hành động quản trị.

### 14.3. Mất bằng chứng kiểm toán

Checksum là một phần dấu vết phát hiện chỉnh sửa changeset. Xóa toàn bộ checksum mà không lưu nguyên nhân và giá trị trước đó làm giảm khả năng điều tra sau này. Hãy lưu bản ghi liên quan theo chính sách bảo mật, ticket, commit, phiên bản Liquibase và người phê duyệt.

### 14.4. Tài khoản và quyền

Chỉ dùng tài khoản được phép thực hiện thao tác quản trị lịch sử. Không đặt password trong dòng lệnh được ghi log, file changelog hoặc tài liệu. Cấp quyền tối thiểu và thu hồi quyền bảo trì tạm thời sau khi hoàn tất theo quy định.

### 14.5. Không dùng SQL UPDATE thủ công lên MD5SUM

Không nên thay lệnh Liquibase bằng:

~~~sql
-- Chỉ minh họa thao tác KHÔNG nên tự thực hiện:
UPDATE databasechangelog
SET md5sum = NULL;
~~~

Cập nhật trực tiếp bảng lịch sử bỏ qua logic, khóa, xác thực và hành vi tương thích của Liquibase. Nếu cần clear checksums, dùng lệnh được công cụ hỗ trợ sau khi đã xác minh phiên bản và phạm vi.

## 15. Kiểm chứng sau khi chạy

Sau clear-checksums, không chỉ xem lệnh trả exit code 0. Cần xác nhận nhiều lớp.

### 15.1. Kiểm tra bảng lịch sử

Trước update, có thể xác nhận MD5SUM đã được xóa theo dự kiến nhưng các hàng lịch sử vẫn còn. Sau update, kiểm tra checksum đã được tính lại cho những changeset Liquibase xét và cập nhật.

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Đây là truy vấn minh họa; tên/schema bảng lịch sử phụ thuộc cấu hình. Không sửa kết quả bằng tay nếu có hàng không như mong đợi.

### 15.2. Kiểm tra schema thực tế

Chọn những đối tượng có liên quan tới changeset từng báo checksum mismatch. Với PostgreSQL, kiểm tra bảng, cột, constraint, index, view hoặc function bằng catalog/information_schema. So sánh với nội dung changeset và release đã triển khai.

### 15.3. Kiểm tra trạng thái pending

Chạy:

~~~bash
liquibase --defaults-file=liquibase.properties status --verbose
~~~

Xem changeset nào còn pending. Nếu một changeset lịch sử đã chạy xuất hiện pending, dừng và điều tra định danh ID/author/FILENAME, logicalFilePath, lịch sử và cấu hình changelog. Không tự chạy update để xem điều gì xảy ra.

### 15.4. Kiểm tra chức năng ứng dụng

Nếu changeset liên quan đến bảng, view, function hoặc quyền truy cập, thử các luồng ứng dụng phụ thuộc. Một checksum hợp lệ không bảo đảm ứng dụng tương thích với schema hiện tại.

## 16. Ví dụ tình huống: changeset lịch sử bị sửa

Giả sử một nhóm đã phát hành changeset tạo bảng **app.invoice** ở dev, test và production. Một pull request vô tình sửa changeset cũ để thêm cột source_system.

### 16.1. Hành động không nên làm

Không chạy ngay:

~~~bash
liquibase clear-checksums
liquibase update
~~~

Việc này có thể khiến Liquibase tính lại checksum cho nội dung mới nhưng không thực thi lại changeset thông thường đã được ghi nhận. Production vẫn có thể thiếu cột source_system trong khi lịch sử không còn cảnh báo checksum mismatch.

### 16.2. Cách xử lý đúng

1. Dừng pipeline đang triển khai.
2. Xác định changeset đã được phát hành ở những môi trường nào.
3. Khôi phục nội dung changeset cũ trong Git về đúng phiên bản đã chạy.
4. Tạo changeset mới, ví dụ 012-add-invoice-source-system, dùng addColumn.
5. Chạy validate, status, update-sql trên dev/test.
6. Xác minh cột và dữ liệu sau migration.
7. Promote cùng artifact đã kiểm thử lên production.
8. Giữ lại lịch sử changeset cũ và mới để truy vết.

Ví dụ changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 012-add-invoice-source-system
      author: platform-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: invoice
      changes:
        - addColumn:
            schemaName: app
            tableName: invoice
            columns:
              - column:
                  name: source_system
                  type: VARCHAR(50)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: invoice
            columnName: source_system
~~~

Rollback dropColumn sẽ xóa dữ liệu source_system được ghi sau khi thêm cột. Vì vậy, chỉ dùng nếu dữ liệu đó có thể bỏ hoặc đã có phương án phục hồi. Ví dụ minh họa không khẳng định cột có thể nullable/NOT NULL phù hợp mọi yêu cầu nghiệp vụ.

## 17. Ví dụ tình huống: nâng cấp Liquibase

Một tổ chức nâng phiên bản Liquibase và phát hiện thông báo checksum khác ở một số database. Không nên xóa checksum hàng loạt ngay.

Quy trình:

1. Ghi lại phiên bản CLI/Library trước và sau nâng cấp.
2. Đọc release notes và hướng dẫn upgrade của đúng phiên bản.
3. Xác định checksum mismatch có xuất phát từ nội dung changeset hay từ thay đổi cách xử lý checksum.
4. Thử nâng cấp trên bản sao database có DATABASECHANGELOG đại diện.
5. Chạy validate và quan sát cách công cụ xử lý checksum.
6. Nếu tài liệu chính thức yêu cầu clear-checksums, xác định database đích, thời điểm và phạm vi.
7. Thực hiện theo runbook, không có job Liquibase đồng thời.
8. Chạy validate/status/update theo kế hoạch và so sánh schema với baseline.
9. Lưu kết quả để các môi trường còn lại dùng cùng quy trình.

Không nên giả định nâng cấp Liquibase luôn cần clear-checksums; nhiều phiên bản có thể tự xử lý thay đổi phiên bản checksum. Hãy theo tài liệu của đúng bản phát hành.

## 18. Tích hợp Spring Boot và CI/CD

Trong Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động nếu dependency và cấu hình được bật. Trong CI/CD, Liquibase có thể được gọi từ một job migration riêng. Dù dùng cách nào, clear-checksums vẫn là **thao tác quản trị trên database đích**, không nên tự động chạy như một bước mặc định mỗi lần deploy.

Một quy trình CI/CD an toàn:

1. Xác định commit và artifact changelog.
2. Cố định phiên bản Liquibase, Java và JDBC driver.
3. Xác minh JDBC URL, database, schema và user.
4. Kiểm tra trạng thái job migration khác và DATABASECHANGELOGLOCK.
5. Chạy validate và phân tích checksum mismatch.
6. So sánh changelog hiện tại với lịch sử Git/release.
7. Nếu có lý do hợp lệ, xin phê duyệt thao tác clear-checksums theo runbook.
8. Thực hiện trên đúng môi trường; không chạy song song với update.
9. Validate, status, review SQL dự kiến và kiểm tra schema sau thao tác.
10. Chỉ chạy update khi có changeset pending được xác định và phê duyệt.
11. Lưu ticket, log, checksum trước/sau và người thực hiện.

Nếu Spring Boot tự migrate production, cần đảm bảo không có một replica khác hoặc job CI cùng chạy thao tác quản trị checksum. Với thao tác đặc biệt này, job migration độc lập thường dễ kiểm soát hơn, nhưng lựa chọn cuối cùng phụ thuộc kiến trúc.

**Không để pipeline tự động gọi clear-checksums khi bắt gặp bất kỳ lỗi checksum nào.** Hành vi đó sẽ biến một cơ chế cảnh báo quan trọng thành một bước bị vô hiệu hóa không có đánh giá.

## 19. Runbook ngắn cho người vận hành

Khi nhận cảnh báo checksum mismatch:

**Dừng**
- Không chạy clear-checksums ngay.
- Không chạy update lại liên tục.
- Không sửa DATABASECHANGELOG trực tiếp.
- Không release-locks nếu chưa xác minh job thực.

**Điều tra**
- Đúng database/schema/user chưa?
- Changeset id/author/filename nào báo lỗi?
- Nội dung hiện tại khác bản phát hành nào?
- Schema thực tế có phản ánh nội dung mới không?
- Có thay đổi phiên bản Liquibase không?
- Những môi trường khác đang có checksum và trạng thái gì?

**Quyết định**
- Changeset cũ bị sửa nhầm: khôi phục bản cũ, tạo changeset mới.
- Database drift: lập kế hoạch hòa giải schema/dữ liệu.
- Nâng cấp công cụ: làm theo hướng dẫn upgrade chính thức.
- Trường hợp bảo trì checksum có phê duyệt: dùng clear-checksums đúng database theo runbook.

**Hậu kiểm**
- Kiểm tra MD5SUM và DATABASECHANGELOG.
- Chạy validate/status.
- Kiểm tra schema và dữ liệu thật.
- Ghi lại bằng chứng và đóng sự cố chỉ khi trạng thái đã rõ.

## 20. Các câu hỏi tự kiểm tra

**Câu 1:** clear-checksums có xóa bản ghi changeset khỏi DATABASECHANGELOG không?

**Đáp án:** Không. Nó xóa checksum đã lưu theo phạm vi database; các thông tin lịch sử changeset vẫn còn.

**Câu 2:** Sau clear-checksums, Liquibase có chạy lại tất cả CREATE TABLE đã thực thi không?

**Đáp án:** Không. Lệnh không xóa trạng thái đã chạy và không có mục tiêu replay toàn bộ changeset. Những changeset có hành vi đặc biệt cần được thử riêng theo phiên bản.

**Câu 3:** Một changeset lịch sử đã bị sửa để thêm cột. clear-checksums có tự thêm cột đó vào production không?

**Đáp án:** Không nên kỳ vọng như vậy. Changeset thông thường vẫn được ghi nhận đã chạy; tính lại checksum không thực thi lại SQL cũ. Hãy khôi phục lịch sử và tạo changeset mới.

**Câu 4:** Có thể clear-checksums trên dev để sửa checksum ở production không?

**Đáp án:** Không. Mỗi database có lịch sử riêng; lệnh chỉ tác động tới database mà cấu hình hiện tại kết nối.

**Câu 5:** clear-checksums có giải phóng DATABASECHANGELOGLOCK không?

**Đáp án:** Không. Khóa changelog là một cơ chế khác; cần kiểm tra tiến trình và dùng quy trình release-locks khi đủ điều kiện.

**Câu 6:** Khi nào cần cân nhắc clear-checksums?

**Đáp án:** Khi có nguyên nhân quản trị checksum được xác minh, tài liệu phiên bản hỗ trợ và quy trình phê duyệt rõ ràng; không phải để bỏ qua một lỗi chưa điều tra.

## 21. Checklist trước và sau clear-checksums

### Trước khi chạy

- [ ] Đã xác định chính xác database, host, schema metadata và user.
- [ ] Đã ghi lại phiên bản Liquibase, Java, JDBC driver và artifact changelog.
- [ ] Đã xác định changeset nào báo mismatch và nguyên nhân có khả năng nhất.
- [ ] Đã so sánh nội dung changelog với Git/release đã triển khai.
- [ ] Đã xác minh schema/dữ liệu thật, không chỉ dựa vào checksum.
- [ ] Đã lưu bằng chứng DATABASECHANGELOG và thông tin liên quan theo chính sách.
- [ ] Đã xác nhận không có job Liquibase đồng thời.
- [ ] Đã có lý do, phê duyệt và runbook cụ thể cho clear-checksums.
- [ ] Đã hiểu thao tác sẽ tác động checksum của database đích trên phạm vi rộng.

### Sau khi chạy

- [ ] Xác nhận bản ghi lịch sử vẫn còn.
- [ ] Xác nhận checksum được tính lại ở lần update theo kế hoạch.
- [ ] Chạy validate và status trên đúng database.
- [ ] Xác nhận không có changeset cũ bất ngờ trở thành pending.
- [ ] Kiểm tra schema, dữ liệu, index, view/function và quyền liên quan.
- [ ] Chỉ chạy update nếu có thay đổi pending đã được review/phê duyệt.
- [ ] Xác nhận không còn job/session migration dở dang.
- [ ] Lưu checksum trước/sau, log, ticket và người thực hiện.
- [ ] Kiểm tra lại các môi trường khác theo lịch sử riêng của chúng.

## 22. Kết luận

**clear-checksums** là lệnh quản trị checksum của Liquibase. Nó xóa các giá trị checksum đã lưu trong **DATABASECHANGELOG** của database đích để Liquibase tính lại ở lần update tiếp theo. Lệnh không xóa lịch sử changeset, không tự chạy lại migration thông thường, không rollback dữ liệu, không sửa schema drift và không giải phóng khóa changelog.

Hệ quả quan trọng nhất là **khả năng phát hiện changeset lịch sử bị chỉnh sửa có thể bị suy giảm** nếu checksum mới được chấp nhận mà schema thật chưa tương ứng. Vì vậy, trước khi chạy, phải điều tra nguyên nhân mismatch, so sánh Git và database, xác minh đúng môi trường, lưu bằng chứng và có phê duyệt. Khi cần thay đổi schema/dữ liệu, hãy giữ changeset cũ bất biến và tạo changeset mới; chỉ dùng clear-checksums cho tình huống bảo trì checksum đã được xác định rõ.

Cách làm này hỗ trợ mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**: quản lý changelog, changeset, precondition, checksum và lịch sử triển khai có thể kiểm chứng; phối hợp dev/test/production và vận hành Liquibase trong Spring Boot hoặc CI/CD với dấu vết rõ ràng.

