# Chọn từng cột, đặt bí danh và tránh phụ thuộc `SELECT *`

Trong SQL, `SELECT` xác định **những biểu thức nào xuất hiện trong kết quả truy vấn**. Một câu lệnh có thể lấy một cột, nhiều cột, biểu thức tính toán hoặc kết quả tổng hợp. Khi viết SQL phục vụ ứng dụng, việc **chọn đúng các cột cần dùng** và **đặt bí danh dễ hiểu** giúp câu truy vấn vừa rõ về ngữ nghĩa, vừa có đầu ra ổn định để mã ứng dụng, API hoặc báo cáo sử dụng.

Cú pháp `SELECT *` rất thuận tiện khi khám phá bảng, nhưng nó khiến câu truy vấn phụ thuộc vào toàn bộ tập cột hiện có. Khi bảng được thêm cột, dữ liệu ngày càng lớn hoặc một bảng được JOIN với bảng khác, phụ thuộc đó có thể làm tăng dữ liệu truyền tải, tạo tên cột trùng, khiến mã đọc kết quả khó kiểm soát và vô tình đưa thông tin không cần thiết ra ngoài.

Bài học này trình bày cách chọn từng cột, đặt bí danh cho cột và bảng, sử dụng tên cột rõ ràng khi JOIN và thiết kế **hợp đồng đầu ra** có chủ đích. Ví dụ dùng **PostgreSQL**, nhưng các nguyên tắc chính áp dụng rộng rãi cho SQL và hệ quản trị cơ sở dữ liệu quan hệ.

## 1. Chọn cột là một phần của ý nghĩa câu truy vấn

Giả sử bảng `customers` có các cột:

| Cột | Ý nghĩa |
| --- | --- |
| `customer_id` | Định danh khách hàng |
| `full_name` | Họ tên |
| `email` | Địa chỉ email |
| `phone` | Số điện thoại tùy chọn |
| `created_at` | Thời điểm tạo hồ sơ |
| `internal_note` | Ghi chú chỉ phục vụ bộ phận nội bộ |

Màn hình danh sách khách hàng chỉ cần **mã, tên và thời điểm đăng ký**. Hai cách truy vấn có thể đều trả được ba thông tin đó, nhưng tạo hợp đồng dữ liệu khác nhau:

```sql
-- Lấy tất cả cột hiện có của bảng.
SELECT *
FROM customers;

-- Chỉ chọn dữ liệu mà màn hình cần.
SELECT customer_id, full_name, created_at
FROM customers;
```

Ở truy vấn thứ nhất, tầng ứng dụng phải nhận cả `email`, `phone`, `internal_note`, dù giao diện không hiển thị. Ở truy vấn thứ hai, kết quả có đúng **ba cột được liệt kê**, theo thứ tự đã viết.

Điều này có ba lợi ích cụ thể:

1. **Rõ nghĩa:** người đọc nhìn vào SELECT biết chức năng dùng những trường nào.
2. **Ổn định đầu ra:** thêm cột mới vào bảng không tự làm tăng số cột mà truy vấn này trả về.
3. **Kiểm soát chi phí và phạm vi dữ liệu:** tránh lấy những cột lớn hoặc không cần thiết, đồng thời giảm khả năng phát tán dữ liệu nội bộ qua kết quả truy vấn.

Một câu SQL tốt không nhất thiết ngắn nhất; nó nên diễn đạt chính xác **đầu vào cần lọc** và **đầu ra cần trả về**.

### 1.1. Projection là gì?

Trong đại số quan hệ, **phép chiếu (projection)** chọn các thuộc tính của một quan hệ. Trong SQL, danh sách biểu thức sau SELECT đảm nhiệm vai trò chọn cột đầu ra, ví dụ:

```sql
SELECT customer_id, full_name
FROM customers;
```

Tuy nhiên, SQL mặc định áp dụng **bag semantics** (cho phép nhiều hàng trùng nhau) trong nhiều truy vấn. Vì vậy, `SELECT full_name` vẫn có thể trả cùng tên nhiều lần; khác với khái niệm projection theo tập hợp thuần túy, SQL chỉ loại hàng trùng khi dùng `DISTINCT` hoặc khi có quy tắc tương đương khác.

```sql
-- Có thể trả nhiều hàng cùng full_name.
SELECT full_name
FROM customers;

-- Trả mỗi giá trị full_name một lần theo ngữ nghĩa DISTINCT.
SELECT DISTINCT full_name
FROM customers;
```

**Chọn cột** và **loại trùng hàng** là hai quyết định khác nhau. Không nên thêm DISTINCT chỉ để sửa vấn đề JOIN sai hoặc thiết kế dữ liệu chưa đúng.

## 2. Môi trường ví dụ tự chứa

Các câu sau dùng bảng tạm PostgreSQL để có thể thử nghiệm độc lập trong một phiên kết nối:

```sql
CREATE TEMP TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    internal_note TEXT NULL
);

CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_customers(customer_id),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED')),
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO demo_customers
    (customer_id, full_name, email, phone, created_at, internal_note)
VALUES
    (1, 'An',   'an@example.test',   '0901000001',
        TIMESTAMPTZ '2026-04-01 09:00:00+07', 'Khách ưu tiên'),
    (2, 'Binh', 'binh@example.test', NULL,
        TIMESTAMPTZ '2026-04-02 10:00:00+07', NULL),
    (3, 'Chi',  'chi@example.test',  '0901000003',
        TIMESTAMPTZ '2026-04-03 11:00:00+07', 'Chỉ dùng nội bộ');

INSERT INTO demo_orders
    (order_id, customer_id, total_amount, status, created_at)
VALUES
    (101, 1, 200000.00, 'PAID',
        TIMESTAMPTZ '2026-04-05 08:00:00+07'),
    (102, 1,  50000.00, 'PENDING',
        TIMESTAMPTZ '2026-04-06 13:00:00+07'),
    (103, 2,  75000.00, 'PAID',
        TIMESTAMPTZ '2026-04-07 14:00:00+07');
```

Dữ liệu mẫu có ba khách và ba đơn; khách **Chi** chưa có đơn. Hai bảng đều có cột `customer_id` và `created_at`. Chính sự trùng tên này sẽ giúp quan sát vì sao cần chỉ rõ nguồn cột khi JOIN.

## 3. Chọn một cột, nhiều cột và biểu thức

### 3.1. Chọn một cột

```sql
SELECT full_name
FROM demo_customers
ORDER BY customer_id;
```

Kết quả:

| full_name |
| --- |
| An |
| Binh |
| Chi |

Mặc dù `customer_id` nằm trong `ORDER BY`, truy vấn vẫn chỉ trả cột `full_name`. Trong trường hợp đơn giản, PostgreSQL cho phép dùng cột nguồn để sắp xếp dù không xuất hiện trong danh sách SELECT, miễn không có quy tắc khác như DISTINCT làm hạn chế.

### 3.2. Chọn nhiều cột đúng nhu cầu

```sql
SELECT customer_id, full_name, email
FROM demo_customers
ORDER BY customer_id;
```

Kết quả:

| customer_id | full_name | email |
| ---: | --- | --- |
| 1 | An | an@example.test |
| 2 | Binh | binh@example.test |
| 3 | Chi | chi@example.test |

**Thứ tự trong danh sách SELECT** quyết định thứ tự cột đầu ra; **ORDER BY** quyết định thứ tự hàng. Hai thứ tự này độc lập:

```sql
SELECT email, customer_id, full_name
FROM demo_customers
ORDER BY full_name DESC;
```

Truy vấn trả các cột theo thứ tự `email`, `customer_id`, `full_name`, nhưng hàng được sắp theo `full_name` giảm dần. Không có `ORDER BY`, SQL không cam kết thứ tự các hàng, kể cả khi SELECT chứa khóa chính.

### 3.3. SELECT có thể chứa biểu thức, không chỉ tên cột

```sql
SELECT
    order_id,
    total_amount,
    total_amount * 0.10 AS estimated_tax,
    total_amount * 1.10 AS estimated_total
FROM demo_orders
ORDER BY order_id;
```

Hai cột `estimated_tax` và `estimated_total` được tính ở thời điểm truy vấn. Chúng **không tự được lưu thành cột vật lý** của `demo_orders`. Tỷ lệ 10% chỉ là giả định minh họa, không đại diện cho chính sách thuế áp dụng trong mọi trường hợp; bài toán thuế thực tế còn cần quy tắc tính và làm tròn riêng.

Biểu thức SELECT có thể là phép tính, hàm, `CASE`, phép nối chuỗi hoặc kết quả tổng hợp:

```sql
SELECT
    customer_id,
    full_name,
    CASE
        WHEN phone IS NULL THEN 'Chưa có số điện thoại'
        ELSE 'Đã có số điện thoại'
    END AS phone_status
FROM demo_customers
ORDER BY customer_id;
```

Đặt bí danh giúp người dùng kết quả hiểu `phone_status` là một cột suy ra, thay vì nhận một tên biểu thức dài hoặc tên tự sinh khó đọc.

## 4. Bí danh cột với AS: tên của kết quả, không phải tên nguồn

**Bí danh (alias)** đặt tên cho một cột hoặc biểu thức **trong kết quả của khối SELECT hiện tại**:

```sql
SELECT
    customer_id AS id,
    full_name AS customer_name,
    created_at AS registered_at
FROM demo_customers;
```

Đầu ra có các cột `id`, `customer_name`, `registered_at`; tên cột gốc trong bảng vẫn là `customer_id`, `full_name`, `created_at`. **AS không đổi tên cột của bảng** và không thực hiện lệnh DDL nào.

Trong nhiều DBMS, có thể bỏ từ khóa AS khi đặt bí danh:

```sql
SELECT customer_id id, full_name customer_name
FROM demo_customers;
```

Tuy vậy, dùng `AS` rõ ràng thường dễ đọc hơn, đặc biệt với biểu thức dài. Một cách đặt tên tốt thể hiện **ý nghĩa của giá trị** hoặc **hợp đồng đầu ra** mà tầng sử dụng mong đợi:

```sql
SELECT
    customer_id AS customer_id,
    full_name AS customer_name,
    created_at AS customer_registered_at
FROM demo_customers;
```

Nếu tên gốc đã rõ, không bắt buộc đặt lại. `customer_id AS customer_id` hợp lệ nhưng thường thừa; chỉ cần bí danh khi muốn xác định tên đầu ra theo quy ước nhất quán hoặc tránh trùng.

### 4.1. Bí danh biểu thức là thói quen hữu ích

```sql
SELECT
    customer_id,
    COALESCE(phone, '(chưa khai báo)') AS display_phone,
    UPPER(full_name) AS uppercase_name
FROM demo_customers
ORDER BY customer_id;
```

Không có AS, DBMS có thể tạo tên mặc định theo hàm hoặc biểu thức. Các tên đó ít ổn định cho mã đọc dữ liệu và không truyền đạt nghĩa sản phẩm bằng bí danh có chủ đích.

Ví dụ tổng hợp:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_order_amount
FROM demo_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Đặt tên `order_count` và `total_order_amount` giúp phân biệt số đơn với giá trị tiền. Không nên đặt chung `total` cho cả hai vì dễ gây hiểu nhầm khi ánh xạ vào DTO hoặc API.

### 4.2. Tên bí danh, chữ hoa và dấu nháy kép

Trong PostgreSQL, tên định danh **không đặt trong dấu nháy kép** thường được chuẩn hóa thành chữ thường:

```sql
SELECT full_name AS customerName
FROM demo_customers;
-- Tên cột đầu ra của PostgreSQL thường là customername.
```

Nếu muốn giữ nguyên chữ hoa/chữ thường hoặc dùng dấu cách trong tên:

```sql
SELECT
    full_name AS "customerName",
    created_at AS "Ngày đăng ký"
FROM demo_customers;
```

Dấu nháy kép `"` ở đây dành cho **identifier** (tên cột/alias), khác với dấu nháy đơn `'` dành cho **giá trị chuỗi**. Tuy nhiên, bí danh có dấu cách hoặc chữ hoa đặc biệt có thể khiến truy vấn ngoài, ORM và công cụ báo cáo phải quote nhất quán. Với SQL dùng lâu dài, quy ước `snake_case` như `customer_name`, `registered_at` thường thuận tiện.

Không đặt tên bí danh quá chung hoặc dễ đụng từ khóa SQL. Tên mang nghĩa ổn định quan trọng hơn tên ngắn. Nếu cần tên JSON theo camelCase, tầng ứng dụng có thể ánh xạ từ bí danh SQL hoặc sử dụng alias có quote theo hợp đồng đã quy định.

### 4.3. Tránh hai cột đầu ra trùng tên

SQL có thể tạo ra một tập kết quả với **hai cột có cùng nhãn**, tùy truy vấn:

```sql
SELECT
    customer_id AS id,
    customer_id + 1000 AS id
FROM demo_customers;
```

Đầu ra có thể chứa hai cột đều mang nhãn `id`. Người đọc ResultSet bằng tên hoặc một công cụ ánh xạ object có thể không biết nên lấy cột nào; có thư viện chọn cột đầu tiên, có thư viện xử lý khác hoặc báo lỗi.

Nên đặt các tên riêng:

```sql
SELECT
    customer_id AS customer_id,
    customer_id + 1000 AS external_display_id
FROM demo_customers;
```

Đặc biệt trong JOIN, tránh cùng đặt `id` cho nhiều khóa. Tên cột đầu ra là một phần của giao diện dữ liệu giữa SQL và nơi tiêu thụ.

## 5. Bí danh bảng và tên cột có tiền tố

Khi JOIN, nhiều bảng có thể có cột tên giống nhau. Trong dữ liệu mẫu, `demo_customers` và `demo_orders` đều có `customer_id` và `created_at`.

```sql
-- Không rõ created_at đến từ bảng nào:
SELECT customer_id, created_at
FROM demo_customers
JOIN demo_orders
    ON demo_customers.customer_id = demo_orders.customer_id;
```

Trên PostgreSQL, câu này gặp lỗi **ambiguous column** vì cả hai bảng đều cung cấp `customer_id` và `created_at`.

Đặt bí danh bảng:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at AS order_created_at
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

`c` là bí danh của `demo_customers`, còn `o` là bí danh của `demo_orders`. Dấu chấm trong `c.customer_id` cho biết cột thuộc nguồn `c`, **không phải một phần của tên cột**.

Một số quy ước tên dễ đọc:

- Với truy vấn ngắn và hai bảng rõ ràng, `c`/`o` là bí danh phổ biến.
- Với nhiều nguồn có tên tương tự, `customer`, `billing_order` hoặc `shipping_order` có thể rõ nghĩa hơn một chữ cái.
- Bí danh cột đầu ra nên nêu nội dung, ví dụ `customer_created_at` và `order_created_at`, để tránh hai trường thời gian cùng tên.

Trong PostgreSQL, khi một bảng đã được đặt bí danh `AS c`, tên alias là cách tham chiếu chính trong khối truy vấn; không nên tiếp tục dùng tên gốc `demo_customers.customer_id` ở cùng khối như thể chưa có alias.

### 5.1. Phân biệt bí danh bảng và bí danh cột

```sql
SELECT
    c.full_name AS customer_name
FROM demo_customers AS c;
```

- `AS c` đặt tên cho **nguồn bảng** để tham chiếu như `c.full_name`.
- `AS customer_name` đặt tên cho **cột đầu ra** của biểu thức `c.full_name`.

Đặt alias cho bảng không đổi tên cột xuất ra; đặt alias cho cột không đổi tên bảng hoặc cột lưu trong database.

### 5.2. JOIN càng nhiều bảng, SELECT * càng dễ gây nhầm

```sql
-- Có thể trả cả hai customer_id và cả hai created_at:
SELECT *
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id;
```

Trong kết quả, các tên cột `customer_id` và `created_at` có thể xuất hiện **hai lần**. Chúng thuộc hai bảng, nhưng chỉ nhìn nhãn cột của một công cụ ánh xạ có thể không phân biệt rõ. Hơn nữa, truy vấn còn đưa `email`, `phone`, `internal_note`, `status`, ... vào kết quả mà màn hình có thể không cần.

Nên chủ động tạo đầu ra:

```sql
SELECT
    c.customer_id,
    c.full_name AS customer_name,
    o.order_id,
    o.total_amount AS order_amount,
    o.status AS order_status,
    o.created_at AS order_created_at
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Kết quả có sáu cột phân biệt rõ vai trò. **Không phải mọi JOIN đều làm số hàng bằng số khách:** khách An có hai đơn sẽ xuất hiện hai lần trong kết quả INNER JOIN; đó là kết quả đúng theo quan hệ một-nhiều, không phải lỗi của SELECT.

### 5.3. `table_alias.*` là lựa chọn trung gian nhưng vẫn phụ thuộc schema

```sql
SELECT c.*, o.order_id, o.total_amount
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id;
```

`c.*` mở rộng thành **mọi cột hiện có của nguồn `c`**. Nó tránh lấy toàn bộ cột của `o`, nhưng vẫn mang theo mọi cột khách hàng, gồm `internal_note`, và vẫn chịu tác động nếu `demo_customers` có thêm cột. Vì thế, `c.*` chỉ phù hợp khi chủ ý thật sự cần mọi cột của nguồn ấy.

## 6. Bí danh SELECT được dùng ở đâu?

Một điểm quan trọng trong cú pháp và ngữ nghĩa SQL: biểu thức đầu ra của SELECT được hiểu về mặt logic **sau** FROM và WHERE, nên không thể mặc định dùng bí danh của SELECT ngay trong WHERE của cùng khối.

```sql
-- Không hợp lệ trong PostgreSQL:
SELECT
    total_amount * 1.10 AS estimated_total
FROM demo_orders
WHERE estimated_total >= 100000;
```

Ở bước WHERE, `estimated_total` chưa là cột nguồn. Có hai cách thể hiện đúng.

**Cách 1 — dùng lại biểu thức:**

```sql
SELECT
    order_id,
    total_amount * 1.10 AS estimated_total
FROM demo_orders
WHERE total_amount * 1.10 >= 100000
ORDER BY order_id;
```

**Cách 2 — dùng truy vấn con hoặc CTE tạo cột đầu ra cho khối ngoài:**

```sql
WITH order_totals AS (
    SELECT
        order_id,
        total_amount * 1.10 AS estimated_total
    FROM demo_orders
)
SELECT
    order_id,
    estimated_total
FROM order_totals
WHERE estimated_total >= 100000
ORDER BY order_id;
```

Ở khối SELECT ngoài, `estimated_total` là một cột đã được nguồn `order_totals` cung cấp, nên WHERE có thể tham chiếu hợp lệ.

### 6.1. ORDER BY có thể dùng alias đầu ra

```sql
SELECT
    customer_id,
    SUM(total_amount) AS total_spending
FROM demo_orders
GROUP BY customer_id
ORDER BY total_spending DESC, customer_id;
```

PostgreSQL cho phép ORDER BY dùng alias `total_spending` từ SELECT. Vì vậy, đặt bí danh cho biểu thức tính toán giúp truy vấn dễ đọc hơn và giảm việc phải chép lại biểu thức dài trong ORDER BY.

GROUP BY và HAVING có quy tắc tham chiếu alias khác nhau giữa các DBMS; chẳng hạn PostgreSQL có thể cho phép alias đầu ra trong một số dạng GROUP BY, nhưng không hỗ trợ dùng alias tổng hợp tùy ý trong HAVING như nhiều người kỳ vọng. Cách viết rõ ràng, dễ chuyển hệ cho điều kiện tổng hợp là:

```sql
SELECT customer_id, SUM(total_amount) AS total_spending
FROM demo_orders
GROUP BY customer_id
HAVING SUM(total_amount) >= 100000
ORDER BY total_spending DESC;
```

Không nên tự suy ra “alias đã có ở SELECT thì dùng ở mọi mệnh đề được”. Cần hiểu phạm vi và quy tắc của từng khối truy vấn.

### 6.2. Tránh dùng số thứ tự cột trong ORDER BY

PostgreSQL và một số hệ hỗ trợ:

```sql
SELECT customer_id, total_amount
FROM demo_orders
ORDER BY 2 DESC;
```

`2` là vị trí cột thứ hai của SELECT, tức `total_amount`. Nhưng nếu đổi vị trí hai cột đầu ra, câu ORDER BY vẫn hợp lệ và **âm thầm đổi nghĩa**. Trong SQL dùng lâu dài, `ORDER BY total_amount DESC` hoặc `ORDER BY order_total DESC` thường dễ bảo trì hơn.

## 7. Vì sao SELECT * dễ tạo phụ thuộc nguy hiểm?

`*` là cú pháp yêu cầu hệ quản trị mở rộng danh sách cột của các nguồn trong truy vấn. Nó không phải “chọn những cột chương trình cần”. Dưới đây là các dạng phụ thuộc cần nhận diện.

### 7.1. Schema thay đổi làm đầu ra tự thay đổi

Ban đầu:

```sql
SELECT *
FROM demo_customers;
```

Truy vấn trả sáu cột như định nghĩa bảng tạm. Nếu một phiên migration về sau thêm cột:

```sql
ALTER TABLE demo_customers
ADD COLUMN customer_tier TEXT;
```

Từ lần thực hiện tiếp theo trong cùng phiên, `SELECT * FROM demo_customers` trực tiếp có thể trả thêm `customer_tier`. Trong khi đó:

```sql
SELECT customer_id, full_name, created_at
FROM demo_customers;
```

vẫn trả đúng ba cột đã chỉ định. **Hợp đồng kết quả không bị mở rộng** chỉ vì bảng nguồn được thêm cột.

Lưu ý: câu này nói về SELECT trực tiếp. Các đối tượng như **view** có quy tắc ghi nhận cấu trúc kết quả khi tạo và thay đổi riêng theo DBMS; không nên khẳng định view chứa `SELECT *` sẽ luôn tự mở rộng khi bảng nền thêm cột.

### 7.2. Mã ánh xạ theo vị trí cột trở nên mong manh

Một ứng dụng hoặc quy trình xuất dữ liệu đôi khi đọc cột thứ 1, 2, 3 thay vì đọc theo tên:

```text
Kết quả mong đợi ban đầu:
1 = customer_id
2 = full_name
3 = created_at

Kết quả SELECT * thực tế:
1 = customer_id
2 = full_name
3 = email
4 = phone
5 = created_at
6 = internal_note
```

Nếu mã giả định cột thứ ba là `created_at`, `SELECT *` sẽ làm sai ngay cả khi schema chưa đổi. Khi cột mới được thêm, bản đồ vị trí có thể lại thay đổi theo thao tác/schema cụ thể. Danh sách SELECT rõ ràng cùng ánh xạ theo **tên cột** giảm rủi ro.

### 7.3. INSERT ... SELECT * có thể ghép sai thứ tự cột

Giả sử có hai bảng cùng số cột nhưng thứ tự khác:

```sql
CREATE TEMP TABLE demo_export_source (
    customer_id INTEGER,
    full_name TEXT,
    email TEXT
);

CREATE TEMP TABLE demo_export_target (
    customer_id INTEGER,
    email TEXT,
    full_name TEXT
);
```

Nếu viết:

```sql
-- Dễ gây lỗi logic: vị trí 2 và 3 của hai bảng không cùng nghĩa.
INSERT INTO demo_export_target
SELECT * FROM demo_export_source;
```

Số cột và kiểu dữ liệu có thể tương thích nên DBMS không nhất thiết báo lỗi, nhưng email và họ tên có thể bị chép vào **nhầm cột**. Hãy chỉ định rõ cả danh sách cột đích và cột nguồn:

```sql
INSERT INTO demo_export_target
    (customer_id, email, full_name)
SELECT
    customer_id,
    email,
    full_name
FROM demo_export_source;
```

Đây là một trong những trường hợp `SELECT *` gây lỗi dữ liệu thực tế nghiêm trọng: **câu SQL vẫn chạy nhưng kết quả sai**.

### 7.4. UNION và số cột phụ thuộc nguồn

```sql
-- Hai nhánh phải có số cột bằng nhau và kiểu tương thích.
SELECT customer_id, full_name
FROM demo_customers
UNION ALL
SELECT customer_id, full_name
FROM demo_customers;
```

Nếu hai nhánh sử dụng `SELECT *` từ các bảng khác nhau, việc thêm một cột vào một bảng có thể làm truy vấn UNION hỏng do số cột không khớp. Ngay cả khi vẫn bằng số cột, **đổi thứ tự hoặc ý nghĩa cột** có thể ghép sai dữ liệu. Viết danh sách cột tường minh và cùng thứ tự ở mọi nhánh giúp giữ hợp đồng của phép tập hợp.

### 7.5. Cột trùng tên khiến ứng dụng đọc sai

`SELECT *` từ hai bảng cùng có `id`, `status` hoặc `created_at` thường dẫn tới những nhãn trùng. Một thư viện ánh xạ từ ResultSet sang object/JSON theo tên có thể mất thông tin hoặc chọn một cột không như ý định. Vì vậy, cần đặt alias kiểu `customer_created_at`, `order_created_at`, `customer_id`, `order_id` rõ nguồn và rõ nghĩa.

## 8. SELECT * ảnh hưởng hiệu năng như thế nào?

Không phải mọi truy vấn `SELECT *` đều chậm. Với bảng nhỏ, dữ liệu ít cột hoặc tính năng thực sự cần toàn bộ hàng, khác biệt có thể không đáng kể. Nhưng **chi phí tăng theo độ rộng của dữ liệu thực sự phải đọc, xử lý, truyền và lưu ở phía tiêu thụ**.

### 8.1. Truyền nhiều dữ liệu hơn

Giả sử bảng có 100.000 hàng, màn hình chỉ cần `customer_id` và `full_name`, nhưng bảng còn có cột JSON chứa lịch sử chi tiết, mô tả dài hoặc ghi chú riêng. `SELECT *` có thể khiến driver, mạng, bộ nhớ tiến trình ứng dụng và bộ chuyển đổi JSON phải xử lý nhiều byte hơn cần thiết.

Công thức trực giác:

```text
Dữ liệu cần truyền ≈ số hàng × kích thước trung bình cột được trả
```

Đây chỉ là mô hình ước lượng. Kích thước thực còn chịu ảnh hưởng giao thức, NULL, mã hóa văn bản, nén, cách DBMS lưu trường lớn và cách driver đọc kết quả. Nhưng nguyên tắc **không lấy trường không sử dụng** vẫn có giá trị.

### 8.2. Có thể bỏ lỡ một kế hoạch chỉ đọc chỉ mục

Giả sử màn hình cần tìm khách bằng email và trả mã cùng tên:

```sql
SELECT customer_id, full_name
FROM demo_customers
WHERE email = 'an@example.test';
```

Trong PostgreSQL, với chỉ mục thích hợp, một truy vấn chỉ cần các cột hiện diện trong chỉ mục **có thể** được thực hiện bằng *index-only scan* khi điều kiện nhìn thấy phiên bản hàng (*visibility*) cho phép. Ví dụ một chỉ mục phủ có thể được cân nhắc theo mẫu truy cập:

```sql
CREATE INDEX idx_demo_customers_email_cover
ON demo_customers (email)
INCLUDE (customer_id, full_name);
```

Nếu lại dùng `SELECT *`, kết quả còn yêu cầu `phone`, `created_at`, `internal_note` và bất kỳ cột mới nào. Chỉ mục trên không bao phủ tất cả các cột ấy nên DBMS có thể phải truy cập bảng để lấy dữ liệu còn thiếu. Tuy nhiên, không phải cứ viết danh sách cột thì DBMS chắc chắn chọn index-only scan: kế hoạch còn tùy thống kê, kích thước bảng, mức chọn lọc, khả năng hiển thị tuple và chi phí dự kiến.

**Không tạo chỉ mục chỉ vì muốn loại SELECT * trên một bảng nhỏ.** Việc chọn chỉ mục phải dựa trên truy vấn thực tế, tải đọc/ghi và số đo.

### 8.3. Dữ liệu lớn và cột nhạy cảm

Cột có văn bản dài, dữ liệu nhị phân hoặc JSON lớn có thể làm tăng băng thông và bộ nhớ khi được chọn. Hơn nữa, một cột như `internal_note` có thể không phù hợp cho API công khai dù tài khoản database có quyền đọc nó.

Chọn cột tường minh thể hiện **nguyên tắc tối thiểu hóa dữ liệu** và giảm khả năng vô ý đưa trường nội bộ ra ngoài. Dù vậy, điều này **không thay thế** kiểm soát truy cập: cần phân quyền database phù hợp, kiểm tra ủy quyền của API và giới hạn việc tuần tự hóa dữ liệu nhạy cảm ở tầng ứng dụng.

### 8.4. Tối ưu cần đo, không dựa vào khẩu hiệu

Có thể quan sát kế hoạch với PostgreSQL:

```sql
EXPLAIN
SELECT customer_id, full_name
FROM demo_customers
WHERE email = 'an@example.test';
```

Trong môi trường phù hợp, `EXPLAIN (ANALYZE, BUFFERS)` sẽ **thực sự chạy truy vấn SELECT** và ghi nhận thời gian, số hàng, buffer được truy cập. Nên đo với dữ liệu có quy mô và phân bố đại diện. Trên bảng tạm vài dòng, việc PostgreSQL dùng Seq Scan thay vì index không chứng minh chỉ mục vô ích trên bảng thật có hàng triệu dòng.

Mục tiêu ở bước này là xác định **các cột thừa làm tốn tài nguyên ở đâu**, thay vì mặc định mọi truy vấn dùng `*` đều tệ như nhau.

## 9. Hợp đồng đầu ra cho API, JDBC và báo cáo

Một truy vấn dùng trong ứng dụng thường không tồn tại độc lập. Kết quả của nó được driver nhận, ánh xạ vào object/DTO, chuyển thành JSON hoặc đổ vào bảng báo cáo. Vì vậy, **tên, kiểu, thứ tự và ý nghĩa của các cột trả về** cần được xem là hợp đồng giữa SQL và mã sử dụng.

### 9.1. Thiết kế SELECT theo nhu cầu của DTO

Giả sử màn hình quản lý đơn hàng cần:

```text
OrderListItem
├── orderId
├── customerName
├── orderTotal
└── orderCreatedAt
```

Truy vấn có thể trả đúng bốn trường, theo tên cột có nghĩa:

```sql
SELECT
    o.order_id AS order_id,
    c.full_name AS customer_name,
    o.total_amount AS order_total,
    o.created_at AS order_created_at
FROM demo_orders AS o
JOIN demo_customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.created_at DESC, o.order_id DESC;
```

Kết quả không chứa `email`, `phone`, `internal_note` hoặc những cột khác không thuộc chức năng này. Tầng ứng dụng có thể ánh xạ `order_id` sang thuộc tính `orderId`, `customer_name` sang `customerName` theo quy ước.

### 9.2. Ví dụ đọc theo tên trong Java/JDBC

Đoạn ví dụ dùng SQL tường minh và `ResultSet` đọc bằng nhãn cột:

```java
String sql = """
    SELECT
        o.order_id AS order_id,
        c.full_name AS customer_name,
        o.total_amount AS order_total,
        o.created_at AS order_created_at
    FROM demo_orders AS o
    JOIN demo_customers AS c
        ON c.customer_id = o.customer_id
    WHERE o.status = ?
    ORDER BY o.created_at DESC, o.order_id DESC
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            String customerName = rs.getString("customer_name");
            BigDecimal orderTotal = rs.getBigDecimal("order_total");
            OffsetDateTime createdAt =
                    rs.getObject("order_created_at", OffsetDateTime.class);

            // Dùng các giá trị đã đọc để xây dựng DTO của ứng dụng.
        }
    }
}
```

Ví dụ giả định đã có `Connection connection` và import các lớp JDBC, `BigDecimal`, `OffsetDateTime` cần thiết. Việc driver cụ thể hỗ trợ ánh xạ `TIMESTAMPTZ` sang `OffsetDateTime` cần được đối chiếu theo driver/phiên bản đang dùng; đây là cách đọc minh họa, không phải một chương trình độc lập.

Ưu điểm của `rs.getLong("order_id")` so với `rs.getLong(1)` là mã **không phụ thuộc vị trí cột** trong danh sách SELECT. Tuy vậy, nếu đổi alias hoặc trả nhiều cột cùng nhãn, mã đọc theo tên vẫn có thể sai. Vì thế, tránh đổi tên bí danh đầu ra tùy tiện khi đang có người tiêu thụ kết quả.

**Dùng placeholder `?` cho giá trị lọc** giúp binding tham số an toàn; không ghép dữ liệu người dùng trực tiếp vào chuỗi SQL. Các tên cột động trong SELECT/ORDER BY không thể thay thế bằng placeholder giá trị theo cùng cách; nếu ứng dụng cho phép chọn cột hoặc kiểu sắp xếp, cần ánh xạ qua danh sách identifier được phép.

### 9.3. SELECT * dễ làm rò rỉ hợp đồng nội bộ

Nếu một API dùng `SELECT *` rồi tự động tuần tự hóa entity ra JSON, thêm cột `internal_note` vào database có thể gây lộ dữ liệu ngoài ý muốn nếu các tầng mapping không bảo vệ. Một tầng DTO xác định rõ những trường API được phép công bố giúp giảm rủi ro này. Tuy nhiên, **bảo mật phải được kiểm soát độc lập với cách viết SELECT**; người dùng không có quyền không được truy cập nội dung chỉ bằng cách đổi query hoặc gọi API khác.

## 10. Chọn cột trong các truy vấn tổng hợp

Danh sách SELECT còn quyết định mức độ chi tiết của báo cáo. Với doanh thu đơn hàng đã thanh toán:

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_total
FROM demo_orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả có mỗi khách xuất hiện trong nhóm thanh toán một hàng. Không thể thêm tùy ý `order_id` vào SELECT mà không tổng hợp hoặc đưa nó vào GROUP BY (trừ những trường hợp DBMS nhận ra phụ thuộc hàm hợp lệ), bởi mỗi nhóm khách có thể gồm nhiều order_id:

```sql
-- Không hợp lệ theo cách tổng hợp thông thường:
SELECT customer_id, order_id, SUM(total_amount)
FROM demo_orders
GROUP BY customer_id;
```

Chọn cột vì thế còn liên quan đến **độ hạt của kết quả**: mỗi hàng đại diện cho một đơn, một khách hay một nhóm thống kê? Việc chọn thêm cột có thể buộc thay đổi GROUP BY và làm báo cáo có nhiều hàng hơn dự kiến.

### 10.1. Giữ khách chưa có đơn bằng LEFT JOIN

```sql
SELECT
    c.customer_id,
    c.full_name AS customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_order_amount
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Với mẫu này, Chi xuất hiện dù chưa có đơn. `COUNT(o.order_id)` bằng 0 cho Chi, còn `COUNT(*)` sẽ đếm cả hàng bù NULL của LEFT JOIN nên có thể cho 1. `COALESCE(SUM(...), 0)` biểu diễn tổng bằng 0 khi không có đơn; đây là quy tắc phù hợp với ví dụ báo cáo tổng giá trị đơn, nhưng không nên thay NULL bằng 0 ở mọi bài toán.

Đặt bí danh `order_count`, `total_order_amount` nêu rõ loại số liệu, giúp tránh nhầm hai cột tổng hợp với cùng tên `count` hoặc `sum`.

### 10.2. Chọn cột đầu ra trong CTE và subquery

```sql
WITH paid_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount
    FROM demo_orders
    WHERE status = 'PAID'
)
SELECT
    customer_id,
    SUM(total_amount) AS paid_total
FROM paid_orders
GROUP BY customer_id;
```

CTE chỉ mang ba cột thực sự cần cho xử lý tiếp. Nếu viết `SELECT *` ở cả CTE và truy vấn ngoài, sự phụ thuộc vào schema nguồn sẽ lan qua nhiều tầng. Với những pipeline có nhiều CTE hoặc view, **đặt tên cột rõ ràng tại mỗi ranh giới** giúp theo dõi luồng dữ liệu và thay đổi cấu trúc an toàn.

## 11. Khi nào SELECT * vẫn hợp lý?

`SELECT *` không phải cú pháp sai. Giá trị của nó nằm ở tình huống sử dụng:

| Tình huống | Đánh giá |
| --- | --- |
| Khám phá nhanh một bảng trong môi trường phát triển | Có thể dùng `SELECT * ... LIMIT ...` để biết dữ liệu đang có; chú ý quyền và dữ liệu nhạy cảm |
| Câu truy vấn ứng dụng trả DTO/API cố định | Ưu tiên danh sách cột tường minh để giữ hợp đồng |
| JOIN nhiều bảng có tên cột trùng | Nên chọn và đặt alias từng cột |
| Xuất/nhập giữa bảng hoặc hệ thống khác nhau | Nên liệt kê cột đích và nguồn để tránh lệch thứ tự |
| Báo cáo nhiều tầng GROUP BY/CTE/view | Nên nêu rõ cột và biểu thức đầu ra |
| Công cụ kiểm tra nội bộ thực sự cần toàn bộ hàng | Có thể dùng `*` có chủ đích, với giới hạn dữ liệu và quyền phù hợp |
| `COUNT(*)` | **Nên dùng khi muốn đếm hàng**; dấu `*` ở đây không có nghĩa lấy mọi cột về ứng dụng |
| `EXISTS (SELECT 1 ...)` | `SELECT 1` thường diễn đạt ý định kiểm tra tồn tại; trong nhiều DBMS, danh sách SELECT bên trong EXISTS không quyết định dữ liệu cần trả ra |

Hai trường hợp `COUNT(*)` và `SELECT *` khác nhau:

```sql
-- Trả một giá trị đếm số hàng.
SELECT COUNT(*)
FROM demo_orders;

-- Trả toàn bộ cột của từng hàng.
SELECT *
FROM demo_orders;
```

`COUNT(*)` không buộc database gửi tất cả các giá trị cột của mọi hàng cho client. `EXISTS` cũng kiểm tra có hàng thỏa điều kiện và không xuất những cột của truy vấn con ra ngoài:

```sql
SELECT
    c.customer_id,
    c.full_name
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Ở ví dụ này, `SELECT 1` làm rõ rằng truy vấn con chỉ phục vụ kiểm tra sự tồn tại của đơn, không cần bất kỳ cột nào của `demo_orders` làm đầu ra. PostgreSQL thường không quan tâm giá trị biểu thức trong target list của EXISTS, nhưng với các biểu thức đặc thù như set-returning function có thể có ngoại lệ; `SELECT 1` là cách viết đơn giản, dễ đọc.

## 12. Quy trình viết SELECT rõ ràng cho chức năng mới

Khi xây dựng một chức năng đọc dữ liệu, có thể làm theo quy trình sau:

1. **Xác định đơn vị của một hàng kết quả:** một khách hàng, một đơn hàng, một dòng đơn hàng hay một nhóm tổng hợp?
2. **Liệt kê trường mà phía sử dụng thật sự cần:** tên, mã, thời gian, số lượng, trạng thái; xác định trường nào bị hạn chế quyền.
3. **Chọn bảng nguồn và quan hệ JOIN:** xem cột cùng tên nằm ở bảng nào; dùng alias bảng rõ ràng.
4. **Viết SELECT tường minh:** chọn từng cột hoặc biểu thức, nêu rõ tiền tố khi cần và đặt alias mang nghĩa ổn định.
5. **Đặt WHERE, GROUP BY, HAVING phù hợp:** bảo đảm tính đúng của dòng và nhóm; không thêm cột tùy tiện khiến mức độ tổng hợp thay đổi.
6. **Quy định ORDER BY và giới hạn kết quả nếu cần:** thứ tự hàng khác thứ tự cột; phân trang cần khóa phụ ổn định.
7. **Ánh xạ kết quả bằng tên và kiểu dự kiến:** tầng JDBC/ORM/API dùng DTO với hợp đồng cột rõ ràng, không dựa vào thứ tự ngầm.
8. **Khi dữ liệu lớn, đo tài nguyên:** xem số cột/hàng trả, kích thước dữ liệu, kế hoạch thực thi và chi phí truyền tải.

### Mẫu truy vấn tham khảo

```sql
SELECT
    o.order_id AS order_id,
    c.full_name AS customer_name,
    o.status AS order_status,
    o.total_amount AS order_total,
    o.created_at AS order_created_at
FROM demo_orders AS o
JOIN demo_customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
```

Truy vấn này nêu rõ **5 cột kết quả**, nguồn từng cột, điều kiện lọc và thứ tự trả hàng. Nếu bảng khách được thêm `customer_tier`, hoặc bảng đơn được thêm `internal_review_note`, truy vấn không tự đưa chúng ra ngoài.

## 13. Những lỗi và hiểu nhầm phổ biến

| Cách viết hoặc suy nghĩ | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “`SELECT *` luôn nhanh hơn vì gõ ít chữ” | Số chữ SQL không quyết định lượng dữ liệu và kế hoạch | Chọn cột thật sự cần; đo khi tối ưu |
| “`SELECT *` luôn chậm” | Bảng nhỏ hoặc trường hợp cần cả hàng có thể không khác biệt đáng kể | Đánh giá theo khối lượng và mục đích |
| “Có alias `AS x` là đổi tên cột trong bảng” | Alias chỉ là tên kết quả tại phạm vi truy vấn | Dùng ALTER TABLE khi thật sự muốn đổi schema |
| `SELECT created_at` sau JOIN hai bảng cùng có cột đó | Tên cột không rõ nguồn, có thể gây lỗi ambiguous | Dùng `c.created_at` hoặc `o.created_at` |
| `SELECT c.*, o.*` cho DTO có tên trường cố định | Nhiều cột trùng tên, thêm cột ngoài dự kiến | Liệt kê cột và đặt alias duy nhất |
| Dùng alias SELECT trong WHERE cùng mức | Alias chưa thuộc nguồn của WHERE | Lặp biểu thức hoặc dùng subquery/CTE |
| Sử dụng `ORDER BY 2` lâu dài | Đổi thứ tự cột SELECT làm đổi cột sắp xếp | Dùng tên cột hoặc alias |
| `INSERT target SELECT * FROM source` khi cấu trúc “gần giống” | Ghép cột theo thứ tự, có thể đảo nghĩa mà vẫn chạy | Nêu rõ danh sách cột đích và nguồn |
| Dùng `COUNT(*)` như `SELECT *` | Hai cấu trúc có tác dụng khác nhau | COUNT(*) dùng để đếm hàng |
| Lấy mọi cột rồi tin rằng API chỉ hiện vài cột là đủ bảo mật | Dữ liệu vẫn có thể xuất hiện ở log/serialization hoặc bộ nhớ | Chọn cột tối thiểu và áp dụng phân quyền đúng |
| Chỉ dựa vào cột `id` của kết quả JOIN | Có thể không biết `id` thuộc bảng nào | Đặt `customer_id`, `order_id` rõ nghĩa |
| Thêm DISTINCT để khử lặp do JOIN | Có thể che lỗi độ hạt hoặc điều kiện JOIN | Kiểm tra quan hệ và mục tiêu dữ liệu |

## 14. Bài tập thực hành

Các bài tập sử dụng hai bảng `demo_customers` và `demo_orders` trong phần 2.

### Bài 1 — Chọn đúng cột

Màn hình quản lý khách hàng yêu cầu: mã khách, họ tên và ngày tạo; không dùng email, số điện thoại hoặc ghi chú nội bộ. Hãy viết SELECT chỉ trả đúng ba cột, dùng `ORDER BY customer_id`. Giải thích vì sao `SELECT *` không thể hiện chính xác hợp đồng này.

Gợi ý:

```sql
SELECT customer_id, full_name, created_at
FROM demo_customers
ORDER BY customer_id;
```

### Bài 2 — Đặt alias cho biểu thức

Viết SELECT trả `order_id`, `total_amount` và một cột `estimated_amount_with_fee` bằng `total_amount * 1.05`. Hãy giải thích alias có làm thay đổi dữ liệu trong bảng hay không, và vì sao tên diễn giải phù hợp hơn tên biểu thức tự sinh.

### Bài 3 — Phân biệt hai cột trùng tên sau JOIN

JOIN `demo_customers` với `demo_orders` và trả đúng: `customer_id`, `customer_name`, `order_id`, `customer_created_at`, `order_created_at`. Cần đặt alias nào để cả hai thời điểm đều rõ nguồn? Nếu thay SELECT bằng `SELECT *`, kết quả có thêm cột gì và cột nào có thể trùng nhãn?

### Bài 4 — Alias trong WHERE

Dự đoán vì sao câu sau không hợp lệ trong PostgreSQL:

```sql
SELECT total_amount * 1.10 AS estimated_total
FROM demo_orders
WHERE estimated_total >= 100000;
```

Viết lại một phiên bản bằng cách lặp biểu thức và một phiên bản với CTE để WHERE ở SELECT ngoài tham chiếu được alias.

### Bài 5 — Thay đổi schema

Giả sử một migration thêm `loyalty_rank INTEGER` vào bảng khách, và sau đó thêm cột nội bộ `risk_comment TEXT`. Hãy so sánh đầu ra của:

```sql
SELECT *
FROM demo_customers;

SELECT customer_id, full_name
FROM demo_customers;
```

Trong trường hợp nào API nhận thêm cột không yêu cầu? Những kiểm soát dữ liệu nào khác ngoài danh sách SELECT vẫn cần thực hiện?

### Bài 6 — Tính tổng đúng độ hạt

Viết truy vấn hiển thị mỗi khách đúng một hàng với `customer_id`, `customer_name`, `order_count`, `total_amount`. Giữ cả khách chưa có đơn. Tại sao nên dùng `COUNT(o.order_id)` thay vì `COUNT(*)` trong LEFT JOIN? Việc thêm `o.order_id` trực tiếp vào SELECT sẽ thay đổi ý nghĩa của GROUP BY ra sao?

### Bài 7 — Dữ liệu nhập và xuất theo thứ tự

Cho bảng nguồn có thứ tự `(customer_id, full_name, email)` và bảng đích có thứ tự `(customer_id, email, full_name)`, cùng kiểu văn bản cho hai cột sau. Tại sao `INSERT INTO target SELECT * FROM source` nguy hiểm? Viết lại bằng danh sách cột tường minh ở cả hai phía.

### Bài 8 — Dấu sao không phải lúc nào cũng cần tránh

Phân biệt ý nghĩa của ba lệnh sau:

```sql
SELECT * FROM demo_orders;

SELECT COUNT(*) FROM demo_orders;

SELECT c.customer_id
FROM demo_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM demo_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Lệnh nào trả mọi cột của mọi đơn? Lệnh nào chỉ trả số hàng? Lệnh nào chỉ trả mã khách có ít nhất một đơn? Vì sao việc hạn chế `SELECT *` trong mã ứng dụng không có nghĩa phải tránh `COUNT(*)`?

## 15. Tổng kết kiến thức cốt lõi

Có thể hình dung một câu SELECT phục vụ ứng dụng như bản mô tả **hợp đồng dữ liệu đầu ra**:

```text
Nhu cầu nghiệp vụ / DTO
        ↓
Chọn đúng nguồn và điều kiện JOIN
        ↓
SELECT c.column, o.column, expression AS meaningful_alias
        ↓
Lọc, nhóm, sắp xếp và phân trang đúng nghĩa
        ↓
ResultSet / DTO / báo cáo nhận đúng những cột đã quy định
```

`SELECT *` lấy các cột theo cấu trúc nguồn hiện có, nên dễ phụ thuộc vào sự thay đổi schema, kéo theo cột không cần thiết và tên cột trùng khi JOIN. **Danh sách cột tường minh** cùng **bí danh rõ nghĩa** giúp người đọc xác định đầu ra ngay từ câu SQL, giữ giao diện giữa database và ứng dụng ổn định hơn, đồng thời tạo cơ hội giảm dữ liệu truyền tải.

Không cần tránh dấu sao một cách máy móc: `COUNT(*)` là cách tự nhiên để đếm hàng, còn `SELECT *` có thể hữu ích khi khám phá dữ liệu. Trong truy vấn dùng lâu dài cho chức năng cụ thể, hãy **chọn những trường thực sự cần, đặt tên đầu ra ổn định và không dựa vào thứ tự hay cột ngầm định**.
