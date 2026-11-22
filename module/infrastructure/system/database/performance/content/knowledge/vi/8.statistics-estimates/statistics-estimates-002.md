# Độ chọn lọc, số giá trị phân biệt và tỷ lệ giá trị NULL

Optimizer cần dự đoán một câu truy vấn sẽ đọc và trả về bao nhiêu hàng trước khi chọn cách thực thi. Dự đoán này ảnh hưởng đến thứ tự kết hợp bảng, cách truy cập chỉ mục, thuật toán join, bộ nhớ dành cho sort hoặc hash và mức độ song song hóa. Nếu ước lượng số hàng sai đáng kể, một kế hoạch tưởng như rẻ có thể trở nên rất tốn kém khi chạy trên dữ liệu thật.

Ba khái niệm thống kê cơ bản giúp giải thích cách optimizer ước lượng dữ liệu là **độ chọn lọc (selectivity)**, **số giá trị phân biệt (number of distinct values, NDV)** và **tỷ lệ giá trị NULL (null fraction)**. Chúng mô tả mức độ phổ biến của điều kiện lọc, mức đa dạng của một cột và phần dữ liệu không có giá trị theo nghĩa SQL. Khi hiểu ba đại lượng này, người vận hành có thể đọc thống kê, nhận diện giả định sai và chọn cách cập nhật hoặc mở rộng thống kê phù hợp.

## 1. Vì sao optimizer cần thống kê?

SQL nêu kết quả cần lấy, nhưng optimizer phải chọn một chuỗi thao tác vật lý để tạo kết quả. Với truy vấn lọc theo khách hàng rồi join đơn hàng, optimizer cần ước lượng có bao nhiêu khách hàng thỏa điều kiện và mỗi khách hàng có bao nhiêu đơn hàng. Từ đó nó mới so sánh được các phương án như:

- Quét toàn bộ bảng rồi lọc.
- Dùng chỉ mục để tìm các hàng thỏa điều kiện.
- Đọc bảng có ít hàng trước rồi tra cứu bảng còn lại bằng Nested Loop.
- Đọc hai tập dữ liệu và kết hợp bằng Hash Join hoặc Merge Join.

Thống kê cung cấp mô tả tóm tắt về dữ liệu mà không cần quét toàn bộ bảng mỗi lần lập kế hoạch. Tùy hệ quản trị, thống kê có thể gồm số hàng và trang, số giá trị phân biệt, tỷ lệ NULL, giá trị xuất hiện thường xuyên, histogram, độ tương quan giữa các cột và thông tin về chỉ mục.

Optimizer sử dụng các thống kê này cùng biểu thức truy vấn, ràng buộc, tham số và mô hình chi phí để ước lượng cardinality. Cardinality là số hàng dự kiến tại một bước của kế hoạch, chẳng hạn sau filter hoặc sau join. Ước lượng càng gần dữ liệu thực tế thì optimizer càng có cơ hội chọn đúng thứ tự và thuật toán.

Thống kê là mô hình gần đúng. Chúng không lưu toàn bộ từng giá trị của bảng, và thường được lấy mẫu hoặc tóm tắt theo giới hạn cấu hình. Dữ liệu thay đổi, phân phối lệch hoặc quan hệ giữa nhiều cột có thể khiến mô hình không còn đại diện cho dữ liệu hiện tại.

## 2. Độ chọn lọc (selectivity)

Độ chọn lọc biểu thị tỷ lệ hàng thỏa mãn một điều kiện lọc so với tổng số hàng thuộc phạm vi xét. Với một bảng có (N) hàng và điều kiện (P), có thể định nghĩa:

\[
S(P)=\frac{\text{Số hàng thỏa }P}{N}
\]

Giá trị (S(P)) thường nằm trong khoảng từ 0 đến 1. Nếu điều kiện khớp 5% số hàng thì selectivity bằng 0,05. Số hàng ước lượng sau lọc là:

\[
\widehat{N}_{P}=N\times S(P)
\]

Trong nhiều tài liệu và công cụ, thuật ngữ *selectivity* đôi khi được dùng cho tỷ lệ khớp, đôi khi người viết nói đến “độ chọn lọc cao” để ám chỉ điều kiện loại bỏ phần lớn dữ liệu. Để tránh nhầm, hãy luôn nêu rõ tỷ lệ đang dùng là tỷ lệ hàng được giữ lại hay tỷ lệ hàng bị loại. Trong bài này, selectivity là tỷ lệ hàng được giữ lại.

Ví dụ, bảng `orders` có 2.000.000 hàng. Nếu điều kiện `status = 'CANCELLED'` khớp khoảng 2% số hàng thì:

\[
2.000.000\times0,02=40.000\text{ hàng}
\]

Optimizer có thể dự đoán khoảng 40.000 hàng sau filter. Nếu chỉ mục cho phép tìm 40.000 hàng với ít chi phí hơn quét bảng, truy cập chỉ mục có thể có lợi. Nếu điều kiện khớp 80% bảng, quét tuần tự có thể rẻ hơn nhiều lần truy cập ngẫu nhiên qua chỉ mục. Quyết định cuối cùng còn phụ thuộc kích thước hàng, vị trí dữ liệu, cache, phân vùng, mức độ phủ của chỉ mục và mô hình chi phí.

### Selectivity của các phép so sánh

Các điều kiện khác nhau cần cách ước lượng khác nhau:

- **So sánh bằng:** `region = 'NORTH'` phụ thuộc tần suất của giá trị `NORTH` và NDV của cột.
- **So sánh khác:** `status <> 'CLOSED'` thường giữ lại phần lớn giá trị còn lại, nhưng phải xét NULL và các giá trị phổ biến.
- **Khoảng:** `created_at >= DATE '2026-01-01'` phụ thuộc phân phối giá trị theo thời gian; histogram hoặc thống kê phân phối giúp ước lượng phần nằm trong khoảng.
- **IN:** `status IN ('NEW', 'PAID')` phụ thuộc tần suất của từng giá trị và khả năng trùng lặp trong danh sách.
- **LIKE hoặc biểu thức:** `email LIKE 'a%'` có thể được ước lượng từ tiền tố hoặc histogram tùy hệ quản trị; `LOWER(email) = ...` có thể khó dùng thống kê cột gốc nếu không có thống kê biểu thức phù hợp.
- **IS NULL:** `deleted_at IS NULL` phụ thuộc tỷ lệ NULL của cột.

Không nên dùng một quy tắc selectivity cố định cho mọi kiểu điều kiện. Khi optimizer thiếu thông tin, nó có thể dùng giả định mặc định. Các giả định này hữu ích để lập kế hoạch nhưng dễ sai với dữ liệu lệch hoặc điều kiện đặc thù.

## 3. Số giá trị phân biệt (NDV)

NDV là số lượng giá trị khác nhau được quan sát hoặc ước lượng trong một cột hay một nhóm cột. Ví dụ, bảng `customers` có 1.000.000 hàng nhưng cột `country_code` chỉ có khoảng 30 giá trị phân biệt; cột `customer_id` có thể có gần 1.000.000 giá trị phân biệt.

NDV giúp optimizer ước lượng độ phổ biến của giá trị khi không có thông tin tần suất chi tiết hơn. Với giả định đơn giản rằng các giá trị khác NULL phân bố đều, xác suất một hàng có một giá trị cụ thể có thể xấp xỉ:

\[
S(c=v)\approx\frac{1-f_{NULL}}{NDV}
\]

Trong đó (f_{NULL}) là tỷ lệ NULL. Nếu cột không có NULL, công thức rút gọn thành (1/NDV). Đây chỉ là giả định phân bố đều; dữ liệu thật thường không đều.

Ví dụ, bảng có 500.000 hàng, tỷ lệ NULL của `region` là 0,02 và NDV của các giá trị không NULL là 10. Khi giả định phân bố đều:

\[
S(region='NORTH')\approx\frac{1-0,02}{10}=0,098
\]

Số hàng dự kiến là khoảng `500.000 × 0,098 = 49.000`. Nếu thực tế `NORTH` chiếm 45% dữ liệu thì ước lượng dựa trên phân bố đều thấp hơn nhiều so với thực tế. Thống kê giá trị phổ biến (most common values) hoặc histogram có thể giúp optimizer mô hình hóa độ lệch này.

### NDV thấp và NDV cao

| Đặc điểm | Ví dụ | Ý nghĩa đối với ước lượng |
|---|---|---|
| NDV thấp | `status`, `gender_code`, `is_active` | Một giá trị có thể xuất hiện ở tỷ lệ lớn; phân phối giữa các giá trị rất quan trọng |
| NDV trung bình | `region_id`, `category_id` | NDV và độ lệch phân phối giúp dự đoán số hàng cho từng giá trị |
| NDV cao | `customer_id`, `email`, `order_id` | Một giá trị thường ít xuất hiện; thống kê cần mô tả tốt các giá trị ngoại lệ và tính duy nhất |

NDV không đồng nghĩa với độ duy nhất tuyệt đối. Một cột có NDV gần bằng số hàng có thể gần duy nhất, nhưng chỉ ràng buộc `PRIMARY KEY` hoặc `UNIQUE` mới thể hiện bảo đảm toàn vẹn tương ứng trong cơ sở dữ liệu. Optimizer có thể sử dụng ràng buộc để suy luận mạnh hơn thống kê lấy mẫu.

### NDV của nhiều cột

NDV của từng cột riêng lẻ không đủ để mô tả NDV của tổ hợp. Giả sử bảng `events` có 100.000 hàng, `tenant_id` có 100 giá trị và `event_type` có 5 giá trị. Không thể tự động kết luận tổ hợp `(tenant_id, event_type)` có 500 giá trị xuất hiện đều nhau. Có thể một tenant chỉ tạo một loại sự kiện, còn tenant khác tạo đủ năm loại.

NDV của tổ hợp cột hữu ích cho ước lượng `GROUP BY tenant_id, event_type`, `COUNT(DISTINCT ...)` hoặc các điều kiện kết hợp. Hệ quản trị có thể lưu thống kê nhiều cột, thống kê mở rộng hoặc thống kê trên chỉ mục tổng hợp. Khả năng và cách dùng khác nhau theo sản phẩm.

## 4. Tỷ lệ giá trị NULL (null fraction)

Trong SQL, `NULL` biểu thị giá trị chưa biết hoặc không có giá trị theo ngữ nghĩa của cột. `NULL` không bằng 0, chuỗi rỗng hay một giá trị mặc định. So sánh thông thường với NULL tạo ra kết quả UNKNOWN thay vì TRUE hoặc FALSE.

Tỷ lệ NULL của cột (c) được tính:

\[
f_{NULL}(c)=\frac{\text{Số hàng có }c\text{ là NULL}}{N}
\]

Tỷ lệ giá trị không NULL là:

\[
f_{nonNULL}(c)=1-f_{NULL}(c)
\]

Nếu bảng có 800.000 hàng và `deleted_at` có 600.000 giá trị NULL, thì `deleted_at IS NULL` khớp 75% bảng; `deleted_at IS NOT NULL` khớp 25%. Nếu optimizer không biết tỷ lệ NULL hoặc dùng thống kê đã cũ, nó có thể ước lượng sai đáng kể số hàng sau điều kiện.

### NULL và logic ba giá trị

Một số biểu thức thường bị hiểu nhầm:

```sql
-- Đúng: kiểm tra NULL
WHERE deleted_at IS NULL

-- Đúng: kiểm tra có giá trị
WHERE deleted_at IS NOT NULL

-- Không tương đương với IS NULL
WHERE deleted_at = NULL
```

Điều kiện `deleted_at = NULL` không trả về TRUE cho các hàng NULL. Vì vậy, câu lệnh cuối không phải cách thay thế cho `IS NULL`. Tương tự, `COUNT(column)` bỏ qua NULL, còn `COUNT(*)` đếm hàng; khác biệt này cần được hiểu khi kiểm tra thống kê và đối chiếu số lượng.

Khi tính selectivity, phải xác định rõ mẫu số có bao gồm toàn bộ hàng hay chỉ hàng không NULL. Với `column = value`, hàng NULL không thỏa điều kiện. Nếu dùng giả định phân bố đều trên các giá trị không NULL, cần nhân tỷ lệ không NULL như công thức ở phần NDV.

### NULL và chỉ mục

Khả năng chỉ mục chứa hoặc bỏ qua NULL phụ thuộc hệ quản trị và loại chỉ mục. Một số hệ quản trị lưu NULL trong chỉ mục B-tree thông thường; một số loại chỉ mục hoặc chiến lược thiết kế có thể có quy tắc riêng. Chỉ mục một phần (partial index) hoặc chỉ mục lọc (filtered index) có thể hữu ích khi truy vấn thường xuyên nhắm đến một tập con như `deleted_at IS NULL`, nếu hệ quản trị hỗ trợ và optimizer có thể chứng minh điều kiện truy vấn phù hợp với điều kiện chỉ mục.

Ví dụ khái niệm với PostgreSQL:

```sql
CREATE INDEX orders_open_created_idx
ON orders (created_at)
WHERE closed_at IS NULL;
```

Chỉ mục này lưu các hàng thỏa `closed_at IS NULL`. Nó có thể phù hợp với truy vấn thường lọc tập đơn hàng đang mở và sắp xếp hoặc giới hạn theo `created_at`. Tuy nhiên, chỉ mục nhỏ hơn không tự động bảo đảm truy vấn nhanh: cần kiểm tra selectivity, số hàng cần đọc, khả năng dùng chỉ mục, chi phí cập nhật và kế hoạch thực tế.

## 5. Kết hợp selectivity, NDV và NULL fraction

Ba đại lượng liên hệ với nhau khi optimizer ước lượng một điều kiện. Giả sử bảng `tickets` có 1.000.000 hàng với các thống kê:

- `priority` có 4 giá trị khác NULL, NDV = 4.
- `priority` có 10% NULL.
- `priority = 'HIGH'` chiếm 30% số hàng không NULL theo thống kê tần suất.
- `assignee_id` có 20% NULL và NDV khoảng 100.000.

Với điều kiện `priority = 'HIGH'`, nếu tần suất 30% được tính trên phần không NULL, selectivity trên toàn bảng là:

\[
S(priority='HIGH')=(1-0,10)\times0,30=0,27
\]

Số hàng ước lượng là 270.000. Với điều kiện `assignee_id IS NULL`, selectivity là 0,20 và số hàng ước lượng là 200.000.

Nếu truy vấn dùng đồng thời hai điều kiện:

```sql
WHERE priority = 'HIGH'
  AND assignee_id IS NULL
```

Một optimizer đơn giản có thể giả định hai điều kiện độc lập và nhân xác suất:

\[
S(P\land Q)\approx S(P)\times S(Q)
\]

\[
0,27\times0,20=0,054
\]

Tức dự đoán khoảng 54.000 hàng. Nhưng nếu các ticket ưu tiên cao thường chưa được phân công, hai điều kiện có tương quan dương và tỷ lệ thực tế có thể cao hơn nhiều. Nếu quy trình vận hành luôn gán người xử lý cho ticket ưu tiên cao, tỷ lệ thực tế có thể thấp hơn. Giả định độc lập không thể thay thế thống kê hoặc hiểu biết về quy tắc nghiệp vụ.

## 6. Vì sao giả định độc lập thường sai?

Optimizer cần kết hợp selectivity của nhiều điều kiện. Khi không có thống kê mô tả quan hệ giữa các cột, một mô hình phổ biến là giả định các điều kiện độc lập. Giả định này có thể hợp lý trong một số dữ liệu nhưng thường sai với dữ liệu nghiệp vụ.

Ví dụ:

- `country_code` và `postal_code` có quan hệ: một mã bưu chính thường thuộc một quốc gia.
- `status` và `closed_at` có quan hệ: đơn đã đóng thường có thời điểm đóng khác NULL.
- `tenant_id` và `region_id` có quan hệ: mỗi tenant chỉ hoạt động ở một vài vùng.
- `product_category` và `tax_code` có quan hệ do quy tắc phân loại sản phẩm.

Nếu optimizer ước lượng từng điều kiện riêng rồi nhân xác suất, cardinality kết hợp có thể thấp hơn hoặc cao hơn thực tế nhiều lần. Sai lệch ở filter đầu vào sẽ lan truyền tới join, sort, aggregate và các quyết định bộ nhớ.

Khi nghi ngờ tương quan, hãy kiểm tra số lượng thực tế của các nhóm điều kiện bằng truy vấn tổng hợp trên dữ liệu đại diện. Cần lưu ý việc đo này có thể tốn tài nguyên nếu bảng lớn; có thể dùng môi trường phân tích, mẫu dữ liệu hoặc thống kê sẵn có. Sau đó đánh giá khả năng tạo thống kê nhiều cột, thống kê phụ thuộc, histogram phù hợp hoặc chỉ mục tổng hợp tùy hệ quản trị.

## 7. Histogram và giá trị xuất hiện thường xuyên

NDV cho biết có bao nhiêu giá trị phân biệt, nhưng không mô tả đầy đủ tần suất của từng giá trị. Nếu một cột có NDV = 100, phân bố có thể đều (mỗi giá trị chiếm xấp xỉ 1%) hoặc lệch mạnh (một giá trị chiếm 60%, 99 giá trị còn lại chia nhau 40%). Optimizer cần thông tin phân phối để ước lượng chính xác hơn.

### Most common values (MCV)

Danh sách giá trị phổ biến lưu một số giá trị có tần suất cao cùng tỷ lệ xuất hiện. Với điều kiện bằng một giá trị nằm trong danh sách MCV, optimizer có thể dùng tần suất riêng thay cho giả định `1/NDV`.

Ví dụ, cột `status` có 5 giá trị nhưng `ACTIVE` chiếm 70%, `ARCHIVED` chiếm 20% và ba giá trị còn lại chia nhau 10%. Nếu chỉ dùng NDV và giả định đều, optimizer có thể ước lượng mỗi giá trị 20%. Điều này sẽ đánh giá thấp `ACTIVE` và đánh giá cao các giá trị hiếm.

### Histogram

Histogram chia miền giá trị thành các khoảng hoặc bucket và tóm tắt phân phối trong từng khoảng. Nó hữu ích cho điều kiện phạm vi như `created_at >= ...`, `price BETWEEN ...` hoặc so sánh lớn hơn/nhỏ hơn. Histogram có thể mô tả biên phân phối và mật độ dữ liệu gần đúng, nhưng độ chính xác phụ thuộc số bucket, cách lấy mẫu, dữ liệu lệch và cách hệ quản trị xây dựng thống kê.

Histogram thường không lưu mọi giá trị. Một điều kiện nằm trong vùng bucket rộng hoặc có phân phối rất lệch bên trong bucket có thể vẫn được ước lượng chưa chính xác. Giá trị ngoài phạm vi histogram cũng có thể cần giả định riêng.

### Thống kê theo cột và theo biểu thức

Điều kiện như `LOWER(email) = 'a@example.com'` áp dụng hàm lên cột. Thống kê trên `email` nguyên bản chưa chắc mô tả phân phối của `LOWER(email)`. Tùy hệ quản trị, có thể tạo expression statistics, computed/persisted column hoặc chỉ mục biểu thức để optimizer có thông tin phù hợp và truy vấn có đường truy cập hữu ích.

Tương tự, điều kiện trên phép ép kiểu, phép tính ngày tháng hoặc biểu thức JSON có thể khiến thống kê cột gốc không đủ. Hãy xem biểu thức trong kế hoạch và xác định optimizer có dùng được thống kê tương ứng hay không.

## 8. Thống kê nhiều cột và chỉ mục tổng hợp

Thống kê nhiều cột giúp mô hình hóa NDV của tổ hợp hoặc mối tương quan giữa các cột. Chỉ mục tổng hợp lại là cấu trúc truy cập dữ liệu. Hai thứ có thể bổ trợ nhau nhưng không đồng nhất:

- Thống kê nhiều cột cải thiện dự đoán cardinality; tự nó không tạo ra đường truy cập dữ liệu mới.
- Chỉ mục tổng hợp có thể hỗ trợ tìm kiếm, join hoặc sắp xếp theo thứ tự cột của chỉ mục; nó cũng tạo chi phí ghi và lưu trữ.
- Một chỉ mục có thể cung cấp thống kê về tổ hợp cột trong một số hệ quản trị, nhưng phạm vi thống kê và cách optimizer sử dụng phụ thuộc sản phẩm.

Ví dụ, truy vấn thường dùng:

```sql
SELECT COUNT(*)
FROM events
WHERE tenant_id = 17
  AND event_type = 'LOGIN';
```

Nếu `tenant_id` và `event_type` có tương quan, thống kê riêng của từng cột có thể dự đoán sai số hàng giao nhau. Thống kê mở rộng về phụ thuộc hoặc NDV của tổ hợp có thể cải thiện ước lượng. Chỉ mục `(tenant_id, event_type)` có thể giúp truy cập dữ liệu phù hợp hơn nếu truy vấn và workload sử dụng các điều kiện này thường xuyên. Cần đánh giá cả hai lựa chọn bằng kế hoạch và tải thực tế.

### Ví dụ với PostgreSQL

PostgreSQL hỗ trợ extended statistics với các loại thông tin như `ndistinct`, `dependencies` và `mcv`. Một ví dụ khai báo thống kê trên hai cột:

```sql
CREATE STATISTICS events_tenant_type_stats
    (ndistinct, dependencies, mcv)
ON tenant_id, event_type
FROM events;

ANALYZE events;
```

`ndistinct` mô tả số tổ hợp phân biệt, `dependencies` mô tả một số phụ thuộc giữa cột, còn `mcv` lưu các tổ hợp phổ biến. Việc khai báo không có nghĩa mọi truy vấn sẽ tự động có ước lượng hoàn hảo; cần kiểm tra loại điều kiện, phiên bản PostgreSQL và kế hoạch sau khi thu thập thống kê.

## 9. Đọc thống kê trong PostgreSQL

PostgreSQL cung cấp view `pg_stats` để xem thống kê dễ đọc cho các cột mà người dùng có quyền truy cập. Các trường hữu ích gồm:

| Trường | Ý nghĩa tổng quát |
|---|---|
| `null_frac` | Tỷ lệ NULL ước lượng của cột |
| `n_distinct` | Ước lượng số giá trị phân biệt; giá trị âm có thể biểu thị tỷ lệ so với số hàng |
| `most_common_vals` | Các giá trị phổ biến được lưu trong thống kê |
| `most_common_freqs` | Tần suất tương ứng với các giá trị phổ biến |
| `histogram_bounds` | Các biên histogram cho phần phân phối được mô tả |
| `correlation` | Mức tương quan giữa thứ tự logic của giá trị cột và thứ tự vật lý của hàng, hữu ích cho ước lượng chi phí truy cập |

Ví dụ xem thống kê của một cột:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname = 'status';
```

View này phản ánh thống kê được thu thập gần nhất, không phải truy vấn đếm chính xác dữ liệu tại thời điểm hiện tại. `n_distinct` có thể mang giá trị âm để biểu thị ước lượng theo tỷ lệ số hàng; không nên hiểu mọi giá trị của trường này là số nguyên dương tuyệt đối. Thông tin trong các trường mảng cũng cần được đọc theo cặp, chẳng hạn giá trị MCV tương ứng với tần suất cùng vị trí.

PostgreSQL cho phép điều chỉnh statistics target theo cột để thu thập mô tả chi tiết hơn:

```sql
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE orders;
```

Statistics target lớn hơn có thể làm tăng số giá trị MCV hoặc bucket histogram được lưu, giúp mô tả phân phối phức tạp tốt hơn. Đổi lại, việc thu thập thống kê có thể tốn thêm thời gian và dung lượng catalog. Không nên tăng target cho mọi cột; hãy chọn cột có phân phối lệch hoặc có sai lệch ước lượng đã được quan sát.

## 10. Thống kê trong MySQL và SQL Server

Các hệ quản trị khác có cách tổ chức thống kê riêng:

| Hệ quản trị | Nơi hoặc công cụ thường dùng | Thông tin cần tìm |
|---|---|---|
| MySQL/InnoDB | `ANALYZE TABLE`, thông tin thống kê trong data dictionary và histogram khi được cấu hình | Cardinality ước lượng của chỉ mục, histogram cho cột được hỗ trợ, ảnh hưởng của thống kê lấy mẫu và phiên bản |
| SQL Server | Statistics objects, `DBCC SHOW_STATISTICS`, execution plan và metadata thống kê | Header, density vector, histogram, ngày cập nhật, số hàng được lấy mẫu và mức độ phù hợp với điều kiện truy vấn |
| PostgreSQL | `ANALYZE`, `pg_stats`, extended statistics | `null_frac`, `n_distinct`, MCV, histogram, correlation và thống kê nhiều cột |

Tên gọi có thể giống nhau nhưng thuật toán, cách lấy mẫu, giới hạn histogram và điều kiện optimizer sử dụng khác nhau. Không áp dụng trực tiếp câu lệnh hoặc ngữ nghĩa thống kê của một hệ quản trị sang hệ khác. Hãy xem tài liệu phiên bản đang vận hành và kiểm tra kế hoạch thực tế.

## 11. Khi nào cần cập nhật thống kê?

Thống kê có thể trở nên lỗi thời khi dữ liệu thay đổi về số lượng hoặc phân phối. Một bảng thêm nhiều hàng mới chưa chắc có cùng phân phối với dữ liệu cũ. Ví dụ, một cột `status` trước đây chủ yếu là `OPEN`, nhưng sau một đợt migration phần lớn hàng được chuyển thành `ARCHIVED`. Optimizer tiếp tục dùng tần suất cũ có thể ước lượng sai.

Những dấu hiệu cần điều tra gồm:

- Chênh lệch lớn giữa estimated rows và actual rows ở một hoặc nhiều nút.
- Kế hoạch thay đổi bất thường sau khi tải dữ liệu, migration hoặc batch update.
- Một giá trị mới xuất hiện với tần suất cao nhưng không có trong thống kê MCV.
- Truy vấn theo khoảng thời gian mới hoặc vùng dữ liệu mới có độ trễ tăng.
- Optimizer chọn scan hoặc join không phù hợp với lượng dữ liệu thực tế.
- Số hàng bảng và phân phối dữ liệu đã thay đổi đáng kể từ lần ANALYZE gần nhất.

Trước khi cập nhật thống kê, ghi lại kế hoạch và số liệu thực tế làm đường cơ sở. Sau khi cập nhật, chạy lại cùng truy vấn với tham số đại diện và so sánh ước lượng, kế hoạch, độ trễ, I/O. Nếu kế hoạch không thay đổi hoặc ước lượng vẫn sai, cần xem xét tương quan cột, biểu thức, histogram, tham số hoặc cách truy vấn.

### Thu thập thống kê không phải lúc nào cũng đồng nghĩa quét toàn bộ dữ liệu

Nhiều hệ quản trị dùng lấy mẫu hoặc cơ chế thu thập thống kê có giới hạn. Lấy mẫu giúp giảm chi phí nhưng có thể bỏ sót giá trị hiếm hoặc phân phối lệch cục bộ. Tăng mức lấy mẫu hoặc statistics target có thể cải thiện độ chính xác trong một số trường hợp, nhưng làm tăng thời gian thu thập. Hãy cân bằng giữa chất lượng thống kê, chi phí vận hành và tần suất thay đổi dữ liệu.

## 12. Quy trình điều tra sai lệch cardinality

Khi thấy kế hoạch có ước lượng sai, có thể làm theo quy trình sau:

1. **Chọn nút sai lệch.** So sánh estimated rows và actual rows từ các nút lá lên gốc. Tìm nút đầu tiên có sai lệch đáng kể; sai lệch ở nút sớm thường ảnh hưởng nhiều quyết định phía trên.
2. **Xác định biểu thức tạo ra cardinality.** Đó là filter đơn cột, điều kiện nhiều cột, join, group by, distinct hay biểu thức trên cột?
3. **Đọc thống kê liên quan.** Kiểm tra NDV, tỷ lệ NULL, MCV, histogram, thống kê chỉ mục hoặc thống kê nhiều cột nếu có.
4. **Kiểm tra phân phối thật có kiểm soát.** Đối chiếu tỷ lệ của giá trị phổ biến, khoảng giá trị và tổ hợp điều kiện trên tập dữ liệu phù hợp. Tránh chạy truy vấn quét lớn trên hệ thống đang chịu tải nếu chưa đánh giá tác động.
5. **Kiểm tra tương quan và giá trị lệch.** Xác định các cột có phụ thuộc nghiệp vụ, giá trị mới hoặc phân phối thay đổi theo thời gian/tenant/khu vực.
6. **Chọn biện pháp phù hợp.** Có thể cập nhật thống kê, tăng target cho một cột, tạo thống kê nhiều cột, thống kê biểu thức, hoặc thiết kế lại điều kiện truy vấn và chỉ mục.
7. **Đo lại.** Thu thập kế hoạch thực tế cùng bộ tham số và điều kiện tải tương đương; so sánh cardinality, join order, loops, thời gian và I/O.
8. **Theo dõi workload rộng hơn.** Một thay đổi có thể giúp một truy vấn nhưng làm truy vấn khác hoặc thao tác ghi tốn kém hơn. Theo dõi các mẫu truy vấn có liên quan và chi phí duy trì thống kê/chỉ mục.

## 13. Ví dụ thực tế: điều kiện lọc kết hợp bị ước lượng thấp

Một ứng dụng quản lý phiếu hỗ trợ có bảng `tickets` với 5.000.000 hàng. Hai điều kiện thường xuất hiện:

```sql
SELECT ticket_id, created_at
FROM tickets
WHERE priority = 'URGENT'
  AND assigned_to IS NULL;
```

Giả sử thống kê đơn cột cho thấy:

- `priority = 'URGENT'` có selectivity 0,08.
- `assigned_to IS NULL` có selectivity 0,25.

Nếu optimizer giả định độc lập, nó dự đoán:

\[
5.000.000\times0,08\times0,25=100.000\text{ hàng}
\]

Nhưng trong quy trình vận hành, phiếu khẩn cấp thường chưa được gán ngay sau khi tạo. Trên dữ liệu thực, 60% phiếu khẩn cấp có `assigned_to IS NULL`. Khi đó selectivity kết hợp là:

\[
0,08\times0,60=0,048
\]

Số hàng thực tế xấp xỉ 240.000, cao gấp 2,4 lần ước lượng. Nếu optimizer chọn một Nested Loop dựa trên dự đoán 100.000 hàng nhưng thực tế có 240.000 hàng, số lần truy cập nhánh trong có thể tăng đáng kể.

Quy trình xử lý:

1. Xác nhận chênh lệch xuất hiện ở filter kết hợp hay ở join phía trên.
2. Kiểm tra `null_frac` của `assigned_to`, NDV và MCV của `priority`.
3. Đo phân phối của cặp `(priority, assigned_to IS NULL)` trên dữ liệu đại diện.
4. Nếu hệ quản trị hỗ trợ, tạo thống kê nhiều cột hoặc thống kê biểu thức phù hợp để mô tả quan hệ.
5. Thu thập thống kê lại, chạy lại kế hoạch thực tế và kiểm tra estimated rows.
6. Nếu truy vấn này quan trọng và thường xuyên, đánh giá chỉ mục có điều kiện phù hợp, nhưng phải đo thêm chi phí ghi khi phiếu được phân công hoặc đổi mức ưu tiên.

Ví dụ cho thấy NDV và NULL fraction cung cấp thông tin nền, nhưng tương quan giữa điều kiện có thể quyết định cardinality cuối cùng. Cập nhật thống kê đơn cột không phải lúc nào cũng khắc phục được sai lệch nhiều cột.

## 14. Các lưu ý khi dùng thống kê để thiết kế chỉ mục

Thống kê giúp dự đoán một chỉ mục có thể hữu ích hay không, nhưng không quyết định thay người thiết kế. Khi cân nhắc chỉ mục, hãy xem:

- Điều kiện lọc giữ lại bao nhiêu phần trăm hàng.
- NDV và độ lệch của giá trị được tìm kiếm.
- Tỷ lệ NULL và tần suất truy vấn `IS NULL`/`IS NOT NULL`.
- Các cột thường được lọc cùng nhau và thứ tự điều kiện.
- Số hàng cần trả, cột cần đọc và khả năng tạo covering index.
- Tần suất cập nhật các cột trong chỉ mục, dung lượng và chi phí bảo trì.
- Khả năng optimizer chứng minh truy vấn phù hợp với partial/filtered index.

Ví dụ, một cột Boolean có NDV = 2 thường không có selectivity cao cho từng giá trị nếu phân phối gần 50/50. Chỉ mục đơn cột trên đó có thể không hữu ích cho truy vấn lấy phần lớn bảng. Nhưng nếu `is_active = true` chỉ chiếm 0,5% dữ liệu và truy vấn thường lấy nhóm này, chỉ mục có thể đáng cân nhắc. Nếu truy vấn còn lọc theo `created_at`, chỉ mục kết hợp hoặc chỉ mục một phần có thể phù hợp hơn. Cần xác minh bằng execution plan và benchmark.

Không tạo chỉ mục chỉ vì NDV cao. Một cột NDV cao nhưng hiếm khi được lọc, hoặc truy vấn luôn cần nhiều cột không có trong chỉ mục, có thể không đem lại lợi ích đủ lớn. Ngược lại, cột NDV thấp vẫn có thể là phần đầu của chỉ mục tổng hợp hữu ích khi đi cùng điều kiện chọn lọc khác.

## 15. Những nhầm lẫn thường gặp

- **NDV cao đồng nghĩa mọi truy vấn đều chọn lọc.** NDV là số giá trị khác nhau, còn selectivity phụ thuộc giá trị và phân phối cụ thể.
- **Mỗi giá trị có tần suất bằng `1/NDV`.** Đây chỉ là giả định phân bố đều; MCV và histogram mô tả độ lệch.
- **NULL là một giá trị thông thường trong mọi phép so sánh.** SQL dùng logic ba giá trị; phải dùng `IS NULL` và `IS NOT NULL`.
- **Tỷ lệ NULL không ảnh hưởng ước lượng.** Nó tác động trực tiếp đến số hàng thỏa điều kiện và số hàng có thể tham gia phép join.
- **Thống kê đơn cột luôn đủ cho nhiều điều kiện.** Các cột có tương quan có thể khiến giả định độc lập sai.
- **Cập nhật thống kê luôn cải thiện kế hoạch.** Thống kê mới có thể làm optimizer chọn kế hoạch khác, nhưng chất lượng phụ thuộc dữ liệu, tham số và mô hình thống kê.
- **Chỉ mục thay thế được thống kê.** Chỉ mục tạo đường truy cập; thống kê mô tả dữ liệu. Cần cả hai để optimizer đánh giá lựa chọn.
- **Tăng statistics target càng cao càng tốt.** Mức cao hơn tốn tài nguyên thu thập và lưu trữ; chỉ nên tăng ở nơi có bằng chứng sai lệch.
- **Một lần chạy đại diện cho mọi tham số.** Giá trị phổ biến, giá trị hiếm và NULL có thể cần kế hoạch khác nhau.

## 16. Checklist đánh giá thống kê

- [ ] Đã xác định tổng số hàng và phạm vi dữ liệu được thống kê.
- [ ] Đã hiểu selectivity là tỷ lệ hàng được giữ lại và xác định rõ mẫu số.
- [ ] Đã kiểm tra NDV, tỷ lệ NULL và tần suất của giá trị phổ biến.
- [ ] Đã xem histogram khi truy vấn lọc theo khoảng hoặc phân phối giá trị.
- [ ] Đã xác định các cột có tương quan và đánh giá giả định độc lập.
- [ ] Đã so sánh estimated rows với actual rows tại nút đầu tiên sai lệch.
- [ ] Đã kiểm tra thời điểm và phạm vi cập nhật thống kê.
- [ ] Đã cân nhắc thống kê nhiều cột hoặc biểu thức khi thống kê đơn cột không đủ.
- [ ] Đã phân biệt lợi ích của thống kê với lợi ích của cấu trúc chỉ mục.
- [ ] Đã đo lại kế hoạch, độ trễ, I/O và tác động lên workload sau điều chỉnh.

Độ chọn lọc cho biết điều kiện giữ lại bao nhiêu hàng; NDV mô tả mức đa dạng của giá trị; tỷ lệ NULL cho biết phần dữ liệu không tham gia các phép so sánh thông thường. Ba đại lượng này giúp optimizer ước lượng cardinality, nhưng chỉ phản ánh dữ liệu đúng khi thống kê đủ mới và mô hình phân phối phù hợp. Khi kết hợp chúng với MCV, histogram, thống kê nhiều cột và số liệu thực tế từ execution plan, nhóm vận hành có thể tìm đúng nguồn sai lệch và cải thiện quyết định truy cập dữ liệu một cách có kiểm chứng.
