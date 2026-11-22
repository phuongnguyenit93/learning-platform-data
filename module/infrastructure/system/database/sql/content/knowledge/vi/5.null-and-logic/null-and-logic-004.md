# AND, OR, NOT khi biểu thức có UNKNOWN

Trong SQL, một biểu thức điều kiện có thể nhận **ba giá trị logic**: **TRUE** (đúng), **FALSE** (sai) hoặc **UNKNOWN** (chưa xác định). Giá trị UNKNOWN thường phát sinh khi một phép so sánh liên quan đến **NULL**. Đây là **logic ba giá trị** (*three-valued logic*, 3VL), khác với logic hai giá trị quen thuộc trong nhiều ngôn ngữ lập trình.

Sự khác biệt này đặc biệt quan trọng với **AND**, **OR** và **NOT**. Chẳng hạn: **TRUE OR UNKNOWN = TRUE**, **FALSE AND UNKNOWN = FALSE**, còn **NOT UNKNOWN = UNKNOWN**. Nếu hiểu sai các quy tắc này, truy vấn có thể âm thầm bỏ sót đơn hàng chưa có trạng thái, tìm sai bản ghi thiếu thông tin hoặc tính sai số lượng các nhóm.

Bài học thuộc chương **NULL và logic**, module **Database SQL**. Các ví dụ thực hành dùng PostgreSQL; nguyên lý bảng chân trị và cách lọc theo TRUE được áp dụng rộng rãi trong SQL.

## 1. UNKNOWN xuất hiện từ đâu?

Giả sử cột **is_paid** của bảng đơn hàng lưu trạng thái thanh toán:

| order_id | is_paid | Ý nghĩa |
| ---: | --- | --- |
| 101 | TRUE | Đã xác nhận thanh toán |
| 102 | FALSE | Đã xác nhận chưa thanh toán |
| 103 | NULL | Chưa rõ/chưa ghi nhận trạng thái |

**NULL không đồng nghĩa với FALSE.** Với bản ghi 103, ta không thể khẳng định đơn đã thanh toán, nhưng cũng không thể khẳng định đơn chưa thanh toán. Vì thế, phép so sánh **is_paid = TRUE** cho kết quả UNKNOWN nếu is_paid là NULL.

~~~sql
SELECT
    TRUE = TRUE                   AS value_true,
    FALSE = TRUE                  AS value_false,
    NULL::BOOLEAN = TRUE          AS value_unknown,
    NOT (NULL::BOOLEAN = TRUE)    AS still_unknown;
~~~

Hai cột cuối có kết quả SQL NULL, biểu thị UNKNOWN trong kiểu BOOLEAN của PostgreSQL. **UNKNOWN là giá trị logic của biểu thức; NULL là dấu hiệu thiếu giá trị dữ liệu**. Chúng có liên hệ mật thiết nhưng không nên nhầm giá trị logic UNKNOWN với chuỗi văn bản 'UNKNOWN' do ứng dụng tự lưu.

Các phép so sánh thường gặp như **=**, **<>**, **<**, **>**, **<=**, **>=** trả về UNKNOWN nếu một toán hạng là NULL:

~~~sql
SELECT
    NULL::INTEGER = 5             AS equal_five,
    NULL::INTEGER <> 5            AS not_equal_five,
    NULL::INTEGER > 5             AS greater_than_five,
    NULL::INTEGER = NULL::INTEGER AS equal_nulls;
~~~

Tất cả đều là UNKNOWN. Đặc biệt, **NULL = NULL** không phải TRUE trong so sánh thông thường: hai giá trị chưa biết không tự động được coi là bằng nhau.

Để kiểm tra có hoặc không có dữ liệu, dùng các phép **IS NULL**, **IS NOT NULL**:

~~~sql
SELECT
    NULL::INTEGER IS NULL     AS is_missing,
    NULL::INTEGER IS NOT NULL AS is_present;
~~~

Kết quả tương ứng **TRUE** và **FALSE**. **IS NULL** là phép kiểm tra có kết quả xác định, khác với **= NULL**.

## 2. Bảng chân trị của AND

Ký hiệu **T** = TRUE, **F** = FALSE, **U** = UNKNOWN.

| A | B | A AND B | Giải thích |
| --- | --- | --- | --- |
| T | T | **T** | Cả hai đều đúng |
| T | F | **F** | Vế B sai |
| T | U | **U** | Chưa rõ vế B |
| F | T | **F** | Vế A sai |
| F | F | **F** | Hai vế sai |
| F | U | **F** | Vế A sai nên kết quả chắc chắn sai |
| U | T | **U** | Chưa rõ vế A |
| U | F | **F** | Vế B sai nên kết quả chắc chắn sai |
| U | U | **U** | Cả hai chưa xác định |

**Quy tắc:** Trong phép AND, **FALSE lấn át UNKNOWN**. Khi một vế đã sai, toàn bộ điều kiện AND sai dù vế còn lại chưa biết. Nếu không vế nào FALSE nhưng có UNKNOWN, kết quả UNKNOWN. Chỉ khi cả hai TRUE thì AND mới TRUE.

~~~sql
SELECT
    TRUE  AND NULL::BOOLEAN AS true_and_unknown,
    FALSE AND NULL::BOOLEAN AS false_and_unknown,
    TRUE  AND TRUE          AS true_and_true;
~~~

Ba kết quả lần lượt là **UNKNOWN**, **FALSE**, **TRUE**.

Ví dụ nghiệp vụ: “Khách đủ 18 tuổi **và** đã được xác minh”. Nếu tuổi đã biết là 15, kết quả **FALSE** ngay cả khi chưa rõ tình trạng xác minh. Nếu tuổi đã biết là 21 nhưng chưa rõ tình trạng xác minh, toàn bộ điều kiện **UNKNOWN**.

## 3. Bảng chân trị của OR

| A | B | A OR B | Giải thích |
| --- | --- | --- | --- |
| T | T | **T** | Ít nhất một vế đúng |
| T | F | **T** | Vế A đúng |
| T | U | **T** | Vế A đúng nên kết quả chắc chắn đúng |
| F | T | **T** | Vế B đúng |
| F | F | **F** | Hai vế đều sai |
| F | U | **U** | Chưa rõ vế B |
| U | T | **T** | Vế B đúng nên kết quả chắc chắn đúng |
| U | F | **U** | Chưa rõ vế A |
| U | U | **U** | Cả hai chưa xác định |

**Quy tắc:** Trong phép OR, **TRUE lấn át UNKNOWN**. Khi một vế chắc chắn đúng, toàn bộ OR đúng. Nếu không vế nào TRUE nhưng có UNKNOWN, kết quả UNKNOWN. OR chỉ FALSE nếu cả hai vế FALSE.

~~~sql
SELECT
    TRUE  OR NULL::BOOLEAN AS true_or_unknown,
    FALSE OR NULL::BOOLEAN AS false_or_unknown,
    FALSE OR FALSE         AS false_or_false;
~~~

Ba kết quả lần lượt **TRUE**, **UNKNOWN**, **FALSE**.

Ví dụ nghiệp vụ: “Đơn đã thanh toán **hoặc** giá trị trên 100.000 đồng”. Nếu trạng thái thanh toán chưa biết nhưng giá trị 200.000 đồng, toàn bộ OR **TRUE** vì vế thứ hai đã đúng.

## 4. Bảng chân trị của NOT

| A | NOT A |
| --- | --- |
| T | **F** |
| F | **T** |
| U | **U** |

**NOT đổi TRUE thành FALSE và FALSE thành TRUE, nhưng không biến điều chưa biết thành điều đã biết.**

~~~sql
SELECT
    NOT TRUE          AS not_true,
    NOT FALSE         AS not_false,
    NOT NULL::BOOLEAN AS not_unknown;
~~~

Kết quả lần lượt **FALSE**, **TRUE**, **UNKNOWN**.

**Không thể suy luận rằng một hàng không được chọn bởi điều kiện A thì chắc chắn sẽ được chọn bởi NOT A.** Hàng có A = UNKNOWN không được chọn bởi cả A lẫn NOT A khi chúng được dùng riêng trong WHERE.

### Ghi nhớ ba trường hợp đặc biệt

| Biểu thức | Kết quả |
| --- | --- |
| **FALSE AND UNKNOWN** | **FALSE** |
| **TRUE OR UNKNOWN** | **TRUE** |
| **NOT UNKNOWN** | **UNKNOWN** |

Nhận xét “hễ biểu thức chứa NULL thì kết quả luôn NULL” là **sai** đối với hai phép kết hợp đầu tiên.

## 5. Chuẩn bị bảng thực hành độc lập

Các ví dụ sau sử dụng **bảng tạm PostgreSQL** để không ảnh hưởng đến dữ liệu của những bài khác. Bảng tạm tồn tại trong phiên kết nối hiện tại.

~~~sql
CREATE TEMP TABLE logic3_orders (
    order_id        INTEGER PRIMARY KEY,
    total_vnd       INTEGER NOT NULL,
    is_paid         BOOLEAN,
    shipped_at      DATE,
    customer_region TEXT,
    coupon_code     TEXT
);

INSERT INTO logic3_orders
    (order_id, total_vnd, is_paid, shipped_at, customer_region, coupon_code)
VALUES
    (101, 120000, TRUE,  '2026-05-03', 'HN',  'SAVE10'),
    (102,  80000, FALSE, NULL,         'HCM', NULL),
    (103, 150000, NULL,  NULL,         'HN',  NULL),
    (104,  50000, TRUE,  NULL,         NULL,  'FIRST'),
    (105,  90000, TRUE,  '2026-05-06', 'HCM', NULL),
    (106, 200000, NULL,  '2026-05-07', NULL,  'VIP'),
    (107, 110000, TRUE,  NULL,         'HCM', NULL),
    (108,  70000, FALSE, NULL,         'HN',  'LOW');
~~~

Các đơn **103, 106** có **is_paid = NULL**; các đơn **104, 106** có **customer_region = NULL**. Nhờ vậy, những ví dụ về UNKNOWN có thể quan sát rõ.

> Nếu chạy lại lệnh tạo bảng trong cùng phiên, tên bảng đã tồn tại. Hãy mở phiên mới hoặc chủ động xóa **riêng bảng tạm logic3_orders** trước khi tạo lại. Không cần xóa bảng nghiệp vụ thật.

## 6. Phân tích AND, OR, NOT ngay trên dữ liệu

Giả sử điều kiện A là **is_paid**, điều kiện B là **total_vnd >= 100000**. Chạy:

~~~sql
SELECT
    order_id,
    is_paid,
    total_vnd,
    is_paid AND (total_vnd >= 100000) AS paid_and_large,
    is_paid OR  (total_vnd >= 100000) AS paid_or_large,
    NOT is_paid                        AS not_paid
FROM logic3_orders
ORDER BY order_id;
~~~

Kết quả logic (U biểu thị NULL của BOOLEAN):

| order_id | is_paid (A) | total_vnd >= 100000 (B) | A AND B | A OR B | NOT A |
| ---: | --- | --- | --- | --- | --- |
| 101 | T | T | **T** | **T** | F |
| 102 | F | F | F | F | **T** |
| 103 | U | T | U | **T** | U |
| 104 | T | F | F | **T** | F |
| 105 | T | F | F | **T** | F |
| 106 | U | T | U | **T** | U |
| 107 | T | T | **T** | **T** | F |
| 108 | F | F | F | F | **T** |

**Đơn 103 và 106** minh họa điểm khác nhau quan trọng: **UNKNOWN AND TRUE = UNKNOWN**, trong khi **UNKNOWN OR TRUE = TRUE**. Dù chưa rõ trạng thái thanh toán, ta biết chắc hai đơn có giá trị cao.

### 6.1. AND trong WHERE

~~~sql
SELECT order_id, total_vnd, is_paid
FROM logic3_orders
WHERE is_paid AND total_vnd >= 100000
ORDER BY order_id;
~~~

Chỉ trả về đơn **101, 107**. Các đơn 103 và 106 không được giữ vì điều kiện cho UNKNOWN, chứ không phải vì hệ thống xác nhận chưa thanh toán.

### 6.2. OR trong WHERE

~~~sql
SELECT order_id, total_vnd, is_paid
FROM logic3_orders
WHERE is_paid OR total_vnd >= 100000
ORDER BY order_id;
~~~

Trả về **101, 103, 104, 105, 106, 107**. Với 103 và 106, vế tổng tiền TRUE nên toàn bộ OR TRUE.

### 6.3. NOT trong WHERE

~~~sql
SELECT order_id, is_paid
FROM logic3_orders
WHERE NOT is_paid
ORDER BY order_id;
~~~

Chỉ trả về **102, 108**. Hai đơn 103 và 106 có NOT UNKNOWN = UNKNOWN nên không được chọn.

Nếu yêu cầu là **“lấy cả đơn được xác nhận chưa thanh toán và đơn chưa xác định thanh toán”**, dùng:

~~~sql
SELECT order_id, is_paid
FROM logic3_orders
WHERE is_paid = FALSE OR is_paid IS NULL
ORDER BY order_id;
~~~

Kết quả **102, 103, 106, 108**. Trong PostgreSQL, có thể viết gọn điều kiện trên bằng:

~~~sql
WHERE is_paid IS NOT TRUE
~~~

Đây là lựa chọn **ngữ nghĩa nghiệp vụ**: *được xác nhận là FALSE* khác với *chưa xác nhận là TRUE*.

## 7. WHERE chỉ giữ TRUE: FALSE và UNKNOWN đều bị loại

Quy tắc trung tâm của bộ lọc **WHERE** là chỉ giữ những hàng mà điều kiện được đánh giá thành **TRUE**. **FALSE** và **UNKNOWN** đều khiến hàng bị loại.

| Kết quả của biểu thức WHERE | Hàng được chọn? |
| --- | --- |
| TRUE | **Có** |
| FALSE | Không |
| UNKNOWN | Không |

Vì vậy:

~~~sql
SELECT order_id
FROM logic3_orders
WHERE NOT (is_paid AND total_vnd >= 100000)
ORDER BY order_id;
~~~

cho kết quả **102, 104, 105, 108**. NOT của toàn bộ biểu thức chỉ TRUE nếu biểu thức gốc FALSE. Hai đơn **103, 106** vẫn bị loại vì biểu thức gốc UNKNOWN.

Muốn nhận cả **FALSE và UNKNOWN** của biểu thức gốc, hãy yêu cầu rõ:

~~~sql
SELECT order_id
FROM logic3_orders
WHERE (is_paid AND total_vnd >= 100000) IS NOT TRUE
ORDER BY order_id;
~~~

Kết quả **102, 103, 104, 105, 106, 108**.

**Điểm dễ nhầm:** “không thỏa WHERE A” không đồng nhất với “thỏa WHERE NOT A”. Trường hợp A = UNKNOWN không đi qua bộ lọc nào trong hai bộ lọc đó.

## 8. IS TRUE, IS FALSE, IS UNKNOWN để phân biệt ba tình huống

Các phép kiểm tra chân trị trên biểu thức BOOLEAN giúp xác định tường minh kết quả, kể cả UNKNOWN:

| A | A IS TRUE | A IS FALSE | A IS UNKNOWN | A IS NOT TRUE |
| --- | --- | --- | --- | --- |
| TRUE | TRUE | FALSE | FALSE | FALSE |
| FALSE | FALSE | TRUE | FALSE | TRUE |
| UNKNOWN | FALSE | FALSE | TRUE | TRUE |

Các phép kiểm tra **IS TRUE**, **IS FALSE**, **IS UNKNOWN**, **IS NOT TRUE**, **IS NOT FALSE**, **IS NOT UNKNOWN** trả về TRUE hoặc FALSE. Đừng nhầm **NOT A** với **A IS FALSE**: nếu A = UNKNOWN thì NOT A = UNKNOWN, còn A IS FALSE = FALSE.

~~~sql
SELECT
    order_id,
    (is_paid AND total_vnd >= 100000) IS TRUE    AS exactly_true,
    (is_paid AND total_vnd >= 100000) IS FALSE   AS exactly_false,
    (is_paid AND total_vnd >= 100000) IS UNKNOWN AS unknown_result
FROM logic3_orders
ORDER BY order_id;
~~~

Ví dụ với đơn **103**, cột exactly_true = FALSE, exactly_false = FALSE, unknown_result = TRUE. Với đơn **102**, ba kết quả tương ứng FALSE, TRUE, FALSE.

Khi A là biểu thức BOOLEAN, **A IS UNKNOWN** cũng nhận diện trường hợp **A IS NULL**. Tuy nhiên, cụm **IS UNKNOWN** được dùng cho biểu thức chân trị; để hỏi liệu cột văn bản hay cột số có thiếu dữ liệu, nên dùng **IS NULL**.

## 9. Độ ưu tiên: NOT, rồi AND, rồi OR

Trong các biểu thức logic phổ biến, thứ tự ưu tiên là:

1. **NOT** được áp dụng trước.
2. **AND** được áp dụng tiếp.
3. **OR** được áp dụng sau.

Ví dụ:

~~~sql
WHERE NOT is_paid OR total_vnd >= 100000
~~~

được hiểu là:

~~~sql
WHERE (NOT is_paid) OR (total_vnd >= 100000)
~~~

Tương tự:

~~~sql
WHERE is_paid OR total_vnd >= 100000 AND customer_region = 'HN'
~~~

được hiểu là:

~~~sql
WHERE is_paid OR (
    (total_vnd >= 100000) AND (customer_region = 'HN')
)
~~~

Đặt ngoặc khác đi có thể thay đổi các hàng được trả về, nhất là khi customer_region NULL.

~~~sql
SELECT
    TRUE OR FALSE AND FALSE   AS without_parentheses,
    (TRUE OR FALSE) AND FALSE AS with_parentheses;
~~~

Hai kết quả là **TRUE** và **FALSE**. Nên thêm ngoặc trong các điều kiện nghiệp vụ phức tạp để giảm nguy cơ hiểu nhầm, kể cả khi đã biết độ ưu tiên.

### Độ ưu tiên không đồng nghĩa với thứ tự thực thi

SQL không bảo đảm rằng hệ quản trị luôn kiểm tra vế trái của AND/OR rồi mới kiểm tra vế phải theo kiểu *short-circuit* của một số ngôn ngữ lập trình. Bộ tối ưu truy vấn có thể biến đổi thứ tự thực thi nếu phù hợp ngữ nghĩa.

Do đó, không nên coi điều kiện sau là biện pháp chắc chắn chống chia cho 0:

~~~sql
-- Không dựa vào vế trái để bảo đảm tránh lỗi ở vế phải.
WHERE denominator <> 0
  AND numerator / denominator > 10
~~~

Với PostgreSQL, có thể viết biểu thức xử lý mẫu số 0 một cách rõ ràng:

~~~sql
WHERE numerator / NULLIF(denominator, 0) > 10
~~~

**NULLIF(denominator, 0)** cho NULL khi mẫu số bằng 0; phép chia khi đó cho NULL, so sánh cho UNKNOWN và WHERE loại hàng tương ứng.

## 10. Luật De Morgan và bẫy phủ định

Hai luật De Morgan vẫn đúng dưới logic ba giá trị:

\[
\mathrm{NOT}(A\ \mathrm{AND}\ B)
\equiv
(\mathrm{NOT}\ A)\ \mathrm{OR}\ (\mathrm{NOT}\ B)
\]

\[
\mathrm{NOT}(A\ \mathrm{OR}\ B)
\equiv
(\mathrm{NOT}\ A)\ \mathrm{AND}\ (\mathrm{NOT}\ B)
\]

Hai vế của mỗi đẳng thức cho cùng kết quả trong **cả ba** trường hợp TRUE, FALSE, UNKNOWN.

~~~sql
SELECT
    order_id,
    NOT (is_paid AND total_vnd >= 100000) AS form_a,
    (NOT is_paid) OR NOT (total_vnd >= 100000) AS form_b
FROM logic3_orders
ORDER BY order_id;
~~~

Hai cột form_a và form_b luôn có cùng giá trị, kể cả ở hàng có is_paid NULL.

Tuy nhiên, có hai quy tắc logic hai giá trị **không còn luôn đúng**:

- **A OR NOT A** không phải lúc nào cũng TRUE. Với A = UNKNOWN, biểu thức bằng UNKNOWN.
- **A AND NOT A** không phải lúc nào cũng FALSE. Với A = UNKNOWN, biểu thức bằng UNKNOWN.

~~~sql
SELECT
    NULL::BOOLEAN OR  NOT NULL::BOOLEAN AS unknown_or_not_unknown,
    NULL::BOOLEAN AND NOT NULL::BOOLEAN AS unknown_and_not_unknown;
~~~

Cả hai cột đều cho UNKNOWN. Đây là lý do **NOT (x = 5)** không thể dùng để lấy tất cả hàng có x khác 5 **kể cả NULL**.

## 11. Phủ định so sánh khi cột có NULL

### 11.1. Điều kiện khác 'HN' không tự bao gồm vùng chưa biết

~~~sql
SELECT order_id, customer_region
FROM logic3_orders
WHERE customer_region <> 'HN'
ORDER BY order_id;
~~~

Kết quả gồm **102, 105, 107** (region = 'HCM'). Hai đơn **104, 106** có customer_region NULL bị loại do NULL <> 'HN' là UNKNOWN.

Nếu yêu cầu nghiệp vụ là **“khác HN hoặc chưa có thông tin vùng”**, dùng:

~~~sql
SELECT order_id, customer_region
FROM logic3_orders
WHERE customer_region <> 'HN'
   OR customer_region IS NULL
ORDER BY order_id;
~~~

Kết quả gồm **102, 104, 105, 106, 107**.

### 11.2. So sánh xử lý NULL bằng IS DISTINCT FROM

PostgreSQL hỗ trợ **IS DISTINCT FROM** và **IS NOT DISTINCT FROM**. Chúng trả về TRUE/FALSE, kể cả khi toán hạng NULL:

~~~sql
SELECT
    NULL::TEXT IS DISTINCT FROM 'HN'              AS null_differs_from_hn,
    NULL::TEXT IS DISTINCT FROM NULL::TEXT        AS two_nulls_differ,
    NULL::TEXT IS NOT DISTINCT FROM NULL::TEXT    AS two_nulls_not_distinct;
~~~

Kết quả lần lượt **TRUE, FALSE, TRUE**. Vì vậy, điều kiện:

~~~sql
WHERE customer_region IS DISTINCT FROM 'HN'
~~~

chọn các vùng khác 'HN' và cả vùng NULL. Cú pháp này thể hiện **quy tắc so sánh có xử lý NULL**, không đồng nghĩa với khẳng định hai giá trị chưa biết thực sự là cùng một khu vực.

### 11.3. COALESCE đổi NULL theo quy ước

~~~sql
SELECT order_id
FROM logic3_orders
WHERE NOT COALESCE(is_paid, FALSE)
ORDER BY order_id;
~~~

Kết quả **102, 103, 106, 108**. **COALESCE(is_paid, FALSE)** chủ động quy ước trạng thái NULL được xử lý như FALSE; sau đó NOT trở thành TRUE.

Việc quy ước này phù hợp hay không tùy nghiệp vụ. Với báo cáo cần tách biệt **“chưa thanh toán”** và **“chưa biết”**, thay NULL bằng FALSE có thể làm mất thông tin quan trọng.

## 12. WHERE, HAVING, JOIN ON, CASE WHEN và CHECK khi có UNKNOWN

Không phải mọi vị trí dùng biểu thức điều kiện đều xử lý UNKNOWN giống nhau về mặt tác động:

| Vị trí | Hành vi khi điều kiện là UNKNOWN |
| --- | --- |
| **WHERE** | Không giữ hàng; chỉ TRUE được giữ |
| **HAVING** | Không giữ nhóm; chỉ TRUE được giữ |
| **JOIN ... ON** | Không coi cặp hàng là khớp; chỉ TRUE tạo cặp ghép |
| **CASE WHEN** | Không vào nhánh WHEN đó; xét WHEN tiếp theo hoặc ELSE |
| **CHECK** constraint | Không vi phạm CHECK; chỉ FALSE bị từ chối |

### 12.1. HAVING lọc nhóm

~~~sql
SELECT
    customer_region,
    COUNT(*) AS order_count
FROM logic3_orders
GROUP BY customer_region
HAVING COUNT(*) >= 2
ORDER BY customer_region NULLS LAST;
~~~

HAVING giống WHERE ở quy tắc “chỉ TRUE được giữ”, nhưng thường làm việc trên các nhóm sau GROUP BY. Một nhóm có biểu thức HAVING trả UNKNOWN sẽ không xuất hiện.

### 12.2. JOIN ON không xem NULL = NULL là TRUE

~~~sql
WITH region_fees(region, fee_vnd) AS (
    VALUES
        ('HN'::TEXT, 15000),
        ('HCM'::TEXT, 20000),
        (NULL::TEXT, 0)
)
SELECT
    o.order_id,
    o.customer_region,
    f.region AS matched_region,
    f.fee_vnd
FROM logic3_orders AS o
LEFT JOIN region_fees AS f
    ON o.customer_region = f.region
ORDER BY o.order_id;
~~~

Đơn **104, 106** có customer_region NULL. Mặc dù bảng region_fees cũng có một hàng region NULL, phép so sánh **NULL = NULL** vẫn UNKNOWN nên không tạo cặp khớp. Vì dùng **LEFT JOIN**, đơn hàng vẫn xuất hiện nhưng các cột từ bảng mức phí là NULL.

Nếu quy tắc nghiệp vụ **cố ý coi hai giá trị NULL là tương ứng**, PostgreSQL có thể dùng **ON o.customer_region IS NOT DISTINCT FROM f.region**. Chỉ áp dụng khi quan hệ giữa hai NULL được quy định rõ; thiếu thông tin khu vực thường không phải một khu vực thực tế.

### 12.3. CASE WHEN chỉ chọn nhánh có TRUE

~~~sql
SELECT
    order_id,
    CASE
        WHEN is_paid AND total_vnd >= 100000 THEN 'Da thanh toan - don lon'
        WHEN is_paid IS NULL THEN 'Chua ro thanh toan'
        WHEN is_paid IS FALSE THEN 'Chua thanh toan'
        ELSE 'Trang thai khac'
    END AS payment_label
FROM logic3_orders
ORDER BY order_id;
~~~

Các đơn **103, 106** không vào nhánh đầu vì điều kiện AND là UNKNOWN; chúng được đưa vào nhánh **is_paid IS NULL**. Nếu không có nhánh WHEN phù hợp thì SQL chọn ELSE, hoặc trả NULL khi không có ELSE.

### 12.4. CHECK chấp nhận UNKNOWN

Điểm dễ ngạc nhiên: khác WHERE, ràng buộc **CHECK** chỉ từ chối hàng khi điều kiện **FALSE**. TRUE hoặc UNKNOWN đều không vi phạm CHECK.

~~~sql
CREATE TEMP TABLE logic3_scores (
    score INTEGER CHECK (score >= 0)
);

INSERT INTO logic3_scores(score)
VALUES (10), (NULL);
~~~

Cả hai dòng được chấp nhận, vì với NULL thì **score >= 0** là UNKNOWN. Muốn cấm NULL, cần thêm **NOT NULL**:

~~~sql
CREATE TEMP TABLE logic3_required_scores (
    score INTEGER NOT NULL CHECK (score >= 0)
);
~~~

CHECK kiểm soát **miền giá trị**; NOT NULL kiểm soát **bắt buộc có dữ liệu**. Hai ràng buộc bổ sung cho nhau.

## 13. Bẫy NOT IN khi danh sách chứa NULL

Một ví dụ điển hình của UNKNOWN:

~~~sql
SELECT
    99 NOT IN (10, 20, NULL::INTEGER) AS ninety_nine_not_in,
    10 NOT IN (10, 20, NULL::INTEGER) AS ten_not_in;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| 99 NOT IN (10, 20, NULL) | **UNKNOWN** |
| 10 NOT IN (10, 20, NULL) | **FALSE** |

Có thể hiểu biểu thức đầu như phép AND:

~~~sql
99 <> 10 AND 99 <> 20 AND 99 <> NULL
~~~

Hai so sánh đầu là TRUE, so sánh cuối UNKNOWN, nên toàn bộ là UNKNOWN. Nếu đặt biểu thức này trong WHERE, hàng 99 cũng bị loại dù không bằng 10 hay 20.

**IN** có thể tương tự tạo UNKNOWN khi không tìm thấy phần tử khớp nhưng danh sách chứa NULL. Ngược lại, **10 IN (10, NULL)** là TRUE vì một vế so khớp đã TRUE.

Nếu tập mã cấm chứa NULL nhưng yêu cầu là “mã không trùng bất cứ mã hợp lệ nào”, có thể loại NULL ở danh sách bên phải:

~~~sql
SELECT order_id
FROM logic3_orders
WHERE order_id NOT IN (
    SELECT blocked_id
    FROM (VALUES (101), (103), (NULL::INTEGER)) AS blocked(blocked_id)
    WHERE blocked_id IS NOT NULL
)
ORDER BY order_id;
~~~

Hoặc mô tả yêu cầu bằng **NOT EXISTS**:

~~~sql
WITH blocked(blocked_id) AS (
    VALUES (101), (103), (NULL::INTEGER)
)
SELECT o.order_id
FROM logic3_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked AS b
    WHERE b.blocked_id = o.order_id
)
ORDER BY o.order_id;
~~~

**EXISTS** kiểm tra có ít nhất một hàng thỏa điều kiện con hay không và trả TRUE/FALSE; **NOT EXISTS** phủ định kết quả đó. Một hàng NULL riêng lẻ trong bảng con không làm NOT EXISTS trở thành UNKNOWN. Nếu mã phía ngoài có thể NULL, cần quyết định riêng việc giữ hay loại những hàng không có mã, vì phép so sánh bằng NULL không tạo cặp khớp.

## 14. Đếm riêng TRUE, FALSE và UNKNOWN

Một cách kiểm tra tình trạng dữ liệu là đếm số hàng cho từng giá trị logic của cùng một điều kiện. Với biểu thức **is_paid AND total_vnd >= 100000**:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE (is_paid AND total_vnd >= 100000) IS TRUE
    ) AS condition_true,
    COUNT(*) FILTER (
        WHERE (is_paid AND total_vnd >= 100000) IS FALSE
    ) AS condition_false,
    COUNT(*) FILTER (
        WHERE (is_paid AND total_vnd >= 100000) IS UNKNOWN
    ) AS condition_unknown
FROM logic3_orders;
~~~

Kết quả mong đợi:

| all_orders | condition_true | condition_false | condition_unknown |
| ---: | ---: | ---: | ---: |
| 8 | 2 | 4 | 2 |

Hai hàng **101, 107** là TRUE; bốn hàng **102, 104, 105, 108** là FALSE; hai hàng **103, 106** là UNKNOWN. Tổng **2 + 4 + 2 = 8**.

Nếu hệ quản trị không hỗ trợ cú pháp **FILTER**, có thể dùng **SUM(CASE ...)**:

~~~sql
SELECT
    SUM(CASE
        WHEN (is_paid AND total_vnd >= 100000) IS TRUE THEN 1 ELSE 0
    END) AS true_count,
    SUM(CASE
        WHEN (is_paid AND total_vnd >= 100000) IS FALSE THEN 1 ELSE 0
    END) AS false_count,
    SUM(CASE
        WHEN (is_paid AND total_vnd >= 100000) IS UNKNOWN THEN 1 ELSE 0
    END) AS unknown_count
FROM logic3_orders;
~~~

Cách phân loại này hữu ích cho kiểm soát chất lượng dữ liệu: chưa rõ trạng thái thanh toán được nhìn thấy riêng, thay vì bị âm thầm gộp vào nhóm FALSE.

## 15. Lỗi thường gặp và cách xử lý

| Hiểu nhầm hoặc cách viết | Hệ quả | Cách hiểu hoặc sửa |
| --- | --- | --- |
| “NULL chính là FALSE.” | Đánh đồng thiếu thông tin với phủ định | NULL thường dẫn đến UNKNOWN trong so sánh; FALSE và UNKNOWN khác nhau |
| **column = NULL** | Cho UNKNOWN, không tìm được hàng NULL | Dùng **column IS NULL** |
| **column <> NULL** | Cho UNKNOWN, không tìm được hàng khác NULL | Dùng **column IS NOT NULL** |
| “AND gặp UNKNOWN thì luôn UNKNOWN.” | Dự đoán sai FALSE AND UNKNOWN | Nhớ FALSE AND UNKNOWN = FALSE |
| “OR gặp UNKNOWN thì luôn UNKNOWN.” | Dự đoán sai TRUE OR UNKNOWN | Nhớ TRUE OR UNKNOWN = TRUE |
| “NOT UNKNOWN = TRUE.” | Dự đoán sai phủ định | NOT UNKNOWN vẫn UNKNOWN |
| “WHERE NOT A lấy tất cả hàng không thỏa A.” | Bỏ sót hàng có A = UNKNOWN | Xem xét **A IS NOT TRUE** nếu muốn gồm FALSE và UNKNOWN |
| Dùng **NOT IN** với danh sách chứa NULL | Nhiều hàng không khớp vẫn bị loại | Cân nhắc **NOT EXISTS**, hoặc lọc NULL đúng nghiệp vụ |
| Dùng **COALESCE(flag, FALSE)** theo thói quen | Xóa khác biệt giữa FALSE và UNKNOWN | Chỉ thay NULL khi đã có quy tắc nghiệp vụ |
| Không đặt ngoặc khi trộn AND, OR | Dễ hiểu sai ưu tiên | Dùng ngoặc cho điều kiện phức hợp |
| Nghĩ CHECK (x > 0) cấm NULL | CHECK chấp nhận UNKNOWN | Dùng **NOT NULL** nếu bắt buộc có x |
| Dựa vào “AND dừng ngay khi vế trái sai” | Có thể phát sinh lỗi do cách tối ưu SQL | Viết biểu thức an toàn, không phụ thuộc thứ tự đánh giá |

## 16. Bài tập thực hành

Sử dụng bảng **logic3_orders** và các bảng chân trị phía trên:

1. Dự đoán trước khi chạy các biểu thức **TRUE AND NULL::BOOLEAN**, **FALSE AND NULL::BOOLEAN**, **TRUE OR NULL::BOOLEAN**, **FALSE OR NULL::BOOLEAN** và **NOT NULL::BOOLEAN**.
2. Lọc các đơn **đã thanh toán và có giá trị ít nhất 100.000 đồng**. Vì sao đơn 103 và 106 không có trong kết quả?
3. Lọc các đơn **đã thanh toán hoặc có giá trị ít nhất 100.000 đồng**. So sánh số hàng với bài 2.
4. Viết hai truy vấn: một truy vấn chỉ lấy các đơn **được xác nhận chưa thanh toán**, truy vấn còn lại lấy **cả đơn chưa thanh toán và chưa rõ thanh toán**.
5. So sánh **WHERE NOT (is_paid AND total_vnd >= 100000)** với **WHERE (is_paid AND total_vnd >= 100000) IS NOT TRUE**. Giải thích sự khác biệt.
6. Tìm các đơn có **customer_region khác 'HN'**, rồi sửa điều kiện để bao gồm cả những đơn thiếu thông tin khu vực.
7. Viết một điều kiện gồm **NOT**, **AND**, **OR**. Thêm dấu ngoặc để thể hiện rõ mong muốn nghiệp vụ; thử thay đổi ngoặc và quan sát kết quả.
8. Đếm riêng các đơn có biểu thức **is_paid AND total_vnd >= 100000** bằng TRUE, FALSE, UNKNOWN.
9. Dự đoán **105 NOT IN (101, 103, NULL)** cho kết quả gì. Dùng **NOT EXISTS** viết lại yêu cầu “mã đơn không nằm trong danh sách cấm”.
10. Tạo bảng tạm có **CHECK (discount >= 0)**, thử thêm discount = NULL. Tạo lại với **NOT NULL** và giải thích điểm khác nhau.

### Tự kiểm tra nhanh

**Câu 1:** A = UNKNOWN, B = FALSE. **NOT (A OR B)** là gì?

**Đáp án:** A OR B = UNKNOWN, nên NOT (A OR B) = **UNKNOWN**.

**Câu 2:** A = UNKNOWN, B = TRUE. **A AND B** và **A OR B** là gì?

**Đáp án:** A AND B = **UNKNOWN**; A OR B = **TRUE**.

**Câu 3:** Một hàng có is_paid = NULL có được chọn bởi **WHERE NOT is_paid** không?

**Đáp án:** **Không**. NOT UNKNOWN là UNKNOWN, trong khi WHERE chỉ chọn TRUE.

**Câu 4:** Vì sao **FALSE AND UNKNOWN = FALSE**, nhưng **FALSE OR UNKNOWN = UNKNOWN**?

**Đáp án:** AND chỉ cần một vế sai để chắc chắn sai; OR không thể khẳng định sai khi vế còn lại chưa xác định.

## 17. Ghi nhớ để áp dụng

**UNKNOWN là giá trị logic thứ ba của SQL**, thường do phép so sánh với NULL tạo ra. Trong biểu thức kết hợp, **FALSE lấn át UNKNOWN ở AND**, **TRUE lấn át UNKNOWN ở OR**, còn **NOT giữ UNKNOWN**. Điều kiện WHERE/HAVING chỉ giữ TRUE; ON chỉ ghép các cặp có điều kiện TRUE; CHECK chỉ bác bỏ FALSE.

Khi thiết kế truy vấn, hãy quyết định rõ dữ liệu chưa biết có nên nằm trong kết quả hay không. Chọn **AND**, **OR**, **NOT**, **IS NULL**, **IS [NOT] TRUE**, **IS UNKNOWN**, **IS DISTINCT FROM**, hoặc **COALESCE** dựa trên ý nghĩa nghiệp vụ, thay vì ngầm xem NULL là FALSE.
