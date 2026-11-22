# Xử lý migration thất bại và giới hạn quay lui thay đổi dữ liệu

## 1. Vì sao migration thất bại là một sự cố tích hợp hệ thống?

Trong một ứng dụng Spring Boot, migration thay đổi cấu trúc hoặc nội dung cơ sở dữ liệu để đáp ứng phiên bản ứng dụng mới. Flyway và Liquibase thường chạy trước khi các thành phần sử dụng database sẵn sàng. Nếu migration lỗi, ứng dụng có thể không khởi động; nghiêm trọng hơn, một phần dữ liệu đã thay đổi trong khi các phiên bản ứng dụng cũ, HTTP client, cache hoặc consumer thông điệp vẫn hoạt động.

Ví dụ, hệ thống đơn hàng đổi trạng thái lưu trong cột **status_text** thành **status_code**. Sau khi cập nhật 600.000 trong 1 triệu đơn, migration phát hiện trạng thái cũ chưa có quy tắc ánh xạ và dừng. Dù triển khai lại phiên bản ứng dụng trước, 600.000 hàng có thể vẫn mang giá trị mới. Việc quay lại mã nguồn cũ không tự đảo ngược các câu lệnh SQL đã commit.

Bài này tập trung vào ba câu hỏi vận hành:

1. Khi migration báo lỗi, **database hiện đang ở trạng thái nào**?
2. Thao tác nào có thể rollback bằng giao dịch, thao tác nào phải sửa tiến (forward fix), bù trừ hoặc phục hồi từ bản sao lưu?
3. Làm thế nào thiết kế quy trình migration để lỗi một phần vẫn có thể kiểm chứng, chạy lại và khôi phục dịch vụ?

Phạm vi bao gồm Flyway/Liquibase, giao dịch SQL, backfill dữ liệu theo lô, triển khai nhiều phiên bản Spring Boot và các luồng tích hợp có API, cache, broker thông điệp.

## 2. Phân biệt rollback giao dịch, rollback schema và phục hồi dữ liệu

Ba thao tác sau giải quyết những vấn đề khác nhau:

| Khái niệm | Ý nghĩa | Điều kiện và giới hạn |
| --- | --- | --- |
| **Transaction rollback** | Hủy các thay đổi **chưa commit** của giao dịch hiện tại. | Chỉ áp dụng cho thao tác được database hỗ trợ trong cùng giao dịch; không hủy các giao dịch đã commit. |
| **Schema rollback** | Đưa cấu trúc về dạng cũ, ví dụ bỏ cột vừa thêm hoặc đổi lại kiểu dữ liệu. | Có thể làm mất dữ liệu và có thể không khôi phục được giá trị trước khi chuyển kiểu, gộp cột hoặc xóa bảng. |
| **Data recovery/compensation** | Phục hồi giá trị cũ từ backup, lịch sử, audit log; hoặc thực hiện hành động nghiệp vụ bù trừ. | Cần nguồn dữ liệu đáng tin cậy và phải xét các thay đổi hợp lệ xảy ra sau migration. |

Một migration thường gồm nhiều bước: thay đổi DDL, cập nhật dữ liệu, tạo chỉ mục, chạy kiểm tra, phát hành phiên bản ứng dụng và đồng bộ hệ thống khác. **Không tồn tại một giao dịch ACID bao trùm tất cả các bước này**, nhất là khi đã gửi thông điệp, gọi HTTP hoặc xóa cache.

### Phụ thuộc vào database và loại lệnh SQL

| Môi trường | Điều xảy ra khi có lỗi | Hàm ý phục hồi |
| --- | --- | --- |
| PostgreSQL, DDL được thực thi trong giao dịch hợp lệ | Phần lớn DDL và DML trong **cùng giao dịch chưa commit** có thể bị rollback. | Vẫn phải xác minh không có giao dịch/lô trước đó đã commit. Các thao tác như **CREATE INDEX CONCURRENTLY** không chạy trong transaction block; thao tác lỗi còn có thể để lại index không hợp lệ. |
| MySQL, nhiều loại DDL | DDL thường gây **implicit commit**. Cơ chế *atomic DDL* của MySQL 8 giúp thao tác DDL nhất quán trước sự cố hệ thống, nhưng **không có nghĩa** người vận hành có thể ROLLBACK một DDL đã hoàn tất. | Phải kiểm tra bảng, cột, index thực tế; không suy luận từ kết quả của lệnh ROLLBACK. |
| DML chạy thành nhiều batch với mỗi batch một commit | Batch đang lỗi có thể rollback, các batch trước vẫn giữ nguyên. | Cần checkpoint, câu lệnh có thể chạy lại và phép kiểm tra đối soát. |
| Migration gọi HTTP, đẩy sự kiện, cập nhật cache | Transaction của database không đảo ngược hiệu ứng ngoài database. | Dùng idempotency, outbox, phát sự kiện sửa sai, hoặc hành động bù trừ có kiểm soát. |

**Quy tắc:** trước khi quyết định rollback, phải biết database đang dùng, phiên bản database, loại DDL/DML, ranh giới giao dịch và các bước đã commit. Không suy luận rằng công cụ migration bảo đảm rollback toàn bộ.

## 3. Nhận diện chính xác trạng thái sau lỗi

Có ít nhất bốn kiểu thất bại khác nhau:

- **Thất bại trước khi thay đổi:** migration không qua kiểm tra cấu hình, checksum, quyền hoặc cú pháp. Database có thể chưa đổi.
- **Thất bại trong giao dịch có rollback:** các thao tác trong giao dịch lỗi đã được hủy, nhưng những migration hoặc transaction trước đó vẫn thành công.
- **Thất bại sau một phần đã commit:** DDL không có transaction, batch backfill đã commit hoặc quá trình dừng giữa nhiều changeset. Schema và dữ liệu có thể ở trạng thái trung gian.
- **Migration thành công về kỹ thuật nhưng sai ngữ nghĩa:** câu SQL chạy hết, công cụ ghi nhận thành công, song ánh xạ dữ liệu sai hoặc phiên bản ứng dụng mới không tương thích. Đây cũng là sự cố migration dù không có lỗi SQL.

### Đọc trạng thái công cụ migration

Với **Flyway**, xem log chạy migration, danh sách version và trạng thái qua lệnh:

~~~bash
flyway info
~~~

Nếu có quyền đọc bảng lịch sử tương ứng, có thể truy vấn:

~~~sql
SELECT installed_rank, version, description, success, installed_on
FROM flyway_schema_history
ORDER BY installed_rank DESC;
~~~

Tên schema/table lịch sử có thể đã được cấu hình khác mặc định. Ở những database hỗ trợ transactional DDL, migration thất bại và được rollback có thể **không tạo** bản ghi thất bại trong bảng lịch sử; thiếu dòng thất bại không phải bằng chứng mọi thứ đã an toàn.

Với **Liquibase**, xem log thay đổi, các changeset đã chạy trong bảng **DATABASECHANGELOG** và trạng thái khóa trong **DATABASECHANGELOGLOCK**. Mỗi changeset có thể có ranh giới transaction riêng; nhiều changeset trong một đợt cập nhật không mặc nhiên nằm trong một transaction duy nhất.

**Không thực hiện ngay** Flyway **repair**, Liquibase **changelogSync**, chỉnh tay bảng lịch sử hoặc mở khóa bằng mọi giá. Các thao tác liên quan metadata chỉ an toàn khi đã xác minh tác động thực tế. Chẳng hạn, **flyway repair** sửa thông tin lịch sử/checksum trong những tình huống được hỗ trợ, nhưng **không hoàn tác** SQL, tạo lại cột bị xóa hay khôi phục dữ liệu sai.

### Đối chiếu với trạng thái database thật

Thực hiện truy vấn chỉ đọc để xác minh:

1. Bảng/cột/index/constraint nào đã tồn tại và có hợp lệ không.
2. Số hàng được xử lý, số hàng còn thiếu, số hàng vi phạm bất biến nghiệp vụ.
3. Migration hoặc batch cuối đã commit; có instance nào vẫn chạy migration hoặc cập nhật dữ liệu không.
4. Có bản backup, log giao dịch/PITR, audit log, event log hoặc dữ liệu nguồn đủ để phục hồi không.
5. API, job nền và consumer đang dùng phiên bản contract nào; có dữ liệu mới phát sinh trong lúc migration dở dang không.

Nên lưu lại thời điểm lỗi, version ứng dụng, version migration, SQL error/SQLState, log của job và các truy vấn đối soát. Lỗi như **duplicate key**, **NOT NULL violation**, **lock timeout**, **checksum mismatch** và **disk full** dẫn đến các cách khắc phục khác nhau.

## 4. Quy trình xử lý sự cố theo thứ tự an toàn

~~~mermaid
flowchart TD
    A[Migration báo lỗi hoặc dữ liệu kiểm tra không đạt] --> B[Khoanh vùng phiên bản và dừng job ghi đang gây lỗi]
    B --> C[Chụp trạng thái: log, lịch sử, schema, dữ liệu, backup]
    C --> D{Thay đổi đã commit?}
    D -->|Chưa| E[Sửa nguyên nhân và kiểm tra lại migration]
    D -->|Một phần hoặc toàn bộ| F{Có thể sửa tiến mà giữ đúng dữ liệu?}
    F -->|Có| G[Migration bổ sung và backfill idempotent]
    F -->|Không| H[Khôi phục chọn lọc từ backup/PITR hoặc bù trừ]
    E --> I[Đối soát bất biến và chạy thử]
    G --> I
    H --> I
    I --> J[Kiểm tra tương thích ứng dụng và cho chạy lại theo pha]
~~~

**Bước 1 — Khống chế tác động.** Dừng pipeline migration hoặc worker backfill gây lỗi; xác định cần tạm ngưng thao tác ghi liên quan hay tách traffic không. Nếu hệ thống vẫn phục vụ bình thường với schema mở rộng, ưu tiên duy trì phần dịch vụ an toàn. Không khởi động đồng loạt nhiều instance để chúng tự thử lại cùng một migration lỗi.

**Bước 2 — Bảo toàn chứng cứ và khả năng phục hồi.** Lưu log, trạng thái schema, checkpoint và phạm vi hàng bị ảnh hưởng. Xác minh backup hiện có và, khi phù hợp, tạo snapshot trước khi sửa tiếp. Không xóa migration history hoặc drop bảng lỗi khi chưa hiểu dữ liệu bên trong.

**Bước 3 — Chẩn đoán lỗi gốc.** Phân biệt lỗi script, dữ liệu thực tế không đạt giả định, quyền database, không đủ dung lượng, khóa kéo dài, mất kết nối hay xung đột giữa hai phiên bản ứng dụng. Chỉ sửa điều kiện gây lỗi; không bỏ qua constraint để “cho migration xanh” nếu constraint bảo vệ dữ liệu đúng.

**Bước 4 — Chọn phương án phục hồi.**

| Kết quả kiểm tra | Hướng xử lý thường phù hợp |
| --- | --- |
| Chưa thay đổi gì; transaction đã rollback đầy đủ | Sửa migration chưa được áp dụng, chạy lại sau khi thử nghiệm. |
| Thêm cột thành công; backfill còn thiếu và cột cũ còn nguyên | Hoàn thiện dữ liệu bằng batch idempotent; giữ ứng dụng tương thích trong thời gian chuyển đổi. |
| Sai mapping đã ghi đè dữ liệu cũ, nhưng còn audit/backup đủ tin cậy | Phục hồi có đối soát theo hàng hoặc viết migration sửa tiến từ nguồn đúng. |
| Đã xóa cột/bảng hoặc chuyển đổi làm mất thông tin gốc | Đánh giá backup/PITR và các ghi mới sau thời điểm lỗi; có thể không phục hồi chính xác nếu thiếu nguồn gốc. |
| Công cụ ghi failed migration sau khi DDL đã commit | Sửa trạng thái schema/dữ liệu trước; chỉ sau đó mới xử lý metadata bằng cơ chế chính thức của công cụ. |

**Bước 5 — Xác minh và mở lại có kiểm soát.** Chạy đối soát dữ liệu, migration validation, kiểm thử các đường đọc/ghi quan trọng, health check và kiểm thử tương thích producer/consumer. Theo dõi lỗi ứng dụng, độ trễ SQL, queue lag và số bản ghi chưa di chuyển. Ghi lại nguyên nhân và thao tác khôi phục đã thực hiện.

## 5. Ví dụ: migration đơn hàng dừng giữa quá trình backfill

Giả sử bảng **orders** hiện có:

- **id**: khóa chính số nguyên.
- **status_text**: giá trị cũ là **new**, **paid**, **cancelled**.
- Ứng dụng mới cần **status_code** với giá trị **NEW**, **PAID**, **CANCELLED**.
- Trong dữ liệu thực tế còn một số hàng có trạng thái **refund_pending** chưa được đặc tả.

Làm việc theo chiến lược **expand → migrate → contract** để tách thay đổi tương thích khỏi việc xóa dữ liệu.

### Pha A — Expand: thêm cấu trúc, chưa ép sử dụng

Ví dụ migration Flyway **V41__add_order_status_code.sql** trên PostgreSQL:

~~~sql
ALTER TABLE orders
  ADD COLUMN status_code VARCHAR(20);
~~~

Sau bước này, mã cũ vẫn đọc **status_text**. Triển khai phiên bản ứng dụng Spring Boot biết cả hai cột: tạm thời đọc cột cũ, ghi đồng thời giá trị cũ và giá trị mới trong **cùng transaction database**. Trong quá trình rolling deployment, cần tính đến các instance cũ vẫn chỉ ghi cột cũ.

### Pha B — Migrate: cập nhật theo lô và có thể chạy lại

Ví dụ một batch xử lý ID trong khoảng **100001–110000**:

~~~sql
BEGIN;

UPDATE orders
SET status_code = CASE status_text
    WHEN 'new'       THEN 'NEW'
    WHEN 'paid'      THEN 'PAID'
    WHEN 'cancelled' THEN 'CANCELLED'
  END
WHERE id >= 100001
  AND id < 110001
  AND status_code IS NULL
  AND status_text IN ('new', 'paid', 'cancelled');

COMMIT;
~~~

Điều kiện **status_code IS NULL** giúp batch chạy lại mà không ghi đè những giá trị đã được ứng dụng mới cập nhật. Mỗi lô cần ghi nhận khoảng ID/checkpoint **sau khi commit**; checkpoint chỉ phục vụ tiến độ, không thay cho kiểm tra trạng thái từng hàng. Nếu quy trình dùng worker đồng thời, cần chia vùng ID hoặc khóa hàng thích hợp, giới hạn tải và theo dõi deadlock/lock timeout.

Lưu ý: mã cập nhật này **cố ý không tự suy diễn** ý nghĩa của **refund_pending**. Sau nhiều batch, truy vấn kiểm tra phát hiện hàng chưa được ánh xạ:

~~~sql
SELECT status_text, COUNT(*) AS remaining_rows
FROM orders
WHERE status_code IS NULL
GROUP BY status_text
ORDER BY remaining_rows DESC;
~~~

Chỉ thêm ánh xạ sau khi xác nhận quy tắc nghiệp vụ. Nếu hàng **refund_pending** cần trạng thái **REFUND_PENDING**, cập nhật contract, code và script backfill phù hợp rồi mới chạy tiếp. Nếu dữ liệu cũ sai, phải sửa từ nguồn có thẩm quyền, tránh sửa “cho khớp” bằng giá trị mặc định không chính xác.

Sau khi xử lý mọi giá trị, đối soát cả trường hợp đã điền **status_code** nhưng điền sai:

~~~sql
SELECT COUNT(*) AS inconsistent_rows
FROM orders
WHERE status_text IS NULL
   OR status_text NOT IN ('new', 'paid', 'cancelled', 'refund_pending')
   OR status_code IS DISTINCT FROM CASE status_text
       WHEN 'new'            THEN 'NEW'
       WHEN 'paid'           THEN 'PAID'
       WHEN 'cancelled'      THEN 'CANCELLED'
       WHEN 'refund_pending' THEN 'REFUND_PENDING'
       ELSE NULL
     END;
~~~

Truy vấn dùng cú pháp **IS DISTINCT FROM** của PostgreSQL để so sánh an toàn với **NULL**. Kết quả mong đợi là **0**, trong điều kiện quy tắc ánh xạ này phản ánh đúng nghiệp vụ. Kiểm tra phải được lặp lại khi các instance cũ ngừng ghi và trước khi chuyển đọc sang cột mới.

### Pha C — Contract: chỉ ràng buộc và xóa cột cũ khi đã an toàn

Khi mọi writer đều ghi **status_code**, số hàng bất nhất bằng 0 và các consumer tương thích, có thể bổ sung constraint ở một migration riêng. Ví dụ trên PostgreSQL:

~~~sql
ALTER TABLE orders
  ADD CONSTRAINT orders_status_code_required
  CHECK (status_code IS NOT NULL) NOT VALID;

ALTER TABLE orders
  VALIDATE CONSTRAINT orders_status_code_required;
~~~

Constraint **NOT VALID** kiểm tra các hàng lịch sử sau, nhưng bắt đầu áp dụng cho thao tác ghi mới; do đó không thêm khi còn writer cũ chỉ ghi **status_text**. Cần kiểm tra đặc điểm khóa và thời gian thực thi với dữ liệu thực tế. Chỉ xóa **status_text** trong một đợt phát hành sau, khi không còn ứng dụng, báo cáo, consumer hay job nào phụ thuộc vào nó và đã đủ thời gian quan sát.

### Nếu lỗi xảy ra ở 60% tiến độ thì sao?

Giả sử 600.000 hàng đã commit, batch kế tiếp thất bại. Lúc này:

1. Giao dịch của batch lỗi có thể rollback, nhưng 600.000 hàng đã commit vẫn giữ **status_code**.
2. Không cần “undo” 600.000 hàng nếu cột mới hợp lệ, cột cũ còn đủ dữ liệu và việc chuyển đổi đang ở pha tương thích.
3. Xác định hàng chưa xử lý, bổ sung ánh xạ được phê duyệt, chạy lại các lô một cách idempotent.
4. Nếu sai mapping đã ghi vào 600.000 hàng, lệnh **WHERE status_code IS NULL** sẽ không tự sửa chúng. Cần một migration hiệu chỉnh có điều kiện dựa trên dữ liệu gốc/audit, kiểm tra ảnh hưởng đến các cập nhật hợp lệ phát sinh sau đó, rồi đối soát lại.

Điểm then chốt là **“chạy lại được” và “sửa sai được” là hai thuộc tính khác nhau**. Idempotency hạn chế thay đổi lặp, còn phục hồi dữ liệu sai cần biết trạng thái đúng.

## 6. Vì sao không thể đơn giản đảo chiều migration?

| Thay đổi đã thực hiện | Có thể đảo bằng SQL ngược không? | Rủi ro cần xét |
| --- | --- | --- |
| Thêm cột mới chưa ai ghi dữ liệu | Thường có thể DROP cột nếu đã xác minh không còn phụ thuộc. | Mất dữ liệu mới nếu có writer đã bắt đầu dùng cột. |
| Đổi tên cột | Có thể đổi lại tên trong một số trường hợp. | Ứng dụng hoặc truy vấn đang chạy có thể dùng tên mới; không giải quyết tương thích rolling deployment. |
| Đổi kiểu dữ liệu từ chuỗi sang số | Chỉ khi ánh xạ ngược xác định và không mất thông tin. | Số 00123 và 123 có thể trở thành cùng giá trị; định dạng ban đầu đã mất. |
| Gộp hai trường thành một, chuẩn hóa chuỗi, làm tròn số | Thường không thể dựng lại chính xác từ kết quả. | Hàm biến đổi nhiều-một; cần dữ liệu gốc, audit hoặc backup. |
| Xóa cột, DROP/TRUNCATE bảng | Không thể phục hồi nội dung chỉ bằng cách tạo lại schema. | Dữ liệu cần lấy từ bản sao lưu, event log hoặc nguồn chính thức khác. |
| Gửi thông điệp hoặc gọi dịch vụ ngoài | Không có SQL ROLLBACK cho hệ thống ngoài. | Consumer có thể đã xử lý, gửi email, trừ tồn kho hoặc gọi thanh toán. |

Một script rollback kiểu **DROP COLUMN status_code** có thể chạy thành công về cú pháp nhưng vẫn là một quyết định sai nếu ứng dụng đã ghi đơn hàng mới chỉ tồn tại ở cột đó.

**Khôi phục toàn database về thời điểm trước migration** cũng có giới hạn: các đơn hàng hoặc giao dịch hợp lệ sau thời điểm khôi phục có nguy cơ bị mất. Với hệ thống đang vận hành, thường nên phục hồi backup/PITR vào **database riêng**, đối chiếu theo khóa nghiệp vụ rồi sửa chọn lọc, thay vì lập tức ghi đè production. Quyết định cuối cùng phụ thuộc RPO/RTO và tính toàn vẹn nghiệp vụ.

## 7. Thiết kế migration có thể phục hồi

### 7.1. Đặt bất biến và phép đối soát trước khi chạy

Một migration tốt nêu rõ:

- **Tiền điều kiện:** bảng/cột tồn tại; tập giá trị cũ có thể xử lý; tài khoản migration đủ quyền; dung lượng trống và giới hạn khóa phù hợp.
- **Bất biến:** mỗi đơn hàng giữ nguyên ID, chủ sở hữu, số tiền; trạng thái mới có cùng ý nghĩa nghiệp vụ; số lượng bản ghi không thay đổi nếu chỉ backfill.
- **Hậu điều kiện:** không còn hàng chưa ánh xạ, không có xung đột cũ/mới, constraint hợp lệ, API đọc/ghi bình thường.
- **Điểm dừng:** ngừng migration nếu phát hiện giá trị chưa biết, lỗi ánh xạ, tăng bất thường về thời gian chờ khóa hoặc chênh lệch số hàng.

Không chỉ kiểm tra “SQL trả exit code 0”; kiểm tra **nội dung dữ liệu** sau từng pha và sau khi chuyển traffic.

### 7.2. Làm backfill theo batch, có checkpoint và idempotency

Tránh transaction dài hàng giờ giữ khóa, tăng WAL/binlog và làm khó phục hồi. Chia dữ liệu thành lô phù hợp, commit từng lô, ghi tiến độ, có thể tiếp tục từ hàng còn thiếu. Checkpoint nên gắn với version migration và phạm vi công việc, tránh nhầm một lô đã xử lý với một lô đã xử lý **đúng**.

Lệnh backfill nên dựa trên khóa ổn định và điều kiện xác định, không dựa vào số lần chạy. Có thể dùng khóa hàng, chia partition/range hoặc **FOR UPDATE SKIP LOCKED** nếu engine hỗ trợ và cách xử lý thật sự cần nhiều worker. Theo dõi tốc độ xử lý, lỗi mỗi batch và độ trễ các truy vấn quan trọng.

Trong Spring Boot, đặt transaction bao quanh **phần công việc nhỏ và nguyên tử** của một batch. Annotation **@Transactional** chỉ có hiệu lực trong phạm vi transaction do Spring quản lý và tài nguyên tham gia transaction đó; nó không làm lệnh DDL không hỗ trợ transaction trở nên có thể rollback và không hoàn tác side effect từ HTTP/broker.

### 7.3. Tách schema khỏi chuyển đổi dữ liệu dài hạn

Một migration versioned thường thích hợp với thay đổi schema nhỏ, nhanh, có thể dự đoán. Đối với hàng triệu bản ghi, nên cân nhắc job backfill được quản lý riêng, có tiến độ, khả năng dừng/tiếp tục và giám sát. Không gắn một bước backfill chạy nhiều giờ vào thời điểm mọi instance Spring Boot bắt đầu khởi động.

Nếu tổ chức dùng Flyway/Liquibase lúc startup, bảo đảm cơ chế khóa migration và cấu hình deploy được kiểm soát. Với quy trình lớn, có thể chạy migration trong **một job/pipeline chuyên trách**, sau đó khởi động các instance ứng dụng với schema đã sẵn sàng. Trong trường hợp đó cần cấu hình tránh việc ứng dụng tự chạy migration trùng.

### 7.4. Triển khai phiên bản tương thích hai chiều

Trong giai đoạn rolling deployment, mã cũ và mới có thể cùng chạy. Vì vậy:

1. **Expand:** thêm cột/bảng hoặc event field mới mà client/consumer cũ vẫn hoạt động.
2. **Migrate:** cập nhật writer, triển khai dual-write có kiểm soát hoặc chuyển đổi qua adapter; chạy backfill và đối soát.
3. **Switch:** đổi đường đọc/feature flag khi dữ liệu và consumer đã tương thích, có thể quay lại đọc dữ liệu cũ nếu còn đầy đủ và nhất quán.
4. **Contract:** bỏ đường tương thích, cột cũ hoặc event field cũ trong đợt triển khai sau.

Nếu dùng cache, cần xét key/version/TTL và invalidation để dữ liệu cũ không bị diễn giải theo schema mới. Nếu phát sự kiện, nên version contract, giữ consumer đọc được cả dạng cũ và mới trong giai đoạn chuyển đổi, đồng thời dùng **outbox pattern** khi cần đảm bảo việc lưu database và phát sự kiện không bị tách rời sau sự cố. Outbox vẫn cần consumer idempotent vì sự kiện có thể được gửi lặp.

### 7.5. Có phương án phục hồi trước thay đổi phá hủy

Trước **DROP**, **TRUNCATE**, gộp trường hoặc thay kiểu gây mất thông tin, xác nhận:

- Có backup/PITR đã thử khôi phục, biết thời điểm khôi phục và ảnh hưởng tới dữ liệu mới.
- Có khóa đối chiếu, audit history hoặc bản chụp dữ liệu gốc nếu cần sửa chọn lọc.
- Đã ngừng mọi đường ghi/đọc phụ thuộc schema cũ; có phương án bù trừ khi dữ liệu đã lan ra hệ thống khác.
- Đã xác định ai quyết định dừng migration, chuyển chế độ bảo trì hoặc mở traffic trở lại.

## 8. Dùng Flyway và Liquibase trong Spring Boot đúng phạm vi

Ví dụ cấu hình khi ứng dụng cho phép Flyway chạy lúc startup:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

**ddl-auto: validate** giúp kiểm tra entity mapping phù hợp với schema kỳ vọng thay vì để Hibernate tự thay đổi cấu trúc. Khi dùng Liquibase làm công cụ chính, cấu hình tương ứng cho Liquibase và tránh để hai bộ công cụ đồng thời quản lý cùng schema ngoài ý muốn.

**Với Flyway:**

- Kiểm tra version, checksum và trạng thái migration qua **info/validate**. Không sửa nội dung migration versioned **đã chạy thành công** trên các môi trường; hãy thêm migration hiệu chỉnh mới.
- Nếu môi trường báo failed migration, kiểm tra SQL đã commit và schema thực trước khi dùng **repair**. Việc sửa lịch sử chỉ giải quyết metadata, không giải quyết dữ liệu một phần.
- Nếu migration gồm statement không thể chạy trong transaction, tách riêng và cấu hình execution phù hợp database. Không xem hỗ trợ transaction là thuộc tính cố định của mọi script.

**Với Liquibase:**

- Dùng changeset nhỏ, precondition phù hợp và chú ý **runInTransaction** cùng khả năng transaction của database/statement. Rollback tự sinh không khả dụng hoặc không đủ an toàn cho mọi kiểu thay đổi; thao tác dữ liệu phá hủy cần kịch bản khôi phục được thiết kế riêng.
- Kiểm tra **DATABASECHANGELOG**, trạng thái lock và kết quả các changeset đã chạy. Chỉ giải phóng lock còn sót sau khi chắc chắn không có quá trình Liquibase nào đang hoạt động.
- Không dùng **changelogSync** để đánh dấu changeset như đã chạy chỉ nhằm vượt qua lỗi mà chưa kiểm chứng schema, dữ liệu và lý do bỏ qua.

**Với cả hai:** không gọi “thành công” chỉ vì migration history được chỉnh cho sạch. Định nghĩa hoàn tất phải bao gồm đối soát dữ liệu, tương thích ứng dụng và tín hiệu vận hành.

## 9. Kiểm thử trước khi chạy production

Một phương án kiểm thử có ích gồm các trường hợp đại diện cho dữ liệu và lỗi thực tế:

| Kịch bản | Kết quả cần kiểm chứng |
| --- | --- |
| Database sạch hoặc đúng phiên bản cũ; chạy migration bình thường | Schema/version đúng; dữ liệu đạt bất biến; ứng dụng khởi động và đọc/ghi được. |
| Có dữ liệu ngoại lệ, null, trùng khóa, quá dài hoặc trạng thái chưa hỗ trợ | Migration dừng có thông báo đủ chẩn đoán; không làm hỏng các hàng đã hợp lệ. |
| Hủy job sau khi vài batch đã commit, rồi khởi động lại | Không nhân đôi, mất hoặc ghi đè dữ liệu; tiến độ và đối soát cuối cùng đúng. |
| Lỗi constraint/lock timeout/disk pressure ở bước bất kỳ | Biết ranh giới commit, xác minh được trạng thái trung gian, có thao tác phục hồi rõ ràng. |
| Hai phiên bản ứng dụng cùng hoạt động | Writer và reader cũ/mới vẫn hiểu dữ liệu; chuyển cờ đọc và rollback ứng dụng không làm mất thông tin. |
| Message bị gửi lại, cache còn giá trị cũ, consumer chậm | Consumer idempotent, contract tương thích và có chỉ số để phát hiện lệch dữ liệu. |
| Cần phục hồi từ backup/PITR | Thử restore vào môi trường riêng; đo được thời gian và kiểm chứng có thể ghép lại các ghi hợp lệ. |

Khi chạy với dữ liệu gần production, nên kiểm tra thêm kích thước bảng/index, thời gian giữ khóa, replication lag, WAL/binlog, chi phí I/O và giới hạn thời gian của pipeline. Không nên dùng duy nhất bộ dữ liệu kiểm thử chỉ có vài hàng “đẹp”.

## 10. Runbook ngắn khi migration báo FAILED

1. **Ghi nhận:** migration/version, môi trường, thời điểm, SQLState, log, bản ứng dụng và các instance còn hoạt động.
2. **Khoanh vùng:** tạm dừng tác nhân gây lỗi và xác định cần hạn chế thao tác ghi nào để tránh làm sai dữ liệu thêm.
3. **Xác minh:** đọc lịch sử Flyway/Liquibase, schema thực, batch đã commit, hàng bất nhất, trạng thái backup/PITR.
4. **Chọn khắc phục:** retry sau rollback thật; sửa tiến nếu dữ liệu vẫn đầy đủ; phục hồi chọn lọc/bù trừ khi dữ liệu đã mất hoặc tác động ra hệ thống ngoài.
5. **Thực thi có kiểm soát:** chạy trên staging với trạng thái tương đương, lập checkpoint, theo dõi lỗi và có điều kiện dừng.
6. **Đối soát và mở lại:** kiểm tra số hàng, bất biến, API/consumer, cache, lag và health check; cập nhật hồ sơ sự cố.

### Những thao tác nên tránh

- Chạy đi chạy lại migration hoặc restart toàn cụm mà chưa biết statement nào đã commit.
- Chạy **repair**, sửa bảng lịch sử hoặc gỡ constraint chỉ để xóa cảnh báo.
- Đổi/xóa migration đã được áp dụng ở môi trường khác khiến checksum và lịch sử phân kỳ.
- ROLLBACK hoặc deploy lại mã cũ rồi giả định dữ liệu cũng đã quay lại.
- DROP cột cũ ngay khi một batch backfill báo thành công, khi writer/consumer cũ vẫn hoạt động.
- Restore đè toàn bộ production mà chưa tính các giao dịch hợp lệ phát sinh sau bản backup.

## 11. Ghi nhớ

**Migration thất bại là bài toán xác định trạng thái thực và giữ tính đúng đắn của dữ liệu.** Công cụ quản lý version giúp biết script nào được dự kiến chạy, nhưng không tự bảo đảm có thể đảo ngược mọi thao tác. Thiết kế migration an toàn phải dựa trên dữ liệu gốc còn kiểm chứng được, các pha tương thích ứng dụng, batch idempotent, checkpoint, quan sát vận hành và kế hoạch khôi phục trước khi thực hiện thay đổi không thể đảo chiều.
