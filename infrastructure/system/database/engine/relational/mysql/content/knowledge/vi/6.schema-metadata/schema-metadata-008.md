# Tra cứu view, routine, trigger, event và người định nghĩa

Trong một hệ thống MySQL đang vận hành, cấu trúc bảng chỉ là một phần của schema. Cơ sở dữ liệu còn có view, stored procedure, stored function, trigger và event. Những đối tượng này có thể chứa logic nghiệp vụ, tự động chạy khi dữ liệu thay đổi hoặc thực thi theo lịch. Khi điều tra một hành vi khó giải thích, chuẩn bị migration, rà soát bảo mật hay bàn giao hệ thống, bạn cần biết đối tượng nào tồn tại, chúng thuộc schema nào, được định nghĩa ra sao và chạy dưới quyền của tài khoản nào.

MySQL cung cấp hai nhóm công cụ chính để tra cứu: các bảng metadata trong `INFORMATION_SCHEMA` và lệnh `SHOW`. `INFORMATION_SCHEMA` phù hợp để lọc, tổng hợp và đối chiếu nhiều đối tượng bằng SQL; `SHOW CREATE` phù hợp để xem câu lệnh định nghĩa đầy đủ của một đối tượng. Cả hai đều chịu ảnh hưởng của quyền người dùng hiện tại, vì vậy kết quả không nhất thiết là danh sách toàn bộ đối tượng có trên máy chủ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Liệt kê view, procedure, function, trigger và event trong một schema hoặc trên máy chủ.
- Tra cứu metadata bằng `INFORMATION_SCHEMA` và kiểm tra định nghĩa bằng `SHOW CREATE`.
- Đọc các thuộc tính `DEFINER`, `SECURITY_TYPE`, `SQL_MODE`, thời điểm và trạng thái của đối tượng.
- Phân biệt quyền của người gọi với quyền của người định nghĩa đối tượng.
- Nhận biết event đã được tạo nhưng chưa chạy vì Event Scheduler đang tắt.
- Xử lý tình huống metadata không hiển thị đầy đủ do thiếu quyền hoặc definer không còn tồn tại.

## 1. Phạm vi tra cứu và quyền nhìn thấy metadata

Các truy vấn trong bài dùng database hiện tại làm phạm vi mặc định. Kiểm tra database đang chọn:

```sql
SELECT DATABASE() AS current_schema;
```

Nếu kết quả là `NULL`, hãy chọn database bằng `USE ten_database;` hoặc thay điều kiện `TABLE_SCHEMA = DATABASE()` bằng tên schema cụ thể. Khi kiểm kê nhiều schema, có thể bỏ điều kiện lọc schema nhưng cần lưu ý quyền truy cập và lượng kết quả.

`INFORMATION_SCHEMA` là schema hệ thống cung cấp metadata dưới dạng các bảng và view. Bạn có thể truy vấn bằng `SELECT`, lọc theo tên schema, sắp xếp hoặc nối với các bảng metadata khác. Không nên truy cập trực tiếp các bảng nội bộ của schema `mysql` để thay thế API metadata công khai; cấu trúc nội bộ có thể thay đổi giữa các phiên bản và không phải giao diện tra cứu ổn định.

Metadata có thể bị giới hạn theo quyền. Người dùng chỉ nhìn thấy những đối tượng mà họ có quyền thích hợp; một số cột chứa phần định nghĩa có thể trả về `NULL` nếu không có quyền xem nội dung. Do đó:

- Không thấy đối tượng trong truy vấn metadata chưa chứng minh đối tượng đó không tồn tại.
- Kết quả kiểm kê phụ thuộc tài khoản đang kết nối. Khi audit toàn schema, cần dùng tài khoản kiểm kê được cấp quyền xem metadata phù hợp.
- Quyền xem định nghĩa khác với quyền thực thi hoặc quyền thay đổi đối tượng.
- Quyền cụ thể có thể khác theo loại đối tượng và phiên bản MySQL. Các quyền thường gặp gồm `SHOW VIEW`, `TRIGGER`, `EVENT`, `CREATE ROUTINE`, `ALTER ROUTINE`, `EXECUTE` và quyền động `SHOW_ROUTINE` ở các phiên bản hỗ trợ.

## 2. Tra cứu view

View là một đối tượng schema lưu định nghĩa truy vấn `SELECT`. Khi ứng dụng đọc view, MySQL xử lý định nghĩa đó như một lớp truy cập dữ liệu. View có thể giúp đóng gói phép nối, chuẩn hóa cách đọc dữ liệu hoặc giới hạn cột được công bố.

### 2.1. Liệt kê view trong schema

`INFORMATION_SCHEMA.VIEWS` cung cấp tên view, schema, người định nghĩa, chế độ bảo mật và định nghĩa truy vấn:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME AS view_name,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Các cột cần chú ý:

| Cột | Ý nghĩa |
|---|---|
| `TABLE_SCHEMA`, `TABLE_NAME` | Schema và tên view |
| `DEFINER` | Tài khoản được ghi nhận là người định nghĩa |
| `SECURITY_TYPE` | `DEFINER` hoặc `INVOKER`, xác định ngữ cảnh quyền khi truy cập view |
| `CHECK_OPTION` | Quy tắc kiểm tra khi ghi qua view có thể cập nhật: `LOCAL`, `CASCADED` hoặc `NONE` |
| `IS_UPDATABLE` | Cho biết view có được MySQL xem là có thể cập nhật hay không |
| `VIEW_DEFINITION` | Phần truy vấn định nghĩa view, có thể không hiển thị nếu thiếu quyền |

Muốn chỉ lấy danh sách tên view, có thể dùng `TABLES`:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'VIEW'
ORDER BY TABLE_NAME;
```

`TABLES` chứa cả bảng thường lẫn view; điều kiện `TABLE_TYPE = 'VIEW'` giúp lọc đúng loại đối tượng.

### 2.2. Xem định nghĩa đầy đủ

Sau khi xác định tên view, dùng `SHOW CREATE VIEW`:

```sql
SHOW CREATE VIEW ten_view;
```

Nếu view nằm trong schema khác database hiện tại, chỉ rõ schema:

```sql
SHOW CREATE VIEW ten_schema.ten_view;
```

Kết quả cho biết câu lệnh tạo view, thường gồm `ALGORITHM`, `DEFINER`, `SQL SECURITY` và truy vấn `SELECT`. Đây là cách thuận tiện để lưu lại định nghĩa khi rà soát migration hoặc so sánh hai môi trường.

Để xem nhanh các view mà tài khoản hiện tại được phép liệt kê:

```sql
SHOW FULL TABLES FROM ten_schema
WHERE Table_type = 'VIEW';
```

`SHOW CREATE VIEW` cần quyền xem định nghĩa view, thường là `SHOW VIEW` cùng quyền phù hợp trên đối tượng. Nếu lệnh báo thiếu quyền, hãy yêu cầu cấp quyền kiểm tra theo chính sách; không suy luận định nghĩa từ tên view.

## 3. Tra cứu stored procedure và stored function

Stored procedure và stored function là các routine được lưu trong schema. Procedure được gọi bằng `CALL`; function trả về một giá trị và có thể được dùng trong biểu thức SQL theo quy tắc của MySQL.

### 3.1. Liệt kê routine

`INFORMATION_SCHEMA.ROUTINES` chứa metadata của cả procedure và function:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS,
    IS_DETERMINISTIC,
    CREATED,
    LAST_ALTERED,
    ROUTINE_DEFINITION
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

Ý nghĩa một số cột:

| Cột | Ý nghĩa |
|---|---|
| `ROUTINE_SCHEMA`, `ROUTINE_NAME` | Schema và tên routine |
| `ROUTINE_TYPE` | `PROCEDURE` hoặc `FUNCTION` |
| `DEFINER` | Tài khoản định nghĩa routine |
| `SECURITY_TYPE` | Ngữ cảnh quyền `DEFINER` hoặc `INVOKER` |
| `SQL_DATA_ACCESS` | Đặc tính khai báo về việc routine có truy cập hoặc sửa dữ liệu SQL hay không |
| `IS_DETERMINISTIC` | Routine có được khai báo là deterministic hay không |
| `CREATED`, `LAST_ALTERED` | Thời điểm tạo và thay đổi gần nhất được metadata ghi nhận |
| `ROUTINE_DEFINITION` | Phần thân routine, có thể bị ẩn do quyền hoặc giới hạn metadata |

`SQL_DATA_ACCESS` thường có các giá trị như `NO SQL`, `CONTAINS SQL`, `READS SQL DATA` và `MODIFIES SQL DATA`. Đây là đặc tính được khai báo khi tạo routine; không nên xem nó như một bộ kiểm tra đầy đủ bảo đảm routine chỉ làm đúng loại thao tác đã khai báo.

### 3.2. Tra cứu tham số routine

`INFORMATION_SCHEMA.PARAMETERS` cho biết tên, thứ tự, mode và kiểu dữ liệu của từng tham số:

```sql
SELECT
    SPECIFIC_SCHEMA,
    SPECIFIC_NAME,
    ROUTINE_TYPE,
    ORDINAL_POSITION,
    PARAMETER_MODE,
    PARAMETER_NAME,
    DATA_TYPE,
    DTD_IDENTIFIER
FROM information_schema.parameters
WHERE SPECIFIC_SCHEMA = DATABASE()
ORDER BY SPECIFIC_NAME, ORDINAL_POSITION;
```

Với function, metadata có thể có một hàng mô tả giá trị trả về ở vị trí `ORDINAL_POSITION = 0`; các tham số đầu vào theo sau. Với procedure, `PARAMETER_MODE` có thể là `IN`, `OUT` hoặc `INOUT`. Đối chiếu thứ tự tham số với câu lệnh gọi để tránh truyền sai kiểu hoặc sai vị trí.

### 3.3. Xem định nghĩa procedure và function

```sql
SHOW CREATE PROCEDURE ten_procedure;
SHOW CREATE FUNCTION ten_function;
```

Có thể chỉ rõ schema nếu routine không thuộc database hiện tại:

```sql
SHOW CREATE PROCEDURE ten_schema.ten_procedure;
SHOW CREATE FUNCTION ten_schema.ten_function;
```

Kết quả hiển thị câu lệnh định nghĩa, tham số, kiểu trả về đối với function, `DEFINER`, `SQL SECURITY`, `SQL_MODE` và các thuộc tính routine. `SQL_MODE` được ghi nhận khi routine được tạo hoặc thay đổi; routine có thể thực thi với mode đã lưu cùng định nghĩa thay vì đơn giản lấy mọi thay đổi session sau này.

Để xem danh sách routine theo kiểu bằng `SHOW`:

```sql
SHOW PROCEDURE STATUS WHERE Db = DATABASE();
SHOW FUNCTION STATUS WHERE Db = DATABASE();
```

Các lệnh `SHOW ... STATUS` hữu ích cho kiểm kê nhanh; khi cần lọc, nối hoặc xuất báo cáo, `INFORMATION_SCHEMA.ROUTINES` linh hoạt hơn. Việc xem phần thân routine có thể cần quyền như `SHOW_ROUTINE` hoặc quyền quản lý/thực thi thích hợp tùy phiên bản.

## 4. Tra cứu trigger

Trigger là routine gắn với một bảng và tự chạy khi có sự kiện `INSERT`, `UPDATE` hoặc `DELETE` xảy ra trên bảng đó. Trigger trong MySQL là trigger cấp hàng: nó chạy cho từng hàng bị tác động, với các tham chiếu `OLD` và `NEW` tùy sự kiện.

### 4.1. Liệt kê trigger

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    EVENT_MANIPULATION,
    ACTION_ORIENTATION,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE,
    CREATED,
    ACTION_STATEMENT
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
```

Các cột quan trọng:

- `EVENT_OBJECT_TABLE`: bảng mà trigger gắn vào.
- `ACTION_TIMING`: thời điểm `BEFORE` hoặc `AFTER`.
- `EVENT_MANIPULATION`: sự kiện `INSERT`, `UPDATE` hoặc `DELETE`.
- `ACTION_ORDER`: thứ tự chạy khi có nhiều trigger cùng thời điểm và sự kiện trên một bảng.
- `DEFINER`: tài khoản định nghĩa trigger.
- `ACTION_STATEMENT`: phần thân trigger.

MySQL cho phép nhiều trigger cùng thời điểm và sự kiện trên một bảng; có thể điều khiển thứ tự bằng `FOLLOWS` hoặc `PRECEDES` khi tạo trigger trong các phiên bản hỗ trợ. Khi điều tra logic cập nhật tự động, phải kiểm tra tất cả trigger trên bảng và thứ tự của chúng, không chỉ trigger đầu tiên tìm thấy.

### 4.2. Xem định nghĩa trigger

```sql
SHOW CREATE TRIGGER ten_trigger;
```

Hoặc chỉ rõ schema:

```sql
SHOW CREATE TRIGGER ten_schema.ten_trigger;
```

Kết quả cung cấp câu lệnh tạo trigger, bảng liên quan, thời điểm, sự kiện, `DEFINER` và `SQL_MODE`. Để liệt kê nhanh trigger:

```sql
SHOW TRIGGERS FROM ten_schema;
```

`SHOW TRIGGERS` và `INFORMATION_SCHEMA.TRIGGERS` chỉ cho thấy metadata mà tài khoản có quyền xem. Người kiểm tra thường cần quyền `TRIGGER` trên bảng hoặc quyền phù hợp theo phiên bản. Nếu thiếu quyền, hãy ghi nhận phạm vi kiểm kê bị hạn chế.

### 4.3. Đánh giá ảnh hưởng trigger

Trigger có thể thay đổi dữ liệu phụ, ghi audit log hoặc xác thực một điều kiện trước khi ghi. Khi rà soát một lệnh `UPDATE` tưởng như chỉ thay đổi một bảng, cần kiểm tra trigger vì trigger có thể làm phát sinh thao tác trên bảng khác, kéo dài thời gian thực thi hoặc gây lỗi cho câu lệnh ban đầu.

Đặc biệt, trigger chạy trong ngữ cảnh giao dịch của câu lệnh kích hoạt nó nếu các bảng liên quan hỗ trợ transaction. Với bảng non-transactional như MyISAM, không thể dựa vào `ROLLBACK` để hoàn tác các thay đổi đã ghi. Khi đánh giá trigger, cần xem cả engine của bảng nguồn và bảng mà trigger ghi vào.

## 5. Tra cứu event và lịch thực thi

Event là đối tượng được MySQL Event Scheduler thực thi theo thời điểm hoặc chu kỳ. Event phù hợp cho tác vụ định kỳ như dọn dữ liệu hết hạn, tổng hợp số liệu hoặc chạy một quy trình bảo trì nhỏ. Event khác trigger ở chỗ nó được kích hoạt theo lịch, không phải bởi thao tác trên một hàng.

### 5.1. Kiểm tra Event Scheduler

Trước tiên, kiểm tra trạng thái scheduler ở cấp máy chủ:

```sql
SELECT @@GLOBAL.event_scheduler AS event_scheduler_status;
```

Giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| `ON` | Event Scheduler đang hoạt động và có thể thực thi event đã bật |
| `OFF` | Scheduler đang tắt; event được lưu nhưng không chạy theo lịch |
| `DISABLED` | Scheduler bị vô hiệu hóa ở cấp khởi động; không thể bật lại chỉ bằng `SET GLOBAL` trong phiên hiện tại |

Một event có `STATUS = ENABLED` không đồng nghĩa nó chắc chắn đã chạy. Scheduler phải ở trạng thái `ON`, thời gian bắt đầu/kết thúc phải phù hợp và definer phải có quyền cần thiết. Cần kiểm tra cả trạng thái của event lẫn trạng thái scheduler.

### 5.2. Liệt kê event

`INFORMATION_SCHEMA.EVENTS` cung cấp thông tin lịch, múi giờ, người định nghĩa, trạng thái và phần thân event:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    EVENT_DEFINITION,
    SQL_MODE
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

Ý nghĩa một số cột:

- `EVENT_TYPE`: event chạy một lần (`ONE TIME`) hay lặp lại (`RECURRING`).
- `EXECUTE_AT`: thời điểm chạy đối với event một lần.
- `INTERVAL_VALUE`, `INTERVAL_FIELD`: khoảng lặp và đơn vị khoảng lặp.
- `STARTS`, `ENDS`: thời điểm bắt đầu và kết thúc của lịch.
- `TIME_ZONE`: múi giờ được dùng để lập lịch và diễn giải thời gian event.
- `STATUS`: event đang `ENABLED`, `DISABLED` hoặc trạng thái liên quan theo phiên bản.
- `LAST_EXECUTED`: thời điểm chạy gần nhất được ghi nhận; `NULL` có thể là event chưa chạy lần nào.
- `DEFINER`: tài khoản mà event dùng để thực thi.

### 5.3. Xem định nghĩa event

```sql
SHOW EVENTS FROM ten_schema;
SHOW CREATE EVENT ten_event;
```

Nếu event thuộc schema khác database hiện tại, chỉ rõ schema theo cú pháp được phiên bản MySQL hỗ trợ:

```sql
SHOW CREATE EVENT ten_schema.ten_event;
```

`SHOW CREATE EVENT` cho biết lịch, định nghĩa câu lệnh, múi giờ, `DEFINER`, `SQL_MODE` và trạng thái. Quyền `EVENT` trên schema/object và quyền xem định nghĩa phù hợp là cần thiết để quản lý hoặc kiểm tra event.

### 5.4. Phân tích event không chạy

Khi event không chạy như mong đợi, kiểm tra theo thứ tự:

1. `@@GLOBAL.event_scheduler` có phải `ON` không?
2. `INFORMATION_SCHEMA.EVENTS.STATUS` có phải `ENABLED` không?
3. `STARTS`, `ENDS`, `EXECUTE_AT` và `TIME_ZONE` có khớp thời điểm dự kiến không?
4. `LAST_EXECUTED` có thay đổi sau thời điểm dự kiến không?
5. Tài khoản `DEFINER` còn tồn tại và có đủ quyền cho câu lệnh event không?
6. Phần thân event có lỗi SQL, phụ thuộc đối tượng bị đổi tên/xóa hoặc gặp lỗi runtime không?

Không nên bật Event Scheduler trên máy chủ dùng chung chỉ để thử một event. Thay đổi scheduler là thay đổi ở cấp máy chủ, cần được thực hiện theo quy trình vận hành và quyền quản trị.

## 6. Hiểu `DEFINER` và `SQL SECURITY`

`DEFINER` là tài khoản MySQL được ghi nhận khi một view, routine, trigger hoặc event được tạo. Tài khoản thường được lưu theo dạng `user_name`@`host_name`. Nó xác định ngữ cảnh quyền của nhiều đối tượng khi thực thi, không phải mật khẩu và cũng không nhất thiết là tài khoản đang kết nối để truy vấn metadata.

`SQL SECURITY` xác định cách MySQL kiểm tra quyền khi truy cập một số đối tượng:

| Đối tượng | Cách bảo mật | Ý nghĩa |
|---|---|---|
| View | `DEFINER` | Truy vấn view dùng quyền của tài khoản định nghĩa |
| View | `INVOKER` | Truy vấn view dùng quyền của tài khoản gọi |
| Procedure/function | `DEFINER` | Routine chạy trong ngữ cảnh quyền của definer |
| Procedure/function | `INVOKER` | Routine chạy trong ngữ cảnh quyền của người gọi |
| Trigger | Luôn theo definer | Trigger thực thi trong ngữ cảnh của definer; không khai báo `SQL SECURITY INVOKER` như view/routine |
| Event | Theo definer | Event chạy theo quyền của tài khoản định nghĩa event |

Đối với view và routine, nếu không khai báo rõ, `SQL SECURITY DEFINER` thường là mặc định. Khi dùng `DEFINER`, người gọi có thể truy cập thông qua đối tượng mà không cần có trực tiếp mọi quyền trên bảng nền, tùy định nghĩa và kiểm tra quyền của MySQL. Đây là cơ chế hữu ích nhưng cần kiểm soát chặt vì đối tượng có thể mở rộng khả năng truy cập dữ liệu.

### 6.1. So sánh tài khoản kết nối và tài khoản thực thi

Trong một session thông thường:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_account;
```

`USER()` cho biết tên người dùng và host mà client dùng khi kết nối. `CURRENT_USER()` cho biết tài khoản MySQL được dùng để kiểm tra quyền trong ngữ cảnh hiện tại. Bên trong một đối tượng chạy với `SQL SECURITY DEFINER`, `CURRENT_USER()` có thể phản ánh tài khoản definer. Vì vậy, khi điều tra quyền, hãy phân biệt tài khoản đăng nhập với tài khoản có hiệu lực trong ngữ cảnh thực thi.

### 6.2. Rủi ro definer không còn tồn tại

Một đối tượng có thể tiếp tục lưu metadata `DEFINER` sau khi tài khoản đó bị xóa hoặc đổi tên. Đối tượng như vậy thường được gọi là orphaned definer. Khi đối tượng cần chạy dưới quyền definer nhưng tài khoản không còn tồn tại hoặc thiếu quyền, truy cập có thể thất bại.

Kiểm kê definer của view:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, DEFINER, SECURITY_TYPE
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY DEFINER, TABLE_NAME;
```

Kiểm kê definer của routine:

```sql
SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SECURITY_TYPE
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY DEFINER, ROUTINE_NAME;
```

Kiểm kê definer của trigger và event:

```sql
SELECT TRIGGER_SCHEMA AS object_schema,
       TRIGGER_NAME AS object_name,
       'TRIGGER' AS object_type,
       DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
UNION ALL
SELECT EVENT_SCHEMA,
       EVENT_NAME,
       'EVENT',
       DEFINER
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY DEFINER, object_type, object_name;
```

Có thể đối chiếu các tài khoản definer với danh sách account trong `mysql.user` nếu tài khoản kiểm kê được cấp quyền đọc thích hợp. Tuy nhiên, không nên cấp quyền đọc rộng bảng hệ thống chỉ để chạy một báo cáo thông thường. DBA có thể thực hiện bước đối chiếu này trong quy trình audit được kiểm soát.

Không tự động thay `DEFINER` bằng tài khoản quản trị chung. Trước khi sửa, cần xác định chủ sở hữu logic của đối tượng, quyền tối thiểu mà đối tượng cần, chế độ `SQL SECURITY`, các bảng được truy cập và tác động tới ứng dụng. Sau đó mới chọn tài khoản service phù hợp, cập nhật định nghĩa qua quy trình migration và kiểm thử bằng tài khoản gọi thực tế.

## 7. Quy trình kiểm kê toàn bộ đối tượng trong một schema

Khi nhận bàn giao hoặc chuẩn bị migration, có thể chạy các truy vấn sau trong một session có quyền xem metadata phù hợp.

**Bước 1: liệt kê view.**

```sql
SELECT TABLE_NAME, DEFINER, SECURITY_TYPE, IS_UPDATABLE
FROM information_schema.views
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

**Bước 2: liệt kê procedure và function.**

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SECURITY_TYPE,
       CREATED, LAST_ALTERED
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

**Bước 3: liệt kê trigger.**

```sql
SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_TIMING,
       EVENT_MANIPULATION, ACTION_ORDER, DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
```

**Bước 4: liệt kê event và trạng thái scheduler.**

```sql
SELECT @@GLOBAL.event_scheduler AS event_scheduler_status;

SELECT EVENT_NAME, DEFINER, EVENT_TYPE, TIME_ZONE,
       STARTS, ENDS, STATUS, LAST_EXECUTED
FROM information_schema.events
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

**Bước 5: xem định nghĩa từng đối tượng quan trọng.** Dùng `SHOW CREATE VIEW`, `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, `SHOW CREATE TRIGGER` hoặc `SHOW CREATE EVENT` theo đúng loại. Lưu kết quả vào hồ sơ migration hoặc hệ thống quản lý phiên bản theo quy trình của nhóm.

**Bước 6: rà soát quyền và definer.** Ghi lại tài khoản definer, `SQL SECURITY`, quyền người gọi cần có, phụ thuộc bảng/view/routine khác và cách kiểm thử khi chạy bằng tài khoản ứng dụng.

Không nên chỉ lưu tên đối tượng. Một bản kiểm kê hữu ích cần cả định nghĩa, ngữ cảnh quyền, phụ thuộc, trạng thái event và thời điểm metadata được ghi nhận.

## 8. Những lỗi thường gặp khi tra cứu metadata

- Dùng `TABLES` mà không lọc `TABLE_TYPE`, dẫn đến nhầm view với bảng thường.
- Chỉ truy vấn `ROUTINES` rồi bỏ qua `PARAMETERS`, khiến thiếu thông tin kiểu và thứ tự tham số.
- Chỉ kiểm tra `STATUS = ENABLED` của event mà không kiểm tra `@@GLOBAL.event_scheduler`.
- Thấy `VIEW_DEFINITION`, `ROUTINE_DEFINITION` hoặc `ACTION_STATEMENT` là `NULL` rồi kết luận đối tượng không có phần thân; nguyên nhân có thể là thiếu quyền xem metadata.
- Nghĩ `DEFINER` là người dùng đang kết nối hoặc là mật khẩu; đây là định danh tài khoản dùng trong ngữ cảnh quyền của đối tượng.
- Chỉ kiểm tra routine và view, bỏ sót trigger có thể tự chạy khi dữ liệu thay đổi.
- Thay definer bằng tài khoản có quyền rộng mà không đánh giá rủi ro mở rộng quyền.
- Chạy truy vấn metadata bằng tài khoản ứng dụng ít quyền rồi dùng kết quả đó làm danh sách đầy đủ của toàn schema.
- Giả định mọi đối tượng đều có `SQL SECURITY`; trigger và event có quy tắc thực thi theo definer.

## 9. Checklist rà soát view, routine, trigger, event và definer

- Đã chọn đúng schema và xác nhận `DATABASE()` không trả về `NULL` khi dùng phạm vi hiện tại.
- Đã kiểm kê view, procedure, function, trigger và event bằng `INFORMATION_SCHEMA`.
- Đã kiểm tra định nghĩa quan trọng bằng `SHOW CREATE`.
- Đã xem tham số routine, loại routine và thuộc tính truy cập dữ liệu.
- Đã kiểm tra thời điểm, sự kiện, thứ tự và phần thân của trigger.
- Đã kiểm tra cả trạng thái event lẫn trạng thái `event_scheduler`, múi giờ và lịch chạy.
- Đã ghi lại `DEFINER`, `SECURITY_TYPE`, `SQL_MODE` và quyền cần thiết để thực thi.
- Đã xác minh tài khoản definer còn tồn tại, có quyền tối thiểu phù hợp và có chủ sở hữu rõ ràng.
- Đã xác nhận tài khoản ứng dụng thực sự gọi được đối tượng trong đúng ngữ cảnh quyền.
- Đã ghi nhận giới hạn do thiếu quyền xem metadata trước khi kết luận danh sách đối tượng là đầy đủ.

View, routine, trigger và event là những phần quan trọng của schema MySQL vì chúng chứa logic và có thể thực thi dưới ngữ cảnh quyền riêng. `INFORMATION_SCHEMA` giúp kiểm kê có hệ thống; `SHOW CREATE` giúp xem định nghĩa đầy đủ; `DEFINER` và `SQL SECURITY` cho biết ai cung cấp quyền khi logic chạy. Kết hợp cả ba góc nhìn giúp bạn hiểu hành vi của database, phát hiện phụ thuộc ẩn và quản lý thay đổi schema an toàn hơn.
