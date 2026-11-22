# Lựa chọn rollback, sửa tiến hoặc khôi phục dữ liệu khi có sự cố

Một migration vừa được triển khai và hệ thống bắt đầu lỗi: ứng dụng không đọc được cột mới, constraint làm một luồng ghi bị từ chối, backfill cập nhật sai dữ liệu hoặc DDL khiến truy vấn chậm nghiêm trọng. Đội vận hành phải quyết định nên **rollback changeset**, **sửa tiến bằng migration mới**, hay **khôi phục dữ liệu từ backup/point-in-time recovery (PITR)**. Chọn sai có thể làm mất dữ liệu mới, phá lịch sử Liquibase, khiến phiên bản ứng dụng không tương thích hoặc đưa hệ thống về một trạng thái còn lỗi hơn.

Bài học thuộc chương **Triển khai an toàn** của module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này cung cấp khung ra quyết định khi có sự cố, cách đánh giá tính đảo ngược của schema và dữ liệu, cách thực hiện rollback Liquibase có kiểm chứng, cách viết forward fix và cách khôi phục dữ liệu mà vẫn giữ được bằng chứng vận hành.

## 1. Ba hướng xử lý và mục tiêu khác nhau

Ba lựa chọn thường được nhắc cùng nhau nhưng giải quyết ba bài toán khác nhau:

| Hướng | Mục tiêu | Khi phù hợp | Điều phải chứng minh |
|---|---|---|---|
| **Rollback** | Đảo ngược một hoặc nhiều changeset để đưa schema/dữ liệu về trạng thái trước đó. | Có rollback an toàn, phạm vi rõ, ứng dụng và dữ liệu chưa phụ thuộc vào thay đổi mới. | Rollback thực sự khôi phục trạng thái mong muốn và không phá dữ liệu phát sinh sau deploy. |
| **Sửa tiến (forward fix)** | Thêm changeset mới để sửa trạng thái hiện tại theo hướng đúng. | Migration đã được sử dụng, rollback nguy hiểm, dữ liệu mới đã phát sinh hoặc cần duy trì tương thích. | Fix áp dụng được trên trạng thái thật của từng môi trường và có kiểm tra hậu điều kiện. |
| **Khôi phục dữ liệu (restore/PITR)** | Khôi phục database hoặc dữ liệu về một thời điểm/bản backup đã biết. | Dữ liệu bị xóa/sửa diện rộng, hỏng logic, không thể tái tạo bằng migration bù. | Điểm khôi phục, tính nhất quán, dữ liệu sau mốc khôi phục và kế hoạch đồng bộ hệ thống phụ thuộc đã rõ. |

Không có phương án mặc định luôn tốt nhất. Một lỗi schema nhỏ có thể sửa tiến trong vài phút; một lệnh xóa nhầm hàng triệu bản ghi có thể cần PITR; một thay đổi mới chưa có traffic và có rollback đã thử có thể rollback an toàn.

### 1.1. Phân biệt rollback ứng dụng và rollback database

Rollback binary ứng dụng và rollback schema là hai hành động riêng:

- **Rollback ứng dụng:** triển khai lại phiên bản binary/container trước.
- **Rollback database:** đảo ngược thay đổi schema hoặc dữ liệu.
- **Rollback toàn release:** phối hợp cả hai theo thứ tự tương thích.

Nếu phiên bản ứng dụng cũ không hiểu cột mới hoặc phiên bản mới cần cột mới, chỉ rollback ứng dụng có thể làm hệ thống lỗi. Ngược lại, rollback database trong khi binary mới vẫn chạy có thể khiến truy vấn mới thất bại.

Vì vậy, cần đánh giá hợp đồng schema giữa **phiên bản ứng dụng cũ, phiên bản ứng dụng mới và trạng thái database** trước khi chọn hành động.

## 2. Việc đầu tiên khi sự cố xảy ra

Trước khi chạy rollback, update hoặc restore, hãy ổn định tình hình và thu thập bằng chứng. Một thao tác khẩn cấp thiếu thông tin có thể làm mất dấu vết nguyên nhân.

### 2.1. Dừng tác động tiếp theo

1. Tạm dừng pipeline migration tự động và retry không kiểm soát.
2. Xác định release, changeset, commit và database bị ảnh hưởng.
3. Nếu migration đang chạy, xác định tiến trình còn hoạt động hay đã dừng; không tự giải phóng lock khi chưa xác minh.
4. Nếu dữ liệu đang bị ghi sai, cân nhắc tạm ngăn luồng ghi liên quan hoặc bật chế độ bảo trì theo quy trình sự cố.
5. Giữ ứng dụng và database ở trạng thái có thể quan sát; ghi nhận thời điểm bắt đầu, phạm vi và triệu chứng.

Không dừng database hoặc xóa object chỉ dựa trên một thông báo lỗi. Một số DDL có thể đã commit trước khi Liquibase ghi history; trạng thái thật phải được kiểm tra.

### 2.2. Thu thập trạng thái

Ghi nhận ít nhất:

- Database engine/version, database/schema và môi trường.
- Phiên bản ứng dụng trước/sau release.
- Phiên bản Liquibase, JDBC driver và changelog artifact.
- Changeset liên quan: ID, author, filename/logical path, execution type và checksum.
- Bản ghi `DATABASECHANGELOG` và trạng thái `DATABASECHANGELOGLOCK`.
- SQL đã thực thi, log ứng dụng, log database và thời điểm lỗi.
- Schema thật, dữ liệu bị ảnh hưởng, số hàng và các consumer liên quan.
- Backup gần nhất, WAL/binlog/archive log và khả năng PITR.

Thông tin bí mật phải được che khỏi log/báo cáo. Không chép password hoặc token vào ticket sự cố.

### 2.3. Xác định lỗi thuộc nhóm nào

| Nhóm sự cố | Ví dụ | Hướng điều tra đầu tiên |
|---|---|---|
| Schema | Thiếu cột, sai kiểu, constraint không tạo được. | Metadata schema, SQL và changeset. |
| Data | Backfill sai, xóa nhầm, dữ liệu trùng. | Phạm vi hàng, audit, transaction log, bản sao dữ liệu. |
| Performance/availability | Lock lâu, index build gây nghẽn, tăng replication lag. | Query/lock monitor, execution plan, DBMS log. |
| Compatibility | Binary cũ không hiểu schema mới. | Phiên bản app đang chạy, contract và thứ tự deploy. |
| Migration state | Changeset lỗi một phần, history không khớp schema. | DATABASECHANGELOG, EXECTYPE, DDL transaction behavior. |

Không dùng một biện pháp cho mọi nhóm. Rollback một changeset DDL không tự khôi phục các hàng dữ liệu đã bị ghi đè; restore database cũng không tự giải quyết một binary không tương thích.

## 3. Cây quyết định tổng quát

~~~mermaid
flowchart TD
    A[Sự cố sau migration] --> B[Ngăn retry và thu thập trạng thái]
    B --> C{Có mất/hỏng dữ liệu nghiêm trọng?}
    C -->|Có| D{Có backup/PITR đáng tin và phạm vi khôi phục rõ?}
    D -->|Có| E[Lập kế hoạch restore và đồng bộ hệ thống phụ thuộc]
    D -->|Không| F[Giữ bằng chứng, xác định nguồn dữ liệu có thể phục hồi]
    C -->|Không| G{Rollback có an toàn và đã kiểm thử?}
    G -->|Có| H{Ứng dụng/dữ liệu đã phụ thuộc schema mới?}
    H -->|Không| I[Preview và thực hiện rollback có kiểm soát]
    H -->|Có| J[Đánh giá forward fix hoặc rollback theo lộ trình tương thích]
    G -->|Không| K[Thiết kế changeset sửa tiến]
    J --> K
    K --> L[Test trên bản sao đại diện]
    I --> M[Kiểm tra schema, dữ liệu, history và ứng dụng]
    E --> M
    F --> M
    L --> M
    M --> N[Giám sát và ghi nhận kết quả sự cố]
~~~

Đây là khung lựa chọn, không phải quyết định tự động. Độ nghiêm trọng của sự cố, yêu cầu RPO/RTO, khả năng khôi phục và quyết định của incident commander/DBA có thể thay đổi phương án.

## 4. Khi nào nên rollback?

Rollback phù hợp khi có thể đảo ngược changeset một cách có dự đoán và trạng thái mới chưa trở thành nền tảng cho dữ liệu hoặc ứng dụng khác.

Các điều kiện thường cần:

- Changeset có rollback được định nghĩa hoặc loại change có rollback tự động được Liquibase hỗ trợ.
- Đã biết chính xác phạm vi changeset cần đảo.
- Đã xem trước và thử rollback SQL trên database đại diện.
- Dữ liệu phát sinh sau migration không bị mất hoặc đã có cách bảo toàn.
- Ứng dụng đã dừng dùng schema mới hoặc có thể chuyển về phiên bản tương thích.
- Không có changeset phụ thuộc phía sau đang được sử dụng.
- Có backup/restore point phù hợp với mức rủi ro.

Ví dụ thêm một index chưa được ứng dụng phụ thuộc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 021-add-customer-email-index
      author: db-team
      changes:
        - createIndex:
            tableName: customer_record
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
      rollback:
        - dropIndex:
            tableName: customer_record
            indexName: idx_customer_email
~~~

Rollback của index này có thể hợp lý nếu index vừa được tạo, không có dependency đặc biệt và thao tác drop không gây vấn đề vận hành. Với index lớn, việc drop vẫn cần đánh giá lock và tác động truy vấn. Tên change type và khả năng rollback phải được kiểm tra trên DBMS/phiên bản đang dùng.

### 4.1. Rollback tự động và rollback tùy chỉnh

Liquibase có thể tạo rollback tự động cho một số change type có thể đảo ngược rõ ràng, ví dụ thêm cột có thể được đảo bằng xóa cột. Nhưng không phải mọi change đều có rollback tự động:

- `insert` có thể được đảo bằng delete nếu xác định được chính xác hàng được insert.
- `update` thường không thể khôi phục giá trị cũ nếu không lưu before-image.
- `delete` không thể tự khôi phục nội dung hàng đã xóa nếu không có dữ liệu nguồn.
- `dropTable` không thể dựng lại dữ liệu đã mất chỉ từ định nghĩa bảng.
- SQL tùy chỉnh có thể không có rollback tự động.
- Một số DDL có behavior khác nhau theo DBMS hoặc không chạy trong transaction.

Khi cần, khai báo rollback tùy chỉnh trong changeset hoặc dùng SQL rollback rõ ràng. Rollback phải đảo đúng thay đổi của changeset, không nên dựa vào giả định “chạy câu ngược lại là đủ”.

### 4.2. Vì sao rollback có thể làm mất dữ liệu?

Ví dụ changeset thêm cột `preferred_language`, ứng dụng mới bắt đầu ghi giá trị vào cột. Nếu rollback bằng `dropColumn`, mọi giá trị đã ghi trong khoảng thời gian đó sẽ mất.

Trước khi rollback, hỏi:

1. Có dữ liệu mới được ghi vào object không?
2. Có thể export/copy dữ liệu đó sang nơi an toàn không?
3. Binary cũ có thể hoạt động trong khi cột vẫn tồn tại không?
4. Có thể rollback phần ứng dụng trước, giữ schema mở rộng tạm thời không?
5. Có consumer khác đã bắt đầu phụ thuộc vào object không?

Nếu chưa trả lời được, không thực hiện rollback phá hủy object chỉ để đưa schema giống snapshot cũ.

## 5. Sử dụng lệnh rollback Liquibase có kiểm soát

Liquibase hỗ trợ các phạm vi rollback như tới tag, tới ngày hoặc theo số changeset tùy phiên bản và cách dùng CLI/API. Những lệnh thường gặp gồm:

- `rollback --tag=<tag>`: rollback các changeset sau mốc tag được chỉ định.
- `rollback-count --count=<n>`: rollback một số changeset gần nhất theo phạm vi được hỗ trợ.
- `rollback-to-date --date=<timestamp>`: rollback theo mốc thời gian.
- Các command rollback cụ thể khác tùy phiên bản/edition.

Tên command và cú pháp đã thay đổi qua các thế hệ Liquibase. Hãy kiểm tra `liquibase --help` và tài liệu đúng phiên bản dự án; không sao chép lệnh của một phiên bản khác vào production.

### 5.1. Dùng tag làm mốc release

Có thể gắn tag sau khi một release đã được xác minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-release-2026-11
      author: release-team
      changes:
        - tagDatabase:
            tag: release-2026-11
~~~

Hoặc dùng command tag theo phiên bản Liquibase. Cần hiểu tag database được ghi nhận ở vị trí nào trong lịch sử và cách command rollback xử lý mốc đó. Nên kiểm tra trên database thử nghiệm trước khi coi tag là điểm rollback production.

Tag là **mốc lịch sử**, không phải backup. Nó không chứa dữ liệu để phục hồi và không bảo đảm mọi changeset sau tag đều có rollback an toàn.

### 5.2. Preview rollback trước khi thực thi

Quy trình nên có bước sinh SQL rollback để review:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml rollback-sql --tag=release-2026-11
~~~

Đây là ví dụ CLI khái quát; cú pháp command và option cần xác minh theo version. Xem toàn bộ SQL được sinh, đặc biệt:

- Có DROP TABLE, DROP COLUMN, DELETE hay truncate không?
- Có khôi phục đúng constraint/index/view không?
- Có thao tác nào cần chạy ngoài transaction không?
- Có tác động lên object/data được tạo sau release không?
- Có rollback custom nào không thể tự sinh hoặc bị thiếu không?

Nếu rollback preview không sinh được SQL vì changeset không có rollback, đó là tín hiệu phải thiết kế phương án khác. Không bỏ qua lỗi preview rồi đoán SQL.

### 5.3. Không chọn số lượng rollback theo cảm tính

`rollback-count` có thể rollback changeset gần nhất theo thứ tự history, không nhất thiết là “một feature” hoặc “một commit”. Nếu có nhiều nhóm cùng phát hành, một changeset không liên quan có thể nằm phía sau changeset gây lỗi.

Trước khi dùng rollback theo count:

- Đọc DATABASECHANGELOG và thứ tự thực thi.
- Xác định các changeset phía sau có dependency không.
- Kiểm tra tag hoặc phạm vi khác có biểu đạt release rõ hơn không.
- Sinh SQL preview và đối chiếu từng statement.

Không xóa trực tiếp hàng trong DATABASECHANGELOG để giả lập rollback. Liquibase cần history và schema nhất quán; sửa history không đảo SQL đã chạy.

## 6. Khi nào nên sửa tiến (forward fix)?

Sửa tiến thường phù hợp khi:

- Migration đã được áp dụng trên production và có traffic sử dụng schema mới.
- Rollback có thể xóa dữ liệu phát sinh sau deploy.
- Changeset cũ không có rollback hoặc rollback không đáng tin.
- DDL đã commit một phần và trạng thái database cần được sửa từ hiện trạng.
- Một hotfix đã được áp dụng thủ công và cần đưa vào lịch sử.
- Phiên bản ứng dụng cũ và mới đang chạy song song; cần giữ schema tương thích.
- Cần sửa logic dữ liệu bằng cách chuyển trạng thái hiện tại sang trạng thái đúng.

Forward fix là **changeset mới** mô tả một chuyển đổi từ trạng thái thực tế sang trạng thái mục tiêu. Không sửa nội dung changeset đã triển khai để cố thay đổi quá khứ.

### 6.1. Ví dụ sửa tiến cho cột sai kiểu

Giả sử changeset cũ tạo `customer_record.email VARCHAR(80)` và đã chạy. Một hotfix làm cột trên production thành `VARCHAR(255)`, nhưng changelog chưa ghi nhận. Nhóm xác nhận 255 là trạng thái mong muốn.

Thêm changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 022-normalize-customer-email-length
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

Ví dụ này mô tả trạng thái chuẩn hóa. Trên production đã là 255, cần xác minh behavior của modifyDataType khi chạy trên kiểu đã đúng, DBMS cụ thể và SQL được sinh. Có thể cần một chiến lược baseline/điều kiện bổ sung để tránh thực hiện DDL không cần thiết. Không giả định precondition chỉ kiểm tra tồn tại là đủ để nhận diện kiểu cũ/mới.

Trên staging còn 80, changeset đưa cột tới 255. Trên database mới, chuỗi migration tạo 80 rồi chuyển lên 255; nếu muốn database mới tạo thẳng 255, vẫn cần bảo toàn lịch sử changeset đã phát hành và kiểm chứng kết quả cuối. Đây là ví dụ về việc các môi trường có trạng thái xuất phát khác nhau nhưng phải hội tụ.

### 6.2. Ví dụ sửa tiến dữ liệu sai

Giả sử một changeset trước đó đã chuẩn hóa nhầm `status` của một nhóm khách hàng. Không nên chạy lại changeset cũ sau khi thêm WHERE hoặc xóa bản ghi history. Hãy tạo changeset sửa dữ liệu mới với:

- Điều kiện xác định chính xác tập hàng bị ảnh hưởng.
- Nguồn dữ liệu đúng để khôi phục giá trị.
- Số hàng dự kiến và ngưỡng dừng nếu vượt dự kiến.
- Cách lưu before-image hoặc audit để truy vết.
- Batch size và kế hoạch lock nếu bảng lớn.
- Hậu điều kiện kiểm tra số hàng, giá trị và bất biến.

Ví dụ SQL minh họa có bảng phục hồi đã được tạo và kiểm tra từ trước:

~~~sql
UPDATE customer_record c
SET status = b.previous_status
FROM customer_status_before_image b
WHERE c.id = b.customer_id
  AND c.status = 'SUSPENDED_BY_BAD_RELEASE';
~~~

Đây là cú pháp PostgreSQL và chỉ đúng nếu bảng before-image có dữ liệu chính xác, được liên kết với release gây lỗi, đồng thời điều kiện không chọn nhầm các hàng vốn đã có trạng thái đó. Trong thực tế phải kiểm tra count trước update và sau update, bảo đảm bảng nguồn phục hồi bất biến, và lưu audit. Không dùng literal trạng thái ví dụ cho dữ liệu thật.

## 7. Khi nào cần khôi phục dữ liệu từ backup hoặc PITR?

Restore/PITR thường được cân nhắc khi dữ liệu đã bị:

- Xóa hoặc ghi đè diện rộng mà không có before-image.
- Chuyển đổi sai khiến không thể tái tạo giá trị gốc.
- Hỏng do thao tác DML/DDL gây mất dữ liệu.
- Thay đổi ngoài ý muốn trên nhiều bảng có quan hệ phức tạp.
- Hỏng vật lý/logical corruption hoặc sự cố cần phục hồi tới mốc nhất quán.

**Backup là bản sao dữ liệu; PITR là khả năng phục hồi tới một thời điểm dựa trên backup và log giao dịch** (ví dụ WAL với PostgreSQL, binlog với MySQL, hoặc cơ chế tương đương trên DBMS khác).

### 7.1. Restore toàn database và phục hồi chọn lọc

| Cách | Ý nghĩa | Rủi ro/chi phí |
|---|---|---|
| Full restore | Khôi phục toàn database về backup/mốc thời gian. | Có thể mất mọi thay đổi hợp lệ phát sinh sau mốc; downtime và đồng bộ consumer. |
| PITR sang database mới | Phục hồi một bản sao tới thời điểm trước sự cố để trích xuất hoặc kiểm tra. | Cần thêm dung lượng và bước so sánh/merge dữ liệu. |
| Selective data recovery | Trích một tập bảng/hàng từ bản phục hồi rồi đưa về database hiện tại. | Khó giữ FK, sequence, trigger, thứ tự và tính nhất quán liên bảng. |
| Logical export/import | Xuất dữ liệu/object có phạm vi từ backup hoặc replica. | Cần mapping, encoding, constraint và xử lý xung đột dữ liệu. |
| Compensating migration | Tạo changeset mới để bù dữ liệu sai bằng nguồn đáng tin. | Không khả thi nếu dữ liệu gốc đã mất và không có nguồn khôi phục. |

Restore toàn database thường dễ giữ tính nhất quán nội bộ hơn selective recovery, nhưng có thể làm mất giao dịch hợp lệ sau thời điểm khôi phục. Phục hồi chọn lọc giảm mất dữ liệu mới nhưng phức tạp hơn và cần hiểu quan hệ giữa các bảng.

### 7.2. RPO và RTO

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể chấp nhận mất, thường được biểu diễn bằng khoảng thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Ví dụ, RPO 5 phút nghĩa là tổ chức đặt mục tiêu không mất quá 5 phút dữ liệu; RTO 30 phút nghĩa là đặt mục tiêu khôi phục dịch vụ trong 30 phút. Đây là mục tiêu cần được kiểm chứng bằng diễn tập, không phải bảo đảm tự động từ việc có backup.

PITR chỉ đạt RPO yêu cầu nếu backup, archive log/WAL/binlog và quy trình phục hồi liên tục đầy đủ. RTO phụ thuộc kích thước database, tốc độ restore, bước xác minh và hệ thống phụ thuộc.

### 7.3. Restore có thể tạo ra hai lịch sử khác nhau

Giả sử database được phục hồi về 10:00, trong khi hệ thống đã xử lý đơn hàng tới 10:20. Sau restore:

- Các changeset Liquibase chạy sau 10:00 có thể không còn trong history.
- Schema/data trở về trạng thái cũ.
- Ứng dụng hoặc hệ thống ngoài database có thể vẫn ghi nhận giao dịch tới 10:20.
- Message queue, cache, search index, object storage và dịch vụ thanh toán có thể không tự quay về cùng mốc.

Do đó, restore database không phải thao tác độc lập. Phải lập kế hoạch **reconciliation** cho giao dịch và hệ thống ngoài database, xác định dữ liệu cần replay, loại bỏ hoặc đối soát.

## 8. So sánh rollback, forward fix và restore theo tiêu chí

| Tiêu chí | Rollback | Forward fix | Restore/PITR |
|---|---|---|---|
| Có thể giữ changeset lịch sử? | Có, history được Liquibase cập nhật theo rollback; không sửa file cũ. | Có; thêm changeset mới. | History trở về mốc được khôi phục, có thể mất bản ghi sau mốc. |
| Dữ liệu mới sau deploy | Có nguy cơ bị mất nếu rollback drop/overwrite. | Có thể bảo toàn nếu fix được thiết kế đúng. | Có thể mất dữ liệu sau mốc; cần replay/reconcile. |
| Cần rollback definition? | Thường cần rollback tự động/custom có kiểm chứng. | Không cần đảo changeset cũ, nhưng cần kế hoạch sửa trạng thái. | Cần backup/PITR và quy trình restore DBMS. |
| Phù hợp DML xóa/ghi đè dữ liệu? | Chỉ khi before-image hoặc dữ liệu đảo ngược đầy đủ. | Có nếu xác định được nguồn và điều kiện sửa. | Thường cân nhắc khi mất dữ liệu không thể tái tạo. |
| Phạm vi tác động | Changeset/đối tượng trong phạm vi rollback. | Các đối tượng được fix chỉ định. | Có thể toàn database hoặc tập dữ liệu chọn lọc. |
| Tốc độ | Có thể nhanh nhưng DDL lớn vẫn tốn thời gian. | Tùy fix; có thể chia batch. | Có thể lâu với database lớn. |
| Rủi ro chính | Mất dữ liệu hoặc làm app không tương thích. | Fix không bao phủ trạng thái thật hoặc gây thêm drift. | Mất giao dịch hợp lệ sau mốc và lệch hệ thống ngoài DB. |

## 9. Thiết kế rollback ngay từ lúc viết changeset

Khả năng rollback phải được xem xét trước release, không đợi đến khi sự cố mới tìm cách đảo ngược.

### 9.1. Phân loại changeset theo khả năng đảo ngược

| Loại thay đổi | Khả năng rollback | Thiết kế cần cân nhắc |
|---|---|---|
| Tạo index | Thường có thể drop index. | Đánh giá lock và tác động hiệu năng khi drop. |
| Thêm nullable column | Có thể drop column về mặt schema. | Dữ liệu đã ghi vào cột sẽ mất. |
| Thêm NOT NULL constraint | Có thể bỏ constraint. | Kiểm tra app có phụ thuộc ràng buộc mới không. |
| Rename column | Có thể rename ngược nếu chưa có consumer phụ thuộc tên mới. | Rolling deployment và tương thích phiên bản. |
| Modify data type | Có thể đổi lại nếu dữ liệu phù hợp. | Kiểm tra overflow, truncation, precision và dữ liệu biên. |
| Insert reference data | Có thể delete nếu xác định đúng khóa và không có tham chiếu. | Không xóa giá trị đã được ứng dụng sử dụng. |
| Update dữ liệu nghiệp vụ | Thường khó đảo. | Lưu before-image, audit hoặc mapping giá trị cũ. |
| Delete dữ liệu | Không tự khôi phục được. | Backup, export trước thao tác hoặc soft delete. |
| Drop table/column | Thường không thể khôi phục nội dung chỉ từ changelog. | Backup/PITR hoặc giữ dữ liệu chuyển tiếp. |
| SQL tùy chỉnh | Phụ thuộc logic. | Viết rollback tường minh và thử trên bản sao. |

### 9.2. Ví dụ rollback tùy chỉnh có before-image

Nếu cần update một giá trị nhưng muốn có thể rollback, có thể lưu giá trị cũ vào bảng audit/backup có định danh release trước khi update. Chỉ sau khi lưu thành công mới thực hiện thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-normalize-customer-status
      author: db-team
      changes:
        - sql:
            sql: >
              INSERT INTO customer_status_before_image
                (release_id, customer_id, previous_status)
              SELECT 'release-030', id, status
              FROM customer_record
              WHERE status = 'enabled';
        - sql:
            sql: >
              UPDATE customer_record
              SET status = 'ACTIVE'
              WHERE status = 'enabled';
      rollback:
        - sql:
            sql: >
              UPDATE customer_record c
              SET status = b.previous_status
              FROM customer_status_before_image b
              WHERE b.release_id = 'release-030'
                AND c.id = b.customer_id;
~~~

Đây là ví dụ PostgreSQL. Trên DBMS khác, cú pháp UPDATE FROM có thể khác. Cần có khóa duy nhất/transaction phù hợp để bảo đảm before-image được lưu một lần, không bị trùng khi retry; cần giới hạn đúng release và giữ bảng audit đủ lâu. Rollback này cũng phải cân nhắc việc ứng dụng đã thay đổi status sau migration: ghi đè về giá trị cũ có thể xóa thay đổi hợp lệ phát sinh sau đó.

Một giải pháp thực tế có thể lưu changed_at, version hoặc điều kiện so sánh giá trị hiện tại trước khi khôi phục. Không dùng before-image nếu không thể phân biệt thay đổi của release với cập nhật nghiệp vụ sau release.

### 9.3. Không phải transaction nào cũng đảo được DDL

Một số DBMS hỗ trợ transactional DDL cho nhiều câu lệnh; một số DDL tự commit hoặc có lệnh không thể chạy trong transaction. Ví dụ PostgreSQL có ngoại lệ như `CREATE INDEX CONCURRENTLY`; MySQL có nhiều DDL implicit commit. Behavior thay đổi theo DBMS/version và change type.

Không giả định `runInTransaction=true` biến mọi migration thành atomic. Hãy xem SQL thực tế, DBMS và tài liệu tương ứng. Nếu một changeset có nhiều bước, cân nhắc tách changeset để trạng thái dở dang dễ nhận diện và khắc phục.

## 10. Quy trình thực hiện rollback an toàn

### Bước 1 — Xác định phạm vi và phụ thuộc

Đọc `DATABASECHANGELOG` để xác định changeset đã chạy sau tag hoặc mốc cần quay về. Kiểm tra changeset sau đó có thuộc nhóm khác không, có view/constraint phụ thuộc và có dữ liệu mới sử dụng object không.

### Bước 2 — Kiểm tra rollback definition

Đọc changelog và rollback custom. Xác định change type có rollback tự động không, rollback có xóa dữ liệu không và có SQL native nào cần xử lý riêng không.

### Bước 3 — Sinh SQL preview

Dùng command rollback SQL tương ứng phiên bản Liquibase. Đọc từng câu SQL, kiểm tra schema, filter, context/label và target database.

### Bước 4 — Thử trên bản sao đại diện

Sao chép database hoặc dùng staging có dữ liệu tương đương. Chạy rollback và xác minh:

- Schema/object trước đó đã trở lại.
- Dữ liệu cần giữ vẫn còn.
- Foreign key, index, view, trigger và sequence hoạt động.
- Ứng dụng phiên bản dự kiến có thể chạy.
- Liquibase history phản ánh rollback đúng.

### Bước 5 — Lập cửa sổ triển khai và bảo vệ dữ liệu

Nếu rollback ảnh hưởng DDL lớn hoặc dữ liệu, cần thông báo owner, dừng ghi liên quan, tạo backup/restore point và chuẩn bị lệnh xác minh.

### Bước 6 — Thực hiện và giám sát

Chạy rollback bằng credential phù hợp, theo dõi lock, thời gian, lỗi SQL, replication lag và trạng thái ứng dụng. Nếu rollback lỗi giữa chừng, dừng và kiểm tra schema/history thật trước khi retry.

### Bước 7 — Xác minh hậu điều kiện

Chạy `status`, kiểm tra `DATABASECHANGELOG`, diff schema, truy vấn dữ liệu và smoke test. Lưu log và kết quả vào hồ sơ sự cố.

## 11. Quy trình thiết kế forward fix an toàn

Forward fix là thay đổi mới từ trạng thái hiện tại, vì vậy phải hiểu trạng thái đó trên từng môi trường.

1. Đối chiếu changelog, history và schema thật.
2. Xác định môi trường đã nhận migration lỗi, hotfix hoặc một phần DDL.
3. Viết changeset mới với ID/author/path mới.
4. Dùng precondition để bảo vệ các giả định cần thiết; nếu trạng thái không đúng, ưu tiên HALT để điều tra.
5. Nếu sửa dữ liệu, định lượng tập hàng và lưu nguồn phục hồi trước khi update/delete.
6. Kiểm tra idempotency và behavior khi retry.
7. Test trên database mới, database đã chạy migration cũ và bản sao có trạng thái lỗi đại diện.
8. Chạy `validate`, `status --verbose`, SQL preview và test ứng dụng.
9. Phát hành theo thứ tự tương thích, kiểm tra history/schema/data sau khi chạy.

### 11.1. Precondition cần đủ mạnh

Một precondition `tableExists` chỉ chứng minh bảng có tồn tại. Nó không xác minh kiểu cột, constraint, index hoặc dữ liệu. Nếu forward fix phụ thuộc vào trạng thái cột cụ thể, cần kiểm tra metadata bằng precondition phù hợp hoặc SQL kiểm tra riêng cho DBMS.

Không dùng `MARK_RAN` chỉ để bỏ qua một trạng thái bất ngờ. Khi điều kiện không đạt và nhóm chưa biết nguyên nhân, `HALT` giúp giữ database ở trạng thái có thể điều tra.

### 11.2. Chia backfill lớn thành nhiều bước

Với bảng lớn, một changeset DML duy nhất có thể giữ lock lâu, tạo nhiều WAL/binlog và ảnh hưởng replication. Có thể:

- Thêm cột nullable hoặc cấu trúc mới.
- Backfill theo batch có checkpoint.
- Kiểm tra số hàng đã xử lý và tính đầy đủ.
- Chuyển ứng dụng đọc/ghi sang cấu trúc mới.
- Thêm constraint sau khi dữ liệu đã hợp lệ.
- Loại bỏ cột cũ ở một release sau.

Nếu dùng Liquibase để điều phối, hãy xác định rõ một changeset có thể chạy bao lâu, transaction scope, retry và cách resume. Với backfill dài, một job ứng dụng/worker chuyên biệt có thể phù hợp hơn một migration startup blocking.

## 12. Quy trình restore/PITR an toàn

Restore cần một runbook riêng vì có thể ảnh hưởng toàn bộ database và những hệ thống ghi nhận giao dịch ngoài database.

### Bước 1 — Chọn mốc khôi phục

Xác định thời điểm ngay trước thao tác gây lỗi hoặc một backup đã biết tốt. Kiểm tra backup chain, archive log/WAL/binlog liên tục và khả năng phục hồi đúng mốc.

### Bước 2 — Phục hồi vào môi trường cô lập

Nếu có thể, restore sang database mới hoặc instance riêng trước. Không ghi đè production ngay khi chưa kiểm tra:

- Database mở được và không có corruption.
- Schema và `DATABASECHANGELOG` đúng với thời điểm mốc.
- Dữ liệu bị ảnh hưởng đã trở lại.
- Các bảng liên quan có quan hệ nhất quán.
- Có thể trích xuất dữ liệu cần giữ sau mốc khôi phục.

### Bước 3 — Quyết định full restore hay selective recovery

Full restore phù hợp khi cần tính nhất quán toàn database và chấp nhận mất/replay giao dịch sau mốc. Selective recovery phù hợp khi chỉ một phần dữ liệu bị hỏng và có thể merge an toàn, nhưng phải kiểm tra FK, sequence, trigger, audit và các bảng phụ thuộc.

### Bước 4 — Lập kế hoạch cho giao dịch sau mốc

Đối chiếu nguồn giao dịch khác như payment provider, message broker, event store, file/object storage và log nghiệp vụ. Xác định giao dịch nào cần replay, giao dịch nào cần bỏ, giao dịch nào cần đối soát để không nhân đôi.

### Bước 5 — Đồng bộ ứng dụng và migration

Ứng dụng phải tương thích schema sau restore. Nếu history quay về trước changeset lỗi, pipeline có thể thấy những changeset đó pending. Chỉ chạy lại sau khi xác minh schema/data và chọn phương án rollback hoặc forward fix phù hợp.

### Bước 6 — Chuyển traffic và theo dõi

Thực hiện cutover theo runbook, kiểm tra kết nối, quyền, schema, history, smoke test, hàng đợi và replication. Giám sát lỗi nghiệp vụ và đối soát dữ liệu trong khoảng thời gian sau phục hồi.

## 13. Những điều không nên làm trong sự cố

| Hành động vội vàng | Vì sao nguy hiểm | Cách làm có kiểm soát |
|---|---|---|
| Xóa hàng `DATABASECHANGELOG` để Liquibase chạy lại | History mất liên hệ với schema thật; SQL có thể tạo trùng hoặc phá dữ liệu. | Đối chiếu schema/history và tạo remediation hoặc restore. |
| Sửa changeset đã triển khai | Checksum/history không còn phản ánh nội dung cũ. | Giữ changeset cũ, thêm changeset mới. |
| Dùng `clearCheckSums` để hết lỗi | Không sửa schema/data, có thể che dấu thay đổi changelog. | Điều tra checksum mismatch và chọn fix đúng. |
| Dùng `changelogSync` để bỏ qua changeset lỗi | Ghi nhận changeset như đã chạy mà không thực thi change. | Chỉ sync baseline đã được đối chiếu và phê duyệt. |
| Rollback theo count mà không xem history | Có thể đảo nhầm changeset của nhóm khác hoặc thay đổi phụ thuộc. | Xác định mốc, preview SQL và review phạm vi. |
| Drop cột để rollback ngay | Có thể mất dữ liệu đã được app ghi. | Export/backup, đánh giá consumer và chọn forward fix nếu cần. |
| Restore production trực tiếp khi chưa thử | Có thể mất giao dịch hợp lệ sau mốc hoặc restore sai backup. | Restore thử, đối soát và chuẩn bị cutover. |
| Retry migration lỗi nhiều lần | DDL tự commit có thể để lại object dở dang. | Kiểm tra schema/history trước mỗi lần retry. |
| Chỉ rollback binary ứng dụng | Binary cũ có thể không tương thích schema mới, hoặc ngược lại. | Kiểm tra ma trận tương thích app/schema. |
| Coi backup thành công là restore đã được thử | Backup có thể thiếu log hoặc không phục hồi được. | Diễn tập restore và đo RPO/RTO. |

## 14. Kết hợp rollback với expand–migrate–contract

Đối với thay đổi phá vỡ tương thích, cách tốt nhất để giảm nhu cầu rollback dữ liệu là thiết kế migration theo giai đoạn.

Ví dụ đổi `customer_name` thành `display_name`:

1. **Expand:** thêm `display_name`, giữ `customer_name`.
2. **Deploy tương thích:** ứng dụng đọc cột mới nếu có, vẫn hỗ trợ cột cũ; có thể dual-write tạm thời.
3. **Migrate:** backfill `display_name` từ `customer_name`, kiểm tra count và giá trị.
4. **Switch:** tất cả consumer chuyển sang `display_name`.
5. **Observe:** theo dõi truy vấn, lỗi và job còn đọc cột cũ.
6. **Contract:** xóa `customer_name` bằng changeset mới sau khi xác nhận không còn consumer.

Nếu release ứng dụng mới gặp lỗi ở giai đoạn 2, có thể rollback binary trong khi giữ schema mở rộng. Nếu đã contract và xóa cột cũ, rollback binary cũ có thể không còn khả thi nếu không phục hồi cột/dữ liệu. Vì vậy contract thường được triển khai ở một release sau, sau khi có bằng chứng.

~~~mermaid
flowchart LR
    A[Schema cũ] --> B[Expand: thêm cột mới]
    B --> C[Deploy app tương thích]
    C --> D[Backfill và kiểm chứng]
    D --> E[Chuyển consumer sang cột mới]
    E --> F[Quan sát không còn consumer cũ]
    F --> G[Contract: bỏ cột cũ]
~~~

## 15. Phối hợp quyết định trong incident response

Quyết định xử lý database không nên chỉ do người viết changeset đưa ra trong lúc áp lực cao. Vai trò thường cần có:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Xác định mức độ, ưu tiên, người quyết định và thời điểm cutover. |
| Database owner/DBA | Đánh giá trạng thái DBMS, lock, backup, transaction và restore. |
| Migration owner | Đọc changelog/history, thiết kế rollback hoặc forward fix. |
| Application owner | Xác minh binary, consumer, traffic và tương thích schema. |
| Data/business owner | Xác nhận dữ liệu nào đúng, sai, cần giữ hoặc tái tạo. |
| Platform/SRE | Điều phối pipeline, secret, monitoring và khôi phục hạ tầng. |

Đối với thao tác phá hủy dữ liệu hoặc restore production, cần tuân thủ quy trình phê duyệt sự cố của tổ chức. Ghi rõ ai quyết định, căn cứ, thời điểm, lệnh đã chạy và kết quả.

## 16. Bài thực hành có kiểm chứng

**Bối cảnh:** một release thêm cột `preferred_language` vào bảng khách hàng. Ứng dụng mới đã ghi dữ liệu vào cột này; sau đó phát hiện một lỗi tương thích với client cũ.

### Giai đoạn A — Đánh giá rollback

1. Kiểm tra changeset thêm cột và rollback definition.
2. Xác định số hàng có `preferred_language` khác NULL.
3. Xác định binary/consumer nào đang đọc hoặc ghi cột mới.
4. Sinh rollback SQL và xem có `DROP COLUMN` hay không.
5. Quyết định rollback cột có làm mất dữ liệu không.

### Giai đoạn B — Thiết kế forward fix

1. Tạo changeset mới để điều chỉnh cách ứng dụng sử dụng cột, hoặc thêm compatibility view/logic nếu phù hợp.
2. Giữ nguyên changeset đã triển khai.
3. Viết precondition kiểm tra bảng/cột và trạng thái cần thiết.
4. Kiểm tra dữ liệu và ứng dụng cũ/mới trên bản sao đại diện.
5. Chạy validate, status, SQL preview và update trên môi trường test.

### Giai đoạn C — Mô phỏng sự cố dữ liệu

Trên database lab độc lập:

1. Tạo before-image cho một tập hàng giả lập.
2. Thực hiện một update có lỗi được kiểm soát.
3. So sánh rollback custom với forward correction dùng before-image.
4. Xác minh số hàng trước/sau và không ghi đè cập nhật ngoài phạm vi.
5. Tạo backup rồi thử restore sang database mới.

### Giai đoạn D — Diễn tập restore và reconciliation

1. Ghi nhận một số giao dịch giả lập sau thời điểm backup.
2. PITR bản sao tới mốc trước sự cố nếu DBMS hỗ trợ.
3. Xác định giao dịch sau mốc cần replay hoặc đối soát.
4. Kiểm tra `DATABASECHANGELOG` sau restore.
5. Xác minh schema, dữ liệu, sequence và ứng dụng trước cutover giả lập.

**Tiêu chí đạt:** giải thích được vì sao chọn rollback, forward fix hoặc restore; chứng minh rollback không làm mất dữ liệu cần giữ; viết changeset sửa tiến có điều kiện và kiểm chứng; mô tả được RPO/RTO, reconciliation và các bước xác minh sau phục hồi.

## 17. Checklist quyết định và thực hiện

- [ ] Đã dừng pipeline/retry gây thêm tác động và xác định tiến trình migration còn chạy hay không.
- [ ] Đã xác định database, schema, release, changeset và phạm vi ảnh hưởng.
- [ ] Đã đọc `DATABASECHANGELOG`/lock và kiểm tra schema thật.
- [ ] Đã xác định lỗi thuộc schema, data, performance, compatibility hay migration state.
- [ ] Đã kiểm tra dữ liệu phát sinh sau migration và consumer phụ thuộc.
- [ ] Rollback definition đã được review; rollback SQL đã preview và thử.
- [ ] Forward fix dùng changeset mới, giữ nguyên lịch sử cũ.
- [ ] Data correction có before-image/nguồn phục hồi, điều kiện và hậu kiểm.
- [ ] Restore/PITR có backup chain, log, mốc khôi phục và bản restore thử.
- [ ] Đã đánh giá RPO/RTO và giao dịch cần replay/reconcile.
- [ ] Ứng dụng, database và consumer có thứ tự chuyển đổi tương thích.
- [ ] Đã kiểm tra transaction/implicit commit và DDL không transactional.
- [ ] Có người chịu trách nhiệm, phê duyệt và runbook cho thao tác rủi ro.
- [ ] Sau xử lý đã xác minh schema, dữ liệu, history, ứng dụng và hệ thống ngoài DB.
- [ ] Đã lưu log, quyết định, SQL và kết quả để rút kinh nghiệm.

## 18. Câu hỏi tự kiểm tra

1. Rollback, forward fix và restore/PITR khác nhau ở mục tiêu nào?
2. Vì sao rollback binary ứng dụng không đồng nghĩa rollback database?
3. `rollback-count` có thể đảo nhầm changeset trong trường hợp nào?
4. Tag Liquibase có chứa dữ liệu để phục hồi không?
5. Vì sao rollback `dropColumn` có thể làm mất dữ liệu hợp lệ phát sinh sau deploy?
6. Những loại changeset nào thường không có rollback tự động an toàn?
7. Vì sao DML update/delete cần before-image hoặc nguồn phục hồi?
8. Khi nào nên chọn forward fix dù rollback có thể thực hiện về mặt kỹ thuật?
9. Vì sao `clearCheckSums` và xóa history không phải phương án phục hồi schema?
10. PITR có thể làm mất những giao dịch nào và cần reconciliation với hệ thống nào?
11. RPO và RTO được dùng để quyết định điều gì?
12. Vì sao cần restore thử thay vì chỉ xác nhận backup job thành công?
13. DDL implicit commit ảnh hưởng thế nào tới retry và rollback?
14. Expand–migrate–contract giúp giảm rủi ro rollback ra sao?

## Kết luận

Khi migration gặp sự cố, hãy chọn phương án theo **trạng thái schema, dữ liệu đã phát sinh, mức tương thích ứng dụng và khả năng phục hồi thực tế**. Rollback phù hợp khi thao tác đảo ngược đã được kiểm chứng và không phá dữ liệu mới; forward fix phù hợp khi cần chuyển trạng thái hiện tại bằng changeset mới; restore/PITR phù hợp khi dữ liệu đã hỏng hoặc mất và cần quay về một mốc đáng tin cậy, kèm kế hoạch replay/reconciliation. Liquibase cung cấp history, tag, rollback và cơ chế triển khai, nhưng không thay thế backup, kiểm tra dữ liệu hay quyết định vận hành. Thiết kế rollback từ đầu, giữ changeset lịch sử bất biến và diễn tập restore giúp `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` triển khai an toàn hơn qua nhiều môi trường.
