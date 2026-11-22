# Multi-valued index và các giới hạn với mảng JSON

Bài học thuộc chương **JSON** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. JSON cho phép lưu các thuộc tính linh hoạt, trong đó mảng thường biểu diễn tập giá trị như mã vùng, nhãn, kỹ năng hoặc quyền của một đối tượng. Nhưng index B-tree thông thường được thiết kế theo quan hệ một hàng dữ liệu với một giá trị index cho mỗi key part. Multi-valued index (MVI) của InnoDB giải quyết bài toán tìm hàng theo từng phần tử của mảng JSON bằng cách tạo nhiều index record cùng trỏ về một hàng dữ liệu.

Sau bài này, bạn có thể giải thích cấu trúc N:1 của MVI, tạo index bằng CAST(... AS ... ARRAY), phân biệt MEMBER OF(), JSON_CONTAINS() và JSON_OVERLAPS(), đọc EXPLAIN để xác minh optimizer sử dụng index, hiểu hành vi của mảng rỗng và NULL, đánh giá giới hạn về ordering, range scan, covering index, foreign key, collation và DDL, đồng thời quyết định khi nào nên dùng MVI và khi nào nên chuẩn hóa mảng thành bảng quan hệ.

## 1. Bài toán: tìm một hàng theo phần tử bên trong mảng JSON

Giả sử ứng dụng lưu khách hàng cùng các mã bưu chính mà khách có thể nhận hàng:

~~~json
{
  "name": "Lan",
  "zip_codes": [70000, 70001, 70003]
}
~~~

Bảng:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id INT NOT NULL,
    profile JSON NOT NULL
) ENGINE=InnoDB;
~~~

Truy vấn tìm khách hàng có mã 70001:

~~~sql
SELECT customer_id, profile
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Nếu không có index phù hợp, MySQL có thể phải đọc nhiều hàng rồi kiểm tra từng JSON document. Index thông thường trên toàn bộ cột profile không tạo một index entry riêng cho từng phần tử trong zip_codes.

Multi-valued index cho phép InnoDB tạo một index record cho mỗi phần tử của mảng được chọn. Với một hàng có ba mã bưu chính, index có ba record cùng tham chiếu về customer_id đó.

~~~text
Một hàng trong bảng customers
customer_id = 42
zip_codes = [70000, 70001, 70003]

Một multi-valued index
70000  ──┐
70001  ──┼──> customer_id = 42
70003  ──┘
~~~

Đây là quan hệ **N:1** giữa index record và hàng bảng: một hàng có thể tạo nhiều index record. MVI là secondary index của InnoDB, được thiết kế cho việc tìm kiếm theo phần tử trong JSON array.

MVI được giới thiệu từ MySQL 8.0.17. Nó không có trong MySQL 5.7. Cần xác minh phiên bản server trước khi thiết kế schema hoặc triển khai migration. [MySQL 8.0.17 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-17.html).

## 2. MVI hoạt động như thế nào?

Một index thông thường có thể hình dung như sau:

| Primary key | Giá trị index |
|---:|---|
| 10 | 70000 |
| 11 | 70001 |
| 12 | 70003 |

Mỗi hàng đóng góp một index value cho key part đó.

Với MVI, một hàng có thể đóng góp nhiều giá trị:

| Primary key | Phần tử trong JSON array | Index record |
|---:|---:|---|
| 10 | 70000 | 70000 → 10 |
| 10 | 70001 | 70001 → 10 |
| 10 | 70003 | 70003 → 10 |
| 11 | 70001 | 70001 → 11 |
| 12 | 70003 | 70003 → 12 |

Khi tìm 70001, InnoDB có thể tìm các index record mang giá trị đó và lấy các hàng tương ứng.

MVI được triển khai dưới dạng functional index trên một virtual column được tạo ngầm từ biểu thức JSON array. Người dùng khai báo biểu thức CAST trong index; không cần tự tạo virtual column để tách từng phần tử.

Một MVI có các đặc điểm:

- Chỉ được hỗ trợ trên bảng InnoDB.
- Là secondary index, không phải primary key.
- Một key part có thể sinh nhiều index record cho một hàng.
- Có thể đứng cùng các key part đơn trị trong một composite index.
- Dữ liệu trong JSON vẫn được lưu trong cột JSON; index chỉ hỗ trợ tìm kiếm theo phần tử.

MVI không biến JSON array thành bảng quan hệ. Nó không tự tạo foreign key cho từng phần tử, không áp dụng constraint quan hệ lên từng phần tử và không cung cấp mọi khả năng truy vấn như một bảng con được chuẩn hóa.

## 3. Cú pháp tạo multi-valued index

Cấu trúc cơ bản:

~~~sql
CREATE INDEX index_name
ON table_name (
    (CAST(json_expression AS SQL_TYPE ARRAY))
);
~~~

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    profile JSON NOT NULL,
    INDEX idx_customer_zip (
        (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
    )
) ENGINE=InnoDB;
~~~

Biểu thức:

~~~sql
CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY)
~~~

có ý nghĩa:

1. Lấy mảng ở JSON path $.zip_codes.
2. CAST các phần tử scalar sang kiểu SQL được chỉ định.
3. Khai báo kết quả là một SQL data type array bằng từ khóa ARRAY.
4. InnoDB tạo index record tương ứng cho các giá trị của mảng.

Có thể tạo index sau khi bảng đã tồn tại:

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Hoặc:

~~~sql
ALTER TABLE customers
ADD INDEX idx_customer_zip (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Trong định nghĩa index, biểu thức cần được đặt trong cặp ngoặc của key part. Do đó thường thấy hai lớp ngoặc quanh CAST expression.

### Chọn kiểu SQL phù hợp

Kiểu sau ARRAY xác định kiểu dữ liệu của từng index value. Chọn kiểu theo dữ liệu thực tế:

- UNSIGNED: mã số nguyên không âm như mã bưu chính số hoặc ID số.
- SIGNED: số nguyên có thể âm.
- CHAR/VARCHAR: phần tử chuỗi có độ dài và collation phù hợp.
- Các kiểu khác được hỗ trợ bởi CAST, tùy quy tắc và giới hạn của MVI.

Không dùng CAST AS BINARY cho multi-valued key part; kiểu BINARY bị cấm. JSON cũng không phải kiểu đích để tạo SQL array index.

Kiểu index phải khớp với cách ứng dụng truy vấn. Nếu dữ liệu chứa số nguyên nhưng query so sánh với chuỗi, MEMBER OF() không tự chuyển đổi giữa string và numeric. Hãy chuẩn hóa kiểu phần tử trước khi tạo index.

### Mảng phải chứa các phần tử scalar cùng kiểu logic

Ví dụ tốt:

~~~json
{
  "zip_codes": [70000, 70001, 70003]
}
~~~

Ví dụ dễ gây vấn đề:

~~~json
{
  "zip_codes": [70000, "70001", null]
}
~~~

Mảng trộn số, chuỗi và JSON null khiến việc CAST và so sánh khó dự đoán. JSON null không được phép xuất hiện trong các giá trị được index bởi MVI. Nên xác thực dữ liệu đầu vào để các phần tử có kiểu thống nhất và không chứa JSON null.

## 4. Dùng MEMBER OF() để tìm một phần tử

MEMBER OF() kiểm tra một giá trị có phải là phần tử của JSON array hay không.

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Kết quả là các khách hàng có phần tử 70001 trong zip_codes.

MVI có thể được optimizer sử dụng cho MEMBER OF() trong WHERE nếu biểu thức phù hợp với index và kế hoạch chi phí chọn index đó.

### So sánh kiểu dữ liệu là chính xác

MEMBER OF() không tự chuyển đổi string thành number hoặc number thành string.

~~~sql
SELECT
    17 MEMBER OF ('[23, "17", 17]') AS numeric_match,
    '17' MEMBER OF ('[23, "17", 17]') AS string_match;
~~~

Hai phép kiểm tra có kiểu giá trị khác nhau. Không nên dựa vào việc MySQL tự chuyển đổi chuỗi số thành số khi tìm phần tử trong JSON array.

Nếu một giá trị được lưu là chuỗi, truy vấn cần dùng chuỗi. Nếu được lưu là số, truy vấn cần dùng số.

Partial match cũng không xảy ra: tìm số 7 không khớp phần tử số 17; tìm chuỗi 'a' không khớp chuỗi 'abc'.

### MEMBER OF() trả về NULL

Nếu giá trị kiểm tra hoặc JSON array là SQL NULL, MEMBER OF() trả về NULL. Kết quả này không phải TRUE và cũng không phải FALSE.

Đối với phần tử JSON object hoặc array, cần truyền giá trị JSON có kiểu phù hợp bằng CAST(... AS JSON), JSON_OBJECT() hoặc JSON_ARRAY() tùy trường hợp. MVI thường được dùng nhất cho các mảng scalar như số hoặc chuỗi.

## 5. Phân biệt MEMBER OF(), JSON_CONTAINS() và JSON_OVERLAPS()

Cả ba phép toán đều có thể được optimizer hỗ trợ bằng MVI khi được dùng phù hợp trong WHERE, nhưng ngữ nghĩa khác nhau.

| Hàm/toán tử | Ý nghĩa với array | Ví dụ nghiệp vụ |
|---|---|---|
| MEMBER OF() | Một scalar có nằm trong array không | Khách có mã zip 70001 |
| JSON_CONTAINS() | Mọi phần tử của candidate đều phải có trong target | Khách có cả zip 70001 và 70003 |
| JSON_OVERLAPS() | Chỉ cần có ít nhất một phần tử chung | Khách có một trong các zip được hỗ trợ |

### MEMBER OF(): tìm một giá trị

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Đây là phép kiểm tra một scalar có là phần tử của array hay không.

### JSON_CONTAINS(): tất cả phần tử candidate phải tồn tại

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001, 70003]' AS JSON)
);
~~~

Candidate là array có hai phần tử. Một hàng chỉ khớp nếu target array chứa cả 70001 và 70003.

Với candidate là scalar, JSON_CONTAINS trên target array kiểm tra scalar đó có nằm trong array hay không.

### JSON_OVERLAPS(): chỉ cần một phần tử giao nhau

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001, 70003]' AS JSON)
);
~~~

Một hàng khớp nếu target array có ít nhất một phần tử trong candidate array.

Ví dụ:

| zip_codes | JSON_CONTAINS [70001,70003] | JSON_OVERLAPS [70001,70003] |
|---|---:|---:|
| [70001,70003] | 1 | 1 |
| [70001,70002] | 0 | 1 |
| [70003] | 0 | 1 |
| [70002,70004] | 0 | 0 |

JSON_CONTAINS là điều kiện AND trên các phần tử candidate. JSON_OVERLAPS là điều kiện OR: chỉ cần một phần tử chung.

Không thay hàm này bằng hàm kia nếu yêu cầu nghiệp vụ khác nhau. Một truy vấn có thể trả nhiều hoặc ít hàng hơn đáng kể chỉ vì thay đổi ngữ nghĩa containment/overlap.

## 6. Cách optimizer sử dụng MVI

MySQL có thể dùng MVI để tìm hàng cho các predicate sau trong WHERE:

- MEMBER OF()
- JSON_CONTAINS()
- JSON_OVERLAPS()

Ví dụ:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Các trường cần kiểm tra:

| Trường EXPLAIN | Cần quan sát |
|---|---|
| possible_keys | MVI có xuất hiện trong danh sách index có thể dùng không |
| key | Optimizer có chọn MVI không |
| type | Có thể xuất hiện access type range khi dùng MVI |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ hàng còn lại sau lọc |
| Extra | Điều kiện còn phải kiểm tra sau khi lấy row |

Ví dụ JSON_CONTAINS:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

Ví dụ JSON_OVERLAPS:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

Optimizer không bắt buộc phải chọn index trong mọi trường hợp. Với bảng nhỏ, giá trị có độ chọn lọc thấp hoặc thống kê chưa phù hợp, table scan có thể rẻ hơn.

Sau khi tạo index trên bảng InnoDB, có thể cập nhật thống kê:

~~~sql
ANALYZE TABLE customers;
~~~

Đừng chỉ nhìn việc index tồn tại trong SHOW INDEX rồi kết luận truy vấn đang sử dụng nó. Hãy kiểm tra EXPLAIN và đo trên dữ liệu có quy mô gần production.

### Biểu thức JSON phải phù hợp với index

Index được tạo trên JSON path cụ thể. Truy vấn nên dùng cùng JSON expression và path mà index định nghĩa.

Ví dụ index:

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Predicate phù hợp:

~~~sql
WHERE 70001 MEMBER OF (profile->'$.zip_codes')
~~~

Nếu ứng dụng truy vấn một path khác như $.preferred_zip hoặc $.addresses[*].zip, index trên $.zip_codes không tự phục vụ path đó.

Hãy xem xét biểu thức JSON, kiểu phần tử và predicate trước khi tạo index. Tránh tạo nhiều MVI trùng lặp cho các path ít được truy vấn.

## 7. MVI trong composite index

Một MVI có thể là một key part trong composite index cùng với các key part đơn trị.

Ví dụ:

~~~sql
CREATE INDEX idx_tenant_zip
ON customers (
    tenant_id,
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Truy vấn:

~~~sql
SELECT customer_id
FROM customers
WHERE tenant_id = 10
  AND 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Index có thể hỗ trợ kết hợp điều kiện tenant_id với tìm phần tử trong array.

Chỉ được có **một multi-valued key part trong mỗi index**. Các key part còn lại phải là key part đơn trị. Key part MVI có thể đứng ở các vị trí khác nhau trong composite index theo cú pháp được hỗ trợ.

Không tạo composite index có hai biểu thức ARRAY:

~~~sql
-- Không hợp lệ: có hai multi-valued key part trong cùng index
CREATE INDEX idx_invalid
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY)),
    (CAST(profile->'$.tag_ids' AS UNSIGNED ARRAY))
);
~~~

Nếu cần truy vấn đồng thời hai mảng độc lập, cân nhắc hai MVI riêng hoặc chuẩn hóa từng mối quan hệ thành bảng con.

### Chọn thứ tự key part

Với composite index, thứ tự key part vẫn quan trọng đối với các truy vấn lọc theo cột đơn trị. Hãy thiết kế dựa trên workload:

- Cột tenant/account thường được lọc bằng phép bằng có thể đứng trước.
- MVI đứng ở vị trí phù hợp với predicate array.
- Kiểm tra các truy vấn có và không có điều kiện tenant.
- Không mặc định một composite index phục vụ tốt mọi biến thể query.

MVI không thay thế nguyên tắc leftmost prefix của composite index. Đo kế hoạch thực thi trên truy vấn thực tế.

## 8. MVI không hỗ trợ ordering và range scan

Đây là giới hạn quan trọng.

MVI không thể được sử dụng để:

- Sắp xếp kết quả theo phần tử array như một B-tree index thông thường.
- Hỗ trợ range scan theo khoảng giá trị array.
- Làm primary key.
- Dùng ASC hoặc DESC trong định nghĩa key part.

Ví dụ truy vấn:

~~~sql
SELECT customer_id
FROM customers
WHERE 70000 <= ANY (profile->'$.zip_codes');
~~~

Không thể mặc định rằng MVI sẽ phục vụ một phép range search như index đơn trị. MVI được tối ưu cho các phép kiểm tra membership/containment/overlap được hỗ trợ.

Tương tự, nếu yêu cầu là lấy khách hàng theo zip code tăng dần, MVI không cung cấp thứ tự đó. Cần sort kết quả hoặc dùng mô hình dữ liệu khác.

Nếu nghiệp vụ cần:

- Tìm các giá trị trong khoảng.
- Sắp xếp theo từng phần tử.
- Phân trang theo phần tử.
- Thống kê hoặc GROUP BY theo từng phần tử thường xuyên.

hãy cân nhắc bảng quan hệ con với một hàng cho mỗi phần tử.

## 9. MVI không phải covering index

Một covering index chứa toàn bộ cột cần thiết cho truy vấn, cho phép engine trả kết quả mà không phải đọc thêm hàng clustered record.

MVI không hỗ trợ index-only scan/covering index. Vì index record của nhiều phần tử cùng trỏ về một clustered row và có các giới hạn truy cập riêng, MySQL vẫn cần truy cập hàng bảng để lấy các cột kết quả hoặc xác minh điều kiện.

Ví dụ:

~~~sql
SELECT customer_id, profile
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

MVI có thể giúp tìm customer_id nhanh hơn, nhưng không có nghĩa toàn bộ profile được trả trực tiếp từ index.

Khi truy vấn trả về nhiều cột hoặc nhiều hàng, chi phí đọc clustered record vẫn tồn tại. Đừng kỳ vọng MVI có hiệu quả giống một covering secondary index thông thường.

## 10. Giới hạn với primary key, foreign key và index prefix

Các giới hạn chính:

| Khả năng | MVI |
|---|---|
| Secondary index | Có |
| Primary key | Không |
| UNIQUE secondary index | Có; uniqueness áp dụng trên các giá trị index được sinh ra |
| Foreign key specification | Không |
| Index prefix | Không |
| ASC/DESC | Không |
| Range scan | Không |
| Index-only scan | Không |
| Covering index | Không |
| Composite index với key part đơn trị | Có |
| Hai MVI key part trong cùng index | Không |

MVI có thể được định nghĩa là UNIQUE index, nhưng ý nghĩa uniqueness áp dụng trên các index value được sinh ra. Đây không phải constraint quan hệ thay thế foreign key. Nếu cần bảo đảm từng ID trong JSON array tham chiếu tới một hàng cha tồn tại, MVI không thực hiện được việc đó.

Nếu các giá trị đã có trong dữ liệu bị trùng theo quy tắc của unique index, việc tạo UNIQUE MVI sẽ thất bại. Khi index đã tồn tại, thao tác ghi tạo ra một index key trùng cũng có thể bị từ chối. Chỉ chọn UNIQUE khi nghiệp vụ yêu cầu tính duy nhất trên toàn bộ key được tạo ra (bao gồm các key part đơn trị nếu index là composite); đây không phải foreign key và không kiểm tra sự tồn tại của hàng được tham chiếu.

Ví dụ lưu product IDs trong JSON array:

~~~json
{
  "product_ids": [100, 101, 102]
}
~~~

MVI có thể tăng tốc tìm đơn hàng chứa product_id 101, nhưng không bảo đảm product 101 tồn tại trong bảng products.

Nếu cần referential integrity, dùng bảng order_items:

~~~sql
CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB;
~~~

Đây là mô hình quan hệ phù hợp khi mỗi phần tử có danh tính, thuộc tính riêng hoặc cần constraint.

## 11. Mảng rỗng, SQL NULL và JSON null

MVI có hành vi đặc biệt với các giá trị rỗng và NULL.

| Giá trị của biểu thức array | Hành vi index |
|---|---|
| Mảng rỗng [] | Không tạo index entry cho hàng |
| Biểu thức tạo ra SQL NULL | Có một index entry chứa NULL trỏ tới hàng |
| Cột JSON/typed array là SQL NULL | InnoDB lưu một entry NULL trỏ tới hàng |
| Phần tử JSON null trong mảng | Không được phép; phát sinh lỗi Invalid JSON value |

Ví dụ:

~~~json
{"zip_codes": []}
~~~

Hàng không có index entry cho zip_codes. Đây là điều hợp lý nếu truy vấn membership chỉ tìm một giá trị cụ thể, vì mảng rỗng không có phần tử nào.

Nếu JSON path không tồn tại, biểu thức có thể trả về SQL NULL. Cần phân biệt trường hợp path không có dữ liệu với mảng rỗng.

Không đưa JSON null vào mảng được index:

~~~json
{"zip_codes": [70001, null, 70003]}
~~~

Hãy kiểm tra và chuẩn hóa dữ liệu trước khi tạo index. Nếu ứng dụng cần biểu diễn “không biết”, “chưa có dữ liệu” hoặc “không áp dụng”, cần chọn quy ước rõ ràng giữa SQL NULL, thiếu path và array rỗng.

### SQL NULL khác JSON null

- SQL NULL là trạng thái NULL của SQL expression/cột.
- JSON null là literal null nằm bên trong JSON document.
- MVI có thể tạo một index entry NULL khi biểu thức array trả SQL NULL.
- JSON null như một phần tử của indexed array bị cấm.

Không gộp các trường hợp này thành một quy tắc duy nhất trong validation hoặc báo cáo.

## 12. Giới hạn số phần tử trên mỗi hàng

MVI tạo nhiều index record cho một hàng. Tổng độ dài key value được tạo ra cho một hàng bị giới hạn bởi lượng dữ liệu có thể lưu trên một undo log page: 65.221 bytes theo tài liệu MySQL 9.7.

Không có một con số phần tử cố định áp dụng cho mọi kiểu dữ liệu. Số lượng phần tử tối đa phụ thuộc kích thước từng giá trị. Tài liệu ghi nhận thử nghiệm có thể chứa đến 1.604 integer key cho một hàng, nhưng đây không phải giới hạn chung được bảo đảm cho mọi schema.

Khi vượt giới hạn, MySQL có thể trả lỗi dạng:

~~~text
ERROR 3905 (HY000):
Exceeded max number of values per record for multi-valued index
~~~

Hệ quả thiết kế:

- Không dùng MVI cho array không giới hạn số phần tử.
- Xác định maximum array length ở tầng ứng dụng.
- Đo kích thước thực tế của phần tử.
- Theo dõi lỗi insert/update khi array phát triển.
- Chuyển sang bảng con nếu một hàng có thể chứa hàng nghìn hoặc hàng chục nghìn phần tử với tần suất thay đổi cao.

Giới hạn byte của index là giới hạn vật lý quan trọng, không chỉ là vấn đề hiệu năng.

## 13. Giới hạn kiểu dữ liệu, charset và collation

Multi-valued key part phải là một JSON expression được CAST sang SQL data type ARRAY.

Các lưu ý:

- Không CAST sang BINARY ARRAY.
- Không CAST sang JSON ARRAY.
- Với chuỗi, chỉ một số tổ hợp charset/collation được hỗ trợ.
- Các tổ hợp được tài liệu MySQL 9.7 nêu gồm binary charset với binary collation mặc định và utf8mb4 với collation mặc định utf8mb4_0900_as_cs.
- Không dùng USING HASH; InnoDB sử dụng B-tree.
- Không có index prefix cho MVI.

Nếu cần index mảng chuỗi, cần kiểm tra collation thực tế của biểu thức và kiểu đích. Không mặc định rằng mọi collation utf8mb4 đều được chấp nhận.

Ví dụ thiết kế array số nguyên thường ít rắc rối hơn về collation:

~~~sql
CREATE INDEX idx_zip_codes
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

Với array chuỗi, cần kiểm tra charset/collation và quy tắc so sánh chữ hoa/chữ thường trước khi tạo index.

## 14. Tạo MVI không hỗ trợ online index creation

Một giới hạn vận hành rất quan trọng: online creation của multi-valued index không được hỗ trợ. Tạo MVI sử dụng ALGORITHM=COPY.

Điều đó có nghĩa thao tác tạo index có thể phải copy/rebuild bảng, tiêu thụ đáng kể:

- Disk space.
- I/O.
- CPU.
- Thời gian giữ metadata lock ở các giai đoạn liên quan.
- Tài nguyên cho việc tạo index entry từ mọi phần tử JSON.

Trước khi tạo MVI trên bảng lớn:

1. Xác định số hàng và kích thước JSON document.
2. Ước lượng tổng số phần tử cần index.
3. Kiểm tra dung lượng đĩa cho thao tác copy/rebuild.
4. Đánh giá tải I/O và replication lag.
5. Thử trên bản sao dữ liệu có kích thước gần production.
6. Lên lịch triển khai trong maintenance window phù hợp.
7. Chuẩn bị rollback hoặc kế hoạch phục hồi nếu DDL thất bại.

Không giả định CREATE INDEX MVI có cùng online DDL behavior với một secondary index thông thường.

Sau khi tạo index thành công, cập nhật thống kê bằng ANALYZE TABLE khi phù hợp và xác minh kế hoạch truy vấn.

## 15. Chi phí ghi và cập nhật JSON array

MVI tăng tốc một số truy vấn đọc, nhưng mỗi phần tử được index làm tăng số index record.

Ví dụ:

- Hàng A có 2 zip code: tạo khoảng 2 index entries.
- Hàng B có 20 zip code: tạo khoảng 20 index entries.
- Hàng C có 200 zip code: tạo khoảng 200 index entries.

Khi UPDATE JSON array, InnoDB phải cập nhật các index entry tương ứng. Nếu array thay đổi thường xuyên và có nhiều phần tử, chi phí ghi có thể đáng kể.

Cần đánh giá:

- Số phần tử trung bình và percentile cao.
- Tần suất INSERT/UPDATE.
- Tỷ lệ thay đổi phần tử trong array.
- Dung lượng index.
- Lock contention và write amplification.
- Tốc độ truy vấn membership được cải thiện bao nhiêu.

Không thêm MVI cho mọi mảng JSON. Chỉ index các path có workload tìm kiếm thực sự.

## 16. Khi nào nên dùng MVI, khi nào nên chuẩn hóa?

MVI phù hợp khi:

- Một hàng có một tập nhỏ hoặc vừa các scalar value.
- Ứng dụng thường tìm hàng bằng một phần tử trong array.
- Quan hệ không cần foreign key cho từng phần tử.
- Không cần range scan, ordering hoặc grouping theo từng phần tử.
- JSON array là một phần của document linh hoạt và được cập nhật theo hàng.
- Truy vấn dùng MEMBER OF(), JSON_CONTAINS() hoặc JSON_OVERLAPS().

Bảng quan hệ con phù hợp hơn khi:

- Mỗi phần tử có thuộc tính riêng.
- Cần foreign key và referential integrity.
- Cần UNIQUE/constraint theo từng phần tử với ngữ nghĩa quan hệ rõ ràng.
- Cần range query hoặc sort theo giá trị phần tử.
- Cần join thường xuyên với bảng khác.
- Cần thống kê, group by hoặc phân trang theo từng phần tử.
- Array có số lượng phần tử lớn hoặc thay đổi liên tục.
- Cần truy vấn theo nhiều chiều và nhiều predicate khác nhau.

| Tiêu chí | JSON array + MVI | Bảng con quan hệ |
|---|---|---|
| Tìm một phần tử | Tốt với predicate được hỗ trợ | Tốt với B-tree index |
| Tìm nhiều phần tử cùng lúc | MEMBER OF/CONTAINS/OVERLAPS | JOIN/GROUP BY |
| Foreign key cho phần tử | Không | Có |
| Range scan theo phần tử | Không | Có |
| ORDER BY theo phần tử | Không hỗ trợ qua MVI | Có |
| Covering index | Không | Có thể |
| Dữ liệu linh hoạt | Cao | Schema rõ ràng hơn |
| Update một phần tử | Cập nhật JSON và MVI | INSERT/UPDATE/DELETE hàng con |
| Array rất lớn | Có giới hạn số byte/index entry | Dễ mở rộng và phân trang hơn |

Một nguyên tắc hữu ích: nếu phần tử trong array thực chất là một quan hệ nghiệp vụ độc lập, hãy cân nhắc mô hình bảng con trước khi chọn JSON array.

## 17. Bài thực hành: tạo MVI và kiểm tra ba predicate

Lab sử dụng bảng khách hàng lưu mảng mã bưu chính. Dữ liệu được cố ý thiết kế để phân biệt MEMBER OF, JSON_CONTAINS và JSON_OVERLAPS.

### Bước 1: tạo database và bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_mvi_lab;
USE mysql_mvi_lab;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id INT NOT NULL,
    profile JSON NOT NULL,
    KEY idx_tenant (tenant_id)
) ENGINE=InnoDB;
~~~

### Bước 2: nạp dữ liệu

~~~sql
INSERT INTO customers (customer_id, tenant_id, profile)
VALUES
    (1, 10, '{"name":"Lan","zip_codes":[70000,70001,70003]}'),
    (2, 10, '{"name":"Minh","zip_codes":[70001,70002]}'),
    (3, 10, '{"name":"An","zip_codes":[70003]}'),
    (4, 20, '{"name":"Binh","zip_codes":[70002,70004]}'),
    (5, 20, '{"name":"Hoa","zip_codes":[]}'),
    (6, 20, '{"name":"Nam","zip_codes":[70001,70003]}');
~~~

### Bước 3: truy vấn trước khi tạo MVI

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Quan sát access type, possible_keys, key và rows. Vì bảng lab nhỏ, optimizer có thể chọn table scan.

### Bước 4: tạo multi-valued index

~~~sql
CREATE INDEX idx_customer_zip
ON customers (
    (CAST(profile->'$.zip_codes' AS UNSIGNED ARRAY))
);
~~~

### Bước 5: cập nhật thống kê

~~~sql
ANALYZE TABLE customers;
~~~

### Bước 6: kiểm tra MEMBER OF

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes')
ORDER BY customer_id;
~~~

Kết quả mong đợi: khách hàng 1, 2 và 6.

### Bước 7: kiểm tra JSON_CONTAINS

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
)
ORDER BY customer_id;
~~~

Kết quả mong đợi: khách hàng 1 và 6 vì cả hai đều có đủ hai mã.

### Bước 8: kiểm tra JSON_OVERLAPS

~~~sql
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
)
ORDER BY customer_id;
~~~

Kết quả mong đợi: khách hàng 1, 2, 3 và 6 vì mỗi khách có ít nhất một trong hai mã.

### Bước 9: kiểm tra EXPLAIN sau khi có index

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

Tiếp tục kiểm tra JSON_CONTAINS và JSON_OVERLAPS:

~~~sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_CONTAINS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);

EXPLAIN
SELECT customer_id
FROM customers
WHERE JSON_OVERLAPS(
    profile->'$.zip_codes',
    CAST('[70001,70003]' AS JSON)
);
~~~

Nếu optimizer chọn MVI, trường key sẽ hiển thị idx_customer_zip và access type có thể là range. Kết quả cụ thể phụ thuộc thống kê, kích thước bảng và selectivity. Bảng lab chỉ có vài hàng nên không bắt buộc optimizer chọn index.

### Bước 10: quan sát hành vi mảng rỗng

Khách hàng 5 có zip_codes là mảng rỗng. Truy vấn:

~~~sql
SELECT customer_id
FROM customers
WHERE 70001 MEMBER OF (profile->'$.zip_codes');
~~~

không trả customer_id 5. Mảng rỗng không có index entry và không chứa phần tử cần tìm.

### Bước 11: cập nhật array

~~~sql
UPDATE customers
SET profile = JSON_SET(
    profile,
    '$.zip_codes',
    JSON_ARRAY(70001, 70005)
)
WHERE customer_id = 5;
~~~

Truy vấn lại:

~~~sql
SELECT customer_id
FROM customers
WHERE 70005 MEMBER OF (profile->'$.zip_codes');
~~~

Khách hàng 5 giờ được tìm thấy. InnoDB cập nhật MVI tương ứng với thay đổi JSON.

### Bước 12: kiểm tra metadata index

~~~sql
SHOW INDEX FROM customers;
~~~

Kiểm tra tên index, non_unique, seq_in_index và biểu thức index. Có thể dùng SHOW CREATE TABLE để xem định nghĩa đầy đủ.

~~~sql
SHOW CREATE TABLE customers;
~~~

### Dọn dẹp

~~~sql
DROP DATABASE mysql_mvi_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tạo được MVI | Bảng không dùng InnoDB | Dùng InnoDB |
| CAST ARRAY báo lỗi | JSON path hoặc kiểu đích không hợp lệ | Kiểm tra expression và kiểu SQL ARRAY |
| Không tìm thấy giá trị dù nhìn thấy trong JSON | Khác kiểu string/numeric hoặc sai JSON path | Chuẩn hóa kiểu phần tử và kiểm tra path |
| JSON null làm INSERT/UPDATE lỗi | JSON null không được phép trong indexed array | Loại JSON null hoặc định nghĩa quy tắc dữ liệu khác |
| Hàng có array rỗng không xuất hiện trong index lookup | Array rỗng không tạo index entry | Đây là hành vi bình thường; kiểm tra nghiệp vụ |
| EXPLAIN không chọn MVI | Bảng nhỏ, selectivity thấp, thống kê hoặc predicate không phù hợp | ANALYZE TABLE, kiểm tra WHERE và đo trên dữ liệu thực |
| Query JSON_CONTAINS trả nhiều hàng hơn dự kiến | Nhầm semantics all-elements với any-element | Dùng JSON_OVERLAPS nếu chỉ cần một phần tử chung |
| Query JSON_OVERLAPS trả nhiều hàng hơn dự kiến | Chỉ cần một phần tử chung để khớp | Dùng JSON_CONTAINS nếu cần tất cả phần tử candidate |
| Không dùng được MVI cho ORDER BY | MVI không hỗ trợ ordering | Sort kết quả hoặc dùng bảng con |
| Query range không dùng MVI | MVI không hỗ trợ range scan | Chuẩn hóa thành bảng con có B-tree index |
| Muốn tạo foreign key từ phần tử JSON | MVI không tham gia foreign key specification | Tạo bảng con và FK |
| Muốn covering index | MVI không hỗ trợ index-only scan | Thiết kế truy vấn/bảng quan hệ phù hợp |
| Không tạo được hai MVI trong cùng index | Chỉ một multi-valued key part cho mỗi index | Tạo hai index riêng hoặc chuẩn hóa dữ liệu |
| Tạo index làm bảng copy lâu | MVI online creation không được hỗ trợ, dùng ALGORITHM=COPY | Lập kế hoạch dung lượng và maintenance window |
| Array quá lớn làm DML lỗi | Vượt giới hạn tổng byte index value mỗi hàng | Giới hạn số phần tử hoặc dùng bảng con |
| MVI chuỗi không tạo được | Charset/collation không được hỗ trợ | Kiểm tra binary hoặc utf8mb4_0900_as_cs |
| DML chậm sau khi thêm MVI | Mỗi phần tử tạo index entry và cần cập nhật khi JSON đổi | Đánh giá write amplification và loại bỏ index ít dùng |

## 19. Checklist thiết kế và vận hành MVI

- [ ] Server chạy MySQL 8.0.17 trở lên.
- [ ] Bảng dùng InnoDB.
- [ ] JSON path được chọn đúng và ổn định.
- [ ] Phần tử trong array có kiểu scalar nhất quán.
- [ ] Kiểu SQL ARRAY phù hợp với dữ liệu và query.
- [ ] Dữ liệu không chứa JSON null trong indexed array.
- [ ] Đã hiểu khác biệt giữa SQL NULL, JSON null và array rỗng.
- [ ] Predicate nằm trong WHERE và thuộc nhóm MEMBER OF, JSON_CONTAINS hoặc JSON_OVERLAPS.
- [ ] Đã chọn đúng semantics all-elements hay any-element.
- [ ] Đã kiểm tra biểu thức JSON trong query phù hợp với index definition.
- [ ] Mỗi index chỉ có một multi-valued key part.
- [ ] Không kỳ vọng MVI hỗ trợ ORDER BY, range scan hoặc covering.
- [ ] Không dùng MVI làm primary key hoặc foreign key.
- [ ] Đã đánh giá có cần composite index với key part đơn trị hay không.
- [ ] Đã ước lượng số phần tử và tổng kích thước key value trên mỗi hàng.
- [ ] Đã đánh giá write amplification khi JSON array thay đổi.
- [ ] Đã kiểm tra charset/collation nếu index chuỗi.
- [ ] Đã tính đến ALGORITHM=COPY và dung lượng khi tạo index.
- [ ] Đã chạy ANALYZE TABLE khi phù hợp.
- [ ] Đã kiểm tra EXPLAIN trên dữ liệu gần production.
- [ ] Đã cân nhắc bảng con nếu cần FK, range, ordering, join hoặc phân tích theo phần tử.

## 20. Nguyên tắc cần ghi nhớ

1. MVI là secondary index của InnoDB dành cho JSON array.
2. MVI tạo nhiều index record trỏ về một hàng dữ liệu, theo quan hệ N:1.
3. MVI có từ MySQL 8.0.17.
4. Tạo MVI bằng CAST(JSON expression AS SQL_TYPE ARRAY).
5. Optimizer có thể sử dụng MVI cho MEMBER OF(), JSON_CONTAINS() và JSON_OVERLAPS() trong WHERE.
6. JSON_CONTAINS yêu cầu mọi phần tử candidate được chứa; JSON_OVERLAPS chỉ cần một phần tử chung.
7. MEMBER OF so sánh phần tử theo kiểu JSON; không dựa vào chuyển đổi string/numeric tự động.
8. Mỗi index chỉ có một multi-valued key part, nhưng có thể kết hợp với key part đơn trị.
9. MVI không hỗ trợ ordering, range scan, index-only scan hoặc covering index.
10. MVI không thể là primary key và không dùng trong foreign key specification.
11. Mảng rỗng không tạo index entry; JSON null trong indexed array bị cấm.
12. Tổng độ dài key value trên một hàng bị giới hạn bởi undo log page; không có một số phần tử cố định áp dụng cho mọi kiểu.
13. Tạo MVI không hỗ trợ online index creation và dùng ALGORITHM=COPY.
14. Mỗi phần tử tăng chi phí lưu trữ và cập nhật index.
15. Nếu cần quan hệ, constraint, range, ordering hoặc phân tích theo phần tử, hãy cân nhắc bảng con chuẩn hóa.

## Tài liệu tham khảo chính thức

Các cú pháp và giới hạn trong bài được đối chiếu với **MySQL 9.7 Reference Manual** và release notes MySQL 8.0:

1. [MySQL 9.7 — CREATE INDEX: Multi-Valued Indexes](https://dev.mysql.com/doc/refman/9.7/en/create-index.html): cú pháp CAST ARRAY, composite index, predicate hỗ trợ, nullability và các giới hạn của MVI.
2. [MySQL 9.7 — Functions That Search JSON Values](https://dev.mysql.com/doc/refman/9.7/en/json-search-functions.html): MEMBER OF(), JSON_CONTAINS(), JSON_OVERLAPS() và semantics của phép tìm kiếm.
3. [MySQL 9.7 — CREATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table.html): khai báo key part và multi-valued index trong CREATE TABLE.
4. [MySQL 9.7 — Multiple-Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/multiple-column-indexes.html): composite index và leftmost prefix.
5. [MySQL 8.0 Release Notes — What Is New in MySQL 8.0](https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html): MVI được InnoDB hỗ trợ từ MySQL 8.0.17.
6. [MySQL 8.0.17 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-17.html): giới thiệu MVI, CAST ARRAY và các predicate optimizer hỗ trợ.

