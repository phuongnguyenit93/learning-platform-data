# Giá trị mặc định, NULL và cột sinh tự động khi thêm hàng

## 1. Vì sao cùng một INSERT lại có thể tạo ra các giá trị khác nhau?

Khi thêm một hàng vào bảng bằng `INSERT`, ta không phải lúc nào cũng cung cấp giá trị cho **tất cả** các cột. Cơ sở dữ liệu có thể:

- Lấy giá trị **`DEFAULT`** đã khai báo cho cột;
- Ghi **`NULL`** nếu cột không được chỉ định, không có default và được phép thiếu dữ liệu;
- Tự sinh **khóa định danh (identity/auto-increment)**;
- Tính **cột phát sinh từ biểu thức (generated/computed column)**;
- Hoặc từ chối câu lệnh vì vi phạm `NOT NULL`, `PRIMARY KEY`, `UNIQUE`, `CHECK`, `FOREIGN KEY` hay quy tắc khác.

Điều quan trọng là hiểu **ba cách viết không nhất thiết tương đương**:

~~~sql
-- Cách A: không đề cập cột note.
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-001', 'So tay');

-- Cách B: yêu cầu dùng DEFAULT của cột note.
INSERT INTO inventory_items (sku, item_name, note)
VALUES ('BK-002', 'So ke hoach', DEFAULT);

-- Cách C: lưu NULL tường minh vào cột note.
INSERT INTO inventory_items (sku, item_name, note)
VALUES ('BK-003', 'So ghi chu', NULL);
~~~

Nếu `note` có `DEFAULT 'Chưa có ghi chú'` và cho phép `NULL`, cách A và B sẽ lưu chuỗi mặc định, còn cách C lưu **`NULL`**, không phải chuỗi mặc định.

Một ví dụ khác là khóa chính tự tăng: ứng dụng thường **không truyền** mã mới mà để DBMS sinh. Nhưng cơ chế sinh mã không giống cơ chế của một cột được tính từ những cột khác. Vì vậy cần phân biệt rõ **giá trị mặc định**, **dữ liệu thiếu** và **giá trị tự sinh**.

Mục tiêu bài học thuộc chủ đề **Thêm dữ liệu (INSERT)** của Database SQL:

1. Đọc đúng điều gì xảy ra khi bỏ qua một cột trong `INSERT`.
2. Hiểu sự khác biệt giữa **không chỉ định cột**, `DEFAULT` và `NULL`.
3. Phối hợp `DEFAULT` với `NOT NULL`, `CHECK` và các ràng buộc khác.
4. Hiểu **identity/auto-increment/sequence**, lấy ID vừa sinh và giới hạn của chúng.
5. Phân biệt khóa sinh tự động với **generated/computed columns**.
6. Viết câu lệnh phù hợp từng hệ quản trị và xử lý dữ liệu đầu vào an toàn.

## 2. Dữ liệu mẫu: bảng sản phẩm có default và khóa tự sinh

Các ví dụ chính sử dụng **PostgreSQL**. Phần cuối có bản đối chiếu MySQL, SQL Server, SQLite và Oracle, vì cú pháp tự sinh mã khác nhau giữa DBMS.

~~~sql
CREATE TABLE inventory_items (
    item_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku           VARCHAR(30) NOT NULL UNIQUE,
    item_name     VARCHAR(120) NOT NULL,
    stock_qty     INTEGER NOT NULL DEFAULT 0,
    item_status   VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    note          TEXT DEFAULT 'Chưa có ghi chú',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_inventory_stock
        CHECK (stock_qty >= 0),
    CONSTRAINT chk_inventory_status
        CHECK (item_status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
);
~~~

Ý nghĩa từng cột:

| Cột | Kiểu/ràng buộc | Khi không truyền giá trị |
| --- | --- | --- |
| `item_id` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | DBMS sinh một giá trị định danh theo identity |
| `sku` | `VARCHAR(30) NOT NULL UNIQUE` | Không có default, vì vậy bỏ qua thường gây lỗi `NOT NULL` |
| `item_name` | `VARCHAR(120) NOT NULL` | Không có default, bỏ qua gây lỗi `NOT NULL` |
| `stock_qty` | `INTEGER NOT NULL DEFAULT 0` | Dùng `0` |
| `item_status` | `VARCHAR(20) NOT NULL DEFAULT 'DRAFT'` | Dùng `'DRAFT'` |
| `note` | `TEXT DEFAULT 'Chưa có ghi chú'`, không có `NOT NULL` | Dùng chuỗi mặc định; vẫn **được phép truyền NULL tường minh** |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` | Dùng giá trị thời gian do DBMS xác định theo ngữ nghĩa timestamp |

Ràng buộc `CHECK` của `stock_qty` và `item_status` vẫn hoạt động dù giá trị đến từ `INSERT` trực tiếp hay từ `DEFAULT`.

**Lưu ý:** tên bảng/cột và ví dụ PostgreSQL là môi trường học tập. Không chạy lại `CREATE TABLE` trên một bảng cùng tên đã tồn tại trong cơ sở dữ liệu thật nếu chưa thiết kế migration phù hợp.

### 2.1. INSERT chỉ nêu các cột bắt buộc

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-001', 'So tay')
RETURNING
    item_id,
    sku,
    item_name,
    stock_qty,
    item_status,
    note,
    created_at;
~~~

Đầu ra điển hình:

| item_id | sku | item_name | stock_qty | item_status | note | created_at |
| ---: | --- | --- | ---: | --- | --- | --- |
| *DBMS sinh* | BK-001 | So tay | 0 | DRAFT | Chưa có ghi chú | *thời điểm mặc định* |

Trong PostgreSQL, `RETURNING` trả các giá trị của **hàng được thêm**; khi dùng identity và default, đây là cách thuận tiện để quan sát kết quả thực tế.

Ta **không dự đoán số `item_id` cụ thể** như 1 hay 2, vì chuỗi identity có thể đã được sử dụng, có khoảng trống, hoặc môi trường học đã có lần chạy trước. Tương tự, giá trị `created_at` phụ thuộc thời điểm giao dịch và cách cài đặt thời gian của phiên/hệ thống.

### 2.2. INSERT với danh sách cột không theo thứ tự bảng

~~~sql
INSERT INTO inventory_items (
    item_name,
    sku,
    item_status,
    stock_qty
)
VALUES (
    'But bi',
    'PN-002',
    'ACTIVE',
    12
)
RETURNING item_id, sku, item_name, item_status, stock_qty;
~~~

SQL ghép giá trị theo **thứ tự cột được liệt kê trong câu INSERT**, không theo thứ tự định nghĩa vật lý trong bảng:

~~~text
item_name   ← 'But bi'
sku         ← 'PN-002'
item_status ← 'ACTIVE'
stock_qty   ← 12
~~~

Các cột `item_id`, `note` và `created_at` không có trong danh sách được xử lý theo cơ chế tự sinh/default tương ứng.

Nên **luôn liệt kê tên cột** trong ứng dụng để tránh phụ thuộc vào thứ tự cột của schema, nhất là khi bảng được bổ sung hoặc sắp xếp lại cột về sau.

## 3. Bỏ qua cột trong INSERT: DBMS điền gì?

Giả sử ta có:

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-004', 'So bai tap');
~~~

SQL không ghi tường minh `stock_qty`, `item_status`, `note` và `created_at`. Cơ chế sẽ lấy **default đã được khai báo** cho những cột này. Riêng `item_id` là cột identity được hệ thống sinh.

Có thể hình dung:

~~~text
Cột được cung cấp trong INSERT?
    |
    +-- Có --> Biểu thức/giá trị tường minh của cột
    |            |
    |            +-- DEFAULT --> Dùng mặc định hoặc cơ chế tự sinh
    |            +-- NULL    --> Truyền NULL; kiểm tra ràng buộc
    |            +-- Giá trị --> Kiểm tra kiểu và ràng buộc
    |
    +-- Không --> Dùng default/cơ chế tự sinh nếu có
                 hoặc NULL khi không có default;
                 sau đó kiểm tra các ràng buộc
~~~

Nếu cột không có giá trị mặc định nào được khai báo và không có cơ chế tự sinh khác, mặc định SQL thường là **`NULL`**. Cột `NOT NULL` sẽ từ chối hàng nếu cuối cùng nhận `NULL`.

Cần nhớ: **bỏ cột không có nghĩa SQL bỏ qua kiểm tra cột đó**. Hàng mới vẫn phải đáp ứng các ràng buộc áp dụng cho toàn bộ bảng.

### 3.1. Bỏ cột bắt buộc không có default

~~~sql
-- LỖI: item_name có NOT NULL, không có DEFAULT.
INSERT INTO inventory_items (sku)
VALUES ('BK-ERR-01');
~~~

Sau khi DBMS xác định `item_name` không có giá trị, nó nhận `NULL` theo logic mặc định và vi phạm `NOT NULL`. Do đó hàng không được thêm thành công.

~~~sql
-- LỖI: sku cũng bắt buộc và không có DEFAULT.
INSERT INTO inventory_items (item_name)
VALUES ('Mat hang chua co SKU');
~~~

**Giải pháp:** cung cấp giá trị hợp lệ cho các cột bắt buộc, hoặc thay đổi thiết kế schema nếu thật sự có quy tắc mặc định đúng nghiệp vụ. Không đặt một chuỗi giả như `'UNKNOWN'` vào cột SKU chỉ để “chạy được” nếu chuỗi đó tạo ra xung đột hoặc đánh mất khả năng nhận diện hàng.

### 3.2. Cột không có DEFAULT nhưng cho phép NULL

Xét bảng phụ:

~~~sql
CREATE TABLE customer_contacts (
    contact_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name  VARCHAR(100) NOT NULL,
    phone      VARCHAR(30),
    email      VARCHAR(120)
);
~~~

Ở đây `phone` và `email` không có `DEFAULT` và cũng không có `NOT NULL`.

~~~sql
INSERT INTO customer_contacts (full_name)
VALUES ('Nguyen An')
RETURNING contact_id, full_name, phone, email;
~~~

Kết quả `phone` và `email` đều là **`NULL`**. Không có một chuỗi rỗng hay giá trị mặc định khác được tự ý tạo ra.

Một cách viết có ý nghĩa tương đương cho hai cột nullable trong ví dụ:

~~~sql
INSERT INTO customer_contacts (
    full_name, phone, email
)
VALUES (
    'Nguyen Binh', NULL, NULL
);
~~~

Cả hai cách làm dữ liệu thiếu ở các cột không có default. Nhưng với cột **có default khác `NULL`**, bỏ qua và truyền `NULL` sẽ khác nhau như mục kế tiếp.

## 4. DEFAULT và NULL: khác nhau ở điểm quyết định

### 4.1. Mặc định không phải cơ chế thay mọi NULL

Với cột:

~~~sql
note TEXT DEFAULT 'Chưa có ghi chú'
~~~

đây là ba tình huống:

~~~sql
-- A: không chỉ định note.
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-010', 'So A');

-- B: ghi DEFAULT rõ ràng.
INSERT INTO inventory_items (
    sku, item_name, note
)
VALUES (
    'BK-011', 'So B', DEFAULT
);

-- C: ghi NULL rõ ràng.
INSERT INTO inventory_items (
    sku, item_name, note
)
VALUES (
    'BK-012', 'So C', NULL
);
~~~

Có thể kiểm tra:

~~~sql
SELECT
    sku,
    note,
    note IS NULL AS note_is_null
FROM inventory_items
WHERE sku IN ('BK-010', 'BK-011', 'BK-012')
ORDER BY sku;
~~~

Kết quả:

| sku | note | note_is_null |
| --- | --- | --- |
| BK-010 | Chưa có ghi chú | FALSE |
| BK-011 | Chưa có ghi chú | FALSE |
| BK-012 | NULL | TRUE |

**Bài học quan trọng nhất:** trong PostgreSQL và SQL thông thường, **`DEFAULT` áp dụng khi cột bị bỏ qua hoặc được yêu cầu bằng từ khóa `DEFAULT`; nó không tự thay một `NULL` được truyền tường minh**.

Một số tính năng riêng của DBMS có thể thay đổi quy tắc này, ví dụ Oracle hỗ trợ `DEFAULT ON NULL` theo cú pháp/phiên bản thích hợp. Không suy rằng hành vi đặc thù đó là quy tắc chung cho mọi hệ SQL.

### 4.2. NULL không phải chuỗi 'NULL', số 0 hay chuỗi rỗng

Trong SQL, những giá trị sau mang nghĩa khác nhau:

| Giá trị | Ý nghĩa |
| --- | --- |
| `NULL` | Chưa có hoặc không biết giá trị; không phải một giá trị cụ thể |
| `'NULL'` | Chuỗi gồm bốn ký tự N-U-L-L |
| `''` | Chuỗi rỗng trong nhiều DBMS; Oracle có quy tắc riêng với chuỗi rỗng |
| `0` | Một giá trị số xác định |
| `'0'` | Một chuỗi ký tự biểu diễn số 0 |
| `DEFAULT` | Từ khóa yêu cầu dùng giá trị mặc định được định nghĩa cho cột |

Ví dụ:

~~~sql
INSERT INTO inventory_items (
    sku, item_name, note, stock_qty
)
VALUES (
    'BK-013',
    'So D',
    'NULL',
    0
);
~~~

Ở hàng này, `note = 'NULL'` là **văn bản**, nên:

~~~sql
note IS NULL
~~~

trả `FALSE`.

Đối với cột số `stock_qty`, số `0` là giá trị hợp lệ đã xác định. Nó không có nghĩa tương tự `NULL`.

### 4.3. DEFAULT cho cột NOT NULL

`stock_qty` được định nghĩa:

~~~sql
stock_qty INTEGER NOT NULL DEFAULT 0
~~~

Các cách hợp lệ:

~~~sql
-- Hợp lệ: bỏ qua stock_qty -> dùng 0.
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-014', 'So E');

-- Hợp lệ: truyền DEFAULT -> dùng 0.
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES (
    'BK-015', 'So F', DEFAULT
);

-- Hợp lệ: truyền 7 -> dùng 7.
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES (
    'BK-016', 'So G', 7
);
~~~

Nhưng:

~~~sql
-- LỖI: NULL tường minh vi phạm NOT NULL.
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES (
    'BK-017', 'So H', NULL
);
~~~

Và:

~~~sql
-- LỖI: -1 vi phạm CHECK (stock_qty >= 0).
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES (
    'BK-018', 'So I', -1
);
~~~

`DEFAULT` chỉ quyết định **nguồn giá trị**. Nó không bỏ qua kiểm tra `NOT NULL`, `CHECK` hay các constraint khác.

## 5. Các cách dùng DEFAULT trong INSERT

### 5.1. Bỏ cột khỏi danh sách

~~~sql
INSERT INTO inventory_items (
    sku, item_name
)
VALUES (
    'BK-020', 'So thuc hanh'
);
~~~

Đây thường là cách rõ nhất khi ứng dụng chỉ cần cung cấp những giá trị nghiệp vụ bắt buộc.

### 5.2. Dùng DEFAULT trong VALUES

~~~sql
INSERT INTO inventory_items (
    sku,
    item_name,
    stock_qty,
    item_status,
    note
)
VALUES (
    'BK-021',
    'So tong hop',
    DEFAULT,
    DEFAULT,
    DEFAULT
);
~~~

Tương ứng:

- `stock_qty = 0`;
- `item_status = 'DRAFT'`;
- `note = 'Chưa có ghi chú'`.

`DEFAULT` ở đây là **từ khóa SQL**, không phải chuỗi `'DEFAULT'`. Cần đặt ở vị trí cú pháp mà DBMS cho phép. Không phải mọi dialect cho phép dùng `DEFAULT` như một biểu thức tự do trong mọi ngữ cảnh.

### 5.3. DEFAULT VALUES: để DBMS điền tất cả các cột

Trong PostgreSQL:

~~~sql
INSERT INTO <ten_bang> DEFAULT VALUES;
~~~

Câu này yêu cầu thêm **một hàng chỉ từ các giá trị default/cơ chế tự sinh**. Nhưng bảng `inventory_items` có `sku` và `item_name` bắt buộc **không có default**, nên:

~~~sql
-- LỖI với schema inventory_items hiện tại.
INSERT INTO inventory_items DEFAULT VALUES;
~~~

Để minh họa một trường hợp hợp lệ, tạo bảng khác:

~~~sql
CREATE TABLE insert_events (
    event_id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO insert_events DEFAULT VALUES
RETURNING event_id, event_type, detail, created_at;
~~~

Kết quả điển hình có:

- `event_id` do identity sinh;
- `event_type = 'UNKNOWN'`;
- `detail = NULL` vì không có default tường minh và được phép `NULL`;
- `created_at` do biểu thức thời gian mặc định sinh.

Không nên dùng `DEFAULT VALUES` để “bỏ qua” cột bắt buộc không có nguồn giá trị.

### 5.4. Chèn nhiều hàng có DEFAULT

PostgreSQL hỗ trợ dùng `DEFAULT` trong từng hàng của danh sách `VALUES`:

~~~sql
INSERT INTO inventory_items (
    sku,
    item_name,
    stock_qty,
    item_status
)
VALUES
    ('BK-022', 'So mot', DEFAULT, DEFAULT),
    ('BK-023', 'So hai', 5,       'ACTIVE'),
    ('BK-024', 'So ba',  0,       DEFAULT)
RETURNING
    item_id, sku, stock_qty, item_status;
~~~

Kết quả có ba hàng mới. Hàng `BK-022` dùng quantity 0 và status DRAFT, `BK-023` dùng giá trị tường minh 5 và ACTIVE, `BK-024` dùng quantity 0 và status mặc định DRAFT.

**Chú ý:** cùng số lượng cột ở mọi nhóm `VALUES`, và các giá trị ở đúng thứ tự cột. Nếu một hàng cần dùng mặc định còn hàng khác có giá trị riêng, `DEFAULT` là lựa chọn tường minh.

### 5.5. DEFAULT trong INSERT ... SELECT

Với `INSERT INTO ... SELECT ...`, khả năng sử dụng từ khóa `DEFAULT` bên trong biểu thức `SELECT` **khác** so với danh sách `VALUES`. Trong PostgreSQL, đừng xem `DEFAULT` là một biểu thức tùy ý có thể viết trong `SELECT`; thay vào đó, hãy **bỏ cột mặc định khỏi danh sách đích** khi muốn toàn bộ các hàng mới dùng default:

~~~sql
-- Ví dụ cấu trúc, giả định có bảng source_items(sku, item_name).
INSERT INTO inventory_items (sku, item_name)
SELECT
    s.sku,
    s.item_name
FROM source_items AS s;
~~~

Các cột `stock_qty`, `item_status`, `note`, `created_at` sẽ được xử lý theo default cho từng hàng được chèn. Trong ví dụ này, `source_items` chỉ là **bảng giả định** để minh họa cú pháp, không phải bảng đã tạo ở phần dữ liệu mẫu.

Nếu cần cả những hàng dùng giá trị tường minh và những hàng dùng mặc định trong một `INSERT ... SELECT`, cần thiết kế biểu thức hoặc chia câu lệnh theo quy tắc dữ liệu. **`COALESCE(s.some_value, 0)` không tự đồng nghĩa với DEFAULT của cột**, đặc biệt khi default sau này thay đổi hoặc không phải hằng số.

## 6. DEFAULT có thể là hằng số hoặc biểu thức

Khai báo:

~~~sql
item_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
~~~

dùng **hằng số**. Còn:

~~~sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

dùng **biểu thức thời gian** mà DBMS đánh giá theo quy tắc của nó. Một số cột mặc định có thể dùng hàm tạo mã UUID, sequence hoặc biểu thức khác tùy DBMS và tính năng được cho phép.

### 6.1. Không tự cố định thời gian ở ứng dụng

Nếu muốn DBMS ghi thời điểm tạo bản ghi:

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-030', 'So co thoi gian')
RETURNING sku, created_at;
~~~

Bỏ `created_at` giúp server áp dụng biểu thức mặc định. Điều này khác với việc ứng dụng tự truyền một timestamp:

~~~sql
INSERT INTO inventory_items (
    sku, item_name, created_at
)
VALUES (
    'BK-031',
    'So co thoi gian tu client',
    TIMESTAMPTZ '2026-11-14 08:00:00+07'
);
~~~

Cả hai có thể hợp lệ, nhưng nguồn thời gian khác nhau. Trong PostgreSQL, `CURRENT_TIMESTAMP` thường phản ánh **thời điểm bắt đầu transaction hiện tại**, không nhất thiết là một đồng hồ mới tại mỗi hàng. Các DBMS và hàm khác (ví dụ `clock_timestamp()` của PostgreSQL) có quy tắc khác.

**Không giả định tất cả các hàng trong một lệnh `INSERT` nhiều hàng sẽ nhận timestamp khác nhau**, hay `created_at` tự cập nhật khi `UPDATE`. `DEFAULT` chủ yếu được dùng khi tạo hàng hoặc khi tường minh yêu cầu default ở những ngữ cảnh được hỗ trợ; muốn tự động cập nhật `updated_at` thường cần thiết kế riêng.

### 6.2. DEFAULT không đọc tùy ý các cột khác của hàng

Giả sử muốn tính `line_total = quantity * unit_price`. Trong PostgreSQL, không thể giải quyết bằng một default tùy tiện tham chiếu trực tiếp hai cột của cùng hàng như:

~~~sql
-- KHÔNG PHẢI định nghĩa DEFAULT hợp lệ cho PostgreSQL:
line_total NUMERIC(14, 2) DEFAULT (quantity * unit_price)
~~~

`DEFAULT` ở PostgreSQL không được phụ thuộc vào các cột khác của chính hàng đang chèn theo mẫu này. Nếu muốn một giá trị luôn được suy ra từ dữ liệu cùng hàng, hãy cân nhắc **generated column** (mục 9), hoặc một cơ chế được DBMS hỗ trợ.

### 6.3. Thay đổi DEFAULT có ảnh hưởng đến dữ liệu cũ không?

Trong PostgreSQL:

~~~sql
ALTER TABLE inventory_items
ALTER COLUMN item_status SET DEFAULT 'ACTIVE';
~~~

Lệnh này thay đổi **mặc định dùng cho các lần thêm hàng tiếp theo** hoặc khi cột được gán `DEFAULT` theo cú pháp phù hợp; nó **không tự sửa giá trị `item_status` của những hàng đã tồn tại**.

Các hàng trước đó có `'DRAFT'` vẫn là `'DRAFT'`. Nếu nghiệp vụ muốn chuyển trạng thái dữ liệu cũ, đó là một thao tác `UPDATE` riêng, cần điều kiện lọc và transaction thích hợp.

Ví dụ sau khi đổi default:

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-032', 'So sau doi default');
~~~

Hàng mới dùng `'ACTIVE'` nếu không có cơ chế khác can thiệp. Nếu cần giữ nguyên kết quả của toàn bộ phần thực hành, **không chạy lệnh ALTER TABLE này trước những bài khác**, hoặc khôi phục:

~~~sql
ALTER TABLE inventory_items
ALTER COLUMN item_status SET DEFAULT 'DRAFT';
~~~

## 7. DEFAULT và ràng buộc NOT NULL, CHECK, UNIQUE, FOREIGN KEY

Một câu `INSERT` thành công cần đáp ứng **toàn bộ ràng buộc áp dụng**, bất kể giá trị đến từ nguồn nào.

### 7.1. DEFAULT không “thắng” NOT NULL

Với cột:

~~~sql
item_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
~~~

- Không truyền trạng thái → mặc định `'DRAFT'`, hợp lệ.
- Truyền `DEFAULT` → `'DRAFT'`, hợp lệ.
- Truyền `'ACTIVE'` → hợp lệ.
- Truyền `NULL` → vi phạm `NOT NULL`.
- Truyền `'PAUSED'` → vi phạm `CHECK` của bảng mẫu.

Lỗi `NOT NULL` không được “chữa” bởi sự tồn tại của `DEFAULT` khi người gọi **đã truyền `NULL` tường minh**.

### 7.2. CHECK có thể chấp nhận NULL nếu thiếu NOT NULL

Một lưu ý rộng hơn về SQL: điều kiện `CHECK` thông thường chỉ từ chối một hàng khi biểu thức kiểm tra là **`FALSE`**; khi là `UNKNOWN` do `NULL`, constraint có thể coi hàng là hợp lệ.

Vì vậy khai báo:

~~~sql
stock_qty INTEGER CHECK (stock_qty >= 0)
~~~

không nhất thiết cấm `stock_qty = NULL`. Muốn cấm thiếu dữ liệu, thêm `NOT NULL` như bảng mẫu:

~~~sql
stock_qty INTEGER NOT NULL DEFAULT 0
    CHECK (stock_qty >= 0)
~~~

`DEFAULT 0` không thay thế `NOT NULL` về mặt định nghĩa miền dữ liệu.

### 7.3. DEFAULT cũng có thể gây vi phạm UNIQUE

Nếu khai báo một mã định danh nghiệp vụ có default cố định:

~~~sql
-- Chỉ để minh họa thiết kế không tốt:
sku VARCHAR(30) NOT NULL UNIQUE DEFAULT 'UNKNOWN'
~~~

thì bản ghi đầu tiên có thể chèn với SKU `'UNKNOWN'`, nhưng lần thứ hai có thể **vi phạm `UNIQUE`**, vì nhiều hàng dùng cùng một giá trị mặc định.

Đối với mã SKU bắt buộc duy nhất, thường nên yêu cầu cung cấp từ nghiệp vụ hoặc dùng cơ chế tạo mã được thiết kế an toàn. Không dùng một default cố định cho cột cần giá trị duy nhất ở mọi hàng.

### 7.4. FOREIGN KEY và giá trị mặc định

Nếu một cột `category_id` có `FOREIGN KEY` tới bảng danh mục, khai báo `DEFAULT 1` **không tự làm mã danh mục 1 tồn tại**. Khi chèn hàng, hệ vẫn kiểm tra giá trị 1 có hợp lệ theo FK (tùy tính năng/trạng thái constraint của DBMS).

Nếu default gây vi phạm FK, `INSERT` sẽ thất bại. Default chỉ cấp một giá trị, không tạo bản ghi tham chiếu.

### 7.5. Trigger và các cơ chế khác có thể ảnh hưởng

Trong hệ thống thực, trigger `BEFORE INSERT`/`AFTER INSERT` hoặc các quy tắc riêng của DBMS có thể bổ sung, biến đổi hoặc từ chối dữ liệu. Khi quan sát hàng sau INSERT mà thấy khác với một biểu thức default đã khai báo, hãy kiểm tra **toàn bộ cơ chế ghi của bảng**, không quy ngay mọi hành vi cho `DEFAULT`.

Cách trigger tương tác với identity/default có thể khác giữa hệ quản trị. Bài này tập trung vào ngữ nghĩa của `INSERT` và cột tự sinh được định nghĩa tường minh.

## 8. IDENTITY: cột định danh do DBMS sinh khi thêm hàng

### 8.1. GENERATED ALWAYS AS IDENTITY trong PostgreSQL

Bảng mẫu dùng:

~~~sql
item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

Đây là cách khai báo cột **identity** theo phong cách SQL chuẩn được PostgreSQL hỗ trợ.

Khi chèn:

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-040', 'So co ma tu sinh')
RETURNING item_id, sku;
~~~

người gọi không phải cung cấp `item_id`. DBMS lấy giá trị từ cơ chế identity gắn với cột.

Ba khái niệm liên quan nhưng khác nhau:

- **`IDENTITY`**: cơ chế sinh giá trị định danh theo cấu hình của DBMS.
- **`PRIMARY KEY`**: ràng buộc nhận diện hàng, cấm `NULL` và trùng khóa.
- **`UNIQUE`**: ràng buộc ngăn trùng giá trị theo quy tắc kiểu/collation/NULL của DBMS.

`IDENTITY` **không tự thay thế mọi ràng buộc nhận diện hàng**. Với PostgreSQL, identity không tự đảm bảo không trùng trong mọi tình huống; cần `PRIMARY KEY` hoặc `UNIQUE` để giữ tính duy nhất ở mức dữ liệu.

### 8.2. GENERATED ALWAYS so với GENERATED BY DEFAULT

PostgreSQL hỗ trợ hai cách khai báo:

~~~sql
CREATE TABLE identity_always_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE identity_by_default_demo (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);
~~~

**`GENERATED ALWAYS`**: cơ sở dữ liệu sinh ID trong các `INSERT` thông thường. Nếu muốn truyền một ID tường minh, PostgreSQL yêu cầu cú pháp override đặc biệt theo ngữ cảnh.

~~~sql
INSERT INTO identity_always_demo (label)
VALUES ('A')
RETURNING id;
~~~

Ví dụ cố ý sai:

~~~sql
-- PostgreSQL: bị từ chối nếu không có OVERRIDING SYSTEM VALUE.
INSERT INTO identity_always_demo (id, label)
VALUES (100, 'Nhap ID thu cong');
~~~

PostgreSQL cho phép override khi thật sự cần chuyển đổi dữ liệu:

~~~sql
INSERT INTO identity_always_demo (id, label)
OVERRIDING SYSTEM VALUE
VALUES (100, 'Du lieu nhap lai');
~~~

Nhưng **chỉ nên override ID khi có nghiệp vụ/migration rõ ràng**, vì có thể xung đột khóa hoặc làm trạng thái sequence không còn đồng bộ với dữ liệu đã chèn.

**`GENERATED BY DEFAULT`**: hệ thống tự sinh ID nếu bỏ qua hoặc dùng `DEFAULT`, nhưng có thể chấp nhận một giá trị tường minh theo cú pháp thường:

~~~sql
INSERT INTO identity_by_default_demo (label)
VALUES ('Tu sinh')
RETURNING id;

INSERT INTO identity_by_default_demo (id, label)
VALUES (100, 'ID da co')
RETURNING id;
~~~

Dù là BY DEFAULT, `PRIMARY KEY` vẫn không cho hai hàng có cùng `id`.

### 8.3. SERIAL và sequence ở PostgreSQL

Một cách cũ vẫn thấy phổ biến:

~~~sql
CREATE TABLE serial_demo (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL
);
~~~

Trong PostgreSQL, `SERIAL`/`BIGSERIAL` là **cú pháp tiện lợi** để tạo một cột số với default lấy giá trị từ sequence; chúng không phải kiểu dữ liệu tự tăng thực thụ theo cùng nghĩa với `IDENTITY`.

Trong mã mới, `GENERATED ... AS IDENTITY` thường diễn đạt ý định tự sinh rõ ràng hơn. Tuy nhiên cần hiểu database và migration hiện có trước khi chuyển đổi một cột `SERIAL` đang hoạt động sang identity.

### 8.4. Không tự tạo ID bằng MAX(id) + 1

Một sai lầm nguy hiểm:

~~~sql
-- KHÔNG NÊN dùng để sinh khóa trong ứng dụng đồng thời.
INSERT INTO some_table (id, label)
SELECT COALESCE(MAX(id), 0) + 1, 'New'
FROM some_table;
~~~

Khi hai transaction cùng đọc `MAX(id)` trước khi bên kia ghi, chúng có thể chọn **cùng một ID**. Sau đó ít nhất một transaction sẽ bị lỗi khóa hoặc đòi hỏi cơ chế khóa phức tạp.

Dùng identity/sequence/autoincrement do DBMS quản lý, kết hợp `PRIMARY KEY`, thay vì tự sinh khóa bằng việc quét `MAX(id)`.

## 9. Generated/computed column: khác với IDENTITY và DEFAULT

Trong SQL, cụm từ **“cột sinh tự động”** có thể ám chỉ nhiều công nghệ. Phải phân biệt:

| Cơ chế | Ví dụ | Khi nào có giá trị? | Nguồn tính |
| --- | --- | --- | --- |
| `DEFAULT` | `stock_qty DEFAULT 0` | Khi không cung cấp hoặc dùng `DEFAULT` | Biểu thức mặc định |
| Identity/auto-increment | `id GENERATED ... AS IDENTITY` | DBMS sinh định danh theo cấu hình | Bộ sinh ID/sequence/counter |
| Generated/computed column | `line_total GENERATED ALWAYS AS (qty * price) STORED` | DBMS tính theo biểu thức dựa trên các cột | Giá trị của chính hàng |
| Trigger | Trigger trên `INSERT` | Khi sự kiện/điều kiện trigger xảy ra | Logic trong trigger |
| Row ID ngầm định | SQLite rowid table | Theo quy tắc engine | Cấu trúc lưu trữ/khóa nội bộ |

### 9.1. Ví dụ generated column STORED trên PostgreSQL

Tạo bảng dòng hàng trong đơn:

~~~sql
CREATE TABLE invoice_lines (
    line_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code  VARCHAR(30) NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  NUMERIC(12, 2) NOT NULL,
    line_total  NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,

    CONSTRAINT chk_line_quantity CHECK (quantity > 0),
    CONSTRAINT chk_line_unit_price CHECK (unit_price >= 0)
);
~~~

Ở đây:

- `line_id` là **identity**, một mã định danh.
- `quantity` có **DEFAULT 1**, áp dụng nếu không cung cấp số lượng.
- `unit_price` phải được ứng dụng cung cấp vì `NOT NULL` và không có default.
- `line_total` là **generated column**, do DBMS tính bằng `quantity * unit_price`.

Chèn dòng hàng:

~~~sql
INSERT INTO invoice_lines (order_code, unit_price)
VALUES ('ORD-001', 25000.00)
RETURNING
    line_id,
    order_code,
    quantity,
    unit_price,
    line_total;
~~~

Kết quả có dạng:

| line_id | order_code | quantity | unit_price | line_total |
| ---: | --- | ---: | ---: | ---: |
| *tự sinh* | ORD-001 | 1 | 25000.00 | 25000.00 |

Chèn hai chiếc:

~~~sql
INSERT INTO invoice_lines (
    order_code, quantity, unit_price
)
VALUES (
    'ORD-002', 2, 15000.00
)
RETURNING quantity, unit_price, line_total;
-- 2, 15000.00, 30000.00
~~~

### 9.2. Không truyền giá trị tính toán vào generated column

Câu sau không hợp lệ với generated column PostgreSQL:

~~~sql
-- LỖI: muốn tự nhập line_total = 12345.
INSERT INTO invoice_lines (
    order_code,
    quantity,
    unit_price,
    line_total
)
VALUES (
    'ORD-003',
    2,
    15000.00,
    12345.00
);
~~~

Hệ quản trị không cho người dùng tuỳ ý ghi giá trị vào `line_total` vì cột được định nghĩa là **GENERATED ALWAYS AS (...)**. Ở PostgreSQL, cột generated có thể được chỉ định `DEFAULT` trong một số ngữ cảnh `INSERT`, nhưng không chấp nhận một giá trị tính toán tường minh tùy ý.

Cách đúng là **chỉ ghi các cột đầu vào** của công thức:

~~~sql
INSERT INTO invoice_lines (
    order_code, quantity, unit_price
)
VALUES (
    'ORD-003', 2, 15000.00
);
~~~

DBMS tính `line_total = 30000.00`.

### 9.3. Generated column có thể đổi khi UPDATE đầu vào

Với cột generated STORED, nếu sửa `quantity` từ `2` thành `3`, hệ sẽ tính lại giá trị được lưu theo quy tắc của generated column:

~~~sql
UPDATE invoice_lines
SET quantity = 3
WHERE order_code = 'ORD-003'
RETURNING quantity, unit_price, line_total;
-- quantity = 3, unit_price = 15000, line_total = 45000
~~~

Đó là điểm khác biệt với `DEFAULT`: default không tự chạy lại mỗi khi một cột khác được cập nhật. Generated column theo biểu thức thể hiện **phụ thuộc tính toán**, còn default là **giá trị dùng khi tạo/gán mặc định**.

### 9.4. STORED và VIRTUAL khác nhau

Một số DBMS hỗ trợ hai hình thức cột phát sinh:

- **`STORED`/`PERSISTED`**: giá trị được tính và lưu theo cơ chế engine;
- **`VIRTUAL`/non-persisted**: giá trị được tính khi đọc hoặc theo cơ chế ảo của engine.

PostgreSQL và các DBMS có phạm vi hỗ trợ khác nhau theo phiên bản; MySQL, SQLite và SQL Server có những cú pháp riêng. Đừng suy rằng mọi hệ đều có cùng từ khóa `STORED`, `VIRTUAL` hoặc cùng quy tắc lập chỉ mục generated column.

**Tóm lại:** cột identity tự sinh **mã**; generated computed column tự sinh **giá trị dựa vào biểu thức**; default cấp giá trị **khi không có dữ liệu tường minh**.

## 10. Cột tự sinh không nhất thiết tạo dãy ID liên tục

### 10.1. Vì sao có khoảng trống trong dãy ID?

Giả sử các hàng có `item_id` là 1, 2, 5, 8. Đây không tự chứng minh dữ liệu bị xóa sai hoặc hệ thống gặp lỗi.

Một cơ chế identity/sequence có thể có khoảng trống do:

- Transaction đã lấy số sequence nhưng bị `ROLLBACK`;
- Câu `INSERT` bị từ chối vì `UNIQUE` hoặc ràng buộc khác;
- Retry sau lỗi, xử lý xung đột hoặc hoạt động đồng thời;
- DBMS cấp phát/cached dãy giá trị;
- Xóa hàng hoặc thao tác quản trị nhập/chuyển dữ liệu.

Ở PostgreSQL, giá trị sequence được cấp thường **không được hoàn tác giống dữ liệu giao dịch** khi rollback. Do đó không dùng identity để đòi hỏi một chuỗi số **không bao giờ khuyết**.

### 10.2. Identity không phải đồng hồ sự kiện

Một ID lớn hơn **không nhất thiết** nghĩa là giao dịch được tạo xong muộn hơn trong mọi trường hợp. Hệ thống có nhiều transaction đồng thời, thứ tự lấy ID có thể khác thứ tự commit; có thể có override hoặc import dữ liệu lịch sử.

Muốn lấy đơn mới nhất hoặc hàng tạo muộn nhất, hãy xác định **cột thời gian và tie-breaker** theo nghiệp vụ. Một identity được dùng làm khóa ổn định, không phải tự động là chứng nhận thời điểm tạo hàng.

### 10.3. Không hứa ID tăng không giới hạn

Cột `INTEGER`/`BIGINT` có phạm vi giá trị hữu hạn; identity có thể hết phạm vi. Ngoài ra, một thiết lập tăng theo bước, giới hạn hoặc cycle có thể ảnh hưởng dãy số. Cần giám sát hệ thống lớn và chọn kiểu phù hợp theo nhu cầu lưu trữ thực tế.

### 10.4. ID tự sinh không thay thế khóa nghiệp vụ

`item_id` là **khóa thay thế (surrogate key)**. Trong bảng `inventory_items`, `sku` là một mã nghiệp vụ cần duy nhất và được bảo vệ bởi `UNIQUE`.

Có thể có hai hàng với hai `item_id` khác nhau nhưng cùng SKU nếu schema không ràng buộc đúng. Việc dùng identity chỉ đảm bảo có một định danh thuận tiện cho mỗi hàng, không tự đảm bảo mọi quy tắc nghiệp vụ khác.

## 11. Lấy giá trị vừa được sinh sau INSERT

### 11.1. PostgreSQL: RETURNING

Một mẫu thực hành:

~~~sql
INSERT INTO inventory_items (
    sku, item_name
)
VALUES (
    'BK-050', 'So moi'
)
RETURNING
    item_id,
    sku,
    stock_qty,
    item_status,
    created_at;
~~~

`RETURNING` cho phép ứng dụng nhận lại các giá trị được sinh/điền sau khi câu `INSERT` tạo hàng.

Trong các hệ/phiên bản hỗ trợ, có thể trả nhiều cột và nhiều hàng:

~~~sql
INSERT INTO inventory_items (
    sku, item_name
)
VALUES
    ('BK-051', 'So mot'),
    ('BK-052', 'So hai')
RETURNING item_id, sku;
~~~

Không nên suy rằng thứ tự các hàng `RETURNING` là một cam kết sắp xếp độc lập cho mọi engine/kế hoạch. Hãy dùng `sku` hoặc khóa nghiệp vụ để ánh xạ kết quả vào các đầu vào khi cần, hoặc dùng cơ chế API trả kết quả được định nghĩa rõ.

### 11.2. JDBC: PreparedStatement và generated keys

Trong Java, JDBC có cơ chế lấy khóa được sinh từ một câu chèn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;

String sql = """
    INSERT INTO inventory_items (sku, item_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "BK-060");
    ps.setString(2, "So tu JDBC");

    int changed = ps.executeUpdate();
    if (changed != 1) {
        throw new IllegalStateException("INSERT khong tao dung 1 hang");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long newItemId = keys.getLong(1);
            System.out.println("New item ID = " + newItemId);
        } else {
            throw new IllegalStateException("Khong nhan duoc generated key");
        }
    }
}
~~~

Khả năng trả khóa và thứ tự/cột trong `getGeneratedKeys()` phụ thuộc driver. Một số driver cho phép chỉ định danh sách tên cột muốn lấy để tránh nhập nhằng, ví dụ overload `prepareStatement(sql, new String[]{"item_id"})` nếu driver hỗ trợ.

Với PostgreSQL JDBC, có thể dùng trực tiếp `INSERT ... RETURNING item_id` qua `executeQuery()`:

~~~java
String sql = """
    INSERT INTO inventory_items (sku, item_name)
    VALUES (?, ?)
    RETURNING item_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "BK-061");
    ps.setString(2, "So tu RETURNING");

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long itemId = rs.getLong("item_id");
            System.out.println(itemId);
        }
    }
}
~~~

**Quan trọng:** đừng chèn xong rồi chạy:

~~~sql
SELECT MAX(item_id) FROM inventory_items;
~~~

để đoán ID vừa tạo. Trong hệ nhiều người dùng, một transaction khác có thể đã chèn hàng mới; `MAX` không phải API trả khóa của **lệnh INSERT của chính bạn**.

### 11.3. Lấy khóa theo cơ chế đặc thù DBMS

Một số kỹ thuật phổ biến:

- PostgreSQL: `INSERT ... RETURNING`.
- SQL Server: `OUTPUT INSERTED.id` (cú pháp `OUTPUT` ở vị trí phù hợp trong `INSERT`).
- SQLite mới: `RETURNING` ở những phiên bản có hỗ trợ.
- MySQL: API lấy generated keys của driver hoặc `LAST_INSERT_ID()` theo ngữ cảnh kết nối, với những quy tắc riêng.
- Oracle: `RETURNING ... INTO` theo API/PLSQL hoặc generated keys của driver.

Không nên sao chép nguyên cú pháp của một hệ sang hệ khác. Đặc biệt, cách lấy ID phải an toàn trong **ngữ cảnh kết nối và câu lệnh đang thực thi**, không dựa vào giá trị lớn nhất toàn bảng.

## 12. INSERT đồng thời, lỗi và transaction

### 12.1. Lỗi constraint không có nghĩa ID đã cấp sẽ được tái sử dụng

Trong PostgreSQL, xét:

~~~sql
BEGIN;

INSERT INTO inventory_items (sku, item_name)
VALUES ('BK-070', 'So trong transaction')
RETURNING item_id;

ROLLBACK;
~~~

Hàng được tạo trong transaction rồi bị rollback, nên **không còn hàng đó** sau rollback. Nhưng số identity/sequence đã cấp trong quá trình chèn **có thể không được trả lại** để sử dụng lần nữa.

Do đó không nên kiểm tra bài học bằng giả định “câu chèn tiếp theo chắc chắn sẽ lấy lại ID vừa rollback”.

### 12.2. Chèn nhiều hàng và lỗi một hàng

Trong DBMS có transaction/statement atomicity theo ngữ cảnh tương ứng, một câu `INSERT` nhiều hàng vi phạm constraint có thể khiến cả câu lệnh thất bại. Tuy nhiên cách xử lý lỗi, chế độ import, xung đột và số hàng được nhận có thể khác giữa engine/cấu hình.

Ví dụ trên PostgreSQL:

~~~sql
-- Có hàng stock_qty âm -> lỗi CHECK, câu INSERT thất bại.
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES
    ('BK-071', 'So hop le', 5),
    ('BK-072', 'So khong hop le', -3);
~~~

Không dùng ví dụ này như một cách chèn dữ liệu có thể bỏ qua lỗi từng hàng. Nếu muốn tiếp nhận hàng hợp lệ và từ chối hàng lỗi riêng, hãy thiết kế **validation và quy trình nạp dữ liệu** tường minh, hoặc dùng tính năng theo dialect có kiểm soát.

### 12.3. ON CONFLICT không đồng nghĩa hoàn tác sequence

PostgreSQL hỗ trợ `ON CONFLICT` để xử lý trùng khóa. Cần lưu ý rằng việc thử `INSERT` có thể tiêu thụ giá trị identity/sequence **ngay cả khi sau đó xử lý xung đột theo nhánh khác**, tùy đường thực thi.

Vì thế không dựa vào số identity liên tục để tính số lượng bản ghi, số hóa đơn hay số đơn hàng. Nếu cần đánh số chứng từ **không khuyết**, phải thiết kế một cơ chế nghiệp vụ riêng, có đồng bộ và chi phí tương ứng; identity không phải công cụ đảm bảo gapless numbering.

## 13. Cú pháp giữa các DBMS: DEFAULT, auto-increment và generated column

Cùng một yêu cầu “thêm hàng mà không truyền khóa” có nhiều cú pháp khác nhau.

### 13.1. PostgreSQL

Khai báo khóa:

~~~sql
CREATE TABLE pg_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Chèn:

~~~sql
INSERT INTO pg_items (label)
VALUES ('A')
RETURNING id, created_at;
~~~

Đặc điểm:

- `GENERATED ALWAYS AS IDENTITY` hoặc `GENERATED BY DEFAULT AS IDENTITY`;
- `SERIAL`/`BIGSERIAL` là cách cũ dựa trên sequence;
- `DEFAULT VALUES` được hỗ trợ;
- `RETURNING` lấy giá trị sau chèn;
- Generated computed column có cú pháp riêng như `GENERATED ALWAYS AS (expr) STORED` trên các phiên bản hỗ trợ.

### 13.2. MySQL

Một thiết kế tương đương về mục đích:

~~~sql
CREATE TABLE mysql_items (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Chèn:

~~~sql
INSERT INTO mysql_items (label)
VALUES ('A');
~~~

Đặc điểm:

- `AUTO_INCREMENT` là cơ chế sinh khóa phổ biến;
- Trường `DEFAULT` và `NULL` tuân theo kiểu, ràng buộc và **SQL mode**;
- Chế độ strict hay non-strict có thể ảnh hưởng việc một số giá trị thiếu/sai kiểu bị từ chối hoặc bị chuyển đổi; không dựa vào chế độ dễ dãi để sửa dữ liệu đầu vào;
- Có thể dùng generated columns `VIRTUAL`/`STORED` theo tính năng của phiên bản.

Ví dụ MySQL cho cột tính toán:

~~~sql
CREATE TABLE mysql_lines (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

Một số chi tiết như gán `0`/`NULL` vào cột `AUTO_INCREMENT`, cách default được đánh giá và việc dùng `DEFAULT VALUES` không nên suy từ PostgreSQL; hãy kiểm tra SQL mode và phiên bản MySQL đang chạy.

### 13.3. SQL Server

SQL Server dùng thuộc tính `IDENTITY(seed, increment)`:

~~~sql
CREATE TABLE dbo.sqlserver_items (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    label NVARCHAR(100) NOT NULL,
    quantity INT NOT NULL DEFAULT (0),
    created_at DATETIME2 NOT NULL DEFAULT (SYSDATETIME())
);
~~~

Chèn và nhận ID:

~~~sql
INSERT INTO dbo.sqlserver_items (label)
OUTPUT INSERTED.id, INSERTED.quantity
VALUES (N'A');
~~~

Các điểm riêng:

- `IDENTITY(1,1)` chỉ định hạt giống và bước tăng;
- Để chèn giá trị identity tường minh trong trường hợp nhập lại dữ liệu, SQL Server có cơ chế `SET IDENTITY_INSERT ... ON` với các ràng buộc;
- `OUTPUT INSERTED...` là cách lấy giá trị từ hàng được chèn;
- Computed column có cú pháp `AS (expression)`, có thể thêm `PERSISTED` nếu thỏa điều kiện.

Ví dụ computed column SQL Server:

~~~sql
CREATE TABLE dbo.sqlserver_lines (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    quantity INT NOT NULL DEFAULT (1),
    unit_price DECIMAL(12,2) NOT NULL,
    line_total AS (quantity * unit_price) PERSISTED
);
~~~

Không dùng `GENERATED ALWAYS AS IDENTITY` của PostgreSQL như cú pháp tương đương cho cột `id` trong T-SQL thông thường.

### 13.4. SQLite

Trong một **rowid table** SQLite phổ biến:

~~~sql
CREATE TABLE sqlite_items (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Khi không chỉ định `id`, SQLite có thể tự cấp một `ROWID` và `id INTEGER PRIMARY KEY` là tên khác (*alias*) của rowid trong rowid table. Đây là cơ chế **khác** với sequence identity của PostgreSQL.

SQLite còn có từ khóa:

~~~sql
id INTEGER PRIMARY KEY AUTOINCREMENT
~~~

nhưng **`AUTOINCREMENT` không cần thiết cho hầu hết trường hợp**. Nó thay đổi quy tắc tái sử dụng ROWID, có thêm chi phí và **không đảm bảo dãy số không có khoảng trống**. Cần hiểu rõ hành vi `INTEGER PRIMARY KEY` và nhu cầu thật trước khi chọn.

SQLite có generated columns từ phiên bản hỗ trợ, với `VIRTUAL` hoặc `STORED`:

~~~sql
CREATE TABLE sqlite_lines (
    id INTEGER PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC NOT NULL,
    line_total NUMERIC
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

SQLite hỗ trợ `RETURNING` ở những phiên bản mới hơn; không giả định một SQLite rất cũ có cùng tính năng. Hệ kiểu linh hoạt của SQLite cũng khiến việc kiểm soát kiểu dữ liệu/constraint cần chú ý, không chỉ dựa vào khai báo cột.

### 13.5. Oracle

Trong các phiên bản Oracle Database hỗ trợ identity:

~~~sql
CREATE TABLE oracle_items (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label VARCHAR2(100) NOT NULL,
    quantity NUMBER DEFAULT 0 NOT NULL
);
~~~

Đặc điểm:

- Oracle hỗ trợ các dạng identity như `GENERATED ALWAYS` hoặc `BY DEFAULT` theo phiên bản;
- Oracle có tính năng **`DEFAULT ON NULL`** cho các trường hợp muốn một giá trị mặc định được áp dụng khi có `NULL` tường minh, nhưng **đó là cú pháp/semantics riêng**, không phổ biến ở mọi DBMS;
- Oracle có quy tắc đặc thù rằng chuỗi rỗng trong nhiều kiểu ký tự được xử lý như `NULL`;
- Trả ID sau chèn có thể dùng `RETURNING ... INTO` theo môi trường/driver.

Ví dụ về ý tưởng của Oracle `DEFAULT ON NULL`:

~~~sql
-- Ví dụ Oracle trên phiên bản hỗ trợ:
CREATE TABLE oracle_defaults (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status_code VARCHAR2(20) DEFAULT ON NULL 'DRAFT' NOT NULL
);
~~~

Với cột `status_code`, truyền `NULL` tường minh có thể được chuyển thành giá trị mặc định theo định nghĩa `DEFAULT ON NULL`. **Không mang câu lệnh này sang PostgreSQL rồi cho rằng `NULL` tự biến thành default**.

### 13.6. Bảng đối chiếu nhanh

| Nhu cầu | PostgreSQL | MySQL | SQL Server | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| Khóa sinh số | `GENERATED ... AS IDENTITY` / sequence | `AUTO_INCREMENT` | `IDENTITY(1,1)` | `INTEGER PRIMARY KEY` trong rowid table | `GENERATED ... AS IDENTITY` |
| Mặc định hằng số | `DEFAULT 0` | `DEFAULT 0` | `DEFAULT (0)` | `DEFAULT 0` | `DEFAULT 0` |
| Mặc định thời gian | `DEFAULT CURRENT_TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` (tùy kiểu) | `DEFAULT (SYSDATETIME())` | `DEFAULT CURRENT_TIMESTAMP` | Kiểu/hàm theo Oracle, ví dụ `SYSTIMESTAMP` |
| Nhận ID sau INSERT | `RETURNING` | Driver/generated keys/`LAST_INSERT_ID()` | `OUTPUT INSERTED.id` | `RETURNING` trên phiên bản hỗ trợ | `RETURNING ... INTO`/driver |
| Cột tính từ biểu thức | Generated column theo phiên bản | Generated `VIRTUAL`/`STORED` | Computed `AS (...)`, có thể `PERSISTED` | Generated `VIRTUAL`/`STORED` theo phiên bản | Virtual/generated features tùy phiên bản |
| `NULL` tường minh có kích hoạt default thường? | Không | Không coi là quy tắc chung; xét SQL mode và định nghĩa | Không theo default thông thường | Không | Có `DEFAULT ON NULL` nếu khai báo đúng |

Bảng này nhằm **định hướng**, không thay thế tài liệu cú pháp của đúng phiên bản. Khi xây hệ thống đa DBMS, đặc biệt cần kiểm tra các điểm: kiểu ID, default timestamp, cơ chế truy xuất generated keys, và tính năng generated column.

## 14. Ứng dụng và ORM: bỏ trường khác với truyền null

Không phải mọi lỗi xuất phát từ người viết SQL trực tiếp. Khi dùng Java, ORM, REST API hoặc công cụ import, cấu trúc câu `INSERT` thực tế có thể khác với ý định ban đầu.

### 14.1. Cùng JSON có thể dẫn tới SQL khác nhau

Hai payload ví dụ:

~~~json
{
  "sku": "BK-080",
  "itemName": "So REST"
}
~~~

và:

~~~json
{
  "sku": "BK-081",
  "itemName": "So REST khac",
  "note": null
}
~~~

Nếu ứng dụng áp dụng chính sách:

- Trường không xuất hiện → **bỏ cột khỏi INSERT**;
- Trường có `null` → **chèn `NULL` tường minh**;

thì kết quả với cột `note DEFAULT 'Chưa có ghi chú'` sẽ khác nhau. Payload thứ nhất nhận default, payload thứ hai lưu `NULL`.

Nhưng một số ORM có thể luôn liệt kê toàn bộ cột và bind `NULL` cho trường không có giá trị trong object, ngay cả khi client không gửi trường đó. Trong trường hợp này, **default ở database có thể không được áp dụng** như kỳ vọng.

**Không suy từ JSON hay entity rằng database chắc chắn thấy một cột bị bỏ qua.** Hãy xem câu SQL thật do driver/ORM phát ra, các annotation/default mappings và cơ chế insert động của framework đang dùng.

### 14.2. Bean có giá trị mặc định trong Java không thay thế database default

Ví dụ một class có:

~~~java
private int stockQty = 0;
private String status = "DRAFT";
~~~

đó là **giá trị khởi tạo trong Java**. Nếu ORM đưa chúng vào `INSERT`, database nhận **giá trị tường minh**, không cần áp dụng default của cột. Điều đó có thể phù hợp, nhưng cần quyết định đâu là **nguồn chuẩn (source of truth)** của quy tắc mặc định.

Trong hệ thống có nhiều ứng dụng cùng ghi một bảng, default tại database giúp nhất quán khi cột bị bỏ qua; default ở ứng dụng giúp logic rõ trước khi gửi dữ liệu. Hai lớp có thể phối hợp, nhưng cần tránh lệch giữa giá trị `'DRAFT'` ở Java và `'ACTIVE'` trong schema.

### 14.3. Không truyền identity do client tự đặt

Một API tạo sản phẩm thường nên nhận:

~~~json
{
  "sku": "BK-082",
  "itemName": "So tu ung dung",
  "stockQty": 10
}
~~~

nhưng không khuyến khích client tự gửi `itemId` như một khóa tự chọn nếu bảng đã dùng `GENERATED ALWAYS AS IDENTITY`. Server/DBMS tạo khóa và **trả lại trong response** sau khi INSERT thành công.

Phải phân biệt **mã nội bộ** do DBMS sinh với **mã nghiệp vụ** `sku` có thể được người dùng cung cấp sau khi kiểm tra hợp lệ.

### 14.4. Dùng tham số hóa với INSERT

Ví dụ JDBC:

~~~java
String sql = """
    INSERT INTO inventory_items (sku, item_name, stock_qty)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "BK-083");
    ps.setString(2, "So an toan");
    ps.setInt(3, 5);
    ps.executeUpdate();
}
~~~

Không nối input người dùng trực tiếp vào câu SQL. Cũng không truyền chuỗi `"DEFAULT"` vào placeholder rồi hy vọng DBMS xem đó là từ khóa `DEFAULT`: placeholder bind **giá trị dữ liệu**, không tự biến thành một token cú pháp SQL.

Khi cần dùng default, hãy **bỏ cột khỏi câu INSERT** hoặc viết từ khóa `DEFAULT` tường minh trong SQL được xây dựng từ cấu trúc đáng tin cậy. Nếu số lượng cột thay đổi theo request, câu SQL động phải được tạo bằng danh sách cột **đã cho phép**, còn giá trị vẫn bind bằng tham số.

## 15. Những lỗi và hiểu nhầm phổ biến

| Lỗi/hiểu nhầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Bỏ một cột là database bỏ qua ràng buộc của nó.” | `INSERT` vẫn có thể vi phạm `NOT NULL`/`CHECK` | Hàng mới phải hợp lệ sau khi DBMS điền giá trị |
| “Có `DEFAULT` thì truyền `NULL` cũng nhận default.” | Cột nullable sẽ lưu `NULL` tường minh | Bỏ cột hoặc dùng `DEFAULT`; ngoại lệ theo dialect như Oracle `DEFAULT ON NULL` |
| “`NULL` là chuỗi `'NULL'`.” | Sai kiểm tra dữ liệu thiếu | Dùng `IS NULL`/`IS NOT NULL` |
| “`NOT NULL DEFAULT 0` cho phép truyền NULL vì có số 0.” | `INSERT` có thể lỗi `NOT NULL` | Default chỉ áp dụng khi được yêu cầu hoặc bỏ cột |
| “`CHECK (qty >= 0)` luôn cấm NULL.” | `UNKNOWN` có thể vượt qua `CHECK` | Thêm `NOT NULL` khi bắt buộc có giá trị |
| “`DEFAULT VALUES` chèn được vào mọi bảng.” | Có thể lỗi nếu có cột bắt buộc không có default | Chỉ dùng khi mọi giá trị cần thiết được cung cấp bằng mặc định/cơ chế khác |
| “Identity bảo đảm khóa liên tục 1,2,3...” | Có thể có khoảng trống | Identity giúp sinh khóa, không đảm bảo gapless |
| “Identity tự đảm bảo khóa duy nhất theo mọi đường ghi.” | Override/sequence có thể tạo xung đột | Giữ `PRIMARY KEY` hoặc `UNIQUE` |
| “ID lớn nhất là hàng vừa chèn của tôi.” | Sai khi có nhiều người dùng | Dùng `RETURNING`/`OUTPUT`/generated keys |
| “ID lớn hơn chắc chắn có thời điểm commit muộn hơn.” | Không đúng khi đồng thời/override | Lưu timestamp và thứ tự nghiệp vụ riêng |
| “`SERIAL` của PostgreSQL là một kiểu IDENTITY tương đương hoàn toàn.” | Nhầm cơ chế sequence và identity | Hiểu default sequence và tính năng identity |
| “Generated column và DEFAULT là một.” | Định nghĩa sai công thức phụ thuộc các cột | Dùng `GENERATED ... AS (...)` cho biểu thức từ cùng hàng |
| “Có thể truyền bất kỳ `line_total` nào vào generated column.” | Lỗi do cột chỉ cho DBMS tính | Truyền quantity/price, để DBMS tính total |
| “`DEFAULT CURRENT_TIMESTAMP` tự cập nhật khi UPDATE.” | `updated_at` không đổi như kỳ vọng | Thiết kế cập nhật riêng theo nghiệp vụ |
| “ORM thiếu field chắc chắn bỏ cột trong INSERT.” | ORM có thể bind `NULL` tường minh | Quan sát SQL sinh thực tế và cấu hình ORM |
| “`AUTO_INCREMENT`, `IDENTITY`, `ROWID` có cùng cú pháp.” | Không chạy trên DBMS khác | Dùng đúng dialect/phiên bản |
| “`INSERT ... SELECT` có thể đặt `DEFAULT` ở mọi biểu thức SELECT.” | Sai cú pháp ở nhiều engine | Bỏ cột đích muốn nhận default |
| “`COALESCE(input, 0)` luôn tương đương default schema.” | Dễ khác nếu default đổi/khác 0 | Xác định rõ fallback nghiệp vụ và nguồn chuẩn |

## 16. Bài tập thực hành

Các bài tập dùng bảng `inventory_items`, `insert_events` và `invoice_lines` của bài. Khi muốn chạy nhiều lần, hãy đổi SKU/order_code để tránh vi phạm `UNIQUE` hoặc xung đột với dữ liệu đã tạo. Những đoạn được ghi **“lỗi”** chỉ nhằm phân tích, không phải lệnh cần chạy trên production.

### Bài 1 — Dự đoán giá trị khi bỏ cột

Với schema `inventory_items` ban đầu, câu sau điền gì vào `stock_qty`, `item_status`, `note` và `created_at`?

~~~sql
INSERT INTO inventory_items (sku, item_name)
VALUES ('EX-001', 'Bai tap mot')
RETURNING item_id, stock_qty, item_status, note, created_at;
~~~

**Đáp án:** `stock_qty = 0`; `item_status = 'DRAFT'`; `note = 'Chưa có ghi chú'`; `created_at` từ `CURRENT_TIMESTAMP` theo DBMS/transaction; `item_id` do identity sinh. Không tự đoán `item_id` hay thời gian cụ thể.

### Bài 2 — DEFAULT khác NULL ở note

Đọc hai câu lệnh:

~~~sql
INSERT INTO inventory_items (sku, item_name, note)
VALUES ('EX-002', 'Bai tap hai A', DEFAULT);

INSERT INTO inventory_items (sku, item_name, note)
VALUES ('EX-003', 'Bai tap hai B', NULL);
~~~

**Câu hỏi:** hàng nào có `note IS NULL = TRUE`?

**Đáp án:** chỉ `EX-003`. `EX-002` dùng chuỗi mặc định `'Chưa có ghi chú'`; `EX-003` lưu `NULL` tường minh vì cột `note` cho phép `NULL`.

### Bài 3 — NULL vào cột NOT NULL

Dự đoán:

~~~sql
INSERT INTO inventory_items (
    sku, item_name, stock_qty
)
VALUES ('EX-004', 'Bai tap ba', NULL);
~~~

**Đáp án:** trong PostgreSQL, câu chèn lỗi `NOT NULL` vì `stock_qty` bắt buộc có giá trị. `DEFAULT 0` không thay `NULL` được truyền tường minh. Muốn dùng mặc định, bỏ `stock_qty` hoặc viết `DEFAULT` thay cho `NULL`.

### Bài 4 — DEFAULT VALUES

Vì sao:

~~~sql
INSERT INTO inventory_items DEFAULT VALUES;
~~~

thất bại, nhưng:

~~~sql
INSERT INTO insert_events DEFAULT VALUES;
~~~

có thể thành công?

**Đáp án:** `inventory_items` có `sku` và `item_name` `NOT NULL` không có default; hàng chỉ từ default không đáp ứng ràng buộc. `insert_events` có default cho `event_type` và `created_at`, identity cho `event_id`, cột `detail` nullable không default nên có thể nhận `NULL`.

### Bài 5 — Nhiều hàng, một số dùng DEFAULT

Viết câu `INSERT` thêm hai sản phẩm:

- `EX-005`: `stock_qty` mặc định, trạng thái mặc định;
- `EX-006`: `stock_qty = 8`, `item_status = 'ACTIVE'`.

**Đáp án:**

~~~sql
INSERT INTO inventory_items (
    sku, item_name, stock_qty, item_status
)
VALUES
    ('EX-005', 'Bai tap nam A', DEFAULT, DEFAULT),
    ('EX-006', 'Bai tap nam B', 8, 'ACTIVE')
RETURNING sku, stock_qty, item_status;
~~~

Kết quả `EX-005` dùng `0, DRAFT`, còn `EX-006` dùng `8, ACTIVE`.

### Bài 6 — CHECK không thay NOT NULL

Giả sử cột là:

~~~sql
quantity INTEGER CHECK (quantity >= 0)
~~~

**Câu hỏi:** có chắc nó từ chối `quantity = NULL` không?

**Đáp án:** **không**. Biểu thức `NULL >= 0` là `UNKNOWN`; `CHECK` trong SQL thường từ chối `FALSE` nhưng không từ chối `UNKNOWN`. Muốn số lượng luôn được cung cấp, khai báo `NOT NULL`; nếu muốn mặc định 0 khi không truyền, thêm `DEFAULT 0`.

### Bài 7 — GENERATED ALWAYS AS IDENTITY

Vì sao câu sau không phải cách INSERT thông thường trên PostgreSQL?

~~~sql
INSERT INTO inventory_items (
    item_id, sku, item_name
)
VALUES (900, 'EX-007', 'Bai tap bay');
~~~

**Đáp án:** `item_id` khai báo `GENERATED ALWAYS AS IDENTITY`, nên người dùng thường không truyền ID tường minh. Nếu thật sự cần nhập lại giá trị ID có sẵn, PostgreSQL có `OVERRIDING SYSTEM VALUE` và phải xử lý vấn đề trùng khóa/sequence; không dùng override tùy tiện trong ứng dụng thông thường.

### Bài 8 — BY DEFAULT AS IDENTITY

So sánh:

~~~sql
CREATE TABLE example_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);
~~~

với `GENERATED ALWAYS AS IDENTITY`.

**Đáp án:** `BY DEFAULT` cho phép DBMS sinh khóa khi người dùng bỏ cột hoặc yêu cầu default, đồng thời chấp nhận ID tường minh theo cú pháp thông thường trong PostgreSQL. `ALWAYS` có kiểm soát chặt hơn khi cung cấp ID tường minh và thường cần override. Cả hai vẫn nên có `PRIMARY KEY` hoặc ràng buộc duy nhất.

### Bài 9 — Generated column tính tiền

Với bảng `invoice_lines`:

~~~sql
INSERT INTO invoice_lines (
    order_code, quantity, unit_price
)
VALUES (
    'EX-009', 3, 12000.00
)
RETURNING quantity, unit_price, line_total;
~~~

**Đáp án:** `quantity = 3`, `unit_price = 12000` và `line_total = 36000` do generated expression `quantity * unit_price` tính. Không cần truyền `line_total`.

### Bài 10 — Generated column khác DEFAULT

Hai người phát biểu:

- A: “`line_total` nhận một giá trị mặc định duy nhất lúc INSERT.”
- B: “`line_total` được tính từ `quantity` và `unit_price` theo định nghĩa generated column.”

Ai đúng?

**Đáp án:** **B**. `line_total` là cột tính toán. Khi dữ liệu nguồn `quantity`/`unit_price` thay đổi theo `UPDATE`, hệ thống tính lại giá trị generated STORED theo quy tắc engine; còn default thường không tự cập nhật vì thay đổi một cột khác.

### Bài 11 — Vì sao không dùng MAX(id)+1?

Giả sử hai ứng dụng đồng thời muốn tạo sản phẩm mới và cả hai cùng chạy:

~~~sql
SELECT MAX(item_id) + 1
FROM inventory_items;
~~~

**Đáp án:** hai transaction có thể đọc cùng một `MAX` và chọn trùng ID trước khi một bên commit. Đây là race condition; nên để DBMS cấp identity/sequence và giữ `PRIMARY KEY`, rồi lấy ID từ kết quả chèn/driver.

### Bài 12 — Gaps trong dãy identity

Một transaction chèn hàng và được cấp ID 25, sau đó `ROLLBACK`. Câu chèn tiếp theo nhận ID 26. Có thể kết luận hệ thống mất dữ liệu không?

**Đáp án:** **không**. Trong PostgreSQL, sequence thường không rollback giá trị đã cấp; khoảng trống có thể xuất hiện tự nhiên. Identity dùng để nhận diện hàng, không phải bộ đếm liên tục hoặc số chứng từ gapless.

### Bài 13 — Viết INSERT và lấy ID trong JDBC

Viết Java/JDBC chèn sản phẩm mới, để DBMS sinh `item_id` và lấy lại khóa.

**Gợi ý đáp án:**

~~~java
String sql = """
    INSERT INTO inventory_items (sku, item_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "EX-013");
    ps.setString(2, "Bai tap muoi ba");
    ps.executeUpdate();

    try (ResultSet rs = ps.getGeneratedKeys()) {
        if (rs.next()) {
            long id = rs.getLong(1);
            System.out.println(id);
        }
    }
}
~~~

Sự hỗ trợ của `getGeneratedKeys` và cột trả về phụ thuộc driver; có thể dùng PostgreSQL `RETURNING item_id` khi chạy trên PostgreSQL.

### Bài 14 — Phân biệt dữ liệu bị bỏ qua và dữ liệu NULL từ API

Một request không chứa thuộc tính `note`; request khác chứa `"note": null`. Nếu API ánh xạ đúng thành “bỏ cột” và “truyền NULL” tương ứng, database lưu gì?

**Đáp án:** request thứ nhất dùng default `'Chưa có ghi chú'`; request thứ hai lưu `NULL` (nếu cột nullable). Nhưng nếu ORM luôn đưa cột vào `INSERT` và bind `NULL`, cả hai có thể thành `NULL`. Phải kiểm tra SQL thật và quy ước API/ORM.

### Bài 15 — Đổi DEFAULT có sửa hàng cũ không?

Giả sử sau khi đã có các hàng DRAFT, chạy:

~~~sql
ALTER TABLE inventory_items
ALTER COLUMN item_status SET DEFAULT 'ACTIVE';
~~~

**Đáp án:** các hàng đã lưu `'DRAFT'` **không tự đổi** thành ACTIVE. Giá trị mặc định mới áp dụng cho các lần gán default/thêm hàng tiếp theo theo cú pháp. Nếu muốn đổi trạng thái hàng cũ, cần thao tác `UPDATE` riêng và điều kiện rõ ràng.

### Bài 16 — Chọn cơ chế phù hợp

Chọn cơ chế hợp lý nhất cho từng nhu cầu:

1. Sinh khóa nội bộ duy nhất cho từng sản phẩm;
2. Nếu không nhập số lượng tồn kho, dùng 0;
3. Tính tiền dòng đơn bằng số lượng nhân đơn giá;
4. Lưu thời điểm tạo hàng do database cung cấp;
5. Từ chối trạng thái ngoài `DRAFT`, `ACTIVE`, `ARCHIVED`.

**Đáp án gợi ý:**

1. Identity/auto-increment kết hợp `PRIMARY KEY`;
2. `DEFAULT 0` kết hợp `NOT NULL` và `CHECK` phù hợp;
3. Generated/computed column hoặc một cơ chế tính nhất quán khác của DBMS;
4. `DEFAULT CURRENT_TIMESTAMP`/hàm thời gian tương ứng, kèm quy tắc timezone;
5. `CHECK`, enum/lookup table hoặc ràng buộc miền được thiết kế theo nghiệp vụ.

Không có một cơ chế `DEFAULT` duy nhất thay thế tất cả những nhu cầu trên.

## 17. Checklist thiết kế INSERT có default và cột tự sinh

Trước khi thêm một bảng mới hoặc dùng `INSERT` trong ứng dụng, hãy trả lời:

1. **Cột nào bắt buộc do ứng dụng cung cấp?** Chúng có `NOT NULL` và không có default giả tạo?
2. **Cột nào có giá trị mặc định thật sự đúng nghiệp vụ?** Ví dụ số lượng 0, trạng thái DRAFT.
3. **Cột nào nên cho phép `NULL`?** Có phân biệt “chưa biết” với “0”, chuỗi rỗng hoặc “chưa có” không?
4. **Khi người dùng truyền `NULL` tường minh, chính sách là gì?** Lưu NULL, từ chối hay chuyển thành default bằng tính năng riêng của DBMS?
5. **Khóa chính được sinh theo cơ chế nào?** Identity/sequence/autoincrement hay một dạng ID khác?
6. **Ràng buộc unique nghiệp vụ nằm ở đâu?** Có nên giữ `sku UNIQUE` ngoài identity PK?
7. **Giá trị nào phụ thuộc vào các cột trong cùng hàng?** Cần generated column hay một phép tính riêng?
8. **Kết quả tạo hàng có được trả về client không?** Dùng `RETURNING`/`OUTPUT`/generated keys phù hợp.
9. **Khi INSERT thất bại hoặc rollback, có đang giả định ID liên tục không?** Nếu có, cần sửa thiết kế.
10. **ORM có bỏ cột hay bind NULL?** Đã xem SQL được sinh thực tế chưa?
11. **Thời gian mặc định có ngữ nghĩa gì?** Theo transaction/statement/clock, múi giờ và độ chính xác ra sao?
12. **Khi default thay đổi, dữ liệu cũ có cần migration không?** `ALTER DEFAULT` không tự biến mọi hàng cũ thành giá trị mới.
13. **Dialect/phiên bản có hỗ trợ cú pháp đang dùng không?** `GENERATED AS IDENTITY`, `AUTO_INCREMENT`, `RETURNING`, `PERSISTED` và `DEFAULT ON NULL` không tương đương tuyệt đối.

## 18. Tổng kết

Khi thêm hàng vào bảng, **bỏ qua một cột**, dùng từ khóa **`DEFAULT`** và truyền **`NULL`** là ba lựa chọn phải được hiểu riêng:

- **Bỏ cột hoặc dùng `DEFAULT`:** DBMS áp dụng biểu thức mặc định/cơ chế sinh tương ứng; nếu không có default, cột có thể nhận `NULL`, sau đó vẫn phải thỏa mọi constraint.
- **Truyền `NULL` tường minh:** thường lưu `NULL` hoặc bị `NOT NULL` từ chối; default thông thường **không tự kích hoạt**, ngoại trừ những tính năng riêng như Oracle `DEFAULT ON NULL`.
- **Identity/auto-increment:** giúp DBMS tạo định danh, nhưng không đảm bảo số liên tục, thứ tự sự kiện hoặc thay thế các constraint nghiệp vụ.
- **Generated/computed columns:** tính giá trị từ biểu thức gắn với hàng, khác với một default được dùng khi giá trị bị bỏ qua.

Dù SQL nhìn ngắn gọn, cần xác định rõ **nguồn giá trị**, **quy tắc thiếu dữ liệu**, **ràng buộc**, **phương thức trả ID** và **dialect**. Cách thiết kế tốt là để database thực thi những quy tắc mang tính toàn vẹn dữ liệu, đồng thời để ứng dụng phân biệt rạch ròi giữa **không cung cấp giá trị** và **chủ động yêu cầu ghi `NULL`**.
