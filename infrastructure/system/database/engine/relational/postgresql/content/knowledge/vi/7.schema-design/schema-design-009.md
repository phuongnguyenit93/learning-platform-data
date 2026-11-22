# Xóa mềm, vòng đời dữ liệu và chính sách lưu giữ trong PostgreSQL

Trong ứng dụng thực tế, hành động “xóa” không phải lúc nào cũng có nghĩa loại bỏ ngay một hàng khỏi database. Một khách hàng có thể yêu cầu đóng tài khoản nhưng đơn hàng cũ vẫn cần được đối soát. Một bài đăng có thể được đưa vào thùng rác trong 30 ngày trước khi bị xóa hẳn. Một bản ghi nhân sự có thể được giữ theo chính sách nội bộ, nhưng không được xuất hiện trong danh sách nhân sự đang làm việc.

Vì vậy, khi thiết kế lược đồ PostgreSQL, cần phân biệt **xóa mềm (soft delete)**, **xóa vật lý (hard delete)**, **các trạng thái trong vòng đời dữ liệu (data lifecycle)** và **chính sách lưu giữ (retention policy)**.

- **Xóa mềm:** đánh dấu bản ghi không còn hoạt động hoặc không còn hiển thị, nhưng hàng vẫn tồn tại trong PostgreSQL.
- **Xóa vật lý:** thực thi `DELETE` để loại bỏ hàng theo semantics giao dịch và ràng buộc của PostgreSQL; dung lượng lưu trữ không nhất thiết được thu hồi ngay.
- **Lưu trữ lâu dài hoặc lưu trữ lạnh (archive):** chuyển hoặc phân loại dữ liệu ít dùng, không đồng nghĩa đã xóa dữ liệu.
- **Retention policy:** quy định loại dữ liệu nào phải được giữ, từ mốc nào, trong bao lâu, khi nào được phép xóa, ai phê duyệt và cách xác minh việc thực hiện.
- **Legal hold / preservation hold:** yêu cầu giữ lại dữ liệu thuộc phạm vi nhất định bất chấp lịch dọn thông thường, nếu có quy định hoặc quyết định hợp lệ.

PostgreSQL cung cấp SQL, transaction, constraints, index, partitioning, role và các công cụ vận hành để triển khai những quy tắc này. Tuy nhiên, **PostgreSQL không tự quyết định dữ liệu nghiệp vụ nào cần giữ trong bao lâu**. Phần chính sách phải được xác định từ yêu cầu ứng dụng, pháp lý và vận hành của tổ chức.

Bài học xây dựng một thiết kế có thể áp dụng: bảng khách hàng và đơn hàng, trường `deleted_at`, partial unique index, thao tác xóa/khôi phục an toàn, kiểm tra quan hệ khóa ngoại, thời điểm được phép dọn và công việc purge theo lô. Các khoảng thời gian như 30 hoặc 90 ngày chỉ là **ví dụ kỹ thuật**, không phải thời hạn bắt buộc cho bất kỳ ngành nghề hay quốc gia nào.

## 1. Vì sao không phải lúc nào cũng DELETE ngay?

Giả sử ứng dụng có bảng khách hàng:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL
);
~~~

Một thao tác xóa vật lý:

~~~sql
DELETE FROM customer
WHERE customer_id = 101;
~~~

Nếu lệnh được commit, bản ghi sẽ không còn trong kết quả `SELECT` thông thường. Điều này thích hợp khi dữ liệu không cần giữ và các quan hệ phụ thuộc đã được xử lý.

Nhưng có các tình huống cần cân nhắc:

1. Người dùng vô tình bấm “Xóa” và cần khôi phục trong một khoảng thời gian.
2. Tài khoản bị đóng nhưng lịch sử đơn hàng cần được giữ theo chính sách riêng.
3. Bộ phận hỗ trợ cần phân biệt “chưa từng tồn tại” và “đã bị xóa”.
4. Ứng dụng có job, cache hoặc hệ thống tìm kiếm chưa nhận được sự kiện xóa.
5. Hệ thống có khóa ngoại và không thể xóa hàng cha khi hàng con còn tham chiếu.
6. Một tác vụ xóa hàng triệu bản ghi có thể tạo tải lớn, WAL và dead tuples.
7. Dữ liệu cần được ẩn khỏi chức năng thông thường ngay, nhưng chưa được phép purge.

**Xóa mềm giải quyết một số nhu cầu về khôi phục và vòng đời**, nhưng không có nghĩa dữ liệu đã biến mất khỏi storage, backup hoặc mọi hệ thống phụ. Khi dữ liệu cần được loại bỏ thực sự theo một yêu cầu cụ thể, phải có cơ chế purge, anonymization hoặc erasure tương ứng.

## 2. So sánh xóa mềm, xóa vật lý, archive và anonymization

| Chiến lược | Thao tác | Dữ liệu còn trong bảng chính? | Khả năng khôi phục | Điều cần lưu ý |
|---|---|---|---|---|
| Soft delete | `UPDATE ... SET deleted_at` | Có | Thường dễ khi chưa purge | Truy vấn phải lọc, dữ liệu vẫn tồn tại |
| Hard delete | `DELETE FROM ...` | Không còn hàng sau commit | Thường cần backup/PITR nếu muốn lấy lại | FK, WAL, MVCC, vacuum |
| Archive | Chuyển/phân loại dữ liệu sang vùng lưu trữ khác | Tùy thiết kế | Có thể đọc lại theo quy trình | Không phải xóa; vẫn phải kiểm soát quyền |
| Anonymization | Loại bỏ hoặc biến đổi thông tin nhận dạng | Có thể còn hàng phi nhận dạng | Phụ thuộc phương pháp | Phải kiểm tra nguy cơ tái nhận dạng |
| Logical deactivation | `status = 'inactive'` | Có | Có thể đổi trạng thái | Không mặc nhiên đồng nghĩa soft delete |

Một hàng có `status = 'cancelled'` chưa chắc nên được soft delete. Ví dụ đơn hàng bị hủy vẫn là một sự kiện nghiệp vụ có ý nghĩa với báo cáo tỷ lệ hủy.

Ngược lại, tài khoản có `deleted_at IS NOT NULL` thường phải biến mất khỏi danh sách tài khoản đang hoạt động, bất kể trạng thái trước khi xóa là gì.

## 3. Phân biệt trạng thái nghiệp vụ và trạng thái tồn tại

Một sai lầm thiết kế là gộp mọi ý nghĩa vào một cột `status`:

~~~text
active
inactive
deleted
archived
blocked
pending
~~~

Danh sách trên trộn nhiều chiều khác nhau:

- `active` / `blocked`: trạng thái sử dụng tài khoản.
- `deleted`: bản ghi bị loại khỏi tập nhìn thấy thông thường.
- `archived`: dữ liệu được chuyển sang mức lưu trữ khác.
- `pending`: có thể chỉ là trạng thái của một quy trình nghiệp vụ.

Thường nên tách ít nhất hai chiều:

~~~text
account_status : active | suspended
deleted_at     : NULL hoặc mốc xóa mềm
~~~

Nếu hệ thống phức tạp, có thể cần state machine cho vòng đời, nhưng phải mô tả rõ các trạng thái không mâu thuẫn.

Ví dụ:

~~~text
Đăng ký
   |
   v
ACTIVE -------> SUSPENDED
   |                 |
   |                 +-------> ACTIVE
   |
   +-------> SOFT_DELETED
                     |
                     +-------> RESTORED (theo chính sách)
                     |
                     +-------> PURGE_ELIGIBLE
                                  |
                                  v
                             HARD_DELETED
~~~

Ở đây `SOFT_DELETED` có thể được biểu diễn bởi `deleted_at IS NOT NULL` chứ không cần thêm vào enum `account_status`. `PURGE_ELIGIBLE` là **điều kiện tại một thời điểm**, không nhất thiết là giá trị cột được ghi vĩnh viễn.

## 4. Những trường thường dùng cho xóa mềm

Thiết kế tối giản:

~~~sql
CREATE TABLE demo_document (
    document_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
~~~

Diễn giải:

- `deleted_at IS NULL`: tài liệu chưa được đánh dấu xóa mềm.
- `deleted_at IS NOT NULL`: tài liệu đã được đánh dấu xóa mềm.
- `deleted_at` cho biết **khi nào** xảy ra sự kiện, có thể hỗ trợ truy vấn retention và audit.

Những trường mở rộng thường hữu ích:

| Trường | Mục đích | Ghi chú |
|---|---|---|
| `deleted_at TIMESTAMPTZ` | Thời điểm xóa mềm | Nên dùng mốc thời gian có timezone semantics rõ ràng |
| `deleted_by` | Người/hệ thống yêu cầu xóa | Có thể là ID hoặc định danh actor phù hợp |
| `deletion_reason` | Lý do xóa theo mã/diễn giải | Cân nhắc không lưu thông tin nhạy cảm không cần thiết |
| `retention_until TIMESTAMPTZ` | Mốc chưa được purge trước đó | Không tự diễn đạt toàn bộ chính sách |
| `legal_hold BOOLEAN` | Chặn purge theo quyết định giữ dữ liệu | Thực tế có thể cần bảng hold riêng |
| `created_at` | Thời điểm tạo | Khác mốc bắt đầu retention của từng loại dữ liệu |
| `updated_at` | Thời điểm sửa gần nhất | PostgreSQL không tự cập nhật nếu chưa viết logic |
| `account_status` | Trạng thái nghiệp vụ | Không nên dùng thay duy nhất cho deleted_at |

**Không có bộ cột bắt buộc cho mọi ứng dụng.** Bảng nhỏ có thể chỉ cần `deleted_at`; hệ thống có nhiều chính sách cần metadata và lịch sử quyết định riêng.

## 5. Ví dụ schema PostgreSQL tự chứa

Ta tạo một schema học tập với hai bảng khách hàng và đơn hàng. Dữ liệu giả được sử dụng để tránh phụ thuộc thông tin thật.

**Chỉ chạy trong database thực hành riêng.** Đoạn dưới tạo schema và bảng mới; nếu đã có những đối tượng cùng tên, cần dùng database test mới hoặc quy trình migration, không xóa nhầm dữ liệu đang dùng.

~~~sql
CREATE SCHEMA lifecycle_lab;

CREATE TABLE lifecycle_lab.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    account_status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    deleted_at TIMESTAMPTZ,
    deleted_by TEXT,
    deletion_reason TEXT,
    retention_until TIMESTAMPTZ,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_customer_status
        CHECK (account_status IN ('active', 'suspended')),

    CONSTRAINT chk_customer_delete_metadata
        CHECK (
            (
                deleted_at IS NULL
                AND deleted_by IS NULL
                AND deletion_reason IS NULL
                AND retention_until IS NULL
            )
            OR (
                deleted_at IS NOT NULL
                AND retention_until IS NOT NULL
                AND retention_until >= deleted_at
            )
        )
);

CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;

CREATE INDEX ix_customer_purge_candidate
ON lifecycle_lab.customer (retention_until, customer_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;

CREATE TABLE lifecycle_lab.customer_order (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lifecycle_lab.customer(customer_id),
    order_status TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    deleted_at TIMESTAMPTZ,
    retention_until TIMESTAMPTZ,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_order_status
        CHECK (
            order_status IN (
                'draft', 'confirmed', 'fulfilled', 'cancelled'
            )
        ),

    CONSTRAINT chk_order_amount
        CHECK (total_amount >= 0),

    CONSTRAINT chk_order_delete_metadata
        CHECK (
            (deleted_at IS NULL AND retention_until IS NULL)
            OR (
                deleted_at IS NOT NULL
                AND retention_until IS NOT NULL
                AND retention_until >= deleted_at
            )
        )
);

CREATE INDEX ix_order_live_by_customer
ON lifecycle_lab.customer_order (customer_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX ix_order_purge_candidate
ON lifecycle_lab.customer_order (retention_until, order_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;
~~~

Thiết kế minh họa một số quyết định có chủ đích:

- Bảng khách hàng và đơn có **primary key ổn định**; xóa mềm không đổi ID.
- Chỉ khách hàng chưa xóa mới tham gia **unique index trên email không phân biệt hoa/thường theo hàm `lower`**.
- Đơn hàng liên kết khách hàng bằng foreign key; xóa mềm khách hàng **không làm foreign key bị mất**.
- `retention_until` nằm ở cả hai bảng để biểu diễn mốc giữ dữ liệu riêng; thực tế có thể cần chính sách khác hẳn nhau.
- `legal_hold` phục vụ minh họa việc tạm chặn xóa vật lý.
- Index một phần cho những câu truy vấn hoạt động thường xuyên.
- `updated_at` là cột dữ liệu do ứng dụng/câu lệnh cập nhật; DDL hiện tại **không có trigger tự đặt lại** mỗi lần sửa.

### 5.1. Vì sao không dùng UNIQUE(email) toàn bảng?

Nếu khai báo:

~~~sql
-- Cách này giữ email duy nhất trên toàn bộ lịch sử bản ghi:
-- UNIQUE (email)
~~~

thì sau khi xóa mềm một khách hàng, một khách hàng mới vẫn không thể dùng cùng email, dù chính sách ứng dụng cho phép tái sử dụng.

Partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;
~~~

chỉ bảo đảm **không có hai hàng chưa xóa mềm** cùng giá trị `lower(email)` theo quy tắc so sánh tương ứng. Email của các hàng đã xóa mềm không tham gia index này.

Lựa chọn có cho phép tái sử dụng email không là **quy tắc nghiệp vụ**, không phải mặc định “đúng” của soft delete. Nếu email phải duy nhất trên toàn bộ lịch sử, thiết kế unique khác hoặc một registry riêng có thể phù hợp hơn.

### 5.2. Vì sao dùng TIMESTAMPTZ?

`TIMESTAMPTZ` biểu diễn thời điểm theo semantics timezone của PostgreSQL. Dùng để tính mốc retention, đối chiếu log và làm việc với hệ thống nhiều múi giờ.

Ví dụ:

~~~sql
SELECT
    now() AS current_transaction_time,
    statement_timestamp() AS current_statement_time,
    clock_timestamp() AS current_wall_clock_time;
~~~

Các hàm thời gian khác nhau:

- `now()` tương đương thời điểm bắt đầu transaction hiện tại.
- `statement_timestamp()` gắn với thời điểm bắt đầu statement.
- `clock_timestamp()` trả thời gian thực tại lúc gọi, có thể thay đổi ngay trong một statement.

Khi ghi cùng một sự kiện xóa, nên chọn và sử dụng **một mốc nhất quán** thay vì để nhiều trường có timestamp khác nhau không cần thiết.

## 6. Nạp dữ liệu thực hành có giá trị cố định

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status, created_at)
VALUES
    (
        101, 'an@example.test', 'Nguyễn An', 'active',
        TIMESTAMPTZ '2026-01-05 08:00:00+00'
    ),
    (
        102, 'binh@example.test', 'Trần Bình', 'active',
        TIMESTAMPTZ '2026-01-06 08:00:00+00'
    ),
    (
        103, 'chi@example.test', 'Lê Chi', 'suspended',
        TIMESTAMPTZ '2026-01-07 08:00:00+00'
    );

INSERT INTO lifecycle_lab.customer_order
    (order_id, customer_id, order_status, total_amount, created_at)
VALUES
    (
        1001, 101, 'confirmed', 250000.00,
        TIMESTAMPTZ '2026-01-10 10:00:00+00'
    ),
    (
        1002, 101, 'draft', 150000.00,
        TIMESTAMPTZ '2026-01-11 11:00:00+00'
    ),
    (
        1003, 102, 'fulfilled', 600000.00,
        TIMESTAMPTZ '2026-01-12 12:00:00+00'
    ),
    (
        1004, 103, 'cancelled', 90000.00,
        TIMESTAMPTZ '2026-01-13 13:00:00+00'
    );
~~~

Ở thời điểm mới nạp:

- Có 3 khách hàng.
- Có 4 đơn hàng.
- Chưa có hàng nào bị soft delete.
- Email không trùng trong tập khách hàng còn hoạt động.
- Một khách hàng có thể có nhiều đơn.

Dữ liệu dùng địa chỉ `example.test` để tránh nhầm với tài khoản thật. Không đưa dữ liệu cá nhân hoặc token production vào bài thực hành.

## 7. Xóa mềm một khách hàng bằng UPDATE

Để xóa mềm khách hàng 102:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    deleted_by = 'operator:training',
    deletion_reason = 'user_requested',
    retention_until = statement_timestamp() + INTERVAL '90 days',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NULL
RETURNING
    customer_id,
    email,
    deleted_at,
    retention_until;
~~~

Giải thích:

- Không dùng `DELETE`; hàng vẫn tồn tại.
- `deleted_at` ghi mốc xóa mềm.
- `deleted_by` và `deletion_reason` ghi thông tin phục vụ truy vết ở mức cơ bản.
- `retention_until` biểu diễn thời điểm sớm nhất **có thể xét purge**, không tự ra quyết định xóa.
- Điều kiện `AND deleted_at IS NULL` giúp thao tác không ghi đè mốc xóa mềm khi bị gọi lặp.
- `RETURNING` cho biết hàng nào thực sự được cập nhật.

Nếu gọi cùng lệnh lần nữa, điều kiện `deleted_at IS NULL` không còn đúng và `RETURNING` trả **0 hàng**. Điều đó khác với việc một lệnh đã được thi hành thành công trong lần đầu.

### 7.1. Vì sao phải cẩn thận khi thực hiện lặp?

Nếu viết:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = now(),
    retention_until = now() + INTERVAL '90 days'
WHERE customer_id = 102;
~~~

mỗi lần hệ thống gửi lại request có thể **đẩy thời hạn purge ra xa thêm**. Nếu bị retry nhiều lần, dữ liệu có thể được giữ lâu hơn chính sách mong muốn.

Vì vậy nên xác định tính **idempotent** của hành động xóa mềm: lặp request không làm thay đổi mốc đã xác nhận, trừ khi nghiệp vụ chủ động gia hạn retention.

### 7.2. Không nên dùng boolean đơn lẻ khi cần audit

Một cột `is_deleted BOOLEAN` giúp lọc:

~~~sql
-- Một thiết kế tối giản nhưng thiếu mốc thời gian:
-- is_deleted BOOLEAN NOT NULL DEFAULT FALSE
~~~

Nhưng khi cần trả lời “xóa từ lúc nào”, “khi nào purge” hoặc “đã giữ quá thời hạn chưa”, cột boolean không đủ thông tin.

Nếu chỉ cần trạng thái hiển thị và không có yêu cầu thời gian, boolean có thể chấp nhận. Nếu dùng cả `is_deleted` và `deleted_at`, nên có constraint/logic bảo đảm chúng không mâu thuẫn, hoặc chọn một nguồn sự thật duy nhất.

## 8. Truy vấn mặc định phải bỏ qua hàng đã xóa mềm

Truy vấn chưa lọc:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
ORDER BY customer_id;
~~~

vẫn trả cả khách hàng 102. Đó là hành vi chính xác của SQL: soft delete chỉ là giá trị cột, PostgreSQL không tự ẩn hàng.

Truy vấn chỉ lấy khách còn hoạt động:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
ORDER BY customer_id;
~~~

Kết quả kỳ vọng sau bước xóa khách 102:

| customer_id | email | full_name |
|---:|---|---|
| 101 | an@example.test | Nguyễn An |
| 103 | chi@example.test | Lê Chi |

Nếu nghiệp vụ còn yêu cầu tài khoản không bị đình chỉ:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND account_status = 'active'
ORDER BY customer_id;
~~~

Khi đó chỉ khách 101 thỏa cả hai điều kiện.

**Quy tắc quan trọng:** “Chưa soft delete” và “được phép sử dụng tài khoản” là hai phép kiểm tra khác nhau. Một bản ghi có `deleted_at IS NULL` nhưng `account_status = 'suspended'` vẫn không phải tài khoản được phép thực hiện mọi thao tác.

## 9. Thiết kế VIEW cho danh sách dữ liệu còn hiệu lực

Để giảm số lần viết điều kiện lọc, có thể tạo view:

~~~sql
CREATE VIEW lifecycle_lab.active_customer AS
SELECT
    customer_id,
    email,
    full_name,
    account_status,
    created_at,
    updated_at
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL;
~~~

Sử dụng:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.active_customer
ORDER BY customer_id;
~~~

View giúp tập trung **định nghĩa tập bản ghi còn hiệu lực** tại một nơi. Tuy nhiên:

- View thông thường **không lưu một bản copy riêng** của dữ liệu.
- View không tự ngăn người có quyền trên bảng gốc truy vấn các hàng đã xóa.
- View không biến soft delete thành tính năng tự động áp dụng cho mọi SQL.
- DML qua view có thể có những điều kiện, giới hạn và semantics riêng.

Nếu muốn ứng dụng chỉ đọc qua view, phải thiết kế **GRANT/REVOKE và role** tương ứng. Quy tắc lọc dùng cho giao diện không đủ thay thế cơ chế bảo mật.

### 9.1. Truy vấn JOIN cần định nghĩa rõ trạng thái ở cả hai bảng

Ví dụ hiển thị đơn còn hiệu lực của khách chưa bị xóa:

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.order_status,
    o.total_amount
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.deleted_at IS NULL
  AND c.deleted_at IS NULL
ORDER BY o.order_id;
~~~

Nếu quên `c.deleted_at IS NULL`, một đơn vẫn có thể xuất hiện cùng dữ liệu của khách đã xóa. Nếu chỉ lọc khách mà quên đơn, những đơn đã bị soft delete vẫn có thể xuất hiện.

Nhưng có những chức năng như đối soát, hỗ trợ khách hàng hoặc báo cáo theo chính sách có thể **cần** nhìn thấy đơn của khách đã xóa mềm. Do đó điều kiện lọc phải đi theo **mục đích truy vấn**, không thêm máy móc vào mọi báo cáo.

## 10. Partial index: tối ưu truy vấn chỉ lấy dữ liệu còn hiệu lực

PostgreSQL hỗ trợ **partial index** — chỉ lập chỉ mục cho hàng thỏa một predicate.

Ví dụ đã tạo:

~~~sql
CREATE INDEX ix_order_live_by_customer
ON lifecycle_lab.customer_order (customer_id, created_at DESC)
WHERE deleted_at IS NULL;
~~~

Truy vấn phù hợp:

~~~sql
SELECT order_id, created_at, total_amount
FROM lifecycle_lab.customer_order
WHERE customer_id = 101
  AND deleted_at IS NULL
ORDER BY created_at DESC;
~~~

Index có thể giúp truy vấn chỉ đọc các đơn chưa xóa, nhất là khi tổng số hàng đã soft delete lớn.

Lưu ý:

- Planner chỉ sử dụng index khi thấy có lợi.
- Tập dữ liệu ví dụ nhỏ có thể dẫn đến sequential scan thay vì index scan; đây không tự là lỗi.
- Predicate của truy vấn phải phù hợp để planner chứng minh phần dữ liệu cần đọc nằm trong partial index.
- Một câu truy vấn tham số hóa viết predicate quá chung chung có thể khiến planner không nhận diện điều kiện partial index trong một số trường hợp, đặc biệt với generic plan.
- Partial index không làm mất dữ liệu đã xóa mềm trong heap/table; chỉ giới hạn thành viên của index.

Có thể xem kế hoạch:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM lifecycle_lab.customer_order
WHERE customer_id = 101
  AND deleted_at IS NULL
ORDER BY created_at DESC;
~~~

Không đánh giá lợi ích index chỉ bằng bảng có bốn dòng. Với production cần đo workload, phân bố dữ liệu và chi phí cập nhật index.

## 11. Partial UNIQUE index: cho phép tái sử dụng email sau soft delete

Bài toán: email chỉ cần duy nhất giữa **các khách hàng còn hiệu lực**.

Đã có index:

~~~sql
CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;
~~~

Khi khách 102 bị xóa mềm, có thể thử thêm một khách mới dùng email cũ:

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (104, 'BINH@example.test', 'Khách mới', 'active');
~~~

Trong môi trường demo, insert này có thể thành công vì hàng 102 đã xóa mềm không còn tham gia partial unique index và `lower('BINH@example.test')` có giá trị tương ứng với email cũ theo quy tắc `lower`.

Sau đó nếu cố tạo **một khách chưa xóa khác** dùng email tương đương:

~~~sql
-- Dự kiến lỗi unique violation khi index được áp dụng:
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (105, 'binh@example.test', 'Khách trùng email', 'active');
~~~

PostgreSQL sẽ từ chối vì hai khách chưa xóa không được phép có giá trị `lower(email)` trùng trong index.

### 11.1. Hệ quả khi khôi phục một hàng cũ

Nếu khách 104 đang dùng email `binh@example.test`, thao tác khôi phục khách 102 về trạng thái `deleted_at IS NULL` sẽ làm hai hàng cùng tham gia unique index. Vì vậy restore có thể **thất bại do unique violation**.

Đây không phải lỗi của PostgreSQL mà là **xung đột chính sách sử dụng lại định danh**. Cần có một trong những chiến lược nghiệp vụ:

- Không cho tái sử dụng email trong khoảng thời gian có thể restore.
- Cho tái sử dụng nhưng restore phải yêu cầu email mới.
- Dùng định danh đăng nhập riêng với email liên hệ.
- Kiểm tra và giải quyết xung đột trước khi restore.
- Chỉ cho restore trong một thời hạn nhất định có chính sách rõ ràng.

Không tự động đổi email hoặc ghi đè tài khoản mới chỉ để làm cho lệnh restore chạy qua.

### 11.2. Collation và case-insensitive không tuyệt đối đơn giản

`lower(email)` phụ thuộc ngữ nghĩa ký tự/collation của PostgreSQL. Quy tắc xác định email tương đương nên được thiết kế đúng theo chính sách ứng dụng, đặc biệt với Unicode, địa chỉ quốc tế hóa và chuẩn hóa chuỗi.

Nếu dùng `citext` hoặc nondeterministic collation, phải hiểu tính năng, quyền cài extension, độ tương thích và tác động tới index. Không mặc định `lower` giải quyết mọi quy tắc email toàn cầu.

## 12. ON CONFLICT khi có partial unique index

Khi dữ liệu live chỉ unique theo một **partial unique index**, câu `INSERT ... ON CONFLICT` phải xác định đúng conflict target để PostgreSQL có thể suy ra index phù hợp.

Một ví dụ:

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (106, 'an@example.test', 'Tên thử nghiệm', 'active')
ON CONFLICT (lower(email)) WHERE deleted_at IS NULL
DO NOTHING;
~~~

Với dữ liệu đã nạp, email `an@example.test` đang thuộc khách 101 chưa xóa, nên câu lệnh không thêm hàng 106.

**Chú ý:** partial unique index là index, không phải một `UNIQUE CONSTRAINT` toàn bảng thông thường. Không nên mặc định viết `ON CONFLICT ON CONSTRAINT uq_customer_live_email` vì `uq_customer_live_email` được tạo bằng `CREATE UNIQUE INDEX`, không phải tên một constraint có thể suy ra theo cách đó.

Nếu `DO UPDATE` được sử dụng, việc update vào hàng nào và có được phép thay dữ liệu khách hàng hiện hữu hay không phải là quyết định nghiệp vụ, không nên coi UPSERT là thao tác vô hại.

## 13. Soft delete không tự xử lý khóa ngoại

Giả sử đơn 1003 thuộc khách hàng 102. Sau khi khách 102 được soft delete:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.deleted_at AS customer_deleted_at
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 1003;
~~~

Đơn vẫn tham chiếu khách bằng foreign key hợp lệ vì hàng khách **vẫn tồn tại**. PostgreSQL không coi `deleted_at IS NOT NULL` là lý do xóa liên kết.

So sánh:

- **Soft delete:** `UPDATE customer SET deleted_at = ...`, không kích hoạt `ON DELETE` của foreign key.
- **Hard delete:** `DELETE FROM customer ...`, PostgreSQL áp dụng hành vi foreign key đã khai báo.

Nếu muốn xóa mềm đồng bộ nhiều loại đối tượng, phải viết **logic nghiệp vụ** (trong ứng dụng, transaction hoặc trigger được thiết kế rõ) thay vì kỳ vọng `ON DELETE CASCADE` tự chạy khi chỉ cập nhật timestamp.

### 13.1. Có nên soft delete toàn bộ đơn khi khách bị xóa?

Không có đáp án chung.

Ví dụ:

- Đơn hàng nháp có thể được xóa mềm cùng tài khoản.
- Đơn đã thanh toán có thể cần giữ để đối soát.
- Đơn đã hoàn tất có thể cần loại bỏ thông tin cá nhân nhưng giữ số liệu giao dịch.
- Đơn thuộc yêu cầu giữ dữ liệu có thể không được purge theo lịch bình thường.

Nếu ứng dụng chỉ dùng `ON DELETE CASCADE` vật lý hoặc update cascade máy móc, có thể vi phạm những chính sách giữ dữ liệu khác nhau.

**Nguyên tắc:** xác định vòng đời cho từng loại đối tượng, sau đó mô tả quan hệ giữa các vòng đời.

## 14. Thiết kế retention khác nhau cho khách hàng và đơn hàng

Một bảng ví dụ về chính sách:

| Loại dữ liệu | Khi nào bắt đầu tính hạn | Thời hạn minh họa | Hành động khi hết hạn |
|---|---|---|---|
| Tài khoản đã xóa mềm | `deleted_at` | 90 ngày | Xét purge hoặc anonymize |
| Đơn hàng nháp bị hủy | Thời điểm hủy | 30 ngày | Xét xóa nếu không có phụ thuộc |
| Đơn đã hoàn tất | Mốc nghiệp vụ xác định | Theo chính sách lưu giữ giao dịch | Archive/anonymize/purge theo quy định |
| Log thao tác vận hành | Thời điểm log | 30 ngày | Xóa/rotate theo phân loại |
| Dữ liệu đang legal hold | Mốc và phạm vi hold | Đến khi hold được gỡ hợp lệ | Không purge trong phạm vi hold |

Các con số chỉ để minh họa thiết kế. Không được suy rằng tất cả đơn hàng, dữ liệu tài chính hoặc thông tin cá nhân đều hợp pháp hoặc bắt buộc giữ theo những mốc này. **Thời hạn thật cần được tổ chức phê duyệt theo yêu cầu cụ thể.**

### 14.1. Vì sao một cột retention_until chưa đủ cho mọi chính sách?

Một mốc thời gian đơn lẻ không trả lời hết:

- Vì sao giữ dữ liệu tới ngày đó?
- Chính sách nào đang được áp dụng?
- Ai phê duyệt hoặc thay đổi thời hạn?
- Có yêu cầu giữ dữ liệu riêng không?
- Khi xóa thì xóa bản ghi, archive hay anonymize?
- Các bản sao, backup, file đính kèm và hệ thống phân tích có cùng hạn không?

Với hệ thống lớn, có thể cần bảng `retention_policy` và bảng `retention_hold` riêng, cùng nhật ký quyết định.

## 15. Mô hình chính sách lưu giữ có version

Một hướng thiết kế cho hệ thống nhiều loại dữ liệu:

~~~sql
CREATE TABLE lifecycle_lab.retention_policy (
    policy_id BIGINT PRIMARY KEY,
    policy_code TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    data_category TEXT NOT NULL,
    duration_days INTEGER NOT NULL,
    retention_event TEXT NOT NULL,
    purge_action TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_policy_version
        UNIQUE (policy_code, policy_version),
    CONSTRAINT chk_duration
        CHECK (duration_days >= 0),
    CONSTRAINT chk_purge_action
        CHECK (purge_action IN ('delete', 'anonymize', 'archive_review'))
);
~~~

Bảng này chỉ minh họa **metadata của chính sách**. Nó không tự thực thi xóa hoặc kiểm soát pháp lý; ứng dụng/job phải áp dụng quy tắc và kiểm tra điều kiện.

Trong thực tế có thể cần thêm:

- Hiệu lực từ/đến của policy.
- Phạm vi tenant/vùng địa lý/loại hợp đồng.
- Đối tượng được giữ ngoài PostgreSQL.
- Căn cứ quyết định và người phê duyệt.
- Định nghĩa chính xác “ngày” hoặc tháng theo quy tắc lịch.
- Cách áp dụng policy khi có phiên bản mới.
- Trạng thái tạm dừng hoặc ưu tiên của các loại hold.

### 15.1. Vì sao cần lưu policy version?

Giả sử tháng trước khách hàng thuộc chính sách giữ 90 ngày, hôm nay tổ chức đổi thành 30 ngày. Nếu chỉ lưu số `retention_until` mà không có metadata, sẽ khó giải thích vì sao một bản ghi được giữ đến ngày nhất định.

Có thể lưu thêm `retention_policy_id` hoặc `policy_version` trên bản ghi/tác vụ xóa, nếu cần truy vết. Nhưng cũng phải cân nhắc cập nhật chính sách hồi tố có được phép hay không; đây là quyết định nghiệp vụ, không phải PostgreSQL tự xử lý.

## 16. Legal hold: chặn purge theo phạm vi được phê duyệt

Bảng mẫu có:

~~~sql
legal_hold BOOLEAN NOT NULL DEFAULT FALSE
~~~

Một worker purge phải kiểm tra `legal_hold = FALSE` trước khi xóa. Nhưng boolean đơn lẻ có hạn chế:

- Không ghi lý do và người quyết định hold.
- Không ghi thời điểm bắt đầu và kết thúc.
- Không biểu diễn nhiều yêu cầu hold độc lập.
- Không có nhật ký ai từng bật/tắt.
- Không thể hiện hold áp dụng cho tập hồ sơ liên quan ở bảng khác.

Một mô hình có thể gồm:

~~~sql
CREATE TABLE lifecycle_lab.retention_hold (
    hold_id BIGINT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    hold_reason TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ,
    CONSTRAINT chk_hold_times
        CHECK (
            released_at IS NULL
            OR released_at >= applied_at
        )
);
~~~

Ví dụ này là **mô hình mô tả chung**, không tự tạo khóa ngoại đa hình từ `entity_type + entity_id`. Nếu cần toàn vẹn tham chiếu chặt, thiết kế các bảng hold chuyên biệt hoặc một entity registry có khóa ngoại rõ ràng.

**Cảnh báo thiết kế:** nếu có nhiều hold, chỉ được purge khi **không còn hold đang hiệu lực** theo chính sách áp dụng. Không đủ để một hệ thống tự đặt một cờ false mà bỏ qua bảng quyết định khác.

### 16.1. Cần giải quyết race condition với hold

Giả sử purge worker kiểm tra “chưa có hold”, đồng thời nhân viên pháp chế vừa thêm hold. Nếu hai thao tác không được điều phối đúng, dữ liệu có thể bị xóa trong khi quyết định giữ dữ liệu đang được ghi nhận.

Trong hệ thống quan trọng, cần một cơ chế nhất quán như:

- Lock bản ghi điều phối tại thời điểm quyết định.
- Cập nhật hold và purge qua transaction cùng mô hình khóa.
- Quy định thứ tự nghiệp vụ khi có yêu cầu giữ và yêu cầu xóa cùng lúc.
- Audit những quyết định và kiểm soát quyền thao tác.

Không chỉ đặt `NOT EXISTS (hold)` trong một câu SQL rồi mặc định mọi cạnh tranh đồng thời đã được giải quyết.

## 17. Soft delete và trạng thái khôi phục

Việc khôi phục có thể được mô hình hóa bằng:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
RETURNING customer_id, email, account_status;
~~~

Trong ví dụ, đặt `account_status = 'suspended'` để bắt buộc quy trình duyệt trước khi cho hoạt động lại. Ứng dụng khác có thể có chính sách khôi phục trạng thái trước khi xóa; khi đó cần lưu trạng thái cũ có kiểm soát.

**Nếu đã thêm khách 104 với email của khách 102 ở phần trước, lệnh restore này có thể lỗi unique violation.** Điều đó minh họa lý do quy trình khôi phục phải xem xét xung đột định danh.

### 17.1. Không khôi phục vô thời hạn chỉ vì hàng còn tồn tại

Một hàng đã quá `retention_until` nhưng job purge chưa chạy có thể vẫn nằm trong database. Điều đó **không tự có nghĩa nghiệp vụ cho phép restore**.

Quyền restore nên dựa trên:

- Chính sách hiện hành.
- Vai trò và thẩm quyền của người yêu cầu.
- Khoảng thời gian cho phép khôi phục.
- Tình trạng xung đột khóa và dữ liệu phụ thuộc.
- Có dữ liệu liên quan đã bị anonymize/purge hay chưa.

Một điều kiện minh họa:

~~~sql
-- Chỉ minh họa khi chính sách cho phép restore
-- trước retention_until.
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
  AND retention_until > statement_timestamp()
RETURNING customer_id;
~~~

Không đặt điều kiện thời gian bằng bản năng; quy trình phải được nghiệp vụ quyết định.

## 18. Giao dịch và tính nhất quán khi xóa một nhóm dữ liệu

Một yêu cầu “đóng tài khoản” có thể liên quan:

- Tài khoản chính.
- Session đăng nhập còn hoạt động.
- API token.
- Hồ sơ hiển thị công khai.
- Đơn hàng nháp.
- Thiết lập thông báo.
- Dữ liệu tìm kiếm hoặc cache.
- Hệ thống gửi email ngoài database.

Nếu toàn bộ các bảng liên quan đều trong **cùng PostgreSQL database**, những cập nhật thích hợp có thể được nhóm trong một transaction:

~~~sql
BEGIN;

-- Ví dụ minh họa: vô hiệu các đơn nháp của khách 101.
UPDATE lifecycle_lab.customer_order
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '30 days'
WHERE customer_id = 101
  AND order_status = 'draft'
  AND deleted_at IS NULL;

-- Xóa mềm hồ sơ khách, giữ mốc và lý do.
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    deleted_by = 'operator:training',
    deletion_reason = 'account_closed',
    retention_until = statement_timestamp() + INTERVAL '90 days',
    updated_at = statement_timestamp()
WHERE customer_id = 101
  AND deleted_at IS NULL;

COMMIT;
~~~

Khi một phần thất bại trước commit, có thể rollback để tránh trạng thái chỉ một nửa dữ liệu được cập nhật.

**Đây là mô hình đơn giản cho môi trường thử.** Không được suy rằng mọi đơn nháp thật đều được xóa theo chính sách 30 ngày hoặc mọi đơn cần biến mất khi khách đóng tài khoản.

### 18.1. Những tác động ngoài PostgreSQL không tự rollback cùng transaction

Ví dụ: trong cùng quá trình đóng tài khoản, hệ thống gọi dịch vụ tìm kiếm để xóa document hoặc gửi email. Nếu transaction PostgreSQL rollback, thao tác đã gửi ra dịch vụ khác có thể không rollback theo.

Một kiến trúc đáng cân nhắc là **transactional outbox**:

1. Cập nhật trạng thái soft delete trong PostgreSQL.
2. Ghi một sự kiện outbox cùng transaction.
3. Commit.
4. Worker đọc outbox và cập nhật search index, cache, notification.
5. Worker xử lý retry/idempotency theo định danh sự kiện.

Điều này giúp tránh trạng thái “database rollback nhưng bên ngoài đã nhận thông báo xóa” hoặc “database commit nhưng sự kiện bị mất giữa chừng”.

## 19. Xóa mềm, thao tác cạnh tranh và idempotency

Giả sử hai request cùng xóa một khách hàng.

Lệnh:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '90 days'
WHERE customer_id = 103
  AND deleted_at IS NULL
RETURNING customer_id, deleted_at;
~~~

PostgreSQL sử dụng cơ chế MVCC/row locking cho `UPDATE`. Một request thực hiện được cập nhật trước; request khác sẽ đánh giá điều kiện khi có thể và thường không cập nhật lại hàng đã xóa mềm.

Điều này giúp tránh ghi đè timestamp nhưng **không giải quyết mọi vấn đề concurrency**:

- Hai thao tác “khôi phục” và “purge” có thể tranh chấp.
- Một request đổi email trong khi request khác soft delete.
- Một job tạo đơn mới trong khi khách bị đóng tài khoản.
- Một legal hold được thêm trong lúc purge kiểm tra điều kiện.
- Hai bản ghi có thể va chạm partial unique index khi restore.

Cần thêm transaction, lock, constraint và quy tắc nghiệp vụ rõ ràng. Với action quan trọng, **không dựa vào việc client chỉ gửi request một lần**; retry là tình huống bình thường.

## 20. Hard delete: diễn ra điều gì trong PostgreSQL?

Câu lệnh:

~~~sql
DELETE FROM lifecycle_lab.customer_order
WHERE order_id = 1002;
~~~

khác `UPDATE deleted_at` ở chỗ hàng bị xóa theo logic của SQL transaction.

Tuy nhiên PostgreSQL dùng **MVCC**:

- Phiên bản tuple cũ có thể còn tồn tại vật lý cho đến khi không transaction nào cần nhìn thấy nó.
- `VACUUM` dọn dead tuples và giúp tái sử dụng không gian theo quy tắc lưu trữ.
- File heap/index không nhất thiết giảm kích thước trên đĩa ngay sau `DELETE`.
- WAL có thể chứa thông tin phục vụ recovery/replication.
- Replica, backup và archive WAL có vòng đời lưu giữ riêng.

Do đó không nên nói rằng “DELETE xong thì mọi byte dữ liệu biến mất lập tức khỏi tất cả các bản sao”.

**Hard delete ở bảng live** và **xóa dữ liệu khỏi backup, log, cache, object storage** là những vấn đề khác nhau. Chính sách data erasure toàn hệ thống cần xét đầy đủ các lớp đó.

### 20.1. VACUUM không phải lệnh xóa mềm

`VACUUM` xử lý các tuple không còn cần theo MVCC và hỗ trợ bảo trì PostgreSQL. Nó **không tự nhận biết `deleted_at`** là dữ liệu cần xóa.

~~~sql
-- Không làm mất những hàng chỉ được đánh dấu deleted_at.
VACUUM lifecycle_lab.customer;
~~~

Hàng soft deleted vẫn là hàng đang tồn tại trong table, nên VACUUM không thể “purge” nó chỉ vì có timestamp.

## 21. Thời điểm nào một hàng đủ điều kiện purge?

Một quy tắc cơ bản:

~~~text
Đã soft delete?
      |
      +-- Không --> Không purge theo pipeline này
      |
      v
Đã đến retention_until?
      |
      +-- Không --> Tiếp tục lưu
      |
      v
Có legal hold / phụ thuộc cần giữ?
      |
      +-- Có --> Hoãn, báo lý do
      |
      v
Đã qua các kiểm tra nghiệp vụ và phụ thuộc?
      |
      +-- Không --> Hoãn, xử lý
      |
      v
Đủ điều kiện chạy hard delete có kiểm soát
~~~

Trong SQL tối giản:

~~~sql
SELECT
    customer_id,
    email,
    retention_until
FROM lifecycle_lab.customer
WHERE deleted_at IS NOT NULL
  AND retention_until <= statement_timestamp()
  AND legal_hold = FALSE
ORDER BY retention_until, customer_id;
~~~

**Đây chỉ là danh sách ứng viên.** Nó chưa kiểm tra có đơn hàng nào cần giữ, có hold ở bảng riêng hay không hoặc có job khác vừa thay đổi chính sách.

Không nên đưa toàn bộ logic pháp lý/nghiệp vụ vào một điều kiện SQL ngắn rồi khẳng định xóa sẽ luôn hợp lệ.

## 22. Purge theo lô để giới hạn tải

Một truy vấn `DELETE` xóa hàng triệu bản ghi trong một transaction có thể:

- Tạo nhiều WAL.
- Giữ row lock lâu.
- Tạo dead tuples lớn.
- Tăng áp lực autovacuum.
- Gây độ trễ replication.
- Làm transaction kéo dài và ảnh hưởng các thao tác khác.

Thông thường nên purge theo **batch nhỏ có kiểm soát**, với tiến trình đo và giới hạn tài nguyên.

Ví dụ batch tối đa 100 đơn hàng đã soft delete và đủ điều kiện đơn giản:

~~~sql
WITH candidates AS (
    SELECT order_id
    FROM lifecycle_lab.customer_order
    WHERE deleted_at IS NOT NULL
      AND retention_until <= statement_timestamp()
      AND legal_hold = FALSE
    ORDER BY retention_until, order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
DELETE FROM lifecycle_lab.customer_order AS o
USING candidates AS c
WHERE o.order_id = c.order_id
RETURNING
    o.order_id,
    o.customer_id,
    o.retention_until;
~~~

Phân tích:

1. CTE `candidates` chọn một số hàng đủ điều kiện.
2. `FOR UPDATE` giữ row lock trên ứng viên trong transaction của statement.
3. `SKIP LOCKED` giúp nhiều worker tránh chờ cùng những hàng đang bị worker khác khóa.
4. `DELETE ... USING` xóa đúng các hàng ứng viên.
5. `RETURNING` cho biết đã xóa những hàng nào.

**`SKIP LOCKED` tạo góc nhìn không đầy đủ tại một thời điểm**: nếu một hàng đang bị lock, worker có thể bỏ qua và thử lại ở vòng sau. Phù hợp xử lý hàng đợi/batch, không dùng làm cơ chế đọc toàn bộ dữ liệu nhất quán cho báo cáo.

### 22.1. Vì sao cần giới hạn batch?

Với batch 100 hoặc 1.000 hàng, worker có thể:

- Commit thường xuyên.
- Hạn chế transaction dài.
- Theo dõi số hàng đã xóa và thời gian.
- Dừng khi tải DB cao.
- Tăng/giảm batch size dựa trên thực nghiệm.

Không có batch size tối ưu cố định. Một hàng chứa JSON/BLOB lớn hoặc nhiều bảng liên quan có chi phí rất khác một hàng nhỏ.

### 22.2. Lệnh ví dụ chưa đủ cho production

Trước khi chạy purge thật cần kiểm tra:

- Quan hệ FK và child tables.
- Hold độc lập và chính sách version.
- Phương án archive hoặc anonymization nếu yêu cầu.
- Quyền của worker và giới hạn tải.
- Audit mà không lưu tràn lan thông tin nhạy cảm.
- Việc dữ liệu đã có trong replica, CDC, backup và hệ thống khác.
- Quy trình khôi phục khi xóa nhầm.

**Không đưa lệnh hard delete vào cron production chỉ bằng cách sao chép đoạn SQL này.**

## 23. Purge hàng cha cần kiểm tra child data

Bảng `customer_order` có foreign key tới `customer`. Trong thiết kế ví dụ, FK không có `ON DELETE CASCADE`.

Nếu cố xóa vật lý khách hàng còn đơn:

~~~sql
-- Dự kiến bị từ chối khi khách vẫn có đơn tham chiếu.
DELETE FROM lifecycle_lab.customer
WHERE customer_id = 101;
~~~

PostgreSQL sẽ kiểm tra foreign key và có thể từ chối. Đây là hành vi bảo vệ tính toàn vẹn tham chiếu.

Một truy vấn **xem ứng viên khách hàng không còn bất kỳ đơn nào**:

~~~sql
SELECT
    c.customer_id,
    c.retention_until
FROM lifecycle_lab.customer AS c
WHERE c.deleted_at IS NOT NULL
  AND c.retention_until <= statement_timestamp()
  AND c.legal_hold = FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM lifecycle_lab.customer_order AS o
      WHERE o.customer_id = c.customer_id
  )
ORDER BY c.retention_until, c.customer_id;
~~~

Cần chú ý: điều kiện `NOT EXISTS` kiểm tra **mọi đơn**, không chỉ đơn chưa soft delete. Một đơn đã soft delete nhưng chưa hard delete vẫn là hàng tham chiếu.

### 23.1. Khi nào dùng ON DELETE CASCADE?

Foreign key với `ON DELETE CASCADE` có thể xóa vật lý hàng con khi hard delete hàng cha:

~~~sql
-- Ví dụ khái niệm, không thay đổi schema demo:
-- FOREIGN KEY (customer_id)
-- REFERENCES customer(customer_id)
-- ON DELETE CASCADE
~~~

Nhưng nó không quan tâm child đang có `legal_hold`, chính sách lưu giữ dài hơn hoặc cần archive riêng. Một cascade có thể quá nguy hiểm nếu các loại dữ liệu có vòng đời khác nhau.

Chỉ dùng cascade khi quan hệ sở hữu và chính sách vòng đời của dữ liệu con thật sự cho phép điều đó. Không dùng để “né” lỗi foreign key trong job purge.

### 23.2. Trường hợp cần giữ đơn nhưng xóa thông tin nhận dạng khách

Có thể phải tách rõ:

- Dữ liệu nhận dạng khách (PII).
- Dữ liệu giao dịch cần giữ.
- Một mã tham chiếu phi nhận dạng phục vụ đối soát.

Giải pháp có thể là ẩn danh dữ liệu khách khi cho phép, dùng bảng identity riêng, hoặc điều chỉnh quan hệ theo mô hình được thiết kế từ đầu. **Không tự giả định rằng thay email bằng chuỗi giả đã khiến toàn bộ hồ sơ không thể tái nhận dạng.**

## 24. Audit log: ai đã xóa, khôi phục, giữ hoặc purge?

Một trường `deleted_by` hữu ích nhưng không phản ánh toàn bộ lịch sử:

- Người A xóa mềm.
- Người B khôi phục.
- Người C xóa lần nữa.
- Một tác vụ cập nhật retention.
- Nhân viên khác bật legal hold.
- Job thực hiện hard delete.

Nếu cần audit, có thể thêm một bảng sự kiện:

~~~sql
CREATE TABLE lifecycle_lab.data_lifecycle_event (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    actor_id TEXT NOT NULL,
    policy_code TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_lifecycle_event_type
        CHECK (
            event_type IN (
                'soft_deleted',
                'restored',
                'retention_changed',
                'hold_applied',
                'hold_released',
                'purged'
            )
        )
);
~~~

Đây là mẫu tối giản. Với hệ thống thật cần thiết kế:

- Quyền append và quyền đọc audit.
- Cách bảo vệ audit khỏi sửa/xóa trái phép.
- Phạm vi thông tin được phép ghi trong `details`.
- Cách liên kết event với idempotency key/request ID.
- Tính chính xác thứ tự sự kiện và liên kết transaction.
- Chính sách retention **của chính audit log**.
- Cách ghi sự kiện purge khi hàng gốc đã mất.

**Không đặt email, token, thông tin nhạy cảm tùy tiện vào audit log**; như vậy có thể duy trì dữ liệu lâu hơn ngoài dự kiến và làm khó việc xóa sau này.

## 25. Ghi sự kiện cùng transaction xóa mềm

Ví dụ một thao tác xóa mềm và ghi audit trong cùng transaction:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE lifecycle_lab.customer
    SET
        deleted_at = statement_timestamp(),
        deleted_by = 'operator:training',
        deletion_reason = 'user_requested',
        retention_until = statement_timestamp() + INTERVAL '90 days',
        updated_at = statement_timestamp()
    WHERE customer_id = 103
      AND deleted_at IS NULL
    RETURNING customer_id
)
INSERT INTO lifecycle_lab.data_lifecycle_event
    (entity_type, entity_id, event_type, actor_id, policy_code)
SELECT
    'customer',
    customer_id,
    'soft_deleted',
    'operator:training',
    'customer-retention-example'
FROM changed;

COMMIT;
~~~

Nếu không có hàng khách nào được cập nhật, CTE `changed` trả 0 hàng nên không thêm event `soft_deleted` giả.

Transaction bảo đảm thay đổi trạng thái và event trong cùng database được commit hoặc rollback cùng nhau. Nhưng nếu audit cần lưu dấu **cả những yêu cầu không thành công**, đó là mục tiêu khác, có thể cần cơ chế ghi nhận riêng với sự đồng ý về bảo mật.

## 26. Event sourcing và soft delete khác nhau

Soft delete giữ lại bản ghi hiện tại cùng cờ/trường đánh dấu. **Event sourcing** lưu lịch sử sự kiện và có thể tái dựng trạng thái từ chuỗi sự kiện. Hai mô hình không đồng nghĩa:

~~~text
Soft delete:
  customer(id=101, deleted_at=...)

Event sourcing:
  CustomerCreated
  CustomerEmailChanged
  CustomerDeleted
~~~

Hệ thống event-sourced vẫn cần chính sách retention và quyền riêng cho event log; dữ liệu cá nhân có thể tồn tại trong sự kiện cũ. Một event `CustomerDeleted` không tự xóa byte trong kho event.

Có thể kết hợp soft delete, outbox và event log, nhưng cần làm rõ đâu là nguồn sự thật và cách xóa dữ liệu ở từng nơi.

## 27. Soft delete trong ORM và repository layer

ORM thường có cơ chế filter hoặc annotation giúp bỏ qua hàng bị xóa mềm. Dù dùng Hibernate, Spring Data hoặc thư viện khác, cần kiểm tra cẩn thận:

1. `findById` có loại bỏ hàng soft deleted không?
2. Query native SQL có tự thêm điều kiện không?
3. Các query aggregate và JOIN có cùng semantics không?
4. Batch job và admin query có cần xem dữ liệu đã xóa không?
5. Unique index có đúng với filter ORM không?
6. Restore có thể phát sinh unique conflict không?
7. Có trường hợp ORM gọi SQL `DELETE` thật trong khi mong xóa mềm không?
8. Có vòng đời/trạng thái cache sau thay đổi không?

Không nên coi một annotation soft delete của ORM là đủ để bảo đảm mọi truy vấn, trigger, stored function và job đều áp dụng cùng điều kiện.

### 27.1. Repository API nên thể hiện ý định

Ví dụ ý tưởng ở tầng ứng dụng:

~~~text
findActiveCustomer(id)
findCustomerIncludingDeleted(id)
softDeleteCustomer(id, actor, reason)
restoreCustomer(id, actor)
findPurgeCandidates(cutoff, batchSize)
~~~

Những API này rõ nghĩa hơn việc một phương thức `delete` chung dùng lẫn cả soft delete và hard delete.

Đối với câu lệnh SQL, nên dùng prepared statements và tham số cho ID, actor, lý do; không ghép dữ liệu người dùng trực tiếp vào chuỗi SQL.

## 28. Row-Level Security có thay thế soft-delete filter không?

PostgreSQL hỗ trợ **Row-Level Security (RLS)** để kiểm soát hàng nào được một role đọc hoặc sửa theo policy.

Về nguyên tắc có thể xây policy để role ứng dụng chỉ nhìn hàng `deleted_at IS NULL`. Tuy nhiên:

- RLS là cơ chế **phân quyền ở mức hàng**, không phải công cụ retention.
- Policy `USING` và `WITH CHECK` có semantics khác nhau cho SELECT/UPDATE/INSERT.
- Chủ sở hữu bảng và role có `BYPASSRLS` hoặc superuser có quy tắc ngoại lệ.
- DML soft delete có thể cần được phép chuyển một hàng từ “visible” sang “not visible” mà không bị policy ngăn bất ngờ.
- Một quyền đọc audit có thể cần nhìn tombstones, trong khi role ứng dụng không được.
- RLS của bảng này không tự xóa dữ liệu trong bảng liên quan hoặc backup.

Vì vậy **không bật một policy RLS mẫu trên production chỉ để thay điều kiện WHERE**, nếu chưa thử đầy đủ các luồng đọc, ghi, soft delete, restore và admin.

Có thể dùng tổ hợp: role ứng dụng chỉ truy cập qua view/RLS với policy phù hợp, còn role vận hành có quyền kiểm tra bản ghi đã xóa theo quy trình kiểm soát. Nhưng mục tiêu bảo mật và mục tiêu vòng đời cần được thiết kế, thử và giám sát riêng.

## 29. Multi-tenant: uniqueness và retention theo khách thuê

Giả sử hệ thống phục vụ nhiều tổ chức (tenant). Một email có thể được phép xuất hiện ở nhiều tenant, nhưng phải duy nhất giữa các khách chưa xóa trong **cùng tenant**.

Thiết kế partial unique index ví dụ:

~~~sql
-- Giả sử bảng có tenant_id và email:
CREATE UNIQUE INDEX uq_customer_live_email_per_tenant
ON tenant_customer (tenant_id, lower(email))
WHERE deleted_at IS NULL;
~~~

Đây là ví dụ cú pháp, không chạy trên schema `lifecycle_lab.customer` vì bảng demo không có `tenant_id`.

Khi multi-tenant, cần lưu ý:

- Mọi truy vấn phải giới hạn đúng `tenant_id` theo mô hình bảo mật.
- Retention policy có thể khác theo hợp đồng/loại dữ liệu, nhưng phải tuân thủ chính sách được phê duyệt.
- Purge một tenant không được tác động hàng của tenant khác.
- Index và foreign key phải bảo đảm quan hệ đúng tenant nếu mô hình yêu cầu.
- Audit và outbox có thể cần mang `tenant_id` nhưng phải tránh lộ thông tin giữa tenant.
- Dữ liệu dùng chung toàn hệ thống có thể có vòng đời khác dữ liệu riêng tenant.

**Partial index không thay thế việc kiểm soát tenant isolation.** Nó chỉ thực thi một quy tắc uniqueness đã khai báo.

## 30. Partitioning và retention dữ liệu lớn

Với bảng log, sự kiện hoặc dữ liệu theo thời gian có khối lượng rất lớn, purge từng hàng có thể tốn chi phí. PostgreSQL hỗ trợ **declarative partitioning** để chia bảng theo một partition key.

Ví dụ:

~~~sql
CREATE TABLE lifecycle_lab.event_log (
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL
)
PARTITION BY RANGE (occurred_at);

CREATE TABLE lifecycle_lab.event_log_2026_01
PARTITION OF lifecycle_lab.event_log
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');

CREATE TABLE lifecycle_lab.event_log_2026_02
PARTITION OF lifecycle_lab.event_log
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO ('2026-03-01 00:00:00+00');
~~~

Khi một partition chứa toàn bộ dữ liệu **đã hết hạn và không cần giữ**, có thể thiết kế quy trình detach/archive/drop partition theo tài liệu PostgreSQL, thay vì `DELETE` từng hàng.

### 30.1. Không drop partition chỉ vì nó “đã cũ”

Trước khi xóa một partition, phải chắc:

- Tất cả dữ liệu trong partition đã hết hạn theo policy.
- Không còn legal hold/record exception trong partition.
- Backup, archive và audit đã được xử lý.
- Không có query/report cần phục hồi dữ liệu từ partition đó.
- Các foreign key và dependency cho phép thao tác.
- Công việc được phê duyệt và diễn tập.

Nếu partition tháng 1 có một hồ sơ cần giữ tới năm sau, **xóa cả partition tháng 1 là sai**. Có thể phải chuyển hồ sơ exception, thiết kế phân vùng theo policy hoặc chọn purge theo hàng.

### 30.2. Partition key quyết định cách purge

Nếu retention dựa trên `occurred_at`, partition theo thời gian có thể phù hợp cho dữ liệu bất biến như event log.

Nếu retention dựa trên `deleted_at` nhưng phần lớn hàng chưa xóa, partition theo `created_at` không đảm bảo mọi hàng trong một partition đều đủ điều kiện purge.

Có thể chọn kiến trúc:

- Bảng dữ liệu live.
- Bảng tombstone/archive riêng.
- Partition theo ngày hết hạn của dữ liệu archive.
- Quy trình chuyển dữ liệu và giữ toàn vẹn tham chiếu.

Đây là quyết định kiến trúc lớn, phải xét query patterns, uniqueness, FK và độ phức tạp vận hành.

### 30.3. Unique constraint trên partitioned table có hạn chế

Trong PostgreSQL, những ràng buộc unique/primary key của partitioned table có điều kiện liên quan partition key; không mặc định có **global unique index** chỉ trên một cột không thuộc partition key.

Vì vậy, nếu chuyển bảng `customer` sang partitioning theo `deleted_at` hoặc `created_at`, quy tắc “email live duy nhất trên toàn bộ bảng” có thể cần thiết kế lại. Không áp dụng nguyên xi partial unique index của bảng thường mà chưa kiểm tra khả năng của phiên bản PostgreSQL và mô hình partition.

## 31. Archive và tiered storage

Xóa mềm không nhất thiết là cách tiết kiệm chi phí lưu trữ. Nếu dữ liệu lớn vẫn nằm trong bảng chính, những tác vụ sau có thể nặng dần:

- Table/index scans.
- VACUUM/ANALYZE.
- Backup và restore.
- Replication và WAL.
- Storage provisioning.
- Số dòng cần bỏ qua khi phân tích.

Một kiến trúc phân tầng có thể là:

~~~text
Dữ liệu đang hoạt động
      |
      | Đạt mốc ít dùng / đóng giao dịch
      v
Dữ liệu archive có kiểm soát
      |
      | Hết hạn retention + không có hold
      v
Purge / anonymize theo chính sách
~~~

Archive có thể nằm trong schema/bảng riêng, database riêng hoặc object storage theo định dạng phù hợp. Nhưng chuyển dữ liệu ra khỏi bảng live **không tự giảm nghĩa vụ bảo mật và lưu giữ**.

Cần xác định:

- Cách truy xuất bản archive.
- Khả năng đối soát integrity.
- Quyền và mã hóa.
- Retention trên kho archive.
- Phục hồi một phần dữ liệu khi cần.
- Cách xóa bản sao archive khi đủ điều kiện.

Nếu bảng có foreign key xuyên dữ liệu live/archive, kiến trúc cần được thiết kế trước; chỉ chuyển hàng khỏi bảng cha có thể khiến bảng con mất liên kết hoặc không thể chuyển.

## 32. Indexing cho soft delete và purge

Có ít nhất hai nhóm truy vấn khác nhau.

### 32.1. Truy vấn live

Ví dụ:

~~~sql
SELECT *
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND lower(email) = lower('an@example.test');
~~~

Partial unique index `uq_customer_live_email` có thể phục vụ tìm kiếm theo `lower(email)` khi predicate phù hợp.

### 32.2. Truy vấn purge

~~~sql
SELECT customer_id, retention_until
FROM lifecycle_lab.customer
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE
  AND retention_until <= statement_timestamp()
ORDER BY retention_until, customer_id
LIMIT 100;
~~~

Partial index cho ứng viên purge:

~~~sql
CREATE INDEX ix_customer_purge_candidate
ON lifecycle_lab.customer (retention_until, customer_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;
~~~

Đã được khai báo trong schema demo. Nó khác với index phục vụ live query.

**Không tạo index cho mọi tổ hợp cột chỉ vì có truy vấn.** Mỗi index làm tăng chi phí ghi, storage và vacuum. Cần dùng thống kê và `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường thử phù hợp để đánh giá.

### 32.3. Tại sao UPDATE deleted_at có thể tốn chi phí?

Khi `deleted_at` chuyển từ NULL sang một timestamp, hàng rời khỏi tập index “live” và có thể vào tập index “purge”. PostgreSQL phải duy trì index và phiên bản tuple theo MVCC. Với số lượng lớn, thao tác này tạo WAL và dead tuples cần vacuum.

Việc dùng soft delete thay hard delete **không phải lựa chọn không tốn tài nguyên**; chỉ là thay đổi semantics và thời điểm xử lý dữ liệu.

## 33. VACUUM, autovacuum và bloat

PostgreSQL dùng MVCC: `UPDATE` có thể tạo phiên bản tuple mới, `DELETE` đánh dấu phiên bản cũ theo quy tắc transaction. Những phiên bản không còn cần thiết sẽ được `VACUUM` dọn để tái sử dụng không gian.

Hệ quả:

- Soft delete bằng `UPDATE` vẫn có chi phí ghi và vacuum.
- Hard delete hàng triệu dòng tạo nhiều dead tuples.
- Long-running transaction có thể khiến việc dọn các phiên bản cũ bị trì hoãn.
- Các index trên cột thay đổi bởi soft delete cũng cần được duy trì.
- Table bloat có thể tăng nếu workload ghi/xóa lớn và vacuum không theo kịp.

Quan sát thống kê bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lifecycle_lab'
ORDER BY n_dead_tup DESC;
~~~

`n_live_tup` và `n_dead_tup` là thống kê/ước lượng, không phải phép đo chính xác tức thời.

Không tắt autovacuum chỉ để một job purge chạy nhanh hơn mà chưa đánh giá hậu quả. Với workload lớn, phải xem cả bloat, WAL, replica lag và checkpoint.

## 34. Backup, WAL, CDC và các bản sao dữ liệu

Một bản ghi bị soft delete vẫn tồn tại trong:

- Bảng PostgreSQL hiện tại.
- Những bản backup được tạo sau đó, nếu backup lấy cả bảng.
- Có thể trong backup trước đó ở trạng thái chưa bị soft delete.
- WAL lưu theo chính sách backup/replication.
- Replica và hệ thống CDC.
- Search index, cache hoặc warehouse nếu chưa xử lý đồng bộ.
- File export hoặc report đã tạo từ trước.

Sau khi hard delete, các bản backup và hệ thống phụ vẫn có **vòng đời lưu giữ riêng**. Không thể đảm bảo “đã xóa khỏi mọi nơi” chỉ bằng một câu `DELETE` trên primary.

### 34.1. Chính sách backup retention không giống row retention

Ví dụ:

- Một hàng customer được purge khỏi primary lúc 10:00.
- Backup trước 10:00 vẫn có thể chứa hàng đó.
- WAL/backup archive có thể tồn tại đến mốc hết hạn theo chính sách DR.

Cần xác định rõ giữa:

1. Hạn lưu hàng trong database đang hoạt động.
2. Hạn lưu bản backup hoặc snapshot.
3. Hạn lưu dữ liệu trong replica/CDC/analytics.
4. Cơ chế restore backup mà không vô tình đưa dữ liệu đã purge trở lại.

Trong môi trường có yêu cầu xóa dữ liệu nghiêm ngặt, phải phối hợp chính sách bảo vệ dữ liệu, backup và phục hồi. Không tuyên bố một quy trình SQL đơn lẻ đáp ứng toàn bộ yêu cầu pháp lý.

### 34.2. Điều gì xảy ra khi restore một backup cũ?

Backup trước sự kiện xóa có thể khôi phục lại trạng thái hàng chưa bị xóa. Vì vậy quy trình DR cần xem xét:

- Điểm khôi phục và nghĩa vụ xử lý các yêu cầu xóa phát sinh sau điểm đó.
- Event log hoặc danh sách các tác vụ phải áp dụng lại trên môi trường phục hồi.
- Hạn chế truy cập cho instance restore dùng để kiểm tra.
- Kiểm tra/xác nhận trước khi đưa dữ liệu restore trở lại phục vụ ứng dụng.

Đây là lý do retention không chỉ là một job chạy `DELETE` mỗi đêm.

## 35. Thiết kế job purge có kiểm soát

Một job purge production nên có ít nhất các thành phần:

**Đầu vào:** loại dữ liệu, policy/version, mốc thời gian hiện tại, batch size, quyền thực thi.

**Điều kiện:** soft deleted, retention đã hết, không còn legal hold, FK và dependency đã xử lý, không có xung đột với workflow khác.

**Thao tác:** hard delete/anonymize/archive theo chính sách, trong transaction có giới hạn hợp lý.

**Quan sát:** số hàng ứng viên, số hàng xử lý, số hàng lỗi, thời gian batch, WAL/replica lag, số hàng bị hold, lần chạy gần nhất.

**Khả năng dừng:** có dry-run/report trước khi xóa, giới hạn số lượng tối đa, cơ chế tạm dừng khi tải cao hoặc phát hiện dữ liệu bất thường.

**Audit:** lưu đủ metadata về chính sách và kết quả mà không giữ lại nội dung nhạy cảm không cần thiết.

### 35.1. Dry-run để xem ứng viên

~~~sql
SELECT
    COUNT(*) AS eligible_count,
    MIN(retention_until) AS oldest_eligible
FROM lifecycle_lab.customer_order
WHERE deleted_at IS NOT NULL
  AND retention_until <= statement_timestamp()
  AND legal_hold = FALSE;
~~~

Đây là số ứng viên theo điều kiện đơn giản, **không phải cam kết tất cả đều được purge**. Cần các kiểm tra nghiệp vụ/phụ thuộc bổ sung nếu policy yêu cầu.

### 35.2. Đếm kết quả thật của mỗi batch

Ví dụ:

~~~sql
WITH candidates AS (
    SELECT order_id
    FROM lifecycle_lab.customer_order
    WHERE deleted_at IS NOT NULL
      AND retention_until <= statement_timestamp()
      AND legal_hold = FALSE
    ORDER BY retention_until, order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
),
deleted AS (
    DELETE FROM lifecycle_lab.customer_order AS o
    USING candidates AS c
    WHERE o.order_id = c.order_id
    RETURNING o.order_id
)
SELECT COUNT(*) AS removed_in_this_batch
FROM deleted;
~~~

Job có thể lặp những batch nhỏ sau khi commit theo quy trình ứng dụng. Không chạy lặp vô hạn không giới hạn khi database đang có tải cao.

### 35.3. Vì sao nên tách logic chọn và logic thực thi?

Nếu một operator xem báo cáo 100.000 hàng đủ điều kiện nhưng job xóa được 99.990 hàng, cần biết 10 hàng còn lại vì:

- Vừa được áp hold.
- Đang bị row lock bởi thao tác khác.
- Có FK/constraint.
- Policy thay đổi.
- Worker gặp lỗi.
- Có transaction mới sửa trạng thái.

Cần khả năng giải thích chênh lệch thay vì tự điều chỉnh câu SQL cho đến khi xóa được toàn bộ.

## 36. Thực hành kiểm tra xóa mềm và khôi phục

Để thử trên dữ liệu demo, có thể thực hiện tuần tự. **Các bước là những nhánh minh họa riêng**, không phải tất cả luôn chạy thành công nếu trước đó đã thêm email trùng hoặc xóa các hàng liên quan.

### Bước 1 — Xem trạng thái ban đầu

~~~sql
SELECT customer_id, email, deleted_at
FROM lifecycle_lab.customer
ORDER BY customer_id;
~~~

### Bước 2 — Xóa mềm khách 102

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '90 days',
    deleted_by = 'operator:training',
    deletion_reason = 'user_requested',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NULL
RETURNING customer_id, deleted_at;
~~~

### Bước 3 — So sánh query có/không lọc

~~~sql
SELECT COUNT(*) AS all_customers
FROM lifecycle_lab.customer;

SELECT COUNT(*) AS live_customers
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL;
~~~

Nếu chưa thêm hoặc xóa hàng nào khác, kết quả tương ứng là **3** và **2**.

### Bước 4 — Kiểm tra FK đơn hàng vẫn còn

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.deleted_at
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 102;
~~~

Đơn 1003 vẫn tham chiếu khách 102.

### Bước 5 — Khôi phục khi chưa có email trùng

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
RETURNING customer_id, email, account_status;
~~~

Đây là khôi phục dữ liệu ở cấp cột; các hệ thống phụ như cache/search index phải được đồng bộ theo quy trình riêng nếu chúng đã xử lý sự kiện xóa.

### Bước 6 — Thử tính idempotent

Chạy lại `UPDATE` khôi phục có điều kiện. Nó sẽ trả 0 hàng vì `deleted_at` đã NULL.

### Bước 7 — Quan sát EXPLAIN

~~~sql
EXPLAIN
SELECT customer_id, email
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND lower(email) = lower('an@example.test');
~~~

Trên bảng nhỏ, PostgreSQL có thể chọn sequential scan. Điều cần học là partial index chỉ có thể được sử dụng khi điều kiện truy vấn phù hợp, không phải luôn buộc planner dùng index.

### Bước 8 — Thử restore conflict trong transaction riêng

Trên môi trường demo, có thể xóa mềm 102, thêm 104 với email tương đương rồi thử restore 102. Kết quả dự kiến là unique violation. Nếu thử trong một transaction, xử lý `ROLLBACK` trước khi tiếp tục query. **Không chạy các bước này trên dữ liệu thật.**

## 37. Kiểm tra trạng thái bằng constraint và CHECK

Trong DDL mẫu, ta có:

~~~sql
CONSTRAINT chk_customer_delete_metadata
CHECK (
    (
        deleted_at IS NULL
        AND deleted_by IS NULL
        AND deletion_reason IS NULL
        AND retention_until IS NULL
    )
    OR (
        deleted_at IS NOT NULL
        AND retention_until IS NOT NULL
        AND retention_until >= deleted_at
    )
)
~~~

Điều này tránh các trạng thái như:

- Chưa soft delete nhưng đã có mốc retention purge của lần xóa.
- Có `deleted_at` nhưng thiếu mốc retention.
- `retention_until` sớm hơn `deleted_at`.

Tuy nhiên nó **không bảo đảm toàn bộ tính đúng nghiệp vụ**:

- Không chứng minh chính sách 90 ngày đã được áp dụng đúng.
- Không chứng minh actor có quyền xóa.
- Không kiểm tra các bảng khác cùng vòng đời.
- Không bảo đảm hold được xử lý đúng.
- Không ghi lại lịch sử các lần restore.

Constraint là lớp phòng vệ về **bất biến dữ liệu có thể biểu diễn bằng SQL**. Logic quy trình và các quyết định ngoài database cần cơ chế bổ sung.

### 37.1. PostgreSQL CHECK và giá trị NULL

Trong PostgreSQL, một `CHECK` cho phép hàng nếu biểu thức đánh giá thành TRUE hoặc UNKNOWN/NULL; chỉ FALSE mới vi phạm. Vì vậy khi thiết kế constraint cho các trường nullable, phải xét semantics ba giá trị của SQL và dùng `IS NULL`, `IS NOT NULL` hoặc `NOT NULL` phù hợp.

Không giả định:

~~~sql
CHECK (deleted_at <= retention_until)
~~~

tự yêu cầu `retention_until` phải tồn tại khi `deleted_at` không NULL. Nếu `retention_until` là NULL, phép so sánh thành UNKNOWN và có thể vượt qua CHECK.

## 38. Tính nhất quán của policy khi đã có nhiều hệ thống

Một luồng xóa có thể liên quan nhiều hệ thống:

~~~text
User yêu cầu xóa
       |
       v
PostgreSQL customer.deleted_at
       |
       +--> Cache invalidation
       +--> Search index delete/update
       +--> Analytics suppression
       +--> Object storage / file attachments
       +--> Notification service
       +--> Audit + retention decision
       |
       v
Đến hạn purge
       |
       +--> PostgreSQL hard delete/anonymize
       +--> Archive và hệ thống phụ
       +--> Backup retention và DR handling
~~~

Những thay đổi này thường **không nằm trong cùng một transaction**. Cần event IDs, idempotent consumers, outbox, retry, dead-letter queue và reconciliation khi phù hợp.

### 38.1. Khác biệt giữa trạng thái “đã xóa trong UI” và “đã xóa toàn hệ thống”

Nên định nghĩa những trạng thái báo cáo riêng:

- **Hidden from normal UI:** không còn xuất hiện trong truy vấn thông thường.
- **Soft deleted:** còn tồn tại trong database nhưng có tombstone.
- **Purge pending:** đủ điều kiện hoặc đang chờ job xóa.
- **Purged from live system:** đã hard delete/anonymize ở hệ thống chính.
- **Propagation pending/completed:** trạng thái đồng bộ các hệ thống khác.
- **Backup expiry pending:** các bản backup trước thời điểm xóa còn vòng đời riêng.

Không thông báo rằng “dữ liệu đã bị xóa khỏi mọi bản sao” khi mới thực hiện `UPDATE deleted_at`.

## 39. Thiết kế các chỉ số giám sát retention

Có thể quan sát những đại lượng:

| Chỉ số | Ý nghĩa |
|---|---|
| `live_rows` | Số hàng chưa soft delete |
| `soft_deleted_rows` | Số hàng có `deleted_at` |
| `eligible_purge_rows` | Số hàng đến hạn theo policy tối thiểu |
| `held_rows` | Số hàng đang bị giữ |
| `purge_batch_count` | Số hàng thực xóa mỗi batch |
| `purge_failure_count` | Số lần lỗi job |
| `oldest_overdue_age` | Mức chậm trễ lâu nhất so với hạn |
| `WAL_generated` | Áp lực ghi log do purge |
| `replication_lag` | Độ trễ sao chép khi purge |
| `vacuum_progress` | Mức độ dọn dead tuples |

Ví dụ SQL:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE deleted_at IS NULL
    ) AS live_rows,

    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
    ) AS soft_deleted_rows,

    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
          AND retention_until <= statement_timestamp()
          AND legal_hold = FALSE
    ) AS eligible_purge_rows,

    COUNT(*) FILTER (
        WHERE legal_hold = TRUE
    ) AS held_rows
FROM lifecycle_lab.customer;
~~~

Trên bảng rất lớn, truy vấn `COUNT(*)` toàn bảng có thể tốn tài nguyên; không chạy quá thường xuyên chỉ để vẽ dashboard. Có thể dùng bảng tổng hợp, sampling hoặc metrics của worker tùy độ chính xác cần thiết.

### 39.1. Alert cần gắn với quyết định hành động

Ví dụ:

- Job purge không chạy thành công trong nhiều ngày.
- Số hàng quá hạn tăng liên tục.
- Replica lag tăng mạnh sau batch purge.
- Tỷ lệ lỗi FK khi purge cao.
- Một policy mới làm số ứng viên tăng bất thường.
- Backup/restore test không đạt điều kiện bảo vệ dữ liệu.

Không chỉ đo số hàng bị xóa. **Một job xóa 0 hàng có thể đúng** nếu không có ứng viên; cũng có thể là lỗi nếu đã quá hạn nhiều bản ghi. Cần so sánh với trạng thái dữ liệu và chính sách.

## 40. Những sai lầm thường gặp

### Sai lầm 1 — Soft delete được xem như hard delete

Dữ liệu vẫn trong bảng, backup và các hệ thống phụ.

**Cách xử lý:** dùng từ chính xác và xây dựng pipeline purge/anonymization khi yêu cầu.

### Sai lầm 2 — Quên WHERE deleted_at IS NULL

Một số query vô tình hiển thị dữ liệu đã ẩn.

**Cách xử lý:** quy ước repository/view/query, kiểm thử riêng cho bản ghi đã xóa và phân quyền.

### Sai lầm 3 — Dùng UNIQUE(email) toàn bảng trong khi cho phép tái sử dụng

Hàng đã soft delete vẫn chặn email cũ.

**Cách xử lý:** xem xét partial unique index theo chính sách và xử lý xung đột restore.

### Sai lầm 4 — Dùng partial unique index nhưng không nghĩ tới restore

Restore có thể thất bại khi định danh đã được dùng lại.

**Cách xử lý:** định nghĩa chính sách tái sử dụng định danh và quy trình giải quyết conflict.

### Sai lầm 5 — Tin rằng ON DELETE CASCADE xử lý soft delete

`ON DELETE CASCADE` liên quan hard delete, không tự chạy khi cập nhật `deleted_at`.

**Cách xử lý:** viết lifecycle logic riêng cho các quan hệ.

### Sai lầm 6 — Soft delete mọi child một cách máy móc

Đơn hàng có thể có chính sách giữ khác tài khoản.

**Cách xử lý:** mô hình vòng đời theo từng loại dữ liệu, đặc biệt dữ liệu giao dịch.

### Sai lầm 7 — Reset deleted_at khi gọi lại request

Mốc retention bị kéo dài khi retry.

**Cách xử lý:** cập nhật có điều kiện `deleted_at IS NULL` và dùng idempotency.

### Sai lầm 8 — Chỉ dùng is_deleted mà không lưu thời gian

Không biết khi nào bản ghi đủ điều kiện purge.

**Cách xử lý:** dùng `deleted_at` và metadata bổ sung khi có nhu cầu thời gian/audit.

### Sai lầm 9 — Xóa theo thời hạn mà bỏ qua hold

Dữ liệu cần giữ có thể bị purge sai.

**Cách xử lý:** policy version, hold workflow, điều phối giao dịch và kiểm tra ứng viên.

### Sai lầm 10 — Xóa hàng triệu bản ghi trong một transaction

WAL, bloat, lock, autovacuum và replica lag có thể tăng.

**Cách xử lý:** batch nhỏ, giám sát tải, stop conditions và rehearsal.

### Sai lầm 11 — Coi VACUUM sẽ purge hàng có deleted_at

VACUUM không tự hiểu chính sách soft delete của ứng dụng.

**Cách xử lý:** job SQL explicit để hard delete; VACUUM bảo trì phiên bản tuple đã chết.

### Sai lầm 12 — Drop partition chỉ dựa vào tháng

Một partition có thể còn dữ liệu dưới legal hold hoặc chưa hết hạn.

**Cách xử lý:** bảo đảm mọi hàng trong partition đủ điều kiện trước thao tác.

### Sai lầm 13 — Dùng bảng audit để giữ nguyên bản mọi dữ liệu nhạy cảm

Có thể làm data erasure không đạt mục tiêu vì audit chứa bản sao.

**Cách xử lý:** audit metadata tối thiểu, retention riêng và kiểm soát quyền.

### Sai lầm 14 — Quên cache, search index và analytics

Database đã soft delete nhưng kết quả tìm kiếm vẫn hiển thị dữ liệu.

**Cách xử lý:** outbox/events, retry, reconciliation và đo propagation lag.

### Sai lầm 15 — Chỉ xóa live table mà quên backup

Dữ liệu có thể còn trong snapshot, WAL archive hoặc bản restore cũ.

**Cách xử lý:** lập chính sách backup retention và DR phù hợp với yêu cầu dữ liệu.

### Sai lầm 16 — Dùng soft delete như thay thế cho quyền SQL

Người có quyền SELECT trên bảng gốc vẫn có thể xem tombstones.

**Cách xử lý:** thiết kế role, GRANT, view hoặc RLS nếu phù hợp, không chỉ filter ở UI.

### Sai lầm 17 — Không kiểm tra legal hold cạnh tranh với purge

Một worker có thể đọc điều kiện cũ trong khi hold được áp dụng.

**Cách xử lý:** tổ chức transaction và khóa nhất quán, không chỉ đọc một cờ.

### Sai lầm 18 — Chạy purge bằng tài khoản quá quyền

Job có thể xóa nhầm bảng hoặc phạm vi tenant khác.

**Cách xử lý:** role chuyên dụng, quyền tối thiểu, lệnh có điều kiện, logging và giới hạn phạm vi.

## 41. Một kịch bản thiết kế tổng hợp

Giả sử nền tảng bán hàng cần:

- Khách hàng tự đóng tài khoản.
- Cho phép yêu cầu khôi phục trong một thời gian được quy định.
- Đơn hàng hoàn tất được giữ theo chính sách giao dịch.
- Email có thể được tái sử dụng sau khi tài khoản cũ bị xóa mềm.
- Hệ thống tìm kiếm phải ngừng hiển thị hồ sơ đã đóng.
- Một số hồ sơ có thể bị đặt legal hold.
- Purge chạy hàng đêm nhưng không được làm tăng latency của giao dịch đang diễn ra.

### 41.1. Thiết kế một cách thiếu an toàn

~~~text
User bấm Delete
    -> UPDATE customer SET is_deleted = true
    -> Không lọc mọi query
    -> Không có hạn giữ dữ liệu
    -> Job DELETE tất cả is_deleted = true
~~~

Những rủi ro:

- UI/query native có thể tiếp tục hiển thị bản ghi.
- Không biết lúc nào cần purge.
- Không kiểm tra hold.
- Child orders gây lỗi FK hoặc bị cascade sai.
- Không có audit và khả năng khôi phục có kiểm soát.
- Không xử lý cache/search index.
- Không tính backup retention.

### 41.2. Thiết kế có kiểm soát hơn

~~~text
[Request đóng tài khoản]
          |
          v
[Authorize / kiểm tra trạng thái]
          |
          v
[Transaction PostgreSQL]
  - set deleted_at, actor, reason
  - xác định retention_until
  - xử lý những đối tượng có cùng vòng đời
  - ghi outbox và audit metadata
          |
          v
[Commit]
          |
          +----> Cập nhật search/cache qua worker
          |
          +----> Cho phép restore theo chính sách
          |
          v
[Đến hạn retention]
          |
          +----> Kiểm tra hold
          +----> Kiểm tra child data và policy
          +----> Archive/anonymize nếu cần
          |
          v
[Purge batch + audit]
          |
          v
[Đối soát database và các hệ thống liên quan]
~~~

Để giải quyết email trùng khi restore, cần định nghĩa liệu sau soft delete có khóa email trong thời gian grace period hay không. Nếu cho tái sử dụng ngay, người dùng cũ có thể phải chọn email mới khi khôi phục.

Đối với đơn hàng hoàn tất, chính sách có thể yêu cầu giữ một phần lịch sử nhưng loại bỏ PII. Việc làm rõ mô hình này **trước khi xóa** thường dễ hơn sửa database sau khi hệ thống đã hoạt động nhiều năm.

## 42. Bài tập thực hành

### Bài 1 — Chọn loại xóa

Một bài viết bị đưa vào thùng rác 14 ngày; khách hàng có thể khôi phục. Nên dùng soft delete hay hard delete ngay?

**Gợi ý:** soft delete với timestamp và mốc purge phù hợp, sau đó hard delete nếu chính sách cho phép.

### Bài 2 — Truy vấn chỉ xem dữ liệu còn hiệu lực

Viết SQL lấy khách hàng chưa soft delete, không bị đình chỉ.

**Gợi ý:** `WHERE deleted_at IS NULL AND account_status = 'active'`.

### Bài 3 — Tính idempotent

Vì sao câu `UPDATE ... SET deleted_at = now() WHERE customer_id = 101` có thể gây vấn đề khi request bị retry?

**Gợi ý:** mốc xóa có thể bị ghi lại và kéo dài thời hạn retention. Thêm điều kiện `deleted_at IS NULL`.

### Bài 4 — Partial unique index

Tạo unique index cho `lower(email)` chỉ với khách chưa xóa.

**Gợi ý:** `CREATE UNIQUE INDEX ... ON ... (lower(email)) WHERE deleted_at IS NULL`.

### Bài 5 — Khôi phục gặp conflict

Khách cũ ID 102 đã soft delete, ID 104 dùng lại email đó. Vì sao restore ID 102 có thể bị lỗi?

**Gợi ý:** cả hai sẽ là hàng live có email tương đương trong partial unique index.

### Bài 6 — Foreign key

Khi soft delete khách hàng, vì sao đơn hàng của khách đó vẫn tham chiếu khóa ngoại hợp lệ?

**Gợi ý:** hàng khách vẫn tồn tại, chỉ timestamp thay đổi.

### Bài 7 — Retention hai loại dữ liệu

Tài khoản cần xóa sau 90 ngày, đơn hoàn tất cần giữ lâu hơn theo chính sách. Có nên hard delete khách cùng tất cả đơn khi hết 90 ngày không?

**Gợi ý:** không mặc định. Xem retention của đơn, tham chiếu và phương án ẩn danh/tách PII.

### Bài 8 — Legal hold

Viết điều kiện SQL tối thiểu chọn khách đã soft delete, đến hạn và không có `legal_hold`.

**Gợi ý:** `deleted_at IS NOT NULL AND retention_until <= now() AND legal_hold = FALSE`.

### Bài 9 — Audit

Vì sao `deleted_by` trên bảng khách không đủ khi bản ghi đã bị xóa, khôi phục rồi xóa lần nữa?

**Gợi ý:** một cột không lưu đủ lịch sử chuyển trạng thái; cần event/audit với policy riêng.

### Bài 10 — Purge theo batch

Giải thích mục đích của `LIMIT 100 FOR UPDATE SKIP LOCKED` trong CTE chọn ứng viên.

**Gợi ý:** giảm transaction quá lớn và giảm tranh chấp giữa worker; hàng đang khóa có thể được thử lại sau.

### Bài 11 — VACUUM

Nếu một hàng có `deleted_at IS NOT NULL` nhưng chưa bị `DELETE`, VACUUM có xóa hàng đó khỏi dữ liệu nghiệp vụ không?

**Gợi ý:** không; hàng vẫn là tuple hợp lệ hiện tại theo MVCC.

### Bài 12 — Backup

Hard delete một hàng khỏi primary có đảm bảo bản backup hôm qua không còn hàng đó không?

**Gợi ý:** không. Backup có thời hạn lưu và điểm dữ liệu riêng.

### Bài 13 — RLS

Nếu ứng dụng lọc `deleted_at IS NULL` trong UI, một tài khoản có quyền SELECT trên bảng gốc có thể nhìn thấy hàng đã soft delete không?

**Gợi ý:** có thể. Filter giao diện không tự trở thành policy bảo mật.

### Bài 14 — Partition retention

Một partition tháng 1 có 99.999 hàng đã hết hạn và một hàng đang legal hold. Có thể drop partition nguyên khối không?

**Gợi ý:** không, trừ khi đã xử lý ngoại lệ theo quy trình được phê duyệt và bảo toàn yêu cầu giữ.

### Bài 15 — Lỗi policy CHECK và NULL

Vì sao `CHECK (retention_until >= deleted_at)` không bảo đảm retention_until luôn được điền khi deleted_at có giá trị?

**Gợi ý:** phép so sánh với NULL tạo UNKNOWN và CHECK có thể cho phép.

### Bài 16 — Multi-tenant

Một email có thể dùng ở tenant A và B, nhưng mỗi tenant chỉ cho một tài khoản live có email đó. Hãy mô tả partial unique index phù hợp.

**Gợi ý:** khóa gồm `tenant_id` và `lower(email)`, predicate `deleted_at IS NULL`.

### Bài 17 — Job purge không chạy được

Worker purge báo nhiều lỗi FK. Có nên sửa bảng thành `ON DELETE CASCADE` rồi chạy lại không?

**Gợi ý:** không vội. Cần xem vòng đời child, retention, hold và dữ liệu cần bảo toàn.

### Bài 18 — Tác động tới hệ thống ngoài database

PostgreSQL đã commit soft delete nhưng search index vẫn có hồ sơ. Cách nào giúp đồng bộ đáng tin hơn?

**Gợi ý:** outbox/event có ID, consumer idempotent, retry và reconciliation.

### Bài 19 — Tính đúng khi khôi phục

Một hồ sơ đã quá hạn khôi phục nhưng chưa được job purge xử lý. Có nên cho restore chỉ vì vẫn còn row?

**Gợi ý:** không mặc định; quyền restore theo policy, không chỉ tồn tại vật lý.

### Bài 20 — Thiết kế runbook

Hãy liệt kê các bước để triển khai purge production hàng đêm mà không xóa nhầm.

**Gợi ý:** dry-run, kiểm tra policy/hold/dependency, batch nhỏ, quyền tối thiểu, audit, monitoring WAL/replica, ngưỡng dừng và diễn tập.

## 43. Ghi nhớ

- **Soft delete = cập nhật trạng thái**, không phải xóa vật lý; `deleted_at IS NULL` thường dùng để biểu diễn hàng còn hiệu lực.
- **Hard delete = `DELETE`**, nhưng MVCC, WAL, VACUUM và backup có vòng đời lưu trữ riêng.
- **Trạng thái nghiệp vụ khác trạng thái xóa**: đơn `cancelled` hoặc tài khoản `suspended` không mặc nhiên phải bị soft delete.
- **Partial unique index** giúp áp dụng tính duy nhất chỉ cho hàng live; phải cân nhắc xung đột khi restore và chính sách tái sử dụng định danh.
- **Soft delete không kích hoạt `ON DELETE CASCADE`**; vòng đời các bảng có foreign key phải được thiết kế có chủ đích.
- **Retention policy** xác định dữ liệu nào được giữ, tới khi nào và hành động nào được phép; `retention_until` chỉ là một phần mô hình.
- **Legal hold và dependency** có thể ngăn purge dù dữ liệu đã quá hạn thông thường.
- **Purge theo batch** giúp kiểm soát transaction, WAL, lock và áp lực vacuum/replication, nhưng cần điều kiện và giám sát đầy đủ.
- **RLS, view và ORM filter** có thể hỗ trợ việc ẩn dữ liệu, nhưng không tự thay chính sách retention, bảo mật hoặc khôi phục.
- **Archive không phải erasure**; bản backup, replica, CDC, search index và file export vẫn có lifecycle riêng.
- **Audit/outbox** giúp truy vết và truyền sự kiện, nhưng bản thân chúng cũng cần chính sách giữ và bảo mật.
- **Diễn tập và đối soát** quan trọng hơn việc chỉ có một cron job báo “đã chạy thành công”.

Thiết kế xóa mềm tốt không dừng ở việc thêm cột `deleted_at`. Nó phải chỉ rõ **khi nào bản ghi không còn hiển thị, ai được phép khôi phục, những dữ liệu phụ thuộc nào phải giữ, điều kiện nào ngăn hard delete, khi nào được phép purge và cách chứng minh quy trình đã áp dụng đúng trên PostgreSQL cũng như những hệ thống liên quan**. Khi các ranh giới đó được thiết kế ngay từ lược đồ, vòng đời dữ liệu sẽ dễ kiểm soát và ít tạo ra những sự cố khó phục hồi về sau.
