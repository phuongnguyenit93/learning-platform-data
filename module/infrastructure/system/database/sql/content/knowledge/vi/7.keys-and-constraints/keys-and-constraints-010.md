# Ràng buộc kiểm tra tức thời hoặc trì hoãn theo hệ quản trị

Khi thiết kế bảng SQL, ta thường đặt **ràng buộc toàn vẹn (constraints)** để dữ liệu luôn đáp ứng các quy tắc như khóa chính không trùng, khóa ngoại phải tham chiếu đến bản ghi hợp lệ hoặc số lượng phải không âm. Nhưng **thời điểm hệ quản trị kiểm tra ràng buộc** cũng quan trọng không kém bản thân quy tắc.

Một số ràng buộc được kiểm tra **ngay khi thực hiện câu lệnh**; một số loại có thể được cấu hình **trì hoãn đến khi giao dịch kết thúc bằng `COMMIT`**. Sự khác biệt này quyết định liệu bạn có thể thực hiện nhiều bước cập nhật mà **trạng thái trung gian tạm thời vi phạm ràng buộc**, miễn là trạng thái cuối cùng hợp lệ, hay không.

Bài học thuộc chương **Khóa và ràng buộc** của module **Database SQL**, sử dụng **PostgreSQL** cho ví dụ SQL thực hành và đối chiếu với **Oracle Database, SQLite, MySQL/MariaDB và SQL Server**. Cú pháp và loại ràng buộc có thể trì hoãn khác nhau giữa các hệ quản trị, vì vậy cần xác định **đúng DBMS và phiên bản đang sử dụng**.

> **Lưu ý về thuật ngữ:** “Kiểm tra ràng buộc” trong tiêu đề nói về **thời điểm xác minh constraint**, không chỉ nói riêng đến ràng buộc có tên `CHECK`. Trong PostgreSQL, `CHECK` là một loại ràng buộc được kiểm tra ngay; trong khi một số ràng buộc `FOREIGN KEY`, `UNIQUE`, `PRIMARY KEY` hoặc `EXCLUDE` có thể được hoãn kiểm tra.

## 1. Vì sao thời điểm kiểm tra có thể thay đổi kết quả?

Giả sử có bảng `customers` và `orders`:

- `customers.customer_id` là khóa chính.
- `orders.customer_id` là khóa ngoại, phải trỏ đến khách hàng có thật.

Bạn nhận dữ liệu gồm một khách hàng mới mang mã `100` và một đơn hàng của khách hàng đó. Vì chương trình nhập dữ liệu theo từng bước, có thể **chèn đơn hàng trước khi chèn khách hàng**:

```sql
-- Bước 1: đơn hàng nhắc đến customer_id = 100.
INSERT INTO orders (order_id, customer_id)
VALUES (1, 100);

-- Bước 2: khách hàng 100 mới được tạo.
INSERT INTO customers (customer_id)
VALUES (100);
```

Nếu khóa ngoại kiểm tra **tức thời**, câu `INSERT` đầu có thể thất bại do khách hàng `100` chưa tồn tại tại thời điểm kiểm tra.

Nếu khóa ngoại được phép **trì hoãn** và đang ở chế độ trì hoãn, giao dịch có thể tạm có một đơn hàng chưa tìm thấy khách hàng, rồi được sửa ở bước tiếp theo. Khi `COMMIT`, ràng buộc phải **được thỏa mãn hoàn toàn**; việc hoãn không có nghĩa là cho phép dữ liệu sai tồn tại sau khi giao dịch hoàn tất.

Ý tưởng có thể hình dung như sau:

```text
BEGIN
  │
  ├─ INSERT orders(customer_id = 100)
  │     ├─ IMMEDIATE: kiểm tra → lỗi (nếu chưa có customer 100)
  │     └─ DEFERRED: tạm chấp nhận, ghi nhận cần kiểm tra
  │
  ├─ INSERT customers(customer_id = 100)
  │
  └─ COMMIT
        ├─ trạng thái cuối hợp lệ → xác nhận giao dịch
        └─ trạng thái cuối vi phạm → từ chối COMMIT
```

Trong trường hợp đơn giản, chèn khách hàng trước rồi chèn đơn hàng sẽ dễ hiểu hơn. Ràng buộc trì hoãn đặc biệt hữu ích khi quy trình nhập dữ liệu khó sắp xếp thứ tự, khi có **tham chiếu vòng**, hoặc khi cần **hoán đổi các giá trị phải duy nhất**.

## 2. Các khái niệm cần phân biệt

### 2.1. IMMEDIATE và DEFERRED nói về thời điểm kiểm tra

| Chế độ kiểm tra | Ý nghĩa | Hệ quả trong một giao dịch |
|---|---|---|
| **IMMEDIATE** | DBMS kiểm tra ràng buộc trong/ở cuối mỗi câu lệnh, tùy loại ràng buộc và DBMS | Không thể để trạng thái vi phạm kéo dài sang câu lệnh kế tiếp |
| **DEFERRED** | DBMS có thể dời việc xác minh đến `COMMIT` hoặc thời điểm ép kiểm tra sớm | Các trạng thái trung gian có thể vi phạm, nhưng trạng thái cuối vẫn phải hợp lệ |

Cụm từ “kiểm tra ngay” **không luôn có nghĩa sau mỗi hàng (row)**. Ví dụ, một số hệ quản trị đánh giá một ràng buộc sau khi cả câu lệnh `UPDATE` hoàn tất, trong khi ràng buộc khác có thể được kiểm tra khi xử lý từng hàng. Đây là chi tiết phụ thuộc **DBMS và loại constraint**.

Ở PostgreSQL, `NOT NULL` và `CHECK` được kiểm tra trong lúc thêm/sửa hàng; ràng buộc `UNIQUE` không khai báo `DEFERRABLE` cũng có thể phát hiện trùng ngay trong thao tác ghi. Với một ràng buộc **`DEFERRABLE INITIALLY IMMEDIATE`**, kiểm tra có thể được thực hiện ở cuối câu lệnh; khi đổi sang **`DEFERRED`**, kiểm tra được dời đến cuối giao dịch.

### 2.2. DEFERRABLE và INITIALLY là hai thuộc tính khác nhau

Khi định nghĩa constraint trong PostgreSQL và một số DBMS khác, có thể thấy ba lựa chọn:

| Khai báo | Có được đổi sang DEFERRED? | Chế độ mặc định khi bắt đầu giao dịch |
|---|---|---|
| `NOT DEFERRABLE` | Không | Luôn kiểm tra tức thời |
| `DEFERRABLE INITIALLY IMMEDIATE` | Có | Tức thời, nhưng có thể chuyển sang trì hoãn |
| `DEFERRABLE INITIALLY DEFERRED` | Có | Trì hoãn, nhưng có thể chuyển sang tức thời |

Ý nghĩa từ khóa:

- `DEFERRABLE`: **ràng buộc được phép trì hoãn** theo khả năng của DBMS.
- `NOT DEFERRABLE`: không thể chuyển ràng buộc này sang trạng thái trì hoãn.
- `INITIALLY IMMEDIATE`: **bắt đầu mỗi giao dịch** ở chế độ kiểm tra tức thời.
- `INITIALLY DEFERRED`: **bắt đầu mỗi giao dịch** ở chế độ kiểm tra trì hoãn.
- `SET CONSTRAINTS`: thay đổi thời điểm kiểm tra của các ràng buộc được phép trì hoãn **trong giao dịch hiện tại** trên những DBMS hỗ trợ.

Khai báo `DEFERRABLE` **không tự động làm cho ràng buộc luôn được trì hoãn**; nếu không chỉ rõ `INITIALLY DEFERRED` thì mặc định thường là `INITIALLY IMMEDIATE`.

### 2.3. Vi phạm tạm thời khác với dữ liệu cuối cùng không hợp lệ

Giả sử giao dịch chèn một đơn hàng tham chiếu khách hàng chưa có, sau đó chèn khách hàng:

- Ở **bước trung gian**, khóa ngoại tạm vi phạm.
- Ở **trạng thái ngay trước `COMMIT`**, cả hai dòng đã tồn tại nên khóa ngoại hợp lệ.
- Với khóa ngoại thực sự được cấu hình **DEFERRED**, giao dịch có thể được commit.

Nhưng nếu không chèn khách hàng trước khi `COMMIT`, DBMS vẫn phát hiện vi phạm và không xác nhận giao dịch. Trì hoãn thay đổi **thời điểm phát hiện lỗi**, không thay đổi **quy tắc cần thỏa mãn**.

## 3. PostgreSQL hỗ trợ hoãn những ràng buộc nào?

PostgreSQL hỗ trợ `DEFERRABLE` với các loại constraint chính sau:

| Loại ràng buộc | Có thể `DEFERRABLE` trong PostgreSQL? | Ví dụ ứng dụng |
|---|---|---|
| `FOREIGN KEY` / `REFERENCES` | **Có** | Chèn bản ghi con trước bản ghi cha trong một giao dịch |
| `UNIQUE` | **Có** | Hoán đổi hai giá trị duy nhất qua nhiều câu `UPDATE` |
| `PRIMARY KEY` | **Có** | Sắp xếp lại giá trị khóa theo quy trình cần hoãn kiểm tra tính duy nhất |
| `EXCLUDE` | **Có** | Các quy tắc loại trừ chồng lấp dựa trên toán tử, thường dùng với kiểu range |
| `CHECK` | **Không** | Kiểm tra `price >= 0` phải thỏa mãn khi ghi hàng |
| `NOT NULL` | **Không** | Cột được khai báo `NOT NULL` không được tạm nhận giá trị `NULL` |

Đây là giới hạn **cụ thể của PostgreSQL**, không phải quy tắc chung cho mọi DBMS.

Chẳng hạn, trong PostgreSQL:

```sql
-- Hợp lệ: khóa ngoại được phép trì hoãn.
CONSTRAINT order_customer_fk
    FOREIGN KEY (customer_id)
    REFERENCES customers(customer_id)
    DEFERRABLE INITIALLY DEFERRED
```

Còn ý tưởng sau **không hợp lệ** trong PostgreSQL:

```sql
-- Không chạy: PostgreSQL không hỗ trợ DEFERRABLE cho CHECK.
CONSTRAINT positive_price
    CHECK (price >= 0)
    DEFERRABLE INITIALLY DEFERRED
```

Nếu một bài toán đòi hỏi “tạm để số lượng âm rồi sửa lại trước commit” nhưng bảng có `CHECK (quantity >= 0)` của PostgreSQL, `SET CONSTRAINTS ALL DEFERRED` cũng **không làm `CHECK` đó trì hoãn**.

## 4. Thực hành PostgreSQL: khóa ngoại kiểm tra tức thời

Các ví dụ từ phần này chỉ dùng cho **database thực hành** với quyền tạo bảng. Tạo mỗi bảng một lần; nếu chạy lại, nên chuẩn bị database thử nghiệm mới hoặc dọn bảng do chính bài tạo. Các đoạn **minh họa lỗi có chủ đích** được đánh dấu riêng để tránh chạy nhầm cùng các lệnh thành công.

### 4.1. Chuẩn bị hai bảng

```sql
CREATE TABLE lesson99_customers_immediate (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson99_orders_immediate (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    CONSTRAINT lesson99_orders_immediate_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson99_customers_immediate(customer_id)
        NOT DEFERRABLE
);
```

Bảng `lesson99_orders_immediate` có khóa ngoại `NOT DEFERRABLE`. Mặc định trong PostgreSQL, nếu không ghi `DEFERRABLE` thì ràng buộc cũng không được trì hoãn.

### 4.2. Thử chèn con trước cha: lỗi có chủ đích

Mở một giao dịch:

```sql
BEGIN;

-- Cố ý vi phạm: chưa có customer_id = 100.
INSERT INTO lesson99_orders_immediate (order_id, customer_id)
VALUES (1, 100);
```

PostgreSQL báo lỗi khóa ngoại, thường kèm nội dung giống:

```text
ERROR: insert or update on table "lesson99_orders_immediate"
violates foreign key constraint "lesson99_orders_immediate_customer_fk"
DETAIL: Key (customer_id)=(100) is not present in table "lesson99_customers_immediate".
```

Sau lỗi, **giao dịch PostgreSQL trở thành trạng thái lỗi**. Trong phiên đó, dùng:

```sql
ROLLBACK;
```

Không thể chỉ chèn tiếp khách hàng để “sửa” giao dịch đã lỗi mà không xử lý trạng thái giao dịch trước.

### 4.3. Thực hiện đúng thứ tự khi dùng ràng buộc tức thời

```sql
BEGIN;

INSERT INTO lesson99_customers_immediate (customer_id, customer_name)
VALUES (100, 'Khách hàng A');

INSERT INTO lesson99_orders_immediate (order_id, customer_id)
VALUES (1, 100);

COMMIT;

SELECT
    o.order_id,
    c.customer_name
FROM lesson99_orders_immediate AS o
JOIN lesson99_customers_immediate AS c
    ON c.customer_id = o.customer_id;
```

Lần này thành công vì tại thời điểm chèn đơn hàng, khách hàng đã có. Việc **sắp xếp đúng thứ tự thao tác** thường là cách đơn giản nhất để giữ toàn vẹn dữ liệu nếu không thật sự cần hoãn constraint.

## 5. Thực hành PostgreSQL: khóa ngoại có thể trì hoãn

### 5.1. Tạo constraint DEFERRABLE INITIALLY DEFERRED

```sql
CREATE TABLE lesson99_customers_deferred (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson99_orders_deferred (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    CONSTRAINT lesson99_orders_deferred_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson99_customers_deferred(customer_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Khóa ngoại `lesson99_orders_deferred_customer_fk` được phép trì hoãn, đồng thời mặc định **DEFERRED** ở đầu mỗi giao dịch.

### 5.2. Chèn con trước cha trong cùng giao dịch

```sql
BEGIN;

INSERT INTO lesson99_orders_deferred (order_id, customer_id)
VALUES (1, 200);

-- Ở đây order 1 chưa tìm thấy customer 200;
-- chỉ khóa ngoại đã hoãn cho phép tồn tại trạng thái trung gian.

INSERT INTO lesson99_customers_deferred (customer_id, customer_name)
VALUES (200, 'Khách hàng B');

COMMIT;

SELECT
    o.order_id,
    c.customer_name
FROM lesson99_orders_deferred AS o
JOIN lesson99_customers_deferred AS c
    ON c.customer_id = o.customer_id;
```

Kết quả cuối: đơn hàng `1` gắn với `Khách hàng B`. Điều kiện của khóa ngoại được thỏa trước lúc commit.

### 5.3. Nếu không sửa lỗi trước COMMIT

Đây là **ví dụ cố ý thất bại**, hãy chạy tách biệt và biết rằng PostgreSQL sẽ không commit được giao dịch:

```sql
BEGIN;

INSERT INTO lesson99_orders_deferred (order_id, customer_id)
VALUES (2, 999);

-- Cố tình không tạo khách hàng 999.
COMMIT; -- Lỗi khóa ngoại; giao dịch không được commit.
```

Ở PostgreSQL, khi `COMMIT` thất bại vì vi phạm ràng buộc đã trì hoãn, giao dịch bị hủy/rollback. Dòng đơn hàng `2` không trở thành dữ liệu đã commit. Bạn phải bắt đầu một giao dịch mới để thực hiện lại quy trình đã sửa.

Không nên kết luận “không có lỗi tại `INSERT` tức là dữ liệu hợp lệ”; với constraint được trì hoãn, lỗi có thể chỉ xuất hiện **cuối giao dịch**, nơi ứng dụng phải xử lý ngoại lệ khi `commit()`.

## 6. DEFERRABLE INITIALLY IMMEDIATE và SET CONSTRAINTS

Một ràng buộc có thể được khai báo **có quyền trì hoãn nhưng mặc định vẫn kiểm tra sớm**:

```sql
CREATE TABLE lesson99_customers_switchable (
    customer_id INTEGER PRIMARY KEY
);

CREATE TABLE lesson99_orders_switchable (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    CONSTRAINT lesson99_orders_switchable_fk
        FOREIGN KEY (customer_id)
        REFERENCES lesson99_customers_switchable(customer_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Với cấu hình này, nếu không thay đổi chế độ thì hành vi mặc định giống kiểm tra tức thời.

### 6.1. Hoãn bằng SET CONSTRAINTS trong giao dịch hiện tại

```sql
BEGIN;

SET CONSTRAINTS lesson99_orders_switchable_fk DEFERRED;

INSERT INTO lesson99_orders_switchable (order_id, customer_id)
VALUES (1, 300);

INSERT INTO lesson99_customers_switchable (customer_id)
VALUES (300);

COMMIT;
```

Khóa ngoại đã đổi sang **DEFERRED** trong giao dịch. Từ giao dịch **kế tiếp**, cấu hình `INITIALLY IMMEDIATE` lại có hiệu lực mặc định; `SET CONSTRAINTS` không thay đổi định nghĩa bảng vĩnh viễn.

Cú pháp PostgreSQL tổng quát:

```sql
SET CONSTRAINTS { ALL | constraint_name [, ...] }
{ DEFERRED | IMMEDIATE };
```

- `ALL`: thay đổi chế độ của **tất cả các ràng buộc hỗ trợ trì hoãn** trong phạm vi áp dụng.
- `constraint_name`: chọn ràng buộc cụ thể; nên đặt tên rõ ràng để dễ đọc, quản trị và kiểm tra.
- `DEFERRED`: kiểm tra ở cuối giao dịch hoặc khi bị yêu cầu kiểm tra sớm.
- `IMMEDIATE`: yêu cầu kiểm tra sớm và các thao tác tiếp theo theo chế độ tức thời.

`SET CONSTRAINTS ALL DEFERRED` **không chuyển `CHECK`, `NOT NULL` hoặc ràng buộc `NOT DEFERRABLE` thành trì hoãn**. Trong PostgreSQL, lệnh `SET CONSTRAINTS` bên ngoài giao dịch tường minh không có tác dụng thay đổi bền vững cho các câu tiếp theo.

### 6.2. Ép kiểm tra ngay trước COMMIT

`SET CONSTRAINTS ... IMMEDIATE` có thể dùng như một **điểm kiểm tra chủ động**:

```sql
BEGIN;

SET CONSTRAINTS lesson99_orders_switchable_fk DEFERRED;

INSERT INTO lesson99_orders_switchable (order_id, customer_id)
VALUES (2, 301);

INSERT INTO lesson99_customers_switchable (customer_id)
VALUES (301);

-- Kiểm tra những vi phạm đang bị trì hoãn trước khi COMMIT.
SET CONSTRAINTS lesson99_orders_switchable_fk IMMEDIATE;

COMMIT;
```

Khi chuyển từ `DEFERRED` sang `IMMEDIATE`, PostgreSQL **kiểm tra ngược lại các thay đổi đang chờ được xác minh** ngay trong câu `SET CONSTRAINTS`. Nếu còn vi phạm, câu lệnh này thất bại; trong một giao dịch thông thường của PostgreSQL, cần `ROLLBACK` hoặc xử lý qua savepoint hợp lệ trước khi tiếp tục.

Ví dụ sau **cố tình gây lỗi tại thời điểm ép kiểm tra**:

```sql
BEGIN;

SET CONSTRAINTS lesson99_orders_switchable_fk DEFERRED;

INSERT INTO lesson99_orders_switchable (order_id, customer_id)
VALUES (3, 888);

SET CONSTRAINTS lesson99_orders_switchable_fk IMMEDIATE;
-- Lỗi: chưa tồn tại customer_id = 888.
```

Sau khi quan sát thông báo lỗi, chạy riêng `ROLLBACK;`. Không dùng đoạn gây lỗi đó trong một script cần chạy liên tục đến cuối.

### 6.3. Có thể chọn tên constraint trong lệnh SET CONSTRAINTS

Trong PostgreSQL, tên constraint không bắt buộc duy nhất trên toàn database; tên cùng nhau có thể xuất hiện ở nhiều bảng. `SET CONSTRAINTS` dùng tên và quy tắc `search_path` để tìm các constraint phù hợp, có thể tác động đến nhiều constraint trùng tên trong một schema.

Khi xây dựng hệ thống lớn, nên đặt tên có ý nghĩa, ví dụ `orders_customer_id_fk` thay vì `fk1`. Có thể chỉ rõ schema khi cần và cân nhắc dùng `ALL` chỉ khi thực sự muốn thay đổi các constraint có thể trì hoãn của cả giao dịch.

## 7. Kiểm tra UNIQUE trì hoãn để hoán đổi giá trị

Một bài toán đặc trưng là **hoán đổi hai giá trị bắt buộc duy nhất**. Giả sử mỗi người có một mã ghế, mỗi ghế chỉ thuộc về một người:

| person_id | seat_code |
|---|---|
| 1 | `A01` |
| 2 | `A02` |

Yêu cầu: hoán đổi ghế giữa hai người trong một giao dịch.

### 7.1. Định nghĩa ràng buộc UNIQUE trì hoãn

```sql
CREATE TABLE lesson99_seat_assignments (
    person_id INTEGER PRIMARY KEY,
    seat_code VARCHAR(10) NOT NULL,
    CONSTRAINT lesson99_seat_code_unique
        UNIQUE (seat_code)
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO lesson99_seat_assignments (person_id, seat_code)
VALUES
    (1, 'A01'),
    (2, 'A02');
```

Khóa chính `person_id` dùng mặc định `NOT DEFERRABLE`, còn `UNIQUE (seat_code)` được phép trì hoãn.

### 7.2. Hoán đổi qua hai câu UPDATE

```sql
BEGIN;

UPDATE lesson99_seat_assignments
SET seat_code = 'A02'
WHERE person_id = 1;

-- Lúc này A02 xuất hiện hai lần trong giao dịch;
-- UNIQUE đã được trì hoãn nên chưa chặn thao tác.

UPDATE lesson99_seat_assignments
SET seat_code = 'A01'
WHERE person_id = 2;

-- Hai mã ghế lại duy nhất trước COMMIT.
COMMIT;

SELECT person_id, seat_code
FROM lesson99_seat_assignments
ORDER BY person_id;
```

Kết quả cuối:

| person_id | seat_code |
|---|---|
| 1 | `A02` |
| 2 | `A01` |

Nếu `UNIQUE (seat_code)` là **NOT DEFERRABLE**, câu cập nhật đầu có thể bị từ chối ngay vì mã `A02` đã được người thứ hai sử dụng.

Việc trì hoãn là một công cụ hữu ích, nhưng không phải cách duy nhất: bạn cũng có thể thay đổi thiết kế hoặc dùng giá trị trung gian tùy kiểu dữ liệu và nghiệp vụ. Cần lưu ý khả năng hỗ trợ và tính đúng đắn khi có nhiều giao dịch đồng thời.

### 7.3. Lưu ý với UPSERT và ON CONFLICT trong PostgreSQL

Một giới hạn quan trọng: **constraint `DEFERRABLE` không thể dùng làm bộ phân xử xung đột (conflict arbiter) của `INSERT ... ON CONFLICT` trong PostgreSQL**.

Ví dụ dạng cú pháp sau không thể dựa vào `lesson99_seat_code_unique` làm đích xử lý xung đột:

```sql
-- Không dùng cho UNIQUE DEFERRABLE làm conflict arbiter.
INSERT INTO lesson99_seat_assignments (person_id, seat_code)
VALUES (3, 'A02')
ON CONFLICT (seat_code) DO NOTHING;
```

Nếu quy trình ứng dụng cần `ON CONFLICT` trên một tập cột, hãy cân nhắc ràng buộc/unique index phù hợp với yêu cầu `ON CONFLICT` hoặc thiết kế lại thao tác. Không quyết định mọi khóa duy nhất đều `DEFERRABLE` chỉ vì muốn linh hoạt.

## 8. Ràng buộc CHECK và NOT NULL trong PostgreSQL vẫn là tức thời

Xét bảng sản phẩm với giá không âm:

```sql
CREATE TABLE lesson99_products (
    product_id INTEGER PRIMARY KEY,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT lesson99_price_nonnegative
        CHECK (price >= 0)
);

INSERT INTO lesson99_products (product_id, price)
VALUES (1, 100000.00);
```

Nếu thử:

```sql
BEGIN;

SET CONSTRAINTS ALL DEFERRED;

UPDATE lesson99_products
SET price = -100.00
WHERE product_id = 1;
-- PostgreSQL báo lỗi ngay tại UPDATE, dù đã SET CONSTRAINTS ALL DEFERRED.
```

Khi lỗi xảy ra, dùng `ROLLBACK;`. Không thể “đợi đến câu `UPDATE` sau sửa lại giá” vì PostgreSQL **không cho hoãn `CHECK`**.

Tương tự, cột `price` có `NOT NULL` không được tạm nhận `NULL` rồi bổ sung giá trị sau trước commit. Hai loại ràng buộc này không có cú pháp `DEFERRABLE` hợp lệ trong PostgreSQL.

### 8.1. CHECK và logic ba giá trị

Trong SQL, điều kiện `CHECK (price >= 0)` có thể được xem là thỏa nếu biểu thức là **TRUE hoặc UNKNOWN**. Nếu `price` là `NULL`, phép so sánh `NULL >= 0` là `UNKNOWN`, nên chỉ `CHECK` có thể không cấm giá trị thiếu. Vì vậy ví dụ đã dùng thêm:

```sql
price NUMERIC(12, 2) NOT NULL,
CONSTRAINT lesson99_price_nonnegative CHECK (price >= 0)
```

`CHECK` kiểm tra miền giá trị hợp lệ còn `NOT NULL` cấm không có giá trị; hai ràng buộc bổ sung cho nhau.

### 8.2. Thay đổi logic nghiệp vụ có làm CHECK trở nên trì hoãn được không?

Không. Nếu bài toán thật sự yêu cầu cho phép trạng thái trung gian vượt qua ngưỡng, cần **thiết kế lại quy trình hoặc dữ liệu** (chẳng hạn bảng staging, cột trạng thái nghiệp vụ, phép cập nhật nguyên tử, hoặc cơ chế xác minh ở mức nghiệp vụ) thay vì giả định rằng `SET CONSTRAINTS` có thể hoãn mọi điều kiện.

Việc vô hiệu hóa constraint để vượt lỗi là một lựa chọn khác về an toàn dữ liệu, **không tương đương** trì hoãn constraint trong một giao dịch.

## 9. FOREIGN KEY: NO ACTION khác RESTRICT

Hai hành động tham chiếu thường gây nhầm lẫn:

- `NO ACTION`: về nguyên tắc, yêu cầu trạng thái tham chiếu hợp lệ **khi ràng buộc được kiểm tra**. Nếu constraint được phép hoãn, có thể sửa trạng thái vi phạm trước thời điểm kiểm tra.
- `RESTRICT`: từ chối ngay hành động xóa/cập nhật khóa cha nếu vẫn có hàng con tham chiếu. Trong PostgreSQL, việc kiểm tra hành động `RESTRICT` **không thể hoãn** theo cách của `NO ACTION`.

Ví dụ định nghĩa khóa ngoại PostgreSQL với `NO ACTION`:

```sql
CREATE TABLE lesson99_parent_no_action (
    parent_id INTEGER PRIMARY KEY
);

CREATE TABLE lesson99_child_no_action (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL,
    CONSTRAINT lesson99_child_no_action_fk
        FOREIGN KEY (parent_id)
        REFERENCES lesson99_parent_no_action(parent_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO lesson99_parent_no_action (parent_id)
VALUES (10);

INSERT INTO lesson99_child_no_action (child_id, parent_id)
VALUES (1, 10);
```

Bạn có thể thực hiện chuỗi thao tác sau trên cùng một giao dịch:

```sql
BEGIN;

DELETE FROM lesson99_parent_no_action
WHERE parent_id = 10;

-- Trong giao dịch, child 1 đang tham chiếu đến parent 10 đã bị xóa.

INSERT INTO lesson99_parent_no_action (parent_id)
VALUES (10);

-- Quan hệ được khôi phục trước COMMIT.
COMMIT;
```

Với `ON DELETE RESTRICT`, thao tác `DELETE` đầu thường bị ngăn ngay trong PostgreSQL dù constraint được khai báo `DEFERRABLE`, vì `RESTRICT` yêu cầu kiểm tra khi xóa cha.

Các hành động như `CASCADE`, `SET NULL` và `SET DEFAULT` cũng có **hiệu ứng cập nhật dữ liệu** khi câu lệnh gây ra hành động diễn ra; không coi các hiệu ứng đó là “mọi thứ đợi đến `COMMIT`”. Khả năng hoãn **kiểm tra toàn vẹn** và thời điểm thực hiện **hành động tham chiếu** là hai khía cạnh cần đọc riêng trong tài liệu DBMS.

## 10. Trường hợp tham chiếu vòng giữa hai bảng

Đôi khi hai bảng tham chiếu lẫn nhau. Ví dụ một bảng `departments` có `lead_employee_id` và bảng `employees` có `department_id`:

- Mỗi nhân viên thuộc một phòng.
- Mỗi phòng có một nhân viên trưởng phòng.
- Dữ liệu ban đầu chưa có dòng ở bảng nào.

Nếu cả hai khóa ngoại đều bắt buộc và kiểm tra ngay, bạn có thể gặp tình huống không thể chèn dòng đầu tiên mà không vi phạm một trong hai khóa ngoại.

Trong PostgreSQL, có thể tạo hai bảng với khóa ngoại có quyền trì hoãn. Dưới đây là ví dụ tối giản:

```sql
CREATE TABLE lesson99_departments_cycle (
    department_id INTEGER PRIMARY KEY,
    lead_employee_id INTEGER NOT NULL
);

CREATE TABLE lesson99_employees_cycle (
    employee_id INTEGER PRIMARY KEY,
    department_id INTEGER NOT NULL,
    CONSTRAINT lesson99_employee_department_fk
        FOREIGN KEY (department_id)
        REFERENCES lesson99_departments_cycle(department_id)
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE lesson99_departments_cycle
    ADD CONSTRAINT lesson99_department_lead_fk
    FOREIGN KEY (lead_employee_id)
    REFERENCES lesson99_employees_cycle(employee_id)
    DEFERRABLE INITIALLY DEFERRED;
```

Hai bảng đều có khóa ngoại nhưng vì tạo bảng `departments` trước rồi dùng `ALTER TABLE` để thêm khóa ngoại quay lại bảng `employees`, ta tránh vấn đề tham chiếu đến bảng chưa tồn tại tại thời điểm định nghĩa.

Bây giờ chèn hai dòng trong **một giao dịch**:

```sql
BEGIN;

INSERT INTO lesson99_departments_cycle (
    department_id, lead_employee_id
)
VALUES (1, 10);

INSERT INTO lesson99_employees_cycle (
    employee_id, department_id
)
VALUES (10, 1);

COMMIT;
```

Cả hai tham chiếu đều hợp lệ tại lúc commit. Đây là ví dụ điển hình mà việc trì hoãn có thể cần thiết.

Tuy nhiên, **tham chiếu vòng cũng là tín hiệu nên xem lại thiết kế dữ liệu**: có thật sự cần hai quan hệ bắt buộc ở cả hai phía không? Có thể thêm trưởng phòng sau khi tạo phòng, dùng cột nullable tạm thời theo quy trình, hoặc tách quan hệ phân công thành bảng riêng. Ràng buộc trì hoãn hỗ trợ một thiết kế phù hợp, nhưng không thay thế công việc thiết kế mô hình dữ liệu.

## 11. SET CONSTRAINTS hoạt động trong phạm vi nào?

### 11.1. Chỉ trong giao dịch hiện tại

Trong PostgreSQL:

```sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
-- Các thao tác SQL trong giao dịch...
COMMIT;
```

Ở giao dịch kế tiếp, mỗi constraint lại khởi đầu theo thuộc tính `INITIALLY IMMEDIATE` hoặc `INITIALLY DEFERRED` đã khai báo. `SET CONSTRAINTS` **không sửa metadata vĩnh viễn**.

Khi chạy lệnh `SET CONSTRAINTS` ngoài một giao dịch tường minh, PostgreSQL cảnh báo và không giúp các câu SQL tiếp theo giữ chế độ hoãn. Đối với ví dụ cần chèn con trước cha, phải bao chúng trong cùng `BEGIN ... COMMIT`.

### 11.2. Chỉ những constraint được phép hoãn mới thay đổi

`SET CONSTRAINTS ALL DEFERRED` không có nghĩa là tất cả ràng buộc của database tạm bị vô hiệu hóa. Chỉ các constraint được khai báo **DEFERRABLE** và thuộc nhóm hỗ trợ mới chuyển chế độ.

### 11.3. COMMIT có thể trở thành điểm phát sinh lỗi

Trong ứng dụng có nhiều bước ghi dữ liệu, lỗi ràng buộc trì hoãn có thể xuất hiện tại `COMMIT`, **không nằm ở câu `INSERT` hoặc `UPDATE` gây vi phạm ban đầu**.

Với JDBC trong Java, đó có thể là ngoại lệ tại `Connection.commit()`:

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        // Thực hiện các INSERT/UPDATE trên cùng một connection.
        // Các constraint DEFERRABLE có thể chưa được xác minh đầy đủ.

        conn.commit(); // Vẫn có thể ném SQLException ở đây.
    } catch (SQLException error) {
        conn.rollback();
        throw error;
    }
}
```

Đây là **mẫu rút gọn**: ứng dụng thực tế phải xử lý cả lỗi khi rollback/đóng connection, và transaction manager có thể quản lý commit thay cho code thủ công. Điểm cần nhớ là **thành công của các câu ghi không bảo đảm commit thành công** nếu constraint đang trì hoãn.

### 11.4. Không làm thay đổi quy tắc cô lập giữa các giao dịch

Việc hoãn constraint **không có nghĩa những giao dịch khác được phép nhìn thấy dữ liệu chưa commit**. Quy tắc cô lập giao dịch vẫn áp dụng.

Mặt khác, các giao dịch đồng thời có thể tranh chấp khóa hoặc chờ nhau khi kiểm tra khóa ngoại, khóa duy nhất. Hoãn kiểm tra có thể đẩy một số xung đột đến cuối giao dịch; nó **không loại bỏ deadlock, race condition hoặc chi phí xác minh toàn vẹn**. Giữ giao dịch ngắn gọn, thiết kế thứ tự thao tác hợp lý và xử lý lỗi commit.

## 12. Xem thông tin ràng buộc trong PostgreSQL

Để kiểm tra các constraint đã khai báo cho bảng `lesson99_orders_switchable`, truy vấn catalog của PostgreSQL:

```sql
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    condeferrable AS is_deferrable,
    condeferred AS initially_deferred,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'lesson99_orders_switchable'::regclass
ORDER BY conname;
```

Trong kết quả:

- `conname`: tên constraint.
- `contype`: ký hiệu loại constraint, chẳng hạn `p` (primary key), `u` (unique), `f` (foreign key), `c` (check), `x` (exclusion).
- `condeferrable`: có khả năng trì hoãn hay không.
- `condeferred`: **khởi đầu** theo chế độ trì hoãn hay không.
- `pg_get_constraintdef(oid)`: biểu diễn lại định nghĩa constraint theo cú pháp PostgreSQL.

**Lưu ý:** `condeferred` là **thuộc tính khởi đầu được khai báo** trong catalog, không phải công cụ đọc trực tiếp mọi thay đổi chế độ `SET CONSTRAINTS` đang có trong giao dịch hiện tại.

Khi chạy trong `psql`, bạn cũng có thể dùng lệnh mô tả bảng:

```text
\d lesson99_orders_switchable
```

`\d` là lệnh của **client `psql`**, không phải cú pháp SQL chuẩn để đưa qua JDBC.

## 13. Khác biệt giữa các hệ quản trị

Cùng là “khóa ngoại” hoặc “ràng buộc duy nhất” nhưng khả năng trì hoãn khác đáng kể.

| Hệ quản trị | Trì hoãn FK? | Trì hoãn UNIQUE/PK? | Cơ chế điển hình |
|---|---|---|---|
| **PostgreSQL** | Có, khi khai báo `DEFERRABLE` | Có, khi khai báo `DEFERRABLE` | `DEFERRABLE INITIALLY ...`, `SET CONSTRAINTS` |
| **Oracle Database** | Có với constraint khai báo `DEFERRABLE` | Có với constraint khai báo `DEFERRABLE` | `DEFERRABLE INITIALLY ...` và `SET CONSTRAINT(S)` |
| **SQLite** | Có, tùy khai báo FK hoặc thiết lập theo giao dịch | `UNIQUE`/`PRIMARY KEY` thông thường không có chế độ trì hoãn tương tự | `DEFERRABLE INITIALLY DEFERRED` cho FK; `PRAGMA defer_foreign_keys` |
| **MySQL/MariaDB** | Không có cơ chế deferred FK tương đương | Không có chế độ trì hoãn UNIQUE/PK kiểu PostgreSQL | Kiểm tra trong lúc thực thi thay đổi; thiết kế thứ tự thao tác |
| **SQL Server** | Không có cú pháp `DEFERRABLE ... INITIALLY DEFERRED` như PostgreSQL | Không có chế độ trì hoãn UNIQUE/PK tương đương | Kiểm tra theo thực thi câu lệnh và tính chất constraint của T-SQL |

Bảng là so sánh **khả năng trì hoãn thường dùng**, không liệt kê mọi trường hợp nội bộ của engine. Trong một hệ quản trị, còn phải xét loại constraint, hành động tham chiếu, trạng thái constraint và phiên bản sản phẩm.

### 13.1. Oracle Database

Oracle hỗ trợ khái niệm **DEFERRABLE** và trạng thái khởi đầu **INITIALLY IMMEDIATE/INITIALLY DEFERRED**, cho phép kiểm tra các constraint được khai báo phù hợp ở cuối giao dịch.

Ví dụ khai báo khóa ngoại theo phong cách Oracle:

```sql
CREATE TABLE lesson99_ora_parent (
    parent_id NUMBER PRIMARY KEY
);

CREATE TABLE lesson99_ora_child (
    child_id NUMBER PRIMARY KEY,
    parent_id NUMBER,
    CONSTRAINT lesson99_ora_child_fk
        FOREIGN KEY (parent_id)
        REFERENCES lesson99_ora_parent(parent_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Có thể thay đổi chế độ constraint được phép trì hoãn trong giao dịch bằng cú pháp `SET CONSTRAINTS` tương ứng. Oracle cũng có các trạng thái `ENABLE/DISABLE` và `VALIDATE/NOVALIDATE` liên quan tới enforcement/validation, **khác mục đích** với kiểm tra tức thời hay trì hoãn.

Một khác biệt đáng nhớ: nhiều lệnh DDL của Oracle như `CREATE TABLE` có hành vi **implicit commit**. Vì vậy đừng lấy các ví dụ PostgreSQL vừa `CREATE TABLE` vừa `ROLLBACK` và cho rằng DDL sẽ được rollback tương tự trong Oracle.

### 13.2. SQLite: deferred FK cần bật foreign key enforcement

SQLite hỗ trợ **foreign key trì hoãn**, nhưng cần lưu ý một số điều quan trọng:

1. Bật kiểm tra khóa ngoại cho **kết nối đang dùng** bằng `PRAGMA foreign_keys = ON;`, đặt **ngoài giao dịch**. Không dựa vào cấu hình mặc định của môi trường.
2. Trong `CREATE TABLE`, khóa ngoại `DEFERRABLE INITIALLY DEFERRED` được phép vi phạm tạm thời cho tới `COMMIT` khi có giao dịch tường minh.
3. SQLite không có `SET CONSTRAINTS ... DEFERRED/IMMEDIATE` tương đương PostgreSQL để tùy ý đổi một FK riêng lẻ trong transaction.
4. `PRAGMA defer_foreign_keys = ON;` có thể hoãn kiểm tra khóa ngoại cho **toàn bộ giao dịch**; thiết lập này được reset sau `COMMIT` hoặc `ROLLBACK`.
5. Hành động `RESTRICT` có thể gây lỗi ngay khi sửa/xóa khóa cha dù FK được khai báo trì hoãn.

Ví dụ SQLite:

```sql
-- Chạy trước khi BEGIN; việc bật/tắt foreign_keys trong transaction
-- không có tác dụng thay đổi chế độ enforcement.
PRAGMA foreign_keys = ON;

CREATE TABLE lesson99_sqlite_parent (
    parent_id INTEGER PRIMARY KEY
);

CREATE TABLE lesson99_sqlite_child (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL,
    FOREIGN KEY (parent_id)
        REFERENCES lesson99_sqlite_parent(parent_id)
        DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

INSERT INTO lesson99_sqlite_child (child_id, parent_id)
VALUES (1, 500);

INSERT INTO lesson99_sqlite_parent (parent_id)
VALUES (500);

COMMIT;
```

Một khác biệt quan trọng về lỗi: khi `COMMIT` của SQLite thất bại do FK trì hoãn vẫn vi phạm, **giao dịch có thể còn mở** để bạn sửa dữ liệu rồi thử `COMMIT` lại. Trong PostgreSQL, một `COMMIT` thất bại vì ràng buộc thường khiến giao dịch bị hủy. Không viết code xử lý lỗi transaction chung cho mọi DBMS mà không kiểm tra quy tắc này.

**Đừng nhầm `BEGIN DEFERRED` của SQLite với deferred constraint.** `BEGIN DEFERRED` nói về **thời điểm bắt đầu giao dịch đọc/ghi và khóa**, không tự làm tất cả constraint trở thành trì hoãn.

### 13.3. MySQL/MariaDB: không có deferred FK theo giao dịch kiểu PostgreSQL

Trong MySQL/MariaDB, khóa ngoại thông thường phải được thỏa tại thời điểm xử lý thay đổi. Một lệnh chèn hàng con tham chiếu cha chưa có sẽ bị lỗi; không có cú pháp `SET CONSTRAINTS ... DEFERRED` để cho phép chèn cha sau trong cùng giao dịch như ví dụ PostgreSQL.

Đôi khi gặp:

```sql
-- MySQL: đây là cơ chế bật/tắt kiểm tra khóa ngoại,
-- KHÔNG phải deferred constraint.
SET FOREIGN_KEY_CHECKS = 0;
```

Lệnh này **vô hiệu hóa kiểm tra khóa ngoại trong phạm vi thiết lập**, không phải “hoãn đến commit rồi đảm bảo dữ liệu hợp lệ”. Khi bật lại `FOREIGN_KEY_CHECKS`, MySQL không tự rà soát đầy đủ các hàng đã chèn trong lúc tắt. Vì vậy, không dùng nó làm cách thay thế thường xuyên cho deferred constraints.

Khi import dữ liệu, nên lên thứ tự chèn bảng cha trước bảng con; nếu thực sự phải tắt kiểm tra trong một quy trình có kiểm soát, cần quy trình xác minh và khôi phục dữ liệu rõ ràng.

### 13.4. SQL Server: không có DEFERRABLE tương đương

SQL Server có ràng buộc `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` và `CHECK`, nhưng không hỗ trợ cơ chế `DEFERRABLE INITIALLY DEFERRED` cho FK/unique như PostgreSQL.

Trong T-SQL, có thể dùng `NOCHECK` để **tắt kiểm tra** một constraint trong tình huống quản trị dữ liệu. Tuy nhiên, trạng thái disabled hoặc untrusted constraint **không phải** deferred constraint tự kiểm tra ở `COMMIT`. Sử dụng `NOCHECK` có thể tạo vấn đề dữ liệu không hợp lệ và ảnh hưởng khả năng tối ưu của engine.

Để cập nhật nhiều hàng cần đổi khóa/tính duy nhất, thường phải thiết kế thứ tự thao tác, chiến lược giá trị tạm phù hợp hoặc thay đổi mô hình xử lý, thay vì trông chờ vào `SET CONSTRAINTS`.

## 14. Trì hoãn constraint không phải vô hiệu hóa constraint

Ba hành động thường bị lẫn lộn:

| Hành động | Ràng buộc có còn hiệu lực không? | Khi nào phát hiện vi phạm? | Rủi ro |
|---|---|---|---|
| **Immediate** | Có | Trong/ở cuối câu SQL, tùy loại | Chặn sớm thao tác có trạng thái trung gian vi phạm |
| **Deferred** | Có | Cuối giao dịch hoặc khi bị ép kiểm tra | Lỗi có thể xuất hiện lúc `COMMIT` và làm hủy công việc |
| **Disabled / bỏ qua kiểm tra** | Không được thực thi bình thường trong khoảng bị tắt | Có thể không được phát hiện tự động | Dữ liệu không hợp lệ có thể tồn tại cả sau khi quy trình kết thúc |

Không dùng các cờ “disable FK” hay “disable constraint” như một cách mặc định để xử lý thứ tự nhập dữ liệu. Deferred constraint là một lựa chọn **có kiểm soát**: nó yêu cầu tất cả quy tắc toàn vẹn phải đúng tại điểm xác nhận giao dịch.

## 15. Khi nào nên chọn kiểm tra tức thời, khi nào cần trì hoãn?

### Ưu tiên tức thời khi

- Các câu `INSERT`/`UPDATE` có thể sắp xếp dễ dàng theo quan hệ khóa.
- Bạn muốn phát hiện lỗi gần vị trí mã gây ra lỗi.
- Một thao tác không cần chấp nhận trạng thái trung gian tạm vi phạm.
- Hệ quản trị không hỗ trợ hoãn loại constraint đó.

### Cân nhắc trì hoãn khi

- Phải chèn dữ liệu có tham chiếu vòng theo một giao dịch.
- Cần hoán đổi các giá trị `UNIQUE` qua nhiều bước mà trạng thái cuối hợp lệ.
- Quá trình import/đồng bộ dữ liệu tạo trạng thái trung gian không hợp lệ nhưng có thể hoàn thiện trước commit.
- Quy trình cần một điểm `SET CONSTRAINTS ... IMMEDIATE` để chủ động kiểm tra sau nhiều bước trước khi xác nhận.

Ngay cả khi có thể trì hoãn, hãy cân nhắc **khả năng bảo trì** và **chi phí kiểm tra cuối giao dịch**. Giao dịch kéo dài có thể giữ khóa lâu hơn, tạo khó khăn khi lỗi chỉ xuất hiện sau hàng nghìn thao tác. Đừng coi trì hoãn là giải pháp cho mọi vấn đề thiết kế thứ tự dữ liệu.

## 16. Những lỗi thường gặp

### Lỗi 1: Hiểu DEFERRABLE là tự động DEFERRED

```sql
-- Mặc định ban đầu vẫn là IMMEDIATE.
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
DEFERRABLE
```

Nếu muốn hoãn mặc định, khai báo `DEFERRABLE INITIALLY DEFERRED`. Nếu chỉ muốn hoãn trong một giao dịch cụ thể, dùng `DEFERRABLE INITIALLY IMMEDIATE` và `SET CONSTRAINTS ... DEFERRED` trong transaction.

### Lỗi 2: Nghĩ SET CONSTRAINTS ALL DEFERRED hoãn cả CHECK và NOT NULL

Trong PostgreSQL, `CHECK` và `NOT NULL` vẫn tức thời. Đặt `SET CONSTRAINTS ALL DEFERRED` không làm câu `UPDATE price = -10` vượt qua `CHECK (price >= 0)`.

### Lỗi 3: Không mở transaction tường minh

Nếu client chạy từng câu ở auto-commit và bạn chèn con trước cha, giao dịch có thể được commit ngay sau câu `INSERT` đầu. Deferred constraint sẽ được kiểm tra ở điểm commit đó và báo lỗi. Phải giữ các bước liên quan trong **cùng một giao dịch**.

### Lỗi 4: Không xử lý lỗi tại COMMIT

Ứng dụng chỉ bắt lỗi quanh `INSERT` mà quên `COMMIT` có thể bỏ sót điểm constraint trì hoãn phát hiện vi phạm. Cần thiết kế xử lý ngoại lệ và rollback theo hành vi DBMS/driver.

### Lỗi 5: Dùng ON DELETE RESTRICT rồi mong SET CONSTRAINTS hoãn được

Với PostgreSQL, `RESTRICT` là hành động chặn ngay và không thể trì hoãn như `NO ACTION`. Phân biệt **hành động tham chiếu** với **khả năng trì hoãn của phép kiểm tra**.

### Lỗi 6: Xem bật/tắt constraint là cùng ý nghĩa với deferred

`SET FOREIGN_KEY_CHECKS = 0` của MySQL hoặc `NOCHECK` của SQL Server không tương đương deferred constraint: không bảo đảm cuối giao dịch sẽ được xác minh như `DEFERRABLE` của PostgreSQL.

### Lỗi 7: Đổi thứ tự giao dịch nhưng quên phụ thuộc khóa

Ngay cả khi một FK được hoãn, các ràng buộc khác như `NOT NULL`, `CHECK` hoặc unique không trì hoãn vẫn có thể làm câu lệnh thất bại. Cần xét **toàn bộ các constraint liên quan**, không chỉ ràng buộc vừa khai báo.

## 17. Bài tập thực hành có lời giải

### Bài 1. Phân biệt DEFERRABLE và INITIALLY

Cho constraint:

```sql
CONSTRAINT lesson99_fk
    FOREIGN KEY (parent_id)
    REFERENCES parent_table(parent_id)
    DEFERRABLE INITIALLY IMMEDIATE
```

Câu hỏi:

1. Có thể đổi sang `DEFERRED` trong một giao dịch không?
2. Nếu không chạy `SET CONSTRAINTS`, khi nào constraint được kiểm tra?
3. Sau khi một giao dịch chuyển sang `DEFERRED` và commit, giao dịch mới bắt đầu ở chế độ nào?

**Đáp án:** (1) Có. (2) Mặc định tức thời. (3) Giao dịch mới lại khởi đầu ở `IMMEDIATE` theo khai báo.

### Bài 2. Dự đoán kết quả một giao dịch

Bảng `lesson99_orders_deferred` có FK `DEFERRABLE INITIALLY DEFERRED` đến `lesson99_customers_deferred`. Giả sử cả hai bảng đang rỗng; chạy:

```sql
BEGIN;

INSERT INTO lesson99_orders_deferred (order_id, customer_id)
VALUES (10, 777);

INSERT INTO lesson99_customers_deferred (customer_id, customer_name)
VALUES (777, 'Khách hàng C');

COMMIT;
```

**Đáp án:** Giao dịch có thể commit thành công vì tại thời điểm kiểm tra cuối cùng, khách hàng `777` đã tồn tại. Nếu bỏ câu chèn khách hàng, `COMMIT` sẽ thất bại.

### Bài 3. Nhận biết giới hạn PostgreSQL

Trong PostgreSQL, ràng buộc nào sau đây **không thể** khai báo `DEFERRABLE`?

- A. `FOREIGN KEY`
- B. `UNIQUE`
- C. `CHECK`
- D. `EXCLUDE`

**Đáp án:** C. `CHECK` không hỗ trợ chế độ trì hoãn trong PostgreSQL. `NOT NULL` cũng không hỗ trợ.

### Bài 4. Sửa lỗi khi hoán đổi ghế

Bạn cần hoán đổi hai mã ghế theo hai câu `UPDATE`. Mỗi ghế phải duy nhất. Lựa chọn nào phù hợp trong PostgreSQL nếu muốn thực hiện bằng hai bước trong cùng một transaction?

**Đáp án gợi ý:** khai báo constraint `UNIQUE (seat_code) DEFERRABLE INITIALLY DEFERRED`, sau đó chạy hai câu `UPDATE` trong một `BEGIN ... COMMIT` như phần 7. Nếu constraint đang `INITIALLY IMMEDIATE` nhưng được khai báo `DEFERRABLE`, có thể chuyển sang `DEFERRED` trước khi cập nhật.

### Bài 5. Đọc lỗi từ SET CONSTRAINTS IMMEDIATE

```sql
BEGIN;

SET CONSTRAINTS lesson99_orders_switchable_fk DEFERRED;

INSERT INTO lesson99_orders_switchable (order_id, customer_id)
VALUES (20, 9999);

SET CONSTRAINTS lesson99_orders_switchable_fk IMMEDIATE;
```

Giả sử không có khách hàng `9999`. **Lỗi xảy ra ở đâu?**

**Đáp án:** Câu `INSERT` có thể chạy được do constraint đang trì hoãn; lỗi xuất hiện tại `SET CONSTRAINTS ... IMMEDIATE` vì PostgreSQL kiểm tra ngay những thay đổi đang chờ. Khi thử, dùng `ROLLBACK;` sau lỗi.

### Bài 6. So sánh các DBMS

Hãy phân loại phát biểu sau là đúng hay sai:

1. SQLite cần xác định cấu hình thực thi FK của kết nối trước khi dựa vào ràng buộc đó.
2. MySQL `FOREIGN_KEY_CHECKS = 0` tương đương `DEFERRABLE INITIALLY DEFERRED`.
3. `BEGIN DEFERRED` của SQLite chắc chắn làm mọi FK trở thành trì hoãn.
4. PostgreSQL có thể trì hoãn `PRIMARY KEY` được khai báo `DEFERRABLE`.
5. SQL Server hỗ trợ nguyên văn `SET CONSTRAINTS ALL DEFERRED` như PostgreSQL.

**Đáp án:** (1) Đúng; (2) Sai; (3) Sai; (4) Đúng; (5) Sai.

### Bài 7. Chọn giải pháp cho tình huống thực tế

Một hệ thống nhập dữ liệu nhân sự có hai bảng: `departments` cần người trưởng phòng tồn tại trong `employees`, còn `employees` cần phòng ban tồn tại trong `departments`. Ứng dụng phải tạo một phòng mới và nhân viên trưởng phòng trong **một transaction**.

**Gợi ý:** Xem lại thiết kế quan hệ bắt buộc. Nếu vòng tham chiếu là nhu cầu thật và DBMS hỗ trợ, có thể dùng các FK `DEFERRABLE INITIALLY DEFERRED` để chèn hai bản ghi rồi commit khi trạng thái cuối hợp lệ. Nếu DBMS không hỗ trợ, cần thay đổi mô hình hoặc quy trình nhập để mỗi bước hợp lệ, chẳng hạn dùng bước gán trưởng phòng sau khi tạo dữ liệu nền với một quan hệ nullable đã được thiết kế rõ ràng.

## 18. Tổng kết

- **IMMEDIATE** kiểm tra ràng buộc tại điểm thực thi câu lệnh theo quy tắc DBMS; **DEFERRED** cho phép kiểm tra muộn hơn, thường ở `COMMIT`.
- **`DEFERRABLE` là khả năng được phép hoãn**, còn **`INITIALLY IMMEDIATE/DEFERRED` là trạng thái bắt đầu giao dịch**.
- Trong **PostgreSQL**, `FOREIGN KEY`, `UNIQUE`, `PRIMARY KEY` và `EXCLUDE` có thể trì hoãn; `CHECK` và `NOT NULL` thì không.
- **`SET CONSTRAINTS`** đổi thời điểm kiểm tra trong giao dịch hiện tại; chuyển sang `IMMEDIATE` còn có thể ép kiểm tra những vi phạm đang được hoãn.
- **Hoãn không phải bỏ qua:** vi phạm cuối giao dịch vẫn làm `COMMIT` thất bại.
- **Các DBMS khác nhau:** Oracle có hỗ trợ constraint deferrable; SQLite hỗ trợ deferred FK với lưu ý `PRAGMA foreign_keys`; MySQL/MariaDB và SQL Server không có cơ chế deferred FK/unique tương đương PostgreSQL.
- **Bật/tắt kiểm tra constraint** không phải cách thay thế an toàn cho trì hoãn; cần hiểu tác động tới tính toàn vẹn dữ liệu.
- Khi ứng dụng dùng deferred constraints, phải **bắt và xử lý lỗi tại `COMMIT`**, đồng thời kiểm tra phạm vi giao dịch và các constraint còn lại.

Khi thấy một quy trình “chèn trước dữ liệu liên quan rồi bổ sung sau”, hãy hỏi ba điều: **DBMS có hỗ trợ trì hoãn loại constraint này không; ràng buộc đã được khai báo `DEFERRABLE` chưa; và tất cả các bước có nằm trong cùng một giao dịch để trạng thái cuối hợp lệ trước `COMMIT` hay không?** Trả lời được ba câu đó giúp bạn lựa chọn giải pháp đúng, thay vì vô hiệu hóa cơ chế bảo vệ dữ liệu.

## Tài liệu tham khảo

- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): chế độ `IMMEDIATE`/`DEFERRED`, cách thay đổi và thời điểm kiểm tra.
- [PostgreSQL — CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): các loại constraint hỗ trợ `DEFERRABLE` và giới hạn `ON CONFLICT`.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): khóa ngoại, `NO ACTION`, `RESTRICT` và các hành động tham chiếu.
- [SQLite — Foreign Key Support](https://www.sqlite.org/foreignkeys.html): foreign key immediate/deferred, `RESTRICT` và cách xử lý `COMMIT`.
- [SQLite — PRAGMA statements](https://www.sqlite.org/pragma.html): `foreign_keys` và `defer_foreign_keys`.
- [Oracle Database — Constraint Syntax](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): các thuộc tính `DEFERRABLE`, `INITIALLY` và trạng thái constraint.

