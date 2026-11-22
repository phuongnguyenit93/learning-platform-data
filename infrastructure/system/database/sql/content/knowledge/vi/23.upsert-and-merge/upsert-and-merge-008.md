# Cạnh tranh đồng thời và rủi ro của kiểm tra rồi ghi trong SQL

Hai người dùng, hai tiến trình xử lý đơn hoặc hai worker đồng bộ có thể cố **tạo hoặc sửa cùng một bản ghi tại gần như cùng thời điểm**. Nếu mỗi tiến trình thực hiện một bước **kiểm tra trước**, rồi dựa vào kết quả ấy để quyết định **ghi sau**, kết quả kiểm tra có thể **không còn đúng tại thời điểm ghi**.

Đây là một vấn đề kinh điển của xử lý đồng thời (*concurrency*) và thường được gọi là **race condition** hoặc **TOCTOU** (*time-of-check to time-of-use*: thời điểm kiểm tra khác thời điểm sử dụng). Trong SQL, nó xuất hiện khi lập trình viên viết:

```text
Nếu mã đơn chưa tồn tại:
    INSERT mã đơn đó
Nếu mã đơn đã tồn tại:
    UPDATE mã đơn đó
```

Một tiến trình có thể làm đúng theo kết quả `SELECT` của riêng nó nhưng **hai tiến trình cùng chạy** lại gây xung đột khóa duy nhất, ghi đè dữ liệu mới, đếm lặp tác vụ hoặc mất một lần tăng bộ đếm.

**Mục tiêu của bài** không phải chỉ là biết cú pháp `UPSERT` hay `MERGE`, mà là hiểu:

- Vì sao **`SELECT` kiểm tra rồi `INSERT/UPDATE`** không phải một thao tác nguyên tử (*atomic*) giữa nhiều phiên.
- Khóa `UNIQUE` và giao dịch xử lý được loại rủi ro nào, **không xử lý được loại nào**.
- Cách PostgreSQL dùng `INSERT ... ON CONFLICT DO NOTHING / DO UPDATE` để giải quyết xung đột khóa.
- Vì sao `ON CONFLICT DO UPDATE` vẫn có thể ghi đè dữ liệu mới hơn nếu **không có quy tắc cập nhật**.
- Khi nào cần **khóa dòng**, **optimistic locking**, **mức cô lập `SERIALIZABLE`**, **retry toàn bộ giao dịch** hoặc thiết kế idempotency.
- Vì sao `MERGE` trong các DBMS khác nhau **không tự mang cùng bảo đảm đồng thời**.

Bài thuộc chương **Upsert và MERGE**, module **Database SQL**, với các ví dụ chính trên **PostgreSQL**. Để thực hành phần chạy đồng thời, bạn cần **hai phiên kết nối cơ sở dữ liệu riêng biệt** (Session A và Session B) trên database thử nghiệm.

## 1. Bối cảnh: một mã nghiệp vụ chỉ được có một bản ghi

Giả sử một ứng dụng tiếp nhận đơn từ đối tác. Mỗi đơn có:

- `tenant_id`: đơn vị/khách thuê hệ thống.
- `external_code`: mã đơn do đối tác gửi.
- `amount`, `order_status`: dữ liệu nghiệp vụ.
- `source_version`: phiên bản nguồn.
- `order_id`: khóa nội bộ.

Quy tắc định danh:

> Trong **mỗi tenant**, một `external_code` phải tương ứng **tối đa một đơn**.

Vì thế, khóa nghiệp vụ là **cặp `(tenant_id, external_code)`**, không phải `external_code` riêng lẻ.

Hai worker có thể nhận cùng sự kiện:

```text
Worker A nhận: tenant=7, mã=WEB-002
Worker B nhận: tenant=7, mã=WEB-002
```

Một cách triển khai ngây thơ:

```sql
-- Bước 1.
SELECT 1
FROM orders
WHERE tenant_id = 7
  AND external_code = 'WEB-002';

-- Nếu không thấy dòng nào, bước 2.
INSERT INTO orders (
    tenant_id,
    external_code,
    amount
)
VALUES (7, 'WEB-002', 150000);
```

Khi chỉ có một worker, cách này có vẻ hoạt động. Khi hai worker chạy cùng lúc, cả hai có thể thấy **“không tồn tại”**, rồi cùng cố chèn.

Vấn đề không phải `SELECT` chạy sai. Vấn đề là kết quả của `SELECT` **không đặt ra độc quyền** trên một mã chưa có dòng để khóa.

## 2. Ba khái niệm cần phân biệt

### 2.1. Tính nguyên tử của một câu lệnh

Trong PostgreSQL, một câu `INSERT`/`UPDATE` thông thường có tính nguyên tử về tác động lên dữ liệu transactional: nó không được xem như một chuỗi các dòng ghi thành công nửa vời khi câu lệnh cuối cùng báo lỗi ràng buộc.

Nhưng:

```sql
SELECT ...;
INSERT ...;
```

là **hai câu lệnh khác nhau**. Việc câu thứ nhất đọc trạng thái **không biến quyết định giữa hai câu thành nguyên tử**.

### 2.2. Tính nguyên tử của giao dịch

`BEGIN ... COMMIT` nhóm các câu lệnh trong một giao dịch. Giao dịch giúp các thay đổi có thể **commit cùng nhau** hoặc **rollback cùng nhau**, nhưng **không mặc nhiên ngăn hai giao dịch đồng thời đọc cùng trạng thái cũ rồi quyết định ghi trùng**.

Ví dụ, hai transaction đều chạy:

```sql
BEGIN;
SELECT ... WHERE key = ...;
-- thấy không có
INSERT ...;
COMMIT;
```

Chúng vẫn có thể cùng vượt qua bước `SELECT` khi khóa chưa tồn tại.

### 2.3. Tính toàn vẹn của khóa nghiệp vụ

Khóa `PRIMARY KEY` hoặc `UNIQUE` ở database là lớp bảo vệ để **không cho hai dòng cùng một khóa duy nhất được commit** trong bảng bình thường, theo ngữ nghĩa của ràng buộc.

Nếu không có ràng buộc duy nhất đúng khóa nghiệp vụ, cả hai câu `INSERT` có thể thành công và tạo **hai dòng trùng mã**. Nếu có `UNIQUE`, một trong hai câu ghi có thể phải chờ giao dịch còn lại và sau đó thành công hoặc báo xung đột, tùy kết quả commit/rollback và cách viết lệnh.

**`UNIQUE` bảo vệ dữ liệu cuối cùng; `ON CONFLICT` xác định cách phản ứng khi xung đột xảy ra.**

## 3. Tạo bộ dữ liệu thực hành PostgreSQL

Chỉ tạo các bảng dưới đây trong **database thực hành**. Các đoạn chạy đồng thời sau đó dùng đúng những bảng này.

### 3.1. Bảng đơn hàng

```sql
CREATE TABLE lesson292_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    order_status VARCHAR(20) NOT NULL
        CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),
    source_version INTEGER NOT NULL
        CHECK (source_version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lesson292_orders_business_uk
        UNIQUE (tenant_id, external_code)
);
```

Có **hai loại khóa**:

- `order_id`: khóa nội bộ do DBMS tự sinh.
- `(tenant_id, external_code)`: **khóa nghiệp vụ** nhận diện một đơn từ nguồn.

Nếu đối tác A và B cùng gửi mã `WEB-001` nhưng thuộc tenant khác nhau, đó có thể là **hai đơn khác nhau**. Ràng buộc `UNIQUE (tenant_id, external_code)` cho phép chúng cùng tồn tại.

### 3.2. Thêm một đơn đã tồn tại

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES
    (7, 'WEB-001', 100000.00, 'NEW', 1);
```

Bảng có một dòng cho `(7, 'WEB-001')`. Khóa `'WEB-002'` vẫn **chưa tồn tại** nếu chưa thực hành các ví dụ tiếp theo.

### 3.3. Đọc trạng thái dựa trên khóa nghiệp vụ

```sql
SELECT
    order_id,
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
FROM lesson292_orders
ORDER BY tenant_id, external_code;
```

**Không dự đoán `order_id` tự sinh**. Giá trị thực có thể có khoảng trống do các lần chèn, thử nghiệm, lỗi hoặc rollback.

### 3.4. Bảng đếm và bảng trạng thái tác vụ

Ta sẽ dùng thêm hai bảng riêng cho hai loại cạnh tranh khác nhau:

```sql
CREATE TABLE lesson292_counters (
    counter_name VARCHAR(50) PRIMARY KEY,
    counter_value BIGINT NOT NULL CHECK (counter_value >= 0)
);

INSERT INTO lesson292_counters (counter_name, counter_value)
VALUES ('paid_events', 0);

CREATE TABLE lesson292_request_log (
    request_key VARCHAR(80) PRIMARY KEY,
    request_status VARCHAR(20) NOT NULL
        CHECK (request_status IN ('IN_PROGRESS', 'DONE', 'FAILED')),
    result_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ
);
```

`lesson292_counters` dùng để hiểu **lost update**. `lesson292_request_log` dùng để hiểu **idempotency key** và tác vụ có thể được gửi lại nhiều lần.

## 4. Race condition: hai phiên cùng kiểm tra “chưa tồn tại”

Giả sử cơ sở dữ liệu ở trạng thái ban đầu, chưa có đơn `(7, 'WEB-002')`.

Mở **hai cửa sổ SQL / hai connection khác nhau**. Mỗi cửa sổ phải dùng cùng database, nhưng **không phải cùng một connection**.

### 4.1. Dòng thời gian xảy ra lỗi

| Thời điểm | Session A | Session B |
|---:|---|---|
| T1 | `BEGIN` | |
| T2 | `SELECT ... WEB-002` → **0 dòng** | |
| T3 | | `BEGIN` |
| T4 | | `SELECT ... WEB-002` → **0 dòng** |
| T5 | `INSERT ... WEB-002` → chưa commit | |
| T6 | | `INSERT ... WEB-002` → **có thể chờ A** |
| T7 | `COMMIT` | |
| T8 | | Nhận lỗi trùng khóa `UNIQUE` |
| T9 | | `ROLLBACK` |

Ở T2 và T4, cả hai câu `SELECT` **đều đúng** đối với trạng thái nhìn thấy trong từng transaction. Nhưng khi ghi, hai câu `INSERT` không thể cùng tạo một khóa duy nhất.

### 4.2. Session A: bắt đầu và kiểm tra

Chạy trong Session A:

```sql
BEGIN;

SELECT order_id
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-002';
```

Kết quả dự kiến: **0 dòng**.

**Chưa commit hoặc rollback** để giữ giao dịch A mở.

### 4.3. Session B: bắt đầu và kiểm tra

Chạy trong Session B:

```sql
BEGIN;

SELECT order_id
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-002';
```

Kết quả cũng có thể là **0 dòng**.

### 4.4. Session A: chèn nhưng chưa commit

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (7, 'WEB-002', 150000.00, 'NEW', 1);
```

Session A đã chèn trong giao dịch của nó, nhưng chưa `COMMIT`.

### 4.5. Session B: thử chèn cùng khóa

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (7, 'WEB-002', 150000.00, 'NEW', 1);
```

Nếu Session A vẫn chưa kết thúc, Session B có thể **chờ** để xác định xung đột duy nhất sẽ tồn tại hay không.

Quay lại Session A:

```sql
COMMIT;
```

Sau khi A commit, câu `INSERT` của B sẽ **bị từ chối vì `UNIQUE (tenant_id, external_code)`**. PostgreSQL báo lỗi tương đương “duplicate key value violates unique constraint”.

Kết thúc Session B:

```sql
ROLLBACK;
```

### 4.6. Nếu A rollback thì sao?

Nếu tại T7 Session A chạy `ROLLBACK` thay vì `COMMIT`, dòng `WEB-002` chưa được commit sẽ biến mất. Session B đang chờ có thể **tiếp tục và chèn thành công**, tùy các thao tác/giao dịch khác.

Cách nhìn đúng:

- `UNIQUE` phân xử những lần ghi tranh cùng khóa.
- Kết quả của lần `SELECT` trước đó **không quyết định** chắc chắn kết quả `INSERT` sau đó.
- Chờ khóa, lỗi trùng và retry là các tình huống **bình thường phải được thiết kế**, không phải sự cố hiếm.

### 4.7. Dọn dữ liệu thực hành giữa các kịch bản

Kịch bản trên có thể đã để lại đơn `WEB-002` của A. Khi muốn thử lại từ trạng thái “chưa có”, có thể chạy **chỉ trong database luyện tập**:

```sql
DELETE FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-002';
```

Không dùng câu xóa này trên dữ liệu sản xuất. Phần sau sẽ dùng những mã mới như `WEB-003` để các ví dụ không phụ thuộc vào việc bạn đã chạy kịch bản nào.

## 5. Vì sao thêm BEGIN/COMMIT quanh SELECT rồi INSERT vẫn chưa đủ?

Nhiều người nghĩ rằng:

```sql
BEGIN;

SELECT 1
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-003';

-- Nếu không có:
INSERT INTO lesson292_orders (...);
COMMIT;
```

đã là thao tác “an toàn đồng thời” vì nằm trong một transaction.

Nhưng **transaction bảo đảm nhóm thay đổi**, không nhất thiết bảo đảm **chỉ một giao dịch được quyền thấy “không tồn tại” rồi quyết định chèn**.

Ở mức cô lập PostgreSQL mặc định `READ COMMITTED`:

- Mỗi câu lệnh thường thấy một snapshot dữ liệu đã commit phù hợp với lúc câu lệnh bắt đầu, cộng các thay đổi do chính giao dịch đó thực hiện.
- Hai `SELECT` ở hai phiên có thể cùng thấy khóa chưa tồn tại.
- Kiểm tra `UNIQUE` của `INSERT` vẫn phải phối hợp với giao dịch khác, kể cả khi dòng xung đột chưa hiển thị trong snapshot thông thường của lần `SELECT` trước.

**Câu hỏi quan trọng không phải chỉ là “đã BEGIN chưa?” mà là “ai phân xử độc quyền trên khóa trước khi hai giao dịch cùng ghi?”**

## 6. Bẫy INSERT ... SELECT ... WHERE NOT EXISTS

Để tránh viết `SELECT` riêng rồi `INSERT`, một số người gộp vào **một câu**:

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
SELECT
    7,
    'WEB-003',
    80000.00,
    'NEW',
    1
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson292_orders
    WHERE tenant_id = 7
      AND external_code = 'WEB-003'
);
```

Trong một phiên đơn lẻ, câu này thường đúng ý: nếu chưa có thì chèn; nếu đã có thì nguồn `SELECT` không sinh dòng.

**Nhưng `NOT EXISTS` không tự tạo khóa độc quyền trên một dòng chưa tồn tại.** Dưới cạnh tranh đồng thời, hai statement có thể cùng đánh giá điều kiện là TRUE đối với trạng thái chúng thấy, rồi cùng cố chèn.

Nếu không có `UNIQUE`, có nguy cơ **hai dòng cùng khóa nghiệp vụ**. Nếu có `UNIQUE`, một câu có thể thành công còn câu kia nhận lỗi xung đột.

Do đó:

> **Gộp kiểm tra và ghi vào một statement không tự động tương đương một cơ chế UPSERT an toàn khi tranh chấp cùng khóa.**

Lỗi thường gặp là tin rằng `NOT EXISTS` đã thay `UNIQUE`. Thực tế, ràng buộc duy nhất ở bảng đích vẫn là lớp bảo vệ cốt lõi.

### 6.1. NOT IN cũng không giải quyết vấn đề

Viết:

```sql
WHERE external_code NOT IN (
    SELECT external_code
    FROM lesson292_orders
)
```

vẫn có khoảng tranh chấp giữa thời điểm đánh giá và ghi; ngoài ra `NOT IN` còn có các bẫy `NULL` khi tập con có giá trị thiếu. Vấn đề cạnh tranh đồng thời không được giải quyết bằng đổi `NOT EXISTS` thành `NOT IN`.

### 6.2. Không dùng SELECT COUNT(*) = 0 để làm “khóa”

```sql
SELECT COUNT(*)
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-003';
```

`COUNT = 0` là một thông tin từ snapshot đọc, **không phải một khóa** dành riêng mã `WEB-003`. Đổi cách kiểm tra `EXISTS` sang `COUNT` không thay đổi rủi ro TOCTOU.

## 7. Cơ chế PostgreSQL: INSERT ... ON CONFLICT DO NOTHING

Khi yêu cầu là:

> Nếu mã chưa tồn tại thì tạo; nếu đã có thì **giữ nguyên** và không báo lỗi trùng mã.

có thể viết **một câu UPSERT dạng bỏ qua xung đột**:

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (
    7, 'WEB-004', 95000.00, 'NEW', 1
)
ON CONFLICT (tenant_id, external_code)
DO NOTHING
RETURNING
    order_id,
    tenant_id,
    external_code;
```

Điểm quan trọng:

1. `ON CONFLICT (tenant_id, external_code)` chỉ định khóa/ràng buộc duy nhất thích hợp để xử lý xung đột.
2. `DO NOTHING` bỏ qua việc chèn dòng xung đột.
3. `RETURNING` chỉ trả các dòng **thực sự được chèn**.
4. Nếu mã đã tồn tại, câu lệnh có thể hoàn tất mà `RETURNING` **0 dòng**.

### 7.1. Chạy lặp cùng sự kiện

Nếu chạy lại câu trên khi `WEB-004` đã có:

- Không tạo thêm dòng trùng mã.
- Không cập nhật `amount` hay `order_status`.
- Không có dòng mới trong `RETURNING` cho khóa ấy.

Đây là một dạng **idempotent insert** theo khóa nghiệp vụ. Nhưng chỉ có nghĩa **tạo tối đa một bản ghi**. Nó chưa giải quyết những tác dụng phụ khác như gửi thông báo, trừ tiền hoặc ghi log vào hệ thống ngoài.

### 7.2. Đồng thời hai INSERT DO NOTHING

Giả sử hai worker cùng chèn `WEB-005` bằng:

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (
    7, 'WEB-005', 120000.00, 'NEW', 1
)
ON CONFLICT (tenant_id, external_code) DO NOTHING;
```

Trong PostgreSQL, hệ thống phối hợp kiểm tra ràng buộc `UNIQUE` để cuối cùng không tạo hai dòng cùng khóa. Một phiên có thể chờ phiên kia, sau đó chèn hoặc bỏ qua tùy kết quả giao dịch đối thủ.

**Không có bảo đảm rằng “worker A luôn là người thắng”** hoặc rằng thứ tự dòng/connection quyết định kết quả. Nếu hai worker mang **nội dung khác nhau**, `DO NOTHING` cũng không chọn bản tốt nhất: nó giữ bản đã thắng cuộc chèn đầu tiên theo quy tắc concurrency, không nhất thiết bản có `source_version` cao hơn.

### 7.3. Xung đột phải được hỗ trợ bởi chỉ mục/ràng buộc thích hợp

PostgreSQL `ON CONFLICT (tenant_id, external_code) DO NOTHING` cần có **unique index/unique constraint tương ứng** để suy ra đối tượng phân xử xung đột theo chỉ định.

Nếu bảng không có `UNIQUE(tenant_id, external_code)`, chỉ viết `ON CONFLICT (tenant_id, external_code)` **không tự tạo tính duy nhất**.

Một lỗi có thể có dạng “there is no unique or exclusion constraint matching the ON CONFLICT specification”.

### 7.4. DO NOTHING không che mọi lỗi

`DO NOTHING` không phải `IGNORE ALL ERRORS`. Nó không có nghĩa bỏ qua tùy ý:

- Vi phạm `NOT NULL`.
- Vi phạm `CHECK (amount >= 0)`.
- Vi phạm khóa ngoại.
- Lỗi ép kiểu.
- Lỗi quyền truy cập.
- Các lỗi transaction/concurrency khác.

Cần kiểm tra đúng loại lỗi và có chiến lược retry thích hợp, không gộp mọi lỗi vào nhóm “bản ghi đã tồn tại”.

## 8. ON CONFLICT DO UPDATE: tạo mới hoặc cập nhật cùng khóa

Nếu quy tắc là:

> Nếu chưa có đơn thì tạo; nếu đã có thì cập nhật dữ liệu của đơn.

dùng `ON CONFLICT ... DO UPDATE`:

```sql
INSERT INTO lesson292_orders AS target (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (
    7, 'WEB-001', 125000.00, 'PAID', 2
)
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
RETURNING
    order_id,
    external_code,
    amount,
    order_status,
    source_version;
```

Vì `WEB-001` đã tồn tại, câu này cập nhật dòng ấy.

### 8.1. EXCLUDED là gì?

Trong PostgreSQL, `EXCLUDED` là quan hệ đặc biệt chứa **giá trị của dòng được đề nghị chèn** nhưng bị xung đột.

Ví dụ:

- `target.amount`: giá trị hiện có của dòng đích trong ngữ cảnh `DO UPDATE`.
- `EXCLUDED.amount`: giá trị mới `125000` được gửi vào câu `INSERT`.
- `EXCLUDED.source_version`: phiên bản mới `2` từ nguồn.

`EXCLUDED` là cú pháp PostgreSQL, không phải tên bảng bạn phải tạo.

### 8.2. Vì sao một statement có thể giúp xử lý race tốt hơn?

Với khóa unique thích hợp, `INSERT ... ON CONFLICT DO UPDATE` để database phối hợp việc **chèn nếu chưa có** hoặc **cập nhật khi xung đột** như một câu lệnh, thay vì ứng dụng tự chạy `SELECT` rồi quyết định câu ghi.

Trong PostgreSQL, `READ COMMITTED` có cơ chế đặc biệt cho `ON CONFLICT DO UPDATE`: một dòng gây xung đột do giao dịch đồng thời có thể được cập nhật sau khi chờ, dù dòng ấy không hiện trong snapshot thông thường của phần đọc của statement.

Tuy nhiên, **tính nguyên tử giữa nhánh INSERT/UPDATE không đồng nghĩa mọi chính sách nghiệp vụ đã an toàn**. Nếu hai bản nguồn có dữ liệu cũ/mới, việc ghi đè theo người đến cuối vẫn có thể sai.

## 9. UPSERT vẫn có thể làm mất bản cập nhật mới hơn

Giả sử bản ghi hiện có:

```text
(tenant=7, external_code='WEB-001')
source_version = 5
amount = 180000
status = 'PAID'
```

Hai sự kiện đến lệch thứ tự:

- Worker A nhận **phiên bản 6**, `amount = 190000`.
- Worker B nhận **phiên bản 4** đến trễ, `amount = 150000`.

Nếu cả hai chạy UPSERT không điều kiện:

```sql
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    source_version = EXCLUDED.source_version
```

worker B có thể ghi đè `190000/version 6` thành `150000/version 4` nếu được xử lý sau. `UNIQUE` vẫn hoàn toàn đúng: chỉ có **một dòng**. Nhưng **nội dung dòng sai vì đã mất phiên bản mới hơn**.

### 9.1. Dùng điều kiện so sánh phiên bản ở DO UPDATE

Nếu chính sách nghiệp vụ là “**chỉ chấp nhận `source_version` lớn hơn phiên bản hiện có**”:

```sql
INSERT INTO lesson292_orders AS target (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (
    7, 'WEB-001', 190000.00, 'PAID', 6
)
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE target.source_version < EXCLUDED.source_version
RETURNING
    order_id,
    external_code,
    amount,
    source_version;
```

Nếu dòng đích có phiên bản 5, câu lệnh cập nhật lên 6.

Nếu một sự kiện phiên bản 4 hoặc 6 được xử lý **sau khi dòng đã ở version 6**, điều kiện `target.source_version < EXCLUDED.source_version` sai nên **không ghi đè**.

### 9.2. Ý nghĩa của WHERE trong DO UPDATE

`WHERE` trong phần `DO UPDATE` xác định **có thực sự cập nhật dòng xung đột hay không**. Ở PostgreSQL, cơ chế xác định và khóa dòng xung đột có thể diễn ra trước khi đánh giá điều kiện này.

Nếu điều kiện là FALSE:

- Dòng hiện có không bị cập nhật bởi nhánh đó.
- Dòng không xuất hiện trong `RETURNING` của câu lệnh.
- Không nên suy diễn `RETURNING` rỗng là “mã không tồn tại”: cũng có thể là **bản nguồn cũ nên bị bỏ qua**.

### 9.3. Phiên bản nguồn phải đáng tin

Điều kiện `source_version` cao hơn chỉ có ý nghĩa nếu nguồn định nghĩa **thứ tự phiên bản nhất quán cho cùng khóa**. Không dùng ngẫu nhiên:

- Timestamp từ hai máy có đồng hồ lệch.
- `stage_id` cấp ở hai vùng khác nhau không có trật tự chung.
- “Ngày nhận được” khi sự kiện có thể đến trễ.
- Một số phiên bản được tái sử dụng hoặc reset sai.

Nếu **phiên bản bằng nhau nhưng payload khác nhau**, cần chính sách lỗi/xung đột rõ ràng, chứ không tự động chấp nhận “bản ghi đến cuối”.

### 9.4. Một UPSERT chưa đủ cho nghiệp vụ nhiều bước

Nếu nhận một đơn vừa cần:

1. Cập nhật đơn.
2. Trừ tồn kho.
3. Ghi bút toán.
4. Gửi thông báo.

thì `ON CONFLICT` trên bảng đơn chỉ bảo vệ phép ghi tương ứng. Phải xác định **giao dịch nhiều bảng**, **idempotency cho từng tác dụng phụ**, và cơ chế phát sự kiện tin cậy. Không suy luận rằng một câu UPSERT đơn hàng khiến toàn bộ quy trình phân tán trở thành nguyên tử.

## 10. Lost update: kiểm tra rồi ghi có thể mất một lần tăng

Loại race thứ hai không phải **trùng khóa**, mà là **mất cập nhật** (*lost update*).

Bảng `lesson292_counters` ban đầu có:

```text
counter_name = 'paid_events'
counter_value = 0
```

Hai worker muốn tăng bộ đếm khi xử lý một sự kiện PAID khác nhau.

### 10.1. Mẫu sai: đọc vào ứng dụng, rồi ghi giá trị tuyệt đối

```text
A: SELECT counter_value → 0
B: SELECT counter_value → 0
A: UPDATE ... SET counter_value = 1
B: UPDATE ... SET counter_value = 1
Kết quả cuối: 1, lẽ ra là 2
```

Về phía ứng dụng:

```sql
-- Câu đọc riêng.
SELECT counter_value
FROM lesson292_counters
WHERE counter_name = 'paid_events';

-- Ứng dụng tự tính new_value = old_value + 1.

-- Câu ghi giá trị đã tính trước.
UPDATE lesson292_counters
SET counter_value = 1
WHERE counter_name = 'paid_events';
```

Nếu hai worker đều đọc 0 rồi ghi 1, cập nhật sau có thể **ghi đè ý định tăng của cập nhật trước**.

### 10.2. Mẫu đúng khi cần tăng một bộ đếm ở một dòng

Đưa phép tính vào **chính câu UPDATE**:

```sql
UPDATE lesson292_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'paid_events'
RETURNING counter_value;
```

Hai phiên cùng tăng một dòng theo cú pháp này: trong PostgreSQL `READ COMMITTED`, các cập nhật phải phối hợp khóa dòng; sau khi chờ cập nhật trước, cập nhật tiếp theo có thể áp dụng phép cộng lên phiên bản dòng hiện hành thích hợp.

Khi hai câu cập nhật **đều commit thành công** và không có thao tác khác, bộ đếm tăng **hai đơn vị**, không mất một lần tăng do cả hai tính từ một giá trị đọc cũ ở tầng ứng dụng.

**Giới hạn:** nếu sự kiện PAID được gửi lặp lại, hai lần cập nhật này vẫn đếm **hai lần**. Cách tránh lost update không tự giải quyết **duplicate event/idempotency**.

### 10.3. Mẫu upsert bộ đếm: chưa có thì tạo, có rồi thì tăng

```sql
INSERT INTO lesson292_counters AS c (
    counter_name,
    counter_value
)
VALUES ('successful_imports', 1)
ON CONFLICT (counter_name)
DO UPDATE SET
    counter_value = c.counter_value + EXCLUDED.counter_value
RETURNING
    counter_name,
    counter_value;
```

- Nếu chưa có `successful_imports`: tạo với giá trị 1.
- Nếu đã có: tăng từ giá trị đang lưu bằng lượng trong `EXCLUDED.counter_value`.

So sánh:

```sql
-- Sai nếu mục tiêu là cộng dồn:
SET counter_value = EXCLUDED.counter_value
```

Cách sai trên **gán về 1** mỗi lần có xung đột, không cộng dồn.

### 10.4. Counter có thể không phản ánh nghiệp vụ nếu thiếu liên kết sự kiện

Một bộ đếm `+1` không thể tự phân biệt lần xử lý đầu tiên và lần retry cùng sự kiện. Với thanh toán/đơn hàng, nên có **mã sự kiện duy nhất**, và thiết kế để chỉ cộng khi sự kiện đó được ghi nhận mới lần đầu, trong cùng transaction phù hợp.

## 11. Optimistic locking: phát hiện người khác đã sửa dòng

Khi ứng dụng cần:

1. Đọc dữ liệu hiện có.
2. Người dùng chỉnh sửa.
3. Ghi nếu dữ liệu **chưa bị ai đổi** kể từ lần đọc.

có thể dùng **optimistic locking** bằng cột phiên bản nội bộ.

Ví dụ bảng hồ sơ độc lập:

```sql
CREATE TABLE lesson292_profiles (
    profile_id INTEGER PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1
);

INSERT INTO lesson292_profiles (
    profile_id, display_name, row_version
)
VALUES (1, 'An', 1);
```

Hai người cùng đọc:

```sql
SELECT display_name, row_version
FROM lesson292_profiles
WHERE profile_id = 1;
```

Cả hai đều thấy `row_version = 1`.

### 11.1. Session A ghi với điều kiện phiên bản

```sql
UPDATE lesson292_profiles
SET
    display_name = 'An Nguyễn',
    row_version = row_version + 1
WHERE profile_id = 1
  AND row_version = 1
RETURNING
    profile_id,
    display_name,
    row_version;
```

A cập nhật thành công, dòng giờ có `row_version = 2`.

### 11.2. Session B ghi với phiên bản cũ

```sql
UPDATE lesson292_profiles
SET
    display_name = 'An Trần',
    row_version = row_version + 1
WHERE profile_id = 1
  AND row_version = 1
RETURNING
    profile_id,
    display_name,
    row_version;
```

B không còn khớp `row_version = 1`, nên **0 dòng được cập nhật**.

Ứng dụng phải hiểu 0 dòng này là **xung đột chỉnh sửa** hoặc có thể là bản ghi không tồn tại. Cần đọc lại trạng thái hoặc trả thông báo người dùng thay vì âm thầm coi như ghi thành công.

### 11.3. Khác với source_version trong UPSERT

- `row_version`: phiên bản của **dòng nội bộ** tăng sau mỗi lần sửa, thường dùng chống ghi đè do form chỉnh sửa cũ.
- `source_version`: phiên bản do **nguồn bên ngoài** cấp, dùng xác định sự kiện mới hơn khi đồng bộ.

Hai cột có thể cùng tồn tại nhưng không nên xem là hoàn toàn tương đương. Một bản ghi có thể được chỉnh sửa nội bộ mà không thay đổi phiên bản nguồn.

### 11.4. Trường hợp cùng lúc có hai UPDATE optimistic

Nếu cả A và B đều chạy `UPDATE ... WHERE row_version = 1` cùng lúc, PostgreSQL phối hợp khóa dòng. Sau khi một cập nhật commit làm `row_version = 2`, cập nhật còn lại ở `READ COMMITTED` sẽ không còn thỏa điều kiện, vì vậy **không cả hai cùng thành công với version 1**.

Ở mức cô lập cao hơn, giao dịch còn lại có thể gặp lỗi serialization thay vì chỉ 0 dòng, tùy tình huống. Ứng dụng phải xử lý **kết quả cập nhật lẫn lỗi giao dịch**.

## 12. SELECT FOR UPDATE: khóa dòng đã tồn tại, không khóa một dòng chưa có

Một phản ứng thường gặp với kiểm tra rồi ghi là thêm:

```sql
BEGIN;

SELECT order_id
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-006'
FOR UPDATE;

-- Nếu không có thì INSERT ...

COMMIT;
```

**Trong PostgreSQL, `SELECT ... FOR UPDATE` khóa những dòng hiện có được truy vấn chọn**, không tự tạo một khóa “khoảng trống” dành riêng cho mọi giá trị khóa **chưa tồn tại**.

Nếu `WEB-006` chưa có, cả A và B có thể nhận **0 dòng**, tức là không có dòng `WEB-006` nào để khóa bằng `FOR UPDATE`. Cả hai vẫn có thể cạnh tranh khi `INSERT`.

### 12.1. Khi nào FOR UPDATE hữu ích?

Khi dòng đã tồn tại và cần thực hiện nhiều bước có phụ thuộc vào giá trị hiện tại:

```sql
BEGIN;

SELECT
    order_id,
    amount,
    source_version
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-001'
FOR UPDATE;

-- Kiểm tra nghiệp vụ dựa trên dòng đã khóa.
-- UPDATE ... WHERE ...;
-- COMMIT hoặc ROLLBACK.

ROLLBACK;
```

Dòng được chọn bị khóa theo chế độ tương ứng trong transaction. Giao dịch khác cần khóa xung đột trên cùng dòng có thể phải chờ.

Tuy nhiên, `FOR UPDATE`:

- Không tự sửa điều kiện nghiệp vụ sai.
- Không bảo vệ các giá trị khóa chưa tồn tại trong PostgreSQL theo cách “khóa dòng rỗng”.
- Không mặc nhiên khóa tất cả bảng con hay hệ thống ngoài.
- Có thể tạo chờ khóa và deadlock nếu nhiều giao dịch lấy khóa khác thứ tự.

### 12.2. Khóa một “dòng neo” có tồn tại

Một kỹ thuật khác là có một bảng quản lý khóa theo tenant hoặc theo tài nguyên nghiệp vụ; trước khi kiểm tra rồi ghi, giao dịch **khóa dòng neo đã tồn tại** đại diện cho phạm vi cần tuần tự hóa.

Ví dụ thiết kế:

```sql
-- Giả định có bảng tenants(tenant_id PRIMARY KEY).
BEGIN;

SELECT tenant_id
FROM tenants
WHERE tenant_id = 7
FOR UPDATE;

-- Mọi writer có chung quy ước phải khóa tenant=7 trước,
-- sau đó mới kiểm tra và ghi mã đơn của tenant ấy.

COMMIT;
```

Kỹ thuật này **chỉ hiệu quả nếu mọi đường ghi cạnh tranh đều tuân theo cùng quy ước**. Nó cũng tuần tự hóa toàn bộ các thao tác trên tenant đó, có thể trở thành nút cổ chai.

Không nên tạo hệ thống khóa thủ công phức tạp khi `UNIQUE + ON CONFLICT` đã giải quyết đúng yêu cầu đơn giản.

## 13. Mức cô lập giao dịch: READ COMMITTED, REPEATABLE READ, SERIALIZABLE

Mức cô lập (*isolation level*) quyết định những hiện tượng đọc/ghi đồng thời nào được DBMS cho phép hoặc phát hiện.

### 13.1. READ COMMITTED trong PostgreSQL

Đây là mức mặc định thường dùng ở PostgreSQL.

- Hai câu `SELECT` ở các thời điểm khác nhau trong cùng transaction có thể thấy **dữ liệu commit mới khác nhau**.
- Một kết quả `SELECT` “không có mã này” không bảo đảm mã đó vẫn vắng mặt khi câu lệnh `INSERT` được thực thi.
- `UNIQUE` vẫn phân xử việc có thể chèn cùng khóa hay không.

Không xem `READ COMMITTED` là “không có bảo vệ”; nó vẫn có tính nhất quán giao dịch và khóa. Nhưng ứng dụng phải thiết kế xử lý race khi nhiều statement làm chung một quyết định.

### 13.2. REPEATABLE READ không thay UNIQUE

Trong PostgreSQL, `REPEATABLE READ` cung cấp snapshot nhất quán trong phạm vi transaction và có những cơ chế chống xung đột ghi nhất định. Tuy nhiên, hai transaction cùng đọc khóa vắng mặt không có nghĩa cả hai được bảo đảm chèn cùng khóa mà không xảy ra chờ, lỗi unique hoặc lỗi serialization.

**Giữ ràng buộc unique đúng khóa nghiệp vụ**; không thay nó bằng giả định về snapshot.

### 13.3. SERIALIZABLE và lỗi serialization

`SERIALIZABLE` cố gắng đảm bảo kết quả của các transaction commit thành công tương đương một thứ tự thực thi tuần tự hợp lệ.

Ở PostgreSQL, mức này có thể **phát hiện cấu trúc phụ thuộc nguy hiểm** và hủy một giao dịch bằng lỗi `serialization_failure` (SQLSTATE `40001`), thay vì cho cả hai commit với kết quả không thể tuần tự hóa.

Ví dụ độc lập trong database thực hành:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'WEB-007';

-- Logic quyết định ghi của transaction.
-- INSERT ... WHERE ...;

COMMIT;
```

Đặt mức cô lập cao hơn **không có nghĩa “không bao giờ lỗi”**. Ngược lại, khi phát hiện race, DBMS có thể yêu cầu ứng dụng **retry giao dịch**.

### 13.4. SERIALIZABLE không phải bản thay thế cho UNIQUE

Ngay cả ở mức `SERIALIZABLE`, quy tắc “chỉ một dòng trên mỗi khóa nghiệp vụ” nên được biểu diễn bằng **`UNIQUE`**. PostgreSQL cũng ghi nhận một số trường hợp các transaction serializable đồng thời có thể gặp lỗi vi phạm unique trong quá trình chèn nếu ứng dụng không phối hợp phù hợp.

Không kết luận mọi xung đột unique có thể tự động chuyển thành một retry an toàn; phải phân biệt:

- **Lỗi serialization/deadlock có thể thử lại toàn giao dịch** theo chính sách.
- **Lỗi unique** có thể biểu thị “bản ghi đã có” hoặc lỗi logic; cần xử lý theo ngữ nghĩa nghiệp vụ.
- **Lỗi dữ liệu** như `CHECK`, `NOT NULL` hoặc quyền truy cập không phải vấn đề chỉ cần retry.

## 14. Retry đúng cách: thử lại cả giao dịch, không chỉ câu cuối

Giả sử transaction thực hiện:

1. Đọc trạng thái đơn.
2. Kiểm tra số dư/tồn kho.
3. Quyết định mức giảm.
4. Ghi đơn và số dư.
5. Commit.

Nếu PostgreSQL báo lỗi serialization ở bước commit, bạn không nên chỉ chạy lại câu `UPDATE` cuối vì quyết định ở bước 1–3 có thể đã dựa trên snapshot không còn hợp lệ.

**Retry an toàn là chạy lại toàn bộ logic của transaction từ đầu với trạng thái mới**, nếu nghiệp vụ cho phép.

### 14.1. Khung xử lý ở tầng ứng dụng

```text
for attempt in 1..MAX_RETRIES:
    BEGIN
    try:
        đọc dữ liệu cần thiết
        tính lại quyết định nghiệp vụ
        thực thi INSERT/UPDATE/DELETE
        COMMIT
        báo thành công
        break
    catch serialization_failure_or_deadlock:
        ROLLBACK
        nếu chưa quá giới hạn: chờ backoff rồi thử lại toàn giao dịch
        nếu hết lần: báo lỗi tạm thời
    catch business_or_validation_error:
        ROLLBACK
        báo lỗi phù hợp; không retry mù quáng
```

Một hệ thống thật cần:

- Giới hạn số lần retry.
- Backoff/jitter để tránh các worker cùng đụng lại ngay.
- Theo dõi mã lỗi DBMS chứ không so sánh chuỗi thông báo.
- Giữ mã yêu cầu/idempotency key qua các lần retry.
- Không gửi email, thu tiền hoặc gọi API bên ngoài không thể hoàn tác lặp lại theo mỗi lần thử không kiểm soát.

### 14.2. Mã lỗi PostgreSQL thường gặp

| SQLSTATE | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `23505` | `unique_violation` | Xét khóa nghiệp vụ và chính sách INSERT/UPSERT; không retry mù |
| `40001` | `serialization_failure` | Retry **toàn giao dịch** khi phù hợp |
| `40P01` | `deadlock_detected` | Retry giao dịch có kiểm soát; xem thứ tự khóa |
| `23503` | `foreign_key_violation` | Sửa tính hợp lệ quan hệ; không chỉ retry vô hạn |
| `23514` | `check_violation` | Sửa dữ liệu/quy tắc, không chỉ retry |
| `23502` | `not_null_violation` | Sửa thiếu dữ liệu, không retry vô hạn |

Mã lỗi là tín hiệu kỹ thuật; việc xem một lỗi là có thể xử lý lại còn phụ thuộc **ngữ cảnh nghiệp vụ và trạng thái giao dịch**.

## 15. MERGE có giải quyết TOCTOU giống ON CONFLICT không?

`MERGE` cho phép mô tả hành vi theo việc dòng nguồn **khớp (MATCHED)** hay **không khớp (NOT MATCHED)** với dòng đích.

Một mẫu PostgreSQL hiện đại, độc lập:

```sql
MERGE INTO lesson292_orders AS t
USING (
    VALUES (
        7,
        'WEB-008',
        78000.00::NUMERIC(12, 2),
        'NEW',
        1
    )
) AS s (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
ON (
    t.tenant_id = s.tenant_id
    AND t.external_code = s.external_code
)
WHEN MATCHED THEN
    UPDATE SET
        amount = s.amount,
        order_status = s.order_status,
        source_version = s.source_version,
        updated_at = CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        tenant_id,
        external_code,
        amount,
        order_status,
        source_version
    )
    VALUES (
        s.tenant_id,
        s.external_code,
        s.amount,
        s.order_status,
        s.source_version
    );
```

`MERGE` diễn tả hai nhánh trong một statement. Nhưng **không phải mọi implementation MERGE đều có cơ chế concurrency giống `INSERT ... ON CONFLICT DO UPDATE`**.

### 15.1. Điểm khác quan trọng ở PostgreSQL

Tài liệu PostgreSQL phân biệt `MERGE` với `INSERT ... ON CONFLICT`. Với `MERGE`, khi đồng thời có dòng mới được chèn bởi giao dịch khác, nhánh `NOT MATCHED THEN INSERT` **có thể gặp lỗi unique** thay vì được bảo đảm tự chuyển thành nhánh `MATCHED UPDATE`.

Nói cách khác:

- `ON CONFLICT DO UPDATE` được thiết kế riêng quanh xung đột unique và có bảo đảm đặc thù về **INSERT hoặc UPDATE** trong các điều kiện phù hợp ở PostgreSQL.
- `MERGE` triển khai **nhiều nhánh thao tác dựa trên matching**, nhưng không nên được xem là lệnh thay thế tương đương tuyệt đối cho tính chất tranh khóa của `ON CONFLICT`.

Vì vậy, nếu yêu cầu chỉ là **UPSERT một khóa unique dưới cạnh tranh cao trong PostgreSQL**, `INSERT ... ON CONFLICT` thường là lựa chọn cần cân nhắc trước. Nếu cần nhiều nhánh thao tác phức tạp theo nguồn và đích, `MERGE` có ích nhưng vẫn cần thiết kế lỗi/retry, ràng buộc và điều kiện đúng.

### 15.2. MERGE và nguồn có khóa lặp

Nếu nguồn `USING` chứa **hai dòng cùng khóa đích**, một câu `MERGE` có thể cố xử lý **một dòng đích nhiều lần** hoặc dẫn đến lỗi/hiệu ứng không mong muốn tùy nhánh và DBMS.

Ví dụ nguồn:

```text
(tenant=7, code=WEB-001, amount=100000)
(tenant=7, code=WEB-001, amount=120000)
```

Nếu yêu cầu một phiên bản duy nhất trên mỗi mã, trước khi `MERGE` cần:

- Nhận diện khóa nghiệp vụ đúng.
- Chọn một dòng nguồn đại diện bằng quy tắc rõ ràng.
- Kiểm tra thứ tự phiên bản.
- Để khóa unique ở đích bảo vệ cuối cùng.

**MERGE không tự tạo quy tắc chọn “dòng nguồn đúng nhất” chỉ vì có MATCHED/NOT MATCHED.**

### 15.3. MERGE và các hệ quản trị khác

| DBMS | Cơ chế liên quan | Lưu ý concurrency |
|---|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT` và `MERGE` | Không coi `MERGE` như bảo đảm UPSERT unique giống `ON CONFLICT`; chi tiết phụ thuộc phiên bản |
| SQL Server | `MERGE`, `UPDATE`/`INSERT`, khóa T-SQL | Có các vấn đề concurrency, plan và đặc tính phiên bản; cần kiểm tra khóa, isolation và các lưu ý chính thức |
| Oracle Database | `MERGE` | Có quy tắc lỗi unique, nguồn lặp và transaction riêng; không mặc định giống PostgreSQL |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` | Không dùng `ON CONFLICT`; nhiều unique key có thể ảnh hưởng cách chọn xung đột |
| SQLite | `INSERT ... ON CONFLICT DO UPDATE` | Cú pháp tương tự một phần, nhưng khóa/transaction và engine khác PostgreSQL |

Chỉ dùng cú pháp được hỗ trợ và đúng **phiên bản thực tế**; một SQL statement có tên “MERGE” ở hai DBMS không đồng nghĩa mọi bảo đảm đồng thời giống nhau.

## 16. SQL Server MERGE và HOLDLOCK: tránh sao chép mẹo một cách máy móc

Trong SQL Server, có hướng dẫn và thảo luận về việc phối hợp `MERGE` với hint khóa như `HOLDLOCK` trong một số mẫu UPSERT để xử lý cạnh tranh trên khóa chưa tồn tại.

Điều cần hiểu ở cấp nguyên tắc:

- `MERGE` được thực thi trong **mô hình khóa và isolation của SQL Server**, khác PostgreSQL.
- `HOLDLOCK` gắn với ngữ nghĩa khóa/phạm vi tương tự serializable cho đối tượng liên quan theo T-SQL, không phải từ khóa SQL đa hệ phổ quát.
- Câu lệnh đúng còn phụ thuộc **chỉ mục unique**, điều kiện `ON`, **thứ tự khóa**, loại nguồn và workload.
- SQL Server `MERGE` có các lưu ý về tính đúng đắn, hiệu năng và phiên bản; trong một số bài toán, mẫu `UPDATE` rồi `INSERT` với khóa/giao dịch đúng có thể dễ kiểm soát hơn.

**Không** mang `WITH (HOLDLOCK)` sang PostgreSQL, và cũng không kết luận chỉ cần thêm một hint là tất cả race/lost update đã biến mất.

Nếu đang thiết kế trên SQL Server, hãy kiểm tra tài liệu `MERGE` và khóa T-SQL đúng phiên bản thay vì áp dụng ngầm các bảo đảm của PostgreSQL `ON CONFLICT`.

## 17. Idempotency key: chống xử lý lặp ở cấp yêu cầu

`UNIQUE (tenant_id, external_code)` giúp tránh **hai đơn cùng mã**. Nhưng một request nghiệp vụ có thể thực hiện nhiều tác động:

```text
POST /charge
  ├── tạo bản ghi xử lý
  ├── ghi bút toán thanh toán
  ├── trừ số dư
  └── gửi biên nhận
```

Nếu client gửi lại cùng request vì mất kết nối mạng, **không được thu tiền hai lần** chỉ vì ứng dụng không nhận được phản hồi lần đầu.

Một kỹ thuật là **idempotency key**: client hoặc hệ thống tạo một khóa duy nhất đại diện cho **cùng một yêu cầu logic**. Bảng `lesson292_request_log` có `request_key PRIMARY KEY`.

### 17.1. Ghi nhận lần xử lý đầu tiên

```sql
INSERT INTO lesson292_request_log (
    request_key,
    request_status
)
VALUES (
    'charge:tenant7:request-2026-001',
    'IN_PROGRESS'
)
ON CONFLICT (request_key) DO NOTHING
RETURNING request_key;
```

- Có dòng `RETURNING`: phiên xử lý đã **claim** được khóa bằng cách tạo dòng mới.
- Không có dòng `RETURNING`: khóa có thể đã được một request khác ghi nhận trước hoặc được một giao dịch khác chèn cạnh tranh.

### 17.2. Claim thành công chưa đồng nghĩa nghiệp vụ hoàn tất

Giả sử worker A tạo `IN_PROGRESS` rồi bị lỗi **trước khi trừ tiền hoặc trước khi ghi DONE**. Worker B nhận cùng idempotency key:

- Không nên tự động tạo request thứ hai.
- Không nên mặc định `IN_PROGRESS` có nghĩa “đã xử lý thành công”.
- Phải có chiến lược quản lý **đang xử lý**, **hoàn tất**, **thất bại**, **hết hạn lease** và **phục hồi khi worker chết**.

Nếu trạng thái tác vụ được quản lý trong cùng database, một số bước có thể đặt **trong một transaction**. Với dịch vụ thanh toán bên ngoài, cần thêm cơ chế idempotency do đối tác hỗ trợ, transactional outbox hoặc thiết kế khác tùy hệ thống.

### 17.3. Cùng key nhưng payload khác là xung đột nghiệp vụ

Nếu lần đầu `request_key = K` với payload “thu 100.000” và lần sau cùng K nhưng payload “thu 200.000”, không nên im lặng dùng kết quả cũ mà không kiểm tra.

Thường cần lưu **fingerprint/hash hoặc cấu trúc yêu cầu chuẩn hóa** để nhận ra việc **tái sử dụng một idempotency key cho nội dung khác**.

### 17.4. Idempotent insert không nhất thiết idempotent processing

```sql
INSERT ... ON CONFLICT DO NOTHING;
```

có thể idempotent về **dòng được chèn**. Nhưng nếu mỗi lần retry vẫn chạy:

```text
gửi email
gọi API trừ tiền
cộng counter
```

ở ngoài nhánh chèn thực sự thành công, hệ thống vẫn có thể làm lặp tác dụng phụ.

**Chống trùng bản ghi là một phần của chống xử lý trùng, không phải toàn bộ giải pháp.**

## 18. Dùng UNIQUE đúng khóa nghiệp vụ và quan tâm NULL

Ràng buộc `UNIQUE` chỉ có ý nghĩa nếu bạn chọn **khóa đúng**.

### 18.1. Khóa gồm tenant và mã nguồn

Đúng với bộ dữ liệu:

```sql
UNIQUE (tenant_id, external_code)
```

Nếu chỉ:

```sql
UNIQUE (external_code)
```

thì tenant 7 và tenant 8 không thể cùng dùng mã `WEB-001` dù nghiệp vụ cho phép.

Ngược lại, nếu chỉ `UNIQUE(tenant_id)` thì mỗi tenant chỉ có thể lưu một đơn — quá hẹp.

### 18.2. NULL và UNIQUE

Trong PostgreSQL, các ràng buộc unique thông thường thường xem các giá trị `NULL` là **khác nhau** khi kiểm tra tính duy nhất, vì vậy một cột nullable có thể chứa nhiều dòng với `NULL` mà không bị coi là trùng theo cơ chế unique mặc định.

Nếu `external_code` được phép `NULL`:

```sql
UNIQUE (tenant_id, external_code)
```

không tự bảo đảm chỉ có một dòng trên mỗi tenant với `external_code NULL` theo mặc định.

Trong ví dụ, ta dùng:

```sql
tenant_id INTEGER NOT NULL,
external_code VARCHAR(40) NOT NULL
```

để khóa nghiệp vụ **luôn có giá trị**. PostgreSQL 15+ còn hỗ trợ `NULLS NOT DISTINCT` cho một số unique index/constraint, nhưng đó là chính sách riêng; không áp dụng mặc định cho mọi DBMS.

### 18.3. Chuẩn hóa khóa

Hai mã `'web-001'` và `'WEB-001'` là khác nhau dưới nhiều kiểu so sánh chuỗi/collation. Nếu hợp đồng nguồn quy định không phân biệt hoa/thường, cần chuẩn hóa giá trị trước khi ghi, hoặc thiết kế chỉ mục/kiểu chuỗi và cơ chế conflict target phù hợp.

Không dùng `LOWER` một cách tùy ý nếu mã phân biệt hoa/thường theo nghiệp vụ. Cách định danh và so sánh phải nhất quán ở **ứng dụng, bảng đích, index unique và câu UPSERT**.

## 19. Partial unique index và “chỉ duy nhất với bản ghi đang hoạt động”

Một hệ thống có `deleted_at` để soft-delete. Có thể yêu cầu:

> Mỗi `(tenant_id, external_code)` được phép có nhiều bản ghi lưu trữ đã xóa, nhưng **chỉ một bản đang hoạt động**.

PostgreSQL hỗ trợ **partial unique index**:

```sql
-- Mô hình độc lập minh họa, không phải bảng lesson292_orders hiện có.
CREATE TABLE lesson292_soft_orders (
    record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX lesson292_soft_orders_active_uk
    ON lesson292_soft_orders (tenant_id, external_code)
    WHERE deleted_at IS NULL;
```

Chỉ các dòng `deleted_at IS NULL` nằm trong ràng buộc uniqueness do index đó thực thi.

### 19.1. Conflict target phải phù hợp với partial unique index

Một cú pháp PostgreSQL thường gặp:

```sql
INSERT INTO lesson292_soft_orders AS t (
    tenant_id,
    external_code,
    amount,
    deleted_at
)
VALUES (
    7,
    'WEB-010',
    105000.00,
    NULL
)
ON CONFLICT (tenant_id, external_code)
    WHERE deleted_at IS NULL
DO UPDATE SET
    amount = EXCLUDED.amount
RETURNING record_id, amount;
```

`WHERE deleted_at IS NULL` ở **conflict target** giúp PostgreSQL suy ra partial unique index phù hợp.

Cần phân biệt với `DO UPDATE ... WHERE ...`:

- `ON CONFLICT (columns) WHERE index_predicate`: liên quan đến **index dùng phân xử xung đột**.
- `DO UPDATE SET ... WHERE update_condition`: quyết định **có cập nhật dòng xung đột đã tìm thấy không**.

Không tráo hai loại điều kiện này cho nhau.

### 19.2. Mềm xóa và mã được tái sử dụng

Nếu một đơn hoạt động bị đánh dấu `deleted_at` khác `NULL`, index cho phép tạo một dòng hoạt động mới cùng mã. Điều đó chỉ đúng nếu hệ thống **cho phép tái sử dụng mã nghiệp vụ** sau khi xóa logic.

Nếu mã đơn phải bất biến duy nhất trong toàn bộ lịch sử, **không dùng partial unique index** để cho phép tái sử dụng.

## 20. Một câu INSERT có nhiều dòng nguồn trùng khóa

Một batch nguồn có thể chứa:

```text
tenant=7, code=WEB-011, source_version=2
tenant=7, code=WEB-011, source_version=3
```

Ngay cả khi `ON CONFLICT DO UPDATE` xử lý cạnh tranh giữa các statement, **một statement chứa nhiều dòng cùng khóa xung đột** vẫn là bài toán riêng.

Ví dụ nguy cơ:

```sql
-- Có thể gây lỗi cardinality violation nếu cùng một dòng đích
-- bị nhắm cập nhật nhiều lần trong cùng statement.
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES
    (7, 'WEB-011', 100000.00, 'NEW', 2),
    (7, 'WEB-011', 120000.00, 'PAID', 3)
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version;
```

PostgreSQL không cho một `INSERT ... ON CONFLICT DO UPDATE` **ảnh hưởng cùng một dòng đích nhiều lần** theo dạng này; có thể báo lỗi `cardinality_violation` khi các dòng đề nghị chèn xung đột nhau.

### 20.1. Chọn một bản nguồn trước khi UPSERT

Dùng `ROW_NUMBER` để lấy phiên bản cao nhất cho mỗi khóa:

```sql
WITH source_rows (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
) AS (
    VALUES
        (7, 'WEB-011', 100000::NUMERIC, 'NEW', 2),
        (7, 'WEB-011', 120000::NUMERIC, 'PAID', 3),
        (7, 'WEB-012',  80000::NUMERIC, 'NEW', 1)
),
ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, external_code
            ORDER BY source_version DESC, amount DESC
        ) AS rn
    FROM source_rows AS s
)
INSERT INTO lesson292_orders AS target (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
SELECT
    r.tenant_id,
    r.external_code,
    r.amount,
    r.order_status,
    r.source_version
FROM ranked AS r
WHERE r.rn = 1
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE target.source_version < EXCLUDED.source_version
RETURNING
    external_code,
    amount,
    source_version;
```

Ở đây:

- Nguồn `WEB-011` chỉ còn **version 3** trước khi vào INSERT.
- `WEB-012` giữ version 1.
- Với dòng đã tồn tại, chỉ cập nhật nếu phiên bản nguồn **lớn hơn** phiên bản đích.

**Lưu ý:** nếu hai dòng nguồn cùng version nhưng payload khác nhau, việc ưu tiên `amount DESC` chỉ là **quy ước minh họa**, không phải chính sách đúng cho mọi nghiệp vụ. Trong thực tế nên đánh dấu dữ liệu xung đột và từ chối khi hai payload bất nhất, hoặc dùng tiêu chí tin cậy đã được quy định.

### 20.2. DISTINCT không tự chọn phiên bản mới nhất

`SELECT DISTINCT tenant_id, external_code, amount, source_version` có thể vẫn giữ hai dòng cùng mã vì các cột khác nhau. Muốn một bản tốt nhất, cần **quy tắc chọn đại diện** thay vì loại trùng toàn hàng một cách mù quáng.

## 21. Deadlock: khi hai giao dịch giữ khóa chéo nhau

Không chỉ có chờ khóa ở một mã. Hai giao dịch cập nhật **hai dòng khác nhau nhưng ngược thứ tự** có thể gây deadlock.

Ví dụ:

| Thời điểm | Session A | Session B |
|---:|---|---|
| T1 | UPDATE dòng X, giữ khóa X | |
| T2 | | UPDATE dòng Y, giữ khóa Y |
| T3 | UPDATE dòng Y → đợi B | |
| T4 | | UPDATE dòng X → đợi A |
| T5 | DBMS phát hiện vòng chờ | Một giao dịch bị hủy |

Không nên chạy thử với các câu lệnh cố tình tạo deadlock trên dữ liệu quan trọng. Nếu gặp `deadlock_detected`:

1. Rollback transaction bị lỗi.
2. Retry toàn bộ transaction nếu nghiệp vụ cho phép.
3. Thiết kế **thứ tự khóa nhất quán**, ví dụ luôn xử lý khóa theo `tenant_id, external_code` tăng dần.
4. Thu hẹp thời gian giữ transaction, tránh gọi mạng bên ngoài khi đang giữ khóa nếu không cần.
5. Quan sát log và kế hoạch, không chỉ tăng số lần retry vô hạn.

### 21.1. UPSERT không miễn nhiễm deadlock

Khi một batch UPSERT nhiều khóa, các transaction vẫn có thể lấy khóa theo thứ tự khác nhau. `ON CONFLICT` giúp phân xử xung đột từng khóa, **không có nghĩa không bao giờ deadlock** trong một nghiệp vụ nhiều dòng.

Dù đơn giản hóa bằng một câu SQL, cần xử lý lỗi transaction có thể retry trong môi trường đồng thời cao.

## 22. Quan sát thực tế với pg_stat_activity và EXPLAIN

Trên PostgreSQL, khi một session chờ khóa, có thể quan sát qua các công cụ giám sát và view hệ thống nếu tài khoản có quyền thích hợp.

Ví dụ truy vấn chẩn đoán tổng quát:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Nếu một câu đang chờ, `wait_event_type` có thể cho biết loại chờ như `Lock`. Không suy diễn chỉ từ một trường rằng “DBMS đang bị treo”; có thể đó là chờ khóa hợp lệ do giao dịch chưa commit.

**Không dùng `pg_terminate_backend` hoặc hủy phiên người khác chỉ để giải quyết ví dụ học tập**. Kiểm tra transaction đang mở và thao tác đang giữ khóa theo quy trình vận hành.

### 22.1. Giới hạn của EXPLAIN

`EXPLAIN` cho thấy kế hoạch truy vấn, chỉ mục và phép xử lý. Nó hữu ích để xem chi phí đọc `SELECT` hoặc tìm khóa. Nhưng kế hoạch không tự chứng minh **không thể xảy ra race**.

Một truy vấn dùng chỉ mục cực nhanh vẫn có thể bị hai worker chạy đồng thời và cùng vượt qua bước kiểm tra. **Đúng dưới cạnh tranh là vấn đề ràng buộc, khóa, isolation và ngữ nghĩa thao tác**, không chỉ thời gian thực thi.

## 23. Kiến trúc an toàn: chọn chiến lược theo loại rủi ro

Không có một mẹo SQL duy nhất giải quyết mọi dạng cạnh tranh. Có thể dùng bảng quyết định:

| Vấn đề | Rủi ro | Công cụ nên xem xét |
|---|---|---|
| Hai worker cùng tạo một mã đơn | Hai dòng trùng hoặc lỗi unique | `UNIQUE` đúng khóa + `INSERT ... ON CONFLICT` |
| Retry cùng đơn đã có | Tạo trùng hoặc xử lý lại | Unique business key, `DO NOTHING`/UPSERT có điều kiện, idempotency |
| Bản nguồn cũ đến sau bản mới | Ghi đè trạng thái mới | `DO UPDATE ... WHERE target.version < EXCLUDED.version` |
| Hai người cùng sửa form | Lost update | `row_version` + `UPDATE ... WHERE row_version = old` |
| Nhiều worker cùng tăng số đếm | Mất lần tăng | `UPDATE SET n = n + delta` hoặc upsert cộng dồn |
| Sự kiện bị gửi lặp làm counter cộng hai lần | Đếm trùng | Khóa sự kiện duy nhất + ghi nhận/cộng trong transaction |
| Ghi nhiều bảng có quyết định liên quan | Invariant bị phá | Giao dịch, khóa thích hợp, isolation/`SERIALIZABLE` khi cần |
| Hai transaction khóa X/Y ngược thứ tự | Deadlock | Thứ tự khóa nhất quán + retry có giới hạn |
| Một dòng chưa tồn tại nhưng cần khóa phạm vi | Hai worker đều thấy vắng | Unique + conflict handling; hoặc khóa một dòng neo/quy tắc đặc biệt |
| MERGE nguồn có nhiều dòng cùng khóa | Một dòng đích bị nhắm nhiều lần | Khử trùng nguồn bằng quy tắc nghiệp vụ |
| Tác vụ gọi dịch vụ ngoài DB | Lặp tác dụng phụ | Idempotency end-to-end, outbox, cơ chế phối hợp phù hợp |

Điểm chung: **định nghĩa bất biến dữ liệu**, thể hiện nó ở mức database nếu có thể, sau đó chọn cách ghi và xử lý lỗi tương ứng.

## 24. Quy trình đề xuất khi thiết kế một UPSERT chịu tải đồng thời

Một quy trình có thể thực hiện theo thứ tự:

1. **Xác định khóa nghiệp vụ:** một bản ghi là duy nhất theo những cột nào, có gồm tenant hay scope khác không?
2. **Thiết kế ràng buộc:** có `UNIQUE`/`PRIMARY KEY` đúng khóa và `NOT NULL`/quy tắc xử lý `NULL` cần thiết.
3. **Định nghĩa chính sách xung đột:** gặp mã đã có thì **giữ nguyên**, **cập nhật**, **báo lỗi** hay **ghi một sự kiện mới**?
4. **Định nghĩa thứ tự dữ liệu:** nếu cập nhật, bản nào là mới hơn/đáng tin hơn? Có version, sequence, timestamp đáng tin hoặc trạng thái xác minh không?
5. **Giải quyết nguồn lặp trong batch:** một khóa có nhiều dòng nguồn thì chọn hoặc từ chối theo quy tắc rõ ràng.
6. **Dùng thao tác nguyên tử tại DBMS:** `ON CONFLICT` của PostgreSQL cho UPSERT unique; `MERGE`/mẫu khác theo DBMS với bảo đảm riêng.
7. **Tách những điều kiện nhiều bước:** nếu đọc rồi xử lý nhiều bảng, quyết định mức cô lập và khóa.
8. **Xử lý retry đúng mã lỗi:** retry toàn giao dịch cho serialization/deadlock nếu an toàn; không retry vô hạn lỗi dữ liệu.
9. **Tính đến idempotency ngoài bảng chính:** email, thanh toán, message broker và các tác vụ có thể phát nhiều lần.
10. **Thử cạnh tranh với hai connection:** không chỉ test chạy một phiên.
11. **Quan sát kết quả:** số dòng thực ghi/cập nhật/bỏ qua, version cuối, những lỗi xung đột và thời gian chờ.
12. **Kiểm tra khả năng phục hồi:** worker chết giữa chừng, transaction rollback, kết nối mất sau commit, client gửi lại cùng request.

Một lời giải chỉ được xem là phù hợp khi nó giải quyết **đúng quy tắc nghiệp vụ cụ thể**, không chỉ dừng ở việc thêm `ON CONFLICT` cho câu SQL.

## 25. Các lỗi phổ biến

### Lỗi 1. SELECT trước rồi INSERT và cho rằng đã an toàn vì ít request

Race phụ thuộc vào việc **hai thao tác chồng nhau**, không nhất thiết hệ thống phải có hàng nghìn request/giây. Một hệ thống thấp tải vẫn có thể trùng thời điểm hiếm gặp.

### Lỗi 2. Bỏ UNIQUE vì đã có NOT EXISTS

`NOT EXISTS` không thay tính duy nhất ở bảng đích. Hai phiên có thể cùng thấy không có dòng rồi cùng chèn.

### Lỗi 3. Tin BEGIN/COMMIT tự biến hai câu thành một quyết định nguyên tử

Transaction không tự tuần tự hóa mọi kiểm tra vắng mặt. Cần unique constraint, thao tác UPSERT, khóa/isolation phù hợp.

### Lỗi 4. SELECT FOR UPDATE trên khóa chưa có rồi nghĩ đã khóa “mã”

Trong PostgreSQL, `FOR UPDATE` khóa dòng tồn tại được chọn. Nếu `SELECT` trả 0 dòng, nó không tự bảo vệ mã chưa có khỏi cạnh tranh.

### Lỗi 5. DO NOTHING rồi mặc định dữ liệu hiện có đúng nhất

Nếu bản nguồn cũ tạo dòng trước, bản mới đến sau sẽ bị bỏ qua dù có version cao hơn. `DO NOTHING` chỉ phù hợp khi chính sách là **giữ nguyên khi đã tồn tại**.

### Lỗi 6. DO UPDATE ghi đè mọi cột dù sự kiện có thể đến trễ

Cần kiểm tra version/thời điểm nghiệp vụ và xác định quyền ghi đè. `UNIQUE` không bảo vệ khỏi cập nhật sai nội dung.

### Lỗi 7. Dùng source timestamp không đáng tin làm thứ tự tuyệt đối

Giờ hệ thống lệch, nhập dữ liệu trễ hoặc timestamp có độ phân giải không đủ có thể làm hai sự kiện không có thứ tự đáng tin. Dùng version nguồn được đảm bảo nếu có, hoặc quy tắc xử lý hòa rõ ràng.

### Lỗi 8. Dùng MAX(version) và MAX(payload) như thể cùng một hàng

Hai phép tổng hợp độc lập có thể lấy từ hai bản nguồn khác nhau. Hãy chọn một **dòng nguồn nguyên vẹn** theo version/priorities, rồi UPSERT.

### Lỗi 9. Một statement có nhiều dòng trùng khóa nhưng dùng DO UPDATE

PostgreSQL có thể báo cardinality violation khi cùng một dòng đích bị nhắm cập nhật nhiều lần. Chọn duy nhất một nguồn trên mỗi conflict key trước.

### Lỗi 10. Đọc counter rồi ghi giá trị tuyệt đối

Hai worker đều đọc 0 rồi ghi 1 dẫn tới lost update. Với một phép tăng, dùng `UPDATE SET n = n + 1`; nếu dữ liệu cần chống xử lý lại, thêm khóa sự kiện.

### Lỗi 11. Nghĩ increment nguyên tử đồng nghĩa event idempotent

Hai lần `n = n + 1` đều đúng theo DBMS, nhưng nếu cùng một event bị xử lý hai lần thì nghiệp vụ vẫn đếm thừa.

### Lỗi 12. Bỏ qua số dòng được cập nhật trong optimistic locking

`UPDATE ... WHERE row_version = old` có thể ảnh hưởng 0 dòng khi bản ghi đã đổi. Phải xử lý xung đột, không báo thành công sai.

### Lỗi 13. Retry chỉ câu INSERT cuối sau lỗi SERIALIZABLE

Khi transaction thất bại do serialization, phải tính lại các quyết định dựa trên dữ liệu mới; retry cả logic transaction có kiểm soát.

### Lỗi 14. Retry vô hạn mọi SQLSTATE

Không nên retry vô hạn lỗi `CHECK`, `NOT NULL`, FK, quyền hoặc sai cú pháp. Phân loại lỗi và có số lần retry tối đa.

### Lỗi 15. Nhầm MERGE với ON CONFLICT ở mọi DBMS

`MERGE` có các bảo đảm và cơ chế xung đột riêng. Trong PostgreSQL, một nhánh `MERGE WHEN NOT MATCHED THEN INSERT` vẫn có thể gặp lỗi unique do concurrent insert.

### Lỗi 16. Nhầm tên cột khóa với phạm vi khóa

Trong hệ thống đa tenant, `external_code` một mình có thể không duy nhất. Phải có conflict target phù hợp với `(tenant_id, external_code)`.

### Lỗi 17. Xem unique index trên nullable key như cấm mọi giá trị NULL lặp

Ngữ nghĩa `NULL` trong unique khác theo DBMS, và PostgreSQL mặc định cho phép nhiều giá trị `NULL` theo quy tắc unique. Đặt `NOT NULL` cho cột khóa bắt buộc.

### Lỗi 18. Gửi thông báo ngoài DB sau mọi lần UPSERT không kiểm tra kết quả

Nếu UPSERT bị bỏ qua do trùng hoặc bản cũ, gửi email/trừ tiền lại có thể khiến xử lý lặp. Cần log và idempotency cho tác dụng phụ.

### Lỗi 19. Không kiểm tra lỗi ở COMMIT

Một số lỗi transaction có thể phát sinh hoặc được báo tại `COMMIT`, đặc biệt với các kiểm tra bị hoãn hoặc serialization. Chỉ coi giao dịch thành công khi **commit thành công**.

### Lỗi 20. Không thử với hai kết nối độc lập

Chạy hai câu nối tiếp trong cùng một connection không mô phỏng đầy đủ race. Cần hai session/transaction thật, có thứ tự T1–Tn rõ ràng.

## 26. Bài tập thực hành có đáp án

Các bài dùng PostgreSQL và bộ bảng `lesson292_*`. Hãy chạy trên database thử nghiệm. Các tình huống hai session là **bài mô phỏng**; không cố tạo deadlock hoặc lỗi trên dữ liệu thật. Bài có `INSERT` có thể thay đổi trạng thái của các bài sau: dùng mã mới hoặc xóa đúng dữ liệu bài thực hành nếu muốn reset.

### Bài 1. Xác định cửa sổ cạnh tranh

Hai worker cùng chạy:

```text
SELECT key tồn tại không?
Nếu không: INSERT
```

Cả hai `SELECT` trả “không có”. Điều gì có thể xảy ra?

**Đáp án:** nếu bảng không có unique đúng khóa, cả hai có thể chèn trùng. Nếu có unique, một lệnh chèn có thể phải chờ rồi bị lỗi, hoặc xử lý theo conflict clause. Cả hai `SELECT` có thể đúng với snapshot của từng phiên; quyết định sau đó không còn độc quyền.

### Bài 2. Dùng NOT EXISTS có giải quyết race không?

```sql
INSERT INTO lesson292_orders (
    tenant_id, external_code, amount, order_status, source_version
)
SELECT
    7, 'EX-002', 50000, 'NEW', 1
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson292_orders
    WHERE tenant_id = 7
      AND external_code = 'EX-002'
);
```

**Đáp án:** Không bảo đảm. Hai transaction có thể cùng đánh giá `NOT EXISTS` là TRUE. Ràng buộc `UNIQUE (tenant_id, external_code)` vẫn cần thiết để ngăn hai dòng trùng. Nếu muốn bỏ qua xung đột thay vì lỗi unique, dùng `ON CONFLICT` phù hợp.

### Bài 3. Viết INSERT idempotent cho mã EX-003

**Yêu cầu:** nếu `(7,'EX-003')` đã có thì không đổi dữ liệu.

```sql
INSERT INTO lesson292_orders (
    tenant_id,
    external_code,
    amount,
    order_status,
    source_version
)
VALUES (7, 'EX-003', 60000.00, 'NEW', 1)
ON CONFLICT (tenant_id, external_code) DO NOTHING
RETURNING order_id, external_code;
```

**Đáp án:** lần đầu có thể chèn và trả dòng; các lần tiếp theo với cùng khóa sẽ không chèn thêm. Không cập nhật giá trị đã tồn tại.

### Bài 4. Vì sao cần UNIQUE trước khi dùng conflict target?

**Câu hỏi:** nếu bỏ ràng buộc unique trên `(tenant_id, external_code)`, chỉ viết `ON CONFLICT (tenant_id, external_code)` có tạo được bảo vệ không?

**Đáp án:** Không. PostgreSQL cần unique index/constraint phù hợp để suy ra arbiter. `ON CONFLICT` không tự thêm unique vào schema.

### Bài 5. UPSERT cập nhật amount nếu mã đã có

```sql
INSERT INTO lesson292_orders AS t (
    tenant_id, external_code, amount, order_status, source_version
)
VALUES (7, 'EX-004', 70000.00, 'PAID', 2)
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
RETURNING external_code, amount, source_version;
```

**Đáp án:** nếu chưa có thì tạo mới; nếu đã có thì cập nhật dòng theo giá trị đề nghị. Nhưng khi sự kiện cũ đến trễ, cách cập nhật không điều kiện có thể ghi đè dữ liệu mới.

### Bài 6. Sửa UPSERT chỉ chấp nhận version mới

```sql
INSERT INTO lesson292_orders AS t (
    tenant_id, external_code, amount, order_status, source_version
)
VALUES (7, 'EX-005', 90000.00, 'PAID', 5)
ON CONFLICT (tenant_id, external_code)
DO UPDATE SET
    amount = EXCLUDED.amount,
    order_status = EXCLUDED.order_status,
    source_version = EXCLUDED.source_version
WHERE t.source_version < EXCLUDED.source_version
RETURNING external_code, amount, source_version;
```

**Đáp án:** dòng đích version 3 được nâng lên 5; dòng version 6 không bị hạ về 5; dòng version 5 không đổi. Nếu điều kiện update không thỏa, `RETURNING` không trả dòng ấy.

### Bài 7. Hai worker tăng counter từ 0

**Yêu cầu:** tránh tình huống cả hai cùng đọc 0 rồi ghi 1.

```sql
UPDATE lesson292_counters
SET counter_value = counter_value + 1
WHERE counter_name = 'paid_events'
RETURNING counter_value;
```

**Đáp án:** với hai cập nhật commit thành công vào cùng dòng và không có cập nhật khác, kết quả cuối tăng 2. Khóa dòng và thực thi biểu thức trên giá trị hiện hành giúp tránh mất lần tăng do ứng dụng ghi giá trị tuyệt đối đã đọc cũ.

### Bài 8. Tại sao cộng counter vẫn có thể đếm thừa?

Một sự kiện thanh toán `evt-101` bị gửi lại hai lần, mỗi lần đều chạy `UPDATE counter_value = counter_value + 1`.

**Đáp án:** SQL tăng đúng hai lần, nhưng nghiệp vụ chỉ có **một sự kiện logic**. Cần ghi nhận `event_id` duy nhất và chỉ cộng khi sự kiện mới được chấp nhận lần đầu, trong transaction phù hợp.

### Bài 9. Optimistic locking với row_version

Giả sử `lesson292_profiles` có `profile_id=1`, `row_version=2`. Ứng dụng đã đọc version 1 và muốn sửa tên.

```sql
UPDATE lesson292_profiles
SET
    display_name = 'Tên sửa từ form cũ',
    row_version = row_version + 1
WHERE profile_id = 1
  AND row_version = 1
RETURNING profile_id;
```

**Đáp án:** **0 dòng** cập nhật vì version không khớp. Ứng dụng cần thông báo xung đột, tải lại và cho người dùng quyết định thay đổi; không âm thầm ghi đè.

### Bài 10. SELECT FOR UPDATE trên dòng chưa tồn tại

Hai transaction đều:

```sql
SELECT *
FROM lesson292_orders
WHERE tenant_id = 7
  AND external_code = 'EX-010'
FOR UPDATE;
```

và đều nhận 0 dòng. Đã khóa được `EX-010` chưa?

**Đáp án:** Chưa. Trong PostgreSQL, `FOR UPDATE` khóa các dòng tồn tại mà truy vấn chọn; không tạo row lock cho khóa chưa có. Muốn ngăn trùng vẫn cần unique và xử lý conflict, hoặc một cơ chế khóa phạm vi đã thiết kế riêng.

### Bài 11. Phân biệt READ COMMITTED và SERIALIZABLE

**Câu hỏi:** Đổi transaction thành `SERIALIZABLE` có bảo đảm không bao giờ phải xử lý lỗi đồng thời nữa không?

**Đáp án:** Không. PostgreSQL có thể báo `serialization_failure` và yêu cầu retry giao dịch; ràng buộc unique vẫn cần cho khóa nghiệp vụ. Mức cô lập cao hơn có thể tăng số transaction phải thử lại khi tranh chấp.

### Bài 12. Retry phần nào sau lỗi 40001?

Một transaction đã đọc tồn kho, tính giá bán, rồi cập nhật đơn. Nó bị lỗi SQLSTATE `40001` tại commit.

**Đáp án:** nếu nghiệp vụ cho phép retry, cần rollback và **thử lại toàn bộ transaction**, gồm đọc tồn kho và tính lại quyết định. Không chỉ retry câu `UPDATE` cuối với giá trị đã tính từ snapshot cũ.

### Bài 13. Vì sao MERGE không tự đảm bảo “không có race”?

Hai session cùng chạy `MERGE WHEN NOT MATCHED THEN INSERT` cho cùng một mã chưa có.

**Đáp án:** tùy DBMS và mức cô lập, hai session có thể cùng đi tới nhánh không khớp rồi tranh chấp khi chèn. Trong PostgreSQL, `MERGE` có thể báo lỗi unique thay vì bảo đảm tự chuyển sang nhánh cập nhật như cơ chế `ON CONFLICT DO UPDATE`. Cần unique ở đích, kiểm soát concurrency và xử lý lỗi.

### Bài 14. Dòng nguồn lặp trước ON CONFLICT DO UPDATE

Nguồn có hai dòng `(7,'EX-014')` với version 4 và 5. Có nên gửi cả hai trực tiếp vào một `INSERT ... ON CONFLICT DO UPDATE`?

**Đáp án:** Không nếu cả hai nhắm cùng một dòng đích: PostgreSQL có thể báo lỗi vì một câu lệnh cố cập nhật cùng dòng nhiều lần. Hãy dùng `ROW_NUMBER() OVER (PARTITION BY tenant_id, external_code ORDER BY source_version DESC, tie_breaker DESC)` rồi lọc `rn = 1`, hoặc từ chối nếu dữ liệu nguồn mâu thuẫn.

### Bài 15. Khóa unique nào phù hợp đa tenant?

Hai tenant 7 và 8 đều có mã đơn `EX-015`. Chúng là hai đơn độc lập.

**Đáp án:** dùng `UNIQUE (tenant_id, external_code)`. Nếu chỉ unique trên `external_code`, sẽ chặn sai nghiệp vụ hai tenant dùng cùng mã.

### Bài 16. Một request bị retry sau mất kết nối

Client gửi `request_key=charge-123`, server xử lý xong nhưng client không nhận phản hồi. Client gửi lại cùng key.

**Đáp án:** hệ thống cần tra/ghi idempotency key ở một nơi có uniqueness phù hợp; trả lại kết quả của yêu cầu đã hoàn tất nếu payload trùng, hoặc theo dõi trạng thái đang xử lý/khôi phục nếu chưa hoàn tất. Không tự gọi lại API thu tiền chỉ vì HTTP request lặp.

### Bài 17. Đọc kết quả DO NOTHING qua RETURNING

```sql
INSERT INTO lesson292_orders (
    tenant_id, external_code, amount, order_status, source_version
)
VALUES (7, 'EX-017', 85000, 'NEW', 1)
ON CONFLICT (tenant_id, external_code) DO NOTHING
RETURNING order_id;
```

Lần đầu trả một dòng; lần hai trả 0 dòng. Có suy ra lần hai xảy ra lỗi không?

**Đáp án:** Không. `DO NOTHING` có thể kết thúc thành công nhưng bỏ qua dòng trùng. 0 dòng `RETURNING` không phải luôn là lỗi; ứng dụng phải phân biệt “đã tồn tại nên không chèn” với các trạng thái khác.

### Bài 18. Dùng ON CONFLICT để tăng bộ đếm mới hoặc cũ

```sql
INSERT INTO lesson292_counters AS c (
    counter_name,
    counter_value
)
VALUES ('processed_batches', 1)
ON CONFLICT (counter_name)
DO UPDATE SET
    counter_value = c.counter_value + EXCLUDED.counter_value
RETURNING counter_name, counter_value;
```

**Đáp án:** lần đầu tạo 1, mỗi lần gọi tiếp thành công tăng thêm 1. Nhưng nếu cùng batch được retry, nó có thể tăng thừa — cần thêm idempotency key của batch nếu muốn đếm batch logic duy nhất.

### Bài 19. Nhận diện xung đột đầu vào ở cùng version

Nguồn gửi hai dòng cho cùng khóa, cùng `source_version = 7`, nhưng `amount` lần lượt 100000 và 200000. Có nên lấy `MAX(amount)`?

**Đáp án:** không có cơ sở chung để kết luận số tiền lớn hơn là đúng. Cần chính sách nhận diện lỗi hoặc tiêu chí chọn nguồn đáng tin. `MAX(amount)` là một quy tắc tự đặt, có thể tạo dữ liệu sai dù không trùng khóa.

### Bài 20. Chọn giải pháp cho bốn loại rủi ro

| Tình huống | Giải pháp cần xem xét |
|---|---|
| Hai worker tạo cùng mã đơn | Unique business key + `ON CONFLICT` |
| Hai người dùng cùng sửa một hồ sơ | `row_version`/optimistic locking |
| Hai worker cộng số đếm trên một dòng | `UPDATE SET n = n + 1` |
| Client gửi lại cùng yêu cầu thu tiền | Idempotency key end-to-end, quản lý trạng thái và tác dụng phụ |

**Đáp án:** mỗi hàng có một cơ chế trọng tâm khác nhau. Không dùng duy nhất `ON CONFLICT DO NOTHING` để thay thế mọi cách bảo vệ này.

## 27. Tóm tắt các mẫu SQL quan trọng

### 27.1. Mẫu có nguy cơ TOCTOU

```sql
SELECT 1
FROM target
WHERE business_key = :key;

-- Nếu không tồn tại:
INSERT INTO target (business_key, value)
VALUES (:key, :value);
```

**Không an toàn đồng thời chỉ nhờ việc SELECT trước.**

### 27.2. Mẫu insert nếu chưa có trong PostgreSQL

```sql
INSERT INTO target (business_key, value)
VALUES (:key, :value)
ON CONFLICT (business_key) DO NOTHING;
```

Cần unique index/constraint phù hợp.

### 27.3. Mẫu UPSERT chỉ cập nhật khi version nguồn lớn hơn

```sql
INSERT INTO target AS t (business_key, value, source_version)
VALUES (:key, :value, :version)
ON CONFLICT (business_key)
DO UPDATE SET
    value = EXCLUDED.value,
    source_version = EXCLUDED.source_version
WHERE t.source_version < EXCLUDED.source_version;
```

Cần định nghĩa và kiểm soát ý nghĩa của `source_version`.

### 27.4. Mẫu tăng counter trên giá trị hiện hành

```sql
UPDATE counters
SET counter_value = counter_value + 1
WHERE counter_name = :counter_name;
```

Giảm rủi ro mất cập nhật do đọc rồi ghi giá trị tuyệt đối; vẫn cần idempotency nếu sự kiện có thể lặp.

### 27.5. Mẫu optimistic locking

```sql
UPDATE profiles
SET
    display_name = :new_name,
    row_version = row_version + 1
WHERE profile_id = :id
  AND row_version = :observed_version;
```

**0 dòng cập nhật** phải được xử lý, không coi mặc nhiên thành công.

Các ví dụ dùng `:key`, `:version` là **ký hiệu tham số ở tầng ứng dụng**, không phải cú pháp literal dùng trực tiếp trong mọi công cụ SQL. Với Java/JDBC, `PreparedStatement` thường dùng dấu `?`.

## 28. Bảng ghi nhớ

| Câu hỏi | Điều cần nhớ |
|---|---|
| TOCTOU trong SQL là gì? | Kết quả kiểm tra có thể lỗi thời trước lúc ghi |
| Transaction có tự ngăn hai INSERT trùng? | Không chỉ nhờ `BEGIN/COMMIT` |
| `NOT EXISTS` trước INSERT có đủ không? | Không đủ để phân xử đồng thời khi khóa chưa tồn tại |
| `UNIQUE` giúp gì? | Bảo vệ tính duy nhất cuối cùng của khóa nghiệp vụ |
| `ON CONFLICT DO NOTHING` | Chèn nếu có thể; bỏ qua khi xung đột theo conflict target |
| `ON CONFLICT DO UPDATE` | Chèn hoặc cập nhật khi xung đột unique, với bảo đảm đặc thù PostgreSQL |
| DO UPDATE có thể ghi đè bản mới? | Có, nếu không kiểm tra version/chính sách |
| `WHERE t.version < EXCLUDED.version` | Chỉ cập nhật khi bản nguồn có version cao hơn theo quy tắc |
| `EXCLUDED` là gì? | Giá trị của dòng đề nghị chèn trong PostgreSQL |
| `RETURNING` không có dòng | Có thể do DO NOTHING hoặc DO UPDATE WHERE không thỏa |
| `SELECT FOR UPDATE` trên 0 dòng | Không khóa một dòng chưa tồn tại trong PostgreSQL |
| Lost update là gì? | Một thay đổi bị ghi đè do thao tác dựa trên dữ liệu cũ |
| Cách tăng counter | `UPDATE SET n = n + 1`, thêm idempotency nếu cần |
| Optimistic locking | `row_version` + `UPDATE ... WHERE row_version = old` |
| Khi nào retry toàn transaction? | Khi gặp lỗi serialization/deadlock phù hợp và nghiệp vụ cho phép |
| `MERGE` có tương đương `ON CONFLICT`? | Không mặc định, đặc biệt về hành vi tranh khóa |
| Multi-row source trùng key | Chọn nguồn duy nhất trước khi UPSERT/MERGE |
| Idempotency key | Nhận diện cùng yêu cầu logic, cần quản lý trạng thái/tác dụng phụ |
| Unique và NULL | Hiểu chính sách `NULL`; dùng `NOT NULL` khi khóa không được thiếu |
| Khóa đa tenant | Thường cần cặp `(tenant_id, external_code)` |
| Test đúng concurrency | Hai connection/transaction độc lập, kiểm tra cả commit và rollback |

## 29. Kết luận

**Rủi ro lớn nhất của “kiểm tra rồi ghi” là thời gian giữa hai bước**. Hai transaction có thể cùng kiểm tra thấy một mã chưa tồn tại, rồi cùng cố chèn. Nếu không có ràng buộc unique đúng khóa, dữ liệu có thể bị trùng. Nếu có unique, một câu có thể phải chờ hoặc bị lỗi; ứng dụng vẫn phải xử lý trạng thái đó.

Trong PostgreSQL, thay vì tự viết `SELECT` để kiểm tra rồi `INSERT`, hãy ưu tiên **ràng buộc `UNIQUE`** và một câu **`INSERT ... ON CONFLICT`** khi mục tiêu thật sự là UPSERT theo khóa. Nếu yêu cầu là giữ bản mới nhất, bổ sung **điều kiện phiên bản** để không bị sự kiện cũ ghi đè. Nếu yêu cầu là tăng bộ đếm, dùng phép cập nhật trên giá trị hiện hành. Nếu người dùng sửa dữ liệu từ bản đọc cũ, dùng **optimistic locking**. Nếu nghiệp vụ trải qua nhiều dòng/bảng, cần thêm giao dịch, isolation, locking và retry thích hợp.

Câu hỏi kiểm tra trước mỗi thiết kế:

1. **Có những worker/giao dịch nào có thể cùng tác động tới khóa này?**
2. **Database đã có ràng buộc thể hiện tính duy nhất hay bất biến chưa?**
3. **Khi hai yêu cầu đến đồng thời, kết quả nào là đúng theo nghiệp vụ?**
4. **Bản cập nhật cũ đến muộn có được phép ghi đè không?**
5. **Nếu giao dịch bị rollback hoặc client retry, các tác dụng phụ có bị làm hai lần không?**

**UPSERT/MERGE là công cụ ghi dữ liệu, không phải phép bảo đảm tự động cho mọi bài toán đồng thời.** Tính đúng đắn đến từ **khóa nghiệp vụ rõ ràng, ràng buộc thích hợp, câu lệnh ghi có ngữ nghĩa đúng và chiến lược xử lý xung đột toàn diện**.

## Tài liệu tham khảo

- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO NOTHING`, `ON CONFLICT DO UPDATE`, `EXCLUDED`, `RETURNING` và hành vi với xung đột khóa.
- [PostgreSQL — MERGE](https://www.postgresql.org/docs/current/sql-merge.html): điều kiện matched/not matched và sự khác biệt về bảo đảm cạnh tranh so với `ON CONFLICT`.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, concurrency và retry.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): khóa dòng, chờ khóa và deadlock.
- [PostgreSQL — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html): unique index, xử lý `NULL` và tính duy nhất.
- [Microsoft Learn — MERGE (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/statements/merge-transact-sql): cú pháp, lưu ý về đồng thời và giới hạn của `MERGE` trong SQL Server.
- [MySQL — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html): cú pháp xử lý trùng khóa ở MySQL.
- [SQLite — UPSERT](https://www.sqlite.org/lang_upsert.html): xử lý xung đột unique bằng các nhánh UPSERT theo SQLite.

