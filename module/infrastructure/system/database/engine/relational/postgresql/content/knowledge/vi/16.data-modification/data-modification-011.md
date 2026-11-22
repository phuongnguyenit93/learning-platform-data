# Tính lặp an toàn, khóa duy nhất và tránh ghi trùng khi thử lại trong PostgreSQL

Trong hệ thống thật, một yêu cầu ghi dữ liệu có thể được gửi **nhiều lần dù người dùng chỉ thực hiện một hành động**. Kết nối mạng bị ngắt sau khi database đã commit, client không nhận được phản hồi, gateway tự retry, worker nhận lại thông điệp, hoặc người dùng bấm nút thanh toán lần nữa. Nếu câu SQL được thiết kế như một lần ghi mới ở mỗi lần gọi, hệ thống có thể tạo **hai đơn hàng, trừ kho hai lần, cộng điểm hai lần hoặc phát hai sự kiện**.

Bài toán cốt lõi là **idempotency (tính lặp an toàn)**: khi cùng một yêu cầu hợp lệ được thực hiện lại, tác động nghiệp vụ quan sát được **không bị nhân lên**. PostgreSQL hỗ trợ xây dựng cơ chế này nhờ khóa duy nhất (`PRIMARY KEY`, `UNIQUE`, unique index), `INSERT ... ON CONFLICT`, transaction, điều kiện cập nhật, khóa hàng và `RETURNING`.

Sau bài này, bạn sẽ biết:

- Phân biệt **retry**, **idempotency**, **deduplication** và **exactly-once**.
- Xác định **business key** và **idempotency key** cùng phạm vi duy nhất.
- Dùng `UNIQUE`/`ON CONFLICT DO NOTHING` để chặn tạo hàng trùng khi hai phiên chạy đồng thời.
- Hiểu `ON CONFLICT DO UPDATE` phù hợp trường hợp nào và vì sao nó có thể **làm sai idempotency**.
- Phát hiện cùng idempotency key nhưng **nội dung request khác nhau**.
- Thiết kế transaction PostgreSQL gồm tạo đơn, lưu kết quả idempotency và ghi transactional outbox.
- Làm việc với `RETURNING` trả 0 hàng, xung đột concurrent transaction, isolation và retry sau lỗi.
- Tránh lặp thao tác không idempotent như `SET quantity = quantity - 3`.
- Kiểm thử các lần gửi lại bằng dữ liệu lab và các tình huống giả lập hai phiên.

## 1. Vì sao request có thể thực thi thành công nhưng client vẫn retry?

Giả sử ứng dụng tạo đơn:

~~~text
1. Client gửi POST /orders, request_id = "req-A".
2. Server INSERT orders.
3. PostgreSQL COMMIT thành công.
4. Server gửi HTTP 201 nhưng kết nối bị ngắt.
5. Client tưởng không thành công và gửi lại req-A.
6. Nếu không chống trùng: server INSERT một đơn thứ hai.
~~~

Trong bước 5, client **không biết chắc** lần đầu đã được commit hay chưa. Retry là một cách thông thường để đạt khả năng phục hồi khi có lỗi tạm thời; vấn đề nằm ở phía nhận phải xử lý các lần gọi lặp một cách an toàn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant D as PostgreSQL
    C->>S: Tạo đơn, key=req-A
    S->>D: INSERT đơn
    D-->>S: COMMIT thành công
    S--xC: Phản hồi bị mất
    C->>S: Gửi lại key=req-A
    S->>D: Tra key và kết quả đã lưu
    D-->>S: Đơn đã tạo ở lần đầu
    S-->>C: Trả kết quả cũ, không tạo đơn thứ hai
~~~

**Không thể dựa vào việc “client chỉ bấm một lần”**. Yêu cầu có thể được phát lại bởi gateway, job scheduler, consumer queue, SDK hoặc logic retry tự động. Hệ thống ghi dữ liệu phải định nghĩa rõ điều gì được xem là **cùng một thao tác nghiệp vụ**.

## 2. Phân biệt các khái niệm dễ bị nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Retry** | Thực hiện lại lời gọi sau lỗi hoặc không rõ kết quả | POST cùng nội dung lần thứ hai |
| **Idempotency** | Lặp lại cùng thao tác không làm tăng thêm hiệu ứng nghiệp vụ | Hai POST với cùng key dẫn tới một đơn |
| **Deduplication** | Phát hiện và loại/không xử lý bản ghi trùng | Unique index chặn hai hàng cùng khóa |
| **Business key** | Định danh nghiệp vụ vốn đã có ý nghĩa duy nhất | Mã đơn của tenant |
| **Idempotency key** | Định danh của **một yêu cầu logic**, được giữ nguyên khi retry | `req-5ec...` |
| **Atomicity** | Tất cả thay đổi trong transaction commit cùng nhau hoặc rollback | Đơn + outbox cùng commit |
| **Exactly-once** | Khái niệm end-to-end khó hơn dedupe database; phụ thuộc nhiều hệ thống | Không phát hai hiệu ứng thanh toán ở nhà cung cấp ngoài |

Tính idempotent thường được mô tả bằng phép toán:

~~~text
apply(request, state)
apply(request, apply(request, state))

Hai cách phải có cùng hiệu ứng nghiệp vụ quan sát được
đối với cùng một logical request.
~~~

Lưu ý: **kết quả HTTP trả về không nhất thiết giống từng byte** nếu hợp đồng API định nghĩa lần đầu trả `201 Created` và lần retry trả `200 OK`. Nhưng **đơn hàng hoặc khoản thanh toán nghiệp vụ** không được tạo mới lần thứ hai. Nếu hợp đồng yêu cầu replay nguyên status/body, phải lưu các thông tin phản hồi để trả lại nhất quán.

## 3. Phân loại thao tác SQL theo tính lặp an toàn

Không phải mọi câu SQL đều idempotent:

| Thao tác | Khi chạy hai lần | Idempotent theo hiệu ứng dữ liệu? |
| --- | --- | --- |
| `UPDATE t SET status = 'paid' WHERE id = 1` | Trạng thái cuối đều paid | Thường có, nhưng vẫn có thể sinh hai lần trigger/audit |
| `UPDATE t SET stock = stock - 3 WHERE id = 1` | Trừ 6 thay vì 3 | **Không** |
| `UPDATE t SET points = points + 10 WHERE id = 1` | Cộng 20 thay vì 10 | **Không** |
| `DELETE FROM t WHERE id = 1` | Hàng chỉ bị xóa một lần | Trạng thái bảng thường idempotent; side effect cần xét thêm |
| `INSERT INTO orders ...` | Có thể sinh hai hàng | **Không**, nếu không có khóa chống trùng |
| `INSERT ... ON CONFLICT DO NOTHING` | Lần sau không thêm hàng trên khóa xung đột | Thường idempotent về số hàng được chèn, cần xét payload |
| `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1` | Tăng count mỗi lần | **Không** |
| `INSERT ... ON CONFLICT DO UPDATE SET status = EXCLUDED.status` | Trạng thái cuối giống nhau | Có thể idempotent về giá trị, nhưng vẫn gây update side effect |

Điểm mấu chốt: **“Giá trị cuối cùng không đổi” không có nghĩa mọi hiệu ứng đều chỉ xảy ra một lần**. Một UPDATE lặp có thể tăng version, cập nhật `updated_at`, tạo WAL, kích hoạt trigger hoặc sinh event. Nếu muốn một lần phát sự kiện, cần ràng buộc rõ **chỉ hành động đầu được ghi nhận**.

## 4. Business key và idempotency key phục vụ hai mục tiêu khác nhau

Một đơn hàng có thể có:

- `order_id`: khóa kỹ thuật do PostgreSQL sinh.
- `(tenant_id, client_order_code)`: khóa nghiệp vụ duy nhất trong phạm vi tenant.
- `(tenant_id, operation, idempotency_key)`: định danh **lần yêu cầu logic** mà client có thể gửi lại.

Ví dụ:

~~~text
tenant_id         = 10
client_order_code = WEB-2026-001
idempotency_key   = 12f6c1ba-... (sinh cho lần create)
operation         = create_order
~~~

Một key được tạo mới cho **mỗi yêu cầu mới**, nhưng **phải giữ nguyên khi retry cùng yêu cầu**. Nếu client sinh key khác cho mỗi lần retry, server không có cách dùng key đó để nhận biết chúng là cùng thao tác.

### Vì sao vẫn cần business key?

Hai request với **hai idempotency key khác nhau** có thể cố tạo cùng một đơn nghiệp vụ `WEB-2026-001`. Khóa unique theo business code vẫn bảo vệ không có hai đơn giống nhau trong phạm vi tenant.

Ngược lại, một idempotency key có thể cần bảo vệ những thao tác không gắn với một hàng business key dễ suy ra, ví dụ gửi một yêu cầu cấp điểm, một lần đặt giữ chỗ hoặc tạo nhiều bản ghi liên quan.

**Khóa nghiệp vụ** bảo vệ tính duy nhất của đối tượng; **idempotency key** bảo vệ việc xử lý lại một yêu cầu.

## 5. Chuẩn bị schema thực hành

Toàn bộ ví dụ sử dụng **database lab riêng** và schema `retry_lab`. Script này **xóa toàn bộ schema `retry_lab` nếu đã tồn tại**, nên không chạy trên database dùng chung hoặc dữ liệu cần giữ.

### 5.1. Tạo bảng orders, request và outbox

~~~sql
-- CẢNH BÁO: chỉ chạy trong database lab do bạn sở hữu.
DROP SCHEMA IF EXISTS retry_lab CASCADE;
CREATE SCHEMA retry_lab;

CREATE TABLE retry_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    client_order_code text NOT NULL,
    amount numeric(14, 2) NOT NULL CHECK (amount >= 0),
    currency text NOT NULL CHECK (currency IN ('VND', 'USD')),
    status text NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'paid', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_orders_tenant_code
        UNIQUE (tenant_id, client_order_code),
    CONSTRAINT chk_order_code_nonblank
        CHECK (btrim(client_order_code) <> '')
);

CREATE TABLE retry_lab.idempotency_requests (
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    operation text NOT NULL,
    idempotency_key text NOT NULL,
    request_payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'processing'
        CHECK (state IN ('processing', 'completed')),
    order_id bigint REFERENCES retry_lab.orders(order_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,

    PRIMARY KEY (tenant_id, operation, idempotency_key),
    CHECK (btrim(idempotency_key) <> ''),
    CHECK (
        (state = 'processing'
            AND order_id IS NULL
            AND completed_at IS NULL)
        OR
        (state = 'completed'
            AND order_id IS NOT NULL
            AND completed_at IS NOT NULL)
    )
);

CREATE TABLE retry_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    order_id bigint NOT NULL
        REFERENCES retry_lab.orders(order_id),
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,

    CONSTRAINT uq_event_per_order
        UNIQUE (tenant_id, order_id, event_type)
);

CREATE TABLE retry_lab.inventory (
    product_id integer PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE retry_lab.stock_deductions (
    product_id integer NOT NULL
        REFERENCES retry_lab.inventory(product_id),
    operation_key text NOT NULL,
    deduct_quantity integer NOT NULL CHECK (deduct_quantity > 0),
    remaining_quantity integer,
    created_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (product_id, operation_key),
    CHECK (remaining_quantity IS NULL OR remaining_quantity >= 0)
);

INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 8), (502, 0);
~~~

Giải thích các constraint:

| Bảng | Ràng buộc quan trọng | Bất biến được bảo vệ |
| --- | --- | --- |
| `orders` | `UNIQUE (tenant_id, client_order_code)` | Không có hai đơn cùng mã trong một tenant |
| `idempotency_requests` | `PRIMARY KEY (tenant_id, operation, idempotency_key)` | Một key không được đại diện cho hai yêu cầu cùng operation/tenant |
| `idempotency_requests` | `state/order_id/completed_at CHECK` | Hàng completed phải có kết quả và thời điểm |
| `outbox_events` | `UNIQUE (tenant_id, order_id, event_type)` | Không ghi hai event cùng loại cho một đơn |
| `inventory` | `CHECK(quantity >= 0)` | Không lưu tồn kho âm |
| `stock_deductions` | `PRIMARY KEY(product_id, operation_key)` | Một request trừ kho cho sản phẩm chỉ có một bản ghi chống trùng |

Các cột `state = 'processing'` trong bài được dùng trong **một transaction chưa commit** rồi đổi thành `completed` trước khi commit. Bảng vẫn cho phép một hàng processing được tạo qua thao tác khác; trong hệ thống thật cần quy tắc recovery cho các hàng processing đã commit. Hàm mẫu ở phần sau không chủ động commit trạng thái processing dở dang.

## 6. Duy nhất trong phạm vi nào?

Nếu `idempotency_key = 'abc'` đến từ hai tenant khác nhau, đó có thể là **hai yêu cầu hợp lệ độc lập**. Vì vậy, khóa:

~~~sql
PRIMARY KEY (tenant_id, operation, idempotency_key)
~~~

cho phép tenant 10 và tenant 20 cùng có key `abc`, nhưng không cho tenant 10 xử lý **hai request `create_order` khác nhau** với cùng key `abc`.

Nếu endpoint tạo đơn và endpoint hủy đơn dùng cùng chuỗi key, cột `operation` giúp chúng không đè nhau. Có hệ thống dùng một key duy nhất toàn account/API; có hệ thống dùng namespace riêng cho từng endpoint. **Hãy ghi rõ quy tắc scope trong hợp đồng API.**

### Đừng dùng chuỗi rỗng hoặc giá trị mặc định làm key

Nếu mọi request thiếu key được biến thành `''`, chúng sẽ xung đột với nhau hoặc dễ bị nhận là retry sai. Trong thiết kế lab, `idempotency_key` là `NOT NULL` và có CHECK không rỗng sau khi trim.

Trong API thật, key nên có độ dài tối đa, được ràng buộc với danh tính người gọi/tenant và có đủ tính ngẫu nhiên để khó đoán. Đừng tin `tenant_id` lấy trực tiếp từ request mà không xác thực quyền của client đối với tenant đó.

## 7. Vì sao SELECT trước INSERT không chống được race condition?

Một cách phổ biến nhưng **không an toàn khi nhiều phiên đồng thời**:

~~~sql
-- Mẫu nguy hiểm nếu không có constraint đúng:
SELECT order_id
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-001';

-- Nếu không thấy thì...
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND');
~~~

Có thể xảy ra:

~~~text
Phiên A                         Phiên B
---------------------------     ---------------------------
SELECT: chưa có WEB-001         SELECT: chưa có WEB-001
INSERT WEB-001                  INSERT WEB-001
COMMIT                          COMMIT
~~~

Nếu **không có unique constraint**, cả hai phiên có thể commit và tạo hai đơn.

Nếu **có unique constraint**, một phiên sẽ không thể commit thêm hàng trùng khóa: PostgreSQL phối hợp kiểm tra duy nhất qua cơ chế index/concurrency. Phiên thua có thể phải chờ rồi nhận lỗi vi phạm unique (SQLSTATE `23505`) nếu dùng INSERT thường.

**Kết luận:** kiểm tra trước bằng `SELECT` giúp hiểu nghiệp vụ nhưng không thay thế `UNIQUE` ở database. Constraint là tuyến phòng vệ quyết định khi có nhiều worker/API instance.

## 8. INSERT ... ON CONFLICT DO NOTHING

PostgreSQL cung cấp cú pháp upsert để xử lý xung đột khóa duy nhất:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id, tenant_id, client_order_code;
~~~

Lần đầu, một hàng được chèn và `RETURNING` trả ID của đơn mới.

Nếu chạy lại cùng câu:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;
~~~

kết quả là **0 hàng**, bởi khóa `(tenant_id, client_order_code)` đã tồn tại.

Thử không để lại dữ liệu:

~~~sql
BEGIN;

INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

SELECT COUNT(*) AS matching_orders
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-001';

ROLLBACK;
~~~

Trong transaction, số đơn trùng business code là **1**. Câu INSERT đầu trả ID; câu thứ hai không trả hàng; sau rollback database trở lại trạng thái ban đầu.

### ON CONFLICT (columns) dùng constraint nào?

`ON CONFLICT (tenant_id, client_order_code)` yêu cầu PostgreSQL suy ra unique index/constraint phù hợp để làm **arbiter**. Nó không có nghĩa có thể dùng một tổ hợp cột bất kỳ chưa được bảo vệ uniqueness.

Có thể viết:

~~~sql
ON CONFLICT ON CONSTRAINT uq_orders_tenant_code DO NOTHING
~~~

nếu muốn chỉ định tên unique constraint đã khai báo. Cách nêu cột thường thuận tiện khi tên constraint thay đổi nhưng đặc tính uniqueness được giữ; cách nêu tên diễn đạt cụ thể constraint được dùng.

## 9. DO NOTHING vẫn có thể che yêu cầu sai nội dung

Giả sử lần đầu:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-002', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code) DO NOTHING;
~~~

Lần sau client dùng **cùng mã đơn nhưng số tiền khác**:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-002', 999.00, 'VND')
ON CONFLICT (tenant_id, client_order_code) DO NOTHING;
~~~

Lần thứ hai bị bỏ qua mà **không báo rằng request khác nội dung lần đầu**. Điều này có thể gây nguy hiểm nếu ứng dụng lầm tưởng 999.00 đã được lưu hoặc trả thành công theo payload mới.

Vì thế một cơ chế idempotency hoàn chỉnh cần:

1. **Chống tạo hàng trùng**, thường qua UNIQUE.
2. **Nhận diện yêu cầu lặp với cùng nội dung**, bằng dữ liệu canonical hoặc fingerprint.
3. **Từ chối reuse key với payload khác**, thường là lỗi xung đột nghiệp vụ (ví dụ HTTP 409 theo hợp đồng API).
4. **Trả đúng kết quả lần đầu**, không tự tạo một kết quả mới từ request có nội dung khác.

**Chống trùng hàng không tự đồng nghĩa xác thực tính tương đương của hai request.**

## 10. DO UPDATE: Upsert có thể hữu ích nhưng phải đúng ý nghĩa

`ON CONFLICT DO UPDATE` cho phép cập nhật hàng đã tồn tại:

~~~sql
INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 20)
ON CONFLICT (product_id)
DO UPDATE
SET quantity = EXCLUDED.quantity
RETURNING product_id, quantity;
~~~

Với mẫu này, dù chạy hai lần, giá trị cuối của sản phẩm 501 là **20**. Tuy nhiên trong lab, nếu thử trên dữ liệu 8, hãy bọc câu lệnh bằng `BEGIN ... ROLLBACK` để không ảnh hưởng các bài khác.

`EXCLUDED` là hàng ứng viên được đưa vào INSERT nhưng vướng xung đột; giá trị như `EXCLUDED.quantity` là **giá trị từ request INSERT**.

### Bẫy: phép cộng trong DO UPDATE không idempotent

~~~sql
-- Không an toàn nếu đây là một request có thể retry.
INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 3)
ON CONFLICT (product_id)
DO UPDATE
SET quantity = retry_lab.inventory.quantity + EXCLUDED.quantity;
~~~

Nếu sản phẩm 501 đã tồn tại, mỗi lần gọi đều **tăng thêm 3**. Retry làm tăng 6, 9, 12... chứ không bảo đảm “một lần nhập kho”.

Tương tự:

~~~sql
ON CONFLICT (account_id)
DO UPDATE
SET points = accounts.points + EXCLUDED.points
~~~

không có khả năng chống lặp cho thao tác cộng điểm. Muốn một lần cộng theo một request, cần ledger/movement có khóa unique của operation và transaction kiểm soát thay đổi số dư.

## 11. Tránh no-op UPDATE khi dùng upsert

Một số ứng dụng dùng `DO UPDATE` chỉ để có thể `RETURNING` hàng cũ:

~~~sql
-- Không khuyến nghị dùng làm mẹo idempotency mặc định.
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-003', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE
SET client_order_code = EXCLUDED.client_order_code
RETURNING order_id;
~~~

Nó có thể trả `order_id` của hàng hiện có, nhưng nhánh UPDATE vẫn có thể:

- Tạo phiên bản hàng mới và WAL.
- Kích hoạt UPDATE trigger, audit hoặc logic version.
- Gây thêm lock contention.
- Che một payload khác số tiền so với bản ghi cũ.

Không coi “gán lại giá trị bằng chính nó” là thao tác hoàn toàn vô hại.

Với các upsert nghiệp vụ thực sự cho phép cập nhật, có thể chỉ UPDATE khi giá trị khác:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-003', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE
SET
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency
WHERE
    retry_lab.orders.amount IS DISTINCT FROM EXCLUDED.amount
    OR retry_lab.orders.currency IS DISTINCT FROM EXCLUDED.currency
RETURNING order_id, amount, currency;
~~~

**Nhưng:** ví dụ này mang ngữ nghĩa **cho phép sửa đơn đã tồn tại**. Với endpoint **create-once**, việc retry bằng số tiền khác phải **bị từ chối**, không được âm thầm sửa đơn. `WHERE` ở DO UPDATE không tự là cơ chế so khớp request ban đầu cho idempotency.

## 12. RETURNING sau ON CONFLICT có nghĩa gì?

| Tình huống | Câu lệnh | Kết quả RETURNING |
| --- | --- | --- |
| Chèn mới thành công | INSERT ... RETURNING | Hàng mới |
| Trùng và `DO NOTHING` | INSERT ... ON CONFLICT DO NOTHING RETURNING | **0 hàng** |
| Trùng và `DO UPDATE` thực sự chạy | INSERT ... ON CONFLICT DO UPDATE RETURNING | Hàng sau UPDATE |
| Trùng và nhánh DO UPDATE có `WHERE` không thỏa | INSERT ... DO UPDATE ... WHERE ... RETURNING | **0 hàng** |
| Xung đột UNIQUE khác không được nhánh ON CONFLICT xử lý | Câu INSERT/UPSERT | Có thể báo `23505` |

Vì vậy, **0 hàng không có nghĩa database lỗi**. Nó có thể nghĩa “đã có request”, “không cần UPDATE” hoặc “không thỏa WHERE”. Ứng dụng cần tra lại record đã lưu và kiểm tra payload để xác định phản hồi nghiệp vụ.

## 13. Quy tắc concurrency của unique index

Unique index không chỉ kiểm tra trạng thái dữ liệu đã commit ở đầu statement. Khi hai phiên cùng muốn chèn một khóa, PostgreSQL phối hợp xung đột với transaction chưa commit.

Ví dụ:

~~~text
Phiên A                               Phiên B
---------------------------------    ------------------------------
BEGIN;
INSERT key=(10, WEB-004);            BEGIN;
                                     INSERT key=(10, WEB-004)
                                     -- có thể phải chờ A
COMMIT;
                                     -- ON CONFLICT DO NOTHING: 0 hàng
                                     COMMIT;
~~~

Nếu A rollback thay vì commit, B có thể tiếp tục chèn khóa đó. Nếu A commit, B không chèn thêm hàng cùng khóa.

Đây là lý do **UNIQUE + ON CONFLICT** mạnh hơn chỉ gọi `SELECT` để kiểm tra trước: uniqueness được đảm bảo khi có ghi đồng thời, không chỉ khi hai phiên chạy tuần tự.

### Snapshot trong READ COMMITTED có một điểm tinh tế

Ở mức `READ COMMITTED`, `INSERT ... ON CONFLICT DO NOTHING` có thể quyết định **không chèn vì một transaction khác đã chèn và commit**, dù hàng đó **không thấy được bởi snapshot của phần SELECT ở cùng statement**.

Do đó một mẫu cố gộp INSERT với “nếu không insert thì SELECT existing” trong cùng statement bằng `UNION ALL` có thể **trả 0 hàng ở một cuộc đua hiếm**.

Nếu cần lấy kết quả đã tồn tại sau khi `DO NOTHING RETURNING` trả 0 hàng, cách dễ hiểu là:

1. Kết thúc statement INSERT.
2. Dùng **một SELECT statement mới** ở `READ COMMITTED` để đọc hàng đã commit.
3. So sánh payload, rồi trả kết quả hoặc lỗi conflict.
4. Nếu đang ở isolation khác hoặc gặp serialization failure, xử lý retry transaction theo chính sách.

Không nên tin vào “một CTE sẽ luôn nhìn thấy record thắng cuộc” trong mọi tình huống concurrency.

## 14. Tại sao unique key thường phải NOT NULL?

Trên PostgreSQL, unique constraint truyền thống cho phép **nhiều giá trị NULL** trong một hoặc nhiều cột khóa, vì mặc định những giá trị NULL được xem là khác nhau cho mục đích uniqueness.

Ví dụ minh họa:

~~~sql
CREATE TABLE retry_lab.null_unique_demo (
    demo_id integer PRIMARY KEY,
    external_reference text UNIQUE
);

INSERT INTO retry_lab.null_unique_demo
    (demo_id, external_reference)
VALUES
    (1, NULL),
    (2, NULL);
~~~

Hai hàng có `external_reference NULL` đều được chấp nhận ở unique constraint mặc định. Nếu ứng dụng dùng NULL làm idempotency key khi client không gửi key, uniqueness có thể **không bảo vệ được trùng lặp như mong đợi**.

Với idempotency key, dùng:

~~~sql
idempotency_key text NOT NULL
~~~

và kiểm tra giá trị không rỗng.

### NULLS NOT DISTINCT từ PostgreSQL 15

PostgreSQL **15 trở lên** hỗ trợ unique constraint/index với `NULLS NOT DISTINCT`, khiến các NULL được coi là không phân biệt đối với uniqueness:

~~~sql
-- PostgreSQL 15+
CREATE TABLE retry_lab.one_nullable_reference (
    reference_code text UNIQUE NULLS NOT DISTINCT
);
~~~

Khi đó chỉ có thể có tối đa một hàng với `reference_code IS NULL` theo constraint này.

Tính năng hữu ích cho một số khóa nghiệp vụ nullable, nhưng **không phải lý do tốt để cho phép idempotency key vắng mặt**. Với operation cần retry an toàn, nên yêu cầu key có giá trị rõ ràng từ phía client/producer.

## 15. Không phải mọi uniqueness đều là cùng một hợp đồng

PostgreSQL có:

- `PRIMARY KEY`: unique và NOT NULL cho cột khóa.
- `UNIQUE`: giới hạn trùng trên cột/nhóm cột.
- Unique index: có thể bảo vệ biểu thức, điều kiện partial và những lựa chọn nâng cao.
- `UNIQUE NULLS NOT DISTINCT`: hỗ trợ NULL theo quy tắc khác từ phiên bản 15.

Ví dụ muốn email không phân biệt chữ hoa/thường theo quy tắc ứng dụng:

~~~sql
CREATE TABLE retry_lab.accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL
);

CREATE UNIQUE INDEX uq_accounts_email_lower
ON retry_lab.accounts (lower(email));
~~~

Unique index trên `lower(email)` bảo vệ một dạng khóa chuẩn hóa. Nhưng nó **không** cho phép suy ra rằng mọi địa chỉ email trên thế giới phải được gộp theo `lower()`; quy tắc danh tính và collation phải do nghiệp vụ quyết định.

Với idempotency key, cần nhất quán về có phân biệt chữ hoa/chữ thường hay không. Nếu quy định key phân biệt byte/chữ, đừng tự thay đổi `lower()` mà không có hợp đồng API rõ ràng.

## 16. ON CONFLICT không xử lý mọi lỗi ghi dữ liệu

`ON CONFLICT` được thiết kế cho xung đột khóa unique/exclusion theo những nhánh hỗ trợ của cú pháp, **không có nghĩa “nếu INSERT có bất kỳ lỗi nào thì bỏ qua”**.

Các lỗi vẫn có thể xảy ra:

- Vi phạm `NOT NULL` hoặc `CHECK`.
- Vi phạm foreign key.
- Vi phạm uniqueness của một constraint khác không được xử lý.
- Không có quyền INSERT/UPDATE/SELECT cần thiết.
- Deadlock hoặc serialization failure.
- Lỗi từ trigger hoặc expression.
- Giá trị không chuyển được sang kiểu cột.

Với `DO UPDATE`, PostgreSQL cần một conflict target phù hợp; việc suy ra arbiter phải tuân các quy tắc unique index/constraint. **Deferrable unique constraint không được dùng làm arbiter cho ON CONFLICT DO UPDATE** theo cơ chế hỗ trợ của PostgreSQL. Một số mô hình uniqueness phức tạp (partial unique index, exclusion constraint, partitioned table) có quy tắc riêng cần đọc tài liệu phiên bản đang dùng.

### Batch INSERT chứa trùng khóa với chính nó

~~~sql
-- Ví dụ cần tránh: cùng business key hai lần trong VALUES.
INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'WEB-X', 100.00, 'VND'),
    (10, 'WEB-X', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

Một statement `ON CONFLICT DO UPDATE` không được tác động **cùng một hàng đích nhiều lần**, nên có thể báo lỗi cardinality violation (`21000`). Trước khi bulk upsert, hãy làm sạch/dedupe dữ liệu nguồn theo khóa và xác định rõ bản ghi ưu tiên khi nội dung trùng khác nhau.

## 17. Lưu fingerprint hoặc payload để nhận biết retry đúng nghĩa

Một idempotency key phải được gắn với **nội dung yêu cầu đã được chuẩn hóa**. Nếu cùng key nhưng một lần yêu cầu số tiền 100 và lần sau 900, đó không thể được xử lý như cùng một request hợp lệ.

Hai cách lưu:

1. **Payload canonical**: lưu JSONB hoặc những trường nghiệp vụ quyết định tính tương đương.
2. **Fingerprint/hash**: tạo từ biểu diễn canonical của request; so sánh hash nhưng cần chọn thuật toán, cách chuẩn hóa và xử lý nguy cơ collision hợp lý.

Trong bài lab, bảng `idempotency_requests.request_payload jsonb` lưu một đối tượng JSONB gồm:

~~~json
{
  "client_order_code": "WEB-100",
  "amount": 120.00,
  "currency": "VND"
}
~~~

Khi retry, server xây cùng cấu trúc và so sánh với giá trị đã lưu bằng `IS DISTINCT FROM` hoặc toán tử bằng phù hợp.

### Vì sao cần chuẩn hóa?

Hai request về mặt nghiệp vụ có thể giống nhau nhưng khác biểu diễn:

~~~text
currency: "vnd" vs "VND"
amount: 120 vs 120.00
key order: {"amount":120,"currency":"VND"}
           vs {"currency":"VND","amount":120}
~~~

Nếu API coi chúng tương đương, hệ thống phải quy định chuẩn hóa **trước khi so sánh**. PostgreSQL `jsonb` có quy tắc biểu diễn và so sánh object khác văn bản JSON thô; tuy nhiên mọi vấn đề nghiệp vụ (đơn vị tiền, Unicode, trường mặc định, dữ liệu bí mật) vẫn cần được định nghĩa rõ.

**Không lưu nguyên thẻ thanh toán, access token hoặc dữ liệu nhạy cảm vào bảng request chỉ để so sánh retry.** Nên lưu tối thiểu các trường nghiệp vụ đã được phép lưu, hoặc fingerprint được tạo an toàn theo chính sách bảo mật.

## 18. Lưu kết quả xử lý, không chỉ dấu “đã thấy key”

Giả sử chỉ có bảng:

~~~text
idempotency_key | created_at
--------------------------------
req-A           | ...
~~~

Khi retry, server biết key từng xuất hiện nhưng **không biết đơn nào đã được tạo**, phản hồi cần trả gì hoặc request đầu đã hoàn tất chưa.

Bảng `idempotency_requests` trong lab lưu:

- `tenant_id`, `operation`, `idempotency_key`: định danh yêu cầu.
- `request_payload`: nội dung chuẩn hóa để phát hiện reuse key sai.
- `state`: đang xử lý hoặc đã hoàn tất.
- `order_id`: kết quả nghiệp vụ.
- `completed_at`: thời điểm xử lý xong.

Đối với endpoint khác, có thể cần lưu thêm mã phản hồi, response body đã chuẩn hóa, business object ID hoặc kết quả lỗi được cache theo hợp đồng API.

**Không tự giả định mọi lần retry phải chạy lại câu INSERT rồi hy vọng nó trả đúng ID cũ.** Nhánh `DO NOTHING` không trả hàng, vì vậy dữ liệu kết quả cần được tra/lưu có chủ đích.

## 19. Workflow transaction với idempotency key

Luồng nghiệp vụ đề xuất:

~~~mermaid
flowchart TD
    A["Nhận tenant, operation, key, payload"] --> B["Chuẩn hóa và validate"]
    B --> C["INSERT request key, ON CONFLICT DO NOTHING"]
    C --> D{"Chèn mới được key?"}
    D -->|"Có"| E["Tạo orders và outbox"]
    E --> F["Lưu order_id, state=completed"]
    F --> G["COMMIT và trả kết quả mới"]
    D -->|"Không"| H["Đọc request đã có"]
    H --> I{"Payload có giống?"}
    I -->|"Không"| J["409 / conflict"]
    I -->|"Có, completed"| K["Trả order_id trước đó"]
    I -->|"Có, processing"| L["Chờ, kiểm tra hoặc retry theo hợp đồng"]
~~~

**Tất cả bước tạo mới** phải nằm trong **cùng transaction**: nhận key, tạo đơn, tạo outbox, đánh dấu kết quả. Không được commit key “processing” trước rồi tùy tiện tạo đơn ngoài transaction nếu chưa có cơ chế phục hồi trạng thái dở dang.

Sự độc lập giữa các request cũng phải được đảm bảo: hai client có cùng key sẽ cạnh tranh trên unique constraint, không chỉ kiểm tra bằng SELECT không khóa.

## 20. Tạo hàm create_order_once mẫu trong PostgreSQL

Để có một ví dụ **có thể gọi lặp thực sự**, ta đặt quy trình transaction logic vào hàm `PL/pgSQL`. Mỗi lần gọi hàm là một statement; nếu ứng dụng đang ở autocommit thông thường, PostgreSQL commit khi statement thành công. Nếu đang nằm trong transaction bên ngoài, kết quả còn phụ thuộc COMMIT/ROLLBACK của transaction đó.

Hàm dưới đây chỉ dùng database, **không gọi HTTP hay hệ thống thanh toán ngoài**.

~~~sql
CREATE OR REPLACE FUNCTION retry_lab.create_order_once(
    p_tenant_id integer,
    p_idempotency_key text,
    p_client_order_code text,
    p_amount numeric,
    p_currency text
)
RETURNS TABLE (
    result_order_id bigint,
    replayed boolean
)
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_payload jsonb;
    v_claimed boolean;
    v_created_order_id bigint;
    v_previous_payload jsonb;
    v_previous_order_id bigint;
    v_previous_state text;
    v_currency text;
BEGIN
    -- Kiểm tra dữ liệu đầu vào trước khi ghi.
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant_id';
    END IF;

    IF p_idempotency_key IS NULL
       OR btrim(p_idempotency_key) = '' THEN
        RAISE EXCEPTION 'Missing idempotency key';
    END IF;

    IF p_client_order_code IS NULL
       OR btrim(p_client_order_code) = '' THEN
        RAISE EXCEPTION 'Missing order code';
    END IF;

    IF p_amount IS NULL OR p_amount < 0 THEN
        RAISE EXCEPTION 'Invalid amount';
    END IF;

    v_currency := upper(p_currency);
    IF v_currency IS NULL OR v_currency NOT IN ('VND', 'USD') THEN
        RAISE EXCEPTION 'Invalid currency';
    END IF;

    -- Payload canonical cho endpoint create_order.
    v_payload := jsonb_build_object(
        'client_order_code', p_client_order_code,
        'amount', p_amount,
        'currency', v_currency
    );

    -- Tranh quyền xử lý request bằng PRIMARY KEY.
    v_claimed := false;

    INSERT INTO retry_lab.idempotency_requests (
        tenant_id,
        operation,
        idempotency_key,
        request_payload
    )
    VALUES (
        p_tenant_id,
        'create_order',
        p_idempotency_key,
        v_payload
    )
    ON CONFLICT (tenant_id, operation, idempotency_key)
    DO NOTHING
    RETURNING true INTO v_claimed;

    IF v_claimed IS TRUE THEN
        -- Đây là request mới: tạo business object.
        INSERT INTO retry_lab.orders (
            tenant_id,
            client_order_code,
            amount,
            currency
        )
        VALUES (
            p_tenant_id,
            p_client_order_code,
            p_amount,
            v_currency
        )
        RETURNING order_id INTO v_created_order_id;

        -- Ghi sự kiện trong cùng statement/transaction.
        INSERT INTO retry_lab.outbox_events (
            tenant_id,
            order_id,
            event_type,
            payload
        )
        VALUES (
            p_tenant_id,
            v_created_order_id,
            'order.created',
            jsonb_build_object(
                'order_id', v_created_order_id,
                'client_order_code', p_client_order_code,
                'amount', p_amount,
                'currency', v_currency
            )
        );

        -- Chỉ hoàn thành request khi đã tạo order/outbox.
        UPDATE retry_lab.idempotency_requests AS r
        SET
            state = 'completed',
            order_id = v_created_order_id,
            completed_at = now()
        WHERE r.tenant_id = p_tenant_id
          AND r.operation = 'create_order'
          AND r.idempotency_key = p_idempotency_key;

        RETURN QUERY
        SELECT v_created_order_id, false;
        RETURN;
    END IF;

    -- Key đã tồn tại: đọc kết quả từ transaction đã thắng.
    SELECT
        r.request_payload,
        r.order_id,
        r.state
    INTO
        v_previous_payload,
        v_previous_order_id,
        v_previous_state
    FROM retry_lab.idempotency_requests AS r
    WHERE r.tenant_id = p_tenant_id
      AND r.operation = 'create_order'
      AND r.idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Trong mô hình READ COMMITTED thông thường,
        -- trường hợp này không kỳ vọng xảy ra sau claim conflict.
        RAISE EXCEPTION 'Request result not visible; retry transaction';
    END IF;

    IF v_previous_payload IS DISTINCT FROM v_payload THEN
        RAISE EXCEPTION
            'Idempotency key reused with different payload';
    END IF;

    IF v_previous_state <> 'completed'
       OR v_previous_order_id IS NULL THEN
        RAISE EXCEPTION
            'Request has no completed result';
    END IF;

    RETURN QUERY
    SELECT v_previous_order_id, true;
END;
$$;
~~~

### Những điểm quan trọng của hàm

- `v_payload` được xây từ các trường nghiệp vụ đã chuẩn hóa theo hợp đồng mẫu.
- `INSERT ... ON CONFLICT DO NOTHING RETURNING true` xác định phiên nào **giành được quyền xử lý key**.
- Nhánh thắng tạo `orders`, ghi `outbox_events` và cập nhật `idempotency_requests` bằng **các statement tuần tự bên trong cùng lời gọi hàm**.
- Nếu INSERT order hoặc outbox lỗi, statement gọi hàm thất bại và những thay đổi database của lời gọi không được commit một phần.
- Nhánh thua đọc yêu cầu đã tồn tại và so payload trước khi trả kết quả cũ.
- `FOR UPDATE` khóa hàng request được đọc trong transaction để xử lý trạng thái một cách có kiểm soát; không phải cách thay thế unique key lúc giành quyền xử lý.
- `VOLATILE` là khai báo thích hợp vì hàm có thao tác INSERT và UPDATE.

**Giới hạn của ví dụ:** đây là một thiết kế phục vụ bài học, không phải package API production hoàn chỉnh. Hệ thống thật còn cần quyền/tenant, response status/body, chính sách timeout, lưu trạng thái lỗi, expiration, retry SQLSTATE và giám sát dữ liệu `processing` bất thường.

## 21. Thực hành gọi cùng key hai lần

Thực hiện trong transaction lab rồi rollback:

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-A', 'WEB-100', 120.00, 'VND'
);

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-A', 'WEB-100', 120.00, 'VND'
);

SELECT
    tenant_id,
    client_order_code,
    order_id,
    amount
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-100';

SELECT
    event_id,
    order_id,
    event_type
FROM retry_lab.outbox_events
WHERE tenant_id = 10;

SELECT
    idempotency_key,
    state,
    order_id
FROM retry_lab.idempotency_requests
WHERE tenant_id = 10
  AND operation = 'create_order';

ROLLBACK;
~~~

Kết quả dự kiến trong transaction:

- Lần gọi đầu: trả `result_order_id = N`, `replayed = false`.
- Lần gọi hai: trả **cùng `N`**, `replayed = true`.
- Có đúng **một hàng orders** với mã `WEB-100`.
- Có đúng **một event `order.created`** cho đơn đó.
- Bảng idempotency có **một key `req-A`** ở trạng thái `completed`.

Số `N` không cố định vì identity sequence có thể đã cấp giá trị trước đó. `ROLLBACK` trả các hàng database về trạng thái lab ban đầu, nhưng **không bảo đảm sequence quay về số cũ**.

### Đừng nhầm cùng key với cùng mã đơn

Nếu dùng **key mới** nhưng vẫn gọi `client_order_code = 'WEB-100'`, unique business key sẽ chặn tạo một đơn thứ hai trong cùng tenant. Lỗi unique là tín hiệu cần được ứng dụng xử lý theo chính sách: kiểm tra đây là một thao tác tạo trùng thực sự hay một request sai key, chứ không tự biến thành một thao tác UPDATE số tiền.

## 22. Nếu cùng key nhưng payload khác thì sao?

Thử tình huống sai trong lab, qua **hai transaction riêng** để mỗi transaction có thể được rollback/commit rõ ràng:

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-B', 'WEB-200', 100.00, 'VND'
);

COMMIT;
~~~

Sau đó gọi cùng key nhưng khác amount:

~~~sql
-- Dự kiến lỗi nghiệp vụ.
SELECT *
FROM retry_lab.create_order_once(
    10, 'req-B', 'WEB-200', 900.00, 'VND'
);
~~~

Hàm từ chối reuse key với payload khác. Trong API, có thể ánh xạ trường hợp này sang phản hồi xung đột (ví dụ HTTP 409), với nội dung không làm lộ dữ liệu request đầu của người khác.

**Lưu ý thực hành:** ví dụ này dùng `COMMIT` nên tạo dữ liệu mới trong schema lab. Khi muốn giữ dataset sạch, hãy chạy phần kiểm thử trên database lab mới được reset, hoặc dùng một `SAVEPOINT` và xử lý lỗi trong transaction thử nghiệm. Đừng chạy kịch bản có chủ đích gây lỗi rồi tiếp tục transaction mà không rollback.

### Tại sao không tự chấp nhận amount mới?

Một idempotency key đại diện cho **một logical request duy nhất**. Nếu cùng key được dùng với một payload khác, hệ thống không thể kết luận “đây là retry của request cũ”; việc âm thầm sửa amount có thể dẫn đến lỗi tính tiền hoặc gian lận.

## 23. Thử với hai phiên đồng thời

Mở **hai session PostgreSQL** trỏ cùng database lab. Dùng một key chưa từng xuất hiện.

**Phiên A:**

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-concurrent', 'WEB-300', 300.00, 'VND'
);

-- Chưa COMMIT, giữ transaction mở để quan sát session B.
~~~

**Phiên B (chạy khi A còn mở):**

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-concurrent', 'WEB-300', 300.00, 'VND'
);

-- Câu gọi có thể chờ unique conflict của A.
~~~

Quay lại A:

~~~sql
COMMIT;
~~~

Sau khi A commit, B có thể tiếp tục và trả kết quả cũ với `replayed = true`. Sau đó ở B:

~~~sql
COMMIT;
~~~

Kiểm tra:

~~~sql
SELECT COUNT(*) AS orders_count
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-300';
~~~

Kết quả kỳ vọng là **1**.

Nếu A rollback thay vì commit, B có thể giành quyền INSERT key và tạo đơn như request mới. Điều này minh họa uniqueness phối hợp với trạng thái transaction chưa commit.

**Điều kiện thử nghiệm:** các ví dụ giả định isolation `READ COMMITTED` phổ biến của PostgreSQL, function được gọi trong transaction bình thường và không có worker khác sửa cùng dữ liệu. Với `REPEATABLE READ`/`SERIALIZABLE`, có thể cần retry toàn transaction khi gặp lỗi concurrency; không được giả định sẽ luôn trả replay ngay trong snapshot cũ.

## 24. Không tạo key “processing” rồi commit riêng tùy tiện

Một anti-pattern:

~~~text
Transaction 1: INSERT request_key(state='processing') → COMMIT
Transaction 2: tạo order → COMMIT
Transaction 3: UPDATE request_key(state='completed') → COMMIT
~~~

Nếu ứng dụng chết giữa các transaction, key đã bị chiếm nhưng không có kết quả hoàn chỉnh. Các lần retry sau có thể mắc kẹt vĩnh viễn ở trạng thái processing hoặc tạo sai lặp ở một luồng phục hồi khác.

Có hai thiết kế có chủ đích:

1. **Toàn bộ thao tác database ngắn trong một transaction**, như hàm `create_order_once`: khi commit thì key và order/outbox cùng hoàn tất.
2. **Workflow dài/saga có trạng thái processing được commit**, nhưng cần lease/timeout, owner token, khả năng khôi phục, khóa cạnh tranh, trạng thái thất bại và retry state machine rõ ràng.

Không chọn mô hình (2) chỉ vì nó dễ chia thành nhiều lần gọi DB; nó yêu cầu nhiều quy tắc hơn đáng kể.

## 25. Transactional outbox và duplicate event

Một đơn có thể chỉ được tạo một lần trong PostgreSQL nhưng ứng dụng vẫn gửi **hai event** nếu đặt việc phát thông điệp ở ngoài transaction và retry toàn endpoint.

Ví dụ không an toàn:

~~~text
INSERT orders → COMMIT
Publish order.created → broker
Response timeout → retry
Publish order.created một lần nữa
~~~

Mẫu an toàn hơn ở database:

~~~text
BEGIN
  Claim idempotency key
  INSERT orders
  INSERT outbox_events
  Mark request completed
COMMIT

Worker riêng đọc outbox đã commit và publish
~~~

Trong bài lab, `outbox_events` còn có:

~~~sql
UNIQUE (tenant_id, order_id, event_type)
~~~

Constraint này giúp không có hai hàng event cùng loại cho một đơn trong bảng outbox, nhưng **không tự bảo đảm broker nhận đúng một lần**. Worker có thể publish thành công rồi chết trước khi ghi `published_at`; lúc phục hồi, nó có thể publish lại.

Vì vậy consumer cần **deduplication/idempotency theo event_id hoặc business event key**, cùng chiến lược retry và quan sát. Một transaction PostgreSQL không thể một mình bảo đảm exactly-once end-to-end ở dịch vụ ngoài.

## 26. Trừ tồn kho là thao tác không idempotent

Bảng inventory có:

~~~sql
SELECT product_id, quantity
FROM retry_lab.inventory
ORDER BY product_id;
~~~

Kết quả seed: sản phẩm 501 còn 8; sản phẩm 502 còn 0.

Một lần xuất kho 3 đơn vị:

~~~sql
UPDATE retry_lab.inventory
SET quantity = quantity - 3
WHERE product_id = 501
  AND quantity >= 3
RETURNING product_id, quantity;
~~~

**Nếu request này bị retry sau khi đã commit**, câu UPDATE có thể tiếp tục trừ 3 lần nữa. Điều kiện `quantity >= 3` bảo vệ không âm nhưng **không ngăn trừ lặp** khi kho vẫn đủ.

Tương tự, đặt `ON CONFLICT DO NOTHING` chỉ ở bước ghi movement **sau khi đã trừ stock** là quá muộn: movement có thể không chèn trùng, nhưng tồn kho đã bị trừ tiếp.

### Sai mẫu cần tránh

~~~text
UPDATE inventory SET quantity = quantity - 3;
INSERT inventory_movements(key, delta=-3)
  ON CONFLICT DO NOTHING;
~~~

Ở lần retry, câu UPDATE vẫn trừ, dù INSERT movement bị bỏ qua.

**Quyền xử lý operation phải được xác định trước khi thực hiện hiệu ứng không idempotent**, và tất cả thao tác liên quan phải commit nguyên tử.

## 27. Hàm deduct_stock_once: chống trừ kho hai lần

Bảng `stock_deductions` có `PRIMARY KEY(product_id, operation_key)`. Ta dùng khóa này trước khi giảm kho, sau đó lưu số lượng còn lại.

~~~sql
CREATE OR REPLACE FUNCTION retry_lab.deduct_stock_once(
    p_product_id integer,
    p_operation_key text,
    p_quantity integer
)
RETURNS TABLE (
    quantity_remaining integer,
    replayed boolean
)
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_claimed boolean;
    v_remaining integer;
    v_previous_quantity integer;
    v_previous_remaining integer;
BEGIN
    IF p_product_id IS NULL THEN
        RAISE EXCEPTION 'Missing product_id';
    END IF;

    IF p_operation_key IS NULL
       OR btrim(p_operation_key) = '' THEN
        RAISE EXCEPTION 'Missing operation key';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;

    v_claimed := false;

    INSERT INTO retry_lab.stock_deductions (
        product_id,
        operation_key,
        deduct_quantity
    )
    VALUES (
        p_product_id,
        p_operation_key,
        p_quantity
    )
    ON CONFLICT (product_id, operation_key)
    DO NOTHING
    RETURNING true INTO v_claimed;

    IF v_claimed IS TRUE THEN
        -- Chỉ request mới được giảm tồn kho.
        UPDATE retry_lab.inventory AS i
        SET quantity = i.quantity - p_quantity
        WHERE i.product_id = p_product_id
          AND i.quantity >= p_quantity
        RETURNING i.quantity INTO v_remaining;

        IF NOT FOUND THEN
            -- Không còn đủ kho: rollback cả claim và UPDATE.
            RAISE EXCEPTION 'Insufficient or missing stock';
        END IF;

        UPDATE retry_lab.stock_deductions AS d
        SET remaining_quantity = v_remaining
        WHERE d.product_id = p_product_id
          AND d.operation_key = p_operation_key;

        RETURN QUERY SELECT v_remaining, false;
        RETURN;
    END IF;

    -- Retry: đọc hiệu ứng đã được commit trước đó.
    SELECT
        d.deduct_quantity,
        d.remaining_quantity
    INTO
        v_previous_quantity,
        v_previous_remaining
    FROM retry_lab.stock_deductions AS d
    WHERE d.product_id = p_product_id
      AND d.operation_key = p_operation_key
    FOR UPDATE;

    IF NOT FOUND OR v_previous_remaining IS NULL THEN
        RAISE EXCEPTION 'Operation has no completed result';
    END IF;

    IF v_previous_quantity <> p_quantity THEN
        RAISE EXCEPTION
            'Operation key reused with different quantity';
    END IF;

    RETURN QUERY SELECT v_previous_remaining, true;
END;
$$;
~~~

### Thực hành

~~~sql
BEGIN;

SELECT *
FROM retry_lab.deduct_stock_once(
    501, 'deduct-01', 3
);

SELECT *
FROM retry_lab.deduct_stock_once(
    501, 'deduct-01', 3
);

SELECT product_id, quantity
FROM retry_lab.inventory
WHERE product_id = 501;

SELECT product_id, operation_key,
       deduct_quantity, remaining_quantity
FROM retry_lab.stock_deductions
WHERE product_id = 501;

ROLLBACK;
~~~

Trong transaction:

- Lần đầu: `quantity_remaining = 5`, `replayed = false`.
- Lần hai: `quantity_remaining = 5`, `replayed = true`.
- Kho chỉ giảm **từ 8 xuống 5**, không giảm còn 2.
- Bảng `stock_deductions` có một dòng cho `deduct-01`.
- Sau rollback, kho lại 8 và dòng deduction được hoàn tác.

### Giới hạn nghiệp vụ của ví dụ

Hàm ghi lại **kết quả thành công**. Khi thiếu kho, nó raise exception và claim bị rollback, nên một lần retry sau khi được nhập thêm kho có thể thành công. Nếu hợp đồng API yêu cầu **cùng key luôn trả cùng kết quả thất bại ban đầu**, cần lưu trạng thái lỗi một cách nguyên tử và xác định lỗi nào được cache, lỗi nào cho retry.

Bên cạnh đó, `quantity_remaining` là **giá trị kho ngay sau lần trừ đầu tiên**, không phải số kho hiện tại ở thời điểm request được replay. Đây là chủ đích lưu kết quả operation cũ. Muốn trả tồn kho hiện tại, thực hiện một truy vấn riêng với tên trường phản ánh đúng ngữ nghĩa.

## 28. Đặc tính của các lỗi khi retry

Một client thường cần phân biệt:

| Trường hợp | Cách xử lý gợi ý |
| --- | --- |
| Duplicate key, cùng payload và đã hoàn tất | Trả kết quả đã lưu |
| Duplicate key, payload khác | Trả conflict; không thực hiện lại |
| Key chưa tồn tại | Xử lý request mới |
| Có bản ghi processing theo workflow dài | Chờ/tra trạng thái/timeout theo state machine |
| SQLSTATE `23505` từ một unique key nghiệp vụ khác | Kiểm tra xung đột cụ thể, không tự coi là retry cùng request |
| SQLSTATE `40001` (serialization_failure) | Có thể retry **toàn transaction** nếu workflow được thiết kế an toàn |
| SQLSTATE `40P01` (deadlock_detected) | Có thể retry transaction có kiểm soát |
| Lỗi mạng sau COMMIT không rõ kết quả | Gửi lại **cùng idempotency key** và tra kết quả |
| Lỗi validate input cố định | Trả lỗi phù hợp; có thể lưu hoặc không tùy hợp đồng |

Không gộp mọi lỗi PostgreSQL thành một vòng lặp retry vô hạn. Một lỗi `23505` có thể là “mã đơn đã thuộc request khác”, không phải sự cố tạm thời; retry mãi không khắc phục được.

Với lỗi concurrency có thể retry, cần giới hạn số lần, backoff/jitter, logging và nhận diện transaction idempotent trước khi lặp.

## 29. Transaction isolation và retry toàn giao dịch

`READ COMMITTED` là mức isolation mặc định của PostgreSQL. Mỗi statement thường nhận snapshot phù hợp với thời điểm bắt đầu statement; PostgreSQL còn có cơ chế xử lý các cập nhật đang đồng thời diễn ra.

Với `REPEATABLE READ` hoặc `SERIALIZABLE`, một transaction có thể nhận **serialization failure** khi không thể áp dụng an toàn kết quả cạnh tranh. Khi đó ứng dụng cần lặp lại **toàn bộ logic đọc–quyết định–ghi của transaction**, không chỉ lặp một statement cuối.

Trong quy trình có key idempotency:

1. Giữ nguyên **idempotency key** qua các lần retry cùng logical request.
2. Bảo đảm mọi side effect database cùng transaction.
3. Nếu transaction rollback, xem như không có kết quả mới được commit.
4. Nếu không rõ đã commit chưa, **tra key** ở statement/transaction mới trước khi suy ra cần tạo operation khác.
5. Chỉ retry với backoff và giới hạn; không lấy `now()`, UUID hay số ngẫu nhiên mới làm **idempotency key mới** cho cùng request mỗi lần.

### Không dùng SQLSTATE để suy ra trạng thái nghiệp vụ nếu không đủ bằng chứng

Ví dụ một INSERT có thể bị unique violation trên `(tenant_id, client_order_code)` do **một yêu cầu khác**. Không tự trả “đơn đã tạo bởi request này” chỉ vì lỗi `23505`; phải truy ra constraint gây lỗi, payload và quyền truy cập kết quả.

## 30. Kết hợp với JDBC / Java

Trong Java, client nên sinh key **một lần cho một logical operation** rồi giữ lại khi retry. Dùng `PreparedStatement` để truyền giá trị, không nội suy chuỗi từ người dùng vào SQL.

Ví dụ lời gọi hàm:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public record CreateOrderResult(long orderId, boolean replayed) {}

public static CreateOrderResult createOrderOnce(
        Connection connection,
        int tenantId,
        String idempotencyKey,
        String clientOrderCode,
        BigDecimal amount,
        String currency
) throws SQLException {

    String sql = """
        SELECT result_order_id, replayed
        FROM retry_lab.create_order_once(?, ?, ?, ?, ?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setInt(1, tenantId);
        ps.setString(2, idempotencyKey);
        ps.setString(3, clientOrderCode);
        ps.setBigDecimal(4, amount);
        ps.setString(5, currency);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("No result from create_order_once");
            }

            return new CreateOrderResult(
                rs.getLong("result_order_id"),
                rs.getBoolean("replayed")
            );
        }
    }
}
~~~

Đây là ví dụ repository, chưa gồm authentication, authorization, HTTP mapping, transaction boundary hoặc retry policy. Nếu connection đang nằm trong transaction do service quản lý, phương thức không được tự commit/rollback tùy tiện.

### Sinh idempotency key đúng lúc

~~~java
// Sinh MỘT LẦN khi bắt đầu một yêu cầu logic mới:
String key = java.util.UUID.randomUUID().toString();

// Retry giữ nguyên key, không sinh UUID mới cho lần gọi lại:
CreateOrderResult result = createOrderOnce(
    connection,
    tenantId,
    key,
    orderCode,
    amount,
    "VND"
);
~~~

Nếu ứng dụng cần retry sau khi process restart, key phải được lưu/giữ ở nơi phù hợp, ví dụ client request context hoặc bản ghi job ổn định. Một UUID chỉ giữ trong biến RAM rồi bị mất khi restart không đủ để nhận diện cùng request sau đó.

### Nhận biết lỗi

Trong JDBC, SQLSTATE có thể lấy từ:

~~~java
try {
    // Thực thi câu SQL.
} catch (SQLException e) {
    String sqlState = e.getSQLState();

    if ("40001".equals(sqlState) || "40P01".equals(sqlState)) {
        // Retry TOÀN TRANSACTION khi có chính sách phù hợp.
    } else if ("23505".equals(sqlState)) {
        // Unique conflict: cần phân tích constraint/business key.
    } else {
        // Xử lý lỗi khác theo phân loại riêng.
    }
    throw e;
}
~~~

Ví dụ trên chỉ minh họa phân loại; đừng tự thêm vòng retry vô hạn ngay trong repository. Một số lỗi làm transaction ở trạng thái aborted, cần rollback trước khi thử transaction mới.

## 31. HTTP API nên trả gì khi replay?

Một hợp đồng API có thể quy định:

| Tình huống | Phản hồi minh họa |
| --- | --- |
| Request mới được tạo thành công | `201 Created` + `order_id` |
| Retry cùng key/payload sau thành công | `200 OK` hoặc replay nguyên `201`, cùng `order_id` |
| Cùng key nhưng payload khác | `409 Conflict` |
| Request đang xử lý trong workflow dài | `202 Accepted` hoặc `409/425` theo thiết kế |
| Không đủ kho | Mã lỗi nghiệp vụ thích hợp |
| Timeout chưa rõ commit | Client retry cùng key |

Không có một mã HTTP duy nhất bắt buộc cho mọi hệ thống. Quan trọng là **hợp đồng rõ ràng, nhất quán** và idempotency được bảo vệ ở phía server.

Nếu cần response giống hệt, bảng request phải lưu thêm những thông tin cần replay, ví dụ `http_status` và body JSON đã được loại dữ liệu nhạy cảm. Nếu chỉ lưu business ID, server có thể dựng response từ dữ liệu hiện tại, nhưng nội dung có thể thay đổi theo thời gian; cần định nghĩa rõ ý nghĩa mong muốn.

## 32. Bảo mật idempotency key và payload

Idempotency key là dữ liệu điều phối, không phải tự thân bằng chứng người gửi có quyền đọc đơn.

Các nguyên tắc:

- Ràng buộc key với **đúng tenant/user/operation** đã xác thực.
- Không cho người dùng A tra kết quả của người dùng B chỉ vì biết key.
- Giới hạn độ dài, tần suất và số lượng key để tránh lạm dụng dung lượng lưu trữ.
- Không log raw payload chứa dữ liệu thanh toán hoặc thông tin cá nhân nhạy cảm.
- Chỉ lưu payload tối thiểu hoặc fingerprint theo chính sách bảo mật.
- Không sử dụng timestamp hoặc số thứ tự dễ đoán làm cơ chế bảo mật.
- Dùng quyền database phù hợp; có thể cân nhắc RLS hoặc chỉ cho phép gọi function/API được kiểm soát.
- Với `SECURITY DEFINER`, phải cố định `search_path` và kiểm soát privilege cẩn thận; đừng nâng quyền chỉ để “cho hàm chạy”.

Idempotency không thay thế authorization. Một request sai quyền phải bị từ chối ngay cả khi có key trông hợp lệ.

## 33. Chính sách lưu giữ, TTL và xóa key

Bảng idempotency tăng theo số request. Cần chính sách retention:

- Giữ key đủ lâu so với **cửa sổ retry tối đa** của client, queue hoặc message broker.
- Xác định key hết hạn có được phép tái sử dụng không.
- Nếu xóa idempotency key quá sớm, một retry rất muộn có thể được coi là request mới.
- Business key unique có thể vẫn chặn trùng một số đối tượng, nhưng không bảo vệ mọi dạng side effect.
- Với dữ liệu tài chính hoặc fulfillment, retention có thể cần dài hơn API request thông thường.
- Có kế hoạch archive/partition/purge và số liệu monitor.

Một truy vấn tìm các key cũ:

~~~sql
SELECT
    tenant_id,
    operation,
    idempotency_key,
    completed_at
FROM retry_lab.idempotency_requests
WHERE state = 'completed'
  AND completed_at < now() - interval '30 days'
ORDER BY completed_at;
~~~

Câu này **chỉ để khảo sát**. Không tự động chạy DELETE 30 ngày trên dữ liệu production vì hợp đồng retry, lưu trữ và compliance có thể yêu cầu thời gian khác.

## 34. Quan sát và kiểm thử chống trùng

Một hệ thống có idempotency cần số liệu không chỉ về request thành công, mà còn về **retry** và **mismatch**:

| Chỉ số | Ý nghĩa |
| --- | --- |
| New operations | Số lần key mới được nhận và hoàn tất |
| Replayed operations | Số retry đúng key/payload và được trả kết quả cũ |
| Payload conflicts | Số trường hợp reuse key với dữ liệu khác |
| Unique violations by constraint | Xung đột nghiệp vụ/khóa khác |
| Processing age | Key ở trạng thái chưa hoàn tất quá lâu |
| Serialization/deadlock retry | Mức tranh chấp transaction |
| Outbox backlog | Event đã commit nhưng chưa publish |
| Duplicate consumer event | Sự kiện trùng được consumer nhận diện |

Các phép thử nên bao gồm:

1. Cùng key, cùng payload gọi hai lần tuần tự.
2. Cùng key, cùng payload gọi song song hai phiên.
3. Cùng key, payload khác.
4. Khác key nhưng cùng business code.
5. Khác tenant, cùng key.
6. Client bị timeout sau commit rồi retry.
7. Client mất kết nối trước commit, transaction rollback.
8. Outbox worker publish thành công nhưng chưa đánh dấu đã gửi.
9. Concurrent stock deductions cùng product nhưng khác operation key.
10. Retry sau khi kho không đủ hoặc sau khi key hết hạn.
11. Serialization failure/deadlock phải retry toàn transaction.
12. Có trigger/audit để phát hiện thao tác bị chạy nhiều lần không mong muốn.

**Đừng chỉ thử hai request tuần tự.** Race condition thường chỉ xuất hiện khi nhiều connection xử lý cùng key trước khi transaction đầu commit.

## 35. Những sai lầm thường gặp

### 35.1. Tin rằng frontend không gửi trùng

Gateway, network và worker có thể retry độc lập với hành động người dùng. Cần xử lý ở server/database.

### 35.2. Chỉ dùng SELECT để kiểm tra rồi INSERT

Hai transaction có thể cùng thấy “chưa tồn tại”. Cần unique constraint.

### 35.3. Sinh idempotency key mới ở mỗi lần retry

Mỗi lần trông như một request mới. Giữ nguyên key của logical operation.

### 35.4. Dùng DO NOTHING để che payload khác

Key trùng với amount khác không được xem là cùng request. So sánh payload/fingerprint.

### 35.5. Lạm dụng DO UPDATE SET col = col để lấy RETURNING

Có thể kích hoạt trigger/WAL/lock và che mismatch. Dùng cơ chế tra kết quả riêng nếu phù hợp.

### 35.6. Dùng DO UPDATE SET quantity = quantity + delta

Mỗi retry lại cộng/trừ một lần. Cần claim operation trước và transaction nguyên tử.

### 35.7. Không đặt scope cho key

Một chuỗi key của tenant A có thể xung đột hoặc lộ kết quả của tenant B nếu khóa không gắn với danh tính phù hợp.

### 35.8. Để idempotency_key nullable

Unique truyền thống cho phép nhiều NULL. Dùng NOT NULL và validate key.

### 35.9. Ghi key processing rồi commit trước nghiệp vụ

Nếu worker chết, key mắc kẹt không có kết quả. Cần atomic transaction hoặc state machine phục hồi.

### 35.10. Ghi đơn rồi publish message bên ngoài trước commit

Có thể publish sự kiện cho giao dịch đã rollback. Dùng outbox và publish sau commit.

### 35.11. Nghĩ outbox tự đảm bảo exactly-once

Worker có thể gửi trùng. Consumer cần idempotent hoặc dedupe.

### 35.12. Coi mọi SQLSTATE 23505 là một request đã xử lý

Xung đột có thể ở business key khác hoặc tenant khác. Đọc constraint và xác minh ownership/payload.

### 35.13. Coi DO NOTHING RETURNING 0 là lỗi SQL

Đó là một kết quả thành công của nhánh xung đột. Client phải tra record đã xử lý.

### 35.14. Đọc hàng existing trong cùng statement và nghĩ luôn nhìn thấy nó

Ở READ COMMITTED, ON CONFLICT có thể nhận biết conflict với hàng chưa nhìn thấy trong snapshot cùng statement. Đọc lại ở statement mới khi cần.

### 35.15. Cố áp dụng một lần POST cho giao dịch ngoài database

Unique key PostgreSQL không thể tự hoàn tác giao dịch đã thực hiện tại payment gateway hoặc dịch vụ thứ ba. Cần idempotency phía đối tác và quy trình reconcile.

### 35.16. Retry transaction nhưng đổi request content

Giữ cùng key mà đổi currency/amount/order code khiến hợp đồng idempotency không còn đúng. Retry cùng logical request phải giữ dữ liệu tương đương.

### 35.17. Không quản lý retention

Xóa key trước cửa sổ retry có thể làm request cũ trở thành thao tác mới.

### 35.18. Coi kết quả tồn kho đã lưu là tồn kho hiện tại

Replay một operation có thể trả `remaining_quantity` tại thời điểm xử lý đầu, không phải số kho bây giờ. Đặt tên trường và hợp đồng phản hồi rõ.

## 36. Bài tập thực hành có đáp án

Các bài tập sau chạy trên schema `retry_lab`. Với ví dụ thay đổi dữ liệu, dùng transaction và `ROLLBACK` trừ khi bài cần quan sát hai transaction có commit thật trong database lab.

### Bài 1. INSERT cùng business code hai lần

~~~sql
BEGIN;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-01', 10.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-01', 10.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

SELECT COUNT(*) AS order_count
FROM retry_lab.orders
WHERE tenant_id = 10 AND client_order_code = 'EX-01';

ROLLBACK;
~~~

**Đáp án:** Lần đầu INSERT trả một ID, lần hai trả 0 hàng, `order_count = 1` trong transaction.

### Bài 2. Hai tenant cùng mã đơn có được không?

~~~sql
BEGIN;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-02', 10.00, 'VND'),
    (20, 'EX-02', 20.00, 'VND')
RETURNING tenant_id, client_order_code;

ROLLBACK;
~~~

**Đáp án:** Có, vì unique key là **cặp** `(tenant_id, client_order_code)`.

### Bài 3. Cùng mã đơn nhưng khác amount

**Câu hỏi:** Vì sao `ON CONFLICT DO NOTHING` chưa đủ để gọi là idempotency hoàn chỉnh?

**Đáp án:** Nó không chèn thêm hàng nhưng cũng không phát hiện payload khác. Phải so request payload/fingerprint, thường báo conflict khi key bị tái sử dụng sai.

### Bài 4. ON CONFLICT cộng stock có an toàn khi retry không?

~~~sql
ON CONFLICT (product_id)
DO UPDATE
SET quantity = retry_lab.inventory.quantity + EXCLUDED.quantity
~~~

**Đáp án:** Không. Mỗi retry tăng stock thêm lần nữa. Cần operation key/ledger và transaction.

### Bài 5. Thử create_order_once hai lần

~~~sql
BEGIN;

SELECT * FROM retry_lab.create_order_once(
    10, 'EX-REQ-01', 'EX-ORDER-01', 99.00, 'VND'
);

SELECT * FROM retry_lab.create_order_once(
    10, 'EX-REQ-01', 'EX-ORDER-01', 99.00, 'VND'
);

ROLLBACK;
~~~

**Đáp án:** Hai lần cùng order_id; lần đầu `replayed=false`, lần hai `replayed=true`.

### Bài 6. Gọi cùng key nhưng khác request có nên tạo đơn mới?

**Đáp án:** Không. Reuse key với payload khác là xung đột, không phải retry hợp lệ. Hệ thống cần từ chối hoặc xử lý theo chính sách đã công bố, không sửa đơn cũ.

### Bài 7. Vì sao UNIQUE có thể cho hai NULL?

**Đáp án:** Theo ngữ nghĩa mặc định, PostgreSQL xem NULL khác nhau cho uniqueness. Dùng NOT NULL cho idempotency key; PostgreSQL 15+ có tùy chọn `NULLS NOT DISTINCT` cho các trường hợp khác.

### Bài 8. Deduct stock hai lần với cùng key

~~~sql
BEGIN;

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-01', 3
);

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-01', 3
);

SELECT quantity
FROM retry_lab.inventory
WHERE product_id = 501;

ROLLBACK;
~~~

**Đáp án:** Stock còn **5** chứ không phải 2; replay dùng lại kết quả đã lưu.

### Bài 9. Deduct stock với key mới thì sao?

Trong cùng transaction, gọi lần lượt:

~~~sql
BEGIN;

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-A', 3
);

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-B', 3
);

SELECT quantity
FROM retry_lab.inventory
WHERE product_id = 501;

ROLLBACK;
~~~

**Đáp án:** Hai operation key khác nhau đại diện **hai yêu cầu hợp lệ**, stock từ 8 xuống 2.

### Bài 10. Nếu không đủ stock?

~~~sql
SELECT * FROM retry_lab.deduct_stock_once(
    502, 'EX-STOCK-C', 3
);
~~~

**Đáp án:** Hàm báo lỗi vì sản phẩm 502 có stock 0. Không có deduction thành công được commit. Muốn lặp lại trong transaction sau lỗi, rollback trước.

### Bài 11. Lỗi nào nên retry toàn transaction?

**Đáp án:** `40001` và `40P01` là các ví dụ thường cần cơ chế retry **toàn transaction** khi nghiệp vụ được thiết kế an toàn. `23505` phải được phân loại theo constraint, không tự retry vô hạn.

### Bài 12. Vì sao không phải mọi 23505 đều là request replay?

**Đáp án:** Xung đột có thể nằm ở `uq_orders_tenant_code` do một request khác dùng business code giống nhau nhưng key khác. Cần xác minh request/các trường nghiệp vụ và ownership.

### Bài 13. Mất response sau commit

**Câu hỏi:** Client có nên sinh một UUID mới rồi gửi lại không?

**Đáp án:** Không. Gửi lại **cùng idempotency key** để server trả kết quả lần trước.

### Bài 14. Outbox có tự chống publish trùng không?

**Đáp án:** Không. Outbox chống tình trạng dữ liệu commit nhưng event không được ghi cùng transaction; worker có thể publish trùng sau khi crash và cần consumer idempotent/deduplication.

### Bài 15. Chọn khóa cho hai endpoint

Một API có `create_order` và `cancel_order`; client tình cờ dùng cùng chuỗi key.

**Đáp án gợi ý:** Đưa `operation` vào phạm vi khóa unique nếu hợp đồng API cho phép key dùng lại giữa hai loại thao tác, ví dụ `PRIMARY KEY(tenant_id, operation, idempotency_key)`.

### Bài 16. Khi nào xóa idempotency key?

**Đáp án gợi ý:** Chỉ sau thời gian đủ dài so với cửa sổ retry của client/queue và yêu cầu lưu trữ, đồng thời xem việc tái sử dụng key và business uniqueness. Không có TTL cố định đúng cho mọi hệ thống.

## 37. Checklist thiết kế retry-safe writes cho production

Khi xây một endpoint hoặc consumer có thể bị gọi lặp, thực hiện:

1. **Định nghĩa logical operation** và phạm vi mà hai request được coi là giống nhau.
2. **Yêu cầu idempotency key** hoặc xác định business key đủ mạnh; không dựa vào timestamp/độ may mắn.
3. **Chuẩn hóa payload** theo quy tắc nghiệp vụ và xác định cách phát hiện payload mismatch.
4. **Tạo UNIQUE/PRIMARY KEY ở database** với scope tenant/user/operation phù hợp, cột key NOT NULL.
5. **Xử lý xung đột bằng ON CONFLICT/transaction**, không dùng SELECT-before-INSERT như tuyến bảo vệ duy nhất.
6. **Lưu business result** (ID, trạng thái, response) để trả khi replay.
7. **Chỉ cho bên thắng claim tạo side effect**, và lưu kết quả cùng transaction.
8. **Không dùng cộng/trừ lặp** nếu chưa có operation ledger với khóa unique.
9. **Dùng RETURNING** để nhận đúng ID và hàng đã tạo, không dùng `MAX(id)`.
10. **Xử lý xung đột content**: cùng key khác payload không được âm thầm bỏ qua hoặc sửa hàng cũ.
11. **Bảo vệ concurrency**: unique index, row lock, isolation, retry transaction khi cần.
12. **Kết hợp outbox** cho event sau commit, thiết kế consumer idempotent.
13. **Phân loại lỗi SQLSTATE**: 23505 khác 40001/40P01, không retry mọi lỗi.
14. **Quản lý trạng thái processing và recovery** nếu workflow kéo dài hơn một transaction.
15. **Xác định retention/TTL** theo cửa sổ retry thật và quy định dữ liệu.
16. **Giới hạn lạm dụng và bảo vệ privacy** của key/payload/response.
17. **Kiểm thử ít nhất hai session đồng thời** và lỗi mất response sau commit.
18. **Ghi metric/log có cấu trúc** để quan sát new/replayed/conflict/pending/outbox lag.

Đối với hệ thống gọi payment processor, shipping provider hoặc một API ngoài, phải đưa **idempotency/reconciliation ở phía đối tác** vào hợp đồng. Một transaction PostgreSQL không bao phủ hành động đã diễn ra ở một dịch vụ không cùng transaction.

## 38. Tài liệu PostgreSQL nên đối chiếu

Khi triển khai thật, xem tài liệu chính thức của **major version PostgreSQL đang chạy**:

- [INSERT / ON CONFLICT / RETURNING](https://www.postgresql.org/docs/current/sql-insert.html): cú pháp và ngữ nghĩa arbiter, DO NOTHING, DO UPDATE.
- [Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS): unique và NULLS NOT DISTINCT.
- [Indexes — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html): duy trì uniqueness.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): hành vi READ COMMITTED, REPEATABLE READ, SERIALIZABLE.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): khóa hàng, chờ khóa và deadlock.
- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): xử lý rẽ nhánh và kết quả trong function.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE 23505, 40001, 40P01.
- [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): luồng dữ liệu và data-modifying CTE.

`/current/` trỏ tới phiên bản hiện hành của tài liệu. Nếu hệ thống chạy server cũ hơn, mở tài liệu đúng major version, đặc biệt với các tính năng như `NULLS NOT DISTINCT`.

## 39. Tổng kết

Một lệnh ghi **retry-safe** không chỉ là một câu `INSERT` có thêm `ON CONFLICT`. Nó là một hợp đồng thống nhất giữa **client key, dữ liệu request, unique constraint, transaction, kết quả đã lưu và các side effect**.

Các nguyên tắc quan trọng nhất:

- **UNIQUE là hàng rào chống trùng khi ghi đồng thời.** `SELECT` kiểm tra trước không đủ.
- **ON CONFLICT DO NOTHING** giúp không tạo hai hàng cùng khóa, nhưng **không xác nhận payload giống nhau** và nhánh conflict không trả hàng `RETURNING`.
- **ON CONFLICT DO UPDATE** là upsert, không tự idempotent; phép cộng/trừ trong nhánh UPDATE vẫn lặp hiệu ứng.
- **Idempotency key phải có scope và gắn với payload canonical.** Cùng key khác payload phải được xử lý như xung đột.
- **Lưu kết quả xử lý** để retry có thể trả lại business ID/response mà không tạo operation mới.
- **Claim key và side effect phải commit nguyên tử** đối với các thao tác database ngắn; workflow dài cần state machine và recovery rõ ràng.
- **Transaction PostgreSQL không bảo đảm exactly-once ở hệ thống ngoài**; cần outbox, dedupe ở consumer và idempotency với đối tác.
- **Concurrency và isolation là phần thiết kế bắt buộc**, nhất là khi nhiều worker xử lý cùng một key.

Khi một yêu cầu có thể được phát lại, hãy bảo đảm **cùng logical request chỉ tạo một tác động nghiệp vụ được commit**, và mọi lần gửi lại sau đó đều nhận diện, xác minh rồi sử dụng kết quả đã lưu — thay vì lặp lại hành động ghi nguy hiểm.
