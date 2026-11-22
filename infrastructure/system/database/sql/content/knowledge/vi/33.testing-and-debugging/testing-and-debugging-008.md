# So sánh kết quả có xét bản sao và thứ tự khi cần

Khi kiểm thử hoặc gỡ lỗi SQL, câu hỏi “hai truy vấn có trả cùng kết quả không?” tưởng như đơn giản. Nhưng “cùng” có thể mang nhiều nghĩa. Hai kết quả có thể chứa cùng các giá trị nhưng khác số lần xuất hiện; có thể chứa đủ các hàng nhưng theo thứ tự khác; hoặc có cùng dữ liệu nhìn thấy nhưng khác kiểu, độ chính xác, giá trị NULL hay quy tắc so sánh chuỗi.

SQL mặc định xử lý kết quả theo **multiset (bag)**: một hàng có thể xuất hiện nhiều lần. Thứ tự hàng **không được bảo đảm nếu truy vấn không có `ORDER BY`**. Vì vậy, cách so sánh phải xuất phát từ hợp đồng của truy vấn:

- Nếu chỉ quan tâm những hàng và số lần mỗi hàng xuất hiện, so sánh theo **multiset**, có xét bản sao.
- Nếu hợp đồng yêu cầu thứ tự, so sánh theo **sequence**, tức vị trí từng hàng.
- Nếu nghiệp vụ chỉ quan tâm các giá trị duy nhất, so sánh theo **set**, bỏ qua số lần lặp.
- Nếu kết quả chứa số gần đúng, timestamp, text theo collation hoặc JSON, phải quy định rõ cách so sánh từng kiểu.

Một phép so sánh sai có thể tạo false positive — báo lỗi dù hai kết quả tương đương theo contract — hoặc false negative — bỏ qua việc mất hàng trùng, sai thứ tự, mất precision hay khác NULL.

> **Nguyên tắc:** xác định trước kết quả là set, multiset hay sequence. Không tự loại bản sao bằng `Set`/`DISTINCT`, không tự sắp xếp để che lỗi thứ tự nếu thứ tự là yêu cầu, và không kiểm tra thứ tự khi SQL chưa cam kết bằng `ORDER BY`.

Bài học thuộc **Database SQL → Kiểm thử và gỡ lỗi**. Nội dung trình bày semantics của result set, cách so sánh có và không xét duplicate, thứ tự có tie-breaker, `EXCEPT`/`EXCEPT ALL`, cách portable bằng GROUP BY và số lượng, xử lý NULL/type/collation, kiểm thử differential và regression, so sánh kết quả lớn, cùng 30 bài tập.

## 1. Ba mô hình kết quả cần phân biệt

Giả sử truy vấn trả các giá trị:

```text
A
A
B
C
```

Có ba cách nhìn:

### 1.1. Set — tập hợp

Set chỉ quan tâm một giá trị có xuất hiện hay không:

```text
{A, B, C}
```

Hai kết quả sau được xem là bằng nhau theo set:

```text
A, A, B, C
A, B, C
```

Set bỏ qua số lần xuất hiện.

### 1.2. Multiset / bag — tập hợp có số lần xuất hiện

Multiset giữ số lần mỗi giá trị xuất hiện:

```text
A -> 2
B -> 1
C -> 1
```

Hai kết quả chỉ bằng nhau nếu mỗi hàng có cùng số lần xuất hiện. Vì thế:

```text
A, A, B, C
A, B, B, C
```

khác nhau dù cả hai đều có tập giá trị duy nhất `{A, B, C}`.

### 1.3. Sequence — dãy có thứ tự

Sequence quan tâm cả giá trị lẫn vị trí:

```text
1: A
2: A
3: B
4: C
```

Kết quả:

```text
A, A, B, C
A, B, A, C
```

có cùng multiset nhưng khác sequence.

### 1.4. Bảng so sánh

| Mô hình | Quan tâm giá trị | Quan tâm số lần lặp | Quan tâm vị trí |
| --- | --- | --- | --- |
| Set | Có | Không | Không |
| Multiset/bag | Có | Có | Không |
| Sequence | Có | Có | Có |

**Phải chọn mô hình dựa trên contract**, không dựa vào cách tiện nhất để viết test.

## 2. SQL mặc định là bag, không phải set

Một hiểu nhầm thường gặp là SQL `SELECT` luôn trả các hàng duy nhất. Thực tế, `SELECT` mặc định giữ bản sao.

```sql
SELECT status
FROM orders;
```

Nếu 20 đơn có status `PAID`, kết quả có thể chứa `PAID` 20 lần.

Muốn loại bản sao:

```sql
SELECT DISTINCT status
FROM orders;
```

`DISTINCT` thay đổi semantics: mỗi giá trị kết quả chỉ xuất hiện một lần theo quy tắc so sánh của DBMS.

### 2.1. UNION và UNION ALL

```sql
SELECT status FROM current_orders
UNION
SELECT status FROM archived_orders;
```

`UNION` loại duplicate giữa các đầu vào.

```sql
SELECT status FROM current_orders
UNION ALL
SELECT status FROM archived_orders;
```

`UNION ALL` giữ tất cả hàng, kể cả duplicate.

Nếu hai nguồn đều có `PAID`, `UNION` có thể trả một `PAID`; `UNION ALL` trả cả hai lần xuất hiện.

### 2.2. JOIN cũng có thể tạo duplicate

Giả sử một customer có ba orders. JOIN customer với orders tạo ba hàng có cùng thông tin customer. Đó không nhất thiết là lỗi; cardinality là một customer tới nhiều order.

Một phép so sánh chỉ dùng `Set<Customer>` có thể vô tình loại các lần xuất hiện hợp lệ. Cần xác định test đang kiểm tra:
- Một hàng customer duy nhất.
- Một hàng cho mỗi order.
- Hay một aggregate theo customer.

### 2.3. GROUP BY thay đổi mức độ chi tiết

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
```

Kết quả không còn một hàng cho mỗi order mà là một hàng cho mỗi customer có đơn. So sánh với query chi tiết phải so đúng grain (mức độ chi tiết) của dữ liệu.

## 3. SQL không bảo đảm thứ tự nếu thiếu ORDER BY

Ví dụ:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10;
```

Database có thể trả hàng theo:
- Thứ tự index scan.
- Thứ tự heap/table scan.
- Join order.
- Parallel worker.
- Execution plan khác sau ANALYZE hoặc khi statistics đổi.

Không có thứ tự nào trong số đó là contract SQL nếu không có `ORDER BY`.

### 3.1. Primary key không tự tạo ORDER BY

Bảng có primary key `order_id` không có nghĩa:

```sql
SELECT order_id FROM orders;
```

được bảo đảm trả tăng dần theo ID. Nếu cần tăng dần, viết:

```sql
SELECT order_id
FROM orders
ORDER BY order_id ASC;
```

### 3.2. Index không cam kết thứ tự kết quả

Một plan hiện tại có thể dùng index và tình cờ trả hàng theo thứ tự index. Sau khi thêm index khác, thay đổi statistics, nâng version hoặc đổi tham số, optimizer có thể chọn plan khác.

Test dựa trên thứ tự tình cờ sẽ dễ flaky.

### 3.3. ORDER BY không loại duplicate

```sql
SELECT status
FROM orders
ORDER BY status;
```

Vẫn có thể trả `PAID` nhiều lần. `ORDER BY` chỉ quy định thứ tự, không thay semantics bag.

### 3.4. ORDER BY chưa đủ nếu có tie

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC;
```

Nếu nhiều hàng có cùng `created_at`, DBMS không bảo đảm thứ tự tương đối của các hàng trong nhóm bằng nhau. Muốn sequence xác định, thêm tie-breaker:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC;
```

Nếu `order_id` là unique trong phạm vi kết quả, tổ hợp sort keys tạo thứ tự toàn phần (total order).

### 3.5. NULL ordering phải rõ khi contract cần

Quy tắc sắp xếp NULL khác nhau giữa DBMS. PostgreSQL hỗ trợ `NULLS FIRST` và `NULLS LAST`; các dialect khác có quy tắc mặc định hoặc cú pháp khác.

Để biểu diễn portable hơn, có thể đưa NULL flag vào sort:

```sql
SELECT order_id, due_at
FROM orders
ORDER BY
    CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
    due_at ASC,
    order_id ASC;
```

Câu trên đặt giá trị NULL cuối, rồi sắp xếp các giá trị không NULL tăng dần. Tie-breaker `order_id` làm thứ tự xác định nếu khóa này unique.

## 4. Chọn đúng cách so sánh cho từng mục tiêu kiểm thử

| Mục tiêu | Cách so sánh |
| --- | --- |
| Hai query trả cùng tập giá trị duy nhất | Set comparison |
| Hai query trả cùng các hàng và cùng số lần | Multiset/bag comparison |
| API cam kết sort order | Sequence comparison |
| API không cam kết thứ tự | Multiset comparison |
| Kiểm tra số lượng từng nhóm | Grouped counts |
| Kiểm tra top-N | Sequence theo sort keys rõ ràng |
| Kiểm tra kết quả aggregate | So sánh giá trị scalar/row theo type |
| Kiểm tra query rewrite | Multiset trước; sequence nếu ORDER BY là contract |

Ví dụ, refactor một query từ JOIN sang `EXISTS` có thể làm thay đổi số duplicate nếu query cũ vô tình nhân hàng. Cần xác định thay đổi đó là bug được sửa hay là hành vi tương thích cần giữ. Đừng tự động dùng DISTINCT để làm hai bên “giống nhau”.

## 5. Dữ liệu lab để thực hành so sánh

Các ví dụ PostgreSQL dưới đây tạo hai tập kết quả có duplicate, NULL và một số khác biệt có chủ ý. Chạy trong một session lab:

```sql
CREATE TEMP TABLE demo_expected_result (
    category TEXT,
    amount NUMERIC(10,2),
    note TEXT
);

CREATE TEMP TABLE demo_actual_result (
    category TEXT,
    amount NUMERIC(10,2),
    note TEXT
);

INSERT INTO demo_expected_result VALUES
    ('PAID', 10.00, 'ok'),
    ('PAID', 10.00, 'ok'),
    ('PENDING', 20.00, 'later'),
    ('CANCELED', 0.00, NULL),
    ('PAID', 15.00, 'adjusted');

INSERT INTO demo_actual_result VALUES
    ('PAID', 10.00, 'ok'),
    ('PENDING', 20.00, 'later'),
    ('PENDING', 20.00, 'later'),
    ('CANCELED', 0.00, NULL),
    ('PAID', 15.00, 'adjusted');
```

Hai bảng có cùng các bộ giá trị duy nhất:
- `PAID, 10.00, ok`
- `PENDING, 20.00, later`
- `CANCELED, 0.00, NULL`
- `PAID, 15.00, adjusted`

Nhưng số lần xuất hiện khác:
- Expected có hai hàng `PAID 10.00`.
- Actual có một hàng `PAID 10.00`.
- Actual có hai hàng `PENDING 20.00`, expected chỉ có một.

Đây là ví dụ mà set comparison sẽ bỏ sót lỗi, còn bag comparison phát hiện được.

## 6. So sánh set bằng EXCEPT hai chiều

Nếu chỉ quan tâm các hàng khác nhau, dùng `EXCEPT` theo cả hai hướng:

```sql
(
    SELECT category, amount, note
    FROM demo_expected_result

    EXCEPT

    SELECT category, amount, note
    FROM demo_actual_result
)
UNION ALL
(
    SELECT category, amount, note
    FROM demo_actual_result

    EXCEPT

    SELECT category, amount, note
    FROM demo_expected_result
);
```

Nếu kết quả rỗng, hai bên có cùng tập giá trị duy nhất theo semantics của `EXCEPT`.

### 6.1. Vì sao phải so sánh hai chiều?

Chỉ chạy:

```sql
SELECT ... FROM expected
EXCEPT
SELECT ... FROM actual;
```

chỉ tìm hàng có trong expected mà thiếu ở actual. Nó không phát hiện hàng thừa chỉ có ở actual.

So sánh hai chiều phát hiện cả:
- Hàng expected bị thiếu.
- Hàng actual thừa.

### 6.2. EXCEPT bỏ qua số lần lặp

Trong ví dụ lab, `EXCEPT` loại duplicate trước khi so sánh. Vì hai bảng có cùng tập giá trị duy nhất, kết quả hai chiều rỗng dù số lượng bản sao khác nhau.

Đây là lý do phải biết mình đang kiểm tra set hay multiset.

### 6.3. EXCEPT/INTERSECT khác nhau theo DBMS

PostgreSQL và một số DBMS hỗ trợ `EXCEPT`; Oracle truyền thống dùng `MINUS`; SQL Server hỗ trợ `EXCEPT`; MySQL có hỗ trợ toán tử tập hợp trong các phiên bản hiện đại. Cú pháp và hỗ trợ `ALL` khác nhau theo engine/version.

Đừng coi một câu so sánh tập hợp là portable tuyệt đối. Nếu bài kiểm thử phải chạy trên nhiều DBMS, kiểm tra dialect hoặc dùng phương pháp grouped counts ở phần sau.

## 7. So sánh multiset bằng EXCEPT ALL

PostgreSQL hỗ trợ `EXCEPT ALL`, giữ sự khác biệt về số lần xuất hiện:

```sql
(
    SELECT category, amount, note
    FROM demo_expected_result

    EXCEPT ALL

    SELECT category, amount, note
    FROM demo_actual_result
)
UNION ALL
(
    SELECT category, amount, note
    FROM demo_actual_result

    EXCEPT ALL

    SELECT category, amount, note
    FROM demo_expected_result
);
```

Kết quả biểu thị các bản sao thừa/thiếu theo từng hướng:
- Hàng `PAID, 10.00, ok` thừa một lần ở expected.
- Hàng `PENDING, 20.00, later` thừa một lần ở actual.

Nếu kết quả rỗng, hai bên bằng nhau theo multiset.

### 7.1. EXCEPT ALL xử lý duplicate như thế nào?

Nếu một hàng xuất hiện:
- 3 lần bên trái.
- 1 lần bên phải.

`EXCEPT ALL` để lại 2 lần bên trái. Nó trừ số lần xuất hiện, thay vì chỉ kiểm tra có/không.

### 7.2. Không có EXCEPT ALL ở mọi DBMS

Một số dialect chỉ hỗ trợ `EXCEPT`/`MINUS` theo semantics distinct, không có `ALL` tương ứng hoặc có cú pháp khác. Với bài test đa hệ quản trị, grouped counts là cách diễn đạt rõ và thường dễ chuyển hơn.

## 8. Cách portable: GROUP BY và so sánh số lần

Có thể gom mỗi hàng thành một nhóm và đếm số lần xuất hiện:

```sql
WITH expected_counts AS (
    SELECT
        category,
        amount,
        note,
        COUNT(*) AS occurrences
    FROM demo_expected_result
    GROUP BY category, amount, note
),
actual_counts AS (
    SELECT
        category,
        amount,
        note,
        COUNT(*) AS occurrences
    FROM demo_actual_result
    GROUP BY category, amount, note
)
SELECT
    e.category AS expected_category,
    e.amount AS expected_amount,
    e.note AS expected_note,
    e.occurrences AS expected_count,
    a.occurrences AS actual_count
FROM expected_counts AS e
FULL OUTER JOIN actual_counts AS a
    ON e.category IS NOT DISTINCT FROM a.category
   AND e.amount IS NOT DISTINCT FROM a.amount
   AND e.note IS NOT DISTINCT FROM a.note
WHERE COALESCE(e.occurrences, 0) <> COALESCE(a.occurrences, 0);
```

Đây là cú pháp PostgreSQL dùng `IS NOT DISTINCT FROM` để so sánh NULL an toàn. Kết quả liệt kê những bộ giá trị có multiplicity khác.

### 8.1. Vì sao GROUP BY giữ được duplicate?

GROUP BY gom các hàng có cùng giá trị thành một nhóm. `COUNT(*)` giữ lại số lần xuất hiện. Khi so sánh hai bảng đếm, multiplicity được bảo toàn.

### 8.2. Vì sao cần FULL OUTER JOIN?

- Chỉ có bên expected: hàng bị thiếu ở actual.
- Chỉ có bên actual: hàng thừa.
- Có ở cả hai nhưng count khác: multiplicity sai.

INNER JOIN sẽ bỏ các hàng chỉ tồn tại ở một bên, nên không đủ để so sánh toàn diện.

### 8.3. NULL-safe equality

Trong SQL, `NULL = NULL` không trả TRUE mà trả UNKNOWN. Vì vậy điều kiện JOIN thông thường:

```sql
e.note = a.note
```

không ghép hai hàng có note NULL.

PostgreSQL `IS NOT DISTINCT FROM` coi hai NULL là tương đương trong phép so sánh. Nếu dùng dialect không hỗ trợ cú pháp này, có thể viết điều kiện tương đương:

```sql
(
    e.note = a.note
    OR (e.note IS NULL AND a.note IS NULL)
)
```

Lặp quy tắc đó cho từng cột trong khóa so sánh. MySQL có toán tử null-safe `<=>`; các DBMS khác có cách biểu diễn riêng.

### 8.4. GROUP BY có semantics riêng cho kiểu dữ liệu

Các cột dùng trong grouping phải có semantics so sánh phù hợp. Với LOB, JSON, kiểu tùy chỉnh hoặc collation đặc biệt, có thể cần canonicalize hoặc so sánh ở application. Không phải mọi DBMS đều cho GROUP BY mọi kiểu dữ liệu.

## 9. So sánh theo khóa logic thay vì toàn bộ hàng

Đôi khi contract nói mỗi `order_id` chỉ có một hàng và các cột còn lại là payload. Khi đó, có thể so sánh theo khóa rồi kiểm tra từng field:

```sql
SELECT
    COALESCE(e.order_id, a.order_id) AS order_id,
    e.status AS expected_status,
    a.status AS actual_status,
    e.amount AS expected_amount,
    a.amount AS actual_amount
FROM expected_orders AS e
FULL OUTER JOIN actual_orders AS a
    ON e.order_id = a.order_id
WHERE e.order_id IS NULL
   OR a.order_id IS NULL
   OR e.status IS DISTINCT FROM a.status
   OR e.amount IS DISTINCT FROM a.amount;
```

Cách này kiểm tra:
- Khóa có thiếu/thừa không.
- Status có khác không.
- Amount có khác không.

### 9.1. Khi nào so theo key tốt hơn so toàn bộ row?

- Có primary/business key duy nhất.
- Cần thông báo field nào khác.
- Muốn phân loại missing row và changed row.
- Dữ liệu có nhiều cột nhưng chỉ một số cột thuộc contract.

### 9.2. Khi nào key comparison chưa đủ?

Nếu kết quả hợp lệ có nhiều hàng cùng key (ví dụ join một order với nhiều tags nhưng không trả tag ID), JOIN theo key có thể tạo Cartesian matching sai. Cần chọn khóa đủ xác định từng hàng kết quả hoặc so sánh multiset toàn bộ projection.

Không tự thêm DISTINCT hoặc group theo một key không unique để làm test dễ hơn.

## 10. So sánh sequence khi thứ tự có ý nghĩa

Nếu API cam kết:
- Đơn mới nhất trước.
- Sản phẩm theo thứ tự ưu tiên.
- Bước workflow theo position.
- Kết quả phân trang theo sort keys.
- Báo cáo theo ngày và mã.

thì phải so sánh thứ tự hàng.

Ví dụ hai kết quả:

```text
Expected: 101, 102, 103
Actual:   102, 101, 103
```

Multiset giống nhau nhưng sequence khác. Nếu contract yêu cầu tăng dần theo ID, actual sai.

### 10.1. So sánh vị trí bằng ROW_NUMBER

PostgreSQL:

```sql
WITH expected_ordered AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS position,
        order_id,
        status,
        amount
    FROM expected_orders
),
actual_ordered AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS position,
        order_id,
        status,
        amount
    FROM actual_orders
)
SELECT
    COALESCE(e.position, a.position) AS position,
    e.order_id AS expected_order_id,
    a.order_id AS actual_order_id,
    e.status AS expected_status,
    a.status AS actual_status
FROM expected_ordered AS e
FULL OUTER JOIN actual_ordered AS a
    ON a.position = e.position
WHERE e.position IS NULL
   OR a.position IS NULL
   OR e.order_id IS DISTINCT FROM a.order_id
   OR e.status IS DISTINCT FROM a.status
   OR e.amount IS DISTINCT FROM a.amount
ORDER BY position;
```

Nếu không có hàng khác biệt, hai sequence giống nhau theo thứ tự định nghĩa.

### 10.2. Cả hai phía phải dùng cùng ORDER BY contract

Nếu expected dùng `ORDER BY created_at, order_id` còn actual dùng `ORDER BY order_id`, so sánh vị trí sẽ phát hiện khác biệt. Nhưng cần xác định đó là lỗi thực sự hay hai query chưa được yêu cầu cùng một thứ tự.

### 10.3. Tie-breaker phải đủ duy nhất

`ORDER BY created_at DESC` chưa tạo total order nếu timestamp trùng. Thêm `order_id` hoặc một khóa unique khác:

```sql
ORDER BY created_at DESC, order_id DESC
```

Nếu không có tie-breaker, hai lần chạy có thể đổi vị trí các hàng đồng hạng mà vẫn hợp lệ theo SQL. Test sequence lúc ấy có thể flaky.

### 10.4. So sánh thứ tự bên ngoài database

Nếu application nhận result list, có thể so sánh list theo vị trí trực tiếp. Nhưng chỉ làm vậy khi query có ORDER BY đủ xác định. Nếu không, test nên so multiset thay vì giả định order.

## 11. Thứ tự trong nhóm tie: có thể cần so multiset theo nhóm

Có trường hợp business chỉ yêu cầu:
- Nhóm theo `priority`.
- Các hàng cùng priority không cần thứ tự.
- Nhóm priority cao phải xuất hiện trước nhóm thấp.

Khi ấy, không cần total order trên mọi cột. Có thể so:
1. Thứ tự của các nhóm priority.
2. Multiset của hàng trong mỗi nhóm.

Hoặc thêm tie-breaker nếu muốn contract mạnh hơn.

Ví dụ:

```sql
ORDER BY priority DESC
```

Nếu hai task cùng priority, thứ tự của chúng không được bảo đảm. Nếu UI không quan tâm, test có thể so bag trong từng priority group. Nếu UI cần ổn định, thêm `task_id ASC`.

## 12. DISTINCT có thể che lỗi duplicate

Giả sử query đúng phải trả hai order khác nhau cùng status:

```text
PAID
PAID
```

Nếu test làm:

```sql
SELECT DISTINCT status
FROM actual_query;
```

thì cả kết quả đúng và kết quả thiếu một order đều trở thành:

```text
PAID
```

Test đã mất thông tin cardinality.

### 12.1. Không canonicalize bằng Set khi duplicate có ý nghĩa

Trong Java:

```java
Set<Row> expectedSet = new HashSet<>(expectedRows);
Set<Row> actualSet = new HashSet<>(actualRows);
assertEquals(expectedSet, actualSet);
```

Đây là set comparison. Nó bỏ số lần lặp.

Trong Python:

```python
set(expected_rows) == set(actual_rows)
```

cũng bỏ multiplicity.

Nếu cần bag comparison, dùng frequency map/Counter.

### 12.2. DISTINCT chỉ đúng khi contract yêu cầu giá trị duy nhất

Nếu API thật sự trả danh sách category duy nhất, `DISTINCT` và set comparison có thể đúng. Nhưng phải kiểm tra semantics của endpoint, không thêm DISTINCT chỉ để test pass.

### 12.3. DISTINCT sau JOIN có thể che lỗi cardinality

Một JOIN sai có thể tạo duplicate. Thêm DISTINCT đôi khi làm kết quả nhìn “đẹp”, nhưng có thể che lỗi điều kiện JOIN hoặc làm tăng chi phí sort/hash. Hãy tìm nguyên nhân duplicate trước khi loại bỏ chúng.

## 13. So sánh giá trị NULL, empty và missing

Ba trạng thái có thể khác nhau:
- SQL `NULL`.
- Chuỗi rỗng `''`.
- Không có hàng/field không tồn tại trong JSON hoặc response.

Không gộp chúng thành một trạng thái “không có dữ liệu”.

### 13.1. NULL trong row comparison

`IS DISTINCT FROM` trong PostgreSQL so sánh NULL an toàn:

```sql
SELECT
    NULL IS DISTINCT FROM NULL AS same_null,
    NULL IS DISTINCT FROM '' AS null_vs_empty,
    NULL IS DISTINCT FROM 0 AS null_vs_zero;
```

Kết quả:
- NULL với NULL: không khác.
- NULL với chuỗi rỗng: khác.
- NULL với số 0: khác.

Trong test application, cần dùng assertion phù hợp với nullability.

### 13.2. Oracle và chuỗi rỗng

Oracle trong nhiều ngữ cảnh coi chuỗi ký tự độ dài 0 tương tự NULL. Vì vậy, khi chạy test đa DBMS, cùng một input `''` có thể được lưu/so sánh khác PostgreSQL hoặc SQL Server. Ghi rõ semantics theo dialect.

### 13.3. LEFT JOIN tạo NULL giả lập

Một hàng parent không có child tạo một row JOIN mà các cột child là NULL. Nó khác với child row tồn tại nhưng các field nullable đều NULL. Dùng child primary key NOT NULL để phân biệt “không có child” với “có child nhưng dữ liệu NULL”.

## 14. Kiểu dữ liệu và độ chính xác khi so sánh

Không phải mọi giá trị đều nên so bằng phép equals đơn giản.

### 14.1. DECIMAL/NUMERIC

Với tiền, dùng decimal exact. PostgreSQL `NUMERIC`, MySQL `DECIMAL`, SQL Server `DECIMAL`, Oracle `NUMBER` có precision/scale cụ thể.

Trong Java `BigDecimal`:
- `equals()` xem cả scale.
- `compareTo()` so giá trị số.

Ví dụ `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false, nhưng `compareTo()` trả 0. Test phải quyết định scale là một phần contract hay chỉ giá trị tiền.

### 14.2. FLOAT/DOUBLE

Số floating point có thể có sai số biểu diễn. Nếu query tính toán gần đúng, dùng tolerance:

\[
|actual - expected| \leq \epsilon_{abs}
\]

Hoặc tolerance tương đối:

\[
|actual - expected| \leq \epsilon_{rel}\times \max(|actual|, |expected|)
\]

Với giá trị gần 0, tolerance tuyệt đối thường quan trọng. Với giá trị rất lớn, tolerance tương đối có ích. Xử lý riêng NaN, Infinity và signed zero theo DBMS/runtime.

Không dùng tolerance để che lỗi làm tròn của tiền tệ; tiền thường cần DECIMAL/NUMERIC.

### 14.3. DATE, TIMESTAMP và TIME ZONE

- `DATE` biểu diễn ngày, không phải instant.
- Timestamp không timezone có thể mang local wall-clock value.
- `TIMESTAMP WITH TIME ZONE`/tương đương thường biểu diễn instant theo quy tắc DBMS.
- Precision timestamp khác nhau giữa DBMS/driver.

Nếu cùng instant được biểu diễn ở timezone khác nhau, có thể tương đương về thời điểm nhưng string hiển thị khác. Chuẩn hóa về instant/timezone xác định khi contract yêu cầu so thời điểm. Không tự đổi DATE thành UTC timestamp.

### 14.4. Text, collation và case

`'An'` và `'an'` có thể được so bằng nhau hoặc khác nhau tùy collation/case sensitivity. Accent sensitivity cũng khác. Test phải dùng collation của production hoặc quy tắc normalization đã công bố.

Không tự `LOWER()` cả hai bên chỉ để làm test pass nếu business yêu cầu phân biệt hoa/thường.

### 14.5. Unicode normalization

Hai chuỗi có thể nhìn giống nhau nhưng mã Unicode khác (ví dụ ký tự có dấu ghép sẵn và ký tự base + combining mark). Nếu hệ thống chuẩn hóa Unicode, test phải áp dụng đúng normalization form. Nếu không, byte/string equality có thể khác dù hiển thị giống.

### 14.6. CHAR padding

Một số DBMS/type có semantics padding cho `CHAR(n)`, khác `VARCHAR`. So sánh text phải xét kiểu cột và driver mapping. Đừng trim mọi string tự động nếu khoảng trắng cuối là dữ liệu có ý nghĩa.

## 15. JSON và dữ liệu cấu trúc

JSON có những quy tắc riêng:
- Thứ tự key trong object thường không mang ý nghĩa dữ liệu.
- Thứ tự phần tử array có ý nghĩa.
- `null` khác key bị thiếu.
- Number representation có thể khác nhau.
- Duplicate object keys có behavior parser khác nhau.

Ví dụ hai object:

```json
{"name":"An","role":"ADMIN"}
```

```json
{"role":"ADMIN","name":"An"}
```

Có thể tương đương về nội dung object dù thứ tự key khác. Nhưng hai array:

```json
["A","B"]
```

```json
["B","A"]
```

khác nhau nếu thứ tự array có ý nghĩa.

Nếu test JSON:
1. Parse thành cấu trúc dữ liệu.
2. Canonicalize object key order nếu contract xem key order không đáng kể.
3. Giữ nguyên array order.
4. Phân biệt missing field với explicit null.
5. So sánh numeric theo type/precision đã quy định.

Không so JSON text byte-for-byte nếu contract là structural equality; cũng không canonicalize array nếu order là dữ liệu.

## 16. So sánh query trước và sau khi tối ưu

Một use case quan trọng là thay query cũ bằng query mới:
- Subquery đổi thành JOIN.
- N+1 đổi thành select-in.
- OFFSET đổi thành keyset.
- ORM fetch strategy thay đổi.
- Aggregate chuyển từ application sang SQL.

### 16.1. Differential testing

Chạy cả query cũ và query mới trên cùng dataset/snapshot, rồi so kết quả theo contract:
- Bag nếu order không quan trọng.
- Sequence nếu order được yêu cầu.
- Key-based comparison nếu mỗi hàng có key duy nhất.
- Tolerance/type-aware compare cho numeric/time nếu phù hợp.

### 16.2. Dùng cùng snapshot

Nếu dữ liệu thay đổi giữa hai lần chạy, hai query có thể trả khác nhau dù logic tương đương. Với DBMS hỗ trợ transaction snapshot phù hợp, chạy cả hai trong cùng snapshot/transaction. Hoặc materialize input data bất biến cho test.

PostgreSQL READ COMMITTED có snapshot mới cho mỗi statement; nếu cần hai query nhìn cùng snapshot, dùng isolation phù hợp như REPEATABLE READ trong một transaction, theo contract của test. Cơ chế khác nhau giữa DBMS.

### 16.3. Không so hai query trên hai database đang đồng bộ bất đồng bộ

Replica có replication lag có thể trả snapshot khác nhau. Nếu mục tiêu là kiểm logic, chạy trên cùng database/snapshot hoặc dữ liệu fixture giống hệt. Nếu mục tiêu là kiểm consistency replication, đó là một test khác với tiêu chí riêng.

### 16.4. Phân biệt bug cũ với hành vi cũ

Query cũ có thể tạo duplicate sai do JOIN. Query mới loại duplicate đúng theo nghiệp vụ. Khi đó kết quả khác là thay đổi có chủ đích. Viết test theo contract nghiệp vụ, không coi query cũ là oracle tuyệt đối.

## 17. Fixture cần có để bắt lỗi duplicate và order

Một fixture tốt nên chứa các trường hợp có thể phân biệt semantics:

| Trường hợp | Vì sao cần |
| --- | --- |
| Hai hàng giống hệt projection | Bắt lỗi mất duplicate |
| Hai hàng cùng key nhưng khác payload | Bắt join/group sai |
| Parent không có child | Kiểm LEFT JOIN/empty collection |
| Parent có nhiều child | Kiểm multiplicity |
| Hai hàng có cùng sort key | Bắt thiếu tie-breaker |
| NULL và empty string | Phân biệt null semantics |
| Số decimal có scale khác | Kiểm precision |
| Timestamp cùng instant khác offset | Kiểm timezone |
| Unicode composed/decomposed | Kiểm normalization |
| Nhiều tenant có cùng local ID | Kiểm composite scope |
| Kết quả rỗng | Kiểm empty result |
| Một hàng duy nhất | Kiểm edge case cardinality |
| Hàng thừa và hàng thiếu | Kiểm diff hai chiều |

Nếu fixture chỉ có một hàng mỗi nhóm và không có ties/NULL, nhiều lỗi sẽ không xuất hiện.

## 18. So sánh trong application: multiset/frequency map

Nếu đã đọc kết quả vào application và tập vừa phải, dùng map đếm số lần từng row xuất hiện.

### 18.1. Python Counter

```python
from collections import Counter

expected = [
    ("PAID", 10, "ok"),
    ("PAID", 10, "ok"),
    ("PENDING", 20, "later"),
]

actual = [
    ("PAID", 10, "ok"),
    ("PENDING", 20, "later"),
    ("PENDING", 20, "later"),
]

expected_counts = Counter(expected)
actual_counts = Counter(actual)

missing_or_extra = expected_counts - actual_counts
extra_or_missing = actual_counts - expected_counts

assert expected_counts == actual_counts
```

`Counter` giữ multiplicity. Hai phép trừ giúp xem phần thừa ở mỗi phía. Với dữ liệu có `Decimal`, datetime hoặc JSON, cần normalize theo contract trước khi dùng làm key.

### 18.2. Java frequency map

```java
Map<RowKey, Long> expectedCounts =
    expectedRows.stream().collect(
        Collectors.groupingBy(
            RowKey::from,
            Collectors.counting()
        )
    );

Map<RowKey, Long> actualCounts =
    actualRows.stream().collect(
        Collectors.groupingBy(
            RowKey::from,
            Collectors.counting()
        )
    );

assertEquals(expectedCounts, actualCounts);
```

`RowKey` là kiểu canonical do ứng dụng định nghĩa. Không nên dùng trực tiếp entity ORM có lazy fields hoặc equals/hashCode không phản ánh đúng row projection.

### 18.3. Java BigDecimal cần canonicalization có chủ ý

Nếu `amount` là BigDecimal và scale không có ý nghĩa trong contract, `RowKey` có thể chuẩn hóa decimal bằng `stripTrailingZeros()` hoặc comparator numeric. Nếu scale có ý nghĩa, giữ nguyên. Không tự động normalize mọi decimal.

### 18.4. Sequence comparison bằng List

Khi order là contract:

```python
assert expected_rows == actual_rows
```

Hoặc Java:

```java
assertEquals(expectedRows, actualRows);
```

Điều này chỉ đúng khi hai query được chạy với cùng ORDER BY total và giá trị đã được normalize đúng type. Nếu không, test có thể phụ thuộc thứ tự không được đảm bảo.

## 19. So sánh kết quả lớn mà không nạp tất cả vào RAM

Với hàng triệu hoặc hàng chục triệu hàng, đọc cả hai kết quả thành list rồi tạo hai Counter có thể quá tốn bộ nhớ.

### 19.1. Nếu có total order, stream hai kết quả song song

Nếu cả hai query có cùng một `ORDER BY` toàn phần, có thể đọc tuần tự:
1. Lấy hàng kế tiếp bên expected.
2. Lấy hàng kế tiếp bên actual.
3. So sánh type/value.
4. Báo vị trí đầu tiên khác.
5. Dừng khi một bên hết hoặc có khác biệt.

Độ phức tạp thời gian O(n), bộ nhớ phụ O(1) nếu driver streaming thật.

### 19.2. Nếu chỉ cần multiset

Có thể:
- Sort cả hai theo toàn bộ canonical row values rồi stream compare.
- GROUP BY/count trong database.
- Dùng external sort trên disk.
- Chia partition theo key ổn định rồi so từng partition.
- Dùng hash/frequency map có kiểm soát nếu tập vừa đủ.

Sort canonical row phải giữ duplicate. Nếu cùng row xuất hiện ba lần, sorted stream vẫn phải có ba lần.

### 19.3. Partition phải giữ mọi bản sao của một giá trị cùng chỗ

Nếu hash partition một row theo hash của toàn bộ giá trị, các bản sao giống nhau sẽ vào cùng partition. Nếu partition theo một phần key không đủ phân biệt hoặc cắt theo page position tùy tiện, duplicate có thể bị chia sai và so sánh bỏ sót.

### 19.4. Hash/checksum chỉ là bằng chứng xác suất

Có thể tạo hash mỗi row rồi tổng hợp, nhưng:
- Hash collision về lý thuyết có thể xảy ra.
- Serialization không canonical có thể làm cùng giá trị ra bytes khác.
- Ghép cột bằng delimiter có thể gây ambiguity.
- NULL, type, timezone và numeric scale cần encoding rõ.
- Tổng hash có thể bỏ qua thứ tự hoặc multiplicity nếu thiết kế sai.

Hash hữu ích để sàng lọc nhanh hoặc xác định partition khác biệt, nhưng không nên là bằng chứng duy nhất cho phép so sánh chính xác nếu rủi ro false negative không chấp nhận được. Với yêu cầu chính xác, so hàng hoặc grouped counts.

### 19.5. COUNT và SUM không đủ để chứng minh hai tập bằng nhau

Hai kết quả có thể cùng:
- Số hàng.
- Tổng amount.
- MIN/MAX.
- Một vài checksum đơn giản.

nhưng vẫn khác từng hàng. Ví dụ `[1, 4]` và `[2, 3]` có cùng count và sum. Dùng aggregate để chẩn đoán, không coi vài aggregate là proof of equality.

## 20. So sánh schema và metadata ngoài row values

Hai result sets có thể chứa cùng giá trị nhưng khác schema:
- Tên cột/alias.
- Thứ tự cột.
- SQL type.
- Nullability.
- Precision/scale.
- Collation.
- Metadata driver.
- Tên field trong JSON/API.

Nếu consumer phụ thuộc schema, test cả metadata. Ví dụ đổi `amount NUMERIC(12,2)` thành `FLOAT` có thể giữ vài fixture values nhưng thay đổi precision và behavior downstream.

### 20.1. Column order

Trong SQL, consumer thường đọc cột theo label/tên; một số code dùng index `getLong(1)`. Nếu query đổi thứ tự cột, code theo index có thể sai dù values nhìn giống nhau. Kiểm schema hoặc dùng column labels ổn định.

### 20.2. Alias

Đổi alias `customer_name` thành `name` có thể phá mapper/JSON contract. So sánh row values không đủ phát hiện nếu test bỏ metadata.

### 20.3. Type coercion

`INTEGER` so với `BIGINT`, `DECIMAL` so với `DOUBLE`, `DATE` so với timestamp có thể tạo khác biệt ở application. Kiểm type theo contract, không chỉ stringify mọi giá trị rồi so.

## 21. Kiểm thử regression cho thứ tự

Nếu API cam kết sort, test cần kiểm:
- Sort direction ASC/DESC.
- Tie-breaker.
- NULL placement.
- Collation/case.
- Pagination boundaries.
- Duplicate rows.
- Stable ordering giữa các trang.

Ví dụ:

```sql
SELECT order_id, priority, created_at
FROM tasks
WHERE tenant_id = $1
ORDER BY
    priority DESC,
    created_at ASC,
    order_id ASC;
```

Test fixture nên có:
- Hai task cùng priority.
- Hai task cùng created_at.
- Task có priority NULL nếu schema cho phép.
- Task có order_id khác nhau.

Kiểm sequence expected chính xác theo sort contract.

### 21.1. Pagination và thứ tự

Một trang dùng:

```sql
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
```

Nếu sort key không unique, hàng có thể đổi vị trí giữa các request. Khi dùng keyset, cursor phải chứa toàn bộ sort keys cần thiết. Test cả boundary giữa trang một và trang hai để phát hiện duplicate/missing.

### 21.2. Không so page độc lập mà bỏ boundary

Trang 1 và trang 2 có thể mỗi trang riêng lẻ đều đúng, nhưng một hàng bị lặp ở cuối trang 1 và đầu trang 2. Test pagination phải ghép toàn bộ pages theo contract rồi kiểm:
- Không duplicate ngoài ý muốn.
- Không missing.
- Order toàn cục đúng.
- Cursor tiến về phía trước.

## 22. Differential testing khi thay đổi DBMS hoặc driver

Khi migrate PostgreSQL sang SQL Server/MySQL/Oracle, cùng SQL business logic có thể cho khác biệt:
- NULL ordering.
- Collation/case.
- Empty string.
- Timestamp precision/timezone.
- Decimal rounding.
- Boolean mapping.
- JSON semantics.
- `LIMIT`/pagination.
- Duplicate handling trong set operators.
- String padding.

### 22.1. Cùng fixture, cùng contract

Chạy cùng input và fixture tương đương trên hai DBMS. Normalize các khác biệt được chấp nhận theo contract, sau đó so bag/sequence phù hợp.

Không normalize rộng đến mức che khác biệt thực sự, ví dụ `LOWER()` mọi text có thể che lỗi phân biệt hoa/thường.

### 22.2. Dialect adapter trong test

Có thể dùng query tương ứng theo từng dialect nhưng so cùng một contract output:
- Cùng column names.
- Cùng semantic types.
- Cùng nullability.
- Cùng multiplicity.
- Cùng ordering khi được cam kết.

### 22.3. Test dữ liệu biên

Đặc biệt quan trọng khi đổi engine:
- `''` và NULL.
- Decimal rounding.
- Timestamp gần ranh giới precision.
- Unicode/collation.
- Duplicate trong UNION/JOIN.
- NULL trong sort key.
- `COUNT` và aggregate trên LEFT JOIN.

## 23. Metamorphic và property-based testing

Không phải lúc nào cũng có một expected result viết tay cho mọi input. Có thể kiểm các quan hệ phải đúng giữa các lần chạy.

### 23.1. Metamorphic property

Ví dụ query lọc theo tenant:
- Thêm hàng ở tenant 20 không được làm thay đổi kết quả tenant 10.
- Thêm một order không liên quan không được làm thay đổi count của customer khác.
- Thay đổi thứ tự insert không được thay đổi result sequence nếu ORDER BY quy định rõ.
- Chạy lại query trên snapshot không đổi phải cho cùng kết quả.
- Chuyển query sang implementation set-based phải giữ multiset theo contract.

### 23.2. Property-based generation

Sinh ngẫu nhiên:
- Nhiều parent/child.
- Parent không child.
- Duplicate projected values.
- NULL.
- Ties trong sort keys.
- Nhiều tenant.
- Decimal/timestamp biên.

Sau đó so query implementation với oracle đơn giản hoặc model trong application. Giữ seed để tái hiện lỗi.

### 23.3. Oracle model phải cùng semantics

Nếu model Python dùng set trong khi SQL giữ bag, test oracle có thể sai. Nếu model sort theo Unicode code point nhưng DB collation không giống, expected order có thể khác. Model phải mô phỏng đúng semantics cần kiểm.

## 24. Test query equivalence với EXCEPT và grouped counts

Một pattern regression hữu ích là materialize hai kết quả trên cùng fixture/snapshot:

```sql
CREATE TEMP TABLE demo_old_output AS
SELECT category, amount, note
FROM demo_expected_result;

CREATE TEMP TABLE demo_new_output AS
SELECT category, amount, note
FROM demo_actual_result;
```

Sau đó chạy bag diff bằng grouped counts hoặc `EXCEPT ALL` nếu DBMS hỗ trợ.

### 24.1. Khi dùng EXCEPT ALL

Ưu điểm:
- Ngắn.
- Thể hiện trực tiếp multiplicity.
- Có thể trả hàng dư theo từng hướng.

Đánh đổi:
- Không portable.
- Hỗ trợ kiểu dữ liệu/toán tử equality phụ thuộc DBMS.
- Có thể tốn sort/hash/memory/temp trên tập lớn.

### 24.2. Khi dùng grouped counts

Ưu điểm:
- Diễn đạt rõ số lần xuất hiện.
- Có thể mở rộng thành report expected_count/actual_count.
- Thường chuyển được giữa dialect nếu hỗ trợ GROUP BY/FULL JOIN hoặc thay thế tương đương.

Đánh đổi:
- Cần null-safe join.
- Phải group được các kiểu dữ liệu liên quan.
- Có thể tốn aggregate lớn.

### 24.3. Khi dùng key-based diff

Ưu điểm:
- Chỉ rõ missing/extra/changed theo khóa.
- Dễ đọc báo cáo lỗi.

Đánh đổi:
- Chỉ đúng nếu khóa thật sự unique ở cả hai kết quả.
- Không phát hiện multiplicity nếu key được chọn không đủ xác định một hàng.
- JOIN sai key có thể che hoặc nhân hàng.

## 25. Báo cáo khác biệt nên hữu ích cho người sửa lỗi

Một test chỉ báo `expected != actual` không đủ thông tin khi kết quả lớn.

Báo cáo tốt có:
- Loại so sánh: set, bag hay sequence.
- Số hàng expected/actual.
- Số giá trị unique.
- Hàng thiếu.
- Hàng thừa.
- Multiplicity expected/actual.
- Vị trí đầu tiên khác nếu sequence.
- Key/field khác nhau.
- Kiểu dữ liệu và normalization đã dùng.
- Query/request ID hoặc fixture seed.

Ví dụ báo cáo:

```text
Comparison mode: MULTISET
Expected rows: 5
Actual rows:   5
Distinct rows: 4

Difference:
  Row: ("PAID", 10.00, "ok")
  Expected occurrences: 2
  Actual occurrences:   1

Difference:
  Row: ("PENDING", 20.00, "later")
  Expected occurrences: 1
  Actual occurrences:   2
```

Ví dụ sequence:

```text
Comparison mode: ORDERED
First mismatch at position 3

Expected: (order_id=103, status="PAID")
Actual:   (order_id=102, status="PENDING")
```

## 26. Những anti-pattern khi so sánh kết quả

| Anti-pattern | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Chuyển cả hai kết quả thành Set | Mất duplicate | Frequency map/Counter |
| Dùng DISTINCT trước khi compare | Che multiplicity | Chỉ dùng nếu contract là unique set |
| So List khi SQL không ORDER BY | Phụ thuộc thứ tự tình cờ | Bag compare hoặc thêm ORDER BY |
| ORDER BY không có tie-breaker | Tie có thể đổi vị trí | Total order |
| Chỉ chạy EXCEPT một chiều | Không thấy hàng thừa | So hai chiều |
| Dùng EXCEPT để kiểm duplicate | EXCEPT bỏ duplicate | EXCEPT ALL hoặc grouped counts |
| INNER JOIN khi diff | Bỏ hàng thiếu/thừa | FULL OUTER JOIN hoặc hai anti-joins |
| Dùng `=` với NULL | NULL không match NULL | Null-safe comparison |
| So mọi giá trị bằng string | Mất type/precision/timezone | Type-aware canonicalization |
| Dùng BigDecimal.equals vô thức | Scale khác tạo false diff | Quy định scale/value semantics |
| So timestamp text | Offset/format khác | Compare instant/local time theo contract |
| LOWER mọi text | Che case-sensitive bug | Dùng đúng collation/contract |
| Sort chỉ theo timestamp | Ties không xác định | Thêm unique tie-breaker |
| Check count và sum rồi kết luận bằng nhau | Nhiều tập khác nhau có cùng aggregate | Compare rows/multiplicities |
| Hash-only equality | Collision/canonicalization risk | Hash sàng lọc, exact diff xác nhận |
| Chạy query cũ/mới ở snapshot khác | Data drift tạo diff giả | Cùng snapshot/fixture |
| Dùng query cũ làm oracle tuyệt đối | Có thể giữ bug cũ | Contract nghiệp vụ |
| Bỏ qua schema metadata | Cùng values nhưng type/alias đổi | Test metadata |
| Test từng page độc lập | Bỏ sót duplicate/missing qua boundary | Ghép và test toàn pagination |
| Normalize quá mức | Che sai khác thật | Chỉ normalize theo contract |

## 27. Quy trình so sánh kết quả SQL

### Bước 1 — Xác định contract

Ghi rõ:
- Grain: một hàng đại diện cho gì?
- Có duplicate hợp lệ không?
- Có yêu cầu order không?
- Nếu có, sort keys và tie-breaker nào?
- NULL, empty, type và precision được hiểu ra sao?
- Schema/column aliases có thuộc contract không?

### Bước 2 — Chọn comparison mode

- Set.
- Multiset.
- Sequence.
- Key-based field diff.
- Approximate numeric comparison nếu phù hợp.

### Bước 3 — Chuẩn bị fixture phân biệt được lỗi

Có duplicate, ties, NULL, empty, parent không child, nhiều tenant, dữ liệu biên và kết quả rỗng.

### Bước 4 — Chạy trong điều kiện có thể so sánh

Dùng cùng dataset/snapshot, cùng parameters, cùng timezone/collation nếu đó là điều kiện của contract. Không để hai query đọc hai trạng thái dữ liệu khác nhau mà không biết.

### Bước 5 — So cả hai chiều

Với set: EXCEPT hai chiều. Với bag: EXCEPT ALL hoặc grouped counts. Với sequence: so theo vị trí và cùng total ORDER BY. Với key: kiểm missing/extra và field changes.

### Bước 6 — Báo cáo diff cụ thể

Cho biết row, count, position hoặc field khác; tránh chỉ trả boolean.

### Bước 7 — Chạy thêm performance/plan tests

Result equivalence không chứng minh query mới nhanh hơn. Đo execution time, rows, buffers, network bytes, memory và plan riêng. Cũng không vì query nhanh hơn mà bỏ qua semantics.

## 28. Bài tập thực hành

Các bài PostgreSQL dùng `demo_expected_result` và `demo_actual_result` ở mục 5 trong cùng session. Một số bài cần tự tạo fixture bổ sung.

### Bài 1 — Set, bag và sequence
Với kết quả `A, A, B, C`, viết set, multiset và sequence tương ứng. Cho ví dụ hai kết quả bằng set nhưng khác bag.

### Bài 2 — SELECT duplicate
Tạo bảng có ba hàng cùng status `PAID`. So sánh SELECT thường với SELECT DISTINCT. Query nào giữ số lần xuất hiện?

### Bài 3 — UNION
Tạo hai nguồn cùng có giá trị `PAID`. So sánh UNION và UNION ALL. Giải thích multiplicity.

### Bài 4 — JOIN multiplication
Một customer có ba orders và hai addresses. JOIN cả hai collection có thể tạo bao nhiêu hàng? Vì sao đó không nhất thiết là dữ liệu nguồn bị duplicate?

### Bài 5 — Không có ORDER BY
Chạy query nhiều lần với/không có index. Vì sao thứ tự khác nhau không chứng minh database sai khi không có ORDER BY?

### Bài 6 — ORDER BY tie
Tạo 5 hàng cùng created_at. Viết ORDER BY có tie-breaker unique. Bỏ tie-breaker và giải thích vì sao test sequence có thể flaky.

### Bài 7 — EXCEPT một chiều
Chạy expected EXCEPT actual. Sau đó đảo chiều. Hàng nào được phát hiện ở mỗi hướng?

### Bài 8 — EXCEPT ALL
Chạy bag diff hai chiều trên fixture lab. Xác định row nào thừa/thiếu và multiplicity tương ứng.

### Bài 9 — Grouped counts
Viết CTE expected_counts và actual_counts, FULL OUTER JOIN, trả mọi row có count khác.

### Bài 10 — NULL-safe join
Thay một điều kiện IS NOT DISTINCT FROM bằng `=`. Quan sát hàng có note NULL có được match không. Viết biểu thức portable tương đương.

### Bài 11 — INNER vs FULL OUTER
Dùng INNER JOIN để so grouped counts. Tạo row chỉ có ở một bên. Vì sao INNER JOIN bỏ sót nó?

### Bài 12 — Key-based comparison
Tạo expected_orders/actual_orders có order_id unique. Viết diff báo missing, extra và amount/status khác.

### Bài 13 — Duplicate cùng key
Tạo kết quả có hai hàng cùng order_id nhưng khác tag. Vì sao join theo order_id đơn giản có thể không đủ để compare?

### Bài 14 — Sequence bằng ROW_NUMBER
Materialize hai query theo ORDER BY total. So sánh hàng tại từng position và tìm mismatch đầu tiên.

### Bài 15 — Ties trong sequence
Bỏ tie-breaker khỏi ROW_NUMBER ORDER BY. Tạo dữ liệu đồng hạng và giải thích tại sao kết quả vị trí không được cam kết.

### Bài 16 — Null ordering
Tạo due_at NULL và non-NULL. Viết ORDER BY đặt NULL cuối bằng CASE. So với cú pháp NULLS LAST trên PostgreSQL.

### Bài 17 — DISTINCT che bug
Xóa một trong hai duplicate của expected rồi compare bằng DISTINCT. Vì sao test không phát hiện lỗi?

### Bài 18 — BigDecimal scale
Trong Java, so sánh BigDecimal `1.0` và `1.00` bằng equals và compareTo. Chọn contract cho amount.

### Bài 19 — Float tolerance
So sánh hai kết quả floating point bằng absolute và relative tolerance. Xử lý trường hợp gần zero, NaN và Infinity.

### Bài 20 — Timestamp/timezone
Tạo cùng instant ở hai offset khác nhau. Chuẩn hóa về instant rồi compare. Phân biệt với DATE và local timestamp.

### Bài 21 — Collation/case
So sánh `An` và `an` trên collation case-sensitive và case-insensitive. Vì sao test phải chạy theo collation production?

### Bài 22 — JSON structural equality
So sánh hai JSON object khác thứ tự key và hai JSON array đảo phần tử. Canonicalize phần nào và giữ nguyên phần nào?

### Bài 23 — Differential query testing
Viết query cũ và query mới trên cùng snapshot. So multiset và báo diff. Tạo một bug duplicate để chứng minh test bắt được.

### Bài 24 — Regression order
Viết endpoint query cam kết `created_at DESC, order_id DESC`. Tạo test có timestamp ties và xác nhận sequence.

### Bài 25 — Pagination boundary
Lấy ba trang liên tiếp. Ghép lại rồi kiểm duplicate/missing và order toàn cục. Mô phỏng sort key thay đổi giữa các trang.

### Bài 26 — Python Counter
Viết test dùng Counter để compare hai list tuple có duplicate. In ra expected excess và actual excess.

### Bài 27 — Large result streaming
Giả sử hai kết quả đã sort theo cùng total order. Viết pseudo-code đọc song song và tìm mismatch đầu tiên với O(1) bộ nhớ phụ.

### Bài 28 — Hash/checksum
Thiết kế canonical row encoding và hash. Nêu ít nhất bốn rủi ro nếu chỉ so tổng hash/checksum rồi kết luận bằng nhau.

### Bài 29 — Cross-DBMS comparison
So cùng fixture trên PostgreSQL và SQL Server hoặc MySQL. Kiểm NULL, empty string, decimal, timestamp, collation và duplicate semantics.

### Bài 30 — Thiết kế framework comparison
Xây helper nhận hai result sets và mode `SET`, `MULTISET`, `ORDERED` hoặc `KEYED`. Quy định type normalization, null handling, diff report, fixture và cách chạy cùng snapshot. Viết test để helper không bỏ sót duplicate hoặc tie-order bug.

## 29. Checklist trước khi kết luận hai kết quả bằng nhau

### Semantics
- [ ] Đã xác định set, multiset hay sequence?
- [ ] Duplicate có ý nghĩa hay phải loại?
- [ ] Có ORDER BY nếu thứ tự thuộc contract?
- [ ] Sort keys tạo total order hoặc đã quy định tie groups?
- [ ] Grain/khóa logic của mỗi hàng rõ ràng?

### Giá trị
- [ ] NULL, empty và missing được phân biệt?
- [ ] Type/precision/scale được so đúng?
- [ ] Timestamp/timezone/precision rõ?
- [ ] Collation, case, Unicode và padding đúng?
- [ ] JSON object/array được so theo semantics?
- [ ] Numeric tolerance chỉ dùng khi contract cho phép?

### Phương pháp
- [ ] Set diff chạy hai chiều?
- [ ] Bag diff giữ multiplicity?
- [ ] FULL OUTER JOIN hoặc logic tương đương phát hiện hàng chỉ có một phía?
- [ ] NULL-safe comparison được dùng?
- [ ] Key comparison chỉ dùng khi key unique?
- [ ] Sequence comparison dùng cùng ORDER BY?

### Test và vận hành
- [ ] Expected/actual chạy trên cùng fixture hoặc snapshot?
- [ ] Fixture có duplicate, ties, NULL và empty result?
- [ ] Test pagination qua boundary?
- [ ] Diff report chỉ rõ hàng/count/position/field?
- [ ] Kết quả lớn được stream/external sort phù hợp?
- [ ] Hash/checksum không được coi là proof duy nhất?
- [ ] Schema metadata được kiểm khi thuộc contract?
- [ ] Performance được đo riêng với correctness?

## 30. Sơ đồ chọn phương pháp

```text
             HAI KẾT QUẢ SQL CẦN SO SÁNH
                          |
                          v
             Thứ tự có thuộc contract không?
                    /              \
                  Có                Không
                  |                   |
                  v                   v
          Có ORDER BY total?    Duplicate có ý nghĩa?
              /      \              /       \
            Có       Không         Có        Không
            |          |            |           |
            v          v            v           v
       Sequence    Chưa thể      Multiset      Set
       comparison  assert order  comparison   comparison
            |                       |
            +-----------+-----------+
                        |
                        v
              Chọn phương pháp diff
                 /       |        \
             EXCEPT   GROUP BY   App Counter/
              ALL     + counts   frequency map
                 \       |        /
                  +------+------+
                         |
                         v
             NULL/type/collation/precision
                         |
                         v
              Same snapshot + useful diff
                         |
                         v
              Performance test riêng biệt
```

## 31. Tổng kết

So sánh kết quả SQL phải tôn trọng semantics của dữ liệu. SQL `SELECT` mặc định giữ duplicate, nên một `Set` hoặc `DISTINCT` trong test có thể che mất hàng bị thiếu/thừa. Nếu không có `ORDER BY`, SQL không bảo đảm thứ tự; nếu có ties, cần tie-breaker để tạo thứ tự xác định. Vì vậy, hãy chọn rõ **set**, **multiset** hay **sequence** trước khi viết assertion.

Để so set, dùng `EXCEPT` hai chiều. Để so multiset, PostgreSQL có `EXCEPT ALL`; cách portable hơn là GROUP BY toàn bộ projection, đếm occurrences rồi FULL OUTER JOIN với phép so sánh NULL-safe. Để so sequence, gắn `ROW_NUMBER()` theo cùng một ORDER BY toàn phần rồi so từng vị trí. Nếu có khóa duy nhất, key-based diff giúp chỉ rõ missing, extra và field changes.

Ngoài duplicate và order, cần kiểm NULL, empty, type, decimal scale, floating tolerance, timezone, collation, Unicode và JSON semantics. Khi so query cũ/mới, chạy trên cùng snapshot hoặc fixture; khi kết quả lớn, stream hai dãy đã sort hoặc dùng grouped counts/external sort. Hash/checksum có thể hỗ trợ sàng lọc nhưng không thay thế so sánh chính xác.

Một test tốt không chỉ trả lời “khác hay giống”, mà còn cho biết **hàng nào, số lần bao nhiêu, ở vị trí nào và field nào khác**. Khi comparison mode khớp contract, fixture có duplicate/ties/NULL và báo cáo diff đủ rõ, việc kiểm thử query rewrite và gỡ lỗi result set sẽ đáng tin cậy hơn nhiều.
