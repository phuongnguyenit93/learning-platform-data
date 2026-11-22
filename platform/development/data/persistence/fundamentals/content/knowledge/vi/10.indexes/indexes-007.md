# Độ chọn lọc và phân bố giá trị

Trong chương **Chỉ mục** của **DATA_PERSISTENCE_FUNDAMENTALS**, hiểu độ chọn lọc (*selectivity*) là bước quan trọng để quyết định chỉ mục nào thực sự giúp truy vấn nhanh hơn. Hai cột có cùng kiểu dữ liệu, cùng số giá trị khác nhau, thậm chí cùng một chỉ mục B-tree, vẫn có thể tạo ra các kế hoạch truy vấn rất khác nhau vì **giá trị xuất hiện với tần suất khác nhau**.

Ở tầng persistence của ứng dụng Java, quyết định tạo chỉ mục cần dựa trên câu lệnh SQL thực tế, số hàng mà điều kiện lọc trả về, phân bố dữ liệu theo từng nhóm người dùng và chi phí đọc/ghi. Bài này tập trung vào cách hiểu các yếu tố đó, cách trình tối ưu truy vấn (*query optimizer*) ước lượng chúng và cách kiểm chứng bằng dữ liệu.

## 1. Các khái niệm dễ bị nhầm lẫn

Giả sử bảng `orders` có tổng cộng \(N\) hàng và điều kiện lọc \(P\) khớp \(M\) hàng. Trong bài này, **độ chọn lọc của điều kiện** được định nghĩa là:

\[
S(P) = \frac{M}{N}, \qquad 0 \leq S(P) \leq 1.
\]

Theo định nghĩa này, **tỷ lệ càng nhỏ thì điều kiện càng chọn lọc**: `WHERE id = 123` có thể chọn đúng một hàng, trong khi `WHERE status = 'SHIPPED'` có thể chọn phần lớn bảng. Nếu nói “điều kiện có độ chọn lọc cao”, cần kiểm tra người viết đang dùng quy ước nào; trong tài liệu kỹ thuật, cách diễn đạt này đôi khi chỉ điều kiện lọc mạnh mặc dù tỷ lệ \(M/N\) nhỏ.

| Thuật ngữ | Ý nghĩa | Ví dụ với 1.000.000 đơn hàng |
| --- | --- | --- |
| **Số giá trị phân biệt** (*NDV*, *number of distinct values*) | Có bao nhiêu giá trị khác nhau trong một cột | `status` có 4 giá trị |
| **Cardinality** | Có thể chỉ số hàng của tập kết quả hoặc NDV của cột, tùy ngữ cảnh | Bảng có 1.000.000 hàng; kết quả có 5.000 hàng |
| **Độ chọn lọc của điều kiện** \(S(P)\) | Tỷ lệ hàng thỏa điều kiện so với toàn bảng | `status = 'CANCELLED'` khớp 5.000 hàng, \(S=0{,}005\) |
| **Tỷ lệ phân biệt** (*distinctness ratio*) | NDV chia tổng số hàng | `status`: \(4/10^6\) |
| **Phân bố giá trị** | Mỗi giá trị chiếm bao nhiêu hàng và các giá trị phụ thuộc nhau ra sao | `'SHIPPED'` nhiều hơn `'CANCELLED'` rất nhiều |

Một số tài liệu gọi **“index selectivity”** là tỷ lệ `NDV / tổng số hàng`; theo quy ước đó, **tỷ lệ càng lớn thì cột càng phân biệt tốt**. Đây là đại lượng khác với \(S(P)\) đang dùng để phân tích một điều kiện `WHERE`. Không nên dùng hai tỷ lệ thay thế cho nhau.

## 2. Cùng một cột, mỗi giá trị có thể có độ chọn lọc khác nhau

Xét tập dữ liệu minh họa gồm **1.000.000** đơn hàng:

| `status` | Số hàng | Tỷ lệ \(S(\text{status}=v)\) |
| --- | ---: | ---: |
| `SHIPPED` | 900.000 | 90% |
| `PENDING` | 50.000 | 5% |
| `FAILED` | 45.000 | 4,5% |
| `CANCELLED` | 5.000 | 0,5% |
| **Tổng** | **1.000.000** | **100%** |

Nếu chỉ biết `status` có bốn giá trị và **giả định phân bố đều**, ta có thể ước lượng mỗi giá trị chiếm 25% bảng. Nhưng dữ liệu thực tế lệch mạnh: tìm `SHIPPED` cần đọc phần lớn bảng, còn tìm `CANCELLED` chỉ cần tìm một phần rất nhỏ. Một chỉ mục trên `status` có thể hữu ích với truy vấn thứ hai nhưng không mang lại lợi ích tương ứng cho truy vấn thứ nhất.

Ví dụ:

```sql
-- Điều kiện ít chọn lọc theo tỷ lệ M/N: khớp khoảng 900.000 hàng.
SELECT id, tenant_id, created_at
FROM orders
WHERE status = 'SHIPPED';

-- Điều kiện chọn lọc hơn: khớp khoảng 5.000 hàng.
SELECT id, tenant_id, created_at
FROM orders
WHERE status = 'CANCELLED';
```

Với truy vấn đầu, trình tối ưu có thể chọn quét tuần tự bảng (*sequential scan*) vì sử dụng chỉ mục để tìm rất nhiều hàng rồi truy cập các trang dữ liệu tương ứng có thể tốn kém hơn. Với truy vấn sau, truy cập qua chỉ mục có thể rẻ hơn. Đây là **khả năng lựa chọn**, không phải một quy tắc cố định: kích thước hàng, số trang đĩa, dữ liệu đã nằm trong bộ nhớ đệm, `SELECT` những cột nào, khả năng *index-only scan*, `ORDER BY` và `LIMIT` đều ảnh hưởng đến chi phí.

Vì vậy, kết luận “cột chỉ có bốn giá trị nên tuyệt đối không tạo chỉ mục” là sai. Điều quan trọng là **truy vấn tìm giá trị nào, trong phạm vi nào, và cần lấy bao nhiêu hàng**.

## 3. Các dạng phân bố giá trị và tác động đến chỉ mục

### 3.1. Phân bố đều

Nếu 100.000 khách hàng có số đơn gần tương đương, điều kiện `customer_id = ?` thường khớp một lượng hàng khá ổn định. Ước lượng đơn giản \(1/\mathrm{NDV}\) có thể là điểm khởi đầu chấp nhận được cho bộ tối ưu, mặc dù vẫn cần kiểm tra trên dữ liệu thật.

### 3.2. Phân bố lệch (*skew*) và đuôi dài

Trong hệ thống đa khách thuê (*multi-tenant*), một số `tenant_id` có thể sở hữu phần lớn đơn hàng, còn đa số tenant chỉ có vài trăm đơn. Truy vấn theo tenant lớn và tenant nhỏ có cùng cấu trúc SQL nhưng chi phí rất khác nhau. Một giá trị phổ biến có thể phù hợp với quét bảng hoặc một chiến lược khác, trong khi giá trị hiếm có thể được phục vụ rất tốt bằng chỉ mục.

Các trường hợp thường gặp là sản phẩm “bán chạy” chiếm phần lớn giao dịch, một số người dùng tạo nhiều sự kiện, một trạng thái chiếm ưu thế hoặc một vài khóa ngoại tập trung rất nhiều hàng. **NDV cao không bảo đảm phân bố đều**.

### 3.3. Phân bố thay đổi theo thời gian

Dữ liệu sự kiện thường tập trung ở những ngày gần đây. Điều kiện `created_at >= ...` trong 24 giờ có thể trả ít hàng ở giai đoạn đầu vận hành nhưng trả hàng triệu hàng khi hệ thống lớn lên. Một điều kiện lọc có “khoảng thời gian ngắn” không mặc nhiên chọn lọc nếu phần lớn dữ liệu nằm trong khoảng đó.

### 3.4. Giá trị `NULL`

Một cột có thể có NDV lớn nhưng 80% hàng mang `NULL`. Khi đó `WHERE attribute IS NULL` ít chọn lọc, trong khi `WHERE attribute = 'một_giá_trị_hiếm'` có thể rất chọn lọc. Thống kê về tỷ lệ `NULL` cần được xét riêng, thay vì suy ra từ NDV.

### 3.5. Tương quan giữa các cột

Hai điều kiện lọc hiếm khi hoàn toàn độc lập. Giả sử:

- Toàn bảng có 1.000.000 đơn; `CANCELLED` chiếm 0,5% (5.000 đơn).
- Tenant `42` có 10.000 đơn (1% toàn bảng).
- Riêng tenant `42`, có 1.500 đơn `CANCELLED` (15% của tenant này).

Nếu **giả định độc lập**, số hàng khớp cả hai điều kiện sẽ là:

\[
1.000.000 \times 0{,}01 \times 0{,}005 = 50 \text{ hàng}.
\]

Thực tế là **1.500 hàng**, cao gấp 30 lần. Công thức đúng là:

\[
P(A \cap B) = P(A) \times P(B \mid A).
\]

Ở đây, \(A\) là `tenant_id = 42`, \(B\) là `status = 'CANCELLED'`. Khi các cột có quan hệ phụ thuộc, lấy độ chọn lọc riêng lẻ rồi nhân với nhau có thể gây sai lệch lớn. Sai số ước lượng số hàng (*row estimate*) ảnh hưởng tới thứ tự join, loại scan và lựa chọn chỉ mục.

## 4. Trình tối ưu truy vấn biết gì về phân bố dữ liệu?

Hệ quản trị cơ sở dữ liệu thường không đếm chính xác toàn bộ hàng cho từng điều kiện trước mỗi lần chạy truy vấn; thay vào đó, nó dựa trên **thống kê** đã thu thập. Tùy hệ quản trị và phiên bản, thống kê có thể gồm:

| Loại thống kê | Dùng để làm gì | Giới hạn cần nhớ |
| --- | --- | --- |
| Tổng số hàng, số trang | Ước lượng chi phí quét bảng | Có thể lạc hậu khi dữ liệu tăng nhanh |
| NDV của cột | Ước lượng điều kiện bằng (`=`) trên nhiều giá trị | Không biểu diễn hết dữ liệu bị lệch |
| Giá trị phổ biến nhất (*MCV*, *most common values*) cùng tần suất | Ước lượng tốt hơn cho những giá trị xuất hiện nhiều | Không nhất thiết ghi nhận mọi giá trị hiếm |
| Histogram / ranh giới các khoảng | Ước lượng điều kiện so sánh, khoảng và ngày tháng | Chịu ảnh hưởng của lấy mẫu và độ phân giải |
| Tỷ lệ `NULL` | Ước lượng `IS NULL` / `IS NOT NULL` | Không mô tả tương quan với cột khác |
| Thống kê nhiều cột (*extended statistics*, nếu được hỗ trợ) | Cải thiện một số ước lượng khi các cột phụ thuộc nhau | Mỗi hệ quản trị hỗ trợ các dạng và trường hợp khác nhau |

**Thống kê chỉ giúp ước lượng; bản thân nó không bảo đảm dùng chỉ mục.** Trình tối ưu còn cân nhắc chi phí truy cập trang bảng, cách sắp xếp vật lý của dữ liệu, số hàng cần trả, thao tác sắp xếp/join và chi phí ngẫu nhiên so với tuần tự. Cũng không có ngưỡng phổ quát kiểu “lọc dưới 10% thì phải dùng index”.

Thống kê có thể lạc hậu sau khi nhập dữ liệu hàng loạt, xóa nhiều bản ghi hoặc thay đổi mạnh cơ cấu trạng thái. Một histogram được tạo lúc `CANCELLED` chỉ chiếm 0,5% sẽ không còn đại diện tốt nếu sau sự cố, tỷ lệ này tăng lên 30%.

## 5. Thực hành đo đạc trên PostgreSQL

Phần này dùng **PostgreSQL** làm ví dụ cụ thể. Các con số trong mục 2 và 3 là **dữ liệu minh họa**, không phải kết quả đo từ một bảng có sẵn. Cú pháp xem thống kê và hiển thị kế hoạch của MySQL, SQL Server hay Oracle khác PostgreSQL; nguyên tắc phân tích vẫn tương tự.

### 5.1. Xác định truy vấn và phân bố hiện tại

Giả sử ứng dụng có bảng sau:

```sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    status       VARCHAR(16) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);
```

Sau khi nạp dữ liệu đại diện cho tải thực tế, đếm số hàng cho từng trạng thái:

```sql
SELECT status,
       COUNT(*) AS row_count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent_of_table
FROM orders
GROUP BY status
ORDER BY row_count DESC;
```

Truy vấn này cho biết **tỷ lệ thực tế trên toàn bảng**, không phải NDV đơn thuần. Với bảng lớn, thao tác đếm có thể tốn tài nguyên; nên thực hiện trên môi trường thử nghiệm hoặc bản sao dữ liệu phù hợp khi cần phân tích đầy đủ.

Để xem tenant nào có nhiều đơn và tỷ lệ hủy của từng tenant, có thể dùng:

```sql
SELECT tenant_id,
       COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_orders,
       ROUND(
           100.0 * COUNT(*) FILTER (WHERE status = 'CANCELLED')
           / NULLIF(COUNT(*), 0), 2
       ) AS cancelled_percent
FROM orders
GROUP BY tenant_id
ORDER BY total_orders DESC
LIMIT 20;
```

Chỉ xem 20 tenant nhiều đơn nhất **không chứng minh** mọi tenant đều có phân bố như vậy. Nếu ứng dụng có tenant đặc biệt quan trọng, cần kiểm tra đúng các tenant đó.

### 5.2. Đọc thống kê mà PostgreSQL đã thu thập

```sql
ANALYZE orders;

SELECT attname,
       n_distinct,
       null_frac,
       most_common_vals,
       most_common_freqs,
       histogram_bounds
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'created_at');
```

`n_distinct` cho biết ước lượng số giá trị phân biệt; trong PostgreSQL, giá trị âm mang ý nghĩa tỷ lệ giá trị phân biệt so với số hàng (được biểu diễn theo quy ước riêng của PostgreSQL), không phải số âm thật của NDV. `most_common_vals` và `most_common_freqs` giúp nhận ra các giá trị phổ biến; `histogram_bounds` phục vụ ước lượng khoảng cho phần phân bố tương ứng. Các trường có thể để trống khi không phù hợp hoặc thống kê chưa đủ.

PostgreSQL tự động thu thập thống kê nhờ autovacuum/autoanalyze trong nhiều cấu hình thông dụng. `ANALYZE` thủ công phù hợp khi vừa nạp hoặc biến đổi dữ liệu đáng kể và cần kiểm tra lại kế hoạch; trên bảng lớn vẫn có chi phí vận hành.

Nếu có tương quan quan trọng giữa `tenant_id` và `status`, PostgreSQL hỗ trợ tạo thống kê nhiều cột:

```sql
CREATE STATISTICS stats_orders_tenant_status (dependencies, mcv)
    ON tenant_id, status
    FROM orders;

ANALYZE orders;
```

Thống kê mở rộng có thể giúp ước lượng một số điều kiện kết hợp, nhưng **không thay cho chỉ mục** và không xử lý được mọi loại tương quan hay mọi dạng truy vấn. Cần kiểm tra lại `EXPLAIN` sau khi thu thập thống kê.

### 5.3. So sánh số hàng ước lượng và số hàng thực tế

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, created_at
FROM orders
WHERE status = 'CANCELLED';
```

Khi đọc kế hoạch, hãy tìm các thông tin sau:

1. **Loại truy cập:** `Seq Scan`, `Index Scan`, `Index Only Scan` hoặc `Bitmap Heap Scan` (có thể đi kèm `Bitmap Index Scan`).
2. **`rows` ước lượng** so với **`actual rows`** ở nút tương ứng. Nếu chênh lệch lớn, cần kiểm tra phân bố, dữ liệu lệch, tương quan và độ mới của thống kê.
3. **`Buffers`** và thời gian thực thi, để đánh giá lượng trang được đọc/đụng tới thay vì chỉ nhìn tổng thời gian một lần chạy.
4. **Điều kiện thực sự được áp dụng tại đâu:** `Index Cond` và `Filter` không luôn tương đương về lượng công việc.

`EXPLAIN (ANALYZE, BUFFERS)` **thực sự thực thi** câu SQL để đo số liệu. Với ví dụ `SELECT` ở trên điều này phù hợp, nhưng không nên dùng tùy tiện với câu lệnh ghi dữ liệu trong môi trường sản xuất. Kết quả thời gian có thể thay đổi theo cache, đồng thời và tải hệ thống.

## 6. Chọn chỉ mục theo điều kiện kết hợp và cách truy vấn dữ liệu

Độ chọn lọc của một cột riêng lẻ chưa đủ để thiết kế chỉ mục. Cần bắt đầu từ **mẫu truy vấn được thực thi nhiều**, nhất là tổ hợp `WHERE`, `ORDER BY` và `LIMIT`.

Ví dụ, màn hình quản lý đơn của từng tenant thường lấy 50 đơn bị hủy mới nhất:

```sql
SELECT id, status, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'CANCELLED'
ORDER BY created_at DESC
LIMIT 50;
```

Một **chỉ mục ứng viên** là:

```sql
CREATE INDEX idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at DESC);
```

Hai cột đầu hỗ trợ tra cứu bằng giá trị chính xác; phần `created_at DESC` hỗ trợ lấy các bản ghi gần nhất theo đúng thứ tự trong phạm vi `tenant_id` và `status` đã chọn. Khi chỉ cần 50 hàng, cơ sở dữ liệu có cơ hội dừng sớm. Dẫu vậy, quyết định sử dụng chỉ mục vẫn tùy dữ liệu và kế hoạch thực tế.

Chỉ mục trên không nhất thiết tối ưu cho truy vấn **chỉ lọc tenant rồi sắp xếp theo ngày**, vì `status` nằm giữa `tenant_id` và `created_at`. Nếu truy vấn sau được dùng thường xuyên, `(tenant_id, created_at DESC)` là một ứng viên khác cần cân nhắc:

```sql
SELECT id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Với nhu cầu đặc biệt thường xuyên chỉ xem những đơn bị hủy, PostgreSQL còn hỗ trợ **partial index**:

```sql
CREATE INDEX idx_orders_cancelled_by_tenant_date
    ON orders (tenant_id, created_at DESC)
    WHERE status = 'CANCELLED';
```

Chỉ mục này chứa các hàng thỏa điều kiện `CANCELLED`, nên có thể nhỏ hơn một chỉ mục đầy đủ nếu trạng thái đó hiếm. Nhưng nó chỉ phù hợp khi bộ tối ưu chứng minh được điều kiện truy vấn bao hàm điều kiện của partial index. Với prepared statement có `status = ?`, đặc biệt khi cơ sở dữ liệu dùng **generic plan**, không thể mặc định chỉ mục riêng cho `CANCELLED` sẽ luôn được sử dụng.

**Không nên tạo đồng loạt cả ba chỉ mục chỉ vì chúng xuất hiện trong ví dụ.** Mỗi chỉ mục chiếm dung lượng, làm tăng chi phí `INSERT`, `UPDATE`, `DELETE` và cần được bảo trì. Hãy chọn tập chỉ mục nhỏ nhất đáp ứng các truy vấn quan trọng đã đo đạc.

| Mẫu truy vấn | Dữ liệu cần kiểm tra | Hướng đánh giá |
| --- | --- | --- |
| `status = 'SHIPPED'` | Chiếm phần lớn bảng hay không | Quét tuần tự có thể hợp lý hơn tra chỉ mục rồi lấy rất nhiều hàng |
| `status = 'CANCELLED'` | Tỷ lệ hủy và số hàng trả về | Chỉ mục đơn cột hoặc partial index có thể đáng thử |
| `tenant_id = ? AND status = ?` | Mức lệch giữa các tenant; tương quan hai cột | Kiểm tra chỉ mục ghép, thống kê nhiều cột và `EXPLAIN` cho nhiều giá trị tham số |
| `tenant_id = ? ORDER BY created_at DESC LIMIT 50` | Số đơn mỗi tenant; thứ tự dữ liệu | Cân nhắc `(tenant_id, created_at DESC)` để lọc và lấy hàng theo thứ tự |
| `created_at >= ? AND created_at < ?` | Phần trăm dữ liệu trong khoảng cần tìm | Kiểm tra thống kê khoảng và lợi ích của chỉ mục theo thời gian |

## 7. Liên hệ với lớp persistence trong Java

Một repository dùng JDBC có thể truyền cùng một câu SQL cho tenant lớn và tenant nhỏ, hoặc cho `SHIPPED` và `CANCELLED`:

```java
String sql = """
    SELECT id, status, created_at
    FROM orders
    WHERE tenant_id = ? AND status = ?
    ORDER BY created_at DESC
    LIMIT ?
    """;

List<Long> orderIds = new ArrayList<>();
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, tenantId);
    statement.setString(2, status);
    statement.setInt(3, pageSize);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            orderIds.add(rs.getLong("id"));
        }
    }
}
```

Tham số hóa giúp truyền giá trị an toàn và cho phép tái sử dụng câu lệnh. Tuy nhiên, **cùng một SQL không có nghĩa là mọi tham số đều có độ chọn lọc như nhau**. Tùy hệ quản trị và cơ chế cache kế hoạch, truy vấn tham số hóa có thể dùng kế hoạch riêng theo giá trị hoặc kế hoạch chung. Vì thế, khi phát hiện độ trễ chênh lệch lớn giữa các tenant/trạng thái, hãy thử phân tích kế hoạch với **giá trị phổ biến, giá trị hiếm và các tenant nhiều dữ liệu**, thay vì chỉ thử một bộ tham số “điển hình”.

ORM cũng không thay đổi nguyên tắc này: cần xem SQL thực tế do ORM phát ra, bao gồm join, điều kiện lọc, sắp xếp, phân trang và các điều kiện được thêm tự động cho tenant hoặc bảo mật dữ liệu.

Một chi tiết liên quan là **khả năng sử dụng chỉ mục của biểu thức lọc**. Chẳng hạn:

```sql
-- Có thể khó tận dụng chỉ mục B-tree thông thường trên created_at
-- khi cột được biến đổi bởi hàm:
SELECT id FROM orders WHERE DATE(created_at) = DATE '2026-11-22';

-- Thường dễ tận dụng điều kiện phạm vi trên created_at hơn:
SELECT id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-22 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-23 00:00:00+07';
```

Hai cách viết chỉ tương đương khi cách hiểu **múi giờ của `DATE(created_at)`** trùng với khoảng `+07` mong muốn; nếu phiên làm việc dùng múi giờ khác, cần điều chỉnh rõ ràng. Ví dụ này cho thấy đánh giá độ chọn lọc cũng phải đi cùng cách biểu diễn điều kiện SQL.

## 8. Quy trình đánh giá trước khi thêm chỉ mục

1. **Ghi lại truy vấn thực tế** và mục tiêu độ trễ: SQL, bộ tham số thường gặp, `ORDER BY`, `LIMIT`, số hàng kết quả và tần suất gọi.
2. **Đo phân bố dữ liệu** trên môi trường đại diện: tổng số hàng, NDV, tần suất giá trị phổ biến/hiếm, tỷ lệ `NULL`, dữ liệu theo tenant và theo thời gian.
3. **Đọc kế hoạch hiện tại** bằng `EXPLAIN`; khi an toàn và phù hợp thì dùng `EXPLAIN ANALYZE` để so sánh số hàng ước lượng với thực tế.
4. **Kiểm tra thống kê** trước khi kết luận thiếu chỉ mục. Nếu thống kê quá cũ, làm mới rồi đánh giá kế hoạch lại.
5. **Thử chỉ mục ứng viên** trên dữ liệu và tải đại diện, so sánh cả thời gian truy vấn, số trang truy cập, chi phí ghi và dung lượng tăng thêm.
6. **Kiểm tra nhiều phân khúc**: tenant lớn/nhỏ, trạng thái phổ biến/hiếm, khoảng thời gian nóng/lạnh. Theo dõi lại khi dữ liệu tăng hoặc phân bố thay đổi.

### Tự kiểm tra

**Câu hỏi 1.** Cột `status` có NDV = 4. Có đủ cơ sở để khẳng định chỉ mục trên cột này vô ích không?

**Gợi ý trả lời:** Không. Nếu một trạng thái hiếm và thường xuyên được truy vấn, chỉ mục vẫn có thể hữu ích; còn `ORDER BY`, `LIMIT`, số cột lấy ra và chi phí truy cập bảng cũng ảnh hưởng đến quyết định.

**Câu hỏi 2.** Bộ tối ưu dự đoán 50 hàng cho `tenant_id = 42 AND status = 'CANCELLED'`, nhưng thực tế là 1.500. Nguyên nhân có thể là gì?

**Gợi ý trả lời:** Hai điều kiện có tương quan: tenant `42` có tỷ lệ hủy cao hơn trung bình. Hãy xem phân bố theo tenant, độ mới của thống kê và khả năng dùng thống kê nhiều cột; sau đó đo lại kế hoạch.

**Câu hỏi 3.** Tại sao không nên tạo chỉ mục cho mọi cột xuất hiện trong `WHERE`?

**Gợi ý trả lời:** Các chỉ mục làm tăng chi phí ghi và dung lượng; nhiều truy vấn cần chỉ mục ghép để vừa lọc vừa sắp xếp; một điều kiện trả phần lớn bảng có thể vẫn được xử lý tốt hơn bằng quét tuần tự. Phải dựa trên phân bố và truy vấn thực tế.

**Điểm cần ghi nhớ:** Độ chọn lọc là đặc tính của **điều kiện trên phân bố dữ liệu hiện tại**, không phải nhãn cố định gắn cho tên cột. Hiểu phân bố, đo sai lệch giữa số hàng ước lượng và thực tế, rồi xác nhận bằng kế hoạch truy vấn là cách đưa ra quyết định chỉ mục có cơ sở cho tầng persistence.
