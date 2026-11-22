# UNION, UNION ALL và tương thích kiểu dữ liệu các nhánh

Khi cần ghép dữ liệu từ nhiều truy vấn có cùng cấu trúc, MySQL cung cấp phép toán tập hợp UNION. Ví dụ, một ứng dụng có bảng đơn hàng hiện tại và bảng lưu trữ, nhưng báo cáo cần xem chúng như một danh sách thống nhất. UNION cho phép ghép các hàng từ nhiều câu SELECT thành một tập kết quả.

Hai biến thể quan trọng là UNION DISTINCT (mặc định viết ngắn là UNION) và UNION ALL. UNION loại bỏ các hàng trùng lặp trong kết quả ghép; UNION ALL giữ lại tất cả hàng, kể cả các hàng giống nhau. Ngoài việc chọn đúng biến thể, bạn cần bảo đảm các nhánh có cùng số cột, thứ tự cột tương ứng đúng ý nghĩa và kiểu dữ liệu có thể kết hợp an toàn.

Bài học thuộc phạm vi DATABASE_MYSQL: truy vấn SQL, tổng hợp dữ liệu từ nhiều nguồn, kiểm soát kiểu dữ liệu, xử lý dữ liệu trùng, đọc kế hoạch thực thi và thiết kế truy vấn có thể mở rộng khi schema thay đổi.

## 1. UNION là gì?

UNION kết hợp kết quả của hai hoặc nhiều câu SELECT thành một tập kết quả. Mỗi SELECT được gọi là một nhánh (query block). Các nhánh phải trả về cùng số lượng cột và các cột tương ứng phải có kiểu dữ liệu tương thích.

Cú pháp cơ bản:

~~~sql
SELECT column_a, column_b
FROM source_a

UNION [ALL | DISTINCT]

SELECT column_x, column_y
FROM source_b;
~~~

UNION ghép theo vị trí cột, không ghép theo tên alias. Cột thứ nhất của SELECT đầu tiên tương ứng với cột thứ nhất của SELECT tiếp theo; cột thứ hai tương ứng với cột thứ hai, và cứ tiếp tục như vậy.

Ví dụ:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, customer_name
FROM customer_store;
~~~

Kết quả gồm các hàng từ cả hai nguồn. Dù hai bảng có thể đặt tên cột khác nhau, điều quan trọng là vị trí và ý nghĩa của các cột tương ứng phải khớp.

### 1.1. UNION khác JOIN như thế nào?

UNION xếp các hàng của nhiều kết quả theo chiều dọc. JOIN kết hợp các cột của các bảng theo quan hệ giữa hàng.

| Tiêu chí | UNION | JOIN |
|---|---|---|
| Cách kết hợp | Nối thêm hàng | Ghép thêm cột |
| Số cột đầu ra | Theo cấu trúc SELECT của các nhánh | Theo các cột được chọn từ các bảng |
| Điều kiện kết hợp | Các nhánh có cùng số cột và kiểu tương thích | Điều kiện nối giữa bảng, trừ CROSS JOIN |
| Ví dụ | Gộp đơn hàng hiện tại và lưu trữ | Ghép đơn hàng với thông tin khách hàng |

Nếu muốn ghép danh sách khách hàng từ hai hệ thống, dùng UNION. Nếu muốn lấy đơn hàng kèm tên khách hàng từ bảng customer, dùng JOIN.

## 2. UNION DISTINCT và UNION ALL

### 2.1. UNION mặc định loại bỏ hàng trùng

Nếu không ghi ALL, UNION mặc định là DISTINCT. MySQL loại bỏ các hàng trùng nhau trong tập kết quả hợp nhất.

~~~sql
SELECT 10 AS customer_id
UNION
SELECT 10
UNION
SELECT 20;
~~~

Kết quả chỉ có hai hàng: 10 và 20.

Có thể viết tường minh:

~~~sql
SELECT 10 AS customer_id
UNION DISTINCT
SELECT 10
UNION DISTINCT
SELECT 20;
~~~

UNION DISTINCT so sánh toàn bộ các cột của hàng đầu ra để xác định hai hàng có trùng hay không. Nó không tự hiểu cột nào là khóa chính hoặc khóa nghiệp vụ.

### 2.2. UNION ALL giữ nguyên mọi hàng

~~~sql
SELECT 10 AS customer_id
UNION ALL
SELECT 10
UNION ALL
SELECT 20;
~~~

Kết quả có ba hàng: 10, 10 và 20. Không có bước loại bỏ bản sao.

UNION ALL phù hợp khi:
- Các nguồn dữ liệu là những phân vùng không chồng lấn.
- Bạn cần giữ số lần xuất hiện để tính tổng hoặc đếm.
- Dữ liệu trùng giữa các nguồn vẫn có ý nghĩa.
- Bạn muốn tránh chi phí khử trùng không cần thiết.

Không nên dùng UNION DISTINCT chỉ vì muốn “an toàn”. Nếu bản ghi trùng là hợp lệ, việc loại bỏ chúng sẽ làm sai số liệu.

### 2.3. So sánh hai biến thể

| Tiêu chí | UNION / UNION DISTINCT | UNION ALL |
|---|---|---|
| Giữ hàng trùng | Không | Có |
| Mặc định | Có, khi chỉ viết UNION | Phải ghi ALL |
| Xử lý trùng | Cần xác định và loại các hàng trùng trong kết quả | Không loại trùng |
| Chi phí thực thi | Có thể cao hơn do khử trùng | Thường thấp hơn khi không cần khử trùng |
| Thứ tự đầu ra | Không được bảo đảm nếu không ORDER BY | Không được bảo đảm nếu không ORDER BY |
| Trường hợp phù hợp | Cần tập kết quả không có hàng trùng hoàn toàn | Cần giữ mọi hàng từ các nhánh |

UNION ALL thường tránh được công việc khử trùng, nhưng không có nghĩa mọi truy vấn UNION ALL luôn nhanh hơn đáng kể. Chi phí thực tế còn phụ thuộc số hàng, kế hoạch thực thi, I/O, biểu thức và cách MySQL materialize kết quả.

## 3. Quy tắc cấu trúc giữa các nhánh

### 3.1. Các nhánh phải có cùng số cột

Ví dụ hợp lệ:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, customer_name
FROM customer_store;
~~~

Ví dụ không hợp lệ vì nhánh đầu có hai cột, nhánh sau chỉ có một:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id
FROM customer_store;
~~~

MySQL báo lỗi vì số cột của các SELECT không bằng nhau.

Nếu một nguồn không có thuộc tính tương ứng, hãy cung cấp một giá trị thay thế có kiểu phù hợp:

~~~sql
SELECT customer_id, customer_name, email
FROM customer_online

UNION ALL

SELECT customer_id, customer_name, CAST(NULL AS CHAR(255))
FROM customer_store;
~~~

Ở ví dụ này, nhánh cửa hàng không có email nên trả NULL cho vị trí cột email.

### 3.2. Thứ tự cột phải cùng ý nghĩa

UNION không ghép theo alias hoặc tên cột. Ví dụ sau có cùng hai cột nhưng đặt sai thứ tự:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_name, customer_id
FROM customer_store;
~~~

Nếu hai kiểu dữ liệu có thể chuyển đổi, truy vấn có thể chạy nhưng dữ liệu sẽ bị đặt sai cột. Đây là lỗi logic nguy hiểm vì không nhất thiết phát sinh lỗi cú pháp.

Hãy viết danh sách cột tường minh trong từng nhánh, theo cùng thứ tự và cùng ý nghĩa. Tránh SELECT * trong UNION vì schema một bảng thay đổi có thể làm thứ tự hoặc số cột không còn tương thích.

### 3.3. Tên cột kết quả lấy từ SELECT đầu tiên

Tên cột của kết quả UNION được xác định bởi danh sách SELECT đầu tiên. Alias ở các nhánh sau không đổi tên cột kết quả.

~~~sql
SELECT customer_id AS id, customer_name AS display_name
FROM customer_online

UNION ALL

SELECT store_customer_id AS customer_key, full_name AS full_name
FROM customer_store;
~~~

Kết quả có tên cột id và display_name, lấy từ SELECT đầu tiên. Các alias customer_key và full_name của nhánh thứ hai không được dùng làm tên cột đầu ra.

Vì vậy, hãy đặt alias có ý nghĩa ở nhánh đầu tiên và bảo đảm mọi nhánh theo đúng vị trí đó.

## 4. Tương thích kiểu dữ liệu giữa các nhánh

Các cột tương ứng không bắt buộc phải khai báo cùng một kiểu dữ liệu, nhưng kiểu phải có thể kết hợp. MySQL xác định kiểu của cột kết quả dựa trên các biểu thức ở tất cả nhánh.

Điều này có thể dẫn đến chuyển đổi kiểu ngầm. Nếu không kiểm soát, kết quả có thể có độ chính xác, miền giá trị hoặc cách hiển thị khác với mong muốn.

Ví dụ:

~~~sql
SELECT 100 AS amount
UNION ALL
SELECT 25.50;
~~~

Kết quả cần biểu diễn cả số nguyên và số thập phân. MySQL sẽ tổng hợp kiểu kết quả để chứa giá trị từ các nhánh. Với dữ liệu tài chính, nên chủ động dùng DECIMAL thay vì để kiểu kết quả phụ thuộc vào biểu thức đầu vào.

### 4.1. Cùng miền dữ liệu, dùng CAST rõ ràng

Giả sử một nguồn dùng INT, nguồn khác dùng BIGINT UNSIGNED. Nếu cột kết quả là mã định danh không âm, có thể ép kiểu tường minh:

~~~sql
SELECT
    CAST(customer_id AS UNSIGNED) AS customer_id,
    customer_name
FROM customer_online

UNION ALL

SELECT
    CAST(customer_key AS UNSIGNED),
    full_name
FROM customer_store;
~~~

Chọn kiểu đích dựa trên miền giá trị thực tế. Không ép mọi ID sang INT nếu nguồn có thể chứa giá trị vượt giới hạn INT.

### 4.2. Tiền tệ và DECIMAL

Không nên trộn DECIMAL với FLOAT/DOUBLE trong dữ liệu tiền nếu cần số thập phân chính xác.

~~~sql
SELECT
    CAST(total_amount AS DECIMAL(15, 2)) AS amount
FROM current_order

UNION ALL

SELECT
    CAST(archived_total AS DECIMAL(15, 2))
FROM archived_order;
~~~

Hai nhánh trả về cùng kiểu DECIMAL(15,2). Hãy chọn precision đủ lớn cho tổng giá trị lớn nhất có thể xuất hiện. Nếu ép kiểu quá hẹp, dữ liệu có thể bị làm tròn, cảnh báo hoặc lỗi tùy SQL mode và ngữ cảnh.

### 4.3. Chuỗi và độ dài

Nếu các nhánh trả về chuỗi có độ dài khác nhau, MySQL tổng hợp metadata kiểu kết quả để chứa dữ liệu từ các nhánh. Tuy nhiên, nên chủ động CAST khi cần một hợp đồng dữ liệu ổn định cho API, view hoặc bảng tạm.

~~~sql
SELECT
    CAST(code AS CHAR(40)) AS reference_code
FROM current_reference

UNION ALL

SELECT
    CAST(legacy_code AS CHAR(40))
FROM old_reference;
~~~

Nếu chuỗi chứa Unicode, hãy bảo đảm character set tương thích. Có thể chỉ định character set trong CAST khi cần:

~~~sql
SELECT
    CAST(code AS CHAR(100) CHARACTER SET utf8mb4) AS label
FROM source_a

UNION ALL

SELECT
    CAST(old_label AS CHAR(100) CHARACTER SET utf8mb4)
FROM source_b;
~~~

Đừng dùng CAST để cắt dữ liệu tùy tiện. Độ dài đích phải đủ chứa giá trị hợp lệ.

### 4.4. Collation của các nhánh chuỗi

Hai nhánh có thể dùng character set hoặc collation khác nhau. Khi MySQL tổng hợp biểu thức kết quả, nó phải xác định collation có thể áp dụng. Nếu các nhánh không tương thích, truy vấn có thể báo lỗi Illegal mix of collations.

Ví dụ chủ động đưa hai nhánh về cùng character set/collation:

~~~sql
SELECT
    customer_name COLLATE utf8mb4_0900_ai_ci AS customer_name
FROM customer_online

UNION ALL

SELECT
    full_name COLLATE utf8mb4_0900_ai_ci
FROM customer_store;
~~~

Collation đích phải tương thích với character set của các biểu thức và có sẵn trên phiên bản MySQL đang chạy. Nếu character set khác nhau, hãy chuyển đổi bằng CONVERT(... USING utf8mb4) trước khi áp dụng COLLATE.

Collation cũng ảnh hưởng tới việc xác định hàng trùng của UNION DISTINCT. Hai chuỗi khác hoa/thường hoặc dấu có thể được xem là bằng nhau theo collation kết quả. Vì vậy, thay đổi collation có thể làm số hàng sau UNION DISTINCT thay đổi.

### 4.5. Giá trị NULL và kiểu kết quả

Khi một nhánh không có dữ liệu cho một cột, có thể dùng NULL làm placeholder. Nhưng nếu tất cả nhánh đều trả NULL không định kiểu hoặc kiểu không rõ ràng, metadata của kết quả có thể không như ý muốn. Hãy CAST NULL về kiểu đích:

~~~sql
SELECT
    customer_id,
    CAST(NULL AS CHAR(100)) AS note
FROM customer_online

UNION ALL

SELECT
    customer_id,
    note
FROM customer_store;
~~~

Nếu cột đích là số thập phân:

~~~sql
CAST(NULL AS DECIMAL(15, 2)) AS amount
~~~

Nếu cột đích là ngày:

~~~sql
CAST(NULL AS DATE) AS effective_date
~~~

Ép kiểu placeholder giúp client, view và các bước xử lý phía sau nhận được kiểu dữ liệu ổn định.

### 4.6. Ngày giờ và kiểu temporal

Không trộn ngày giờ với chuỗi văn bản chỉ vì cả hai có thể hiển thị giống nhau. Hãy thống nhất kiểu DATE, DATETIME hoặc TIMESTAMP theo ý nghĩa dữ liệu.

~~~sql
SELECT
    CAST(order_date AS DATETIME(6)) AS event_time
FROM current_order

UNION ALL

SELECT
    CAST(created_at AS DATETIME(6))
FROM archived_order;
~~~

Nếu một nguồn chỉ có DATE và nguồn kia có DATETIME, cần xác định thời điểm mặc định của phần giờ. Không tự coi ngày là thời điểm trong múi giờ cụ thể nếu dữ liệu không mang thông tin đó.

## 5. UNION DISTINCT loại trùng theo toàn bộ hàng

UNION DISTINCT không biết khóa nghiệp vụ của bảng. Nó so sánh tất cả các cột được SELECT.

Ví dụ:

~~~sql
SELECT 10 AS customer_id, 'An' AS customer_name
UNION
SELECT 10, 'An'
UNION
SELECT 10, 'Anh';
~~~

Kết quả có hai hàng:
- (10, 'An')
- (10, 'Anh')

Dù customer_id trùng, hai hàng không giống nhau vì customer_name khác nhau.

Nếu thêm cột nguồn:

~~~sql
SELECT 10 AS customer_id, 'An' AS customer_name, 'online' AS source
UNION
SELECT 10, 'An', 'store';
~~~

Kết quả có hai hàng vì giá trị source khác nhau. Điều này rất quan trọng: thêm metadata nguồn sẽ làm các hàng khác nhau khi xét UNION DISTINCT.

### 5.1. NULL trong khử trùng

Trong phép loại trùng của UNION DISTINCT, các hàng có cùng giá trị ở mọi cột, kể cả vị trí NULL tương ứng, được xem là trùng để chỉ giữ một hàng.

~~~sql
SELECT NULL AS note
UNION
SELECT NULL;
~~~

Kết quả chỉ có một hàng NULL.

Trong khi đó:

~~~sql
SELECT NULL AS note
UNION ALL
SELECT NULL;
~~~

Kết quả có hai hàng NULL.

Quy tắc này thuộc phép loại trùng của tập kết quả; không suy ra rằng biểu thức SQL NULL = NULL trả TRUE. Phép so sánh bằng thông thường giữa hai NULL vẫn trả UNKNOWN.

## 6. UNION ALL cho bảng hiện tại và bảng lưu trữ

Một trường hợp thực tế là dữ liệu được chia thành bảng hoạt động và bảng lịch sử. Báo cáo cần xem cả hai nguồn.

Giả sử hai bảng có cùng cấu trúc:

~~~sql
CREATE TABLE orders_current (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders_archive (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE = InnoDB;
~~~

Truy vấn gộp:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    'current' AS source_name
FROM orders_current

UNION ALL

SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    'archive'
FROM orders_archive;
~~~

Dùng UNION ALL khi dữ liệu hiện tại và lưu trữ được phân vùng không chồng lấn, hoặc khi cần giữ mọi bản ghi. Nếu có thể cùng một order_id tồn tại ở cả hai bảng, UNION ALL sẽ giữ cả hai; hãy xử lý theo quy tắc nghiệp vụ thay vì tự động xóa trùng.

### 6.1. Lọc ở từng nhánh

Có thể đặt điều kiện ở mỗi SELECT để giảm số hàng cần ghép:

~~~sql
SELECT order_id, customer_id, total_amount, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'

UNION ALL

SELECT order_id, customer_id, total_amount, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01';
~~~

Điều kiện được áp dụng tại nguồn. Nếu cột created_at có index, mỗi nhánh có thể tận dụng range access phù hợp.

### 6.2. Sắp xếp và giới hạn kết quả sau khi ghép

~~~sql
SELECT order_id, customer_id, total_amount, created_at
FROM orders_current

UNION ALL

SELECT order_id, customer_id, total_amount, created_at
FROM orders_archive

ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

ORDER BY và LIMIT ở cuối áp dụng cho toàn bộ tập kết quả UNION. Nếu muốn lấy 100 hàng mới nhất từ từng nguồn trước khi ghép, cần đặt từng nhánh trong ngoặc và có ORDER BY/LIMIT riêng.

## 7. ORDER BY và LIMIT trong UNION

### 7.1. ORDER BY cuối cùng áp dụng cho kết quả chung

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, full_name
FROM customer_store

ORDER BY customer_name ASC;
~~~

ORDER BY đặt sau nhánh cuối cùng sẽ sắp xếp toàn bộ kết quả. Tên cột/alias tham chiếu trong ORDER BY của UNION nên dựa trên tên cột kết quả, được lấy từ SELECT đầu tiên.

Không dựa vào thứ tự ngẫu nhiên mà MySQL trả về các nhánh. Nếu không có ORDER BY ngoài cùng, thứ tự hàng không được bảo đảm.

### 7.2. ORDER BY và LIMIT riêng cho từng nhánh

Nếu cần giới hạn từng nguồn trước khi ghép, dùng ngoặc:

~~~sql
(SELECT order_id, total_amount, created_at
 FROM orders_current
 ORDER BY created_at DESC
 LIMIT 10)

UNION ALL

(SELECT order_id, total_amount, created_at
 FROM orders_archive
 ORDER BY created_at DESC
 LIMIT 10)

ORDER BY created_at DESC
LIMIT 10;
~~~

Truy vấn lấy tối đa 10 hàng từ mỗi nguồn, sau đó ghép và lấy 10 hàng mới nhất trong kết quả chung.

ORDER BY bên trong nhánh xác định hàng nào được chọn bởi LIMIT của nhánh. ORDER BY bên ngoài xác định thứ tự cuối cùng. Nếu không có ORDER BY cuối, kết quả chung vẫn không có thứ tự được bảo đảm.

### 7.3. Alias trong ORDER BY

Tên cột kết quả lấy từ SELECT đầu tiên. Ví dụ:

~~~sql
SELECT total_amount AS amount
FROM orders_current

UNION ALL

SELECT archived_total
FROM orders_archive

ORDER BY amount DESC;
~~~

ORDER BY dùng alias amount từ nhánh đầu tiên. Alias ở nhánh sau không đổi tên kết quả.

Nếu cần sắp xếp theo biểu thức phức tạp không tiện tham chiếu trực tiếp, hãy bọc UNION trong derived table:

~~~sql
SELECT
    combined.order_id,
    combined.total_amount
FROM (
    SELECT order_id, total_amount
    FROM orders_current

    UNION ALL

    SELECT order_id, archived_total
    FROM orders_archive
) AS combined
ORDER BY combined.total_amount DESC;
~~~

## 8. Khử trùng theo khóa nghiệp vụ không giống UNION DISTINCT

Giả sử một order_id có thể xuất hiện ở cả bảng hiện tại và bảng lưu trữ, và bạn muốn ưu tiên bản ghi hiện tại. UNION DISTINCT không giải quyết đúng yêu cầu nếu các cột khác nhau, vì nó chỉ loại các hàng giống hoàn toàn.

Dùng UNION ALL để giữ dữ liệu và sau đó chọn một hàng theo khóa nghiệp vụ:

~~~sql
WITH combined_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        1 AS source_priority,
        'current' AS source_name
    FROM orders_current

    UNION ALL

    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        2 AS source_priority,
        'archive' AS source_name
    FROM orders_archive
),
ranked_orders AS (
    SELECT
        combined_orders.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY source_priority
        ) AS row_num
    FROM combined_orders
)
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    source_name
FROM ranked_orders
WHERE row_num = 1;
~~~

ROW_NUMBER đánh số hàng trong từng order_id. Hàng có source_priority nhỏ hơn được chọn. Cách này diễn đạt rõ quy tắc ưu tiên và có thể mở rộng thêm tiêu chí như thời gian cập nhật.

Ví dụ dùng CTE và window function yêu cầu MySQL 8.0 trở lên. Nếu dùng phiên bản cũ, cần chiến lược khác như anti-join hoặc bảng staging với quy tắc chọn hàng.

Nếu hai hàng cùng order_id và cùng source_priority, thứ tự chọn giữa chúng không xác định. Hãy thêm tie-breaker ổn định, chẳng hạn updated_at DESC rồi khóa phụ duy nhất.

## 9. Tương thích kiểu dữ liệu: ví dụ tổng hợp

Khi ghép nhiều nguồn, hãy chuẩn hóa kiểu dữ liệu ở mỗi vị trí cột.

Ví dụ một báo cáo lấy giao dịch từ hai hệ thống có kiểu khác nhau:

~~~sql
SELECT
    CAST(transaction_id AS UNSIGNED) AS transaction_id,
    CAST(amount AS DECIMAL(15, 2)) AS amount,
    CAST(event_time AS DATETIME(6)) AS event_time,
    CAST(description AS CHAR(200) CHARACTER SET utf8mb4) AS description
FROM payment_current

UNION ALL

SELECT
    CAST(legacy_id AS UNSIGNED),
    CAST(legacy_amount AS DECIMAL(15, 2)),
    CAST(processed_at AS DATETIME(6)),
    CAST(legacy_note AS CHAR(200) CHARACTER SET utf8mb4)
FROM payment_legacy;
~~~

Trước khi ép kiểu, kiểm tra:
- Miền giá trị lớn nhất/nhỏ nhất.
- Số chữ số thập phân cần bảo toàn.
- Độ dài chuỗi tối đa.
- Character set và collation.
- Kiểu ngày giờ và độ chính xác fractional seconds.
- Khả năng NULL của từng cột.

CAST có thể làm mất thông tin nếu kiểu đích quá hẹp. Với dữ liệu quan trọng, hãy thử trên bản sao và kiểm tra warning, giá trị biên trước khi triển khai.

### 9.1. Dùng NULL placeholder đúng kiểu

Một nhánh có thể không có cột tương ứng:

~~~sql
SELECT
    employee_id,
    employee_name,
    CAST(NULL AS DATE) AS terminated_date
FROM current_employee

UNION ALL

SELECT
    employee_id,
    employee_name,
    terminated_date
FROM former_employee;
~~~

Việc CAST NULL làm kiểu kết quả rõ ràng hơn và giúp client nhận metadata nhất quán.

### 9.2. Tránh chuyển đổi ngầm giữa số và chuỗi

Không nên viết truy vấn mà một nhánh trả ID số còn nhánh khác trả mã chuỗi nếu không có quy tắc biểu diễn chung:

~~~sql
SELECT customer_id AS reference_id
FROM customer_numeric

UNION ALL

SELECT external_code
FROM customer_external;
~~~

Nếu kết quả cần là chuỗi định danh, hãy chuyển cả hai nhánh thành một kiểu chuỗi đủ dài. Nếu kết quả phải là số, không thể chuyển external_code tùy ý khi nó chứa chữ.

~~~sql
SELECT CAST(customer_id AS CHAR(40)) AS reference_id
FROM customer_numeric

UNION ALL

SELECT CAST(external_code AS CHAR(40))
FROM customer_external;
~~~

Chỉ dùng cách này nếu việc coi hai loại định danh là văn bản là đúng nghiệp vụ. Đừng ép kiểu chỉ để làm hết lỗi mà không xác định ý nghĩa dữ liệu.

## 10. UNION và collation của văn bản

Khi UNION các cột chuỗi, MySQL cần xác định character set và collation của kết quả. Nếu các nhánh dùng collation khác nhau, quy tắc coercibility có thể quyết định collation kết quả hoặc gây lỗi không tương thích.

Kiểm tra metadata của cột nguồn:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_NAME IN ('customer_online', 'customer_store')
  AND COLUMN_NAME IN ('customer_name', 'full_name');
~~~

Nếu cần thống nhất, chuyển đổi các nhánh về cùng character set và collation:

~~~sql
SELECT
    customer_name COLLATE utf8mb4_0900_ai_ci AS display_name
FROM customer_online

UNION ALL

SELECT
    full_name COLLATE utf8mb4_0900_ai_ci
FROM customer_store;
~~~

Nếu hai cột chưa cùng character set, có thể dùng CONVERT(... USING utf8mb4) trước COLLATE. Kiểm tra collation đích tồn tại trên server.

Lưu ý: collation còn ảnh hưởng tới khử trùng của UNION DISTINCT. Nếu collation không phân biệt hoa/thường, các chuỗi chỉ khác chữ hoa/thường có thể bị xem là trùng. Nếu dữ liệu định danh cần so sánh chính xác, hãy chọn collation đúng trước khi dùng UNION DISTINCT.

## 11. UNION trong báo cáo và tổng hợp dữ liệu

UNION thường dùng để ghép các tập dữ liệu có cùng cấu trúc, sau đó truy vấn ngoài có thể tiếp tục lọc, nhóm hoặc tổng hợp.

Ví dụ hợp nhất doanh thu từ hai kênh:

~~~sql
WITH all_sales AS (
    SELECT
        'ONLINE' AS channel,
        order_date,
        total_amount
    FROM online_sales

    UNION ALL

    SELECT
        'STORE' AS channel,
        sale_date,
        amount
    FROM store_sales
)
SELECT
    channel,
    YEAR(order_date) AS sales_year,
    SUM(total_amount) AS revenue,
    COUNT(*) AS transaction_count
FROM all_sales
GROUP BY channel, YEAR(order_date)
ORDER BY sales_year, channel;
~~~

Các nhánh có thể đặt alias khác nhau ở SELECT đầu và sau, nhưng tên cột kết quả lấy từ nhánh đầu tiên. Ở ví dụ, sale_date và amount của nhánh cửa hàng được ánh xạ vào order_date và total_amount của kết quả chung theo vị trí.

Dùng UNION ALL để bảo toàn từng giao dịch. Nếu dùng UNION DISTINCT, hai giao dịch có cùng ngày và số tiền cùng channel có thể bị gộp dù thực tế là hai giao dịch khác nhau.

## 12. UNION và hiệu năng

### 12.1. Khi nào UNION DISTINCT tốn chi phí?

UNION DISTINCT phải xác định và loại bỏ các hàng trùng. Với tập dữ liệu lớn, bước này có thể cần cấu trúc tạm, so sánh nhiều hàng và sử dụng thêm CPU/bộ nhớ hoặc I/O.

UNION ALL không cần bước khử trùng. Nếu nghiệp vụ không yêu cầu loại trùng, chọn ALL để tránh công việc không cần thiết.

### 12.2. Đẩy điều kiện lọc vào từng nhánh

Thay vì ghép toàn bộ bảng rồi mới lọc, có thể lọc ở từng nhánh:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'
  AND status = 'PAID'

UNION ALL

SELECT order_id, customer_id, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01'
  AND status = 'PAID';
~~~

Điều này giúp mỗi nhánh có cơ hội sử dụng index phù hợp và giảm số hàng cần ghép. Optimizer cũng có thể đẩy một số điều kiện từ truy vấn ngoài xuống nhánh, nhưng hãy kiểm tra kế hoạch thực thi thay vì giả định.

### 12.3. Chỉ chọn cột cần thiết

Tránh SELECT * khi ghép dữ liệu. Chọn đúng các cột cần thiết sẽ giảm kích thước hàng trung gian, lượng dữ liệu truyền và chi phí khử trùng nếu dùng DISTINCT.

### 12.4. Index cho từng nhánh

Mỗi SELECT được tối ưu dựa trên bảng và index của chính nhánh đó. Nếu lọc theo created_at ở cả hai bảng, hãy đánh giá index trên created_at của từng bảng. Nếu lọc theo status và khoảng thời gian, composite index có thể phù hợp tùy workload.

UNION không tạo một index chung cho kết quả. Nếu kết quả cần được truy vấn lặp lại nhiều lần như một bảng, hãy cân nhắc materialized table do ứng dụng hoặc job ETL quản lý.

### 12.5. Kiểm tra bằng EXPLAIN

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'

UNION ALL

SELECT order_id, customer_id, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01';
~~~

Đọc access type, possible_keys, key, rows ước tính và Extra cho từng nhánh. Với truy vấn phức tạp, dùng EXPLAIN FORMAT=TREE hoặc EXPLAIN ANALYZE trên môi trường phù hợp để xem kế hoạch và số liệu thực thi.

EXPLAIN ANALYZE thực thi truy vấn để đo các iterator. Không dùng tùy tiện với truy vấn thay đổi dữ liệu hoặc truy vấn quá nặng trên production.

## 13. UNION và ORDER BY trong từng nhánh

ORDER BY cuối cùng sắp xếp kết quả chung. Nếu muốn ORDER BY/LIMIT riêng từng nhánh, cần đặt SELECT trong ngoặc.

Ví dụ lấy 5 giao dịch mới nhất từ từng nguồn rồi chọn 5 giao dịch mới nhất chung:

~~~sql
(SELECT transaction_id, amount, created_at
 FROM payment_current
 ORDER BY created_at DESC
 LIMIT 5)

UNION ALL

(SELECT transaction_id, amount, created_at
 FROM payment_archive
 ORDER BY created_at DESC
 LIMIT 5)

ORDER BY created_at DESC
LIMIT 5;
~~~

Nếu bỏ ngoặc hoặc đặt ORDER BY ở vị trí sai, MySQL có thể hiểu đó là ORDER BY của toàn bộ phép UNION hoặc báo lỗi cú pháp. Dùng ngoặc để làm rõ phạm vi của LIMIT.

Nếu cần kết quả ổn định khi nhiều hàng có cùng created_at, thêm khóa duy nhất vào ORDER BY, ví dụ created_at DESC, transaction_id DESC.

## 14. UNION với view và CTE

Có thể định nghĩa một view hợp nhất các nguồn:

~~~sql
CREATE VIEW all_customer_events AS
SELECT event_id, customer_id, event_type, occurred_at
FROM current_customer_event

UNION ALL

SELECT event_id, customer_id, event_type, occurred_at
FROM archived_customer_event;
~~~

Sau đó truy vấn như một nguồn dữ liệu:

~~~sql
SELECT customer_id, COUNT(*) AS event_count
FROM all_customer_events
GROUP BY customer_id;
~~~

View thông thường không lưu sẵn kết quả; truy vấn view sẽ được xử lý theo định nghĩa view và kế hoạch optimizer. Nếu cần lưu kết quả để đọc nhanh, cần một bảng vật lý hoặc quy trình materialization do hệ thống quản lý.

CTE có thể giúp đặt tên tập kết quả tạm trong phạm vi một câu lệnh:

~~~sql
WITH all_events AS (
    SELECT event_id, customer_id, occurred_at
    FROM current_customer_event

    UNION ALL

    SELECT event_id, customer_id, occurred_at
    FROM archived_customer_event
)
SELECT customer_id, MAX(occurred_at) AS last_event_at
FROM all_events
GROUP BY customer_id;
~~~

CTE giúp chia truy vấn thành bước có tên, nhưng không mặc định luôn nhanh hơn subquery hoặc view. Hãy đo kế hoạch thực thi.

## 15. Tham số hóa truy vấn UNION trong ứng dụng

Nếu các nhánh nhận giá trị từ ứng dụng, hãy dùng prepared statement. Mỗi placeholder trong mỗi nhánh được bind riêng theo thứ tự xuất hiện.

Ví dụ JDBC:

~~~java
String sql = """
    SELECT order_id, total_amount, created_at
    FROM orders_current
    WHERE customer_id = ?
      AND created_at >= ?

    UNION ALL

    SELECT order_id, total_amount, created_at
    FROM orders_archive
    WHERE customer_id = ?
      AND created_at >= ?

    ORDER BY created_at DESC
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setTimestamp(2, fromTime);
    ps.setLong(3, customerId);
    ps.setTimestamp(4, fromTime);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả hợp nhất.
        }
    }
}
~~~

Không ghép trực tiếp giá trị đầu vào vào SQL. Tên bảng, tên cột và từ khóa không thể bind như giá trị; nếu cấu trúc truy vấn phải thay đổi động, dùng whitelist cho các lựa chọn được phép.

## 16. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| UNION báo số cột không khớp | Các SELECT có số cột khác nhau | Liệt kê cột tường minh và thêm placeholder có kiểu |
| Dữ liệu nằm sai cột nhưng truy vấn vẫn chạy | Các nhánh đặt cột sai thứ tự | Chuẩn hóa thứ tự và ý nghĩa từng vị trí |
| Alias ở nhánh sau không xuất hiện | Tên cột kết quả lấy từ SELECT đầu tiên | Đặt alias ở nhánh đầu |
| UNION làm mất hàng hợp lệ | UNION mặc định DISTINCT | Dùng UNION ALL khi cần giữ mọi hàng |
| UNION DISTINCT không gộp bản ghi cùng ID | Các cột khác nhau nên toàn bộ hàng không trùng | Khử trùng theo khóa nghiệp vụ bằng GROUP BY/window logic |
| Thêm source_name khiến số hàng tăng | Cột nguồn làm các hàng khác nhau | Xác định có cần giữ nguồn trong tiêu chí khử trùng không |
| Illegal mix of collations | Các nhánh chuỗi có collation không tương thích | CONVERT và COLLATE về quy tắc chung |
| Số tiền bị thay đổi độ chính xác | Kiểu số giữa các nhánh không phù hợp hoặc CAST quá hẹp | Dùng DECIMAL có precision/scale đủ lớn |
| NULL placeholder có metadata không mong muốn | NULL không được ép kiểu rõ | CAST(NULL AS kiểu_đích) |
| ORDER BY sắp xếp sai phạm vi | Nhầm ORDER BY của nhánh với toàn UNION | Dùng ORDER BY cuối hoặc ngoặc cho từng nhánh |
| Kết quả thay đổi thứ tự giữa các lần chạy | Không có ORDER BY ngoài cùng | Chỉ định ORDER BY có tie-breaker |
| Truy vấn chậm | DISTINCT, nhiều hàng hoặc từng nhánh quét lớn | Xem xét ALL, lọc sớm, index và EXPLAIN |

## 17. Quy trình thiết kế UNION an toàn

Trước khi ghép nhiều SELECT, hãy thực hiện:

1. Xác định mục tiêu là ghép mọi hàng hay tạo tập hàng duy nhất hoàn toàn.
2. Chọn UNION ALL nếu cần giữ mọi lần xuất hiện; chọn UNION DISTINCT nếu thực sự cần loại hàng trùng toàn bộ.
3. Liệt kê các cột đầu ra và ý nghĩa của từng vị trí.
4. Bảo đảm mỗi nhánh trả cùng số cột theo cùng thứ tự.
5. Kiểm tra kiểu dữ liệu, miền giá trị, precision, scale, độ dài chuỗi và NULL.
6. Chuẩn hóa character set/collation nếu các nhánh trả chuỗi.
7. CAST rõ ràng cho dữ liệu khác kiểu hoặc placeholder NULL khi cần hợp đồng đầu ra ổn định.
8. Đặt alias ở SELECT đầu tiên.
9. Đặt ORDER BY/LIMIT cuối cho toàn kết quả; dùng ngoặc nếu cần giới hạn từng nhánh.
10. Lọc sớm ở từng nhánh và chọn đúng cột để giảm dữ liệu trung gian.
11. Chạy EXPLAIN và đo trên dữ liệu đại diện.
12. Kiểm tra duplicate theo khóa nghiệp vụ riêng nếu yêu cầu không trùng theo ID.

## 18. Bài tập thực hành

### Bài 1: UNION và UNION ALL

Chạy:

~~~sql
SELECT 1 AS value
UNION
SELECT 1
UNION
SELECT 2;
~~~

Sau đó đổi UNION thành UNION ALL. Đếm số hàng của mỗi kết quả và giải thích sự khác biệt.

### Bài 2: Ghép bảng có cấu trúc tương tự

Tạo bảng customer_online và customer_store. Ghép customer_id, tên và email bằng UNION ALL. Thử đổi thứ tự cột trong nhánh thứ hai để quan sát lỗi logic.

### Bài 3: Chuẩn hóa kiểu dữ liệu

Tạo hai nguồn có amount lần lượt là INT và DECIMAL. Ghép chúng rồi kiểm tra metadata kiểu kết quả. Viết lại bằng CAST AS DECIMAL(15,2) ở cả hai nhánh.

### Bài 4: NULL placeholder

Ghép bảng nhân viên hiện tại và cựu nhân viên, trong đó chỉ bảng cựu nhân viên có terminated_date. Dùng CAST(NULL AS DATE) ở nhánh hiện tại và xác minh kiểu cột kết quả.

### Bài 5: Collation

Tạo hai bảng có cột tên dùng collation khác nhau. Thử UNION DISTINCT với các giá trị chỉ khác hoa/thường hoặc dấu. Sau đó chuyển các nhánh về cùng collation và so sánh số hàng.

### Bài 6: Khử trùng theo khóa nghiệp vụ

Tạo hai bảng có order_id trùng nhưng total_amount khác nhau. So sánh UNION DISTINCT với UNION ALL kết hợp ROW_NUMBER() OVER (PARTITION BY order_id). Chọn bản ghi ưu tiên theo nguồn và giải thích vì sao hai cách khác nhau.

### Bài 7: ORDER BY và LIMIT

Lấy 5 hàng mới nhất từ từng nguồn, ghép bằng UNION ALL rồi lấy 5 hàng mới nhất chung. Thử bỏ ngoặc ở từng nhánh và quan sát phạm vi ORDER BY/LIMIT.

### Bài 8: Đọc EXPLAIN

Tạo index trên các cột lọc của từng nguồn. Chạy EXPLAIN cho UNION ALL và UNION DISTINCT trên tập dữ liệu lớn hơn. Ghi nhận access type, key, rows và chi phí khử trùng.

## 19. Checklist trước khi đưa UNION vào ứng dụng

- [ ] Đã chọn đúng UNION DISTINCT hoặc UNION ALL theo quy tắc nghiệp vụ.
- [ ] Mọi nhánh có cùng số cột.
- [ ] Các cột tương ứng cùng ý nghĩa và đúng thứ tự.
- [ ] Đã xác định tên cột kết quả từ SELECT đầu tiên.
- [ ] Đã kiểm tra kiểu số, precision/scale, độ dài chuỗi và kiểu temporal.
- [ ] Đã CAST tường minh khi cần kiểu đầu ra ổn định.
- [ ] Đã kiểm tra character set và collation giữa các nhánh.
- [ ] Đã xử lý NULL placeholder với kiểu dữ liệu rõ ràng.
- [ ] Đã hiểu UNION DISTINCT loại trùng trên toàn bộ hàng.
- [ ] Đã dùng logic riêng nếu cần khử trùng theo khóa nghiệp vụ.
- [ ] Đã đặt ORDER BY/LIMIT đúng phạm vi.
- [ ] Đã dùng ORDER BY ngoài cùng nếu cần thứ tự kết quả ổn định.
- [ ] Đã lọc sớm, chọn cột cần thiết và kiểm tra index từng nhánh.
- [ ] Đã dùng prepared statement cho tham số đầu vào.
- [ ] Đã kiểm tra EXPLAIN và kết quả trên dữ liệu đại diện.

## 20. Kết luận

UNION ghép các kết quả SELECT theo chiều dọc. UNION mặc định là DISTINCT và loại bỏ các hàng trùng hoàn toàn; UNION ALL giữ mọi hàng. Hai biến thể không thể thay thế nhau tùy tiện vì lựa chọn sai có thể làm mất dữ liệu hoặc tạo chi phí khử trùng không cần thiết.

Để UNION đáng tin cậy, các nhánh phải có cùng số cột, cùng thứ tự ý nghĩa và kiểu dữ liệu tương thích. Tên cột kết quả lấy từ SELECT đầu tiên; kiểu dữ liệu được tổng hợp từ các nhánh. Hãy CAST rõ ràng khi cần kiểm soát precision, độ dài, temporal type, NULL placeholder hoặc collation. Nếu cần loại trùng theo khóa nghiệp vụ, hãy dùng logic chọn bản ghi theo khóa thay vì trông chờ UNION DISTINCT. Cuối cùng, đặt ORDER BY đúng phạm vi, lọc sớm và kiểm tra kế hoạch thực thi bằng EXPLAIN.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – UNION Clause](https://dev.mysql.com/doc/refman/8.4/en/union.html)
- [MySQL 8.4 Reference Manual – Set Operations](https://dev.mysql.com/doc/refman/8.4/en/set-operations.html)
- [MySQL 8.4 Reference Manual – CAST() and CONVERT()](https://dev.mysql.com/doc/refman/8.4/en/cast-functions.html)
- [MySQL 8.4 Reference Manual – Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/8.4/en/type-conversion.html)
- [MySQL 8.4 Reference Manual – Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-coercibility.html)
- [MySQL 8.4 Reference Manual – WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)

