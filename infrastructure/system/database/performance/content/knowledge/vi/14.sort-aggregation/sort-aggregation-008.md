# Tổng hợp trước và bảng tổng hợp cho báo cáo lặp lại

Trong chương **Sắp xếp và tổng hợp** của module **DATABASE_PERFORMANCE**, tổng hợp trước (*pre-aggregation*) là cách tính sẵn các chỉ số thường dùng và lưu kết quả ở mức chi tiết phù hợp để báo cáo có thể đọc ít dữ liệu hơn. Thay vì mỗi lần mở dashboard đều quét hàng triệu giao dịch, join nhiều bảng rồi group và sort lại từ đầu, hệ thống có thể duy trì bảng tổng hợp theo ngày, cửa hàng, sản phẩm hoặc nhóm nghiệp vụ. Báo cáo sau đó truy vấn tập kết quả nhỏ hơn và chỉ thực hiện phần tổng hợp còn lại.

Kỹ thuật này hữu ích khi cùng một phép tổng hợp được chạy lặp lại, dữ liệu nguồn lớn và độ trễ báo cáo là mục tiêu quan trọng. Đổi lại, hệ thống phải trả chi phí tính toán, ghi, lưu trữ và đồng bộ kết quả tổng hợp. Thiết kế tốt cần xác định đúng mức chi tiết, loại chỉ số, quy tắc cập nhật, độ mới dữ liệu và cách đối soát với nguồn gốc.

## 1. Vì sao cần tổng hợp trước?

Giả sử hệ thống bán hàng có bảng giao dịch `sales` với hàng chục triệu dòng. Dashboard thường xuyên hiển thị doanh thu và số đơn theo ngày, cửa hàng và khu vực. Một truy vấn trực tiếp trên dữ liệu chi tiết có thể như sau:

```sql
SELECT CAST(s.sold_at AS date) AS sales_day,
       st.region,
       SUM(s.net_amount) AS revenue,
       COUNT(DISTINCT s.order_id) AS order_count
FROM sales AS s
JOIN stores AS st
  ON st.store_id = s.store_id
WHERE s.sold_at >= :from_time
  AND s.sold_at <  :to_time
  AND s.status = 'COMPLETED'
GROUP BY CAST(s.sold_at AS date), st.region
ORDER BY sales_day, st.region;
```

Mỗi lần chạy, database có thể phải đọc nhiều dòng giao dịch, lọc trạng thái và thời gian, join bảng cửa hàng, tính tổng, đếm và sắp xếp kết quả. Nếu dashboard có nhiều người dùng hoặc tự làm mới liên tục, cùng một lượng công việc có thể được lặp lại nhiều lần.

Có thể tổng hợp dữ liệu một lần ở mức `ngày + cửa hàng`, lưu kết quả, rồi join bảng cửa hàng để báo cáo theo vùng. Khi đó, truy vấn báo cáo đọc số dòng theo ngày/cửa hàng thay vì toàn bộ giao dịch. Nếu cần tổng hợp theo vùng, database chỉ phải cộng các tổng nhỏ hơn.

### 1.1. Lợi ích

- **Giảm lượng dữ liệu đọc:** báo cáo truy cập các dòng tổng hợp thay vì quét toàn bộ bảng chi tiết.
- **Giảm CPU cho group và sort:** nhiều phép tính đã được thực hiện trong bước nạp hoặc cập nhật dữ liệu tổng hợp.
- **Giảm tải cho workload giao dịch:** báo cáo lặp lại có thể chuyển sang bảng tổng hợp hoặc kho phân tích riêng.
- **Thời gian phản hồi ổn định hơn:** kích thước bảng tổng hợp thường tăng chậm hơn nhiều so với bảng giao dịch.
- **Tái sử dụng kết quả:** nhiều dashboard và báo cáo có thể dùng chung một tập chỉ số đã chuẩn hóa.

### 1.2. Chi phí và giới hạn

- Tốn thêm dung lượng lưu trữ và chỉ mục cho dữ liệu tổng hợp.
- Phát sinh CPU, I/O và log khi xây dựng hoặc cập nhật kết quả.
- Có thể xuất hiện độ trễ giữa dữ liệu nguồn và báo cáo.
- Cần xử lý giao dịch đến muộn, cập nhật, hủy và xóa dữ liệu cũ.
- Sai quy tắc tổng hợp có thể làm sai lệch báo cáo trên diện rộng.
- Nhiều mức tổng hợp và nhiều chỉ số có thể làm quy trình ETL/ELT khó quản lý.

Tổng hợp trước chỉ có lợi khi phần chi phí đọc lặp lại được tiết kiệm lớn hơn chi phí tạo và duy trì kết quả. Cần đo toàn bộ workload thay vì chỉ so sánh một lần chạy báo cáo.

## 2. Chọn mức chi tiết (grain) của bảng tổng hợp

Grain là ý nghĩa của một dòng trong bảng tổng hợp. Đây là quyết định quan trọng nhất vì nó xác định thông tin nào còn giữ được và những loại báo cáo nào có thể xây dựng từ dữ liệu đó.

Ví dụ một dòng trong `daily_store_sales` có thể đại diện cho:

> Tổng hợp doanh thu của một cửa hàng trong một ngày, theo một loại tiền tệ và một quy tắc trạng thái giao dịch xác định.

Khóa logic của bảng có thể gồm `(sales_day, store_id, currency_code)`. Các cột đo lường gồm `gross_amount`, `net_amount`, `order_count` và `item_quantity`.

| Grain | Số dòng tương đối | Báo cáo có thể hỗ trợ |
|---|---:|---|
| Ngày + cửa hàng | Thấp | Doanh thu ngày, tháng, quý theo cửa hàng hoặc vùng |
| Ngày + cửa hàng + sản phẩm | Cao hơn | Doanh thu theo sản phẩm, cửa hàng và thời gian |
| Giờ + cửa hàng + sản phẩm | Cao hơn nhiều | Phân tích theo giờ, sản phẩm và cửa hàng |
| Ngày + cửa hàng + kênh bán + loại tiền | Tùy số chiều | Phân tích đa chiều theo kênh và tiền tệ |

Grain càng chi tiết thì càng linh hoạt cho báo cáo, nhưng số dòng, dung lượng và chi phí cập nhật càng lớn. Grain quá thô có thể làm mất khả năng phân tích cần thiết. Ví dụ, nếu chỉ lưu doanh thu theo vùng và ngày, không thể suy ra chính xác doanh thu theo từng cửa hàng khi không còn chiều cửa hàng trong dữ liệu.

### 2.1. Xác định grain trước khi chọn chỉ số

Hãy mô tả grain bằng một câu nghiệp vụ, sau đó xác định khóa duy nhất tương ứng. Ví dụ:

- Một dòng cho mỗi ngày, cửa hàng, sản phẩm và loại tiền.
- Một dòng cho mỗi giờ, tenant và loại sự kiện.
- Một dòng cho mỗi tháng, tài khoản và loại số dư.

Không nên bắt đầu bằng danh sách cột rồi mới đoán ý nghĩa của một dòng. Nếu grain không rõ, nhóm phát triển có thể cộng trùng dữ liệu, lưu các chỉ số không thể kết hợp hoặc không xử lý được dữ liệu đến muộn.

### 2.2. Chọn chiều phân tích cần giữ

Các chiều thường gặp gồm thời gian, cửa hàng, khách hàng, sản phẩm, khu vực, kênh bán và trạng thái. Không nhất thiết đưa mọi chiều vào mọi bảng tổng hợp. Hãy dựa trên các câu hỏi báo cáo thực tế và khả năng kết hợp dữ liệu.

Nếu báo cáo theo vùng thay đổi thường xuyên, có thể giữ `store_id` trong bảng tổng hợp và join sang dimension cửa hàng để lấy vùng hiện tại. Nếu cần báo cáo lịch sử theo vùng tại thời điểm giao dịch, phải lưu hoặc liên kết tới phiên bản dimension có hiệu lực ở thời điểm đó. Nếu chỉ join vùng hiện tại, việc cửa hàng chuyển vùng có thể làm thay đổi báo cáo lịch sử.

## 3. Phân biệt các loại chỉ số tổng hợp

Không phải mọi chỉ số đều có thể cộng từ các tổng nhỏ. Trước khi tạo bảng, cần xác định chỉ số là cộng được, bán cộng được hay không cộng được.

### 3.1. Chỉ số cộng được (additive)

Chỉ số additive có thể cộng theo mọi chiều phù hợp. Ví dụ:

- Tổng doanh thu (`SUM(net_amount)`).
- Tổng số lượng hàng bán (`SUM(quantity)`).
- Số giao dịch (`COUNT(*)`) nếu grain và định nghĩa giao dịch được xác định rõ.
- Tổng chi phí hoặc tổng thuế.

Nếu bảng tổng hợp lưu doanh thu ngày theo cửa hàng, báo cáo doanh thu tháng theo vùng có thể cộng doanh thu của các ngày và cửa hàng trong vùng.

### 3.2. Chỉ số bán cộng được (semi-additive)

Chỉ số semi-additive có thể cộng theo một số chiều nhưng không thể cộng theo mọi chiều. Số dư tài khoản là ví dụ: có thể cộng số dư của nhiều tài khoản tại cùng một thời điểm, nhưng cộng số dư của cùng tài khoản qua nhiều ngày thường không tạo ra một số dư có ý nghĩa.

Với số dư cuối ngày, báo cáo tháng thường cần số dư tại ngày cuối kỳ hoặc số dư trung bình theo định nghĩa nghiệp vụ, không phải tổng tất cả số dư ngày. Cần lưu rõ thời điểm snapshot và quy tắc chọn giá trị.

### 3.3. Chỉ số không cộng được (non-additive)

Một số chỉ số không thể tổng hợp chính xác bằng cách cộng kết quả của các nhóm:

- **Trung bình:** không thể lấy trung bình của các trung bình nếu số quan sát mỗi nhóm khác nhau. Cần lưu `SUM` và `COUNT`, sau đó tính lại `SUM / COUNT`.
- **Tỷ lệ:** cần lưu tử số và mẫu số rồi tính tỷ lệ sau khi gộp. Không cộng hoặc lấy trung bình đơn giản các tỷ lệ nhóm.
- **Số lượng phân biệt:** `COUNT(DISTINCT customer_id)` của các ngày không thể cộng nếu một khách hàng xuất hiện nhiều ngày.
- **Median và percentile:** không thể lấy trung bình các median/percentile nhóm để có kết quả chính xác toàn kỳ. Cần lưu dữ liệu đủ chi tiết, trạng thái thống kê có thể gộp hoặc chấp nhận xấp xỉ có kiểm soát.

Ví dụ lưu trung bình giá trị đơn hàng:

```sql
SELECT sales_day,
       SUM(order_amount) AS amount_sum,
       COUNT(*) AS order_count
FROM orders
GROUP BY sales_day;
```

Khi tính trung bình tháng, dùng:

```sql
SELECT DATE_TRUNC('month', sales_day) AS sales_month,
       SUM(amount_sum) / NULLIF(SUM(order_count), 0) AS avg_order_amount
FROM daily_order_summary
GROUP BY DATE_TRUNC('month', sales_day);
```

Ví dụ trên dùng cú pháp PostgreSQL cho `DATE_TRUNC`; cần đổi hàm ngày theo hệ quản trị đang sử dụng. Ý nghĩa quan trọng là lưu tổng và số lượng, không chỉ lưu trung bình ngày.

### 3.4. Số lượng phân biệt và cấu trúc xấp xỉ

Nếu báo cáo cần số khách hàng duy nhất theo tháng, việc cộng số khách hàng duy nhất mỗi ngày sẽ đếm trùng người mua nhiều ngày. Có ba hướng:

1. Tính lại `COUNT(DISTINCT ...)` từ dữ liệu chi tiết khi cần kết quả chính xác.
2. Lưu tập khóa khách hàng ở mức đủ chi tiết để loại trùng khi tổng hợp phạm vi lớn hơn, chấp nhận chi phí lưu trữ.
3. Dùng cấu trúc thống kê có thể gộp như HyperLogLog nếu nghiệp vụ chấp nhận sai số xấp xỉ đã định lượng.

Không nên thay kết quả chính xác bằng ước lượng mà không công bố sai số, phạm vi áp dụng và cách kiểm chứng.

## 4. Thiết kế bảng tổng hợp

Một bảng tổng hợp nên thể hiện rõ grain, khóa và định nghĩa của từng chỉ số. Ví dụ với PostgreSQL:

```sql
CREATE TABLE daily_store_sales (
    sales_day       date           NOT NULL,
    store_id        bigint         NOT NULL,
    currency_code   char(3)        NOT NULL,
    order_count     bigint         NOT NULL DEFAULT 0,
    item_quantity   numeric(18, 3) NOT NULL DEFAULT 0,
    gross_amount    numeric(20, 2) NOT NULL DEFAULT 0,
    net_amount      numeric(20, 2) NOT NULL DEFAULT 0,
    refreshed_at    timestamptz    NOT NULL,
    PRIMARY KEY (sales_day, store_id, currency_code)
);
```

Khóa chính bảo đảm một dòng cho mỗi tổ hợp grain. Nếu một cửa hàng có thể giao dịch nhiều loại tiền, `currency_code` phải nằm trong grain để tránh cộng những đơn vị tiền tệ khác nhau. Không được cộng trực tiếp VND và USD thành một tổng có ý nghĩa nếu chưa quy đổi theo tỷ giá và thời điểm đã xác định.

### 4.1. Chọn kiểu dữ liệu và quy tắc làm tròn

- Dùng kiểu số nguyên hoặc decimal phù hợp cho tiền tệ; tránh `FLOAT`/`REAL` nếu yêu cầu kết quả tiền chính xác.
- Chọn precision/scale đủ cho tổng lớn hơn giá trị của một giao dịch.
- Xác định làm tròn ở cấp dòng, hóa đơn hay tổng báo cáo; các cách làm tròn khác nhau có thể tạo chênh lệch.
- Lưu múi giờ hoặc quy tắc xác định ngày nghiệp vụ. `DATE` theo UTC có thể khác ngày tại múi giờ cửa hàng.
- Lưu trạng thái hoặc phiên bản quy tắc tính nếu cách xác định doanh thu có thể thay đổi.

### 4.2. Chỉ mục cho bảng tổng hợp

Khóa chính `(sales_day, store_id, currency_code)` hỗ trợ tốt truy vấn bắt đầu bằng khoảng ngày và cửa hàng. Nếu dashboard thường lọc theo cửa hàng rồi theo khoảng ngày, thứ tự khóa có thể cần được điều chỉnh hoặc bổ sung chỉ mục phù hợp:

```sql
CREATE INDEX ix_daily_store_sales_store_day
ON daily_store_sales (store_id, sales_day);
```

Không tạo chỉ mục cho mọi tổ hợp chiều. Mỗi chỉ mục tăng dung lượng và chi phí insert/upsert, đồng thời có thể làm giảm hiệu quả cache. Hãy dùng workload truy vấn thực tế để chọn thứ tự cột, chỉ mục bao phủ và phân vùng.

### 4.3. Partitioning và thời gian lưu trữ

Bảng tổng hợp theo ngày có thể partition theo tháng hoặc năm khi kích thước đủ lớn hoặc cần quản lý vòng đời dữ liệu. Partition pruning giúp truy vấn chỉ đọc phần thời gian cần thiết; partition cũ có thể được archive hoặc loại bỏ theo chính sách.

Partitioning không tự động làm truy vấn nhanh hơn nếu truy vấn không có điều kiện trên partition key hoặc mỗi partition vẫn rất lớn. Với bảng tổng hợp nhỏ, partition có thể làm tăng độ phức tạp mà không mang lại lợi ích đáng kể.

## 5. Xây dựng dữ liệu tổng hợp từ nguồn

Có hai cách phổ biến để tạo bảng tổng hợp:

- **Tổng hợp toàn bộ (full rebuild):** đọc dữ liệu nguồn và tính lại toàn bộ kết quả. Cách này dễ hiểu và thuận lợi khi dữ liệu chưa quá lớn hoặc chạy theo lịch ít thường xuyên.
- **Tổng hợp tăng dần (incremental aggregation):** chỉ xử lý phần dữ liệu mới hoặc phần thay đổi kể từ lần chạy trước. Cách này giảm lượng đọc và tính toán nhưng yêu cầu kiểm soát watermark, trùng lặp, cập nhật, xóa và giao dịch đến muộn.

### 5.1. Full rebuild

Ví dụ tạo lại dữ liệu tổng hợp từ bảng giao dịch:

```sql
INSERT INTO daily_store_sales (
    sales_day,
    store_id,
    currency_code,
    order_count,
    item_quantity,
    gross_amount,
    net_amount,
    refreshed_at
)
SELECT sold_at::date,
       store_id,
       currency_code,
       COUNT(DISTINCT order_id),
       SUM(quantity),
       SUM(gross_amount),
       SUM(net_amount),
       clock_timestamp()
FROM sales
WHERE status = 'COMPLETED'
GROUP BY sold_at::date, store_id, currency_code
ON CONFLICT (sales_day, store_id, currency_code)
DO UPDATE SET
    order_count   = EXCLUDED.order_count,
    item_quantity = EXCLUDED.item_quantity,
    gross_amount  = EXCLUDED.gross_amount,
    net_amount    = EXCLUDED.net_amount,
    refreshed_at  = EXCLUDED.refreshed_at;
```

Đây là ví dụ upsert cho PostgreSQL. Nó cập nhật các nhóm xuất hiện trong nguồn nhưng chưa tự xóa những nhóm không còn dòng phù hợp. Một quy trình rebuild hoàn chỉnh cần xử lý nhóm biến mất, thường bằng bảng staging rồi thay thế dữ liệu trong phạm vi đã tính, hoặc xóa và nạp lại partition/khoảng ngày trong cùng quy trình kiểm soát.

Nếu xóa toàn bộ bảng rồi nạp lại, báo cáo có thể nhìn thấy trạng thái rỗng hoặc dữ liệu chưa đầy đủ tùy cách commit và cách ứng dụng đọc. Có thể nạp vào bảng staging, kiểm tra kết quả rồi hoán đổi/đổi partition hoặc thực hiện transaction phù hợp với khả năng của hệ quản trị.

### 5.2. Incremental aggregation cho dữ liệu chỉ thêm mới

Nếu nguồn là event bất biến, mỗi sự kiện chỉ được ghi một lần và có `batch_id`, có thể tổng hợp delta của batch rồi cộng vào bảng tổng hợp. Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_summary_batches (
    batch_id     bigint PRIMARY KEY,
    processed_at timestamptz NOT NULL
);
```

Mỗi batch cần được nhận diện duy nhất. Có thể dùng một CTE để chỉ tính delta khi batch chưa được ghi nhận:

```sql
BEGIN;

WITH claimed AS (
    INSERT INTO processed_summary_batches (batch_id, processed_at)
    VALUES (:batch_id, clock_timestamp())
    ON CONFLICT (batch_id) DO NOTHING
    RETURNING batch_id
), delta AS (
    SELECT e.sold_at::date AS sales_day,
           e.store_id,
           e.currency_code,
           COUNT(DISTINCT e.order_id) AS order_count,
           SUM(e.quantity) AS item_quantity,
           SUM(e.gross_amount) AS gross_amount,
           SUM(e.net_amount) AS net_amount
    FROM sales_events AS e
    JOIN claimed AS c
      ON c.batch_id = e.batch_id
    WHERE e.status = 'COMPLETED'
    GROUP BY e.sold_at::date, e.store_id, e.currency_code
)
INSERT INTO daily_store_sales (
    sales_day, store_id, currency_code,
    order_count, item_quantity, gross_amount, net_amount, refreshed_at
)
SELECT sales_day, store_id, currency_code,
       order_count, item_quantity, gross_amount, net_amount,
       clock_timestamp()
FROM delta
ON CONFLICT (sales_day, store_id, currency_code)
DO UPDATE SET
    order_count = daily_store_sales.order_count + EXCLUDED.order_count,
    item_quantity = daily_store_sales.item_quantity + EXCLUDED.item_quantity,
    gross_amount = daily_store_sales.gross_amount + EXCLUDED.gross_amount,
    net_amount = daily_store_sales.net_amount + EXCLUDED.net_amount,
    refreshed_at = EXCLUDED.refreshed_at;

COMMIT;
```

Ví dụ giả định `sales_events` chứa các sự kiện hoàn tất bất biến, batch được đóng trước khi xử lý và `batch_id` đại diện cho một tập sự kiện không đổi. Việc ghi nhận batch đã xử lý và cập nhật summary nằm trong cùng transaction: nếu transaction rollback, cả hai cùng rollback; nếu batch được gửi lại, khóa duy nhất ngăn cộng delta lần thứ hai. Cần bảo đảm không có hai batch khác nhau chứa cùng một sự kiện và không đếm trùng `order_id` qua nhiều batch. Nếu một đơn hàng gồm nhiều dòng sản phẩm, `COUNT(DISTINCT order_id)` theo từng batch có thể đếm trùng đơn hàng nếu các dòng của cùng đơn bị tách batch; khi đó cần tổng hợp đơn hàng ở grain phù hợp trước khi cộng.

### 5.3. Watermark và dữ liệu đến muộn

Với nguồn có `created_at` hoặc `updated_at`, có thể dùng watermark để chọn phần dữ liệu cần xử lý. Tuy nhiên, chỉ đọc `created_at > last_watermark` an toàn khi nguồn chỉ thêm mới và không sửa/xóa dữ liệu cũ. Nếu giao dịch có thể được sửa sau khi tạo, watermark theo thời điểm tạo sẽ bỏ sót thay đổi.

Các lựa chọn phổ biến:

- CDC hoặc transaction log capture để nhận biết insert, update và delete.
- Cột `updated_at` có quy tắc cập nhật đáng tin cậy, kết hợp cửa sổ chồng lấn và cơ chế chống xử lý trùng.
- Event bất biến với sự kiện điều chỉnh hoặc đảo bút toán thay cho sửa bản ghi cũ.
- Recompute lại một khoảng ngày gần đây để xử lý dữ liệu đến muộn.

Nếu dùng cửa sổ chồng lấn, phải có khóa chống trùng hoặc cơ chế thay thế kết quả trong phạm vi cửa sổ. Nếu chỉ cộng lại các dòng của ba ngày gần nhất mà không loại delta cũ, số liệu sẽ bị cộng nhiều lần.

### 5.4. Xử lý update và delete

Khi một giao dịch đổi từ `COMPLETED` sang `CANCELLED`, hoặc đổi ngày/cửa hàng, tổng hợp cần loại đóng góp cũ khỏi nhóm trước và thêm đóng góp mới vào nhóm sau. Có thể thực hiện bằng:

1. Đọc before-image và after-image từ CDC.
2. Tạo delta âm cho nhóm cũ và delta dương cho nhóm mới.
3. Gộp delta theo khóa grain.
4. Cập nhật summary và checkpoint CDC trong cùng transaction hoặc bằng cơ chế giao nhận có thể phục hồi.

Với một đơn hàng đổi từ 100 sang 120, delta doanh thu là `-100` ở phiên bản cũ và `+120` ở phiên bản mới, tổng thay đổi ròng là `+20`. Nếu chỉ cộng giá trị mới mà không đảo giá trị cũ, summary sẽ sai.

Đối với delete, phải biết nhóm và giá trị trước khi xóa. Nếu nguồn chỉ giữ trạng thái hiện tại và không lưu lịch sử thay đổi, có thể phải recompute lại nhóm hoặc khoảng thời gian liên quan.

## 6. Đảm bảo tính đúng và khả năng chạy lại

Bảng tổng hợp thường phục vụ nhiều báo cáo nên một lỗi nhỏ có thể lan rộng. Quy trình cần có tính idempotent, khả năng phục hồi và đối soát.

### 6.1. Idempotency

Một batch được xử lý lại sau timeout hoặc lỗi mạng không được cộng số liệu lần thứ hai. Cần định danh batch/sự kiện duy nhất và ghi nhận checkpoint cùng kết quả trong một transaction hoặc một giao thức nhất quán. Không cập nhật watermark trước khi dữ liệu tổng hợp đã commit.

Nếu cập nhật summary và checkpoint nằm ở hai hệ thống khác nhau, cần cơ chế outbox/inbox, trạng thái xử lý hoặc giao thức phục hồi để tránh trường hợp một bên đã commit còn bên kia chưa ghi nhận.

### 6.2. Tính nguyên tử và khả năng nhìn thấy dữ liệu

Báo cáo không nên đọc một phần batch mới trong khi các nhóm khác vẫn chưa cập nhật. Có thể nạp staging, kiểm tra rồi publish bằng transaction, đổi partition hoặc cờ phiên bản snapshot. Khả năng atomic swap và mức khóa phụ thuộc hệ quản trị.

Nếu refresh diễn ra lâu, hãy xác định báo cáo đọc snapshot cũ trong lúc refresh hay phải chờ. Cơ chế MVCC, lock và isolation level có thể ảnh hưởng cách người dùng nhìn thấy dữ liệu. Đừng giả định mọi hệ quản trị đều có cùng semantics refresh.

### 6.3. Đối soát số liệu

Đối soát định kỳ giữa nguồn và summary giúp phát hiện lỗi mất batch, xử lý trùng hoặc quy tắc lọc không nhất quán. Có thể so sánh theo từng ngày/cửa hàng:

```sql
SELECT sold_at::date AS sales_day,
       store_id,
       currency_code,
       SUM(net_amount) AS source_net_amount
FROM sales
WHERE status = 'COMPLETED'
  AND sold_at >= :from_time
  AND sold_at <  :to_time
GROUP BY sold_at::date, store_id, currency_code;
```

So sánh với `daily_store_sales` theo cùng khoảng và cùng định nghĩa trạng thái, múi giờ, tiền tệ và làm tròn. Không chỉ so tổng toàn hệ thống; đối soát theo grain giúp tìm nhóm sai lệch.

Các chỉ số kiểm soát nên gồm:

- Số batch đã nhận, đã xử lý, đang lỗi và đang chờ.
- Watermark nguồn và thời điểm dữ liệu mới nhất đã publish.
- Số dòng hoặc tổng tiền nguồn so với summary theo khoảng.
- Số lượng khóa grain bị thiếu hoặc có giá trị âm bất thường.
- Thời gian refresh, số dòng đọc/ghi và lượng log tạo ra.
- Tỷ lệ báo cáo đọc dữ liệu summary thành công và thời gian phản hồi.

## 7. Materialized view và bảng tổng hợp tự quản lý

Tổng hợp trước có thể được triển khai bằng materialized view do database quản lý hoặc bảng summary do ứng dụng/ETL quản lý. Hai cách có mục đích gần nhau nhưng khác cơ chế cập nhật và vận hành.

| Tiêu chí | Materialized view | Bảng tổng hợp tự quản lý |
|---|---|---|
| Định nghĩa truy vấn | Lưu trong đối tượng view | Nằm trong ETL, procedure hoặc ứng dụng |
| Cập nhật | Full refresh hoặc fast/incremental refresh tùy engine và truy vấn | Do pipeline thiết kế, có thể theo batch, CDC hoặc sự kiện |
| Độ mới dữ liệu | Theo lịch hoặc cơ chế refresh được hỗ trợ | Có thể kiểm soát theo batch và yêu cầu nghiệp vụ |
| Xử lý update/delete | Phụ thuộc khả năng fast refresh và metadata của engine | Có thể thiết kế delta âm/dương hoặc recompute |
| Khả năng quan sát | Theo dõi trạng thái refresh và metadata hệ quản trị | Cần tự xây checkpoint, log và đối soát |
| Tính linh hoạt | Phụ thuộc giới hạn materialized view của sản phẩm | Linh hoạt hơn nhưng nhiều trách nhiệm vận hành hơn |

### 7.1. PostgreSQL materialized view

PostgreSQL hỗ trợ materialized view lưu kết quả truy vấn. Ví dụ:

```sql
CREATE MATERIALIZED VIEW mv_daily_store_sales AS
SELECT sold_at::date AS sales_day,
       store_id,
       currency_code,
       COUNT(DISTINCT order_id) AS order_count,
       SUM(quantity) AS item_quantity,
       SUM(net_amount) AS net_amount
FROM sales
WHERE status = 'COMPLETED'
GROUP BY sold_at::date, store_id, currency_code;

CREATE UNIQUE INDEX ux_mv_daily_store_sales
ON mv_daily_store_sales (sales_day, store_id, currency_code);
```

Làm mới toàn bộ:

```sql
REFRESH MATERIALIZED VIEW mv_daily_store_sales;
```

Để cho phép refresh đồng thời với truy vấn đọc trong điều kiện được hỗ trợ:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_store_sales;
```

`CONCURRENTLY` yêu cầu materialized view đã được populate và có unique index phù hợp bao phủ tất cả dòng; chỉ mục đó không được là partial hoặc expression index. Mỗi materialized view chỉ có thể có một refresh đang chạy tại một thời điểm. Refresh vẫn tính lại kết quả truy vấn theo cơ chế của PostgreSQL, không phải tự động incremental refresh. Nếu cần cập nhật delta thường xuyên, phải thiết kế bảng tổng hợp và pipeline riêng hoặc đánh giá extension phù hợp.

### 7.2. SQL Server indexed view

SQL Server có indexed view: sau khi tạo view với `SCHEMABINDING` và tạo unique clustered index trên view, kết quả được vật hóa và duy trì khi bảng nền thay đổi. Đây là cách hỗ trợ một số truy vấn tổng hợp, nhưng có nhiều giới hạn về biểu thức, join, aggregate, kiểu dữ liệu và tùy chọn `SET`.

Ví dụ đơn giản:

```sql
CREATE VIEW dbo.v_daily_store_sales
WITH SCHEMABINDING
AS
SELECT sales_day,
       store_id,
       COUNT_BIG(*) AS sale_count,
       SUM(net_amount) AS net_amount
FROM dbo.Sales
GROUP BY sales_day, store_id;
GO

CREATE UNIQUE CLUSTERED INDEX CIX_v_daily_store_sales
ON dbo.v_daily_store_sales (sales_day, store_id);
```

Đây là ví dụ khái niệm; bảng nền, kiểu dữ liệu, schema binding và các yêu cầu về `SET` option phải đáp ứng quy tắc indexed view của SQL Server. Indexed view được duy trì cùng DML trên bảng nền, vì vậy insert/update/delete có thể tốn thêm chi phí. Cần đo workload ghi và đọc, kiểm tra edition/phiên bản và xem optimizer có sử dụng indexed view hay không. Với báo cáo phức tạp hoặc cần refresh theo batch, bảng summary tự quản lý có thể phù hợp hơn.

### 7.3. Oracle materialized view

Oracle hỗ trợ materialized view với các lựa chọn refresh như `COMPLETE`, `FAST` hoặc `FORCE`. Fast refresh có thể áp dụng khi truy vấn và metadata đáp ứng điều kiện, thường cần materialized view log trên bảng nguồn đối với các trường hợp phù hợp. Không phải mọi phép join, aggregate hoặc biểu thức đều hỗ trợ fast refresh.

Ví dụ khai báo đơn giản:

```sql
CREATE MATERIALIZED VIEW mv_daily_store_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT TRUNC(sold_at) AS sales_day,
       store_id,
       currency_code,
       SUM(net_amount) AS net_amount
FROM sales
WHERE status = 'COMPLETED'
GROUP BY TRUNC(sold_at), store_id, currency_code;
```

Làm mới theo yêu cầu:

```sql
BEGIN
  DBMS_MVIEW.REFRESH('MV_DAILY_STORE_SALES', 'C');
END;
/
```

Tham số `'C'` yêu cầu complete refresh. Nếu muốn fast refresh, cần thiết kế materialized view log, chọn cú pháp refresh phù hợp và kiểm tra tính đủ điều kiện bằng công cụ/metadata của Oracle. Đo thời gian refresh, lượng redo/undo, khóa và tác động tới workload nguồn.

### 7.4. MySQL và bảng tổng hợp tự quản lý

MySQL Server không cung cấp materialized view tổng quát tương đương cú pháp `CREATE MATERIALIZED VIEW` của một số hệ quản trị khác. Một cách thường dùng là tạo bảng summary và cập nhật bằng scheduled event, procedure, job ETL hoặc ứng dụng.

Ví dụ cấu trúc bảng:

```sql
CREATE TABLE daily_store_sales (
    sales_day DATE NOT NULL,
    store_id BIGINT NOT NULL,
    currency_code CHAR(3) NOT NULL,
    order_count BIGINT NOT NULL DEFAULT 0,
    net_amount DECIMAL(20, 2) NOT NULL DEFAULT 0,
    refreshed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (sales_day, store_id, currency_code)
);
```

MySQL hỗ trợ `INSERT ... ON DUPLICATE KEY UPDATE` để upsert. Tuy nhiên, pipeline vẫn phải tự bảo đảm batch không bị cộng trùng, cập nhật/xóa được phản ánh và checkpoint được lưu bền vững. Cần kiểm tra transaction engine, isolation và DDL theo phiên bản MySQL đang sử dụng.

## 8. Chọn full refresh hay incremental refresh

| Điều kiện | Full refresh phù hợp khi | Incremental phù hợp khi |
|---|---|---|
| Dữ liệu nguồn | Nhỏ hoặc có thể quét nhanh | Rất lớn, chỉ một phần thay đổi mỗi kỳ |
| Tần suất cập nhật | Theo ngày/tuần hoặc ít lần | Liên tục hoặc theo batch ngắn |
| Yêu cầu độ mới | Chấp nhận chờ refresh hoàn tất | Cần cập nhật gần thời gian thực hoặc theo lịch ngắn |
| Logic dữ liệu | Đơn giản, ít sửa/xóa lịch sử | Có CDC, event hoặc quy tắc delta rõ ràng |
| Độ phức tạp vận hành | Muốn quy trình dễ kiểm tra | Có năng lực quản lý watermark, idempotency và đối soát |

Full refresh thường đơn giản hơn và ít rủi ro sai delta, nhưng có thể tạo tải đọc/ghi lớn. Incremental giảm lượng dữ liệu xử lý nhưng yêu cầu xử lý chính xác mọi thay đổi. Nếu dữ liệu cũ ít thay đổi và chỉ ngày gần nhất có thể đến muộn, một chiến lược kết hợp là rebuild lại cửa sổ ngày gần đây và giữ nguyên các kỳ đã chốt.

### 8.1. Cửa sổ sửa đổi gần đây

Một số hệ thống chấp nhận dữ liệu trong ngày có thể thay đổi trong vài ngày sau khi giao dịch phát sinh. Có thể mỗi lần chạy tính lại 3-7 ngày gần nhất rồi thay thế kết quả của các ngày đó. Các ngày cũ hơn được xem là đã chốt và chỉ mở lại khi có quy trình điều chỉnh.

Chiến lược này đơn giản hơn CDC đầy đủ nếu quy tắc nghiệp vụ cho phép giới hạn thời gian đến muộn. Tuy nhiên, phải có cơ chế phát hiện giao dịch sửa ngoài cửa sổ, quy trình mở lại kỳ và đối soát định kỳ để tránh bỏ sót điều chỉnh.

### 8.2. Thứ tự commit và checkpoint

Một batch nên được xử lý theo trình tự:

1. Chọn phạm vi nguồn hoặc batch id.
2. Đọc và chuẩn hóa dữ liệu đầu vào.
3. Tính delta ở đúng grain.
4. Cập nhật summary một cách idempotent.
5. Ghi nhận batch/checkpoint trong cùng transaction hoặc giao thức có thể phục hồi.
6. Commit và công bố watermark mới.

Nếu checkpoint được tăng trước khi summary commit, lỗi giữa chừng có thể làm mất dữ liệu vĩnh viễn vì lần chạy sau bỏ qua phạm vi đó. Nếu summary commit nhưng checkpoint không được ghi, batch có thể bị chạy lại và cộng trùng. Giao dịch nguyên tử hoặc cơ chế deduplication là điều kiện thiết yếu.

## 9. Tối ưu truy vấn báo cáo trên bảng tổng hợp

Khi bảng summary đã có, báo cáo vẫn cần chỉ mục và SQL phù hợp. Ví dụ truy vấn theo khoảng ngày và cửa hàng:

```sql
SELECT sales_day,
       SUM(net_amount) AS revenue,
       SUM(order_count) AS order_count
FROM daily_store_sales
WHERE store_id = :store_id
  AND sales_day >= :from_day
  AND sales_day <  :to_day
  AND currency_code = :currency
GROUP BY sales_day
ORDER BY sales_day;
```

Hãy kiểm tra:

- Index có hỗ trợ điều kiện equality trước và range sau theo thứ tự phù hợp không.
- Số dòng summary được đọc so với số dòng được trả về.
- Có sort thừa do thứ tự index không đáp ứng `ORDER BY` không.
- Có thể dùng covering index mà không làm chỉ mục quá rộng không.
- Có partition pruning nếu bảng summary được partition theo ngày không.
- Có cần join dimension sau khi đã giảm số dòng hay có thể lưu khóa dimension ở grain thích hợp.

Không nên lưu sẵn mọi tổ hợp chiều để tránh join. Mỗi bảng tổng hợp bổ sung làm tăng công việc refresh và nguy cơ số liệu không nhất quán. Hãy ưu tiên grain đủ linh hoạt, sau đó thêm summary chuyên biệt khi workload có bằng chứng cần thiết.

## 10. Theo dõi và kiểm chứng hiệu năng

Để đánh giá tổng hợp trước, cần đo cả truy vấn báo cáo và quy trình duy trì dữ liệu.

| Nhóm đo | Chỉ số |
|---|---|
| Độ trễ báo cáo | p50, p95, p99, timeout và tỷ lệ lỗi |
| Hiệu quả truy vấn | Elapsed, CPU, logical/physical reads, số dòng scan, sort và spill |
| Chi phí cập nhật | Thời gian batch, rows/second, CPU, I/O, log/redo/undo |
| Độ mới dữ liệu | Khoảng cách giữa thời điểm nguồn commit và thời điểm summary được publish |
| Độ chính xác | Sai lệch giữa nguồn và summary theo grain, số batch thiếu/trùng |
| Dung lượng | Kích thước summary, index, staging, log và vùng lưu lịch sử |
| Ảnh hưởng workload | p95/p99 giao dịch OLTP khi refresh hoặc ETL chạy |

### 10.1. Benchmark trước và sau

Chọn các truy vấn báo cáo phổ biến, chạy trên cùng tập dữ liệu và cùng điều kiện tải. Ghi lại kế hoạch thực thi và số liệu trước khi tạo summary. Sau khi triển khai, chạy lại các truy vấn trên bảng tổng hợp và đo thêm chi phí ETL/refresh.

Không chỉ so thời gian một truy vấn. Ví dụ, báo cáo giảm từ 8 giây xuống 300 ms nhưng refresh tiêu thụ CPU và I/O trong giờ cao điểm làm giao dịch tăng p99 gấp đôi thì giải pháp chưa chắc phù hợp. Có thể cần chuyển refresh sang batch nhỏ hơn, chạy trên replica, thay đổi lịch hoặc tối ưu cách nạp.

### 10.2. Đối soát và cảnh báo

Thiết lập cảnh báo khi:

- Watermark không tiến triển hoặc độ trễ summary vượt SLO.
- Batch lỗi lặp lại hoặc có batch bị bỏ qua.
- Tổng doanh thu/số lượng nguồn và summary lệch quá ngưỡng.
- Summary có giá trị âm bất thường hoặc khóa grain trùng.
- Refresh vượt thời gian dự kiến hoặc chiếm quá nhiều I/O/CPU.
- Kích thước bảng hoặc chỉ mục tăng nhanh ngoài dự báo.

Đối với chỉ số tiền tệ, đối soát cần cùng quy tắc làm tròn, tỷ giá, múi giờ, trạng thái giao dịch và xử lý hoàn tiền. Chênh lệch có thể do quy tắc nghiệp vụ khác nhau chứ không chỉ do lỗi kỹ thuật.

## 11. Ví dụ chọn chiến lược cho báo cáo doanh thu

Một dashboard hiển thị doanh thu theo ngày, cửa hàng và vùng. Bảng nguồn có 200 triệu dòng, dữ liệu phát sinh liên tục; giao dịch có thể bị hoàn tiền hoặc điều chỉnh trong 48 giờ sau khi hoàn tất. Dashboard được làm mới mỗi phút và yêu cầu dữ liệu trễ tối đa 3 phút.

Một thiết kế có thể gồm:

1. Bảng giao dịch rowstore tiếp tục phục vụ ghi và tra cứu chi tiết.
2. Luồng CDC hoặc event ghi nhận insert, update và trạng thái hoàn tiền.
3. Pipeline tổng hợp theo `ngày + cửa hàng + loại tiền` trong các batch ngắn.
4. Mỗi thay đổi dùng before-image/after-image để tạo delta âm/dương, hoặc rebuild lại cửa sổ hai ngày gần nhất nếu khối lượng cho phép.
5. Summary được cập nhật cùng checkpoint; batch id có unique constraint để chống chạy lặp.
6. Dashboard đọc summary, join dimension cửa hàng để lấy vùng và lọc theo khoảng ngày.
7. Job đối soát hằng ngày so sánh nguồn và summary theo từng ngày/cửa hàng/loại tiền.

Các phép đo cần xác nhận:

- Dashboard đạt p95/p99 theo SLO.
- Độ trễ CDC và refresh nằm trong giới hạn 3 phút.
- Tốc độ batch đủ theo kịp lượng giao dịch cao điểm.
- Update và hoàn tiền làm giảm đúng nhóm cũ, cộng đúng nhóm mới.
- Refresh không làm giao dịch ghi vượt SLO.
- Đối soát phát hiện được batch thiếu, trùng và giao dịch đến muộn.

Nếu chỉ số phân tích cần số khách hàng duy nhất theo vùng, không cộng số khách hàng duy nhất từng cửa hàng vì một khách có thể mua ở nhiều cửa hàng. Cần tính distinct ở grain báo cáo, lưu tập định danh đủ chi tiết hoặc dùng cấu trúc xấp xỉ có sai số được chấp nhận.

## 12. Những sai lầm thường gặp

- **Chọn grain quá thô:** mất chiều phân tích cần thiết và không thể khôi phục từ số tổng đã lưu.
- **Chọn grain quá chi tiết:** summary gần bằng bảng nguồn, không giảm đáng kể I/O nhưng vẫn tăng chi phí duy trì.
- **Cộng các chỉ số không cộng được:** cộng trung bình, tỷ lệ hoặc distinct count tạo kết quả sai.
- **Bỏ qua tiền tệ và múi giờ:** cộng khác đơn vị hoặc gom sai ngày nghiệp vụ.
- **Chỉ xử lý dữ liệu mới:** bỏ sót update, delete, hoàn tiền và giao dịch đến muộn.
- **Không chống xử lý batch trùng:** retry có thể cộng số liệu nhiều lần.
- **Cập nhật checkpoint sai thứ tự:** có thể bỏ mất batch hoặc xử lý lặp.
- **Full refresh không xử lý nhóm biến mất:** kết quả cũ vẫn tồn tại dù nguồn không còn dòng phù hợp.
- **Chỉ đo tốc độ báo cáo:** bỏ qua thời gian refresh, tải ghi, độ mới và ảnh hưởng OLTP.
- **Tạo quá nhiều bảng tổng hợp và chỉ mục:** chi phí cập nhật, dung lượng và đối soát tăng nhanh.
- **Không đối soát theo grain:** tổng toàn hệ thống có thể đúng tình cờ dù một số nhóm đã sai lệch.

## 13. Checklist thiết kế và vận hành bảng tổng hợp

- [ ] Đã xác định câu hỏi báo cáo lặp lại và workload thực sự cần tăng tốc.
- [ ] Đã mô tả grain bằng ý nghĩa nghiệp vụ và xác định khóa duy nhất.
- [ ] Đã phân loại chỉ số additive, semi-additive và non-additive.
- [ ] Đã xác định quy tắc tiền tệ, múi giờ, trạng thái giao dịch và làm tròn.
- [ ] Đã chọn full refresh, incremental refresh hoặc cửa sổ rebuild gần đây.
- [ ] Đã xác định cách nhận biết insert, update, delete và dữ liệu đến muộn.
- [ ] Đã thiết kế idempotency, batch id, watermark và phục hồi lỗi.
- [ ] Đã bảo đảm summary và checkpoint được commit theo cách nhất quán.
- [ ] Đã chọn index, partition và retention theo truy vấn báo cáo thực tế.
- [ ] Đã đối soát nguồn và summary theo từng khóa grain.
- [ ] Đã đo thời gian báo cáo, thời gian refresh, CPU, I/O, log và độ mới dữ liệu.
- [ ] Đã kiểm thử tải hỗn hợp và tác động tới giao dịch OLTP.
- [ ] Đã có cảnh báo cho batch lỗi, watermark trễ và sai lệch số liệu.
- [ ] Đã lưu baseline và kết quả trước/sau để chứng minh lợi ích tổng thể.

Tổng hợp trước giúp báo cáo lặp lại đọc ít dữ liệu và giảm công việc tính toán tại thời điểm người dùng yêu cầu. Hiệu quả phụ thuộc vào grain, loại chỉ số, chiến lược refresh và khả năng xử lý mọi thay đổi của dữ liệu nguồn. Khi quy trình có idempotency, checkpoint, đối soát và benchmark cả tải đọc lẫn tải ghi, bảng tổng hợp có thể cải thiện độ trễ báo cáo mà vẫn giữ được tính đúng đắn và độ mới theo yêu cầu nghiệp vụ.
