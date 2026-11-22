# Thiết kế chỉ mục để giảm thời gian giữ khóa mà vẫn bảo vệ bất biến

Chỉ mục (index) thường được giới thiệu như một cách làm truy vấn nhanh hơn. Trong hệ thống có nhiều transaction đồng thời, chỉ mục còn ảnh hưởng đến **đường truy cập dữ liệu mà DBMS phải duyệt**, số hàng hoặc khóa chỉ mục được kiểm tra, và thời gian transaction phải giữ khóa trong khi hoàn thành thao tác.

Một truy vấn tìm đúng vài hàng bằng chỉ mục phù hợp thường kết thúc nhanh hơn truy vấn phải quét nhiều hàng. Khi truy vấn nằm trong transaction và đang giữ khóa, việc rút ngắn thời gian tìm kiếm có thể làm giảm thời gian các transaction khác phải chờ. Với những DBMS dùng khóa phạm vi, chỉ mục còn ảnh hưởng đến phạm vi khóa được lấy để bảo vệ điều kiện truy vấn và ngăn phantom.

Tuy nhiên, **chỉ mục không tự bảo vệ bất biến nghiệp vụ**. Một index giúp DBMS tìm dữ liệu hiệu quả; transaction, constraint và cơ chế khóa/isolation mới xác định quy tắc nào được bảo vệ. Thiết kế tốt phải đồng thời trả lời: truy vấn tìm dữ liệu qua đường nào, DBMS khóa những gì, và bất biến vẫn đúng khi có nhiều transaction cùng chạy hay không.

## 1. Vì sao đường truy cập ảnh hưởng đến thời gian giữ khóa?

Giả sử một transaction cần cập nhật trạng thái của một đơn hàng theo mã đơn:

~~~sql
BEGIN;

SELECT order_id, status
FROM orders
WHERE order_code = 'ORD-2026-0042'
FOR UPDATE;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_code = 'ORD-2026-0042';

COMMIT;
~~~

Nếu order_code có chỉ mục phù hợp, DBMS có thể định vị hàng nhanh. Nếu không có chỉ mục, DBMS có thể phải quét một phần lớn hoặc toàn bộ bảng để tìm hàng phù hợp. Transaction giữ khóa trong lúc thực hiện các bước đó; các transaction khác có thể phải chờ trên hàng hoặc tài nguyên liên quan.

Thời gian transaction giữ khóa thường bao gồm nhiều phần:

- Thời gian chờ khóa trước khi được phép tiếp tục.
- Thời gian DBMS tìm các hàng cần đọc hoặc ghi.
- Thời gian kiểm tra điều kiện và thực hiện cập nhật.
- Thời gian ứng dụng xử lý thêm trong transaction.
- Thời gian commit/rollback và hoàn tất công việc ghi log.

Chỉ mục chủ yếu giúp giảm chi phí tìm kiếm và xử lý dữ liệu. Nó không làm cho transaction tự động commit nhanh nếu ứng dụng vẫn giữ transaction mở để gọi HTTP, chờ người dùng hoặc thực hiện công việc không liên quan.

### Một ví dụ quét bảng và truy cập bằng chỉ mục

Giả sử bảng orders có hàng triệu bản ghi và truy vấn thường xuyên tìm đơn theo order_code.

Không có index:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_code = 'ORD-2026-0042';
~~~

DBMS có thể phải kiểm tra rất nhiều hàng. Khi câu truy vấn là locking read hoặc là một phần của UPDATE, việc tìm kiếm kéo dài có thể làm tăng thời gian chờ và thời gian giữ khóa.

Tạo chỉ mục:

~~~sql
CREATE UNIQUE INDEX ux_orders_order_code
ON orders (order_code);
~~~

DBMS có thể tìm một giá trị order_code bằng đường truy cập B-tree thay vì quét toàn bộ bảng. UNIQUE còn bảo vệ bất biến mỗi mã đơn chỉ xuất hiện một lần.

Điểm quan trọng là index và constraint có hai vai trò khác nhau trong ví dụ này:

- B-tree giúp tìm hàng theo order_code nhanh hơn.
- UNIQUE bảo đảm không thể commit hai hàng có cùng order_code.
- Transaction và khóa ghi bảo vệ thay đổi trạng thái của hàng.

Nếu order_code vốn đã là PRIMARY KEY hoặc có UNIQUE constraint, DBMS thường đã có index hỗ trợ; không nên tạo thêm một index trùng lặp.

## 2. Chỉ mục giúp giảm phạm vi dữ liệu cần duyệt

Một chỉ mục B-tree sắp xếp các khóa theo thứ tự. DBMS có thể định vị vùng bắt đầu và duyệt phần khóa thỏa điều kiện thay vì kiểm tra toàn bộ bảng.

Ví dụ, truy vấn tìm các đơn READY của một tenant theo thời gian tạo:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 25
  AND status = 'READY'
ORDER BY created_at, order_id
FETCH FIRST 20 ROWS ONLY;
~~~

Một chỉ mục phù hợp có thể là:

~~~sql
CREATE INDEX ix_orders_claim
ON orders (tenant_id, status, created_at, order_id);
~~~

Các cột được sắp theo mục đích truy vấn:

1. tenant_id là điều kiện bằng.
2. status là điều kiện bằng.
3. created_at phục vụ thứ tự thời gian.
4. order_id tạo thứ tự phụ ổn định khi nhiều hàng có cùng created_at.

Đường truy cập có thể tìm đúng nhóm READY của tenant 25 rồi duyệt theo thời gian. Nếu transaction cần khóa một số hàng đầu tiên để worker nhận việc, index phù hợp giúp DBMS tìm các hàng ứng viên nhanh hơn.

~~~sql
-- Ví dụ theo cú pháp PostgreSQL; hệ quản trị khác có thể dùng LIMIT,
-- TOP/OFFSET hoặc locking hints/API riêng.
SELECT order_id
FROM orders
WHERE tenant_id = 25
  AND status = 'READY'
ORDER BY created_at, order_id
FETCH FIRST 20 ROWS ONLY
FOR UPDATE;
~~~

Ví dụ locking read ở trên dùng cú pháp PostgreSQL. Trong hệ thống queue, một số DBMS hỗ trợ SKIP LOCKED để worker bỏ qua hàng đang được worker khác khóa; SQL Server có các locking hints và READPAST với ngữ nghĩa riêng. Chỉ mục trên tenant_id, status, created_at, order_id giúp định vị và sắp xếp tập ứng viên hiệu quả hơn. Tuy nhiên, phải xác nhận cú pháp, thứ tự khóa và cách xử lý LIMIT/FETCH cùng SKIP LOCKED trên DBMS cụ thể.

## 3. Chọn thứ tự cột trong composite index

Chỉ mục nhiều cột (composite index) có thứ tự. Với B-tree, thứ tự cột quyết định những điều kiện nào có thể định vị một khoảng liên tục trong index.

Quy tắc thực hành phổ biến:

- Đặt các cột có điều kiện bằng (=) ở đầu nếu truy vấn thường cố định chúng.
- Sau các cột bằng, đặt cột dùng điều kiện phạm vi (<, >, BETWEEN) hoặc sắp xếp chính.
- Thêm cột tie-breaker nếu truy vấn cần thứ tự ổn định.
- Chỉ thêm cột cần thiết; index quá rộng làm tăng chi phí ghi và dung lượng.

Ví dụ truy vấn:

~~~sql
SELECT booking_id
FROM bookings
WHERE resource_id = 12
  AND start_at >= TIMESTAMP '2026-11-14 08:00:00'
  AND start_at <  TIMESTAMP '2026-11-14 10:00:00'
ORDER BY start_at, booking_id;
~~~

Chỉ mục phù hợp:

~~~sql
CREATE INDEX ix_bookings_resource_start
ON bookings (resource_id, start_at, booking_id);
~~~

resource_id là điều kiện bằng, start_at là khoảng thời gian, booking_id hỗ trợ thứ tự phụ. DBMS có thể định vị vùng của resource 12 và duyệt các khóa start_at trong khoảng.

Nếu đảo thứ tự thành (start_at, resource_id), truy vấn vẫn có thể dùng index một phần, nhưng thường phải duyệt nhiều khoảng thời gian của các resource khác nhau trước khi lọc resource_id. Cần xem execution plan thực tế, không chỉ suy luận từ tên index.

### Điều kiện phạm vi làm giới hạn phần cột phía sau

Với B-tree, một điều kiện phạm vi trên cột thường giới hạn việc dùng các cột phía sau để xác định một khoảng liên tục duy nhất. Một số DBMS vẫn có thể dùng các cột sau để lọc trong index hoặc thực hiện index condition, nhưng không nên giả định chúng làm khoảng tìm kiếm hẹp đi theo mọi cách.

Ví dụ:

~~~sql
WHERE resource_id = 12
  AND start_at < :requested_end
  AND end_at > :requested_start
~~~

Index (resource_id, start_at, end_at) có thể thu hẹp theo resource_id và start_at. Điều kiện end_at > requested_start có thể được kiểm tra thêm trên các mục index hoặc sau khi lấy hàng, tùy DBMS và execution plan. Nó không biến bài toán khoảng chồng lấn hai chiều thành một khoảng B-tree đơn giản.

Nếu có rất nhiều booking cũ của cùng resource, điều kiện start_at < requested_end có thể vẫn quét một phạm vi lớn. Cần cân nhắc mô hình dữ liệu, phân vùng thời gian, chuẩn hóa thành slot rời rạc hoặc một cơ chế bảo vệ khác phù hợp với bất biến.

## 4. Chỉ mục và bảo vệ bất biến không phải cùng một việc

Xem quy tắc: một phòng không được có hai booking đang hoạt động trùng thời gian.

Điều kiện chồng lấn hai khoảng thời gian là:

~~~text
existing.start_at < requested.end_at
AND existing.end_at > requested.start_at
~~~

Truy vấn kiểm tra:

~~~sql
SELECT booking_id
FROM bookings
WHERE resource_id = :resource_id
  AND status = 'ACTIVE'
  AND start_at < :requested_end
  AND end_at > :requested_start;
~~~

Chỉ mục có thể giúp tìm nhanh các booking ứng viên:

~~~sql
CREATE INDEX ix_bookings_active_resource_start
ON bookings (resource_id, status, start_at);
~~~

Nhưng nếu transaction chỉ SELECT để kiểm tra rồi INSERT, hai transaction có thể cùng thấy không có booking chồng lấn và cùng tạo booking mới. Index làm truy vấn nhanh hơn, nhưng bản thân nó không bảo đảm không có phantom hoặc không có hai transaction cùng vượt qua bước kiểm tra.

Cần một cơ chế bảo vệ phù hợp:

- Constraint loại trừ khoảng thời gian nếu DBMS hỗ trợ (ví dụ PostgreSQL exclusion constraint với range type).
- Unique constraint nếu mô hình hóa thời gian thành các slot rời rạc có khóa duy nhất.
- Locking read/range lock trên phạm vi phù hợp trong DBMS hỗ trợ.
- Guard row theo resource_id để mọi transaction đặt phòng cùng tranh chấp một hàng.
- SERIALIZABLE nếu DBMS có thể bảo vệ predicate và ứng dụng xử lý serialization failure.

Ví dụ PostgreSQL có thể dùng exclusion constraint cho các khoảng thời gian không chồng lấn. Mẫu minh họa cần extension btree_gist để kết hợp equality của resource_id với overlap của range:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE bookings
ADD CONSTRAINT bookings_no_active_overlap
EXCLUDE USING gist (
    resource_id WITH =,
    tstzrange(start_at, end_at, '[)') WITH &&
)
WHERE (status = 'ACTIVE');
~~~

Constraint này biểu diễn trực tiếp bất biến: hai booking ACTIVE của cùng resource không được có khoảng thời gian giao nhau. Chỉ mục GiST phục vụ constraint. Cú pháp và kiểu range phụ thuộc PostgreSQL; DBMS khác cần giải pháp tương đương hoặc giao thức transaction riêng.

## 5. Range lock phụ thuộc chỉ mục như thế nào?

Một số DBMS dùng khóa phạm vi trên index để bảo vệ các điều kiện truy vấn khỏi phantom. Khi transaction kiểm tra một khoảng khóa, DBMS có thể khóa các mục index hoặc khoảng trống giữa các khóa để ngăn transaction khác chèn một hàng mới thỏa predicate.

Index quyết định cách DBMS xác định khoảng khóa. Một index phù hợp giúp phạm vi cần bảo vệ hẹp hơn. Nếu không có index phù hợp, DBMS có thể phải quét và khóa một phạm vi lớn hơn, thậm chí khóa nhiều key hoặc đối tượng rộng hơn tùy engine và isolation level.

Không phải mọi DBMS đều triển khai range lock theo cùng cách:

| DBMS / cơ chế | Cách bảo vệ phạm vi đọc |
|---|---|
| MySQL InnoDB | Dùng record lock, gap lock và next-key lock trong các tình huống/isolation level phù hợp; phạm vi phụ thuộc index access path |
| SQL Server SERIALIZABLE | Có thể dùng key-range lock trên index để ngăn insert/update tạo phantom trong phạm vi được bảo vệ |
| PostgreSQL READ COMMITTED / REPEATABLE READ | Không dùng gap lock thông thường để chặn insert vào khoảng đọc; PostgreSQL SERIALIZABLE dùng predicate lock kiểu SIREAD để phát hiện phụ thuộc, thường không chặn writer trực tiếp |
| Oracle | Dùng consistent read và row-level locking; SERIALIZABLE dựa trên snapshot transaction và có thể từ chối cập nhật xung đột; không nên giả định có gap lock kiểu InnoDB |

### InnoDB: next-key lock theo index range

Trong InnoDB, next-key lock kết hợp record lock trên một index record với gap lock trên khoảng trước record đó. Cơ chế này có thể ngăn transaction khác chèn khóa mới vào khoảng được bảo vệ.

Ví dụ, truy vấn locking read:

~~~sql
SELECT *
FROM bookings
WHERE resource_id = 12
  AND start_at >= '2026-11-14 08:00:00'
  AND start_at <  '2026-11-14 10:00:00'
FOR UPDATE;
~~~

Nếu index (resource_id, start_at) được dùng, InnoDB có thể khóa các index record và khoảng khóa liên quan đến phạm vi truy vấn theo isolation level. Một index phù hợp giúp DBMS xác định vùng cần khóa chính xác hơn so với full scan.

Trong InnoDB REPEATABLE READ, locking range scan thường dùng next-key locks để ngăn phantom. Ở READ COMMITTED, gap locking cho locking read và DML thông thường được giảm hoặc tắt trong phần lớn trường hợp, ngoại trừ một số mục đích như kiểm tra khóa ngoại và duplicate-key. Cần xem đúng loại câu lệnh và phiên bản MySQL.

### SQL Server: key-range lock

SQL Server ở SERIALIZABLE có thể dùng key-range locks để bảo vệ một khoảng index. Nếu truy vấn có index phù hợp, DBMS có thể khóa một vùng key nhỏ hơn. Nếu không có index phù hợp, việc bảo vệ predicate có thể cần khóa nhiều key hoặc phạm vi rộng hơn.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT booking_id
FROM bookings
WHERE resource_id = 12
  AND start_at >= '2026-11-14T08:00:00'
  AND start_at <  '2026-11-14T10:00:00';

-- Kiểm tra và ghi booking trong cùng transaction.

COMMIT;
~~~

Index (resource_id, start_at) có thể hỗ trợ key-range locking cho predicate. Nhưng loại khóa thực tế phụ thuộc execution plan, hint, thống kê, phiên bản và các thao tác trong transaction. Kiểm tra DMV hoặc công cụ giám sát khóa để xác nhận.

### PostgreSQL: predicate lock không giống gap lock chặn ghi

PostgreSQL SERIALIZABLE dùng Serializable Snapshot Isolation (SSI). Predicate lock (SIREAD) ghi nhận vùng dữ liệu đã đọc để phát hiện các phụ thuộc đọc/ghi nguy hiểm. Nó thường không chặn transaction khác ghi trực tiếp vào vùng đó như một gap lock của InnoDB.

Index vẫn có ảnh hưởng đến độ chi tiết của predicate lock và cách DBMS theo dõi phạm vi đọc; khi không có index phù hợp, PostgreSQL có thể phải ghi nhận predicate lock ở mức rộng hơn, thậm chí relation-level. Điều này có thể làm tăng số xung đột serialization và retry dù không nhất thiết làm writer phải chờ khóa đọc.

Do đó, trong PostgreSQL SERIALIZABLE, chỉ mục có thể giúp giảm chi phí truy vấn và giảm phạm vi theo dõi phụ thuộc. Nó không phải lời hứa rằng mọi writer ngoài phạm vi index sẽ bị chặn.

## 6. Chỉ mục phù hợp có thể giảm thời gian giữ khóa ra sao?

Có ba tác động cần xem xét riêng:

1. **Giảm thời gian tìm hàng**: DBMS duyệt ít index entry và ít hàng hơn để tìm tập dữ liệu cần thao tác.
2. **Giảm số đối tượng cần khóa hoặc kiểm tra**: trong DBMS dùng row/key/range locks, access path chọn lọc có thể giảm footprint. Với predicate locking, phạm vi theo dõi có thể chi tiết hơn.
3. **Giảm công việc phụ trong transaction**: index hỗ trợ ORDER BY hoặc điều kiện lọc có thể tránh sort lớn, scan dư thừa và lookup không cần thiết.

Ví dụ worker nhận một job READY:

~~~sql
SELECT job_id
FROM jobs
WHERE tenant_id = :tenant_id
  AND state = 'READY'
ORDER BY priority DESC, created_at, job_id
FETCH FIRST 1 ROW ONLY
FOR UPDATE;
~~~

Chỉ mục gợi ý:

~~~sql
CREATE INDEX ix_jobs_claim
ON jobs (tenant_id, state, priority DESC, created_at, job_id);
~~~

Nếu execution plan dùng index này, DBMS có thể đi thẳng vào nhóm job READY của tenant, theo đúng thứ tự ưu tiên, rồi tìm hàng đầu tiên. Không cần quét tất cả job của tenant hoặc sort toàn bộ tập ứng viên.

Một transaction ngắn có thể khóa và chuyển trạng thái:

~~~sql
BEGIN;

SELECT job_id
FROM jobs
WHERE tenant_id = :tenant_id
  AND state = 'READY'
ORDER BY priority DESC, created_at, job_id
FETCH FIRST 1 ROW ONLY
FOR UPDATE;

UPDATE jobs
SET state = 'RUNNING'
WHERE job_id = :job_id
  AND state = 'READY';

COMMIT;
~~~

Đây là minh họa theo cú pháp PostgreSQL; cú pháp FETCH FIRST/FOR UPDATE và khả năng dùng SKIP LOCKED khác nhau giữa DBMS. Cần bảo đảm cách lấy khóa và claim job là nguyên tử theo hệ quản trị. Nếu DBMS hỗ trợ UPDATE ... RETURNING hoặc locking read với SKIP LOCKED, có thể xây dựng mẫu claim phù hợp. Chỉ mục không thay thế điều kiện state = 'READY' trong câu UPDATE và không bảo đảm worker không claim trùng nếu giao thức transaction sai.

## 7. Covering index: giảm lookup nhưng cân nhắc chi phí

Một covering index chứa các cột đủ để trả lời truy vấn mà không cần truy cập thêm bảng dữ liệu trong một số DBMS/plan.

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 25
  AND status = 'READY'
ORDER BY created_at, order_id;
~~~

Index:

~~~sql
CREATE INDEX ix_orders_ready_cover
ON orders (tenant_id, status, created_at, order_id);
~~~

Các cột truy vấn đã nằm trong index. DBMS có thể đọc dữ liệu từ index mà không cần lookup hàng gốc trong những trường hợp phù hợp. Điều này có thể giảm I/O và thời gian thực thi.

Tuy nhiên, covering index không có nghĩa mọi locking read đều chỉ khóa index và bỏ qua hàng gốc. Ví dụ, SELECT FOR UPDATE cần khóa hàng theo ngữ nghĩa DBMS; engine có thể vẫn truy cập và khóa record tương ứng trong bảng/clustered index. SQL Server có thể lấy thêm khóa trên index hoặc hàng dữ liệu tùy plan và isolation. InnoDB lưu dữ liệu hàng trong clustered index và secondary index chứa khóa chính để tìm hàng gốc.

Chỉ thêm cột vào index để bao phủ truy vấn khi lợi ích đọc xứng đáng với chi phí ghi và dung lượng. Cột lớn như TEXT/BLOB thường không phù hợp để nhồi vào index; một covering index quá rộng có thể làm giảm cache hit và tăng thời gian cập nhật.

## 8. Index quá nhiều có thể làm tăng tranh chấp ghi

Mỗi index liên quan phải được duy trì khi dữ liệu thay đổi. INSERT, DELETE hoặc UPDATE cột được index hóa có thể cập nhật nhiều cấu trúc index.

Hệ quả:

- Mỗi transaction ghi có thêm I/O và CPU.
- Cần khóa hoặc latch trên các trang index tương ứng.
- Một index có nhiều writer cùng chèn vào vùng nóng có thể trở thành điểm tranh chấp.
- Index rộng làm tăng dung lượng và giảm số entry trên mỗi page.
- Thay đổi thứ tự cập nhật nhiều index hoặc nhiều hàng có thể làm tăng khả năng deadlock.
- Index không dùng đến làm chậm mọi đường ghi mà không đem lại lợi ích truy vấn.

Ví dụ, index trên created_at tăng dần có thể khiến nhiều INSERT mới tập trung vào các page cuối của B-tree. Engine có cơ chế latch và tối ưu riêng, nhưng hotspot ở vùng chèn vẫn cần theo dõi khi tải ghi lớn.

Không nên tạo index cho mọi cột xuất hiện trong WHERE. Hãy chọn index dựa trên truy vấn quan trọng, độ chọn lọc, tần suất đọc/ghi và execution plan. Xóa index dư thừa chỉ sau khi kiểm tra workload và khả năng sử dụng gián tiếp của nó.

## 9. Chỉ mục và deadlock

Index có thể giảm số hàng cần khóa, nhưng cũng ảnh hưởng thứ tự DBMS truy cập và khóa các tài nguyên. Hai transaction cập nhật nhiều hàng theo thứ tự khác nhau vẫn có thể deadlock.

Ví dụ:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Khóa hàng account 1           Khóa hàng account 2
Cần khóa account 2            Cần khóa account 1
Chờ B                         Chờ A
~~~

Một index thay đổi execution plan có thể làm thứ tự truy cập hàng khác đi, vì vậy việc thêm index đôi khi làm deadlock biến mất hoặc xuất hiện. Điều đó không chứng minh index đã sửa nguyên nhân logic.

Các biện pháp:

- Cập nhật nhiều hàng theo thứ tự khóa nhất quán, ví dụ account_id tăng dần.
- Giữ transaction ngắn.
- Có index cho điều kiện tìm kiếm của UPDATE/DELETE để tránh scan rộng.
- Không dựa vào thứ tự ngẫu nhiên của execution plan làm thứ tự khóa nghiệp vụ.
- Bắt deadlock và retry transaction theo quy tắc phù hợp.
- Theo dõi deadlock graph để xác định tài nguyên và câu SQL thực sự liên quan.

## 10. Làm thế nào kiểm chứng index thực sự giúp?

Không nên kết luận chỉ mục đã giảm khóa chỉ vì truy vấn nhanh hơn trong một lần chạy. Cần kiểm tra execution plan và đo hành vi đồng thời.

### Kiểm tra execution plan

Dùng công cụ của DBMS để xem:

- Table scan hay index seek/range scan đang được dùng?
- Số hàng ước tính và số hàng thực tế có gần nhau không?
- Index condition và filter condition là gì?
- Có sort, hash hoặc lookup bổ sung không?
- Truy vấn có dùng đúng thứ tự cột trong composite index không?
- Optimizer có bỏ qua index do thống kê cũ hoặc độ chọn lọc thấp không?

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id
FROM bookings
WHERE resource_id = 12
  AND start_at >= TIMESTAMP '2026-11-14 08:00:00'
  AND start_at < TIMESTAMP '2026-11-14 10:00:00';
~~~

EXPLAIN ANALYZE thực thi câu truy vấn; cần cẩn thận nếu áp dụng cho UPDATE/DELETE hoặc câu lệnh có side effect. Trong môi trường production, dùng transaction rollback hoặc công cụ phân tích plan phù hợp khi cần tránh thay đổi dữ liệu.

Với MySQL, dùng EXPLAIN và EXPLAIN ANALYZE ở phiên bản hỗ trợ. SQL Server có Actual Execution Plan và SET STATISTICS IO/TIME. Oracle có DBMS_XPLAN và thống kê thực thi. Tên công cụ khác nhau, nhưng mục tiêu là xác nhận access path thực tế.

### Đo thời gian chờ và thời gian giữ khóa

Chạy workload trước và sau khi thêm index với cùng dữ liệu và mức đồng thời. Thu thập:

- Thời gian thực thi truy vấn.
- Thời gian chờ khóa trung bình và p95/p99.
- Thời gian transaction mở.
- Số hàng và số index entry được đọc.
- Deadlock, lock timeout và serialization failure.
- Throughput và tỷ lệ request thành công.
- Chi phí ghi và kích thước index.

Không chỉ nhìn latency của một truy vấn đơn lẻ. Một index có thể giảm thời gian SELECT nhưng tăng đáng kể chi phí INSERT/UPDATE hoặc làm hotspot ở index page.

### Kiểm tra tính đúng của bất biến

Sau khi thay đổi index, chạy lại các lịch cạnh tranh có chủ đích. Ví dụ hai transaction cùng đặt một resource trong khoảng thời gian giao nhau. Xác nhận một trong các điều sau:

- Constraint từ chối một thao tác.
- Range lock ngăn transaction thứ hai chèn dữ liệu xung đột.
- Guard row buộc hai transaction tuần tự hóa quyết định.
- SERIALIZABLE hủy một transaction và ứng dụng retry đúng cách.

Một execution plan nhanh không chứng minh bất biến được bảo vệ. Bằng chứng phải bao gồm kết quả cuối của lịch đồng thời và hành vi lỗi/retry.

## 11. Quy trình thiết kế index theo bất biến

Có thể áp dụng quy trình sau cho từng nghiệp vụ:

1. **Viết bất biến**: xác định chính xác điều kiện phải luôn đúng, ví dụ không có hai booking ACTIVE cùng resource và khoảng thời gian chồng lấn.
2. **Liệt kê transaction liên quan**: tìm tất cả API, worker, batch job và service có thể đọc hoặc ghi tập dữ liệu.
3. **Xác định predicate**: ghi rõ điều kiện WHERE, điều kiện join, ORDER BY và giới hạn số hàng.
4. **Chọn cơ chế bảo vệ**: constraint, unique/exclusion constraint, locking read, range lock, guard row hoặc SERIALIZABLE.
5. **Thiết kế index theo access path**: equality prefix trước, range/order tiếp theo; chỉ thêm cột cần thiết.
6. **Kiểm tra execution plan**: xác nhận DBMS thực sự dùng index và phạm vi duyệt phù hợp.
7. **Kiểm tra lock behavior**: xác nhận đúng loại khóa/phạm vi predicate theo DBMS và isolation level.
8. **Chạy concurrency test**: điều khiển lịch đọc/ghi bằng nhiều connection; xác nhận bất biến sau commit/retry.
9. **Đo trade-off**: latency, lock wait, deadlock, write throughput, dung lượng và chi phí bảo trì index.
10. **Theo dõi sau triển khai**: phát hiện plan regression, index không còn dùng, hotspot và tỷ lệ xung đột.

### Ví dụ thiết kế cho truy vấn khoảng thời gian

Bất biến: không có hai booking ACTIVE của cùng resource chồng lấn thời gian.

Truy vấn kiểm tra:

~~~sql
SELECT booking_id
FROM bookings
WHERE resource_id = :resource_id
  AND status = 'ACTIVE'
  AND start_at < :requested_end
  AND end_at > :requested_start;
~~~

Thiết kế index ban đầu:

~~~sql
CREATE INDEX ix_bookings_resource_status_start
ON bookings (resource_id, status, start_at);
~~~

Sau đó:

- Kiểm tra plan có seek theo resource_id và status không.
- Xem phạm vi start_at được duyệt có quá rộng không.
- Đo số hàng bị lọc thêm bởi end_at.
- Kiểm tra DBMS khóa index range nào trong locking read hoặc SERIALIZABLE.
- Nếu phạm vi vẫn quá rộng, cân nhắc mô hình slot rời rạc, phân vùng thời gian, guard row theo resource hoặc constraint loại trừ nếu DBMS hỗ trợ.

Không nên thêm end_at vào cuối index và giả định DBMS có thể khóa chính xác hình chữ nhật hai chiều của điều kiện overlap. B-tree có thứ tự một chiều theo từng prefix; điều kiện range đầu tiên thường quyết định vùng duyệt chính.

## 12. Những ngộ nhận thường gặp

### Có index thì không còn lock contention

Index giúp tìm dữ liệu nhanh và có thể thu hẹp phạm vi khóa, nhưng nhiều transaction vẫn có thể cùng cập nhật một hàng nóng hoặc cùng chèn vào một index page. Contention vẫn tồn tại nếu workload tập trung vào cùng tài nguyên.

### Index luôn làm phạm vi khóa nhỏ hơn

Điều này phụ thuộc DBMS, isolation level và execution plan. Một index không phù hợp có thể không được dùng; một scan rộng có thể cần khóa nhiều hàng/key hơn. PostgreSQL predicate lock, InnoDB next-key lock và SQL Server key-range lock có ngữ nghĩa khác nhau.

### SELECT nhanh chứng minh bất biến an toàn

Một truy vấn SELECT nhanh chỉ chứng minh đường đọc có thể hiệu quả. Hai transaction vẫn có thể cùng đọc “không tồn tại” rồi cùng INSERT nếu không có constraint hoặc cơ chế khóa bảo vệ predicate.

### Chỉ cần index trên các cột WHERE

Thứ tự cột, điều kiện bằng/phạm vi, ORDER BY, join, độ chọn lọc và loại index đều quan trọng. Một index có đủ cột nhưng sai thứ tự có thể không giúp truy vấn như mong muốn.

### Càng nhiều index càng tốt

Mỗi index tăng chi phí ghi, dung lượng và công việc bảo trì. Index không dùng có thể làm giảm throughput của mọi transaction ghi.

## 13. Bảng lựa chọn nhanh

| Mục tiêu | Hướng thiết kế |
|---|---|
| Tìm một hàng theo mã duy nhất | PRIMARY KEY hoặc UNIQUE index |
| Tìm hàng theo tenant và trạng thái, sau đó sắp xếp theo thời gian | Composite index theo equality columns rồi ordering columns |
| Khóa một phạm vi theo resource và thời gian | Index bắt đầu bằng resource_id, tiếp theo là cột phạm vi; xác nhận range lock thực tế |
| Bảo vệ uniqueness hoặc quan hệ chính xác | Constraint ở DBMS |
| Bảo vệ predicate nhiều hàng trong PostgreSQL | SERIALIZABLE/SSI hoặc thiết kế guard/constraint phù hợp; index hỗ trợ plan và predicate tracking |
| Giảm thời gian claim job | Index theo tenant, state, priority/time, tie-breaker; transaction claim ngắn |
| Giảm write contention trên index nóng | Đo hotspot, xem lại thứ tự khóa, phân vùng hoặc mô hình ghi |
| Tránh index lookup cho truy vấn đọc thường xuyên | Cân nhắc covering index, cân bằng với chi phí ghi và độ rộng index |

Chỉ mục là một phần của thiết kế concurrency. Index phù hợp rút ngắn đường tìm kiếm, giúp transaction hoàn thành nhanh hơn và trong một số DBMS thu hẹp phạm vi khóa hoặc predicate cần bảo vệ. Nhưng index không thay thế transaction, constraint hay isolation level. Hãy bắt đầu từ bất biến, chọn cơ chế bảo vệ đúng với DBMS, thiết kế index theo predicate và access path thực tế, rồi xác nhận bằng execution plan, lock observation và kiểm thử đồng thời.
