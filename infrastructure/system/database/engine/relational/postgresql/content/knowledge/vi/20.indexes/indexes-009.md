# Chỉ mục một phần và khả năng suy ra điều kiện trong PostgreSQL

Trong cơ sở dữ liệu nghiệp vụ, không phải mọi hàng của một bảng đều có tần suất truy vấn như nhau. Một bảng công việc có thể chứa vài triệu công việc **đã hoàn tất** nhưng chỉ vài nghìn công việc đang **chờ xử lý**; một bảng tài khoản có nhiều bản ghi **đã xóa mềm** nhưng hệ thống chỉ tra cứu những tài khoản đang hoạt động; hoặc một bảng giao dịch chỉ thường xuyên lọc những bản ghi **chưa đối soát**.

Tạo chỉ mục B-tree thông thường trên toàn bộ bảng là lựa chọn hợp lệ, nhưng nó phải duy trì các mục chỉ mục cho cả những hàng mà workload hiếm khi quan tâm. PostgreSQL cung cấp **partial index — chỉ mục một phần**: một chỉ mục chỉ chứa những hàng của bảng thỏa một **predicate** (điều kiện lọc) được khai báo khi tạo.

Ví dụ:

```sql
CREATE INDEX jobs_queued_idx
ON jobs (tenant_id, run_after)
WHERE status = 'queued';
```

Chỉ mục trên **không** chứa mọi hàng `jobs`; nó chỉ lập chỉ mục những hàng có `status='queued'`. Tuy nhiên, một câu truy vấn muốn sử dụng nó phải phù hợp với điều kiện lọc đó. Đây là điểm nhiều người dễ bỏ qua:

> **PostgreSQL chỉ có thể dùng một partial index để tìm đầy đủ kết quả khi điều kiện của truy vấn suy ra rằng mọi hàng cần lấy đều thỏa predicate của chỉ mục** (hoặc planner có cách kết hợp truy cập khác để xử lý đầy đủ từng nhánh). Không đủ để hai điều kiện “trông có vẻ giống nhau” theo trực giác.

Bài thuộc chương **Chỉ mục** của module *Database Engine Relational PostgreSQL*. Chúng ta sẽ đi từ cú pháp, ví dụ SQL chạy độc lập, tư duy logic về **predicate implication**, giới hạn suy luận của planner, prepared statements, `UNIQUE` một phần, `NULL`, chi phí duy trì chỉ mục, `EXPLAIN` và các bài thực hành.

**Mục tiêu sau bài học:**

- Phân biệt partial index với index toàn bảng, index nhiều cột, covering index và partitioning.
- Giải thích điều kiện **`Q ⇒ P`** giữa bộ lọc truy vấn `Q` và predicate của chỉ mục `P`.
- Nhận diện trường hợp `AND`, `OR`, `IS NULL`, `IS NOT NULL` và so sánh bất đẳng thức có hoặc không suy ra predicate.
- Biết vì sao planner không phải một trình chứng minh logic tổng quát; những biểu thức chỉ tương đương về nghiệp vụ chưa chắc được nhận dạng.
- Hiểu giới hạn của tham số `$1` trong prepared statements, sự khác nhau giữa **generic plan** và **custom plan**.
- Dùng **partial unique index** để bảo vệ tính duy nhất chỉ đối với bản ghi “đang hoạt động”, kể cả dưới tải ghi đồng thời.
- Biết kiểm tra bằng `EXPLAIN`, thống kê, chi phí cập nhật và quy trình triển khai an toàn.

> **Bối cảnh phiên bản:** Những ví dụ cốt lõi về partial indexes, `UNIQUE` và `EXPLAIN` dùng các tính năng PostgreSQL phổ biến. `INCLUDE` được hỗ trợ từ PostgreSQL 11; `plan_cache_mode` có từ PostgreSQL 12. Hãy dùng phiên bản server phù hợp hoặc bỏ những ví dụ phụ thuộc phiên bản nếu môi trường cũ hơn.

---

## 1. Partial index là gì?

### 1.1. So sánh trực quan

Giả sử bảng `jobs` có 100.000 hàng:

```text
jobs
├── done       : 80.000 hàng
├── failed     : 12.000 hàng
├── running    :  3.000 hàng
└── queued     :  5.000 hàng
```

Một index toàn bảng:

```sql
CREATE INDEX jobs_status_run_after_idx
ON jobs (status, run_after);
```

về mặt logic duy trì entry cho **mọi hàng** trong bảng.

Một partial index:

```sql
CREATE INDEX jobs_queued_run_after_idx
ON jobs (run_after)
WHERE status = 'queued';
```

chỉ có entry cho **các hàng queued**, vì predicate ở cuối đã loại các trạng thái khác.

```text
                                  +----------------------+
                                  |  Partial B-tree       |
jobs                              |  WHERE status=queued |
  done     --------------------X  |                      |
  failed   --------------------X  |  các hàng queued      |
  running  --------------------X  |  sắp theo run_after   |
  queued   ---------------------> |                      |
                                  +----------------------+
```

Hình trên là sơ đồ khái niệm, không phải hình biểu diễn chính xác cấu trúc trang B-tree.

### 1.2. Predicate khác index key

Trong lệnh:

```sql
CREATE INDEX jobs_queued_idx
ON jobs (tenant_id, run_after)
WHERE status = 'queued';
```

có hai phần riêng:

| Phần | Vai trò |
|---|---|
| `(tenant_id, run_after)` | **Index key**: dùng để tra cứu, sắp xếp hoặc lọc các hàng đã có trong index |
| `WHERE status='queued'` | **Predicate**: xác định **những hàng nào được đưa vào index** |

Điểm đáng chú ý: **`status` không bắt buộc phải là index key**. Với truy vấn đã bảo đảm `status='queued'`, tất cả entry trong index đều có cùng giá trị trạng thái đó; thêm `status` vào đầu index key có thể trở nên dư thừa.

Nhưng một query thiếu `status='queued'` không thể giả định index chứa cả `done`, `running` và `failed`.

### 1.3. Predicate được đánh giá trên hàng của bảng được đánh index

Một partial index được định nghĩa trên **một bảng** và predicate xét dữ liệu từ bảng đó. Không thể viết predicate dùng join trực tiếp sang bảng khác theo kiểu:

```sql
-- KHÔNG phải định nghĩa partial index hợp lệ:
-- CREATE INDEX idx ON orders (created_at)
-- WHERE customer_id IN (
--     SELECT customer_id
--     FROM customers
--     WHERE status = 'active'
-- );
```

Điều kiện bên trong index predicate không được tùy ý tham chiếu bảng khác bằng subquery. Nếu cần chỉ mục theo trạng thái của bảng liên quan, hãy xem lại thiết kế dữ liệu, dữ liệu dẫn xuất được duy trì nhất quán, materialized view, partitioning hoặc phương án truy vấn phù hợp.

### 1.4. Partial index không thay đổi kết quả SQL

Index là một cấu trúc truy cập. Nó không xóa hàng ngoài predicate và không khiến SELECT tự động chỉ thấy hàng trong index.

```sql
SELECT *
FROM jobs;
```

vẫn có thể trả mọi trạng thái. Một partial index chỉ thay đổi **lựa chọn đường truy cập khả thi của planner**, chứ không tự gắn `WHERE status='queued'` lên tất cả câu truy vấn.

---

## 2. Mấu chốt: khả năng suy ra điều kiện (predicate implication)

Đặt:

- **`P(row)`**: predicate của partial index.
- **`Q(row)`**: toàn bộ điều kiện `WHERE` của query đang xét.

Một partial index có thể được dùng như nguồn phù hợp cho một nhóm hàng khi:

```text
Mọi hàng làm Q đúng đều phải làm P đúng.

Viết theo logic:

    Q => P
```

Nghĩa là **tập hàng mà query cần nằm trong tập hàng được index bao phủ**.

### 2.1. Ví dụ suy ra đơn giản

Partial index:

```sql
CREATE INDEX idx
ON jobs (run_after)
WHERE status = 'queued';
```

Query:

```sql
SELECT *
FROM jobs
WHERE status = 'queued'
  AND run_after < TIMESTAMPTZ '2026-11-15 00:00+00';
```

`Q` là:

```text
status='queued'
AND run_after < cutoff
```

Rõ ràng mỗi hàng thỏa `Q` cũng thỏa `P: status='queued'`.

**`Q ⇒ P` là đúng**, nên partial index **có thể phù hợp**.

### 2.2. Chiều suy luận ngược thường sai

Query:

```sql
SELECT *
FROM jobs
WHERE run_after < TIMESTAMPTZ '2026-11-15 00:00+00';
```

Không có điều kiện `status`. Một hàng `done` cũng có thể có `run_after < cutoff`. Query muốn lấy cả những hàng **không nằm trong partial index**.

Do đó `Q ⇒ P` **không đúng**. Partial index này **không thể một mình là nguồn đầy đủ cho toàn bộ kết quả** của truy vấn ấy.

### 2.3. Bảng tư duy

Giả sử `P` là `status='queued'`.

| Query predicate `Q` | `Q ⇒ P`? | Diễn giải |
|---|---|---|
| `status='queued'` | Có | Trùng predicate |
| `status='queued' AND tenant_id=2` | Có | Điều kiện bổ sung làm tập nhỏ hơn |
| `status='queued' AND priority >= 8` | Có | Vẫn chỉ lấy queued |
| `status='running'` | Không | Tập hàng khác |
| `status IN ('queued','running')` | Không | Query còn cần running |
| `run_after < cutoff` | Không | Không ràng buộc trạng thái |
| `status='queued' OR priority=9` | Không | Nhánh priority có thể là done |
| `status='queued' AND (priority=9 OR tenant_id=2)` | Có | Cả hai nhánh vẫn ràng buộc queued |

Đây là **suy luận logic trước khi optimizer tính chi phí**. Khi đã chứng minh được tính phù hợp, PostgreSQL vẫn có thể không chọn index vì một sequential scan hoặc một index khác rẻ hơn.

### 2.4. Suy luận logic và khả năng nhận ra của planner là hai tầng riêng

Hai câu hỏi khác nhau:

1. **Về logic**, `Q ⇒ P` có đúng với mọi hàng không?
2. **Về triển khai**, PostgreSQL planner có nhận ra điều đó khi lập kế hoạch không?

PostgreSQL **không có một bộ chứng minh định lý tổng quát** để giải mọi biểu thức tương đương; nó nhận ra một số trường hợp đơn giản, chẳng hạn các điều kiện khớp cấu trúc hoặc một số so sánh bất đẳng thức. Vì vậy:

> Một quan hệ suy luận đúng theo tri thức nghiệp vụ **không đảm bảo planner sẽ nhận dạng và chọn partial index**.

Với predicate phức tạp, nên viết truy vấn dùng điều kiện dễ nhận diện, tránh kỳ vọng PostgreSQL sẽ tự hiểu những hàm/phép biến đổi tương đương không hiển nhiên.

---

## 3. Tạo bộ dữ liệu thực hành riêng

Mọi ví dụ thao tác bảng thật bên dưới dùng schema `partial_idx_lab` để tránh nhầm với dữ liệu ứng dụng.

### 3.1. Kiểm tra server và quyền

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Đảm bảo đây là database lab. Người chạy cần quyền tạo schema, bảng và index trong phạm vi tương ứng.

### 3.2. Tạo bảng jobs

```sql
CREATE SCHEMA IF NOT EXISTS partial_idx_lab;

CREATE TABLE partial_idx_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'running', 'failed', 'done')),
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    run_after TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Trong bảng này:

- `tenant_id` là phạm vi tổ chức.
- `status` quyết định job đang chờ/chạy/thất bại/hoàn thành.
- `run_after` là thời điểm job đủ điều kiện được lấy.
- `priority` giúp sắp xếp job cùng thời điểm.
- `completed_at` là thời điểm hoàn tất, nếu có.
- `payload` chứa dữ liệu xử lý, không nhất thiết cần có trong index.

### 3.3. Nạp dữ liệu phân bố trạng thái

Ví dụ nạp 20.000 job bằng `generate_series`:

```sql
INSERT INTO partial_idx_lab.jobs
    (tenant_id, status, priority, created_at,
     run_after, completed_at, payload)
SELECT
    1 + (g % 13) AS tenant_id,
    CASE
        WHEN g % 100 < 5 THEN 'queued'
        WHEN g % 100 < 8 THEN 'running'
        WHEN g % 100 < 20 THEN 'failed'
        ELSE 'done'
    END AS status,
    g % 10 AS priority,
    TIMESTAMPTZ '2026-11-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    TIMESTAMPTZ '2026-11-14 00:00:00+00'
        + (g % 240) * INTERVAL '1 minute' AS run_after,
    CASE
        WHEN g % 100 >= 20 THEN
            TIMESTAMPTZ '2026-11-15 00:00:00+00'
        ELSE NULL::timestamptz
    END AS completed_at,
    jsonb_build_object('seed', g) AS payload
FROM generate_series(1, 20000) AS gs(g);
```

Từ điều kiện `g % 100`, dữ liệu có khoảng:

- 5% `queued`.
- 3% `running`.
- 12% `failed`.
- 80% `done`.

Vì 20.000 chia hết cho 100, số hàng seeded của từng trạng thái lần lượt là **1.000, 600, 2.400 và 16.000**.

**Lưu ý:** lệnh `INSERT` phía trên **không idempotent**; chạy lại sẽ tăng số hàng. Nếu muốn bắt đầu lại, dùng schema riêng mới hoặc dọn dữ liệu demo một cách có chủ đích khi không có kết nối khác đang dùng. Không chạy khối seed hai lần rồi dự đoán thống kê vẫn như ban đầu.

### 3.4. Kiểm tra phân bố và cập nhật thống kê

```sql
SELECT status, COUNT(*) AS jobs
FROM partial_idx_lab.jobs
GROUP BY status
ORDER BY status;

ANALYZE partial_idx_lab.jobs;
```

`ANALYZE` cập nhật thống kê giúp planner ước lượng số hàng, **không đảm bảo sẽ chọn index**. Kế hoạch vẫn phụ thuộc số hàng thực, phân bố tenant, điều kiện lọc, cost settings và trạng thái cache.

---

## 4. Tạo partial index đầu tiên

Mục tiêu: lấy các job `queued` theo tenant và thời điểm sẵn sàng chạy.

### 4.1. Câu lệnh CREATE INDEX

```sql
CREATE INDEX jobs_queued_tenant_run_after_idx
ON partial_idx_lab.jobs
    (tenant_id, run_after, priority DESC, job_id)
WHERE status = 'queued';
```

Đọc từng phần:

| Phần câu lệnh | Ý nghĩa |
|---|---|
| `jobs_queued_tenant_run_after_idx` | Tên chỉ mục |
| `ON partial_idx_lab.jobs` | Bảng được lập chỉ mục |
| `tenant_id` | Khóa dẫn đầu, hữu ích khi lọc theo tenant |
| `run_after` | Khóa tiếp, hỗ trợ điều kiện thời gian và sắp xếp |
| `priority DESC` | Hướng sắp xếp của khóa |
| `job_id` | Khóa ổn định để phân định thứ tự trong cùng giá trị trước đó |
| `WHERE status='queued'` | Chỉ những job đang chờ được đưa vào index |

Giả sử workload thường chạy:

```sql
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

Về logic, query chứa `status='queued'`, nên **mọi hàng mục tiêu đều nằm trong tập được partial index bao phủ**. Thêm điều kiện tenant và run_after làm tập nhỏ hơn.

### 4.2. Predicate không cần chứa tenant

Chỉ mục này bao gồm **queued của mọi tenant**; `tenant_id` là một **index key**, không phải điều kiện lựa chọn hàng tham gia index.

Đừng nhầm:

```sql
ON jobs (tenant_id, run_after)
WHERE status = 'queued'
```

với:

```sql
ON jobs (run_after)
WHERE status = 'queued' AND tenant_id = 2
```

Chỉ mục thứ hai **chỉ chứa tenant 2**, không giúp như một nguồn bao phủ đầy đủ queued của tenant khác. Chỉ tạo index chuyên biệt tenant khi workload và quản trị thực sự cho phép.

### 4.3. Partial index có phải nhất thiết nhỏ hơn?

Nếu chỉ khoảng 5% hàng có `queued`, index lọc theo trạng thái này **có cơ hội** nhỏ hơn index tương đương chứa toàn bộ hàng. Nhưng kích thước thực còn phụ thuộc:

- Số cột index key và chiều dài giá trị.
- Số hàng thực sự thỏa predicate.
- Kiểu index (B-tree/GiST...), fill factor và cấu trúc trang.
- `INCLUDE`, bloat và lịch sử cập nhật.
- Các index khác trên bảng.

Không dùng “5% hàng” để suy ra “index chính xác bằng 5% dung lượng của index toàn bảng”.

---

## 5. EXPLAIN: có điều kiện suy ra cũng chưa chắc dùng index

PostgreSQL dùng cost-based optimizer. **Phù hợp về logic** là điều kiện cần để sử dụng partial index như một nguồn đáp ứng query, nhưng **không đủ để đảm bảo nó sẽ được chọn**.

### 5.1. Kiểm tra bằng EXPLAIN

```sql
EXPLAIN
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

Kế hoạch có thể hiển thị:

```text
Index Scan using jobs_queued_tenant_run_after_idx ...
  Index Cond: ((tenant_id = 2) AND (run_after < ...))
```

**Đây chỉ là hình dạng kế hoạch minh họa.** Kế hoạch trên máy bạn có thể dùng Index Scan, Bitmap Scan, Seq Scan hoặc phương án khác. Nếu PostgreSQL nhận ra predicate `status='queued'` thông qua việc chọn partial index, nó không nhất thiết cần giữ điều kiện ấy như một Filter riêng, vì các entry đã thỏa predicate.

### 5.2. Đọc EXPLAIN ANALYZE

Với dữ liệu lab và câu SELECT không sửa dữ liệu:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

Chú ý:

- **Index Scan / Bitmap Index Scan / Seq Scan**: đường truy cập đã chọn.
- **Index Cond**: điều kiện được index xử lý trực tiếp.
- **Filter**: điều kiện còn phải áp dụng để loại hàng sau khi lấy từ nguồn.
- **Rows Removed by Filter**: số hàng được loại tại filter (khi có).
- **Actual rows** và **estimated rows**: giúp đánh giá thống kê có lệch không.
- **Buffers**: trang được truy cập, có ích khi so sánh workload thực.
- **Sort / Incremental Sort / Limit**: xem chỉ mục có hỗ trợ thứ tự cần thiết không.

`EXPLAIN ANALYZE` thực sự chạy SELECT để đo; với lệnh ghi `UPDATE`/`DELETE`, nó cũng **thực sự ghi** nếu không có biện pháp rollback. Bài này chỉ sử dụng nó cho SELECT.

### 5.3. Planner có thể chọn Seq Scan

Ngay cả khi `Q ⇒ P` đúng, planner có thể chọn quét bảng nếu:

- Bảng rất nhỏ.
- Phần lớn hàng được truy vấn cần lấy.
- Điều kiện tenant/time không đủ chọn lọc.
- Truy vấn cần nhiều cột phải lấy từ heap.
- Index ordering không phù hợp `ORDER BY`.
- Thống kê và tham số chi phí khiến một phương án khác rẻ hơn.

Không kết luận “partial index không hoạt động” chỉ vì thấy Seq Scan ở một dataset nhỏ. Hãy dựa vào kế hoạch, thống kê và workload có tính đại diện.

---

## 6. Suy luận qua AND: điều kiện mạnh hơn predicate

Predicate của index:

```sql
WHERE status = 'queued'
```

Các truy vấn sau đều **suy ra** predicate:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued';
```

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 3;
```

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 3
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

Tại sao?

```text
Q = P AND R

Q đúng => cả P và R đúng
      => P đúng
```

Đây là dạng suy luận đơn giản nhất nên được ưu tiên khi thiết kế query dùng partial index.

### 6.1. Không phải mọi AND đều giúp index key

Query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND priority = 9;
```

vẫn suy ra predicate và index **có thể áp dụng** về phạm vi hàng. Tuy nhiên, index key bắt đầu bằng `tenant_id, run_after`; không có điều kiện trên hai cột đầu, nên sử dụng index để tìm đúng priority có thể kém hiệu quả. Index phù hợp về **predicate** không đồng nghĩa tối ưu về **thứ tự cột key**.

### 6.2. Điều kiện ngầm từ JOIN có luôn được chứng minh?

Giả sử câu truy vấn dùng các điều kiện JOIN và các constraint khác để logic nghiệp vụ suy ra một trạng thái. PostgreSQL đôi khi có thể suy luận từ các phép so sánh rõ ràng, nhưng không được giả định nó suy ra mọi ràng buộc phức tạp hoặc mọi quan hệ dựa trên bảng khác.

Nếu query thật sự chỉ cần queued, nên ghi tường minh:

```sql
WHERE j.status = 'queued'
```

thay vì chỉ kỳ vọng planner tự hiểu một cột của bảng khác chắc chắn có nghĩa job đang queued.

---

## 7. OR: một nhánh thiếu predicate có thể phá suy luận

Predicate vẫn là `status='queued'`.

### 7.1. Trường hợp KHÔNG suy ra

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
   OR priority = 9;
```

Một hàng `done` với `priority=9` cũng thỏa query. Vì vậy `Q ⇒ P` **sai**.

Partial index queued **không một mình bao phủ toàn bộ query**. Planner có thể dùng cách khác hoặc, trong một số trường hợp, kết hợp những nguồn truy cập để xử lý các nhánh; không nên khẳng định chỉ mục queued bị cấm xuất hiện trong mọi loại plan của truy vấn OR.

### 7.2. Trường hợp CÓ suy ra

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND (tenant_id = 1 OR tenant_id = 2);
```

Cả hai nhánh tenant đều nằm bên dưới điều kiện chung `status='queued'`.

```text
Q = P AND (A OR B)
Q => P
```

### 7.3. Dấu ngoặc quan trọng

So sánh:

```sql
-- Không được suy ra P:
WHERE (status = 'queued' AND tenant_id = 1)
   OR tenant_id = 2
```

với:

```sql
-- Suy ra P:
WHERE status = 'queued'
  AND (tenant_id = 1 OR tenant_id = 2)
```

Ở câu đầu, tất cả job tenant 2 đều có thể được chọn bất kể status. Ở câu sau, chỉ các job queued của tenant 1 hoặc 2 được chọn.

### 7.4. Có thể tách OR thành UNION ALL không?

Nếu nghiệp vụ cho phép và các nhánh được định nghĩa **không trùng nhau**, bạn có thể tách một query phức tạp thành nhiều SELECT:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 1

UNION ALL

SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'running'
  AND tenant_id = 1;
```

Hai nhánh ở ví dụ này không giao vì một hàng không thể vừa `queued` vừa `running`. Planner có thể xem xét đường truy cập phù hợp **riêng từng nhánh**. Nhưng `UNION ALL` giữ trùng giữa các nhánh nếu điều kiện chúng trùng, còn `UNION` loại trùng và có chi phí; không đổi câu SQL tùy tiện mà không xác định ngữ nghĩa mong muốn.

---

## 8. Khả năng suy ra từ bất đẳng thức

PostgreSQL có thể nhận biết một số suy luận số học đơn giản ở lúc lập kế hoạch.

### 8.1. Ví dụ x nhỏ hơn 10 thì cũng nhỏ hơn 100

Partial index:

```sql
CREATE INDEX jobs_low_priority_idx
ON partial_idx_lab.jobs (tenant_id, job_id)
WHERE priority < 8;
```

Query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND priority < 4;
```

Về logic:

```text
priority < 4  =>  priority < 8
```

Do đó query không cần hàng nằm ngoài index. PostgreSQL có khả năng nhận ra một số điều kiện bất đẳng thức đơn giản kiểu này.

**Nhưng:** index trên `tenant_id, job_id` không có `priority` làm key nên chưa chắc nhanh nhất cho workload lọc theo priority. **Tính suy ra predicate** và **tính hữu ích của index key** vẫn là hai câu hỏi khác nhau.

### 8.2. Ví dụ ngược lại KHÔNG suy ra

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE priority < 10;
```

Điều kiện này có thể bao gồm priority 8 và 9, không nằm trong index `priority < 8`.

```text
priority < 10  =/=>  priority < 8
```

### 8.3. Dấu ≤ và < ở cận

Giả sử predicate:

```sql
WHERE priority <= 5
```

thì query `priority < 5` hoặc `priority <= 3` về logic đều là tập con.

Ngược lại, query `priority <= 6` không suy ra predicate `priority <= 5`.

**Không suy luận cẩu thả ở giá trị biên.** `<` và `<=` khác nhau, nhất là với timestamp hoặc numeric.

### 8.4. Không biến ví dụ thành lời hứa suy luận tổng quát

PostgreSQL không phải hệ thống chứng minh mọi bất đẳng thức sau các phép biến đổi. Ví dụ:

```sql
-- Chỉ là biểu thức logic có thể tương đương theo miền dữ liệu,
-- không bảo đảm planner nhận ra mọi lần:
-- WHERE priority + 1 < 9
```

Không nên kỳ vọng chỉ mục `WHERE priority < 8` được dùng cho mọi cách viết biến đổi đại số của cùng điều kiện. Nếu đây là truy vấn quan trọng, **viết lại theo dạng predicate rõ ràng hoặc đo EXPLAIN**.

---

## 9. NULL và điều kiện ba giá trị

PostgreSQL sử dụng logic SQL với `TRUE`, `FALSE` và `UNKNOWN` (thường xuất hiện khi có `NULL`). Đối với partial index, một hàng **chỉ tham gia index khi predicate trả TRUE**.

### 9.1. Predicate IS NULL

Tạo chỉ mục cho job **chưa có thời điểm hoàn tất**:

```sql
CREATE INDEX jobs_not_completed_idx
ON partial_idx_lab.jobs (tenant_id, created_at, job_id)
WHERE completed_at IS NULL;
```

Truy vấn phù hợp:

```sql
SELECT job_id, tenant_id, created_at
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND completed_at IS NULL
ORDER BY created_at, job_id;
```

`Q ⇒ P` đúng vì query chứa `completed_at IS NULL`.

Nhưng query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued';
```

**không nhất thiết được planner chứng minh** là suy ra `completed_at IS NULL`, cho dù dữ liệu seed hiện tại có thiết lập `queued` luôn chưa hoàn tất. Trừ khi mô hình có constraint/bất biến và bộ suy luận planner nhận diện đủ, không dựa vào mối tương quan dữ liệu hiện tại như một chứng minh logic.

### 9.2. IS NOT NULL

Một index cho những hàng có thời gian hoàn tất:

```sql
CREATE INDEX jobs_completed_idx
ON partial_idx_lab.jobs (tenant_id, completed_at)
WHERE completed_at IS NOT NULL;
```

Query có `WHERE completed_at IS NOT NULL` là cách dễ thấy nhất để suy ra predicate.

Một so sánh:

```sql
WHERE completed_at <
    TIMESTAMPTZ '2026-11-16 00:00+00'
```

về ngữ nghĩa SQL, hàng làm biểu thức so sánh **TRUE** phải có `completed_at` không NULL. PostgreSQL có thể nhận ra những quan hệ nghiêm ngặt tương ứng tùy biểu thức và kế hoạch. Tuy nhiên, không suy rộng sang mọi hàm phức tạp hoặc phép biến đổi tương đương; hãy dùng `EXPLAIN` trên truy vấn thực.

### 9.3. Sai lầm: so sánh bằng NULL

Không dùng:

```sql
-- Sai ý nghĩa kiểm tra NULL:
-- WHERE completed_at = NULL;
```

Trong SQL, phép so sánh thông thường với NULL không trả TRUE. Cần:

```sql
WHERE completed_at IS NULL
```

Nếu bạn viết predicate bằng `= NULL`, không những query sai về tập hàng mà index cũng không trở thành “index các hàng chưa hoàn tất” như mong muốn.

### 9.4. Hai trạng thái boolean với NULL

Với cột `is_active BOOLEAN` cho phép NULL:

- `WHERE is_active` chỉ lấy TRUE.
- `WHERE NOT is_active` chỉ lấy FALSE, không lấy NULL.
- `WHERE is_active IS FALSE` lấy FALSE.
- `WHERE is_active IS NOT TRUE` lấy FALSE **và NULL**.

Hai predicate cuối **không tương đương** nếu cột nullable. Chọn đúng tập hàng trước khi tối ưu, không đổi giữa chúng vì “đọc giống nhau”.

### 9.5. Tập con cần tính theo điều kiện TRUE

Khi kiểm tra `Q ⇒ P`, câu hỏi là: **có tồn tại hàng nào mà `Q` TRUE trong khi `P` không TRUE không?** Nếu có, partial index không bao phủ đầy đủ query đó.

Sự khác nhau giữa FALSE và UNKNOWN quan trọng ở SQL ba giá trị; không dùng suy luận Boolean hai giá trị một cách máy móc khi predicate có NULL.

---

## 10. Prepared statements: tham số không phải hằng số ở mọi plan

Một bẫy nổi tiếng của partial index là câu truy vấn tham số hóa:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = $1
  AND tenant_id = $2;
```

Partial index có predicate:

```sql
WHERE status = 'queued'
```

### 10.1. Tại sao generic plan khó dùng chỉ mục này?

Khi lập **generic plan**, PostgreSQL phải tạo kế hoạch có thể chạy đúng với **mọi giá trị** của `$1`:

```text
$1 = 'queued'  -> partial index queued bao phủ kết quả.
$1 = 'done'    -> partial index queued thiếu rất nhiều hàng.
$1 = 'failed'  -> partial index queued cũng thiếu hàng.
```

Do đó điều kiện `status=$1` **không suy ra** `status='queued'` với mọi giá trị có thể của `$1`.

Một generic plan không thể dùng partial index queued như thể nó chứa đầy đủ mọi status.

### 10.2. Custom plan có thể khác

PostgreSQL có thể lập **custom plan** theo giá trị tham số của một lần thực thi. Khi giá trị đã biết ở lúc planning, planner **có thể** nhận ra trường hợp `$1='queued'` phù hợp với predicate của partial index.

Tuy nhiên, **không có bảo đảm mọi prepared statement sẽ dùng custom plan**, và dù dùng custom plan vẫn còn bài toán ước lượng chi phí. Cùng một prepared statement có thể chọn plan khác theo thời điểm và mẫu thực thi.

### 10.3. Thí nghiệm với PREPARE

```sql
PREPARE find_jobs(TEXT, INTEGER) AS
SELECT job_id, tenant_id, run_after
FROM partial_idx_lab.jobs
WHERE status = $1
  AND tenant_id = $2
ORDER BY run_after, job_id
LIMIT 20;
```

Quan sát plan ở chế độ custom:

```sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE find_jobs('queued', 2);
```

Quan sát plan ở chế độ generic:

```sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE find_jobs('queued', 2);
```

Kết thúc:

```sql
RESET plan_cache_mode;
DEALLOCATE find_jobs;
```

**Quan sát có thể khác nhau**: custom plan có khả năng sử dụng partial index cho giá trị queued; generic plan không thể giả định `$1` luôn là queued. `EXPLAIN EXECUTE` cho bạn biết kế hoạch thực tế, nhưng ngay cả với custom plan, planner có thể chọn index khác hoặc sequential scan.

### 10.4. auto, custom và generic

Tham số cấu hình:

```sql
SHOW plan_cache_mode;
```

Thông thường là `auto`. PostgreSQL có thể đánh giá việc dùng generic hay custom plan theo chi phí và lịch sử thực thi của prepared statement.

Không nên để `force_custom_plan` toàn ứng dụng chỉ vì một truy vấn partial index: **custom planning có chi phí**, và quy tắc chọn plan tổng thể còn phụ thuộc workload. Sử dụng thay đổi cưỡng bức chủ yếu để **chẩn đoán và thử nghiệm**, rồi xác định giải pháp phù hợp.

### 10.5. Thiết kế query ổn định: cố định điều kiện trạng thái, bind phần còn lại

Nếu endpoint chỉ phục vụ **job queued**, viết SQL:

```sql
PREPARE find_queued_jobs(INTEGER, TIMESTAMPTZ) AS
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = $1
  AND run_after < $2
ORDER BY run_after, priority DESC, job_id
LIMIT 20;

EXPLAIN EXECUTE find_queued_jobs(
    2,
    TIMESTAMPTZ '2026-11-14 02:00+00'
);

DEALLOCATE find_queued_jobs;
```

Ở đây điều kiện **`status='queued'` là hằng** trong SQL và query rõ ràng suy ra predicate của partial index, trong khi tenant và thời điểm vẫn được bind an toàn.

Đây là một lựa chọn thiết kế query **có chủ đích theo nghiệp vụ**, không phải đề xuất tự nối chuỗi SQL từ đầu vào. Nếu endpoint cần nhiều trạng thái tùy chọn, không được bí mật cố định queued làm mất kết quả hợp lệ.

### 10.6. Ví dụ JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class QueuedJobRepository {
    public List<Long> findDueJobIds(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        String sql = """
            SELECT job_id
            FROM partial_idx_lab.jobs
            WHERE status = 'queued'
              AND tenant_id = ?
              AND run_after < CAST(? AS timestamptz)
            ORDER BY run_after, priority DESC, job_id
            LIMIT 20
            """;

        List<Long> ids = new ArrayList<>();
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setInt(1, tenantId);
            ps.setObject(2, cutoff);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("job_id"));
                }
            }
        }
        return ids;
    }
}
```

Đây là Java text block (Java 15+) với JDBC driver hỗ trợ `OffsetDateTime`. Hằng trạng thái queued nằm trong câu SQL được kiểm soát bởi code; tham số tenant/cutoff vẫn được bind.

**Lưu ý an toàn nghiệp vụ:** `SELECT` job queued không tự biến chúng thành “đã được worker nhận”; khi xử lý queue đồng thời cần giao thức claim job phù hợp (ví dụ transaction với row locking/`SKIP LOCKED`), không suy rằng partial index giải quyết tranh chấp nhận job.

---

## 11. Partial UNIQUE index: tính duy nhất có điều kiện

Partial index không chỉ dùng để tăng tốc SELECT. Kết hợp với `UNIQUE`, nó có thể **thực thi một ràng buộc nghiệp vụ cho một tập con hàng**.

Ví dụ: trong một tenant, một email không được có **hai contact chưa xóa mềm**, nhưng các bản ghi đã xóa mềm được giữ làm lịch sử.

### 11.1. Tạo bảng contacts

```sql
CREATE TABLE partial_idx_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Quy tắc nghiệp vụ:** với cùng một tenant, không được có hai contact `deleted_at IS NULL` có email giống nhau theo so sánh **không phân biệt chữ hoa/thường**.

### 11.2. Tạo unique partial index

```sql
CREATE UNIQUE INDEX contacts_live_email_uq
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Diễn giải:

- Chỉ **contact chưa xóa mềm** mới có entry trong index.
- `tenant_id` là một phần khóa duy nhất.
- `lower(email)` đưa chuỗi email về cùng biểu thức so sánh theo quy tắc collations/casing của database.
- Hai contact live cùng tenant với cùng `lower(email)` vi phạm uniqueness.
- Hai contact **khác tenant** được phép cùng email.
- Contact đã `deleted_at IS NOT NULL` nằm ngoài index nên không bị ràng buộc bởi uniqueness của index này.

**Ghi chú:** Chuẩn hóa email thực tế còn có các vấn đề về Unicode/collation và quy tắc địa chỉ; `lower(email)` chỉ minh họa một lựa chọn so sánh case-insensitive, không phải bộ chuẩn hóa email toàn diện.

### 11.3. Chèn dữ liệu hợp lệ

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES
    (10, 'an@example.test', 'An (tenant 10)'),
    (20, 'an@example.test', 'An (tenant 20)');
```

Cả hai hàng hợp lệ vì `tenant_id` khác nhau.

### 11.4. Chèn trùng live trong cùng tenant bị từ chối

```sql
-- Không chạy nếu muốn giữ lab liền mạch: lệnh này sẽ lỗi 23505.
-- INSERT INTO partial_idx_lab.contacts
--     (tenant_id, email, display_name)
-- VALUES (10, 'AN@example.test', 'An duplicated');
```

PostgreSQL sẽ phát hiện xung đột unique của các entry thỏa predicate `deleted_at IS NULL`. Lỗi điển hình:

```text
SQLSTATE 23505 — unique_violation
```

Vì ràng buộc được thực thi bởi database, hai transaction đồng thời cố chèn cùng khóa live không được phép cùng commit hai hàng live vi phạm unique index.

### 11.5. Sau soft delete, có thể dùng lại email

```sql
UPDATE partial_idx_lab.contacts
SET deleted_at = TIMESTAMPTZ '2026-11-14 12:00:00+07'
WHERE tenant_id = 10
  AND lower(email) = 'an@example.test'
  AND deleted_at IS NULL;

INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'AN@example.test', 'An đăng ký lại');
```

Bản ghi cũ đã ra khỏi tập `deleted_at IS NULL`. Bản ghi mới có thể trở thành contact live duy nhất của tenant 10 mang email này.

### 11.6. Khôi phục contact cũ có thể vi phạm uniqueness

Nếu thử đặt `deleted_at = NULL` cho bản ghi đã xóa mềm trong khi contact live mới cùng tenant/email vẫn tồn tại, PostgreSQL sẽ từ chối do unique partial index.

Điều này là đúng theo bất biến: **không thể có hai contact live cùng email trong cùng tenant**.

### 11.7. Partial UNIQUE index không phải UNIQUE constraint bình thường

PostgreSQL không cho viết một `UNIQUE` table constraint kèm `WHERE` theo đúng kiểu partial index. Thực thể ta tạo bằng:

```sql
CREATE UNIQUE INDEX ... WHERE ...;
```

là **unique partial index**.

Không mặc định có thể dùng tên partial index ở mọi nơi hệ thống yêu cầu một **constraint name**. Ví dụ `ON CONFLICT ON CONSTRAINT contacts_live_email_uq` không phải cách diễn đạt mặc định cho partial unique index này, vì nó không phải unique constraint được khai báo theo dạng đó.

---

## 12. INSERT ... ON CONFLICT với partial unique index

PostgreSQL cho phép chỉ định **conflict target** gồm cột/biểu thức và **index predicate** để suy ra arbiter index tương ứng.

### 12.1. Chỉ xử lý xung đột contact chưa xóa

Ví dụ chỉ muốn không chèn trùng contact live:

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'an@example.test', 'Tên mới')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO NOTHING;
```

Phần:

```sql
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
```

giúp **inference** index unique có khóa `(tenant_id, lower(email))` và predicate phù hợp.

Nếu có contact live cùng email, `DO NOTHING` bỏ qua chèn. Nếu chỉ có contact **đã soft delete**, nó không gây xung đột theo partial index, nên vẫn có thể tạo contact live mới.

### 12.2. Vì sao không dùng ON CONFLICT ON CONSTRAINT?

`ON CONFLICT ON CONSTRAINT constraint_name` yêu cầu tên ràng buộc có loại được hỗ trợ. Một partial unique index tạo qua `CREATE UNIQUE INDEX ... WHERE ...` thường **không phải** một ràng buộc unique mang tên có thể dùng trong cấu trúc này.

Với partial unique index, hãy dùng conflict target theo **cột/biểu thức và predicate** để hỗ trợ index inference như ví dụ.

### 12.3. Đừng bỏ predicate khi inference không còn rõ

```sql
-- Không phải cách mô tả đầy đủ partial unique arbiter:
-- ON CONFLICT (tenant_id, lower(email)) DO NOTHING
```

Nếu chỉ có partial unique index và không có unique index bao phủ toàn bộ cặp khóa, một conflict target thiếu predicate **có thể không suy ra được arbiter phù hợp** và gây lỗi không tìm thấy unique/exclusion constraint phù hợp.

Ngược lại, nếu tồn tại một unique index **không partial** trên cùng khóa, PostgreSQL cũng có thể suy ra nó tùy conflict target. Vì vậy luôn kiểm tra **toàn bộ index hiện có** và mô hình uniqueness, không chỉ đọc một dòng `ON CONFLICT`.

### 12.4. ON CONFLICT không biến uniqueness thành khóa toàn hệ thống

Với index trên `(tenant_id, lower(email))`, email giống nhau ở **tenant khác** không xung đột. Bỏ tenant khỏi conflict target hoặc khỏi unique index sẽ thay đổi bất biến.

Trong hệ thống multi-tenant, tính đúng đắn của điều kiện uniqueness và phân quyền tenant là hai vấn đề khác nhau. Index bảo vệ **trùng khóa**, không tự phân quyền người dùng được xem/sửa contact của tenant nào.

---

## 13. Partial index và dữ liệu active / soft delete

Partial index cho các hàng còn hiệu lực là một mẫu sử dụng phổ biến:

```sql
CREATE INDEX contacts_live_lookup_idx
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Nhưng vì `contacts_live_email_uq` đã là **unique partial index** trên cùng khóa và predicate, nó cũng có thể hỗ trợ tra cứu theo biểu thức ấy. Trên lab này, **không cần tạo thêm** index gần như trùng lặp chỉ để SELECT.

### 13.1. Query phù hợp

```sql
SELECT contact_id, display_name
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

Query vừa suy ra predicate **`deleted_at IS NULL`**, vừa có điều kiện phù hợp với biểu thức index key **`lower(email)`**.

### 13.2. Query không có guard soft delete

```sql
SELECT contact_id, display_name
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND lower(email) = 'an@example.test';
```

Câu này có thể trả **cả contact đã xóa mềm**. Partial index live không bao phủ đầy đủ kết quả vì query không ràng buộc `deleted_at IS NULL`.

Đừng vì muốn dùng index mà tự động thêm guard nếu endpoint thật sự cần trả lịch sử; trước hết phải xác định yêu cầu dữ liệu.

### 13.3. Query so sánh trực tiếp email

```sql
SELECT contact_id
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND email = 'an@example.test';
```

Query này có predicate phù hợp, nhưng điều kiện **`email = ...`** không hoàn toàn giống biểu thức **`lower(email)`** trong index key. PostgreSQL có thể vẫn xem xét index để thu hẹp theo `tenant_id` rồi lọc email, nhưng không nên giả định tìm kiếm case-sensitive qua `email` tận dụng được toàn bộ key expression `lower(email)`.

**Tách hai câu hỏi:** hàng query có nằm trong index không, và **cột/biểu thức tra cứu** có khớp cấu trúc key để tìm nhanh không?

---

## 14. Điều kiện thời gian động: vì sao WHERE now() dễ sai?

Một ý tưởng dễ gặp:

> “Tôi chỉ truy vấn các job tạo trong bảy ngày gần đây; hãy index những hàng mới hơn `now() - interval '7 days'`.”

Có người muốn tạo:

```sql
-- KHÔNG HỢP LỆ vì predicate dùng hàm theo thời gian thay đổi:
-- CREATE INDEX jobs_last_week_idx
-- ON partial_idx_lab.jobs (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
```

### 14.1. Tại sao PostgreSQL không chấp nhận?

Index predicate cần biểu thức phù hợp yêu cầu **tính bất biến (immutability)** khi duy trì các entry index. `now()` thay đổi theo thời gian giữa các transaction (dù ổn định trong một transaction) và không được xem là immutable.

Nếu index tự định nghĩa “bảy ngày gần đây” dựa vào đồng hồ, một hàng hôm nay còn trong index nhưng tuần sau sẽ không còn phù hợp **dù không có UPDATE nào trên hàng đó**. PostgreSQL không có cơ chế tự di chuyển entry ra khỏi index chỉ vì thời gian trôi qua.

Do đó, dùng `now()` hoặc `CURRENT_DATE` làm predicate để tạo một cửa sổ thời gian trượt **không phải cách hợp lệ**.

### 14.2. Predicate với cutoff cố định

Một chỉ mục có thể dùng mốc cố định:

```sql
CREATE INDEX jobs_since_november_idx
ON partial_idx_lab.jobs (created_at)
WHERE created_at >=
    TIMESTAMPTZ '2026-11-01 00:00:00+00';
```

Hàng nào có `created_at` từ mốc này trở đi sẽ được index. Nhưng **mốc không tự chạy theo đồng hồ**. Sau vài tháng, index có thể không còn phản ánh tập “mới đây” mà ứng dụng thực sự quan tâm.

### 14.3. Chiến lược thay thế cho cửa sổ trượt

Tùy workload:

- Một B-tree thông thường trên `created_at` nếu truy vấn range thời gian phổ biến.
- Partitioning theo ngày/tháng với partition pruning và vòng đời partition nếu phù hợp.
- BRIN cho bảng lớn, dữ liệu thời gian có tương quan tốt với vị trí vật lý.
- Một cột trạng thái nghiệp vụ như `is_recent_bucket` được **cập nhật chủ động** nếu thiết kế chấp nhận việc duy trì.
- Định kỳ thay một partial index với **cutoff literal mới** bằng quy trình triển khai có kiểm soát, không tự coi predicate là động.

Không có một lựa chọn tối ưu cho mọi bảng; cần đánh giá quy mô, tần suất cập nhật, retention, cách lọc và chi phí bảo trì.

### 14.4. Hàm do người dùng tự định nghĩa

Không đánh dấu một hàm phụ thuộc đồng hồ, session, bảng khác hoặc cấu hình thay đổi là `IMMUTABLE` chỉ để PostgreSQL cho tạo partial index. Làm vậy có thể khiến index sai về mặt ngữ nghĩa và dẫn tới kết quả truy vấn không đáng tin.

Độ biến động hàm phải phản ánh **thực sự** cùng đầu vào luôn cho cùng kết quả theo yêu cầu của PostgreSQL, không phải chỉ là một nhãn để qua kiểm tra DDL.

---

## 15. Predicate phức tạp và giới hạn suy luận

### 15.1. Đừng kỳ vọng planner chứng minh mọi logic nghiệp vụ

Ví dụ ứng dụng định nghĩa “active job” là trạng thái thuộc một nhóm và một tập quy tắc về completed_at. Bạn có thể viết:

```sql
CREATE INDEX jobs_active_complex_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status IN ('queued', 'running')
  AND completed_at IS NULL;
```

Một query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 2
  AND completed_at IS NULL;
```

về logic nằm trong tập được index, nhưng **không nên coi mọi dạng diễn đạt phức tạp là planner chắc chắn chứng minh được**. Với workload quan trọng, hãy xem `EXPLAIN` và cân nhắc viết predicate theo dạng dễ đối chiếu trong query.

### 15.2. Khớp cấu trúc biểu thức dễ hơn chứng minh tương đương

Ví dụ partial index:

```sql
CREATE INDEX jobs_priority9_idx
ON partial_idx_lab.jobs (tenant_id, job_id)
WHERE priority = 9;
```

Query có:

```sql
WHERE priority = 9
  AND tenant_id = 2
```

thường dễ nhận diện hơn cách viết logic tương đương thông qua một hàm tự định nghĩa hoặc phép biến đổi đại số.

### 15.3. Giữ predicate ổn định giữa DDL và query

Một chiến lược thực dụng:

1. Định nghĩa predicate ngắn, rõ, ít biến đổi.
2. Ghi đúng điều kiện lựa chọn trong query nghiệp vụ, có kiểu dữ liệu rõ ràng.
3. Không giấu điều kiện sau những biểu thức không cần thiết.
4. Đo `EXPLAIN` cho query production thực tế với tham số thật và chế độ plan thật.
5. Không hy sinh ngữ nghĩa SQL chỉ để tạo điều kiện khớp index.

### 15.4. Constraint và functional dependency

Giả sử schema có `CHECK (status='done' => completed_at IS NOT NULL)` bằng một biểu thức tương ứng. Điều đó giúp **đảm bảo dữ liệu**, nhưng planner không phải bộ suy luận tổng quát kết hợp mọi constraint và phép biến đổi để tìm partial index.

Đừng kỳ vọng “vì trong database không thể có queued với completed_at khác NULL” nên mọi query `WHERE status='queued'` sẽ chắc chắn dùng index `WHERE completed_at IS NULL`. Viết predicate khớp query hoặc đo khả năng planner chứng minh trên phiên bản/cấu trúc thực.

---

## 16. Partial index trên nhiều tenant: phạm vi và bảo mật

Với ứng dụng multi-tenant, ví dụ:

```sql
CREATE INDEX jobs_queued_tenant_run_after_idx
ON partial_idx_lab.jobs (tenant_id, run_after, priority DESC, job_id)
WHERE status = 'queued';
```

là một index chung cho queued của **nhiều tenant**. Nó không tự đặt giới hạn truy cập.

### 16.1. Query phải có tenant guard

```sql
SELECT job_id, tenant_id, run_after
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
ORDER BY run_after;
```

Điều kiện `tenant_id=2` giúp truy vấn chỉ lấy tenant cần thiết và tận dụng cột dẫn đầu của index.

**Nhưng:** PostgreSQL index **không phải cơ chế authorization**. Một role có quyền SELECT trên toàn bảng và không có RLS vẫn có thể truy vấn tenant khác. Cần áp dụng quyền, policy và kiểm soát ứng dụng độc lập với chiến lược index.

### 16.2. Có nên tạo một partial index cho mỗi tenant?

Một ý tưởng:

```sql
-- Ví dụ tạo index cực kỳ chuyên biệt:
-- CREATE INDEX jobs_tenant2_queued_idx
-- ON partial_idx_lab.jobs (run_after)
-- WHERE tenant_id = 2 AND status = 'queued';
```

Có thể hợp lý trong một số trường hợp dữ liệu không cân đối và tenant nóng đặc biệt, nhưng thường gây khó khăn nếu có hàng nghìn tenant:

- Rất nhiều index cần tạo, cập nhật, vacuum/reindex và quản lý.
- Planner phải xem xét nhiều lựa chọn.
- Workload thay đổi khi tenant tăng/giảm.
- Mỗi INSERT/UPDATE có thể phải đánh giá predicate của nhiều index.

Đa số hệ thống nhiều tenant nên bắt đầu từ **ít index chung có cột tenant dẫn đầu**, sau đó đo hotspot để quyết định chỉ mục chuyên biệt nếu thật sự cần.

### 16.3. Partial index và RLS

Row-Level Security có thể giới hạn những hàng role được xem, nhưng không đồng nghĩa planner luôn có thể suy ra predicate partial index chỉ từ policy hay context tenant.

Không dựa vào index làm lớp bảo mật. Khi phân tích kế hoạch truy vấn dưới RLS, cần thử với **role và policy thật**, vì cách biểu thức được lập kế hoạch có thể phụ thuộc security barriers và các quy tắc optimizer.

---

## 17. Partial index, covering index và index-only scan

### 17.1. INCLUDE dùng để bổ sung cột đọc

Giả sử truy vấn thường lấy `job_id, tenant_id, run_after, priority, created_at` nhưng chỉ lọc và sắp xếp theo những khóa đầu:

```sql
CREATE INDEX jobs_queued_covering_idx
ON partial_idx_lab.jobs
    (tenant_id, run_after, priority DESC, job_id)
INCLUDE (created_at)
WHERE status = 'queued';
```

Trong index này:

- Các cột trong `(...)` là **key columns**.
- `created_at` là một cột **INCLUDE** (payload của index), không phải khóa sắp xếp/tra cứu.
- Predicate vẫn chỉ nhận hàng queued.

### 17.2. Khi nào có thể có Index Only Scan?

Một truy vấn chỉ cần các cột được index lưu:

```sql
SELECT job_id, tenant_id, run_after, priority, created_at
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

có thể sử dụng **Index Only Scan** nếu planner thấy phù hợp và có đủ thông tin về visibility. Tuy nhiên, PostgreSQL vẫn phải tôn trọng MVCC: kiểm tra **visibility map** hoặc truy cập heap khi cần.

Không khẳng định “đã INCLUDE đủ cột thì chắc chắn không đọc heap”. Nếu bảng thường xuyên được cập nhật và các trang chưa all-visible, Index Only Scan có thể phải heap fetch nhiều.

### 17.3. Chi phí của INCLUDE

INCLUDE làm entry index lớn hơn, tăng dung lượng và chi phí duy trì khi ghi. Với dữ liệu lớn như `payload JSONB`, không tự thêm vào index chỉ để cố có Index Only Scan; kiểu/giới hạn kích thước index tuple và workload có thể khiến điều đó không phù hợp.

### 17.4. Tránh index trùng lặp

Nếu đã có:

```sql
jobs_queued_tenant_run_after_idx
```

và bạn tạo thêm:

```sql
jobs_queued_covering_idx
```

với cùng key và predicate, sự khác biệt chỉ ở cột INCLUDE. Trong production, cần xem có nên **thay** index cũ bằng index mới hoặc chỉ giữ một index phù hợp, thay vì duy trì cả hai vô thời hạn.

**Trong lab**, cả hai có thể được tạo để quan sát `EXPLAIN`; khi đo hiệu năng thật cần kiểm soát index dư.

---

## 18. Chi phí INSERT, UPDATE và DELETE của partial index

Partial index **không miễn phí**, ngay cả khi nhỏ hơn index toàn bảng.

### 18.1. INSERT

Với mỗi hàng mới, PostgreSQL cần xác định predicate của từng index có thỏa hay không:

```text
INSERT status='done'
    -> không thêm entry vào jobs_queued...

INSERT status='queued'
    -> thêm entry vào jobs_queued...
```

Đây là sơ đồ khái niệm. Hàng mới vẫn có thể đi vào những index khác như PK.

### 18.2. UPDATE khiến hàng đi vào hoặc rời index

Ví dụ job chuyển `queued → running`:

```sql
BEGIN;

UPDATE partial_idx_lab.jobs
SET status = 'running'
WHERE job_id = 1
  AND status = 'queued';

ROLLBACK;
```

Nếu `job_id=1` không phải queued trong dữ liệu seed, câu trên có thể `UPDATE 0`; mục đích là minh họa logic, không ép một trạng thái cụ thể.

Về mặt chỉ mục queued:

```text
queued -> running:
    hàng rời khỏi tập thỏa predicate.

running -> queued:
    hàng bắt đầu tham gia partial index.
```

Các thay đổi này tạo công việc duy trì chỉ mục/WAL và có thể ảnh hưởng HOT updates.

### 18.3. HOT update và predicate columns

PostgreSQL có cơ chế **Heap-Only Tuple (HOT)** cho một số UPDATE khi các điều kiện về cột/index và không gian trang cho phép. Nếu UPDATE thay đổi cột được tham chiếu bởi **index key, expression index hoặc partial-index predicate** theo cách ảnh hưởng cập nhật index, cơ hội HOT có thể giảm hoặc không còn.

Đừng kết luận “vì hàng done không có entry trong partial index queued nên mọi UPDATE status của nó chắc chắn là HOT”. Việc một cột xuất hiện trong predicate vẫn liên quan tới khả năng cần bảo trì index và quy tắc HOT.

### 18.4. DELETE

DELETE làm thay đổi khả năng tồn tại của tuple và các entry index tương ứng. Theo MVCC, không phải lúc nào dung lượng vật lý của bảng/index giảm ngay sau DELETE; VACUUM/autovacuum sẽ dọn dẹp và tái sử dụng theo điều kiện phù hợp.

### 18.5. Khi partial index ít lợi

Nếu phần lớn hàng thỏa predicate, ví dụ 95% hàng có `status='active'`, partial index theo `status='active'` có thể **gần bằng index toàn bảng** về số entry, nhưng vẫn thêm chi phí đánh giá predicate và làm phạm vi query sử dụng nó chặt hơn.

Partial index hữu ích nhất khi **tập hàng được index và tập truy vấn thường gặp đủ tập trung**, không phải cứ có WHERE là nên dùng.

---

## 19. Thống kê, kích thước và mức sử dụng chỉ mục

### 19.1. Xem các index đã tạo

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partial_idx_lab'
ORDER BY tablename, indexname;
```

`indexdef` giúp xác nhận:

- Bảng và cột/biểu thức key.
- Predicate `WHERE ...`.
- `UNIQUE` hay không.
- Phương pháp truy cập như B-tree.
- Cột INCLUDE nếu có.

Không chỉ tin tên index; hãy đọc DDL thực.

### 19.2. So sánh kích thước index

```sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
WHERE n.nspname = 'partial_idx_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Lệnh cho kích thước vật lý hiện tại của các quan hệ index trong schema. Kích thước bị ảnh hưởng bởi cấu trúc trang, số hàng, bloat và lịch sử cập nhật; không đồng nhất với tỷ lệ số hàng thỏa predicate.

### 19.3. Số lần scan và tuple đọc

```sql
SELECT
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'partial_idx_lab'
ORDER BY relname, indexrelname;
```

Các giá trị là **thống kê tích lũy**, có thể thay đổi giữa các thời điểm và bị reset theo quy trình hệ thống. Cần xem cùng:

- Thời gian quan sát.
- Độ lớn/đặc tính workload.
- Kế hoạch từ `EXPLAIN`.
- Số lần cập nhật bảng và chi phí duy trì index.

Một index có `idx_scan` thấp **không tự động là index dư**: partial unique index có thể tồn tại chủ yếu để **bảo vệ tính đúng đắn khi ghi**, không phải chỉ để tăng tốc SELECT.

### 19.4. Thống kê cột và sự phân bố

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'partial_idx_lab'
  AND tablename = 'jobs'
  AND attname IN ('status', 'tenant_id', 'priority');
```

Thông tin này giúp hiểu planner đang ước lượng các predicate như `status='queued'` ra sao.

Khi dữ liệu thay đổi mạnh (ví dụ job liên tục chuyển trạng thái), phân bố và thống kê có thể thay đổi. Autovacuum/autonalyze cập nhật thống kê theo cơ chế server; với bulk load hoặc thử nghiệm, có thể chạy `ANALYZE` có kiểm soát.

---

## 20. Triển khai partial index trên bảng đang hoạt động

### 20.1. CREATE INDEX thông thường có thể gây blocking

```sql
CREATE INDEX jobs_queued_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status = 'queued';
```

Khi tạo index trên bảng lớn có nhiều ghi đồng thời, việc tạo index theo cách thường có ảnh hưởng khóa và thời gian triển khai. Không tự đưa lệnh DDL này vào giờ cao điểm chỉ vì nó chạy nhanh trên bảng lab.

### 20.2. CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ:

```sql
CREATE INDEX CONCURRENTLY jobs_queued_concurrent_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status = 'queued';
```

`CONCURRENTLY` được dùng để giảm chặn hoạt động ghi trong lúc xây index, nhưng:

- Có thể mất nhiều thời gian hơn và dùng tài nguyên.
- Có quy tắc chờ transaction/snapshot đang tồn tại.
- **Không được chạy bên trong transaction block tường minh** như `BEGIN; ... COMMIT;`.
- Nếu tạo thất bại, có thể để lại một index **invalid** cần đánh giá và dọn theo quy trình.
- Vẫn cần lên kế hoạch năng lực, theo dõi tiến độ và nguy cơ tranh chấp.

Không lấy chữ “concurrently” làm bảo đảm hoàn toàn không có lock hay tác động hiệu năng.

### 20.3. Thay predicate không phải chỉ sửa một biến

Predicate là một phần định nghĩa index. Muốn đổi từ:

```sql
WHERE status = 'queued'
```

sang:

```sql
WHERE status IN ('queued', 'running')
```

cần **thiết kế lại/tạo index tương ứng** và chuyển workload an toàn. PostgreSQL không tự biến index cũ thành index có predicate mới chỉ vì ứng dụng thay WHERE.

Đặc biệt với unique partial index, chuyển predicate có thể làm **nhiều hàng cũ vốn hợp lệ trở thành xung đột unique**. Phải kiểm tra dữ liệu trước khi áp quy tắc mới.

### 20.4. Kiểm tra index validity và tiến độ

Ví dụ xem trạng thái catalog:

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c ON c.oid = i.indexrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'partial_idx_lab'
ORDER BY c.relname;
```

Khi tạo index concurrently trên bảng lớn, có thể tham khảo `pg_stat_progress_create_index` nếu phiên bản hỗ trợ. Các thuộc tính internal khác của index cần được diễn giải theo tài liệu, không xem `indisvalid=false` đơn thuần là “server tự sửa sau vài giây”.

---

## 21. Partial index không phải partitioning

Hai cơ chế đều có thể tập trung truy cập vào một phần dữ liệu, nhưng khác bản chất:

| Tiêu chí | Partial index | Partitioning |
|---|---|---|
| Dữ liệu bảng | Vẫn ở bảng được đánh index | Hàng được phân bố theo partition |
| Predicate | Xác định **entry trong index** | Quy tắc phân vùng hàng |
| Truy vấn | Planner có thể dùng index nếu query suy ra predicate | Planner có thể prune partition nếu điều kiện phù hợp |
| Quản lý retention | Không tự loại hàng cũ khỏi bảng | Có thể quản lý theo partition ở một số mô hình |
| DDL và vận hành | Quản lý index/uniqueness | Quản lý partition, constraints, indexes |
| Chi phí ghi | Đánh giá predicate và bảo trì index | Route hàng đến partition và bảo trì các index của partition |

Một bảng partitioned cũng có thể có index phù hợp trên các partition. Hai kỹ thuật **có thể bổ sung cho nhau**, nhưng không thay thế vô điều kiện.

### 21.1. Khi nào ưu tiên partitioning?

Nếu yêu cầu chính là:

- Lưu lịch sử cực lớn theo tháng/năm.
- Xóa/archival **toàn bộ một giai đoạn** theo quy tắc rõ.
- Hầu hết truy vấn có điều kiện partition key.
- Quản lý lifecycle của dữ liệu là vấn đề trọng tâm.

thì partitioning có thể phù hợp. Một partial index kiểu “created_at gần đây” với cutoff cố định không tự thay thế vòng đời partition.

### 21.2. Khi nào partial index nổi bật?

Nếu trong mỗi partition/bảng, chỉ vài phần trăm hàng có `status='queued'` hoặc `deleted_at IS NULL`, partial index có thể cung cấp đường truy cập tập trung cho những hàng được đọc thường xuyên.

Nhưng vẫn cần đánh giá query predicates, số lần update status và kế hoạch thực tế.

---

## 22. Những sai lầm thường gặp

**1. “Partial index có WHERE nhưng SELECT tự thêm WHERE đó.”** Sai. SELECT vẫn trả hàng theo điều kiện riêng; index không thay semantics.

**2. “Partial index trên queued luôn giúp query mọi trạng thái.”** Sai. Index thiếu hàng done/running/failed.

**3. “Nếu một query có điều kiện mạnh hơn predicate, index bắt buộc được dùng.”** Sai. Planner còn so chi phí và index key.

**4. “PostgreSQL có thể chứng minh mọi biểu thức logic tương đương.”** Sai. Bộ suy luận chỉ nhận ra một số dạng dễ chứng minh.

**5. “status IN ('queued','running') suy ra status='queued'.”** Sai. Running là phản ví dụ.

**6. “WHERE status='queued' OR priority=9 suy ra queued.”** Sai. Nhánh priority có thể lấy trạng thái khác.

**7. “WHERE status='queued' AND tenant_id=2 không dùng được partial index.”** Sai. Nó suy ra predicate queued.

**8. “Đổi hướng suy luận P ⇒ Q là đủ.”** Sai. Cần **Q ⇒ P**: query phải không yêu cầu hàng ngoài index.

**9. “Thêm status vào index key là bắt buộc vì status xuất hiện trong predicate.”** Sai. Predicate và key là hai vai trò.

**10. “Chỉ cần SQL đúng logic thì planner chắc chắn hiểu mọi phép biến đổi.”** Không. Xem `EXPLAIN`.

**11. “Đặt status=$1 vẫn cho generic plan giả định $1='queued'.”** Sai. Generic plan phải hợp lệ với mọi giá trị tham số.

**12. “Prepared statement không bao giờ có thể dùng partial index.”** Quá tuyệt đối. Custom plan có thể xét giá trị tham số và chọn index phù hợp; cần đo.

**13. “force_custom_plan luôn nhanh hơn.”** Không. Tạo plan theo giá trị tham số có chi phí; planner vẫn có thể chọn kế hoạch khác.

**14. “IS NULL giống = NULL.”** Sai. So sánh `= NULL` không cho kết quả TRUE như mong muốn.

**15. “WHERE NOT is_active luôn tương đương IS NOT TRUE.”** Sai nếu boolean nullable: `IS NOT TRUE` bao gồm NULL.

**16. “Index WHERE deleted_at IS NULL dùng cho mọi query theo email.”** Sai nếu query muốn cả hàng đã soft delete.

**17. “UNIQUE (tenant_id, email) luôn tương đương UNIQUE partial theo deleted_at.”** Không. Partial uniqueness chỉ áp cho tập live.

**18. “Partial unique index chỉ tăng tốc SELECT, không bảo vệ ghi đồng thời.”** Sai. Unique index thực thi uniqueness cho tập hàng thỏa predicate.

**19. “ON CONFLICT ON CONSTRAINT luôn dùng được tên partial unique index.”** Không. Partial unique index không phải unique table constraint cùng dạng.

**20. “ON CONFLICT bỏ predicate vẫn luôn suy ra partial unique arbiter.”** Không chắc và có thể báo không có arbiter phù hợp.

**21. “Một unique index trên lower(email) tự biến mọi so sánh email thành case-insensitive.”** Không. Query sử dụng `email=...` và `lower(email)=...` có semantics/khả năng dùng key khác nhau.

**22. “now() trong predicate là hợp lệ vì thời gian chỉ đổi sau mỗi transaction.”** Sai. Partial-index predicate cần tính bất biến phù hợp; `now()` không IMMUTABLE.

**23. “Index với cutoff ngày cố định tự trở thành rolling 7 days.”** Sai. Predicate không tự thay đổi khi đồng hồ chạy.

**24. “Tạo partial index một cái cho mỗi tenant luôn tối ưu.”** Không. Số index lớn gây chi phí quản lý và ghi.

**25. “Index là hàng rào bảo mật tenant.”** Sai. Cần role/RLS và query guard.

**26. “Có INCLUDE đủ cột là đảm bảo Index Only Scan không heap fetch.”** Sai. MVCC visibility map và planner vẫn quan trọng.

**27. “Một index có idx_scan thấp thì chắc chắn nên drop.”** Không. Unique partial index có thể tồn tại để bảo vệ constraint và thống kê phụ thuộc workload.

**28. “Tạo thêm index luôn giúp ghi nhanh hơn.”** Sai. INSERT/UPDATE/DELETE phải duy trì index.

**29. “Chuyển status không làm thay đổi index vì status không phải key.”** Sai. Status ở predicate quyết định hàng có tham gia index.

**30. “Vì một hàng không nằm trong partial index nên UPDATE của nó luôn HOT.”** Không. Predicate dependencies và các index khác ảnh hưởng HOT eligibility.

**31. “CREATE INDEX CONCURRENTLY có thể chạy trong BEGIN.”** Sai. PostgreSQL không cho thực thi bên trong transaction block tường minh.

**32. “CONCURRENTLY bảo đảm hoàn toàn không có ảnh hưởng tải/lock.”** Sai. Nó có chi phí và quy tắc chờ.

**33. “Thay WHERE trong query làm đổi predicate index đã tạo.”** Sai. Cần tạo index mới theo định nghĩa mới.

**34. “EXPLAIN ANALYZE chỉ xem kế hoạch không thực thi SQL.”** Sai. Nó chạy statement; dùng SELECT lab hoặc transaction kiểm soát khi đo DML.

**35. “Index nhỏ hơn luôn làm query nhanh hơn.”** Không. Còn phụ thuộc index key, chọn lọc, ORDER BY, heap fetch và chi phí planner.

**36. “Partial index thay được partitioning cho mọi bài toán retention.”** Không. Nó không xóa hoặc tách dữ liệu khỏi bảng.

---

## 23. Bài tập thực hành có lời giải

### Bài 1 — Nhận diện phần key và predicate

Cho:

```sql
CREATE INDEX jobs_queue_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status='queued';
```

**Hỏi:** đâu là index key và đâu là predicate?

**Đáp án:** `(tenant_id, run_after)` là key; `status='queued'` là predicate. `status` không cần nằm trong key.

### Bài 2 — Q ⇒ P

Predicate `P: status='queued'`. Query `Q: status='queued' AND tenant_id=3`.

**Đáp án:** `Q ⇒ P` là đúng vì mọi hàng thỏa Q đều queued; partial index có thể được xem xét.

### Bài 3 — OR phá suy luận

```sql
WHERE status='queued' OR priority=9
```

**Đáp án:** Không suy ra `status='queued'`. Hàng done với priority 9 vẫn thỏa Q.

### Bài 4 — Bất đẳng thức

Index predicate `priority < 8`. Query `priority < 4`.

**Đáp án:** Query là tập con của predicate vì `priority < 4 ⇒ priority < 8`. PostgreSQL có thể nhận diện so sánh bất đẳng thức đơn giản.

### Bài 5 — Bất đẳng thức ngược

Index predicate `priority < 8`. Query `priority < 10`.

**Đáp án:** Không suy ra, vì giá trị priority 8 hoặc 9 là phản ví dụ.

### Bài 6 — Tạo index cho queued

**Yêu cầu:** truy vấn queued theo tenant và run_after; viết partial index.

**Đáp án:**

```sql
CREATE INDEX jobs_queue_lookup_ex_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status='queued';
```

Trên lab đã có `jobs_queued_tenant_run_after_idx` phục vụ mục đích gần giống; đây chỉ là bài tập cú pháp. Trong production cần đánh giá trùng lặp trước khi giữ cả hai.

### Bài 7 — Truy vấn theo cùng predicate

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND status='queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

**Đáp án:** Query suy ra `status='queued'`. Chạy `EXPLAIN` để biết index có được chọn theo chi phí không.

### Bài 8 — Thiếu trạng thái

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

**Đáp án:** Không suy ra queued. Query còn cần mọi trạng thái có cùng tenant và thời gian, nên partial index queued không bao phủ đầy đủ kết quả.

### Bài 9 — Prepared statement generic

```sql
PREPARE q(TEXT) AS
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status=$1;
```

**Hỏi:** generic plan có thể luôn dùng index `WHERE status='queued'` không?

**Đáp án:** Không. `$1` có thể là `done`. Một generic plan phải đúng cho mọi giá trị.

### Bài 10 — Prepared statement custom

**Hỏi:** custom plan cho `$1='queued'` có thể xem xét partial index queued không?

**Đáp án:** Có thể, nếu giá trị tham số được biết lúc planning và predicate được nhận diện. Nhưng planner còn xét chi phí; dùng `EXPLAIN EXECUTE` để quan sát thực tế.

### Bài 11 — Cố định predicate trong SQL

**Yêu cầu:** thiết kế query chỉ lấy queued, nhưng bind tenant và cutoff.

**Đáp án:**

```sql
PREPARE q_queued(INTEGER, TIMESTAMPTZ) AS
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status='queued'
  AND tenant_id=$1
  AND run_after<$2;
```

`status='queued'` là điều kiện hằng thuộc hợp đồng endpoint; các đầu vào khác vẫn được bind.

### Bài 12 — Partial unique index

**Yêu cầu:** trong một tenant, email live không được trùng theo `lower(email)`, còn email đã soft delete được giữ lịch sử.

**Đáp án:**

```sql
CREATE UNIQUE INDEX contacts_live_email_uq_ex
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Bảng lab đã có unique partial index `contacts_live_email_uq` cùng định nghĩa; không cần giữ thêm một index trùng. Lệnh đáp án nhằm diễn đạt cú pháp.

### Bài 13 — Soft delete và uniqueness

**Câu hỏi:** Nếu contact tenant 10/email X đã `deleted_at IS NOT NULL`, có thể thêm một contact live cùng email X không?

**Đáp án:** Có, theo partial unique index chỉ bao phủ `deleted_at IS NULL`, miễn không có **contact live** khác cùng cặp `(tenant_id, lower(email))`.

### Bài 14 — ON CONFLICT với partial unique

**Đáp án gợi ý:**

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'an@example.test', 'Test')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO NOTHING;
```

Chú ý conflict target phải phù hợp định nghĩa arbiter index.

### Bài 15 — NULL

Predicate `P: completed_at IS NULL`. Query `Q: completed_at IS NULL AND tenant_id=3`.

**Đáp án:** `Q ⇒ P` đúng. Trái lại `WHERE completed_at = NULL` không phải phép kiểm tra NULL hợp lệ.

### Bài 16 — Hàm thời gian

```sql
-- CREATE INDEX ... WHERE created_at > now()-INTERVAL '7 days';
```

**Hỏi:** tại sao không hợp lệ?

**Đáp án:** `now()` không IMMUTABLE; index predicate không thể tự cập nhật membership chỉ vì thời gian trôi. Cân nhắc index toàn bảng trên created_at, partitioning/BRIN hoặc cutoff literal với quy trình quản lý rõ.

### Bài 17 — Index chỉ có một tenant

Index:

```sql
CREATE INDEX jobs_tenant2_only_idx
ON partial_idx_lab.jobs (run_after)
WHERE tenant_id=2 AND status='queued';
```

**Hỏi:** truy vấn queued của tenant 3 có thể dùng index này như nguồn đầy đủ không?

**Đáp án:** Không. Index chỉ chứa tenant 2.

### Bài 18 — Vì sao index vẫn có chi phí?

**Đáp án:** PostgreSQL phải đánh giá predicate và bảo trì entry khi INSERT/UPDATE/DELETE; chuyển `queued → running` làm hàng rời tập index; index còn chiếm dung lượng, WAL và có thể ảnh hưởng HOT.

### Bài 19 — Đọc EXPLAIN

**Yêu cầu:** kiểm tra kế hoạch của query queued theo tenant 2.

**Đáp án:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND status='queued'
ORDER BY run_after
LIMIT 20;
```

Đọc Index Cond, Filter, actual/estimated rows và buffers. Không khẳng định tên plan trước khi quan sát.

### Bài 20 — INCLUDE và index-only

**Câu hỏi:** Khi index có INCLUDE(created_at), query lấy created_at có chắc là Index Only Scan không?

**Đáp án:** Không. Nó **có thể đủ dữ liệu cột** cho Index Only Scan nhưng planner và thông tin MVCC visibility map vẫn quyết định số heap fetch và đường truy cập.

### Bài 21 — Chỉ mục không dùng cho truy vấn lịch sử

Một query phải trả cả contact đã xóa mềm:

```sql
SELECT contact_id
FROM partial_idx_lab.contacts
WHERE tenant_id=10
  AND lower(email)='an@example.test';
```

**Đáp án:** Query không suy ra `deleted_at IS NULL`, nên partial index live không chứa đầy đủ kết quả lịch sử.

### Bài 22 — Có thể xem index usage ở đâu?

**Đáp án:** `pg_stat_user_indexes` cung cấp `idx_scan`, `idx_tup_read`, `idx_tup_fetch`; `pg_indexes` hiển thị định nghĩa; `pg_relation_size` cho dung lượng; `EXPLAIN` cho kế hoạch của query cụ thể.

### Bài 23 — Có thể tạo concurrently trong transaction không?

**Đáp án:** Không. `CREATE INDEX CONCURRENTLY` không được phép chạy trong transaction block tường minh; phải triển khai theo quy trình phù hợp và theo dõi trạng thái nếu tạo thất bại.

### Bài 24 — Khi nào partial index không phải lựa chọn tốt?

**Đáp án:** Nếu phần lớn hàng thỏa predicate, query không có điều kiện khớp, status thay đổi quá thường xuyên hoặc muốn giải bài toán retention theo thời gian, một index thông thường/partitioning/BRIN hoặc thiết kế khác có thể phù hợp hơn.

---

## 24. Checklist lựa chọn và vận hành partial index

Trước khi tạo một chỉ mục một phần trong PostgreSQL, hãy tự trả lời:

1. **Workload chính là gì?** Những query nào chạy nhiều nhất, với `WHERE` và `ORDER BY` thực tế?
2. **Tập hàng nóng nhỏ cỡ nào?** Predicate chọn 1%, 5% hay 95% dữ liệu?
3. **Predicate P là gì?** Nó có thể diễn đạt gọn, ổn định, không phụ thuộc thời gian thay đổi không?
4. **Query Q có thực sự suy ra P không?** Kiểm tra bằng phản ví dụ `Q TRUE, P không TRUE`.
5. **Planner có thể nhận ra suy luận không?** Ưu tiên so sánh trực tiếp và biểu thức khớp, tránh dựa vào định lý phức tạp.
6. **Có tham số không?** Generic plan có thể không chứng minh được predicate; đo custom/generic khi cần.
7. **Index key có đúng thứ tự không?** Cột tenant, cột lọc/sắp xếp, điểm dừng của range scan?
8. **Query có ORDER BY/LIMIT không?** Có cơ hội tận dụng thứ tự B-tree?
9. **Cột nullable có ý nghĩa gì?** `IS NULL`, `IS NOT NULL`, `NOT` và logic ba giá trị phải chính xác.
10. **Có cần unique partial index không?** Nếu bảo vệ invariant active/soft-delete, xác định khóa và predicate đúng.
11. **ON CONFLICT có chọn được arbiter index không?** Kiểm tra cột/biểu thức và index predicate.
12. **Có nhiều tenant không?** Index không thay RLS/quyền; tenant guard và isolation vẫn quan trọng.
13. **Có index trùng lặp không?** Một unique index có thể đã phục vụ SELECT; không tạo hai bản tương đương vô ích.
14. **Chi phí ghi thế nào?** Predicate/key changes, HOT eligibility, WAL, kích thước và bloat.
15. **Có cần INCLUDE không?** Có cân bằng lợi ích index-only và chi phí index phình to?
16. **Có dùng thời gian trượt không?** Không sử dụng `now()` trong index predicate; chọn giải pháp có lifecycle rõ.
17. **Có thống kê phù hợp không?** `ANALYZE` sau bulk load, hiểu sai lệch ước lượng.
18. **Đã chạy EXPLAIN trên query thật chưa?** Với SQL tham số, kiểm tra loại plan đang áp dụng.
19. **Có kế hoạch triển khai online không?** `CREATE INDEX CONCURRENTLY` có giới hạn và không chạy trong transaction block.
20. **Có giám sát index usage không?** Kết hợp `pg_stat_user_indexes`, kích thước và workload; không drop chỉ vì `idx_scan` thấp.
21. **Có kế hoạch đổi predicate không?** Kiểm tra data conflicts và chuyển index có kiểm soát.
22. **Có lựa chọn khác tốt hơn không?** B-tree toàn bảng, BRIN, partitioning, materialized view hoặc thay đổi query.

---

## 25. Tổng kết

**Partial index** là chỉ mục chỉ chứa những hàng làm **predicate của index** đúng. Nó hữu ích cho các tập dữ liệu nóng như job `queued`, bản ghi `deleted_at IS NULL`, giao dịch chưa đối soát hoặc lỗi cần xử lý. Nhưng hiệu quả của nó phụ thuộc chặt chẽ vào **mối quan hệ giữa bộ lọc truy vấn và predicate**.

Hãy ghi nhớ năm điểm:

1. **Đúng chiều suy luận là `Q ⇒ P`**: mọi hàng query cần đều phải thuộc tập hàng có trong partial index.
2. **Đúng logic chưa đủ**: PostgreSQL chỉ nhận ra một số dạng suy luận, và sau đó planner còn xét chi phí, index key và thống kê.
3. **`AND` thường củng cố predicate, `OR` có thể làm mất predicate** nếu có nhánh chọn hàng ngoài tập index; `NULL` cần ngữ nghĩa ba giá trị.
4. **Generic plan của prepared statement không được giả định tham số là hằng queued**; custom plan có thể khác. Với endpoint thật sự chỉ phục vụ queued, giữ điều kiện `status='queued'` tường minh trong SQL và bind các tham số còn lại.
5. **Partial UNIQUE index vừa tối ưu vừa thực thi quy tắc dữ liệu** như “email chưa xóa mềm là duy nhất trong tenant”, nhưng không thay phân quyền, audit, transaction logic hay quản lý vòng đời index.

**Nguyên tắc cuối:** trước khi thêm một partial index, hãy viết ra hai biểu thức **`P` (predicate của index)** và **`Q` (WHERE của query)**. Tự tìm một hàng thỏa `Q` mà không thỏa `P`. Nếu có hàng phản ví dụ, index không bao phủ toàn bộ query. Nếu không có, hãy kiểm tra planner có nhận diện được điều đó và liệu index có thực sự đáng dùng so với các đường truy cập khác.

### Tài liệu PostgreSQL chính thức

- [Partial Indexes — `11.8`](https://www.postgresql.org/docs/current/indexes-partial.html).
- [CREATE INDEX — Predicate, INCLUDE, UNIQUE và CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html).
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html).
- [PREPARE — Generic và Custom Plans](https://www.postgresql.org/docs/current/sql-prepare.html).
- [INSERT — ON CONFLICT và Index Inference](https://www.postgresql.org/docs/current/sql-insert.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Statistics Collector và Index Usage](https://www.postgresql.org/docs/current/monitoring-stats.html).
