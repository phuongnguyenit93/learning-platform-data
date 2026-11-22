# Kiểu kết quả chung của các nhánh CASE

Khi viết `CASE` trong SQL, một câu lệnh có thể trả về kết quả khác nhau theo điều kiện: trạng thái đơn hàng là chữ, tiền thanh toán là số, ngày hết hạn là ngày, hoặc tình trạng xác minh là `TRUE`/`FALSE`. Tuy nhiên, với nhiều hệ quản trị như **PostgreSQL**, tất cả các nhánh `THEN` và `ELSE` của **một biểu thức `CASE`** phải được thống nhất thành **một kiểu dữ liệu kết quả chung** trước khi truy vấn được thực thi.

Điểm này dễ bị bỏ qua vì ta thường đọc `CASE` theo suy nghĩ: “nếu điều kiện đúng thì lấy nhánh đó, các nhánh còn lại không cần quan tâm”. Việc lựa chọn **giá trị** theo điều kiện và việc xác định **kiểu dữ liệu** cho cả biểu thức là hai công việc khác nhau.

Bài học tập trung vào **Database SQL → Rẽ nhánh trong SQL → Kiểu kết quả chung của các nhánh CASE**: tại sao một nhánh trả số và nhánh còn lại trả chuỗi có thể gây lỗi; `NULL` ảnh hưởng đến suy luận kiểu ra sao; khi nào SQL tự chuyển kiểu và khi nào phải dùng `CAST`; làm sao thiết kế các cột kết quả ổn định trong truy vấn và API. Ví dụ thực hành chính sử dụng **PostgreSQL**, kèm những điểm khác biệt cần lưu ý ở các DBMS khác.

## 1. CASE là một biểu thức có kiểu dữ liệu

Hai dạng `CASE` phổ biến:

**Searched CASE**: kiểm tra nhiều điều kiện riêng biệt.

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE result_default
END
```

**Simple CASE**: so sánh một biểu thức với các giá trị đối chiếu.

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE result_default
END
```

Cả hai đều tạo ra **một giá trị kết quả** tại vị trí chúng xuất hiện. Chẳng hạn:

```sql
SELECT
    120 AS amount,
    CASE
        WHEN 120 >= 100 THEN 'Đơn lớn'
        ELSE 'Đơn nhỏ'
    END AS amount_group;
```

Kết quả của `CASE` là chuỗi `'Đơn lớn'`. Điều quan trọng hơn: dù nhánh nào được chọn, biểu thức `CASE` ở đây là **biểu thức trả văn bản** theo quy tắc suy luận kiểu của DBMS.

Hãy phân biệt ba loại biểu thức:

| Vị trí | Nhiệm vụ | Yêu cầu kiểu dữ liệu |
| --- | --- | --- |
| `WHEN condition` trong searched CASE | Quyết định chọn nhánh | Điều kiện phải là biểu thức logic hợp lệ; PostgreSQL cần kiểu `BOOLEAN` |
| `CASE expression WHEN value` trong simple CASE | Xác định nhánh khớp | Các giá trị cần so sánh được theo quy tắc chuyển kiểu và toán tử của DBMS |
| `THEN result` và `ELSE result` | Cung cấp giá trị cuối cùng | Các kết quả phải có một kiểu dữ liệu chung có thể xác định theo DBMS |

**Kiểu dữ liệu của điều kiện không quyết định kiểu dữ liệu của kết quả.** Ví dụ, `WHEN amount > 0` là điều kiện boolean nhưng `THEN 'Có tiền'` là văn bản.

## 2. Tại sao phải có kiểu kết quả chung?

Một cột trong kết quả SQL thường được mô tả bằng metadata gồm **tên cột và kiểu dữ liệu**. Ứng dụng, driver JDBC/ODBC, công cụ báo cáo hoặc truy vấn ngoài cần biết cách đọc cột đó.

Xét biểu thức:

```sql
SELECT CASE
    WHEN TRUE THEN 10
    ELSE 20
END AS chosen_number;
```

Hai nhánh đều trả số nguyên nên kiểu kết quả dễ xác định.

Nhưng nếu viết:

```sql
SELECT CASE
    WHEN TRUE THEN 10
    ELSE 'Không có dữ liệu'
END AS chosen_value;
```

DBMS phải quyết định liệu toàn bộ cột `chosen_value` là **số** hay **chữ**. Việc nhánh đầu tiên đang đúng không đồng nghĩa nhánh còn lại được phép mang kiểu dữ liệu tùy ý.

Trong PostgreSQL, `'Không có dữ liệu'` ban đầu là literal chuỗi chưa được gắn kiểu cụ thể (`unknown`). Khi kết hợp với nhánh số nguyên, hệ quản trị có thể cố ép literal đó sang kiểu số và báo lỗi **không chuyển được chuỗi sang integer**. Nếu ép chuỗi đó rõ ràng thành `TEXT`, các nhánh `INTEGER` và `TEXT` lại có thể gây lỗi vì không tìm được kiểu chung theo quy tắc của PostgreSQL.

Một kết quả `CASE` khác loại không mặc nhiên được hiểu là “trả kiểu gì cũng được tùy từng hàng”, đặc biệt trong hệ quản trị có hệ thống kiểu tĩnh như PostgreSQL.

### Giá trị được chọn khác với kiểu được phân giải

Hãy hình dung hai giai đoạn:

```text
Câu SQL chứa CASE
         │
         ▼
Phân tích và xác định kiểu
    ├─ Kiểm tra điều kiện WHEN
    ├─ Xét kiểu của các kết quả THEN và ELSE
    ├─ Tìm kiểu kết quả chung hợp lệ
    └─ Áp dụng chuyển kiểu cần thiết hoặc báo lỗi
         │
         ▼
Thực thi trên từng hàng
    ├─ Tìm điều kiện WHEN được chọn
    └─ Trả giá trị thuộc kiểu kết quả đã xác định
```

Không nên trông chờ điều kiện `WHEN` luôn đúng để bỏ qua một nhánh `THEN`/`ELSE` có kiểu không tương thích.

## 3. Cách PostgreSQL suy luận kiểu cho CASE

PostgreSQL có cơ chế *type resolution* cho `CASE`, `UNION` và một số cấu trúc khác. Với `CASE`, hệ quản trị xét toàn bộ biểu thức kết quả, bao gồm `THEN` và `ELSE`.

Một cách hiểu thực hành:

1. Nếu các biểu thức kết quả cùng một kiểu không phải `unknown`, kiểu đó thường được giữ.
2. Các literal chuỗi chưa xác định kiểu và `NULL` chưa ép kiểu có thể tham gia như kiểu `unknown`; chúng **không luôn buộc** kết quả thành `TEXT`.
3. Nếu mọi kết quả đều thuộc `unknown`, PostgreSQL thường chọn `TEXT`.
4. Khi có nhiều kiểu khác nhau, PostgreSQL áp dụng **nhóm kiểu dữ liệu**, **kiểu ưu tiên** và khả năng **chuyển kiểu ngầm** để chọn một kiểu ứng viên. Nếu không có kiểu phù hợp, truy vấn bị từ chối.
5. Ngay cả khi chọn được kiểu chung, một literal vẫn có thể **không chuyển được** sang kiểu đó, dẫn đến lỗi.
6. Một số kiểu đặc biệt như domain, array, enum hay kiểu do người dùng định nghĩa có quy tắc riêng; không nên suy luận chỉ từ tên hiển thị của kiểu.

Trong thuật toán phân giải kiểu của PostgreSQL, biểu thức `ELSE` được xem trước các biểu thức `THEN` cho mục đích xét ứng viên kiểu. Đây là chi tiết dành cho các trường hợp chuyển kiểu phức tạp; người mới học nên ưu tiên **viết các nhánh cùng kiểu một cách rõ ràng** hơn là dựa vào thứ tự để cố đạt một kiểu mong muốn.

### Quan sát kiểu với pg_typeof

PostgreSQL cung cấp hàm `pg_typeof(expression)` để xem kiểu được xác định cho một biểu thức:

```sql
SELECT
    pg_typeof(
        CASE WHEN TRUE THEN 10 ELSE 20 END
    ) AS integer_case_type,

    pg_typeof(
        CASE WHEN TRUE THEN 10 ELSE 20.5 END
    ) AS decimal_case_type,

    pg_typeof(
        CASE WHEN TRUE THEN 'A' ELSE 'B' END
    ) AS text_case_type;
```

Trong PostgreSQL, các kiểu ở ví dụ trên lần lượt là `integer`, `numeric` và `text`.

`pg_typeof` là hàm **riêng của PostgreSQL**. Các DBMS khác có công cụ kiểm tra metadata hoặc cơ chế suy luận kiểu khác; không mang nguyên cú pháp này sang MySQL hay SQL Server.

## 4. Bảng thực hành cho các tình huống CASE

Để làm việc trên cùng một bộ dữ liệu, hãy mở kết nối **PostgreSQL thực hành** và tạo bảng tạm:

```sql
CREATE TEMP TABLE case_result_lab (
    order_id        INTEGER PRIMARY KEY,
    order_status    TEXT,
    quantity        INTEGER,
    amount          NUMERIC(12, 2),
    discount_amount NUMERIC(12, 2),
    paid_at         DATE
);

INSERT INTO case_result_lab (
    order_id, order_status, quantity,
    amount, discount_amount, paid_at
)
VALUES
    (1, 'NEW',       2,   50.00, NULL,  NULL),
    (2, 'PAID',      5,  120.00, 10.00, DATE '2026-04-01'),
    (3, 'CANCELLED', 0,    0.00, NULL,  NULL),
    (4, 'REFUNDED',  1,   50.00, 50.00, DATE '2026-04-03'),
    (5, NULL,       3,     NULL, NULL,  NULL);

SELECT *
FROM case_result_lab
ORDER BY order_id;
```

Bảng `case_result_lab` là **bảng tạm**, chỉ tồn tại trong phiên kết nối. Lệnh tạo bảng nên chạy một lần trong phiên; nếu đã có cùng tên, hãy mở phiên mới hoặc chọn tên bảng thực hành khác.

| `order_id` | `order_status` | `quantity` | `amount` | `discount_amount` | `paid_at` |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | NEW | 2 | 50.00 | `NULL` | `NULL` |
| 2 | PAID | 5 | 120.00 | 10.00 | 2026-04-01 |
| 3 | CANCELLED | 0 | 0.00 | `NULL` | `NULL` |
| 4 | REFUNDED | 1 | 50.00 | 50.00 | 2026-04-03 |
| 5 | `NULL` | 3 | `NULL` | `NULL` | `NULL` |

Các phần tiếp theo sử dụng bảng này để minh họa những cách tạo kiểu chung ổn định.

## 5. Các nhánh đều trả văn bản

Một trường hợp phổ biến là ánh xạ mã trạng thái thành nhãn hiển thị:

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'PAID' THEN 'Đã thanh toán'
        WHEN order_status = 'NEW' THEN 'Đơn mới'
        WHEN order_status = 'CANCELLED' THEN 'Đã hủy'
        WHEN order_status = 'REFUNDED' THEN 'Đã hoàn tiền'
        ELSE 'Chưa xác định'
    END AS status_label
FROM case_result_lab
ORDER BY order_id;
```

Các giá trị kết quả đều là literal chuỗi, nên PostgreSQL chọn kiểu kết quả `TEXT`.

| Đơn | `status_label` |
| ---: | --- |
| 1 | Đơn mới |
| 2 | Đã thanh toán |
| 3 | Đã hủy |
| 4 | Đã hoàn tiền |
| 5 | Chưa xác định |

Dù `order_status` gốc mang `NULL`, biểu thức có `ELSE 'Chưa xác định'` nên trả một chuỗi. Đây là **quy tắc hiển thị**: dữ liệu gốc vẫn là `NULL`.

Nếu nhãn cần giữ nguyên trạng thái thiếu để xử lý về sau, bỏ `ELSE` hoặc dùng `ELSE NULL::TEXT`; khi đó các hàng không khớp sẽ trả `NULL`.

### Literal chuỗi chưa xác định kiểu không phải luôn là TEXT

Trong PostgreSQL, literal viết `'42'` chưa có cast trong một số ngữ cảnh ban đầu mang kiểu đặc biệt `unknown`. Nếu đặt cạnh kết quả số, hệ quản trị có thể suy luận nó phải là số:

```sql
SELECT
    CASE WHEN TRUE THEN 42 ELSE '0' END AS numeric_result,
    pg_typeof(
        CASE WHEN TRUE THEN 42 ELSE '0' END
    ) AS numeric_result_type;
```

Kết quả kiểu là `integer`: literal `'0'` có thể được chuyển thành số nguyên.

Nhưng điều này **không** chứng minh mọi chuỗi có thể ghép với số. Chỉ chuỗi biểu diễn một giá trị hợp lệ theo kiểu đích mới chuyển được.

## 6. Trộn số nguyên với số thập phân

Ví dụ:

```sql
SELECT
    CASE
        WHEN TRUE THEN 7
        ELSE 2.75
    END AS result_value,
    pg_typeof(
        CASE WHEN TRUE THEN 7 ELSE 2.75 END
    ) AS result_type;
```

PostgreSQL phân giải `7` (integer) với `2.75` (numeric literal) thành kiểu `NUMERIC`. Giá trị ở ví dụ này là `7`, nhưng **kiểu biểu thức** là `NUMERIC`.

Với bảng thực hành:

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'PAID' THEN amount
        ELSE 0
    END AS paid_amount,
    pg_typeof(
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END
    ) AS result_type
FROM case_result_lab
ORDER BY order_id;
```

Cột `amount` là `NUMERIC(12,2)`, còn `0` là literal số nguyên. PostgreSQL tìm được kiểu chung `numeric`. Kết quả `paid_amount` lần lượt là `0`, `120.00`, `0`, `0`, `0` theo các hàng 1..5.

Ở đây `ELSE 0` có nghĩa “các đơn chưa ở trạng thái PAID được tính giá trị 0 trong báo cáo”. Đó là lựa chọn nghiệp vụ, không phải điều `CASE` bắt buộc. Nếu phải phân biệt “không áp dụng” với 0, `ELSE NULL::NUMERIC` sẽ thích hợp hơn.

### INTEGER và BIGINT

Các kiểu nguyên có phạm vi khác nhau. Nếu một nhánh có giá trị `BIGINT` và nhánh khác là `INTEGER`, PostgreSQL có thể suy luận kết quả `BIGINT`:

```sql
SELECT pg_typeof(
    CASE
        WHEN TRUE THEN 1::INTEGER
        ELSE 3000000000::BIGINT
    END
) AS common_integer_type;
```

Kết quả là `bigint`. Việc chọn kiểu rộng hơn giúp biểu diễn các giá trị nguyên lớn trong phạm vi `BIGINT`, nhưng không có nghĩa phép toán trung gian trước `CASE` sẽ tự động tránh tràn.

Ví dụ, nếu `THEN` chứa phép cộng hai `INTEGER` đã vượt phạm vi, việc nhánh `ELSE` có `BIGINT` không bảo đảm phép cộng bên trong nhánh đó được thực hiện bằng `BIGINT`. Khi cần phép tính rộng, ép kiểu **trước khi tính**:

```sql
CASE
    WHEN some_condition
        THEN integer_column::BIGINT + 1::BIGINT
    ELSE 0::BIGINT
END
```

Đoạn trên minh họa cách tổ chức biểu thức; `some_condition` và `integer_column` là tên giả định trong truy vấn thực tế.

### NUMERIC và DOUBLE PRECISION

Khi trộn số thập phân chính xác với số dấu phẩy động, kiểu chung có thể trở thành kiểu gần đúng theo quy tắc chuyển kiểu của DBMS. Trên PostgreSQL:

```sql
SELECT pg_typeof(
    CASE
        WHEN TRUE THEN 1.25::NUMERIC
        ELSE 2.5::DOUBLE PRECISION
    END
) AS mixed_numeric_type;
```

Trường hợp này cho kiểu `double precision`. Điều đó quan trọng nếu biểu thức dùng để tính tiền: **một nhánh gần đúng có thể khiến cả biểu thức mang kiểu gần đúng**. Để giữ kiểu decimal chính xác cho nghiệp vụ, cần thiết kế các nhánh `NUMERIC` nhất quán thay vì dùng `FLOAT` không chủ đích.

## 7. Vì sao nhánh số và nhánh chữ thường gây lỗi?

Xét biểu thức sau:

```sql
-- PostgreSQL: ví dụ lỗi chuyển literal chuỗi sang số nguyên
SELECT CASE
    WHEN TRUE THEN 100
    ELSE 'Không áp dụng'
END AS value_or_message;
```

Lỗi không xuất phát từ việc `TRUE` hay `FALSE` được chọn ở một hàng cụ thể. Trong quá trình tìm kiểu kết quả chung, PostgreSQL thấy nhánh số nguyên và literal chuỗi chưa có kiểu; khi cố chuyển literal chữ thành integer, nó không chuyển được.

Nếu ép chuỗi rõ ràng thành `TEXT`:

```sql
-- PostgreSQL: ví dụ các kiểu không có cách thống nhất trực tiếp
SELECT CASE
    WHEN TRUE THEN 100::INTEGER
    ELSE 'Không áp dụng'::TEXT
END;
```

truy vấn vẫn không hợp lệ vì kiểu số nguyên và văn bản không được PostgreSQL ngầm hợp nhất thành một kiểu kết quả cho `CASE` theo cách này.

### Cách 1: Đổi tất cả nhánh sang TEXT khi kết quả là nhãn hiển thị

```sql
SELECT order_id,
       CASE
           WHEN amount IS NULL THEN 'Chưa có tiền'
           ELSE amount::TEXT
       END AS amount_display
FROM case_result_lab
ORDER BY order_id;
```

Hai nhánh đều trả `TEXT`. Cột `amount_display` là **văn bản để hiển thị**, không còn là số dùng để `SUM` hay `AVG` trực tiếp.

Để tiếp tục tính toán, nên giữ cột số riêng và chỉ tạo nhãn ở tầng báo cáo hoặc ứng dụng:

```sql
SELECT order_id,
       amount AS amount_numeric,
       CASE
           WHEN amount IS NULL THEN 'Chưa có tiền'
           ELSE amount::TEXT
       END AS amount_display
FROM case_result_lab
ORDER BY order_id;
```

Cách này giúp ứng dụng không phải phân tích ngược chuỗi như `'Chưa có tiền'` thành dữ liệu số.

### Cách 2: Giữ tất cả nhánh là NUMERIC nếu kết quả cần tính toán

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN amount
           WHEN order_status = 'REFUNDED' THEN -amount
           ELSE 0::NUMERIC
       END AS signed_amount
FROM case_result_lab
ORDER BY order_id;
```

Mọi kết quả đều là kiểu số hoặc chuyển được sang kiểu số. Giá trị của `signed_amount` ở dữ liệu mẫu lần lượt là `0`, `120.00`, `0`, `-50.00`, `0`.

Nếu trạng thái không xác định phải tạo **giá trị thiếu**, dùng `ELSE NULL::NUMERIC` thay vì gán 0. Việc chọn giữa `0` và `NULL` phải phản ánh ý nghĩa nghiệp vụ.

### Cách 3: Tách nhãn trạng thái khỏi số liệu

Trong một API, thường tốt hơn khi trả:

```sql
SELECT
    order_id,
    CASE
        WHEN amount IS NULL THEN 'missing'
        ELSE 'known'
    END AS amount_status,
    amount AS amount_value
FROM case_result_lab
ORDER BY order_id;
```

`amount_status` là văn bản; `amount_value` vẫn là số. Một cột `CASE` duy nhất không cần gánh đồng thời hai loại dữ liệu không tương thích.

## 8. NULL trong CASE: chưa có kiểu và đã có kiểu

`NULL` không tự mang ý nghĩa số, chữ hay ngày nếu chưa được gắn kiểu trong ngữ cảnh. Vì vậy, một `NULL` không định kiểu có thể thích nghi với kiểu chung của nhánh còn lại.

### Có ELSE NULL hoặc bỏ ELSE

```sql
SELECT
    pg_typeof(
        CASE WHEN TRUE THEN 100 ELSE NULL END
    ) AS inferred_number_type,

    pg_typeof(
        CASE WHEN TRUE THEN DATE '2026-04-01' ELSE NULL END
    ) AS inferred_date_type;
```

Kết quả lần lượt là `integer` và `date`.

Khi **bỏ `ELSE`**, ngữ nghĩa của `CASE` là trả `NULL` nếu không có điều kiện `WHEN` nào khớp:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN amount
       END AS amount_only_when_paid
FROM case_result_lab
ORDER BY order_id;
```

Cột này có kiểu `numeric` do nhánh `THEN amount`. Các đơn không ở trạng thái `PAID` cho `NULL`; riêng đơn 2 trả `120.00`.

### Mọi nhánh là NULL

```sql
SELECT pg_typeof(
    CASE WHEN TRUE THEN NULL ELSE NULL END
) AS all_null_type;
```

Trong PostgreSQL, trường hợp mọi kết quả đều chưa xác định kiểu sẽ được phân giải thành `text`. Đây là ví dụ dễ nhầm: không phải bất cứ biểu thức trả `NULL` nào cũng có kiểu được mong muốn tự động theo ý định ứng dụng.

Nếu cột cần là `NUMERIC`:

```sql
SELECT
    CASE
        WHEN TRUE THEN NULL::NUMERIC
        ELSE NULL::NUMERIC
    END AS missing_numeric;
```

Nếu cột cần là `DATE`:

```sql
SELECT
    CASE
        WHEN TRUE THEN CAST(NULL AS DATE)
        ELSE CAST(NULL AS DATE)
    END AS missing_date;
```

Hai cách đặt kiểu rõ ràng có ích khi tạo view, xuất báo cáo và trả metadata cột ổn định cho ứng dụng.

### NULL có kiểu vẫn có thể gây xung đột

Không nên cho rằng viết `NULL` ở bất kỳ nhánh nào cũng an toàn:

```sql
-- PostgreSQL: kiểu NUMERIC và DATE không có kiểu CASE chung phù hợp
SELECT CASE
    WHEN TRUE THEN NULL::NUMERIC
    ELSE DATE '2026-04-01'
END;
```

Dù giá trị của nhánh đầu vẫn là `NULL`, biểu thức đó **đã có kiểu NUMERIC**. Nó tham gia vào quá trình suy luận kiểu giống các biểu thức có giá trị khác `NULL`.

## 9. CASE cho giá trị DATE, TIMESTAMP và BOOLEAN

### 9.1. Ngày tháng: không ghép ngày với nhãn chữ tùy ý

Một yêu cầu như “nếu đơn đã thanh toán thì lấy ngày thanh toán, nếu không thì chưa có ngày” có thể viết:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN paid_at
           ELSE NULL::DATE
       END AS confirmed_payment_date
FROM case_result_lab
ORDER BY order_id;
```

Cột kết quả mang kiểu `DATE`. Hàng 2 trả `2026-04-01`; các hàng khác trả `NULL`.

Không nên viết `ELSE 'Chưa thanh toán'` nếu kết quả cần là ngày: PostgreSQL có thể cố ép chuỗi đó sang `DATE` rồi báo lỗi. Nếu giao diện cần hiển thị câu chữ, tạo một cột `payment_date_label` kiểu văn bản riêng:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' AND paid_at IS NOT NULL
               THEN paid_at::TEXT
           ELSE 'Chưa có ngày thanh toán'
       END AS payment_date_label
FROM case_result_lab
ORDER BY order_id;
```

Với dữ liệu thực tế, giá trị `DATE` nên giữ ở dạng ngày trong lớp dữ liệu; định dạng chuỗi ngày dùng cho người dùng thường nên do ứng dụng kiểm soát theo múi giờ và định dạng hiển thị (đặc biệt khi chuyển sang `TIMESTAMP`).

### 9.2. BOOLEAN: cùng trả giá trị logic

Nếu muốn biết đơn có ở trạng thái đã thanh toán hay không:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN TRUE
           WHEN order_status IS NULL THEN NULL::BOOLEAN
           ELSE FALSE
       END AS is_paid
FROM case_result_lab
ORDER BY order_id;
```

Kiểu kết quả là `BOOLEAN`. Ở hàng 5, trạng thái thanh toán thiếu nên kết quả `is_paid` là `NULL`, không bị gộp với `FALSE`.

Nếu một nhánh trả `TRUE` và nhánh khác trả số `0`, bạn đang trộn **boolean** với **integer**. PostgreSQL không tự cho phép điều đó như một kiểu chung thông dụng. Để trả cờ số `0/1`, mọi nhánh nên là `INTEGER`:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN 1
           WHEN order_status IS NULL THEN NULL::INTEGER
           ELSE 0
       END AS paid_flag
FROM case_result_lab
ORDER BY order_id;
```

Khi truyền dữ liệu qua API, cần thống nhất rõ cờ là boolean, integer hay chuỗi, tránh mỗi nhánh dùng một cách biểu diễn.

## 10. Kiểu chung và độ rộng/scale của NUMERIC là hai vấn đề khác nhau

Một cột khai báo `NUMERIC(12,2)` có:

- **Precision** 12: tối đa 12 chữ số thập phân có ý nghĩa trong khuôn dạng thông dụng.
- **Scale** 2: hai chữ số sau dấu thập phân.

Khi đưa cột đó vào biểu thức `CASE`, PostgreSQL thường phân giải **kiểu cơ sở** là `numeric`. Không nên mặc định rằng toàn bộ biểu thức mới luôn tiếp tục mang chính xác ràng buộc độ rộng và scale như cột `NUMERIC(12,2)` ban đầu.

Ví dụ:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN amount
           ELSE 1.2345::NUMERIC
       END AS result_amount
FROM case_result_lab
ORDER BY order_id;
```

Kết quả `result_amount` có kiểu `NUMERIC`, nhưng các giá trị có thể hiển thị số chữ số thập phân khác nhau tùy nhánh và biểu thức. Nếu một **cột kết quả** cần được ép về hai chữ số, hãy áp dụng `CAST` lên toàn bộ `CASE`:

```sql
SELECT order_id,
       CAST(
           CASE
               WHEN order_status = 'PAID' THEN amount
               ELSE 1.2345::NUMERIC
           END AS NUMERIC(12,2)
       ) AS result_amount
FROM case_result_lab
ORDER BY order_id;
```

Như vậy, kết quả nhánh `ELSE` được đưa về `1.23` theo quy tắc làm tròn `numeric` của PostgreSQL.

**Cẩn thận:** `CAST(... AS NUMERIC(12,2))` không chỉ làm đẹp phần hiển thị. Nó có thể **làm tròn** và **báo tràn số** nếu giá trị sau chuyển đổi vượt phạm vi kiểu đích. Cần chọn `precision` và `scale` theo miền dữ liệu hợp lệ, không lấy một cặp số tùy ý chỉ để định dạng.

Nếu chỉ muốn hiển thị hai chữ số trên giao diện mà vẫn giữ độ chính xác tính toán, có thể cần tách **giá trị số** khỏi **định dạng hiển thị**.

## 11. Chuyển kiểu ngầm và CAST tường minh

**Implicit conversion** (chuyển kiểu ngầm) là việc DBMS tự thêm bước chuyển đổi khi ngữ cảnh cho phép. **Explicit conversion** (chuyển kiểu tường minh) do người viết SQL chỉ rõ, ví dụ:

```sql
CAST(expression AS target_type)
```

PostgreSQL còn hỗ trợ cú pháp rút gọn:

```sql
expression::target_type
```

Hai cú pháp có thể dùng để giữ kiểu đầu ra rõ ràng:

```sql
SELECT
    CASE
        WHEN TRUE THEN CAST(1 AS NUMERIC)
        ELSE CAST(2 AS NUMERIC)
    END AS numeric_value,

    CASE
        WHEN TRUE THEN CAST(1 AS TEXT)
        ELSE CAST(2 AS TEXT)
    END AS text_value;
```

Kết quả nhìn có thể cùng là `1`, nhưng cột đầu có kiểu số, cột sau có kiểu văn bản. Sự khác biệt ảnh hưởng đến phép cộng, phép so sánh, sắp xếp, driver và cách hiển thị.

### CAST từng nhánh hay CAST toàn CASE?

Hai cách thường khác về ý nghĩa:

**Ép kiểu trước khi chọn nhánh:**

```sql
CASE
    WHEN condition THEN expression_a::NUMERIC
    ELSE expression_b::NUMERIC
END
```

**Chọn kết quả chung rồi ép kiểu sau:**

```sql
CAST(
    CASE
        WHEN condition THEN expression_a
        ELSE expression_b
    END
    AS NUMERIC
)
```

Cách thứ hai **chỉ hoạt động nếu bản thân `CASE` đã phân giải được một kiểu chung**. Nếu `expression_a` là `TEXT` và `expression_b` là `INTEGER` không tương thích theo PostgreSQL, đặt `CAST(... AS NUMERIC)` bao ngoài không tự sửa được lỗi xác định kiểu xảy ra **bên trong `CASE`**.

Với tình huống trộn dữ liệu chuỗi số và số thật, hãy chuyển các nhánh về một kiểu ngay tại đầu ra:

```sql
SELECT CASE
    WHEN TRUE THEN '125.50'::NUMERIC
    ELSE 0::NUMERIC
END AS amount;
```

Chuyển một chuỗi không biểu diễn số hợp lệ có thể báo lỗi, dù có dùng `CAST` rõ ràng. Vì thế cần xác thực dữ liệu nguồn hoặc thiết kế cột theo đúng loại giá trị.

### CASE không bảo đảm che mọi lỗi biểu thức ở nhánh không chọn

Thông thường, `CASE` không cần đánh giá biểu thức kết quả ở nhánh không được chọn cho mỗi hàng. Tuy nhiên, quy tắc đó không có nghĩa mọi lỗi bị che: PostgreSQL có thể xử lý một số hằng và biểu thức tại thời điểm lập kế hoạch, trước lúc chọn nhánh trên từng hàng. Một phép chia hằng cho 0 hoặc ép literal không hợp lệ ở nhánh khác vẫn có thể gây lỗi tùy cấu trúc truy vấn và bước xử lý.

Khi lập trình, hãy đảm bảo **mọi nhánh hợp lệ về cú pháp và kiểu**; với phép toán nhạy cảm, bảo vệ điều kiện ngay trong biểu thức phù hợp.

## 12. Kiểu trả về ổn định cho truy vấn dùng trong ứng dụng

Giả sử một ứng dụng đọc báo cáo `net_amount` theo kiểu số decimal. Một biểu thức như:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID'
               THEN amount - COALESCE(discount_amount, 0)
           ELSE 'N/A'
       END AS net_amount
FROM case_result_lab;
```

trộn kết quả số với literal nhãn `'N/A'`. Trong PostgreSQL, nó có thể không phân giải/không chuyển được kiểu và báo lỗi. Ngoài ra, nếu cố biến mọi kết quả thành chuỗi, ứng dụng không còn nhận cột `net_amount` theo kiểu numeric.

Thiết kế kết quả rõ hơn:

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' AND amount IS NOT NULL
             THEN amount - COALESCE(discount_amount, 0)
           ELSE NULL::NUMERIC
       END AS net_amount,
       CASE
           WHEN order_status = 'PAID' AND amount IS NOT NULL
             THEN 'calculated'
           WHEN amount IS NULL THEN 'missing_amount'
           ELSE 'not_applicable'
       END AS net_amount_status
FROM case_result_lab
ORDER BY order_id;
```

Hai cột trả hai ý nghĩa khác nhau:

- `net_amount`: kiểu `NUMERIC`, chứa số hợp lệ hoặc `NULL`.
- `net_amount_status`: kiểu `TEXT`, giải thích lý do có/không có kết quả.

Ở đơn 2, `net_amount = 110.00` và `status = 'calculated'`. Ở đơn 5, `net_amount` là `NULL` với trạng thái `'missing_amount'`. Ở đơn 1, 3, 4, số `net_amount` là `NULL` và trạng thái `'not_applicable'`.

Cách này giúp tránh biến một cột thành hỗn hợp “lúc số, lúc chữ”; rất có ích khi ánh xạ sang Java `BigDecimal`, DTO, API JSON, bảng tính hoặc công cụ BI.

### CASE trong ORDER BY cũng cần kiểu chung

`CASE` không chỉ xuất hiện trong `SELECT` mà còn trong `ORDER BY`, `WHERE`, `GROUP BY` và các biểu thức lồng khác khi cú pháp cho phép. Đối với một `CASE` đơn lẻ, quy tắc chọn kiểu kết quả chung vẫn được áp dụng.

Ví dụ tạo thứ tự ưu tiên bằng số:

```sql
SELECT order_id, order_status
FROM case_result_lab
ORDER BY
    CASE
        WHEN order_status = 'NEW' THEN 1
        WHEN order_status = 'PAID' THEN 2
        WHEN order_status = 'REFUNDED' THEN 3
        WHEN order_status = 'CANCELLED' THEN 4
        ELSE 5
    END,
    order_id;
```

Các nhánh `THEN`/`ELSE` đều là số nguyên; biểu thức sắp xếp có kiểu thống nhất. Nếu trộn `THEN 'Đầu tiên'` với `ELSE 2`, cần quyết định **mục tiêu là thứ tự bằng số hay nhãn văn bản** trước khi sửa kiểu.

## 13. Dùng CASE với COALESCE và NULLIF

`COALESCE` và `NULLIF` cũng có thể xuất hiện trong từng nhánh; chúng ảnh hưởng tới **giá trị** và đôi khi **kiểu** của biểu thức kết quả.

### COALESCE cung cấp giá trị mặc định cùng kiểu

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID'
               THEN COALESCE(amount, 0::NUMERIC)
           ELSE NULL::NUMERIC
       END AS paid_amount
FROM case_result_lab
ORDER BY order_id;
```

`COALESCE(amount, 0::NUMERIC)` tạo kết quả numeric, nên dễ kết hợp với `ELSE NULL::NUMERIC`. Nhưng việc thay một `amount` thiếu bằng 0 là quyết định nghiệp vụ: nếu thiếu số tiền phải được báo lỗi thay vì coi là 0, đừng dùng `COALESCE` như trên.

### NULLIF giúp bảo vệ mẫu số

```sql
SELECT order_id,
       CASE
           WHEN amount IS NULL THEN NULL::NUMERIC
           ELSE amount / NULLIF(quantity, 0)
       END AS amount_per_unit
FROM case_result_lab
ORDER BY order_id;
```

Cột `amount_per_unit` có kiểu `NUMERIC`. Khi `quantity = 0`, `NULLIF(quantity,0)` trả `NULL`, làm kết quả phép chia không xác định thay vì gây lỗi chia cho 0 trong PostgreSQL. Đây là trường hợp nhánh `ELSE` có thể trả `NULL` dù biểu thức `CASE` không chọn một nhánh `THEN NULL`.

Nếu ứng dụng cần biết lý do không có kết quả (thiếu tiền, số lượng bằng 0), có thể thêm cột trạng thái riêng. `NULL` không tự mang theo nguyên nhân.

## 14. Simple CASE và searched CASE: quy tắc kiểu kết quả không đổi

Hai cách viết sau đều trả nhãn văn bản:

```sql
SELECT order_id,
       CASE order_status
           WHEN 'NEW' THEN 'new'
           WHEN 'PAID' THEN 'paid'
           ELSE 'other'
       END AS simple_status,
       CASE
           WHEN order_status = 'NEW' THEN 'new'
           WHEN order_status = 'PAID' THEN 'paid'
           ELSE 'other'
       END AS searched_status
FROM case_result_lab
ORDER BY order_id;
```

Khác biệt của hai dạng nằm ở **cách kiểm tra điều kiện**:

- `simple CASE` so sánh một biểu thức với các giá trị ở `WHEN`.
- `searched CASE` cho phép từng `WHEN` là một điều kiện tổng quát, ví dụ `amount > 100 AND order_status = 'PAID'`.

Cả hai vẫn cần một kiểu kết quả chung cho **`THEN` và `ELSE`**. Không có quy tắc “simple CASE cho một kiểu còn searched CASE cho nhiều kiểu”.

Đối với `NULL`, cần nhớ `CASE order_status WHEN NULL THEN ...` không phải cách đúng để nhận diện giá trị thiếu theo logic so sánh thông thường:

```sql
-- Không nên dùng để kiểm tra order_status IS NULL
CASE order_status
    WHEN NULL THEN 'missing'
    ELSE 'known'
END
```

Trong PostgreSQL, so sánh thông thường với `NULL` không cho TRUE. Hãy dùng searched CASE:

```sql
CASE
    WHEN order_status IS NULL THEN 'missing'
    ELSE 'known'
END
```

Đây là vấn đề **điều kiện chọn nhánh**, riêng với vấn đề **kiểu kết quả chung**.

## 15. Khác biệt cần nhớ giữa các hệ quản trị

Tên `CASE` được sử dụng rộng rãi, nhưng hệ thống kiểu dữ liệu không giống nhau giữa các DBMS.

| Hệ quản trị | Điểm cần nhớ về kiểu kết quả CASE |
| --- | --- |
| **PostgreSQL** | Cố tìm kiểu chung từ các nhánh theo nhóm kiểu, kiểu ưu tiên và quy tắc chuyển đổi. Một `CASE` có metadata kiểu kết quả xác định; trộn `TEXT` và `INTEGER` không tự cho một cột hỗn hợp tùy hàng. |
| **SQL Server** | Kiểu kết quả thường được xác định theo **thứ tự ưu tiên kiểu dữ liệu** (*data type precedence*) giữa các biểu thức kết quả; các nhánh còn lại phải chuyển đổi phù hợp, nếu không có thể lỗi. |
| **MySQL** | Có quy tắc tổng hợp kiểu riêng cho các nhánh `CASE`, bao gồm các nhóm số/chuỗi/ngày giờ. Cách chuyển đổi và cảnh báo phụ thuộc kiểu và ngữ cảnh; không suy ra trực tiếp từ PostgreSQL. |
| **Oracle Database** | Các kiểu kết quả phải tương thích theo quy tắc `CASE` của Oracle; với nhóm số, Oracle có quy tắc **numeric precedence**. Kiểu ký tự, ngày và chuyển kiểu ngầm cần xét riêng. |
| **SQLite** | Có **dynamic typing**; giá trị do `CASE` trả về có thể mang storage class khác nhau tùy nhánh và hàng, nhất là khi biểu thức đứng riêng trong truy vấn. Không nên dùng đặc điểm này để giả định những DBMS khác làm tương tự. |

### Ví dụ sự khác biệt với SQLite

Trong SQLite, có thể quan sát kiểu của giá trị ở thời điểm thực thi:

```sql
-- SQLite (không phải ví dụ PostgreSQL về kiểu kết quả tĩnh)
SELECT typeof(
    CASE WHEN 1 = 1 THEN 100 ELSE 'n/a' END
) AS selected_storage_class;
```

Kết quả có thể là `integer` vì nhánh được chọn trả số. Nếu điều kiện đổi để lấy `'n/a'` thì `typeof(...)` cho `text`. **Đây là cách SQLite phân loại giá trị**, khác với cơ chế PostgreSQL chọn một kiểu chung cho `CASE`.

Ngay cả trong SQLite, khi đưa kết quả vào bảng có ràng buộc, `STRICT` table hoặc ứng dụng cần một schema dữ liệu ổn định, kiểu đích vẫn cần được quản lý. Thiết kế API có kiểu ổn định luôn hữu ích dù DBMS linh hoạt về giá trị.

### Tránh suy luận “CASE luôn trả kiểu của nhánh đầu tiên”

Đó là kết luận sai ở nhiều DBMS. Trong PostgreSQL, kiểu được giải từ **toàn bộ** kết quả `THEN` và `ELSE`. Trong SQL Server, kiểu có mức ưu tiên cao có thể được chọn dù nhánh đó không phải nhánh đầu. Trong SQLite, kiểu giá trị có thể phụ thuộc nhánh được thực thi.

Vì vậy khi chuyển câu SQL giữa các hệ, nên ghi kiểu rõ ràng bằng `CAST` nếu ứng dụng phụ thuộc vào kiểu chính xác.

## 16. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `CASE types integer and text cannot be matched` trong PostgreSQL | Kết quả các nhánh là hai kiểu không tìm được kiểu chung | Chọn một kiểu đích theo nghiệp vụ; `CAST` từng nhánh cho nhất quán |
| `invalid input syntax for type integer` ở literal văn bản | PostgreSQL cố chuyển literal `unknown` sang số nhưng nội dung không phải số | Không trộn nhãn chữ với giá trị numeric; tách cột nhãn hoặc chuyển các kết quả thành `TEXT` |
| Kết quả `CASE` thành `NUMERIC` dù một nhánh là `INTEGER` | DBMS đã chọn kiểu số chung có thể chứa giá trị thập phân | Xác định kiểu cần trả và cast nếu muốn rõ ràng |
| Giá trị tiền bị đưa vào `DOUBLE PRECISION` | Nhánh có kiểu floating point tham gia vào suy luận kiểu | Dùng `NUMERIC`/`DECIMAL` thống nhất cho dữ liệu tiền |
| `CASE WHEN ... THEN NULL ELSE NULL END` có kiểu ngoài dự kiến | Mọi kết quả `NULL` chưa có kiểu nên DBMS chọn kiểu mặc định | Ghi `NULL::NUMERIC`, `NULL::DATE` hoặc kiểu rõ ràng |
| Một nhánh DATE, nhánh khác là `'Chưa có ngày'` | Nhãn văn bản không chuyển thành ngày hợp lệ | Trả `DATE/NULL::DATE`, tạo cột hiển thị riêng |
| `CAST(CASE ... END AS ...)` vẫn báo lỗi kiểu | Bản thân các nhánh `CASE` đã không thống nhất được | `CAST` bên trong từng `THEN`/`ELSE` trước |
| Dữ liệu trả về bị làm tròn/tràn sau cast | Kiểu numeric đích có precision/scale giới hạn | Chọn kiểu và quy tắc làm tròn theo miền giá trị thực tế |
| Cờ `TRUE/FALSE` bị trộn với số `0/1` | Boolean và integer là hai loại kết quả khác nhau | Chọn một hợp đồng biểu diễn: boolean hoặc integer |
| Một phép chia vẫn lỗi dù nhánh không được chọn | Biểu thức hằng hoặc kế hoạch có thể được xử lý sớm; hoặc điều kiện không bảo vệ đúng biểu thức | Đảm bảo mọi biểu thức hợp lệ và dùng `NULLIF`/điều kiện bảo vệ mẫu số phù hợp |
| Cùng CASE nhưng kiểu kết quả khác khi chuyển DBMS | Quy tắc phân giải và chuyển kiểu đặc thù từng hệ | Kiểm tra DBMS đích, dùng `CAST` tường minh, kiểm tra metadata đầu ra |

## 17. Bài tập tự luyện

Dùng bảng tạm `case_result_lab` đã tạo ở mục 4 trong PostgreSQL. Với mỗi bài, hãy **dự đoán kiểu kết quả trước**, rồi mới dự đoán giá trị từng hàng.

### Bài 1. Nhánh cùng kiểu nguyên

Dự đoán kiểu mà `pg_typeof` trả về:

```sql
SELECT pg_typeof(
    CASE WHEN TRUE THEN 10 ELSE 20 END
);
```

Vì sao điều kiện `TRUE` không làm thay đổi nhu cầu xác định kiểu của nhánh `ELSE`?

### Bài 2. Nhánh nguyên và thập phân

```sql
SELECT pg_typeof(
    CASE WHEN TRUE THEN 10 ELSE 20.75 END
);
```

Kiểu kết quả là gì? Viết lại để cả hai nhánh đều có kiểu `NUMERIC` rõ ràng.

### Bài 3. Nhánh số và nhãn chữ

Câu sau có hợp lệ ở PostgreSQL không?

```sql
SELECT order_id,
       CASE
           WHEN amount IS NULL THEN 'Chưa có tiền'
           ELSE amount
       END AS amount_or_message
FROM case_result_lab;
```

Hãy sửa theo hai yêu cầu: (a) cột chỉ để hiển thị dạng văn bản; (b) cột vẫn là số cho tính toán, và thông điệp được trả ở cột khác.

### Bài 4. NULL không định kiểu

Dự đoán kiểu:

```sql
SELECT
    pg_typeof(CASE WHEN TRUE THEN 5 ELSE NULL END),
    pg_typeof(CASE WHEN TRUE THEN NULL ELSE NULL END);
```

Viết một `CASE` trả `NULL` ở mọi nhánh nhưng có kiểu `DATE`.

### Bài 5. Cột số tiền

Với `case_result_lab`, tạo cột `signed_amount`:

- `PAID`: trả `amount`.
- `REFUNDED`: trả `-amount`.
- Các trạng thái khác: trả `0` dưới dạng `NUMERIC`.

Kết quả theo thứ tự `order_id` là gì?

### Bài 6. Ngày thanh toán

Viết `CASE` trả ngày `paid_at` nếu đơn `PAID`, còn lại trả `NULL::DATE`. Dùng `pg_typeof` xác nhận kiểu kết quả.

### Bài 7. Cờ boolean ba trạng thái

Tạo cột `is_paid`: `TRUE` nếu `PAID`, `NULL` nếu `order_status IS NULL`, còn lại `FALSE`. Vì sao không nên trả số `0` ở nhánh `ELSE` nếu muốn kiểu `BOOLEAN`?

### Bài 8. Scale và CAST ở ngoài CASE

Cho biểu thức:

```sql
CASE
    WHEN order_status = 'PAID' THEN amount
    ELSE 1.2345::NUMERIC
END
```

Viết cách ép **toàn bộ giá trị kết quả** về `NUMERIC(12,2)`. Giá trị nhánh `ELSE` sẽ trở thành bao nhiêu trong PostgreSQL?

### Bài 9. CASE có kiểu chung trong ORDER BY

Viết câu truy vấn sắp xếp `NEW` trước, `PAID` kế tiếp, `REFUNDED` rồi `CANCELLED`, và trạng thái `NULL` cuối cùng. Dùng `CASE` trả số thứ tự nguyên để `ORDER BY`.

### Bài 10. Đề xuất cấu trúc API

Một ứng dụng muốn trả tiền thanh toán (số hoặc thiếu) và lý do vì sao chưa có tiền. Hãy đề xuất hai cột thay vì một cột lúc `NUMERIC`, lúc chuỗi `'N/A'`. Giải thích điều đó giúp mapping sang Java `BigDecimal` và API như thế nào.

## 18. Gợi ý lời giải

**Bài 1:** `integer`. PostgreSQL phân giải kiểu của toàn bộ biểu thức `CASE` trước khi chọn giá trị theo điều kiện.

**Bài 2:** `numeric`. Có thể viết:

```sql
SELECT pg_typeof(
    CASE
        WHEN TRUE THEN 10::NUMERIC
        ELSE 20.75::NUMERIC
    END
);
```

**Bài 3:** Trong PostgreSQL, chuỗi `'Chưa có tiền'` không thể được chuyển thành kiểu numeric của `amount`. Cách (a):

```sql
SELECT order_id,
       CASE
           WHEN amount IS NULL THEN 'Chưa có tiền'
           ELSE amount::TEXT
       END AS amount_display
FROM case_result_lab
ORDER BY order_id;
```

Cách (b) giữ `amount` kiểu numeric và thêm cột `amount_status`:

```sql
SELECT order_id,
       amount AS amount_value,
       CASE
           WHEN amount IS NULL THEN 'missing'
           ELSE 'known'
       END AS amount_status
FROM case_result_lab
ORDER BY order_id;
```

**Bài 4:** Kết quả lần lượt `integer` và `text` trong PostgreSQL. Ví dụ kiểu `DATE`:

```sql
SELECT CASE
    WHEN TRUE THEN NULL::DATE
    ELSE NULL::DATE
END AS missing_date;
```

**Bài 5:**

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN amount
           WHEN order_status = 'REFUNDED' THEN -amount
           ELSE 0::NUMERIC
       END AS signed_amount
FROM case_result_lab
ORDER BY order_id;
```

Các giá trị lần lượt `0`, `120.00`, `0`, `-50.00`, `0`.

**Bài 6:**

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN paid_at
           ELSE NULL::DATE
       END AS payment_date,
       pg_typeof(
           CASE
               WHEN order_status = 'PAID' THEN paid_at
               ELSE NULL::DATE
           END
       ) AS payment_date_type
FROM case_result_lab
ORDER BY order_id;
```

Kiểu kết quả là `date`.

**Bài 7:**

```sql
SELECT order_id,
       CASE
           WHEN order_status = 'PAID' THEN TRUE
           WHEN order_status IS NULL THEN NULL::BOOLEAN
           ELSE FALSE
       END AS is_paid
FROM case_result_lab
ORDER BY order_id;
```

Mọi nhánh đều thuộc `BOOLEAN`; số `0` là integer, không phải boolean trong PostgreSQL.

**Bài 8:**

```sql
SELECT order_id,
       CAST(
           CASE
               WHEN order_status = 'PAID' THEN amount
               ELSE 1.2345::NUMERIC
           END AS NUMERIC(12,2)
       ) AS result_amount
FROM case_result_lab
ORDER BY order_id;
```

Nhánh `ELSE` được ép về `1.23`.

**Bài 9:**

```sql
SELECT order_id, order_status
FROM case_result_lab
ORDER BY
    CASE
        WHEN order_status = 'NEW' THEN 1
        WHEN order_status = 'PAID' THEN 2
        WHEN order_status = 'REFUNDED' THEN 3
        WHEN order_status = 'CANCELLED' THEN 4
        ELSE 5
    END,
    order_id;
```

**Bài 10:** Có thể trả `amount_value NUMERIC` (số hoặc `NULL`) và `amount_status TEXT` (`'known'`, `'missing'` hoặc trạng thái nghiệp vụ phù hợp). Khi đó Java có thể ánh xạ `amount_value` sang `BigDecimal` và `amount_status` sang `String` hoặc enum, tránh phải phân tích chuỗi lẫn trong cột số.

Khi viết một `CASE`, hãy kiểm tra **các điều kiện `WHEN` có đúng logic không**, sau đó kiểm tra riêng **mọi giá trị ở `THEN` và `ELSE` có thể cùng thuộc kiểu nào**. Nếu kết quả dùng cho tính toán, hãy giữ kiểu số/ngày/boolean phù hợp và biểu diễn trạng thái thiếu bằng `NULL` hoặc cột giải thích riêng. Nếu kết quả chỉ dùng hiển thị, có thể chuyển rõ ràng thành văn bản. Việc định nghĩa kiểu đầu ra ngay từ đầu giúp câu SQL dễ đọc, dễ chuyển hệ và ít gây lỗi cho ứng dụng sử dụng kết quả.
