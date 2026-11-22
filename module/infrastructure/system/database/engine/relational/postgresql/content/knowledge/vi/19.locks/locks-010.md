# Kiểm soát cạnh tranh bằng phiên bản dữ liệu trong ứng dụng với PostgreSQL

Một ứng dụng nhiều người dùng có thể cho hai người cùng mở một đơn hàng, cùng sửa rồi lần lượt bấm **Lưu**. Cả hai thao tác có thể là câu `UPDATE` hoàn toàn hợp lệ trong PostgreSQL, nhưng nếu không có cơ chế kiểm soát cạnh tranh thì người lưu sau có thể **ghi đè thay đổi của người lưu trước** mà không nhận được bất cứ cảnh báo nào.

Ví dụ:

```text
10:00:00  A đọc đơn #101: note="Giao buổi sáng"
10:00:01  B đọc đơn #101: note="Giao buổi sáng"

10:00:10  B lưu: note="Khách đổi sang buổi chiều"
10:00:20  A lưu: note="Gọi trước khi giao"

Nếu cả hai UPDATE chỉ có WHERE order_id=101:
    Giá trị cuối có thể là "Gọi trước khi giao".
    Thay đổi của B biến mất khỏi biểu diễn hiện tại.
```

PostgreSQL có MVCC, row-level locks và các mức cô lập giao dịch, nhưng **row lock trong transaction ghi không tự cho PostgreSQL biết form của A đã được tải từ mười phút trước**. Điều cần bảo vệ là kỳ vọng của ứng dụng: *tôi chỉ muốn cập nhật nếu bản ghi chưa bị người khác sửa kể từ khi tôi đọc nó*.

Một cách phổ biến là **optimistic concurrency control** (*optimistic locking*) bằng **phiên bản dữ liệu**. Mỗi hàng chứa một cột `row_version`; lúc đọc ứng dụng nhận cả dữ liệu và version; lúc ghi ứng dụng gửi lại **expected version** và PostgreSQL kiểm tra ngay trong lệnh UPDATE.

```sql
UPDATE orders
SET note = 'Gọi trước khi giao',
    row_version = row_version + 1
WHERE order_id = 101
  AND row_version = 7
RETURNING row_version;
```

Nếu version hiện tại vẫn là 7, một hàng được cập nhật và version thành 8. Nếu người khác đã thay đổi nó thành version 8, câu UPDATE với expected version 7 sẽ cập nhật **0 hàng**. Ứng dụng phải xử lý đây là một điều kiện không khớp, thay vì báo “lưu thành công”.

Đây là bài học về **kiểm soát cạnh tranh bằng phiên bản dữ liệu trong ứng dụng** thuộc chương **Khóa** của PostgreSQL. Trọng tâm là thiết kế giao thức đọc–ghi, so khớp phiên bản nguyên tử, tình huống hai session, khác biệt với `SELECT FOR UPDATE`, xử lý conflict/retry, tích hợp API/Java/JPA, giới hạn của version trên một hàng và tính đúng khi cập nhật nhiều bảng.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân tích **lost update** và giải thích vì sao MVCC không thay thế kiểm tra phiên bản ở tầng ứng dụng.
2. So sánh optimistic locking với pessimistic locking.
3. Thiết kế cột version dùng `BIGINT NOT NULL` và quy tắc khởi tạo/tăng.
4. Viết lệnh **compare-and-swap (CAS)** bằng `UPDATE ... WHERE id = ? AND row_version = ?`.
5. Dùng `RETURNING` hoặc số hàng tác động để xác định thành công và conflict.
6. Mô phỏng hai session cùng đọc một version và chứng minh chỉ một writer có thể ghi thành công trên cùng expected version.
7. Kết hợp version với `tenant_id`, trạng thái đơn, soft delete và kiểm tra quyền.
8. Phân biệt UPDATE 0 hàng với deadlock, serialization failure và lỗi ràng buộc.
9. Thiết kế chính sách UX khi form stale: tải lại, so sánh khác biệt, merge hoặc từ chối.
10. Hiểu cách tích hợp qua JDBC, JPA `@Version`, HTTP `ETag/If-Match`.
11. Giữ outbox/audit nhất quán trong transaction và dùng idempotency cho request retry.
12. Nhận biết tình huống version trên từng hàng không bảo vệ invariant nhiều hàng.
13. Kiểm tra các đường ghi như batch job, import, admin script và ORM bulk update.
14. Thiết kế integration test hai connection với barrier và quan sát conflict rate.

Các câu DDL, INSERT, UPDATE, DELETE trong phần thực hành **chỉ dùng trên database thử nghiệm**. Nếu đã thay đổi dữ liệu của một ví dụ, cần reset lab trước khi dự đoán đầu ra của ví dụ khác.

---

## 2. Lost update: vấn đề ở đâu?

Giả sử bảng đơn hàng có dữ liệu:

| order_id | note | row_version |
| ---: | --- | ---: |
| 101 | Giao buổi sáng | 7 |

Hai trình duyệt cùng gọi API:

```text
Client A                      PostgreSQL                     Client B
   |                              |                              |
   |---- GET order #101 --------->|<-------- GET order #101 ----|
   |<--- note=morning,version=7 --|--- note=morning,version=7 -->|
   |                              |                              |
   |                              |<------- UPDATE của B --------|
   |                              |   note=afternoon, COMMIT     |
   |                              |-------- SUCCESS ------------>|
   |                              |                              |
   |------- UPDATE của A -------->|                              |
   |        từ bản đọc v7         |                              |
   |                              |                              |
   |     Không có version guard:  |                              |
   |     A ghi đè thay đổi mới.   |                              |
```

Câu UPDATE dễ gây lost update:

```sql
UPDATE orders
SET note = :new_note
WHERE order_id = :order_id;
```

Điều kiện này hỏi “hàng còn tồn tại không?”, **không hỏi “hàng còn đúng phiên bản mà client đã đọc không?”**.

### 2.1. Vì sao row lock không tự cứu được biểu mẫu cũ?

PostgreSQL dùng row-level locking khi thực thi UPDATE. Hai transaction cố thay đổi cùng hàng có thể phải chờ nhau; PostgreSQL tránh các thay đổi vật lý đồng thời không an toàn.

Tuy nhiên, một biểu mẫu thường được đọc ở transaction trước đã đóng. Người dùng có thể suy nghĩ vài phút trong browser rồi mới gửi request ghi ở transaction hoàn toàn mới. Row lock của lần đọc trước **không còn tồn tại**.

Nếu request ghi chỉ mang giá trị mới tuyệt đối, server không thể tự biết người dùng dựa trên dữ liệu cũ. Việc đưa `expected_version` vào WHERE làm rõ tiền điều kiện của thao tác.

### 2.2. Last-write-wins không phải lúc nào cũng sai

Với các cột mang tính cache hoặc thông tin có thể chấp nhận ghi sau thắng, last-write-wins có thể là contract hợp lệ. Nhưng với hồ sơ khách hàng, nội dung biên tập, trạng thái phê duyệt, thanh toán hoặc cấu hình quan trọng, ghi đè âm thầm thường gây mất quyết định của người khác.

Cơ chế version giúp biến xung đột thành **một sự kiện có thể phát hiện và xử lý**, thay vì một kết quả sai khó truy vết.

---

## 3. Optimistic locking so với pessimistic locking

| Khía cạnh | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Giả định | Xung đột tương đối hiếm; kiểm tra khi ghi | Xung đột đáng kể; giữ khóa để tuần tự hóa công việc |
| Cơ chế | `WHERE row_version = expected` | `SELECT ... FOR UPDATE`, row locks |
| Khi xảy ra xung đột | UPDATE 0 hàng hoặc lỗi transaction tùy isolation | Chờ lock, timeout, NOWAIT failure, deadlock |
| Thời gian giữ transaction | Thường chỉ trong request ghi | Trong khoảng đọc, quyết định và ghi bên trong transaction |
| Phù hợp | Form, API, người dùng chỉnh sửa lâu | Workflow ngắn cần giữ hàng trong khi kiểm tra nhiều bước |
| Đánh đổi | Cần phản hồi conflict và merge/retry | Lock contention, transaction dài và khả năng deadlock |

**Optimistic locking không có nghĩa PostgreSQL UPDATE không khóa hàng.** Đây là cách ứng dụng kiểm tra kỳ vọng phiên bản, không phải cách tắt khóa của database.

### 3.1. Không dùng FOR UPDATE xuyên thời gian chỉnh sửa của người dùng

Một form có thể mở nhiều phút. Giữ transaction và row lock lâu như vậy có thể:

- Chặn các thao tác khác.
- Chiếm connection.
- Gây lock wait và timeout.
- Góp phần giữ snapshot/tuple cũ.
- Khó phục hồi khi client mất mạng hoặc đóng tab.

Cách phổ biến: **đọc dữ liệu cùng version, đóng transaction, rồi dùng CAS khi client gửi lưu**.

### 3.2. Có thể kết hợp cả hai

Một ứng dụng có thể dùng optimistic version ở tầng API, nhưng bên trong transaction ghi còn dùng row lock cho bảng liên quan. Ví dụ, chuyển trạng thái đơn và trừ tồn kho có thể cần nhiều điều kiện và khóa ngắn. Hai cơ chế bổ sung cho nhau, không loại trừ nhau.

---

## 4. Thiết kế cột phiên bản

Schema tối thiểu:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version > 0)
);
```

Các quy tắc:

- Khởi tạo version bằng một giá trị thống nhất (thường 0 hoặc 1).
- Mỗi thay đổi cần bảo vệ phải tăng version.
- **Không reset/reuse version** trong vòng đời của một đối tượng.
- Version cần đi kèm định danh bản ghi, không cần unique toàn hệ thống.
- Tăng version **trong cùng statement hoặc transaction thích hợp** với thay đổi dữ liệu.
- Trả version mới cho client sau khi commit thành công.

### 4.1. Tại sao dùng BIGINT?

`BIGINT` cung cấp miền số nguyên có dấu rất rộng. Với phần lớn bản ghi nghiệp vụ, nó đủ cho số lần cập nhật trong vòng đời hệ thống. Tuy nhiên nó vẫn có giới hạn; không nên dựa vào hành vi tự quay vòng khi overflow.

### 4.2. Tại sao không chỉ dùng updated_at?

Timestamp có nhiều vấn đề khi làm token cạnh tranh:

- `now()` của PostgreSQL cố định theo **thời điểm bắt đầu transaction**, nhiều UPDATE trong cùng transaction có thể nhận cùng giá trị.
- Độ chính xác timestamp có thể bị cắt khi qua JSON, Java, JavaScript hoặc hệ thống khác.
- Hai thay đổi rất gần nhau có thể tạo giá trị thời gian không phân biệt được theo cách ứng dụng lưu/truyền.
- Trigger/migration có thể đặt updated_at theo cách khác.
- Timestamp mô tả thời gian, không bảo đảm mỗi lần sửa đều tạo một phiên bản logic mới.

Giữ `updated_at` cho audit và hiển thị; dùng `row_version` hoặc token opaque có hợp đồng rõ ràng cho CAS.

### 4.3. Vì sao không dùng xmin hoặc ctid làm token ứng dụng lâu dài?

PostgreSQL có system columns `xmin`, `xmax`, `ctid`. Tuy nhiên:

- `xmin` liên quan transaction tạo tuple, với cơ chế transaction ID, freeze và vòng đời nội bộ.
- `ctid` là vị trí vật lý của tuple version, có thể đổi sau UPDATE hoặc rewrite.
- Chúng không phải mã version nghiệp vụ ổn định xuyên các loại migration/replication.
- Chúng khó phối hợp với API contract và quản lý phiên bản ngoài database.

Có những thư viện tận dụng metadata hệ thống trong phạm vi riêng, nhưng thiết kế ứng dụng tổng quát nên ưu tiên **cột version do hệ thống kiểm soát**.

---

## 5. Tạo bộ dữ liệu thực hành PostgreSQL

Bộ lab có hai tenant, để học cả kiểm soát phiên bản và phạm vi khóa nghiệp vụ.

> **Cảnh báo:** Những lệnh `DROP TABLE IF EXISTS` dưới đây xóa dữ liệu bảng thực hành có cùng tên. Chỉ chạy trong database riêng được phép reset; không chạy ở production.

### 5.1. Schema orders

```sql
CREATE SCHEMA IF NOT EXISTS optimistic_lock_lab;

DROP TABLE IF EXISTS optimistic_lock_lab.order_outbox;
DROP TABLE IF EXISTS optimistic_lock_lab.orders;

CREATE TABLE optimistic_lock_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, order_id)
);
```

PRIMARY KEY là **(tenant_id, order_id)**, cho phép các tenant có số order_id giống nhau. Điều kiện UPDATE phải sử dụng **đủ khóa**; xác thực tenant phải dựa vào identity được server tin cậy, không dựa vào một trường client tự khai tùy ý.

### 5.2. Nạp dữ liệu

```sql
INSERT INTO optimistic_lock_lab.orders (
    tenant_id, order_id, status, amount, note, row_version
)
VALUES
    (10, 101, 'DRAFT', 100.00, 'Giao buổi sáng', 1),
    (10, 102, 'DRAFT',  50.00, 'Đóng gói', 1),
    (10, 103, 'PAID',  150.00, 'Đã thanh toán', 1),
    (20, 101, 'DRAFT',  70.00, 'Đơn tenant khác', 1);

SELECT tenant_id, order_id, status, note, row_version
FROM optimistic_lock_lab.orders
ORDER BY tenant_id, order_id;
```

Ban đầu mỗi bản ghi có `row_version=1`. Các ví dụ có ghi dữ liệu sẽ làm version tăng; khi thực hành nhiều ví dụ độc lập, hãy reset lab ở đầu phần này.

### 5.3. Outbox phục vụ ví dụ nâng cao

```sql
CREATE TABLE optimistic_lock_lab.order_outbox (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    resulting_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES optimistic_lock_lab.orders(tenant_id, order_id)
);
```

Bảng outbox chỉ dùng để minh họa tính nguyên tử giữa thay đổi đơn và sự kiện. Nó chưa phải toàn bộ hệ thống xử lý message, vì thiếu claim, retry, deduplication và trạng thái gửi.

---

## 6. Câu SQL trọng tâm: compare-and-swap

Câu UPDATE đúng:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Gọi trước khi giao',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING
    o.tenant_id,
    o.order_id,
    o.note,
    o.row_version,
    o.updated_at;
```

Với dữ liệu ban đầu, câu lệnh cập nhật một hàng, note mới được lưu và version thành **2**.

### 6.1. Vì sao phải kiểm tra trong WHERE?

Nếu viết:

```text
SELECT row_version
So sánh expectedVersion bằng code
UPDATE orders SET note=... WHERE order_id=...
```

có **khoảng trống cạnh tranh** giữa kiểm tra và sử dụng. Writer khác có thể UPDATE sau câu SELECT nhưng trước câu UPDATE của bạn.

Khi viết:

```sql
UPDATE ...
WHERE order_id = :id
  AND row_version = :expected_version;
```

PostgreSQL kiểm tra điều kiện trên hàng cần cập nhật như một phần của operation ghi. Cùng với row locking và MVCC, điều này bảo vệ không có hai cập nhật CAS cùng thành công trên một phiên bản cũ của **cùng hàng** theo những điều kiện áp dụng.

### 6.2. Vì sao tăng version trong cùng UPDATE?

Cách sai:

```sql
UPDATE orders SET note = :new_note WHERE order_id = :id;
UPDATE orders SET row_version = row_version + 1 WHERE order_id = :id;
```

Hai statement tách rời có thể khiến một thao tác thành công còn thao tác kia thất bại, hoặc writer khác xen vào nếu không được bảo vệ bằng transaction/lock đúng cách.

Gộp lại:

```sql
UPDATE orders
SET note = :new_note,
    row_version = row_version + 1
WHERE order_id = :id
  AND row_version = :expected_version
RETURNING row_version;
```

Việc kiểm tra version và thay đổi dữ liệu được thực hiện **nguyên tử ở mức câu UPDATE**.

### 6.3. Chạy lại cùng expected version

Nếu version đã thành 2, chạy lại cùng câu với điều kiện `row_version=1`:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Gọi trước khi giao',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.row_version;
```

sẽ trả **0 hàng**. Đây là kết quả của điều kiện không còn khớp; không phải lỗi cú pháp hay lỗi PostgreSQL tự ném.

### 6.4. Vì sao SET version = row_version + 1?

Nếu WHERE đã bảo đảm expected version, phép tính `expected_version+1` có thể cho cùng kết quả. Nhưng lấy `row_version` hiện có làm nguồn tăng giúp câu SQL tự thể hiện rõ “version mới = version đang lưu + 1”, tránh lỗi bind nhầm tham số.

---

## 7. Thí nghiệm hai session: phát hiện stale update

Mở hai kết nối PostgreSQL **thực sự độc lập**. Nếu đã sửa order 101 trong phần trước, reset lab bằng INSERT ban đầu trước khi thử.

### 7.1. Session A đọc

```sql
-- SESSION A
SELECT tenant_id, order_id, note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

A nhận:

```text
note="Giao buổi sáng"
row_version=1
```

A đang sửa form và định lưu note `"Gọi trước khi giao"`.

### 7.2. Session B đọc cùng phiên bản

```sql
-- SESSION B
SELECT tenant_id, order_id, note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

B cũng nhận version 1 và định lưu `"Giao buổi chiều"`.

### 7.3. B ghi trước

```sql
-- SESSION B
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Giao buổi chiều',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.note, o.row_version;
```

Khi autocommit thành công, kết quả là một hàng với version **2**.

### 7.4. A lưu form cũ

```sql
-- SESSION A
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Gọi trước khi giao',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.note, o.row_version;
```

A được trả **0 hàng** vì version thực tế đã khác 1.

Kiểm tra:

```sql
SELECT note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

Dữ liệu vẫn là:

```text
note="Giao buổi chiều"
row_version=2
```

**Kết quả mong muốn:** thay đổi của B được bảo vệ, A nhận xung đột để lựa chọn tải lại hoặc merge, không âm thầm ghi đè.

### 7.5. Nếu cả hai UPDATE bắt đầu cùng lúc?

Khi hai transaction cạnh tranh cập nhật cùng hàng:

1. Một transaction có thể giữ row lock trước.
2. Transaction kia chờ hoặc nhận lỗi nếu có chính sách timeout/NOWAIT phù hợp.
3. Khi writer trước commit, writer sau xử lý theo quy tắc visibility/isolation.
4. Với `READ COMMITTED` và CAS version cũ, writer sau thường sẽ không còn khớp WHERE, dẫn tới **0 hàng**.
5. Với isolation cao hơn, một số lịch có thể gây **serialization failure** thay vì 0 hàng.

Ứng dụng phải xử lý cả xung đột version lẫn lỗi transaction khi có cạnh tranh.

---

## 8. UPDATE 0 hàng không phải lúc nào cũng là version conflict

Xét câu:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET status = 'PAID',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
  AND o.status = 'DRAFT'
RETURNING o.row_version;
```

Nếu không trả hàng nào, có nhiều nguyên nhân:

- Tài nguyên không tồn tại.
- Sai tenant.
- Không được phép nhìn hoặc cập nhật hàng theo RLS.
- Version đã khác.
- Status không phải DRAFT.
- Bản ghi đã bị xóa.
- Điều kiện nghiệp vụ khác không còn đúng.

Do đó, **0 hàng = không khớp tất cả điều kiện**, chưa đủ để khẳng định nguyên nhân duy nhất.

### 8.1. Phân loại trong phạm vi quyền

Một ứng dụng có thể đọc lại bản ghi theo quyền được xác thực để đưa ra thông điệp rõ hơn. Tuy nhiên:

- Việc đọc lại diễn ra ở thời điểm mới, có thể có writer khác tiếp tục sửa.
- Không dùng truy vấn phân loại nguyên nhân để tiết lộ tài nguyên tenant khác.
- Không xem kết quả đọc lại là snapshot nguyên tử với UPDATE vừa thất bại.
- Không trả mã HTTP sai chỉ vì tất cả nguyên nhân được xử lý chung trong repository.

### 8.2. Dùng RETURNING

`RETURNING` trả các trường của những hàng thực sự được cập nhật:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Đã xác minh',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
RETURNING o.order_id, o.note, o.row_version;
```

- Đúng một hàng: cập nhật thành công theo điều kiện.
- 0 hàng: không khớp.
- Nhiều hàng: với WHERE theo PRIMARY KEY chính xác, không được xảy ra.

Không chỉ kiểm tra “SQL không báo lỗi” rồi báo lưu thành công.

---

## 9. Phiên bản và trạng thái nghiệp vụ là hai kiểm tra khác nhau

Ví dụ vòng đời đơn hàng:

```text
DRAFT ------> PAID
   |
   +--------> CANCELED

PAID -X-> DRAFT (bị cấm theo ví dụ)
CANCELED -X-> PAID
```

Câu UPDATE chuyển trạng thái:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET status = 'PAID',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
  AND o.status = 'DRAFT'
RETURNING o.status, o.row_version;
```

Hai predicate quan trọng:

- `row_version = expected`: phát hiện client sử dụng snapshot cũ.
- `status='DRAFT'`: thực thi rule chỉ được chuyển DRAFT → PAID.

Nếu bỏ status guard, một client có phiên bản mới vẫn có thể tạo chuyển trạng thái không hợp lệ. Nếu bỏ version guard, client giữ bản nháp cũ không được cảnh báo những thay đổi liên quan.

### 9.1. Đừng quên tenant_id

Hai tenant có thể cùng `order_id=101` và `row_version=1`. Nếu UPDATE chỉ WHERE order_id + version, có thể tác động nhiều hàng.

Dùng khóa chính đầy đủ:

```sql
WHERE tenant_id = :authenticated_tenant
  AND order_id = :order_id
  AND row_version = :expected_version
```

Tenant phải xuất phát từ ngữ cảnh xác thực đáng tin cậy. Version không phải secret credential và không thay authorization.

### 9.2. Business rule có thể cần ràng buộc DB

Các điều kiện như `amount >= 0`, uniqueness, foreign key nên được bảo vệ bằng `CHECK`, `UNIQUE`, `FOREIGN KEY` phù hợp. Version predicate không thay tính toàn vẹn dữ liệu.

---

## 10. Tăng version cho mọi thay đổi được bảo vệ

Một lỗi rất phổ biến: REST API dùng CAS, nhưng scheduled job hoặc admin script sửa hàng **không tăng row_version**.

Ví dụ:

```sql
-- Thiếu tăng version.
UPDATE optimistic_lock_lab.orders
SET status = 'CANCELED'
WHERE tenant_id = 10 AND order_id = 102;
```

Sau câu này, một client đã mở form ở version 1 có thể vẫn gửi CAS version 1 và thành công dù status đã đổi. Giao thức optimistic lock bị thủng.

### 10.1. Những writer cần rà soát

```text
REST / GraphQL mutations
Admin console
Scheduled jobs
Queue consumers
Import và backfill scripts
Native SQL / stored procedures
ORM bulk updates
Support tools
Database migrations
```

Tất cả những đường ghi làm thay đổi dữ liệu client cần nhận biết phải thống nhất chính sách version.

### 10.2. Version có tăng cho no-op UPDATE?

Tùy contract:

- Nếu mỗi request xác nhận ghi cần làm stale client khác bị từ chối, có thể tăng cả khi giá trị không thay đổi.
- Nếu không muốn tạo tuple mới khi dữ liệu bằng nhau, có thể dùng `IS DISTINCT FROM` để tránh no-op update.
- Nếu phải ghi audit mọi yêu cầu xác nhận, tránh UPDATE cũng có thể làm mất trigger/event.

Ví dụ chỉ cập nhật note khi thực sự đổi:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'verified',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
  AND o.note IS DISTINCT FROM 'verified'
RETURNING o.row_version;
```

0 hàng lúc này còn có thể là note đã bằng `verified`, **không nhất thiết stale version**. Phải xác định ngữ nghĩa API khi no-op.

### 10.3. Trigger quản lý version có được không?

Có thể thiết kế trigger tự tăng version khi UPDATE. Nhưng cần tránh:

- ORM tự tăng version rồi trigger cũng tăng.
- Trigger chỉ tăng một số trường, bỏ sót trường quan trọng.
- Một số native/bulk writer không còn khớp cơ chế ORM.
- Ứng dụng hiểu sai token được `RETURNING` trả về.

Chọn một chiến lược rõ ràng: version do SQL/ORM quản lý hoặc do trigger quản lý nhất quán, rồi kiểm thử mọi đường ghi. Trigger chỉ tăng version **không tự phát hiện stale client** nếu câu UPDATE bỏ điều kiện expected version.

---

## 11. READ COMMITTED và câu UPDATE CAS

`READ COMMITTED` là isolation level mặc định của PostgreSQL. Các statement thường dùng snapshot tại đầu statement, nhưng UPDATE có quy tắc chờ lock và đánh giá lại điều kiện với hàng đã bị transaction khác cập nhật.

Ví dụ hai writer cùng expected version 4:

```text
A: UPDATE WHERE version=4 -> khóa hàng
B: UPDATE WHERE version=4 -> đợi A

A: ghi version=5 và COMMIT

B: tiếp tục, điều kiện version=4 không còn khớp
B: UPDATE 0 hàng
```

B không tự ghi đè chỉ vì nó đã bắt đầu chờ từ lúc version còn 4.

### 11.1. MVCC không thể đoán ý định client

Nếu B dùng:

```sql
UPDATE orders SET note='old draft value' WHERE id=101;
```

thì sau khi chờ A, B vẫn có thể ghi thành công theo điều kiện hiện có. Row locking bảo vệ storage consistency nhưng **không bảo vệ ý định người dùng** khi UPDATE thiếu version guard.

### 11.2. REPEATABLE READ/SERIALIZABLE

Trong isolation level cao hơn, một UPDATE đụng hàng bị transaction khác sửa sau snapshot có thể phát sinh `SQLSTATE 40001` (*serialization_failure*) thay vì chỉ UPDATE 0 hàng.

Ứng dụng cần:

- Rollback transaction đã thất bại.
- Retry **toàn bộ transaction** khi nghiệp vụ cho phép, không chỉ chạy lại một statement cũ.
- Giới hạn số lần retry và backoff.
- Không tự làm lại một form stale bằng payload cũ sau khi đổi expected version mà không merge/đánh giá lại.

---

## 12. Optimistic locking không thay atomic UPDATE

Một số bài toán tốt nhất được diễn đạt bằng phép toán trực tiếp trong SQL.

Ví dụ tăng một bộ đếm:

**Cách dễ lost update:**

```text
Client A đọc stock=10
Client B đọc stock=10
A tính 11, UPDATE stock=11
B tính 11, UPDATE stock=11
Mất một lần tăng.
```

**Cách nguyên tử:**

```sql
-- Mẫu với bảng inventory giả định, không có trong lab.
UPDATE inventory
SET stock = stock + 1
WHERE sku = 'SKU-A'
RETURNING stock;
```

Nếu nghiệp vụ chỉ là tăng thêm 1, PostgreSQL có thể xử lý phép tăng trực tiếp an toàn trên hàng. Không nhất thiết phải kéo giá trị ra client rồi CAS để tính lại.

### 12.1. Điều kiện giới hạn cần nằm trong UPDATE

Để giảm tồn kho khi còn hàng:

```sql
UPDATE inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
  AND stock >= 1
RETURNING stock;
```

Điều kiện `stock >= 1` nằm **trong câu ghi**, tránh race giữa SELECT kiểm tra tồn kho và UPDATE.

### 12.2. Khi nào vẫn cần version?

Nếu người dùng đang đặt **giá trị tuyệt đối** mới dựa trên snapshot cũ, hoặc cập nhật một tập trường có liên hệ nghiệp vụ, optimistic version giúp phát hiện stale form.

Nếu phép toán có tính cộng dồn và có thể gộp an toàn theo contract, atomic UPDATE có thể đơn giản hơn. Hai kỹ thuật có thể kết hợp khi cần.

---

## 13. Xung đột cần được phản hồi đúng cho người dùng

Sau khi CAS thất bại do version mismatch, ứng dụng có thể:

1. **Từ chối và yêu cầu tải lại:** an toàn cho tác vụ quan trọng.
2. **Hiển thị diff:** bản đang lưu, bản người dùng đã mở và thay đổi dự kiến.
3. **Cho phép merge có kiểm soát:** khi các trường độc lập theo nghiệp vụ.
4. **Tự retry một thao tác có thể gộp:** chỉ khi chứng minh được an toàn.

Ví dụ thông báo:

```text
Không thể lưu vì đơn hàng đã được cập nhật bởi một thao tác khác.

Phiên bản bạn đang chỉnh: 7
Phiên bản hiện tại: 8

Vui lòng tải lại và so sánh thay đổi trước khi lưu tiếp.
```

### 13.1. Anti-pattern: đọc version mới rồi ghi lại nguyên payload cũ

```text
UPDATE WHERE version=7 -> 0 rows
SELECT version -> 8
UPDATE WHERE version=8, payload vẫn là form cũ -> thành công
```

Đây thực chất là **bỏ qua conflict**. Thay đổi của người khác có thể bị ghi đè mà không được review.

Auto-retry chỉ nên làm khi thao tác và invariant cho phép, ví dụ phép cộng một số lượng đã được xác định an toàn. Với đổi trạng thái, ghi chú hay thông tin thanh toán, ứng dụng thường phải tải lại rồi đánh giá ý định.

### 13.2. Merge theo field không luôn an toàn

A sửa note, B sửa amount. Dù hai người không sửa cùng cột, note có thể chứa cam kết về amount. Merge tự động có thể tạo một trạng thái chưa ai duyệt.

Cần định nghĩa rõ field nào độc lập, field nào thuộc cùng invariant, và khi nào phải yêu cầu người dùng xác nhận.

---

## 14. HTTP ETag và If-Match

Một API REST có thể trả version qua ETag:

```http
GET /tenants/10/orders/101 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-101-v7"

{
  "orderId": 101,
  "status": "DRAFT",
  "note": "Giao buổi sáng",
  "version": 7
}
```

Client gửi lại khi lưu:

```http
PUT /tenants/10/orders/101 HTTP/1.1
If-Match: "order-101-v7"
Content-Type: application/json

{
  "status": "DRAFT",
  "note": "Gọi trước khi giao"
}
```

Server cần:

1. Xác thực caller và scope tenant.
2. Kiểm tra precondition token theo contract.
3. Sử dụng version tương ứng trong CAS UPDATE.
4. Kiểm tra row count/RETURNING.
5. COMMIT thành công.
6. Trả ETag/version mới hoặc lỗi phù hợp.

### 14.1. HTTP status thường dùng

| Trường hợp | HTTP status thường phù hợp |
| --- | --- |
| GET thành công | `200 OK`, có ETag |
| Ghi thành công | `200 OK` hoặc `204 No Content` |
| If-Match không còn khớp | `412 Precondition Failed` |
| API yêu cầu precondition nhưng thiếu | `428 Precondition Required` |
| Chuyển trạng thái vi phạm nghiệp vụ | `409 Conflict` hoặc mã theo API contract |
| Không thấy tài nguyên trong phạm vi được phép | `404 Not Found` |
| Không được phép thao tác | `403 Forbidden` hoặc chính sách không tiết lộ tồn tại |

Khi API dùng trường version trong JSON mà không dùng HTTP If-Match, nhiều hệ thống dùng 409 cho conflict. PostgreSQL không tự quyết định HTTP status.

### 14.2. ETag mạnh và tính opaque

`If-Match` sử dụng ngữ nghĩa strong comparison. Một weak ETag không phải token tương đương cho điều kiện If-Match. ETag có thể là chuỗi opaque, miễn server gắn nó với representation/version có hợp đồng rõ.

Version/ETag **không phải credential bảo mật**. Biết ETag của order không làm người gọi có quyền cập nhật order đó.

### 14.3. Không chỉ kiểm tra If-Match ở code rồi UPDATE trần

Sai:

```text
SELECT current ETag
if equal:
    UPDATE orders SET ...
```

Writer khác có thể thay đổi hàng giữa hai bước. Luôn có điều kiện CAS ở database hoặc dùng cơ chế transaction/locking tương đương được thiết kế chính xác.

---

## 15. Java JDBC: PreparedStatement với RETURNING

Trong Java, có thể triển khai repository theo mẫu sau.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderRepository {

    // Trả null nếu điều kiện CAS không khớp.
    public Long updateNote(
            Connection connection,
            int tenantId,
            long orderId,
            long expectedVersion,
            String newNote) throws SQLException {

        String sql = """
            UPDATE optimistic_lock_lab.orders
            SET note = ?,
                row_version = row_version + 1,
                updated_at = clock_timestamp()
            WHERE tenant_id = ?
              AND order_id = ?
              AND row_version = ?
            RETURNING row_version
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {

            ps.setString(1, newNote);
            ps.setInt(2, tenantId);
            ps.setLong(3, orderId);
            ps.setLong(4, expectedVersion);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }

                long newVersion = rs.getLong("row_version");

                if (rs.next()) {
                    throw new SQLException(
                        "Unexpected multiple rows for one order");
                }

                return newVersion;
            }
        }
    }
}
```

Ví dụ dùng Java text block (Java 15+). Với Java cũ, dùng chuỗi thông thường.

### 15.1. Phân biệt repository và service transaction

Nếu một nghiệp vụ phải UPDATE đơn rồi INSERT outbox/audit, transaction nên ở tầng service:

```text
Service transaction
    |
    +--> CAS UPDATE order
    |       |
    |       +--> no row: rollback/conflict
    |
    +--> INSERT outbox
    +--> kiểm tra các invariants khác
    |
    +--> COMMIT
```

Repository không nên tự COMMIT từng phần nếu service cần nguyên tử nhiều thao tác.

### 15.2. Không xác nhận thành công trước COMMIT

Ngay cả khi `RETURNING` trả version mới, transaction vẫn có thể thất bại khi COMMIT (ví dụ constraints deferred hoặc lỗi concurrency). Chỉ gửi “đã lưu” cho client sau khi commit theo contract.

### 15.3. Không nối giá trị user vào chuỗi SQL

Dùng bind parameters. Không viết:

```java
String sql = "UPDATE orders SET note='" + userNote
        + "' WHERE order_id=" + orderId;
```

vì lỗi quoting, SQL injection và nhầm kiểu.

---

## 16. JPA/Hibernate: @Version

Nhiều ORM Java có cơ chế optimistic locking qua `@Version`.

Ví dụ entity với khóa đơn giản:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "application_orders")
public class OrderEntity {

    @Id
    private Long orderId;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long rowVersion;

    private String status;
    private BigDecimal amount;
    private String note;
}
```

**Lưu ý:** Đây là mapping ví dụ cho bảng `application_orders` khóa đơn. Bảng lab có khóa ghép `(tenant_id,order_id)`, nên khi map trực tiếp vào lab phải dùng chiến lược khóa ghép như `@EmbeddedId`/`@IdClass` và đảm bảo tenant scope.

### 16.1. ORM thường làm gì?

Ý tưởng SQL do ORM tạo:

```sql
UPDATE application_orders
SET note = ?,
    row_version = ?
WHERE order_id = ?
  AND row_version = ?;
```

ORM kiểm tra số hàng tác động. Khi version không còn khớp, framework có thể ném `OptimisticLockException` hoặc wrapper tương ứng. Lỗi có thể chỉ xuất hiện lúc `flush()` hoặc transaction COMMIT, không nhất thiết ngay khi gọi setter.

### 16.2. Đừng tự tăng version khi ORM quản lý

Nếu ORM đã quản lý version:

- Không tự set phiên bản lên +1 tùy tiện.
- Không cho bulk native SQL bỏ qua việc tăng version.
- Không trộn hai cơ chế tăng version của ORM và trigger mà chưa có thiết kế chung.
- Không bỏ qua ngoại lệ optimistic lock trong service.

### 16.3. Bulk update là một điểm rủi ro

Một lệnh:

```sql
UPDATE application_orders
SET status = 'CANCELED'
WHERE status = 'DRAFT';
```

có thể bypass cơ chế version của entity manager nếu chạy như native SQL/bulk update. Nếu version không tăng, các entity/bản nháp cũ vẫn có token đang khớp.

Mọi writer, kể cả migration, job và admin script, phải tuân thủ quy tắc đã chọn.

---

## 17. Transactional outbox: cập nhật và tạo sự kiện cùng nhau

Giả sử chuyển đơn sang PAID phải phát sự kiện `OrderPaid`.

Nếu gọi message broker **trước COMMIT**, database có thể rollback nhưng sự kiện đã phát. Nếu COMMIT trước rồi mới phát, server có thể crash giữa hai bước và mất sự kiện.

Một phương án là **transactional outbox**: ghi sự kiện vào bảng DB cùng transaction với CAS.

```sql
BEGIN;

WITH changed AS (
    UPDATE optimistic_lock_lab.orders AS o
    SET status = 'PAID',
        row_version = o.row_version + 1,
        updated_at = clock_timestamp()
    WHERE o.tenant_id = 10
      AND o.order_id = 101
      AND o.row_version = 1
      AND o.status = 'DRAFT'
    RETURNING
        o.tenant_id, o.order_id,
        o.status, o.row_version
)
INSERT INTO optimistic_lock_lab.order_outbox (
    tenant_id, order_id, event_type,
    resulting_version, payload
)
SELECT
    tenant_id,
    order_id,
    'OrderPaid',
    row_version,
    jsonb_build_object(
        'status', status,
        'version', row_version
    )
FROM changed
RETURNING event_id, order_id, resulting_version;

COMMIT;
```

Nếu CAS không khớp, CTE changed trả 0 hàng và INSERT outbox **không thêm event**. Ứng dụng vẫn phải kiểm tra rằng thao tác cần thiết đã cập nhật đúng một hàng trước khi báo thành công.

Nếu INSERT outbox thất bại và transaction rollback, UPDATE order cũng được rollback. Đó là giá trị của **một transaction**.

### 17.1. Outbox không tự bảo đảm gửi đúng một lần

Worker gửi thông điệp có thể crash sau khi gửi nhưng trước khi ghi nhận đã gửi. Lần retry có thể gửi trùng. Consumer cần idempotency/deduplication hoặc cơ chế tương đương.

Có thể đính kèm `tenant_id`, `order_id`, `row_version` vào event để hỗ trợ theo dõi thứ tự, nhưng version không tự giải quyết mọi vấn đề phân phối thông điệp.

### 17.2. Không gọi API ngoài khi đang giữ row lock lâu

Nếu CAS UPDATE đã khóa hàng rồi transaction còn chờ HTTP request từ hệ thống khác, lock/connection bị giữ lâu và có thể làm conflict/latency tăng. Outbox giúp tách transaction ghi ngắn khỏi phần gửi message bất đồng bộ.

---

## 18. Idempotency không đồng nghĩa optimistic locking

**Optimistic locking:** ngăn một request ghi dựa trên version cũ.

**Idempotency:** ngăn cùng operation nghiệp vụ bị thực hiện hai lần khi request được gửi lại.

Ví dụ:

```text
Client gửi yêu cầu thanh toán.
Server CAS và COMMIT thành công.
Response bị mất vì timeout.

Client gửi lại cùng request.
Expected version cũ -> UPDATE 0 hàng.
```

Client không thể chỉ từ conflict biết lần thanh toán trước **đã thành công** hay thất bại do người khác thay đổi.

### 18.1. Idempotency key

Ứng dụng có thể lưu request key cùng kết quả, dùng unique constraint:

```sql
-- Schema minh họa, không cần tạo trong lab chính.
CREATE TABLE processed_requests (
    tenant_id INTEGER NOT NULL,
    request_id UUID NOT NULL,
    operation TEXT NOT NULL,
    response_payload JSONB,
    PRIMARY KEY (tenant_id, request_id)
);
```

Khi request_id cũ xuất hiện lại, hệ thống có thể tra cứu kết quả đã commit thay vì thực hiện lại nghiệp vụ. Nếu cùng key dùng cho payload khác, cần reject theo contract.

Việc claim key và thay đổi dữ liệu phải có thiết kế transaction/uniqueness phù hợp để hai retry đồng thời không cùng xử lý.

### 18.2. Version không phải idempotency key

Version 7 có thể được hai thao tác khác nhau đọc cùng lúc; nó không đại diện duy nhất cho một yêu cầu thanh toán. Trong hệ thống cần cả chống stale update lẫn chống xử lý trùng, dùng **cả hai cơ chế**.

---

## 19. Soft delete và DELETE theo phiên bản

Nhiều hệ thống dùng soft delete:

```text
deleted_at IS NULL       -> đang hoạt động
deleted_at IS NOT NULL   -> đã soft-delete
```

Đó là một **UPDATE**, nên cũng phải tăng version theo policy.

Ví dụ trên một bảng giả định có `deleted_at`:

```sql
UPDATE application_orders AS o
SET deleted_at = clock_timestamp(),
    row_version = row_version + 1
WHERE o.tenant_id = :tenant_id
  AND o.order_id = :order_id
  AND o.row_version = :expected_version
  AND o.deleted_at IS NULL
RETURNING o.row_version;
```

Nếu B soft-delete trong lúc A mở form, A không được tự “hồi sinh” hàng vì thiếu kiểm tra điều kiện.

### 19.1. Physical DELETE cũng có thể conditional

Trên bảng lab:

```sql
DELETE FROM optimistic_lock_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
RETURNING o.order_id, o.row_version;
```

Câu này xóa hàng **chỉ nếu version còn khớp**. Nếu người khác đã sửa, DELETE 0 hàng giúp tránh xóa một phiên bản mới hơn mà client chưa nhìn thấy.

Chỉ thực hành trên lab; trong production phải xét FK, audit, retention, quyền và các hệ quả của xóa vật lý.

### 19.2. DELETE idempotent khác conditional DELETE

Một endpoint DELETE có thể hứa hẹn trạng thái cuối là “không còn bản ghi” dù client gọi lại nhiều lần. Conditional DELETE lại yêu cầu token phiên bản phải khớp.

Không đồng nhất hai contract. Với thao tác nhạy cảm, có thể yêu cầu If-Match để đảm bảo người dùng chỉ xóa phiên bản họ đã xác nhận.

---

## 20. Version không phải giải pháp cho invariant nhiều hàng

Một vấn đề điển hình là **write skew**.

Giả sử bệnh viện yêu cầu “luôn phải có ít nhất một bác sĩ trực”. Hai bác sĩ A và B đều đang trực:

```text
T1 đọc: A=on, B=on
T2 đọc: A=on, B=on

T1 UPDATE hàng A: on_call=false, version 3->4
T2 UPDATE hàng B: on_call=false, version 5->6

Hai hàng khác nhau, version riêng không xung đột.
Kết quả: không còn ai trực.
```

CAS chỉ bảo vệ **hàng mà request kiểm tra version**. Nếu invariant trải qua nhiều hàng, phiên bản từng hàng có thể không đủ.

### 20.1. Hướng giải quyết

Tùy mô hình:

- Dùng `SERIALIZABLE` và retry toàn transaction khi có serialization failure.
- Khóa một hàng điều phối chung.
- Đặt aggregate root version mà mọi thay đổi liên quan bắt buộc cùng claim.
- Dùng constraints nếu invariant có thể biểu diễn được.
- Row locking theo thứ tự ổn định trong transaction ngắn.
- Thiết kế lại mô hình dữ liệu để invariant có thể được bảo vệ atomically.

Không tuyên bố “mọi bảng có row_version thì hệ thống không còn race”.

---

## 21. Aggregate root version cho nhiều bảng

Giả sử một order có nhiều order_items. Hai người sửa hai item khác nhau, nhưng business invariant là tổng tiền của cả order không vượt hạn mức.

Nếu chỉ version từng item, cả hai sửa có thể cùng thành công mà tổng vi phạm.

Một mô hình dùng version ở **order root**:

```sql
BEGIN;

-- Claim version của aggregate root.
UPDATE orders
SET row_version = row_version + 1
WHERE order_id = :order_id
  AND row_version = :expected_version
RETURNING row_version;

-- Nếu không đúng một hàng: ROLLBACK.
-- Nếu đúng một hàng: sửa order_items, tính lại tổng,
-- kiểm tra business invariants, ghi outbox nếu cần.

COMMIT;
```

Những bảng trên là mẫu khái niệm. Để vận hành thật còn cần khóa tenant, quyền, FK, xử lý lỗi transaction và các ràng buộc phù hợp.

### 21.1. Vì sao claim root version trước sửa child?

Hai transaction cùng sửa items của một order phải cùng cạnh tranh trên **một hàng root**. Nếu root version không được cập nhật trong cùng transaction với child, một writer có thể sửa items mà client khác không phát hiện là phiên bản aggregate đã thay đổi.

### 21.2. Nếu chỉ một phần child thay đổi?

Cần quy định rõ:

- Thay đổi nào thuộc aggregate.
- Thay đổi nào bắt buộc bump root version.
- Field nào được merge độc lập.
- Có cần bảo vệ invariant ở database không.

Thiết kế version theo phạm vi quá rộng có thể tạo conflict không cần thiết; quá hẹp có thể bỏ sót xung đột quan trọng.

---

## 22. Batch UPDATE với nhiều expected versions

Giả sử client muốn cập nhật hai đơn với expected versions khác nhau. Một UPDATE chỉ theo `IN (101,102)` không bảo vệ riêng từng token.

Có thể dùng CTE `VALUES`:

```sql
WITH expected(tenant_id, order_id, row_version) AS (
    VALUES
        (10, 101::BIGINT, 1::BIGINT),
        (10, 102::BIGINT, 1::BIGINT)
)
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Batch checked',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
FROM expected AS e
WHERE o.tenant_id = e.tenant_id
  AND o.order_id = e.order_id
  AND o.row_version = e.row_version
RETURNING o.tenant_id, o.order_id, o.row_version;
```

Chỉ những hàng khớp cả khóa lẫn expected version được cập nhật.

### 22.1. Thành công một phần

Nếu một trong hai order đã đổi version, UPDATE có thể chỉ tác động hàng còn khớp. PostgreSQL không tự rollback toàn batch vì một hàng không khớp WHERE.

Nếu nghiệp vụ yêu cầu **all-or-nothing**, chạy trong transaction, kiểm tra đủ số và tập khóa được cập nhật, rồi ROLLBACK nếu có bất kỳ hàng nào thiếu.

### 22.2. Chú ý duplicate trong nguồn UPDATE FROM

Nếu CTE expected có hai dòng cùng `(tenant_id,order_id)`, JOIN có nhiều match cho một target row. PostgreSQL không hứa chọn hàng nguồn theo quy tắc bạn muốn. Nên validate input unique hoặc nạp vào staging table có PRIMARY KEY.

### 22.3. Thực thi batch không có nghĩa bỏ version

Các job backfill, SQL migration và admin scripts vẫn phải tăng version khi thay đổi representation mà client có thể đang chỉnh sửa. Nếu không, optimistic protection của API bị thủng.

---

## 23. UPSERT và version guard

`INSERT ... ON CONFLICT DO UPDATE` giải quyết tranh chấp khóa unique khi chèn, **không tự giải quyết stale overwrite**.

Ví dụ rủi ro:

```sql
INSERT INTO application_orders(order_id, note, row_version)
VALUES (101, 'new value', 1)
ON CONFLICT (order_id)
DO UPDATE SET note = EXCLUDED.note;
```

Nếu bản ghi đã tồn tại và có dữ liệu mới, nhánh DO UPDATE có thể ghi đè nó mà không kiểm tra version.

PostgreSQL cho phép thêm điều kiện ở nhánh DO UPDATE:

```sql
-- Mẫu minh họa, không phải schema lab.
INSERT INTO application_orders (
    order_id, note, row_version
)
VALUES (101, 'new value', 1)
ON CONFLICT (order_id) DO UPDATE
SET note = EXCLUDED.note,
    row_version = application_orders.row_version + 1
WHERE application_orders.row_version = 1
RETURNING order_id, row_version;
```

Tuy nhiên:

- Nhánh INSERT vẫn chạy khi không có conflict; không phù hợp nếu API chỉ cho phép cập nhật một resource đang tồn tại.
- Giá trị version khởi tạo và expected version của nhánh UPDATE cần contract rõ, đặc biệt khi expected version không phải 1.
- Nếu nhánh DO UPDATE không thỏa WHERE, `RETURNING` không có hàng từ nhánh đó, dù hàng conflict có thể đã bị khóa để đánh giá.
- UPSERT không thay business status guard, tenant guard, authorization hay idempotency.

Với endpoint update-only, `UPDATE ... WHERE row_version=? RETURNING` thường đơn giản và an toàn hơn.

---

## 24. ABA: trạng thái trở lại giá trị cũ nhưng version vẫn phải khác

**ABA problem** xuất hiện khi một giá trị đổi A → B → A, khiến người chỉ so sánh **giá trị hiện tại** tưởng rằng chưa có gì thay đổi.

Ví dụ:

```text
Status DRAFT, version 5
    |
    v
Status PAID,  version 6
    |
    v
Status DRAFT, version 7  (giả sử policy cho phép quay lại)
```

Một client từng thấy DRAFT version 5, sau đó kiểm tra status vẫn DRAFT, có thể nghĩ dữ liệu không đổi. Nhưng version 7 nói đã có thay đổi trung gian.

### 24.1. Không reset version

Nếu code tự đặt version từ 7 về 5 vì status quay lại DRAFT, một client cũ có thể vượt qua điều kiện CAS, phá khả năng phát hiện stale data.

Version nên tăng **đơn điệu theo vòng đời logical object**. Nếu đối tượng bị xóa rồi tạo mới với cùng business ID, cần cân nhắc token thế hệ hoặc identity để tránh nhầm với phiên bản của đối tượng đã xóa.

---

## 25. Trường hợp retry và lỗi database

Một số tín hiệu khác nhau:

| Sự kiện | Cách báo |
| --- | --- |
| CAS version mismatch | UPDATE 0 hàng |
| Row lock wait quá thời gian | Timeout/exception phù hợp |
| Deadlock | `SQLSTATE 40P01` |
| Serialization failure | `SQLSTATE 40001` |
| Duplicate key | `SQLSTATE 23505` |
| CHECK violation | `SQLSTATE 23514` |
| Foreign key violation | `SQLSTATE 23503` |

### 25.1. Khi nào auto-retry?

| Nghiệp vụ | Chính sách thường hợp lý |
| --- | --- |
| Form sửa text | Reject, tải lại hoặc cho merge |
| Phép cộng đồng nhất | Atomic UPDATE hoặc retry có kiểm soát |
| Duyệt đơn | Kiểm tra lại trạng thái và quyền |
| Thanh toán | Idempotency và state machine |
| Transaction SERIALIZABLE gặp 40001 | Retry **toàn transaction** với giới hạn |
| Request timeout sau COMMIT | Truy vấn operation status/idempotency |
| Ghi audit | Không tự loại bỏ hoặc ghi đè event lịch sử |

### 25.2. Không retry bằng cách bỏ WHERE version

Cách này phá cơ chế bảo vệ:

```text
Lần 1: UPDATE WHERE version=7 -> 0 hàng
Lần 2: UPDATE WHERE id=101      -> 1 hàng
```

Không bao giờ dùng “fallback write không guard” để làm mọi request có vẻ thành công.

### 25.3. Không giữ transaction trong lúc chờ API mạng

Nếu transaction đã UPDATE CAS và giữ row lock, việc gọi một API bên ngoài trước COMMIT có thể khiến request khác chờ lâu. Nên giữ transaction ngắn, xử lý tác dụng phụ qua outbox khi phù hợp.

---

## 26. Hiệu năng, index và HOT update

Optimistic locking thêm một điều kiện theo version, nhưng thường không cần một index riêng trên `row_version` nếu truy vấn đã dùng PRIMARY KEY.

Ví dụ:

```sql
WHERE tenant_id = ?
  AND order_id = ?
  AND row_version = ?
```

PRIMARY KEY `(tenant_id,order_id)` giúp PostgreSQL tìm tối đa một hàng, sau đó so version.

### 26.1. Index riêng trên row_version có thể hại ghi

Nếu tạo index trên row_version, **mỗi lần UPDATE tăng version sẽ đổi indexed column**, ảnh hưởng khả năng HOT và tạo thêm chi phí index/WAL.

Không đánh index chỉ vì một cột xuất hiện trong WHERE. Hãy xem query plan, độ chọn lọc và workload thực sự.

### 26.2. Optimistic locking vẫn tạo tuple version mới

Trong PostgreSQL MVCC, UPDATE với CAS vẫn:

- Tạo phiên bản hàng mới.
- Phát sinh WAL cho bảng logged.
- Có thể duy trì index.
- Để lại phiên bản cũ cần pruning/VACUUM khi đủ điều kiện.

Version giúp đúng concurrency, không phải tối ưu ghi vật lý miễn phí.

### 26.3. Hot row và conflict rate

Khi hàng bị cập nhật liên tục:

- CAS conflicts tăng.
- Row lock wait có thể tăng.
- Retry storm có thể làm throughput tệ hơn.
- Chỉnh version không giải quyết được contention thực chất.

Có thể xem lại aggregate boundary, chuyển phép cộng sang atomic UPDATE, dùng queue/serial command processing hoặc mô hình event phù hợp. Không tự bỏ kiểm tra version để giảm số conflict.

### 26.4. Quan sát metrics

Nên ghi nhận:

- Số CAS attempts và successes.
- Version conflicts được xác nhận.
- Những conditional failures khác.
- Retry count, retry success.
- HTTP 409/412.
- Thời gian transaction và lock waits.
- Deadlock/serialization errors.
- Tỷ lệ người dùng phải merge/reload.
- Write throughput và chi phí WAL.

Đừng dùng tất cả UPDATE 0 rows như một bộ đếm chính xác của version conflicts vì WHERE còn nhiều điều kiện.

---

## 27. Kiểm thử concurrent requests đúng cách

Một unit test chỉ kiểm tra một UPDATE thành công chưa đủ. Cần integration tests thực sự dùng **hai connection**.

### 27.1. Test happy path

- Đơn version 1.
- Update expected 1.
- Trả version 2.
- Nội dung đúng.
- Commit thành công.

### 27.2. Test stale form

- A và B đều đọc version 1.
- B commit UPDATE version 2.
- A UPDATE expected 1.
- A nhận 0 rows/conflict.
- Dữ liệu B không bị ghi đè.

### 27.3. Test cạnh tranh đồng thời

Dùng barrier/latch trong test để hai worker cùng khởi động UPDATE expected version 1. Tùy isolation và thứ tự lock:

- Một writer commit thành công.
- Writer còn lại không được commit một thay đổi khác với **cùng expected version cũ** trên cùng hàng.
- Nó có thể trả 0 rows hoặc lỗi concurrent transaction cần retry theo contract.

### 27.4. Các trường hợp biên

- Sai tenant hoặc thiếu quyền.
- Đơn không tồn tại.
- Status guard không khớp.
- Form thiếu version.
- Version đã cũ.
- Hai trường khác nhau nhưng cùng aggregate.
- Soft delete xảy ra khi form đang mở.
- Batch ghi một phần.
- Transaction rollback sau UPDATE.
- Outbox insert thất bại.
- Client timeout sau COMMIT.
- Cùng idempotency key gửi hai lần.
- DML native/ORM bulk bỏ version.
- Deadlock hoặc serialization failure.

Không dựa vào các đoạn sleep ngẫu nhiên để “tạo concurrency”: test dễ chập chờn theo scheduler. Dùng đồng bộ có kiểm soát để tạo trạng thái cạnh tranh xác định.

---

## 28. Những lỗi triển khai phổ biến

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| UPDATE chỉ theo ID | Stale overwrite | Thêm expected version |
| SELECT version rồi UPDATE không guard | Race giữa check và use | CAS một statement |
| Không tăng version trên mọi writer | Bản nháp cũ vẫn khớp | Thống nhất policy |
| Chỉ kiểm tra SQL error | UPDATE 0 báo thành công | Kiểm tra row count/RETURNING |
| Tự đọc version mới rồi gửi lại payload cũ | Bỏ qua conflict | Reload/merge có chủ đích |
| Tự retry bằng UPDATE không version | Ghi đè dữ liệu mới | Không bỏ guard |
| updated_at là token nhưng mất precision | Có thể bỏ sót cập nhật | BIGINT/opaque token |
| Dùng ctid/xmin làm API token bền | Phụ thuộc metadata nội bộ | Cột version ứng dụng |
| Version không tăng khi soft delete | Form cũ có thể hồi sinh bản ghi | Bump token + state guard |
| ORM @Version nhưng bulk SQL bỏ qua | Protection không đồng nhất | Kiểm tra mọi đường ghi |
| Dùng một version mỗi hàng cho invariant nhiều hàng | Write skew | Aggregate root, locks, SERIALIZABLE |
| Batch không kiểm tra đủ số hàng | Commit thành công một phần | Transaction + rollback |
| Gửi event trước COMMIT | Event không tương ứng dữ liệu đã commit | Transactional outbox |
| COMMIT trước khi ghi outbox | Có thể mất event | Ghi trong cùng transaction |
| Coi version là idempotency | Không biết request trước đã xử lý chưa | Idempotency key |
| Bỏ tenant_id trong WHERE | Ghi sai tenant | Scope đầy đủ và authorization |
| Coi version token là mật khẩu | Vẫn thiếu quyền | Authn/authz riêng |
| Index row_version mà không đo | Tăng index work, giảm HOT | Dùng PK rồi kiểm tra version |
| Giữ FOR UPDATE khi user mở form | Lock/transaction dài | Optimistic locking |
| Không kiểm thử hai session | Bỏ sót race | Integration test có barrier |
| Báo success trước COMMIT | Xác nhận giả | Response sau COMMIT |
| Không xử lý 40001/40P01 | Transaction lỗi không được retry/diagnose | Phân loại SQLSTATE |
| Version 64-bit qua JS Number không chính xác | CAS sai ở miền số lớn | Truyền string opaque khi cần |

---

## 29. Bài tập thực hành

### Bài 1 — Phân tích lost update

Hai client A/B đọc note='A' và version 3. B ghi note='B', A ghi note='C'. Viết trạng thái cuối nếu UPDATE chỉ theo ID và nếu dùng CAS.

### Bài 2 — CAS với RETURNING

Trên bảng lab, đổi note order `(10,102)` từ version 1 sang version 2. Chạy cùng UPDATE lần nữa với expected version 1; giải thích vì sao trả 0 hàng.

### Bài 3 — Hai session

Mở hai kết nối, cùng đọc order 101 version 1. B lưu trước, A lưu sau. Xác định winner, loser và giá trị cuối.

### Bài 4 — Row locks so với optimistic version

Viết transaction ngắn có `SELECT ... FOR UPDATE`. Vì sao không giữ transaction đó trong lúc người dùng mở form 30 phút?

### Bài 5 — Chuyển trạng thái

Chỉ cho phép DRAFT → PAID. Viết câu UPDATE có `status='DRAFT'` và expected version. Status đã CANCELED nhưng version còn đúng sẽ cho kết quả gì?

### Bài 6 — Phân tích UPDATE 0 rows

Liệt kê ít nhất năm nguyên nhân khiến câu UPDATE theo tenant/id/version/status trả 0 hàng. Tại sao phải phân loại trong phạm vi quyền?

### Bài 7 — No-op và IS DISTINCT FROM

Viết câu UPDATE note chỉ khi khác giá trị mới. Điều gì xảy ra với version và audit nếu note vốn đã bằng giá trị đó?

### Bài 8 — updated_at và version

Giải thích vì sao `now()` trong cùng transaction không thích hợp làm token bắt buộc tăng với từng UPDATE. Vì sao JSON có thể làm mất microsecond?

### Bài 9 — Không dùng xmin/ctid làm mã bền

Phân biệt system columns với row_version của ứng dụng. Tại sao table rewrite/UPDATE có thể làm ctid đổi?

### Bài 10 — Atomic increment

Viết UPDATE cộng stock lên 1 và UPDATE trừ stock 1 khi stock>=1. Tại sao chúng có thể an toàn hơn cách SELECT rồi ghi giá trị tuyệt đối?

### Bài 11 — JDBC

Viết PreparedStatement với bind parameters và RETURNING row_version. Xử lý ResultSet rỗng thế nào? Khi nào service COMMIT?

### Bài 12 — JPA @Version

Mô tả cơ chế @Version và thời điểm có thể nhận OptimisticLockException. Một native bulk UPDATE không tăng version gây rủi ro gì?

### Bài 13 — HTTP If-Match

GET trả ETag v7, PUT gửi If-Match v7 nhưng DB đã lên v8. HTTP status phù hợp là gì? Nếu thiếu If-Match khi API bắt buộc thì sao?

### Bài 14 — Retry stale form

Một developer sửa conflict bằng cách đọc version mới rồi tự gửi lại payload cũ. Vì sao điều đó đánh bại optimistic locking?

### Bài 15 — Idempotency

Server COMMIT thành công nhưng response bị timeout, client retry. Vì sao CAS conflict không cho biết request đầu đã thành công hay chưa? Đề xuất idempotency key.

### Bài 16 — Transactional outbox

Viết CTE `WITH changed AS (UPDATE ... RETURNING ...) INSERT outbox SELECT ... FROM changed`. Nếu CAS trả 0 hàng, outbox có gì? Nếu outbox INSERT lỗi, trạng thái order ra sao sau rollback?

### Bài 17 — Soft delete

Thiết kế UPDATE deleted_at kèm version guard. Vì sao điều kiện deleted_at IS NULL cũng cần nếu ứng dụng chỉ thao tác với hàng hoạt động?

### Bài 18 — Conditional DELETE

Viết DELETE theo tenant/id/version RETURNING. So sánh với xóa theo id khi người khác vừa sửa bản ghi.

### Bài 19 — Write skew

Hai bác sĩ cùng xin nghỉ, mỗi transaction CAS trên một hàng khác nhau. Vì sao cả hai có thể thành công và vi phạm invariant? Đề xuất cơ chế bảo vệ.

### Bài 20 — Aggregate root

Order có nhiều items. Thiết kế transaction thay đổi item và claim version của order root. Vì sao không được commit child changes trước khi tăng version root?

### Bài 21 — Batch

Dùng `VALUES(tenant_id,order_id,expected_version)` để cập nhật hai hàng. Nếu chỉ một hàng khớp mà nghiệp vụ yêu cầu all-or-nothing, cần xử lý transaction thế nào?

### Bài 22 — Duplicate trong UPDATE FROM

Nếu nguồn expected chứa hai hàng cùng key, điều gì nguy hiểm? Nêu cách dùng staging table có PRIMARY KEY.

### Bài 23 — UPSERT

Vì sao ON CONFLICT DO UPDATE thiếu version guard có thể ghi đè dữ liệu mới? Vì sao endpoint update-only không nên ngầm insert?

### Bài 24 — ABA

Một bản ghi đổi A→B→A, version 5→6→7. Nếu client chỉ so trạng thái A, nó có thể bỏ sót điều gì? Vì sao không reset version?

### Bài 25 — Multi-tenant

Hai tenant có order_id 101, cùng version 1. Viết CAS chỉ sửa tenant 10. Version có thay authorization không?

### Bài 26 — SERIALIZABLE retry

Khi gặp SQLSTATE 40001, nêu quy trình rollback, backoff và retry toàn transaction. Vì sao không tự bỏ expected version?

### Bài 27 — Hot row

Một order bị nhiều worker UPDATE liên tục. Conflict và lock wait tăng. Đề xuất ba hướng cải thiện mà không bỏ correctness.

### Bài 28 — Index version

Vì sao PRIMARY KEY (tenant_id,order_id) thường đủ để tìm hàng khi CAS? Index riêng trên row_version có thể làm HOT update khó hơn như thế nào?

### Bài 29 — Concurrent test

Thiết kế test hai connection/barrier cùng UPDATE version 1. Các kết quả hợp lệ là gì theo isolation? Điều gì chứng minh không có hai thay đổi cùng commit từ một version?

### Bài 30 — Review API PATCH

Lập checklist: nhận expected version, auth tenant, status guard, CAS, RETURNING, COMMIT, conflict UX, outbox, idempotency, retry, bulk writers, monitoring và test concurrency.

---

## 30. Checklist triển khai

| Câu hỏi | Điểm cần xác định |
| --- | --- |
| Resource nào phải tránh stale update? | Aggregate boundary và business rules |
| Định danh chính xác? | Primary key, tenant scope |
| Version lưu kiểu nào? | BIGINT hoặc opaque token |
| Khi nào tăng version? | Mọi thay đổi cần bảo vệ |
| Ai quản lý version? | SQL/ORM/trigger, thống nhất |
| Client gửi expected bằng gì? | JSON version hoặc If-Match |
| Có bắt buộc gửi token? | Reject nếu endpoint yêu cầu |
| Guard có atomic? | UPDATE theo khóa + version, tăng cùng statement |
| Có status/business guard? | Đặt trong UPDATE |
| Có bảo vệ tenant? | Authn/authz/RLS phù hợp |
| Có kiểm tra số hàng? | RETURNING/count chính xác |
| 0 hàng xử lý thế nào? | Phân loại conflict/not found/forbidden |
| Trả thành công khi nào? | Sau COMMIT |
| Form stale xử lý thế nào? | Reload, compare, merge, reject |
| Retry có an toàn không? | Chỉ khi thao tác hợp nhất được |
| Có idempotency? | Request key và trạng thái operation |
| Có event ngoài DB? | Outbox transaction |
| Có child tables? | Root version/invariants trong một transaction |
| Có invariant nhiều hàng? | Constraint/locks/SERIALIZABLE |
| Có soft/physical delete? | Conditional delete và retention |
| Có job/batch/native SQL? | Tuân thủ version policy |
| Có JPA @Version? | Không bypass hoặc double increment |
| Có JS client? | Bảo toàn token BIGINT khi cần |
| Index version cần thiết? | Đo plan và write amplification |
| Có hot rows? | Quan sát conflict, lock wait, retry |
| Có concurrent tests? | Hai connection, barrier, một winner |
| Có failure tests? | Rollback, lost response, conflict, 40001 |
| Có monitoring? | Success/conflict rate và latency |

## Kết luận

**Kiểm soát cạnh tranh bằng phiên bản dữ liệu trong ứng dụng** giúp PostgreSQL phát hiện một request đang ghi từ bản nháp đã cũ, mà không cần giữ row lock suốt thời gian người dùng suy nghĩ.

Cốt lõi là một câu lệnh compare-and-swap:

```sql
UPDATE orders
SET business_data = :new_value,
    row_version = row_version + 1
WHERE primary_key = :id
  AND row_version = :expected_version
RETURNING row_version;
```

Cần nhớ:

- **MVCC và row locks** bảo vệ thao tác database, nhưng không tự nhận biết stale form giữa nhiều transaction.
- **Version phải được kiểm tra trong WHERE và tăng trong cùng UPDATE**; SELECT trước rồi UPDATE không điều kiện tạo race.
- **UPDATE 0 hàng không phải thành công** và cũng không mặc định chỉ có nguyên nhân version conflict.
- **Mọi writer** phải tuân thủ version policy, gồm API, ORM, batch, migration và admin tools.
- **Business guard, tenant scope, permissions và constraints** cần tồn tại bên cạnh version.
- **Retry tự động** không được vô hiệu hóa mục đích phát hiện xung đột của người dùng.
- **Idempotency và outbox** bảo vệ request retry và tác dụng phụ; chúng khác với optimistic locking.
- **Version của một hàng không bảo vệ mọi invariant nhiều hàng**; khi cần phải kết hợp aggregate root, locking, constraints hoặc SERIALIZABLE.
- **JDBC, JPA @Version và HTTP If-Match** là các cách triển khai khác nhau của cùng một giao thức cần được thống nhất.
- **Kiểm thử hai session và quan sát conflict rate** là nền tảng để chứng minh ứng dụng không âm thầm ghi đè dữ liệu mới.

Khi xác định đúng ranh giới tài nguyên, token phiên bản, điều kiện CAS và cách xử lý conflict, ứng dụng PostgreSQL có thể giữ được thay đổi của nhiều người dùng một cách nhất quán mà không biến mọi lần chỉnh sửa thành một transaction giữ khóa kéo dài.
