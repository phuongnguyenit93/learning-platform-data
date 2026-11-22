# Chọn sửa tiến bằng changeset mới thay cho sửa lịch sử

Một migration Liquibase đã chạy trên production nhưng có sai sót: độ dài cột quá ngắn, dữ liệu được cập nhật nhầm, thiếu index hoặc một ràng buộc chưa phù hợp. Cách sửa dễ nghĩ đến là mở tệp changelog cũ, thay câu SQL hoặc thông số và triển khai lại. **Đây thường là quyết định sai**: database đã lưu việc thực thi changeset cũ trong lịch sử, còn mã nguồn sau khi sửa lại mô tả một trạng thái khác. Liquibase có thể báo checksum không khớp; kể cả không báo lỗi, việc sửa mã cũ cũng không tự thực thi lại thay đổi đã ghi nhận.

Nguyên tắc xử lý chủ đạo là **sửa tiến (forward fix)**: giữ nguyên định nghĩa changeset đã triển khai và tạo **changeset mới** để đưa database từ trạng thái đã tồn tại sang trạng thái mong muốn. Bài học thuộc chương **Checksum và lịch sử** của module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, với mục tiêu quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum, lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Bản chất của “không sửa lịch sử”

Liquibase không coi mỗi tệp changelog là bản mô tả schema cuối cùng để tự động cập nhật lại tất cả các đối tượng mỗi lần chạy. Nó đọc **danh sách changeset**, so sánh chúng với lịch sử của database và quyết định changeset nào cần thực thi.

Một changeset đã phát hành có hai mặt:

1. **Định nghĩa trong version control:** câu lệnh, tác giả, ID, đường dẫn định danh, các điều kiện và metadata.
2. **Dấu vết trong database:** bản ghi tại `DATABASECHANGELOG` cho biết Liquibase đã xử lý changeset ấy như thế nào tại một thời điểm.

Nếu sửa định nghĩa sau khi database đã chạy, hai mặt này có thể không còn tương ứng. Lịch sử không bị “viết lại” chỉ vì file nguồn bị chỉnh sửa. Một thay đổi tiếp theo phải được mô tả thành **bước chuyển trạng thái mới** để Liquibase và con người đều có thể truy vết.

### 1.1. Đường thời gian đúng và sai

~~~mermaid
flowchart TD
    A["001 đã chạy: email VARCHAR(80)"] --> B{"Cần tăng lên VARCHAR(255)"}
    B -->|"Sửa trực tiếp 001"| C["Mã nguồn khác lịch sử đã ghi"]
    C --> D["Có nguy cơ checksum mismatch; thay đổi chưa được áp dụng"]
    B -->|"Tạo changeset 002"| E["001 giữ nguyên, 002 đổi kiểu cột"]
    E --> F["DATABASECHANGELOG ghi nhận thêm 002"]
    F --> G["Dễ truy vết, nâng cấp và kiểm chứng nhiều môi trường"]
~~~

**Sửa tiến không có nghĩa mọi thay đổi đều phải đẩy thẳng lên production.** Nó là cách quản lý lịch sử sau khi đã xác định migration cũ tồn tại ở ít nhất một database cần bảo toàn. Đối với thay đổi chưa từng phát hành hoặc chưa chạy ở bất kỳ môi trường nào, nhóm vẫn có thể chỉnh sửa trước khi chốt phiên bản, nhưng phải **xác minh chắc chắn** điều kiện đó và phối hợp với các nhánh, artifact đã phân phối.

## 2. Định danh, checksum và DATABASECHANGELOG

Liquibase thường nhận diện changeset bằng bộ ba **`id`, `author` và đường dẫn định danh changelog**. Đường dẫn này có thể được bảo toàn bằng `logicalFilePath` khi tệp vật lý được đổi tên hoặc di chuyển.

Sau khi changeset được thực thi hoặc ghi nhận, bảng `DATABASECHANGELOG` chứa những thông tin điển hình:

| Trường | Vai trò | Cần nhớ khi sửa tiến |
|---|---|---|
| `ID` | ID của changeset. | Không tái sử dụng ID cũ để tạo một thay đổi khác với cùng author/path. |
| `AUTHOR` | Tác giả hoặc nhóm sở hữu. | Thay author của changeset cũ có thể biến nó thành định danh khác. |
| `FILENAME` | Đường dẫn định danh changelog. | Di chuyển file không bảo toàn logical path có thể khiến changeset cũ bị nhận là mới. |
| `DATEEXECUTED` | Thời điểm ghi nhận thực thi. | Là dấu vết lịch sử, không phải một lệnh SQL có thể chạy lại. |
| `ORDEREXECUTED` | Thứ tự thực thi được ghi nhận. | Hữu ích khi điều tra migration trước/sau lỗi. |
| `EXECTYPE` | Trạng thái như `EXECUTED`, `MARK_RAN` hoặc `RERAN` theo tình huống. | `MARK_RAN` không chứng minh câu SQL đã chạy. |
| `MD5SUM` | Checksum định nghĩa changeset đã ghi nhận. | Khác biệt có thể dẫn đến validation error hoặc cơ chế chạy lại được cấu hình. |

Truy vấn chỉ đọc:

~~~sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED,
       ORDEREXECUTED, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Ví dụ truy vấn giả định Liquibase dùng tên bảng mặc định. Nếu dự án thay đổi `databaseChangeLogTableName` hoặc schema metadata, hãy điều chỉnh đúng tên/bối cảnh kết nối.

### 2.1. Checksum bảo vệ điều gì?

Checksum Liquibase là giá trị dùng để phát hiện **sự thay đổi trong định nghĩa được Liquibase tính vào checksum** của một changeset đã ghi nhận. Không nên hiểu checksum là chữ ký mật mã toàn diện của repository hoặc toàn bộ schema. Một số metadata, comment hoặc khác biệt biểu diễn nhất định có thể không làm đổi checksum tùy loại change và phiên bản Liquibase; ngược lại, thay SQL hoặc giá trị của change đã chạy thường cần được xem xét kỹ.

Khi Liquibase phát hiện nội dung changeset cũ không tương thích checksum lịch sử, `validate` hoặc `update` có thể báo lỗi. Đây là một **tín hiệu bảo vệ lịch sử**, không phải phiền toái cần vô hiệu hóa tùy tiện.

### 2.2. Vì sao sửa SQL cũ không tự sửa database?

Giả sử `001` đã được ghi `EXECUTED`. Sau đó bạn đổi cột từ `VARCHAR(80)` thành `VARCHAR(255)` trong chính changeset `001`:

- Nếu checksum bị xem là không hợp lệ, Liquibase có thể **dừng validation/update**.
- Nếu một khác biệt không ảnh hưởng checksum hoặc đã được chấp nhận theo một cơ chế đặc biệt, Liquibase cũng **không mặc định** tạo câu `ALTER COLUMN` để “bù” cho schema đã triển khai.
- Nếu đổi ID/author/path để ép Liquibase coi nó là changeset mới, thao tác gốc `CREATE TABLE` có thể bị chạy lại và thất bại, hoặc tệ hơn là tạo dữ liệu trùng.

Vì vậy, hãy mô tả một **migration bổ sung đúng nghĩa** thay vì cố làm cho file quá khứ “trông đúng”.

## 3. Ví dụ xuyên suốt: email quá ngắn sau khi triển khai

Giả định service khách hàng đã phát hành changeset đầu tiên tạo bảng `customer_record`, nhưng định nghĩa `email VARCHAR(80)` không đủ cho yêu cầu mới. Production đã chạy `001` thành công.

### 3.1. Định nghĩa cũ phải được giữ nguyên

File changelog YAML ban đầu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: db-team
      changes:
        - createTable:
            tableName: customer_record
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(80)
                  constraints:
                    nullable: false
~~~

Với production đã chạy `001`, **không đổi** `VARCHAR(80)` thành `VARCHAR(255)` trong changeset này. Changelog cũ tiếp tục mô tả chính xác bước migration lịch sử.

### 3.2. Thêm changeset mới để sửa tiến

Bổ sung **một phần tử mới** vào mảng `databaseChangeLog` (giữ nguyên `001`):

~~~yaml
  - changeSet:
      id: 002-expand-customer-email
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_record
        - columnExists:
            tableName: customer_record
            columnName: email
      changes:
        - modifyDataType:
            tableName: customer_record
            columnName: email
            newDataType: VARCHAR(255)
~~~

Đoạn ở mục 3.2 là **phần tử array tiếp theo**, không phải changelog YAML độc lập khi sao chép riêng. Trong file thật, đặt nó ngay sau `001` ở đúng cấp thụt lề. Các precondition chỉ kiểm tra bảng/cột **tồn tại**, chưa xác minh kiểu hiện tại bằng `VARCHAR(80)`. Trong hệ thống có nguy cơ schema drift, cần thêm kiểm chứng metadata hoặc điều kiện đặc thù DBMS trước khi đổi kiểu.

`modifyDataType` cũng không có hành vi/rollback giống nhau trên mọi DBMS. Hãy xác minh hỗ trợ của phiên bản Liquibase, SQL được sinh, thời gian giữ lock, index và dữ liệu thực tế. Không tự động giả định có thể rollback từ `VARCHAR(255)` về `VARCHAR(80)` khi đã chứa email dài hơn 80 ký tự.

### 3.3. Kết quả mong đợi ở ba môi trường

| Môi trường | Trạng thái trước phát hành | Kết quả mong đợi |
|---|---|---|
| Development | Đã chạy `001`, chưa chạy `002`. | `002` được nhận là pending, sau `update` cột được nới dài. |
| Staging | Đã chạy `001` như production. | `002` chạy trên dữ liệu đại diện; kiểm thử ứng dụng với email dài. |
| Database trống | Chưa có lịch sử. | Liquibase chạy `001` rồi `002` theo thứ tự để đạt schema cuối. |

Điểm mạnh của sửa tiến là **cùng một chuỗi lịch sử tạo được trạng thái cuối** từ database mới lẫn database đã triển khai, miễn các giả định của từng changeset được thỏa mãn.

Nếu một môi trường chưa từng chạy `001` nhưng đã được tạo bảng thủ công, đó là tình huống **baseline/schema drift**, không thể kết luận chỉ bằng “bổ sung `002`” rằng mọi thứ sẽ ổn. Phải điều tra và lập phương án đồng bộ được phê duyệt.

## 4. Sửa tiến DDL và sửa tiến DML khác nhau

Sửa kiểu cột, thêm index hay constraint là **schema correction**. Sửa dữ liệu cũ hoặc backfill là **data correction**. Hai nhóm có rủi ro riêng và thường nên tách changeset để dễ kiểm chứng.

### 4.1. Ví dụ sửa dữ liệu theo điều kiện

Giả sử một bản phát hành cũ vô tình lưu `status = 'enabled'` trong khi hợp đồng mới quy định `ACTIVE`. Nếu đã xác nhận đây là quy tắc chuyển đổi hợp lệ cho toàn bộ dữ liệu liên quan, hãy tạo một changeset **mới**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-normalize-customer-status
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_record
        - columnExists:
            tableName: customer_record
            columnName: status
      changes:
        - sql:
            sql: >
              UPDATE customer_record
              SET status = 'ACTIVE'
              WHERE status = 'enabled'
~~~

Đây là một changelog **độc lập về cấu trúc** để minh họa thay đổi dữ liệu, giả định cột `status` đã tồn tại và có nghĩa nghiệp vụ như nêu. Trên hệ thống thật, đặt changeset ở vị trí đúng sau các migration tạo cột; không chạy nó khi chưa xác minh chính sách giá trị và số hàng bị tác động.

Điều kiện `WHERE status = 'enabled'` khiến SQL mang tính **idempotent về giá trị** đối với riêng phép chuẩn hóa này: các hàng đã chuyển sang `ACTIVE` không tiếp tục bị đổi. Nhưng điều đó không đồng nghĩa thay đổi an toàn tuyệt đối:

- Có thể có ứng dụng cũ vẫn ghi `enabled` trong quá trình rolling deployment.
- Điều kiện cần phân biệt chữ hoa/thường hoặc khoảng trắng theo quy ước nghiệp vụ.
- Trên bảng lớn, `UPDATE` có thể giữ lock lâu, tăng WAL/binlog và ảnh hưởng replication.
- Nếu cần khôi phục giá trị ban đầu, rollback `ACTIVE` về `enabled` **không an toàn** nếu trước đó cũng đã có hàng `ACTIVE` hợp lệ; thông tin nguồn gốc đã mất.

Với dữ liệu nhạy cảm, phải thiết kế audit, backup hoặc mapping theo từng hàng; khi cần backfill lớn, cân nhắc chia lô và chiến lược expand–migrate–contract phù hợp.

### 4.2. Không sửa migration cũ để “tối ưu” dữ liệu đã chạy

Nếu changeset cũ từng `UPDATE customer_record SET status = 'ACTIVE'` mà thiếu `WHERE`, không nên chỉ thêm `WHERE` vào changeset đã chạy rồi nghĩ production sẽ tự sửa. Câu SQL mới chỉ có thể ảnh hưởng database chưa từng chạy changeset ấy; các môi trường đã ghi history không tự thực thi lại. Kết quả có thể tạo **hai lịch sử hành vi khác nhau dưới cùng ID**, rất khó kiểm toán.

Giải pháp sửa tiến là mô tả chính xác điều cần làm **từ trạng thái hiện tại**: xác định các hàng bị tác động, điều kiện khôi phục và migration mới để sửa giá trị hoặc phục hồi từ dữ liệu nguồn có thể tin cậy.

## 5. Quy tắc quyết định: khi nào được chỉnh changeset cũ?

Không phải mọi sửa đổi trong repository đều bị cấm; vấn đề là **lịch sử triển khai đã tồn tại hay chưa**.

| Tình huống | Quyết định nên cân nhắc | Vì sao |
|---|---|---|
| Changeset mới đang ở nhánh cá nhân, chắc chắn chưa từng chạy trên bất kỳ database cần bảo toàn nào | Có thể chỉnh trực tiếp trước khi phát hành. | Chưa có lịch sử đã được cam kết cần giữ. |
| Changeset đã merge hoặc artifact đã phân phối, chưa rõ ai đã chạy | **Không tự sửa**; xác minh history của các môi trường trước. | Có thể đã được áp dụng ở một database ngoài máy phát triển. |
| Changeset đã `EXECUTED` trên staging hoặc production | Giữ nguyên; tạo changeset sửa tiến. | Bảo toàn lịch sử và tránh checksum mismatch. |
| Changeset đã `MARK_RAN` | Không coi là chưa từng tồn tại; điều tra điều kiện và schema trước khi sửa. | History đã ghi nhận dù SQL không thực thi. |
| Changeset dùng `runOnChange` để quản lý view/function có thể thay thế | Cân nhắc cập nhật theo **chính sách đã thiết kế**, kiểm thử lại. | Đây là ngoại lệ có chủ đích, không phải giấy phép sửa mọi migration. |
| Changeset đã chạy một phần rồi lỗi, chưa có `EXECUTED` mới | Điều tra trạng thái thật; không vội thêm/sửa rồi retry. | DDL có thể đã commit dù history chưa ghi nhận. |
| Chỉ sửa comment hoặc formatting | Xem xét ảnh hưởng checksum và policy; không tự cho là vô hại. | Hành vi checksum phụ thuộc thay đổi và phiên bản. |

**Nguyên tắc vận hành an toàn:** từ thời điểm migration có khả năng đã được người khác chạy, hãy xem changeset như một phần **lịch sử bất biến** cho tới khi chứng minh được điều ngược lại.

## 6. Vì sao không chỉnh trực tiếp DATABASECHANGELOG?

`DATABASECHANGELOG` là bảng metadata Liquibase dùng để đối chiếu định danh, checksum và trạng thái thực thi. Việc tự thay `ID`, `AUTHOR`, `FILENAME`, `MD5SUM` hoặc xóa hàng có thể khiến Liquibase:

- Xem một changeset đã chạy là mới và thử thực thi lại.
- Bỏ qua một changeset chưa từng thực thi trong database.
- Chấp nhận một định nghĩa không khớp với schema thật.
- Tạo lịch sử không còn đáng tin để rollback hoặc audit.

Đặc biệt, **xóa hàng history không hoàn tác SQL** mà changeset đã chạy. Ngược lại, tự thêm một hàng history không tạo ra bảng/cột hoặc dữ liệu. Cả hai cách làm đều có thể khiến history và schema đi lệch nhau.

Khi cần đồng bộ metadata do sự cố thực sự, phải có kế hoạch có kiểm chứng: backup, kiểm tra schema/data, xác định chính xác changeset, đánh giá từng môi trường, phê duyệt thay đổi metadata và đối chiếu kết quả sau xử lý. Đó là **ngoại lệ xử lý sự cố**, không phải phương án sửa tiến mặc định.

## 7. Phân biệt công cụ khắc phục với sửa tiến

Những lệnh/cơ chế sau có ích trong những trường hợp nhất định nhưng **không thay thế** changeset sửa tiến khi schema hoặc dữ liệu thật cần thay đổi:

| Công cụ/cơ chế | Thực sự làm gì? | Không làm gì? | Nguy cơ khi lạm dụng |
|---|---|---|---|
| `clearCheckSums` | Xóa checksum đã lưu để Liquibase tính/ghi nhận lại theo quy trình của nó. | Không tự chạy lại mọi change đã ghi `EXECUTED`; không tạo SQL sửa schema bị thiếu. | Che mất tín hiệu một changeset cũ đã bị thay nội dung ngoài ý muốn. |
| `validCheckSum` | Chấp nhận những checksum được khai báo hợp lệ đối với changeset. | Không thực thi DDL/DML sửa lỗi nghiệp vụ. | Hợp thức hóa chênh lệch mà không chứng minh schema đúng. |
| `changelogSync` | Ghi nhận changeset chưa ghi history như đã chạy, **không thực thi change**. | Không tạo bảng/cột/index hoặc sửa dữ liệu. | History nói “đã chạy” khi object chưa tồn tại. |
| `onFail="MARK_RAN"` | Khi precondition ở cấp changeset không đạt, ghi nhận changeset đã chạy mà bỏ qua change theo policy. | Không bảo đảm kết quả change đã có trong database. | Đánh dấu thành công dựa trên kiểm tra chưa đầy đủ. |
| `runOnChange` | Cho phép xét thực thi lại changeset khi nội dung thay đổi theo checksum. | Không tự sửa một migration hỏng nếu SQL không có khả năng thay thế an toàn. | Kích hoạt DDL nhiều lần, thiếu snapshot phiên bản body cũ, tác động dependencies. |
| `runAlways` | Xét thực thi changeset ở mỗi lần update đủ điều kiện. | Không bảo đảm change idempotent hoặc dữ liệu an toàn. | Thực thi lại thao tác không nên lặp. |
| `logicalFilePath` | Giữ đường dẫn định danh khi đổi vị trí file changelog. | Không tự tìm file vật lý, không sửa SQL/data. | Cấu hình sai có thể gây trùng hoặc đổi định danh. |
| Liquibase rollback command | Thực thi các thao tác đảo ngược theo phạm vi đã chọn. | Không chắc phục hồi dữ liệu nếu rollback phá hủy hoặc thiếu dữ liệu nguồn. | Làm mất dữ liệu hoặc gỡ những changeset đang được ứng dụng phụ thuộc. |

### 7.1. Khi nào validCheckSum có thể hợp lệ?

Ví dụ một lần thay đổi có chủ đích về cách biểu diễn changeset đã triển khai nhưng **không làm thay đổi hiệu ứng nghiệp vụ**, được kiểm chứng kỹ trên mọi môi trường. Nhóm có thể quyết định chấp nhận một checksum cũ qua `validCheckSum` theo chính sách riêng. Đây là **quy trình xử lý checksum**, không phải cách để áp dụng một kiểu cột hoặc dữ liệu mới.

Nếu email thực tế vẫn `VARCHAR(80)` thì chấp nhận checksum của định nghĩa đã đổi sang `VARCHAR(255)` **không nới cột**. Một changeset sửa tiến vẫn cần thiết.

### 7.2. Khi nào runOnChange là ngoại lệ có chủ đích?

Với view, procedure hoặc function được triển khai bằng `CREATE OR REPLACE`, `runOnChange` có thể là mô hình đã được thiết kế ngay từ đầu. Khi nội dung thay đổi hợp lệ, Liquibase sẽ xử lý theo policy đó. Tuy vậy, đổi chữ ký procedure, kiểu trả về function hoặc cấu trúc bảng phụ thuộc có thể không thay thế tại chỗ được; khi ấy nên tạo bước migration mới có trình tự và rollback rõ ràng.

Không tự bổ sung `runOnChange` vào một changeset `createTable` đã triển khai chỉ để vượt qua lỗi checksum. Một lệnh `CREATE TABLE` thông thường không an toàn khi thực thi lại.

## 8. Cần phân loại trạng thái trước khi viết fix

Một đội vận hành có nhiều database hoặc nhiều vùng triển khai. Trước khi soạn changeset sửa tiến, hãy phân loại:

| Trạng thái thực tế | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Old changeset đã chạy đủ trên tất cả môi trường | History đồng nhất; schema cũ đã biết. | Tạo một changeset mới, kiểm thử từ mỗi trạng thái. |
| Một số môi trường chưa chạy old changeset | Độ dài lịch sử khác nhau nhưng đều hợp lệ. | Thêm changeset mới sau old changeset; kiểm tra lần nâng cấp từ zero. |
| Old changeset đã được ghi `MARK_RAN` ở một môi trường | SQL có thể chưa được áp dụng. | Xác minh schema tương đương trước khi tiếp tục; đừng giả định history chứng minh object đã có. |
| Old changeset lỗi giữa chừng, DDL có thể tự commit | History và schema có thể không khớp. | Dừng retry, điều tra và phục hồi trạng thái trước khi tiếp tục chuỗi migration. |
| Một môi trường bị sửa schema thủ công | Schema drift ngoài changelog. | Thu thập bằng chứng, thiết kế remediation phù hợp, tránh phá dữ liệu đúng. |
| Changelog cũ đổi tên/đường dẫn | Có nguy cơ bộ ba định danh không khớp. | Kiểm tra `FILENAME` và bảo toàn `logicalFilePath`. |
| Có ứng dụng cũ và mới đồng thời hoạt động | Contract schema cần tương thích trong giai đoạn chuyển tiếp. | Dùng expand–migrate–contract, thêm changeset và nâng ứng dụng theo thứ tự. |

**Đặc biệt quan trọng:** nếu một changeset cũ thất bại nhưng đã tạo bảng/cột trên DBMS có DDL tự commit, chỉ bổ sung changeset mới phía sau **có thể không đủ**. Liquibase có thể vẫn xem changeset lỗi là chưa chạy và thử lại nó trước khi tới fix. Phải giải quyết trạng thái dở dang theo bằng chứng, không đi vòng bằng `MARK_RAN` hay sửa history một cách tự phát.

## 9. Workflow sửa tiến có kiểm chứng

### Bước 1 — Đóng băng sự kiện và xác định phạm vi

Ghi lại lỗi hoặc thay đổi nghiệp vụ mới, môi trường ảnh hưởng, schema và dữ liệu kỳ vọng. Không để pipeline tự retry một migration có thể không idempotent. Xác định DBMS/version, Liquibase Core/CLI, JDBC driver, bản artifact và commit changelog.

### Bước 2 — Đối chiếu lịch sử và trạng thái thực

Trên mỗi môi trường liên quan:

1. Đọc `DATABASECHANGELOG` theo `ID`, `AUTHOR`, `FILENAME`, `EXECTYPE`, `MD5SUM`.
2. Kiểm tra schema thật bằng metadata DBMS, không chỉ từ history.
3. Đối chiếu dữ liệu đã bị tác động, số lượng bản ghi và những giá trị biên.
4. Kiểm tra xem có migration khác đang chạy hoặc khóa `DATABASECHANGELOGLOCK` còn giữ không.
5. Lập ma trận trạng thái môi trường để tránh thiết kế fix chỉ đúng với database của người phát triển.

### Bước 3 — Mô tả chuyển đổi từ trạng thái cũ sang trạng thái mong muốn

Một forward fix tốt có thể diễn đạt:

~~~text
Trước:
  customer_record.email = VARCHAR(80)
  changeset 001 đã EXECUTED

Yêu cầu:
  customer_record.email lưu giá trị dài đến 255

Thay đổi mới:
  changeset 002 -> modifyDataType VARCHAR(255)

Kiểm chứng:
  dữ liệu cũ vẫn đọc được
  ứng dụng ghi/đọc giá trị biên
  DATABASECHANGELOG ghi 001 và 002
~~~

Nếu yêu cầu là sửa dữ liệu sai, phải chỉ rõ tập hàng, điều kiện chuyển đổi, hậu quả khi chạy lặp và phương án khôi phục dữ liệu gốc. Không diễn đạt mơ hồ “chạy lại migration 001” khi lịch sử đã ghi.

### Bước 4 — Thiết kế changeset có định danh mới

Đặt ID mới, author rõ ràng và vị trí include phù hợp. Thêm precondition khi cần bảo vệ bất biến schema/data; dùng `onFail="HALT"` với điều kiện bắt buộc thay vì tự `MARK_RAN`. Cân nhắc chia DDL, backfill dữ liệu và thêm constraint thành changeset riêng để dễ thử, giám sát và xử lý lỗi.

### Bước 5 — Kiểm tra trước khi update

Ví dụ lệnh CLI, với kết nối và bí mật được cấu hình an toàn:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml validate
liquibase --changelog-file=db/changelog/master.yaml status --verbose
liquibase --changelog-file=db/changelog/master.yaml update-sql
~~~

Hãy dùng cú pháp phù hợp phiên bản Liquibase đã khóa; một số bản cũ đặt tên lệnh sinh SQL khác, chẳng hạn `updateSQL`. `validate` kiểm tra định nghĩa và những ràng buộc Liquibase có thể phát hiện, `status` cho thấy changeset chờ, `update-sql` giúp review SQL dự kiến. **Không công cụ nào trong ba lệnh này tự bảo đảm đổi kiểu/đổi dữ liệu sẽ an toàn với dữ liệu production.**

### Bước 6 — Kiểm thử từ các điểm khởi đầu khác nhau

- Database mới chưa có history.
- Database đã chạy changeset cũ và có dữ liệu thật đại diện.
- Database chỉ mới hoàn thành một phần chuỗi migration (nếu thuộc trạng thái hợp lệ).
- Môi trường staging có cấu hình, số lượng dữ liệu và phiên bản ứng dụng gần production.
- Các nhánh DBMS được sản phẩm hỗ trợ, nếu changelog cần portable.

Sau khi chạy thử, đối chiếu metadata, dữ liệu, behavior của ứng dụng và bản ghi `DATABASECHANGELOG`. Lần `update` tiếp theo với changeset thông thường đã hoàn tất không nên tạo lại thay đổi đó.

### Bước 7 — Phát hành và giám sát

Phát hành đúng artifact đã kiểm chứng, điều phối Liquibase trong Spring Boot hoặc pipeline để tránh nhiều bộ công cụ đồng thời sở hữu migration. Theo dõi lock, thời gian DDL, số hàng backfill, replication lag và lỗi truy cập từ ứng dụng. Nếu lỗi, thu thập bằng chứng **trước khi retry**.

## 10. Rollback hay sửa tiến?

Hai chiến lược giải quyết những bài toán khác nhau:

| Câu hỏi | Rollback | Sửa tiến |
|---|---|---|
| Mục tiêu | Đưa một phạm vi changeset về trạng thái trước đó theo rollback đã định nghĩa. | Chuyển trạng thái hiện tại sang trạng thái mới đúng bằng changeset bổ sung. |
| Cần lịch sử đáng tin? | Có. | Có. |
| Có thể mất dữ liệu? | Có: drop table/column hoặc đảo ngược không đầy đủ. | Có: nếu fix là backfill/cleanup sai hoặc đổi kiểu mất thông tin. |
| Tương thích với ứng dụng đang chạy | Cần xem ứng dụng có phụ thuộc schema mới không. | Có thể thiết kế expand–migrate–contract để duy trì tương thích. |
| Khi nào phù hợp | Có rollback an toàn đã thử, biết phạm vi, dữ liệu có thể khôi phục. | Schema đã dùng thật, cần sửa một sai sót mà vẫn giữ lịch sử phát hành. |

**Không mặc định forward fix luôn tốt hơn rollback.** Nếu vừa phát hành một changeset có thể rollback an toàn, chưa có dữ liệu phụ thuộc và quay lại trạng thái trước là mục tiêu rõ ràng, rollback được kiểm chứng có thể phù hợp. Ngược lại, nếu schema đã có dữ liệu mới hoặc đang có client sử dụng, sửa tiến thường dễ kiểm soát hơn việc xóa rồi tạo lại.

### 10.1. Rollback của bản sửa tiến phải có ý nghĩa dữ liệu

Ví dụ đổi `VARCHAR(80)` thành `VARCHAR(255)`, rollback về 80 có thể thất bại hoặc cắt dữ liệu dài hơn 80. Việc viết một câu `modifyDataType VARCHAR(80)` vào rollback **không tự làm nó an toàn**. Cần xem xét:

- Khả năng rollback trước khi có dữ liệu dài hơn 80.
- Khả năng sử dụng một chiến lược ứng dụng tương thích cả hai kiểu trong giai đoạn chuyển tiếp.
- Backup/restore hoặc compensating migration nếu không thể đảo ngược mà giữ dữ liệu.
- Có nên tuyên bố migration không có rollback dữ liệu an toàn và sử dụng kế hoạch **roll-forward** hay không.

Với DML sửa sai dữ liệu, nếu trạng thái cũ không được ghi lại, SQL đảo ngược có thể không phân biệt dữ liệu được sửa với dữ liệu vốn đã hợp lệ. **Khả năng đảo ngược nghiệp vụ phải được thiết kế, không được suy ra chỉ từ cú pháp SQL.**

## 11. Dữ liệu thật và tính tương thích giữa các phiên bản ứng dụng

Không phải mọi lỗi migration đều giải quyết bằng một `ALTER TABLE`. Ví dụ một cột tên `customer_name` đang được ứng dụng cũ sử dụng, trong khi ứng dụng mới muốn tách `given_name`/`family_name`. Việc sửa changeset tạo bảng lịch sử sẽ không giúp ứng dụng cũ còn chạy.

Mẫu **expand–migrate–contract**:

1. **Expand:** thêm cột mới, giữ cột cũ; ưu tiên thay đổi tương thích ngược.
2. **Migrate:** backfill dữ liệu có kiểm chứng; nếu cần, tạm dual-write để tránh lệch dữ liệu.
3. **Switch:** triển khai ứng dụng đọc/ghi theo mô hình mới, kiểm chứng toàn bộ client.
4. **Contract:** khi không còn client phụ thuộc, dùng changeset mới để bỏ cột cũ và constraint tạm.

Mỗi giai đoạn nên là changeset riêng có định danh ổn định. Trên MySQL/Oracle hoặc những lệnh DDL tự commit, một lỗi có thể để lại thay đổi dở dang dù Liquibase báo failure; cần đánh giá trạng thái thực trước khi retry. Trên PostgreSQL nhiều DDL có thể rollback trong transaction, nhưng vẫn có ngoại lệ như `CREATE INDEX CONCURRENTLY` cần cấu hình chạy riêng.

**Không dùng precondition để che một schema thiếu:** `onFail="MARK_RAN"` khi bảng đã tồn tại đôi khi hợp lệ với database đã được baseline và kiểm chứng, nhưng việc bảng tồn tại **chưa chứng minh kiểu cột, constraint, index, dữ liệu đều đúng**. Nếu thiếu thông tin, `HALT` là lựa chọn bảo thủ hơn.

## 12. Hậu quả với nhiều môi trường và nhiều DBMS

Giả sử development đã sửa trực tiếp `001` nhưng production vẫn lưu checksum cũ. Nếu staging/production dùng cùng commit mới, những khả năng xảy ra:

- Development mới tạo từ zero chạy theo định nghĩa mới, còn production vẫn có schema cũ.
- Production báo checksum mismatch do khác định nghĩa đã ghi.
- Một số database đã chấp nhận checksum hoặc `MARK_RAN` thủ công, gây lịch sử không đồng nhất.

Khi thay vì sửa `001`, cả ba môi trường dùng **`001` bất biến + `002` sửa tiến**:

- Database mới sẽ lần lượt chạy `001` rồi `002`.
- Database có `001` sẽ chỉ chạy `002` nếu thuộc phạm vi.
- Mọi môi trường đều có dấu vết của quyết định sửa trong `DATABASECHANGELOG`.

Kết quả này chỉ đúng khi không có drift hoặc trạng thái đặc biệt chưa được xử lý. Một ma trận triển khai thực tế nên ghi:

| Môi trường | Old ID/author/FILENAME | EXECTYPE | Schema hiện tại | New changeset pending? |
|---|---|---|---|---|
| Development | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Staging | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Production | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |

Không giả định bảng history các môi trường giống nhau chỉ vì dùng cùng branch git. Trên hệ thống hỗ trợ nhiều DBMS, kiểm thử `modifyDataType`, DDL lock và rollback riêng cho từng DBMS/version.

## 13. Các dấu hiệu thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân có thể | Hành động an toàn |
|---|---|---|
| `validate` báo checksum mismatch | Đã sửa changeset cũ, đổi body SQL hoặc cấu trúc tính checksum. | Đối chiếu commit gốc và history; khôi phục định nghĩa cũ, thêm changeset sửa tiến. |
| `status` liệt kê changeset đã chạy | Bộ ba ID/author/FILENAME đổi, nối sai changelog, nhầm database. | Kiểm tra đích kết nối và `logicalFilePath` trước khi chạy `update`. |
| `clearCheckSums` làm validation qua nhưng schema vẫn cũ | Chỉ xử lý checksum; không áp dụng thay đổi logic. | Tạo changeset mới để sửa schema/data thực. |
| `changelogSync` xong không còn pending nhưng thiếu bảng | Changeset bị đánh dấu đã chạy, không thực thi SQL. | Điều tra history/schema drift và lập remediation. |
| Old changeset lỗi vì bảng đã tồn tại khi retry | DDL cũ đã tự commit hoặc bảng tồn tại trước đó. | Dừng retry; kiểm tra table definition, transaction và history. |
| Backfill chạy lại làm trùng dữ liệu | DML không idempotent hoặc được ép chạy lại. | Thiết kế điều kiện unique/WHERE, test dữ liệu đã có. |
| Database mới dựng được nhưng nâng cấp production lỗi | Fix chỉ kiểm thử trên trạng thái zero, bỏ qua dữ liệu và schema cũ. | Test từ snapshot có lịch sử đại diện production. |
| Rollback của fix làm mất dữ liệu mới | Phép đảo ngược không còn an toàn sau thời gian chạy thật. | Dùng backup/restore hoặc compensating migration đã kiểm chứng. |
| App cũ lỗi sau khi fix | Schema đổi phá tương thích khi rolling deployment. | Expand–migrate–contract và kế hoạch thứ tự phát hành. |

Một dấu hiệu quan trọng là **“history không còn pending” nhưng kết quả nghiệp vụ vẫn sai**. Khi đó tiếp tục sửa history không giải quyết mục tiêu; cần xác định bất biến bị vi phạm trong schema hoặc dữ liệu rồi đưa ra changeset/biện pháp dữ liệu phù hợp.

## 14. Bài thực hành có kiểm chứng

**Tình huống:** service khách hàng đã triển khai bảng `customer_record(email VARCHAR(80))`. Yêu cầu mới cần tối đa 255 ký tự. Hãy chọn sửa tiến thay vì chỉnh lại changeset cũ.

### Giai đoạn A — Quan sát history cũ

1. Trên PostgreSQL thử nghiệm, chạy changeset `001` ở mục 3.1.
2. Truy vấn `DATABASECHANGELOG` xác định `ID`, `AUTHOR`, `FILENAME`, `EXECTYPE` và `MD5SUM`.
3. Kiểm tra metadata cột `email` để xác minh giới hạn 80.
4. Ghi lại checksum, mã nguồn và trạng thái schema.

### Giai đoạn B — Quan sát anti-pattern trên database cô lập

1. Trên **bản sao lab**, sửa trực tiếp `VARCHAR(80)` thành `VARCHAR(255)` trong `001`.
2. Chạy `validate` và ghi nhận kết quả checksum/validation trên phiên bản Liquibase đang dùng.
3. Kiểm tra cột thật **không tự nới** chỉ vì sửa định nghĩa.
4. Khôi phục changelog `001` về nội dung ban đầu trong lab.

### Giai đoạn C — Thực hiện sửa tiến

1. Giữ nguyên `001`, thêm `002` ở mục 3.2.
2. Chạy `validate`, `status --verbose` và `update-sql`; kiểm tra `002` là changeset mới.
3. Chạy `update` trên database thử đã có `001`; xác minh email dài hơn 80 ký tự nhưng không quá 255 được lưu/đọc đúng.
4. Truy vấn history để xác nhận có cả `001` và `002`, không có một bản ghi khác mượn lại `001`.
5. Chạy `update` lần nữa nếu an toàn; `002` thông thường không được thực thi lại.

### Giai đoạn D — Thử trên database mới

1. Tạo database thử độc lập chưa có history.
2. Chạy changelog có cả `001` và `002` từ đầu.
3. Đối chiếu schema cuối và dữ liệu kiểm thử với database ở giai đoạn C.
4. Kiểm tra rollback: liệu thu hẹp về 80 có còn an toàn sau khi lưu email dài? Nếu không, ghi rõ chiến lược roll-forward/restore.

**Tiêu chí đạt:** giải thích được vì sao không sửa changeset cũ; xác định changeset mới bằng ID/author/FILENAME; đọc được checksum và history; kiểm chứng schema cuối giống nhau từ hai điểm khởi đầu; có kế hoạch xử lý rollback phù hợp với dữ liệu thật.

## 15. Checklist trước khi quyết định forward fix

- [ ] Đã xác minh changeset cũ có được áp dụng ở bất kỳ môi trường nào chưa.
- [ ] Đã giữ nguyên ID, author, đường dẫn logic và nội dung của changeset lịch sử.
- [ ] Đã đọc `DATABASECHANGELOG` và kiểm tra schema/data thật, không dựa duy nhất vào history.
- [ ] Đã xác định rõ trạng thái trước và trạng thái mục tiêu.
- [ ] Fix dùng changeset mới, ID mới, vị trí trong chuỗi migration đúng.
- [ ] Preconditions bảo vệ giả định thật; không dùng `MARK_RAN` như cách che drift.
- [ ] DML có điều kiện rõ, kiểm tra số hàng bị tác động và tình huống retry.
- [ ] Đã kiểm tra khả năng transaction/implicit commit, lock và dữ liệu đang phục vụ.
- [ ] Đã thử trên database đã chạy history cũ và database mới từ zero.
- [ ] Đã đối chiếu `validate`, `status`, SQL preview, schema và history sau update.
- [ ] Đã cân nhắc rollback, backup, restore và tính tương thích với ứng dụng cũ/mới.
- [ ] Không dùng `clearCheckSums`/`validCheckSum`/`changelogSync` thay thế việc sửa schema/data.
- [ ] CI/CD và Spring Boot dùng cùng artifact, phiên bản Liquibase/driver và cấu hình đích.
- [ ] Có bằng chứng review, test và phê duyệt trước production.

## 16. Câu hỏi tự kiểm tra

1. Vì sao chỉnh định nghĩa `CREATE TABLE` trong changeset đã chạy không tự làm cột trong production thay đổi?
2. Bộ ba định danh changeset và vai trò của `MD5SUM` khác nhau như thế nào?
3. Khi nào có thể chỉnh một changeset cũ mà chưa cần tạo fix mới? Cần xác minh điều gì?
4. Vì sao `clearCheckSums` không phải cách nới cột `VARCHAR(80)` lên `VARCHAR(255)`?
5. Một database đã có `001` và database mới chưa có `001` sẽ chạy chuỗi `001` → `002` ra sao?
6. Precondition `tableExists` và `columnExists` còn thiếu thông tin nào khi dự án có schema drift?
7. Khi nào `runOnChange` là lựa chọn có chủ đích, và vì sao không nên tự thêm nó vào `createTable` đã chạy?
8. Nếu DDL tự commit rồi changeset lỗi, vì sao bổ sung changeset mới phía sau chưa chắc xử lý được?
9. `MARK_RAN`, `changelogSync` và việc sửa `DATABASECHANGELOG` khác nhau thế nào với một migration sửa tiến?
10. Vì sao rollback từ `VARCHAR(255)` về `VARCHAR(80)` có thể không an toàn sau khi đã có dữ liệu mới?
11. Sửa tiến DML cần những kiểm chứng gì để tránh làm thay đổi sai nhiều hàng?
12. Tại sao phải thử cả database mới và database đã có dữ liệu/lịch sử production đại diện?
13. Khi nào nên chọn rollback có kiểm chứng thay vì forward fix?
14. Trong rolling deployment, chiến lược expand–migrate–contract giúp giảm rủi ro nào?

## Kết luận

**Changeset đã triển khai là một phần lịch sử, không phải bản nháp được phép viết lại cho đẹp.** Khi schema hoặc dữ liệu cần thay đổi, hãy giữ định danh và định nghĩa cũ, dùng một changeset mới để chuyển từ trạng thái đã ghi nhận sang trạng thái mong muốn. `DATABASECHANGELOG`, checksum, `validate`, `status` và SQL preview giúp kiểm soát quá trình ấy, nhưng bằng chứng cuối cùng vẫn là **schema, dữ liệu và ứng dụng thực tế** sau migration. Sửa tiến có kiểm chứng tạo ra chuỗi thay đổi dễ truy vết, giảm sai lệch giữa các môi trường và giúp `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` vận hành đáng tin cậy cùng Spring Boot và CI/CD.
