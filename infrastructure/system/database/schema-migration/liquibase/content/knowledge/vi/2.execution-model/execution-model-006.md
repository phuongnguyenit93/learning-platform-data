# Checksum trong quá trình đối chiếu changeset

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, thuộc chương **Mô hình thực thi**, checksum là dấu kiểm tra mà Liquibase dùng để nhận biết định nghĩa của một changeset đã được triển khai có còn khớp với định nghĩa hiện tại trong changelog hay không. Cơ chế này giúp quản lý thay đổi schema và dữ liệu có thể kiểm chứng, giữ lịch sử triển khai nhất quán giữa các môi trường và phát hiện việc sửa lại migration đã chạy.

Sau bài này, người học có thể giải thích checksum được tạo và lưu ở đâu, phân biệt checksum với định danh changeset, đọc lỗi checksum validation, truy tìm nguyên nhân sai khác và chọn cách xử lý an toàn trong dự án có Liquibase, Spring Boot hoặc CI/CD.

## 1. Checksum nằm ở đâu trong mô hình thực thi?

Một changelog là tập hợp các changeset. Mỗi changeset mô tả một đơn vị thay đổi cơ sở dữ liệu, chẳng hạn tạo bảng, thêm cột, nạp dữ liệu tham chiếu hoặc chạy SQL. Liquibase đọc changelog, xác định changeset nào đã được thực thi và quyết định changeset nào cần chạy trong lần cập nhật hiện tại.

Liquibase duy trì lịch sử này trong bảng **DATABASECHANGELOG**. Mỗi changeset đã được ghi nhận có một dòng lịch sử với các thông tin như:

- **ID**, **AUTHOR** và **FILENAME**: nhận diện changeset trong changelog.
- **DATEEXECUTED** và **ORDEREXECUTED**: thời điểm và thứ tự được ghi nhận.
- **EXECTYPE**: loại thực thi được ghi nhận, ví dụ EXECUTED hoặc RERAN.
- **MD5SUM**: checksum của định nghĩa changeset mà Liquibase lưu để đối chiếu ở những lần chạy sau.
- **LIQUIBASE**: phiên bản Liquibase ghi nhận lần thực thi.

Checksum vì vậy gắn với từng changeset đã được ghi vào lịch sử, không phải một mã duy nhất đại diện cho toàn bộ file changelog. Khi đọc một lỗi checksum, cần xác định đúng dòng lịch sử bằng ID, AUTHOR và FILENAME trước khi kết luận.

Cần phân biệt hai khái niệm:

- **Định danh changeset** trả lời câu hỏi “đây là changeset nào?”. Liquibase dựa vào ID, AUTHOR và đường dẫn changelog (có thể được điều khiển bằng logicalFilePath).
- **Checksum** trả lời câu hỏi “định nghĩa hiện tại của changeset này có khớp với nội dung đã được ghi nhận trước đó không?”.

Hai changeset khác nhau có thể có nội dung giống nhau nhưng vẫn là hai định danh khác nhau. Ngược lại, một changeset giữ nguyên định danh nhưng bị sửa nội dung sau khi triển khai có thể phát sinh lỗi checksum.

## 2. Liquibase tạo và đối chiếu checksum như thế nào?

Ở mức khái niệm, quy trình diễn ra theo các bước sau:

1. Liquibase đọc changelog, xử lý các file được include và tạo danh sách changeset cần xét.
2. Với từng changeset, Liquibase tìm bản ghi tương ứng trong DATABASECHANGELOG dựa trên định danh của changeset.
3. Nếu changeset chưa có trong lịch sử, Liquibase xem đó là thay đổi chưa được áp dụng. Khi changeset được thực thi và ghi nhận thành công, Liquibase lưu checksum của định nghĩa đã xử lý vào MD5SUM.
4. Nếu changeset đã có trong lịch sử, Liquibase tính checksum từ định nghĩa hiện tại và so sánh với giá trị đã lưu.
5. Nếu hai giá trị hợp lệ và khớp nhau, changeset được xem là đã áp dụng. Nếu không khớp, Liquibase có thể dừng ở bước validation với lỗi checksum để ngăn việc tiếp tục trên một lịch sử migration không nhất quán.

Một giá trị trong MD5SUM thường có dạng gồm tiền tố phiên bản và phần mã băm, ví dụ **9:giá-trị-mã-băm**. Con số tiền tố biểu thị phiên bản thuật toán checksum mà Liquibase sử dụng. Không nên giả định mọi dự án đều dùng cùng một tiền tố: giá trị cụ thể phụ thuộc phiên bản Liquibase và lịch sử của dự án.

Liquibase dùng checksum để kiểm tra tính nhất quán của định nghĩa changeset trong lịch sử migration. Đây không phải chữ ký bảo mật hay bằng chứng rằng schema thực tế của database chắc chắn giống với changelog. Một người có quyền sửa database vẫn có thể thay đổi schema thủ công mà không làm checksum trong DATABASECHANGELOG tự phản ánh thay đổi đó. Vì vậy, checksum cần được kết hợp với quyền truy cập database, quy trình migration và kiểm tra trạng thái schema khi vận hành.

Checksum cũng không đơn giản là mã băm của từng byte trong toàn bộ file changelog. Cách Liquibase tạo checksum phụ thuộc loại change, định dạng changelog và phiên bản thuật toán. Một số khác biệt về khoảng trắng, comment hoặc metadata có thể được chuẩn hóa hay bỏ qua. Không nên suy luận rằng mọi chỉnh sửa văn bản đều chắc chắn làm checksum đổi, cũng không nên dựa vào việc đổi định dạng để né kiểm tra. Khi có nghi vấn, hãy dùng chính phiên bản Liquibase của dự án để chạy validation và kiểm tra bản ghi lịch sử.

## 3. Các tình huống thường gặp khi đối chiếu

| Tình huống | Kết quả thường thấy | Cách hiểu |
|---|---|---|
| Changeset chưa từng chạy | Chưa có checksum lịch sử để so sánh | Liquibase có thể thực thi changeset rồi ghi nhận checksum |
| Changeset đã chạy và định nghĩa hiện tại khớp | Checksum khớp | Liquibase xem changeset đã được áp dụng |
| Changeset đã chạy nhưng nội dung có thay đổi ảnh hưởng checksum | Checksum không khớp | Validation có thể báo lỗi và dừng cập nhật |
| Changeset có runOnChange được sửa | Liquibase có thể chạy lại changeset theo chính sách runOnChange | Phù hợp với một số đối tượng có thể thay thế như view hoặc stored procedure |
| Bản ghi checksum cũ cần được xử lý theo thay đổi phiên bản thuật toán | Có thể cần cơ chế tương thích hoặc tính lại checksum có kiểm soát | Phải xác định phiên bản Liquibase và nguyên nhân trước khi thao tác |

Một lỗi phổ biến là sửa trực tiếp changeset đã chạy, ví dụ tăng độ dài cột từ VARCHAR(120) lên VARCHAR(255) trong chính changeset tạo bảng ban đầu. Ở môi trường đã triển khai, database vẫn giữ cấu trúc được tạo từ phiên bản cũ, trong khi changelog hiện tại mô tả nội dung mới. Checksum giúp phát hiện sự khác biệt này; nó không tự biến thay đổi mới thành một migration an toàn.

Một tình huống khác là hai môi trường được triển khai từ hai artifact khác nhau. Môi trường thử nghiệm có thể đã chạy một phiên bản changeset, trong khi nhánh phát hành sau đó chỉnh sửa lại chính changeset ấy. Khi artifact mới đến môi trường đã chạy phiên bản trước, Liquibase phát hiện checksum không khớp. Đây là dấu hiệu cần truy tìm lịch sử build và triển khai, không phải lý do để xóa lịch sử ngay lập tức.

## 4. Kiểm tra checksum khi có lỗi

Khi Liquibase báo lỗi validation, trước hết hãy giữ lại nguyên văn thông báo, bao gồm định danh changeset và hai giá trị checksum nếu có. Sau đó kiểm tra trạng thái changelog và lịch sử database bằng cùng phiên bản Liquibase mà ứng dụng hoặc pipeline đang sử dụng.

Các lệnh CLI hữu ích:

~~~bash
liquibase validate
liquibase status --verbose
liquibase history
~~~

- **liquibase validate** kiểm tra changelog và các điều kiện validation mà Liquibase hỗ trợ, trong đó có kiểm tra checksum.
- **liquibase status --verbose** giúp xem các changeset còn chờ áp dụng.
- **liquibase history** hiển thị lịch sử triển khai được Liquibase ghi nhận.

Có thể truy vấn trực tiếp bảng lịch sử để xem checksum của một changeset cụ thể. Cú pháp SQL có thể cần điều chỉnh theo hệ quản trị cơ sở dữ liệu:

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
WHERE ID = '2026-11-19-001'
  AND AUTHOR = 'platform';
~~~

Kết quả cần được đối chiếu với changelog nằm trong artifact đang triển khai và với commit đã được dùng để tạo artifact ở môi trường trước. Nếu một ID xuất hiện với FILENAME khác dự kiến, hãy kiểm tra việc di chuyển hoặc đổi tên file changelog, cấu hình include và logicalFilePath. Thay đổi đường dẫn có thể ảnh hưởng định danh changeset, trong khi checksum chỉ là một phần của cơ chế kiểm soát lịch sử.

Một trình tự điều tra có thể áp dụng:

1. Ghi nhận môi trường, database, phiên bản Liquibase, artifact và commit đang triển khai.
2. Xác định đúng ID, AUTHOR, FILENAME trong thông báo lỗi.
3. Đọc dòng tương ứng trong DATABASECHANGELOG, đặc biệt là MD5SUM và EXECTYPE.
4. So sánh changeset hiện tại với phiên bản changelog từng được triển khai ở môi trường đó.
5. Kiểm tra thay đổi đến từ commit, merge, cherry-pick, build lại artifact, đổi đường dẫn hay nâng cấp Liquibase.
6. Chọn cách khắc phục phù hợp với trạng thái database và lịch sử triển khai; chạy validation lại trước khi tiếp tục.

Không nên chỉ nhìn vào phần mã băm rồi kết luận database bị hỏng. Cần tìm nguyên nhân tạo ra sai khác giữa định nghĩa migration và lịch sử đã ghi nhận.

## 5. Chọn cách xử lý đúng

### 5.1. Tạo changeset mới cho thay đổi schema đã phát sinh

Với migration đã được triển khai ở bất kỳ môi trường dùng chung nào, cách an toàn thông thường là giữ nguyên changeset cũ và tạo changeset mới mô tả thay đổi tiếp theo. Ví dụ, changeset đầu tiên tạo cột email với độ dài 120; yêu cầu mới tăng độ dài lên 255 thì tạo changeset mới dùng modifyDataType.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: platform
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
                  name: email
                  type: VARCHAR(120)
                  constraints:
                    nullable: false

  - changeSet:
      id: 2026-11-19-002
      author: platform
      changes:
        - modifyDataType:
            tableName: customer
            columnName: email
            newDataType: VARCHAR(255)
~~~

Khi triển khai, Liquibase nhận diện changeset đầu tiên đã chạy và tiếp tục với changeset thứ hai. Lịch sử thể hiện được cả thay đổi ban đầu lẫn điều chỉnh sau này. Cách làm này hỗ trợ rollback, điều tra sự cố và tái tạo database ở môi trường mới tốt hơn việc viết lại lịch sử.

Nếu changeset cũ mới chỉ tồn tại ở môi trường cá nhân và chưa được chia sẻ hoặc triển khai, nhóm có thể thống nhất chỉnh sửa trước khi phát hành. Điều kiện quan trọng là mọi môi trường mục tiêu phải có cùng một lịch sử và cùng artifact trước khi changeset được coi là đã phát hành.

### 5.2. Khôi phục định nghĩa đã triển khai

Nếu changeset bị sửa nhầm sau khi đã triển khai, hãy khôi phục nội dung của changeset về đúng phiên bản đã được phát hành. Sau đó đưa yêu cầu mới vào changeset mới. Việc khôi phục cần dựa trên commit hoặc artifact có thể xác minh, không dựa vào phỏng đoán nội dung cũ.

### 5.3. Dùng runOnChange cho đối tượng cần thay thế

Một số đối tượng database được quản lý theo kiểu cập nhật định nghĩa, chẳng hạn view hoặc stored procedure. Trong trường hợp đó, **runOnChange: true** có thể phù hợp vì Liquibase chạy lại changeset khi checksum của nó thay đổi.

Ví dụ với formatted SQL:

~~~sql
--liquibase formatted sql
--changeset platform:active-customer-view runOnChange:true
CREATE OR REPLACE VIEW active_customer AS
SELECT id, email
FROM customer
WHERE status = 'ACTIVE';
~~~

Cách này phù hợp khi câu lệnh được thiết kế để thay thế đối tượng hiện có và có thể chạy lặp lại an toàn theo quy tắc của hệ quản trị cơ sở dữ liệu. Không nên bật runOnChange đại trà cho mọi migration tạo bảng, thêm cột hoặc nạp dữ liệu một lần. Với các thay đổi cấu trúc có tính tuần tự, changeset mới thường dễ kiểm soát hơn.

**runAlways** có mục đích khác: yêu cầu một changeset được chạy trong mỗi lần cập nhật phù hợp. Nó không nên được xem là công cụ sửa lỗi checksum. Hãy chọn thuộc tính dựa trên hành vi mong muốn và kiểm tra cách phiên bản Liquibase đang dùng xử lý changeset đó.

### 5.4. Khai báo validCheckSum khi có lý do được phê duyệt

**validCheckSum** cho phép khai báo một checksum cụ thể được chấp nhận cho changeset. Cơ chế này có thể hữu ích khi nhóm đã xác minh một thay đổi lịch sử có chủ đích và cần cho phép Liquibase chấp nhận checksum cũ hoặc checksum được xác định rõ.

Ví dụ minh họa trong XML:

~~~xml
<changeSet id="2026-11-19-001" author="platform">
    <validCheckSum>8:old-checksum-value</validCheckSum>
    <!-- Các change đã được định nghĩa -->
</changeSet>
~~~

Giá trị ví dụ phải được thay bằng checksum thực tế đã xác minh từ lịch sử của hệ thống. **validCheckSum** cho phép validation chấp nhận giá trị được liệt kê; nó không tự chạy lại changeset và cũng không đồng bộ schema thực tế của database. Tránh dùng giá trị chấp nhận mọi checksum như **1:any** trong vận hành thông thường vì sẽ làm mất khả năng phát hiện nhiều chỉnh sửa ngoài dự kiến.

### 5.5. Dùng clear-checksums trong trường hợp được kiểm soát

Lệnh **clear-checksums** xóa các giá trị checksum đang lưu trong bảng DATABASECHANGELOG. Trong lần cập nhật tiếp theo, Liquibase tính lại checksum và ghi lại giá trị mới cho các changeset đã được ghi nhận.

~~~bash
liquibase clear-checksums
liquibase update
~~~

Lệnh này không chạy lại tất cả changeset đã triển khai. Nó tác động đến metadata checksum trong lịch sử để Liquibase có thể tính lại các giá trị. Vì thế, nếu changelog hiện tại đã bị sửa sai, thao tác xóa checksum rồi cập nhật có thể khiến định nghĩa mới được chấp nhận trong khi database vẫn đang phản ánh lần triển khai cũ. Sai khác giữa schema và changelog có thể bị che khuất.

Chỉ dùng clear-checksums khi đã hiểu nguyên nhân, xác định phạm vi ảnh hưởng, thống nhất với người quản trị database và có kế hoạch kiểm chứng sau thao tác. Không sửa trực tiếp cột MD5SUM bằng SQL để ép hai giá trị khớp nhau. Cũng không chạy lệnh này như phản xạ đầu tiên mỗi khi gặp lỗi checksum.

## 6. Quản lý checksum giữa nhiều môi trường

Trong quy trình phát triển thông thường, cùng một changeset được đưa qua môi trường phát triển, kiểm thử, staging và production. Khi mọi môi trường dùng cùng artifact và cùng phiên bản Liquibase, checksum của cùng một định nghĩa changeset phải được đối chiếu nhất quán. Các môi trường có thể có dữ liệu khác nhau, nhưng dữ liệu khác nhau không phải lý do để sửa nội dung changeset đã phát hành.

Một số nguyên tắc giúp tránh sai khác:

- Đóng gói changelog cùng phiên bản ứng dụng hoặc artifact migration có thể truy nguyên về commit cụ thể.
- Dùng cùng phiên bản Liquibase trong máy phát triển, pipeline CI/CD và môi trường triển khai; quản lý nâng cấp phiên bản như một thay đổi có kiểm thử.
- Không chỉnh sửa changeset đã phát hành. Mọi thay đổi schema tiếp theo được bổ sung bằng changeset mới, trừ trường hợp thiết kế rõ ràng cho runOnChange.
- Giữ ổn định đường dẫn changelog và logicalFilePath để định danh changeset không thay đổi ngoài dự kiến.
- Không dùng nội dung changelog khác nhau theo từng môi trường chỉ để xử lý dữ liệu riêng. Dùng contexts, labels, dbms hoặc preconditions đúng mục đích và kiểm tra tác động của chúng.
- Chỉ cho một tiến trình triển khai chịu trách nhiệm chạy migration tại một thời điểm. Nếu nhiều bản sao ứng dụng Spring Boot cùng tự động chạy Liquibase khi khởi động, cần kiểm soát thứ tự triển khai và cơ chế khóa để tránh cạnh tranh cập nhật.

Tiền tố checksum cũng nhắc nhóm rằng phiên bản thuật toán có thể thay đổi theo phiên bản Liquibase. Khi nâng cấp Liquibase, hãy đọc ghi chú tương thích của phiên bản đích, chạy validation trên bản sao database đại diện và kiểm tra cách phiên bản đó xử lý checksum cũ. Không tự sửa tiền tố hoặc phần mã băm trong DATABASECHANGELOG. Việc dùng một phiên bản Liquibase nhất quán trong pipeline giúp tránh việc các môi trường diễn giải lịch sử theo các phiên bản công cụ khác nhau.

## 7. Tích hợp với Spring Boot và CI/CD

Spring Boot có thể tự chạy Liquibase khi ứng dụng khởi động nếu Liquibase được bật và có changelog hợp lệ trên classpath. Cấu hình thường gặp:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi ứng dụng khởi động, Liquibase đọc changelog và đối chiếu với DATABASECHANGELOG của database được cấu hình. Nếu checksum của changeset đã triển khai không hợp lệ, quá trình khởi động hoặc cập nhật có thể thất bại. Vì vậy, lỗi checksum ở production cần được xử lý như một vấn đề phát hành migration, không nên khắc phục bằng cách tự động xóa lịch sử để ứng dụng khởi động được.

Với hệ thống có nhiều instance, nhóm thường dễ kiểm soát hơn khi tách migration thành một bước triển khai riêng: pipeline chạy validation, triển khai migration bằng một job được kiểm soát, xác minh kết quả rồi mới đưa các instance ứng dụng mới vào phục vụ. Nếu chọn để Spring Boot chạy migration khi khởi động, phải bảo đảm cấu hình và chiến lược triển khai kiểm soát được việc nhiều instance cùng khởi chạy.

Một pipeline CI/CD có thể áp dụng trình tự sau:

1. Checkout commit và tạo artifact chứa changelog đúng với phiên bản ứng dụng.
2. Chạy **liquibase validate** bằng phiên bản Liquibase đã được khóa trong dự án.
3. Chạy migration trên database kiểm thử mới để kiểm tra khả năng tái tạo schema.
4. Chạy migration trên database nâng cấp từ phiên bản trước để kiểm tra đường nâng cấp thực tế.
5. Khi phát hành, dùng chính artifact đã kiểm thử và triển khai migration theo một bước có kiểm soát.
6. Ghi nhận phiên bản artifact, commit, phiên bản Liquibase và kết quả triển khai để có thể truy nguyên khi checksum khác nhau giữa các môi trường.

Kiểm tra trên database mới là chưa đủ: một changelog có thể dựng được schema từ đầu nhưng vẫn thất bại khi nâng cấp một database đã có lịch sử. Do đó, kiểm thử cả luồng cài mới và luồng nâng cấp giúp phát hiện sớm changeset bị sửa sau triển khai.

## 8. Checklist trước khi xử lý lỗi checksum

Trước khi cho phép pipeline tiếp tục, hãy xác nhận:

- Đã xác định đúng changeset qua ID, AUTHOR và FILENAME.
- Đã kiểm tra MD5SUM, EXECTYPE và thời điểm triển khai trong DATABASECHANGELOG.
- Đã xác định artifact và commit thực sự được triển khai ở môi trường gặp lỗi.
- Đã so sánh changelog hiện tại với phiên bản từng được triển khai.
- Đã kiểm tra khác biệt phiên bản Liquibase và đường dẫn changelog.
- Đã chọn phương án có thể giải thích và kiểm chứng: khôi phục nội dung cũ, thêm changeset mới, dùng runOnChange hoặc validCheckSum có phê duyệt, hay tính lại checksum trong một quy trình kiểm soát.
- Đã chạy validation và kiểm tra trạng thái database sau khi xử lý.

Checksum là cơ chế giúp Liquibase phát hiện thay đổi ngoài dự kiến trong định nghĩa changeset đã được ghi nhận. Khi hiểu rõ quan hệ giữa định danh, checksum và DATABASECHANGELOG, nhóm có thể bảo vệ tính bất biến của migration, phát hiện sai khác giữa artifact và lịch sử triển khai, đồng thời xử lý nâng cấp Liquibase và phát hành qua nhiều môi trường một cách có kiểm chứng.

