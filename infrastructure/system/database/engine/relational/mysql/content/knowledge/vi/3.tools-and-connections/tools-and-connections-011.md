# Biến người dùng, biến hệ thống và tham số ở phạm vi phiên

Khi làm việc với MySQL, một kết nối có thể giữ trạng thái trong suốt thời gian tồn tại: giá trị tạm do người dùng gán, chế độ SQL, múi giờ, mức cô lập transaction, charset kết nối và nhiều thiết lập khác. Hiểu rõ phạm vi của từng loại biến giúp bạn viết script dễ kiểm soát, điều chỉnh hành vi của một phiên làm việc và tránh để trạng thái của lần chạy trước ảnh hưởng đến request tiếp theo.

MySQL có hai nhóm biến thường gặp ở cấp SQL: **biến do người dùng định nghĩa** (user-defined variables, có tên bắt đầu bằng `@`) và **biến hệ thống** (system variables, thường đọc qua `@@`). Biến hệ thống có thể có phạm vi toàn máy chủ (`GLOBAL`), phạm vi kết nối hiện tại (`SESSION`), hoặc cả hai. Ngoài ra còn có tham số của prepared statement, biến cục bộ trong stored program và tham số routine; chúng có quy tắc riêng, không đồng nhất với hai nhóm trên.

Bài học tập trung vào cách đọc, gán, thay đổi và quản lý trạng thái ở phạm vi một session MySQL.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt biến người dùng `@name` với biến hệ thống `@@GLOBAL.name` và `@@SESSION.name`.
- Khởi tạo, gán và đọc biến người dùng trong một kết nối; hiểu vòng đời và giới hạn của chúng.
- Đọc giá trị biến hệ thống bằng `SELECT` và `SHOW`, đồng thời nhận biết biến nào hỗ trợ phạm vi session.
- Thay đổi các tham số như `time_zone`, `sql_mode`, `autocommit` và transaction isolation cho kết nối hiện tại.
- Phân biệt thay đổi session với thay đổi global và cấu hình tồn tại qua lần khởi động máy chủ.
- Quản lý trạng thái kết nối an toàn, đặc biệt khi ứng dụng sử dụng connection pool hoặc prepared statement.

## 1. Session MySQL là gì?

Mỗi lần client kết nối thành công đến MySQL, máy chủ tạo một session cho kết nối đó. Session giữ trạng thái làm việc riêng, chẳng hạn:

- Biến người dùng do câu lệnh SQL tạo ra, ví dụ `@current_customer_id`.
- Giá trị session của các biến hệ thống, ví dụ `@@SESSION.time_zone` hoặc `@@SESSION.sql_mode`.
- Transaction đang mở, mức cô lập áp dụng cho transaction tiếp theo và trạng thái `autocommit`.
- Một số đối tượng gắn với kết nối như temporary table, prepared statement phía máy chủ và lock cấp session.

Nếu hai cửa sổ terminal mở hai kết nối riêng, mỗi cửa sổ có session riêng. Thay đổi biến người dùng hoặc tham số session trong cửa sổ A không tự động xuất hiện ở cửa sổ B. Khi kết nối đóng, trạng thái gắn với session đó được giải phóng.

```text
Client A                         MySQL Server                         Client B
session A                                                            session B
  @step = 1  ----------------->  giữ @step trong A
  time_zone = '+00:00' ------->  giữ time_zone của A

                                                               @step chưa được gán
                                                               time_zone theo mặc định B
```

Điểm cần nhớ: **session là phạm vi của một kết nối**, không nhất thiết là phạm vi của một người dùng đăng nhập hay một cửa sổ ứng dụng. Một ứng dụng có thể mở nhiều kết nối và mỗi kết nối có trạng thái khác nhau.

## 2. Biến do người dùng định nghĩa (`@variable`)

Biến người dùng là biến tạm do client tạo trong session hiện tại. Tên biến bắt đầu bằng ký tự `@`, ví dụ `@quantity`, `@subtotal` hoặc `@current_order_id`. Bạn không cần khai báo kiểu dữ liệu trước khi sử dụng.

### 2.1. Khởi tạo và đọc biến

Bạn có thể gán biến bằng `SET`:

```sql
SET @unit_price = 125000.00;
SET @quantity = 3;
SET @discount_rate = 0.10;

SELECT
    @unit_price AS unit_price,
    @quantity AS quantity,
    @unit_price * @quantity AS subtotal,
    @unit_price * @quantity * (1 - @discount_rate) AS amount_after_discount;
```

`SET` có thể gán nhiều biến trong một câu lệnh:

```sql
SET @min_price = 100000.00,
    @max_price = 500000.00,
    @category_code = 'ACCESSORY';

SELECT @min_price, @max_price, @category_code;
```

Biến chưa được gán có giá trị `NULL` trong session. Vì vậy, phép tính với một biến chưa khởi tạo thường cho kết quả `NULL`:

```sql
SELECT @counter AS counter_before_initialization;
SELECT @counter + 1 AS result_before_initialization;

SET @counter = 0;
SET @counter = @counter + 1;

SELECT @counter AS counter_after_initialization;
```

Kết quả cuối cùng là `1`. Hãy khởi tạo biến trước khi dùng nó trong phép tính hoặc điều kiện.

### 2.2. Gán giá trị từ truy vấn

Bạn có thể đưa kết quả của một truy vấn vào biến bằng `SELECT ... INTO`:

```sql
SELECT COUNT(*)
INTO @table_count
FROM information_schema.tables
WHERE table_schema = DATABASE();

SELECT @table_count AS table_count_in_current_database;
```

Truy vấn trên đếm số bảng trong database hiện được chọn. Hàm `DATABASE()` trả về `NULL` nếu session chưa chọn database bằng `USE` hoặc cấu hình kết nối tương ứng.

`SELECT ... INTO @variable` cần trả về tối đa một hàng. Nếu không có hàng, MySQL phát cảnh báo và biến giữ giá trị trước đó; nếu có nhiều hơn một hàng, câu lệnh báo lỗi. Dùng hàm tổng hợp như `COUNT(*)` hoặc điều kiện khóa duy nhất khi bạn cần chắc chắn chỉ có một kết quả.

### 2.3. Kiểu dữ liệu và chuyển đổi

Biến người dùng có thể nhận giá trị số, chuỗi, giá trị nhị phân hoặc `NULL`. Kiểu của giá trị phụ thuộc biểu thức được gán; MySQL có thể chuyển đổi kiểu khi biến được dùng trong biểu thức khác. Không nên dựa vào chuyển đổi ngầm nếu phép tính yêu cầu độ chính xác hoặc định dạng cụ thể.

```sql
SET @price = CAST('125000.50' AS DECIMAL(12,2));
SET @quantity = CAST('2' AS UNSIGNED);

SELECT
    @price AS price,
    @quantity AS quantity,
    CAST(@price * @quantity AS DECIMAL(14,2)) AS line_total;
```

Tên biến người dùng không phân biệt chữ hoa và chữ thường. Đặt tên có ý nghĩa, dùng nhất quán và tránh trùng tên với các biến khác trong script để việc đọc và bảo trì dễ dàng hơn.

### 2.4. Phạm vi và vòng đời

Biến người dùng chỉ tồn tại trong session đã tạo nó. Ví dụ, nếu chạy `SET @run_id = 42` trong kết nối A thì kết nối B không đọc được giá trị `42` đó. Khi kết nối A đóng, biến và giá trị của nó không còn.

Biến người dùng không phải dữ liệu lưu trữ lâu dài. Chúng không được ghi vào bảng, không chia sẻ giữa các kết nối và không phải cơ chế truyền dữ liệu giữa các máy chủ. Chúng cũng không phải biến giao dịch: `ROLLBACK` không hoàn tác việc gán `@variable`.

Ví dụ:

```sql
SET @marker = 'created-before-rollback';

START TRANSACTION;
SET @marker = 'changed-inside-transaction';
ROLLBACK;

SELECT @marker AS marker_after_rollback;
```

Kết quả vẫn là `changed-inside-transaction`, vì việc gán biến session không thuộc transaction dữ liệu của InnoDB.

### 2.5. Lưu ý khi dùng biến trong câu truy vấn

Bạn có thể đọc biến người dùng trong biểu thức, điều kiện hoặc phép tính:

```sql
SET @minimum_total = 250000.00;

SELECT @minimum_total AS configured_threshold;
```

Tuy nhiên, biến người dùng không thay thế tên bảng, tên cột hoặc định danh SQL. Ví dụ, `SELECT * FROM @table_name` không phải cú pháp hợp lệ để chọn bảng theo giá trị biến. Muốn tạo SQL động, cần dùng prepared statement và kiểm soát chặt các định danh được ghép vào câu lệnh.

Không nên vừa đọc vừa gán cùng một biến trong một biểu thức `SELECT` rồi phụ thuộc vào thứ tự đánh giá. Thứ tự đánh giá biểu thức có tham chiếu và cập nhật cùng biến không được bảo đảm. Cách viết cũ như `SELECT @n := @n + 1` ngoài câu `SET` cũng đã bị deprecated trong các phiên bản MySQL 8.0 hiện đại. Hãy tách thành các câu lệnh rõ ràng:

```sql
SET @n = 0;
SET @n = @n + 1;
SELECT @n;
```

## 3. Biến hệ thống (`@@GLOBAL` và `@@SESSION`)

Biến hệ thống là thiết lập do MySQL cung cấp để điều khiển hành vi của máy chủ hoặc session. Ví dụ: số kết nối tối đa, chế độ SQL, múi giờ, charset kết nối, `autocommit` và mức cô lập transaction.

### 3.1. Đọc biến hệ thống

Dùng tiền tố `@@` để đọc biến hệ thống. Nên chỉ rõ phạm vi khi muốn tránh nhầm lẫn:

```sql
SELECT
    @@GLOBAL.max_connections AS server_connection_limit,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit,
    @@SESSION.transaction_isolation AS session_transaction_isolation;
```

`@@GLOBAL.name` đọc giá trị toàn máy chủ. `@@SESSION.name` đọc giá trị của kết nối hiện tại. `@@LOCAL.name` là cách viết tương đương `@@SESSION.name`.

Với dạng viết tắt `@@variable_name` không chỉ rõ phạm vi, MySQL dùng giá trị session nếu biến có phạm vi session; nếu biến chỉ có phạm vi global thì dùng giá trị global. Trong tài liệu vận hành và script cần dễ đọc, nên ghi rõ `@@GLOBAL` hoặc `@@SESSION`.

Bạn cũng có thể dùng `SHOW VARIABLES`:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW SESSION VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'time_zone';
```

Nếu bỏ từ khóa `GLOBAL` hoặc `SESSION` trong `SHOW VARIABLES`, MySQL mặc định hiển thị giá trị session. Để kiểm tra một thiết lập của máy chủ, hãy yêu cầu `SHOW GLOBAL VARIABLES` rõ ràng.

### 3.2. Phạm vi của biến hệ thống

Không phải biến hệ thống nào cũng hỗ trợ cả hai phạm vi. Có biến chỉ có phạm vi global, có biến chỉ có phạm vi session, và có biến hỗ trợ cả hai.

| Phạm vi | Ý nghĩa | Ví dụ |
|---|---|---|
| `GLOBAL` | Một giá trị ở cấp máy chủ, ảnh hưởng đến hành vi chung hoặc giá trị mặc định cho kết nối mới | `max_connections` |
| `SESSION` | Giá trị riêng cho kết nối hiện tại; một số biến chỉ có phạm vi này và có thể chỉ đọc | `in_transaction` (trạng thái transaction hiện tại) |
| `GLOBAL` và `SESSION` | Có giá trị máy chủ và giá trị riêng cho từng kết nối | `sql_mode`, `time_zone`, `autocommit` |

Khi một kết nối mới được tạo, các biến có cả phạm vi global và session thường khởi tạo giá trị session từ giá trị global tại thời điểm kết nối. Sau đó, thay đổi session chỉ tác động kết nối đó. Nếu một biến không hỗ trợ phạm vi session mà bạn cố đọc `@@SESSION.variable_name`, MySQL báo lỗi. Vì vậy, cần kiểm tra tài liệu của từng biến thay vì giả định tất cả biến đều có cả hai phạm vi.

### 3.3. Phân biệt biến người dùng và biến hệ thống

| Tiêu chí | Biến người dùng | Biến hệ thống |
|---|---|---|
| Cách viết | `@my_value` | `@@SESSION.sql_mode`, `@@GLOBAL.max_connections` |
| Ai định nghĩa | Người viết câu lệnh SQL | MySQL cung cấp |
| Mục đích | Giữ giá trị tạm để dùng trong session | Cấu hình hành vi máy chủ hoặc session |
| Kiểu dữ liệu | Không khai báo kiểu trước; nhận giá trị từ biểu thức | Kiểu và miền giá trị do MySQL quy định |
| Cách gán | `SET @my_value = ...` | `SET SESSION ...` hoặc `SET GLOBAL ...` nếu được hỗ trợ |
| Phạm vi | Session hiện tại | Global, session hoặc cả hai tùy biến |

Hai cú pháp có hình thức gần nhau nhưng không thể thay thế cho nhau:

```sql
SET @time_zone_note = 'Múi giờ dùng trong bài kiểm thử';
SET SESSION time_zone = '+00:00';

SELECT
    @time_zone_note AS user_variable,
    @@SESSION.time_zone AS system_variable;
```

`@time_zone_note` chỉ là giá trị do script lưu tạm; nó không thay đổi múi giờ. `@@SESSION.time_zone` là thiết lập thực sự được MySQL dùng cho session.

## 4. Thay đổi tham số ở phạm vi session

Để thay đổi biến hệ thống cho kết nối hiện tại, dùng `SET SESSION` hoặc `SET @@SESSION.variable_name`:

```sql
SET SESSION time_zone = '+00:00';
-- Tương đương:
SET @@SESSION.time_zone = '+00:00';

SELECT @@SESSION.time_zone;
```

Thiết lập này chỉ áp dụng cho kết nối hiện tại. Khi kết nối đóng, thay đổi session không được giữ lại cho kết nối mới.

### 4.1. Thay đổi múi giờ session

Múi giờ session ảnh hưởng đến các hàm trả về thời gian hiện tại và cách MySQL chuyển đổi giá trị `TIMESTAMP` khi đọc/ghi. Ví dụ:

```sql
SET SESSION time_zone = '+00:00';

SELECT
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    CURRENT_TIMESTAMP() AS session_current_timestamp,
    UTC_TIMESTAMP() AS utc_now;
```

`NOW()` và `CURRENT_TIMESTAMP()` sử dụng múi giờ session. `UTC_TIMESTAMP()` trả về thời gian UTC. `DATETIME` lưu và trả về thành phần ngày giờ đã ghi mà không tự chuyển đổi theo múi giờ session; `TIMESTAMP` được chuyển đổi giữa múi giờ session và UTC khi ghi/đọc. Vì thế, ứng dụng cần thống nhất quy ước múi giờ ở tầng kết nối và tầng nghiệp vụ.

### 4.2. Thay đổi chế độ SQL cho session

`sql_mode` điều khiển cách MySQL xử lý một số cú pháp và dữ liệu, ví dụ chế độ strict hoặc yêu cầu nhóm cột rõ ràng. Bạn có thể kiểm tra trước khi thay đổi:

```sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
```

Đặt `sql_mode` ở session sẽ thay thế toàn bộ danh sách mode hiện tại của session:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

Ví dụ trên chỉ là một danh sách minh họa. Trong ứng dụng thật, không sao chép nguyên danh sách này một cách máy móc vì có thể bỏ các mode mà môi trường đang cần. Hãy đọc giá trị hiện tại, thống nhất danh sách mode mong muốn và xác minh lại sau khi thay đổi.

### 4.3. Thay đổi tham số an toàn truy vấn

`sql_safe_updates` có thể giúp giảm nguy cơ vô tình chạy `UPDATE` hoặc `DELETE` trên quá nhiều hàng khi không có điều kiện dựa trên khóa hoặc giới hạn phù hợp:

```sql
SET SESSION sql_safe_updates = 1;
SELECT @@SESSION.sql_safe_updates;
```

Đây là lớp bảo vệ tiện ích cho session làm việc, không phải cơ chế phân quyền hay ranh giới bảo mật. Nó không thay thế transaction, bản sao lưu, quyền tối thiểu hoặc việc kiểm tra câu lệnh trước khi thực thi.

### 4.4. Thiết lập mức cô lập transaction

Có thể đặt mức cô lập mặc định cho các transaction tiếp theo của session bằng cú pháp:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT @@SESSION.transaction_isolation;
```

Các mức thường gặp là `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. MySQL InnoDB mặc định dùng `REPEATABLE READ` trong cấu hình thông thường. Thay đổi mức cô lập có thể làm thay đổi cách transaction nhìn thấy dữ liệu và cách khóa được sử dụng; cần đánh giá theo yêu cầu nhất quán và tải đồng thời của ứng dụng.

Nếu chỉ muốn áp dụng mức cô lập cho transaction kế tiếp, dùng `SET TRANSACTION ISOLATION LEVEL ...` mà không có từ khóa `SESSION`. Nếu dùng `SET SESSION TRANSACTION ...`, giá trị trở thành mặc định cho các transaction tiếp theo trong session đó.

### 4.5. Thiết lập charset kết nối

`SET NAMES` thiết lập bộ ký tự client, connection và results cho session, đồng thời chọn collation kết nối tương ứng nếu có chỉ định:

```sql
SET NAMES utf8mb4;
-- Hoặc chỉ rõ collation:
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
```

Trong ứng dụng, nên cấu hình charset trong driver hoặc connection string để mỗi kết nối được khởi tạo đúng. Không nên phụ thuộc vào việc chạy thủ công `SET NAMES` trong một cửa sổ terminal nếu ứng dụng mở các kết nối riêng.

## 5. Thay đổi biến global và ảnh hưởng đến session hiện có

Biến global tác động ở cấp máy chủ. Nếu biến hỗ trợ thay đổi động, tài khoản có quyền phù hợp có thể dùng `SET GLOBAL`:

```sql
SET GLOBAL max_connections = 300;
SELECT @@GLOBAL.max_connections;
```

`max_connections` là thiết lập giới hạn kết nối ở cấp máy chủ. Lệnh ví dụ cần quyền quản trị phù hợp, thường là quyền động `SYSTEM_VARIABLES_ADMIN` trong MySQL 8.0; các phiên bản cũ có thể dùng quyền `SUPER`. Tên quyền và điều kiện cụ thể phụ thuộc phiên bản.

Thay đổi global không tự động ghi đè giá trị session đã được tạo ở các kết nối đang hoạt động. Với biến có cả hai phạm vi, kết nối mới sẽ nhận giá trị global hiện tại làm giá trị khởi tạo; các session hiện hữu tiếp tục giữ giá trị session riêng cho đến khi chúng thay đổi hoặc kết thúc.

```text
Thời điểm T1: GLOBAL time_zone = SYSTEM
  Kết nối A mở -> SESSION A nhận SYSTEM
  Kết nối B mở -> SESSION B nhận SYSTEM

Thời điểm T2: GLOBAL time_zone đổi thành +00:00
  Kết nối A vẫn giữ SESSION A = SYSTEM
  Kết nối B vẫn giữ SESSION B = SYSTEM
  Kết nối C mở -> SESSION C nhận +00:00
```

Đây là lý do một thay đổi global không phải cách để ép tất cả session hiện hữu dùng cấu hình mới ngay lập tức.

`SET GLOBAL` thay đổi giá trị đang chạy trong bộ nhớ máy chủ. Thông thường, giá trị này không tự tồn tại sau khi MySQL khởi động lại. Nếu cần cấu hình lâu dài, hãy thay đổi file cấu hình hoặc dùng cơ chế lưu cấu hình phù hợp với phiên bản và chính sách vận hành.

Từ MySQL 8.0.11, `SET PERSIST` có thể thay đổi giá trị global đang chạy và ghi giá trị vào file cấu hình persisted để áp dụng sau lần khởi động tiếp theo:

```sql
-- Ví dụ minh họa; chỉ thực hiện khi có phê duyệt vận hành
SET PERSIST max_connections = 300;
```

`SET PERSIST_ONLY` ghi giá trị persisted mà không thay đổi giá trị runtime hiện tại, thường hữu ích với một số biến chỉ có thể cấu hình khi khởi động. `SET PERSIST` và `SET PERSIST_ONLY` cần quyền quản trị phù hợp và phải được dùng theo quy trình thay đổi cấu hình. Không dùng chúng để thử tham số session thông thường.

Không phải mọi biến đều có thể thay đổi động hoặc lưu bằng `SET PERSIST`. Một số biến chỉ đọc hoặc chỉ được thiết lập lúc máy chủ khởi động; khi đó cần cấu hình trong file cấu hình và lên kế hoạch restart theo quy trình vận hành.

## 6. Quyền và giới hạn khi thay đổi biến

Khả năng đọc biến và khả năng thay đổi biến là hai việc khác nhau. Nhiều biến session thông thường cho phép người dùng thay đổi trong session của mình, nhưng một số biến bị giới hạn cần quyền bổ sung. Thay đổi biến global cần quyền quản trị. Các thao tác persisted cần quyền phù hợp để sửa cấu hình được lưu.

Trước khi thực hiện thay đổi:

1. Đọc giá trị hiện tại ở đúng phạm vi (`GLOBAL` hay `SESSION`).
2. Xác nhận biến có hỗ trợ phạm vi và có thể thay đổi động ở phiên bản MySQL đang chạy.
3. Kiểm tra quyền của tài khoản và phạm vi ảnh hưởng.
4. Ghi lại giá trị ban đầu nếu cần khôi phục session sau thử nghiệm.
5. Thay đổi trong phạm vi nhỏ nhất có thể, sau đó đọc lại biến để xác minh.

Ví dụ lưu lại và khôi phục một thiết lập session trong cùng kết nối:

```sql
SET @old_time_zone = @@SESSION.time_zone;

SET SESSION time_zone = '+00:00';
SELECT @@SESSION.time_zone;

-- Khôi phục giá trị đã lưu trong biến người dùng
SET SESSION time_zone = @old_time_zone;
SELECT @@SESSION.time_zone;
```

Ví dụ này chỉ có ý nghĩa trong cùng một session. Nếu kết nối bị đóng giữa chừng, biến `@old_time_zone` cũng mất; session mới được khởi tạo theo giá trị global hiện hành.

## 7. Biến người dùng, biến cục bộ và tham số prepared statement

Ba cơ chế dưới đây thường bị nhầm vì đều có thể giữ hoặc truyền giá trị, nhưng phạm vi và mục đích khác nhau.

| Cơ chế | Cú pháp | Phạm vi | Mục đích |
|---|---|---|---|
| Biến người dùng | `@customer_id` | Session kết nối | Giữ giá trị tạm giữa các câu lệnh SQL |
| Biến cục bộ trong stored program | `DECLARE v_total DECIMAL(12,2)` | Khối `BEGIN ... END` hoặc routine | Biến tạm có khai báo kiểu trong procedure/function |
| Tham số prepared statement | `?` | Lần thực thi prepared statement | Gắn giá trị đầu vào vào câu SQL đã chuẩn bị |

Ví dụ tham số prepared statement ở phía ứng dụng:

```sql
SELECT customer_id, email
FROM customer
WHERE customer_id = ?;
```

Ứng dụng gửi câu lệnh đã chuẩn bị và truyền giá trị `customer_id` qua API bind parameter của driver. Không nối chuỗi đầu vào của người dùng vào câu SQL để tạo điều kiện lọc. Parameter marker `?` đại diện cho giá trị dữ liệu, không đại diện cho tên bảng hoặc tên cột.

Ở SQL client, prepared statement phía máy chủ có thể dùng biến người dùng để cung cấp giá trị cho `EXECUTE ... USING`:

```sql
SET @customer_id = 101;
SET @sql_text =
    'SELECT customer_id, email FROM customer WHERE customer_id = ?';

PREPARE customer_lookup FROM @sql_text;
EXECUTE customer_lookup USING @customer_id;
DEALLOCATE PREPARE customer_lookup;
```

Ở đây `@customer_id` là biến session cung cấp giá trị cho placeholder. Placeholder vẫn chỉ đại diện cho giá trị dữ liệu; nếu cần thay đổi tên bảng hoặc cột, phải kiểm tra định danh theo danh sách cho phép và tạo câu lệnh một cách an toàn.

## 8. Connection pool và trạng thái session

Trong ứng dụng web hoặc dịch vụ backend, connection pool giữ sẵn một nhóm kết nối để tái sử dụng. Một request có thể mượn kết nối A, thiết lập `@request_id` hoặc thay đổi `time_zone`, rồi trả kết nối về pool. Request tiếp theo có thể nhận lại đúng kết nối A.

Nếu pool không reset session state, request sau có thể nhìn thấy biến người dùng hoặc thiết lập session do request trước để lại. Điều này gây lỗi khó tái hiện vì kết quả phụ thuộc vào kết nối nào được pool cấp.

Các biện pháp cần áp dụng:

- Đặt các thiết lập bắt buộc ở bước khởi tạo mỗi kết nối, ví dụ charset và múi giờ theo quy ước của ứng dụng.
- Trả session về trạng thái chuẩn trước khi trả kết nối vào pool, hoặc bật cơ chế reset connection do driver/pool hỗ trợ.
- Không dựa vào biến `@name` để truyền dữ liệu giữa hai request độc lập.
- Kết thúc transaction đúng cách bằng `COMMIT` hoặc `ROLLBACK` trước khi trả kết nối.
- Không để temporary table, prepared statement phía máy chủ hoặc lock cấp session tồn tại ngoài vòng đời cần thiết.
- Kiểm thử trường hợp một kết nối được tái sử dụng cho hai request có thiết lập khác nhau.

Một nguyên tắc hữu ích là coi mọi kết nối mượn từ pool như một session có thể chứa trạng thái cũ. Request phải thiết lập rõ những gì nó cần và dọn trạng thái mà nó tạo ra theo hợp đồng của pool.

## 9. Quy trình thực hành: quan sát và thay đổi session

Bạn có thể thực hiện bài tập sau trong một database sandbox. Không cần tạo bảng hoặc sửa dữ liệu để quan sát các biến session.

**Bước 1: xem trạng thái ban đầu.**

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    DATABASE() AS current_database,
    @@GLOBAL.max_connections AS global_max_connections,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit;
```

Ghi lại `connection_id` và các giá trị session.

**Bước 2: tạo biến người dùng.**

```sql
SET @exercise_label = 'mysql-session-lab';
SET @expected_rows = 5;

SELECT @exercise_label, @expected_rows;
```

**Bước 3: thay đổi múi giờ và kiểm tra.**

```sql
SET SESSION time_zone = '+00:00';

SELECT
    CONNECTION_ID() AS connection_id,
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

`connection_id` phải giữ nguyên trong cùng kết nối. `time_zone` của session hiện tại phải là `+00:00`.

**Bước 4: so sánh với một kết nối thứ hai.**

Mở một kết nối MySQL mới và chạy:

```sql
SELECT
    CONNECTION_ID() AS second_connection_id,
    @exercise_label AS user_variable_in_second_session,
    @@SESSION.time_zone AS second_session_time_zone;
```

Kết nối thứ hai có `connection_id` khác. `@exercise_label` có giá trị `NULL` vì biến được tạo ở session thứ nhất. Múi giờ session thứ hai được khởi tạo theo giá trị global hiện hành, không tự nhận thay đổi session của kết nối thứ nhất.

**Bước 5: đóng kết nối thử nghiệm.**

Đóng kết nối thứ nhất rồi mở lại và kiểm tra `@exercise_label`. Biến không còn vì session cũ đã kết thúc. Nếu dùng connection pool, đóng cửa sổ ứng dụng không nhất thiết đóng ngay kết nối vật lý; hãy dựa vào cơ chế reset hoặc vòng đời thực tế của pool.

## 10. Những lỗi thường gặp

- Dùng `@variable` nhưng quên khởi tạo, dẫn đến biểu thức trả về `NULL`.
- Nghĩ rằng `SET SESSION` thay đổi cấu hình của toàn máy chủ; thực tế nó chỉ tác động kết nối hiện tại.
- Đọc `SHOW VARIABLES` rồi cho rằng đó là giá trị global; mặc định lệnh này hiển thị session.
- Thay đổi `SET GLOBAL` nhưng mong các session đang chạy tự động nhận giá trị mới.
- Nghĩ rằng `SET GLOBAL` sẽ tồn tại sau restart; thay đổi runtime thông thường không tự được lưu bền vững.
- Cho rằng `ROLLBACK` hoàn tác việc gán biến người dùng; biến session không thuộc transaction dữ liệu.
- Dùng biến người dùng để thay tên bảng/cột hoặc ghép chuỗi đầu vào vào SQL, tạo lỗi cú pháp hoặc nguy cơ SQL injection.
- Để connection pool tái sử dụng session mà không reset biến, transaction hoặc thiết lập đã thay đổi.
- Giả định mọi biến hệ thống đều có phạm vi session và có thể thay đổi động; phạm vi, quyền và khả năng thay đổi phụ thuộc từng biến và phiên bản MySQL.

## 11. Checklist quản lý biến và tham số session

- Đã xác định giá trị cần lưu là biến tạm do script tạo hay biến hệ thống do MySQL quản lý.
- Đã dùng đúng cú pháp `@name`, `@@SESSION.name` hoặc `@@GLOBAL.name`.
- Đã khởi tạo biến người dùng trước khi đọc hoặc tính toán.
- Đã kiểm tra giá trị, kiểu và kết quả truy vấn sau khi gán.
- Đã xác minh biến hệ thống có hỗ trợ phạm vi cần dùng và có thể thay đổi động hay không.
- Đã đọc giá trị trước khi thay đổi và biết cách khôi phục nếu thử nghiệm cần thiết lập ban đầu.
- Đã hiểu thay đổi session chỉ ảnh hưởng kết nối hiện tại; thay đổi global có quy tắc riêng đối với kết nối mới và kết nối đang hoạt động.
- Đã kiểm tra quyền cần thiết trước khi thay đổi biến global hoặc persisted.
- Đã thiết lập và reset trạng thái session theo quy trình của connection pool.
- Đã dùng parameter binding của driver cho dữ liệu đầu vào ứng dụng thay vì ghép chuỗi SQL.

Biến người dùng giúp lưu giá trị tạm trong một kết nối; biến hệ thống điều khiển hành vi của MySQL ở phạm vi global hoặc session; còn tham số prepared statement giúp ứng dụng truyền dữ liệu vào câu SQL đã chuẩn bị. Khi phân biệt đúng ba cơ chế và quản lý vòng đời kết nối, bạn có thể điều chỉnh hành vi của một phiên làm việc mà không vô tình làm rò rỉ trạng thái sang request khác hoặc thay đổi cấu hình ngoài phạm vi dự kiến.
