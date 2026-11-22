# Phân loại SQLSTATE, lỗi có thể thử lại và tính lặp an toàn trong PostgreSQL

Một ứng dụng Java gửi lệnh chuyển tiền hoặc tạo đơn hàng tới PostgreSQL. Câu SQL có thể thất bại vì dữ liệu nhập sai, khóa ngoại không tồn tại, hai giao dịch deadlock, xung đột ở mức `SERIALIZABLE`, hết kết nối hoặc máy chủ bị khởi động lại. Những lỗi đó **không thể xử lý bằng cùng một quy tắc “catch exception rồi chạy lại”**.

Ví dụ:

```text
23505  unique_violation         → thường là trùng dữ liệu / idempotency key
23503  foreign_key_violation    → dữ liệu tham chiếu không hợp lệ
40001  serialization_failure   → thử lại toàn bộ transaction
40P01  deadlock_detected        → có thể thử lại toàn bộ transaction
55P03  lock_not_available      → có thể thử lại nếu hợp đồng cho phép
57014  query_canceled          → phải xác định do timeout hay client hủy
08006  connection_failure      → kết nối hỏng, kết quả COMMIT có thể chưa rõ
```

**SQLSTATE** là mã lỗi chuẩn hóa gồm **5 ký tự** do PostgreSQL trả về. Ứng dụng nên phân loại theo mã này thay vì so khớp chuỗi thông báo lỗi có thể đổi theo phiên bản/ngôn ngữ. Tuy vậy, SQLSTATE **không đủ một mình** để xác định được phép lặp lại mọi thao tác: phải xét **giai đoạn transaction**, **mức độ side effect**, **idempotency** và **yêu cầu nghiệp vụ**.

Tình huống đặc biệt nguy hiểm là:

```text
Client gửi COMMIT
    |
    v
Server có thể đã COMMIT
    |
    X  Mất kết nối trước khi response đến client
    |
    v
Client nhận lỗi network, không biết kết quả cuối
```

Nếu client gửi lại “trừ 100.000 đồng” với một operation ID mới, có nguy cơ trừ tiền **hai lần**. Cách xử lý an toàn là dùng **mã yêu cầu duy nhất, ràng buộc UNIQUE, trạng thái kết quả bền vững và giao thức tra cứu/thử lại có kiểm soát**.

Bài học này kết nối ba lớp: **phân loại SQLSTATE**, **quyết định retry transaction đúng cách**, và **thiết kế thao tác an toàn khi cùng yêu cầu được gửi nhiều lần**. Các ví dụ dùng PostgreSQL và JDBC; kiến trúc tương tự áp dụng cho API, background jobs và message consumers.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc cấu trúc mã SQLSTATE 5 ký tự và phân loại bằng hai ký tự đầu.
2. Phân biệt lỗi dữ liệu không nên retry, lỗi transaction có thể retry, lỗi timeout/cancel và lỗi kết nối có trạng thái không xác định.
3. Nhận diện các mã thường gặp như `23505`, `23503`, `40001`, `40P01`, `55P03`, `57014`, `08006` và `25P02`.
4. Giải thích vì sao `40001`/`40P01` thường yêu cầu thử lại **toàn bộ transaction**, không chỉ câu SQL đã lỗi.
5. Sử dụng `SQLException.getSQLState()` trong JDBC và không phụ thuộc vào message text.
6. Thiết kế chính sách retry hữu hạn với backoff, jitter, deadline, logs và circuit-breaker/overload protection khi cần.
7. Phân biệt **lỗi kết nối** với **quyền được replay thao tác có side effect**.
8. Sử dụng khóa idempotency và `UNIQUE`/`ON CONFLICT` để chống xử lý trùng khi API được gọi lại.
9. Hiểu **commit outcome unknown**, thiết kế phục hồi bằng truy vấn trạng thái bền vững.
10. Tránh thao tác ngoài PostgreSQL (gửi email/gọi thanh toán) lặp ngoài ý muốn bằng outbox và idempotency của bên nhận.
11. Tự tạo deadlock/serialization conflict trong lab nhiều session và quan sát mã SQLSTATE.
12. Viết bộ test âm tính và theo dõi số lần retry, kết quả cuối và mức độ tin cậy của hệ thống.

## 2. SQLSTATE là gì?

SQLSTATE là trường lỗi cấu trúc mà PostgreSQL gửi cho client qua giao thức. Với lỗi SQL được server báo đầy đủ, nó thường có dạng:

```text
23505
││└──┬──┘
││   └─ Mã điều kiện cụ thể (3 ký tự cuối)
└┴───── Class lỗi (2 ký tự đầu: 23)
```

Ví dụ:

- `23`: nhóm **integrity constraint violation**.
- `23505`: điều kiện **unique_violation** trong nhóm `23`.
- `40`: nhóm **transaction rollback**.
- `40001`: **serialization_failure**.

Mã là chuỗi **5 ký tự**, **không phải số nguyên**: có các chữ cái như `40P01`, `08P01` và `22P02`. Không chuyển SQLSTATE thành integer hoặc regex chỉ chấp nhận 5 chữ số.

### 2.1. Dùng class để nhóm, mã đầy đủ để quyết định

Phân loại hai bước:

1. Xem **2 ký tự đầu** để xác định nhóm vấn đề.
2. Xem **cả 5 ký tự** để quyết định cách xử lý phù hợp cho một lỗi cụ thể.

Ví dụ, nhiều lỗi thuộc `Class 40` liên quan rollback transaction, nhưng không nên tự động replay mọi thao tác chỉ vì mã bắt đầu bằng `40`. Với `40001` và `40P01`, PostgreSQL có hướng dẫn retry rõ hơn; với những mã khác cần xem ý nghĩa cụ thể.

### 2.2. SQLSTATE khác thông báo lỗi

Thông báo có thể là:

```text
ERROR: duplicate key value violates unique constraint "orders_pkey"
DETAIL: Key (order_id)=(123) already exists.
SQLSTATE: 23505
```

Trong client có thể có ngôn ngữ/phiên bản/chi tiết khác. **`23505`** là định danh máy đọc ổn định hơn “duplicate key”, “trùng khóa” hay tên constraint trong message.

### 2.3. SQLSTATE khác HTTP status

HTTP `409 Conflict` là một quyết định ánh xạ ở tầng API; nó không phải SQLSTATE. Một backend có thể ánh xạ `23505` sang HTTP 409 khi request tạo tài nguyên trùng, nhưng cũng có thể trả lại kết quả thành công cũ nếu đó là **cùng idempotency key và cùng payload**.

### 2.4. SQLSTATE khác lỗi mạng thuần client

Một số sự cố DNS/TLS/socket xảy ra **trước khi PostgreSQL gửi error response**. Driver JDBC có thể ném `SQLException` với SQLSTATE thuộc class `08` hoặc không có SQLSTATE hữu ích. Vì vậy classifier phải có nhánh **unknown/null SQLSTATE** và xét bối cảnh driver/connection, không giả định mọi lỗi đều có một mã PostgreSQL cụ thể.

### 2.5. Không lấy tên constraint từ việc parse message

Khi cần biết constraint cụ thể, driver PostgreSQL có thể cung cấp structured server error metadata (ví dụ `PSQLException.getServerErrorMessage()` và `getConstraint()` khi có). Không làm:

```java
if (e.getMessage().contains("orders_pkey")) {
    // ...
}
```

Đây là logic mong manh; message có thể thay đổi, thông tin constraint không phải lúc nào cũng có và không nên xuất toàn bộ thông điệp PostgreSQL cho end user.

## 3. Các class SQLSTATE thường gặp

| Class | Nhóm | Ví dụ | Cách tiếp cận ban đầu |
| --- | --- | --- | --- |
| `00` | Successful Completion | `00000` | Không phải lỗi cần retry. |
| `01` | Warning | `01000` | Ghi cảnh báo, xem hợp đồng ứng dụng. |
| `02` | No Data | `02000` | Xử lý “không có dữ liệu” theo nghiệp vụ. |
| `08` | Connection Exception | `08001`, `08006` | Đánh giá mất kết nối và trạng thái COMMIT không rõ. |
| `0A` | Feature Not Supported | `0A000` | Sửa SQL/cấu hình/phiên bản; không retry mù. |
| `22` | Data Exception | `22P02`, `22003` | Validate input/chuyển kiểu; thường không retry. |
| `23` | Integrity Constraint Violation | `23505`, `23503` | Xử lý conflict/constraint theo nghiệp vụ. |
| `25` | Invalid Transaction State | `25P02`, `25006` | Sửa luồng transaction/rollback. |
| `28` | Invalid Authorization Specification | `28P01` | Xác thực/cấu hình quyền; không replay giao dịch. |
| `3D` | Invalid Catalog Name | `3D000` | Sửa tên database/cấu hình. |
| `3F` | Invalid Schema Name | `3F000` | Sửa migration/schema. |
| `40` | Transaction Rollback | `40001`, `40P01` | Thường retry **toàn transaction** cho mã được phép. |
| `42` | Syntax Error or Access Rule Violation | `42601`, `42P01`, `42501` | Sửa SQL/schema/permission. |
| `53` | Insufficient Resources | `53100`, `53200`, `53300` | Giảm tải/khắc phục tài nguyên; chỉ retry có giới hạn. |
| `55` | Object Not in Prerequisite State | `55P03`, `55006` | Xem lock/object state; có thể backoff. |
| `57` | Operator Intervention | `57014`, `57P01`, `57P03` | Phân biệt cancel/timeout/shutdown và trạng thái thao tác. |
| `58` | System Error | `58030` | Xem hạ tầng/I/O; không retry dồn dập. |
| `P0` | PL/pgSQL Error | `P0001`, `P0002` | Xem exception trong function/procedure. |
| `XX` | Internal Error | `XX000` | Cần điều tra/log/DBA; không replay không giới hạn. |

**Không có class nào bảo đảm 100% “retryable” chỉ từ tiền tố.** Ví dụ class `08` mô tả vấn đề kết nối, nhưng nếu client không biết COMMIT đã thành công hay chưa, không thể tự động phát lại cùng side effect bằng request mới.

## 4. Những SQLSTATE cần thuộc và phản ứng mặc định

| SQLSTATE | Tên điều kiện | Thường gặp khi | Hướng xử lý |
| --- | --- | --- | --- |
| `40001` | `serialization_failure` | Transaction isolation cao gặp lịch sử không thể serialize. | Rollback và retry **toàn transaction** bằng input/operation ID an toàn. |
| `40P01` | `deadlock_detected` | Hai transaction khóa tài nguyên theo thứ tự xung đột. | Rollback, backoff, retry toàn transaction; đồng thời sửa lock ordering. |
| `55P03` | `lock_not_available` | `NOWAIT` hoặc `lock_timeout` gặp lock bận. | Có thể retry hoặc trả busy theo SLA; rollback transaction lỗi. |
| `57014` | `query_canceled` | `statement_timeout` hoặc cancel. | Kiểm tra nguyên nhân/hạn thời gian; không tự replay nếu user đã cancel. |
| `23505` | `unique_violation` | Insert/Update trùng unique key. | Phân biệt duplicate request vs business conflict; dùng idempotency/UPSERT. |
| `23503` | `foreign_key_violation` | Thiếu parent row hoặc thao tác phá FK. | Sửa thứ tự và tính hợp lệ dữ liệu. |
| `23502` | `not_null_violation` | Cố ghi SQL NULL vào cột NOT NULL. | Validate input/schema. |
| `23514` | `check_violation` | Vi phạm CHECK constraint. | Sửa dữ liệu/định nghĩa. |
| `23P01` | `exclusion_violation` | Vi phạm exclusion constraint. | Xử lý conflict theo nghiệp vụ. |
| `22P02` | `invalid_text_representation` | Cast text không hợp lệ, ví dụ `'abc'::integer`. | Sửa input; không retry. |
| `22003` | `numeric_value_out_of_range` | Số vượt phạm vi kiểu. | Sửa input/schema. |
| `42501` | `insufficient_privilege` | Thiếu GRANT/role/USAGE. | Sửa quyền đúng, không cấp bừa BYPASS/superuser. |
| `42P01` | `undefined_table` | Thiếu bảng/search_path/migration. | Sửa migration/cấu hình. |
| `42703` | `undefined_column` | Sai tên cột/schema mismatch. | Sửa SQL/migration. |
| `42601` | `syntax_error` | SQL sai cú pháp. | Sửa code. |
| `25006` | `read_only_sql_transaction` | Ghi trên transaction read-only/replica. | Định tuyến đúng primary, sửa transaction mode. |
| `25P02` | `in_failed_sql_transaction` | Tiếp tục SQL sau lỗi mà chưa rollback. | Rollback hoặc ROLLBACK TO SAVEPOINT thích hợp. |
| `08006` | `connection_failure` | Kết nối bị hỏng. | Mở kết nối mới, phân loại **kết quả transaction có thể chưa biết**. |
| `08003` | `connection_does_not_exist` | Dùng connection không còn tồn tại. | Thay connection, xác định outcome trước replay. |
| `08001` | `sqlclient_unable_to_establish_sqlconnection` | Không thiết lập được kết nối. | Có thể thử kết nối lại với backoff; không tự phát lại side effect cũ. |
| `08004` | `sqlserver_rejected_establishment_of_sqlconnection` | Server từ chối kết nối. | Xem overload/auth/config, backoff. |
| `08P01` | `protocol_violation` | Sai giao thức/client/server. | Điều tra driver/proxy; không lặp dồn dập. |
| `57P01` | `admin_shutdown` | Server bị dừng theo yêu cầu quản trị. | Chờ server/định tuyến; kiểm tra outcome. |
| `57P02` | `crash_shutdown` | Server crash. | Điều tra hạ tầng và xác nhận kết quả. |
| `57P03` | `cannot_connect_now` | Server chưa sẵn sàng nhận kết nối. | Retry connect có giới hạn. |
| `53300` | `too_many_connections` | Hết connection slots. | Giới hạn pool/concurrency, backoff, không storm. |
| `53100` | `disk_full` | Storage thiếu. | Phục hồi dung lượng, alert; không replay hàng loạt. |
| `53200` | `out_of_memory` | Không đủ memory. | Giảm tải/sửa query, alert. |
| `P0001` | `raise_exception` | PL/pgSQL `RAISE EXCEPTION` mặc định. | Phân loại theo contract của function, không tự coi transient. |

Danh sách mang tính thiết thực, **không phải toàn bộ mã của PostgreSQL**. Các tên lỗi và mã chính thức có thể tra trong tài liệu PostgreSQL *Appendix A — Error Codes*. Đừng dựa vào danh sách này để tự phỏng đoán những mã lạ: log mã, tìm tài liệu chính thức và xử lý lỗi không nhận diện theo nguyên tắc bảo thủ.

## 5. Phân loại lỗi theo hành động, không chỉ theo mã

Một mô hình thực tế có ít nhất năm nhóm hành động:

| Nhóm | Ví dụ | Hành động |
| --- | --- | --- |
| **Business/input** | `23505`, `23503`, `23514`, `22P02` | Từ chối/sửa yêu cầu, ánh xạ lỗi công khai an toàn. |
| **Transaction transient** | `40001`, `40P01` | Rollback rồi retry **toàn bộ giao dịch**, giới hạn lượt. |
| **Contention/timeout có điều kiện** | `55P03`, `57014` | Xem SLA, lý do cancel, deadline và khả năng thử lại. |
| **Connection/unknown outcome** | `08...`, network exception | Kết nối lại; không replay side effect nếu chưa có giao thức idempotent/reconciliation. |
| **Code/config/infrastructure** | `42P01`, `42501`, `53300`, `53100` | Sửa deployment/permission/tài nguyên hoặc giảm tải; không lặp vô hạn. |

### 5.1. “Retryable” là thuộc tính của *operation + context*

Hai câu SQL có cùng `55P03` có thể cần phản ứng khác:

- Một job lấy lock advisory `NOWAIT` để làm báo cáo: có thể đợi rồi thử lại.
- Một request checkout có deadline 300 ms: không đủ thời gian để chờ, nên trả busy/hẹn lại.

Tương tự, mất kết nối khi chạy `SELECT 1` khác mất kết nối **sau khi gửi COMMIT của thanh toán**.

### 5.2. Không chuyển mọi SQLSTATE thành HTTP 500

Nên có taxonomy ở tầng API:

- Dữ liệu đầu vào sai: trả lỗi client thích hợp.
- Trùng business key: 409 hoặc kết quả cũ đã xác nhận theo idempotency.
- Retry exhaustion do tranh chấp: trả lỗi tạm thời được chuẩn hóa, có thể kèm `Retry-After` khi phù hợp.
- Unknown commit outcome: trả trạng thái “đang xác minh/không rõ kết quả” cùng operation ID để client tra cứu, thay vì khẳng định thất bại.

Mã HTTP cuối cùng phụ thuộc contract API, nhưng **không nên để ứng dụng vô tình tạo lại side effects** chỉ vì một lần trả HTTP 5xx.

## 6. Mô hình quyết định retry an toàn

```text
                 Bắt SQLException/DB failure
                            |
                            v
                   Có SQLSTATE hợp lệ?
                      /            \
                    Có              Không
                    |                 |
          Phân loại mã đầy đủ       Xem stage + driver
                    |             / network context
      +-------------+-------------+
      |
      +-- Input/schema/privilege → KHÔNG tự retry; xử lý nguyên nhân
      |
      +-- 40001/40P01 → ROLLBACK → retry TOÀN transaction
      |                                  (budget/backoff)
      |
      +-- 55P03/57014 → kiểm tra timeout/cancel/deadline/policy
      |
      +-- Connection failure / lost COMMIT response
                   |
                   v
           Transaction outcome chắc chắn?
               /                  \
            Chắc chắn             Không rõ
             |                       |
       Theo tình huống          Reconcile bằng operation ID
             |                 + idempotent protocol
             v                       |
       Retry nếu hợp lệ         Không phát lại blind
```

**Luôn tách hai câu hỏi:**

1. *Hạ tầng có thể kết nối lại/thực thi lại statement không?*
2. *Về mặt nghiệp vụ, chạy lại thao tác có gây trùng kết quả hoặc side effect không?*

Chỉ trả lời “có thể retry” khi cả điều kiện kỹ thuật lẫn hợp đồng nghiệp vụ đều cho phép.

## 7. Bộ dữ liệu thực hành: lỗi, giao dịch và idempotency

Toàn bộ ví dụ từ đây sử dụng schema riêng `retry_lab`. Chạy trên **database thực hành**, không trên dữ liệu thật. Một số demo cố tình gây lỗi hoặc deadlock, sẽ được đánh dấu rõ và nên thực hiện bằng hai cửa sổ `psql` riêng.

### 7.1. Tạo schema, bảng tài khoản và dữ liệu

```sql
CREATE SCHEMA IF NOT EXISTS retry_lab;

CREATE TABLE retry_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_label text NOT NULL,
    balance numeric(14, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO retry_lab.accounts
    (account_id, owner_label, balance)
VALUES
    (1, 'Account A', 1000.00),
    (2, 'Account B',  500.00),
    (3, 'Account C',  200.00);
```

Chạy phần tạo bảng/INSERT trên database trống **một lần**. Nếu đã tạo lab trước đó, không lặp INSERT mà không có chiến lược reset phù hợp.

### 7.2. Bảng yêu cầu có idempotency key

```sql
CREATE TABLE retry_lab.transfer_requests (
    request_id uuid PRIMARY KEY,
    from_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    to_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL
        CHECK (amount > 0),
    status text NOT NULL
        CHECK (
            status IN (
                'processing',
                'applied',
                'insufficient_funds'
            )
        ),
    result_note text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CHECK (from_account <> to_account)
);
```

`request_id` do client/trusted service tạo, ổn định **qua mọi lần retry của cùng yêu cầu**. PRIMARY KEY vừa ngăn trùng key vừa là cơ sở đồng bộ nhiều requests cạnh tranh.

### 7.3. Bảng ledger để quan sát số lần áp giao dịch

```sql
CREATE TABLE retry_lab.transfer_ledger (
    ledger_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE
        REFERENCES retry_lab.transfer_requests(request_id),
    from_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    to_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

`UNIQUE(request_id)` ở ledger là một **lớp bảo vệ thứ hai**: một request không được có hai bản ghi chuyển tiền thành công trong ledger.

### 7.4. Bảng outbox minh họa

```sql
CREATE TABLE retry_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL
        REFERENCES retry_lab.transfer_requests(request_id),
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz,
    UNIQUE (request_id, event_type)
);
```

Outbox chỉ lưu sự kiện **bền vững trong cùng PostgreSQL transaction**. Việc gửi sự kiện tới broker/API ngoài PostgreSQL phải do worker riêng xử lý và cũng cần cơ chế chống gửi trùng.

### 7.5. Bảng nhỏ để thử UNIQUE/FK/CHECK

```sql
CREATE TABLE retry_lab.sample_items (
    item_id integer PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    quantity integer NOT NULL
        CHECK (quantity >= 0)
);

INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES
    (1, 'SKU-A', 10),
    (2, 'SKU-B', 20);
```

### 7.6. Lưu ý về dữ liệu mẫu

- `accounts` bắt đầu với balances `1000/500/200`.
- `transfer_requests`, `transfer_ledger` và `outbox_events` ban đầu rỗng.
- Những ví dụ có COMMIT sẽ thay đổi trạng thái; nếu muốn chạy lại từ đầu, tạo một database lab mới hoặc khôi phục dữ liệu phù hợp.
- Các câu gây lỗi được comment hoặc khuyên chạy riêng vì PostgreSQL có thể đưa transaction vào trạng thái failed.
- Mỗi lệnh SQL không chỉ tác động dữ liệu: trigger, foreign keys, locks, WAL và MVCC vẫn hoạt động.

## 8. Thử các lỗi thuộc nhóm constraint và data

### 8.1. UNIQUE violation — `23505`

```sql
-- Chạy riêng để quan sát lỗi dự kiến:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (3, 'SKU-A', 5);
```

`sku='SKU-A'` đã tồn tại. PostgreSQL có thể trả:

```text
ERROR: duplicate key value violates unique constraint ...
SQLSTATE: 23505
```

**Phản ứng:** xem đây là hai requests có cùng identity cần trả kết quả đã xử lý, hay hai tài nguyên thực sự xung đột. Không mặc định ngủ 100 ms rồi INSERT cùng dữ liệu một lần nữa.

### 8.2. CHECK violation — `23514`

```sql
-- Lỗi dự kiến:
-- UPDATE retry_lab.sample_items
-- SET quantity = -3
-- WHERE item_id = 1;
```

Không có lý do retry: `CHECK(quantity >= 0)` sẽ vẫn từ chối giá trị -3 cho đến khi dữ liệu hoặc quy tắc thay đổi.

### 8.3. NOT NULL — `23502`

```sql
-- Lỗi dự kiến:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (4, NULL, 5);
```

Trường `sku` bắt buộc không NULL. Retry cùng payload không giải quyết.

### 8.4. FOREIGN KEY — `23503`

```sql
-- Lỗi dự kiến khi account_id=999 không có trong accounts:
-- INSERT INTO retry_lab.transfer_requests (
--     request_id, from_account, to_account, amount, status
-- )
-- VALUES (
--     '00000000-0000-4000-8000-000000000099',
--     999, 2, 10.00, 'processing'
-- );
```

Đây có thể là nhập sai account, thứ tự import sai hoặc race với thao tác xóa parent. Cần kiểm tra nguyên nhân. Chỉ retry sau khi một **dependency có khả năng hợp lệ được chờ hoàn tất** nếu ứng dụng thiết kế luồng eventual consistency rõ; không xem `23503` mặc nhiên transient.

### 8.5. Invalid text representation — `22P02`

```sql
-- Lỗi dự kiến:
-- SELECT 'not-an-integer'::integer;
```

Sửa/validate input trước. Nếu lỗi đến từ schema/type mismatch ở application, đó là defect cần sửa code.

### 8.6. Numeric out of range — `22003`

```sql
-- Lỗi dự kiến:
-- SELECT 1000000000000000000000::integer;
```

Một giá trị không nằm trong miền biểu diễn của kiểu `integer`. Không có ý nghĩa thử lại cùng câu SQL mãi.

### 8.7. Xem SQLSTATE trong psql

Trong `psql`, có thể bật hiển thị chi tiết lỗi:

```text
\set VERBOSITY verbose
```

Sau khi thực thi một câu SQL có lỗi, `psql` có thể hiển thị SQLSTATE trong output verbose. Đây là **psql meta-command**, không phải SQL gửi qua JDBC.

### 8.8. Khi nào dùng ON CONFLICT?

Nếu hành động mong muốn là “chèn nếu chưa tồn tại, nếu đã tồn tại thì đọc lại/không chèn”, thay vì coi `23505` như transient error, dùng:

```sql
INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES
    (3, 'SKU-A', 5)
ON CONFLICT (sku) DO NOTHING
RETURNING item_id, sku, quantity;
```

Vì `SKU-A` đã tồn tại, câu này không chèn row mới và `RETURNING` trả 0 rows. **Nó không tự xác minh payload có giống request ban đầu hay không**. Nếu `SKU-A` là business key, ứng dụng phải kiểm tra các trường khác hoặc xử lý conflict theo hợp đồng.

## 9. PostgreSQL transaction bị lỗi: `25P02`

Một hành vi quan trọng của PostgreSQL: khi một statement thất bại trong transaction block thông thường, transaction rơi vào **failed state**. Các SQL tiếp theo trong transaction đó có thể trả:

```text
SQLSTATE 25P02
current transaction is aborted, commands ignored
until end of transaction block
```

### 9.1. Thử trên lab

Mở một session `psql`:

```sql
BEGIN;

-- Chạy không comment để chủ ý tạo 23505:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (9, 'SKU-A', 8);

-- Nếu câu trên đã lỗi, câu dưới cũng sẽ lỗi 25P02:
SELECT COUNT(*) FROM retry_lab.sample_items;

ROLLBACK;
```

Các câu gây lỗi được comment để bạn lựa chọn chạy riêng. Khi bỏ comment INSERT rồi thực thi trong cùng transaction, SELECT phía sau sẽ không “tự phục hồi”.

### 9.2. Quy tắc khôi phục

Sau lỗi ở transaction:

1. Ghi nhận SQLSTATE **gốc** (ví dụ `23505` hoặc `40001`).
2. `ROLLBACK` toàn transaction nếu cần thử lại.
3. Với `SAVEPOINT`, có thể `ROLLBACK TO SAVEPOINT` khi bạn **chủ động thiết kế** cô lập lỗi cấp subtransaction.
4. Không lấy `25P02` làm “nguyên nhân gốc” rồi lặp lại SELECT mãi trên cùng connection/transaction.

### 9.3. Savepoint cho lỗi dự kiến

```sql
BEGIN;

SAVEPOINT before_optional_insert;

-- Bỏ comment câu này để quan sát 23505:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (9, 'SKU-A', 8);

-- Nếu câu INSERT vừa lỗi, chạy:
ROLLBACK TO SAVEPOINT before_optional_insert;

SELECT COUNT(*) FROM retry_lab.sample_items;

COMMIT;
```

`ROLLBACK TO SAVEPOINT` phục hồi transaction chính về trạng thái có thể tiếp tục. Trong thực tế nếu chỉ muốn bỏ qua duplicate theo conflict key phù hợp, `INSERT ... ON CONFLICT DO NOTHING` thường đơn giản hơn một exception/savepoint loop.

### 9.4. Savepoint không thay thế retry toàn transaction

Với `40001 serialization_failure`, việc rollback về một savepoint và lặp chỉ câu UPDATE đã lỗi **không được xem là retry đúng của cả giao dịch**, vì quyết định trước đó có thể dựa trên snapshot cũ. Hướng khuyến nghị là retry toàn transaction từ đầu.

### 9.5. JDBC connection sau lỗi

Nếu connection được trả về pool trong trạng thái transaction aborted mà không rollback, request sau có thể gặp `25P02` khó hiểu. Transaction manager/try-finally phải luôn kết thúc transaction đúng (COMMIT hoặc ROLLBACK), đặc biệt khi timeout/cancel và exceptions.

## 10. Vì sao `40001` cần thử lại toàn bộ transaction?

PostgreSQL có các mức isolation. Với `SERIALIZABLE`, hệ quản trị có thể phát hiện lịch thực thi giao dịch đồng thời không thể tạo kết quả tương đương một thứ tự nối tiếp hợp lệ. Một transaction bị chọn rollback và trả:

```text
40001  serialization_failure
```

Đây **không nhất thiết là SQL sai**; có thể là kết quả hợp lệ của điều khiển cạnh tranh. Ứng dụng được kỳ vọng **thử lại toàn bộ transaction**, bao gồm logic quyết định câu SQL và giá trị cần ghi.

### 10.1. Vì sao chỉ chạy lại UPDATE cuối không đủ?

Giả sử:

```text
T1: SELECT số hàng còn lại trong kho
T1: Nếu còn đủ, quyết định xuất 5 sản phẩm
T2: Cập nhật kho và COMMIT
T1: UPDATE kho → 40001
```

Nếu chỉ lặp lại UPDATE mà không SELECT/check điều kiện từ snapshot mới, quyết định cũ có thể đã hết hợp lệ. Khi retry:

```text
BEGIN SERIALIZABLE
  đọc lại dữ liệu
  đánh giá lại business rules
  tính lại giá trị cần ghi
  ghi dữ liệu
COMMIT
```

### 10.2. Dùng một operation ID ổn định qua retry

Business request có thể được gọi nhiều lần ở JDBC transaction level. `request_id`/idempotency key phải giữ **không đổi** qua các attempt để không tạo hai yêu cầu logic khác nhau.

### 10.3. Không thực hiện side effect bên ngoài trong transaction retryable

Không nên:

```text
BEGIN
  UPDATE database
  gửi email thật
  gọi API thanh toán thật
COMMIT  → 40001
retry toàn transaction → email/thanh toán lặp lại
```

Vì PostgreSQL rollback không thể hoàn tác email đã gửi hoặc tiền đã chuyển qua nhà cung cấp. Dùng outbox/idempotency ở hệ thống ngoài.

## 11. Lab hai session: tạo serialization failure `40001`

Đây là demo có concurrency; cần **hai cửa sổ psql riêng** cùng kết nối vào database lab. Không chạy trên production. Để không làm thay đổi tài khoản chuyển tiền ở phần sau, tạo bảng riêng:

```sql
CREATE TABLE retry_lab.serial_test (
    id integer PRIMARY KEY,
    value integer NOT NULL
);

INSERT INTO retry_lab.serial_test(id, value)
VALUES (1, 100), (2, 100);
```

### 11.1. Session A

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT SUM(value) AS total
FROM retry_lab.serial_test;
-- Đợi Session B cũng chạy SELECT trước khi tiếp tục.
```

### 11.2. Session B

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT SUM(value) AS total
FROM retry_lab.serial_test;
-- Cả hai transaction đều thấy tổng ban đầu 200.
```

### 11.3. Session A ghi hàng thứ nhất

```sql
UPDATE retry_lab.serial_test
SET value = value + 10
WHERE id = 1;
```

### 11.4. Session B ghi hàng thứ hai

```sql
UPDATE retry_lab.serial_test
SET value = value + 10
WHERE id = 2;
```

### 11.5. COMMIT hai phía

Ở A:

```sql
COMMIT;
```

Ở B:

```sql
COMMIT;
```

Hai transaction đều đọc toàn bộ hai hàng rồi ghi những hàng khác nhau, tạo ra quan hệ read/write conflict có thể khiến PostgreSQL từ chối một transaction để giữ tính serializable. Thông thường một bên gặp `40001`, nhưng lịch thực thi và thời điểm phát hiện là yếu tố concurrency; không hard-code rằng Session B phải luôn là victim trong mọi lần thử.

### 11.6. Hướng xử lý đúng

Nếu một transaction nhận `40001`, hãy bắt đầu lại **BEGIN ISOLATION LEVEL SERIALIZABLE**, thực hiện lại SELECT, đánh giá lại các quyết định và UPDATE, rồi COMMIT. Đừng chỉ chạy lại COMMIT hoặc UPDATE trên transaction đã aborted.

### 11.7. Tại sao lại thử trên bảng riêng?

Thử nghiệm có thể COMMIT một trong hai UPDATE. Nếu dùng bảng `accounts` thật của lab idempotency, số dư đầu vào sẽ không còn như mô tả. Giữ ví dụ serialization trên `serial_test` giúp phần nghiệp vụ transfer độc lập.

### 11.8. SERIALIZABLE không loại bỏ nhu cầu retry

Isolation cao hơn giúp PostgreSQL phát hiện và hủy những lịch thực thi không thể serialize, **không đảm bảo giao dịch luôn thành công ngay lần đầu**. Một ứng dụng dùng SERIALIZABLE nhưng không có retry logic phù hợp có thể trả lỗi không cần thiết trong các đợt tranh chấp.

## 12. Lab hai session: tạo deadlock `40P01`

Deadlock xảy ra khi hai transaction mỗi bên giữ lock bên kia cần và cả hai không thể tiếp tục. PostgreSQL phát hiện vòng chờ, hủy một transaction làm nạn nhân và báo `40P01`.

### 12.1. Bảng riêng cho deadlock

```sql
CREATE TABLE retry_lab.deadlock_test (
    id integer PRIMARY KEY,
    value integer NOT NULL
);

INSERT INTO retry_lab.deadlock_test(id, value)
VALUES (1, 10), (2, 20);
```

### 12.2. Session A khóa ID 1

```sql
BEGIN;

UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 1;
-- Giữ transaction mở.
```

### 12.3. Session B khóa ID 2

```sql
BEGIN;

UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 2;
-- Giữ transaction mở.
```

### 12.4. Session A thử cập nhật ID 2

```sql
UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 2;
```

Lệnh này có thể **đợi** vì Session B đang giữ row lock tương ứng.

### 12.5. Khi A đang đợi, Session B thử ID 1

```sql
UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 1;
```

Giờ A chờ B, B chờ A. PostgreSQL phát hiện deadlock và một bên nhận lỗi `40P01`. Bên còn lại có thể tiếp tục sau khi transaction victim giải phóng locks.

### 12.6. Kết thúc đúng hai sessions

Transaction bị báo `40P01` phải `ROLLBACK`. Transaction còn thành công có thể `COMMIT` hoặc `ROLLBACK` nếu bạn chỉ muốn thử. **Không để session còn chờ/idle in transaction** sau lab.

### 12.7. Cách giảm deadlock từ gốc

- Các transactions cập nhật cùng nhiều rows nên có **thứ tự khóa nhất quán**.
- Giữ transactions ngắn.
- Tránh giữ lock trong lúc gọi API ngoài hoặc chờ người dùng.
- Dùng index phù hợp để giảm phạm vi lock do câu SQL tìm hàng kém hiệu quả.
- Với các queue patterns, cân nhắc `FOR UPDATE SKIP LOCKED` khi đúng ngữ nghĩa.
- Dù đã giảm nguy cơ, vẫn cần logic xử lý `40P01` vì deadlock có thể xảy ra từ những cấu trúc phức tạp.

Ví dụ chuyển A→B và B→A đồng thời nên xác định thứ tự khóa theo `account_id` trước khi thay đổi balances nếu thiết kế đa lệnh đòi khóa hai tài khoản.

## 13. `55P03`: NOWAIT và lock_timeout

`55P03 lock_not_available` thường xảy ra khi lệnh yêu cầu lock nhưng không thể đợi hoặc đã đợi quá thời hạn cho phép.

### 13.1. FOR UPDATE NOWAIT

Session A:

```sql
BEGIN;

SELECT *
FROM retry_lab.deadlock_test
WHERE id = 1
FOR UPDATE;
-- Giữ transaction mở.
```

Session B:

```sql
BEGIN;

-- Dự kiến 55P03 nếu A còn giữ lock:
SELECT *
FROM retry_lab.deadlock_test
WHERE id = 1
FOR UPDATE NOWAIT;

-- Nếu có lỗi, khôi phục transaction:
ROLLBACK;
```

`NOWAIT` là yêu cầu **không chờ** row lock trong trường hợp được hỗ trợ, thường trả `55P03` ngay.

### 13.2. lock_timeout

```sql
BEGIN;

SET LOCAL lock_timeout = '500ms';

-- Thử lệnh cần lock đang bị session khác giữ:
-- UPDATE retry_lab.deadlock_test
-- SET value = value + 1 WHERE id = 1;

ROLLBACK;
```

Nếu chờ lock quá 500 ms, PostgreSQL có thể hủy statement với `55P03`. Nếu không có contention thì UPDATE vẫn thành công và không có lỗi.

### 13.3. Xử lý theo SLA

`55P03` có thể là tín hiệu “tài nguyên đang bận”:

- Một job maintenance có thể đợi rồi thử lại.
- Một API tương tác có thể trả lỗi tạm thời nếu hết deadline.
- Một job xử lý queue có thể chọn work item khác thay vì tranh lock.

Nếu retry, vẫn cần rollback failed transaction, giới hạn số lượt và backoff. Đừng spin-loop retry liên tục tạo thêm áp lực lock manager.

### 13.4. lock_timeout và statement_timeout

`lock_timeout` đo thời gian đợi để có lock; `statement_timeout` giới hạn thời gian thực thi câu lệnh theo semantics PostgreSQL. Nếu `lock_timeout` bằng hoặc lớn hơn `statement_timeout`, statement timeout có thể kích hoạt trước và làm hạn mức chờ lock ít hữu dụng. Cần định nghĩa hai ngưỡng nhất quán với SLA.

## 14. `57014`: query_canceled và statement_timeout

`57014 query_canceled` là mã có thể xuất hiện khi client hủy truy vấn hoặc PostgreSQL hủy statement do timeout. **Không tự suy ra nguyên nhân từ SQLSTATE một mình**.

### 14.1. Demo statement_timeout

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

-- Câu sau cố tình kéo dài hơn giới hạn:
-- SELECT pg_sleep(2);

ROLLBACK;
```

Nếu bỏ comment `SELECT pg_sleep(2)`, PostgreSQL thường hủy truy vấn vì quá một giây và trả `57014`. Transaction cần rollback trước khi tiếp tục.

### 14.2. Cùng mã nhưng hai ngữ cảnh rất khác

- **Người dùng nhấn Cancel:** đừng tự chạy lại query họ đã yêu cầu dừng.
- **Service đặt statement timeout do SLA:** retry chỉ có ích nếu có thay đổi điều kiện, ngân sách thời gian và operation idempotent; không lặp lại câu query luôn cần 30 giây dưới timeout 1 giây.
- **Admin/job cancellation:** xem nguyên nhân vận hành và có thể không được phép replay ngay.

### 14.3. Kết nối vẫn có thể sống, nhưng transaction đã failed

Một `57014` không luôn có nghĩa socket đã đóng. Driver có thể tiếp tục dùng connection sau `ROLLBACK` phù hợp. Không “đập bỏ pool” mỗi lần query bị cancel; đồng thời không sử dụng transaction đã thất bại như thể bình thường.

### 14.4. Timeout nhiều tầng

Ứng dụng thường có:

```text
HTTP/request deadline
   └── JDBC query timeout
          └── PostgreSQL statement_timeout
                 └── PostgreSQL lock_timeout
```

Các hạn mức nên phối hợp để tầng trong còn cơ hội dừng công việc trước khi tầng ngoài mất kiên nhẫn. Khi deadline tổng đã hết, backoff rồi retry có thể chỉ kéo dài lỗi và gây quá tải.

## 15. Xem transactions và blocking trong PostgreSQL

### 15.1. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    clock_timestamp() - query_start AS query_elapsed,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Khi có contention, `wait_event_type='Lock'` thường là tín hiệu hữu ích. Không phải mọi query chậm đều đang đợi lock: có thể là CPU, I/O, plan kém hoặc external network.

### 15.2. Xác định blocker PIDs

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

### 15.3. pg_locks

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
WHERE l.relation = 'retry_lab.deadlock_test'::regclass
ORDER BY l.pid, l.mode;
```

Không mong mọi row-level lock đều hiển thị trực tiếp như một dòng relation lock dễ đọc; PostgreSQL có nhiều loại lock và cách biểu diễn việc chờ. Đọc cùng `pg_stat_activity` và `pg_blocking_pids`.

### 15.4. Log lỗi gốc trước `25P02`

Trong một chuỗi sự kiện có `23505` rồi `25P02`, nguyên nhân gốc là `23505`. Hãy ghi lại exception đầu tiên cùng operation ID và transaction attempt. Không chỉ lưu lỗi cuối cùng rồi kết luận server “bị kẹt transaction”.

## 16. `Class 08`: connection failure không đồng nghĩa retry operation an toàn

`08006`, `08003` và các mã cùng nhóm nói về đường kết nối client–server. Khi connection hỏng:

- Một `SELECT` chưa có side effect thường có thể chạy lại trên connection mới nếu deadline còn.
- Một explicit transaction chưa gửi COMMIT thường sẽ rollback nếu session bị chấm dứt; nhưng phía ứng dụng vẫn cần phân biệt từng giai đoạn và các tác động ngoài DB.
- Nếu client đã gửi một statement autocommit DML hoặc `COMMIT` rồi mất response, **không biết chắc kết quả đã được commit hay chưa**.

### 16.1. Mất phản hồi không chứng minh server rollback

```text
Client                  Network               PostgreSQL
  |                        |                        |
  |---- COMMIT ----------->|----------------------->|
  |                        |                   commit thành công
  |                        X<---- response OK -------|
  |<-- connection error ---|
  |
  | App nghĩ "lỗi" nhưng DB đã áp thay đổi
```

Một nhánh khác là COMMIT chưa đến server hoặc server crash trước commit. Từ lỗi socket ở client, hai nhánh có thể không phân biệt được nếu không có hệ thống theo dõi kết quả.

### 16.2. Không tự retry COMMIT trên connection mới

Transaction cũ gắn với session/connection cũ. Một connection mới không thể “tiếp tục COMMIT transaction cũ” như tiếp tục một hàm Java chưa chạy xong. Muốn phục hồi, phải **reconcile trạng thái bền vững** và nếu cần thực thi lại **cùng business operation ID** trong một transaction mới theo giao thức idempotent.

### 16.3. Connection pool không bảo đảm idempotency

HikariCP, PgBouncer hoặc proxy có thể tạo kết nối khác, nhưng chúng không biết nghiệp vụ “chuyển 100” đã thành công chưa. Pool có thể xử lý socket hỏng; **ứng dụng** phải xử lý outcome và duplicate operations.

### 16.4. Kết nối tới read replica

Nếu sau mất kết nối, ứng dụng đọc operation ID từ một replica có replication lag, có thể chưa thấy bản ghi vừa commit trên primary. “Không thấy trên replica” **không chứng minh** operation thất bại. Quy trình reconciliation cần đọc nguồn đủ nhất quán (thường là primary hoặc consistency mechanism đã thiết kế).

### 16.5. Failover và tính chắc chắn

Failover có thể làm thay đổi dữ liệu đã visible tùy replication/durability configuration, đặc biệt asynchronous replication. Idempotency key giúp tránh replay trùng trên một trạng thái authoritative, nhưng chính sách failover và RPO vẫn phải được định nghĩa; không tuyên bố mọi commit “đã phản hồi” chắc chắn tồn tại sau mọi kiểu failover không đồng bộ.

## 17. Idempotency là gì?

Một thao tác có tính **lặp an toàn (idempotent)** nếu gửi lại **cùng thao tác logic** không khiến tác dụng nghiệp vụ được áp thêm lần nữa, dù có thể có khác biệt ở metadata, log hoặc thời gian xử lý.

### 17.1. So sánh ba SQL statements

```sql
-- Cập nhật giá trị đích giống nhau sau nhiều lần chạy:
UPDATE retry_lab.sample_items
SET quantity = 10
WHERE item_id = 1;

-- Không idempotent theo giá trị cuối:
UPDATE retry_lab.sample_items
SET quantity = quantity + 10
WHERE item_id = 1;

-- Chèn mới có nguy cơ nhân bản nếu thiếu uniqueness:
INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES (10, 'SKU-C', 10);
```

Đoạn trên minh họa ý nghĩa; chạy nhiều lần trên lab sẽ làm dữ liệu thay đổi và dòng INSERT có thể bị `23505` do PK/UNIQUE. Lặp `SET quantity=10` có giá trị cuối giống nhau, nhưng trigger, updated_at, WAL và audit **vẫn có thể chạy lại**.

### 17.2. Idempotency theo nghiệp vụ mạnh hơn “SET cùng giá trị”

Một API chuyển tiền có thao tác `balance = balance - 100`, vốn không idempotent. Ta tạo **business operation ID** để hệ thống áp trừ tiền **tối đa một lần cho ID đó**.

```text
POST /transfers
Idempotency-Key: 7c9e... (ổn định)
Payload: {from:1, to:2, amount:100}

Lần 1: thực thi thành công nhưng response mất
Lần 2: cùng key và cùng payload
        → trả lại trạng thái kết quả đã lưu
        → KHÔNG trừ tiền lần hai
```

### 17.3. Ba điều kiện thiết kế

1. **Key duy nhất và ổn định** cho cùng một yêu cầu logic, kể cả retry của HTTP client, queue consumer hoặc transaction.
2. **Bản ghi kết quả bền vững** có uniqueness và được commit **cùng transaction** với thay đổi nghiệp vụ.
3. **So sánh payload**: cùng key nhưng số tiền/tài khoản khác là lỗi conflict, không được trả success mù hoặc áp thao tác mới.

### 17.4. Idempotency không tự cung cấp exactly-once delivery

Client/network/broker vẫn có thể gửi cùng message nhiều lần. Mục tiêu thực tế là **at-least-once delivery với idempotent processing**, hoặc “effectively once” trên một business operation trong phạm vi đã thiết kế. Không tuyên bố mọi side effect bên ngoài PostgreSQL luôn exactly-once nếu bên nhận không hỗ trợ deduplication.

## 18. Thiết kế bảng lưu kết quả có khóa duy nhất

Bảng lab `transfer_requests` có:

```sql
request_id uuid PRIMARY KEY
```

Mỗi key có tối đa một row. Row lưu:

- `from_account`, `to_account`, `amount`: các trường xác định request.
- `status`: `processing`, `applied`, `insufficient_funds`.
- `result_note`: thông tin kết quả có thể trả lại.
- `completed_at`: thời điểm kết quả terminal được ghi.

### 18.1. Cùng key, payload khác phải bị từ chối

Giả sử hai requests:

```text
Request A:
  request_id = 1111...
  from=1, to=2, amount=100

Request B:
  request_id = 1111...
  from=1, to=3, amount=900
```

Nếu chỉ dùng `ON CONFLICT DO NOTHING` rồi trả kết quả cũ, request B sẽ nhận một phản hồi không tương ứng với yêu cầu. Hợp đồng phải quy định **409 Idempotency-Key Conflict** hoặc lỗi tương đương khi key đã dùng với payload không giống.

### 18.2. Payload canonicalization

Nếu idempotency dựa trên request hash, cần canonicalization nhất quán:

- Sắp/chuẩn hóa các trường tương ứng, không hash raw JSON string với thứ tự keys biến động.
- Quy định precision của amount (ví dụ `100.00` và `100` có được xem là cùng giá trị?).
- Định danh user/tenant trong phạm vi key, tránh key của tenant khác va chạm.
- Bảo vệ secret/token của request trong logs.

Trong lab, ta so sánh **trực tiếp ba cột** `from_account`, `to_account`, `amount` để tránh cần một hash canonicalization riêng.

### 18.3. Scope của request_id

Với UUID toàn cục và PRIMARY KEY, hai tenants dùng cùng UUID sẽ conflict. Đây có thể là lựa chọn hợp lý nếu UUID đủ ngẫu nhiên và ứng dụng kiểm tra quyền truy vấn kết quả. Trong hệ thống khác có thể dùng `UNIQUE(tenant_id, request_key)` để key chỉ duy nhất **trong tenant**. Quan trọng là ranh giới bảo mật phải rõ và backend không tiết lộ kết quả yêu cầu của tenant khác.

### 18.4. Không dùng số sequence làm kết luận retry

PostgreSQL `nextval()` có thể tạo khoảng trống khi transaction rollback hoặc upsert conflict. Sequence gaps không chứng minh có hai lần xử lý business request; hãy kiểm tra **row result và ledger theo operation ID**.

## 19. Giao thức xử lý chuyển tiền an toàn khi retry

Ta triển khai **một transaction PostgreSQL** gồm:

1. Reserve `request_id` với `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
2. Nếu key đã có, **không ghi lại**; đọc kết quả hiện có và so sánh payload.
3. Nếu key mới, debit tài khoản nguồn bằng `UPDATE ... WHERE balance >= amount`.
4. Nếu thiếu tiền, lưu trạng thái terminal `insufficient_funds` và COMMIT, không credit.
5. Nếu debit thành công, credit tài khoản đích, ghi ledger và outbox.
6. Ghi `status='applied'` rồi COMMIT.
7. Chỉ trả success sau khi COMMIT được xác nhận; nếu kết nối mất, reconcile bằng request ID.

### 19.1. Sơ đồ

```text
BEGIN
  |
  v
INSERT request_id ... ON CONFLICT DO NOTHING RETURNING
  |
  +-- 0 rows -> STOP write path
  |             đọc existing request, so payload/status
  |             trả kết quả cũ hoặc báo key conflict
  |
  +-- 1 row mới
          |
          v
      UPDATE source balance >= amount RETURNING
          |
          +-- 0 rows -> ghi insufficient_funds -> COMMIT
          |
          +-- 1 row -> UPDATE target
                         -> INSERT ledger UNIQUE(request_id)
                         -> INSERT outbox UNIQUE(request_id,event_type)
                         -> ghi applied -> COMMIT
```

**Đây là state machine ở tầng ứng dụng**, không phải một script SQL có thể chạy vô điều kiện từ đầu đến cuối. App phải kiểm tra kết quả của từng statement và chọn nhánh.

### 19.2. Bước 1: reserve request ID

Ví dụ request:

```text
request_id = 00000000-0000-4000-8000-000000000101
from_account = 1
to_account = 2
amount = 100.00
```

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id,
    from_account,
    to_account,
    amount,
    status
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

Nếu `RETURNING` trả **1 row**, transaction này đã reserve key mới. Nếu trả **0 rows**, **không chạy các bước debit/credit dưới đây**; thay vào đó `ROLLBACK` transaction hiện tại và tra cứu kết quả cũ trong một transaction/query phù hợp.

### 19.3. Bước 2: debit có điều kiện, không cho số dư âm

Chỉ chạy nếu bước 1 trả 1 row:

```sql
UPDATE retry_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00
RETURNING account_id, balance;
```

Với dataset ban đầu, câu UPDATE trả account 1 và số dư **900.00**. Predicate `balance >= 100.00` được xét trong cơ chế UPDATE/row locking, giúp tránh trừ quá số dư trong những transaction cạnh tranh theo semantics PostgreSQL.

**Nếu UPDATE trả 0 rows:**

```sql
UPDATE retry_lab.transfer_requests
SET
    status = 'insufficient_funds',
    result_note = 'Insufficient balance',
    completed_at = clock_timestamp()
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

COMMIT;
```

Lúc đó không chạy credit/ledger/outbox nhánh thành công. Đối với một request ID đã có kết quả `insufficient_funds`, những lần retry cùng key trả lại kết quả từ chối đã lưu; nếu user nạp thêm tiền và muốn thử chuyển tiền **lần mới**, phải dùng operation key mới theo hợp đồng API.

**Trong đường thành công của lab** (debit đã trả 1 row), **không chạy block insufficient_funds**; tiếp tục bước 3.

### 19.4. Bước 3: credit tài khoản đích

```sql
UPDATE retry_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 2
RETURNING account_id, balance;
```

Với dataset ban đầu, account 2 thành **600.00**. Câu lệnh phải ảnh hưởng đúng 1 row, nếu 0 hoặc lỗi thì **ROLLBACK toàn transaction**, không COMMIT riêng debit.

### 19.5. Bước 4: ghi ledger duy nhất theo request ID

```sql
INSERT INTO retry_lab.transfer_ledger (
    request_id,
    from_account,
    to_account,
    amount
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00
)
RETURNING ledger_id, request_id;
```

Ràng buộc `UNIQUE(request_id)` là một **lớp bảo vệ thứ hai** chống ghi ledger trùng cho cùng thao tác logic. Nếu lỗi unexpected, **không** nuốt lỗi và tiếp tục COMMIT các thay đổi debit/credit thiếu nhất quán.

### 19.6. Bước 5: ghi outbox event

```sql
INSERT INTO retry_lab.outbox_events (
    request_id,
    event_type,
    payload
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    'transfer_applied',
    jsonb_build_object(
        'request_id',
        '00000000-0000-4000-8000-000000000101',
        'from_account', 1,
        'to_account', 2,
        'amount', 100.00
    )
);
```

Event nằm trong **cùng DB transaction** với debit/credit/ledger. Nó chưa đồng nghĩa đã gửi đến broker hoặc nhận ở ứng dụng khác.

### 19.7. Bước 6: ghi kết quả terminal và COMMIT

```sql
UPDATE retry_lab.transfer_requests
SET
    status = 'applied',
    result_note = 'Transfer completed',
    completed_at = clock_timestamp()
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

COMMIT;
```

Nếu server trả COMMIT thành công, cả marker, debit, credit, ledger và outbox đều được commit cùng nhau.

### 19.8. Kết quả sau lần chạy thành công

```sql
SELECT account_id, balance
FROM retry_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

SELECT request_id, from_account, to_account,
       amount, status, completed_at
FROM retry_lab.transfer_requests
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

SELECT COUNT(*) AS ledger_rows
FROM retry_lab.transfer_ledger
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';
```

Nếu dataset ban đầu chưa từng bị sửa và nhánh thành công đã commit: balances là **900/600**, marker `applied` và ledger count = **1**.

### 19.9. Vì sao không COMMIT marker 'processing' trước?

Trong mẫu này, marker, các thay đổi tài khoản và trạng thái kết quả terminal **cùng một transaction**. Những transaction khác không nhìn thấy marker `processing` chưa commit. Nếu marker được commit riêng trước rồi worker chết, hệ thống có thể bị kẹt ở trạng thái processing mãi và cần lease/recovery protocol phức tạp hơn.

Đó không phải thiết kế luôn cấm trạng thái processing đã commit; nhưng nếu chọn two-phase processing, phải có **lease timeout, ownership, retry và compensation** rõ ràng. Bài lab chọn giao thức atomic đơn giản.

## 20. Retry cùng request_id sau thành công

Giả sử chuyển tiền với ID `00000000-0000-4000-8000-000000000101` đã COMMIT. Client mất response nên gửi **lại cùng key và cùng payload**.

### 20.1. Reserve key lần nữa

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id,
    from_account,
    to_account,
    amount,
    status
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

Lệnh trả **0 rows** vì key đã tồn tại. Đây là tín hiệu **không chạy debit/credit** lần nữa.

### 20.2. Rollback đường write và đọc lại kết quả

```sql
ROLLBACK;

SELECT
    request_id,
    from_account,
    to_account,
    amount,
    status,
    result_note,
    completed_at
FROM retry_lab.transfer_requests
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';
```

Backend so sánh ba trường account/amount với request hiện tại:

- Nếu cùng payload và `status='applied'` → trả **kết quả chuyển tiền cũ đã lưu**, không gửi lại lệnh trừ tiền.
- Nếu cùng payload và `status='insufficient_funds'` → trả kết quả từ chối cũ.
- Nếu payload khác → lỗi reuse idempotency key.
- Nếu trạng thái `processing` đã commit xuất hiện ngoài thiết kế này → không coi đó là success; xem xét stale lease/recovery protocol.

### 20.3. Idempotency không phải “mọi duplicate đều thành công”

Một request A có key K, amount 100; request B dùng cùng K nhưng amount 900 phải **bị từ chối**, không phải mặc nhiên trả thành công của A. Điều này bảo vệ cả client khỏi tái sử dụng key sai.

### 20.4. Nếu key chưa tồn tại thì sao?

Sau một connection failure, `SELECT` từ primary không thấy key **không luôn chứng minh một attempt đang bay chưa có khả năng commit**. Có thể request cũ chưa hoàn tất; sự kiện commit trong flight hoặc job chưa nhận request. Backend cần retry/reconcile theo cùng **ID**, để ràng buộc UNIQUE quyết định chỉ một transaction thành công.

### 20.5. Khi hai requests trùng key đến đồng thời

Session A:

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id, from_account, to_account, amount, status
)
VALUES (
    '00000000-0000-4000-8000-000000000202',
    1, 2, 25.00, 'processing'
);
-- Giữ transaction chưa COMMIT.
```

Session B:

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id, from_account, to_account, amount, status
)
VALUES (
    '00000000-0000-4000-8000-000000000202',
    1, 2, 25.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

Session B có thể **đợi** kết quả transaction A vì unique key đang tranh chấp. Nếu A COMMIT, B thường thấy conflict và RETURNING 0 rows. Nếu A ROLLBACK, B có thể chèn được key và trở thành owner của attempt.

Đây là lợi ích quan trọng của **UNIQUE constraint ở database**; một `SELECT COUNT(*)` trước INSERT mà không có uniqueness sẽ không an toàn vì hai sessions có thể cùng thấy “chưa có” rồi cùng xử lý.

### 20.6. Dọn demo hai session

Không dùng các câu chuyển tiền sau khi chỉ reserve ID `...202` trong session A/B; đây là thí nghiệm về UNIQUE lock. Hãy kết thúc:

```sql
ROLLBACK;
```

ở những sessions còn mở; nếu Session B đang chờ, kết thúc A trước rồi kiểm tra kết quả B, sau đó ROLLBACK B. Nếu A đã COMMIT một marker `processing` của demo thì cần xử lý dữ liệu test theo quy trình quản trị riêng; đừng nhập marker dở này vào business flow thật.

### 20.7. READ COMMITTED và visibility sau DO NOTHING

Trong PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` có thể không chèn vì một transaction cạnh tranh mà row conflict chưa hiện hữu trong snapshot của **cùng statement**. Ở `READ COMMITTED`, một `SELECT` ở statement kế tiếp có thể nhận snapshot mới để thấy kết quả đã COMMIT. Vì vậy protocol không giả định `DO NOTHING RETURNING 0` sẽ luôn đi kèm một row visible trong **cùng statement**.

Để đơn giản, ví dụ chủ động kết thúc attempt hiện tại rồi đọc trạng thái trong một transaction/query mới sau khi conflict đã được giải quyết. Với `REPEATABLE READ`/`SERIALIZABLE` cần tuân thủ snapshot/retry semantics của isolation đó.

## 21. Commit outcome unknown: trạng thái thứ ba ngoài success/failure

Trong các API có side effect, kết quả một attempt không chỉ có hai trạng thái “success” và “failure”. Cần tính đến:

| Trạng thái client | Ý nghĩa |
| --- | --- |
| **Confirmed success** | Server phản hồi COMMIT thành công hoặc đã reconcile được bản ghi terminal đúng request ID. |
| **Confirmed failure/rollback** | Nhận lỗi có ngữ nghĩa transaction đã rollback/không được commit, hoặc kết quả nghiệp vụ terminal từ chối. |
| **Unknown outcome** | Mất response/network trước khi xác minh được transaction đã commit hay chưa. |

### 21.1. Vì sao unknown không được ép thành failed?

Nếu database đã COMMIT nhưng response bị rơi, đánh dấu failed rồi tạo request ID mới để “thử lại” có thể tạo giao dịch mới hợp lệ, và tiền bị trừ **lần thứ hai**.

### 21.2. Không khẳng định success khi chỉ thấy kết nối ổn

Connection được pool thay và ping thành công không nói gì về transaction trước đó. Phải đọc **business result theo ID** từ authoritative store.

### 21.3. Giao thức phục hồi

```text
Mất response ở COMMIT
         |
         v
Giữ nguyên request_id, KHÔNG sinh key mới
         |
         v
Mở connection mới đến nguồn nhất quán
         |
         v
SELECT transfer_requests WHERE request_id = K
         |
         +-- APPLIED/REJECTED & payload match
         |       -> trả lại kết quả đã lưu
         |
         +-- Key tồn tại nhưng payload mismatch
         |       -> lỗi conflict / security incident
         |
         +-- Không thấy / chưa rõ
                 -> chờ ngắn/backoff hoặc thử lại
                    nguyên business operation với K
                    theo giao thức UNIQUE atomic
```

### 21.4. Reconciliation cần hạn thời gian

Không nên để API chờ vô hạn. Có thể trả `202 Accepted`/“pending verification” theo hợp đồng rồi cho client tra cứu `GET /transfers/by-request-id/K`; hoặc trả lỗi tạm thời với chỉ dẫn **retry bằng cùng key**. API phải mô tả rõ client được phép resend thế nào.

### 21.5. Không lấy “không thấy marker” từ replica lag làm rollback

Khi primary vừa commit, một replica bất đồng bộ có thể chưa replay WAL. Lookup kết quả phải tuân theo mức consistency của quá trình phục hồi, thường ưu tiên primary/authoritative writer.

### 21.6. Các mã kết nối không phân biệt được tất cả đường đi

`08006`, IOException, connection reset và socket timeout có thể được driver/wrapper diễn đạt khác. Nếu mất response khi COMMIT hoặc autocommit write, hãy phân loại theo **outcome ambiguous** dù không có mã PostgreSQL cụ thể.

## 22. Outbox: không gửi email/sự kiện trực tiếp giữa các lần retry transaction

Giả sử sau mỗi transfer cần thông báo cho hệ thống khác. Không làm:

```text
BEGIN
UPDATE accounts
HTTP POST đến hệ thống thông báo
COMMIT
```

Nếu COMMIT gặp `40001`/`40P01` và transaction bị rollback, HTTP POST **không thể rollback cùng**. Retry toàn transaction có thể gửi thông báo hai lần.

### 22.1. Transactional outbox

```text
BEGIN PostgreSQL
  UPDATE accounts
  INSERT ledger
  INSERT transfer_requests result
  INSERT outbox_events
COMMIT
      |
      v
Outbox worker đọc event chưa published
      |
      v
Gửi event đến broker/API ngoài
      |
      v
Đánh dấu trạng thái gửi / retry
```

Đây là nguyên tắc **atomic commit trong DB, giao hàng bất đồng bộ ra ngoài**.

### 22.2. Worker lấy batch events

Một mẫu claim event theo batch:

```sql
BEGIN;

SELECT event_id, request_id, event_type, payload
FROM retry_lab.outbox_events
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Đây là một bước chọn/khóa cho worker.
-- Nếu không hoàn thành xử lý, ROLLBACK để giải phóng locks.
ROLLBACK;
```

`SKIP LOCKED` giúp nhiều workers không cùng claim những row đang được lock, nhưng **không** tự đảm bảo exactly-once delivery nếu worker crash sau khi remote nhận sự kiện.

### 22.3. Crash ở ranh giới broker

```text
Worker gửi event K -> broker nhận và xử lý
         |
         X  Worker crash trước khi UPDATE published_at
         |
         v
Worker mới thấy K chưa published -> gửi lại K
```

Giải pháp: bên nhận phải có **idempotency/consumer deduplication** theo `event_id` hoặc `request_id + event_type`. Outbox không tự biến delivery thành exactly-once.

### 22.4. Idempotency của consumer

Ví dụ consumer lưu:

```sql
CREATE TABLE retry_lab.processed_events (
    consumer_name text NOT NULL,
    event_id bigint NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong transaction của consumer, thử chèn `(consumer_name,event_id)` bằng `ON CONFLICT DO NOTHING RETURNING`; nếu 0 rows thì không áp side effect database lần nữa. Nếu consumer còn gọi hệ thống ngoài, phải kết hợp idempotency protocol của hệ thống ngoài hoặc workflow tương ứng.

### 22.5. Đừng giữ transaction DB chờ API ngoài lâu

Việc lấy `FOR UPDATE` rồi giữ transaction mở trong suốt lời gọi mạng nhiều giây có thể tăng lock contention. Trong production thường dùng mô hình **claim/lease** trên outbox, commit claim, gửi ngoài, sau đó ghi success/failure, kèm timeout và retry. Điều đó phức tạp hơn đoạn lab và cần bảo vệ khỏi hai workers cùng claim khi lease hết hạn.

### 22.6. Tách kết quả nghiệp vụ khỏi delivery status

Transfer có thể đã `applied` trong PostgreSQL nhưng event `transfer_applied` chưa tới consumer. Đừng đảo ngược transfer chỉ vì một thông báo gửi chậm nếu business contract không yêu cầu. Ghi nhận **business commit state** và **notification delivery state** riêng.

## 23. Đọc SQLSTATE bằng JDBC

Trong Java, `java.sql.SQLException` cung cấp:

```java
String sqlState = exception.getSQLState();
int vendorCode = exception.getErrorCode();
String message = exception.getMessage();
```

Đối với pgJDBC, `getSQLState()` là nguồn chính cho việc phân loại mã PostgreSQL. `getErrorCode()` là mã số riêng theo driver/server (nếu có), **không thay cho SQLSTATE** trong mô hình này.

### 23.1. Mẫu bắt lỗi

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class StockReader {
    private final DataSource dataSource;

    public StockReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int readQuantity(int itemId) throws SQLException {
        String sql =
            "SELECT quantity " +
            "FROM retry_lab.sample_items " +
            "WHERE item_id = ?";

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setInt(1, itemId);
            try (var rs = ps.executeQuery()) {
                return rs.next() ? rs.getInt(1) : -1;
            }
        } catch (SQLException ex) {
            String state = ex.getSQLState();
            // Log cấu trúc: state, operation name, correlation ID.
            // Không gửi chi tiết DB (SQL, keys, constraint values)
            // trực tiếp về response công khai.
            throw ex;
        }
    }
}
```

Đoạn này dùng `var` của Java 10+ trong try-with-resources; nếu dùng Java cũ, khai báo `ResultSet` tường minh. Quan trọng nhất là `getSQLState()` và việc không nuốt exception.

### 23.2. SQLSTATE có thể null

Khi lỗi bắt nguồn từ client/network trước khi nhận phản hồi server, SQLSTATE có thể `null` hoặc không đủ thông tin. Code không được gọi `state.startsWith(...)` khi state là null.

### 23.3. SQLException chain

`SQLException` có `getNextException()`; frameworks cũng có thể bọc lỗi ở `cause`. Khi log, hãy giữ thông tin về original exception và SQLSTATE của nested SQL exception thích hợp, nhưng đừng “lấy mã đầu tiên bất kỳ” nếu nó che lỗi gốc.

### 23.4. PostgreSQL-specific diagnostics

Khi sử dụng pgJDBC, `org.postgresql.util.PSQLException` có thể chứa `ServerErrorMessage`:

```java
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

static void inspectConstraint(SQLException ex) {
    if (ex instanceof PSQLException) {
        PSQLException pgEx = (PSQLException) ex;
        ServerErrorMessage server = pgEx.getServerErrorMessage();
        if (server != null) {
            String constraint = server.getConstraint();
            String table = server.getTable();
            // Chỉ dùng metadata có sẵn để log/categorize
            // theo allowlist, không tiết lộ cho public client.
        }
    }
}
```

Không phải mọi lỗi đều có `ServerErrorMessage` hoặc constraint name; đừng dựa vào đó để nhận diện lỗi mạng.

### 23.5. Vì sao không parse message?

Một test so sánh `ex.getMessage().contains("deadlock detected")` dễ vỡ vì localization, proxy, driver format, thay đổi wording và nested exceptions. Dùng `"40P01".equals(ex.getSQLState())` rõ ràng hơn.

## 24. Viết bộ phân loại SQLSTATE

Không nên dùng một boolean `isRetryable(error)` cho mọi trường hợp. Hãy trả về **quyết định có ngữ nghĩa**:

```java
import java.sql.SQLException;

public final class PgErrorClassifier {
    public enum Action {
        RETRY_WHOLE_TRANSACTION,
        RETRY_CONTENTION_IF_DEADLINE,
        RESOLVE_BUSINESS_CONFLICT,
        CHECK_CANCEL_OR_TIMEOUT,
        CONNECTION_OUTCOME_UNKNOWN,
        ROLLBACK_ABORTED_TRANSACTION,
        FIX_INPUT_OR_CONFIGURATION,
        INVESTIGATE
    }

    public static Action classify(SQLException error) {
        String state = error.getSQLState();

        if (state == null || state.length() != 5) {
            return Action.INVESTIGATE;
        }

        switch (state) {
            case "40001": // serialization_failure
            case "40P01": // deadlock_detected
                return Action.RETRY_WHOLE_TRANSACTION;
            case "55P03": // lock_not_available
                return Action.RETRY_CONTENTION_IF_DEADLINE;
            case "57014": // query_canceled
                return Action.CHECK_CANCEL_OR_TIMEOUT;
            case "23505": // unique_violation
            case "23P01": // exclusion_violation
                return Action.RESOLVE_BUSINESS_CONFLICT;
            case "25P02": // in_failed_sql_transaction
                return Action.ROLLBACK_ABORTED_TRANSACTION;
            case "23502":
            case "23503":
            case "23514":
            case "22P02":
            case "22003":
            case "42501":
            case "42P01":
            case "42703":
            case "42601":
                return Action.FIX_INPUT_OR_CONFIGURATION;
            default:
                if (state.startsWith("08")) {
                    return Action.CONNECTION_OUTCOME_UNKNOWN;
                }
                return Action.INVESTIGATE;
        }
    }
}
```

Đây là **bước phân loại sơ bộ**, không phải hệ thống retry hoàn chỉnh. `CONNECTION_OUTCOME_UNKNOWN` nói rằng **cần xem stage/side effect**: có những lỗi kết nối xảy ra trước khi SQL được gửi (không có commit nào), có lỗi xảy ra sau khi commit đã được gửi.

### 24.1. Không tự retry theo class `40` chung

Chỉ những mã đã được phân tích như `40001`/`40P01` mới vào nhánh retry whole transaction. Nếu gặp một mã `40xxx` khác, hãy kiểm tra ý nghĩa, không mặc định replay.

### 24.2. Đừng giả định mọi `SQLTransientException` là an toàn

Java có các subclass SQL exception về tính tạm thời, nhưng pgJDBC/framework không nhất thiết ánh xạ mọi SQLSTATE giống nhau. “Transient” ở lớp kết nối không giải quyết câu hỏi **side effect đã commit hay chưa**.

### 24.3. Classifier phải thêm ngữ cảnh

Một hệ thống hoàn thiện cần:

```text
Decision = f(
    SQLSTATE,
    SQL command / operation,
    transaction stage,
    commit attempted?,
    idempotency protocol?,
    request deadline,
    retry attempt count,
    isolation level,
    user cancellation?
)
```

Ví dụ `57014` do người dùng chủ động cancel phải được xử lý khác `55P03` do một job gặp lock bận.

## 25. Mẫu retry transaction bằng JDBC

Một wrapper retry an toàn cần:

1. Mở **connection/transaction mới** cho mỗi attempt.
2. Chạy lại **toàn bộ** business SQL và các điều kiện đọc/quyết định.
3. Rollback khi attempt thất bại.
4. Không gọi API ngoài hoặc gửi email thật bên trong phần work có thể chạy nhiều lần.
5. Giữ **operation ID cố định** cho toàn bộ attempts.
6. Dừng khi hết attempts, deadline hoặc bị cancel.
7. Nếu kết nối mất khi commit, chuyển sang **reconciliation**, không coi đó là lỗi transaction chắc chắn rollback.

### 25.1. Ví dụ Java: retry `40001` và `40P01`

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import java.util.concurrent.ThreadLocalRandom;

public final class SerializableTransactionRunner {
    @FunctionalInterface
    public interface Work<T> {
        T run(Connection c) throws SQLException;
    }

    private final DataSource dataSource;
    private static final int MAX_ATTEMPTS = 4;

    public SerializableTransactionRunner(DataSource ds) {
        this.dataSource = ds;
    }

    public <T> T execute(Work<T> work)
            throws SQLException, InterruptedException {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            boolean retry = false;

            try (Connection c = dataSource.getConnection()) {
                c.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );
                c.setAutoCommit(false);

                try {
                    // Có thể chạy nhiều lần: không side effect ngoài DB.
                    T result = work.run(c);
                    c.commit();
                    return result;
                } catch (SQLException ex) {
                    try {
                        c.rollback();
                    } catch (SQLException rollbackError) {
                        ex.addSuppressed(rollbackError);
                    }

                    String state = ex.getSQLState();
                    retry = ("40001".equals(state)
                            || "40P01".equals(state))
                            && attempt < MAX_ATTEMPTS;

                    if (!retry) {
                        // Với lỗi kết nối khi COMMIT, caller phải
                        // reconcile bằng request_id/idempotency.
                        throw ex;
                    }
                }
            }

            // Connection đã đóng/trả về pool trước khi sleep.
            if (retry) {
                long baseMs = Math.min(100L << (attempt - 1), 800L);
                long jitterMs = ThreadLocalRandom.current()
                    .nextLong(0, 100);
                Thread.sleep(baseMs + jitterMs);
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
```

**Quan trọng:** Đây là mẫu tập trung vào `40001`/`40P01` để giải thích vòng retry. Không gọi nó như một transaction manager production hoàn chỉnh khi chưa bổ sung:

- **Request deadline** và cancellation từ HTTP/job.
- Connection/pool errors, timeouts khi lấy connection.
- Logging/metrics và retry budget toàn hệ thống.
- Reconciliation cho **commit outcome unknown**.
- Kiểm soát context transaction ở Spring/JTA và cleanup.
- Quy tắc tương tác với external side effects.

### 25.2. Vì sao rollback vẫn được gọi sau lỗi COMMIT?

Code cố rollback best-effort, nhưng khi COMMIT đã gửi và socket mất, một `rollback()` trên connection hỏng **không thể chứng minh COMMIT trước đó đã thất bại**. Nếu SQLSTATE là class `08` ở commit stage, caller phải giữ operation ID và reconcile. Không dùng “rollback không ném lỗi” làm bằng chứng request an toàn để phát lại bằng key mới.

### 25.3. Không “retry” lỗi dữ liệu

Wrapper trên chỉ retry đúng hai mã transaction conflict. Nếu work trả `23505`, `23514` hoặc `22P02`, exception được ném cho tầng business xử lý; không sleep rồi lặp cùng dữ liệu vô ích.

### 25.4. Chú ý retry ngay trên cùng transaction

Sau `40001`, transaction cũ đã hỏng. Phải bắt đầu transaction mới, thực hiện lại SELECT/logic. Không gọi `work.run(c)` một lần nữa trước rollback trên cùng transaction aborted.

### 25.5. Ngữ nghĩa của Thread.sleep

Trong service có nhiều requests, sleep ở request thread làm chiếm worker thread và có thể tăng latency. Hệ thống tải lớn có thể dùng delayed queue/async retry/worker scheduler để backoff; ví dụ đồng bộ trên chỉ là minh họa mechanics.

### 25.6. Retry không phải quyền thực thi hai request logic

Nếu work tạo một `UUID.randomUUID()` **mỗi lần attempt**, đó là nhiều business keys khác nhau. Hãy tạo key một lần ở tầng request rồi truyền vào `Work` của mọi lần retry. Nếu business operation đã có external side effects, phải có outbox/compensation.

## 26. Spring và transaction manager: retry ở đúng ranh giới

Trong Spring, `@Transactional` thường bao quanh một transaction được AOP/proxy quản lý. Một lỗi phổ biến là:

```java
@Transactional
public void pay() {
    try {
        updateAccount();
    } catch (Exception ex) {
        updateAccount(); // Thử lại trong transaction đã failed!
    }
}
```

Nếu `updateAccount()` gặp PostgreSQL serialization failure/deadlock, transaction hiện tại đã ở trạng thái cần rollback. Lặp câu SQL bên trong cùng phương thức `@Transactional` thường không tạo một transaction/snapshot mới và có thể chỉ nhận `25P02`.

### 26.1. Đặt retry bên ngoài transaction boundary

Mô hình khái niệm:

```text
API/controller
    |
    v
Retry coordinator (có operation ID, deadline)
    |
    +-- Attempt #1 -> Transactional service (BEGIN ... COMMIT/ROLLBACK)
    |                                  |
    |                           SQLSTATE 40001
    |
    +-- backoff
    |
    +-- Attempt #2 -> Transactional service (TRANSACTION MỚI)
                                       |
                                 success/commit
```

Spring có những cách triển khai như một lớp `RetryService` gọi bean khác có `@Transactional`, hoặc dùng `TransactionTemplate` để **mỗi attempt mở scope transaction mới**. Cần chú ý thứ tự interceptor của retry/transaction nếu dùng `@Retryable` và `@Transactional` cùng phương thức; đừng giả định annotation order luôn đúng.

### 26.2. Self-invocation qua Spring proxy

Một method nội bộ gọi `this.transactionalMethod()` có thể bỏ qua proxy transaction advice trong cấu hình AOP thông thường. Nếu retry/transaction được tách bằng method calls trong cùng bean mà thiếu proxy, attempts có thể không tạo transaction như kỳ vọng.

### 26.3. Framework có thể dịch SQLException

Spring có thể chuyển SQLException sang các lớp `DataAccessException`. Lớp exception được chọn có thể phụ thuộc translator/driver/framework version; không thiết kế bằng cách đoán chỉ từ một tên exception cụ thể. Nếu cần SQLSTATE, lấy nguyên nhân SQL exception được giữ trong chain hoặc sử dụng translator có hợp đồng kiểm soát.

### 26.4. Rollback theo exception type

Mặc định `@Transactional` của Spring có quy tắc rollback dựa trên loại exception (thường unchecked exceptions); những checked exceptions có thể cần cấu hình `rollbackFor` theo nghiệp vụ. Nếu handler nuốt exception và trả kết quả “thành công”, transaction manager có thể không rollback như bạn mong đợi.

### 26.5. Không gọi external API trong retryable transaction

Ngay cả khi Spring transaction rollback DB thành công, một HTTP request đã gửi tới hệ thống khác không tự rollback. Hãy ghi outbox event trong transaction, rồi gửi ngoài sau commit, kết hợp idempotency bên nhận.

### 26.6. JPA/Hibernate persistence context

Sau lỗi transaction, persistence context/EntityManager có thể ở trạng thái không nên tiếp tục dùng. Retry đúng là scope transaction/persistence context mới, không phải tiếp tục làm việc với entity cache của attempt đã rollback.

## 27. Backoff, jitter và retry budget

Thử lại cùng lúc ở hàng trăm workers có thể khiến database đang tải cao **càng quá tải**. Bởi vậy retry policy cần kiểm soát cường độ.

### 27.1. Exponential backoff

Một công thức tham khảo:

\[
\text{baseDelay}(n) = \min(D_{\max},D_0\cdot 2^{n-1})
\]

Ví dụ `D0=100ms`, `Dmax=800ms`:

| Attempt thất bại | Base delay trước lần kế tiếp |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |

Các giá trị **chỉ minh họa**. Retry count phải được giới hạn và không vượt deadline.

### 27.2. Jitter

Nếu 500 clients cùng nhận `40P01` rồi cùng ngủ đúng 100 ms, chúng có thể lại tranh chấp đồng loạt. Jitter thêm một thành phần ngẫu nhiên có giới hạn:

\[
\text{delay}=\min(D_{\max},D_0\cdot 2^{n-1})+\text{jitter}
\]

Một số chiến lược dùng full jitter trong khoảng từ 0 đến base delay. Không có một công thức tối ưu cho mọi workload; chọn dựa trên tài nguyên và SLA.

### 27.3. Retry budget theo request

Ví dụ API có deadline tổng 2 giây và mỗi attempt có thể chiếm 1,5 giây. Không thể thử 5 lần với sleep 100–800 ms rồi kỳ vọng vẫn trả đúng deadline. Hãy chia budget cho:

- Thời gian lấy connection.
- Thời gian query và lock wait.
- Thời gian COMMIT.
- Backoff.
- Reconciliation nếu commit outcome unknown.

### 27.4. Retry storm

`53300 too_many_connections` xảy ra khi hết connection slots. Nếu tất cả clients lập tức mở thêm connection rồi retry liên tục, tình trạng càng xấu. Giới hạn pool, queue work, admission control, backoff/jitter và cảnh báo hạ tầng.

### 27.5. Không retry khi bị người dùng hủy

Khi request context đã canceled hoặc deadline đã hết, scheduled retry nên dừng, trừ khi business workflow là một job bền vững có thỏa thuận tiếp tục độc lập với HTTP request. Không biến Cancel của user thành thêm ba attempts.

### 27.6. Circuit breaker và bulkhead

Với hệ thống đang gặp outage/overload dài, circuit breaker có thể tạm ngừng các requests mới không cần thiết, bulkhead giới hạn concurrency và job queue ưu tiên lại công việc. Đây là **các cơ chế cấp application/hệ thống**, không phải thay cho transaction/idempotency.

## 28. Timeout: các tầng cùng cần rõ ràng

| Tầng | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| HTTP | API request deadline | Có thể hết trước khi DB đã commit. |
| Connection pool | Acquisition timeout | Không biết có lấy được connection, thường chưa có SQL mới được gửi bởi request đó. |
| Network/socket | Read timeout/reset | Có thể mất phản hồi sau một write/COMMIT. |
| JDBC | Statement query timeout | Có thể yêu cầu cancel, nhưng bối cảnh transaction vẫn cần cleanup. |
| PostgreSQL | `statement_timeout` | Có thể phát `57014` và làm transaction thất bại. |
| PostgreSQL | `lock_timeout` | Có thể phát `55P03` do chờ lock. |
| PostgreSQL | `idle_in_transaction_session_timeout` | Có thể chấm dứt connection khi idle quá lâu trong transaction. |

### 28.1. Ví dụ timeout theo transaction

```sql
BEGIN;

SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '500ms';

SELECT account_id, balance
FROM retry_lab.accounts
WHERE account_id = 1;

COMMIT;
```

`SET LOCAL` chỉ áp trong transaction, giúp tránh lưu session setting sang request sau khi connection được trả về pool.

### 28.2. Không tự suy ra SQLSTATE từ tầng HTTP

HTTP request timeout có thể xảy ra khi DB vẫn đang chạy hoặc vừa commit. Một response HTTP 504 không đảm bảo `ROLLBACK` đã được thực hiện ở PostgreSQL. Khi application không thể xác định kết quả, giữ operation ID để phục hồi.

### 28.3. Thực thi async và tác dụng còn chạy

Trong một số môi trường, client bỏ chờ nhưng backend query vẫn chưa bị hủy ngay. Đừng tạo một job thứ hai cùng business operation với key mới chỉ vì HTTP client không còn đợi.

### 28.4. Cancellation là ngữ nghĩa nghiệp vụ

Nếu user hủy một bước **chưa commit**, có thể rollback. Nếu transaction đã commit, “hủy” có thể là một **compensating operation** riêng (ví dụ hoàn tiền), không phải đơn giản xóa dấu vết ở DB.

## 29. Lỗi connection/setup và resource exhaustion

### 29.1. Connection không thể thiết lập

`08001`, `08004`, `57P03` có thể xuất hiện trước khi một request mới bắt đầu DML. Lúc đó retry **kết nối** với backoff có thể hợp lý, đặc biệt khi server đang restart. Nhưng nếu request trước đó có COMMIT unknown, không được tự chuyển từ “retry connect” sang “replay payment bằng ID mới”.

### 29.2. Authentication/authorization

Sai mật khẩu hoặc thiếu quyền thường không tự biến mất sau 200 ms. `28P01` hoặc `42501` cần sửa credentials/GRANT/config. Vòng retry dày đặc có thể làm đầy log và kích hoạt cơ chế bảo vệ tài khoản.

### 29.3. Too many connections

`53300` cho biết connection slots đã hết. Tăng pool size ở mọi service đồng thời có thể làm lỗi nặng hơn. Kiểm tra:

- Max connections và pool size tổng.
- Idle connections/idle in transaction.
- Connection leaks.
- PgBouncer nếu phù hợp.
- Workload concurrency và queueing.

### 29.4. Disk full/out of memory

`53100`/`53200` thường là sự cố tài nguyên nghiêm trọng; cần alert, dọn/khôi phục tài nguyên và tránh retry storm. Không coi chúng như deadlock.

### 29.5. Read-only transaction

`25006` có thể do ghi vào read replica hoặc transaction đặt read-only. Chọn đúng primary/write connection và transaction mode. Đừng retry cùng write trên cùng replica vô hạn.

### 29.6. Undefined table/column

`42P01`/`42703` có thể do deploy application trước migration, thiếu search_path hoặc schema mismatch. Cần rollback/fix migration và version compatibility; không ngủ rồi retry vô hạn với SQL sai.

## 30. Monitoring: đo retry mà không che lỗi

Một hệ thống retry tốt cần chỉ số, không chỉ log “attempt 2”.

### 30.1. Metric gợi ý

| Metric | Ý nghĩa |
| --- | --- |
| `db_errors_total{sqlstate}` | Lỗi theo mã; cardinality labels phải kiểm soát. |
| `db_retry_attempts_total{operation,reason}` | Tổng attempts retry. |
| `db_retry_exhausted_total` | Số operations hết budget. |
| `db_transaction_duration_seconds` | Thời gian transaction theo histogram. |
| `db_lock_wait_seconds` | Thời gian đợi lock, nếu đo được. |
| `db_connection_acquire_seconds` | Pool acquisition delay. |
| `idempotency_duplicate_total` | Số lần gặp request ID đã xử lý. |
| `idempotency_key_conflict_total` | Số lần cùng key nhưng payload khác. |
| `commit_outcome_unknown_total` | Số lần phải reconcile. |
| `outbox_lag_seconds` | Độ trễ gửi event ngoài DB. |

### 30.2. Thông tin trong structured logs

Nên ghi:

```text
operation_type
request_id / correlation_id (đã xử lý bảo mật)
transaction_attempt
sqlstate
error_classification
transaction_stage
retry_decision
backoff_ms
elapsed_ms
result_status
```

Không log raw passwords, full SQL bind values chứa dữ liệu cá nhân/tài chính hoặc entire server error details ra kênh công khai.

### 30.3. Phân biệt 23505 business conflict với duplicate idempotency

Hai số liệu khác nhau:

- `business_conflict`: khách đặt SKU/email không hợp lệ vì thực sự trùng tài nguyên.
- `duplicate_request`: cùng business operation đã được xử lý, nên trả lại kết quả cũ.

Nếu đo cả hai chỉ bằng “số lần SQLSTATE 23505”, bạn có thể bỏ lỡ lỗi thiết kế retry hoặc nhầm client resend hợp lệ thành lỗi hệ thống.

### 30.4. Theo dõi tỷ lệ retry thành công

Đo tỷ lệ attempts và operations thành công sau retry. Nếu phần lớn transactions phải retry 3–4 lần, điều đó có thể báo hiệu lock ordering sai, isolation design chưa hợp lý hoặc contention quá cao, dù API cuối cùng trả success.

### 30.5. Cảnh báo unknown outcome

Những operations ở trạng thái “chưa xác minh kết quả” quá lâu là rủi ro cao. Cần một reconciliation worker/alert có giới hạn và đường hỗ trợ, không chỉ để client tự resend vô hạn.

## 31. PL/pgSQL: bắt SQLSTATE và lưu lỗi gốc

Khi debug logic thủ tục, PostgreSQL cung cấp `SQLSTATE` và `GET STACKED DIAGNOSTICS` bên trong khối `EXCEPTION`.

### 31.1. Ví dụ bắt lỗi unique trong lab

```sql
DO $$
DECLARE
    v_state text;
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO retry_lab.sample_items (
            item_id, sku, quantity
        )
        VALUES (99, 'SKU-A', 5);
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE
            'Caught SQLSTATE %, constraint %',
            v_state, v_constraint;
    END;
END;
$$;
```

Lệnh INSERT cố trùng `sku=SKU-A`, nên exception handler bắt `23505`; thông tin cấu trúc có thể được quan sát mà không parse text thông báo.

### 31.2. Exception blocks có chi phí

Khối `BEGIN ... EXCEPTION` của PL/pgSQL dùng cơ chế subtransaction để cô lập lỗi. Đây là công cụ hữu ích khi lỗi cá biệt đã được dự liệu, nhưng một vòng lặp hàng triệu rows mỗi row có exception block có thể tốn chi phí lớn. Nếu xử lý duplicates, `ON CONFLICT` hoặc staging validation theo tập thường thích hợp hơn.

### 31.3. Không nuốt lỗi rồi tuyên bố thành công

Ví dụ nguy hiểm:

```sql
-- Anti-pattern:
-- EXCEPTION WHEN OTHERS THEN
--     NULL;
```

Ứng dụng có thể tưởng transaction thành công dù một bước quan trọng đã lỗi. Nếu muốn chuyển lỗi thành business response, phải **ghi rõ state** và đảm bảo side effects trước đó có được rollback/commit theo contract.

### 31.4. RAISE SQLSTATE tùy chỉnh

PL/pgSQL có thể dùng `RAISE EXCEPTION USING ERRCODE = ...`. Nếu ứng dụng dùng SQLSTATE tùy chỉnh cho lỗi nghiệp vụ, cần tài liệu hóa danh mục mã, tránh trùng mã built-in và không đánh đồng tất cả custom errors với transient database failures. Thường có lợi hơn nếu API dùng domain-specific error code riêng ở response còn SQLSTATE dùng để phân loại lỗi database.

## 32. Những case study thực tế

### 32.1. Case A: API tạo đơn trùng sau khi client timeout

**Bối cảnh:** một người dùng nhấn “Đặt hàng”, server đã COMMIT, nhưng response bị mất. Trình duyệt tự gửi lại POST.

**Sai:** request thứ hai sinh order ID mới và INSERT thêm một đơn, dù payload giống hệt.

**Đúng hơn:** client giữ `Idempotency-Key` do lần đầu tạo. Backend lưu bảng `order_requests(tenant_id,request_key,payload_hash,order_id,status)` với unique constraint, commit cùng đơn hàng, và khi key trùng thì xác minh payload trước khi trả order ID cũ.

**Điểm cần test:** hai requests trùng key đến **cùng lúc**, một request mất connection khi COMMIT, key trùng nhưng payload khác.

### 32.2. Case B: hai thao tác chuyển tiền đối nghịch gây deadlock

**Bối cảnh:** transaction A chuyển tiền account 1→2, transaction B chuyển 2→1; mỗi transaction cập nhật hai tài khoản với lock ordering ngược.

**Triệu chứng:** một transaction nhận `40P01`.

**Hướng xử lý:** khóa các accounts theo **thứ tự ID ổn định** trước khi cập nhật; giữ transaction ngắn; retry toàn transaction với request ID cố định và backoff. Không chạy lại mỗi câu credit riêng nếu debit ở attempt cũ đã bị rollback.

### 32.3. Case C: serialization failure khi đọc–ghi

**Bối cảnh:** hai transactions SERIALIZABLE đọc cùng tập rồi cập nhật các rows liên quan.

**Triệu chứng:** `40001` tại UPDATE hoặc COMMIT.

**Hướng xử lý:** bắt đầu transaction mới, đọc lại predicates/aggregates và quyết định mới. Không retry chỉ COMMIT. Một số điều kiện cạnh tranh có thể được giảm bằng statement atomic update, indexes hoặc thay đổi isolation theo business contract; nhưng nếu dùng SERIALIZABLE thì vẫn phải thiết kế retry.

### 32.4. Case D: báo cáo bị cancel

**Bối cảnh:** người dùng nhấn Cancel trong lúc chạy truy vấn analytics; driver nhận `57014`.

**Sai:** retry middleware coi mọi `57xxx` là transient, tiếp tục chạy báo cáo sau Cancel.

**Đúng:** giữ thông tin cancellation source và request deadline. Nếu do user cancel, kết thúc công việc. Nếu là statement timeout, điều tra query plan/tài nguyên rồi chỉ thử lại khi có lý do và budget.

### 32.5. Case E: lỗi `23505` trong đăng ký tài khoản

**Bối cảnh:** email đã tồn tại theo unique constraint.

**Sai:** retry INSERT 5 lần vì “unique có thể do race”.

**Đúng:** xác định email là business key global hay per tenant; trả conflict an toàn hoặc xử lý sign-in/link account theo contract. Nếu duplicate đến từ **cùng idempotent signup request**, lookup status theo key thay vì tạo account khác.

### 32.6. Case F: ứng dụng deploy trước migration

**Bối cảnh:** code mới truy vấn cột `new_status` nhưng DB chưa có cột.

**Triệu chứng:** `42703`.

**Sai:** retry mỗi 50ms trên 10.000 requests.

**Đúng:** sửa rollout/migration order, có compatibility window, fail fast/alert và tránh ép DB thêm tải vô ích.

### 32.7. Case G: quá nhiều connection

**Bối cảnh:** mỗi instance chạy pool 100 connections, scale từ 5 lên 50 instances; PostgreSQL quá tải.

**Triệu chứng:** `53300`.

**Đúng:** tính tổng pool budget, giảm/giới hạn connections, dùng pooler nếu phù hợp, giới hạn concurrency, backoff và alert. Không tăng pool size ở tất cả instances như phản xạ.

### 32.8. Case H: outbox worker gửi event hai lần

**Bối cảnh:** broker đã nhận event K, worker crash trước khi cập nhật `published_at`.

**Triệu chứng:** worker khởi động lại gửi lại event K.

**Đúng:** consumer deduplicate bằng event ID hoặc operation key lưu bền vững cùng side effect. Outbox giảm mất event trong transaction nhưng không tự đảm bảo single delivery.

### 32.9. Case I: “thất bại” do mất response của COMMIT

**Bối cảnh:** transfer đã COMMIT, JDBC socket timeout khi chờ phản hồi.

**Sai:** phát sinh UUID mới rồi debit lần nữa.

**Đúng:** giữ UUID cũ, tra `transfer_requests` từ primary/authoritative source, so payload, trả kết quả terminal cũ. Nếu chưa xác định, replay bằng **cùng key** qua UNIQUE protocol sau backoff, không tuyên bố chắc failed.

### 32.10. Case J: số dư không được âm dưới READ COMMITTED

**Bối cảnh:** hai requests khác request IDs cùng trừ tiền một tài khoản.

**Sai:** cả hai SELECT balance trước rồi gửi UPDATE kiểu `SET balance = balance - amount` không có điều kiện kiểm tra trong câu cập nhật, dễ gây overdraw hoặc business invariant bị phá nếu constraints không đủ.

**Đúng:** dùng UPDATE có điều kiện:

```sql
UPDATE retry_lab.accounts
SET balance = balance - 700
WHERE account_id = 1
  AND balance >= 700
RETURNING balance;
```

Row-level locking và kiểm tra WHERE trong UPDATE giúp những transactions cạnh tranh không cùng trừ vượt số dư theo pattern này, cùng với `CHECK(balance>=0)` là rào chắn dữ liệu bổ sung. Nếu UPDATE 0 rows, đó là **business rejection**, không tự động retry lỗi SQL.

## 33. Những lỗi thiết kế retry thường gặp

### 33.1. Retry mọi SQLException

Điều này khiến lỗi input (`22P02`), quyền (`42501`), schema (`42P01`) và unique conflict (`23505`) lặp vô ích.

### 33.2. Retry ngay trong transaction đã failed

Sau `40001`, `40P01` hoặc lỗi SQL khác, transaction cần rollback. Lặp câu SQL trên connection còn `25P02` không giải quyết gì.

### 33.3. Retry chỉ statement cuối của transaction

Quyết định dựa trên SELECT trước đó có thể đã cũ. Với serialization/deadlock, phải chạy lại logic cả transaction.

### 33.4. Sinh request ID mới mỗi attempt

Biến một request thành nhiều operations. Nếu outcome không rõ, key mới có thể tạo debit/order lần hai.

### 33.5. Cho rằng connection failure nghĩa rollback

COMMIT có thể đã hoàn tất nhưng response thất lạc. Phải reconcile.

### 33.6. Cho rằng rollback() thành công chứng minh commit chưa thành công

Một rollback trên connection khác hoặc connection đã hỏng không thể đảo một COMMIT đã durable.

### 33.7. Dùng SELECT COUNT(*) trước INSERT thay unique constraint

Hai concurrent requests có thể cùng thấy COUNT=0. `UNIQUE`/`PRIMARY KEY` ở DB là hàng rào cần thiết.

### 33.8. ON CONFLICT DO NOTHING rồi trả success bừa

Không có row mới không chứng minh request cũ có cùng payload hoặc status successful. Phải đọc và xác minh.

### 33.9. Không ghi kết quả terminal trong cùng transaction

Nếu debit commit trước, marker status commit sau rồi server crash giữa hai bước, trạng thái khó reconcile. Transaction atomic giúp đồng bộ business effect và marker.

### 33.10. Commit processing marker riêng nhưng không có recovery

Khi worker chết, key có thể kẹt vô hạn. Nếu thiết kế workflow nhiều phase, cần lease/retry/status transitions rõ.

### 33.11. Không có giới hạn attempts/deadline

Retry vô hạn gây tăng tải, deadline vượt SLA và có thể kéo dài outage.

### 33.12. Mọi client cùng backoff cố định

Synchronized retries có thể tạo thundering herd; thêm jitter và admission control.

### 33.13. Retry `57014` sau user cancel

Vi phạm ý định user và tốn tài nguyên. Phải phân biệt cancel khỏi timeout.

### 33.14. Coi mọi `55P03` đều nên chờ

Một API với deadline 200ms có thể phải trả busy, không nên block thêm vài giây.

### 33.15. Quên rollback khi gặp lỗi, trả connection về pool

Session còn transaction failed gây `25P02` ở request tiếp theo. Framework/pool phải cleanup đúng transaction.

### 33.16. Gửi email hoặc gọi payment gateway trong transaction retryable

DB rollback không hoàn tác side effects ngoài DB; retry làm gửi/thu tiền lặp. Dùng outbox hoặc provider idempotency key.

### 33.17. Tin rằng outbox đảm bảo exactly-once broker delivery

Worker crash ở ranh giới publish/ack có thể gửi event lần hai. Consumer/provider phải idempotent.

### 33.18. Lookup status trên replica lag

Không thấy result row trên replica chưa chắc transaction trên primary thất bại. Reconcile cần nguồn đủ nhất quán.

### 33.19. Parse message thay SQLSTATE

Thông báo lỗi thay đổi theo locale/driver/major; classifier dễ vỡ. Dùng SQLSTATE và structured fields.

### 33.20. Không gắn request ID trong log

Không thể gộp attempts, xác định duplicate hay điều tra commit unknown. Ghi correlation ID an toàn, không log payment details nhạy cảm.

### 33.21. Retry lỗi tài nguyên bằng cách tăng concurrency

`53300`/`53200` có thể xấu hơn nếu clients retry cùng lúc. Giảm tải và sửa hạ tầng trước.

### 33.22. Dùng account balance hiện tại làm bằng chứng transaction cũ

Một số dư có thể bị các transfers khác thay đổi, không chứng minh operation K đã chạy. Tra **request marker/ledger theo ID**.

### 33.23. Thiếu kiểm tra cùng key khác payload

Một attacker/client bug tái sử dụng key K với amount khác có thể nhận kết quả của thao tác không liên quan. So sánh payload sau khi xác thực tenant/owner.

### 33.24. Lẫn lộn rollback chắc chắn với unknown outcome

`40001` server trả rõ là transaction bị rollback theo semantics lỗi; lỗi socket khi COMMIT không nói điều đó. Tách nhánh riêng.

### 33.25. Không test race conditions

Một integration test chỉ gửi requests tuần tự có thể không phát hiện việc hai clients cùng xử lý một key. Cần mô phỏng concurrency thật và fault injection ở commit/response.

## 34. Bài tập thực hành

Các bài sử dụng schema `retry_lab` trong phần 7, trừ những bài tình huống Java/API. Không chạy demo deadlock hoặc ngắt COMMIT trên production. Nếu dùng những SQL có thay đổi dữ liệu, hãy xét transaction/rollback hoặc dùng database lab riêng để giữ dữ liệu đầu vào cho bài sau.

### Bài 1. Cấu trúc SQLSTATE

Mã `23505` có class nào và condition nào? Vì sao không lưu SQLSTATE trong một cột kiểu integer?

### Bài 2. Hai class khác nhau

So sánh nhóm `23` và `40` về ý nghĩa, cho ví dụ mã thường gặp và cách phản ứng.

### Bài 3. Phân loại UNIQUE

Lệnh INSERT một SKU đã tồn tại gây `23505`. Có nên retry INSERT 5 lần với cùng dữ liệu không? Khi nào nó có thể là duplicate idempotency request?

### Bài 4. Foreign key

INSERT transfer với `from_account=999` không có parent account. Mã dự kiến là gì? Đây có phải auto-retryable không?

### Bài 5. Numeric conversion

`SELECT 'abc'::integer` có thể trả SQLSTATE nào? Hướng sửa?

### Bài 6. CHECK constraint

`UPDATE sample_items SET quantity=-1` vi phạm CHECK. Tên và mã lỗi nào? Vì sao backoff không giúp?

### Bài 7. Transaction failed

Sau một INSERT lỗi `23505` trong `BEGIN`, câu SELECT tiếp theo trả `25P02`. Phải làm gì trước khi tiếp tục?

### Bài 8. SAVEPOINT

Viết một transaction có savepoint để thử INSERT SKU trùng, rollback về savepoint khi lỗi rồi tiếp tục một SELECT khác.

### Bài 9. 40001

Khi nhận `40001`, nên retry câu SQL cuối hay toàn transaction? Vì sao?

### Bài 10. Deadlock

Hai sessions UPDATE ID 1→2 và ID 2→1 theo thứ tự ngược. SQLSTATE nào có thể xuất hiện và hướng giảm deadlock ngoài retry?

### Bài 11. NOWAIT

Session A giữ `FOR UPDATE` trên row 1; Session B dùng `FOR UPDATE NOWAIT`. Mã lỗi nào có thể có? Có nên retry ngay vô hạn?

### Bài 12. statement_timeout

Session chạy `SET LOCAL statement_timeout='1s'` và `SELECT pg_sleep(2)`. SQLSTATE nào có thể trả, và transaction cần xử lý ra sao?

### Bài 13. User cancel

`57014` xuất hiện vì người dùng nhấn Cancel. Một retry middleware tự động chạy lại là đúng hay sai?

### Bài 14. Connection failure trước BEGIN

Ứng dụng chưa gửi DML, không lấy được connection (class `08`). Có thể retry bước nào? Điều gì vẫn cần giới hạn?

### Bài 15. Mất response COMMIT

App đã gửi COMMIT nhưng socket đóng. Có thể kết luận transaction rollback không? Hướng xử lý đúng?

### Bài 16. JDBC

Viết Java expression kiểm tra SQLSTATE `40001` hoặc `40P01` từ `SQLException` mà không bị NullPointerException.

### Bài 17. Parsing message

Vì sao `e.getMessage().contains("deadlock detected")` không phải classifier đáng tin?

### Bài 18. Retry budget

Một request HTTP có deadline 2 giây. Vì sao ba attempts, mỗi attempt timeout 1 giây và backoff 100/200ms có thể vượt SLA?

### Bài 19. Jitter

Jitter giải quyết vấn đề gì khi 500 clients đều gặp deadlock rồi backoff?

### Bài 20. Spring @Transactional

Vì sao catch `40001` rồi retry câu UPDATE ngay bên trong cùng một method `@Transactional` có thể gây `25P02`? Đặt retry ở đâu?

### Bài 21. Row count sau debit

Trong mẫu transfer, `UPDATE accounts ... WHERE balance>=amount RETURNING` trả 0 rows. Đây có phải `40001` không? Cần làm gì?

### Bài 22. Idempotency key

Một client gửi cùng lệnh chuyển tiền hai lần vì response mất. Điều kiện nào giúp đảm bảo debit chỉ một lần?

### Bài 23. Cùng key khác payload

Request K ban đầu chuyển 100 từ 1→2. Lần sau cũng K nhưng chuyển 900 từ 1→3. Hệ thống phải xử lý thế nào?

### Bài 24. ON CONFLICT DO NOTHING

`INSERT ... ON CONFLICT (request_id) DO NOTHING RETURNING request_id` trả 0 rows. Có được chạy tiếp debit/credit không? Vì sao?

### Bài 25. Hai clients tranh cùng key

Hai transaction đồng thời INSERT cùng UUID unique, một chưa COMMIT. Unique constraint giúp ngăn xử lý trùng thế nào?

### Bài 26. READ COMMITTED visibility

Vì sao `DO NOTHING RETURNING 0` không bảo đảm luôn có thể thấy row conflict trong cùng statement snapshot?

### Bài 27. Lưu marker

Vì sao marker, ledger, debit, credit và trạng thái terminal nên commit trong cùng một transaction trong thiết kế lab?

### Bài 28. Insufficient funds

Một transfer trả `insufficient_funds` và commit trạng thái từ chối. Nếu người dùng nạp thêm tiền rồi muốn thử lại thực sự, nên dùng request key cũ hay mới?

### Bài 29. Outbox

Vì sao không gửi HTTP notification trực tiếp giữa BEGIN và COMMIT của một transaction có thể retry?

### Bài 30. Gửi event hai lần

Outbox worker gửi event thành công nhưng crash trước khi ghi `published_at`. Sau restart, phải làm gì để không nhân tác dụng ở bên nhận?

### Bài 31. Replica lag

Sau commit unknown, API đọc request ID trên replica và không thấy row. Có thể suy ra transfer rollback không?

### Bài 32. SQLSTATE resource

`53300` khác `23505` ra sao? Vì sao tăng số lượng connections/clients retry không phải cách xử lý hợp lý cho `53300`?

### Bài 33. Read-only

Ứng dụng kết nối vào replica rồi cố UPDATE, nhận `25006`. Cần sửa gì?

### Bài 34. Schema migration

`42P01` và `42703` xuất hiện sau deploy phiên bản mới. Nêu nguyên nhân thường gặp và phản ứng phù hợp.

### Bài 35. PL/pgSQL diagnostics

Trong `EXCEPTION WHEN unique_violation`, lấy SQLSTATE và tên constraint bằng lệnh gì?

### Bài 36. Đếm deadlocks

Viết SQL xem số deadlocks tích lũy của database hiện tại từ catalog thống kê, và nêu giới hạn của chỉ số này.

### Bài 37. Effectively-once

“Tôi có outbox, nên broker và tất cả consumers sẽ nhận đúng một lần” — khẳng định này đúng không? Vì sao?

### Bài 38. SELECT FOR UPDATE SKIP LOCKED

`SKIP LOCKED` giúp gì cho job queue, và tại sao không được coi là cơ chế exactly-once end-to-end?

### Bài 39. Thiết kế test

Đề xuất ít nhất tám test cases cho hệ thống transfer để xác thực lỗi, retry, idempotency và commit outcome unknown.

### Bài 40. Thiết kế tổng hợp

Một API tạo đơn hàng dùng PostgreSQL, chạy qua Spring/JDBC, nhận request ID từ client, cần gửi email sau khi đơn đã lưu. Thiết kế transaction, SQLSTATE policy, retry boundary, idempotency và outbox; nêu cách phục hồi khi COMMIT response bị mất.

## 35. Gợi ý lời giải

### Đáp án 1. Cấu trúc

`23505` có class `23` (integrity constraint violation), condition `505` tương ứng `unique_violation` trong class ấy. Mã có thể chứa chữ như `40P01`/`22P02`, vì vậy phải lưu/so sánh **chuỗi 5 ký tự**, không dùng integer.

### Đáp án 2. Constraint và transaction rollback

Class `23` thường báo dữ liệu xung đột constraints: `23505` unique, `23503` foreign key, `23514` CHECK. Thường phải sửa request/schema hoặc giải quyết conflict. Class `40` báo transaction rollback: `40001` serialization failure và `40P01` deadlock thường có thể retry **toàn transaction** sau rollback.

### Đáp án 3. UNIQUE không mặc định retry

Không. Nếu SKU đã tồn tại đúng như constraint thiết kế, INSERT lại 5 lần vẫn trùng. Nếu duplicate do **cùng request_id** đã xử lý, hãy đọc record kết quả và xác minh payload, hoặc dùng `ON CONFLICT` theo nghiệp vụ. Đừng coi `23505` là transient lỗi mạng.

### Đáp án 4. FK

`23503 foreign_key_violation`. Thường cần sửa account_id hoặc bảo đảm parent hợp lệ trước, không auto-retry. Chỉ có thể thử lại theo dependency protocol đã thiết kế (ví dụ parent sẽ xuất hiện sau) với deadline/budget rõ.

### Đáp án 5. Cast sai

`22P02 invalid_text_representation`. Validate/cast input đúng kiểu hoặc sửa mapping ở Java/SQL. Retry cùng string `abc` không giúp.

### Đáp án 6. CHECK

`23514 check_violation`. Dữ liệu `quantity=-1` vẫn không thỏa `CHECK(quantity>=0)`; sleeping/backoff không làm constraint tự đổi.

### Đáp án 7. Failed transaction

Phải `ROLLBACK` toàn transaction hoặc `ROLLBACK TO SAVEPOINT` được tạo phù hợp trước lỗi. Đừng tiếp tục SELECT/UPDATE trên transaction aborted; `25P02` chỉ là hệ quả, cần log SQLSTATE gốc `23505`.

### Đáp án 8. SAVEPOINT

```sql
BEGIN;

SAVEPOINT sp_before_insert;

-- Bỏ comment để gây lỗi dự kiến 23505:
-- INSERT INTO retry_lab.sample_items
-- (item_id,sku,quantity)
-- VALUES (88,'SKU-A',10);

-- Sau lỗi duplicate, rollback subtransaction:
ROLLBACK TO SAVEPOINT sp_before_insert;

SELECT COUNT(*) FROM retry_lab.sample_items;

COMMIT;
```

Vì `INSERT` đang comment, script bình thường chạy và rollback về savepoint không thay dữ liệu; bỏ comment khi muốn quan sát lỗi. Trong code app, bắt error và chọn rollback to savepoint; với duplicate bình thường, `ON CONFLICT` thường gọn hơn.

### Đáp án 9. Retry 40001

Retry **toàn transaction** sau rollback: đọc lại dữ liệu, tính lại business rule, thực thi DML và COMMIT. Nếu chỉ retry câu UPDATE cuối, những quyết định dựa trên snapshot cũ có thể sai.

### Đáp án 10. Deadlock

`40P01 deadlock_detected`. Giảm khả năng deadlock bằng **thứ tự khóa thống nhất** (ví dụ luôn lock account có ID nhỏ trước), transaction ngắn, tránh chờ API ngoài trong transaction. Nếu vẫn xảy ra, rollback và retry toàn transaction với budget.

### Đáp án 11. NOWAIT

Thường `55P03 lock_not_available`. Không retry vòng lặp bận vô hạn. Có thể backoff/jitter rồi retry nếu SLA cho phép, hoặc trả busy/chọn work item khác.

### Đáp án 12. statement_timeout

Thường `57014 query_canceled`. Statement bị cancel, transaction block có thể ở failed state; `ROLLBACK` trước khi dùng connection tiếp. Chỉ retry nếu không phải user cancel, deadline và nguyên nhân cho phép.

### Đáp án 13. User cancel

Sai. Retry middleware phải tôn trọng ý định Cancel của người dùng. SQLSTATE `57014` không đủ để quyết định: phải biết cancel source và request deadline.

### Đáp án 14. Chưa gửi DML

Có thể retry **kết nối/connection acquisition** với giới hạn attempts, deadline và jitter. Không có side effect mới của attempt chưa gửi SQL, nhưng vẫn cần không tạo retry storm, nhất là khi database quá tải.

### Đáp án 15. COMMIT unknown

Không thể kết luận rollback. COMMIT có thể thành công nhưng response bị mất. Giữ request ID, reconnect, tra cứu result/ledger từ nguồn đủ nhất quán và nếu cần retry **cùng business key** qua giao thức UNIQUE idempotent; không sinh key mới.

### Đáp án 16. JDBC boolean

```java
String state = exception.getSQLState();
boolean retryWholeTx =
    "40001".equals(state) || "40P01".equals(state);
```

`"constant".equals(state)` an toàn khi state null. Caller vẫn phải rollback và mở **transaction mới**, không chỉ lặp statement.

### Đáp án 17. Message parsing

Message có thể khác theo locale, driver/proxy, server version, chi tiết constraint và cách bọc exception. SQLSTATE được cấu trúc cho máy xử lý. Nếu cần constraint name, dùng pgJDBC structured server error metadata khi tồn tại, không parse message.

### Đáp án 18. Deadline

Ba lần timeout 1 giây đã có thể chiếm khoảng 3 giây, chưa kể backoff và connection/commit time, vượt deadline 2 giây. Policy phải tính **thời gian còn lại tổng** trước khi thử thêm.

### Đáp án 19. Jitter

Giúp tránh các clients retry cùng nhịp, tạo thêm lock contention/connection spike sau sự cố chung. Jitter phân tán thời điểm attempts, đi cùng exponential backoff và retry budget.

### Đáp án 20. Spring transaction boundary

`@Transactional` thường mở một transaction bao quanh method. Sau `40001`, transaction đã failed/rollback-only; chạy lại UPDATE trong cùng scope có thể trả `25P02` hoặc vẫn bị rollback. Đặt retry **ngoài** transaction proxy hoặc dùng `TransactionTemplate` để mỗi attempt mở transaction mới; chú ý self-invocation và interceptor ordering.

### Đáp án 21. Debit 0 rows

Đây không phải `40001` tự thân. Với `WHERE account_id=... AND balance>=amount`, 0 rows nghĩa không có target hợp lệ theo predicate tại thời điểm update, ví dụ không đủ tiền. Trong lab có FK đảm bảo account tồn tại khi marker được thêm vào; nhưng ứng dụng production vẫn phải phân biệt missing account, không đủ tiền và lỗi quyền/RLS nếu có. Khi không đủ tiền, ghi trạng thái terminal `insufficient_funds` và COMMIT marker, **không credit**.

### Đáp án 22. Điều kiện idempotent

Giữ request key ổn định, bảng `transfer_requests` có `PRIMARY KEY(request_id)`, reserve key atomically, chỉ owner của key mới được debit/credit, ghi kết quả terminal và ledger trong cùng DB transaction. Duplicate request so payload và đọc result cũ; không tự trừ tiền thêm.

### Đáp án 23. Same key, different payload

Từ chối reuse key, ví dụ HTTP 409 Idempotency-Key Conflict sau khi xác thực caller/tenant. Không chuyển 900, không trả success của yêu cầu 100 như thể hai payload là một.

### Đáp án 24. ON CONFLICT trả 0 rows

Không được chạy debit/credit. Có key đã được claim/commit bởi một attempt khác hoặc conflict tương ứng; kết thúc write branch, tra cứu existing record trong transaction/snapshot phù hợp và so khớp payload/status. Nếu cứ chạy tiếp, UNIQUE marker không còn bảo đảm ngăn double debit.

### Đáp án 25. UNIQUE dưới cạnh tranh

UNIQUE index/PK buộc hai sessions có cùng key phải giải quyết conflict ở database. Một INSERT có thể chờ transaction cạnh tranh; khi bên kia COMMIT, request sau không chèn được; nếu bên kia ROLLBACK, request sau có thể trở thành owner. Dùng `ON CONFLICT DO NOTHING RETURNING` và chỉ cho owner thực hiện side effects.

### Đáp án 26. Snapshot của cùng statement

Ở READ COMMITTED, `INSERT ON CONFLICT DO NOTHING` có thể nhận ra conflict với row được một transaction khác commit nhưng row ấy không nằm trong snapshot bắt đầu statement hiện tại. `DO NOTHING` không chèn nhưng cùng statement không nhất thiết có thể SELECT row ấy. Một statement SELECT tiếp theo với snapshot mới hoặc transaction/query mới có thể thấy record.

### Đáp án 27. Atomic commit

Nếu marker và debit/credit/ledger/outbox cùng transaction, rollback do lỗi không để trạng thái “đã trừ tiền nhưng chưa ghi operation result”. Commit thành công xuất bản tất cả cùng nhau; khi response mất, request ID và ledger cho phép reconcile. Nếu ghi từng phần và commit riêng, phải thiết kế workflow phức tạp hơn để phục hồi các trạng thái dở.

### Đáp án 28. Retry sau thiếu tiền

Dùng **request key mới** cho một ý định chuyển tiền mới sau khi nguồn tiền thay đổi, vì key cũ đã có kết quả terminal `insufficient_funds` và lặp key cũ phải trả lại kết quả ấy. Không dùng một key cho hai nỗ lực nghiệp vụ khác nhau.

### Đáp án 29. Outbox thay external call trong transaction

PostgreSQL có thể rollback transaction sau `40001`/`40P01` nhưng không thể hủy HTTP/email đã gửi. Gửi ngoài trong transaction rồi retry sẽ nhân side effect. Ghi outbox event cùng DB transaction, worker gửi sau commit, dùng idempotency bên nhận.

### Đáp án 30. Event duplicate

Worker crash sau remote success nhưng trước ghi `published_at` làm event có thể gửi lại. Consumer/provider cần deduplication bền vững theo event ID hoặc request ID/event_type; hành động xử lý và marker consumer phải nằm trong transaction tương ứng nếu đó là side effect DB.

### Đáp án 31. Replica lag

Không. Replica có thể chưa replay COMMIT trên primary. Reconcile bằng nguồn authoritative có consistency phù hợp (thường primary) hoặc cơ chế đọc bảo đảm nhìn thấy commit cần thiết; không phát lại bằng key mới vì replica không thấy record.

### Đáp án 32. 53300

`53300 too_many_connections` là lỗi tài nguyên/kết nối; `23505 unique_violation` là lỗi constraint dữ liệu. Tăng connections và retry đồng loạt khi `53300` có thể làm database tiếp tục quá tải. Giảm/giới hạn concurrency, sửa pool budget, backoff/jitter và cảnh báo.

### Đáp án 33. 25006

`25006 read_only_sql_transaction`. Định tuyến write tới primary/write endpoint, kiểm tra transaction read-only setting và cấu hình connection pool; không retry UPDATE vô hạn trên read replica.

### Đáp án 34. 42P01/42703

`42P01 undefined_table`, `42703 undefined_column` có thể do migration thiếu/chạy sai thứ tự, search_path sai, app/DB versions không tương thích. Sửa rollout/schema/SQL; fail fast hoặc degrade theo thiết kế, không tự động retry cùng SQL sai hàng nghìn lần.

### Đáp án 35. GET STACKED DIAGNOSTICS

```sql
GET STACKED DIAGNOSTICS
    v_state = RETURNED_SQLSTATE,
    v_constraint = CONSTRAINT_NAME;
```

Chạy trong `EXCEPTION` block của PL/pgSQL với các biến đã khai báo, ví dụ `v_state text` và `v_constraint text`. Không cần parse message text.

### Đáp án 36. pg_stat_database

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

`deadlocks` là số lượng **tích lũy theo database kể từ lần reset thống kê**, không phải histogram SQLSTATE theo request hoặc danh sách các deadlock đang xảy ra. Muốn điều tra nguyên nhân, cần logs/stack/query context và monitoring phù hợp.

### Đáp án 37. Outbox không tự exactly-once

Sai. Outbox giúp không mất event khi cùng transaction DB được commit, nhưng worker có thể gửi lại vì lỗi network/crash trước ack/ghi trạng thái. Message delivery thường là at-least-once; bên nhận phải idempotent/deduplicate và chịu trách nhiệm cho external side effects.

### Đáp án 38. SKIP LOCKED

`FOR UPDATE SKIP LOCKED` giúp nhiều workers claim các rows queue khác nhau mà không chờ các rows đang khóa, tăng khả năng tiến hành công việc. Nó không đảm bảo một message sẽ chỉ được xử lý một lần khi worker crash sau side effect nhưng trước COMMIT trạng thái; cần durable lease/status, retry và idempotency.

### Đáp án 39. Tám test cases

Một bộ tối thiểu:

1. `23505` do tạo business key trùng → trả conflict/đọc result đúng, không blind retry.
2. `23514` do amount âm → từ chối input, không retry.
3. Hai SERIALIZABLE transactions tạo `40001` → toàn transaction retry từ snapshot mới.
4. Deadlock `40P01` → một victim rollback, retry bounded, không commit nửa transfer.
5. `55P03` qua NOWAIT → retry có deadline/backoff hoặc busy theo SLA.
6. `57014` do user cancel → không tự replay request đã hủy.
7. Hai requests cùng `request_id` và payload, chạy đồng thời → chỉ một ledger row/debit.
8. Hai requests cùng key nhưng amount khác → conflict, không debit thêm.
9. Drop response sau COMMIT thành công → retry same key nhận kết quả cũ, không double debit.
10. Drop connection trước COMMIT → transaction rollback hoặc outcome uncertain; protocol bằng key xử lý an toàn.
11. Outbox worker crash sau publish trước mark → consumer dedup không nhân tác dụng.
12. Đọc result ở replica bị lag → không kết luận rollback và không sinh key mới.

Với các bài có race/commit loss, cần fault injection hoặc test harness điều khiển sessions; test tuần tự đơn giản không bao phủ hết.

### Đáp án 40. Thiết kế API tạo đơn

Một kiến trúc tham khảo:

```text
Client:
  POST /orders (Idempotency-Key = K, payload P)
              |
              v
Trusted backend xác thực user/tenant
              |
              v
Retry coordinator (budget + deadline + K ổn định)
              |
              v
Transaction PostgreSQL:
  INSERT operation K UNIQUE / ON CONFLICT DO NOTHING RETURNING
  nếu đã tồn tại: dừng write, so payload, trả result cũ
  nếu mới:
      validate stock/price và concurrency
      INSERT order / UPDATE stock có điều kiện
      INSERT outbox 'order_created' UNIQUE(K,type)
      UPDATE operation K terminal(result/order_id)
  COMMIT
              |
              v
Async outbox worker gửi email có idempotency
```

SQLSTATE policy:

- `40001`/`40P01`: rollback và retry **toàn transaction** dưới một K; mỗi attempt có scope transaction mới.
- `23505`: xem conflict key nào; nếu là K, so payload/status; nếu là business key khác, xử lý domain conflict.
- `23503`/`23514`/`22P02`: validate/sửa input, không retry mù.
- `55P03`/`57014`: xem lock/cancel/deadline, không retry vô hạn.
- `08xxx` hoặc mất socket khi COMMIT: **unknown outcome**, không đánh dấu chắc failed; lookup operation K ở authoritative DB rồi trả result cũ hoặc replay same K theo protocol idempotent.
- `42P01`/`42501`/`53300`: code/config/resources, sửa nguyên nhân và giảm tải.

Email được gửi ngoài transaction bằng outbox worker, có consumer/provider deduplication để tránh gửi trùng do crash. Spring retry interceptor phải nằm **ngoài transaction boundary** và tránh self-invocation/proxy bypass. Giám sát operations với K, SQLSTATE, retry count, commit stage và outbox lag.

## 36. Checklist trước khi triển khai retry PostgreSQL

### 36.1. Phân loại SQLSTATE

1. Có lấy `SQLException.getSQLState()` thay vì parse message text không?
2. Mã SQLSTATE có được lưu dưới dạng chuỗi 5 ký tự không?
3. Có xử lý trường hợp SQLSTATE `null`/không hợp lệ không?
4. Có phân biệt `40001`, `40P01`, `55P03`, `57014` và class `08` không?
5. Có tránh tự retry `23505`/`23503`/`23514` và `22P02` mà chưa có giải thích nghiệp vụ không?
6. Có phân biệt lỗi cấu hình `42P01`/`42703`/`42501` với transient conflict không?
7. Có giữ SQLSTATE gốc trước các lỗi `25P02` phát sinh tiếp theo không?
8. Có dùng structured metadata/constraint name khi cần mà không lộ giá trị nhạy cảm không?

### 36.2. Transaction boundary

9. Mỗi attempt `40001`/`40P01` có transaction/snapshot mới không?
10. Retry có chạy lại **cả SELECT/check/business decision** không?
11. Connection/transaction được rollback/close đúng khi exception không?
12. Với Spring, retry có nằm **ngoài** transaction proxy/TransactionTemplate không?
13. Có tránh self-invocation và không nuốt exception khiến rollback bị bỏ qua không?
14. Có giám sát deadline, statement timeout và lock timeout cùng nhau không?
15. Có tránh gọi API ngoài/gửi email giữa các DB attempts có thể rollback không?
16. Có kiểm tra statement retry này có giữ được business invariant dưới concurrency không?

### 36.3. Retry policy

17. Có max attempts/deadline và backoff/jitter không?
18. Có giới hạn retry đồng thời khi DB quá tải không?
19. Có dừng retry khi user cancel hoặc request đã hết deadline không?
20. Có phân loại errors không đủ resources như `53300`/`53100` thành alert/overload response không?
21. Có đo rate `40001`/`40P01` và retry exhaustion không?
22. Có tránh ngủ trong transaction đang giữ locks không?
23. Có cách tránh retry storm sau outage/failover không?

### 36.4. Idempotency

24. Business request có key ổn định **qua HTTP/client/DB attempts** không?
25. Unique constraint nằm ở **database**, không chỉ SELECT-before-INSERT không?
26. Key có scope tenant/user/business phù hợp không?
27. Cùng key khác payload có bị từ chối không?
28. Duplicate key có trả **kết quả terminal đã lưu**, không tạo side effect mới không?
29. Result marker có COMMIT cùng business DML không?
30. Transfer/stock/account có được cập nhật bằng predicate và constraints an toàn không?
31. Nếu key chưa thấy ngay sau connection failure, có dùng protocol reconcile thay vì sinh key mới không?
32. Có kiểm thử **hai requests cùng key đồng thời** không?
33. Có tránh dùng sequence gaps/current balance làm bằng chứng request thành công không?

### 36.5. Unknown outcome và side effects

34. Hệ thống có mô hình riêng cho **COMMIT outcome unknown** không?
35. Có đọc result từ authoritative source phù hợp thay vì replica lag không?
36. Khi COMMIT response mất, client có được hướng dẫn retry **cùng key** hoặc query status không?
37. Có lưu và retry những operations pending verification một cách có giới hạn không?
38. Outbox event có được ghi trong cùng transaction với business update không?
39. Outbox worker có retry/lease/timeout và deduplication bên nhận không?
40. Có phân biệt business committed với notification delivered không?
41. Có kiểm thử crash sau external publish nhưng trước mark delivered không?
42. Có xác định RPO/consistency implications trong failover không?

### 36.6. Quan sát và kiểm thử

43. Logs có operation ID, SQLSTATE, attempt, stage, duration và retry decision không?
44. Metrics có phân biệt duplicate idempotency với business unique conflict không?
45. Có fault injection cho `40001`, `40P01`, `55P03` và `57014` không?
46. Có test connection reset trước/sau COMMIT và response drop không?
47. Có integration test dùng pool/proxy và Spring transaction thực tế không?
48. Có test cùng idempotency key nhưng amount/tenant khác không?
49. Có test retry exhaustion đúng HTTP/job contract không?
50. Có runbook điều tra deadlocks, pool saturation và unresolved operations không?

## 37. Runbook khi production xuất hiện nhiều lỗi retry

### Bước 1. Xác định SQLSTATE và transaction stage

Từ structured logs, phân nhóm:

- `40001`/`40P01`: transaction conflicts.
- `55P03`: lock unavailable.
- `57014`: timeout/cancel.
- `08xxx`/network: connection/outcome ambiguous.
- `23505`/`23503`: dữ liệu/constraints.
- `53300`: quá nhiều connection.

Đừng bật auto-retry toàn diện chỉ vì tỷ lệ 5xx tăng.

### Bước 2. Xác định số lần retry và tổng duration

Kiểm tra liệu một request có phải thực thi 4–5 attempts, làm cạn request threads/connection pool không. Có thể tạm giảm concurrency hoặc retry budget để giữ database ổn định.

### Bước 3. Với deadlock/lock contention: xem blockers

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY xact_start NULLS LAST;
```

Cần quyền xem activity phù hợp. Đừng kill backend theo một metric đơn lẻ; xem transaction mục tiêu, có đang rollback/commit, và ảnh hưởng tới users khác.

### Bước 4. Với pool/connection errors: giảm tải trước

Kiểm tra pool size toàn cụm, active/idle connections, `max_connections`, connection leaks, database restarts/failover. Với `53300`, thêm vô hạn connections/retries chỉ làm lỗi nặng hơn.

### Bước 5. Với unknown outcome: ưu tiên reconciliation

Tìm các request IDs có log “commit started; response lost” nhưng chưa xác nhận terminal result. Tra bản ghi request/ledger từ nguồn authoritative rồi trả kết quả hoặc thử lại **cùng key** theo protocol. Không sửa thủ công số dư trước khi đối chiếu ledger/idempotency.

### Bước 6. Với 23505: phân biệt duplicate request

Kiểm tra constraint name và operation type: business key bị trùng thật, hay request marker trùng do client resend? Hai trường hợp có phản ứng khác. Không tăng retry attempts của `23505` mà không biết root cause.

### Bước 7. Cải thiện có kiểm soát

Sửa thứ tự lock, index, isolation/transaction scope, idempotency protocol hoặc retry policy theo nguyên nhân. Triển khai canary/load test, quan sát SQLSTATE distribution và alert thresholds; không chỉ đổi timeout để che bottleneck.

## 38. Tra cứu nhanh

| Tình huống | Không làm | Nên làm |
| --- | --- | --- |
| `40001` | Retry một UPDATE trên transaction đã lỗi. | Rollback và retry cả transaction. |
| `40P01` | Chỉ tăng timeout, không sửa lock ordering. | Retry toàn transaction; giảm deadlock gốc. |
| `55P03` | Busy loop retry vô hạn. | Backoff/deadline hoặc trả busy. |
| `57014` | Tự retry sau user Cancel. | Xem cancel source và SLA. |
| `23505` | Giả định mọi duplicate là transient. | Business conflict hoặc idempotency lookup. |
| `23503` | Retry parent missing vô hạn. | Validate FK/dependency. |
| `25P02` | Chạy tiếp nhiều SQL trong transaction đã lỗi. | Rollback hoặc rollback to savepoint. |
| `08xxx` khi COMMIT | Coi chắc rollback. | Outcome unknown → reconcile theo request ID. |
| `53300` | Tăng pool size mọi instance. | Giảm concurrency, xử lý pool budget. |
| `42P01`/`42703` | Retry đến khi may mắn. | Sửa migration/schema. |
| Hai POST trùng | Mỗi POST tạo UUID/row mới. | Giữ idempotency key và UNIQUE result. |
| Same key different payload | Bỏ qua khác biệt. | Trả key-conflict an toàn. |
| Outbox duplicate publish | Tin event chỉ gửi một lần. | Consumer/provider dedup. |
| Failed SQL transaction | Trả connection về pool chưa rollback. | Transaction cleanup đầy đủ. |
| Replica không thấy marker | Coi transfer chưa commit. | Lookup theo consistency/authority. |
| Thử retry nhiều lần | Sleep cố định cho mọi worker. | Budget, backoff, jitter. |

## 39. Tổng kết

**Một chính sách retry PostgreSQL an toàn không chỉ hỏi “lỗi này có thể xảy ra tạm thời không?” mà còn hỏi “nếu xử lý lại, nghiệp vụ có bị áp thêm lần nữa không?”**

Những quy tắc cốt lõi:

- **SQLSTATE là chuỗi năm ký tự**, có class hai ký tự đầu và mã điều kiện chi tiết. Phân loại theo mã, không parse message.
- **`40001` và `40P01`** thường yêu cầu rollback rồi retry **toàn bộ transaction** cùng business input/operation ID; không chỉ lặp statement lỗi.
- **`23505`, `23503`, `23514`, `22P02`** thường là business/input/constraint errors; không retry mù.
- **`55P03`** có thể retry có điều kiện khi lock bận và deadline còn; **`57014`** cần biết query timeout hay user cancel.
- **`25P02`** là hậu quả transaction đã failed; cần rollback/savepoint, không lặp SQL trên transaction đó.
- **Class `08`** liên quan kết nối; **mất response của COMMIT không chứng minh transaction rollback**. Đó là trạng thái **unknown outcome** cần reconciliation.
- **Idempotency key ổn định + UNIQUE constraint + atomic result record** giúp chống tác dụng lặp khi client, JDBC hoặc message broker gửi lại cùng business request.
- **Cùng key nhưng payload khác phải bị từ chối**; `ON CONFLICT DO NOTHING` không tự đảm bảo semantic equivalence.
- **Ghi marker/ledger/outbox trong cùng transaction** để thành công hoặc rollback như một đơn vị.
- **Outbox giảm mất sự kiện**, nhưng bên nhận vẫn phải idempotent vì worker có thể gửi lại sau crash.
- **Retry budget, deadline, backoff và jitter** giúp tránh retry storm và tác động tới latency.
- **Spring/JDBC phải retry ngoài transaction boundary**, mở snapshot và persistence context mới theo yêu cầu.
- **Test races và commit-response loss**, không chỉ chạy từng request một cách tuần tự.

Nguyên tắc thực hành:

> **Phân loại lỗi bằng SQLSTATE; retry đúng phạm vi transaction; giữ một định danh nghiệp vụ không đổi; và khi kết quả COMMIT chưa rõ, xác minh trước khi cho phép tạo tác dụng mới.**

## 40. Tài liệu tham khảo

Các trang chính thức sau hữu ích để tra cứu thêm; chọn tài liệu khớp PostgreSQL major đang triển khai:

- [PostgreSQL Error Codes, Appendix A](https://www.postgresql.org/docs/current/errcodes-appendix.html): danh mục SQLSTATE class, condition và mã cụ thể.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `SERIALIZABLE`, serialization failures và yêu cầu retry.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks, deadlocks và thiết kế thứ tự khóa.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO NOTHING/UPDATE`, `RETURNING` và uniqueness.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): câu UPDATE có điều kiện, WHERE/RETURNING, xử lý hàng cập nhật.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html): tạo savepoint.
- [ROLLBACK TO SAVEPOINT](https://www.postgresql.org/docs/current/sql-rollback-to.html): phục hồi subtransaction.
- [Runtime Configuration — Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): `statement_timeout`, `lock_timeout` và các timeout liên quan.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_stat_database`, `pg_locks`.
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE` và exception patterns.
- [PL/pgSQL Diagnostics](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-EXCEPTION-DIAGNOSTICS): `GET STACKED DIAGNOSTICS`.
- [JDBC SQLException — Java SE API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): `getSQLState`, `getNextException` và exception metadata.
- [pgJDBC Documentation](https://jdbc.postgresql.org/documentation/): kết nối JDBC tới PostgreSQL và lỗi driver.













