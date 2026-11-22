# Quan sát kế hoạch truy vấn trước và sau khi thêm chỉ mục

Trong chương **Thực hành tổng hợp** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, người học kết nối những kiến thức về lược đồ, truy vấn, chỉ mục, giao dịch, đo hiệu năng và vận hành thành một thí nghiệm có thể lặp lại: **đọc execution plan của PostgreSQL trước khi tạo index, lựa chọn index theo một use case, rồi đo lại cùng truy vấn sau khi tạo index**.

Một câu SQL trả đúng kết quả chưa chắc sử dụng tài nguyên hiệu quả. Với bảng có vài trăm hàng, PostgreSQL có thể đọc toàn bảng trong thời gian ngắn; trên hàng triệu hàng, cùng truy vấn có thể tạo lượng đọc lớn, CPU tăng, truy vấn chậm và giữ connection của ứng dụng Java lâu hơn. Tuy nhiên, **thêm index không phải lúc nào cũng làm câu SQL nhanh hơn**: truy vấn trả phần lớn bảng, index thiếu cột phù hợp hoặc dữ liệu quá nhỏ có thể khiến sequential scan vẫn tối ưu. Index cũng tốn dung lượng, WAL và công ghi bảo trì.

Mục tiêu của bài là biết **đưa ra một giả thuyết có thể kiểm chứng**, **đo baseline trước thay đổi**, **đọc những phần quan trọng của EXPLAIN**, **đánh giá tác dụng và chi phí của index**, rồi **quyết định giữ, sửa hoặc bỏ index theo bằng chứng**. Các lệnh PostgreSQL dưới đây dành cho **database thí nghiệm cô lập**, không được chạy lệnh tạo/xóa hay nạp hàng trăm nghìn bản ghi trực tiếp vào production.

## 1. Mục tiêu học tập và tiêu chí hoàn thành

Sau thực hành, người học có thể:

1. Mô tả sự khác nhau giữa `EXPLAIN` và `EXPLAIN ANALYZE`, giữa chi phí ước lượng của planner và thời gian thực đo.
2. Xác định một use case Java cụ thể cần tối ưu, gồm filter, sort, pagination, projection và kích thước dữ liệu.
3. Tạo dữ liệu thử đại diện và ghi nhận baseline mà không làm ảnh hưởng môi trường thật.
4. Đọc được những node cơ bản như `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Sort`, `Limit` và `Index Only Scan`.
5. Giải thích vai trò của selectivity, cardinality, statistics, thứ tự cột trong index và kiểu truy vấn.
6. So sánh trước/sau dựa trên execution plan, actual rows, buffers, thời gian và tài nguyên; tránh khẳng định cải thiện chỉ từ một lần đo.
7. Nhận diện chi phí index lên thao tác `INSERT/UPDATE/DELETE`, WAL, ổ đĩa, migration và backup.
8. Đề xuất một thay đổi index có kiểm thử, có phương án khôi phục và tiêu chí triển khai.

**Sản phẩm thực hành:** hai hoặc nhiều output `EXPLAIN (ANALYZE, BUFFERS)` của **cùng một câu SELECT**, bảng so sánh và một đoạn kết luận có căn cứ. Các số đo phải lấy từ lần chạy thật của người học; bài này không coi các con số minh họa là benchmark đã thực hiện.

## 2. Bối cảnh nghiệp vụ: trang đơn hàng gần đây

Giả sử dịch vụ Java có endpoint:

```text
GET /api/tenants/{tenantId}/orders?status=PENDING&limit=25
```

Ứng dụng cần lấy **25 đơn gần đây nhất** của một tenant với một trạng thái cụ thể. Điều kiện nghiệp vụ:

- Mọi bản ghi trả về thuộc đúng tenant được xác thực.
- Trạng thái phải khớp giá trị đã được cho phép.
- Kết quả sắp xếp từ mới đến cũ theo `created_at`, sau đó `id` để ổn định khi trùng thời gian.
- Chỉ trả những trường cần hiển thị, không tải nguyên một entity graph gồm customer, lines và audit.
- Không được thay đổi dữ liệu hay làm yếu đi bảo vệ tenant chỉ vì cần nhanh hơn.

Câu SQL mục tiêu:

```sql
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

Khi bảng còn ít hàng, quét toàn bảng có thể hợp lý. Khi bảng có hàng trăm nghìn đến hàng triệu hàng, planner phải tìm ít kết quả trong tập lớn và sắp xếp để lấy 25 hàng đầu. Đây là một ứng viên để thử **B-tree composite index khớp các điều kiện lọc và sắp xếp**.

**Câu hỏi cần chứng minh:** index trên `(tenant_id, status, created_at DESC, id DESC)` có giúp PostgreSQL giảm số hàng cần duyệt, bỏ hoặc giảm sort, đọc ít buffer hơn và cải thiện latency với dữ liệu thực tế không?

## 3. Sơ đồ đường đi: từ Java tới execution plan

```text
HTTP request
     |
     v
OrderQueryService
     |
     v
PreparedStatement (tenant_id, status, limit)
     |
     v
PostgreSQL parser / planner / executor
     |
     +-- Thống kê bảng và cột (ANALYZE)
     +-- Có những index nào?
     +-- Phân phối tenant/status ra sao?
     +-- Điều kiện WHERE, ORDER BY, LIMIT?
     |
     v
Chọn execution plan
     |
     +-- Seq Scan + Sort + Limit
     |        hoặc
     +-- Index Scan + Limit
     |        hoặc kế hoạch khác
     |
     v
Rows / buffers / timing
     |
     v
Java map DTO và trả response
```

Một index không phải lệnh “bắt buộc sử dụng”. PostgreSQL lựa chọn kế hoạch dựa trên mô hình chi phí và thống kê hiện có. Sau khi tạo index, planner **có thể** dùng hoặc không dùng index; nhiệm vụ của người đo là giải thích tại sao.

## 4. Chuẩn bị môi trường kiểm thử cô lập

**Không chạy các lệnh DDL/seed trong production.** Hãy dùng PostgreSQL trên máy thử nghiệm, một database do CI tạo, hoặc Testcontainers. Điều kiện khuyến nghị:

| Thành phần | Cách chuẩn bị | Mục đích |
| --- | --- | --- |
| PostgreSQL | Cùng major version hoặc phiên bản được chọn rõ ràng; ghi lại version. | Tránh so kế hoạch giữa các engine/dialect khác nhau. |
| Database | Một DB/schema lab không chia sẻ với ứng dụng thật. | Được phép tạo/xóa bảng và index. |
| Credential | Role thử nghiệm có quyền trên dữ liệu lab, không dùng credential prod. | Giảm phạm vi rủi ro. |
| Dữ liệu | Hàng trăm nghìn hàng tổng hợp, tenant/status phân bố có chủ đích. | Có đủ kích thước để xem thay đổi plan. |
| Tài nguyên | Ghi CPU, RAM, storage, config và tải nền. | Giải thích độ nhiễu trong số đo. |
| Công cụ | `psql`/GUI SQL client, `EXPLAIN`, `ANALYZE` và thống kê DB. | Quan sát planner và executor. |
| Ứng dụng Java | JDBC driver và repository/query thật trong bài kiểm thử. | Kiểm tra tác động sau khi mapping DTO. |

Trong môi trường test có thể ghi version bằng:

```sql
SELECT version();
SHOW server_version;
SHOW default_transaction_isolation;
SHOW work_mem;
SHOW effective_cache_size;
SHOW random_page_cost;
```

Các thông số trên **không cần được sửa** chỉ để ép ra plan mong muốn. Ghi lại chúng giúp so sánh công bằng, vì version, statistics và cost parameters có thể dẫn tới lựa chọn khác nhau.

**Mẹo an toàn:** phần lab sử dụng bảng có tên `lab_orders` thay vì `orders`; tên này giúp giảm nguy cơ nhầm với bảng nghiệp vụ, nhưng **không thay thế việc xác nhận database và quyền kết nối**.

## 5. Tạo bảng thử nghiệm và dữ liệu có phân phối được kiểm soát

Chạy các lệnh dưới đây **chỉ trong database lab**. Bảng có primary key trên `id`, do đó đã tồn tại một index phục vụ khóa chính; bài thực hành chưa có index phụ cho mẫu truy vấn tenant/status.

```sql
CREATE TABLE lab_orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    INTEGER NOT NULL,
    status       TEXT NOT NULL
                 CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    created_at   TIMESTAMPTZ NOT NULL,
    total_cents  BIGINT NOT NULL CHECK (total_cents >= 0),
    note         TEXT
);
```

Tạo 600.000 hàng dữ liệu giả, không chứa thông tin cá nhân thật:

```sql
INSERT INTO lab_orders (
    tenant_id, status, created_at, total_cents, note
)
SELECT
    (g * 37 % 1009) + 1 AS tenant_id,
    CASE
        WHEN g % 20 < 17 THEN 'PAID'
        WHEN g % 20 < 19 THEN 'PENDING'
        ELSE 'CANCELLED'
    END AS status,
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    10000 + (g % 50000) AS total_cents,
    'synthetic lab row' AS note
FROM generate_series(1, 600000) AS g;

ANALYZE lab_orders;
```

Ở đây:

- `tenant_id` trải khoảng 1.009 tenant nhờ modulo với 1009; hệ số 37 không làm mất sự phân bố vì nguyên tố tương đối với 1009.
- `status` có phân phối **xấp xỉ** 85% PAID, 10% PENDING và 5% CANCELLED.
- `created_at` tăng theo từng phút, để bộ lọc “đơn gần đây” có ý nghĩa.
- `ANALYZE` tạo/cập nhật statistics giúp planner ước lượng chọn lọc thay vì dựa vào thống kê cũ hoặc thiếu.
- 600.000 hàng là mức demo, **không phải chuẩn benchmark**; kích thước thực phụ thuộc tài nguyên lab, PostgreSQL version, block layout và môi trường.

Không dùng một dữ liệu quá nhỏ chỉ có 100 hàng rồi kết luận rằng index vô ích. Ngược lại, không nạp hàng chục triệu hàng nếu môi trường thiếu dung lượng và mục tiêu bài chỉ cần thấy sự khác biệt giữa hai kiểu truy cập.

### Xác nhận phân phối trước khi đo

```sql
SELECT COUNT(*) AS total_rows
FROM lab_orders;

SELECT status, COUNT(*) AS rows_per_status
FROM lab_orders
GROUP BY status
ORDER BY status;

SELECT tenant_id, status, COUNT(*) AS n
FROM lab_orders
WHERE tenant_id IN (42, 43)
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Điều kiện tenant/status phải trả số hàng đủ để quan sát. Nếu dữ liệu seed bị thay đổi, hãy kiểm tra lại distribution trước khi so sánh plan. Không lấy số hàng giả định từ bài học làm bằng chứng nếu lệnh seed trên máy bạn đã chạy khác.

## 6. Ghi baseline trước khi tạo index

Trước khi thay đổi, lưu bản sao câu SQL và tham số. Thực thi:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

Trong PostgreSQL:

- `EXPLAIN` (không có `ANALYZE`) đưa ra **kế hoạch ước lượng** và thường **không thực thi** câu SQL cần giải thích.
- `EXPLAIN (ANALYZE)` **thực thi** câu SQL, ghi các hàng/thời gian quan sát thực tế rồi hiển thị kế hoạch; với câu SELECT này không có ghi dữ liệu nghiệp vụ.
- `BUFFERS` bổ sung thông tin về buffer block được chạm qua các node truy vấn.
- Planning Time và Execution Time là số liệu liên quan lập kế hoạch và thực thi ở server, **không phải toàn bộ HTTP p95** của Java.

**Cảnh báo quan trọng:** `EXPLAIN ANALYZE` đối với `INSERT/UPDATE/DELETE` hoặc các câu có side effect **sẽ thực sự chạy thao tác**. Nếu cần phân tích DML, phải dùng database lab hoặc transaction an toàn với hiểu biết về sequence, trigger và tác dụng ngoài DB; không xem nó là chế độ “dry run”.

### Bạn có thể thấy kiểu kế hoạch nào?

Trước index phụ, một kế hoạch có thể có cấu trúc tương tự (đây là **sơ đồ minh họa, không phải output số đo thật**):

```text
Limit
  -> Sort
       Sort Key: created_at DESC, id DESC
       Sort Method: top-N heapsort (nếu planner/executor chọn)
       -> Seq Scan on lab_orders
            Filter: (tenant_id = 42 AND status = 'PENDING')
            Rows Removed by Filter: ...
Planning Time: ...
Execution Time: ...
```

Planner có thể dùng kế hoạch khác tùy cardinality, statistics, parallel query, bộ nhớ và cấu hình. Không gán nhãn “lỗi” cho `Seq Scan` trước khi biết dữ liệu và selectivity.

### Lưu kết quả baseline vào bảng ghi nhận

| Thông số | Trước index — ghi số từ máy bạn | Vì sao cần |
| --- | --- | --- |
| PostgreSQL version / thông số liên quan | … | Đảm bảo so trên cùng môi trường. |
| Tổng số hàng và kích thước bảng | … | Bối cảnh so sánh. |
| Loại scan / sort node | … | Biết đường đi của query. |
| Estimated rows vs actual rows | … | Phát hiện thống kê sai. |
| Rows Removed by Filter | … | Bao nhiêu hàng bị bỏ qua sau đọc. |
| Shared hit/read buffers | … | Số block được chạm/cần đọc vào buffer cache. |
| Planning Time | … | Chi phí chọn plan. |
| Execution Time | … | Chi phí thực thi tại DB. |
| Kết quả trả về / thứ tự | … | Chứng minh không thay đổi semantics. |

**Chưa ghi số liệu nếu chưa chạy thí nghiệm.** Dấu ba chấm trong bảng này là chỗ người học cần điền từ output thật.

## 7. Đọc EXPLAIN theo thứ tự dễ hiểu

Một execution plan là **cây node**: node con cung cấp hàng cho node cha. Có thể đọc từ node lá (scan) lên `Sort` và `Limit`, đồng thời đọc điều kiện nào được áp dụng ở đâu.

| Node / trường | Cách diễn giải | Điểm cần tránh |
| --- | --- | --- |
| `Seq Scan` | Đọc relation tuần tự, dùng filter khi duyệt. | Không mặc định là chậm; có thể tối ưu với nhiều hàng. |
| `Index Scan` | Duyệt index để tìm vị trí hàng, có thể lấy cột khác từ heap. | Index scan có thể làm nhiều random heap accesses. |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Thu thập vị trí hàng từ index và đọc heap theo bitmap. | Không đồng nghĩa query nào có index cũng sẽ chọn index scan thường. |
| `Index Only Scan` | Có khả năng lấy dữ liệu từ index; visibility map vẫn ảnh hưởng heap fetches. | Không hứa “không bao giờ đọc heap”. |
| `Filter` | Điều kiện lọc áp dụng sau khi có row từ access path. | Có thể nhiều hàng bị đọc rồi bỏ. |
| `Index Cond` | Điều kiện planner dùng để giới hạn phạm vi truy cập qua index. | Không đồng nhất mọi `WHERE` với index condition. |
| `Sort` | Sắp xếp hàng theo tiêu chí; có thể dùng top-N khi LIMIT. | Một sort nhỏ trong memory có thể rất rẻ. |
| `Limit` | Chỉ trả số hàng yêu cầu. | Không có nghĩa scan bên dưới luôn chỉ đọc 25 hàng. |
| `cost=...` | Ước lượng tương đối dựa trên cost model. | **Không phải millisecond**. |
| `rows=...` | Số hàng ước lượng ở node. | Không phải số hàng thực khi chưa xem `actual rows`. |
| `actual time=...` | Thời gian thực tại node trong lần chạy. | Không cộng thô mọi thời gian node lồng nhau. |
| `loops=...` | Số lượt thực thi node. | `actual rows` có thể là trung bình mỗi loop. |
| `Buffers: shared hit/read` | Block được chạm trong shared buffers, miss phải yêu cầu đọc vào cache. | `read` không nhất thiết là đọc **đĩa vật lý**, do OS page cache. |
| `Heap Fetches` | Số lần kiểm tra heap của index-only scan trong kế hoạch. | Có thể lớn nếu visibility map chưa đánh dấu all-visible. |

Để tìm nút nghẽn, không chỉ nhìn node đầu tiên. Hãy hỏi: node nào đọc nhiều rows/buffers? Điều kiện nào không được push vào access path? Có sort/hash spill ra temp không? Planner ước lượng 10 hàng nhưng thực tế 100.000 hàng không?

## 8. Chọn index khớp mẫu lọc và sắp xếp

Với truy vấn:

```sql
WHERE tenant_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25
```

Một ứng viên hợp lý là B-tree composite index:

```sql
CREATE INDEX lab_orders_tenant_status_recent_idx
ON lab_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Giải thích:

1. `tenant_id` và `status` dùng **so sánh bằng**; chúng giới hạn một phần của index.
2. `created_at DESC` và `id DESC` tương thích yêu cầu sắp xếp trong nhóm tenant/status.
3. Nếu planner dùng đường index phù hợp, nó có thể duyệt những hàng gần nhất và **dừng sau khi có đủ 25** mà không cần sort toàn bộ tập.
4. `id` làm tie-breaker vì nhiều bản ghi có thể có cùng `created_at`; nếu không có `id` trong ORDER BY, trang có thể không ổn định.
5. `total_cents` không nằm trong index nên `Index Scan` thường cần truy cập heap để lấy cột này; với LIMIT 25, chi phí đó có thể chấp nhận được.

**Thứ tự cột có tác dụng.** Một index bắt đầu bằng `status` có thể cũng hữu ích khi cả tenant và status đều là equality conditions, nhưng mức tái sử dụng cho các truy vấn khác, thống kê và selectivity có thể khác. Không có một quy tắc “luôn đặt cột nhiều giá trị nhất trước” áp dụng cho mọi composite index. Quyết định phải dựa trên **tập query thực tế**, leftmost prefix, sort và chi phí ghi.

Vì bài này so sánh **một thay đổi**, hãy tạo đúng **một index ứng viên** trước, đo lại rồi mới thử các biến thể khác. Thêm 3 index cùng lúc khiến khó xác định index nào tạo ra cải thiện và index nào chỉ làm tăng chi phí.

## 9. Đo lại sau khi thêm index, không đổi câu SQL

Sau tạo index, chạy lại query **giữ nguyên filter, sort, LIMIT, projection và dữ liệu**:

```sql
ANALYZE lab_orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

PostgreSQL có thể tạo kế hoạch tương tự sơ đồ sau (đây là **ví dụ hình dạng**, không phải số đo đã ghi):

```text
Limit
  -> Index Scan using lab_orders_tenant_status_recent_idx
       on lab_orders
       Index Cond: (tenant_id = 42 AND status = 'PENDING')
Planning Time: ...
Execution Time: ...
```

Nếu planner chọn index, bạn thường thấy số hàng cần duyệt và số buffer được chạm giảm rõ đối với mẫu **tenant hẹp + LIMIT nhỏ**. Tuy nhiên, điều đó chỉ được khẳng định sau khi đối chiếu output thật.

Nếu output vẫn là `Seq Scan`, chưa có nghĩa PostgreSQL “không nhận index”. Planner có thể nhận thấy scan tuần tự rẻ hơn cho kích thước bảng, phân phối dữ liệu hoặc điều kiện cụ thể. Hãy kiểm tra statistics, selectivity, có đúng index được tạo trong schema đang query không, và query có thật khớp key expressions không.

## 10. So sánh trước–sau bằng cùng một thước đo

Tạo một bảng kết quả:

| Chỉ số | Trước index | Sau index | Đánh giá |
| --- | --- | --- | --- |
| Plan scan node | Điền thực đo | Điền thực đo | `Seq Scan` → `Index Scan`? |
| Có `Sort`? | Điền | Điền | Có loại được sort không? |
| Actual rows cần đi qua node scan | Điền | Điền | Có giảm lượng xử lý? |
| Rows Removed by Filter | Điền | Điền | Hàng dư thừa bị duyệt có ít đi? |
| Shared hit/read blocks | Điền | Điền | Có giảm block accesses? |
| Planning Time | Điền | Điền | Có đánh đổi chi phí lập plan? |
| Execution Time | Điền | Điền | Có cải thiện đáng kể qua nhiều lần? |
| Kết quả 25 rows | So ID/hash | So ID/hash | **Phải tương đương** nếu dữ liệu không đổi. |
| Kích thước index mới | Không có | Điền | Giá phải trả của cải thiện. |

Không dùng bảng so sánh với các số “ước đoán là bao nhiêu” rồi công bố đã tối ưu. **Baseline và after phải lấy từ cùng workload, cùng schema (trừ index), cùng dữ liệu và điều kiện được ghi lại.**

### Ví dụ cách tính tỷ lệ cải thiện

Nếu kết quả chạy thật của bạn ghi `t_before` và `t_after` (cùng đơn vị), tỷ lệ tăng tốc về thời gian:

\[
\text{speedup} = \frac{t_{\text{before}}}{t_{\text{after}}}
\]

Phần trăm giảm thời gian:

\[
\text{reduction} = \frac{t_{\text{before}}-t_{\text{after}}}{t_{\text{before}}} \times 100\%
\]

Nếu trước là 80 ms và sau là 8 ms **trong một ví dụ giả định**, tốc độ nhanh hơn 10 lần, thời gian giảm 90%. Không có nghĩa mọi query của hệ thống đều nhanh hơn 10 lần, vì đây chỉ là một query trong điều kiện đã chọn.

## 11. Đo nhiều lần và hiểu cache nóng/lạnh

Thực thi lần đầu có thể đọc nhiều block chưa ở shared buffers hoặc OS page cache. Những lần sau có thể hưởng cache nóng. Sau khi tạo index, cache trạng thái khác với trước nên nếu chỉ đo **một lần trước và một lần sau**, kết luận dễ sai.

Đề xuất:

1. Ghi dữ liệu/DDL và xác định không có worker khác ghi vào bảng lab.
2. Chạy query một vài lần để làm nóng đường truy cập, sau đó thu thập nhiều lần đo cùng truy vấn.
3. Lặp lại một số lần ở hai trạng thái, ghi rõ trạng thái cache nếu thí nghiệm cố ý phân biệt cold/warm.
4. Báo median, p95 hoặc phạm vi biến thiên (tùy số mẫu), không chỉ lấy **mẫu nhanh nhất**.
5. So số buffer và plan bên cạnh thời gian, vì chúng giúp giải thích kết quả khác nhau do tải nền.
6. Nếu đo cold cache cần cơ chế reset được phép trong lab; **không xóa OS cache hoặc restart production** để làm thí nghiệm.

Ví dụ: trước index đọc 5.000 shared buffers nhưng sau index chỉ đọc 30 shared buffers, cùng số dòng và kết quả. Đây là bằng chứng giảm công việc đọc ở database đáng tin hơn chênh lệch 1–2 ms giữa hai lần chạy trên máy CI đang bị CPU tranh chấp.

**Lưu ý:** `shared hit` là block đã có trong PostgreSQL shared buffers; `shared read` là yêu cầu đọc block vào shared buffers, nhưng block đó vẫn có thể có trong **OS page cache**. Đừng gọi mọi `shared read` là một lượt disk physical I/O. Nếu có `track_io_timing` được bật và quyền xem phù hợp, các trường I/O timing có thể giúp, nhưng đó vẫn không phải toàn bộ latency ứng dụng.

## 12. Estimated rows, actual rows và statistics

Planner ước lượng số hàng thỏa filter dựa trên statistics do `ANALYZE` thu thập. Nếu ước lượng sai lớn, nó có thể chọn kế hoạch không tối ưu.

Ví dụ giả định:

```text
Planner estimated: rows=500
Executor observed: actual rows=75.000
```

Chênh lệch lớn gợi ý:

- Statistics cũ sau khi data distribution thay đổi đáng kể.
- Correlation giữa `tenant_id` và `status` mà statistics đơn cột chưa biểu diễn tốt.
- Dữ liệu skew: một tenant chiếm phần lớn bản ghi.
- Biểu thức lọc/cast/function khiến selectivity khó ước lượng.
- Generic prepared statement plan không sát với tham số hiện tại.

Trước tiên chạy `ANALYZE` phù hợp và xác nhận các giá trị thực. PostgreSQL có **extended statistics** cho một số quan hệ đa cột khi cần:

```sql
-- Thử trong lab khi có bằng chứng tương quan cột:
CREATE STATISTICS lab_orders_tenant_status_stats
    (dependencies, mcv)
ON tenant_id, status
FROM lab_orders;

ANALYZE lab_orders;
```

Extended statistics có thể cải thiện một số ước lượng, nhưng **không thay thế index**, và không tự bảo đảm planner chọn index. Việc tạo statistics cũng phải được đánh giá/phiên bản hóa nếu đưa vào migration thật.

### Khi statistics không phải nguyên nhân

Nếu query trả 80% toàn bộ bảng, `Seq Scan` có thể hợp lý dù thống kê chính xác và index tồn tại. Nếu query trả 25 hàng nhưng buộc `OFFSET 1000000`, index cũng có thể phải đi qua nhiều hàng. Đừng tăng statistics target hoặc đổi planner cost parameters vô điều kiện khi chưa xem chính shape của query.

## 13. Thử một câu SELECT rộng để thấy index không phải thuốc chữa bách bệnh

Đổi use case sang báo cáo lấy phần lớn bảng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE status = 'PAID';
```

Với dữ liệu lab, PAID chiếm phần lớn bảng. Một `Seq Scan` có thể hợp lý: đi qua hầu hết heap theo thứ tự vật lý thường rẻ hơn duyệt index rồi truy cập ngẫu nhiên rất nhiều heap pages. Composite index bắt đầu bằng `tenant_id` cũng không được thiết kế chủ yếu cho truy vấn **chỉ lọc status**.

Các câu hỏi:

- Bao nhiêu phần trăm bảng thỏa `status = 'PAID'`?
- Có trả hàng trăm nghìn rows về Java mà nghiệp vụ không cần không?
- Đã phân trang hoặc aggregate tại DB thay vì tải toàn bộ entity vào JVM chưa?
- Query có sort/aggregate tốn chi phí hơn phần scan không?

**Đừng kết luận index thất bại chỉ vì query khác không dùng nó.** Một index phải được đánh giá theo bộ workload nó phục vụ và chi phí nó tạo ra cho tất cả thao tác ghi.

## 14. Thử cột thứ tự khác để thấy leftmost prefix và ORDER BY

Composite index hiện tại là:

```sql
CREATE INDEX lab_orders_tenant_status_recent_idx
ON lab_orders(tenant_id, status, created_at DESC, id DESC);
```

So sánh:

| Truy vấn | Index có thể hỗ trợ thế nào? | Cần xem EXPLAIN |
| --- | --- | --- |
| `tenant_id=? AND status=? ORDER BY created_at DESC,id DESC` | Rất phù hợp về điều kiện và thứ tự. | `Index Cond`, `Sort`, `Limit`. |
| `tenant_id=? ORDER BY created_at DESC` | Index bắt đầu bằng tenant nhưng xen status, thường không cung cấp thứ tự created_at toàn tenant. | Có `Sort` bổ sung hoặc plan khác không? |
| `status=?` | Thiếu điều kiện trên cột đầu tiên; có thể không hiệu quả với index này. | `Seq Scan` vs index; phiên bản DB có thể có các cách tối ưu khác. |
| `tenant_id=? AND status=? ORDER BY created_at ASC,id ASC` | B-tree có thể scan ngược để đáp ứng thứ tự cùng chiều khi phù hợp. | Có cần sort không? |
| `tenant_id=? AND created_at>=?` | Cột status ở giữa có thể làm index kém khớp với khoảng thời gian. | Rows scanned và filter ở đâu? |
| `tenant_id=? AND status=? AND id=?` | Index hoặc primary key có thể cạnh tranh. | Planner chọn đường nào rẻ hơn? |

Không áp dụng máy móc một quy tắc leftmost prefix cho mọi phiên bản/kiểu scan. PostgreSQL có các khả năng tối ưu đặc thù từng phiên bản, nhưng **một truy vấn tốt thường được thiết kế để khai thác các cột dẫn đầu và thứ tự index một cách rõ ràng**.

### Thử nghiệm bổ sung với yêu cầu khác

Nếu chức năng thực tế là “25 đơn gần đây của tenant, bất kể status”, index `(tenant_id, created_at DESC, id DESC)` có thể phù hợp hơn. Nhưng tạo thêm index thứ hai chỉ có ý nghĩa nếu workload đó đủ quan trọng để bù chi phí ghi và dung lượng.

Trong bài thực hành, **đổi một yếu tố mỗi lần** rồi so sánh plan; không tạo một rổ index khi chưa biết truy vấn nào cần chúng.

## 15. Index scan, bitmap scan và index-only scan khác nhau thế nào?

Khi một index được tạo, PostgreSQL không chỉ có hai lựa chọn “dùng index” hoặc “quét bảng”. Những kế hoạch quan trọng gồm:

**Index Scan:** PostgreSQL dùng key của index để xác định các tuple phù hợp rồi đọc heap khi cần lấy cột không có trong index hoặc kiểm tra visibility. Với truy vấn tenant/status và `LIMIT 25`, index scan có thể rất hiệu quả nếu vị trí trong index đã đúng thứ tự mong muốn.

**Bitmap Index Scan + Bitmap Heap Scan:** PostgreSQL tạo bitmap xác định các page cần đọc rồi truy cập heap theo cách giảm random I/O. Kế hoạch này có thể phù hợp khi số kết quả ở mức vừa hoặc khi kết hợp nhiều điều kiện/index. Bitmap thường **không duy trì thứ tự cần thiết cho ORDER BY**, nên query vẫn có thể thêm `Sort`.

**Index Only Scan:** có thể xảy ra khi **mọi cột cần lấy** đều sẵn trong index và điều kiện visibility cho phép giảm việc đọc heap. Với query đang chọn `total_cents` nhưng index chưa lưu cột đó, index-only scan thường không đáp ứng đủ projection.

Một biến thể có thể thử sau khi đã ghi baseline của index ban đầu là **covering index**:

```sql
-- Chỉ thử như PHƯƠNG ÁN THAY THẾ trong lab.
-- Không giữ thêm cả hai index tương tự nếu chưa chứng minh cần.
CREATE INDEX lab_orders_covering_idx
ON lab_orders (
    tenant_id, status, created_at DESC, id DESC
)
INCLUDE (total_cents);
```

Ở index này, `total_cents` là cột **INCLUDE**: có trong leaf entries để phục vụ đọc, nhưng không là cột khóa dùng xác định thứ tự tìm kiếm. Vì câu SELECT còn lấy `tenant_id` và `status` (cũng nằm trong key), tất cả cột cần trả có thể được cung cấp từ index.

Tuy nhiên:

- Có index covering **không đồng nghĩa** planner chắc chắn chọn `Index Only Scan`.
- Cơ chế MVCC của PostgreSQL cần kiểm tra tính hiển thị; khi visibility map chưa có all-visible cho page liên quan, index-only scan vẫn có **Heap Fetches**.
- Mọi hàng/cột `INCLUDE` bổ sung làm index lớn hơn, có thể giảm hiệu quả cache và tăng chi phí ghi.
- Với một query chỉ lấy 25 rows, lợi ích tránh 25 heap visits có thể không đáng chi phí index phình ra.

Trong lab có thể đo:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('lab_orders_tenant_status_recent_idx'::regclass)
    ) AS key_only_index_size,
    pg_size_pretty(
        pg_relation_size('lab_orders_covering_idx'::regclass)
    ) AS covering_index_size;
```

**Đừng tạo index covering chỉ vì thấy từ “Index Only” hấp dẫn.** Cần so duration, buffers, heap fetches, workload ghi và kích thước index.

## 16. Partial index cho tập con được truy vấn thường xuyên

Nếu hầu hết request quan trọng chỉ xem đơn `PENDING`, một **partial index** có thể nhỏ hơn index chứa tất cả trạng thái:

```sql
CREATE INDEX lab_orders_pending_recent_idx
ON lab_orders (tenant_id, created_at DESC, id DESC)
WHERE status = 'PENDING';
```

Index này chỉ lưu các hàng khớp predicate `status = 'PENDING'` tại thời điểm index được duy trì. Với dữ liệu giả định 10% PENDING, nó có thể nhỏ hơn composite index toàn bảng đáng kể, nhưng vẫn phải đo vì overhead index, độ rộng key và phân phối dữ liệu khác nhau.

Đổi lại:

1. Chỉ hữu ích cho query mà planner **chứng minh được** điều kiện của query hàm ý predicate index.
2. Không giúp các query `PAID` hoặc `CANCELLED` theo cùng cách.
3. Khi status thay đổi từ PENDING sang PAID, database cần cập nhật thành viên index; chi phí ghi có thể lớn theo workload chuyển trạng thái.
4. Truy vấn với bind parameter `status = ?` có thể dùng **generic prepared plan** không biết tham số luôn là PENDING, nên partial index có thể không được chọn.
5. Nếu nhiều index gần giống nhau cùng tồn tại, chi phí bảo trì/index bloat tăng.

Nên so ba phương án **theo các lần thử độc lập**: không có index phụ, composite index toàn trạng thái và partial index cho PENDING. Khi đo mỗi phương án, ghi rõ những index nào đang tồn tại.

### Cẩn trọng với partial index và prepared statement

Ví dụ:

```sql
PREPARE find_pending_or_other(integer, text) AS
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, id DESC
LIMIT 25;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_pending_or_other(42, 'PENDING');
```

Planner có thể chọn **custom plan** dựa trên tham số của lượt thực thi hoặc chuyển sang **generic plan** theo chính sách cache plan. Với partial index chỉ gồm PENDING, một generic plan phải dùng được cả khi status là PAID, nên thường không chứng minh được `status = 'PENDING'` từ parameter chưa biết.

Để tìm nguyên nhân trong **lab**, có thể thử riêng:

```sql
SET plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_pending_or_other(42, 'PENDING');

SET plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_pending_or_other(42, 'PENDING');

RESET plan_cache_mode;
DEALLOCATE find_pending_or_other;
```

Đây là **công cụ chẩn đoán**, không phải lời khuyên ép `force_custom_plan` trên production. Một quyết định sửa query/index phải xét driver/JDBC thực tế, nhiều giá trị parameter và chi phí lập plan.

## 17. Query pagination: index tốt chưa cứu được OFFSET quá sâu

Với trang đầu:

```sql
SELECT id, created_at, status, total_cents
FROM lab_orders
WHERE tenant_id = 42 AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25 OFFSET 0;
```

Index phù hợp có thể giúp đi thẳng tới các hàng đầu. Nhưng khi ứng dụng yêu cầu `OFFSET 100000`, database thường vẫn phải đi qua rất nhiều index entries/hàng trước khi trả page tiếp theo. Giá thành có thể tăng theo độ sâu offset.

Nếu nghiệp vụ cho phép **keyset pagination**, ta dùng khóa của hàng cuối trang trước làm cursor:

```sql
-- Cursor được lấy từ (created_at, id) của hàng cuối trang trước.
SELECT id, created_at, status, total_cents
FROM lab_orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

Với thứ tự giảm của **cả** `created_at` và `id`, tuple comparison `<` chọn các hàng đứng sau cursor. Chỉ sử dụng khi hai cột có kiểu phù hợp và quy tắc `NULL` đã được xử lý; trong bảng lab cả hai đều `NOT NULL`. Với query có sắp xếp hướng hỗn hợp, điều kiện cursor cần biến đổi khác.

Keyset có thể được composite index hỗ trợ tốt hơn ở trang sâu. Nhưng:

- Nó thay đổi giao diện từ “trang số 100” sang cursor/continuation token.
- Cần định nghĩa hành vi khi có đơn mới/cập nhật thời điểm giữa hai lần xem.
- Cursor phải gắn với filter, tenant, sort order và được bảo vệ khỏi sửa trái phép nếu chứa thông tin nhạy cảm.
- Đối với use case cần nhảy đến trang bất kỳ hoặc tổng số trang, có thể vẫn cần chiến lược khác.

Mục tiêu của bài thực hành là hiểu **plan và đặc tính truy vấn**, không chỉ thêm index rồi bỏ qua thuật toán phân trang.

## 18. Đo chi phí ghi khi thêm index

Mỗi index làm việc đọc phù hợp rẻ hơn trong một số trường hợp nhưng tạo thêm công cho:

- `INSERT`: tạo entry ở index mới.
- `UPDATE` các cột ảnh hưởng key/predicate/INCLUDE: có thể sửa index và tác động HOT update.
- `DELETE`: quản lý entry/phiên bản cũ theo MVCC và vacuum.
- WAL generation, replication, backup và checkpoint.
- Storage, cache, vacuum/reindex và thời gian migration.

Không nên đánh giá chỉ bằng việc query SELECT giảm từ 100 ms xuống 5 ms nếu hệ thống ghi hàng chục nghìn sự kiện mỗi giây và việc thêm index làm tăng lock wait hoặc WAL đáng kể.

### Thí nghiệm write overhead trong lab

Ghi baseline thời gian thao tác ghi **trước index**, khi DB ở trạng thái giống nhau. Sau khi thêm index, dùng một tập dữ liệu mới tương đương và đo lại. Có thể tạo một **bảng khác cùng schema** cho biến thể không index hoặc reset/reseed cô lập để tránh ảnh hưởng do kích thước bảng đã tăng.

Ví dụ workload update:

```sql
-- Chỉ trên lab_orders trong database test.
-- Dùng đúng cột filter và tình huống thật cần mô phỏng.
UPDATE lab_orders
SET status = 'PAID'
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Đây là câu ghi **thực sự thay đổi dữ liệu và thống kê phân phối**, nên không chạy trước khi hoàn tất so sánh SELECT hoặc phải reset fixture sau đó. Khi đo qua `EXPLAIN ANALYZE`, câu ghi cũng **thực thi thật**; không dùng nó làm phép xem plan “vô hại”.

Nếu ứng dụng chủ yếu cập nhật `status`, một index chứa `status` trong key/predicate có thể tác động đáng kể đến chi phí update. Nếu ứng dụng ghi hàng mới rất nhiều, cân nhắc WAL throughput và số index trên bảng.

### Ghi lại dung lượng trước–sau

```sql
SELECT
    pg_size_pretty(pg_table_size('lab_orders'::regclass)) AS table_size,
    pg_size_pretty(pg_indexes_size('lab_orders'::regclass)) AS all_indexes,
    pg_size_pretty(pg_total_relation_size('lab_orders'::regclass))
        AS total_size;
```

Lưu kích thước **trước khi tạo index và sau khi tạo index** để thấy storage delta, nhưng nhớ rằng các chỉ số có thể thay đổi thêm do vacuum, TOAST hoặc hoạt động ghi khác. Dung lượng index trên một bảng không chỉ bằng phần chênh kích thước tổng nếu trong lúc đo còn có backfill/rewrite.

## 19. Quyền và transaction khi thêm index

Ứng dụng Java runtime không nên sở hữu schema hoặc có quyền DDL chỉ để triển khai tối ưu. Trong thực tế:

1. **Developer** đề xuất index dựa trên trace, query plan và workload.
2. **Migration** được review chạy bằng role có quyền phù hợp.
3. **Ứng dụng runtime** tiếp tục dùng role ít quyền cho query/transaction thường ngày.
4. **Monitoring** theo dõi thời gian tạo index, write latency, WAL, replication lag và disk headroom.
5. **Rollback** được chuẩn bị nếu index gây ảnh hưởng xấu.

Không thêm `CREATE INDEX` vào code đường xử lý một request và cũng không cho ORM tự tạo index bất ngờ khi service khởi động ở production.

### CREATE INDEX CONCURRENTLY trên PostgreSQL

Trong production có ghi đồng thời, `CREATE INDEX CONCURRENTLY` thường được cân nhắc vì được thiết kế để tránh khóa chặn các thao tác ghi thông thường trong quá trình build chính. Tuy vậy, nó:

- Có thể chạy lâu, đọc nhiều lần và chờ các transaction liên quan.
- Tạo thêm WAL/I/O/storage trong lúc xây.
- Có những lock ngắn và điều kiện chờ; không nên gọi là hoàn toàn “không khóa”.
- **Không được chạy bên trong transaction block thông thường**.
- Nếu thất bại có thể để lại **index invalid** cần kiểm tra và dọn theo runbook.
- Không thay thế kiểm tra version DBMS, loại index và yêu cầu quản trị deployment.

Ví dụ **chỉ thực hiện sau review và có đủ headroom**, bên dưới đang dùng tên index lab:

```sql
-- Không đặt trong BEGIN/COMMIT hoặc một migration tự bọc transaction.
CREATE INDEX CONCURRENTLY lab_orders_tenant_status_recent_idx
ON lab_orders (tenant_id, status, created_at DESC, id DESC);
```

Nếu index lab đã tồn tại từ bước 8, câu trên sẽ báo trùng tên. **Không chạy cả hai lệnh tạo cùng index**; hãy hiểu đây là **hai hình thức triển khai thay thế**, một cho lab và một kịch bản production có ghi đồng thời. Công cụ migration như Flyway/Liquibase cần cấu hình chế độ execution không bao transaction cho statement dạng này theo phiên bản công cụ.

Kiểm tra tình trạng index:

```sql
SELECT
    ns.nspname AS schema_name,
    cls.relname AS index_name,
    idx.indisvalid,
    idx.indisready,
    pg_size_pretty(pg_relation_size(cls.oid)) AS index_size
FROM pg_index AS idx
JOIN pg_class AS cls ON cls.oid = idx.indexrelid
JOIN pg_namespace AS ns ON ns.oid = cls.relnamespace
WHERE cls.relname LIKE 'lab_orders_%_idx'
ORDER BY cls.relname;
```

Với build dài có thể quan sát tiến độ nếu DBMS/phiên bản hỗ trợ:

```sql
SELECT pid, datname, relid::regclass AS table_name,
       index_relid::regclass AS index_name,
       phase, lockers_total, lockers_done
FROM pg_stat_progress_create_index;
```

**Không xóa một invalid index trên production mà chưa đánh giá tính năng/constraint phụ thuộc và hoạt động concurrent khác.** Một số index có tính duy nhất có thể có hành vi đặc biệt trong quá trình build; thay đổi cần runbook phù hợp.

## 20. Khi index không được dùng: trình tự điều tra

Giả sử sau khi tạo index, `EXPLAIN` vẫn cho `Seq Scan`. Thay vì ép planner bằng setting toàn cục, đi theo thứ tự:

1. **Đúng database/schema/query?** Có đang kết nối DB test có index hay nhầm môi trường?
2. **Index có hợp lệ?** Xem `pg_index.indisvalid`, key/predicate và trạng thái build.
3. **Dữ liệu đủ lớn?** Với bảng nhỏ, seq scan có thể rẻ hơn.
4. **Selectivity?** Bao nhiêu phần trăm hàng thỏa filter? Có tenant cực lớn không?
5. **Query khớp index?** Kiểm tra `WHERE`, `ORDER BY`, cast và hàm.
6. **Statistics mới?** Chạy `ANALYZE` trong lab, so estimated vs actual rows.
7. **Prepared plan?** Custom/generic có làm planner không biết tham số cho partial index không?
8. **Projection?** Query có trả cột lớn hoặc rất nhiều hàng khiến heap accesses đắt?
9. **Alternative path?** Bitmap scan hoặc primary key index có rẻ hơn không?
10. **Version/cost parameters?** Ghi lại và thử thay đổi chỉ ở session lab để phân tích, không ép cấu hình production để “có Index Scan”.

Một trick chẩn đoán là:

```sql
-- CHỈ thử trong session test, không coi đây là giải pháp mặc định.
SET enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = 42 AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25;

RESET enable_seqscan;
```

Setting này có thể khiến planner xem xét index paths rõ hơn, nhưng **không chứng minh index path nên dùng trong thực tế**. Nó còn có thể chọn kế hoạch kém rất nhiều khi query không phù hợp. Phải reset session và đánh giá kế hoạch mặc định.

### Đừng bỏ qua loại dữ liệu và cast

Một query được viết để lọc `tenant_id INTEGER` nhưng vô tình chuyển cột thành text:

```sql
-- Dạng này không tương đương với predicate có thể tìm kiếm
-- trực tiếp qua B-tree integer index theo cách thông thường.
WHERE tenant_id::text = '42'
```

Cú pháp trên chỉ là **mảnh điều kiện**, không phải statement SQL hoàn chỉnh. Cast/function trên cột có thể làm planner không tận dụng được index key thông thường; cách tốt hơn thường là **bind đúng kiểu INTEGER** trong Java. Nếu nghiệp vụ thực sự cần biểu thức, cân nhắc expression index được chứng minh bằng workload và chi phí riêng.

## 21. Đưa truy vấn tối ưu vào Java JDBC/Spring

Thí nghiệm bằng literal SQL là bước đầu; ứng dụng thật thường dùng prepared statement. Ví dụ Spring JDBC:

```java
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class LabOrderQueryRepository {
    public record OrderRow(
            long id,
            int tenantId,
            String status,
            OffsetDateTime createdAt,
            long totalCents
    ) {}

    private final JdbcTemplate jdbc;

    public LabOrderQueryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderRow> newestOrders(
            int authenticatedTenantId, String status, int limit) {
        if (authenticatedTenantId <= 0) {
            throw new IllegalArgumentException("Invalid tenant");
        }
        if (!List.of("PAID", "PENDING", "CANCELLED").contains(status)) {
            throw new IllegalArgumentException("Invalid status");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Limit out of range");
        }

        return jdbc.query("""
            SELECT id, tenant_id, status, created_at, total_cents
            FROM lab_orders
            WHERE tenant_id = ?
              AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (rs, rowNum) -> new OrderRow(
                rs.getLong("id"),
                rs.getInt("tenant_id"),
                rs.getString("status"),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getLong("total_cents")
            ),
            authenticatedTenantId, status, limit
        );
    }
}
```

Ví dụ này dùng `lab_orders` và cần Spring JDBC/driver cùng DataSource trỏ tới DB lab; nó **không phải code đã tích hợp vào dự án thật**. Trong production, tenant phải được lấy từ authentication/authorization context đáng tin, không nhận nguyên giá trị tenant từ URL rồi mặc nhiên truy cập. Role DB chỉ có quyền phù hợp; nếu hệ thống dùng RLS, phải kiểm thử cùng cấu hình tenant session/transaction.

Điểm cần so với EXPLAIN:

- JDBC bind tham số đúng kiểu (`INTEGER`, `TEXT`, `LIMIT integer`).
- Query shape, `ORDER BY`, projection và LIMIT giống mẫu đã đo.
- Prepared statement có thể sử dụng custom/generic plan tùy driver/server và lịch chạy.
- Việc mapping DTO và trả JSON mất thời gian ngoài Execution Time của DB.
- Nếu JPA thay cho JDBC, cần xem SQL **thực tế do ORM sinh**, fetch graph và N+1; tối ưu một SQL viết tay không bảo đảm ORM chạy cùng SQL.

### Đo tại ranh giới application

Một endpoint có thể được cải thiện ở DB từ 80 ms xuống 8 ms (chỉ giả định) nhưng HTTP p95 ít thay đổi nếu phần lớn thời gian nằm ở service ngoài, mapping nhiều DTO hoặc chờ connection. Bởi vậy cần ghi cả:

| Tầng | Các thước đo cần cân nhắc |
| --- | --- |
| DB statement | Plan, actual rows, buffers, Execution Time, lock wait. |
| JDBC/pool | Prepared execution duration, connection acquire wait, timeout. |
| Application service | Thời gian use case, số query/request, mapping/serialization. |
| HTTP | p50/p95/p99 latency, error rate, throughput. |
| Host/volume | CPU, RAM, IOPS, WAL throughput, space remaining. |

**Không log literal SQL chứa giá trị người dùng nhạy cảm** để thu thập metric. Dùng query đã chuẩn hóa, operation name, span và nhãn metric có cardinality được kiểm soát.

## 22. Tái hiện trong integration test với PostgreSQL thật

Một bài học thực hành tốt nên tự kiểm tra **kết quả truy vấn không đổi** khi index được thêm; không chỉ assert rằng `EXPLAIN` có chuỗi `Index Scan`.

Quy trình kiểm thử:

```text
Fresh PostgreSQL test instance
        |
        v
Create schema / apply migrations
        |
        v
Seed deterministic synthetic fixture
        |
        v
Run SELECT, record ordered IDs + other fields
        |
        v
Run EXPLAIN baseline
        |
        v
Create one candidate index
        |
        v
Run EXPLAIN again + SELECT
        |
        v
Assert results equivalent
        |
        v
Record plan difference / performance measurements
```

Trong Java, Testcontainers có thể cung cấp PostgreSQL phù hợp phiên bản. Với JUnit 5/Spring Boot, cách khởi tạo phổ biến:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class OrderQueryIndexIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", postgres::getJdbcUrl);
        properties.add("spring.datasource.username", postgres::getUsername);
        properties.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    LabOrderQueryRepository repository;

    @Test
    void orderResultIsStable() {
        // Migration và fixture chạy trong test setup của dự án.
        var result = repository.newestOrders(42, "PENDING", 25);
        assertEquals(25, result.size());
        // Cần kiểm tra IDs, tenant, status và order sau khi
        // đã chuẩn bị fixture xác định; không chỉ kiểm tra size.
    }
}
```

Đây là **khung minh họa**, không phải suite chạy độc lập: cần dependency Testcontainers/Spring tương thích, schema/migration, dữ liệu fixture và kiểm soát vòng đời test. Nếu dữ liệu seed không bảo đảm ít nhất 25 hàng PENDING của tenant 42 thì assertion phải được điều chỉnh theo fixture thật.

Không viết unit test chỉ mock repository rồi tuyên bố đã chứng minh index. Mock không có PostgreSQL planner, MVCC, heap/index pages hay cost model.

### Có nên assert plan luôn dùng Index Scan?

**Thận trọng.** Planner có thể đổi node khi PostgreSQL version, số hàng, statistics hoặc cấu hình máy thay đổi, trong khi query vẫn đúng và nhanh. Một test cứng rằng output phải chứa chuỗi `Index Scan` có thể flaky hoặc che mục tiêu nghiệp vụ.

Các lựa chọn tốt hơn:

- **Contract test:** cùng dữ liệu thì kết quả, bộ lọc và thứ tự phải đúng.
- **Performance regression test cô lập:** kiểm tra query count, số buffers/độ trễ dưới điều kiện được kiểm soát, có ngưỡng hợp lý.
- **Plan review:** lưu EXPLAIN JSON, diff và kiểm tra thủ công hoặc công cụ phân tích phù hợp.
- **Migration test:** index tồn tại, hợp lệ và schema đúng sau chạy migration.

Khi có yêu cầu đặc biệt về plan shape, có thể assert điều kiện mạnh hơn trong pipeline chuyên biệt, nhưng cần giải thích rõ version/cấu hình ràng buộc và cách xử lý khi optimizer chọn kế hoạch tốt tương đương.

## 23. Dùng EXPLAIN định dạng JSON cho phép so sánh có cấu trúc

Output text dễ đọc với con người. Khi lưu bằng chứng tự động, định dạng JSON giúp truy xuất các trường mà không parse text bằng regex phụ thuộc spacing:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, tenant_id, status, created_at, total_cents
FROM lab_orders
WHERE tenant_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

JSON có cây `Plan`, các trường như `Node Type`, `Plan Rows`, `Actual Rows`, `Actual Loops`, thời gian và buffers khi được thu thập; tên trường/chi tiết khác nhau theo phiên bản và options.

Để so sánh **mang ý nghĩa**, đừng diff toàn văn JSON mà coi mọi thay đổi chi phí/time là lỗi: dữ liệu và bộ nhớ đệm có thể thay đổi. Thay vào đó:

1. Lưu Postgres version, table size, row count, index definitions và query parameters.
2. Tách node types, index name nếu có, `Index Cond`/`Filter`, actual row counts, buffers và thời gian.
3. So đường truy cập dữ liệu và điều kiện đã được push vào index.
4. Ghi rõ độ nhiễu của thời gian, nhất là khi lab chạy chung máy CI.
5. Đối chiếu kết quả nghiệp vụ riêng, không phụ thuộc nội dung plan.

Với hệ thống đa tenant, một EXPLAIN chứa literal tenant/customer có thể bị coi là dữ liệu nhạy cảm trong log. Đừng công bố query text hoặc literal chứa thông tin riêng tư trên dashboard không được phân quyền.

## 24. Quan sát workload thật với pg_stat_statements

EXPLAIN của một query rất hữu ích nhưng **không cho biết nó được gọi bao nhiêu lần/ngày** hoặc có chiếm nhiều CPU tổng thể hay không. Nếu `pg_stat_statements` được cài và bật theo chính sách PostgreSQL đang dùng, có thể xem thống kê tổng hợp:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows,
       shared_blks_hit,
       shared_blks_read,
       LEFT(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Chú ý:

- `calls` lớn với `mean_exec_time` nhỏ vẫn có thể tạo tổng tải lớn.
- `total_exec_time` đo thời gian thực thi theo thống kê, **không bao gồm toàn bộ chờ connection pool hoặc network từ Java**.
- `rows` và buffers là số liệu tích lũy; cần xem khoảng thời gian và mốc reset.
- Một normalized query có thể chạy với parameter khác nhau, selectivity khác nhau. Không coi một plan test của tenant 42 là đại diện cho tất cả tenant.
- Extension/quyền/phiên bản phải được quản trị bật trước; bài thực hành **không tự ý thay cấu hình production**.

Kết hợp trace Java với thống kê DB:

```text
Use case: listPendingOrders
  |-- 50.000 calls/day
  |-- Tenant phân bố không đều
  |-- Query normalized có thời gian DB tích lũy lớn
  |-- p95 JDBC tăng vào giờ cao điểm
  v
Chọn parameter đại diện (tenant nhỏ và tenant lớn)
  v
EXPLAIN trước/sau index trên staging/lab
  v
Triển khai có giới hạn và đo lại p95, buffers, WAL, writes
```

Đây mới là một vòng tối ưu dựa trên **tác động tổng thể của workload**, thay vì tối ưu một câu SQL hiếm khi chạy chỉ vì nó trông xấu.

## 25. Thay đổi chỉ mục trong ứng dụng đang hoạt động: quy trình có kiểm soát

Đưa kết quả từ lab vào production cần một kế hoạch rõ:

**Trước triển khai**

- Xác nhận query thực trong Java khớp SQL đã phân tích; có đủ sample tenant/status khác nhau.
- Ghi baseline sản xuất: query p95/p99, total executions, CPU, I/O, WAL, connection pool wait và kích thước bảng.
- Tính dung lượng index mới và headroom cho build, migration, replication/backup.
- Review quyền owner/migration, lock, thời gian cửa sổ thay đổi, khả năng chạy concurrently.
- Có backup và kế hoạch khôi phục phù hợp; xác định cách phát hiện index invalid.

**Trong triển khai**

- Thực thi migration đúng transaction mode, tránh tạo trùng index.
- Quan sát `pg_stat_progress_create_index` khi có hỗ trợ, disk, WAL, replica lag, write latency và lock waits.
- Nếu build lỗi hoặc vượt giới hạn vận hành, chuyển sang runbook dừng/khôi phục; không xóa file trong data directory để lấy chỗ.

**Sau triển khai**

- Kiểm tra index hợp lệ, query plan của các parameter đại diện và kết quả API.
- Đo lại read latency, tổng tải DB, write latency, dung lượng và ổn định trong giờ cao điểm.
- Xem có index cũ trùng chức năng để đề xuất bỏ **sau khi đánh giá phụ thuộc**, không drop vội.
- Nếu thay đổi không có lợi, có kế hoạch loại bỏ index có kiểm soát.

### Xóa index lab sau thực hành

Khi bài đo đã lưu đủ bằng chứng, có thể dọn **các index chỉ do bài lab tạo**:

```sql
DROP INDEX IF EXISTS lab_orders_covering_idx;
DROP INDEX IF EXISTS lab_orders_pending_recent_idx;
DROP INDEX IF EXISTS lab_orders_tenant_status_recent_idx;
DROP STATISTICS IF EXISTS lab_orders_tenant_status_stats;
```

Nếu lab không còn cần dữ liệu và đã xác nhận đúng database cô lập:

```sql
DROP TABLE IF EXISTS lab_orders;
```

**Không sao chép lệnh DROP này để chạy trên production**. Một index thực tế có thể được nhiều query dùng, hoặc là backing của constraint, và cách drop online có thể đòi `DROP INDEX CONCURRENTLY` ngoài transaction block; mọi thay đổi cần được review theo đặc tính bản triển khai.

## 26. Một bảng quyết định: khi nào nên giữ index?

| Kết quả quan sát | Khả năng giải thích | Quyết định gợi ý |
| --- | --- | --- |
| Index scan bỏ sort, buffers và p95 giảm trên use case quan trọng | Index khớp filter + order + limit. | Cân nhắc giữ sau đo chi phí ghi. |
| Planner vẫn seq scan, query trả 80% bảng | Scan tuần tự có thể hợp lý. | Không giữ index chỉ để “có index”. |
| Query tenant nhỏ nhanh, tenant rất lớn chậm | Data skew/parameter selectivity. | Thử parameter khác, stats/generic vs custom plan. |
| Index-only scan nhưng heap fetches cao | Visibility map chưa đáp ứng, workload update nhiều. | Đo MVCC/vacuum và lợi ích thực tế. |
| Read nhanh hơn 5% nhưng write throughput giảm đáng kể | Index maintenance tốn chi phí. | Xem lại business priorities và alternatives. |
| Partial index rất nhỏ nhưng query Java không dùng | Generic plan không suy được predicate, query không khớp. | Kiểm tra prepared plan và query contract. |
| Lợi ích chỉ xuất hiện lần chạy đầu | Cache/hệ thống có nhiễu. | Lặp thí nghiệm, ghi buffers và workload. |
| Kế hoạch tốt hơn nhưng tổng HTTP latency không đổi | Bottleneck ngoài DB hoặc pool. | Tìm nút nghẽn ở application/other service. |
| Tạo index quá lâu hoặc làm WAL/replica lag tăng | Migration/headroom không phù hợp. | Điều chỉnh lịch/build strategy và theo dõi. |

Quyết định nên dựa trên **chất lượng phục vụ nghiệp vụ với nguồn lực chấp nhận được**, không dựa vào việc EXPLAIN “đẹp” theo một mẫu cố định.

## 27. Bài tập mở rộng để kiểm tra hiểu biết

**Bài tập A — tenant lệch phân phối.** Tạo thêm nhiều hàng cho một tenant riêng, `ANALYZE` và so plan cho tenant nhỏ với tenant rất lớn. Câu hỏi: planner có ước lượng được hai trường hợp? Index có còn lợi khi một tenant chiếm phần lớn bảng?

**Bài tập B — trạng thái phổ biến.** Đổi filter từ `PENDING` sang `PAID`. Khi cả tenant/status vẫn được lọc và LIMIT nhỏ, index toàn trạng thái có hoạt động tốt không? Đừng suy chỉ từ tần suất status trên toàn bảng; phải xem số hàng của **tenant cụ thể**.

**Bài tập C — partial index.** So size và plan của partial index PENDING với composite index toàn bảng. Sau đó đo query qua prepared statement custom/generic. Câu hỏi: vì sao index nhỏ hơn không bảo đảm được dùng?

**Bài tập D — covering.** Thử index có `INCLUDE(total_cents)`. Quan sát `Index Only Scan` và `Heap Fetches`, so với kích thước index tăng. Câu hỏi: query LIMIT 25 có thật cần covering index không?

**Bài tập E — page sâu.** So `LIMIT 25 OFFSET 0`, `OFFSET 500` và keyset cursor trên một tenant có đủ nhiều hàng. Câu hỏi: số hàng đọc và buffers tăng theo độ sâu thế nào?

**Bài tập F — chi phí ghi.** Đo một workload `INSERT` và chuyển `PENDING → PAID` trên fixture mới, trước/sau index. Câu hỏi: lợi ích read bù được write overhead không?

**Bài tập G — actual vs estimated.** Thay dữ liệu lớn mà chưa `ANALYZE`, ghi sai khác hàng ước lượng. Sau đó chạy `ANALYZE` rồi đo lại. Câu hỏi: khi nào statistics thay đổi plan dù index không đổi?

Các bài tập phải chạy trong môi trường test có thể tái tạo. Với mỗi biến thể, ghi rõ **index nào đang tồn tại, dữ liệu nào đã bị thay đổi và các mốc đo**.

## 28. Mẫu báo cáo thực hành có thể dùng lại

Một báo cáo review index nên có cấu trúc:

```text
Use case:
  listPendingOrders(tenantId, limit=25)

Business contract:
  filter tenant + status, created_at/id DESC, DTO 5 cột

Environment:
  PostgreSQL version, host/container resources, JDBC driver
  table rows, table size, data distribution, stats timestamp

Baseline:
  SQL text + representative parameters
  EXPLAIN before: node types, estimated/actual rows, buffers
  repeated execution durations and HTTP/JDBC latency if measured

Proposed change:
  CREATE INDEX ... ON (tenant_id, status, created_at DESC, id DESC)
  index size, expected write impact, migration approach

After:
  EXPLAIN after + same SQL/params/data
  buffers, rows, timing, result hash/equality

Trade-offs:
  storage, index maintenance, WAL, pool, replica, other queries

Decision:
  KEEP / REVISE / REJECT, with reasons
  rollback plan and post-deploy monitoring
```

Bản báo cáo phải phân biệt **giả thuyết**, **số đo quan sát**, **đánh giá** và **quyết định**. Nếu môi trường không đại diện traffic production, hãy ghi giới hạn đó, không gọi số đo lab là SLO production.

## 29. Các lỗi tư duy thường gặp

| Ngộ nhận | Vì sao sai? |
| --- | --- |
| “Query chậm thì thêm index vào mọi cột WHERE.” | Có thể tạo nhiều index dư thừa, làm write tốn hơn và không giúp ORDER BY. |
| “Có index thì PostgreSQL chắc chắn dùng.” | Planner chọn kế hoạch theo cost/statistics/parameter. |
| “Seq Scan là bug.” | Có thể hợp lý trên bảng nhỏ hoặc query đọc phần lớn dữ liệu. |
| “EXPLAIN cost=100 nghĩa là 100 ms.” | Cost là điểm chi phí tương đối, không phải thời gian đo. |
| “EXPLAIN ANALYZE chỉ mô phỏng, không chạy query.” | Nó thực thi statement; DML có side effect thật. |
| “Sau index nhanh hơn một lần là đủ chứng minh.” | Cache/tải nền có thể làm kết luận sai; cần lặp và so buffers. |
| “Index Only Scan không bao giờ chạm heap.” | MVCC visibility map có thể đòi heap fetches. |
| “Covering index luôn tốt hơn index key-only.” | INCLUDE tăng size/write overhead, có thể không đáng cho LIMIT nhỏ. |
| “Partial index PENDING luôn được dùng khi Java bind status=PENDING.” | Generic plan có thể không chứng minh predicate từ bind parameter. |
| “B-tree composite trên tenant,status tự sắp xếp toàn tenant theo time.” | Cột status nằm giữa có thể làm thứ tự theo time không toàn cục trong tenant. |
| “LIMIT 25 nghĩa là DB đọc đúng 25 rows.” | Scan/filter/sort bên dưới có thể đọc hàng trăm nghìn rows. |
| “Xóa 1 triệu hàng chắc giảm ngay size database.” | MVCC/vacuum thường tái sử dụng chỗ thay vì thu nhỏ file. |
| “Tạo index chỉ ảnh hưởng đọc, không ảnh hưởng ghi.” | Index maintenance, WAL, disk, vacuum, migration đều tăng. |
| “CREATE INDEX CONCURRENTLY không có tác động vận hành.” | Vẫn có chi phí, chờ transaction, lock ngắn và khả năng invalid index. |
| “Plan đẹp trên tenant 42 đủ cho mọi tenant.” | Skew và prepared plan có thể khiến mỗi tenant khác nhau. |
| “Test được trên H2 nghĩa là PostgreSQL planner tương tự.” | Cost model, index types, MVCC và dialect khác nhau. |

## 30. Checklist kiểm tra trước khi kết luận

1. Xác nhận **database lab** và role test, không có URL/credential production trong thao tác có tác dụng.
2. Định nghĩa đúng use case: filter, projection, order, LIMIT, tenant và tính đúng đắn.
3. Tạo đủ dữ liệu tổng hợp có phân phối rõ ràng, `ANALYZE` trước baseline.
4. Ghi PostgreSQL version, table size, query và parameters.
5. Lưu `EXPLAIN (ANALYZE, BUFFERS)` **trước index**.
6. Chọn một index ứng viên có lý do từ filter + sort.
7. Tạo index ở lab, ghi dung lượng và kiểm tra index hợp lệ.
8. Đo **cùng query/cùng dữ liệu** sau index, lặp nhiều lần.
9. Đối chiếu plan nodes, actual/estimated rows, buffers, sort, thời gian.
10. Kiểm tra **kết quả/ordered IDs không thay đổi**.
11. Thử parameter khác, data skew, custom/generic plans nếu query thật có bind.
12. Xem thêm index size, write overhead, WAL và các query bị ảnh hưởng.
13. Không coi một dạng node là mục tiêu cuối; tối ưu **nghiệp vụ + tài nguyên**.
14. Lập migration có quyền phù hợp, headroom, cách theo dõi và rollback.
15. Có kế hoạch giám sát sau triển khai trên workload thật và xác minh SLO.

## 31. Câu hỏi tự kiểm tra

**Câu 1.** Trước khi thêm index, `EXPLAIN` hiển thị `Seq Scan`. Có thể kết luận ngay truy vấn được thiết kế sai không?

**Không.** Seq Scan có thể tối ưu với bảng nhỏ hoặc query chọn phần lớn hàng. Cần xem rows, buffers, selectivity và execution time thực tế.

**Câu 2.** Vì sao bài học dùng `ORDER BY created_at DESC, id DESC` thay vì chỉ `created_at DESC`?

Vì `id` tạo thứ tự xác định khi nhiều đơn có cùng thời điểm, giúp phân trang ổn định và index hỗ trợ đúng thứ tự.

**Câu 3.** `cost=5000` trong EXPLAIN có phải query chạy 5 giây không?

**Không.** `cost` là ước lượng tương đối do optimizer dùng để so kế hoạch, không phải millisecond hay giây.

**Câu 4.** Sau khi thêm index, `Execution Time` giảm nhưng `shared hit` cũng giảm. Nên diễn giải thế nào?

Có thể query mới chạm ít shared buffer pages hơn. Cần so actual rows, cache, load và nhiều lần đo; không đồng nhất `shared read` với I/O thiết bị vật lý.

**Câu 5.** Index composite `(tenant_id,status,created_at DESC,id DESC)` có tự đáp ứng `ORDER BY created_at DESC` khi chỉ lọc `tenant_id` không?

**Không chắc.** Vì status nằm trước created_at trong index, các trạng thái khác nhau được nhóm riêng; dữ liệu trong toàn tenant không nhất thiết theo thứ tự created_at mong muốn. Planner có thể cần Sort.

**Câu 6.** Có `INCLUDE(total_cents)` thì PostgreSQL chắc chắn không đọc heap?

**Không.** Nó giúp đủ cột để cân nhắc index-only scan, nhưng MVCC visibility map có thể yêu cầu heap fetches và planner có thể chọn plan khác.

**Câu 7.** Vì sao partial index `WHERE status='PENDING'` có thể không được dùng khi JDBC query `status=?`?

Vì generic prepared plan không biết giá trị tham số ở lúc lập kế hoạch, nên không thể mặc định predicate partial index đúng với mọi giá trị.

**Câu 8.** Có nên tăng `enable_seqscan=off` ở production để ép PostgreSQL dùng index không?

**Không.** Đây chỉ là công cụ chẩn đoán trong lab; ép planner có thể làm những query khác chậm hơn. Cần sửa nguyên nhân thực và đo.

**Câu 9.** `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` có làm thay đổi hàng không?

**Có.** EXPLAIN ANALYZE thực thi UPDATE. Chỉ chạy thử trên môi trường cô lập hoặc transaction được thiết kế kỹ, không coi là dry run.

**Câu 10.** Tại sao việc thêm index có thể làm hệ thống ghi chậm hơn?

Vì mỗi insert/update/delete có thể phải duy trì thêm cấu trúc index, tạo WAL và tăng I/O, dung lượng, chi phí vacuum/maintenance.

**Câu 11.** `CREATE INDEX CONCURRENTLY` có thể đặt trong một migration mặc định bao transaction không?

**Không.** PostgreSQL không cho chạy lệnh này trong transaction block thông thường; cần cấu hình migration phù hợp và theo dõi khả năng index invalid nếu thất bại.

**Câu 12.** Sau khi tối ưu query trong PostgreSQL, API Java vẫn có p95 chậm. Nên làm gì?

Đo toàn đường request: connection pool wait, số SQL/N+1, mapping/serialization, external service, network, cache và CPU. DB Execution Time chỉ là một phần.

**Câu 13.** Có thể dùng kết quả EXPLAIN của tenant nhỏ để chứng minh index có lợi cho tenant lớn không?

**Không.** Data skew, số rows và prepared plan có thể khác. Cần sample các tham số đại diện và kiểm tra tổng workload.

**Câu 14.** Khi nào nên giữ index mới?

Khi bằng chứng cho thấy use case quan trọng được cải thiện đáng kể, kết quả SQL không đổi và chi phí ghi/dung lượng/migration/operations nằm trong ngân sách được chấp nhận.

## Kết luận

**Quan sát kế hoạch truy vấn trước và sau khi thêm chỉ mục** là một bài thực hành về **ra quyết định dựa trên số liệu**. Câu SQL đúng là điểm bắt đầu; người học phải hiểu planner chọn đường nào, đọc bao nhiêu hàng và buffer, mất thời gian ở đâu, và index mới có thực sự cải thiện workload cụ thể không.

Trong hệ sinh thái Java persistence, hãy đo SQL của **use case thật**, thử trên PostgreSQL cô lập với dữ liệu đại diện, lưu `EXPLAIN (ANALYZE, BUFFERS)` trước/sau, đọc selectivity/sort/estimated vs actual rows và đối chiếu kết quả nghiệp vụ. Cuối cùng, đánh giá chi phí của index lên ghi, WAL, disk, migration, backup và vận hành trước khi triển khai. **Index tốt không phải index luôn được dùng: đó là index giúp hệ thống đạt mục tiêu nghiệp vụ với tổng chi phí hợp lý và vẫn giữ đúng tính nhất quán, phân quyền, khả năng phục hồi.**
