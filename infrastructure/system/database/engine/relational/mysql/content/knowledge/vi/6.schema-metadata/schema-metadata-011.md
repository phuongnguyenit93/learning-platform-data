# Quyền nhìn thấy metadata và giới hạn theo tài khoản

Metadata mô tả cấu trúc và trạng thái của database: schema, bảng, cột, index, constraint, view, routine và một số thông tin vận hành. Trong MySQL, metadata không mặc nhiên hiển thị đầy đủ cho mọi tài khoản. Khả năng nhìn thấy phụ thuộc vào quyền của tài khoản đang kết nối, loại đối tượng và lệnh hoặc bảng metadata được truy vấn.

Cơ chế này giúp người quản trị giới hạn thông tin cấu trúc mà từng ứng dụng hoặc nhóm người dùng được phép khám phá. Một tài khoản chỉ có quyền đọc một bảng có thể xem một phần metadata của bảng đó, nhưng không nhất thiết xem được toàn bộ schema, định nghĩa view, stored routine hay hoạt động của session khác.

Trong module **DATABASE_MYSQL**, hiểu quyền nhìn thấy metadata giúp thiết kế phân quyền, xây dựng công cụ kiểm tra schema, hỗ trợ migration, audit và xử lý sự cố. Cần phân biệt rõ ba câu hỏi: tài khoản có nhìn thấy tên đối tượng không, có xem được định nghĩa chi tiết không, và có được đọc hoặc thay đổi dữ liệu không.

## 1. Metadata là gì và được truy cập ở đâu?

Metadata là dữ liệu mô tả database chứ không phải các hàng nghiệp vụ trong bảng. Ví dụ:

- **Schema:** tên database và các thuộc tính liên quan.
- **Table và view:** tên đối tượng, engine, định dạng, thời điểm tạo hoặc cập nhật.
- **Column:** tên cột, kiểu dữ liệu, nullability, default, collation và thứ tự.
- **Index:** tên index, cột tham gia, thứ tự cột và tính chất unique.
- **Constraint:** primary key, foreign key, unique và check constraint.
- **Routine và trigger:** tên, kiểu đối tượng, definer, trạng thái và định nghĩa tùy quyền.
- **Metadata vận hành:** thông tin về session, statement, lock, transaction và instrument khi được cung cấp qua Performance Schema.

MySQL cung cấp nhiều giao diện để xem metadata:

| Giao diện | Mục đích |
|---|---|
| `SHOW DATABASES`, `SHOW TABLES`, `SHOW COLUMNS`, `SHOW INDEX` | Lệnh nhanh để kiểm tra schema, bảng, cột và index |
| `SHOW CREATE TABLE`, `SHOW CREATE VIEW` | Xem câu lệnh định nghĩa đối tượng |
| `INFORMATION_SCHEMA` | Truy vấn metadata có cấu trúc bằng SQL |
| `SHOW STATUS`, `SHOW VARIABLES` | Xem trạng thái và cấu hình server/session |
| `performance_schema` | Quan sát hoạt động, statement, session, wait và lock |
| `sys` | Các view tiện dụng tổng hợp dữ liệu chẩn đoán từ Performance Schema và Information Schema |

Các giao diện này không có cùng mục tiêu và không có cùng quy tắc hiển thị. Đặc biệt, `INFORMATION_SCHEMA` không phải một bản sao công khai đầy đủ của data dictionary. Các hàng metadata được lọc theo quyền của tài khoản và một số cột định nghĩa còn có yêu cầu quyền riêng.

## 2. Nguyên tắc lọc metadata theo quyền

MySQL áp dụng nguyên tắc **chỉ hiển thị đối tượng mà tài khoản có quyền phù hợp để biết hoặc thao tác**. Vì thế, hai tài khoản truy vấn cùng một bảng metadata có thể nhận các kết quả khác nhau.

Ví dụ, một tài khoản có quyền trên `appdb.orders` có thể nhìn thấy bảng đó trong các lệnh liệt kê và truy vấn metadata tương ứng. Một tài khoản không có quyền trên schema hoặc bảng có thể không thấy đối tượng đó trong kết quả liệt kê thông thường.

Cần phân biệt:

1. **Quyền nhìn thấy schema:** quyết định tài khoản có thể liệt kê database hay không.
2. **Quyền nhìn thấy đối tượng:** ảnh hưởng đến khả năng liệt kê bảng, view, cột và index.
3. **Quyền xem định nghĩa:** một số đối tượng như view hoặc routine có thể yêu cầu quyền bổ sung để xem nội dung định nghĩa.
4. **Quyền sử dụng dữ liệu:** `SELECT`, `INSERT`, `UPDATE`, `DELETE` và các quyền khác quyết định thao tác dữ liệu có được phép hay không.
5. **Quyền quan sát hoạt động server:** các thông tin session và statement có thể cần quyền như `PROCESS` hoặc quyền đọc Performance Schema.

Việc nhìn thấy tên bảng không đồng nghĩa được đọc mọi hàng trong bảng. Ngược lại, một view được cấp quyền `SELECT` có thể cho phép đọc một tập dữ liệu đã giới hạn mà người dùng không có quyền trực tiếp trên các bảng nền.

## 3. Quyền nhìn thấy database và bảng

### 3.1. SHOW DATABASES

Theo mặc định, `SHOW DATABASES` chỉ liệt kê các schema mà tài khoản có một quyền phù hợp. Tài khoản có quyền toàn cục `SHOW DATABASES` có thể liệt kê tất cả schema trên instance.

Ví dụ:

```sql
SHOW DATABASES;
```

Một tài khoản được cấp quyền trên một database cụ thể có thể nhìn thấy database đó mà không cần quyền liệt kê toàn bộ schema. Quản trị viên có thể cấp quyền toàn cục nếu vai trò kiểm toán hoặc quản trị thực sự cần:

```sql
GRANT SHOW DATABASES ON *.*
TO 'metadata_auditor'@'10.20.0.25';
```

`SHOW DATABASES` làm tăng phạm vi thông tin mà tài khoản có thể khám phá. Không nên cấp quyền này cho mọi ứng dụng chỉ vì ứng dụng cần kết nối tới một schema đã biết.

### 3.2. SHOW TABLES và INFORMATION_SCHEMA.TABLES

`SHOW TABLES` liệt kê bảng và view mà tài khoản có quyền phù hợp trong schema được chỉ định hoặc schema hiện tại.

```sql
SHOW TABLES FROM appdb;
```

Có thể truy vấn có cấu trúc qua `INFORMATION_SCHEMA.TABLES`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
ORDER BY TABLE_NAME;
```

Kết quả được lọc theo quyền của tài khoản. Tài khoản có quyền trên `appdb.orders` có thể thấy metadata của bảng đó, trong khi các bảng khác không có quyền có thể không xuất hiện.

Đừng dùng kết quả `SHOW TABLES` hoặc `INFORMATION_SCHEMA.TABLES` của một tài khoản hạn chế để kết luận rằng database không có các bảng khác. Muốn kiểm kê toàn bộ schema, hãy sử dụng một account audit được cấp phạm vi quyền có chủ đích.

### 3.3. Metadata của cột và index

Tài khoản có quyền phù hợp trên bảng có thể xem thông tin cột bằng `SHOW COLUMNS`:

```sql
SHOW FULL COLUMNS FROM appdb.orders;
```

Hoặc truy vấn `INFORMATION_SCHEMA.COLUMNS`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Thông tin index có thể được xem bằng:

```sql
SHOW INDEX FROM appdb.orders;
```

Hoặc:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Metadata cột và index hữu ích cho công cụ migration, schema diff và kiểm tra hiệu năng. Tuy nhiên, kết quả vẫn phản ánh góc nhìn quyền của account hiện tại. Khi công cụ tự động phát hiện schema, cần chạy bằng account có đủ quyền đọc metadata cần thiết.

## 4. Xem định nghĩa view và routine cần quyền riêng

Tên view hoặc routine có thể xuất hiện trong một số kết quả metadata nhưng nội dung định nghĩa không nhất thiết hiển thị cho mọi tài khoản.

### 4.1. View và quyền SHOW VIEW

Quyền `SHOW VIEW` cho phép xem định nghĩa view. Ví dụ:

```sql
GRANT SHOW VIEW ON appdb.*
TO 'metadata_auditor'@'10.20.0.25';

SHOW CREATE VIEW appdb.order_summary;
```

Có thể truy vấn metadata view qua `INFORMATION_SCHEMA.VIEWS`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'appdb';
```

Nếu tài khoản không có `SHOW VIEW` phù hợp, trường `VIEW_DEFINITION` có thể trả về `NULL`. Đây là giới hạn quan trọng: nhìn thấy tên view không đồng nghĩa được xem câu SQL định nghĩa view.

Quyền `SHOW VIEW` không tự cấp quyền đọc dữ liệu mà view trả về. Quyền truy vấn view và quyền xem định nghĩa là hai vấn đề riêng biệt.

### 4.2. Stored procedure và function

Metadata routine được cung cấp qua `INFORMATION_SCHEMA.ROUTINES`, cùng các lệnh như `SHOW PROCEDURE STATUS`, `SHOW FUNCTION STATUS` và `SHOW CREATE PROCEDURE`.

Từ MySQL 8.0.20, dynamic privilege `SHOW_ROUTINE` hỗ trợ kiểm soát việc xem định nghĩa stored routine. Tài khoản cũng có thể có quyền trên routine cụ thể như `EXECUTE`, `ALTER ROUTINE` hoặc `CREATE ROUTINE`; khả năng xem định nghĩa phụ thuộc tổ hợp quyền và phiên bản. Khi xây dựng account audit, hãy kiểm tra tài liệu đúng phiên bản và chỉ cấp quyền xem routine khi thực sự cần.

Ví dụ xem metadata tổng quát:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';
```

Không nên cấp quyền xem toàn bộ routine definitions cho tài khoản runtime nếu ứng dụng chỉ cần gọi một procedure đã được cấp `EXECUTE`.

## 5. Metadata của session và hoạt động server

Thông tin cấu trúc database khác với thông tin vận hành. Các bảng trong `performance_schema` và các view thuộc `sys` có thể chứa statement SQL, tên user, host, trạng thái thread, lock và wait event.

### 5.1. PROCESS và danh sách kết nối

Không có quyền `PROCESS`, tài khoản thông thường chỉ nhìn thấy các thread hoặc connection của chính mình trong các giao diện process list. Tài khoản có quyền toàn cục `PROCESS` có thể xem thông tin thread của các user khác.

Ví dụ:

```sql
SHOW FULL PROCESSLIST;
```

Hoặc:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND';
```

Để đọc các bảng Performance Schema, tài khoản cần quyền `SELECT` phù hợp trên các bảng đó. Quyền `PROCESS` mở rộng khả năng nhìn thấy thread của các tài khoản khác trong process list. Đây là quyền nhạy cảm vì thông tin hiển thị có thể chứa câu SQL và dữ liệu vận hành.

### 5.2. Đọc lock và wait

Performance Schema cung cấp các bảng như `data_locks`, `data_lock_waits` và `metadata_locks` để chẩn đoán khóa. Ví dụ:

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS
FROM performance_schema.data_locks;
```

Một truy vấn chẩn đoán chỉ trả về những thông tin mà account có quyền đọc và hệ thống đang instrument. Nếu không có quyền `SELECT` trên bảng Performance Schema, truy vấn sẽ bị từ chối; nếu không có dữ liệu phù hợp hoặc instrument không ghi nhận sự kiện, kết quả có thể rỗng.

Đối với vận hành production, hãy cấp quyền đọc riêng cho nhóm DBA hoặc observability, thay vì cấp `PROCESS` và quyền đọc rộng cho mọi ứng dụng.

### 5.3. View trong sys schema

`sys` cung cấp các view dễ đọc hơn để tổng hợp dữ liệu từ Performance Schema và Information Schema, ví dụ các view về statement, schema, index hoặc process list. Đây là lớp tiện ích cho người quản trị, không phải cơ chế bỏ qua quyền.

Khả năng truy vấn view `sys` phụ thuộc định nghĩa SQL SECURITY của view và các quyền mà account có đối với view hoặc nguồn dữ liệu bên dưới. Nếu gặp `Access denied`, hãy xác minh quyền cần thiết thay vì mặc định mọi view `sys` đều công khai.

## 6. Ví dụ phân quyền theo vai trò

Một hệ thống thường có ít nhất ba nhóm tài khoản với nhu cầu metadata khác nhau:

| Vai trò | Nhu cầu | Phạm vi quyền nên cân nhắc |
|---|---|---|
| Ứng dụng runtime | Kết nối và thao tác dữ liệu nghiệp vụ | Quyền DML trên schema/bảng cần thiết; không cần quyền audit toàn instance |
| Công cụ migration | Đọc schema và thay đổi cấu trúc theo đợt triển khai | Quyền đọc metadata và quyền DDL cần thiết trong cửa sổ migration |
| DBA/auditor | Kiểm kê schema, xem định nghĩa, chẩn đoán session và lock | Quyền metadata, `SHOW VIEW`, quyền routine hoặc `PROCESS` theo nhiệm vụ cụ thể |

Ví dụ tạo tài khoản đọc dữ liệu một bảng và metadata liên quan:

```sql
CREATE USER 'report_reader'@'10.20.0.25'
    IDENTIFIED BY 'REPLACE_WITH_A_STRONG_SECRET';

GRANT SELECT
    ON appdb.orders
    TO 'report_reader'@'10.20.0.25';
```

Account này có quyền đọc dữ liệu của bảng `orders` và có thể xem metadata tương ứng theo quy tắc của MySQL. Nó không tự động có quyền xem mọi database, định nghĩa view riêng tư, routine hoặc session của user khác.

Nếu một nhóm cần xem định nghĩa view trong schema:

```sql
GRANT SHOW VIEW
    ON appdb.*
    TO 'metadata_auditor'@'10.20.0.25';
```

Nếu auditor cần liệt kê mọi schema, có thể cấp `SHOW DATABASES` toàn cục sau khi đánh giá phạm vi:

```sql
GRANT SHOW DATABASES
    ON *.*
    TO 'metadata_auditor'@'10.20.0.25';
```

Chỉ cấp `PROCESS` khi nhiệm vụ yêu cầu quan sát connection của các tài khoản khác:

```sql
GRANT PROCESS
    ON *.*
    TO 'dba_observer'@'10.20.0.25';
```

Các ví dụ dùng địa chỉ IP và mật khẩu giả định; hãy thay bằng account và nguồn kết nối thực tế. Không sử dụng mật khẩu ví dụ trong production.

## 7. Kiểm tra quyền và giải thích kết quả

### 7.1. Xác định account thực sự đang được sử dụng

Chạy trên chính kết nối cần kiểm tra:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS matched_account,
    CURRENT_ROLE() AS active_roles,
    DATABASE() AS current_database;
```

`USER()` cho biết danh tính client trình bày khi kết nối. `CURRENT_USER()` cho biết account MySQL được chọn để kiểm tra quyền. `CURRENT_ROLE()` hiển thị role đang hoạt động trong session. Hai account có cùng username nhưng host khác nhau có thể có tập quyền khác nhau.

Nếu quyền được cấp thông qua role, cần kiểm tra role đã được kích hoạt trong session hay chưa. Role có thể được đặt mặc định cho user hoặc kích hoạt bằng `SET ROLE` tùy cấu hình.

### 7.2. Xem quyền được cấp

Dùng `SHOW GRANTS` để kiểm tra quyền của account:

```sql
SHOW GRANTS FOR 'report_reader'@'10.20.0.25';
```

Để xem quyền của account hiện tại:

```sql
SHOW GRANTS;
```

Nếu account nhận quyền qua role, xem các role đã cấp và role đang hoạt động. Không nên chỉ nhìn một câu `GRANT SELECT` rồi kết luận toàn bộ quyền: quyền có thể đến từ global, schema, table, column, routine hoặc role.

### 7.3. So sánh metadata giữa hai tài khoản

Giả sử `report_reader` chỉ có quyền trên `appdb.orders`, còn `metadata_auditor` có quyền đọc metadata của nhiều bảng hơn. Khi chạy cùng truy vấn `INFORMATION_SCHEMA.TABLES`, kết quả có thể khác nhau.

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA IN ('appdb', 'billing')
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

Để kết luận sự khác biệt, phải so sánh quyền hiệu lực của hai session, gồm user/host, role active và các quyền được cấp trực tiếp. Một kết quả rỗng không đủ để kết luận schema hoặc bảng không tồn tại.

## 8. Các giới hạn và lưu ý bảo mật

### 8.1. Metadata vẫn có thể tiết lộ thông tin nhạy cảm

Tên database, tên bảng, tên cột, index, routine và view definition có thể tiết lộ kiến trúc nghiệp vụ. Tên cột như `salary`, `customer_token` hoặc `payment_reference` có thể hé lộ loại dữ liệu hệ thống lưu trữ dù người xem không có quyền đọc giá trị.

Vì vậy, quyền metadata cũng cần tuân theo nguyên tắc least privilege. Chỉ cấp khả năng kiểm kê toàn schema hoặc xem routine definitions cho nhóm có nhiệm vụ tương ứng.

### 8.2. Ẩn metadata không thay thế phân quyền dữ liệu

Không thể dùng việc đối tượng không xuất hiện trong `SHOW TABLES` làm cơ chế bảo vệ dữ liệu. Bảo vệ dữ liệu phải dựa vào quyền `SELECT`, `INSERT`, `UPDATE`, `DELETE`, quyền thực thi routine, view security context và các cơ chế kiểm soát phù hợp.

Nếu account có quyền đọc một view dùng `SQL SECURITY DEFINER`, nó có thể truy vấn dữ liệu mà definer được phép truy cập, dù account gọi view không có quyền trực tiếp trên bảng nền. Đây là một cơ chế ủy quyền có chủ đích; cần review định nghĩa view và quyền của definer.

### 8.3. Không truy cập trực tiếp file hoặc bảng hệ thống để lách quyền

Từ MySQL 8.0, data dictionary được quản lý theo cơ chế transactional. Ứng dụng nên dùng `INFORMATION_SCHEMA`, `SHOW` và các giao diện được công bố thay vì phụ thuộc vào file metadata cũ hoặc sửa trực tiếp bảng hệ thống.

Không cấp quyền đọc rộng trên schema `mysql` chỉ để một công cụ lấy metadata. Hãy xác định giao diện metadata phù hợp và cấp đúng quyền trên giao diện đó.

### 8.4. Metadata có thể thay đổi giữa hai lần kiểm tra

Metadata là ảnh chụp tại thời điểm truy vấn. Một migration có thể tạo hoặc xóa bảng giữa hai lần đọc; quyền cũng có thể thay đổi khi role được cấp, thu hồi hoặc kích hoạt. Công cụ audit và migration nên ghi lại thời điểm kiểm tra, account, role và server version để kết quả có thể giải thích được.

Không nên dựa vào một lần kiểm tra metadata để đảm bảo schema không thay đổi trước khi chạy thao tác tiếp theo. Các thao tác DDL cần được điều phối và kiểm tra lại trong quá trình triển khai.

## 9. Quy trình kiểm kê metadata an toàn

Khi xây dựng công cụ audit hoặc schema discovery, hãy thực hiện theo trình tự:

1. **Xác định mục đích.** Công cụ cần liệt kê schema, so sánh bảng/cột/index, xem view definition hay quan sát session?
2. **Chọn account riêng.** Không dùng tài khoản root hoặc account runtime cho công cụ audit.
3. **Cấp quyền tối thiểu.** Cấp quyền trên schema/bảng cần kiểm tra; bổ sung `SHOW VIEW`, `SHOW_ROUTINE`, `SHOW DATABASES` hoặc `PROCESS` chỉ khi tác vụ yêu cầu.
4. **Ghi nhận danh tính session.** Lưu `USER()`, `CURRENT_USER()`, role active và phiên bản server.
5. **Truy vấn metadata chính thức.** Dùng `INFORMATION_SCHEMA` và các lệnh `SHOW` phù hợp.
6. **Diễn giải kết quả theo quyền.** Không coi hàng bị ẩn là bằng chứng đối tượng không tồn tại.
7. **Kiểm tra quyền hiệu lực.** Dùng `SHOW GRANTS`, xác minh role và phạm vi quyền.
8. **Bảo vệ kết quả audit.** Metadata, view definition và câu SQL trong process list có thể chứa thông tin nhạy cảm; giới hạn người truy cập báo cáo.
9. **Lặp lại sau migration.** So sánh metadata trước/sau triển khai bằng account có cùng phạm vi quyền để tránh sai lệch do khác account.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `SHOW DATABASES` luôn liệt kê mọi schema | Mặc định kết quả bị giới hạn theo quyền; `SHOW DATABASES` toàn cục mở rộng khả năng liệt kê |
| Không thấy bảng nghĩa là bảng không tồn tại | Có thể account không có quyền nhìn thấy đối tượng |
| Thấy tên view là xem được định nghĩa view | `SHOW VIEW` có thể cần thiết để xem định nghĩa |
| Có `SELECT` trên view là có quyền trên bảng nền | View có thể dùng `SQL SECURITY DEFINER`; quyền trên view và bảng nền khác nhau |
| `INFORMATION_SCHEMA` luôn chứa toàn bộ metadata | Các hàng và một số cột metadata bị lọc theo quyền |
| Không có `PROCESS` vẫn xem được session của mọi user | Thông thường chỉ thấy thread của chính mình; `PROCESS` mở rộng khả năng quan sát |
| Metadata permission đồng nghĩa quyền đọc dữ liệu | Metadata visibility và quyền thao tác dữ liệu là hai lớp khác nhau |
| Công cụ audit chạy bằng account runtime là đủ | Account runtime thường không có quyền kiểm kê schema hoặc xem định nghĩa cần thiết |

## 11. Ghi nhớ

- Metadata mô tả schema, bảng, cột, index, constraint, view, routine và hoạt động server.
- `SHOW` và `INFORMATION_SCHEMA` lọc đối tượng theo quyền của account; kết quả rỗng không chứng minh đối tượng không tồn tại.
- `SHOW DATABASES` toàn cục cho phép liệt kê mọi schema; chỉ cấp khi có nhu cầu quản trị hoặc audit.
- `SHOW VIEW` kiểm soát việc xem định nghĩa view; routine definition có thể cần `SHOW_ROUTINE` hoặc quyền liên quan tùy phiên bản.
- `PROCESS` mở rộng khả năng nhìn thấy connection của user khác; cần giới hạn vì process list có thể chứa SQL và thông tin vận hành.
- Performance Schema và sys là giao diện chẩn đoán, cũng chịu kiểm soát quyền.
- Tách account runtime, migration và DBA/auditor; cấp quyền metadata tối thiểu theo nhiệm vụ.
- Không dùng metadata bị ẩn làm cơ chế bảo vệ dữ liệu; luôn phân quyền dữ liệu và view/routine đúng cách.

Khi hiểu rõ quyền nhìn thấy metadata, bạn có thể xây dựng công cụ schema discovery và audit đáng tin cậy, giải thích đúng kết quả truy vấn metadata, đồng thời tránh cấp quyền rộng hơn nhu cầu của từng tài khoản MySQL.

