# Hàm hệ thống, thông tin phiên và kiểm tra quyền

Khi viết ứng dụng với PostgreSQL, không phải lúc nào vấn đề cũng nằm ở câu `SELECT` hay cấu trúc bảng. Có lúc một truy vấn chạy được trong `psql` nhưng thất bại qua JDBC; một service kết nối đúng database mà không tìm thấy bảng; một người dùng có quyền `SELECT` nhưng không nhìn thấy hàng nào; hoặc một kết nối dùng lại từ pool vẫn mang cấu hình của request trước. Những tình huống đó liên quan tới **danh tính của phiên**, **ngữ cảnh thực thi**, **cấu hình đang có hiệu lực** và **cơ chế kiểm soát quyền**.

PostgreSQL cung cấp nhiều hàm hệ thống và biểu thức đặc biệt để trả lời các câu hỏi này:

- “Tôi đang kết nối tới database nào, bằng tài khoản nào?” — `current_database()`, `session_user`.
- “Lệnh hiện tại đang được kiểm tra quyền theo role nào?” — `current_user`, `current_role`.
- “Tên bảng không ghi schema sẽ được tìm ở đâu?” — `current_schema()`, `current_schemas()`, `current_setting('search_path')`.
- “Đây là backend nào; kết nối tới server qua TCP hay Unix socket?” — `pg_backend_pid()`, `inet_client_addr()`, `inet_server_addr()`.
- “Cấu hình `statement_timeout`, `TimeZone`, `application_name` thực sự là gì?” — `SHOW`, `current_setting()`, `pg_settings`.
- “Role này có thể đọc bảng, cột, schema, sequence hoặc gọi function không?” — các hàm `has_*_privilege()` và `pg_has_role()`.
- “Quyền đã có nhưng dữ liệu vẫn bị lọc?” — kiểm tra thêm **row-level security (RLS)**, quyền theo cột, role đang hiệu lực và ngữ cảnh truy vấn.

Bài học đi từ khái niệm đến truy vấn thực hành, phục vụ cả người học SQL, lập trình viên Java/JDBC, người thiết kế phân quyền và người xử lý sự cố vận hành.

> **Phạm vi:** Các ví dụ sử dụng PostgreSQL hiện đại, với một schema thử nghiệm tên `lesson_sys`. Câu lệnh tạo role, cấp/thu hồi quyền, thay đổi `search_path` và đặt role có thể cần đặc quyền riêng. Chỉ thực hiện thao tác thay đổi quyền trong môi trường lab được cho phép; trong hệ thống thật cần tuân thủ quy trình bảo mật và nguyên tắc đặc quyền tối thiểu. Kết quả của một số hàm phụ thuộc role, phương thức kết nối và phiên bản PostgreSQL nên không thể mặc định mọi người sẽ thấy cùng giá trị.

## 1. Hàm hệ thống và biểu thức đặc biệt

Một số thành phần thường được gọi chung là “hàm hệ thống”, nhưng **cú pháp SQL của chúng không hoàn toàn giống nhau**:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| **Thông tin danh tính** | `current_user`, `session_user`, `current_role` | Xác định role thực thi và role phiên. |
| **Thông tin database/schema** | `current_database()`, `current_schema()`, `current_schemas(true)` | Xác định ngữ cảnh tìm đối tượng. |
| **Thông tin backend/kết nối** | `pg_backend_pid()`, `inet_client_addr()` | Nhận diện backend và một số thuộc tính network. |
| **Cấu hình runtime** | `current_setting()`, `set_config()`, `pg_settings` | Đọc/đặt tham số cấu hình. |
| **Thời gian phiên/transaction** | `now()`, `statement_timestamp()`, `clock_timestamp()` | Phân biệt thời điểm transaction, statement và đồng hồ. |
| **Kiểm tra quyền** | `has_table_privilege()`, `has_schema_privilege()`, `pg_has_role()` | Kiểm tra một số quyền ở cấp object/role. |
| **Thông tin hệ thống** | `version()`, `pg_is_in_recovery()`, `pg_postmaster_start_time()` | Nhận biết phiên bản và trạng thái server. |

Ví dụ tối thiểu:

```sql
SELECT
    current_user,
    session_user,
    current_role,
    current_database(),
    current_schema(),
    pg_backend_pid();
```

Lưu ý: `current_user`, `session_user` và `current_role` là **những biểu thức SQL đặc biệt**, thường viết **không có cặp ngoặc**. Trong khi đó, `current_database()` và `pg_backend_pid()` là lời gọi hàm có ngoặc.

Không suy ra rằng mọi thứ trông giống từ khóa “current” đều có cùng kiểu cú pháp.

## 2. Chuẩn bị database lab

Các ví dụ tiếp theo sử dụng một bảng nhân viên đơn giản, một bảng công việc và một function để kiểm tra quyền gọi hàm.

```sql
CREATE SCHEMA IF NOT EXISTS lesson_sys;

CREATE TABLE lesson_sys.staff (
    staff_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    salary NUMERIC(12, 2) NOT NULL CHECK (salary >= 0),
    department TEXT NOT NULL
);

CREATE TABLE lesson_sys.tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES lesson_sys.staff(staff_id),
    title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('TODO', 'DOING', 'DONE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO lesson_sys.staff(full_name, email, salary, department)
VALUES
    ('An', 'an@example.invalid', 20000000, 'Engineering'),
    ('Bình', 'binh@example.invalid', 17000000, 'Engineering'),
    ('Chi', 'chi@example.invalid', 15000000, 'Support');

INSERT INTO lesson_sys.tasks(owner_id, title, status)
VALUES
    (1, 'Thiết kế API', 'DOING'),
    (1, 'Kiểm thử quyền', 'TODO'),
    (2, 'Viết tài liệu', 'DONE');
```

Đây là dữ liệu minh họa trong môi trường lab. Các giá trị `staff_id` được giả định là 1, 2, 3 khi bảng mới hoàn toàn và identity sequence bắt đầu mặc định; nếu database đã có dữ liệu, lấy ID thực bằng `INSERT ... RETURNING` thay vì dùng những số này.

Tạo một function có tên rõ ràng:

```sql
CREATE FUNCTION lesson_sys.normalize_label(p_label TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT lower(btrim(p_label))
$$;
```

Thử:

```sql
SELECT lesson_sys.normalize_label('  PostgreSQL  ') AS normalized;
-- postgresql
```

Sau khi tạo, bảng `lesson_sys.staff`, `lesson_sys.tasks` và function `lesson_sys.normalize_label(text)` là đối tượng phục vụ ví dụ kiểm tra quyền. **Đừng cấp quyền trên đối tượng demo này cho role production chỉ để chạy bài học**.

## 3. Phân biệt session và transaction

Một ứng dụng thường có cấu trúc:

```text
JDBC application
      │
      │ mở hoặc mượn Connection
      ▼
PostgreSQL session / backend
      ├── Danh tính phiên (session_user)
      ├── Role hiệu lực (current_user)
      ├── Cấu hình (TimeZone, search_path, application_name, ...)
      │
      ├── Transaction A: BEGIN ... COMMIT
      ├── Transaction B: BEGIN ... ROLLBACK
      └── Transaction C: BEGIN ... COMMIT
```

**Session** là ngữ cảnh của kết nối backend. Một session có thể thực hiện nhiều transaction nối tiếp nhau. **Transaction** là đơn vị nguyên tử cho những thao tác SQL có chung cam kết commit/rollback.

Trong một session:

- Role đang hiệu lực có thể bị thay đổi bằng những thao tác được phép như `SET ROLE`.
- Một số tham số cấu hình có phạm vi session và tồn tại qua nhiều transaction.
- `SET LOCAL` chỉ đặt cấu hình trong transaction hiện tại.
- `pg_backend_pid()` nhận diện backend hiện tại trong thời gian kết nối đó tồn tại.

Khi dùng connection pool, một **Connection object được trả về pool** có thể được **mượn lại cho một request khác**. Nếu không quản lý state rõ ràng, request sau có thể kế thừa những thiết lập cấp session không mong muốn.

## 4. current_user, session_user và current_role

Đây là nhóm biểu thức đầu tiên cần nhớ:

```sql
SELECT
    session_user AS session_login_role,
    current_user AS effective_role,
    current_role AS current_role_name;
```

| Biểu thức | Ý nghĩa | Có thể thay đổi khi nào? |
|---|---|---|
| `session_user` | Role làm **session authorization identifier**, thường là role đã xác thực lúc thiết lập phiên. | Có thể thay đổi bằng `SET SESSION AUTHORIZATION` khi đủ quyền; không tự đổi chỉ vì `SET ROLE`. |
| `current_user` | **Effective role** dùng trong phần lớn kiểm tra quyền cho SQL hiện tại. | Thay đổi với `SET ROLE`, `RESET ROLE` và tạm thời trong `SECURITY DEFINER` function. |
| `current_role` | Trong PostgreSQL, về cơ bản tương đương `current_user` cho ngữ cảnh role hiệu lực. | Phản ánh role hiệu lực tương ứng. |

Trong phiên kết nối bình thường, thường có:

```text
session_user = app_user
current_user = app_user
current_role = app_user
```

Tuy nhiên, **không được coi ba giá trị này luôn giống nhau**.

### Vì sao quan trọng?

Khi câu `SELECT` báo “permission denied”, bạn cần biết **role nào đang được dùng để kiểm tra quyền**. Chỉ nhìn tên tài khoản lúc đăng nhập có thể chưa đủ nếu ứng dụng đã gọi `SET ROLE` hoặc đang chạy function `SECURITY DEFINER`.

### current_user không tự là người dùng cuối của API

Một backend Java có thể dùng chung tài khoản database `app_service` để phục vụ hàng nghìn người dùng đã xác thực qua HTTP. Khi đó:

```text
Người dùng HTTP: user-101, user-102, ...
               │
               ▼
         Backend application
               │ DB connection bằng app_service
               ▼
current_user = app_service
```

`current_user` xác định **role PostgreSQL**, không tự cho biết người dùng nghiệp vụ đã đăng nhập vào web/mobile app.

## 5. SET ROLE và phạm vi thay đổi danh tính

`SET ROLE` dùng để đổi role hiệu lực khi session có quyền chuyển sang role đó.

Ví dụ **chỉ chạy nếu role đã tồn tại và session được phép đổi role**:

```sql
SELECT session_user, current_user;

SET ROLE lab_reader;

SELECT session_user, current_user, current_role;

RESET ROLE;

SELECT session_user, current_user;
```

Khi `SET ROLE lab_reader` thành công:

- `session_user` thường **không đổi**.
- `current_user` trở thành `lab_reader`.
- Các thao tác SQL tiếp theo chịu kiểm tra quyền theo role hiệu lực và các quy tắc membership/inheritance liên quan.

Nếu role không tồn tại hoặc session không được phép `SET ROLE`, lệnh thất bại. Không nên dùng `SET ROLE` như cách tự cấp quyền.

### Khác SET SESSION AUTHORIZATION

`SET SESSION AUTHORIZATION` có ngữ nghĩa thay đổi **session authorization identifier**, khác `SET ROLE`. Khả năng đặt sang một role khác bị hạn chế bởi quyền của người gọi; thao tác này không nên được dùng trong luồng ứng dụng thông thường chỉ để “thử quyền”.

Một cách nhớ:

```text
session_user ── gốc ủy quyền của session
current_user ── role hiệu lực cho hoạt động SQL hiện tại
```

Đối với kiểm tra quyền theo ngữ cảnh thực tế, **query lại cả hai biểu thức trên đúng connection** trước khi suy đoán.

## 6. SECURITY DEFINER và thay đổi tạm thời current_user

Function PostgreSQL có thể khai báo:

- `SECURITY INVOKER`: thường chạy theo quyền role gọi hàm.
- `SECURITY DEFINER`: chạy trong ngữ cảnh đặc quyền của **owner function**.

Hãy xem một function trong lab:

```sql
CREATE FUNCTION lesson_sys.who_is_executing()
RETURNS TABLE (
    effective_role NAME,
    session_role NAME
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT current_user::name, session_user::name
$$;
```

Khi gọi:

```sql
SELECT *
FROM lesson_sys.who_is_executing();
```

`effective_role` ở **bên trong function** thể hiện owner function theo quy tắc `SECURITY DEFINER`; `session_role` thể hiện session authorization. Nếu function được tạo bởi role khác role đang kết nối, hai giá trị có thể khác nhau.

### Vì sao không tự dùng current_user làm audit actor?

Khi một trigger function chạy `SECURITY DEFINER`, `current_user` **bên trong function** có thể là owner function, không phải caller ban đầu. Nếu audit yêu cầu “người dùng nghiệp vụ nào đã yêu cầu thao tác”, phải xây cơ chế truyền danh tính đã xác thực hoặc ghi sự kiện ở tầng đáng tin.

### Cảnh báo bảo mật

`SECURITY DEFINER` không phải cách tăng quyền tùy tiện. Khi cần dùng:

1. Function phải thuộc role đáng tin.
2. Khóa `search_path` an toàn; ưu tiên tên `schema.object` rõ ràng.
3. Kiểm soát quyền `EXECUTE`, kể cả grant mặc định cho `PUBLIC`.
4. Không xây dynamic SQL bằng cách nối input không đáng tin.
5. Rà soát quyền `CREATE` trên những schema xuất hiện trong `search_path`.

Function lab chỉ dùng biểu thức hệ thống, nhưng nguyên tắc vẫn áp dụng trước khi triển khai function có quyền đọc/sửa dữ liệu nhạy cảm.

## 7. current_database(): biết chính xác database đang kết nối

`current_database()` trả tên database mà connection hiện tại đang sử dụng:

```sql
SELECT current_database() AS database_name;
```

Trong PostgreSQL, **một connection gắn với một database cụ thể**. Không có cú pháp SQL phổ thông tương đương `USE other_database` của một số hệ khác để chuyển database ngay trong session hiện tại.

Nếu muốn truy cập database khác trong cùng cluster, thông thường cần **mở connection tới database đó** hoặc dùng cơ chế riêng như FDW/dblink đã được cấu hình.

### Vì sao kiểm tra current_database()?

Một ứng dụng có thể nhầm:

- Database phát triển với database staging.
- Database cùng tên schema nhưng khác dữ liệu.
- Connection string đã bị cấu hình sang database mặc định khác.
- Connection pool dùng một datasource không đúng môi trường.

Kiểm tra:

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    pg_backend_pid();
```

Giúp định vị **database, role và backend của đúng connection** trước khi điều tra sâu hơn.

## 8. current_schema() và current_schemas()

Một database PostgreSQL có thể có nhiều schema như `public`, `lesson_sys` hoặc các schema nghiệp vụ khác.

Hai hàm quan trọng:

```sql
SELECT
    current_schema() AS current_schema_name,
    current_schemas(false) AS explicit_search_schemas,
    current_schemas(true) AS effective_search_schemas;
```

Ý nghĩa:

- `current_schema()` trả schema hiện hành theo quy tắc đường tìm kiếm hợp lệ; nó cũng liên quan schema mặc định của các câu tạo đối tượng không ghi schema.
- `current_schemas(false)` trả danh sách schema **hợp lệ** trong đường tìm kiếm từ cấu hình.
- `current_schemas(true)` có thể bao gồm cả những schema được tìm kiếm **ngầm định**, như `pg_catalog` và schema tạm hiện hành khi phù hợp.

Kết quả phụ thuộc cấu hình phiên, quyền/schema đang tồn tại và sự hiện diện của đối tượng tạm; không nên copy một output cụ thể làm chuẩn cho mọi server.

### search_path là cấu hình tên đối tượng, không phải quyền

```sql
SHOW search_path;

SELECT current_setting('search_path') AS configured_path;
```

`search_path` quyết định các schema mà PostgreSQL tra cứu khi một tên đối tượng **không có tiền tố schema** được sử dụng.

Ví dụ trong lab:

```sql
SET search_path TO lesson_sys, public;

SELECT staff_id, full_name
FROM staff
ORDER BY staff_id;

RESET search_path;
```

Với `search_path` như trên, tên ngắn `staff` có thể được phân giải đến `lesson_sys.staff` nếu role có quyền truy cập thích hợp.

Nhưng:

**`SET search_path TO lesson_sys` không cấp quyền `USAGE` trên schema và không cấp `SELECT` trên bảng.** Cấu hình tên và quyền truy cập là hai cơ chế riêng.

### Phân biệt tên schema và alias bảng

```sql
SELECT s.full_name
FROM lesson_sys.staff AS s;
```

- `lesson_sys`: schema xác định đối tượng thật.
- `staff`: tên bảng thật trong schema.
- `s`: alias của nguồn trong query block.
- `s.full_name`: cột `full_name` của nguồn `s`.

Không nhầm `s` với schema mới và không dùng tên bảng gốc thay alias trong cùng query block sau khi đã đặt alias.

## 9. pg_catalog, pg_temp và rủi ro từ search_path

Hai schema đặc biệt cần biết:

- **`pg_catalog`** chứa các đối tượng hệ thống, nhiều hàm tích hợp và catalog.
- **`pg_temp`** liên quan schema đối tượng tạm của phiên khi có.

PostgreSQL có quy tắc tìm kiếm các schema đặc biệt; không thể chỉ nhìn chuỗi `SHOW search_path` và giả định đó là toàn bộ thứ tự phân giải hiệu lực cho mọi loại đối tượng.

Ví dụ:

```sql
SELECT
    current_schemas(true) AS effective_schemas,
    current_schemas(false) AS configured_valid_schemas;
```

### Vì sao search_path liên quan bảo mật?

Nếu function `SECURITY DEFINER` gọi đối tượng bằng tên không đủ schema, và một schema không đáng tin có thể cung cấp đối tượng cùng tên, quá trình phân giải có thể bị lợi dụng. Đó là một dạng **search-path hijacking**.

Đối với code có quyền cao:

```sql
CREATE FUNCTION lesson_sys.safe_example(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT pg_catalog.lower(p_text)
$$;
```

Ví dụ cố định đường tìm kiếm và schema-qualify hàm tích hợp. Khi dùng bảng nghiệp vụ trong function, cũng nên ghi rõ `lesson_sys.staff` thay vì phụ thuộc schema có thể bị thay đổi theo session.

**Không tự tin rằng mọi function định nghĩa có đặc quyền đều an toàn chỉ vì nó chạy trong PostgreSQL.** An toàn còn phụ thuộc owner, quyền EXECUTE, search_path, đối tượng được gọi và logic SQL bên trong.

## 10. Kiểm tra sự tồn tại của đối tượng bằng to_regclass()

Trong quá trình debug, đôi khi cần biết một tên bảng có được phân giải thành relation không.

```sql
SELECT
    to_regclass('lesson_sys.staff') AS known_table,
    to_regclass('lesson_sys.nonexistent_table') AS missing_table;
```

Kết quả kỳ vọng:

- `known_table`: một giá trị kiểu `regclass` biểu diễn relation tương ứng.
- `missing_table`: SQL `NULL` nếu không có đối tượng theo tên đó.

Điểm hữu ích: `to_regclass(text)` có thể trả `NULL` thay vì lỗi cho tên relation không tồn tại.

### Khác ép kiểu trực tiếp sang regclass

```sql
SELECT 'lesson_sys.staff'::regclass AS table_object;
```

Nếu relation tồn tại, phép ép kiểu thành công; nếu không, cast `::regclass` có thể phát sinh lỗi. Chọn `to_regclass()` khi muốn kiểm tra sự tồn tại một cách có kiểm soát.

**Cảnh báo:** Relation tồn tại **không đồng nghĩa role có quyền đọc dữ liệu**. `to_regclass` không thay thế `has_table_privilege`, `has_schema_privilege` hoặc việc xét RLS.

### Tham số tên cần được kiểm soát

Nếu tên relation được tạo động từ input, phải phân biệt text tên đối tượng với identifier SQL và dùng cách quote/kiểm tra phù hợp. Đừng nối tên bảng tùy ý từ HTTP request để xây SQL thực thi.

## 11. pg_backend_pid(): định danh backend hiện tại

`pg_backend_pid()` trả **process ID của backend PostgreSQL** đang phục vụ session hiện tại:

```sql
SELECT pg_backend_pid() AS backend_pid;
```

Hữu ích khi:

- Đối chiếu thông tin giữa log server và phiên ứng dụng.
- Tìm hàng tương ứng trong `pg_stat_activity`.
- Kiểm tra connection pool có đang dùng cùng backend cho hai lần mượn liên tiếp hay không.
- Chẩn đoán transaction, lock wait hoặc timeout theo đúng connection.

### Backend PID không phải user ID hoặc request ID

Một backend có thể phục vụ nhiều request tuần tự khi connection được tái sử dụng. PID cũng có thể được hệ điều hành tái sử dụng sau khi process kết thúc. Vì vậy, **PID không phải định danh duy nhất toàn lịch sử cho một request**.

Trong log/trace, nên kết hợp backend PID với application name, timestamp, request/correlation ID và những trường cần thiết theo chính sách logging.

## 12. Thông tin địa chỉ kết nối: inet_client_* và inet_server_*

Một số hàm hệ thống giúp quan sát đầu mút network của phiên:

```sql
SELECT
    inet_client_addr() AS client_ip,
    inet_client_port() AS client_port,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port;
```

| Hàm | Ý nghĩa |
|---|---|
| `inet_client_addr()` | Địa chỉ IP phía client theo kết nối backend nhìn thấy. |
| `inet_client_port()` | Cổng phía client khi phù hợp. |
| `inet_server_addr()` | Địa chỉ IP phía server mà kết nối dùng. |
| `inet_server_port()` | Cổng phía server khi phù hợp. |

**Không giả định các giá trị này luôn có IP.** Kết nối qua Unix-domain socket có thể khiến địa chỉ IP trả SQL `NULL` và cổng có cách biểu diễn đặc biệt theo tài liệu PostgreSQL. Trong môi trường container/proxy/PgBouncer, địa chỉ client PostgreSQL nhìn thấy có thể là **proxy**, không phải địa chỉ người dùng HTTP cuối.

### Không dùng IP như danh tính được xác thực

IP có thể thay đổi, được NAT hoặc đi qua load balancer. `inet_client_addr()` hữu ích cho chẩn đoán network nhưng **không tự chứng minh người dùng nghiệp vụ nào đã thực hiện hành động**.

## 13. pg_stat_activity: quan sát đúng backend

View hệ thống `pg_stat_activity` cho biết các backend/session đang hoạt động.

Tìm chính connection hiện tại:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    xact_start,
    state,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE pid = pg_backend_pid();
```

Một số trường:

- `pid`: backend PID.
- `usename`: role của session theo metadata backend.
- `datname`: database đang kết nối.
- `application_name`: nhãn ứng dụng được cấu hình.
- `backend_start`: thời điểm backend bắt đầu.
- `xact_start`: thời điểm bắt đầu transaction hiện tại khi có.
- `state`: trạng thái backend theo hệ thống thống kê.
- `wait_event_type`/`wait_event`: loại và nguyên nhân chờ được báo cáo khi có.

### Quyền nhìn session khác có thể bị hạn chế

Role thông thường không nhất thiết xem được toàn bộ trường nhạy cảm của các session khác. Một số thông tin quan sát/giám sát yêu cầu role hoặc quyền giám sát thích hợp như các quyền thuộc nhóm `pg_monitor`/`pg_read_all_stats` tùy nhu cầu.

**Không cấp superuser chỉ để xem pg_stat_activity.** Hãy chọn quyền giám sát tối thiểu, đúng đối tượng.

### Cẩn thận với query text

`pg_stat_activity` có trường `query` chứa thông tin câu lệnh theo ngữ cảnh và quyền. Văn bản SQL có thể chứa dữ liệu nhạy cảm nếu ứng dụng xây literal trực tiếp. Khi xuất báo cáo/log debug, cần che/mask nội dung phù hợp.

## 14. version(), server_version và server_version_num

Muốn xác định phiên bản PostgreSQL:

```sql
SELECT version() AS build_description;

SHOW server_version;

SELECT current_setting('server_version') AS server_version;

SELECT
    current_setting('server_version_num')::integer
        AS server_version_number;
```

Khác biệt:

- `version()` có thể chứa mô tả phiên bản và thông tin build/platform.
- `server_version` là chuỗi phiên bản server.
- `server_version_num` là thông tin phiên bản dạng số dễ dùng trong điều kiện logic hơn việc tự phân tích chuỗi.

Trong hệ thống thực, không nên dùng `version()` như một “health check” duy nhất: nó cho biết server trả lời truy vấn, **không chứng minh database sẵn sàng cho mọi thao tác ghi, replication ổn định hoặc ứng dụng có đầy đủ quyền**.

### Kiểm tra version trước khi dùng tính năng mới

Một tính năng hoặc biến thể hàm có thể không tồn tại trên bản PostgreSQL cũ. Thay vì đoán theo phiên bản máy local, hãy hỏi **đúng server ứng dụng đang kết nối**.

Ví dụ khi kiểm tra migration:

```sql
SELECT
    current_database(),
    current_setting('server_version_num')::integer AS version_num;
```

Không cố định số version của mọi server trong tài liệu triển khai nếu môi trường dev, staging và production có thể khác nhau.

## 15. current_setting(): đọc tham số cấu hình runtime

`current_setting(name)` đọc giá trị hiện hành của một tham số cấu hình PostgreSQL.

```sql
SELECT
    current_setting('TimeZone') AS session_timezone,
    current_setting('search_path') AS schema_search_path,
    current_setting('application_name') AS application_name,
    current_setting('statement_timeout') AS statement_timeout;
```

Các kết quả có **kiểu text**. Nếu cần dùng làm số, chỉ cast khi biết chính xác format/đơn vị của setting đang đọc.

### SHOW tương đương thao tác đọc người dùng hay dùng

```sql
SHOW TimeZone;
SHOW search_path;
SHOW application_name;
SHOW statement_timeout;
```

`SHOW` thuận tiện khi kiểm tra một giá trị. `current_setting()` thuận tiện khi muốn **đưa nhiều setting vào một SELECT**, kết hợp chúng với thông tin role/database hoặc lấy giá trị trong biểu thức.

### Tham số không tồn tại

Với tên không tồn tại, một lời gọi thông thường:

```sql
SELECT current_setting('unknown.demo_parameter');
```

có thể báo lỗi vì PostgreSQL không nhận ra setting.

Phiên bản:

```sql
SELECT current_setting(
    'unknown.demo_parameter',
    true
) AS optional_value;
```

Tham số thứ hai `missing_ok = true` cho phép trả SQL `NULL` khi setting không tồn tại theo quy tắc của hàm.

**Không nên coi missing_ok là cơ chế validate tên cấu hình**. Với custom configuration parameter, có thể tồn tại giá trị rỗng hoặc trạng thái đã từng được đặt trong session; kiểm tra `NULL` và chuỗi rỗng theo hợp đồng ứng dụng.

## 16. set_config(), SET và phạm vi hiệu lực

`set_config(name, value, is_local)` thay đổi một tham số runtime phù hợp trong phạm vi cho phép.

Ví dụ:

```sql
SELECT set_config(
    'application_name',
    'demo-report-worker',
    false
) AS effective_application_name;

SELECT current_setting('application_name');
```

Tham số `is_local = false` đặt cấu hình với hiệu lực **cấp session** theo quy tắc transaction của PostgreSQL; đừng nhầm với thay đổi bền vững trong `postgresql.conf`.

Có cú pháp `SET` tương ứng:

```sql
SET application_name = 'demo-report-worker';

SHOW application_name;

RESET application_name;
```

`RESET` đưa setting về giá trị mặc định áp dụng cho session theo hệ thống cấu hình đang có, không có nghĩa “đặt thành chuỗi rỗng” cho mọi setting.

### SET LOCAL chỉ trong transaction

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SELECT current_setting('statement_timeout') AS inside_transaction;

COMMIT;

SELECT current_setting('statement_timeout') AS after_commit;
```

Sau `COMMIT`, thay đổi `SET LOCAL` không còn hiệu lực; setting trở lại mức áp dụng bên ngoài transaction (có thể là giá trị session đã đặt trước đó).

Tương tự:

```sql
BEGIN;

SELECT set_config(
    'application_name',
    'one-request-only',
    true
);

SELECT current_setting('application_name');

ROLLBACK;
```

Tham số `true` đặt cấu hình **trong transaction hiện tại**. Sau rollback, giá trị do transaction đặt không còn duy trì như setting session lâu dài.

### Đừng dùng SET LOCAL bên ngoài transaction theo giả định cũ

Để đạt hiệu lực transaction-local dự đoán được, đặt `SET LOCAL` **bên trong `BEGIN ... COMMIT/ROLLBACK`** rõ ràng. Khi dùng connection pool hoặc JDBC auto-commit, cần đảm bảo mọi câu lệnh liên quan thực sự được chạy trên cùng connection và transaction.

## 17. pg_settings: giá trị, nguồn và ngữ cảnh cấu hình

`pg_catalog.pg_settings` là một view hệ thống hữu ích hơn `SHOW` khi cần hiểu **cấu hình đến từ đâu và có thể thay đổi ở phạm vi nào**.

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE lower(name) IN (
    'timezone',
    'search_path',
    'application_name',
    'statement_timeout',
    'max_connections'
)
ORDER BY name;
```

Một số cột:

| Cột | Ý nghĩa |
|---|---|
| `name` | Tên setting. |
| `setting` | Giá trị hiện hành ở dạng text. |
| `unit` | Đơn vị hoặc dạng giải thích đơn vị nếu có. |
| `context` | Mức ngữ cảnh mà setting được phép thay đổi. |
| `source` | Nguồn đang quyết định giá trị, ví dụ mặc định, file cấu hình, user/session... |
| `pending_restart` | Có thay đổi cấu hình cần restart để được áp dụng hay không theo thông tin server. |

### Không phải setting nào cũng thay đổi được bằng SET

Ví dụ `max_connections` thường là tham số yêu cầu khởi động lại server để áp dụng giá trị mới, không phải thứ bạn có thể tùy ý chạy:

```sql
-- Không phải thao tác hợp lệ cho việc đổi max_connections tại runtime:
-- SET max_connections = 200;
```

Ngược lại, `application_name` và `statement_timeout` hỗ trợ thay đổi ở phạm vi phiên/transaction khi role được phép.

### Nguồn và quyền xem cấu hình

Một số trường trong `pg_settings`, như vị trí file nguồn, có thể bị hạn chế theo quyền. Không cấp đặc quyền quá rộng chỉ để debug một setting; dùng những cột đủ cần và role giám sát phù hợp.

Không nên dựa vào `SHOW search_path` để kết luận giá trị **bền vững sau restart**. Setting hiệu lực có thể đến từ login role, database, session hoặc transaction; phân tích `source` và quy trình cấu hình mới giúp xác định nguyên nhân.

## 18. Custom configuration parameter cho ngữ cảnh request

Ứng dụng có thể dùng một số tên setting tùy chỉnh, ví dụ:

```sql
BEGIN;

SELECT set_config('app.request_id', 'req-123', true);
SELECT set_config('app.actor_id', 'user-456', true);

SELECT
    NULLIF(
        current_setting('app.request_id', true),
        ''
    ) AS request_id,
    NULLIF(
        current_setting('app.actor_id', true),
        ''
    ) AS actor_id;

COMMIT;
```

Điều này hữu ích khi trigger hoặc function cần biết **ngữ cảnh request** trên cùng transaction.

Nhưng có giới hạn:

- `app.actor_id` là **chuỗi do ứng dụng đặt**; PostgreSQL không tự xác thực người dùng web mang ID ấy.
- Một client có quyền chạy SQL trên connection có thể tự đặt custom setting trong nhiều tình huống.
- Với RLS hoặc audit, không dùng custom setting do client tự kiểm soát làm bằng chứng an ninh độc lập.
- Khi connection được tái sử dụng, ưu tiên phạm vi transaction và luôn hoàn tất transaction để state không rò sang request khác.

### Bài học connection pool

```text
Request A
    └── Mượn connection X
          SET app.actor_id = 'user-A'  [session]
          trả connection về pool

Request B
    └── Mượn lại connection X
          có nguy cơ đọc app.actor_id = 'user-A'
          nếu pool/app không reset state
```

Sử dụng `SET LOCAL`/`set_config(..., true)` trong transaction là một cách giảm rủi ro **rò rỉ ngữ cảnh** giữa các request khi ứng dụng quản lý giao dịch đúng.

## 19. Hàm thời gian hệ thống: transaction, statement và clock

PostgreSQL có nhiều biểu thức “thời gian hiện tại” nhưng chúng không cùng ngữ nghĩa:

| Biểu thức | Thời điểm quan sát |
|---|---|
| `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction. |
| `now()` | Tương đương thời điểm bắt đầu transaction. |
| `transaction_timestamp()` | Thời điểm bắt đầu transaction. |
| `statement_timestamp()` | Thời điểm bắt đầu statement hiện hành. |
| `clock_timestamp()` | Đồng hồ tại lúc hàm được gọi, có thể thay đổi trong cùng statement. |
| `CURRENT_DATE` | Ngày hiện hành theo ngữ cảnh thời gian/múi giờ của session. |

Ví dụ:

```sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

SELECT pg_sleep(1);

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

Trong transaction:

- `now()` giữ thời điểm bắt đầu transaction.
- `statement_timestamp()` ở câu SELECT sau có thể khác câu trước.
- `clock_timestamp()` đọc đồng hồ ở thời điểm gọi.

### Không dùng timestamp làm bằng chứng thứ tự commit

Hai transaction có thể bắt đầu theo thứ tự A rồi B nhưng commit theo thứ tự B rồi A. `now()` hay `statement_timestamp()` **không tự bảo đảm thứ tự commit**.

Nếu nghiệp vụ cần số phiên bản tăng theo entity, nên dùng cơ chế khóa/version number/transaction phù hợp, không chỉ dùng timestamp làm khóa tranh chấp.

## 20. Hàm trạng thái server liên quan vận hành

Một số hàm hệ thống hỗ trợ kiểm tra ngữ cảnh server:

```sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_postmaster_start_time() AS postmaster_started_at;
```

Ý nghĩa:

- `pg_is_in_recovery()` cho biết server hiện ở trạng thái recovery theo ngữ nghĩa PostgreSQL; trên standby vật lý có thể trả true.
- `pg_postmaster_start_time()` cho biết thời điểm tiến trình postmaster/server được khởi động theo thông tin server.

### In recovery không phải phép kiểm tra đầy đủ toàn bộ topology

`pg_is_in_recovery() = false` không tự chứng minh ứng dụng có thể ghi mọi bảng hoặc hệ replication khỏe mạnh. Quyền ghi, transaction mode, kết nối tới proxy, đồng bộ và các điều kiện khác vẫn có thể hạn chế thao tác.

Tương tự, `pg_postmaster_start_time()` có ích khi đối chiếu restart nhưng không thay thế monitoring hệ thống, readiness checks và giám sát replication.

## 21. Quyền trong PostgreSQL: object privilege và role membership

PostgreSQL dùng **role** cho danh tính và phân quyền. Những quyền thường gặp:

| Đối tượng | Privilege thường dùng | Ví dụ mục đích |
|---|---|---|
| Database | `CONNECT`, `CREATE`, `TEMPORARY` | Kết nối, tạo schema, tạo object tạm. |
| Schema | `USAGE`, `CREATE` | Phân giải/sử dụng object trong schema, tạo object. |
| Table/view | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`, `MAINTAIN` (theo phiên bản) | Đọc/ghi và thao tác phù hợp với loại object. |
| Column | `SELECT`, `INSERT`, `UPDATE`, `REFERENCES` | Cấp quyền chọn lọc theo cột. |
| Sequence | `USAGE`, `SELECT`, `UPDATE` | Truy cập và điều khiển sequence theo chức năng tương ứng. |
| Function/procedure | `EXECUTE` | Cho phép gọi đối tượng callable phù hợp. |
| Role membership | `MEMBER`, `USAGE` qua `pg_has_role` | Kiểm tra quan hệ vai trò và khả năng thừa hưởng theo ngữ nghĩa role. |

**Không phải mọi object hỗ trợ mọi privilege trong bảng.** Những quyền như `MAINTAIN` có thể phụ thuộc phiên bản PostgreSQL. Luôn xác định phiên bản và object type trước khi dùng một tên privilege cụ thể.

### Hai lớp quyền thường phải có đồng thời

Để gọi:

```sql
SELECT *
FROM lesson_sys.staff;
```

role có thể cần:

1. `USAGE` trên schema `lesson_sys`.
2. `SELECT` trên bảng `lesson_sys.staff` hoặc quyền thích hợp với những cột đang đọc.

**Có SELECT trên bảng nhưng thiếu USAGE schema vẫn có thể không truy cập được bảng bằng cách gọi thông thường.** Ngược lại, chỉ có USAGE schema không tự cấp SELECT bảng.

### Quyền và sở hữu object

Object owner có khả năng quản lý/cấp quyền với object theo những quy tắc riêng, và role superuser có cơ chế bỏ qua nhiều kiểm tra quyền. Các hàm `has_*_privilege` cần được hiểu cùng owner, membership và quyền đặc biệt; không chỉ xem một dòng GRANT đơn lẻ.

## 22. has_database_privilege(): kiểm tra quyền database

Ví dụ kiểm tra quyền của role hiệu lực trên database hiện tại:

```sql
SELECT
    current_database() AS db_name,
    has_database_privilege(
        current_user,
        current_database(),
        'CONNECT'
    ) AS can_connect,
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create_in_database,
    has_database_privilege(
        current_user,
        current_database(),
        'TEMPORARY'
    ) AS can_create_temp_objects;
```

Các hàm kiểm tra quyền trả kiểu boolean khi đối tượng/đối số hợp lệ. Chúng giúp trả lời **“đường cấp quyền cho role này hiện cho phép privilege ở đối tượng ấy không?”**

### CONNECT đã đúng không có nghĩa schema/tables truy cập được

`has_database_privilege(..., 'CONNECT')` chỉ trả lời quyền kết nối database, không kiểm tra:

- Role có `USAGE` trên schema nghiệp vụ hay không.
- Role có `SELECT` trên bảng hay không.
- RLS có lọc dữ liệu hay không.
- Một function có `EXECUTE` hay không.

Ngoài ra, kết nối từ network còn chịu **xác thực và quy tắc truy cập** như `pg_hba.conf`/proxy. Quyền `CONNECT` là một lớp của bức tranh, không mô phỏng toàn bộ thủ tục đăng nhập từ phía client.

## 23. has_schema_privilege(): quyền USAGE và CREATE

Ví dụ:

```sql
SELECT
    has_schema_privilege(
        current_user,
        'lesson_sys',
        'USAGE'
    ) AS can_use_schema,
    has_schema_privilege(
        current_user,
        'lesson_sys',
        'CREATE'
    ) AS can_create_in_schema;
```

Ý nghĩa:

- **`USAGE`**: quyền sử dụng/tra cứu các object trong schema theo quy tắc phân quyền.
- **`CREATE`**: quyền tạo object mới trong schema, nhưng không tự cấp quyền đặc biệt trên mọi object đã có.

### Một tình huống dễ nhầm

Role `report_reader` được cấp:

```sql
GRANT SELECT ON lesson_sys.staff TO report_reader;
```

nhưng **chưa được cấp `USAGE` trên `lesson_sys`**. Truy vấn đọc bảng vẫn có thể thất bại do thiếu quyền schema.

Thông thường cần:

```sql
GRANT USAGE ON SCHEMA lesson_sys TO report_reader;
```

Các lệnh `GRANT` này chỉ là ví dụ triển khai khi role tồn tại và người thực thi có quyền cấp, không phải thao tác được chạy tự động trong bài.

### USAGE không cấp quyền sửa schema

Một role chỉ có `USAGE` không vì vậy được `CREATE TABLE lesson_sys.some_table`. `CREATE` là privilege riêng.

## 24. has_table_privilege(): kiểm tra SELECT, INSERT, UPDATE và DELETE

Ví dụ với bảng lab:

```sql
SELECT
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'SELECT'
    ) AS can_select_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'INSERT'
    ) AS can_insert_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'UPDATE'
    ) AS can_update_staff,
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'DELETE'
    ) AS can_delete_staff;
```

Hàm có những dạng overload nhận user, table và privilege, hoặc bỏ user để kiểm tra role hiệu lực theo quy tắc của hàm.

Ví dụ ngắn:

```sql
SELECT
    has_table_privilege(
        'lesson_sys.staff',
        'SELECT'
    ) AS current_role_can_select;
```

### Tên bảng phải tồn tại

Đối với các hàm kiểm tra privilege nhận tên bảng bằng text, tên object không hợp lệ có thể gây lỗi phân giải relation. Đừng đồng nhất “không tồn tại” với “tồn tại nhưng không có quyền”.

Ví dụ kiểm tra an toàn hơn về việc relation có tồn tại:

```sql
SELECT
    to_regclass('lesson_sys.staff') IS NOT NULL
        AS staff_relation_exists;
```

Sau khi xác nhận object tồn tại, dùng `has_table_privilege` kiểm tra quyền. Trong truy vấn debug động, cần xem xét cả quyền/schema và thay đổi schema đồng thời; hai bước kiểm tra không phải giao thức giao dịch chống race.

### Privilege được cấp có thể theo nhiều đường

`has_table_privilege` xem xét cơ chế đặc quyền của PostgreSQL, không chỉ những GRANT trực tiếp gắn vào role. Quyền có thể đến từ membership/inheritance, `PUBLIC` hoặc owner/superuser theo ngữ nghĩa áp dụng.

## 25. has_column_privilege(): phân quyền đến từng cột

Một bảng có thể chứa trường công khai và trường nhạy cảm:

```text
lesson_sys.staff
├── staff_id
├── full_name
├── email
├── salary        <-- dữ liệu nhạy cảm
└── department
```

PostgreSQL hỗ trợ `GRANT SELECT(column_name)` để cấp quyền đọc những cột cụ thể.

Ví dụ kiểm tra:

```sql
SELECT
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS can_read_full_name,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS can_read_salary;
```

**has_column_privilege có thể trả true khi role có quyền ở cấp bảng hoặc quyền riêng cột.** Không nên chỉ đọc bảng GRANT cột rồi kết luận đủ về quyền hiệu lực nếu role còn được cấp `SELECT ON TABLE` qua đường khác.

### Ví dụ cấp quyền hạn chế theo cột

**Chỉ dành cho người quản trị có quyền trong database lab:**

```sql
CREATE ROLE lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA lesson_sys TO lab_reader;

GRANT SELECT (staff_id, full_name, department)
ON lesson_sys.staff TO lab_reader;
```

Khi đó, nếu role không có những grant khác:

```sql
SELECT
    has_table_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'SELECT'
    ) AS full_table_select,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS name_select,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS salary_select;
```

Kỳ vọng về ý nghĩa là:

- `full_table_select`: **false** nếu không có quyền SELECT toàn bảng theo đường khác.
- `name_select`: **true**.
- `salary_select`: **false**.

### Khi áp dụng thực tế

Đừng dùng `SELECT *` đối với role chỉ có quyền vài cột. Chọn:

```sql
SELECT staff_id, full_name, department
FROM lesson_sys.staff;
```

Điều này vừa tương thích phân quyền cột vừa giúp API không vô tình trả dữ liệu nhạy cảm.

**Lưu ý:** Khả năng dùng cột trong `WHERE`, `ORDER BY` hoặc biểu thức khác cũng có thể chịu quy tắc đặc quyền SELECT cột; không phải chỉ các cột hiện lên trong output mới quan trọng.

## 26. has_sequence_privilege(): quyền trên sequence

Sequence là object riêng trong PostgreSQL. Bảng dùng `serial` hoặc một sequence được khai báo thủ công có thể cần quyền sequence thích hợp khi ứng dụng gọi `nextval()`/`currval()`/`setval()` theo ngữ nghĩa từng hàm.

Ví dụ lấy tên sequence gắn với cột identity ở bảng lab:

```sql
SELECT
    pg_get_serial_sequence(
        'lesson_sys.staff',
        'staff_id'
    ) AS associated_sequence;
```

Hàm `pg_get_serial_sequence` tìm sequence liên kết với cột theo cơ chế PostgreSQL, bao gồm các trường hợp phù hợp như serial/identity.

Kiểm tra quyền:

```sql
SELECT
    has_sequence_privilege(
        current_user,
        pg_get_serial_sequence(
            'lesson_sys.staff',
            'staff_id'
        ),
        'USAGE'
    ) AS can_use_associated_sequence;
```

### Phân biệt SERIAL và IDENTITY

`GENERATED ... AS IDENTITY` và `serial` có cơ chế cấp phát giá trị liên quan sequence nhưng **quy tắc quyền khi INSERT có khác biệt**. Không kết luận rằng mọi lệnh INSERT vào bảng có identity column đều bắt buộc role phải có `USAGE` trên sequence như những trường hợp dùng serial/`nextval()` trực tiếp.

Khi chẩn đoán lỗi insert do sequence:

1. Xem schema cột là `IDENTITY` hay `serial`/default `nextval(...)`.
2. Xem quyền `INSERT` trên bảng/cột.
3. Xem function/sequence thực được gọi trong biểu thức default.
4. Kiểm tra `has_sequence_privilege` đối với sequence liên quan.
5. Dùng role thực của ứng dụng để tái hiện, không dựa vào quyền của owner/superuser.

## 27. has_function_privilege(): quyền EXECUTE

Đối với function đã tạo trong lab:

```sql
SELECT
    has_function_privilege(
        current_user,
        'lesson_sys.normalize_label(text)',
        'EXECUTE'
    ) AS can_call_normalize_label;
```

Chú ý tên function có **chữ ký kiểu đối số**:

```text
lesson_sys.normalize_label(text)
```

PostgreSQL hỗ trợ **overloading**: hai function có cùng tên nhưng khác kiểu đối số là những object khác nhau. Để kiểm tra đúng function, cần phân giải chính xác signature.

### Hàm không có đối số

Với function:

```sql
SELECT
    has_function_privilege(
        current_user,
        'lesson_sys.who_is_executing()',
        'EXECUTE'
    ) AS can_call_context_function;
```

### PUBLIC có thể có EXECUTE mặc định

Ở PostgreSQL, function mới tạo thường có quyền `EXECUTE` mặc định cho `PUBLIC`, trừ khi cấu hình default privileges hoặc thay đổi quyền tác động. Vì vậy, chỉ chạy:

```sql
GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

không có nghĩa trước đó function chắc chắn bị chặn với mọi role khác.

Khi function có đặc quyền hoặc đọc dữ liệu nhạy cảm, cần rà soát quyền `PUBLIC` và có thể thu hồi:

```sql
-- Chỉ áp dụng trong lab hoặc migration đã được phê duyệt:
REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

**EXECUTE không có nghĩa user có mọi quyền trực tiếp trên các bảng mà function đọc.** Với `SECURITY INVOKER`, quyền truy cập object bên trong vẫn được kiểm tra theo ngữ nghĩa caller; với `SECURITY DEFINER`, function chạy theo quyền owner trong phạm vi thực thi.

## 28. pg_has_role(): quyền thành viên và thừa hưởng role

Role PostgreSQL có thể được **grant cho role khác**, tạo một đồ thị membership.

```text
report_viewer
    ▲
    │ GRANT report_viewer TO app_analyst
    │
app_analyst
```

Một số kiểm tra:

```sql
SELECT
    pg_has_role(
        current_user,
        'pg_monitor',
        'MEMBER'
    ) AS member_of_pg_monitor,
    pg_has_role(
        current_user,
        'pg_monitor',
        'USAGE'
    ) AS inherits_pg_monitor_privileges;
```

Ở đây `pg_monitor` là role giám sát có sẵn trong các PostgreSQL hiện đại. Hai biểu thức minh họa sự khác biệt:

- **`MEMBER`**: kiểm tra quan hệ membership phù hợp theo ngữ nghĩa PostgreSQL.
- **`USAGE`**: kiểm tra quyền của role có sẵn cho người gọi theo cơ chế thừa hưởng quyền (không chỉ quan hệ thành viên thuần túy).

Kết quả tùy grant, membership options, vai trò và phiên bản PostgreSQL. **Một role là thành viên không nhất thiết được sử dụng toàn bộ đặc quyền theo cách người viết mong muốn**, đặc biệt khi có inheritance/SET ROLE options.

### Role không tồn tại

`pg_has_role(..., 'some_role', ...)` có thể lỗi khi tên role không tồn tại; không nên mặc định mọi role name từ input có thể dùng như một kiểm tra boolean an toàn.

Để xem role đang có:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname IN ('pg_monitor', 'lab_reader')
ORDER BY rolname;
```

`pg_roles` hiển thị metadata role trong phạm vi hệ thống cung cấp; thông tin đó **không đồng nghĩa bạn có quyền SET ROLE hoặc cấp role**.

## 29. Tạo role và GRANT/REVOKE trong lab

Nếu đã được cấp quyền quản trị role trong database lab, có thể minh họa nguyên tắc đặc quyền tối thiểu như sau.

### 29.1. Tạo role chỉ dùng cho ví dụ

```sql
-- Chỉ thực hiện khi lab_reader chưa tồn tại:
CREATE ROLE lab_reader NOLOGIN;
```

`NOLOGIN` nghĩa là role này không dùng để đăng nhập trực tiếp trong cấu hình ví dụ; nó vẫn có thể được dùng làm role nhóm quyền.

### 29.2. Cấp USAGE schema và SELECT cột

```sql
GRANT USAGE ON SCHEMA lesson_sys TO lab_reader;

GRANT SELECT (staff_id, full_name, department)
ON lesson_sys.staff TO lab_reader;
```

### 29.3. Cấp quyền EXECUTE một function

```sql
REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
TO lab_reader;
```

### 29.4. Kiểm tra quyền theo tên role

```sql
SELECT
    has_schema_privilege(
        'lab_reader',
        'lesson_sys',
        'USAGE'
    ) AS schema_usage,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS read_name,
    has_column_privilege(
        'lab_reader',
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS read_salary,
    has_function_privilege(
        'lab_reader',
        'lesson_sys.normalize_label(text)',
        'EXECUTE'
    ) AS execute_normalize_label;
```

### 29.5. Thu hồi khi không còn cần

```sql
REVOKE SELECT (staff_id, full_name, department)
ON lesson_sys.staff FROM lab_reader;

REVOKE EXECUTE
ON FUNCTION lesson_sys.normalize_label(text)
FROM lab_reader;
```

**Quan trọng:** `REVOKE` một đường cấp quyền **không bảo đảm quyền thực tế biến mất**, nếu role vẫn có quyền từ membership, `PUBLIC`, cấp quyền bảng hoặc đường khác. Kiểm tra lại `has_*_privilege` sau khi thay đổi.

### Không tự chạy SET ROLE nếu chưa có membership

`CREATE ROLE lab_reader NOLOGIN` không tự cấp quyền `SET ROLE lab_reader` cho mọi người. Để test bằng `SET ROLE`, cần một tài khoản được phép chuyển role theo chính sách grant hiện hành. Một người có quyền phù hợp có thể cấp membership, nhưng không nên thực hiện trên role production chỉ để thử bài học.

## 30. Phân biệt kiểm tra quyền của role khác và kiểm tra quyền phiên

Hai câu sau trả lời hai câu hỏi khác nhau:

```sql
SELECT has_table_privilege(
    current_user,
    'lesson_sys.staff',
    'SELECT'
) AS my_effective_select;

SELECT has_table_privilege(
    'lab_reader',
    'lesson_sys.staff',
    'SELECT'
) AS lab_reader_select;
```

- Câu thứ nhất hỏi về **role hiệu lực của connection hiện tại**.
- Câu thứ hai hỏi về **role có tên `lab_reader`**, không có nghĩa connection hiện tại đã trở thành role ấy.

Chỉ vì một function kiểm tra quyền của role X trả true không có nghĩa **caller hiện tại được phép giả làm role X** hoặc truy cập dữ liệu với tư cách X.

### Có nên dùng has_*_privilege làm cơ chế kiểm soát duy nhất trong app?

Không. Các hàm kiểm tra quyền hữu ích để **hiển thị trạng thái và chẩn đoán**, nhưng thao tác SQL thật vẫn phải được PostgreSQL kiểm tra quyền tại thời điểm thực hiện.

Giữa một lần kiểm tra và thao tác sau đó, quyền/object/role có thể thay đổi, và những lớp khác như RLS vẫn có thể tác động. Đây là dạng **time-of-check/time-of-use** nếu ứng dụng cố dựa vào kiểm tra trước như bảo đảm vĩnh viễn.

## 31. Quyền bảng khác row-level security

PostgreSQL hỗ trợ **row-level security (RLS)** để giới hạn những hàng có thể đọc hoặc thay đổi theo policy.

Ví dụ ý tưởng:

```text
Role có SELECT trên bảng staff
               │
               ▼
       Kiểm tra object privilege
               │
               ▼
          RLS policy
               │
               ▼
     Chỉ các hàng được phép
```

Khi `has_table_privilege(..., 'SELECT')` trả true, điều đó **không bảo đảm mọi hàng đều được trả**. Một policy RLS có thể khiến query trả 0 hàng hoặc chỉ một tập con.

### Kiểm tra RLS có hiệu lực

PostgreSQL cung cấp `row_security_active()` để kiểm tra trạng thái áp dụng RLS với một bảng theo ngữ cảnh hiện tại:

```sql
SELECT row_security_active(
    'lesson_sys.staff'::regclass
) AS rls_active_for_current_context;
```

Nếu bảng chưa bật RLS, kết quả thông thường là false. Khi đã bật RLS, việc có áp dụng policy cho connection hiện tại còn phụ thuộc owner, quyền bypass, cấu hình và các quy tắc PostgreSQL.

**Không suy ra chỉ từ `row_security_active` rằng role có hoặc không có SELECT.** Nó kiểm tra một khía cạnh bổ sung, không thay thế object privileges.

### Vì sao role có SELECT nhưng không thấy dữ liệu?

Những nguyên nhân cần kiểm tra:

1. RLS có bật và policy có giới hạn hàng không?
2. Session đang ở role nào (`current_user`)?
3. Tham số ngữ cảnh tenant có giá trị đúng không?
4. Có filter ở `WHERE`, view hoặc application không?
5. Có đang kết nối đúng database/schema không?

Ở hệ thống multi-tenant, không nên dùng một tham số `app.tenant_id` do client tùy ý đặt làm căn cứ bảo mật duy nhất.

## 32. Quyền schema, quyền cột và quyền role có thể kết hợp

Giả sử role `lab_reader` được cấp:

```text
USAGE ON SCHEMA lesson_sys
SELECT (staff_id, full_name) ON TABLE lesson_sys.staff
EXECUTE ON FUNCTION lesson_sys.normalize_label(text)
```

Một truy vấn được kỳ vọng có thể phù hợp:

```sql
SELECT staff_id, full_name
FROM lesson_sys.staff
ORDER BY staff_id;
```

Nhưng truy vấn:

```sql
SELECT *
FROM lesson_sys.staff;
```

cần đọc **tất cả các cột**, bao gồm `salary` và `email`. Nếu role không có quyền đọc những cột đó theo đường nào khác, truy vấn `SELECT *` không phù hợp.

### Tại sao lỗi có thể xuất hiện dù has_column_privilege cho name là true?

Vì trong truy vấn thực có thể còn:

- Cột khác chưa được cấp quyền.
- Schema hoặc function được gọi trong biểu thức.
- View/function với ngữ nghĩa quyền riêng.
- RLS hoặc cấu hình phiên.

**Phân quyền là hợp thành từ nhiều điều kiện**, không phải chỉ một boolean trả về từ một hàm.

## 33. Các view catalog hỗ trợ kiểm tra quyền

Ngoài các hàm `has_*_privilege`, có thể quan sát catalog và information schema.

### pg_roles

```sql
SELECT
    rolname,
    rolcanlogin,
    rolcreatedb,
    rolcreaterole,
    rolinherit,
    rolbypassrls
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

Đây là metadata role, không phải danh sách toàn bộ quyền trên mọi object.

### information_schema.table_privileges

```sql
SELECT
    grantor,
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'lesson_sys'
ORDER BY table_name, grantee, privilege_type;
```

Information schema giúp xem nhiều **GRANT khai báo được biểu diễn** trong phạm vi role và view; danh sách hàng nhìn thấy có thể phụ thuộc quyền và ngữ nghĩa của view.

**Không xem mọi view liệt kê grant là một cách tự động tái dựng toàn bộ quyền hiệu lực.** Quyền inherited, owner, `PUBLIC`, role membership và RLS cần được xem xét riêng.

### information_schema.column_privileges

```sql
SELECT
    grantee,
    table_schema,
    table_name,
    column_name,
    privilege_type
FROM information_schema.column_privileges
WHERE table_schema = 'lesson_sys'
  AND table_name = 'staff'
ORDER BY grantee, column_name;
```

Hữu ích khi điều tra một ứng dụng chỉ được đọc vài cột, nhưng một lần nữa cần kiểm tra **đặc quyền hiệu lực** bằng các hàm có liên quan và query thực.

## 34. Phân quyền trong view và function

Khi truy vấn qua **view**, quyền của view, bảng gốc và những tùy chọn bảo mật có thể tác động tới kết quả. Với những PostgreSQL hỗ trợ `security_invoker` cho view, semantics kiểm tra quyền bảng gốc có thể khác view dùng ngữ nghĩa owner.

Tương tự, function:

- `SECURITY INVOKER` thường cần quyền phù hợp của caller trên object truy cập bên trong.
- `SECURITY DEFINER` chạy phần code function với quyền owner, nhưng người gọi vẫn cần quyền EXECUTE và các điều kiện khác.

Do đó, một câu:

```sql
SELECT has_table_privilege(
    current_user,
    'lesson_sys.staff',
    'SELECT'
);
```

không tự trả lời “mọi view hoặc function đọc staff sẽ thành công hay không”. Cần kiểm tra **đường truy cập thực**.

### Vì sao không dùng view/function như lối vòng qua mọi chính sách?

View và function có thể là thành phần hợp pháp để cung cấp API database hạn chế, nhưng chúng phải được **thiết kế, review và phân quyền** như bề mặt bảo mật. Một `SECURITY DEFINER` function trả toàn bộ salary có thể làm lộ dữ liệu nếu `EXECUTE` được cấp quá rộng.

## 35. Thông tin phiên trong ứng dụng Java/JDBC

Một service Java thường lấy connection từ datasource/pool. Có thể kiểm tra ngữ cảnh:

```java
String sql = """
    SELECT
        current_database() AS database_name,
        session_user AS login_role,
        current_user AS effective_role,
        current_schema() AS schema_name,
        pg_backend_pid() AS backend_pid,
        current_setting('application_name') AS app_name
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        String database = rs.getString("database_name");
        String loginRole = rs.getString("login_role");
        String effectiveRole = rs.getString("effective_role");
        String schema = rs.getString("schema_name");
        int backendPid = rs.getInt("backend_pid");
        String appName = rs.getString("app_name");

        // Ghi chẩn đoán ở mức cần thiết, tránh lộ thông tin nhạy cảm.
    }
}
```

Đoạn code sử dụng Java text block và giả định `connection` đã được tạo, có imports và xử lý `SQLException`.

### Vì sao phải kiểm tra trên đúng connection?

Nếu bạn chạy `SELECT current_user` trong `psql` bằng tài khoản admin nhưng ứng dụng dùng `app_service`, kết quả kiểm tra **không đại diện** cho quyền thật của ứng dụng.

Với pool:

```text
psql admin connection ──> current_user = db_admin
Spring app connection  ──> current_user = app_service
Background worker      ──> current_user = report_worker
```

Khi điều tra lỗi, hãy lấy thông tin từ **connection đang gây lỗi**, không chỉ từ một client khác kết nối cùng database.

### Không log tất cả thông tin ở production

Tùy chính sách, tên role/database và application name có thể hữu ích cho observability. Nhưng không nên tự động đưa query text, token, mật khẩu, dữ liệu cá nhân hoặc toàn bộ thông tin network vào log công khai.

## 36. Đặt ngữ cảnh transaction bằng JDBC

Giả sử một request cần truyền `request_id` vào trigger và giới hạn statement timeout trong transaction.

```java
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT set_config('app.request_id', ?, true)")) {
        ps.setString(1, "req-123");
        ps.execute();
    }

    try (Statement st = connection.createStatement()) {
        st.execute("SET LOCAL statement_timeout = '3s'");
    }

    // Các câu INSERT/UPDATE liên quan dùng chính connection này.
    // ...

    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
```

Ví dụ tập trung vào nguyên tắc **cùng một connection, cùng một transaction**. Trong ứng dụng thực tế, quản lý lỗi trong `finally` và cơ chế rollback/đóng connection cần phù hợp với transaction manager và pool đang dùng. Đừng tự điều khiển auto-commit bên trong một framework transaction như Spring `@Transactional` nếu điều đó mâu thuẫn cơ chế quản lý kết nối của framework.

### SET LOCAL không phải shared global variable

Thay đổi trong transaction của connection A không tự thay đổi session B. Điều này hữu ích khi một server xử lý nhiều request đồng thời.

### Không dựa vào RESET ROLE tự động của mọi pool

Các pool có những cơ chế reset state khác nhau. Nếu ứng dụng chủ động chạy `SET ROLE` hoặc thay đổi `search_path` cấp session, phải xác định **chính xác pool/driver nào đảm bảo reset điều gì**; không tự giả định việc `close()` của JDBC object luôn xóa mọi trạng thái backend.

## 37. Quy trình chẩn đoán “permission denied”

Giả sử API gặp lỗi:

```text
ERROR: permission denied for table staff
SQLSTATE: 42501
```

Một quy trình kiểm tra có hệ thống:

### Bước 1 — Xác định ngữ cảnh connection

```sql
SELECT
    current_database(),
    session_user,
    current_user,
    current_role,
    pg_backend_pid();
```

### Bước 2 — Xác định schema và relation

```sql
SHOW search_path;

SELECT current_schemas(true);

SELECT to_regclass('lesson_sys.staff') AS resolved_table;
```

### Bước 3 — Kiểm tra quyền schema

```sql
SELECT has_schema_privilege(
    current_user,
    'lesson_sys',
    'USAGE'
) AS schema_usage;
```

### Bước 4 — Kiểm tra quyền bảng/cột

```sql
SELECT
    has_table_privilege(
        current_user,
        'lesson_sys.staff',
        'SELECT'
    ) AS select_table,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'full_name',
        'SELECT'
    ) AS select_name,
    has_column_privilege(
        current_user,
        'lesson_sys.staff',
        'salary',
        'SELECT'
    ) AS select_salary;
```

### Bước 5 — Xem có RLS hay không

```sql
SELECT row_security_active(
    'lesson_sys.staff'::regclass
) AS rls_applies;
```

### Bước 6 — Kiểm tra đường GRANT và thử query đúng vai trò

Nếu người quản trị quyết định cấp quyền, hãy cấp **đúng quyền tối thiểu** và kiểm tra lại. Đừng tự động chạy `GRANT SELECT ON ALL TABLES ...` để chữa một lỗi thiếu quyền đọc một cột cụ thể.

### Bước 7 — Xác nhận môi trường ứng dụng

Kiểm tra connection pool có dùng role/session settings khác terminal không, có `SET ROLE`/`SET search_path` không, và lỗi xảy ra ở câu SQL nào. Một query trong function/view có thể cần quyền **khác** với query thẳng vào bảng.

## 38. Khi nào nên dùng hàm kiểm tra quyền thay vì thử truy vấn thật?

| Tình huống | Hàm hữu ích | Vẫn phải kiểm tra thêm |
|---|---|---|
| Hiển thị dashboard quyền database | `has_database_privilege` | Xác thực/network/proxy khi mở kết nối thực. |
| Kiểm tra role được sử dụng schema | `has_schema_privilege` | Quyền bảng/function nằm trong schema. |
| Kiểm tra quyền SELECT ở cấp bảng | `has_table_privilege` | Quyền cột, RLS, view/function. |
| Kiểm tra chỉ một cột | `has_column_privilege` | Những cột khác được tham chiếu trong query. |
| Kiểm tra gọi function | `has_function_privilege` | Quyền thực thi bên trong và bảo mật function. |
| Kiểm tra sequence | `has_sequence_privilege` | Identity/serial/default và thao tác gọi cụ thể. |
| Kiểm tra membership role | `pg_has_role` | Inheritance, quyền SET ROLE và đường cấp quyền thực tế. |

Các hàm này đặc biệt có ích cho **preflight diagnostics** và công cụ quản trị, nhưng không nên đưa ra quyết định an ninh vĩnh viễn chỉ dựa vào một boolean đã tính trước. Database vẫn phải kiểm tra mọi thao tác thật.

### Một câu SQL tổng hợp dùng khi hỗ trợ sự cố

```sql
SELECT
    current_database() AS db_name,
    session_user AS login_role,
    current_user AS effective_role,
    current_schema() AS schema_name,
    current_setting('search_path') AS path,
    pg_backend_pid() AS pid,
    has_schema_privilege(
        current_user, 'lesson_sys', 'USAGE'
    ) AS schema_usage,
    has_table_privilege(
        current_user, 'lesson_sys.staff', 'SELECT'
    ) AS table_select,
    has_column_privilege(
        current_user, 'lesson_sys.staff', 'full_name', 'SELECT'
    ) AS name_select;
```

Kết quả này là một **ảnh chụp ngữ cảnh tại thời điểm truy vấn**, không phải file chứng nhận quyền vĩnh viễn.

## 39. Các lỗi và hiểu nhầm phổ biến

### 39.1. Nhầm session_user với người dùng web

`session_user` thường là tài khoản PostgreSQL, không phải ID người dùng đăng nhập vào HTTP API. Cần phân biệt identity của database và principal nghiệp vụ.

### 39.2. Cho rằng current_user và session_user luôn bằng nhau

`SET ROLE` hoặc `SECURITY DEFINER` có thể tạo ra khác biệt. Khi debug, đọc cả hai.

### 39.3. Dùng current_role như tên role đã đăng nhập

Trong PostgreSQL, `current_role` theo role hiệu lực (tương đương `current_user`), không nên dùng thay `session_user` để khẳng định danh tính lúc bắt đầu session.

### 39.4. SET search_path là được cấp quyền schema

Không. `search_path` phục vụ phân giải tên, `USAGE` và quyền trên object là cơ chế khác.

### 39.5. Có quyền schema USAGE thì đọc được mọi bảng

Không. Mỗi bảng/view/function/sequence có quyền riêng.

### 39.6. has_table_privilege SELECT false nghĩa là không đọc được cột nào

Không nhất thiết. PostgreSQL hỗ trợ quyền `SELECT` theo cột. Kiểm tra thêm `has_column_privilege`.

### 39.7. has_table_privilege SELECT true nghĩa là nhìn thấy mọi hàng

Không. Row-level security có thể giới hạn hàng hoặc query có filter.

### 39.8. Role là MEMBER thì luôn có thể dùng mọi quyền role đó

Không thể suy ra đơn giản như vậy. Membership, inheritance và khả năng `SET ROLE` có thể khác nhau; dùng `pg_has_role` với privilege phù hợp và kiểm tra chính sách role.

### 39.9. Cấp EXECUTE cho một role là function trở thành riêng tư

Chưa chắc. Function có thể đã được cấp `EXECUTE` cho `PUBLIC` theo mặc định. Kiểm tra/thay đổi grant gốc.

### 39.10. SECURITY DEFINER luôn là cách an toàn để vượt lỗi quyền

Không. Function có quyền owner cần thiết kế `search_path`, input, owner và quyền EXECUTE chặt chẽ để tránh lộ dữ liệu/nâng quyền.

### 39.11. is_local=false nghĩa là lưu bền vững sau restart

Không. `set_config(..., false)` đặt hiệu lực session theo quy tắc cấu hình runtime; thay đổi qua session không đồng nghĩa sửa file cấu hình bền vững.

### 39.12. SET LOCAL hoạt động như SET cấp session

Không. `SET LOCAL` có hiệu lực trong transaction hiện hành; dùng đúng transaction boundary.

### 39.13. pg_backend_pid là request ID

Không. Backend có thể được connection pool tái sử dụng cho nhiều request và PID có thể tái sử dụng sau restart.

### 39.14. inet_client_addr luôn là IP của người dùng cuối

Không. PostgreSQL có thể thấy proxy hoặc kết nối qua Unix socket, và IP không tự là danh tính được xác thực.

### 39.15. pg_stat_activity luôn cho thấy toàn bộ SQL của mọi user

Không. Phạm vi thông tin quan sát chịu quyền và cấu hình logging/monitoring.

### 39.16. now() luôn tăng qua từng statement trong một transaction

Không. `now()` gắn với thời điểm transaction bắt đầu; dùng `statement_timestamp()`/`clock_timestamp()` khi cần ngữ nghĩa khác.

### 39.17. Chỉ cần version() là biết ứng dụng kết nối đúng môi trường

Không. Cần kiểm tra thêm database, role, schema, host/datasource và dữ liệu phù hợp.

### 39.18. REVOKE một quyền đảm bảo role mất quyền hiệu lực

Không nếu còn grant từ `PUBLIC`, membership, quyền cấp bảng hoặc đường khác.

### 39.19. Có quyền SELECT là được SELECT * qua mọi view

Không. Cấu trúc view, quyền theo cột, security mode và RLS có thể làm kết quả khác.

### 39.20. Custom setting app.user_id là danh tính bất biến không thể giả

Không. Đó là trạng thái phiên ứng dụng đặt; phải bảo vệ nguồn danh tính và đường gọi SQL.

## 40. Bài tập thực hành

### Bài 1 — Xác định vai trò của phiên

Viết truy vấn trả `session_user`, `current_user` và `current_role`. Giải thích khi nào ba giá trị có thể khác nhau và vì sao `current_user` không tự là người dùng HTTP.

### Bài 2 — Phân biệt database và schema

Viết một truy vấn lấy `current_database()`, `current_schema()`, `current_schemas(true)` và `current_setting('search_path')`. Giải thích cơ chế tên `lesson_sys.staff` khác tên `staff` trong `FROM`.

### Bài 3 — SET ROLE

Trong lab có role đã được grant phù hợp, chạy `SET ROLE lab_reader`, quan sát `current_user`/`session_user` rồi `RESET ROLE`. Ghi lại điều kiện bắt buộc để `SET ROLE` hợp lệ.

### Bài 4 — Chẩn đoán thiếu USAGE schema

Một role có `SELECT ON lesson_sys.staff` nhưng thiếu `USAGE ON SCHEMA lesson_sys`. Viết hai lệnh `has_*_privilege` để chỉ ra hai lớp quyền và giải thích vì sao câu đọc bảng có thể lỗi.

### Bài 5 — Quyền theo cột

Role `lab_reader` chỉ được cấp `SELECT(staff_id, full_name)`. Dùng `has_table_privilege` và `has_column_privilege` để so sánh quyền SELECT toàn bảng, cột `full_name` và cột `salary`. Tại sao `SELECT *` không phù hợp?

### Bài 6 — Kiểm tra quyền database

Dùng `has_database_privilege` kiểm tra `CONNECT`, `CREATE` và `TEMPORARY` trên `current_database()`. Những quyền này có thay thế quyền `SELECT` trên bảng không?

### Bài 7 — Function EXECUTE

Kiểm tra `has_function_privilege('lesson_sys.normalize_label(text)', 'EXECUTE')`. Giải thích vì sao phải chỉ rõ `(text)` và cách `PUBLIC` có thể ảnh hưởng tới kết quả.

### Bài 8 — Sequence và IDENTITY

Dùng `pg_get_serial_sequence('lesson_sys.staff','staff_id')` rồi kiểm tra quyền sequence. Giải thích vì sao không thể áp dụng quy tắc quyền `nextval` của mọi cột serial một cách máy móc cho identity.

### Bài 9 — Role membership

Dùng `pg_has_role(current_user, 'pg_monitor', 'MEMBER')` và biến thể `USAGE`. Tìm hiểu sự khác nhau giữa quan hệ membership và quyền thừa hưởng.

### Bài 10 — Session config và transaction config

Trong một transaction, chạy `SET LOCAL statement_timeout = '2s'`, đọc bằng `current_setting`, commit rồi đọc lại. Tại sao không nên mặc định giá trị 2 giây còn hiệu lực sau commit?

### Bài 11 — Custom GUC

Đặt `app.request_id` bằng `set_config(..., true)` trong transaction. Đọc qua `current_setting(..., true)` và `NULLIF`. Giải thích rủi ro khi đặt `is_local=false` trong connection pool.

### Bài 12 — Phân biệt các mốc giờ

Chạy hai lần `SELECT now(), statement_timestamp(), clock_timestamp()` trong cùng transaction với `pg_sleep(1)` giữa hai lần. Mốc nào giữ nguyên và mốc nào thay đổi?

### Bài 13 — Backend và network

Viết query lấy `pg_backend_pid()`, `inet_client_addr()` và `inet_server_addr()`. Vì sao `client_ip` có thể là SQL NULL hoặc là IP của proxy?

### Bài 14 — pg_stat_activity

Truy vấn `pg_stat_activity` với `WHERE pid = pg_backend_pid()`. Xem `backend_start`, `state` và `application_name`. Nêu sự khác nhau giữa backend PID và request ID.

### Bài 15 — pg_settings

Tìm hàng `pg_settings` cho `statement_timeout` và `max_connections`. Đối chiếu `context`, `source` và `pending_restart`. Tại sao không phải tham số nào cũng có thể `SET` tại runtime?

### Bài 16 — Object tồn tại nhưng không truy cập được

Dùng `to_regclass('lesson_sys.staff')` và `has_table_privilege(...)`. Nêu vì sao kết quả “relation tồn tại” không chứng minh role có SELECT.

### Bài 17 — SECURITY DEFINER

Tạo function `lesson_sys.who_is_executing()` trong lab và gọi từ một role được cấp `EXECUTE` phù hợp. Dự đoán `current_user` bên trong khác `session_user` thế nào. Tại sao không được mặc định dùng `current_user` trong function ấy làm audit actor?

### Bài 18 — RLS

Với một bảng đã bật RLS trong lab riêng, so sánh `has_table_privilege(..., 'SELECT')` và `row_security_active(...)`. Cho biết tại sao có SELECT privilege mà query vẫn có thể không trả hàng.

### Bài 19 — JDBC diagnosis

Viết `PreparedStatement` đọc `current_database()`, `session_user`, `current_user`, `current_schema()` và `pg_backend_pid()`. Giải thích vì sao kết quả từ connection JDBC quan trọng hơn một phiên `psql` admin khác khi điều tra sự cố API.

### Bài 20 — Phân tích phân quyền tối thiểu

Một API chỉ cần đọc `staff_id` và `full_name` để hiển thị danh sách nhân viên. Hãy đề xuất:

1. Quyền database/schema/bảng/cột tối thiểu.
2. Cách kiểm tra bằng `has_schema_privilege` và `has_column_privilege`.
3. Cách tránh `SELECT *`/JSON toàn hàng.
4. Quy trình xác minh bằng role ứng dụng thay vì superuser.

## Kết luận

Hệ thống hàm và biểu thức của PostgreSQL giúp **quan sát đúng ngữ cảnh thực thi**, nhưng mỗi nhóm trả lời một câu hỏi riêng. **`session_user`** phản ánh session authorization; **`current_user`/`current_role`** cho biết role hiệu lực; **`current_database()`**, **`current_schema()`** và **`current_schemas()`** xác định nơi câu SQL đang chạy và cách tên object được phân giải. **`pg_backend_pid()`** và các hàm `inet_*` hỗ trợ chẩn đoán kết nối, còn **`current_setting()`/`set_config()`/`pg_settings`** giúp nhận biết cấu hình hiện hành và phạm vi tác động của nó.

Để kiểm tra quyền, hãy phân biệt **quyền database**, **quyền schema**, **quyền bảng**, **quyền cột**, **quyền sequence**, **quyền EXECUTE function** và **role membership**. Những hàm như `has_table_privilege` và `pg_has_role` giúp kiểm tra đặc quyền hiệu lực, nhưng **không thay thế** việc thực thi câu SQL thật dưới đúng role, không bảo đảm RLS trả toàn bộ hàng và không phải bảo đảm quyền không thể thay đổi sau khi kiểm tra.

Trong ứng dụng Java/JDBC, đặc biệt khi dùng connection pool, hãy ghi nhớ sự khác nhau giữa **session-level state** và **transaction-local state**, dùng `SET LOCAL` hoặc `set_config(..., true)` khi cần đặt ngữ cảnh request theo transaction, và không dùng custom setting chưa xác thực làm căn cứ bảo mật duy nhất. Một quy trình debug tốt bắt đầu bằng cách xác định **đúng database, đúng connection, đúng role hiệu lực, đúng schema, đúng object và đúng privilege**, sau đó mới xét RLS, function/view, cấu hình và logic ứng dụng. Khi nắm chắc những công cụ này, bạn có thể giải thích và xử lý nhiều sự cố PostgreSQL một cách chính xác, có kiểm soát và bảo mật hơn.
