# IF, CASE và cấu trúc điều kiện trong PL/pgSQL

Một chương trình xử lý đơn hàng không thể chỉ chạy các câu `INSERT`, `UPDATE` hoặc `SELECT` theo một đường cố định. Ứng dụng cần quyết định: hóa đơn chưa thanh toán thì có được phát hành không, số tiền âm có phải từ chối không, người dùng không có quyền thì báo lỗi thế nào, một bản ghi đã xử lý có nên bỏ qua khi yêu cầu được gửi lại không?

Trong PostgreSQL, **PL/pgSQL** cung cấp các cấu trúc điều khiển luồng để thực hiện quyết định ngay bên trong function, procedure, trigger hoặc khối `DO`. Hai nhóm nền tảng là:

- **`IF ... THEN ... ELSIF ... ELSE ... END IF`:** chọn nhánh theo những biểu thức Boolean, thích hợp để kiểm tra điều kiện, khoảng giá trị, quyền, dữ liệu `NULL` và những bất biến nghiệp vụ.
- **`CASE ... WHEN ... THEN ... ELSE ... END CASE`:** chọn một trong nhiều nhánh. Có **simple CASE** so một biểu thức với danh sách giá trị và **searched CASE** đánh giá nhiều điều kiện Boolean.

Điểm dễ nhầm là PostgreSQL còn có **biểu thức `CASE` của SQL**, thường nằm bên trong `SELECT`, `UPDATE`, `ORDER BY` và `INSERT`. Biểu thức này trả về một giá trị và kết thúc bằng `END`, còn **câu lệnh CASE trong PL/pgSQL điều khiển nhánh lệnh và kết thúc bằng `END CASE;`**.

```text
                        Một yêu cầu xử lý
                                |
                                v
                     Kiểm tra dữ liệu đầu vào
                           IF / ELSIF
                                |
             +------------------+------------------+
             |                  |                  |
          Bị thiếu          Không hợp lệ        Hợp lệ
             |                  |                  |
             v                  v                  v
       RETURN / lỗi        RAISE EXCEPTION   Kiểm tra trạng thái
                                                   |
                                                   v
                                            CASE trạng thái
                                                   |
                           +-----------------------+--------------------+
                           |                       |                    |
                         draft                   issued                paid
                           |                       |                    |
                         phát hành            giữ nguyên hoặc       từ chối đổi
                                               thanh toán          không hợp lệ
```

Bài học thuộc chương **PL/pgSQL** của module *Database Engine Relational PostgreSQL*. Tài liệu giải thích từ cú pháp cơ bản đến tình huống xử lý nghiệp vụ thực tế, bao gồm ví dụ SQL tự chạy, các trường hợp `NULL`, tìm hàng bằng `FOUND`, kiểm tra trạng thái dưới concurrency và bài tập có đáp án.

**Mục tiêu:**

1. Viết đúng cấu trúc `IF`, `ELSIF`, `ELSE`, `END IF`.
2. Phân biệt simple `CASE` và searched `CASE` trong PL/pgSQL.
3. Phân biệt `CASE` **statement** trong PL/pgSQL với `CASE` **expression** trong SQL.
4. Hiểu ba trạng thái logic của SQL: `TRUE`, `FALSE` và `NULL`.
5. Tránh lỗi do so sánh `= NULL`, `NOT IN` chứa NULL, nhánh không có `ELSE` và thứ tự ưu tiên điều kiện.
6. Dùng `SELECT ... INTO`, `FOUND`, `RAISE EXCEPTION`, `RETURN` để tạo function có luồng xử lý rõ.
7. Thiết kế kiểm soát chuyển trạng thái hóa đơn có `SELECT ... FOR UPDATE`.
8. Biết khi nào viết logic theo tập hợp bằng SQL `CASE` thay vì chạy vòng lặp PL/pgSQL từng hàng.

> **Phạm vi thực hành:** Các lệnh tạo dữ liệu sử dụng schema `plpgsql_cond_lab` trong một database thử nghiệm. Không chạy thao tác cập nhật hóa đơn mẫu trên hệ thống thật. Những câu lệnh `RAISE EXCEPTION` minh họa lỗi được đặt ở phần riêng hoặc viết dưới dạng comment để người học chủ động thử.

---

## 1. PL/pgSQL khác SQL ở điều khiển luồng

### 1.1. SQL mô tả thao tác với tập dữ liệu

SQL thường diễn đạt một phép tính trên nhiều hàng:

```sql
SELECT
    amount,
    CASE
        WHEN amount >= 1000 THEN 'large'
        WHEN amount >= 100 THEN 'medium'
        ELSE 'small'
    END AS amount_group
FROM invoices;
```

`CASE` trong câu `SELECT` này là **biểu thức** trả giá trị cho mỗi hàng. Nó không điều khiển việc chạy một loạt câu `UPDATE`, `INSERT` hoặc `RAISE` trong một stored function.

### 1.2. PL/pgSQL điều khiển các câu lệnh thực thi

```sql
CREATE FUNCTION example_amount_group(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'unknown';
    ELSIF p_amount >= 1000 THEN
        RETURN 'large';
    ELSIF p_amount >= 100 THEN
        RETURN 'medium';
    ELSE
        RETURN 'small';
    END IF;
END;
$function$;
```

Trong ví dụ này:

- `IF` quyết định câu lệnh nào được thực hiện.
- `RETURN` kết thúc function và trả giá trị.
- Các nhánh phía sau nhánh đã trả về sẽ không được chạy.
- Những câu lệnh nghiệp vụ phức tạp hơn có thể đặt trong từng nhánh.

### 1.3. PL/pgSQL không thay thế SQL

Thông thường:

- Dùng **SQL** để thao tác với hàng loạt bản ghi.
- Dùng **PL/pgSQL** để tổ chức thứ tự, điều kiện, retry policy ở mức phù hợp, validation và các thao tác gồm nhiều câu SQL.

Một function PL/pgSQL được viết rất dài không đương nhiên nhanh hơn một câu SQL `UPDATE ... CASE`. Đôi khi logic theo tập hợp trong SQL đơn giản, ít round-trip và hiệu quả hơn.

---

## 2. Khối PL/pgSQL cơ bản

### 2.1. Cấu trúc DECLARE, BEGIN, END

```sql
DO $block$
DECLARE
    v_amount numeric := 125.50;
    v_label text;
BEGIN
    v_label := 'unclassified';

    IF v_amount >= 100 THEN
        v_label := 'medium or larger';
    END IF;

    RAISE NOTICE 'amount=%, label=%', v_amount, v_label;
END;
$block$;
```

`DO` thực thi một khối code ẩn danh. Nó hữu ích cho thí nghiệm không cần lưu function. `RAISE NOTICE` đưa thông điệp ra client, không trả một result set như `SELECT`.

### 2.2. Các thành phần cú pháp

| Thành phần | Ý nghĩa |
|---|---|
| `DO $block$ ... $block$;` | Chạy một khối code PL/pgSQL ẩn danh |
| `DECLARE` | Khai báo biến cục bộ nếu cần |
| `BEGIN` | Bắt đầu phần lệnh của một khối PL/pgSQL |
| `END;` | Kết thúc khối PL/pgSQL |
| `:=` | Gán giá trị cho biến |
| `IF ... END IF;` | Điều khiển nhánh theo điều kiện |
| `RAISE NOTICE` | In thông điệp chẩn đoán |
| `RETURN` | Trả kết quả và kết thúc function tương ứng |

### 2.3. BEGIN của PL/pgSQL không phải BEGIN TRANSACTION

Hai cú pháp có cùng từ khóa nhưng mục đích khác:

```sql
DO $block$
BEGIN
    RAISE NOTICE 'This is a PL/pgSQL block';
END;
$block$;
```

`BEGIN ... END` trong PL/pgSQL chỉ **gom các câu lệnh** thành một khối. Nó **không tự bắt đầu một transaction mới** giống SQL `BEGIN; ... COMMIT;`.

Function PL/pgSQL thông thường chạy trong transaction của câu lệnh gọi nó. Không đưa `COMMIT` tùy tiện vào một function thường rồi cho rằng mỗi nhánh sẽ tự commit.

### 2.4. Dấu chấm phẩy

Ví dụ:

```sql
IF condition THEN
    statement_1;
    statement_2;
END IF;
```

- Các câu lệnh con có dấu `;`.
- `END IF;` cũng có `;`.
- Không viết `THEN;` như một câu lệnh.
- `ELSIF` là một phần cấu trúc IF, không phải một khối IF độc lập cần `END IF` riêng.

---

## 3. IF đơn giản: một nhánh có điều kiện

### 3.1. Cú pháp

```text
IF boolean_expression THEN
    statements;
END IF;
```

Nếu điều kiện là `TRUE`, PostgreSQL thực thi các câu lệnh trong nhánh. Nếu là `FALSE` hoặc `NULL`, nhánh đó bị bỏ qua.

### 3.2. Ví dụ kiểm tra số tiền âm

```sql
DO $block$
DECLARE
    v_amount numeric := -5;
BEGIN
    IF v_amount < 0 THEN
        RAISE NOTICE 'Invalid amount: %', v_amount;
    END IF;

    RAISE NOTICE 'Validation block finished';
END;
$block$;
```

`RAISE NOTICE` không dừng khối; thông điệp thứ hai vẫn được phát ra. Khi cần dừng toàn bộ thao tác không hợp lệ, dùng `RAISE EXCEPTION` hoặc `RETURN` theo hợp đồng function.

### 3.3. IF không bắt buộc có ELSE

Nếu chỉ cần làm gì đó khi đúng:

```sql
IF v_amount = 0 THEN
    RAISE NOTICE 'Zero amount';
END IF;
```

Không cần viết một `ELSE` rỗng.

### 3.4. Điều kiện phải là Boolean

Điều kiện có thể là:

```sql
IF v_amount > 0 THEN ...
IF v_status = 'paid' THEN ...
IF v_customer_id IS NULL THEN ...
IF v_is_active THEN ...
IF EXISTS (SELECT 1 FROM ...) THEN ...
```

Trong PL/pgSQL, không dùng số nguyên như Boolean kiểu ngôn ngữ C:

```sql
-- Không phải cách viết hợp lệ nếu v_count là INTEGER:
-- IF v_count THEN ...

-- Đúng:
-- IF v_count > 0 THEN ...
```

---

## 4. IF ... ELSE: hai con đường rõ ràng

### 4.1. Cú pháp

```text
IF condition THEN
    statements_when_true;
ELSE
    statements_when_not_true;
END IF;
```

Trong PL/pgSQL, “not true” bao gồm trường hợp điều kiện cho `FALSE` và `NULL`.

### 4.2. Thực hành với biến Boolean

```sql
DO $block$
DECLARE
    v_verified boolean := true;
BEGIN
    IF v_verified THEN
        RAISE NOTICE 'Account verified';
    ELSE
        RAISE NOTICE 'Account not confirmed';
    END IF;
END;
$block$;
```

### 4.3. Trường hợp NULL

```sql
DO $block$
DECLARE
    v_verified boolean := NULL;
BEGIN
    IF v_verified THEN
        RAISE NOTICE 'Verified';
    ELSE
        RAISE NOTICE 'Not verified or unknown';
    END IF;
END;
$block$;
```

Vì `v_verified` là `NULL`, nhánh `THEN` **không được chọn**; khối `ELSE` được chạy.

Đừng tự suy rằng `NULL` đồng nghĩa `FALSE` trong mọi biểu thức SQL. Chỉ trong ngữ cảnh chọn nhánh `IF`, PL/pgSQL không chọn nhánh khi điều kiện không phải `TRUE`.

### 4.4. Phân biệt FALSE và UNKNOWN khi cần

Nếu nghiệp vụ có ba trạng thái:

```sql
DO $block$
DECLARE
    v_verified boolean := NULL;
BEGIN
    IF v_verified IS TRUE THEN
        RAISE NOTICE 'Verified';
    ELSIF v_verified IS FALSE THEN
        RAISE NOTICE 'Explicitly unverified';
    ELSE
        RAISE NOTICE 'Verification status unknown';
    END IF;
END;
$block$;
```

Đây là cách rõ hơn khi quyền truy cập hoặc quy trình phê duyệt cần phân biệt “đã bị từ chối” và “chưa có thông tin”.

---

## 5. IF ... ELSIF ... ELSE: nhiều điều kiện

### 5.1. Cú pháp

```text
IF condition_1 THEN
    statements_1;
ELSIF condition_2 THEN
    statements_2;
ELSIF condition_3 THEN
    statements_3;
ELSE
    statements_default;
END IF;
```

PostgreSQL xét các nhánh **từ trên xuống**. **Nhánh đầu tiên có điều kiện TRUE được thực thi**; các nhánh sau không còn được xét trong lần đi qua IF đó.

### 5.2. Ví dụ phân nhóm tiền

```sql
CREATE FUNCTION plpgsql_cond_lab.classify_amount(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount < 0 THEN
        RAISE EXCEPTION 'Amount cannot be negative: %', p_amount
            USING ERRCODE = '22023';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSIF p_amount < 100 THEN
        RETURN 'SMALL';
    ELSIF p_amount < 1000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LARGE';
    END IF;
END;
$function$;
```

**Chú ý thứ tự:** phải kiểm tra `IS NULL` và số âm trước các nhóm tiền hợp lệ. Khi đã biết `p_amount >= 100` mà chưa tới 1000, không cần lặp lại điều kiện cận dưới trong mọi nhánh.

### 5.3. Thứ tự nhánh có thể làm sai logic

Sai:

```sql
IF p_amount < 1000 THEN
    RETURN 'BELOW_1000';
ELSIF p_amount < 100 THEN
    RETURN 'BELOW_100';
END IF;
```

Vì mọi số nhỏ hơn 100 cũng nhỏ hơn 1000, nhánh thứ hai **không bao giờ được chọn** cho giá trị không NULL.

Đúng khi cần các nhóm riêng:

```sql
IF p_amount < 100 THEN
    RETURN 'BELOW_100';
ELSIF p_amount < 1000 THEN
    RETURN 'FROM_100_TO_999';
ELSE
    RETURN 'AT_LEAST_1000';
END IF;
```

### 5.4. ELSIF, không phải một ELSE chứa IF ngầm

`ELSIF` là cú pháp phổ biến. PostgreSQL cũng chấp nhận biến thể viết `ELSEIF` trong PL/pgSQL. Để mã nhất quán và dễ đọc, tài liệu này dùng `ELSIF`.

Nếu thực sự lồng một `IF` mới sau `ELSE` thì phải đóng **hai** cấu trúc:

```sql
IF first_condition THEN
    RAISE NOTICE 'first';
ELSE
    IF second_condition THEN
        RAISE NOTICE 'second';
    END IF;
END IF;
```

Đoạn trên không giống một chuỗi `ELSIF` đơn về mặt tổ chức khối, dù có trường hợp cho kết quả tương tự.

---

## 6. Trường hợp Boolean NULL và logic ba giá trị

Đây là nền tảng quyết định đúng trong PL/pgSQL.

### 6.1. SQL có ba trạng thái Boolean

| Biểu thức | Kết quả |
|---|---|
| `5 > 3` | TRUE |
| `5 < 3` | FALSE |
| `NULL::integer > 3` | NULL |
| `NULL::integer = NULL::integer` | NULL |
| `NULL::integer IS NULL` | TRUE |
| `NULL::integer IS NOT NULL` | FALSE |

`NULL` thể hiện dữ liệu **không biết/không có**, không phải số 0 hoặc chuỗi rỗng.

### 6.2. IF NULL không chọn THEN

```sql
DO $block$
DECLARE
    v_result boolean;
BEGIN
    v_result := NULL::integer = 10;

    IF v_result THEN
        RAISE NOTICE 'TRUE';
    ELSE
        RAISE NOTICE 'FALSE or UNKNOWN';
    END IF;
END;
$block$;
```

Kết quả thông báo là `FALSE or UNKNOWN`.

### 6.3. Vì sao = NULL sai?

```sql
-- Không dùng để kiểm tra dữ liệu thiếu:
-- IF p_customer_id = NULL THEN ...

-- Đúng:
-- IF p_customer_id IS NULL THEN ...
```

Toán tử `=` trên toán hạng NULL thông thường trả UNKNOWN, nên điều kiện không thành TRUE.

### 6.4. IS TRUE, IS FALSE, IS NOT TRUE

| Giá trị x | `x IS TRUE` | `x IS FALSE` | `x IS NOT TRUE` |
|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE |
| FALSE | FALSE | TRUE | TRUE |
| NULL | FALSE | FALSE | TRUE |

Nếu quy tắc là “chỉ cho phép khi được xác nhận TRUE”, có thể viết:

```sql
IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;
```

Điều này từ chối cả FALSE và NULL, phù hợp một số quy tắc **fail closed**.

### 6.5. IS DISTINCT FROM xử lý NULL rõ ràng

```sql
SELECT
    NULL::text IS DISTINCT FROM 'paid' AS different,
    NULL::text IS NOT DISTINCT FROM NULL::text AS same_null,
    'paid'::text IS DISTINCT FROM 'paid'::text AS same_text;
```

Kết quả tương ứng `true`, `true`, `false`.

Khi so dữ liệu cũ và mới có thể NULL, `IS DISTINCT FROM` thường rõ hơn `<>`:

```sql
IF NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE NOTICE 'Status has changed';
END IF;
```

Đoạn trên thích hợp trong một **UPDATE trigger** có `NEW` và `OLD`. Không sao chép vào một function thường mà chưa khai báo các biến này.

### 6.6. AND, OR và NULL

Một số quy tắc quan trọng:

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| TRUE | NULL | NULL | TRUE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |
| TRUE | FALSE | FALSE | TRUE |

`NOT NULL` cũng là `NULL`, không phải TRUE.

### 6.7. NOT IN chứa NULL

```sql
SELECT 7 NOT IN (1, 2, NULL) AS is_other;
```

Kết quả là **NULL**, không phải TRUE. Với danh sách có NULL, logic `NOT IN` có thể khiến `IF` bỏ qua nhánh ngay cả khi giá trị so sánh không bằng bất kỳ giá trị non-NULL nào.

Nếu dùng subquery để kiểm tra không tồn tại bản ghi, nhiều trường hợp `NOT EXISTS` an toàn về nghĩa hơn `NOT IN` với tập có NULL.

### 6.8. COALESCE không phải lúc nào cũng đúng

```sql
IF COALESCE(p_approved, false) THEN
    ...
END IF;
```

Đây là một chính sách **coi NULL như FALSE**, có thể phù hợp. Nhưng nếu cần phân biệt “chưa xác minh” với “bị từ chối”, `COALESCE` đã làm mất thông tin. Chính sách phải được quyết định trước khi chọn hàm.

---

## 7. Điều kiện kết hợp và dấu ngoặc

### 7.1. Nhiều điều kiện

```sql
IF p_amount > 0
   AND p_status = 'issued'
   AND p_tenant_id IS NOT NULL THEN
    RAISE NOTICE 'Eligible for payment';
END IF;
```

### 7.2. Ưu tiên logic

Trong SQL, `NOT`, `AND` và `OR` có thứ tự ưu tiên theo quy tắc cú pháp của PostgreSQL. Một câu không có ngoặc có thể khác ý người viết.

Ví dụ:

```sql
IF p_is_admin
   OR p_is_owner AND p_is_active THEN
    ...
END IF;
```

Nhìn tổng quát, `AND` gắn chặt hơn `OR`, nên điều kiện có ý nghĩa:

```sql
IF p_is_admin
   OR (p_is_owner AND p_is_active) THEN
    ...
END IF;
```

Nếu yêu cầu là **ai cũng phải active**, phải viết:

```sql
IF (p_is_admin OR p_is_owner)
   AND p_is_active THEN
    ...
END IF;
```

Hai quy tắc **không tương đương**. Dùng ngoặc để diễn đạt rõ policy.

### 7.3. Điều kiện thừa

```sql
IF p_amount > 0 AND p_amount <> 0 THEN
    ...
END IF;
```

Với NUMERIC thông thường, `p_amount > 0` đã bao hàm `p_amount <> 0`. Những điều kiện thừa làm code dài và khó đọc mà không tăng tính chính xác.

### 7.4. Không dựa vào short-circuit để che phép toán nguy hiểm

Khi lập trình, nhiều người giả định điều kiện phía sau `AND` hoặc `OR` sẽ không bao giờ được đánh giá nếu vế đầu đủ quyết định. SQL optimizer có quyền biến đổi nhiều biểu thức và thứ tự đánh giá không phải hợp đồng chung để bảo vệ mọi biểu thức có lỗi.

Rủi ro:

```sql
-- Không dùng thứ tự AND như một bảo đảm tổng quát:
-- WHERE denominator <> 0
--   AND numerator / denominator > 10
```

Với phép chia, cách an toàn hơn là định nghĩa kết quả khi mẫu số 0:

```sql
SELECT
    numerator / NULLIF(denominator, 0)
FROM ...
```

Trong PL/pgSQL, có thể tổ chức **những statement riêng biệt bằng IF** để chặn trước khi thực hiện phép chia:

```sql
IF p_denominator = 0 OR p_denominator IS NULL THEN
    RAISE EXCEPTION 'Invalid denominator'
        USING ERRCODE = '22023';
END IF;

v_ratio := p_numerator / p_denominator;
```

Đoạn này giả định `v_ratio` và các tham số đã được khai báo. Sự phân tách thành hai câu lệnh diễn đạt rõ validation trước calculation.

---

## 8. Simple CASE statement trong PL/pgSQL

Simple `CASE` phù hợp khi một biến cần được đối chiếu với **các giá trị rời rạc**.

### 8.1. Cú pháp

```text
CASE test_expression
    WHEN value_1 [, value_2 ...] THEN
        statements_1;
    WHEN value_3 THEN
        statements_2;
    ELSE
        statements_default;
END CASE;
```

`test_expression` được xác định một lần cho cấu trúc simple CASE; các `WHEN` so giá trị của nó với các biểu thức tương ứng theo quy tắc so sánh của PostgreSQL.

### 8.2. Ví dụ phân nhánh theo trạng thái

```sql
DO $block$
DECLARE
    v_status text := 'issued';
BEGIN
    CASE v_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Document can be edited';
        WHEN 'issued' THEN
            RAISE NOTICE 'Document is ready for payment';
        WHEN 'paid' THEN
            RAISE NOTICE 'Document has been paid';
        ELSE
            RAISE NOTICE 'Unknown or unsupported status';
    END CASE;
END;
$block$;
```

Kết quả là một thông báo cho nhánh `issued`. Các nhánh còn lại không chạy.

### 8.3. Một WHEN có nhiều giá trị

PL/pgSQL simple CASE hỗ trợ nhiều giá trị trong một `WHEN`:

```sql
DO $block$
DECLARE
    v_status text := 'draft';
BEGIN
    CASE v_status
        WHEN 'draft', 'issued' THEN
            RAISE NOTICE 'Still in pre-payment workflow';
        WHEN 'paid' THEN
            RAISE NOTICE 'Payment complete';
        WHEN 'void' THEN
            RAISE NOTICE 'Document void';
        ELSE
            RAISE NOTICE 'Other status';
    END CASE;
END;
$block$;
```

Nên gom các giá trị vào một nhánh khi chúng **thực sự có cùng xử lý nghiệp vụ**, không chỉ để giảm số dòng.

### 8.4. Simple CASE khác IF nhiều điều kiện

Khi muốn chọn theo một thuộc tính `status`:

```sql
CASE v_status
    WHEN 'draft' THEN ...
    WHEN 'issued' THEN ...
    WHEN 'paid' THEN ...
    ELSE ...
END CASE;
```

thường gọn hơn:

```sql
IF v_status = 'draft' THEN
    ...
ELSIF v_status = 'issued' THEN
    ...
ELSIF v_status = 'paid' THEN
    ...
ELSE
    ...
END IF;
```

Nhưng simple CASE **không diễn đạt trực tiếp các khoảng** như “amount từ 100 đến dưới 1000” chỉ bằng `WHEN 100..1000` theo cú pháp này. Với khoảng và điều kiện phối hợp, dùng searched CASE hoặc IF.

---

## 9. Searched CASE statement trong PL/pgSQL

Searched CASE xét **mỗi WHEN là một điều kiện Boolean**.

### 9.1. Cú pháp

```text
CASE
    WHEN boolean_expression_1 THEN
        statements_1;
    WHEN boolean_expression_2 THEN
        statements_2;
    ELSE
        statements_default;
END CASE;
```

### 9.2. Ví dụ phân nhóm khoảng tiền

```sql
DO $block$
DECLARE
    v_amount numeric := 750;
BEGIN
    CASE
        WHEN v_amount IS NULL THEN
            RAISE NOTICE 'Missing amount';
        WHEN v_amount < 0 THEN
            RAISE NOTICE 'Invalid negative amount';
        WHEN v_amount < 100 THEN
            RAISE NOTICE 'Small';
        WHEN v_amount < 1000 THEN
            RAISE NOTICE 'Medium';
        ELSE
            RAISE NOTICE 'Large';
    END CASE;
END;
$block$;
```

Với `v_amount=750`, nhánh `Medium` được chọn.

### 9.3. Giống ELSIF nhưng không giống hoàn toàn

Searched CASE và IF/ELSIF đều kiểm tra điều kiện từ trên xuống, chọn nhánh đầu tiên TRUE. Tuy nhiên, khác biệt quan trọng:

- `IF` **có thể không có ELSE** mà không báo lỗi.
- PL/pgSQL `CASE` **không có ELSE và không nhánh nào match** sẽ phát sinh lỗi `CASE_NOT_FOUND`.

Nếu có khả năng không match và đó là hành vi hợp lệ, hãy viết `ELSE NULL;` hoặc một nhánh xử lý có chủ đích.

### 9.4. Các điều kiện chồng lấn

```sql
CASE
    WHEN v_amount >= 100 THEN
        RAISE NOTICE 'At least 100';
    WHEN v_amount >= 1000 THEN
        RAISE NOTICE 'At least 1000';
    ELSE
        RAISE NOTICE 'Below 100';
END CASE;
```

Với `v_amount=1500`, nhánh **At least 100** sẽ thắng, vì đã được kiểm tra trước. Sửa:

```sql
CASE
    WHEN v_amount >= 1000 THEN
        RAISE NOTICE 'At least 1000';
    WHEN v_amount >= 100 THEN
        RAISE NOTICE 'From 100 to below 1000';
    ELSE
        RAISE NOTICE 'Below 100';
END CASE;
```

---

## 10. CASE_NOT_FOUND và ELSE NULL

### 10.1. Simple CASE không có ELSE

Ví dụ cố ý phát sinh lỗi:

```sql
-- Chỉ chạy khi muốn quan sát lỗi.
-- DO $block$
-- DECLARE
--     v_status text := 'unknown';
-- BEGIN
--     CASE v_status
--         WHEN 'draft' THEN
--             RAISE NOTICE 'Draft';
--         WHEN 'paid' THEN
--             RAISE NOTICE 'Paid';
--     END CASE;
-- END;
-- $block$;
```

Vì `'unknown'` không match và không có `ELSE`, PostgreSQL phát sinh `CASE_NOT_FOUND`. Đây là **cơ chế bắt thiếu trạng thái** có thể hữu ích trong quy trình nghiệp vụ.

### 10.2. Searched CASE tương tự

```sql
-- Cũng có thể phát sinh CASE_NOT_FOUND nếu amount=5:
-- CASE
--     WHEN v_amount > 100 THEN
--         ...
--     WHEN v_amount < 0 THEN
--         ...
-- END CASE;
```

### 10.3. ELSE NULL là lựa chọn không làm gì

Trong PL/pgSQL, `NULL;` là một **câu lệnh rỗng** hợp lệ:

```sql
DO $block$
DECLARE
    v_status text := 'unknown';
BEGIN
    CASE v_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Draft';
        WHEN 'paid' THEN
            RAISE NOTICE 'Paid';
        ELSE
            NULL;
    END CASE;

    RAISE NOTICE 'Continues safely';
END;
$block$;
```

Nhánh mặc định không làm gì và không ném `CASE_NOT_FOUND`. Chỉ dùng cách này nếu việc bỏ qua là **chính sách rõ ràng**, không phải để che một giá trị đầu vào không hợp lệ.

### 10.4. Dùng ELSE để từ chối trạng thái lạ

```sql
CASE v_status
    WHEN 'draft' THEN
        RAISE NOTICE 'Editable';
    WHEN 'paid' THEN
        RAISE NOTICE 'Completed';
    ELSE
        RAISE EXCEPTION 'Unsupported status: %', v_status
            USING ERRCODE = '22023';
END CASE;
```

Đây là lựa chọn tốt khi các giá trị ngoài danh mục **không được phép**.

### 10.5. Bắt CASE_NOT_FOUND khi thật sự cần

```sql
DO $block$
DECLARE
    v_status text := 'other';
BEGIN
    BEGIN
        CASE v_status
            WHEN 'draft' THEN
                RAISE NOTICE 'Draft';
            WHEN 'paid' THEN
                RAISE NOTICE 'Paid';
        END CASE;
    EXCEPTION
        WHEN case_not_found THEN
            RAISE NOTICE 'Unexpected status: %', v_status;
    END;
END;
$block$;
```

Đây là ví dụ nhận diện exception, **không** phải khuyến nghị dùng exception để phân nhánh thường xuyên. Thông thường, xử lý bằng `ELSE` rõ ràng, dễ đọc và ít overhead hơn.

---

## 11. CASE của SQL: biểu thức trả về giá trị, không phải PL/pgSQL statement

### 11.1. Hai dạng SQL CASE

**Simple SQL CASE expression:**

```sql
SELECT
    CASE 'issued'
        WHEN 'draft' THEN 'Editable'
        WHEN 'issued' THEN 'Ready'
        WHEN 'paid' THEN 'Completed'
        ELSE 'Unknown'
    END AS status_label;
```

**Searched SQL CASE expression:**

```sql
SELECT
    CASE
        WHEN 750 >= 1000 THEN 'Large'
        WHEN 750 >= 100 THEN 'Medium'
        ELSE 'Small'
    END AS amount_label;
```

Điểm nhận dạng: **`END`** đóng biểu thức SQL CASE.

### 11.2. PL/pgSQL CASE statement kết thúc bằng END CASE;

```sql
DO $block$
BEGIN
    CASE
        WHEN 750 >= 1000 THEN
            RAISE NOTICE 'Large';
        WHEN 750 >= 100 THEN
            RAISE NOTICE 'Medium';
        ELSE
            RAISE NOTICE 'Small';
    END CASE;
END;
$block$;
```

Điểm nhận dạng: **`END CASE;`** đóng câu lệnh điều khiển luồng.

### 11.3. SQL CASE không ELSE trả NULL

```sql
SELECT
    CASE
        WHEN 2 > 10 THEN 'Greater than 10'
    END AS result;
```

Kết quả là SQL `NULL`. Nó **không** ném `CASE_NOT_FOUND`.

So với PL/pgSQL CASE statement không có ELSE, đây là khác biệt cực kỳ quan trọng.

### 11.4. SQL CASE nằm trong SELECT

```sql
SELECT
    status,
    CASE status
        WHEN 'draft' THEN 'DRAFT'
        WHEN 'issued' THEN 'OPEN'
        WHEN 'paid' THEN 'SETTLED'
        ELSE 'INACTIVE'
    END AS display_group
FROM plpgsql_cond_lab.invoices;
```

Toán tử CASE sẽ tính một giá trị biểu diễn cho **mỗi row** của câu SELECT.

### 11.5. SQL CASE có thể dùng trong UPDATE

```sql
-- Mẫu minh họa chuyển nhãn trong một lệnh SQL theo tập hợp.
-- UPDATE some_table
-- SET priority = CASE
--     WHEN amount >= 1000 THEN 'high'
--     WHEN amount >= 100  THEN 'medium'
--     ELSE 'low'
-- END;
```

Không cần viết một function PL/pgSQL rồi `FOR` từng hàng chỉ để cập nhật cột theo điều kiện đơn giản.

### 11.6. CASE là một biểu thức, không chứa câu lệnh RAISE

Sai về bản chất:

```sql
-- SQL CASE không phải nơi viết câu lệnh PL/pgSQL:
-- SELECT CASE WHEN amount < 0
--             THEN RAISE EXCEPTION 'invalid'
--        END;
```

Trong SQL CASE, mỗi `THEN` cần một **biểu thức trả giá trị**, không phải một câu lệnh điều khiển PL/pgSQL như `RAISE` hoặc `RETURN`. Muốn dừng nghiệp vụ với lỗi, thực hiện trong PL/pgSQL `IF`/`CASE` statement hoặc qua ràng buộc SQL thích hợp.

### 11.7. Type resolution của các nhánh

`CASE` expression phải trả về **một kiểu kết quả có thể xác định chung** cho các nhánh:

```sql
SELECT CASE
           WHEN true THEN 10
           ELSE 20
       END AS integer_result;
```

Không nên giả định có thể trả tùy ý JSON object, timestamp, boolean, text và numeric trong các nhánh mà không cần quy tắc ép kiểu hợp lệ.

---

## 12. Đặt tên biến và tránh nhầm cột SQL với biến PL/pgSQL

### 12.1. Quy ước có lợi

| Ký hiệu | Mục đích |
|---|---|
| `p_amount` | Parameter truyền vào function |
| `v_status` | Biến cục bộ |
| `v_invoice` | Row/record được SELECT từ bảng |
| `t` hoặc `i` | Alias bảng trong SQL |
| `NEW` / `OLD` | Row của trigger |

### 12.2. Ambiguous names

Nếu bảng có `status` và biến cục bộ cũng tên `status`:

```sql
SELECT status INTO status FROM invoices;
```

code có thể gặp lỗi tham chiếu nhập nhằng hoặc đọc sai ý theo cấu hình xử lý variable conflict. Nên viết:

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

### 12.3. Gán biến bằng :=

```sql
v_label := 'paid';
v_count := v_count + 1;
```

Đừng nhầm `:=` trong PL/pgSQL với `SET status = 'paid'` trong SQL UPDATE.

### 12.4. SELECT ... INTO của PL/pgSQL

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

Trong PL/pgSQL, `SELECT ... INTO variable` gán giá trị kết quả query vào biến. Đây không phải lệnh `SELECT INTO new_table` của SQL dùng để tạo bảng mới.

---

## 13. Phòng thực hành độc lập: hóa đơn và chuyển trạng thái

Chúng ta tạo một mô hình nhỏ để minh họa **IF để kiểm tra** và **CASE để chọn xử lý theo trạng thái**.

### 13.1. Khởi tạo schema

```sql
CREATE SCHEMA plpgsql_cond_lab;
```

Thực hiện trong database thử nghiệm chưa có schema cùng tên. Không chạy `DROP SCHEMA ... CASCADE` trong database dùng chung chỉ để reset bài.

### 13.2. Tạo bảng invoices

```sql
CREATE TABLE plpgsql_cond_lab.invoices (
    invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL
        CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    issued_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status <> 'paid' OR paid_at IS NOT NULL)
);
```

Ràng buộc cần phân biệt:

- `NOT NULL` và `CHECK` bảo vệ dữ liệu ở database, kể cả khi một session bỏ qua function nghiệp vụ.
- Function xử lý chuyển trạng thái cung cấp quy trình và thông báo lỗi dễ hiểu.
- `CHECK (status <> 'paid' OR paid_at IS NOT NULL)` ngăn row paid thiếu `paid_at`, nhưng **không** diễn đạt mọi quy tắc chuyển trạng thái giữa hai thời điểm.

### 13.3. Nạp dữ liệu mẫu

```sql
INSERT INTO plpgsql_cond_lab.invoices
    (tenant_id, amount, status, issued_at, paid_at)
VALUES
    (1, 120.00, 'draft',  NULL, NULL),
    (1, 200.00, 'issued', TIMESTAMPTZ '2026-11-01 08:00+00', NULL),
    (1,  90.00, 'paid',
        TIMESTAMPTZ '2026-11-01 08:00+00',
        TIMESTAMPTZ '2026-11-02 10:00+00'),
    (2,  50.00, 'void',   NULL, NULL),
    (2,   0.00, 'issued', TIMESTAMPTZ '2026-11-03 09:00+00', NULL);
```

Trên schema mới với một lần INSERT, `invoice_id` thường từ 1 đến 5. Những ví dụ sử dụng ID 1, 2, 3, 4, 5 giả định dữ liệu lab này chỉ được nạp một lần.

### 13.4. Xem trạng thái nguồn

```sql
SELECT
    invoice_id,
    tenant_id,
    amount,
    status,
    issued_at,
    paid_at
FROM plpgsql_cond_lab.invoices
ORDER BY invoice_id;
```

### 13.5. Logic nghiệp vụ đơn giản

```text
draft  --issue--> issued --pay--> paid
  |                 |
  +-----void--------+

paid: trạng thái cuối trong ví dụ
void: trạng thái cuối trong ví dụ
```

Đây chỉ là state machine tối giản; invoice thực tế có thể có `partially_paid`, `overdue`, `refunded`, `disputed` hoặc nhiều lần thanh toán.

---

## 14. Function phân nhóm amount bằng IF

### 14.1. Định nghĩa đầy đủ

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.classify_amount(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount < 0 THEN
        RAISE EXCEPTION 'Negative amount: %', p_amount
            USING ERRCODE = '22023';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSIF p_amount < 100 THEN
        RETURN 'SMALL';
    ELSIF p_amount < 1000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LARGE';
    END IF;
END;
$function$;
```

Đây là bản có schema phù hợp cho lab, thay cho ví dụ khái niệm ở mục 5. Đầu tiên kiểm tra NULL rồi số âm; tiếp đó loại dần theo khoảng.

### 14.2. Chạy với các giá trị hợp lệ

```sql
SELECT
    p.amount,
    plpgsql_cond_lab.classify_amount(p.amount) AS category
FROM (
    VALUES
        (NULL::numeric),
        (0::numeric),
        (25::numeric),
        (100::numeric),
        (999.99::numeric),
        (1000::numeric)
) AS p(amount);
```

Kết quả theo thứ tự là `UNKNOWN`, `ZERO`, `SMALL`, `MEDIUM`, `MEDIUM`, `LARGE`.

### 14.3. Thử lỗi số âm một cách có chủ đích

```sql
-- Chạy riêng để quan sát exception:
-- SELECT plpgsql_cond_lab.classify_amount(-5);
```

Function dùng `RAISE EXCEPTION` với SQLSTATE `22023` (*invalid_parameter_value*). Câu gọi sẽ thất bại thay vì trả `SMALL`.

### 14.4. Tại sao RETURN nằm trong từng nhánh?

`RETURN` là quyết định kết thúc function ngay tại nhánh đã chọn. Nếu không có RETURN hoặc RAISE trên mọi đường đi trong một function trả scalar, function có thể tới cuối mà không có giá trị trả và gây lỗi runtime.

Một cách khác là gán `v_category` trong các nhánh rồi `RETURN v_category;` một lần ở cuối. Chọn kiểu nào tùy độ phức tạp và khả năng đọc.

---

## 15. Function dùng simple CASE cho trạng thái

### 15.1. Tạo nhãn hiển thị

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.invoice_status_label(p_status text)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    CASE p_status
        WHEN 'draft' THEN
            RETURN 'Đang soạn';
        WHEN 'issued' THEN
            RETURN 'Đã phát hành';
        WHEN 'paid' THEN
            RETURN 'Đã thanh toán';
        WHEN 'void' THEN
            RETURN 'Đã hủy';
        ELSE
            RETURN 'Không xác định';
    END CASE;
END;
$function$;
```

### 15.2. Gọi function

```sql
SELECT
    invoice_id,
    status,
    plpgsql_cond_lab.invoice_status_label(status)
        AS status_label
FROM plpgsql_cond_lab.invoices
ORDER BY invoice_id;
```

### 15.3. Đây chưa phải lý do đủ để viết PL/pgSQL

Nếu chỉ cần chuyển một giá trị trạng thái sang nhãn trong hàng nghìn rows, một biểu thức SQL `CASE` ngay trong `SELECT` có thể đơn giản hơn và tránh chi phí gọi PL/pgSQL function từng row:

```sql
SELECT
    invoice_id,
    CASE status
        WHEN 'draft'  THEN 'Đang soạn'
        WHEN 'issued' THEN 'Đã phát hành'
        WHEN 'paid'   THEN 'Đã thanh toán'
        WHEN 'void'   THEN 'Đã hủy'
        ELSE 'Không xác định'
    END AS status_label
FROM plpgsql_cond_lab.invoices;
```

Mục đích function ở phần này là minh họa **CASE statement**. Trong production, cân nhắc triển khai tại nơi đơn giản và hiệu quả nhất.

---

## 16. Function issue_invoice: IF, FOUND, CASE và row lock

### 16.1. Yêu cầu

Một hóa đơn chỉ được phát hành nếu:

- Có `invoice_id` hợp lệ.
- Thuộc đúng `tenant_id` của request.
- Trạng thái hiện tại là `draft`.

Nếu đã `issued`, có thể trả `ALREADY_ISSUED` thay vì cập nhật lại. Nếu đã `paid` hoặc `void`, từ chối chuyển lại sang `issued`.

### 16.2. Vì sao cần SELECT ... FOR UPDATE?

Hai transaction có thể cùng gọi function cho một hóa đơn. Nếu cả hai đọc trạng thái cũ rồi cập nhật, một luồng kiểm tra không có lock thích hợp dễ bị race khi logic phát triển phức tạp.

`SELECT ... FOR UPDATE` khóa row được chọn trong transaction, giúp một giao dịch xử lý/kiểm tra trạng thái có phối hợp với giao dịch khác đang muốn sửa row ấy.

### 16.3. Định nghĩa function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.issue_invoice(
        p_invoice_id bigint,
        p_tenant_id integer
    )
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status text;
BEGIN
    IF p_invoice_id IS NULL OR p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Invoice ID and tenant ID are required'
            USING ERRCODE = '22023';
    END IF;

    SELECT i.status
    INTO v_status
    FROM plpgsql_cond_lab.invoices AS i
    WHERE i.invoice_id = p_invoice_id
      AND i.tenant_id = p_tenant_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Invoice % not found for tenant %',
            p_invoice_id, p_tenant_id
            USING ERRCODE = 'P0002';
    END IF;

    CASE v_status
        WHEN 'draft' THEN
            UPDATE plpgsql_cond_lab.invoices AS i
            SET status = 'issued',
                issued_at = transaction_timestamp()
            WHERE i.invoice_id = p_invoice_id
              AND i.tenant_id = p_tenant_id;

            RETURN 'ISSUED';

        WHEN 'issued' THEN
            RETURN 'ALREADY_ISSUED';

        WHEN 'paid' THEN
            RAISE EXCEPTION
                'Paid invoice % cannot be issued again',
                p_invoice_id
                USING ERRCODE = '22023';

        WHEN 'void' THEN
            RAISE EXCEPTION
                'Void invoice % cannot be issued',
                p_invoice_id
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unsupported invoice status: %', v_status
                USING ERRCODE = '22023';
    END CASE;
END;
$function$;
```

### 16.4. Đọc từng lớp điều kiện

1. `IF p_invoice_id IS NULL OR ...`: kiểm tra tham số.
2. `SELECT ... INTO v_status ... FOR UPDATE`: lấy đúng row và khóa để xử lý.
3. `IF NOT FOUND`: từ chối ID không có/không thuộc tenant.
4. `CASE v_status`: chọn chính sách theo trạng thái.
5. `UPDATE` chỉ ở nhánh `draft`.
6. `RETURN` dừng function khi kết quả đã biết.
7. `RAISE EXCEPTION` từ chối những chuyển trạng thái không hợp lệ.

### 16.5. Thực hành phát hành hóa đơn draft

```sql
SELECT plpgsql_cond_lab.issue_invoice(1, 1) AS result;

SELECT invoice_id, tenant_id, status, issued_at
FROM plpgsql_cond_lab.invoices
WHERE invoice_id = 1;
```

Nếu chạy một lần trên dữ liệu mẫu, kết quả `ISSUED` và trạng thái invoice 1 chuyển từ `draft` thành `issued`.

### 16.6. Gửi lại yêu cầu

```sql
SELECT plpgsql_cond_lab.issue_invoice(1, 1) AS result;
```

Lần gọi tiếp theo trả `ALREADY_ISSUED`, không phát hành lại và không tự đổi timestamp phát hành.

Đây là một ví dụ về **idempotent effect theo trạng thái** cho thao tác phát hành. Trong nghiệp vụ phức tạp, cần cân nhắc side effects ngoài database, request ID và tính exactly-once effect.

### 16.7. Sai tenant

```sql
-- Gọi riêng để quan sát lỗi không tìm thấy theo scope:
-- SELECT plpgsql_cond_lab.issue_invoice(1, 2);
```

Function không trả chi tiết rằng invoice có tồn tại ở tenant khác hay không; nó trả “not found for tenant” theo điều kiện tìm row. Đây là một cách giảm rủi ro làm lộ dữ liệu tenant khác, nhưng **không thay thế RLS/quyền tại DB**.

### 16.8. Đã paid

```sql
-- Gọi riêng để quan sát lỗi:
-- SELECT plpgsql_cond_lab.issue_invoice(3, 1);
```

Function từ chối trạng thái `paid` theo rule. Không có một `ELSE` âm thầm chuyển mọi trạng thái lạ thành `issued`.

---

## 17. FOUND sau SELECT INTO và các lỗi thường gặp

### 17.1. FOUND là biến Boolean đặc biệt

PL/pgSQL cung cấp biến `FOUND` để phản ánh kết quả của một số câu lệnh SQL gần nhất, bao gồm `SELECT INTO`, `PERFORM`, `INSERT`, `UPDATE`, `DELETE` theo những quy tắc cụ thể.

Ví dụ:

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

IF NOT FOUND THEN
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

### 17.2. Kiểm tra FOUND ngay sau câu lệnh liên quan

Không làm:

```sql
SELECT i.status INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

PERFORM 1;

IF NOT FOUND THEN
    -- FOUND lúc này không còn phản ánh SELECT phía trên.
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

`PERFORM 1` có thể thay đổi `FOUND`. Trong ví dụ này, nó thường đặt FOUND thành TRUE và che việc SELECT trước đó không có row.

### 17.3. Không có row và SELECT INTO không STRICT

`SELECT ... INTO` thông thường, khi query không trả row, đặt biến đích theo tình huống không có hàng và `FOUND = FALSE`. Nếu query trả nhiều rows, biến nhận một row theo cơ chế không `STRICT`; nếu cần đúng một, hãy áp ràng buộc hoặc dùng `STRICT`.

### 17.4. SELECT INTO STRICT

```sql
SELECT i.status
INTO STRICT v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

Với `STRICT`:

- Không có row → lỗi `NO_DATA_FOUND`.
- Nhiều rows → lỗi `TOO_MANY_ROWS`.
- Đúng một row → gán biến.

Nếu ID là primary key, tối đa một row đã được constraint bảo đảm, nhưng không có row vẫn cần xử lý.

### 17.5. Chọn IF FOUND hay EXCEPTION NO_DATA_FOUND?

- `IF NOT FOUND` sau SELECT không STRICT phù hợp khi “không có row” là một nhánh nghiệp vụ dự kiến.
- `INTO STRICT` phù hợp khi chương trình coi thiếu hoặc thừa row là vi phạm invariant.

Không cần dùng exception cho mọi trường hợp truy vấn rỗng; exception block có chi phí và ảnh hưởng transaction context.

### 17.6. RETURNING và ROW_COUNT

Với UPDATE:

```sql
UPDATE plpgsql_cond_lab.invoices
SET status = 'issued'
WHERE invoice_id = p_invoice_id
  AND status = 'draft';

IF FOUND THEN
    RAISE NOTICE 'One or more rows updated';
END IF;
```

Nếu muốn biết số hàng chính xác:

```sql
GET DIAGNOSTICS v_updated_count = ROW_COUNT;
```

`v_updated_count` cần được khai báo kiểu số phù hợp. `FOUND` cho biết có hay không, còn `ROW_COUNT` giúp xác minh invariant như “có đúng một row được sửa”.

---

## 18. Function pay_invoice: kết hợp guard IF và state CASE

### 18.1. Quy tắc

- Chỉ hóa đơn `issued` được chuyển sang `paid`.
- Gửi lại yêu cầu khi đã `paid` trả `ALREADY_PAID`, không đổi `paid_at`.
- Thiếu timestamp thanh toán bị từ chối.
- `draft` và `void` không được thanh toán theo state machine mẫu.
- Mọi truy cập gắn với tenant và xử lý dưới row lock.

### 18.2. Định nghĩa function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.pay_invoice(
        p_invoice_id bigint,
        p_tenant_id integer,
        p_paid_at timestamptz DEFAULT transaction_timestamp()
    )
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status text;
BEGIN
    IF p_invoice_id IS NULL OR p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Invoice ID and tenant ID are required'
            USING ERRCODE = '22023';
    END IF;

    IF p_paid_at IS NULL THEN
        RAISE EXCEPTION 'Payment timestamp is required'
            USING ERRCODE = '22023';
    END IF;

    SELECT i.status
    INTO v_status
    FROM plpgsql_cond_lab.invoices AS i
    WHERE i.invoice_id = p_invoice_id
      AND i.tenant_id = p_tenant_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Invoice % not found for tenant %',
            p_invoice_id, p_tenant_id
            USING ERRCODE = 'P0002';
    END IF;

    CASE v_status
        WHEN 'issued' THEN
            UPDATE plpgsql_cond_lab.invoices AS i
            SET status = 'paid',
                paid_at = p_paid_at
            WHERE i.invoice_id = p_invoice_id
              AND i.tenant_id = p_tenant_id;

            RETURN 'PAID';

        WHEN 'paid' THEN
            RETURN 'ALREADY_PAID';

        WHEN 'draft' THEN
            RAISE EXCEPTION
                'Draft invoice % must be issued first',
                p_invoice_id
                USING ERRCODE = '22023';

        WHEN 'void' THEN
            RAISE EXCEPTION
                'Void invoice % cannot be paid',
                p_invoice_id
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unsupported invoice status: %', v_status
                USING ERRCODE = '22023';
    END CASE;
END;
$function$;
```

### 18.3. Gọi với hóa đơn đã issued

```sql
SELECT plpgsql_cond_lab.pay_invoice(
    2,
    1,
    TIMESTAMPTZ '2026-11-04 11:00:00+00'
) AS result;

SELECT invoice_id, status, paid_at
FROM plpgsql_cond_lab.invoices
WHERE invoice_id = 2;
```

Kết quả là `PAID`, với `paid_at` chính xác như tham số đã đưa vào.

### 18.4. Thử gọi lại

```sql
SELECT plpgsql_cond_lab.pay_invoice(
    2,
    1,
    TIMESTAMPTZ '2026-11-05 11:00:00+00'
) AS result;
```

Trả `ALREADY_PAID`. Timestamp cũ được giữ nguyên; không được thay đổi vì một retry.

### 18.5. Tại sao kiểm tra timestamp trước khi đọc trạng thái?

Đây là lựa chọn contract: yêu cầu thiếu `p_paid_at` luôn bị coi là invalid, kể cả invoice đã paid. Một thiết kế khác có thể cho retry “đã paid” trước khi kiểm tra timestamp, nhưng phải có chính sách rõ ràng.

Không có một thứ tự kiểm tra bắt buộc cho mọi nghiệp vụ; **thứ tự IF là một phần của hành vi API**.

### 18.6. Bảo mật và transaction

Row lock giúp phối hợp thay đổi trạng thái trên cùng hóa đơn, nhưng:

- Không tự chứng minh người gọi có quyền của tenant.
- Không thay RLS/grants hoặc authorization ở tầng ứng dụng.
- Nếu function dùng `SECURITY DEFINER`, phải đặc biệt thận trọng với owner, `search_path` và quyền gọi.
- Nếu có side effect ra dịch vụ ngoài, transaction DB rollback không tự rollback tác động ngoài DB.

Các function ở lab dùng behavior mặc định, không minh họa một giao thức thanh toán production đầy đủ.

---

## 19. CASE và IF trong trigger

Trigger thường cần kiểm tra sự thay đổi giữa `OLD` và `NEW`.

### 19.1. Ví dụ kiểm soát chuyển trạng thái

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.guard_invoice_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    CASE OLD.status
        WHEN 'draft' THEN
            IF NEW.status NOT IN ('issued', 'void') THEN
                RAISE EXCEPTION
                    'Invalid transition: % -> %',
                    OLD.status, NEW.status
                    USING ERRCODE = '22023';
            END IF;

        WHEN 'issued' THEN
            IF NEW.status NOT IN ('paid', 'void') THEN
                RAISE EXCEPTION
                    'Invalid transition: % -> %',
                    OLD.status, NEW.status
                    USING ERRCODE = '22023';
            END IF;

        WHEN 'paid', 'void' THEN
            RAISE EXCEPTION
                'Terminal invoice state cannot change: % -> %',
                OLD.status, NEW.status
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unknown old status: %', OLD.status
                USING ERRCODE = '22023';
    END CASE;

    RETURN NEW;
END;
$function$;
```

### 19.2. Gắn BEFORE UPDATE trigger

```sql
CREATE TRIGGER invoices_guard_transition
BEFORE UPDATE OF status
ON plpgsql_cond_lab.invoices
FOR EACH ROW
EXECUTE FUNCTION
    plpgsql_cond_lab.guard_invoice_transition();
```

Vì cột `status` được khai báo NOT NULL và CHECK danh mục trạng thái, biểu thức `NEW.status NOT IN (...)` không phải xử lý trường hợp NULL trên dữ liệu đã được bảo vệ; nếu dữ liệu nguồn nullable, phải sửa điều kiện để tránh UNKNOWN.

### 19.3. Thử chuyển trạng thái hợp lệ

```sql
-- Nếu invoice 1 đã được issue ở mục 16:
SELECT plpgsql_cond_lab.pay_invoice(
    1, 1, TIMESTAMPTZ '2026-11-06 10:00:00+00'
);
```

Trigger cho phép `issued → paid`. Function trả `PAID`.

### 19.4. Thử chuyển trạng thái không hợp lệ

```sql
-- Chỉ chạy riêng để xem lỗi:
-- UPDATE plpgsql_cond_lab.invoices
-- SET status = 'draft'
-- WHERE invoice_id = 3;
```

Trigger chặn `paid → draft`. Bởi `RAISE EXCEPTION` gây lỗi statement, thay đổi status không được commit như một UPDATE thành công.

### 19.5. Trigger và UPDATE OF

`BEFORE UPDATE OF status` chạy khi cột status có trong **target list của UPDATE**, không nhất thiết vì giá trị status thực sự đổi. Function đã kiểm tra:

```sql
IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
END IF;
```

nhằm bỏ qua khi không có thay đổi giá trị.

### 19.6. Giới hạn của UPDATE OF với nhiều triggers

Nếu một BEFORE trigger khác thay đổi `NEW.status` khi SQL không liệt kê status trong `SET`, trigger `UPDATE OF status` có thể không được kích hoạt vì danh sách cột được kiểm tra theo câu SQL. Nếu cần bảo vệ **mọi thay đổi status từ bất kỳ trigger nào**, có thể chọn `BEFORE UPDATE` không giới hạn cột và tổ chức thứ tự triggers phù hợp.

### 19.7. Trigger order là một phần thiết kế

Nhiều triggers cùng loại/event trên một bảng chạy theo quy tắc thứ tự tên. Nếu một trigger chuẩn hóa/đổi status sau trigger kiểm tra, trạng thái cuối cùng có thể thoát kiểm tra.

Giải pháp tốt không phải chỉ đổi tên cho may mắn; hãy xác định rõ **bất biến, thứ tự xử lý và nơi duy nhất có quyền thay đổi status**.

### 19.8. Trigger không tự bảo đảm nghiệp vụ bên ngoài

Trigger chỉ bảo vệ những UPDATE đi qua bảng và ngữ cảnh kích hoạt phù hợp; các migration/replication settings, quyền bypass hoặc side effects ngoài database cần được thiết kế riêng. Không coi một trigger là toàn bộ chính sách bảo mật hay workflow.

---

## 20. RAISE NOTICE, WARNING, EXCEPTION và SQLSTATE

### 20.1. Ba mức thông báo thường gặp

| Cú pháp | Hành vi điển hình |
|---|---|
| `RAISE NOTICE` | Phát thông điệp chẩn đoán, không tự hủy statement |
| `RAISE WARNING` | Phát cảnh báo, statement có thể tiếp tục |
| `RAISE EXCEPTION` | Ném lỗi, thoát khỏi đường lệnh bình thường |

Ví dụ:

```sql
DO $block$
BEGIN
    RAISE NOTICE 'Starting validation';
    RAISE WARNING 'This is a demonstration warning';
    RAISE NOTICE 'Still running';
END;
$block$;
```

### 20.2. Exception dùng khi không thể tiếp tục

```sql
IF p_amount < 0 THEN
    RAISE EXCEPTION 'Amount must be non-negative: %', p_amount
        USING ERRCODE = '22023';
END IF;
```

`ERRCODE = '22023'` biểu diễn lỗi tham số không hợp lệ trong SQLSTATE. Ứng dụng có thể phân loại lỗi bằng SQLSTATE thay vì chỉ so nội dung message.

### 20.3. Khối EXCEPTION có subtransaction semantics

```sql
DO $block$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Controlled failure';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Caught: %, SQLSTATE=%', SQLERRM, SQLSTATE;
    END;

    RAISE NOTICE 'Outer block continues';
END;
$block$;
```

Khi bắt exception, PostgreSQL xử lý rollback những thay đổi persistent database của khối bị lỗi theo cơ chế subtransaction tương ứng. Biến PL/pgSQL cục bộ có quy tắc riêng khi exception xảy ra.

### 20.4. Không dùng EXCEPTION như IF bình thường

Nếu một giá trị có thể `NULL` hoặc nhỏ hơn 0, dùng `IF` để kiểm tra. Không cố để phép toán gây lỗi rồi bắt exception cho mọi row. Exception blocks thường đắt hơn điều kiện thông thường, tăng độ phức tạp và có thể che lỗi thật.

### 20.5. Không nuốt mọi lỗi

Một khối:

```sql
EXCEPTION
    WHEN others THEN
        NULL;
```

thường nguy hiểm nếu được dùng để “cho chương trình chạy tiếp”, vì có thể che lỗi quyền, deadlock, mất kết nối logic hoặc constraint.

Nếu bắt lỗi, hãy xác định đúng SQLSTATE/exception name, log đủ ngữ cảnh, rồi xử lý hoặc `RAISE;` lại khi không thể phục hồi.

---

## 21. RETURN, RETURN NEXT và luồng điều khiển

### 21.1. RETURN kết thúc function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.describe_sign(p_value integer)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_value IS NULL THEN
        RETURN 'unknown';
    END IF;

    IF p_value < 0 THEN
        RETURN 'negative';
    END IF;

    IF p_value = 0 THEN
        RETURN 'zero';
    END IF;

    RETURN 'positive';
END;
$function$;
```

Sau khi một `RETURN` được chạy, phần còn lại của function không được thực hiện.

### 21.2. Early return giảm lồng nhau

So sánh:

```sql
IF p_customer_id IS NOT NULL THEN
    IF p_amount > 0 THEN
        IF p_approved THEN
            -- Business action
        ELSE
            -- Error
        END IF;
    ELSE
        -- Error
    END IF;
ELSE
    -- Error
END IF;
```

với các guard clauses:

```sql
IF p_customer_id IS NULL THEN
    RAISE EXCEPTION 'Customer ID required';
END IF;

IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Positive amount required';
END IF;

IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;

-- Business action ở mức lồng ít hơn.
```

Guard clauses thường làm happy path rõ hơn, miễn là chúng phản ánh đúng thứ tự ưu tiên và policy khi đầu vào có nhiều lỗi đồng thời.

### 21.3. RETURN NEXT khác RETURN

Trong function trả tập hợp (`RETURNS SETOF ...`), `RETURN NEXT` đưa thêm một row vào tập kết quả nhưng **không tự kết thúc function ngay** như `RETURN value` của scalar function.

Ví dụ khái niệm:

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.sample_signs()
RETURNS SETOF text
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN NEXT 'negative';
    RETURN NEXT 'zero';
    RETURN NEXT 'positive';
    RETURN;
END;
$function$;
```

`RETURN;` cuối function kết thúc quá trình sinh tập kết quả.

### 21.4. Đừng sử dụng IF như vòng lặp

`IF` chọn một nhánh **một lần** tại vị trí chạy qua. Nếu cần lặp tới khi điều kiện thỏa, đó là chủ đề `LOOP`/`WHILE`/`FOR`; không thể thêm `END IF;` rồi mong điều kiện tự lặp lại.

---

## 22. Nên dùng CASE SQL hay PL/pgSQL khi cập nhật hàng loạt?

### 22.1. Vấn đề

Cần chia hàng triệu hóa đơn thành nhóm ưu tiên dựa trên amount.

Một cách kém hiệu quả là:

```text
FOR each invoice:
    SELECT one row
    IF ...
       UPDATE row
    ELSIF ...
       UPDATE row
    END IF
```

Nếu logic là một hàm thuần trên amount, làm việc từng hàng bằng PL/pgSQL có thể gây nhiều overhead.

### 22.2. Một SELECT dùng SQL CASE

```sql
SELECT
    invoice_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN 'high'
        WHEN amount >= 100 THEN 'normal'
        ELSE 'low'
    END AS priority
FROM plpgsql_cond_lab.invoices;
```

SQL CASE tính biểu thức cho từng row trong một câu SELECT theo tập hợp. Không cần procedural loop.

### 22.3. Một UPDATE set-based

Nếu bảng có cột `priority` riêng, bạn có thể dùng:

```sql
-- Mẫu minh họa trên bảng đã có priority:
-- UPDATE some_schema.invoices
-- SET priority = CASE
--     WHEN amount >= 1000 THEN 'high'
--     WHEN amount >= 100 THEN 'normal'
--     ELSE 'low'
-- END;
```

Không chạy trên bảng lab vì bảng `plpgsql_cond_lab.invoices` không có cột `priority`.

### 22.4. CASE với aggregate

```sql
SELECT
    tenant_id,
    SUM(
        CASE
            WHEN status = 'paid' THEN amount
            ELSE 0
        END
    ) AS paid_amount
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id
ORDER BY tenant_id;
```

PostgreSQL còn có cú pháp `FILTER` thường sáng sủa hơn cho conditional aggregates:

```sql
SELECT
    tenant_id,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0
    ) AS paid_amount,
    COUNT(*) FILTER (WHERE status = 'paid')
        AS paid_count
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id
ORDER BY tenant_id;
```

`SUM` trên tập trống trả SQL NULL, nên `COALESCE` được dùng nếu hợp đồng cần số 0.

### 22.5. Khi PL/pgSQL thực sự có giá trị

Dùng PL/pgSQL khi cần:

- Nhiều câu SQL phải phối hợp theo trạng thái.
- Validation và trả lỗi chuyên biệt.
- Chuyển trạng thái có lock/transaction semantics.
- Trigger kiểm soát bất biến.
- Nhánh xử lý phụ thuộc kết quả một câu SQL trước đó.
- Tổ chức logic procedure/function được dùng lại.

Đừng dùng IF/CASE statement để thay SQL CASE expression cho mọi phép ánh xạ giá trị đơn giản.

---

## 23. CASE trong ORDER BY và phân loại mức ưu tiên

### 23.1. Sắp xếp trạng thái theo thứ tự nghiệp vụ

Mặc định `ORDER BY status` sắp xếp theo collation/text, không nhất thiết là thứ tự nghiệp vụ.

```sql
SELECT
    invoice_id,
    status,
    amount
FROM plpgsql_cond_lab.invoices
ORDER BY
    CASE status
        WHEN 'issued' THEN 1
        WHEN 'draft' THEN 2
        WHEN 'paid' THEN 3
        WHEN 'void' THEN 4
        ELSE 5
    END,
    invoice_id;
```

### 23.2. CASE trong WHERE có thể làm khó index

```sql
-- Không cần làm phức tạp khi chỉ lọc status:
-- WHERE CASE WHEN status = 'paid' THEN true ELSE false END
```

Nếu có thể viết trực tiếp:

```sql
WHERE status = 'paid'
```

thì planner dễ nhìn thấy điều kiện trên cột để cân nhắc index phù hợp.

### 23.3. CASE có thể dùng cho điều kiện thật sự khác nhau

```sql
SELECT invoice_id, amount, status
FROM plpgsql_cond_lab.invoices
WHERE
    CASE
        WHEN status = 'issued' THEN amount >= 100
        WHEN status = 'draft' THEN amount >= 500
        ELSE false
    END;
```

Về logic, có thể viết:

```sql
WHERE
    (status = 'issued' AND amount >= 100)
    OR
    (status = 'draft' AND amount >= 500)
```

Trong nhiều trường hợp, dạng Boolean trực tiếp dễ hiểu hơn và cho optimizer những predicate rõ ràng hơn. Hãy xem `EXPLAIN` nếu cần tối ưu.

---

## 24. Độ chính xác với ngày giờ và điều kiện

### 24.1. Dùng timestamptz cho mốc thực

`paid_at` trong bảng mẫu là `TIMESTAMPTZ`, đại diện một thời điểm thực. Không dùng chuỗi không timezone khi nghiệp vụ cần so sánh rõ mốc.

### 24.2. Phân loại quá hạn

Một function có thể xét:

```sql
IF p_paid_at IS NOT NULL THEN
    RETURN 'PAID';
ELSIF p_due_at IS NULL THEN
    RETURN 'UNKNOWN_DUE_DATE';
ELSIF p_due_at < transaction_timestamp() THEN
    RETURN 'OVERDUE';
ELSE
    RETURN 'OPEN';
END IF;
```

Đây là **mẫu thân function**, các biến `p_paid_at` và `p_due_at` cần được khai báo nếu viết thành function thực.

### 24.3. NULL phải được xử lý trước so sánh

Nếu `p_due_at IS NULL`, điều kiện `p_due_at < now()` là UNKNOWN. Để phân loại “chưa có hạn”, phải có nhánh `IS NULL` riêng.

### 24.4. Thời điểm transaction và clock

`transaction_timestamp()` trả mốc thời gian bắt đầu transaction hiện tại. `clock_timestamp()` trả thời gian đồng hồ thực tại thời điểm gọi và có thể thay đổi trong cùng statement.

Đối với một quy trình cần timestamp nhất quán trong transaction, `transaction_timestamp()` thường dễ lý giải. Nếu cần đo thời gian thực hiện/độ trễ, `clock_timestamp()` phù hợp hơn. Chọn rõ mục đích thay vì dùng `now()` và `clock_timestamp()` lẫn lộn.

---

## 25. NULL trong simple CASE và searched CASE

### 25.1. Simple CASE và giá trị NULL

Giả sử:

```sql
CASE p_status
    WHEN 'paid' THEN ...
    WHEN NULL THEN ...
    ELSE ...
END CASE;
```

**Không** dùng `WHEN NULL` để bắt một `test_expression` là SQL NULL như cách dùng `IS NULL`. So sánh bình thường với NULL không trả TRUE.

### 25.2. Cách đúng

```sql
CASE
    WHEN p_status IS NULL THEN
        RAISE NOTICE 'Missing status';
    WHEN p_status = 'paid' THEN
        RAISE NOTICE 'Paid';
    ELSE
        RAISE NOTICE 'Other';
END CASE;
```

Hoặc kiểm tra bằng IF trước simple CASE:

```sql
IF p_status IS NULL THEN
    RAISE EXCEPTION 'Status required';
END IF;

CASE p_status
    WHEN 'paid' THEN ...
    WHEN 'issued' THEN ...
    ELSE ...
END CASE;
```

### 25.3. searched CASE WHEN NULL không được chọn

```sql
DO $block$
DECLARE
    v_amount numeric := NULL;
BEGIN
    CASE
        WHEN v_amount > 100 THEN
            RAISE NOTICE 'Above 100';
        WHEN v_amount <= 100 THEN
            RAISE NOTICE 'At most 100';
        ELSE
            RAISE NOTICE 'Missing amount';
    END CASE;
END;
$block$;
```

Với NULL, cả hai điều kiện so sánh đều UNKNOWN, nên ELSE được chọn.

### 25.4. Cách xử lý rủi ro: fail closed

Nếu Boolean `p_has_permission` nullable, một điều kiện:

```sql
IF p_has_permission = false THEN
    RAISE EXCEPTION 'Denied';
END IF;
```

**không** từ chối NULL, vì `NULL = false` là UNKNOWN. Nếu policy là chỉ cho phép TRUE:

```sql
IF p_has_permission IS NOT TRUE THEN
    RAISE EXCEPTION 'Permission required';
END IF;
```

Kiểm soát truy cập thực tế còn cần xác thực người gọi và RLS/grants tại database; một tham số Boolean do client tự gửi **không phải bằng chứng quyền**.

---

## 26. Điều kiện trong procedure khác function thế nào?

### 26.1. Function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.is_positive(p_value numeric)
RETURNS boolean
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_value IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_value > 0;
END;
$function$;
```

Gọi:

```sql
SELECT plpgsql_cond_lab.is_positive(10);
```

### 26.2. Procedure

```sql
CREATE OR REPLACE PROCEDURE
    plpgsql_cond_lab.describe_invoice_status(p_status text)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    CASE p_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Draft';
        WHEN 'issued' THEN
            RAISE NOTICE 'Issued';
        WHEN 'paid' THEN
            RAISE NOTICE 'Paid';
        ELSE
            RAISE NOTICE 'Other';
    END CASE;
END;
$procedure$;
```

Gọi:

```sql
CALL plpgsql_cond_lab.describe_invoice_status('issued');
```

### 26.3. Cùng IF/CASE, khác giao diện thực thi

`IF` và `CASE` là các cấu trúc PL/pgSQL, dùng được trong function, procedure, trigger function và `DO`. Nhưng:

- Function có kiểu trả về và gọi qua SQL expression như `SELECT function(...)`.
- Procedure gọi bằng `CALL` và có cơ chế tham số/transaction control theo quy tắc procedure.
- Trigger function dùng `NEW`/`OLD`/`TG_OP` trong ngữ cảnh trigger.
- `DO` là khối ẩn danh, không tạo một callable function bền vững.

Không lấy một ví dụ `RETURN 'paid'` trong function scalar rồi dán nguyên vào procedure khai báo khác hợp đồng trả về.

---

## 27. Debug luồng điều kiện

### 27.1. RAISE NOTICE với giá trị biến

```sql
RAISE NOTICE 'invoice=%, tenant=%, status=%',
    p_invoice_id, p_tenant_id, v_status;
```

Thông điệp giúp xác định nhánh nào được đi qua, nhưng không nên log thông tin tài chính nhạy cảm hoặc PII khi không cần.

### 27.2. Ghi nhánh được chọn

```sql
DO $block$
DECLARE
    v_amount numeric := 150;
BEGIN
    IF v_amount < 100 THEN
        RAISE NOTICE 'branch=small';
    ELSIF v_amount < 1000 THEN
        RAISE NOTICE 'branch=medium';
    ELSE
        RAISE NOTICE 'branch=large';
    END IF;
END;
$block$;
```

### 27.3. RAISE NOTICE không phải kiểm thử đầy đủ

Với code quan trọng, nên có test assertions:

```sql
DO $test$
DECLARE
    v_category text;
BEGIN
    v_category := plpgsql_cond_lab.classify_amount(150);

    IF v_category IS DISTINCT FROM 'MEDIUM' THEN
        RAISE EXCEPTION
            'Unexpected category: %, expected MEDIUM',
            v_category;
    END IF;
END;
$test$;
```

Một test dạng này tự thất bại nếu giá trị không như dự kiến. Vì `IS DISTINCT FROM` xử lý NULL rõ, test không âm thầm bỏ qua khi result bất ngờ là NULL.

### 27.4. Test các giá trị ranh giới

Với phân loại `SMALL`/`MEDIUM`/`LARGE`, tối thiểu nên kiểm:

```text
NULL
-1
0
0.01
99.99
100
999.99
1000
```

Lỗi off-by-one ở mốc cận dễ bị bỏ sót nếu chỉ thử giá trị ở giữa khoảng.

### 27.5. Test thứ tự nhánh

Một test tốt cố tình chọn giá trị **thỏa hai điều kiện chồng lấn** để xác nhận nhánh ưu tiên:

```sql
DO $test$
DECLARE
    v_amount numeric := 1500;
    v_label text;
BEGIN
    IF v_amount >= 1000 THEN
        v_label := 'LARGE';
    ELSIF v_amount >= 100 THEN
        v_label := 'MEDIUM';
    ELSE
        v_label := 'SMALL';
    END IF;

    IF v_label <> 'LARGE' THEN
        RAISE EXCEPTION 'Wrong branch: %', v_label;
    END IF;
END;
$test$;
```

### 27.6. Test rollback và lỗi nghiệp vụ

Với function issue/pay, test:

- Invoice không tồn tại.
- Đúng ID nhưng sai tenant.
- Draft → issued.
- Retry issued.
- Issued → paid.
- Retry paid.
- Paid → issued bị từ chối.
- Void → paid bị từ chối.
- Hai sessions cùng cập nhật một invoice.

Đừng chỉ kiểm function trả string đúng; phải xác nhận **trạng thái hàng trong database** sau khi commit/rollback.

---

## 28. Những lỗi thường gặp

**1. Thiếu `END IF;`.** Mỗi cấu trúc IF phải được đóng rõ.

**2. Viết `END;` thay `END IF;`.** `END;` đóng khối PL/pgSQL, không đóng IF.

**3. Viết `END;` thay `END CASE;` cho PL/pgSQL CASE statement.** Biểu thức SQL CASE và statement CASE có cú pháp kết thúc khác.

**4. Viết `END CASE;` bên trong SELECT SQL.** Biểu thức SQL CASE dùng `END`.

**5. Dùng `WHEN v_amount > 100` trong simple CASE với test_expression amount.** Khoảng giá trị nên dùng searched CASE hoặc IF.

**6. Cho rằng mọi CASE thiếu ELSE đều trả NULL.** Chỉ SQL CASE expression không ELSE trả NULL; PL/pgSQL CASE statement không match và thiếu ELSE ném `CASE_NOT_FOUND`.

**7. Dùng `IF x = NULL`.** Phải dùng `IS NULL`.

**8. Coi NULL Boolean là FALSE ở mọi biểu thức.** SQL có logic ba giá trị; IF chỉ không chọn nhánh khi không TRUE.

**9. Dùng `WHEN NULL` trong simple CASE để bắt SQL NULL.** Dùng searched CASE với `IS NULL` hoặc IF trước.

**10. Dùng `NOT IN` với tập có NULL mà quên UNKNOWN.** Cân nhắc `NOT EXISTS`.

**11. Không xử lý UNKNOWN trong điều kiện bảo mật.** Dùng `IS NOT TRUE` khi chỉ cho phép xác nhận TRUE.

**12. Đặt điều kiện tổng quát trước điều kiện cụ thể.** Nhánh sau trở nên không thể tới.

**13. Không dùng ngoặc trong điều kiện nhiều AND/OR có ý nghĩa bảo mật.** Dễ diễn đạt sai policy.

**14. Dựa vào thứ tự evaluation của SQL AND/OR để che phép chia cho 0.** Thiết kế guard hoặc `NULLIF` rõ.

**15. Dùng số nguyên làm Boolean trong IF.** Điều kiện cần kiểu Boolean.

**16. Quên dấu chấm phẩy sau câu lệnh và `END IF;`.** PL/pgSQL parser sẽ báo lỗi.

**17. Lẫn `ELSIF` với một IF lồng trong ELSE.** Khi lồng thật phải đóng đủ hai IF.

**18. Viết một function scalar có đường đi tới cuối mà không RETURN.** Runtime có thể báo lỗi.

**19. Dùng `RAISE NOTICE` khi thực sự cần từ chối giao dịch.** NOTICE không ngăn UPDATE tiếp tục.

**20. Bắt `WHEN OTHERS THEN NULL` để che mọi lỗi.** Có thể làm sai dữ liệu âm thầm.

**21. Dùng exception như câu IF thường xuyên.** Có thêm overhead và khó hiểu.

**22. SELECT INTO rồi kiểm FOUND sau một câu PERFORM khác.** FOUND có thể đã bị thay đổi.

**23. SELECT INTO không STRICT trên query nhiều rows mà giả định “row đầu” có thứ tự xác định.** Phải có unique condition hoặc thứ tự/giới hạn có chủ đích.

**24. Gọi SELECT có kết quả trong function mà không INTO/PERFORM đúng kiểu.** PL/pgSQL yêu cầu xử lý kết quả truy vấn phù hợp.

**25. Đặt tên biến trùng tên cột mà không dùng alias.** Có thể dẫn tới ambiguous reference.

**26. Coi `BEGIN ... END` của PL/pgSQL là transaction boundary.** Không đúng.

**27. Dùng CASE statement để cập nhật từng row khi SQL CASE expression đủ.** Có thể gây overhead không cần thiết.

**28. Giả định SQL CASE luôn xử lý an toàn mọi biểu thức lỗi vì không chọn nhánh.** Một số biểu thức hằng có thể bị planner xử lý trước runtime; nên thiết kế toán học/kiểu dữ liệu an toàn.

**29. Thay trạng thái invoice bằng UPDATE không có lock khi có nhiều writers.** Dễ gây race nếu quy trình kiểm tra/delta có nhiều bước.

**30. SELECT FOR UPDATE nhưng transaction giữ mở quá lâu.** Tăng lock contention.

**31. Kiểm tra tenant_id chỉ ở SELECT rồi UPDATE không scope theo tenant.** Thiết kế scope nhất quán và phân quyền.

**32. Coi parameter tenant_id do client gửi là cơ chế phân quyền duy nhất.** Cần authentication, authorization, grants/RLS khi phù hợp.

**33. Coi CHECK constraint là đủ thay state machine.** Constraint kiểm tra trạng thái hiện tại, không luôn biểu diễn chuyển đổi cũ → mới.

**34. Gửi lại payment request rồi cập nhật lại paid_at.** Có thể làm mất tính idempotent của workflow.

**35. Trigger guard không xét OLD/NEW trong các chuyển trạng thái.** Có thể cho phép chuyển ngược không hợp lệ.

**36. Trigger UPDATE OF status bỏ qua thay đổi status do trigger khác tạo.** Xem thứ tự/cấu trúc triggers.

**37. Viết một CASE không ELSE với input ngoài danh mục, nhưng không biết sẽ có CASE_NOT_FOUND.** Dùng ELSE RAISE hoặc ELSE NULL theo policy.

**38. Cho rằng SQL CASE và PL/pgSQL CASE có cùng hành vi missing ELSE.** Không.

**39. Dùng `COALESCE` để gộp trạng thái UNKNOWN với FALSE trong nghiệp vụ cần ba trạng thái.** Làm mất thông tin.

**40. Tự tối ưu bằng nhiều nhánh IF mà không có test ranh giới.** Dễ sai với mốc 0, 100, 1000 và NULL.

---

## 29. Bài tập thực hành có đáp án

### Bài 1 — IF không ELSE

**Yêu cầu:** ghi NOTICE khi số lượng âm.

**Đáp án:**

```sql
IF v_quantity < 0 THEN
    RAISE NOTICE 'Negative quantity';
END IF;
```

Đây là thân khối PL/pgSQL, `v_quantity` phải được khai báo.

### Bài 2 — IF ... ELSE

**Yêu cầu:** phân biệt số lớn hơn 0 với số không lớn hơn 0.

```sql
IF v_number > 0 THEN
    RAISE NOTICE 'Positive';
ELSE
    RAISE NOTICE 'Non-positive or NULL';
END IF;
```

**Giải thích:** Với NULL, điều kiện UNKNOWN nên vào ELSE. Nếu muốn ba trạng thái, dùng `IS NULL` trước.

### Bài 3 — Ba trạng thái Boolean

**Yêu cầu:** tách TRUE, FALSE và NULL.

```sql
IF v_flag IS TRUE THEN
    RAISE NOTICE 'TRUE';
ELSIF v_flag IS FALSE THEN
    RAISE NOTICE 'FALSE';
ELSE
    RAISE NOTICE 'UNKNOWN';
END IF;
```

### Bài 4 — Phân loại khoảng

**Yêu cầu:** amount âm là lỗi, 0 là ZERO, dưới 100 là SMALL, từ 100 là LARGE.

```sql
IF v_amount IS NULL THEN
    RAISE EXCEPTION 'Missing amount';
ELSIF v_amount < 0 THEN
    RAISE EXCEPTION 'Negative amount';
ELSIF v_amount = 0 THEN
    v_label := 'ZERO';
ELSIF v_amount < 100 THEN
    v_label := 'SMALL';
ELSE
    v_label := 'LARGE';
END IF;
```

### Bài 5 — Thứ tự nhánh

```sql
IF v_amount >= 100 THEN
    v_label := 'MEDIUM';
ELSIF v_amount >= 1000 THEN
    v_label := 'LARGE';
END IF;
```

**Hỏi:** với 1500 trả gì?

**Đáp án:** `MEDIUM` vì nhánh đầu tiên đã TRUE. Phải đưa `>=1000` lên trước.

### Bài 6 — Simple CASE

**Yêu cầu:** ánh xạ status draft/issued/paid sang nhãn tiếng Anh.

```sql
CASE v_status
    WHEN 'draft' THEN
        v_label := 'DRAFT';
    WHEN 'issued' THEN
        v_label := 'OPEN';
    WHEN 'paid' THEN
        v_label := 'SETTLED';
    ELSE
        v_label := 'OTHER';
END CASE;
```

### Bài 7 — Nhóm nhiều giá trị trong simple CASE

```sql
CASE v_status
    WHEN 'draft', 'issued' THEN
        v_label := 'UNPAID';
    WHEN 'paid' THEN
        v_label := 'SETTLED';
    ELSE
        v_label := 'OTHER';
END CASE;
```

**Đáp án:** Một WHEN có thể có nhiều giá trị trong PL/pgSQL simple CASE.

### Bài 8 — Searched CASE

```sql
CASE
    WHEN v_score IS NULL THEN
        v_grade := 'UNKNOWN';
    WHEN v_score >= 90 THEN
        v_grade := 'A';
    WHEN v_score >= 70 THEN
        v_grade := 'B';
    ELSE
        v_grade := 'C';
END CASE;
```

### Bài 9 — CASE_NOT_FOUND

**Hỏi:** PL/pgSQL CASE không ELSE và không match có trả NULL không?

**Đáp án:** Không. Nó phát sinh `CASE_NOT_FOUND`.

### Bài 10 — ELSE NULL

**Yêu cầu:** CASE không làm gì với trạng thái lạ.

```sql
CASE v_status
    WHEN 'paid' THEN
        RAISE NOTICE 'Paid';
    ELSE
        NULL;
END CASE;
```

**Giải thích:** `NULL;` là câu lệnh không làm gì trong PL/pgSQL.

### Bài 11 — SQL CASE expression thiếu ELSE

```sql
SELECT CASE WHEN 1 > 10 THEN 'yes' END AS result;
```

**Đáp án:** Trả SQL NULL, khác PL/pgSQL CASE statement.

### Bài 12 — END CASE hay END?

**Hỏi:** `SELECT CASE ... END CASE` có đúng không?

**Đáp án:** Không theo cú pháp SQL CASE expression. Biểu thức SQL dùng `END`; PL/pgSQL CASE statement dùng `END CASE;`.

### Bài 13 — Kiểm tra NULL

```sql
IF v_value = NULL THEN
    ...
END IF;
```

**Đáp án:** Sai cách kiểm tra. Dùng `IF v_value IS NULL THEN`.

### Bài 14 — Permission nullable

**Yêu cầu:** chỉ tiếp tục khi `p_approved=TRUE`.

```sql
IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;
```

### Bài 15 — AND/OR

**Yêu cầu:** người dùng phải active và phải là admin hoặc owner.

```sql
IF p_is_active IS TRUE
   AND (p_is_admin IS TRUE OR p_is_owner IS TRUE) THEN
    RAISE NOTICE 'Authorized';
ELSE
    RAISE EXCEPTION 'Not authorized';
END IF;
```

### Bài 16 — NOT IN có NULL

```sql
SELECT 9 NOT IN (1, 2, NULL);
```

**Đáp án:** Kết quả là NULL, không phải TRUE.

### Bài 17 — SELECT INTO và FOUND

**Yêu cầu:** lấy status invoice và báo lỗi nếu thiếu.

```sql
SELECT i.status INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

IF NOT FOUND THEN
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

**Lưu ý:** Kiểm tra FOUND ngay sau SELECT.

### Bài 18 — Vì sao PERFORM giữa SELECT và IF FOUND nguy hiểm?

**Đáp án:** `PERFORM` có thể thay đổi giá trị `FOUND`, làm IF kiểm tra kết quả của PERFORM thay vì SELECT trước đó.

### Bài 19 — INTO STRICT

**Hỏi:** `SELECT INTO STRICT` khi không có hàng gây gì?

**Đáp án:** Lỗi `NO_DATA_FOUND`. Nếu nhiều hàng, lỗi `TOO_MANY_ROWS`.

### Bài 20 — RAISE NOTICE hay RAISE EXCEPTION?

**Tình huống:** Amount âm không được ghi vào invoice.

**Đáp án:** Cần `RAISE EXCEPTION` hoặc constraint để từ chối thao tác; `NOTICE` chỉ thông báo và không tự ngăn ghi.

### Bài 21 — RETURN sớm

**Yêu cầu:** trả UNKNOWN nếu đầu vào NULL, nếu không trả POSITIVE hoặc OTHER.

```sql
IF p_value IS NULL THEN
    RETURN 'UNKNOWN';
END IF;

IF p_value > 0 THEN
    RETURN 'POSITIVE';
END IF;

RETURN 'OTHER';
```

### Bài 22 — Hóa đơn draft

**Tình huống:** invoice 1 bắt đầu ở `draft` và gọi `issue_invoice(1,1)`.

**Đáp án:** Function khóa row, chọn nhánh draft, cập nhật trạng thái sang issued và trả `ISSUED`.

### Bài 23 — Retry issue

**Tình huống:** gọi `issue_invoice(1,1)` lần hai.

**Đáp án:** Trả `ALREADY_ISSUED` và không phát hành lại.

### Bài 24 — Sai tenant

**Tình huống:** invoice 1 thuộc tenant 1, gọi `issue_invoice(1,2)`.

**Đáp án:** SELECT theo cả invoice ID và tenant ID không có row; `NOT FOUND` gây lỗi theo contract.

### Bài 25 — Paid → issued

**Hỏi:** Vì sao function từ chối phát hành lại invoice paid?

**Đáp án:** State machine không cho phép chuyển ngược từ trạng thái cuối `paid` sang `issued`; cần guard để tránh sai lệch nghiệp vụ.

### Bài 26 — SELECT FOR UPDATE

**Hỏi:** Tại sao lấy row và khóa trước khi chọn CASE?

**Đáp án:** Giúp phối hợp các transaction đồng thời sửa cùng hóa đơn, giảm race giữa kiểm tra trạng thái và cập nhật. Không thay toàn bộ transaction design hay phân quyền.

### Bài 27 — Trigger guard

**Yêu cầu:** ngăn `paid → draft`.

**Đáp án:** Trigger `BEFORE UPDATE` có thể kiểm tra `OLD.status='paid'` và `NEW.status IS DISTINCT FROM OLD.status`, rồi `RAISE EXCEPTION` nếu chuyển trạng thái không hợp lệ.

### Bài 28 — Khi nào dùng SQL CASE thay PL/pgSQL IF?

**Đáp án:** Khi chỉ cần tính/ghi một giá trị theo điều kiện cho nhiều rows trong một câu `SELECT`/`UPDATE`, SQL CASE theo tập hợp thường đơn giản và hiệu quả hơn procedural loop.

### Bài 29 — CASE trong ORDER BY

**Yêu cầu:** issued trước draft, rồi paid.

```sql
SELECT invoice_id, status
FROM plpgsql_cond_lab.invoices
ORDER BY
    CASE status
        WHEN 'issued' THEN 1
        WHEN 'draft' THEN 2
        WHEN 'paid' THEN 3
        ELSE 4
    END,
    invoice_id;
```

### Bài 30 — Aggregate có điều kiện

**Yêu cầu:** tổng amount paid theo tenant.

```sql
SELECT
    tenant_id,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0
    ) AS paid_total
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id;
```

### Bài 31 — Nguy cơ EXCEPTION WHEN OTHERS THEN NULL

**Đáp án:** Nuốt lỗi có thể che constraint violation hoặc bug, khiến quy trình tiếp tục ở trạng thái sai. Chỉ bắt exception cụ thể và xử lý có chủ đích.

### Bài 32 — BEGIN ... END

**Hỏi:** `BEGIN ... END` trong function có tương đương `BEGIN TRANSACTION ... COMMIT` không?

**Đáp án:** Không. Đó là khối PL/pgSQL, không tự tạo một transaction boundary mới.

### Bài 33 — Transaction timestamp

**Hỏi:** Vì sao `transaction_timestamp()` phù hợp cho nhiều thao tác cần chung mốc?

**Đáp án:** Nó cố định tại thời điểm bắt đầu transaction hiện tại, giúp các câu lệnh trong cùng transaction có chung mốc tham chiếu.

### Bài 34 — Test NULL bằng assertion

```sql
DO $test$
DECLARE
    v_label text;
BEGIN
    v_label := plpgsql_cond_lab.classify_amount(NULL);

    IF v_label IS DISTINCT FROM 'UNKNOWN' THEN
        RAISE EXCEPTION 'Expected UNKNOWN, got %', v_label;
    END IF;
END;
$test$;
```

**Đáp án:** Dùng `IS DISTINCT FROM` giúp assertion phát hiện cả kết quả NULL ngoài dự kiến.

### Bài 35 — Test mốc 100

```sql
SELECT plpgsql_cond_lab.classify_amount(100);
```

**Đáp án:** `MEDIUM` theo function của lab, vì điều kiện `p_amount < 100` đã sai tại đúng 100.

### Bài 36 — Test mốc 1000

```sql
SELECT plpgsql_cond_lab.classify_amount(1000);
```

**Đáp án:** `LARGE` theo function của lab.

---

## 30. Checklist khi viết IF/CASE trong PL/pgSQL

### Cú pháp

1. Dùng `IF ... THEN ... END IF;` đúng dấu chấm phẩy.
2. Dùng `ELSIF` cho chuỗi điều kiện thay thế.
3. Dùng `CASE test_expression ... END CASE;` khi so một trạng thái với nhiều giá trị.
4. Dùng `CASE WHEN condition ... END CASE;` cho nhiều biểu thức Boolean.
5. Phân biệt SQL `CASE ... END` và PL/pgSQL `CASE ... END CASE;`.
6. Có `ELSE` hợp lý cho mọi giá trị đầu vào, hoặc hiểu rõ `CASE_NOT_FOUND`.

### Tính đúng đắn

7. Có xử lý `NULL` bằng `IS NULL`/`IS NOT NULL` thay vì `= NULL`.
8. Với quyền/approval nullable, policy có cần `IS NOT TRUE` không?
9. Đặt điều kiện cụ thể trước điều kiện rộng.
10. Dùng ngoặc cho các điều kiện AND/OR có ý nghĩa khác nhau.
11. Không dựa vào short-circuit SQL như guard tổng quát cho chia 0.
12. Đặt cận khoảng đúng `<`/`<=`/`>`/`>=`.
13. Không trộn kiểu số/text trong những so sánh có semantics khác.
14. Không che lỗi bằng `ELSE NULL` khi input không hợp lệ phải bị từ chối.
15. Không nhầm NOTICE với EXCEPTION.

### Query và concurrency

16. Đặt alias bảng và tên biến `p_`/`v_` rõ ràng.
17. Dùng `SELECT INTO` đúng cú pháp PL/pgSQL.
18. Kiểm tra `FOUND` ngay sau statement thiết lập nó.
19. Dùng `INTO STRICT` khi cần đúng một row và chấp nhận exception.
20. Với chuyển trạng thái có race, cân nhắc `SELECT ... FOR UPDATE`/atomic UPDATE.
21. Kiểm tra tenant scope và authorization thực tế, không chỉ tham số client.
22. Thêm constraint ở DB cho bất biến trạng thái hiện tại.
23. Nếu state machine cần OLD → NEW, thiết kế trigger/function phù hợp.
24. Tránh transaction giữ lock quá lâu.

### Hiệu năng và kiểm thử

25. Ưu tiên SQL set-based CASE cho ánh xạ nhiều rows đơn giản.
26. Không dùng exception như nhánh IF bình thường.
27. Test NULL, FALSE, TRUE riêng khi có Boolean nullable.
28. Test các mốc cận 0, 100, 1000.
29. Test trạng thái không nằm trong danh mục.
30. Test retry cùng yêu cầu và tính idempotent.
31. Test nhiều sessions cập nhật cùng row nếu workflow có concurrency.
32. Test cả giá trị RETURN và trạng thái database sau transaction.
33. Đảm bảo mỗi đường đi của scalar function có RETURN hoặc RAISE.
34. Log có kiểm soát, không làm lộ dữ liệu nhạy cảm qua NOTICE.
35. Không dùng `EXPLAIN (ANALYZE)` cho DML production như thể nó chỉ xem trước.

---

## 31. Tổng kết

`IF` và `CASE` là hai cấu trúc điều kiện quan trọng nhất trong PL/pgSQL:

- **`IF`** phù hợp với guard clauses, validation và điều kiện phức hợp; `ELSE` có thể bỏ qua. Nếu điều kiện là `NULL`, nhánh `THEN` không được chọn.
- **Simple `CASE`** phù hợp khi so **một biểu thức** với nhiều giá trị rời rạc. Có thể gom nhiều giá trị trong một `WHEN`.
- **Searched `CASE`** phù hợp với khoảng số, nhiều Boolean predicates và những điều kiện có thứ tự ưu tiên.
- **PL/pgSQL `CASE` statement** kết thúc bằng `END CASE;` và nếu không nhánh nào match, không có ELSE thì phát sinh `CASE_NOT_FOUND`.
- **SQL `CASE` expression** kết thúc bằng `END`, trả một giá trị và không có ELSE thì trả NULL. Nó thường phù hợp hơn cho xử lý set-based trong `SELECT`/`UPDATE`.

Khi điều kiện dựa trên dữ liệu đã truy vấn, hãy kiểm tra `FOUND` đúng thời điểm, phân biệt no-row với NULL, bảo vệ chuyển trạng thái bằng cơ chế concurrency phù hợp và dùng `RAISE EXCEPTION` khi thao tác không hợp lệ phải bị từ chối. Với yêu cầu retry, chỉ thiết kế nhánh “đã xử lý” một cách có chủ đích; không để việc gọi lại âm thầm thay đổi timestamp hoặc cộng trùng nghiệp vụ.

**Câu hỏi tự kiểm tra:** Với một đầu vào `NULL`, một trạng thái mới chưa có trong danh mục, và hai transactions cùng cập nhật một hàng, code của bạn sẽ đi vào nhánh nào, trả kết quả hay ném lỗi gì, và những thay đổi đã được commit có còn đúng không? Nếu trả lời được cụ thể cho cả ba trường hợp, bạn đã nắm được tinh thần sử dụng `IF` và `CASE` an toàn trong PL/pgSQL.

### Tài liệu PostgreSQL chính thức

- [PL/pgSQL — Conditional Statements](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-CONDITIONALS).
- [PL/pgSQL — Structure of PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-structure.html).
- [PL/pgSQL — Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html).
- [PL/pgSQL — Statements Executing a Query](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-SQL-ONEROW).
- [PL/pgSQL — Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html).
- [PL/pgSQL — Trapping Errors](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING).
- [SQL Conditional Expressions — CASE, COALESCE, NULLIF](https://www.postgresql.org/docs/current/functions-conditional.html).
- [Comparison Functions and Operators — NULL](https://www.postgresql.org/docs/current/functions-comparison.html).
- [SQL Syntax — Value Expressions](https://www.postgresql.org/docs/current/sql-expressions.html).
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html).
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html).
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
