# LISTAGG, tràn độ dài kết quả và khác biệt theo phiên bản Oracle

Khi một báo cáo cần hiển thị danh sách đơn hàng, tên nhân viên, mã sản phẩm hoặc trạng thái của nhiều hàng trong cùng một nhóm, việc trả về từng hàng riêng có thể không thuận tiện. Oracle Database cung cấp hàm tổng hợp **`LISTAGG`** để ghép nhiều giá trị thành một chuỗi theo thứ tự xác định.

Ví dụ, thay vì trả ba hàng trạng thái:

```text
CUSTOMER_ID   STATUS
-----------   ------
101           NEW
101           PAID
101           SHIPPED
```

ta có thể tạo một hàng:

```text
CUSTOMER_ID   STATUS_LIST
-----------   --------------------
101           NEW, PAID, SHIPPED
```

LISTAGG rất tiện cho báo cáo, nhưng kết quả của nó có giới hạn độ dài. Khi chuỗi vượt giới hạn, các phiên bản Oracle cũ thường báo `ORA-01489: result of string concatenation is too long`. Từ Oracle Database 12.2, cú pháp `ON OVERFLOW TRUNCATE` cho phép chủ động cắt danh sách và có thể kèm số lượng phần tử bị bỏ. Từ Oracle Database 19c, LISTAGG hỗ trợ `DISTINCT` trực tiếp để loại giá trị trùng.

Bài học này giải thích cú pháp LISTAGG, cách nhóm và sắp xếp dữ liệu, xử lý NULL, giới hạn byte, lựa chọn theo phiên bản và các phương án khi cần kết quả dài hơn giới hạn VARCHAR2.

Sau bài học, bạn có thể:

- Dùng LISTAGG ở dạng aggregate và analytic.
- Kiểm soát delimiter, thứ tự phần tử, giá trị NULL và phần tử trùng.
- Hiểu vì sao cùng một câu SQL có thể chạy ở một phiên bản nhưng lỗi cú pháp hoặc tràn độ dài ở phiên bản khác.
- Chọn `ON OVERFLOW ERROR` hoặc `ON OVERFLOW TRUNCATE` theo yêu cầu dữ liệu.
- Giải thích quan hệ giữa `MAX_STRING_SIZE`, giới hạn VARCHAR2 và số byte thực tế của chuỗi.
- Viết phương án thay thế bằng subquery DISTINCT, XMLAGG hoặc xử lý CLOB khi cần giữ toàn bộ danh sách.
- Kiểm tra hiệu năng, tính ổn định của thứ tự và tính an toàn của dữ liệu xuất.

> Bài học tập trung vào Oracle Database 11gR2 trở lên. Các cú pháp mới như `ON OVERFLOW TRUNCATE` và `LISTAGG(DISTINCT ...)` không có trên mọi phiên bản cũ. Luôn xác định phiên bản database đích trước khi triển khai SQL.

## 1. LISTAGG làm gì?

`LISTAGG` là hàm tổng hợp chuỗi: nó lấy giá trị của nhiều hàng, ghép các giá trị không NULL thành một chuỗi, chèn delimiter giữa các giá trị và sắp xếp phần tử theo `WITHIN GROUP (ORDER BY ...)`.

Cú pháp khái quát:

```sql
LISTAGG(
    [ALL | DISTINCT] measure_expr
    [, delimiter]
    [ON OVERFLOW {ERROR | TRUNCATE [truncation_indicator]
        [{WITH | WITHOUT} COUNT}]]
)
WITHIN GROUP (ORDER BY order_by_clause)
[OVER (query_partition_clause)]
```

Trong đó:

- `measure_expr` là biểu thức tạo ra giá trị cần ghép, thường là cột ký tự.
- `delimiter` là chuỗi ngăn cách hai phần tử liên tiếp; nếu bỏ qua, delimiter mặc định là NULL (không thêm ký tự phân cách).
- `ALL` là hành vi mặc định: giữ các giá trị trùng.
- `DISTINCT` loại các giá trị trùng; cú pháp trực tiếp được hỗ trợ từ Oracle 19c.
- `ON OVERFLOW` xác định xử lý khi kết quả vượt giới hạn.
- `WITHIN GROUP (ORDER BY ...)` xác định thứ tự các giá trị bên trong chuỗi.
- `OVER (PARTITION BY ...)` dùng LISTAGG như hàm phân tích, trả kết quả theo partition mà không gom mất từng hàng.

LISTAGG có thể dùng theo hai dạng:

1. **Aggregate:** tạo một chuỗi cho mỗi nhóm `GROUP BY`, hoặc một chuỗi cho toàn bộ tập hàng nếu không có GROUP BY.
2. **Analytic:** tạo chuỗi cho mỗi partition và lặp kết quả đó trên từng hàng trong partition.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ sau dùng bảng có tiền tố `LAB_`. Hãy chạy trong schema thực hành có quyền `CREATE TABLE`; nếu tên bảng đã tồn tại, chọn tên khác thay vì ghi đè dữ liệu.

```sql
CREATE TABLE lab_listagg_orders (
    order_id    NUMBER(10) PRIMARY KEY,
    customer_id NUMBER(10) NOT NULL,
    status      VARCHAR2(20),
    product_name VARCHAR2(80),
    amount      NUMBER(12, 2)
);

INSERT INTO lab_listagg_orders VALUES
    (1, 101, 'NEW',     'Keyboard',  50);
INSERT INTO lab_listagg_orders VALUES
    (2, 101, 'PAID',    'Mouse',     20);
INSERT INTO lab_listagg_orders VALUES
    (3, 101, 'SHIPPED', 'Monitor',  200);
INSERT INTO lab_listagg_orders VALUES
    (4, 102, 'NEW',     'Cable',     10);
INSERT INTO lab_listagg_orders VALUES
    (5, 102, 'NEW',     'Cable',     10);
INSERT INTO lab_listagg_orders VALUES
    (6, 102, NULL,      'Adapter',   15);
INSERT INTO lab_listagg_orders VALUES
    (7, 103, NULL,      'Stand',     30);

COMMIT;
```

Dữ liệu minh họa:

| ORDER_ID | CUSTOMER_ID | STATUS | PRODUCT_NAME |
| ---: | ---: | --- | --- |
| 1 | 101 | NEW | Keyboard |
| 2 | 101 | PAID | Mouse |
| 3 | 101 | SHIPPED | Monitor |
| 4 | 102 | NEW | Cable |
| 5 | 102 | NEW | Cable |
| 6 | 102 | NULL | Adapter |
| 7 | 103 | NULL | Stand |

Hàng có `STATUS NULL` được giữ trong bảng để quan sát cách LISTAGG xử lý NULL. Khách hàng 102 có hai giá trị `NEW` và hai tên sản phẩm `Cable` trùng nhau; khách hàng 103 chỉ có trạng thái NULL.

## 3. LISTAGG dạng aggregate

### 3.1. Ghép một cột thành một chuỗi

```sql
SELECT
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Kết quả:

```text
NEW, PAID, SHIPPED
```

`ORDER BY order_id` trong `WITHIN GROUP` sắp xếp các giá trị bên trong chuỗi. Nếu bỏ điều kiện khách hàng và không dùng GROUP BY, LISTAGG tạo **một chuỗi cho tất cả hàng**:

```sql
SELECT
    LISTAGG(status, ' | ')
        WITHIN GROUP (ORDER BY customer_id, order_id) AS all_statuses
FROM lab_listagg_orders;
```

### 3.2. Một chuỗi cho mỗi nhóm

Thường LISTAGG được dùng cùng `GROUP BY`:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả minh họa:

| CUSTOMER_ID | STATUS_LIST |
| ---: | --- |
| 101 | NEW, PAID, SHIPPED |
| 102 | NEW, NEW |
| 103 | NULL |

Với khách hàng 102, hàng có STATUS NULL bị bỏ qua; hai giá trị NEW được giữ vì mặc định là ALL. Với khách hàng 103, mọi measure đều NULL nên kết quả LISTAGG là NULL.

### 3.3. Delimiter mặc định và delimiter tùy chọn

Nếu bỏ delimiter:

```sql
SELECT LISTAGG(status)
       WITHIN GROUP (ORDER BY order_id) AS joined_status
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Kết quả là `NEWPAIDSHIPPED`. Delimiter có thể là dấu phẩy, dấu gạch, dấu xuống dòng hoặc chuỗi khác:

```sql
SELECT LISTAGG(status, CHR(10))
       WITHIN GROUP (ORDER BY order_id) AS status_lines
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Ở đây `CHR(10)` là line feed; client có thể hiển thị các phần tử trên nhiều dòng hoặc hiển thị ký tự điều khiển tùy cấu hình. Khi xuất file, phải xác định cách xử lý newline và quoting.

Delimiter được chèn **giữa các measure values**, không phải trước phần tử đầu hoặc sau phần tử cuối. Nếu delimiter là NULL, LISTAGG không thêm dấu phân cách.

### 3.4. LISTAGG bỏ qua measure NULL

LISTAGG không thêm phần tử cho hàng mà `measure_expr` là NULL. Ví dụ:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(status) AS nonnull_status_rows,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
WHERE customer_id = 102;
```

Kết quả có 3 hàng, 2 status không NULL và chuỗi `NEW, NEW`. LISTAGG không chèn một delimiter đại diện cho status NULL.

Đối với Oracle, chuỗi ký tự độ dài 0 (`''`) được xử lý như NULL trong ngữ cảnh ký tự thông thường. Vì vậy, measure biểu thức tạo ra chuỗi rỗng cũng có thể bị LISTAGG bỏ qua như một giá trị NULL. Cần nhớ quy tắc này khi dữ liệu nguồn đến từ ứng dụng hoặc phép nối chuỗi.

### 3.5. Thứ tự bên trong LISTAGG khác ORDER BY bên ngoài

Hai vị trí ORDER BY có nhiệm vụ khác nhau:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id DESC) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id ASC;
```

- `ORDER BY order_id DESC` bên trong `WITHIN GROUP` quyết định thứ tự status được ghép.
- `ORDER BY customer_id ASC` ở cuối câu SQL quyết định thứ tự các hàng kết quả (các nhóm).

Không thể chuyển ORDER BY bên trong ra cuối câu truy vấn rồi kỳ vọng thứ tự phần tử trong chuỗi thay đổi theo.

## 4. Tính xác định của thứ tự và các giá trị trùng

Oracle chỉ bảo đảm thứ tự LISTAGG khi danh sách biểu thức ORDER BY tạo ra một thứ tự xác định. Nếu nhiều hàng có cùng giá trị sắp xếp, thứ tự tương đối giữa chúng có thể không ổn định.

Ví dụ:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY status) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id;
```

Nếu một khách hàng có nhiều hàng status NEW, chỉ ORDER BY STATUS không xác định thứ tự riêng của các hàng đó. Với chuỗi chỉ gồm status giống nhau thì kết quả nhìn có vẻ giống, nhưng khi measure có thêm dữ liệu khác hoặc biểu thức phức tạp, sự không xác định có thể trở nên rõ ràng.

Hãy thêm khóa duy nhất làm tie-breaker:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY status, order_id) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id;
```

Quy tắc:

- Nếu cần tái lập cùng một chuỗi qua các lần chạy, ORDER BY bên trong LISTAGG nên có đủ cột để phân biệt thứ tự các hàng liên quan.
- Nếu dùng nhiều cột, xác định rõ ASC/DESC và cách xử lý NULL nếu cột sắp xếp có thể NULL.
- Không dựa vào thứ tự vật lý của bảng, thứ tự index hoặc kết quả tình cờ của execution plan.

## 5. LISTAGG dạng analytic

LISTAGG cũng có thể hoạt động như analytic function bằng `OVER (PARTITION BY ...)`. Khi đó mỗi hàng vẫn được giữ, và mỗi hàng nhận chuỗi tổng hợp của partition tương ứng.

```sql
SELECT
    order_id,
    customer_id,
    status,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id)
        OVER (PARTITION BY customer_id) AS customer_statuses
FROM lab_listagg_orders
ORDER BY customer_id, order_id;
```

Kết quả khái niệm:

| ORDER_ID | CUSTOMER_ID | STATUS | CUSTOMER_STATUSES |
| ---: | ---: | --- | --- |
| 1 | 101 | NEW | NEW, PAID, SHIPPED |
| 2 | 101 | PAID | NEW, PAID, SHIPPED |
| 3 | 101 | SHIPPED | NEW, PAID, SHIPPED |
| 4 | 102 | NEW | NEW, NEW |
| 5 | 102 | NEW | NEW, NEW |
| 6 | 102 | NULL | NEW, NEW |
| 7 | 103 | NULL | NULL |

Khác biệt:

| Aggregate LISTAGG | Analytic LISTAGG |
| --- | --- |
| Thường kết hợp GROUP BY | Dùng OVER để chia partition |
| Trả một hàng cho mỗi nhóm | Giữ mỗi hàng nguồn |
| Hữu ích cho báo cáo tổng hợp | Hữu ích khi cần vừa xem chi tiết vừa có chuỗi tổng hợp |

Không đặt một `ORDER BY` cuối câu SQL vào thay cho thứ tự trong `WITHIN GROUP`. Phần `OVER (PARTITION BY ...)` xác định partition; `WITHIN GROUP` vẫn kiểm soát thứ tự các phần tử trong chuỗi.

## 6. Loại bỏ phần tử trùng: ALL, DISTINCT và phiên bản

### 6.1. Mặc định LISTAGG giữ giá trị trùng

Với khách hàng 102:

```sql
SELECT
    customer_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders
WHERE customer_id = 102
GROUP BY customer_id;
```

Kết quả:

```text
Cable, Cable, Adapter
```

Đây là hành vi mặc định `ALL`. Hai đơn hàng khác nhau cùng có sản phẩm Cable nên LISTAGG hiển thị Cable hai lần.

### 6.2. LISTAGG DISTINCT từ Oracle 19c

Oracle Database 19c hỗ trợ từ khóa `DISTINCT` trực tiếp trong LISTAGG:

```sql
SELECT
    customer_id,
    LISTAGG(DISTINCT product_name, ', ')
        WITHIN GROUP (ORDER BY product_name) AS unique_products
FROM lab_listagg_orders
WHERE customer_id = 102
GROUP BY customer_id;
```

Kết quả chỉ có mỗi sản phẩm một lần:

```text
Adapter, Cable
```

DISTINCT loại các measure trùng nhau trước khi ghép. Đối với dữ liệu ký tự, việc xác định hai giá trị trùng còn cần xét kiểu dữ liệu/collation và quy tắc so sánh hiệu lực của database/biểu thức.

Nếu cần thứ tự nghiệp vụ khác thứ tự alphabet, hãy cân nhắc dữ liệu nào đại diện cho thứ tự của giá trị duy nhất. Không nên thêm một cột tie-breaker tùy ý vào ORDER BY của LISTAGG DISTINCT nếu cột đó không có ý nghĩa duy nhất cho từng measure sau khi loại trùng.

### 6.3. Oracle 11gR2 đến trước 19c: DISTINCT qua subquery

Trên phiên bản chưa hỗ trợ `LISTAGG(DISTINCT ...)`, loại trùng ở một truy vấn con rồi mới LISTAGG:

```sql
SELECT
    customer_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY product_name) AS unique_products
FROM (
    SELECT DISTINCT customer_id, product_name
    FROM lab_listagg_orders
    WHERE customer_id = 102
      AND product_name IS NOT NULL
)
GROUP BY customer_id;
```

Nếu tổng hợp nhiều khách hàng, giữ khóa nhóm trong subquery như ví dụ để không loại trùng xuyên qua các nhóm khác nhau. Cần lọc/giữ NULL theo đúng mục tiêu; LISTAGG tự bỏ measure NULL nên điều kiện `IS NOT NULL` ở đây chủ yếu giúp thể hiện ý định.

### 6.4. Tránh loại trùng sai phạm vi

Ví dụ không đúng mục tiêu:

```sql
SELECT DISTINCT product_name
FROM lab_listagg_orders;
```

Nếu sau đó ghép danh sách cho nhiều khách hàng, câu trên loại trùng trên toàn bảng, khiến cùng một sản phẩm chỉ còn một lần cho tất cả khách hàng. Khi cần DISTINCT theo từng nhóm, subquery phải bao gồm **các khóa nhóm và measure**.

## 7. Vì sao LISTAGG có thể bị tràn độ dài?

LISTAGG tạo kết quả dạng `VARCHAR2` (hoặc `RAW` nếu measure là RAW). Kết quả có giới hạn độ dài tối đa theo kiểu dữ liệu và tham số `MAX_STRING_SIZE`.

Với kết quả VARCHAR2:

| MAX_STRING_SIZE | Giới hạn tối đa của kết quả LISTAGG |
| --- | ---: |
| `STANDARD` | 4000 byte |
| `EXTENDED` | 32767 byte |

Với measure kiểu RAW, giới hạn tương ứng là 2000 byte ở STANDARD và 32767 byte ở EXTENDED. Trong trường hợp RAW, delimiter và truncation indicator cũng cần có kiểu RAW tương thích.

**Giới hạn được tính theo byte**, không phải luôn theo số ký tự. Nếu database dùng character set đa byte như AL32UTF8, một ký tự có thể chiếm nhiều byte. Một danh sách 1500 ký tự tiếng Việt không nhất thiết chỉ chiếm 1500 byte.

### 7.1. Kiểm tra MAX_STRING_SIZE

Người dùng có quyền xem tham số có thể truy vấn:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
```

Hoặc trong SQL*Plus/SQLcl:

```sql
SHOW PARAMETER max_string_size
```

Giá trị phổ biến:

- `STANDARD`: giới hạn VARCHAR2 SQL truyền thống.
- `EXTENDED`: cho phép kiểu VARCHAR2/RAW SQL có giới hạn lớn hơn trong những điều kiện Oracle hỗ trợ.

`MAX_STRING_SIZE` là tham số cấu hình database có quy trình quản trị riêng. **Không thể đổi bằng ALTER SESSION** và không nên thay đổi chỉ để chữa một báo cáo LISTAGG bị dài. Chuyển sang EXTENDED có các yêu cầu triển khai/upgrade và hệ quả tương thích; hãy để DBA đánh giá.

### 7.2. ORA-01489: lỗi kết quả nối chuỗi quá dài

Trên các phiên bản hoặc cách gọi LISTAGG dùng chế độ mặc định, nếu kết quả vượt giới hạn, Oracle báo:

```text
ORA-01489: result of string concatenation is too long
```

Đây là lỗi ở **độ dài kết quả tổng hợp**, không nhất thiết do một cột nguồn đơn lẻ quá dài. Một measure có thể ngắn, nhưng hàng nghìn measure cộng delimiter lại vượt giới hạn.

Ví dụ minh họa cách tạo chuỗi dài:

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS value_text
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT LISTAGG(value_text, ', ')
       WITHIN GROUP (ORDER BY id) AS long_text
FROM generated_rows;
```

Tổng độ dài trong ví dụ này vượt 4000 byte theo STANDARD và có thể tạo ORA-01489 nếu không có cách xử lý overflow. Không cần chạy câu lệnh tạo chuỗi lớn trên hệ thống production để kiểm tra.

### 7.3. Tính sơ bộ kích thước kết quả

Nếu có `n` measure không NULL, độ dài kết quả gần bằng:

```text
Tổng độ dài các measure
+ (n - 1) × độ dài delimiter
```

Đây chỉ là ước lượng khái niệm; phải tính theo **byte**, chuyển đổi kiểu dữ liệu, character set và delimiter thực tế. Với dữ liệu nhiều byte, `LENGTHB` phù hợp hơn `LENGTH` khi ước tính dung lượng:

```sql
SELECT
    SUM(LENGTHB(product_name)) AS measure_bytes,
    (COUNT(product_name) - 1) * LENGTHB(', ') AS delimiter_bytes,
    SUM(LENGTHB(product_name))
      + GREATEST(COUNT(product_name) - 1, 0) * LENGTHB(', ')
        AS estimated_bytes
FROM lab_listagg_orders
WHERE customer_id = 102;
```

Ví dụ trên ước lượng một nhóm cụ thể với delimiter `', '`. LISTAGG bỏ qua NULL, nên dùng `COUNT(product_name)` thay cho `COUNT(*)` để đếm số measure thực sự được nối.

Không dựa vào ước lượng này để bảo đảm truy vấn không tràn nếu measure là biểu thức có chuyển kiểu, collation/encoding khác hoặc dữ liệu thay đổi đồng thời; nó là chỉ báo dung lượng trước khi chạy.

## 8. Xử lý overflow từ Oracle 12.2: ON OVERFLOW ERROR/TRUNCATE

Oracle Database 12.2 bổ sung **overflow clause** cho LISTAGG.

### 8.1. ON OVERFLOW ERROR

`ON OVERFLOW ERROR` yêu cầu hành vi báo lỗi khi kết quả vượt giới hạn. Đây cũng là hành vi mặc định nếu không chỉ rõ overflow clause:

```sql
SELECT
    LISTAGG(product_name, ', ' ON OVERFLOW ERROR)
        WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

Nếu kết quả vượt giới hạn, câu SQL có thể báo `ORA-01489`. Chế độ này phù hợp khi **thiếu bất kỳ phần tử nào cũng là lỗi dữ liệu** và caller phải xử lý.

### 8.2. ON OVERFLOW TRUNCATE

`ON OVERFLOW TRUNCATE` cho phép Oracle cắt danh sách để kết quả nằm trong giới hạn và thêm một dấu hiệu báo đã cắt:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE
    ) WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

Truncation indicator mặc định là `...`. Có thể chỉ định indicator khác:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '[con lai]'
    ) WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

**TRUNCATE là mất dữ liệu có chủ đích trong kết quả.** Nó chỉ phù hợp khi ứng dụng chấp nhận danh sách rút gọn và có cách nhận biết kết quả không đầy đủ. Nếu API cần tất cả phần tử, hãy dùng kiểu trả về/thiết kế khác, không dùng TRUNCATE để che lỗi.

### 8.3. WITH COUNT và WITHOUT COUNT

Từ 12.2, có thể chọn:

- `WITH COUNT`: thêm số lượng phần tử bị cắt trong ngoặc ở cuối.
- `WITHOUT COUNT`: chỉ thêm truncation indicator, không in số lượng phần tử bị bỏ.

Ví dụ:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS products_with_count,
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITHOUT COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS products_without_count
FROM lab_listagg_orders;
```

Nếu không chỉ định WITH/WITHOUT COUNT, mặc định là **WITH COUNT**. Khi WITH COUNT, kết quả có thể bị cắt sớm hơn vì Oracle phải dành đủ chỗ cho delimiter cuối, truncation indicator và phần đếm số phần tử bị bỏ (Oracle dành vùng dự phòng theo quy tắc của nó, gồm tối đa 24 ký tự cho số đếm được đặt trong ngoặc). Vì vậy không tự tính vị trí cắt chỉ bằng cách trừ độ dài indicator.

Oracle cắt tại ranh giới các measure values, không tùy tiện cắt giữa một giá trị measure. Kết quả giữ một số phần tử đầy đủ, rồi indicator và có thể là count.

### 8.4. Chọn indicator phù hợp

Indicator nên nói rõ dữ liệu đã bị rút gọn, ví dụ:

```sql
LISTAGG(
    product_name,
    ', ' ON OVERFLOW TRUNCATE '...[truncated]' WITHOUT COUNT
)
WITHIN GROUP (ORDER BY order_id)
```

Trong giao diện người dùng, có thể dùng indicator ngắn như `...`. Trong log/audit, nên chọn indicator dễ nhận biết và lưu thêm metadata như tổng số phần tử, số phần tử hiển thị và số phần tử bị bỏ. Đừng dùng một chuỗi có thể xuất hiện hợp lệ trong dữ liệu mà không có quy ước phân biệt.

### 8.5. TRUNCATE không thay thế xử lý CLOB

Nếu một danh sách có 100.000 phần tử và API phải trả đầy đủ, cắt chuỗi thành 4000/32767 byte không giải quyết yêu cầu. Các lựa chọn phù hợp hơn:

- Trả dữ liệu theo **nhiều hàng** và để ứng dụng hiển thị/gom ở tầng cần thiết.
- Trả **JSON array** hoặc một cấu trúc dữ liệu có kiểu phù hợp thay vì chuỗi phân cách.
- Dùng **CLOB** và một phương pháp aggregate/ghép CLOB phù hợp nếu thật sự cần một giá trị văn bản dài.
- Phân trang kết quả thay vì tạo một chuỗi rất lớn.

## 9. Khác biệt theo phiên bản Oracle

Đây là bảng mốc chính để quyết định cú pháp:

| Phiên bản | LISTAGG cơ bản | ON OVERFLOW TRUNCATE | LISTAGG DISTINCT |
| --- | --- | --- | --- |
| Oracle 11g Release 2 | Có | Không | Không |
| Oracle 12.1 | Có | Không | Không |
| Oracle 12.2 | Có | Có | Không |
| Oracle 18c | Có | Có | Không |
| Oracle 19c | Có | Có | Có |
| Các phiên bản mới hơn | Có | Có | Có |

Mốc tính năng quan trọng:

1. **11gR2:** LISTAGG được giới thiệu, dùng `WITHIN GROUP (ORDER BY ...)`.
2. **12.2:** bổ sung `ON OVERFLOW ERROR/TRUNCATE`, indicator và WITH/WITHOUT COUNT.
3. **19c:** bổ sung `DISTINCT` trong LISTAGG.
4. **MAX_STRING_SIZE:** tham số cấu hình riêng quyết định giới hạn VARCHAR2/RAW (STANDARD/EXTENDED); nó không thay đổi mốc cú pháp DISTINCT hoặc overflow clause.

Nếu SQL cần chạy trên nhiều đời Oracle, hãy xác định **phiên bản thấp nhất** trong môi trường hỗ trợ. Một câu SQL chứa `ON OVERFLOW TRUNCATE` sẽ không biên dịch trên database cũ không hỗ trợ cú pháp đó; tương tự, `LISTAGG(DISTINCT ...)` không dùng được trước 19c.

### 9.1. Kiểm tra phiên bản database

Có thể xem phiên bản:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Hoặc với quyền xem view phù hợp:

```sql
SELECT version, version_full
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Tên/cột khả dụng có thể thay đổi theo phiên bản. Một cách tổng quát khác là:

```sql
SELECT * FROM v$version;
```

Đừng nhầm phiên bản client SQL Developer/SQLcl với **phiên bản database server**: cú pháp được thực thi và hỗ trợ bởi server.

### 9.2. Tách SQL theo khả năng server

Ứng dụng hỗ trợ nhiều phiên bản có thể:

- Dùng SQL cơ bản LISTAGG cho phiên bản thấp nhất nếu độ dài dữ liệu được kiểm soát.
- Chỉ thêm `ON OVERFLOW TRUNCATE` khi server hỗ trợ từ 12.2.
- Chỉ dùng `DISTINCT` trong LISTAGG khi server hỗ trợ từ 19c.
- Với phiên bản cũ, loại trùng ở subquery.
- Với kết quả dài, chọn CLOB/JSON/multiple rows thay vì trông chờ một tính năng cú pháp không có.

Không nên chỉ bắt lỗi cú pháp ở runtime để quyết định chiến lược. Tốt hơn là biết version/capability khi triển khai và kiểm thử SQL trên đúng server.

## 10. MAX_STRING_SIZE và giới hạn theo byte

### 10.1. STANDARD và EXTENDED

`MAX_STRING_SIZE` quyết định giới hạn tối đa của các kiểu VARCHAR2/RAW trong SQL:

| Kiểu kết quả | STANDARD | EXTENDED |
| --- | ---: | ---: |
| VARCHAR2 | 4000 byte | 32767 byte |
| RAW | 2000 byte | 32767 byte |

LISTAGG trả VARCHAR2 nếu measure là kiểu ký tự, hoặc RAW khi measure là RAW theo quy tắc kiểu dữ liệu. Vì thế giới hạn LISTAGG không phải một con số “4000 ký tự” áp dụng cho mọi hệ thống.

### 10.2. Character set nhiều byte

Trong database dùng AL32UTF8, một ký tự có thể chiếm từ một đến nhiều byte. Do đó:

- `LENGTH(text)` đếm ký tự theo quy tắc của Oracle.
- `LENGTHB(text)` đếm số byte.
- Giới hạn VARCHAR2/LISTAGG được xét theo byte.

Ví dụ:

```sql
SELECT
    LENGTH('Oracle') AS char_count,
    LENGTHB('Oracle') AS byte_count,
    LENGTH('Tiếng Việt') AS viet_char_count,
    LENGTHB('Tiếng Việt') AS viet_byte_count
FROM dual;
```

Kết quả cụ thể phụ thuộc database character set. Hãy dùng chính môi trường triển khai để đo; không dùng số ký tự trên giao diện làm bằng chứng chuỗi nằm dưới giới hạn.

### 10.3. Không nên tăng MAX_STRING_SIZE chỉ vì một LISTAGG lỗi

Chuyển STANDARD sang EXTENDED là quyết định cấp database, có quy trình và tác động tương thích. Nó không:

- Làm LISTAGG trả CLOB không giới hạn.
- Loại bỏ mọi khả năng ORA-01489 khi danh sách vẫn vượt 32767 byte.
- Sửa truy vấn đang tổng hợp quá nhiều dữ liệu không cần thiết.
- Giải quyết nhu cầu truyền hàng trăm nghìn phần tử trong một VARCHAR2.

Trước hết cần xác định **người dùng có thật sự cần một chuỗi duy nhất hay không**, có thể phân trang hoặc trả nhiều hàng không, và dữ liệu có thể được biểu diễn dưới dạng CLOB/JSON hay không.

## 11. Giải pháp cho phiên bản cũ và danh sách dài

### 11.1. Trước 12.2: không có ON OVERFLOW TRUNCATE

Trên Oracle 11gR2/12.1, LISTAGG không hỗ trợ overflow clause. Nếu kết quả vượt giới hạn, truy vấn có thể báo ORA-01489. Cần lựa chọn:

- Giới hạn tập dữ liệu trước khi tổng hợp nếu nghiệp vụ chỉ cần một tập con.
- Trả từng hàng cho ứng dụng tự phân trang/gom.
- Dùng phương án tạo CLOB như XMLAGG hoặc xử lý LOB phù hợp.
- Tăng giới hạn VARCHAR2 ở cấp database chỉ khi có kế hoạch DBA được phê duyệt và điều đó thực sự giải quyết nhu cầu.

### 11.2. Dùng XMLAGG để tạo kết quả CLOB

Một mẫu thường gặp dùng `XMLAGG` và `XMLELEMENT`:

```sql
SELECT
    XMLAGG(
        XMLELEMENT(e, product_name || ', ')
        ORDER BY order_id
    ).EXTRACT('//text()').GETCLOBVAL() AS product_list_clob
FROM lab_listagg_orders
WHERE customer_id = 102;
```

Kết quả là một CLOB chứa nội dung được ghép cùng delimiter (mẫu trên có delimiter ở cuối). XMLAGG là aggregate trên XMLType và không bị ràng buộc theo cùng giới hạn VARCHAR2 của LISTAGG.

**Cần kiểm thử ký tự đặc biệt XML** như `&`, `<`, `>` và nội dung Unicode. XML serialization/escaping có thể làm biểu diễn khác chuỗi văn bản gốc; nếu dùng cho dữ liệu người dùng hoặc cần round-trip chính xác, phải xử lý/giải mã theo quy tắc XML phù hợp. Đừng coi XMLAGG là một phép nối chuỗi thuần không có tác dụng phụ về escaping.

### 11.3. Xây CLOB bằng DBMS_LOB trong PL/SQL

Nếu cần quy tắc ghép rõ ràng và đầu ra CLOB, có thể tạo temporary CLOB rồi append từng measure. Ví dụ minh họa với measure VARCHAR2:

```sql
SET SERVEROUTPUT ON

DECLARE
    l_result    CLOB;
    l_delimiter VARCHAR2(10) := ', ';
    l_first     BOOLEAN := TRUE;
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_result, TRUE);

    FOR r IN (
        SELECT product_name
        FROM lab_listagg_orders
        WHERE customer_id = 102
        ORDER BY order_id
    ) LOOP
        IF r.product_name IS NOT NULL THEN
            IF NOT l_first THEN
                DBMS_LOB.WRITEAPPEND(
                    l_result,
                    LENGTH(l_delimiter),
                    l_delimiter
                );
            END IF;

            DBMS_LOB.WRITEAPPEND(
                l_result,
                LENGTH(r.product_name),
                r.product_name
            );
            l_first := FALSE;
        END IF;
    END LOOP;

    -- Chỉ in phần đầu để minh họa; DBMS_OUTPUT có giới hạn dòng.
    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(l_result, 4000, 1));
    DBMS_LOB.FREETEMPORARY(l_result);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_result) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_result);
        END IF;
        RAISE;
END;
/
```

Đoạn PL/SQL trên minh họa cách quản lý delimiter và bỏ qua measure NULL. Trong ứng dụng thật:

- Không in CLOB lớn qua `DBMS_OUTPUT` như thể output console không có giới hạn.
- Trả CLOB qua OUT parameter, đọc bằng JDBC LOB API hoặc lưu vào cột CLOB phù hợp.
- Xử lý temporary LOB trong mọi đường thành công/lỗi.
- Nếu measure là CLOB, dùng các thao tác LOB phù hợp thay vì giả định `WRITEAPPEND` với VARCHAR2 buffer có thể nhận nội dung bất kỳ độ dài.
- Đảm bảo ORDER BY có tie-breaker nếu cần thứ tự tái lập.

### 11.4. Trả JSON array thay vì một chuỗi delimiter

Nếu consumer là REST API hoặc ứng dụng, một mảng JSON thường an toàn hơn chuỗi nối bằng dấu phẩy:

```json
["Keyboard", "Mouse", "Monitor"]
```

JSON giữ ranh giới phần tử rõ ràng; một giá trị chứa dấu phẩy không bị hiểu nhầm thành nhiều phần tử. Các phiên bản Oracle hỗ trợ `JSON_ARRAYAGG` và các tùy chọn `RETURNING CLOB` có thể tạo JSON lớn hơn VARCHAR2 trong điều kiện phù hợp:

```sql
SELECT JSON_ARRAYAGG(
           product_name
           ORDER BY order_id
           RETURNING CLOB
       ) AS products_json
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Kiểm tra cú pháp/tính năng JSON trên phiên bản server cụ thể. JSON array **không tương đương** chuỗi LISTAGG: nó là cấu trúc dữ liệu có kiểu và cần consumer parse JSON.

### 11.5. Khi nào nên trả nhiều hàng thay vì aggregate?

Nếu ứng dụng cần:

- Phân trang từng sản phẩm.
- Lọc/sắp xếp ở client hoặc server.
- Mở chi tiết một phần tử.
- Truyền danh sách có thể lên đến hàng chục nghìn giá trị.
- Giữ đúng kiểu dữ liệu của mỗi phần tử.

thì trả nhiều hàng thường phù hợp hơn LISTAGG. Tổng hợp thành một chuỗi dài làm mất cấu trúc từng phần tử, khiến parse ngược phức tạp và tăng bộ nhớ ở database/client.

## 12. Dữ liệu chứa delimiter và nguy cơ không thể tách ngược

Giả sử danh sách sản phẩm:

```text
Adapter, USB
Cable
```

Nếu LISTAGG dùng delimiter `', '`, kết quả có thể là:

```text
Adapter, USB, Cable
```

Không thể biết chắc chuỗi này có ba sản phẩm `Adapter`, `USB`, `Cable` hay hai sản phẩm `Adapter, USB` và `Cable` nếu không có quy tắc escaping/quoting. LISTAGG chỉ ghép chuỗi; nó không tự mã hóa ranh giới giá trị.

Khi tạo CSV:

- Phải dùng quy tắc quote và escape chuẩn CSV cho từng field.
- Không chỉ nối bằng dấu phẩy rồi giả định có thể split đơn giản.
- Nếu dữ liệu có dấu xuống dòng, dấu nháy hoặc delimiter, phải escape đúng.

Khi truyền qua API:

- Ưu tiên JSON array hoặc result set.
- Nếu bắt buộc dùng một chuỗi, định nghĩa rõ delimiter và escape format.
- Ghi rõ có bỏ NULL/duplicate/truncate hay không.

Một chuỗi LISTAGG phục vụ hiển thị có thể rất phù hợp; một chuỗi được dùng như **định dạng lưu trữ để parse ngược** cần hợp đồng chặt chẽ hơn.

## 13. Hiệu năng và execution plan

LISTAGG phải xử lý nhiều giá trị trong từng nhóm và sắp xếp theo `WITHIN GROUP`. Với nhóm lớn, công việc sắp xếp có thể tiêu thụ PGA/TEMP và CPU; `DISTINCT` có thể bổ sung chi phí loại trùng.

### 13.1. Giảm dữ liệu trước khi tổng hợp

Không aggregate nhiều hàng hơn mức nghiệp vụ cần:

```sql
SELECT customer_id,
       LISTAGG(product_name, ', ')
           WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders
WHERE status IN ('NEW', 'PAID')
GROUP BY customer_id;
```

WHERE giảm tập hàng đầu vào trước khi LISTAGG. Hãy bảo đảm điều kiện lọc đúng yêu cầu, không lọc để né ORA-01489 rồi vô tình bỏ dữ liệu nghiệp vụ.

### 13.2. Index không tự bảo đảm LISTAGG không phải sort

Index có thể hỗ trợ truy cập hàng theo nhóm hoặc thứ tự, nhưng optimizer quyết định plan dựa trên thống kê, selectivity, join, group và chi phí. Đừng suy ra cứ có index trên `(customer_id, order_id)` thì LISTAGG sẽ không cần xử lý sort.

Xem execution plan theo công cụ phù hợp, ví dụ `DBMS_XPLAN` nếu có quyền:

```sql
EXPLAIN PLAN FOR
SELECT customer_id,
       LISTAGG(status, ', ')
           WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
GROUP BY customer_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` là plan ước tính; nó không thay thế việc quan sát plan thực thi thực tế và thống kê runtime trong môi trường có quyền/công cụ thích hợp.

### 13.3. Tránh tổng hợp lặp lại cùng partition

Nếu một báo cáo vừa cần danh sách status vừa cần danh sách sản phẩm, hãy xem xét:

- Có thể dùng một truy vấn nhóm với các aggregate phù hợp không?
- Có cần cùng một tập dữ liệu và cùng điều kiện lọc không?
- Có đang join làm nhân bản hàng trước LISTAGG không?
- Có thể tổng hợp ở subquery trước rồi join kết quả nhóm để tránh nhân bản không?

Join một-nhiều trước khi LISTAGG có thể làm measure xuất hiện nhiều lần không mong muốn. Đừng thêm DISTINCT để che lỗi nhân bản do join nếu quan hệ dữ liệu cần được sửa.

### 13.4. Đếm phần tử trước khi quyết định truncate

Một báo cáo có thể trả cùng lúc số phần tử và chuỗi hiển thị:

```sql
SELECT
    customer_id,
    COUNT(product_name) AS product_count,
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS product_list
FROM lab_listagg_orders
GROUP BY customer_id;
```

Số đếm riêng giúp consumer biết quy mô tổng thể, còn LISTAGG có indicator để báo phần chuỗi đã bị cắt. Nếu cần biết chính xác phần tử nào bị bỏ, hãy truy vấn chi tiết/phân trang; chỉ số count không cho biết nội dung các giá trị bị bỏ.

## 14. Các lỗi và bẫy thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ORA-01489` | Chuỗi LISTAGG vượt giới hạn VARCHAR2/RAW | Từ 12.2 dùng TRUNCATE nếu được phép mất phần tử; nếu phải giữ đủ, chọn CLOB/JSON/multiple rows |
| `ORA-00923` hoặc lỗi cú pháp ở OVERFLOW | Server chưa hỗ trợ `ON OVERFLOW TRUNCATE` hoặc đặt clause sai vị trí | Xác nhận version; dùng cú pháp đúng, hoặc giải pháp tương thích cũ |
| Lỗi cú pháp với `LISTAGG(DISTINCT ...)` | Server trước 19c | SELECT DISTINCT ở subquery rồi LISTAGG |
| Danh sách bị lặp giá trị | Mặc định LISTAGG là ALL hoặc JOIN nhân bản hàng | Xem quan hệ join; dùng DISTINCT chỉ khi nghiệp vụ thực sự muốn loại trùng |
| Thứ tự chuỗi thay đổi giữa lần chạy | ORDER BY trong WITHIN GROUP không duy nhất | Thêm khóa phụ duy nhất/tie-breaker |
| Danh sách không có giá trị dù có hàng | Measure toàn NULL hoặc biểu thức trả NULL | Kiểm tra COUNT(measure), NULL và kiểu dữ liệu |
| Có delimiter lặp bất ngờ | Dữ liệu nguồn chứa chuỗi delimiter hoặc measure đã được nối trước | Chuẩn hóa measure và định nghĩa escaping |
| Chuỗi bị cắt dù tưởng còn chỗ | Giới hạn tính theo byte; WITH COUNT/indicator cần vùng dự phòng | Dùng LENGTHB, xem character set và kiểu output |
| DISTINCT loại những giá trị tưởng khác nhau | Collation/kiểu dữ liệu làm chúng được xem tương đương | Kiểm tra collation và quy tắc so sánh |
| LISTAGG chạy chậm | Nhóm lớn, sort, distinct hoặc join nhân bản | Lọc đúng, xem plan, thống kê, chia nhỏ/đổi cấu trúc kết quả |
| SQL chạy trên dev nhưng không compile production | Khác version server | Xác nhận version thấp nhất và viết SQL tương thích |
| JSON/XML output khác chuỗi gốc | Escaping/serialization | Dùng cấu trúc có kiểu và decode đúng giao thức |

### 14.1. Checklist chẩn đoán ORA-01489

1. Xác định câu LISTAGG nào tràn và nhóm nào có nhiều phần tử nhất.
2. Đo số measure không NULL bằng `COUNT(measure)`.
3. Ước lượng byte bằng `SUM(LENGTHB(measure))` cộng delimiter.
4. Kiểm tra `MAX_STRING_SIZE` và character set database.
5. Xác định consumer có chấp nhận kết quả bị cắt không.
6. Nếu chấp nhận, cân nhắc `ON OVERFLOW TRUNCATE` từ 12.2.
7. Nếu cần đầy đủ, chuyển sang CLOB/JSON/multiple rows hoặc giới hạn nghiệp vụ hợp lý.
8. Kiểm tra version server trước khi dùng cú pháp mới.

Không tăng `MAX_STRING_SIZE` hoặc thêm DISTINCT chỉ để hết lỗi mà chưa xác nhận yêu cầu dữ liệu.

## 15. So sánh các lựa chọn triển khai

| Nhu cầu | Giải pháp | Lưu ý |
| --- | --- | --- |
| Chuỗi ngắn, nhóm nhỏ, cần đủ tất cả giá trị | LISTAGG mặc định/ON OVERFLOW ERROR | Lỗi khi vượt giới hạn giúp phát hiện dữ liệu quá lớn |
| Danh sách hiển thị có thể rút gọn | LISTAGG ON OVERFLOW TRUNCATE | Phải báo rõ đã truncate; không dùng cho dữ liệu cần đầy đủ |
| Loại trùng trên Oracle 19c+ | LISTAGG DISTINCT | Kiểm tra collation và ý nghĩa của loại trùng |
| Loại trùng trên bản trước 19c | SELECT DISTINCT trong subquery | Giữ đủ khóa nhóm trong subquery |
| Cần CLOB dài trong SQL | XMLAGG hoặc phương án aggregate LOB thích hợp | Kiểm tra XML escaping, thứ tự và tài nguyên |
| Cần CLOB tùy biến | PL/SQL với DBMS_LOB | Quản lý temporary LOB và exception cleanup |
| Trả danh sách có cấu trúc cho API | JSON_ARRAYAGG/JSON array | Cần server hỗ trợ và consumer parse JSON |
| Danh sách rất lớn, cần phân trang/tương tác | Trả nhiều hàng | Giữ kiểu dữ liệu và ranh giới phần tử rõ ràng |

Không có một lựa chọn tốt nhất cho mọi bài toán. Hãy chọn theo **độ dài tối đa, yêu cầu đầy đủ, phiên bản server, định dạng consumer và khả năng phân trang**.

## 16. Bài thực hành tổng hợp

### Bước 1 — LISTAGG theo khách hàng

```sql
SELECT
    customer_id,
    LISTAGG(status, ' -> ')
        WITHIN GROUP (ORDER BY order_id) AS status_flow
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Dự đoán:

- Khách hàng 101 có ba status theo order_id.
- Khách hàng 102 có hai NEW; status NULL bị bỏ.
- Khách hàng 103 chỉ có status NULL nên kết quả là NULL.

### Bước 2 — LISTAGG analytic

```sql
SELECT
    order_id,
    customer_id,
    status,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id)
        OVER (PARTITION BY customer_id) AS all_customer_statuses
FROM lab_listagg_orders
ORDER BY customer_id, order_id;
```

Giải thích vì sao số hàng đầu ra bằng số hàng bảng nguồn, trong khi chuỗi tổng hợp của một khách hàng xuất hiện lặp trên các hàng cùng partition.

### Bước 3 — Distinct cho phiên bản phù hợp

Trên Oracle 19c+:

```sql
SELECT customer_id,
       LISTAGG(DISTINCT product_name, ', ')
           WITHIN GROUP (ORDER BY product_name) AS products
FROM lab_listagg_orders
GROUP BY customer_id;
```

Trên phiên bản cũ:

```sql
SELECT customer_id,
       LISTAGG(product_name, ', ')
           WITHIN GROUP (ORDER BY product_name) AS products
FROM (
    SELECT DISTINCT customer_id, product_name
    FROM lab_listagg_orders
)
GROUP BY customer_id;
```

So sánh kết quả khách hàng 102. Nêu vì sao subquery phải giữ `CUSTOMER_ID`.

### Bước 4 — Tạo dữ liệu đủ dài để thử overflow

Không cần chèn hàng thật:

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT LISTAGG(item, ', ')
       WITHIN GROUP (ORDER BY id) AS item_list
FROM generated_rows;
```

Trên STANDARD, câu lệnh có thể báo ORA-01489. Ghi nhận version và `MAX_STRING_SIZE` trước khi kết luận.

### Bước 5 — Thử ON OVERFLOW TRUNCATE trên 12.2+

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT
    LISTAGG(
        item,
        ', ' ON OVERFLOW TRUNCATE '...[cut]' WITH COUNT
    ) WITHIN GROUP (ORDER BY id) AS truncated_list
FROM generated_rows;
```

Quan sát indicator và count ở cuối. Thử `WITHOUT COUNT` rồi giải thích vì sao danh sách có thể giữ được thêm một số measure.

### Bước 6 — Tính ước lượng byte

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT
    COUNT(item) AS measure_count,
    SUM(LENGTHB(item)) AS measure_bytes,
    (COUNT(item) - 1) * LENGTHB(', ') AS delimiter_bytes,
    SUM(LENGTHB(item))
      + GREATEST(COUNT(item) - 1, 0) * LENGTHB(', ')
        AS estimated_bytes
FROM generated_rows;
```

So sánh ước lượng với giới hạn output. Nếu thay X bằng chuỗi tiếng Việt có dấu, đo lại LENGTHB để thấy số byte có thể tăng.

### Bước 7 — Chọn kiểu trả kết quả

Một API cần danh sách 20.000 sản phẩm và phải giữ mọi phần tử. Hãy chọn giữa LISTAGG, LISTAGG TRUNCATE, JSON array, CLOB và nhiều hàng. Nêu rõ:

- Consumer có cần parse từng phần tử không?
- Có cần giữ kiểu/ranh giới dữ liệu không?
- Giới hạn độ dài nào áp dụng?
- Server version nào phải hỗ trợ?
- Nếu trả CLOB, client sẽ đọc stream ra sao?

## 17. Nguyên tắc thực hành tốt

1. **Luôn chỉ định ORDER BY trong WITHIN GROUP** và thêm tie-breaker duy nhất khi thứ tự cần tái lập.
2. **Hiểu NULL và DISTINCT:** LISTAGG bỏ measure NULL; mặc định giữ duplicates; DISTINCT trực tiếp chỉ có từ 19c.
3. **Biết phiên bản server:** ON OVERFLOW TRUNCATE từ 12.2; LISTAGG DISTINCT từ 19c.
4. **Đo byte, không chỉ đếm ký tự:** LENGTHB và character set quan trọng đối với giới hạn VARCHAR2.
5. **Không dùng TRUNCATE khi dữ liệu phải đầy đủ.** Indicator chỉ báo cắt, không khôi phục phần tử bị bỏ.
6. **Không tăng MAX_STRING_SIZE tùy tiện.** EXTENDED vẫn có giới hạn và là thay đổi cấu hình database.
7. **Chọn CLOB/JSON/multiple rows cho danh sách lớn.** Đừng cố ép mọi tập dữ liệu thành một VARCHAR2.
8. **Kiểm tra join trước khi dùng DISTINCT.** DISTINCT có thể che việc join nhân bản dữ liệu sai.
9. **Định nghĩa delimiter và escaping.** LISTAGG không tự tạo định dạng round-trip an toàn.
10. **Đo execution plan và workload.** Group lớn, sort và distinct có thể tốn CPU/PGA/TEMP.

## 18. Câu hỏi tự kiểm tra

1. LISTAGG khác `CONCAT` ở điểm nào về số lượng hàng đầu vào?
2. Nếu bỏ delimiter, Oracle dùng giá trị gì? Nếu measure là NULL thì phần tử có được nối không?
3. Vì sao cần ORDER BY bên trong WITHIN GROUP dù câu SQL đã có ORDER BY ở cuối?
4. Khi ORDER BY không duy nhất, vì sao chuỗi kết quả có thể không tái lập hoàn toàn?
5. Oracle 11gR2/12.1 có dùng được ON OVERFLOW TRUNCATE không?
6. ON OVERFLOW TRUNCATE được bổ sung từ phiên bản nào? LISTAGG DISTINCT có từ phiên bản nào?
7. Với STANDARD và EXTENDED, giới hạn LISTAGG VARCHAR2 lần lượt là bao nhiêu byte?
8. Vì sao 2000 ký tự tiếng Việt có thể vượt một giới hạn byte dù số ký tự nhỏ hơn 4000?
9. WITH COUNT khác WITHOUT COUNT như thế nào? Vì sao WITH COUNT có thể cắt sớm hơn?
10. Khi nào nên dùng XMLAGG/CLOB thay cho LISTAGG?
11. Vì sao chuỗi LISTAGG chứa delimiter trong dữ liệu gốc không nhất thiết parse ngược được?
12. Nếu một JOIN làm một sản phẩm xuất hiện ba lần, có nên thêm DISTINCT ngay không? Cần kiểm tra gì trước?

## 19. Mô hình ghi nhớ

```text
Nhiều hàng
   │
   ▼
LISTAGG(measure, delimiter)
   │
   ├── Bỏ qua measure NULL
   ├── ALL mặc định: giữ giá trị trùng
   ├── DISTINCT: Oracle 19c+
   └── WITHIN GROUP (ORDER BY ...)
          quyết định thứ tự phần tử
   │
   ▼
VARCHAR2 / RAW có giới hạn byte
   │
   ├── Mặc định / ON OVERFLOW ERROR
   │       → ORA-01489 nếu quá giới hạn
   │
   └── ON OVERFLOW TRUNCATE (Oracle 12.2+)
           → indicator
           → WITH COUNT / WITHOUT COUNT

Nếu cần đầy đủ và dài:
   → XMLAGG / CLOB
   → JSON array
   → trả nhiều hàng / phân trang
```

**Điểm cần nhớ:** LISTAGG là công cụ tổng hợp chuỗi tiện lợi, nhưng đầu ra vẫn là kiểu có giới hạn. Hãy kiểm soát thứ tự, NULL, duplicate, phiên bản server và số byte trước khi dùng trong báo cáo hoặc API. Khi có thể mất phần tử, dùng `ON OVERFLOW TRUNCATE` với indicator rõ ràng; khi phải giữ đầy đủ danh sách dài, chuyển sang CLOB, JSON hoặc trả nhiều hàng thay vì che lỗi bằng cách cắt dữ liệu.
