# Phân biệt BOOLEAN trong PL/SQL và SQL theo phiên bản hỗ trợ

Trong Oracle Database, từ **`BOOLEAN`** có thể xuất hiện trong hai ngữ cảnh: **biến và biểu thức của PL/SQL** và **kiểu dữ liệu, biểu thức của SQL**. Hai ngữ cảnh này từng có khả năng hỗ trợ khác nhau theo phiên bản. Đây là lý do một đoạn `DECLARE v_ok BOOLEAN := TRUE;` chạy tốt trên Oracle 19c nhưng một bảng có cột `is_active BOOLEAN` lại không tạo được trên cùng database.

Điểm thay đổi quan trọng là **Oracle Database 23c/23ai đưa kiểu dữ liệu `BOOLEAN` vào SQL**. Các bản phát hành trước đó, bao gồm Oracle 19c và 21c, đã hỗ trợ `BOOLEAN` trong **PL/SQL** nhưng **chưa có kiểu cột `BOOLEAN` gốc trong SQL**. Khi làm việc với một hệ thống nhiều phiên bản, lập trình viên cần chọn cách lưu cờ trạng thái, viết truy vấn và ánh xạ JDBC dựa trên **phiên bản database thực tế**, đồng thời kiểm thử driver/ORM đang sử dụng.

## 1. Trước hết phân biệt hai ngôn ngữ của Oracle

**SQL** dùng để định nghĩa và thao tác dữ liệu: `CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `WHERE`, `JOIN`, `GROUP BY` và các biểu thức truy vấn. **PL/SQL** là ngôn ngữ thủ tục mở rộng SQL của Oracle, có biến, kiểu dữ liệu, `IF`, vòng lặp, exception, procedure, function và package.

```text
            ỨNG DỤNG / SQL CLIENT
                     |
          +----------+----------+
          |                     |
          v                     v
      ORACLE SQL             ORACLE PL/SQL
  CREATE TABLE, SELECT,      DECLARE, IF, LOOP,
  INSERT, WHERE, CASE        FUNCTION, PROCEDURE
          |                     |
          | SQL BOOLEAN từ      | PL/SQL BOOLEAN đã
          | Oracle 23c/23ai     | có từ các bản cũ
          +----------+----------+
                     |
                ORACLE DATABASE
```

Ngay cả trên Oracle 19c, điều kiện trong `WHERE` vẫn có logic **TRUE, FALSE, UNKNOWN**. Chẳng hạn `WHERE amount > 0` kiểm tra một điều kiện đúng/sai/không xác định. Tuy nhiên, **có điều kiện Boolean trong ngữ pháp SQL không đồng nghĩa có một kiểu dữ liệu SQL `BOOLEAN` để lưu vào cột hoặc trả về như một giá trị**. Sự khác biệt giữa *logical condition* và *first-class SQL data type* là cốt lõi của bài này.

### 1.1. Bảng hỗ trợ theo phiên bản

| Phiên bản Oracle Database | Biến `BOOLEAN` trong PL/SQL | Cột `BOOLEAN` trong `CREATE TABLE` | Biểu thức Boolean là giá trị SQL độc lập | Cách lưu cờ trạng thái phổ biến |
|---|---|---|---|---|
| 11g/12c/18c | Có | Không | Chưa có kiểu SQL `BOOLEAN` | `NUMBER(1)`, `CHAR(1)`, `VARCHAR2` có constraint |
| **19c** | **Có** | **Không** | Không dùng Boolean như kiểu giá trị SQL | `NUMBER(1)` hoặc `CHAR(1)` có ràng buộc |
| **21c** | **Có** | **Không** | Không có kiểu dữ liệu SQL `BOOLEAN` gốc | Vẫn dùng kiểu lưu trữ thay thế |
| **23c/23ai** | **Có** | **Có** | **Có**, gồm literal `TRUE`/`FALSE` và biểu thức Boolean | Có thể dùng trực tiếp `BOOLEAN` nếu toàn bộ hệ sinh thái hỗ trợ |
| **26ai và các phiên bản có hỗ trợ SQL BOOLEAN tiếp theo** | Có | Có | Có | `BOOLEAN` được hỗ trợ; kiểm tra driver, ORM và đường nâng cấp |

> **Chú ý về tên phiên bản:** tài liệu và ví dụ có thể gọi tính năng mới là “Oracle Database 23c SQL BOOLEAN” hoặc “Oracle Database 23ai SQL BOOLEAN”. Khi chuẩn bị chạy script, hãy đối chiếu **release đang thực sự kết nối**. Không suy luận từ tên tệp SQL, tên service, phiên bản SQL Developer hoặc phiên bản JDBC driver.

**Hệ quả trực tiếp:** một schema migration sử dụng `CREATE TABLE ... (flag BOOLEAN)` không thể được xem là tương thích ngược với Oracle 19c/21c. Nếu ứng dụng phải chạy trên cả 19c và 23ai, cần một chiến lược lưu trữ/migration có điều kiện rõ ràng.

## 2. PL/SQL BOOLEAN: đã có từ trước Oracle 23ai

Kiểu `BOOLEAN` trong PL/SQL có ba trạng thái:

- `TRUE`: điều kiện đúng.
- `FALSE`: điều kiện sai.
- `NULL`: không biết hoặc chưa xác định; **khác** `FALSE`.

Đây là một kiểu logic dùng trong **biến, parameter và kết quả của hàm PL/SQL**. Ví dụ sau dùng cú pháp PL/SQL, chạy trên các phiên bản Oracle thông dụng trước và sau 23ai:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_paid     BOOLEAN := TRUE;
    v_verified BOOLEAN := NULL;
BEGIN
    IF v_paid THEN
        DBMS_OUTPUT.PUT_LINE('Đơn hàng đã thanh toán');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Đơn hàng chưa được xác nhận thanh toán');
    END IF;

    IF v_verified IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Trạng thái xác minh chưa biết');
    END IF;
END;
/
```

Đoạn mã sử dụng `DBMS_OUTPUT.PUT_LINE` với **chuỗi ký tự**. Trên các phiên bản cũ, `DBMS_OUTPUT.PUT_LINE(v_paid)` với `v_paid` là `BOOLEAN` không có overload nhận Boolean như một `VARCHAR2` thông thường; vì thế chuyển thành chuỗi bằng `IF`/`CASE` là cách biểu đạt tương thích rộng.

### 2.1. `BOOLEAN` trong procedure và function

```sql
CREATE OR REPLACE PROCEDURE check_discount (
    p_is_vip IN BOOLEAN
) AS
BEGIN
    IF p_is_vip THEN
        DBMS_OUTPUT.PUT_LINE('Áp dụng quyền VIP');
    ELSIF p_is_vip IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Chưa xác định trạng thái VIP');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Không áp dụng quyền VIP');
    END IF;
END;
/

BEGIN
    check_discount(TRUE);
    check_discount(FALSE);
    check_discount(NULL);
END;
/
```

Ba lần gọi trên diễn ra **bên trong PL/SQL**. Điều này không chứng minh mọi ứng dụng hoặc mọi câu lệnh SQL cũ đều có thể bind/trả về `BOOLEAN` như một SQL column type. Khi gọi PL/SQL từ JDBC, OCI hoặc một công cụ bên ngoài, khả năng bind phụ thuộc driver/API và phiên bản; phải xem cơ chế được driver hỗ trợ thay vì coi nó giống thao tác với một cột SQL `BOOLEAN`.

### 2.2. `IF` xử lý `NULL` thế nào?

Trong PL/SQL, nhánh `THEN` của `IF expression THEN` được thực hiện **chỉ khi biểu thức bằng `TRUE`**. Khi biểu thức là `FALSE` hoặc `NULL`, Oracle đi sang `ELSIF`/`ELSE` theo điều kiện tương ứng.

```sql
DECLARE
    v_enabled BOOLEAN := NULL;
BEGIN
    IF v_enabled THEN
        DBMS_OUTPUT.PUT_LINE('TRUE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Không phải TRUE');
    END IF;

    IF NOT v_enabled THEN
        DBMS_OUTPUT.PUT_LINE('FALSE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Không phải FALSE');
    END IF;
END;
/
```

Với `v_enabled = NULL`, hai câu `IF` trên đều đi vào `ELSE`: `v_enabled` là `NULL`, và `NOT NULL` cũng là `NULL`. Vì vậy không thể dùng `IF NOT v_enabled` như phép kiểm tra chắc chắn giá trị là `FALSE` khi biến nullable.

Muốn phân biệt đủ ba trạng thái trong PL/SQL, sử dụng thứ tự:

```sql
IF v_enabled IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('UNKNOWN');
ELSIF v_enabled THEN
    DBMS_OUTPUT.PUT_LINE('TRUE');
ELSE
    DBMS_OUTPUT.PUT_LINE('FALSE');
END IF;
```

`NULL` có thể là trạng thái nghiệp vụ thật sự, ví dụ yêu cầu chưa được duyệt, dữ liệu chưa được đồng bộ hoặc user chưa trả lời. Không nên tự biến mọi `NULL` thành `FALSE` nếu điều đó thay đổi ý nghĩa nghiệp vụ.

### 2.3. Bảng chân trị ba giá trị

| A | `NOT A` | Ghi chú |
|---|---|---|
| `TRUE` | `FALSE` | Phủ định đúng thành sai |
| `FALSE` | `TRUE` | Phủ định sai thành đúng |
| `NULL` | `NULL` | Chưa biết vẫn chưa biết |

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| `TRUE` | `TRUE` | `TRUE` | `TRUE` |
| `TRUE` | `FALSE` | `FALSE` | `TRUE` |
| `TRUE` | `NULL` | `NULL` | `TRUE` |
| `FALSE` | `FALSE` | `FALSE` | `FALSE` |
| `FALSE` | `NULL` | `FALSE` | `NULL` |
| `NULL` | `NULL` | `NULL` | `NULL` |

Logic ba giá trị xuất hiện cả trong điều kiện SQL (kể cả trước 23ai) và trong `BOOLEAN` PL/SQL. Sự khác biệt theo phiên bản nằm ở **khả năng dùng Boolean như một giá trị dữ liệu SQL**.

## 3. Oracle 19c/21c: vì sao SQL không có cột `BOOLEAN`?

Trên Oracle 19c hoặc 21c, câu lệnh sau không được hỗ trợ:

```sql
-- KHÔNG chạy được trên Oracle 19c/21c:
CREATE TABLE lab_feature_flags (
    feature_id NUMBER PRIMARY KEY,
    enabled    BOOLEAN
);
```

Đây là **DDL SQL**. Dù PL/SQL ở cùng phiên bản cho phép `DECLARE v_enabled BOOLEAN;`, bộ kiểu dữ liệu cột của SQL chưa chứa `BOOLEAN`. Trên môi trường cũ, bạn có thể gặp lỗi kiểu dữ liệu không hợp lệ, chẳng hạn `ORA-00902`, tùy lệnh và phiên bản; không nên dự đoán mọi trường hợp đều cho cùng một mã lỗi.

Tương tự, một câu `SELECT TRUE FROM dual` hoặc `SELECT (amount > 0) FROM orders` **không thể được diễn giải như việc SQL 19c/21c trả về một cột kiểu Boolean**. Trên những phiên bản này, cú pháp *điều kiện* có thể xuất hiện trong `WHERE`, `CASE WHEN`, `HAVING`, nhưng việc chọn biểu thức điều kiện như một giá trị trả về độc lập không có hỗ trợ SQL `BOOLEAN` của 23ai.

### 3.1. Vẫn có thể dùng điều kiện đúng/sai trong `WHERE` và `CASE`

```sql
-- Tương thích với các phiên bản trước SQL BOOLEAN:
SELECT order_id, amount
FROM orders
WHERE amount > 0;

SELECT order_id,
       CASE WHEN amount > 0 THEN 1 ELSE 0 END AS has_positive_amount
FROM orders;
```

Ở đây `amount > 0` là một **SQL condition**; kết quả `CASE` có kiểu `NUMBER`, không phải kiểu SQL `BOOLEAN`. Không nên gán tên alias `has_positive_amount` rồi suy ra database đã có Boolean column.

### 3.2. Mẫu dùng `NUMBER(1)` với `CHECK`

Giải pháp thường dùng cho cờ hai trạng thái trong schema Oracle 19c/21c:

```sql
CREATE TABLE lab_flags_number (
    feature_id NUMBER PRIMARY KEY,
    enabled    NUMBER(1) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_lab_flags_number_enabled CHECK (enabled IN (0, 1))
);

INSERT INTO lab_flags_number (feature_id, enabled) VALUES (1, 1);
INSERT INTO lab_flags_number (feature_id, enabled) VALUES (2, 0);
COMMIT;

SELECT feature_id, enabled
FROM lab_flags_number
WHERE enabled = 1;
```

Ý nghĩa quy ước phải rõ: `1 = TRUE`, `0 = FALSE`. `NUMBER(1)` **không tự giới hạn chỉ 0 và 1**; ràng buộc `CHECK` giúp từ chối các giá trị không thuộc miền mong muốn. `NOT NULL` làm trạng thái chỉ còn hai giá trị. Nếu nghiệp vụ cần “chưa biết”, có thể bỏ `NOT NULL` và chấp nhận `NULL`, nhưng phải định nghĩa hành vi từ API đến SQL.

Nếu cột nullable, `CHECK (enabled IN (0,1))` **không tự cấm `NULL`**; trong Oracle, ràng buộc check cho phép trường hợp điều kiện không xác định (`UNKNOWN`) trừ khi có ràng buộc khác. Đây là lý do `NOT NULL` phải được khai báo tường minh khi cần dữ liệu hai trạng thái.

### 3.3. Mẫu dùng `CHAR(1)` với `Y/N`

```sql
CREATE TABLE lab_flags_char (
    feature_id NUMBER PRIMARY KEY,
    enabled    CHAR(1) DEFAULT 'N' NOT NULL,
    CONSTRAINT ck_lab_flags_char_enabled CHECK (enabled IN ('Y', 'N'))
);

INSERT INTO lab_flags_char (feature_id, enabled) VALUES (1, 'Y');
INSERT INTO lab_flags_char (feature_id, enabled) VALUES (2, 'N');
COMMIT;
```

`Y/N` dễ đọc khi kiểm tra bằng SQL thủ công nhưng đòi hỏi mapping rõ sang `Boolean` trong Java. Một ứng dụng khác dùng `'T'/'F'` hoặc `'TRUE'/'FALSE'` là **quy ước dữ liệu**, không phải SQL Boolean thực sự. Không trộn nhiều quy ước trong cùng schema nếu không có lý do và kế hoạch tương thích.

### 3.4. So sánh hai lựa chọn truyền thống

| Tiêu chí | `NUMBER(1)` + `CHECK (IN (0,1))` | `CHAR(1)` + `CHECK (IN ('Y','N'))` |
|---|---|---|
| Giá trị lưu | `1`, `0` | `'Y'`, `'N'` |
| Có phải kiểu `BOOLEAN` SQL gốc? | Không | Không |
| Dễ đọc khi query thủ công | Cần biết quy ước 1/0 | Khá trực quan nếu biết Y/N |
| Mapping JDBC/ORM | Có thể ánh xạ số sang Java Boolean qua converter/dialect | Thường dùng converter tường minh |
| Cần constraint? | Có để tránh số khác 0/1 | Có để tránh giá trị chữ khác Y/N |
| Có thể lưu `NULL`? | Có, nếu không `NOT NULL` | Có, nếu không `NOT NULL` |
| Chuyển sang SQL BOOLEAN khi nâng cấp | Cần migration và ánh xạ | Cần migration và ánh xạ |

Trong hệ thống đã vận hành, ưu tiên **giữ một quy ước nhất quán** và chỉ đổi kiểu khi đã xem xét schema, dữ liệu hiện có, client, stored procedures và khả năng rollback/forward fix.

## 4. Ranh giới PL/SQL và SQL trên phiên bản cũ

Một procedure PL/SQL nhận `BOOLEAN` không có nghĩa SQL ở Oracle 19c/21c có thể **lưu hoặc xuất trực tiếp** Boolean theo cách dùng SQL column.

```sql
-- PL/SQL trước 23ai: hàm có thể trả về BOOLEAN cho caller PL/SQL.
CREATE OR REPLACE FUNCTION lab_is_even (p_value IN NUMBER)
RETURN BOOLEAN
IS
BEGIN
    RETURN MOD(p_value, 2) = 0;
END;
/

-- Gọi từ PL/SQL trên các bản cũ:
BEGIN
    IF lab_is_even(10) THEN
        DBMS_OUTPUT.PUT_LINE('10 là số chẵn');
    END IF;
END;
/
```

Ở các phiên bản chưa hỗ trợ SQL BOOLEAN, không dùng kết quả `BOOLEAN` của hàm làm **một biểu thức giá trị trả về trong `SELECT`** theo cách sau:

```sql
-- Không phải truy vấn SQL hợp lệ trên Oracle 19c/21c:
SELECT lab_is_even(10) AS is_even
FROM dual;
```

Một cách tương thích rộng là cung cấp **wrapper trả về kiểu SQL có sẵn**, chẳng hạn `NUMBER` hoặc `VARCHAR2`. Wrapper phải chuyển `NULL` đúng ý nghĩa, tránh biến “không biết” thành `FALSE` ngoài chủ ý.

```sql
CREATE OR REPLACE FUNCTION lab_is_even_num (p_value IN NUMBER)
RETURN NUMBER
IS
    v_result BOOLEAN;
BEGIN
    v_result := lab_is_even(p_value);

    IF v_result IS NULL THEN
        RETURN NULL;
    ELSIF v_result THEN
        RETURN 1;
    ELSE
        RETURN 0;
    END IF;
END;
/

-- Dùng kết quả NUMBER trong SQL cũ:
SELECT lab_is_even_num(10) AS is_even_number
FROM dual;
```

Trong một số phiên bản và ngữ cảnh, SQL có khả năng gọi PL/SQL function có **tham số** Boolean thông qua cơ chế bind được hỗ trợ. Điều đó **không biến Boolean thành một SQL datatype đầy đủ**: không nên suy luận có thể dùng mọi literal, cột, giá trị trả về hoặc API bind theo cùng cách. Khi cần tương thích chặt với 19c/21c, API có tham số/giá trị trả về thuộc các kiểu SQL truyền thống thường đơn giản và ít gây nhầm lẫn hơn.

## 5. Oracle 23c/23ai: SQL BOOLEAN trở thành kiểu dữ liệu gốc

Oracle Database 23c/23ai hỗ trợ `BOOLEAN` ngay trong SQL, bao gồm cột, biểu thức và điều kiện. Kiểu SQL `BOOLEAN` có ba giá trị logic `TRUE`, `FALSE`, `NULL` (không xác định); cột `NOT NULL` giới hạn còn `TRUE` và `FALSE`.

```sql
-- CHỈ chạy trên Oracle Database có hỗ trợ SQL BOOLEAN (23c/23ai trở lên).
CREATE TABLE lab_flags_boolean (
    feature_id NUMBER PRIMARY KEY,
    feature_name VARCHAR2(100 CHAR) NOT NULL,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)
VALUES (1, 'new-checkout', TRUE);

INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)
VALUES (2, 'old-report', FALSE);

COMMIT;

SELECT feature_id, feature_name, enabled
FROM lab_flags_boolean;
```

Cột `enabled` giờ **thực sự là SQL `BOOLEAN`**. Trên một số tài liệu Oracle, từ khóa **`BOOL`** cũng được chấp nhận như một tên thay thế cho kiểu này. Tuy vậy, để tài liệu và migration dễ nhận diện, nên dùng `BOOLEAN` nhất quán.

### 5.1. `TRUE` và `FALSE` là literal SQL

Ở SQL 23ai, `TRUE` và `FALSE` là literal logic, không phải tên cột hay chuỗi `'TRUE'`, `'FALSE'`:

```sql
-- SQL BOOLEAN trực tiếp:
SELECT TRUE AS always_true,
       FALSE AS always_false
FROM dual;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS TRUE;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS FALSE;
```

`IS TRUE` và `IS FALSE` cho phép kiểm tra trạng thái rõ ràng. Với cột nullable, dùng thêm `IS NULL` khi cần phân biệt “chưa biết”. Biểu thức Boolean cũng có thể xuất hiện trong `SELECT` để trả về một giá trị Boolean:

```sql
SELECT feature_id,
       (feature_id > 1) AS has_large_id
FROM lab_flags_boolean;
```

Đây là điểm khác biệt đáng kể với SQL 19c/21c, nơi điều kiện như `feature_id > 1` có thể đứng trong `WHERE` nhưng chưa là một **giá trị kiểu SQL `BOOLEAN`** có thể trả về ở danh sách cột.

### 5.2. Viết điều kiện với Boolean SQL

```sql
-- Các cách diễn đạt về cờ TRUE:
SELECT feature_name
FROM lab_flags_boolean
WHERE enabled;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS TRUE;

-- Các cách diễn đạt về cờ FALSE:
SELECT feature_name
FROM lab_flags_boolean
WHERE NOT enabled;

SELECT feature_name
FROM lab_flags_boolean
WHERE enabled IS FALSE;
```

Trong bảng `enabled NOT NULL` ở ví dụ, các cách tương ứng cho kết quả đúng theo hai trạng thái. Nhưng khi cột **có thể `NULL`**, có khác biệt quan trọng: `WHERE NOT enabled` chỉ chọn hàng mà `enabled` là `FALSE`; **không** chọn hàng `NULL` vì `NOT NULL` vẫn là `NULL`, còn `WHERE` chỉ lấy điều kiện `TRUE`.

### 5.3. Boolean nullable và điều kiện `IS NOT TRUE`

Tạo một ví dụ khác cho trạng thái ba giá trị:

```sql
-- Oracle 23ai trở lên; cột được phép NULL.
CREATE TABLE lab_flags_nullable (
    id NUMBER PRIMARY KEY,
    approved BOOLEAN
);

INSERT INTO lab_flags_nullable VALUES (1, TRUE);
INSERT INTO lab_flags_nullable VALUES (2, FALSE);
INSERT INTO lab_flags_nullable VALUES (3, NULL);
COMMIT;
```

| Điều kiện SQL | Hàng được chọn | Ý nghĩa |
|---|---|---|
| `approved IS TRUE` | `id = 1` | Chỉ giá trị `TRUE` |
| `approved IS FALSE` | `id = 2` | Chỉ giá trị `FALSE` |
| `approved IS NULL` | `id = 3` | Chỉ giá trị chưa biết |
| `NOT approved` | `id = 2` | `NOT NULL` vẫn `NULL`, không chọn `id = 3` |
| `approved IS NOT TRUE` | `id = 2, 3` | Bao gồm `FALSE` **và** `NULL` |
| `approved IS NOT FALSE` | `id = 1, 3` | Bao gồm `TRUE` **và** `NULL` |

`IS NOT TRUE` **khác** `IS FALSE`. Câu SQL phục vụ nghiệp vụ “chưa được xác nhận là đã phê duyệt” có thể muốn cả `FALSE` và `NULL`; câu SQL phục vụ “đã từ chối” thường chỉ nên lấy `FALSE`. Đó là một quyết định nghiệp vụ, không chỉ là tối ưu cú pháp.

### 5.4. `CASE` có thể trả về kiểu nào?

Trong SQL 23ai, `BOOLEAN` có thể là kết quả của một biểu thức SQL tương thích:

```sql
-- Trả về Boolean trực tiếp:
SELECT feature_id,
       CASE
           WHEN feature_id = 1 THEN TRUE
           ELSE FALSE
       END AS is_first_feature
FROM lab_flags_boolean;

-- Nếu API cũ đang chờ NUMBER(1), có thể giữ contract số:
SELECT feature_id,
       CASE WHEN enabled IS TRUE THEN 1 ELSE 0 END AS enabled_num
FROM lab_flags_boolean;
```

Ở ví dụ thứ hai, `enabled NOT NULL` nên phép biến đổi `1/0` không mất trạng thái chưa biết. Nếu nguồn có thể `NULL` và API muốn giữ ba trạng thái, cần ánh xạ riêng `NULL`, ví dụ:

```sql
SELECT id,
       CASE
           WHEN approved IS TRUE THEN 1
           WHEN approved IS FALSE THEN 0
           ELSE NULL
       END AS approved_num
FROM lab_flags_nullable;
```

Không nên dùng `ELSE 0` cho cả `FALSE` và `NULL` trừ khi nghiệp vụ định nghĩa chúng tương đương.

## 6. SQL BOOLEAN và PL/SQL BOOLEAN từ 23ai: tương tác thuận tiện hơn

Khi SQL có datatype `BOOLEAN`, việc trao đổi giá trị giữa PL/SQL và SQL trở nên trực tiếp hơn. Một hàm PL/SQL có kết quả Boolean có thể được dùng như biểu thức giá trị SQL trong những trường hợp phiên bản hỗ trợ:

```sql
-- Hàm PL/SQL tương tự ví dụ trước:
CREATE OR REPLACE FUNCTION lab_is_positive (p_value IN NUMBER)
RETURN BOOLEAN
IS
BEGIN
    IF p_value IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_value > 0;
END;
/

-- Oracle 23ai trở lên: SQL nhận giá trị BOOLEAN trả về.
SELECT lab_is_positive(10) AS positive_check
FROM dual;
```

Trên các phiên bản cũ, một function có `RETURN BOOLEAN` dùng được từ PL/SQL nhưng **không thể coi kết quả đó là kiểu cột SQL trả về trong `SELECT`**. Tính năng ở 23ai làm đơn giản hóa contract SQL/PLSQL cho hệ thống chạy trên phiên bản mới.

PL/SQL vẫn có ý nghĩa riêng: `BOOLEAN` trong một biểu thức PL/SQL điều khiển `IF`, `LOOP` và procedure; SQL `BOOLEAN` là kiểu dữ liệu có thể tồn tại trong schema, được truy vấn qua driver. Việc cả hai hỗ trợ Boolean không loại bỏ khác biệt về **scope, transaction, SQL syntax và quyền**.

### 6.1. Không phải mọi thành phần cũ tự hiểu kiểu mới

Một ứng dụng kết nối 23ai có thể sử dụng driver hoặc ORM cũ đã thiết kế mapping `Boolean` sang `NUMBER(1)` hoặc `CHAR(1)`. Dù database có SQL BOOLEAN, vẫn cần kiểm tra:

- JDBC/OCI/ODP.NET hoặc driver được dùng có hỗ trợ kiểu `BOOLEAN` của server không?
- Hibernate/JPA dialect có chọn đúng SQL type cho `Boolean` ở **phiên bản Oracle đích** không?
- Code đọc `NULL` vào `boolean` nguyên thủy có làm mất trạng thái chưa biết không?
- Native query, stored procedure, schema migration, serializer và report/export có biết kiểu mới không?
- Nếu dùng nhiều datasource, có môi trường 19c/21c nào còn dùng schema cũ không?

**Phiên bản database và phiên bản client là hai trục tương thích.** Không nâng cấp cách lưu chỉ dựa vào việc ứng dụng đã cập nhật JDK hoặc Spring Boot.

## 7. Chuyển đổi giữa BOOLEAN, NUMBER và chuỗi

Trên SQL 23ai trở lên, Oracle có khả năng chuyển đổi kiểu dữ liệu logic và cung cấp các phép chuyển đổi tường minh như `TO_BOOLEAN`, `TO_CHAR` hoặc `CAST` theo ngữ cảnh được hỗ trợ.

### 7.1. Chuyển đổi tường minh trong SQL mới

```sql
-- Chỉ dùng trên phiên bản SQL BOOLEAN được hỗ trợ:
SELECT TO_BOOLEAN(1) AS bool_from_one,
       TO_BOOLEAN(0) AS bool_from_zero,
       TO_BOOLEAN('true') AS bool_from_text
FROM dual;

SELECT TO_CHAR(TRUE) AS true_as_text,
       TO_CHAR(FALSE) AS false_as_text
FROM dual;
```

`TO_BOOLEAN` hỗ trợ các đầu vào số/chuỗi hợp lệ theo quy tắc của phiên bản; với đầu vào số, **0 là `FALSE` và số khác 0 được chuyển thành `TRUE`**. Do đó, nếu dữ liệu legacy vô tình chứa `2` hoặc `-1`, việc chuyển số thẳng sang Boolean có thể biến chúng thành `TRUE` thay vì báo lỗi như một miền `0/1` mong muốn. **Phải làm sạch và ràng buộc dữ liệu trước migration**.

Các giá trị chuỗi được chấp nhận phụ thuộc quy tắc chuyển đổi Oracle, có thể gồm dạng biểu diễn như `'true'`/`'false'`. Trong migration production, nên **định nghĩa mapping tường minh** thay vì phụ thuộc vào mọi dạng chuỗi Oracle có thể tự chuyển.

Ví dụ chuyển cờ `NUMBER(1)` sang biểu thức Boolean có bảo vệ:

```sql
-- SQL BOOLEAN trên Oracle 23ai+; cột legacy_enabled chứa 0/1/NULL.
SELECT feature_id,
       CASE
           WHEN legacy_enabled = 1 THEN TRUE
           WHEN legacy_enabled = 0 THEN FALSE
           ELSE NULL
       END AS enabled_bool
FROM legacy_flags;
```

Đây là biểu thức minh họa trên bảng `legacy_flags` có sẵn; cần tạo schema/tài liệu migration thực tế trước khi chạy. So với `TO_BOOLEAN(legacy_enabled)`, `CASE` diễn đạt rõ miền dữ liệu được chấp nhận và cách xử lý giá trị ngoài miền. Nếu thấy giá trị ngoài `0/1/NULL`, phải điều tra hoặc báo lỗi theo quy trình, không tự gộp thành một nhánh mà làm thay đổi nghiệp vụ.

### 7.2. Đổi từ Boolean sang chuỗi để hiển thị

Với SQL Boolean 23ai+, có thể tạo nhãn để hiển thị và xử lý cả trạng thái chưa biết:

```sql
SELECT id,
       CASE
           WHEN approved IS TRUE THEN 'APPROVED'
           WHEN approved IS FALSE THEN 'REJECTED'
           ELSE 'PENDING'
       END AS approval_label
FROM lab_flags_nullable;
```

Việc chuyển thành nhãn là **chức năng trình bày**. Không dùng nhãn đa ngôn ngữ làm dạng lưu trữ chuẩn trong database nếu ứng dụng còn cần lọc, sắp xếp hoặc đồng bộ trạng thái nghiệp vụ. Nếu trạng thái có nhiều hơn hai giá trị có ý nghĩa riêng như `PENDING`, `APPROVED`, `REJECTED`, cân nhắc **mã trạng thái/enum** thay vì ép nó thành Boolean.

### 7.3. Chuyển đổi PL/SQL trên phiên bản cũ

Trong PL/SQL 19c/21c, wrapper tường minh bằng `IF` hoặc `CASE` là cách rõ nghĩa:

```sql
DECLARE
    v_flag BOOLEAN := NULL;
    v_number NUMBER(1);
BEGIN
    IF v_flag IS NULL THEN
        v_number := NULL;
    ELSIF v_flag THEN
        v_number := 1;
    ELSE
        v_number := 0;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Mapped flag: ' || NVL(TO_CHAR(v_number), 'NULL'));
END;
/
```

Từ Oracle 23ai trở đi có thêm khả năng chuyển đổi nhưng không nên áp dụng một hàm mới vào script cần chạy trên 19c. Khi xây thư viện chung, tách code theo baseline phiên bản hoặc tiếp tục dùng mapping kiểu cũ cho các môi trường chưa nâng cấp.

## 8. Tương thích ứng dụng Java/JDBC: `boolean` khác `Boolean`

Trong Java:

- `boolean` là kiểu nguyên thủy, chỉ có `true` hoặc `false`.
- `java.lang.Boolean` là kiểu wrapper, có thể nhận `true`, `false` hoặc `null`.

Khi cột SQL có thể `NULL`, việc đọc vào `boolean` nguyên thủy có thể làm **mất trạng thái chưa biết**. JDBC `ResultSet.getBoolean(...)` trả về Java `boolean`; khi cột SQL `NULL`, API chuẩn trả về `false` và phải gọi **`ResultSet.wasNull()`** để biết giá trị ban đầu có phải `NULL` hay không.

### 8.1. Đọc SQL BOOLEAN trên Oracle 23ai+ qua JDBC hỗ trợ

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class BooleanFlagReader {
    public static Boolean readFlag(Connection connection, long featureId)
            throws SQLException {
        String sql = "SELECT enabled FROM lab_flags_boolean WHERE feature_id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, featureId);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null; // Không tìm thấy record; caller phải phân biệt nếu cần.
                }

                boolean value = result.getBoolean("enabled");
                return result.wasNull() ? null : Boolean.valueOf(value);
            }
        }
    }
}
```

Ở bảng `lab_flags_boolean` ví dụ, cột `enabled` là `NOT NULL`, nhưng code minh họa cách JDBC xử lý `NULL` nói chung. Một API nghiệp vụ thật nên **phân biệt không có bản ghi** với bản ghi có cờ `NULL`, ví dụ dùng `Optional`, record kết quả hoặc exception rõ ràng.

Với JDBC driver có hỗ trợ SQL `BOOLEAN` native, `PreparedStatement.setBoolean(...)` và `ResultSet.getBoolean(...)` là các API quen thuộc. Một số driver có thêm `getObject(..., Boolean.class)` hoặc SQL type hỗ trợ trực tiếp; khả năng cụ thể cần được **kiểm tra theo phiên bản Oracle JDBC driver và server**. Không suy luận driver bất kỳ đều hỗ trợ kiểu mới chỉ vì Java có `Boolean`.

### 8.2. Chèn SQL BOOLEAN qua `PreparedStatement`

```java
String sql = "INSERT INTO lab_flags_boolean (feature_id, feature_name, enabled)"
           + " VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 100L);
    statement.setString(2, "feature-java");
    statement.setBoolean(3, true);
    statement.executeUpdate();
}
```

Ví dụ dành cho **database SQL BOOLEAN và driver tương thích**. Nó sẽ không làm Oracle 19c/21c tự có cột `BOOLEAN`. Nếu cần ghi `NULL` vào cột Boolean nullable, sử dụng `setNull` với SQL type do JDBC/driver hỗ trợ, ví dụ `java.sql.Types.BOOLEAN`, sau khi xác nhận mapping bằng test tích hợp.

### 8.3. Với Oracle 19c/21c: bind theo kiểu lưu trữ thực tế

Nếu schema lưu cờ bằng `NUMBER(1)`, cách tường minh là:

```java
// Cột enabled là NUMBER(1), 1 = true, 0 = false.
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE lab_flags_number SET enabled = ? WHERE feature_id = ?")) {
    statement.setInt(1, true ? 1 : 0);
    statement.setLong(2, 1L);
    statement.executeUpdate();
}
```

Trong ứng dụng thật, giá trị Boolean sẽ đến từ biến nghiệp vụ. Nếu nullable, ánh xạ `null` thành SQL `NULL` khi contract cho phép, không ép sang `0` một cách ngầm định. Với cột `CHAR(1)`, truyền `'Y'`/`'N'` qua `setString`; có thể dùng `AttributeConverter<Boolean, String>` hoặc cơ chế ORM tương ứng để tập trung hóa mapping.

### 8.4. ORM/JPA/Hibernate có thể phát sinh DDL khác nhau

Ví dụ entity Java:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class FeatureFlag {
    @Id
    private Long id;

    @Column(nullable = false)
    private Boolean enabled;

    // Constructor / getter / setter được lược bớt trong ví dụ.
}
```

Entity này **không tự quy định** database sẽ tạo cột `BOOLEAN`, `NUMBER(1)` hay loại khác. Kết quả DDL và bind phụ thuộc dialect, ORM version, JDBC driver, chế độ schema generation và cách cấu hình explicit mapping. Với một ứng dụng cần chạy trên **19c và 23ai**, không nên dựa duy nhất vào auto-generated DDL từ ORM; cần quản lý migration SQL theo phiên bản và test trên **Oracle thật** cho từng baseline được hỗ trợ.

### 8.5. Lưu ý thay đổi bind trong các bản driver mới

Khi nâng cấp database hoặc Oracle JDBC driver, cơ chế truyền **Java `boolean`** tới server có thể thay đổi theo khả năng kiểu SQL native. Điều này ảnh hưởng những ứng dụng cũ vốn chờ một bind kiểu `NUMBER` hoặc `VARCHAR` thay vì SQL `BOOLEAN`. Tài liệu Oracle JDBC cho các bản mới có tùy chọn kiểm soát cách gửi native Boolean trong một số trường hợp; chỉ dùng tùy chọn đó khi đã đánh giá driver/server thực tế.

Trước khi nâng cấp, test tối thiểu các trường hợp `INSERT`, `UPDATE`, `SELECT`, bind `TRUE/FALSE/NULL`, stored procedure và native query. Đặc biệt không dựa vào ép kiểu ngầm định khi contract database yêu cầu chính xác `0/1` hoặc `Y/N`.

## 9. Migration từ `NUMBER(1)`/`CHAR(1)` sang SQL BOOLEAN

Khi nâng Oracle lên 23ai hoặc bản hỗ trợ SQL BOOLEAN mới hơn, **có thể** dùng cột `BOOLEAN` native. Nhưng việc đổi một cột đang được ứng dụng sử dụng có thể tác động tới SQL, stored procedures, report, index, ETL, ORM, cache và các client cũ. Đây là thay đổi về **schema contract**, không chỉ là thay một từ khóa trong DDL.

### 9.1. Khảo sát dữ liệu hiện hữu

Giả sử bảng legacy dùng `NUMBER(1)` và quy ước `1/0`:

```sql
-- Chạy trên bảng legacy_flags đã tồn tại trong môi trường kiểm thử.
SELECT legacy_enabled, COUNT(*) AS row_count
FROM legacy_flags
GROUP BY legacy_enabled
ORDER BY legacy_enabled;
```

Phải biết có giá trị `NULL`, `2`, `-1` hoặc dữ liệu không hợp lệ hay không. Một cột khai báo `NUMBER(1)` không đảm bảo giá trị chỉ 0/1 nếu trước đó không có constraint; cần kiểm tra chất lượng dữ liệu trước khi chuyển đổi.

```sql
SELECT COUNT(*) AS invalid_rows
FROM legacy_flags
WHERE legacy_enabled NOT IN (0, 1)
   OR legacy_enabled IS NULL;
```

Điều kiện trên tính cả `NULL` là “không hợp lệ” **chỉ nếu** nghiệp vụ yêu cầu cờ hai trạng thái `NOT NULL`. Nếu `NULL` là trạng thái hợp lệ, điều chỉnh truy vấn kiểm tra và plan migration tương ứng.

### 9.2. Thêm cột Boolean mới thay vì đổi trực tiếp không kiểm soát

Một chiến lược phù hợp cho hệ thống có yêu cầu tương thích là **expand → backfill → switch → contract**:

```text
Schema cũ: legacy_enabled NUMBER(1)
       |
       v
EXPAND: thêm enabled_bool BOOLEAN nullable
       |
       v
BACKFILL: chuyển 1 -> TRUE, 0 -> FALSE, NULL -> NULL
       |
       v
VERIFY: so số dòng, kiểm tra sai lệch, thử ứng dụng và client
       |
       v
SWITCH: ứng dụng chuyển dần sang cột mới theo kế hoạch
       |
       v
CONTRACT: bỏ cột cũ khi không còn consumer phụ thuộc
```

Ví dụ **chỉ dành cho Oracle 23ai+ trong môi trường được phép**:

```sql
-- Bảng legacy_flags đã tồn tại, có cột legacy_enabled NUMBER(1).
ALTER TABLE legacy_flags ADD (enabled_bool BOOLEAN);

UPDATE legacy_flags
SET enabled_bool = CASE
    WHEN legacy_enabled = 1 THEN TRUE
    WHEN legacy_enabled = 0 THEN FALSE
    ELSE NULL
END;

COMMIT;
```

Đoạn ví dụ giúp nhìn mapping, **không phải một migration hoàn chỉnh cho bảng production lớn**. Trước khi chạy thật cần quyết định xử lý dữ liệu ngoài miền, chia batch/backfill, lock, undo/redo, rollback ứng dụng, sync hai cột trong thời gian chuyển tiếp, thời điểm siết `NOT NULL` và tiêu chí xóa cột cũ.

### 9.3. Kiểm tra sau backfill

```sql
-- Oracle 23ai+, ví dụ kiểm tra mapping 0/1/NULL.
SELECT COUNT(*) AS mismatch_rows
FROM legacy_flags
WHERE (legacy_enabled = 1 AND enabled_bool IS NOT TRUE)
   OR (legacy_enabled = 0 AND enabled_bool IS NOT FALSE)
   OR (legacy_enabled IS NULL AND enabled_bool IS NOT NULL);
```

Truy vấn chỉ thể hiện **một phần** kiểm chứng mapping; các giá trị `legacy_enabled` ngoài 0/1/NULL phải được phát hiện trong bước khảo sát. Đối với hệ thống lớn, so sánh theo khóa, thống kê và từng batch có thể hữu ích hơn một câu quét toàn bảng lúc cao điểm.

Oracle DDL thường có **implicit commit**, vì vậy `ALTER TABLE ... ADD` không biến mất chỉ bởi `ROLLBACK` của giao dịch DML sau đó. Rollback ứng dụng và rollback schema là hai câu chuyện khác nhau; cần kế hoạch chuyển tiếp khi nhiều phiên bản ứng dụng cùng hoạt động.

### 9.4. Khi không nên vội đổi sang BOOLEAN

- Hệ thống còn phải chạy trên Oracle 19c/21c hoặc có môi trường dự phòng chưa nâng cấp.
- ETL, BI/report, integration hoặc driver chưa hỗ trợ SQL BOOLEAN native.
- Contract bên ngoài đang dùng `0/1`, `Y/N` hoặc mã trạng thái được nhiều đối tác sử dụng.
- Giá trị thực tế không chỉ có hai trạng thái và `NULL` có ý nghĩa riêng.
- Việc đổi schema đòi hỏi can thiệp nhiều stored procedure, index, materialized view, job hoặc API chưa được kiểm chứng.

Trong những trường hợp này, giữ representation cũ có constraint và mapping rõ ràng có thể giảm rủi ro hơn. Dùng SQL BOOLEAN là lựa chọn thiết kế, **không phải yêu cầu buộc phải chuyển ngay khi database được nâng cấp**.

## 10. Xác định phiên bản và khả năng hỗ trợ thực tế

Một hệ thống có nhiều PDB, môi trường hoặc driver có thể không đồng nhất. Trước khi chạy cú pháp SQL Boolean, hãy xác minh đích:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Tùy quyền và môi trường, DBA có thể xác minh release của database từ thông tin instance/version mà Oracle cung cấp; ví dụ những tài khoản có quyền phù hợp có thể dùng:

```sql
-- View/version data có thể cần quyền phù hợp.
SELECT banner_full
FROM v$version;
```

Không cấp quyền catalog rộng cho tài khoản ứng dụng chỉ để biết version; trong môi trường hạn quyền, hỏi DBA hoặc lấy thông tin version qua cấu hình triển khai đã được xác minh. Có thể xem metadata loại cột sau khi tạo trên môi trường hỗ trợ:

```sql
SELECT column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_FLAGS_BOOLEAN'
ORDER BY column_id;
```

Trên Oracle 23ai+, cột `ENABLED` trong bảng ví dụ được biểu diễn bằng datatype `BOOLEAN`. Còn trên 19c/21c, việc migration dùng Boolean SQL sẽ bị từ chối ở bước tạo schema; **không sử dụng một bảng đã tồn tại ở database khác làm bằng chứng phiên bản đích hỗ trợ tính năng**.

### 10.1. Tách kiểm tra server, driver và framework

| Lớp | Điều cần xác nhận |
|---|---|
| Oracle Database | Phiên bản nào, PDB/service nào, SQL BOOLEAN có được hỗ trợ không |
| Oracle JDBC/OCI client | Kiểu native Boolean có được bind/read không, xử lý `NULL` thế nào |
| ORM/dialect | `Boolean` map thành kiểu SQL nào, có tự sinh DDL hợp phiên bản không |
| Migration tool | Script có điều kiện phiên bản, thứ tự migration và đường fallback không |
| API/ETL/report | Có cần tiếp tục contract số/ký tự hoặc chuẩn JSON Boolean không |
| Runtime test | Có integration test trực tiếp với Oracle phiên bản đích, gồm null/edge case không |

Không lấy “unit test dùng H2 pass” làm chứng cứ đầy đủ cho cú pháp Oracle SQL Boolean, vì engine thử nghiệm có thể hỗ trợ Boolean ở các phiên bản mà Oracle cũ chưa hỗ trợ.

## 11. Ví dụ thực hành cho hai nhóm phiên bản

Các bài thực hành dưới đây dùng dữ liệu giả trong **DEV/TEST được cấp quyền**. Không cần account `SYSDBA`. Người thực hành cần quyền tạo bảng trong schema lab và phải xác định đúng PDB trước khi chạy DDL.

### Bài A — Oracle 19c/21c: Boolean trong PL/SQL nhưng cờ được lưu bằng số

**Bước 1.** Chạy PL/SQL ba giá trị:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_flag BOOLEAN := NULL;
BEGIN
    IF v_flag IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = UNKNOWN');
    ELSIF v_flag THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = TRUE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PL/SQL BOOLEAN = FALSE');
    END IF;
END;
/
```

**Bước 2.** Trong đúng schema lab, tạo cờ lưu bằng `NUMBER(1)`:

```sql
CREATE TABLE lab_legacy_bool (
    id NUMBER PRIMARY KEY,
    is_valid NUMBER(1),
    CONSTRAINT ck_lab_legacy_bool CHECK (is_valid IN (0, 1))
);

INSERT INTO lab_legacy_bool VALUES (1, 1);
INSERT INTO lab_legacy_bool VALUES (2, 0);
INSERT INTO lab_legacy_bool VALUES (3, NULL);
COMMIT;
```

**Bước 3.** Đọc dữ liệu và chuyển về nhãn:

```sql
SELECT id,
       CASE
           WHEN is_valid = 1 THEN 'TRUE'
           WHEN is_valid = 0 THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS validity
FROM lab_legacy_bool
ORDER BY id;
```

Kết quả dự kiến theo thứ tự `id = 1, 2, 3` là `TRUE`, `FALSE`, `UNKNOWN`. Đây là **chuỗi hiển thị**, không có cột SQL `BOOLEAN` native. Để minh họa khác biệt phiên bản, hãy **đọc lý thuyết** về DDL `BOOLEAN` ở phần trước; không cần chạy DDL không được hỗ trợ trên môi trường dùng chung chỉ để tạo lỗi.

### Bài B — Oracle 23ai+: lưu và lọc Boolean trực tiếp

**Bước 1.** Tạo bảng lab nullable:

```sql
-- Chỉ dùng khi database đã hỗ trợ SQL BOOLEAN.
CREATE TABLE lab_native_bool (
    id NUMBER PRIMARY KEY,
    is_valid BOOLEAN
);

INSERT INTO lab_native_bool VALUES (1, TRUE);
INSERT INTO lab_native_bool VALUES (2, FALSE);
INSERT INTO lab_native_bool VALUES (3, NULL);
COMMIT;
```

**Bước 2.** Đọc ba nhóm trạng thái:

```sql
SELECT id FROM lab_native_bool WHERE is_valid IS TRUE;
SELECT id FROM lab_native_bool WHERE is_valid IS FALSE;
SELECT id FROM lab_native_bool WHERE is_valid IS NULL;

SELECT id FROM lab_native_bool WHERE is_valid IS NOT TRUE;
```

Ba truy vấn đầu lần lượt lấy `id = 1`, `id = 2`, `id = 3`. Truy vấn cuối lấy `id = 2` và `id = 3`, vì **“không phải TRUE”** bao gồm cả FALSE và NULL.

**Bước 3.** Đọc dictionary để xác nhận kiểu dữ liệu:

```sql
SELECT table_name, column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_NATIVE_BOOL'
ORDER BY column_id;
```

**Bước 4.** Dùng SQL Boolean trong biểu thức:

```sql
SELECT id,
       (id > 1) AS id_greater_than_one,
       CASE
           WHEN is_valid IS TRUE THEN 'TRUE'
           WHEN is_valid IS FALSE THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS readable_status
FROM lab_native_bool
ORDER BY id;
```

Quan sát khác biệt giữa `id_greater_than_one` (Boolean SQL) và `readable_status` (`VARCHAR2` từ `CASE`).

**Bước 5.** Nếu được phép dọn đúng dữ liệu lab do mình tạo:

```sql
DROP TABLE lab_native_bool PURGE;
```

Với bài A, có thể thu dọn `lab_legacy_bool` tương tự theo đúng quyền và phạm vi. `DROP TABLE ... PURGE` là thao tác xóa object/dữ liệu và DDL implicit commit; **không chạy trên bảng ngoài bài lab**.

## 12. Các lỗi và hiểu lầm thường gặp

| Nhận định sai | Vì sao sai | Cách xử lý |
|---|---|---|
| “Oracle 19c hỗ trợ Boolean vì `DECLARE x BOOLEAN` chạy được.” | PL/SQL và SQL có tập kiểu dữ liệu khác nhau trước 23ai. | Chỉ dùng PL/SQL Boolean trong PL/SQL; lưu cột bằng `NUMBER(1)`/`CHAR(1)` có constraint. |
| “SQL `WHERE amount > 0` chứng minh SQL 19c có kiểu BOOLEAN.” | Điều kiện logic trong `WHERE` khác với kiểu cột/kết quả biểu thức SQL Boolean độc lập. | Phân biệt *condition* với *datatype*. |
| “Driver Java có `setBoolean()` thì Oracle 19c tạo được cột BOOLEAN.” | JDBC API và khả năng lưu kiểu SQL ở server là hai lớp khác nhau. | Kiểm tra DDL và mapping trên server thực tế. |
| “`NUMBER(1)` chỉ chứa 0 hoặc 1.” | NUMBER có thể chứa giá trị khác nếu không ràng buộc miền. | Thêm `CHECK (IN (0,1))`. |
| “`CHECK (flag IN (0,1))` tự cấm NULL.” | Check constraint không tự thay `NOT NULL`. | Khai báo `NOT NULL` nếu nghiệp vụ chỉ có hai trạng thái. |
| “Trong PL/SQL, `NOT NULL` là TRUE.” | Phủ định Boolean NULL vẫn là NULL. | Dùng `IS NULL` để nhận diện unknown. |
| “`IS NOT TRUE` đồng nghĩa `IS FALSE`.” | Với cột nullable, `IS NOT TRUE` còn bao gồm NULL. | Chọn predicate theo ý nghĩa nghiệp vụ. |
| “`getBoolean()` trả `false` nghĩa là dữ liệu chắc chắn FALSE.” | JDBC có thể trả `false` khi SQL là NULL. | Kiểm tra `wasNull()` hoặc API wrapper hỗ trợ null. |
| “Cứ đổi `NUMBER(1)` thành `BOOLEAN` sau khi nâng cấp server.” | Client/ORM/report/migration có thể còn phụ thuộc 0/1. | Triển khai expand/backfill/switch/contract và test end-to-end. |
| “`TO_BOOLEAN(2)` phải báo lỗi vì 2 không phải 1.” | Oracle có quy tắc chuyển số khác 0 thành TRUE trong SQL Boolean hỗ trợ. | Làm sạch dữ liệu và xác nhận miền 0/1 trước chuyển đổi. |
| “Bật tính năng ở JDBC sẽ làm SQL Boolean xuất hiện trên Oracle 19c.” | Kiểu SQL là năng lực của server/database release. | Chọn baseline tương thích; không giả lập bằng cấu hình driver. |
| “`NULL` và `FALSE` không khác nhau trong WHERE.” | Logic ba giá trị làm `NOT NULL` vẫn UNKNOWN. | Viết `IS FALSE`, `IS NULL` hoặc `IS NOT TRUE` theo đúng yêu cầu. |

### 12.1. Một số triệu chứng khi nâng cấp

- **`ORA-00902: invalid datatype`** khi tạo cột `BOOLEAN` trên release chưa hỗ trợ: trước tiên kiểm tra database version/service/PDB, không đổi tên cột hoặc tăng quyền.
- **Lỗi SQL khi chọn literal `TRUE` trên bản cũ:** đang dùng cú pháp SQL Boolean của phiên bản mới; thay bằng biểu thức tương thích hoặc nâng cấp có kế hoạch.
- **Lỗi bind/conversion trong JDBC:** kiểm tra driver version, target column type, cách gửi `BOOLEAN`/`NUMBER` và dữ liệu `NULL`; không giả định Java `Boolean` tự tương thích với mọi kiểu SQL.
- **Ứng dụng chạy nhưng báo trạng thái sai:** xác minh mapping `1/0`, `Y/N`, `TRUE/FALSE/NULL`, converter và logic `IS NOT TRUE`. Đây có thể là lỗi nghiệp vụ âm thầm nguy hiểm hơn lỗi cú pháp.
- **Migration chỉ thất bại ở production:** đối chiếu Oracle Database version, schema version, service/PDB và đường migration; môi trường TEST phải đủ tương đồng để phát hiện trước.

## 13. Hướng dẫn chọn thiết kế cho dự án Oracle

**Trường hợp A — Ứng dụng vẫn chạy trên Oracle 19c LTS hoặc 21c:** dùng `BOOLEAN` cho điều kiện PL/SQL nhưng cột cờ dùng `NUMBER(1)`/`CHAR(1)` có constraint. Tập trung hóa mapping thành một contract để tránh module này dùng `1/0`, module khác dùng `'Y'/'N'`.

**Trường hợp B — Dự án mới chỉ triển khai Oracle 23ai/26ai và driver được chứng minh tương thích:** dùng cột `BOOLEAN` native khi khái niệm nghiệp vụ thật sự chỉ có hai trạng thái hoặc ba trạng thái gồm `NULL`. Viết `IS TRUE`/`IS FALSE`/`IS NULL` rõ nghĩa và test JDBC/ORM, API, report.

**Trường hợp C — Dự án hỗ trợ đồng thời Oracle 19c và 23ai:** giữ một dạng lưu trữ chung được cả hai phiên bản hỗ trợ, hoặc tách migration/dialect có kiểm thử riêng. Không phát hành một script `BOOLEAN` native cho tất cả môi trường nếu còn database cũ.

**Trường hợp D — Dữ liệu có nhiều trạng thái nghiệp vụ:** dùng mã trạng thái có miền rõ ràng (`PENDING`, `APPROVED`, `REJECTED`, ...), ràng buộc và bảng tham chiếu nếu phù hợp. Một Boolean không biểu diễn tự nhiên bốn hay năm trạng thái; đừng dùng `NULL` để giấu thêm nhiều ý nghĩa khác nhau.

**Trường hợp E — API Java nhận/trả `Boolean`:** phân biệt `boolean` và `Boolean`, xử lý `NULL`/missing field tại contract API, kiểm tra converter và kiểu SQL thực tế. Đừng để tên thuộc tính `isActive` quyết định ngầm datatype hoặc giá trị mặc định trong database.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Trên Oracle 19c, đoạn `DECLARE v_ok BOOLEAN := TRUE; BEGIN NULL; END;` chạy được. Có thể tạo cột `is_ok BOOLEAN` không?

**Đáp án:** không. Đó là `BOOLEAN` của PL/SQL; Oracle 19c chưa có kiểu SQL `BOOLEAN` gốc.

**Câu 2.** Một cột `enabled NUMBER(1)` được gán `2`. Vì sao vẫn có thể xảy ra nếu chỉ khai báo kiểu `NUMBER(1)`?

**Đáp án:** vì kiểu số không tự giới hạn miền 0/1; cần `CHECK (enabled IN (0,1))` để xác định quy ước Boolean và `NOT NULL` nếu không cho phép UNKNOWN.

**Câu 3.** Trong PL/SQL, một biến `BOOLEAN` là `NULL`. Điều kiện `IF NOT v_flag THEN` có chạy nhánh THEN không?

**Đáp án:** không. `NOT NULL` vẫn là `NULL`, và `IF` chỉ vào THEN khi biểu thức bằng `TRUE`.

**Câu 4.** Trong SQL Oracle 23ai, `flag` nhận `TRUE`, `FALSE`, `NULL`. `WHERE flag IS NOT TRUE` chọn những trạng thái nào?

**Đáp án:** `FALSE` và `NULL`. Nó khác `WHERE flag IS FALSE`.

**Câu 5.** Java gọi `ResultSet.getBoolean()` và nhận `false`. Có thể kết luận cột chứa SQL FALSE không?

**Đáp án:** chưa đủ. Cần gọi `wasNull()` hoặc API đọc được `Boolean` nullable để phân biệt giá trị gốc là `NULL`.

**Câu 6.** Oracle 23ai hỗ trợ SQL BOOLEAN. Có nên tự đổi mọi cột `'Y'/'N'` đang chạy thành `BOOLEAN` trong một lần phát hành?

**Đáp án:** không. Phải xem client/driver, ORM, stored procedures, report, data quality và đường tương thích, rồi lập migration có kiểm thử.

**Câu 7.** `SELECT CASE WHEN amount > 0 THEN 1 ELSE 0 END AS positive FROM orders` có nghĩa SQL 19c đã trả về Boolean chưa?

**Đáp án:** chưa. Biểu thức trả `NUMBER` theo `THEN`/`ELSE`, dù điều kiện trong `WHEN` có logic đúng/sai.

**Câu 8.** Dữ liệu legacy là `0`, `1`, `2`, `NULL`. Có thể gọi `TO_BOOLEAN` cho cả cột rồi khẳng định kết quả luôn giữ quy ước 0/1 ban đầu?

**Đáp án:** không. Trên Oracle có SQL BOOLEAN, số khác 0 có thể được đổi thành `TRUE`; cần phát hiện giá trị `2`, quyết định chính sách làm sạch rồi mới chuyển.

## Kết luận

**Trước Oracle 23c/23ai, `BOOLEAN` là kiểu được PL/SQL hỗ trợ nhưng chưa phải datatype SQL để lưu cột. Từ Oracle 23c/23ai, SQL hỗ trợ `BOOLEAN` native**, cho phép tạo cột, chọn literal `TRUE`/`FALSE`, xây biểu thức Boolean và truyền kết quả giữa SQL/PLSQL thuận tiện hơn. **`NULL` vẫn là trạng thái thứ ba**, cần xử lý tường minh khi lọc SQL, viết PL/SQL và ánh xạ qua Java/JDBC.

Khi thiết kế hệ thống Oracle, hãy quyết định representation theo **database release thật, driver/ORM được kiểm chứng và ý nghĩa nghiệp vụ của dữ liệu**. Trên 19c/21c, dùng `NUMBER(1)` hoặc `CHAR(1)` có constraint và converter rõ ràng; trên 23ai trở lên có thể dùng SQL `BOOLEAN` khi toàn bộ hệ sinh thái đã sẵn sàng. Cách tiếp cận đó giúp tránh lỗi migration, ngầm chuyển sai `NULL`/`FALSE` và khác biệt hành vi giữa DEV, TEST và production.

## Tài liệu Oracle tham khảo theo phiên bản

- [Oracle Database 19c — PL/SQL `BOOLEAN` Data Type](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/boolean-data-type.html): cơ chế Boolean PL/SQL và giới hạn tương tác với SQL trước 23ai.
- [Oracle Database 23ai — Explore SQL Features](https://docs.oracle.com/en/learn/db23ai-sql-features/): ví dụ `BOOLEAN` như kiểu dữ liệu SQL.
- [Oracle Database 23ai — SQL Boolean Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/boolean-expressions.html): biểu thức và điều kiện kiểm tra Boolean trong SQL.
- [Oracle AI Database 26ai — SQL Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html): các giá trị, phép logic và quy tắc chuyển đổi SQL Boolean.
- [Oracle JDBC — Accessing and Manipulating Oracle Data](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/accessing-and-manipulating-Oracle-data.html): mapping JDBC và các lưu ý đối với native Boolean ở các bản driver/database mới.
