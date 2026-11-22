# JSON_ARRAYAGG, JSON_OBJECTAGG và đặc điểm kết quả

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Dùng JSON_ARRAYAGG để gom nhiều hàng thành một JSON array.
- Dùng JSON_OBJECTAGG để tạo JSON object từ các cặp key/value.
- Kết hợp JSON aggregation với GROUP BY, JOIN và các hàm JSON khác.
- Hiểu cách hai hàm xử lý NULL, tập kết quả rỗng và khóa trùng.
- Tránh phụ thuộc vào thứ tự không được bảo đảm của kết quả tổng hợp.
- Tạo kết quả JSON lồng nhau cho API và báo cáo.
- Chọn cách khử trùng lặp, kiểm soát thứ tự và kiểm tra kết quả phù hợp với phiên bản MySQL.

MySQL có thể tổng hợp nhiều hàng quan hệ thành một cấu trúc JSON ngay trong câu SQL. JSON_ARRAYAGG tạo một mảng từ các giá trị của nhiều hàng; JSON_OBJECTAGG tạo một object từ các cặp khóa và giá trị. Hai hàm này hữu ích khi API cần trả về một đơn hàng kèm danh sách dòng hàng, một danh mục kèm các sản phẩm, hoặc một người dùng kèm bản đồ thiết lập.

Tuy nhiên, JSON aggregation có một số đặc điểm khác GROUP_CONCAT: thứ tự phần tử, khóa trùng, NULL và tập kết quả rỗng cần được hiểu rõ. Nếu bỏ qua các quy tắc này, kết quả có thể thay đổi theo kế hoạch thực thi hoặc chứa dữ liệu không như mong đợi.

Hai hàm JSON aggregation có từ MySQL 5.7.22. CTE yêu cầu MySQL 8.0 trở lên; khả năng dùng JSON_ARRAYAGG và JSON_OBJECTAGG như window function có từ MySQL 8.0.14. Các ví dụ window trong bài cần phiên bản 8.0.14 trở lên.

## 1. JSON_ARRAYAGG: gom nhiều hàng thành một mảng

### 1.1. Cú pháp và ý nghĩa

Cú pháp tổng hợp nhóm:

~~~sql
JSON_ARRAYAGG(expr)
~~~

Hàm đánh giá expr trên từng hàng trong nhóm và đưa các giá trị thành phần tử của một JSON array.

Ví dụ bảng sản phẩm:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id),
    KEY idx_product_category (category_id)
) ENGINE = InnoDB;

INSERT INTO product (category_id, product_name, unit_price)
VALUES
    (10, 'Bàn phím cơ', 1250000.00),
    (10, 'Chuột không dây', 450000.00),
    (10, 'Lót chuột', 120000.00),
    (20, 'Màn hình 27 inch', 5200000.00);
~~~

Gom tên sản phẩm theo danh mục:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS product_names
FROM product
GROUP BY category_id;
~~~

MySQL trả về một result set gồm một hàng cho mỗi category_id. Nếu lớp ứng dụng đóng gói các hàng đó thành JSON response, hình dạng có thể như sau:

~~~json
[
  {
    "category_id": 10,
    "product_names": [
      "Bàn phím cơ",
      "Chuột không dây",
      "Lót chuột"
    ]
  },
  {
    "category_id": 20,
    "product_names": [
      "Màn hình 27 inch"
    ]
  }
]
~~~

Đây là hình dạng minh họa. Thứ tự các hàng trả về bởi SELECT và thứ tự phần tử bên trong array không được bảo đảm nếu không có cơ chế sắp xếp được hỗ trợ.

### 1.2. Có thể tổng hợp biểu thức, không chỉ một cột

expr có thể là một biểu thức SQL hoặc một JSON value. Điều này cho phép tạo mảng object:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'productId', product_id,
            'name', product_name,
            'price', unit_price,
            'active', is_active
        )
    ) AS products
FROM product
GROUP BY category_id;
~~~

Kết quả mỗi phần tử là một JSON object, không phải chuỗi ghép thủ công:

~~~json
[
  {
    "category_id": 10,
    "products": [
      {
        "productId": 1,
        "name": "Bàn phím cơ",
        "price": 1250000.00,
        "active": 1
      }
    ]
  }
]
~~~

Các giá trị SQL được chuyển thành kiểu JSON tương ứng. Chuỗi trở thành JSON string, số trở thành JSON number, NULL trở thành JSON null. Khi dùng BOOLEAN trong MySQL, kiểu lưu trữ thực tế là TINYINT(1), nên giá trị có thể xuất hiện dưới dạng 0 hoặc 1; nếu hợp đồng API yêu cầu true/false rõ ràng, hãy tạo biểu thức JSON phù hợp và kiểm tra kết quả thực tế.

### 1.3. Giá trị NULL trong array

Nếu expr của một hàng là SQL NULL, JSON_ARRAYAGG giữ vị trí đó bằng JSON null:

~~~sql
SELECT JSON_ARRAYAGG(value_text) AS values_json
FROM (
    SELECT 'alpha' AS value_text
    UNION ALL
    SELECT NULL
    UNION ALL
    SELECT 'gamma'
) AS source_rows;
~~~

Kết quả có dạng:

~~~json
["alpha", null, "gamma"]
~~~

Hàm không tự loại bỏ các hàng có giá trị NULL. Nếu muốn bỏ chúng, lọc trước khi tổng hợp:

~~~sql
WITH source_rows AS (
    SELECT 'alpha' AS value_text
    UNION ALL
    SELECT NULL
    UNION ALL
    SELECT 'gamma'
)
SELECT JSON_ARRAYAGG(value_text) AS values_json
FROM source_rows
WHERE value_text IS NOT NULL;
~~~

Nếu NULL mang ý nghĩa “không có dữ liệu” và cần được giữ đúng vị trí, hãy để JSON null. Nếu muốn danh sách chỉ chứa giá trị có thật, lọc rõ ràng bằng WHERE.

### 1.4. Tập đầu vào rỗng

Khi một aggregate query không có hàng đầu vào, JSON_ARRAYAGG trả về SQL NULL, không tự trả về array rỗng:

~~~sql
SELECT JSON_ARRAYAGG(product_name) AS products
FROM product
WHERE category_id = 999;
~~~

Kết quả là NULL.

Nếu API yêu cầu luôn trả về mảng, kể cả khi không có phần tử, dùng COALESCE:

~~~sql
SELECT
    COALESCE(
        JSON_ARRAYAGG(product_name),
        JSON_ARRAY()
    ) AS products
FROM product
WHERE category_id = 999;
~~~

Kết quả:

~~~json
[]
~~~

Với truy vấn có GROUP BY, một nhóm không có hàng thường không xuất hiện trong kết quả. Nếu cần trả về cả danh mục không có sản phẩm, phải bắt đầu từ bảng CATEGORY rồi LEFT JOIN hoặc dùng correlated subquery; không thể mong GROUP BY tự sinh nhóm rỗng.

## 2. JSON_OBJECTAGG: tạo object từ các cặp key/value

### 2.1. Cú pháp và ý nghĩa

Cú pháp:

~~~sql
JSON_OBJECTAGG(key, value)
~~~

Hàm tạo một JSON object. Mỗi hàng cung cấp một cặp khóa và giá trị. Key được chuyển thành tên thuộc tính dạng chuỗi của JSON object. Vì vậy, các giá trị key có kiểu khác nhau nhưng chuyển thành cùng chuỗi, ví dụ số 1 và chuỗi '1', có thể tạo cùng tên thuộc tính và gây trùng key.

Ví dụ bảng thiết lập:

~~~sql
CREATE TABLE user_setting (
    setting_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    setting_key VARCHAR(80) NOT NULL,
    setting_value VARCHAR(500) NULL,
    PRIMARY KEY (setting_id),
    KEY idx_user_setting_user (user_id)
) ENGINE = InnoDB;

INSERT INTO user_setting (user_id, setting_key, setting_value)
VALUES
    (101, 'theme', 'dark'),
    (101, 'language', 'vi'),
    (101, 'page_size', '50'),
    (102, 'theme', 'light'),
    (102, 'language', 'en');
~~~

Tạo object thiết lập cho mỗi người dùng:

~~~sql
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM user_setting
GROUP BY user_id;
~~~

MySQL trả về một result set gồm một hàng cho mỗi user_id. Nếu lớp ứng dụng đóng gói các hàng đó thành JSON response, hình dạng có thể như sau:

~~~json
[
  {
    "user_id": 101,
    "settings": {
      "theme": "dark",
      "language": "vi",
      "page_size": "50"
    }
  },
  {
    "user_id": 102,
    "settings": {
      "theme": "light",
      "language": "en"
    }
  }
]
~~~

JSON object phù hợp khi mỗi key có một giá trị trong phạm vi nhóm, ví dụ một người dùng có một giá trị theme hoặc một mã cấu hình ánh xạ đến một thiết lập.

### 2.2. Key không được NULL

Key của JSON_OBJECTAGG không được NULL. Nếu một hàng đưa key NULL vào hàm, MySQL phát sinh lỗi thay vì tạo thuộc tính có tên null.

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value)
FROM user_setting;
~~~

Vì setting_key được khai báo NOT NULL trong ví dụ nên không phát sinh lỗi này. Nếu nguồn dữ liệu cho phép NULL, hãy lọc hoặc xử lý rõ:

~~~sql
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM imported_user_setting
WHERE setting_key IS NOT NULL
GROUP BY user_id;
~~~

Không dùng COALESCE(key, '') một cách máy móc. Nhiều hàng key NULL sẽ bị đổi thành cùng một key rỗng và tạo ra xung đột. Chỉ ánh xạ NULL sang một tên thay thế nếu nghiệp vụ xác định tên đó có ý nghĩa và duy nhất.

### 2.3. Value có thể là NULL

Khác với key, value có thể là NULL. Giá trị đó được biểu diễn thành JSON null:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM (
    SELECT 'theme' AS setting_key, 'dark' AS setting_value
    UNION ALL
    SELECT 'backup_email', NULL
) AS source_rows;
~~~

Kết quả:

~~~json
{
  "theme": "dark",
  "backup_email": null
}
~~~

JSON null khác với việc không có thuộc tính. Client có thể phân biệt object có key với value null và object không chứa key đó. Hãy chọn cách biểu diễn theo hợp đồng API.

### 2.4. Tập đầu vào rỗng

Khi không có hàng đầu vào, JSON_OBJECTAGG trả về SQL NULL:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value)
FROM user_setting
WHERE user_id = 999;
~~~

Nếu cần object rỗng:

~~~sql
SELECT
    COALESCE(
        JSON_OBJECTAGG(setting_key, setting_value),
        JSON_OBJECT()
    ) AS settings
FROM user_setting
WHERE user_id = 999;
~~~

Kết quả là:

~~~json
{}
~~~

## 3. Khóa trùng trong JSON_OBJECTAGG

Đây là đặc điểm quan trọng nhất cần kiểm soát khi dùng JSON_OBJECTAGG.

Một JSON object chỉ nên có một giá trị cho mỗi tên thuộc tính. Nếu nhiều hàng trong cùng nhóm tạo ra cùng key, MySQL xử lý khóa trùng theo quy tắc **giá trị được xử lý sau cùng sẽ thắng**.

Ví dụ:

~~~sql
SELECT JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM (
    SELECT 'theme' AS setting_key, 'light' AS setting_value
    UNION ALL
    SELECT 'theme', 'dark'
) AS duplicate_keys;
~~~

Kết quả sẽ chỉ giữ một thuộc tính theme. Tuy nhiên, với aggregate thông thường, thứ tự hàng đầu vào không được bảo đảm. Do đó không nên dựa vào việc hàng light hay dark luôn được xử lý cuối cùng.

### 3.1. Vì sao kết quả có thể không ổn định?

Thứ tự xử lý hàng có thể thay đổi khi:

- Optimizer chọn execution plan khác.
- Index hoặc thống kê được cập nhật.
- Dữ liệu được phân vùng hoặc phân phối lại.
- Truy vấn chạy trên phiên bản MySQL khác.
- Cách join hoặc materialize derived table thay đổi.

Nếu key trùng, kết quả object có thể giữ giá trị khác nhau giữa các lần chạy dù dữ liệu nguồn không đổi. ORDER BY ở truy vấn ngoài không kiểm soát thứ tự các hàng đã đi vào aggregate.

### 3.2. Bảo đảm một key duy nhất trước khi tổng hợp

Cách tốt nhất là thiết kế dữ liệu sao cho key duy nhất trong phạm vi nhóm:

~~~sql
ALTER TABLE user_setting
    ADD UNIQUE KEY uq_user_setting_key (user_id, setting_key);
~~~

Trước khi thêm UNIQUE, phải kiểm tra và xử lý các key trùng hiện có. Ràng buộc này bảo đảm mỗi user chỉ có một hàng cho mỗi setting_key.

Nếu dữ liệu có lịch sử nhiều phiên bản và cần chọn bản mới nhất, hãy khử trùng lặp trước khi gọi JSON_OBJECTAGG.

Ví dụ bảng lịch sử có updated_at và setting_id:

~~~sql
WITH ranked_settings AS (
    SELECT
        user_id,
        setting_key,
        setting_value,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, setting_key
            ORDER BY updated_at DESC, setting_id DESC
        ) AS rn
    FROM user_setting_history
)
SELECT
    user_id,
    JSON_OBJECTAGG(setting_key, setting_value) AS settings
FROM ranked_settings
WHERE rn = 1
GROUP BY user_id;
~~~

ROW_NUMBER chọn đúng một hàng cho mỗi cặp user_id và setting_key. updated_at DESC chọn phiên bản mới nhất; setting_id DESC là tie-breaker khi hai bản ghi có cùng thời điểm. Điều kiện rn = 1 làm cho mỗi key chỉ xuất hiện một lần trước khi tổng hợp.

Không dùng MAX(setting_value) hoặc MIN(setting_value) để thay thế quy tắc “bản ghi mới nhất” nếu chuỗi giá trị không có thứ tự nghiệp vụ tương ứng. Hãy xác định rõ cột thời gian và tie-breaker.

## 4. Thứ tự phần tử của JSON_ARRAYAGG

### 4.1. Aggregate thông thường không bảo đảm thứ tự

JSON_ARRAYAGG(expr) tạo mảng từ các hàng được tổng hợp, nhưng thứ tự phần tử trong array của aggregate thông thường là không xác định. Không dựa vào thứ tự vật lý của bảng, thứ tự index hoặc một ORDER BY ở nơi không bảo đảm thứ tự đầu vào của aggregate.

Ví dụ:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS products
FROM product
GROUP BY category_id;
~~~

Không thể cam kết phần tử đầu tiên luôn là sản phẩm có product_id nhỏ nhất. Nếu thứ tự là một phần của hợp đồng API, phải thiết kế truy vấn có cơ chế thứ tự rõ ràng.

Cú pháp JSON_ARRAYAGG không có mệnh đề ORDER BY bên trong dấu ngoặc như một số hàm tổng hợp chuỗi. Việc viết ORDER BY ở truy vấn ngoài chỉ sắp xếp các nhóm kết quả, không sắp xếp phần tử bên trong từng JSON array.

### 4.2. Window function không tạo cam kết thứ tự cho array

Từ MySQL 8.0.14, JSON_ARRAYAGG có thể được dùng như window function. Có thể dùng PARTITION BY để tính một array theo từng nhóm và gắn kết quả đó vào từng hàng trong nhóm:

~~~sql
SELECT
    order_id,
    line_no,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'lineNo', line_no,
            'productId', product_id,
            'name', product_name,
            'quantity', quantity
        )
    ) OVER (
        PARTITION BY order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS items_for_order
FROM order_item;
~~~

Khung ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING yêu cầu mỗi hàng trong partition nhìn thấy toàn bộ các hàng của đơn. Window function trả về một kết quả cho mỗi hàng, nên cùng một array được lặp lại trên các hàng thuộc cùng order_id.

**Điểm quan trọng:** MySQL vẫn mô tả thứ tự phần tử của JSON_ARRAYAGG là không xác định, kể cả khi hàm được dùng như window function. ORDER BY trong OVER xác định thứ tự cửa sổ và frame, nhưng không phải cam kết được tài liệu hóa về thứ tự phần tử của JSON array. Vì vậy, không dùng window này để bảo đảm mảng được sắp theo line_no.

Nếu thứ tự phần tử là một phần bắt buộc của hợp đồng API, hãy lấy các hàng bằng truy vấn quan hệ có ORDER BY rõ ràng rồi tạo array trong ứng dụng. Ví dụ:

~~~sql
SELECT
    line_no,
    product_id,
    product_name,
    quantity
FROM order_item
WHERE order_id = 1001
ORDER BY line_no;
~~~

Khóa ghép (order_id, line_no) giúp line_no duy nhất trong mỗi đơn. Ứng dụng có thể đọc các hàng theo thứ tự này và tuần tự hóa thành JSON array. Không dựa vào thứ tự vật lý, index hoặc ORDER BY trong subquery để ép JSON_ARRAYAGG sắp xếp phần tử.

JSON_ARRAYAGG cũng không có tùy chọn DISTINCT trong cú pháp aggregate. Nếu muốn loại giá trị trùng, hãy khử trùng lặp ở derived table hoặc CTE trước khi tổng hợp.

### 4.3. Không nhầm thứ tự object với thứ tự array

JSON object là tập thuộc tính theo tên; thứ tự thành viên của object không nên được dùng làm hợp đồng nghiệp vụ. JSON array là một dãy có thứ tự, nên thứ tự phần tử có thể mang ý nghĩa.

Ví dụ:

- Danh sách các dòng đơn hàng nên là array và có thể cần sắp xếp theo line_no.
- Bản đồ thiết lập theo setting_key phù hợp với object; client truy cập bằng key thay vì vị trí.
- Danh sách các trạng thái theo thứ tự ưu tiên nên là array nếu thứ tự là quan trọng.

Không dùng JSON_OBJECTAGG để thay thế một danh sách mà các phần tử có thể lặp hoặc cần thứ tự.

## 5. Tổng hợp JSON lồng nhau

Có thể lồng JSON_OBJECT trong JSON_ARRAYAGG để tạo cấu trúc nhiều cấp. Đây là cách phổ biến khi một API trả về cha cùng danh sách con.

### 5.1. Một đơn hàng cùng các dòng hàng

Giả sử có:

- sales_order(order_id, order_no, ordered_at)
- order_item(order_id, line_no, product_id, product_name, quantity, unit_price)

Tạo một JSON array dòng hàng cho mỗi đơn:

~~~sql
SELECT
    oi.order_id,
    JSON_ARRAYAGG(
        JSON_OBJECT(
            'lineNo', oi.line_no,
            'productId', oi.product_id,
            'productName', oi.product_name,
            'quantity', oi.quantity,
            'unitPrice', oi.unit_price
        )
    ) AS items
FROM order_item AS oi
GROUP BY oi.order_id;
~~~

Kết hợp với bảng đơn hàng:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    o.ordered_at,
    (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', oi.line_no,
                'productId', oi.product_id,
                'productName', oi.product_name,
                'quantity', oi.quantity,
                'unitPrice', oi.unit_price
            )
        )
        FROM order_item AS oi
        WHERE oi.order_id = o.order_id
    ) AS items
FROM sales_order AS o
WHERE o.order_id = 1001;
~~~

Nếu đơn hàng không có dòng hàng, correlated subquery trả về NULL. Nếu hợp đồng API yêu cầu items luôn là array, bọc bằng COALESCE:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    COALESCE(
        (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'lineNo', oi.line_no,
                    'productId', oi.product_id,
                    'productName', oi.product_name,
                    'quantity', oi.quantity,
                    'unitPrice', oi.unit_price
                )
            )
            FROM order_item AS oi
            WHERE oi.order_id = o.order_id
        ),
        JSON_ARRAY()
    ) AS items
FROM sales_order AS o
WHERE o.order_id = 1001;
~~~

Dùng correlated subquery tránh một vấn đề thường gặp khi LEFT JOIN: nếu không có dòng con, JSON_OBJECT vẫn có thể được tạo từ một hàng join chứa các cột con NULL, tạo array có một object toàn null thay vì array rỗng.

### 5.2. JSON object lồng nhau

Có thể tạo object cho thông tin khách hàng và array cho các đơn hàng:

~~~sql
SELECT
    c.customer_id,
    JSON_OBJECT(
        'customerId', c.customer_id,
        'name', c.full_name,
        'email', c.email,
        'orders',
        COALESCE(
            (
                SELECT JSON_ARRAYAGG(
                    JSON_OBJECT(
                        'orderId', o.order_id,
                        'orderNo', o.order_no,
                        'orderedAt', o.ordered_at
                    )
                )
                FROM sales_order AS o
                WHERE o.customer_id = c.customer_id
            ),
            JSON_ARRAY()
        )
    ) AS customer_document
FROM customer AS c
WHERE c.customer_id = 101;
~~~

Kết quả là một JSON object chứa thuộc tính orders với giá trị là JSON array. Khi lồng các hàm JSON, MySQL giữ kiểu JSON của biểu thức JSON thay vì ghép chuỗi thủ công.

### 5.3. Kết hợp nhiều cấp tổng hợp

Có thể tổng hợp sản phẩm theo danh mục, sau đó tổng hợp danh mục theo cửa hàng hoặc tenant. Tuy nhiên, hãy kiểm soát cardinality trước khi join. Nếu join nhiều quan hệ 1:N trong cùng một truy vấn, số hàng có thể nhân lên và làm JSON_ARRAYAGG lặp phần tử.

Ví dụ, một đơn có 3 dòng hàng và 2 lần thanh toán. Nếu join trực tiếp ORDER_ITEM với PAYMENT qua SALES_ORDER, kết quả trung gian có thể có 3 x 2 = 6 hàng. JSON_ARRAYAGG dòng hàng khi đó có thể lặp mỗi dòng hai lần.

Cách an toàn là tổng hợp từng nhánh con riêng biệt rồi ghép kết quả:

~~~sql
WITH item_agg AS (
    SELECT
        order_id,
        JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', line_no,
                'productId', product_id,
                'quantity', quantity
            )
        ) AS items
    FROM order_item
    GROUP BY order_id
),
payment_agg AS (
    SELECT
        order_id,
        JSON_ARRAYAGG(
            JSON_OBJECT(
                'paymentId', payment_id,
                'amount', amount,
                'status', payment_status
            )
        ) AS payments
    FROM payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.items, JSON_ARRAY()) AS items,
    COALESCE(p.payments, JSON_ARRAY()) AS payments
FROM sales_order AS o
LEFT JOIN item_agg AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_agg AS p
    ON p.order_id = o.order_id;
~~~

Mỗi CTE tạo tối đa một hàng cho mỗi order_id. Join các kết quả đã tổng hợp tránh nhân chéo các dòng hàng và thanh toán.

## 6. Phân biệt JSON aggregation với GROUP_CONCAT

GROUP_CONCAT nối giá trị thành một chuỗi. JSON_ARRAYAGG và JSON_OBJECTAGG tạo giá trị JSON có cấu trúc.

| Tiêu chí | GROUP_CONCAT | JSON_ARRAYAGG | JSON_OBJECTAGG |
|---|---|---|---|
| Kết quả | Chuỗi | JSON array | JSON object |
| Cách truy cập phía client | Phải tự tách chuỗi | Parse JSON array | Parse JSON object |
| Escape dấu phân cách | Phải tự thiết kế | JSON xử lý escape | JSON xử lý escape |
| Nhiều hàng | Các phần tử nối chuỗi | Một phần tử cho mỗi hàng | Một cặp key/value cho mỗi hàng |
| Thứ tự | Có thể dùng ORDER BY trong hàm | Aggregate thường không bảo đảm thứ tự | Không nên dựa vào thứ tự thuộc tính |
| Khóa trùng | Không có khái niệm key | Phần tử lặp vẫn được giữ | Key trùng cần được xử lý |
| Giới hạn kết quả | Bị cắt theo group_concat_max_len và còn chịu max_allowed_packet | Không bị cắt theo group_concat_max_len; kết quả vẫn chịu giới hạn packet/row và tài nguyên | Không bị cắt theo group_concat_max_len; kết quả vẫn chịu giới hạn packet/row và tài nguyên |

Ví dụ GROUP_CONCAT:

~~~sql
SELECT
    category_id,
    GROUP_CONCAT(product_name ORDER BY product_name SEPARATOR ', ')
        AS product_list
FROM product
GROUP BY category_id;
~~~

Kết quả là một chuỗi như Bàn phím cơ, Chuột không dây, Lót chuột. Nếu tên sản phẩm có dấu phẩy hoặc ký tự phân cách, client khó tách chính xác nếu không có quy ước escape.

Với JSON_ARRAYAGG:

~~~sql
SELECT
    category_id,
    JSON_ARRAYAGG(product_name) AS product_list
FROM product
GROUP BY category_id;
~~~

Client nhận một JSON array hợp lệ và không phải tự tách dấu phân cách. Tuy vậy, JSON_ARRAYAGG có quy tắc thứ tự riêng; không thay GROUP_CONCAT rồi giả định thứ tự vẫn được bảo đảm.

## 7. Kiểm soát kiểu dữ liệu và JSON lồng nhau

### 7.1. SQL NULL và JSON null

Cần phân biệt:

- SQL NULL: không có giá trị SQL.
- JSON null: một giá trị null nằm bên trong JSON document.
- Không có key: object không chứa thuộc tính đó.
- Array rỗng: JSON array không có phần tử.

Ví dụ:

~~~sql
SELECT
    JSON_ARRAY(NULL) AS array_with_null,
    JSON_ARRAY() AS empty_array,
    JSON_OBJECT('value', NULL) AS object_with_null,
    JSON_OBJECT() AS empty_object;
~~~

Kết quả lần lượt có dạng:

~~~json
[
  [null],
  [],
  {"value": null},
  {}
]
~~~

Trong aggregate, SQL NULL của biểu thức JSON_ARRAYAGG được biểu diễn thành JSON null cho hàng đó. Nhưng khi không có hàng đầu vào, aggregate trả về SQL NULL. COALESCE giúp chuyển SQL NULL ở cấp kết quả thành JSON array/object rỗng nếu đó là hợp đồng mong muốn.

### 7.2. Chuỗi JSON và JSON value

Nếu một cột VARCHAR chứa văn bản trông giống JSON, JSON_OBJECT có thể xem nó là một chuỗi, không tự động parse thành object lồng nhau.

~~~sql
SELECT JSON_OBJECT(
    'metadata',
    '{"source":"web","priority":2}'
) AS result;
~~~

Giá trị metadata có thể trở thành JSON string chứa ký tự JSON, thay vì object lồng nhau.

Muốn parse chuỗi JSON hợp lệ thành JSON value, dùng CAST AS JSON:

~~~sql
SELECT JSON_OBJECT(
    'metadata',
    CAST('{"source":"web","priority":2}' AS JSON)
) AS result;
~~~

Kết quả là object lồng nhau:

~~~json
{
  "metadata": {
    "source": "web",
    "priority": 2
  }
}
~~~

CAST sẽ báo lỗi nếu chuỗi không phải JSON hợp lệ. Nếu dữ liệu đến từ nguồn không tin cậy hoặc có thể sai định dạng, hãy kiểm tra JSON_VALID trước khi chuyển đổi.

### 7.3. Số, chuỗi và ngày giờ

JSON aggregation giữ kiểu dữ liệu theo biểu thức SQL. Nếu cột giá là DECIMAL, giá trị thường được biểu diễn thành JSON number. Nếu muốn một số được hiển thị dưới dạng chuỗi, cần CAST rõ ràng; ngược lại, không ép số thành chuỗi nếu client cần tính toán.

DATE, DATETIME và TIMESTAMP thường được biểu diễn thành chuỗi ngày giờ trong JSON. Hãy thống nhất timezone và định dạng thời gian trong hợp đồng API; JSON aggregation không tự giải quyết quy ước timezone của ứng dụng.

## 8. Window function với JSON_OBJECTAGG

JSON_OBJECTAGG cũng có thể dùng làm window function từ MySQL 8.0.14. Điều này hữu ích khi muốn tạo object theo partition nhưng vẫn giữ các hàng chi tiết. Khác với JSON_ARRAYAGG, ORDER BY trong cửa sổ có thể quyết định hàng nào là hàng cuối cùng khi một key xuất hiện nhiều lần.

Ví dụ:

~~~sql
SELECT
    user_id,
    setting_key,
    setting_value,
    JSON_OBJECTAGG(setting_key, setting_value) OVER (
        PARTITION BY user_id
    ) AS all_settings
FROM user_setting;
~~~

Mỗi hàng của user có thể mang cùng object settings của partition. Nếu dùng window ORDER BY và có key trùng, thứ tự cửa sổ cùng frame ảnh hưởng đến giá trị nào được xem là cuối cùng. Ví dụ, để giữ giá trị cuối theo thời gian cập nhật:

~~~sql
SELECT
    user_id,
    setting_key,
    setting_value,
    JSON_OBJECTAGG(setting_key, setting_value) OVER (
        PARTITION BY user_id
        ORDER BY updated_at, setting_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS latest_settings
FROM user_setting_history;
~~~

ORDER BY updated_at, setting_id phải xác định được thứ tự duy nhất trong partition. Với frame toàn partition, hàng cuối cùng theo thứ tự đó thắng khi key bị lặp. Cách dễ kiểm soát nhất cho một object trên mỗi user vẫn là khử trùng lặp bằng ROW_NUMBER trước khi aggregate, như phần 3.2.

Đừng dùng window function chỉ để tránh một bước GROUP BY nếu kết quả cần đúng một hàng cho mỗi nhóm. Window function giữ lại từng hàng đầu vào; cần thêm ROW_NUMBER hoặc một bước chọn đại diện nếu muốn một hàng cho mỗi partition.

## 9. Hiệu năng và giới hạn vận hành

JSON aggregation giảm số hàng truyền từ database sang ứng dụng, nhưng không miễn phí.

Chi phí có thể tăng khi:

- Một nhóm chứa rất nhiều hàng.
- Mỗi phần tử là object có nhiều thuộc tính.
- JSON document lồng nhau có kích thước lớn.
- Câu truy vấn join nhiều nhánh 1:N trước khi tổng hợp.
- Client chỉ cần một vài trường nhưng SQL tạo toàn bộ document.
- Nhiều request đồng thời cùng tạo các JSON document lớn.

Một số nguyên tắc:

1. Lọc hàng trước khi tổng hợp bằng WHERE.
2. Chọn đúng cột và biểu thức cần đưa vào JSON.
3. Tổng hợp từng nhánh 1:N trước khi join các nhánh.
4. Dùng index cho điều kiện lọc và khóa join.
5. Giới hạn kích thước nhóm hoặc phân trang ở cấp đối tượng cha.
6. Đo thời gian, memory và kích thước payload trên dữ liệu gần thực tế; lưu ý max_allowed_packet ở server/client khi trả về một JSON document lớn.
7. Không dùng JSON aggregation thay thế mọi thao tác truy vấn quan hệ.

Ví dụ lấy các đơn gần đây của một khách hàng:

~~~sql
SELECT
    o.order_id,
    o.order_no,
    (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'lineNo', oi.line_no,
                'productName', oi.product_name,
                'quantity', oi.quantity
            )
        )
        FROM order_item AS oi
        WHERE oi.order_id = o.order_id
    ) AS items
FROM sales_order AS o
WHERE o.customer_id = 101
ORDER BY o.ordered_at DESC
LIMIT 20;
~~~

Index (customer_id, ordered_at) hỗ trợ lọc và sắp xếp đơn hàng theo khách hàng. Primary key hoặc index bắt đầu bằng order_id trên ORDER_ITEM hỗ trợ truy vấn con lấy dòng hàng.

Nếu một đơn có hàng trăm nghìn dòng, việc tạo một JSON array duy nhất có thể tạo payload quá lớn. Khi đó hãy phân trang dòng hàng hoặc để API tải chi tiết theo endpoint riêng.

## 10. Kiểm tra kết quả JSON

Có thể dùng các hàm JSON để kiểm tra kết quả:

~~~sql
SELECT
    JSON_VALID(
        JSON_ARRAYAGG(product_name)
    ) AS is_valid_json,
    JSON_TYPE(
        JSON_ARRAYAGG(product_name)
    ) AS result_type
FROM product;
~~~

JSON_TYPE có thể trả về ARRAY cho kết quả JSON_ARRAYAGG. Với JSON_OBJECTAGG, kết quả là OBJECT khi có dữ liệu.

Có thể dùng JSON_PRETTY để đọc dễ hơn khi debug:

~~~sql
SELECT JSON_PRETTY(
    JSON_OBJECTAGG(setting_key, setting_value)
) AS formatted_settings
FROM user_setting
WHERE user_id = 101;
~~~

JSON_PRETTY hữu ích cho kiểm tra thủ công, nhưng không cần thiết trong payload production nếu client đã parse JSON. Việc pretty-print làm tăng kích thước truyền tải.

Khi kiểm tra dữ liệu:

- Xác nhận JSON_VALID trả về 1.
- Xác nhận JSON_TYPE đúng ARRAY hoặc OBJECT.
- Kiểm tra số phần tử với JSON_LENGTH.
- Kiểm tra một key cụ thể bằng JSON_EXTRACT.
- Kiểm tra array rỗng và object rỗng theo hợp đồng API.
- Kiểm tra key trùng trước khi tổng hợp object.

Ví dụ:

~~~sql
SELECT
    JSON_LENGTH(products_json) AS product_count,
    JSON_EXTRACT(products_json, '$[0].productId') AS first_product_id
FROM category_product_document;
~~~

JSON_EXTRACT trả về JSON value. Nếu cần scalar SQL, có thể dùng JSON_UNQUOTE hoặc toán tử ->> tùy phiên bản và biểu thức.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng JSON_ARRAYAGG luôn sắp xếp theo index | Thứ tự array có thể thay đổi | Nếu thứ tự bắt buộc, SELECT các hàng với ORDER BY rồi serialize array ở ứng dụng |
| Dùng JSON_OBJECTAGG với key trùng | Giá trị cuối cùng thắng; kết quả có thể không ổn định | UNIQUE key hoặc ROW_NUMBER để chọn một hàng |
| Đưa key NULL vào JSON_OBJECTAGG | Hàm phát sinh lỗi | Lọc hoặc ánh xạ key theo quy tắc nghiệp vụ |
| Nghĩ value NULL là lỗi | Bỏ sót ý nghĩa JSON null | Phân biệt NULL ở key và value |
| Mong tập rỗng tự trả [] hoặc {} | Aggregate trả SQL NULL | Dùng COALESCE với JSON_ARRAY()/JSON_OBJECT() |
| LEFT JOIN rồi tổng hợp object con | Có thể tạo object toàn null cho hàng không có con | Dùng correlated subquery hoặc aggregate con riêng |
| Join nhiều nhánh 1:N trước khi tổng hợp | Phần tử JSON bị nhân lặp | Tổng hợp từng nhánh trong CTE/derived table |
| Dùng JSON_OBJECTAGG cho danh sách có thứ tự | Object không phải cấu trúc danh sách | Dùng JSON_ARRAYAGG |
| Coi JSON text trong VARCHAR là JSON object | Kết quả bị lồng thành chuỗi | CAST chuỗi hợp lệ AS JSON |
| Tạo một JSON document quá lớn | Tăng memory, latency và payload | Lọc, phân trang hoặc chia endpoint |

## 12. Bài tập thực hành

### Bài 1: Gom tên sản phẩm

Tạo bảng PRODUCT có category_id và product_name. Dùng JSON_ARRAYAGG để trả về danh sách tên sản phẩm theo danh mục. Kiểm tra JSON_TYPE và JSON_LENGTH.

### Bài 2: Gom object thiết lập người dùng

Tạo USER_SETTING với user_id, setting_key và setting_value. Dùng JSON_OBJECTAGG để tạo một object cho mỗi user. Thử value NULL và quan sát JSON null.

### Bài 3: Kiểm tra khóa trùng

Chèn hai hàng cùng user_id và setting_key nhưng khác setting_value. Chạy JSON_OBJECTAGG nhiều lần và quan sát quy tắc khóa trùng. Sau đó dùng ROW_NUMBER để chọn bản ghi mới nhất trước khi aggregate.

### Bài 4: Trả về đơn hàng dạng JSON

Tạo SALES_ORDER và ORDER_ITEM. Dùng JSON_ARRAYAGG(JSON_OBJECT(...)) để tạo items cho từng đơn. Xử lý trường hợp đơn không có dòng hàng để kết quả là [].

### Bài 5: Ngăn nhân bản do JOIN

Tạo một đơn có 3 dòng hàng và 2 thanh toán. Thử join cả hai bảng con rồi aggregate. Đếm số phần tử bị lặp, sau đó chuyển sang hai CTE tổng hợp riêng và join kết quả.

### Bài 6: Phân biệt tổng hợp window và thứ tự array

Dùng JSON_ARRAYAGG dưới dạng window function với PARTITION BY order_id và ROWS frame toàn partition để gắn array vào các hàng chi tiết. Sau đó chạy SELECT các dòng của một đơn với ORDER BY line_no và serialize thành array ở ứng dụng. Giải thích vì sao cách thứ hai mới bảo đảm thứ tự theo line_no.

### Bài 7: So sánh GROUP_CONCAT và JSON_ARRAYAGG

Tạo tên sản phẩm có dấu phẩy, dấu nháy kép và ký tự Unicode. So sánh chuỗi GROUP_CONCAT với JSON array. Parse kết quả JSON ở client và xác nhận từng phần tử được giữ nguyên.

### Bài 8: Thiết kế hợp đồng API

Tạo một response JSON có thông tin customer, orders và items. Xác định rõ trường nào là array, trường nào là object, trường nào có thể null và trường nào phải là mảng rỗng khi không có dữ liệu.

## Kết luận

JSON_ARRAYAGG chuyển nhiều hàng thành JSON array; JSON_OBJECTAGG chuyển nhiều cặp key/value thành JSON object. Chúng giúp MySQL trả về cấu trúc dữ liệu gần với hợp đồng API và giảm việc ghép chuỗi thủ công ở ứng dụng.

Để kết quả ổn định, hãy xử lý rõ thứ tự array, khóa object trùng, key NULL, SQL NULL và nhóm rỗng. Khi join nhiều nhánh quan hệ 1:N, tổng hợp từng nhánh riêng trước khi ghép để tránh nhân bản phần tử. Cuối cùng, kiểm tra kiểu JSON, kích thước payload và hiệu năng trên dữ liệu thực tế.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Aggregate Functions: https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html
- MySQL 8.4 Reference Manual — JSON Creation Functions: https://dev.mysql.com/doc/refman/8.4/en/json-creation-functions.html
- MySQL 8.4 Reference Manual — JSON Functions: https://dev.mysql.com/doc/refman/8.4/en/json-functions.html
- MySQL 8.4 Reference Manual — Window Function Concepts and Syntax: https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html
- MySQL 8.4 Reference Manual — Window Function Restrictions: https://dev.mysql.com/doc/refman/8.4/en/window-function-restrictions.html

