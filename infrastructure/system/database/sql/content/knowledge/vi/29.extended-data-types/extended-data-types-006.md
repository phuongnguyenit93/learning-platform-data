# Tạo đối tượng, mảng JSON và tổng hợp dữ liệu quan hệ

## 1. Từ nhiều hàng quan hệ đến một tài liệu JSON

Trong cơ sở dữ liệu quan hệ, một đơn hàng thường được lưu ở nhiều bảng:

- `customers` chứa thông tin khách hàng.
- `orders` chứa các đơn, mỗi đơn tham chiếu một khách hàng.
- `order_items` chứa những dòng sản phẩm thuộc một đơn.
- `products` chứa tên và thông tin sản phẩm.
- `payments` chứa các lần thanh toán, một đơn có thể có nhiều lần.

Khi gửi dữ liệu cho ứng dụng web/mobile hoặc cho một hệ thống khác, ta thường cần **một đối tượng JSON lồng các mảng** thay vì bốn tập hàng riêng biệt.

Ví dụ một đơn hàng:

~~~json
{
  "orderId": 1001,
  "status": "PAID",
  "customer": {
    "customerId": 1,
    "name": "An"
  },
  "items": [
    {
      "lineNo": 1,
      "sku": "NOTE-01",
      "productName": "Sổ tay",
      "quantity": 2,
      "unitPrice": 50.00
    },
    {
      "lineNo": 2,
      "sku": "PEN-02",
      "productName": "Bút bi",
      "quantity": 3,
      "unitPrice": 10.00
    }
  ],
  "subtotal": 130.00,
  "payments": [
    {"paymentId": 501, "method": "CARD", "amount": 100.00},
    {"paymentId": 502, "method": "CASH", "amount": 30.00}
  ]
}
~~~

Tập dữ liệu trong JSON có **cấu trúc khác** kết quả của một phép JOIN thông thường:

~~~text
Quan hệ:
customers ──1:N── orders ──1:N── order_items ──N:1── products
                       │
                       └──────1:N── payments

JSON:
{
  "orderId": ...,
  "customer": { ... },
  "items": [ { ... }, { ... } ],
  "payments": [ { ... }, { ... } ]
}
~~~

Bài học này tập trung vào ba kỹ năng:

1. **Tạo đối tượng JSON** từ các cột SQL, ví dụ `jsonb_build_object(...)`.
2. **Tạo mảng JSON** từ nhiều hàng, ví dụ `jsonb_agg(...)`.
3. **Tổng hợp quan hệ đúng cấp**: một hàng cha thành một object, các hàng con thành array, nhiều nhánh con được tổng hợp riêng để không nhân bản.

Các ví dụ chính dùng **PostgreSQL** và kiểu `jsonb`. Phần sau đối chiếu MySQL, SQL Server, SQLite, Oracle và SQL/JSON. Cú pháp cũng như quy tắc NULL, thứ tự và kiểu dữ liệu thay đổi giữa các hệ.

## 2. JSON là kiểu cấu trúc gì?

Một tài liệu JSON có sáu loại giá trị cơ bản:

| Loại JSON | Ví dụ | Ý nghĩa trong truy vấn |
| --- | --- | --- |
| Object | `{"id": 1, "name": "An"}` | Tập thuộc tính key–value của một thực thể |
| Array | `[{"id": 1}, {"id": 2}]` | Danh sách phần tử có thứ tự |
| String | `"Đang xử lý"` | Chuỗi văn bản Unicode |
| Number | `12.5` | Giá trị số theo cú pháp JSON |
| Boolean | `true` | Giá trị đúng/sai |
| null | `null` | Giá trị JSON null |

Một JSON document có thể là object, array hoặc giá trị scalar. Nhưng khi thiết kế API, object thường là dạng gốc vì dễ mở rộng trường và đặt tên hợp đồng.

### 2.1. Hàng SQL không phải tự nhiên là JSON object

Kết quả:

~~~sql
SELECT order_id, order_status
FROM orders
WHERE order_id = 1001;
~~~

có hai cột trong một hàng SQL. Nó không tự động tương đương chuỗi JSON:

~~~json
{"orderId": 1001, "status": "PAID"}
~~~

Để dựng JSON trong database, ta cần **hàm xây dựng** với các khóa và giá trị rõ ràng. Cách đặt tên trong SQL là `order_id` còn hợp đồng API có thể dùng `orderId`; hàm tạo object cho phép ánh xạ hai kiểu tên này.

### 2.2. PostgreSQL json và jsonb

PostgreSQL có hai kiểu dữ liệu chính:

| Tiêu chí | `json` | `jsonb` |
| --- | --- | --- |
| Cách lưu | Biểu diễn văn bản JSON đã kiểm tra cú pháp | Biểu diễn nhị phân đã phân tích |
| Khoảng trắng và định dạng văn bản | Giữ dạng đầu vào tốt hơn | Không giữ nguyên cách trình bày |
| Thứ tự khóa object | Giữ thứ tự khóa trong văn bản đầu vào | Không bảo đảm thứ tự khóa object |
| Khóa trùng trong object | Có thể giữ nội dung văn bản có khóa lặp | Không giữ nhiều bản cùng khóa; một giá trị được giữ |
| Toán tử/indexing | Có nhưng hạn chế hơn | Nhiều toán tử và khả năng index hơn |
| Thao tác tổng hợp/thay đổi JSON | Có các hàm `json_*` | Có các hàm `jsonb_*` và toán tử tiện lợi |

Ví dụ:

~~~sql
SELECT
    json_build_object('id', 1, 'active', TRUE) AS as_json,
    jsonb_build_object('id', 1, 'active', TRUE) AS as_jsonb;
~~~

Ở bài này, `jsonb` được chọn vì các truy vấn dựng, kết hợp và kiểm tra tài liệu dễ thống nhất kiểu. **Không suy rằng `jsonb` luôn phù hợp hơn `json` cho mọi trường hợp**: nếu cần giữ chính xác văn bản gốc, cách format hoặc chữ ký dữ liệu, yêu cầu lưu trữ sẽ khác.

### 2.3. Mảng JSON không phải bảng quan hệ

Một mảng như:

~~~json
[
  {"lineNo": 1, "sku": "NOTE-01"},
  {"lineNo": 2, "sku": "PEN-02"}
]
~~~

là một giá trị JSON duy nhất. Nó không có khóa ngoại, unique constraint hay index quan hệ cho từng phần tử giống `order_items` theo mặc định.

Vì vậy kiến trúc phổ biến là **giữ dữ liệu cần đảm bảo toàn vẹn trong các bảng quan hệ**, rồi **tạo JSON khi cần xuất dữ liệu**. Chỉ vì API cần JSON không có nghĩa phải thay mọi bảng quan hệ bằng một cột `jsonb`.

## 3. Bộ dữ liệu mẫu có đủ quan hệ một-nhiều

Các câu lệnh từ đây đến mục 16 là **PostgreSQL**. Dùng database thực hành riêng để tránh thay đổi dữ liệu đang phục vụ ứng dụng.

### 3.1. Bảng khách hàng

~~~sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    city TEXT
);

INSERT INTO customers (customer_id, full_name, city)
VALUES
    (1, 'An',   'Hà Nội'),
    (2, 'Bình', 'TP.HCM'),
    (3, 'Chi',  'Đà Nẵng'),
    (4, 'Dũng', NULL);
~~~

### 3.2. Bảng sản phẩm

~~~sql
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL
        CHECK (list_price >= 0)
);

INSERT INTO products (
    product_id, sku, product_name, list_price
)
VALUES
    (10, 'NOTE-01', 'Sổ tay', 50.00),
    (20, 'PEN-02',  'Bút bi', 10.00),
    (30, 'BAG-03',  'Túi đeo', 200.00);
~~~

### 3.3. Bảng đơn hàng

~~~sql
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL
        CHECK (
            order_status IN (
                'NEW', 'PENDING', 'PAID', 'CANCELLED'
            )
        )
);

INSERT INTO orders (
    order_id, customer_id, ordered_at, order_status
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-10-01 09:00:00+07', 'PAID'),
    (1002, 1, TIMESTAMPTZ '2026-10-03 10:00:00+07', 'PENDING'),
    (1003, 2, TIMESTAMPTZ '2026-10-04 11:00:00+07', 'PAID'),
    (1004, 3, TIMESTAMPTZ '2026-10-05 12:00:00+07', 'CANCELLED'),
    (1005, 2, TIMESTAMPTZ '2026-10-06 13:00:00+07', 'PAID');
~~~

Khách `Dũng` chưa có đơn hàng. Điều này giúp minh họa cách tạo **mảng rỗng `[]`** cho một quan hệ không có hàng con.

### 3.4. Dòng hàng trong đơn

~~~sql
CREATE TABLE order_items (
    order_id INTEGER NOT NULL
        REFERENCES orders(order_id),
    line_no INTEGER NOT NULL
        CHECK (line_no > 0),
    product_id INTEGER NOT NULL
        REFERENCES products(product_id),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

INSERT INTO order_items (
    order_id, line_no, product_id, quantity, unit_price
)
VALUES
    (1001, 1, 10, 2,  50.00),
    (1001, 2, 20, 3,  10.00),
    (1002, 1, 30, 1, 200.00),
    (1003, 1, 20, 4,  10.00),
    (1003, 2, 30, 1, 180.00),
    (1005, 1, 10, 1,  50.00);
~~~

Chúng ta cố tình để đơn `1004` không có dòng hàng. Trong nghiệp vụ thật, đơn bị hủy có thể vẫn có dòng lịch sử; ở đây đây là dữ liệu mô phỏng để thấy cách xử lý một tập con rỗng.

Tổng tiền tính từ dòng hàng:

| order_id | Các phép tính | Subtotal |
| ---: | --- | ---: |
| 1001 | 2 × 50 + 3 × 10 | 130.00 |
| 1002 | 1 × 200 | 200.00 |
| 1003 | 4 × 10 + 1 × 180 | 220.00 |
| 1004 | Không có dòng | 0.00 |
| 1005 | 1 × 50 | 50.00 |

`unit_price` trong `order_items` là **đơn giá tại thời điểm bán**, có thể khác `products.list_price` hiện tại. Ví dụ đơn 1003 bán túi giá 180 dù giá niêm yết là 200.

### 3.5. Các lần thanh toán

~~~sql
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES orders(order_id),
    payment_method TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    payment_status TEXT NOT NULL
        CHECK (
            payment_status IN (
                'CAPTURED', 'FAILED', 'PENDING'
            )
        )
);

INSERT INTO payments (
    payment_id, order_id,
    payment_method, amount, payment_status
)
VALUES
    (501, 1001, 'CARD',     100.00, 'CAPTURED'),
    (502, 1001, 'CASH',      30.00, 'CAPTURED'),
    (503, 1003, 'TRANSFER', 220.00, 'CAPTURED'),
    (504, 1005, 'CASH',      50.00, 'CAPTURED');
~~~

Đơn `1001` có **2 dòng hàng** và **2 dòng thanh toán**. Đây là tình huống quan trọng để thấy JOIN hai quan hệ một-nhiều gây **nhân số hàng** nếu tổng hợp JSON không đúng cấp.

### 3.6. Bản đồ quan hệ

~~~text
customers (1) ────< orders (N)
                       |
                       +────< order_items (N) >──── products (1)
                       |
                       +────< payments (N)

Khách 1 / An
  ├── Đơn 1001: 2 items, 2 payments
  └── Đơn 1002: 1 item, 0 payments

Khách 2 / Bình
  ├── Đơn 1003: 2 items, 1 payment
  └── Đơn 1005: 1 item, 1 payment

Khách 3 / Chi
  └── Đơn 1004: 0 items, 0 payments

Khách 4 / Dũng
  └── Không có đơn
~~~

Đầu ra JSON phải tôn trọng chính xác những lực lượng quan hệ này, không nhân bản dòng hàng hoặc biến một quan hệ rỗng thành mảng có một object toàn `null`.

## 4. Tạo một JSON object với jsonb_build_object

### 4.1. Cú pháp cơ bản

PostgreSQL:

~~~sql
SELECT jsonb_build_object(
    'orderId', 1001,
    'status', 'PAID',
    'paid', TRUE,
    'amount', 130.00
) AS payload;
~~~

Giá trị JSON:

~~~json
{
  "orderId": 1001,
  "status": "PAID",
  "paid": true,
  "amount": 130.00
}
~~~

Cú pháp nhận các cặp **key, value** nối tiếp nhau:

~~~text
jsonb_build_object(
    key_1, value_1,
    key_2, value_2,
    ...
)
~~~

Trong PostgreSQL, số lượng đối số phải tạo được các cặp; gọi với số đối số lẻ không tạo thành cặp khóa–giá trị hợp lệ. Tên key được chuyển thành chuỗi JSON theo quy tắc hàm. Giá trị SQL được chuyển thành loại giá trị JSON thích hợp.

### 4.2. Tạo object từ cột bảng

~~~sql
SELECT
    c.customer_id,
    jsonb_build_object(
        'customerId', c.customer_id,
        'name', c.full_name,
        'city', c.city
    ) AS customer_json
FROM customers AS c
WHERE c.customer_id = 1;
~~~

Kết quả JSON:

~~~json
{
  "customerId": 1,
  "name": "An",
  "city": "Hà Nội"
}
~~~

`customer_id` ngoài cùng vẫn là cột SQL; `customer_json` là **một giá trị jsonb**. Cách này hữu ích khi ứng dụng muốn nhận danh sách các hàng SQL mà mỗi hàng có một payload JSON riêng.

### 4.3. Lồng object bên trong object

~~~sql
SELECT jsonb_build_object(
    'orderId', o.order_id,
    'status', o.order_status,
    'customer', jsonb_build_object(
        'customerId', c.customer_id,
        'name', c.full_name
    )
) AS order_json
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

Kết quả:

~~~json
{
  "orderId": 1001,
  "status": "PAID",
  "customer": {
    "customerId": 1,
    "name": "An"
  }
}
~~~

Đây là **object nằm trong object** chứ không phải chuỗi chứa dấu ngoặc. Do `jsonb_build_object` bên trong trả `jsonb`, hàm ngoài giữ đúng cấu trúc JSON lồng.

### 4.4. Không tự ghép chuỗi để tạo JSON

Mẫu không an toàn:

~~~sql
-- KHÔNG NÊN:
SELECT
    '{"name":"' || full_name || '"}' AS document
FROM customers;
~~~

Nếu tên chứa dấu `"`, dấu `\` hoặc ký tự điều khiển, chuỗi tự ghép có thể thành JSON sai hoặc làm thay đổi ý nghĩa dữ liệu. Ví dụ tên người `A "Sách"` cần escaping chính xác.

Dùng:

~~~sql
SELECT jsonb_build_object(
    'name', full_name
) AS document
FROM customers;
~~~

Hàm JSON builder chịu trách nhiệm escaping theo kiểu dữ liệu. Điều này **không thay việc dùng tham số SQL** trong ứng dụng: các giá trị người dùng đưa vào câu SQL vẫn phải được bind an toàn, tránh SQL injection.

### 4.5. Đặt key rõ ràng, không nhầm tên cột và giá trị

Hai câu sau không giống nhau:

~~~sql
-- Key cố định tên "customerId".
SELECT jsonb_build_object(
    'customerId', customer_id
)
FROM customers;
~~~

~~~sql
-- Key được lấy từ GIÁ TRỊ của cột full_name.
SELECT jsonb_build_object(
    full_name, customer_id
)
FROM customers;
~~~

Nếu mục tiêu là API có key `customerId`, hãy dùng literal cho tên key. Key động theo dữ liệu chỉ phù hợp khi thật sự muốn xây một object kiểu bản đồ, như `{"NOTE-01": 2, "PEN-02": 3}`.

## 5. Kiểu số, chuỗi, boolean và NULL khi dựng object

### 5.1. Giữ số thành JSON number

~~~sql
SELECT jsonb_build_object(
    'quantity', 2,
    'unitPrice', 50.00::NUMERIC,
    'active', TRUE,
    'sku', 'NOTE-01'
) AS payload;
~~~

Kết quả có các loại:

~~~json
{
  "quantity": 2,
  "unitPrice": 50.00,
  "active": true,
  "sku": "NOTE-01"
}
~~~

Không cần ép mọi số thành `TEXT`:

~~~sql
-- Dễ gây sai hợp đồng vì unitPrice trở thành JSON string.
SELECT jsonb_build_object(
    'unitPrice', 50.00::TEXT
);
~~~

Kết quả sẽ chứa `"unitPrice": "50.00"`, không phải một JSON number. Khi thiết kế API, số tiền thường cần **hợp đồng riêng về độ chính xác**: số JSON được nhiều client JavaScript đọc bằng kiểu Number, có thể không đại diện chính xác mọi số thập phân hoặc số nguyên lớn.

Nếu cần tránh sai số ở client, có thể dùng chuỗi thập phân có format xác định hoặc integer minor units theo hợp đồng API. Đó là **quyết định giao diện**, không phải lý do database luôn phải ép số thành chuỗi.

### 5.2. SQL NULL trở thành JSON null trong object builder

~~~sql
SELECT jsonb_build_object(
    'customerId', customer_id,
    'city', city
) AS document
FROM customers
WHERE customer_id = 4;
~~~

Khách Dũng có `city IS NULL`, nên object tương ứng chứa:

~~~json
{"customerId": 4, "city": null}
~~~

**JSON null khác việc key không xuất hiện.** Hai document sau không tương đương về hợp đồng API:

~~~json
{"customerId": 4, "city": null}
~~~

~~~json
{"customerId": 4}
~~~

Cái thứ nhất nói rõ key `city` có giá trị null; cái thứ hai không có key `city`.

### 5.3. Bỏ key có null khi thực sự muốn

PostgreSQL:

~~~sql
SELECT jsonb_strip_nulls(
    jsonb_build_object(
        'customerId', customer_id,
        'name', full_name,
        'city', city
    )
) AS document
FROM customers
WHERE customer_id = 4;
~~~

Kết quả:

~~~json
{"customerId": 4, "name": "Dũng"}
~~~

`jsonb_strip_nulls` loại những thuộc tính object có giá trị JSON null theo quy tắc của hàm; không tự biến một **mảng rỗng** thành key vắng mặt.

Cần chọn chính sách rõ ràng:

- **Trả key với null** nếu client cần phân biệt “đã biết thuộc tính nhưng giá trị rỗng”.
- **Bỏ key** nếu API quy định thuộc tính là tùy chọn và không trả khi chưa có dữ liệu.
- **Trả []** cho tập con rỗng nếu API quy định danh sách luôn tồn tại.

### 5.4. SQL NULL và chuỗi "null" khác nhau

~~~sql
SELECT jsonb_build_object(
    'sqlNull', NULL,
    'textNull', 'null',
    'emptyText', ''
);
~~~

Kết quả có ba giá trị khác loại:

~~~json
{
  "sqlNull": null,
  "textNull": "null",
  "emptyText": ""
}
~~~

Không tạo string `"null"` để thay cho JSON null. Khi trả JSON cho client, cần giữ phân biệt giữa không có giá trị, chuỗi rỗng, số 0 và array rỗng.

## 6. Tạo JSON array từ các giá trị cố định

### 6.1. jsonb_build_array

~~~sql
SELECT jsonb_build_array(
    'PAID', 'PENDING', 'CANCELLED'
) AS statuses;
~~~

Kết quả:

~~~json
["PAID", "PENDING", "CANCELLED"]
~~~

Có thể lồng object:

~~~sql
SELECT jsonb_build_array(
    jsonb_build_object('id', 1, 'name', 'An'),
    jsonb_build_object('id', 2, 'name', 'Bình')
) AS customers;
~~~

Kết quả:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"}
]
~~~

`jsonb_build_array` phù hợp khi biết danh sách phần tử ở thời điểm viết câu SQL. Nhưng khi dữ liệu đến từ **nhiều hàng truy vấn**, cần một hàm aggregate như `jsonb_agg`.

### 6.2. Object không bảo đảm thứ tự key; array giữ thứ tự phần tử

JSON object về mặt mô hình là tập thành viên theo key; thứ tự key thường không phải hợp đồng dữ liệu. Trong PostgreSQL `jsonb`, thứ tự khóa có thể thay đổi khi lưu/hiển thị.

JSON array thì có thứ tự phần tử:

~~~json
[{"lineNo": 1}, {"lineNo": 2}]
~~~

khác:

~~~json
[{"lineNo": 2}, {"lineNo": 1}]
~~~

Nếu client cần hiển thị dòng hàng theo `line_no`, ta phải xác định thứ tự **ngay lúc tổng hợp array**; không dựa vào thứ tự vật lý của bảng.

## 7. jsonb_agg: biến nhiều hàng thành một mảng

### 7.1. Tạo danh sách SKU của một đơn

~~~sql
SELECT
    oi.order_id,
    jsonb_agg(
        p.sku
        ORDER BY oi.line_no
    ) AS skus
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1001
GROUP BY oi.order_id;
~~~

Kết quả:

~~~json
["NOTE-01", "PEN-02"]
~~~

`jsonb_agg` là **aggregate function**: nó nhận một giá trị trên **mỗi hàng đầu vào**, rồi gom các giá trị đó thành một JSON array.

### 7.2. Tổng hợp array các object

~~~sql
SELECT
    oi.order_id,
    jsonb_agg(
        jsonb_build_object(
            'lineNo', oi.line_no,
            'sku', p.sku,
            'productName', p.product_name,
            'quantity', oi.quantity,
            'unitPrice', oi.unit_price
        )
        ORDER BY oi.line_no
    ) AS items
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1001
GROUP BY oi.order_id;
~~~

Kết quả:

~~~json
[
  {
    "lineNo": 1,
    "sku": "NOTE-01",
    "productName": "Sổ tay",
    "quantity": 2,
    "unitPrice": 50.00
  },
  {
    "lineNo": 2,
    "sku": "PEN-02",
    "productName": "Bút bi",
    "quantity": 3,
    "unitPrice": 10.00
  }
]
~~~

Mỗi hàng `order_items` tạo **một object**, còn `jsonb_agg` tạo **một array** chứa các object đó.

### 7.3. ORDER BY đặt bên trong aggregate

Đúng:

~~~sql
jsonb_agg(
    jsonb_build_object('lineNo', oi.line_no, 'sku', p.sku)
    ORDER BY oi.line_no
)
~~~

Không đủ chắc chắn:

~~~sql
SELECT jsonb_agg(jsonb_build_object('lineNo', line_no))
FROM (
    SELECT line_no
    FROM order_items
    ORDER BY line_no
) AS pre_sorted;
~~~

Một subquery có `ORDER BY` có thể cho thứ tự mong muốn trong những trường hợp cụ thể, nhưng nếu kết quả đi qua các phép JOIN/aggregate hoặc optimizer thay đổi kế hoạch, **không nên dựa vào thứ tự từ nguồn như một bảo đảm chung**. Đặt `ORDER BY` **bên trong chính `jsonb_agg`** là cách diễn đạt thứ tự phần tử rõ nhất trong PostgreSQL.

Để tránh thứ tự không ổn định khi bằng nhau, thêm khóa phá hòa:

~~~sql
jsonb_agg(
    jsonb_build_object('lineNo', oi.line_no)
    ORDER BY oi.order_id, oi.line_no
)
~~~

Trong một đơn đã lọc theo `order_id`, `line_no` là duy nhất nên đủ; trong một tập rộng hơn, chọn các khóa sort phù hợp.

### 7.4. Không có GROUP BY thì kết quả gom tất cả hàng nguồn

~~~sql
SELECT jsonb_agg(order_id ORDER BY order_id) AS all_order_ids
FROM orders;
~~~

Kết quả:

~~~json
[1001, 1002, 1003, 1004, 1005]
~~~

Đây là **một hàng kết quả SQL**, chứa một giá trị array. Nếu muốn một array cho **mỗi khách hàng**, phải `GROUP BY customer_id` hoặc dùng truy vấn con tương quan.

### 7.5. GROUP BY đúng cấp cha

~~~sql
SELECT
    o.customer_id,
    jsonb_agg(
        o.order_id
        ORDER BY o.ordered_at, o.order_id
    ) AS order_ids
FROM orders AS o
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Kết quả:

| customer_id | order_ids |
| ---: | --- |
| 1 | `[1001, 1002]` |
| 2 | `[1003, 1005]` |
| 3 | `[1004]` |

Khách `4` không có hàng ở `orders`, nên **không xuất hiện trong kết quả** của truy vấn bắt đầu từ `orders`. Muốn giữ cả khách không có đơn, phải lấy `customers` làm bảng cha và xử lý array rỗng.

## 8. Mảng rỗng, JSON null và LEFT JOIN

### 8.1. Aggregate trên tập không có hàng trả SQL NULL

~~~sql
SELECT jsonb_agg(
    jsonb_build_object(
        'lineNo', oi.line_no,
        'quantity', oi.quantity
    )
) AS items
FROM order_items AS oi
WHERE oi.order_id = 1004;
~~~

Vì không có dòng hàng cho đơn `1004`, `jsonb_agg` trả **SQL NULL**, không tự trả `[]`.

Trong nhiều API, một field có kiểu danh sách cần là `[]` ngay cả khi không có phần tử.

### 8.2. COALESCE trả []

~~~sql
SELECT COALESCE(
    jsonb_agg(
        jsonb_build_object(
            'lineNo', oi.line_no,
            'quantity', oi.quantity
        )
    ),
    '[]'::jsonb
) AS items
FROM order_items AS oi
WHERE oi.order_id = 1004;
~~~

Kết quả:

~~~json
[]
~~~

`'[]'::jsonb` là một giá trị JSON array rỗng, không phải chuỗi JSON `"[]"`.

Sai ý định:

~~~sql
COALESCE(jsonb_agg(...), '[]'::text)
~~~

Nếu trộn kiểu không tương thích, PostgreSQL có thể không phân giải kiểu như mong muốn. Giữ biểu thức và fallback cùng kiểu `jsonb`.

### 8.3. LEFT JOIN có thể sinh một hàng giả với các cột bên phải NULL

Truy vấn:

~~~sql
SELECT
    o.order_id,
    jsonb_agg(
        jsonb_build_object(
            'lineNo', oi.line_no,
            'quantity', oi.quantity
        )
    ) AS items
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.order_id = 1004
GROUP BY o.order_id;
~~~

**Không** tự trả `[]`. Vì LEFT JOIN giữ hàng cha, bên phải có một hàng được **null-extend**, nên hàm dựng object vẫn chạy và tạo object có key với null:

~~~json
[
  {"lineNo": null, "quantity": null}
]
~~~

Đây là **một phần tử giả**, không phải danh sách rỗng thật.

### 8.4. FILTER loại hàng null-extended

Đúng:

~~~sql
SELECT
    o.order_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'quantity', oi.quantity
            )
            ORDER BY oi.line_no
        ) FILTER (
            WHERE oi.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ) AS items
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.order_id = 1004
GROUP BY o.order_id;
~~~

Kết quả:

| order_id | items |
| ---: | --- |
| 1004 | `[]` |

`oi.order_id` là một phần của **PRIMARY KEY**, nên giá trị này không thể NULL cho hàng con thật. Nó là điều kiện tin cậy để phân biệt hàng thật với hàng giả do LEFT JOIN.

**Không lọc theo một cột con được phép NULL** như `note IS NOT NULL`, vì điều đó sẽ vô tình làm mất những hàng con hợp lệ có note rỗng.

### 8.5. Một câu cho mọi đơn, kể cả không có item

~~~sql
SELECT
    o.order_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'productId', oi.product_id,
                'quantity', oi.quantity
            )
            ORDER BY oi.line_no
        ) FILTER (
            WHERE oi.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ) AS items
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Năm đơn đều xuất hiện; `1004` có `items=[]`. Đây là mẫu phổ biến khi ánh xạ quan hệ **một-nhiều**.

## 9. Gói một đơn hàng thành object có items và subtotal

### 9.1. Truy vấn tổng hợp theo order_id

~~~sql
SELECT
    o.order_id,
    jsonb_build_object(
        'orderId', o.order_id,
        'status', o.order_status,
        'items', COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'lineNo', oi.line_no,
                    'sku', p.sku,
                    'productName', p.product_name,
                    'quantity', oi.quantity,
                    'unitPrice', oi.unit_price
                )
                ORDER BY oi.line_no
            ) FILTER (
                WHERE oi.order_id IS NOT NULL
            ),
            '[]'::jsonb
        ),
        'subtotal', COALESCE(
            SUM(oi.quantity * oi.unit_price),
            0::NUMERIC
        )
    ) AS order_json
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN products AS p
  ON p.product_id = oi.product_id
WHERE o.order_id = 1001
GROUP BY o.order_id, o.order_status;
~~~

Kết quả:

~~~json
{
  "orderId": 1001,
  "status": "PAID",
  "items": [
    {
      "lineNo": 1,
      "sku": "NOTE-01",
      "productName": "Sổ tay",
      "quantity": 2,
      "unitPrice": 50.00
    },
    {
      "lineNo": 2,
      "sku": "PEN-02",
      "productName": "Bút bi",
      "quantity": 3,
      "unitPrice": 10.00
    }
  ],
  "subtotal": 130.00
}
~~~

Giải thích:

- `GROUP BY` tạo một nhóm cho đơn 1001.
- `jsonb_agg` gom mọi dòng hàng của đơn thành array.
- `FILTER` loại hàng giả khi đơn không có dòng.
- `SUM(quantity * unit_price)` tính tổng tiền dòng hàng.
- `jsonb_build_object` lồng cả số tiền và mảng vào object của đơn.

Với `order_id=1004`, cùng mẫu sẽ có `"items": []` và `"subtotal": 0`.

### 9.2. Vì sao không SUM products.list_price?

`products.list_price` là giá hiện tại; `order_items.unit_price` là giá tại thời điểm đơn được ghi. Nếu đã có khuyến mãi, chiết khấu hoặc thay đổi bảng giá, dùng giá sản phẩm hiện tại để tính doanh thu quá khứ có thể sai.

Phép tổng trong ví dụ là:

~~~sql
SUM(oi.quantity * oi.unit_price)
~~~

Không phải:

~~~sql
SUM(oi.quantity * p.list_price)
~~~

Trường `subtotal` ở đây chưa bao gồm phí vận chuyển, thuế hoặc hoàn tiền; khi tích hợp nghiệp vụ thật, cần định nghĩa nguồn và công thức số tiền một cách rõ ràng.

### 9.3. Hạn chế của mẫu GROUP BY nhiều cột

Nếu trong object ta muốn đưa vào nhiều thuộc tính của đơn hoặc khách, phải thêm các cột non-aggregated vào `GROUP BY` khi cần, hoặc tách quá trình thành bước tổng hợp con rồi JOIN về cha.

Một tài liệu JSON nhiều cấp thường dễ viết và kiểm soát hơn bằng **CTE tiền tổng hợp**, **subquery tương quan**, hoặc `LATERAL` thay vì một câu GROUP BY khổng lồ.

## 10. LATERAL: tạo mảng con cho từng hàng cha

### 10.1. Ý tưởng

Một truy vấn con có thể cần tham chiếu `order_id` của hàng cha đang xét. PostgreSQL có `LATERAL`:

~~~text
orders o
   |
   | với mỗi o.order_id
   v
LATERAL query → tổng hợp items thành một JSON array
   |
   v
jsonb_build_object(...) → một object cho mỗi đơn
~~~

### 10.2. Ví dụ hoàn chỉnh

~~~sql
SELECT
    o.order_id,
    jsonb_build_object(
        'orderId', o.order_id,
        'status', o.order_status,
        'items', lines.items,
        'subtotal', lines.subtotal
    ) AS document
FROM orders AS o
CROSS JOIN LATERAL (
    SELECT
        COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'lineNo', oi.line_no,
                    'sku', p.sku,
                    'quantity', oi.quantity,
                    'unitPrice', oi.unit_price
                )
                ORDER BY oi.line_no
            ),
            '[]'::jsonb
        ) AS items,
        COALESCE(
            SUM(oi.quantity * oi.unit_price),
            0::NUMERIC
        ) AS subtotal
    FROM order_items AS oi
    JOIN products AS p
      ON p.product_id = oi.product_id
    WHERE oi.order_id = o.order_id
) AS lines
WHERE o.order_id IN (1001, 1004)
ORDER BY o.order_id;
~~~

Với đơn 1001, `lines.items` có hai phần tử, subtotal 130. Với đơn 1004, `lines.items=[]`, subtotal 0.

### 10.3. Vì sao CROSS JOIN LATERAL không loại đơn 1004?

Trong subquery `lines`, `jsonb_agg` và `SUM` là aggregate **không có GROUP BY**. Dù tập input không có hàng, PostgreSQL vẫn trả **một hàng tổng hợp** có các giá trị aggregate NULL, rồi `COALESCE` chuyển thành `[]` và 0.

Nếu thay subquery bằng dạng có `GROUP BY oi.order_id`, nó có thể trả **0 hàng** khi không có item. Khi đó `CROSS JOIN LATERAL` sẽ loại hàng cha; nếu muốn giữ cha phải cân nhắc `LEFT JOIN LATERAL ... ON TRUE` và xử lý null.

### 10.4. Correlated scalar subquery cũng phù hợp

Khi chỉ cần một mảng nhỏ:

~~~sql
SELECT
    o.order_id,
    jsonb_build_object(
        'orderId', o.order_id,
        'items', COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'lineNo', oi.line_no,
                        'quantity', oi.quantity
                    )
                    ORDER BY oi.line_no
                )
                FROM order_items AS oi
                WHERE oi.order_id = o.order_id
            ),
            '[]'::jsonb
        )
    ) AS document
FROM orders AS o
ORDER BY o.order_id;
~~~

Truy vấn con tương quan được đặt làm **giá trị của field items**. Nó tự trả aggregate một hàng; cha không bị loại khi không có item.

Chọn `LATERAL` khi cần trả **nhiều giá trị tính chung một lần** như `items`, `subtotal`, `itemCount`, hoặc khi cú pháp trở nên rõ ràng hơn. Chọn scalar subquery khi logic gọn. Với tập cha rất lớn, cần đo kế hoạch thực thi để biết giải pháp nào phù hợp.

## 11. Tổng hợp nhiều quan hệ một-nhiều: tránh nhân bản dữ liệu

Đây là lỗi quan trọng nhất khi dựng JSON lồng nhiều mảng.

### 11.1. JOIN cả items và payments trực tiếp

Giả sử dùng:

~~~sql
SELECT
    o.order_id,
    oi.line_no,
    oi.quantity,
    pa.payment_id,
    pa.amount AS payment_amount
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN payments AS pa
  ON pa.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY oi.line_no, pa.payment_id;
~~~

Đơn 1001 có 2 items và 2 payments. Kết quả JOIN:

| order_id | line_no | quantity | payment_id | payment_amount |
| ---: | ---: | ---: | ---: | ---: |
| 1001 | 1 | 2 | 501 | 100 |
| 1001 | 1 | 2 | 502 | 30 |
| 1001 | 2 | 3 | 501 | 100 |
| 1001 | 2 | 3 | 502 | 30 |

Có **4 hàng**, không phải 2. Đây là phép nhân lực lượng `2 × 2` của hai nhánh con độc lập.

### 11.2. Điều gì sai nếu jsonb_agg ngay trên JOIN này?

Nếu viết đồng thời:

~~~sql
jsonb_agg(jsonb_build_object('lineNo', oi.line_no, ...))
~~~

và:

~~~sql
jsonb_agg(jsonb_build_object('paymentId', pa.payment_id, ...))
~~~

trên tập JOIN bốn hàng, array items sẽ có **mỗi dòng hàng lặp hai lần**, array payments cũng lặp hai lần.

Càng nguy hiểm hơn:

~~~sql
SUM(oi.quantity * oi.unit_price)
~~~

sẽ cho `260` thay vì `130` cho đơn 1001, vì mỗi dòng hàng bị đếm hai lần.

**Đây không phải lỗi của JSON.** Nó là lỗi xác định **cấp tổng hợp quan hệ** trước khi dựng JSON.

### 11.3. Không dùng DISTINCT như thuốc chữa mọi fan-out

`jsonb_agg(DISTINCT ...)` có thể loại một số object lặp, nhưng:

- Có thể xóa những dòng hàng **thật** có giá trị object giống nhau.
- Có thể làm mất hoặc khó bảo đảm thứ tự.
- Không sửa được phép `SUM` bị nhân số hàng nếu vẫn SUM trên JOIN sai.
- Aggregate DISTINCT kèm ORDER BY có các giới hạn cú pháp của PostgreSQL.
- Có thể tăng chi phí xử lý mà vẫn che nguyên nhân mô hình sai.

Cách đúng là **tổng hợp từng nhánh một-nhiều riêng**, mỗi nhánh tạo đúng một hàng trên mỗi `order_id`, rồi JOIN các kết quả đã tổng hợp về bảng cha.

### 11.4. Tiền tổng hợp items trong CTE

~~~sql
WITH item_totals AS (
    SELECT
        oi.order_id,
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'sku', p.sku,
                'quantity', oi.quantity,
                'unitPrice', oi.unit_price
            )
            ORDER BY oi.line_no
        ) AS items,
        SUM(oi.quantity * oi.unit_price) AS subtotal
    FROM order_items AS oi
    JOIN products AS p
      ON p.product_id = oi.product_id
    GROUP BY oi.order_id
)
SELECT *
FROM item_totals
ORDER BY order_id;
~~~

Mỗi `order_id` có **tối đa một hàng** trong `item_totals`. Không có hàng cho đơn 1004 vì không có item; điều đó sẽ được xử lý ở JOIN với bảng orders.

### 11.5. Tiền tổng hợp payments trong CTE riêng

~~~sql
WITH payment_totals AS (
    SELECT
        pa.order_id,
        jsonb_agg(
            jsonb_build_object(
                'paymentId', pa.payment_id,
                'method', pa.payment_method,
                'amount', pa.amount,
                'status', pa.payment_status
            )
            ORDER BY pa.payment_id
        ) AS payments,
        COALESCE(
            SUM(pa.amount) FILTER (
                WHERE pa.payment_status = 'CAPTURED'
            ),
            0::NUMERIC
        ) AS captured_amount
    FROM payments AS pa
    GROUP BY pa.order_id
)
SELECT *
FROM payment_totals
ORDER BY order_id;
~~~

`payment_totals` cũng có tối đa một hàng trên mỗi đơn.

### 11.6. Kết hợp hai nhánh đã tổng hợp

~~~sql
WITH item_totals AS (
    SELECT
        oi.order_id,
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'sku', p.sku,
                'quantity', oi.quantity,
                'unitPrice', oi.unit_price
            )
            ORDER BY oi.line_no
        ) AS items,
        SUM(oi.quantity * oi.unit_price) AS subtotal
    FROM order_items AS oi
    JOIN products AS p
      ON p.product_id = oi.product_id
    GROUP BY oi.order_id
),
payment_totals AS (
    SELECT
        pa.order_id,
        jsonb_agg(
            jsonb_build_object(
                'paymentId', pa.payment_id,
                'method', pa.payment_method,
                'amount', pa.amount,
                'status', pa.payment_status
            )
            ORDER BY pa.payment_id
        ) AS payments,
        COALESCE(
            SUM(pa.amount) FILTER (
                WHERE pa.payment_status = 'CAPTURED'
            ),
            0::NUMERIC
        ) AS captured_amount
    FROM payments AS pa
    GROUP BY pa.order_id
)
SELECT
    o.order_id,
    jsonb_build_object(
        'orderId', o.order_id,
        'status', o.order_status,
        'items', COALESCE(
            it.items, '[]'::jsonb
        ),
        'subtotal', COALESCE(
            it.subtotal, 0::NUMERIC
        ),
        'payments', COALESCE(
            pt.payments, '[]'::jsonb
        ),
        'capturedAmount', COALESCE(
            pt.captured_amount, 0::NUMERIC
        )
    ) AS document
FROM orders AS o
LEFT JOIN item_totals AS it
  ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
  ON pt.order_id = o.order_id
WHERE o.order_id IN (1001, 1004)
ORDER BY o.order_id;
~~~

Đơn 1001 có:

- `items`: đúng 2 phần tử.
- `payments`: đúng 2 phần tử.
- `subtotal`: 130.
- `capturedAmount`: 130.

Đơn 1004 có:

- `items=[]`.
- `payments=[]`.
- `subtotal=0`.
- `capturedAmount=0`.

Số tiền thanh toán ở đây chỉ là một ví dụ cộng các payment `CAPTURED`; không đồng nhất nó với tổng hóa đơn trong mọi trạng thái (hoàn tiền, phí, partial capture và chargeback cần mô hình riêng).

### 11.7. Nguyên tắc tổng hợp trước, nối sau

~~~text
order_items -- GROUP BY order_id --> item_totals
                                  (1 row per order_id)
                                           |
orders ------------------------------------+-- JOIN --> order JSON
                                           |
payments ---- GROUP BY order_id --> payment_totals
                                  (1 row per order_id)
~~~

Khi cần nhiều arrays song song, hãy tách các phép aggregate ở **đúng cấp con**, rồi ghép bằng khóa cha. Điều này bảo vệ cả **tính đúng đắn của JSON** lẫn **các tổng số học**.

## 12. Tạo JSON nhiều cấp khách hàng → đơn hàng → items

### 12.1. Mục tiêu

Ví dụ khách An:

~~~json
{
  "customerId": 1,
  "name": "An",
  "orders": [
    {
      "orderId": 1001,
      "status": "PAID",
      "items": [
        {"lineNo": 1, "sku": "NOTE-01", "quantity": 2},
        {"lineNo": 2, "sku": "PEN-02", "quantity": 3}
      ]
    },
    {
      "orderId": 1002,
      "status": "PENDING",
      "items": [
        {"lineNo": 1, "sku": "BAG-03", "quantity": 1}
      ]
    }
  ]
}
~~~

Một khách có **nhiều đơn**, mỗi đơn có **nhiều item**. Để tạo tài liệu đúng cấp, có thể đi từ trong ra ngoài:

1. Tổng hợp `order_items` thành một array trên mỗi `order_id`.
2. Dựng một object JSON trên mỗi đơn, chứa array items.
3. Tổng hợp các object đơn thành array trên mỗi `customer_id`.
4. Dựng object khách hàng chứa array orders.

### 12.2. Câu SQL PostgreSQL nhiều CTE

~~~sql
WITH item_arrays AS (
    SELECT
        oi.order_id,
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'sku', p.sku,
                'quantity', oi.quantity
            )
            ORDER BY oi.line_no
        ) AS items
    FROM order_items AS oi
    JOIN products AS p
      ON p.product_id = oi.product_id
    GROUP BY oi.order_id
),
order_objects AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        jsonb_build_object(
            'orderId', o.order_id,
            'status', o.order_status,
            'items', COALESCE(
                ia.items, '[]'::jsonb
            )
        ) AS order_document
    FROM orders AS o
    LEFT JOIN item_arrays AS ia
      ON ia.order_id = o.order_id
),
customer_order_arrays AS (
    SELECT
        oo.customer_id,
        jsonb_agg(
            oo.order_document
            ORDER BY oo.ordered_at, oo.order_id
        ) AS orders
    FROM order_objects AS oo
    GROUP BY oo.customer_id
)
SELECT
    c.customer_id,
    jsonb_build_object(
        'customerId', c.customer_id,
        'name', c.full_name,
        'orders', COALESCE(
            ca.orders, '[]'::jsonb
        )
    ) AS customer_document
FROM customers AS c
LEFT JOIN customer_order_arrays AS ca
  ON ca.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả cuối có **4 hàng SQL**, mỗi hàng là một tài liệu khách:

| customer_id | Số object trong orders | Ghi chú |
| ---: | ---: | --- |
| 1 | 2 | Đơn 1001 và 1002 |
| 2 | 2 | Đơn 1003 và 1005 |
| 3 | 1 | Đơn 1004 có `items=[]` |
| 4 | 0 | Khách Dũng có `orders=[]` |

### 12.3. Vì sao cách này không tạo nhân bản?

Trong `item_arrays`, mỗi đơn có **tối đa một hàng**; trong `order_objects`, mỗi đơn tạo **một object**; trong `customer_order_arrays`, mỗi khách có **tối đa một hàng**. Các phép JOIN giữa các cấp đều dựa trên quan hệ đã giảm lực lượng đúng cách.

Nếu viết một truy vấn thẳng từ khách qua đơn rồi qua items và payments và cùng dùng `jsonb_agg`, có thể vô tình tạo nhiều bản sao của đơn hoặc dòng hàng.

### 12.4. Một output lớn hay nhiều tài liệu nhỏ?

Truy vấn trên trả một document cho mỗi khách. Nếu cần một **mảng chứa tất cả khách hàng**, có thể bao ngoài:

~~~sql
WITH customer_docs AS (
    -- Thay bằng SELECT dựng một JSON document
    -- trên mỗi customer như truy vấn đầy đủ ở trên.
    SELECT
        customer_id,
        jsonb_build_object(
            'customerId', customer_id,
            'name', full_name
        ) AS document
    FROM customers
)
SELECT COALESCE(
    jsonb_agg(
        document ORDER BY customer_id
    ),
    '[]'::jsonb
) AS customers
FROM customer_docs;
~~~

Đoạn này minh họa **cấu trúc aggregate ngoài cùng**, sử dụng document khách rút gọn để tự chạy được trên dữ liệu mẫu. Để trả toàn bộ cây có orders/items, dùng truy vấn dựng customer document đầy đủ làm nội dung CTE `customer_docs`.

Với API thực tế, không nên luôn trả **toàn bộ database thành một JSON document lớn**. Tải hàng nghìn khách cùng mọi đơn và item sẽ tăng bộ nhớ, CPU serialize và kích thước response. Cần lọc/phân trang ở cấp cha phù hợp.

## 13. jsonb_object_agg: gom nhiều hàng thành object có key động

### 13.1. Array và object map khác nhau

Từ hai dòng của đơn 1001:

| sku | quantity |
| --- | ---: |
| NOTE-01 | 2 |
| PEN-02 | 3 |

Ta có hai cách biểu diễn.

**Array of objects:**

~~~json
[
  {"sku": "NOTE-01", "quantity": 2},
  {"sku": "PEN-02", "quantity": 3}
]
~~~

**Object map:**

~~~json
{
  "NOTE-01": 2,
  "PEN-02": 3
}
~~~

Array phù hợp khi cần giữ **thứ tự và các dòng riêng**. Object map phù hợp khi muốn **tra theo key**, với điều kiện mỗi key trong output có ý nghĩa **duy nhất**.

### 13.2. Tạo object map từ hai cột

~~~sql
SELECT COALESCE(
    jsonb_object_agg(
        p.sku,
        oi.quantity
        ORDER BY oi.line_no
    ),
    '{}'::jsonb
) AS quantity_by_sku
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1001;
~~~

Kết quả:

~~~json
{
  "NOTE-01": 2,
  "PEN-02": 3
}
~~~

`jsonb_object_agg(key, value)` lấy **key từ một cột** và **value từ cột khác** cho mỗi hàng. Nó không giống `jsonb_build_object`, nơi các tên key thường được viết cố định.

### 13.3. Khi không có hàng, object rỗng là {}

~~~sql
SELECT COALESCE(
    jsonb_object_agg(p.sku, oi.quantity),
    '{}'::jsonb
) AS quantity_by_sku
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1004;
~~~

Kết quả:

~~~json
{}
~~~

Chọn fallback theo kiểu:

- `'[]'::jsonb` cho **array**.
- `'{}'::jsonb` cho **object**.

Đừng trả `[]` nếu client trông đợi một map object, hoặc trả `{}` khi trường được khai báo là danh sách.

### 13.4. Key của object không được NULL

Trong PostgreSQL, `jsonb_object_agg` không chấp nhận một key SQL NULL. Ví dụ logic gây lỗi:

~~~sql
-- Ví dụ lỗi: key NULL không hợp lệ.
SELECT jsonb_object_agg(sku, qty)
FROM (
    VALUES
        (NULL::TEXT, 2),
        ('PEN-02'::TEXT, 3)
) AS x(sku, qty);
~~~

Nếu nguồn có key nullable, cần:

- Lọc các hàng có key NULL một cách có chủ đích;
- Chuẩn hóa key từ upstream;
- Hoặc chuyển sang array các object nếu key không thật sự duy nhất/bắt buộc.

Không tự đổi NULL thành chuỗi `"null"` hoặc `"unknown"` nếu không có chính sách nghiệp vụ rõ.

### 13.5. Duplicate keys làm mất thông tin

Giả sử đơn 1001 có hai dòng đều dùng cùng SKU:

~~~text
line 1: NOTE-01, qty=2
line 2: NOTE-01, qty=5
~~~

Nếu tổng hợp trực tiếp bằng `jsonb_object_agg(sku, qty)`, object JSON không thể giữ **hai thành viên phân biệt cùng key** một cách đáng tin như array. Với `jsonb`, một giá trị cho key trùng sẽ được giữ theo quy tắc xử lý; thông tin từng dòng bị mất.

Nếu nghiệp vụ muốn tổng số lượng theo SKU, hãy **GROUP BY SKU trước**:

~~~sql
WITH quantity_by_sku AS (
    SELECT
        oi.order_id,
        p.sku,
        SUM(oi.quantity) AS total_quantity
    FROM order_items AS oi
    JOIN products AS p
      ON p.product_id = oi.product_id
    WHERE oi.order_id = 1001
    GROUP BY oi.order_id, p.sku
)
SELECT COALESCE(
    jsonb_object_agg(
        sku, total_quantity
    ),
    '{}'::jsonb
) AS quantity_map
FROM quantity_by_sku;
~~~

Cách này làm rõ **quy tắc hợp nhất**: mỗi SKU trở thành một key duy nhất với số lượng tổng. Nếu cần giữ hai dòng riêng, dùng array thay vì map.

### 13.6. JSON object không phải bảng có UNIQUE constraint

Dù key JSON object về mặt biểu diễn là duy nhất trong `jsonb`, điều đó không tự thay ràng buộc `UNIQUE(sku)` của bảng nguồn. Các phép tổng hợp với key trùng có thể làm mất dữ liệu mà không báo conflict theo nghiệp vụ.

Đừng dùng JSON object như kho dữ liệu duy nhất nếu cần kiểm soát số dòng, lịch sử thay đổi và ràng buộc quan hệ.

## 14. row_to_json, to_jsonb và cách chọn các cột đưa ra ngoài

### 14.1. Chuyển toàn bộ một hàng thành JSON

PostgreSQL:

~~~sql
SELECT to_jsonb(c) AS document
FROM customers AS c
WHERE c.customer_id = 1;
~~~

Kết quả dựa trên tên cột của bảng:

~~~json
{
  "customer_id": 1,
  "full_name": "An",
  "city": "Hà Nội"
}
~~~

`row_to_json(c)` trả kiểu `json`; `to_jsonb(c)` trả `jsonb`.

Cách này tiện khi muốn chuyển một bản ghi tương đối ổn định thành JSON, nhưng **có thể vô tình xuất quá nhiều cột** nếu schema sau này thêm trường nhạy cảm hoặc nội bộ.

### 14.2. Chọn field và alias trước khi chuyển

~~~sql
SELECT to_jsonb(x) AS customer_json
FROM (
    SELECT
        customer_id AS "customerId",
        full_name AS "name"
    FROM customers
    WHERE customer_id = 1
) AS x;
~~~

Kết quả:

~~~json
{"customerId": 1, "name": "An"}
~~~

Dấu nháy kép trong PostgreSQL giữ **chữ hoa/thường** của alias. Nếu viết `AS customerId` không quote, định danh SQL có thể bị chuyển thành chữ thường `customerid`, không đúng contract JSON.

Tùy nhu cầu, `jsonb_build_object` còn rõ ràng hơn:

~~~sql
SELECT jsonb_build_object(
    'customerId', c.customer_id,
    'name', c.full_name
)
FROM customers AS c
WHERE c.customer_id = 1;
~~~

### 14.3. Loại bỏ hoặc thêm thuộc tính cho jsonb object

PostgreSQL cho phép thao tác trên `jsonb`:

~~~sql
SELECT
    to_jsonb(c) - 'city' AS without_city
FROM customers AS c
WHERE c.customer_id = 1;
~~~

`- 'city'` bỏ key `city` ở object cấp ngoài. Có thể kết hợp nhiều phép toán phù hợp:

~~~sql
SELECT
    jsonb_build_object(
        'customerId', c.customer_id,
        'name', c.full_name
    )
    || jsonb_build_object(
        'hasOrders', EXISTS (
            SELECT 1
            FROM orders AS o
            WHERE o.customer_id = c.customer_id
        )
    ) AS document
FROM customers AS c;
~~~

Toán tử `||` ghép `jsonb` object ở cấp ngoài theo quy tắc PostgreSQL; nếu hai phía có cùng key, một giá trị có thể ghi đè giá trị kia. Nó **không phải phép merge đệ quy tổng quát** cho mọi object lồng sâu.

### 14.4. Tên trường là phần của API contract

Khi JSON được tiêu thụ bởi frontend hoặc dịch vụ khác, key như `orderId`, `orderedAt` và `lineNo` cần được thống nhất. Không tự dùng `to_jsonb(table_alias)` rồi mặc định tên cột snake_case đáp ứng mọi client.

Một schema/API contract ổn định nên quyết định:

- Casing của key;
- Field nào bắt buộc/tùy chọn;
- Kiểu dữ liệu: number, string, boolean, object, array, null;
- Thứ tự array;
- Định dạng thời gian và đơn vị tiền;
- Quy tắc bỏ key khi null;
- Pagination và versioning.

## 15. Tổng hợp có điều kiện: FILTER và mảng riêng theo trạng thái

### 15.1. Một khách có đơn PAID và PENDING

~~~sql
SELECT
    o.customer_id,
    COALESCE(
        jsonb_agg(
            o.order_id
            ORDER BY o.order_id
        ) FILTER (
            WHERE o.order_status = 'PAID'
        ),
        '[]'::jsonb
    ) AS paid_order_ids,
    COALESCE(
        jsonb_agg(
            o.order_id
            ORDER BY o.order_id
        ) FILTER (
            WHERE o.order_status = 'PENDING'
        ),
        '[]'::jsonb
    ) AS pending_order_ids
FROM orders AS o
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Kết quả:

| customer_id | paid_order_ids | pending_order_ids |
| ---: | --- | --- |
| 1 | `[1001]` | `[1002]` |
| 2 | `[1003,1005]` | `[]` |
| 3 | `[]` | `[]` |

Khách 3 chỉ có đơn CANCELLED, vì vậy cả hai arrays lọc đều rỗng.

### 15.2. Vì sao FILTER phù hợp hơn chèn null?

Mẫu:

~~~sql
jsonb_agg(
    CASE
        WHEN order_status = 'PAID' THEN order_id
        ELSE NULL
    END
)
~~~

có thể tạo các phần tử **JSON null** cho đơn không PAID. Với một khách có một đơn PAID và một PENDING, kết quả có thể là `[1001, null]` thay vì `[1001]`.

Dùng `FILTER (WHERE ...)` để loại **hàng đầu vào** khỏi aggregate, không chỉ biến giá trị của nó thành NULL.

### 15.3. Giữ khách hàng không có đơn

Bắt đầu từ `customers` rồi LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'orderId', o.order_id,
                'status', o.order_status
            )
            ORDER BY o.order_id
        ) FILTER (
            WHERE o.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ) AS orders
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Khách Dũng (4) có `orders=[]`. Không dùng `WHERE o.order_status='PAID'` ở cuối truy vấn nếu cần giữ cả khách không có đơn: điều kiện WHERE như vậy có thể loại các hàng null-extended và biến ý nghĩa LEFT JOIN thành tương tự INNER JOIN đối với những hàng đó.

Khi cần lọc đơn PAID nhưng vẫn giữ khách:

~~~sql
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
~~~

kết hợp `FILTER (WHERE o.order_id IS NOT NULL)` trong aggregate.

## 16. Truy vấn dữ liệu JSON đã dựng

Dù bài tập trung vào **tạo JSON**, việc đọc lại giúp hiểu kiểu kết quả và cấu trúc.

### 16.1. Toán tử -> và ->>

PostgreSQL:

~~~sql
WITH doc AS (
    SELECT jsonb_build_object(
        'orderId', 1001,
        'customer', jsonb_build_object(
            'name', 'An'
        ),
        'items', jsonb_build_array(
            jsonb_build_object(
                'sku', 'NOTE-01',
                'quantity', 2
            )
        )
    ) AS payload
)
SELECT
    payload -> 'customer' AS customer_object,
    payload -> 'items' AS items_array,
    payload #>> '{customer,name}' AS customer_name_text,
    payload ->> 'orderId' AS order_id_text
FROM doc;
~~~

- `->` trả một giá trị JSON/JSONB tại key hoặc vị trí tương ứng.
- `->>` trả nội dung dưới dạng **TEXT**.
- `#>>` đọc một đường dẫn nhiều cấp và trả TEXT.

Ví dụ `payload ->> 'orderId'` cho chuỗi `'1001'`, không phải kiểu INTEGER SQL. Nếu muốn so với số, ép kiểu có kiểm soát khi dữ liệu hợp lệ:

~~~sql
(payload ->> 'orderId')::INTEGER
~~~

### 16.2. Mở array bằng jsonb_array_elements

~~~sql
WITH doc AS (
    SELECT jsonb_build_object(
        'items',
        jsonb_build_array(
            jsonb_build_object('sku', 'NOTE-01', 'quantity', 2),
            jsonb_build_object('sku', 'PEN-02', 'quantity', 3)
        )
    ) AS payload
)
SELECT
    item ->> 'sku' AS sku,
    (item ->> 'quantity')::INTEGER AS quantity
FROM doc
CROSS JOIN LATERAL jsonb_array_elements(
    payload -> 'items'
) AS x(item);
~~~

Kết quả hai hàng NOTE-01/2 và PEN-02/3. Hàm `jsonb_array_elements` chuyển một mảng JSONB thành **tập hàng**, để SQL tiếp tục xử lý theo quan hệ.

Không tự gọi `jsonb_array_elements` cho một scalar hoặc JSON object; cần kiểm tra loại giá trị theo contract. Nếu field có thể không phải array, dữ liệu đầu vào nên được validate.

### 16.3. JSON null và key vắng mặt

~~~sql
SELECT
    '{"city":null}'::jsonb ? 'city' AS has_city_key,
    '{}'::jsonb ? 'city' AS missing_city_key,
    '{"city":null}'::jsonb -> 'city' AS json_null_value,
    '{}'::jsonb -> 'city' AS absent_value;
~~~

- `? 'city'` kiểm tra **key tồn tại** ở object cấp ngoài.
- Object `{"city":null}` có key city, còn `{}` không có.
- Lấy `-> 'city'` ở key vắng mặt trả **SQL NULL**; ở key chứa JSON null trả **giá trị JSONB null**.
- Khi in qua client, cách biểu diễn hai loại null có thể dễ bị nhầm; cần kiểm tra theo kiểu dữ liệu, không chỉ nhìn text.

### 16.4. Không biến JSON thành nguồn duy nhất nếu đã có bảng chuẩn hóa

Nếu cần lọc “mọi đơn chứa sản phẩm NOTE-01” và hệ đã có `order_items`/`products`, câu SQL JOIN trên bảng chuẩn hóa thường rõ ràng hơn:

~~~sql
SELECT DISTINCT oi.order_id
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE p.sku = 'NOTE-01';
~~~

Không cần tạo JSON rồi mở lại bằng `jsonb_array_elements` chỉ để truy vấn một quan hệ đã tồn tại.

## 17. Hiệu năng, index và pagination

### 17.1. Aggregate JSON có thể tốn bộ nhớ

Một `jsonb_agg` có thể tạo **một giá trị rất lớn**. Nếu lấy 1 triệu dòng hàng thành một array rồi gửi qua API:

- Database cần tính và tạo giá trị JSON;
- Client phải nhận, parse và giữ dữ liệu;
- Kết nối truyền tải một payload lớn;
- Chi phí sort tăng nếu có `ORDER BY` trong aggregate;
- Giới hạn bộ nhớ, kích thước giá trị hoặc thời gian request có thể bị chạm.

**Đừng biến “có thể viết thành một JSON” thành yêu cầu luôn trả mọi dữ liệu trong một response.** Hãy lọc, phân trang hoặc chia nhỏ các tập con theo nhu cầu.

### 17.2. Phân trang đúng cấp cha trước khi aggregate

Nếu API lấy trang 20 đơn hàng, nên chọn danh sách đơn trước:

~~~sql
WITH page_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        order_status
    FROM orders
    WHERE customer_id = 1
    ORDER BY ordered_at, order_id
    LIMIT 20
)
SELECT
    o.order_id,
    jsonb_build_object(
        'orderId', o.order_id,
        'items', COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'lineNo', oi.line_no,
                        'quantity', oi.quantity
                    )
                    ORDER BY oi.line_no
                )
                FROM order_items AS oi
                WHERE oi.order_id = o.order_id
            ),
            '[]'::jsonb
        )
    ) AS document
FROM page_orders AS o
ORDER BY o.ordered_at, o.order_id;
~~~

Cách này giới hạn **số hàng cha** trước khi dựng arrays con. Nếu giới hạn sau JOIN với `order_items`, có thể cắt một đơn giữa chừng, dẫn tới document thiếu items hoặc số đơn trên trang không như mong đợi.

Ví dụ trên chỉ minh họa `LIMIT`; hệ thống thật còn cần offset/keyset pagination và khóa sort ổn định để tránh thiếu/trùng khi dữ liệu thay đổi giữa hai trang.

### 17.3. Index cho khóa ngoại và thứ tự dòng

Các index ứng viên PostgreSQL:

~~~sql
CREATE INDEX idx_orders_customer_time
ON orders (customer_id, ordered_at, order_id);

CREATE INDEX idx_order_items_order_line
ON order_items (order_id, line_no);

CREATE INDEX idx_payments_order_id
ON payments (order_id, payment_id);
~~~

Trong schema mẫu, `order_items` đã có `PRIMARY KEY(order_id, line_no)`, nên index `idx_order_items_order_line` **có thể là dư thừa** và không nên tạo thêm chỉ vì thấy ví dụ. Tương tự, hãy kiểm tra index có sẵn, workload đọc/ghi, số lượng bản ghi và kế hoạch trước khi tạo.

Index có thể giúp lấy items/payment theo `order_id` và thứ tự đã định, nhưng không có index nào tự biến việc serialize một triệu phần tử thành miễn phí.

### 17.4. CTE, LATERAL hay JOIN nhóm?

Không có một phương án luôn nhanh nhất:

- `LATERAL` và correlated subquery dễ diễn đạt một mảng con trên mỗi cha; với nhiều cha, optimizer và index quyết định chi phí.
- CTE preaggregate phù hợp khi cần tính tổng hợp theo tập trước khi nối nhiều nhánh con.
- `JOIN + GROUP BY` gọn cho một nhánh một-nhiều, nhưng phải tránh fan-out khi có nhiều nhánh.
- JSON builder diễn ra trong database có thể giảm logic assemble ở ứng dụng, nhưng tăng CPU database.

Đo bằng `EXPLAIN (ANALYZE, BUFFERS)` trong PostgreSQL đối với truy vấn SELECT trên dữ liệu thử. Đánh giá cả **thời gian database và kích thước payload**. Không dựa vào số dòng SQL hoặc giả định JSON trong DB luôn nhanh hơn xử lý ở Java.

### 17.5. Index GIN trên JSONB khi nào?

Nếu database còn **lưu tài liệu JSONB trong một cột** và thường truy vấn containment/path, index GIN có thể hữu ích:

~~~sql
-- Bảng minh họa khác, không thuộc schema orders ở trên:
CREATE TABLE incoming_documents (
    document_id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL
);

CREATE INDEX idx_incoming_payload_gin
ON incoming_documents
USING GIN (payload);
~~~

Đây là index cho **truy vấn dữ liệu JSONB đã lưu**, không tự tăng tốc `jsonb_agg` tạo JSON từ `order_items`. Phải phân biệt xây JSON để trả API với lưu JSON làm nguồn dữ liệu có thể được truy vấn.

## 18. Tính đúng đắn, an toàn và hợp đồng đầu ra

### 18.1. JSON builder không thay constraint

`jsonb_build_object` có thể tạo:

~~~json
{"quantity": -5}
~~~

về mặt cú pháp JSON hợp lệ, nhưng quantity âm có thể vi phạm nghiệp vụ. Bảng quan hệ vẫn nên kiểm soát `CHECK (quantity > 0)`, FK, khóa chính, uniqueness và transaction.

Tạo JSON không làm dữ liệu tự nhiên “hợp lệ hơn” chỉ vì cú pháp JSON đúng.

### 18.2. Không sao chép mọi cột nhạy cảm

Nếu bảng `customers` có email, số điện thoại, thông tin xác thực hoặc dữ liệu nội bộ, dùng `to_jsonb(c)` có thể đưa những trường không nên lộ vào response.

Ưu tiên **danh sách key được phép**:

~~~sql
jsonb_build_object(
    'customerId', c.customer_id,
    'name', c.full_name
)
~~~

Không chọn `SELECT *` hoặc toàn bộ row chỉ để đỡ gõ, trừ khi hợp đồng rõ ràng cho phép công khai tất cả trường.

### 18.3. JSON an toàn khác SQL an toàn

Đúng về tạo JSON:

~~~sql
jsonb_build_object('name', c.full_name)
~~~

nhưng nếu client tạo câu query:

~~~text
SELECT ... WHERE customer_id = <chuỗi nối trực tiếp từ input>
~~~

vẫn có nguy cơ SQL injection. Bind tham số bằng `PreparedStatement` hoặc API tương ứng. Các tên bảng/cột hoặc mệnh đề ORDER BY động cần whitelist vì thường không được bind như giá trị.

### 18.4. Đối tượng rỗng và null phải thống nhất

Một API có thể chọn:

~~~json
{
  "orders": [],
  "address": null,
  "metadata": {}
}
~~~

- `orders=[]`: không có bản ghi đơn nào.
- `address=null`: một thuộc tính được biết nhưng chưa có giá trị.
- `metadata={}`: một object map hiện rỗng.

Không thay cả ba bằng chuỗi rỗng `""` hay chuỗi `"null"`. Client dựa vào kiểu dữ liệu để render và validate.

### 18.5. Timestamp và múi giờ

PostgreSQL `TIMESTAMPTZ` biểu diễn một thời điểm; khi chuyển sang JSON, cách format/offset có thể phụ thuộc quy tắc chuyển kiểu và múi giờ session. Nếu API quy định timestamp ISO 8601 UTC hoặc offset rõ ràng, hãy chuẩn hóa/định dạng một cách nhất quán.

Ví dụ lấy UTC theo một format do ứng dụng quy định:

~~~sql
SELECT
    jsonb_build_object(
        'orderId', order_id,
        'orderedAtUtc',
        to_char(
            ordered_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        )
    ) AS document
FROM orders
WHERE order_id = 1001;
~~~

`to_char` trả TEXT, nên field là JSON string. Việc cố định `Z` là hợp lý ở đây vì đã chuyển sang giờ UTC trước. Nếu cần nanosecond precision, offset gốc hoặc chuẩn khác, phải thiết kế format riêng; không khẳng định cùng biểu thức là yêu cầu bắt buộc cho mọi API.

### 18.6. Determinism và kiểm thử đầu ra

Muốn so sánh JSON giữa các lần chạy, cần quy định:

- Mỗi array có `ORDER BY` ổn định;
- Không phụ thuộc thứ tự key của object;
- Kiểu số/thời gian nhất quán;
- Quy tắc NULL/missing/empty;
- Quy tắc một hàng cha → một object;
- Không fan-out và không mất hàng khi LEFT JOIN;
- Có chính sách duplicate keys cho object maps.

Khi so tài liệu JSON, nên so theo **cấu trúc và giá trị** thay vì chuỗi text có thể khác thứ tự key/khoảng trắng. Với `jsonb` của PostgreSQL, phép so kiểu dữ liệu thường thuận tiện hơn so text format khi contract không yêu cầu một byte sequence cụ thể.

## 19. Đối chiếu các hệ quản trị SQL

Ý tưởng “hàng → object, nhóm hàng → array” có mặt ở nhiều DBMS nhưng cú pháp và kiểu trả về không hoàn toàn tương đương.

### 19.1. PostgreSQL

Các hàm phổ biến:

| Nhiệm vụ | PostgreSQL |
| --- | --- |
| Object từ các cặp key/value | `json_build_object`, `jsonb_build_object` |
| Array từ các giá trị cố định | `json_build_array`, `jsonb_build_array` |
| Array từ nhiều hàng | `json_agg`, `jsonb_agg` |
| Object map từ nhiều hàng | `json_object_agg`, `jsonb_object_agg` |
| Hàng/composite → JSON | `row_to_json`, `to_jsonb` |
| Bỏ thuộc tính null | `json_strip_nulls`, `jsonb_strip_nulls` |
| Mở array thành hàng | `jsonb_array_elements` |
| Đọc key/path | `->`, `->>`, `#>`, `#>>` |
| Lọc hàng đầu vào aggregate | `FILTER (WHERE ...)` |
| Thứ tự phần tử array | `ORDER BY` bên trong `jsonb_agg(...)` |

Ví dụ ngắn:

~~~sql
SELECT COALESCE(
    jsonb_agg(
        jsonb_build_object(
            'orderId', order_id,
            'status', order_status
        )
        ORDER BY order_id
    ),
    '[]'::jsonb
)
FROM orders
WHERE customer_id = 1;
~~~

### 19.2. MySQL

MySQL có các hàm như:

- `JSON_OBJECT(key, value, ...)`.
- `JSON_ARRAY(value, ...)`.
- `JSON_ARRAYAGG(expression)`.
- `JSON_OBJECTAGG(key, value)`.

Ví dụ MySQL cho một đơn:

~~~sql
SELECT JSON_OBJECT(
    'orderId', o.order_id,
    'status', o.order_status,
    'items', COALESCE(
        (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'lineNo', oi.line_no,
                    'quantity', oi.quantity
                )
            )
            FROM order_items AS oi
            WHERE oi.order_id = o.order_id
        ),
        JSON_ARRAY()
    )
) AS document
FROM orders AS o
WHERE o.order_id = 1001;
~~~

Lưu ý:

- MySQL `JSON_ARRAYAGG` không cho một bảo đảm thứ tự phần tử giống cách PostgreSQL viết `ORDER BY` trực tiếp trong `jsonb_agg`. Theo phiên bản MySQL, thứ tự của `JSON_ARRAYAGG` có thể không được xác định; không suy rằng SELECT nguồn có thứ tự là đủ. Nếu API yêu cầu thứ tự cứng, dùng phương pháp/hàm hỗ trợ của đúng engine/phiên bản hoặc sắp xếp ở tầng ứng dụng theo khóa `lineNo`.
- Trong MySQL, không sao chép `FILTER (WHERE ...)` của PostgreSQL vào JSON aggregate nếu cú pháp không hỗ trợ.
- Dùng subquery chỉ đọc `order_items` thật, thay vì LEFT JOIN tạo object toàn NULL khi không có item.
- Các quy tắc về JSON null, duplicate key và kiểu số cần kiểm tra theo MySQL; không áp ngữ nghĩa `jsonb` của PostgreSQL.

### 19.3. SQL Server: FOR JSON PATH

SQL Server thường dựng JSON bằng `FOR JSON PATH`:

~~~sql
-- SQL Server, giả định bảng dbo.orders và dbo.order_items.
SELECT
    o.order_id AS [orderId],
    o.order_status AS [status],
    JSON_QUERY(
        (
            SELECT
                oi.line_no AS [lineNo],
                oi.quantity AS [quantity],
                oi.unit_price AS [unitPrice]
            FROM dbo.order_items AS oi
            WHERE oi.order_id = o.order_id
            ORDER BY oi.line_no
            FOR JSON PATH
        )
    ) AS [items]
FROM dbo.orders AS o
WHERE o.order_id = 1001
FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;
~~~

Ý nghĩa:

- `FOR JSON PATH` tạo JSON từ tập hàng.
- Dùng alias như `[orderId]`, `[unitPrice]` để đặt tên field.
- Subquery `FOR JSON PATH` tạo array items cho đơn.
- `JSON_QUERY` đánh dấu nội dung subquery là một fragment JSON hợp lệ để tránh bị serialize thành **chuỗi JSON đã escape** ở đầu ra ngoài.
- `WITHOUT_ARRAY_WRAPPER` chỉ hợp lý khi outer query thật sự trả **một object duy nhất**; nếu trả nhiều hàng, đầu ra có thể không còn một tài liệu JSON hợp lệ theo kỳ vọng.

SQL Server có quy tắc riêng về việc bỏ các key có SQL NULL theo mặc định và tùy chọn `INCLUDE_NULL_VALUES` để hiện key null. Không coi nó giống hệt PostgreSQL `jsonb_build_object`, nơi key với giá trị null được đưa vào trừ khi được xử lý loại bỏ.

### 19.4. SQLite: JSON1

SQLite hiện đại hỗ trợ các hàm JSON như:

- `json_object(key, value, ...)`;
- `json_array(value, ...)`;
- `json_group_array(value)`;
- `json_group_object(key, value)`;
- `json_extract` và các hàm đọc JSON.

Ví dụ SQLite cho một đơn:

~~~sql
SELECT json_object(
    'orderId', o.order_id,
    'status', o.order_status,
    'items', json(
        COALESCE(
            (
                SELECT json_group_array(
                    json_object(
                        'lineNo', oi.line_no,
                        'quantity', oi.quantity
                    )
                )
                FROM order_items AS oi
                WHERE oi.order_id = o.order_id
            ),
            '[]'
        )
    )
) AS document
FROM orders AS o
WHERE o.order_id = 1001;
~~~

Trong SQLite, JSON có thể được biểu diễn/lưu bằng văn bản và ở các phiên bản mới còn có biến thể JSONB riêng của SQLite; **đừng nhầm SQLite JSONB với PostgreSQL jsonb**.

Một điểm quan trọng: khi nối/đưa một **chuỗi TEXT trông giống JSON** vào `json_object` như một giá trị thường, nó có thể thành chuỗi JSON đã escape thay vì object/array lồng. Dùng các hàm JSON phù hợp hoặc `json(...)` khi muốn diễn giải văn bản là JSON hợp lệ.

Độ sẵn có của tính năng, thứ tự aggregate, hành vi null và tối ưu phụ thuộc phiên bản SQLite. Khi cần array có thứ tự, kiểm tra cú pháp aggregate ORDER BY của đúng phiên bản hoặc dùng hướng an toàn tương ứng; không tự dùng PostgreSQL `FILTER ... ORDER BY` mà không xác minh.

### 19.5. Oracle Database: SQL/JSON functions

Oracle có các hàm SQL/JSON như:

~~~sql
-- Oracle: ví dụ trên bảng orders.
SELECT JSON_OBJECT(
    'orderId' VALUE o.order_id,
    'status' VALUE o.order_status
    RETURNING CLOB
) AS document
FROM orders o
WHERE o.order_id = 1001;
~~~

Tạo mảng từ nhiều hàng:

~~~sql
SELECT JSON_ARRAYAGG(
    JSON_OBJECT(
        'lineNo' VALUE oi.line_no,
        'quantity' VALUE oi.quantity
    )
    ORDER BY oi.line_no
    RETURNING CLOB
) AS items
FROM order_items oi
WHERE oi.order_id = 1001;
~~~

Một số phiên bản Oracle hỗ trợ `RETURNING JSON` hoặc lựa chọn loại dữ liệu khác; `RETURNING CLOB` thường được dùng để tránh giới hạn kích thước chuỗi mặc định ở những ngữ cảnh/phiên bản. Cần kiểm tra kiểu kết quả và khả năng sử dụng `FORMAT JSON`, `NULL ON NULL`/`ABSENT ON NULL` theo phiên bản.

Không sử dụng cú pháp `jsonb_build_object` hoặc `'[]'::jsonb` của PostgreSQL trong Oracle.

### 19.6. SQL/JSON chuẩn và khả năng tương thích

SQL hiện đại có các tên/khái niệm như `JSON_OBJECT`, `JSON_ARRAY`, `JSON_ARRAYAGG` và `JSON_OBJECTAGG` theo SQL/JSON, nhưng:

- Tên hàm, cú pháp cặp key/value và mệnh đề `RETURNING` khác nhau.
- Chế độ NULL/missing có thể có tùy chọn riêng.
- Độ bảo đảm về thứ tự array khác nhau.
- Kiểu dữ liệu trả về là JSON, JSONB, VARCHAR, CLOB, NVARCHAR hoặc kiểu khác tùy engine.
- Hàm tổng hợp trên tập rỗng có hành vi cần kiểm tra.
- Các phiên bản mới của cùng DBMS có thể bổ sung cú pháp SQL/JSON chuẩn.

Đừng chỉ đổi tên `jsonb_agg` thành `JSON_ARRAYAGG` mà bỏ qua các khác biệt về thứ tự, kiểu dữ liệu, empty arrays và xử lý duplicate keys.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Ghép chuỗi `'{"name":"' || name || '"}'` | Sai escaping khi chuỗi có ký tự đặc biệt | Dùng JSON builder |
| Đưa số thành TEXT trước khi tạo JSON | JSON number bị biến thành string | Giữ kiểu số hoặc chọn contract cố ý |
| Nghĩ SQL NULL và JSON null giống hệt | Sai khi kiểm tra missing key | Phân biệt key tồn tại, JSON null, SQL NULL |
| Nghĩ key thiếu và key có null tương đương | Client xử lý sai optional fields | Định nghĩa chính sách null/missing |
| Dùng `jsonb_agg` không ORDER BY | Array thay thứ tự giữa các lần chạy | ORDER BY bên trong aggregate |
| Nghĩ thứ tự key object là hợp đồng | JSONB có thể trình bày khác | Không phụ thuộc key order |
| Dùng COALESCE cho LEFT JOIN nhưng không FILTER | Sinh `[{"id":null}]` | FILTER trên khóa con NOT NULL |
| Dùng `jsonb_agg` không có hàng và mong `[]` | Nhận SQL NULL | COALESCE(..., '[]'::jsonb) |
| Trả `'[]'` như chuỗi JSON | Client nhận string, không phải array | Dùng kiểu JSONB hoặc hàm JSON |
| JOIN items và payments trước khi gom | Fan-out 2×2, trùng cả array và SUM | Aggregate từng nhánh riêng |
| Dùng DISTINCT để che fan-out | Có thể mất hàng hợp lệ, sai tổng | Sửa cardinality và group level |
| GROUP BY nhầm cấp con | Một đơn có nhiều document, hoặc thiếu rows | Một object trên mỗi khóa cha |
| Mất khách không có đơn | Bắt đầu từ bảng con hoặc WHERE sai | Lấy bảng cha làm nguồn, LEFT JOIN |
| Dùng WHERE lọc bảng con sau LEFT JOIN | Loại hàng cha không có con | Đặt điều kiện thích hợp vào ON/FILTER |
| Dùng object_agg với key trùng | Mất dữ liệu từng dòng | GROUP BY key trước hoặc dùng array |
| Dùng object_agg với key NULL | Lỗi hoặc hành vi không mong muốn | Chuẩn hóa/lọc key |
| Đổi giá lịch sử theo products.list_price | Sai subtotal đơn cũ | Dùng giá snapshot order_items |
| Tạo JSON toàn bộ bảng bằng to_jsonb(table) | Lộ cột nhạy cảm hoặc không đúng API | Whitelist field |
| Phân trang sau JOIN hàng con | Cắt một đơn ở giữa | Phân trang tập cha trước |
| Tạo một array khổng lồ cho mọi row | CPU/memory/network lớn | Pagination, batch, scope hợp lý |
| Dùng index JSONB để kỳ vọng tăng tốc JSON aggregate | Sai mục đích index | Index khóa JOIN/filter trên bảng nguồn |
| Dùng cú pháp PostgreSQL trên MySQL/SQLite | Sai cú pháp, sai order/null semantics | Viết theo dialect |
| Quên JSON_QUERY của SQL Server với JSON fragment | Nested JSON bị escape thành chuỗi | Dùng JSON_QUERY đúng ngữ cảnh |
| Coi JSON builder là validation nghiệp vụ | Sinh JSON hợp lệ chứa dữ liệu sai | Duy trì constraint/transaction |
| So JSON string để kiểm thử cấu trúc | Sai khi object key order khác | So cấu trúc/giá trị |
| Trả dữ liệu timestamp không chuẩn hóa | Client khó xác định múi giờ | Hợp đồng thời gian/định dạng rõ |

## 21. Bài tập thực hành có đáp án

Các bài dùng schema PostgreSQL `customers`, `products`, `orders`, `order_items`, `payments` ở mục 3. Các SELECT không sửa dữ liệu. Với những bài tạo bảng/chèn bổ sung để thử tình huống fan-out, dùng transaction rồi `ROLLBACK` hoặc môi trường thực hành riêng.

### Bài 1 — Dựng object đơn hàng

Tạo object có `orderId` và `status` của đơn 1001.

**Đáp án:**

~~~sql
SELECT jsonb_build_object(
    'orderId', order_id,
    'status', order_status
) AS document
FROM orders
WHERE order_id = 1001;
~~~

Kết quả:

~~~json
{"orderId": 1001, "status": "PAID"}
~~~

### Bài 2 — Dựng object khách lồng trong đơn

Trả `orderId` và object `customer` có `customerId`, `name`.

**Đáp án:**

~~~sql
SELECT jsonb_build_object(
    'orderId', o.order_id,
    'customer', jsonb_build_object(
        'customerId', c.customer_id,
        'name', c.full_name
    )
) AS document
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

### Bài 3 — Chỉ định kiểu số

Trong `jsonb_build_object('quantity', oi.quantity)`, `quantity` nhận JSON number hay string?

**Đáp án:** nếu `oi.quantity` là INTEGER SQL, JSON builder tạo **JSON number**. Nếu ép trước sang TEXT, nó thành JSON string. Kiểu cần đúng hợp đồng API.

### Bài 4 — Phân biệt key vắng mặt và null

Hai document:

~~~json
{"city": null}
~~~

và:

~~~json
{}
~~~

có giống nhau không?

**Đáp án:** không. Document thứ nhất có key `city` với giá trị JSON null; thứ hai không có key. Có thể dùng `? 'city'` trong PostgreSQL để kiểm tra sự hiện diện của key.

### Bài 5 — Bỏ city null

Lấy khách Dũng (4) và dựng object không có key `city` nếu NULL.

**Đáp án:**

~~~sql
SELECT jsonb_strip_nulls(
    jsonb_build_object(
        'customerId', customer_id,
        'name', full_name,
        'city', city
    )
)
FROM customers
WHERE customer_id = 4;
~~~

Kết quả có `customerId` và `name` nhưng không có `city`.

### Bài 6 — Tạo mảng cố định

Tạo `["NEW","PENDING","PAID"]` bằng PostgreSQL.

**Đáp án:**

~~~sql
SELECT jsonb_build_array(
    'NEW', 'PENDING', 'PAID'
);
~~~

### Bài 7 — Tạo array SKU của đơn 1001

**Đáp án:**

~~~sql
SELECT jsonb_agg(
    p.sku ORDER BY oi.line_no
) AS skus
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1001;
~~~

Kết quả `["NOTE-01","PEN-02"]`.

### Bài 8 — Tại sao ORDER BY phải nằm trong jsonb_agg?

Một báo cáo dùng array cho dòng hàng theo `line_no`. Có thể chỉ đặt `ORDER BY` ở SELECT ngoài cùng không?

**Đáp án:** `ORDER BY` của SELECT ngoài sắp xếp **các hàng kết quả**, không tự sắp phần tử bên trong array. Cần:

~~~sql
jsonb_agg(
    jsonb_build_object('lineNo', oi.line_no)
    ORDER BY oi.line_no
)
~~~

### Bài 9 — Tạo array các object

Dựng array dòng hàng đơn 1003 với `lineNo`, `quantity` và `unitPrice`.

**Đáp án:**

~~~sql
SELECT jsonb_agg(
    jsonb_build_object(
        'lineNo', line_no,
        'quantity', quantity,
        'unitPrice', unit_price
    )
    ORDER BY line_no
) AS items
FROM order_items
WHERE order_id = 1003;
~~~

Kết quả có hai phần tử với số lượng 4/1 và giá 10/180.

### Bài 10 — Không có hàng thì array gì?

Đơn 1004 không có `order_items`. `jsonb_agg(...)` trả gì và làm sao để trả `[]`?

**Đáp án:** aggregate trên tập không có hàng trả **SQL NULL**. Dùng `COALESCE(..., '[]'::jsonb)`.

~~~sql
SELECT COALESCE(
    jsonb_agg(line_no ORDER BY line_no),
    '[]'::jsonb
)
FROM order_items
WHERE order_id = 1004;
~~~

### Bài 11 — LEFT JOIN sinh phần tử giả

Vì sao `LEFT JOIN order_items` rồi `jsonb_agg(jsonb_build_object('lineNo', oi.line_no))` có thể cho `[{"lineNo":null}]` cho đơn 1004?

**Đáp án:** LEFT JOIN tạo một hàng null-extended để giữ hàng cha. Hàm dựng object vẫn tạo một object từ hàng đó. Phải dùng `FILTER (WHERE oi.order_id IS NOT NULL)` và COALESCE sang array rỗng.

### Bài 12 — Một array trên mỗi khách

Viết truy vấn giữ cả khách Dũng chưa có đơn.

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    COALESCE(
        jsonb_agg(
            o.order_id ORDER BY o.order_id
        ) FILTER (
            WHERE o.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ) AS order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Khách 4 có `[]`.

### Bài 13 — Tính subtotal đúng

Đơn 1003 có 4 bút giá 10 và 1 túi giá 180. Tổng tiền là bao nhiêu, và SQL nào đúng?

**Đáp án:** `4×10 + 1×180 = 220`.

~~~sql
SELECT SUM(quantity * unit_price) AS subtotal
FROM order_items
WHERE order_id = 1003;
~~~

Không dùng giá niêm yết `products.list_price` nếu cần giữ số tiền giao dịch lịch sử.

### Bài 14 — Chỉ dùng một JOIN cho một mảng con

Dựng object đơn 1004 có `items=[]` và `subtotal=0`.

**Đáp án:**

~~~sql
SELECT jsonb_build_object(
    'orderId', o.order_id,
    'items', COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'lineNo', oi.line_no,
                'quantity', oi.quantity
            )
            ORDER BY oi.line_no
        ) FILTER (
            WHERE oi.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ),
    'subtotal', COALESCE(
        SUM(oi.quantity * oi.unit_price),
        0::NUMERIC
    )
)
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.order_id = 1004
GROUP BY o.order_id;
~~~

### Bài 15 — Phát hiện fan-out

Đơn 1001 có 2 dòng hàng và 2 payment. JOIN trực tiếp cả hai bảng con trả mấy hàng? Nếu SUM tiền dòng hàng trên JOIN, giá trị có thể là bao nhiêu?

**Đáp án:** `2 × 2 = 4` hàng. `SUM(quantity * unit_price)` từ JOIN này thành **260** thay vì 130 vì mỗi item xuất hiện hai lần.

### Bài 16 — Sửa fan-out

Nêu giải pháp nếu JSON cần đồng thời `items` và `payments`.

**Đáp án:** tổng hợp `order_items` thành một hàng trên mỗi `order_id` trong CTE hoặc LATERAL riêng, tổng hợp `payments` trong nhánh khác, sau đó LEFT JOIN hai kết quả đó về `orders`. Không tổng hợp hai arrays trực tiếp trên kết quả JOIN nhiều-một của cả hai nhánh.

### Bài 17 — Object map theo SKU

Tạo `{"NOTE-01":2,"PEN-02":3}` cho đơn 1001.

**Đáp án:**

~~~sql
SELECT jsonb_object_agg(
    p.sku, oi.quantity
) AS quantity_map
FROM order_items AS oi
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE oi.order_id = 1001;
~~~

Không dựa vào thứ tự các key khi serialize object.

### Bài 18 — Duplicate key trong object_agg

Nếu hai dòng có cùng SKU, dùng `jsonb_object_agg(sku, qty)` trực tiếp có giữ được cả hai dòng không?

**Đáp án:** không. Object JSONB không lưu hai thành viên phân biệt cùng key; dữ liệu một dòng có thể bị che. Nếu cần tổng quantity, `GROUP BY sku` rồi `SUM(qty)` trước; nếu cần giữ từng dòng, dùng array các object.

### Bài 19 — Tạo {} từ tập rỗng

Một truy vấn `jsonb_object_agg` không có hàng, API cần object map rỗng. Viết fallback.

**Đáp án:**

~~~sql
COALESCE(
    jsonb_object_agg(sku, quantity),
    '{}'::jsonb
)
~~~

Chỉ là biểu thức minh họa trong truy vấn có các cột `sku` và `quantity`. `'{}'::jsonb` là object rỗng, không phải array rỗng.

### Bài 20 — Chỉ giữ đơn PAID nhưng không bỏ khách

Muốn mọi khách, mỗi người có array `paidOrderIds` (khách không có đơn PAID vẫn có `[]`). Làm sao tránh biến LEFT JOIN thành INNER JOIN?

**Đáp án:**

~~~sql
SELECT
    c.customer_id,
    COALESCE(
        jsonb_agg(
            o.order_id ORDER BY o.order_id
        ) FILTER (
            WHERE o.order_id IS NOT NULL
        ),
        '[]'::jsonb
    ) AS paid_order_ids
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Đặt điều kiện trạng thái trong `ON` và lọc null-extended rows trong aggregate.

### Bài 21 — to_jsonb và tên cột

`to_jsonb(c)` trên bảng `customers` sẽ dùng key `customer_id` hay `customerId`?

**Đáp án:** theo tên cột nguồn, thường là `customer_id`. Muốn key `customerId`, dùng `jsonb_build_object` hoặc một subquery với quoted alias `AS "customerId"` trước khi `to_jsonb`.

### Bài 22 — JSON_QUERY ở SQL Server

Trong SQL Server `FOR JSON PATH`, vì sao có thể cần `JSON_QUERY(subquery_for_json)` cho mảng items lồng?

**Đáp án:** để engine nhận nội dung là một **JSON fragment**, thay vì một chuỗi ký tự JSON bị escape lần nữa. Đúng cách diễn đạt phụ thuộc ngữ cảnh SQL Server và phiên bản hỗ trợ.

### Bài 23 — Thứ tự MySQL JSON_ARRAYAGG

Có được sao chép PostgreSQL `jsonb_agg(... ORDER BY line_no)` nguyên văn sang MySQL `JSON_ARRAYAGG` và giả định thứ tự được bảo đảm không?

**Đáp án:** không. Kiểm tra cú pháp và bảo đảm thứ tự của đúng phiên bản MySQL; nếu cần thứ tự cứng, dùng chiến lược phù hợp hoặc sắp xếp phần tử ở ứng dụng theo `lineNo`.

### Bài 24 — Phân trang JSON nhiều cấp

API cần 20 đơn hàng đầu tiên, mỗi đơn chứa tất cả dòng hàng. Nên `LIMIT 20` sau JOIN items hay trước khi JOIN?

**Đáp án:** chọn **20 đơn hàng cha** bằng CTE/subquery với ORDER BY ổn định trước, rồi dựng arrays items của các đơn đó. Giới hạn sau JOIN có thể cắt ngang một đơn và làm số đơn trên trang sai.

### Bài 25 — Thiết kế đầu ra chuẩn

Một API muốn trả tài liệu cho mỗi đơn với `orderId`, `status`, `items`, `payments`, `subtotal`; không được nhân bản, không có con thì mảng rỗng, thứ tự items theo line_no. Hãy mô tả các bước.

**Gợi ý đáp án:**

1. Truy vấn tập `orders` cần xuất (lọc/pagination ở cấp cha).
2. Nhánh `order_items + products`: `GROUP BY order_id`, `jsonb_agg(object ORDER BY line_no)`, `SUM(quantity*unit_price)`.
3. Nhánh `payments`: `GROUP BY order_id`, `jsonb_agg(object ORDER BY payment_id)`.
4. LEFT JOIN hai kết quả vào `orders` theo `order_id`.
5. Dùng `COALESCE(items,'[]'::jsonb)`, `COALESCE(payments,'[]'::jsonb)`, `COALESCE(subtotal,0)`.
6. Dùng `jsonb_build_object` để tạo object cuối, không ghép chuỗi thủ công.
7. Kiểm tra hàng có 0 items, nhiều items, nhiều payments và dữ liệu có NULL.
8. Giữ các ràng buộc quan hệ, quyền và hợp đồng JSON rõ ràng.

## 22. Checklist triển khai

Trước khi trả JSON được tổng hợp từ dữ liệu quan hệ, hãy xác định:

1. **Đơn vị đầu ra:** Mỗi object tương ứng một hàng khách, đơn hay sản phẩm?
2. **Lực lượng quan hệ:** Quan hệ con là 0:1, 1:N hay N:M?
3. **Cấp aggregate:** Mỗi `GROUP BY` có thực sự gom đúng khóa cha?
4. **Nhiều nhánh con:** Đã tiền tổng hợp để tránh phép nhân `N × M` chưa?
5. **Thứ tự array:** Có `ORDER BY` trong aggregate theo khóa đủ ổn định?
6. **Array rỗng:** Có trả `[]` khi không có hàng con?
7. **LEFT JOIN:** Có loại hàng null-extended trước `jsonb_agg` bằng FILTER phù hợp?
8. **Kiểu dữ liệu:** Số, boolean, timestamp và string đúng contract JSON?
9. **NULL/missing:** Có chính sách rõ cho field vắng mặt, JSON null, array rỗng?
10. **Object map:** Key có không NULL, không trùng hoặc có quy tắc hợp nhất?
11. **Giá trị tính toán:** Có SUM trên bảng đã bị fan-out không?
12. **Giá trị lịch sử:** Dùng snapshot unit_price của dòng hàng hay giá hiện tại?
13. **Phân trang:** Đã giới hạn danh sách cha trước khi tổng hợp con?
14. **Kích thước:** Có tránh tạo document quá lớn?
15. **Index:** Có index phù hợp với khóa JOIN, bộ lọc, thứ tự?
16. **Bảo mật:** Có whitelist field và giới hạn quyền truy cập dữ liệu nguồn?
17. **An toàn SQL:** Các tham số động có được bind, key/cột động có whitelist?
18. **Dialect:** Cú pháp MySQL, SQL Server, SQLite, Oracle đã đúng phiên bản?
19. **Kiểm thử:** Có kiểm tra các ca 0/1/N hàng con, dữ liệu có NULL, thứ tự và Unicode?
20. **Hợp đồng API:** Đã định nghĩa tên key, kiểu field, empty arrays, version schema và định dạng ngày giờ?

## 23. Tổng kết

**Tạo đối tượng, mảng JSON và tổng hợp dữ liệu quan hệ** là quá trình đổi hình dạng dữ liệu có cấu trúc:

- `jsonb_build_object`: tạo **một object** từ các cặp key–value.
- `jsonb_build_array`: tạo **một array** từ các giá trị được viết sẵn.
- `jsonb_agg`: biến **nhiều hàng** thành array; dùng `ORDER BY` bên trong aggregate để xác định thứ tự phần tử.
- `jsonb_object_agg`: biến nhiều cặp key–value thành **object map**, cần xử lý khóa NULL/trùng một cách có chủ đích.
- `COALESCE(...,'[]'::jsonb)` hoặc `'{}'::jsonb`: tạo đúng dạng rỗng khi aggregate không có hàng.
- `FILTER`: loại các hàng null-extended từ LEFT JOIN trước khi tạo JSON array.
- CTE/`LATERAL`/subquery: tổng hợp **mỗi quan hệ con ở đúng cấp**, rồi ghép lại thành object cha nhiều tầng.

Điểm dễ sai nhất không phải cú pháp JSON mà là **lực lượng kết quả sau JOIN**. Một đơn có hai dòng hàng và hai lần thanh toán sẽ cho bốn hàng nếu JOIN cả hai nhánh con trước khi tổng hợp; các arrays và SUM có thể bị nhân bản. Hãy **gom items riêng, gom payments riêng, rồi nối về order**.

Các DBMS có cùng mục tiêu nhưng khác cú pháp: PostgreSQL dùng `jsonb_*`, MySQL dùng `JSON_OBJECT/JSON_ARRAYAGG`, SQL Server có `FOR JSON PATH`, SQLite có `json_object/json_group_array`, còn Oracle có hệ hàm SQL/JSON. Đặc biệt phải xác minh quy tắc về **thứ tự array, null, empty result và JSON fragment lồng nhau** theo đúng engine.

**Nguyên tắc cốt lõi:** *một thực thể cha tạo một object; những thực thể con tạo một array có thứ tự; các nhánh con được tổng hợp riêng trước khi ghép; kết quả rỗng phải giữ đúng kiểu JSON đã công bố*.
