# Phân biệt rollback migration, khôi phục bản sao lưu và sửa tiến

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, người học quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Phần thực hành chú trọng migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Hoàn tác**, giải quyết câu hỏi thiết yếu khi một lần triển khai database gặp sự cố: **nên rollback các changeset, khôi phục bản sao lưu, hay tạo một migration mới để sửa tiến về phía trước?**

Ba phương án này không tương đương:

- **Rollback migration:** thực thi các thao tác đảo ngược đã được thiết kế cho những changeset cụ thể.
- **Khôi phục bản sao lưu (backup restore):** khôi phục trạng thái database từ bản sao hoặc một mốc thời gian được bảo vệ trước đó.
- **Sửa tiến (forward fix):** tạo thay đổi mới để đưa database và ứng dụng từ trạng thái hiện tại đến một trạng thái đúng, không cố quay lại trạng thái cũ.

Lựa chọn sai có thể làm mất những giao dịch vừa phát sinh, xóa một cột đang chứa dữ liệu mới, khôi phục lịch sử Liquibase không phù hợp hoặc để ứng dụng chạy trên schema không còn tương thích.

Sau bài này, bạn cần có khả năng:

1. Mô tả ranh giới của từng chiến lược và loại trạng thái mà mỗi chiến lược có thể thay đổi.
2. Chọn phương án theo dữ liệu đã được ghi sau deployment, mức độ lỗi, RPO/RTO và độ an toàn của thao tác đảo ngược.
3. Thiết kế changeset có rollback rõ ràng, xem trước SQL rollback và không nhầm rollback với transaction.
4. Giải thích tác động tới DATABASECHANGELOG, DATABASECHANGELOGLOCK, checksum và lần chạy Liquibase tiếp theo.
5. Lập runbook xử lý sự cố có bước dừng, điều tra, kiểm chứng, thực thi và hậu kiểm.
6. Tích hợp quyết định khôi phục vào Spring Boot/CI/CD mà không tạo retry hoặc rollback tự động nguy hiểm.

## 2. Một tình huống xuyên suốt

Ứng dụng quản lý đơn hàng có bảng purchase_order chứa trạng thái dạng chuỗi. Release mới gồm:

- **Changeset A:** thêm cột status_code.
- **Changeset B:** backfill status_code từ status_text.
- **Changeset C:** thêm khóa ngoại từ status_code tới bảng danh mục trạng thái.
- **Ứng dụng mới:** bắt đầu ghi trực tiếp vào status_code.

Giả sử A và B đã chạy xong, C thất bại vì còn một số mã tham chiếu không hợp lệ. Trong lúc đó, một phần instance ứng dụng mới đã được khởi động và có đơn hàng mới được tạo.

Có ba hướng xử lý đáng cân nhắc:

1. **Rollback:** hoàn tác những changeset đã chạy. Nhưng nếu DROP COLUMN status_code, các đơn hàng mới ghi chỉ vào cột đó có thể mất trạng thái.
2. **Restore:** đưa database về snapshot trước release. Nhưng tất cả đơn hàng và thanh toán hợp lệ phát sinh sau mốc sao lưu có nguy cơ biến mất nếu khôi phục đè toàn bộ database.
3. **Forward fix:** giữ cấu trúc và dữ liệu hiện có, xử lý các mã sai, bổ sung migration còn thiếu rồi hoàn tất triển khai. Phương án này có thể tránh mất giao dịch mới, nhưng cần xác minh ứng dụng và dữ liệu vẫn tương thích.

Không có một nút “undo” an toàn cho mọi trường hợp. Phải dựa trên **trạng thái database thực tế**, những thay đổi ứng dụng đã thực hiện và cách mỗi phương án ảnh hưởng đến dữ liệu mới.

## 3. Phân biệt ba phương án trên cùng một bảng

| Tiêu chí | Rollback migration | Khôi phục bản sao lưu | Forward fix |
|---|---|---|---|
| Mục tiêu | Đảo ngược các thay đổi được chọn | Đưa database về snapshot hoặc thời điểm được khôi phục | Sửa trạng thái hiện có bằng thay đổi mới |
| Công cụ chủ đạo | Liquibase rollback và rollback khai báo | Công cụ backup/PITR của DBMS, snapshot đã kiểm chứng | Changeset mới, SQL sửa dữ liệu, job backfill có kiểm soát |
| Phạm vi | Những changeset mục tiêu và các đối tượng liên quan | Database, cluster, schema hoặc phạm vi mà cơ chế restore hỗ trợ | Tập đối tượng và bản ghi được xác định |
| Dữ liệu mới sau deploy | Có nguy cơ bị mất nếu rollback xóa cấu trúc/dữ liệu | Có thể bị mất khi restore đè về mốc cũ | Có cơ hội bảo toàn nếu thiết kế đúng |
| Lịch sử DATABASECHANGELOG | Có thể thay đổi theo những changeset bị rollback | Trở về lịch sử tại mốc backup nếu restore toàn bộ metadata | Tiếp tục với changeset mới, nhưng phải xử lý trạng thái dở dang trước |
| Thời gian thực hiện | Phụ thuộc lượng changeset và SQL rollback | Phụ thuộc dung lượng, khả năng backup/PITR và topology | Phụ thuộc độ phức tạp của lỗi và việc chuyển đổi |
| Điều kiện tiên quyết | Rollback được hỗ trợ, đã thử và còn an toàn với dữ liệu hiện tại | Backup hợp lệ, phục hồi được, có mốc khôi phục và kế hoạch đối soát | Hiểu nguyên nhân lỗi và trạng thái hiện tại; có cách sửa kiểm chứng được |
| Rủi ro chính | Đảo ngược gây mất dữ liệu hoặc phá tương thích ứng dụng | Mất giao dịch mới, lệch với hệ thống ngoài | Logic sửa sai, bỏ sót trường hợp biên hoặc kéo dài trạng thái trung gian |

Điều quan trọng nhất không phải công cụ nào tiện hơn, mà là **phương án nào đưa hệ thống đến trạng thái đúng với mức thiệt hại và thời gian gián đoạn chấp nhận được**.

## 4. Phân biệt transaction rollback và rollback migration

Cùng gọi là “rollback” nhưng có hai phạm vi hoàn toàn khác nhau.

**Transaction rollback** diễn ra bên trong một giao dịch database chưa commit. Nếu lệnh DDL/DML trong transaction thất bại và DBMS hỗ trợ, database có thể hoàn tác phần chưa commit.

**Liquibase migration rollback** là thao tác chủ động đảo ngược những changeset đã được áp dụng theo lịch sử. Liquibase đọc changelog, xác định những changeset thuộc phạm vi rollback rồi thực hiện các bước rollback tương ứng theo thứ tự thích hợp, thường ngược với thứ tự áp dụng.

Sơ đồ minh họa:

~~~text
Release
  +-- changeset A --> COMMIT
  +-- changeset B --> COMMIT
  +-- changeset C --> LỖI

Lỗi C không tự hoàn tác A và B.

Nếu muốn đảo A và B:
  cần lệnh rollback mục tiêu + rollback khả dụng + kiểm chứng dữ liệu.
~~~

Mặc định, Liquibase cố chạy mỗi changeset trong transaction khi DBMS hỗ trợ. Thuộc tính runInTransaction có thể thay đổi hành vi; một số DDL gây implicit commit hoặc không chạy được trong transaction. Vì vậy, rollback migration **không đồng nghĩa** một giao dịch nguyên tử bao trọn toàn bộ release.

Kể cả khi một câu SQL đảo ngược thực thi thành công, dữ liệu phát sinh sau khi ứng dụng mới được triển khai vẫn có thể không được khôi phục về đúng ý nghĩa nghiệp vụ.

## 5. Liquibase biết phải rollback những gì bằng cách nào?

Trong một lần update, Liquibase xác định changeset bằng **id, author và đường dẫn changelog** (hoặc logicalFilePath khi được cấu hình) và ghi thông tin thực thi vào **DATABASECHANGELOG**.

Khi rollback, Liquibase cần:

1. Kết nối đúng database và dùng đúng changelog cùng các tham số liên quan.
2. Xác định mốc rollback: tag, số lượng changeset hoặc thời điểm.
3. Xác định những changeset trong lịch sử cần đảo theo mốc đó.
4. Tìm hoặc tạo được thao tác rollback thích hợp cho từng changeset mục tiêu.
5. Thực hiện, cập nhật lịch sử và báo cáo kết quả.

**Không phải change type nào cũng có thể tự đảo ngược.** Một số change type có auto rollback được Liquibase hỗ trợ; số khác cần rollback tường minh hoặc không thể khôi phục dữ liệu đã mất.

Ví dụ:

| Thay đổi ban đầu | Thao tác đảo về mặt cấu trúc | Vấn đề cần cảnh giác |
|---|---|---|
| createIndex | dropIndex | Truy vấn có thể chậm lại; cần kiểm tra index có do changeset tạo |
| addColumn | dropColumn | Mọi dữ liệu mới trong cột bị mất |
| createTable | dropTable | Bảng có thể chứa dữ liệu đã được ứng dụng ghi |
| addForeignKeyConstraint | dropForeignKeyConstraint | Mất hàng rào toàn vẹn tham chiếu |
| insert mã tham chiếu | delete theo mã tương ứng | Mã có thể đã được đơn hàng tham chiếu |
| update dữ liệu nghiệp vụ | Khôi phục giá trị cũ nếu có bản ghi đáng tin cậy | SQL đảo ngược không thể đoán chính xác giá trị ban đầu |
| dropColumn/dropTable | Không có phép đảo đủ dữ liệu chỉ từ tên đối tượng | Cần backup, nguồn dữ liệu hoặc phương án phục hồi riêng |

Nếu rollback không tồn tại hoặc không đủ an toàn, **không nên thêm một lệnh DELETE/DROP tùy tiện chỉ để công cụ ngừng báo lỗi**.

## 6. Thiết kế changeset có rollback tường minh

Ví dụ một changeset tạo index trên bảng purchase_order đã tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: schema-team
      comment: Tăng tốc truy vấn đơn hàng theo thời gian tạo
      changes:
        - createIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_created_at
            columns:
              - column:
                  name: created_at
      rollback:
        - dropIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_created_at
~~~

Changeset này có thao tác đảo **có chủ đích**: xóa đúng index đã tạo. Tuy nhiên, sau rollback, ứng dụng hoặc báo cáo có thể bị ảnh hưởng hiệu năng. Vì vậy “không mất dữ liệu” chỉ là một phần của đánh giá an toàn.

Một thay đổi thêm cột có thể được mô tả:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-002
      author: schema-team
      changes:
        - addColumn:
            tableName: purchase_order
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(20)
      rollback:
        - dropColumn:
            tableName: purchase_order
            columnName: status_code
~~~

**Cảnh báo:** rollback DROP COLUMN sẽ xóa dữ liệu trong status_code. Nếu ứng dụng mới đã ghi dữ liệu quan trọng vào cột này, rollback có thể gây mất thông tin không phục hồi được từ cấu trúc cũ.

Bởi vậy, rollback cần được đánh giá không chỉ theo câu SQL đúng cú pháp, mà theo **trạng thái dữ liệu và phiên bản ứng dụng tại thời điểm quyết định hoàn tác**.

## 7. Tag, rollback theo số lượng và rollback theo thời gian

Liquibase hỗ trợ các cách lựa chọn mốc rollback như tag, số lượng changeset hoặc thời điểm, tùy phiên bản và tính năng CLI đang sử dụng.

### 7.1. Đặt mốc bằng tag

Có thể tạo mốc tại ranh giới giữa hai release. Ví dụ, một changeset đánh dấu trạng thái trước khi bắt đầu các migration mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-baseline
      author: release-team
      changes:
        - tagDatabase:
            tag: before_release_2026_11

  - changeSet:
      id: 2026-11-19-add-order-index
      author: schema-team
      changes:
        - createIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_created_at
            columns:
              - column:
                  name: created_at
      rollback:
        - dropIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_created_at
~~~

Ví dụ giả định bảng purchase_order và cột created_at đã có. **Tag là mốc trong lịch sử Liquibase, không phải bản sao dữ liệu**. Rollback về tag nhằm đảo các changeset thích hợp sau mốc đó; nó không tự phục hồi những giao dịch nghiệp vụ mới.

### 7.2. Xem trước trước khi rollback

Các lệnh sau giả định kết nối database và đường dẫn changelog đã được cấu hình. Cú pháp tùy chọn cụ thể cần kiểm tra trên phiên bản Liquibase của dự án:

~~~bash
liquibase validate
liquibase history
liquibase rollback-sql --tag=before_release_2026_11
liquibase rollback --tag=before_release_2026_11
~~~

**rollback-sql** dùng để xem trước SQL mà Liquibase dự kiến thực thi, giúp reviewer kiểm tra thứ tự, đối tượng bị xóa và những điểm có thể làm mất dữ liệu. Chỉ thực hiện rollback thật sau khi xem xét bản preview, kết quả dữ liệu và kế hoạch ứng dụng.

### 7.3. Rollback theo số lượng

Lựa chọn theo số lượng changeset có thể thích hợp khi mục tiêu rất rõ, ví dụ vừa chạy một thay đổi độc lập. Nhưng một đợt release có thể có nhiều changeset, bao gồm cả những thay đổi đã được ứng dụng sử dụng. Đếm số lượng mà không kiểm tra lịch sử rất dễ chọn nhầm phạm vi.

### 7.4. Rollback theo thời điểm

Rollback theo thời điểm phụ thuộc timestamp lịch sử của Liquibase và tập changeset phù hợp. Đây **không phải** cơ chế khôi phục database về đúng trạng thái ở một giây bất kỳ như point-in-time recovery của DBMS; nó vẫn thực hiện các thao tác rollback của changeset đã triển khai.

**Nguyên tắc:** tag/count/date đều là cách chọn phạm vi **migration rollback**; không thay thế backup hay xác minh dữ liệu nghiệp vụ.

## 8. Vì sao có rollback SQL vẫn chưa chắc có thể rollback?

Xem ba tình huống:

**Tình huống A: cột vừa thêm chưa được dùng.** Rollback DROP COLUMN có thể chấp nhận nếu xác minh không có dữ liệu mới hoặc quy tắc nghiệp vụ phụ thuộc cột.

**Tình huống B: cột vừa thêm đã chứa dữ liệu duy nhất.** DROP COLUMN làm mất dữ liệu mà không có nguồn khôi phục. Dù Liquibase chạy rollback thành công, hệ thống có thể sai về nghiệp vụ.

**Tình huống C: dữ liệu tham chiếu đã được sử dụng.** Rollback DELETE mã trạng thái mới có thể vi phạm FOREIGN KEY hoặc làm đơn hàng mất ý nghĩa nếu khóa ngoại không được bảo vệ đúng.

Mức độ an toàn phụ thuộc vào:

- Dữ liệu nào được ghi kể từ lúc migration chạy?
- Thay đổi có bị các bảng, dịch vụ hoặc báo cáo khác tham chiếu không?
- Bản ứng dụng hiện tại có còn chạy được sau khi đảo DDL không?
- Có thể xây dựng lại dữ liệu cần giữ từ backup, sự kiện hoặc lịch sử đáng tin cậy không?
- Thao tác đảo có gây lock hoặc downtime vượt quá ngưỡng chấp nhận không?

**Rollback đúng kỹ thuật không đồng nghĩa rollback đúng về nghiệp vụ.**

## 9. Dữ liệu nghiệp vụ và bài toán không thể đảo ngược

Schema migration có thể dễ mô tả phép đảo ở cấp DDL; dữ liệu nghiệp vụ thường khó hơn nhiều.

Giả sử migration chuẩn hóa:

~~~sql
UPDATE customer
SET phone_number = REGEXP_REPLACE(phone_number, '[^0-9]', '', 'g');
~~~

Nếu nhiều chuỗi nguồn khác nhau cho cùng một kết quả đã chuẩn hóa, phép biến đổi có thể **không đảo ngược được**. Ví dụ các số điện thoại có dấu cách, dấu gạch hoặc ngoặc có thể trở thành cùng dạng chỉ gồm chữ số.

Muốn trở về giá trị trước đó, cần một **nguồn lưu giá trị cũ đáng tin cậy**, chẳng hạn bảng đối soát có phiên bản, backup, audit history hoặc dữ liệu gốc do chủ dữ liệu quản lý. Không thể tự đoán chuỗi ban đầu từ giá trị đã chuẩn hóa.

Tương tự, một UPDATE gộp nhiều trạng thái giao dịch thành một mã mới có thể mất thông tin phân biệt. Trong các trường hợp này:

1. Cần nhận diện tính mất mát thông tin trước deployment.
2. Có thể phải ghi snapshot dữ liệu mục tiêu hoặc nhật ký ánh xạ trước khi chuyển đổi.
3. Cần xác định cách xử lý các bản ghi được thêm hoặc sửa sau migration.
4. Nếu không thể hoàn tác an toàn, đánh dấu thay đổi là **không có rollback tự động an toàn** và thiết kế forward fix hoặc restore dữ liệu chọn lọc.

Không dùng rollback rỗng để truyền đạt rằng dữ liệu đã được khôi phục. Một thay đổi không có rollback tự động cần runbook phục hồi riêng.

## 10. Khôi phục bản sao lưu là gì?

**Backup restore** dùng bản sao dữ liệu và metadata đã được bảo vệ trước đó để phục hồi database. Phạm vi có thể là toàn database, instance, cluster hoặc tập đối tượng được công cụ quản trị hỗ trợ. Nó khác migration rollback bởi **không dựa vào từng changeset để đảo SQL**.

Các cơ chế phổ biến có thể bao gồm:

- **Full backup**: bản sao đầy đủ ở một thời điểm hoặc mốc nhất quán.
- **Incremental/differential backup**: chỉ lưu phần thay đổi theo phương án backup của hệ quản trị.
- **Snapshot storage**: ảnh chụp trạng thái hạ tầng, chỉ hữu ích nếu đạt yêu cầu nhất quán cho database.
- **Point-in-time recovery (PITR)**: kết hợp backup và nhật ký giao dịch như WAL/binlog để phục hồi đến mốc được hỗ trợ.
- **Khôi phục chọn lọc**: dựng bản sao từ backup rồi trích xuất những bản ghi hoặc đối tượng cần thiết, với quy trình đối soát riêng.

Tên và giới hạn cụ thể khác nhau theo PostgreSQL, MySQL, SQL Server, Oracle, dịch vụ database managed và hạ tầng backup.

**Có file backup không đồng nghĩa có khả năng restore.** Phải biết bản sao có nhất quán không, có đủ log để phục hồi không, có thể giải mã và truy cập không, có thử phục hồi thành công trên môi trường độc lập không.

## 11. RPO và RTO quyết định chiến lược restore

Hai khái niệm vận hành quan trọng:

- **RPO — Recovery Point Objective:** mức mất mát dữ liệu tối đa theo thời gian mà hệ thống chấp nhận trong một sự cố.
- **RTO — Recovery Time Objective:** thời gian tối đa mục tiêu để phục hồi dịch vụ hoạt động.

Ví dụ, snapshot được tạo lúc 10:00 và sự cố phát hiện lúc 10:25. Nếu chỉ có thể restore về 10:00, những dữ liệu hợp lệ phát sinh trong 25 phút có thể bị mất khi khôi phục đè. Nếu có PITR tới thời điểm ngay trước thao tác gây lỗi, khoảng mất mát có thể giảm, nhưng vẫn phải xác định **mốc an toàn thật sự** và những giao dịch hợp lệ đã xảy ra xen kẽ.

| Bối cảnh | Restore có thể phù hợp? | Điều phải xác minh |
|---|---|---|
| Database thử nghiệm không có dữ liệu cần giữ | Thường dễ cân nhắc | Snapshot đúng cấu hình, có thể dựng lại |
| Production chưa nhận ghi mới sau deployment | Có thể là phương án rõ ràng | Bản backup nhất quán và thời gian restore chấp nhận |
| Production có nhiều giao dịch hợp lệ sau deployment | Rủi ro cao nếu restore đè | RPO, giao dịch mới và kế hoạch khôi phục/chuyển tiếp dữ liệu |
| Dữ liệu bị hủy hàng loạt, không có phép đảo chính xác | Backup/PITR có thể rất quan trọng | Khả năng phục hồi và đối soát mất mát |
| Chỉ vài bản ghi cần phục hồi | Có thể khôi phục chọn lọc | Tránh ghi đè toàn bộ database, kiểm chứng quan hệ dữ liệu |

Cần đo thực tế thời gian backup/restore. Một database nhiều terabyte có thể không đạt RTO dù backup hoàn toàn hợp lệ.

## 12. Vì sao restore toàn bộ database có thể làm mất giao dịch hợp lệ?

Xét mốc thời gian:

~~~text
10:00  Backup nhất quán
10:05  Chạy migration release
10:08  Ứng dụng mới được mở cho người dùng
10:10  Người dùng tạo đơn hàng A
10:15  Người dùng thanh toán đơn hàng A
10:20  Phát hiện lỗi migration
10:25  Quyết định phương án khôi phục
~~~

Nếu restore **đè** database về 10:00, thông tin đơn hàng và thanh toán sau 10:00 có thể biến mất khỏi database, trong khi cổng thanh toán hoặc hệ thống khác vẫn ghi nhận giao dịch đó. Đây không chỉ là mất một vài row: hệ thống có thể **lệch với các bên ngoài**.

Để giảm rủi ro, có thể cần:

1. Tạm dừng hoặc cô lập các luồng ghi theo quy trình vận hành.
2. Chụp lại trạng thái hiện tại để bảo toàn bằng chứng và dữ liệu sau sự cố.
3. Dựng backup/PITR trên một database **riêng** trước, không ghi đè ngay production.
4. Đối chiếu những giao dịch phát sinh giữa mốc khôi phục và hiện tại.
5. Xây dựng kế hoạch replay/nhập lại dữ liệu hợp lệ nếu khả thi và được nghiệp vụ phê duyệt.
6. Chỉ chuyển lưu lượng khi database được khôi phục đã được kiểm chứng và ứng dụng tương thích.

Việc khôi phục riêng để lấy dữ liệu có thể phù hợp hơn restore đè nếu mục tiêu chỉ là lấy lại một tập bản ghi hoặc giá trị cũ.

## 13. Backup restore ảnh hưởng thế nào đến lịch sử Liquibase?

Bảng **DATABASECHANGELOG** nằm trong database do Liquibase quản lý. Nếu restore toàn bộ database về một mốc trước một release, lịch sử Liquibase cũng có thể quay về mốc đó cùng các đối tượng schema và dữ liệu.

Hệ quả:

- Những changeset được chạy **sau mốc backup** có thể không còn row lịch sử.
- Changelog và artifact ứng dụng đang triển khai có thể vẫn là phiên bản **sau** mốc backup.
- Khi chạy Liquibase lần tiếp theo, các changeset có thể được xem là pending và cố chạy lại.
- Nếu restore chỉ một phần schema/dữ liệu mà **không khôi phục tương ứng lịch sử Liquibase**, tình trạng lịch sử và đối tượng thực tế có thể không nhất quán.
- Các thay đổi ngoài database như phát sự kiện, gọi API, gửi thông báo hoặc lưu file không tự biến mất khi restore database.

Vì vậy, một runbook restore phải bao gồm bước **đồng bộ phiên bản ứng dụng, cấu hình Liquibase, lịch sử migration và các hệ thống tích hợp**. Không nên chỉ khôi phục dữ liệu rồi restart mọi instance với artifact mới nhất.

Không tự chèn hoặc xóa row DATABASECHANGELOG để “làm cho khớp” khi chưa có bằng chứng và quy trình quản trị. Lịch sử migration cần phản ánh trạng thái thực tế, không phải chỉ vượt qua bước validate.

## 14. Sửa tiến (forward fix) là gì?

**Forward fix** là thay đổi có version mới nhằm đưa hệ thống **từ trạng thái hiện tại tới trạng thái đúng**. Với Liquibase, phương án phổ biến là thêm changeset mới vào changelog và triển khai theo thứ tự có kiểm soát.

Ví dụ: một release tạo cột status_code và backfill, nhưng chưa bổ sung đầy đủ mã tham chiếu; nhiều đơn hàng mới đã dùng cột status_code. Thay vì DROP COLUMN và mất dữ liệu mới, nhóm có thể:

1. Xác định những mã tham chiếu thiếu và quy tắc nghiệp vụ chính xác.
2. Bổ sung mã còn thiếu bằng changeset mới.
3. Sửa các bản ghi có mã không hợp lệ theo ánh xạ được chủ dữ liệu phê duyệt.
4. Kiểm tra không còn dữ liệu vi phạm.
5. Tạo hoặc áp dụng khóa ngoại còn thiếu.
6. Hậu kiểm và mở lại luồng triển khai.

**Ưu điểm:** có cơ hội giữ nguyên giao dịch mới và tránh quay lại schema cũ. **Nhược điểm:** yêu cầu hiểu đúng nguyên nhân và trạng thái dở dang; một fix sai có thể làm drift lan rộng.

Không xem forward fix là “bỏ qua lỗi” bằng MARK_RAN. Mục tiêu là **sửa trạng thái thực tế** và ghi lại một chuỗi thay đổi có kiểm chứng.

### Một hạn chế rất quan trọng

Nếu một changeset trước đó **thất bại giữa chừng và vẫn pending**, chỉ thêm changeset mới ở **sau** nó trong changelog chưa chắc giúp pipeline chạy tới phần sửa; Liquibase có thể tiếp tục thất bại tại changeset cũ.

Khi đó cần một kế hoạch phục hồi cụ thể: xác minh phần đã áp dụng, cleanup có kiểm soát hoặc cơ chế điều chỉnh lịch sử được phê duyệt, rồi mới tiếp tục chuỗi changeset. Không sửa changeset đã chạy trên các môi trường khác một cách tùy tiện và không dùng clear-checksums để che giấu trạng thái dở dang.

## 15. Ví dụ forward fix với một changeset mới

Giả sử bảng order_status và purchase_order.status_code đã tồn tại. Bản release trước thiếu mã trạng thái REVIEW nhưng application đã bắt đầu sử dụng mã đó. Sau khi nghiệp vụ xác nhận REVIEW là mã chuẩn, có thể bổ sung bằng changeset riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003-add-review-status
      author: data-team
      comment: Bổ sung trạng thái REVIEW được xác nhận theo nghiệp vụ
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: order_status
        - sqlCheck:
            expectedResult: "0"
            sql: >
              SELECT COUNT(*)
              FROM order_status
              WHERE code = 'REVIEW'
      changes:
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: REVIEW
              - column:
                  name: display_name
                  value: Chờ kiểm tra
      rollback:
        - delete:
            tableName: order_status
            where: "code = 'REVIEW'"
~~~

**Điều kiện để ví dụ an toàn:**

- Bảng order_status tồn tại và có khóa/cơ chế không cho phép mã bị trùng.
- REVIEW đã được chủ sở hữu nghiệp vụ phê duyệt về ý nghĩa và điều kiện sử dụng.
- Nếu REVIEW đã tồn tại, HALT để kiểm tra xem dữ liệu có đúng ý nghĩa hay không; không tự MARK_RAN.
- Rollback DELETE chỉ an toàn khi REVIEW **chưa được dữ liệu nghiệp vụ tham chiếu**. Nếu đã được dùng, không nên xóa mã mà không giải quyết các tham chiếu.
- Những changeset cũ đang pending hoặc lỗi dở dang phải được xử lý trước theo runbook, không kỳ vọng thêm changeset này tự vượt qua chúng.

Forward fix thường được xem là thay đổi **ít phá hủy hơn**, nhưng vẫn phải có hậu kiểm và chiến lược khôi phục riêng.

## 16. Bảng quyết định: nên rollback, restore hay forward fix?

| Tình huống | Ưu tiên xem xét | Vì sao |
|---|---|---|
| Vừa tạo index lỗi hiệu năng; chưa có phụ thuộc dữ liệu | **Rollback migration** | Xóa index có thể đủ để khôi phục hành vi cũ |
| Vừa thêm cột; ứng dụng chưa ghi vào cột mới | **Rollback migration**, sau khi xác minh | Có khả năng đảo DDL mà ít mất dữ liệu |
| Cột mới đã được ứng dụng sử dụng để ghi dữ liệu độc nhất | **Forward fix** | DROP COLUMN có thể làm mất dữ liệu mới |
| Dữ liệu bị DELETE hàng loạt, không còn nguồn khác | **Restore/PITR** hoặc phục hồi chọn lọc | Có thể cần bản sao trạng thái trước khi lỗi |
| Backfill sai ánh xạ nhưng đã lưu giá trị gốc trong bảng audit | **Forward fix hoặc phục hồi chọn lọc** | Có dữ liệu gốc để sửa chính xác mà không cần đảo cả DB |
| Database production có nhiều giao dịch mới sau mốc backup | **Forward fix**, hoặc restore có kế hoạch replay | Restore đè có nguy cơ mất giao dịch hợp lệ |
| Migration chỉ thành công một phần; trạng thái không rõ | **Dừng và điều tra trước** | Chưa đủ căn cứ chọn thao tác khôi phục |
| Lỗi cấu trúc chưa có dữ liệu mới, rollback đã được thử | **Rollback migration** | Có thể quay lại an toàn với ít tác động |
| Data corruption lan rộng và không thể xác định bộ bản ghi bị ảnh hưởng | **Restore/PITR** cần được đánh giá nghiêm túc | Cần tìm lại trạng thái nguồn đáng tin cậy |

Đây là **định hướng lựa chọn**, không phải quy tắc tự động. Phải xét mức độ khẩn cấp, RPO/RTO, topology, ứng dụng đang chạy và các hệ thống liên quan.

Một câu hỏi ra quyết định có ích: **phương án nào giữ được nhiều dữ liệu hợp lệ nhất và có bằng chứng kiểm chứng trạng thái sau khi thực hiện?**

## 17. Quy trình xử lý sự cố trước khi quyết định

Khi phát hiện migration có vấn đề, hãy tách **xác định trạng thái** khỏi **hành động khôi phục**.

### Bước 1: ngăn lỗi lan rộng

- Tạm dừng pipeline migration hoặc auto-retry nếu đang lỗi.
- Không restart liên tục ứng dụng có Liquibase tự chạy khi chưa hiểu trạng thái.
- Nếu cần, chặn luồng ghi mới vào chức năng bị ảnh hưởng, theo quy trình sự cố đã được phê duyệt.
- Không tự động DROP/DELETE hay restore đè chỉ vì muốn giảm thời gian cảnh báo.

### Bước 2: ghi nhận mốc thời gian

Ghi lại lúc bắt đầu migration, những changeset đã hoàn tất, thời điểm ứng dụng mới được bật, thời gian phát sinh giao dịch mới và thời điểm phát hiện lỗi.

### Bước 3: kiểm tra trạng thái database

Xác định:

- Bảng/cột/index/constraint nào đã thực sự thay đổi?
- Dữ liệu nào đã được cập nhật hoặc xóa?
- Có transaction, khóa hoặc DDL dài còn đang chạy không?
- Các changeset đang ở trạng thái EXECUTED, MARK_RAN, RERAN hay pending?
- Có dữ liệu nghiệp vụ mới phát sinh sau deployment không?
- Các ứng dụng/worker tích hợp nào đang đọc hoặc ghi cấu trúc mới?

### Bước 4: đánh giá ba phương án

- **Rollback:** có SQL rollback thích hợp, dữ liệu mới và dependency có cho phép không?
- **Restore:** backup có kiểm chứng, mốc phục hồi nào khả dụng, RPO/RTO có chấp nhận không?
- **Forward fix:** có thể sửa chính xác từ trạng thái hiện tại, tránh mất giao dịch mới không?

### Bước 5: thử trong môi trường cô lập

Dùng bản sao database có lịch sử và dữ liệu tương tự khi có thể. Kiểm tra SQL preview, rollback, restore hoặc forward fix tương ứng. Các thử nghiệm phá hủy không được làm trực tiếp trên production.

### Bước 6: thực thi có người chịu trách nhiệm

Có người phê duyệt, cửa sổ triển khai, log và điểm dừng. Với restore, cần điều phối hạ tầng, ứng dụng và các hệ thống ngoài database.

### Bước 7: hậu kiểm

Không chỉ kiểm tra lệnh thoát thành công. Đối chiếu schema, dữ liệu, DATABASECHANGELOG, nghiệp vụ, hiệu năng và phiên bản ứng dụng.

## 18. Checklist cho rollback migration trước production

| Câu hỏi | Mục đích |
|---|---|
| Mốc tag/count/date có trỏ đúng release cần đảo không? | Tránh rollback quá phạm vi |
| Những changeset nào sẽ bị đảo? | Xác định dependency và thứ tự |
| SQL rollback đã được xem trước chưa? | Phát hiện DROP/DELETE và nguy cơ dữ liệu |
| Có change type nào không hỗ trợ rollback tự động không? | Tránh dừng giữa quá trình rollback |
| Đã kiểm tra dữ liệu mới sau deployment chưa? | Tránh xóa dữ liệu hợp lệ |
| Ứng dụng hiện tại có tương thích với schema cũ không? | Tránh khôi phục database nhưng gây lỗi ứng dụng |
| DDL rollback có gây lock/downtime lớn không? | Đánh giá ảnh hưởng production |
| Có backup hoặc phương án phục hồi bổ sung không? | Chuẩn bị khi rollback chính nó thất bại |
| Đã thử trên bản sao có lịch sử chưa? | Xác nhận SQL và dữ liệu |
| Có hậu kiểm DATABASECHANGELOG và schema không? | Xác nhận lịch sử và trạng thái thực khớp |

Đặc biệt, thao tác rollback có thể **thất bại giữa chừng**. Nếu một vài changeset đã bị đảo nhưng bước sau lỗi, cần điều tra tương tự như khi update lỗi; không mặc định toàn bộ rollback là nguyên tử.

## 19. Checklist cho khôi phục backup/PITR

Một runbook restore nên làm rõ:

1. Backup gần nhất và chuỗi incremental/log tương ứng **còn toàn vẹn**.
2. Mốc phục hồi dự kiến và mức mất dữ liệu chấp nhận được.
3. Công cụ, credential, quyền truy cập và encryption key cần thiết.
4. Database nào sẽ được restore, có làm đứt quan hệ với database/dịch vụ khác không.
5. Cần khôi phục sang **môi trường riêng** trước hay có thể phục hồi tại chỗ.
6. Cách bảo toàn và xử lý giao dịch phát sinh sau mốc restore.
7. Cách kiểm chứng consistency, constraint, số bản ghi và đối soát nghiệp vụ.
8. Cách chọn lại phiên bản ứng dụng, cấu hình Liquibase và migration history.
9. Cách chuyển lưu lượng, kiểm soát ghi đồng thời và theo dõi sau phục hồi.
10. Bằng chứng đã **diễn tập restore thực tế**, không chỉ kiểm tra backup job báo success.

Với dịch vụ managed, các thao tác snapshot/restore có thể tạo instance mới hoặc thay đổi endpoint. Kế hoạch chuyển kết nối và dữ liệu phát sinh song song có thể quan trọng ngang với việc restore dữ liệu.

## 20. Checklist cho forward fix

Một kế hoạch forward fix tốt cần:

- [ ] Xác định nguyên nhân gốc, không chỉ triệu chứng lỗi.
- [ ] Lập danh sách những thay đổi đã có hiệu lực, những bước còn thiếu và dữ liệu sai.
- [ ] Chứng minh phép sửa không ghi đè giao dịch hợp lệ mới.
- [ ] Thiết kế changeset mới với id/author ổn định, không sửa lịch sử đã triển khai.
- [ ] Có precondition bảo thủ và điều kiện dừng nếu schema/data khác dự kiến.
- [ ] Xử lý rõ những changeset trước đó thất bại hoặc còn pending.
- [ ] Chia dữ liệu lớn theo lô có checkpoint nếu cần.
- [ ] Thử trên bản sao có dữ liệu và lịch sử tương ứng.
- [ ] Review validate, update-sql và các câu DML/DDL thực tế.
- [ ] Có kế hoạch rollback hoặc forward fix kế tiếp nếu phương án đầu chưa đạt.
- [ ] Đã xác định tiêu chí nghiệp vụ và hậu kiểm đo được.
- [ ] Đã cập nhật runbook để không lặp lại cùng một lỗi.

Sửa tiến **không phải** lệnh update lại nguyên changelog với các giả định cũ. Nó là một thay đổi có chủ đích, có version và đủ bằng chứng để chứng minh trạng thái được sửa đúng.

## 21. DATABASECHANGELOG, checksum và locking trong ba chiến lược

### 21.1. Rollback thay đổi lịch sử theo mốc

Khi Liquibase rollback các changeset đã được ghi nhận, lịch sử cần phản ánh rằng những changeset đó không còn ở trạng thái đã áp dụng như trước. Nếu chạy update lại, chúng có thể được xử lý lại theo lịch sử và điều kiện hiện hành. Vì vậy phải giữ tệp changelog và cấu hình phù hợp, không đổi id/author/đường dẫn logic tùy tiện.

### 21.2. Restore quay cả dữ liệu lẫn lịch sử, nếu phục hồi cùng phạm vi

Một bản restore đầy đủ có thể đưa DATABASECHANGELOG về trạng thái cũ. Nếu lại chạy một ứng dụng phiên bản mới tự chạy Liquibase, những changeset sau mốc restore có thể được áp dụng lại ngay. Đây là hành vi có thể đúng với kế hoạch rebuild, nhưng có thể nguy hiểm nếu chưa đối soát các hệ thống ngoài database.

### 21.3. Forward fix tiếp tục lịch sử nhưng không được che giấu lỗi dở dang

Thông thường, forward fix thêm changeset mới và giữ nguyên lịch sử cũ. Nếu trước đó có changeset failed hoặc đã áp dụng một phần ngoài transaction, cần xác minh và xử lý trạng thái ấy; không dùng MARK_RAN hay clear-checksums chỉ để pipeline vượt qua.

### 21.4. DATABASECHANGELOGLOCK không làm rollback/restore trở nên nguyên tử

DATABASECHANGELOGLOCK giúp điều phối các lần chạy Liquibase. Nó **không** tự bảo vệ giao dịch nghiệp vụ, không làm một chuỗi DDL thành một transaction lớn và không tự khôi phục backup.

Nếu tiến trình migration lỗi và lock bị giữ, cần xác nhận không còn tác vụ chạy trước khi thực hiện xử lý lock theo quy trình vận hành. Giải phóng lock sai thời điểm có thể dẫn đến hai tiến trình cập nhật database chồng lấn.

### 21.5. Checksum không phải cơ chế khôi phục

Checksum phát hiện một số thay đổi trong nội dung changeset được ghi nhận. Nó không khôi phục dữ liệu đã mất. Không dùng clear-checksums để thay thế việc tìm hiểu vì sao schema hiện tại khác lịch sử hoặc vì sao rollback thất bại.

## 22. Tương thích ứng dụng và chiến lược expand–migrate–contract

Trong hệ thống có rolling deployment, ứng dụng cũ và mới có thể hoạt động cùng lúc. Đó là lý do rollback schema ngay sau khi triển khai mã ứng dụng mới có thể rủi ro.

Một chiến lược giảm rủi ro:

1. **Expand:** thêm cột/bảng mới nhưng chưa xóa cấu trúc cũ, bảo đảm ứng dụng cũ vẫn hoạt động.
2. **Migrate:** backfill và đồng bộ dữ liệu trong thời gian nhiều phiên bản ứng dụng cùng chạy.
3. **Contract:** chỉ xóa cấu trúc cũ khi không còn phụ thuộc và đã có bằng chứng nghiệp vụ.

Nếu rollout gặp lỗi ở giai đoạn expand hoặc migrate, **rollback ứng dụng** có thể đơn giản hơn rollback schema, miễn schema mới vẫn tương thích với mã cũ. Nếu dữ liệu đã được ghi theo cấu trúc mới, forward fix thường an toàn hơn việc xóa cột.

Nếu đã thực hiện contract và xóa cột cũ, khả năng rollback ứng dụng về phiên bản trước có thể mất. Khi đó phải cân nhắc restore/forward fix và khả năng tái tạo dữ liệu cũ từ nguồn có kiểm chứng.

**Nguyên tắc:** kế hoạch rollback ứng dụng và kế hoạch rollback database phải được review cùng nhau, nhưng **không được coi là cùng một thao tác**.

## 23. Spring Boot và CI/CD: đừng gắn rollback database vào rollback ứng dụng một cách mù quáng

Spring Boot có thể chạy Liquibase khi ứng dụng khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Khi có nhiều instance hoặc database đang được nhiều dịch vụ sử dụng, nên xác định một cơ chế điều phối migration rõ ràng. Một job migration chuyên trách trong CI/CD thường giúp dễ xem SQL, đặt mốc tag, kiểm tra hậu triển khai và chủ động xử lý sự cố.

Quy trình release điển hình:

~~~text
Kiểm tra changelog + SQL dự kiến
        |
        v
Tạo/kiểm chứng backup và xác định mốc tag
        |
        v
Thực hiện migration
        |
        v
Đối soát schema + dữ liệu + DATABASECHANGELOG
        |
        v
Triển khai/bật tính năng ứng dụng
        |
        v
Theo dõi và sẵn sàng phương án khôi phục
~~~

Nếu migration thất bại, pipeline phải dừng hoặc chuyển sang nhánh xử lý sự cố đã định nghĩa. Không nên tự chạy một lệnh rollback database chỉ vì deploy ứng dụng thất bại, bởi database có thể đã nhận dữ liệu mới và rollback có thể xóa dữ liệu đó.

Trong CI/CD, nên lưu bằng chứng:

- Git commit và phiên bản artifact chứa changelog.
- Phiên bản Liquibase/DBMS, cấu hình cần thiết không bí mật và context/label.
- Kết quả validate, SQL dự kiến và lịch sử migration.
- Mốc tag được sử dụng khi chuẩn bị release.
- Kết quả đối soát dữ liệu trước/sau deployment.
- Backup ID, mốc khôi phục có thể dùng và kết quả diễn tập.
- Quyết định rollback/restore/forward fix có người phê duyệt nếu có sự cố.

## 24. Ví dụ tình huống: dữ liệu đơn hàng đã có giao dịch mới

### Đề bài

Một release thêm status_code và chuyển dữ liệu cũ từ status_text. Sau đó ứng dụng mới bắt đầu ghi status_code. Mười phút sau, nhóm phát hiện một số trạng thái không có mã tham chiếu phù hợp; khóa ngoại mới không thể thêm. Trong khoảng mười phút ấy, hệ thống đã tiếp nhận 2.000 đơn hàng mới.

Có backup ngay trước release và rollback của addColumn đã khai báo DROP COLUMN.

### Phân tích

**Rollback migration:** DROP COLUMN có thể loại bỏ status_code của 2.000 đơn hàng mới. Chỉ cân nhắc nếu chứng minh được không mất dữ liệu hoặc có kế hoạch chuyển dữ liệu ngược an toàn, ứng dụng cũng tương thích.

**Backup restore:** đưa database về trước release có thể làm mất 2.000 đơn hàng mới và các thao tác thanh toán. Muốn dùng restore, cần xác định RPO, PITR, bản sao khôi phục riêng và kế hoạch xử lý dữ liệu đã phát sinh sau mốc backup.

**Forward fix:** nếu các đơn hàng mới vẫn còn nguyên dữ liệu, có thể bổ sung mã tham chiếu còn thiếu và xử lý các bản ghi lỗi theo quy tắc được phê duyệt. Sau khi dữ liệu đạt, thêm khóa ngoại và hậu kiểm. Đây thường là phương án đáng ưu tiên xem xét nếu có thể sửa chính xác mà không xóa giao dịch mới.

**Điều kiện tiên quyết:** kiểm tra C đã thất bại ở đâu và liệu A/B đã được ghi lịch sử đúng chưa. Nếu C bị áp dụng một phần, cần xác minh/cleanup trước khi tiếp tục. Không chỉ thêm một changeset mới ở cuối rồi cho rằng Liquibase sẽ vượt được lỗi cũ.

### Câu hỏi tự kiểm tra

1. Có thể rollback cột mới chỉ vì YAML có khối rollback không? **Không**, phải xét dữ liệu mới và tương thích ứng dụng.
2. Backup trước release có tự bảo toàn 2.000 đơn hàng mới không? **Không**, nếu restore đè về mốc cũ.
3. Có thể dùng PITR như migration rollback theo tag không? **Không**, cơ chế và phạm vi hoàn toàn khác.
4. DATABASECHANGELOG có đủ chứng minh tất cả mã trạng thái đều hợp lệ không? **Không**, cần đối soát dữ liệu.
5. Nếu có giá trị cũ được lưu trong audit, có thể dùng chúng hỗ trợ khôi phục chọn lọc không? **Có**, nhưng phải bảo toàn các thay đổi hợp lệ phát sinh sau mốc lỗi.
6. Nếu changeset C vẫn pending và tiếp tục thất bại, chỉ append một changeset mới có đủ không? **Không chắc**, phải xử lý trạng thái lỗi và thứ tự thực thi.
7. Rollback ứng dụng có tự rollback schema không? **Không**.

## 25. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách tiếp cận đúng |
|---|---|---|
| Đồng nhất rollback transaction với rollback migration | Tưởng toàn release được hoàn tác khi một changeset lỗi | Xác định ranh giới transaction và lịch sử changeset |
| Thấy rollback SQL là chạy ngay | Xóa dữ liệu mới hoặc phá ứng dụng | Kiểm tra dữ liệu, dependency, preview và bản thử |
| Restore đè production ngay khi có lỗi | Mất giao dịch phát sinh sau snapshot | Đánh giá RPO/RTO, restore riêng và đối soát |
| Xem tag Liquibase như snapshot database | Tin rằng rollback tag phục hồi mọi dữ liệu | Hiểu tag chỉ xác định mốc lịch sử migration |
| Thêm changeset sửa ở cuối khi changeset cũ vẫn lỗi | Pipeline có thể không bao giờ chạy tới fix | Xử lý trạng thái dở dang và thứ tự trước |
| Chỉ dựa vào DATABASECHANGELOG | Bỏ sót SQL đã có hiệu lực ngoài transaction | Đối chiếu với catalog, dữ liệu, log |
| Dùng clear-checksums để “phục hồi” | Che giấu sửa lịch sử, không khôi phục dữ liệu | Giữ lịch sử bất biến, dùng quy trình khôi phục |
| Coi rollback app đồng nghĩa rollback DB | Mất tương thích phiên bản | Lập kế hoạch app/database cùng nhau |
| Không thử restore trước sự cố | Backup không dùng được hoặc RTO quá lâu | Diễn tập và đo thời gian thực tế |
| Dùng MARK_RAN để vượt qua migration lỗi | Lịch sử “đã chạy” nhưng dữ liệu chưa đúng | Chỉ dùng khi trạng thái tương đương đã được chứng minh |
| Xóa mã tham chiếu khi rollback | Phá FK hoặc mất ý nghĩa dữ liệu | Kiểm tra tham chiếu, cân nhắc forward fix |

## 26. Checklist trước khi tuyên bố khôi phục thành công

- [ ] Đã xác định nguyên nhân sự cố và phạm vi ảnh hưởng.
- [ ] Đã xác nhận không còn migration/DDL hoặc job dữ liệu xung đột đang chạy.
- [ ] Có log và mốc thời gian đủ để giải thích quá trình xử lý.
- [ ] Schema/constraint/index đúng với phiên bản ứng dụng được chọn.
- [ ] DATABASECHANGELOG phù hợp trạng thái những changeset đã thực hiện.
- [ ] Không có lỗi checksum chưa được điều tra.
- [ ] Đã đối soát dữ liệu nghiệp vụ và dữ liệu tham chiếu.
- [ ] Các giao dịch phát sinh sau deploy được giữ lại hoặc được xử lý theo chính sách đã phê duyệt.
- [ ] Các hệ thống ngoài database đã được đối chiếu nếu có sự kiện/thanh toán tích hợp.
- [ ] Đã kiểm tra login, đọc/ghi, luồng nghiệp vụ quan trọng và hiệu năng.
- [ ] Đã xác nhận RPO/RTO nếu có restore và ghi nhận dữ liệu không thể phục hồi.
- [ ] Đã lưu lại quyết định, lệnh thực thi, bằng chứng và người phê duyệt.
- [ ] Đã có biện pháp tránh lặp lại sự cố.

## 27. Ghi nhớ

**Rollback migration, restore backup và forward fix là ba công cụ cho ba bài toán phục hồi khác nhau.** Rollback đảo các changeset theo lịch sử; restore lấy lại trạng thái từ bản sao/mốc thời gian; forward fix dùng thay đổi mới để sửa trạng thái đang tồn tại.

Không có phương án nào tự động bảo toàn tất cả dữ liệu hợp lệ và mọi hệ thống tích hợp. Trước khi lựa chọn cần hiểu **trạng thái database thực tế, dữ liệu phát sinh sau deploy, khả năng đảo ngược, RPO/RTO và phiên bản ứng dụng đang chạy**.

Với Liquibase, hãy version hóa changelog và rollback, xem trước SQL, bảo toàn lịch sử DATABASECHANGELOG, diễn tập backup/restore, thiết kế các release theo hướng expand–migrate–contract và kiểm chứng sau triển khai. Mục tiêu cuối cùng không phải “làm lệnh rollback chạy thành công”, mà là **đưa database và ứng dụng về một trạng thái nhất quán, đúng nghiệp vụ và có thể giải thích được**.
