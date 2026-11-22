# Trạng thái phiên, bảng tạm và prepared statement khi dùng pool trong PostgreSQL

Một API xử lý hai yêu cầu liên tiếp có thể nhìn như hai công việc độc lập:

```text
Request A: xem đơn hàng của tenant 10
Request B: xem đơn hàng của tenant 20
```

Nhưng nếu cả hai cùng dùng lại một **kết nối PostgreSQL vật lý** từ pool, những thiết lập và đối tượng có phạm vi **session** mà request A tạo ra có thể vẫn tồn tại khi request B bắt đầu. Ví dụ, A chạy `SET search_path`, tạo bảng tạm `temp_report`, gọi `PREPARE` hoặc chiếm một session-level advisory lock. Chỉ gọi `Connection.close()` trên một kết nối được pool quản lý **không mặc nhiên đóng PostgreSQL session thật**; thường nó chỉ trả kết nối về pool.

Đây là điểm giao nhau giữa **quản lý kết nối ứng dụng**, **trạng thái session**, **vòng đời transaction**, **temporary tables** và **prepared statements**. Sai sót có thể gây dữ liệu rò giữa requests, lỗi ngẫu nhiên khi dùng PgBouncer transaction pooling, giữ lock lâu hơn dự kiến hoặc tạo ra kết quả không nhất quán.

```text
                 APPLICATION
     Request A              Request B
         |                      |
         v                      v
     borrow conn           borrow conn
         |                      |
         +----------+-----------+
                    |
                    v
          APPLICATION CONNECTION POOL
          (HikariCP, container pool, ...)
                    |
           PostgreSQL connections
                    |
                optional
                    v
                PgBouncer
              /     |      \
         session transaction statement
          pool      pool       pool
              \     |      /
                    v
        POSTGRESQL BACKEND SESSIONS
           PID 5411      PID 5412
           TEMP          PREPARE
           SET           LISTEN
           LOCKS         PORTALS
```

Bài thuộc chương **Kết nối ứng dụng** của module *Database Engine Relational PostgreSQL*. Trọng tâm không chỉ là “có nên dùng pool?” mà là **đối tượng nào thuộc phiên, đối tượng nào thuộc transaction, ai có trách nhiệm dọn dẹp và mode pooling nào hỗ trợ từng tính năng**.

Sau khi học xong, bạn có thể:

- Phân biệt **logical connection handle**, **client connection**, **server connection**, **backend session** và **transaction**.
- Giải thích vì sao `SET`, `SET LOCAL`, `RESET`, `DISCARD ALL` có tác động khác nhau.
- Chọn vòng đời đúng cho temporary table với `ON COMMIT PRESERVE ROWS`, `DELETE ROWS` hoặc `DROP`.
- Hiểu SQL `PREPARE/EXECUTE/DEALLOCATE`, JDBC `PreparedStatement`, protocol-level named prepared statements và `pg_prepared_statements`.
- Nhận diện khác biệt giữa application pooling, PgBouncer **session/transaction/statement pooling**.
- Thiết kế an toàn với `search_path`, tenant context, RLS, timezone, session locks, `LISTEN` và cursor.
- Tránh lỗi khi retry sau statement thất bại, khi pool tái sử dụng kết nối và khi thay đổi schema.
- Viết một transaction JDBC với context dùng `SET LOCAL`/`set_config(..., true)`.
- Kiểm tra lỗi “prepared statement already exists”, “does not exist”, bảng tạm biến mất và transaction ở trạng thái aborted.
- Lập checklist cấu hình, test hội nhập và runbook khi triển khai với PgBouncer.

> **An toàn:** Ví dụ tạo schema `pool_state_lab` và những đối tượng tạm trong PostgreSQL test database. Không chạy `DISCARD ALL`, `RESET ROLE`, thay đổi `search_path`/RLS, hay sửa PgBouncer production khi chưa có kế hoạch triển khai. Một số ví dụ cố ý tạo lỗi, được ghi chú để chạy riêng. SQL snippets cấu hình pool là **ví dụ**; version và driver thực tế phải được xác minh trước khi rollout.

---

## 1. Phân biệt năm khái niệm rất dễ lẫn

### 1.1. Connection handle của ứng dụng

Trong JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    // Execute SQL.
}
```

Biến `connection` là một đối tượng Java mà code request sử dụng. Nếu `dataSource` là pool, `connection.close()` thường **trả handle về pool**, không trực tiếp hủy socket/backend PostgreSQL đang đứng sau nó.

### 1.2. Kết nối vật lý ở pool ứng dụng

HikariCP hoặc một JDBC pool tương đương quản lý một tập physical connections tới endpoint database. Một kết nối vật lý có thể được các request mượn **tuần tự**:

```text
10:00:00 Request A borrows connection #3
10:00:01 Request A returns connection #3
10:00:02 Request B borrows connection #3
```

Nếu #3 vẫn kết nối thẳng tới cùng PostgreSQL backend session thì session-level objects tồn tại xuyên qua hai lần mượn, trừ khi driver/pool/application reset đúng những loại state liên quan.

### 1.3. PostgreSQL backend session

Một kết nối trực tiếp tới PostgreSQL thường tương ứng một server backend process/session. Có thể quan sát:

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role;
```

`pg_backend_pid()` giúp nhận diện backend đang thực thi statement. Nhưng một **logical client connection qua PgBouncer transaction pooling** có thể chạy những transactions khác nhau trên các backend khác nhau.

### 1.4. Transaction

`BEGIN ... COMMIT` hoặc `ROLLBACK` xác định đơn vị thay đổi dữ liệu nguyên tử. Nhiều SQL statements trong cùng transaction dùng một backend do PgBouncer transaction pooling giữ trong suốt transaction đó.

Transaction không phải session:

- Một session có thể chạy nhiều transactions.
- Một session có thể giữ temporary table, SQL prepared statement hoặc session setting qua nhiều commits.
- `SET LOCAL` và transaction-scoped advisory lock chỉ có hiệu lực trong transaction.

### 1.5. Pool mode

Mode quyết định **khi nào** một PostgreSQL server connection được trả về pool trung gian:

- **Session pooling:** client giữ một server connection suốt thời gian client session còn sống.
- **Transaction pooling:** server connection chỉ được giữ từ lúc bắt đầu đến lúc kết thúc transaction.
- **Statement pooling:** server connection được trả sau từng statement; multi-statement transactions không được hỗ trợ theo mô hình mode này.

Application pool và PgBouncer có thể cùng tồn tại:

```text
Application request
      |
      v
JDBC Connection từ HikariCP
      |
      v
TCP connection tới PgBouncer
      |
      v
Một backend PostgreSQL có thể được đổi sau COMMIT
```

Vì vậy “tôi giữ nguyên đối tượng JDBC Connection” **không đồng nghĩa** “tôi đang giữ nguyên PostgreSQL backend PID” nếu bên dưới là transaction pooling.

---

## 2. Bảng phạm vi vòng đời: thứ gì sống tới đâu?

| Đối tượng/trạng thái | Scope bình thường | Sống qua COMMIT? | Ghi chú |
|---|---|---|---|
| `SET parameter = ...` | Session | Có nếu transaction chứa SET commit | Có thể rò sang lần mượn sau |
| `SET LOCAL parameter = ...` | Transaction | Không | Phải đặt trong transaction thật |
| `SET ROLE` | Session | Có theo semantics SET | Cần reset/quy trình quyền |
| `SET LOCAL ROLE` | Transaction | Không | Có thể dùng khi role switching được cho phép |
| `CREATE TEMP TABLE ... ON COMMIT PRESERVE ROWS` | Session | Có | PostgreSQL mặc định PRESERVE ROWS |
| `CREATE TEMP TABLE ... ON COMMIT DELETE ROWS` | Session, dữ liệu theo transaction | Table có, rows bị xóa khi COMMIT | Không tự giải quyết transaction pooling |
| `CREATE TEMP TABLE ... ON COMMIT DROP` | Transaction cho bảng vừa tạo | Không | Thích hợp cho batch cùng transaction |
| SQL `PREPARE name AS ...` | Session | Có | Chỉ tồn tại ở backend được PREPARE |
| Protocol-level named prepared statement | Backend, trừ khi pooler hỗ trợ remapping | Có trên cùng backend | PgBouncer version/config quan trọng |
| `pg_advisory_lock(...)` | Session | Có | Phải unlock hoặc kết thúc session |
| `pg_advisory_xact_lock(...)` | Transaction | Không | Tự giải phóng cuối transaction |
| `LISTEN channel` | Session | Có | Không phù hợp khi backend đổi tùy transaction |
| `NOTIFY channel` | Statement/transaction | Phát khi transaction commit | Không đòi LISTEN của client đó |
| Cursor thường không `WITH HOLD` | Transaction | Không | Không dùng sau COMMIT |
| Cursor `WITH HOLD` | Session | Có | Không phù hợp transaction pooling |
| Row locks thông thường | Transaction | Không | Release khi commit/rollback |
| Session-level GUC tùy biến `app.tenant_id` | Session nếu SET | Có | Không dùng làm authorization bằng bản thân nó |

**Quy tắc nhớ:** Pool **không tự chuyển đổi** những tài nguyên session thành transaction resources. Tính năng nào dựa vào phiên phải được xét theo kiểu pooling đang dùng.

---

## 3. Chuẩn bị môi trường thử nghiệm

### 3.1. Kiểm tra môi trường

```sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid(),
    current_setting('server_version') AS version;
```

Nếu dùng PgBouncer, bạn cần phân biệt **SQL qua endpoint PgBouncer tới PostgreSQL** với câu lệnh quản trị gửi tới **PgBouncer admin console**. Không dùng các câu `SHOW POOLS` của PgBouncer như một truy vấn SQL thông thường trên database nghiệp vụ.

### 3.2. Tạo schema test

```sql
CREATE SCHEMA pool_state_lab;

CREATE TABLE pool_state_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'paid'))
);

INSERT INTO pool_state_lab.orders
    (tenant_id, amount, status)
VALUES
    (10, 100.00, 'paid'),
    (10,  50.00, 'draft'),
    (20, 200.00, 'paid');
```

Chỉ chạy trong database test chưa có schema `pool_state_lab`. Nếu đã tồn tại, hãy dùng một database test mới; không xóa schema của người khác bằng `DROP ... CASCADE`.

### 3.3. Xác nhận dữ liệu

```sql
SELECT order_id, tenant_id, amount, status
FROM pool_state_lab.orders
ORDER BY order_id;
```

Đây là tập dữ liệu dùng minh họa tenant context. Bản thân bảng chưa có RLS; việc SELECT theo `tenant_id` trong lab chỉ là filter SQL, không phải cơ chế bảo mật đa tenant production.

### 3.4. Tách các thí nghiệm

Các ví dụ `SET`, `PREPARE` và `CREATE TEMP TABLE` cần được chạy **trên cùng một backend session** khi kiểm tra session scope. Nếu công cụ của bạn tự đổi backend qua transaction pooling thì hiện tượng không ổn định chính là một nội dung của bài.

---

## 4. Nhận diện backend session với pg_backend_pid()

### 4.1. Mở hai terminal psql

Tại **Terminal A**:

```sql
SELECT pg_backend_pid() AS pid_a;
```

Tại **Terminal B**:

```sql
SELECT pg_backend_pid() AS pid_b;
```

Hai kết nối trực tiếp đang hoạt động đồng thời tới PostgreSQL thường có PID khác nhau.

### 4.2. Kết nối qua pool ứng dụng

Trong một pool JDBC trực tiếp, cùng physical connection có thể có cùng PID qua các lần checkout. Nếu dùng PgBouncer transaction pooling, **cùng client connection** có thể nhận backend khác ở transaction kế tiếp.

### 4.3. PID không phải contract của API

Không lưu `pg_backend_pid()` như một khóa định danh người dùng hoặc transaction:

- Backend PID có thể đổi sau reconnect.
- Pooler có thể chuyển backend.
- PID không phải dữ liệu nghiệp vụ.
- PID có thể được tái sử dụng trong vòng đời server.

Dùng PID để chẩn đoán, không làm cơ sở nhất quán dữ liệu.

### 4.4. Kết quả không đổi cũng không chứng minh session pinning

Trong transaction pooling, hai lần gọi `pg_backend_pid()` tình cờ vẫn có thể trả cùng PID nếu pooler chọn lại đúng backend. Để chứng minh compatibility, hãy kiểm tra **pool mode và semantics**, không dựa vào một phép thử PID trùng ngẫu nhiên.

---

## 5. Session state là gì?

Một PostgreSQL session giữ nhiều trạng thái ngoài các rows đã commit:

```text
PostgreSQL backend session
├── Current GUC settings (search_path, TimeZone, statement_timeout...)
├── Effective/session role
├── Temporary tables and their data
├── SQL prepared statements / protocol-level statements
├── Open cursors and portals
├── Session-level advisory locks
├── LISTEN subscriptions
├── Cached plans / sequence caches
└── Transaction state (đang idle, in transaction, aborted...)
```

Khi một request trả kết nối logic về pool, **những mục có scope session có thể còn ở physical backend**. Không có một lệnh `ROLLBACK` đơn giản nào có thể xóa mọi loại state đã tồn tại qua những transactions trước.

---

## 6. SET và SET LOCAL: khác nhau ở transaction boundary

### 6.1. SET thông thường là session-scoped

```sql
SHOW TimeZone;

SET TimeZone = 'Asia/Ho_Chi_Minh';

SHOW TimeZone;
```

Sau khi `SET` thành công, giá trị session có thể tồn tại qua những commits tiếp theo cho tới khi reset, đổi lại, hoặc session kết thúc.

### 6.2. SET trong một transaction rồi COMMIT

```sql
BEGIN;

SET TimeZone = 'UTC';

COMMIT;

SHOW TimeZone;
```

Nếu transaction chứa `SET` đã commit thành công, cấu hình session-level `TimeZone='UTC'` vẫn có hiệu lực.

### 6.3. SET trong một transaction rồi ROLLBACK

```sql
BEGIN;

SET TimeZone = 'Asia/Ho_Chi_Minh';

ROLLBACK;
```

Lệnh SET được thực hiện trong transaction bị rollback nên tác động tương ứng được hoàn tác theo semantics `SET`.

### 6.4. SET LOCAL chỉ có hiệu lực trong transaction

```sql
BEGIN;

SET LOCAL TimeZone = 'UTC';

SHOW TimeZone;

COMMIT;

SHOW TimeZone;
```

Sau COMMIT, giá trị session-level trước đó hoặc default lại có hiệu lực.

### 6.5. SET LOCAL ngoài transaction

```sql
-- Không dùng như cách thiết lập cho một request autocommit:
-- SET LOCAL TimeZone = 'UTC';
```

Ngoài transaction block thực sự, `SET LOCAL` phát cảnh báo và không giữ tác dụng cho câu SELECT tiếp theo như người lập trình mong muốn.

### 6.6. SET rồi SET LOCAL trong cùng transaction

```sql
BEGIN;

SET TimeZone = 'Asia/Ho_Chi_Minh';
SET LOCAL TimeZone = 'UTC';

SHOW TimeZone; -- UTC trong transaction

COMMIT;

SHOW TimeZone; -- Asia/Ho_Chi_Minh nếu SET đã commit
```

`SET LOCAL` che tạm thời cấu hình `SET` của session trong transaction; khi transaction kết thúc, `SET` session-level tiếp tục có hiệu lực.

### 6.7. SET LOCAL và savepoint

Nếu bạn `ROLLBACK TO SAVEPOINT` được tạo **trước** `SET LOCAL`, thay đổi cục bộ tương ứng cũng có thể bị hủy.

Không giả định GUC còn tồn tại sau rollback một phần mà không kiểm tra.

### 6.8. So sánh

| Câu lệnh | Scope | Sau COMMIT | Sau ROLLBACK |
|---|---|---|---|
| `SET x = value` ngoài transaction | Session | Tiếp tục | Không có rollback tương ứng |
| `SET x = value` trong transaction | Session nếu transaction commit | Tiếp tục | Trả về giá trị trước transaction |
| `SET LOCAL x = value` trong transaction | Transaction | Phục hồi giá trị trước LOCAL | Phục hồi giá trị trước LOCAL |
| `RESET x` | Session setting tương ứng | Có nếu commit | Theo transaction rollback |
| `RESET ALL` | Nhiều GUC settings | Không xóa toàn bộ session objects | Không tương đương DISCARD ALL |

---

## 7. Một request có thể làm rò session state thế nào?

### 7.1. Tình huống

```text
Request A (tenant 10)
  SET app.tenant_id = '10';
  SELECT ...
  return connection to pool

Request B (tenant 20)
  SELECT current_setting('app.tenant_id');
  -> có thể vẫn là '10'
```

Đây là tình huống có thể xảy ra nếu physical session được tái sử dụng và pool không reset custom GUC đó.

### 7.2. GUC tùy biến

PostgreSQL cho phép tạo custom setting names theo dạng có dấu chấm, chẳng hạn:

```sql
SET app.tenant_id = '10';

SELECT current_setting('app.tenant_id') AS tenant_context;
```

Đó chỉ là một biến cấu hình của session, **không tự chứng minh user đã được phép truy cập tenant 10**.

### 7.3. Bài thử session-only

Chạy trên cùng một PostgreSQL connection trực tiếp:

```sql
SET app.tenant_id = '10';

SELECT
    pg_backend_pid(),
    current_setting('app.tenant_id', true) AS tenant_context;

COMMIT; -- nếu không có transaction, câu lệnh này chỉ cảnh báo.

SELECT current_setting('app.tenant_id', true);
```

Giá trị session đã SET có thể vẫn còn. Đừng xem `COMMIT` như lệnh tự reset mọi GUC.

### 7.4. Cách đúng cho request-scoped state

```sql
BEGIN;

SET LOCAL app.tenant_id = '10';

SELECT
    order_id, amount, status
FROM pool_state_lab.orders
WHERE tenant_id = current_setting('app.tenant_id')::integer;

COMMIT;
```

Khi transaction kết thúc, `app.tenant_id` đã đặt bởi `SET LOCAL` không tiếp tục được giữ như một session-level assignment.

### 7.5. Khi SET LOCAL đã kết thúc

Với custom GUC chưa từng tồn tại ở session trước đó, cách `current_setting(..., true)` biểu diễn trạng thái chưa được gán/đã reset có thể gồm NULL hoặc trường hợp giá trị trống tùy vòng đời placeholder. Không viết một RLS policy chỉ dựa trên giả định rằng lúc nào “unset” cũng là một số nguyên hợp lệ.

Một policy cần xử lý **thiếu, rỗng, sai kiểu và trạng thái không đáng tin** một cách an toàn.

---

## 8. Thiết kế tenant context an toàn: SET LOCAL không phải authorization

### 8.1. Khi nào GUC có ích?

Một transaction có thể dùng custom GUC để truyền context vào các functions hoặc policy SQL:

```sql
BEGIN;

SET LOCAL app.tenant_id = '10';

SELECT current_setting('app.tenant_id', true) AS tenant_context;

ROLLBACK;
```

Ưu điểm là các statements trong transaction chia sẻ cùng một context mà không phải truyền `tenant_id` vào từng function nội bộ.

### 8.2. GUC do caller tự SET không là danh tính đáng tin

Nếu một role có quyền SQL thông thường có thể tự chạy:

```sql
SET LOCAL app.tenant_id = '20';
```

thì việc RLS đọc `current_setting('app.tenant_id')` **không đủ** để chứng minh role đó thực sự thuộc tenant 20.

Hợp đồng bảo mật phải xác định ai có thể kết nối, ai được phép đặt context và cơ chế nào ràng buộc context với danh tính đã xác thực.

### 8.3. Cách truyền context cho RLS là quyết định bảo mật

Những mô hình thực tế:

- Database role riêng cho nhóm quyền/tenant phù hợp, RLS dựa vào database identity.
- Tầng API xác thực request, chuyển tenant context trong transaction, đồng thời ngăn runtime role tự đổi context không được phép bằng thiết kế quyền/interface.
- Privileged procedure có validation caller/tenant dựa trên nguồn tin cậy rồi thực hiện thao tác kiểm soát.

Không đủ để viết một `CREATE POLICY` tùy ý rồi cho mọi caller quyền `SET app.tenant_id`.

### 8.4. Fail closed khi thiếu context

Nếu policy dựa trên context, điều kiện thiếu hoặc không hợp lệ phải **từ chối**, không mở quyền. Ví dụ một helper function kiểm soát parse có thể ném lỗi khi context bị thiếu, thay vì dùng `COALESCE(..., '0')` không được kiểm chứng.

### 8.5. SECURITY DEFINER có thêm ranh giới

Routine `SECURITY DEFINER` chạy theo quyền owner, có thể ảnh hưởng RLS/tenant scope. Đừng nghĩ `SET LOCAL tenant` ở caller tự bảo đảm mọi definer routine chỉ thấy một tenant.

Kiểm tra owner, RLS behavior, qualified names, `search_path` và cách xác thực context trong routine đó.

---

## 9. application_name, TimeZone, search_path và timeouts

### 9.1. Những GUC thường bị ứng dụng thay đổi

```sql
SHOW application_name;
SHOW TimeZone;
SHOW search_path;
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
```

Độ nhạy:

| GUC | Tại sao quan trọng |
|---|---|
| `search_path` | Tên bảng/function unqualified có thể trỏ sang schema khác |
| `TimeZone` | Định dạng và ép kiểu thời gian có thể khác |
| `DateStyle` | Parsing/format của date text có thể khác |
| `statement_timeout` | Query có thể bị hủy bất ngờ hoặc chạy quá lâu |
| `lock_timeout` | Khả năng đợi lock thay đổi |
| `application_name` | Monitoring và attribution bị sai nếu state rò |
| `app.tenant_id` | Sai tenant context có thể thành lỗi bảo mật |
| `row_security` | Ảnh hưởng xử lý RLS theo điều kiện quyền và config |

### 9.2. Nên dùng gì ở request scope?

Khi cần thay một setting trong phạm vi đúng một unit of work nhiều statements:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL TimeZone = 'UTC';

SELECT ...
FROM pool_state_lab.orders;

COMMIT;
```

Đây là ví dụ cú pháp; không chạy `SELECT ...` placeholder nguyên văn.

### 9.3. Kết nối có thể dùng startup parameters

Một số tham số như `application_name` hoặc `TimeZone` có thể được truyền khi mở PostgreSQL connection và theo dõi bởi proxy/pooler theo khả năng của phiên bản/cấu hình.

**Không suy rằng mọi session `SET` được PgBouncer transaction pooling theo dõi và tái áp dụng cho backend mới.** Đối với GUC quan trọng, phải đọc danh sách parameter tracking của đúng PgBouncer/PostgreSQL version và test.

### 9.4. TimeZone là case đặc biệt cần hiểu

PgBouncer hỗ trợ theo dõi một số startup parameters cơ bản, bao gồm `TimeZone`, nhưng behavior của các tham số bổ sung/cấu hình `track_extra_parameters` còn phụ thuộc PostgreSQL version và những biến PostgreSQL thực sự báo qua protocol.

Đừng mở rộng từ “TimeZone được hỗ trợ” thành “mọi GUC custom đều được đồng bộ”.

---

## 10. Temporary table là session-local, không phải request-local

### 10.1. CREATE TEMP

```sql
CREATE TEMP TABLE temp_selected_orders (
    order_id BIGINT PRIMARY KEY
);
```

Temporary table được gắn với **PostgreSQL session đang tạo nó**. Các session khác không đọc trực tiếp table này như một bảng thường trong schema application.

### 10.2. Mặc định ON COMMIT PRESERVE ROWS

Khi không ghi `ON COMMIT`, PostgreSQL mặc định **PRESERVE ROWS**:

```sql
CREATE TEMP TABLE temp_selected_orders (
    order_id BIGINT PRIMARY KEY
) ON COMMIT PRESERVE ROWS;
```

Sau COMMIT, table và những rows đã commit vẫn tồn tại trong cùng session cho tới khi bị drop hoặc session kết thúc.

### 10.3. Vì sao dễ rò trong application pool?

Giả sử request A tạo/insert temporary table rồi trả kết nối mà không drop:

```text
Backend P1
    Request A: temp_selected_orders chứa [1,2]
    COMMIT
    return connection
    Request B: SELECT * FROM temp_selected_orders
               -> vẫn có thể thấy [1,2]
```

Đây là **rò state giữa hai logical requests dùng chung backend**, không phải dữ liệu bị chia sẻ giữa hai PostgreSQL sessions độc lập.

### 10.4. Bảng tạm cũng ảnh hưởng name resolution

Khi tồn tại temp table cùng tên với bảng thường, schema tạm có thể được PostgreSQL tìm trước cho **relation names** nếu `pg_temp` không được đặt tường minh ở vị trí phù hợp trong `search_path`.

Đừng đặt tên temp table trùng bảng nghiệp vụ rồi dùng SQL unqualified trong code quyền cao.

---

## 11. Ba chế độ ON COMMIT

| Tùy chọn | Sau COMMIT | Dùng khi |
|---|---|---|
| `ON COMMIT PRESERVE ROWS` | Bảng còn, dữ liệu còn | Cố ý làm việc nhiều transactions **trên cùng session** |
| `ON COMMIT DELETE ROWS` | Bảng còn, dữ liệu bị xóa | Cố ý tái sử dụng **cùng session**, mỗi transaction có bộ rows mới |
| `ON COMMIT DROP` | Bảng bị xóa | Tạo, sử dụng và bỏ bảng trong **một transaction** |

### 11.1. PRESERVE ROWS

```sql
BEGIN;
CREATE TEMP TABLE demo_preserve (id integer)
ON COMMIT PRESERVE ROWS;
INSERT INTO demo_preserve VALUES (1);
COMMIT;

SELECT * FROM demo_preserve; -- 1 trên cùng session
```

Đó là hành vi mong đợi, nhưng không phù hợp nếu application coi `close()` logical handle là đã xóa toàn bộ request data.

### 11.2. DELETE ROWS

```sql
BEGIN;
CREATE TEMP TABLE demo_delete_rows (id integer)
ON COMMIT DELETE ROWS;
INSERT INTO demo_delete_rows VALUES (1);
SELECT * FROM demo_delete_rows; -- 1 trong transaction
COMMIT;

SELECT COUNT(*) FROM demo_delete_rows; -- 0 trên cùng session
```

Table vẫn tồn tại, nên `CREATE TEMP TABLE demo_delete_rows` lần nữa trên cùng backend có thể báo lỗi relation already exists.

### 11.3. DROP

```sql
BEGIN;
CREATE TEMP TABLE demo_drop (id integer)
ON COMMIT DROP;
INSERT INTO demo_drop VALUES (1);
SELECT * FROM demo_drop; -- 1
COMMIT;

-- Sau COMMIT, demo_drop đã bị DROP ở backend này.
```

Đây thường là tùy chọn thích hợp cho một workflow chỉ cần staging table trong một transaction.

### 11.4. ON COMMIT DROP và autocommit

Nếu JDBC connection ở chế độ autocommit, câu:

```sql
CREATE TEMP TABLE auto_drop (id integer) ON COMMIT DROP;
```

có thể tự commit ngay sau statement tạo table, khiến table bị drop **trước SELECT/INSERT kế tiếp**. Vì vậy phải tạo và sử dụng trong một transaction thật.

### 11.5. ON COMMIT DELETE ROWS không phải ON COMMIT DROP

Hai trường hợp khác nhau:

```text
DELETE ROWS: session vẫn có table object.
DROP: object không còn sau commit.
```

Trong transaction pooling, giữ table object sau COMMIT vẫn làm code phụ thuộc backend session; vì vậy `DELETE ROWS` **không** trở thành an toàn chỉ vì dữ liệu đã bị xóa.

---

## 12. Temporary table trong transaction pooling

### 12.1. Hoạt động trong một transaction

PgBouncer transaction pooling giữ một server connection trong suốt transaction:

```sql
BEGIN;

CREATE TEMP TABLE tmp_ids (
    id bigint
) ON COMMIT DROP;

INSERT INTO tmp_ids VALUES (1), (2);

SELECT COUNT(*) FROM tmp_ids; -- 2

COMMIT;
```

Mọi statement bên trong transaction dùng cùng backend nên có thể tham chiếu bảng tạm; `ON COMMIT DROP` dọn đối tượng trước khi backend trả về pool.

### 12.2. Không sử dụng temp table qua hai transactions

```sql
BEGIN;

CREATE TEMP TABLE tmp_report (
    id bigint
) ON COMMIT PRESERVE ROWS;

INSERT INTO tmp_report VALUES (1);

COMMIT;

BEGIN;

-- Không được dựa vào tmp_report còn tồn tại ở backend lần này.
-- SELECT * FROM tmp_report;

ROLLBACK;
```

Trong PgBouncer transaction pooling, transaction thứ hai có thể dùng backend khác và không thấy `tmp_report`. Nếu tình cờ trỏ lại cùng backend, table còn tồn tại lại tạo kết quả không ổn định và có thể nhiễm state giữa clients.

### 12.3. Khuyến nghị rõ

- **Dùng `ON COMMIT DROP`** nếu temporary table chỉ cần trong một transaction.
- Tránh `PRESERVE ROWS` và `DELETE ROWS` trong transaction pooling.
- Không dùng temp table làm “bộ nhớ của user session” xuyên nhiều requests khi có transaction pool.
- Nếu cần state bền vững giữa requests, dùng bảng persistent có scope, row ownership, TTL/cleanup và quyền rõ ràng.

### 12.4. Statement pooling còn chặt hơn

Statement pooling không cho một multi-statement transaction thông thường như ở ví dụ trên. Vì vậy pattern `CREATE TEMP TABLE → INSERT → SELECT → COMMIT` không phải lựa chọn tương thích với statement pooling.

---

## 13. Session pooling vẫn cần dọn dẹp bảng tạm

### 13.1. PgBouncer session pooling

Một PgBouncer client connection giữ cùng PostgreSQL server connection cho đến khi client disconnect. Vì vậy temp tables, SQL PREPARE và session GUC có thể hoạt động đúng **trong lifetime của client connection**.

### 13.2. Application pool kéo dài lifetime

Nếu HikariCP giữ 20 connections tới PgBouncer session pool trong nhiều giờ, phía server có thể bị pin bởi 20 PostgreSQL backends trong nhiều giờ. Session pooling không tự làm một physical JDBC connection trở thành “một request = một session mới”.

### 13.3. Dọn trước khi trả connection

Nếu workflow dùng temp table:

```sql
DROP TABLE IF EXISTS pg_temp.temp_selected_orders;
```

Phải quản lý lỗi và transaction boundary. Nhưng dùng `ON COMMIT DROP` có thể giảm rủi ro quên drop trong workflow phù hợp.

### 13.4. Không dùng DROP TABLE unqualified thiếu cân nhắc

Nếu vừa có temp relation vừa có permanent relation cùng tên, qualification `pg_temp.table_name` giúp chỉ rõ bảng tạm cần xóa. Đừng chạy `DROP TABLE orders` không qualified trên connection có search path phức tạp rồi đoán nó xóa đúng đối tượng.

### 13.5. Đừng tự động DISCARD ALL trong mọi checkout

`DISCARD ALL` có thể dọn temp objects/prepared plans, nhưng cũng xóa session caches khác và không được chạy trong transaction block. Nếu chạy ở một JDBC connection khi driver đang cache server-prepared statement names, có thể gây mất đồng bộ cache nếu driver không được thông báo/không hỗ trợ reset đó.

Chiến lược reset phải phù hợp **pool + driver + PgBouncer** thực tế, không chỉ thêm một câu SQL cho chắc.

---

## 14. Không phải mọi bảng tạm đều cần thiết

### 14.1. Thay temporary table bằng CTE

Nếu chỉ dùng dữ liệu trung gian trong một câu SQL:

```sql
WITH selected AS (
    SELECT order_id, amount
    FROM pool_state_lab.orders
    WHERE tenant_id = 10
      AND status = 'paid'
)
SELECT COUNT(*) AS paid_count, SUM(amount) AS paid_total
FROM selected;
```

CTE là một phần truy vấn; nó không tạo temporary table session-scoped.

### 14.2. Dùng VALUES/unnest/parameter array

Nếu cần truyền một danh sách ID ngắn:

```sql
SELECT o.order_id, o.amount
FROM pool_state_lab.orders AS o
JOIN (VALUES (1::bigint), (3::bigint)) AS ids(order_id)
  ON ids.order_id = o.order_id;
```

Trong ứng dụng, có thể dùng array parameter và `unnest($1::bigint[])` với driver phù hợp thay vì tạo temp table cho mỗi request.

### 14.3. Khi temp table vẫn hữu ích

Temporary table phù hợp khi:

- Một transaction có nhiều bước JOIN trên dữ liệu trung gian lớn.
- Cần index/statistics trên dữ liệu staging tạm.
- Tránh truyền một tập dữ liệu lớn qua application nhiều lần.
- Có chiến lược dọn rõ theo transaction/session.

Không “cấm mọi temp table”; hãy chọn lifetime theo mode pooling.

---

## 15. SQL PREPARE: prepared statement là đối tượng của session

### 15.1. Tạo SQL prepared statement

```sql
PREPARE find_order(bigint) AS
SELECT order_id, tenant_id, amount, status
FROM pool_state_lab.orders
WHERE order_id = $1;
```

### 15.2. Thực thi

```sql
EXECUTE find_order(1);
EXECUTE find_order(2);
```

`PREPARE` giúp PostgreSQL giữ thông tin parse/analyze và cân nhắc reuse plan theo chiến lược generic/custom plans.

### 15.3. Kết thúc bằng DEALLOCATE

```sql
DEALLOCATE find_order;
```

Nếu không DEALLOCATE, SQL prepared statement tồn tại tới khi backend session kết thúc hoặc bị reset phù hợp.

### 15.4. PREPARE không tự gắn với transaction

```sql
BEGIN;

PREPARE count_orders(integer) AS
SELECT COUNT(*)
FROM pool_state_lab.orders
WHERE tenant_id = $1;

COMMIT;

EXECUTE count_orders(10);
```

Trên **cùng PostgreSQL session trực tiếp**, statement có thể còn sau commit. Đó chính là lý do không được dùng pattern này xuyên transaction boundaries khi PgBouncer được cấu hình transaction pooling.

### 15.5. Tên phải duy nhất trong session

Chạy:

```sql
PREPARE find_order(bigint) AS SELECT ...;
```

hai lần với cùng tên trên một backend chưa DEALLOCATE có thể gây `duplicate_prepared_statement` (SQLSTATE `42P05`).

### 15.6. EXECUTE trên backend chưa PREPARE

Nếu backend không có tên đó, `EXECUTE find_order(1)` có thể báo `invalid_sql_statement_name` (SQLSTATE `26000`).

Hai lỗi này thường gặp trong ứng dụng đang hiểu nhầm lifetime của session-prepared statements hoặc đang thay đổi pooler mode.

---

## 16. pg_prepared_statements: quan sát SQL và protocol prepared

### 16.1. Xem prepared statements của session hiện tại

```sql
SELECT
    name,
    statement,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
ORDER BY name;
```

View này phản ánh những prepared statements tồn tại **trong session hiện tại**, không phải inventory toàn cluster cho mọi backend của mọi client.

### 16.2. from_sql nghĩa là gì?

- `from_sql = true`: được tạo qua SQL `PREPARE`.
- `from_sql = false`: được tạo qua PostgreSQL extended query protocol (protocol-level).

Đây là chỉ dấu hữu ích khi điều tra hành vi driver.

### 16.3. Generic plan và custom plan

PostgreSQL có thể chọn:

- **Custom plan** phụ thuộc giá trị tham số cụ thể.
- **Generic plan** dùng chung cho nhiều executions.

`generic_plans`/`custom_plans` giúp biết lịch sử lựa chọn của prepared statement trong session đó.

### 16.4. EXPLAIN EXECUTE

```sql
PREPARE explain_order(bigint) AS
SELECT *
FROM pool_state_lab.orders
WHERE order_id = $1;

EXPLAIN EXECUTE explain_order(1);

DEALLOCATE explain_order;
```

Không mặc định chuẩn bị statement sẽ luôn làm query nhanh hơn. Nó chủ yếu tối ưu những bước parse/planning trong các trường hợp phù hợp.

### 16.5. Có thể bị replan

Thay đổi DDL, thống kê planner hoặc `search_path` có thể khiến PostgreSQL phân tích/lập plan lại prepared statement theo quy tắc tương ứng. Một prepared statement không phải snapshot vĩnh viễn của cấu trúc bảng.

Với name resolution và schema shadowing, việc đổi search path hoặc DDL có thể tạo behavior khó hiểu nếu SQL dùng tên unqualified. Cần schema-qualified statements trong những code paths nhạy cảm.

---

## 17. JDBC PreparedStatement không đồng nghĩa SQL PREPARE

### 17.1. API JDBC

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, amount FROM pool_state_lab.orders WHERE order_id = ?")) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
```

Đây là **API bind parameters**; nó không có nghĩa driver luôn gửi SQL text `PREPARE find_order(...) AS ...`.

### 17.2. Ba tầng thường bị trộn

1. **JDBC PreparedStatement object:** đối tượng Java với parameter bindings.
2. **PostgreSQL extended query protocol:** Parse/Bind/Execute, có thể dùng unnamed statement/portal.
3. **Server-side named prepared statement:** driver có thể cache tên và dùng lại trên cùng server session sau một số lần thực thi/config phù hợp.

Driver quyết định cách ánh xạ giữa các tầng. Không suy từ việc Java có `PreparedStatement` là PostgreSQL có một tên SQL PREPARE bền vững.

### 17.3. pgJDBC prepareThreshold

pgJDBC có tùy chọn `prepareThreshold` ảnh hưởng việc sử dụng server-side prepared statements theo số lần thực thi. Một cấu hình thường gặp là ngưỡng 5, nhưng hãy kiểm tra **driver version và DataSource/URL thực tế**.

Ví dụ URL:

```text
jdbc:postgresql://localhost:5432/appdb?prepareThreshold=0
```

Theo hướng dẫn tương thích PgBouncer, `prepareThreshold=0` là một cách tắt server-side named prepare ở pgJDBC khi cần tránh phụ thuộc phiên. **Không đồng nghĩa tắt parameter binding**: ứng dụng vẫn có thể dùng `PreparedStatement` để truyền dữ liệu an toàn.

### 17.4. Prepared statement caching ở driver/pool

Driver có thể cache metadata và tên prepared statements theo physical connection. Nếu phía server bị reset/discard nhưng phía driver vẫn tưởng tên còn tồn tại, lỗi invalid statement có thể xuất hiện.

Không tự ý `DEALLOCATE ALL` hoặc `DISCARD ALL` trên một connection khi còn driver cache mà không hiểu cơ chế khôi phục của driver.

### 17.5. Java PreparedStatement giúp chống SQL injection

Parameter binding an toàn đối với **giá trị dữ liệu**; nó không cho phép bind tên schema/table tùy ý:

```java
// Dữ liệu được bind:
PreparedStatement ps = connection.prepareStatement(
    "SELECT * FROM pool_state_lab.orders WHERE tenant_id = ?");
ps.setInt(1, 10);
```

Nếu tên bảng thay đổi theo tenant, phải dùng một mô hình identifier/authorization rõ, không ghép input chưa tin cậy vào SQL string.

---

## 18. PgBouncer transaction pooling và hai loại prepared

Đây là phần dễ bị làm sai nhất khi tích hợp driver với PgBouncer.

### 18.1. SQL PREPARE/EXECUTE không tương thích với assumption session

```sql
PREPARE count_by_tenant(integer) AS
SELECT COUNT(*)
FROM pool_state_lab.orders
WHERE tenant_id = $1;

-- Transaction sau có thể chạy trên backend khác:
EXECUTE count_by_tenant(10);
```

Trong transaction pooling, hai statements trên nếu không thuộc cùng transaction **không được bảo đảm dùng chung backend**. `EXECUTE` có thể không tìm thấy prepared statement, hoặc vô tình gặp tên đã tồn tại trên backend khác.

### 18.2. Protocol-level named prepared đã có hỗ trợ có điều kiện

Từ **PgBouncer 1.21.0**, PgBouncer có khả năng theo dõi **protocol-level named prepared statements** trong transaction pooling và ánh xạ chúng sang prepared statements ở backend tương ứng **khi cấu hình `max_prepared_statements` khác 0**.

Điều này áp dụng cho giao thức prepared của client/driver phù hợp, **không có nghĩa SQL text `PREPARE ...; EXECUTE ...; DEALLOCATE ...` tự được hỗ trợ xuyên mọi transactions**.

### 18.3. Vai trò của max_prepared_statements

Ví dụ đoạn cấu hình PgBouncer:

```ini
[pgbouncer]
pool_mode = transaction
max_prepared_statements = 100
```

Đây là ví dụ giá trị để hiểu cơ chế; chọn đúng mức phụ thuộc workload, cardinality query và memory overhead. Cấu hình phải được kiểm chứng với **phiên bản PgBouncer, driver và deployment thực tế**.

### 18.4. Khi feature bật, PgBouncer làm gì?

Ở mức khái niệm:

```text
Client C1:
  protocol Parse name=stmt_A, SQL=SELECT ... WHERE id=$1
            |
            v
PgBouncer tracks client name and SQL/query identity
            |
        transaction #1
            |
            v
Backend P1: internal named prepared statement

        transaction #2
            |
            v
Backend P2: PgBouncer ensures corresponding protocol
            prepared statement is available/rebound
```

Pooler quản lý ánh xạ tên của client và prepared statements thực tế ở server theo khả năng/config của nó. Việc này có thêm overhead và giới hạn; không thay mọi loại session state khác.

### 18.5. Khi feature tắt

Nếu `max_prepared_statements=0` hoặc phiên bản không có hỗ trợ tương ứng, driver dùng named server-side prepares xuyên các transactions có thể gặp lỗi. Hướng giải quyết:

- Bật tính năng PgBouncer trong version tương thích và kiểm thử.
- Hoặc tắt server-side named prepare ở driver, chẳng hạn `prepareThreshold=0` cho pgJDBC.
- Hoặc chọn session pooling / direct connection cho workload cần session semantics.

### 18.6. Không hiểu “PgBouncer hỗ trợ prepared” là mọi session feature hoạt động

Kể cả khi protocol-level prepared statements được hỗ trợ, các tính năng như SQL `PREPARE`, session `LISTEN`, `ON COMMIT PRESERVE ROWS` temp table và session-level advisory locks **vẫn không thành an toàn xuyên transaction boundaries**.

### 18.7. Client library khác nhau

Không áp một cấu hình driver JDBC cho mọi client library. PHP/PDO, libpq, Python drivers, Go drivers, ORM và server-side prepare caching có khả năng khác nhau theo version. Đọc bảng compatibility/FAQ của PgBouncer và thực hiện test với đúng driver version.

---

## 19. Bảng tương thích PgBouncer theo pool mode

Bảng dưới tóm lược các khái niệm cốt lõi; chi tiết hỗ trợ còn phụ thuộc PgBouncer version/config. Đây không phải bảng thay thế tài liệu chính thức.

| Tính năng | Session pooling | Transaction pooling | Statement pooling |
|---|---|---|---|
| Multi-statement transaction | Có | Có | Không theo thiết kế |
| Session `SET/RESET` tùy ý và phụ thuộc qua transactions | Có, khi reset đúng | Không được dựa vào | Không được dựa vào |
| `SET LOCAL` trong transaction | Có | Có | Không dùng cho workflow nhiều statements |
| Temp `ON COMMIT DROP` dùng cùng transaction | Có | Có | Không dùng workflow nhiều statements |
| Temp `PRESERVE ROWS` qua commits | Có khi cùng client/server session | Không | Không |
| Temp `DELETE ROWS` nhưng table còn | Có khi cùng session | Không | Không |
| SQL `PREPARE/EXECUTE` qua commits | Có nếu session được giữ | Không | Không |
| Protocol-level named prepared | Có | Có điều kiện với hỗ trợ và cấu hình phù hợp | Có điều kiện theo version/config |
| Session `LISTEN` | Có | Không | Không |
| `NOTIFY` | Có | Có | Có trong phạm vi statement |
| Session-level advisory lock | Có nếu chủ động unlock | Không | Không |
| Transaction-level advisory lock | Có | Có | Chỉ trong transaction được hỗ trợ |
| Cursor không `WITH HOLD` trong một transaction | Có | Có | Không cho multi-statement transaction |
| Cursor `WITH HOLD` qua commits | Có | Không | Không |
| Backend PID ổn định suốt client connection | Có | Không bảo đảm | Không bảo đảm |

### 19.1. Không nên tối ưu pool mode theo một benchmark duy nhất

Transaction pooling có thể giảm số backends cần cấp cho số lượng clients lớn, nhưng nếu ứng dụng phụ thuộc nhiều session features, migration sang transaction pooling có thể phát sinh lỗi và rủi ro correctness. **Tính tương thích chức năng** là điều kiện trước khi đánh giá throughput.

### 19.2. Session pooling và pool ứng dụng

Khi HikariCP giữ connections liên tục tới PgBouncer session pool, mỗi client connection có thể pin backend tương ứng, nên lợi ích multiplexing nhỏ hơn transaction pooling. Dù vậy session mode có thể thích hợp cho những workload cần prepared SQL, temp session tables hay LISTEN.

---

## 20. Connection reset: RESET, DEALLOCATE, DISCARD khác nhau

### 20.1. RESET

```sql
RESET TimeZone;
RESET search_path;
RESET ALL;
```

`RESET ALL` đặt lại những cấu hình run-time có thể reset theo semantics của session. Nó **không phải** một lệnh tổng vệ sinh mọi đối tượng tạm, mọi prepared statement và advisory lock.

### 20.2. DEALLOCATE

```sql
DEALLOCATE ALL;
```

Xóa prepared statements thuộc session hiện hành. Nó không xóa temp tables hay thay mọi GUC session.

### 20.3. DISCARD PLANS

```sql
DISCARD PLANS;
```

Loại bỏ cached execution plans để lập lại sau này khi cần. Nó không giống `DEALLOCATE ALL` vì prepared statements không bị loại bỏ chỉ bằng việc discard plans.

### 20.4. DISCARD TEMP

```sql
DISCARD TEMP;
```

Loại bỏ temporary tables của session hiện tại. Đừng chạy khi application vẫn cần chúng.

### 20.5. DISCARD ALL

```sql
DISCARD ALL;
```

PostgreSQL dùng `DISCARD ALL` để reset rộng session, gồm những tài nguyên như GUC changes, SQL/protocol prepared state tương ứng, temp objects, portals, LISTEN subscriptions, advisory locks và cached plans theo semantics lệnh.

**`DISCARD ALL` không được thực hiện bên trong một transaction block.**

### 20.6. So sánh reset

| Lệnh | GUC | Temp tables | Prepared statements | Session advisory locks | LISTEN |
|---|---|---|---|---|---|
| `RESET ALL` | Reset | Không | Không | Không | Không |
| `DEALLOCATE ALL` | Không | Không | Xóa | Không | Không |
| `DISCARD PLANS` | Không | Không | Giữ tên, xóa cached plans | Không | Không |
| `DISCARD TEMP` | Không | Xóa | Không | Không | Không |
| `UNLISTEN *` | Không | Không | Không | Không | Hủy subscriptions |
| `pg_advisory_unlock_all()` | Không | Không | Không | Giải phóng session advisory locks | Không |
| `DISCARD ALL` | Reset rộng | Xóa | Xóa | Giải phóng | Hủy |

### 20.7. Vấn đề driver cache sau reset

Nếu driver giữ client-side metadata rằng prepared statement `S_42` tồn tại trên backend, một `DISCARD ALL` ở ngoài có thể làm backend quên `S_42` trong khi driver chưa biết. Driver cần có logic phát hiện và tái prepare hoặc pool cần dùng cơ chế reset tương thích.

Không chạy manual `DISCARD ALL` trong application transaction cleanup mà không xét driver behavior.

---

## 21. PgBouncer server_reset_query

### 21.1. Session pooling

PgBouncer có cấu hình:

```ini
[pgbouncer]
pool_mode = session
server_reset_query = DISCARD ALL
```

Trong session pooling, reset query thường chạy khi PgBouncer trả PostgreSQL server connection về pool sau khi client session kết thúc. Nó làm sạch state để client khác không tiếp quản những objects/settings từ session trước.

### 21.2. Không phải lúc nào reset query chạy

Trong transaction pooling, mặc định PgBouncer **không dùng `server_reset_query` ở cuối mỗi transaction**. Lý do: transaction pooling đòi client không dựa vào các session features không tương thích và thường dùng cơ chế session-free protocol. Có tùy chọn `server_reset_query_always` trong những tình huống đặc biệt, nhưng không xem nó là cách hợp thức hóa mọi pattern session state.

### 21.3. Nếu JDBC pool giữ PgBouncer client session

Khi HikariCP giữ socket tới PgBouncer session pooling mở lâu, PgBouncer chưa thấy client disconnect, do đó **chưa tới thời điểm chạy server_reset_query**. Những trạng thái session vẫn tồn tại giữa các lần một logical JDBC connection được checkout/trả về.

### 21.4. Phân biệt hai lớp reset

```text
Request A -> Hikari logical close
              |
              +-- Hikari có reset một số JDBC states
              |   nhưng không bảo đảm xóa mọi custom GUC/temp/PREPARE
              |
              v
        Hikari physical connection vẫn mở
              |
              v
        PgBouncer client session vẫn mở
              |
              v
        server_reset_query session-mode chưa chạy
```

### 21.5. Cách xử lý

Chọn **một hợp đồng state rõ**:

- Tránh session-scoped state ở request code.
- Dùng `SET LOCAL` và `ON COMMIT DROP`.
- Đặt/reset những state session còn cần bằng hooks được quản lý, có test.
- Recycle physical connection khi cần xóa session state toàn phần.
- Tách connection/pool riêng cho workload phải giữ session state lâu.

---

## 22. JDBC/HikariCP: một transaction với context cục bộ

Đoạn dưới minh họa **một luồng request** dùng DataSource. Nó không yêu cầu JDBC driver tạo SQL `PREPARE` bằng tay.

### 22.1. Code Java minh họa

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderReportService {
    private final DataSource dataSource;

    public OrderReportService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal paidTotalForTenant(int tenantId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // SET LOCAL semantics: true means transaction-local.
                try (PreparedStatement context =
                        connection.prepareStatement(
                            "SELECT set_config('app.tenant_id', ?, true)")) {
                    context.setString(1, Integer.toString(tenantId));
                    context.executeQuery().close();
                }

                BigDecimal total;
                try (PreparedStatement query =
                        connection.prepareStatement(
                            "SELECT COALESCE(SUM(amount), 0) " +
                            "FROM pool_state_lab.orders " +
                            "WHERE tenant_id = " +
                            "current_setting('app.tenant_id')::integer " +
                            "AND status = 'paid'")) {
                    try (ResultSet rs = query.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("Aggregate returned no row");
                        }
                        total = rs.getBigDecimal(1);
                    }
                }

                connection.commit();
                return total;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Restore JDBC state for pool. The actual transaction-local
                // tenant context is cleared by COMMIT/ROLLBACK.
                try {
                    connection.setAutoCommit(previousAutoCommit);
                } catch (SQLException resetFailure) {
                    // In production, let the pool discard a broken connection
                    // and log this failure through the service error policy.
                    throw resetFailure;
                }
            }
        }
    }
}
```

### 22.2. Vì sao dùng set_config(..., true)?

`set_config(setting_name, value, is_local)` cho phép đặt GUC. Tham số thứ ba:

- `true`: transaction-local, gần với `SET LOCAL`.
- `false`: session-level, gần với `SET`.

`PreparedStatement` bind chuỗi tenant ID như một **data value**, tránh cố dùng placeholder không được hỗ trợ trong cú pháp `SET LOCAL some_guc = ?`.

### 22.3. Vì sao setAutoCommit(false) trước?

Để tất cả statements từ đặt context đến SELECT nằm trong một transaction. Nếu autocommit bật, transaction-local GUC của statement đầu **không tồn tại tới SELECT kế tiếp**.

### 22.4. Vì sao rollback trong catch?

Một query có thể lỗi, đưa transaction vào trạng thái aborted; nếu không rollback, lần mượn kết nối sau có thể bị ảnh hưởng nếu pool/driver không cleanup đúng.

### 22.5. Vì sao trả JDBC state?

`setAutoCommit(false)` là trạng thái trên JDBC Connection. Một pool thường cố khôi phục các JDBC state được theo dõi, nhưng application nên có contract rõ và tuyệt đối không trả kết nối khi vẫn có transaction mở.

### 22.6. Lưu ý về finally và exception

Đoạn mã minh họa flow; trong ứng dụng production, đặt policy nhất quán cho lỗi **rollback, commit outcome không xác định, reset state, connection invalidation**. Nếu `setAutoCommit(previousAutoCommit)` thất bại, lỗi đó có thể làm thay đổi exception được quan sát bởi caller; logging/monitoring nên giữ cả lỗi gốc. Không coi ví dụ này là toàn bộ transaction framework.

### 22.7. SECURITY CAVEAT

Đoạn code dùng `tenantId` do service nhận; nó không chứng minh user đã được phép truy cập tenant ấy. Phải xác thực/authorize trước khi gọi. Nếu dùng RLS dựa trên GUC, quyền SQL runtime và nguồn xác thực GUC phải được thiết kế để caller không tự chọn tenant bất kỳ.

---

## 23. HikariCP và các session settings

### 23.1. HikariCP có thể reset một số JDBC properties

Một JDBC pool có thể theo dõi/khôi phục những thuộc tính như autocommit, read-only, isolation, catalog/schema, network timeout theo khả năng của driver/pool. Nhưng **không suy rằng nó biết mọi câu SQL `SET` do application chạy**.

Ví dụ:

```sql
SET app.tenant_id = '10';
SET search_path = tenant_10, public;
```

Đây là SQL ở backend; pool không tự có một bảng đầy đủ những GUC đã thay đổi bởi custom SQL.

### 23.2. connectionInitSql không phải per-request reset

HikariCP có tùy chọn `connectionInitSql` thường dùng khi **một physical connection mới được tạo**, không phải một hook mặc định chạy lại cho mọi logical checkout.

Không gắn:

```text
connectionInitSql=SET app.tenant_id='10'
```

rồi giả định request B tenant 20 được reset đúng mỗi lần mượn.

### 23.3. Đặt baseline ở connect time

Các cấu hình mặc định như application name, timezone hay schema có thể được thiết lập khi tạo connection và có thể phù hợp với **toàn bộ connection lifetime**.

Nhưng context thay đổi theo request như tenant ID, deadline của query và nghiệp vụ chuyển role không nên gắn cứng vào physical connection lâu dài trừ khi đã có chiến lược multi-tenant isolation/cleanup chặt chẽ.

### 23.4. Không dùng close như rollback chắc chắn duy nhất

Code nên kết thúc transaction bằng `commit` hoặc `rollback` rõ trước khi trả handle. Pool có thể cố rollback một transaction chưa hoàn tất khi trả connection, nhưng không nên coi cơ chế phòng lỗi đó là flow bình thường.

### 23.5. Physical connection lỗi

Một socket/backend bị kill, mất kết nối hoặc failover có thể làm mọi prepared statements/temp tables/session locks biến mất. Driver/pool phải loại connection hỏng hoặc reconnect/reinitialize theo hợp đồng, không chạy lại nửa transaction cũ một cách mù quáng.

---

## 24. PostgreSQL transaction bị lỗi và SQLSTATE 25P02

### 24.1. Một statement lỗi trong transaction

```sql
BEGIN;

SELECT 1 / 0;

-- Chạy tiếp ở đây sẽ bị từ chối trong transaction đã aborted:
-- SELECT * FROM pool_state_lab.orders;

ROLLBACK;
```

Sau lỗi `division_by_zero`, transaction thường vào trạng thái aborted; statements tiếp theo báo lỗi kiểu “current transaction is aborted, commands ignored until end of transaction block” (SQLSTATE `25P02`) cho tới khi transaction được rollback/khôi phục theo cơ chế hợp lệ.

### 24.2. Tại sao nguy hiểm với pool?

Nếu application nuốt exception rồi trả connection mà transaction vẫn lỗi, request tiếp theo có thể nhận một physical connection ở trạng thái không thể thực hiện SQL bình thường.

### 24.3. Cleanup tối thiểu

Trong catch:

```java
try {
    connection.rollback();
} catch (SQLException rollbackFailure) {
    // Record failure; connection might be unusable.
}
```

Sau rollback mới được xem xét dùng lại connection.

### 24.4. SAVEPOINT khi muốn phục hồi một phần

```sql
BEGIN;

SAVEPOINT before_optional_work;

-- Optional statement có thể lỗi.

-- Nếu lỗi ở optional statement và caller đã nhận diện:
-- ROLLBACK TO SAVEPOINT before_optional_work;

COMMIT;
```

Savepoint có thể cho phép transaction tiếp tục sau rollback tới điểm thích hợp, nhưng code phải xử lý chính xác và không bỏ qua bất biến nghiệp vụ. Không dùng savepoint làm cách “nuốt mọi lỗi rồi commit”.

---

## 25. Advisory locks: session và transaction hoàn toàn khác

### 25.1. Session-level advisory lock

```sql
SELECT pg_advisory_lock(901);

-- Làm việc cần bảo vệ.

SELECT pg_advisory_unlock(901);
```

Lock do `pg_advisory_lock` lấy là **session-scoped**. `COMMIT` hoặc `ROLLBACK` không tự giải phóng nó. Nếu bỏ quên unlock, connection được trả về pool có thể mang lock sang một logical request khác.

### 25.2. Transaction-level advisory lock

```sql
BEGIN;

SELECT pg_advisory_xact_lock(901);

-- Thao tác trong transaction.

COMMIT; -- lock được tự giải phóng
```

Đây thường là lựa chọn tốt hơn cho một đơn vị công việc chỉ cần lock tới commit.

### 25.3. Transaction pooling

Trong PgBouncer transaction pooling:

- Session-level advisory locks **không tương thích** với việc server connection được trả sang client khác sau transaction.
- Transaction-level advisory locks có thể dùng trong cùng transaction theo semantics PostgreSQL.

### 25.4. ROLLBACK không xóa session advisory lock

```sql
BEGIN;

SELECT pg_advisory_lock(902);

ROLLBACK;

-- Lock session-level có thể vẫn còn ở backend này.
SELECT pg_advisory_unlock(902);
```

Điểm này rất dễ bị bỏ sót khi code cho rằng “lỗi thì rollback tất cả state”.

### 25.5. pg_advisory_unlock_all()

```sql
SELECT pg_advisory_unlock_all();
```

Giải phóng session advisory locks được backend hiện tại giữ. Đây là một công cụ cleanup nhưng không thay đồng bộ transaction logic hoặc xác định ownership của locks nếu application đang chủ động giữ session lock dài hạn.

---

## 26. LISTEN/NOTIFY và connection lifetime

### 26.1. LISTEN là session-scoped

```sql
LISTEN order_events;
```

Subscription gắn với PostgreSQL session. Nếu client bị chuyển sang backend khác sau commit, nó không còn cùng session đã đăng ký LISTEN.

### 26.2. Không dùng LISTEN qua transaction pool để nhận liên tục

PgBouncer transaction pooling không cung cấp một PostgreSQL backend pinned suốt client lifetime, nên subscription `LISTEN` **không thích hợp** cho một long-lived listener qua endpoint này.

### 26.3. Cấu trúc phù hợp

```text
Application request pool
       |
       +--> transaction pooling (queries ngắn)

Dedicated notification listener
       |
       +--> direct connection hoặc session pooling
              |
              +--> LISTEN order_events
```

Một listener cần cơ chế reconnect và đăng ký LISTEN lại khi connection mới xuất hiện.

### 26.4. NOTIFY khác LISTEN

```sql
NOTIFY order_events, 'order_changed';
```

Việc phát NOTIFY có thể dùng trong transaction pooling theo semantics commit của PostgreSQL; nhưng việc **nhận** thông báo qua LISTEN đòi session registration ổn định.

### 26.5. UNLISTEN

```sql
UNLISTEN *;
```

Dùng để hủy subscriptions của backend session hiện tại khi phù hợp. `DISCARD ALL` cũng bao gồm cleanup LISTEN state.

---

## 27. Cursor và WITH HOLD

### 27.1. Cursor trong transaction

```sql
BEGIN;

DECLARE cur_orders CURSOR FOR
SELECT order_id, amount
FROM pool_state_lab.orders
ORDER BY order_id;

FETCH 2 FROM cur_orders;

CLOSE cur_orders;

COMMIT;
```

Cursor thông thường gắn với transaction và không sống qua COMMIT; trong transaction pooling, nó có thể hoạt động **khi tất cả operations nằm trong cùng transaction**.

### 27.2. WITH HOLD

```sql
BEGIN;

DECLARE cur_orders_hold CURSOR WITH HOLD FOR
SELECT order_id, amount
FROM pool_state_lab.orders
ORDER BY order_id;

COMMIT;

-- Với cùng backend session trực tiếp:
FETCH ALL FROM cur_orders_hold;

CLOSE cur_orders_hold;
```

`WITH HOLD` làm cursor có thể tồn tại sau commit trên **cùng backend session**, nên không phù hợp khi client qua transaction pooling có thể đổi backend trước FETCH.

### 27.3. Streaming ResultSet của JDBC

Một số driver dùng server-side cursor/fetch size khi autocommit và transaction settings phù hợp. Nếu application dùng streaming ResultSet, phải:

- Giữ transaction mở đúng trong suốt vòng đời ResultSet.
- Đảm bảo connection không bị trả về pool trước khi đọc xong.
- Không commit giữa quá trình fetch nếu driver/cursor không hỗ trợ.
- Không giữ transaction idle quá lâu.

Đừng bật fetch size lớn/nhỏ theo kinh nghiệm mà không hiểu driver và proxy behavior.

---

## 28. SQL PREPARE và connection reset trong practice

### 28.1. Chuỗi lệnh bình thường trên session trực tiếp

```sql
PREPARE sum_paid(integer) AS
SELECT COALESCE(SUM(amount),0)
FROM pool_state_lab.orders
WHERE tenant_id = $1 AND status = 'paid';

EXECUTE sum_paid(10);

SELECT name, from_sql FROM pg_prepared_statements;

DEALLOCATE sum_paid;
```

### 28.2. Trong application pool trực tiếp

Một request có thể PREPARE, dùng rồi DEALLOCATE trước khi trả connection. Nhưng nếu driver đã dùng server-side prepare caching, đừng phối hợp tùy tiện tên driver quản lý với SQL `DEALLOCATE ALL`.

### 28.3. PREPARE cache không phải cache kết quả

Server-side prepared statement **không lưu rows của SELECT**. Khi `EXECUTE`, PostgreSQL vẫn thực hiện query trên dữ liệu theo snapshot/quy tắc transaction tương ứng.

### 28.4. DDL và cached plan

Một schema migration có thể làm old plan không còn phù hợp hoặc return type thay đổi. PostgreSQL có cơ chế invalidation/replanning, nhưng ứng dụng vẫn có thể gặp lỗi trong một số thay đổi cấu trúc như cached plan result type không còn hợp lệ.

Không coi “prepared statement cache” là kết quả snapshot đã được làm mới tự động khi app thay đổi SQL contract. Migrations cần quản lý driver/server connections, rollout phiên bản ứng dụng và error handling.

### 28.5. Version và kế hoạch generic

`plan_cache_mode` có các tùy chọn như `auto`, `force_generic_plan` và `force_custom_plan`. Đây là công cụ điều tra performance; không tự sửa mọi lỗi pooling bằng cách ép generic plan.

---

## 29. Mối quan hệ giữa pool, số backend và hiệu năng

### 29.1. Không đồng nhất số requests và số connections

Một ứng dụng có thể nhận 10.000 requests đồng thời nhưng dùng một pool 100 connections. Ngược lại, nếu có 50 service instances × 20 connections, tổng số physical connections có thể là 1.000.

### 29.2. Mỗi backend PostgreSQL có tài nguyên

Backends dùng bộ nhớ, file descriptors, transaction state và tài nguyên quản trị. Connection pooling giúp tái sử dụng và giới hạn concurrency, nhưng không tự làm database thực hiện các queries đắt nhanh hơn.

### 29.3. Pool quá lớn

Pool quá lớn có thể:

- Làm tăng số backends.
- Tăng contention trên locks/CPU/I/O.
- Gây áp lực memory/context switching.
- Che vấn đề query chậm bằng nhiều clients chờ.

### 29.4. Pool quá nhỏ

Pool quá nhỏ có thể khiến requests chờ checkout, dù database vẫn còn năng lực. Cần đo queue latency, DB execution latency và workload thay vì chọn số kết nối tùy ý.

### 29.5. Transaction pooling có lợi khi nào?

Khi có nhiều client connections nhưng mỗi transaction ngắn và không cần session state xuyên transactions, PgBouncer có thể multiplex lên ít backends hơn.

Không dùng transaction pooling cho một long-lived session workflow rồi kỳ vọng mọi SQL state vẫn nằm trên cùng backend.

---

## 30. Monitoring: theo dõi session, transaction và pooler

### 30.1. Quan sát PostgreSQL backends

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
```

Quyền role và chính sách PostgreSQL quyết định bạn nhìn được chi tiết gì của sessions khác.

### 30.2. idle in transaction

`state = 'idle in transaction'` thể hiện một backend đang giữ transaction mở nhưng tạm không chạy statement. Điều này có thể giữ locks/snapshot và gây bloat hoặc blocking.

Không trả một connection vào pool với transaction chưa xử lý. Cân nhắc `idle_in_transaction_session_timeout` cho các workload phù hợp, nhưng timeout có thể hủy session và cần ứng dụng phục hồi.

### 30.3. PgBouncer SHOW POOLS

Khi có quyền và kết nối vào **PgBouncer administrative database/console**, PgBouncer hỗ trợ những lệnh như:

```text
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
```

Đây là **commands của PgBouncer admin console**, không nhất thiết chạy được khi gửi vào PostgreSQL application database.

### 30.4. Chỉ số cần đo

| Chỉ số | Ý nghĩa |
|---|---|
| Client connections | Số clients kết nối vào pooler |
| Active server connections | Backend đang được dùng |
| Idle server connections | Backend sẵn sàng cấp lại |
| Waiting clients | Clients đang chờ backend |
| maxwait | Thời gian chờ lâu nhất ở pool |
| Pool checkout latency | Thời gian app đợi JDBC Connection |
| Query p95/p99 | Độ trễ SQL thực |
| Transaction duration | Thời gian giữ backend/locks |
| Invalid prepared statement errors | Dấu hiệu protocol/pool mismatch |
| Duplicate prepared name errors | Dấu hiệu session cache/cleanup sai |
| temp files and temp tables | Áp lực tài nguyên và lifetime |

### 30.5. Quan sát pg_prepared_statements đúng chỗ

`pg_prepared_statements` chỉ hiển thị state trong backend session đang chạy query. Query qua transaction pooling ở hai transaction khác nhau có thể nhìn những backend khác nhau; không dùng kết quả đó làm inventory cluster-level.

---

## 31. Lỗi hay gặp và cách chẩn đoán

### 31.1. prepared statement does not exist

Ví dụ SQLSTATE `26000`:

```text
ERROR: prepared statement "stmt_17" does not exist
```

Những nguyên nhân có thể:

- Client PREPARE trên backend A, EXECUTE trên backend B.
- PgBouncer transaction pooling thiếu hỗ trợ/cấu hình protocol prepared.
- Session/backend bị reset hoặc reconnect.
- `DEALLOCATE/DISCARD ALL` đã xóa prepared statement nhưng driver chưa cập nhật state.

Kiểm tra pool mode, driver, `max_prepared_statements` và giới hạn của SQL PREPARE so với protocol prepare.

### 31.2. prepared statement already exists

Ví dụ SQLSTATE `42P05`:

```text
ERROR: prepared statement "stmt_17" already exists
```

Có thể do code chuẩn bị lại tên trên một backend vẫn giữ tên từ client/request trước đó, reset policy không phù hợp hoặc driver/pooler chưa đồng bộ session state.

Không giải quyết bằng cách đổi sang tên ngẫu nhiên không giới hạn cho mỗi request; làm vậy có thể tạo thêm session bloat nếu statements không được deallocate.

### 31.3. relation does not exist

Ví dụ SQLSTATE `42P01`:

```text
ERROR: relation "tmp_ids" does not exist
```

Nguyên nhân thường gặp:

- Temp table tạo ở backend khác.
- `ON COMMIT DROP` làm table biến mất trước statement sau.
- Session đã bị reset/reconnect.
- `search_path` khác.
- Table chưa được tạo trong transaction hiện tại.

### 31.4. relation already exists

```text
ERROR: relation "tmp_ids" already exists
```

Có thể vì temporary table `PRESERVE ROWS` hoặc `DELETE ROWS` còn tồn tại từ request trước trên cùng session.

### 31.5. current transaction is aborted

SQLSTATE `25P02` thường là **hậu quả** của lỗi trước đó trong transaction. Phải tìm lỗi gốc và rollback. Không gửi thêm SET/SELECT như thể transaction vẫn bình thường.

### 31.6. Session biến mất

Lỗi mạng, connection reset, backend termination hoặc failover có thể xóa prepared/temp/session state. Retry business transaction cần xử lý idempotency và commit outcome; không chỉ reconnect rồi tiếp tục từ statement thứ ba.

### 31.7. Mất notification

Ứng dụng dùng `LISTEN` qua PgBouncer transaction pool có thể không có listener session ổn định. Tách dedicated connection và đăng ký lại sau reconnect.

### 31.8. Advisory lock giữ quá lâu

Kiểm tra session-level `pg_advisory_lock` không được unlock; chuyển sang `pg_advisory_xact_lock` nếu business scope chỉ là transaction.

---

## 32. Chọn chiến lược pool cho từng loại workload

| Workload | Hướng cân nhắc | Lý do |
|---|---|---|
| API CRUD, transactions ngắn, không giữ session state | PgBouncer transaction pooling | Multiplex backend tốt khi ứng dụng tuân thủ |
| API với TEMP ON COMMIT DROP trong một transaction | Transaction pooling có thể dùng | Backend được giữ trong transaction |
| Job nhiều transactions cần same temp table | Direct/session pooling hoặc đổi kiến trúc | State cần session pinned |
| Dedicated LISTEN/NOTIFY receiver | Direct/session pooling | LISTEN là session state |
| JDBC dùng named protocol prepared trong transaction pooling | PgBouncer hỗ trợ version + `max_prepared_statements` | Pooler phải map tên và chuẩn bị ở backend |
| SQL PREPARE xuyên commits | Direct/session pooling hoặc refactor | SQL PREPARE session-bound |
| Cursor WITH HOLD qua commits | Direct/session pooling | Cursor thuộc session |
| Advisory lock trong transaction | `pg_advisory_xact_lock` | Không giữ lock sau COMMIT |
| Multi-tenant request-scoped GUC | Explicit transaction + `SET LOCAL` | Tránh rò state, nhưng vẫn cần authorization |
| DDL migrations hoặc các scripts tùy biến session | Tách pool/connection phù hợp | Dễ cần session pinning hoặc lock time dài |

### 32.1. Tách pool theo nhu cầu là bình thường

Một hệ thống có thể dùng:

```text
web-api-pool        -> PgBouncer transaction pooling
notification-listen -> direct connection
migration-runner    -> direct connection / controlled admin session
long-reporting      -> dedicated read pool với cấu hình phù hợp
```

Không nhất thiết một endpoint và một pool mode phục vụ mọi chức năng.

### 32.2. Transaction pooling không phải universal accelerator

Nó không làm một query chậm thành query nhanh; nó chủ yếu tối ưu sử dụng PostgreSQL backend connections. Nếu workload bị giới hạn bởi I/O hoặc locks, cần tối ưu SQL/index/transaction duration bên cạnh connection pool.

---

## 33. Kế hoạch chuyển từ session pool sang transaction pool

### 33.1. Kiểm kê session features

Tìm trong ứng dụng/ORM/scripts:

- `SET search_path`, `SET ROLE`, custom `SET`.
- `CREATE TEMP TABLE` và `ON COMMIT`.
- SQL `PREPARE/EXECUTE`.
- JDBC server-side named prepare/cache.
- `LISTEN`.
- `pg_advisory_lock`.
- `DECLARE CURSOR WITH HOLD`.
- Transaction mở dài và streaming ResultSet.
- Những DDL migrations hoặc extension calls phụ thuộc session.

### 33.2. Chuyển session state sang transaction scope

- `SET` request-local → `SET LOCAL` khi phù hợp.
- Temp table cross-transaction → `ON COMMIT DROP` trong một transaction hoặc persistent staging table.
- Session advisory lock → transaction advisory lock hoặc dedicated connection.
- LISTEN → dedicated direct/session connection.
- SQL PREPARE cross-transaction → bỏ dependency, dùng driver protocol tương thích hoặc session mode.

### 33.3. Xác minh prepared compatibility

Chốt **chính xác**:

1. PgBouncer version.
2. Pool mode.
3. `max_prepared_statements`.
4. Driver/ORM version.
5. Driver server-side prepare options.
6. Feature/statement type (SQL PREPARE hay protocol prepared).

Không chỉ dựa vào việc “test vài query thành công”.

### 33.4. Test dưới concurrency

Tạo nhiều requests xen kẽ trên nhiều physical connections. Với transaction pooling, cần test khi backend reassignment thực sự xảy ra, không chỉ một client với một backend rảnh.

### 33.5. Rollout và rollback

Triển khai từng service/pool riêng, monitor SQLSTATE và request correctness, giữ đường quay lại session/direct endpoint khi có lỗi không tương thích.

### 33.6. Không thay mode cho migrations mà chưa kiểm tra

DDL và schema migrations có thể cần long transactions, temporary objects hoặc session settings. Chạy migration qua pooler đã được kiểm chứng hoặc connection trực tiếp; không mặc định giống CRUD API.

---

## 34. Quy trình reset một connection khi bị nhiễm state

### 34.1. Khi nào nên loại physical connection?

Một connection có thể cần được loại thay vì trả lại pool nếu:

- Transaction outcome hoặc session state không thể xác nhận.
- Backend/server đã disconnect.
- Rollback thất bại.
- Application không biết có đang giữ session-level lock, TEMP object hay role state không.
- Driver/server prepare cache đã mất đồng bộ mà không có cơ chế phục hồi an toàn.

### 34.2. Không chạy DISCARD ALL bên trong transaction

```sql
BEGIN;

-- Không hợp lệ bên trong transaction:
-- DISCARD ALL;

ROLLBACK;
```

`DISCARD ALL` chỉ dùng ngoài transaction block, khi chắc chắn không còn business work đang thực hiện.

### 34.3. Vấn đề driver protocol state

Nếu bạn gửi raw `DISCARD ALL` sau mỗi request trên một JDBC connection còn được driver cache named statements, driver có thể không nhận được tín hiệu xóa caches tương ứng.

Một phương án an toàn hơn là dùng pool/driver reset API đã được nhà cung cấp hỗ trợ hoặc **đóng physical connection** để tạo session mới nếu không thể đồng bộ.

### 34.4. Trước khi reset, phải xác nhận quyền

`DISCARD ALL` có thể làm mất role setting, temp objects, LISTEN subscriptions và lock đã được một component khác giữ có chủ đích. Trong kiến trúc nhiều component dùng chung session, reset không đúng thời điểm có thể gây lỗi.

### 34.5. Tách lỗi nghiệp vụ và connection hygiene

Một transaction bị từ chối vì constraint nghiệp vụ cần rollback. Một connection đã hỏng hoặc bị nhiễm state cần bị loại hoặc reset. Hai bước xử lý có thể cùng xuất hiện nhưng **không thay thế nhau**.

---

## 35. Những sai lầm phổ biến

**1. “Connection.close() của JDBC pool luôn đóng PostgreSQL backend session.”** Sai. Thường chỉ trả logical handle về pool.

**2. “COMMIT xóa toàn bộ trạng thái session.”** Sai. Nó kết thúc transaction, không tự xóa session GUC, temp PRESERVE ROWS, SQL PREPARE, LISTEN hay session advisory locks.

**3. “SET và SET LOCAL giống nhau.”** Sai. Scope và rollback semantics khác nhau.

**4. “SET LOCAL ngoài transaction vẫn được giữ cho query tiếp theo.”** Không.

**5. “Custom GUC app.tenant_id tự chứng minh quyền tenant.”** Không. Caller có thể có khả năng tự đặt nó; cần authorization.

**6. “TimeZone và search_path chỉ ảnh hưởng hiển thị.”** Không. Có thể ảnh hưởng semantics parsing, resolution và query results.

**7. “Pool luôn reset mọi SQL SET tự phát.”** Không được mặc định.

**8. “connectionInitSql chạy lại cho từng request.”** Không phải contract mặc định của physical connection initialization.

**9. “Temporary table là request-local.”** Sai. Mặc định là session-local.

**10. “Temporary table mặc định tự drop lúc COMMIT.”** Sai. PostgreSQL mặc định `ON COMMIT PRESERVE ROWS`.

**11. “ON COMMIT DELETE ROWS xóa luôn table.”** Sai. Table còn ở session.

**12. “ON COMMIT DROP chạy được qua nhiều autocommit statements.”** Không. Table có thể drop ngay sau statement tạo.

**13. “PRESERVE ROWS an toàn xuyên transactions với PgBouncer transaction pool.”** Không.

**14. “DELETE ROWS temp table an toàn vì dữ liệu đã xóa.”** Không, table object vẫn session-bound.

**15. “Transaction pool thay backend giữa hai statements trong cùng transaction bình thường.”** Không theo contract; server connection được giữ trong transaction.

**16. “Statement pooling cho phép multi-statement transaction như session mode.”** Không.

**17. “Một PID trùng hai lần chứng minh backend luôn pinned.”** Không; có thể do pooler chọn lại tình cờ.

**18. “PREPARE là cache dữ liệu SELECT.”** Không. Nó giữ cấu trúc chuẩn bị/plan, query vẫn thực thi.

**19. “JDBC PreparedStatement luôn gửi SQL PREPARE.”** Không.

**20. “PgBouncer transaction pooling không bao giờ hỗ trợ bất kỳ prepared statements nào.”** Không còn đúng: protocol-level named prepared có hỗ trợ có điều kiện từ PgBouncer 1.21.

**21. “max_prepared_statements khác 0 làm SQL PREPARE/EXECUTE xuyên sessions hoạt động.”** Không. Tính năng hỗ trợ protocol-level named statements; SQL PREPARE riêng.

**22. “prepareThreshold=0 làm JDBC mất khả năng bind parameters.”** Không. Nó tắt kiểu server-side named prepare theo pgJDBC, không bỏ PreparedStatement API.

**23. “pg_prepared_statements cho biết tất cả prepared của cluster.”** Sai. Nó là view cho session hiện tại.

**24. “DISCARD PLANS và DEALLOCATE ALL tương đương.”** Không.

**25. “RESET ALL xóa temp tables.”** Không.

**26. “DISCARD ALL chạy được trong một transaction.”** Không.

**27. “DISCARD ALL luôn an toàn khi driver cache named statements.”** Không nếu client/server state không đồng bộ.

**28. “PgBouncer server_reset_query luôn chạy sau mỗi transaction.”** Không trong transaction pooling theo mặc định.

**29. “Dùng session pooling với Hikari nghĩa PgBouncer reset backend sau mỗi web request.”** Không nếu physical Hikari connection vẫn mở.

**30. “ROLLBACK giải phóng pg_advisory_lock session-level.”** Không.

**31. “LISTEN hoạt động ổn định qua transaction pooling.”** Không.

**32. “NOTIFY không thể dùng trong transaction pooling vì LISTEN không tương thích.”** Hai tính năng khác nhau; NOTIFY có thể dùng.

**33. “Cursor WITH HOLD không cần same session sau COMMIT.”** Sai.

**34. “Một transaction lỗi vẫn có thể chạy SELECT tiếp nếu bỏ qua exception.”** Không; thường cần rollback (25P02).

**35. “Connection đã lỗi rollback vẫn cứ trả lại pool.”** Nguy hiểm; cần chính sách loại connection khi state không xác định.

**36. “Prepared statement được chuẩn bị trên một backend có thể luôn EXECUTE trên backend khác.”** Sai nếu thiếu pooler protocol remapping.

**37. “SQLSTATE 26000 và 42P05 là cùng lỗi.”** Không. Một cái không tồn tại tên, một cái trùng tên.

**38. “Mọi GUC custom được PgBouncer track tự động.”** Không; phụ thuộc version/parameter reporting/cấu hình.

**39. “Search path là tenant authorization.”** Không.

**40. “Prepared statement tên unqualified luôn mãi tham chiếu cùng object bất kể DDL/search_path.”** Không đơn giản như vậy; reparse/replan có điều kiện.

**41. “Một pool lớn luôn tăng throughput.”** Không nếu database đã bão hòa.

**42. “Đổi pool mode không cần test driver version.”** Sai.

**43. “Idle in transaction không ảnh hưởng database.”** Có thể giữ locks/snapshots và gây bloat/contension.

**44. “Application pool và PgBouncer luôn là cùng một loại pool.”** Không. Hai lớp có lifetime và reset points khác nhau.

**45. “Mọi lỗi sau đổi pool mode đều do database chậm.”** Không; nhiều lỗi là contract mismatch về session state.

---

## 36. Bài tập thực hành có đáp án

### Bài 1 — Logical close

**Câu hỏi:** `Connection.close()` khi dùng HikariCP có mặc nhiên kết thúc PostgreSQL backend session không?

**Đáp án:** Không. Thường trả logical connection về pool, physical session vẫn được giữ để tái sử dụng.

### Bài 2 — Phạm vi SET

```sql
BEGIN;
SET TimeZone = 'UTC';
COMMIT;
```

**Câu hỏi:** Session có giữ UTC sau COMMIT không?

**Đáp án:** Có theo semantics của `SET` nếu transaction chứa SET commit thành công.

### Bài 3 — SET LOCAL

```sql
BEGIN;
SET LOCAL TimeZone = 'UTC';
COMMIT;
```

**Đáp án:** Giá trị LOCAL hết hiệu lực sau transaction; session quay lại setting trước LOCAL.

### Bài 4 — Request context

**Yêu cầu:** Đặt tenant context chỉ trong transaction.

```sql
BEGIN;
SET LOCAL app.tenant_id = '10';
SELECT current_setting('app.tenant_id');
COMMIT;
```

### Bài 5 — SET LOCAL trong JDBC

**Câu hỏi:** Vì sao phải `setAutoCommit(false)` trước khi đặt local context rồi SELECT?

**Đáp án:** Để SET LOCAL và SELECT nằm cùng transaction; autocommit có thể kết thúc scope local ngay sau statement đầu.

### Bài 6 — GUC và security

**Câu hỏi:** Có thể dùng `current_setting('app.tenant_id')` làm bằng chứng quyền tenant không?

**Đáp án:** Không nếu client/role có thể tự SET bất kỳ giá trị. Cần authentication/authorization và database policy thích hợp.

### Bài 7 — Default temp ON COMMIT

**Đáp án:** PostgreSQL mặc định `ON COMMIT PRESERVE ROWS` cho temp table khi không chỉ rõ.

### Bài 8 — ON COMMIT DELETE ROWS

**Câu hỏi:** Sau COMMIT, bảng còn không?

**Đáp án:** Còn table object, dữ liệu bị xóa theo semantics DELETE ROWS.

### Bài 9 — ON COMMIT DROP

**Câu hỏi:** Sau COMMIT, bảng còn không?

**Đáp án:** Không, bảng đã được drop.

### Bài 10 — Temp trong transaction pooling

**Yêu cầu:** Tạo table và dùng nó trong một transaction.

```sql
BEGIN;
CREATE TEMP TABLE tmp_lab (id bigint) ON COMMIT DROP;
INSERT INTO tmp_lab VALUES (1);
SELECT * FROM tmp_lab;
COMMIT;
```

### Bài 11 — Temp qua transaction boundary

**Câu hỏi:** Có thể dùng temp `PRESERVE ROWS` từ transaction 1 trong transaction 2 khi PgBouncer transaction pooling?

**Đáp án:** Không được dựa vào; transaction 2 có thể lấy backend khác và không thấy table.

### Bài 12 — Autocommit

**Câu hỏi:** Tại sao một câu `CREATE TEMP TABLE ... ON COMMIT DROP` ở autocommit có thể làm câu INSERT sau báo relation not found?

**Đáp án:** Table bị drop ngay khi transaction ngầm của statement CREATE commit.

### Bài 13 — SQL PREPARE

```sql
PREPARE lookup_order(bigint) AS
SELECT * FROM pool_state_lab.orders WHERE order_id = $1;

EXECUTE lookup_order(1);

DEALLOCATE lookup_order;
```

**Đáp án:** SQL PREPARE tạo session object, EXECUTE dùng tên trên cùng backend, DEALLOCATE xóa nó.

### Bài 14 — Prepared statement qua COMMIT

**Câu hỏi:** SQL PREPARE có tồn tại sau COMMIT trên cùng direct backend session không?

**Đáp án:** Có, tới khi DEALLOCATE/session end/reset thích hợp.

### Bài 15 — Prepared trong PgBouncer transaction

**Câu hỏi:** Có thể SQL PREPARE trước COMMIT rồi EXECUTE trong transaction khác không?

**Đáp án:** Không được dựa vào; backend có thể đổi.

### Bài 16 — Protocol-level prepared

**Câu hỏi:** Từ PgBouncer 1.21, điều kiện nào hỗ trợ named protocol prepared trong transaction pooling?

**Đáp án:** Version hỗ trợ, driver dùng protocol-level statements phù hợp và cấu hình `max_prepared_statements` khác 0, cùng các điều kiện tương thích khác.

### Bài 17 — max_prepared_statements và SQL PREPARE

**Câu hỏi:** Bật `max_prepared_statements=100` có tự làm SQL `PREPARE/EXECUTE` session-scoped hoạt động xuyên transactions không?

**Đáp án:** Không. Hỗ trợ nói đến protocol-level named statements.

### Bài 18 — JDBC parameter binding

**Câu hỏi:** `prepareThreshold=0` có làm `PreparedStatement.setInt(...)` không dùng được không?

**Đáp án:** Không. Nó thay server-side named prepare behavior của pgJDBC, không xóa parameter binding API.

### Bài 19 — pg_prepared_statements

```sql
SELECT name, from_sql
FROM pg_prepared_statements;
```

**Đáp án:** Quan sát prepared statements của session hiện tại và nguồn SQL hay protocol-level.

### Bài 20 — Duplicate prepared name

**Câu hỏi:** Lỗi SQLSTATE `42P05` gợi ý gì?

**Đáp án:** Tên prepared statement đã tồn tại trong session; kiểm tra việc prepare lại/reset/pooler state.

### Bài 21 — Missing prepared name

**Câu hỏi:** Lỗi SQLSTATE `26000` có thể đến từ đâu?

**Đáp án:** EXECUTE/driver tham chiếu tên chưa được chuẩn bị trên backend hiện tại hoặc đã bị reset/deallocate.

### Bài 22 — RESET ALL

**Câu hỏi:** `RESET ALL` có xóa temp tables và SQL PREPARE không?

**Đáp án:** Không. Nó reset settings, không phải cleanup toàn session.

### Bài 23 — DISCARD ALL

**Câu hỏi:** Có thể chạy `DISCARD ALL` trong transaction đang mở không?

**Đáp án:** Không. Nó không được thực thi trong transaction block.

### Bài 24 — DISCARD PLANS

**Câu hỏi:** `DISCARD PLANS` có tương đương `DEALLOCATE ALL` không?

**Đáp án:** Không. Nó bỏ cached plans, không xóa tên prepared statements như DEALLOCATE.

### Bài 25 — PgBouncer reset query

**Câu hỏi:** `server_reset_query=DISCARD ALL` có mặc định chạy sau mỗi commit trong PgBouncer transaction pooling không?

**Đáp án:** Không. Theo mode mặc định, reset query phục vụ session pooling khi server connection được trả sau client session, không chạy sau mọi transaction.

### Bài 26 — Hikari + PgBouncer session mode

**Câu hỏi:** Vì sao Request B có thể thấy temp table của Request A?

**Đáp án:** Hikari có thể tái sử dụng physical client connection còn giữ cùng PgBouncer/backend session; reset query của PgBouncer chưa chạy nếu client connection chưa disconnect.

### Bài 27 — Session advisory lock

**Câu hỏi:** `ROLLBACK` có tự giải phóng `pg_advisory_lock(901)` không?

**Đáp án:** Không. Nó là session-level advisory lock; cần unlock hoặc end session.

### Bài 28 — Transaction advisory lock

```sql
BEGIN;
SELECT pg_advisory_xact_lock(901);
COMMIT;
```

**Đáp án:** Lock tự giải phóng tại transaction end.

### Bài 29 — LISTEN

**Câu hỏi:** Một long-lived LISTEN receiver nên dùng transaction pooling?

**Đáp án:** Không. Dùng dedicated direct connection/session pool có backend pinned và đăng ký lại khi reconnect.

### Bài 30 — NOTIFY

**Câu hỏi:** NOTIFY có cùng yêu cầu session lifetime như LISTEN không?

**Đáp án:** Không. Phát NOTIFY có thể dùng transaction pooling; subscriber LISTEN cần session ổn định.

### Bài 31 — Cursor WITH HOLD

**Câu hỏi:** Vì sao FETCH sau COMMIT bằng cursor WITH HOLD không phù hợp transaction pooling?

**Đáp án:** Cursor tồn tại ở backend session cũ; transaction sau có thể dùng backend khác.

### Bài 32 — Lỗi 25P02

**Câu hỏi:** Sau một statement lỗi trong transaction, bước cleanup thông thường?

**Đáp án:** Ghi nhận lỗi gốc và `ROLLBACK` trước khi dùng lại connection; không tiếp tục chạy SELECT như transaction không lỗi.

### Bài 33 — pg_backend_pid

**Câu hỏi:** Hai lần gọi PID trùng nhau có chứng minh PgBouncer đang session pooling không?

**Đáp án:** Không. Transaction pool có thể tình cờ chọn lại cùng backend.

### Bài 34 — Connection pool sizing

**Câu hỏi:** Tăng Hikari pool từ 20 lên 200 có luôn làm throughput tăng?

**Đáp án:** Không. Database có thể bị contention/CPU/I/O và tăng số backend chỉ làm chậm hơn. Đo workload/queue/DB latency.

### Bài 35 — Migrating pooling mode

**Yêu cầu:** Nêu bốn nhóm cần audit trước khi chuyển sang transaction pooling.

**Đáp án:** (1) session SET/tenant GUC/search_path, (2) temporary tables ON COMMIT, (3) server-side prepared statement mode/driver/PgBouncer version, (4) session locks/LISTEN/cursors. Nên thêm migrations, transaction length và cleanup.

### Bài 36 — Giải pháp cho nhiều bước với temp table

**Tình huống:** Cần CREATE TEMP → INSERT → SELECT trong một đơn vị công việc.

**Đáp án:** Đưa toàn bộ vào cùng transaction, dùng `ON COMMIT DROP` và chọn pool mode hỗ trợ multi-statement transaction.

### Bài 37 — Connection init

**Câu hỏi:** Vì sao không đặt `connectionInitSql=SET app.tenant_id='10'` cho hệ thống multi-tenant?

**Đáp án:** Nó thiết lập baseline khi physical connection khởi tạo, không thay tenant context theo request và có thể tạo rò/nhầm tenant.

### Bài 38 — Test compatibility

**Yêu cầu:** Thiết kế một test khi PgBouncer transaction pooling và driver dùng named prepare.

**Đáp án:** Sử dụng nhiều client connections và nhiều transactions ngắn, xen kẽ với các query tham số giống nhau; theo dõi `pg_backend_pid` để xác nhận có backend reassignment trong một số lần, quan sát SQLSTATE 26000/42P05, cấu hình `max_prepared_statements`, driver prepareThreshold và kiểm tra query results đúng. Không kết luận chỉ từ một lượt không đổi PID.

---

## 37. Checklist ứng dụng PostgreSQL với pool

### Hợp đồng connection/transaction

1. Xác định một lần borrow/return **logical** connection có tương ứng physical session mới không.
2. Nếu có PgBouncer, biết **pool_mode** thực sự.
3. Biết PgBouncer endpoint và phiên bản.
4. Biết số physical connections qua mọi service instances.
5. Không trả connection khi transaction chưa commit/rollback.
6. Xử lý rollback failure bằng connection invalidation phù hợp.
7. Có timeout và quan sát checkout latency.

### GUC và bảo mật

8. Không dùng `SET` session-level cho context thay đổi mỗi request nếu không reset.
9. Dùng `SET LOCAL` trong một transaction thật khi phù hợp.
10. Kiểm tra `set_config(..., true)` được thực hiện trước query cần context.
11. Không tin custom GUC là authentication/authorization.
12. Xem RLS/SECURITY DEFINER/search_path với role thật.
13. Biết GUC nào PgBouncer version/config có thể track.
14. Không mặc định pool reset mọi custom SQL SET.
15. Tách migration/admin role khỏi runtime role.

### Temporary tables

16. Biết PostgreSQL mặc định `ON COMMIT PRESERVE ROWS`.
17. Nếu cần transaction-lifetime, dùng `ON COMMIT DROP`.
18. Không tạo ON COMMIT DROP rồi dùng qua autocommit statements.
19. Không dựa vào PRESERVE/DELETE ROWS trong transaction pooling.
20. Tránh temp table nếu CTE/VALUES/unnest đáp ứng tốt.
21. Không để bảng tạm che relation trusted do search_path.
22. Có cleanup/retention theo session khi dùng session pooling.

### Prepared statements

23. Phân biệt SQL `PREPARE` và JDBC `PreparedStatement`.
24. Phân biệt protocol-level named prepare với SQL PREPARE.
25. Kiểm tra pgJDBC `prepareThreshold`/driver version.
26. Với PgBouncer transaction pool, xem `max_prepared_statements` và feature support.
27. Không coi SQL PREPARE qua commits là được remap tự động.
28. Không DISCARD/DEALLOCATE bất ngờ làm driver cache lệch.
29. Quan sát SQLSTATE `26000`, `42P05` và schema migration errors.
30. Không coi prepared statement là cache kết quả SELECT.

### Other session state

31. Không giữ session advisory locks trong transaction pool.
32. Ưu tiên `pg_advisory_xact_lock` khi scope là transaction.
33. Tách long-lived LISTEN receiver.
34. Không dùng WITH HOLD cursor qua transaction pool.
35. Đóng ResultSet/cursor trước khi trả connection.
36. Theo dõi idle in transaction.

### Vận hành

37. Hiểu `RESET ALL`, `DEALLOCATE ALL`, `DISCARD TEMP`, `DISCARD ALL`.
38. Không chạy DISCARD ALL trong transaction.
39. Không coi `server_reset_query` chạy ở mọi pool mode.
40. Test reset behavior cả ở application pool và PgBouncer.
41. Test nhiều clients, backend reassignment, retries và failover.
42. Có runbook chuyển về session/direct endpoint khi tính năng không tương thích.
43. Đo actual query latency, queue wait, server backends và resource usage.
44. Không dùng pool size để thay chữa SQL query hoặc transaction giữ lock lâu.

---

## 38. Kết luận: tài nguyên theo session cần được đối xử như session state

Chính sự khác nhau giữa **logical request**, **database transaction** và **physical PostgreSQL session** quyết định một tính năng có hoạt động đúng khi thêm connection pool hay không.

**Ghi nhớ năm nguyên tắc:**

1. **Không mặc định logical connection close đóng physical session.** HikariCP và các application pools thường tái sử dụng connections.
2. **Dùng transaction scope cho state của một request.** `SET LOCAL`, `ON COMMIT DROP` và transaction advisory locks giúp giảm rủi ro state còn lại sau khi request kết thúc; nhưng chỉ an toàn khi có transaction boundary đúng.
3. **Transaction pooling không bảo đảm session pinning qua COMMIT.** Temp tables PRESERVE/DELETE ROWS, SQL PREPARE, LISTEN, session advisory locks và WITH HOLD cursors không thể được dùng xuyên transactions như khi kết nối trực tiếp.
4. **Prepared statements có nhiều loại.** PgBouncer 1.21+ có hỗ trợ có điều kiện cho **protocol-level named prepared statements** với `max_prepared_statements` khác 0; điều này không làm SQL `PREPARE/EXECUTE` trở nên session-independent.
5. **Reset phải hiểu driver/pooler.** `RESET ALL` không phải `DISCARD ALL`, `DISCARD PLANS` không phải `DEALLOCATE ALL`, và reset phía server có thể làm mất đồng bộ với prepared cache phía client.

Một nguyên tắc thiết kế thực dụng:

```text
Một request cần trạng thái tạm thời?
             |
             v
Có thể biểu diễn trong đúng một transaction?
         /                         \
       Có                          Không
       |                              |
       v                              v
  SET LOCAL, TEMP                Có thực sự cần session
  ON COMMIT DROP,                state xuyên commits?
  xact locks                      /               \
       |                        Có                Không
       v                        |                   |
Transaction pooling             v                   v
  có thể phù hợp           Session/direct       Refactor sang
  khi driver tương thích   connection pool       transactional/
                           có cleanup rõ         persistent state
```

**Câu hỏi tự kiểm tra cuối bài:** Khi request A trả JDBC Connection, những dữ liệu nào **được commit vào bảng nghiệp vụ**, những trạng thái nào **đã kết thúc với transaction**, và những đối tượng nào **vẫn còn trong PostgreSQL backend session**? Nếu application, pool và PgBouncer có cùng một câu trả lời rõ ràng cho ba câu hỏi này, bạn mới có cơ sở tin việc tái sử dụng kết nối là đúng và an toàn.

### Tài liệu chính thức và nguồn tham khảo

- [PostgreSQL — SET (SESSION và LOCAL)](https://www.postgresql.org/docs/current/sql-set.html).
- [PostgreSQL — RESET](https://www.postgresql.org/docs/current/sql-reset.html).
- [PostgreSQL — DISCARD](https://www.postgresql.org/docs/current/sql-discard.html).
- [PostgreSQL — CREATE TABLE (Temporary tables và ON COMMIT)](https://www.postgresql.org/docs/current/sql-createtable.html).
- [PostgreSQL — PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html).
- [PostgreSQL — EXECUTE](https://www.postgresql.org/docs/current/sql-execute.html).
- [PostgreSQL — DEALLOCATE](https://www.postgresql.org/docs/current/sql-deallocate.html).
- [PostgreSQL — pg_prepared_statements](https://www.postgresql.org/docs/current/view-pg-prepared-statements.html).
- [PostgreSQL — Session information functions](https://www.postgresql.org/docs/current/functions-info.html).
- [PostgreSQL — Advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS).
- [PostgreSQL — LISTEN](https://www.postgresql.org/docs/current/sql-listen.html).
- [PostgreSQL — NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html).
- [PostgreSQL — DECLARE cursor](https://www.postgresql.org/docs/current/sql-declare.html).
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [PostgreSQL — Row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [PgBouncer — Pooling Modes and Feature Compatibility](https://www.pgbouncer.org/features.html).
- [PgBouncer — Configuration: pool_mode, max_prepared_statements, server_reset_query](https://www.pgbouncer.org/config.html).
- [PgBouncer — FAQ: JDBC prepared statement compatibility](https://www.pgbouncer.org/faq.html).
- [PgBouncer — Administrative Console](https://www.pgbouncer.org/usage.html).
- [pgJDBC — Connection Parameters](https://jdbc.postgresql.org/documentation/use/).
