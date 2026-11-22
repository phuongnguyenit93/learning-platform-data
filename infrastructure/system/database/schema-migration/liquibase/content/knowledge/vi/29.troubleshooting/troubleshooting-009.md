# Changeset thực thi dở dang và lịch sử không phản ánh đầy đủ

Liquibase bắt đầu một changeset, database đã thực hiện một số câu lệnh, sau đó một câu lệnh khác thất bại. Lần chạy tiếp theo báo object đã tồn tại, cột đã được thêm hoặc dữ liệu đã ở trạng thái khác, trong khi DATABASECHANGELOG không có bản ghi tương ứng. Một tình huống khác là history ghi changeset đã chạy nhưng schema thực tế không còn giống trạng thái mà changelog mô tả. Đây là nhóm sự cố **changeset thực thi dở dang và lịch sử không phản ánh đầy đủ**.

Nguyên nhân thường nằm ở ranh giới transaction, hành vi DDL của DBMS, cấu hình runInTransaction, thao tác thủ công ngoài Liquibase, retry sau lỗi hoặc nhiều tiến trình migration cùng tác động. Liquibase lưu lịch sử ở mức changeset; bảng history không phải nhật ký từng câu SQL và không thể tự chứng minh mọi object/dữ liệu hiện tại vẫn đúng.

Bài học thuộc chương **Xử lý sự cố** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này giải thích trạng thái thực thi một phần, cách đọc history và schema thật, cách phân loại sự cố, và cách phục hồi có kiểm soát trước khi chạy lại migration.

## 1. Vì sao history có thể không khớp với schema?

Một changeset có thể gồm nhiều change hoặc nhiều câu SQL. Liquibase thường thực thi changeset trong transaction theo mặc định khi DBMS hỗ trợ và changeset cho phép transaction. Khi changeset thành công, Liquibase ghi nhận nó trong DATABASECHANGELOG. Nếu một câu lệnh thất bại, transaction có thể rollback toàn bộ thay đổi trong changeset.

Nhưng không phải mọi thao tác database đều có thể rollback nguyên tử:

- Một số DBMS thực hiện DDL với implicit commit.
- Một số lệnh DDL không được phép chạy bên trong transaction.
- Changeset có thể đặt runInTransaction: false.
- SQL script có thể gồm nhiều statement và dừng ở statement giữa chừng.
- Một thay đổi có thể đã commit ở DBMS trước khi Liquibase ghi history.
- Tiến trình có thể mất kết nối sau khi database đã commit nhưng client chưa nhận được kết quả.
- Người vận hành hoặc ứng dụng khác có thể sửa schema ngoài Liquibase.

Vì vậy, trạng thái của changeset và trạng thái của database là hai nguồn thông tin cần đối chiếu.

### 1.1. Ba lớp trạng thái cần phân biệt

| Lớp | Câu hỏi | Nguồn kiểm tra |
|---|---|---|
| **Changelog dự kiến** | Changeset định tạo/sửa object và dữ liệu nào? | File YAML/XML/JSON/SQL, include, context, label và precondition. |
| **Liquibase history** | Liquibase ghi nhận changeset nào đã xử lý? | DATABASECHANGELOG và kết quả lệnh status. |
| **Database thực tế** | Object và dữ liệu hiện đang ở trạng thái nào? | System catalog, metadata, truy vấn dữ liệu, constraint/index và log DBMS. |

Không thể suy ra database thực tế chỉ từ file changelog. Cũng không thể kết luận schema đúng chỉ vì một hàng history tồn tại.

### 1.2. History không phải nhật ký từng statement

DATABASECHANGELOG chủ yếu ghi nhận danh tính changeset, thời điểm, thứ tự thực thi, checksum và execution type theo phiên bản Liquibase. Nó không lưu đầy đủ before-image, kết quả từng statement, số hàng bị ảnh hưởng hoặc trạng thái trung gian của mọi DDL.

Ví dụ, một changeset có ba bước:

1. Tạo bảng staging.
2. Chuyển dữ liệu vào bảng đích.
3. Tạo index.

Nếu DBMS commit bước 1 và 2 riêng rẽ rồi bước 3 lỗi, history có thể chưa có bản ghi thành công cho changeset. Lần chạy sau thấy changeset pending, nhưng bảng staging và dữ liệu đã tồn tại. History cho biết Liquibase chưa ghi nhận hoàn tất; nó không nói rằng database chưa từng bị thay đổi.

## 2. Cơ chế transaction của changeset

### 2.1. Mặc định: một changeset trong transaction

Theo mặc định, Liquibase cố gắng chạy các change trong một changeset trong transaction nếu DBMS và loại statement hỗ trợ. Khi một change thất bại, Liquibase có thể rollback transaction và không ghi changeset như đã thực thi thành công.

Điều này có ích vì một changeset được thiết kế tốt thường có trạng thái all-or-nothing: tất cả thay đổi thành công hoặc không thay đổi nào được giữ lại.

Tuy nhiên, đây là behavior phụ thuộc DBMS và SQL thực tế. Không nên coi cấu hình mặc định là bảo đảm atomic cho mọi DDL, stored procedure hoặc câu SQL native.

### 2.2. runInTransaction: false

Khi đặt runInTransaction: false, changeset không được Liquibase bao trong transaction theo cách mặc định. Điều này có thể cần cho một số lệnh DBMS không chạy được trong transaction, ví dụ tạo index concurrently trên PostgreSQL.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 041-create-orders-index-concurrently
      author: db-team
      runInTransaction: false
      changes:
        - sql:
            sql: CREATE INDEX CONCURRENTLY idx_orders_created_at ON orders(created_at);
~~~

Nếu một changeset không transaction chứa nhiều statement, statement đầu có thể đã hoàn tất trước khi statement sau lỗi. Liquibase có thể không ghi history thành công cho changeset, nhưng tác động của statement trước vẫn tồn tại.

Với thay đổi không thể transaction, ưu tiên tách mỗi đơn vị có thể phục hồi thành changeset riêng, hoặc có runbook rõ ràng để nhận diện và sửa trạng thái dở dang. Không gom nhiều DDL độc lập vào một changeset chỉ để giảm số dòng history.

### 2.3. DDL có implicit commit

Một số DBMS hoặc một số loại DDL tự commit trước/sau câu lệnh. MySQL có nhiều DDL implicit commit; PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác nhưng có ngoại lệ như CREATE INDEX CONCURRENTLY. Hành vi còn phụ thuộc phiên bản và loại câu lệnh.

Khi DDL tự commit, rollback ở tầng JDBC/Liquibase không thể đưa database trở lại trước statement đã commit. Một changeset thất bại có thể để lại object dù transaction phía ứng dụng đã rollback.

### 2.4. Mất kết nối ở thời điểm commit

Một tình huống khó chẩn đoán:

1. Database nhận statement cuối và commit thành công.
2. Kết nối mạng bị ngắt trước khi client nhận phản hồi.
3. Liquibase không xác định được kết quả cuối hoặc không hoàn tất bước ghi history.
4. Pipeline báo lỗi dù một phần hoặc toàn bộ thay đổi đã tồn tại.

Đây là lý do không nên retry mù quáng. Trước khi chạy lại, hãy kiểm tra object và dữ liệu trực tiếp trên database.

## 3. Những dạng lệch giữa changeset và history

| Trạng thái quan sát | Ý nghĩa có thể có | Việc cần làm |
|---|---|---|
| Không có hàng history, không có thay đổi thực tế | Transaction đã rollback hoàn toàn hoặc changeset chưa bắt đầu. | Sửa nguyên nhân môi trường rồi chạy lại sau khi xác minh. |
| Không có hàng history, một số object đã tồn tại | DDL đã commit một phần, changeset không transaction hoặc thay đổi ngoài Liquibase. | Xác định chính xác trạng thái object và phục hồi trước khi retry. |
| Không có hàng history, dữ liệu đã bị cập nhật | DML đã commit riêng hoặc transaction scope không bao phủ toàn bộ. | Đối chiếu tập hàng, audit và nguồn before-image. |
| Có hàng history với EXECTYPE thành công, object bị thiếu | Object bị xóa/đổi sau migration, drift, restore không đồng bộ hoặc history được đồng bộ thủ công. | Điều tra thay đổi ngoài Liquibase và nguồn restore. |
| Có hàng history với MARK_RAN | Liquibase ghi nhận changeset đã xử lý mà không thực thi nội dung changeset theo điều kiện/command tương ứng. | Xác minh trạng thái được đánh dấu có đúng mục tiêu hay không. |
| Có hàng history nhưng checksum khác | Nội dung changelog thay đổi sau khi được ghi nhận hoặc checksum được xử lý lại. | Kiểm tra lịch sử file, checksum và thay đổi có chủ đích. |
| History ở database/schema khác | CLI và ứng dụng dùng URL, user hoặc schema metadata khác nhau. | Xác minh danh tính kết nối và cấu hình thực tế. |
| Lock đang được giữ dù pipeline đã kết thúc | Tiến trình còn chạy, bị treo hoặc lock chưa được giải phóng sau sự cố. | Kiểm tra session/process trước khi giải phóng lock. |

Một hàng history vắng mặt không chứng minh không có side effect. Một hàng history có mặt cũng không chứng minh schema vẫn nguyên vẹn.

## 4. Ví dụ: changeset thực thi dở dang

Giả sử một changeset không dùng transaction gồm hai bước:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 042-prepare-order-archive
      author: db-team
      runInTransaction: false
      changes:
        - createTable:
            tableName: order_archive_stage
            columns:
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
              - column:
                  name: archived_at
                  type: TIMESTAMP
              - column:
                  name: archived_at
                  type: TIMESTAMP
        - sql:
            sql: INSERT INTO order_archive_stage (order_id, archived_at) SELECT id, CURRENT_TIMESTAMP FROM sales_order WHERE archived = true;
        - createIndex:
            tableName: order_archive_stage
            indexName: idx_order_archive_stage_archived_at
            columns:
              - column:
                  name: archived_at
~~~

Giả sử bảng được tạo và dữ liệu đã được insert, nhưng tạo index thất bại do thiếu quyền hoặc lock. Có thể quan sát:

- order_archive_stage đã tồn tại.
- Số hàng trong bảng stage lớn hơn 0.
- Index chưa tồn tại hoặc được tạo ở trạng thái không hợp lệ tùy DBMS.
- DATABASECHANGELOG không có changeset 042-prepare-order-archive vì toàn changeset chưa được ghi nhận thành công.

Nếu chạy lại ngay, bước create table có thể lỗi “already exists”. Nếu thêm precondition tableExists rồi dùng MARK_RAN, Liquibase có thể đánh dấu changeset đã chạy dù bước insert hoặc index chưa hoàn tất. Cách đó biến một lỗi có thể sửa được thành history sai lệch.

## 5. Đọc DATABASECHANGELOG đúng cách

### 5.1. Tìm changeset liên quan

Các cột phổ biến trong DATABASECHANGELOG gồm:

- ID: ID của changeset.
- AUTHOR: author.
- FILENAME: đường dẫn định danh changelog.
- DATEEXECUTED: thời điểm Liquibase ghi nhận thực thi.
- ORDEREXECUTED: thứ tự thực thi.
- EXECTYPE: loại kết quả được ghi nhận.
- MD5SUM: checksum theo cơ chế/phiên bản Liquibase.
- DEPLOYMENT_ID: định danh lần triển khai nếu được phiên bản hỗ trợ.

Schema bảng và tập cột có thể khác theo phiên bản Liquibase. Trước khi viết truy vấn chẩn đoán, kiểm tra cấu trúc bảng thực tế.

Ví dụ truy vấn PostgreSQL:

~~~sql
SELECT id, author, filename, dateexecuted, orderexecuted, exectype, md5sum
FROM databasechangelog
WHERE id = '042-prepare-order-archive'
ORDER BY orderexecuted;
~~~

Tên bảng/cột có thể được tạo với cách viết hoa/thường hoặc schema khác tùy DBMS và cấu hình. Hãy dùng đúng schema metadata, quoting và tên thực tế.

### 5.2. Hiểu EXECTYPE

Liquibase có thể ghi các execution type như:

| EXECTYPE | Diễn giải khái quát |
|---|---|
| EXECUTED | Changeset được thực thi và ghi nhận. |
| RERAN | Changeset được chạy lại theo cơ chế như runOnChange. |
| MARK_RAN | Changeset được đánh dấu đã chạy mà không thực thi thay đổi thông thường. |
| SKIPPED | Changeset bị bỏ qua trong một số luồng/phiên bản. |
| FAILED | Trạng thái lỗi có thể xuất hiện trong một số phiên bản/cơ chế. |

Không giả định mọi lỗi đều tạo một hàng FAILED. Trong nhiều trường hợp, changeset thất bại không được ghi như một lần thực thi thành công; vì vậy hàng có thể hoàn toàn không xuất hiện. Hãy dựa vào phiên bản Liquibase, log và schema thật.

### 5.3. Xác định đúng đường dẫn changeset

Liquibase nhận diện changeset bằng ID, author và đường dẫn changelog định danh. Nếu file được di chuyển hoặc logicalFilePath thay đổi, Liquibase có thể coi đó là một changeset khác.

Khi điều tra history:

- So sánh đủ ID, author và FILENAME.
- Kiểm tra include path và relative path.
- Kiểm tra logicalFilePath nếu có.
- Xác minh CLI và Spring Boot nạp cùng root changelog.
- Không sửa FILENAME trong history thủ công để ép Liquibase nhận diện.

### 5.4. History có thể phản ánh filter khác nhau

Context, label, DBMS filter và precondition có thể khiến một changeset được chạy hoặc bỏ qua theo môi trường. Hai môi trường có cùng changelog nhưng history khác nhau chưa chắc là lỗi; phải đối chiếu tham số chạy và chính sách triển khai.

## 6. Đọc DATABASECHANGELOGLOCK

Liquibase dùng bảng DATABASECHANGELOGLOCK để tránh nhiều tiến trình cùng cập nhật history trên một database tại cùng thời điểm. Các trường phổ biến gồm trạng thái lock, thời điểm cấp lock và thông tin tiến trình giữ lock.

Một lock đang tồn tại có thể là:

- Migration vẫn đang chạy.
- Migration đang chờ database hoặc statement.
- Tiến trình bị dừng bất thường và chưa giải phóng lock.
- Một worker khác đang triển khai cùng database.

Lock không chứng minh changeset đã rollback hay đã commit. Nó cũng không bảo vệ khỏi thao tác DDL thủ công ngoài Liquibase.

### 6.1. Trước khi release lock

1. Kiểm tra pipeline/job liên quan còn chạy không.
2. Kiểm tra session database có statement migration còn hoạt động không.
3. Xác định tiến trình giữ lock và thời điểm lock được cấp.
4. Xác nhận không có tiến trình hợp lệ đang thực thi.
5. Thu thập log và trạng thái schema/history trước khi giải phóng.
6. Dùng command release lock được Liquibase hỗ trợ cho phiên bản đang dùng nếu thực sự cần.

Không xóa hàng lock hoặc đặt cột lock về false bằng SQL tùy tiện. Nếu tiến trình vẫn chạy, giải phóng lock có thể cho một migration thứ hai bắt đầu trong khi migration đầu còn thay đổi database.

## 7. Chẩn đoán schema và dữ liệu thực tế

Sau khi đọc history, kiểm tra trực tiếp object mà changeset định tạo hoặc sửa.

### 7.1. Kiểm tra object

Với mỗi object liên quan, ghi nhận:

- Có tồn tại không?
- Kiểu dữ liệu, nullability, default và collation có đúng không?
- Primary key, unique, foreign key và check constraint có đúng không?
- Index có tồn tại và hợp lệ không?
- View/routine/trigger có definition mong đợi không?
- Owner và grants có đúng không?
- Object có nằm trong đúng schema/catalog không?

Chỉ kiểm tra tên bảng tồn tại là chưa đủ. Bảng có thể đã tồn tại nhưng thiếu cột, sai kiểu hoặc thiếu constraint.

### 7.2. Kiểm tra dữ liệu

Nếu changeset có DML/backfill, kiểm tra:

- Tổng số hàng trước và sau (nếu có số liệu baseline).
- Số hàng thỏa điều kiện thay đổi.
- Số hàng còn pending.
- NULL, duplicate, orphan và giá trị ngoài miền hợp lệ.
- Có cập nhật trùng khi retry không.
- Có dữ liệu được ứng dụng ghi sau thời điểm migration không.

Ví dụ truy vấn kiểm tra dữ liệu archive:

~~~sql
SELECT COUNT(*) AS staged_rows
FROM order_archive_stage;

SELECT COUNT(*) AS eligible_rows
FROM sales_order
WHERE archived = true;

SELECT COUNT(*) AS missing_rows
FROM sales_order s
LEFT JOIN order_archive_stage a ON a.order_id = s.id
WHERE s.archived = true
  AND a.order_id IS NULL;
~~~

Các số liệu chỉ có ý nghĩa khi điều kiện lọc, thời điểm đọc và dữ liệu nguồn không thay đổi trong lúc kiểm tra. Nếu có ghi đồng thời, cần snapshot/transaction phù hợp hoặc tạm kiểm soát luồng ghi.

### 7.3. Kiểm tra index PostgreSQL

Một index được tạo bằng thao tác concurrent có thể tồn tại nhưng không hợp lệ nếu quá trình tạo thất bại. Có thể kiểm tra metadata PostgreSQL:

~~~sql
SELECT i.relname AS index_name, ix.indisready, ix.indisvalid
FROM pg_class t
JOIN pg_index ix ON ix.indrelid = t.oid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'orders';
~~~

Nếu index không hợp lệ, không chỉ nhìn thấy tên index rồi kết luận migration đã hoàn tất. Hãy kiểm tra DBMS docs và plan sửa: drop index lỗi rồi tạo lại, hoặc xử lý theo trạng thái hiện tại sau khi xác nhận không có dependency.

## 8. Phân loại và chọn cách phục hồi

| Tình trạng sau lỗi | Phương án thường cân nhắc | Điều kiện trước khi thực hiện |
|---|---|---|
| Transaction đã rollback toàn bộ, schema/data ở trạng thái trước | Sửa nguyên nhân môi trường rồi retry changeset. | Xác minh không có side effect và changeset chưa chạy thành công ở môi trường khác nếu định sửa nội dung. |
| Một phần DDL còn tồn tại, không có dữ liệu quan trọng | Khôi phục đúng pre-state rồi chạy lại, hoặc hoàn tất state có kiểm soát. | Đọc metadata và xác định dependency/owner. |
| DML đã cập nhật một phần | Tiếp tục theo checkpoint hoặc khôi phục bằng before-image. | Xác định tập hàng, tính idempotent và nguồn giá trị cũ. |
| Object đã đạt đúng trạng thái cuối nhưng history thiếu | Reconcile history theo quy trình có phê duyệt, sau khi chứng minh trạng thái đầy đủ. | Đối chiếu toàn bộ side effect; dùng cơ chế Liquibase có phạm vi hẹp phù hợp phiên bản. |
| History có nhưng object bị thiếu/sai | Điều tra drift, restore hoặc thao tác ngoài Liquibase; thêm remediation. | Xác định ai/thời điểm làm thay đổi và consumer bị ảnh hưởng. |
| Changeset đã chạy thành công ở môi trường khác nhưng file bị sửa | Giữ nguyên changeset cũ, thêm changeset mới. | Kiểm tra checksum và kế hoạch đồng bộ mọi môi trường. |

Không có một câu lệnh chung an toàn cho mọi trạng thái dở dang. Chọn cách phục hồi sau khi xác định chính xác database đang ở trạng thái nào.

## 9. Quy trình phục hồi khi changeset thất bại giữa chừng

### Bước 1 — Ngăn chạy đồng thời

Tạm dừng pipeline retry hoặc deployment tiếp theo cho database đó. Kiểm tra Liquibase lock và session DBMS. Không để một tiến trình thứ hai chạy khi tiến trình đầu chưa được xác định trạng thái.

### Bước 2 — Giữ nguyên bằng chứng

Lưu log, SQL preview, stack trace, SQLState, vendor code, changelog artifact và phiên bản Liquibase. Ghi lại thời điểm lỗi, ID/author/path và profile/context/label.

### Bước 3 — Xác định history

Tìm đúng bộ ba ID/author/FILENAME trong DATABASECHANGELOG. Xác định hàng có tồn tại không, EXECTYPE/checksum nào được ghi và có changeset sau đó phụ thuộc không.

### Bước 4 — Kiểm tra database thật

Đối chiếu từng statement trong changeset với object và dữ liệu thực tế. Kiểm tra transaction behavior của DBMS và câu lệnh cụ thể.

### Bước 5 — Chọn trạng thái mục tiêu

Quyết định cần:

- Trở về pre-state để chạy lại changeset.
- Hoàn tất phần còn thiếu để đạt post-state.
- Sửa tiến bằng changeset mới.
- Khôi phục dữ liệu/schema từ backup hoặc nguồn đáng tin.

Không trộn nhiều phương án trong một thao tác không có checkpoint.

### Bước 6 — Thực hiện sửa chữa có kiểm soát

Thử trên bản sao đại diện trước. Nếu cần SQL thủ công, lưu script, người thực hiện, thời điểm và kết quả. Dùng transaction nếu DBMS và câu lệnh hỗ trợ; nếu không, chia bước và có kiểm tra sau từng bước.

### Bước 7 — Reconcile Liquibase history

Chỉ sau khi database đã được xác minh đạt trạng thái mà history dự kiến biểu diễn, mới xử lý trạng thái Liquibase. Ưu tiên để một changeset hợp lệ chạy và ghi history theo luồng bình thường. Nếu cần đánh dấu baseline hoặc đồng bộ history thủ công, phải giới hạn đúng changeset/môi trường bằng cơ chế được hỗ trợ, xem trước phạm vi và có phê duyệt.

changelogSync có thể đánh dấu các changeset pending theo bộ lọc hiện tại là đã chạy mà không thực thi chúng. Đây là công cụ baseline/reconciliation có phạm vi rộng tùy cấu hình, không phải cách sửa lỗi dở dang. Trước khi dùng, phải xác định chính xác tập changeset sẽ bị đánh dấu; không chạy chỉ để làm status hết pending.

### Bước 8 — Xác minh sau phục hồi

Chạy validate, status --verbose, xem SQL preview nếu còn changeset pending, kiểm tra schema/data và đọc lại history. Kiểm thử ứng dụng và các consumer phụ thuộc trước khi mở lại deployment.

## 10. Khi nào được retry cùng changeset?

Retry chỉ an toàn khi hiểu trạng thái của lần chạy trước và chứng minh thao tác sẽ không nhân đôi hoặc phá dữ liệu.

### 10.1. Trường hợp có thể retry

- Changeset không có history thành công.
- Transaction rollback hoàn toàn hoặc các side effect đã được đưa về pre-state.
- Không có dữ liệu được ghi một phần hoặc dữ liệu đó đã được xử lý có kiểm chứng.
- Tài khoản, network, lock hoặc điều kiện môi trường gây lỗi đã được sửa.
- Nội dung changeset không bị thay đổi so với artifact cần triển khai.
- Đã thử trên database đại diện.

### 10.2. Trường hợp không nên retry ngay

- Bảng/index/constraint đã tồn tại một phần.
- DML có thể insert/update trùng hoặc ghi đè dữ liệu hợp lệ.
- DBMS đã implicit commit một số statement.
- Changeset có SQL không idempotent.
- Có tiến trình khác đang chạy migration.
- History ở môi trường khác đã ghi nhận cùng changeset nhưng checksum/path không khớp.
- Không xác định được statement nào đã hoàn tất.

### 10.3. Retry không đồng nghĩa chạy lại SQL tùy tiện

Liquibase thường bỏ qua changeset đã ghi nhận thành công. Khi không có hàng history, Liquibase có thể xem changeset là pending và chạy lại toàn bộ. Nó không tự biết statement đầu của lần chạy trước đã commit hay chưa.

Do đó, retry phải dựa trên trạng thái database thật, không dựa vào việc Liquibase hiển thị changeset pending.

## 11. Thiết kế changeset để giảm rủi ro thực thi dở dang

### 11.1. Một changeset nên là một đơn vị thay đổi có thể hiểu và phục hồi

Tách những thay đổi có failure mode độc lập:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 050-create-order-archive-stage
      author: db-team
      changes:
        - createTable:
            tableName: order_archive_stage
            columns:
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    primaryKey: true

  - changeSet:
      id: 051-create-order-archive-index
      author: db-team
      runInTransaction: false
      changes:
        - sql:
            sql: CREATE INDEX CONCURRENTLY idx_order_archive_stage_archived_at ON order_archive_stage(archived_at);
~~~

Ví dụ minh họa việc tách tạo bảng và tạo index không transaction. Trước khi dùng, bảo đảm cột archived_at đã được thêm vào bảng trong changeset phù hợp; ví dụ này tập trung vào ranh giới transaction, không phải một changelog hoàn chỉnh để triển khai nguyên trạng.

### 11.2. Không gom DDL và backfill dài vào một changeset

Nếu một changeset vừa tạo bảng, vừa backfill hàng triệu dòng, vừa thêm constraint, lỗi ở cuối có thể để lại trạng thái khó phân loại. Có thể chia:

1. Expand schema.
2. Backfill theo batch/checkpoint.
3. Validate dữ liệu.
4. Add constraint/index.
5. Contract sau khi consumer chuyển đổi.

Mỗi bước có điều kiện đầu vào và hậu điều kiện rõ ràng.

### 11.3. Sử dụng precondition để bảo vệ giả định

Precondition giúp Liquibase kiểm tra trạng thái trước khi chạy changeset. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 052-add-order-source
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: sales_order
      changes:
        - addColumn:
            tableName: sales_order
            columns:
              - column:
                  name: source_channel
                  type: VARCHAR(30)
~~~

Precondition ở đây chỉ bảo đảm bảng tồn tại. Nếu cần bảo đảm cột chưa tồn tại, kiểu hiện tại đúng hoặc dữ liệu đáp ứng constraint, cần kiểm tra thêm. Không dùng precondition quá yếu rồi suy ra toàn bộ trạng thái schema đã đúng.

### 11.4. Idempotency và khả năng resume

Đối với backfill, hãy thiết kế để:

- Có khóa định danh từng hàng hoặc checkpoint.
- Chỉ xử lý hàng chưa hoàn tất.
- Có thể chạy lại mà không tạo bản ghi trùng.
- Ghi nhận số hàng đã xử lý và lỗi.
- Không ghi đè dữ liệu được cập nhật hợp lệ sau đó.
- Có thể tiếp tục từ checkpoint sau khi process bị dừng.

Không phải mọi DDL có thể làm idempotent bằng IF NOT EXISTS; một object cùng tên nhưng definition sai vẫn cần được phát hiện và xử lý.

## 12. Vai trò của runOnChange, runAlways và checksum

### 12.1. runOnChange không phải cơ chế retry một phần

runOnChange cho phép changeset được chạy lại khi nội dung thay đổi theo checksum. Nó phù hợp với một số object như view/procedure được quản lý như definition hiện tại. Nó không phải công cụ phục hồi changeset DDL/DML đã thực thi dở dang.

Nếu một changeset có DML không idempotent và bật runOnChange, thay đổi nội dung có thể làm statement chạy lại trên dữ liệu đã được cập nhật. Cần thiết kế semantics và rollback riêng.

### 12.2. runAlways không bảo đảm an toàn

runAlways khiến changeset được chạy ở mỗi lần update theo điều kiện áp dụng. Nếu nội dung là insert hoặc update không idempotent, nó có thể tạo dữ liệu trùng hoặc sửa dữ liệu nhiều lần. Không dùng runAlways để “đảm bảo changeset chạy nốt phần còn lại”.

### 12.3. Checksum mismatch là một vấn đề khác

Checksum giúp Liquibase phát hiện nội dung changeset đã thay đổi sau khi được ghi nhận. Nó không cho biết statement nào đã commit và không mô tả trạng thái object thực tế.

- clearCheckSums làm Liquibase tính lại checksum theo cơ chế hỗ trợ; nó không sửa schema hoặc dữ liệu.
- validCheckSum cho phép chấp nhận checksum cụ thể trong một số trường hợp có chủ đích; nó không chứng minh thay đổi đã được thực thi.
- Sửa nội dung changeset đã triển khai có thể gây checksum mismatch và làm lịch sử giữa môi trường không đồng nhất.

Nếu changeset đã thành công ở bất kỳ môi trường nào, giữ nguyên nội dung lịch sử và tạo changeset mới cho sửa chữa. Nếu changeset chỉ thất bại ở mọi môi trường, chưa có history thành công và chưa có release nào phụ thuộc vào nội dung đó, việc sửa source vẫn cần được phối hợp và xác minh trạng thái từng database trước khi phát hành lại.

## 13. Khi schema đã hoàn tất nhưng history thiếu

Đây là trường hợp dễ bị xử lý sai nhất. Có thể database đã đạt post-state nhưng Liquibase không ghi history do mất kết nối ở cuối, hoặc DBA đã hoàn tất thủ công phần còn thiếu.

Trước khi reconciliation, cần chứng minh:

1. Tất cả object được changeset tạo/sửa đều đúng definition.
2. Tất cả DML đã chạy đủ, không thiếu hoặc trùng hàng.
3. Constraint/index/sequence/view/routine ở trạng thái hợp lệ.
4. Không có statement phụ nào trong changeset chưa chạy.
5. Dữ liệu không bị thay đổi ngoài dự kiến sau migration.
6. Các changeset phụ thuộc có thể chạy an toàn.
7. Mọi môi trường đã được đối chiếu để không tạo checksum/path conflict.

Nếu trạng thái cuối chưa đạt, hãy hoàn tất hoặc khôi phục database trước. Nếu trạng thái cuối đã đạt hoàn toàn, lựa chọn cơ chế ghi nhận history cần dựa trên version Liquibase và policy triển khai. Không dùng changelogSync rộng trên production khi chưa biết nó sẽ đánh dấu thêm những changeset pending nào.

### 13.1. Tại sao MARK_RAN không phải cách sửa mặc định?

MARK_RAN phù hợp với một điều kiện nghiệp vụ được định nghĩa trước: nếu thay đổi đã tồn tại và đáp ứng contract, Liquibase có thể ghi nhận changeset mà không chạy lại nội dung. Nhưng nếu chỉ kiểm tra tableExists trong khi bảng thiếu cột, dữ liệu chưa backfill hoặc index chưa tạo, history sẽ đánh dấu một trạng thái chưa hoàn tất.

Nếu dùng MARK_RAN trong reconciliation, precondition phải chứng minh đầy đủ trạng thái đích, không chỉ một dấu hiệu đơn giản. Điều kiện đó cần được kiểm thử trên database sạch, database đã được sửa thủ công và các môi trường khác.

## 14. Khi history có changeset nhưng schema thực tế bị thiếu

Một changeset có history nhưng object bị thiếu thường chỉ ra một thay đổi xảy ra **sau** khi Liquibase ghi nhận, ví dụ:

- DBA hoặc script khác drop/alter object.
- Restore database không đồng bộ với bảng history.
- Một nhánh migration khác thay đổi object.
- Schema drift do thao tác ngoài pipeline.
- History được sync thủ công mà không kiểm chứng trạng thái.

Quy trình:

1. Xác minh đúng database/schema và history row.
2. Xem checksum, execution type, thời điểm và deployment ID nếu có.
3. Kiểm tra audit log, DDL log hoặc hoạt động DBA.
4. So sánh schema thật với trạng thái mà changelog mong đợi.
5. Xác định consumer và dữ liệu có bị ảnh hưởng không.
6. Tạo changeset remediation mới hoặc phục hồi từ backup nếu dữ liệu bị mất.
7. Giữ nguyên history đã phát hành; không xóa hàng history để ép chạy lại.

Nếu object bị thiếu do restore về mốc cũ, hãy xem cả history lẫn toàn bộ database đã được khôi phục cùng một mốc chưa. Không trộn history từ database mới với schema của database cũ.

## 15. Những thao tác dễ làm history sai lệch

| Thao tác | Tác dụng thực tế | Rủi ro khi dùng sai |
|---|---|---|
| changelogSync | Đánh dấu changeset pending theo bộ lọc hiện tại là đã chạy mà không thực thi chúng. | Có thể bỏ qua nhiều changeset chưa áp dụng. |
| clearCheckSums | Xóa checksum lưu để Liquibase tính lại theo cơ chế hỗ trợ. | Có thể che dấu việc changelog bị sửa nếu không điều tra. |
| validCheckSum | Chấp nhận một checksum được chỉ định cho changeset. | Không sửa object/data đang sai. |
| MARK_RAN | Ghi nhận changeset như đã chạy khi precondition chọn nhánh đó. | Có thể đánh dấu thiếu bước nếu precondition yếu. |
| runOnChange | Chạy lại changeset khi checksum thay đổi theo quy tắc. | Có thể lặp DML hoặc thay đổi definition ngoài ý muốn. |
| runAlways | Chạy changeset trong mỗi lần update phù hợp. | Có thể nhân đôi dữ liệu hoặc lặp side effect. |
| Sửa trực tiếp DATABASECHANGELOG | Thay đổi metadata history. | History không còn phản ánh quá trình triển khai thật. |
| Xóa DATABASECHANGELOGLOCK | Can thiệp trạng thái lock. | Có thể tạo migration đồng thời khi tiến trình cũ còn chạy. |

Các command này có trường hợp sử dụng hợp lệ, nhưng phải gắn với một mục tiêu cụ thể, scope được review và bằng chứng schema/data. Không dùng chúng như nút “reset” khi Liquibase báo lỗi.

## 16. Các tình huống thực tế

### Tình huống A — Tạo bảng thành công, tạo index thất bại

**Triệu chứng:** lần đầu báo lỗi khi tạo index; lần sau báo bảng đã tồn tại; history không có changeset.

**Điều tra:** kiểm tra bảng, cột, constraint, dữ liệu và index; xem SQL/DBMS log để biết statement nào commit.

**Xử lý:** nếu bảng và dữ liệu chưa có giá trị cần giữ, có thể khôi phục đúng pre-state rồi retry changeset sau khi sửa nguyên nhân. Nếu dữ liệu đã có ý nghĩa, thiết kế cách hoàn tất phần index và reconciliation history có kiểm soát. Không dùng MARK_RAN chỉ vì bảng tồn tại.

### Tình huống B — Backfill chỉ cập nhật một phần

**Triệu chứng:** một tập hàng có giá trị mới, phần còn lại vẫn NULL; changeset pending.

**Điều tra:** xác định batch/checkpoint, số hàng dự kiến, điều kiện lọc, transaction và nguồn dữ liệu.

**Xử lý:** nếu update có thể resume an toàn, chạy job/changeset tiếp tục chỉ trên hàng chưa xử lý. Nếu có giá trị bị ghi sai, dùng before-image/audit để sửa. Không chạy lại toàn bộ update nếu có thể ghi đè thay đổi hợp lệ.

### Tình huống C — Index concurrently tồn tại nhưng invalid

**Triệu chứng:** PostgreSQL có tên index trong catalog nhưng query planner không dùng; changeset không có history.

**Điều tra:** kiểm tra pg_index.indisvalid và indisready, lỗi tạo index và session cạnh tranh.

**Xử lý:** theo DBMS docs, xác nhận không có dependency; drop index invalid nếu phù hợp rồi tạo lại, hoặc thực hiện remediation có kiểm soát. Sau đó xác minh index hợp lệ trước khi reconciliation history.

### Tình huống D — History có nhưng cột bị drop

**Triệu chứng:** Liquibase báo changeset đã chạy, ứng dụng báo column not found.

**Điều tra:** xác minh database/schema, DDL audit, restore history và thao tác ngoài pipeline.

**Xử lý:** nếu cột bị drop ngoài ý muốn, tạo changeset mới tái tạo cột và khôi phục dữ liệu từ nguồn đáng tin. Không xóa history changeset cũ để chạy lại.

### Tình huống E — Pipeline timeout nhưng migration có thể đã commit

**Triệu chứng:** job timeout hoặc connection reset; lần sau changeset pending.

**Điều tra:** kiểm tra server log, session, object/data và history. Xác định timeout xảy ra trước hay sau commit.

**Xử lý:** chỉ retry khi đã chứng minh side effect trước đó đã rollback hoặc đã được xử lý. Nếu kết quả commit không xác định, ưu tiên kiểm tra trạng thái database và reconciliation.

## 17. Bài thực hành có kiểm chứng

**Bối cảnh:** một database PostgreSQL lab có bảng sales_order. Liquibase cần tạo bảng archive staging, copy các đơn hàng đã archive và tạo index concurrently. Mục tiêu là quan sát trạng thái khi changeset thực thi dở dang.

### Giai đoạn A — Chuẩn bị

1. Tạo database lab riêng và dữ liệu đơn hàng giả lập.
2. Viết changelog có changeset tạo bảng staging và changeset tạo index riêng.
3. Đặt changeset index dùng SQL phù hợp với PostgreSQL nếu cần concurrent build.
4. Chạy validate và SQL preview để kiểm tra statement.
5. Ghi lại số hàng nguồn và schema ban đầu.

### Giai đoạn B — Tạo lỗi có kiểm soát

1. Trong môi trường lab, tạo điều kiện để index build thất bại hoặc cố ý gây lỗi ở bước sau.
2. Chạy Liquibase và lưu log.
3. Kiểm tra changeset có được ghi trong DATABASECHANGELOG không.
4. Kiểm tra bảng staging, số hàng và trạng thái index trong system catalog.
5. Xác nhận lock đã được giải phóng hay tiến trình còn chạy.

### Giai đoạn C — Phục hồi

1. Phân loại database đang ở pre-state, partial-state hay post-state.
2. Chọn khôi phục pre-state hoặc hoàn tất post-state.
3. Nếu dùng SQL thủ công, lưu script và kiểm tra từng bước.
4. Chạy lại Liquibase chỉ sau khi xác minh retry an toàn.
5. Kiểm tra history, object, index validity và số hàng.

### Giai đoạn D — So sánh hành vi transaction

1. Chạy một changeset tương tự với transaction mặc định trên DBMS hỗ trợ.
2. Tạo lỗi giữa các statement trong lab.
3. So sánh schema/data trước và sau rollback transaction.
4. Chạy lại với runInTransaction: false và quan sát side effect còn lại.
5. Ghi nhận khác biệt và xây runbook cho từng loại change.

**Tiêu chí đạt:** giải thích được vì sao history không ghi nhận một changeset nhưng database vẫn có side effect; phân biệt được transaction rollback với implicit commit/non-transactional DDL; xác minh được schema, dữ liệu, index và lock; chọn được phương án phục hồi trước retry.

## 18. Checklist xử lý changeset dở dang

- [ ] Dừng pipeline retry và xác định có tiến trình migration nào còn hoạt động.
- [ ] Ghi nhận đúng database, schema, changelog artifact, Liquibase version và changeset ID/author/path.
- [ ] Đọc history và execution type; không giả định lỗi luôn tạo hàng FAILED.
- [ ] Kiểm tra DATABASECHANGELOGLOCK và session DBMS trước khi release lock.
- [ ] Xác định runInTransaction, transaction scope và DDL behavior của DBMS.
- [ ] Đối chiếu từng statement với object và dữ liệu thực tế.
- [ ] Kiểm tra constraint, index validity, sequence, view, routine và grants khi liên quan.
- [ ] Xác định DML có thể chạy một phần hoặc bị lặp khi retry không.
- [ ] Chọn rõ pre-state, post-state hoặc trạng thái phục hồi mục tiêu.
- [ ] Thử phương án trên bản sao đại diện.
- [ ] Không sửa changeset đã chạy thành công ở môi trường khác.
- [ ] Không dùng MARK_RAN/changelogSync chỉ để xóa trạng thái pending.
- [ ] Không xóa hoặc sửa trực tiếp history/lock để làm sạch lỗi.
- [ ] Reconcile history chỉ sau khi chứng minh schema/data đạt trạng thái tương ứng.
- [ ] Chạy validate, status, SQL preview và test ứng dụng sau phục hồi.
- [ ] Lưu log, SQL sửa chữa, người thực hiện và kết quả hậu kiểm.

## 19. Câu hỏi tự kiểm tra

1. Vì sao một changeset có thể thất bại nhưng database vẫn giữ một phần thay đổi?
2. Liquibase mặc định xử lý transaction của changeset như thế nào khi DBMS hỗ trợ?
3. runInTransaction: false làm tăng rủi ro gì?
4. DDL implicit commit ảnh hưởng thế nào tới retry?
5. Vì sao không có hàng trong DATABASECHANGELOG không chứng minh database chưa thay đổi?
6. Vì sao có hàng history cũng không chứng minh schema hiện tại còn đúng?
7. EXECTYPE có thể cho biết những gì và không cho biết những gì?
8. DATABASECHANGELOGLOCK có bảo vệ khỏi DDL thủ công ngoài Liquibase không?
9. Trước khi retry một changeset pending, cần kiểm tra những object và dữ liệu nào?
10. Khi nào có thể retry cùng changeset sau khi sửa lỗi?
11. Vì sao precondition tableExists không đủ để đánh dấu một changeset nhiều bước là hoàn tất?
12. runOnChange và runAlways có phải cơ chế resume changeset dở dang không?
13. clearCheckSums có sửa schema hoặc dữ liệu không?
14. Vì sao changelogSync có thể làm history sai lệch nếu dùng không giới hạn?
15. Khi schema đã đạt post-state nhưng history thiếu, cần chứng minh điều gì trước reconciliation?
16. Nếu history có nhưng object bị thiếu, nên điều tra theo hướng nào?

## Kết luận

Changeset thực thi dở dang xảy ra khi **trạng thái transaction/DDL của database và thời điểm ghi history không cùng phản ánh một kết quả nguyên tử**. Khi gặp lỗi, hãy giữ nguyên bằng chứng, xác định tiến trình và lock, đọc history rồi kiểm tra từng object/dữ liệu trực tiếp. Chỉ retry khi đã chứng minh side effect trước đó được rollback hoặc được phục hồi; chỉ reconcile history khi database thực sự đạt trạng thái mà history sẽ biểu diễn. Thiết kế changeset nhỏ, hiểu transaction của DBMS, dùng precondition đủ mạnh và backfill có thể resume giúp **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** vận hành đáng tin cậy hơn khi migration bị gián đoạn.
