# Tư duy tập hợp và cách mô tả kết quả bằng SQL

SQL (Structured Query Language) là ngôn ngữ dùng để **mô tả tập kết quả cần lấy hoặc thay đổi trong cơ sở dữ liệu quan hệ**. Khi mới học lập trình, ta thường quen với cách nghĩ: lấy một dòng, kiểm tra điều kiện, cộng dồn, rồi chuyển sang dòng tiếp theo. Với SQL, điểm xuất phát hiệu quả hơn là hỏi: **Những dòng nào thuộc kết quả? Kết quả cần những cột nào? Các dòng được kết hợp và tổng hợp theo quy tắc gì?**

Bài học này xây dựng tư duy tập hợp (*set-based thinking*) từ một tình huống bán hàng xuyên suốt. Trọng tâm là chuyển câu hỏi nghiệp vụ thành biểu thức SQL rõ ràng, kiểm soát đúng ý nghĩa của từng dòng kết quả và tránh các lỗi thường gặp khi làm việc với nhiều dòng dữ liệu.

## 1. Từ xử lý từng dòng đến mô tả kết quả

Giả sử cửa hàng muốn biết **tổng tiền của các đơn đã thanh toán theo từng khách hàng**.

Theo cách tư duy tuần tự, ta có thể hình dung:

```text
Khởi tạo tổng tiền cho từng khách hàng = 0
Lặp qua từng đơn hàng:
    Nếu đơn đã thanh toán:
        Cộng số tiền của đơn vào tổng của khách hàng tương ứng
Trả về danh sách khách hàng và tổng tiền
```

Thuật toán trên mô tả *cách thực hiện*: thứ tự lặp, biến tích lũy và cập nhật từng bước. SQL cho phép ta mô tả *kết quả mong muốn*:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS total_paid
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Một cách đọc sát ý nghĩa là: “Trong các đơn có trạng thái `PAID`, gom những đơn thuộc cùng một `customer_id`, sau đó trả về mã khách hàng và tổng `total_amount` của mỗi nhóm.” Cơ sở dữ liệu quyết định cách truy cập, lọc và nhóm dữ liệu để thực thi yêu cầu đó.

Đây là **tính khai báo** (*declarative*) của SQL: người viết truy vấn xác định điều kiện và hình dạng đầu ra, còn hệ quản trị cơ sở dữ liệu lập kế hoạch thực thi. Điều này không có nghĩa ta có thể bỏ qua hiệu năng; nó có nghĩa ta nên xác định đúng *ngữ nghĩa của kết quả* trước khi tối ưu cách lấy kết quả.

## 2. Dữ liệu mẫu: cùng một tình huống cho nhiều câu hỏi

Xét hai bảng trong hệ thống bán hàng:

**`customers` — danh sách khách hàng**

| customer_id | full_name | city |
|---:|---|---|
| 1 | An | Hà Nội |
| 2 | Bình | TP.HCM |
| 3 | Chi | Hà Nội |
| 4 | Dũng | Đà Nẵng |
| 5 | Hạnh | TP.HCM |

**`orders` — danh sách đơn hàng**

| order_id | customer_id | ordered_at | status | total_amount (VND) |
|---:|---:|---|---|---:|
| 101 | 1 | 2026-05-01 | PAID | 500000 |
| 102 | 1 | 2026-05-03 | CANCELLED | 80000 |
| 103 | 2 | 2026-05-05 | PAID | 200000 |
| 104 | 3 | 2026-05-07 | PAID | 120000 |
| 105 | 3 | 2026-06-01 | PAID | 300000 |
| 106 | 4 | 2026-06-02 | PENDING | 100000 |
| 107 | 2 | 2026-06-10 | PAID | 150000 |

Ở đây:

- Một dòng trong `customers` biểu diễn **một khách hàng**; `customer_id` là khóa chính phân biệt khách hàng.
- Một dòng trong `orders` biểu diễn **một đơn hàng**; `order_id` là khóa chính, còn `customer_id` liên kết đơn với khách hàng tương ứng.
- Một khách hàng có thể có nhiều đơn hoặc chưa có đơn nào. Đơn `CANCELLED` và `PENDING` không được xem là đã thanh toán.
- `total_amount` là tổng giá trị một đơn, không phải số tiền tích lũy của khách hàng.

Điều quan trọng nhất là biết **độ hạt** (*grain*) của dữ liệu: “một dòng nói về một đối tượng gì?”. Nếu truy vấn trả về một dòng trên mỗi đơn, khác với một dòng trên mỗi khách hàng, thì phép đếm và phép tính tổng cũng mang ý nghĩa khác nhau.

> Các ví dụ dùng cú pháp SQL thông dụng, với literal ngày `DATE 'YYYY-MM-DD'` phù hợp SQL chuẩn và PostgreSQL. Một số hệ quản trị có cách viết literal ngày hoặc giới hạn số dòng khác nhau; ý tưởng về tập kết quả không thay đổi.

## 3. Quan hệ, tập hợp và thực tế “bag” của SQL

Trong mô hình quan hệ, bảng có thể được hình dung như một **quan hệ** gồm nhiều bộ giá trị (*tuple*). Phép toán quan hệ không cần dựa vào thứ tự vật lý của các dòng. Ta thường nói “tập hợp các dòng”, nhưng cần phân biệt chính xác:

1. **Tập hợp toán học (set)** không có phần tử lặp.
2. **Kết quả SQL thông thường có thể có dòng trùng nhau**, thường gọi là *multiset* hoặc *bag*. `SELECT` mặc định không tự loại bỏ trùng lặp.
3. **Dòng kết quả không có thứ tự bảo đảm** nếu không có `ORDER BY`, dù công cụ hiện tại tình cờ hiển thị theo một thứ tự dễ đoán.

Ví dụ:

```sql
SELECT city
FROM customers;
```

Truy vấn trả về 5 dòng, vì có 5 khách hàng. Giá trị `Hà Nội` xuất hiện hai lần và `TP.HCM` cũng xuất hiện hai lần. Nếu yêu cầu là **các thành phố khác nhau đang có khách hàng**, ta chủ động chỉ rõ:

```sql
SELECT DISTINCT city
FROM customers;
```

Lúc này kết quả có 3 giá trị: `Hà Nội`, `TP.HCM`, `Đà Nẵng` (chưa quy định thứ tự). `DISTINCT` áp dụng lên **toàn bộ tổ hợp cột trong `SELECT`**, không chỉ một cột ngẫu nhiên.

Nếu yêu cầu có thứ tự, phải mô tả thứ tự đó:

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY customer_id ASC;
```

Không nên suy ra thứ tự mặc định từ khóa chính, thứ tự thêm dữ liệu hay kết quả của lần chạy trước.

## 4. Dịch câu hỏi tự nhiên thành cấu trúc SQL

Trước khi viết truy vấn, có thể diễn đạt đầu ra bằng sáu câu hỏi:

| Câu hỏi | Quyết định cần đưa ra | Thành phần SQL thường dùng |
|---|---|---|
| Mỗi dòng kết quả đại diện cho gì? | Một khách hàng, một đơn, hay một nhóm? | `FROM`, `JOIN`, `GROUP BY` |
| Cần dữ liệu từ nguồn nào? | Bảng nào, liên hệ qua khóa nào? | `FROM`, `JOIN ... ON` |
| Dòng nào đủ điều kiện? | Trạng thái, khoảng thời gian, địa điểm? | `WHERE` |
| Cần hiển thị thông tin gì? | Cột gốc hay biểu thức tính toán? | `SELECT`, `AS` |
| Có cần tổng hợp/lọc nhóm không? | Đếm, cộng, trung bình, ngưỡng? | `GROUP BY`, `HAVING` |
| Kết quả có cần phân biệt và sắp xếp không? | Loại trùng, xếp hạng, giới hạn? | `DISTINCT`, `ORDER BY`, `FETCH`/`LIMIT` |

Ví dụ câu hỏi: “Liệt kê mã đơn và số tiền của **các đơn đã thanh toán có giá trị từ 200.000 VND**, từ đơn cũ đến đơn mới.”

- Độ hạt: **một dòng trên mỗi đơn hàng**.
- Nguồn: `orders`, không cần bảng khách hàng.
- Điều kiện: `status = 'PAID'` và `total_amount >= 200000`.
- Đầu ra: mã đơn, số tiền.
- Thứ tự: ngày đặt tăng dần; thêm `order_id` để phá hòa nếu nhiều đơn cùng ngày.

```sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND total_amount >= 200000
ORDER BY ordered_at ASC, order_id ASC;
```

| order_id | total_amount |
|---:|---:|
| 101 | 500000 |
| 103 | 200000 |
| 105 | 300000 |

Chỉ yêu cầu cột đầu ra cần thiết; điều kiện và cột dùng để sắp xếp **không bắt buộc phải xuất hiện trong `SELECT`** ở truy vấn thông thường. Khi truy vấn sử dụng `DISTINCT` hoặc gom nhóm, một số hệ quản trị đặt thêm ràng buộc đối với biểu thức `ORDER BY`.

## 5. Các thao tác tập hợp cốt lõi

### 5.1. Lọc dòng bằng `WHERE`: giữ những dòng thỏa điều kiện

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND ordered_at >= DATE '2026-06-01'
  AND ordered_at < DATE '2026-07-01';
```

Đây là tập các đơn đã thanh toán trong tháng 6/2026: đơn **105** và **107**. Mỗi dòng được xét theo cùng một điều kiện; ta không cần viết vòng lặp thủ công.

Mẫu khoảng ngày nửa mở `>= ngày_bắt_đầu AND < ngày_bắt_đầu_kế_tiếp` đặc biệt hữu ích nếu cột lưu cả ngày và giờ (*timestamp*), vì không phải tự đoán thời điểm cuối cùng của ngày.

### 5.2. Chọn cột và biểu thức bằng `SELECT`

```sql
SELECT
    order_id,
    total_amount,
    total_amount * 0.10 AS illustrative_tax
FROM orders
WHERE status = 'PAID';
```

`SELECT` xác định hình dạng kết quả; biểu thức tính toán không làm thay đổi dữ liệu gốc. `illustrative_tax` chỉ là phép tính minh họa 10%, không đại diện cho quy tắc thuế thực tế. Dùng `AS` để đặt tên biểu thức có ý nghĩa cho người đọc hoặc chương trình nhận kết quả.

### 5.3. Ghép các tập dòng liên quan bằng `JOIN`

“Liệt kê tên khách hàng và từng đơn đã thanh toán của họ” đòi hỏi thông tin từ hai bảng:

```sql
SELECT
    c.full_name,
    o.order_id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Kết quả có **5 dòng đơn đã thanh toán**, không phải 3 dòng khách hàng, vì một khách hàng có thể có nhiều đơn. `JOIN` kết hợp các dòng thỏa điều kiện liên hệ; nó có thể **làm tăng số dòng** của một bảng khi một dòng ghép với nhiều dòng bên kia.

| full_name | order_id | total_amount |
|---|---:|---:|
| An | 101 | 500000 |
| Bình | 103 | 200000 |
| Bình | 107 | 150000 |
| Chi | 104 | 120000 |
| Chi | 105 | 300000 |

Nếu câu hỏi đổi thành “những khách hàng từng có đơn đã thanh toán”, kết quả mong muốn lại là **một dòng trên mỗi khách hàng**. Khi đó `EXISTS` ở phần sau thường diễn đạt ý định tốt hơn việc `JOIN` rồi sửa dòng lặp bằng `DISTINCT`.

### 5.4. Chia nhóm và tổng hợp bằng `GROUP BY`

“Mỗi khách hàng đã thanh toán bao nhiêu đơn, tổng cộng bao nhiêu tiền?”

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS total_paid
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
```

| customer_id | paid_order_count | total_paid |
|---:|---:|---:|
| 1 | 1 | 500000 |
| 2 | 2 | 350000 |
| 3 | 2 | 420000 |

`WHERE` loại bỏ các đơn không thanh toán **trước khi nhóm**. `GROUP BY customer_id` tạo một nhóm cho mỗi mã khách hàng còn lại. `COUNT(*)` đếm số dòng trong từng nhóm, còn `SUM(total_amount)` cộng giá trị trong nhóm đó.

Không xuất hiện khách hàng 4 và 5 vì bảng đơn sau khi lọc không có dòng nào thuộc họ. Đó là kết quả đúng cho yêu cầu **“những khách hàng có đơn đã thanh toán”**, nhưng sẽ chưa đủ cho yêu cầu **“toàn bộ khách hàng, kể cả người chưa thanh toán”**.

### 5.5. Lọc nhóm bằng `HAVING`

“Chỉ lấy khách hàng có ít nhất hai đơn đã thanh toán”:

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
```

Kết quả là khách hàng **2 (Bình)** và **3 (Chi)**, mỗi người có 2 đơn đã thanh toán. `WHERE` đặt điều kiện lên **từng dòng trước khi nhóm**; `HAVING` đặt điều kiện lên **mỗi nhóm sau khi tổng hợp**.

Ví dụ không thể thay `HAVING COUNT(*) >= 2` bằng `WHERE COUNT(*) >= 2`, vì tại thời điểm lọc dòng, nhóm chưa được tạo theo ngữ nghĩa logic của truy vấn.

## 6. Chọn đúng độ hạt khi kết hợp `JOIN` và tổng hợp

Bài toán: “Liệt kê **tất cả khách hàng**, kể cả người chưa có đơn đã thanh toán, cùng số đơn và tổng tiền đã thanh toán.”

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_paid
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

| customer_id | full_name | paid_order_count | total_paid |
|---:|---|---:|---:|
| 1 | An | 1 | 500000 |
| 2 | Bình | 2 | 350000 |
| 3 | Chi | 2 | 420000 |
| 4 | Dũng | 0 | 0 |
| 5 | Hạnh | 0 | 0 |

Cách đọc:

1. **Bắt đầu từ mọi dòng của `customers`**: đó là tập đối tượng bắt buộc giữ lại.
2. `LEFT JOIN` ghép vào chỉ các đơn có cùng khách hàng **và** trạng thái `PAID`.
3. Nếu một khách hàng không có đơn phù hợp, SQL vẫn giữ dòng khách hàng; các cột phía `orders` nhận `NULL`.
4. `COUNT(o.order_id)` chỉ đếm mã đơn không `NULL`, nên trả về `0` cho khách hàng không có đơn phù hợp.
5. `SUM` trên nhóm không có giá trị đơn phù hợp trả về `NULL`; `COALESCE(..., 0)` chuyển thành `0` để biểu diễn tổng tiền.

**Vị trí điều kiện trong `LEFT JOIN` thay đổi ý nghĩa câu hỏi.** So sánh đoạn đúng ở trên với truy vấn sau:

```sql
SELECT c.customer_id, COUNT(o.order_id)
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id;
```

Đặt `o.status = 'PAID'` trong `WHERE` làm các dòng khách hàng không có đơn thanh toán bị loại, do so sánh với `NULL` không thỏa điều kiện `WHERE`. Vì vậy truy vấn này chỉ còn khách hàng 1, 2 và 3.

Một bẫy khác là dùng `COUNT(*)` cho `LEFT JOIN`: dù không khớp đơn nào, dòng khách hàng vẫn tồn tại nên `COUNT(*)` có thể bằng **1**, không phải **0**. Hãy đếm một cột không `NULL` của phía được ghép, như khóa chính `o.order_id`, khi cần đếm các dòng thực sự khớp.

### Khi một phép nối có thể làm cộng tiền hai lần

Nếu sau này thêm bảng `order_items` (mỗi đơn có nhiều dòng sản phẩm), thì nối `orders` với `order_items` sẽ tạo **một dòng trên mỗi dòng sản phẩm**, không còn một dòng trên mỗi đơn. Lúc ấy:

```sql
-- Sai nếu mục tiêu là tổng tiền từng đơn: mỗi đơn có thể bị nhân số lần.
SELECT SUM(o.total_amount)
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id;
```

Nếu một đơn có 3 dòng sản phẩm, `o.total_amount` của đơn đó xuất hiện 3 lần sau phép nối. Để tránh lỗi, trước hết xác định độ hạt cần tính: **tính từ bảng đơn nếu cộng tổng tiền đơn**, hoặc **tổng hợp dữ liệu dòng sản phẩm về một dòng trên mỗi đơn trước khi nối**. `DISTINCT` áp dụng tùy tiện không sửa được mọi phép cộng trùng, nhất là khi các đơn khác nhau có cùng số tiền.

## 7. Diễn đạt “có”, “không có” bằng `EXISTS` và `NOT EXISTS`

Trong nhiều câu hỏi, ta quan tâm **sự tồn tại của dòng phù hợp**, chứ không cần lấy mọi dòng đó.

### 7.1. Khách hàng có ít nhất một đơn đã thanh toán

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả: **An, Bình, Chi** — mỗi người đúng một dòng. `EXISTS` hỏi liệu truy vấn con có **ít nhất một dòng** hay không. `SELECT 1` là quy ước dễ đọc vì giá trị được chọn không ảnh hưởng đến phép kiểm tra tồn tại. Điều kiện `o.customer_id = c.customer_id` khiến truy vấn con liên hệ với khách hàng đang xét (*correlated subquery*).

Viết bằng `JOIN` cũng có thể đúng nếu kiểm soát số dòng bằng `DISTINCT`, nhưng `EXISTS` thể hiện trực tiếp ý nghĩa “có ít nhất một”.

### 7.2. Khách hàng chưa có đơn đã thanh toán

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả là **Dũng** (chỉ có đơn `PENDING`) và **Hạnh** (chưa có đơn). Đây là hai trường hợp khác nhau về dữ liệu, nhưng đều thỏa cùng câu hỏi “không tồn tại đơn `PAID`”.

Cần phân biệt với “khách hàng **chưa từng đặt đơn**”: câu hỏi thứ hai phải kiểm tra `NOT EXISTS` trên **mọi đơn**, không có điều kiện `status = 'PAID'`; khi đó chỉ còn **Hạnh**.

### 7.3. Khi nào dùng `IN`?

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

`IN` diễn đạt “giá trị này thuộc tập giá trị kia”; ở ví dụ này kết quả cũng là An, Bình, Chi. `EXISTS` diễn đạt “tồn tại dòng thỏa quan hệ”. Cả hai đều hữu ích; hãy chọn cấu trúc nêu rõ ý định và kiểm tra kế hoạch thực thi khi cần tối ưu.

Đặc biệt cẩn thận với `NOT IN` nếu truy vấn con có khả năng trả về `NULL`: do logic ba giá trị, kết quả có thể bất ngờ. `NOT EXISTS` thường là cách rõ ràng, an toàn hơn để diễn đạt “không có dòng liên quan”. Trong dữ liệu mẫu, `orders.customer_id` được thiết kế không `NULL`, nhưng thói quen nhận diện rủi ro này vẫn quan trọng ở các hệ thống thực.

## 8. Gộp tập kết quả: `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT`

Đôi khi câu hỏi được hình thành từ **hai tập kết quả có cùng cấu trúc cột**. Các toán tử tập hợp giúp kết hợp chúng.

Giả sử muốn lấy mã khách hàng có đơn `PAID` trong **tháng 5 hoặc tháng 6 năm 2026**:

```sql
SELECT customer_id
FROM orders
WHERE status = 'PAID'
  AND ordered_at >= DATE '2026-05-01'
  AND ordered_at < DATE '2026-06-01'

UNION

SELECT customer_id
FROM orders
WHERE status = 'PAID'
  AND ordered_at >= DATE '2026-06-01'
  AND ordered_at < DATE '2026-07-01';
```

`UNION` loại các **dòng kết quả trùng toàn bộ giá trị cột**, nên tập mã trả về là `{1, 2, 3}`. `UNION ALL` giữ lại tất cả bản sao: ở dữ liệu mẫu, mã `1` xuất hiện một lần, `2` hai lần và `3` hai lần. Để biểu diễn yêu cầu đơn giản “đơn trong một trong hai tháng liên tiếp”, một `WHERE` với khoảng ngày từ 01/05 đến trước 01/07 cũng có thể ngắn gọn hơn.

Hai toán tử khác thường có trong SQL chuẩn là:

| Toán tử | Ý nghĩa mặc định (không `ALL`) | Ví dụ diễn đạt |
|---|---|---|
| `UNION` | Nằm trong ít nhất một trong hai kết quả | Khách có đơn trả tiền tháng 5 **hoặc** tháng 6 |
| `INTERSECT` | Nằm trong cả hai kết quả | Khách có đơn trả tiền **ở cả hai tháng** (Bình, Chi) |
| `EXCEPT` | Nằm ở kết quả thứ nhất nhưng không nằm ở thứ hai | Khách có đơn trả tiền tháng 5 **nhưng không có** trong tháng 6 (An) |
| `UNION ALL` | Nối các dòng và giữ trùng lặp | Giữ mọi lần xuất hiện của mã khách hàng |

Các nhánh của toán tử tập hợp phải có số cột tương ứng và kiểu dữ liệu tương thích. Kết quả tổng thể chỉ có thứ tự chắc chắn khi thêm `ORDER BY` ở bên ngoài biểu thức hợp nhất. Một số hệ quản trị hoặc phiên bản có mức hỗ trợ toán tử tập hợp khác nhau.

## 9. `NULL`: thiếu giá trị không đồng nghĩa bằng 0 hoặc chuỗi rỗng

`NULL` biểu diễn giá trị **không có hoặc chưa biết** trong ngữ cảnh dữ liệu. Trong SQL, điều kiện so sánh có thể nhận ba kết quả: `TRUE`, `FALSE` hoặc `UNKNOWN`.

```sql
-- Không đúng: phép so sánh với NULL không trả TRUE.
WHERE some_column = NULL

-- Đúng: kiểm tra thiếu giá trị bằng IS NULL.
WHERE some_column IS NULL
```

Điều kiện `WHERE` chỉ giữ những dòng có điều kiện là `TRUE`. Dòng có `FALSE` **hoặc** `UNKNOWN` đều không được giữ. Vì thế điều kiện đặt lên cột `NULL` ở phía phải của `LEFT JOIN` có thể loại các dòng khách hàng cần bảo toàn.

Khi tổng hợp:

- `COUNT(*)` đếm các dòng, kể cả dòng có cột `NULL`.
- `COUNT(column_name)` đếm các dòng mà `column_name` **không** là `NULL`.
- `SUM(column_name)` và `AVG(column_name)` bỏ qua các giá trị `NULL`; nếu không có giá trị không `NULL` để cộng, `SUM` trả về `NULL`.
- `COALESCE(value, fallback)` lấy giá trị đầu tiên không `NULL`; chỉ nên thay bằng `0` khi nghiệp vụ thật sự muốn diễn đạt như vậy.

Ví dụ: “không ghi số tiền” có thể nghĩa là **chưa biết số tiền**, không phải “đơn 0 VND”. Tự động biến mọi `NULL` thành `0` có thể làm mất ý nghĩa dữ liệu.

## 10. Thứ tự logic giúp đọc và kiểm tra truy vấn

SQL thường được **viết** bắt đầu bằng `SELECT`, nhưng để hiểu đúng kết quả, hãy đọc theo dòng chảy logic gần đúng:

```text
FROM / JOIN ... ON   → xác định các nguồn và ghép các dòng
WHERE              → lọc từng dòng
GROUP BY           → gom các dòng thành nhóm
HAVING             → lọc các nhóm
SELECT             → tạo các cột/biểu thức đầu ra
DISTINCT           → loại các dòng kết quả trùng
ORDER BY           → sắp xếp kết quả
FETCH / LIMIT      → lấy số dòng được yêu cầu
```

Đây là **mô hình tư duy về ngữ nghĩa**, không phải thứ tự vật lý mà cơ sở dữ liệu buộc phải chạy. Bộ tối ưu truy vấn có thể đổi thứ tự phép toán, sử dụng chỉ mục, chọn thuật toán nối hoặc gom nhóm mà vẫn giữ kết quả tương đương.

Từ mô hình trên, có thể lý giải một số quy tắc:

- Phép tổng hợp như `COUNT(*)` thường thuộc `SELECT`/`HAVING`, không phải điều kiện lọc từng dòng trong `WHERE`.
- Nếu muốn lọc đơn theo trạng thái rồi đếm, đặt trạng thái trong `WHERE`; nếu muốn lọc khách hàng theo số đơn, đặt điều kiện số lượng trong `HAVING`.
- Không được dựa vào `ORDER BY` trong một truy vấn con để bảo đảm thứ tự của kết quả ngoài cùng; cần sắp xếp ở lớp kết quả thực sự được trả về.
- `ORDER BY total_paid DESC, customer_id ASC` quy định rõ cách phá hòa khi hai khách hàng có cùng tổng tiền.

## 11. Từ một câu hỏi nghiệp vụ đến truy vấn hoàn chỉnh

**Đề bài:** “Tìm ba khách hàng có tổng giá trị đơn đã thanh toán cao nhất, hiển thị tên, số đơn đã thanh toán và tổng tiền. Nếu có cùng tổng tiền, ưu tiên mã khách hàng nhỏ hơn.”

### Bước 1: Chốt ý nghĩa của một dòng kết quả

Mỗi dòng phải là **một khách hàng**, không phải một đơn. Khách hàng có nhiều đơn `PAID` cần được gom lại trước khi xếp hạng.

### Bước 2: Xác định tập nguồn và tập cần giữ

Nguồn gồm `customers` (tên) và `orders` (trạng thái, số tiền). Chỉ xét đơn `PAID`, nhưng nên giữ khách hàng không có đơn khi bài toán dùng cụm “ba khách hàng” trên toàn bộ danh sách. Trong dữ liệu mẫu, họ có tổng bằng 0 và không lọt top 3.

### Bước 3: Chia phép tính thành hai lớp ý nghĩa

CTE (`WITH`) giúp đặt tên cho tập kết quả trung gian “doanh thu theo khách hàng”, rồi lấy top 3 từ tập ấy:

```sql
WITH customer_paid AS (
    SELECT
        c.customer_id,
        c.full_name,
        COUNT(o.order_id) AS paid_order_count,
        COALESCE(SUM(o.total_amount), 0) AS total_paid
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
       AND o.status = 'PAID'
    GROUP BY c.customer_id, c.full_name
)
SELECT
    customer_id,
    full_name,
    paid_order_count,
    total_paid
FROM customer_paid
ORDER BY total_paid DESC, customer_id ASC
FETCH FIRST 3 ROWS ONLY;
```

| customer_id | full_name | paid_order_count | total_paid |
|---:|---|---:|---:|
| 1 | An | 1 | 500000 |
| 3 | Chi | 2 | 420000 |
| 2 | Bình | 2 | 350000 |

`FETCH FIRST 3 ROWS ONLY` là cú pháp SQL chuẩn được nhiều hệ quản trị hỗ trợ; PostgreSQL cũng hỗ trợ `LIMIT 3`. Nếu yêu cầu là “lấy **tất cả** khách hàng đồng hạng ở vị trí thứ ba”, ta phải định nghĩa lại quy tắc top và dùng cách xếp hạng phù hợp, ví dụ hàm cửa sổ `RANK()` ở bài học nâng cao; giới hạn cố định 3 dòng không có ý nghĩa đồng hạng đó.

### Bước 4: Đọc lại truy vấn như một đặc tả

“Lấy toàn bộ khách hàng. Gắn các đơn `PAID` tương ứng, gom thành một dòng trên mỗi khách hàng, đếm đơn và tính tổng tiền. Cuối cùng xếp theo tổng tiền giảm dần, theo mã tăng dần nếu hòa, rồi chọn ba dòng đầu.”

Nếu không thể đọc lại SQL thành một câu chính xác như vậy, rất có thể độ hạt, điều kiện hoặc phép ghép chưa đúng với yêu cầu.

## 12. Những nhầm lẫn thường gặp khi tư duy theo tập hợp

| Biểu hiện | Vì sao sai hoặc thiếu | Cách xác định lại |
|---|---|---|
| `JOIN` xong có nhiều dòng hơn số khách | Quan hệ một-nhiều sinh nhiều dòng cho mỗi khách | Xác định một dòng đầu ra đại diện cho khách hay đơn; dùng `EXISTS` hoặc `GROUP BY` nếu cần |
| Dùng `DISTINCT` để chữa tổng tiền bị nhân | Loại trùng ở kết quả không sửa độ hạt của phép cộng trước đó | Tổng hợp tại độ hạt đúng trước khi nối |
| `LEFT JOIN` mà mất khách chưa có đơn | Điều kiện phía bảng phải được đưa vào `WHERE` | Đặt điều kiện ghép phù hợp trong `ON`; hiểu rõ khi nào cần `WHERE` |
| Đếm khách chưa có đơn thành 1 | `COUNT(*)` đếm dòng được giữ bởi `LEFT JOIN` | Đếm khóa không `NULL` của bảng được ghép |
| Dùng `WHERE COUNT(*) > 1` | `WHERE` không lọc các nhóm đã tổng hợp | Dùng `HAVING COUNT(*) > 1` |
| Kết quả đổi thứ tự khi chạy lại | Không có quy tắc sắp xếp đầu ra | Thêm `ORDER BY` và điều kiện phá hòa khi cần |
| Thiếu dòng do so sánh `NULL` | `NULL = ...` cho kết quả `UNKNOWN` | Dùng `IS NULL`, `IS NOT NULL` và xét logic ba giá trị |
| Một khoảng tháng bỏ sót dữ liệu cuối ngày | Dùng giới hạn `<=` không phù hợp với timestamp | Dùng khoảng nửa mở: `>= start AND < next_start` |

Tư duy tập hợp cũng giúp chọn một truy vấn chung thay cho việc tải nhiều dòng về ứng dụng để lặp từng dòng. Tuy nhiên, “viết một câu SQL” không tự động đồng nghĩa “nhanh nhất”: hiệu năng còn phụ thuộc khối lượng dữ liệu, chỉ mục, thống kê, chiến lược `JOIN` và kế hoạch thực thi. Khi làm việc trên dữ liệu lớn, cần xem `EXPLAIN` hoặc công cụ tương đương, nhưng chỉ sau khi đã xác nhận ngữ nghĩa cần trả về.

## 13. Bài tập tự luyện

Dùng hai bảng dữ liệu mẫu ở mục 2. Trước khi viết truy vấn, hãy ghi rõ “một dòng kết quả đại diện cho gì” và dự đoán các giá trị trả về.

**Bài 1 — Lọc:** Lấy mã đơn và số tiền của các đơn `PAID` trong tháng 5/2026, xếp theo mã đơn tăng dần.

**Bài 2 — Tổng hợp:** Với mỗi thành phố, tính số khách hàng hiện có. Sắp xếp số khách giảm dần, rồi tên thành phố tăng dần.

**Bài 3 — Không tồn tại:** Liệt kê khách hàng chưa từng có bất kỳ đơn hàng nào, dù đơn thuộc trạng thái gì.

**Bài 4 — Tổng hợp có điều kiện:** Tìm các khách hàng có tổng tiền đơn `PAID` từ 400.000 VND trở lên; kết quả gồm mã khách và tổng tiền, xếp tổng tiền giảm dần.

<details>
<summary>Gợi ý lời giải và kết quả mong đợi</summary>

**Bài 1:** Một dòng trên mỗi đơn phù hợp; kết quả là đơn `101`, `103`, `104`.

```sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND ordered_at >= DATE '2026-05-01'
  AND ordered_at < DATE '2026-06-01'
ORDER BY order_id;
```

**Bài 2:** Một dòng trên mỗi thành phố; Hà Nội: 2, TP.HCM: 2, Đà Nẵng: 1. Thứ tự hai thành phố có 2 khách phụ thuộc quy tắc sắp xếp chuỗi/collation của hệ quản trị.

```sql
SELECT city, COUNT(*) AS customer_count
FROM customers
GROUP BY city
ORDER BY customer_count DESC, city ASC;
```

**Bài 3:** Một dòng trên mỗi khách hàng chưa có đơn nào; kết quả chỉ có **Hạnh (5)**.

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

**Bài 4:** Một dòng trên mỗi khách có tổng `PAID` đạt ngưỡng; **An: 500000** và **Chi: 420000**.

```sql
SELECT customer_id, SUM(total_amount) AS total_paid
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(total_amount) >= 400000
ORDER BY total_paid DESC;
```

</details>

## 14. Phụ lục: SQL tạo dữ liệu mẫu để thực hành

Các lệnh sau phù hợp với PostgreSQL. Có thể chạy trong một cơ sở dữ liệu thử nghiệm riêng để tự đối chiếu ví dụ.

```sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    ordered_at DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 0) NOT NULL
);

INSERT INTO customers (customer_id, full_name, city) VALUES
    (1, 'An',   'Hà Nội'),
    (2, 'Bình', 'TP.HCM'),
    (3, 'Chi',  'Hà Nội'),
    (4, 'Dũng', 'Đà Nẵng'),
    (5, 'Hạnh', 'TP.HCM');

INSERT INTO orders (order_id, customer_id, ordered_at, status, total_amount) VALUES
    (101, 1, DATE '2026-05-01', 'PAID',      500000),
    (102, 1, DATE '2026-05-03', 'CANCELLED',  80000),
    (103, 2, DATE '2026-05-05', 'PAID',      200000),
    (104, 3, DATE '2026-05-07', 'PAID',      120000),
    (105, 3, DATE '2026-06-01', 'PAID',      300000),
    (106, 4, DATE '2026-06-02', 'PENDING',   100000),
    (107, 2, DATE '2026-06-10', 'PAID',      150000);
```

## 15. Nguyên tắc mang sang những bài SQL tiếp theo

Khi nhận một yêu cầu mới, hãy diễn đạt kết quả bằng lời trước: **mỗi dòng là gì; lấy từ đâu; dòng nào được giữ; có cần ghép, chia nhóm, tính tổng hay kiểm tra tồn tại; có cần loại trùng và sắp xếp không**. Sau đó ánh xạ từng quyết định sang `FROM`/`JOIN`, `WHERE`, `GROUP BY`, `HAVING`, `SELECT`, `EXISTS`, `DISTINCT` và `ORDER BY`.

Cách tư duy này áp dụng rộng hơn ví dụ bán hàng: đếm sinh viên theo lớp, tìm sản phẩm chưa có giao dịch, xác định tài khoản hoạt động trong tháng, tổng hợp lượt truy cập theo ngày, hoặc so sánh hai nhóm dữ liệu. SQL trở nên dễ đọc hơn khi mỗi truy vấn là một **mô tả có thể kiểm chứng về tập kết quả**, thay vì một chuỗi thao tác mơ hồ lên từng dòng.
