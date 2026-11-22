# Phân biệt trigger, ràng buộc, giá trị mặc định và logic ứng dụng trong PostgreSQL

Khi thiết kế một bảng PostgreSQL, bạn thường gặp những yêu cầu tưởng giống nhau:

- Nếu không truyền trạng thái đơn hàng, tự đặt là `draft`.
- Không cho tổng tiền âm.
- Không cho đơn hàng tham chiếu khách hàng không tồn tại.
- Tự tính thành tiền sau chiết khấu.
- Khi sửa đơn hàng, cập nhật `updated_at`.
- Không cho đơn đã hủy chuyển lại thành đã xác nhận.
- Ghi lại lịch sử thay đổi để kiểm tra.
- Sau khi đơn được xác nhận, gửi thông báo cho người mua.
- Hiển thị một thông báo dễ hiểu nếu người dùng điền dữ liệu sai.

Có thể cố giải quyết tất cả bằng **trigger**. Nhưng làm vậy dễ tạo hệ thống khó hiểu, chậm, khó kiểm thử và không rõ nơi nào thực sự bảo vệ dữ liệu. Cũng không thể chỉ kiểm tra ở **ứng dụng**, vì dữ liệu có thể được ghi qua API khác, psql, batch import, migration hoặc nhiều client đồng thời.

Cách tiếp cận bền vững là **đặt mỗi quy tắc ở cơ chế phù hợp nhất**:

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **`DEFAULT`** | Khi người ghi không truyền giá trị thì điền gì? | `status DEFAULT 'draft'` |
| **Ràng buộc** (`NOT NULL`, `CHECK`, `UNIQUE`, `FK`, …) | Trạng thái dữ liệu nào **không bao giờ được phép tồn tại**? | `discount <= subtotal` |
| **Generated column** | Giá trị nào được tính thuần từ những cột cùng hàng? | `total = subtotal - discount` |
| **Trigger** | Trước/sau một sự kiện DML, cần thực hiện logic gì phụ thuộc thao tác, `OLD`/`NEW` hoặc ghi nhận side effect giao dịch? | Ghi audit, chặn chuyển `cancelled -> confirmed` |
| **Logic ứng dụng** | Giao diện, orchestration và tích hợp bên ngoài cần làm gì? | Validation để báo lỗi đẹp, gọi cổng thanh toán, gửi email |
| **Transaction/service** | Nhiều bước ghi cần nhất quán và xử lý concurrency ra sao? | Tạo đơn + giữ tồn kho + outbox trong một transaction |

Bài học thuộc chương **Trigger và luật**, module **Database Engine Relational PostgreSQL**. Đây là tài liệu tự chứa, có một lab đơn hàng đầy đủ, truy vấn kiểm chứng, các tình huống concurrency, bài tập có đáp án và checklist triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn sẽ có thể:

1. Chọn đúng giữa `DEFAULT`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, generated column, trigger và logic ứng dụng.
2. Hiểu thời điểm các cơ chế được áp dụng và điều gì xảy ra khi dữ liệu không hợp lệ.
3. Viết trigger `BEFORE` và `AFTER` trên `INSERT`, `UPDATE`, `DELETE`.
4. Phân biệt trigger cấp hàng (`FOR EACH ROW`) và cấp câu lệnh (`FOR EACH STATEMENT`).
5. Sử dụng `OLD`, `NEW`, `TG_OP` và `RETURN NEW/OLD/NULL` đúng ngữ cảnh.
6. Dùng trigger cho quy tắc phụ thuộc trạng thái **trước và sau** một bản ghi.
7. Tránh dùng trigger thay constraint khi constraint có thể diễn đạt trực tiếp.
8. Hiểu các thay đổi do trigger thực hiện thuộc **cùng transaction**, không tự commit.
9. Đánh giá race condition, khóa hàng, deadlock và sự giới hạn của trigger đối với quy tắc nhiều hàng.
10. Chọn cách phát sự kiện bên ngoài bằng transactional outbox thay vì gửi HTTP/email trực tiếp trong trigger.
11. Phân biệt default, generated columns và logic ứng dụng về việc “ai là nguồn sự thật”.
12. Quan sát trigger, lập kế hoạch migration và kiểm thử các đường ghi khác nhau.

## 2. Bản đồ quyết định trước khi viết code

Một sơ đồ tư duy:

~~~mermaid
flowchart TD
    R["Có một quy tắc mới"] --> Q{"Chỉ cần giá trị khi INSERT thiếu field?"}
    Q -->|"Có"| D["DEFAULT / IDENTITY"]
    Q -->|"Không"| C{"Là bất biến biểu diễn được bằng constraint?"}
    C -->|"Có"| K["NOT NULL / CHECK / UNIQUE / FK / EXCLUDE"]
    C -->|"Không"| G{"Tính thuần từ cột cùng hàng?"}
    G -->|"Có"| GC["Generated column hoặc biểu thức khi SELECT"]
    G -->|"Không"| T{"Phụ thuộc sự kiện DML, OLD/NEW hoặc cần audit trong transaction?"}
    T -->|"Có"| TR["Xem xét trigger có phạm vi hẹp"]
    T -->|"Không"| A["Ứng dụng / service / transaction coordinator"]
    TR --> E{"Cần gọi hệ thống ngoài sau commit?"}
    E -->|"Có"| O["Outbox trong DB + worker xử lý sau commit"]
    E -->|"Không"| X["Đo và kiểm thử trigger"]
~~~

Đây là **quy tắc ưu tiên**, không phải hệ thống quyết định cứng. Có những yêu cầu cần phối hợp nhiều lớp: ứng dụng báo lỗi sớm, constraint vẫn bảo vệ dữ liệu, trigger ghi audit và service xử lý sự kiện sau commit.

**Nguyên tắc cốt lõi:** nếu một bất biến dữ liệu có thể diễn đạt bằng constraint khai báo, hãy ưu tiên constraint thay vì viết một trigger chỉ để ném lỗi tương tự.

## 3. Bốn cơ chế không cùng mục đích

### 3.1. DEFAULT: một giá trị thay thế khi thiếu input

~~~sql
status text NOT NULL DEFAULT 'draft'
~~~

Nếu câu `INSERT` bỏ cột `status` hoặc dùng từ khóa `DEFAULT`, PostgreSQL dùng giá trị mặc định. Nếu ứng dụng truyền `NULL` một cách tường minh, `DEFAULT` **không** tự thay nó thành `draft`; `NOT NULL` có thể báo lỗi.

### 3.2. Constraint: bất biến phải được cưỡng chế

~~~sql
discount numeric(12,2) NOT NULL
    DEFAULT 0
    CHECK (discount >= 0)
~~~

`CHECK` ngăn một số trạng thái dữ liệu không hợp lệ, bất kể ghi từ JDBC, psql, background job hay trigger khác.

### 3.3. Trigger: phản ứng với sự kiện dữ liệu

~~~sql
CREATE TRIGGER ...
BEFORE UPDATE ON ...
FOR EACH ROW
EXECUTE FUNCTION ...;
~~~

Trigger có ngữ cảnh `OLD`/`NEW` và biết thao tác `INSERT`/`UPDATE`/`DELETE`. Nó có thể sửa `NEW` trong `BEFORE ROW`, ghi một hàng audit trong `AFTER ROW` hoặc chặn chuyển trạng thái lịch sử.

### 3.4. Ứng dụng: điều phối trải nghiệm và ngoại hệ thống

Ứng dụng biết người dùng là ai, request thuộc workflow nào, nên hiện lỗi thế nào và khi nào gọi email/payment provider. Một trigger chạy trong database **không tự biết đầy đủ ý định request** và không phải vị trí tốt để gọi API mạng chậm hoặc không thể rollback.

## 4. “Kiểm tra ở ứng dụng” không thay được constraint

Giả sử API Java có:

~~~java
if (discount.compareTo(subtotal) > 0) {
    throw new IllegalArgumentException(
        "Discount cannot exceed subtotal"
    );
}
~~~

Đây là validation hữu ích để trả phản hồi ngay, nhưng một đường ghi khác vẫn có thể chạy:

~~~sql
UPDATE orders
SET discount = 1000
WHERE order_id = 1;
~~~

Nếu bảng không có constraint, PostgreSQL không tự biết quy tắc đó.

Phân tầng hợp lý:

- **Ứng dụng**: phát hiện lỗi sớm, thông điệp theo ngôn ngữ người dùng.
- **Database constraint**: bảo đảm bất biến với tất cả đường ghi được phép.
- **Service/transaction**: xử lý workflow nhiều bảng, concurrency và external systems.

Không nên lựa chọn “chỉ app” hay “chỉ DB” như hai phương án loại trừ nhau.

## 5. DEFAULT hoạt động khi nào?

Ví dụ độc lập:

~~~sql
CREATE TEMP TABLE default_demo (
    id integer GENERATED ALWAYS AS IDENTITY,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

INSERT INTO default_demo DEFAULT VALUES;

INSERT INTO default_demo (status)
VALUES (DEFAULT);

SELECT id, status, created_at
FROM default_demo
ORDER BY id;
~~~

Cả hai INSERT nhận status `draft`.

### DEFAULT không phải UPDATE trigger

Sau đó:

~~~sql
UPDATE default_demo
SET status = 'confirmed'
WHERE id = 1;
~~~

Không có chuyện `DEFAULT 'draft'` tự chạy lại và ghi đè `confirmed`. `DEFAULT` giải quyết giá trị tại thời điểm thêm hàng hoặc dùng từ khóa `DEFAULT` tường minh, không phải một lifecycle hook cho mọi UPDATE.

### DEFAULT không bảo đảm tính hợp lệ độc lập

~~~sql
status text DEFAULT 'draft'
~~~

vẫn cho phép giá trị `'unexpected'` nếu không có constraint. Muốn ràng buộc miền giá trị, cần `CHECK`/enum/domain hoặc một mô hình tham chiếu phù hợp.

## 6. Explicit NULL khác bỏ cột

~~~sql
CREATE TEMP TABLE default_null_demo (
    id integer PRIMARY KEY,
    state text NOT NULL DEFAULT 'new'
);

-- Hợp lệ: bỏ state, nhận DEFAULT.
INSERT INTO default_null_demo(id) VALUES (1);

-- CỐ Ý LỖI: explicit NULL vi phạm NOT NULL.
INSERT INTO default_null_demo(id, state)
VALUES (2, NULL);
~~~

Lệnh thứ hai sẽ báo lỗi. Nếu đang trong explicit SQL transaction, transaction có thể ở trạng thái aborted cho tới khi rollback theo quy tắc PostgreSQL.

**Đừng cấu hình application serializer luôn gửi mọi field với null** rồi kỳ vọng database tự dùng DEFAULT. Muốn DEFAULT, hãy bỏ cột khỏi INSERT hoặc dùng `DEFAULT` một cách tường minh.

## 7. Các loại DEFAULT thường gặp

| Nhu cầu | Cách biểu diễn |
| --- | --- |
| Trạng thái ban đầu | `status DEFAULT 'draft'` |
| Thời điểm tạo | `created_at DEFAULT transaction_timestamp()` |
| Định danh số tăng | `GENERATED ... AS IDENTITY` |
| ID UUID (tùy phiên bản/cấu hình) | Default gọi một hàm UUID phù hợp |
| Giá trị cấu hình mặc định | `language DEFAULT 'vi'` |
| Giá trị phụ thuộc cột khác | **Không** dùng DEFAULT tham chiếu trực tiếp cột cùng hàng; xem generated column |
| Giá trị tự cập nhật mỗi UPDATE | **Không** tự xảy ra vì DEFAULT; xem trigger/app |

### DEFAULT có thể dùng hàm thời gian

~~~sql
created_at timestamptz NOT NULL
    DEFAULT transaction_timestamp()
~~~

`transaction_timestamp()` phản ánh thời điểm bắt đầu transaction. `statement_timestamp()` và `clock_timestamp()` có semantics khác. Chọn một cách thống nhất để hệ thống audit hiểu đúng; không coi mọi hàm `now()`/`clock_timestamp()` có cùng hành vi trong transaction dài.

### Một mặc định không phải quy tắc lịch sử

`status DEFAULT 'draft'` không ngăn `cancelled -> confirmed`. Nó chỉ đưa ra giá trị khởi đầu khi status không được truyền.

## 8. Generated column khác DEFAULT

Nếu giá trị được tính trực tiếp từ các cột cùng hàng:

~~~sql
subtotal numeric(12,2) NOT NULL,
discount numeric(12,2) NOT NULL DEFAULT 0,
total numeric(12,2)
    GENERATED ALWAYS AS (subtotal - discount) STORED
~~~

thì `total` không phải giá trị “chỉ điền khi INSERT”; nó là giá trị được tính từ `subtotal` và `discount`.

### Sự khác biệt

| Tiêu chí | DEFAULT | Generated column |
| --- | --- | --- |
| Khi nào tính | Khi cần giá trị mặc định cho INSERT hoặc thao tác DEFAULT | Theo biểu thức generated khi hàng được ghi |
| Có tham chiếu cột khác cùng hàng? | Không theo cách default thông thường | Có, trong giới hạn biểu thức |
| Có thể nhập giá trị tùy ý cho cột? | Có thể nếu constraint cho phép | `GENERATED ALWAYS` không nhận giá trị thường theo cách nhập cột bình thường |
| Dùng cho `updated_at` dựa vào thời gian thực? | Không tự chạy khi UPDATE | Biểu thức generated có hạn chế immutability; không phải giải pháp cho clock timestamp |
| Có thể thay bằng biểu thức SELECT? | Tùy nhu cầu | Có thể không lưu cột nếu chỉ cần tính lúc đọc |

Generated column ở PostgreSQL yêu cầu biểu thức phù hợp giới hạn immutability và chỉ tham chiếu dữ liệu được cho phép. **Không dùng nó để đọc bảng khác hoặc chạy logic tùy ý có side effect**.

## 9. Constraint: lớp bảo vệ dữ liệu được khai báo

Những constraint thường gặp:

| Constraint | Bất biến điển hình |
| --- | --- |
| `NOT NULL` | Email/tổng tiền không được NULL |
| `CHECK` | Discount không âm và không lớn hơn subtotal |
| `UNIQUE` | Không có hai email normalized giống nhau |
| `PRIMARY KEY` | Có định danh duy nhất, không NULL |
| `FOREIGN KEY` | Đơn phải tham chiếu khách hàng tồn tại |
| `EXCLUDE` | Không cho một số hàng có sự chồng lấn theo quan hệ toán tử |
| `DEFERRABLE` ở các loại hỗ trợ | Hoãn một số kiểm tra tới cuối transaction |

Constraint là lời hứa dữ liệu phải thỏa. PostgreSQL có thể dùng cơ chế nội bộ khác nhau để cưỡng chế, nhưng **mục tiêu khai báo** vẫn rõ hơn một trigger tự viết làm cùng việc.

## 10. CHECK chỉ xét trạng thái hàng và NULL cần thận trọng

~~~sql
CREATE TEMP TABLE check_demo (
    id integer PRIMARY KEY,
    discount numeric CHECK (discount >= 0)
);
~~~

`CHECK (discount >= 0)` **không tự ngăn NULL**: trong SQL, `NULL >= 0` cho UNKNOWN, và một CHECK nhìn chung được coi là đạt nếu điều kiện không phải FALSE.

Muốn không cho NULL:

~~~sql
CREATE TEMP TABLE check_strict_demo (
    id integer PRIMARY KEY,
    discount numeric NOT NULL
        CHECK (discount >= 0)
);
~~~

### CHECK có thể kết hợp nhiều cột cùng hàng

~~~sql
CHECK (discount <= subtotal)
~~~

Đây là bất biến cùng hàng, thích hợp với CHECK. Không cần một `BEFORE INSERT OR UPDATE` trigger chỉ để làm cùng phép so sánh.

### CHECK không phù hợp để xem dữ liệu ở hàng khác

Một điều kiện tổng tiền của nhiều đơn hoặc tổng tồn kho của nhiều sản phẩm **không nên** cố giải quyết bằng CHECK gọi một hàm đi đọc toàn bộ bảng khác. PostgreSQL không duy trì CHECK theo các thay đổi của hàng khác như một cross-table assertion và có các giả định về tính bất biến của biểu thức.

Với quy tắc nhiều hàng, phải thiết kế constraint phù hợp (UNIQUE/FK/EXCLUDE), transaction locking, hoặc mô hình dữ liệu khác.

## 11. UNIQUE và PRIMARY KEY mạnh hơn một trigger đếm trùng

Một cách sai để chống email trùng:

~~~text
BEFORE INSERT trigger:
  SELECT count(*) WHERE email = NEW.email
  IF count > 0 THEN RAISE EXCEPTION
~~~

Hai transaction có thể cùng chưa nhìn thấy email của nhau, rồi cả hai đi qua kiểm tra.

**UNIQUE index/constraint được PostgreSQL thực thi đồng bộ với concurrency** theo cơ chế của nó, phù hợp hơn cho bất biến duy nhất.

Ví dụ:

~~~sql
CREATE TEMP TABLE unique_demo (
    id integer PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

Không cần viết trigger “nếu SELECT chưa thấy email thì cho INSERT” để thay UNIQUE.

### Unique nhiều cột hoặc chỉ trên tập hàng hoạt động

Có thể có `UNIQUE (tenant_id, external_id)` hoặc **partial unique index** để chỉ giới hạn hàng chưa xóa mềm:

~~~sql
-- Ví dụ ý tưởng, không phụ thuộc lab chính:
CREATE UNIQUE INDEX ux_live_email
ON some_schema.users (tenant_id, lower(email))
WHERE deleted_at IS NULL;
~~~

Đây là cú pháp minh họa: phải có bảng/cột thật tương ứng mới chạy được. Partial unique index không phải UNIQUE constraint thông thường có thể DEFERRABLE theo cùng cách; cần hiểu tác động khi chọn.

## 12. FOREIGN KEY không chỉ là kiểm tra tồn tại đơn giản

~~~sql
customer_id bigint NOT NULL
    REFERENCES customers(customer_id)
~~~

Foreign key có semantics liên quan đến concurrency, cập nhật/xóa hàng cha và các action `ON DELETE`/`ON UPDATE`.

PostgreSQL hiện thực nhiều hành vi FK bằng trigger nội bộ, nhưng người viết ứng dụng nên khai báo **FOREIGN KEY** nếu mục tiêu là toàn vẹn tham chiếu.

**Đừng tự thay FK bằng trigger SELECT parent rồi cho INSERT**; thiết kế tự viết rất dễ gặp race condition và thiếu các trường hợp cascade, khóa hoặc transaction.

### Khi nào FK chưa đủ?

Nếu cần “chỉ đặt đơn cho khách có state = active”, FK chỉ bảo đảm khách tồn tại, không bảo đảm điều kiện `active` của quan hệ khác. Quy tắc đó có thể cần service transaction/lock hoặc mô hình khác. Một trigger kiểm tra state cũng phải giải quyết cập nhật đồng thời phía bảng khách hàng, không chỉ viết SELECT.

## 13. Lab: tạo schema cửa hàng

Lab dùng bốn bảng:

- `customers`: khách hàng và email chuẩn hóa.
- `orders`: đơn hàng, trạng thái và tiền.
- `order_audit`: lịch sử DML đối với đơn.
- `outbox`: sự kiện đã commit để worker bên ngoài gửi thông báo.

**Cảnh báo:** câu `DROP SCHEMA ... CASCADE` xóa tất cả đối tượng trong schema lab. Chỉ chạy trong **database thực hành riêng**, tuyệt đối không dùng nguyên câu lệnh trên production.

~~~sql
-- CHỈ CHẠY TRÊN DATABASE LAB.
DROP SCHEMA IF EXISTS guardrail_lab CASCADE;
CREATE SCHEMA guardrail_lab;

CREATE TABLE guardrail_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL,
    normalized_email text
        GENERATED ALWAYS AS (lower(btrim(email))) STORED,
    full_name text NOT NULL,
    state text NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'blocked')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    CONSTRAINT uq_customers_normalized_email
        UNIQUE (normalized_email)
);

CREATE TABLE guardrail_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES guardrail_lab.customers(customer_id)
        ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'cancelled')),
    subtotal numeric(12,2) NOT NULL DEFAULT 0
        CHECK (subtotal >= 0),
    discount numeric(12,2) NOT NULL DEFAULT 0
        CHECK (discount >= 0),
    total numeric(12,2)
        GENERATED ALWAYS AS (subtotal - discount) STORED,
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    CONSTRAINT chk_order_discount
        CHECK (discount <= subtotal),
    CONSTRAINT chk_confirmed_order_positive
        CHECK (status <> 'confirmed' OR subtotal > discount)
);

CREATE TABLE guardrail_lab.order_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    operation text NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_row jsonb,
    new_row jsonb,
    recorded_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    db_role name NOT NULL
        DEFAULT current_user
);

CREATE TABLE guardrail_lab.outbox (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    delivery_status text NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'processing', 'sent')),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
~~~

### Tại sao dùng từng cơ chế?

| Nhu cầu | Cơ chế trong lab |
| --- | --- |
| Khách có email chuẩn hóa | Generated `normalized_email` |
| Không trùng email chuẩn hóa | `UNIQUE (normalized_email)` |
| Trạng thái khách ban đầu active | `DEFAULT 'active'` |
| Trạng thái đơn ban đầu draft | `DEFAULT 'draft'` |
| Không có status lạ | `CHECK status IN (...)` |
| Không tiền âm/discount vượt subtotal | `CHECK` kết hợp `NOT NULL` |
| Tổng tiền = subtotal - discount | Generated `total` |
| Chỉ đơn có khách tồn tại | `FOREIGN KEY` |
| Cập nhật timestamp khi sửa | Trigger sẽ tạo sau |
| Không cho đảo ngược transition bị cấm | Trigger so sánh `OLD.status`/`NEW.status` |
| Lịch sử thay đổi | AFTER trigger ghi audit trong transaction |
| Gửi thông báo sau commit | Trigger/outbox + worker ứng dụng |

**`db_role = current_user` là role DB thực thi**, không tự bảo đảm định danh end user thật khi nhiều request dùng chung connection role. Audit chuyên nghiệp cần thiết kế danh tính và quyền ghi chặt chẽ.

## 14. Khai báo dữ liệu seed

~~~sql
INSERT INTO guardrail_lab.customers (
    customer_id, email, full_name
)
VALUES
    (101, 'Lan@Example.Test', 'Lan'),
    (102, 'minh@example.test', 'Minh');

-- Tạm thời tạo orders trước khi cài audit trigger.
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal, discount
)
VALUES
    (101, 'draft',     120.00, 20.00),
    (101, 'confirmed',  60.00,  0.00),
    (102, 'cancelled',  50.00, 10.00);

SELECT
    order_id,
    customer_id,
    status,
    subtotal,
    discount,
    total,
    created_at,
    updated_at
FROM guardrail_lab.orders
ORDER BY order_id;
~~~

Sau reset schema, identity sẽ gán `order_id` dự kiến 1, 2, 3. Nếu đã chạy nhiều bài DML có INSERT, số sequence có thể nhảy và không tái sử dụng sau rollback; khi đó không nên giả định mã ID là liên tục.

Kết quả nghiệp vụ:

| order_id | status | subtotal | discount | total |
| ---: | --- | ---: | ---: | ---: |
| 1 | draft | 120.00 | 20.00 | 100.00 |
| 2 | confirmed | 60.00 | 0.00 | 60.00 |
| 3 | cancelled | 50.00 | 10.00 | 40.00 |

### Truy vấn thử default

~~~sql
BEGIN;

INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (101, 75.00)
RETURNING order_id, status, subtotal, discount, total;

ROLLBACK;
~~~

Trong transaction, status là `draft`, discount là 0, total là 75.00. Đây là **DEFAULT + generated column**, không có trigger nào cần thiết.

## 15. Kiểm tra constraints bằng các câu lệnh riêng

Các ví dụ dưới đây **cố ý gây lỗi**, nên chạy từng câu riêng; sau lỗi trong một explicit SQL transaction phải rollback trước khi chạy ví dụ khác.

### Không có khách hàng

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (999, 10.00);
~~~

Dự kiến: `foreign_key_violation`, SQLSTATE `23503`.

### Discount vượt subtotal

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal, discount
)
VALUES (101, 10.00, 50.00);
~~~

Dự kiến: `check_violation`, SQLSTATE `23514`.

### Trạng thái không nằm trong tập

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal
)
VALUES (101, 'delivered', 10.00);
~~~

Dự kiến: `check_violation`, không cần trigger kiểm tra một danh sách giá trị đơn giản.

### Confirmed nhưng tổng tiền không dương

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal, discount
)
VALUES (101, 'confirmed', 20.00, 20.00);
~~~

Dự kiến: `chk_confirmed_order_positive` không cho hàng được lưu. Vì quy tắc chỉ phụ thuộc các cột **cùng hàng ở trạng thái mới**, CHECK phù hợp hơn một trigger lịch sử.

## 16. Trigger chỉ trở nên cần thiết khi có lịch sử thao tác

Bảng orders có constraint:

~~~sql
CHECK (status IN ('draft', 'confirmed', 'cancelled'))
~~~

Constraint này cho phép ba giá trị, nhưng không biết **giá trị trước đó** là gì. Một số quy tắc chuyển trạng thái cần `OLD` và `NEW`:

- `draft -> confirmed`: cho phép nếu CHECK khác thỏa.
- `draft -> cancelled`: cho phép.
- `confirmed -> cancelled`: cho phép.
- `confirmed -> draft`: không cho.
- `cancelled -> confirmed/draft`: không cho.
- Giữ nguyên status khi sửa field khác: cho phép nếu các constraint còn thỏa.

~~~mermaid
flowchart LR
    A["draft"] -->|"confirm"| B["confirmed"]
    A -->|"cancel"| C["cancelled"]
    B -->|"cancel"| C
    B -.->|"forbidden: back to draft"| A
    C -.->|"forbidden: reopen"| B
~~~

Đây là **quy tắc lịch sử**, không phải chỉ một giá trị hiện tại. `CHECK` thông thường không truy cập `OLD`. Trigger `BEFORE UPDATE` là một lựa chọn phù hợp nếu tất cả đường ghi phải tuân thủ state machine.

## 17. Viết trigger function cho transition

Trong PostgreSQL, trigger gọi một **trigger function** có kiểu trả về `trigger`:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.enforce_order_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF OLD.status = 'cancelled'
       AND NEW.status IS DISTINCT FROM OLD.status
    THEN
        RAISE EXCEPTION
            'Cancelled order % cannot change status from % to %',
            OLD.order_id, OLD.status, NEW.status
            USING ERRCODE = 'P2001';
    END IF;

    IF OLD.status = 'confirmed'
       AND NEW.status = 'draft'
    THEN
        RAISE EXCEPTION
            'Confirmed order % cannot return to draft',
            OLD.order_id
            USING ERRCODE = 'P2002';
    END IF;

    RETURN NEW;
END;
$fn$;
~~~

Gắn vào bảng:

~~~sql
CREATE TRIGGER trg_orders_10_transition
BEFORE UPDATE ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.enforce_order_transition();
~~~

### Vì sao RETURN NEW?

Với `BEFORE ... FOR EACH ROW`, trigger function trả `NEW` để PostgreSQL tiếp tục thao tác trên bản ghi (có thể đã được chỉnh sửa). Trả `NULL` ở BEFORE ROW sẽ yêu cầu bỏ qua thao tác cho hàng đó, một hành vi có thể làm người gọi bất ngờ.

Nếu mục tiêu là **từ chối thao tác không hợp lệ**, dùng `RAISE EXCEPTION` rõ ràng thay vì `RETURN NULL` âm thầm khiến `UPDATE 0`.

### Trigger không thay CHECK

Function trên **không** kiểm tra `discount <= subtotal` và không liệt kê tất cả status hợp lệ. Những quy tắc đó đã có constraint. Phân chia trách nhiệm làm code ngắn hơn, có mã lỗi rõ ràng và ít trùng lặp.

## 18. OLD và NEW tồn tại ở sự kiện nào?

| Trigger event | `OLD` | `NEW` |
| --- | --- | --- |
| `INSERT` cấp hàng | Không có hàng cũ | Hàng mới |
| `UPDATE` cấp hàng | Hàng trước sửa | Hàng sau sửa |
| `DELETE` cấp hàng | Hàng trước xóa | Không có hàng mới |
| `TRUNCATE` | Không có per-row OLD/NEW | Không có per-row OLD/NEW |

`TG_OP` cho biết tên operation, chẳng hạn `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`.

Các biến ngữ cảnh khác gồm `TG_TABLE_NAME`, `TG_TABLE_SCHEMA`, `TG_NAME`, `TG_WHEN`, `TG_LEVEL`, `TG_ARGV` và `TG_NARGS`.

**Không dùng `NEW` trong DELETE trigger hoặc `OLD` trong INSERT trigger** rồi kỳ vọng chúng mang một hàng có nghĩa.

## 19. BEFORE, AFTER và INSTEAD OF khác nhau

| Loại trigger | Thời điểm/công dụng chính |
| --- | --- |
| `BEFORE ROW` | Kiểm tra/chỉnh `NEW` trước khi lưu hàng; có thể skip hàng |
| `AFTER ROW` | Phản ứng sau thao tác hàng, phù hợp audit/side effect trong transaction |
| `BEFORE STATEMENT` | Một lần trước câu DML, không có cặp OLD/NEW theo hàng |
| `AFTER STATEMENT` | Một lần sau câu DML, có thể dùng transition relations trong ngữ cảnh hỗ trợ |
| `INSTEAD OF` | Thường trên view để định nghĩa cách xử lý DML thay cho operation mặc định |

### Lựa chọn thực hành

- **Chuẩn hóa giá trị trước khi ghi:** có thể dùng BEFORE ROW, nhưng cân nhắc generated column/DEFAULT nếu phù hợp.
- **Ghi audit sau khi hàng đã qua các bước xử lý thích hợp:** AFTER ROW.
- **Bắt thay đổi của nhiều hàng một lần:** AFTER STATEMENT kết hợp transition tables nếu phù hợp.
- **DML qua view phức tạp:** INSTEAD OF trigger khi không dùng được cơ chế updatable view tự động.

Không có lý do đặt mọi loại trigger thành BEFORE. Thời điểm thực thi làm thay đổi semantics và dữ liệu sẵn có.

## 20. Trigger cập nhật updated_at khi UPDATE

`DEFAULT transaction_timestamp()` chỉ giúp điền `updated_at` ban đầu. Nó **không tự chạy lại trên UPDATE**.

Tạo BEFORE trigger:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.stamp_order_update()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW IS DISTINCT FROM OLD THEN
        NEW.updated_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_orders_20_stamp
BEFORE UPDATE ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.stamp_order_update();
~~~

### Vì sao có điều kiện IS DISTINCT FROM?

Nếu update request không thực sự thay đổi các field, trigger cố tránh thay `updated_at` vô ích.

**Nhưng vẫn cần lưu ý:** một câu `UPDATE` đã chạy trên một hàng có thể tạo tuple version mới ngay cả khi các giá trị cột không khác. Chỉ vì trigger giữ timestamp cũ **không có nghĩa PostgreSQL bỏ qua toàn bộ chi phí UPDATE**.

Nếu API có nhiều request idempotent/no-op, có thể thêm điều kiện `WHERE ... IS DISTINCT FROM ...` để tránh gửi một UPDATE không cần thiết.

### Dùng clock_timestamp hay transaction_timestamp?

- `transaction_timestamp()` có cùng mốc thời gian trong transaction.
- `clock_timestamp()` lấy thời gian thực tại lúc gọi, có thể khác giữa các hàng.
- Chọn một semantics và ghi lại. Không có một lựa chọn đúng cho mọi audit/system.

## 21. Tên trigger và thứ tự cùng loại

Trong PostgreSQL, nếu nhiều trigger **cùng loại, cùng event** trên một bảng, thứ tự thực thi giữa chúng thường theo **tên trigger theo bảng chữ cái**, không phải ngày tạo.

Trong lab có:

~~~text
trg_orders_10_transition
trg_orders_20_stamp
~~~

Điều đó giúp diễn đạt: kiểm tra transition trước, rồi stamp timestamp (đều là BEFORE UPDATE ROW).

**Không nên xây logic nghiệp vụ quá phức tạp chỉ dựa vào quy ước tên.** Nếu hai hành động phụ thuộc chặt nhau, cân nhắc gom vào một function có trình tự rõ; kiểm thử hành vi khi thêm trigger mới hoặc thay tên.

### BEFORE trigger có thể chỉnh NEW

Một BEFORE trigger khác sửa `NEW.status` có thể làm thay đổi điều kiện mà trigger phía sau nhìn thấy. Vì vậy tính đúng đắn không chỉ phụ thuộc câu `UPDATE SET status=...` ban đầu mà còn phụ thuộc pipeline trigger.

## 22. Thử cập nhật status và timestamp

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1
RETURNING
    order_id,
    status,
    subtotal,
    discount,
    total,
    updated_at;

ROLLBACK;
~~~

Trong transaction:

- `draft -> confirmed` hợp lệ.
- CHECK đảm bảo total > 0.
- Trigger stamp gán `updated_at` mới.
- Không có lỗi trạng thái.
- `ROLLBACK` hoàn tác thay đổi và timestamp.

### Thử một transition bị cấm

~~~sql
-- CỐ Ý GÂY LỖI trên seed gốc:
UPDATE guardrail_lab.orders
SET status = 'draft'
WHERE order_id = 2;
~~~

Trigger phát `P2002` vì đơn 2 đã confirmed.

Với transaction explicit, cần `ROLLBACK` sau câu SQL lỗi trước khi tiếp tục; không cố chạy nhiều ví dụ bên trong một transaction đã aborted.

## 23. Ghi lịch sử bằng AFTER ROW trigger

Audit cần lưu:

- ID đơn hàng.
- Loại thao tác.
- Trạng thái hàng **trước** và **sau**.
- Thời điểm ghi.
- Database role thực thi.

Function:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.audit_order_change()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'INSERT', NULL, to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'UPDATE',
            to_jsonb(OLD), to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            OLD.order_id, 'DELETE',
            to_jsonb(OLD), NULL
        );

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER trg_orders_90_audit
AFTER INSERT OR UPDATE OR DELETE
ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.audit_order_change();
~~~

### Vì sao AFTER?

Ta muốn audit trạng thái cuối của row sau các BEFORE triggers và bước DML. Với AFTER ROW trigger, giá trị trả về từ trigger function **được PostgreSQL bỏ qua** về mặt quyết định hàng có bị ghi hay không. Trả `NEW`/`OLD` trong function là dễ hiểu, nhưng **không mang semantics đổi hàng** như BEFORE ROW.

### Một audit trigger không tự bảo vệ bảng audit

Để có audit đáng tin:

- Hạn chế quyền UPDATE/DELETE trên `order_audit`.
- Kiểm soát owner, migration role và quyền disable trigger.
- Có retention, partitioning/archival khi audit lớn.
- Không dựa `current_user` như bằng chứng không thể giả mạo về end-user identity.
- Đánh giá compliance nếu cần immutable/tamper-evident audit độc lập.

Trigger ghi audit là một **cơ chế quan sát giao dịch**, chưa phải hệ thống kiểm toán chống chỉnh sửa hoàn chỉnh.

## 24. Audit trigger cũng thuộc cùng SQL transaction

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET discount = 25.00
WHERE order_id = 1;

SELECT
    audit_id,
    order_id,
    operation,
    old_row ->> 'discount' AS old_discount,
    new_row ->> 'discount' AS new_discount
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Trong transaction, dòng audit của UPDATE có thể nhìn thấy. Sau `ROLLBACK`, thay đổi đơn và dòng audit mới đều bị hủy.

**Không có autonomous commit mặc định** cho AFTER trigger. Nếu một transaction bị rollback, audit ghi trong chính transaction đó cũng rollback.

Đây là lý do cần tách yêu cầu:

- Audit **những thay đổi đã commit**: trigger cùng transaction thường phù hợp.
- Ghi nhận **mọi lần thử thất bại hoặc bị rollback**: cần log phía ứng dụng/hệ thống quan sát hoặc kênh riêng với semantics rõ ràng.

## 25. Trigger lỗi thì điều gì xảy ra?

Giả sử AFTER audit trigger INSERT vào bảng audit gặp lỗi constraint. Nếu lỗi không được xử lý theo một cơ chế hợp lệ, statement gốc bị lỗi.

Ví dụ khái niệm:

~~~text
UPDATE orders
  -> BEFORE transition pass
  -> UPDATE row
  -> AFTER audit INSERT fails
  -> SQL statement fails
  -> những thay đổi thuộc statement bị rollback
~~~

Trong một transaction explicit, lỗi làm transaction chuyển trạng thái thất bại cho tới khi rollback hoặc được xử lý qua ngữ cảnh savepoint/subtransaction phù hợp.

Điều này đôi khi đúng vì mục tiêu là **“không có order update nếu không ghi được audit”**. Nhưng cũng có thể tạo sự phụ thuộc vận hành ngoài ý muốn: bảng audit hết dung lượng làm mọi UPDATE order thất bại.

**Phải quyết định rõ audit là bắt buộc hay best-effort.** Không nuốt lỗi audit trong trigger bằng `WHEN OTHERS THEN NULL` nếu requirement yêu cầu toàn vẹn audit.

## 26. AFTER trigger không thể “tự sửa NEW” để thay row

Cách sai về ý định:

~~~sql
CREATE FUNCTION ... RETURNS trigger AS $fn$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

-- Nếu function này gắn AFTER UPDATE,
-- sửa NEW không tự thay phiên bản row đã ghi.
~~~

Muốn thay nội dung hàng đang được ghi, dùng **BEFORE ROW** trigger hoặc một cơ chế khai báo thích hợp.

Muốn tạo side effect trong transaction sau khi thay đổi thành công, dùng **AFTER**.

### Vì sao không UPDATE cùng bảng ngay trong AFTER trigger?

Một AFTER UPDATE trigger chạy `UPDATE orders SET ... WHERE order_id = NEW.order_id` có thể kích hoạt **một vòng trigger UPDATE mới**, gây đệ quy, work thừa hoặc lỗi. Để stamp timestamp cùng hàng, sửa `NEW` trong BEFORE ROW sẽ thường đơn giản hơn.

## 27. RETURN NULL trong BEFORE ROW nghĩa là gì?

~~~sql
CREATE FUNCTION guardrail_lab.skip_some_rows()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.subtotal = 0 THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$fn$;
~~~

Nếu gắn vào `BEFORE INSERT FOR EACH ROW`, trả `NULL` khiến PostgreSQL **bỏ qua thao tác đối với hàng đó**. Những row triggers tiếp theo cho hàng bị bỏ qua có thể không chạy theo semantics.

Đây là lựa chọn rất nhạy cảm:

- Caller có thể nghĩ đã INSERT nhưng thực ra không có hàng.
- `RETURNING` và số hàng tác động có thể ít hơn dự kiến.
- Dữ liệu không hợp lệ có thể bị bỏ qua âm thầm thay vì báo lỗi.

**Nếu quy tắc là “không cho subtotal = 0”, dùng CHECK; nếu là “không cho chuyển trạng thái”, dùng RAISE EXCEPTION rõ ràng.** RETURN NULL chỉ phù hợp khi việc bỏ qua hàng là hành vi nghiệp vụ được thiết kế có chủ ý.

## 28. Row-level và statement-level trigger

Một câu:

~~~sql
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE status = 'draft';
~~~

có thể cập nhật nhiều hàng.

| Loại | Số lần gọi |
| --- | --- |
| `FOR EACH ROW` | Một lần cho từng hàng liên quan |
| `FOR EACH STATEMENT` | Một lần cho cả statement, kể cả statement không sửa hàng nào trong nhiều trường hợp |

Row-level phù hợp khi cần `OLD`/`NEW` cho từng hàng. Statement-level phù hợp khi cần logic tổng hợp hoặc ghi nhận một sự kiện trên cả statement.

### Trigger statement và transition tables

PostgreSQL hỗ trợ **transition relations** cho một số AFTER triggers, cho phép xem tập hàng OLD/NEW của statement.

Ví dụ khái niệm:

~~~sql
CREATE TRIGGER trg_orders_bulk_audit
AFTER UPDATE ON guardrail_lab.orders
REFERENCING
    OLD TABLE AS old_orders
    NEW TABLE AS new_orders
FOR EACH STATEMENT
EXECUTE FUNCTION guardrail_lab.some_statement_trigger();
~~~

Câu này **minh họa cú pháp**, không chạy độc lập vì chưa có function `some_statement_trigger`. Transition table có giới hạn cú pháp/event/loại bảng cụ thể; không tự dùng với mọi trigger mode hoặc `UPDATE OF ...` tùy tiện.

### Chọn row hay statement?

- Cần thay `NEW.updated_at` từng hàng → BEFORE ROW.
- Cần audit từng trạng thái hàng → AFTER ROW.
- Cần xử lý một batch lớn theo tập hàng → cân nhắc AFTER STATEMENT với transition tables.
- Cần đếm DML tổng quát → statement trigger có thể phù hợp, nhưng nên tránh chèn nhiều dòng/scan lại toàn bảng vô ích.

## 29. ON CONFLICT và trigger cần được hiểu riêng

Ứng dụng có thể dùng:

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (101, 20.00);
~~~

Nhưng để upsert thường dùng `INSERT ... ON CONFLICT ... DO UPDATE` trên bảng có unique key phù hợp.

**Không giả định một câu SQL chỉ gây đúng một loại trigger event.** Với `INSERT ... ON CONFLICT DO UPDATE`, PostgreSQL có những quy tắc kích hoạt INSERT/UPDATE triggers tùy có conflict và loại trigger. Một số BEFORE INSERT triggers có thể chạy trước khi xác định nhánh conflict; kết quả từ BEFORE triggers có thể ảnh hưởng dữ liệu được xử lý trong nhánh UPDATE.

### Hệ quả

- Tránh trigger có side effect bất ngờ hoặc không idempotent.
- Kiểm thử cả nhánh INSERT, conflict DO NOTHING và conflict DO UPDATE.
- Không dựa chỉ vào tên câu SQL “INSERT” để suy ra không trigger UPDATE nào chạy.
- Với audit, cần biết DML thực sự đã xảy ra để ghi operation đúng.

Nếu mục tiêu chỉ xử lý trùng key bình thường, **UNIQUE + ON CONFLICT** thường tốt hơn trigger tự SELECT xem key đã tồn tại.

## 30. Khóa, concurrency và giới hạn của trigger

Trigger chạy cùng transaction, nhưng **việc có trigger không tự đảm bảo mọi quy tắc nhiều hàng đều an toàn khi đồng thời**.

Ví dụ sai:

~~~text
Trigger BEFORE INSERT orders:
  SELECT count(*) FROM orders WHERE customer_id = NEW.customer_id;
  IF count >= 5 THEN reject;
~~~

Hai transaction có thể cùng thấy 4 đơn đã tồn tại rồi đều INSERT, kết quả thành 6 đơn nếu không có cơ chế đồng bộ phù hợp.

### Cách xử lý quy tắc nhiều hàng

- Nếu có thể biểu diễn bằng UNIQUE/FK/EXCLUDE, ưu tiên constraint/index tương ứng.
- Với quota, cân nhắc **counter row** được khóa/cập nhật atomically hoặc thiết kế reservation phù hợp.
- Dùng `SELECT ... FOR UPDATE` cho hàng điều phối khi transaction cần giữ một lock ổn định.
- Xem xét isolation `SERIALIZABLE` và logic retry toàn transaction khi phù hợp.
- Thiết kế thứ tự lấy lock nhất quán để giảm deadlock.
- Không chỉ thêm một SELECT trong trigger rồi cho rằng race condition biến mất.

### Trigger với OLD/NEW trên cùng hàng

Quy tắc transition trong lab so sánh `OLD.status`/`NEW.status` của chính hàng đang UPDATE. PostgreSQL phối hợp khóa và phiên bản hàng trong UPDATE theo isolation semantics, nên đây là trường hợp phù hợp hơn việc trigger tự đọc rồi đếm nhiều hàng ở nơi khác.

Ở `REPEATABLE READ`/`SERIALIZABLE`, transaction có thể gặp `40001`; ứng dụng cần retry phù hợp chứ không nuốt lỗi rồi tự coi là thành công.

## 31. Logic ứng dụng vẫn cần tồn tại

Ví dụ khi người dùng gửi request xác nhận đơn:

1. Xác thực danh tính và quyền truy cập.
2. Kiểm tra thông tin giỏ hàng/cổng thanh toán.
3. Validate form để trả lỗi dễ hiểu.
4. Bắt đầu transaction.
5. Thực hiện các câu SQL cập nhật dữ liệu và outbox.
6. Commit; phản hồi trạng thái theo API contract.
7. Worker xử lý email/payment webhook khi sự kiện đã commit.

Database constraints/trigger bảo vệ dữ liệu, nhưng **không thể thay toàn bộ quy trình giao tiếp với người dùng và hệ thống ngoài**.

### Không trông chờ trigger để gọi HTTP

Một trigger gửi HTTP/email ngay khi update order có nhiều rủi ro:

- External request có thể thành công nhưng transaction DB sau đó rollback.
- Network timeout khiến row lock/transaction giữ quá lâu.
- Trigger chạy lại có thể gửi trùng.
- Retry transaction có thể tạo nhiều lần gửi.
- Khó quản lý timeout/circuit breaker/observability.
- Phát sinh quyền truy cập mạng và rủi ro bảo mật từ database.

Dùng **transactional outbox** khi cần liên kết sự kiện DB với công việc xử lý sau commit.

## 32. Transactional outbox: ghi ý định gửi, không gửi ngay

Bảng `guardrail_lab.outbox` đã tạo ở lab. Khi đơn chuyển thành confirmed, ta muốn có một event pending.

Function:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.queue_order_confirmed()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO guardrail_lab.outbox (
        event_key,
        event_type,
        payload
    )
    VALUES (
        'order-confirmed-' || NEW.order_id::text,
        'order.confirmed',
        jsonb_build_object(
            'order_id', NEW.order_id,
            'customer_id', NEW.customer_id,
            'total', NEW.total
        )
    )
    ON CONFLICT (event_key) DO NOTHING;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_orders_80_outbox
AFTER UPDATE ON guardrail_lab.orders
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'confirmed'
)
EXECUTE FUNCTION guardrail_lab.queue_order_confirmed();
~~~

### Vì sao WHEN nằm trên CREATE TRIGGER?

Điều kiện lọc những UPDATE có thay đổi trạng thái sang `confirmed`. Các UPDATE chỉ đổi discount hoặc updated_at mà status vẫn confirmed không phát sự kiện mới.

### Vì sao ON CONFLICT?

`event_key` là unique, minh họa idempotency cho loại event “đơn xác nhận lần đầu”. Mỗi domain cần chọn event identity phù hợp. Nếu cho phép xác nhận lại sau khi hủy, key chỉ theo order_id có thể **không đủ** để phân biệt các lần xác nhận; cần version/event ID.

### Outbox không tự gửi email

Một worker bên ngoài sẽ tìm event đã commit ở `delivery_status='pending'`, thực hiện gửi, cập nhật trạng thái theo một giao thức có retry/idempotency.

**Outbox thường cung cấp cơ sở cho at-least-once delivery, không mặc nhiên là exactly-once gửi email.** Consumer/provider cần cách tránh xử lý trùng.

## 33. Thử outbox cùng transaction

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1
RETURNING order_id, status, total;

SELECT
    event_key,
    event_type,
    payload,
    delivery_status
FROM guardrail_lab.outbox
ORDER BY event_id;

SELECT
    operation,
    old_row ->> 'status' AS old_status,
    new_row ->> 'status' AS new_status
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Trong transaction:

- Đơn 1 đổi draft → confirmed.
- Audit có dòng UPDATE.
- Outbox có event `order.confirmed` pending.
- Cả ba cùng thuộc transaction.

Sau `ROLLBACK`, thay đổi status, audit mới và event pending đều bị hủy. Worker ngoài kết nối khác không thấy outbox chưa commit theo transaction isolation thông thường.

### Không gửi email trong trigger rồi hy vọng ROLLBACK cũng “thu hồi email”

Email đã gửi không thể bị rollback bằng SQL. Chỉ có **ý định gửi** được ghi transactionally; worker gửi sau khi commit thành công.

## 34. Vì sao có thể tạo outbox trong service thay vì trigger?

Outbox không bắt buộc phải được tạo bằng trigger.

**Phương án service transaction:**

~~~text
BEGIN
  UPDATE orders SET status = 'confirmed' ...
  INSERT INTO outbox (...)
COMMIT
~~~

**Phương án trigger:**

~~~text
BEGIN
  UPDATE orders SET status = 'confirmed' ...
  AFTER UPDATE trigger ghi outbox
COMMIT
~~~

| Yếu tố | Service ghi outbox | Trigger ghi outbox |
| --- | --- | --- |
| Ý định nghiệp vụ rõ trong code service | Thường cao | Có thể bị che trong DB |
| Bao phủ nhiều đường ghi DB | Cần mọi đường ghi tuân workflow | Trigger bao phủ DML liên quan nếu trigger hoạt động |
| Quan sát dễ qua code review | Thường dễ | Cần xem cả schema/trigger functions |
| Có thể vô tình tạo event từ migration/batch | Service kiểm soát rõ | Trigger có thể chạy khi batch cập nhật |
| Gắn DB state và event cùng transaction | Có nếu cùng transaction | Có vì trigger cùng transaction |
| Phù hợp mọi hệ thống | Không | Không |

**Khuyến nghị thiết kế:** nếu sự kiện cần phát sinh cho mọi thay đổi trạng thái bất kể đường ghi, trigger có thể hữu ích. Nếu sự kiện gắn chặt với hành động nghiệp vụ cụ thể, service explicit transaction có thể dễ bảo trì hơn. Dù chọn cách nào, cần có test và idempotency.

## 35. Logic app không thể tự bảo đảm một constraint cross-request

Ví dụ API tự kiểm tra email trùng:

~~~text
Request A: SELECT email -> chưa có
Request B: SELECT email -> chưa có
Request A: INSERT email
Request B: INSERT email
~~~

Nếu thiếu UNIQUE, cả hai có thể thành công.

Nếu có UNIQUE(normalized_email):

- Chỉ một INSERT được chấp nhận cho giá trị normalized trùng.
- Request còn lại nhận lỗi phù hợp, ví dụ SQLSTATE `23505`.
- Service có thể map thành HTTP `409 Conflict` (tùy API contract).

### Không nên tự dự đoán từ câu SELECT

Pre-check vẫn có thể làm UX tốt hơn, nhưng **constraint mới là nguồn cưỡng chế cuối cùng**. Service phải xử lý lỗi constraint khi race xảy ra.

Cũng không nên bắt mọi lỗi 23505 rồi mặc định là email trùng: một transaction có thể vi phạm UNIQUE ở cột/bảng khác. Có thể cần kiểm tra tên constraint có kiểm soát.

## 36. Trigger không tự tạo bất biến dữ liệu bất khả vi phạm

Một trigger custom có thể:

- Bị thay đổi/disable bởi role có quyền thích hợp.
- Không được kích hoạt trong một số chế độ replication hoặc đặc thù thao tác theo configuration.
- Bị sai nếu logic dùng SELECT không khóa đúng.
- Chạy trên một event nhưng quên event khác.
- Chịu chi phí và side effect khi batch nhập dữ liệu.

Trong khi đó constraint khai báo phản ánh quy tắc trực tiếp và thường dễ thấy trong catalog/schema diff.

### Bảo mật và quyền triển khai

Nếu threat model bao gồm người có quyền superuser/owner thay đổi schema, không constraint/trigger nào trên cùng database là “bất biến không thể bị can thiệp” trước họ. Cần quản trị quyền, audit độc lập, backup và quy trình thay đổi production.

Đừng dùng trigger như một biện pháp thay thế cho authorization đúng.

## 37. Row-level security và quyền truy cập khác trigger

RLS có mục tiêu khác:

- Ràng buộc điều kiện hàng nào một DB role có thể `SELECT/INSERT/UPDATE/DELETE`.
- Không được thay thế chỉ bằng trigger.
- Không được thay thế chỉ bằng filter app nếu hệ thống dựa vào DB-level isolation.

Ví dụ khái niệm:

~~~sql
ALTER TABLE some_schema.tenant_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_policy
ON some_schema.tenant_orders
USING (tenant_id = current_setting('app.tenant_id')::bigint)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
~~~

Đây là **minh họa**, không chạy trực tiếp vì bảng chưa được tạo và cần chính sách secure tenant context. Giá trị `current_setting` do session có thể đặt không tự đáng tin trong mọi trust model; việc cho caller tự đặt tenant ID tùy ý có thể phá cách ly.

RLS cũng có bypass conditions đối với chủ bảng/role đặc biệt theo cấu hình. Vì vậy cần kiểm thử bằng **role ứng dụng thực tế**, không chỉ bằng superuser.

### Phân biệt ngắn

- Constraint: dữ liệu hợp lệ không?
- RLS/quyền: ai có thể nhìn hoặc sửa hàng?
- Trigger: phản ứng với sự kiện ghi?
- Ứng dụng: caller thực sự được làm workflow nào?

## 38. Trigger và rule (CREATE RULE) khác nhau

Chương có tên **“Trigger và luật”**; trong PostgreSQL, `CREATE RULE` là một cơ chế **query rewrite** riêng, không đồng nhất với trigger.

| Tiêu chí | Trigger | Rule |
| --- | --- | --- |
| Giai đoạn | Gắn với thực thi event DML | Gắn với rewrite query |
| Có `OLD`/`NEW` theo trigger function | Có trong row trigger | Có các pseudo-relations theo cơ chế rule khác |
| Phù hợp audit mỗi hàng | Thường có | Thường không phải lựa chọn ưu tiên |
| Có thể thay nội dung hàng BEFORE | Có | Không cùng cơ chế |
| Dùng cho view | `INSTEAD OF` trigger có thể phù hợp | Rule có thể tham gia updatable view/rewrite |
| Dễ hiểu với logic nghiệp vụ thường nhật | Thường rõ hơn | Rewrite semantics có thể bất ngờ |

`CREATE RULE` không phải “constraint rule” dùng để thay mọi logic kiểm tra. Rules có những tương tác phức tạp với câu query nhiều hàng, RETURNING và side effects; PostgreSQL thường khuyến khích cân nhắc triggers trước cho nhiều nghiệp vụ cần phản ứng theo hàng.

**Đừng dùng một rewrite rule để mô phỏng constraint hoặc audit trigger nếu không có lý do đã được kiểm chứng.**

## 39. BEFORE trigger và generated column có liên quan thời điểm tính

Trong lab:

~~~sql
total numeric(12,2)
    GENERATED ALWAYS AS (subtotal - discount) STORED
~~~

Nếu BEFORE trigger thay `NEW.subtotal` hoặc `NEW.discount`, generated column được tính theo dữ liệu đầu vào đã qua những bước phù hợp trong pipeline. Không nên cố truy cập/gán stored generated column bên trong BEFORE trigger như một cột thường để tự sửa theo mong muốn.

### Một trigger tính total thủ công có cần không?

Không:

~~~text
BEFORE INSERT OR UPDATE:
  NEW.total := NEW.subtotal - NEW.discount
~~~

là logic trùng với generated column nếu biểu thức đúng là một công thức thuần từ cùng hàng.

Generated column mô tả rõ nguồn gốc giá trị, tránh phải đảm bảo trigger có gắn cho mọi event đúng và không bị quên khi thêm đường ghi.

### Khi nào không dùng generated column?

Nếu total phụ thuộc phí vận chuyển từ hệ thống khác, giá lịch sử, dữ liệu nhiều bảng hoặc các sự kiện thời gian thay đổi, công thức không còn đơn thuần immutable từ cột cùng hàng. Khi đó phải thiết kế domain model, snapshot giá tại thời điểm giao dịch và transaction logic, không ép vào generated expression sai semantics.

## 40. Ràng buộc lịch sử khác bất biến trạng thái hiện tại

Trong đơn hàng có hai loại quy tắc:

**Bất biến hiện tại:**

~~~sql
CHECK (
    status <> 'confirmed'
    OR subtotal > discount
)
~~~

Bất kể cách hàng chuyển đến trạng thái này, nếu confirmed thì tổng phải dương.

**Bất biến chuyển trạng thái:**

~~~text
OLD.status = cancelled
NEW.status = confirmed
=> forbidden
~~~

Để kiểm tra quy tắc thứ hai cần biết **OLD/NEW** của thao tác, do đó trigger hoặc một service transition method có bảo vệ tương đương.

### Có cần cả hai không?

Có thể. Trigger chống chuyển trạng thái không đồng nghĩa đã xác thực toàn bộ dữ liệu tài chính; CHECK ngăn trạng thái cuối không hợp lệ dù trigger bỏ sót một nhánh.

Ngược lại, CHECK không thể tự cấm confirmed → draft vì draft là một giá trị hợp lệ xét riêng hàng hiện tại.

## 41. Constraint deferrable và constraint trigger

Một số constraint có thể `DEFERRABLE`, cho phép hoãn kiểm tra tới thời điểm phù hợp trong transaction:

~~~sql
-- Ví dụ khái niệm về FK:
CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
DEFERRABLE INITIALLY DEFERRED
~~~

Tuy nhiên:

- PostgreSQL không cho mọi constraint (như CHECK/NOT NULL thông thường) trở thành DEFERRABLE theo cùng cách.
- Unique, primary key, exclusion và foreign key có các khả năng/giới hạn deferral riêng.
- `SET CONSTRAINTS ...` tác động lên những constraint phù hợp và còn phụ thuộc mode.

PostgreSQL còn có **constraint trigger** dạng `AFTER ROW` có thể khai báo `DEFERRABLE` theo quy tắc:

~~~sql
CREATE CONSTRAINT TRIGGER constraint_name
AFTER INSERT OR UPDATE ON some_schema.some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_schema.some_trigger_function();
~~~

Đây là ví dụ cú pháp, không thể chạy nếu chưa tạo các object tương ứng. **Đừng suy từ đó ra mọi BEFORE/AFTER trigger đều có thể defer**.

### Khi nào cân nhắc?

Khi một quy tắc chỉ nên được kiểm tra sau một tập các thay đổi trong transaction, xem xét liệu FK/UNIQUE/EXCLUDE deferrable có mô tả đúng hơn không. Constraint trigger tùy biến đòi hỏi hiểu semantics và concurrency ở mức sâu, không phải lựa chọn mặc định.

## 42. Trigger và thao tác hàng loạt

Câu:

~~~sql
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE status = 'draft';
~~~

có thể kích hoạt:

- BEFORE UPDATE ROW cho từng hàng.
- AFTER UPDATE ROW cho từng hàng.
- Statement-level triggers theo event.
- Index/constraint checking và audit/outbox theo logic đã gắn.

### Những điều cần tính

- Nếu 100.000 hàng được UPDATE, audit row-level có thể tạo gần 100.000 audit entries.
- Nếu trigger chạy một query SELECT phức tạp mỗi hàng, có thể thành mô hình N+1 queries.
- Nếu UPDATE làm nhiều người cùng giữ lock, latency và deadlock risk tăng.
- Một statement lỗi do một hàng vi phạm constraint có thể làm toàn statement thất bại; không mặc định “99.999 hàng đã thành công”.

**Đừng benchmark trigger trên UPDATE một hàng rồi khẳng định batch 100.000 hàng sẽ rẻ.** Với workload lớn, có thể nghiên cứu statement-level transition tables, batch/partition, queue và giảm các query lặp.

## 43. COPY và các đường ghi khác

Các đường ghi vào PostgreSQL gồm:

- JDBC prepared statements.
- psql hoặc pgAdmin.
- Batch ETL.
- `COPY FROM`.
- Service khác trong hệ thống.
- Stored procedures.
- Migration scripts.
- Replication/apply processes có các quy tắc riêng.

Một trigger trên `INSERT` có thể chạy khi dữ liệu được nhập bằng `COPY FROM` theo quy tắc trigger của PostgreSQL, chứ không chỉ chạy qua UI.

Nhưng không nên tuyên bố **mọi đường ghi luôn chạy mọi trigger giống nhau** bất kể replication mode, disabled trigger hoặc special permissions.

### Đặc biệt với logical replication

Replication apply có chế độ firing triggers khác execution client thông thường; `ENABLE REPLICA TRIGGER`/`ENABLE ALWAYS TRIGGER` và cấu hình liên quan có thể thay đổi hành vi. Khi dùng logical replication, cần kiểm tra chính xác các triggers, constraints và generated columns trong cả publisher/subscriber.

**Trigger không phải bằng chứng tuyệt đối rằng mọi dữ liệu nhập từ mọi nguồn đều đã chạy cùng business workflow.**

## 44. Không vô tình tạo recursion

Một AFTER UPDATE trigger có code:

~~~sql
UPDATE guardrail_lab.orders
SET updated_at = clock_timestamp()
WHERE order_id = NEW.order_id;
~~~

có thể làm chính hàng đó UPDATE lần nữa, từ đó kích hoạt trigger UPDATE mới và lặp.

Vì vậy:

- Stamp cùng hàng bằng **BEFORE ROW** sửa `NEW`.
- Tránh UPDATE cùng bảng từ AFTER trigger trừ khi đã thiết kế cơ chế ngăn recursion rõ ràng.
- Không dựa vào `pg_trigger_depth()` như “bùa hộ mệnh” để vá mọi sai thiết kế; nó chỉ hỗ trợ kiểm tra độ sâu, có giới hạn và không thay transaction logic đúng.
- Với audit, ghi sang bảng khác ít tạo recursion hơn nhưng vẫn phải kiểm soát triggers trên bảng audit đó.

## 45. Triggers và khóa: logic có thể chậm dù UPDATE đơn giản

Một lệnh UPDATE có thể tốn:

1. Chi phí xác định hàng qua index/scan.
2. Chi phí lock tuple/transaction.
3. Chi phí gọi nhiều trigger functions.
4. Chi phí queries phụ trong trigger.
5. Chi phí kiểm tra constraints và duy trì index.
6. Chi phí WAL, buffer dirty và vacuum về sau.
7. Chi phí contention khi nhiều session cùng ghi.

Khi trigger làm thêm 3 SQL queries/hàng, một batch 10.000 hàng có thể tăng công việc rất nhiều so với một biểu thức set-based.

### Một trigger function nên làm gì?

- Giữ ít side effects, phạm vi rõ.
- Không gọi mạng.
- Không chạy toàn bảng mỗi hàng nếu tránh được.
- Không phụ thuộc trạng thái session không kiểm soát.
- Không ném lỗi mơ hồ.
- Không lặp validation đã có CHECK/UNIQUE/FK.

Đo bằng workload thật trước khi tối ưu hoặc chuyển logic sang nơi khác.

## 46. Transaction boundaries và rollback

Một ví dụ tổng hợp:

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1;

SELECT *
FROM guardrail_lab.outbox
ORDER BY event_id;

SELECT *
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Dù trigger đã chạy và INSERT audit/outbox, **ROLLBACK** vẫn loại bỏ thay đổi trong transaction.

### Nếu client mất kết nối sau COMMIT?

Có thể có tình huống client không biết commit đã thành công hay chưa. Đây là lý do các thao tác nghiệp vụ quan trọng cần **idempotency key** và cơ chế truy vấn trạng thái, không chỉ dựa vào “client thấy exception hay không”.

Trigger không tự giải quyết bài toán distributed systems này.

## 47. Lỗi trigger nên có SQLSTATE/error contract

Lab dùng:

- `P2001`: đơn cancelled không được chuyển trạng thái.
- `P2002`: confirmed không được về draft.

Các mã `P2001`/`P2002` là ví dụ **mã do ứng dụng chọn**, không phải SQLSTATE mặc định chung của mọi PostgreSQL deployment.

Những lỗi constraint tiêu chuẩn:

| Lỗi | SQLSTATE |
| --- | --- |
| `unique_violation` | `23505` |
| `foreign_key_violation` | `23503` |
| `check_violation` | `23514` |
| `not_null_violation` | `23502` |
| `serialization_failure` | `40001` |
| `deadlock_detected` | `40P01` |

Ứng dụng nên map lỗi **theo nhóm đã biết** thành API responses có cấu trúc. Không hiển thị nguyên SQL statement/schema internal nếu thông tin đó có thể nhạy cảm.

### Vì sao không dùng message text làm định danh lỗi?

Thông điệp có thể thay đổi do localization, PostgreSQL version hoặc điều chỉnh câu chữ. `SQLSTATE` và constraint name (khi đáng tin) ổn định hơn để phân loại.

## 48. JDBC: bắt constraint errors đúng lớp

Ví dụ Java minh họa:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static void createDraftOrder(
        Connection connection,
        long customerId,
        java.math.BigDecimal subtotal
) throws SQLException {

    String sql = """
        INSERT INTO guardrail_lab.orders (customer_id, subtotal)
        VALUES (?, ?)
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {

        ps.setLong(1, customerId);
        ps.setBigDecimal(2, subtotal);
        ps.executeUpdate();

    } catch (SQLException ex) {
        switch (ex.getSQLState()) {
            case "23503" ->
                throw new IllegalArgumentException(
                    "Customer does not exist", ex);
            case "23514" ->
                throw new IllegalArgumentException(
                    "Invalid order amounts", ex);
            default ->
                throw ex;
        }
    }
}
~~~

### Những lưu ý vận hành

- `SQLException.getSQLState()` trả SQLSTATE do JDBC driver cung cấp; cần xử lý `null`/nhiều dạng exception nếu driver đặc thù.
- Ví dụ dùng Java switch arrow syntax; project Java cũ cần cú pháp tương đương.
- Trong transaction có lỗi, caller phải quản lý rollback/savepoint theo đúng semantics. **Catch Java exception không tự làm transaction đã lỗi thành transaction hợp lệ**.
- Thông điệp validation ở client có thể chi tiết hơn lỗi database nhưng constraint vẫn phải là lớp bảo vệ.
- Đừng convert mọi SQL error thành HTTP 400; các lỗi vận hành/kết nối phải được xử lý khác.

## 49. Khi nào dùng service transaction thay trigger?

Với đơn hàng có workflow phức tạp:

~~~text
validate request
authorize user
get inventory/pricing snapshot
BEGIN
  reserve inventory
  create/update order
  write order event/outbox
COMMIT
return response
async worker sends notification
~~~

Nếu logic phụ thuộc các object từ nhiều service, retry policy và external coordination, **service transaction** có thể là nơi rõ ràng hơn trigger.

Nhưng vẫn cần:

- FK/UNIQUE/CHECK trong PostgreSQL.
- DB transactions và row locks phù hợp.
- RLS/privileges khi áp dụng.
- Test mọi đường ghi.
- Outbox cho các side effects sau commit.

**Không dùng service thay constraint**, và cũng không nhét toàn bộ service vào một trigger để “mọi thứ tự động”.

## 50. Bảng so sánh quyết định thiết kế

| Yêu cầu | Lựa chọn ưu tiên | Vì sao | Không nên mặc định dùng |
| --- | --- | --- | --- |
| Status ban đầu là draft | DEFAULT | Xử lý field vắng khi INSERT | BEFORE trigger |
| Không cho status ngoài enum | CHECK/enum/domain | Bất biến dữ liệu | Trigger kiểm tra IN list |
| Không cho discount âm | NOT NULL + CHECK | Bất biến cùng hàng | Chỉ validation app |
| Không cho email trùng | UNIQUE/index unique | Chịu concurrency đúng | Trigger SELECT COUNT |
| Order phải có customer | FOREIGN KEY | Toàn vẹn tham chiếu | Trigger SELECT parent |
| total = subtotal - discount | Generated column hoặc SELECT expression | Tính thuần cùng hàng | Trigger tự gán total |
| updated_at tự đổi trên UPDATE | BEFORE ROW trigger hoặc service được kiểm soát | DEFAULT không làm điều đó | Generated column dùng clock |
| Chặn cancelled -> confirmed | BEFORE UPDATE trigger hoặc state-transition service có bảo vệ DB | Cần OLD/NEW | CHECK status IN |
| Ghi audit thay đổi đã commit | AFTER ROW trigger hoặc explicit service write cùng transaction | Theo event DML | DEFAULT |
| Email sau xác nhận | Outbox + worker | Chờ commit, có retry | HTTP trong trigger |
| Hiển thị lỗi đẹp | Ứng dụng | UX/localization | RAISE NOTICE làm UI |
| Tenant/user authorization | Privileges/RLS + app policy | Quyền truy cập | CHECK hoặc ranking |
| Quota nhiều hàng | Constraint/mô hình counter/lock/transaction | Cần concurrency control | Trigger SELECT COUNT không khóa |
| DML qua view phức tạp | INSTEAD OF trigger khi phù hợp | Ánh xạ DML qua view | Ghi thẳng view tùy tiện |

**Thứ tự tư duy:** DEFAULT để điền giá trị, generated để tính giá trị, constraint để bảo vệ bất biến, trigger cho event/history, app/service cho orchestration và user-facing behavior.

## 51. Thay schema và migrate logic khi đang có dữ liệu

Thêm constraint mới trên bảng production không chỉ là viết SQL. Nếu dữ liệu cũ đã vi phạm, DDL có thể thất bại.

Một kế hoạch thường gồm:

1. Khảo sát dữ liệu cũ.
2. Sửa hoặc quyết định policy cho các trường hợp sai.
3. Thêm constraint theo cơ chế phù hợp, có thể dùng `NOT VALID` cho một số loại constraint được hỗ trợ.
4. Kiểm tra/`VALIDATE CONSTRAINT` theo điều kiện version/loại constraint.
5. Triển khai ứng dụng tương thích với schema mới.
6. Giám sát errors/latency.
7. Dọn code trigger/app trùng lặp sau khi kiểm chứng.

### Không áp dụng NOT VALID cho mọi loại constraint

Ví dụ CHECK/FK có những cơ chế `NOT VALID` phù hợp; không được tự suy ra UNIQUE/PK có cách thêm `NOT VALID` hệt như CHECK. Kiểm tra tài liệu `ALTER TABLE` của major version đang dùng.

### Thêm trigger trên bảng đã có dữ liệu

Trigger thường áp dụng cho sự kiện **sau khi được tạo**, không chạy tự động một lần cho tất cả các hàng lịch sử. Nếu cần audit/backfill hay tạo outbox cho trạng thái hiện tại, phải có kế hoạch migration/backfill rõ ràng, tránh phát email hàng loạt ngoài ý muốn.

## 52. Khi thay đổi trigger function

`CREATE OR REPLACE FUNCTION` thay nội dung function nhưng không đồng nghĩa đã kiểm thử mọi bảng gọi function đó.

Trước khi sửa:

- Liệt kê triggers nào phụ thuộc function.
- Kiểm tra quyền, search_path và SQLSTATE.
- Xác nhận logic với OLD/NEW và từng event.
- Thử batch DML, rollback, concurrency.
- Có kế hoạch deployment/backward compatibility.
- Xem hiệu ứng lên replication/apply jobs.
- Không tự đổi nghĩa trigger mà không thông báo những service dựa vào nó.

Một trigger có thể được chia sẻ bởi nhiều bảng; function viết cho tên cột cụ thể không nên gắn tùy tiện lên bảng khác.

## 53. Quan sát trigger trong system catalogs

Liệt kê các trigger do người dùng định nghĩa trên bảng orders:

~~~sql
SELECT
    tgname AS trigger_name,
    tgenabled,
    pg_get_triggerdef(oid) AS definition
FROM pg_trigger
WHERE tgrelid = 'guardrail_lab.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Các cột:

- `tgname`: tên trigger.
- `tgenabled`: trạng thái kích hoạt theo chế độ liên quan.
- `pg_get_triggerdef`: định nghĩa trigger dễ đọc.
- `tgisinternal`: phân biệt triggers nội bộ như cơ chế FK.

### Vì sao catalog quan trọng?

Code ứng dụng có thể chỉ chứa `UPDATE orders` mà không nêu tên triggers. Muốn hiểu đầy đủ side effects thực tế, phải xem schema đang triển khai, không chỉ file Java.

Không chỉnh sửa `pg_trigger` trực tiếp. Dùng DDL được PostgreSQL hỗ trợ và quản lý qua migration.

## 54. EXPLAIN và đánh giá chi phí trigger

Có thể dùng:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE order_id = 1;

ROLLBACK;
~~~

**Cảnh báo:** `EXPLAIN ANALYZE UPDATE` **thực thi UPDATE thật**. Bọc trong transaction rollback trên database lab để không giữ dữ liệu thay đổi. Tùy chọn `WAL` phụ thuộc PostgreSQL version (có từ PostgreSQL 13).

Một số báo cáo EXPLAIN cho DML có thể thể hiện thời gian/hoạt động trigger. Không phải mọi phiên bản/plan đều hiển thị cùng một mức chi tiết.

Ngoài thời gian statement, đo:

- Số rows affected.
- CPU/IO từ các SQL phụ của trigger.
- WAL records/bytes và dirty buffers khi công cụ hỗ trợ.
- Lock waits khi concurrent updates.
- Audit/outbox growth và index overhead.
- TPS và p95/p99 latency của API.
- Autovacuum và dead tuples sau workload ghi.

**Không kết luận trigger luôn chậm hoặc luôn nhanh.** Chi phí phụ thuộc lượng row, logic bên trong, index, kích thước dữ liệu và concurrency.

## 55. Thử từng đường ghi trong lab

Một tập test tối thiểu:

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| 1 | INSERT order không truyền status | status = draft |
| 2 | INSERT explicit NULL status | NOT NULL error |
| 3 | INSERT discount > subtotal | CHECK error |
| 4 | INSERT customer_id không tồn tại | FK error |
| 5 | INSERT order confirmed có total = 0 | CHECK error |
| 6 | UPDATE draft -> confirmed | Thành công nếu tiền hợp lệ |
| 7 | UPDATE confirmed -> draft | Trigger error P2002 |
| 8 | UPDATE cancelled -> confirmed | Trigger error P2001 |
| 9 | UPDATE subtotal/discount | Generated total tính lại |
| 10 | UPDATE hợp lệ | updated_at được stamp |
| 11 | UPDATE hợp lệ | audit ghi OLD/NEW |
| 12 | UPDATE sang confirmed | outbox có pending event |
| 13 | Rollback transaction | Order/audit/outbox cùng rollback |
| 14 | UPDATE nhiều rows | Trigger row-level chạy cho từng row phù hợp |
| 15 | Concurrent updates | Không mất bất biến dưới thiết kế khóa/isolation phù hợp |
| 16 | Trigger lỗi khi audit insert | Statement gốc thất bại |
| 17 | Ghi qua batch/COPY | Kiểm tra triggers/constraints có hoạt động như kỳ vọng |
| 18 | DML bằng role ứng dụng | Kiểm tra permissions/RLS, không chỉ bằng owner |

### Test cần dùng transaction riêng

Không chạy cả bảng test gây lỗi trong một transaction rồi tiếp tục như không có gì. Một SQLSTATE constraint failure có thể khiến transaction bị aborted. Hãy rollback hoặc sử dụng savepoint/test harness có kiểm soát cho từng ca.

## 56. Bài tập thực hành có đáp án

Những bài dưới đây dựa trên `guardrail_lab` sau khi chạy lab. Với DML nên dùng `BEGIN; ... ROLLBACK;` để không làm thay đổi trạng thái cho bài tiếp theo. Câu cố ý lỗi phải kết thúc transaction phù hợp trước khi thực hành bài khác.

### Bài 1. Trạng thái khởi đầu của đơn nên đặt ở đâu?

**Đáp án:** `status text NOT NULL DEFAULT 'draft'`. Đây là giá trị khi INSERT không truyền status.

### Bài 2. Nếu ứng dụng truyền explicit NULL cho status thì sao?

**Đáp án:** `DEFAULT` không tự được dùng; `NOT NULL` báo lỗi.

### Bài 3. Chặn subtotal âm bằng gì?

**Đáp án:** `subtotal numeric NOT NULL CHECK (subtotal >= 0)`. Không cần trigger để so sánh một cột với hằng.

### Bài 4. Chặn discount > subtotal bằng gì?

**Đáp án:** `CHECK (discount <= subtotal)` với các cột NOT NULL phù hợp. Đây là bất biến cùng hàng.

### Bài 5. Vì sao CHECK(amount > 0) chưa cấm NULL?

**Đáp án:** CHECK thường chấp nhận UNKNOWN/NULL của biểu thức; thêm `NOT NULL` nếu cần.

### Bài 6. Tạo total từ subtotal - discount bằng gì?

**Đáp án:** Generated column với biểu thức immutable từ các cột cùng hàng, hoặc tính khi SELECT nếu không cần lưu.

### Bài 7. DEFAULT updated_at có tự thay khi UPDATE không?

**Đáp án:** Không. Cần BEFORE UPDATE trigger hoặc một hợp đồng application ghi timestamp đúng; DEFAULT chỉ xử lý khi áp dụng giá trị mặc định.

### Bài 8. Không trùng email normalized nên làm sao?

**Đáp án:** Generated normalized_email + UNIQUE constraint/index, hoặc unique expression index được thiết kế phù hợp; không dùng trigger `SELECT count(*)` thay UNIQUE.

### Bài 9. Customer_id phải tồn tại?

**Đáp án:** FOREIGN KEY tới customers, không phải trigger tự SELECT parent.

### Bài 10. Trạng thái chỉ được draft/confirmed/cancelled?

**Đáp án:** CHECK (status IN (...)) với NOT NULL; nếu cần domain type có thể cân nhắc enum/domain theo yêu cầu migration.

### Bài 11. Không cho cancelled -> confirmed?

**Đáp án:** Quy tắc cần OLD/NEW, thích hợp với BEFORE UPDATE trigger hoặc state-transition service được bảo vệ đúng trong DB/transaction. CHECK status IN không đủ.

### Bài 12. BEFORE ROW function phải trả gì để tiếp tục UPDATE?

**Đáp án:** Thường `RETURN NEW;`. Trả `NULL` sẽ bỏ qua thao tác trên hàng theo semantics của BEFORE ROW trigger.

### Bài 13. AFTER ROW RETURN NEW có cập nhật hàng không?

**Đáp án:** Không. Giá trị return của AFTER ROW trigger không quyết định row đã ghi; dùng BEFORE ROW nếu muốn sửa `NEW`.

### Bài 14. TG_OP nghĩa là gì?

**Đáp án:** Loại thao tác gây trigger, ví dụ INSERT, UPDATE, DELETE, TRUNCATE theo event hỗ trợ.

### Bài 15. OLD có nghĩa khi INSERT không?

**Đáp án:** Không có hàng cũ cho INSERT; NEW mới đại diện cho hàng được thêm.

### Bài 16. DELETE có NEW không?

**Đáp án:** Không có hàng mới cho DELETE; dùng OLD để lấy trạng thái bị xóa trong row trigger.

### Bài 17. Audit trước hay sau UPDATE?

**Đáp án:** AFTER ROW thường phù hợp để lưu OLD/NEW đã qua xử lý DML; nếu cần can thiệp hàng thì BEFORE ROW.

### Bài 18. UPDATE 100 hàng kích hoạt row trigger bao nhiêu lần?

**Đáp án:** Về nguyên tắc một lần cho mỗi hàng liên quan tại mỗi trigger row-level; statement trigger một lần cho cả statement.

### Bài 19. Trigger ghi audit có tự commit riêng không?

**Đáp án:** Không. Audit insert thuộc transaction của statement gốc; rollback ngoài hủy cả hai.

### Bài 20. Vì sao gửi email trong trigger là rủi ro?

**Đáp án:** DB transaction có thể rollback sau khi email đã gửi; mạng chậm giữ lock, có thể gửi trùng khi retry. Dùng outbox + worker sau commit.

### Bài 21. Outbox event có bảo đảm exactly-once email không?

**Đáp án:** Không. Outbox giúp đồng bộ việc ghi ý định với DB transaction, còn worker cần retry/idempotency; gửi bên ngoài có thể at-least-once.

### Bài 22. UNIQUE có ưu điểm concurrency nào so với trigger COUNT?

**Đáp án:** UNIQUE được DB thực thi theo cơ chế đảm bảo tính duy nhất giữa các transaction đồng thời; trigger đếm trùng không khóa đúng có race condition.

### Bài 23. Hai transaction cùng thấy 4 đơn trước khi INSERT là lỗi gì?

**Đáp án:** Race condition/logic nhiều hàng. Một SELECT trong trigger không đảm bảo quota. Cần thiết kế counter/lock/constraint/isolation phù hợp.

### Bài 24. Tại sao UPDATE chính bảng trong AFTER UPDATE dễ lỗi?

**Đáp án:** Nó có thể tạo thêm UPDATE và kích hoạt trigger lặp lại (recursion). Stamp `NEW` trong BEFORE ROW sẽ đơn giản hơn.

### Bài 25. Bảng users muốn unique email chỉ với deleted_at IS NULL?

**Đáp án:** Dùng partial unique index theo điều kiện nếu phù hợp; hiểu giới hạn của partial index và migration.

### Bài 26. Authorization multi-tenant nên nằm ở đâu?

**Đáp án:** App authorization và khi yêu cầu cô lập tại DB thì RLS/privileges; không thay bằng CHECK hoặc trigger đơn giản.

### Bài 27. Nếu trigger bị disable khi batch import thì sao?

**Đáp án:** Logic trigger có thể không chạy; cần policy quyền, quy trình import/replication và bước kiểm tra dữ liệu/backfill phù hợp. Không mặc định trigger chạy cho mọi cách ghi.

### Bài 28. Trigger có thể thay CREATE RULE không?

**Đáp án:** Không phải luôn tương đương. Rule là query rewrite, trigger phản ứng tại execution event; lựa chọn theo semantics, view và use case.

### Bài 29. Không cho confirmed order có total = 0 nên dùng gì?

**Đáp án:** `CHECK (status <> 'confirmed' OR subtotal > discount)`; không cần biết OLD nên CHECK tốt hơn trigger.

### Bài 30. Tại sao generated column tốt hơn trigger gán total?

**Đáp án:** Nó khai báo công thức từ cùng hàng rõ ràng, PostgreSQL duy trì theo cơ chế generated và giảm nguy cơ bỏ sót event hoặc ghi trùng logic.

### Bài 31. Làm sao xem trigger đang gắn vào orders?

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid = 'guardrail_lab.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

**Đáp án:** Catalog cho thấy trigger name/state/definition trên bảng.

### Bài 32. SQLSTATE nào cho CHECK và FK?

**Đáp án:** CHECK violation `23514`; foreign key violation `23503`.

### Bài 33. Nếu một UPDATE batch gây lỗi ở hàng cuối?

**Đáp án:** SQL statement bị lỗi và hiệu ứng transaction của statement không được commit một phần theo cách bình thường; cần rollback phù hợp, không tự coi những hàng đầu là thành công.

### Bài 34. Vì sao không xóa audit nếu muốn kiểm toán lâu dài?

**Đáp án:** Audit thường cần phân quyền và retention rõ, tránh ứng dụng có quyền sửa/xóa tùy ý. Trigger ghi log không tự bảo đảm tamper-evident audit.

### Bài 35. Khi nào dùng application validation dù DB đã có constraint?

**Đáp án:** Để báo lỗi sớm, gợi ý người dùng, localization và xác thực input trước khi mở transaction; DB vẫn là lớp cưỡng chế cuối.

### Bài 36. Khi nào nên đưa logic sang service?

**Đáp án:** Khi workflow phụ thuộc quyền người dùng, nhiều service, external payment/email, retry và orchestration. Vẫn dùng constraint/transaction trong DB để giữ invariants.

## 57. Những lỗi thường gặp

### 57.1. Dùng trigger cho mọi việc

Quy tắc mặc định, tính toán cùng hàng và UNIQUE/FK thường có cơ chế khai báo tốt hơn.

### 57.2. Chỉ validate ở application

Một đường ghi khác hoặc race condition có thể vượt qua kiểm tra ở app.

### 57.3. Nghĩ DEFAULT chạy trên UPDATE

DEFAULT không tự stamp `updated_at` ở mỗi UPDATE.

### 57.4. Nghĩ explicit NULL sẽ được DEFAULT thay thế

Không; cần bỏ cột hoặc dùng từ khóa DEFAULT.

### 57.5. Nghĩ CHECK tự cấm NULL

CHECK biểu thức UNKNOWN/NULL không bị coi là FALSE; thêm NOT NULL khi cần.

### 57.6. Tính total bằng trigger dù generated column là đủ

Làm trùng công thức và khó kiểm soát các đường ghi.

### 57.7. Dùng trigger COUNT để thay UNIQUE

Race condition giữa transactions có thể khiến dữ liệu trùng.

### 57.8. Dùng trigger SELECT parent để thay FOREIGN KEY

Dễ thiếu semantics khóa, cascade và concurrency.

### 57.9. Chỉ kiểm tra status IN mà quên transition rule

Một trạng thái hợp lệ vẫn có thể được chuyển tới qua đường không được phép.

### 57.10. Dùng RETURN NULL để “từ chối” không báo lỗi

Caller có thể không biết hàng bị skip.

### 57.11. Thay NEW trong AFTER trigger và nghĩ row thay đổi

AFTER return value không chỉnh hàng đã ghi theo cách BEFORE ROW.

### 57.12. UPDATE cùng bảng trong AFTER UPDATE

Có thể kích hoạt recursion/ghi thừa.

### 57.13. Không xem thứ tự các BEFORE triggers

Các trigger cùng event có quy tắc order; sửa NEW ở trigger trước có thể ảnh hưởng trigger sau.

### 57.14. Nghĩ trigger audit luôn commit

Audit cùng transaction; rollback kéo theo audit rollback.

### 57.15. Gửi HTTP/email trong trigger

External side effect không rollback cùng database.

### 57.16. Nghĩ outbox đảm bảo exactly-once

Worker vẫn có thể gửi trùng; cần idempotency.

### 57.17. Nhầm role DB với danh tính người dùng cuối

`current_user` thường là role connection, không tự đại diện end-user.

### 57.18. Không kiểm soát disable trigger/replication mode

Các đường ghi đặc biệt có thể không chạy cùng business behavior.

### 57.19. Bắt mọi lỗi trong trigger và âm thầm tiếp tục

Có thể mất tính nhất quán, audit và contract ứng dụng.

### 57.20. Không tính chi phí trigger theo số rows

Row trigger chạy lặp nhiều lần trong batch DML.

### 57.21. Gắn trigger lên view/table sai loại

INSTEAD OF, BEFORE/AFTER và ROW/STATEMENT có phạm vi hỗ trợ khác nhau.

### 57.22. Coi RULE là tương đương trigger

Rule rewrite query; trigger phản ứng ở execution. Dùng nhầm gây semantics khó dự đoán.

### 57.23. Thêm constraint vào production không kiểm tra dữ liệu cũ

DDL có thể thất bại hoặc khóa/tải ảnh hưởng vận hành.

### 57.24. Thêm trigger rồi kỳ vọng tự tạo audit lịch sử

Trigger không tự chạy một lần cho toàn bộ hàng cũ; cần backfill riêng.

### 57.25. Không test SQLSTATE và rollback

Các đường lỗi mới là nơi rõ nhất để biết constraint và trigger có bảo vệ dữ liệu không.

## 58. Checklist triển khai trong dự án

- [ ] Phân loại yêu cầu thành default, invariant, derived, event, workflow hoặc authorization.
- [ ] Ưu tiên `NOT NULL`/`CHECK`/`UNIQUE`/`FK`/`EXCLUDE` khi biểu diễn đúng bất biến.
- [ ] Dùng `DEFAULT` cho giá trị khi INSERT thiếu cột, không kỳ vọng chạy khi UPDATE.
- [ ] Dùng generated column cho biểu thức immutable từ cùng hàng khi phù hợp.
- [ ] Xác định rõ transition nào cần OLD/NEW và trigger event nào bảo vệ.
- [ ] Viết BEFORE trigger để kiểm tra/sửa NEW; AFTER trigger cho side effect trong transaction.
- [ ] Tránh `RETURN NULL` nếu không có chủ ý skip hàng.
- [ ] Không sửa NEW trong AFTER rồi kỳ vọng thay row.
- [ ] Phân biệt ROW/STATEMENT triggers, cân nhắc transition relations khi batch.
- [ ] Kiểm soát recursion và thứ tự trigger có phụ thuộc.
- [ ] Dùng mã lỗi SQLSTATE/constraint name rõ ràng, tránh thông báo mơ hồ.
- [ ] Không dùng trigger để gọi email/payment HTTP trực tiếp.
- [ ] Dùng outbox + worker có retry/idempotency cho external side effects.
- [ ] Kiểm thử transaction rollback của order, audit, outbox cùng nhau.
- [ ] Với invariant nhiều hàng, đánh giá khóa, isolation và race condition.
- [ ] Không thay UNIQUE/FK bằng trigger SELECT/COUNT tự viết.
- [ ] Chọn quyền DB/RLS và app authorization phù hợp với threat model.
- [ ] Cấu hình role, privileges, SECURITY DEFINER/search_path nếu có routine đặc quyền.
- [ ] Không để application role tự ý disable/alter triggers.
- [ ] Kiểm tra trigger behavior trên COPY, batch import, replication và migrations.
- [ ] Có kế hoạch backfill khi thêm trigger cho bảng đã có dữ liệu.
- [ ] Đo chi phí ghi theo số hàng, index maintenance, WAL và lock waits.
- [ ] Đo latency API p95/p99 thay vì chỉ EXPLAIN một UPDATE.
- [ ] Kiểm thử mọi đường INSERT/UPDATE/DELETE, dữ liệu lỗi và concurrency.
- [ ] Chuẩn hóa migration/schema review để trigger không thành “logic vô hình”.
- [ ] Không chạy lệnh DROP SCHEMA hoặc benchmark DML nặng trên production.

## 59. Ghi chú về SECURITY DEFINER và search_path

Trigger function mặc định thực thi theo quyền phù hợp của caller, nhưng đôi khi cần quyền ghi audit/outbox mà application role không nên có trực tiếp. Một routine `SECURITY DEFINER` có thể là một phần giải pháp, nhưng **làm tăng trách nhiệm bảo mật**.

Các nguyên tắc:

- Chỉ tạo SECURITY DEFINER khi thật sự cần.
- Owner của function phải là role ít đặc quyền nhất cần thiết.
- Đặt `search_path` an toàn, không cho caller điều khiển việc resolve object sang schema không tin cậy.
- Schema-qualify các bảng/function quan trọng.
- Kiểm soát `EXECUTE` privileges.
- Không dùng dynamic SQL với identifier/value từ input không được validate/quote đúng.
- Kiểm thử bằng application role thực tế.

Trong lab, các function chủ yếu schema-qualify bảng như `guardrail_lab.order_audit` để dễ thấy đích ghi. Khi triển khai thật, nên có một security review riêng thay vì mặc định nâng quyền cho mọi trigger.

## 60. Tài liệu PostgreSQL chính thức

Tham khảo tài liệu **đúng major version PostgreSQL đang chạy**:

- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — BEFORE/AFTER/INSTEAD OF, ROW/STATEMENT, WHEN, transition relations và constraint triggers.
- [Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html) — `NEW`, `OLD`, `TG_OP`, return semantics.
- [Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html) — kích hoạt trigger và thời điểm chạy.
- [CREATE RULE](https://www.postgresql.org/docs/current/sql-createrule.html) — query rewrite rules khác trigger.
- [DDL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, EXCLUDE.
- [Default Values](https://www.postgresql.org/docs/current/ddl-default.html) — mặc định khi INSERT.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html) — điều kiện và semantics generated columns.
- [Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html) — GENERATED AS IDENTITY.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — INSERT, DEFAULT, RETURNING, ON CONFLICT.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — UPDATE/RETURNING và DML.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — thêm/validate constraints, enable/disable trigger theo quyền.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS và các giới hạn.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — MVCC và concurrency.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, deadlocks.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — LANGUAGE, security definer.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — kế hoạch và chi phí thực thi.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — thống kê bảng/index.

Đường dẫn `/current/` trỏ tới tài liệu PostgreSQL hiện hành. Nếu hệ thống dùng major version cũ hơn, cần đối chiếu tính năng generated columns, transition tables, MERGE/ON CONFLICT và các điều kiện trigger cụ thể với version đó.

## 61. Tổng kết

**Không phải mọi hành vi tự động trong database đều nên được viết thành trigger.** PostgreSQL có các cơ chế riêng, mỗi cơ chế mang một hợp đồng rõ ràng.

1. **DEFAULT** điền giá trị khi INSERT không truyền cột; nó không tự chạy lại khi UPDATE và không thay explicit NULL.
2. **Ràng buộc** bảo vệ những trạng thái không hợp lệ. `CHECK` cho bất biến cùng hàng, `UNIQUE` cho tính duy nhất, `FK` cho tham chiếu; nên ưu tiên chúng trước trigger tự kiểm tra.
3. **Generated column** mô tả giá trị tính thuần từ cột cùng hàng như `total = subtotal - discount`.
4. **BEFORE ROW trigger** phù hợp khi cần so sánh `OLD`/`NEW` hoặc chỉnh `NEW`, chẳng hạn trạng thái không được đảo ngược và stamp `updated_at`.
5. **AFTER ROW trigger** có thể ghi audit/outbox gắn với thay đổi hàng, nhưng những ghi đó **thuộc cùng transaction** và sẽ rollback cùng statement/caller.
6. **Logic ứng dụng** điều phối quyền người dùng, trải nghiệm, thanh toán, thông báo, retry và các service ngoài database.
7. **Outbox** giúp lưu ý định phát sự kiện atomically với thay đổi dữ liệu; worker vẫn cần idempotency và retry để xử lý external side effects.
8. **Trigger không tự loại bỏ race condition**, nhất là quy tắc nhiều hàng. Cần constraint/index, khóa, isolation hoặc mô hình dữ liệu phù hợp.
9. **Trigger có chi phí và vận hành riêng**: recursion, batch overhead, migration, permissions, replication mode, catalog visibility và debugging.
10. **Thiết kế tốt là kết hợp các lớp có chủ đích**, không dồn mọi trách nhiệm vào một chỗ.

Khi biết **quy tắc nào thuộc dữ liệu, quy tắc nào thuộc sự kiện và quy tắc nào thuộc workflow**, bạn sẽ xây được hệ thống PostgreSQL dễ hiểu, có thể kiểm chứng, an toàn với đồng thời và thuận tiện bảo trì lâu dài.
