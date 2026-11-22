# Diễn tập rollback, sửa tiến và khôi phục dữ liệu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thực hành này hướng dẫn diễn tập ba hướng phục hồi sau một lần phát hành database: **rollback changeset**, **forward-fix bằng migration mới** và **khôi phục dữ liệu từ backup/PITR**.

Ba hướng này giải quyết những tình huống khác nhau. Rollback phù hợp khi thay đổi có thể đảo ngược và chưa tạo ra dữ liệu mới cần giữ. Forward-fix phù hợp khi schema đã được ứng dụng sử dụng hoặc cần sửa trạng thái hiện tại bằng một thay đổi tiến mới. Backup/PITR phù hợp khi dữ liệu bị mất hoặc hỏng và không thể tái tạo an toàn bằng migration. Chọn sai hướng có thể làm mất dữ liệu hợp lệ, tạo mismatch giữa DATABASECHANGELOG và schema hoặc kéo dài sự cố.

Bài sử dụng một hệ thống đơn hàng chạy PostgreSQL để minh họa, nhưng nguyên tắc lập kế hoạch, ghi nhận lịch sử, kiểm chứng và bàn giao áp dụng cho các DBMS khác. Các lệnh phục hồi vật lý và PITR phải được điều chỉnh theo phiên bản PostgreSQL hoặc dịch vụ database managed đang vận hành.

## 1. Mục tiêu và phạm vi diễn tập

Sau bài thực hành, người học có thể:

- Xác định trạng thái database và changeset trước khi chọn phương án phục hồi.
- Chuẩn bị một database thử nghiệm có dữ liệu đại diện và release marker.
- Preview, thực thi và xác minh rollback theo tag.
- Giải thích vì sao không sửa changeset đã triển khai để khắc phục lỗi.
- Viết một changeset forward-fix có precondition, hậu điều kiện và rollback phù hợp.
- Diễn tập phục hồi dữ liệu bằng PITR trên một target cô lập.
- Phân biệt restore toàn database với phục hồi chọn lọc một tập bản ghi.
- Đối chiếu DATABASECHANGELOG, schema và dữ liệu sau phục hồi.
- Đo RPO/RTO, lưu bằng chứng và hoàn thiện runbook.

**Chỉ thực hiện các thao tác phá hủy trên database dùng riêng cho diễn tập.** Không chạy lệnh DELETE, DROP, rollback hoặc restore minh họa trên production. Khi áp dụng vào môi trường thật, phải dùng quy trình change approval, backup, maintenance window và quyền vận hành đã được phê duyệt.

## 2. Kịch bản xuyên suốt

Giả sử dịch vụ Commerce có bảng orders. Release 1.0 lưu mã đơn, trạng thái, tổng tiền và thời điểm tạo. Release 1.1 thêm bảng audit để lưu lịch sử trạng thái. Release 1.2 thêm một default cho status. Sau phát hành, nhóm phát hiện default được chọn không phù hợp với quy tắc nghiệp vụ. Đồng thời, trong một diễn tập riêng, một câu lệnh DELETE nhầm làm mất các đơn hàng cũ.

Ta sẽ xử lý ba tình huống độc lập:

| Tình huống | Vấn đề | Hướng diễn tập |
|---|---|---|
| A. Release 1.1 tạo bảng audit nhưng cần hủy trước khi ứng dụng sử dụng | Thay đổi DDL có rollback rõ ràng | Rollback theo tag |
| B. Release 1.2 đặt default sai, nhưng ứng dụng đã ghi dữ liệu mới | Không thể xóa thay đổi cũ mà không ảnh hưởng dữ liệu | Forward-fix bằng changeset mới |
| C. Một thao tác xóa nhầm làm mất dữ liệu orders | Cần khôi phục các hàng đã mất | PITR hoặc restore từ backup vào môi trường cô lập |

Không gộp ba tình huống vào một lần thực thi. Mỗi tình huống có checkpoint, bằng chứng và điều kiện hoàn tất riêng.

## 3. Quyết định rollback, forward-fix hay restore

Trước khi chạy lệnh phục hồi, trả lời bốn câu hỏi:

1. **Database đã thay đổi đến đâu?** Changeset đã chạy hết, một phần hay chưa bắt đầu?
2. **Có dữ liệu mới phát sinh sau thay đổi không?** Ứng dụng đã ghi hoặc đọc dữ liệu từ cấu trúc mới chưa?
3. **Thay đổi có đảo ngược an toàn không?** Rollback có làm mất dữ liệu, phá constraint hoặc khiến code hiện tại không tương thích không?
4. **Mục tiêu phục hồi là gì?** Trả schema về trạng thái trước release, sửa trạng thái hiện tại, hay khôi phục dữ liệu bị mất?

| Phương án | Dùng khi | Rủi ro chính |
|---|---|---|
| **Rollback Liquibase** | Changeset có rollback được kiểm thử, thay đổi chưa được phụ thuộc hoặc dữ liệu mới có thể bỏ | Mất object/dữ liệu mới; rollback không hoàn tác side effect bên ngoài |
| **Forward-fix** | Schema mới đã được sử dụng, rollback nguy hiểm hoặc cần sửa trạng thái hiện tại | Cần thiết kế migration mới và kiểm soát tương thích |
| **Restore/PITR** | Dữ liệu hoặc cấu trúc bị mất/hỏng, không thể tái tạo đáng tin cậy | Có thể mất giao dịch sau thời điểm phục hồi; cần reconcile ứng dụng và lịch sử |
| **Selective recovery** | Chỉ một nhóm bản ghi bị mất và cần giữ các giao dịch mới hơn | Xung đột khóa, quan hệ, sequence, dữ liệu đã thay đổi sau mốc |

Không chọn rollback chỉ vì pipeline báo lỗi. Một changeset có thể đã commit DDL trước khi process thất bại. Cũng không chọn restore toàn database khi chỉ cần khôi phục một nhóm bản ghi và các giao dịch hợp lệ sau đó phải được giữ lại.

## 4. Các bất biến cần giữ trong mọi phương án

Một lần phục hồi an toàn cần duy trì những nguyên tắc sau:

- Chỉ một migration owner thực hiện thao tác thay đổi trên cùng database tại một thời điểm.
- Ghi nhận release ID, target database, schema, DBMS/version và commit changelog.
- Không sửa nội dung changeset đã được triển khai để che lỗi.
- Không sửa tay DATABASECHANGELOG hoặc checksum để làm trạng thái trông như thành công.
- Trước retry, đối chiếu lịch sử Liquibase với schema và dữ liệu thực tế.
- Backup/PITR phải được kiểm chứng khả năng restore.
- Phục hồi vào môi trường cô lập trước khi cutover hoặc chép dữ liệu trở lại.
- Kiểm tra ứng dụng, consumer, job nền và replication sau phục hồi.
- Ghi lại người phê duyệt, người thực hiện, thời điểm và kết quả.

**DATABASECHANGELOG là lịch sử Liquibase, không phải bản backup schema/data.** Nếu database được restore tới thời điểm trước một changeset, lịch sử trong DATABASECHANGELOG của bản restore phải phản ánh đúng thời điểm đó. Không tự thêm hoặc xóa bản ghi lịch sử bằng SQL để ép nó khớp với một release khác.

## 5. Chuẩn bị database dùng riêng cho diễn tập

Dựng một database PostgreSQL không chứa dữ liệu thật. Ví dụ cấu trúc tối thiểu:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_no VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO orders(order_no, status, total_amount, created_at)
VALUES
    ('ORD-1001', 'PENDING', 125000.00, '2026-10-01 09:00:00'),
    ('ORD-1002', 'PAID',    250000.00, '2026-10-02 10:00:00'),
    ('ORD-1003', 'CANCELLED', 75000.00, '2026-10-03 11:00:00');
~~~

Trong bài thực hành, dữ liệu mẫu nhỏ giúp đọc kết quả dễ dàng. Khi diễn tập PITR, tạo thêm nhiều bản ghi và giao dịch theo các thời điểm khác nhau để mô phỏng workload.

Ghi nhận trạng thái ban đầu:

~~~sql
SELECT COUNT(*) AS order_count,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM orders;

SELECT id, order_no, status, total_amount, created_at
FROM orders
ORDER BY id;
~~~

Lưu ý các giá trị kết quả vào release record hoặc biên bản diễn tập. Đây là baseline để so sánh sau mỗi bước.

Nếu database được Liquibase quản lý, tạo changelog baseline tương ứng hoặc dùng database test đã được khởi tạo qua changelog. Không tạo bảng thủ công rồi giả định Liquibase đã biết changeset nào tạo ra chúng. Khi baseline bằng tay cho bài tập, ghi rõ đó là fixture test và chỉ bắt đầu diễn tập từ release marker đã được thiết lập.

## 6. Thiết lập changelog và release marker

Ví dụ cấu trúc file:

~~~text
db/changelog/
  db.changelog-master.yaml
  changes/
    001-create-orders.yaml
    010-create-order-status-history.yaml
    020-set-order-status-default.yaml
    021-fix-order-status-default.yaml
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/010-create-order-status-history.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/020-set-order-status-default.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/021-fix-order-status-default.yaml
      relativeToChangelogFile: true
~~~

Trong thực tế, chỉ include changeset thuộc release được phát hành. Ví dụ khi diễn tập tình huống A, có thể dùng một master changelog riêng cho nhánh thử nghiệm hoặc tag release tại trạng thái sau baseline. Không thay đổi master changelog production để phục vụ bài tập.

Sau khi baseline đã được áp dụng và xác minh, tạo release marker:

~~~shell
liquibase tag release_1_0_baseline
~~~

Tag giúp xác định mốc lịch sử để rollback. Cú pháp CLI cần xác minh theo phiên bản Liquibase đang dùng. Ghi lại tag, thời điểm, commit và target database.

Một tag không thay thế backup. Tag đánh dấu vị trí trong lịch sử Liquibase; backup/PITR lưu khả năng phục hồi dữ liệu và trạng thái vật lý theo cơ chế DBMS.

## 7. Kiểm tra trước mỗi lần diễn tập

Trước khi thực thi bất kỳ phương án nào:

~~~shell
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Các lệnh preview phải dùng đúng changelog, URL, schema, contexts và labels như lệnh sẽ chạy. Cú pháp tham số có thể khác theo phiên bản CLI.

Xác nhận target PostgreSQL:

~~~sql
SELECT current_database(),
       current_schema(),
       current_user,
       current_setting('server_version');
~~~

Kiểm tra lịch sử:

~~~sql
SELECT id, author, filename, exectype, md5sum,
       dateexecuted, orderexecuted, tag
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Kiểm tra lock:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM public.databasechangeloglock;
~~~

Tên schema metadata có thể khác cấu hình thực tế. Không mặc định DATABASECHANGELOG luôn nằm trong public.

Nếu có checksum mismatch, lock đang được giữ hoặc trạng thái schema không khớp release marker, dừng diễn tập và làm rõ nguyên nhân trước khi chạy rollback/update.

## 8. Tình huống A: tạo thay đổi có rollback rõ ràng

Release 1.1 thêm bảng order_status_history để lưu trạng thái thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-order-status-history
      author: commerce-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
      changes:
        - createTable:
            tableName: order_status_history
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: previous_status
                  type: VARCHAR(20)
              - column:
                  name: new_status
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
              - column:
                  name: changed_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
              - column:
                  name: changed_by
                  type: VARCHAR(100)
                  constraints:
                    nullable: false

        - addForeignKeyConstraint:
            baseTableName: order_status_history
            baseColumnNames: order_id
            constraintName: fk_order_status_history_order
            referencedTableName: orders
            referencedColumnNames: id

        - createIndex:
            tableName: order_status_history
            indexName: idx_order_status_history_order_time
            columns:
              - column:
                  name: order_id
              - column:
                  name: changed_at

      rollback:
        - dropTable:
            tableName: order_status_history
~~~

Ví dụ trên cho thấy changeset có rollback được khai báo tường minh. Liquibase có thể tự sinh rollback cho một số change type, nhưng với thay đổi quan trọng nên review SQL rollback thực tế và thử trên database dùng riêng.

Nếu ứng dụng đã ghi dữ liệu audit vào bảng, rollback dropTable sẽ xóa toàn bộ lịch sử đó. Do vậy tình huống A chỉ diễn tập khi bảng chưa được ứng dụng sử dụng hoặc dữ liệu mới có thể bỏ theo quyết định rõ ràng.

### Thực thi và xác minh

~~~shell
liquibase update-sql
liquibase update
~~~

Sau update, kiểm tra bảng, FK, index và DATABASECHANGELOG. Ghi nhận changeset 010 đã được thực thi và dữ liệu bảng audit hiện có.

Tạo một tag mới sau khi release 1.1 đã được nghiệm thu nếu cần dùng làm mốc cho release tiếp theo. Trong bài tập, để rollback về baseline, sử dụng tag release_1_0_baseline đã được tạo trước khi chạy changeset 010.

## 9. Preview rollback trước khi thực thi

Không chạy rollback trực tiếp khi chưa xem SQL. Ví dụ:

~~~shell
liquibase rollback-sql --tag=release_1_0_baseline
~~~

Lệnh preview giúp review các thao tác Liquibase dự kiến thực hiện để quay về tag. Kiểm tra:

- Changeset nào sẽ được rollback?
- Có DROP TABLE, DROP INDEX hoặc thao tác xóa dữ liệu không?
- Có changeset nào sau tag không thuộc phạm vi mong muốn?
- Có thay đổi nào không có rollback được khai báo?
- Ứng dụng đã bắt đầu phụ thuộc vào bảng/cột mới chưa?
- Dữ liệu được tạo sau release có cần giữ không?

Nếu SQL preview khác kế hoạch, không thực thi. Xác định đúng tag và target, kiểm tra lịch sử và chạy lại preview.

Rollback theo tag có thể đảo mọi changeset sau tag trong phạm vi changelog đã áp dụng. Vì vậy, tag phải được đặt ở mốc có ý nghĩa và phạm vi rollback cần được hiểu chính xác.

## 10. Thực thi rollback và postflight

Chỉ trên database diễn tập, sau khi preview được review:

~~~shell
liquibase rollback --tag=release_1_0_baseline
~~~

Sau đó kiểm tra:

~~~sql
SELECT to_regclass('public.order_status_history') AS history_table;

SELECT id, author, filename, exectype, md5sum, dateexecuted, tag
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Kỳ vọng:

- Bảng order_status_history không còn.
- FK và index thuộc bảng đó cũng không còn.
- Changeset sau tag đã được rollback theo lịch sử Liquibase.
- Changeset baseline trước tag vẫn được ghi nhận.
- Các bảng orders và dữ liệu baseline còn nguyên.

Với rollback thành công, Liquibase cập nhật lịch sử để phản ánh changeset đã được rollback theo cơ chế của nó. Không tự xóa dòng DATABASECHANGELOG bằng SQL.

### Nếu rollback thất bại giữa chừng

Không giả định toàn bộ rollback được hoàn tác. DDL semantics phụ thuộc DBMS và changeset có thể chứa thao tác non-transactional. Kiểm tra:

1. Log và statement cuối cùng.
2. Session database còn chạy không.
3. Object nào đã bị xóa hoặc còn tồn tại.
4. DATABASECHANGELOG ghi nhận trạng thái nào.
5. Có dữ liệu nào bị mất không.
6. Có thể tiếp tục rollback hay cần forward-fix/reconcile.

Không chạy rollback lần nữa chỉ vì job trước có exit code khác 0. Trước tiên phải xác định trạng thái thực tế.

## 11. Tình huống B: thay đổi đã phát hành nhưng cần sửa tiến

Giả sử release 1.2 đã đặt default status sai thành NEW, trong khi quy tắc đúng là PENDING.

Changeset đã triển khai:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-set-order-status-default
      author: commerce-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              ALTER TABLE public.orders
              ALTER COLUMN status SET DEFAULT 'NEW';
      rollback:
        - sql:
            sql: |
              ALTER TABLE public.orders
              ALTER COLUMN status DROP DEFAULT;
~~~

Sau khi release chạy, ứng dụng đã tạo nhiều đơn hàng dùng default NEW. Việc rollback changeset 020 chỉ DROP DEFAULT không sửa giá trị của các đơn hàng đã được ghi. Nếu rollback còn xóa cột hoặc thay đổi cấu trúc mà code đang dùng, rủi ro sẽ lớn hơn.

Cách phù hợp trong tình huống này là **forward-fix**: giữ nguyên changeset 020 và thêm changeset 021 sửa default về PENDING.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 021-fix-order-status-default
      author: commerce-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: status
      changes:
        - sql:
            sql: |
              ALTER TABLE public.orders
              ALTER COLUMN status SET DEFAULT 'PENDING';
      rollback:
        - sql:
            sql: |
              ALTER TABLE public.orders
              ALTER COLUMN status SET DEFAULT 'NEW';
~~~

Changeset mới biểu diễn trạng thái mong muốn từ thời điểm sửa lỗi. Nó không viết lại lịch sử cũ.

### Xác minh forward-fix

Kiểm tra default:

~~~sql
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'status';
~~~

Kỳ vọng default là PENDING. Tiếp theo, kiểm tra các hàng đã bị ảnh hưởng bởi default cũ. Không tự động đổi mọi status NEW thành PENDING vì NEW có thể là giá trị hợp lệ được ứng dụng ghi tường minh.

Nếu cần sửa dữ liệu đã ghi, phải có tiêu chí nhận diện chính xác, chẳng hạn một khoảng thời gian release, source version hoặc audit record. Hãy xác minh với nghiệp vụ trước khi chạy UPDATE. Thay đổi default chỉ tác động các INSERT sau đó; nó không sửa các hàng hiện có.

## 12. Forward-fix cho dữ liệu đã bị chuyển đổi sai

Giả sử một backfill cũ đã gán status PENDING cho các đơn hàng có paid_at khác NULL. Theo quy tắc nghiệp vụ của bài tập, các đơn hàng có paid_at khác NULL phải là PAID. Nếu nguồn paid_at đáng tin cậy và không có ngoại lệ, changeset mới có thể sửa những hàng còn sai:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 022-correct-paid-order-status
      author: commerce-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: paid_at
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: status
      changes:
        - sql:
            sql: |
              UPDATE public.orders
              SET status = 'PAID'
              WHERE paid_at IS NOT NULL
                AND status = 'PENDING';
~~~

Đây chỉ là ví dụ nếu quy tắc nghiệp vụ thực sự bảo đảm paid_at là nguồn sự thật. Trong hệ thống có thanh toán đang xử lý, hoàn tiền hoặc capture bất đồng bộ, không dùng phép suy luận này nếu không đúng.

Với dữ liệu lớn, không chạy một UPDATE dài mà không đánh giá WAL, lock và replication lag. Dùng batch/checkpoint hoặc job dữ liệu có kiểm soát. Trước khi sửa, lưu số lượng và danh sách định danh bản ghi bị ảnh hưởng theo chính sách bảo mật.

### Vì sao không sửa changeset backfill cũ?

Nếu changeset cũ đã chạy ở production, sửa SQL của nó sẽ làm checksum khác với DATABASECHANGELOG. Môi trường đã chạy và môi trường mới có thể xử lý khác nhau. Tạo changeset 022 giữ lịch sử minh bạch: 011 đã thực hiện backfill ban đầu; 022 sửa lỗi được phát hiện sau đó.

Không dùng clear-checksums hoặc validCheckSum chỉ để bỏ qua sai khác chưa hiểu. Các công cụ checksum cần quyết định riêng, có review và bằng chứng.

## 13. Tình huống C: diễn tập xóa nhầm dữ liệu

Giả sử một câu lệnh vận hành bị viết sai:

~~~sql
DELETE FROM public.orders
WHERE created_at < TIMESTAMP '2026-10-01 00:00:00';
~~~

Trong bài tập, chạy câu lệnh này chỉ trên database disposable đã có backup/PITR được cấu hình. Không chạy trên môi trường thật.

Ngay sau khi xóa, ghi lại:

- Thời điểm thực hiện và timezone.
- Người/job thực hiện.
- SQL và điều kiện lọc.
- Số hàng bị xóa nếu có log/row count.
- Database/schema bị ảnh hưởng.
- Các giao dịch hợp lệ phát sinh sau thời điểm xóa.
- Release ID và trạng thái Liquibase hiện tại.

Không tiếp tục chạy migration hoặc job ghi dữ liệu trên database diễn tập cho đến khi đã chọn phương án phục hồi. Với sự cố thật, cân nhắc write freeze hoặc chuyển traffic theo quy trình incident để giới hạn thay đổi tiếp theo.

### Kiểm tra mức độ mất dữ liệu

Nếu còn nguồn audit, CDC, event log hoặc bản sao đọc, dùng chúng để xác định tập bản ghi bị xóa. Đừng chỉ dựa vào COUNT(*) hiện tại vì không biết số hàng ban đầu.

Ví dụ so sánh baseline đã ghi nhận:

~~~text
Baseline trước sự cố: 3.000.000 orders
Sau thao tác xóa:      2.100.000 orders
Chênh lệch:              900.000 orders
~~~

Các con số chỉ minh họa. Trong hệ thống thật, cần dùng bằng chứng từ backup, audit hoặc thống kê đáng tin cậy để xác định số hàng và phạm vi bị mất.

## 14. Chuẩn bị và xác minh backup/PITR

Khả năng PITR phụ thuộc cấu hình DBMS và dịch vụ managed database. Với PostgreSQL, phục hồi tới thời điểm yêu cầu thường cần base backup phù hợp và WAL archive liên tục đến mốc đích. Với dịch vụ managed, dùng chức năng point-in-time restore theo hướng dẫn của nhà cung cấp.

Trước khi diễn tập, xác nhận:

- Có backup nền đủ mới.
- WAL/archive hoặc transaction log được lưu liên tục.
- Thời gian retention bao phủ mốc cần phục hồi.
- Có quyền tạo instance/cluster phục hồi.
- Có đủ dung lượng và quota.
- Có network/security group phù hợp.
- Biết timezone và độ chính xác của target time.
- Có thể khởi chạy database phục hồi trong môi trường cô lập.
- Có quy trình kiểm tra dữ liệu trước khi cutover hoặc trích xuất.

**Backup job thành công không chứng minh restore thành công.** Hãy diễn tập restore định kỳ và ghi lại thời gian thực tế, lỗi, dung lượng, bước thủ công và kết quả kiểm tra.

### Chọn target time

Để phục hồi dữ liệu bị xóa, target time phải nằm ngay trước giao dịch DELETE gây sự cố. Chọn mốc quá sớm có thể loại bỏ nhiều giao dịch hợp lệ hơn; chọn mốc quá muộn có thể bao gồm thao tác xóa.

Ghi rõ:

- Thời điểm sự cố theo UTC.
- Target time đã chọn.
- Vì sao mốc này nằm trước thao tác gây lỗi.
- Giao dịch nào sẽ bị loại khỏi bản restore.
- Ai phê duyệt RPO và phạm vi mất dữ liệu có thể chấp nhận.

## 15. Restore vào môi trường cô lập trước

Không restore trực tiếp đè lên database đang phục vụ chỉ để kiểm tra. Tạo một instance/database phục hồi riêng, ví dụ:

~~~text
commerce-prod
    |
    +-- backup/WAL archive
              |
              v
       PITR target: trước DELETE
              |
              v
       commerce-restore-drill
              |
              +-- validate schema
              +-- validate DATABASECHANGELOG
              +-- compare orders
              +-- extract missing rows
~~~

Với PostgreSQL tự quản lý, quy trình vật lý có thể bao gồm restore base backup, cấu hình WAL archive/recovery target và promote instance sau khi recovery đạt mốc. Cú pháp file cấu hình và quy trình khởi động phụ thuộc PostgreSQL version và cách quản lý cluster. Với managed database, dùng chức năng PITR được cung cấp để tạo instance mới tại target time.

Sau khi instance phục hồi sẵn sàng:

1. Xác nhận database name, server identity và target time.
2. Xác nhận ứng dụng không ghi vào instance phục hồi.
3. Kiểm tra bảng orders, số hàng và bản ghi đại diện.
4. Kiểm tra DATABASECHANGELOG có trạng thái tương ứng với thời điểm restore.
5. Kiểm tra foreign key, index, sequence/identity và dữ liệu liên quan.
6. Lưu log restore và thời gian hoàn thành.

Không trỏ ứng dụng production vào instance phục hồi cho đến khi có quyết định cutover được phê duyệt.

## 16. Phục hồi toàn database hay chỉ khôi phục dữ liệu?

Có hai chiến lược chính:

### A. Restore toàn database và cutover

Phù hợp khi:

- Mất dữ liệu trên diện rộng.
- Các giao dịch sau target time có thể bỏ hoặc được tái tạo.
- Database có thể chuyển sang trạng thái nhất quán tại mốc phục hồi.
- Ứng dụng và consumer có kế hoạch chuyển endpoint.

Các bước:

1. Dừng hoặc điều phối writer.
2. Restore database tới target time trên instance mới.
3. Kiểm tra schema, data và DATABASECHANGELOG.
4. Đối chiếu các giao dịch sau target time cần replay.
5. Phê duyệt cutover.
6. Chuyển traffic và theo dõi.
7. Giữ instance cũ theo chính sách điều tra/retention.

Nhược điểm là giao dịch hợp lệ sau target time có thể bị mất nếu không replay. Phải đánh giá RPO và nghiệp vụ trước khi chọn.

### B. Restore cô lập và phục hồi chọn lọc

Phù hợp khi chỉ một nhóm bản ghi bị xóa nhưng các giao dịch mới hơn phải được giữ.

Quy trình:

1. PITR toàn database sang instance cô lập.
2. Xác định bản ghi có ở instance phục hồi nhưng thiếu ở production.
3. Xác minh các bản ghi đó chưa được tạo lại hoặc thay đổi hợp lệ sau sự cố.
4. Kiểm tra khóa chính, khóa ngoại và dependency.
5. Trích xuất tập dữ liệu cần khôi phục.
6. Nạp lại theo batch có idempotency và audit.
7. Kiểm tra sequence/identity sau khi nạp.
8. Chạy data assertions và smoke test.

Không copy nguyên DATABASECHANGELOG từ instance PITR sang production khi chỉ phục hồi một số hàng. Production có thể đã chạy các changeset khác sau mốc PITR; ghi đè lịch sử sẽ làm mất dấu các migration hợp lệ. Chỉ phục hồi dữ liệu nghiệp vụ được chọn và giữ lịch sử Liquibase của target hiện tại.

## 17. Reconcile DATABASECHANGELOG sau restore

Đây là bước rất quan trọng. Sau restore, schema, dữ liệu và lịch sử phải mô tả cùng một trạng thái.

### Restore toàn database tới một thời điểm

Nếu PITR phục hồi toàn bộ database nhất quán, DATABASECHANGELOG cũng được phục hồi tới cùng thời điểm. Khi đó:

- Changeset đã chạy trước target time vẫn có bản ghi.
- Changeset chạy sau target time có thể không còn bản ghi.
- Schema phản ánh trạng thái tại target time.
- Các release sau target time cần được đánh giá và triển khai/replay theo kế hoạch.

Không chạy Liquibase update ngay sau restore nếu chưa xác định changelog release tương ứng với mốc phục hồi.

### Phục hồi chọn lọc dữ liệu

Nếu chỉ chép lại một số hàng từ instance PITR:

- Không thay DATABASECHANGELOG của production.
- Không xóa changeset record để ép Liquibase chạy lại.
- Giữ schema hiện tại và kiểm tra dữ liệu được phục hồi tương thích với schema đó.
- Đảm bảo các cột mới, constraint và default trên production được đáp ứng.
- Cập nhật sequence/identity nếu dữ liệu được nạp có ID lớn hơn giá trị hiện tại.

Nếu schema đã tiến xa hơn bản restore, dữ liệu cũ cần được transform trước khi nạp. Viết script/job phục hồi riêng, có review và log; không coi bản ghi từ PITR tự động tương thích với schema hiện tại.

### Kiểm tra lịch sử

~~~sql
SELECT id, author, filename, exectype, md5sum,
       dateexecuted, orderexecuted, tag
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Đối chiếu với release manifest và changelog commit. Nếu history và schema không khớp, dừng và điều tra. Không sửa trực tiếp DATABASECHANGELOG để tạo trạng thái mong muốn.

## 18. Xử lý sequence, khóa ngoại và dữ liệu phụ thuộc

Phục hồi dữ liệu chọn lọc có thể tạo vấn đề ngoài bảng chính:

- Sequence/identity có thể chưa vượt qua ID vừa được nạp.
- Bản ghi con có thể thiếu bản ghi cha.
- Unique constraint có thể xung đột với bản ghi được tạo sau sự cố.
- Trigger có thể tạo side effect khi INSERT lại.
- Audit/outbox có thể ghi sự kiện trùng.
- CDC/downstream consumer có thể xử lý lại dữ liệu.
- Cache hoặc search index có thể vẫn giữ trạng thái cũ.

Với PostgreSQL, sequence cần được kiểm tra theo đúng sequence gắn với cột và cách cấp ID. Không gọi nextval chỉ để thử vì nó tiêu thụ giá trị. Việc setval phải dựa trên trạng thái dữ liệu và chính sách cấp ID, đặc biệt khi có writer đồng thời.

Với foreign key, phục hồi theo thứ tự cha trước con hoặc dùng quy trình được DBMS hỗ trợ. Không tắt constraint một cách tùy tiện; nếu phải tạm hoãn validation, cần có postflight chứng minh không có orphan.

## 19. Đo RPO và RTO trong diễn tập

Hai chỉ số phục hồi cần ghi lại:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường được biểu diễn bằng thời gian giữa thời điểm sự cố và mốc dữ liệu phục hồi.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ về mức chấp nhận được.

Ví dụ:

~~~text
Incident detected:       10:15 UTC
Accidental DELETE:       10:12 UTC
PITR target:             10:11 UTC
Restore ready:           10:42 UTC
Validation complete:     10:55 UTC
Service restored:        11:05 UTC
Observed data point:     10:11 UTC
~~~

Ví dụ này cho thấy RPO thực tế và RTO thực tế phải tính theo mốc dữ liệu và thời điểm dịch vụ hoạt động lại, không chỉ thời gian database restore xong.

Ghi nhận:

- Thời gian phát hiện.
- Thời điểm sự cố.
- Target time.
- Thời gian bắt đầu restore.
- Thời gian database phục hồi sẵn sàng.
- Thời gian validation.
- Thời gian cutover hoặc selective recovery hoàn tất.
- Thời điểm smoke test đạt.
- RPO/RTO thực tế và mục tiêu.

Nếu diễn tập vượt RTO, ghi nguyên nhân: backup lớn, thiếu quota, restore chậm, thiếu quyền, bước thủ công, validation lâu hoặc cutover chưa tự động. Chuyển kết quả thành công việc cải tiến có owner.

## 20. Phối hợp rollback với phiên bản ứng dụng

Database rollback có thể khiến code đang chạy không còn tương thích. Ví dụ:

- Ứng dụng mới truy vấn cột status_history vừa bị rollback.
- Code đã ghi dữ liệu vào cột mới, rollback drop cột làm mất dữ liệu.
- Ứng dụng cũ không hiểu enum status mới.
- Một batch job đã tạo tham chiếu đến bảng mới.

Trước rollback, cần quyết định thứ tự giữa application và database:

| Tình huống | Hướng phối hợp |
|---|---|
| Schema mới chưa được code sử dụng | Có thể rollback schema sau khi xác minh |
| Code mới đang dùng object mới | Rollback code trước hoặc giữ schema tương thích |
| Dữ liệu mới đã được ghi | Đánh giá giữ schema/forward-fix; tránh drop mất dữ liệu |
| Thay đổi destructive đã xảy ra | Restore/PITR hoặc phục hồi chọn lọc |
| Rolling deployment còn instance cũ | Giữ schema tương thích cả code cũ và mới |

Mẫu expand–migrate–contract giúp giảm rủi ro: thêm cấu trúc mới, deploy code tương thích, chuyển dữ liệu, chuyển consumer, rồi mới loại bỏ cấu trúc cũ trong release sau.

## 21. Tích hợp rollback và recovery vào CI/CD

Pipeline không nên tự động chạy rollback chỉ vì update job trả mã lỗi. Thay vào đó, chuyển sang trạng thái cần đánh giá:

~~~text
Liquibase update
      |
      +-- success --> postflight
      |
      +-- failure --> stop next rollout
                         |
                         v
                  inspect session/log
                         |
                         v
                  reconcile DBCL/schema/data
                         |
              +----------+----------+
              |                     |
              v                     v
         reversible             data loss /
         and safe               uncertain state
              |                     |
              v                     v
        preview rollback       restore/PITR or
        approval               forward-fix decision
              |                     |
              v                     v
        execute rollback       isolated recovery
              |                     |
              +----------+----------+
                         |
                         v
                    postflight
                         |
                         v
                  record decision
~~~

Các gate cần có:

- Migration owner duy nhất.
- Target identity xác nhận.
- Backup/PITR sẵn sàng trước thay đổi có rủi ro.
- Rollback SQL preview hoặc forward-fix review.
- Approval cho thao tác destructive/restore.
- Không retry trước reconcile.
- Postflight schema/data/history/application.
- Evidence và incident record.

Spring Boot production nên có một migration owner rõ ràng: job CI/CD hoặc một startup owner được điều phối. Không để nhiều replica tự chạy update trong lúc một job recovery đang thực hiện.

## 22. Runbook diễn tập đầy đủ

Có thể tổ chức một buổi diễn tập theo thứ tự:

### Phần A — Baseline và rollback

1. Tạo database dùng riêng.
2. Áp dụng baseline changelog.
3. Nạp dữ liệu mẫu và lưu số lượng.
4. Tạo tag release_1_0_baseline.
5. Áp dụng changeset tạo order_status_history.
6. Xác minh bảng, FK, index và DATABASECHANGELOG.
7. Chạy rollback-sql theo tag.
8. Review SQL rollback.
9. Chạy rollback.
10. Xác minh bảng bị xóa, dữ liệu orders còn nguyên và lịch sử phản ánh rollback.

### Phần B — Forward-fix

1. Áp dụng changeset đặt default status sai trong database test.
2. Tạo một số đơn hàng sử dụng default.
3. Xác nhận default và dữ liệu hiện tại.
4. Tạo changeset mới sửa default.
5. Không sửa changeset cũ.
6. Chạy validate, update-sql và review.
7. Chạy update.
8. Xác minh default mới.
9. Phân loại các hàng đã được ghi bằng default cũ; chỉ sửa khi có tiêu chí nhận diện và nguồn sự thật.
10. Xác minh checksum/history của cả changeset cũ và mới.

### Phần C — PITR và selective recovery

1. Bật backup/WAL archive hoặc dùng dịch vụ managed hỗ trợ PITR trên database diễn tập.
2. Tạo dữ liệu orders ở nhiều thời điểm.
3. Ghi mốc thời gian và số lượng baseline.
4. Thực hiện DELETE sai trên database diễn tập.
5. Ghi nhận thời điểm sự cố.
6. Restore tới thời điểm trước DELETE vào instance cô lập.
7. Xác minh schema, dữ liệu và DATABASECHANGELOG của instance phục hồi.
8. So sánh bản ghi bị mất với target hiện tại.
9. Chọn full restore/cutover hoặc selective recovery.
10. Nếu selective, nạp dữ liệu theo batch, xử lý khóa/sequence/dependency.
11. Chạy data assertions, smoke test và kiểm tra downstream.
12. Ghi RPO/RTO và bài học.

### Phần D — Đóng diễn tập

- Thu thập log, SQL preview, approval và query results.
- Ghi quyết định rollback/forward-fix/restore.
- Ghi target database và release ID.
- Ghi trạng thái DATABASECHANGELOG trước/sau.
- Xác nhận không còn lock hoặc session phục hồi.
- Cập nhật runbook và owner follow-up.
- Xóa database diễn tập theo chính sách sau khi lưu evidence cần thiết.

## 23. Mẫu biên bản phục hồi

~~~text
INCIDENT / DRILL:
  id:
  environment:
  severity_or_exercise:
  detected_at_utc:
  occurred_at_utc:

TARGET:
  database_identity:
  schema:
  dbms_version:
  liquibase_version:
  application_release:

LIQUIBASE_STATE:
  last_changeset:
  databasechangelog_status:
  checksum_findings:
  databasechangeloglock_state:

IMPACT:
  affected_tables:
  affected_rows:
  affected_tenants:
  downstream_systems:

DECISION:
  rollback / forward_fix / full_restore / selective_recovery
  rationale:
  approver:
  owner:

RECOVERY:
  backup_reference:
  pitr_target_time:
  restore_target:
  start_time:
  ready_time:
  validation_time:
  service_restored_time:

VALIDATION:
  schema:
  data_assertions:
  databasechangelog:
  application_smoke:
  replication_and_consumers:

OBJECTIVES:
  rpo_target:
  rpo_actual:
  rto_target:
  rto_actual:

HANDOFF:
  runbook:
  evidence:
  open_items:
  owner:
  due_date:
~~~

Không đưa password, token, dữ liệu khách hàng hoặc connection string chứa secret vào biên bản. Dùng tham chiếu tới hệ thống lưu trữ có phân quyền.

## 24. Những lỗi thường gặp khi phục hồi

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Rollback ngay khi pipeline fail | DDL có thể đã commit hoặc dữ liệu đã được dùng | Reconcile session, schema, history trước |
| Không preview rollback | Drop nhầm object hoặc xóa dữ liệu | Chạy rollback-sql và review |
| Sửa changeset cũ | Checksum mismatch, lịch sử không nhất quán | Tạo changeset forward-fix |
| Cho rằng rollback DDL khôi phục dữ liệu | Dữ liệu đã xóa không tự quay lại | Dùng backup/PITR hoặc nguồn phục hồi |
| Restore thẳng production để thử | Làm gián đoạn và mất giao dịch mới | Restore vào môi trường cô lập |
| Restore DB nhưng không kiểm tra DBCL | Lịch sử có thể không khớp trạng thái | Đối chiếu DBCL, schema và release manifest |
| Chép DBCL từ PITR vào production | Xóa dấu vết migration mới hơn | Chỉ phục hồi dữ liệu nghiệp vụ khi selective recovery |
| Không xử lý sequence | INSERT mới có thể trùng ID | Kiểm tra và đồng bộ sequence theo DBMS |
| Không xét FK/trigger/outbox | Dữ liệu phục hồi thiếu quan hệ hoặc tạo side effect | Nạp theo dependency và kiểm tra downstream |
| Không đo RPO/RTO | Không biết khả năng phục hồi thực tế | Ghi timeline và so với mục tiêu |

## 25. Checklist nghiệm thu diễn tập

**Trước diễn tập**

- [ ] Database disposable và target identity đã xác nhận.
- [ ] Baseline dữ liệu và release marker được lưu.
- [ ] Liquibase/DBMS version được ghi.
- [ ] Backup/PITR đã được xác minh có thể restore.
- [ ] Có migration owner và người quan sát.
- [ ] Có runbook và tiêu chí dừng.

**Rollback**

- [ ] Changeset có rollback phù hợp.
- [ ] rollback-sql đã được review.
- [ ] Đã đánh giá dữ liệu mới và dependency ứng dụng.
- [ ] Rollback chỉ chạy trên target được phê duyệt.
- [ ] Postflight schema/data/history đạt.

**Forward-fix**

- [ ] Changeset cũ được giữ nguyên.
- [ ] Changeset mới có ID/author/path ổn định.
- [ ] Precondition và hậu điều kiện rõ.
- [ ] Dữ liệu cần sửa có nguồn sự thật và phạm vi xác định.
- [ ] Checksum/history sau fix được đối chiếu.

**Restore/PITR**

- [ ] Target time nằm đúng trước sự cố.
- [ ] Restore được thực hiện trên môi trường cô lập trước.
- [ ] Schema và DATABASECHANGELOG của bản restore được kiểm tra.
- [ ] Chọn rõ full restore hay selective recovery.
- [ ] Không ghi đè DATABASECHANGELOG production trong selective recovery.
- [ ] FK, sequence, trigger, outbox và downstream được kiểm tra.
- [ ] Data assertions và smoke test đạt.
- [ ] RPO/RTO thực tế được ghi.

**Bàn giao**

- [ ] Log, SQL, query results và approval được lưu.
- [ ] Release/incident record cập nhật.
- [ ] Không còn lock hoặc process phục hồi ngoài dự kiến.
- [ ] Ngoại lệ và follow-up có owner/thời hạn.
- [ ] Runbook được cập nhật từ bài học diễn tập.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, rollback, forward-fix và khôi phục dữ liệu là ba công cụ phục hồi có mục tiêu khác nhau. Rollback đảo changeset khi việc đảo ngược an toàn; forward-fix thêm migration mới để sửa trạng thái đã được sử dụng; backup/PITR khôi phục dữ liệu hoặc database về một mốc có thể kiểm chứng. Trong mọi trường hợp, phải đối chiếu DATABASECHANGELOG với schema và dữ liệu thực tế, thử phục hồi ở môi trường cô lập, kiểm tra ứng dụng và đo RPO/RTO. Một buổi diễn tập đạt yêu cầu khi đội vận hành có thể chứng minh đã khôi phục đúng trạng thái, giữ được giao dịch cần thiết và bàn giao đầy đủ bằng chứng cùng runbook cho lần xử lý sự cố thật.
