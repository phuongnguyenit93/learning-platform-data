# Chấp nhận checksum có kiểm soát bằng validCheckSum

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Người học cần thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Checksum và lịch sử**, tập trung vào thuộc tính **validCheckSum**: khi nào một checksum khác với giá trị đã ghi trong database có thể được chấp nhận có kiểm soát, cách khai báo, cách xác minh và những giới hạn của cơ chế này.

Checksum mismatch thường là tín hiệu cho biết nội dung changeset hiện tại khác nội dung Liquibase đã ghi nhận khi triển khai. Tuy nhiên, không phải mọi khác biệt đều là lỗi SQL, và cũng không phải mọi checksum khác nhau đều nên được chấp nhận. Nếu dùng validCheckSum thiếu kiểm soát, một môi trường có thể tiếp tục với schema cũ trong khi source changelog mô tả schema mới.

Sau bài học, bạn có thể:

- Giải thích checksum, trường MD5SUM và mối liên hệ với DATABASECHANGELOG.
- Phân biệt **checksum mismatch**, **changeset identity mismatch** và **schema drift**.
- Dùng validCheckSum để chấp nhận một checksum cụ thể đã được xác minh.
- Hiểu checksum version prefix và vì sao cần lấy giá trị thực từ đúng phiên bản Liquibase.
- Phân biệt validCheckSum với clear-checksums, runOnChange và runAlways.
- Lập quy trình review, kiểm chứng trên nhiều môi trường và giữ lịch sử migration có thể giải thích.

## 2. Checksum của Liquibase là gì?

**Checksum** là giá trị Liquibase tính từ nội dung changeset theo quy tắc và phiên bản checksum của Liquibase. Khi changeset được thực thi, Liquibase lưu checksum trong cột **MD5SUM** của bảng **DATABASECHANGELOG** cùng với định danh và thông tin lịch sử thực thi.

Ở lần chạy sau, Liquibase so sánh checksum được tính từ changelog hiện tại với checksum đã lưu. Nếu chúng không tương thích với quy tắc kiểm tra của phiên bản đang chạy, Liquibase có thể báo lỗi **checksum validation failed**.

~~~text
Source changelog hiện tại
        |
        v
Liquibase tính checksum hiện tại
        |
        v
Đối chiếu với DATABASECHANGELOG.MD5SUM
        |
        +-- Khớp hoặc được chấp nhận --> tiếp tục
        |
        +-- Không khớp               --> báo checksum validation error
~~~

Checksum giúp phát hiện một số thay đổi đối với nội dung changeset đã triển khai. Nó là một phần của cơ chế bảo vệ tính nhất quán lịch sử, **không phải bản sao SQL, bản ghi mọi câu lệnh đã chạy hoặc chữ ký bảo mật của toàn bộ database**.

### 2.1. Checksum không chứng minh schema đang đúng

Một checksum khớp cho biết nội dung changeset được kiểm tra phù hợp với giá trị lịch sử theo cơ chế Liquibase. Nó không chứng minh:

- DBA không thay đổi bảng bằng SQL ngoài Liquibase.
- Một job khác không sửa dữ liệu sau migration.
- Index có đúng trạng thái hoặc constraint đang được thực thi.
- Dữ liệu nghiệp vụ thỏa các quy tắc mới.
- Mọi môi trường có cùng schema và cùng dữ liệu.

Muốn xác minh trạng thái database cần kết hợp DATABASECHANGELOG với catalog của DBMS, truy vấn đối soát, validate, SQL dự kiến và kiểm thử nghiệp vụ.

### 2.2. Checksum không phải công cụ bảo mật

Không sử dụng checksum Liquibase như cơ chế xác thực nguồn phát hành, chữ ký số artifact hoặc bảo vệ chống người có quyền sửa database. Quyền truy cập, kiểm soát thay đổi, review Git, chữ ký artifact và audit cần được quản lý riêng.

## 3. DATABASECHANGELOG lưu gì?

DATABASECHANGELOG là bảng lịch sử do Liquibase quản lý. Một row thường chứa các thông tin nhận diện và theo dõi changeset như:

- **ID:** giá trị id của changeset.
- **AUTHOR:** tác giả khai báo changeset.
- **FILENAME:** đường dẫn changelog dùng để nhận diện.
- **DATEEXECUTED:** thời điểm ghi nhận thực thi.
- **ORDEREXECUTED:** thứ tự thực thi theo lịch sử.
- **EXECTYPE:** loại thực thi như EXECUTED, RERAN hoặc MARK_RAN.
- **MD5SUM:** checksum được ghi nhận.
- **TAG:** tag nếu changeset liên quan đến mốc triển khai.
- Các trường khác phục vụ mô tả, deployment hoặc theo dõi theo phiên bản Liquibase.

Tên và chi tiết trường có thể thay đổi theo phiên bản; khi điều tra, cần xem schema DATABASECHANGELOG thực tế của môi trường.

**Định danh changeset** thường dựa trên tổ hợp **id + author + đường dẫn changelog**; nếu dùng logicalFilePath thì đường dẫn logic có thể được dùng thay cho đường dẫn vật lý. Checksum là một phần kiểm tra nội dung, không phải định danh duy nhất của changeset.

Điều này tạo ra hai câu hỏi khác nhau:

1. Liquibase có đang tìm đúng changeset trong lịch sử không?
2. Nội dung changeset hiện tại có được chấp nhận so với checksum đã lưu không?

validCheckSum chỉ liên quan đến câu hỏi thứ hai. Nó không sửa lỗi sai ID, author hoặc đường dẫn nhận diện.

## 4. Vì sao checksum có thể khác?

Một checksum mismatch có thể xuất hiện trong nhiều hoàn cảnh:

| Nguyên nhân | Điều có thể đã xảy ra | Hướng điều tra |
|---|---|---|
| Sửa SQL/changes trong changeset đã chạy | Nội dung thực thi dự kiến đã thay đổi | So sánh Git và lịch sử phát hành |
| Sửa change type hoặc thuộc tính ảnh hưởng checksum | Liquibase tính lại nội dung changeset khác trước | Xác định thay đổi có ảnh hưởng SQL hoặc ý nghĩa không |
| Thay đổi do nhánh Git hoặc merge | Một môi trường đã chạy phiên bản nội dung khác | Đối chiếu commit/artifact từng môi trường |
| Nâng cấp Liquibase | Quy tắc/phiên bản checksum được cập nhật hoặc tính lại | Kiểm tra version prefix và tài liệu phiên bản |
| Tệp include hoặc logical path được tái cấu trúc | Có thể ảnh hưởng nhận diện changeset thay vì chỉ checksum | Kiểm tra ID, author, FILENAME và logicalFilePath |
| Có chỉnh sửa thủ công hoặc thay đổi ngoài quy trình | Source và lịch sử triển khai không còn đồng bộ | Điều tra nguồn thay đổi và schema thực tế |

Không nên kết luận ngay rằng Liquibase bị lỗi. Checksum mismatch thường là dấu hiệu hữu ích cho thấy cần xem xét lịch sử thay đổi.

### Cần phân biệt ba loại vấn đề

- **Checksum mismatch:** changeset được nhận diện nhưng checksum hiện tại không được chấp nhận.
- **Identity mismatch:** Liquibase không còn nhận diện đúng changeset cũ do id, author hoặc đường dẫn khác.
- **Schema drift:** schema/data thực tế khác trạng thái mà changelog mong đợi.

Một validCheckSum có thể xử lý trường hợp checksum mismatch đã được hiểu rõ; nó không sửa identity mismatch hoặc schema drift.

## 5. validCheckSum dùng để làm gì?

**validCheckSum** cho phép khai báo một hoặc nhiều checksum cụ thể mà Liquibase được phép coi là hợp lệ đối với changeset. Khi checksum đang được lưu trong DATABASECHANGELOG nằm trong danh sách được chấp nhận theo cú pháp và phiên bản hỗ trợ, Liquibase có thể vượt qua bước xác thực checksum đó.

Mục đích là **chấp nhận một khác biệt lịch sử đã được điều tra và phê duyệt**, không phải yêu cầu Liquibase chạy lại changeset và cũng không phải bỏ qua mọi lỗi migration.

Ví dụ YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: schema-team
      validCheckSum: "8:CHECKSUM_DA_XAC_MINH"
      changes:
        - createTable:
            tableName: feature_flag
            columns:
              - column:
                  name: flag_key
                  type: VARCHAR(100)
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

8:CHECKSUM_DA_XAC_MINH chỉ là **giá trị minh họa**, không phải checksum thật và không được sao chép vào dự án. Phải thay bằng checksum thực tế đã được thu thập từ lỗi, lịch sử hoặc công cụ tương ứng của phiên bản Liquibase đang dùng.

Ví dụ này mô tả vị trí khai báo validCheckSum trong changeset. Cú pháp và cách biểu diễn nhiều giá trị có thể phụ thuộc định dạng changelog và phiên bản Liquibase; cần chạy validate và thử trên bản Liquibase của dự án.

### validCheckSum không có nghĩa là gì?

- Không có nghĩa thay đổi SQL cũ sẽ được chạy lại.
- Không tự sửa schema hoặc dữ liệu.
- Không cập nhật mã nguồn changeset thành một lịch sử mới đã được thực thi.
- Không bảo đảm checksum được chấp nhận ở mọi phiên bản Liquibase.
- Không thay thế backup, rollback hoặc forward fix.
- Không sửa lỗi nhận diện changeset do đổi ID, author hoặc đường dẫn.

**Nó chỉ là một ngoại lệ có khai báo trong kiểm tra checksum.**

## 6. Khi nào có thể cân nhắc validCheckSum?

Chỉ cân nhắc sau khi đã xác định **vì sao checksum cũ khác checksum hiện tại** và chứng minh việc chấp nhận khác biệt không làm sai ý nghĩa migration.

Một số tình huống có thể được xem xét:

1. **Khác biệt nội dung đã được xác định là không làm thay đổi kết quả database**, nhưng vẫn tạo ra checksum khác theo cơ chế tính của phiên bản cụ thể.
2. **Một nhóm môi trường có lịch sử checksum đã biết và được phê duyệt**, còn nội dung database thực tế đã được xác minh tương đương.
3. **Có thay đổi lịch sử hợp lệ cần duy trì khả năng nâng cấp**, nhưng không thể sửa lại DATABASECHANGELOG cũ theo cách thủ công.
4. **Nâng cấp Liquibase hoặc xử lý checksum version** đã được kiểm chứng theo tài liệu của phiên bản, và nhóm cần chấp nhận một checksum cụ thể để hỗ trợ chuyển tiếp.

Các tình huống này không phải giấy phép chỉnh sửa tùy ý changeset đã triển khai. Cần có bằng chứng và reviewer chịu trách nhiệm.

### Trường hợp không nên dùng

- SQL trong changeset cũ đã bị thay đổi về logic và database hiện tại chưa nhận thay đổi mới.
- Thay đổi làm đổi kiểu cột, constraint, index, dữ liệu seed hoặc quy tắc nghiệp vụ.
- Không biết môi trường nào đã chạy nội dung nào.
- Checksum mismatch xuất hiện cùng dấu hiệu schema drift chưa được điều tra.
- Mục tiêu chỉ là làm cho pipeline chạy xanh.
- Có thể giải quyết đúng bằng một changeset mới nhưng nhóm muốn tránh thêm lịch sử.

Nếu nội dung thay đổi có ảnh hưởng thực tế đến database, **tạo changeset mới** thường là hướng đúng. validCheckSum không thể thay thế migration cần thiết.

## 7. Cách lấy checksum đúng

Không tự tính checksum bằng MD5 bên ngoài hoặc đoán giá trị từ nội dung YAML. Liquibase sử dụng quy tắc checksum riêng theo phiên bản, có thể bao gồm version prefix và cách chuẩn hóa nội dung.

Nguồn đáng tin cậy để điều tra gồm:

- Giá trị trong trường **MD5SUM** của row changeset tương ứng trong DATABASECHANGELOG.
- Giá trị checksum hiện tại hoặc checksum expected được nêu trong thông báo lỗi Liquibase.
- Kết quả công cụ Liquibase phù hợp với phiên bản đang chạy, khi phiên bản đó cung cấp lệnh hoặc cách hiển thị checksum.
- Bản log triển khai trước và artifact changelog đã được lưu.

Ví dụ thông báo lỗi minh họa:

~~~text
Validation Failed:
  1 changesets check sum
  path/to/changelog.yaml::2026-11-19-001::schema-team
  was: 8:CHECKSUM_CU
  but is now: 8:CHECKSUM_MOI
~~~

Đây là **dữ liệu giả lập để giải thích cách đọc lỗi**. Trong thực tế:

- **was** thường chỉ checksum đã được ghi trong lịch sử.
- **but is now** chỉ checksum tính từ changelog hiện tại.
- Phần path, ID và author giúp xác định changeset.
- Version prefix phải được giữ nguyên khi dùng checksum làm giá trị validCheckSum.

Không copy checksum từ một database khác chỉ vì cùng tên changeset. Hai môi trường có thể đã chạy nội dung khác hoặc khác lịch sử; cần xác minh từng môi trường.

## 8. Version prefix trong checksum

Checksum Liquibase có thể có dạng tổng quát:

~~~text
<checksum-version>:<checksum-value>
~~~

Ví dụ minh họa:

~~~text
8:abc123...
~~~

Số ở đầu biểu thị **phiên bản thuật toán/định dạng checksum** được Liquibase sử dụng, không phải phiên bản ứng dụng hay số release. Khi Liquibase thay đổi cách tính checksum qua các phiên bản, cùng một changeset có thể được xử lý theo version checksum khác.

Do đó:

- Không bỏ version prefix khi ghi validCheckSum nếu định dạng yêu cầu.
- Không tự thay prefix bằng số phiên bản Liquibase.
- Không giả định checksum bắt đầu bằng một con số cố định ở mọi phiên bản.
- Không so sánh riêng phần chuỗi phía sau prefix mà bỏ qua cách tính tương ứng.
- Khi nâng cấp Liquibase, kiểm tra hành vi checksum trên database có lịch sử trước khi nâng production.

**Version prefix là thông tin kỹ thuật của checksum.** Lấy giá trị từ đúng lỗi hoặc công cụ Liquibase đang dùng, không lấy từ ví dụ trong tài liệu.

## 9. validCheckSum không chạy lại changeset

Giả sử changeset đã được triển khai và DATABASECHANGELOG lưu checksum cũ. Source hiện tại có checksum mới, nhưng nhóm đã chứng minh khác biệt được chấp nhận. Khi khai báo validCheckSum chứa checksum cũ, Liquibase có thể chấp nhận lịch sử đó.

Điều này **không có nghĩa** các câu lệnh trong changeset được chạy lại.

~~~text
Lần triển khai ban đầu:
  changeset 001 --> tạo cột status_code
  DATABASECHANGELOG.MD5SUM = checksum cũ

Sau đó source có checksum mới:
  Liquibase so sánh checksum hiện tại với lịch sử
  checksum cũ được validCheckSum chấp nhận
  --> tiếp tục kiểm tra các changeset khác
  --> không chạy lại changeset 001 chỉ vì validCheckSum
~~~

Nếu database chưa từng chạy changeset này, Liquibase sẽ xử lý changeset theo luồng update bình thường với nội dung source hiện tại. Vì vậy, có thể xảy ra khác biệt giữa database cũ đã chạy nội dung trước đó và database mới dựng từ source hiện tại nếu sự khác biệt thực chất ảnh hưởng kết quả.

Đây là lý do phải giới hạn validCheckSum cho khác biệt đã chứng minh là tương đương, hoặc có kế hoạch migration mới để đưa database cũ đến trạng thái hiện tại.

## 10. validCheckSum và clear-checksums khác nhau

Hai cơ chế này thường bị dùng nhầm khi gặp checksum mismatch.

| Tiêu chí | validCheckSum | clear-checksums |
|---|---|---|
| Cách hoạt động | Khai báo checksum cụ thể được chấp nhận cho changeset | Xóa các giá trị checksum đã lưu theo phạm vi lệnh Liquibase |
| Phạm vi | Gắn với changeset khai báo | Thường ảnh hưởng checksum lưu trong DATABASECHANGELOG của database |
| Mục tiêu | Chấp nhận ngoại lệ lịch sử có kiểm soát | Yêu cầu Liquibase tính lại checksum ở lần update phù hợp tiếp theo |
| Có chạy lại SQL changeset đã chạy không? | Không chỉ vì khai báo validCheckSum | Không; không tự chạy lại các changeset đã được ghi nhận |
| Có sửa schema/data không? | Không | Không |
| Rủi ro | Chấp nhận nhầm checksum và che giấu nội dung khác | Tác động rộng, có thể làm mất bằng chứng checksum cũ |
| Cách dùng | Chỉ cho checksum cụ thể đã xác minh | Chỉ trong quy trình quản trị checksum có lý do và kiểm soát |

**clear-checksums không phải phiên bản “mạnh hơn” của validCheckSum.** Nó không sửa SQL, không khôi phục dữ liệu và không làm schema trở về trạng thái mà changelog mô tả.

Nếu chỉ một changeset có khác biệt đã được điều tra, validCheckSum có phạm vi thể hiện ý định hẹp hơn. Nếu vấn đề liên quan thay đổi thuật toán checksum khi nâng phiên bản Liquibase, cần làm theo hướng dẫn nâng cấp chính thức thay vì tự chạy clear-checksums hàng loạt.

## 11. validCheckSum và runOnChange, runAlways

| Cơ chế | Ý nghĩa | Có phải cách chấp nhận checksum cũ? |
|---|---|---|
| **validCheckSum** | Chấp nhận checksum được khai báo cho changeset | Có, đúng mục đích |
| **runOnChange** | Cho phép changeset được chạy lại khi nội dung thay đổi theo cơ chế Liquibase | Không |
| **runAlways** | Cho phép changeset chạy mỗi lần update phù hợp | Không |
| **clear-checksums** | Xóa checksum đã lưu để Liquibase tính lại theo quy trình tiếp theo | Không |

runOnChange thường phù hợp với đối tượng được thiết kế để thay thế nội dung, ví dụ một số view hoặc stored procedure, khi thay đổi source cần được triển khai lại. Nó không phải lựa chọn chung cho changeset DDL/DML đã phát hành.

runAlways phù hợp với những thao tác được thiết kế rõ ràng để chạy ở mỗi lần update; không dùng nó cho thao tác không idempotent như INSERT seed có thể nhân bản dữ liệu.

validCheckSum chỉ xử lý kiểm tra checksum. Nếu nhóm muốn changeset chạy lại, cần một cơ chế và mục tiêu khác, có đánh giá tác động cụ thể.

## 12. Phân biệt checksum mismatch với thay đổi đường dẫn

Liquibase nhận diện changeset bằng ID, author và đường dẫn changelog hoặc logicalFilePath. Giả sử:

~~~text
Trước khi di chuyển:
  db/changelog/legacy/customer.yaml
  id: 2026-11-19-001
  author: schema-team

Sau khi di chuyển:
  db/changelog/releases/2026-11/customer.yaml
  id: 2026-11-19-001
  author: schema-team
~~~

Dù nội dung và checksum giống nhau, việc đổi đường dẫn có thể khiến Liquibase nhận diện thành một changeset khác nếu đường dẫn logic không được bảo toàn. Đây là **vấn đề identity**, không phải đơn thuần checksum mismatch.

validCheckSum không sửa được vấn đề này. Nếu tái cấu trúc file đã triển khai, cần xem xét logicalFilePath theo phiên bản Liquibase, giữ định danh cũ và kiểm tra trên database có DATABASECHANGELOG trước khi áp dụng.

Không dùng validCheckSum để xử lý một changeset bị nhận diện thành changeset mới, bởi điều đó không khôi phục đúng định danh lịch sử.

## 13. Ví dụ kiểm soát checksum cũ

Giả sử một changeset tạo view report_order_summary. Một nhóm đã phát hành nội dung changeset, sau đó chỉnh sửa phần chú thích hoặc một khác biệt nội dung đã được xác minh là không thay đổi định nghĩa view thực tế, nhưng checksum theo phiên bản đang dùng khác.

Sau khi thu thập được checksum cũ từ DATABASECHANGELOG và xác minh SQL/schema thực tế tương đương, nhóm có thể cân nhắc khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-010
      author: reporting-team
      validCheckSum: "8:CHECKSUM_CU_DA_XAC_MINH"
      changes:
        - createView:
            viewName: report_order_summary
            replaceIfExists: true
            selectQuery: >
              SELECT status, COUNT(*) AS total
              FROM purchase_order
              GROUP BY status
~~~

CHECKSUM_CU_DA_XAC_MINH là placeholder, phải thay bằng checksum thật được xác minh. Ví dụ createView và replaceIfExists cũng phụ thuộc khả năng hỗ trợ của Liquibase/DBMS; cần kiểm tra phiên bản cụ thể.

Cần đặc biệt chú ý: nếu phần SELECT thực sự đã đổi logic, chấp nhận checksum cũ **không cập nhật view trên database cũ**. Trong trường hợp đó, tạo changeset mới để thay đổi view hoặc dùng runOnChange nếu đối tượng và quy trình đã được thiết kế phù hợp. Không sử dụng validCheckSum để giả vờ database cũ đã nhận nội dung mới.

## 14. Có thể khai báo nhiều checksum không?

Trong một số định dạng và phiên bản Liquibase, một changeset có thể chấp nhận nhiều checksum đã biết. Khi đó cần khai báo theo cú pháp được hỗ trợ chính thức của định dạng changelog đang dùng.

Một cách biểu diễn khái niệm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-011
      author: schema-team
      validCheckSum:
        - "8:CHECKSUM_CU_A"
        - "8:CHECKSUM_CU_B"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: migrated_at
                  type: TIMESTAMP
~~~

Các checksum trong ví dụ là giả lập. Trước khi sử dụng danh sách, phải xác nhận cú pháp YAML và khả năng hỗ trợ trong đúng phiên bản Liquibase. Không tự suy ra rằng mọi dạng XML, YAML, JSON và mọi bản phân phối đều chấp nhận cấu trúc giống nhau.

**Mỗi giá trị được thêm vào danh sách làm mở rộng tập lịch sử được chấp nhận.** Vì vậy, mỗi checksum cần có nguồn gốc, môi trường tương ứng, lý do và người phê duyệt. Không đưa checksum vào danh sách chỉ vì một pipeline bất kỳ báo mismatch.

## 15. Quy trình điều tra checksum mismatch

Khi pipeline báo checksum validation failed, không sửa changelog ngay. Hãy đi theo trình tự:

### Bước 1: xác định chính xác changeset

Ghi lại:

- Đường dẫn changelog hoặc logicalFilePath.
- ID và author.
- Checksum **was** trong lỗi.
- Checksum **but is now** trong lỗi.
- Phiên bản Liquibase, driver và DBMS.
- Git commit/artifact được dùng khi triển khai lần trước và lần hiện tại.

### Bước 2: đối chiếu lịch sử source

- Xem lịch sử Git của đúng changeset.
- So sánh nội dung source đã phát hành với source hiện tại.
- Xác định có thay đổi SQL, change type, thuộc tính hay cấu trúc không.
- Kiểm tra thay đổi có xuất phát từ merge conflict, cherry-pick hoặc nhánh phát hành không.

### Bước 3: xác minh database thực tế

- Đối chiếu DATABASECHANGELOG.
- Kiểm tra schema/catalog của DBMS.
- Xác minh view, constraint, index hoặc dữ liệu liên quan.
- Tìm thay đổi thủ công ngoài Liquibase nếu có bằng chứng.

### Bước 4: phân loại khác biệt

| Phân loại | Ví dụ | Hướng giải quyết |
|---|---|---|
| Chỉ khác checksum, kết quả thực tế tương đương và có bằng chứng | Khác biệt được xác minh không đổi kết quả migration | Có thể cân nhắc validCheckSum |
| Nội dung SQL thực sự cần thay đổi | Thêm constraint, đổi biểu thức, sửa dữ liệu | Tạo changeset mới |
| Khác do thay đổi đường dẫn/identity | Di chuyển tệp changelog | Xử lý logicalFilePath/định danh |
| Database drift do DBA hoặc ứng dụng sửa ngoài | Schema khác source | Điều tra và migration sửa drift |
| Khác do nâng cấp Liquibase/checksum version | Prefix hoặc checksum được tính lại | Theo hướng dẫn version, thử trên bản sao |
| Không xác định được nội dung đã chạy | Thiếu artifact/log lịch sử | Dừng và thu thập bằng chứng; không chấp nhận checksum đoán |

### Bước 5: review quyết định

Một thay đổi validCheckSum cần có lý do rõ, checksum chính xác, môi trường bị ảnh hưởng, bằng chứng tương đương và phương án kiểm chứng sau khi chấp nhận.

## 16. Quy trình sử dụng validCheckSum an toàn

Có thể áp dụng quy trình sau khi đã xác định tình huống thực sự phù hợp:

1. **Chụp lại bằng chứng:** lưu thông báo lỗi, checksum cũ/mới, commit, phiên bản Liquibase và thông tin database.
2. **Xác minh nội dung cũ:** tìm artifact changelog đã chạy ở môi trường có checksum cũ.
3. **So sánh nội dung:** xác định thay đổi là vô hại về kết quả hay đã thay đổi SQL/ý nghĩa migration.
4. **Kiểm tra schema/data:** xác nhận trạng thái thực tế trên từng môi trường có liên quan.
5. **Lấy checksum chính xác:** dùng giá trị từ lịch sử hoặc thông báo lỗi; giữ version prefix.
6. **Đánh giá phạm vi:** chỉ chấp nhận checksum đã biết, không mở rộng wildcard hoặc chấp nhận mơ hồ.
7. **Thêm validCheckSum:** đặt ở đúng changeset và đúng cú pháp được phiên bản hỗ trợ.
8. **Review Git:** yêu cầu người phụ trách database và release review lý do, checksum, môi trường.
9. **Validate và thử trên bản sao:** kiểm tra một database có checksum cũ và một database mới.
10. **Hậu kiểm:** xác nhận Liquibase vượt kiểm tra checksum và schema thực tế vẫn đáp ứng yêu cầu.

Nếu ở bước 3 phát hiện SQL có thay đổi nghiệp vụ, **dừng việc dùng validCheckSum như cách giải quyết duy nhất**. Hãy tạo changeset mới hoặc một kế hoạch chuyển đổi rõ ràng.

## 17. Nhiều môi trường có checksum khác nhau

Một ứng dụng có thể có DEV, TEST, STAGING và PRODUCTION. Mỗi database có DATABASECHANGELOG riêng. Nếu các môi trường từng chạy những artifact khác nhau, checksum của cùng một changeset có thể không giống nhau.

Ví dụ:

| Môi trường | Checksum đã lưu | Source hiện tại | Trạng thái điều tra |
|---|---|---|---|
| DEV | Checksum B | Checksum C | Đã biết DEV chạy nhánh thử nghiệm |
| STAGING | Checksum C | Checksum C | Khớp |
| PRODUCTION | Checksum A | Checksum C | Cần xác minh artifact phát hành trước |

Bảng này chỉ minh họa. Không được thêm A và B vào validCheckSum nếu chưa biết chúng đại diện cho nội dung nào.

Một quy trình đa môi trường:

- Thu thập checksum thực tế ở từng môi trường.
- Đối chiếu Git commit và artifact đã chạy.
- Phân biệt khác biệt vô hại với khác biệt SQL thực tế.
- Nếu nhiều checksum lịch sử đều được chứng minh tương đương, cân nhắc chấp nhận chính xác các giá trị cần thiết theo cú pháp hỗ trợ.
- Nếu có môi trường thực sự chưa nhận thay đổi SQL, tạo changeset mới để đưa nó tới trạng thái mong muốn.
- Sau xử lý, triển khai cùng một artifact đã review cho các môi trường tiếp theo.

Không xem một lần chạy thành công ở DEV là bằng chứng checksum đã được xử lý đúng cho production.

## 18. validCheckSum và checksum version khi nâng cấp Liquibase

Khi nâng phiên bản Liquibase, cách tính checksum có thể thay đổi theo **checksum version**. Giá trị lưu trong MD5SUM có thể mang version prefix, ví dụ ở dạng:

~~~text
<version>:<checksum>
~~~

Một số bản Liquibase có thể tự nhận biết checksum cũ và tính lại/cập nhật theo quy trình của phiên bản mới. Hành vi chính xác cần được kiểm tra trong tài liệu nâng cấp và thử nghiệm.

Trước khi nâng cấp:

1. Ghi nhận phiên bản Liquibase hiện tại và mục tiêu.
2. Backup hoặc snapshot database thử nghiệm có DATABASECHANGELOG thật.
3. Chạy validate/status với phiên bản hiện tại để ghi nhận trạng thái nền.
4. Chạy phiên bản Liquibase mới trên bản sao.
5. Kiểm tra log checksum, các changeset bị báo lỗi và thay đổi trong MD5SUM.
6. Xác minh schema/data không thay đổi ngoài dự kiến.
7. Chỉ thêm validCheckSum nếu có một checksum cụ thể cần được chấp nhận và có căn cứ.

**Không dùng validCheckSum để thay thế kế hoạch nâng cấp Liquibase.** Checksum version khác không nhất thiết có nghĩa changeset đã thay đổi về SQL; ngược lại, checksum version giống nhau cũng không chứng minh nội dung giống nhau nếu giá trị checksum khác.

## 19. validCheckSum và rollback

validCheckSum không khai báo rollback và không ảnh hưởng trực tiếp đến câu SQL đảo ngược. Nó chỉ liên quan đến việc Liquibase chấp nhận checksum của changeset.

Khi rollback:

- Liquibase vẫn cần xác định changeset theo lịch sử và mốc rollback.
- Rollback sử dụng thao tác rollback được khai báo hoặc khả năng rollback của change type.
- Nếu changeset đã được chấp nhận bằng validCheckSum, điều đó không bổ sung rollback còn thiếu.
- Nếu nội dung SQL cũ và mới khác nhau, cần biết database thực tế đã áp dụng phiên bản nào trước khi rollback.
- Không giả định validCheckSum làm cho rollback của mọi môi trường giống nhau.

Ví dụ một changeset tạo cột có rollback DROP COLUMN. Nếu môi trường A đã tạo cột theo nội dung cũ, môi trường B theo nội dung mới, cần xác minh cấu trúc và dữ liệu trước khi rollback. Một checksum được chấp nhận không thể cho biết cột đã chứa dữ liệu nào hoặc có được ứng dụng sử dụng hay không.

## 20. Những rủi ro khi chấp nhận checksum quá rộng

Một checksum cụ thể vẫn cần review. Nếu chấp nhận quá nhiều giá trị hoặc dùng cơ chế chấp nhận không giới hạn khi phiên bản hỗ trợ, nhóm có thể mất khả năng phát hiện changeset bị chỉnh sửa ngoài ý muốn.

Các rủi ro:

- SQL có thay đổi thực sự nhưng được coi là hợp lệ.
- Môi trường cũ giữ schema khác môi trường mới.
- Một lỗi sửa changeset bị che đi thay vì được triển khai bằng changeset mới.
- Người review không còn biết checksum nào tương ứng artifact nào.
- Pipeline vượt qua validate nhưng database không đạt yêu cầu nghiệp vụ.
- Rollback và phục hồi trở nên khó giải thích do các môi trường đã chạy nội dung khác nhau.

**Chỉ chấp nhận checksum có nguồn gốc rõ ràng và phạm vi nhỏ nhất có thể.** Nếu không xác định được vì sao checksum tồn tại, không thêm nó vào validCheckSum.

## 21. Checklist review một validCheckSum

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Changeset được nhận diện đúng không? | ID, author, filename/logicalFilePath |
| Checksum cũ lấy từ đâu? | DATABASECHANGELOG hoặc lỗi Liquibase đã lưu |
| Checksum mới lấy từ đâu? | Lỗi hiện tại hoặc công cụ Liquibase đúng phiên bản |
| Version prefix có được giữ nguyên không? | Chuỗi checksum đầy đủ |
| Nội dung cũ và mới khác ở điểm nào? | Diff Git/artifact đã phát hành |
| SQL và kết quả database có tương đương không? | Schema/catalog và kiểm tra dữ liệu |
| Có cần changeset mới không? | Đánh giá thay đổi logic/DDL/DML |
| Phạm vi môi trường nào bị ảnh hưởng? | DEV/STAGING/PRODUCTION history |
| Cú pháp validCheckSum có được phiên bản hỗ trợ không? | Validate và thử nghiệm |
| Có bằng chứng cho người kiểm toán không? | Ticket, commit, reviewer, lý do |
| Có hậu kiểm sau khi chấp nhận không? | DATABASECHANGELOG và schema/data |
| Có đang dùng validCheckSum để che drift không? | Điều tra thay đổi ngoài Liquibase |

Nếu một câu hỏi quan trọng chưa có câu trả lời, giữ pipeline ở trạng thái dừng và điều tra thêm.

## 22. Tình huống thực hành

### Tình huống A: chỉ có một checksum khác sau thay đổi không ảnh hưởng SQL

Một changeset tạo bảng đã triển khai ở production. Nhóm sửa một khác biệt nội dung được xác minh là không thay đổi SQL/định nghĩa database trên phiên bản Liquibase đang dùng. Production báo checksum mismatch.

**Cách xử lý:**

1. Lấy checksum cũ từ DATABASECHANGELOG và checksum mới từ lỗi.
2. Xem diff source, xác minh nội dung thay đổi không làm thay đổi kết quả migration.
3. Kiểm tra schema thực tế trên production.
4. Nếu có đủ bằng chứng, thêm validCheckSum với checksum cũ chính xác.
5. Validate và thử trên bản sao production trước khi triển khai.

Không tự giả định mọi comment/whitespace đều bị bỏ qua hoặc đều tạo checksum giống nhau; hãy dùng kết quả thực tế của phiên bản.

### Tình huống B: SQL thay đổi để thêm constraint mới

Changeset ban đầu chỉ tạo bảng. Sau khi chạy production, nhóm sửa trực tiếp changeset cũ để thêm CHECK constraint. Liquibase báo mismatch.

**Cách xử lý:** không dùng validCheckSum để chấp nhận checksum cũ rồi kết luận production đã có CHECK. Tạo changeset mới để thêm constraint, kiểm tra dữ liệu cũ và triển khai theo thứ tự.

### Tình huống C: một môi trường có checksum từ nhánh cũ

DEV có checksum A, STAGING có B, PRODUCTION có C. Nhóm không biết các nhánh khác nhau ở đâu.

**Cách xử lý:** dừng việc chấp nhận checksum hàng loạt. Thu thập artifact/commit từng môi trường, so sánh nội dung và schema thực tế, phân loại thay đổi. Chỉ sau khi chứng minh một checksum cụ thể tương đương mới cân nhắc validCheckSum; nếu khác logic thì cần migration sửa trạng thái.

### Tình huống D: đổi đường dẫn changelog

Một changeset được chuyển từ db/changelog/legacy.yaml sang db/changelog/releases/v2.yaml. ID và author không đổi nhưng Liquibase xem nó như một changeset mới.

**Cách xử lý:** đây là vấn đề identity/path. validCheckSum không giải quyết. Xem xét logicalFilePath theo phiên bản Liquibase và thử trên database có lịch sử trước khi triển khai.

## 23. Quy trình CI/CD đề xuất

Một pipeline quản lý checksum có thể chia thành các bước:

1. **Đóng băng artifact:** ghi nhận commit, changelog, phiên bản Liquibase và DBMS.
2. **Validate:** kiểm tra cấu trúc changelog và các lỗi có thể phát hiện trước.
3. **Status/history:** xác định changeset nào được xem là đã chạy hoặc pending.
4. **Thu thập mismatch:** nếu có, lưu ID, author, path, checksum cũ/mới và môi trường.
5. **Phân loại:** checksum-only, identity/path, schema drift hay SQL đã thay đổi.
6. **Review quyết định:** validCheckSum, changeset mới, xử lý logicalFilePath hoặc runbook drift.
7. **Thử trên bản sao:** bao gồm database mới và database có lịch sử thực tế.
8. **Update-sql:** xem trước các thay đổi SQL sẽ chạy.
9. **Triển khai:** chỉ dùng artifact đã được review; không thay source giữa các môi trường.
10. **Hậu kiểm:** xác nhận DATABASECHANGELOG, schema, dữ liệu và các constraint/index.
11. **Lưu bằng chứng:** checksum được chấp nhận, lý do, ticket, commit và reviewer.

Các lệnh Liquibase điển hình khi đã cấu hình kết nối và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Các lệnh trên hỗ trợ kiểm chứng và triển khai; chúng không tự quyết định checksum mismatch có vô hại hay không. **Quyết định validCheckSum phải có người review và bằng chứng.**

## 24. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Copy checksum từ môi trường khác | Chấp nhận nhầm lịch sử không tương đương | Lấy checksum đúng changeset/database |
| Bỏ version prefix | Sai định dạng hoặc mất thông tin phiên bản | Giữ nguyên checksum đầy đủ |
| Dùng validCheckSum để chấp nhận SQL mới | Database cũ không nhận logic mới | Tạo changeset mới |
| Dùng validCheckSum để sửa đường dẫn | Changeset identity vẫn sai | Xử lý logicalFilePath |
| Dùng clear-checksums cho mọi mismatch | Xóa bằng chứng checksum cũ trên phạm vi rộng | Chỉ dùng theo quy trình nâng cấp có kiểm soát |
| Coi checksum là chữ ký bảo mật | Đánh giá sai mức bảo vệ | Dùng kiểm soát artifact/audit riêng |
| Thêm mọi checksum thấy trong log | Mở rộng ngoại lệ không rõ nguồn gốc | Chỉ thêm checksum được xác minh và phê duyệt |
| Nghĩ validCheckSum chạy lại SQL | Database vẫn giữ trạng thái cũ | Dùng changeset mới hoặc cơ chế chạy lại đúng mục tiêu |
| Không kiểm tra schema thực tế | Che giấu drift | Đối chiếu catalog và dữ liệu |
| Chỉ thử database mới | Bỏ sót lịch sử production cũ | Thử cả database có DATABASECHANGELOG |
| Sửa changeset đã chạy để tiết kiệm một changeset | Mất khả năng tái tạo lịch sử | Bảo toàn lịch sử, bổ sung migration mới |

## 25. Ghi nhớ

**validCheckSum** là cơ chế chấp nhận có kiểm soát một checksum cụ thể cho changeset. Nó hữu ích khi một khác biệt lịch sử đã được điều tra, có checksum chính xác và có bằng chứng rằng việc chấp nhận không che giấu một thay đổi schema/data cần triển khai.

Ba nguyên tắc cần giữ:

1. **Điều tra trước khi chấp nhận:** phân biệt checksum mismatch, identity mismatch và schema drift; lấy checksum từ lịch sử hoặc thông báo Liquibase đúng phiên bản.
2. **Chấp nhận hẹp và có bằng chứng:** giữ version prefix, chỉ khai báo giá trị đã xác minh, review phạm vi môi trường và ghi nhận lý do.
3. **Không thay thế migration:** nếu SQL hoặc ý nghĩa dữ liệu cần thay đổi, tạo changeset mới; validCheckSum không chạy lại SQL, clear-checksums không sửa database và checksum không chứng minh trạng thái nghiệp vụ.

Khi kết hợp changelog bất biến, DATABASECHANGELOG được quản lý, kiểm tra schema/data và quy trình CI/CD có review, nhóm có thể xử lý checksum khác biệt mà vẫn giữ được lịch sử triển khai minh bạch và có thể tái tạo.
