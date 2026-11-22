# Số nguyên, số thập phân chính xác và số dấu phẩy động trong SQL

## 1. Vì sao chọn kiểu số là một quyết định nghiệp vụ?

Giả sử hệ thống bán hàng lưu số lượng sản phẩm, đơn giá và khối lượng vận chuyển:

- Số lượng hàng tồn kho là `12` chiếc, không có ý nghĩa nếu bằng `12.7` chiếc.
- Đơn giá `12500.25` đồng phải được tính và đối soát theo quy tắc tiền tệ rõ ràng.
- Khối lượng đo từ cảm biến có thể là `0.137482` kg, mang sai số thiết bị và thường được xử lý bằng phép tính gần đúng.

Ba đại lượng đều là “số”, nhưng không nên mặc định dùng chung một kiểu dữ liệu. SQL phân biệt ba họ kiểu quan trọng:

| Họ kiểu | Ví dụ tên kiểu phổ biến | Bản chất | Thường dùng cho |
| --- | --- | --- | --- |
| **Số nguyên** | `SMALLINT`, `INTEGER` / `INT`, `BIGINT` | Giá trị nguyên trong một miền hữu hạn, biểu diễn chính xác | Số lượng, số thứ tự, bộ đếm, ID |
| **Số thập phân chính xác** | `DECIMAL(p, s)`, `NUMERIC(p, s)` | Giá trị thập phân có độ chính xác và quy mô chữ số xác định | Tiền, thuế suất cần quy định thang số, số liệu kế toán |
| **Số dấu phẩy động** | `REAL`, `FLOAT`, `DOUBLE PRECISION` | Biểu diễn xấp xỉ số thực, thường theo dấu phẩy động nhị phân | Đo lường, mô phỏng, thống kê khoa học |

Khác biệt lớn nhất là **lưu giá trị có chính xác theo hệ thập phân hay không**, phạm vi biểu diễn, khả năng tràn số và quy tắc làm tròn. Chọn kiểu hợp lý ngay từ thiết kế giúp tránh sai lệch âm thầm khi tính tổng, so sánh hoặc chuyển dữ liệu giữa SQL và ứng dụng.

## 2. Số nguyên: SMALLINT, INTEGER và BIGINT

### 2.1. Giá trị và miền biểu diễn

Các kiểu số nguyên lưu số không có phần thập phân. Trong PostgreSQL và nhiều DBMS thông dụng, miền của số nguyên **có dấu** là:

| Kiểu SQL | Số bit phổ biến | Miền giá trị có dấu | Ví dụ |
| --- | ---: | --- | --- |
| `SMALLINT` | 16 | −32.768 đến 32.767 | Số thứ tự nhỏ, trạng thái được mã hóa bằng số |
| `INTEGER` hoặc `INT` | 32 | −2.147.483.648 đến 2.147.483.647 | Số lượng, bộ đếm vừa phải |
| `BIGINT` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | ID hoặc bộ đếm có thể tăng rất lớn |

Các độ rộng trên là đặc điểm của nhiều hệ quản trị hiện hành, **không nên xem là cam kết chung cho mọi SQL dialect**. Một số hệ, chẳng hạn MySQL, còn có biến thể `UNSIGNED` với miền không âm rộng hơn; `UNSIGNED` không phải lựa chọn di động giữa tất cả các DBMS.

Khi định nghĩa cột:

~~~sql
CREATE TABLE warehouse_stock (
    product_id   BIGINT PRIMARY KEY,
    quantity     INTEGER NOT NULL,
    rack_number  SMALLINT,
    CONSTRAINT ck_quantity_nonnegative CHECK (quantity >= 0)
);
~~~

`quantity` là số nguyên vì không có “nửa sản phẩm” trong nghiệp vụ này. Ràng buộc `CHECK (quantity >= 0)` thể hiện quy tắc **không âm**; bản thân `INTEGER` vẫn cho phép số âm. `NOT NULL` ngăn giá trị chưa biết, còn `PRIMARY KEY` xác định mã sản phẩm duy nhất.

### 2.2. Tràn số và giới hạn kiểu

Kiểu nguyên không thể chứa giá trị vượt miền của nó. Ví dụ, `INTEGER` 32-bit không thể lưu `2147483648`:

~~~sql
-- PostgreSQL: giá trị 2147483648 vượt miền INTEGER.
SELECT CAST(2147483648 AS INTEGER);

-- Đổi sang BIGINT để có đủ miền biểu diễn:
SELECT CAST(2147483648 AS BIGINT) AS large_count;
~~~

Phép cộng cũng có thể tràn nếu **kiểu của biểu thức** không đủ lớn, dù cột nhận kết quả sau đó là `BIGINT`:

~~~sql
-- Ép kiểu trước khi cộng để phép toán diễn ra trong miền BIGINT.
SELECT CAST(2147483647 AS BIGINT) + 1 AS next_value;
~~~

Trên các DBMS thông dụng, phép toán vượt miền có thể báo lỗi hoặc xử lý theo chế độ cấu hình. Không nên trông cậy vào hành vi tràn số cụ thể khi viết SQL chạy đa hệ.

### 2.3. Phép chia số nguyên không nhất thiết trả số thập phân

Với PostgreSQL:

~~~sql
SELECT
    5 / 2 AS integer_division,
    5.0 / 2 AS decimal_division;
~~~

Kết quả logic là `integer_division = 2` và `decimal_division = 2.5`. Ở phép đầu, hai toán hạng được xử lý theo phép chia số nguyên và phần thập phân bị bỏ. Ở phép sau, giá trị `5.0` được xử lý theo kiểu số thập phân phù hợp. **Hệ SQL khác có thể suy luận và chuyển kiểu khác**, nên khi muốn lấy tỉ lệ, hãy thể hiện ý định:

~~~sql
SELECT CAST(5 AS DECIMAL(10, 2)) / 2 AS ratio;
~~~

Phép chia cho 0 cần được xử lý riêng. Với dữ liệu đầu vào có mẫu số có thể bằng 0, cách viết như `numerator / NULLIF(denominator, 0)` cho kết quả `NULL` khi mẫu số bằng 0 trên các DBMS hỗ trợ `NULLIF`, thay vì cố chia cho 0. Cần quyết định ở tầng nghiệp vụ nên hiển thị “không xác định”, báo lỗi, hay áp dụng quy tắc khác.

### 2.4. Số nguyên dùng làm ID không phải lúc nào cũng đồng nghĩa với số thứ tự liên tục

`INTEGER` và `BIGINT` thường được dùng cho khóa chính. Nhiều DBMS cung cấp cơ chế sinh ID như `IDENTITY`, `AUTO_INCREMENT` hoặc sequence. Những cơ chế này có thể tạo **khoảng trống** khi transaction rollback, xóa dữ liệu hoặc phân phối ID đồng thời. Vì thế không nên dùng khóa tự tăng để suy ra “không thiếu số nào” hoặc làm bộ đếm nghiệp vụ phải liên tục.

## 3. Số thập phân chính xác: DECIMAL và NUMERIC

### 3.1. Precision và scale là gì?

Kiểu `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` khai báo:

- **`p` (precision):** tổng số chữ số thập phân được phép biểu diễn.
- **`s` (scale):** số chữ số nằm bên phải dấu thập phân.
- Với dạng thông dụng `0 <= s <= p`, có tối đa `p - s` chữ số bên trái dấu thập phân.

Ví dụ `DECIMAL(7, 2)` có bảy chữ số có nghĩa, trong đó hai chữ số nằm sau dấu thập phân; miền giá trị theo giới hạn chữ số là **−99.999,99 đến 99.999,99**. Dấu âm và dấu thập phân không được đếm là chữ số của `precision`.

| Khai báo | Số chữ số phần nguyên tối đa | Số chữ số phần thập phân | Một giá trị hợp lệ |
| --- | ---: | ---: | ---: |
| `DECIMAL(5, 2)` | 3 | 2 | `999.99` |
| `DECIMAL(10, 2)` | 8 | 2 | `12345678.90` |
| `DECIMAL(12, 4)` | 8 | 4 | `1234.5678` |
| `NUMERIC(19, 4)` | 15 | 4 | `9876543210.1234` |

Theo SQL tiêu chuẩn, `DECIMAL` và `NUMERIC` đều là họ kiểu thập phân chính xác nhưng có một số khác biệt quy định về precision tối thiểu; PostgreSQL và nhiều DBMS thường xử lý hai tên rất giống nhau trong thực tế. Một số hệ cho phép `NUMERIC` không ghi `p, s`, số khác cần khai báo rõ độ rộng hoặc có giới hạn khác nhau. Những mở rộng như scale âm của PostgreSQL không nên dùng nếu mục tiêu là SQL di động.

### 3.2. Vì sao DECIMAL phù hợp cho tiền?

Với số tiền viết ở hệ thập phân, kiểu chính xác có thể lưu nguyên vẹn các giá trị trong miền/scale đã chọn:

~~~sql
CREATE TABLE order_lines (
    line_id        BIGINT PRIMARY KEY,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    discount_rate  DECIMAL(7, 4) NOT NULL DEFAULT 0
        CHECK (discount_rate BETWEEN 0 AND 1)
);

INSERT INTO order_lines (line_id, quantity, unit_price, discount_rate)
VALUES
    (1, 3, 19.90, 0.1000),
    (2, 2, 0.10,  0.0000);
~~~

`19.90`, `0.10` và `0.1000` có thể được lưu với thang thập phân đã khai báo. Đối với đơn giá và tổng tiền, độ chính xác theo **chữ số thập phân** thường quan trọng hơn tốc độ của phép tính xấp xỉ.

~~~sql
SELECT
    line_id,
    quantity,
    unit_price,
    quantity * unit_price AS gross_amount
FROM order_lines
ORDER BY line_id;
~~~

Với dữ liệu trên, `gross_amount` của dòng 1 là `59.70` và dòng 2 là `0.20`. Tuy nhiên, “chính xác” không đồng nghĩa với “không bao giờ cần làm tròn”: thuế, chiết khấu và phép chia có thể tạo ra nhiều chữ số hơn scale lưu trữ.

### 3.3. Làm tròn, ép kiểu và tràn precision

Xét kiểu `NUMERIC(5, 2)`, chỉ lưu được tối đa ba chữ số trước dấu thập phân:

~~~sql
-- PostgreSQL: làm tròn đến hai chữ số thập phân.
SELECT CAST(12.345 AS NUMERIC(5, 2)) AS rounded_value;
-- Kết quả: 12.35
~~~

Trong PostgreSQL, khi chuyển sang `NUMERIC(p, s)`, giá trị nhiều chữ số sau dấu thập phân được làm tròn theo scale; nếu phần nguyên sau khi làm tròn vượt giới hạn, câu lệnh lỗi:

~~~sql
-- PostgreSQL: kết quả làm tròn sẽ là 1000.00,
-- nhưng NUMERIC(5, 2) chỉ chứa phần nguyên đến 999.
SELECT CAST(999.995 AS NUMERIC(5, 2));
-- Numeric field overflow
~~~

Hành vi chuyển kiểu và làm tròn khi gán vào cột có thể khác giữa các DBMS và chế độ strict/non-strict; trong nghiệp vụ tiền tệ nên kiểm soát rõ quy tắc làm tròn, không mặc định mọi hệ sẽ xử lý giống nhau.

Khi phải chỉ định số chữ số sau dấu thập phân trong một phép tính, có thể dùng `ROUND`:

~~~sql
-- PostgreSQL, đối số numeric: làm tròn nửa đơn vị ra xa số 0.
SELECT ROUND(CAST(10.005 AS NUMERIC), 2) AS amount;
-- 10.01
~~~

Chính sách kế toán có thể yêu cầu làm tròn khác, chẳng hạn *round half to even* (làm tròn về số chẵn khi đúng điểm giữa). Chính sách này phải được xác định và hiện thực nhất quán ở DB, ứng dụng và hệ thống thanh toán; không nên giả định `ROUND` của mọi DBMS là như nhau cho mọi kiểu dữ liệu.

### 3.4. “Số chính xác” vẫn có giới hạn

`DECIMAL(p, s)` lưu chính xác các giá trị thập phân **phù hợp precision và scale**. Điều này không làm cho mọi phép toán đều có kết quả thập phân hữu hạn. Chẳng hạn `1 / 3` có biểu diễn thập phân vô hạn; DBMS phải chọn độ chính xác/scale cho kết quả hoặc thực hiện làm tròn khi ép về kiểu lưu trữ. Phép nhân nhiều giá trị lớn cũng có thể tạo ra kết quả cần nhiều chữ số hơn cột đích.

Vì thế, khi thiết kế tiền tệ cần quyết định:

1. **Đơn vị lưu trữ:** đồng, xu, cent, điểm thưởng hay đơn vị rất nhỏ.
2. **Scale lưu trữ:** ví dụ `DECIMAL(19, 4)` nếu cần bốn chữ số sau dấu thập phân.
3. **Thời điểm làm tròn:** từng dòng, từng loại thuế, hay sau khi tổng hợp.
4. **Quy tắc làm tròn:** theo yêu cầu pháp lý/nghiệp vụ của từng loại tiền và loại giao dịch.
5. **Miền lớn nhất:** tổng tiền tối đa và việc cộng nhiều dòng có vượt precision hay không.

Đặc biệt, các loại tiền không có cùng số chữ số thập phân sử dụng trong thanh toán. Không nên áp dụng mặc định “mọi tiền tệ đều có hai chữ số thập phân”.

## 4. Số dấu phẩy động: REAL, FLOAT, DOUBLE PRECISION

### 4.1. Lưu gần đúng thay vì chính xác thập phân

Các kiểu dấu phẩy động trong nhiều hệ quản trị dựa trên biểu diễn nhị phân tương tự IEEE 754. Chúng lưu giá trị bằng các thành phần gần với **dấu, phần định trị (significand)** và **số mũ (exponent)**. Nhờ đó chúng biểu diễn được số rất lớn hoặc rất nhỏ với dung lượng lưu trữ thường cố định, nhưng chỉ giữ được một số chữ số có nghĩa hữu hạn.

| Kiểu thường gặp | Cỡ lưu trữ thường gặp | Mức chính xác xấp xỉ khi theo IEEE 754 | Ghi chú |
| --- | ---: | --- | --- |
| `REAL` | 4 byte | Khoảng 6–7 chữ số thập phân có nghĩa | Dấu phẩy động độ chính xác đơn |
| `DOUBLE PRECISION` | 8 byte | Khoảng 15–16 chữ số thập phân có nghĩa | Dấu phẩy động độ chính xác kép |
| `FLOAT` hoặc `FLOAT(p)` | Tùy DBMS | Tùy hệ và tham số precision | Có thể ánh xạ về REAL hoặc DOUBLE |

Độ rộng, miền, cách ánh xạ `FLOAT(p)` và hỗ trợ số đặc biệt (`NaN`, vô cực) khác nhau giữa các SQL dialect. Không nên suy ra `FLOAT` trong mọi DB đều là “64-bit double”.

### 4.2. Vì sao 0.1 + 0.2 có thể không bằng 0.3?

Phân số thập phân `0.1` không có biểu diễn nhị phân hữu hạn, giống như `1/3` không có biểu diễn thập phân hữu hạn. Khi lưu bằng dấu phẩy động nhị phân, DBMS phải chọn một số nhị phân gần nhất trong miền độ chính xác của kiểu.

Trong PostgreSQL, có thể quan sát:

~~~sql
SELECT
    CAST(0.1 AS DOUBLE PRECISION)
      + CAST(0.2 AS DOUBLE PRECISION)
      = CAST(0.3 AS DOUBLE PRECISION) AS float_equal,
    CAST(0.1 AS NUMERIC(10, 2))
      + CAST(0.2 AS NUMERIC(10, 2))
      = CAST(0.3 AS NUMERIC(10, 2)) AS decimal_equal;
~~~

Trong môi trường dùng số nhị phân IEEE 754 thông thường, `float_equal` là `FALSE` còn `decimal_equal` là `TRUE`. Phần hiển thị kết quả dấu phẩy động có thể làm tròn thành `0.3`, khiến sai lệch bên trong khó nhìn ra. Đây là đặc tính biểu diễn số, **không phải lỗi riêng của SQL**.

Để so sánh hai kết quả đo gần đúng, có thể chọn khoảng dung sai (**tolerance**) phù hợp với đơn vị và miền giá trị:

~~~sql
-- Ví dụ có chủ đích dùng dung sai tuyệt đối ở miền giá trị nhỏ.
SELECT
    ABS(
        CAST(0.1 AS DOUBLE PRECISION) +
        CAST(0.2 AS DOUBLE PRECISION) -
        CAST(0.3 AS DOUBLE PRECISION)
    ) < 1e-9 AS approximately_equal;
~~~

`1e-9` trong ví dụ chỉ có ý nghĩa minh họa. Với dữ liệu thực, phải chọn **dung sai tuyệt đối và/hoặc tương đối** dựa vào độ lớn giá trị, độ chính xác thiết bị, yêu cầu nghiệp vụ và nguy cơ tích lũy sai số. Không có một epsilon cố định đúng cho mọi phép đo.

### 4.3. Sai số tích lũy và thứ tự phép tính

Với số dấu phẩy động, việc cộng và nhân nhiều số có thể dẫn đến sai số làm tròn. Thậm chí:

~~~text
(a + b) + c
~~~

và

~~~text
a + (b + c)
~~~

không nhất thiết cho hai kết quả bit-for-bit giống nhau khi tính bằng dấu phẩy động hữu hạn. DBMS có thể sử dụng kế hoạch thực thi song song hoặc thứ tự tổng hợp khác nhau, dẫn đến chênh lệch rất nhỏ khi tính `SUM` trên cột float trong một số trường hợp.

Điều này đặc biệt quan trọng khi:

- So sánh trực tiếp bằng toán tử `=` một kết quả tính toán với một hằng thập phân.
- Cộng nhiều khoản tiền bằng `FLOAT` rồi đòi hỏi khớp từng đơn vị nhỏ nhất.
- Tính trên các số rất lớn và rất nhỏ cùng lúc, nơi phần giá trị nhỏ có thể bị mất do giới hạn chữ số có nghĩa.
- Chuyển qua lại giữa `DECIMAL` và `FLOAT` và kỳ vọng giữ nguyên từng chữ số thập phân.

Với đo đạc hoặc khoa học, sai số có thể là phần tự nhiên của bài toán; cần mô hình hóa và đặt dung sai. Với sổ cái và đối soát tiền, nên ưu tiên decimal exact hoặc một thiết kế số nguyên theo đơn vị tiền nhỏ nhất.

## 5. Thực hành bằng một bảng chứa đủ ba họ kiểu

Ví dụ sau dùng PostgreSQL để xác định kiểu một cách rõ ràng; khi chạy trên DBMS khác có thể phải đổi tên kiểu hoặc cú pháp giá trị luận lý, nhưng các nguyên lý phân loại vẫn giữ nguyên.

~~~sql
CREATE TABLE catalog_items (
    item_id            BIGINT PRIMARY KEY,
    sku                VARCHAR(30) NOT NULL UNIQUE,
    stock_units        INTEGER NOT NULL CHECK (stock_units >= 0),
    unit_price         NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    shipping_weight_kg DOUBLE PRECISION
);

INSERT INTO catalog_items (
    item_id, sku, stock_units, unit_price, shipping_weight_kg
)
VALUES
    (1, 'PEN',     10,   12500.25, 0.015),
    (2, 'MONITOR',  3, 3450000.00, 4.830),
    (3, 'CABLE',    0,   59000.10, 0.075);
~~~

Ý nghĩa các cột:

- `item_id` dùng `BIGINT` vì có thể tăng nhiều theo thời gian.
- `stock_units` dùng `INTEGER`; `CHECK` ngăn giá trị âm, `NOT NULL` ngăn chưa có số liệu.
- `unit_price` dùng `NUMERIC(12,2)` để giữ giá tiền ở scale hai chữ số cho **ví dụ này**.
- `shipping_weight_kg` dùng `DOUBLE PRECISION` để lưu số đo có tính gần đúng; cột cho phép `NULL` nếu chưa cân.

Tính tổng giá trị tồn kho theo từng mặt hàng:

~~~sql
SELECT
    sku,
    stock_units,
    unit_price,
    stock_units * unit_price AS inventory_value
FROM catalog_items
ORDER BY item_id;
~~~

| sku | stock_units | unit_price | inventory_value |
| --- | ---: | ---: | ---: |
| PEN | 10 | 12500.25 | 125002.50 |
| MONITOR | 3 | 3450000.00 | 10350000.00 |
| CABLE | 0 | 59000.10 | 0.00 |

Tổng giá trị tồn kho:

~~~sql
SELECT SUM(stock_units * unit_price) AS total_inventory_value
FROM catalog_items;
-- 10475002.50
~~~

Phép nhân giữa số lượng nguyên và giá `NUMERIC` tạo ra kết quả số học theo quy tắc kiểu của DBMS. Khi viết truy vấn nhiều hệ hoặc cần lưu kết quả vào cột khác, cần kiểm tra kiểu kết quả và scale, không chỉ nhìn phần văn bản hiển thị.

Thống kê khối lượng trung bình các sản phẩm **có số đo**:

~~~sql
SELECT AVG(shipping_weight_kg) AS average_weight_kg
FROM catalog_items
WHERE shipping_weight_kg IS NOT NULL;
~~~

`AVG` trên `DOUBLE PRECISION` trả một giá trị gần đúng; cách hiển thị chữ số có thể khác theo công cụ SQL. Nếu chưa có số đo, `NULL` không có nghĩa khối lượng bằng `0`; tự động thay bằng `0` có thể kéo trung bình xuống sai lệch.

## 6. Kết hợp nhiều kiểu trong một biểu thức

### 6.1. Ép kiểu tường minh bằng CAST

SQL có thể tự chuyển kiểu (**implicit conversion**) trong một số phép toán, nhưng mỗi DBMS có quy tắc khác nhau. Khi cần ý nghĩa nhất quán, hãy dùng `CAST(expression AS type)`.

~~~sql
-- PostgreSQL: phép chia nguyên và phép chia thập phân
SELECT
    7 / 2 AS quotient_integer,
    CAST(7 AS NUMERIC(10, 2)) / 2 AS quotient_decimal;
~~~

Kết quả đầu là `3` theo phép chia nguyên PostgreSQL; kết quả sau biểu diễn giá trị `3.5` theo kiểu thập phân. `CAST` được thực hiện **trước** phép chia, nên chọn đúng phép toán mong muốn. Nếu ép kiểu **sau** khi chia nguyên, phần thập phân đã mất:

~~~sql
SELECT CAST(7 / 2 AS NUMERIC(10, 2)) AS too_late;
-- PostgreSQL: 3.00, không phải 3.50
~~~

Lưu ý `CAST` từ float sang decimal không tạo lại độ chính xác thập phân đã mất ban đầu. Nếu nguồn đã là số xấp xỉ, việc chuyển kiểu chỉ chọn cách biểu diễn/làm tròn kết quả hiện có.

### 6.2. Phép tổng hợp và kiểu kết quả

Các hàm `SUM`, `AVG` và `COUNT` có thể trả kiểu khác với kiểu cột đầu vào. Chẳng hạn, PostgreSQL thường trả `BIGINT` khi `SUM` trên cột `INTEGER`, và `NUMERIC` khi `SUM` trên cột `BIGINT`; `AVG` trên số nguyên trả `NUMERIC`. Điều này giúp giảm nguy cơ tràn hoặc mất phần thập phân ở một số thao tác, nhưng không phải quy tắc giống hệt trong mọi DBMS.

~~~sql
SELECT
    COUNT(*) AS number_of_items,
    SUM(stock_units) AS all_units,
    AVG(unit_price) AS average_price
FROM catalog_items;
~~~

Hãy phân biệt **kiểu cột lưu trữ**, **kiểu trung gian của phép toán** và **kiểu trả về của hàm**. Khi tổng có thể rất lớn, cần kiểm tra tài liệu DBMS về miền giá trị và overflow.

### 6.3. So sánh và lọc số

Với cột decimal exact:

~~~sql
SELECT sku, unit_price
FROM catalog_items
WHERE unit_price = 59000.10;
~~~

`59000.10` là một hằng thập phân trong ngữ cảnh PostgreSQL và có thể so sánh chính xác với `unit_price NUMERIC(12,2)`. Với cột float chứa phép đo, tránh giả định biểu thức tính ra sẽ bằng chính xác một hằng viết ở dạng decimal:

~~~sql
-- Phù hợp khi yêu cầu thật sự là nằm trong khoảng khối lượng.
SELECT sku, shipping_weight_kg
FROM catalog_items
WHERE shipping_weight_kg >= 0.07
  AND shipping_weight_kg < 0.08;
~~~

Khoảng đo có thể được chọn dựa trên ý nghĩa nghiệp vụ. Cũng cần xem xét chỉ mục và cách viết điều kiện nếu bảng lớn, nhưng quyết định đầu tiên vẫn là kiểu dữ liệu và tính đúng đắn của so sánh.

## 7. Cạm bẫy thường gặp

| Cạm bẫy | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dùng `FLOAT` cho đơn giá rồi tổng tiền lệch vài đơn vị nhỏ | Số thập phân không luôn có biểu diễn nhị phân chính xác | Dùng `DECIMAL/NUMERIC` theo scale nghiệp vụ hoặc số nguyên của đơn vị tiền nhỏ nhất |
| `5 / 2` cho `2` thay vì `2.5` trong PostgreSQL | Phép chia hai số nguyên | `CAST` ít nhất một toán hạng sang kiểu decimal trước khi chia |
| `NUMERIC(5,2)` không lưu được `1000.00` | Chỉ cho ba chữ số phần nguyên | Tăng precision hoặc điều chỉnh miền nghiệp vụ |
| Ép `DOUBLE PRECISION` sang `DECIMAL` rồi nghĩ đã khôi phục số gốc | Nguồn float đã xấp xỉ trước đó | Giữ dữ liệu gốc bằng decimal nếu cần chính xác thập phân ngay từ đầu |
| So sánh `a + b = c` trên cột float | Sai số làm tròn ở các phép tính | Sử dụng dung sai có cơ sở hoặc khoảng giá trị |
| Dùng `SMALLINT` cho bộ đếm tăng vô hạn | Vượt miền kiểu nguyên | Ước lượng tăng trưởng và chọn `INTEGER/BIGINT` |
| Dùng `COALESCE(weight, 0)` không có quy tắc nghiệp vụ | Nhầm “chưa đo” với “đo bằng 0” | Giữ `NULL` và hiển thị trạng thái chưa đo |
| Dùng kiểu decimal có scale 2 cho mọi tiền tệ | Số chữ số nhỏ nhất khác nhau theo đồng tiền và nghiệp vụ | Quy định đơn vị tiền, currency code, precision/scale và chính sách làm tròn |
| Tin giá trị hiển thị của float là giá trị nội bộ chính xác | Trình điều khiển/công cụ có thể làm tròn khi in | Dùng phép kiểm tra phù hợp và hiểu kiểu lưu trữ |

## 8. Lựa chọn kiểu số theo yêu cầu

Trước khi tạo cột, hãy trả lời các câu hỏi:

1. Dữ liệu có cho phép phần thập phân không? Nếu **không**, chọn họ kiểu nguyên.
2. Nếu có phần thập phân, phải **chính xác theo chữ số thập phân** hay chấp nhận **sai số biểu diễn**? Nếu cần đối soát, chọn decimal.
3. Giá trị lớn nhất/nhỏ nhất dự kiến là gì, kể cả sau vài năm tăng trưởng? Miền đó phải nằm trong khả năng của kiểu.
4. Cần bao nhiêu chữ số sau dấu thập phân và làm tròn ở bước nào? Điều này quyết định `scale` và chính sách tính toán.
5. Có giá trị chưa biết không? Phải phân biệt `NULL` với `0`, cũng như bổ sung `CHECK` khi cần.
6. Dữ liệu đi qua JDBC, ORM, API hoặc hệ khác dưới kiểu nào? Cần bảo toàn giá trị qua mọi lớp.

Gợi ý lựa chọn:

| Dữ liệu | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| Số lượng mặt hàng | `INTEGER` + `CHECK (quantity >= 0)` | Không có phần lẻ; ràng buộc không âm |
| Mã ID có khả năng tăng rất lớn | `BIGINT` | Miền nguyên rộng |
| Giá sản phẩm | `DECIMAL(p, s)` / `NUMERIC(p, s)` | Cần chữ số thập phân chính xác trong scale khai báo |
| Số tiền tính bằng đơn vị nhỏ nhất, quy tắc cố định | `BIGINT` (ví dụ số cent) | Số nguyên chính xác; phải thống nhất đơn vị và chống overflow |
| Tỉ lệ thuế cần 4–6 chữ số sau dấu thập phân | `DECIMAL(p, 4)` hoặc `DECIMAL(p, 6)` | Kiểm soát precision và làm tròn |
| Giá trị đọc từ cảm biến | `DOUBLE PRECISION` | Dữ liệu gần đúng, phạm vi rộng |
| Kết quả mô phỏng thống kê | `DOUBLE PRECISION` | Hỗ trợ tính toán xấp xỉ ở độ chính xác kép |

**Không có quy tắc “DECIMAL luôn tốt hơn FLOAT”.** Decimal exact phù hợp các số thập phân phải bảo toàn theo quy ước, còn float phù hợp dữ liệu đo đạc và tính toán gần đúng. Kiểu decimal có thể tiêu thụ nhiều tài nguyên tính toán/lưu trữ hơn float trong một số hệ và trường hợp, nhưng quyết định cần ưu tiên tính đúng đắn trước và đo hiệu năng thực tế sau.

## 9. Khi ứng dụng Java trao đổi dữ liệu số với SQL

Với Java và JDBC, kiểu số ở tầng ứng dụng cần giữ đúng ý nghĩa cột:

- `INTEGER` thường đọc/ghi qua `int` hoặc `Integer` khi có thể `NULL`; `BIGINT` thường qua `long`/`Long` nếu trong miền Java.
- `DECIMAL/NUMERIC` thường nên đọc/ghi qua `java.math.BigDecimal` để giữ số thập phân chính xác; không chuyển trung gian qua `double` nếu muốn bảo toàn giá tiền.
- `REAL/DOUBLE PRECISION` thường đọc/ghi qua `float/double` hoặc lớp bao tương ứng khi phù hợp với kiểu JDBC và yêu cầu nghiệp vụ.

Ví dụ ý nghĩa của đầu vào số tiền:

~~~java
import java.math.BigDecimal;
import java.sql.PreparedStatement;

BigDecimal price = new BigDecimal("12500.25"); // Tạo từ chuỗi thập phân chính xác

// PreparedStatement ps đã được tạo cho SQL có placeholder (?):
ps.setBigDecimal(1, price);
~~~

Khi tạo `BigDecimal` từ một literal `double` như `new BigDecimal(0.1)`, số `double` đã mang xấp xỉ nhị phân. Nếu muốn biểu diễn giá trị thập phân `0.1`, dùng `new BigDecimal("0.1")` hoặc API có chủ đích chuyển dạng hiển thị như `BigDecimal.valueOf(0.1)` theo yêu cầu. `BigDecimal` cũng có scale và các chế độ làm tròn riêng: cần thống nhất chúng với quy tắc SQL.

Khi truyền số qua JSON, JavaScript hoặc các hệ thống phân tích dữ liệu, cần kiểm tra có bước nào chuyển decimal sang số dấu phẩy động nhị phân hay không. Định nghĩa cột SQL là `DECIMAL` không bảo đảm tính chính xác nếu một tầng trung gian đã làm mất thông tin trước khi lưu vào DB.

## 10. Bài tập thực hành

Các bài tập dùng PostgreSQL và bảng `catalog_items` của mục 5, chưa thay đổi dữ liệu.

### Bài 1 — Chọn kiểu cho ba cột

Một bảng cần lưu: số học viên đang đăng ký, học phí theo đơn vị tiền và thời gian thực hiện bài đo được tính bằng giây với sai số phần nghìn. Hãy đề xuất họ kiểu phù hợp.

**Gợi ý:** số học viên là `INTEGER` hoặc `BIGINT` tùy quy mô; học phí dùng `DECIMAL/NUMERIC` theo quy tắc tiền tệ; thời gian đo là đại lượng gần đúng nên có thể dùng `DOUBLE PRECISION` (hoặc decimal nếu quy ước sản phẩm yêu cầu cố định chính xác đến mili giây).

### Bài 2 — Phép chia trước và sau CAST

Dự đoán kết quả hai cột trong PostgreSQL:

~~~sql
SELECT
    CAST(9 / 4 AS NUMERIC(10, 2)) AS late_cast,
    CAST(9 AS NUMERIC(10, 2)) / 4 AS early_cast;
~~~

**Đáp án:** `late_cast = 2.00` vì `9 / 4` đã thực hiện phép chia nguyên trước; `early_cast` biểu diễn `2.25` vì toán hạng đã được ép sang decimal trước khi chia.

### Bài 3 — Precision và scale

`DECIMAL(6,2)` có bao nhiêu chữ số ở phần nguyên? Có thể lưu `9999.99` và `10000.00` không?

**Đáp án:** có tối đa bốn chữ số phần nguyên. `9999.99` phù hợp; `10000.00` vượt precision vì phần nguyên có năm chữ số.

### Bài 4 — Tổng giá trị tồn kho

Viết truy vấn tính tổng giá trị hàng đang tồn (số lượng nhân với đơn giá). Kết quả là bao nhiêu?

~~~sql
SELECT SUM(stock_units * unit_price) AS total_value
FROM catalog_items;
~~~

**Đáp án:** `10475002.50`. Trong truy vấn này giá trị tồn kho được tính bằng số lượng nguyên và đơn giá `NUMERIC`, phù hợp yêu cầu chính xác thập phân.

### Bài 5 — Hiểu số dấu phẩy động

Vì sao biểu thức cộng hai giá trị `DOUBLE PRECISION` đại diện cho `0.1` và `0.2` có thể không bằng chính xác giá trị `0.3` đã chuyển sang `DOUBLE PRECISION`?

**Gợi ý:** cả ba đều là các giá trị nhị phân gần nhất có thể biểu diễn; phép cộng có thể làm tròn thành một kết quả nhị phân khác với biểu diễn gần nhất của `0.3`. Cần dùng decimal exact nếu yêu cầu là đồng nhất các số thập phân, hoặc dùng tiêu chí sai số phù hợp nếu đây là dữ liệu đo.

### Bài 6 — Phát hiện nguy cơ làm tròn

Một cột `NUMERIC(5,2)` đang được chuẩn bị để ghi giá trị `999.995` trong PostgreSQL. Vì sao giá trị này gây lỗi dù nhìn ban đầu chỉ có ba chữ số phần nguyên?

**Đáp án:** làm tròn về hai chữ số sau dấu thập phân tạo thành `1000.00`, cần bốn chữ số phần nguyên và vượt `NUMERIC(5,2)`. Tăng precision nếu nghiệp vụ cho phép giá trị đó.

## 11. Tổng kết

Trong SQL, **số nguyên** giữ chính xác các giá trị không có phần lẻ nhưng bị giới hạn miền; **`DECIMAL/NUMERIC`** giữ chính xác các giá trị thập phân nằm trong precision/scale được thiết kế; **`REAL/FLOAT/DOUBLE PRECISION`** biểu diễn giá trị xấp xỉ với sai số dấu phẩy động, thích hợp cho đo lường và tính toán khoa học. Chọn kiểu dựa trên ý nghĩa dữ liệu, miền giá trị, độ chính xác cần bảo toàn, quy tắc làm tròn và khả năng trao đổi với ứng dụng. Khi viết phép tính, luôn để ý kiểu của **toán hạng trước khi tính**, kiểu kết quả, xử lý `NULL` và giới hạn khác nhau giữa các hệ quản trị.
