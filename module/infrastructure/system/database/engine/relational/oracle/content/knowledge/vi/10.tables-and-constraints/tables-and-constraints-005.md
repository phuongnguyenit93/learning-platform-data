# CHECK, NOT NULL và giới hạn của kiểm tra dữ liệu khai báo trong Oracle Database

## 1. Vấn đề: ai bảo đảm dữ liệu luôn hợp lệ?

Một ứng dụng đặt hàng có thể kiểm tra `quantity > 0` ở giao diện, dịch vụ Java và thủ tục PL/SQL. Nhưng dữ liệu còn có thể được ghi qua batch job, script SQL, ứng dụng khác, import hoặc quá trình bảo trì. Nếu chỉ tin vào validation phía ứng dụng, mỗi đường ghi phải triển khai đúng cùng một quy tắc. **Integrity constraints** trong Oracle Database đặt ra hợp đồng dữ liệu ngay tại bảng: mọi thao tác DML thuộc phạm vi thực thi ràng buộc phải tuân thủ các quy tắc đã khai báo.

Hai dạng ràng buộc cơ bản nhưng rất quan trọng:

- **`NOT NULL`:** một cột bắt buộc có giá trị khác `NULL`.
- **`CHECK (condition)`:** giá trị của **mỗi row** phải làm điều kiện kiểm tra có kết quả **`TRUE` hoặc `UNKNOWN`**; chỉ kết quả **`FALSE`** mới vi phạm.

Ví dụ:

```sql
CREATE TABLE order_items_demo (
    item_id    NUMBER PRIMARY KEY,
    sku        VARCHAR2(30 CHAR) NOT NULL,
    quantity   NUMBER NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    discount   NUMBER(5,2),
    CONSTRAINT oi_quantity_ck CHECK (quantity > 0),
    CONSTRAINT oi_price_ck    CHECK (unit_price >= 0),
    CONSTRAINT oi_discount_ck CHECK (discount BETWEEN 0 AND 100)
);
```

Bảng này chặn `quantity = 0` và `unit_price = -1`, chặn `quantity = NULL`, nhưng **cho phép `discount = NULL`**: ràng buộc CHECK trên `discount` cho kết quả UNKNOWN khi cột NULL, và cột chưa có `NOT NULL`.

> Bài học dùng hành vi thông dụng của Oracle Database 19c. Cú pháp và tính năng bổ sung có thể thay đổi ở các release khác. Những câu `CREATE TABLE`, `ALTER TABLE`, `INSERT` và `DROP TABLE` là thao tác thật; chỉ chạy trong schema lab bạn sở hữu. Phần đọc metadata có thể được thực hiện ở môi trường được cấp quyền.

## 2. CHECK và NOT NULL nằm ở đâu trong hệ ràng buộc?

| Cơ chế | Quy tắc nó bảo vệ | Ví dụ | Điều nó **không** làm |
| --- | --- | --- | --- |
| `NOT NULL` | Một cột không được NULL | `email VARCHAR2(200) NOT NULL` | Không chứng minh email đúng định dạng hoặc còn hoạt động |
| `CHECK` | Biểu thức hợp lệ **trên row hiện tại** | `CHECK (price >= 0)` | Không kiểm tra tổng hợp tất cả row hoặc truy vấn bảng khác |
| `PRIMARY KEY` | Định danh duy nhất, không NULL | `order_id PRIMARY KEY` | Không kiểm tra trạng thái nghiệp vụ |
| `UNIQUE` | Tính duy nhất theo semantics NULL của Oracle | `CONSTRAINT uq_code UNIQUE(code)` | Không bảo đảm một chuỗi có định dạng hợp lệ |
| `FOREIGN KEY` | Giá trị tham chiếu tồn tại ở parent key hợp lệ | `customer_id REFERENCES customers(id)` | Không kiểm tra mọi quy tắc điều kiện hoặc tổng hợp |
| `DEFAULT` | Cung cấp giá trị mặc định theo luật của column | `status DEFAULT 'NEW'` | Không thay thế constraint; không mặc nhiên chặn NULL |
| Trigger / procedure | Chạy logic nhiều bước, có thể đọc thêm dữ liệu | Kiểm tra workflow đặc thù | Phải thiết kế đúng concurrency, lỗi và quyền |
| Ứng dụng / API | UX, thông báo thân thiện và quy trình nghiệp vụ | Validate input trước gửi SQL | Không chặn mọi đường ghi ngoài ứng dụng đó |

Kiến trúc phòng thủ hợp lý:

```text
Client/API validation        → phát hiện sớm, giải thích lỗi rõ
        │
        ▼
Service / PL/SQL transaction → thực hiện nghiệp vụ và phối hợp nhiều row
        │
        ▼
Oracle table constraints     → từ chối row không thỏa invariants đã khai báo
        │
        ▼
Committed database state     → dữ liệu được bảo vệ bất kể đường ghi thông thường
```

**Invariant** là tính chất phải luôn đúng với trạng thái dữ liệu được chấp nhận, ví dụ “giá không âm”, “ngày kết thúc không trước ngày bắt đầu” hoặc “trạng thái thuộc tập được cho phép”. Chọn constraint thích hợp với **phạm vi** của invariant là bước đầu tiên khi thiết kế bảng.

## 3. Cú pháp: khai báo khi tạo bảng và khi bảng đã tồn tại

### 3.1. `NOT NULL` là ràng buộc inline theo cột

```sql
CREATE TABLE customer_contact_demo (
    customer_id NUMBER,
    full_name   VARCHAR2(100 CHAR)
        CONSTRAINT ccd_name_nn NOT NULL,
    email       VARCHAR2(200 CHAR),
    CONSTRAINT ccd_pk PRIMARY KEY (customer_id)
);
```

`NOT NULL` được khai báo tại **định nghĩa cột**. Nếu không đặt tên, Oracle có thể sinh tên `SYS_C...`; đặt tên nhất quán giúp log lỗi, migration và dashboard dễ nhận diện hơn.

Đặt `NOT NULL` lên cột hiện có:

```sql
ALTER TABLE customer_contact_demo
  MODIFY (email CONSTRAINT ccd_email_nn NOT NULL);
```

Lệnh này cần kiểm tra dữ liệu hiện có; nếu đang có `email IS NULL`, thao tác đặt ràng buộc theo chế độ validate mặc định có thể thất bại. Cần làm sạch hoặc xác định quy trình chuyển đổi dữ liệu trước.

### 3.2. `CHECK` có thể inline hoặc out-of-line

**Inline** khi biểu thức chỉ cần giá trị một cột:

```sql
CREATE TABLE product_demo (
    product_id NUMBER PRIMARY KEY,
    price      NUMBER(12,2)
        CONSTRAINT product_price_ck CHECK (price >= 0)
);
```

**Out-of-line** ở mức bảng khi quy tắc so sánh nhiều cột:

```sql
CREATE TABLE booking_period_demo (
    booking_id NUMBER PRIMARY KEY,
    starts_at  DATE NOT NULL,
    ends_at    DATE NOT NULL,
    CONSTRAINT booking_period_ck CHECK (ends_at >= starts_at)
);
```

Trong biểu thức CHECK đặt ở mức bảng, được phép tham chiếu **nhiều cột trong cùng một row**. Ví dụ: `CHECK (end_date >= start_date)`, `CHECK (discount <= amount)`, `CHECK (status <> 'CANCELLED' OR cancel_reason IS NOT NULL)`.

Thêm một CHECK cho bảng đang chạy:

```sql
ALTER TABLE product_demo
  ADD CONSTRAINT product_discount_ck
  CHECK (price <= 999999.99);
```

Mặc định, CHECK mới phải phù hợp dữ liệu cũ nếu dùng chế độ `ENABLE VALIDATE`. Có cách chuyển tiếp `ENABLE NOVALIDATE` cho dữ liệu legacy, trình bày ở phần quản lý vòng đời constraint.

### 3.3. Một cột có thể có nhiều CHECK

```sql
CREATE TABLE item_validation_demo (
    item_id NUMBER PRIMARY KEY,
    code    VARCHAR2(30 CHAR) NOT NULL,
    amount  NUMBER(12,2),
    CONSTRAINT iv_amount_nonnegative_ck CHECK (amount >= 0),
    CONSTRAINT iv_amount_max_ck         CHECK (amount <= 1000000),
    CONSTRAINT iv_code_nonblank_ck      CHECK (TRIM(code) IS NOT NULL)
);
```

Nhiều constraint nhỏ, mỗi constraint đại diện **một quy tắc**, thường dễ đọc và dễ xử lý lỗi hơn một biểu thức rất dài. **Thứ tự Oracle đánh giá nhiều CHECK không được bảo đảm**; không viết điều kiện mà kết quả phụ thuộc vào việc constraint A chạy trước constraint B.

## 4. Quy tắc quan trọng nhất: CHECK chấp nhận TRUE **và** UNKNOWN

SQL không chỉ có `TRUE` và `FALSE`. Khi biểu thức so sánh một giá trị `NULL`, kết quả thường là **`UNKNOWN`**. Oracle coi CHECK bị vi phạm **chỉ khi điều kiện trả FALSE**.

| Giá trị `score` | `score >= 0` | CHECK cho qua? |
| --- | --- | --- |
| `15` | TRUE | Có |
| `0` | TRUE | Có |
| `-3` | FALSE | **Không** |
| `NULL` | UNKNOWN | **Có** |

Vì thế:

```sql
CREATE TABLE score_demo (
    score NUMBER
        CONSTRAINT score_nonnegative_ck CHECK (score >= 0)
);

INSERT INTO score_demo(score) VALUES (10);   -- Hợp lệ.
INSERT INTO score_demo(score) VALUES (NULL); -- Cũng hợp lệ!
```

Nếu yêu cầu **bắt buộc có điểm và điểm không âm**, phải có cả hai điều kiện:

```sql
CREATE TABLE score_required_demo (
    score NUMBER NOT NULL,
    CONSTRAINT score_required_ck CHECK (score >= 0)
);
```

### 4.1. Bảng chân trị SQL ba giá trị

| A | B | `A AND B` | `A OR B` |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Với `NOT`: `NOT TRUE = FALSE`, `NOT FALSE = TRUE` và `NOT UNKNOWN = UNKNOWN`.

Hệ quả quan trọng: một ràng buộc `CHECK (salary > 0 OR commission >= 0)` có thể **chấp nhận** `salary = NULL` và `commission = -100`, vì `UNKNOWN OR FALSE = UNKNOWN`. Nếu quy tắc đòi cả hai cột bắt buộc, hãy khai báo thêm `NOT NULL` hoặc biểu thức kiểm tra NULL tường minh.

### 4.2. `= NULL` không phải phép kiểm tra NULL

```sql
-- SAI về nghĩa: col <> NULL trả UNKNOWN với mọi giá trị.
CHECK (status <> NULL)

-- ĐÚNG: sử dụng IS NOT NULL.
CHECK (status IS NOT NULL)
```

Đối với column thông thường, **nên khai báo `NOT NULL`** thay vì dùng một CHECK tách riêng chỉ gồm `IS NOT NULL`, vì intent và metadata cột rõ ràng hơn. CHECK `IS NOT NULL` hữu ích khi là một phần điều kiện kết hợp hoặc xử lý trường hợp đặc thù.

## 5. NOT NULL: giá trị phải tồn tại, không bảo đảm có ý nghĩa

### 5.1. Ba điều kiện dễ bị đánh đồng

| Trường hợp | Giá trị | Với `NOT NULL` | Có hợp lệ về nghiệp vụ? |
| --- | --- | --- | --- |
| Chưa cung cấp | `NULL` | **Bị chặn** | Tùy yêu cầu |
| Chuỗi rỗng cho `VARCHAR2` | `''` | Oracle hiện hành coi là `NULL` → **bị chặn** | Thường không |
| Chuỗi toàn dấu cách | `'   '` | **Được chấp nhận** vì không NULL | Thường không nếu cần tên/mã thật |
| Chuỗi `'0'` | Không NULL | Được chấp nhận | Có thể sai miền giá trị |
| Chuỗi `'UNKNOWN'` | Không NULL | Được chấp nhận | Phụ thuộc quy tắc |

Trong Oracle Database, chuỗi ký tự độ dài 0 **hiện được xử lý như NULL** đối với cách dùng thông thường của `VARCHAR2`; **không** nên dựa vào việc phân biệt `''` và `NULL` trong bảng Oracle. Nhưng chuỗi chứa một hoặc nhiều dấu cách **không** phải NULL. Với kiểu `CHAR` có blank-padding, cần cân nhắc thêm semantics của kiểu cột.

Để loại mã chỉ gồm dấu cách:

```sql
CREATE TABLE customer_code_demo (
    code VARCHAR2(30 CHAR)
        CONSTRAINT customer_code_nn NOT NULL,
    CONSTRAINT customer_code_nonblank_ck
      CHECK (TRIM(code) IS NOT NULL)
);
```

**Tại sao không dùng `CHECK (LENGTH(TRIM(code)) > 0)` đơn lẻ?** Khi `TRIM(code)` trở thành chuỗi rỗng (Oracle coi như NULL), `LENGTH(NULL) > 0` cho **UNKNOWN**, và CHECK sẽ **chấp nhận** nó. `TRIM(code) IS NOT NULL` kiểm tra đúng trường hợp cần loại.

### 5.2. `DEFAULT` không thay thế `NOT NULL`

```sql
CREATE TABLE status_default_demo (
    id     NUMBER PRIMARY KEY,
    status VARCHAR2(20 CHAR) DEFAULT 'NEW' NOT NULL
);

INSERT INTO status_default_demo(id) VALUES (1);
-- STATUS được gán 'NEW' khi cột bị bỏ qua trong INSERT.

-- DML sau có thể bị chặn bởi NOT NULL:
INSERT INTO status_default_demo(id, status) VALUES (2, NULL);
```

`DEFAULT` thông thường áp dụng khi giá trị không được cung cấp theo ngữ nghĩa của câu lệnh; **explicit NULL** không có nghĩa chắc chắn được thay bằng DEFAULT. Oracle có `DEFAULT ON NULL` với hành vi riêng, nhưng ngay cả khi dùng nó vẫn phải thiết kế rõ quy tắc CHECK và semantics UPDATE. Default là **chính sách điền giá trị**, không phải kiểm tra mọi bất biến.

### 5.3. PRIMARY KEY đã có tính chất NOT NULL

`PRIMARY KEY` bảo đảm **duy nhất và không NULL**. Vì vậy với `order_id NUMBER PRIMARY KEY` không cần đặt thêm một `CHECK (order_id IS NOT NULL)` chỉ để tạo cùng quy tắc. Tuy nhiên, đặt một **constraint name có chủ đích** cho PK vẫn cần thiết.

### 5.4. NOT NULL là một dạng constraint được ghi metadata

Trong `USER_CONSTRAINTS`/`DBA_CONSTRAINTS`, cả `NOT NULL` và `CHECK` thông thường có `CONSTRAINT_TYPE = 'C'`. Một constraint `NOT NULL` được nhận diện qua điều kiện kiểu `"COL_NAME" IS NOT NULL` và metadata cột; đừng lấy mọi `CONSTRAINT_TYPE='C'` rồi gọi tất cả là CHECK nghiệp vụ.

Oracle yêu cầu `NOT NULL` **được khai báo inline trên cột** (ví dụ `MODIFY (col CONSTRAINT col_nn NOT NULL)`); khi cần điều kiện kết hợp nhiều cột, dùng CHECK out-of-line ở mức bảng.

## 6. Các mẫu CHECK nên dùng trong schema thực

### 6.1. Miền giá trị cố định: `IN`

```sql
status VARCHAR2(12 CHAR)
    CONSTRAINT orders_status_nn NOT NULL,

CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED'))
```

Lợi ích: chỉ những trạng thái được phép mới được lưu. Điểm cần suy xét:

- `NULL` vẫn qua `IN` CHECK nếu **không** có `NOT NULL`.
- `'paid'` khác `'PAID'` theo quy tắc so sánh/collation đang áp dụng; nếu nghiệp vụ yêu cầu chữ hoa, chuẩn hóa và kiểm tra rõ.
- Nếu danh mục trạng thái thường xuyên thay đổi, hoặc có metadata riêng như `display_name` và `is_active`, cân nhắc **lookup table + foreign key** thay vì cứ sửa CHECK mỗi lần thêm mã.

### 6.2. Khoảng số: `BETWEEN`, `>=`, `<=`

```sql
CONSTRAINT price_nonnegative_ck CHECK (unit_price >= 0),
CONSTRAINT discount_pct_ck     CHECK (discount_pct BETWEEN 0 AND 100)
```

`NUMBER(5,2)` chỉ giới hạn **độ chính xác/scale** của giá trị, không bảo đảm `discount_pct` thuộc khoảng 0–100. Cần constraint cho quy tắc nghiệp vụ; và cần `NOT NULL` nếu giảm giá là trường bắt buộc.

### 6.3. Quan hệ giữa hai cột **trong cùng row**

```sql
CONSTRAINT validity_dates_ck
  CHECK (valid_to IS NULL
         OR (valid_from IS NOT NULL AND valid_to >= valid_from))
```

Ý nghĩa: ngày kết thúc có thể chưa biết, nhưng **nếu có ngày kết thúc thì phải có ngày bắt đầu và không được sớm hơn ngày bắt đầu**.

Nếu cả hai luôn bắt buộc thì đơn giản hơn:

```sql
valid_from DATE NOT NULL,
valid_to   DATE NOT NULL,
CONSTRAINT validity_dates_ck CHECK (valid_to >= valid_from)
```

### 6.4. Quy tắc điều kiện: trạng thái quyết định trường bắt buộc

```sql
CONSTRAINT cancelled_reason_ck
  CHECK (status <> 'CANCELLED'
         OR TRIM(cancel_reason) IS NOT NULL)
```

Nếu `status = 'CANCELLED'`, vế trái FALSE nên `cancel_reason` không được NULL/rỗng/trắng. Nếu status khác `'CANCELLED'`, vế trái TRUE nên không yêu cầu reason. **Phải kết hợp `status NOT NULL`** để tránh UNKNOWN làm biểu thức không chặn các row thiếu status.

Một số quy tắc còn yêu cầu chiều ngược lại: “không CANCELLED thì `cancel_reason` phải NULL”. Khi đó cần biểu thức bổ sung rõ ràng; không mặc định CHECK ở trên đã cấm reason cho status khác.

### 6.5. Kiểm tra định dạng: giới hạn của `LIKE` và `REGEXP_LIKE`

```sql
-- Chỉ là một chính sách mã minh họa, không phải validation cho mọi quốc gia.
CONSTRAINT customer_code_pattern_ck
  CHECK (REGEXP_LIKE(customer_code, '^[A-Z0-9-]+$', 'c'))
```

Khi `customer_code IS NULL`, biểu thức không tự thay thế `NOT NULL`. Regular expression chỉ kiểm tra **hình thức chuỗi**, không kiểm tra mã có thật, đã được cấp, có trùng hay hợp lệ về mặt nghiệp vụ. Với email, số điện thoại, mã số thuế, địa chỉ, phần “có thật/đang hoạt động” thường nằm ngoài khả năng của CHECK thuần khai báo.

### 6.6. Không ép chuyển kiểu ngầm trong CHECK

Không nên viết `CHECK (varchar_price > '100')` rồi hiểu đó là phép so sánh số: với chuỗi, semantics so sánh và NLS/implicit conversion có thể không đúng ý. **Dùng cột NUMBER để lưu số**, cột DATE/TIMESTAMP để lưu thời gian, và so sánh bằng literal/kiểu tương thích. Khi cần biểu thức ngày giờ, dùng DATE/TIMESTAMP literals rõ ràng thay vì phụ thuộc định dạng ngày của session.

## 7. Ví dụ hoàn chỉnh: bảng đơn hàng với CHECK và NOT NULL

Giả sử schema ứng dụng quản lý đơn hàng. Các quy tắc:

1. Mỗi đơn có `order_id`, `order_code`, `status`, `quantity` và `unit_price`.
2. `order_code` không được rỗng hoặc chỉ có dấu cách.
3. `status` chỉ thuộc một tập được quản lý.
4. `quantity > 0` và `unit_price >= 0`.
5. `discount_pct` có thể NULL; nếu cung cấp phải từ 0 đến 100.
6. `valid_to` có thể NULL; nếu không NULL thì `valid_from` phải có và `valid_to >= valid_from`.
7. Khi `status = 'CANCELLED'` phải có lý do không toàn dấu cách.

```sql
CREATE TABLE orders_check_lab (
    order_id       NUMBER
        CONSTRAINT orders_lab_pk PRIMARY KEY,

    order_code     VARCHAR2(40 CHAR)
        CONSTRAINT orders_lab_code_nn NOT NULL,

    status         VARCHAR2(12 CHAR) DEFAULT 'NEW'
        CONSTRAINT orders_lab_status_nn NOT NULL,

    quantity       NUMBER(8)
        CONSTRAINT orders_lab_quantity_nn NOT NULL,

    unit_price     NUMBER(12,2)
        CONSTRAINT orders_lab_price_nn NOT NULL,

    discount_pct   NUMBER(5,2),
    valid_from     DATE,
    valid_to       DATE,
    cancel_reason  VARCHAR2(200 CHAR),

    CONSTRAINT orders_lab_code_ck
      CHECK (TRIM(order_code) IS NOT NULL),

    CONSTRAINT orders_lab_status_ck
      CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),

    CONSTRAINT orders_lab_quantity_ck
      CHECK (quantity > 0),

    CONSTRAINT orders_lab_price_ck
      CHECK (unit_price >= 0),

    CONSTRAINT orders_lab_discount_ck
      CHECK (discount_pct BETWEEN 0 AND 100),

    CONSTRAINT orders_lab_period_ck
      CHECK (valid_to IS NULL
             OR (valid_from IS NOT NULL AND valid_to >= valid_from)),

    CONSTRAINT orders_lab_cancel_ck
      CHECK (status <> 'CANCELLED'
             OR TRIM(cancel_reason) IS NOT NULL)
);
```

**Lưu ý:** Đây là schema lab để học constraints, không phải mô hình thương mại điện tử đầy đủ. Giá/giảm giá còn có vấn đề tiền tệ, thuế, đơn vị, precision, khóa ngoại, tính tồn kho, giao dịch thanh toán và concurrency cần xử lý riêng.

### 7.1. Row hợp lệ khi chưa có `discount_pct`

```sql
INSERT INTO orders_check_lab (
    order_id, order_code, quantity, unit_price, valid_from
) VALUES (
    1, 'ORD-001', 2, 125000,
    DATE '2026-01-01'
);

-- STATUS dùng DEFAULT 'NEW'.
-- DISCOUNT_PCT và VALID_TO được phép NULL.
SELECT order_id, status, quantity, unit_price, discount_pct
FROM   orders_check_lab
WHERE  order_id = 1;
```

### 7.2. Row không hợp lệ: một số trường hợp dự kiến báo lỗi

**Mỗi câu INSERT bên dưới là một thử nghiệm độc lập; hãy chạy từng câu.** Chúng được đưa ra để minh họa lỗi, không phải một migration script dự kiến chạy sạch từ đầu đến cuối.

```sql
-- quantity = 0: CHECK (quantity > 0) → FALSE.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (2, 'ORD-002', 'NEW', 0, 100);
-- Dự kiến: ORA-02290, constraint ORDERS_LAB_QUANTITY_CK.

-- quantity NULL: NOT NULL bị vi phạm.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (3, 'ORD-003', 'NEW', NULL, 100);
-- Dự kiến: ORA-01400, cannot insert NULL.

-- Trạng thái không thuộc tập cho phép.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (4, 'ORD-004', 'UNKNOWN', 1, 100);
-- Dự kiến: ORA-02290, constraint ORDERS_LAB_STATUS_CK.

-- CANCELLED nhưng reason chỉ là khoảng trắng.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, cancel_reason)
VALUES (5, 'ORD-005', 'CANCELLED', 1, 100, '   ');
-- Dự kiến: ORA-02290, constraint ORDERS_LAB_CANCEL_CK.

-- Có valid_to nhưng thiếu valid_from.
INSERT INTO orders_check_lab
    (order_id, order_code, quantity, unit_price, valid_to)
VALUES (6, 'ORD-006', 1, 100, DATE '2026-02-01');
-- Dự kiến: ORA-02290, constraint ORDERS_LAB_PERIOD_CK.
```

Nếu `INSERT` sai ở constraint **NOT DEFERRABLE** thông thường, **statement đó** bị rollback, không tự rollback toàn bộ những statement trước đã chạy thành công trong cùng transaction. Khi defer một constraint tới commit, semantics rollback khác và sẽ được nêu ở phần sau.

### 7.3. Row hợp lệ khi CANCELLED có reason

```sql
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, cancel_reason)
VALUES (7, 'ORD-007', 'CANCELLED', 1, 100, 'Khach yeu cau huy');

SELECT order_id, status, cancel_reason
FROM   orders_check_lab
WHERE  order_id = 7;
```

Khi cần rollback dữ liệu thử nghiệm trong cùng transaction, dùng `ROLLBACK` trước khi kết thúc lab. `CREATE TABLE` là DDL có implicit commit; `ROLLBACK` không xóa table đã tạo.

## 8. CHECK kiểm tra được đến đâu? Giới hạn SQL khai báo

Oracle 19c giới hạn biểu thức CHECK vào điều kiện có thể đánh giá trên **row đang INSERT/UPDATE**. Không có phép đọc tùy ý những row khác hoặc bảng khác trong một CHECK thông thường.

| Nhu cầu | Có thể trực tiếp bằng CHECK? | Thiết kế thay thế hoặc bổ sung |
| --- | --- | --- |
| `amount >= 0` trên row | **Có** | CHECK + NOT NULL nếu bắt buộc |
| `end_date >= start_date` cùng row | **Có** | CHECK table-level |
| `status IN (...)` | **Có** | CHECK hoặc lookup table + FK |
| Cấm NULL ở một cột | **Có**, dùng `NOT NULL` | Tránh dùng CHECK đơn lẻ nếu chỉ cần not-null |
| `email LIKE ...` về định dạng sơ bộ | **Có**, giới hạn của biểu thức | Không chứng minh email có thật |
| `orders.customer_id` phải tồn tại ở bảng `customers` | **Không** bằng CHECK | **FOREIGN KEY** |
| Mã sản phẩm không được trùng giữa các row | **Không** bằng CHECK | **UNIQUE** hoặc PK |
| Tổng lượng đặt của một sản phẩm không quá tồn kho | **Không** bằng CHECK của một row | Transaction, row locks, cập nhật điều kiện; thiết kế ledger/counter phù hợp |
| Không có hai khoảng thời gian đặt lịch bị chồng nhau cho cùng phòng | **Không** bằng CHECK đơn thuần | Thiết kế concurrency, locking/serialization và truy vấn overlap |
| Tổng phần trăm phân bổ của một nhóm bằng 100 | **Không** bằng CHECK trên từng row | Logic tổng hợp transactional hoặc mô hình dữ liệu khác |
| `created_at <= SYSDATE` | **Không** trong CHECK Oracle 19c | Kiểm tra lúc ghi bằng logic được hỗ trợ; bảo đảm thời điểm qua quy trình |
| Kiểm tra tên quốc gia qua user-defined function | **Không** trong CHECK 19c | Lookup table + FK hoặc logic nghiệp vụ |

### 8.1. Những biểu thức bị cấm trong CHECK Oracle 19c

Theo **SQL Language Reference** và **Database Development Guide**:

- **Subquery** hoặc scalar subquery; không được `SELECT` bảng khác trong điều kiện.
- **Sequence** và pseudocolumn `CURRVAL`, `NEXTVAL`; không thể tạo một rule dựa trên giá trị sequence tiếp theo.
- Các hàm không ổn định theo context/thời gian như `SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `UID`, `USER` và `USERENV`, cùng những hàm có tên trong danh sách hạn chế của release.
- **User-defined functions** (kể cả khi hàm được gắn nhãn `DETERMINISTIC`).
- Pseudocolumn `ROWNUM`, `LEVEL` và toán tử `PRIOR`.
- Một số tham chiếu object/`REF`/nested-table attribute đặc thù, cũng như các biểu thức ngày hằng không được chỉ định đầy đủ.
- Không đặt một table CHECK constraint trên một **view** thông thường; `WITH CHECK OPTION` trên view là cơ chế khác. Các loại bảng chuyên biệt như external table có hạn chế riêng.

Ví dụ **không hợp lệ**:

```sql
-- Không được: CHECK không thể truy vấn bảng khác.
CONSTRAINT fk_by_check_bad
CHECK (customer_id IN (SELECT id FROM customers))

-- Không được: SYSDATE thay đổi theo thời gian.
CONSTRAINT created_before_now_bad
CHECK (created_at <= SYSDATE)

-- Không được: user-defined function trong CHECK (Oracle 19c).
CONSTRAINT valid_code_fn_bad
CHECK (my_package.is_valid_code(code) = 1)
```

**Tại sao có những giới hạn này?** Ràng buộc CHECK là hợp đồng cần có kết quả ổn định, đánh giá được ngay từ một row; cho phép phụ thuộc tùy ý vào bảng khác, thời gian hiện tại hoặc function có side effect sẽ gây vấn đề về tính nhất quán, thay đổi độc lập và concurrency.

### 8.2. “Không quá số lượng tồn kho” là ví dụ sai phạm vi

Giả sử `inventory.stock = 10`, có nhiều row `order_items.qty`. CHECK `qty <= 10` ở từng row không ngăn **hai đơn mỗi đơn đặt 8 sản phẩm**, tổng bằng 16. Điều kiện mong muốn là một bất biến **xuyên nhiều row và trạng thái tồn kho**.

Một mô hình bảo vệ tồn kho có thể:

1. Thực hiện transaction cập nhật stock **có điều kiện**: `UPDATE inventory SET available = available - :qty WHERE sku = :sku AND available >= :qty`.
2. Kiểm tra số row đã update để xác định thành công/thất bại.
3. Trong cùng transaction, tạo order item; commit hoặc rollback cùng nhau.
4. Dùng CHECK `available >= 0` cho inventory **như lớp bảo vệ row**, nhưng không nhầm nó là toàn bộ cơ chế cấp phát.

SQL update có điều kiện cùng row lock giúp tránh một số race condition thông dụng, còn chính xác mô hình tồn kho phụ thuộc thiết kế các luồng trả hàng, hủy, giữ hàng và idempotency.

### 8.3. Quy tắc liên dòng hoặc liên bảng không dễ “vá” bằng trigger

Trigger có thể thực hiện kiểm tra phức tạp hơn CHECK nhưng phải quan tâm:

- **Mutating table** (`ORA-04091`) với một số trigger tham chiếu lại chính bảng đang thay đổi.
- **Concurrency/race conditions**: hai session có thể cùng đọc trạng thái hợp lệ rồi cùng ghi gây vi phạm logic nếu thiếu locking/serialization.
- Row trigger, statement trigger, compound trigger có thời điểm chạy và hạn chế khác nhau.
- Quyền, xử lý lỗi, DML recursion và chi phí vận hành.

Ưu tiên PK, UNIQUE, FK, CHECK, NOT NULL khi logic biểu diễn được bằng các constraint đó. Nếu phải dùng trigger hoặc stored procedure, chứng minh tính đúng đắn **dưới concurrency**, không chỉ khi test một session.

## 9. Hành vi khi DML vi phạm constraint

### 9.1. Ràng buộc mặc định kiểm tra ở cuối statement

Trong Oracle 19c, constraint **`NOT DEFERRABLE`** là mặc định; constraint được kiểm tra khi statement thực thi theo semantics của Oracle, với phát hiện lỗi tại statement. Một `INSERT`/`UPDATE` làm row vi phạm thì **statement bị rollback** và Oracle trả lỗi.

```text
Transaction T
  │
  ├─ INSERT row A hợp lệ          → thành công, vẫn chưa COMMIT
  │
  ├─ INSERT row B quantity = -5 → ORA-02290
  │                               statement B bị rollback
  │
  ├─ SELECT kiểm tra row A       → A vẫn ở trong transaction
  │
  └─ COMMIT                      → lưu row A nếu không có lỗi khác
```

Không nên viết ứng dụng coi lỗi constraint là “database tự hủy tất cả công việc đã làm từ đầu transaction”. Mức rollback phụ thuộc **statement** hay **transaction** (đặc biệt khi có constraint deferred hoặc lỗi khác). Application nên quyết định rollback transaction trong error handling theo yêu cầu atomicity của nghiệp vụ.

### 9.2. Lỗi phổ biến

| Mã lỗi | Tình huống thường gặp | Ví dụ |
| --- | --- | --- |
| `ORA-02290` | Check constraint violated | `CHECK (quantity > 0)` nhận 0 hoặc âm |
| `ORA-01400` | Không thể INSERT NULL vào cột NOT NULL | `INSERT ... email = NULL` |
| `ORA-01407` | Không thể UPDATE cột NOT NULL thành NULL | `UPDATE ... SET email = NULL` |
| `ORA-02293` | Không thể validate constraint vì dữ liệu hiện có vi phạm | `ENABLE VALIDATE` khi có row sai |
| `ORA-02296` | Không thể enable NOT NULL vì có NULL | `ALTER TABLE ... MODIFY ... NOT NULL` |
| `ORA-02291` | Foreign key thiếu parent row | Thuộc **FK**, không phải CHECK |
| `ORA-00001` | Unique constraint/index violated | Thuộc **UNIQUE/PK**, không phải CHECK |

Các error text chi tiết có thể khác theo release và ngữ cảnh; ưu tiên **mã lỗi, tên constraint** và metadata chính xác của database thay vì đoán từ câu thông báo đã được ứng dụng dịch lại.

### 9.3. Khi nhiều CHECK cùng bị vi phạm

Oracle không cam kết thứ tự thực hiện các CHECK. Một row có thể sai `quantity`, `discount` và `status` cùng lúc nhưng lỗi trả về chỉ chỉ ra **một** constraint ở lần DML đó. Không dùng thứ tự constraint để quyết định thông báo nghiệp vụ; ứng dụng có thể kiểm tra trước nhiều trường để trả danh sách lỗi thân thiện, trong khi database vẫn chặn dữ liệu không hợp lệ.

## 10. DEFERRABLE: kiểm tra ở statement hay tới COMMIT?

Khái niệm **deferrability** khác với `ENABLE/NOVALIDATE`:

- **`NOT DEFERRABLE` (mặc định):** không được hoãn kiểm tra đến COMMIT; ràng buộc được kiểm tra ở statement.
- **`DEFERRABLE INITIALLY IMMEDIATE`:** mặc định kiểm tra sau mỗi statement, nhưng một transaction có thể đặt `SET CONSTRAINTS ... DEFERRED`.
- **`DEFERRABLE INITIALLY DEFERRED`:** mặc định kiểm tra tại COMMIT, nhưng transaction có thể chuyển về `IMMEDIATE` bằng `SET CONSTRAINTS`.

Oracle 19c **có hỗ trợ ràng buộc NOT NULL deferrable** nếu khai báo như vậy, bên cạnh CHECK và một số loại constraint khác. Không nên kết luận rằng mọi NOT NULL đều không thể deferred chỉ vì ví dụ thông thường kiểm tra ngay.

### 10.1. Lab minh họa CHECK kiểm tra trễ

```sql
CREATE TABLE defer_check_lab (
    id     NUMBER PRIMARY KEY,
    amount NUMBER,
    CONSTRAINT defer_amount_ck
      CHECK (amount >= 0)
      DEFERRABLE INITIALLY DEFERRED
);

-- Câu lệnh đầu tiên của transaction tạm thời tạo row sai CHECK:
INSERT INTO defer_check_lab (id, amount) VALUES (1, -10);

-- Trước COMMIT, sửa lại để toàn transaction kết thúc hợp lệ:
UPDATE defer_check_lab
SET    amount = 10
WHERE  id = 1;

COMMIT; -- Có thể hoàn thành vì trạng thái cuối thỏa CHECK.
```

Nếu để lại `amount = -10` và `COMMIT`, Oracle sẽ phát hiện vi phạm tại commit và **transaction không được commit**; theo hành vi ràng buộc deferred, transaction bị rollback khi commit thất bại vì constraint. Vì vậy **DML tạm thành công không có nghĩa transaction đã được chấp nhận**.

Trong transaction có constraint deferrable:

```sql
-- Đặt tất cả constraints có thể deferrable thành deferred cho transaction.
SET CONSTRAINTS ALL DEFERRED;

-- Kiểm tra tất cả các constraints có thể defer ngay tại đây,
-- trước khi thực sự COMMIT.
SET CONSTRAINTS ALL IMMEDIATE;
```

`SET CONSTRAINTS` chỉ ảnh hưởng trạng thái kiểm tra **trong transaction hiện tại**, không thay đổi định nghĩa `INITIALLY` vĩnh viễn. Không gọi `SET CONSTRAINTS` tùy tiện trong trigger; Oracle có hạn chế về câu lệnh đó.

### 10.2. Deferrability là thuộc tính thiết kế

Oracle không cho đổi một constraint từ `NOT DEFERRABLE` sang `DEFERRABLE` bằng cách `MODIFY` thuộc tính deferrability sau khi tạo; thông thường phải **drop/re-create** constraint theo quy trình quản trị có kiểm soát. Vì vậy cần xác định ngay khi thiết kế bảng. Phần lớn rule như `quantity > 0`, `status IN (...)` nên dùng default `NOT DEFERRABLE`; chỉ deferred khi có nhu cầu hợp lệ cần trạng thái tạm trong transaction.

**Không dùng deferred constraint như cách hợp pháp hóa dữ liệu sai cuối transaction.** Nó chỉ cho phép **tạm thời chưa thỏa**, nhưng cuối transaction phải hợp lệ.

## 11. Trạng thái ENABLE/DISABLE và VALIDATE/NOVALIDATE

Một constraint trong Oracle còn có hai chiều quan trọng:

1. **`ENABLED` hay `DISABLED`:** có thực thi kiểm tra DML tương lai không?
2. **`VALIDATED` hay `NOT VALIDATED`:** dữ liệu tồn tại đã được Oracle kiểm tra/đảm bảo thỏa constraint đến mức nào?

| Trạng thái | DML sau khi bật trạng thái | Dữ liệu hiện có | Mục đích và lưu ý |
| --- | --- | --- | --- |
| **`ENABLE VALIDATE`** | Phải tuân thủ | Đã được kiểm tra thỏa | Trạng thái mạnh nhất cho integrity thông thường |
| **`ENABLE NOVALIDATE`** | DML mới và row được sửa phải tuân thủ | Có thể còn row cũ vi phạm | Phù hợp giai đoạn áp constraint cho dữ liệu legacy |
| **`DISABLE NOVALIDATE`** | Không enforce constraint | Không bảo đảm thỏa | Chấp nhận rủi ro dữ liệu mới vi phạm; cần kiểm soát đặc biệt |
| **`DISABLE VALIDATE`** | Constraint bị disabled; có hạn chế DML trên các cột liên quan | Được đánh dấu validated | Chế độ đặc biệt thường có mục đích quản trị/data warehouse, không nên hiểu như “disable bình thường” |

**Điểm dễ nhầm nhất:** `ENABLE NOVALIDATE` **không có nghĩa database sẽ chỉ quan sát mà không chặn DML mới**. Nó vẫn kiểm tra các row được thao tác kể từ khi enable, dù các row lịch sử có thể chưa sạch.

### 11.1. Điều gì xảy ra với row cũ đang vi phạm?

Giả sử trước đây bảng `legacy_orders` chứa một row `quantity = -3`. DBA thêm:

```sql
ALTER TABLE legacy_orders
  ADD CONSTRAINT legacy_qty_ck
  CHECK (quantity > 0)
  ENABLE NOVALIDATE;
```

Ràng buộc trên được enforce cho DML sau đó, nhưng **row -3 đã tồn tại vẫn có thể ở lại bảng**. Khi cần đạt trạng thái `ENABLE VALIDATE`, DBA phải sửa/xóa các row vi phạm hoặc áp dụng quy trình data remediation; không nên tuyên bố dữ liệu toàn bảng sạch chỉ vì constraint đã `ENABLED`.

### 11.2. `RELY` không phải chứng minh dữ liệu thật

`RELY`/`NORELY` có liên quan việc optimizer/query rewrite **tin vào một số constraint ở trạng thái NOVALIDATE** trong những chế độ integrity được hỗ trợ. Nó **không quét sạch dữ liệu vi phạm** và **không đồng nghĩa constraint đang được enforce trên toàn bộ row lịch sử**.

Nếu đánh dấu một giả định không đúng rồi để query rewrite dựa vào giả định đó, việc suy luận kết quả truy vấn có thể sai về mặt nghiệp vụ. Chỉ dùng `RELY` theo chính sách đã xác minh dữ liệu, semantics và môi trường.

## 12. Thêm CHECK vào bảng legacy mà không chặn kế hoạch triển khai

Giả sử một bảng hiện có hàng triệu row và một số `amount < 0` do dữ liệu cũ. Mục tiêu là “chặn lỗi mới ngay” nhưng “sửa dữ liệu lịch sử theo batch”.

### Bước A — Kiểm kê dữ liệu trước khi đổi DDL

```sql
-- Chỉ đọc; nếu amount phải NOT NULL thì đếm NULL riêng.
SELECT COUNT(*) AS negative_amount_rows
FROM   legacy_orders
WHERE  amount < 0;

SELECT COUNT(*) AS null_amount_rows
FROM   legacy_orders
WHERE  amount IS NULL;

SELECT order_id, amount
FROM   legacy_orders
WHERE  amount < 0
ORDER BY order_id
FETCH FIRST 50 ROWS ONLY;
```

**Không dùng `WHERE NOT (amount >= 0)` để tìm tất cả row vi phạm nếu bạn cũng muốn bắt NULL**: `NOT (NULL >= 0)` vẫn UNKNOWN, và `WHERE` chỉ trả row TRUE. Phải kiểm tra NULL riêng nếu yêu cầu nghiệp vụ bao gồm bắt buộc.

### Bước B — Bật constraint cho dữ liệu mới

```sql
-- Chỉ thực hiện sau khi phê duyệt change; đây là DDL thật.
ALTER TABLE legacy_orders
  ADD CONSTRAINT legacy_amount_ck
  CHECK (amount >= 0)
  ENABLE NOVALIDATE;
```

Từ thời điểm này, DML mới không được tạo `amount < 0` ở row được kiểm tra theo trạng thái constraint. Nhưng nếu `amount` vẫn nullable, CHECK **không ngăn NULL**. Không nên nói “mọi dữ liệu mới đều có amount hợp lệ” khi chưa định nghĩa đầy đủ rule.

### Bước C — Làm sạch dữ liệu cũ bằng nghiệp vụ

Ví dụ lựa chọn xử lý:

- Phân loại row âm là hoàn tiền hợp lệ hay lỗi nhập; nếu là hoàn tiền hợp lệ thì **đổi mô hình nghiệp vụ**, không ép sửa thành 0.
- Nếu row thực sự sai, chọn giá trị sửa theo nguồn dữ liệu gốc được xác nhận.
- Chạy batch cập nhật có kiểm soát transaction, logging, quyền và kiểm soát số row.
- Nếu row cũ vi phạm bị cập nhật, Oracle có thể yêu cầu row mới sau UPDATE phải tuân thủ CHECK; đừng giả định có thể sửa một trường không liên quan mà giữ nguyên giá trị vi phạm.

Sau khi số vi phạm về 0:

```sql
SELECT COUNT(*) AS remaining_invalid_rows
FROM   legacy_orders
WHERE  amount < 0;

-- Sau khi kiểm tra phạm vi/các bên phụ thuộc:
ALTER TABLE legacy_orders
  MODIFY CONSTRAINT legacy_amount_ck ENABLE VALIDATE;
```

`ENABLE VALIDATE` cho kết quả bảo đảm mạnh hơn, vì Oracle phải xác minh các row cần thiết đã thỏa constraint. Trên bảng lớn, validation có thể tốn I/O/CPU và ảnh hưởng thời gian triển khai, cần đánh giá trong change window.

### Bước D — Bắt NULL riêng nếu quy tắc mới yêu cầu

```sql
-- Xem dữ liệu thiếu:
SELECT COUNT(*) FROM legacy_orders WHERE amount IS NULL;

-- Sau khi đã xử lý NULL và phê duyệt thay đổi:
ALTER TABLE legacy_orders
  MODIFY (amount CONSTRAINT legacy_amount_nn NOT NULL);
```

Không thêm `NOT NULL` khi những dòng NULL hiện hữu chưa được xử lý nếu bạn mong thao tác VALIDATE thành công. Ngoài ra, thêm default sẽ không tự động sửa tất cả giá trị NULL cũ nếu không có một bước dữ liệu phù hợp.

**Các lệnh trong phần này giả định bảng `LEGACY_ORDERS` có sẵn trong schema và column names tương ứng.** Chúng là mẫu quy trình, không phải script thay đổi production đã kiểm thử trên cấu trúc cụ thể.

## 13. Metadata: kiểm kê CHECK, NOT NULL và trạng thái thực thi

Oracle ghi thông tin constraint trong data dictionary. Với schema hiện tại:

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       rely,
       search_condition_vc
FROM   user_constraints
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY constraint_name;
```

**Diễn giải cột:**

| Cột | Nội dung |
| --- | --- |
| `CONSTRAINT_NAME` | Tên rõ ràng như `ORDERS_LAB_STATUS_CK` hoặc tên Oracle sinh `SYS_C...` |
| `CONSTRAINT_TYPE` | `C` cho CHECK và NOT NULL; `P` cho PK; `U` cho UNIQUE; `R` cho FK |
| `STATUS` | `ENABLED`/`DISABLED` |
| `VALIDATED` | `VALIDATED`/`NOT VALIDATED` |
| `DEFERRABLE` | `DEFERRABLE`/`NOT DEFERRABLE` |
| `DEFERRED` | Trạng thái mặc định `IMMEDIATE`/`DEFERRED` của constraint |
| `RELY` | Metadata liên quan query rewrite/integrity assumption |
| `SEARCH_CONDITION_VC` | Biểu thức CHECK ở dạng VARCHAR2 cho việc đọc nhanh |

Ở Oracle 19c, `SEARCH_CONDITION_VC` thuận tiện khi hiển thị trong SQL client, nhưng có thể **bị cắt** nếu biểu thức dài; `SEARCH_CONDITION` là cột kiểu `LONG` với hạn chế thao tác SQL. Khi cần xuất nguyên vẹn định nghĩa constraint, dùng `DBMS_METADATA` hoặc công cụ metadata tương ứng thay vì dựa vào một cột preview bị giới hạn.

### 13.1. Cột nào tham gia constraint?

```sql
SELECT c.constraint_name,
       c.constraint_type,
       cc.position,
       cc.column_name
FROM   user_constraints c
JOIN   user_cons_columns cc
       ON cc.constraint_name = c.constraint_name
      AND cc.table_name      = c.table_name
WHERE  c.table_name = 'ORDERS_CHECK_LAB'
ORDER BY c.constraint_name, cc.position;
```

Không phải constraint nào cũng gắn với **một cột**. CHECK out-of-line `valid_to >= valid_from` có nhiều column references; khi xây công cụ kiểm kê, tránh lấy row đầu tiên trong `USER_CONS_COLUMNS` rồi cho rằng đó là toàn bộ biểu thức.

### 13.2. `USER_TAB_COLUMNS.NULLABLE` khác metadata CHECK

```sql
SELECT column_name,
       data_type,
       nullable,
       data_default
FROM   user_tab_columns
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY column_id;
```

`NULLABLE = 'N'` thường thể hiện Oracle đã có metadata nullability được bảo đảm phù hợp, nhưng cách xác định còn phụ thuộc constraint state và loại cột. Vì thế khi lập báo cáo compliance, đọc **cả `USER_TAB_COLUMNS` và `USER_CONSTRAINTS`**, thay vì chỉ kiểm tra `NULLABLE` để suy rằng constraint đang `ENABLE VALIDATE`.

### 13.3. Xem DDL đã được chuẩn hóa bằng `DBMS_METADATA`

```sql
-- SQL*Plus / SQLcl: cấu hình CLOB hiển thị đầy đủ.
SET LONG 200000
SET PAGESIZE 0

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS_CHECK_LAB')
FROM   dual;
```

DDL cho thấy các `NOT NULL`/`CHECK` và constraint states theo chế độ transform; một số thông tin physical cũng có thể xuất hiện. Nếu công cụ chỉ hiển thị đoạn đầu CLOB, đừng kết luận constraints đã biến mất. Việc đọc metadata từ schema khác cần quyền thích hợp.

### 13.4. CDB/PDB: xác định container trước khi đọc

Trong Oracle Multitenant, cùng tên `ORDERS_CHECK_LAB` có thể tồn tại ở hai PDB. Kiểm tra:

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM   dual;
```

`USER_CONSTRAINTS` và `DBMS_METADATA.GET_DDL` thông thường làm việc trong ngữ cảnh **PDB/session hiện tại** và theo quyền. Đừng trộn DDL constraint của `PDB_A` với data/metadata `PDB_B` khi audit hai tenant.

## 14. Dùng constraint sao cho hoạt động và dễ quản trị

### 14.1. Tên constraint cần phản ánh một quy tắc

Nên dùng tên nhất quán, ví dụ:

- `orders_quantity_nn`: quantity bắt buộc.
- `orders_quantity_pos_ck`: quantity > 0.
- `orders_status_domain_ck`: status thuộc miền cho phép.
- `orders_dates_order_ck`: thứ tự ngày.
- `orders_cancel_reason_ck`: canceled phải có reason.

Một tên như `CHECK1` hoặc `SYS_C012345` không giúp nhóm vận hành hiểu lỗi. Oracle có giới hạn độ dài identifier theo release/compatibility; giữ tên rõ, ngắn, không chứa thông tin nhạy cảm.

### 14.2. Chọn constraint theo tầng bảo vệ

```text
Rule: "quantity must be positive"
  └─ CHECK(quantity > 0) + NOT NULL

Rule: "customer_id must exist in customers"
  └─ FOREIGN KEY, không dùng CHECK subquery

Rule: "email must be unique"
  └─ UNIQUE (và NOT NULL nếu nghiệp vụ bắt buộc)

Rule: "total ordered quantity <= stock"
  └─ Transaction/locking + row invariants

Rule: "created timestamp must not be in the future at insertion"
  └─ Application/DB procedure/trigger tại thời điểm ghi;
     SYSDATE không hợp lệ trong CHECK 19c

Rule: "percentage valid only if supplied"
  └─ CHECK(pct BETWEEN 0 AND 100), cho NULL theo thiết kế
```

Một constraint chỉ tốt khi phát biểu được **đúng quy tắc**, không chỉ đủ để câu `CREATE TABLE` chạy thành công.

### 14.3. Concurrency và tính nhất quán giao dịch

Oracle thực thi CHECK trên row được thao tác với cơ chế giao dịch/locking thích hợp. Nếu hai session cập nhật **cùng một row**, row lock và tính toán cập nhật có thể ngăn một số lỗi cạnh tranh. Nhưng CHECK không tự biết tổng số row thuộc một nhóm, số booking đang chồng lấn hay trạng thái hệ thống bên ngoài.

Ví dụ `CHECK (balance >= 0)` trên từng tài khoản ngăn số dư âm sau update, nhưng **không** thay thế thiết kế transaction chuyển khoản hai tài khoản, bảo đảm tổng tiền, xử lý timeout khi không biết commit thành công hay chống double-spend ở tầng giao dịch.

### 14.4. Hiệu năng và query optimizer

- CHECK đơn giản thường có chi phí nhỏ so với logic nghiệp vụ, nhưng hàng triệu DML cùng nhiều biểu thức phức tạp vẫn tạo overhead cần đo.
- CHECK **không tự tạo index**. Index là quyết định riêng phục vụ query và có thể phục vụ constraint khác (PK/UNIQUE) theo cơ chế Oracle.
- Metadata constraint hợp lệ có thể hỗ trợ optimizer suy luận trong những tình huống được hỗ trợ. Không đánh dấu `RELY` khi dữ liệu chưa thật sự tin cậy.
- DML bị chặn bởi CHECK tạo lỗi/rollback statement, nhưng không mặc định đảm bảo chương trình đã rollback toàn bộ transaction.
- Chế độ `DISABLE` hoặc `NOVALIDATE` có thể dùng trong maintenance, song phải đặt ra kế hoạch xác nhận lại chất lượng dữ liệu.

### 14.5. Đừng loại bỏ constraints chỉ vì ứng dụng đã validate

Ứng dụng có thể bỏ sót batch load, SQL console, ETL hoặc phiên bản client cũ; DB constraint là “ranh giới cuối cùng” cho bất biến có thể biểu diễn khai báo. Nếu có yêu cầu import dữ liệu không sạch để làm việc tiếp, cân nhắc **staging table riêng** hoặc trạng thái chuyển tiếp có kiểm soát thay vì vô hiệu hóa toàn bộ bảng nghiệp vụ.

## 15. DDL và migration: cẩn thận với implicit COMMIT

`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` là DDL trong Oracle và có semantics **implicit commit**. Vì thế:

1. Không đặt một nhóm lệnh DML remediation vào cùng transaction rồi trông chờ `ROLLBACK` sẽ đảo ngược cả lệnh `ALTER TABLE`.
2. Nên backup/snapshot metadata, chuẩn bị rollback plan dạng DDL/DML phù hợp, không chỉ `ROLLBACK`.
3. Test các câu `ENABLE VALIDATE` với data volume tương đương staging và thời gian hoạt động cao.
4. Ứng dụng nên bắt lỗi constraint với thông báo thân thiện nhưng không bỏ qua ORA error.
5. Schema migration framework cần khai báo constraint name/column có chủ đích; không hard-code assumption về `SYS_C...`.

Một deployment “thêm NOT NULL cho column mới” đôi khi cần **expand–backfill–constrain**:

```text
1. Thêm cột nullable (expand schema)
2. Triển khai ứng dụng có thể ghi cột mới
3. Backfill giá trị hợp lệ cho dữ liệu cũ
4. Kiểm kê NULL và dữ liệu vi phạm
5. Chốt NOT NULL / CHECK với validation đúng
6. Loại bỏ code tương thích ngược khi đủ điều kiện
```

Phương án cụ thể còn phụ thuộc yêu cầu zero-downtime, Oracle release, lock/DDL behavior, partitioning và dữ liệu hiện có. Không hứa mọi `ALTER TABLE` đều không khóa hoặc “online” chỉ vì constraint đơn giản.

## 16. Bài thực hành an toàn theo từng phiên

> Chỉ chạy với schema lab và quyền phù hợp. Các câu DML cố tình sai sẽ trả ORA error để minh họa. Nếu SQL*Plus được cấu hình `WHENEVER SQLERROR EXIT`, nên chạy từng câu thử riêng; không gom mọi câu lỗi vào một script triển khai.

### Phần A — Đọc trạng thái constraint đã tạo

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       search_condition_vc
FROM   user_constraints
WHERE  table_name = 'ORDERS_CHECK_LAB'
ORDER BY constraint_name;
```

Mong đợi: nhiều constraint `C`, một PK `P`; `NOT NULL` cũng được phản ánh trong nhóm `C`.

### Phần B — Dùng SAVEPOINT để thử DML

```sql
SAVEPOINT before_constraint_lab;

INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (101, 'LAB-101', 'NEW', 1, 1000);

-- Cố ý sai, chạy riêng:
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (102, 'LAB-102', 'NEW', -1, 1000);
-- Dự kiến ORA-02290.

SELECT order_id, quantity
FROM   orders_check_lab
WHERE  order_id IN (101, 102)
ORDER BY order_id;

ROLLBACK TO before_constraint_lab;
```

Sau lỗi của row 102, row 101 vẫn có thể tồn tại trong transaction trước khi rollback đến savepoint. Đây là tính chất rollback của **statement** đối với constraint nondeferrable, không phải tự rollback toàn transaction.

### Phần C — Quan sát NULL có được CHECK chấp nhận không

```sql
-- DISCOUNT_PCT không có NOT NULL, nên được phép NULL.
SAVEPOINT before_null_lab;

INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price, discount_pct)
VALUES (103, 'LAB-103', 'NEW', 1, 1000, NULL);

SELECT order_id, discount_pct
FROM   orders_check_lab
WHERE  order_id = 103;

ROLLBACK TO before_null_lab;
```

Không được giải thích rằng CHECK `BETWEEN 0 AND 100` đã xác nhận discount 0–100 cho row 103: thực chất **điều kiện UNKNOWN được chấp nhận**, và nghiệp vụ chủ động cho phép trường tùy chọn.

### Phần D — Xem lỗi khi giá trị không phải NULL nhưng chỉ toàn dấu cách

```sql
-- Chạy riêng, dự kiến vi phạm ORDERS_LAB_CODE_CK.
INSERT INTO orders_check_lab
    (order_id, order_code, status, quantity, unit_price)
VALUES (104, '   ', 'NEW', 1, 1000);
```

`NOT NULL` của `ORDER_CODE` không đủ loại chuỗi toàn khoảng trắng, trong khi `CHECK (TRIM(order_code) IS NOT NULL)` mới thực hiện quy tắc “có nội dung”.

### Phần E — Xem lỗi deferred chỉ ở COMMIT (tùy chọn)

Chạy sau khi hiểu tác động transaction và **trên bảng lab riêng `DEFER_CHECK_LAB`** từ phần 10. Đây là bước dễ nhầm nhất:

```sql
-- Constraint DEFERRABLE INITIALLY DEFERRED.
INSERT INTO defer_check_lab (id, amount) VALUES (2, -100);

-- Tạm thời UPDATE lại để cuối transaction hợp lệ.
UPDATE defer_check_lab SET amount = 100 WHERE id = 2;
COMMIT;
```

Nếu không UPDATE, COMMIT sẽ thất bại và toàn transaction liên quan có thể bị rollback. Không dùng deferred constraint để giấu dữ liệu vi phạm hay làm “mềm” tính toàn vẹn sau commit.

### Phần F — Dọn môi trường lab

Các lệnh dưới đây **xóa bảng và có implicit commit**; chỉ chạy khi chắc chắn các bảng là object vừa được tạo trong schema lab và không còn dữ liệu cần giữ:

```sql
DROP TABLE orders_check_lab PURGE;
DROP TABLE defer_check_lab PURGE;
```

Nếu các bảng demo `score_demo`, `score_required_demo`, `product_demo`, `customer_contact_demo`... cũng được tạo trong schema lab, cần dọn từng object đúng tên và xác nhận quyền sở hữu; **không** dùng một script DROP hàng loạt không kiểm soát.

## 17. Tình huống thực tế và cách phân tích

### Tình huống 1 — Cột có CHECK nhưng vẫn có NULL

**Dấu hiệu:** DBA thấy `CHECK (score BETWEEN 0 AND 100)` nhưng có row `score IS NULL`.

**Giải thích:** CHECK cho phép UNKNOWN. Cần xác minh có `NOT NULL` hay không và liệu ứng dụng có cho phép “chưa nhập” một cách có chủ đích. Nếu bắt buộc thì khai báo NOT NULL, xử lý NULL cũ trước khi validate.

### Tình huống 2 — Cột có NOT NULL nhưng tên khách hàng toàn dấu cách

**Dấu hiệu:** `NAME = '   '` không bị chặn.

**Giải thích:** NOT NULL chỉ cấm NULL. Có thể thêm `CHECK (TRIM(name) IS NOT NULL)` cho cột VARCHAR2, đồng thời quy định normalization và policy đối với Unicode whitespace/định dạng input từ bên ngoài. `TRIM` mặc định không nhận diện mọi loại whitespace Unicode; nếu nghiệp vụ cần chặt hơn, kiểm tra thêm theo yêu cầu và character set.

### Tình huống 3 — Trạng thái đơn mới xuất hiện không có trong CHECK

**Dấu hiệu:** ứng dụng triển khai status `REFUNDED`, insert trả `ORA-02290`.

**Giải thích:** CHECK miền giá trị chưa được migration cùng ứng dụng. Cần release coordination: thêm trạng thái vào constraint theo quy trình, hoặc chuyển sang bảng tham chiếu nếu miền thay đổi thường xuyên và cần metadata. Không disable constraint vĩnh viễn để ứng dụng “chạy qua”.

### Tình huống 4 — Câu lệnh SELECT tìm row sai không ra kết quả nhưng VALIDATE thất bại

**Dấu hiệu:** DBA kiểm tra `WHERE NOT (col > 0)`, không thấy row, nhưng có lỗi khi thêm constraint `col > 0` kết hợp yêu cầu NOT NULL.

**Giải thích:** `NULL` bị bỏ qua vì `NOT UNKNOWN = UNKNOWN`, `WHERE` không chọn row đó. Kiểm tra `col IS NULL` riêng. Ngoài ra phải đối chiếu **đúng** biểu thức, chuyển đổi kiểu, collation, dữ liệu đang thay đổi và constraint state.

### Tình huống 5 — ENABLE NOVALIDATE nhưng vẫn có số âm

**Dấu hiệu:** sau khi enable, query thấy row `amount=-3`.

**Giải thích:** row có thể đã tồn tại trước đó. `ENABLE NOVALIDATE` kiểm soát DML sau khi bật nhưng không ép mọi row cũ phải sạch. Khi hoàn tất remediation mới nâng `ENABLE VALIDATE`.

### Tình huống 6 — Trigger kiểm tra tổng mỗi nhóm nhưng vẫn có lỗi dưới tải cao

**Dấu hiệu:** test tuần tự thành công, nhưng hai giao dịch song song làm tổng nhóm vượt giới hạn.

**Giải thích:** logic đọc tổng rồi ghi không có locking/serialization thích hợp có race. CHECK không thể biểu diễn invariant xuyên nhiều row; trigger cũng không tự bảo đảm đúng concurrency. Cần phân tích lại transaction và mẫu dữ liệu.

### Tình huống 7 — DML thành công nhưng COMMIT thất bại

**Dấu hiệu:** code dùng constraint `DEFERRABLE INITIALLY DEFERRED`, nhiều INSERT thành công, COMMIT bị rollback do CHECK.

**Giải thích:** constraint deferred được kiểm tra tại COMMIT. Ứng dụng phải xử lý lỗi ở **commit boundary**, chứ không chỉ catch ORA tại mỗi INSERT.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Bảng có `CHECK (age >= 18)` nhưng không có NOT NULL. `age = NULL` được chấp nhận không?

**Câu 2.** Vì sao `CHECK (LENGTH(TRIM(code)) > 0)` có thể không chặn chuỗi chỉ gồm dấu cách trong Oracle?

**Câu 3.** Một đơn hàng cần `status = 'CANCELLED'` thì `cancel_reason` phải có nội dung. Cách viết biểu thức nào phù hợp, và cột nào nên NOT NULL?

**Câu 4.** Có thể đặt `CHECK (customer_id IN (SELECT id FROM customers))` để thay FOREIGN KEY không?

**Câu 5.** `ENABLE NOVALIDATE` khác `ENABLE VALIDATE` ra sao đối với dữ liệu cũ?

**Câu 6.** Khi `DEFERRABLE INITIALLY DEFERRED`, tại sao INSERT sai CHECK có thể được chấp nhận tạm thời nhưng COMMIT thất bại?

**Câu 7.** `CONSTRAINT_TYPE='C'` trong `USER_CONSTRAINTS` có nghĩa tất cả đều là CHECK nghiệp vụ không?

**Câu 8.** Vì sao chỉ có CHECK `balance >= 0` chưa đủ để cài đặt an toàn việc chuyển tiền giữa hai tài khoản?

**Câu 9.** Một bảng có `NOT NULL` trên `VARCHAR2`. `''` và `'   '` bị xử lý giống nhau không?

**Câu 10.** Khi thêm constraint cho bảng có dữ liệu legacy, nên triển khai theo những giai đoạn nào để không bỏ qua row vi phạm cũ?

<details>
<summary>Gợi ý đáp án</summary>

1. **Có.** So sánh `NULL >= 18` là UNKNOWN, CHECK chỉ chặn FALSE. Muốn bắt buộc nhập phải thêm NOT NULL.
2. `TRIM('   ')` có thể trở thành chuỗi rỗng, Oracle coi là NULL; `LENGTH(NULL)>0` trả UNKNOWN và CHECK chấp nhận. Dùng `TRIM(code) IS NOT NULL`, thêm NOT NULL cho cột.
3. `CHECK (status <> 'CANCELLED' OR TRIM(cancel_reason) IS NOT NULL)`, đồng thời `status NOT NULL` và constraint cho miền giá trị.
4. **Không.** CHECK không cho subquery/đọc bảng khác. Dùng FOREIGN KEY.
5. `ENABLE NOVALIDATE` chặn DML mới/row cập nhật vi phạm nhưng dữ liệu lịch sử có thể sai; `ENABLE VALIDATE` kiểm tra và bảo đảm dữ liệu hiện có thỏa.
6. Oracle hoãn việc kiểm tra đến cuối transaction. Trạng thái cuối phải hợp lệ; nếu không, COMMIT thất bại và transaction bị rollback.
7. **Không.** Oracle thể hiện cả NOT NULL dưới loại `C`; xem `SEARCH_CONDITION` và metadata cột.
8. Còn atomicity của hai UPDATE, tổng số dư, lỗi mạng/commit, double-spend, concurrency và business ledger. Cần transaction design chặt.
9. Không. `''` thường được Oracle xử lý thành NULL và bị NOT NULL chặn; `'   '` không NULL, nên có thể được lưu.
10. Kiểm kê/định nghĩa rule → bật `ENABLE NOVALIDATE` nếu thích hợp để chặn lỗi mới → làm sạch/đối chiếu row cũ → chuyển `ENABLE VALIDATE` → xác minh trạng thái dictionary.

</details>

## 19. Nguyên tắc kết luận

- **CHECK bảo vệ điều kiện trên một row**, không phải điều kiện toàn database.
- **`FALSE` mới là lỗi CHECK; `UNKNOWN` do NULL vẫn qua**. Nếu cần giá trị bắt buộc, dùng `NOT NULL` và thiết kế NULL semantics rõ ràng.
- **NOT NULL không đồng nghĩa “có nội dung có ý nghĩa”**; khoảng trắng và chuỗi placeholder có thể cần một CHECK khác.
- **Có thể so sánh nhiều cột cùng row**, nhưng không tham chiếu bảng khác, subquery, user-defined function hoặc thời gian hiện tại theo CHECK Oracle 19c.
- **Constraint có trạng thái và thời điểm enforce**: `ENABLE/DISABLE`, `VALIDATE/NOVALIDATE` và `DEFERRABLE` là các chiều khác nhau.
- **Dữ liệu cũ với NOVALIDATE chưa được chứng minh sạch**. Muốn có bảo đảm đầy đủ, phải xử lý tồn đọng và chuyển sang VALIDATE.
- **Dùng PK/UNIQUE/FK cho invariant liên quan key và bảng khác**, transaction có kiểm soát cho các invariant tổng hợp/concurrency.
- **Đọc metadata thực tế** qua `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_TAB_COLUMNS` và `DBMS_METADATA` thay vì chỉ tin vào câu DDL từng được viết trong Git.

## 20. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — `constraint`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): cú pháp `NOT NULL`, `CHECK`, điều kiện bị cấm, `DEFERRABLE`, `ENABLE`/`VALIDATE`/`RELY` và ví dụ.
2. [Oracle Database 19c Database Development Guide — Maintaining Data Integrity in Database Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/data-integrity.html): thiết kế CHECK, ba giá trị TRUE/FALSE/UNKNOWN và giới hạn row-level.
3. [Oracle Database 19c Concepts — Data Integrity](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-integrity.html): các loại constraint, trạng thái enforcement/validation và xử lý immediate/deferred.
4. [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html): thêm, sửa, enable, disable, validate và xử lý exceptions trên dữ liệu hiện có.
5. [Oracle Database 19c SQL Language Reference — `CREATE TABLE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html), [`ALTER TABLE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): tạo và thay đổi constraint trong DDL.
6. [Oracle Database 19c SQL Language Reference — `SET CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-CONSTRAINTS.html): thay đổi thời điểm kiểm tra deferrable constraint trong transaction.
7. [Oracle Database 19c Database Reference — `USER_CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONSTRAINTS.html), [`ALL_CONSTRAINTS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONSTRAINTS.html), [`USER_CONS_COLUMNS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONS_COLUMNS.html): đọc metadata của ràng buộc.
8. [Oracle Database 19c PL/SQL Packages and Types Reference — `DBMS_METADATA`](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html): xuất DDL để đối chiếu constraints với schema hiện tại.

**Chuỗi quyết định cần nhớ:** phát biểu chính xác invariant → chọn phạm vi một cột/một row/khóa/đa row → xử lý NULL và ba-valued logic → chọn NOT NULL/CHECK/PK/UNIQUE/FK hoặc transaction logic → chọn thời điểm enforce/trạng thái validate → kiểm chứng metadata và dữ liệu trước khi triển khai.
