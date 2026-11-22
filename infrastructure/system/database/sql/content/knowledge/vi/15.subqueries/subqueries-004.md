# ANY, SOME và ALL trong phép so sánh

Một truy vấn SQL không chỉ có thể so sánh một giá trị với **một giá trị khác**. Đôi khi yêu cầu là so sánh với **cả một tập giá trị** được trả về từ truy vấn con (*subquery*): “Giá sản phẩm này cao hơn **ít nhất một** chiếc điện thoại?”, “Mức lương này cao hơn **tất cả** mức lương của nhóm đối chiếu?”, hoặc “Mã đơn này có bằng **bất kỳ** mã nào trong danh sách loại trừ?”.

SQL cung cấp các từ khóa **`ANY`**, **`SOME`** và **`ALL`** để diễn đạt phép so sánh có **lượng từ** (*quantified comparison*). Những từ khóa này đứng sau một toán tử so sánh và trước một truy vấn con trả **một cột**:

```sql
expression comparison_operator ANY  (subquery)
expression comparison_operator SOME (subquery)
expression comparison_operator ALL  (subquery)
```

Hiểu đúng chúng quan trọng hơn thuộc cú pháp, bởi kết quả có thể bất ngờ khi truy vấn con trả về **0 dòng**, chứa **`NULL`** hoặc có nhiều giá trị trùng. Bài học thuộc chương **Truy vấn con** của Database SQL, lấy PostgreSQL làm môi trường thực hành chính và chỉ rõ nơi các hệ quản trị có khác biệt.

## 1. Ý tưởng nền tảng: so sánh với tập thay vì với một số duy nhất

Xét các giá trị đối chiếu `12` và `24`. Cùng một số `20` nhưng ba câu hỏi sau khác nhau:

| Câu hỏi | Diễn đạt | Kết quả |
|---|---|---|
| 20 có lớn hơn **một trong các** giá trị 12, 24? | `20 > ANY (...)` | `TRUE` vì `20 > 12` |
| 20 có lớn hơn **mọi** giá trị 12, 24? | `20 > ALL (...)` | `FALSE` vì `20 > 24` sai |
| 20 có lớn hơn **ít nhất một** giá trị 12, 24? | `20 > SOME (...)` | `TRUE`, tương đương `ANY` |

Trong ngôn ngữ logic:

- **`ANY` / `SOME`** diễn đạt **tồn tại ít nhất một** giá trị đối chiếu khiến phép so sánh đúng.
- **`ALL`** diễn đạt **mọi** giá trị đối chiếu đều phải khiến phép so sánh đúng.
- `SOME` chỉ là **từ đồng nghĩa** của `ANY` trong dạng so sánh này; không có sự khác nhau về số lượng dòng được yêu cầu.

```text
Giá trị cần xét: 20       Tập đối chiếu: {12, 24}

20 > ANY {12, 24}
    ├── 20 > 12  → TRUE  ──> chỉ cần một TRUE → TRUE
    └── 20 > 24  → FALSE

20 > ALL {12, 24}
    ├── 20 > 12  → TRUE
    └── 20 > 24  → FALSE ──> chỉ cần một FALSE → FALSE
```

Ví dụ PostgreSQL không cần bảng:

```sql
SELECT
    20 > ANY (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS greater_than_some,
    20 > SOME (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS greater_than_some_synonym,
    20 > ALL (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS greater_than_everyone;
```

Kết quả là `TRUE`, `TRUE`, `FALSE`. Đây là ví dụ của **truy vấn con không tương quan**: các tập giá trị bên phải không phụ thuộc vào dòng của truy vấn bên ngoài.

## 2. Cấu trúc cú pháp chính xác

### 2.1. Một toán tử đứng trước lượng từ

```sql
SELECT column_name
FROM outer_table
WHERE column_name > ANY (
    SELECT compared_value
    FROM inner_table
    WHERE ...
);
```

Đọc từ trái sang phải:

1. Lấy giá trị `column_name` ở dòng hiện tại của truy vấn ngoài.
2. Truy vấn con trả về một tập giá trị `compared_value`.
3. Dùng toán tử `>` so sánh giá trị ngoài với từng giá trị trong tập.
4. Kết hợp các kết quả theo lượng từ `ANY`/`SOME` hoặc `ALL`.

Các toán tử so sánh thông dụng:

| Dạng | Ý nghĩa khi tập đối chiếu có giá trị không `NULL` |
|---|---|
| `x = ANY (subquery)` | `x` bằng ít nhất một giá trị trong tập |
| `x <> ANY (subquery)` | `x` khác ít nhất một giá trị trong tập |
| `x > ANY (subquery)` | `x` lớn hơn ít nhất một giá trị trong tập |
| `x >= ANY (subquery)` | `x` lớn hơn hoặc bằng ít nhất một giá trị |
| `x < ANY (subquery)` | `x` nhỏ hơn ít nhất một giá trị |
| `x <= ANY (subquery)` | `x` nhỏ hơn hoặc bằng ít nhất một giá trị |
| `x = ALL (subquery)` | `x` bằng mọi giá trị trong tập |
| `x <> ALL (subquery)` | `x` khác mọi giá trị trong tập |
| `x > ALL (subquery)` | `x` lớn hơn mọi giá trị trong tập |
| `x >= ALL (subquery)` | `x` lớn hơn hoặc bằng mọi giá trị |
| `x < ALL (subquery)` | `x` nhỏ hơn mọi giá trị trong tập |
| `x <= ALL (subquery)` | `x` nhỏ hơn hoặc bằng mọi giá trị |

Phần bên phải thường là truy vấn con **trả đúng một cột** có kiểu so sánh được với biểu thức bên trái. Nó có thể trả **nhiều dòng**, chỉ một dòng hoặc không dòng nào.

### 2.2. `ANY` không thay thế toán tử

Không viết:

```sql
-- Không phải cú pháp của phép so sánh định lượng:
-- WHERE price_million ANY (SELECT price_million FROM ...);
```

Phải có toán tử:

```sql
WHERE price_million > ANY (
    SELECT price_million FROM comparison_lab_products
);
```

Đây cũng không phải lệnh `SELECT ANY(...)` để lấy một phần tử bất kỳ. Trong bài, `ANY` **kết hợp các kết quả so sánh**, không chọn một dòng mẫu ngẫu nhiên.

### 2.3. Phân biệt phép so sánh với truy vấn con vô hướng

Một truy vấn con vô hướng được dùng như một giá trị phải trả **không quá một dòng và một cột**:

```sql
-- Chỉ hợp lệ nếu inner_table thật sự trả tối đa một dòng.
SELECT *
FROM outer_table
WHERE amount > (SELECT one_amount FROM inner_table WHERE ...);
```

Nếu truy vấn con trả nhiều dòng, nhiều hệ quản trị sẽ báo lỗi ở dạng vô hướng. Với `ANY`/`ALL`, **nhiều dòng là điều được mong đợi**:

```sql
SELECT *
FROM outer_table
WHERE amount > ALL (
    SELECT one_amount
    FROM inner_table
    WHERE ...
);
```

Kết quả là **một giá trị logic theo dòng ngoài** (`TRUE`, `FALSE`, hoặc `UNKNOWN`), chứ không phải một phép JOIN tự tạo cột cho từng dòng con.

## 3. Dữ liệu mẫu: sản phẩm và mức giá

Để thấy khác biệt giữa “ít nhất một” và “tất cả”, sử dụng bảng `comparison_lab_products`, trong đó **mỗi dòng là một sản phẩm**.

| product_id | product_name | category | price_million | is_active |
|---:|---|---|---:|---|
| 1 | Laptop Basic | Laptop | 20.00 | TRUE |
| 2 | Laptop Pro | Laptop | 28.00 | TRUE |
| 3 | Laptop Max | Laptop | 35.00 | FALSE |
| 4 | Phone Basic | Phone | 12.00 | TRUE |
| 5 | Phone Pro | Phone | 24.00 | TRUE |
| 6 | Phone Draft | Phone | `NULL` | TRUE |
| 7 | Tablet Basic | Tablet | 7.00 | TRUE |
| 8 | Tablet Pro | Tablet | 18.00 | TRUE |
| 9 | Mouse | Accessory | 1.00 | TRUE |
| 10 | Keyboard | Accessory | 3.00 | TRUE |
| 11 | Gift Voucher | Gift | `NULL` | TRUE |

`price_million` có đơn vị **triệu đồng** và kiểu `NUMERIC(8,2)`; chẳng hạn 20.00 nghĩa là 20 triệu đồng. `NULL` nghĩa là giá chưa được xác định, **không đồng nghĩa 0 đồng**.

Ba giá trị trong danh mục `Phone` là:

```text
Phone Basic = 12
Phone Pro   = 24
Phone Draft = NULL
```

Để bắt đầu bằng phép so sánh hai giá trị rõ ràng, những ví dụ đầu sẽ **lọc bỏ giá `NULL` bên trong truy vấn con**:

```sql
SELECT q.price_million
FROM comparison_lab_products AS q
WHERE q.category = 'Phone'
  AND q.price_million IS NOT NULL;
-- Trả 12.00 và 24.00 (không cam kết thứ tự nếu thiếu ORDER BY).
```

Đoạn cuối bài có **script đầy đủ tạo bảng tạm và chèn dữ liệu**, để người học chạy các câu SQL này trong PostgreSQL.

## 4. `> ANY`: lớn hơn ít nhất một giá trị

Yêu cầu: “Liệt kê sản phẩm đang hoạt động có giá **cao hơn ít nhất một điện thoại đang có giá**.”

```sql
SELECT
    p.product_id,
    p.product_name,
    p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million > ANY (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

Kết quả:

| product_id | product_name | price_million |
|---:|---|---:|
| 1 | Laptop Basic | 20.00 |
| 2 | Laptop Pro | 28.00 |
| 5 | Phone Pro | 24.00 |
| 8 | Tablet Pro | 18.00 |

Vì danh sách giá điện thoại là `{12,24}`, điều kiện `p.price_million > ANY (...)` chỉ cần sản phẩm **đắt hơn giá 12** để có ít nhất một phép so sánh đúng.

Một lỗi suy luận thường gặp là hiểu `> ANY` thành “lớn hơn bất kỳ giá nào, tức lớn hơn tất cả”. Đó **không phải** ý nghĩa của `ANY`. Từ `ANY` ở đây có nghĩa **chỉ cần một phần tử phù hợp**.

### 4.1. Một sản phẩm có thể thuộc chính tập đối chiếu

Trong kết quả có `Phone Pro` giá 24: nó cao hơn **Phone Basic** giá 12, dù chính nó là một trong những điện thoại được dùng để so sánh. Truy vấn con không yêu cầu dòng đối chiếu phải khác dòng hiện tại trừ khi ta thêm điều kiện.

Nếu yêu cầu là “so với **các sản phẩm khác**”, phải xác định rõ có loại cùng `product_id` hay không. Với truy vấn con **tương quan**, có thể bổ sung `q.product_id <> p.product_id`; phần 10 sẽ giải thích.

### 4.2. Thay `ANY` bằng `SOME`

```sql
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million > SOME (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

Kết quả giống `> ANY`. Trong ngữ cảnh so sánh này, **`SOME` và `ANY` là hai cách viết cùng ý nghĩa**. `SOME` đôi khi đọc tự nhiên hơn với người mới học tiếng Anh, nhưng `ANY` thường xuất hiện nhiều hơn trong các ví dụ SQL.

## 5. `> ALL`: lớn hơn mọi giá trị

Yêu cầu khác: “Sản phẩm đang hoạt động nào có giá **cao hơn tất cả điện thoại đang có giá**?”

```sql
SELECT
    p.product_id,
    p.product_name,
    p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million > ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

Kết quả chỉ có:

| product_id | product_name | price_million |
|---:|---|---:|
| 2 | Laptop Pro | 28.00 |

Giá đối chiếu là 12 và 24; sản phẩm phải đắt hơn **cả hai**. `Laptop Basic` giá 20 không đạt vì 20 không lớn hơn 24. `Laptop Max` giá 35 đạt phép so sánh nhưng bị loại bởi `p.is_active = TRUE`.

```text
                      ANY              ALL
Laptop Basic 20   20 > 12 TRUE     20 > 12 TRUE
                  20 > 24 FALSE    20 > 24 FALSE
                  ─────────────    ─────────────
                  TRUE             FALSE

Laptop Pro   28   28 > 12 TRUE     28 > 12 TRUE
                  28 > 24 TRUE     28 > 24 TRUE
                  ─────────────    ─────────────
                  TRUE             TRUE
```

Khi tập đối chiếu **không rỗng**, không chứa `NULL` và phép so sánh thông thường có thứ tự nhất quán, `> ALL` tương ứng với yêu cầu “lớn hơn **giá trị lớn nhất** của tập”. Nhưng cách biến thành `MAX()` phải cẩn thận với **tập rỗng** và **`NULL`**, xem mục 12.

## 6. Không chỉ có toán tử `>`: ý nghĩa thay đổi theo toán tử

`ANY`/`ALL` không mang ý nghĩa “lớn hơn”. Chính **toán tử đứng trước** chúng quyết định kiểu điều kiện.

Cho tập `{12,24}`:

| Biểu thức | Kết quả | Giải thích |
|---|---|---|
| `20 > ANY {12,24}` | `TRUE` | 20 > 12 |
| `20 > ALL {12,24}` | `FALSE` | 20 không > 24 |
| `20 < ANY {12,24}` | `TRUE` | 20 < 24 |
| `20 < ALL {12,24}` | `FALSE` | 20 không < 12 |
| `24 >= ALL {12,24}` | `TRUE` | 24 ≥ 12 và 24 ≥ 24 |
| `12 <= ALL {12,24}` | `TRUE` | 12 ≤ 12 và 12 ≤ 24 |
| `24 = ANY {12,24}` | `TRUE` | Có giá trị bằng 24 |
| `24 = ALL {12,24}` | `FALSE` | 24 không bằng 12 |
| `24 <> ANY {12,24}` | `TRUE` | 24 khác 12 |
| `24 <> ALL {12,24}` | `FALSE` | 24 không khác chính 24 |

Các biểu thức ở bảng là **cách ký hiệu toán học ngắn**; trong SQL phải dùng truy vấn con:

```sql
SELECT
    24 = ANY (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS equals_some,
    24 <> ANY (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS differs_from_some,
    24 <> ALL (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS differs_from_every_value;
```

Kết quả lần lượt `TRUE`, `TRUE`, `FALSE`. Điểm cần nhớ: **`<> ANY` không có nghĩa “không nằm trong tập”**. Nó chỉ hỏi có ít nhất một phần tử **khác** giá trị đang xét hay không. Chỉ cần tập có hai giá trị khác nhau thì rất nhiều giá trị, kể cả giá trị thuộc tập, có thể làm `<> ANY` trả `TRUE`.

### 6.1. Bảng quy tắc đọc nhanh

| Cụm SQL | Cách đọc đúng |
|---|---|
| `= ANY` | Bằng **ít nhất một** |
| `<> ANY` | Khác **ít nhất một** |
| `< ANY` | Nhỏ hơn **ít nhất một** |
| `> ANY` | Lớn hơn **ít nhất một** |
| `= ALL` | Bằng **tất cả** |
| `<> ALL` | Khác **tất cả** |
| `< ALL` | Nhỏ hơn **mọi** |
| `> ALL` | Lớn hơn **mọi** |

Khi thấy `ANY` hoặc `ALL`, đừng suy luận theo từ khóa một mình; phải đọc **cả toán tử**.

## 7. Tập rỗng: trường hợp dễ bất ngờ nhất

Một truy vấn con có thể trả **0 dòng**, chẳng hạn danh mục `Camera` chưa có sản phẩm:

```sql
SELECT price_million
FROM comparison_lab_products
WHERE category = 'Camera';
-- 0 dòng trong dữ liệu mẫu.
```

Trong SQL, với phép so sánh định lượng thông thường:

- **`x op ANY (tập rỗng)` trả `FALSE`.** Không có phần tử nào để chứng minh “tồn tại ít nhất một”.
- **`x op ALL (tập rỗng)` trả `TRUE`.** Không có phần tử nào phản ví dụ cho yêu cầu “mọi phần tử đều thỏa”.

```sql
SELECT
    20 > ANY (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS any_empty,
    20 > ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS all_empty;
-- FALSE, TRUE.
```

`ALL` trên tập rỗng gọi là **đúng một cách rỗng** (*vacuous truth*) trong logic. Điều này có thể bất ngờ nếu diễn giải nghiệp vụ “giá cao hơn tất cả camera” thành “phải có camera để đối chiếu”.

### 7.1. Khi “không có dữ liệu để so sánh” là một trạng thái riêng

Giả sử chính sách yêu cầu sản phẩm phải đắt hơn **mọi** sản phẩm trong danh mục `Camera`, **và danh mục đó phải có ít nhất một giá hợp lệ**. Chỉ `> ALL` không đủ:

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.price_million IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Camera'
        AND q.price_million IS NOT NULL
  )
  AND p.price_million > ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Camera'
        AND q.price_million IS NOT NULL
  );
```

Với dữ liệu mẫu, truy vấn trả **0 dòng** vì điều kiện `EXISTS` không thỏa. Nó diễn đạt **đã có dữ liệu đối chiếu rồi mới so với tất cả**.

### 7.2. Ngay cả giá trị ngoài `NULL` cũng khác khi tập rỗng

```sql
SELECT
    CAST(NULL AS NUMERIC) > ANY (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS null_any_empty,
    CAST(NULL AS NUMERIC) > ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS null_all_empty;
-- FALSE và TRUE.
```

Kết quả **không phụ thuộc giá trị ngoài** khi tập đối chiếu rỗng, bởi không có phép so sánh riêng lẻ nào được thực hiện. Đây là lý do quan trọng để thêm `p.price_million IS NOT NULL` nếu yêu cầu nghiệp vụ chỉ cho phép sản phẩm đã có giá.

## 8. `NULL` và logic ba giá trị trong `ANY`/`ALL`

SQL không chỉ có `TRUE` và `FALSE`; phép so sánh liên quan tới `NULL` thường cho **`UNKNOWN`**, được nhiều SQL client hiển thị là `NULL`.

Trong các ví dụ tiếp theo, ta sử dụng toán tử số học so sánh thông thường, vốn trả `UNKNOWN` nếu một toán hạng là `NULL`.

### 8.1. Quy tắc kết hợp khi không có tập rỗng

**`ANY` / `SOME`:**

1. Có **ít nhất một phép so sánh `TRUE`** → kết quả `TRUE`.
2. Không có `TRUE` nhưng có ít nhất một `UNKNOWN` → kết quả `UNKNOWN`.
3. Mọi phép so sánh đều `FALSE` → kết quả `FALSE`.

**`ALL`:**

1. Có **ít nhất một phép so sánh `FALSE`** → kết quả `FALSE`.
2. Không có `FALSE` nhưng có ít nhất một `UNKNOWN` → kết quả `UNKNOWN`.
3. Mọi phép so sánh đều `TRUE` → kết quả `TRUE`.

**Tập rỗng** là trường hợp riêng: `ANY` trả `FALSE`, `ALL` trả `TRUE`.

| Biểu thức minh họa | `ANY` | `ALL` | Vì sao? |
|---|---|---|---|
| `5 > {2,8}` | `TRUE` | `FALSE` | Có một đúng, một sai |
| `5 > {8,10}` | `FALSE` | `FALSE` | Cả hai sai |
| `5 > {2,NULL}` | `TRUE` | `UNKNOWN` | Một đúng, một không biết |
| `5 > {8,NULL}` | `UNKNOWN` | `FALSE` | Một sai, một không biết |
| `5 > {NULL}` | `UNKNOWN` | `UNKNOWN` | Chỉ có phép so sánh không biết |
| `5 > {}` | `FALSE` | `TRUE` | Tập rỗng |

Ký hiệu `{...}` trong bảng là cách ghi **tập giá trị để giải thích**, không phải literal SQL ở mọi hệ quản trị.

### 8.2. Thử trực tiếp `NULL` trong PostgreSQL

```sql
SELECT
    5 > ANY (
        SELECT v FROM (VALUES (2), (NULL::integer)) AS s(v)
    ) AS true_and_unknown_any,
    5 > ALL (
        SELECT v FROM (VALUES (2), (NULL::integer)) AS s(v)
    ) AS true_and_unknown_all,
    5 > ANY (
        SELECT v FROM (VALUES (8), (NULL::integer)) AS s(v)
    ) AS false_and_unknown_any,
    5 > ALL (
        SELECT v FROM (VALUES (8), (NULL::integer)) AS s(v)
    ) AS false_and_unknown_all;
```

Kết quả lần lượt là `TRUE`, `NULL`, `NULL`, `FALSE`. Trong PostgreSQL, cách cast `NULL::integer` làm kiểu của cột mẫu rõ ràng.

### 8.3. Điều kiện `WHERE` chỉ nhận `TRUE`

Trong `WHERE`, những dòng có điều kiện là `FALSE` **hoặc** `UNKNOWN` đều bị loại. Vì vậy:

```sql
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.price_million > ALL (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
);
```

Truy vấn con trên trả **12, 24 và `NULL`**. Với `Laptop Pro` giá 28:

```text
28 > 12    → TRUE
28 > 24    → TRUE
28 > NULL  → UNKNOWN
--------------------------------
28 > ALL (12,24,NULL) → UNKNOWN
```

Do `WHERE` không giữ `UNKNOWN`, `Laptop Pro` bị loại dù nó cao hơn **tất cả mức giá điện thoại đã biết**. Để diễn đạt đúng yêu cầu “so với những điện thoại **có giá được xác định**”, phải nói rõ:

```sql
WHERE p.price_million > ALL (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
)
```

**Không tự động lọc `NULL` trong mọi bài toán**: loại `NULL` là một quyết định nghiệp vụ. Nếu dữ liệu thiếu cần khiến so sánh không xác định, phải giữ nó hoặc xử lý bằng trạng thái kiểm tra riêng.

### 8.4. `NULL` ngoài cũng cần xử lý

Nếu `p.price_million IS NULL`, phép so sánh của nó với một tập **không rỗng** giá trị số thông thường đều cho `UNKNOWN`. Vì vậy, khi yêu cầu là tìm sản phẩm có giá hợp lệ, nên viết tường minh:

```sql
WHERE p.price_million IS NOT NULL
  AND p.price_million >= ALL (...)
```

Điều này đặc biệt quan trọng khi truy vấn con có thể **rỗng**: nếu không có điều kiện `IS NOT NULL`, `NULL >= ALL (empty)` vẫn cho `TRUE`.

## 9. `= ANY`, `<> ALL`, `IN` và `NOT IN`

Đây là nhóm phép viết thường gặp nhất và cũng dễ bị đọc sai.

### 9.1. `= ANY` tương đương `IN (subquery)`

```sql
-- Cách 1: dùng lượng từ ANY.
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.price_million = ANY (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
)
ORDER BY p.product_id;
```

Có thể viết:

```sql
-- Cách 2: IN với truy vấn con.
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.price_million IN (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
)
ORDER BY p.product_id;
```

Với dữ liệu mẫu, cả hai trả **Phone Basic (4)** và **Phone Pro (5)**. `= ANY` có cùng ý nghĩa kiểm tra thành viên như `IN (subquery)`, gồm cả cách xử lý `NULL` theo logic ba giá trị.

### 9.2. `<> ALL` tương đương `NOT IN (subquery)`

Để chọn sản phẩm có giá **không trùng bất kỳ giá điện thoại nào**, với tập đối chiếu không `NULL`:

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.price_million IS NOT NULL
  AND p.price_million <> ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

Điều kiện `p.price_million <> ALL (...)` cũng có thể viết:

```sql
p.price_million NOT IN (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
)
```

Với bảng mẫu và không lọc `is_active`, các ID có giá không trùng `{12,24}` là **1, 2, 3, 7, 8, 9, 10**.

### 9.3. Bẫy `NULL` trong `NOT IN`

Nếu bỏ điều kiện lọc `q.price_million IS NOT NULL`, tập bên phải là `{12,24,NULL}`:

```sql
SELECT
    20 NOT IN (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Phone'
    ) AS not_in_with_null,
    20 <> ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Phone'
    ) AS not_equal_all_with_null;
-- Cả hai đều trả NULL/UNKNOWN.
```

Số 20 không bằng 12, không bằng 24, nhưng không biết nó **khác `NULL`** hay không. Khi tất cả giá trị đã biết đều khác 20 mà có thêm `NULL`, `NOT IN` và `<> ALL` trả `UNKNOWN`, không phải `TRUE`.

Trong `WHERE`, điều kiện này sẽ **không chọn** sản phẩm giá 20. Đây là lý do `NOT IN` với truy vấn con có thể chứa `NULL` thường gây kết quả bất ngờ.

### 9.4. Không thay `<> ALL` bằng `<> ANY`

So sánh:

```sql
SELECT
    24 <> ANY (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS different_from_some,
    24 <> ALL (
        SELECT v FROM (VALUES (12), (24)) AS s(v)
    ) AS different_from_every;
-- TRUE và FALSE.
```

24 **khác 12**, nên `<> ANY` là `TRUE`, dù 24 **có trong tập**. Nếu mục tiêu là “không thuộc danh sách”, dùng `NOT IN`/`<> ALL` (có xét `NULL`) hoặc `NOT EXISTS` phù hợp, **không dùng `<> ANY`**.

### 9.5. Phủ định lượng từ

Về logic ba giá trị của các toán tử so sánh thông thường:

```text
NOT (x = ANY S)   tương ứng   x <> ALL S
NOT (x > ANY S)   tương ứng   x <= ALL S
NOT (x > ALL S)   tương ứng   x <= ANY S
```

Các quan hệ trên giữ ý nghĩa `UNKNOWN` trong logic ba giá trị cho các phép so sánh thường dùng, miễn hai vế nói về **cùng tập S** và cùng kiểu so sánh. Đặc biệt:

```text
NOT (x <> ANY S)  không phải là x <> ALL S.
```

Mẹo đọc an toàn: **phủ định phép so sánh đồng thời đổi lượng từ** (`ANY` ↔ `ALL`) theo quy tắc De Morgan, thay vì chỉ thêm `NOT` theo cảm giác.

## 10. Truy vấn con tương quan: tập so sánh thay đổi theo dòng ngoài

Các truy vấn trước đối chiếu mọi sản phẩm với **cùng một tập giá điện thoại**. Nhưng nhiều yêu cầu phải so với những dòng **thuộc cùng nhóm** của sản phẩm hiện tại.

Ví dụ: “Tìm các sản phẩm đang hoạt động có giá **cao nhất trong từng danh mục**, cho phép đồng hạng.”

```sql
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million IS NOT NULL
  AND p.price_million >= ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = p.category
        AND q.is_active = TRUE
        AND q.price_million IS NOT NULL
  )
ORDER BY p.category, p.product_id;
```

**Điểm tạo tương quan** là:

```sql
q.category = p.category
```

`q` là alias bên trong; `p` là alias ở truy vấn ngoài. Với mỗi sản phẩm `p`, tập so sánh gồm **giá những sản phẩm đang hoạt động và có giá trong cùng danh mục**.

Kết quả:

| category | product_id | product_name | price_million |
|---|---:|---|---:|
| Accessory | 10 | Keyboard | 3.00 |
| Laptop | 2 | Laptop Pro | 28.00 |
| Phone | 5 | Phone Pro | 24.00 |
| Tablet | 8 | Tablet Pro | 18.00 |

`Laptop Max` giá 35 bị loại vì không còn hoạt động. Danh mục `Gift` chỉ có sản phẩm giá `NULL` nên không có hàng nào được chọn; điều kiện `p.price_million IS NOT NULL` loại nó trước khi xét `ALL`.

### 10.1. Vì sao dùng `>= ALL` mà không dùng `> ALL`?

Truy vấn con trên **bao gồm chính sản phẩm p** trong tập đối chiếu, vì nó cùng danh mục và đang hoạt động. Do đó, với giá đã xác định, `p.price_million > p.price_million` luôn `FALSE`. Nếu dùng `> ALL`, không có sản phẩm nào vượt qua phép so sánh với chính nó.

Muốn chọn mức cao nhất **kể cả chính nó**, dùng:

```sql
p.price_million >= ALL (...)
```

Sản phẩm cao nhất thỏa `>=` với mọi giá trong danh mục. Nếu có **hai sản phẩm cùng mức cao nhất**, cả hai đều được chọn: đây là kết quả hợp lý cho yêu cầu “tất cả sản phẩm đồng hạng cao nhất”.

### 10.2. Khi cần đúng một sản phẩm trong mỗi danh mục

`>= ALL` có thể trả **nhiều dòng** cho một danh mục khi có đồng hạng. Nếu nghiệp vụ cần **đúng một đại diện duy nhất**, phải thêm quy tắc phân xử như `product_id` nhỏ hơn đứng trước và dùng `ROW_NUMBER()` hoặc một chiến lược chọn dòng tương đương.

```sql
WITH ranked AS (
    SELECT
        product_id,
        product_name,
        category,
        price_million,
        ROW_NUMBER() OVER (
            PARTITION BY category
            ORDER BY price_million DESC, product_id ASC
        ) AS rn
    FROM comparison_lab_products
    WHERE is_active = TRUE
      AND price_million IS NOT NULL
)
SELECT product_id, product_name, category, price_million
FROM ranked
WHERE rn = 1
ORDER BY category;
```

Đây là **mục tiêu khác** với chọn mọi sản phẩm đồng hạng cao nhất. Không nên dùng `LIMIT 1` trên truy vấn toàn bảng nếu cần một đại diện **cho từng danh mục**.

### 10.3. Cần có ít nhất một sản phẩm đối chiếu **khác chính nó**

Giả sử bài toán là “giá của p cao hơn **mọi sản phẩm khác** trong danh mục”, nghĩa là loại chính p khỏi tập con:

```sql
SELECT p.product_id, p.product_name, p.category, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million IS NOT NULL
  AND p.price_million > ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = p.category
        AND q.product_id <> p.product_id
        AND q.is_active = TRUE
        AND q.price_million IS NOT NULL
  );
```

Nếu một danh mục chỉ còn **một sản phẩm có giá**, tập đối chiếu của nó rỗng và `> ALL` sẽ trả `TRUE`. Nếu yêu cầu thật sự cần có **ít nhất một đối thủ khác**, thêm `EXISTS` với cùng điều kiện để kiểm tra sự tồn tại:

```sql
AND EXISTS (
    SELECT 1
    FROM comparison_lab_products AS q
    WHERE q.category = p.category
      AND q.product_id <> p.product_id
      AND q.is_active = TRUE
      AND q.price_million IS NOT NULL
)
```

Việc loại chính dòng ngoài, yêu cầu nhóm có thành viên khác và xử lý đồng hạng là **ba quyết định khác nhau**. Không nên mặc nhiên gộp chúng thành một điều kiện.

## 11. Dùng `ANY`/`ALL` với dữ liệu nhân viên: cùng cấu trúc, khác câu hỏi

Trong một bảng nhân sự giả định `employees(employee_id, department, salary_million, is_active)`:

**Câu A — “Nhân viên nào có lương cao hơn ít nhất một người của phòng Kinh doanh?”**

```sql
SELECT e.employee_id, e.salary_million
FROM employees AS e
WHERE e.salary_million > ANY (
    SELECT s.salary_million
    FROM employees AS s
    WHERE s.department = 'Kinh doanh'
      AND s.salary_million IS NOT NULL
);
```

**Câu B — “Nhân viên nào có lương cao hơn tất cả người của phòng Kinh doanh?”**

```sql
SELECT e.employee_id, e.salary_million
FROM employees AS e
WHERE e.salary_million > ALL (
    SELECT s.salary_million
    FROM employees AS s
    WHERE s.department = 'Kinh doanh'
      AND s.salary_million IS NOT NULL
);
```

**Câu C — “Ai có lương thuộc nhóm cao nhất trong phòng của chính họ?”**

```sql
SELECT e.employee_id, e.department, e.salary_million
FROM employees AS e
WHERE e.salary_million IS NOT NULL
  AND e.salary_million >= ALL (
    SELECT s.salary_million
    FROM employees AS s
    WHERE s.department = e.department
      AND s.salary_million IS NOT NULL
  );
```

Câu C là **truy vấn tương quan** vì `s.department = e.department`. Những câu này minh họa cách nghĩ trên một schema giả định khác; script thực hành ở mục 18 chỉ tạo bảng sản phẩm.

Trong hệ thống thật, có thể cần lọc nhân viên còn hiệu lực và xác định lương hợp lệ ở **cả truy vấn ngoài và truy vấn trong**. Nếu dùng các nhóm khác nhau để so sánh vì quên điều kiện, SQL có thể đúng cú pháp nhưng sai câu hỏi nghiệp vụ.

## 12. Quan hệ với `MIN`, `MAX`: đúng khi nào, khác khi nào?

Với tập **không rỗng, toàn giá trị không `NULL`** và phép so sánh theo thứ tự bình thường:

| Dạng lượng từ | Tương đương về phép so sánh |
|---|---|
| `x > ANY S` | `x > MIN(S)` |
| `x >= ANY S` | `x >= MIN(S)` |
| `x < ANY S` | `x < MAX(S)` |
| `x <= ANY S` | `x <= MAX(S)` |
| `x > ALL S` | `x > MAX(S)` |
| `x >= ALL S` | `x >= MAX(S)` |
| `x < ALL S` | `x < MIN(S)` |
| `x <= ALL S` | `x <= MIN(S)` |

Ví dụ với tập giá Phone đã lọc `NULL`, là `{12,24}`:

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million > (
      SELECT MAX(q.price_million)
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

Với tập so sánh không rỗng và giá hợp lệ, kết quả của truy vấn trên giống `> ALL` trong mục 5: chỉ có `Laptop Pro` (`product_id = 2`).

### 12.1. Tập rỗng làm hai cách viết khác nhau

```sql
SELECT
    20 > ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS using_all,
    20 > (
        SELECT MAX(price_million)
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS using_max;
```

Trong PostgreSQL:

- `using_all` là **`TRUE`**, vì tập so sánh rỗng.
- `MAX(price_million)` trên tập rỗng trả **`NULL`**; `20 > NULL` cho **`UNKNOWN`**.

Vì vậy, **không được khẳng định `> ALL` luôn thay được bằng `> MAX` trong mọi trường hợp**.

### 12.2. `NULL` làm `MAX` và `ALL` có thể khác

`MAX` và `MIN` thường **bỏ qua `NULL`**. Trong khi đó, `ALL` vẫn phải kết hợp một phép so sánh với `NULL` thành `UNKNOWN` nếu không có phép so sánh nào đã `FALSE`.

Với tập `{12,24,NULL}`:

```sql
SELECT
    28 > ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Phone'
    ) AS all_including_null,
    28 > (
        SELECT MAX(price_million)
        FROM comparison_lab_products
        WHERE category = 'Phone'
    ) AS greater_than_max;
-- NULL/UNKNOWN và TRUE.
```

Để phép so sánh bằng `MAX` phản ánh ý nghĩa “lớn hơn **mọi giá đã biết**”, cần xác định tập giá đối chiếu phải có ít nhất một giá và không tính các giá `NULL`. Nếu nghiệp vụ xem giá `NULL` là lỗi chưa thể quyết định, không nên âm thầm bỏ qua.

### 12.3. Dùng `MIN`/`MAX` khi muốn lấy ngưỡng rõ ràng

Nếu yêu cầu là “giá sản phẩm cao hơn **giá điện thoại đắt nhất đã niêm yết**”, việc dùng `MAX` có thể mô tả nghiệp vụ tự nhiên:

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.price_million > (
    SELECT MAX(q.price_million)
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
);
```

Nhưng nếu không có điện thoại có giá, `MAX` trả `NULL` và truy vấn ngoài không chọn dòng nào. Đó có thể là hành vi mong muốn khác với `> ALL` trên tập rỗng; hãy quyết định có chủ ý.

## 13. Quan hệ với `EXISTS` và `NOT EXISTS`

`ANY`/`ALL` biểu diễn **một phép so sánh với tập giá trị**; `EXISTS`/`NOT EXISTS` biểu diễn **sự tồn tại của dòng** thỏa điều kiện.

### 13.1. `> ANY` và `EXISTS`

Yêu cầu: “Có ít nhất một điện thoại có giá thấp hơn giá sản phẩm p.”

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
        AND p.price_million > q.price_million
  )
ORDER BY p.product_id;
```

Với tập giá đã xác định, các sản phẩm được chọn giống truy vấn `> ANY` ở mục 4.

**Lưu ý logic:** `EXISTS` luôn trả `TRUE`/`FALSE`, trong khi `> ANY` có thể trả `UNKNOWN` do `NULL`. Khi dùng trong `WHERE`, cả `FALSE` và `UNKNOWN` đều không được giữ, nên hai cách có thể lọc **cùng những dòng** dù **giá trị biểu thức boolean** không hoàn toàn giống nhau trong các tình huống có `NULL`.

### 13.2. `> ALL` và “không tồn tại phản ví dụ”

“Giá của p lớn hơn mọi giá Phone hợp lệ” có thể đọc là “**không tồn tại** giá Phone hợp lệ nào **lớn hơn hoặc bằng** giá p”:

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active = TRUE
  AND p.price_million IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
        AND q.price_million >= p.price_million
  )
ORDER BY p.product_id;
```

Với giá nguồn và giá ngoài **không `NULL`**, điều kiện `NOT EXISTS` chọn cùng dòng như `p.price_million > ALL (các giá Phone hợp lệ)`. Tuy nhiên:

- Nếu tập Phone hợp lệ **rỗng**, `NOT EXISTS` là `TRUE`, giống `> ALL` trên tập rỗng.
- Nếu muốn có ít nhất một Phone, phải thêm `EXISTS`.
- Nếu chưa lọc `NULL`, không được thay máy móc vì các so sánh `UNKNOWN` không trở thành dòng phản ví dụ trong `WHERE` của truy vấn con.

### 13.3. `NOT EXISTS` thay cho `NOT IN` khi quan hệ được diễn đạt bằng dòng

Ví dụ: tìm sản phẩm có giá xác định **không trùng giá của điện thoại nào**:

```sql
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.price_million IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million = p.price_million
  )
ORDER BY p.product_id;
```

Nếu `q.price_million IS NULL`, phép so sánh `q.price_million = p.price_million` là `UNKNOWN`, nên dòng giá thiếu không tạo một giá **trùng**. Đây là cách diễn đạt nghiệp vụ “không có bản ghi điện thoại nào mang **cùng giá trị đã biết**”.

Nó có thể khác `NOT IN` khi danh sách có `NULL`. Không có phương án nào đúng tuyệt đối trong mọi nghiệp vụ; phải xác định “giá chưa biết” có được bỏ qua, gây lỗi hay khiến kết quả chưa xác định.

## 14. Trùng lặp, số dòng và `ORDER BY` trong truy vấn con

### 14.1. Các giá trị trùng không làm thay đổi lượng từ

Với toán tử so sánh thông thường, tập `{12,24}` và tập các dòng `{12,12,24}` cho cùng kết quả `20 > ANY`, `20 > ALL`:

- `ANY` chỉ cần có ít nhất một phép so sánh đúng.
- `ALL` chỉ cần mọi phép so sánh đúng.
- Lặp một phép so sánh giống nhau không đổi kết quả logic.

Vì thế, `SELECT DISTINCT price_million` bên trong truy vấn con thường **không cần chỉ để làm đúng ngữ nghĩa ANY/ALL**. Có thể cân nhắc tối ưu thực thi theo kế hoạch thật, nhưng không nên thêm `DISTINCT` như phản xạ mặc định.

### 14.2. `ORDER BY` trong tập đối chiếu không mang nghĩa “chọn giá đầu”

```sql
SELECT p.product_id
FROM comparison_lab_products AS p
WHERE p.price_million > ANY (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
    ORDER BY q.price_million DESC
);
```

`ANY` không dừng ở “giá đầu tiên được sắp”. Nó kiểm tra điều kiện tồn tại, không phải phép lấy dòng đầu. Trong câu hỏi này, `ORDER BY` của truy vấn con **không cần thiết để diễn đạt logic** và có thể tạo công việc thừa tùy bộ tối ưu.

Nếu mục tiêu thật sự là “so với **giá cao nhất**”, dùng `MAX`, hoặc `> ALL` khi đã quyết định xử lý tập rỗng/`NULL`. Không dùng `ORDER BY` như một cách gián tiếp thay thế lượng từ.

### 14.3. `LIMIT` trong truy vấn con làm thay đổi tập đang so sánh

```sql
WHERE p.price_million > ALL (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
    ORDER BY q.price_million DESC
    LIMIT 1
)
```

Với dữ liệu mẫu, tập bị giới hạn còn **một giá lớn nhất** là 24. Khi đó `> ALL` chỉ so với một giá duy nhất. Trong PostgreSQL, điều kiện có thể cho kết quả cùng với `> MAX` nếu nhóm có giá, nhưng đây là **một truy vấn con khác**: đã chủ động thay tập ban đầu bằng một tập được giới hạn.

Nếu không có `ORDER BY` phù hợp, `LIMIT 1` không đảm bảo chọn dòng nào. Với `NULL`, quy tắc sắp xếp `NULL` còn ảnh hưởng việc dòng nào được chọn.

## 15. Khác biệt PostgreSQL: `ANY (subquery)` và `ANY (array)`

PostgreSQL hỗ trợ hai hình thức có thể nhìn khá giống nhau:

**1. So sánh với các dòng của truy vấn con:**

```sql
SELECT 20 > ANY (
    SELECT v
    FROM (VALUES (12), (24)) AS t(v)
) AS subquery_any;
```

**2. So sánh với các phần tử của mảng PostgreSQL:**

```sql
SELECT 20 > ANY (ARRAY[12, 24]) AS array_any;
```

Hai ví dụ đều trả `TRUE`. Nhưng cần phân biệt:

| Hình thức | Bên phải là gì? | Ghi chú |
|---|---|---|
| `op ANY (SELECT ...)` | Truy vấn con trả một cột, nhiều dòng | Dạng được dạy chính trong chương **Truy vấn con** |
| `op ANY (ARRAY[...])` | Một **mảng** PostgreSQL | Dùng kiểu mảng; cú pháp tạo mảng và cơ chế suy kiểu của PostgreSQL |
| `op ALL (ARRAY[...])` | Một mảng PostgreSQL | Phải kiểm tra mọi phần tử theo quy tắc mảng |

Một ví dụ mảng rỗng:

```sql
SELECT
    20 > ANY (ARRAY[]::INTEGER[]) AS any_empty_array,
    20 > ALL (ARRAY[]::INTEGER[]) AS all_empty_array;
-- FALSE và TRUE.
```

**Không chuyển thẳng** ví dụ `ARRAY[...]` sang MySQL, SQL Server hay SQLite rồi coi là SQL chung. Những hệ đó có cơ chế dữ liệu dạng danh sách/mảng khác nhau hoặc không hỗ trợ cú pháp tương đương.

### 15.1. Mảng `NULL` và phần tử `NULL` không đồng nghĩa

Trong PostgreSQL, một **mảng rỗng** là khác với một **mảng có phần tử `NULL`**, và cũng khác với bản thân **giá trị mảng bằng `NULL`**. Ví dụ:

```sql
SELECT
    5 = ANY (ARRAY[]::INTEGER[]) AS empty_array_result,
    5 = ANY (ARRAY[NULL]::INTEGER[]) AS null_element_result,
    5 = ANY (NULL::INTEGER[]) AS null_array_result;
-- FALSE, NULL, NULL.
```

Đây là đặc điểm cần chú ý nếu ứng dụng truyền danh sách ID bằng tham số mảng. Đối với truy vấn con bảng quan hệ, hãy tập trung vào số dòng và `NULL` của **các giá trị trong cột truy vấn con**.

## 16. Khác biệt giữa các hệ quản trị

| Hệ quản trị | Hỗ trợ định lượng so sánh | Lưu ý |
|---|---|---|
| PostgreSQL | `ANY`, `SOME`, `ALL` với truy vấn con; còn có dạng mảng riêng | Logic ba giá trị, tập rỗng và cú pháp mảng cần phân biệt |
| MySQL | `ANY`, `SOME`, `ALL` trong so sánh với truy vấn con | Nên xác nhận kiểu và quy tắc chuyển đổi ngầm của các toán hạng |
| SQL Server | Có cú pháp so sánh với `ALL`, `ANY`, `SOME` | Chú ý kết quả `UNKNOWN` khi giá trị đối chiếu `NULL` |
| SQLite | Không hỗ trợ trực tiếp các toán tử định lượng `ANY`/`ALL` kiểu truy vấn con như PostgreSQL | Diễn đạt bằng `EXISTS`, `NOT EXISTS` hoặc các phép tổng hợp thích hợp |

Ví dụ tư duy chuyển truy vấn:

```sql
-- Ý nghĩa: có ít nhất một giá đối chiếu thấp hơn giá đang xét.
-- PostgreSQL / những hệ hỗ trợ quantified comparison:
WHERE p.price_million > ANY (
    SELECT q.price_million
    FROM products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
)
```

Một dạng dùng `EXISTS` tương ứng cho mục tiêu **lọc dòng**:

```sql
WHERE EXISTS (
    SELECT 1
    FROM products AS q
    WHERE q.category = 'Phone'
      AND q.price_million IS NOT NULL
      AND p.price_million > q.price_million
)
```

Trong khi `EXISTS` có sẵn ở nhiều hệ, cách viết kiểu dữ liệu, bí danh, truy vấn con tương quan và bộ tối ưu có khác biệt. **Tính di động** không chỉ là thay từ khóa mà còn phải kiểm thử `NULL`, tập rỗng và những phép chuyển kiểu ngầm có thể làm kết quả khác.

## 17. Hiệu năng và cách chọn cú pháp

### 17.1. Không mặc định truy vấn con tương quan luôn chạy như vòng lặp

Về mặt logic, có thể nghĩ mỗi dòng `p` đi tìm tập `q` để so sánh. Nhưng bộ tối ưu SQL **không nhất thiết thực thi đúng một truy vấn con độc lập cho từng dòng**. Nó có thể biến đổi hoặc dùng chiến lược join, semi-join, anti-join, aggregate, index scan tùy hệ quản trị và dữ liệu.

Vì vậy, không nên khẳng định `ANY` luôn chậm hơn `EXISTS`, hoặc `ALL` luôn chậm hơn `MAX`. Muốn biết thực tế cần xem kế hoạch của **truy vấn và dữ liệu cụ thể**.

### 17.2. Chỉ mục có thể giúp tìm tập đối chiếu

Với truy vấn thường lọc `q.category` rồi so sánh `q.price_million`, một chỉ mục phù hợp có thể hữu ích trên bảng lớn:

```sql
-- PostgreSQL: ví dụ thiết kế chỉ mục để xem xét.
CREATE INDEX idx_comparison_lab_category_price
ON comparison_lab_products (category, price_million);
```

Ví dụ trên chỉ minh họa cơ chế; với bảng thực hành 11 dòng, một quét bảng nhỏ có thể nhanh hơn dùng chỉ mục. Hãy cân nhắc tần suất truy vấn, tỷ lệ giá `NULL`, điều kiện `is_active` và kế hoạch thực tế.

### 17.3. Lọc đúng tập trước khi so sánh

Với câu hỏi “lớn hơn mọi mức giá **Phone đang niêm yết**”, chỉ rõ:

```sql
WHERE q.category = 'Phone'
  AND q.is_active = TRUE
  AND q.price_million IS NOT NULL
```

Trong ví dụ dữ liệu, các Phone đều đang hoạt động nên điều kiện `q.is_active` không đổi tập giá đã biết. Nhưng trên dữ liệu thật, bỏ nó có thể đưa sản phẩm đã ngừng bán vào mức đối chiếu.

Nên xem điều kiện tập đối chiếu là **một phần của định nghĩa câu hỏi**, không phải chỉ là mẹo cải thiện hiệu năng.

### 17.4. Giữ kiểu dữ liệu thống nhất

Nếu bên ngoài có giá kiểu số nhưng cột bên trong chứa chuỗi, phép so sánh có thể lỗi hoặc tự chuyển đổi theo quy tắc hệ quản trị. Giá nên được lưu dưới kiểu số có độ chính xác phù hợp như `NUMERIC`; thời điểm nên ở kiểu thời gian; ID không nên bị chuyển thành chuỗi khi không cần.

Khi dùng `ANY`/`ALL` với `NULL`, **độ rõ về ý nghĩa dữ liệu và quy tắc xử lý giá trị thiếu** thường quan trọng hơn việc rút ngắn cú pháp.

## 18. Script thực hành PostgreSQL

Chạy đoạn dưới đây trong một kết nối đến **database thực hành**. Bảng `comparison_lab_products` là **bảng tạm** và sẽ biến mất khi phiên PostgreSQL kết thúc.

```sql
CREATE TEMP TABLE comparison_lab_products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(30) NOT NULL,
    price_million NUMERIC(8, 2),
    is_active BOOLEAN NOT NULL
);

INSERT INTO comparison_lab_products
    (product_id, product_name, category, price_million, is_active)
VALUES
    (1,  'Laptop Basic', 'Laptop',   20.00, TRUE),
    (2,  'Laptop Pro',   'Laptop',   28.00, TRUE),
    (3,  'Laptop Max',   'Laptop',   35.00, FALSE),
    (4,  'Phone Basic',  'Phone',    12.00, TRUE),
    (5,  'Phone Pro',    'Phone',    24.00, TRUE),
    (6,  'Phone Draft',  'Phone',    NULL,  TRUE),
    (7,  'Tablet Basic','Tablet',    7.00, TRUE),
    (8,  'Tablet Pro',  'Tablet',   18.00, TRUE),
    (9,  'Mouse',       'Accessory', 1.00, TRUE),
    (10, 'Keyboard',    'Accessory', 3.00, TRUE),
    (11, 'Gift Voucher','Gift',      NULL,  TRUE);

SELECT product_id, product_name, category, price_million, is_active
FROM comparison_lab_products
ORDER BY product_id;
```

Vì bảng là `TEMP`, nếu chạy lại toàn bộ script trong **cùng kết nối** mà không xóa bảng, lệnh `CREATE TEMP TABLE` sẽ báo đã tồn tại. Có thể mở phiên học tập mới hoặc chủ động tạo tên khác. Không cần thay đổi một bảng sản phẩm thật để thực hành các phép so sánh.

### 18.1. Đối chiếu ba dạng `ANY`, `SOME`, `ALL`

```sql
SELECT
    p.product_id,
    p.product_name,
    p.price_million,
    p.price_million > ANY (
        SELECT q.price_million
        FROM comparison_lab_products AS q
        WHERE q.category = 'Phone'
          AND q.price_million IS NOT NULL
    ) AS higher_than_any_phone,
    p.price_million > SOME (
        SELECT q.price_million
        FROM comparison_lab_products AS q
        WHERE q.category = 'Phone'
          AND q.price_million IS NOT NULL
    ) AS higher_than_some_phone,
    p.price_million > ALL (
        SELECT q.price_million
        FROM comparison_lab_products AS q
        WHERE q.category = 'Phone'
          AND q.price_million IS NOT NULL
    ) AS higher_than_all_phones
FROM comparison_lab_products AS p
ORDER BY p.product_id;
```

Ở các sản phẩm có giá:

- Laptop Basic (20): `ANY = TRUE`, `SOME = TRUE`, `ALL = FALSE`.
- Laptop Pro (28): cả ba là `TRUE`.
- Phone Pro (24): `ANY = TRUE`, `SOME = TRUE`, `ALL = FALSE` vì điều kiện là **lớn hơn**, không phải **lớn hơn hoặc bằng** 24.
- Tablet Basic (7): cả ba là `FALSE`.
- Phone Draft và Gift Voucher (giá `NULL`): các kết quả là `NULL`/`UNKNOWN` vì tập Phone đã lọc `NULL` vẫn **không rỗng**.

### 18.2. Bắt buộc danh mục đối chiếu có ít nhất một giá

```sql
-- Chọn danh mục Camera (chưa có sản phẩm trong mẫu).
SELECT
    p.product_id,
    p.product_name
FROM comparison_lab_products AS p
WHERE p.is_active
  AND p.price_million IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Camera'
        AND q.price_million IS NOT NULL
  )
  AND p.price_million > ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Camera'
        AND q.price_million IS NOT NULL
  );
-- 0 dòng: không có tập giá Camera hợp lệ để đối chiếu.
```

### 18.3. Chọn sản phẩm đang hoạt động có giá cao nhất trong từng danh mục

```sql
SELECT p.category, p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active
  AND p.price_million IS NOT NULL
  AND p.price_million >= ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = p.category
        AND q.is_active
        AND q.price_million IS NOT NULL
  )
ORDER BY p.category, p.product_id;
```

Kết quả là Keyboard, Laptop Pro, Phone Pro và Tablet Pro; không có Gift Voucher do giá chưa được xác định.

## 19. Bài tập tự luyện

Sử dụng bảng `comparison_lab_products`. Với mỗi câu, hãy viết **bằng lời** giá trị ngoài được so với **tập nào**, lượng từ đòi **ít nhất một** hay **tất cả**, và có cần xử lý tập rỗng/`NULL` không.

### Bài 1 — `ANY` và `ALL` trên cùng tập

Tập đối chiếu là `{12, 24}`. Dự đoán kết quả của bốn biểu thức:

```text
20 > ANY {12,24}
20 > ALL {12,24}
28 > ANY {12,24}
28 > ALL {12,24}
```

Viết một câu SQL PostgreSQL dùng truy vấn con `VALUES` để kiểm tra.

### Bài 2 — Dùng `SOME`

Viết câu SQL trả các sản phẩm **đang hoạt động** có giá **nhỏ hơn ít nhất một giá điện thoại đã xác định**, dùng `SOME` và `ORDER BY product_id`. Dự đoán các mã sản phẩm.

### Bài 3 — Thêm `=` vào toán tử

So sánh `24 > ALL {12,24}` với `24 >= ALL {12,24}`. Giá trị 24 có vượt qua từng điều kiện không? Vì sao?

### Bài 4 — Bẫy `<> ANY`

Đánh giá `24 <> ANY {12,24}` và `24 <> ALL {12,24}`. Nếu yêu cầu là “giá sản phẩm **không thuộc tập `{12,24}`**”, biểu thức nào phù hợp và cần chú ý gì về `NULL`?

### Bài 5 — Tập rỗng

Đánh giá:

```sql
SELECT
    50 > ANY (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS any_result,
    50 > ALL (
        SELECT price_million
        FROM comparison_lab_products
        WHERE category = 'Camera'
    ) AS all_result;
```

Nếu quy định phải có ít nhất một Camera thì cần bổ sung điều kiện nào?

### Bài 6 — `NULL` trong tập Phone

Không lọc giá `NULL` của Phone. Dự đoán `28 > ALL (giá Phone)` và `28 > ANY (giá Phone)`. Giải thích bằng ba phép so sánh với 12, 24 và `NULL`.

### Bài 7 — `NOT IN` và `NOT EXISTS`

Vì sao số 20 có thể không vượt qua điều kiện `20 NOT IN (SELECT price_million FROM ... WHERE category='Phone')`, dù 20 khác hai mức giá 12 và 24? Viết câu `NOT EXISTS` diễn đạt “không có điện thoại **có giá bằng 20**”.

### Bài 8 — Cao nhất theo từng danh mục

Viết truy vấn tương quan tìm các sản phẩm đang hoạt động có giá bằng hoặc cao hơn **mọi sản phẩm đang hoạt động có giá khác** trong cùng danh mục. Dùng `>= ALL`, giữ các sản phẩm đồng hạng cao nhất, và loại giá `NULL`.

### Bài 9 — `> ALL` trên tập chỉ có một phần tử

Giả sử tập so sánh là `{18}`. Điều kiện `20 > ALL {18}` có nghĩa gì? Nó có khác `20 > 18` về giá trị logic không? Nếu tập ấy trở thành rỗng thì chuyện gì xảy ra?

### Bài 10 — `MAX` không luôn thay được `ALL`

Giải thích sự khác nhau giữa:

```sql
20 > ALL (SELECT price_million FROM comparison_lab_products
          WHERE category = 'Camera')
```

và:

```sql
20 > (SELECT MAX(price_million) FROM comparison_lab_products
      WHERE category = 'Camera')
```

### Bài 11 — Tập đối chiếu thay đổi theo dòng ngoài

Hãy giải thích vì sao `q.category = p.category` làm truy vấn con **tương quan**, và vì sao dùng `p.price_million > ALL (...)` mà **không loại chính p khỏi tập** sẽ không chọn được sản phẩm có giá xác định khi tập chứa p.

### Bài 12 — Chuyển sang `EXISTS`

Viết lại ý nghĩa “sản phẩm p đắt hơn **ít nhất một** điện thoại có giá xác định” bằng `EXISTS`. Nêu điều kiện để kết quả **lọc dòng trong `WHERE`** tương ứng với `> ANY`, và vì sao hai biểu thức boolean có thể khác nhau khi xuất hiện `NULL`.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:** `TRUE`, `FALSE`, `TRUE`, `TRUE`.

```sql
SELECT
    20 > ANY (SELECT v FROM (VALUES (12), (24)) AS s(v)) AS a,
    20 > ALL (SELECT v FROM (VALUES (12), (24)) AS s(v)) AS b,
    28 > ANY (SELECT v FROM (VALUES (12), (24)) AS s(v)) AS c,
    28 > ALL (SELECT v FROM (VALUES (12), (24)) AS s(v)) AS d;
```

**Bài 2:** Dùng `< SOME` (tương đương `< ANY`); Phone Pro giá 24 là mức lớn nhất, nên các sản phẩm hoạt động có giá nhỏ hơn 24 được chọn: **1, 4, 7, 8, 9, 10**.

```sql
SELECT p.product_id, p.product_name, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active
  AND p.price_million < SOME (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
  )
ORDER BY p.product_id;
```

**Bài 3:** `24 > ALL {12,24}` là `FALSE`, vì 24 không **lớn hơn** 24; `24 >= ALL {12,24}` là `TRUE`, vì 24 lớn hơn hoặc bằng cả hai giá trị.

**Bài 4:** `24 <> ANY {12,24}` là `TRUE` vì 24 khác 12; `24 <> ALL {12,24}` là `FALSE` vì 24 bằng chính nó trong tập. “Không thuộc tập” dùng `<> ALL`/`NOT IN` với quy tắc `NULL` đã xác định, hoặc `NOT EXISTS` theo điều kiện so sánh.

**Bài 5:** `any_result = FALSE`, `all_result = TRUE`. Muốn bắt buộc có ít nhất một Camera với giá hợp lệ, thêm `EXISTS` kiểm tra cùng tập đối chiếu.

**Bài 6:** `28 > 12` là `TRUE`, `28 > 24` là `TRUE`, `28 > NULL` là `UNKNOWN`; vì vậy `> ALL` cho `UNKNOWN`, nhưng `> ANY` cho `TRUE`.

**Bài 7:** `NOT IN` có thể cho `UNKNOWN` do tập chứa giá `NULL`. Có thể diễn đạt “không có giá điện thoại bằng 20”:

```sql
SELECT NOT EXISTS (
    SELECT 1
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone'
      AND q.price_million = 20
) AS no_phone_price_20;
-- TRUE.
```

**Bài 8:**

```sql
SELECT p.product_id, p.product_name, p.category, p.price_million
FROM comparison_lab_products AS p
WHERE p.is_active
  AND p.price_million IS NOT NULL
  AND p.price_million >= ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = p.category
        AND q.is_active
        AND q.price_million IS NOT NULL
  )
ORDER BY p.category, p.product_id;
```

Kết quả: **Keyboard (10)**, **Laptop Pro (2)**, **Phone Pro (5)**, **Tablet Pro (8)**.

**Bài 9:** Trên tập một phần tử, `20 > ALL {18}` tương đương `20 > 18` và là `TRUE`. Khi tập rỗng, `> ALL` vẫn `TRUE`; còn so sánh với một giá trị duy nhất chỉ có nghĩa khi giá trị đó thực sự tồn tại.

**Bài 10:** `> ALL` trên tập Camera rỗng là `TRUE`; `MAX` trên tập rỗng trả `NULL`, nên `20 > NULL` là `UNKNOWN`. Không thể thay hai cách viết mà bỏ qua tập rỗng.

**Bài 11:** Truy vấn con tham chiếu `p.category` của dòng ngoài, nên tập giá thay đổi theo từng `p`. Nếu tập chứa chính `p`, phép `p.price > p.price` là `FALSE`, khiến `> ALL` không thỏa; dùng `>= ALL` để cho phép giá bằng mức tối đa, hoặc loại chính p theo ID nếu nghiệp vụ thật sự yêu cầu so với người khác.

**Bài 12:**

```sql
SELECT p.product_id, p.product_name
FROM comparison_lab_products AS p
WHERE p.is_active
  AND EXISTS (
      SELECT 1
      FROM comparison_lab_products AS q
      WHERE q.category = 'Phone'
        AND q.price_million IS NOT NULL
        AND p.price_million > q.price_million
  )
ORDER BY p.product_id;
```

Với phép so sánh số thông thường, `EXISTS` là `TRUE` đúng khi có ít nhất một giá Phone làm phép `>` đúng. Trong điều kiện `WHERE`, các dòng được chọn tương ứng với `> ANY`; tuy nhiên `EXISTS` không trả `UNKNOWN`, còn `> ANY` có thể trả `UNKNOWN` nếu tập chứa `NULL`.

</details>

## 20. Bảng lỗi thường gặp

| Cách hiểu hoặc cách viết | Sai ở đâu? | Cách tiếp cận đúng |
|---|---|---|
| “`> ANY` là lớn hơn mọi giá” | `ANY` chỉ cần **một** phép so sánh đúng | Dùng `> ALL` nếu yêu cầu lớn hơn **tất cả** |
| “`SOME` khác `ANY`” | Hai từ là đồng nghĩa trong phép so sánh định lượng | Chọn một cách viết nhất quán |
| “`<> ANY` nghĩa là `NOT IN`” | Chỉ cần khác **một** phần tử | `<> ALL`/`NOT IN` hoặc `NOT EXISTS` |
| “`> ALL` trên tập rỗng là sai” | Không có phản ví dụ; SQL trả `TRUE` | Thêm `EXISTS` nếu phải có tập đối chiếu |
| “Giá ngoài `NULL` luôn làm `ALL` trả `NULL`” | `ALL(empty)` vẫn `TRUE` | Kiểm tra tập rỗng và thêm `IS NOT NULL` nếu cần |
| “`NULL` bên trong không ảnh hưởng `> ALL`” | Có thể làm kết quả `UNKNOWN` | Định nghĩa chính sách dữ liệu thiếu |
| “`NOT IN` bỏ qua `NULL` trong danh sách” | `NULL` có thể làm kết quả `UNKNOWN` | Lọc `NULL` có chủ đích hoặc dùng `NOT EXISTS` |
| “`> ALL` luôn bằng `> MAX`” | Khác khi tập rỗng hoặc có `NULL` | Chỉ thay khi đã xử lý các trường hợp biên |
| “`> ALL` dùng để lấy bản ghi giá cao nhất trong cùng nhóm” | Nếu tập gồm chính bản ghi đó, so sánh `>` với chính nó sai | Dùng `>= ALL` hoặc loại chính dòng |
| “Thêm `DISTINCT` là bắt buộc cho `ANY`/`ALL`” | Trùng giá trị không thay đổi logic lượng từ | Chỉ thêm khi có lý do riêng |
| “Truy vấn con `ORDER BY` quyết định giá được `ANY` thử trước” | Lượng từ không chọn dòng theo thứ tự | Bỏ sắp xếp thừa hoặc định nghĩa tập cần so |
| “Truy vấn con tương quan luôn chạy vật lý một lần trên mỗi dòng” | Bộ tối ưu có thể viết lại kế hoạch | Dùng `EXPLAIN` để quan sát hệ thực tế |
| “SQL nào cũng hỗ trợ `ANY(ARRAY[...])`” | Đây là cú pháp mảng riêng PostgreSQL | Phân biệt dạng mảng và dạng truy vấn con |
| “Tập con so sánh phải luôn có một dòng” | Truy vấn con có thể rỗng hợp lệ | Xác định ngữ nghĩa cho tập rỗng |

## 21. Quy trình chọn `ANY`/`SOME`/`ALL`

Trước khi dùng lượng từ trong SQL, hãy trả lời:

1. **Giá trị ngoài là gì?** Giá tiền, mức lương, ngày giờ, số lượng hay mã định danh?
2. **Tập đối chiếu đến từ đâu?** Cùng danh mục, cùng phòng, danh sách trạng thái hay bảng khác?
3. **Điều kiện là “ít nhất một” hay “tất cả”?** Chọn `ANY`/`SOME` hoặc `ALL` đúng lượng từ.
4. **Toán tử nào thể hiện đúng so sánh?** `=`, `<>`, `>`, `>=`, `<`, `<=` mang ý nghĩa rất khác nhau.
5. **Tập có thể rỗng không?** Nhớ `ANY(empty) = FALSE`, `ALL(empty) = TRUE`; cần thêm `EXISTS` nếu yêu cầu có ít nhất một giá trị đối chiếu.
6. **Có `NULL` không?** Định nghĩa việc bỏ qua, coi là chưa xác định hoặc báo lỗi dữ liệu, thay vì để logic ba giá trị tạo kết quả ngoài mong đợi.
7. **Truy vấn con có tương quan không?** Nếu tập phụ thuộc dòng ngoài, dùng alias rõ vai trò và đặt điều kiện đúng phía.
8. **Có so với chính dòng ngoài không?** Với tìm cực trị, `>= ALL` có thể phù hợp hơn `> ALL`.
9. **Cần trả mọi dòng đồng hạng hay chỉ một dòng?** `>= ALL` giữ tất cả dòng đạt mức cao nhất, `ROW_NUMBER` kèm khóa phân xử có thể chọn một dòng đại diện.
10. **Có cần chuyển cú pháp không?** Cân nhắc `IN`, `NOT EXISTS`, `MIN`, `MAX` khi chúng diễn đạt nghiệp vụ tự nhiên hơn, nhưng không bỏ qua `NULL`/tập rỗng.

Ba mẫu dễ nhớ:

```sql
-- 1. Lớn hơn ít nhất một giá điện thoại đã biết.
WHERE p.price_million > ANY (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone' AND q.price_million IS NOT NULL
)

-- 2. Lớn hơn tất cả giá điện thoại đã biết.
WHERE p.price_million > ALL (
    SELECT q.price_million
    FROM comparison_lab_products AS q
    WHERE q.category = 'Phone' AND q.price_million IS NOT NULL
)

-- 3. Đạt mức giá cao nhất trong cùng danh mục, có thể đồng hạng.
WHERE p.price_million IS NOT NULL
  AND p.price_million >= ALL (
      SELECT q.price_million
      FROM comparison_lab_products AS q
      WHERE q.category = p.category
        AND q.price_million IS NOT NULL
  )
```

**`ANY`/`SOME` trả lời “có ít nhất một giá trị thỏa so sánh không?”, còn `ALL` trả lời “mọi giá trị đều thỏa không?”.** Khi đọc chúng cùng toán tử, tập đối chiếu, quy tắc `NULL` và tình huống tập rỗng, bạn có thể diễn đạt những yêu cầu lọc phức tạp bằng truy vấn con một cách chính xác, dễ giải thích và kiểm chứng.
