# Nạp lặp có kiểm soát bằng khóa nghiệp vụ và ràng buộc duy nhất

Trong hệ thống thực tế, cùng một lô dữ liệu có thể được gửi lại nhiều lần. Một dịch vụ nhận webhook có thể nhận lại sự kiện vì phía gửi chưa nhận được xác nhận; một công việc ETL có thể phải chạy lại sau lỗi mạng; một tệp giao dịch có thể được nhập lại để sửa dữ liệu; hoặc hai worker cùng cố ghi một đơn hàng.

Nếu mỗi lần nhận lại đều thực hiện `INSERT` vô điều kiện, bảng đích có thể chứa nhiều bản ghi đại diện cho **cùng một đối tượng nghiệp vụ**:

```text
Lần nạp 1: đơn WEB / ORD-1001 → một hàng
Lần nạp 2: đơn WEB / ORD-1001 → thêm một hàng trùng
Lần nạp 3: đơn WEB / ORD-1001 → thêm một hàng trùng
```

Hậu quả là báo cáo đếm ba đơn thay vì một, doanh thu có thể bị cộng nhiều lần, và khóa ngoại từ các bảng khác không còn có một đối tượng rõ ràng để tham chiếu.

Mục tiêu của **nạp lặp có kiểm soát** là: cùng một dữ liệu nghiệp vụ được xử lý lại mà không làm tăng số đối tượng hoặc thay đổi trạng thái ngoài chủ đích. Trong Database SQL, nền tảng của cách làm này gồm:

1. **Khóa nghiệp vụ** (*business key*) xác định một đối tượng là ai.
2. **Ràng buộc duy nhất** (*UNIQUE constraint/index*) để database bảo vệ tính duy nhất, kể cả khi ghi đồng thời.
3. **Chính sách xử lý xung đột**: bỏ qua, cập nhật, từ chối hay đưa vào vùng kiểm tra.
4. **Kiểm soát phiên bản và giao dịch** để dữ liệu đến muộn hoặc nạp lại không ghi đè trạng thái mới hơn.

Bài học thuộc chương **Thêm dữ liệu** của Database SQL. Các ví dụ có thể chạy theo thứ tự trên **PostgreSQL**. Những khác biệt với MySQL, SQL Server, SQLite và Oracle được trình bày riêng; không giả định mọi hệ quản trị có cùng cú pháp `UPSERT`.

## 1. “Nạp lặp an toàn” nghĩa là gì?

Trong xử lý dữ liệu, ta thường muốn một thao tác có tính **idempotent**: thực hiện lại cùng thao tác với cùng đầu vào sẽ cho cùng trạng thái nghiệp vụ mong muốn.

Hình dung thao tác nạp lô B:

```text
Trạng thái T trước khi nạp
        │
        ├── Nạp B lần đầu → Trạng thái T'
        │
        └── Nạp lại chính B trên T' → Vẫn là T'
```

Viết ngắn gọn, nếu `Load` là thao tác biến đổi trạng thái:

\[
Load(Load(T, B), B) = Load(T, B)
\]

Đẳng thức này nói về **trạng thái mà nghiệp vụ quan tâm**, chẳng hạn tập đơn hàng, số tiền, trạng thái và phiên bản nguồn. Nó không đương nhiên có nghĩa mọi hiệu ứng vật lý của database đều giống hệt: dãy số tự tăng có thể bị tiêu hao, log có thể ghi nhận lần thử, và trigger hoặc hệ thống bên ngoài có thể có tác dụng phụ nếu thiết kế không cẩn thận.

### 1.1. Ba tình huống cần phân biệt

Giả sử khóa đơn là `(source_system, external_order_id)`:

| Đầu vào | Đích hiện có? | Hành vi mong muốn |
| --- | --- | --- |
| Một đơn hoàn toàn mới | Chưa | Chèn một hàng |
| Cùng đơn, cùng phiên bản và dữ liệu | Có | Không tạo bản sao; thường không cập nhật |
| Cùng đơn, phiên bản mới hơn hợp lệ | Có | Cập nhật chính hàng đó theo quy tắc |
| Cùng đơn, phiên bản cũ đến muộn | Có | Không ghi đè phiên bản mới |
| Cùng khóa và cùng phiên bản nhưng nội dung khác | Có | Báo xung đột dữ liệu, không âm thầm chọn một |
| Dữ liệu thiếu khóa nghiệp vụ | Không xác định được đối tượng | Từ chối hoặc đưa vào khu vực cách ly |

Ở đây, “kiểm soát” không chỉ là **chống thêm trùng**, mà còn là quyết định đúng khi đầu vào đại diện cho **thay đổi thực sự**.

### 1.2. “At least once” không đồng nghĩa “exactly once”

Nhiều hệ thống truyền tin bảo đảm ít nhất một lần giao sự kiện: phía nhận có thể nhận **một hoặc nhiều lần**. Database có thể biến nhiều lần nhận thành **một trạng thái kết quả** bằng khóa và ràng buộc duy nhất.

Nhưng một câu `INSERT ... ON CONFLICT` **không tự biến toàn bộ pipeline thành “exactly once”**. Nếu cùng sự kiện còn gây gửi email, trừ tiền, phát thông báo hoặc gọi API ngoài, những hiệu ứng đó phải được kiểm soát riêng, ví dụ bằng khóa idempotency của hành động, transactional outbox hoặc quy trình ghi nhận và xác nhận phù hợp.

## 2. Khóa nghiệp vụ, khóa thay thế và grain của dữ liệu

**Grain** là cấp độ mà một hàng đại diện cho một đối tượng hay sự kiện. Trước khi thêm dữ liệu, phải nói rõ mỗi hàng có nghĩa gì.

Ví dụ:

- Bảng `orders`: một hàng trên **mỗi đơn hàng từ một hệ nguồn**.
- Bảng `order_items`: một hàng trên **mỗi dòng hàng của một đơn**.
- Bảng `payments`: một hàng trên **mỗi giao dịch thanh toán**.
- Bảng `daily_sales`: một hàng trên **mỗi ngày–cửa hàng–loại tiền tệ**.

Một khóa đúng cho `orders` chưa chắc đúng cho `payments`. Nếu một đơn có ba lần thanh toán, dùng `order_id` duy nhất cho bảng thanh toán sẽ làm mất hai giao dịch hợp lệ.

### 2.1. Khóa thay thế không giải quyết trùng nghiệp vụ

Một bảng có thể dùng khóa chính tự sinh:

```sql
CREATE TABLE orders_example (
    order_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_id TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);
```

`order_pk` bảo đảm **hai hàng không có cùng giá trị khóa chính**. Nhưng database vẫn cho phép:

```text
order_pk = 1, external_order_id = ORD-1001
order_pk = 2, external_order_id = ORD-1001
order_pk = 3, external_order_id = ORD-1001
```

Ba khóa chính khác nhau không chứng minh có ba đơn khác nhau. Nếu `external_order_id` là định danh nghiệp vụ, cần một **UNIQUE** thích hợp trên nó hoặc trên bộ khóa đầy đủ.

### 2.2. Khóa nghiệp vụ có thể gồm nhiều cột

ID đơn `ORD-1001` có thể được phát hành đồng thời bởi hệ `WEB` và hệ `POS`. Khi đó chỉ dùng `external_order_id` sẽ gây **xung đột giả** giữa hai đơn hợp lệ.

Khóa đúng của bài:

```text
(source_system, external_order_id)
```

Ví dụ:

| `source_system` | `external_order_id` | Có phải cùng đối tượng? |
| --- | --- | --- |
| WEB | ORD-1001 | Đơn thứ nhất |
| POS | ORD-1001 | Đơn thứ hai, không trùng đơn WEB |
| WEB | ORD-1001 | Lặp lại đơn thứ nhất |

Một hệ thống đa tenant có thể cần khóa `(tenant_id, source_system, external_order_id)`. **Phạm vi duy nhất** phải được nêu trong hợp đồng dữ liệu, không đoán theo một cột có tên `id`.

### 2.3. Dấu hiệu của khóa nghiệp vụ tốt

Khóa nên:

- **Xác định duy nhất** một đối tượng trong phạm vi đã định.
- **Ổn định** khi thuộc tính mô tả thay đổi.
- **Có thể lấy lại** từ đầu vào khi nạp lại.
- **Không được tái sử dụng** cho đối tượng khác, trừ khi có cơ chế định danh bổ sung.
- Có quy tắc rõ về **phân biệt hoa–thường, khoảng trắng, định dạng, NULL**.

Email, tên người hoặc địa chỉ thường **không phải khóa ổn định** cho thực thể khách hàng; chúng có thể đổi hoặc không duy nhất. Mã giao dịch bên nguồn, mã sự kiện hoặc một ID được hợp đồng nguồn bảo đảm thường phù hợp hơn.

## 3. UNIQUE là hàng rào cuối cùng chống ghi trùng

Với PostgreSQL, khai báo khóa thay thế và khóa nghiệp vụ:

```sql
CREATE TEMP TABLE demo_orders_269 (
    order_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system TEXT NOT NULL,
    external_order_id TEXT NOT NULL,
    customer_ref TEXT NOT NULL,
    order_total NUMERIC(12, 2) NOT NULL CHECK (order_total >= 0),
    order_state TEXT NOT NULL
        CHECK (order_state IN ('pending', 'paid', 'cancelled', 'refunded')),
    source_revision INTEGER NOT NULL CHECK (source_revision >= 1),
    source_changed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_demo_orders_269_business
        UNIQUE (source_system, external_order_id)
);
```

Hai loại ràng buộc phục vụ hai mục tiêu:

| Thành phần | Vai trò |
| --- | --- |
| `PRIMARY KEY(order_pk)` | ID kỹ thuật để tham chiếu nội bộ |
| `UNIQUE(source_system, external_order_id)` | Không cho hai hàng cùng một đơn nghiệp vụ |
| `NOT NULL` trên bộ khóa | Ngăn thiếu thành phần định danh |
| `CHECK(order_total >= 0)` | Bảo vệ miền giá trị mẫu |
| `CHECK(order_state IN (...))` | Bảo vệ trạng thái được phép |
| `source_revision` | So sánh phiên bản khi nhận cập nhật |

### 3.1. UNIQUE phát hiện trùng ngay tại database

Sau khi thêm một hàng:

```sql
INSERT INTO demo_orders_269 (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1001', 'C-01',
    120.00, 'paid', 1, TIMESTAMPTZ '2025-06-01 09:00:00+00'
);
```

Cố gắng thêm cùng khóa một lần nữa bằng `INSERT` thuần:

```sql
-- CỐ Ý GÂY LỖI UNIQUE; chỉ chạy nếu muốn quan sát lỗi.
INSERT INTO demo_orders_269 (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1001', 'C-01',
    120.00, 'paid', 1, TIMESTAMPTZ '2025-06-01 09:00:00+00'
);
```

PostgreSQL báo lỗi vi phạm ràng buộc `uq_demo_orders_269_business`. Đây là hành vi **đúng**: database từ chối thêm một đối tượng đã có.

Trong phần thực hành đầy đủ bên dưới, ta sẽ tạo lại bảng tạm trên một kết nối mới hoặc bắt đầu từ trạng thái vừa tạo; ví dụ lỗi ở trên chỉ nhằm giải thích ràng buộc, **không phải bước bắt buộc trong quy trình nạp mẫu**.

### 3.2. Vì sao không dùng SELECT MAX(order_pk) + 1?

Khóa tự sinh `order_pk` không phải căn cứ để nhận diện đơn nghiệp vụ. Tự tạo khóa bằng:

```sql
SELECT MAX(order_pk) + 1 FROM demo_orders_269;
```

không chống được hai phiên cùng chọn một giá trị, cũng không giải quyết vấn đề cùng đơn `WEB/ORD-1001` được nạp lại. Để sinh khóa thay thế, dùng identity/sequence theo DBMS. Để chống **bản sao nghiệp vụ**, dùng `UNIQUE` trên khóa nghiệp vụ.

## 4. Vì sao “kiểm tra rồi INSERT” chưa đủ khi có đồng thời?

Một cách viết dễ gặp:

```sql
INSERT INTO demo_orders_269 (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
SELECT
    'WEB', 'ORD-2001', 'C-10',
    50.00, 'pending', 1,
    TIMESTAMPTZ '2025-06-01 10:00:00+00'
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_orders_269 AS t
    WHERE t.source_system = 'WEB'
      AND t.external_order_id = 'ORD-2001'
);
```

Câu này có thể tránh thêm trùng trong một tình huống đơn giản, nhưng **không phải cơ chế chống trùng an toàn nếu chỉ dựa vào nó**.

Hai transaction có thể diễn ra:

```text
Phiên A                              Phiên B
--------------------------------    --------------------------------
Kiểm tra: chưa có ORD-2001
                                    Kiểm tra: chưa có ORD-2001
Thử INSERT
                                    Thử INSERT
COMMIT                              Thử ghi trùng → cần UNIQUE xử lý
```

Cả hai phiên có thể đồng thời nhìn thấy “chưa có”. Nếu không có ràng buộc duy nhất, hai hàng trùng có thể được ghi. Nếu có `UNIQUE`, database sẽ xử lý xung đột; một bên có thể chờ và nhận lỗi.

**Nguyên tắc:** `NOT EXISTS` có ích để tìm dữ liệu chưa tồn tại, nhưng **không thay thế ràng buộc duy nhất** trong tình huống nhiều phiên ghi.

## 5. Ba chính sách khi gặp khóa nghiệp vụ đã tồn tại

Một hệ thống cần chọn chính sách trước khi viết SQL.

### 5.1. Từ chối và báo lỗi

```sql
INSERT INTO demo_orders_269 (...)
VALUES (...);
```

Phù hợp khi việc nạp trùng là dấu hiệu dữ liệu bất thường và cần dừng lô để điều tra. Ràng buộc `UNIQUE` bảo vệ bảng.

### 5.2. Bỏ qua nếu đã tồn tại: insert-if-absent

PostgreSQL:

```sql
INSERT INTO demo_orders_269 (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1001', 'C-01',
    120.00, 'paid', 1, TIMESTAMPTZ '2025-06-01 09:00:00+00'
)
ON CONFLICT (source_system, external_order_id)
DO NOTHING;
```

Nếu khóa chưa tồn tại, câu lệnh chèn. Nếu khóa đã tồn tại, câu lệnh không chèn thêm hàng.

Đây là hành vi **“đã có thì giữ nguyên”**. Nó không tự sửa dữ liệu cũ nếu đầu vào mới mang amount hoặc trạng thái khác.

### 5.3. Cập nhật khi có phiên bản mới hơn: upsert

```sql
INSERT INTO demo_orders_269 AS t (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1001', 'C-01',
    125.00, 'paid', 2, TIMESTAMPTZ '2025-06-02 07:00:00+00'
)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    customer_ref = EXCLUDED.customer_ref,
    order_total = EXCLUDED.order_total,
    order_state = EXCLUDED.order_state,
    source_revision = EXCLUDED.source_revision,
    source_changed_at = EXCLUDED.source_changed_at,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_revision > t.source_revision;
```

Trong PostgreSQL:

- `ON CONFLICT (source_system, external_order_id)` chọn khóa duy nhất dùng để phát hiện xung đột.
- `EXCLUDED` là hàng ứng viên **đã được đề xuất chèn**.
- `t` là alias của hàng đã tồn tại trong bảng đích.
- `DO UPDATE SET` thay đổi chính hàng đích khi có xung đột.
- `WHERE EXCLUDED.source_revision > t.source_revision` chỉ áp dụng cập nhật nếu bản nguồn mới hơn.

Nếu bản ghi đến cùng `source_revision` hoặc cũ hơn, `DO UPDATE` **không thực hiện cập nhật**. Lưu ý điều kiện `WHERE` này nằm trong **nhánh xử lý xung đột**; nó không ngăn việc chèn một khóa hoàn toàn mới.

## 6. Lựa chọn chính sách cập nhật không đơn giản là “lấy bản cuối”

Khi một khóa nghiệp vụ đã tồn tại, có nhiều quy tắc có thể hợp lệ:

| Tình huống | Quy tắc phù hợp trong một số nghiệp vụ |
| --- | --- |
| Bản ghi mới có revision cao hơn | Cập nhật nếu nguồn bảo đảm revision tăng theo thực thể |
| Bản ghi có revision bằng và nội dung bằng | Không làm gì |
| Bản ghi có revision bằng nhưng nội dung khác | Báo lỗi/đưa vào khu vực bất thường |
| Bản ghi cũ đến sau bản mới | Bỏ qua hoặc ghi nhận là sự kiện đến trễ |
| Bản ghi bị hủy | Cập nhật trạng thái hoặc xử lý tombstone theo thiết kế |
| Khóa nghiệp vụ bị đổi hợp lệ | Dùng bảng ánh xạ định danh/di trú, không coi là đơn mới tùy tiện |
| Nguồn gửi toàn bộ ảnh chụp mới | Có thể đồng bộ trạng thái theo snapshot đã xác thực, khác với xử lý sự kiện lẻ |

Không phải dữ liệu nào cũng có `source_revision` đáng tin cậy. Nếu chỉ có `source_changed_at`, cần làm rõ độ chính xác, múi giờ, khả năng hai cập nhật trùng timestamp và liệu đồng hồ nguồn có thực sự đơn điệu hay không.

Nếu phía nguồn cung cấp một **số phiên bản tăng dần cho từng khóa**, dùng nó để ngăn bản cũ ghi đè bản mới thường dễ giải thích hơn dựa vào thời gian nhận ở hệ đích.

## 7. Tạo bảng staging để nạp lô có kiểm soát

Nạp lặp thường gồm hai lớp:

```text
File / API / webhook
          │
          ▼
    Staging / landing
          │
          ├── Kiểm tra schema và miền giá trị
          ├── Chuẩn hóa khóa theo hợp đồng
          ├── Phát hiện trùng trong cùng lô
          └── Chọn một bản nguồn hợp lệ cho mỗi khóa
          │
          ▼
    INSERT ... ON CONFLICT
          │
          ▼
    Bảng đích có UNIQUE nghiệp vụ
```

Staging lưu các hàng nhận được cùng `batch_id` và vị trí hàng nguồn. Ta **không** đặt `UNIQUE(source_system, external_order_id)` trên bảng staging, bởi đôi khi cần **quan sát bản ghi trùng trong chính lô** trước khi quyết định cách xử lý.

### 7.1. Bảng staging

```sql
CREATE TEMP TABLE demo_stage_orders_269 (
    batch_id INTEGER NOT NULL,
    source_row_no INTEGER NOT NULL,
    source_system TEXT NOT NULL,
    external_order_id TEXT NOT NULL,
    customer_ref TEXT NOT NULL,
    order_total NUMERIC(12, 2) NOT NULL CHECK (order_total >= 0),
    order_state TEXT NOT NULL
        CHECK (order_state IN ('pending', 'paid', 'cancelled', 'refunded')),
    source_revision INTEGER NOT NULL CHECK (source_revision >= 1),
    source_changed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (batch_id, source_row_no)
);
```

`(batch_id, source_row_no)` chỉ định danh **hàng nhập**. Nó không phải khóa nghiệp vụ của đơn. Hai hàng nguồn khác nhau vẫn được phép nói về cùng một đơn.

### 7.2. Nạp lô 1: bốn đơn nghiệp vụ

```sql
INSERT INTO demo_stage_orders_269 (
    batch_id, source_row_no, source_system, external_order_id,
    customer_ref, order_total, order_state,
    source_revision, source_changed_at
)
VALUES
    (1, 1, 'WEB', 'ORD-1001', 'C-01', 120, 'paid',
        1, TIMESTAMPTZ '2025-06-01 09:00:00+00'),
    (1, 2, 'WEB', 'ORD-1002', 'C-02', 80, 'pending',
        1, TIMESTAMPTZ '2025-06-01 10:00:00+00'),
    (1, 3, 'POS', 'ORD-1001', 'C-09', 200, 'paid',
        1, TIMESTAMPTZ '2025-06-01 11:00:00+00'),
    (1, 4, 'WEB', 'ORD-1003', 'C-03', 50, 'paid',
        1, TIMESTAMPTZ '2025-06-01 12:00:00+00');
```

Hai mã `ORD-1001` đến từ `WEB` và `POS` là **hai đơn khác nhau** vì khóa nghiệp vụ có `source_system`.

### 7.3. Nạp lô 2: cập nhật, trùng trong lô và đơn mới

```sql
INSERT INTO demo_stage_orders_269 (
    batch_id, source_row_no, source_system, external_order_id,
    customer_ref, order_total, order_state,
    source_revision, source_changed_at
)
VALUES
    (2, 1, 'WEB', 'ORD-1001', 'C-01', 125, 'paid',
        2, TIMESTAMPTZ '2025-06-02 07:00:00+00'),
    (2, 2, 'WEB', 'ORD-1002', 'C-02', 80, 'pending',
        1, TIMESTAMPTZ '2025-06-01 10:00:00+00'),
    (2, 3, 'WEB', 'ORD-1004', 'C-04', 75, 'pending',
        1, TIMESTAMPTZ '2025-06-02 08:00:00+00'),
    (2, 4, 'POS', 'ORD-1001', 'C-09', 190, 'refunded',
        2, TIMESTAMPTZ '2025-06-02 09:00:00+00'),
    (2, 5, 'WEB', 'ORD-1001', 'C-01', 125, 'paid',
        2, TIMESTAMPTZ '2025-06-02 07:00:00+00');
```

Lô 2 có **năm hàng nguồn** nhưng chỉ **bốn khóa nghiệp vụ khác nhau**, vì hai hàng `(2,1)` và `(2,5)` là bản sao cùng phiên bản của `WEB/ORD-1001`.

### 7.4. Nạp lô 3: sự kiện cũ đến muộn

```sql
INSERT INTO demo_stage_orders_269 (
    batch_id, source_row_no, source_system, external_order_id,
    customer_ref, order_total, order_state,
    source_revision, source_changed_at
)
VALUES
    (3, 1, 'WEB', 'ORD-1001', 'C-01', 115, 'pending',
        1, TIMESTAMPTZ '2025-05-31 15:00:00+00');
```

Lô 3 mô phỏng một thông điệp **revision 1** đến sau khi hệ thống đã ghi **revision 2**. Chính sách của ví dụ là **không được ghi đè** bản mới bằng bản cũ.

## 8. Phát hiện trùng bên trong lô trước khi UPSERT

Trước khi ghi đích, cần hiểu lô nguồn có bao nhiêu hàng cho mỗi khóa.

```sql
SELECT
    batch_id,
    source_system,
    external_order_id,
    COUNT(*) AS source_rows,
    MIN(source_revision) AS min_revision,
    MAX(source_revision) AS max_revision
FROM demo_stage_orders_269
WHERE batch_id = 2
GROUP BY batch_id, source_system, external_order_id
HAVING COUNT(*) > 1
ORDER BY source_system, external_order_id;
```

Kết quả:

| `batch_id` | `source_system` | `external_order_id` | `source_rows` | Revision |
| ---: | --- | --- | ---: | --- |
| 2 | WEB | ORD-1001 | 2 | 2 |

### 8.1. Trùng khóa không phải lúc nào cũng là trùng nội dung

Hai hàng mang cùng khóa có thể là:

- **Bản sao hoàn toàn:** cùng revision, cùng trường nghiệp vụ; thường có thể chọn một.
- **Hai phiên bản hợp lệ:** revision 1 và 2 trong một lô; thường chọn bản có revision lớn hơn nếu mục tiêu là bảng trạng thái hiện tại.
- **Xung đột cùng phiên bản:** cùng khóa, cùng revision nhưng amount hoặc status khác; không được âm thầm chọn tùy ý.

Ví dụ PostgreSQL phát hiện trường hợp **cùng revision, nội dung khác** ngay trong staging:

```sql
SELECT
    a.batch_id,
    a.source_system,
    a.external_order_id,
    a.source_revision,
    a.source_row_no AS first_row,
    b.source_row_no AS second_row
FROM demo_stage_orders_269 AS a
JOIN demo_stage_orders_269 AS b
    ON b.batch_id = a.batch_id
   AND b.source_system = a.source_system
   AND b.external_order_id = a.external_order_id
   AND b.source_revision = a.source_revision
   AND b.source_row_no > a.source_row_no
WHERE
    ROW(a.customer_ref, a.order_total, a.order_state, a.source_changed_at)
    IS DISTINCT FROM
    ROW(b.customer_ref, b.order_total, b.order_state, b.source_changed_at)
ORDER BY a.batch_id, a.source_system, a.external_order_id;
```

Với bộ dữ liệu mẫu, truy vấn này trả **0 hàng**, vì hai bản sao trong lô 2 giống hệt nhau. Nếu có kết quả, pipeline nên **quarantine** hoặc từ chối lô theo chính sách dữ liệu, thay vì để `ROW_NUMBER` che mất xung đột.

### 8.2. Chọn một hàng xác định trên mỗi khóa nghiệp vụ

Có thể dùng `ROW_NUMBER()`:

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_order_id
            ORDER BY source_revision DESC, source_row_no DESC
        ) AS rn
    FROM demo_stage_orders_269 AS s
    WHERE batch_id = 2
)
SELECT
    source_system,
    external_order_id,
    source_revision,
    order_total,
    order_state
FROM ranked
WHERE rn = 1
ORDER BY source_system, external_order_id;
```

Kết quả có **bốn hàng**: `POS/ORD-1001`, `WEB/ORD-1001`, `WEB/ORD-1002` và `WEB/ORD-1004`.

`ORDER BY source_revision DESC` chọn revision cao nhất. `source_row_no DESC` là một cách phá hòa **có tính xác định trong lô**, nhưng chỉ nên dùng sau khi đã kiểm tra rằng những hàng cùng khóa và cùng revision không mâu thuẫn. “Dòng xuất hiện cuối” không tự động có tính đúng đắn nghiệp vụ.

## 9. Vì sao phải khử trùng trong lô trước ON CONFLICT DO UPDATE?

PostgreSQL không cho một câu `INSERT ... ON CONFLICT DO UPDATE` tác động lên **cùng một hàng đích nhiều lần** theo cách không xác định.

Ví dụ nguy hiểm nếu trực tiếp đưa cả hai bản sao lô 2 của `WEB/ORD-1001` vào cùng câu `INSERT ... DO UPDATE`: database có thể báo lỗi dạng **cannot affect row a second time**.

Ràng buộc `UNIQUE` giúp chặn trùng ở bảng đích nhưng **không biến nhiều hàng trùng trong nguồn của một câu lệnh thành một lựa chọn tự động đúng nghiệp vụ**.

Vì vậy, đối với chiến lược upsert theo trạng thái hiện tại:

1. Kiểm tra chất lượng lô.
2. Chọn **một hàng hợp lệ trên mỗi khóa nghiệp vụ**.
3. `INSERT ... ON CONFLICT DO UPDATE` vào bảng đích.
4. Xác nhận kết quả nạp ở cấp khóa.

Nếu nghiệp vụ là **lưu mọi sự kiện** thay vì bảng trạng thái hiện tại, không nên khử trùng theo khóa thực thể; khi đó khóa của bảng sự kiện thường cần thêm `event_id` hoặc định danh sự kiện riêng. Bài này chủ yếu xử lý bảng **trạng thái đơn hiện tại**.

## 10. Quy trình nạp hoàn chỉnh bằng PostgreSQL UPSERT

Các bảng `demo_orders_269` và `demo_stage_orders_269` đã được tạo ở phần 3 và 7. Để dễ chạy lại các lô, định nghĩa một câu `PREPARE` nhận `batch_id`.

### 10.1. Chuẩn bị truy vấn nạp có kiểm soát

```sql
PREPARE load_demo_batch_269(integer) AS
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY s.source_system, s.external_order_id
            ORDER BY s.source_revision DESC, s.source_row_no DESC
        ) AS rn
    FROM demo_stage_orders_269 AS s
    WHERE s.batch_id = $1
)
INSERT INTO demo_orders_269 AS t (
    source_system,
    external_order_id,
    customer_ref,
    order_total,
    order_state,
    source_revision,
    source_changed_at
)
SELECT
    source_system,
    external_order_id,
    customer_ref,
    order_total,
    order_state,
    source_revision,
    source_changed_at
FROM ranked
WHERE rn = 1
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    customer_ref = EXCLUDED.customer_ref,
    order_total = EXCLUDED.order_total,
    order_state = EXCLUDED.order_state,
    source_revision = EXCLUDED.source_revision,
    source_changed_at = EXCLUDED.source_changed_at,
    updated_at = CURRENT_TIMESTAMP
WHERE EXCLUDED.source_revision > t.source_revision
RETURNING
    source_system,
    external_order_id,
    order_total,
    order_state,
    source_revision;
```

Đọc từng lớp:

- `ranked` đánh số hàng theo **khóa nghiệp vụ**, ưu tiên phiên bản nguồn cao nhất.
- `WHERE rn = 1` chỉ chuyển một hàng đại diện cho mỗi khóa sang `INSERT`.
- `ON CONFLICT` dựa vào `UNIQUE(source_system, external_order_id)` của bảng đích.
- Khi chưa có khóa, `INSERT` tạo hàng mới.
- Khi khóa đã có, chỉ `DO UPDATE` nếu revision đầu vào lớn hơn revision đích.
- `RETURNING` trả các hàng **được chèn hoặc thực sự được cập nhật**. Các hàng xung đột nhưng không thỏa điều kiện cập nhật không nằm trong `RETURNING`.

Truy vấn dùng **revision của nguồn** làm quyền quyết định thứ tự cập nhật. Nếu nguồn không có revision đáng tin cậy, không được tự thay bằng `source_row_no` của staging vì thứ tự hàng trong một lô không nói lên thứ tự thay đổi xuyên lô.

### 10.2. Thực hiện lô 1

```sql
EXECUTE load_demo_batch_269(1);
```

Lô 1 thêm bốn khóa nghiệp vụ:

| `source_system` | `external_order_id` | `order_total` | `order_state` | `revision` |
| --- | --- | ---: | --- | ---: |
| POS | ORD-1001 | 200 | paid | 1 |
| WEB | ORD-1001 | 120 | paid | 1 |
| WEB | ORD-1002 | 80 | pending | 1 |
| WEB | ORD-1003 | 50 | paid | 1 |

Thứ tự hiển thị của `RETURNING` không được bảo đảm; bảng trên chỉ trình bày theo khóa cho dễ đọc.

Kiểm tra tập hiện tại:

```sql
SELECT
    source_system, external_order_id, order_total,
    order_state, source_revision
FROM demo_orders_269
ORDER BY source_system, external_order_id;
```

Kết quả có **4 hàng**.

### 10.3. Nạp lại lô 1

```sql
EXECUTE load_demo_batch_269(1);
```

Mỗi khóa đã tồn tại với `source_revision = 1`. Điều kiện:

```sql
WHERE EXCLUDED.source_revision > t.source_revision
```

đều sai, nên không có hàng nào bị cập nhật; `RETURNING` **không có hàng**. Bảng đích vẫn gồm **4 đơn**.

Chỉ nhìn vào số hàng đích, ta kiểm tra được rằng không có bản sao nghiệp vụ được chèn thêm. Khi đánh giá idempotency sâu hơn, còn cần kiểm tra trường `updated_at`, trigger, log và tác động ra hệ thống ngoài theo hợp đồng của pipeline.

### 10.4. Nạp lô 2

```sql
EXECUTE load_demo_batch_269(2);
```

Lô 2 có bốn khóa sau khi chọn hàng đại diện:

- `WEB/ORD-1001`: revision 2 lớn hơn 1 → cập nhật tổng từ 120 thành 125.
- `WEB/ORD-1002`: revision 1 bằng 1 → giữ nguyên.
- `WEB/ORD-1004`: khóa chưa tồn tại → chèn mới.
- `POS/ORD-1001`: revision 2 lớn hơn 1 → cập nhật tổng từ 200 thành 190, trạng thái từ `paid` sang `refunded`.

Vì vậy, câu `RETURNING` có **3 hàng thay đổi**, còn bảng đích có **5 khóa nghiệp vụ**.

### 10.5. Nạp lại lô 2

```sql
EXECUTE load_demo_batch_269(2);
```

Bây giờ các khóa liên quan đã đạt revision lớn nhất của lô. Không có revision mới hơn, nên `RETURNING` trả **0 hàng** và bảng đích vẫn có **5 đơn**.

### 10.6. Nạp sự kiện cũ lô 3

```sql
EXECUTE load_demo_batch_269(3);
```

`WEB/ORD-1001` đang ở revision 2, trong khi lô 3 chỉ có revision 1. Sự kiện cũ không ghi đè tổng 125 và trạng thái paid. `RETURNING` trả **0 hàng**.

### 10.7. Bảng kết quả cuối cùng

```sql
SELECT
    source_system,
    external_order_id,
    customer_ref,
    order_total,
    order_state,
    source_revision
FROM demo_orders_269
ORDER BY source_system, external_order_id;
```

Kết quả sau lô 1 → lô 1 lặp → lô 2 → lô 2 lặp → lô 3:

| Nguồn | Mã đơn | Khách | Tổng đơn | Trạng thái | Revision |
| --- | --- | --- | ---: | --- | ---: |
| POS | ORD-1001 | C-09 | 190 | refunded | 2 |
| WEB | ORD-1001 | C-01 | 125 | paid | 2 |
| WEB | ORD-1002 | C-02 | 80 | pending | 1 |
| WEB | ORD-1003 | C-03 | 50 | paid | 1 |
| WEB | ORD-1004 | C-04 | 75 | pending | 1 |

Số hàng là **5**, số khóa nghiệp vụ khác nhau cũng là **5**. Không có thêm hàng do nạp lại, và bản cũ không làm mất revision mới.

Dùng xong ví dụ có thể giải phóng prepared statement:

```sql
DEALLOCATE load_demo_batch_269;
```

## 11. Quy tắc cập nhật phiên bản và giới hạn của nó

Điều kiện:

```sql
WHERE EXCLUDED.source_revision > t.source_revision
```

nghĩa là **chỉ ghi nhận nguồn mới hơn**. Nó có những đặc tính quan trọng:

1. Bản lặp cùng revision được bỏ qua.
2. Bản cũ đến sau không thể ghi đè bản mới.
3. Bản mới hơn được ghi nhận, kể cả khi một số thuộc tính nghiệp vụ không thay đổi.
4. Bản cùng revision nhưng payload khác **cũng bị bỏ qua** — vì vậy phải có bước phát hiện xung đột, không được coi việc không cập nhật là bằng chứng đầu vào đúng.

### 11.1. Vì sao vẫn cập nhật source_revision nếu payload không đổi?

Giả sử revision 2 giữ nguyên `order_total = 120` và `order_state = 'paid'` so với revision 1. Nếu ta bỏ cập nhật chỉ vì các cột nghiệp vụ giống nhau, đích có thể vẫn lưu revision 1.

Sau đó một sự kiện revision 1 khác hoặc một cập nhật revision thấp hơn nhưng payload khác đến muộn; thiếu thông tin revision cao nhất có thể làm logic so sánh sai.

Vì vậy, khi nguồn có revision đáng tin cậy, **revision cũng là một phần của trạng thái cần đồng bộ**, ngay cả khi nội dung hiển thị không đổi. Việc có muốn thay `updated_at` trong trường hợp chỉ tiến revision hay không phải được định nghĩa rõ.

### 11.2. Nếu chỉ có thời điểm thay đổi từ nguồn?

Một mẫu có điều kiện:

```sql
WHERE EXCLUDED.source_changed_at > t.source_changed_at
```

có thể phù hợp khi nguồn bảo đảm thời điểm thay đổi **đơn điệu và đủ độ phân giải** cho từng khóa.

Nhưng timestamp có thể trùng nhau, đồng hồ bị lệch, sự kiện gửi lại hoặc các vùng thời gian được ghi không nhất quán. Khi không có bảo đảm về thứ tự, “bản có timestamp lớn nhất” chưa chắc là bản đúng nhất.

Một hợp đồng nguồn tốt có thể cung cấp `revision`, `sequence_number` hoặc `event_id` cùng thứ tự đáng tin cậy, thay vì yêu cầu database đoán “bản mới” từ thời gian nhận.

### 11.3. Không dùng updated_at của đích để so với thời gian nguồn

`updated_at` của đích là thời điểm xử lý trong database. Nó có thể lớn hơn `source_changed_at` của một sự kiện hợp lệ đến muộn, hoặc nhỏ hơn thời gian trên đồng hồ nguồn bị lệch.

Hãy phân biệt:

| Trường | Ý nghĩa |
| --- | --- |
| `source_revision` | Phiên bản do nguồn phát hành |
| `source_changed_at` | Thời điểm đối tượng thay đổi ở nguồn |
| `received_at` | Thời điểm pipeline nhận được thông điệp |
| `created_at` | Thời điểm tạo hàng đích |
| `updated_at` | Thời điểm cập nhật hàng đích |

Không nên dùng các trường này thay nhau mà không có quy tắc nghiệp vụ.

## 12. Chọn giữa DO NOTHING và DO UPDATE

Hai chính sách chống trùng không tương đương.

### 12.1. Insert-if-absent

```sql
INSERT INTO demo_orders_269 (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1003', 'C-03',
    999.00, 'paid', 99, TIMESTAMPTZ '2025-07-01 00:00:00+00'
)
ON CONFLICT (source_system, external_order_id)
DO NOTHING;
```

`WEB/ORD-1003` đã tồn tại, nên tổng tiền **không đổi thành 999**. Câu này phù hợp cho dữ liệu **bất biến sau khi tạo**, hoặc khi quy định rõ mọi lần gửi lại cùng khóa phải được bỏ qua.

Nếu đơn có thể được chỉnh sửa hợp lệ, `DO NOTHING` có thể làm **mất cập nhật**.

### 12.2. Upsert phiên bản mới

`DO UPDATE` phù hợp cho bảng lưu **trạng thái hiện tại** của đơn. Nhưng phải xác định điều kiện cập nhật: revision, trạng thái hợp lệ, nguồn có quyền ghi hoặc các điều kiện khác.

Một câu luôn cập nhật:

```sql
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    order_total = EXCLUDED.order_total,
    updated_at = CURRENT_TIMESTAMP
```

có thể khiến **nạp lại cùng một bản ghi** thay đổi `updated_at` và kích hoạt trigger/CDC, dù nội dung không mới. Vì vậy, phiên bản của bài dùng `WHERE EXCLUDED.source_revision > t.source_revision`.

### 12.3. Khi không có revision nhưng chỉ muốn cập nhật nếu dữ liệu khác

PostgreSQL có `IS DISTINCT FROM` để so sánh có xử lý `NULL`:

```sql
-- Mẫu minh họa, giả sử khóa và quyền ghi đã được xác thực.
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    customer_ref = EXCLUDED.customer_ref,
    order_total = EXCLUDED.order_total,
    order_state = EXCLUDED.order_state,
    updated_at = CURRENT_TIMESTAMP
WHERE
    ROW(t.customer_ref, t.order_total, t.order_state)
    IS DISTINCT FROM
    ROW(EXCLUDED.customer_ref, EXCLUDED.order_total, EXCLUDED.order_state)
```

Cách này giảm cập nhật không cần thiết khi payload không đổi, nhưng **không bảo vệ trước dữ liệu cũ đến muộn**: một payload cũ khác vẫn có thể ghi đè payload mới. Nó chỉ giải quyết **phát hiện sự khác nhau**, không giải quyết **thứ tự phiên bản**.

## 13. NULL trong khóa UNIQUE: bẫy thường bị bỏ qua

Trong PostgreSQL, ràng buộc `UNIQUE` thông thường có thể cho phép **nhiều hàng mang `NULL`** ở cột khóa, vì `NULL` theo mặc định không bị xem là trùng theo cách của unique index thông thường.

Ví dụ khái niệm:

```sql
CREATE TEMP TABLE demo_optional_ref_269 (
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    UNIQUE (tenant_id, external_ref)
);

INSERT INTO demo_optional_ref_269 VALUES
    (1, NULL),
    (1, NULL);
```

Trong PostgreSQL với unique mặc định, hai hàng có `external_ref = NULL` vẫn được chấp nhận. Vì thế, nếu một cột là **thành phần bắt buộc của khóa nghiệp vụ**, hãy khai báo `NOT NULL`.

### 13.1. Khóa bắt buộc: NOT NULL và UNIQUE

```sql
CREATE TEMP TABLE demo_strict_ref_269 (
    tenant_id INTEGER NOT NULL,
    external_ref TEXT NOT NULL,
    payload TEXT,
    UNIQUE (tenant_id, external_ref)
);
```

Bây giờ thiếu `external_ref` bị từ chối; hai hàng cùng `tenant_id` và `external_ref` cũng bị từ chối.

### 13.2. Trường hợp muốn NULL được xem là trùng

PostgreSQL 15+ hỗ trợ cú pháp:

```sql
-- PostgreSQL 15+, dùng khi nghiệp vụ thực sự cần.
CREATE TEMP TABLE demo_nulls_not_distinct_269 (
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)
);
```

Khi đó hai hàng `(tenant_id = 1, external_ref = NULL)` xung đột với nhau.

Nhưng đây không phải cách thay thế mặc định cho khóa nghiệp vụ thiếu thông tin. Nếu không có mã định danh nguồn, nhiều bản ghi khác nhau có thể đều thiếu mã; ép mọi `NULL` thành “cùng đối tượng” cũng có thể sai. Chính sách thông thường là **từ chối hoặc cách ly đầu vào không có khóa**.

## 14. Chuẩn hóa khóa nghiệp vụ trước khi kiểm tra duy nhất

Các chuỗi sau có thể là cùng một mã theo hợp đồng của một nguồn:

```text
" ord-1001 "
"ORD-1001"
"Ord-1001"
```

Nhưng có những hệ thống phân biệt chữ hoa và chữ thường, hoặc coi khoảng trắng là có ý nghĩa. Việc chuẩn hóa phải dựa trên **hợp đồng định danh** chứ không dựa vào cảm giác.

### 14.1. Ví dụ chuẩn hóa có chủ đích

Giả sử hệ `WEB` quy định mã đơn không phân biệt hoa–thường và bỏ khoảng trắng ở hai đầu. Có thể dùng:

```sql
UPPER(BTRIM(external_order_id))
```

để chuẩn hóa trước khi ghi một cột `external_order_id_norm` được bảo vệ bằng unique.

Một thiết kế rõ ràng:

```sql
CREATE TEMP TABLE demo_normalized_keys_269 (
    tenant_id INTEGER NOT NULL,
    external_order_id_raw TEXT NOT NULL,
    external_order_id_norm TEXT GENERATED ALWAYS AS (
        UPPER(BTRIM(external_order_id_raw))
    ) STORED,
    CHECK (BTRIM(external_order_id_raw) <> ''),
    UNIQUE (tenant_id, external_order_id_norm)
);
```

Với thiết kế này, `' ord-1001 '` và `'ORD-1001'` thuộc cùng tenant sẽ xung đột.

### 14.2. Những vấn đề cần xác định trước khi chuẩn hóa

- Nguồn có thực sự coi `abc` và `ABC` như nhau không?
- Có được phép bỏ dấu gạch nối, dấu cách ở giữa hay số 0 ở đầu không?
- Mã `"0012"` và `"12"` có phải hai mã khác nhau không?
- Unicode, dấu tiếng Việt và quy tắc collation có thay đổi so sánh hay không?
- Cần giữ cả **raw key** và **canonical key** để điều tra nguồn dữ liệu không?

**Chuẩn hóa sai có thể gộp hai đối tượng thật thành một**, nguy hiểm không kém việc không chuẩn hóa và tạo bản sao.

## 15. Ràng buộc UNIQUE nhiều cột trong hệ đa tenant

Giả sử mỗi tenant có thể dùng mã `C-001` cho khách riêng:

```sql
CREATE TEMP TABLE demo_tenant_customers_269 (
    customer_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_customer_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    UNIQUE (tenant_id, external_customer_id)
);
```

Chèn hai khách:

```sql
INSERT INTO demo_tenant_customers_269 (
    tenant_id, external_customer_id, full_name
)
VALUES
    (10, 'C-001', 'An'),
    (20, 'C-001', 'Binh');
```

Hai hàng hợp lệ vì tenant khác nhau.

Nếu chỉ đặt `UNIQUE(external_customer_id)`, database sẽ nhầm hai khách này thành một khóa trùng. Nếu không đặt unique nào, hai phiên có thể chèn trùng `C-001` **trong cùng tenant**.

Khi nạp dữ liệu nhiều tenant, mọi điều kiện dò tìm, deduplicate và conflict target phải bao gồm **đầy đủ khóa phạm vi**:

```sql
ON CONFLICT (tenant_id, external_customer_id)
DO UPDATE SET
    full_name = EXCLUDED.full_name
```

Đồng thời phải kiểm soát quyền truy cập tenant ở lớp ứng dụng và database; unique key chỉ bảo vệ tính duy nhất, **không phải cơ chế phân quyền**.

## 16. Khóa nghiệp vụ thay đổi hoặc được tái sử dụng

Khóa tốt thường ổn định, nhưng đời thực có ngoại lệ:

- Hệ nguồn đổi định dạng mã đơn.
- Một công ty sáp nhập hai nguồn, khiến phạm vi mã thay đổi.
- Mã bên ngoài bị tái sử dụng sau nhiều năm.
- Một khách được gộp hoặc tách hồ sơ.
- Một bản ghi bị xóa mềm rồi tạo lại với cùng mã.

### 16.1. Không tự coi thay đổi khóa là một đơn mới

Nếu cùng đối tượng đổi mã từ `OLD-1001` sang `NEW-1001`, thao tác upsert trên khóa mới có thể tạo **một hàng thứ hai**. Ràng buộc `UNIQUE` không biết hai mã là một đối tượng.

Có thể cần một **bảng ánh xạ định danh**:

```text
(source_system, external_id) → canonical_entity_id
```

Khi nguồn thông báo đổi khóa, pipeline cập nhật ánh xạ theo quy tắc nghiệp vụ. Không nên xóa bản cũ hoặc gộp hai bản ghi chỉ dựa vào sự giống nhau của tên, email hoặc tổng tiền.

### 16.2. Khi nguồn có khả năng tái sử dụng ID

Nếu `ORD-1001` có thể được tái sử dụng cho một đơn mới sau một kỳ, khóa chỉ gồm `(source_system, external_order_id)` không còn duy nhất xuyên thời gian.

Có thể cần thêm một thành phần do nguồn quy định như `source_epoch`, `document_type` hoặc namespace khác, **nếu đó thực sự là một phần định danh**. Không thêm `load_date` một cách máy móc, vì làm như vậy sẽ khiến mỗi lần nạp lại ngày khác trở thành đối tượng mới.

## 17. Xóa mềm và unique chỉ trên bản ghi đang hoạt động

Giả sử yêu cầu “một tenant chỉ có một mã liên hệ **đang hoạt động**”, nhưng vẫn giữ các bản cũ đã bị xóa mềm để kiểm toán.

PostgreSQL có **partial unique index**:

```sql
CREATE TEMP TABLE demo_soft_deleted_269 (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_contact_id TEXT NOT NULL,
    label TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_demo_active_contact_269
ON demo_soft_deleted_269 (tenant_id, external_contact_id)
WHERE deleted_at IS NULL;
```

Index này bảo vệ tính duy nhất **chỉ trên các hàng có `deleted_at IS NULL`**. Các hàng đã xóa mềm được phép trùng khóa với hàng hoạt động, theo đúng quy tắc trên.

### 17.1. UPSERT vào partial unique index

Khi dùng PostgreSQL `ON CONFLICT`, cần chỉ ra predicate phù hợp với unique index:

```sql
INSERT INTO demo_soft_deleted_269 AS c (
    tenant_id, external_contact_id, label, deleted_at
)
VALUES (10, 'P-001', 'Main contact', NULL)
ON CONFLICT (tenant_id, external_contact_id)
WHERE deleted_at IS NULL
DO UPDATE SET
    label = EXCLUDED.label;
```

**Không mặc định** rằng `ON CONFLICT ON CONSTRAINT ...` có thể trỏ tới mọi unique index dạng partial: partial unique index là **index**, không phải một `UNIQUE CONSTRAINT` thông thường được khai báo cho toàn bảng.

### 17.2. Cân nhắc khôi phục hay tạo mới

Nếu một liên hệ đã xóa mềm được gửi lại, tạo một hàng mới có thể đúng hoặc sai tùy chính sách. Có hệ thống muốn **khôi phục hàng cũ** để giữ lịch sử cùng ID; có hệ thống muốn **một vòng đời mới**.

Cách xử lý phụ thuộc yêu cầu nghiệp vụ; không thể chỉ nhìn thấy `deleted_at` rồi quyết định dùng `ON CONFLICT DO NOTHING` hay `DO UPDATE`.

## 18. Transaction: nạp nhiều bảng phải nhất quán

Một đơn hàng có thể có bảng cha `orders` và bảng con `order_items`. Nạp trạng thái cha thành công nhưng lỗi khi nạp chi tiết có thể khiến dữ liệu không nhất quán.

Với PostgreSQL:

```sql
BEGIN;

-- Bước 1: kiểm tra dữ liệu lô và xác định khóa nghiệp vụ.
-- Bước 2: UPSERT bảng đơn.
-- Bước 3: UPSERT/thay thế chi tiết theo khóa dòng nghiệp vụ.
-- Bước 4: ghi nhận trạng thái xử lý lô.

COMMIT;
```

Nếu một bước lỗi và cần hoàn tác toàn bộ:

```sql
ROLLBACK;
```

Đoạn trên là **khung thao tác**, không phải một script hoàn chỉnh vì chưa định nghĩa bảng chi tiết và bảng log. Ý nghĩa là đặt các thay đổi cần nhất quán trong **cùng transaction** khi có thể.

### 18.1. Không giả định row count = số đối tượng nguồn

Một lô có thể có:

```text
100 hàng nguồn
→ 96 khóa khác nhau sau loại bản sao
→ 5 khóa mới
→ 12 khóa cập nhật phiên bản
→ 79 khóa giữ nguyên
```

Đếm số hàng `INSERT` trả về mà gọi đó là “đã xử lý 100 bản ghi” sẽ sai ý nghĩa. Cần phân biệt:

- Số hàng thô nhận được.
- Số khóa nghiệp vụ hợp lệ.
- Số hàng nguồn bị khử trùng.
- Số khóa mới được chèn.
- Số khóa đã thay đổi.
- Số khóa lặp/stale bị bỏ qua.
- Số khóa bị cách ly do lỗi.

Trong ví dụ phần 10, `RETURNING` phản ánh những hàng được chèn hoặc cập nhật, **không phân biệt trực tiếp hai loại bằng chính kết quả đang chọn**. Nếu vận hành cần tách chính xác inserted/updated, nên thiết kế lớp audit hoặc phương pháp nhận diện có hợp đồng rõ ràng, không suy luận tùy tiện từ ID tự tăng hoặc cột nội bộ không được cam kết.

### 18.2. Commit rồi mới xác nhận message

Giả sử ứng dụng đọc từ queue:

```text
Nhận event → ghi database → COMMIT → xác nhận đã xử lý với queue
```

Nếu ứng dụng chết sau `COMMIT` nhưng trước khi xác nhận, queue có thể gửi lại event. Thiết kế idempotent giúp lần lặp không tạo đơn trùng.

Nếu xác nhận queue **trước khi database commit**, lỗi sau đó có thể khiến event mất nhưng queue tưởng đã xử lý. Cần thiết kế thứ tự xác nhận và cơ chế retry phù hợp với dịch vụ message thực tế.

### 18.3. Transaction không làm được “gọi API ngoài và ghi DB atomic” một cách tự nhiên

Một transaction database thông thường không tự bao trùm email, thanh toán bên ngoài hoặc HTTP API. Nếu cần vừa ghi DB vừa phát thông điệp đáng tin cậy, cân nhắc **transactional outbox**: ghi bản thay đổi và bản ghi outbox trong cùng transaction, sau đó một worker phát thông điệp với cơ chế xử lý lặp an toàn.

## 19. Bảng ghi nhận lô và cơ chế chống xử lý cùng lô

Ngoài unique trên **thực thể**, có thể cần theo dõi **lô nạp**:

```sql
CREATE TEMP TABLE demo_batch_log_269 (
    batch_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('started', 'completed', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);
```

Ý nghĩa:

- `batch_id`: định danh lô xử lý.
- `content_fingerprint`: dấu vết nội dung giúp nhận biết cùng ID lô nhưng tệp đã đổi.
- `status`: trạng thái tiến trình.
- `completed_at`: mốc hoàn thành.

### 19.1. Unique ở cấp lô và cấp thực thể là hai lớp khác nhau

| Lớp | Khóa | Mục tiêu |
| --- | --- | --- |
| Bảng log lô | `batch_id` hoặc `(source_name, batch_external_id)` | Nhận diện lô đã được xử lý |
| Bảng đơn | `(source_system, external_order_id)` | Một hàng trên mỗi đơn nghiệp vụ |
| Bảng sự kiện | `(source_system, event_id)` | Nhận diện từng sự kiện để không xử lý hai lần |
| Bảng dòng đơn | `(source_system, external_order_id, line_id)` | Không tạo trùng dòng hàng trong một đơn |

Một lô mới vẫn có thể chứa những đơn đã có từ lô cũ, nên log lô **không thay thế** unique nghiệp vụ ở bảng đích.

### 19.2. Nếu batch_id cũ được gửi lại với nội dung khác?

Không nên tự coi là “đã xong” và bỏ qua mà không kiểm tra. Có thể có lỗi gắn lại cùng ID cho tệp khác.

Chính sách thường cần so sánh fingerprint và metadata:

- Cùng ID và cùng fingerprint, trạng thái completed → có thể xác nhận đã xử lý.
- Cùng ID nhưng fingerprint khác → báo xung đột/quarantine.
- Chưa hoàn thành → xác định cách retry/resume hoặc rollback.
- Lô bị mất kết nối sau commit → xác minh trạng thái committed trước khi quyết định chạy lại.

Dấu vết nội dung phải được tạo theo **định dạng chuẩn xác định**, tránh hai tệp giống về nghiệp vụ nhưng khác xuống dòng hoặc thứ tự không liên quan bị coi là khác không mong muốn; hoặc ngược lại dùng một fingerprint không đủ bảo đảm.

## 20. Quy tắc xóa: snapshot, delta và tombstone

Không phải mọi nguồn dữ liệu đều gửi từng thay đổi theo `revision`.

### 20.1. Delta/event

Nguồn gửi:

```text
ORD-1001 revision 2 → total 125
```

Bảng trạng thái hiện tại xử lý bằng upsert có điều kiện revision. Nếu muốn giữ **lịch sử sự kiện**, lưu thêm ở bảng event với khóa `event_id`, không chỉ cập nhật đè bản hiện tại.

### 20.2. Snapshot đầy đủ

Nguồn gửi một tệp chứa **tất cả đơn đang có trong phạm vi**. Khi đó một bản ghi đích không còn xuất hiện trong snapshot mới có thể cần được **đánh dấu không còn hoạt động**, nhưng chỉ khi snapshot được xác nhận là **đầy đủ và thành công**.

Không được dùng:

```sql
-- NGUY HIỂM: không dùng khi lô chỉ là bản cập nhật một phần.
DELETE FROM target
WHERE business_key NOT IN (SELECT business_key FROM staging);
```

một cách tùy tiện. Nếu staging chỉ có một phần dữ liệu hoặc chứa `NULL`, truy vấn có thể sai nghiêm trọng.

Nếu cần đồng bộ đầy đủ, quy trình phải xác định phạm vi snapshot (tenant, ngày, nguồn), tính hoàn chỉnh, khóa, chống chạy đồng thời và chính sách xóa mềm. Điều kiện “không xuất hiện” phải được áp dụng **trong đúng phạm vi snapshot được xác minh**.

### 20.3. Tombstone: sự kiện xóa có danh tính và phiên bản

Một nguồn có thể gửi:

```text
key = WEB / ORD-1001
revision = 4
operation = delete
```

Nếu chỉ xóa hẳn hàng đích, sau này một sự kiện revision 2 đến muộn có thể tạo lại đơn cũ vì khóa không còn trong bảng.

Để tránh **hồi sinh bản cũ**, một số hệ thống lưu **tombstone** hoặc trạng thái `deleted` kèm revision cao nhất. Khi sự kiện cũ đến, điều kiện revision bảo vệ trạng thái xóa.

Việc giữ tombstone bao lâu phụ thuộc hợp đồng giao sự kiện và thời gian có thể nhận dữ liệu đến muộn. Không mặc định thao tác `DELETE` vật lý là phương án đúng cho mọi pipeline.

## 21. Upsert và các tác dụng phụ ít được để ý

Một lần nạp lặp có thể không tạo bản sao nghiệp vụ nhưng vẫn phát sinh hiệu ứng khác.

### 21.1. Dãy số identity có thể xuất hiện khoảng trống

Khi thử chèn rồi gặp conflict, các hệ quản trị có thể đã đánh giá giá trị identity/sequence trước khi quyết định không chèn. Vì thế, ngay cả khi bảng chỉ có năm đơn, `order_pk` có thể có khoảng trống.

**Không dùng độ liên tục của ID tự sinh để xác minh nạp lặp.** Hãy kiểm tra khóa nghiệp vụ, số hàng và trường revision.

### 21.2. Trigger và updated_at

Một câu `ON CONFLICT DO UPDATE` không có điều kiện có thể thực hiện một UPDATE ngay cả khi dữ liệu giống hệt, làm:

- Thay đổi `updated_at`.
- Kích hoạt trigger cập nhật hoặc audit.
- Phát sinh row version mới, WAL/binlog và lưu lượng CDC.
- Kéo theo thông báo ngoài nếu trigger tích hợp không được kiểm soát.

Điều kiện `WHERE` trong nhánh update giảm những cập nhật không cần thiết. Tuy nhiên, việc *thử* insert và sự kiện trigger cụ thể vẫn phụ thuộc DBMS và thiết kế trigger; không được coi tất cả side effect đã biến mất chỉ vì `RETURNING` rỗng.

### 21.3. Các giá trị không xác định khi nạp

Các thao tác như:

```sql
updated_at = CURRENT_TIMESTAMP
```

hay gán mã ngẫu nhiên mới cho mỗi lần nhận có thể làm trạng thái thay đổi khi replay nếu nhánh update luôn chạy.

Nguyên tắc: những trường cần **ổn định theo sự kiện nguồn** nên nhận giá trị ổn định từ nguồn hoặc được sinh **chỉ khi thực sự tạo đối tượng**; những trường mô tả thời gian xử lý phải có quy tắc rõ khi chạy lại.

## 22. Đồng thời, mức cô lập và khả năng tranh chấp

Ràng buộc unique là **bảo đảm tại database** về không có hai hàng cùng khóa hợp lệ. Nhưng từ đó không thể suy ra mọi quy tắc nghiệp vụ đã được tuần tự hóa.

Ví dụ hai nguồn cùng gửi cập nhật mới cho `WEB/ORD-1001`:

```text
Worker A: revision 3
Worker B: revision 4
```

Với `ON CONFLICT DO UPDATE ... WHERE EXCLUDED.source_revision > t.source_revision`, PostgreSQL sẽ xử lý xung đột trên hàng đích theo cơ chế khóa và đồng thời của nó. Ý định là revision thấp không được ghi đè revision cao nếu các cập nhật được áp dụng đúng điều kiện.

Tuy nhiên cần tính đến:

- Mức cô lập transaction và khả năng retry khi gặp serialization failure/deadlock.
- Revision có thực sự tăng đơn điệu theo **cùng khóa** hay không.
- Trường hợp revision bằng nhau nhưng payload khác.
- Quy tắc thay đổi trạng thái có hợp lệ không (ví dụ `refunded` rồi nhận `pending`).
- Tác động trong nhiều bảng và hệ thống ngoài.

`UNIQUE` chống **trùng định danh**, chứ không tự đảm bảo một quy trình nhiều bước luôn an toàn trước mọi race condition.

### 22.1. Retry toàn bộ transaction

Nếu database báo lỗi có thể retry như deadlock hoặc serialization failure, ứng dụng có thể thử lại **toàn transaction** theo chính sách giới hạn và backoff.

Việc retry phải an toàn khi một lần thử trước đã commit nhưng ứng dụng không nhận được phản hồi. Đây chính là động lực thiết kế nạp lặp idempotent và ghi nhận batch/event có khóa.

### 22.2. Kiểm soát cạnh tranh trên nhiều khóa

Một lô có thể cập nhật hàng trăm khóa; hai lô đồng thời xử lý các khóa theo thứ tự khác nhau dễ tạo khóa chờ hoặc deadlock hơn khi thao tác đơn lẻ.

Có thể cân nhắc thứ tự khóa nhất quán, giới hạn kích thước batch, thực thi theo phân vùng nguồn hoặc cơ chế serialize có chủ đích. Quyết định cuối cùng phải dựa trên tải và mức cô lập thực tế; không thay thế thiết kế unique bằng một khóa ứng dụng không được chia sẻ giữa mọi writer.

## 23. Đối soát sau khi nạp

Sau khi viết dữ liệu, cần một cơ chế đối soát để biết pipeline đang tạo ra trạng thái đúng. Các truy vấn sau chỉ **đọc** bảng mẫu đã nạp theo phần 10.

### 23.1. Số hàng đích

```sql
SELECT COUNT(*) AS target_rows
FROM demo_orders_269;
```

Sau lô 1 và lô 2: **5** hàng.

### 23.2. Đếm khóa nghiệp vụ khác nhau

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT (source_system, external_order_id)) AS distinct_business_keys
FROM demo_orders_269;
```

Kết quả: **5** và **5**.

Với khóa được khai báo `NOT NULL` và unique, số này phải bằng nhau. Nó là một phép đối soát dễ đọc, nhưng **không thay thế** ràng buộc unique — truy vấn kiểm tra chỉ nhìn một thời điểm, còn ràng buộc bảo vệ mọi thao tác ghi.

### 23.3. Kiểm tra trùng trong staging

```sql
SELECT
    batch_id,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT (source_system, external_order_id))
        AS distinct_business_keys
FROM demo_stage_orders_269
GROUP BY batch_id
ORDER BY batch_id;
```

Kết quả:

| Batch | Hàng nguồn | Khóa nghiệp vụ khác nhau |
| ---: | ---: | ---: |
| 1 | 4 | 4 |
| 2 | 5 | 4 |
| 3 | 1 | 1 |

Có **một hàng lặp trong lô 2** theo khóa nghiệp vụ. Việc trùng khóa cần được phân loại như phần 8 trước khi bỏ đi, bởi đó có thể là nhiều revision hợp lệ hoặc mâu thuẫn dữ liệu.

### 23.4. Tìm đầu vào đến muộn so với trạng thái đích

```sql
SELECT
    s.batch_id,
    s.source_row_no,
    s.source_system,
    s.external_order_id,
    s.source_revision AS incoming_revision,
    t.source_revision AS stored_revision
FROM demo_stage_orders_269 AS s
JOIN demo_orders_269 AS t
    ON t.source_system = s.source_system
   AND t.external_order_id = s.external_order_id
WHERE s.source_revision < t.source_revision
ORDER BY s.batch_id, s.source_row_no;
```

Ví dụ, bản revision 1 của `WEB/ORD-1001` trong lô 3 sẽ được tìm thấy vì đích đã có revision 2. Các hàng cũ khác từ lô 1 cũng có thể xuất hiện nếu nhìn toàn bộ staging sau khi lô 2 được áp dụng.

### 23.5. Tìm cùng revision nhưng payload không khớp

```sql
SELECT
    s.batch_id,
    s.source_row_no,
    s.source_system,
    s.external_order_id,
    s.source_revision
FROM demo_stage_orders_269 AS s
JOIN demo_orders_269 AS t
    ON t.source_system = s.source_system
   AND t.external_order_id = s.external_order_id
WHERE s.source_revision = t.source_revision
  AND ROW(
      s.customer_ref, s.order_total, s.order_state, s.source_changed_at
  ) IS DISTINCT FROM ROW(
      t.customer_ref, t.order_total, t.order_state, t.source_changed_at
  )
ORDER BY s.batch_id, s.source_row_no;
```

Với dữ liệu mẫu sau các lượt nạp, truy vấn trả **0 hàng**. Nếu có kết quả, đó là tín hiệu quan trọng: cùng danh tính và phiên bản nhưng thông tin hai bên khác nhau. Pipeline nên có kênh xử lý bất thường thay vì bỏ qua im lặng.

### 23.6. Đối soát nên tách số bản ghi nguồn và số thay đổi

Ví dụ lô 2:

```text
Hàng nguồn nhận được:               5
Khóa nguồn khác nhau sau dedupe:    4
Khóa mới được chèn:                 1
Khóa đã cập nhật revision:          2
Khóa cùng revision giữ nguyên:      1
Tổng hàng đích sau lô:              5
```

Những số liệu này giúp phân biệt “pipeline bỏ qua vì lặp an toàn” với “pipeline lặng lẽ đánh mất thay đổi”.

## 24. Nạp qua nhiều hệ quản trị: tương đồng và khác biệt

Mọi hệ quản trị quan hệ lớn đều có cách bảo vệ khóa duy nhất, nhưng cú pháp upsert và chi tiết xử lý xung đột khác nhau.

### 24.1. PostgreSQL: ON CONFLICT

```sql
INSERT INTO orders AS t (
    source_system, external_order_id,
    amount, source_revision
)
VALUES ('WEB', 'ORD-1001', 125, 2)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    amount = EXCLUDED.amount,
    source_revision = EXCLUDED.source_revision
WHERE EXCLUDED.source_revision > t.source_revision;
```

Đây là ví dụ **cấu trúc** giả định bảng `orders` có các cột tương ứng. PostgreSQL có thể xác định conflict target theo khóa/cột hoặc ràng buộc unique cụ thể trong các trường hợp phù hợp.

### 24.2. MySQL: ON DUPLICATE KEY UPDATE

Trong MySQL, dạng thường gặp:

```sql
-- MySQL, ví dụ cấu trúc:
INSERT INTO orders (
    source_system, external_order_id, amount
)
VALUES ('WEB', 'ORD-1001', 125)
ON DUPLICATE KEY UPDATE
    amount = 125;
```

MySQL dùng `ON DUPLICATE KEY UPDATE` khi gặp xung đột trên khóa duy nhất/khóa chính phù hợp, nhưng **không chọn một conflict target theo danh sách cột giống PostgreSQL**.

Nếu bảng có **nhiều ràng buộc unique**, cần cân nhắc xung đột xảy ra trên khóa nào và bản ghi nào sẽ được cập nhật. Không viết một upsert có thể cập nhật nhầm hàng chỉ vì nó xung đột với một unique khác.

Cú pháp tham chiếu giá trị đầu vào trong nhánh update thay đổi theo phiên bản MySQL; cách dùng `VALUES(col)` cũ đã bị hạn chế/khuyến nghị thay thế trong một số phiên bản. Cần kiểm tra phiên bản thực tế trước khi dịch câu PostgreSQL có `EXCLUDED` sang MySQL.

### 24.3. SQLite: ON CONFLICT DO UPDATE

SQLite hỗ trợ upsert kiểu:

```sql
-- SQLite 3.24.0+; ví dụ cấu trúc:
INSERT INTO orders (
    source_system, external_order_id, amount
)
VALUES ('WEB', 'ORD-1001', 125)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET amount = excluded.amount;
```

Không nhầm với `INSERT OR REPLACE`: hành vi thay thế của SQLite có thể xóa hàng cũ rồi chèn mới, ảnh hưởng khóa ngoại, trigger và metadata. Nó không đồng nghĩa với việc cập nhật có kiểm soát đúng cùng hàng.

### 24.4. SQL Server: UNIQUE và chiến lược UPDATE/INSERT hoặc MERGE

SQL Server có `MERGE` để kết hợp nguồn và đích, nhưng cách dùng đồng thời, khóa và hành vi theo phiên bản cần được xem xét cẩn thận. Không nên nghĩ rằng thêm `MERGE` sẽ tự giải quyết mọi race condition.

Một mẫu giao dịch có ý định **cập nhật nếu có; nếu chưa thì chèn**:

```sql
-- SQL Server: ví dụ khung, cần thiết kế khóa và isolation phù hợp.
BEGIN TRANSACTION;

UPDATE dbo.orders
SET amount = @amount
WHERE source_system = @source_system
  AND external_order_id = @external_order_id;

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.orders (
        source_system, external_order_id, amount
    )
    VALUES (
        @source_system, @external_order_id, @amount
    );
END;

COMMIT TRANSACTION;
```

**Đây không phải công thức chống race hoàn chỉnh.** Dưới ghi đồng thời, hai phiên vẫn có thể tranh chấp giữa bước UPDATE và INSERT; cần `UNIQUE` ở database và có thể cần khóa phạm vi, isolation phù hợp hoặc xử lý lỗi và retry. Mẫu cũng cần được mở rộng nếu muốn kiểm soát revision hoặc tránh cập nhật bản lặp.

### 24.5. Oracle Database: MERGE

Oracle có `MERGE INTO ... USING ... ON ... WHEN MATCHED ... WHEN NOT MATCHED ...`:

```sql
-- Oracle: ví dụ cấu trúc, không phải script chạy trên PostgreSQL.
MERGE INTO orders t
USING (
    SELECT 'WEB' AS source_system,
           'ORD-1001' AS external_order_id,
           125 AS amount
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_order_id = s.external_order_id
)
WHEN MATCHED THEN
    UPDATE SET t.amount = s.amount
WHEN NOT MATCHED THEN
    INSERT (source_system, external_order_id, amount)
    VALUES (s.source_system, s.external_order_id, s.amount);
```

Khi nguồn `USING` có nhiều hàng cho cùng khóa, `MERGE` có thể gặp lỗi về tính ổn định/kết quả xác định. Vì vậy, **khử trùng nguồn và đặt ràng buộc unique** vẫn quan trọng, bất kể tên cú pháp là `MERGE` hay `ON CONFLICT`.

### 24.6. Bảng chọn giải pháp

| Hệ quản trị | Ràng buộc | Cơ chế nạp có xung đột thường dùng |
| --- | --- | --- |
| PostgreSQL | `PRIMARY KEY` / `UNIQUE` / unique index | `INSERT ... ON CONFLICT DO NOTHING/DO UPDATE` |
| MySQL/InnoDB | `PRIMARY KEY` / `UNIQUE` | `INSERT ... ON DUPLICATE KEY UPDATE` |
| SQLite | `PRIMARY KEY` / `UNIQUE` | `INSERT ... ON CONFLICT ... DO UPDATE` |
| SQL Server | `PRIMARY KEY` / `UNIQUE` | Transactional UPDATE/INSERT hoặc `MERGE` với thiết kế đồng thời cẩn trọng |
| Oracle | `PRIMARY KEY` / `UNIQUE` | `MERGE` hoặc chiến lược có xử lý xung đột |

Dù cú pháp nào, ba câu hỏi vẫn giống nhau: **định danh là gì**, **xung đột được bảo vệ ở đâu**, và **khi có bản mới thì ai được quyền thay thế bản cũ**?

## 25. Khóa duy nhất và bảng phân vùng

Khi bảng đích được phân vùng theo thời gian hoặc tenant, khả năng tạo một ràng buộc unique **toàn cục** có thể bị giới hạn bởi thiết kế partitioning và phiên bản DBMS.

Ví dụ, nếu business key là `(source_system, external_order_id)` nhưng bảng được chia theo `load_date`, việc đặt unique bao gồm `load_date` có thể cho phép **cùng đơn xuất hiện ở nhiều ngày nạp khác nhau**:

```text
WEB / ORD-1001 / load_date=01/06
WEB / ORD-1001 / load_date=02/06
```

Hai hàng khác partition key không xung đột nếu ràng buộc chỉ bảo vệ bộ ba này. Như vậy đã phá vỡ ý nghĩa “một hàng cho mỗi đơn”.

Trong PostgreSQL, các ràng buộc unique trên bảng partitioned có các yêu cầu liên quan đến cột partition key. Nếu cần bảo vệ một khóa nghiệp vụ không chứa partition key, có thể phải đổi chiến lược partition, dùng bảng ánh xạ khóa trung tâm, hoặc mô hình trạng thái/lịch sử riêng.

**Không được thêm ngày nạp vào unique key chỉ để làm câu DDL chạy được** nếu nó khiến mỗi lần replay ở ngày khác thành một đối tượng mới.

## 26. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng identity primary key | Mỗi lần nạp lại tạo một ID mới cho cùng đơn | Unique trên business key |
| Chọn khóa quá hẹp | Hai đơn hợp lệ từ hai nguồn xung đột | Bao gồm namespace/source/tenant cần thiết |
| Chọn khóa quá rộng, có `load_date` | Cùng đơn hôm sau không còn xung đột | Giữ đúng định danh thực thể, tách metadata lô |
| Dùng `SELECT NOT EXISTS` mà không có unique | Race condition giữa hai writer | UNIQUE ở database + upsert/retry |
| `ON CONFLICT DO NOTHING` cho dữ liệu có cập nhật | Bỏ mất revision mới | Chính sách `DO UPDATE` có điều kiện |
| `DO UPDATE` vô điều kiện | Replay làm đổi timestamp, trigger/audit | Kiểm soát revision hoặc so sánh payload |
| Chọn hàng staging cuối mà không kiểm tra | Có thể che xung đột cùng revision | Kiểm tra dữ liệu rồi dedupe có quy tắc |
| Đưa trùng khóa nguồn vào một `DO UPDATE` | Có thể báo lỗi tác động cùng hàng nhiều lần | Một hàng hợp lệ mỗi khóa trước upsert |
| Chỉ dựa vào thời gian nhận | Bản cũ đến muộn ghi đè bản mới | Dùng revision/sequence của nguồn |
| Bỏ qua payload khác cùng revision | Mất tín hiệu dữ liệu bất nhất | Quarantine/alert |
| Cho phép `NULL` ở business key | UNIQUE thông thường có thể không chống trùng NULL | `NOT NULL` hoặc quy tắc NULL rõ ràng |
| Chuẩn hóa ID mà không có hợp đồng | Gộp hai đối tượng khác nhau | Canonicalization được phê duyệt |
| Dùng `REPLACE` như một update bình thường | Có thể xóa/chèn lại, ảnh hưởng FK và trigger | Chọn upsert đúng semantics |
| Dùng `MERGE` và nghĩ không còn race | Đồng thời vẫn có thể gây xung đột | UNIQUE, isolation, retry |
| Không xử lý event cũ đến muộn | Trạng thái mới bị ghi lùi | Chỉ cập nhật khi revision tăng |
| Xóa hàng mà không giữ dấu vết revision | Event cũ có thể làm hồi sinh đối tượng | Tombstone hoặc cơ chế phòng vệ |
| Tin rằng ID tự tăng phải liên tục | Coi khoảng trống do conflict là lỗi nạp | Kiểm tra business key và revision |
| Tính tổng trên bảng staging | Một event lặp bị tính nhiều lần | Tổng hợp từ đích đúng grain hoặc dedupe |
| Không log khóa lỗi và lô bị lỗi | Không biết số hàng bị bỏ qua | Batch audit, quarantine, reconciliation |
| Retry gây tác dụng phụ ngoài DB | Email/thanh toán có thể lặp | Idempotency cho side effect, outbox |
| Chỉ unique ở một partition | Trùng thực thể xuyên partition | Thiết kế unique theo phạm vi nghiệp vụ |

## 27. Bài tập thực hành có đáp án

Các bài 1–14 dựa trên bảng `demo_orders_269` và `demo_stage_orders_269` đã tạo ở phần 3–7, sau khi thực hiện các lô ở phần 10. Những ví dụ giả định khác được ghi rõ.

### Bài 1 — Khóa nghiệp vụ của đơn là gì?

Hai hàng có:

```text
WEB / ORD-1001
POS / ORD-1001
```

có trùng nhau không?

**Đáp án:** Không, vì khóa nghiệp vụ trong bài là `(source_system, external_order_id)`. Chúng có cùng external ID nhưng thuộc hai nguồn.

### Bài 2 — Vì sao order_pk duy nhất vẫn chưa đủ?

**Đáp án:** `order_pk` chỉ phân biệt **hàng kỹ thuật**. Một đơn có thể bị nạp lặp thành nhiều hàng khác `order_pk`. `UNIQUE(source_system, external_order_id)` mới bảo vệ số đối tượng nghiệp vụ.

### Bài 3 — Số hàng staging ở lô 2

```sql
SELECT
    COUNT(*) AS source_rows,
    COUNT(DISTINCT (source_system, external_order_id))
        AS business_keys
FROM demo_stage_orders_269
WHERE batch_id = 2;
```

**Đáp án:** `source_rows = 5`, `business_keys = 4`. Hai hàng cùng khóa `WEB/ORD-1001` là bản sao trong lô.

### Bài 4 — Lô 1 nạp lần đầu và lần thứ hai

Sau lần nạp đầu của batch 1, có bao nhiêu đơn? Lần nạp lại `EXECUTE load_demo_batch_269(1)` có thêm hàng không?

**Đáp án:** Lần đầu có **4 đơn**, lần sau không thêm và không cập nhật vì revision bằng nhau; vẫn **4 đơn**.

### Bài 5 — Lô 2 tạo bao nhiêu thay đổi?

**Đáp án:** **3 khóa thay đổi**: cập nhật `WEB/ORD-1001`, cập nhật `POS/ORD-1001`, chèn `WEB/ORD-1004`. `WEB/ORD-1002` cùng revision nên giữ nguyên. Bảng đích có **5 đơn**.

### Bài 6 — Bản cũ đến muộn có được áp dụng không?

`WEB/ORD-1001` đang có revision 2, một event revision 1 đưa tổng về 115.

**Đáp án:** Không. Điều kiện `EXCLUDED.source_revision > t.source_revision` sai; không ghi đè tổng 125 ở đích.

### Bài 7 — Tại sao nên có UNIQUE và ON CONFLICT cùng lúc?

**Đáp án:** `UNIQUE` là ràng buộc bảo vệ tính đúng đắn của dữ liệu ở database, bao gồm nhiều writer đồng thời. `ON CONFLICT` xác định **cách ứng xử khi vi phạm khóa đó**, ví dụ bỏ qua hoặc cập nhật có điều kiện.

### Bài 8 — Bẫy NOT EXISTS

Hai phiên cùng kiểm tra chưa có một đơn, rồi cùng chèn. Chỉ dùng `WHERE NOT EXISTS` có chắc tránh trùng không?

**Đáp án:** Không. Cả hai có thể cùng thấy chưa tồn tại. Cần unique và thao tác ghi có xử lý xung đột.

### Bài 9 — Bản sao cùng revision nhưng payload khác

Hai hàng cùng `WEB/ORD-1001` revision 2, nhưng một hàng có tổng 125 và một hàng có tổng 135.

**Đáp án:** Đây là dữ liệu **mâu thuẫn** theo mô hình revision của bài. Không chọn dòng cuối một cách tùy tiện; cần báo/quarantine hoặc áp dụng quy tắc giải quyết xung đột được xác nhận bởi nguồn.

### Bài 10 — UNIQUE trên cột có thể NULL

Trong PostgreSQL với `UNIQUE(tenant_id, external_ref)`, nếu `external_ref` cho phép `NULL`, hai hàng `(10,NULL)` có thể cùng tồn tại không?

**Đáp án:** Có với ngữ nghĩa unique mặc định. Nếu là khóa bắt buộc, hãy khai báo `NOT NULL`; PostgreSQL 15+ có `NULLS NOT DISTINCT` cho một chính sách khác khi thật sự cần.

### Bài 11 — Xác minh số hàng đích

```sql
SELECT
    COUNT(*) AS rows_total,
    COUNT(DISTINCT (source_system, external_order_id))
        AS keys_total
FROM demo_orders_269;
```

**Đáp án:** Sau các lượt nạp mẫu, cả hai giá trị bằng **5**.

### Bài 12 — Vì sao không dùng load_date trong khóa đơn?

Một đơn được nhập ngày 1/6 và nhập lại ngày 2/6. Nếu khóa unique là `(source_system, external_order_id, load_date)`, chuyện gì xảy ra?

**Đáp án:** Hai lần nhập ở hai ngày có hai khóa khác nhau, nên database có thể lưu **hai hàng cho cùng một đơn**. `load_date` là metadata nạp, không phải thành phần định danh của đơn trong bài.

### Bài 13 — DO NOTHING hay DO UPDATE?

Đơn đã có tổng 120, nguồn gửi revision 2 với tổng 125. Nếu chạy `DO NOTHING`, đích có đạt trạng thái mới không?

**Đáp án:** Không. `DO NOTHING` giữ nguyên bản cũ; nếu nguồn cho phép cập nhật đơn, cần `DO UPDATE` có điều kiện version và kiểm soát payload.

### Bài 14 — Replay có thể làm tăng order_pk không?

Số identity/sequence có thể tăng hoặc có khoảng trống dù câu `ON CONFLICT` không tạo hàng mới hay không?

**Đáp án:** Có thể. Tiêu hao sequence không được rollback như một bộ đếm nghiệp vụ liên tục. Không lấy khoảng trống ID kỹ thuật làm thước đo lỗi trùng đơn.

### Bài 15 — Khóa cho bảng thanh toán

Một đơn `ORD-1001` có hai thanh toán riêng `PAY-1` và `PAY-2`. Có nên dùng unique chỉ theo `order_id` trong bảng thanh toán?

**Đáp án:** Không, vì một đơn được phép có nhiều thanh toán. Cần xác định ID thanh toán duy nhất, ví dụ `(payment_provider, payment_id)`, hoặc một khóa giao dịch được nguồn đảm bảo.

### Bài 16 — Tại sao replay không có nghĩa exactly once cho email?

Một event tạo đơn được nạp an toàn bằng unique, nhưng ứng dụng vẫn gửi email mỗi lần nhận event.

**Đáp án:** Bảng đơn không trùng, nhưng email vẫn có thể gửi nhiều lần. Cần chính sách idempotent riêng cho thông báo, như bảng thông điệp/outbox có khóa nghiệp vụ của hành động.

### Bài 17 — Snapshot thiếu một phần dữ liệu

Một tệp chỉ chứa 20 đơn mới nhưng pipeline xóa mọi đơn đích không có trong tệp. Vấn đề là gì?

**Đáp án:** Tệp là **delta**, không phải snapshot đầy đủ; việc coi những khóa không xuất hiện là “đã bị xóa” sẽ làm mất dữ liệu hợp lệ. Chỉ đồng bộ xóa theo snapshot khi đã xác thực phạm vi và tính đầy đủ của nó.

### Bài 18 — Câu SQL tránh cập nhật khi revision không mới hơn

Hoàn thiện mẫu PostgreSQL:

```sql
INSERT INTO demo_orders_269 AS t (
    source_system, external_order_id, customer_ref,
    order_total, order_state, source_revision, source_changed_at
)
VALUES (
    'WEB', 'ORD-1001', 'C-01', 125, 'paid',
    2, TIMESTAMPTZ '2025-06-02 07:00:00+00'
)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    order_total = EXCLUDED.order_total,
    order_state = EXCLUDED.order_state,
    source_revision = EXCLUDED.source_revision,
    source_changed_at = EXCLUDED.source_changed_at
WHERE EXCLUDED.source_revision > t.source_revision;
```

**Đáp án:** Điều kiện cuối chỉ cập nhật nếu nguồn mới hơn đích. Với `WEB/ORD-1001` đang ở revision 2, câu này không thay đổi hàng.

## 28. Quy trình áp dụng vào dự án thật

Một pipeline nạp lặp an toàn thường cần được thiết kế theo thứ tự sau.

### Bước 1: xác định grain và khóa

Viết rõ: “Một hàng bảng đích đại diện cho **đối tượng gì**?” Khóa này có gồm tenant, nguồn hay loại chứng từ không? Có trường hợp tái sử dụng hoặc đổi ID không?

### Bước 2: ràng buộc tính duy nhất ở database

Tạo `UNIQUE` hoặc `PRIMARY KEY` trên khóa nghiệp vụ thực tế, và `NOT NULL` cho thành phần bắt buộc. Kiểm tra chính sách `NULL`, collation, chuẩn hóa, xóa mềm và phân vùng.

### Bước 3: phân loại nguồn là event, delta hay snapshot

- **Event:** thường có event ID và revision.
- **Delta:** chỉ có các thay đổi.
- **Snapshot:** mô tả toàn bộ trạng thái trong phạm vi đã xác minh.

Loại nguồn quyết định xử lý bản cũ, bản bị xóa và bản không xuất hiện.

### Bước 4: staging và kiểm tra dữ liệu

Lưu dấu vết batch/row. Kiểm tra kiểu dữ liệu, khóa thiếu, khóa chuẩn hóa, trùng trong batch, cùng revision nhưng payload khác. Đưa dữ liệu không hợp lệ sang luồng xử lý lỗi thay vì âm thầm bỏ.

### Bước 5: chọn một bản hợp lệ trên mỗi khóa

Nếu đích là bảng trạng thái hiện tại, chọn revision mới nhất theo thứ tự nguồn đã xác nhận. Nếu đích là bảng sự kiện, dùng **khóa sự kiện** để giữ mọi sự kiện khác nhau thay vì chọn một trạng thái.

### Bước 6: upsert nguyên tử

Dùng cơ chế của DBMS cùng unique constraint. `DO NOTHING` nếu dữ liệu bất biến/first-write-wins; `DO UPDATE` nếu phải tiếp nhận phiên bản mới. Chặn ghi lùi revision.

### Bước 7: transaction và side effect

Nhóm các thay đổi phải nhất quán trong cùng transaction. Xác nhận message sau commit theo thiết kế hệ thống; dùng outbox hoặc cơ chế idempotency riêng khi phát sinh hành động ngoài database.

### Bước 8: đối soát và quan sát

Ghi nhận số hàng nguồn, khóa hợp lệ, bản sao, khóa chèn/cập nhật/không đổi, stale và lỗi. Đối chiếu với bảng đích theo business key, không đo bằng số identity liên tục.

### Bước 9: thử các tình huống biên

Ít nhất phải mô phỏng:

- Nạp lô lần đầu.
- Nạp lại nguyên lô.
- Trùng khóa trong cùng lô.
- Hai nguồn có cùng external ID.
- Cùng khóa nhận bản mới hơn.
- Bản cũ đến muộn.
- Cùng revision nhưng payload khác.
- Thiếu thành phần khóa.
- Hai worker cùng ghi.
- Retry sau khi commit nhưng trước khi nhận xác nhận.
- Xóa mềm hoặc tombstone và bản cũ đến sau.
- Thay đổi khóa nghiệp vụ hoặc dữ liệu theo snapshot một phần.

## 29. Tổng kết

**Khóa nghiệp vụ trả lời “đây là đối tượng nào”; ràng buộc `UNIQUE` khiến database bảo vệ câu trả lời đó; chính sách `UPSERT` quyết định phải làm gì khi đối tượng đã tồn tại.**

Nếu cần nạp lặp an toàn, đừng chỉ thêm `DISTINCT` vào dữ liệu nguồn hoặc kiểm tra `NOT EXISTS` trước khi chèn. Hãy xác định đúng grain, khóa và phạm vi duy nhất; bảo vệ bằng ràng buộc ở database; kiểm tra trùng và mâu thuẫn trong staging; dùng phiên bản nguồn để tránh dữ liệu đến muộn ghi lùi; và tách các tác dụng phụ ngoài database khỏi tính duy nhất của bảng đích.

Khi những thành phần này được thiết kế đồng bộ, việc chạy lại một lô sẽ trở thành một thao tác **có thể dự đoán và đối soát**, thay vì một nguồn tạo bản ghi trùng, mất cập nhật hoặc sai báo cáo.

