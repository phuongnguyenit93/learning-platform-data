# Khóa trong ALTER TABLE, tạo chỉ mục và bảo trì PostgreSQL

## 1. Vì sao DDL và bảo trì có thể làm nghẽn hệ thống?

Một bảng PostgreSQL có thể đang phục vụ hàng nghìn lệnh `SELECT`, `INSERT`, `UPDATE` và `DELETE` mỗi phút. Khi đội kỹ thuật cần thêm cột, tạo chỉ mục, kiểm tra ràng buộc, dọn phiên bản hàng cũ hoặc tổ chức lại dữ liệu, cơ sở dữ liệu phải bảo đảm rằng **cấu trúc bảng và dữ liệu không bị thay đổi không tương thích trong lúc thao tác đang chạy**.

PostgreSQL dùng nhiều loại **lock** (khóa) để bảo vệ sự nhất quán đó. DDL và maintenance là những tác vụ thường được mô tả là “quản trị”, nhưng chúng có thể ảnh hưởng trực tiếp đến lưu lượng ứng dụng:

- `ALTER TABLE` có thể cần `ACCESS EXCLUSIVE` ngay cả khi thay đổi metadata diễn ra rất nhanh.
- `CREATE INDEX` thông thường cho phép đọc nhưng có thể **chặn ghi** trên bảng đích trong lúc xây chỉ mục.
- `CREATE INDEX CONCURRENTLY` giảm chặn ghi nhưng mất nhiều thời gian, tốn công hơn và phải tuân thủ giới hạn vận hành.
- `VACUUM` thông thường được thiết kế để chạy song song với phần lớn thao tác đọc/ghi, nhưng vẫn có xung đột với một số DDL/maintenance.
- `VACUUM FULL` viết lại bảng, cần khóa mạnh và có thể **chặn cả đọc lẫn ghi**.
- Một yêu cầu lấy khóa mạnh **đang chờ** cũng có thể khiến các query mới xếp hàng phía sau, dù bản thân DDL chưa bắt đầu sửa bảng.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **table-level locks**, **row-level locks** và **transaction/virtual transaction locks** ở mức cần để vận hành.
2. Hiểu các mode như `ACCESS SHARE`, `ROW EXCLUSIVE`, `SHARE UPDATE EXCLUSIVE`, `SHARE`, `SHARE ROW EXCLUSIVE`, `ACCESS EXCLUSIVE`.
3. Giải thích khi nào `ALTER TABLE` chặn đọc/ghi và vì sao một thao tác metadata rất nhanh vẫn có thể gây sự cố.
4. Chọn `CREATE INDEX` hoặc `CREATE INDEX CONCURRENTLY` theo yêu cầu đồng thời.
5. Phân biệt `REINDEX`, `REINDEX CONCURRENTLY`, `VACUUM`, `VACUUM FULL`, `ANALYZE` và `CLUSTER`.
6. Quan sát blocker/waiter qua `pg_stat_activity`, `pg_locks`, `pg_blocking_pids()` và các view tiến độ.
7. Dùng `lock_timeout`, `statement_timeout` và migration theo giai đoạn để hạn chế rủi ro.
8. Thử hai kết nối để quan sát sự chờ khóa trong database thực hành.
9. Xây checklist triển khai schema/index bảo trì với khả năng rollback và xác minh.

> **An toàn thực hành:** chỉ chạy các ví dụ khóa/DDL trên database lab có quyền sử dụng. Không giữ transaction chặn bảng trên production để “xem sẽ thế nào”. Các thao tác `VACUUM FULL`, `CLUSTER` hoặc tạo chỉ mục lớn có thể gây tải, dùng nhiều dung lượng đĩa và ảnh hưởng trực tiếp tới người dùng.

---

## 2. Lock trong PostgreSQL: ba cấp độ thường gặp

Khái niệm “khóa” không chỉ có một dạng. Khi đọc tài liệu hoặc xử lý incident, cần biết đang nói tới lớp nào.

| Lớp khóa | Vai trò | Tình huống |
|---|---|---|
| **Table-level / relation locks** | Bảo vệ thao tác trên một relation và khả năng phối hợp giữa DDL, DML, maintenance | `ALTER TABLE`, `CREATE INDEX`, `VACUUM`, `SELECT` |
| **Row-level locks** | Điều phối việc cập nhật hoặc khóa từng hàng | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` |
| **Transaction ID / virtual transaction locks** | Phối hợp việc chờ transaction khác kết thúc | Một writer đang chờ transaction đã sửa row |

Ngoài ra còn có lock mức page, predicate locks (ở SERIALIZABLE), advisory locks và các cơ chế đồng bộ nội bộ. Bài tập trung vào **relation locks** khi triển khai ALTER TABLE, index và maintenance, nhưng phải biết row/transaction locks cũng có thể xuất hiện trong báo cáo chờ khóa.

### 2.1. Tên lock mode không giống “khóa toàn bộ bảng tuyệt đối”

`ROW EXCLUSIVE` có chữ “EXCLUSIVE” nhưng **không** có nghĩa nó ngăn mọi `SELECT`. Ngược lại, `ACCESS EXCLUSIVE` là mode mạnh nhất trong các relation locks, xung đột với mọi relation lock mode khác, kể cả `ACCESS SHARE` của SELECT thông thường.

Chữ **ROW** trong tên `ROW SHARE` hay `ROW EXCLUSIVE` cũng không có nghĩa đó là **row-level lock**: đây vẫn là **table-level lock modes**.

### 2.2. Relation locks và quyền nhìn thấy dữ liệu MVCC

Một `SELECT` thường dùng `ACCESS SHARE` trên các relation cần đọc, trong khi hệ thống dùng MVCC để quyết định phiên bản row nào visible cho snapshot. MVCC giúp đọc không phải luôn chờ writer cập nhật từng row, nhưng **không loại bỏ** xung đột DDL như `ACCESS EXCLUSIVE`.

### 2.3. Lock được giữ trong bao lâu?

Nhiều relation lock được lấy bởi statement trong transaction và được giữ **đến khi transaction kết thúc**, không nhất thiết được nhả ngay khi câu ALTER chạy xong. Ví dụ:

~~~sql
BEGIN;
ALTER TABLE demo.some_table ADD COLUMN note TEXT;
-- ALTER TABLE đã trả kết quả, nhưng transaction vẫn đang mở.
-- Lock liên quan có thể tiếp tục được giữ đến COMMIT/ROLLBACK.
COMMIT;
~~~

Đoạn trên **minh họa**, chưa có bảng `demo.some_table` trong lab. Đừng chạy nó khi chưa chuẩn bị bảng thực hành ở phần sau.

Hệ quả: **không mở transaction rồi chạy ALTER TABLE và chờ kiểm tra thủ công vài phút trước khi COMMIT**. Một DDL vốn chỉ mất vài mili giây cũng có thể giữ lock mạnh suốt khoảng chờ của ứng dụng/DBA.

---

## 3. Các relation lock modes cần ghi nhớ

PostgreSQL có tám mode thường được mô tả trong bảng khóa cấp relation:

| Lock mode | Điểm nổi bật / thao tác thường gặp |
|---|---|
| `ACCESS SHARE` | Được `SELECT` thông thường yêu cầu; xung đột với `ACCESS EXCLUSIVE` |
| `ROW SHARE` | Được `SELECT ... FOR UPDATE/SHARE` và các biến thể khóa hàng yêu cầu trên relation; còn có row locks cụ thể |
| `ROW EXCLUSIVE` | Được `INSERT`, `UPDATE`, `DELETE`, `MERGE` và một số thao tác ghi yêu cầu |
| `SHARE UPDATE EXCLUSIVE` | Được `VACUUM` thường, `ANALYZE`, `CREATE INDEX CONCURRENTLY` và một số ALTER/maintenance yêu cầu |
| `SHARE` | Điển hình cho `CREATE INDEX` thông thường trên bảng; cho phép đọc nhưng xung đột với ghi dữ liệu |
| `SHARE ROW EXCLUSIVE` | Một số thay đổi ràng buộc như `ALTER TABLE ... ADD FOREIGN KEY`; xung đột với ghi thông thường |
| `EXCLUSIVE` | Mode mạnh, vẫn tương thích với `ACCESS SHARE` nhưng chặn nhiều mode khác |
| `ACCESS EXCLUSIVE` | Mạnh nhất; xung đột với mọi mode khác, kể cả đọc SELECT thông thường |

**Quan trọng:** các câu ở cột bên phải là ví dụ phổ biến, không phải quy tắc mỗi câu SQL chỉ lấy duy nhất một lock. Một statement có thể khóa **nhiều relation** (bảng, index, bảng tham chiếu) và nhiều kiểu khóa ở những đối tượng khác nhau.

### 3.1. Một số cặp xung đột cốt lõi

| Cặp lock mode | Có xung đột? | Ý nghĩa |
|---|---|---|
| `ACCESS SHARE` – `ACCESS EXCLUSIVE` | **Có** | SELECT có thể bị ALTER TABLE khóa mạnh chặn |
| `ACCESS SHARE` – `SHARE` | **Không** | CREATE INDEX thường vẫn cho SELECT |
| `ROW EXCLUSIVE` – `SHARE` | **Có** | INSERT/UPDATE/DELETE có thể bị CREATE INDEX thường chặn |
| `ROW EXCLUSIVE` – `SHARE UPDATE EXCLUSIVE` | **Không** | VACUUM thường và CREATE INDEX CONCURRENTLY có thể cùng tồn tại với DML thông thường |
| `SHARE UPDATE EXCLUSIVE` – chính nó | **Có** | Hai tác vụ maintenance lấy cùng mode trên một bảng có thể phải chờ |
| `ROW EXCLUSIVE` – `ACCESS EXCLUSIVE` | **Có** | ALTER TABLE khóa mạnh chặn ghi |
| `ACCESS SHARE` – `SHARE UPDATE EXCLUSIVE` | **Không** | VACUUM thường không chặn SELECT theo cặp lock mode này |
| `ROW SHARE` – `EXCLUSIVE` | **Có** | Mode EXCLUSIVE chặn nhiều truy vấn có row locking |

Bảng chỉ liệt kê **các cặp tiêu biểu**, không thay thế toàn bộ lock compatibility matrix của PostgreSQL. Ngoài relation lock, hoạt động vẫn có thể chờ row lock, I/O, CPU hoặc transaction khác.

### 3.2. Tác vụ nào thường chặn đọc, tác vụ nào thường chặn ghi?

| Tác vụ trên bảng đích | Mode điển hình | SELECT thông thường | INSERT/UPDATE/DELETE |
|---|---|---|---|
| `ALTER TABLE ADD COLUMN` | `ACCESS EXCLUSIVE` | Có thể chờ | Có thể chờ |
| `CREATE INDEX` | `SHARE` | Thường vẫn chạy | Có thể chờ |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | Thường vẫn chạy | Thường vẫn chạy |
| `VACUUM` thường | `SHARE UPDATE EXCLUSIVE` | Thường vẫn chạy | Thường vẫn chạy |
| `ANALYZE` | `SHARE UPDATE EXCLUSIVE` | Thường vẫn chạy | Thường vẫn chạy |
| `VACUUM FULL` | `ACCESS EXCLUSIVE` | Có thể chờ | Có thể chờ |
| `CLUSTER` | `ACCESS EXCLUSIVE` | Có thể chờ | Có thể chờ |

Các cột cuối phản ánh **xung đột relation lock cơ bản**. “Thường vẫn chạy” không có nghĩa chắc chắn nhanh, không thể bị chặn bởi yếu tố khác hoặc không chịu áp lực CPU/I/O.

---

## 4. Chuẩn bị một bảng lab riêng cho bài học

Tạo schema và bảng mô phỏng đơn hàng. Chỉ thực hiện trong database được phép thực hành:

~~~sql
CREATE SCHEMA IF NOT EXISTS lock_lab;

CREATE TABLE lock_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);

INSERT INTO lock_lab.orders (customer_id, status, amount)
VALUES
    (101, 'new', 150),
    (102, 'paid', 250),
    (101, 'paid', 90),
    (103, 'new', 300),
    (104, 'paid', 420);

SELECT order_id, customer_id, status, amount, created_at
FROM lock_lab.orders
ORDER BY order_id;
~~~

Bảng có năm đơn mẫu. Không chạy lại INSERT trên cùng bảng khi đang kỳ vọng đúng năm đơn, vì `order_id` identity sẽ tiếp tục tăng và có thể tạo thêm dữ liệu.

Một bảng khách hàng để thực hành thêm FOREIGN KEY:

~~~sql
CREATE TABLE lock_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

INSERT INTO lock_lab.customers (customer_id, customer_name)
VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi'),
    (104, 'Dũng');
~~~

### 4.1. Hai phiên kết nối

Mở **hai connection độc lập** vào cùng database lab, gọi là **phiên A** và **phiên B**. Dùng hai cửa sổ psql hoặc hai connection rõ ràng, không chạy toàn bộ ví dụ hai phiên nối tiếp trong một connection.

Nếu cần tìm PID để giám sát:

~~~sql
SELECT pg_backend_pid() AS current_pid;
~~~

### 4.2. Mục đích của lab

Ví dụ sau dùng `ROLLBACK` để **không giữ thay đổi ALTER hoặc cập nhật thử**. Các ví dụ `CREATE INDEX CONCURRENTLY` và bảo trì đặc biệt có giới hạn về transaction block, nên được trình bày riêng; không ép vào cùng transaction rollback.

---

## 5. ALTER TABLE: mặc định phải xem đây là một thay đổi có thể khóa mạnh

### 5.1. Vì sao ALTER TABLE cần khóa?

`ALTER TABLE` thay đổi cấu trúc hoặc quy tắc của một relation, ví dụ:

- Thêm/bỏ/đổi kiểu cột.
- Đổi tên cột hoặc bảng.
- Thêm/bỏ constraint.
- Đặt hoặc bỏ NOT NULL.
- Thay đổi partition, trigger và metadata.
- Thay đổi default, storage, generated expression hoặc các thuộc tính khác.

Để những transaction khác không đọc/ghi với một cấu trúc ở trạng thái nửa cập nhật, PostgreSQL phải lấy khóa phù hợp trên relation và đôi khi cả relation phụ thuộc.

**Quy tắc an toàn:** nhiều dạng `ALTER TABLE` dùng `ACCESS EXCLUSIVE` **trừ những subcommand được ghi nhận có lock yếu hơn**. Mức khóa cụ thể phụ thuộc **subcommand** và đôi khi phiên bản PostgreSQL.

### 5.2. Thêm cột nullable: metadata nhanh vẫn có ACCESS EXCLUSIVE

Ví dụ lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN shipping_note TEXT;

-- Dừng ở đây chỉ trong lab để quan sát, không giữ lâu.
ROLLBACK;
~~~

Dạng thêm cột nullable không default thường không cần viết lại toàn bộ dữ liệu, nên thao tác bản thân có thể nhanh. Tuy nhiên việc lấy **ACCESS EXCLUSIVE** vẫn có thể phải chờ các transaction đang giữ `ACCESS SHARE`, `ROW EXCLUSIVE` hoặc lock liên quan; và khi đã lấy được lock, nó có thể chặn truy vấn đến khi transaction kết thúc.

**Không suy luận:** “không rewrite bảng” ⇒ “không khóa bảng”.

### 5.3. Thêm cột DEFAULT hằng số: tối ưu rewrite khác với lock mode

Trong các phiên bản PostgreSQL hiện đại, thêm cột với **DEFAULT không volatile** có thể tận dụng tối ưu để không cập nhật lại toàn bộ từng row ngay tại thời điểm ALTER. Ví dụ:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN channel TEXT DEFAULT 'web';

ROLLBACK;
~~~

Điều này có thể giảm đáng kể **thời gian thực thi**, nhưng không đồng nghĩa nó không cần relation lock mạnh. Mặt khác, default dùng **biểu thức volatile** có thể khiến PostgreSQL phải tính lại và rewrite dữ liệu tùy trường hợp.

### 5.4. ALTER TYPE: rủi ro scan/rewrite, index và khóa lâu

Ví dụ minh họa:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ALTER COLUMN status TYPE VARCHAR(40);

ROLLBACK;
~~~

Không phải mọi phép đổi kiểu đều rewrite heap; điều đó phụ thuộc kiểu cũ/mới, cast và cách PostgreSQL lưu trữ. Nhưng một số phép đổi kiểu có thể:

- Đọc/viết lại khối lượng lớn dữ liệu.
- Xây lại index có liên quan.
- Tạo WAL và áp lực I/O.
- Giữ lock mạnh trong thời gian dài.

Vì vậy không triển khai đổi kiểu trên bảng lớn chỉ dựa vào việc truy vấn chạy nhanh trong lab năm dòng.

### 5.5. Bỏ cột: xong nhanh chưa chắc không có chi phí hậu kỳ

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders DROP COLUMN notes;
ROLLBACK;
~~~

Trong nhiều tình huống, bỏ cột là thay đổi metadata (giá trị vật lý cũ có thể chưa được loại ngay khỏi từng tuple). Điều này không loại bỏ yêu cầu `ACCESS EXCLUSIVE` của thao tác và không đồng nghĩa thu hồi dung lượng storage ngay lập tức.

### 5.6. Một ALTER TABLE nhiều subcommand

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders
    ADD COLUMN source_system TEXT,
    ALTER COLUMN status SET DEFAULT 'new';
ROLLBACK;
~~~

Khi kết hợp nhiều subcommand, mức khóa thường phải đủ mạnh cho **subcommand mạnh nhất** trong cùng câu `ALTER TABLE`. Không giả định lock mode yếu của một tiểu mục sẽ áp dụng cho toàn câu lệnh có nhiều thay đổi.

---

## 6. ALTER TABLE thêm và xác minh constraint

### 6.1. Ràng buộc giúp đúng dữ liệu nhưng có thể yêu cầu scan lớn

Ví dụ thêm CHECK trên bảng có nhiều hàng:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_order_status
    CHECK (status IN ('new', 'paid', 'canceled'));
~~~

Không phải một lựa chọn “không downtime” mặc định. PostgreSQL có thể cần kiểm tra dữ liệu đã tồn tại để đảm bảo tất cả hàng thỏa CHECK và phải lấy lock thích hợp trong quá trình thay đổi. Trên bảng lớn, scan/đợi lock có thể gây tác động đáng kể.

Với lab hiện tại, đừng chạy lệnh này lặp lại nhiều lần khi constraint đã tồn tại; hãy xem đây là ví dụ cấu trúc thay đổi schema.

### 6.2. Mẫu hai bước: ADD CHECK NOT VALID → VALIDATE

Để tách việc cài đặt quy tắc khỏi lần quét dữ liệu cũ:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_order_status
    CHECK (status IN ('new', 'paid', 'canceled'))
    NOT VALID;
~~~

Sau đó, ở một thời điểm phù hợp:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT chk_order_status;
~~~

Ý nghĩa:

1. `ADD ... NOT VALID` thêm constraint **mà không quét xác minh toàn bộ hàng cũ ở bước thêm**.
2. Các thao tác ghi mới hoặc sửa hàng liên quan vẫn phải tuân thủ constraint theo semantics của loại constraint; `NOT VALID` **không có nghĩa mọi dữ liệu mới được bỏ qua CHECK**.
3. `VALIDATE CONSTRAINT` kiểm tra những hàng cũ để chuyển constraint sang trạng thái đã được xác minh.
4. `VALIDATE CONSTRAINT` thường dùng lock **SHARE UPDATE EXCLUSIVE** trên bảng được validate, yếu hơn ACCESS EXCLUSIVE, cho phép DML bình thường theo compatibility mode.

Điểm quan trọng: **bước ADD NOT VALID vẫn là một ALTER TABLE có yêu cầu lock**, chỉ là lock có thể được giữ trong khoảng ngắn hơn vì tránh scan lớn ở bước đó. Nó không phải phép thay thế mọi thay đổi constraint mà không cần lập kế hoạch.

### 6.3. FOREIGN KEY: hai bảng tham gia

Ví dụ trên schema lab:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES lock_lab.customers(customer_id)
    NOT VALID;
~~~

`ADD FOREIGN KEY` là một trường hợp PostgreSQL dùng mức khóa **SHARE ROW EXCLUSIVE** trên cả bảng tham chiếu và bảng được tham chiếu, thay vì mặc định ACCESS EXCLUSIVE trong nhiều dạng ALTER khác. Mode này **xung đột với ghi thông thường** trên những relation liên quan, vì vậy phải cân nhắc cả bảng `orders` và `customers`.

Validate sau khi chuẩn bị:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT fk_orders_customer;
~~~

Việc validate có thể quét nhiều hàng nhưng dùng mức khóa nhẹ hơn để duy trì hoạt động ghi bình thường trên bảng cần xác minh, tùy các lock khác của hệ thống.

### 6.4. CHECK NOT VALID không sửa dữ liệu sai đã có

Nếu dữ liệu cũ vi phạm constraint, `ADD ... NOT VALID` vẫn có thể thành công, nhưng `VALIDATE CONSTRAINT` sẽ **báo lỗi** cho đến khi dữ liệu được làm sạch. Vì vậy migration hai bước thường có ba giai đoạn:

~~~text
ADD CONSTRAINT ... NOT VALID
          |
          v
Kiểm tra và làm sạch dữ liệu cũ theo batch
          |
          v
VALIDATE CONSTRAINT
~~~

Không coi status NOT VALID như dấu đã hoàn tất toàn bộ migration.

### 6.5. SET NOT NULL có thể cần scan

~~~sql
ALTER TABLE lock_lab.orders
    ALTER COLUMN status SET NOT NULL;
~~~

Nếu PostgreSQL chưa có bằng chứng thích hợp rằng không có NULL, thao tác đặt NOT NULL có thể cần quét bảng để kiểm tra. Trong các phiên bản hỗ trợ, một **CHECK đã được validate và chứng minh cột không NULL** có thể giúp tránh lần scan kiểm tra này. Tuy nhiên ALTER subcommand cuối vẫn có lock riêng; tránh hiểu “skip scan” là “không lock”.

---

## 7. Vì sao ALTER TABLE đang chờ có thể gây hiệu ứng hàng đợi?

Một sự cố phổ biến khi deploy:

1. Query cũ giữ `ACCESS SHARE` hoặc transaction ghi giữ `ROW EXCLUSIVE` trên bảng.
2. Migration yêu cầu `ACCESS EXCLUSIVE`, **phải chờ**.
3. Các SELECT/INSERT/UPDATE **mới** đến sau yêu cầu lock có thể bị xếp hàng phía sau để giữ công bằng với waiter.
4. Dù ALTER chưa thực hiện một thay đổi nào, latency và timeout của ứng dụng có thể tăng đột biến.

~~~text
T=0    SELECT/report dài giữ ACCESS SHARE
T=1    ALTER TABLE yêu cầu ACCESS EXCLUSIVE → WAITING
T=2    SELECT mới yêu cầu ACCESS SHARE       → có thể WAITING sau ALTER
T=3    API requests mới tiếp tục tích tụ
T=...  Report cũ kết thúc → ALTER có cơ hội lấy lock
       ALTER xong và COMMIT → các request chờ tiếp tục
~~~

### 7.1. Không phải chỉ độ dài câu ALTER quyết định rủi ro

Ngay cả lệnh “ADD COLUMN nullable” mất vài mili giây khi chạy một mình cũng có thể **đợi rất lâu** để lấy lock nếu bảng đang có transaction dài. Sau khi lấy được, nếu transaction migration chưa COMMIT thì khóa mạnh vẫn còn.

### 7.2. Timeout sớm để tránh xếp hàng lâu

Một pattern thận trọng:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE lock_lab.orders
    ADD COLUMN external_ref TEXT;

COMMIT;
~~~

Ở production, giá trị timeout phải được chọn theo chính sách triển khai, tải hệ thống và số lần thử. Nếu `lock_timeout` xảy ra, transaction thường vào trạng thái lỗi; cần **ROLLBACK** thay vì tiếp tục gửi statement. Không bật retry liên tục không backoff vì có thể tạo hàng đợi DDL dày đặc.

### 7.3. Đặt transaction thật ngắn

Tốt hơn:

~~~text
Chuẩn bị migration, xác minh data, thống nhất rollback
        |
        v
BEGIN → SET LOCAL lock_timeout → ALTER → COMMIT
        |
        v
Kiểm tra kết quả ở một transaction mới
~~~

Không nên:

~~~text
BEGIN → ALTER → chờ kỹ sư review thủ công 10 phút
      → gọi API khác → chụp ảnh màn hình → COMMIT
~~~

Khóa có thể bị giữ xuyên suốt các bước không cần thiết, gây sự cố cho toàn bộ bảng.

---

## 8. CREATE INDEX thông thường

### 8.1. Khi thêm index cũng cần bảo vệ relation

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_created
ON lock_lab.orders (customer_id, created_at);
~~~

`CREATE INDEX` thông thường quét dữ liệu bảng để xây index. Trong phần lớn trường hợp trên bảng thường, nó lấy `SHARE` lock trên bảng, có đặc điểm:

- Cho phép `SELECT` thông thường (`ACCESS SHARE` tương thích).
- Có thể chặn `INSERT`, `UPDATE`, `DELETE` vì các lệnh ghi yêu cầu `ROW EXCLUSIVE`.
- Bị ảnh hưởng bởi transaction/DDL/maintenance khác đang giữ lock xung đột.
- Nếu bảng rất lớn, thời gian build dài → thời gian ảnh hưởng ghi có thể dài.

### 8.2. Đọc được không có nghĩa không có ảnh hưởng

Trong lúc xây index, bảng vẫn có thể phục vụ SELECT, nhưng I/O/CPU để quét/sort có thể làm chậm truy vấn. Hành vi chặn ghi và áp lực tài nguyên là **hai nguồn ảnh hưởng khác nhau**.

### 8.3. CREATE INDEX trong transaction

`CREATE INDEX` thường có thể nằm trong transaction tường minh, ví dụ lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE INDEX ix_orders_status_lab
ON lock_lab.orders (status);

ROLLBACK;
~~~

Sau `ROLLBACK`, index mới không được giữ lại. Tuy nhiên **lock SHARE có thể giữ đến khi transaction kết thúc**, nên không mở transaction rồi ngồi kiểm tra GUI khi chưa COMMIT/ROLLBACK.

### 8.4. Index có khóa trên nhiều quan hệ?

Một lệnh index có thể liên quan bảng và index mới/các catalog hệ thống. Khi chẩn đoán trong `pg_locks`, đừng cho rằng chỉ có đúng một dòng lock cho một statement.

### 8.5. Khóa quan hệ khác row lock

Nếu truy vấn SELECT thông thường không bị CREATE INDEX khóa ở mức table nhưng chậm, nguyên nhân có thể là cạnh tranh CPU/I/O hoặc các lock của thao tác khác. Cần nhìn `wait_event_type` và kế hoạch thực thi, không gán mọi latency cho relation lock.

---

## 9. CREATE INDEX CONCURRENTLY: giảm chặn ghi nhưng không miễn phí

Khi ứng dụng cần tiếp tục ghi trong lúc xây index trên bảng lớn, PostgreSQL có:

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_customer_created_c
ON lock_lab.orders (customer_id, created_at);
~~~

**Lưu ý:** chỉ chạy câu này nếu tên index chưa tồn tại; khác với index ở phần 8. Nó có các đặc tính quan trọng:

1. Không chặn các thao tác `INSERT`, `UPDATE`, `DELETE` thông thường theo xung đột relation lock như CREATE INDEX thường.
2. Có thể phải **đọc bảng nhiều lượt** và **chờ những transaction/snapshot liên quan**, nên mất nhiều thời gian hơn.
3. Dùng `SHARE UPDATE EXCLUSIVE` trên bảng trong những giai đoạn phù hợp; không thể coi là “không có khóa”.
4. Có thể xung đột với maintenance/DDL khác, kể cả những thao tác cùng yêu cầu `SHARE UPDATE EXCLUSIVE`.
5. **Không được thực thi bên trong một transaction block tường minh**.
6. Có thể để lại một index **INVALID** nếu build thất bại hoặc bị hủy.
7. Có thể cần thêm dung lượng đĩa và tạo tải I/O/CPU đáng kể.

### 9.1. Ví dụ sai: cố chạy trong BEGIN

~~~sql
-- Sai: PostgreSQL từ chối CREATE INDEX CONCURRENTLY
-- trong transaction block tường minh.
BEGIN;
CREATE INDEX CONCURRENTLY ix_orders_status_c
ON lock_lab.orders (status);
ROLLBACK;
~~~

Vì command có hạn chế transaction block, migration tool nào luôn bọc mọi migration trong một BEGIN phải **tắt transactional wrapping cho đúng migration này** theo chức năng framework.

### 9.2. Không dùng IF NOT EXISTS để thay việc kiểm tra định nghĩa index

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_status_c
ON lock_lab.orders (status);
~~~

`IF NOT EXISTS` chỉ giúp tránh lỗi khi đã có relation cùng tên theo quy tắc DDL; **không chứng minh index tồn tại là index đúng định nghĩa hoặc đang VALID**.

Một index trùng tên nhưng sai cột/predicate hoặc invalid vẫn cần được kiểm tra bằng catalog.

### 9.3. Hai lượt scan và chờ các transaction

Mô hình khái quát:

~~~text
CREATE INDEX CONCURRENTLY
        |
        v
Tạo metadata index ban đầu (chưa usable)
        |
        v
Quét bảng lượt 1
        |
        v
Chờ các writer liên quan / cập nhật index
        |
        v
Quét bảng lượt 2 để bắt các thay đổi phát sinh
        |
        v
Chờ một số snapshot cũ kết thúc
        |
        v
Đánh dấu index VALID khi hoàn tất thành công
~~~

Các giai đoạn chính xác phụ thuộc loại index và phiên bản PostgreSQL. Công cụ giám sát phù hợp là `pg_stat_progress_create_index` và các catalog, không đoán từ một lần query chậm.

### 9.4. Chỉ một concurrent index build phù hợp trên cùng bảng tại một thời điểm

`CREATE INDEX CONCURRENTLY` không phải công cụ để song song tạo hàng chục index trên **cùng một bảng** không giới hạn. PostgreSQL giới hạn các concurrent index builds trên cùng relation và lock mode của chúng có thể xung đột. Nên lập lịch từng index và đánh giá tổng tải.

### 9.5. UNIQUE index xây concurrently: cần chuẩn bị dữ liệu

~~~sql
-- Ví dụ minh họa; không chạy nếu customer_id có lặp:
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_ref
ON lock_lab.orders (external_ref);
~~~

Câu trên giả sử đã tồn tại cột `external_ref`; lab mặc định chưa có. UNIQUE index sẽ thất bại nếu giá trị khóa không thỏa tính duy nhất (ngoại trừ quy tắc NULL theo phiên bản/định nghĩa). Đặc biệt, khi xây **UNIQUE INDEX CONCURRENTLY**, kiểm tra uniqueness có thể bắt đầu ảnh hưởng các transaction khác **trước khi quá trình build kết thúc**, và một build lỗi có thể để lại index invalid vẫn gây chi phí hoặc ảnh hưởng đến uniqueness enforcement tùy giai đoạn.

Do đó:

- Làm sạch dữ liệu trùng trước.
- Biết chính sách NULL/duplicate của index.
- Giám sát bước build và kết quả catalog.
- Chuẩn bị phương án xử lý invalid index.
- Không tự động retry cùng tên không kiểm tra trạng thái.

### 9.6. CONCURRENTLY trên partitioned table

PostgreSQL có những giới hạn với việc xây **partitioned index** theo cách concurrently trực tiếp trên parent. Một chiến lược triển khai trên hệ thống partition lớn là tạo index ở từng partition theo khả năng hỗ trợ, sau đó tạo/attach metadata index trên parent theo quy trình thích hợp. Cần kiểm tra phiên bản PostgreSQL và cấu trúc partition của hệ thống, không sao chép nguyên SQL nonpartitioned vào parent rồi mong chạy tự động.

### 9.7. Chọn CREATE INDEX hay CREATE INDEX CONCURRENTLY?

| Tiêu chí | `CREATE INDEX` | `CREATE INDEX CONCURRENTLY` |
|---|---|---|
| Chặn ghi trên bảng | Thường có | Tránh chặn DML thông thường do lock build |
| Cho SELECT | Thường có | Thường có |
| Chi phí/thời gian | Thường ít công hơn | Thường nhiều scan và thời gian hơn |
| Chạy trong BEGIN | Có thể | **Không** |
| Cần theo dõi invalid state | Có nhưng đơn giản hơn | Đặc biệt quan trọng |
| Phù hợp bảng rất lớn còn ghi liên tục | Cần maintenance window | Thường là ứng viên đáng cân nhắc |
| Hoàn toàn không tác động production | **Không** | **Không** |

**Tư duy chọn:** quyết định theo yêu cầu availability, khối lượng bảng, write traffic, thời hạn thực hiện và khả năng kiểm soát failure, không chỉ theo cú pháp ngắn hơn.

---

## 10. Kiểm tra và xử lý index INVALID

### 10.1. Index concurrent có thể thất bại sau khi đã tạo metadata

Nếu build `CREATE INDEX CONCURRENTLY` bị hủy, hết tài nguyên, gặp duplicate khi xây UNIQUE hoặc bị một lỗi khác, PostgreSQL có thể để lại một index được khai báo trong catalog nhưng **chưa hợp lệ để planner dùng cho truy vấn**.

Không được chỉ nhìn tên index có tồn tại rồi kết luận deploy thành công.

### 10.2. Kiểm tra pg_index

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready_for_inserts,
    i.indislive AS is_live,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'lock_lab'
  AND tbl.relname = 'orders'
ORDER BY index_name;
~~~

Ý nghĩa các cờ quan trọng:

- `indisvalid`: index hợp lệ để được dùng theo quy tắc planner.
- `indisready`: trạng thái có thể nhận thay đổi từ các thao tác ghi.
- `indislive`: index có còn được coi là live trong cơ chế quản lý nội bộ hay không.

Chúng không thay thế việc đọc lỗi của command và kiểm tra định nghĩa thực tế.

### 10.3. Các hướng phục hồi phổ biến

Nếu thấy một index invalid:

1. Xác minh câu lệnh build trước đã **thực sự kết thúc**, không phải đang chạy.
2. Đọc lỗi gốc và xác định duplicate data, thiếu tài nguyên, deadlock, timeout hay nguyên nhân khác.
3. Kiểm tra index có đang tham gia constraint/uniqueness hay quan hệ phụ thuộc khác không.
4. Theo quy trình hỗ trợ, **DROP INDEX CONCURRENTLY** index invalid để dọn rồi tạo lại, hoặc dùng lựa chọn **REINDEX CONCURRENTLY** khi phù hợp.
5. Kiểm tra lại `indisvalid` và khả năng phục vụ truy vấn.

Ví dụ cho **index thử đã bị xác nhận invalid và không thuộc constraint**, không phải lệnh mặc định để chạy mù quáng:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS lock_lab.ix_orders_status_c;
~~~

`DROP INDEX CONCURRENTLY` có giới hạn riêng: không thực thi trong transaction block, không hỗ trợ tùy ý mọi chỉ mục đang dùng để thực thi constraint, và không hỗ trợ `CASCADE` như cách DROP INDEX thường. Kiểm tra dependencies trước khi xóa.

### 10.4. Không dùng DROP INDEX tùy ý để sửa sự cố nhanh

Index có thể phục vụ:

- Primary key/unique constraint.
- Các truy vấn quan trọng.
- Foreign key join paths.
- Bảo đảm uniqueness khi nhiều writer chạy đồng thời.

Xóa index không có phương án phục hồi có thể khiến hệ thống **từ nghẽn DDL chuyển sang chậm truy vấn hoặc sai invariant**. Điều tra trạng thái và kế hoạch trước khi thao tác.

---

## 11. REINDEX và REINDEX CONCURRENTLY

### 11.1. REINDEX giải quyết vấn đề gì?

`REINDEX` xây lại index từ dữ liệu bảng, có thể được dùng khi index hỏng, bị bloat lớn, cần thay đổi storage/collation theo quy trình vận hành, hoặc thực hiện maintenance được khuyến nghị.

Ví dụ:

~~~sql
REINDEX INDEX lock_lab.ix_orders_customer_created;
~~~

Chỉ chạy khi index đã tồn tại và có kế hoạch thích hợp. `REINDEX` thông thường có thể chặn các thao tác ghi trên bảng nguồn trong thời gian xây lại, đồng thời có thể khóa index ở mức gây ảnh hưởng đến các truy vấn đang dựa vào index đó.

### 11.2. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY lock_lab.ix_orders_customer_created;
~~~

Mục tiêu là xây lại index với mức chặn DML nhẹ hơn, gần với tinh thần concurrent index build. Nhưng cần nhớ:

- Dùng nhiều bước và chờ những transaction/snapshot liên quan.
- Có thể tốn **đĩa bổ sung** vì cần tồn tại phiên bản index cũ/mới trong quá trình chuyển đổi.
- **Không dùng trong transaction block tường minh**.
- Có các giới hạn về đối tượng hỗ trợ và các tình huống system/shared catalog.
- Có thể tạo các index tạm/invalid còn sót lại nếu thất bại ở những giai đoạn nhất định; cần điều tra catalog trước khi chạy lại.

### 11.3. Không nhầm REINDEX với ANALYZE

`ANALYZE` cập nhật thống kê cho query planner; `REINDEX` xây lại cấu trúc vật lý của index. Khi truy vấn bỗng chọn plan kém do thống kê cũ, không nên lập tức chạy REINDEX như giải pháp mặc định.

### 11.4. Không nhầm REINDEX với VACUUM

`VACUUM` quản lý dead tuples, visibility/freezing và không gian tái sử dụng. `REINDEX` xây lại index. Chúng giải quyết những vấn đề liên quan nhưng không đồng nhất, có chi phí và lock behavior khác nhau.

---

## 12. VACUUM thường và AUTOVACUUM

### 12.1. Vì sao cần VACUUM?

PostgreSQL dùng MVCC: `UPDATE` có thể tạo version mới, `DELETE` đánh dấu version cũ. Sau khi không còn snapshot cần version cũ, chúng có thể được xử lý làm dead tuples. `VACUUM` giúp:

- Thu hồi không gian có thể tái sử dụng cho các tuple.
- Hỗ trợ dọn cấu trúc index/heap theo phương án engine.
- Cập nhật thông tin visibility map và các metadata bảo trì.
- Quản lý freezing transaction IDs, giảm nguy cơ wraparound.

### 12.2. VACUUM thường sử dụng khóa nhẹ hơn

~~~sql
VACUUM lock_lab.orders;
~~~

`VACUUM` thông thường lấy `SHARE UPDATE EXCLUSIVE` trên bảng đang vacuum, về mặt lock compatibility thường **không chặn SELECT/INSERT/UPDATE/DELETE bình thường**.

Tuy nhiên:

- Có thể tranh chấp với DDL hoặc maintenance cũng dùng lock tương tự/mạnh hơn.
- Tiêu thụ I/O/CPU và có thể ảnh hưởng latency.
- Có thể phải chờ các hoạt động khác, hoặc bị yêu cầu khóa xung đột làm gián đoạn theo quy tắc bảo trì.
- Không phải mọi dead tuple đều dọn được nếu có snapshot, replication slot hoặc transaction chưa kết thúc còn cần chúng.

### 12.3. VACUUM không nằm trong transaction block

Ví dụ **sai**:

~~~sql
BEGIN;
VACUUM lock_lab.orders;
COMMIT;
~~~

PostgreSQL không cho `VACUUM` thường chạy trong transaction block tường minh. Điều này cũng quan trọng khi dùng migration framework tự bọc mọi SQL bằng transaction.

### 12.4. Autovacuum

Autovacuum là tiến trình nền PostgreSQL tự thực hiện VACUUM/ANALYZE theo điều kiện cấu hình. Nó đóng vai trò quan trọng để:

- Dọn phiên bản cũ định kỳ.
- Duy trì thống kê.
- Đảm bảo tuổi XID/MultiXact không vượt ngưỡng an toàn.

Autovacuum cũng cần relation lock phù hợp; không “miễn xung đột” với mọi DDL. Một số autovacuum thông thường có thể bị hủy khi có xung đột lock, nhưng những tiến trình phục vụ chống wraparound có yêu cầu bảo vệ đặc biệt. **Không tắt autovacuum chỉ để một DDL chạy nhanh** mà chưa có kế hoạch thay thế bảo trì và quản lý tuổi XID.

### 12.5. VACUUM không nhất thiết làm file nhỏ ngay

Regular VACUUM thường làm không gian trong bảng **có thể tái sử dụng**, không bảo đảm ngay lập tức giảm kích thước file vật lý tương ứng tất cả dead tuples. Trả dung lượng về OS thường đòi điều kiện cụ thể hoặc thao tác rewrite như `VACUUM FULL` với chi phí khóa mạnh.

### 12.6. Transaction dài cản trở dọn dead tuples

~~~text
Reader REPEATABLE READ giữ snapshot cũ
           |
           v
Writer UPDATE tạo nhiều version → COMMIT
           |
           v
VACUUM thấy một số version vẫn có thể cần cho reader
           |
           v
Không thể thu hồi các version đó quá sớm
~~~

Một bảng bị bloat không phải lúc nào do “VACUUM không chạy”, mà có thể do **VACUUM không thể thu hồi** dữ liệu vì snapshot/horizon vẫn bị giữ.

---

## 13. ANALYZE: thu thập thống kê với lock bảo trì

### 13.1. ANALYZE dùng để làm gì?

~~~sql
ANALYZE lock_lab.orders;
~~~

`ANALYZE` thu thập thống kê phục vụ planner, ví dụ phân bố giá trị, số hàng, độ chọn lọc và histogram liên quan. Nó **không** tạo index và **không** tự rewrite toàn bộ bảng để thu gọn file.

### 13.2. Tại sao cần khóa?

Vì ANALYZE phải đọc relation và cập nhật metadata thống kê một cách nhất quán, nó thường lấy `SHARE UPDATE EXCLUSIVE`. Mode này tương thích với đọc/ghi thông thường nhưng có thể xung đột với:

- `VACUUM` và một số maintenance cùng mode.
- `CREATE INDEX CONCURRENTLY` trên cùng bảng.
- `ALTER TABLE` lock mạnh hơn.
- Một số lệnh cần `SHARE`/`ACCESS EXCLUSIVE`.

### 13.3. Khi nào chạy ANALYZE chủ động?

- Sau bulk load lớn.
- Sau cập nhật phân bố dữ liệu lớn mà thống kê còn cũ.
- Khi một truy vấn đổi sang kế hoạch kém và `EXPLAIN` cho thấy ước lượng rows sai đáng kể.
- Sau những maintenance/migration đặc biệt khiến planner cần dữ liệu mới.

Không chạy ANALYZE liên tục một cách mù quáng trên bảng rất lớn vào giờ cao điểm; autovacuum có thể đã đảm nhiệm đủ cho workload.

### 13.4. ALTER và ANALYZE: thứ tự triển khai

Nếu vừa thêm cột hoặc dữ liệu lớn rồi index:
 
~~~text
Migration schema hợp lệ
       |
       v
Backfill/bulk load theo batch (nếu cần)
       |
       v
Tạo index / kiểm tra status VALID
       |
       v
ANALYZE khi phù hợp
       |
       v
EXPLAIN các truy vấn quan trọng
~~~

Tùy workload, ANALYZE có thể được đặt ở giai đoạn khác. Điều quan trọng là không biến ANALYZE thành câu lệnh “chắc chắn sửa được mọi query chậm” mà không đo plan.

---

## 14. VACUUM FULL và CLUSTER: rewrite bảng với ACCESS EXCLUSIVE

### 14.1. VACUUM FULL khác regular VACUUM

~~~sql
-- Chỉ minh họa; không chạy trên production khi chưa có
-- maintenance window và tính toán dung lượng/lock.
VACUUM FULL lock_lab.orders;
~~~

`VACUUM FULL` viết lại bảng sang dạng compact hơn để thu hồi dung lượng vật lý. Nó lấy `ACCESS EXCLUSIVE` trên bảng và có thể **chặn SELECT lẫn DML** trong suốt thời gian xử lý.

Hệ quả:

- Bảng lớn có thể bị ảnh hưởng lâu.
- Cần **không gian đĩa trống bổ sung** để rewrite và cấu trúc liên quan.
- Có thể tạo WAL lớn và gây lag replica.
- Các `ctid` của tuple có thể thay đổi.
- Không được chạy trong transaction block tường minh.

### 14.2. CLUSTER

~~~sql
-- Chỉ thực hành trên database lab khi hiểu chi phí và khóa.
CLUSTER lock_lab.orders USING ix_orders_customer_created;
~~~

`CLUSTER` tái sắp xếp dữ liệu vật lý của bảng theo một index đã chọn. Trong hình thức thông thường, nó cần `ACCESS EXCLUSIVE` và có thể ngăn đọc/ghi trên bảng trong lúc rewrite.

`CLUSTER` không tự duy trì thứ tự vật lý mãi mãi sau các INSERT/UPDATE mới. Nếu muốn thứ tự trả về của SELECT, **vẫn dùng ORDER BY**, không dựa vào việc bảng từng CLUSTER.

### 14.3. So sánh

| Đặc điểm | `VACUUM` thường | `VACUUM FULL` | `CLUSTER` |
|---|---|---|---|
| Mục đích | Dọn dead tuples/visibility/freeze | Rewrite compact bảng | Rewrite sắp vật lý theo index |
| Lock điển hình | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE | ACCESS EXCLUSIVE |
| SELECT thông thường | Thường không bị chặn bởi relation lock | Có thể bị chặn | Có thể bị chặn |
| DML thông thường | Thường không bị chặn bởi relation lock | Có thể bị chặn | Có thể bị chặn |
| Đĩa/WAL | Tùy lượng dọn, không rewrite toàn bảng | Có thể rất lớn | Có thể rất lớn |
| Transaction block | Không | Không | Phụ thuộc hình thức lệnh/quy tắc phiên bản; lập lịch riêng |
| Mục tiêu trả dung lượng về OS | Không bảo đảm | Phù hợp hơn khi thực sự cần compact | Rewrite không nhất thiết là công cụ giảm bloat tối ưu |

### 14.4. Thận trọng khi có replica

Bảo trì rewrite có thể tạo lượng WAL lớn, gây áp lực replication và I/O; trên standby có thể xuất hiện conflict với query chạy lâu tùy cấu hình. Vì vậy kế hoạch maintenance không chỉ cân nhắc primary mà còn phải tính:

- Số replica và độ trễ cho phép.
- Mức WAL tạo ra và khả năng lưu giữ.
- Dung lượng đĩa của primary/replica.
- Thời gian chặn đọc/ghi ở primary.
- Chiến lược failover nếu maintenance gặp sự cố.

---

## 15. Một số lệnh bảo trì khác và phạm vi lock

### 15.1. TRUNCATE

~~~sql
-- Ví dụ chỉ để hiểu, KHÔNG chạy lên bảng đang có dữ liệu cần giữ.
TRUNCATE TABLE lock_lab.orders;
~~~

`TRUNCATE` lấy `ACCESS EXCLUSIVE` trên bảng đích và thường không được chọn khi yêu cầu phải giữ các transaction SELECT hoạt động bình thường. Nó có semantics khác `DELETE` (bao gồm trigger, identity, khóa và MVCC snapshot) nên **không tự đổi DELETE thành TRUNCATE để tăng tốc**.

### 15.2. REFRESH MATERIALIZED VIEW

Nếu hệ thống dùng materialized view, PostgreSQL hỗ trợ:

~~~sql
REFRESH MATERIALIZED VIEW some_schema.sales_summary;
~~~

và một hình thức:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY some_schema.sales_summary;
~~~

Tên view ở đây là **minh họa**, không tồn tại trong lab. Refresh thông thường lấy lock mạnh trên **materialized view**, có thể chặn người đọc nó trong khi refresh; dạng CONCURRENTLY được thiết kế giảm chặn đọc, nhưng có điều kiện tiên quyết như **một UNIQUE index phù hợp, bao phủ tất cả hàng và không dựa vào expression/WHERE predicate** cùng những hạn chế khác.

Đừng nhầm `REFRESH ... CONCURRENTLY` với `CREATE INDEX CONCURRENTLY`: hai lệnh giải quyết hai bài toán khác nhau, và điều kiện sử dụng khác nhau.

### 15.3. ATTACH PARTITION

Với bảng phân vùng, `ALTER TABLE ... ATTACH PARTITION` có đặc điểm lock riêng: parent partitioned table thường có thể dùng `SHARE UPDATE EXCLUSIVE` thay vì `ACCESS EXCLUSIVE`, nhưng relation được attach và bảng con/những relation liên quan có thể cần **lock mạnh** hoặc scan để xác minh partition bounds.

Một `CHECK` thích hợp đã được validate trên child có thể giúp tránh một số scan xác minh dữ liệu. Không áp một bảng lock duy nhất cho toàn bộ operation ATTACH vì nó có **nhiều relation**.

### 15.4. Thêm PRIMARY KEY/UNIQUE constraint bằng index đã chuẩn bị

Trên bảng lớn, một chiến lược giảm thời gian chặn ghi:

1. Tạo một **unique index phù hợp** bằng `CREATE UNIQUE INDEX CONCURRENTLY`.
2. Xác nhận index đã VALID và dữ liệu/definition thỏa yêu cầu.
3. Chạy `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` để dùng index đã có, giảm nhu cầu xây lại index trong ALTER.

Ví dụ schema minh họa (không phải tên index đã tồn tại sẵn):

~~~sql
-- Bước 1, chạy ngoài transaction block:
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_code
ON lock_lab.orders (external_code);

-- Bước 2, sau khi kiểm tra VALID, trong migration riêng:
ALTER TABLE lock_lab.orders
ADD CONSTRAINT uq_orders_external_code
UNIQUE USING INDEX ux_orders_external_code;
~~~

**Điều kiện:** cột `external_code` phải được tạo trước; unique index phải hợp lệ, không partial/expression và phù hợp cho kiểu constraint. Bước ALTER vẫn cần lock DDL, tuy có thể ngắn vì tránh xây index trong bước đó. Với PRIMARY KEY, yêu cầu NOT NULL và kiểm tra dữ liệu liên quan có thể tăng thời gian/lock; phải đọc điều kiện của đúng subcommand trên phiên bản triển khai.

---

## 16. Khóa của index build và VACUUM xung đột ra sao?

Một số tình huống điển hình:

### 16.1. CREATE INDEX CONCURRENTLY vs VACUUM

Cả hai có thể cần `SHARE UPDATE EXCLUSIVE` trên cùng bảng ở các giai đoạn thích hợp. Mode này **xung đột với chính nó**.

~~~text
VACUUM orders: giữ SHARE UPDATE EXCLUSIVE
        |
        v
CREATE INDEX CONCURRENTLY orders: đợi lock phù hợp
~~~

Hoặc chiều ngược lại. Đây là lý do cần theo dõi maintenance đang chạy trước khi bắt đầu index build, dù cả hai thường không chặn DML.

### 16.2. CREATE INDEX thường vs writer

~~~text
Writer (INSERT/UPDATE): ROW EXCLUSIVE
             ↕  xung đột
CREATE INDEX thường: SHARE
~~~

Nếu writer còn transaction mở, CREATE INDEX có thể chờ. Khi CREATE INDEX lấy SHARE thành công, các write mới có thể chờ cho đến khi index build và transaction chứa nó hoàn tất.

### 16.3. ALTER TABLE vs SELECT

~~~text
SELECT: ACCESS SHARE
           ↕  xung đột
ALTER TABLE ADD COLUMN: ACCESS EXCLUSIVE
~~~

Một SELECT dài hoặc transaction có SELECT đã được giữ khóa phù hợp có thể trì hoãn ALTER; khi ALTER đang chờ, các SELECT mới cũng có thể xếp hàng.

### 16.4. Không đánh đồng lock wait và I/O wait

Từ góc nhìn ứng dụng, câu SQL "đang chậm" có thể do:

- Đợi relation lock.
- Đợi transaction ID/row lock.
- Đợi I/O đọc bảng/index.
- CPU sort/hash hoặc tạo WAL.
- Throttling, checkpoint, replication, network.

Chỉ có thông tin wait events, query plan và metrics mới giúp phân biệt. Không tăng lock_timeout để chữa CPU/I/O saturation.

---

## 17. Thời hạn khóa và transaction boundary

### 17.1. Một thao tác DDL ngắn vẫn có thể giữ lock lâu

Ví dụ **chỉ chạy trong lab**:

~~~sql
BEGIN;

ALTER TABLE lock_lab.orders
    ADD COLUMN migration_flag BOOLEAN DEFAULT false;

-- DDL đã thực thi xong nhưng transaction chưa COMMIT.
-- Không chuyển sang làm việc khác ở đây.
ROLLBACK;
~~~

Nếu bạn giữ transaction mở trong vài phút sau ALTER, các transaction khác có thể phải chờ, mặc dù việc thêm cột đã xong.

### 17.2. Các câu lệnh bị lỗi trong transaction

Khi `ALTER TABLE` bị `lock_timeout` trong một transaction, transaction có thể chuyển sang trạng thái **aborted**. Các SQL thông thường tiếp theo có thể báo `25P02`.

Cách phục hồi:

~~~sql
ROLLBACK;
~~~

Không gửi lệnh DDL thứ hai ngay trên cùng transaction aborted, cũng không cố `COMMIT` để ép qua lỗi. Trong migration tool, cần kết thúc unit-of-work rồi retry có giới hạn ở thời điểm thích hợp.

### 17.3. lock_timeout không phải statement_timeout

| Tùy chọn | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| `lock_timeout` | Thời gian chờ **lấy lock** | DDL không được xếp hàng 60 giây chờ SELECT dài |
| `statement_timeout` | Thời gian thực thi **statement** | ALTER/CREATE INDEX không chạy quá chính sách 30 phút |
| `idle_in_transaction_session_timeout` | Thời gian session ở trạng thái idle trong transaction | Ngăn bỏ quên BEGIN sau DDL |
| `deadlock_timeout` | Thời gian chờ trước khi kiểm tra deadlock / log lock wait theo cấu hình | Không tự thay như mẹo tối ưu |
| Timeout ở application/job | Hạn mức tổng của request/migration | Job deploy phải báo lỗi khi vượt ngân sách |

`SET LOCAL` trong transaction là cách cô lập thay đổi tham số cho scope đó:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE lock_lab.orders
    ADD COLUMN app_tag TEXT;

ROLLBACK;
~~~

Với `CREATE INDEX CONCURRENTLY` không dùng BEGIN, cần cấu hình timeout **ở session hoặc phía client** theo cách có kiểm soát, và reset/khôi phục session sau đó; không chèn `SET LOCAL` ngoài transaction rồi mong nó tự áp dụng đúng cho command tiếp theo.

---

## 18. Giám sát lock wait bằng pg_stat_activity

Khi ứng dụng báo “mọi SELECT đột nhiên chậm ngay lúc deploy”, bước đầu là xác định **backend nào đang chờ** và **chờ điều gì**, không tự kill process.

### 18.1. Xem các phiên hiện tại

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
    now() - query_start AS query_age,
    LEFT(query, 180) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
~~~

Ý nghĩa:

| Trường | Cách đọc |
|---|---|
| `pid` | Backend process ID |
| `application_name` | Giúp truy nguồn service/migration job nếu client đặt đúng |
| `state` | `active`, `idle`, `idle in transaction`, ... |
| `xact_start` | Thời điểm bắt đầu transaction hiện tại nếu có |
| `query_start` | Thời điểm statement tương ứng bắt đầu |
| `wait_event_type` | Nhóm chờ, ví dụ `Lock` hoặc `IO` |
| `wait_event` | Loại sự kiện chờ cụ thể |
| `query` | Câu lệnh đang/đã chạy, có thể chứa dữ liệu nhạy cảm và bị giới hạn quyền xem |

**Cảnh báo:** khi đang ở `idle in transaction`, cột `query` có thể hiển thị statement **đã thực thi gần nhất**, không nhất thiết “SQL hiện đang chạy”. Backend có thể chặn người khác dù trông có vẻ nhàn rỗi.

### 18.2. Lọc những phiên đang chờ Lock

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event,
    now() - query_start AS waiting_duration,
    LEFT(query, 180) AS statement
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY query_start;
~~~

`wait_event_type='Lock'` báo đang chờ một lock, nhưng `wait_event` có thể là `relation`, `transactionid`, `virtualxid` hoặc loại khác. Không giả định mọi lock wait đều là khóa bảng do ALTER TABLE.

### 18.3. Query nhìn xact_start khác query_start

- `xact_start` giúp phát hiện transaction mở lâu.
- `query_start` giúp xem statement hiện tại/statement gần nhất.
- `state_change` (nếu chọn thêm) cho biết thời điểm backend đổi trạng thái.

Một session có statement đã chạy xong nhưng transaction vẫn mở **không có nghĩa lock đã được nhả**.

---

## 19. Xác định blocker bằng pg_blocking_pids()

### 19.1. Truy vấn nhanh cho từng session chờ

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 180) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
~~~

`pg_blocking_pids(pid)` trả mảng PID đang chặn backend đích theo phân tích của PostgreSQL. Nó hữu ích hơn cách tự JOIN `pg_locks` theo relation rồi đoán blocker, vì cơ chế chờ còn liên quan **lock queues** và nhiều loại lock.

### 19.2. Hiển thị từng blocker cùng query

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    blocking.pid AS blocking_pid,
    blocking.application_name AS blocking_app,
    blocking.state AS blocking_state,
    blocking.xact_start AS blocking_xact_start,
    LEFT(waiting.query, 160) AS waiting_sql,
    LEFT(blocking.query, 160) AS blocking_sql
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(waiting.pid)
) AS blocker(blocking_pid)
JOIN pg_stat_activity AS blocking
  ON blocking.pid = blocker.blocking_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.pid, blocking.pid;
~~~

Query này có thể cho thấy một backend `idle in transaction` đang giữ lock dù SQL cuối trông chỉ là SELECT hoặc ALTER đã chạy xong.

Không tự động terminate blocker mà không biết:

- Ai sở hữu transaction?
- Transaction có đang xử lý thanh toán hoặc migration dở không?
- Việc ngắt có làm rollback thay đổi nhiều phút hay mất trạng thái ứng dụng không?
- Có phương án an toàn hơn như yêu cầu service tự COMMIT/ROLLBACK, giảm tải hoặc rút timeout không?

### 19.3. Blocking PID không phải toàn bộ câu chuyện

Một backend có thể chờ vì một lock đang được cấp cho transaction khác **hoặc** vì lock waiter có độ ưu tiên trước nó trong hàng đợi. Vì vậy nhìn từng cặp “A chặn B” cần đặt trong bối cảnh cả chuỗi waiter và lịch khai thác hệ thống.

Nếu blocker là chính transaction của một thao tác DDL, hãy xác minh ai đang giữ session và commit/rollback đã diễn ra chưa; không đoán từ tên query cuối.

---

## 20. Quan sát chi tiết relation locks qua pg_locks

### 20.1. Xem lock của bảng orders

~~~sql
SELECT
    l.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.waitstart
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.relation = 'lock_lab.orders'::regclass
ORDER BY l.granted, l.pid, l.mode;
~~~

`granted=true`: lock đã được cấp.

`granted=false`: backend đang chờ cấp lock đó. Với một số loại lock, `pid` có thể NULL nếu lock thuộc prepared transaction; không nên coi mọi lock đều thuộc backend đang chạy trong `pg_stat_activity`.

`waitstart` có thể NULL nếu lock vừa bắt đầu đợi hoặc thông tin không được thiết lập trong ngữ cảnh tương ứng; không dùng duy nhất nó để kết luận thứ tự tất cả blocker.

### 20.2. Xem các lock relation của toàn schema lab

~~~sql
SELECT
    l.pid,
    a.application_name,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted
FROM pg_locks AS l
JOIN pg_class AS c ON c.oid = l.relation
JOIN pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE n.nspname = 'lock_lab'
  AND l.locktype = 'relation'
ORDER BY relation_name::text, l.pid, l.mode;
~~~

Một statement có thể giữ lock trên bảng, index và đối tượng phụ thuộc. Không đếm số hàng trong `pg_locks` rồi suy ra số row bị khóa. **Row-level locks thông thường không được biểu diễn đầy đủ như một dòng `pg_locks` cho từng hàng**; việc chờ cập nhật row thường thể hiện qua transaction-id/tuple lock tương ứng.

### 20.3. Không chỉ xem mode mà bỏ qua granted

Một dòng:

~~~text
mode = AccessExclusiveLock
granted = false
~~~

có nghĩa backend **đang chờ** ACCESS EXCLUSIVE, không phải đã chiếm độc quyền bảng. Nhưng chính waiter đó vẫn có thể ảnh hưởng những request đến sau do hàng đợi.

### 20.4. Đừng chỉnh catalog/pg_locks

`pg_locks` là view chẩn đoán, không phải bảng để UPDATE hoặc DELETE. Cách giải quyết xung đột là **kết thúc transaction, điều chỉnh lịch/timeout hoặc xử lý session theo quy trình vận hành**, không “xóa dòng khóa” trong SQL.

---

## 21. Giám sát CREATE INDEX CONCURRENTLY bằng progress view

### 21.1. pg_stat_progress_create_index

Trong những phiên bản PostgreSQL có hỗ trợ, khi có index build đang chạy:

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS table_name,
    p.index_relid::regclass AS index_name,
    p.command,
    p.phase,
    p.lockers_total,
    p.lockers_done,
    p.current_locker_pid,
    p.blocks_total,
    p.blocks_done,
    p.tuples_total,
    p.tuples_done
FROM pg_stat_progress_create_index AS p
WHERE p.datname = current_database()
ORDER BY p.pid;
~~~

Cột `phase` là chìa khóa để nhận biết build đang:

- Khởi tạo hoặc đợi writers liên quan.
- Xây chỉ mục từ dữ liệu.
- Validate index.
- Đợi những snapshot cũ hoàn tất.
- Thực hiện các giai đoạn khác theo phiên bản/cơ chế index access method.

Tên phase chi tiết có thể thay đổi theo phiên bản. Nếu view không có dòng, có thể **không có index build đang chạy** lúc truy vấn, chứ không chứng minh index trước đó VALID.

### 21.2. Chẩn đoán một build “đứng yên”

Khi một index build mất nhiều thời gian:

1. Xem `phase`.
2. Nếu chờ locker/writer/snapshot, dùng `pg_blocking_pids()` và các session có transaction lâu.
3. Nếu đang xây/scan, theo dõi tiến độ blocks/tuples (không phải mọi phase đều cập nhật mọi counter).
4. Xem I/O, disk, WAL/replica lag và tình trạng autovacuum.
5. Sau khi command kết thúc, xác minh `pg_index.indisvalid`.

Không lấy phép chia `blocks_done / blocks_total` làm “% job hoàn thành” toàn diện, vì một build có nhiều phase với chi phí khác nhau.

### 21.3. Không có progress view không phải build vô hại

Một command chạy nhanh có thể không kịp xuất hiện trong view. Command lớn có thể có phase đang chờ mà số block đã scan không tăng. Kết hợp progress với `pg_stat_activity` và các metric hệ thống.

---

## 22. Giám sát VACUUM, ANALYZE, CLUSTER

### 22.1. Progress của VACUUM thường

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
WHERE datname = current_database()
ORDER BY pid;
~~~

View này phù hợp cho regular VACUUM, với những phase như scanning heap, vacuuming indexes, vacuuming heap, cleaning up indexes (tùy bản PostgreSQL). `VACUUM FULL` dùng đường thực thi rewrite khác, thường được giám sát qua `pg_stat_progress_cluster`.

### 22.2. VACUUM FULL / CLUSTER rewrite

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written
FROM pg_stat_progress_cluster
WHERE datname = current_database()
ORDER BY pid;
~~~

`pg_stat_progress_cluster` có thể hiển thị các tác vụ `CLUSTER` và `VACUUM FULL` liên quan rewrite. Khi số lượng tuple lớn, cần cân nhắc thời gian và disk headroom; thông tin progress không đồng nghĩa có thể dừng/resume đúng điểm.

### 22.3. Progress của ANALYZE

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    sample_blks_total,
    sample_blks_scanned
FROM pg_stat_progress_analyze
WHERE datname = current_database()
ORDER BY pid;
~~~

Các view progress và cột cụ thể phụ thuộc **phiên bản PostgreSQL**. Nếu môi trường cũ chưa có view, xem `pg_stat_activity` và công cụ monitoring tương ứng thay vì kết luận command không chạy.

### 22.4. Kiểm tra kết quả sau maintenance

Sau khi chạy maintenance:

- Bảo đảm lệnh trả kết quả thành công.
- Kiểm tra index state nếu liên quan.
- Xem thống kê/bloat và plan thực tế khi cần.
- Xem tình trạng replication nếu thao tác sinh WAL lớn.
- Không chỉ ghi “VACUUM đã chạy” mà bỏ qua các blockers khiến nó không dọn được phần cần thiết.

---

## 23. Thí nghiệm hai phiên: SELECT chặn ALTER TABLE

Mục đích: quan sát một `SELECT` đã kết thúc statement nhưng transaction vẫn mở khiến `ALTER TABLE` chờ `ACCESS EXCLUSIVE`.

### 23.1. Phiên A — giữ transaction mở sau SELECT

~~~sql
BEGIN;

SELECT COUNT(*) AS order_count
FROM lock_lab.orders;

-- CHƯA COMMIT/ROLLBACK.
-- Giữ phiên A tại đây trong khi chuyển sang B.
~~~

SELECT trên bảng tạo `ACCESS SHARE` phù hợp và trong transaction tường minh lock đó thường được giữ tới khi transaction kết thúc.

### 23.2. Phiên B — thử ALTER với timeout ngắn

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN lab_lock_probe TEXT;
~~~

Vì A vẫn giữ `ACCESS SHARE`, B yêu cầu `ACCESS EXCLUSIVE` nên phải chờ, rồi có thể gặp lỗi:

~~~text
ERROR: canceling statement due to lock timeout
SQLSTATE: 55P03
~~~

Ngay sau lỗi trong transaction B:

~~~sql
ROLLBACK;
~~~

### 23.3. Phiên A — nhả lock

~~~sql
ROLLBACK;
~~~

### 23.4. Phiên B — thử lại khi không còn blocker

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN lab_lock_probe TEXT;

-- ALTER có thể hoàn thành nhanh trên bảng 5 dòng.
-- Dùng ROLLBACK để không lưu lại cột lab_lock_probe.
ROLLBACK;
~~~

**Kết luận:** thời gian chờ lock không nhất thiết phản ánh chi phí xử lý metadata hoặc số hàng trong bảng.

### 23.5. Tình huống câu SELECT mới bị xếp sau ALTER

Nếu có phiên C và chạy đúng lúc B đang **chờ ACCESS EXCLUSIVE**, SELECT mới ở C có thể bị xếp sau yêu cầu DDL của B. Điều này được gọi là **head-of-line blocking** trong hàng đợi lock. Không cần tự gây hiện tượng này trên production để xác nhận nguyên lý.

---

## 24. Thí nghiệm hai phiên: writer chặn CREATE INDEX thường

### 24.1. Phiên A — giữ lock từ UPDATE

~~~sql
BEGIN;

UPDATE lock_lab.orders
SET amount = amount + 1
WHERE order_id = (
    SELECT MIN(order_id) FROM lock_lab.orders
);

-- Chưa COMMIT/ROLLBACK.
~~~

UPDATE tạo `ROW EXCLUSIVE` trên relation và các row-level/transaction locks cần thiết.

### 24.2. Phiên B — tạo index thường

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE INDEX ix_orders_amount_probe
ON lock_lab.orders (amount);
~~~

`CREATE INDEX` thường cần `SHARE`, xung đột với `ROW EXCLUSIVE` của A nên có thể chờ và timeout.

Phiên B:

~~~sql
ROLLBACK;
~~~

Phiên A:

~~~sql
ROLLBACK;
~~~

### 24.3. Vì sao B không nên đợi vô hạn?

Vì môi trường thật có thể có những transaction ghi dài, một CREATE INDEX thường đang chờ dễ kéo theo các writer mới bị xếp hàng, tạo sự cố. Một giới hạn `lock_timeout` ngắn giúp migration thất bại có kiểm soát và được thử lại có kế hoạch.

### 24.4. Bảng lớn còn ghi liên tục

Nếu có yêu cầu index và không được dừng ghi, cân nhắc `CREATE INDEX CONCURRENTLY` cùng progress monitoring. Nhưng cần tính I/O, snapshot wait, timeouts, invalid index cleanup và thời điểm triển khai phù hợp.

---

## 25. Thực hành CREATE INDEX CONCURRENTLY có kiểm soát

Không đặt lệnh này trong BEGIN. Trên bảng lab, có thể thực hiện như một command độc lập:

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_status_created_c
ON lock_lab.orders (status, created_at);
~~~

Sau đó xác nhận:

~~~sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid = 'lock_lab.orders'::regclass
  AND idx.relname = 'ix_orders_status_created_c';
~~~

Khi test xong, nếu index chỉ là phụ trợ lab và không cần giữ:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS
    lock_lab.ix_orders_status_created_c;
~~~

Lưu ý:

- `CREATE INDEX CONCURRENTLY` và `DROP INDEX CONCURRENTLY` phải chạy **bên ngoài transaction block**.
- Không chạy lại CREATE cùng tên khi index còn tồn tại, kể cả đang INVALID, nếu chưa điều tra trạng thái.
- Một index trên bảng vài hàng có thể không được planner dùng vì seq scan rẻ hơn; mục tiêu của lab này là hiểu lock/build lifecycle, không ép planner chọn index.

---

## 26. Triển khai thay đổi schema trên bảng lớn: expand → backfill → enforce → contract

Một kịch bản nghiệp vụ: muốn thêm mã bên ngoài `external_code` vào đơn hàng, dữ liệu đã có cần backfill, cuối cùng bảo đảm mọi đơn có mã và mã là duy nhất.

**Không triển khai tất cả thành một transaction dài.** Chia thành các bước có thể kiểm soát.

### 26.1. Expand: thêm cột nullable bằng DDL ngắn

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN external_code TEXT;

COMMIT;
~~~

Trong ứng dụng thật, nên làm code cũ và code mới tương thích schema mở rộng trước khi chuyển toàn bộ traffic.

### 26.2. Backfill theo batch

Đối với lab nhỏ:

~~~sql
UPDATE lock_lab.orders
SET external_code = 'ORD-' || order_id::text
WHERE external_code IS NULL;
~~~

Với bảng rất lớn, không nên một UPDATE toàn bảng trong một transaction duy nhất vì:

- Khóa hàng và transaction có thể kéo dài.
- Tạo nhiều dead tuples/WAL.
- Tăng replication lag.
- Khó retry khi lỗi.
- Có thể làm tăng áp lực VACUUM.

Một mô hình batch nếu có nhiều worker độc lập:

~~~sql
WITH batch AS (
    SELECT order_id
    FROM lock_lab.orders
    WHERE external_code IS NULL
    ORDER BY order_id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_lab.orders AS o
SET external_code = 'ORD-' || o.order_id::text
FROM batch
WHERE o.order_id = batch.order_id;
~~~

`SKIP LOCKED` ở đây được dùng cho workload **chia việc backfill**, nơi một worker có thể bỏ qua row mà worker khác đang xử lý. Phải có điều kiện dừng/đếm row còn lại và bảo đảm **mọi row cuối cùng đều được xử lý**. Không áp dụng SKIP LOCKED cho tác vụ nghiệp vụ bắt buộc phải lấy chính xác một hàng đang khóa.

### 26.3. Enforce uniqueness: tạo index ngoài transaction

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_code
ON lock_lab.orders (external_code);
~~~

Trước khi build, cần xác minh dữ liệu backfill đầy đủ, không có duplicate và quy tắc NULL phù hợp.

Sau build, kiểm tra:

~~~sql
SELECT i.indisvalid, i.indisready
FROM pg_index AS i
WHERE i.indexrelid = 'lock_lab.ux_orders_external_code'::regclass;
~~~

### 26.4. Enforce NOT NULL theo giai đoạn

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_external_code_not_null
    CHECK (external_code IS NOT NULL)
    NOT VALID;
~~~

Sau khi làm sạch tất cả hàng cũ:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT chk_external_code_not_null;
~~~

Sau đó, khi phù hợp với phiên bản triển khai:

~~~sql
ALTER TABLE lock_lab.orders
    ALTER COLUMN external_code SET NOT NULL;
~~~

Một CHECK đã validate có thể là bằng chứng để tránh scan NOT NULL riêng, nhưng **không đồng nghĩa bước SET NOT NULL không cần lock**.

### 26.5. Dùng index để thêm UNIQUE constraint

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT uq_orders_external_code
    UNIQUE USING INDEX ux_orders_external_code;
~~~

Bước này thường nhanh hơn việc để ALTER tự xây một index lớn trong lock mạnh, nhưng vẫn cần lock DDL phù hợp, và index phải đáp ứng các điều kiện constraint.

### 26.6. Contract: dọn thành phần cũ khi ứng dụng đã chuyển

Chỉ khi mọi service/worker/ETL đã chuyển sang schema mới và có kế hoạch rollback hợp lý, mới:

- Bỏ column/constraint/index cũ nếu thực sự không dùng.
- Bỏ dual-write.
- Cập nhật ORM/schema migration metadata.
- Đặt policy giám sát dữ liệu và độ trễ ghi.

**Không xóa cột cũ cùng lúc deploy code mới khi vẫn còn instance chạy phiên bản cũ.**

### 26.7. Checklist cho từng stage

| Stage | Hình thức lock quan trọng | Điều cần xác minh |
|---|---|---|
| ADD COLUMN | ACCESS EXCLUSIVE, cố gắng giữ ngắn | App tương thích cột nullable |
| Backfill | Row locks + ROW EXCLUSIVE từng batch | Đã xử lý hết, không tạo WAL quá mức |
| UNIQUE INDEX CONCURRENTLY | SHARE UPDATE EXCLUSIVE, waits/snapshots | Index VALID, dữ liệu không trùng |
| ADD CHECK NOT VALID | ALTER ngắn, vẫn có lock | Dữ liệu mới bị kiểm tra đúng |
| VALIDATE CHECK | SHARE UPDATE EXCLUSIVE | Dữ liệu cũ sạch, constraint validated |
| SET NOT NULL | ALTER lock có thể mạnh | Có đủ bằng chứng không NULL, timing tốt |
| ADD UNIQUE USING INDEX | DDL lock, thường ngắn | Index phù hợp/constraint hoạt động |
| Cleanup | DDL lock tùy subcommand | Không service nào còn dùng schema cũ |

Không phải mọi bước có thể rollback như một khối duy nhất khi có `CONCURRENTLY`. Vì vậy phải có kế hoạch **recovery theo bước**, không coi toàn bộ migration là một transaction khổng lồ.

---

## 27. Rollout migration an toàn với nhiều ứng dụng đang chạy

### 27.1. Lock timeout phải nằm trong ngân sách request

Nếu API có timeout 3 giây, một ALTER chờ lock 60 giây có thể làm request khác tích tụ và timeout trước khi ALTER hoàn thành. Vì vậy deploy migration cần phối hợp:

- Thời hạn chờ lock có thể chấp nhận.
- Thời hạn chạy statement.
- Thời gian còn lại của ứng dụng và connection pool.
- Kế hoạch retry có giới hạn.
- Khả năng rollback/cancel migration khi metrics vượt ngưỡng.

Mục tiêu không phải “ALTER bằng mọi giá”, mà là **không đổi một sửa chữa schema thành sự cố availability**.

### 27.2. Đo trước trên bản sao dữ liệu đại diện

Một bảng 5 dòng không cho biết:

- Một ALTER TYPE trên 200 triệu row mất bao lâu.
- Index build cần bao nhiêu đĩa/WAL.
- Replication lag sẽ tăng đến đâu.
- Có transaction kéo dài, cron maintenance hoặc CDC nào chờ.
- Có index/trigger/constraint phụ thuộc đang được vận hành không.

Cần đánh giá ở staging có thống kê, kích thước và pattern ghi tương đối gần production. Dù đã test, production vẫn có concurrency khác, nên timeout và giám sát là bắt buộc.

### 27.3. Đặt application_name cho migration job

Khi driver hỗ trợ, đặt tên kết nối rõ ràng, ví dụ `schema-migrate-orders`, để DBA nhanh chóng tìm:

~~~sql
SELECT
    pid, application_name, state, xact_start,
    wait_event_type, wait_event,
    LEFT(query, 180) AS sql_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name LIKE 'schema-migrate-%';
~~~

Không đặt tên application giống service khác gây nhầm lẫn và không đưa bí mật/token vào `application_name`.

### 27.4. Migration tool và nontransactional steps

Nhiều công cụ migration mặc định **mỗi migration là một transaction**. Đây là hành vi tốt cho nhiều DDL, nhưng không hợp lệ với `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY` hoặc `REINDEX ... CONCURRENTLY`.

Quy trình:

1. Kiểm tra framework có chế độ “nontransactional migration” không.
2. Tách bước `CONCURRENTLY` thành migration/job riêng khi cần.
3. Không ghi “migration hoàn thành” chỉ vì relation cùng tên đã xuất hiện.
4. Kiểm tra index `VALID`, uniqueness và phiên bản schema.
5. Nếu bước concurrent lỗi, xử lý invalid index trước khi chạy lại.
6. Bảo đảm migration không chạy trùng nhau từ nhiều app instances.

### 27.5. Advisory lock chỉ dùng để điều phối, không thay relation locks

Một số hệ thống dùng **advisory lock** để chỉ cho một migrator chạy tại một thời điểm. Advisory lock có thể hữu ích, nhưng:

- Nó hoạt động theo **thỏa thuận giữa các client**, không tự ngăn SELECT/UPDATE/ALTER từ ứng dụng không dùng cùng khóa advisory.
- Nó không thay thế relation locks mà PostgreSQL bắt buộc dùng cho DDL.
- Transaction-level và session-level advisory locks có vòng đời khác nhau, đặc biệt trong connection pool.

Không coi “đã có advisory migration lock” là bằng chứng ALTER không chặn traffic.

### 27.6. Khi cần cancel/terminate blocker

PostgreSQL có cơ chế hủy query hoặc kết thúc backend được quản trị qua quyền thích hợp. Nhưng đây là **thao tác rủi ro trên phiên của người khác**, có thể làm rollback transaction lớn hoặc gián đoạn người dùng.

Thứ tự ưu tiên trong incident thường là:

1. Xác định chính xác blocker/waiter và owner.
2. Xem transaction đó đang làm gì, đã mở bao lâu, mức độ quan trọng.
3. Cân nhắc **hủy/rollback chính migration** trước nếu nó là waiter gây hàng đợi.
4. Nếu phải xử lý blocker, phối hợp với owner và runbook đã phê duyệt.
5. Theo dõi hệ thống phục hồi và xác minh trạng thái schema sau can thiệp.

Không đưa một câu lệnh terminate PID bất kỳ vào script tự động học tập.

---

## 28. Lập kế hoạch index và bảo trì theo workload

### 28.1. Ba nguồn chi phí độc lập

Một thao tác bảo trì có thể đắt ở ba trục:

| Trục | Câu hỏi đo lường | Ví dụ |
|---|---|---|
| **Locking** | Nó chặn ai, chờ ai, giữ bao lâu? | ALTER cần ACCESS EXCLUSIVE |
| **Compute/I/O** | Nó quét, sort, rewrite, tạo WAL bao nhiêu? | CREATE INDEX CONCURRENTLY quét nhiều lượt |
| **Storage/replication** | Cần đĩa tạm, index mới, tăng replica lag ra sao? | VACUUM FULL, REINDEX, CLUSTER |

Có thể không chặn DML ở tầng lock nhưng vẫn làm latency ứng dụng tăng mạnh nếu I/O bão hòa.

### 28.2. Dấu hiệu autovacuum không theo kịp

View thống kê bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'lock_lab'
ORDER BY relname;
~~~

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải COUNT(*) chính xác. Nhiều dead tuples có thể do workload UPDATE/DELETE cao hoặc transaction giữ snapshot lâu; đừng chỉ tăng tần suất VACUUM mà bỏ qua horizon cũ.

### 28.3. Dung lượng table/index

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('lock_lab.orders'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('lock_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('lock_lab.orders'::regclass)
    ) AS total_size;
~~~

Các con số giúp ước lượng quy mô trước index build/rewrite, nhưng không đủ để đo **bloat thực** hoặc đĩa tạm cần dùng. Size và concurrency thay đổi theo thời gian.

### 28.4. REINDEX sau lỗi collation hoặc bloat

Nếu collation version thay đổi hoặc index có vấn đề liên quan nội dung text, quy trình reindex có thể cần theo hướng dẫn của phiên bản PostgreSQL và chiến lược quản trị. Không chỉ chạy `ALTER DATABASE REFRESH COLLATION VERSION` để loại warning mà bỏ qua việc xây lại những index bị ảnh hưởng.

### 28.5. Autovacuum không nên bị bỏ đói bởi liên tục index build

Nếu các job index concurrent, ANALYZE và DDL chạy liên tục trên cùng bảng, một số hoạt động maintenance có thể chờ lock và dồn backlog. Lập lịch theo bảng/vùng dữ liệu, tránh nhiều job đồng thời không kiểm soát.

---

## 29. Checklist trước, trong và sau DDL/maintenance

### 29.1. Trước khi triển khai

- [ ] Chốt rõ mục tiêu schema/index/maintenance và lý do kỹ thuật.
- [ ] Xác định phiên bản PostgreSQL, kiểu bảng thường/partitioned/materialized.
- [ ] Xác định **lock mode của subcommand** và những relation liên quan.
- [ ] Đo kích thước bảng/index, số hàng, tốc độ ghi và replication lag.
- [ ] Kiểm tra transaction dài, blockers tiềm tàng và maintenance đang chạy.
- [ ] Chọn `CREATE INDEX` hay `CREATE INDEX CONCURRENTLY` theo availability.
- [ ] Kiểm tra constraint, dữ liệu trùng, NULL và điều kiện validation.
- [ ] Chuẩn bị lock_timeout/statement_timeout và chính sách retry.
- [ ] Nếu có `CONCURRENTLY`, kiểm tra tool không bọc nó trong BEGIN.
- [ ] Chuẩn bị script rollback/recovery **cho từng bước**, đặc biệt index INVALID.
- [ ] Thống nhất maintenance window hoặc phương án chạy online và metrics dừng.

### 29.2. Trong khi chạy

- [ ] Theo dõi `pg_stat_activity.wait_event_type` và `pg_blocking_pids`.
- [ ] Theo dõi `pg_stat_progress_create_index/vacuum/cluster` khi có.
- [ ] Quan sát số connection đang chờ, latency API và timeout.
- [ ] Theo dõi CPU, I/O, disk headroom, WAL và replica lag.
- [ ] Nếu lock timeout, rollback transaction bị lỗi; không “nhân đôi” migrate jobs.
- [ ] Không giữ transaction mở để chạy thao tác kiểm tra thủ công dài.

### 29.3. Sau khi hoàn tất

- [ ] Xác nhận migration/index command báo thành công.
- [ ] Kiểm tra index `indisvalid`, `indisready` khi phù hợp.
- [ ] Kiểm tra constraint đã validated hoặc trạng thái NOT VALID là chủ đích.
- [ ] Dùng EXPLAIN cho truy vấn quan trọng, không ép planner bằng giả định.
- [ ] Đảm bảo không còn `idle in transaction` từ migration.
- [ ] Xem backlog VACUUM/ANALYZE và replica lag đã phục hồi.
- [ ] Cập nhật schema version, runbook và các bước dọn sau rollout.

---

## 30. Sơ đồ quyết định chọn kỹ thuật

~~~mermaid
flowchart TD
    A["Cần thay đổi hoặc bảo trì bảng PostgreSQL"] --> B{"Loại công việc?"}
    B -- "ALTER TABLE" --> C{"Có thể chia nhỏ?"}
    C -- "Có" --> D["Expand / backfill batch / validate / contract"]
    C -- "Không" --> E["Đánh giá ACCESS EXCLUSIVE, rewrite, maintenance window"]
    B -- "Thêm index" --> F{"Bảng có cần tiếp tục ghi?"}
    F -- "Không, có maintenance window" --> G["CREATE INDEX thường"]
    F -- "Có" --> H["CREATE INDEX CONCURRENTLY ngoài transaction block"]
    B -- "Dọn dead tuples/stats" --> I["VACUUM thường hoặc ANALYZE"]
    B -- "Compact/reorder vật lý" --> J["VACUUM FULL / CLUSTER, ACCESS EXCLUSIVE"]
    B -- "Xây lại index" --> K{"Cần giảm chặn DML?"}
    K -- "Có" --> L["REINDEX CONCURRENTLY khi được hỗ trợ"]
    K -- "Không" --> M["REINDEX thường trong maintenance window"]
    D --> N["lock_timeout, pg_stat_activity, blockers"]
    E --> N
    G --> N
    H --> N
    I --> N
    J --> N
    L --> N
    M --> N
    N --> O["Xác minh catalog/progress và sức khỏe ứng dụng"]
~~~

Sơ đồ là định hướng. Quyết định cuối cùng phụ thuộc phiên bản PostgreSQL, kích thước dữ liệu, phụ thuộc schema, mức độ quan trọng của write availability và các cam kết vận hành.

---

## 31. Những lỗi và ngộ nhận thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| “ALTER ADD COLUMN nullable không rewrite nên không lock” | SELECT/DML có thể bị chặn | Phân biệt **thời gian xử lý** với **lock mode** |
| BEGIN → ALTER → kiểm tra GUI lâu → COMMIT | Giữ ACCESS EXCLUSIVE quá lâu | Transaction DDL ngắn |
| Không dùng lock_timeout cho DDL trên bảng nóng | Một ALTER waiter kéo theo hàng đợi | Fail fast và retry có kiểm soát |
| Chỉ xem blocker đang giữ lock, bỏ qua waiter queue | Không giải thích vì sao SELECT mới cũng chờ | Xem `pg_blocking_pids()` và lock queue |
| Dùng CREATE INDEX thường trên bảng lớn ghi liên tục | Ghi bị chặn lâu | Xem xét CREATE INDEX CONCURRENTLY |
| Tưởng CREATE INDEX CONCURRENTLY không dùng lock | Bị bất ngờ bởi DDL/VACUUM xung đột | Hiểu SHARE UPDATE EXCLUSIVE |
| Đưa CREATE INDEX CONCURRENTLY vào BEGIN | SQL bị từ chối | Migration nontransactional |
| Thấy tên index tồn tại, kết luận deploy xong | Có thể INVALID hoặc sai định nghĩa | `pg_index` + `pg_get_indexdef` |
| Retry build invalid cùng tên không điều tra | Tiếp tục lỗi, tốn tài nguyên | Tìm nguyên nhân và xử lý index invalid |
| Tạo UNIQUE concurrent khi dữ liệu còn trùng | Build thất bại, phát sinh error cho writers | Làm sạch dữ liệu và lập kế hoạch uniqueness |
| Dùng IF NOT EXISTS để xác minh index đúng | Bỏ qua index sai/trạng thái invalid | So catalog definition/state |
| Dùng VACUUM FULL như VACUUM thường | Chặn đọc/ghi, rewrite đắt | Chỉ dùng khi thực sự cần trong window |
| Tắt autovacuum để “DDL khỏi bị chặn” | Dead tuples, XID age tăng | Điều phối workload; không tắt tùy tiện |
| Chạy ANALYZE để sửa mọi query chậm | Không xử lý được index/SQL sai hoặc lock | EXPLAIN và thống kê |
| Xem n_dead_tup như COUNT(*) chuẩn | Chẩn đoán sai | Coi là estimate |
| Mở transaction dài khi backfill | Lock/WAL/bloat lớn | Chia batch và commit ngắn |
| Dùng SKIP LOCKED cho bản ghi bắt buộc xử lý ngay | Bỏ sót dữ liệu nghiệp vụ | Chỉ dùng cho queue/backfill được theo dõi |
| Nghĩ SET NOT NULL là đổi metadata không scan | ALTER có thể quét bảng | Xác minh CHECK/validation và version |
| Chỉ xem bảng chính khi ADD FOREIGN KEY | Bị blocker ở bảng tham chiếu | Xem cả hai relation |
| Chỉ xem % progress blocks và kết luận job hoàn thành | Build còn phase wait/validation | Theo dõi phase và catalog |
| Dùng VACUUM FULL để sửa xmin/xmax | Hiểu sai MVCC, downtime | Không coi rewrite là công cụ điều chỉnh tuple status |
| Tự terminate blocker khi chưa biết chủ sở hữu | Mất transaction, lỗi người dùng | Điều tra/điều phối theo runbook |
| Quên replication lag/WAL trong kế hoạch | Replica tụt hậu hoặc hết dung lượng | Theo dõi primary và replica |
| Bỏ qua app compatibility khi đổi schema | App cũ/worker cũ lỗi | Expand/contract theo giai đoạn |
| Không rollback sau lock timeout trong BEGIN | Session ở trạng thái aborted | ROLLBACK và reset connection |

---

## 32. Bài tập thực hành

Các bài dùng `lock_lab.orders` và `lock_lab.customers` của phần 4, trừ khi nêu tình huống giả định. Không chạy bài làm thay đổi schema trên cùng lab với nhiều người đang làm việc. Với bài liên quan hai connection, thực hiện đúng thứ tự và **kết thúc mọi transaction**, không để session chờ lock sau khi thực hành.

### Bài 1 — Nhận diện lock modes

Một SELECT bình thường và ALTER TABLE ADD COLUMN lấy các relation lock modes nào? Hai mode đó có tương thích với nhau không?

### Bài 2 — SELECT so với CREATE INDEX

Vì sao SELECT bình thường có thể vẫn chạy trong khi CREATE INDEX thường đang xây trên bảng, nhưng INSERT/UPDATE có thể bị chặn?

### Bài 3 — ROW EXCLUSIVE không phải row-level lock

Giải thích tại sao `ROW EXCLUSIVE` là tên của table-level lock, không có nghĩa toàn bộ bảng bị khóa không cho SELECT.

### Bài 4 — ALTER metadata nhanh nhưng deploy chậm

Một ADD COLUMN nullable mất 10 ms khi chạy riêng, nhưng ở production đợi lock 45 giây. Nêu ít nhất ba điều cần kiểm tra.

### Bài 5 — Head-of-line blocking

Phiên A giữ SELECT trong transaction, phiên B đợi ACCESS EXCLUSIVE để ALTER, phiên C chạy SELECT mới. Vì sao phiên C cũng có thể đợi dù A và C đều chỉ SELECT?

### Bài 6 — Hai phiên DDL

Viết SQL để phiên A BEGIN và SELECT bảng orders nhưng chưa commit; phiên B ALTER ADD COLUMN với lock_timeout 2s. Sau khi timeout, mỗi phiên phải làm gì để lab về bình thường?

### Bài 7 — ADD CONSTRAINT NOT VALID

Một bảng lớn cần CHECK `amount >= 0` nhưng chưa có bảo đảm dữ liệu cũ sạch. Viết lộ trình `NOT VALID`, cleanup và `VALIDATE CONSTRAINT`. Việc NOT VALID có cho các INSERT mới vi phạm CHECK không?

### Bài 8 — FOREIGN KEY

ADD FOREIGN KEY tham gia những bảng nào và dùng lock mode nào điển hình? Vì sao phải kiểm tra blocker ở cả bảng con và bảng cha?

### Bài 9 — SET NOT NULL

Nếu bảng có hàng triệu row, tại sao `SET NOT NULL` có thể tốn thời gian? Một CHECK đã VALID có thể giúp gì trong phiên bản hỗ trợ?

### Bài 10 — CREATE INDEX thường

Viết câu tạo index trên `(customer_id, created_at)` rồi giải thích vì sao writer có thể bị chặn trong lúc build.

### Bài 11 — CREATE INDEX CONCURRENTLY

Viết SQL tạo index trên `(status, created_at)` mà giảm chặn DML; vì sao không được bọc trong BEGIN?

### Bài 12 — INVALID index

Một concurrent index build thất bại nhưng `pg_class` vẫn có tên index. Viết SQL kiểm tra `indisvalid` và `indisready`. Bước tiếp theo nên làm gì?

### Bài 13 — IF NOT EXISTS

`CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_name ...` chạy không lỗi có chứng minh index đúng cột và VALID không?

### Bài 14 — DROP INDEX CONCURRENTLY

Vì sao DROP INDEX CONCURRENTLY cũng phải chạy ngoài transaction block? Có thể xóa tùy ý index phục vụ PRIMARY KEY/UNIQUE constraint không?

### Bài 15 — REINDEX

Phân biệt REINDEX thường và REINDEX CONCURRENTLY về lock, chi phí, transaction block và phục hồi khi build lỗi.

### Bài 16 — VACUUM thường

VACUUM thường dùng lock mode nào? Tại sao có thể không chặn DML nhưng vẫn làm API chậm?

### Bài 17 — VACUUM FULL

Vì sao VACUUM FULL có thể chặn cả đọc lẫn ghi và cần thêm đĩa? Nêu trường hợp nên tránh.

### Bài 18 — ANALYZE

ANALYZE giải quyết bài toán gì và có xây lại index không? Vì sao không nên dùng REINDEX như giải pháp mặc định khi thống kê planner cũ?

### Bài 19 — CLUSTER

CLUSTER sắp dữ liệu vật lý theo gì? Sau CLUSTER, SELECT không ORDER BY có được PostgreSQL bảo đảm luôn trả theo thứ tự index đó không?

### Bài 20 — Xung đột maintenance

Vì sao CREATE INDEX CONCURRENTLY và VACUUM trên cùng bảng có thể phải chờ nhau, dù cả hai thường cho phép INSERT/UPDATE?

### Bài 21 — Blocking PIDs

Viết câu SQL liệt kê các backend đang bị chặn và mảng blocking PIDs. Có nên tự terminate blocker đầu tiên tìm thấy không?

### Bài 22 — pg_locks

Viết SQL xem các relation lock trên `lock_lab.orders` cùng `mode` và `granted`. `granted=false` nghĩa là gì?

### Bài 23 — CREATE INDEX progress

Viết SQL xem `phase` và progress blocks của một index build. Tại sao `blocks_done / blocks_total` không phải luôn là % hoàn thành toàn job?

### Bài 24 — VACUUM progress

View nào xem progress VACUUM thường? View nào thường xem progress cho VACUUM FULL/CLUSTER?

### Bài 25 — Transaction DDL

Vì sao nên commit ngay sau ALTER ngắn, thay vì giữ transaction mở để chờ đánh giá thủ công? Nêu rủi ro với connection pool.

### Bài 26 — Phân biệt timeout

`lock_timeout` và `statement_timeout` giới hạn những thời gian nào? Nếu lock_timeout báo lỗi trong BEGIN, phải xử lý trạng thái transaction ra sao?

### Bài 27 — Hệ thống partitioned

Vì sao ATTACH PARTITION cần xem lock trên parent và child, không chỉ một relation? Constraint nào có thể giúp tránh scan xác minh dữ liệu?

### Bài 28 — Migration expand/contract

Thiết kế năm bước cho việc thêm `external_code` duy nhất và NOT NULL trên bảng orders lớn mà vẫn cho ứng dụng tiếp tục ghi.

### Bài 29 — Backfill batch

Vì sao UPDATE mọi row trong một transaction lớn có thể gây WAL/bloat/lock dài? Khi nào có thể dùng FOR UPDATE SKIP LOCKED?

### Bài 30 — Ứng dụng và replica

Một VACUUM FULL hoặc CLUSTER tạo rất nhiều WAL. Vì sao chỉ giám sát primary mà bỏ qua replica là chưa đủ?

### Bài 31 — Quyền và điều tra khóa

Một backend `idle in transaction` đang chặn ALTER, nhưng transaction thuộc service thanh toán. Nên làm gì trước khi cân nhắc cancel hoặc terminate?

### Bài 32 — Chọn kỹ thuật phù hợp

Với từng yêu cầu, chọn hướng chính:

1. Cần thêm index cho bảng 100 triệu row và vẫn phải nhận ghi.
2. Muốn cập nhật thống kê sau bulk load.
3. Muốn thu hồi dead tuples thường xuyên, hạn chế chặn DML.
4. Cần compact file bảng rất bloat và chấp nhận maintenance window.
5. Cần thay đổi type cột trên bảng nóng, có nguy cơ rewrite.
6. Cần thêm CHECK cho dữ liệu cũ rất nhiều hàng.
7. Cần xây lại index mà hạn chế chặn ghi.
8. Cần xóa index invalid còn sót lại mà không được mở BEGIN.

Giải thích ngắn lựa chọn và giới hạn của từng cách.

---

## 33. Gợi ý lời giải

### Bài 1 — Relation lock của SELECT và ALTER

`SELECT` bình thường thường lấy `ACCESS SHARE`; `ALTER TABLE ... ADD COLUMN` thường cần `ACCESS EXCLUSIVE`. Hai mode **xung đột**, nên SELECT đang giữ lock có thể khiến ALTER đợi và ALTER đã lấy lock có thể khiến SELECT đợi.

### Bài 2 — SELECT và CREATE INDEX thường

`CREATE INDEX` thường lấy `SHARE`. `ACCESS SHARE` của SELECT **tương thích** với SHARE; `ROW EXCLUSIVE` của INSERT/UPDATE/DELETE **xung đột** với SHARE, nên các writer có thể phải chờ index build hoặc transaction chứa build kết thúc.

### Bài 3 — ROW EXCLUSIVE

`ROW EXCLUSIVE` là **table-level mode** được DML yêu cầu, không phải dấu hiệu toàn bộ bảng bị khóa độc quyền khỏi SELECT. SELECT bình thường dùng ACCESS SHARE và tương thích với ROW EXCLUSIVE. Việc các writer tranh nhau trên **cùng một row** liên quan thêm row-level/transaction locks.

### Bài 4 — ALTER metadata nhanh, đợi lâu

Cần kiểm tra:

1. Backend nào đang giữ lock xung đột qua `pg_blocking_pids()`?
2. Có transaction lâu/`idle in transaction` giữ ACCESS SHARE hoặc ROW EXCLUSIVE không?
3. ALTER đang **waiting** hay đã được cấp ACCESS EXCLUSIVE?
4. Có waiter phía trước trong lock queue không?
5. Có timeout, transaction migration, DDL khác hoặc maintenance đang chạy không?

Không khắc phục bằng cách tăng vô hạn timeout.

### Bài 5 — Head-of-line blocking

Phiên B đã vào hàng đợi để lấy ACCESS EXCLUSIVE, xung đột với SELECT C dù C có ACCESS SHARE tương thích với A. PostgreSQL không nhất thiết cho C vượt qua B liên tục vì sẽ làm B bị đói lock. Do vậy chính ALTER **đang đợi** cũng có thể gây backlog.

### Bài 6 — Hai phiên DDL

**Phiên A:**

~~~sql
BEGIN;
SELECT COUNT(*) FROM lock_lab.orders;
-- Chưa kết thúc, chuyển sang B.
~~~

**Phiên B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE lock_lab.orders ADD COLUMN lab_test_col TEXT;
-- Khi gặp lock timeout:
ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

Khi thử lại và muốn không giữ cột lab:

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders ADD COLUMN lab_test_col TEXT;
ROLLBACK;
~~~

### Bài 7 — CHECK NOT VALID và VALIDATE

~~~sql
ALTER TABLE lock_lab.orders
ADD CONSTRAINT chk_orders_amount_nn
CHECK (amount >= 0) NOT VALID;
~~~

Sau đó làm sạch dữ liệu sai trong các batch có kiểm tra, rồi:

~~~sql
ALTER TABLE lock_lab.orders
VALIDATE CONSTRAINT chk_orders_amount_nn;
~~~

`NOT VALID` tránh scan toàn bảng **ở bước ADD**, không cho phép các thay đổi dữ liệu mới vi phạm CHECK mà vẫn được chấp nhận. `VALIDATE` xác minh dữ liệu đã có và thường dùng SHARE UPDATE EXCLUSIVE. Trong lab, `amount` vốn đã có CHECK tương đương nên ví dụ chỉ để minh họa thủ pháp triển khai, không cần thêm constraint thừa ở production.

### Bài 8 — FOREIGN KEY

~~~sql
ALTER TABLE lock_lab.orders
ADD CONSTRAINT fk_orders_customers
FOREIGN KEY (customer_id)
REFERENCES lock_lab.customers(customer_id)
NOT VALID;
~~~

ADD FK sử dụng `SHARE ROW EXCLUSIVE` trên bảng tham chiếu `orders` và bảng đích `customers`; cả hai đều có thể bị ảnh hưởng ghi. `VALIDATE CONSTRAINT` ở giai đoạn sau giúp tách scan dữ liệu cũ khỏi bước ADD.

### Bài 9 — SET NOT NULL

`SET NOT NULL` có thể phải scan toàn bảng để xác nhận không tồn tại NULL. Trong PostgreSQL hỗ trợ tối ưu, một CHECK `column IS NOT NULL` đã VALID có thể cung cấp bằng chứng để bỏ scan kiểm tra đó. Nhưng thao tác vẫn có lock của ALTER và có thể phải chờ lock xung đột.

### Bài 10 — CREATE INDEX thường

~~~sql
CREATE INDEX ix_orders_customer_created
ON lock_lab.orders(customer_id, created_at);
~~~

SHARE lock dùng trong build xung đột với ROW EXCLUSIVE của writer. Trong bảng lớn có write traffic liên tục, cân nhắc một maintenance window hoặc xây concurrently theo yêu cầu availability.

### Bài 11 — CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_status_created_c
ON lock_lab.orders(status, created_at);
~~~

Không bọc trong BEGIN: công cụ này cần nhiều transaction nội bộ và chờ những snapshot/writers liên quan. PostgreSQL từ chối `CREATE INDEX CONCURRENTLY` trong transaction block tường minh. Nó giảm chặn DML thông thường nhưng vẫn có lock và chi phí.

### Bài 12 — INVALID index

~~~sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid = 'lock_lab.orders'::regclass;
~~~

Nếu invalid, tìm lỗi gốc, xác nhận job build đã dừng, đánh giá uniqueness/dependencies, rồi xử lý dọn hoặc reindex theo đúng loại index và runbook. Không tự retry bằng cùng tên khi chưa điều tra.

### Bài 13 — IF NOT EXISTS

**Không.** Nó chỉ tránh lỗi tên relation trùng theo semantics của command. Không xác minh index cùng tên có đúng các cột, predicate, uniqueness, collations hoặc trạng thái VALID. Cần đọc catalog và định nghĩa index.

### Bài 14 — DROP INDEX CONCURRENTLY

`DROP INDEX CONCURRENTLY` có quy tắc transaction riêng và phải chạy ngoài transaction block. Không xóa trực tiếp index gắn với PRIMARY KEY/UNIQUE constraint theo cách phá phụ thuộc; phải xử lý constraint và dữ liệu theo migration plan hợp lệ.

### Bài 15 — REINDEX

- `REINDEX` thường: có thể chặn ghi và các thao tác liên quan index trong quá trình rebuild; lập lịch theo workload.
- `REINDEX ... CONCURRENTLY`: giảm chặn DML thông thường nhưng nhiều bước, thêm disk/WAL, chờ snapshots và không nằm trong transaction block tường minh.
- Sau lỗi: kiểm tra trạng thái index, index tạm/invalid và điều kiện để chạy lại; không lập tức lặp vô hạn.

### Bài 16 — VACUUM thường

Regular VACUUM dùng `SHARE UPDATE EXCLUSIVE`, tương thích với ROW EXCLUSIVE và ACCESS SHARE thông thường. Dù không trực tiếp chặn DML theo lock mode, nó vẫn có thể làm latency tăng vì I/O, CPU, index/heap processing hoặc xung đột maintenance khác.

### Bài 17 — VACUUM FULL

`VACUUM FULL` rewrite bảng để compact dung lượng, dùng `ACCESS EXCLUSIVE`; SELECT và DML có thể bị chặn. Rewrite có thể cần disk bổ sung và tạo WAL/replica lag lớn. Tránh chạy giữa giờ cao điểm trên bảng nóng hoặc khi thiếu disk/maintenance window.

### Bài 18 — ANALYZE

`ANALYZE` cập nhật thống kê cho query planner. Nó không rebuild index. Nếu planner ước lượng row count sai do bulk load hoặc thay đổi phân bố dữ liệu, ANALYZE là công cụ phù hợp để xem xét trước, không mặc định REINDEX.

### Bài 19 — CLUSTER

`CLUSTER table USING index` rewrite dữ liệu theo index và thường yêu cầu ACCESS EXCLUSIVE trên bảng. Sau đó các thao tác ghi mới có thể thay đổi bố trí vật lý. SELECT **không ORDER BY** vẫn không có thứ tự kết quả bảo đảm.

### Bài 20 — Xung đột maintenance

`CREATE INDEX CONCURRENTLY` và regular `VACUUM` đều có thể dùng SHARE UPDATE EXCLUSIVE trên cùng relation; mode này xung đột **với chính nó**, dù vẫn tương thích với nhiều dạng DML. Cần quan sát tiến độ và lịch maintenance.

### Bài 21 — Blocking PIDs

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    LEFT(query, 160) AS sql_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

**Không** tự terminate PID đầu tiên. Xem owner, loại transaction, mục tiêu nghiệp vụ, rủi ro rollback và phối hợp với người vận hành.

### Bài 22 — pg_locks

~~~sql
SELECT
    pid, locktype, mode, granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE relation = 'lock_lab.orders'::regclass
ORDER BY granted, pid, mode;
~~~

`granted=false` nghĩa là lock chưa được cấp, backend đang chờ nó. Không coi đó là bằng chứng backend đã khóa độc quyền bảng.

### Bài 23 — Index progress

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    lockers_total,
    lockers_done
FROM pg_stat_progress_create_index
WHERE datname = current_database();
~~~

Job còn có thể phải scan/validate/chờ snapshot sau phase hiện tại. Một tỷ lệ blocks chỉ phản ánh phần của **phase tương ứng**, không phải tổng chi phí/thời gian của toàn build.

### Bài 24 — VACUUM progress

- `pg_stat_progress_vacuum`: VACUUM thông thường.
- `pg_stat_progress_cluster`: tiến độ những thao tác rewrite như VACUUM FULL và CLUSTER.
- `pg_stat_progress_analyze`: ANALYZE trong phiên bản hỗ trợ.

### Bài 25 — Transaction DDL

Relation lock có thể giữ tới cuối transaction. Sau ALTER đã chạy xong, nếu transaction chưa COMMIT thì các SELECT/DML vẫn có thể chờ. Với pool, backend bị giữ trong `idle in transaction` hoặc trả về pool khi chưa rollback có thể gây nghẽn cho request tiếp theo. DDL transaction phải ngắn và kết thúc rõ ở mọi nhánh.

### Bài 26 — Timeout

`lock_timeout`: thời gian chờ **lấy lock**.

`statement_timeout`: thời gian xử lý **statement**, bao gồm cả thời gian chờ tương ứng.

Trong transaction, nếu statement lỗi timeout, transaction có thể ở trạng thái aborted; cần `ROLLBACK` toàn transaction hoặc xử lý savepoint hợp lệ, không tiếp tục gửi SQL như không có lỗi.

### Bài 27 — ATTACH PARTITION

Operation có thể lấy lock khác nhau trên parent, child và các quan hệ liên quan. Nếu child chưa có ràng buộc chứng minh mọi row thuộc partition bound, PostgreSQL có thể phải scan để xác minh. Một CHECK phù hợp **đã VALID** có thể giúp tránh scan đó trong trường hợp hỗ trợ.

### Bài 28 — Expand/contract

Một lộ trình:

1. **Expand:** thêm `external_code TEXT` nullable với ALTER ngắn, code tương thích cả hai schema.
2. **Backfill:** cập nhật từng batch, kiểm tra uniqueness và tất cả row đã có giá trị.
3. **Index:** `CREATE UNIQUE INDEX CONCURRENTLY`, xác minh `indisvalid` và định nghĩa.
4. **Enforce:** thêm CHECK NOT VALID/VALIDATE và SET NOT NULL khi phù hợp; gắn UNIQUE constraint USING INDEX bằng DDL ngắn.
5. **Contract:** chuyển toàn bộ app/ETL sang schema mới rồi dọn thành phần cũ, giám sát và có kế hoạch phục hồi riêng từng bước.

Không ép CREATE INDEX CONCURRENTLY vào cùng một transaction với các ALTER.

### Bài 29 — Backfill batch

Một UPDATE toàn bảng tạo transaction lớn, nhiều row locks/versions, WAL, replication lag và bloat. Chia batch nhỏ, commit thường xuyên. `FOR UPDATE SKIP LOCKED` có thể hữu ích khi có nhiều worker xử lý queue/backfill độc lập, nhưng cần kiểm soát để không bỏ sót row lâu dài.

### Bài 30 — Replica

Các thao tác rewrite/index lớn có thể tạo WAL và tải I/O, khiến replica lag tăng hoặc gặp áp lực dung lượng. Dù primary hoàn thành, hệ thống đọc từ replica có thể còn chậm/lag. Theo dõi cả lag, disk, replay, backup và các giới hạn hạ tầng liên quan.

### Bài 31 — Backend idle in transaction

Đầu tiên xác định owner service, job/request, thời gian transaction và ảnh hưởng thực tế qua `pg_stat_activity`, `pg_blocking_pids()`. Cân nhắc rollback/cancel **migration waiter** để gỡ hàng đợi nếu phù hợp, hoặc phối hợp với service thanh toán để kết thúc transaction có kiểm soát. Không kill phiên thanh toán tùy tiện.

### Bài 32 — Chọn công cụ

| Tình huống | Hướng phù hợp | Lưu ý |
|---|---|---|
| Index bảng lớn vẫn nhận ghi | `CREATE INDEX CONCURRENTLY` | Ngoài BEGIN, có scan/snapshot wait, kiểm tra INVALID |
| Thu thập thống kê sau bulk load | `ANALYZE` | SHARE UPDATE EXCLUSIVE, không rebuild index |
| Dọn dead tuples định kỳ | `VACUUM`/autovacuum | Không chặn DML thường theo lock mode, vẫn tốn I/O |
| Thu nhỏ file bảng trong maintenance window | `VACUUM FULL` | ACCESS EXCLUSIVE, rewrite và cần disk |
| Đổi kiểu cột có nguy cơ rewrite | Expand/contract hoặc maintenance window | Phân tích cast/rewrite, lock mạnh và app compatibility |
| CHECK trên bảng nhiều hàng cũ | `ADD ... NOT VALID` rồi `VALIDATE` | Bước ADD vẫn lock, validate có scan |
| Rebuild index giảm chặn ghi | `REINDEX ... CONCURRENTLY` nếu hỗ trợ | Ngoài BEGIN, cần disk và giám sát |
| Dọn index invalid còn sót | `DROP INDEX CONCURRENTLY` nếu phù hợp | Ngoài BEGIN, kiểm tra dependencies/constraints |

---

## 34. Kết luận

**Khóa trong PostgreSQL là một phần bắt buộc của quản lý nhất quán giữa DDL, DML và bảo trì; điều quan trọng không chỉ là lệnh có nhanh hay chậm, mà là lock mode, thời gian giữ lock và cách yêu cầu khóa tương tác với traffic hiện tại.**

- **`ALTER TABLE`:** nhiều subcommand lấy `ACCESS EXCLUSIVE`. Một thay đổi metadata không rewrite vẫn có thể chờ và chặn cả SELECT/DML. Phải xem từng subcommand, đặc biệt constraint/partition operations.
- **Constraint lớn:** chia thành `ADD ... NOT VALID`, backfill/cleanup rồi `VALIDATE CONSTRAINT` khi phù hợp; giảm thời gian scan trong bước ADD nhưng không loại bỏ khóa.
- **`CREATE INDEX` thường:** thường lấy `SHARE`, cho SELECT nhưng có thể chặn DML.
- **`CREATE INDEX CONCURRENTLY`:** giảm chặn ghi, nhưng tốn scan, có thể chờ snapshot và dùng `SHARE UPDATE EXCLUSIVE`; không được đặt trong transaction block, có thể để lại index INVALID.
- **`REINDEX`/`REINDEX CONCURRENTLY`:** xây lại index, có những đánh đổi về lock, thời gian, đĩa và khả năng recovery.
- **`VACUUM` thường và `ANALYZE`:** được thiết kế để phối hợp với phần lớn DML bình thường nhưng vẫn tốn tài nguyên và có thể xung đột với maintenance/DDL.
- **`VACUUM FULL`/`CLUSTER`:** rewrite và dùng `ACCESS EXCLUSIVE`, cần maintenance window và đánh giá disk/WAL/replication.
- **Quan sát:** `pg_stat_activity`, `pg_blocking_pids()`, `pg_locks` và các view `pg_stat_progress_*` giúp phân biệt blocker, waiter, phase và tải.
- **Triển khai an toàn:** transaction DDL ngắn, `lock_timeout` có giới hạn, cleanup khi lỗi, expand/backfill/enforce/contract, kiểm tra catalog và ứng dụng sau deploy.

Cách làm phù hợp cho hệ thống đang hoạt động: **xác định thay đổi và lock mode → đo concurrency/dung lượng → chọn kỹ thuật ít chặn phù hợp → chuẩn bị rollback/timeout → triển khai theo giai đoạn → giám sát blockers và progress → xác minh catalog, hiệu năng, dữ liệu và replica sau khi hoàn tất**.
