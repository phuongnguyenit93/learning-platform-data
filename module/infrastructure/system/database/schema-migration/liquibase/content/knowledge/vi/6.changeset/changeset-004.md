# Changeset bất biến sau khi đã được triển khai

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Khi thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường hoặc tích hợp Spring Boot/CI/CD, cần áp dụng một nguyên tắc nhất quán: **changeset đã triển khai là một mốc lịch sử cần giữ bất biến**.

Khi có yêu cầu thay đổi thiết kế mới, cách thực hiện thông thường là **tạo changeset mới** để chuyển cấu trúc hoặc dữ liệu từ trạng thái cũ sang trạng thái mới. Sửa trực tiếp một changeset đã chạy có thể gây lỗi checksum hoặc khiến nhiều môi trường có lịch sử triển khai giống tên nhưng cấu trúc khác nhau.

## 1. Bất biến changeset nghĩa là gì?

Một changeset là đơn vị thay đổi trong changelog. Nó có thể thêm bảng, đổi cột, tạo index, bổ sung constraint hoặc di chuyển dữ liệu. Khi chưa được triển khai trên bất kỳ database được chia sẻ hay bản phát hành nào, nhóm có thể chỉnh sửa changeset trong quá trình review. Sau khi được triển khai, định nghĩa đó trở thành một phần của lịch sử.

**Bất biến** ở đây là nguyên tắc quản trị: không tùy tiện đổi định danh, nội dung nghiệp vụ hoặc hành vi thực thi của changeset đã chạy. File vẫn có thể sửa về mặt kỹ thuật; Liquibase cũng cung cấp các cơ chế chạy lại có chủ đích như runOnChange và runAlways. Nhưng những cơ chế này có phạm vi áp dụng riêng và không phải lý do để sửa lại migration chạy một lần.

Ba khái niệm liên quan cần phân biệt:

| Khái niệm | Nguồn | Cho biết điều gì? |
|---|---|---|
| Định nghĩa changeset | File changelog trong source control | Thay đổi được mô tả trong phiên bản mã nguồn hiện tại |
| Lịch sử changeset | Bảng DATABASECHANGELOG của từng database | Những changeset Liquibase đã ghi nhận là xử lý |
| Trạng thái schema thực tế | Catalog/metadata của database | Bảng, cột, index, constraint hiện đang tồn tại |

Sự tồn tại của một dòng trong DATABASECHANGELOG không chứng minh schema còn đúng; ngược lại, một cột tồn tại trong database cũng không chứng minh nó từng được tạo bởi Liquibase. Checksum chỉ giúp kiểm tra định nghĩa changeset, không phải hash toàn bộ database.

Ví dụ: changeset A đã tạo cột status có kiểu VARCHAR(20). Yêu cầu mới cần VARCHAR(40). Nếu sửa A, database mới có thể thấy một định nghĩa khác với database đã chạy A. Cách nên làm là giữ A nguyên vẹn và tạo **changeset B** để tăng độ dài cột.

## 2. Cách Liquibase nhận diện changeset và sử dụng checksum

### 2.1. Định danh gồm ba thành phần

Liquibase nhận diện một changeset theo tổ hợp:

1. **id:** mã định danh do tác giả đặt cho changeset.
2. **author:** tác giả hoặc nhóm chịu trách nhiệm.
3. **đường dẫn changelog:** đường dẫn file được dùng làm định danh; có thể kiểm soát bằng logicalFilePath khi thích hợp.

Ví dụ changeset YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create
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
                  defaultValue: PENDING
~~~

Nếu changeset này đã chạy, việc đổi id thành orders-001-initialize hoặc đổi author có thể khiến Liquibase coi nó như changeset khác. Khi chạy update, Liquibase có thể thử tạo lại bảng orders và báo lỗi vì bảng đã tồn tại.

Đổi thư mục chứa changelog cũng có thể ảnh hưởng định danh. Khi cần tái cấu trúc cây file, hãy kiểm tra cơ chế logicalFilePath của phiên bản đang dùng để duy trì đường dẫn nhận diện ổn định. Không đổi id, author, vị trí file và nội dung nghiệp vụ cùng lúc rồi kỳ vọng Liquibase tự đối chiếu với lịch sử cũ.

### 2.2. Checksum dùng để phát hiện thay đổi định nghĩa

Khi ghi nhận changeset đã chạy, Liquibase lưu thông tin như ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE và MD5SUM trong bảng DATABASECHANGELOG. Trong những lần kiểm tra tiếp theo, Liquibase so sánh định nghĩa changeset với lịch sử đã lưu. Nếu nội dung thuộc phạm vi tính checksum thay đổi và không có cơ chế ngoại lệ hợp lệ, Liquibase có thể báo lỗi validation.

Luồng xử lý thường gặp:

~~~text
Đọc changelog
      |
      v
Xác định changeset: id + author + đường dẫn
      |
      v
Tra DATABASECHANGELOG của database đích
      |
  +---+---------------------+
  |                         |
Chưa được ghi nhận      Đã được ghi nhận
  |                         |
  v                         v
Xét điều kiện           Kiểm tra checksum,
và thực thi              quy tắc chạy lại
  |                         |
  v                         v
Ghi lịch sử         Bỏ qua, chạy lại có chủ đích,
                    hoặc báo validation error
~~~

**Không suy luận rằng mọi thay đổi ký tự đều làm đổi checksum.** Một số comment, khoảng trắng hoặc metadata có thể được xử lý khác nhau theo định dạng và phiên bản Liquibase. Mặt khác, có những chỉnh sửa ảnh hưởng đến việc chọn changeset hoặc precondition mà không nhất thiết được phản ánh theo cách người dùng kỳ vọng từ checksum.

Vì vậy, nguyên tắc bất biến phải được hiểu ở **mức ý nghĩa và hành vi**. Kết quả validate thành công không cho phép tùy tiện đổi context, label, precondition hoặc những điều kiện quyết định môi trường nào chạy changeset.

### 2.3. Checksum khác với schema drift

Giả sử DBA xóa thủ công cột orders.status sau khi Liquibase tạo cột đó. Nếu không thay đổi changelog, checksum của changeset vẫn có thể khớp. Liquibase status có thể không liệt kê changeset là pending vì bảng DATABASECHANGELOG vẫn ghi nhận nó đã chạy.

Để phát hiện drift, cần kiểm tra catalog, snapshot hoặc diff giữa database đích và reference phù hợp. Checksum trả lời định nghĩa changeset có còn nhất quán với lịch sử không; nó không liên tục đối chiếu tất cả đối tượng hoặc dữ liệu nghiệp vụ.

## 3. Nguy cơ khi chỉnh sửa changeset đã chạy

### 3.1. Một định danh, hai cách triển khai

Giả sử dev chạy changeset A tạo cột status VARCHAR(20). Sau đó lập trình viên sửa trực tiếp A thành VARCHAR(40), trong khi production chưa chạy A.

| Môi trường | Thời điểm chạy A | Tình huống phát sinh |
|---|---|---|
| Dev | Trước khi sửa | Đã có cột VARCHAR(20) và checksum của A cũ |
| Production | Sau khi sửa | Có thể tạo cột VARCHAR(40) từ định nghĩa A mới |
| Test mới dựng | Sau khi sửa | Có thể nhận A mới khác kết quả dev |

Hai database có thể cùng nhận diện changeset A nhưng cấu trúc khác nhau. Dev cũng có thể bị lỗi checksum khi Liquibase đọc lại A đã sửa. Lịch sử không còn phản ánh một chuỗi thay đổi rõ ràng.

Cách xử lý: giữ A theo đúng bản đã triển khai, thêm B để đổi kiểu cột. Dev chỉ chạy B; production chạy A rồi B; hai môi trường có cơ hội hội tụ về cùng trạng thái dự kiến.

### 3.2. Mất khả năng tái tạo và kiểm toán

Một database mới cần chạy changelog từ đầu. Một database cũ cần chạy phần chưa có trong lịch sử. Nếu một changeset mang nhiều định nghĩa khác nhau qua thời gian, nhóm khó biết tại sao một bảng được tạo theo cấu trúc cụ thể, SQL nào đã chạy trong bản phát hành trước, hoặc rollback nào phù hợp với trạng thái thực tế.

Giữ bất biến giúp xác định chính xác thứ tự thay đổi, review được từng bước, đối chiếu với commit/artifact và tái tạo lịch sử trên môi trường thử nghiệm. Nó còn hỗ trợ điều tra sự cố, duy trì đường nâng cấp cho khách hàng có phiên bản cũ và kiểm soát thay đổi dữ liệu.

## 4. Mẫu chuẩn: thêm changeset mới thay vì sửa changeset cũ

Giả sử A đã chạy như sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create
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

Yêu cầu mới là tăng độ dài status lên 40 ký tự. Giữ nguyên A và thêm B:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-001-create
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

Đây là ví dụ minh họa cú pháp change type. Khả năng hỗ trợ, câu SQL thực tế, lock và rollback của modifyDataType phụ thuộc DBMS. Trước khi triển khai production, cần review update-sql và xác minh ảnh hưởng đến ứng dụng.

Kết quả kỳ vọng:

- Database mới: chạy A tạo bảng với VARCHAR(20), rồi B nâng cột thành VARCHAR(40).
- Database đã có A: A tiếp tục được nhận diện là đã chạy; chỉ B pending và được thực thi.
- Lịch sử: A và B được ghi nhận thành hai mốc có thể kiểm tra riêng.

**Tạo changeset mới** cũng áp dụng khi thêm ràng buộc, đổi index, đổi default value và chuyển dữ liệu. Với thay đổi ảnh hưởng dữ liệu hoặc độ sẵn sàng, có thể chia nhiều bước expand → migrate/backfill → switch ứng dụng → contract; mỗi bước có changeset, hậu điều kiện và thời điểm triển khai rõ ràng.

### 4.1. Khi cần làm migration dữ liệu

Ví dụ bổ sung cột email_normalized rồi cập nhật dữ liệu từ email. Thay vì chỉnh sửa changeset tạo bảng users ban đầu, tạo changeset thêm cột, changeset backfill có thể kiểm chứng và changeset thêm constraint khi dữ liệu đã đạt yêu cầu.

Với lượng dữ liệu lớn, không mặc định một UPDATE toàn bảng có thể chạy an toàn trong một changeset duy nhất. Cần xem xét batch, thời gian khóa, khả năng khởi động lại, idempotency, kiểm tra số dòng và compatibility với phiên bản ứng dụng đang hoạt động.

## 5. Phân loại thay đổi trước và sau triển khai

| Thay đổi | Khi chưa chạy ở môi trường dùng chung | Khi đã triển khai |
|---|---|---|
| Sửa SQL, cột hoặc type trong changeset | Cho phép trong quá trình review | Tạo changeset mới để sửa trạng thái |
| Đổi id hoặc author | Có thể thay đổi nếu chưa ai dùng | Tránh đổi vì ảnh hưởng định danh |
| Di chuyển file changelog | Có thể sắp xếp lại | Giữ logicalFilePath hoặc chuyển đổi có kiểm chứng |
| Thêm changeset mới | Bình thường | Là cách mở rộng mặc định |
| Sửa comment hoặc format | Có thể chỉnh sửa | Cân nhắc ảnh hưởng checksum/kiểm toán, ưu tiên giữ nguyên |
| Sửa context, label, precondition | Review phạm vi thực thi | Kiểm tra hành vi giữa môi trường đã và chưa chạy |
| Sửa định nghĩa rollback | Review trước phát hành | Cần kế hoạch và kiểm thử riêng, tránh thay đổi tùy tiện |
| Sửa changeset thiết kế để chạy lại | Theo cơ chế đã chọn | Chỉ khi đúng runOnChange/runAlways và có kiểm chứng |

**Mốc “đã triển khai”** nên tính từ bất kỳ môi trường dùng chung, staging, production, hệ thống của khách hàng hoặc artifact đã phát hành, không chỉ từ production. Một changeset chưa chạy ở production vẫn có thể đã nằm trong lịch sử dev hoặc staging.

## 6. Các cơ chế ngoại lệ có chủ đích

### 6.1. runOnChange

runOnChange cho phép Liquibase chạy lại changeset nếu nội dung được nhận diện là đã thay đổi. Cơ chế này phù hợp với một số đối tượng tái định nghĩa toàn bộ như view hoặc stored procedure, khi thực thi lại là hành vi mong muốn.

Ví dụ với SQL formatted changelog:

~~~sql
--liquibase formatted sql

--changeset database-team:orders-summary-view runOnChange:true
CREATE OR REPLACE VIEW orders_summary AS
SELECT id, status
FROM orders;
~~~

Chỉ dùng câu lệnh tương ứng ở DBMS có hỗ trợ. Changelog của một view có thể được cập nhật theo thiết kế đã định và changeset chạy lại khi thay đổi phù hợp. Cần bảo đảm câu lệnh an toàn khi lặp lại, không phụ thuộc trạng thái mơ hồ và được review trên các môi trường.

Không bật runOnChange cho migration tạo bảng hoặc chuyển dữ liệu chỉ để bỏ lỗi checksum. Không mặc định mọi chỉnh sửa khoảng trắng hoặc comment đều kích hoạt chạy lại.

### 6.2. runAlways

runAlways yêu cầu changeset thực hiện mỗi lần cập nhật phù hợp. Điều này chỉ phù hợp với tác vụ có chủ đích chạy nhiều lần và có thể kiểm chứng tác động lặp. Nếu cần thêm một thay đổi schema có thứ tự, một changeset mới sẽ dễ review hơn.

### 6.3. validCheckSum

validCheckSum dùng để khai báo những checksum cụ thể được coi là hợp lệ khi có lịch sử cần tương thích. Đây là cơ chế chấp nhận checksum, **không tự thực thi phần thay đổi mới** và không sửa schema cho khớp changelog. Chỉ dùng sau khi xác định lý do khác biệt, đối chiếu database và lưu quyết định kỹ thuật.

### 6.4. clear-checksums

~~~bash
liquibase clear-checksums
~~~

Lệnh này xóa các checksum đã lưu để Liquibase tính lại trong lần xử lý phù hợp về sau. Nó không tự sửa dữ liệu hoặc schema, và không biến mọi changeset lịch sử thành pending để chạy lại.

Dùng clear-checksums khi chưa hiểu nguyên nhân checksum khác nhau có thể làm mất dấu vết thay đổi ngoài dự kiến. Không coi đây là cách xử lý mặc định cho lỗi validation.

### 6.5. MARK_RAN và changelogSync

Precondition có thể dùng onFail: MARK_RAN hoặc một quy trình baseline có thể gọi changelogSync để ghi nhận changeset mà không thực thi nội dung. Những cơ chế này chỉ thích hợp khi đã kiểm tra database thực tế có trạng thái tương ứng.

Ghi nhận MARK_RAN không có nghĩa change SQL đã thực thi. Vì vậy, không dùng MARK_RAN hoặc changelogSync để che lỗi checksum, thiếu đối tượng hoặc migration thất bại.

## 7. Quy trình xử lý khi gặp checksum mismatch

Giả sử một lần chạy validate báo:

~~~text
Validation Failed:
  changeset orders-001-create has changed checksum
  stored checksum != current checksum
~~~

Làm theo quy trình:

1. **Dừng cập nhật database đích.** Không chỉnh tay cột MD5SUM hoặc xóa dòng trong DATABASECHANGELOG.
2. **Xác nhận định danh** gồm id, author và đường dẫn file, cũng như database/catalog/schema đang kết nối.
3. **Tìm bản đã triển khai** từ tag release, commit hoặc artifact tương ứng.
4. **So sánh định nghĩa** ở bản cũ và bản hiện tại; xác định có đổi SQL, kiểu dữ liệu, metadata, parser, logicalFilePath hoặc phiên bản Liquibase không.
5. **Kiểm tra schema và dữ liệu thật** để xác định tác động, bao gồm mọi thay đổi ngoài Liquibase.
6. **Ưu tiên khôi phục changeset lịch sử** và thêm changeset mới để thực hiện yêu cầu.
7. **Nếu dùng ngoại lệ**, ghi rõ nguyên nhân và bằng chứng phù hợp với validCheckSum, runOnChange hoặc cơ chế chính thức khác.
8. **Thử lại trên database có lịch sử tương đương**, chạy validate, status --verbose và update-sql trước khi triển khai.
9. **Lưu kết quả kiểm chứng** và bài học về quy trình review để ngăn tái diễn.

| Nguyên nhân | Cách xử lý ưu tiên | Rủi ro nếu xử lý sai |
|---|---|---|
| Đổi type trong changeset cũ | Trả changeset về bản cũ, thêm changeset mới | Hai môi trường có schema khác nhau |
| Đổi id/author | Khôi phục định danh lịch sử | Liquibase thử chạy lại thay đổi cũ |
| Di chuyển changelog | Ổn định đường dẫn logic, kiểm tra lịch sử | Changeset cũ xuất hiện pending |
| Khác biệt sau nâng cấp Liquibase | Kiểm chứng quy tắc checksum của phiên bản mới | Che lỗi chỉnh sửa nghiệp vụ thật |
| Changeset runOnChange chủ đích đổi view | Review câu lệnh chạy lại | Tác động lặp không an toàn |
| Đối tượng bị DBA sửa trực tiếp | Đối chiếu schema, tạo migration sửa chữa | Checksum khớp nhưng schema vẫn drift |

Không giải quyết checksum mismatch bằng cách chỉnh bảng DATABASECHANGELOGLOCK. Bảng đó điều phối khóa, không quản lý tính nhất quán nội dung changeset. Cũng không tự giải phóng lock khi vẫn có tiến trình migration thực thi.

## 8. Rollback và tính bất biến

Rollback là logic đảo ngược changeset đã triển khai theo phương thức Liquibase hỗ trợ. Nó không có nghĩa rằng được sửa tùy ý định nghĩa changeset cũ hoặc rằng mọi thay đổi đều khôi phục được.

Ví dụ tạo index kèm rollback tường minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-003-index-status
      author: database-team
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
      rollback:
        - dropIndex:
            tableName: orders
            indexName: idx_orders_status
~~~

Trước khi chạy rollback cần kiểm tra chính xác phạm vi changeset sẽ bị đảo ngược, SQL rollback, DBMS, khả năng khóa, tác động dữ liệu và tính tương thích với ứng dụng. Với thao tác xóa cột chứa dữ liệu, rollback thêm cột trở lại thường không phục hồi dữ liệu cũ. Với migration chuyển dữ liệu không đảo ngược, cần backup hoặc quy trình khôi phục được thử nghiệm.

Nếu DDL không được DBMS rollback theo transaction, một changeset thất bại có thể để lại thay đổi một phần dù chưa có bản ghi hoàn tất. Lúc đó cần kiểm tra database thực tế, log và transaction trước khi quyết định chạy lại hoặc bổ sung changeset sửa chữa.

## 9. Phối hợp nhiều môi trường

Mỗi database có bảng DATABASECHANGELOG riêng. Một thay đổi đã chạy ở staging nhưng chưa chạy ở production cũng phải được coi là lịch sử khi sửa source code. Quy tắc phối hợp:

- Dùng cùng nguồn changelog quản lý bằng version control và cùng quy tắc định danh id/author/file path.
- Xem artifact phát hành là bất biến; khi sửa yêu cầu, tạo thay đổi mới trong lần phát hành sau.
- Không viết lại changeset đã tồn tại ở các nhánh phát hành hoặc đã được khách hàng cài đặt.
- Review context, label, dbms và precondition để thấy môi trường nào sẽ chạy hoặc bỏ qua changeset.
- Kiểm tra đường nâng cấp từ database có lịch sử cũ cũng như đường tạo mới từ database trống.
- Không sao chép riêng DATABASECHANGELOG sang một database có schema không tương ứng.
- Sau thao tác khẩn cấp ngoài Liquibase, ghi nhận drift và đưa schema về trạng thái mong muốn bằng thay đổi có kiểm chứng.

Hai môi trường cùng có changeset A trong lịch sử chưa chắc cấu trúc thực tế giống nhau. Checksum và lịch sử cần được bổ sung bằng snapshot, diff hoặc truy vấn catalog và kiểm tra dữ liệu theo phạm vi nghiệp vụ.

## 10. Đưa nguyên tắc bất biến vào CI/CD

Một quy trình phát hành có thể tổ chức như sau:

~~~text
Developer thêm changeset mới
           |
           v
Review id / author / đường dẫn và bất biến lịch sử
           |
           v
Validate changelog
           |
           v
Test trên database mới + database đã có lịch sử
           |
           v
Review update-sql, rollback, precondition
           |
           v
Triển khai vào môi trường được chọn
           |
           v
Xác minh history, schema và smoke test
~~~

### 10.1. Các lệnh kiểm tra căn bản

Khi CLI được cấu hình sẵn URL, credentials và changelog đúng database đích:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Sau khi đã review và được phép triển khai:

~~~bash
liquibase update
liquibase history
~~~

validate giúp phát hiện các vấn đề trong changelog và checksum thuộc phạm vi kiểm tra của Liquibase; status hiển thị changeset pending theo bộ lọc hiện tại; update-sql cho thấy SQL dự kiến. Những lệnh này không chứng minh mọi dữ liệu và đối tượng trong database đã đúng. Cần kiểm tra hậu điều kiện quan trọng sau update.

### 10.2. Kiểm soát pull request

Reviewer nên xác minh:

1. PR có thêm changeset mới thay cho sửa nội dung nghiệp vụ của changeset đã chạy không?
2. Các id có duy nhất trong phạm vi định danh và đường dẫn changelog không?
3. Có thay đổi id, author hoặc logicalFilePath không?
4. Có thay đổi context, label, precondition của changeset lịch sử không?
5. Nếu có runOnChange hoặc runAlways, chúng có được thiết kế chạy lặp an toàn không?
6. Migration có tương thích với ứng dụng đang chạy và bản phát hành trước không?
7. Có hậu điều kiện, kế hoạch rollback/forward-fix và kiểm chứng dữ liệu không?
8. Bản build có chứa đúng changelog đã review không?

Pipeline có thể so sánh các changeset đã phát hành với PR mới và yêu cầu review đặc biệt khi thấy sửa/xóa hoặc di chuyển changeset lịch sử. Không nên phụ thuộc hoàn toàn vào validate vì cơ chế này không thay thế việc review thay đổi có ý nghĩa nghiệp vụ.

### 10.3. Tích hợp Spring Boot

Ứng dụng Spring Boot có thể chạy Liquibase khi khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi chạy nhiều instance, cần bảo đảm chúng dùng cùng changelog và bộ bảng metadata trên database đích; Liquibase lock giúp điều phối. Trong CI/CD, có thể đặt migration trong một job riêng trước khi triển khai phiên bản ứng dụng và tắt migration tự động ở các instance runtime nếu phù hợp kiến trúc.

Bất kể dùng Spring Boot, Liquibase CLI hay pipeline, quy tắc không sửa changeset đã triển khai vẫn phải được áp dụng nhất quán.

## 11. Bài thực hành: quan sát lỗi rồi sửa đúng

Chỉ thực hiện trên database thử nghiệm có thể dựng lại. Mục tiêu là so sánh hành vi của changeset bị sửa với changeset bổ sung.

### Bước 1. Chạy changeset ban đầu

~~~yaml
databaseChangeLog:
  - changeSet:
      id: practice-001
      author: learner
      changes:
        - createTable:
            tableName: practice_orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: note
                  type: VARCHAR(50)
~~~

Chạy:

~~~bash
liquibase validate
liquibase update-sql
liquibase update
liquibase history
~~~

Quan sát bảng practice_orders và dòng tương ứng trong DATABASECHANGELOG.

### Bước 2. Thử sửa changeset đã chạy

Sửa type của note trong practice-001 từ VARCHAR(50) thành VARCHAR(100). Chạy validate và quan sát thông báo nếu thay đổi ảnh hưởng checksum. Không chạy clear-checksums để che lỗi.

~~~bash
liquibase validate
~~~

Mục tiêu là chứng kiến sự không nhất quán giữa định nghĩa ở source hiện tại và lịch sử database; thông báo cụ thể phụ thuộc phiên bản Liquibase.

### Bước 3. Khôi phục định nghĩa rồi thêm changeset

Trả practice-001 về VARCHAR(50), sau đó tạo practice-002:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: practice-001
      author: learner
      changes:
        - createTable:
            tableName: practice_orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: note
                  type: VARCHAR(50)

  - changeSet:
      id: practice-002
      author: learner
      changes:
        - modifyDataType:
            tableName: practice_orders
            columnName: note
            newDataType: VARCHAR(100)
~~~

Chạy lại validate, status và update-sql. Nếu DBMS hỗ trợ phép đổi kiểu, thực hiện update trên database thử nghiệm rồi kiểm tra type cột và lịch sử. Database đã chạy practice-001 chỉ cần chạy practice-002; database thử nghiệm mới sẽ chạy lần lượt hai changeset.

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Không dùng ví dụ này như hướng dẫn chạy trực tiếp production: cần kiểm thử ảnh hưởng lên dữ liệu, khóa, rollback và tương thích ứng dụng.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Sửa SQL cũ để code sạch hơn là được” | Database đã chạy vẫn giữ lịch sử cũ, có thể lỗi checksum hoặc drift |
| “Production chưa chạy nên cứ sửa” | Staging, dev, khách hàng hoặc nhánh khác có thể đã chạy |
| “Checksum khớp là schema hoàn toàn đúng” | Checksum phản ánh định nghĩa changeset, không phản ánh đầy đủ trạng thái DB |
| “Đổi id/author không ảnh hưởng” | Định danh changeset có thể thay đổi và bị chạy lại |
| “Đổi đường dẫn file luôn an toàn” | Cần giữ định danh logic hoặc có kế hoạch di chuyển |
| “clear-checksums sẽ sửa schema” | Lệnh chỉ làm trống checksum đã lưu |
| “runOnChange nên bật cho mọi changeset” | Chỉ dùng khi changeset được thiết kế để chạy lại an toàn |
| “Rollback luôn khôi phục dữ liệu cũ” | Có những thay đổi dữ liệu không thể đảo ngược hoàn toàn |
| “Cùng DATABASECHANGELOG là cùng schema” | Schema vẫn có thể bị sửa thủ công hoặc migration dở dang |

## 13. Checklist phát hành

- [ ] Changeset đã chạy ở bất kỳ môi trường dùng chung nào được giữ nguyên định nghĩa lịch sử.
- [ ] Mọi yêu cầu schema/dữ liệu mới đều có changeset bổ sung với id riêng.
- [ ] Không đổi tùy tiện id, author, tên file hoặc logicalFilePath của changeset đã chạy.
- [ ] Các ngoại lệ runOnChange/runAlways có lý do và bằng chứng chạy lại an toàn.
- [ ] Không dùng validCheckSum, clear-checksums hay MARK_RAN để che lỗi chưa hiểu nguyên nhân.
- [ ] Context, label, dbms và precondition đã được review theo môi trường.
- [ ] validate, status, update-sql và hậu điều kiện đã được kiểm tra.
- [ ] Đã thử nâng cấp từ database cũ và tạo mới từ changelog khi cần.
- [ ] SQL rollback hoặc phương án forward-fix, backup và kiểm chứng dữ liệu đã được chuẩn bị.
- [ ] Artifact phát hành, log và lịch sử DATABASECHANGELOG có thể đối chiếu theo phiên bản.

## 14. Kết luận

**Changeset bất biến sau khi triển khai** giúp Liquibase giữ được một chuỗi lịch sử có thể tái tạo, kiểm toán và nâng cấp qua nhiều môi trường. id, author và đường dẫn logic giúp nhận diện changeset; checksum giúp kiểm soát những thay đổi định nghĩa đã ghi nhận. Khi nghiệp vụ yêu cầu thay đổi schema hoặc dữ liệu, ưu tiên tạo changeset mới theo thứ tự, kiểm chứng SQL và hậu điều kiện, thay vì viết lại mốc lịch sử.

Các tính năng runOnChange, runAlways, validCheckSum, clear-checksums, MARK_RAN và changelogSync có mục đích chuyên biệt và không thay thế quy tắc quản lý thay đổi. Kết hợp nguyên tắc bất biến với review Git, kiểm thử migration, rollback có kế hoạch và CI/CD nhất quán giúp hệ thống database phát triển an toàn mà vẫn hiểu rõ điều gì đã được triển khai.
