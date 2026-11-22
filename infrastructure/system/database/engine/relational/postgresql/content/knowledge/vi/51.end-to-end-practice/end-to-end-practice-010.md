# Thực hiện migration tương thích khi ứng dụng vẫn hoạt động

Migration database khi ứng dụng vẫn phục vụ người dùng là quá trình thay đổi schema và dữ liệu trong lúc nhiều phiên bản ứng dụng có thể cùng tồn tại. Trong một đợt rolling deployment, một số Pod còn chạy phiên bản cũ, Pod khác đã chạy phiên bản mới; worker, cron job, consumer hoặc service nền cũng có thể tiếp tục truy cập database. Vì vậy, một thay đổi schema chỉ an toàn khi mọi phiên bản ứng dụng đang hoạt động đều có thể làm việc với trạng thái database trong suốt quá trình chuyển đổi.

PostgreSQL hỗ trợ nhiều thao tác DDL có tính giao dịch, nhưng điều đó không có nghĩa mọi migration đều không gây gián đoạn. Một câu lệnh có thể cần khóa mạnh, chờ transaction dài hoặc làm tăng I/O. Backfill lớn có thể cạnh tranh tài nguyên với truy vấn production. Migration tương thích cần phối hợp thứ tự thay đổi schema, phát hành ứng dụng, chuyển dữ liệu, xác minh và dọn schema cũ qua nhiều giai đoạn.

Mẫu triển khai phổ biến là **expand and contract**: mở rộng schema để phiên bản cũ và mới cùng hoạt động, chuyển ứng dụng và dữ liệu theo từng bước, rồi chỉ loại bỏ cấu trúc cũ sau khi chắc chắn không còn thành phần nào phụ thuộc vào nó.

## 1. Vì sao migration trực tiếp có thể làm ứng dụng ngừng hoạt động?

Giả sử ứng dụng đang đọc và ghi cột **customers.full_name**. Một bản phát hành mới muốn đổi tên cột thành **display_name**.

Nếu migration chạy:

~~~sql
ALTER TABLE customers RENAME COLUMN full_name TO display_name;
~~~

mọi phiên bản ứng dụng vẫn truy cập **full_name** sẽ lỗi ngay sau khi rename. Trong rolling deployment, Pod cũ chưa bị thay thế hết nên lỗi có thể xuất hiện ngay trong thời gian rollout. Rollback ứng dụng về phiên bản cũ cũng không giải quyết được nếu schema vẫn chỉ có cột mới.

Các thay đổi dễ tạo ra tình huống tương tự:

- Xóa hoặc đổi tên cột, bảng, index, enum value hoặc function mà code cũ vẫn dùng.
- Đổi kiểu dữ liệu khiến câu lệnh hoặc dữ liệu cũ không còn hợp lệ.
- Thêm cột NOT NULL nhưng không có giá trị cho các hàng hiện tại hoặc cho phiên bản ứng dụng cũ.
- Thêm constraint ngay lập tức trong khi dữ liệu hiện có chưa thỏa điều kiện.
- Tạo index theo cách giữ khóa quá lâu trên bảng đang có tải.
- Chuyển dữ liệu trong một transaction rất lớn, giữ row lock lâu hoặc tạo lượng WAL vượt khả năng lưu trữ.
- Triển khai ứng dụng mới trước khi schema cần thiết đã sẵn sàng.

Một migration an toàn phải xét cả **schema trước và sau migration**, **các phiên bản ứng dụng cùng hoạt động**, **transaction đang mở**, **các job nền** và **khả năng rollback**.

## 2. Tương thích ngược và tương thích xuôi

Hai khái niệm này mô tả hai chiều tương tác:

- **Backward compatibility:** schema mới vẫn hỗ trợ ứng dụng cũ. Ví dụ, thêm một cột mới thường không làm hỏng code cũ nếu cột cũ vẫn còn.
- **Forward compatibility:** ứng dụng mới có thể chạy với schema cũ hơn trong một giai đoạn triển khai. Điều này hữu ích khi ứng dụng được phát hành trước hoặc song song với migration schema, nhưng không phải lúc nào cũng cần đạt được.

Trong rolling deployment, mục tiêu quan trọng nhất là bảo đảm mọi phiên bản ứng dụng đang chạy tương thích với schema tại thời điểm đó.

| Ứng dụng | Schema cũ | Schema đã expand | Schema đã contract |
|---|---|---|---|
| Phiên bản cũ | Hoạt động | Phải tiếp tục hoạt động | Thường không còn tương thích |
| Phiên bản chuyển tiếp (bridge) | Chỉ khi được thiết kế để chịu schema cũ | Hoạt động | Có thể không còn tương thích |
| Phiên bản mới | Chỉ khi được thiết kế để chịu schema cũ | Hoạt động | Hoạt động |

Bảng này cho thấy vì sao cần trì hoãn contract. Sau khi xóa cột cũ, ứng dụng cũ không thể quay lại sử dụng schema đó. Nếu cần rollback binary, schema phải tiếp tục giữ cấu trúc cũ trong suốt rollback window.

## 3. Mẫu Expand and Contract

Một thay đổi được chia thành hai giai đoạn lớn:

**Expand:** thêm cấu trúc mới theo cách không phá vỡ code hiện tại. Có thể thêm cột nullable, bảng mới, index mới, constraint ở trạng thái chưa validate hoặc API song song. Ứng dụng cũ vẫn hoạt động.

**Contract:** sau khi ứng dụng mới đã sử dụng cấu trúc mới, mọi phiên bản cũ đã được loại bỏ, dữ liệu đã được xác minh và rollback window đã kết thúc, mới ngừng ghi rồi xóa cấu trúc cũ.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Schema cũ + ứng dụng cũ] --> B[Expand: thêm cấu trúc mới]
    B --> C[Triển khai ứng dụng bridge]
    C --> D[Backfill và đồng bộ dữ liệu]
    D --> E[Xác minh dữ liệu mới]
    E --> F[Chuyển ứng dụng sang đọc cấu trúc mới]
    F --> G[Ngừng phụ thuộc cấu trúc cũ]
    G --> H[Contract: xóa cấu trúc cũ ở release sau]
~~~

Mỗi bước cần một trạng thái có thể vận hành được. Nếu triển khai dừng giữa chừng, hệ thống vẫn phải phục vụ traffic bằng schema và phiên bản ứng dụng hiện tại. Không gộp expand, backfill, switch và contract thành một migration duy nhất.

### Quy tắc thực hành

- Thêm trước, xóa sau.
- Đọc trước từ cấu trúc cũ, rồi mới chuyển đọc sang cấu trúc mới.
- Bắt đầu dual-write hoặc đồng bộ trước khi backfill.
- Backfill theo batch nhỏ, có thể tiếp tục sau khi bị gián đoạn.
- Xác minh dữ liệu trước khi đổi nguồn đọc.
- Giữ khả năng rollback trong thời hạn đã thống nhất.
- Chỉ contract khi mọi ứng dụng, worker, báo cáo và quy trình vận hành đã ngừng dùng cấu trúc cũ.

## 4. Ví dụ xuyên suốt: chuyển cột full_name sang display_name

Giả sử bảng đang có:

~~~sql
CREATE TABLE customers (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
~~~

Ứng dụng cũ chỉ đọc và ghi **full_name**. Yêu cầu mới muốn dùng **display_name**. Vì đây là thay đổi cùng ý nghĩa dữ liệu, có thể chuyển theo các giai đoạn sau.

### Giai đoạn 1: Expand schema

Thêm cột mới ở trạng thái nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name text;
~~~

Đây là thay đổi cộng thêm, nên code cũ vẫn có thể truy cập **full_name**. Việc thêm cột vẫn cần khóa metadata trên bảng; dù thường diễn ra nhanh, lệnh có thể phải chờ transaction đang giữ lock. Chọn thời điểm phù hợp và đặt lock_timeout để migration không chờ vô hạn.

~~~sql
SET lock_timeout = '2s';

ALTER TABLE customers
ADD COLUMN display_name text;

RESET lock_timeout;
~~~

Đoạn trên minh họa một session chạy migration. Nếu lệnh lỗi do timeout, transaction có thể ở trạng thái aborted nếu đang trong transaction block; cần rollback trước khi chạy lệnh tiếp theo. Migration runner nên quản lý trạng thái lỗi rõ ràng.

### Giai đoạn 2: Bảo đảm ghi mới được đồng bộ

Trong lúc rolling deployment, Pod cũ chỉ ghi **full_name**. Nếu backfill đã đi qua một hàng rồi Pod cũ cập nhật hàng đó, **display_name** có thể trở lại lỗi thời. Cần bảo đảm mọi lần ghi cũ đều cập nhật cột mới trong giai đoạn chuyển tiếp.

Có thể dùng một trigger tạm thời để giữ cột mới đồng bộ với cột cũ:

~~~sql
CREATE FUNCTION sync_customer_display_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.display_name := NEW.full_name;
    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_display_name
BEFORE INSERT OR UPDATE OF full_name
ON customers
FOR EACH ROW
EXECUTE FUNCTION sync_customer_display_name();
~~~

Đây là ví dụ cho trường hợp hai cột có cùng ngữ nghĩa và cột cũ vẫn là nguồn dữ liệu chuẩn trong giai đoạn chuyển tiếp. Trigger làm cho insert mới và update từ ứng dụng cũ cập nhật **display_name**.

Một phiên bản bridge của ứng dụng có thể tiếp tục ghi **full_name** và **display_name** trong cùng transaction, nhưng trigger ở ví dụ này vẫn lấy **full_name** làm nguồn chuẩn. Không dùng mẫu trigger một chiều này nếu hai cột có quy tắc biến đổi khác nhau hoặc phiên bản mới chỉ ghi cột mới. Với thay đổi phức tạp, cần thiết kế đồng bộ hai chiều có quy tắc xung đột rõ ràng hoặc chuyển đổi nguồn ghi theo một giao thức riêng.

Trigger là logic production và có chi phí trên mỗi lần ghi. Cần theo dõi lỗi trigger, latency và deadlock; ghi rõ trigger thuộc migration nào và điều kiện gỡ bỏ.

### Giai đoạn 3: Backfill dữ liệu cũ theo batch

Các hàng đã tồn tại trước khi thêm trigger có thể có **display_name** là NULL. Không cập nhật toàn bộ bảng trong một transaction dài nếu bảng lớn. Chia thành batch, commit từng batch và có thể tiếp tục sau khi tiến trình bị dừng.

Ví dụ một batch tối đa 1.000 hàng:

~~~sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE display_name IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET display_name = c.full_name
FROM batch
WHERE c.id = batch.id
RETURNING c.id;
~~~

Chạy câu lệnh lặp lại trong các transaction riêng cho đến khi không còn hàng cần xử lý. **SKIP LOCKED** giúp worker bỏ qua hàng đang bị transaction khác khóa; vì vậy, kết quả một batch rỗng không nhất thiết chứng minh toàn bảng đã hoàn tất nếu vẫn còn transaction đang giữ hàng. Cần chạy vòng kiểm tra cuối sau khi các transaction liên quan đã kết thúc.

Backfill cần có các đặc điểm:

- **Idempotent:** chạy lại không làm hỏng dữ liệu đã đúng.
- **Có checkpoint:** ghi nhận tiến độ hoặc dùng điều kiện truy vấn để tiếp tục từ phần còn lại.
- **Có giới hạn tải:** batch size, độ trễ giữa batch và số worker phải phù hợp với tải production.
- **Có thể dừng:** dừng job không để lại transaction khổng lồ hoặc trạng thái nửa vời không kiểm soát.
- **Có quan sát:** log số hàng cập nhật, tốc độ, lỗi, WAL generation, replica lag và thời gian truy vấn.

Không tăng batch size chỉ để hoàn thành nhanh. Backfill có thể làm tăng WAL, replication lag, I/O, cache churn và cạnh tranh với autovacuum. Chọn batch nhỏ ban đầu rồi điều chỉnh dựa trên số liệu.

### Giai đoạn 4: Kiểm tra dữ liệu và tính đầy đủ

Sau backfill, so sánh hai cột:

~~~sql
SELECT
    count(*) FILTER (WHERE display_name IS NULL) AS missing_count,
    count(*) FILTER (
        WHERE display_name IS DISTINCT FROM full_name
    ) AS mismatch_count
FROM customers;
~~~

Với giả định **full_name** luôn có giá trị và hai cột phải giống nhau, cả hai số đếm phải bằng 0. Nếu dữ liệu được chuẩn hóa hoặc chuyển đổi theo quy tắc khác, phép kiểm tra phải so sánh với biểu thức chuyển đổi tương ứng thay vì so sánh trực tiếp.

Có thể lấy mẫu các hàng để xem nội dung:

~~~sql
SELECT id, full_name, display_name
FROM customers
WHERE display_name IS DISTINCT FROM full_name
ORDER BY id
LIMIT 100;
~~~

Không chuyển ứng dụng sang đọc cột mới chỉ vì backfill job báo hoàn tất. Cần xác minh dữ liệu, kiểm tra mọi đường ghi và xử lý các hàng bị bỏ qua do lock hoặc lỗi chuyển đổi.

### Giai đoạn 5: Chuyển ứng dụng sang đọc cột mới

Phát hành phiên bản ứng dụng tiếp theo để đọc **display_name**. Trong giai đoạn rollback window, tiếp tục ghi cả cột cũ và cột mới, hoặc duy trì cơ chế đồng bộ đã được kiểm chứng, để binary cũ vẫn có thể hoạt động nếu cần rollback.

Một câu truy vấn đọc mới:

~~~sql
SELECT id, display_name
FROM customers
WHERE id = $1;
~~~

Khi rollout, theo dõi:

- Lỗi truy vấn do thiếu cột hoặc sai quyền.
- Số lượng NULL và mismatch.
- Tỷ lệ request thành công, latency và lỗi nghiệp vụ.
- Số Pod đang chạy phiên bản cũ và mới.
- Worker, cron, consumer hoặc script còn đọc/ghi cột cũ.
- Log trigger và số lần cột cũ được cập nhật.

Không dùng một lần kiểm tra Pod deployment làm bằng chứng duy nhất rằng mọi client đã được nâng cấp. Job định kỳ hoặc service bên ngoài có thể không nằm trong Deployment chính.

### Giai đoạn 6: Contract ở một release riêng

Chỉ khi không còn code nào phụ thuộc vào **full_name**, dữ liệu mới đã được xác minh, rollback window đã đóng và nhóm sở hữu dữ liệu chấp thuận, mới loại bỏ trigger và cột cũ.

~~~sql
DROP TRIGGER customers_sync_display_name ON customers;
DROP FUNCTION sync_customer_display_name();

ALTER TABLE customers
DROP COLUMN full_name;
~~~

Đây là bước phá vỡ tương thích. Không chạy cùng đợt rolling deployment mà vẫn còn phiên bản ứng dụng cũ. Cũng không chạy khi chưa kiểm tra view, function, report, ETL, ad-hoc query và công cụ quản trị có thể phụ thuộc vào cột cũ.

Sau contract, rollback về binary cũ có thể không còn khả thi. Nếu cần quay lại, phải có một kế hoạch forward-fix hoặc khôi phục dữ liệu/schema riêng; không giả định có thể chỉ rollback image.

## 5. Thay đổi kiểu dữ liệu hoặc quy tắc dữ liệu

Thay đổi kiểu dữ liệu có thể cần nhiều bước hơn đổi tên cột. Ví dụ muốn chuyển **amount_text** dạng text sang **amount numeric(12,2)**. Việc cast trực tiếp có thể thất bại nếu có dữ liệu không hợp lệ và có thể khóa hoặc quét bảng lâu.

Mẫu chuyển đổi an toàn:

1. Thêm cột mới có kiểu dữ liệu đích, ban đầu nullable.
2. Phát hành code tương thích để ghi dữ liệu theo quy tắc thống nhất.
3. Backfill giá trị cũ sang kiểu mới theo batch.
4. Ghi nhận và xử lý các giá trị không thể chuyển đổi.
5. Kiểm tra số lượng hàng, tổng hợp và sai lệch.
6. Chuyển đọc sang cột mới.
7. Duy trì ghi tương thích trong rollback window.
8. Xóa cột cũ ở release sau.

Trước khi cast, tìm dữ liệu lỗi:

~~~sql
SELECT id, amount_text
FROM invoices
WHERE amount_text IS NOT NULL
  AND amount_text !~ '^[0-9]+([.][0-9]{1,2})?$'
ORDER BY id
LIMIT 100;
~~~

Regex trên chỉ là ví dụ cho định dạng số thập phân đơn giản; nó không xử lý mọi quy ước dấu âm, dấu phân cách hàng nghìn, locale hoặc số mũ. Quy tắc parse phải phản ánh định dạng dữ liệu thực tế.

Không dùng một phép cast trong migration rồi để cả bảng thất bại khi gặp một hàng không hợp lệ. Hãy phân loại dữ liệu, quyết định cách sửa hoặc cách giữ lại ngoại lệ và ghi nhận số hàng được xử lý.

## 6. Thêm constraint mà không chặn ứng dụng lâu

Thêm constraint ngay lập tức có thể yêu cầu kiểm tra toàn bộ dữ liệu và lấy khóa ảnh hưởng đến truy vấn. PostgreSQL cung cấp một số cơ chế triển khai theo giai đoạn.

Ví dụ thêm kiểm tra **display_name** không NULL nhưng chưa quét dữ liệu cũ ngay khi thêm:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT customers_display_name_not_null
CHECK (display_name IS NOT NULL)
NOT VALID;
~~~

Constraint NOT VALID chưa xác nhận các hàng cũ, nhưng được áp dụng với những hàng mới hoặc hàng bị cập nhật theo quy tắc của constraint. Sau khi backfill và kiểm tra dữ liệu, validate riêng:

~~~sql
ALTER TABLE customers
VALIDATE CONSTRAINT customers_display_name_not_null;
~~~

Sau đó, nếu phiên bản PostgreSQL và trạng thái constraint cho phép, có thể đặt thuộc tính NOT NULL chính thức:

~~~sql
ALTER TABLE customers
ALTER COLUMN display_name SET NOT NULL;
~~~

Một CHECK đã validate có thể giúp PostgreSQL tránh quét lại toàn bộ bảng khi đặt NOT NULL trên các phiên bản hỗ trợ tối ưu đó. Dù vậy, lệnh vẫn cần lock metadata; cần thử trên đúng phiên bản và kích thước dữ liệu. Sau khi NOT NULL đã được thiết lập, constraint CHECK tạm có thể được gỡ nếu không còn mục đích riêng:

~~~sql
ALTER TABLE customers
DROP CONSTRAINT customers_display_name_not_null;
~~~

NOT VALID không áp dụng cho mọi loại constraint. Với foreign key, unique và check, khả năng cũng như thứ tự triển khai khác nhau. Hãy dùng cú pháp đúng với loại constraint và phiên bản PostgreSQL đang chạy.

### Foreign key theo giai đoạn

Có thể thêm foreign key với NOT VALID, sau đó kiểm tra dữ liệu cũ bằng VALIDATE CONSTRAINT:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT order_items_product_fk
FOREIGN KEY (product_id)
REFERENCES products(id)
NOT VALID;

ALTER TABLE order_items
VALIDATE CONSTRAINT order_items_product_fk;
~~~

Trong giai đoạn chưa validate, constraint vẫn được áp dụng cho dữ liệu mới theo semantics của PostgreSQL. Trước khi thêm, cần kiểm tra dữ liệu hiện tại có orphan row không và xác định cách xử lý.

## 7. Tạo index trên bảng đang có tải

Tạo index thông thường có thể chặn thao tác ghi trên bảng trong thời gian build. PostgreSQL hỗ trợ:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_display_name
ON customers(display_name);
~~~

CONCURRENTLY cho phép các thao tác INSERT, UPDATE và DELETE tiếp tục trong phần lớn quá trình tạo index, nhưng build kéo dài hơn và có thêm các pha chờ transaction. Lệnh này **không được chạy bên trong transaction block**. Migration tool cần hỗ trợ một migration riêng không transactional cho lệnh đó.

Nếu tạo index concurrent thất bại, PostgreSQL có thể để lại index không hợp lệ. Kiểm tra trạng thái:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisready,
    indisvalid
FROM pg_index
WHERE indexrelid = 'idx_customers_display_name'::regclass;
~~~

Nếu index không hợp lệ, cần xử lý theo runbook và có thể phải xóa bằng DROP INDEX CONCURRENTLY trước khi tạo lại:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS idx_customers_display_name;
~~~

Lệnh DROP INDEX CONCURRENTLY cũng không chạy trong transaction block. Không xóa index cũ đang được ứng dụng sử dụng trước khi index mới đã sẵn sàng và query plan được kiểm tra.

Sau khi tạo index, xem EXPLAIN (ANALYZE, BUFFERS) trên truy vấn đại diện trong môi trường phù hợp. Index tồn tại không có nghĩa planner sẽ chọn nó hoặc hiệu năng đã tốt hơn. Với bảng lớn, việc build index còn tiêu thụ CPU, I/O và dung lượng tạm; cần theo dõi tải.

## 8. Kiểm soát lock và thời gian chạy DDL

DDL cần lock trên relation. Một lệnh ALTER TABLE có thể phải chờ transaction dài đang truy cập bảng. Khi DDL chờ khóa mạnh, các truy vấn khác đến sau cũng có thể xếp hàng phía sau nó, tạo ra một đợt nghẽn lớn dù lệnh thay đổi schema chưa thực sự chạy.

Dùng lock_timeout để lệnh thất bại sớm nếu không lấy được lock trong khoảng cho phép:

~~~sql
SET lock_timeout = '2s';
ALTER TABLE customers ADD COLUMN display_name text;
RESET lock_timeout;
~~~

Đặt timeout ngắn giúp tránh migration chờ vô hạn trong giờ cao điểm. Khi timeout, ghi nhận lỗi và thử lại ở thời điểm phù hợp; không tăng timeout vô hạn để ép migration chạy. Có thể dùng statement_timeout riêng để giới hạn tổng thời gian câu lệnh, nhưng cần đặt phù hợp với thao tác như validate constraint hoặc tạo index.

Trước migration, kiểm tra transaction dài và session đang giữ lock:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Kiểm tra lock liên quan đến bảng:

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    l.mode,
    l.granted,
    a.xact_start,
    a.query
FROM pg_locks AS l
JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation = 'customers'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
~~~

Không tự động terminate mọi session lâu năm. Một transaction có thể thuộc tác vụ hợp lệ hoặc cần được chủ sở hữu xử lý. Xác định application, câu lệnh và tác động trước khi can thiệp.

## 9. Backfill dữ liệu lớn trong khi production tiếp tục ghi

Backfill là công việc đọc và cập nhật dữ liệu cũ để đưa chúng về định dạng mới. Nó thường là phần tiêu tốn tài nguyên nhất của một migration online.

### Vì sao không nên backfill toàn bảng trong một transaction?

Một transaction lớn có thể:

- Giữ row lock lâu và làm các transaction ứng dụng chờ.
- Sinh lượng WAL lớn, tăng replication lag và áp lực archive.
- Giữ phiên bản tuple cũ, làm vacuum khó thu hồi không gian.
- Tăng thời gian rollback nếu tiến trình thất bại.
- Làm tăng bloat và áp lực I/O.
- Làm replica hoặc backup không theo kịp.

Hãy chia công việc theo primary key hoặc một cursor ổn định, commit từng batch và giới hạn tốc độ. Với bảng có khóa tăng dần, có thể lưu checkpoint last_id của job. Tuy nhiên, phải có lượt quét cuối để bắt những hàng bị bỏ qua hoặc được chèn trong lúc job chạy.

### Theo dõi và điều chỉnh tải

Các chỉ số nên quan sát:

- Số hàng đã xử lý, còn lại và tốc độ hàng/giây.
- Thời gian mỗi batch và số lần retry.
- CPU, IOPS, latency và dung lượng đĩa.
- WAL generation rate, archive backlog và dung lượng pg_wal.
- Replication lag trên từng standby.
- Lock wait, deadlock, autovacuum và bloat.
- Tỷ lệ lỗi của ứng dụng trong cùng thời gian.

Nếu replica lag hoặc latency production vượt ngưỡng, giảm batch size, giảm số worker hoặc tạm dừng backfill. Job phải có thể tiếp tục mà không phải chạy lại từ đầu.

### Tránh ghi đè dữ liệu mới

Backfill có thể chạy đồng thời với ứng dụng. Điều kiện cập nhật phải tránh ghi đè giá trị mới hơn do ứng dụng vừa ghi. Ví dụ dùng điều kiện display_name IS NULL nếu trigger hoặc bridge writer đã đảm bảo các giá trị mới được điền. Nếu logic chuyển đổi cần cập nhật mọi hàng, hãy dùng version/timestamp hoặc một quy tắc compare-and-set để phân biệt dữ liệu cũ và mới.

Không chạy nhiều worker backfill cùng cập nhật một vùng dữ liệu mà không có cơ chế phân chia hoặc SKIP LOCKED. Nhiều worker có thể tăng throughput nhưng cũng tăng contention, WAL và tải storage.

## 10. Dual-write, trigger và chuyển nguồn dữ liệu

Dual-write nghĩa là trong một giai đoạn, ứng dụng ghi cả cấu trúc cũ và mới. Cách này có thể giúp rollback, nhưng cũng tạo thêm rủi ro nếu một trong hai lần ghi thất bại hoặc logic chuyển đổi không giống nhau.

Nếu hai cột cùng nằm trong một PostgreSQL transaction và được cập nhật trong cùng một câu lệnh/transaction, database có thể bảo đảm cả hai thay đổi commit hoặc rollback cùng nhau. Nếu ứng dụng ghi sang hai hệ thống hoặc hai database khác nhau, không có tính nguyên tử mặc định; cần outbox, CDC hoặc cơ chế đồng bộ có khả năng phục hồi.

Các lựa chọn phổ biến:

| Cách đồng bộ | Phù hợp khi | Rủi ro cần quản lý |
|---|---|---|
| Application dual-write | Có thể phát hành bridge version và kiểm soát mọi writer | Mỗi service/job phải dùng cùng quy tắc; lỗi một nhánh ghi cần xử lý |
| Database trigger | Cần bảo vệ trước writer cũ chưa thể nâng cấp đồng thời | Logic ẩn trong database, chi phí ghi, recursion và thứ tự ưu tiên khi hai cột cùng đổi |
| Backfill một lần rồi switch | Không còn writer cũ hoặc dữ liệu không thay đổi trong thời gian chuyển | Ghi đồng thời có thể làm dữ liệu mới bị thiếu hoặc ghi đè |
| CDC/replication pipeline | Chuyển dữ liệu giữa hệ thống hoặc bảng lớn với yêu cầu liên tục | Lag, ordering, duplicate, schema evolution và xử lý lỗi |

Không dual-write vô thời hạn. Xác định nguồn dữ liệu chuẩn trong từng giai đoạn, quy tắc xử lý xung đột và điều kiện kết thúc. Nếu hai cột được phép khác nhau theo nghiệp vụ, không thể dùng phép so sánh bằng nhau để xác minh.

## 11. Quản lý migration khi nhiều instance ứng dụng khởi động

Không nên để mọi Pod ứng dụng cùng chạy migration trong startup hook nếu nhiều Pod có thể khởi động đồng thời. Hai tiến trình migration có thể cùng kiểm tra một version rồi cùng áp dụng DDL, hoặc một Pod chạy migration trong khi Pod khác đang dùng schema chưa hoàn chỉnh.

Một mô hình an toàn hơn:

1. Pipeline hoặc Kubernetes Job chuyên biệt chạy migration.
2. Migration runner lấy lock để bảo đảm chỉ một tiến trình chạy tại một thời điểm.
3. Runner kiểm tra version hiện tại và chỉ chạy migration chưa áp dụng.
4. Mỗi migration có định danh/version, checksum và trạng thái rõ ràng.
5. Sau khi migration hoàn tất, pipeline triển khai ứng dụng.
6. Job migration có log, timeout, retry policy và quyền database riêng.

Có thể dùng advisory lock cấp session để khóa runner:

~~~sql
SELECT pg_advisory_lock(652001, 1);

-- Migration runner thực hiện các migration theo thứ tự.
-- Giữ nguyên connection này trong toàn bộ thời gian giữ lock.

SELECT pg_advisory_unlock(652001, 1);
~~~

Lock session phải được lấy và nhả trên cùng một connection. Nếu connection bị đóng, PostgreSQL giải phóng session-level advisory lock. Migration tool thường có cơ chế lock riêng; ưu tiên dùng cơ chế đã được kiểm thử thay vì tự triển khai một lock không có quy trình recovery.

Migration history table nên lưu ít nhất version, thời điểm chạy, trạng thái và checksum nội dung migration. Nếu nội dung migration đã chạy bị sửa, checksum mismatch cần được xử lý rõ ràng; không âm thầm chạy lại migration cũ.

## 12. Transaction boundary và migration không transactional

Nhiều DDL của PostgreSQL có thể chạy trong transaction, giúp rollback nếu thất bại. Tuy nhiên, một số lệnh không được chạy trong transaction block, nổi bật là CREATE INDEX CONCURRENTLY và DROP INDEX CONCURRENTLY. Một số thao tác bảo trì khác cũng có giới hạn riêng.

Không bọc toàn bộ migration release vào một transaction duy nhất nếu trong đó có lệnh không transactional hoặc công việc backfill lớn. Chia migration theo mục đích và khả năng rollback:

- DDL ngắn, tương thích: transaction nhỏ.
- Index concurrent: migration riêng không transactional.
- Backfill: job có batch và checkpoint.
- Validation: bước riêng có thể theo dõi.
- Contract: migration phá vỡ tương thích, chạy sau cùng ở release riêng.

Migration đã commit không tự động được hoàn tác chỉ vì bước sau thất bại. Cần có kế hoạch forward-fix, migration bù hoặc restore tùy loại thay đổi.

## 13. Rolling deployment và thứ tự release

Một quy trình release điển hình:

| Giai đoạn | Database | Ứng dụng | Điều kiện tiếp tục |
|---|---|---|---|
| 0. Baseline | Chỉ có schema cũ | Tất cả phiên bản cũ | Ghi nhận backup và trạng thái |
| 1. Expand | Thêm cột/bảng/index mới, giữ cấu trúc cũ | Vẫn là phiên bản cũ | Kiểm tra schema mới và ứng dụng cũ |
| 2. Bridge | Đồng bộ cũ/mới, backfill | Rolling deploy bridge version | Tất cả writer được bảo vệ |
| 3. Switch read | Cả hai cấu trúc còn tồn tại | Phiên bản mới đọc cấu trúc mới | Dữ liệu và metric xác nhận đúng |
| 4. Retire old writes | Dừng phụ thuộc cũ nhưng vẫn giữ cấu trúc | Phiên bản mới, rollback window đã kết thúc | Không còn reader/writer cũ |
| 5. Contract | Xóa trigger/cột/index cũ | Phiên bản chỉ dùng schema mới | Có phê duyệt và kế hoạch phục hồi |

Thứ tự quan trọng là expand schema trước khi triển khai code cần schema mới. Khi rollback ứng dụng, schema mở rộng vẫn phải tương thích với binary cũ. Contract diễn ra sau khi rollback về binary cũ không còn là yêu cầu.

### Kiểm tra toàn bộ writer và reader

Trước contract, tìm mọi phụ thuộc:

- API service và worker.
- CronJob, scheduled task và consumer queue.
- Báo cáo BI, ETL, data warehouse và CDC.
- View, materialized view, function, procedure, trigger và rule.
- Script quản trị, notebook và truy vấn ad-hoc.
- Ứng dụng bên thứ ba hoặc tích hợp dùng chung database.
- Backup/restore tooling, migration tiếp theo và runbook.

Một cột không xuất hiện trong code service chính vẫn có thể được một báo cáo hoặc job đêm sử dụng.

## 14. Rollback và forward-fix

Rollback ứng dụng và rollback database là hai việc khác nhau. Trong migration tương thích, mục tiêu là cho phép rollback binary trong khi schema vẫn giữ được cấu trúc mới và cũ.

**Trước khi switch read:** có thể rollback bridge version về phiên bản cũ nếu schema expand vẫn hỗ trợ code cũ và trigger/dual-write còn hoạt động.

**Sau khi switch read nhưng trước contract:** có thể rollback về phiên bản bridge hoặc phiên bản cũ nếu dữ liệu cũ vẫn được đồng bộ đầy đủ và mọi dependency còn nguyên.

**Sau contract:** binary cũ có thể không chạy được. Lúc này thường cần forward-fix, restore schema/data từ backup hoặc tạo migration phục hồi riêng. Không giả định lệnh rename ngược lại sẽ khôi phục an toàn mọi dữ liệu phát sinh sau cutover.

Với thao tác dữ liệu không thể đảo ngược, hãy lưu bản sao hoặc audit trail trước khi chạy. Nhưng không nên sao chép toàn bộ bảng chỉ để có cảm giác an toàn nếu cách đó tạo tải quá lớn; thiết kế backup và phương án restore phù hợp với kích thước dữ liệu.

Mỗi release nên ghi rõ rollback boundary: bước nào còn rollback được bằng binary, bước nào cần forward-fix, bước nào cần restore và ai có quyền quyết định.

## 15. Migration trong môi trường có nhiều ứng dụng

Một database dùng chung có thể được truy cập bởi nhiều service độc lập, mỗi service có lịch phát hành riêng. Schema thay đổi phải được phối hợp theo hợp đồng giữa các consumer.

Nên quản lý ownership của bảng/cột và liệt kê consumer. Nếu một service muốn xóa cột đang được service khác dùng, cần có quá trình thông báo, telemetry hoặc xác nhận trực tiếp với chủ sở hữu. Không thể chỉ dựa vào việc repository của service chính không còn tham chiếu.

Các thay đổi API database nên được version hóa và thông báo như một thay đổi hợp đồng. Có thể sử dụng schema registry hoặc catalog nội bộ để ghi nhận producer/consumer, owner và thời hạn deprecation.

Nếu nhiều team cùng chạy migration, cần quy ước thứ tự và tránh hai migration độc lập cùng thay đổi một bảng. Migration lock ngăn chạy đồng thời nhưng không giải quyết xung đột logic giữa hai kế hoạch thay đổi.

## 16. Kiểm thử migration trước production

Kiểm thử phải bao gồm cả thời gian chuyển tiếp khi schema và ứng dụng chưa đồng nhất hoàn toàn.

Một bộ kiểm thử nên có:

- **Schema compatibility:** ứng dụng cũ chạy được với schema expand; bridge version chạy được; phiên bản mới chạy được trước contract.
- **Rolling deployment:** mô phỏng old Pod và new Pod cùng truy cập database.
- **Concurrent writes:** cập nhật hàng trong lúc backfill đang chạy.
- **Backfill restart:** dừng giữa chừng rồi chạy lại, bảo đảm không mất hoặc nhân đôi dữ liệu.
- **Lock behavior:** chạy migration khi có transaction dài và xác nhận lock_timeout hoạt động.
- **Index build:** xác nhận CREATE INDEX CONCURRENTLY chạy đúng ngoài transaction và xử lý trạng thái index invalid.
- **Constraint validation:** thử với dữ liệu hợp lệ và dữ liệu vi phạm.
- **Rollback:** rollback binary ở từng giai đoạn trước contract.
- **Failure injection:** mô phỏng mất kết nối, job bị kill, hết dung lượng tạm hoặc replica lag.
- **Data verification:** so sánh count, NULL, mismatch, aggregate và các invariant nghiệp vụ.

Dùng bản sao dữ liệu đại diện về kích thước và phân bố. Một bảng staging vài trăm hàng không thể phản ánh thời gian lock, WAL và I/O của bảng production hàng trăm triệu hàng.

## 17. Quan sát trong khi migration chạy

Migration online vẫn có thể làm giảm hiệu năng. Theo dõi cả database và ứng dụng.

**PostgreSQL:**

- pg_stat_activity: query, transaction age, wait event.
- pg_locks: lock được cấp và lock đang chờ.
- pg_stat_progress_create_index: tiến độ tạo index.
- pg_stat_user_tables: số lần update, dead tuple và vacuum.
- pg_stat_replication: sent/write/flush/replay LSN.
- pg_stat_archiver: archive backlog và lỗi archive.

Ví dụ xem tiến độ index build:

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
~~~

**Ứng dụng và hạ tầng:**

- Error rate, latency p95/p99 và request timeout.
- Connection pool saturation và số connection bị reset.
- CPU, memory, I/O latency, disk usage.
- Queue depth của worker và độ trễ consumer.
- Replication lag, WAL archive delay và backup status.
- Tiến độ backfill, số lỗi và batch duration.

Đặt ngưỡng dừng hoặc giảm tốc trước khi bắt đầu. Ví dụ, nếu replication lag vượt ngưỡng hoặc latency production tăng mạnh, backfill worker nên tự giảm tốc hoặc tạm dừng. Cần có người theo dõi và cách dừng migration an toàn.

## 18. Các anti-pattern thường gặp

**Rename hoặc drop cột trong cùng release với code mới.** Pod cũ có thể vẫn đang chạy và rollback sẽ thất bại. Hãy thêm cấu trúc mới, chuyển dần rồi xóa sau.

**Thêm NOT NULL ngay trên bảng lớn khi chưa backfill.** Dữ liệu cũ có thể vi phạm và việc kiểm tra có thể gây tải/lock. Dùng cột nullable, backfill, validate rồi mới đặt constraint.

**Backfill cả bảng trong một transaction.** Transaction dài giữ tài nguyên, tạo WAL và làm rollback đắt. Chia batch, commit và có checkpoint.

**Dùng dual-write nhưng không xác định nguồn chuẩn.** Hai giá trị có thể phân kỳ. Xác định thứ tự ưu tiên, xử lý conflict và điều kiện kết thúc dual-write.

**Chạy migration từ mọi Pod.** Nhiều instance có thể chạy cùng DDL. Dùng một migration runner có lock và history table.

**Chạy CREATE INDEX CONCURRENTLY trong transaction block.** PostgreSQL từ chối lệnh. Đặt nó trong migration riêng không transactional.

**Dùng lock_timeout quá lớn.** DDL chờ lock có thể tạo hàng đợi và làm tăng downtime. Dùng timeout có giới hạn, quan sát transaction dài và thử lại có kiểm soát.

**Contract ngay sau khi rollout hoàn tất.** Worker, cron hoặc client cũ có thể chưa được cập nhật; rollback window chưa kết thúc. Xác minh mọi dependency trước khi xóa.

**Coi migration thành công là dữ liệu đúng.** DDL hoàn tất không bảo đảm backfill đầy đủ hoặc logic chuyển đổi chính xác. Kiểm tra dữ liệu bằng invariant và số liệu nghiệp vụ.

## 19. Mẫu runbook cho một migration online

Một runbook có thể tổ chức như sau:

**Trước khi thay đổi**

1. Ghi nhận schema version, ứng dụng đang chạy và consumer liên quan.
2. Xác nhận backup gần nhất và khả năng restore.
3. Chạy migration trên bản sao dữ liệu có kích thước tương đương.
4. Kiểm tra lock, thời gian DDL, WAL, replication lag và kế hoạch rollback.
5. Chốt owner, cửa sổ quan sát, ngưỡng dừng và người phê duyệt contract.

**Trong giai đoạn expand**

1. Chạy DDL cộng thêm với lock_timeout phù hợp.
2. Xác minh cột/index/constraint mới đã tồn tại.
3. Triển khai bridge version theo rolling deployment.
4. Xác nhận phiên bản cũ và bridge version cùng hoạt động.
5. Bật trigger hoặc dual-write theo thiết kế.

**Trong giai đoạn chuyển dữ liệu**

1. Chạy backfill theo batch và ghi checkpoint.
2. Theo dõi WAL, replica lag, lock, latency và lỗi ứng dụng.
3. Dừng hoặc giảm tốc khi vượt ngưỡng.
4. Chạy lượt kiểm tra cuối cho các hàng bị bỏ qua.
5. Xác minh count, NULL, mismatch và invariant.

**Trong giai đoạn switch**

1. Triển khai phiên bản đọc cấu trúc mới.
2. Giữ đồng bộ cột cũ trong rollback window.
3. Theo dõi lỗi truy vấn, dữ liệu lệch và các consumer cũ.
4. Xác nhận mọi Pod, worker, cron và job đã chuyển phiên bản.

**Trước contract**

1. Xác nhận không còn truy cập cấu trúc cũ.
2. Xác nhận rollback window đã kết thúc và owner chấp thuận.
3. Lưu backup/snapshot theo chính sách.
4. Gỡ trigger hoặc dual-write trong release thích hợp.
5. Xóa cấu trúc cũ bằng migration riêng, có lock timeout.
6. Xác minh ứng dụng, query plan, metric và dữ liệu sau contract.

## 20. Checklist trước khi kết thúc migration

- [ ] Schema expand không phá vỡ phiên bản ứng dụng cũ.
- [ ] Migration runner chỉ có một tiến trình thực thi và có history/checksum.
- [ ] DDL được chia nhỏ, có lock timeout và transaction boundary phù hợp.
- [ ] Index lớn được tạo bằng phương thức phù hợp, xử lý được index invalid.
- [ ] Backfill chia batch, có checkpoint, retry và giới hạn tải.
- [ ] Writer cũ và mới đồng bộ dữ liệu theo một nguồn chuẩn rõ ràng.
- [ ] Dữ liệu đã được xác minh bằng count, NULL, mismatch và invariant.
- [ ] Phiên bản mới đã đọc cấu trúc mới ổn định.
- [ ] Worker, cron, consumer, report và service khác đã được kiểm tra.
- [ ] Rollback binary đã được thử trong giai đoạn schema còn tương thích.
- [ ] Rollback window đã kết thúc trước khi contract.
- [ ] Cấu trúc cũ chỉ bị xóa sau khi có xác nhận của data owner.
- [ ] Monitoring và runbook đã được cập nhật.

Migration tương thích là một chuỗi phát hành có chủ đích. Khi schema được mở rộng trước, dữ liệu được đồng bộ và xác minh, ứng dụng chuyển đổi theo từng phiên bản, rồi cấu trúc cũ mới được loại bỏ, PostgreSQL có thể tiếp tục phục vụ traffic trong suốt phần lớn quá trình. Thành công được xác nhận bằng cả khả năng tương thích của ứng dụng, tính đúng đắn của dữ liệu và khả năng vận hành khi một bước triển khai phải dừng hoặc rollback.

