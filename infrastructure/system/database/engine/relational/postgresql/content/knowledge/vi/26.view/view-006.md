# REFRESH MATERIALIZED VIEW và chế độ CONCURRENTLY trong PostgreSQL

Một hệ thống bán hàng có hàng triệu đơn mỗi ngày. Trang dashboard cần hiển thị doanh thu theo ngày và cửa hàng; nếu mỗi lần mở dashboard đều quét bảng đơn rồi `GROUP BY`, chi phí truy vấn có thể lớn. PostgreSQL cho phép lưu kết quả của một câu truy vấn trong **materialized view** (*khung nhìn vật hóa*), sau đó đọc kết quả đã lưu như một quan hệ vật lý.

Nhưng materialized view **không tự cập nhật khi bảng nguồn thay đổi**. Hôm qua hệ thống có 10.000 đơn, hôm nay thêm 1.000 đơn; báo cáo có thể vẫn hiển thị dữ liệu từ lần tính trước cho đến khi chạy:

```sql
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
```

Một vấn đề mới xuất hiện: dashboard vẫn có người đọc trong lúc refresh. Lệnh thông thường có thể khóa việc đọc từ materialized view trong thời gian thay thế dữ liệu. PostgreSQL cung cấp:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.daily_revenue;
```

để **cho phép các câu SELECT thông thường tiếp tục đọc materialized view** trong khi quá trình làm mới đang diễn ra. Tuy nhiên `CONCURRENTLY` không phải tùy chọn có thể thêm vào mọi materialized view: nó yêu cầu view đã được nạp dữ liệu và có **một UNIQUE index phù hợp, bao trùm tất cả các hàng, chỉ dùng tên cột**. Nó cũng **không biến refresh thành cập nhật tăng dần miễn phí**, không cho phép nhiều refresh chạy song song trên cùng một view, và không làm dữ liệu mới xuất hiện tức thì.

Bài này giải thích chính xác cơ chế, cú pháp, điều kiện để dùng `CONCURRENTLY`, khác biệt về lock và tính nhất quán khi đọc, chi phí thực tế, cách vận hành an toàn và bộ ví dụ SQL có thể tự chạy.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Phân biệt `VIEW`, `MATERIALIZED VIEW` và bảng tổng hợp tự duy trì.
2. Giải thích dữ liệu trong materialized view bị cũ (*stale*) vì sao và khi nào cần refresh.
3. Đọc cú pháp `REFRESH MATERIALIZED VIEW [CONCURRENTLY] ... [WITH [NO] DATA]`.
4. Mô tả điểm khác biệt giữa refresh thông thường và `CONCURRENTLY` đối với SELECT, locks, tài nguyên và thời điểm công bố dữ liệu.
5. Liệt kê chính xác điều kiện **populated** và **UNIQUE index hợp lệ** để dùng `CONCURRENTLY`.
6. Giải thích vì sao UNIQUE index partial hoặc expression không đáp ứng điều kiện của concurrent refresh.
7. Khởi tạo materialized view `WITH NO DATA`, nạp lần đầu, xây index và chuyển sang refresh đồng thời.
8. Nhận diện rủi ro duplicate rows/khóa logic không duy nhất, dữ liệu thay đổi giữa các lần refresh và vấn đề quyền truy cập.
9. Dùng `pg_matviews`, `pg_indexes`, `pg_stat_activity` và `pg_locks` để quan sát trạng thái, index và refresh đang chạy.
10. Thiết kế lịch refresh, giám sát freshness, xử lý refresh lỗi và chọn giải pháp thay thế nếu yêu cầu dữ liệu real-time.

## 2. VIEW thường, MATERIALIZED VIEW và bảng thường

### 2.1. VIEW thường lưu định nghĩa, không lưu kết quả theo mặc định

```sql
CREATE VIEW reporting.daily_revenue_live AS
SELECT tenant_id, sale_date, SUM(amount) AS revenue
FROM sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

Khi `SELECT` qua view thường, PostgreSQL dùng định nghĩa view như một phần của query để xây kế hoạch và lấy dữ liệu nguồn theo quy tắc MVCC tại thời điểm truy vấn. View thường **không có bản sao kết quả tồn tại độc lập** mà ta cần refresh.

### 2.2. MATERIALIZED VIEW lưu kết quả

```sql
CREATE MATERIALIZED VIEW reporting.daily_revenue AS
SELECT tenant_id, sale_date, SUM(amount) AS revenue
FROM sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

Materialized view lưu kết quả của query vào cấu trúc vật lý, có thể tạo index trên các cột kết quả, có statistics và được quét như bảng khi SELECT. Câu query gốc được PostgreSQL lưu lại để dùng khi làm mới.

Khi `sales` thay đổi, những kết quả đã lưu **không tự đổi**. `REFRESH MATERIALIZED VIEW` chạy lại truy vấn để tạo tập kết quả mới.

### 2.3. Bảng tổng hợp tự duy trì là lựa chọn khác

Một bảng `reporting.daily_revenue_cache` do ứng dụng cập nhật trong cùng transaction, trigger hoặc event consumer có thể được duy trì theo những thay đổi riêng lẻ. Đó **không phải** materialized view tự có incremental maintenance của PostgreSQL.

Materialized view chuẩn rất hữu ích khi chấp nhận một khoảng trễ cập nhật. Nếu cần mỗi giao dịch lập tức phản ánh ở báo cáo với consistency chặt, cần xem kiến trúc bảng tổng hợp transactional hoặc query trực tiếp.

### 2.4. So sánh nhanh

| Đặc điểm | VIEW | MATERIALIZED VIEW | Bảng tổng hợp do ứng dụng duy trì |
| --- | --- | --- | --- |
| Lưu sẵn tập kết quả? | Không, thông thường. | Có. | Có. |
| Tự phản ánh thay đổi nguồn? | Khi query chạy, theo snapshot SQL. | Không; cần REFRESH. | Tùy logic đồng bộ. |
| Có index riêng trên kết quả? | Không, index ở bảng nguồn. | Có thể tạo index. | Có thể tạo index. |
| Phải quản lý refresh? | Không. | Có. | Phải quản lý cơ chế cập nhật. |
| Có thể stale? | Không theo kiểu snapshot cache vật hóa; vẫn chịu MVCC của truy vấn. | Có, từ lần refresh gần nhất. | Tùy cơ chế. |
| Phù hợp | Trừu tượng hóa câu SQL, truy vấn live. | Báo cáo/tổng hợp có độ trễ chấp nhận được. | Số liệu cần cập nhật theo transaction/event hoặc logic riêng. |

## 3. Cú pháp REFRESH MATERIALIZED VIEW

```sql
REFRESH MATERIALIZED VIEW [ CONCURRENTLY ] view_name
    [ WITH [ NO ] DATA ];
```

Trong đó:

- **`view_name`**: materialized view đã tồn tại; nên ghi đầy đủ schema để tránh nhầm `search_path`.
- **Không có `CONCURRENTLY`**: làm mới theo chế độ thông thường, có thể chặn các SELECT đọc chính view trong thời gian refresh.
- **`CONCURRENTLY`**: thực hiện refresh mà không khóa các SELECT thông thường đang đọc view; yêu cầu populated view và UNIQUE index hợp lệ.
- **`WITH DATA`**: thực hiện query định nghĩa view và cập nhật dữ liệu; đây là **mặc định**.
- **`WITH NO DATA`**: không lấy dữ liệu mới, làm view ở trạng thái **không thể quét/truy vấn (unscannable)** cho đến lần làm mới có dữ liệu.

Ví dụ:

```sql
-- Làm mới thông thường; ngầm định WITH DATA:
REFRESH MATERIALIZED VIEW reporting.daily_revenue;

-- Có thể chọn ghi rõ:
REFRESH MATERIALIZED VIEW reporting.daily_revenue WITH DATA;

-- Cho phép SELECT tiếp tục trong khi cập nhật:
REFRESH MATERIALIZED VIEW CONCURRENTLY
    reporting.daily_revenue;

-- Không giữ tập dữ liệu đã lưu và khiến view unscannable:
REFRESH MATERIALIZED VIEW reporting.daily_revenue
    WITH NO DATA;
```

**Không hợp lệ:**

```sql
-- Không được kết hợp hai tùy chọn này:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     reporting.daily_revenue WITH NO DATA;
```

`CONCURRENTLY` chỉ có ý nghĩa khi đang thay tập kết quả mà người đọc có thể tiếp tục dùng bản cũ. `WITH NO DATA` làm view không thể quét nên không kết hợp với concurrent refresh.

### 3.1. REFRESH không thay đổi định nghĩa SELECT

Nếu materialized view được tạo từ `SELECT ... FROM sales WHERE status='paid'`, lệnh REFRESH **không tự đổi** điều kiện WHERE, cấu trúc cột hay cách GROUP BY. Nó dùng định nghĩa đã lưu của materialized view.

Muốn thay đổi định nghĩa query ở mức lớn thường cần một chiến lược tạo lại view/migration phù hợp, không phải truyền SELECT mới vào lệnh REFRESH.

### 3.2. REFRESH là làm mới theo yêu cầu

PostgreSQL **không tự lập lịch REFRESH** chỉ vì có materialized view. Trigger làm mới, job scheduler, pg_cron extension nếu được cài đặt hoặc bộ điều phối ETL là những lựa chọn bên ngoài hành vi mặc định của lệnh.

### 3.3. Không có tham số WHERE trong cú pháp REFRESH

```sql
-- Không có cú pháp chuẩn này:
-- REFRESH MATERIALIZED VIEW reporting.daily_revenue
-- WHERE tenant_id = 7;
```

REFRESH làm mới **kết quả của query định nghĩa toàn view**, không cho phép chỉ định phạm vi một tenant hay một tháng ngay trong cú pháp chuẩn. Nếu cần incremental/cục bộ theo từng key, phải thiết kế phương án khác.

## 4. Materialized view stale là như thế nào?

Giả sử dữ liệu nguồn tại ba thời điểm:

```text
T0  (09:00)  orders có 100 hàng paid
             REFRESH daily_revenue hoàn thành
             MV hiện có doanh thu từ 100 hàng

T1  (09:05)  20 đơn paid mới được COMMIT vào orders
             MV vẫn chỉ phản ánh snapshot lần REFRESH T0

T2  (09:10)  REFRESH lần hai hoàn thành
             MV phản ánh tập dữ liệu nguồn quan sát tại lần refresh mới
```

Giữa T1 và T2:

```sql
SELECT SUM(amount)
FROM sales
WHERE status = 'paid';
```

có thể khác:

```sql
SELECT SUM(revenue)
FROM reporting.daily_revenue;
```

Điều này **không nhất thiết là database lỗi nhất quán**. Nó là kết quả của quyết định kiến trúc dùng cache vật hóa cập nhật theo lịch.

### 4.1. Freshness SLA

Trước khi dùng materialized view, cần trả lời:

- Báo cáo chấp nhận trễ 30 giây, 5 phút, một giờ hay một ngày?
- Thời gian REFRESH thực tế bao lâu?
- Có thể có nhiều batch nguồn đến muộn không?
- Khi refresh thất bại, hệ thống được phép phục vụ dữ liệu cũ trong bao lâu?
- Có cần hiển thị “Cập nhật lần cuối lúc ...” trên UI không?

Nếu yêu cầu số dư tài khoản phải chính xác ngay sau COMMIT, refresh định kỳ thường không phải cơ chế phù hợp.

### 4.2. Không đánh đồng thời điểm bắt đầu và thời điểm kết thúc

Giả sử refresh bắt đầu 09:00, chạy 4 phút, hoàn thành 09:04. Dữ liệu nguồn commit lúc 09:03 **không được bảo đảm có trong kết quả refresh đó** nếu query nguồn sử dụng snapshot đã xác lập trước khi commit. Vì vậy “lần refresh thành công 09:04” **không đồng nghĩa** toàn bộ dữ liệu nguồn commit đến 09:04 đã hiện diện.

Thiết kế freshness nên xác định cả **thời điểm/điểm cắt dữ liệu nguồn** nếu cần. Một timestamp “refresh_finished_at” chỉ nói thời điểm thao tác hoàn thành, không chứng minh watermark nghiệp vụ.

## 5. REFRESH thông thường hoạt động như thế nào?

```sql
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
```

PostgreSQL thực thi query đã lưu của materialized view, tạo tập kết quả và thay dữ liệu vật hóa. Trong thời gian đó, chế độ thường lấy lock trên chính materialized view ở mức **ACCESS EXCLUSIVE**.

### 5.1. ACCESS EXCLUSIVE tác động gì?

`ACCESS EXCLUSIVE` xung đột với `ACCESS SHARE` mà SELECT thông thường cần trên relation, nên một SELECT đến đúng materialized view trong lúc lock được giữ có thể **bị chờ**.

```text
Session A                             Session B
---------                             ---------
REFRESH MATERIALIZED VIEW ...
  có ACCESS EXCLUSIVE lock
                                      SELECT * FROM materialized_view;
                                      -> có thể đợi lock A
COMMIT / lệnh kết thúc
                                      -> SELECT tiếp tục
```

Các bảng nguồn vẫn có lock/snapshot riêng khi query định nghĩa chạy. Không có nghĩa ACCESS EXCLUSIVE trên materialized view đồng thời khóa mọi bảng nguồn theo cùng mode.

### 5.2. Tại sao chế độ thường vẫn có ích?

Refresh thường có thể:

- Dùng ít tài nguyên hơn và hoàn thành nhanh hơn khi tập dữ liệu thay đổi nhiều.
- Có thiết lập đơn giản hơn, không cần UNIQUE index để chọn chế độ thường.
- Phù hợp báo cáo làm mới vào cửa sổ bảo trì hoặc khi không có reader truy cập.
- Phù hợp lần nạp đầu khi materialized view chưa có dữ liệu.

**Đừng mặc định CONCURRENTLY luôn nhanh hơn.** Mục tiêu chính của tùy chọn đó là **không chặn SELECT trên view**, không phải bảo đảm thời gian REFRESH ngắn hơn.

### 5.3. Transaction và atomicity

REFRESH là một thao tác SQL có tính transaction. Người đọc không thấy một bảng “đang được chèn nửa chừng” như sản phẩm cuối cùng của một refresh đã commit. Trong chế độ thường, SELECT có thể phải đợi lock; sau khi refresh hoàn thành/commit, phiên đọc với snapshot phù hợp thấy tập dữ liệu mới.

Nếu refresh thất bại và transaction rollback, không được coi “một nửa hàng mới đã được xuất bản” là trạng thái hợp lệ của materialized view.

### 5.4. Lock có thể giữ đến hết transaction

Nếu đặt REFRESH trong transaction tường minh:

```sql
BEGIN;
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
-- Transaction chưa COMMIT...
```

lock mà REFRESH đã lấy thường tiếp tục được giữ đến khi transaction kết thúc. Đây là lý do không nên để một session chạy REFRESH rồi **idle in transaction** quá lâu; ngay cả khi bước tính dữ liệu đã xong, người đọc vẫn có thể chờ transaction COMMIT.

## 6. REFRESH ... CONCURRENTLY khác gì?

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    reporting.daily_revenue;
```

Tùy chọn này cho phép các câu `SELECT` thông thường tiếp tục đọc materialized view trong khi REFRESH thực hiện công việc cập nhật. Theo cơ chế lock của PostgreSQL, concurrent refresh lấy lock mức **EXCLUSIVE** trên materialized view, vẫn tương thích với `ACCESS SHARE` của SELECT thông thường, nhưng **không** có nghĩa hoàn toàn không có locks.

### 6.1. Sơ đồ đọc trong lúc làm mới

```text
             Materialized view đã populated
                          |
             dữ liệu được công bố hiện tại
                          |
            +-------------+--------------+
            |                            |
            v                            v
      Session A                      Session B
      REFRESH ...                    SELECT ...
      CONCURRENTLY                   đọc MV theo snapshot
            |                            |
            |  xây kết quả mới           |
            |  và reconcile              |
            |                            |
            +------ COMMIT --------------+
                          |
            các SELECT mới, với snapshot
            phù hợp, thấy kết quả cập nhật
```

### 6.2. Người đọc thấy dữ liệu nào?

Trong lúc REFRESH CONCURRENTLY chạy, SELECT có thể tiếp tục đọc **phiên bản dữ liệu vật hóa đang nhìn thấy theo MVCC snapshot**. Sau khi refresh commit, những truy vấn mới với snapshot phù hợp thấy phiên bản cập nhật. Một transaction snapshot cũ có thể tiếp tục nhìn thấy dữ liệu cũ theo quy tắc MVCC.

**Không có “live update” tự động:** khi bảng nguồn vừa nhận một row, materialized view có thể vẫn stale cho tới khi một refresh commit.

### 6.3. Vì sao cần UNIQUE index?

Với concurrent refresh, PostgreSQL cần cơ sở để đối chiếu tập kết quả cũ và mới, xác định những hàng cần thêm/xóa/sửa trong quá trình giữ khả năng đọc song song. Một **UNIQUE index hợp lệ trên các cột kết quả** là điều kiện bắt buộc của cơ chế này.

Chỉ có `PRIMARY KEY` ở bảng nguồn chưa đủ: materialized view phải **có UNIQUE index của chính nó** thỏa điều kiện.

### 6.4. Concurrent refresh không phải “chỉ lấy hàng mới”

Trong PostgreSQL chuẩn, REFRESH CONCURRENTLY **vẫn chạy query định nghĩa để tạo tập kết quả mới**, rồi thực hiện công việc đối chiếu/cập nhật. Nó **không mặc định đọc WAL để chỉ cộng 10 đơn mới** vào số doanh thu, cũng không tự duy trì incremental aggregates.

Nếu view tổng hợp dữ liệu nguồn 500 triệu hàng, chi phí tính toàn bộ SELECT có thể vẫn lớn dù phần kết quả thay đổi chỉ một vài dòng.

### 6.5. Chỉ một REFRESH trên cùng view tại một thời điểm

Ngay cả với `CONCURRENTLY`, PostgreSQL chỉ cho **một lệnh REFRESH tại một thời điểm trên cùng materialized view**. Scheduler không nên bắn nhiều refresh trùng nhau vì nghĩ “concurrently” nghĩa là được nhiều refresh song song.

Các view khác nhau có thể có những hoạt động refresh riêng, nhưng vẫn chia sẻ CPU, I/O, WAL, locks trên bảng nguồn và tài nguyên hệ thống.

### 6.6. Bảng so sánh

| Khía cạnh | REFRESH thường | REFRESH CONCURRENTLY |
| --- | --- | --- |
| Lệnh | `REFRESH MATERIALIZED VIEW v` | `REFRESH MATERIALIZED VIEW CONCURRENTLY v` |
| Đọc SELECT đồng thời | Có thể bị chặn bởi lock | SELECT thông thường có thể tiếp tục đọc |
| Lock trên materialized view | ACCESS EXCLUSIVE | EXCLUSIVE |
| Yêu cầu view đã populated | Không | **Có** |
| Yêu cầu UNIQUE index phù hợp | Không | **Có** |
| Kết hợp WITH NO DATA | Có thể | **Không** |
| Tốc độ | Có thể nhanh hơn khi thay phần lớn dữ liệu | Có overhead đối chiếu; có thể có lợi khi thay ít hàng |
| Có incremental maintenance tự động? | Không | Không |
| Cho hai REFRESH cùng view chạy song song? | Không | Không |
| Bảo đảm query đọc nguồn real-time? | Không | Không |

## 7. Hai điều kiện bắt buộc khi dùng CONCURRENTLY

Đây là phần quan trọng nhất khi vận hành.

### 7.1. Điều kiện 1: view phải đã populated

Một materialized view tạo bằng:

```sql
CREATE MATERIALIZED VIEW some_view AS
SELECT ...
WITH NO DATA;
```

đang ở trạng thái **chưa có dữ liệu sử dụng được**, không thể `SELECT` bình thường từ nó. Lần REFRESH đầu phải là:

```sql
REFRESH MATERIALIZED VIEW some_view WITH DATA;
```

Sau khi đã populated, mới có thể dùng `REFRESH ... CONCURRENTLY` nếu đáp ứng điều kiện về index.

**Lưu ý:** populated không đồng nghĩa view có **ít nhất một row**. Một materialized view với query trả **0 hàng** vẫn có thể ở trạng thái populated/scannable sau `REFRESH ... WITH DATA`. Điều kiện nói về **trạng thái nạp dữ liệu**, không phải row count lớn hơn 0.

### 7.2. Điều kiện 2: UNIQUE index hợp lệ trên view

Ví dụ một materialized view trả mỗi cặp `(tenant_id, sale_date)` đúng một row:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_date
ON reporting.daily_revenue (tenant_id, sale_date);
```

Đây là index đáp ứng điều kiện nếu:

- Index được tạo trên **chính materialized view**.
- Index là **UNIQUE** và hợp lệ.
- Index keys là **tên các cột** của materialized view, không phải expression.
- Index bao gồm **toàn bộ rows** của materialized view, không có `WHERE` giới hạn tập rows (không phải partial index).

### 7.3. UNIQUE index chỉ dùng biểu thức không được chấp nhận

Ví dụ không đủ điều kiện `CONCURRENTLY`:

```sql
-- Đường index có expression, không đáp ứng riêng điều kiện:
CREATE UNIQUE INDEX ux_summary_lower_region
ON reporting.some_summary ((lower(region)));
```

Index này có thể hữu ích cho truy vấn khác nhưng **không phải loại unique index chỉ dùng tên cột** mà `REFRESH CONCURRENTLY` yêu cầu.

### 7.4. UNIQUE partial index cũng không đủ

```sql
-- Chỉ ràng buộc một phần rows, không đạt điều kiện:
CREATE UNIQUE INDEX ux_summary_current
ON reporting.some_summary (tenant_id, sale_date)
WHERE is_current;
```

Những rows không thỏa `WHERE` không được index này kiểm soát. Do đó nó không đáp ứng yêu cầu index bao phủ **mọi row** của materialized view.

### 7.5. Index thông thường không có UNIQUE không đủ

```sql
-- Không đáp ứng riêng điều kiện:
CREATE INDEX idx_summary_tenant_date
ON reporting.some_summary (tenant_id, sale_date);
```

Index có thể giúp SELECT nhưng không bảo đảm identity của rows trong refresh reconciliation. Nếu chỉ có index này, `REFRESH ... CONCURRENTLY` vẫn có thể bị từ chối vì thiếu một UNIQUE index phù hợp.

### 7.6. UNIQUE index trên bảng nguồn không đủ

```sql
-- Bảng sales có PRIMARY KEY(order_id)
-- không đồng nghĩa materialized view có UNIQUE index.
```

Materialized view là một quan hệ riêng, tập kết quả có thể GROUP BY/JOIN làm thay đổi tính duy nhất. Phải chứng minh và tạo index trên **các cột kết quả** của view.

### 7.7. Không phải bắt buộc một cột

UNIQUE index có thể gồm nhiều cột:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_date
ON reporting.daily_revenue (tenant_id, sale_date);
```

Đây là trường hợp phổ biến vì một hàng tổng hợp thường được định danh bằng **khóa nhóm**. Một cột duy nhất như `sale_date` có thể không unique khi nhiều tenant có cùng ngày.

### 7.8. Tạo index không sửa được định nghĩa view sai

Nếu query định nghĩa tạo hai hàng có cùng `(tenant_id,sale_date)`, lệnh `CREATE UNIQUE INDEX` sẽ thất bại. Không nên “chữa” bằng cách thêm `DISTINCT` bừa bãi vào query nếu nó làm đổi nghĩa doanh thu.

Thay vào đó phải xác định khóa nhóm/khóa nghiệp vụ đúng, sửa logic JOIN tránh nhân bản rows, hoặc thay đổi cách tổng hợp.

## 8. Bộ dữ liệu thực hành hoàn chỉnh

Toàn bộ SQL trong phần này dùng schema `mv_refresh_lab`; chỉ chạy trong **database thực hành**. Người học không cần có bảng `sales` hoặc schema `reporting` giả định ở các ví dụ trước.

### 8.1. Tạo schema và bảng nguồn

```sql
CREATE SCHEMA IF NOT EXISTS mv_refresh_lab;

CREATE TABLE mv_refresh_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    tenant_id integer NOT NULL,
    sale_date date NOT NULL,
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled'))
);
```

Thiết kế này cố ý đơn giản: `sale_date` là kiểu `date` không phụ thuộc timezone session, `amount` là numeric cho số tiền, và chỉ những hàng `status='paid'` mới được tính doanh thu.

### 8.2. Chèn dữ liệu mẫu

```sql
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (1, DATE '2026-11-01', 100.00, 'paid'),
    (1, DATE '2026-11-01',  50.00, 'paid'),
    (1, DATE '2026-11-01', 300.00, 'cancelled'),
    (1, DATE '2026-11-02',  75.00, 'paid'),
    (2, DATE '2026-11-01', 200.00, 'paid'),
    (2, DATE '2026-11-02',  30.00, 'pending');
```

Chạy một lần trên bảng trống. Nếu chạy lại, vì `sale_id` là identity tự sinh, những hàng nghiệp vụ sẽ bị nhân đôi thay vì báo lỗi trùng khóa — điều này làm kết quả bài tập khác đi. Có thể tạo database lab mới hoặc khôi phục dataset nếu muốn lặp lại từ đầu.

### 8.3. Kiểm tra dữ liệu nguồn

```sql
SELECT
    tenant_id,
    sale_date,
    SUM(amount) AS revenue,
    COUNT(*) AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
ORDER BY tenant_id, sale_date;
```

Kết quả:

| tenant_id | sale_date | revenue | paid_orders |
| ---: | --- | ---: | ---: |
| 1 | 2026-11-01 | 150.00 | 2 |
| 1 | 2026-11-02 | 75.00 | 1 |
| 2 | 2026-11-01 | 200.00 | 1 |

Hàng pending và cancelled **không** tính vào tổng này.

### 8.4. Tạo materialized view có dữ liệu

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.daily_revenue AS
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue,
    COUNT(*)::bigint AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
WITH DATA;
```

`WITH DATA` có thể bỏ qua vì mặc định đã là nạp dữ liệu. Bài ghi rõ để người học thấy khác với `WITH NO DATA`.

### 8.5. SELECT dữ liệu đã được vật hóa

```sql
SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

Kết quả giống bảng tổng hợp ở phần 8.3 khi chưa có thay đổi nguồn.

### 8.6. Tạo UNIQUE index đáp ứng CONCURRENTLY

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
    (tenant_id, sale_date);
```

Mỗi `(tenant_id,sale_date)` có đúng một dòng vì query định nghĩa đã GROUP BY hai cột đó, nên đây là khóa logic phù hợp trong lab.

Index này có **hai vai trò**:

1. Bảo đảm uniqueness của khóa tổng hợp trong materialized view.
2. Cho phép dùng `REFRESH MATERIALIZED VIEW CONCURRENTLY` vì chỉ gồm tên cột và bao phủ toàn bộ rows.

Nó cũng có thể giúp một số truy vấn SELECT theo tenant/ngày, nhưng PostgreSQL vẫn chọn scan dựa trên chi phí.

### 8.7. Kiểm tra trạng thái populated

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue';
```

Sau khi tạo `WITH DATA` và có index, kỳ vọng `ispopulated=true` và `hasindexes=true`. **`hasindexes=true` chưa chứng minh có UNIQUE index hợp lệ**, chỉ cho biết view có index; kiểm tra index definition riêng ở phần sau.

### 8.8. Dữ liệu nguồn thay đổi, view chưa đổi

Chèn thêm một giao dịch:

```sql
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (1, DATE '2026-11-01',  25.00, 'paid'),
    (2, DATE '2026-11-02', 110.00, 'paid');
```

Hai hàng mới đã COMMIT trong chế độ autocommit thông thường. Query bảng nguồn:

```sql
SELECT
    tenant_id,
    sale_date,
    SUM(amount) AS current_revenue
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
ORDER BY tenant_id, sale_date;
```

Sẽ có hai thay đổi quan trọng:

- Tenant 1, 01/11: doanh thu từ 150 lên **175**.
- Tenant 2, 02/11: xuất hiện nhóm mới doanh thu **110**.

Nhưng:

```sql
SELECT tenant_id, sale_date, revenue
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

vẫn hiển thị kết quả **cũ** do chưa REFRESH.

### 8.9. Làm mới thông thường

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

Kỳ vọng:

| tenant_id | sale_date | revenue | paid_orders |
| ---: | --- | ---: | ---: |
| 1 | 2026-11-01 | 175.00 | 3 |
| 1 | 2026-11-02 | 75.00 | 1 |
| 2 | 2026-11-01 | 200.00 | 1 |
| 2 | 2026-11-02 | 110.00 | 1 |

Đây là ảnh chụp dữ liệu nguồn tại thời điểm refresh phù hợp, không phải một quan hệ luôn đồng bộ sau đó.

### 8.10. Cập nhật nguồn rồi refresh CONCURRENTLY

Giả sử có đơn pending ban đầu của tenant 2, 02/11 với `amount=30`. Đổi trạng thái hàng đó thành paid:

```sql
UPDATE mv_refresh_lab.sales
SET status = 'paid'
WHERE tenant_id = 2
  AND sale_date = DATE '2026-11-02'
  AND amount = 30.00
  AND status = 'pending';
```

Trước REFRESH, materialized view của tenant 2 ngày 02/11 vẫn có revenue 110. Sau:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 2
  AND sale_date = DATE '2026-11-02';
```

Kết quả cập nhật thành **revenue = 140.00** và **paid_orders = 2**.

### 8.11. Trường hợp nhóm biến mất

Nếu tất cả hàng paid của một cặp tenant/ngày được chuyển sang cancelled, query định nghĩa không còn trả nhóm đó. Refresh sau sẽ làm nhóm tương ứng biến mất khỏi materialized view, không phải để nó ở revenue 0 trừ khi query định nghĩa được xây để trả tất cả nhóm kể cả không có paid orders.

Ví dụ chỉ chạy trong transaction rồi rollback để không ảnh hưởng lab:

```sql
BEGIN;

UPDATE mv_refresh_lab.sales
SET status = 'cancelled'
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-02'
  AND status = 'paid';

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

SELECT *
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-02';

ROLLBACK;
```

Trong transaction, SELECT sau refresh không còn nhóm này. Sau `ROLLBACK`, thay đổi nguồn **và** refresh nằm trong cùng transaction đều được hoàn tác. Không dùng transaction dài như vậy trong production nếu không cần thiết; ví dụ nhằm thể hiện ngữ nghĩa atomicity.

## 9. WITH NO DATA và vòng đời populated/unscannable

Materialized view có hai trạng thái cần phân biệt:

```text
               CREATE MATERIALIZED VIEW ...
                          |
               +----------+-----------+
               |                      |
            WITH DATA              WITH NO DATA
               |                      |
               v                      v
            populated              unscannable
               |                      |
               |               REFRESH ... WITH DATA
               |                      |
               +----------------------+
                          |
                          v
                       populated
                          |
             REFRESH ... WITH NO DATA
                          |
                          v
                      unscannable
```

### 9.1. Tạo view nhưng chưa nạp dữ liệu

Trong lab, tạo một materialized view khác, không ảnh hưởng `daily_revenue`:

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.daily_revenue_later AS
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
WITH NO DATA;
```

Kiểm tra:

```sql
SELECT matviewname, ispopulated
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue_later';
```

`ispopulated=false`. **Không thể SELECT dữ liệu từ view này** trong trạng thái unscannable.

### 9.2. Lệnh CONCURRENTLY đầu tiên sẽ không được chấp nhận

```sql
-- Lệnh sau dự kiến lỗi do view chưa populated:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     mv_refresh_lab.daily_revenue_later;
```

Ngay cả khi bạn tạo UNIQUE index trên view trước đó, trạng thái unscannable vẫn khiến `CONCURRENTLY` không hợp lệ.

### 9.3. Nạp lần đầu bằng REFRESH thường

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;

SELECT *
FROM mv_refresh_lab.daily_revenue_later
ORDER BY tenant_id, sale_date;
```

Từ đây view **scannable**. Nó có thể có 0 row nếu query nguồn không trả dòng nào nhưng vẫn được đánh dấu populated.

### 9.4. Tạo UNIQUE index, sau đó dùng CONCURRENTLY

```sql
CREATE UNIQUE INDEX ux_daily_revenue_later
ON mv_refresh_lab.daily_revenue_later
    (tenant_id, sale_date);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue_later;
```

Thứ tự đúng cho bootstrap:

```text
CREATE MV WITH NO DATA
        |
        v
REFRESH MV WITH DATA     (không CONCURRENTLY)
        |
        v
CREATE UNIQUE INDEX     (trên cột, toàn bộ rows)
        |
        v
REFRESH MV CONCURRENTLY (các lần tiếp theo)
```

Bạn cũng có thể tạo materialized view `WITH DATA` ngay từ đầu rồi tạo UNIQUE index. Quyết định phụ thuộc thời gian tạo/nạp dữ liệu và kế hoạch triển khai.

### 9.5. WITH NO DATA trên view đã populated

```sql
-- Mẫu thử riêng trên view phụ để tránh mất dữ liệu lab chính:
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH NO DATA;
```

Sau đó `ispopulated=false`, view unscannable; các truy vấn SELECT dữ liệu từ nó sẽ báo lỗi thay vì trả một tập 0 rows bình thường. UNIQUE index nếu còn tồn tại **không làm view trở nên scannable**.

Muốn phục hồi:

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;
```

Sau khi có dữ liệu và index hợp lệ, mới dùng CONCURRENTLY ở lần tiếp theo.

### 9.6. Không dùng WITH NO DATA để “tạm hiển thị báo cáo rỗng”

`WITH NO DATA` không biến materialized view thành một view có **0 row hợp lệ để truy vấn**. Nó khiến view **không thể quét**, nên API đọc dữ liệu sẽ gặp lỗi. Nếu nghiệp vụ muốn hiển thị báo cáo rỗng, phải có chiến lược khác.

## 10. Kiểm tra UNIQUE index bằng catalog

Một index tồn tại không có nghĩa đáp ứng `CONCURRENTLY`. Có thể đọc:

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'mv_refresh_lab'
  AND tablename = 'daily_revenue'
ORDER BY indexname;
```

Kỳ vọng thấy:

```text
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
USING btree (tenant_id, sale_date)
```

Trình bày của `pg_get_indexdef`/`indexdef` có thể hơi khác theo major, nhưng ý chính là **UNIQUE** trên hai tên cột, không có `WHERE`.

### 10.1. Kiểm tra thuộc tính catalog

```sql
SELECT
    idx.relname AS index_name,
    i.indisunique AS is_unique,
    i.indisvalid AS is_valid,
    i.indpred IS NULL AS covers_all_rows,
    i.indexprs IS NULL AS only_column_keys,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY idx.relname;
```

Ở index `ux_daily_revenue_tenant_day`, các cờ `is_unique`, `is_valid`, `covers_all_rows` và `only_column_keys` đều TRUE.

Đây là truy vấn quan sát để **hỗ trợ nhận diện** candidate index; ứng dụng không nên tự tuyên bố “CONCURRENTLY chắc chắn thành công” chỉ từ bốn cột boolean, vì còn điều kiện populated, tính đúng đắn dữ liệu, quyền và resource/lock constraints.

### 10.2. UNIQUE index trên biểu thức có thể vẫn có lợi ích riêng

Ví dụ minh họa:

```sql
-- Index này không phải eligible UNIQUE index cho concurrent refresh:
-- CREATE UNIQUE INDEX ux_lower_name
-- ON some_materialized_view ((lower(name)));
```

Nó có thể dùng để enforce uniqueness theo biểu thức và phục vụ SELECT, nhưng không thay thế index cần cho `REFRESH CONCURRENTLY`.

### 10.3. Partial UNIQUE index không bao trùm tất cả hàng

```sql
-- Không eligible:
-- CREATE UNIQUE INDEX ux_active
-- ON some_materialized_view (tenant_id, sale_date)
-- WHERE active;
```

Nếu query của view đã lọc chỉ `active`, index không cần thêm `WHERE active` để phục vụ concurrent refresh. Với những cột kết quả phù hợp, tạo **UNIQUE index không có WHERE** trên toàn bộ rows thực của materialized view mới là hướng đúng.

### 10.4. NULL trong khóa UNIQUE

Trong nhiều phiên bản PostgreSQL, UNIQUE index mặc định cho phép nhiều rows có cùng các giá trị non-NULL nhưng khác/đều NULL ở một phần key. Từ PostgreSQL 15 có tùy chọn `NULLS NOT DISTINCT` để thay đổi cách NULL được xem xét trong uniqueness.

Đối với materialized view tổng hợp, nếu khóa logic có NULL, cần xác định **ngữ nghĩa nhóm và uniqueness thật sự**. PostgreSQL có quy tắc nội bộ cho concurrent refresh và các bản ghi trùng nhau; đừng mặc định chỉ tạo index trên các cột nullable là đủ đảm bảo một định danh nghiệp vụ duy nhất theo cách application mong muốn.

Trong lab, `tenant_id` và `sale_date` từ bảng nguồn đều `NOT NULL` nên tránh được trường hợp này.

### 10.5. Không chọn khóa theo “thứ tự hàng”

Vì materialized view không được bảo đảm thứ tự ổn định khi refresh, không nên tạo định danh bằng `row_number() OVER (...)` rồi coi nó là **ID bất biến** giữa các lần nạp. Khi tập nguồn thay đổi, thứ tự và row_number có thể thay đổi, làm nhiều rows bị nhận diện khác trước và tăng chi phí reconcile hoặc làm hỏng logic liên kết nghiệp vụ.

Ưu tiên các khóa dựa trên business identity/grouping ổn định như `(tenant_id,sale_date)`.

## 11. Thử quan sát locks với hai session

Để hiểu tại sao REFRESH thường có thể chặn SELECT, hãy mở **hai kết nối psql riêng đến cùng database lab**. Không dùng thủ thuật giữ lock/sleep trên production. Thử nghiệm nhằm thể hiện khác biệt lock; một view 4 rows refresh quá nhanh có thể khó quan sát trực tiếp nếu không kéo dài transaction.

### 11.1. Chuẩn bị ở Session A

```sql
BEGIN;

REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

-- Chỉ trong lab: giữ transaction mở vài giây sau refresh.
SELECT pg_sleep(8);

COMMIT;
```

Lệnh `REFRESH` lấy ACCESS EXCLUSIVE trên materialized view và lock thường được giữ tới cuối transaction. Trong lúc Session A đang ngủ trước COMMIT, chạy Session B:

### 11.2. Session B khi Session A refresh thường

```sql
SET lock_timeout = '2s';

SELECT COUNT(*)
FROM mv_refresh_lab.daily_revenue;

RESET lock_timeout;
```

Nếu SELECT bắt đầu trong khoảng Session A giữ lock, nó có thể báo lỗi do chờ khóa quá 2 giây. Đây là kết quả mong đợi của mô phỏng contention, không phải dấu hiệu materialized view bị hỏng.

**Nếu bỏ lỡ cửa sổ 8 giây**, SELECT có thể chạy bình thường. Có thể chạy lại lab với hai sessions được điều khiển rõ ràng, không tăng `pg_sleep` vô hạn và không thử trên production.

### 11.3. Thử lại với CONCURRENTLY ở Session A

```sql
BEGIN;

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

-- Chỉ trong lab:
SELECT pg_sleep(8);

COMMIT;
```

Trong lúc Session A giữ EXCLUSIVE lock, Session B chạy:

```sql
SET lock_timeout = '2s';

SELECT COUNT(*)
FROM mv_refresh_lab.daily_revenue;

RESET lock_timeout;
```

SELECT thông thường lấy ACCESS SHARE và tương thích với EXCLUSIVE lock; nó **có thể hoàn thành** trong khi Session A chưa commit. Điều này **không** đồng nghĩa Session B nhìn thấy dữ liệu đang thay đổi từng dòng; nó đọc theo MVCC snapshot.

### 11.4. Ghi nhớ giới hạn của demo

- Một số lock khác, DDL khác hoặc tài nguyên quá tải vẫn có thể làm SELECT chậm/chờ, ngay khi dùng CONCURRENTLY.
- Chế độ CONCURRENTLY bảo vệ khả năng SELECT trên **materialized view**, không tự loại mọi lock contention trên bảng nguồn.
- Long-running transactions có thể làm giữ nhiều tuple versions hơn, tạo thêm áp lực VACUUM trong những trường hợp liên quan.
- Nếu Session A quên COMMIT/ROLLBACK, giữ lock quá lâu có thể gây sự cố; luôn kết thúc transaction thực hành.

### 11.5. Quan sát session chờ lock bằng SQL

Từ kết nối giám sát có quyền:

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.query_start NULLS LAST;
```

Khi Session B chờ lock, `wait_event_type` có thể là `Lock`; `wait_event` và trạng thái cụ thể tùy diễn biến. Đừng in nguyên `query` lên dashboard công khai nếu SQL chứa dữ liệu nhạy cảm.

Trong tình huống phát hiện query đang bị chặn, có thể dùng:

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

Hàm `pg_blocking_pids` giúp xác định blockers, nhưng không phải mọi tình trạng chậm đều do table lock.

## 12. Quan sát lock mode của materialized view

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    a.state,
    a.wait_event_type,
    a.wait_event
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.granted, l.mode, l.pid;
```

### 12.1. Những modes cần biết

| Lệnh | Lock trên materialized view | Ảnh hưởng điển hình |
| --- | --- | --- |
| `SELECT ... FROM matview` | ACCESS SHARE | Có thể đọc đồng thời với EXCLUSIVE nhưng không với ACCESS EXCLUSIVE. |
| `REFRESH MATERIALIZED VIEW` | ACCESS EXCLUSIVE | Có thể chặn các SELECT trên view. |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` | EXCLUSIVE | Cho phép SELECT thông thường, chặn một số hành động xung đột khác. |

Locks thường được giữ đến kết thúc transaction. Một `SELECT` ở Session B có thể chờ không chỉ vì REFRESH chưa tính xong mà vì Session A đã tính xong **nhưng chưa COMMIT**.

### 12.2. Lock trên bảng nguồn

Query định nghĩa materialized view phải đọc `mv_refresh_lab.sales` và có các yêu cầu lock/snapshot trên quan hệ nguồn. Đây là lý do một số DDL trên bảng nguồn có thể chờ refresh, dù người đọc materialized view không bị chặn khi dùng `CONCURRENTLY`.

Không diễn giải "CONCURRENTLY" là không có locks hoặc không ảnh hưởng workload.

### 12.3. Không kill session chỉ vì thấy ExclusiveLock

Đó là lock bình thường của concurrent refresh. Việc hủy refresh có thể rollback lượng công việc lớn và tạo thêm áp lực hệ thống. Muốn quyết định cancel/terminate, cần xem elapsed time, blockers, load và chính sách vận hành.

## 13. MVCC và tính nhất quán của dữ liệu trong lần REFRESH

Một materialized view có thể bị **trễ theo thời gian** nhưng một lần refresh vẫn cần trả tập kết quả có ý nghĩa theo quy tắc transaction.

### 13.1. Snapshot nhất quán khi đọc bảng nguồn

Khi PostgreSQL chạy query định nghĩa để làm mới view, nó sử dụng cơ chế snapshot/MVCC của statement/transaction tương ứng. Query không được thiết kế để đọc nửa hàng của một transaction nguồn chưa COMMIT rồi tự ghép với nửa còn lại.

Giả sử một transaction nguồn:

```sql
BEGIN;
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (9, DATE '2026-11-07', 300, 'paid');
-- Chưa COMMIT.
```

Một refresh ở session khác không thể tùy tiện nhìn thấy row uncommitted này. Nếu nguồn COMMIT sau khi snapshot phù hợp đã được xác lập, row có thể không nằm trong kết quả refresh hiện tại mà phải đợi lần sau.

### 13.2. Tại sao "completed" không nghĩa "fresh đến giờ hoàn thành"?

```text
09:00:00  Query refresh lấy snapshot nguồn S
09:00:01  Nguồn nhận COMMIT đơn mới
09:00:10  REFRESH hoàn tất COMMIT view
```

Đơn commit sau snapshot S **không nhất thiết xuất hiện** trong materialized view. Vì vậy muốn báo cáo độ mới, cần phân biệt:

- Thời điểm job bắt đầu.
- Thời điểm snapshot/điểm cắt dữ liệu nguồn.
- Thời điểm job hoàn thành.
- Watermark nghiệp vụ: thời gian event/LSN/sequence đã chắc chắn được xử lý, nếu có cơ chế theo dõi.

### 13.3. Người đọc trong CONCURRENTLY thấy snapshot cũ hay mới?

Khi REFRESH CONCURRENTLY đang chạy nhưng chưa commit, SELECT đang chạy ở session khác **không thấy thay đổi chưa commit**. Sau khi commit, những câu SELECT mới với snapshot phù hợp sẽ đọc kết quả mới. Với `REPEATABLE READ`, transaction có snapshot trước đó có thể tiếp tục nhìn bản cũ theo MVCC.

Không nên xây ứng dụng dựa trên giả định “mọi SELECT ở mọi transaction đồng loạt đổi sang bản mới tại một millisecond mà không cần quan tâm snapshot”.

### 13.4. Không có đảm bảo real-time giữa nhiều materialized views

Nếu có:

```text
reporting.revenue_by_day
reporting.refunds_by_day
reporting.net_revenue_by_day
```

và scheduler refresh ba view ở các thời điểm khác nhau, dashboard truy vấn chúng có thể thấy **ba thời điểm dữ liệu khác nhau**. `CONCURRENTLY` chỉ điều khiển cách refresh từng view trong quan hệ với độc giả, không cung cấp transaction snapshot thống nhất cho tất cả views khi làm mới độc lập.

Nếu business cần phiên bản báo cáo đồng bộ giữa nhiều bảng kết quả, phải thiết kế cơ chế publish/version cutover hoặc transaction refresh phù hợp với locks và SLA.

## 14. Không dựa vào ORDER BY của query định nghĩa

Một truy vấn định nghĩa materialized view có thể chứa `ORDER BY`:

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.top_sales_demo AS
SELECT sale_id, tenant_id, sale_date, amount
FROM mv_refresh_lab.sales
WHERE status = 'paid'
ORDER BY sale_date DESC, sale_id DESC
WITH DATA;
```

Điều này có thể khiến dữ liệu ban đầu được tạo theo một trật tự, nhưng **REFRESH MATERIALIZED VIEW không bảo đảm bảo toàn thứ tự vật lý/đầu ra đó** qua các lần làm mới.

### 14.1. SELECT cần ORDER BY riêng

```sql
SELECT sale_id, tenant_id, sale_date, amount
FROM mv_refresh_lab.top_sales_demo
ORDER BY sale_date DESC, sale_id DESC
LIMIT 20;
```

Nếu ứng dụng cần trang đầu ổn định, hãy có một `ORDER BY` **đầy đủ và mang tính xác định** (ví dụ ngày và sale_id), không dựa vào thứ tự heap hay may mắn từ lần tạo materialized view.

### 14.2. Index hỗ trợ sắp xếp là chuyện riêng

```sql
CREATE INDEX idx_top_sales_date
ON mv_refresh_lab.top_sales_demo
    (sale_date DESC, sale_id DESC);
```

Index có thể giúp một số query ORDER BY/LIMIT, nhưng query vẫn phải **yêu cầu ORDER BY** để có hợp đồng thứ tự kết quả. Index không thay thế cú pháp sắp xếp ở tầng SQL.

### 14.3. LIMIT trong định nghĩa cần khóa sắp xếp ổn định

Nếu materialized view định nghĩa `SELECT ... ORDER BY amount DESC LIMIT 100`, tập top 100 sẽ được tính lại khi REFRESH. Nếu nhiều hàng có cùng amount và không có tie-breaker, tập 100 hàng có thể không xác định hoàn toàn theo nghiệp vụ.

Muốn kết quả có thể dự đoán, thêm các cột tie-breaker hợp lệ trong ORDER BY. Nếu định dùng UNIQUE index theo một rank được sinh ngẫu nhiên, cân nhắc độ ổn định identity trước.

## 15. Chi phí tài nguyên của REFRESH

Việc duy trì materialized view tiêu thụ tài nguyên: chạy SELECT nguồn, tạo hoặc lưu tập kết quả, I/O, memory cho sort/hash, duy trì indexes, WAL và đôi khi cần dung lượng trung gian đáng kể.

### 15.1. Refresh thường

Ở chế độ thường, PostgreSQL có thể dùng chiến lược thay thế toàn bộ dữ liệu vật hóa tương đối trực tiếp. Nếu view gần như thay đổi hết giữa các lần refresh, đây thường là lựa chọn hợp lý về tổng thời gian/tài nguyên khi có thể chấp nhận khóa đọc.

### 15.2. Refresh đồng thời

Concurrent refresh phải chuẩn bị kết quả mới và **đối chiếu** với dữ liệu cũ để cập nhật theo cách cho SELECT tiếp tục đọc. Công việc so sánh, thao tác index và tạo dữ liệu trung gian có thể tăng nhu cầu CPU, I/O, WAL và đĩa.

Nếu kết quả của view thay đổi rất ít, concurrent refresh có thể hữu ích, thậm chí nhanh trong một số trường hợp. Nhưng nó vẫn **chạy lại query nguồn** để tính kết quả; không được coi là một incremental refresh thực thụ.

### 15.3. Khi view có nhiều indexes

Materialized view thường được tạo index để dashboard SELECT nhanh. Mỗi lần refresh, các indexes này cũng cần được duy trì hoặc tái xây dựng tùy cơ chế. Nhiều indexes có thể tăng chi phí write/refresh và dung lượng.

Không tự tạo 20 indexes trên materialized view chỉ để tối ưu mọi câu SELECT hiếm gặp. Cần đo query frequency, read latency và refresh duration.

### 15.4. Dữ liệu nguồn có nhiều JOIN/aggregates

Nếu view định nghĩa:

```sql
SELECT ...
FROM large_orders AS o
JOIN large_order_items AS i
    ON i.order_id = o.id
JOIN large_customers AS c
    ON c.id = o.customer_id
GROUP BY ...;
```

thì một refresh đầy đủ vẫn phải trả chi phí thực thi query phức tạp ấy. `CONCURRENTLY` không tự làm JOIN nhanh hoặc dùng index tốt hơn. Phải tối ưu query nguồn/index/stats như với mọi SELECT.

### 15.5. Thời gian đọc và thời gian refresh là hai SLA

Một thiết kế có thể:

- SELECT từ materialized view: 5 ms.
- REFRESH: 15 phút.
- Khoảng lịch: 5 phút.

Lịch như vậy **không khả thi theo kỳ vọng 5 phút** nếu các refresh không thể hoàn thành trước lịch tiếp theo. Scheduler có thể tạo backlog, locks và stale data tăng. Phải đo cả duration p50/p95/p99 của refresh, không chỉ độ nhanh của SELECT.

### 15.6. Dung lượng tạm và WAL

Khi làm mới trên tập lớn, cần kiểm tra:

- Disk free space, trong đó có không gian cho tập dữ liệu trung gian.
- Temp files/Sort/Hash spills.
- WAL generation và áp lực replication.
- Autovacuum và lượng row versions cũ sau concurrent refresh.
- Read I/O trên bảng nguồn.

Không coi `CONCURRENTLY` là “không cần gấp đôi storage” hoặc “không phát sinh WAL”. Lượng thực tế tùy phương án, kích thước view và số thay đổi.

## 16. Đo chi phí query nguồn và bản vật hóa

`EXPLAIN (ANALYZE, BUFFERS)` rất hữu ích để hiểu SELECT định nghĩa; nó **thực thi SELECT** khi có ANALYZE. Với materialized view báo cáo đơn giản:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue,
    COUNT(*)::bigint AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

Đối chiếu với query đọc view:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, sale_date, revenue
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-01';
```

Một query trực tiếp có thể đọc nhiều hàng và aggregate; query trên materialized view có thể đọc một hàng kết quả đã lưu. Trên lab vài rows, cả hai đều có thể dùng seq scan và khác biệt thời gian rất nhỏ.

### 16.1. Đo duration của chính REFRESH

Trong `psql`:

```text
\timing on
```

Rồi chạy:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;
```

`\timing` là metacommand của **psql client**, không phải SQL cho JDBC. Công cụ giám sát/application có thể đo elapsed duration ở phía job runner và ghi lại success/failure.

### 16.2. So sánh trong điều kiện công bằng

Để so hai chế độ:

1. Dùng cùng dataset và định nghĩa view.
2. Chạy nhiều lần, không chỉ một phép đo đơn lẻ.
3. Ghi tỷ lệ rows của tập kết quả thay đổi.
4. Ghi CPU/I/O/temp/WAL và số độc giả concurrent.
5. Đánh giá cả reader wait time và refresh duration.
6. Không ép tắt index scan/seq scan toàn hệ thống để được con số đẹp.

**Một chế độ nhanh hơn trong lab nhỏ không bảo đảm nhanh hơn trong production.**

### 16.3. Vì sao EXPLAIN không đủ để biết tất cả?

`EXPLAIN` trên query định nghĩa giúp biết chi phí SELECT/aggregate. REFRESH còn có thao tác cập nhật quan hệ và indexes vật hóa, nên cần đo lệnh REFRESH thực tế. Chỉ cộng các cost planner của SELECT không ra thời gian refresh chính xác.

## 17. Quyền hạn REFRESH: khác biệt theo phiên bản

PostgreSQL đã thay đổi mô hình quyền cho một số thao tác bảo trì.

### 17.1. PostgreSQL 17 trở lên

Ở PostgreSQL 17+, quyền **`MAINTAIN`** áp dụng cho REFRESH MATERIALIZED VIEW. Chủ sở hữu relation có quyền phù hợp; người dùng khác cần được cấp quyền hoặc thuộc role tương ứng theo cấu hình.

Mẫu phân quyền:

```sql
-- Ví dụ chỉ khi role đã tồn tại và được chủ sở hữu cấp quyền:
-- GRANT MAINTAIN
-- ON TABLE mv_refresh_lab.daily_revenue
-- TO report_refresh_worker;
```

Không cần cấp quyền superuser chỉ để chạy một refresh định kỳ nếu có cơ chế phân quyền phù hợp.

### 17.2. PostgreSQL 16 trở xuống

Ở các major cũ hơn như PostgreSQL 16, tài liệu của lệnh REFRESH yêu cầu **owner của materialized view** hoặc role có quyền owner tương ứng. Không sao chép lệnh `GRANT MAINTAIN` từ PostgreSQL 17 sang phiên bản chưa hỗ trợ và kỳ vọng nó hoạt động.

Kiểm tra:

```sql
SHOW server_version;
```

và tham khảo tài liệu **đúng major** đang chạy.

### 17.3. Quyền đọc view khác quyền refresh

Một role có quyền:

```sql
SELECT * FROM mv_refresh_lab.daily_revenue;
```

không tự động có quyền làm mới view. Đọc dữ liệu và quản trị làm mới là hai trách nhiệm khác nhau.

### 17.4. Quyền schema và bảo mật

Trong production, tách vai trò:

- Role đọc dashboard chỉ có SELECT cần thiết.
- Role vận hành refresh chỉ có quyền bảo trì cần thiết.
- Role quản trị DDL/index là quyền riêng.
- Các bảng nguồn và user-defined functions trong query định nghĩa được xem xét theo quyền và security model của PostgreSQL.

Không cấp quyền rộng cho `PUBLIC` hoặc chạy refresh dưới superuser khi không cần.

### 17.5. search_path trong quá trình REFRESH

Tài liệu PostgreSQL lưu ý khi REFRESH chạy, `search_path` tạm thời được thay thành `pg_catalog, pg_temp`. Vì vậy không nên xây các user-defined functions hoặc dependencies yêu cầu giải quyết tên không schema-qualified tùy ý trong quá trình refresh.

Trong view định nghĩa, ưu tiên tên quan hệ/hàm do người dùng tạo được schema-qualify khi thiết kế, và kiểm tra behavior theo major. Đây vừa là vấn đề độ tin cậy vừa liên quan an toàn `search_path`.

## 18. REFRESH thất bại thì điều gì xảy ra?

Lệnh REFRESH có thể lỗi vì:

- Không đủ quyền bảo trì.
- Không có UNIQUE index đủ điều kiện với CONCURRENTLY.
- View chưa populated.
- Một toán tử/hàm trong SELECT nguồn báo lỗi.
- Thiếu dung lượng đĩa hoặc temp space.
- Lock timeout, statement timeout hoặc bị hủy.
- Schema/objects nguồn bị thay đổi theo cách không phù hợp.
- Tập kết quả mới không tương thích uniqueness của index.

### 18.1. Không có “nửa view mới” sau rollback hợp lệ

Nếu refresh thất bại trong transaction PostgreSQL, thao tác refresh đó không được commit nửa chừng vào materialized view. View vốn đã populated vẫn có thể tiếp tục có dữ liệu **cũ nhưng hợp lệ** sau rollback.

Tuy nhiên service có thể vẫn vi phạm freshness SLA. Đây là failure về độ mới báo cáo, không nên che bằng cách trả HTTP 200 với tuyên bố “dữ liệu real-time” khi job đang lỗi.

### 18.2. Cần quan sát lỗi thật, không đoán từ last success

Khi refresh lỗi, nên lưu:

- Tên view và job.
- Thời điểm bắt đầu và kết thúc/failed.
- SQLSTATE hoặc thông điệp lỗi đã được làm sạch dữ liệu nhạy cảm.
- Thời lượng và trạng thái retry.
- Last successful refresh.
- Dữ liệu nguồn/độ mới ước lượng nếu có watermark.

Không nên chỉ lưu boolean `refresh_running` rồi bỏ qua các lần thất bại.

### 18.3. Retry có backoff

Nếu lỗi do lock timeout/tải quá cao, có thể retry theo backoff và giới hạn số lần. Nhưng nếu lỗi do thiếu unique index, invalid source schema hoặc duplicate rows, retry liên tục sẽ chỉ làm hệ thống quá tải. Phân loại **transient** và **structural** failures trước.

### 18.4. Hủy job có thể tốn thời gian rollback

Khi refresh đang xử lý dữ liệu lớn, cancellation/rollback có thể tiêu tốn I/O và cần thời gian; không mặc định mọi lệnh cancel hoàn tất tức thì. Hãy định nghĩa timeout và runbook theo workload thực tế.

## 19. Lên lịch REFRESH: làm thế nào để không chạy trùng?

PostgreSQL không tự làm mới materialized view khi bảng nguồn INSERT/UPDATE/DELETE. Bạn phải chọn một **trigger scheduling** bên ngoài semantics mặc định:

- Cron/Task Scheduler chạy lệnh `psql`.
- Background service của ứng dụng (Spring Boot scheduler, Quartz).
- Airflow/Dagster hoặc hệ thống orchestration ETL.
- `pg_cron` extension nếu được hỗ trợ/cài đặt và được phép sử dụng.
- Job serverless hoặc worker riêng có cấu hình quyền/timeout.

### 19.1. Chọn chu kỳ dựa trên SLA

Ví dụ:

| Nhu cầu nghiệp vụ | Chiến lược tham khảo |
| --- | --- |
| Dashboard báo cáo ngày hôm qua | Refresh hằng ngày sau khi dữ liệu nguồn đã hoàn thiện. |
| Trang quản trị chấp nhận trễ 10–15 phút | Refresh mỗi 5–10 phút nếu duration và độ trễ nguồn cho phép. |
| Tổng hợp hàng triệu rows có query nguồn mất 20 phút | Lịch thưa hơn, tối ưu query hoặc thay cơ chế incremental. |
| Số dư tài chính bắt buộc phản ánh ngay COMMIT | Không dựa một mình vào refresh định kỳ. |

Lịch refresh phải có đủ khoảng **giữa các lần chạy** để job không chồng lên nhau, kể cả lúc duration p95/p99 tăng.

### 19.2. Ví dụ lệnh cho scheduler gọi psql

Một job ngoài PostgreSQL có thể gọi:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -d your_database \
  -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_refresh_lab.daily_revenue;"
```

Đây là câu lệnh **shell** minh họa cho môi trường đã cài psql, cấu hình kết nối và xác thực an toàn. Không hard-code mật khẩu database trong command hoặc log. Tùy hệ điều hành và bộ scheduler, cú pháp shell khác nhau.

Tùy chọn `ON_ERROR_STOP=1` giúp script nhận lỗi SQL theo cách thích hợp để cảnh báo, thay vì coi một lần refresh thất bại là job thành công.

### 19.3. Ví dụ với pg_cron (tùy chọn)

Nếu DBA đã cài và cho phép dùng extension `pg_cron`, cú pháp lịch có thể là:

```sql
-- Chỉ khi pg_cron đã được cài đặt và cấu hình:
-- SELECT cron.schedule(
--     'daily-revenue-refresh-every-10-minutes',
--     '*/10 * * * *',
--     $$
--         REFRESH MATERIALIZED VIEW CONCURRENTLY
--             mv_refresh_lab.daily_revenue;
--     $$
-- );
```

Không chạy `CREATE EXTENSION pg_cron` hoặc giả định extension luôn có trong managed PostgreSQL. Cấu hình `shared_preload_libraries`, quyền và nơi pg_cron lưu job phụ thuộc môi trường triển khai.

### 19.4. Tránh xếp hàng refresh khi job chậm

Nếu job A mất 12 phút nhưng lịch kích hoạt mỗi 5 phút:

```text
10:00  Job A bắt đầu
10:05  Job B đến, có thể đợi
10:10  Job C đến, có thể đợi
10:12  Job A xong, Job B có thể mới bắt đầu
...
```

Vì PostgreSQL chỉ cho một refresh tại một thời điểm trên cùng materialized view, scheduler phải có cơ chế **skip/coalesce/serialize** theo chính sách. Đừng coi các yêu cầu refresh chồng nhau là một cách giữ dữ liệu mới hơn.

### 19.5. Advisory lock ở tầng job

Trong những hệ thống có nhiều worker, có thể dùng **advisory lock** để đảm bảo chỉ một worker quyết định chạy refresh. Ý tưởng:

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(337001)
    AS acquired_job_lock;

-- Chỉ khi acquired_job_lock = TRUE, orchestrator mới gọi:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     mv_refresh_lab.daily_revenue;

COMMIT;
```

Đoạn này chỉ là **mẫu giao thức hai bước**. SQL không tự bỏ qua lệnh REFRESH nếu `acquired_job_lock=FALSE`; job runner phải đọc kết quả và rẽ nhánh đúng. Trong transaction-scoped advisory lock, lock được giữ đến COMMIT/ROLLBACK, nên phải giữ transaction ấy xuyên suốt lần refresh khi cần serialization.

Advisory lock không thay thế lock nội bộ của PostgreSQL trên materialized view; nó giúp **ứng dụng tránh khởi động công việc vô ích** và tích tụ hàng đợi.

### 19.6. Không refresh trực tiếp sau mỗi INSERT

Một trigger gọi REFRESH cho mỗi row mới thường là thiết kế xấu với bảng nhiều writes: mỗi transaction phải trả giá query tổng hợp toàn view hoặc chờ locks, throughput có thể sụt mạnh.

Nếu cần cập nhật tổng hợp theo từng row, hãy xem **aggregate table transactional/trigger delta hoặc asynchronous events**, không dùng REFRESH toàn view sau từng INSERT như một giải pháp mặc định.

## 20. Theo dõi thời điểm refresh thành công

PostgreSQL cung cấp `pg_matviews` để xem trạng thái populated và metadata, nhưng **không có cột built-in đơn giản kiểu `last_refresh_at` trong `pg_matviews`** để thay thế monitoring job.

### 20.1. Tạo bảng metadata vận hành riêng

Ví dụ lab:

```sql
CREATE TABLE mv_refresh_lab.refresh_status (
    view_name text PRIMARY KEY,
    last_started_at timestamptz,
    last_succeeded_at timestamptz,
    last_duration_ms numeric,
    last_status text NOT NULL DEFAULT 'never_run',
    last_error text
);

INSERT INTO mv_refresh_lab.refresh_status (
    view_name, last_status
)
VALUES
    ('mv_refresh_lab.daily_revenue', 'never_run');
```

### 20.2. Ghi metadata từ orchestrator

Một job có thể:

1. Ghi thời điểm bắt đầu và trạng thái running.
2. Thực thi REFRESH.
3. Nếu REFRESH COMMIT thành công, ghi finished time/duration và status success.
4. Nếu lỗi, ghi error ở **transaction riêng còn hoạt động**.

Ví dụ mẫu cập nhật sau thành công (thời điểm và duration do job runner cung cấp):

```sql
UPDATE mv_refresh_lab.refresh_status
SET
    last_started_at = TIMESTAMPTZ '2026-11-14 08:00+00',
    last_succeeded_at = clock_timestamp(),
    last_duration_ms = 3200,
    last_status = 'success',
    last_error = NULL
WHERE view_name = 'mv_refresh_lab.daily_revenue';
```

Giá trị `3200` chỉ là thời gian minh họa; không phải benchmark. Trong hệ thống thực, lấy kết quả đo từ worker/job chứ không chép literal.

### 20.3. Vì sao cần ghi failed trong transaction khác?

Nếu REFRESH thất bại trong transaction rồi rollback toàn bộ, mọi dòng log **nằm cùng transaction lỗi ấy** cũng có thể rollback. Scheduler phải bắt lỗi và tạo một transaction mới để ghi sự kiện thất bại/alert.

### 20.4. Last success không phải data watermark

`last_succeeded_at` cho biết lúc job hoàn thành, nhưng không chứng minh dữ liệu nguồn đã được xử lý đầy đủ tới chính timestamp đó. Nếu ETL có watermark như `max_ingested_at` hoặc LSN, nên lưu thêm thông số đã xác nhận phù hợp contract.

### 20.5. Hiển thị độ mới lên dashboard

```sql
SELECT
    view_name,
    last_succeeded_at,
    clock_timestamp() - last_succeeded_at
        AS elapsed_since_success,
    last_status
FROM mv_refresh_lab.refresh_status
WHERE view_name = 'mv_refresh_lab.daily_revenue';
```

Nếu `last_succeeded_at IS NULL` thì chưa có thành công được ghi vào bảng metadata (hoặc metadata chưa đồng bộ), không phải bằng chứng materialized view chưa từng populated.

## 21. Quan sát materialized view đang chạy

### 21.1. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS elapsed,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Lọc theo database và user/job cụ thể nếu môi trường nhiều queries. Không chỉ dùng `query LIKE '%REFRESH%'` rồi khẳng định đã tìm đầy đủ: query text có thể bị cắt theo cấu hình hoặc lệnh được gọi từ công cụ/hàm khác.

### 21.2. pg_locks trên view

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.pid, l.mode;
```

Bạn có thể thấy lock EXCLUSIVE hoặc ACCESS EXCLUSIVE khi refresh còn đang giữ lock. Nếu query bị chặn, xem cả **blocking PIDs**, **transaction state** và hoạt động khác.

### 21.3. pg_matviews.ispopulated

```sql
SELECT
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
ORDER BY matviewname;
```

`ispopulated=true` nghĩa view có dữ liệu đã nạp ở trạng thái có thể SELECT, **không nghĩa nội dung vừa được refresh xong hoặc đang đồng bộ với nguồn**.

### 21.4. Kích thước view và indexes

```sql
SELECT
    pg_size_pretty(
        pg_relation_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS total_size;
```

Kích thước có thể thay đổi theo mode và lịch sử refresh. Không chỉ đo query duration; cần nhìn storage growth và maintenance cost.

### 21.5. Query rows và statistics

```sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_class AS c
WHERE c.oid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

`reltuples` là **ước lượng**, không phải exact count. Nếu query planner có estimates kém sau biến động lớn, cân nhắc cập nhật statistics theo hướng dẫn phù hợp, ví dụ:

```sql
ANALYZE mv_refresh_lab.daily_revenue;
```

Trên production, cần quyền bảo trì tương ứng và đo tác động. ANALYZE **không làm REFRESH từ bảng nguồn**, chỉ cập nhật thống kê phục vụ planner.

## 22. Tài liệu vận hành cho job refresh

Một job đáng tin cậy phải có các yếu tố:

| Thành phần | Câu hỏi vận hành |
| --- | --- |
| Owner/job role | Role nào có quyền MAINTAIN hoặc ownership phù hợp? |
| Frequency | Bao lâu chạy một lần, và vì sao? |
| Deadline | Lúc nào dashboard bắt buộc có dữ liệu mới? |
| Dependencies | ETL/bảng nguồn đã hoàn tất kỳ dữ liệu nào? |
| Overlap policy | Job mới sẽ skip, chờ hay gom yêu cầu refresh? |
| Timeout | Khi nào hủy câu lệnh bị treo/chậm? |
| Lock budget | Có cho phép block SELECT không? |
| Resource budget | Có đủ CPU, RAM, temp space, WAL, I/O? |
| Observability | Ai nhận thông báo khi refresh fail hoặc duration tăng? |
| Recovery | Khi job lỗi, phục vụ view cũ hay fallback query? |
| Data contract | “Last refreshed at” và watermark được định nghĩa thế nào? |

### 22.1. Mẫu quy trình job

```text
Scheduler kích hoạt
    |
    v
Kiểm tra job trước còn chạy?
    | Có
    +-----> SKIP / COALESCE / ALERT (theo policy)
    |
    | Không
    v
Ghi started_at + kiểm tra dependency/watermark
    |
    v
REFRESH MATERIALIZED VIEW [CONCURRENTLY] ...
    |
    +-----> Lỗi -> rollback -> ghi failed ở transaction mới -> alert
    |
    v
COMMIT thành công
    |
    v
Ghi succeeded_at/duration/watermark + metric
    |
    v
Kiểm tra freshness SLA
```

### 22.2. Không ghi thành công trước khi commit

Nếu scheduler ghi trạng thái “success” ngay khi gửi lệnh REFRESH mà chưa đợi server trả thành công/commit, monitoring có thể báo sai. Thành công phải được xác nhận sau khi command/transaction đã hoàn tất.

### 22.3. Giới hạn lịch chạy theo chi phí lớn nhất

Giả sử lịch mỗi 10 phút và refresh bình thường mất 4 phút, nhưng cuối tháng có thể mất 30 phút. Scheduler cần xử lý p99 durations, không dựa duy nhất vào trung bình. Nếu quá tải, cân nhắc giảm tần suất, tối ưu query định nghĩa hoặc chuyển sang mô hình incremental có kiểm soát.

## 23. Khi nào chọn REFRESH thường?

Không phải ứng dụng nào cũng cần CONCURRENTLY.

### 23.1. Nạp đầu tiên

View vừa tạo `WITH NO DATA` chưa populated, nên refresh đầu tiên phải là chế độ thường `WITH DATA`. Không có con đường hợp lệ để “chạy CONCURRENTLY khi chưa nạp” chỉ bằng cách tạo index.

### 23.2. Báo cáo chạy ngoài giờ

Nếu view chỉ được đọc trong giờ hành chính, batch làm mới lúc 02:00 có thể chấp nhận ACCESS EXCLUSIVE lock và hưởng lợi từ chế độ thường nếu nó dùng ít tài nguyên hoặc hoàn thành nhanh hơn.

### 23.3. Gần như toàn bộ kết quả thay đổi

Khi mỗi lần refresh thay thế gần hết các hàng, việc làm đối chiếu của concurrent refresh có thể không có lợi so với thay thế toàn bộ. Phải benchmark trên kích thước thực.

### 23.4. Không có khóa unique logic phù hợp

Nếu kết quả không có tập cột nào duy nhất theo nghiệp vụ và không thể định nghĩa UNIQUE index hợp lệ, CONCURRENTLY không dùng được. REFRESH thường vẫn có thể hoạt động, nhưng nên xem lại **thiết kế kết quả view** — có thể đang có duplicate rows do JOIN sai hoặc thiếu grouping.

### 23.5. Chấp nhận khóa đọc là quyết định có ý thức

REFRESH thường sẽ phù hợp hơn khi:

- Số users đọc view trong cửa sổ refresh rất thấp.
- Có thông báo maintenance window rõ ràng.
- Workload ưu tiên hoàn thành batch nhanh.
- Chi phí concurrency mode không bù được lợi ích.

Không nên dùng chế độ thường trên một materialized view nằm ở đường đọc của API latency-sensitive mà không đánh giá mức chặn.

## 24. Khi nào chọn CONCURRENTLY?

### 24.1. Dashboard cần khả năng đọc liên tục

Nếu dashboard được đọc mỗi giây trong ngày, REFRESH thường dài vài phút có thể gây timeout. CONCURRENTLY giúp người đọc tiếp tục truy cập bản dữ liệu cũ trong lúc refresh tính toán.

### 24.2. Unique business key ổn định

View tổng hợp `GROUP BY tenant_id, sale_date` có khóa rõ, index đáp ứng điều kiện; đây là ứng viên phù hợp. Với dữ liệu kết quả ít thay đổi giữa các lần refresh, chi phí reconcile có thể hợp lý.

### 24.3. Chấp nhận stale trong thời gian refresh

Người đọc vẫn có thể thấy **kết quả cũ** trước khi concurrent refresh commit. Vì vậy chức năng phải chấp nhận:

- Số liệu chưa phải real-time.
- Thời điểm cập nhật cuối cần được hiển thị hoặc hiểu rõ.
- Khi refresh lỗi, view có thể tiếp tục cũ hơn SLA.

### 24.4. Có ngân sách tài nguyên

Concurrent refresh có thể cần CPU, temp space, WAL và index maintenance không nhỏ. Nếu đang ở peak write traffic, cần tránh chạy job không giới hạn làm chậm các giao dịch chính.

### 24.5. Có cơ chế điều phối

Chỉ một REFRESH trên cùng view tại một thời điểm. Job runner phải quản lý overlap, timeout và trạng thái thành công/thất bại.

## 25. Nếu cần near-real-time hoặc real-time thì làm gì?

Nếu dữ liệu phải cập nhật mỗi giây hoặc cùng transaction, không nên giả định tăng tần suất `REFRESH CONCURRENTLY` đến mỗi 100 ms sẽ giải quyết. Một lần REFRESH vẫn có chi phí query nguồn và reconcile.

### 25.1. Query trực tiếp bảng nguồn

Ưu điểm:

- Đọc trạng thái đã COMMIT theo snapshot SQL.
- Không quản lý cache materialized.
- Phù hợp tập dữ liệu được index tốt và query đủ nhanh.

Nhược:

- Mỗi lần đọc lại phải thực thi filter/JOIN/aggregate.
- Với bảng cực lớn, dashboard rộng có thể rất đắt.

### 25.2. Bảng aggregate transactional

Một bảng tổng hợp được cập nhật trong cùng transaction ghi nguồn:

```text
BEGIN
    INSERT order
    UPDATE daily_totals SET revenue = revenue + delta
COMMIT
```

Cách này có thể cung cấp consistency mạnh nếu xử lý đúng cạnh tranh, sửa/xóa/rollback, ràng buộc và idempotency. Nhưng nó chuyển chi phí tính toán sang write path và cần xử lý những thay đổi trạng thái của giao dịch.

### 25.3. Event-driven projection

Một consumer nhận sự kiện `OrderPaid`, `OrderRefunded` và cập nhật bảng read model:

```text
Orders DB -> Outbox/CDC -> Worker -> Revenue projection
                                   |
                                   v
                            Dashboard SELECT
```

Cách này có thể cập nhật tăng dần, nhưng có độ trễ, retry, duplicate delivery, out-of-order events và nhu cầu reconciliation. Không tự có consistency mạnh với bảng nguồn nếu không thiết kế.

### 25.4. Extensions/hệ thống khác

Một số extensions hoặc database chuyên analytics có cơ chế incremental/continuous aggregates riêng. Đó là **năng lực ngoài lệnh REFRESH MATERIALIZED VIEW chuẩn của PostgreSQL**; không giả định có sẵn trên mọi managed PostgreSQL.

### 25.5. Hai tầng báo cáo

Ví dụ:

- Materialized view tổng hợp dữ liệu lịch sử ổn định đến ngày hôm qua.
- Query trực tiếp bảng nóng chỉ cho ngày hôm nay.
- API hợp nhất kết quả với định nghĩa tránh double count.

Thiết kế này có thể giảm tần suất full refresh và giữ dữ liệu gần hiện tại, nhưng đòi hỏi **watermark/cutoff rõ ràng**, timezone nhất quán và xử lý late-arriving events. Không cộng hai nguồn mà không đảm bảo hai tập dữ liệu không chồng nhau.

## 26. Những lỗi thường gặp khi dùng CONCURRENTLY

### 26.1. Lỗi “cannot refresh ... concurrently”

Nguyên nhân thường thấy: view chưa populated hoặc không có unique index hợp lệ. Quy trình:

1. Kiểm tra `pg_matviews.ispopulated`.
2. Nếu false, chạy `REFRESH MATERIALIZED VIEW ... WITH DATA`.
3. Kiểm tra các index trên view bằng `pg_indexes` và `pg_index`.
4. Đảm bảo ít nhất một UNIQUE index dùng **tên cột** và không có `WHERE`.
5. Kiểm tra index valid và dữ liệu đáp ứng uniqueness.
6. Thử lại khi có quyền và tài nguyên phù hợp.

Không sửa bằng cách tạo index non-unique rồi chạy lại vô hạn.

### 26.2. Lỗi duplicate key khi CREATE UNIQUE INDEX

Nếu query tạo nhiều rows với cùng key:

```sql
-- Materialized view giả định có:
-- tenant_id | sale_date   | revenue
-- 1         | 2026-11-01  | 100
-- 1         | 2026-11-01  |  50
```

`CREATE UNIQUE INDEX ... (tenant_id,sale_date)` thất bại vì có duplicate key. Cần xác định vì sao view chứa hai rows cho một cặp nếu business muốn một hàng tổng hợp.

Kiểm tra trên view hiện đã populated:

```sql
SELECT
    tenant_id,
    sale_date,
    COUNT(*) AS rows_per_key
FROM mv_refresh_lab.daily_revenue
GROUP BY tenant_id, sale_date
HAVING COUNT(*) > 1;
```

Lab chuẩn không có duplicates; đây là query chẩn đoán có thể áp dụng cho một view có khóa ghép tương ứng.

### 26.3. UNIQUE index trên cột không phải khóa nhóm

Ví dụ `UNIQUE(tenant_id)` trên daily_revenue sẽ thất bại khi một tenant có doanh thu ở nhiều ngày. Thực tế không phải “thiếu DISTINCT” mà là **tenant_id không đủ định danh một hàng của view**.

### 26.4. Tạo index expression/partial rồi vẫn lỗi

Nếu chỉ có:

```sql
-- Không eligible:
-- CREATE UNIQUE INDEX ux_expression
-- ON my_matview ((lower(name)));
-- CREATE UNIQUE INDEX ux_partial
-- ON my_matview (tenant_id, sale_date) WHERE active;
```

thì `REFRESH CONCURRENTLY` vẫn không được cho phép. Index có thể phục vụ các truy vấn khác, nhưng không thỏa điều kiện lock-free readers refresh.

### 26.5. REFRESH chạy quá lâu

Tập trung phân tích:

- Query định nghĩa có SELECT/JOIN/GROUP BY tốn kém không?
- Số rows/bytes view kết quả là bao nhiêu?
- Có lượng thay đổi rất lớn giữa hai phiên bản không?
- Temp disk/WAL/I/O có bão hòa không?
- Có lock wait hay worker đang xếp hàng không?
- Có nhiều indexes trên view cần duy trì không?
- Có transaction dài giữ snapshot/versions không?

Đừng chỉ tăng `work_mem` toàn server mà không đo đúng root cause.

### 26.6. Dashboard bị timeout dù dùng CONCURRENTLY

Xem:

- Dashboard query có đọc trực tiếp **bảng nguồn** chứ không chỉ materialized view?
- SELECT có bị chặn bởi DDL khác hoặc lock ACCESS EXCLUSIVE?
- Server có bị CPU/I/O saturation do REFRESH?
- Query SELECT có cần index/stats tốt hơn?
- Có transaction/client timeout quá ngắn?

CONCURRENTLY chủ yếu giải quyết **lock giữa refresh và SELECT trên view**, không đảm bảo latency mọi request trong mọi điều kiện.

### 26.7. REFRESH thành công nhưng dashboard sai tổng

Khả năng:

- Snapshot refresh trước khi một batch nguồn COMMIT.
- View định nghĩa lọc status/date khác ý nghĩa dashboard.
- Query nguồn có JOIN nhân bản rows.
- ETL có late-arriving data.
- Dashboard tổng hợp nhiều views ở các thời điểm khác nhau.
- Dashboard SELECT không có ORDER BY ổn định hoặc GROUP BY thiếu key.

Phải đối chiếu định nghĩa và snapshot/watermark trước khi kết luận PostgreSQL đã “làm mới thiếu”.

## 27. Runbook xử lý sự cố REFRESH trong production

Một quy trình điều tra có thể áp dụng mà không phá trạng thái hiện hành:

### Bước 1. Xác định triệu chứng

Phân biệt:

- REFRESH báo lỗi SQL.
- Refresh đang chạy lâu.
- Reader bị chặn.
- Reader chậm nhưng không bị chặn.
- Dữ liệu stale.
- Kết quả tổng hợp sai nghiệp vụ.

Mỗi triệu chứng có nguyên nhân và cách khắc phục khác nhau.

### Bước 2. Xem trạng thái view

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab';
```

Nếu unscannable, cần chạy REFRESH thường WITH DATA sau khi xác nhận nguồn/trạng thái phù hợp.

### Bước 3. Xác nhận UNIQUE index

```sql
SELECT
    idx.relname,
    i.indisunique,
    i.indisvalid,
    i.indexprs IS NULL AS no_expressions,
    i.indpred IS NULL AS no_predicate,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

Index phải ở **chính view**, không partial/expression và UNIQUE.

### Bước 4. Xem PIDs/locks

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS elapsed
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Kết hợp `pg_locks` hoặc `pg_blocking_pids(pid)` để xem có lock contention không. Không hủy backend khi chưa biết side effects.

### Bước 5. Đánh giá nguồn và query

Chạy `EXPLAIN (ANALYZE, BUFFERS)` cho SELECT định nghĩa trong môi trường cho phép. Đọc estimated vs actual rows, sort/hash spills, buffers và indexes của nguồn. Với dataset lớn, câu EXPLAIN ANALYZE vẫn thực thi SELECT nên phải chọn thời điểm phù hợp.

### Bước 6. Đối chiếu freshness

Đọc last successful refresh, duration và watermark do job runner lưu. Nếu metadata không tồn tại hoặc không tin cậy, nói rõ không có bằng chứng timestamp chính xác, không suy đoán từ `pg_matviews.ispopulated`.

### Bước 7. Chọn biện pháp

| Nguyên nhân | Hướng xử lý |
| --- | --- |
| View chưa populated | REFRESH thường WITH DATA. |
| Thiếu UNIQUE index | Thiết kế đúng khóa và CREATE UNIQUE INDEX đủ điều kiện. |
| Query nguồn rất nặng | Tối ưu query/index/stats hoặc thay mô hình aggregate. |
| Reader bị chặn bởi REFRESH thường | Xem CONCURRENTLY nếu đủ điều kiện; hoặc đổi cửa sổ chạy. |
| Bị chặn do DDL khác | Điều phối locks/DDL, không coi CONCURRENTLY chữa mọi thứ. |
| Scheduler chạy chồng | Skip/coalesce/serialize jobs. |
| Stale vì ETL đến trễ | Định nghĩa dependency và watermark; đổi thời điểm refresh. |
| Duplicate rows khi tạo UNIQUE | Sửa khóa nghiệp vụ hoặc logic tổng hợp/JOIN. |
| Không đủ permission | Cấp MAINTAIN đúng phiên bản hoặc ownership phù hợp. |

### Bước 8. Sau khi khắc phục

Theo dõi duration của những lần refresh sau, tần suất lỗi, lượng WAL/temp, reader latency và độ mới số liệu. Ghi lại một phương án rollback nếu thay index/schedule/định nghĩa báo cáo.

## 28. An toàn khi tạo UNIQUE index trên view lớn

View hiện có hàng trăm triệu rows; tạo UNIQUE index trực tiếp có thể tốn thời gian và locks. PostgreSQL có tùy chọn:

```sql
-- Ví dụ khi materialized view đã populated:
-- CREATE UNIQUE INDEX CONCURRENTLY ux_daily_revenue_tenant_day
-- ON mv_refresh_lab.daily_revenue (tenant_id, sale_date);
```

**`CREATE UNIQUE INDEX CONCURRENTLY` và `REFRESH MATERIALIZED VIEW CONCURRENTLY` là hai lệnh khác nhau.**

### 28.1. Ý nghĩa của từng CONCURRENTLY

| Lệnh | Mục tiêu |
| --- | --- |
| `CREATE UNIQUE INDEX CONCURRENTLY ...` | Xây index với chiến lược giảm chặn thao tác truy cập phù hợp trên relation khi điều kiện cho phép. |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY ...` | Thay kết quả đã lưu mà vẫn cho phép SELECT thông thường đọc materialized view. |

### 28.2. Tạo index concurrently có giới hạn transaction

`CREATE INDEX CONCURRENTLY` không được chạy trong transaction block tường minh và có quy tắc vận hành/khôi phục riêng nếu việc build bị gián đoạn. Không đặt hai lệnh này trong một khối `BEGIN ... COMMIT` rồi giả định cú pháp hợp lệ.

### 28.3. Có thể có invalid index sau lỗi build

Khi một concurrent index build thất bại/được hủy, index object chưa valid có thể vẫn còn và cần xử lý đúng theo catalog/DBA. Không chỉ thấy tên index trong `pg_indexes` rồi mặc định refresh đồng thời đã có index eligible.

### 28.4. Tạo index cũng cần uniqueness thật

Không có cách chọn `CONCURRENTLY` cho CREATE UNIQUE INDEX để bỏ qua duplicate keys. Nếu dữ liệu trong view không unique theo khóa được chọn, build vẫn phải thất bại.

### 28.5. Phối hợp thời điểm CREATE INDEX và REFRESH

Trên view lớn:

1. Chọn khóa logic từ query định nghĩa.
2. Kiểm tra duplicates và NULL semantics.
3. Lập kế hoạch tạo index với lock/duration có thể chấp nhận.
4. Xác nhận index valid/full/column-only.
5. Chạy REFRESH CONCURRENTLY trong maintenance window thử nghiệm.
6. Đo reader latency, refresh duration và rollback plan.

## 29. Case study 1: Dashboard có người đọc liên tục

**Bối cảnh**

- API lấy số liệu doanh thu qua materialized view.
- 300 request SELECT mỗi giây trong giờ cao điểm.
- REFRESH mất khoảng 90 giây.
- Business chấp nhận dữ liệu trễ tối đa 10 phút.
- Kết quả view có một dòng duy nhất trên cặp (tenant_id, sale_date).

### 29.1. Chọn chế độ

`REFRESH MATERIALIZED VIEW CONCURRENTLY` là ứng viên mạnh vì reader cần tiếp tục được phục vụ trong 90 giây. Tạo UNIQUE index đúng khóa tổng hợp:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
    (tenant_id, sale_date);
```

Trong lab index này đã tạo; ví dụ chỉ nhắc lại thiết kế, không chạy lần thứ hai nếu index cùng tên đã tồn tại.

### 29.2. Những điểm phải kiểm soát

- Cứ bao lâu REFRESH một lần để trễ không vượt SLA, kể cả lúc job chạy 90 giây?
- View đã populated chưa?
- Reader SELECT có index phù hợp không?
- Job có chạy trùng không?
- Có đủ temp space/WAL khi refresh peak traffic không?
- Dashboard có hiển thị last success/watermark không?

### 29.3. Kết luận

CONCURRENTLY giúp tránh chặn SELECT thông thường trên materialized view, nhưng không bảo đảm reader luôn latency thấp khi server bị bão hòa tài nguyên. Cần load test concurrent SELECT với chính job REFRESH.

## 30. Case study 2: Báo cáo tổng hợp ban đêm

**Bối cảnh**

- Hệ thống ETL nhập dữ liệu đã chốt sau 01:00.
- Báo cáo chỉ được người dùng truy cập từ 08:00.
- Mỗi đêm 80% kết quả tổng hợp thay đổi.
- Refresh thông thường mất 8 phút, concurrently trong thử nghiệm mất 13 phút.

### 30.1. Chọn chế độ

`REFRESH MATERIALIZED VIEW` thông thường có thể phù hợp hơn vì:

- Không có reader trong cửa sổ batch.
- Không cần trả overhead reconcile cho mục tiêu tránh chặn người đọc.
- Thời gian và chi phí tài nguyên được đo thấp hơn trong tình huống giả định.

### 30.2. Không refresh trước khi ETL hoàn tất

Nếu scheduler chạy 01:10 nhưng ETL chỉ COMMIT xong 01:20, báo cáo vẫn thiếu dữ liệu. Cần dependency rõ:

```text
ETL source completed
          |
          v
Source validation/watermark
          |
          v
REFRESH MATERIALIZED VIEW
          |
          v
Success + report publish
```

### 30.3. Kết luận

**Không bắt buộc dùng CONCURRENTLY chỉ vì PostgreSQL hỗ trợ.** Mục tiêu là đạt SLA đọc/dữ liệu mới với chi phí thấp nhất có thể chấp nhận, dựa trên benchmark.

## 31. Case study 3: Materialized view chưa nạp lần nào

**Bối cảnh**

- Schema migration tạo materialized view bằng `WITH NO DATA`.
- Một UNIQUE index đã được tạo hoặc đang dự kiến tạo.
- Deployment job ngay lập tức gọi `REFRESH ... CONCURRENTLY`.

### 31.1. Triệu chứng

Lệnh concurrent refresh bị từ chối do view **chưa populated**. Việc tồn tại index không giải quyết được điều kiện thứ nhất.

### 31.2. Quy trình bootstrap

```text
1. CREATE MATERIALIZED VIEW ... WITH NO DATA
2. REFRESH MATERIALIZED VIEW ... WITH DATA
3. CREATE UNIQUE INDEX ... (key columns; no WHERE)
4. REFRESH MATERIALIZED VIEW CONCURRENTLY ... (về sau)
```

Nếu view đã được tạo `WITH DATA`, có thể bỏ bước refresh đầu, tạo index và chuyển sang concurrent refresh ở những lần sau.

### 31.3. Tập kết quả rỗng vẫn hợp lệ

Nếu tại lần nạp đầu không có dữ liệu nguồn, `WITH DATA` có thể tạo view có **0 rows** và `ispopulated=true`. Đừng viết một bootstrap check chỉ hỏi `SELECT COUNT(*) > 0` để suy ra điều kiện CONCURRENTLY.

## 32. Case study 4: Không có UNIQUE key phù hợp

**Bối cảnh**

Một view lưu từng bản ghi giao dịch nhưng output lại bỏ `transaction_id`:

```sql
-- Ví dụ vấn đề về thiết kế kết quả:
-- SELECT tenant_id, sale_date, amount
-- FROM sales;
```

Hai đơn hàng của cùng tenant, cùng ngày và cùng amount có thể trở thành **hai rows giống nhau** trong view. Không thể tạo UNIQUE index trên ba cột đó nếu thực sự có trùng lặp.

### 32.1. Đừng thêm DISTINCT một cách phản xạ

Nếu `SELECT DISTINCT tenant_id,sale_date,amount`, hai giao dịch thật giống nhau sẽ bị gộp thành một row — có thể **làm mất dữ liệu nghiệp vụ**.

### 32.2. Hướng sửa đúng

- Nếu cần từng giao dịch: đưa `transaction_id` duy nhất vào output, tạo UNIQUE index theo ID.
- Nếu cần tổng hợp theo tenant/ngày: `GROUP BY tenant_id,sale_date` và tính COUNT/SUM phù hợp.
- Nếu dữ liệu nguồn có duplicate không hợp lệ: sửa nguyên nhân ở nguồn và constraints.
- Nếu không có khóa ổn định thích hợp: cân nhắc REFRESH thường và chấp nhận maintenance window, hoặc thiết kế lại representation.

### 32.3. Kết luận

Yêu cầu UNIQUE index của CONCURRENTLY là **một yêu cầu dữ liệu có ý nghĩa**, không phải một mẹo DDL. Chọn khóa sai có thể làm view không tạo index được hoặc khiến logic dữ liệu không đúng.

## 33. Case study 5: Hệ thống cần số dư mới ngay sau thanh toán

**Bối cảnh**

Người dùng thanh toán xong phải nhìn thấy số dư mới ngay. Materialized view số dư được REFRESH mỗi phút.

### 33.1. Vấn đề

Một phút có thể là quá lâu với số dư liên quan quyền mua/rút tiền. Ngay cả REFRESH CONCURRENTLY mỗi giây cũng không đảm bảo snapshot có mọi commit vừa xảy ra.

### 33.2. Kiến trúc phù hợp hơn

Đọc trực tiếp dữ liệu transactional, bảng tổng hợp duy trì trong cùng transaction hoặc ledger/read model có đảm bảo consistency theo yêu cầu. Materialized view định kỳ có thể phục vụ **báo cáo phân tích**, không nên là nguồn quyết định giao dịch thời gian thực nếu hợp đồng đòi read-your-writes mạnh.

### 33.3. Kết luận

CONCURRENTLY không biến eventual freshness thành strong consistency. Phân biệt **không chặn người đọc** với **người đọc thấy giao dịch mới nhất**.

## 34. Case study 6: Nhiều materialized views phụ thuộc nhau

**Bối cảnh**

Có ba lớp:

```text
sales table
    |
    v
mv_sales_by_day
    |
    v
mv_sales_by_month
    |
    v
dashboard
```

Nếu `mv_sales_by_month` được refresh trước `mv_sales_by_day`, monthly view có thể tiếp tục dùng bản daily cũ dù bảng sales đã có thay đổi.

### 34.1. Scheduler phải có thứ tự phụ thuộc

```text
Source ingestion complete
          |
          v
REFRESH mv_sales_by_day
          |
          v
Confirm success/watermark
          |
          v
REFRESH mv_sales_by_month
          |
          v
Publish dashboard freshness
```

### 34.2. CONCURRENTLY không giải quyết dependency

Mỗi lệnh CONCURRENTLY cho phép SELECT trên view đó, nhưng không ép refresh ở lớp sau phải đợi lớp trước trừ khi scheduler lập DAG đúng.

### 34.3. Consistency xuyên nhiều view

Ngay cả khi refresh theo đúng thứ tự, dashboard đọc hai view ở hai thời điểm khác nhau có thể thấy version khác nhau nếu job đang chạy. Nếu cần snapshot chung, phải thiết kế publish boundary/version protocol và các giao dịch phù hợp.

## 35. Case study 7: Source có dữ liệu đến trễ

**Bối cảnh**

- Materialized view `revenue_by_day` tổng hợp theo ngày thanh toán.
- Payment gateway gửi một số giao dịch của tuần trước vào hôm nay.
- View được refresh hằng đêm.

### 35.1. Điều gì xảy ra?

Khi giao dịch đến muộn được COMMIT trước snapshot refresh, lần refresh sau có thể **thay đổi doanh thu của ngày quá khứ**, không chỉ ngày hiện tại. Một lệnh REFRESH tiêu chuẩn tính lại tập kết quả theo query, vì vậy dữ liệu lịch sử trong materialized view có thể bị chỉnh lại.

### 35.2. Tại sao cần xem query định nghĩa?

Nếu query cố định `WHERE sale_date = CURRENT_DATE`, view chỉ giữ ngày hiện tại; giao dịch đến muộn của tuần trước sẽ không nằm trong kết quả, bất kể refresh bao nhiêu lần. Nếu định nghĩa dùng khoảng lịch sử cho phép backfill, dữ liệu đến muộn có thể được tính.

### 35.3. Watermark và policy

Ứng dụng cần:

- Định nghĩa late-arrival window.
- Nêu các kỳ đã được chốt/finalized hay còn được sửa.
- Theo dõi source ingestion status.
- Quy định refresh lịch sử sau corrections.

CONCURRENTLY không quyết định chính sách những kỳ nào được thay đổi.

## 36. Một số anti-pattern trong thiết kế materialized view

### 36.1. Dùng random() làm khóa duy nhất

```sql
-- Thiết kế sai nếu làm identity qua refresh:
-- SELECT random() AS synthetic_id, ... FROM sales;
```

Giá trị ngẫu nhiên thay đổi mỗi lần query định nghĩa chạy. Nó không phải định danh ổn định; còn có nguy cơ va chạm và không phản ánh business key.

### 36.2. Dùng row_number() mà không hiểu dữ liệu biến động

`row_number() OVER (ORDER BY amount DESC)` có thể đổi giá trị khi thêm một đơn có amount lớn, làm hàng loạt IDs dịch chuyển giữa các lần REFRESH. Nếu downstream dùng row number như business ID thì dữ liệu sai về mặt quan hệ.

### 36.3. Refresh toàn view sau mỗi row write

Đây là vòng lặp tốn chi phí và có thể gây contention. Dữ liệu thay đổi liên tục yêu cầu maintenance tốt hơn việc thực thi full aggregate cho mọi INSERT.

### 36.4. Bật CONCURRENTLY nhưng bỏ qua UNIQUE index design

Nếu query định nghĩa chứa duplicate rows, tạo arbitrary index chỉ để “đủ điều kiện” có thể sai dữ liệu. Hãy xác định khóa thật hoặc thay schema.

### 36.5. Lịch refresh nhanh hơn thời gian chạy

Nguyên nhân gây hàng đợi job, stale data không giảm và lock contention. Cần cơ chế skip/coalesce và đo duration.

### 36.6. Tin rằng ORDER BY trong CREATE MV là đủ

REFRESH không bảo đảm thứ tự vật lý/kết quả. Mọi client cần ORDER BY khi yêu cầu sort.

### 36.7. Xem ispopulated là chỉ báo dữ liệu mới

`ispopulated=true` chỉ có nghĩa view đã có tập dữ liệu scannable, có thể đã stale rất lâu.

### 36.8. Log thành công trước khi COMMIT

Nếu REFRESH cuối cùng bị rollback, job metadata vẫn ghi success sẽ đánh lừa dashboard. Phải phân biệt started, finished, committed success và nguồn watermark.

### 36.9. Dùng REFRESH WITH NO DATA như cách “clear report tạm thời”

Hành vi là **unscannable**; SELECT có thể lỗi. Nếu muốn hiển thị không dữ liệu hợp lệ, thiết kế response/feature flag/empty report khác.

### 36.10. Không phân biệt CREATE INDEX CONCURRENTLY và REFRESH CONCURRENTLY

Hai lệnh có tác dụng, khóa và giới hạn transaction khác nhau. Từ CONCURRENTLY trong tên không làm chúng tương đương.

### 36.11. Bỏ qua security

Materialized view lưu bản sao dữ liệu thật. Cấp SELECT rộng cho view có thể làm lộ số liệu nhạy cảm ngay cả khi các bảng nguồn bị hạn chế. Phải xem lại grant, schema USAGE, ownership, RLS và các chính sách xuất báo cáo.

### 36.12. Tự tin rằng refresh không gây WAL hoặc replication lag

Với dữ liệu lớn, việc thay dữ liệu vật hóa vẫn có thể sinh WAL/disk activity và ảnh hưởng replica. Phải giám sát I/O và replication theo workload.

## 37. Tích hợp job REFRESH vào Java/JDBC

Với hệ thống Java Spring Boot hoặc một service thuần JDBC, cách đơn giản nhất là **để scheduler/job worker** gọi SQL REFRESH bằng tài khoản có quyền phù hợp. Tránh để request web của từng người dùng tự REFRESH trước khi đọc dashboard.

### 37.1. Ví dụ JDBC với DataSource

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class MaterializedViewRefresher {
    private final DataSource dataSource;

    public MaterializedViewRefresher(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void refreshDailyRevenue() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(true);

            try (Statement statement = connection.createStatement()) {
                // Giới hạn thời gian chạy theo JDBC driver;
                // không thay thế monitoring/timeout ở DB.
                statement.setQueryTimeout(300);

                statement.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY " +
                    "mv_refresh_lab.daily_revenue"
                );
            }
        }
    }
}
```

Điều kiện trước khi đoạn code này hoạt động:

1. Materialized view đã được tạo và `WITH DATA`/populated.
2. View có UNIQUE index đúng yêu cầu.
3. Tài khoản JDBC có `MAINTAIN` trên PostgreSQL 17+ hoặc quyền ownership phù hợp với major cũ.
4. Scheduler có cơ chế chống overlap và xử lý lỗi.
5. Query timeout và job timeout được tính phù hợp.

### 37.2. Không coi setQueryTimeout là kill switch tuyệt đối

`setQueryTimeout(300)` yêu cầu JDBC driver giới hạn thời gian câu SQL theo cơ chế được hỗ trợ. Việc cancel có thể có độ trễ hoặc liên quan trạng thái network/server; cần thêm monitoring và timeout vận hành thích hợp như `statement_timeout` khi môi trường cho phép.

### 37.3. Không đặt REFRESH vào request GET

Thiết kế không tốt:

```text
GET /dashboard
     |
     v
REFRESH MATERIALIZED VIEW CONCURRENTLY
     |
     v
SELECT report
```

Với 100 request đồng thời, bạn đang cố yêu cầu 100 refresh của cùng một view — PostgreSQL vẫn chỉ cho một refresh tại một thời điểm và các requests có thể phải đợi, gây timeout.

Thiết kế tốt hơn:

```text
Scheduler/job worker -> REFRESH theo lịch/trigger hợp lý

GET /dashboard       -> SELECT từ materialized view
                        + hiển thị last_success/watermark
```

### 37.4. Transaction context trong framework

Không vô tình đặt REFRESH vào một transaction ứng dụng dài cùng hàng loạt DB writes và gọi API ngoài. Locks có thể được giữ đến cuối transaction và làm tăng khả năng contention.

Nếu job cần ghi metadata, nên tách **start/failure logging** và **success after commit** rõ ràng, không coi exception trong transaction đã abort là có thể tiếp tục ghi log bằng cùng transaction.

### 37.5. Bảo mật thông tin kết nối

Sử dụng connection pool và secret manager/environment được bảo vệ theo chính sách, không hard-code password/connection string vào source code hoặc log. Quyền SELECT của API reader không cần đồng nhất với quyền MAINTAIN của job worker.

## 38. Bài tập thực hành

Các bài sau có thể dùng bộ dữ liệu `mv_refresh_lab` của phần 8. Câu hỏi về lock với hai sessions chỉ thực hành trong database riêng; đừng giữ transactions ngủ lâu trên production. Khi đề hỏi kết quả cụ thể, giả định dữ liệu theo đúng thứ tự bài lab; nếu đã chạy thêm các lệnh demo khác, kết quả có thể khác.

### Bài 1. Phân biệt ba loại đối tượng

VIEW thường khác MATERIALIZED VIEW và bảng tổng hợp tự duy trì ở điểm nào? Đối tượng nào tự lưu kết quả SELECT trong PostgreSQL?

### Bài 2. Vì sao dữ liệu stale?

Một materialized view được REFRESH lúc 08:00. Đến 08:10 có 2.000 rows mới COMMIT vào bảng nguồn. Đến 08:12 không có REFRESH thêm. Query materialized view có bắt buộc phản ánh 2.000 rows mới không?

### Bài 3. Cú pháp

Viết lệnh refresh thông thường cho `mv_refresh_lab.daily_revenue` và lệnh có `CONCURRENTLY`.

### Bài 4. WITH DATA

`REFRESH MATERIALIZED VIEW v` có khác `REFRESH MATERIALIZED VIEW v WITH DATA` về mặc định nạp dữ liệu không?

### Bài 5. WITH NO DATA

Sau `REFRESH MATERIALIZED VIEW v WITH NO DATA`, SELECT trên v có trả 0 rows hợp lệ không? Tại sao?

### Bài 6. CONCURRENTLY + NO DATA

Lệnh `REFRESH MATERIALIZED VIEW CONCURRENTLY v WITH NO DATA` có hợp lệ không?

### Bài 7. Populated vs row count

Một materialized view được tạo `WITH NO DATA` rồi chạy `REFRESH ... WITH DATA` nhưng query nguồn trả 0 rows. Có đủ điều kiện populated cho lần concurrent refresh sau không?

### Bài 8. Yêu cầu index

Nêu bốn thuộc tính của UNIQUE index phù hợp cho `REFRESH ... CONCURRENTLY`.

### Bài 9. Unique index ở bảng nguồn

Nguồn `sales` có PRIMARY KEY(sale_id). Vì sao đây **chưa đủ** để REFRESH CONCURRENTLY `daily_revenue`?

### Bài 10. Composite unique key

View tổng hợp mỗi tenant mỗi ngày một dòng. Tại sao `UNIQUE(tenant_id)` không phù hợp? Viết index đúng.

### Bài 11. Expression index

`UNIQUE INDEX ON mv ((lower(email)))` có đủ điều kiện CONCURRENTLY không? Tại sao?

### Bài 12. Partial index

`UNIQUE INDEX ON mv (tenant_id, sale_date) WHERE active` có đủ không? Tại sao?

### Bài 13. Index không unique

Chỉ có `CREATE INDEX ON mv (tenant_id,sale_date)`. Chế độ CONCURRENTLY có thể dựa riêng vào index ấy không?

### Bài 14. Quy trình bootstrap

Viết thứ tự từ `CREATE MATERIALIZED VIEW ... WITH NO DATA` tới lần `REFRESH CONCURRENTLY` đầu tiên.

### Bài 15. Doanh thu trước/sau refresh

Lab ban đầu có tenant 1 ngày 01/11 với paid amounts 100 và 50; sau đó thêm paid 25. Trước refresh, view báo bao nhiêu? Sau refresh báo bao nhiêu?

### Bài 16. Nhóm mới xuất hiện

Ban đầu tenant 2 ngày 02/11 chỉ có order pending 30. Sau khi thêm paid 110 và refresh, dòng nào xuất hiện trong daily_revenue?

### Bài 17. Đổi pending thành paid

Trong lab đã có paid 110 và pending 30 cho tenant 2 ngày 02/11. Sau khi UPDATE 30 thành paid và REFRESH CONCURRENTLY, revenue và paid_orders là bao nhiêu?

### Bài 18. Xóa hết các hàng thuộc một nhóm

Nếu tất cả rows paid của tenant 1 ngày 02/11 đổi sang cancelled, query `GROUP BY` chỉ lọc paid còn trả nhóm đó không? Sau refresh view sẽ thế nào?

### Bài 19. ACCESS EXCLUSIVE

Vì sao REFRESH thường có thể chặn SELECT trên materialized view? Tên lock mode là gì?

### Bài 20. EXCLUSIVE

REFRESH CONCURRENTLY sử dụng lock mode nào trên materialized view? SELECT thường dùng lock gì và có tương thích không?

### Bài 21. Transaction dài

Session A chạy REFRESH thường trong BEGIN rồi ngủ 5 phút trước COMMIT. Tại sao Session B có thể đợi SELECT dù phần tính REFRESH đã xong?

### Bài 22. Giữa refresh thì người đọc thấy gì?

Session A đang REFRESH CONCURRENTLY và chưa commit. Session B chạy SELECT. Có đọc được dữ liệu mới chưa commit không? Điều gì có thể xảy ra khi snapshot cũ còn tồn tại?

### Bài 23. Freshness

Refresh bắt đầu 10:00, nguồn có transaction commit 10:01, refresh kết thúc 10:03. Có thể khẳng định view chứa transaction commit 10:01 không?

### Bài 24. ORDER BY

Một materialized view có `ORDER BY amount DESC` trong query định nghĩa. Sau REFRESH, ứng dụng có thể SELECT không ORDER BY mà cam kết thứ tự giảm không?

### Bài 25. Chỉ một REFRESH

Scheduler kích hoạt 09:00, 09:05, 09:10 nhưng REFRESH mất 20 phút. `CONCURRENTLY` có cho ba REFRESH cùng view chạy song song không? Đề xuất policy.

### Bài 26. Lịch chạy

Dashboard cần độ trễ tối đa 10 phút, job REFRESH có p99 duration 8 phút. Có nên cứ 1 phút gọi REFRESH mới một lần không? Những đại lượng nào cần tính?

### Bài 27. pg_matviews

Viết query đọc trạng thái `ispopulated` và `hasindexes` của `mv_refresh_lab.daily_revenue`. Có cột built-in `last_refresh_at` ở view này không?

### Bài 28. Kiểm tra index

Viết SQL đọc `pg_indexes` hoặc `pg_index` để xác nhận UNIQUE index và không có WHERE/expression.

### Bài 29. Khóa và blocking

Viết query quan sát `pg_locks` cho materialized view và nêu một cách xác định blocker PIDs trong PostgreSQL.

### Bài 30. Quyền bảo trì

PostgreSQL 17+ cho phép refresh dựa trên quyền nào? Trong PostgreSQL 16, điểm khác biệt chính là gì?

### Bài 31. Dữ liệu thật vs cache

Một API buộc phải hiển thị số dư cập nhật ngay sau COMMIT. Vì sao REFRESH CONCURRENTLY theo lịch không đảm bảo yêu cầu đó? Kể hai lựa chọn kiến trúc khác.

### Bài 32. EXPLAIN

`EXPLAIN (ANALYZE, BUFFERS)` trên query định nghĩa giúp biết điều gì? Tại sao vẫn cần đo thời gian REFRESH riêng?

### Bài 33. Materialized view chain

`mv_month` phụ thuộc `mv_day`, `mv_day` phụ thuộc `sales`. Scheduler nên refresh theo thứ tự nào và vì sao?

### Bài 34. Unique identity

Nếu view lấy mỗi giao dịch nhưng bỏ transaction_id, hai giao dịch giống ngày/tenant/amount có thể trùng hoàn toàn. Có nên thêm `DISTINCT` để lấy một UNIQUE index theo ba cột ấy không? Giải thích rủi ro.

### Bài 35. Error recovery

REFRESH CONCURRENTLY lỗi do unique index invalid. Job nên retry liên tục mỗi giây hay phân loại lỗi rồi cảnh báo? Vì sao?

### Bài 36. REFRESH WITH NO DATA

Một view đang được dashboard dùng; admin chạy `REFRESH ... WITH NO DATA`. Hậu quả đối với SELECT là gì, và làm thế nào đưa view về trạng thái scannable?

### Bài 37. CREATE INDEX CONCURRENTLY

Phân biệt `CREATE UNIQUE INDEX CONCURRENTLY` với `REFRESH MATERIALIZED VIEW CONCURRENTLY`. Lệnh nào không được chạy trong transaction block tường minh?

### Bài 38. Nhật ký refresh

Thiết kế tối thiểu bảng hoặc log chứa các trường để biết last success, duration, error và watermark nguồn. Vì sao timestamp kết thúc refresh không phải chứng cứ dữ liệu nguồn đã được xử lý đến chính timestamp ấy?

### Bài 39. JDBC

Vì sao nên để job worker gọi REFRESH thay vì gọi trong mỗi HTTP GET dashboard? Nêu các quyền và timeout cần kiểm soát.

### Bài 40. Đề xuất thiết kế

Một hệ thống có dashboard đọc liên tục, chấp nhận trễ 15 phút, mỗi REFRESH 4 phút, materialized view có khóa nhóm ổn định, 1% rows thay đổi mỗi lần. Chế độ nào đáng thử trước và phải đo thêm những chỉ số gì?

## 39. Gợi ý lời giải

### Đáp án 1. VIEW, MATERIALIZED VIEW, aggregate table

VIEW thường là định nghĩa truy vấn được đánh giá khi đọc, không giữ bản sao kết quả độc lập. MATERIALIZED VIEW lưu kết quả vật lý và cần REFRESH để cập nhật. Aggregate table do ứng dụng/trigger/event worker duy trì có logic đồng bộ riêng; nó có thể cập nhật delta, không phải mặc định của REFRESH.

### Đáp án 2. Stale data

Không. Materialized view vẫn phản ánh tập dữ liệu đã vật hóa tại lần refresh 08:00. Rows commit 08:10 chưa tự xuất hiện; phải chạy REFRESH thành công và bảo đảm snapshot thích hợp để đưa chúng vào kết quả mới.

### Đáp án 3. Cú pháp

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;
```

Lệnh thứ hai chỉ hợp lệ khi view đã populated và có UNIQUE index đủ điều kiện.

### Đáp án 4. WITH DATA

Không khác về mặt default: `REFRESH MATERIALIZED VIEW v` ngầm định `WITH DATA`. Cả hai thực thi query định nghĩa để cập nhật dữ liệu vật hóa và để view ở trạng thái scannable.

### Đáp án 5. WITH NO DATA

Không. `WITH NO DATA` để view ở trạng thái **unscannable**. SELECT dữ liệu từ view có thể báo lỗi; nó không tương đương một result set 0 rows hợp lệ.

### Đáp án 6. CONCURRENTLY cùng NO DATA

Không hợp lệ. PostgreSQL cấm kết hợp hai tùy chọn. CONCURRENTLY được thiết kế để refresh một materialized view đã có dữ liệu mà không khóa SELECT, không phải để đặt view thành unscannable.

### Đáp án 7. Populated có thể 0 rows

Có. `REFRESH ... WITH DATA` đã nạp query thành công, nên `ispopulated=true` ngay cả khi query trả 0 rows. Muốn dùng CONCURRENTLY còn cần UNIQUE index hợp lệ; điều kiện không phải `COUNT(*) > 0`.

### Đáp án 8. UNIQUE index đủ điều kiện

Index phải:

1. Nằm trên **chính materialized view**.
2. Là **UNIQUE** và valid.
3. Chỉ dùng **column names** làm index keys, không dùng expression.
4. Bao phủ **tất cả rows**, không có partial predicate `WHERE`.

Ngoài index, materialized view phải đã populated.

### Đáp án 9. PK của nguồn không đủ

Materialized view là một quan hệ riêng có tập rows đầu ra riêng; GROUP BY và JOIN có thể làm thay đổi identity. `REFRESH CONCURRENTLY` yêu cầu UNIQUE index **trên chính view**, không chỉ trên source table.

### Đáp án 10. Composite key

Một tenant có thể có báo cáo nhiều ngày, nên `UNIQUE(tenant_id)` không đúng và có thể thất bại.

```sql
CREATE UNIQUE INDEX ux_example_daily_revenue
ON mv_refresh_lab.daily_revenue (tenant_id, sale_date);
```

Nếu `ux_daily_revenue_tenant_day` đã tồn tại, index mới là thừa; câu SQL ở đây chỉ minh họa index key đúng, không khuyên tạo thêm một bản sao trên lab.

### Đáp án 11. Expression index

Không. Index trên `lower(email)` là **expression index**, không phải UNIQUE index chỉ gồm tên cột mà CONCURRENTLY yêu cầu. Nó có thể phục vụ query khác nhưng không dùng làm điều kiện duy nhất cho concurrent refresh.

### Đáp án 12. Partial index

Không. `WHERE active` làm index chỉ bao phủ một phần rows. CONCURRENTLY yêu cầu index UNIQUE bao trùm toàn bộ materialized view.

### Đáp án 13. Index non-unique

Không. `CREATE INDEX` không bảo đảm uniqueness. Phải có ít nhất một UNIQUE index đủ điều kiện, bất kể materialized view có bao nhiêu index hỗ trợ SELECT.

### Đáp án 14. Bootstrap

```sql
-- 1. Tạo view chưa có dữ liệu:
-- CREATE MATERIALIZED VIEW ... AS SELECT ... WITH NO DATA;

-- 2. Nạp lần đầu, KHÔNG CONCURRENTLY:
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;

-- 3. Tạo index nếu chưa có:
-- CREATE UNIQUE INDEX ...
-- ON mv_refresh_lab.daily_revenue_later (tenant_id, sale_date);

-- 4. Các lần tiếp theo:
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue_later;
```

Phần 9 có bộ câu lệnh hoàn chỉnh. Đoạn trên giả định view `daily_revenue_later` đã được tạo bằng `WITH NO DATA`, có index ở bước 3 và đã populated trước bước 4.

### Đáp án 15. Doanh thu thay đổi

Trước REFRESH: **150.00** vì materialized view chưa cập nhật. Sau REFRESH có snapshot chứa đơn mới 25: **175.00** và `paid_orders=3`.

### Đáp án 16. Nhóm mới

Tenant 2, `2026-11-02` có hàng:

```text
tenant_id=2
sale_date=2026-11-02
revenue=110.00
paid_orders=1
```

Hàng pending 30 không được tính vào query `WHERE status='paid'`.

### Đáp án 17. Cập nhật pending thành paid

Sau khi đổi 30 sang paid và REFRESH với snapshot mới:

```text
revenue=140.00
paid_orders=2
```

Kết quả sau refresh khác với dữ liệu cũ (110, 1) đã được vật hóa trước đó.

### Đáp án 18. Nhóm biến mất

Không. Nếu không còn row nào `status='paid'` trong group đó, query `GROUP BY` từ tập paid không trả group. Sau refresh, view cũng không có row cho cặp tenant/ngày đó — không tự giữ group với revenue 0.

### Đáp án 19. ACCESS EXCLUSIVE

REFRESH thường dùng **ACCESS EXCLUSIVE** trên materialized view. SELECT bình thường cần ACCESS SHARE, hai mode xung đột nên SELECT có thể phải đợi.

### Đáp án 20. EXCLUSIVE

REFRESH CONCURRENTLY dùng **EXCLUSIVE** trên materialized view. SELECT thông thường dùng ACCESS SHARE; hai modes tương thích với nhau, vì vậy SELECT có thể tiếp tục đọc theo MVCC.

### Đáp án 21. Transaction giữ lock

Trong PostgreSQL, các lock liên quan có thể được giữ tới **COMMIT/ROLLBACK**. Dù REFRESH tính xong, transaction A chưa kết thúc vẫn có thể giữ ACCESS EXCLUSIVE, làm Session B chờ. Đây là lý do không để session REFRESH idle in transaction.

### Đáp án 22. Snapshot khi concurrent refresh

Session B không thấy dữ liệu refresh chưa commit. Nó đọc snapshot materialized view phù hợp; sau khi refresh commit, các statement mới với snapshot phù hợp có thể thấy tập mới. Một transaction REPEATABLE READ với snapshot cũ có thể tiếp tục thấy dữ liệu trước refresh.

### Đáp án 23. Timestamp không phải watermark

Không. Nếu snapshot nguồn của refresh được xác lập trước COMMIT 10:01 thì transaction đó có thể không nằm trong kết quả dù refresh hoàn thành 10:03. Cần biết điểm cắt nguồn/watermark mới khẳng định mức độ mới chính xác.

### Đáp án 24. ORDER BY

Không. REFRESH không bảo đảm thứ tự lưu kết quả theo ORDER BY của định nghĩa. SELECT cần:

```sql
SELECT *
FROM mv_refresh_lab.top_sales_demo
ORDER BY amount DESC, sale_id DESC;
```

Ví dụ giả định view `top_sales_demo` được tạo ở phần 14. Tie-breaker `sale_id` làm thứ tự xác định hơn.

### Đáp án 25. Scheduler overlap

Không. Một materialized view chỉ có **một refresh tại một thời điểm**, kể cả CONCURRENTLY. Scheduler nên skip/coalesce các lần chạy trùng, ghi last success/duration, giới hạn timeout và báo động khi thời gian refresh vượt cadence.

### Đáp án 26. Tần suất refresh

Không nên tạo job mỗi phút khi p99 duration 8 phút nếu không có cơ chế tránh chồng. Phải xét:

- Freshness SLA 10 phút.
- Duration p50/p95/p99.
- Thời điểm nguồn đã COMMIT/ETL hoàn tất.
- Thời gian đợi lock/queue.
- Chi phí CPU/I/O/temp/WAL.
- Backoff khi lỗi.

Nếu điều kiện SLA không khả thi với full refresh, cần tối ưu query hoặc thay mô hình cập nhật tăng dần.

### Đáp án 27. pg_matviews

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue';
```

`pg_matviews` không có trường built-in `last_refresh_at` phản ánh lần REFRESH thành công để phục vụ monitoring. Cần job metadata/log riêng.

### Đáp án 28. pg_index

```sql
SELECT
    idx.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indexprs IS NULL AS no_expressions,
    i.indpred IS NULL AS full_index,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

Candidate phù hợp có `indisunique=true`, `indisvalid=true`, không expression và không partial predicate, đồng thời view đã populated.

### Đáp án 29. pg_locks và blockers

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted
FROM pg_locks AS l
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.pid, l.mode;

SELECT
    a.pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

Trong lab, ACCESS EXCLUSIVE có thể chặn SELECT; EXCLUSIVE của CONCURRENTLY cho phép ACCESS SHARE nhưng vẫn có những xung đột khác.

### Đáp án 30. Quyền REFRESH

PostgreSQL **17+** dùng quyền **MAINTAIN** đối với REFRESH MATERIALIZED VIEW; role owner có quyền bảo trì phù hợp. PostgreSQL **16 và các major cũ hơn** yêu cầu quyền owner tương ứng (hoặc superuser/quyền được thừa kế phù hợp theo cơ chế vai trò), không dùng cú pháp GRANT MAINTAIN của major mới khi server chưa hỗ trợ.

### Đáp án 31. Không phải real-time

CONCURRENTLY đảm bảo SELECT trên view có thể tiếp tục đọc trong lúc refresh, **không** tự cập nhật ngay sau mỗi COMMIT ở bảng nguồn. Các lựa chọn khác:

- SELECT trực tiếp trạng thái transactional hoặc ledger nguồn.
- Bảng tổng hợp được cập nhật trong cùng transaction.
- Read model với consistency contract và version/watermark rõ nếu có event-driven processing.

Yêu cầu tài chính cần xác định rõ mức consistency, không chỉ giảm độ trễ trung bình.

### Đáp án 32. EXPLAIN và duration

`EXPLAIN (ANALYZE, BUFFERS)` trên SELECT định nghĩa giúp đo filter/JOIN/GROUP BY, row counts, I/O và các plan nodes. REFRESH còn cần thay/cập nhật dữ liệu vật hóa, đối chiếu trong CONCURRENTLY và duy trì indexes, nên phải đo **thời gian chính lệnh REFRESH** và các chỉ số resources/locks để biết tổng chi phí.

### Đáp án 33. Refresh chain

Thứ tự:

```text
1. Nguồn sales đã hoàn tất ingest
2. REFRESH mv_day, xác nhận thành công
3. REFRESH mv_month, xác nhận thành công
4. Công bố trạng thái báo cáo/dashboard
```

Nếu tháng được tính từ daily view cũ, refresh tháng trước daily sẽ tạo monthly summary còn stale; CONCURRENTLY không tự giải quyết dependency ordering.

### Đáp án 34. Không dùng DISTINCT tùy tiện

Không. Hai giao dịch thật có thể có `tenant_id,sale_date,amount` giống nhau. `DISTINCT` sẽ gộp chúng thành một, làm mất rows/doanh thu. Cần đưa transaction_id thực vào output nếu muốn từng giao dịch, hoặc GROUP BY đúng khóa nhóm và SUM/COUNT cho báo cáo tổng hợp.

### Đáp án 35. Invalid unique index

Đây thường là **lỗi cấu trúc**, không phải transient. Retry mỗi giây tạo load mà không sửa điều kiện. Job cần ghi lỗi, cảnh báo, kiểm tra `pg_index.indisvalid` và sửa index/khóa dữ liệu trước khi chạy lại.

### Đáp án 36. WITH NO DATA

View chuyển sang **unscannable**, SELECT có thể báo lỗi thay vì trả 0 rows. Khôi phục:

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue WITH DATA;
```

Sau khi populated trở lại và có UNIQUE index đủ điều kiện, các lần sau có thể dùng CONCURRENTLY.

### Đáp án 37. Hai câu lệnh CONCURRENTLY

- `CREATE UNIQUE INDEX CONCURRENTLY`: xây index với cơ chế giảm chặn phù hợp, **không chạy trong transaction block tường minh**.
- `REFRESH MATERIALIZED VIEW CONCURRENTLY`: làm mới materialized view nhưng cho SELECT tiếp tục đọc; yêu cầu populated view và UNIQUE index eligible. Tùy chọn này không đồng nghĩa với tạo index.

Các giới hạn transaction phải xem riêng từng loại lệnh.

### Đáp án 38. Refresh log

Một bảng metadata có thể gồm:

```text
view_name
last_started_at
last_succeeded_at
last_duration_ms
last_status
last_error
source_watermark
```

Timestamp kết thúc ghi khi job trả thành công. Nó không nói thời điểm snapshot query nguồn lấy dữ liệu là lúc ấy, nên không chứng minh mọi commit của nguồn trước thời điểm kết thúc đã được tính.

### Đáp án 39. JDBC job

Nếu mỗi GET dashboard gọi REFRESH, requests sẽ gây công việc lặp, chờ khóa và timeout vì một view chỉ có một refresh tại một thời điểm. Nên dùng job worker độc lập, account có quyền bảo trì đúng major, SELECT role riêng cho API, timeout/monitoring, cơ chế skip overlap và báo cáo last success.

### Đáp án 40. Chọn chế độ

`REFRESH MATERIALIZED VIEW CONCURRENTLY` là ứng viên tốt để thử vì:

- Dashboard có người đọc liên tục.
- Có business key đủ điều kiện UNIQUE index.
- Chấp nhận stale 15 phút.
- Chỉ phần nhỏ kết quả thay đổi.
- Refresh 4 phút có thể phù hợp cadence nếu được điều phối.

Phải đo reader latency trong lúc refresh, refresh duration p95/p99, WAL/temp/I/O/CPU, số rows output thay đổi, queue overlap, last successful refresh và watermark thật. Không hứa CONCURRENTLY luôn nhanh hơn hay luôn đáp ứng SLA khi chưa benchmark.

## 40. Checklist triển khai REFRESH MATERIALIZED VIEW

Trước khi đưa job vào production, hãy kiểm tra từng nhóm quyết định.

### 40.1. Định nghĩa dữ liệu

1. Query định nghĩa view có đúng ngữ nghĩa báo cáo không?
2. Các JOIN có làm nhân bản giao dịch trước GROUP BY không?
3. Có business key hoặc grouping key đủ để định danh từng row kết quả không?
4. Dữ liệu có late arrivals, corrections hoặc state transitions không?
5. Thời điểm snapshot/watermark được hiểu và công bố rõ chưa?

### 40.2. Khả năng dùng CONCURRENTLY

6. View đã `ispopulated=true` chưa?
7. Có UNIQUE index **trên chính view** không?
8. UNIQUE index có valid và chỉ dùng column names không?
9. Index có bao phủ toàn bộ rows, không có `WHERE` không?
10. Những cột khóa có semantics NULL phù hợp không?
11. Có đang dùng `WITH NO DATA` hoặc mới tạo view chưa nạp không?
12. Scheduler có tránh nhiều REFRESH cùng view chồng nhau không?

### 40.3. Hiệu năng

13. Đã đo query nguồn bằng EXPLAIN và dữ liệu thực chưa?
14. Đã đo duration REFRESH thường và CONCURRENTLY trên workload đại diện chưa?
15. Đã đo SELECT latency khi refresh đang chạy chưa?
16. Có đủ disk/temp space/WAL bandwidth cho refresh peak không?
17. Indexes trên view có lợi ích SELECT đủ bù chi phí duy trì không?
18. Có đo planning/execution time cho những query dashboard quan trọng không?
19. Long-running transactions có nguy cơ giữ locks/versions không?

### 40.4. Độ mới và vận hành

20. Freshness SLA là bao lâu và được đo thế nào?
21. Job có đợi ETL/source ingest hoàn thành chưa?
22. Có bảng/log ghi started/succeeded/failed/duration không?
23. Có watermark nguồn nếu cần chứng minh mức độ mới không?
24. Có alert khi không refresh thành công quá hạn không?
25. Có backoff, skip/coalesce và retry policy cho lỗi tạm thời không?
26. Có runbook cho lỗi unique index/unpopulated/source schema không?
27. Có chiến lược phục vụ stale data hay fallback nếu refresh lỗi không?

### 40.5. Quyền và an toàn

28. Role thực thi có `MAINTAIN` (PG17+) hoặc ownership theo major phù hợp không?
29. Role dashboard chỉ có quyền SELECT cần thiết không?
30. Nội dung view có dữ liệu nhạy cảm cần kiểm soát quyền/truy cập không?
31. Các DDL liên quan index/view có maintenance window và rollback plan không?
32. Có tránh REFRESH đồng bộ trong HTTP GET/transaction dài không?
33. Các bản ghi log có tránh SQL chứa secrets và thông tin nhạy cảm không?

## 41. Bảng tra cứu nhanh

| Vấn đề | Giải pháp/cảnh báo |
| --- | --- |
| Muốn làm mới materialized view | `REFRESH MATERIALIZED VIEW schema.view;` |
| Muốn SELECT tiếp tục khi refresh | `REFRESH MATERIALIZED VIEW CONCURRENTLY schema.view;` |
| View tạo `WITH NO DATA` | Lần đầu phải REFRESH thường `WITH DATA`. |
| CONCURRENTLY bị từ chối | Kiểm tra populated và UNIQUE index eligible. |
| Chỉ có index `CREATE INDEX` | Không đủ; cần UNIQUE index hợp lệ. |
| Chỉ có UNIQUE expression index | Không đủ cho CONCURRENTLY. |
| Chỉ có UNIQUE partial index | Không đủ cho CONCURRENTLY. |
| Muốn chỉ refresh một tenant | REFRESH chuẩn không có tham số `WHERE tenant_id`. |
| Muốn xem last refresh time | Dùng scheduler/job metadata riêng, không chỉ `pg_matviews`. |
| View có ORDER BY trong định nghĩa | SELECT client vẫn cần ORDER BY. |
| Refresh thường chặn SELECT | ACCESS EXCLUSIVE lock trên view. |
| Concurrent refresh vẫn có lock | EXCLUSIVE lock, tương thích SELECT ACCESS SHARE. |
| Muốn nhiều REFRESH cùng view song song | Không được; cần điều phối job. |
| Muốn kết quả real-time | Xem query live hoặc bảng tổng hợp transactional/incremental. |
| Tài liệu không có data mới dù refresh success | Kiểm tra snapshot/watermark/ETL timing và định nghĩa. |
| Không có permission | MAINTAIN ở PG17+; ownership ở major cũ. |

## 42. Tổng kết

**Materialized view giúp tăng tốc những truy vấn đọc lặp lại bằng cách lưu sẵn kết quả.** Đổi lại, dữ liệu không được tự cập nhật khi bảng nguồn thay đổi; PostgreSQL cần **`REFRESH MATERIALIZED VIEW`** để tính lại và xuất bản kết quả mới.

Những điểm cần nhớ:

- **REFRESH thường** có thể dùng ít tài nguyên hơn và phù hợp lần nạp đầu hoặc batch ngoài giờ, nhưng sử dụng **ACCESS EXCLUSIVE** trên materialized view và có thể chặn SELECT.
- **REFRESH CONCURRENTLY** cho phép SELECT thông thường tiếp tục đọc trong lúc làm mới nhờ cơ chế lock **EXCLUSIVE** tương thích ACCESS SHARE, nhưng vẫn có chi phí tính toán và locks khác.
- **CONCURRENTLY cần cả hai điều kiện**: materialized view đã populated, **và** có ít nhất một **UNIQUE index trên chính view**, chỉ dùng tên cột và bao gồm tất cả rows.
- **CONCURRENTLY không dùng cùng WITH NO DATA**, không thể bootstrap một view chưa nạp và không cho phép hai refresh cùng view chạy song song.
- **REFRESH không phải incremental maintenance mặc định**: query định nghĩa được tính lại và kết quả được thay thế/đối chiếu. Không nên gọi toàn bộ refresh sau mỗi INSERT nếu workload ghi lớn.
- **Freshness là quyết định nghiệp vụ**. Người đọc trong thời gian concurrent refresh vẫn có thể thấy bản cũ; thành công lúc 10:00 không chứng minh dữ liệu nguồn commit đến 10:00 đều đã được tính.
- **ORDER BY trong query định nghĩa không bảo đảm thứ tự SELECT** sau khi refresh; client phải viết ORDER BY nếu cần thứ tự.
- **Monitoring phải tự có**: `pg_matviews` hỗ trợ kiểm tra populated/indexes, `pg_stat_activity`/`pg_locks` hỗ trợ điều tra chờ, còn timestamp lần refresh thành công và watermark nên được job runner ghi riêng.
- **Quyền REFRESH phụ thuộc major**: PostgreSQL 17+ sử dụng quyền `MAINTAIN`, các major cũ yêu cầu ownership phù hợp.
- **Chọn chế độ theo workload**: đo reader wait, thời gian refresh, CPU/I/O/WAL/temp space, số rows thay đổi và tính khả thi của lịch; không mặc định CONCURRENTLY luôn nhanh hơn.

Nguyên tắc thực dụng:

> **Dùng materialized view khi có thể chấp nhận dữ liệu được làm mới theo đợt; dùng CONCURRENTLY khi cần giữ khả năng SELECT trong lúc làm mới và đã thiết kế được khóa UNIQUE hợp lệ.**

Nếu yêu cầu là *mọi lần đọc đều thấy giao dịch vừa commit*, bài toán là **consistency/cập nhật tổng hợp theo giao dịch**, không phải thêm một từ khóa CONCURRENTLY.

## 43. Tài liệu tham khảo

Các liên kết chính thức của PostgreSQL, nên chọn đúng major đang sử dụng:

- [REFRESH MATERIALIZED VIEW — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html): cú pháp, điều kiện `CONCURRENTLY`, `WITH NO DATA` và giới hạn ordering.
- [CREATE MATERIALIZED VIEW — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-creatematerializedview.html): tạo view và `WITH DATA/NO DATA`.
- [Materialized Views — PostgreSQL Documentation](https://www.postgresql.org/docs/current/rules-materializedviews.html): đặc điểm lưu kết quả và ví dụ tổng hợp.
- [CREATE INDEX — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-createindex.html): UNIQUE index, biểu thức, partial index và CONCURRENTLY khi tạo index.
- [Explicit Locking — PostgreSQL Documentation](https://www.postgresql.org/docs/current/explicit-locking.html): ACCESS SHARE, EXCLUSIVE và ACCESS EXCLUSIVE.
- [REFRESH MATERIALIZED VIEW — PostgreSQL 16](https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html): đối chiếu khác biệt quyền owner ở major cũ.
- [REFRESH MATERIALIZED VIEW — PostgreSQL 17](https://www.postgresql.org/docs/17/sql-refreshmaterializedview.html): đối chiếu quyền MAINTAIN trên các major mới.









