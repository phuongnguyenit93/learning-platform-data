# Trạng thái giao dịch lỗi và yêu cầu rollback

Khi làm việc với PostgreSQL, một lỗi SQL trong giao dịch tường minh thường có hệ quả lớn hơn việc riêng câu lệnh ấy thất bại. Chẳng hạn, trong `BEGIN ... COMMIT`, nếu `INSERT` vi phạm khóa duy nhất, câu lệnh bị lỗi và **toàn bộ giao dịch chuyển sang trạng thái thất bại** (*failed/aborted transaction*). Từ thời điểm đó, bạn không thể tiếp tục dùng các câu `SELECT`, `UPDATE` hay `INSERT` thông thường như chưa có chuyện gì xảy ra. PostgreSQL thường trả:

```text
ERROR:  current transaction is aborted, commands ignored
        until end of transaction block
SQLSTATE: 25P02
```

Mã `25P02` thường là **hậu quả** của lỗi đầu tiên, không phải nguyên nhân gốc. Để kết thúc trạng thái lỗi, ứng dụng phải **rollback giao dịch**, hoặc **rollback về một savepoint hợp lệ đã tồn tại trước lỗi** nếu nghiệp vụ cho phép tiếp tục phần còn lại.

Bài học này giải thích:

- Giao dịch PostgreSQL chuyển từ trạng thái bình thường sang trạng thái lỗi như thế nào.
- Phân biệt **lỗi gốc** như `23505`, `23503`, `22P02` với lỗi kéo theo `25P02`.
- Vì sao `ROLLBACK` thường là thao tác cần thực hiện, và `COMMIT` sau giao dịch thất bại có thể thực chất kết thúc bằng rollback.
- Khi nào dùng **`SAVEPOINT`**, `ROLLBACK TO SAVEPOINT` và `RELEASE SAVEPOINT`.
- Vì sao cách xử lý lỗi khác nhau giữa `psql` autocommit, giao dịch tường minh, JDBC và framework Spring.
- Cách retry **toàn bộ giao dịch** cho những lỗi có thể thử lại, thay vì cố chạy tiếp một giao dịch đã lỗi.
- Cách chẩn đoán qua SQLSTATE, log, `pg_stat_activity` và trạng thái kết nối.

> **An toàn thực hành:** Chỉ dùng database lab. Các câu SQL bên dưới chủ động tạo lỗi rồi rollback để quan sát. Không thực thi trên dữ liệu production hoặc dùng connection đang phục vụ request thật. Trong ứng dụng Java, luôn tuân theo transaction manager đang sở hữu connection; không tự ý phát lệnh `BEGIN`/`ROLLBACK` nếu framework quản lý giao dịch cho bạn.

## 1. Giao dịch là đơn vị thành công hoặc thất bại

Một giao dịch (transaction) giúp nhiều thao tác được xem là một đơn vị:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Đây là **mẫu minh họa**, không phải script chạy được trong lab nếu chưa tạo bảng `accounts`. Khi cả hai thao tác hợp lệ, `COMMIT` kết thúc giao dịch và công bố kết quả. Nếu xảy ra lỗi trong quá trình xử lý, không nên chỉ coi câu lệnh cuối cùng là vấn đề: **toàn bộ nghiệp vụ chuyển tiền phải được quyết định là commit hay rollback**.

Các tính chất ACID liên quan trực tiếp:

| Tính chất | Liên hệ với trạng thái giao dịch lỗi |
|---|---|
| **Atomicity** | Hoặc toàn bộ thay đổi của transaction được commit, hoặc các thay đổi chưa commit bị hủy. |
| **Consistency** | Ràng buộc dữ liệu được kiểm tra theo cơ chế PostgreSQL; giao dịch lỗi không được tiếp tục commit tùy tiện. |
| **Isolation** | Transaction nhìn thấy snapshot và tương tác đồng thời theo mức cô lập được cấu hình. |
| **Durability** | Sau commit thành công, PostgreSQL bảo đảm độ bền theo các cấu hình và giả định vận hành tương ứng. |

**`ROLLBACK` không phải “xóa một lỗi khỏi màn hình”**. Nó chấm dứt giao dịch hiện hành, hủy những thay đổi chưa được commit của giao dịch đó, rồi đưa session trở lại trạng thái sẵn sàng bắt đầu giao dịch mới.

## 2. Chuẩn bị schema và dữ liệu mẫu

Để mô phỏng lỗi một cách độc lập, tạo bảng sản phẩm và bảng thao tác:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_tx_error;

CREATE TABLE lesson_tx_error.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE lesson_tx_error.audit_events (
    audit_id BIGINT PRIMARY KEY,
    event_name TEXT NOT NULL,
    product_id BIGINT NOT NULL
        REFERENCES lesson_tx_error.products(product_id)
);

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES
    (1, 'SKU-001', 'Bàn phím', 10),
    (2, 'SKU-002', 'Chuột', 20);
```

Giả định schema/bảng chưa tồn tại và role có quyền tạo. Những câu ví dụ tiếp theo dùng **ID mới** trong transaction rồi `ROLLBACK` để không phải giữ trạng thái dữ liệu khác nhau giữa các lần học.

Xem dữ liệu:

```sql
SELECT product_id, sku, product_name, quantity
FROM lesson_tx_error.products
ORDER BY product_id;
```

Kết quả ban đầu:

| product_id | sku | product_name | quantity |
|---:|---|---|---:|
| 1 | SKU-001 | Bàn phím | 10 |
| 2 | SKU-002 | Chuột | 20 |

Ràng buộc `UNIQUE(sku)` cố ý dùng để tạo lỗi `23505` trong bài thực hành.

## 3. Trạng thái của một transaction ở mức khái niệm

Một cách mô hình hóa đơn giản:

```text
Session sẵn sàng (không ở trong transaction tường minh)
             │
             │ BEGIN
             ▼
     Transaction bình thường
     có thể SELECT/INSERT/UPDATE/DELETE
             │
       ┌─────┴─────────┐
       │               │
    COMMIT          SQL bị lỗi
       │               │
       ▼               ▼
   Kết thúc      Transaction đã lỗi
   thành công    (failed / aborted)
                       │
                 ┌─────┴─────────────────┐
                 │                       │
              ROLLBACK          ROLLBACK TO SAVEPOINT
                 │              (nếu savepoint hợp lệ)
                 ▼                       │
             Kết thúc                    ▼
             giao dịch        Trở lại transaction hợp lệ
                                       │
                                COMMIT / ROLLBACK
```

Trong PostgreSQL, transaction tường minh sau một lỗi SQL thông thường **không tự quay về trạng thái có thể làm việc tiếp**. Bạn phải xử lý ranh giới giao dịch.

Một số trạng thái khái niệm cần phân biệt:

- **Idle:** không đang ở trong transaction block tường minh.
- **In transaction:** đã `BEGIN` và transaction đang ở trạng thái có thể thực hiện lệnh.
- **Failed transaction:** đã có lỗi khiến transaction bị đánh dấu thất bại.
- **Active:** backend đang xử lý câu lệnh ở thời điểm quan sát; đây là trạng thái hoạt động, không phải một kiểu commit riêng.
- **Connection lost/unknown:** phiên đã bị mất hoặc không thể xác định trạng thái; không thể giả định rollback đã được server xử lý cho một commit đang bay trên mạng.

Các công cụ khác nhau biểu diễn trạng thái khác nhau; phần sau sẽ chỉ ra ký hiệu trong `psql`, trạng thái libpq và `pg_stat_activity`.

## 4. Kịch bản gốc: lỗi 23505 dẫn đến 25P02

Thực hiện các lệnh **từng câu** trong một session `psql` để thấy chuỗi lỗi:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 1
WHERE product_id = 1;

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (
    3, 'SKU-001', 'Sản phẩm trùng SKU', 5
);
```

Câu `UPDATE` đầu tiên có thể thành công và tạo thay đổi **chưa commit**. Nhưng `INSERT` dùng `SKU-001` vốn đã có trong bảng, nên ràng buộc unique báo lỗi:

```text
ERROR: duplicate key value violates unique constraint "products_sku_key"
DETAIL: Key (sku)=(SKU-001) already exists.
SQLSTATE: 23505
```

Tên constraint và định dạng thông điệp có thể khác theo môi trường; mã SQLSTATE là tín hiệu ổn định hơn để phân loại.

Bây giờ chạy tiếp:

```sql
SELECT quantity
FROM lesson_tx_error.products
WHERE product_id = 1;
```

PostgreSQL có thể trả:

```text
ERROR: current transaction is aborted, commands ignored
       until end of transaction block
SQLSTATE: 25P02
```

Ngay cả một `SELECT 1` thông thường cũng không cứu được giao dịch:

```sql
SELECT 1;
-- ERROR 25P02 trong cùng transaction đã lỗi
```

Để kết thúc:

```sql
ROLLBACK;

SELECT product_id, quantity
FROM lesson_tx_error.products
WHERE product_id = 1;
```

`quantity` của sản phẩm 1 vẫn là **10**, vì thao tác giảm về 9 chưa được commit và đã bị hủy khi rollback.

**Đây là ý chính của bài:** câu `INSERT` vi phạm unique là lỗi gốc `23505`; những câu SQL sau trong transaction báo `25P02` do transaction **đã bị hủy trạng thái**, và `ROLLBACK` đưa session về trạng thái có thể làm việc trở lại.

## 5. Vì sao PostgreSQL không tiếp tục như chưa có lỗi?

Nếu câu đầu thay đổi tồn kho, câu sau ghi audit, câu tiếp tạo hóa đơn, một lỗi giữa chừng có thể khiến trạng thái nghiệp vụ chỉ được thực hiện **một phần** nếu database cho tiếp tục tùy ý.

PostgreSQL không mặc định suy luận “bỏ qua câu lỗi, nhưng vẫn commit các câu trước” trong transaction tường minh. Thay vào đó, một lỗi SQL thông thường làm transaction bị đánh dấu **aborted**, buộc client xác định lại ranh giới:

- **Rollback tất cả** khi nghiệp vụ là nguyên tử.
- **Rollback về savepoint** nếu phần có lỗi là nhánh nghiệp vụ độc lập, cho phép bỏ phần ấy nhưng giữ phần trước.

Điều này phù hợp với tính nguyên tử của transaction và giúp lỗi được xử lý tường minh ở tầng ứng dụng.

### Transaction aborted không đồng nghĩa dữ liệu đã commit

Ở ví dụ trên, câu `UPDATE` báo thành công trước `INSERT` lỗi. Điều đó **không có nghĩa thay đổi đã bền vững**. Nó vẫn nằm trong transaction chưa commit, và rollback sẽ hủy.

Không thể suy luận “câu lệnh được PostgreSQL trả UPDATE 1 thì chắc chắn commit” khi đang ở trong `BEGIN ... COMMIT`.

## 6. SQLSTATE 25P02: lỗi thứ cấp cần tìm nguyên nhân đầu tiên

Thông điệp:

```text
current transaction is aborted, commands ignored until end
of transaction block
```

và SQLSTATE **`25P02`** có tên điều kiện **`in_failed_sql_transaction`**.

Ví dụ trình tự log:

```text
10:00:00 BEGIN
10:00:01 UPDATE ...              -> OK
10:00:02 INSERT duplicate SKU    -> 23505
10:00:03 SELECT ...              -> 25P02
10:00:04 INSERT audit ...        -> 25P02
10:00:05 SELECT current_user     -> 25P02
```

Nếu chỉ nhìn exception cuối, developer có thể mất thời gian “sửa SELECT” hoặc “sửa audit insert”, trong khi câu SQL sai đầu tiên là `INSERT` ở 10:00:02.

### Quy trình đọc chuỗi lỗi

1. Xác định request/connection/transaction có lỗi.
2. Tìm **SQLSTATE đầu tiên khác 25P02** trong cùng transaction.
3. Đọc SQLSTATE, constraint name, table/column/detail từ lỗi đầu.
4. Tìm nguyên nhân nghiệp vụ hoặc dữ liệu của câu đầu.
5. **Rollback transaction** trước khi thử lại hoặc trả connection về pool.
6. Nếu cần retry, bắt đầu transaction mới, không tái sử dụng trạng thái aborted.

Không nên log hàng trăm lần `25P02` rồi bỏ qua thông điệp gốc; một số lỗi sau chỉ là triệu chứng của transaction đã thất bại.

## 7. Các lỗi gốc thường đưa transaction vào trạng thái failed

| SQLSTATE | Tên lỗi thường gặp | Ví dụ |
|---|---|---|
| **`23505`** | `unique_violation` | Chèn SKU/khóa unique đã tồn tại. |
| **`23503`** | `foreign_key_violation` | Chèn dòng con tham chiếu ID cha không có. |
| **`23502`** | `not_null_violation` | Ghi `NULL` vào cột `NOT NULL`. |
| **`23514`** | `check_violation` | Tồn kho âm vi phạm `CHECK(quantity >= 0)`. |
| **`22P02`** | `invalid_text_representation` | Ép `'abc'::integer`. |
| **`22012`** | `division_by_zero` | Biểu thức chia cho 0. |
| **`42P01`** | `undefined_table` | Gọi bảng không tồn tại. |
| **`42703`** | `undefined_column` | Gọi cột không tồn tại. |
| **`42501`** | `insufficient_privilege` | Không có quyền thao tác. |
| **`40001`** | `serialization_failure` | Xung đột ở mức cô lập serializable/repeatable-read theo ngữ nghĩa tương ứng. |
| **`40P01`** | `deadlock_detected` | PostgreSQL phát hiện vòng chờ khóa và chọn một transaction làm nạn nhân. |
| **`55P03`** | `lock_not_available` | Không lấy được lock khi `NOWAIT` hoặc hết `lock_timeout`. |
| **`57014`** | `query_canceled` | Câu SQL bị cancel hoặc hết `statement_timeout`. |
| **`25P02`** | `in_failed_sql_transaction` | Lệnh tiếp theo bị từ chối vì transaction đã ở trạng thái failed. |

Những mã trên giúp phân loại lỗi nhưng **không tự quyết định có nên retry hay không**. Ví dụ `23505` có thể là xung đột nghiệp vụ cần trả HTTP 409, chứ không phải thử insert lại liên tục. `40001` thường là ứng viên retry **toàn bộ giao dịch**, nhưng cần giới hạn số lần và bảo đảm tác dụng phụ ngoài database không bị nhân đôi.

### Lỗi ở lệnh đọc cũng có thể làm transaction aborted

Không chỉ `INSERT`/`UPDATE`:

```sql
BEGIN;

SELECT 'not-a-number'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

Câu `SELECT` có lỗi vẫn có thể làm một transaction tường minh chuyển thành failed.

## 8. Giao dịch tường minh và autocommit khác nhau thế nào?

### Trường hợp A — Không BEGIN, psql mặc định autocommit

`psql` thường bật autocommit. Mỗi câu lệnh riêng tự được xử lý trong transaction ngầm của nó:

```sql
INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Trùng', 5);
-- Lỗi 23505, transaction của câu này bị rollback.

SELECT 1 AS still_working;
-- Thường chạy được: transaction implicit mới.
```

Không có `BEGIN` tường minh, lỗi của một statement thông thường chỉ rollback statement transaction ấy. Câu tiếp theo có thể bắt đầu transaction mới nên không gặp `25P02` do cùng một transaction.

### Trường hợp B — Có BEGIN

```sql
BEGIN;

SELECT 'abc'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

Giao dịch còn đang ở trạng thái failed giữa lỗi và rollback.

### Autocommit là hành vi của client/driver, không phải “transaction biến mất”

Ngay cả khi mỗi statement tự commit/rollback, PostgreSQL vẫn xử lý statement theo ngữ nghĩa transaction. `autocommit=true` ở JDBC nghĩa là driver/connection quản lý mỗi statement theo quy tắc đó, không có nghĩa database bỏ ACID.

### Trộn BEGIN tay với JDBC autocommit dễ gây nhầm

Không nên gửi `BEGIN` trực tiếp qua `Statement.execute("BEGIN")` trong một chương trình đồng thời dựa vào `Connection.setAutoCommit(false)` mà không có thiết kế rõ. Với JDBC, ưu tiên giao diện `setAutoCommit(false)`, `commit()` và `rollback()`, hoặc để transaction manager sở hữu toàn bộ vòng đời.

## 9. COMMIT khi transaction đã lỗi có làm dữ liệu được commit không?

Một điểm dễ hiểu sai: Trong PostgreSQL, nếu transaction tường minh đã bị aborted, việc gửi `COMMIT` có thể **kết thúc transaction bằng rollback** và server thường trả command tag `ROLLBACK`.

Ví dụ:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = 5
WHERE product_id = 1;

SELECT 'bad'::integer;
-- ERROR 22P02

COMMIT;
-- PostgreSQL thường phản hồi: ROLLBACK
```

**Không có chuyện COMMIT cứu được các thay đổi trước lỗi**. Lượng tồn kho đã đặt về 5 được hoàn nguyên.

### Vậy nên dùng COMMIT hay ROLLBACK?

Khi đã biết transaction failed, nên gọi **`ROLLBACK` tường minh** để ý định rõ ràng và tránh hiểu lầm. Đừng xây chương trình dựa vào việc “cứ COMMIT cuối cùng; server sẽ tự làm đúng”.

### COMMIT có thể tự gây lỗi khác

Một trường hợp riêng là lỗi **xảy ra ngay khi COMMIT**, ví dụ kiểm tra ràng buộc deferred hoặc lỗi serialization được phát hiện lúc commit. Khi đó, transaction có thể đã được PostgreSQL kết thúc bằng rollback. Cần đọc lỗi gốc và trạng thái connection thay vì giả định mọi lỗi đều để lại cùng một transaction đang mở chờ `ROLLBACK`.

Điểm chung ở phía ứng dụng: **không thông báo nghiệp vụ thành công khi COMMIT không thành công**; kiểm tra kết quả và khởi tạo giao dịch mới nếu cần thử lại.

## 10. ROLLBACK hủy tất cả thay đổi chưa commit

Ví dụ:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 2
WHERE product_id = 2;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (900, 'decrement-stock', 2);

ROLLBACK;

SELECT quantity
FROM lesson_tx_error.products
WHERE product_id = 2;

SELECT *
FROM lesson_tx_error.audit_events
WHERE audit_id = 900;
```

Sau rollback, `quantity` của product 2 trở về 20 và audit event 900 không tồn tại, miễn không có tác động ngoại lai ngoài transaction.

### Những gì rollback không nhất thiết hoàn nguyên

Không phải mọi hệ quả có thể quan sát đều transactional:

- Giá trị đã lấy từ **sequence** bằng `nextval()` thường **không được trả lại** khi rollback.
- Một lời gọi ra **email, HTTP API hoặc hệ thống ngoài** có thể đã xảy ra và không tự bị thu hồi.
- Log của ứng dụng, log server và metric được ghi bên ngoài transaction có thể vẫn tồn tại.
- Một số hoạt động dùng tài nguyên ngoài hoặc side effects của extension có ngữ nghĩa riêng.

Vì vậy, “rollback database” **không đồng nghĩa rollback toàn bộ thế giới bên ngoài**. Nếu nghiệp vụ có hệ thống ngoài, cần thiết kế outbox, idempotency hoặc cơ chế bù trừ phù hợp.

## 11. SAVEPOINT: giới hạn phạm vi phải quay lui

Không phải mọi lỗi cục bộ đều buộc bỏ toàn bộ công việc nếu nghiệp vụ cho phép. PostgreSQL hỗ trợ `SAVEPOINT` trong transaction.

```text
BEGIN
  │
  ├── thao tác A thành công
  │
  ├── SAVEPOINT before_optional
  │
  ├── thao tác B thất bại
  │      │
  │      └── ROLLBACK TO SAVEPOINT before_optional
  │
  ├── thao tác C tiếp tục hợp lệ
  │
  └── COMMIT
```

`ROLLBACK TO SAVEPOINT` hủy các thay đổi được thực hiện **sau savepoint được chỉ định**, nhưng **không hủy toàn bộ transaction**. Thao tác trước savepoint vẫn còn trong transaction và chỉ thành bền vững nếu cuối cùng `COMMIT` thành công.

### Ví dụ đầy đủ

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 1
WHERE product_id = 1;

SAVEPOINT before_optional_insert;

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Trùng SKU', 5);
-- ERROR 23505

ROLLBACK TO SAVEPOINT before_optional_insert;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (901, 'inventory-adjusted', 1);

RELEASE SAVEPOINT before_optional_insert;

COMMIT;
```

Sau ví dụ này:

- Việc giảm số lượng product 1 và audit 901 được commit.
- Bản ghi product 3 không được tạo vì `INSERT` lỗi và đã rollback về savepoint.

**Lưu ý:** Khác các ví dụ có `ROLLBACK` cuối cùng, ví dụ này `COMMIT` thật và thay đổi dữ liệu lab. Nếu muốn luyện lại nhiều lần mà không để lại thay đổi, đặt thêm một transaction ngoài trong môi trường riêng hoặc sửa câu cuối thành `ROLLBACK` sau khi thử đường phục hồi.

### Lệnh nào được phép trong trạng thái failed?

Trong một transaction đã lỗi, `ROLLBACK TO SAVEPOINT tên_hợp_lệ` là cách phục hồi được hỗ trợ **nếu savepoint đã được thiết lập trước lỗi và còn hiệu lực**. `RELEASE SAVEPOINT` hoặc các statement SQL thông thường **không thay thế** `ROLLBACK TO SAVEPOINT` trong trạng thái aborted.

## 12. ROLLBACK TO SAVEPOINT khác ROLLBACK hoàn toàn

| Câu lệnh | Tác động | Có thể tiếp tục transaction cũ? |
|---|---|---|
| `ROLLBACK;` | Kết thúc transaction, hủy mọi thay đổi chưa commit. | **Không**; muốn tiếp tục phải bắt đầu transaction mới. |
| `ROLLBACK TO SAVEPOINT s;` | Hủy thao tác sau savepoint `s` và phục hồi trạng thái transaction tại đó. | **Có**, nếu savepoint hợp lệ và việc phục hồi thành công. |
| `RELEASE SAVEPOINT s;` | Bỏ savepoint đã tạo; không phải commit transaction. | Có khi transaction bình thường; không dùng để cứu failed transaction. |
| `COMMIT;` | Commit nếu transaction hợp lệ; khi transaction đã aborted có thể kết thúc bằng rollback. | Kết thúc transaction hiện tại. |

Sau `ROLLBACK TO SAVEPOINT s`, savepoint `s` **vẫn còn tồn tại**; có thể dùng `RELEASE SAVEPOINT s` hoặc rollback tới nó lần nữa theo quy tắc savepoint.

### SAVEPOINT không phải giao dịch lồng nhau độc lập

Không thể commit riêng thao tác B ở savepoint và đảm bảo nó sống sót nếu transaction ngoài bị rollback. Mọi thay đổi còn nằm trong **cùng transaction ngoài** cho tới `COMMIT` cuối.

Đừng nhầm:

```sql
SAVEPOINT s;
-- thay đổi
RELEASE SAVEPOINT s;
-- chưa phải COMMIT!
ROLLBACK;
```

với hai transaction độc lập. `ROLLBACK` cuối vẫn hủy những thay đổi chưa commit, kể cả phần đã release savepoint.

## 13. Savepoint có thể lồng nhiều mức

PostgreSQL hỗ trợ nhiều savepoint theo cấu trúc lồng:

```sql
BEGIN;

SAVEPOINT phase_a;
-- Công việc thuộc phase A.

SAVEPOINT phase_b;
-- Công việc thuộc phase B.

ROLLBACK TO SAVEPOINT phase_b;
-- Hủy thay đổi sau phase_b.

RELEASE SAVEPOINT phase_b;

ROLLBACK TO SAVEPOINT phase_a;
-- Tiếp tục hủy những thay đổi sau phase_a.

ROLLBACK;
```

Nếu tạo nhiều savepoint **cùng tên**, PostgreSQL có quy tắc ưu tiên savepoint gần nhất đang còn hiệu lực; để tránh gây khó hiểu, tốt hơn dùng tên khác nhau và cấu trúc scope rõ ràng.

### Không tạo savepoint sau khi đã lỗi để “cứu” transaction

```sql
BEGIN;
SELECT 'broken'::integer;
-- ERROR

SAVEPOINT too_late;
-- Không thể coi đây là savepoint phục hồi.
```

Một khi transaction đã aborted, câu lệnh `SAVEPOINT` mới không thể chạy bình thường. Savepoint phải được tạo **trước thao tác có thể lỗi**.

Để khôi phục ví dụ trên:

```sql
ROLLBACK;
```

## 14. Khi nào nên dùng savepoint?

Các ví dụ phù hợp khi nghiệp vụ cho phép:

- Import nhiều dòng nhưng một số dòng lỗi có thể **ghi nhận rồi bỏ qua**, trong khi các dòng hợp lệ cần commit.
- Một bước tùy chọn không được phép làm hủy toàn bộ workflow.
- Thử thao tác có khả năng vi phạm constraint, rồi quay lại trạng thái trước bước đó và xử lý theo hướng khác.
- ORM/driver hỗ trợ **nested transaction dựa trên savepoint** một cách đúng đắn.

Tuy nhiên, savepoint **không tự làm mọi lỗi trở thành có thể bỏ qua**. Nếu bước lỗi có nghĩa đơn hàng không còn hợp lệ, bạn nên rollback toàn bộ transaction thay vì tiếp tục tạo hóa đơn thiếu dữ liệu.

### Cẩn thận với retry ở savepoint

Lỗi `40001` (serialization failure) thường yêu cầu thử lại **toàn bộ transaction** bao gồm những phép đọc và quyết định nghiệp vụ, không chỉ lặp lại statement bị lỗi trong cùng transaction. `40P01` (deadlock) cũng thường cần rollback giao dịch nạn nhân và thử lại công việc từ đầu. Không thiết kế savepoint như cách chung để vượt qua mọi loại lỗi đồng thời.

## 15. Các lệnh psql để nhìn trạng thái lỗi

Trong `psql`, prompt mặc định có thể phản ánh trạng thái transaction. Một số kiểu hiển thị:

```text
postgres=#        -- không ở trong BEGIN tường minh
postgres=*#       -- đang ở trong transaction bình thường
postgres=!#       -- transaction đã failed/aborted
```

Đây là ví dụ prompt khi role có prompt kiểu `#`; với role thông thường ký tự cuối thường là `>`. Tên database trong prompt cũng tùy connection. Ký hiệu `*`/`!` thể hiện trạng thái giao dịch theo cấu hình prompt của `psql`.

### Bật chi tiết lỗi

Trong `psql`:

```text
\set VERBOSITY verbose
```

Sau một lỗi, có thể dùng:

```text
\errverbose
```

để xem thêm trường chẩn đoán, bao gồm SQLSTATE nếu server cung cấp.

Các lệnh bắt đầu bằng dấu `\` là **meta-command của `psql`**, không phải câu SQL để gửi qua JDBC.

### Kịch bản thực hành

```sql
BEGIN;
SELECT 1 / 0;
-- ERROR 22012
SELECT 2;
-- ERROR 25P02
ROLLBACK;
SELECT 2;
-- Thành công
```

Nếu prompt vẫn biểu thị failed transaction, đừng cố chạy thêm `SELECT` hoặc `SET` thông thường. Hãy kết thúc giao dịch với `ROLLBACK` trước.

## 16. ON_ERROR_ROLLBACK trong psql

`psql` có biến riêng `ON_ERROR_ROLLBACK` hỗ trợ quy trình tương tác khi đang ở trong transaction block:

```text
\set ON_ERROR_ROLLBACK on
```

Với thiết lập này, trong những ngữ cảnh phù hợp `psql` có thể tạo một savepoint tự động trước statement trong transaction và rollback về đó khi statement lỗi. Nhờ vậy, bạn có thể tiếp tục ở transaction sau một số lỗi mà không phải gõ `SAVEPOINT` thủ công cho từng statement.

Ví dụ mục đích:

```text
\set ON_ERROR_ROLLBACK on
BEGIN;
SELECT 1;
SELECT 1 / 0;   -- psql tự phục hồi về savepoint nội bộ
SELECT 2;       -- có thể tiếp tục
ROLLBACK;
```

**Đừng coi đây là hành vi mặc định của server PostgreSQL.** Đây là tính năng của **client `psql`**. JDBC, ứng dụng web hoặc công cụ migration không tự có cơ chế đó chỉ vì bạn đã từng bật trong phiên `psql`.

### ON_ERROR_ROLLBACK khác ON_ERROR_STOP

- `ON_ERROR_ROLLBACK`: hỗ trợ phục hồi theo savepoint trong `psql` khi phù hợp.
- `ON_ERROR_STOP`: yêu cầu `psql` **dừng xử lý script** khi gặp lỗi, thay vì tiếp tục đọc các câu lệnh kế tiếp.

Hai biến giải quyết hai vấn đề khác nhau. Nếu mục tiêu migration là **dừng và rollback tất cả khi có lỗi**, thường nên dùng cơ chế một transaction và dừng khi lỗi, không bật tự động bỏ qua lỗi rồi commit phần còn lại.

## 17. Chạy script SQL an toàn với psql

Với file migration đã được thiết kế để chạy trong một transaction, một mẫu gọi hữu ích:

```powershell
psql -X -v ON_ERROR_STOP=1 --single-transaction -f migration.sql
```

Giải thích:

- `-X`: không đọc startup file `psqlrc`, giảm ảnh hưởng cấu hình cá nhân.
- `-v ON_ERROR_STOP=1`: dừng khi gặp lỗi trong script.
- `--single-transaction` (tương đương `-1`): bọc các lệnh `-f`/`-c` trong một transaction do `psql` quản lý.
- `-f migration.sql`: chạy file SQL.

Nếu có lỗi trong cách chạy này, `psql` sẽ không tiếp tục chạy toàn bộ migration và sẽ cố kết thúc giao dịch theo cơ chế rollback phù hợp.

**Điều kiện quan trọng:** Không phải câu lệnh PostgreSQL nào cũng được chạy trong transaction block, ví dụ những tác vụ nhất định như `CREATE DATABASE`. Script chứa lệnh đòi chạy ngoài transaction không phù hợp với `--single-transaction`; cần thiết kế migration theo tính chất lệnh.

### Trong script không bọc transaction sẽ ra sao?

Nếu `psql` autocommit và tiếp tục sau lỗi, các câu lệnh **trước đó có thể đã commit riêng**. Dừng script ở lỗi không tự hoàn nguyên các câu đã commit từ trước.

Vì vậy cần phân biệt:

1. **Dừng khi lỗi** (`ON_ERROR_STOP`).
2. **Đảm bảo atomic cho cả script** (transaction bao quanh các câu lệnh hỗ trợ).

Một workflow an toàn cần cả hai khi bài toán yêu cầu *all-or-nothing*.

## 18. Kiểm tra transaction status qua libpq

Ở tầng client C/libpq, PostgreSQL cung cấp API như `PQtransactionStatus()` để trả trạng thái transaction của connection.

Các giá trị thường gặp:

| Trạng thái libpq | Ý nghĩa |
|---|---|
| `PQTRANS_IDLE` | Connection hiện không trong transaction block. |
| `PQTRANS_ACTIVE` | Đang xử lý command. |
| `PQTRANS_INTRANS` | Trong transaction block bình thường. |
| `PQTRANS_INERROR` | Trong transaction block đã failed. |
| `PQTRANS_UNKNOWN` | Không xác định được trạng thái, thường liên quan lỗi kết nối. |

Đây là tên hằng/API của **libpq**, không phải câu SQL:

```c
PGTransactionStatusType status = PQtransactionStatus(conn);

if (status == PQTRANS_INERROR) {
    // Cần kết thúc transaction lỗi hoặc rollback về savepoint.
}
```

Mẫu code C chỉ minh họa ý nghĩa; giả định `PGconn *conn` hợp lệ và đã bao gồm header libpq.

### JDBC có dùng API này trực tiếp không?

JDBC chuẩn không expose các hằng `PQTRANS_*` như một hợp đồng xuyên driver. Với JDBC, nên dựa vào **vòng đời transaction mà ứng dụng sở hữu**, `SQLException.getSQLState()`, `Connection.rollback()` và khả năng kiểm soát lỗi qua driver/framework. Không viết code Java phụ thuộc một API libpq không tồn tại trong JDBC tiêu chuẩn.

## 19. pg_stat_activity và trạng thái "idle in transaction (aborted)"

Khi một session có transaction lỗi nhưng client chưa rollback, PostgreSQL có thể hiển thị trạng thái:

```text
idle in transaction (aborted)
```

trong `pg_catalog.pg_stat_activity` khi backend đang nhàn rỗi chờ lệnh tiếp theo.

Ví dụ truy vấn chẩn đoán:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    state_change,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction (aborted)'
ORDER BY state_change;
```

**Đây phải là một connection giám sát khác đang ở trạng thái bình thường.** Trong chính transaction failed, việc chạy `SELECT pg_stat_activity` cũng có thể nhận `25P02`.

### Trạng thái này có ý nghĩa vận hành gì?

Nó cho thấy một client đã để transaction lỗi **chưa được xử lý dứt điểm**. Tác động có thể bao gồm:

- Connection bị chiếm và không phục vụ được công việc bình thường.
- Connection pool bị cạn nếu nhiều request giữ connection như vậy.
- Ứng dụng lặp đi lặp lại SQL và chỉ nhận `25P02`.
- Tốn tài nguyên backend/session và làm khó việc theo dõi vấn đề thật.

Không nên nói rằng mọi transaction aborted chắc chắn vẫn giữ mọi row lock giống transaction bình thường; cơ chế hủy của PostgreSQL có thể giải phóng các loại lock/tài nguyên liên quan. Vấn đề chính là **lifecycle transaction và connection chưa được xử lý đúng**.

### Quyền xem pg_stat_activity

Role thông thường có thể bị giới hạn thông tin phiên của người khác. Dùng role giám sát có quyền tối thiểu phù hợp; không cấp superuser chỉ để xem state.

## 20. Timeout, cancel và trạng thái giao dịch

Một câu SQL có thể thất bại vì timeout hoặc bị hủy:

```sql
BEGIN;

SET LOCAL statement_timeout = '100ms';

SELECT pg_sleep(1);
-- Có thể ERROR 57014 query_canceled do statement_timeout.

SELECT 1;
-- Có thể ERROR 25P02 do transaction đã failed.

ROLLBACK;
```

`SET LOCAL` đặt cấu hình trong transaction hiện tại. Khi `pg_sleep(1)` bị hủy bởi `statement_timeout`, câu lệnh lỗi có thể khiến giao dịch tường minh chuyển sang aborted, giống nhiều lỗi SQL khác.

### Những loại timeout khác nhau

| Cơ chế | Tác động điển hình |
|---|---|
| `statement_timeout` | Hủy câu SQL chạy quá giới hạn. |
| `lock_timeout` | Lỗi khi chờ lấy lock quá giới hạn. |
| `idle_in_transaction_session_timeout` | Có thể chấm dứt session đã idle trong transaction quá lâu. |
| Timeout phía JDBC/pool/network | Có thể hủy statement, mất kết nối hoặc trả lỗi ở client tùy nơi phát sinh. |

Không giả định mọi timeout đều tạo cùng SQLSTATE hay cùng trạng thái connection. Nếu server đã **đóng kết nối**, không thể chạy `ROLLBACK` trên chính connection đã mất; ứng dụng phải bỏ connection và xử lý kết quả nghiệp vụ theo khả năng xác minh.

### Query cancel không phải transaction rollback tự động

Khi một câu SQL bị cancel trong transaction tường minh, xử lý an toàn là **xác định lỗi, rollback giao dịch hoặc savepoint hợp lệ**, rồi bắt đầu công việc mới. Đừng chỉ gọi lại statement ngay trên transaction failed.

## 21. Deadlock và serialization failure: rollback rồi retry toàn bộ

Hai lỗi thường được coi là **transient** trong bối cảnh đồng thời:

- `40P01` — deadlock detected.
- `40001` — serialization failure.

Chúng không có nghĩa SQL chắc chắn sai cú pháp. Hai transaction hợp lệ có thể xung đột do lịch chạy.

### Vì sao retry một statement là sai?

Giả sử transaction làm:

```text
BEGIN
  SELECT current_balance
  Tính quyết định chuyển tiền
  UPDATE accounts
  INSERT transfer_history
COMMIT
```

Nếu `UPDATE` hoặc `COMMIT` gặp `40001`, việc thử lại **chỉ UPDATE** trong cùng transaction không phục hồi những điều kiện đọc và quyết định ban đầu. Bạn cần:

1. Đảm bảo giao dịch cũ **đã kết thúc/rollback**.
2. Bắt đầu transaction **mới**.
3. Đọc lại dữ liệu liên quan.
4. Tính lại quyết định nghiệp vụ.
5. Thực hiện lại toàn bộ thay đổi.
6. Commit, và chỉ coi thành công khi commit thành công.

### Retry cần có giới hạn

- Giới hạn số lần thử, ví dụ 3–5 tùy SLA/workload.
- Dùng backoff có jitter khi nhiều worker cùng tranh chấp.
- Ghi lại SQLSTATE và số lần thử.
- Đảm bảo thao tác với hệ ngoài là **idempotent** hoặc được phối hợp bằng outbox.
- Nếu vượt số lần, trả lỗi có thể quan sát và xử lý ở tầng trên.

Không retry vô hạn vì có thể che lỗi thiết kế hoặc gây quá tải trong thời điểm tranh chấp.

## 22. Unique violation: rollback hay xử lý bằng ON CONFLICT?

Với mục tiêu “chèn SKU nếu chưa có”, `23505` có thể là một khả năng nghiệp vụ bình thường. Đừng tạo lỗi rồi cố tiếp tục trong transaction không có savepoint.

PostgreSQL hỗ trợ:

```sql
INSERT INTO lesson_tx_error.products(
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Bàn phím thay thế', 5)
ON CONFLICT (sku) DO NOTHING;
```

Khi trùng SKU, lệnh không insert và **không gây `23505` cho trường hợp conflict được xử lý**. Transaction vẫn có thể tiếp tục.

Nếu muốn update khi conflict:

```sql
INSERT INTO lesson_tx_error.products(
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Bàn phím thay thế', 5)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name;
```

Cần hiểu rõ quy tắc cập nhật để không vô tình ghi đè dữ liệu. `ON CONFLICT` chỉ xử lý những conflict thuộc phạm vi cú pháp; lỗi ràng buộc khác vẫn có thể phát sinh và làm transaction failed.

### Lựa chọn theo nghiệp vụ

| Yêu cầu | Chiến lược |
|---|---|
| Trùng khóa là **lỗi nghiêm trọng** | Báo `23505`, rollback transaction, trả kết quả lỗi nghiệp vụ phù hợp. |
| Trùng khóa có thể **bỏ qua** | `ON CONFLICT DO NOTHING` khi đúng chính sách. |
| Trùng khóa thì **cập nhật có điều kiện** | `ON CONFLICT DO UPDATE ... WHERE ...`. |
| Một item tùy chọn trong import bị lỗi | Có thể dùng savepoint rồi bỏ item đó; ghi nhận lý do. |
| Muốn giữ cả các lần nhận dữ liệu raw | Lưu raw append-only và deduplicate ở bảng canonical riêng. |

**Đừng dùng `ON CONFLICT` như mẹo bỏ qua mọi lỗi dữ liệu.** Hãy chỉ rõ constraint/key và ý nghĩa khi có conflict.

## 23. Foreign key và CHECK: lỗi đầu phải được xử lý

Một ví dụ vi phạm khóa ngoại:

```sql
BEGIN;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (902, 'unknown-product', 999999);
-- ERROR 23503

SELECT 1;
-- ERROR 25P02

ROLLBACK;
```

Vi phạm `CHECK`:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = -100
WHERE product_id = 1;
-- ERROR 23514

SELECT product_id
FROM lesson_tx_error.products;
-- ERROR 25P02

ROLLBACK;
```

Giải pháp không phải vô hiệu hóa constraint để “cho transaction chạy tiếp”, trừ khi đó là một thay đổi schema được thiết kế và phê duyệt. Constraint bảo vệ bất biến dữ liệu; tầng ứng dụng cần kiểm tra input, xử lý lỗi và rollback đúng.

## 24. Ràng buộc deferred: lỗi có thể đến vào lúc COMMIT

PostgreSQL có những ràng buộc hỗ trợ `DEFERRABLE`, ví dụ một số unique/foreign key/exclusion constraints. Nếu được đặt `INITIALLY DEFERRED` hoặc `SET CONSTRAINTS ... DEFERRED`, một số kiểm tra có thể được dời tới cuối transaction.

Ví dụ minh họa trong lab:

```sql
CREATE TABLE lesson_tx_error.deferred_demo (
    id INTEGER PRIMARY KEY,
    group_code TEXT,
    CONSTRAINT uq_deferred_group_code
        UNIQUE (group_code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Thử trong transaction:

```sql
BEGIN;

INSERT INTO lesson_tx_error.deferred_demo(id, group_code)
VALUES (1, 'A'), (2, 'A');

COMMIT;
-- Có thể lỗi 23505 tại COMMIT, transaction không được commit.
```

Điểm quan trọng: **Câu INSERT có thể báo thành công nhưng COMMIT thất bại** vì ràng buộc deferred. Do đó, kết quả commit phải được kiểm tra chứ không chỉ các execute trước đó.

Sau khi commit lỗi, tình trạng transaction/session cần được đánh giá theo trạng thái server/driver thực tế; không mặc định nó luôn giống trường hợp `23505` xảy ra giữa hai câu SQL trong `BEGIN`.

### Không mọi constraint đều có thể deferrable

Không phải mọi loại constraint hoặc kiểu unique index có cùng khả năng trì hoãn. Cần thiết kế schema phù hợp, và không xem `SET CONSTRAINTS DEFERRED` là cách né lỗi vĩnh viễn: nếu dữ liệu vẫn vi phạm ở thời điểm kiểm tra cuối, commit sẽ thất bại.

## 25. PL/pgSQL EXCEPTION có thể phục hồi lỗi bên trong block

Trong PL/pgSQL, một block có `EXCEPTION` được xử lý bằng cơ chế **subtransaction** nội bộ của PostgreSQL. Khi câu SQL trong block lỗi và được xử lý bởi handler, các thay đổi database trong block có thể bị rollback mà transaction bao ngoài **vẫn có thể tiếp tục**.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION lesson_tx_error.try_optional_sku()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        INSERT INTO lesson_tx_error.products(
            product_id, sku, product_name, quantity
        )
        VALUES (999, 'SKU-001', 'Tạo trùng có chủ đích', 1);

        RETURN 'inserted';
    EXCEPTION
        WHEN unique_violation THEN
            RETURN 'duplicate-sku-skipped';
    END;
END;
$$;
```

Gọi:

```sql
BEGIN;

SELECT lesson_tx_error.try_optional_sku() AS result;
-- duplicate-sku-skipped

SELECT COUNT(*) FROM lesson_tx_error.products;
-- Có thể tiếp tục, transaction không bị aborted bởi lỗi đã được bắt.

ROLLBACK;
```

**Không có nghĩa PL/pgSQL handler biến mọi lỗi thành an toàn**:

- Chỉ lỗi thực sự được **bắt và xử lý** mới đi theo nhánh này.
- Nếu handler ném lỗi tiếp bằng `RAISE;`, lỗi vẫn có thể làm transaction của caller aborted.
- Một handler bắt `unique_violation` có thể bắt lỗi từ ràng buộc **không phải SKU dự kiến**; muốn chính xác, cần kiểm tra constraint phù hợp.
- Không dùng `WHEN OTHERS THEN NULL` tùy tiện vì sẽ che lỗi dữ liệu, permission và các vấn đề nghiêm trọng.

### Biến PL/pgSQL và dữ liệu database

Khi exception được bắt, các thay đổi persistent database trong block lỗi được rollback theo cơ chế subtransaction. Giá trị biến PL/pgSQL có thể có quy tắc duy trì riêng; không nên suy luận đó là rollback mọi trạng thái bên ngoài database.

## 26. Bắt đúng constraint trong EXCEPTION

Giả sử chỉ muốn bỏ qua conflict do `products_sku_key`, nhưng một lỗi `unique_violation` khác cần được đẩy ra ngoài.

```sql
CREATE OR REPLACE FUNCTION lesson_tx_error.try_insert_known_sku(
    p_product_id BIGINT,
    p_sku TEXT,
    p_product_name TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_constraint_name TEXT;
BEGIN
    INSERT INTO lesson_tx_error.products(
        product_id, sku, product_name, quantity
    )
    VALUES (p_product_id, p_sku, p_product_name, 0);

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint_name = CONSTRAINT_NAME;

        IF v_constraint_name = 'products_sku_key' THEN
            RETURN FALSE;
        END IF;

        RAISE;
END;
$$;
```

Đoạn này minh họa:

- `GET STACKED DIAGNOSTICS` đọc metadata của exception đang xử lý.
- `CONSTRAINT_NAME` giúp phân biệt conflict dự kiến với vi phạm khóa chính.
- `RAISE;` trong exception handler phát lại lỗi không được dự kiến.

Trong ứng dụng, **`INSERT ... ON CONFLICT (sku) DO NOTHING`** thường đơn giản hơn cho nghiệp vụ “không chèn nếu SKU đã có”. Chỉ dùng exception handler khi cần điều kiện xử lý đặc thù.

## 27. JDBC: giao dịch thất bại phải được rollback trong catch

Trong JDBC, khi `Connection.setAutoCommit(false)`, các câu SQL tiếp theo tham gia transaction do ứng dụng kiểm soát. Một `SQLException` có thể khiến transaction PostgreSQL ở trạng thái aborted.

Mẫu cơ bản:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement update = connection.prepareStatement("""
                UPDATE lesson_tx_error.products
                SET quantity = quantity - 1
                WHERE product_id = ?
                """)) {
            update.setLong(1, 1L);
            update.executeUpdate();
        }

        try (PreparedStatement insert = connection.prepareStatement("""
                INSERT INTO lesson_tx_error.products(
                    product_id, sku, product_name, quantity
                )
                VALUES (?, ?, ?, ?)
                """)) {
            insert.setLong(1, 3L);
            insert.setString(2, "SKU-001");
            insert.setString(3, "Sản phẩm trùng");
            insert.setInt(4, 5);
            insert.executeUpdate();  // Có thể ném SQLException 23505.
        }

        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đây là mẫu Java minh họa trong phương thức có `throws SQLException` và có `DataSource dataSource` hợp lệ, dùng Java text blocks; imports được bỏ cho ngắn gọn.

Điểm cần chú ý:

1. **Không commit** nếu có một bước không được xử lý hợp lệ.
2. Trong `catch`, cố gắng `rollback()` để dọn transaction trước khi connection được đóng/trả về pool.
3. Nếu rollback cũng lỗi, **không che lỗi gốc**; ví dụ dùng `addSuppressed`.
4. Connection có thể hỏng hoặc mất mạng; khi `rollback()` không thành công, không tiếp tục sử dụng connection như còn sạch.
5. Khi framework quản lý transaction, dùng cơ chế transaction của framework thay vì tự rollback trên connection thuộc framework.

### Có cần khôi phục autoCommit?

Khi quản lý pool/connection thực, cần tuân theo hợp đồng của datasource về reset state. Trong mẫu trên, connection chỉ được mượn trong scope `try-with-resources` rồi đóng (trả về pool nếu pool quản lý). Không nên tự kết luận **mọi pool đều reset mọi session setting và transaction state**. Nếu tự giữ connection sống qua nhiều thao tác, cần quản lý việc phục hồi auto-commit, isolation, read-only và session state một cách chặt chẽ.

## 28. SQLException.getSQLState(): đừng bắt lỗi theo chuỗi message

Một xử lý đơn giản:

```java
try {
    statement.executeUpdate(sql);
} catch (SQLException e) {
    String state = e.getSQLState();

    if ("23505".equals(state)) {
        // Vi phạm unique constraint.
    } else if ("40001".equals(state) || "40P01".equals(state)) {
        // Có thể thử lại toàn bộ transaction theo chính sách.
    } else if ("25P02".equals(state)) {
        // Transaction đã lỗi; tìm exception gốc và rollback.
    }

    throw e;
}
```

Mẫu code giả định `statement` và `sql` đã có, minh họa phân loại exception chứ chưa thay thế transaction handling.

### Vì sao không bắt thông điệp tiếng Anh?

Thông điệp có thể khác vì locale, server version hoặc loại lỗi:

```java
// Không nên:
if (e.getMessage().contains("duplicate key")) {
    // ...
}
```

SQLSTATE là mã có cấu trúc để phần mềm phân loại. Nếu dùng pgJDBC, thông tin server error có thể còn cung cấp constraint/table/column qua API đặc thù driver; khi cần chính xác hơn `23505`, hãy đọc các trường cấu trúc đó.

### SQLException có chuỗi nguyên nhân

Một lỗi JDBC có thể có `getNextException()` hoặc cause chain. Khi logging, cần giữ SQLSTATE và context của **lỗi đầu**. Đừng chỉ log lỗi cuối `25P02` rồi bỏ qua nguyên nhân trước đó.

## 29. JDBC Savepoint: xử lý bước tùy chọn

JDBC có `java.sql.Savepoint` và các API:

- `Connection.setSavepoint()` hoặc `setSavepoint(name)`.
- `Connection.rollback(savepoint)`.
- `Connection.releaseSavepoint(savepoint)`.

Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Bước nghiệp vụ bắt buộc:
        try (PreparedStatement ps = connection.prepareStatement("""
                UPDATE lesson_tx_error.products
                SET quantity = quantity - 1
                WHERE product_id = ?
                """)) {
            ps.setLong(1, 1L);
            ps.executeUpdate();
        }

        Savepoint optionalInsert = connection.setSavepoint("optional_insert");

        try {
            try (PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO lesson_tx_error.products(
                        product_id, sku, product_name, quantity
                    )
                    VALUES (3, 'SKU-001', 'Trùng', 5)
                    """)) {
                ps.executeUpdate();
            }
        } catch (SQLException e) {
            if ("23505".equals(e.getSQLState())) {
                connection.rollback(optionalInsert);
                // Chỉ bỏ phần optional theo policy đã xác định.
            } else {
                throw e;
            }
        }

        connection.releaseSavepoint(optionalInsert);
        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Chỉ dùng mẫu này khi **vi phạm unique bất kỳ trong bước optional đều là tình huống có thể bỏ qua**. Nếu cần phân biệt khóa chính và unique SKU, hãy kiểm tra **constraint name** qua API driver hoặc thiết kế `ON CONFLICT (sku)`.

### Savepoint phục hồi lỗi database, không phải logic nghiệp vụ

Một savepoint hợp lệ giúp PostgreSQL trở lại transaction có thể chạy tiếp, nhưng **không đảm bảo object/EntityManager cache trong ORM cũng còn nhất quán** nếu nó đã flush thất bại. Với Hibernate/JPA, sau lỗi persistence thường nên rollback và bỏ persistence context tương ứng theo hướng dẫn framework, không “cứu” một session ORM hỏng bằng savepoint thủ công.

## 30. Spring @Transactional và rollback-only

Trong ứng dụng Spring, phương thức có `@Transactional` thường được chạy trong transaction do transaction manager kiểm soát:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeInventory(long productId) {
        repository.decrementQuantity(productId);
        repository.insertOptionalRelatedRecord(productId);
    }
}
```

Đây là skeleton minh họa, không phải file Java có đầy đủ class/interface; repository methods cần được ứng dụng định nghĩa.

Trong Spring transaction management phổ biến:

- Khi runtime exception đi ra khỏi transactional method, framework thường đánh dấu transaction cần rollback.
- Theo mặc định trong nhiều cấu hình Spring, **unchecked exceptions** và `Error` kích hoạt rollback, trong khi **checked exception** có thể cần `rollbackFor` nếu muốn rollback.
- Nếu một thành phần bên trong đã đánh dấu transaction **rollback-only**, bên ngoài cố commit có thể nhận `UnexpectedRollbackException`.
- **Bắt exception rồi bỏ qua** không tự làm PostgreSQL transaction trở lại bình thường.

### Ví dụ nguy hiểm: bắt lỗi SQL rồi tiếp tục

```java
@Transactional
public void dangerousWorkflow() {
    try {
        repository.insertDuplicateSku(); // Có thể ném DataAccessException.
    } catch (DataAccessException ignored) {
        // Sai nếu cho rằng transaction PostgreSQL được phục hồi.
    }

    repository.updateInventory(); // Có thể nhận SQLSTATE 25P02.
}
```

**Vấn đề:** Bắt exception ở Java không tương đương với `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` trên PostgreSQL.

### Các lựa chọn đúng

1. Nếu lỗi làm nghiệp vụ không hợp lệ: **để exception dẫn tới rollback** và trả lỗi phù hợp.
2. Nếu thao tác có thể trùng một cách hợp lệ: dùng **`ON CONFLICT`** hoặc thiết kế idempotent.
3. Nếu bước tùy chọn thật sự có thể rollback riêng: dùng **transaction propagation/savepoint** mà transaction manager và JDBC driver hỗ trợ, kiểm tra giới hạn ORM.
4. Nếu cần cô lập công việc độc lập: cân nhắc transaction mới với `REQUIRES_NEW` theo semantics framework và tài nguyên pool phù hợp.

`PROPAGATION_NESTED` dựa trên savepoint trong những transaction manager phù hợp; không tự coi nó có hỗ trợ trên mọi JPA stack. `REQUIRES_NEW` thường dùng **transaction độc lập**, không phải “savepoint mạnh hơn”, và có thể cần thêm connection.

## 31. Exception đã bị bắt không có nghĩa transaction được cứu

Một cặp tình huống cần phân biệt:

### Tình huống A — Exception ở tầng Java trước khi gửi SQL

```java
if (quantity < 0) {
    throw new IllegalArgumentException("quantity must be >= 0");
}
```

Nếu lỗi xảy ra **trước khi gửi statement** tới PostgreSQL, database có thể chưa gặp SQL error. Trạng thái transaction phụ thuộc transaction manager và việc exception được xử lý thế nào.

### Tình huống B — PostgreSQL đã từ chối statement

```java
statement.executeUpdate(
    "UPDATE lesson_tx_error.products SET quantity = -1 WHERE product_id = 1"
);
// PostgreSQL trả 23514 và transaction tường minh bị aborted.
```

Ở đây, dù Java bắt `SQLException` và không ném tiếp, transaction PostgreSQL **vẫn failed** trừ khi đã rollback tới savepoint hợp lệ hoặc kết thúc transaction.

### Tình huống C — PL/pgSQL handler xử lý lỗi nội bộ

Function có `EXCEPTION WHEN ...` có thể phục hồi qua subtransaction **ngay trong server**, nên transaction của caller vẫn bình thường nếu function hoàn thành thành công. Đây là cơ chế khác với **Java catch** thuần túy.

## 32. Batch insert: một dòng lỗi có thể ảnh hưởng cả batch

Với JDBC batch:

```java
try (PreparedStatement ps = connection.prepareStatement("""
        INSERT INTO lesson_tx_error.products(
            product_id, sku, product_name, quantity
        ) VALUES (?, ?, ?, ?)
        """)) {
    // ... addBatch nhiều lần ...
    ps.executeBatch();
}
```

Nếu một phần tử batch gây lỗi và transaction đang ở chế độ manual commit, **không nên giả định các phần tử còn lại có thể được commit bình thường**.

Hành vi cụ thể về những statement trong batch đã chạy/được gửi, update counts và exception phụ thuộc driver và các optimization của batch. Nhưng trong PostgreSQL transaction tường minh, khi một statement thực sự gây lỗi chưa được xử lý, giao dịch có thể bị aborted.

### Thiết kế import có dòng sai

Bạn có các lựa chọn:

- **All-or-nothing:** cả batch không thành công thì rollback và báo lỗi.
- **Skip từng dòng có kiểm soát:** savepoint theo đơn vị xử lý thích hợp hoặc chia batch thành các transaction nhỏ, lưu báo cáo lỗi.
- **Upsert idempotent:** nếu nhiều lỗi chỉ là conflict dự kiến, sử dụng `ON CONFLICT`.
- **Validate trước:** giảm lỗi nhưng không thay thế constraint vì có race và sự thay đổi dữ liệu đồng thời.

Đừng chỉ bắt `BatchUpdateException` rồi gọi `COMMIT` và hy vọng PostgreSQL giữ những hàng nào “đã chèn được”.

## 33. Transaction đã lỗi và connection pool

Connection pool (HikariCP, PgBouncer hoặc giải pháp khác) **tái sử dụng tài nguyên connection** để giảm chi phí kết nối. Nếu ứng dụng để một transaction failed chưa kết thúc, tình trạng đó có thể làm hỏng các thao tác tiếp theo trên cùng backend cho tới khi rollback.

```text
Request A
  mượn connection X
  BEGIN
  INSERT -> 23505
  [quên ROLLBACK]
  trả/giữ connection không được dọn đúng cách
                   │
                   ▼
Request B
  dùng lại backend X
  SELECT -> có thể gặp 25P02
```

Một số pool có logic reset hoặc rollback khi trả connection, nhưng **không nên giả định mọi cấu hình/pool/proxy luôn cứu được lỗi ứng dụng**. Chủ sở hữu transaction phải kết thúc nó đúng cách; pool đóng vai trò phòng vệ bổ sung.

### Các nguyên tắc

1. Mỗi request/job có **ranh giới transaction** rõ ràng.
2. Nếu có exception, rollback trong `finally`/`catch` hoặc để framework thực hiện rollback.
3. Không giữ connection mở khi thực hiện I/O ngoài kéo dài mà transaction không cần thiết.
4. Nếu rollback thất bại hoặc network mất, **loại bỏ connection không tin cậy** theo API/pool phù hợp.
5. Không tự thay đổi autocommit/session settings ở nhiều tầng khác nhau nếu không có hợp đồng reset rõ.
6. Theo dõi connection leak, pool exhaustion và `idle in transaction (aborted)`.

### PgBouncer không tự sửa transaction SQL bị lỗi

PgBouncer có các chế độ pooling với vòng đời backend khác nhau. Dù proxy có thể quản lý việc cấp lại kết nối, **transaction SQL hiện tại vẫn phải được xử lý đúng ở tầng ứng dụng**. Không dùng proxy như giải pháp thay cho rollback/savepoint.

## 34. Mất kết nối trong lúc COMMIT: kết quả có thể không chắc chắn

Một trường hợp đặc biệt nguy hiểm:

```text
Client gửi COMMIT
       │
       ▼
PostgreSQL có thể commit
       │
       ├── phản hồi về client -> client biết thành công
       │
       └── mạng đứt trước phản hồi -> client không chắc kết quả
```

Nếu mất mạng **sau khi server đã commit nhưng trước khi client nhận phản hồi**, client có thể thấy lỗi I/O và không biết chắc transaction đã commit hay chưa. Từ connection mất đó, bạn không thể gửi rollback và coi như đã hoàn tác thành công.

### Cách xử lý ở nghiệp vụ quan trọng

- Sử dụng **idempotency key** với unique constraint để retry an toàn.
- Có khả năng **truy vấn hòa giải** (reconciliation) theo business transaction ID.
- Không gửi lại thao tác chuyển tiền/đặt hàng một cách mù quáng có thể tạo trùng.
- Phân biệt lỗi SQLSTATE server với lỗi network/client trong log.
- Không thông báo chắc chắn “đã rollback” khi không có bằng chứng server đã xử lý.

Nguyên tắc này không mâu thuẫn với ACID: database có thể đảm bảo transaction đã commit hoặc rollback, nhưng **client bị mất thông tin về kết quả** ở một thời điểm nhất định.

## 35. Read-only transaction cũng có thể bị failed

Đừng coi các transaction chỉ đọc là miễn nhiễm:

```sql
BEGIN READ ONLY;

SELECT 'abc'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

`READ ONLY` hạn chế những thao tác ghi không phù hợp, nhưng không ngăn lỗi phép tính, cú pháp, quyền hoặc serialization. Những lỗi như `42P01`, `42703` hoặc `57014` cũng có thể làm transaction tường minh aborted.

### BEGIN READ ONLY không có nghĩa SELECT luôn thành công

Quyền `SELECT` trên bảng, điều kiện RLS và trạng thái query vẫn có thể gây lỗi hoặc trả 0 hàng. Transaction read-only cần rollback khi failed giống transaction khác.

## 36. DDL cũng có thể làm transaction aborted

PostgreSQL hỗ trợ nhiều thao tác DDL trong transaction:

```sql
BEGIN;

CREATE TABLE lesson_tx_error.temp_example (
    id INTEGER PRIMARY KEY
);

CREATE TABLE lesson_tx_error.temp_example (
    id INTEGER PRIMARY KEY
);
-- ERROR: relation already exists

SELECT 1;
-- 25P02

ROLLBACK;
```

Sau rollback, bảng `temp_example` được tạo ở câu đầu **không còn tồn tại** nếu trước đó không có bảng cùng tên. Đây là ví dụ về **transactional DDL** của PostgreSQL.

### Không phải mọi DDL đều chạy được trong transaction block

Một số thao tác quản trị yêu cầu chạy ngoài transaction block hoặc có quy tắc transaction riêng. Không viết script migration toàn cục `BEGIN ... COMMIT` rồi mặc định mọi câu lệnh đều phù hợp.

Nếu DDL bị lỗi trong một transaction được hỗ trợ, thao tác phục hồi vẫn là rollback hoặc savepoint hợp lệ, giống DML.

## 37. Các trạng thái SQLSTATE gần nhau nhưng không giống nhau

SQLSTATE là mã 5 ký tự. Hai ký tự đầu biểu thị **class lỗi**:

- `23`: integrity constraint violation, như `23505` hoặc `23503`.
- `22`: data exception, như `22P02`.
- `25`: invalid transaction state, bao gồm `25P02`.
- `40`: transaction rollback, như `40001` và `40P01`.
- `42`: syntax error or access rule violation.
- `57`: operator intervention, như `57014`.
- `08`: connection exception.

Không nên gom toàn bộ các class lại làm một policy. Ví dụ:

```text
23505 unique violation
    -> thường là lỗi dữ liệu/nhận diện trùng

40001 serialization failure
    -> có thể retry toàn bộ giao dịch

40P01 deadlock detected
    -> có thể retry toàn bộ giao dịch theo policy

25P02 in failed SQL transaction
    -> cần xử lý transaction đã lỗi, tìm lỗi gốc

08006 connection failure
    -> trạng thái connection có thể không còn tin cậy
```

**`25P02` là một trạng thái để ứng dụng khôi phục transaction**, không phải lý do để retry riêng statement vừa nhận mã đó.

## 38. Sơ đồ xử lý lỗi trong ứng dụng

Một thuật toán tư duy:

```text
Bắt đầu transaction
        │
        ▼
Thực hiện nghiệp vụ
        │
        ├── Không lỗi ──► COMMIT
        │                    │
        │              Thành công?
        │                 │      │
        │               Có       Không
        │                 │        │
        │              Xong     Phân tích lỗi commit
        │                          │
        └── Có lỗi ────────────────┘
                  │
                  ▼
          Có savepoint hợp lệ và
          nghiệp vụ cho phép bỏ bước?
               │              │
              Có             Không
               │              │
               ▼              ▼
       ROLLBACK TO s       ROLLBACK toàn bộ
               │              │
         Tiếp tục phần     Cần retry?
         còn lại nếu           │
         transaction OK       ├── Có -> transaction mới,
               │              │         làm lại toàn bộ
               ▼              │
             COMMIT           └── Không -> báo lỗi
```

Sơ đồ trên là mô hình quyết định. Đối với lỗi **mất kết nối**, thao tác rollback không chắc thực hiện được và kết quả commit có thể chưa rõ. Khi đó cần loại bỏ connection và thực hiện reconciliation/idempotency phù hợp.

## 39. Những hiểu nhầm phổ biến

**“Lỗi INSERT chỉ làm INSERT đó bị hủy, rồi tôi có thể tiếp tục UPDATE.”** Trong transaction tường minh PostgreSQL, lỗi SQL thông thường làm **toàn transaction bị aborted** cho tới rollback hoặc rollback về savepoint hợp lệ.

**“SQLSTATE 25P02 là lỗi đầu tiên.”** Thường không; đó là hậu quả khi chạy statement sau lỗi. Hãy tìm SQLSTATE trước đó.

**“Bắt SQLException ở Java làm database quên lỗi.”** Không. Java catch không thay thế rollback transaction của server.

**“COMMIT sau 25P02 sẽ commit những statement đã thành công.”** Không. PostgreSQL có thể trả `ROLLBACK` và hủy thay đổi chưa commit.

**“ROLLBACK TO SAVEPOINT cũng kết thúc transaction ngoài.”** Không. Nó phục hồi tới mốc đã tạo; transaction ngoài vẫn tồn tại và cần COMMIT/ROLLBACK sau đó.

**“RELEASE SAVEPOINT là commit một transaction con.”** Không. Nó chỉ giải phóng savepoint.

**“Có thể tạo SAVEPOINT sau khi lỗi.”** Không thể dùng một savepoint tạo quá muộn để khôi phục giao dịch đã aborted.

**“psql tự phục hồi lỗi nên JDBC cũng như vậy.”** Không. `ON_ERROR_ROLLBACK` là tính năng client `psql`, không phải mặc định PostgreSQL dành cho mọi client.

**“Rollback sẽ trả lại mọi giá trị sequence đã lấy.”** Không. Sequence có thể tăng và không rollback số đã cấp.

**“Rollback database sẽ thu hồi email đã gửi.”** Không. Tác dụng phụ ngoài database cần idempotency/outbox/bù trừ.

**“Savepoint là cách chuẩn retry mọi lỗi 40001.”** Không. Serialization failure thường yêu cầu thử lại **toàn bộ transaction**.

**“Mọi SQLSTATE 23505 đều nên retry.”** Không. Conflict có thể là lỗi nghiệp vụ thực, cần trả thông báo phù hợp.

**“Hết statement_timeout chỉ hủy câu đó và transaction vẫn luôn bình thường.”** Không với transaction tường minh; lỗi cancel có thể làm transaction aborted.

**“Connection.isValid() true nghĩa transaction không aborted.”** Không. Kết nối có thể còn sống nhưng transaction đang failed; kiểm tra vòng đời/lỗi và rollback.

**“Khi close() vào pool thì chắc chắn mọi state được xóa.”** Phụ thuộc pool/driver/transaction manager; ứng dụng vẫn phải kết thúc transaction đúng.

**“COMMIT có lỗi thì chắc chắn rollback được qua cùng connection.”** Không nếu connection đã mất; kết quả commit có thể chưa xác định.

**“Hàm PL/pgSQL bắt lỗi thì toàn bộ transaction bị rollback.”** Không nhất thiết. Exception block có thể rollback nội bộ qua subtransaction và trả lại caller bình thường.

**“Một lần SELECT thành công trước lỗi nghĩa dữ liệu đã commit.”** Không; trong transaction explicit, commit mới quyết định trạng thái cuối.

**“ON CONFLICT bỏ qua mọi lỗi constraint.”** Không. Nó xử lý những conflict được nêu/được hỗ trợ; lỗi khác vẫn có thể hủy transaction.

**“Tăng isolation level sẽ làm lỗi biến mất.”** Không; isolation cao hơn có thể phát sinh serialization failures cần retry hợp lệ.

## 40. Checklist vận hành cho transaction failed

Khi ứng dụng phát hiện `25P02` hoặc `idle in transaction (aborted)`:

1. **Tìm statement lỗi đầu tiên** trong cùng request/transaction, đọc SQLSTATE và constraint/detail.
2. **Không gửi thêm SQL nghiệp vụ** trên transaction failed.
3. Xác định **client sở hữu transaction**: code JDBC, framework, job runner hay migration tool.
4. Nếu không có savepoint được quản lý đúng và nghiệp vụ cho phép, **rollback toàn bộ**.
5. Nếu dùng savepoint, đảm bảo savepoint đã tồn tại trước lỗi và rollback tới đó thực sự thành công.
6. Đừng commit phần còn lại chỉ vì đã “nuốt” exception.
7. Đừng trả connection ở trạng thái không tin cậy cho request khác.
8. Phân loại lỗi gốc: business validation, conflict, deadlock/serialization, timeout hay network.
9. Chỉ retry toàn bộ transaction khi policy cho phép, giới hạn số lần và đảm bảo idempotency.
10. Theo dõi **tần suất lỗi gốc**, số backend aborted/idle, pool exhaustion và chậm commit.

Với lỗi network ở thời điểm commit, thêm bước **đối soát trạng thái nghiệp vụ** trước khi tự động gửi lại thao tác có tác dụng phụ.

## 41. Bài tập thực hành

### Bài 1 — Quan sát 23505 rồi 25P02

Trong `psql`, bắt đầu `BEGIN`, giảm `quantity` của product 1, sau đó chèn product mới có `sku = 'SKU-001'`. Ghi SQLSTATE của lỗi `INSERT` và của câu `SELECT 1` tiếp theo. Thực hiện `ROLLBACK` và xác nhận quantity ban đầu không đổi.

### Bài 2 — Lỗi SELECT cũng làm transaction failed

Chạy `BEGIN; SELECT 'bad'::integer; SELECT 2; ROLLBACK;`. Giải thích tại sao câu `SELECT 2` nhận `25P02` dù không thay đổi dữ liệu.

### Bài 3 — Autocommit và explicit transaction

So sánh kết quả khi chạy lỗi `'bad'::integer` ở hai trường hợp: ngoài `BEGIN` và trong `BEGIN`. Tại sao câu SQL sau có thể chạy được ở trường hợp thứ nhất nhưng bị từ chối ở trường hợp thứ hai?

### Bài 4 — COMMIT sau failed transaction

Trong lab, thay đổi số lượng trước khi tạo lỗi. Sau lỗi, thử `COMMIT` thay `ROLLBACK`; quan sát phản hồi của PostgreSQL và kiểm tra dữ liệu. Giải thích vì sao câu `UPDATE` báo thành công nhưng không được commit.

### Bài 5 — ROLLBACK TO SAVEPOINT

Viết giao dịch có hai bước: giảm tồn kho bắt buộc, chèn record tùy chọn có thể trùng SKU. Tạo savepoint trước phần tùy chọn, nếu lỗi thì `ROLLBACK TO SAVEPOINT`, rồi ghi audit và commit. Chỉ dùng lab, giải thích lý do nghiệp vụ nào cho phép bỏ bước tùy chọn.

### Bài 6 — RELEASE SAVEPOINT

Giải thích vì sao `RELEASE SAVEPOINT` không commit dữ liệu, và tại sao không dùng riêng `RELEASE` để cứu một transaction đã nhận `23505`.

### Bài 7 — Savepoint nhiều tầng

Tạo `SAVEPOINT s1`, `SAVEPOINT s2` rồi `ROLLBACK TO s2` và `ROLLBACK TO s1` trong transaction lab. Phân biệt thao tác nào được giữ ở mỗi mốc.

### Bài 8 — Phân tích chuỗi SQLSTATE

Log một request gồm `23503`, ba lần `25P02` và một lỗi rollback do mất kết nối. Xác định lỗi gốc cần ưu tiên điều tra, trạng thái connection và vì sao không thể kết luận rollback thành công khi network đã mất.

### Bài 9 — Đọc pg_stat_activity

Dùng hai session PostgreSQL trong lab: session A tạo transaction failed và để mở; session B dùng `pg_stat_activity` tìm `idle in transaction (aborted)`. Ghi backend PID và thời điểm `state_change`. Sau đó rollback ở A.

### Bài 10 — psql ON_ERROR_ROLLBACK

Trong `psql`, thử bật `\set ON_ERROR_ROLLBACK on` rồi tạo một lỗi `SELECT 1/0` giữa transaction. So sánh khả năng tiếp tục câu lệnh sau với chế độ mặc định, và giải thích vì sao JDBC không tự kế thừa biến này.

### Bài 11 — Script migration

Thiết kế cách chạy file `migration.sql` với `-v ON_ERROR_STOP=1 --single-transaction`. Tại sao chỉ dùng `ON_ERROR_STOP` mà không có transaction bao quanh có thể vẫn để lại các thay đổi đã commit từ trước?

### Bài 12 — Constraint deferred

Tạo bảng có unique `DEFERRABLE INITIALLY DEFERRED` trong lab, chèn hai bản ghi cùng key rồi `COMMIT`. Giải thích vì sao có thể chỉ phát hiện lỗi tại commit, và code Java phải kiểm tra cả kết quả `commit()`.

### Bài 13 — JDBC rollback

Viết một method JDBC bật `setAutoCommit(false)`, thực hiện hai update/insert, commit khi thành công, rollback trong `catch(SQLException | RuntimeException)`. Khi rollback lỗi, hãy giữ lỗi gốc và đính kèm rollback exception.

### Bài 14 — JDBC Savepoint

Dùng `Connection.setSavepoint`, gây lỗi `23505` ở bước tùy chọn, gọi `rollback(savepoint)` rồi tiếp tục update ở transaction ngoài. Giải thích tại sao không được bỏ qua mọi `SQLException` mà không phân loại.

### Bài 15 — Spring và lỗi bị nuốt

Phân tích method `@Transactional` có `try/catch(DataAccessException)` rồi chạy tiếp một repository call. Những hiện tượng nào có thể xảy ra ở PostgreSQL và transaction manager? Thiết kế lại để lỗi dẫn tới rollback hoặc được xử lý bằng savepoint/upsert hợp lệ.

### Bài 16 — Retry serialization failure

Viết pseudocode retry khi `getSQLState() == "40001"`. Mỗi lần thử phải tạo transaction mới, đọc lại dữ liệu và tính lại quyết định. Giới hạn số lần, thêm backoff và giải thích rủi ro gửi email bên trong vòng retry.

### Bài 17 — Deadlock

Mô tả hai transaction lần lượt lock account 1 rồi account 2 theo thứ tự ngược nhau. Khi PostgreSQL phát hiện deadlock `40P01`, vì sao không thể chỉ retry statement đang chờ trong cùng transaction bị chọn làm nạn nhân?

### Bài 18 — Timeout và query cancel

Trong lab, chạy `BEGIN; SET LOCAL statement_timeout = '100ms'; SELECT pg_sleep(1);`. Quan sát lỗi và trạng thái của câu `SELECT 1` sau đó. Khi nào phải rollback, và tình huống mất connection khác thế nào?

### Bài 19 — ON CONFLICT

Viết `INSERT ... ON CONFLICT (sku) DO NOTHING` cho product có SKU trùng. So sánh với `INSERT` thông thường gây `23505` trong transaction. Khi nào bỏ qua conflict là một quyết định nghiệp vụ hợp lệ?

### Bài 20 — PL/pgSQL EXCEPTION

Tạo function có `EXCEPTION WHEN unique_violation`, cố chèn SKU trùng, rồi trả một status text. Gọi trong `BEGIN`, sau đó chạy một câu `SELECT` khác. Giải thích khác biệt giữa server-side exception block và Java `catch`.

### Bài 21 — Phân biệt rollback database với side effect

Một transaction ghi DB và gửi email cho khách, rồi gặp lỗi và rollback. Email có tự biến mất không? Đề xuất giao thức transactional outbox hoặc cách đảm bảo gửi idempotent.

### Bài 22 — Mất mạng ở COMMIT

Client gửi `COMMIT` rồi mất kết nối trước khi nhận phản hồi. Phân tích hai khả năng server đã commit hoặc chưa commit và thiết kế idempotency key để retry nghiệp vụ mà không tạo trùng.

### Bài 23 — Connection pool

Một request tạo `23505` rồi trả connection về pool mà không rollback. Mô tả cách request sau có thể nhận `25P02`, chỉ ra trách nhiệm của transaction owner và vai trò phòng vệ của pool.

### Bài 24 — Phân loại lỗi có thể retry

Với các SQLSTATE `23505`, `23503`, `40001`, `40P01`, `57014`, `25P02` và `08006`, hãy đề xuất chính sách xử lý riêng: rollback, trả lỗi nghiệp vụ, retry toàn bộ transaction, kiểm tra connection hoặc đối soát trạng thái commit. Giải thích vì sao không có chính sách “retry mọi lỗi” hợp lệ.

## Kết luận

Trong PostgreSQL, lỗi SQL xảy ra giữa **giao dịch tường minh** thường làm giao dịch chuyển sang **failed/aborted**, và câu lệnh sau sẽ nhận **SQLSTATE `25P02`** thay vì được xử lý bình thường. Cần tìm **lỗi đầu tiên** như `23505`, `23503`, `22P02`, `40001` hoặc `57014` để xác định nguyên nhân, không chỉ sửa câu lệnh cuối cùng báo `25P02`.

**`ROLLBACK` là phương án phục hồi mặc định** khi transaction không còn có thể hoàn tất hợp lệ. Nếu một bước riêng có thể thất bại theo chính sách nghiệp vụ, **`SAVEPOINT` được tạo trước bước đó** cùng `ROLLBACK TO SAVEPOINT` cho phép hủy phần công việc có lỗi rồi tiếp tục trong cùng transaction. `RELEASE SAVEPOINT` không phải commit độc lập; `COMMIT` sau aborted transaction không cứu các thay đổi trước lỗi.

Ở tầng ứng dụng, **bắt exception không thay thế rollback**. JDBC cần `rollback()` trong xử lý thất bại; Spring cần transaction propagation và quy tắc rollback phù hợp; `psql ON_ERROR_ROLLBACK` chỉ là tiện ích client. Lỗi đồng thời như `40001`/`40P01` thường cần **retry toàn bộ transaction mới**, có giới hạn và bảo đảm idempotency. Khi mất mạng trong lúc commit, kết quả có thể chưa biết chắc, nên cần đối soát thay vì mặc định đã rollback.

Quy trình bền vững là **xác định ranh giới transaction, ghi nhận lỗi gốc, rollback đúng cấp, không tiếp tục trên connection aborted, và chỉ bắt đầu công việc mới khi trạng thái đã rõ ràng**. Đó là nền tảng để các ứng dụng PostgreSQL duy trì tính nguyên tử, tránh lỗi dây chuyền `25P02` và xử lý sự cố giao dịch một cách an toàn.
