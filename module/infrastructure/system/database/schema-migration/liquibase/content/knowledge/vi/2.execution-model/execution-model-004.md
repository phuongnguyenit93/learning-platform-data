# Cách xác định changeset đã chạy và changeset đang chờ

Trong chương **Mô hình thực thi**, bài học này giải thích cách Liquibase xác định trạng thái của từng changeset trên một cơ sở dữ liệu đích. Với phạm vi **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, bạn cần nắm được changelog nào được nạp, khóa định danh nào được dùng để đối chiếu lịch sử, cách đọc bảng DATABASECHANGELOG và cách kiểm tra danh sách changeset đang chờ trước khi triển khai.

Liquibase không suy luận trạng thái chỉ từ cấu trúc schema hiện tại. Nó đối chiếu changelog mà lệnh triển khai đang sử dụng với lịch sử do chính Liquibase lưu trong cơ sở dữ liệu đích. Vì vậy, cùng một changelog có thể ở trạng thái khác nhau giữa development, staging và production.

## 1. Mô hình xác định trạng thái

Khi chạy một lệnh như status hoặc update, Liquibase cần biết ba điều:

1. **Changelog đầu vào:** tệp changelog gốc được cấu hình qua CLI, Spring Boot hoặc công cụ triển khai.
2. **Tập changeset có hiệu lực:** changelog gốc cùng các tệp được nạp qua include hoặc includeAll, sau khi áp dụng thứ tự và bộ lọc như context, label, dbms.
3. **Lịch sử của database đích:** các changeset đã được ghi nhận trong bảng DATABASECHANGELOG của chính database đó.

Liquibase duyệt changelog theo cấu trúc và thứ tự khai báo, tạo tập changeset cần xem xét, rồi đối chiếu từng changeset với lịch sử. Một changeset thường được nhận diện bằng tổ hợp ba giá trị:

- **id:** mã changeset do người viết changelog đặt.
- **author:** tác giả hoặc định danh nhóm chịu trách nhiệm.
- **filename:** đường dẫn changelog được Liquibase ghi nhận.

Cả ba thành phần cùng tạo nên định danh. Chỉ so sánh id là chưa đủ: hai tệp khác nhau có thể chứa changeset trùng id và author mà vẫn là hai định danh khác nhau do filename khác nhau.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-001
      author: platform
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
~~~

Trong ví dụ này, Liquibase đối chiếu changeset bằng id là 2026-001, author là platform và filename của tệp chứa changeset. Nếu đổi tên hoặc di chuyển tệp, filename có thể thay đổi và Liquibase có thể xem changeset là một định danh mới. Khi tổ chức lại thư mục changelog, cần giữ đường dẫn ổn định hoặc cấu hình logicalFilePath phù hợp để duy trì định danh lịch sử.

## 2. DATABASECHANGELOG là nguồn lịch sử triển khai

Khi Liquibase thực thi hoặc ghi nhận một changeset, nó lưu một dòng trong bảng DATABASECHANGELOG. Bảng này thường được Liquibase tự tạo trong schema được cấu hình. Mỗi database đích có lịch sử riêng; dòng lịch sử ở staging không chứng minh rằng production đã chạy cùng changeset.

Một số cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| ID | Giá trị id của changeset |
| AUTHOR | Giá trị author của changeset |
| FILENAME | Đường dẫn changelog được ghi nhận |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận changeset |
| ORDEREXECUTED | Thứ tự thực thi được ghi nhận |
| EXECTYPE | Kiểu kết quả, ví dụ EXECUTED, RERAN hoặc MARK_RAN |
| MD5SUM | Checksum Liquibase dùng để phát hiện thay đổi nội dung |
| DESCRIPTION | Mô tả thay đổi được Liquibase suy ra |
| COMMENTS | Ghi chú của changeset nếu có |
| CONTEXTS | Context gắn với lần ghi nhận |
| LABELS | Label gắn với lần ghi nhận |
| LIQUIBASE | Phiên bản Liquibase ghi nhận lần triển khai |

Tùy phiên bản Liquibase và hệ quản trị cơ sở dữ liệu, bảng có thể có thêm cột hoặc cách biểu diễn khác. Khi truy vấn trực tiếp, hãy kiểm tra cấu trúc bảng thực tế của môi trường đang làm việc.

Truy vấn lịch sử tổng quát:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    CONTEXTS,
    LABELS
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Để kiểm tra một changeset cụ thể, phải dùng đủ ba thành phần định danh:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
WHERE ID = '2026-001'
  AND AUTHOR = 'platform'
  AND FILENAME = 'db/changelog/changes/2026-001.yaml';
~~~

Giá trị FILENAME trong điều kiện phải khớp với giá trị đang được lưu trong database. Nếu dự án dùng logicalFilePath, hãy đối chiếu theo đường dẫn logic đó thay vì tự đoán từ vị trí vật lý của tệp.

Nếu truy vấn trả về một dòng, Liquibase đã ghi nhận changeset với định danh này. Hãy đọc thêm EXECTYPE để hiểu cách nó được ghi nhận:

- **EXECUTED:** changeset đã được thực thi.
- **RERAN:** changeset được chạy lại, thường do cấu hình runOnChange.
- **MARK_RAN:** Liquibase đã ghi nhận changeset là đã chạy nhưng không thực thi phần thay đổi của changeset, chẳng hạn do precondition dùng onFail: MARK_RAN hoặc do thao tác đồng bộ lịch sử có chủ đích.

Các giá trị trên là những trường hợp thường gặp, không phải danh sách đầy đủ cho mọi phiên bản và tình huống. Một dòng MARK_RAN không chứng minh rằng câu lệnh DDL hoặc DML bên trong changeset đã được chạy.

Không nên sửa, thêm hoặc xóa dòng trong DATABASECHANGELOG bằng SQL thủ công để làm cho trạng thái hiển thị như mong muốn. Thao tác đó có thể làm lịch sử lệch khỏi schema thật và khiến những lần triển khai sau bỏ qua hoặc chạy lặp thay đổi.

## 3. DATABASECHANGELOGLOCK có vai trò gì?

Liquibase còn sử dụng bảng DATABASECHANGELOGLOCK để điều phối quyền chạy migration. Bảng này giúp ngăn hai tiến trình Liquibase cùng triển khai changelog lên một database tại cùng thời điểm.

Có thể kiểm tra trạng thái khóa bằng truy vấn:

~~~sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
~~~

Thông thường, một dòng khóa có ID bằng 1. LOCKED cho biết khóa đang được giữ; LOCKGRANTED và LOCKEDBY giúp nhận diện thời điểm và tiến trình đã lấy khóa.

Cần phân biệt rõ:

- DATABASECHANGELOG trả lời changeset nào đã được ghi nhận trong lịch sử.
- DATABASECHANGELOGLOCK cho biết tiến trình Liquibase có đang giữ khóa triển khai hay không.

Một changeset không xuất hiện trong DATABASECHANGELOG không có nghĩa là nó đang bị khóa. Ngược lại, LOCKED bằng true không cho biết changeset nào đã chạy; nó chỉ báo hiệu một tiến trình đang giữ quyền triển khai hoặc một khóa chưa được giải phóng.

Nếu khóa còn tồn tại sau khi tiến trình triển khai kết thúc bất thường, hãy xác minh chắc chắn không còn migration đang chạy trước khi dùng lệnh release-locks. Không xóa bảng khóa hoặc tự đặt LOCKED về false khi chưa hiểu tiến trình nào đang sử dụng database.

## 4. Phân biệt changeset đã chạy và changeset đang chờ

Có thể dùng hai khái niệm sau để đọc trạng thái:

**Changeset đã được ghi nhận** là changeset có định danh tương ứng trong DATABASECHANGELOG. Đây là bằng chứng lịch sử của Liquibase đối với database đang kết nối.

**Changeset đang chờ** là changeset thuộc tập changelog có hiệu lực của lần chạy hiện tại nhưng chưa có bản ghi tương ứng trong DATABASECHANGELOG. Lệnh status giúp liệt kê nhóm này.

Không phải mọi changeset không có dòng lịch sử đều chắc chắn sẽ được thực thi trong lần update kế tiếp. Các bộ lọc và điều kiện triển khai có thể ảnh hưởng đến kết quả:

- **Context:** giới hạn changeset theo ngữ cảnh như dev, test hoặc prod.
- **Label:** phân nhóm changeset để chọn phạm vi triển khai.
- **dbms:** giới hạn hệ quản trị cơ sở dữ liệu phù hợp.
- **Precondition:** kiểm tra điều kiện trước khi chạy changeset. Hành vi phụ thuộc onFail hoặc onError, ví dụ HALT, WARN, CONTINUE hay MARK_RAN.

Với onFail: HALT, Liquibase dừng khi điều kiện không đạt. Với onFail: CONTINUE, changeset được bỏ qua trong lần chạy đó và thường vẫn chưa có bản ghi lịch sử, nên có thể được xem xét lại ở lần chạy sau. Với onFail: MARK_RAN, Liquibase ghi nhận changeset mà không thực thi phần thay đổi. Với onFail: WARN, Liquibase cảnh báo và tiếp tục theo cấu hình của changeset. Hãy đọc cả precondition cấp changelog và cấp changeset khi điều tra một thay đổi không chạy như dự kiến.

Ví dụ một changeset chỉ dành cho môi trường development:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-002
      author: platform
      context: dev
      changes:
        - createTable:
            tableName: debug_event
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Khi chạy với bộ lọc chỉ chọn context prod, changeset trên không thuộc phạm vi triển khai. Vì thế, không nên kết luận một changeset bị lỗi chỉ vì nó chưa xuất hiện trong lịch sử; trước tiên hãy xác nhận context, label, dbms và precondition của lần chạy.

## 5. Các lệnh Liquibase để kiểm tra trạng thái

Các lệnh dưới đây giả định kết nối database và changelog gốc đã được cấu hình qua tham số CLI, tệp liquibase.properties hoặc cấu hình của môi trường chạy.

### Liệt kê changeset đang chờ

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
~~~

status hiển thị changeset chưa được triển khai theo changelog và cấu hình đang dùng. Tùy chọn verbose cung cấp thông tin chi tiết hơn. Đây là bước kiểm tra trạng thái; lệnh không thực thi migration.

### Xem lịch sử đã triển khai

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml history
~~~

history hiển thị lịch sử triển khai mà Liquibase ghi nhận trong database đang kết nối. Dùng lệnh này cùng với status để so sánh phần đã ghi nhận và phần đang chờ.

### Kiểm tra changelog

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
~~~

validate kiểm tra tính hợp lệ của changelog, chẳng hạn cấu trúc, tham chiếu tệp và một số lỗi cấu hình. Lệnh này không chứng minh rằng mọi câu lệnh SQL sẽ chạy thành công trên dữ liệu thực tế. Vẫn cần kiểm tra quyền, phiên bản database, dữ liệu hiện có và các điều kiện phụ thuộc môi trường.

### Xem SQL dự kiến

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

update-sql tạo SQL mà Liquibase dự kiến dùng để triển khai changeset đang cần áp dụng. Hãy đọc nội dung SQL, xác nhận schema đích, thứ tự thay đổi và ảnh hưởng đến dữ liệu trước khi triển khai. Lệnh này giúp review kế hoạch nhưng không thay thế việc thực thi và xác minh sau triển khai.

### Thực thi changeset đang chờ

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

update thực thi các changeset cần áp dụng theo changelog, bộ lọc và lịch sử của database hiện tại. Liquibase ghi nhận kết quả trong DATABASECHANGELOG. Khi lệnh kết thúc, chạy lại history hoặc truy vấn DATABASECHANGELOG để xác nhận trạng thái.

Một quy trình kiểm tra thông thường là:

1. Xác nhận đúng URL, database, schema, changelog gốc và phiên bản Liquibase.
2. Chạy status --verbose để biết changeset nào đang chờ.
3. Chạy history hoặc truy vấn DATABASECHANGELOG để kiểm tra lịch sử.
4. Chạy validate để phát hiện lỗi changelog.
5. Chạy update-sql và review SQL được tạo.
6. Triển khai bằng update trong đúng môi trường.
7. Kiểm tra lại history, DATABASECHANGELOG và schema sau triển khai.

status là ảnh chụp trạng thái tại thời điểm truy vấn. Một tiến trình khác có thể triển khai sau bước status và trước bước update. Vì vậy, kết quả status không phải là khóa giữ chỗ và cũng không đảm bảo danh sách pending vẫn giống hệt khi update bắt đầu. update mới là thao tác thực thi có điều phối khóa.

## 6. Checksum và những trường hợp changeset được chạy lại

Cột MD5SUM lưu checksum mà Liquibase tính cho changeset. Checksum giúp phát hiện nội dung của changeset đã thay đổi sau khi được ghi nhận. Nếu sửa một changeset đã chạy, Liquibase có thể báo lỗi checksum khi kiểm tra hoặc triển khai, bởi lịch sử đang lưu không còn khớp với nội dung hiện tại.

Quy tắc an toàn là coi changeset đã triển khai như lịch sử bất biến. Khi cần thay đổi schema hoặc dữ liệu, hãy tạo changeset mới có định danh mới. Ví dụ, nếu changeset 2026-001 đã tạo bảng customer, hãy tạo changeset 2026-003 để thêm cột phone thay vì quay lại sửa nội dung 2026-001.

Hai thuộc tính có hành vi đặc biệt:

- **runOnChange: true:** Liquibase chạy lại changeset khi checksum của nó thay đổi. Cách này thường hữu ích cho định nghĩa đối tượng cần cập nhật theo nội dung mới, nhưng cần hiểu rõ tác động của câu lệnh.
- **runAlways: true:** Liquibase chạy changeset mỗi lần update đi qua changelog, kể cả khi changeset đã có trong lịch sử.

Do đó, cần đọc cả định danh, checksum và thuộc tính thực thi trước khi kết luận changeset đã ghi nhận sẽ luôn bị bỏ qua. Một changeset có runAlways hoặc runOnChange có thể được thực thi lại theo quy tắc tương ứng.

Liquibase có lệnh clear-checksums để xóa checksum đã lưu và tính lại trong lần chạy sau. Đây không phải cách sửa mặc định cho lỗi checksum: dùng tùy tiện có thể làm mất tín hiệu phát hiện việc chỉnh sửa changeset cũ. Chỉ sử dụng khi đã hiểu nguyên nhân, có quy trình được kiểm soát và biết rõ tác động đến toàn bộ lịch sử checksum. validCheckSum cũng chỉ nên dùng trong trường hợp ngoại lệ đã được xem xét và ghi lại.

## 7. Áp dụng trong Spring Boot

Khi tích hợp Spring Boot, Liquibase thường được cấu hình để chạy khi ứng dụng khởi động. Ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: prod
~~~

Khi enabled là true, Spring Boot khởi tạo Liquibase với datasource và changelog đã cấu hình. Liquibase kiểm tra lịch sử trong DATABASECHANGELOG, lấy khóa triển khai khi cần và áp dụng changeset thuộc phạm vi phù hợp. Vì vậy, nếu ứng dụng khởi động vào một database mới, nhiều changeset có thể đang chờ; nếu database đã có lịch sử tương ứng, các changeset thông thường sẽ được bỏ qua.

Một số điểm cần xác nhận khi điều tra trạng thái trong Spring Boot:

- Ứng dụng đang dùng đúng datasource và đúng database/schema dự kiến.
- change-log trỏ đến đúng changelog gốc đã đóng gói trong classpath.
- contexts và các bộ lọc khác phù hợp với môi trường.
- Bản build đang triển khai chứa đúng phiên bản changelog dự kiến.
- Chỉ có một quy trình triển khai chủ động thực hiện migration cho database tại một thời điểm.

Có thể tắt Liquibase tự chạy bằng spring.liquibase.enabled=false nếu kiến trúc triển khai giao migration cho một job riêng. Khi đó, job migration phải dùng đúng changelog, cấu hình kết nối và bộ lọc mà ứng dụng sẽ sử dụng.

## 8. Kiểm soát nhiều môi trường và CI/CD

Mỗi môi trường thường có database và bảng DATABASECHANGELOG riêng. Một changeset có thể đã chạy ở development nhưng vẫn đang chờ ở staging hoặc production. Đây là hành vi bình thường vì Liquibase đối chiếu lịch sử của database đích hiện tại.

Để kết quả nhất quán giữa các môi trường:

- Đưa changelog vào cùng quy trình quản lý phiên bản với mã nguồn.
- Dùng cùng phiên bản artifact và cùng nội dung changelog khi promote qua các môi trường.
- Cấu hình URL, thông tin xác thực, schema và context theo từng môi trường; không sửa nội dung changeset chỉ để phù hợp một môi trường.
- Giữ ổn định id, author và logicalFilePath.
- Chạy status, validate và update-sql trong pipeline để tạo bằng chứng review trước khi triển khai.
- Chỉ chạy update ở bước migration đã được kiểm soát; xác nhận kết quả qua DATABASECHANGELOG sau khi chạy.
- Tránh để nhiều pipeline độc lập cùng triển khai changelog lên một database. Cơ chế lock của Liquibase giúp điều phối, nhưng pipeline vẫn cần quản lý thứ tự và xử lý thời gian chờ rõ ràng.

Một pipeline có thể chia thành bước kiểm tra changelog, tạo SQL để review, bước phê duyệt theo quy trình nội bộ, rồi bước thực thi update. Bước thực thi cần nhận đúng cấu hình môi trường và artifact đã được kiểm tra. Không nên dùng việc status trả về không có pending làm bằng chứng duy nhất rằng schema thực tế hoàn toàn đúng; trạng thái lịch sử và cấu trúc database là hai loại bằng chứng khác nhau.

## 9. Chẩn đoán khi trạng thái không như dự kiến

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Changeset đáng lẽ đã chạy nhưng status vẫn liệt kê pending | Kết nối nhầm database/schema; filename thay đổi; id hoặc author khác; dòng lịch sử không tồn tại | Xác nhận datasource, changelog gốc và đủ bộ ba id-author-filename trong DATABASECHANGELOG |
| Changeset chưa xuất hiện trong danh sách pending | Context, label hoặc dbms không khớp; changeset đã được ghi nhận; precondition hoặc cấu hình changelog làm thay đổi phạm vi | Kiểm tra bộ lọc, precondition, history và changelog đã được nạp |
| Liquibase báo checksum không khớp | Nội dung changeset đã triển khai bị sửa | Khôi phục nội dung lịch sử hoặc tạo changeset mới; chỉ xử lý checksum bằng ngoại lệ có kiểm soát |
| Changeset có EXECTYPE là MARK_RAN | Liquibase đã đánh dấu changeset là đã chạy mà không thực thi phần thay đổi | Kiểm tra precondition, onFail và lịch sử đồng bộ; xác minh schema thực tế |
| Migration dừng do lock | Một tiến trình đang chạy hoặc lần chạy trước kết thúc bất thường | Kiểm tra tiến trình triển khai và DATABASECHANGELOGLOCK; chỉ giải phóng khóa khi chắc chắn không còn tiến trình giữ khóa |
| Schema đã có thay đổi nhưng DATABASECHANGELOG không có dòng tương ứng | Thay đổi được thực hiện ngoài Liquibase hoặc lịch sử chưa được đồng bộ | Xác minh schema trước; chỉ dùng changelogSync hoặc markNextChangeSetRan trong quy trình baseline được phê duyệt |

Với database đã tồn tại schema trước khi đưa Liquibase vào quản lý, có thể cần quy trình baseline để ghi nhận các changeset tương ứng mà không chạy lại DDL. Các lệnh như changelogSync hoặc markNextChangeSetRan có thể đánh dấu changeset là đã chạy mà không thực thi nội dung. Chỉ dùng chúng sau khi đã đối chiếu schema thực tế với changelog; nếu đánh dấu sai, Liquibase sẽ tin rằng thay đổi đã được áp dụng và có thể bỏ qua migration cần thiết.

## 10. Ví dụ quy trình kiểm tra một changeset cụ thể

Giả sử nhóm phát triển thêm changeset 2026-003 để bổ sung cột phone cho bảng customer. Trước khi triển khai staging, người vận hành thực hiện:

1. Kiểm tra cấu hình kết nối để chắc chắn đang trỏ đến database staging.
2. Chạy status --verbose với changelog gốc của bản build. Nếu 2026-003 xuất hiện, ghi nhận nó đang chờ trong phạm vi bộ lọc hiện tại.
3. Truy vấn DATABASECHANGELOG với id, author và filename của 2026-003 để xác nhận chưa có dòng lịch sử tương ứng.
4. Chạy validate và update-sql; review câu lệnh ALTER TABLE, kiểu dữ liệu, khả năng tương thích và ảnh hưởng đến ứng dụng.
5. Chạy update trong bước triển khai staging.
6. Truy vấn lại DATABASECHANGELOG. Xác nhận có dòng với định danh đúng, EXECTYPE phù hợp và thời điểm ghi nhận mới.
7. Kiểm tra schema để xác nhận cột phone thực sự tồn tại với kiểu dữ liệu và ràng buộc mong muốn.

Khi promote cùng artifact lên production, thực hiện lại các bước kiểm tra trên production. Không lấy kết quả lịch sử staging làm kết luận cho production vì mỗi database duy trì DATABASECHANGELOG riêng.

## 11. Checklist đọc trạng thái trước khi triển khai

- [ ] Đúng database, schema, datasource và changelog gốc.
- [ ] Đã xác nhận phiên bản Liquibase và artifact đang triển khai.
- [ ] Đã kiểm tra các include/includeAll và thứ tự changelog.
- [ ] Đã kiểm tra context, label, dbms và precondition.
- [ ] Đối chiếu changeset bằng đủ id, author và filename.
- [ ] Đã đọc EXECTYPE và MD5SUM khi điều tra changeset đã ghi nhận.
- [ ] Đã xem status --verbose và history.
- [ ] Đã chạy validate và review update-sql.
- [ ] Đã xác nhận không có tiến trình migration cạnh tranh hoặc lock bất thường.
- [ ] Sau update, đã kiểm tra lại DATABASECHANGELOG và schema thực tế.

Khi đọc trạng thái Liquibase, hãy luôn gắn kết quả với đúng database đích, changelog và bộ lọc của lần chạy. DATABASECHANGELOG cho biết Liquibase đã ghi nhận điều gì; status cho biết changeset nào còn chờ theo cấu hình hiện tại; DATABASECHANGELOGLOCK cho biết trạng thái điều phối tiến trình. Kết hợp ba góc nhìn này với việc kiểm tra schema thực tế sẽ giúp triển khai migration có thể kiểm chứng qua Spring Boot, CI/CD và nhiều môi trường.
