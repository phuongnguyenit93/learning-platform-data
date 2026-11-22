# Không suy luận quy tắc phụ thuộc chỉ từ vài dòng dữ liệu mẫu

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, nhiệm vụ quan trọng là chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, ràng buộc và lược đồ vật lý có thể kiểm chứng. Một lỗi dễ gặp ở giai đoạn này là nhìn vài dòng dữ liệu, nhận thấy một cột có vẻ xác định cột khác, rồi mặc nhiên coi đó là **phụ thuộc hàm** (*functional dependency*, FD) phải đúng cho toàn hệ thống.

Bài học thuộc chủ đề **Phụ thuộc dữ liệu** này giúp bạn:

- Phân biệt **phụ thuộc hàm được nghiệp vụ bảo đảm** với **mẫu hình tình cờ** trong dữ liệu hiện có.
- Giải thích vì sao dữ liệu mẫu có thể **bác bỏ** một phụ thuộc nhưng không thể **chứng minh** nó đúng cho mọi dữ liệu hợp lệ.
- Nhận diện các nguyên nhân gây suy luận sai: mẫu nhỏ, khóa gần như duy nhất, phạm vi mã, lịch sử, giá trị thiếu và dữ liệu không đại diện.
- Dùng SQL để **phát hiện ứng viên và phản ví dụ**, sau đó xác minh bằng câu hỏi nghiệp vụ.
- Chuyển phụ thuộc đã xác nhận thành khóa, ràng buộc, chuẩn hóa và cách lưu lịch sử thích hợp.

## 1. Phụ thuộc hàm là quy tắc trên mọi trạng thái dữ liệu hợp lệ

Xét quan hệ \(R(U)\), trong đó \(U\) là tập thuộc tính. Phụ thuộc hàm:

\[
X\rightarrow Y \quad (X,Y\subseteq U)
\]

có nghĩa: **trong mọi trạng thái dữ liệu hợp lệ của quan hệ**, nếu hai bản ghi bằng nhau trên tất cả thuộc tính thuộc \(X\), chúng phải bằng nhau trên tất cả thuộc tính thuộc \(Y\).

\[
\forall r\text{ hợp lệ},\ \forall t_1,t_2\in r:
\quad t_1[X]=t_2[X]\Rightarrow t_1[Y]=t_2[Y].
\]

Ví dụ, nếu nghiệp vụ quy định **mỗi mã đơn hàng thuộc duy nhất một khách hàng**, thì:

~~~text
order_id → customer_id
~~~

Nội dung của quy tắc là: hệ thống **không được có** hai dòng hợp lệ cùng `order_id` nhưng khác `customer_id`. Việc hiện tại chỉ có ba đơn hàng và cả ba đều thỏa quy tắc không phải là lý do để khẳng định quy tắc. Lý do nằm ở **ý nghĩa của mã đơn và chính sách nghiệp vụ**.

Một phụ thuộc hàm là khẳng định về **tính duy nhất được xác định**, không nhất thiết có công thức tính toán và không nhất thiết thể hiện quan hệ nhân quả. Nhiều mã đơn hàng khác nhau có thể xác định cùng một mã khách hàng, nên `order_id → customer_id` **không kéo theo** `customer_id → order_id`.

### Hai cấp độ kiểm tra dễ bị nhầm

| Cấp độ | Câu hỏi | Giá trị của kết quả |
|---|---|---|
| **Trạng thái dữ liệu cụ thể** \(r\) | Có hai dòng nào cùng \(X\), khác \(Y\) trong tập dữ liệu này không? | Phát hiện vi phạm **trong mẫu** |
| **Lược đồ và nghiệp vụ** \(R,F\) | Mọi trạng thái hợp lệ về sau có bắt buộc thỏa \(X\rightarrow Y\) không? | Xác định **ràng buộc thiết kế** |

Không tìm được phản ví dụ ở cấp độ thứ nhất **không đủ** để kết luận ở cấp độ thứ hai.

## 2. Ví dụ: ba dòng dữ liệu khiến nhiều phụ thuộc sai trông có vẻ đúng

Giả sử một bản xuất dữ liệu giao dịch gồm:

~~~text
ORDER_LINE(
    order_id, line_no, customer_id,
    product_id, quantity, unit_price_at_sale
)
~~~

Mỗi dòng đại diện cho **một sản phẩm ở một dòng của đơn hàng**. Ban đầu nhóm phân tích chỉ có ba dòng:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 1 | KH01 | SP01 | 2 | 10000 |
| DH02 | 1 | KH01 | SP01 | 1 | 11000 |
| DH03 | 1 | KH02 | SP02 | 3 | 20000 |

Trên mẫu này, các câu sau **đều chưa có phản ví dụ**:

~~~text
order_id → customer_id
order_id → product_id
order_id → quantity
order_id → unit_price_at_sale
~~~

Vì mỗi `order_id` **chỉ xuất hiện một lần**, bất cứ thuộc tính nào ở vế phải cũng sẽ có một giá trị duy nhất với mỗi mã đơn trong mẫu. Điều này gọi là **thỏa phụ thuộc một cách tình cờ hoặc hiển nhiên do dữ liệu chưa có lặp vế trái** (*vacuous satisfaction*).

Giả sử ngày hôm sau hệ thống nhận thêm một dòng hoàn toàn hợp lệ:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 2 | KH01 | SP02 | 1 | 22000 |

Khi đó hai dòng của `DH01` có **cùng mã đơn** nhưng khác `product_id`, `quantity` và `unit_price_at_sale`. Những phụ thuộc nhìn có vẻ đúng trước đó bị bác bỏ trên tập dữ liệu mở rộng:

~~~text
order_id ↛ product_id
order_id ↛ quantity
order_id ↛ unit_price_at_sale
~~~

Ngược lại, cả hai dòng `DH01` vẫn có `customer_id = KH01`. Điều này **phù hợp** với `order_id → customer_id` nhưng bản thân nó chưa chứng minh quy tắc. Muốn chọn quy tắc ấy để thiết kế, cần xác nhận: “**Theo định nghĩa nghiệp vụ, một đơn hàng chỉ được gắn với một khách hàng tại thời điểm đang xét.**”

Trong cùng ví dụ, `product_id → unit_price_at_sale` **đã có phản ví dụ ngay từ mẫu đầu tiên**: `SP01` được bán với giá 10000 và 11000. Nếu hai giao dịch hợp lệ, giá tại thời điểm bán không thể được xác định chỉ bằng mã sản phẩm.

### Bài học về mức hạt

Nếu mỗi dòng đại diện cho **một đơn hàng**, `order_id` có thể là khóa của bảng. Nếu mỗi dòng là **một dòng hàng**, khóa tự nhiên thường gồm `(order_id, line_no)` theo quy tắc số dòng duy nhất trong từng đơn.

Việc lấy mẫu một dòng đầu tiên của mỗi đơn đã **làm mất mức hạt thực tế** và tạo cảm giác mã đơn xác định mọi thuộc tính trên dòng. Luôn xác nhận “**một bản ghi là một cái gì?**” trước khi suy luận phụ thuộc.

## 3. Vì sao dữ liệu mẫu không chứng minh được một phụ thuộc?

Giả sử \(r\) là tập dữ liệu đang có và hiện không tìm thấy hai dòng cùng \(X\) nhưng khác \(Y\). Ta chỉ có thể khẳng định:

\[
r\models X\rightarrow Y.
\]

Điều này nói **trạng thái dữ liệu \(r\)** thỏa phụ thuộc, không suy ra rằng **mọi trạng thái hợp lệ theo nghiệp vụ** đều thỏa. Một trạng thái hợp lệ \(r'\) trong tương lai có thể chứa trường hợp chưa từng xuất hiện.

### Những nguồn gây ảo giác phụ thuộc hàm

| Hiện tượng | Mẫu dữ liệu khiến ta tưởng gì? | Phản ví dụ hoặc câu hỏi cần kiểm tra |
|---|---|---|
| **Vế trái không lặp** | `order_id → product_id` vì mỗi đơn chỉ có một dòng trong mẫu | Khi một đơn có nhiều dòng sản phẩm thì sao? |
| **Mẫu lấy theo bộ lọc** | `customer_id → country` trong tập chỉ chứa khách Việt Nam | Dữ liệu đầy đủ có khách đổi địa chỉ hoặc ở nước khác không? |
| **Hai thuộc tính chỉ tình cờ đi cùng** | `job_title → salary` trên năm nhân viên cùng bậc lương | Một chức danh có nhiều mức lương không? |
| **Mã chỉ duy nhất trong phạm vi** | `invoice_no → total` khi mới xem dữ liệu một cửa hàng | Hai cửa hàng có thể cùng số hóa đơn không? |
| **Dữ liệu hiện tại khác dữ liệu lịch sử** | `customer_id → customer_name` trong snapshot mới nhất | Bảng lịch sử có lưu nhiều tên theo thời điểm không? |
| **Giá trị thiếu hoặc chuẩn hóa không thống nhất** | Chỉ thấy một giá trị `Y` không NULL cho mỗi `X` | Dòng NULL là thiếu dữ liệu, không phải chứng cứ cho tính duy nhất |
| **Bảng đã được tổng hợp sẵn** | `product_id → total_sales` trong báo cáo một kỳ | Nếu có nhiều ngày hoặc nhiều thị trường, cần thêm thuộc tính phạm vi nào? |

**Một trăm nghìn dòng cũng có thể gây hiểu sai** nếu toàn bộ dữ liệu bị lọc về một trạng thái hoặc nếu tất cả giá trị \(X\) chỉ xuất hiện đúng một lần. Quy mô mẫu lớn không thay thế hiểu biết nghiệp vụ.

### Phân biệt tương quan, công thức và phụ thuộc hàm

- “Giá bán thường tăng theo thời gian” là mô tả **xu hướng**, không phải phụ thuộc hàm.
- “Trường `total` được tính bằng `quantity × unit_price`” là quy tắc tính toán. Nếu các đầu vào và cách làm tròn được định nghĩa chặt chẽ, có thể suy ra phụ thuộc từ cặp thuộc tính đầu vào đến `total`; nhưng cần xác nhận còn thuế, giảm giá, vận chuyển hay điều chỉnh hay không.
- “Mỗi mã đơn xác định một khách hàng” là quy tắc **định danh**, phù hợp để biểu diễn bằng phụ thuộc hàm.

Phụ thuộc hàm đòi hỏi **tính xác định đúng tuyệt đối trong miền dữ liệu hợp lệ**. Các quan hệ thống kê có xác suất cao nhưng đôi khi sai không phải phụ thuộc hàm chính xác.

## 4. Một phản ví dụ trong dữ liệu: phải kiểm tra tính hợp lệ trước khi kết luận

Về mặt toán học, một tập dòng có hai bản ghi cùng \(X\) nhưng khác \(Y\) là **phản ví dụ** đối với \(X\rightarrow Y\) trên tập dòng đó. Nhưng trong hệ thống thật, phản ví dụ trong bảng nhập tạm còn có thể là:

- **Dữ liệu lỗi:** hai dòng cùng `order_id` nhưng khác `customer_id` do quy trình đồng bộ ghi sai.
- **Thiếu thuộc tính phạm vi:** cùng `invoice_no = 001` ở hai cửa hàng; quy tắc đúng có thể là `(store_id, invoice_no) → invoice_date`.
- **Trộn phiên bản:** bản ghi cũ và mới của một đối tượng được lưu cùng lúc; khóa của **bản ghi lịch sử** phải chứa thêm phiên bản hoặc thời điểm phù hợp.
- **Hiểu nhầm ngữ nghĩa:** `customer_name_at_order` là tên chụp tại lúc mua; cùng một `customer_id` có thể xuất hiện với nhiều tên ở các đơn khác nhau.
- **Trùng lặp do ETL/join sai:** phép nối trên một khóa không đủ khiến một giao dịch bị nhân bản hoặc gắn thông tin sai.

Vì thế, phải tách hai câu hỏi:

1. **Trạng thái dữ liệu này có vi phạm phụ thuộc không?** — kiểm tra trực tiếp bằng truy vấn.
2. **Quy tắc phụ thuộc có sai về mặt nghiệp vụ không?** — chỉ kết luận sau khi xác minh các dòng vi phạm là **hợp lệ và được phép tồn tại**.

Ví dụ, nếu chính sách xác nhận `order_id → customer_id` và staging chứa hai mã khách cho cùng mã đơn, đó là **lỗi dữ liệu cần xử lý**. Không nên âm thầm thay quy tắc thành `(order_id, line_no) → customer_id` chỉ để dữ liệu hết vi phạm.

## 5. Phạm vi và thời gian có thể thay đổi hoàn toàn vế trái

### Trường hợp A — Định danh trong nhiều cửa hàng

Nghiệp vụ: “Số hóa đơn tăng từ 1 tại từng cửa hàng, có thể trùng giữa các cửa hàng.”

**Không nên suy ra**:

~~~text
invoice_no → invoice_date
~~~

Quy tắc có căn cứ hơn có thể là:

~~~text
(store_id, invoice_no) → invoice_date
~~~

Nếu số hóa đơn khởi động lại mỗi năm, cần xác nhận thêm `fiscal_year` hoặc một mã định danh toàn cục. Không tự thêm cột nếu chưa biết chính sách đánh số.

### Trường hợp B — Dữ liệu hiện hành và dữ liệu lịch sử

Một bảng `CUSTOMER_CURRENT(customer_id, customer_name)` chỉ giữ **tên hiện hành**. Khi mỗi mã khách có đúng một bản ghi hiện hành, ta có:

~~~text
customer_id → customer_name
~~~

Trong bảng `CUSTOMER_NAME_HISTORY(customer_id, valid_from, customer_name, valid_to)`, cùng khách có thể đổi tên nhiều lần. Khi đó:

~~~text
customer_id ↛ customer_name
~~~

Nếu mỗi `(customer_id, valid_from)` định danh duy nhất một phiên bản, có thể xác nhận:

~~~text
(customer_id, valid_from) → customer_name, valid_to
~~~

Việc coi `customer_id → customer_name` trên **toàn bảng lịch sử** sẽ đánh đồng “một giá trị tại mỗi thời điểm” với “một giá trị qua mọi thời điểm”. Một phụ thuộc hàm thông thường không tự diễn đạt điều kiện **khoảng thời gian không chồng lấn**; đó là ràng buộc thời gian cần kiểm soát riêng.

### Trường hợp C — Giá hiện hành khác giá đã bán

- `(product_id, price_list_id, effective_from) → list_price` có thể hợp lệ nếu bảng giá định danh từng phiên bản theo bộ thuộc tính này.
- `product_id → unit_price_at_sale` thường không đúng với bảng chi tiết giao dịch, vì một sản phẩm có thể bán theo khuyến mãi, khách hàng hoặc thời điểm khác nhau.
- `(order_id, line_no) → unit_price_at_sale` có thể đúng khi một dòng đơn hàng ghi nhận một giá giao dịch.

Tên cột có vẻ giống nhau không có nghĩa chúng tuân theo cùng một phụ thuộc. **Ý nghĩa nghiệp vụ và mức hạt** quyết định vế trái.

## 6. Dùng SQL khám phá ứng viên và tìm phản ví dụ

Các truy vấn dưới đây nhằm **phân tích dữ liệu**, không tự chứng nhận quy tắc. Giả sử bảng staging:

~~~text
staging_order_lines(
    order_id, line_no, customer_id, product_id, unit_price_at_sale
)
~~~

### 6.1. Tìm nhóm có cùng \(X\) nhưng khác \(Y\)

Để kiểm tra dữ liệu hiện có có phản ví dụ đối với `order_id → customer_id` hay không:

~~~sql
SELECT
    order_id,
    COUNT(*) AS row_count,
    COUNT(DISTINCT customer_id) AS distinct_customer_count
FROM staging_order_lines
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

Mỗi dòng kết quả là một `order_id` xuất hiện với **ít nhất hai mã khách không NULL khác nhau**. Hãy mở bản ghi gốc của những mã này để xác minh dữ liệu và ngữ nghĩa nghiệp vụ.

Ở đây `WHERE ... IS NOT NULL` nói rõ **phạm vi của phép kiểm tra**. Nếu các trường có thể thiếu, cần kiểm tra riêng dữ liệu thiếu và quy tắc `NOT NULL`; việc loại `NULL` không chứng minh phụ thuộc trên toàn bộ bảng.

### 6.2. Kiểm tra khả năng quan sát: có nhóm \(X\) nào lặp không?

Ngay cả khi không có vi phạm, cần xem dữ liệu có đủ cơ hội để bộc lộ phụ thuộc sai hay không:

~~~sql
WITH groups_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS row_count,
        COUNT(DISTINCT product_id) AS distinct_products
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY order_id
)
SELECT
    COUNT(*) AS orders_observed,
    SUM(CASE WHEN row_count > 1 THEN 1 ELSE 0 END)
        AS orders_with_multiple_rows,
    SUM(CASE WHEN distinct_products > 1 THEN 1 ELSE 0 END)
        AS orders_with_multiple_products
FROM groups_by_order;
~~~

Nếu `orders_with_multiple_rows = 0`, phụ thuộc `order_id → product_id` **chưa được kiểm tra thực chất** bởi mẫu vì mọi vế trái đều xuất hiện một lần. Nếu `orders_with_multiple_products > 0`, đã có phản ví dụ trên dữ liệu được xét.

**Cẩn thận:** `row_count > 1` đôi khi chỉ do trùng hàng khi ETL; số dòng lặp không bảo đảm có nhiều sự kiện nghiệp vụ độc lập. Xem thêm `line_no` và nguồn gốc dòng.

### 6.3. Tìm bản ghi cụ thể gây xung đột

~~~sql
WITH conflicting_orders AS (
    SELECT order_id
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND customer_id IS NOT NULL
    GROUP BY order_id
    HAVING COUNT(DISTINCT customer_id) > 1
)
SELECT
    s.order_id,
    s.line_no,
    s.customer_id,
    s.product_id
FROM staging_order_lines s
JOIN conflicting_orders c
    ON s.order_id = c.order_id
ORDER BY s.order_id, s.line_no;
~~~

Truy vấn trả lại các dòng cần tra soát, giúp xác định đây là **lỗi nhập**, **ghép sai** hay **ngoại lệ hợp lệ**.

### 6.4. Kiểm tra khóa nghiệp vụ được đề xuất

Nếu giả định `(order_id, line_no)` là duy nhất ở cấp dòng hàng:

~~~sql
SELECT
    order_id,
    line_no,
    COUNT(*) AS occurrences
FROM staging_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Nếu có kết quả, đó là các khóa trùng trong mẫu. Tuy nhiên, một tập dữ liệu sạch chưa chứng minh quy tắc duy nhất **đúng theo nghiệp vụ**. Ngoài ra, cần kiểm tra `order_id` và `line_no` có được phép `NULL` không trước khi triển khai khóa.

### Đọc kết quả đúng mức

| Quan sát từ profiling | Được kết luận | Chưa được kết luận |
|---|---|---|
| Không nhóm nào có hai \(Y\) khác nhau | Mẫu đang xét **chưa có phản ví dụ** trong phạm vi truy vấn | \(X\rightarrow Y\) là quy tắc toàn cục |
| Có hai \(Y\) khác nhau cho cùng \(X\) | Các dòng đang xét **không cùng thỏa** \(X\rightarrow Y\) | Chính sách nghiệp vụ sai, trước khi xác minh dữ liệu |
| Mỗi \(X\) xuất hiện đúng một lần | Mẫu không đủ sức phân biệt nhiều phụ thuộc giả | \(X\) chắc chắn là khóa ứng viên |
| Có nhiều nhóm \(X\) lặp và đều cùng \(Y\) | Mẫu cung cấp bằng chứng hỗ trợ một **ứng viên** | Phụ thuộc sẽ luôn đúng trong tương lai |

Các phép đếm cũng có giới hạn về chuẩn hóa chuỗi, collation, khoảng trắng và cách biểu diễn giá trị thiếu. Các vấn đề này cần được xử lý nhất quán theo hệ quản trị đang dùng.

## 7. Quy trình xác minh phụ thuộc từ yêu cầu nghiệp vụ

Thay vì lấy danh sách phụ thuộc trực tiếp từ thống kê, hãy lập **hồ sơ cho từng phụ thuộc ứng viên**.

### Bước 1 — Xác định mức hạt và thuộc tính

Hỏi: “Một dòng đại diện cho **một đơn**, **một dòng đơn**, **một phiên bản**, hay **một sự kiện thay đổi**?” Ghi rõ thời điểm dữ liệu và phạm vi tổ chức. Một phụ thuộc có thể đúng ở mức đơn nhưng sai ở mức dòng hàng.

### Bước 2 — Ghi câu quy tắc có thể bị phản bác

Đổi câu mơ hồ “mỗi khách hàng thường có một địa chỉ” thành câu có thể kiểm tra:

> “Trong bảng thông tin **địa chỉ giao hàng mặc định hiện hành**, mỗi `customer_id` có tối đa một `default_shipping_address_id` tại một thời điểm.”

Đây chỉ là **ví dụ câu cần xác nhận**; nếu nghiệp vụ cho phép nhiều địa chỉ mặc định theo kênh bán, phải bổ sung phạm vi thích hợp.

### Bước 3 — Chủ động tìm ngoại lệ

Hỏi người phụ trách nghiệp vụ:

- Có hai đối tượng khác nhau được dùng chung mã \(X\) không?
- Mã được cấp toàn cục, theo cửa hàng, theo năm hay theo tổ chức?
- Có cho phép một đối tượng có nhiều giá trị \(Y\) cùng lúc không?
- Khi \(Y\) thay đổi, hệ thống **ghi đè** hay **lưu nhiều phiên bản**?
- Có nhập dữ liệu từ các hệ thống có quy ước định danh khác nhau không?

Chính các trường hợp “khó” hoặc hiếm mới giúp phân biệt phụ thuộc thật với sự trùng hợp.

### Bước 4 — Dùng dữ liệu khám phá để hỗ trợ xác minh

Kiểm tra nhiều thời kỳ, nhiều chi nhánh, dữ liệu trước và sau thay đổi nghiệp vụ. Phân tích nhóm trùng \(X\), các phản ví dụ, tỷ lệ NULL và bản ghi nguồn. Nếu tìm thấy vi phạm, **phân loại nguyên nhân** trước khi sửa thiết kế.

### Bước 5 — Ghi nhận và phê duyệt giả định

Mỗi phụ thuộc được đưa vào thiết kế cần có định nghĩa, phạm vi, chủ sở hữu quy tắc và phương án kiểm soát. Ví dụ:

| Trường | Ví dụ ghi nhận |
|---|---|
| Ứng viên | `order_id → customer_id` |
| Định nghĩa | Mỗi đơn có một khách hàng chủ sở hữu |
| Mức hạt | Bản ghi đơn và các dòng hàng thuộc đơn |
| Phạm vi | `order_id` duy nhất toàn hệ thống |
| Thời gian | Trạng thái đơn hiện hành; lịch sử thay đổi lưu riêng nếu cần |
| Ngoại lệ | Không cho phép hai khách hiện hành trên một đơn |
| Người xác nhận | Chủ sở hữu quy trình đơn hàng |
| Cơ chế thực thi | `orders.order_id` khóa chính; `customer_id` là cột của `orders` |
| Chứng cứ hỗ trợ | Quy tắc nghiệp vụ + truy vấn phát hiện dữ liệu sai |

Nếu người phụ trách chưa xác nhận, đánh dấu **“giả định chưa xác minh”**. Đừng dùng ứng viên như phụ thuộc chắc chắn trong tính khóa, phủ tối thiểu hoặc chuẩn hóa.

## 8. Hậu quả nếu đưa phụ thuộc giả vào thiết kế

### 8.1. Chọn sai khóa ứng viên

Một mẫu chỉ có một sản phẩm trên mỗi đơn khiến `order_id` trông giống khóa của bảng dòng hàng. Nếu đặt `PRIMARY KEY(order_id)`, đơn hàng thứ hai có thêm dòng sản phẩm sẽ **không chèn được**; hoặc nhà phát triển buộc phải ghi đè dữ liệu cũ.

Khóa đúng cần dựa trên quy tắc “số dòng không lặp trong một đơn”, tức `(order_id, line_no)` trong ví dụ.

### 8.2. Chuẩn hóa và phân rã sai

Giả sử mặc nhiên `product_id → unit_price_at_sale` và chuyển `unit_price_at_sale` sang bảng `PRODUCTS`. Giá giao dịch lịch sử khi giảm giá hoặc đổi bảng giá có thể bị **ghi đè**, làm sai hóa đơn và báo cáo.

Ngược lại, phụ thuộc thật `order_id → customer_id` nên được thể hiện ở bảng `ORDERS` để tránh lặp và mâu thuẫn mã khách giữa các dòng.

### 8.3. Thực thi ràng buộc quá chặt hoặc quá lỏng

- Ràng buộc **quá chặt** như `UNIQUE(order_id, product_id)` sẽ chặn trường hợp một sản phẩm được phép xuất hiện ở nhiều dòng trong một đơn.
- Ràng buộc **quá lỏng** như bỏ khóa nghiệp vụ chỉ vì staging có lỗi sẽ cho phép các trạng thái không hợp lệ tiếp tục được ghi.

Ràng buộc cơ sở dữ liệu nên phản ánh **quy tắc đã xác nhận**, không phản ánh tình trạng ngẫu nhiên của dữ liệu hôm nay.

### 8.4. Ví dụ thiết kế SQL theo mức hạt đã xác nhận

Giả sử mỗi đơn có một khách hiện hành và số dòng là duy nhất trong mỗi đơn:

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id),
    order_date DATE NOT NULL
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Lược đồ này áp dụng các phụ thuộc đã xác nhận:

~~~text
order_id            → customer_id, order_date
product_id          → product_name
customer_id         → customer_name
(order_id, line_no) → product_id, quantity, unit_price_at_sale
~~~

Giá tại lúc bán vẫn nằm trong **dòng giao dịch**. Cơ chế `PRIMARY KEY`, `FOREIGN KEY`, `NOT NULL` và `CHECK` cùng nhau bảo vệ các loại quy tắc khác nhau; phụ thuộc hàm **không thay thế** toàn bộ ràng buộc miền và quan hệ tham chiếu.

## 9. Phát hiện phụ thuộc tự động: hữu ích nhưng phải có bước xác nhận

Các công cụ *data profiling* hoặc *functional dependency discovery* có thể quét dữ liệu để đưa ra:

~~~text
candidate: X → Y
support: số nhóm X có thể quan sát
violations: số nhóm X có từ hai Y khác nhau
null_rate: mức độ thiếu dữ liệu ở X/Y
scope: nguồn, thời gian và bộ lọc của mẫu
~~~

Đây là **danh sách ứng viên và bằng chứng dữ liệu**, chưa phải hợp đồng nghiệp vụ. Cần đặc biệt chú ý:

- Một cột gần như duy nhất khiến **rất nhiều phụ thuộc giả** có số vi phạm bằng 0.
- Phụ thuộc gần đúng (*approximate FD*) có một tỷ lệ ngoại lệ; nó không có cùng ý nghĩa với ràng buộc FD bắt buộc đúng tuyệt đối.
- Kết quả có thể thay đổi khi mở rộng nguồn dữ liệu, lấy thêm thời điểm hoặc bổ sung bản ghi ngoại lệ hiếm.
- Một bất thường được gắn nhãn “ngoại lệ thống kê” có thể lại là **trường hợp nghiệp vụ hợp lệ** quan trọng nhất cần mô hình hỗ trợ.

Nếu thiết kế bắt buộc hệ thống **cưỡng chế** một phụ thuộc, phải có câu quy tắc đã xác nhận. Không đặt `UNIQUE` chỉ vì công cụ profiling báo “độ tin cậy 99,9%”.

## 10. Áp dụng tư duy này cho các cách mô hình hóa khác

Trong **mô hình quan hệ**, phụ thuộc hàm là khái niệm hình thức phục vụ xác định khóa và chuẩn hóa.

Trong **mô hình document**, dữ liệu nhúng có thể được chọn để tối ưu truy vấn, nhưng cần biết trường nào là ảnh chụp lịch sử và trường nào là thông tin hiện hành. Một document đơn hàng không có nghĩa mã đơn chỉ có thể chứa một sản phẩm.

Trong **mô hình đồ thị**, các nút có thể có định danh hệ thống, định danh nghiệp vụ và thuộc tính có thể thay đổi. Việc các nút trong một bản xuất mẫu không trùng `external_id` không chứng minh `external_id` là khóa duy nhất toàn đồ thị.

Trong **mô hình phân tích**, mức hạt fact table, chiều thời gian, phân vùng và phiên bản dimension quyết định một tổ hợp cột có thực sự định danh một sự kiện hay không. Bảng tổng hợp theo tháng không thể dùng làm bằng chứng trực tiếp cho phụ thuộc ở bảng sự kiện chi tiết.

Điểm chung là phải xác định **mức hạt, phạm vi định danh, lịch sử và ngoại lệ** trước khi chọn cấu trúc hoặc tối ưu chỉ mục. Mỗi hệ lưu trữ có cơ chế cưỡng chế quy tắc khác nhau; không mặc định ràng buộc SQL được thực thi giống hệt ở document hay graph.

## 11. Bài luyện tập có lời giải

### Bài 1 — Phụ thuộc tình cờ do vế trái duy nhất

Cho dữ liệu `SALES(order_id, product_id)`:

| order_id | product_id |
|---|---|
| D1 | P1 |
| D2 | P2 |
| D3 | P3 |

**Câu hỏi:** Có thể khẳng định `order_id → product_id` là quy tắc nghiệp vụ không?

**Lời giải:** Không. Mẫu thỏa phụ thuộc vì mỗi `order_id` chỉ xuất hiện một lần. Nếu một đơn hợp lệ có nhiều sản phẩm, phụ thuộc sẽ sai trên bảng chi tiết. Cần hỏi “một dòng là một đơn hay một dòng hàng?” và liệu một đơn có nhiều sản phẩm được không.

### Bài 2 — Phản ví dụ và chất lượng dữ liệu

Một bảng staging có:

~~~text
(order_id = D1, customer_id = C1)
(order_id = D1, customer_id = C2)
~~~

Quy trình nghiệp vụ xác nhận mỗi đơn chỉ thuộc một khách. Bạn nên làm gì?

**Lời giải:** Hai dòng là phản ví dụ **trong staging**. Kiểm tra nguồn, lịch sử và phép nối; sửa dữ liệu hoặc cơ chế đồng bộ sai theo quy trình. Không tự sửa thành `(order_id, customer_id) → ...` và bỏ `order_id → customer_id` nếu nghiệp vụ không cho phép nhiều khách trên một đơn.

### Bài 3 — Khóa theo phạm vi tổ chức

Ba cửa hàng đều dùng hóa đơn số `0001`. Trong mẫu một cửa hàng, `invoice_no → invoice_date` không có vi phạm. Hãy đề xuất phụ thuộc cần xác minh khi gom dữ liệu toàn chuỗi.

**Lời giải:** Thử xác minh `(store_id, invoice_no) → invoice_date` nếu mã hóa đơn duy nhất trong từng cửa hàng. Nếu mã khởi động lại theo năm, còn cần xác nhận phạm vi thời gian hoặc một mã hóa đơn toàn cục. Không tự suy `invoice_no → invoice_date` từ mẫu một cửa hàng.

### Bài 4 — Thông tin hiện hành và lịch sử

Khách `KH01` có tên “An” trong hồ sơ năm 2024 và “An Nguyễn” sau khi đổi tên năm 2026. `customer_id → customer_name` đúng không?

**Lời giải:** Trên bảng **lịch sử nhiều phiên bản**, không. Trên bảng **chỉ chứa bản hiện hành**, có thể đúng nếu mã khách có đúng một tên hiện hành. Nếu dùng bảng lịch sử phiên bản, phải xác nhận khóa bổ sung như `(customer_id, valid_from)`; ràng buộc khoảng thời gian hiệu lực cần mô hình riêng.

### Bài 5 — Dữ liệu lớn nhưng thiếu sức kiểm chứng

Một công cụ báo “`receipt_id → product_id`: 0 vi phạm trên 2 triệu dòng”. Thống kê tiếp cho thấy có đúng 2 triệu giá trị `receipt_id` khác nhau. Kết luận nào hợp lý?

**Lời giải:** Mẫu không kiểm chứng được khả năng một biên lai có nhiều dòng. Mỗi `receipt_id` xuất hiện một lần nên bất kỳ thuộc tính nào cũng có vẻ được nó xác định. Cần kiểm tra mức hạt, tìm dữ liệu chi tiết thật và hỏi nghiệp vụ trước khi khẳng định.

### Bài 6 — Truy vấn trả về 0 dòng

Truy vấn tìm `COUNT(DISTINCT customer_id) > 1` theo `order_id` không trả kết quả. Có thể tạo ngay ràng buộc xem `order_id` xác định `customer_id` không?

**Lời giải:** Chưa đủ căn cứ. Phải kiểm tra tỷ lệ NULL, có bao nhiêu mã đơn xuất hiện nhiều dòng, dữ liệu có bao phủ các chi nhánh và giai đoạn cần thiết không, và quan trọng nhất là người sở hữu nghiệp vụ có xác nhận quy tắc một khách cho một đơn hay không. Sau khi xác nhận mới chọn cấu trúc/ràng buộc thích hợp.

## 12. Checklist trước khi đưa phụ thuộc vào mô hình

- [ ] Đã xác định đúng **mức hạt**: một dòng đại diện cho đối tượng hoặc sự kiện nào.
- [ ] Đã định nghĩa \(X\) và \(Y\) bằng **ngữ nghĩa nghiệp vụ**, không chỉ bằng tên cột.
- [ ] Đã xác nhận phạm vi định danh: toàn hệ thống, tenant, cửa hàng, năm hoặc phiên bản.
- [ ] Đã phân biệt thuộc tính **hiện hành**, **tại thời điểm giao dịch** và **lịch sử**.
- [ ] Đã chủ động tìm ngoại lệ hợp lệ, thay vì chỉ xem các dòng điển hình.
- [ ] Đã dùng profiling để tìm phản ví dụ, đồng thời ghi nhận bộ lọc, tỷ lệ NULL và độ lặp của vế trái.
- [ ] Đã xác minh xem dòng vi phạm là lỗi dữ liệu hay trường hợp nghiệp vụ hợp lệ.
- [ ] Đã có người phụ trách nghiệp vụ xác nhận phụ thuộc dùng để thiết kế.
- [ ] Chỉ dùng **phụ thuộc đã xác nhận** để tính bao đóng, khóa ứng viên, phủ tối thiểu và chuẩn hóa.
- [ ] Đã chọn khóa, `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, `CHECK` và cơ chế quản lý lịch sử phù hợp.

**Ghi nhớ:** **Không thấy hai dòng cùng \(X\) nhưng khác \(Y\) chỉ chứng minh mẫu hiện tại chưa bộc lộ vi phạm.** Một phản ví dụ trong dữ liệu có thể chỉ ra vấn đề cần điều tra; một phản ví dụ **hợp lệ theo nghiệp vụ** mới bác bỏ quy tắc đang đề xuất. Muốn mô hình dữ liệu rõ ràng, dễ tiến hóa và kiểm chứng, hãy xuất phát từ **quy tắc nghiệp vụ, mức hạt, phạm vi và thời gian**, rồi dùng dữ liệu làm bằng chứng hỗ trợ.
