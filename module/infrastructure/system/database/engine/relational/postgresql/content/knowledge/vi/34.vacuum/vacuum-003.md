# ANALYZE và cập nhật thống kê cho bộ lập kế hoạch trong PostgreSQL

## 1. Vì sao PostgreSQL cần thống kê?

Một câu SQL có thể được thực thi theo nhiều cách. Ví dụ:

~~~sql
SELECT order_id, total_amount
FROM app.orders
WHERE customer_id = 1024;
~~~

PostgreSQL có thể chọn **Sequential Scan** (đọc tuần tự bảng), **Index Scan**, **Bitmap Index Scan** hoặc một đường truy cập khác. Nếu query join thêm customers và order_items, planner còn phải chọn thứ tự join, kiểu join, cách sort, hash và khả năng chạy song song.

Để đưa ra quyết định, planner cần ước lượng:

- Bảng có khoảng bao nhiêu rows?
- Có bao nhiêu giá trị khác nhau trong một cột?
- Bao nhiêu rows có giá trị NULL?
- Giá trị nào xuất hiện thường xuyên?
- Một điều kiện WHERE sẽ lọc còn bao nhiêu rows?
- Hai điều kiện trên cùng bảng có tương quan hay gần độc lập?
- Giá trị cột được sắp xếp vật lý gần với thứ tự index tới mức nào?
- Một phép GROUP BY dự kiến sinh bao nhiêu nhóm?
- Dữ liệu rộng bao nhiêu bytes, ảnh hưởng tới sort/hash và memory thế nào?

PostgreSQL không thể suy ra chính xác tất cả điều này chỉ từ cú pháp SQL. Nó duy trì **thống kê dữ liệu** (planner statistics), chủ yếu qua lệnh `ANALYZE` và cơ chế tự động **autovacuum/autoanalyze**.

Nếu thống kê cũ hoặc không đại diện cho phân bố hiện tại, planner có thể chọn kế hoạch kém: đọc cả bảng dù index có ích, dùng nested loop cho một tập rất lớn, hash join với bảng ước lượng quá nhỏ, sort/hash quá nhiều dữ liệu hoặc chọn sai thứ tự join. Query có thể chậm hơn rất nhiều dù SQL và indexes không đổi.

**ANALYZE thu thập thống kê để bộ lập kế hoạch ước lượng dữ liệu.** Nó không sửa dữ liệu nghiệp vụ, không xóa dead tuples và không thay thế VACUUM.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `ANALYZE`, `VACUUM`, `VACUUM ANALYZE` và autoanalyze.
2. Đọc các trường thống kê trong `pg_stats`: `null_frac`, `n_distinct`, MCV, histogram, correlation và average width.
3. Hiểu planner dùng thống kê để ước lượng selectivity, cardinality, join order và scan type như thế nào.
4. Chọn statistics target mặc định hoặc riêng từng cột.
5. Dùng extended statistics để mô tả tương quan giữa nhiều cột và biểu thức.
6. Cập nhật thống kê sau bulk load, backfill, data skew hoặc thay đổi phân bố.
7. Theo dõi thời điểm analyze và tiến trình autoanalyze.
8. Chẩn đoán trường hợp `EXPLAIN` ước lượng sai so với số rows thực tế.
9. Xử lý thống kê cho partitioned tables, inheritance, foreign tables và các đối tượng có đặc thù.
10. Lập kế hoạch analyze không gây ảnh hưởng không cần thiết tới workload đang chạy.

### 1.2. Phạm vi

Bài tập trung vào thống kê cho **planner của PostgreSQL**. Các ví dụ dùng cú pháp SQL PostgreSQL và các catalog/views thông dụng. Một số view, cột thống kê, tính năng expression statistics và chi tiết autoanalyze thay đổi theo major version; hãy kiểm tra tài liệu đúng phiên bản server đang vận hành.

---

## 2. ANALYZE làm gì?

### 2.1. Lệnh cơ bản

~~~sql
ANALYZE app.orders;
~~~

PostgreSQL lấy mẫu dữ liệu của bảng và thu thập thống kê cho các cột phù hợp. Kết quả được lưu trong system catalogs, chủ yếu là `pg_statistic`, và được trình bày qua view `pg_stats`.

Có thể phân tích toàn bộ database:

~~~sql
ANALYZE;
~~~

Hoặc một schema/table cụ thể:

~~~sql
ANALYZE app.orders;
ANALYZE app.customers;
~~~

### 2.2. Chỉ định một số cột

~~~sql
ANALYZE app.orders (customer_id, order_status, created_at);
~~~

Điều này hữu ích khi chỉ một vài cột quan trọng vừa thay đổi phân bố hoặc khi muốn tập trung thu thập stats. Các cột khác không được chỉ định không được cập nhật theo cùng lệnh đó. Hãy cân nhắc extended statistics objects có liên quan và yêu cầu của planner.

### 2.3. Hiển thị thông tin tiến trình

~~~sql
ANALYZE VERBOSE app.orders;
~~~

`VERBOSE` in thêm thông tin về quá trình thu thập thống kê, gồm các thông tin lấy mẫu theo phiên bản. Đây là cách hữu ích để quan sát lệnh thủ công trong môi trường thử nghiệm/maintenance.

### 2.4. ANALYZE không đọc chính xác mọi row

PostgreSQL thường dùng **sampling** (lấy mẫu) thay vì quét và giữ mọi giá trị của mọi row. Thống kê là các ước lượng có cơ sở thống kê, không phải bản đếm chính xác tuyệt đối.

Vì thế:

- Chạy `ANALYZE` hai lần có thể cho số liệu hơi khác nhau.
- Bảng thay đổi đồng thời có thể làm mẫu phản ánh một thời điểm nhất định chứ không phải mọi transaction tương lai.
- Bảng rất lớn vẫn có thể được analyze với chi phí thấp hơn việc lưu toàn bộ giá trị của mọi row.
- Tăng statistics target thường tăng lượng mẫu/chi tiết có thể thu thập, nhưng tốn thêm thời gian và tài nguyên.

### 2.5. ANALYZE không thay đổi rows nghiệp vụ

`ANALYZE` không UPDATE hay DELETE rows trong bảng. Nó cập nhật metadata thống kê mà planner sử dụng. Nó không phải lệnh làm sạch bloat, không trả dung lượng data file về OS và không làm thay đổi business values.

### 2.6. ANALYZE có thể chạy khi hệ thống đang phục vụ query

ANALYZE được thiết kế để có thể chạy đồng thời với các hoạt động đọc/ghi thông thường; nó không yêu cầu khóa độc quyền ngăn mọi DML như một số DDL. Tuy vậy, nó vẫn tiêu thụ I/O/CPU, đọc dữ liệu, cập nhật catalogs và có thể tranh tài nguyên với workload. Trên bảng rất lớn hoặc nhiều cột target cao, nên chọn thời điểm và đo tác động.

---

## 3. Phân biệt ANALYZE và VACUUM

Hai lệnh thường được nhắc cùng nhau nhưng mục tiêu khác nhau.

| Lệnh | Mục đích chính | Tác động điển hình |
|---|---|---|
| `ANALYZE table` | Thu thập planner statistics | Cập nhật thống kê cột/extended stats |
| `VACUUM table` | Dọn/reclaim dead tuples khi an toàn, cập nhật visibility/freeze metadata | Hỗ trợ tái sử dụng không gian và MVCC |
| `VACUUM ANALYZE table` | Thực hiện cả hai mục tiêu | Dọn dead tuples rồi thu thập thống kê |
| `VACUUM FULL table` | Rewrite bảng để thu hồi không gian vật lý | Có lock mạnh, cần dung lượng tạm và chi phí cao |

### 3.1. Khi nào chỉ cần ANALYZE?

- Bulk import nhiều rows mới.
- Phân bố dữ liệu thay đổi rõ rệt.
- Backfill làm thay đổi giá trị ở nhiều rows.
- Thay đổi skew/hot values khiến estimates sai.
- Tạo hoặc cập nhật extended statistics object.
- Query planner ước lượng sai cardinality dù dead tuples không phải vấn đề.

### 3.2. Khi nào cần VACUUM?

- UPDATE/DELETE tạo nhiều dead tuples.
- Bảng có nguy cơ bloat hoặc cần reclaim space để tái sử dụng.
- Cần cập nhật visibility map và freeze tuples theo cơ chế MVCC.
- Autovacuum không theo kịp workload.

### 3.3. Khi nào dùng VACUUM ANALYZE?

Sau một đợt UPDATE/DELETE lớn, có thể cần cả dọn dead tuples và cập nhật stats:

~~~sql
VACUUM (ANALYZE) app.orders;
~~~

Đừng dùng `VACUUM ANALYZE` theo phản xạ sau mọi INSERT nhỏ. INSERT có thể làm stats cũ về cardinality/distribution, nhưng không nhất thiết tạo dead tuples đáng kể. `ANALYZE` riêng có thể đủ.

### 3.4. VACUUM không tự bảo đảm stats tốt nhất

VACUUM và ANALYZE có thể được autovacuum phối hợp trong một số tình huống, nhưng chức năng của chúng vẫn khác. Nếu bảng thay đổi distribution mạnh mà chưa đến ngưỡng autoanalyze, planner có thể cần `ANALYZE` thủ công ngay cả khi không cần vacuum.

### 3.5. ANALYZE không làm bảng nhỏ lại

Nếu vấn đề là file table/index chiếm dung lượng lớn sau DELETE, `ANALYZE` không thu nhỏ file. Cần hiểu VACUUM thường reclaim space để reuse; `VACUUM FULL` rewrite và có trade-offs. Đừng nhầm “planner stats đã cập nhật” với “bloat đã được xử lý”.

---

## 4. Planner sử dụng thống kê ở đâu?

### 4.1. Từ SQL tới plan

~~~text
SQL statement
     |
     v
Parse / Rewrite
     |
     v
Planner / Optimizer
     |
     +--> Đọc catalog, indexes, constraints
     |
     +--> Đọc thống kê từ ANALYZE
     |
     +--> Ước lượng selectivity/cardinality/cost
     |
     v
Chọn execution plan
     |
     v
Executor chạy plan
~~~

Thống kê là một đầu vào của planner, cùng với schema, indexes, constraints, cost settings, parameter values và thông tin khác.

### 4.2. Cardinality estimation

**Cardinality** là số rows planner dự đoán một node sẽ trả về. Ví dụ:

~~~sql
SELECT *
FROM app.orders
WHERE order_status='paid';
~~~

Nếu bảng có 10 triệu rows và 20% là `paid`, planner có thể ước lượng khoảng 2 triệu rows. Estimate này ảnh hưởng lựa chọn sequential scan/index scan, join và memory.

### 4.3. Selectivity

Selectivity là tỷ lệ rows thỏa điều kiện. Với ví dụ trên:

\[
\text{selectivity} \approx \frac{\text{rows thỏa điều kiện}}{\text{tổng rows}}
\]

Nếu selectivity thấp, index có thể hữu ích; nếu cao, sequential scan có thể rẻ hơn. Không có quy tắc “có index thì luôn dùng index”.

### 4.4. Join order

Một query join nhiều bảng có nhiều thứ tự khả dĩ. Sai estimates ở một bảng có thể khiến planner chọn thứ tự join kém, ví dụ đưa bảng lớn vào nested loop outer/inner không phù hợp.

### 4.5. Join method

Planner có thể chọn:

- **Nested Loop:** thường hữu ích khi outer side nhỏ và inner lookup có index hiệu quả.
- **Hash Join:** thường hữu ích với tập dữ liệu đủ lớn, build hash table phù hợp memory.
- **Merge Join:** có thể hiệu quả khi inputs đã được sắp xếp hoặc chi phí sort hợp lý.

Thống kê ảnh hưởng cardinality và cost, từ đó ảnh hưởng join method.

### 4.6. Sort, aggregate và parallelism

Estimate sai có thể làm planner dự đoán số rows/groups sai, ảnh hưởng sort, hash aggregate, hash memory, spill to disk và quyết định parallel plan. Thống kê tốt không bảo đảm plan hoàn hảo, nhưng là điều kiện quan trọng để planner ước lượng thực tế.

### 4.7. ANALYZE không tạo index

Nếu query cần một đường truy cập mà chưa có index, `ANALYZE` không tự tạo index. Nó chỉ giúp planner đánh giá các đường truy cập hiện có. Tương tự, ANALYZE không tự rewrite SQL hoặc tăng `work_mem`.

---

## 5. Các nguồn thống kê cơ bản trong pg_stats

### 5.1. Xem thống kê cột

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname='app'
  AND tablename='orders'
ORDER BY attname;
~~~

`pg_stats` là view dễ đọc hơn catalog nội bộ `pg_statistic`. Một số cột chỉ có dữ liệu khi loại dữ liệu/cấu hình thống kê tương ứng hỗ trợ. Nếu cột không xuất hiện, kiểm tra relation, quyền và việc ANALYZE đã chạy hay chưa.

### 5.2. null_frac

`null_frac` là ước lượng tỷ lệ giá trị NULL của cột.

| Cột | null_frac | Diễn giải |
|---|---:|---|
| `customer_id` | 0.00 | Hầu như không có NULL |
| `coupon_code` | 0.75 | Khoảng 75% rows NULL |
| `shipped_at` | 0.40 | Khoảng 40% rows NULL |

Planner dùng thông tin này để ước lượng predicates như `IS NULL`, `IS NOT NULL` và các điều kiện khác.

### 5.3. avg_width

`avg_width` là kích thước trung bình ước lượng (bytes) của dữ liệu cột. Nó giúp planner ước lượng row width và cost của những thao tác cần lưu/truyền rows.

Với `text`, `jsonb`, `bytea` hoặc cột biến độ dài, average width có thể thay đổi mạnh theo workload. Nếu payload size tăng, stats cũ có thể khiến planner đánh giá sai memory/I/O.

### 5.4. n_distinct

`n_distinct` là ước lượng số giá trị khác nhau:

- Giá trị dương: ước lượng số distinct values tuyệt đối.
- Giá trị âm: độ lớn biểu thị tỷ lệ so với số rows trong bảng.

Ví dụ:
- `n_distinct = 100`: khoảng 100 giá trị khác nhau.
- `n_distinct = -1`: cột gần như unique, distinct count xấp xỉ số rows.
- `n_distinct = -0.1`: distinct count xấp xỉ 10% số rows.

Giá trị này đặc biệt quan trọng với GROUP BY, DISTINCT và selectivity equality khi giá trị không nằm trong MCV list.

### 5.5. most_common_vals (MCV)

MCV là danh sách **Most Common Values** — các giá trị xuất hiện nhiều nhất trong mẫu/thống kê — cùng với tần suất trong `most_common_freqs`.

Ví dụ `order_status` có:

| Giá trị | Tần suất |
|---|---:|
| `paid` | 0.60 |
| `new` | 0.20 |
| `cancelled` | 0.15 |
| Các giá trị khác | 0.05 |

Nếu `paid` là MCV, planner có thể dùng tần suất riêng thay vì giả định mọi distinct values có xác suất bằng nhau.

### 5.6. histogram_bounds

Histogram mô tả phân bố của các giá trị không NULL còn lại, thường sau khi MCV values được tách riêng. Các boundaries đại diện cho các bucket có số lượng mẫu gần tương đương (equidepth) theo cơ chế thống kê.

Planner dùng histogram để ước lượng range predicates như:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-01-01'
  AND created_at <  TIMESTAMPTZ '2026-02-01'
~~~

Histogram không phải danh sách mọi giá trị và không bảo đảm mỗi khoảng thời gian có đúng cùng số rows khi dữ liệu thay đổi.

### 5.7. correlation

`correlation` mô tả tương quan giữa **thứ tự vật lý của rows trong heap** và thứ tự logic theo giá trị cột (thường từ thấp đến cao), nằm trong khoảng -1 đến +1.

- Gần +1: heap order tương đối cùng chiều với column order.
- Gần -1: heap order tương đối ngược chiều.
- Gần 0: thứ tự vật lý gần như không tương quan với giá trị.

Đây **không phải** hệ số tương quan giữa hai cột nghiệp vụ, ví dụ `customer_id` với `region`. Nó giúp planner ước lượng chi phí truy cập index và heap pages.

### 5.8. Thống kê cho arrays và các loại dữ liệu đặc biệt

`pg_stats` còn có các fields như `most_common_elems`, `most_common_elem_freqs`, `elem_count_histogram` cho những loại dữ liệu phù hợp. Các thống kê này hỗ trợ planner với một số operators/array predicates. Không phải mọi kiểu dữ liệu đều có mọi field.

### 5.9. Thống kê là ước lượng, không phải số đếm chính xác

`pg_stats.n_distinct`, MCV frequencies và histogram là kết quả sampling. Đừng dùng chúng làm báo cáo nghiệp vụ chính xác như `COUNT(DISTINCT ...)`. Nếu cần số liệu chính xác, chạy query phù hợp và cân nhắc cost.

---

## 6. MCV và histogram phối hợp ước lượng selectivity

### 6.1. Equality với giá trị phổ biến

~~~sql
SELECT *
FROM app.orders
WHERE order_status='paid';
~~~

Nếu `paid` nằm trong `most_common_vals`, planner có thể dùng tần suất tương ứng trong `most_common_freqs` để ước lượng số rows.

### 6.2. Equality với giá trị hiếm/không có trong MCV

Nếu giá trị không nằm trong MCV, planner thường phải ước lượng dựa trên distinct count và phần tần suất còn lại. Với phân bố rất skewed, estimate có thể kém nếu MCV list không đủ chi tiết.

### 6.3. Range predicates

~~~sql
SELECT *
FROM app.orders
WHERE total_amount BETWEEN 100 AND 200;
~~~

Histogram giúp planner ước lượng tỷ lệ rows nằm trong khoảng. Nếu dữ liệu có một spike rất hẹp hoặc nhiều khoảng rỗng mà histogram không thể biểu diễn đủ, estimate vẫn có thể sai.

### 6.4. NULL predicates

`null_frac` cung cấp thông tin cho:

~~~sql
WHERE coupon_code IS NULL
~~~

và

~~~sql
WHERE coupon_code IS NOT NULL
~~~

NULL không được xử lý như một giá trị bình thường trong histogram; planner có thống kê riêng.

### 6.5. Tại sao một MCV target thấp có thể gây estimate kém?

Giả sử bảng có hàng triệu rows, một số `customer_id` cực kỳ hot và phần còn lại có tần suất thấp. Nếu các hot values không được giữ đủ trong MCV list, planner có thể đánh giá equality predicate trên hot customer giống một distinct value thông thường.

Tăng statistics target cho cột đó có thể làm MCV list chi tiết hơn, nhưng cũng tăng sampling/metadata overhead. Hãy xác nhận bằng `EXPLAIN` trước/sau.

---

## 7. ANALYZE và lấy mẫu dữ liệu

### 7.1. Vì sao sampling?

Trên bảng hàng tỷ rows, quét toàn bộ rows chỉ để tính một số thống kê planner sẽ rất tốn kém. Sampling cho phép ước lượng phân bố với chi phí nhỏ hơn đáng kể.

### 7.2. Sampling có thể bỏ lỡ giá trị hiếm

Nếu một giá trị chỉ xuất hiện rất ít, mẫu có thể không chọn được rows đại diện cho giá trị đó. Kết quả là MCV/histogram không thể mô tả chính xác mọi tail values.

### 7.3. Sampling target

`default_statistics_target` kiểm soát mức chi tiết mặc định của thống kê. Target lớn hơn thường làm sample và thống kê có thể chi tiết hơn, nhưng tốn thêm thời gian, I/O và catalog space. Target không phải “số rows muốn analyze”.

### 7.4. Thống kê không đồng nhất theo mọi cột

Một bảng có thể có:
- `status`: ít giá trị, skew mạnh.
- `customer_id`: nhiều distinct values, một số khách hàng cực hot.
- `created_at`: phân bố thời gian có xu hướng.
- `payload`: JSONB rộng, đa dạng.

Mỗi cột có nhu cầu statistics target khác nhau. Không nên đặt target cực cao cho mọi cột chỉ vì một query có estimate sai.

### 7.5. Analyze khi dữ liệu đang thay đổi

ANALYZE lấy mẫu tại thời điểm thực hiện; các transactions đồng thời có thể thêm/sửa/xóa dữ liệu. Sau khi hoàn tất, stats là best-effort snapshot và có thể nhanh chóng trở nên cũ nếu write rate cao. Autovacuum/autoanalyze tiếp tục cập nhật theo ngưỡng.

### 7.6. Bảng nhỏ

Với bảng nhỏ, PostgreSQL có thể thu thập mẫu bao phủ phần lớn hoặc toàn bộ rows, tùy giới hạn và cơ chế lấy mẫu. Với bảng rất nhỏ, việc tăng target từ 100 lên 1.000 có thể không cải thiện đáng kể.

### 7.7. Không cần ANALYZE mỗi câu INSERT

ANALYZE sau mỗi một vài rows thường lãng phí. Hãy để autoanalyze xử lý thay đổi bình thường, và chạy thủ công sau những thay đổi lớn hoặc khi có evidence planner stats đã stale.

---

## 8. Statistics target

### 8.1. Target mặc định

~~~sql
SHOW default_statistics_target;
~~~

Giá trị mặc định phổ biến là 100, nhưng có thể thay đổi theo PostgreSQL version/distribution hoặc cấu hình cluster.

### 8.2. Target riêng cho một cột

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS 1000;

ANALYZE app.orders (customer_id);
~~~

Thao tác này yêu cầu thống kê chi tiết hơn cho `customer_id`. Số 1000 là **ví dụ để thử nghiệm**, không phải giá trị khuyến nghị chung.

### 8.3. Trở về target mặc định

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS -1;
~~~

`-1` có nghĩa dùng default target. Giá trị `0` có thể dùng để tắt thu thập thống kê cho cột trong các trường hợp phù hợp; không nên làm vậy cho cột query-critical nếu chưa đánh giá.

### 8.4. Đổi default ở session

~~~sql
SET default_statistics_target = 300;
ANALYZE app.orders;
~~~

Đây là setting trong session hiện tại; nó ảnh hưởng ANALYZE được chạy trong session theo quy tắc config. Nếu cần cấu hình bền vững ở cấp hệ thống/role/database, phải quản lý bằng cơ chế cấu hình phù hợp và quyền được phép.

### 8.5. Target lớn hơn không phải lúc nào cũng tốt hơn

Trade-offs:

- ANALYZE tốn thời gian và tài nguyên hơn.
- Statistics catalog lớn hơn.
- MCV/histogram chi tiết hơn, có thể cải thiện estimate cho skewed distributions.
- Một số query vẫn không hưởng lợi nếu predicate/joins không được loại stats đó hỗ trợ.
- Sampling vẫn là ước lượng; tăng target không biến stats thành full exact counts.

### 8.6. Chọn target theo evidence

Quy trình:

1. Xác định query có estimate sai.
2. Xác định cột/predicate gây sai.
3. Đọc `pg_stats`.
4. Kiểm tra MCV/histogram có mô tả được distribution không.
5. Tăng target riêng cột cần thiết.
6. Chạy ANALYZE.
7. So sánh `EXPLAIN` estimates/plan và thời gian trên workload đại diện.
8. Giữ target cao nếu có cải thiện thực và overhead chấp nhận được; nếu không, trả về mức phù hợp.

### 8.7. Target của bảng không đồng nghĩa sampling mọi columns giống nhau

Một vài cột có target lớn có thể ảnh hưởng sampling effort cho relation; nhưng chi phí và số lượng thống kê cụ thể còn phụ thuộc số columns, kiểu dữ liệu và extended statistics objects. Đừng dự đoán chính xác thời gian ANALYZE chỉ từ một con số target.

---

## 9. Extended statistics: mô tả quan hệ giữa nhiều cột

### 9.1. Vấn đề khi giả định các cột độc lập

Giả sử bảng app.users có hai cột country và currency. Trong dữ liệu thực, hầu hết users ở Việt Nam dùng VND, users ở Nhật dùng JPY. Hai cột có tương quan mạnh.

~~~sql
SELECT *
FROM app.users
WHERE country='VN'
  AND currency='VND';
~~~

Nếu planner chỉ có thống kê từng cột và giả định hai điều kiện độc lập, nó có thể nhân hai selectivities. Kết quả có thể không phản ánh phân bố thực tế của các cặp giá trị.

### 9.2. CREATE STATISTICS

PostgreSQL cung cấp **extended statistics** để thu thập thông tin về nhiều columns hoặc expressions trên cùng một table.

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (dependencies, ndistinct, mcv)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

Các loại thống kê được chọn:

- **dependencies:** functional dependencies giữa các cột.
- **ndistinct:** ước lượng số tổ hợp distinct.
- **mcv:** most common combinations (các tổ hợp giá trị phổ biến).

Không cần tạo cả ba cho mọi cặp cột. Chọn theo query patterns và loại sai lệch estimate.

### 9.3. Functional dependencies

Ví dụ nếu zip_code gần như xác định city, điều kiện:

~~~sql
WHERE zip_code='700000'
  AND city='Ho Chi Minh City'
~~~

có thể có tương quan mạnh. Nếu planner giả định độc lập, nó có thể đánh giá selectivity thấp hơn thực tế.

Extended dependency statistics giúp planner nhận biết một số quan hệ kiểu này trong các predicate phù hợp.

### 9.4. Giới hạn của dependencies

Functional dependency statistics không phải mô hình tương quan tổng quát. Planner sử dụng chúng chủ yếu cho những điều kiện đơn giản như equality với constants và một số dạng IN phù hợp; không nên kỳ vọng chúng xử lý mọi range predicate, LIKE, biểu thức phức tạp, column-to-column comparison hoặc join selectivity.

Nếu query vẫn ước lượng sai, kiểm tra loại predicate có được loại extended stats đó hỗ trợ hay không.

### 9.5. Multivariate ndistinct

Một query GROUP BY nhiều cột:

~~~sql
SELECT country, currency, count(*)
FROM app.users
GROUP BY country, currency;
~~~

Số nhóm không nhất thiết bằng tích distinct(country) × distinct(currency). Multivariate ndistinct statistics giúp planner ước lượng số tổ hợp distinct của nhiều cột, từ đó dự đoán số groups và chi phí aggregate.

### 9.6. Multivariate MCV

MCV statistics cho các combinations phổ biến giúp mô tả skew ở cấp tổ hợp. Ví dụ một số cặp country/currency xuất hiện rất nhiều, các cặp khác rất hiếm hoặc không xuất hiện.

Planner có thể dùng thông tin này khi query predicates phù hợp. MCV không phải bảng lookup mọi combinations; chỉ lưu các tổ hợp phổ biến trong giới hạn thống kê.

### 9.7. Xem extended statistics

~~~sql
SELECT
    stxname,
    stxkeys,
    stxkind
FROM pg_statistic_ext
WHERE stxnamespace='app'::regnamespace;
~~~

stxkind thể hiện các loại thống kê được yêu cầu. Dữ liệu đã thu thập được lưu ở catalog liên quan, ví dụ pg_statistic_ext_data; việc xem trực tiếp có giới hạn quyền và representation nội bộ. Ưu tiên pg_stats_ext hoặc pg_stats_ext_exprs khi phiên bản có view phù hợp.

### 9.8. Thống kê mở rộng chỉ trong cùng một relation

Extended statistics được tạo trên columns/expressions của **một table**. Chúng không phải cơ chế khai báo mọi mối tương quan giữa hai bảng để planner tự giải quyết join cardinality. Nếu sai estimate ở join, xem thống kê từng bảng, join keys, uniqueness/FK constraints, data distribution và query shape.

---

## 10. Extended statistics cho biểu thức

### 10.1. Query trên biểu thức

Một ứng dụng có thể thường xuyên chạy:

~~~sql
SELECT *
FROM app.customers
WHERE lower(email)='alice@example.com';
~~~

Thống kê riêng của cột email có thể không mô tả đầy đủ phân bố của biểu thức lower(email), nhất là khi dữ liệu có nhiều biến thể hoa/thường.

### 10.2. CREATE STATISTICS trên expression

Ở các PostgreSQL versions hỗ trợ expression statistics:

~~~sql
CREATE STATISTICS app.customers_lower_email_stats
ON (lower(email))
FROM app.customers;

ANALYZE app.customers;
~~~

Sau đó planner có thể dùng statistics của biểu thức cho những query phù hợp. Tính năng và cú pháp expression statistics phụ thuộc phiên bản; xác minh trước khi đưa migration vào production.

### 10.3. Extended statistics kết hợp cột và expression

~~~sql
CREATE STATISTICS app.customer_region_lower_name_stats
    (mcv, dependencies)
ON region, (lower(customer_name))
FROM app.customers;

ANALYZE app.customers;
~~~

Điều này mô tả một số quan hệ giữa cột region và biểu thức lower(customer_name) trên cùng bảng, trong giới hạn planner hỗ trợ.

### 10.4. Statistics không thay expression index

Nếu query cần tìm theo lower(email) và cần truy cập nhanh, expression index có thể cần thiết:

~~~sql
CREATE INDEX ix_customers_lower_email
ON app.customers (lower(email));
~~~

- **Expression statistics** giúp planner ước lượng phân bố.
- **Expression index** cung cấp access path để tìm rows.

Hai thứ giải quyết hai vấn đề khác nhau và có thể bổ trợ nhau.

### 10.5. Không tạo stats cho mọi expression

Mỗi stats object có chi phí metadata/analyze. Tạo objects cho các biểu thức không xuất hiện trong workload không đem lại lợi ích đáng kể. Ưu tiên expressions có query frequency/cost cao và evidence estimate sai.

---

## 11. Tạo lab về thống kê phân bố

Phần này tạo một dataset thử nghiệm để quan sát khác biệt giữa số lượng giá trị và skew. Chỉ chạy trong database lab có quyền tạo schema/table.

### 11.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS analyze_lab;

CREATE TABLE analyze_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL,
    region text NOT NULL,
    order_status text NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL,
    coupon_code text
);
~~~

### 11.2. Sinh dữ liệu skewed

~~~sql
INSERT INTO analyze_lab.orders
    (order_id,customer_id,region,order_status,
     total_amount,created_at,coupon_code)
SELECT
    g,
    CASE
      WHEN g % 100 < 40 THEN 1
      ELSE 2 + (g % 9998)
    END,
    CASE
      WHEN g % 100 < 60 THEN 'north'
      ELSE 'south'
    END,
    CASE
      WHEN g % 100 < 70 THEN 'paid'
      WHEN g % 100 < 90 THEN 'new'
      ELSE 'cancelled'
    END,
    (10 + (g % 50000))::numeric / 10,
    timestamptz '2025-01-01 00:00:00+00'
       + (g % 365) * interval '1 day',
    CASE
      WHEN g % 4 = 0 THEN NULL
      WHEN g % 100 < 5 THEN 'VIP'
      ELSE 'STANDARD'
    END
FROM generate_series(1,200000) AS g;
~~~

Dataset cố ý tạo phân bố không đồng đều: customer 1 hot, status paid phổ biến và coupon có nhiều NULL. Đây là dữ liệu lab, không đại diện một hệ thống thực.

### 11.3. Tạo indexes để so sánh access path

~~~sql
CREATE INDEX ix_analyze_orders_customer
ON analyze_lab.orders(customer_id);

CREATE INDEX ix_analyze_orders_status
ON analyze_lab.orders(order_status);

CREATE INDEX ix_analyze_orders_region_status
ON analyze_lab.orders(region,order_status);
~~~

### 11.4. Xem stats trước khi analyze

Bảng mới nạp có thể chưa có thống kê cột đầy đủ. Kiểm tra:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
ORDER BY attname;
~~~

Kết quả phụ thuộc việc stats đã tồn tại từ autoanalyze hoặc các thao tác trước đó. Không giả định luôn NULL.

### 11.5. Chạy ANALYZE

~~~sql
ANALYZE VERBOSE analyze_lab.orders;
~~~

### 11.6. Đọc thống kê

~~~sql
SELECT
    attname,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
ORDER BY attname;
~~~

Quan sát:
- customer_id có MCV hot value.
- order_status có MCV theo tần suất.
- coupon_code có NULL fraction đáng kể.
- correlation phản ánh physical order theo từng cột, không phải relation giữa region và status.

### 11.7. Kiểm tra số liệu chính xác để so với estimates

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE customer_id=1) AS hot_customer_rows,
    COUNT(*) FILTER (WHERE order_status='paid') AS paid_rows,
    COUNT(*) FILTER (WHERE coupon_code IS NULL) AS null_coupon_rows
FROM analyze_lab.orders;
~~~

Query này tính số thật trên lab. Nó có thể tốn scan; không chạy một phép COUNT full-table liên tục trên bảng production khổng lồ chỉ để thay thế thống kê planner.

### 11.8. So sánh estimates với actual

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM analyze_lab.orders
WHERE customer_id=1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM analyze_lab.orders
WHERE customer_id=9999;
~~~

Planner có thể chọn access path khác nhau do selectivity. Nếu hot customer chiếm nhiều rows, sequential scan có thể rẻ hơn index lookup; với customer hiếm, index có thể phù hợp.

EXPLAIN ANALYZE thực sự thực thi query. Với SELECT trong lab, nó đọc dữ liệu và tiêu thụ tài nguyên nhưng không thay đổi rows. Với DML, nó thực thi DML và triggers thật; chỉ chạy trong lab hoặc transaction có rollback và hiểu side effects.

---

## 12. Đọc EXPLAIN: estimated rows và actual rows

### 12.1. Ví dụ output giản lược

~~~text
Seq Scan on orders  (cost=0.00..4500.00 rows=80000 width=64)
                    (actual time=0.050..28.000 rows=140000 loops=1)
  Filter: (order_status = 'paid')
  Rows Removed by Filter: 60000
Planning Time: 0.300 ms
Execution Time: 32.000 ms
~~~

Đây là output minh họa, không phải kết quả từ dataset thật.

- **rows=80000** ở phần cost: planner **ước lượng** số rows.
- **actual rows=140000**: executor thực tế trả rows theo lần loop.
- **loops=1**: node chạy một lần.
- **width=64**: planner ước lượng row width.
- **Rows Removed by Filter**: rows đã đọc nhưng bị filter loại.
- **cost**: đơn vị cost nội bộ tương đối, không phải milliseconds.

### 12.2. Actual rows khi loops lớn hơn 1

Với nested loop inner node có loops=1000, actual rows thường là số rows trung bình mỗi loop được hiển thị theo cách của EXPLAIN. Để hiểu tổng lượng rows, phải xét actual rows × loops, đồng thời nhớ các số hiển thị có thể được làm tròn.

Không so estimated rows và actual rows mà bỏ qua loops.

### 12.3. Planning Time và Execution Time

- **Planning Time:** thời gian planner tạo plan.
- **Execution Time:** thời gian executor chạy query theo cách đo EXPLAIN.

ANALYZE statistics có thể ảnh hưởng plan và planning cost, nhưng query chậm còn do I/O, locks, cache, network, row width, memory, concurrency và nhiều yếu tố khác.

### 12.4. Sai số estimate

Một cách xem nhanh là tỷ lệ actual/estimated, nhưng tránh kết luận chỉ từ một node. Các node phía trên chịu sai số tích lũy từ nodes dưới; một estimate lệch lớn ở scan có thể làm join order thay đổi toàn query.

### 12.5. Tìm node đầu tiên sai nhiều

Khi plan xấu, đọc từ leaves lên:
1. Scan node có estimated rows và actual rows lệch nhiều?
2. Predicate nào gây sai?
3. Stats cột đã cập nhật chưa?
4. Cột có skew/MCV không?
5. Predicate nhiều cột có cần extended stats?
6. Có expression/cast/function khiến stats không khớp query expression?
7. Có prepared generic plan làm parameter values không được xét?
8. Có data distribution thay đổi sau ANALYZE?

### 12.6. EXPLAIN không tự nói nguyên nhân

Nếu planner chọn Seq Scan, không thể kết luận ngay stats sai. Có thể sequential scan thực sự rẻ hơn, index không selective, bảng nhỏ, query cần phần lớn columns, visibility/cache/I/O cost hoặc cost parameters khác.

### 12.7. Không ép planner để che stats sai

Tắt Seq Scan, ép join method hoặc thay cost parameters có thể làm một query sample chạy nhanh nhưng gây plan regressions ở query khác. Trước tiên hiểu cardinality và data distribution; dùng planner enable flags chủ yếu như công cụ chẩn đoán trong session thử nghiệm, không phải fix chung.

---

## 13. Stats cũ sau bulk load và thay đổi dữ liệu

### 13.1. Khi nào cần ANALYZE thủ công?

- COPY/INSERT một lượng rows lớn vào bảng trước đó nhỏ hoặc rỗng.
- Backfill làm thay đổi tỷ lệ giá trị.
- Import một data partition có phân bố khác hẳn partition trước.
- Xóa phần lớn rows hoặc chuyển trạng thái hàng loạt.
- Thay đổi distribution của hot keys/tenant/status.
- Query plan regression xảy ra ngay sau data migration.

### 13.2. Vì sao autoanalyze có thể chưa chạy?

Autoanalyze dựa trên threshold/scale factor và thống kê thay đổi được ghi nhận. Sau bulk load, hệ thống có thể chưa đến lượt worker, worker bận, table settings khác default hoặc parent partitioned table không có tuple counters như bảng thường.

Nếu query quan trọng chạy ngay sau import, có thể chạy ANALYZE thủ công trước khi mở traffic/read path mới.

### 13.3. Sau CREATE INDEX

Tạo index không tự bảo đảm mọi column statistics mới nhất. Nếu workload/query plan phụ thuộc phân bố vừa thay đổi, chạy ANALYZE riêng sau thao tác migration phù hợp.

### 13.4. Sau restore/clone

Restore có thể mang theo stats hoặc cần ANALYZE theo quy trình restore/version. Sau import một lượng lớn dữ liệu, stats có thể chưa đại diện cho dataset mới. Lập bước analyze trong runbook trước khi chuyển traffic.

### 13.5. Analyze trong migration online

Khi vừa thêm cột/backfill, stats của cột mới có thể chưa tồn tại hoặc chưa phản ánh dữ liệu. Trình tự triển khai nên tính cả:
- Add schema.
- Deploy code ghi dữ liệu mới.
- Backfill theo batch.
- ANALYZE các cột/expressions quan trọng.
- Kiểm tra plans và latency.
- Chuyển read path/cutover.

Không chuyển traffic query-critical ngay sau bulk load mà không xem xét planner stats.

---

## 14. Autovacuum và autoanalyze

### 14.1. Tự động thu thập thống kê

PostgreSQL có cơ chế autovacuum launcher/workers. Ngoài VACUUM tự động, workers có thể thực hiện **autoanalyze** khi thống kê một relation được coi là đã cũ đủ theo thresholds.

### 14.2. Threshold và scale factor

Các settings quan trọng gồm:

~~~sql
SHOW autovacuum;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
~~~

Ngưỡng autoanalyze cho một bảng thường được mô tả theo công thức khái quát:

\[
\text{analyze threshold}
=
\text{autovacuum\_analyze\_threshold}
+
\text{autovacuum\_analyze\_scale\_factor}
\times
\text{ước lượng số tuples của bảng}
\]

Giá trị mặc định phổ biến là threshold 50 và scale factor 0.1, nhưng phải xem cấu hình server và table-level reloptions thực tế.

### 14.3. Ví dụ ước lượng threshold

Nếu bảng có khoảng 1.000.000 rows, threshold minh họa là:

\[
50 + 0.1 \times 1{,}000{,}000 = 100{,}050
\]

Đây là số thay đổi ước lượng theo cơ chế thống kê, không phải cam kết autoanalyze chạy chính xác sau row thứ 100.050. Thời điểm còn phụ thuộc worker scheduling, stats collector state, table settings và tải hệ thống.

### 14.4. INSERT/UPDATE/DELETE

Các phiên bản PostgreSQL hiện đại có thống kê thay đổi phù hợp để xem xét analyze threshold theo insert/update/delete; chi tiết counters và công thức có thể thay đổi theo version. Đừng tự áp một công thức cũ cho mọi server.

### 14.5. Table-level settings

Có thể override thresholds theo bảng:

~~~sql
ALTER TABLE app.orders SET (
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

Đây là ví dụ cấu hình cần benchmark. Đặt scale factor nhỏ làm analyze thường xuyên hơn, tăng tài nguyên background; đặt quá lớn làm stats stale lâu hơn.

### 14.6. Autovacuum không phải lúc nào cũng chạy ngay

Autovacuum workers có thể đang bận, bị giới hạn bởi số workers, cost delay hoặc maintenance workload khác. ANALYZE thủ công là lựa chọn khi có lý do cụ thể; không nên chạy cron ANALYZE toàn database mỗi phút để bù một cấu hình autovacuum sai.

### 14.7. Partitioned parent

Partitioned parent không lưu tuples như một ordinary heap table. Thay đổi ở partitions không nhất thiết kích hoạt autoanalyze cho parent theo cách bảng thường. Khi parent-level/global stats cần được cập nhật, **chạy ANALYZE trên parent** theo lịch hoặc sau thay đổi partition lớn; đồng thời kiểm tra từng partition theo nhu cầu.

### 14.8. Kiểm tra autovacuum có bật không

Autovacuum có thể bị tắt ở cấp hệ thống, nhưng autovacuum cũng liên quan freeze/wraparound safety. Không tắt toàn cục chỉ để giảm I/O. Nếu một bảng cụ thể cần xử lý khác, tune table-level settings và vẫn bảo đảm wraparound maintenance.

### 14.9. Autoanalyze và auto-vacuum là hai loại activity

Một bảng có thể cần ANALYZE nhưng không có nhiều dead tuples; hoặc cần VACUUM dù stats chưa stale. last_analyze và last_autovacuum là các thời điểm khác nhau; đừng coi một field thay cho field kia.

---

## 15. Theo dõi ANALYZE và autoanalyze

### 15.1. pg_stat_user_tables

View này cung cấp thông tin hoạt động theo relation. Một query thường dùng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname='app'
ORDER BY n_mod_since_analyze DESC NULLS LAST;
~~~

Một số cột có thể khác theo PostgreSQL version. Hãy xem schema view thực tế nếu server cũ hoặc managed service có extension/compatibility khác.

### 15.2. Ý nghĩa các trường

- **last_analyze:** thời điểm ANALYZE thủ công gần nhất được ghi nhận.
- **last_autoanalyze:** thời điểm autoanalyze gần nhất.
- **analyze_count:** số lần ANALYZE thủ công theo statistics collector.
- **autoanalyze_count:** số lần autoanalyze.
- **n_mod_since_analyze:** ước lượng số tuples đã bị thay đổi kể từ lần analyze gần nhất, trong các phiên bản hỗ trợ.
- **n_live_tup / n_dead_tup:** ước lượng live/dead tuples, không phải COUNT chính xác.

Nếu last_autoanalyze là NULL, không nhất thiết có lỗi: bảng có thể chưa đến ngưỡng, chưa từng được autoanalyze hoặc statistics vừa được reset.

### 15.3. Xem bảng chưa analyze lâu

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY last_autoanalyze NULLS FIRST;
~~~

Đây là danh sách để điều tra, không phải danh sách “bắt buộc chạy ANALYZE ngay”. Cần đối chiếu workload, table changes, query plan và ngưỡng autoanalyze.

### 15.4. Statistics reset

Một số counters có thể bị reset bởi thao tác reset statistics hoặc restart/maintenance tùy loại stats và phiên bản. Khi so sánh thời gian, luôn ghi nhận mốc reset và đừng coi count từ lúc reset là tổng lịch sử của bảng.

### 15.5. pg_stat_progress_analyze

Các phiên bản PostgreSQL hiện đại có view tiến trình ANALYZE:

~~~sql
SELECT *
FROM pg_stat_progress_analyze;
~~~

View này có thể cho biết relation, phase và tiến độ sampling/extended statistics theo các fields mà version cung cấp. Kiểm tra tài liệu đúng major version vì các cột/phase có thể khác nhau.

### 15.6. Kết hợp với pg_stat_activity

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS relation_name,
    p.phase,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_analyze AS p
JOIN pg_stat_activity AS a USING (pid);
~~~

Query minh họa này hữu ích khi ANALYZE chạy lâu. Một số fields có thể không tồn tại ở version cũ; giảm cột SELECT nếu cần.

### 15.7. ANALYZE và pg_stat_activity

ANALYZE là command bình thường nên thường có thể thấy trong pg_stat_activity khi chạy. Nhưng việc nhìn thấy query text không cho biết nó đã lấy mẫu xong hay đang chờ lock; kết hợp progress view, wait events và logs.

---

## 16. Đọc pg_stats đúng cách

### 16.1. Query theo một cột cụ thể

~~~sql
SELECT
    attname,
    inherited,
    null_frac,
    avg_width,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname IN ('customer_id','order_status','coupon_code');
~~~

Trường inherited giúp phân biệt thống kê tính trên relation và dữ liệu kế thừa từ các child relations trong những tình huống inheritance/partition phù hợp.

### 16.2. Vì sao pg_stats có thể không hiện cột?

- Chưa chạy ANALYZE hoặc relation chưa có thống kê.
- Query sai schema/table/column.
- Role hiện tại không có quyền xem thống kê chi tiết của relation theo security rules.
- Cột là dropped/system/không thuộc relation như tưởng.
- Loại dữ liệu/operator không có slot thống kê phù hợp.
- Stats target của cột bằng 0 hoặc stats chưa được thu thập.

### 16.3. pg_statistic là catalog nội bộ

pg_statistic lưu representation nội bộ của các thống kê. Không nên tự INSERT/UPDATE/DELETE vào catalog này. Dùng ANALYZE, ALTER TABLE SET STATISTICS và CREATE/ALTER STATISTICS để điều khiển cách thu thập.

### 16.4. Quyền xem pg_stats

View pg_stats được thiết kế để cung cấp thông tin thống kê trong giới hạn quyền truy cập; một số dữ liệu có thể nhạy cảm với table contents. Không giả định mọi role đều thấy toàn bộ stats của mọi relation. Dùng role quản trị/monitor có quyền phù hợp theo policy.

### 16.5. Giá trị arrays là representation, không phải API nghiệp vụ

Các cột như most_common_vals và histogram_bounds là arrays có kiểu/format tùy column type. Có thể hiển thị trong SQL client, nhưng không nên parse output text bằng script brittle để làm business logic. Nếu cần metrics, thiết kế query/monitoring rõ và version-aware.

---

## 17. ANALYZE trên partitioned tables và inheritance

### 17.1. Partitioned table có parent và partitions

~~~text
orders (partitioned parent)
    |
    +-- orders_2026_01
    +-- orders_2026_02
    +-- orders_2026_03
~~~

Parent là relation logic; các partitions lưu rows. Planner cần thống kê phù hợp cho partition pruning, estimates toàn bảng và từng partition.

### 17.2. Analyze parent

~~~sql
ANALYZE app.orders;
~~~

Thông thường, ANALYZE relation partitioned/inheritance sẽ xử lý các child partitions/relations theo semantics của PostgreSQL. Thống kê parent-level được dùng cho query nhắm parent; thống kê từng partition có thể phục vụ plan khi partition pruning/scan từng child.

### 17.3. ONLY

~~~sql
ANALYZE ONLY app.orders;
~~~

ONLY yêu cầu analyze relation được nêu mà không phân tích descendants theo quy tắc inheritance. Dùng đúng khi có lý do; với partitioned parent, nếu mục tiêu là cập nhật thống kê tổng thể từ partitions, chỉ analyze parent không descendants có thể không phản ánh dữ liệu bạn muốn.

### 17.4. Autoanalyze và partitioned parent

Partitioned parent không lưu heap tuples như bảng thường, nên autovacuum không nhất thiết tự kích hoạt autoanalyze parent chỉ vì các partitions nhận nhiều rows. Nếu global/parent-level stats quan trọng, lên lịch chạy ANALYZE parent sau các đợt load/partition maintenance và kiểm tra plans.

### 17.5. Analyze từng partition

~~~sql
ANALYZE app.orders_2026_03;
~~~

Có thể hữu ích khi một partition mới được nạp nhiều dữ liệu hoặc distribution khác hẳn các partitions cũ. Nhưng nếu query thường nhắm parent, đừng quên stats của parent.

### 17.6. Inheritance và inherited statistics

Với ordinary table inheritance, query trên parent có thể bao gồm rows từ descendants. PostgreSQL lưu thống kê theo loại inherited/non-inherited phù hợp; view pg_stats có field inherited để phân biệt. Khi dùng ONLY hoặc query descendants, planner cần stats tương ứng.

### 17.7. Partition pruning không thay ANALYZE

Partition pruning xác định partitions nào có thể bị bỏ dựa trên partition key/constraints. ANALYZE cung cấp thống kê rows và phân bố trong relations. Một hệ thống có partition pruning tốt vẫn có thể estimate sai số rows bên trong partition nếu stats stale.

### 17.8. Partition có skew khác nhau

Ví dụ partition tháng hiện tại chứa nhiều đơn hàng mới, partition cũ có chủ yếu cancelled/archived. Một thống kê trung bình ở parent có thể không mô tả chính xác một partition riêng trong mọi query. Planner kết hợp metadata và stats theo plan; sau khi load partition mới, analyze cả partition lẫn parent khi cần.

---

## 18. ANALYZE trên foreign tables và materialized views

### 18.1. Foreign tables

PostgreSQL có thể thu thập thống kê cho foreign tables khi foreign data wrapper hỗ trợ thao tác cần thiết. Chi phí có thể bao gồm đọc dữ liệu qua remote source; không mặc định ANALYZE một foreign table là một thao tác local rẻ.

### 18.2. FDW statistics

Một số FDWs có khả năng lấy thông tin thống kê/ước lượng từ remote system hoặc hỗ trợ sampling theo cách riêng. Hành vi phụ thuộc extension/version. Nếu planner ước lượng sai remote rows, kiểm tra FDW options, remote EXPLAIN và khả năng pushdown.

### 18.3. Materialized views

Materialized view lưu kết quả của query. Sau REFRESH, thống kê của relation có thể cần cập nhật để planner hiểu distribution mới:

~~~sql
REFRESH MATERIALIZED VIEW app.monthly_sales;
ANALYZE app.monthly_sales;
~~~

REFRESH có locking/resource behavior riêng; ANALYZE không thay refresh và không làm materialized view chứa dữ liệu mới.

### 18.4. Temporary tables

Temporary tables có thể cần ANALYZE thủ công sau khi nạp nhiều dữ liệu vì planner cần stats cho các joins/filters tiếp theo trong session. Autoanalyze có hành vi theo temporary relation/session và version; đừng giả định mọi temp table được xử lý giống bảng permanent.

### 18.5. Views thông thường

Ordinary views không lưu rows riêng, nên ANALYZE view như một bảng vật lý không có cùng ý nghĩa. Planner dùng stats của các base relations và expression/extended stats phù hợp. Nếu query view chậm, analyze base tables, xem view rewrite/query plan và các expressions.

---

## 19. ANALYZE và quyền truy cập

### 19.1. Ai được chạy ANALYZE?

Quyền cần thiết phụ thuộc PostgreSQL version và privileges được cấp. Trên nhiều versions, table owner hoặc superuser có thể chạy; các phiên bản mới có thể hỗ trợ privilege MAINTAIN cho một số maintenance operations. Kiểm tra tài liệu đúng phiên bản và không cấp superuser chỉ để một job analyze được bảng.

### 19.2. Quyền đọc thống kê

pg_stats có security behavior để tránh tiết lộ thống kê của những bảng mà role không được phép đọc. Các catalog nội bộ có quyền truy cập hạn chế hơn. Monitoring role cần quyền tối thiểu theo policy.

### 19.3. Security definer job

Nếu một job quản trị chạy ANALYZE thay mặt application, dùng role maintenance riêng có quyền phù hợp. Không biến mọi application roles thành owner của toàn schema để giải quyết một quyền analyze thiếu.

### 19.4. ANALYZE không cấp quyền query

Chạy ANALYZE không thay đổi GRANT/ownership/RLS. Một query có thể có plan tốt hơn sau analyze nhưng vẫn bị permission denied hoặc bị RLS lọc rows.

---

## 20. ANALYZE, locks và tác động vận hành

### 20.1. Có block DML không?

ANALYZE được thiết kế để không chặn các thao tác SELECT/INSERT/UPDATE/DELETE thông thường theo cách một lock độc quyền làm. Tuy nhiên, nó cần lock relation phù hợp và có thể xung đột với một số maintenance/DDL operations. Nếu DDL đang chạy hoặc relation bị khóa lâu, ANALYZE có thể phải chờ.

### 20.2. Tốn I/O và CPU

Sampling vẫn đọc blocks và tính toán statistics. Một lần ANALYZE trên bảng có nhiều columns, target cao và extended stats phức tạp có thể tạo workload đáng kể.

### 20.3. Đừng chạy tất cả tables đồng thời

Chạy ANALYZE hàng loạt trên nhiều bảng lớn có thể làm I/O tăng đột ngột, cạnh tranh với query latency và autovacuum. Chia lịch, ưu tiên bảng query-critical và quan sát impact.

### 20.4. SKIP_LOCKED

Một số PostgreSQL versions hỗ trợ tùy chọn SKIP_LOCKED cho ANALYZE để tránh chờ lock trên relation khi không lấy được lock thích hợp. Nếu relation bị bỏ qua, không được kết luận stats đã được cập nhật. Kiểm tra output/monitoring và lên lịch chạy lại khi lock biến mất.

Ví dụ cú pháp phụ thuộc version:

~~~sql
ANALYZE (SKIP_LOCKED) app.orders;
~~~

Xác nhận option được hỗ trợ trên server đang chạy trước khi dùng trong automation.

### 20.5. ANALYZE trong transaction

ANALYZE có thể được gọi trong ngữ cảnh transaction SQL phù hợp, nhưng thay đổi thống kê/visibility và cách planner nhìn thấy cập nhật có semantics riêng. Không bọc hàng loạt analyze lâu trong một transaction mở chỉ để “atomic” chúng; stats của nhiều bảng không phải business dataset cần một transaction publication duy nhất.

### 20.6. Khi analyze đang chạy mà DDL đến

Một số DDL có thể phải chờ ANALYZE hoặc ngược lại tùy locks. Điều phối migrations, partition attach/detach, reindex và analyze để tránh maintenance queue kéo dài.

---

## 21. Các nguyên nhân khiến ANALYZE chưa cải thiện query

### 21.1. Predicate không được stats mô tả

Stats một cột không thể mô tả mọi biểu thức, JSON path, function hoặc correlated predicates. Xem xét expression statistics, extended stats hoặc rewrite predicate cho planner hiểu tốt hơn.

### 21.2. Correlation giữa các cột

Nếu query lọc đồng thời region/status, single-column stats có thể giả định độc lập và estimate sai. Tạo multivariate MCV/dependencies phù hợp, rồi ANALYZE.

### 21.3. Generic prepared plan

Một prepared statement có thể dùng **generic plan** không phụ thuộc một parameter value cụ thể, trong khi data distribution skew rất mạnh theo parameter. Ví dụ customer 1 có 40% rows còn customer 9999 chỉ có vài rows. Một generic plan duy nhất có thể không tối ưu cho cả hai.

Dùng EXPLAIN EXECUTE và xem plan caching behavior/driver settings. Một custom plan có thể dùng parameter values cụ thể; không phải mọi trường hợp đều cần ép custom plan, vì planning overhead cũng có cost.

### 21.4. Stats tốt nhưng cost settings không hợp

Planner còn dựa trên cost parameters như seq_page_cost, random_page_cost, cpu_tuple_cost và effective_cache_size. Nếu các assumptions về storage/cache không phù hợp, plan có thể kém dù cardinality estimates tương đối đúng.

Không chỉnh cost settings để bù stats stale; trước hết tách lỗi cardinality khỏi lỗi cost model.

### 21.5. Index không phù hợp

ANALYZE không thể tạo index. Nếu query dùng predicate không có access path hiệu quả, planner có thể chọn Seq Scan hợp lý. Cần xem index design, operator class, collation, expression, partial predicate và query selectivity.

### 21.6. Data distribution thay đổi ngay sau analyze

Với write-heavy table, stats có thể cũ nhanh. Nếu job import thay đổi hot values liên tục, cân nhắc autoanalyze thresholds, schedule thủ công hoặc data model/partitioning để stats phù hợp hơn.

### 21.7. Query bottleneck không nằm ở planner

Query có thể chậm vì lock waits, disk latency, network, client fetch, serialization, triggers, CPU contention hoặc memory spills. EXPLAIN ANALYZE/BUFFERS và wait-event monitoring giúp phân biệt.

### 21.8. Plan ổn nhưng runtime biến động

Cache warm/cold, concurrent load, IO pressure, autovacuum, checkpoint và parameter values có thể làm execution time khác nhau dù plan không đổi. Đừng đánh đồng mọi latency regression với stats.

---

## 22. Workflow chẩn đoán estimate sai

~~~mermaid
flowchart TD
    A["Query chậm hoặc plan regression"] --> B["EXPLAIN (ANALYZE, BUFFERS)"]
    B --> C{"Estimated rows lệch actual?"}
    C -- "Không đáng kể" --> D["Kiểm tra I/O, locks, memory, indexes, cost settings"]
    C -- "Có" --> E["Tìm scan/predicate đầu tiên sai"]
    E --> F["Đọc pg_stats và last_analyze"]
    F --> G{"Stats stale hoặc thiếu chi tiết?"}
    G -- "Có" --> H["ANALYZE / tăng target cột cần thiết"]
    G -- "Không" --> I{"Nhiều cột hoặc expression tương quan?"}
    I -- "Có" --> J["Extended statistics / expression statistics"]
    I -- "Không" --> K["Kiểm tra generic plan, casts, operators, skew"]
    H --> L["EXPLAIN lại với parameters đại diện"]
    J --> L
    K --> L
    L --> M["So plan, estimates, latency và workload impact"]
~~~

### 22.1. Tìm sai lệch ở node thấp nhất

Nếu query có nhiều joins, đừng chỉ nhìn tổng thời gian. Tìm node đầu tiên từ dưới lên mà estimate khác xa actual. Nếu scan đầu đã trả gấp 100 lần dự đoán, join phía trên có thể chỉ là hậu quả.

### 22.2. Kiểm tra statistics freshness

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_mod_since_analyze,
    n_live_tup
FROM pg_stat_user_tables
WHERE schemaname='app'
  AND relname='orders';
~~~

Kết hợp với query distribution hiện tại và table growth. Một timestamp analyze mới không chứng minh mọi cột/extended stats đã phù hợp với query.

### 22.3. So sánh estimate sau ANALYZE

~~~sql
ANALYZE app.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM app.orders
WHERE customer_id=1024;
~~~

Nếu estimates cải thiện nhưng runtime không thay đổi, nguyên nhân có thể nằm ở I/O/index/locks. Nếu estimates không đổi, kiểm tra stats target, predicate support, skew và parameterization.

### 22.4. Test nhiều parameter values

Với skewed column, thử các parameter đại diện: hot key, median key, rare key, missing key, NULL khi hợp lệ. Một plan tốt cho một customer không chứng minh nó tốt cho tất cả.

### 22.5. Ghi lại before/after

Khi tune statistics target hoặc extended stats, lưu:
- Query text/parameter class.
- EXPLAIN plan.
- Estimated vs actual rows.
- Planning/execution time.
- Buffer hits/reads.
- Stats target/extended stats definition.
- Tải hệ thống khi đo.

Chỉ giữ thay đổi khi cải thiện có thể lặp lại và không làm workload khác suy giảm nghiêm trọng.

---

## 23. Quản lý extended statistics trong schema

### 23.1. Xem danh sách objects

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    inherited
FROM pg_stats_ext
WHERE schemaname='app'
ORDER BY tablename, statistics_name;
~~~

View pg_stats_ext có trên các PostgreSQL versions hỗ trợ extended statistics. Tên cột và view expression-specific có thể thay đổi theo version; xem catalog/view definition trên server thật.

### 23.2. Tạo object theo workload

Ví dụ query thường xuyên lọc country/currency:

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (mcv, dependencies)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

Không tạo stats object chỉ vì hai cột có tên liên quan. Phải có query predicates hoặc GROUP BY thực sự cần ước lượng tổ hợp.

### 23.3. Xóa object không còn dùng

~~~sql
DROP STATISTICS IF EXISTS app.users_country_currency_stats;
~~~

DROP STATISTICS không xóa rows nghiệp vụ hoặc indexes; nó xóa metadata extended stats object. Nếu object được quản lý trong migration, ghi thay đổi vào schema migration/version control.

### 23.4. Extended statistics target

Một số PostgreSQL versions cho phép đặt statistics target riêng cho object extended statistics bằng ALTER STATISTICS ... SET STATISTICS. Điều này điều chỉnh mức chi tiết của thống kê đa biến. Kiểm tra syntax/version và chỉ tăng target khi query plans cho thấy object hiện tại chưa mô tả đủ combinations.

### 23.5. Không tạo dependency object thay constraint

Nếu business invariant nói zip_code xác định city, extended statistics chỉ giúp planner ước lượng; nó **không** ngăn dữ liệu sai. Dùng UNIQUE, FOREIGN KEY, CHECK hoặc bảng mapping/logic nghiệp vụ phù hợp để enforce consistency.

### 23.6. Không dùng extended stats để thay normalization

Nếu bảng lặp lại nhiều dữ liệu dimension hoặc có quan hệ dữ liệu cần quản trị, thiết kế schema/constraints vẫn là nền tảng. Extended stats chỉ là metadata cho query optimizer.

---

## 24. Những giới hạn quan trọng của planner statistics

### 24.1. Không phải mọi predicate đều được mô tả

Thống kê cột và extended stats hỗ trợ những loại predicates nhất định. Các điều kiện chứa hàm tùy biến, biểu thức phức tạp, casts khác kiểu, collation, pattern matching hoặc operator class đặc biệt có thể không sử dụng đúng stats như mong đợi.

### 24.2. Correlation không có nghĩa planner hiểu mọi cặp cột

Một stats object dependencies cho equality restrictions không tự cung cấp model xác suất hoàn chỉnh cho mọi query. Không suy ra rằng chỉ cần CREATE STATISTICS là mọi join/range predicates hết estimate error.

### 24.3. Join selectivity

Extended statistics chủ yếu hỗ trợ estimates cho restrictions trên một relation; planner không sử dụng chúng như một mô hình tổng quát để ước lượng mọi join giữa các bảng. Nếu join estimate sai, kiểm tra stats từng relation, unique keys, FK, data skew và join clauses.

### 24.4. Statistics không bao gồm dữ liệu tương lai

Một ANALYZE tốt phản ánh mẫu tại thời điểm thu thập. Nếu ingest liên tục tạo một tenant mới chiếm 70% rows trong vài phút, stats trước đó sẽ không thể dự đoán distribution mới.

### 24.5. Stats không phải histogram nghiệp vụ

Planner histogram là cấu trúc nội bộ phục vụ selectivity estimation. Nó không được thiết kế để làm dashboard phân tích dữ liệu, percentiles chính xác hay báo cáo phân phối có SLA.

### 24.6. Thống kê có thể được ước lượng lại

Hai lần ANALYZE có thể tạo sample khác nhau. Nếu query plan thay đổi nhỏ sau một lần analyze, cần đánh giá độ ổn định và workload chứ không nhất thiết coi một lần plan change là lỗi.

### 24.7. Statistics target cực cao không thay đổi query semantics

Target chỉ thay độ chi tiết ước lượng, không thay kết quả SQL, không tạo constraints và không đảm bảo planner sẽ chọn index. Không dùng nó như một “hint” ép plan.

---

## 25. Bảng quyết định: khi nào chạy ANALYZE?

| Tình huống | Hành động thường phù hợp | Vì sao |
|---|---|---|
| Tạo bảng và nạp hàng triệu rows | ANALYZE sau load | Stats cần đại diện cho dữ liệu mới |
| Thêm vài rows vào bảng ổn định | Thường để autoanalyze | Chưa chắc cần analyze thủ công |
| Backfill một cột query-critical | ANALYZE cột đó hoặc bảng | Phân bố có thể thay đổi mạnh |
| UPDATE làm status skew thay đổi | ANALYZE status | MCV/selectivity có thể stale |
| Tạo extended statistics object | ANALYZE relation | Thu thập dữ liệu cho object mới |
| Tạo expression statistics | ANALYZE relation | Planner cần expression stats |
| Query plan sai estimate rõ rệt | Đọc pg_stats, rồi ANALYZE/tune nếu cần | Tìm nguyên nhân trước khi chỉnh |
| DELETE nhiều rows | VACUUM và/hoặc ANALYZE theo nhu cầu | Hai mục tiêu khác nhau |
| Partition mới vừa nạp dữ liệu | ANALYZE partition và parent nếu cần | Stats cục bộ/global |
| REFRESH materialized view lớn | ANALYZE materialized view | Distribution của relation đã đổi |
| Temp table được nạp nhiều rows | ANALYZE trong session | Autovacuum không quản lý temp table như permanent |
| Foreign table remote lớn | Theo dõi FDW và ANALYZE nếu hỗ trợ | Stats remote có thể stale |
| Tạo index nhưng không đổi distribution | Không nhất thiết phải ANALYZE chỉ vì index | Index build không tự làm data distribution thay đổi |
| Restore/clone database | Theo restore procedure, thường kiểm tra và ANALYZE | Đảm bảo planner stats phù hợp restored data |

---

## 26. Thực hành: stats cũ và autoanalyze threshold

### 26.1. Kiểm tra bảng lab

~~~sql
SELECT
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname='analyze_lab'
  AND relname='orders';
~~~

Nếu bảng vừa mới tạo, các giá trị timestamp có thể NULL. Sau ANALYZE thủ công, last_analyze có thể cập nhật; autoanalyze timestamp là hoạt động riêng.

### 26.2. Thay đổi phân bố

~~~sql
UPDATE analyze_lab.orders
SET order_status='paid'
WHERE order_status='cancelled';
~~~

DML này làm thay đổi phân bố status, nhưng stats không nhất thiết được cập nhật tức thì. Trong lab, xem EXPLAIN trước/sau khi chạy ANALYZE.

### 26.3. Đọc stats trước và sau

~~~sql
SELECT
    attname,
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname='order_status';
~~~

Sau đó:

~~~sql
ANALYZE analyze_lab.orders (order_status);

SELECT
    attname,
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname='analyze_lab'
  AND tablename='orders'
  AND attname='order_status';
~~~

### 26.4. So sánh estimate

~~~sql
EXPLAIN
SELECT *
FROM analyze_lab.orders
WHERE order_status='paid';
~~~

EXPLAIN không thực thi SELECT, chỉ cho plan/estimates. Dùng EXPLAIN ANALYZE nếu muốn actual rows, nhưng nó sẽ thực thi query và đọc dữ liệu.

### 26.5. Xem counters

~~~sql
SELECT
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname='analyze_lab'
  AND relname='orders';
~~~

Các counters có thể bị reset và không đồng bộ tức thời với mọi transaction. Không dùng một giá trị đơn lẻ để kết luận autoanalyze chắc chắn đã chạy hay không.

---

## 27. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “ANALYZE dọn dead tuples” | Bloat không được xử lý | VACUUM xử lý MVCC cleanup |
| “VACUUM luôn cập nhật mọi stats đầy đủ” | Planner vẫn dùng stats cũ | Dùng ANALYZE khi cần |
| “ANALYZE đếm chính xác mọi row” | Nhầm estimate với exact count | Stats dựa trên sampling |
| “Chạy ANALYZE mỗi INSERT” | I/O/CPU overhead không cần thiết | Dựa vào workload và autoanalyze |
| “Stats target là số rows mẫu” | Chọn target sai | Target là độ chi tiết/slot, ảnh hưởng sample |
| “Target càng cao luôn càng nhanh” | Analyze tốn tài nguyên, lợi ích không chắc | Tune theo evidence |
| “n_distinct luôn là số dương” | Đọc sai negative fraction | Giá trị âm là tỷ lệ trên row count |
| “correlation là tương quan hai cột” | Hiểu sai pg_stats | Heap order so với value order |
| “Histogram chứa mọi giá trị” | Coi stats như raw data | Histogram là bucket boundaries |
| “MCV liệt kê toàn bộ giá trị” | Bỏ qua tail values | Chỉ chứa common values |
| “ANALYZE tự tạo index” | Mong đợi access path không tồn tại | Stats chỉ hỗ trợ planner chọn path |
| “Có index thì planner phải dùng” | Ép plan sai | Seq Scan có thể rẻ hơn |
| “Extended stats mô tả mọi join” | Estimate join vẫn sai | Chủ yếu hỗ trợ restrictions trên một relation |
| “Dependencies là constraint” | Dữ liệu sai vẫn vào bảng | Enforce bằng constraints |
| “ANALYZE parent tự luôn chạy sau partition load” | Parent stats stale | Analyze parent theo lịch/đợt load |
| “Autoanalyze chạy ngay khi vượt threshold” | Bỏ qua worker scheduling | Threshold không phải deadline |
| “last_autoanalyze NULL là lỗi” | Báo động giả | Bảng có thể chưa đến ngưỡng |
| “pg_stat_user_tables n_live_tup là COUNT chính xác” | Dùng estimates làm business totals | Đây là ước lượng |
| “ANALYZE chỉ tác động planner, không tốn tài nguyên” | Gây I/O/CPU contention | Sampling vẫn đọc blocks |
| “ANALYZE chặn mọi DML” | Tránh chạy khi không cần | Thường cho phép DML, nhưng vẫn cần lock/tài nguyên |
| “SKIP_LOCKED chạy thành công nghĩa mọi table đã analyze” | Bỏ sót relation bị lock | Kiểm tra output/progress và chạy lại |
| “pg_statistic có thể update tay” | Corrupt catalog/planner state | Dùng ANALYZE và DDL chính thức |
| “ANALYZE materialized view làm refresh data” | Dữ liệu vẫn cũ | REFRESH trước, ANALYZE sau |
| “ANALYZE view thường giống table” | Không có storage relation riêng | Analyze base tables/expressions |
| “ANALYZE foreign table luôn local/rẻ” | Remote sampling có thể đắt | Xem FDW capabilities |
| “Estimate sai luôn do stats” | Bỏ qua index/cost/locks/I/O | Tìm node đầu tiên sai |
| “EXPLAIN ANALYZE chỉ mô phỏng” | DML có thể thay đổi dữ liệu | Nó thực thi query thật |
| “Generic plan luôn tối ưu cho mọi parameter” | Skew gây plan không phù hợp | Test hot/rare values |
| “Stats vừa analyze là không thể stale” | Writes mới đổi distribution | Theo dõi write rate và autoanalyze |
| “Đổi cost settings giải quyết stats stale” | Che nguyên nhân | Tách cardinality và cost model |
| “ANALYZE thay authorization” | Query vẫn permission denied/RLS | Quyền SQL độc lập |

---

## 28. Checklist vận hành thống kê

### 28.1. Trước ANALYZE

- [ ] Xác định relation và cột query-critical.
- [ ] Xem thời điểm analyze và số modifications từ lần gần nhất.
- [ ] Xác định data distribution đã thay đổi ra sao.
- [ ] Kiểm tra autovacuum/autoanalyze có bật và có bị backlog không.
- [ ] Xem query plans/estimated vs actual rows.
- [ ] Kiểm tra workload đang chạy, I/O và locks.
- [ ] Nếu bảng partitioned, xác định cần analyze parent, partitions hay cả hai.

### 28.2. Khi tuning statistics

- [ ] Chỉ tăng target cho cột có evidence.
- [ ] Dùng extended stats khi predicates nhiều cột thực sự tương quan.
- [ ] Phân biệt dependencies, ndistinct và MCV.
- [ ] Expression stats không thay expression index.
- [ ] Không dùng extended stats thay constraints.
- [ ] Kiểm tra query có generic plan hoặc unsupported predicates.
- [ ] So sánh plans với nhiều parameter values đại diện.

### 28.3. Sau ANALYZE

- [ ] Xác nhận last_analyze/last_autoanalyze hoặc progress/output phù hợp.
- [ ] Đọc pg_stats/pg_stats_ext.
- [ ] EXPLAIN lại query đại diện.
- [ ] So estimated rows và actual rows.
- [ ] Đo execution latency, buffers và workload impact.
- [ ] Không giữ target cao nếu không có cải thiện đo được.
- [ ] Theo dõi stats freshness sau khi workload tiếp tục ghi.

---

## 29. Runbook khi query regression do planner estimates

1. Lưu query text và parameters đại diện, không để lộ secrets/PII.
2. Lấy EXPLAIN (ANALYZE, BUFFERS) trên môi trường an toàn hoặc với workload có thể chịu được.
3. Tìm node thấp nhất có estimated rows lệch mạnh so với actual.
4. Xác định predicate/cột/biểu thức gây sai.
5. Đọc pg_stats và pg_stats_ext; xem last_analyze, n_mod_since_analyze.
6. Kiểm tra skew, MCV coverage, histogram, NULL fraction và distinct estimate.
7. Nếu predicates nhiều cột, xem extended statistics có phù hợp và có được planner hỗ trợ cho loại clause đó.
8. Nếu query dùng prepared statement, so generic/custom plans và nhiều parameter values.
9. Chạy ANALYZE thủ công nếu stats stale; chỉ tăng target/extended stats khi có evidence.
10. Đo lại plan và latency; không chỉ dựa vào một lần chạy cache warm.
11. Nếu estimate tốt nhưng query vẫn chậm, chuyển điều tra sang indexes, cost settings, locks, I/O, memory, parallelism và concurrency.
12. Ghi lại thay đổi DDL/target và rollback path.
13. Theo dõi workload sau deploy để đảm bảo query khác không regression.
14. Nếu data distribution thay đổi liên tục, điều chỉnh autoanalyze thresholds hoặc data model/partitioning theo workload.

---

## 30. Tài liệu tham khảo PostgreSQL

Khi triển khai, ưu tiên tài liệu chính thức đúng major version server:

- [PostgreSQL — ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): cú pháp và mục đích ANALYZE.
- [PostgreSQL — Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): thống kê cơ bản, MCV, histogram, extended statistics và statistics target.
- [PostgreSQL — pg_stats](https://www.postgresql.org/docs/current/view-pg-stats.html): view thống kê theo cột.
- [PostgreSQL — pg_statistic](https://www.postgresql.org/docs/current/catalog-pg-statistic.html): catalog nội bộ.
- [PostgreSQL — CREATE STATISTICS](https://www.postgresql.org/docs/current/sql-createstatistics.html): multivariate/expression statistics.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): statistics target cho columns và table reloptions.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum, autoanalyze và vacuum.
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): thresholds, scale factors và workers.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): estimated costs/rows và ANALYZE output.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_user_tables, progress views và activity.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partitioned tables và planning.
- [PostgreSQL — Foreign Data](https://www.postgresql.org/docs/current/ddl-foreign-data.html): foreign tables và FDW behavior.

Đường dẫn /current/ trỏ tài liệu phiên bản mới nhất; một số tính năng như expression statistics, progress view fields, privileges và autoanalyze counters phụ thuộc major version. Kiểm tra docs tương ứng server thật.

---

## 31. Tổng kết

**ANALYZE cung cấp dữ liệu thống kê để PostgreSQL ước lượng số rows và chọn execution plan.** Một query có thể chậm không phải vì SQL thay đổi, mà vì distribution đã thay đổi trong khi planner vẫn dựa vào stats cũ hoặc quá đơn giản.

Các nguyên tắc quan trọng:

1. **ANALYZE và VACUUM khác nhau:** ANALYZE thu thập planner stats; VACUUM xử lý dead tuples, visibility và freezing. VACUUM ANALYZE làm cả hai.
2. **Statistics dựa trên sampling:** MCV, histogram, distinct count và null fraction là ước lượng, không phải số đếm nghiệp vụ chính xác.
3. **Planner dùng stats để ước lượng cardinality/selectivity:** những estimates này ảnh hưởng scan, join order, join methods, sort, aggregate và parallel plans.
4. **MCV mô tả hot values; histogram mô tả range distribution:** cả hai có giới hạn về độ chi tiết và sampling.
5. **n_distinct có thể âm:** độ lớn là tỷ lệ trên số rows, ví dụ -1 gần unique.
6. **correlation trong pg_stats là thứ tự heap so với giá trị cột:** không phải tương quan giữa hai business columns.
7. **Statistics target điều chỉnh độ chi tiết:** tăng target chỉ khi evidence cho thấy stats chưa mô tả đủ; không đặt cực cao cho mọi cột.
8. **Extended statistics mô tả quan hệ nhiều cột/biểu thức:** dependencies, ndistinct và MCV phục vụ các loại estimates khác nhau, chủ yếu trên cùng relation.
9. **Expression stats khác expression index:** một cái giúp estimate, cái kia tạo access path.
10. **Autoanalyze hoạt động theo threshold và scheduling:** vượt threshold không có nghĩa chạy ngay; partitioned parent/temp tables có những lưu ý riêng.
11. **Sau bulk load/backfill/distribution changes, ANALYZE có thể cần chạy thủ công:** nhất là trước khi chuyển workload query-critical.
12. **EXPLAIN so estimate và actual:** tìm node thấp nhất sai nhiều, xem pg_stats và predicates trước khi thay cost settings.
13. **ANALYZE tiêu thụ tài nguyên:** sampling đọc blocks và cập nhật catalogs; lên lịch theo workload.
14. **Không ép planner để che vấn đề:** Seq Scan có thể là plan tốt; xem indexes, cost model, I/O và concurrency nếu estimates đã hợp lý.
15. **Statistics không enforce data integrity:** dùng constraints để bảo vệ business rules, không dùng dependencies stats thay FK/UNIQUE/CHECK.
16. **Không thao tác trực tiếp pg_statistic:** dùng ANALYZE, ALTER TABLE và CREATE/ALTER STATISTICS.
17. **Tối ưu có kiểm chứng:** lưu plan trước/sau, thử nhiều parameter values, đo latency/buffers và quan sát regression trên workload khác.

Quy trình thực tế: **phát hiện query regression → EXPLAIN ANALYZE → tìm cardinality estimate sai đầu tiên → đọc pg_stats và freshness → ANALYZE hoặc tune target/extended stats đúng cột → đo lại plan và workload → theo dõi autoanalyze để giữ thống kê phù hợp khi dữ liệu tiếp tục thay đổi**.

---

## 32. Bài tập thực hành

Các bài dùng schema analyze_lab trong lab nếu không nói khác. Câu lệnh tạo/sửa dữ liệu chỉ chạy trong database thử nghiệm. Các bài yêu cầu đọc EXPLAIN nên phân biệt rõ EXPLAIN thuần và EXPLAIN ANALYZE thực thi query thật.

### Bài 1 — ANALYZE là gì?

Giải thích ANALYZE làm gì cho planner và hai việc nó không làm.

### Bài 2 — ANALYZE và VACUUM

Một bảng vừa DELETE 5 triệu rows. Khi nào cần VACUUM, khi nào cần ANALYZE, khi nào có thể dùng VACUUM ANALYZE?

### Bài 3 — Planner statistics

Kể ít nhất năm thông tin planner cần ước lượng trước khi chọn execution plan.

### Bài 4 — null_frac

Một cột coupon_code có null_frac=0.8. Ước lượng tỷ lệ NULL và giải thích query IS NULL có thể dùng thông tin này thế nào.

### Bài 5 — avg_width

Một cột payload JSONB có avg_width tăng từ 100 bytes lên 2.000 bytes sau import. Điều gì có thể thay đổi trong planner cost estimates?

### Bài 6 — n_distinct âm

Giải thích ý nghĩa n_distinct=-0.25. Nếu bảng có khoảng 2 triệu rows, distinct count ước lượng khoảng bao nhiêu?

### Bài 7 — MCV

Cột status có MCV paid với frequency 0.7. Query WHERE status='paid' có selectivity ước lượng khoảng bao nhiêu theo thống kê này? Vì sao giả định uniform distinct values có thể sai?

### Bài 8 — Histogram

Histogram_bounds có phải danh sách toàn bộ giá trị cột không? Nêu hai dạng query planner dùng histogram để ước lượng.

### Bài 9 — Correlation

pg_stats.correlation=-0.95 có nghĩa customer_id và region tương quan âm mạnh không? Giải thích chính xác ý nghĩa.

### Bài 10 — Statistics target

Viết SQL tăng statistics target cho customer_id lên 500, chạy ANALYZE riêng cột đó và đưa cột về default.

### Bài 11 — Target cao

Vì sao target 10.000 cho mọi cột có thể là quyết định kém? Nêu ít nhất ba trade-offs.

### Bài 12 — Sampling

Vì sao hai lần ANALYZE có thể tạo stats hơi khác nhau? Khi nào sampling có thể bỏ lỡ hot/rare values?

### Bài 13 — ANALYZE sau COPY

Bạn vừa COPY 50 triệu rows vào bảng rỗng. Vì sao nên xem xét ANALYZE trước khi mở traffic đọc lớn?

### Bài 14 — Autoanalyze threshold

Với threshold=50 và scale_factor=0.1, bảng 1 triệu rows có ngưỡng khái quát bao nhiêu modifications? Vì sao không thể coi đó là deadline chính xác?

### Bài 15 — Autoanalyze chưa chạy

n_mod_since_analyze lớn hơn threshold ước lượng nhưng last_autoanalyze chưa cập nhật. Nêu ít nhất bốn lý do có thể.

### Bài 16 — pg_stat_user_tables

Viết query liệt kê 10 tables có n_mod_since_analyze lớn nhất, cùng last_analyze và last_autoanalyze.

### Bài 17 — Extended statistics

Một query lọc country='VN' và currency='VND'. Hai cột có tương quan. Viết CREATE STATISTICS thu thập dependencies và MCV, rồi ANALYZE.

### Bài 18 — Dependencies không phải constraint

Nếu extended dependency cho thấy zip_code gần như xác định city, dữ liệu zip_code/city sai có bị database ngăn không? Cần dùng gì để enforce?

### Bài 19 — ndistinct đa biến

Vì sao số groups của GROUP BY country,currency không nhất thiết bằng distinct(country) × distinct(currency)? Loại extended stats nào giúp estimate?

### Bài 20 — Extended stats và joins

Extended statistics của bảng users có tự mô tả quan hệ join giữa users và orders không? Nêu giới hạn chính.

### Bài 21 — Expression statistics

Viết mẫu CREATE STATISTICS cho lower(email). Nó thay expression index không? Vì sao?

### Bài 22 — pg_stats

Viết query xem null_frac, n_distinct, MCV, histogram và correlation của cột customer_id trong schema app, table orders.

### Bài 23 — pg_statistic

Có nên UPDATE trực tiếp pg_statistic để sửa n_distinct không? Vì sao?

### Bài 24 — Partitioned table

Một parent partitioned table nhận thêm 20 triệu rows vào partition mới. Vì sao có thể cần ANALYZE cả partition lẫn parent? Autoanalyze parent có chắc tự chạy không?

### Bài 25 — Temporary table

Một session nạp 1 triệu rows vào TEMP table rồi join với bảng lớn. Vì sao cần cân nhắc ANALYZE temp table?

### Bài 26 — Foreign table

Vì sao ANALYZE foreign table có thể tốn network/remote I/O? Phụ thuộc vào thành phần nào?

### Bài 27 — Materialized view

Sau REFRESH MATERIALIZED VIEW, planner vẫn có thể estimate sai. Cần làm gì tiếp theo?

### Bài 28 — EXPLAIN rows

Một plan node có rows=1.000, actual rows=100.000, loops=1. Tỷ lệ sai estimate là bao nhiêu? Điều gì có thể bị ảnh hưởng phía trên node?

### Bài 29 — Loops

Một inner node có actual rows=10 và loops=500. Ước lượng tổng số rows được xử lý xấp xỉ bao nhiêu? Vì sao không được bỏ qua loops?

### Bài 30 — EXPLAIN vs EXPLAIN ANALYZE

Sự khác nhau quan trọng nhất giữa hai lệnh là gì? Vì sao không chạy EXPLAIN ANALYZE một UPDATE production chỉ để xem plan?

### Bài 31 — Generic plan

Một customer_id có 40% rows, phần lớn customers chỉ có vài rows. Vì sao generic prepared plan có thể không tốt cho mọi parameter values? Nêu cách chẩn đoán.

### Bài 32 — Stats đã mới nhưng query vẫn chậm

Nêu ít nhất năm nguyên nhân khác ngoài stats stale có thể làm query chậm.

### Bài 33 — Cost settings

Nếu planner chọn Seq Scan sau ANALYZE, có nên giảm random_page_cost ngay không? Đưa ra trình tự điều tra hợp lý.

### Bài 34 — SKIP_LOCKED

ANALYZE (SKIP_LOCKED) chạy nhưng một relation bị bỏ qua do lock. Có được đánh dấu relation đó đã cập nhật stats không? Làm gì tiếp?

### Bài 35 — Phân biệt stats freshness và vacuum

Một bảng có last_analyze rất mới nhưng n_dead_tup cao. Có thể kết luận bảng đã sạch không? Vì sao?

### Bài 36 — ANALYZE permissions

Một application role không có quyền chạy ANALYZE. Có nên cấp superuser cho role này không? Đề xuất cách tổ chức quyền.

### Bài 37 — ANALYZE và concurrency

ANALYZE không block DML thông thường nhưng vẫn có thể ảnh hưởng workload bằng cách nào? Nêu các resources/locks liên quan.

### Bài 38 — Bảng write-heavy

Một bảng nhận 100.000 updates/giây, autoanalyze liên tục nhưng stats nhanh stale. Nêu ba hướng thiết kế/điều chỉnh.

### Bài 39 — Tuning target theo evidence

Viết quy trình từ phát hiện estimate sai tới quyết định tăng target và kiểm chứng kết quả.

### Bài 40 — Case study

Một query lọc region='north' AND status='paid' ước lượng 500 rows nhưng thực tế 300.000 rows. Mỗi cột riêng lẻ có MCV hợp lý. Giải thích giả định độc lập có thể gây lỗi thế nào và đề xuất extended stats.

### Bài 41 — Parent/partition stats

Một partition mới có distribution status khác hoàn toàn các partitions cũ. Query qua parent bị estimate sai. Hãy nêu các bước kiểm tra và analyze.

### Bài 42 — Import và plan regression

Sau import 100 triệu rows, query báo cáo chuyển từ Hash Join sang Nested Loop và chạy chậm hơn. Hãy viết quy trình chẩn đoán có thứ tự.

### Bài 43 — Stats và data integrity

Một developer muốn dùng dependencies statistics để bảo đảm mỗi customer_id chỉ có một region. Vì sao thiết kế này sai? Đề xuất constraint/model phù hợp.

### Bài 44 — Lựa chọn lệnh

Ghép tình huống với hành động phù hợp: (a) chỉ stats cũ sau bulk INSERT, (b) nhiều dead tuples sau UPDATE/DELETE, (c) vừa REFRESH materialized view, (d) tạo multivariate stats object, (e) query dùng TEMP table vừa nạp.

### Bài 45 — Runbook production

Query quan trọng bị regression sau backfill, actual rows cao gấp 200 lần estimates, API p99 tăng. Viết runbook an toàn để xác định nguyên nhân, cập nhật stats và xác nhận không gây regression ở workload khác.

---

## 33. Lời giải — bài 1 đến 25

### Bài 1 — ANALYZE

ANALYZE lấy mẫu và cập nhật planner statistics như null fraction, distinct values, MCV và histogram. Nó **không** xóa dead tuples và **không** tạo index. Nó cũng không thay đổi business values trong bảng.

### Bài 2 — VACUUM và ANALYZE

DELETE 5 triệu rows tạo dead tuple versions cần được reclaim khi snapshots không còn cần. VACUUM hỗ trợ cleanup/reuse. ANALYZE cập nhật thống kê nếu distribution/row count thay đổi. VACUUM ANALYZE phù hợp nếu cần cả hai. ANALYZE riêng không giải quyết bloat.

### Bài 3 — Planner estimates

Ví dụ: total rows, distinct values, NULL fraction, MCV/frequency, histogram range distribution, physical correlation, row width, số groups, join cardinality/selectivity.

### Bài 4 — null_frac

0.8 tương đương khoảng 80% rows NULL theo stats. Planner có thể dùng tỷ lệ này để ước lượng WHERE coupon_code IS NULL/IS NOT NULL. Đây là ước lượng sampling, không phải exact count.

### Bài 5 — avg_width

Row width ước lượng tăng có thể làm cost sort/hash/materialize/scan và memory footprint ước lượng thay đổi. Nếu stats cũ còn 100 bytes trong khi payload thực 2.000 bytes, planner có thể đánh giá thấp chi phí xử lý nhiều rows.

### Bài 6 — n_distinct âm

-0.25 biểu thị distinct values xấp xỉ 25% số rows. Với 2 triệu rows, khoảng 500.000 distinct values. Đây là ước lượng, không phải COUNT DISTINCT chính xác.

### Bài 7 — MCV

Nếu paid có frequency 0.7, selectivity của điều kiện status='paid' có thể xấp xỉ 70%. Nếu distribution skew, giả định uniform giữa tất cả distinct values sẽ bỏ lỡ hot values như paid.

### Bài 8 — Histogram

Histogram không chứa mọi giá trị; nó chứa bucket boundaries của phần dữ liệu phù hợp, thường sau khi tách MCV/NULL. Planner dùng để ước lượng range predicates như amount BETWEEN 100 AND 200 hoặc timestamp nằm trong khoảng.

### Bài 9 — Correlation

Không. -0.95 mô tả quan hệ giữa **physical heap order** và thứ tự giá trị cột theo hướng ngược chiều mạnh. Nó không mô tả tương quan giữa customer_id và region.

### Bài 10 — Target riêng

~~~sql
ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS 500;

ANALYZE app.orders (customer_id);

ALTER TABLE app.orders
ALTER COLUMN customer_id
SET STATISTICS -1;
~~~

Lệnh cuối trả về default target. Nếu muốn giữ target 500 sau khi tune thành công thì không chạy bước reset; cần ghi lại migration/config.

### Bài 11 — Target cực cao

- ANALYZE tốn sampling/I/O/CPU hơn.
- Catalog statistics lớn hơn.
- Autoanalyze có thể tốn tài nguyên nhiều hơn.
- Lợi ích không tăng nếu query không dùng loại stats đó.
- Sampling vẫn có sai số; target cao không bảo đảm plan tốt.
- Các cột không liên quan bị tăng overhead vô ích.

### Bài 12 — Sampling

Sampling có yếu tố ngẫu nhiên; hai lần lấy mẫu khác nhau có thể tạo MCV/histogram estimates hơi khác. Giá trị rất hiếm có thể không được sample; một hot value ở partition nhỏ cũng có thể bị đánh giá thấp nếu sample không đại diện.

### Bài 13 — ANALYZE sau COPY

Bảng rỗng trước import có thể có stats không tồn tại hoặc không đại diện cho distribution mới. Planner có thể ước lượng sai rows, join order và scan type. ANALYZE sau load giúp cập nhật stats trước khi query/reporting workload tăng.

### Bài 14 — Threshold

50 + 0.1 × 1.000.000 = **100.050 modifications** theo công thức khái quát. Không phải deadline chính xác vì row counts là estimates, worker scheduling/counters/table options và version ảnh hưởng thời điểm chạy.

### Bài 15 — Autoanalyze chưa chạy

Các lý do có thể:
1. Worker đang bận hoặc số workers giới hạn.
2. Autovacuum bị tắt hoặc table option khác default.
3. Stats counters vừa reset hoặc chưa được cập nhật.
4. Relation đang bị lock/maintenance.
5. Table là partitioned parent/temp table với semantics đặc biệt.
6. Autovacuum naptime/scheduling chưa tới.
7. Stats không được theo dõi theo giả định bạn đang dùng.

### Bài 16 — Top 10 modified tables

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC NULLS LAST
LIMIT 10;
~~~

Các counters là estimates và phụ thuộc version/stats reset.

### Bài 17 — Extended statistics

~~~sql
CREATE STATISTICS app.users_country_currency_stats
    (dependencies, mcv)
ON country, currency
FROM app.users;

ANALYZE app.users;
~~~

MCV mô tả tổ hợp phổ biến, dependencies mô tả một số functional relationships. Nếu query còn GROUP BY country,currency và số nhóm ước lượng sai, có thể thêm ndistinct.

### Bài 18 — Dependency không enforce data

Không. Extended stats chỉ giúp planner ước lượng. Dùng UNIQUE/FK/CHECK hoặc bảng mapping và transaction logic phù hợp để đảm bảo zip_code/city consistency. Chọn constraint đúng với cardinality nghiệp vụ.

### Bài 19 — ndistinct đa biến

Các cột có thể tương quan nên không phải mọi country đều có mọi currency. Multivariate ndistinct giúp ước lượng số tổ hợp distinct và số groups thay vì nhân độc lập hai cardinalities.

### Bài 20 — Extended stats và join

Không. Extended stats được tạo trên columns/expressions của một relation và chủ yếu giúp estimates cho restrictions trên relation đó. Join selectivity còn phụ thuộc join keys, uniqueness, constraints và thống kê từng bảng; không có cross-table extended stats tổng quát.

### Bài 21 — Expression statistics

~~~sql
CREATE STATISTICS app.customer_lower_email_stats
ON (lower(email))
FROM app.customers;

ANALYZE app.customers;
~~~

Nó không thay expression index. Stats giúp planner estimate; index tạo access path để lookup nhanh theo lower(email).

### Bài 22 — pg_stats

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname='app'
  AND tablename='orders'
  AND attname='customer_id';
~~~

Nếu không có row, kiểm tra quyền, relation name và việc ANALYZE/statistics target.

### Bài 23 — Không sửa pg_statistic trực tiếp

Không. Đây là catalog nội bộ với representation phụ thuộc version. Tự update có thể tạo stats không nhất quán. Dùng ALTER TABLE SET STATISTICS, CREATE STATISTICS và ANALYZE.

### Bài 24 — Partitioned table

Analyze partition để có stats cục bộ và parent để cập nhật global/inherited stats phục vụ queries nhắm parent. Autoanalyze parent không được bảo đảm tự chạy chỉ vì partitions có nhiều inserts; lên lịch/manual ANALYZE parent.

### Bài 25 — TEMP table

Planner cần biết cardinality, distribution và distinct values của temp table để chọn join order/method hợp lý. Autovacuum không quản lý temp tables như permanent relations; session nên chạy ANALYZE sau khi nạp lượng rows đáng kể trước join quan trọng.

---

## 34. Lời giải — bài 26 đến 45

### Bài 26 — Foreign table

ANALYZE có thể cần FDW lấy mẫu hoặc đọc dữ liệu từ remote server. Chi phí phụ thuộc FDW implementation, remote query pushdown, network latency, source size và credentials/permissions. Không mặc định đây là một lần đọc catalog local.

### Bài 27 — Materialized view

Sau REFRESH, chạy ANALYZE materialized view để thu thập stats theo distribution mới nếu planner cần:

~~~sql
REFRESH MATERIALIZED VIEW app.monthly_sales;
ANALYZE app.monthly_sales;
~~~

ANALYZE không refresh dữ liệu; thứ tự là refresh trước rồi analyze.

### Bài 28 — Estimate sai 100 lần

Actual 100.000 / estimated 1.000 = **100 lần**. Node phía trên có thể chọn join method/order sai, memory estimate sai hoặc tạo nhiều vòng nested loop hơn dự kiến.

### Bài 29 — Loops

10 rows mỗi loop × 500 loops ≈ **5.000 rows** tổng qua node. EXPLAIN thường hiển thị actual rows trung bình theo loop; bỏ qua loops có thể đánh giá thấp công việc thực tế.

### Bài 30 — EXPLAIN vs EXPLAIN ANALYZE

EXPLAIN thuần chỉ hiển thị plan ước lượng, không thực thi query. EXPLAIN ANALYZE thực thi query và đo actual rows/time. Với UPDATE production, nó thực sự thay đổi dữ liệu và chạy triggers; không dùng như một lệnh preview an toàn.

### Bài 31 — Generic plan

Generic plan không chuyên biệt theo parameter values. Nếu customer 1 chiếm 40% rows còn customer khác chỉ có vài rows, một plan chung có thể không tối ưu cho cả hai. Chẩn đoán bằng EXPLAIN EXECUTE với các parameters đại diện, xem plan caching/driver settings và so custom/generic plan khi phù hợp.

### Bài 32 — Query vẫn chậm dù stats mới

Các nguyên nhân khác:
- Index thiếu/sai hoặc không phù hợp predicate.
- Lock waits/deadlocks.
- Disk/network latency.
- CPU contention.
- Sort/hash spill do memory.
- Row width lớn/TOAST.
- Triggers/functions tốn thời gian.
- Cost parameters không phản ánh storage/cache.
- Generic prepared plan.
- Concurrent workload và cache cold.

### Bài 33 — Seq Scan không có nghĩa stats sai

Không giảm random_page_cost ngay. Trình tự:
1. EXPLAIN ANALYZE/BUFFERS trên workload an toàn.
2. So estimates và actual rows.
3. Xác minh stats freshness/distribution.
4. Kiểm tra index có selective, query cần nhiều columns/rows không.
5. Kiểm tra cache/I/O và cost model.
6. Chỉ tune cost parameters sau benchmark đại diện, không ép planner cho một query riêng.

### Bài 34 — SKIP_LOCKED

Không. Relation bị bỏ qua chưa được analyze theo lệnh đó. Kiểm tra output/progress, chờ DDL/maintenance lock kết thúc rồi chạy ANALYZE lại. Không đánh dấu stats freshness hoàn tất nếu relation chưa được xử lý.

### Bài 35 — Stats mới không có nghĩa bảng sạch

Không. last_analyze chỉ cho biết thống kê được thu thập gần đây; n_dead_tup cao có thể vẫn tồn tại. VACUUM/autovacuum xử lý dead tuples. Hai hoạt động có mục tiêu riêng.

### Bài 36 — Quyền ANALYZE

Không cấp superuser cho application. Dùng DBA/maintenance role có quyền phù hợp theo PostgreSQL version, hoặc giao maintenance job cho role owner/MAINTAIN privilege khi hỗ trợ. Ứng dụng runtime giữ least privilege.

### Bài 37 — ANALYZE và concurrency

ANALYZE đọc blocks và tính toán stats nên tiêu thụ I/O/CPU/memory; cập nhật system catalogs; lấy relation lock có thể xung đột với một số DDL/maintenance; nhiều analyze đồng thời gây I/O burst. Nó thường cho phép DML thông thường nhưng không miễn phí.

### Bài 38 — Write-heavy table

Hướng xử lý:
1. Tune table-level analyze threshold/scale factor theo write rate và cost.
2. Chọn cột quan trọng/target hợp lý, tránh stats không cần thiết.
3. Partition dữ liệu theo workload/time để giới hạn phạm vi stats và analyze.
4. Lịch ANALYZE thủ công có điều tiết cho các query-critical distributions.
5. Tối ưu query/model nếu distribution biến đổi nhanh hơn khả năng thống kê.
6. Theo dõi autoanalyze backlog và worker capacity.

Không đặt scale factor cực nhỏ cho mọi bảng mà không tính I/O.

### Bài 39 — Quy trình tune target

1. Lấy EXPLAIN ANALYZE và tìm node estimate sai.
2. Xác định cột/predicate.
3. Đọc pg_stats MCV/histogram/n_distinct/null_frac.
4. Xác định skew hoặc tail values chưa được mô tả.
5. Tăng target riêng cột cần thiết.
6. ANALYZE cột/table.
7. So plan/estimates với nhiều parameter values.
8. Đo latency, buffers và tác động của analyze.
9. Giữ thay đổi nếu cải thiện ổn định; nếu không, trả target về default và điều tra nguyên nhân khác.

### Bài 40 — Region và status correlated

Planner có thể nhân selectivity của region='north' và status='paid' như thể hai điều kiện độc lập. Nếu phần lớn orders ở north cũng là paid, kết quả thực tế lớn hơn nhiều so với estimate. Tạo multivariate MCV/dependencies trên cùng bảng:

~~~sql
CREATE STATISTICS app.orders_region_status_stats
    (mcv, dependencies)
ON region, status
FROM app.orders;

ANALYZE app.orders;
~~~

Sau đó EXPLAIN lại query. Dependencies không hỗ trợ mọi predicate; MCV có thể hữu ích với combinations phổ biến.

### Bài 41 — Parent/partition stats

1. Kiểm tra query nhắm parent hay trực tiếp partition.
2. Xem pg_stat_user_tables cho từng partition và parent.
3. Đọc pg_stats với inherited flag phù hợp.
4. Chạy ANALYZE trên partition mới.
5. Chạy ANALYZE parent để cập nhật global/inherited stats nếu query nhắm parent.
6. EXPLAIN lại query với partition pruning.
7. Theo dõi autoanalyze; không giả định parent được tự cập nhật.

### Bài 42 — Import làm join plan regression

1. Lưu query/parameters và EXPLAIN ANALYZE/BUFFERS trước/sau nếu có.
2. Tìm node scan đầu tiên estimate sai.
3. Kiểm tra last_analyze/n_mod_since_analyze và row counts.
4. Chạy ANALYZE trên tables/cột bị thay đổi.
5. Kiểm tra MCV/histogram/n_distinct và skew mới.
6. Kiểm tra correlated predicates, tạo extended stats nếu phù hợp.
7. Kiểm tra generic prepared plan và parameters.
8. Đo lại plan, actual rows, buffers, p95/p99.
9. Nếu estimates đã đúng mà plan vẫn xấu, xem indexes/cost settings/locks/I/O.
10. Theo dõi workload khác để tránh fix một query gây regression nơi khác.

### Bài 43 — Dependencies không enforce uniqueness

Extended stats không ngăn hai rows có cùng customer_id nhưng region khác nhau. Dùng UNIQUE constraint, mapping table có primary key/foreign key hoặc mô hình chuẩn hóa. Chọn constraint phù hợp nếu mỗi customer chỉ có một region; nếu region có lịch sử theo thời gian thì cần effective dates/versioning thay vì unique đơn giản.

### Bài 44 — Ghép lệnh

- (a) Chỉ stats cũ sau bulk INSERT → **ANALYZE**.
- (b) Nhiều dead tuples sau UPDATE/DELETE → **VACUUM**, và ANALYZE nếu stats cần cập nhật; có thể dùng **VACUUM ANALYZE**.
- (c) Vừa REFRESH materialized view → **ANALYZE materialized view** sau REFRESH.
- (d) Tạo multivariate stats object → **ANALYZE relation** để thu thập dữ liệu cho object.
- (e) TEMP table vừa nạp nhiều rows → **ANALYZE temp table** trong session trước query joins quan trọng.

### Bài 45 — Runbook production

1. Ghi query text/parameters, thời điểm backfill, deployment và metrics; redact secrets.
2. Lấy EXPLAIN (ANALYZE, BUFFERS) trong điều kiện an toàn hoặc query đại diện.
3. Tìm node thấp nhất có actual rows gấp 200 lần estimate.
4. Xác định predicate/cột và xem pg_stats, last_analyze, n_mod_since_analyze.
5. Chạy ANALYZE cột/table đã thay đổi nếu stats stale.
6. Nếu correlated columns, tạo extended stats phù hợp; nếu skew, cân nhắc target riêng.
7. Nếu generic plan, kiểm tra prepared statement/driver và nhiều parameter classes.
8. So plan và runtime sau thay đổi, không chỉ với một parameter.
9. Xác minh query khác trên cùng bảng không regression; quan sát API p99, CPU/I/O, buffers, locks.
10. Nếu không cải thiện, điều tra index design, cost settings, I/O, memory spills, locks và application fetch.
11. Ghi lại target/extended stats migration, quyền, rollback path và owner.
12. Theo dõi autoanalyze để stats không stale lại ngay sau backfill.

---

## 35. Sơ đồ tư duy chọn thống kê

~~~mermaid
flowchart TD
    A["Planner estimate sai"] --> B{"Một cột?"}
    B -- "Có" --> C["Xem null_frac, MCV, histogram, n_distinct"]
    C --> D{"Skew/rare values chưa mô tả?"}
    D -- "Có" --> E["Tăng target cột + ANALYZE"]
    D -- "Không" --> F["Kiểm tra expression, generic plan, operator"]
    B -- "Nhiều cột cùng bảng?" --> G["Extended statistics: dependencies / MCV / ndistinct"]
    B -- "Join nhiều bảng?" --> H["Stats từng bảng, keys, uniqueness, FK, join predicates"]
    E --> I["EXPLAIN lại, đo workload"]
    F --> I
    G --> I
    H --> I
~~~
