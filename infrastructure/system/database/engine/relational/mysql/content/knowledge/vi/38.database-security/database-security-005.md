# GRANT, REVOKE và quyền theo server/database/table/column/routine

Trong MySQL, đăng nhập thành công chỉ xác nhận danh tính của kết nối. Người dùng còn cần đúng quyền để đọc hoặc thay đổi dữ liệu, quản lý cấu trúc và gọi các stored routine. `GRANT` cấp quyền, `REVOKE` thu hồi quyền; phạm vi của quyền quyết định tài nguyên mà tài khoản có thể tác động.

Bài học này thuộc chương **Bảo mật** của module `DATABASE_MYSQL`. Nội dung đi từ quyền toàn server đến database, table, column và routine, sau đó kết hợp role để xây dựng cách phân quyền có thể kiểm tra và bảo trì. Các ví dụ dùng cú pháp MySQL 8.0 trở lên; một số quyền động và tính năng có thể khác theo phiên bản hoặc plugin đang cài.

Sau bài học, bạn có thể:

- Phân biệt tài khoản MySQL với quyền mà tài khoản được cấp.
- Chọn phạm vi quyền nhỏ nhất đáp ứng công việc.
- Cấp và thu hồi quyền bằng `GRANT` và `REVOKE`.
- Dùng role để gom quyền theo vai trò công việc.
- Kiểm tra quyền hiệu lực và tìm nguyên nhân cấp quyền quá rộng.
- Đánh giá rủi ro khi cấp quyền gọi stored procedure hoặc function.

## 1. Tài khoản và quyền là hai lớp khác nhau

MySQL nhận diện một tài khoản bằng cặp **user và host**, thường viết như sau:

```sql
'app_reader'@'10.20.%'
```

Phần `app_reader` là tên tài khoản; phần `10.20.%` giới hạn nguồn kết nối theo quy tắc khớp host của MySQL. Hai tài khoản có cùng tên user nhưng host khác nhau là hai tài khoản riêng, có thể có mật khẩu và quyền khác nhau. Vì vậy, khi cấp hoặc thu hồi quyền, phải dùng đúng cặp user/host.

Tạo tài khoản trước, rồi mới cấp quyền:

```sql
CREATE USER 'app_reader'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
```

Mật khẩu trong ví dụ chỉ là chỗ giữ chỗ; khi triển khai, hãy dùng bí mật mạnh, duy nhất và quy trình quản lý secret của hệ thống. Giới hạn host ở địa chỉ hoặc dải mạng thực sự cần thiết. Tránh dùng host `%` nếu ứng dụng không cần kết nối từ mọi nguồn.

Không dùng tài khoản `root` cho ứng dụng. Tạo tài khoản riêng cho ứng dụng, báo cáo, sao lưu, migration và vận hành. Mỗi tài khoản chỉ nên có quyền cần cho đúng nhiệm vụ.

Hai hàm thường hữu ích khi kiểm tra danh tính kết nối:

```sql
SELECT USER(), CURRENT_USER();
```

- `USER()` cho biết tên user mà client gửi cùng nguồn kết nối mà server nhận diện.
- `CURRENT_USER()` cho biết tài khoản MySQL thực tế được dùng để kiểm tra quyền. Trong stored routine chạy với quyền DEFINER, giá trị này có thể là tài khoản DEFINER.

Nếu quyền được cấp cho `'app_reader'@'localhost'` nhưng kết nối đang khớp với `'app_reader'@'10.20.%'`, kết quả có thể khác mong đợi. Hãy kiểm tra `CURRENT_USER()` trước khi kết luận rằng `GRANT` không có tác dụng.

## 2. Hiểu năm phạm vi quyền

MySQL cho phép cấp quyền ở nhiều mức. Cú pháp `ON` trong câu lệnh `GRANT` xác định phạm vi đó.

| Phạm vi | Cú pháp đối tượng | Ý nghĩa |
|---|---|---|
| Toàn server | `*.*` | Quyền áp dụng trên toàn instance MySQL; phạm vi ảnh hưởng lớn nhất. |
| Database | `sales.*` | Quyền áp dụng cho các đối tượng trong database `sales`, gồm cả đối tượng được tạo sau này. |
| Table | `sales.orders` | Quyền áp dụng cho một bảng hoặc view cụ thể. |
| Column | `sales.orders (order_id, status)` | Chỉ áp dụng cho các cột được liệt kê; phù hợp khi cần giới hạn dữ liệu có thể đọc hoặc sửa. |
| Routine | `PROCEDURE sales.close_order` hoặc `FUNCTION sales.calculate_tax` | Quyền áp dụng cho một stored procedure hoặc stored function cụ thể. |

Phạm vi càng rộng thì hậu quả của việc cấp nhầm quyền càng lớn. Ví dụ, `SELECT ON *.*` cho phép đọc dữ liệu trên toàn server; `SELECT ON sales.*` cho phép đọc mọi bảng trong database `sales`; `SELECT ON sales.orders` chỉ cho phép đọc bảng `orders`.

Các quyền ở phạm vi rộng hơn có thể đóng góp vào quyền hiệu lực ở phạm vi hẹp hơn. Nếu một tài khoản đã có `SELECT ON *.*`, việc chỉ cấp thêm `SELECT ON sales.orders` không giới hạn tài khoản vào bảng đó: quyền toàn server vẫn cho phép đọc các bảng khác. Khi thiết kế quyền, phải xem toàn bộ các nguồn quyền của tài khoản, gồm quyền trực tiếp và role đang hoạt động.

### 2.1. Quyền ở mức server

Quyền toàn server thường dành cho quản trị viên hoặc tài khoản vận hành chuyên biệt. Một số ví dụ là `CREATE USER`, `PROCESS`, `RELOAD`, `SHUTDOWN`, `FILE` và các quyền động như `BACKUP_ADMIN` hoặc `CONNECTION_ADMIN`.

Ví dụ cấp quyền xem thông tin process:

```sql
GRANT PROCESS ON *.* TO 'ops_observer'@'10.20.%';
```

`PROCESS` có thể để lộ thông tin về hoạt động và truy vấn của các kết nối khác. Hãy cân nhắc dữ liệu mà người vận hành cần xem trước khi cấp quyền này. Các quyền như `FILE`, `SHUTDOWN`, `CREATE USER` hoặc quyền quản trị hệ thống có thể tạo ra tác động lớn và không nên nằm trong tài khoản ứng dụng thông thường.

### 2.2. Quyền ở mức database

Quyền database phù hợp khi một ứng dụng hoặc nhóm người dùng làm việc với nhiều bảng trong cùng một database.

```sql
GRANT SELECT, INSERT, UPDATE
ON sales.*
TO 'sales_app'@'10.20.%';
```

Tài khoản có thể đọc, thêm và cập nhật dữ liệu trong database `sales`. Câu lệnh không cấp `DELETE`, `DROP`, `ALTER` hay quyền quản trị khác. Việc chỉ cấp những thao tác thực sự cần thiết giúp hạn chế thiệt hại khi thông tin đăng nhập của ứng dụng bị lộ hoặc câu truy vấn bị lỗi.

Quyền database cũng áp dụng với các đối tượng được tạo trong database đó về sau. Vì vậy, nếu tài khoản chỉ cần làm việc với một vài bảng ổn định, cấp quyền database có thể rộng hơn yêu cầu.

### 2.3. Quyền ở mức table

Khi chỉ cần truy cập một bảng, cấp quyền trực tiếp trên bảng:

```sql
GRANT SELECT
ON sales.orders
TO 'order_reporter'@'10.20.%';
```

Tài khoản có thể đọc bảng `sales.orders` mà không được tự động đọc mọi bảng khác trong `sales`. Có thể cấp thêm thao tác riêng nếu công việc yêu cầu:

```sql
GRANT INSERT, UPDATE
ON sales.orders
TO 'order_processor'@'10.20.%';
```

Không cấp `DELETE`, `ALTER` hoặc `DROP` chỉ vì ứng dụng đang có quyền `INSERT` và `UPDATE`. Những thao tác đó có mục đích và rủi ro khác nhau.

### 2.4. Quyền ở mức column

Quyền column dùng khi một người hoặc một dịch vụ chỉ cần một tập con các cột. MySQL hỗ trợ quyền theo cột cho `SELECT`, `INSERT`, `UPDATE` và `REFERENCES`.

Ví dụ, nhân viên hỗ trợ chỉ cần mã đơn và trạng thái, không cần đọc địa chỉ hoặc thông tin thanh toán:

```sql
GRANT SELECT (order_id, status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

Nếu họ chỉ được đổi trạng thái đơn hàng:

```sql
GRANT UPDATE (status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

Quyền column không làm mất hiệu lực quyền rộng hơn đã có. Nếu tài khoản đồng thời có `SELECT ON sales.orders` hoặc `SELECT ON sales.*`, giới hạn hai cột ở trên không còn giới hạn được dữ liệu đọc. Khi điều tra quyền column, hãy kiểm tra cả quyền global, database, table và role.

### 2.5. Quyền trên stored procedure và function

Stored routine có phạm vi cấp quyền riêng. Hai quyền thường gặp là:

- `EXECUTE`: cho phép gọi routine.
- `ALTER ROUTINE`: cho phép thay đổi hoặc xóa routine theo quyền MySQL tương ứng.

Ví dụ cấp quyền gọi procedure:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

Với function:

```sql
GRANT EXECUTE
ON FUNCTION sales.calculate_tax
TO 'checkout_app'@'10.20.%';
```

Quyền `CREATE ROUTINE` và `ALTER ROUTINE` cũng có thể được cấp ở phạm vi database khi cần quản lý vòng đời routine. Tách quyền triển khai routine khỏi quyền gọi routine: tài khoản ứng dụng thường chỉ cần `EXECUTE`, còn tài khoản migration hoặc người bảo trì mới cần quyền tạo và thay đổi.

## 3. Cấp quyền bằng GRANT

Cú pháp khái quát:

```sql
GRANT privilege_list
ON object
TO 'user'@'host'
[WITH GRANT OPTION];
```

`privilege_list` là một hoặc nhiều quyền được phép ở phạm vi đã chọn; `object` xác định phạm vi; `TO` chỉ rõ tài khoản nhận quyền.

Ví dụ đầy đủ cho tài khoản báo cáo:

```sql
CREATE USER 'report_user'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT
ON sales.orders
TO 'report_user'@'10.20.%';
```

Tài khoản chỉ được đọc bảng đơn hàng. Nếu yêu cầu thay đổi, hãy cấp đúng thao tác và đúng đối tượng thay vì mở rộng thành `ALL PRIVILEGES`.

### 3.1. Chọn quyền theo công việc

| Công việc | Quyền thường cần xem xét | Cần tránh cấp mặc định |
|---|---|---|
| Đọc báo cáo | `SELECT` trên bảng hoặc database báo cáo | `INSERT`, `UPDATE`, `DELETE`, `DROP` |
| Ghi dữ liệu ứng dụng | `SELECT`, `INSERT`, `UPDATE` trên bảng cần thiết | `ALTER`, `DROP`, `CREATE USER`, `FILE` |
| Chạy tác vụ đóng đơn | `EXECUTE` trên procedure được chỉ định | Quyền sửa routine hoặc quyền toàn server |
| Triển khai schema | Quyền DDL cần cho migration trên database đích | Quyền quản trị toàn server nếu không cần |
| Theo dõi vận hành | Các quyền giám sát cụ thể như `PROCESS` khi có lý do | Quyền thay đổi dữ liệu hoặc tắt server |

Đây là điểm bắt đầu để phân tích, không phải danh sách cấp quyền tự động. Hãy kiểm tra các câu SQL thực tế mà từng thành phần chạy; một số câu lệnh cần nhiều quyền hơn tên thao tác chính gợi ý.

### 3.2. GRANT OPTION

`WITH GRANT OPTION` cho phép người nhận cấp tiếp các quyền mà họ có thể cấp ở phạm vi tương ứng. Ví dụ:

```sql
GRANT SELECT
ON sales.*
TO 'team_lead'@'10.20.%'
WITH GRANT OPTION;
```

`team_lead` có thể cấp tiếp quyền `SELECT` được ủy quyền trong phạm vi đó. Đây là quyền ủy quyền, không chỉ là quyền đọc dữ liệu. Nếu cấp cho nhiều tài khoản, việc truy vết ai đã cấp quyền cho ai sẽ phức tạp hơn.

`ALL PRIVILEGES` không tự động bao gồm `GRANT OPTION`. Nếu một tài khoản cần quyền cấp tiếp, hãy quyết định và ghi rõ việc đó bằng `WITH GRANT OPTION`. Các quyền động cũng được quản lý riêng; đừng giả định `ALL PRIVILEGES` đã bao gồm mọi quyền do server hoặc plugin cung cấp.

## 4. Thu hồi quyền bằng REVOKE

Cú pháp cơ bản:

```sql
REVOKE privilege_list
ON object
FROM 'user'@'host';
```

Ví dụ thu hồi quyền cập nhật nhưng vẫn giữ quyền đọc:

```sql
REVOKE UPDATE
ON sales.orders
FROM 'order_processor'@'10.20.%';
```

Thu hồi quyền column:

```sql
REVOKE UPDATE (status)
ON sales.orders
FROM 'support_agent'@'10.20.%';
```

Thu hồi quyền gọi routine:

```sql
REVOKE EXECUTE
ON PROCEDURE sales.close_order
FROM 'batch_runner'@'10.20.%';
```

Thu hồi quyền ủy quyền mà vẫn giữ quyền sử dụng:

```sql
REVOKE GRANT OPTION FOR SELECT
ON sales.*
FROM 'team_lead'@'10.20.%';
```

Trong ví dụ cuối, `team_lead` mất khả năng cấp tiếp quyền `SELECT` tương ứng; quyền `SELECT` của chính tài khoản vẫn được giữ nếu không có lệnh thu hồi riêng.

Muốn thu hồi toàn bộ quyền và quyền ủy quyền trực tiếp của một tài khoản:

```sql
REVOKE ALL PRIVILEGES, GRANT OPTION
FROM 'report_user'@'10.20.%';
```

Lệnh này không xóa tài khoản. Nếu tài khoản không còn cần tồn tại, quản trị viên có thể xem xét `DROP USER` sau khi kiểm tra các dịch vụ còn sử dụng tài khoản đó.

### 4.1. REVOKE không phải lúc nào cũng làm mất quyền hiệu lực

MySQL tổng hợp quyền từ nhiều nguồn. Nếu một tài khoản có `SELECT` toàn server, thu hồi `SELECT` ở mức database không làm mất quyền được cấp ở mức global. Tương tự, thu hồi quyền column không giới hạn được tài khoản đang có quyền table hoặc database rộng hơn.

Ví dụ:

```sql
GRANT SELECT ON *.* TO 'auditor'@'10.20.%';
REVOKE SELECT ON sales.* FROM 'auditor'@'10.20.%';
```

Khi tính năng partial revoke không được bật, quyền `SELECT` toàn server vẫn cho phép tài khoản đọc database `sales`. Vì vậy, khi một `REVOKE` dường như không có tác dụng, hãy kiểm tra mọi cấp quyền và role đang hoạt động trước khi sửa tiếp.

MySQL không cung cấp một cơ chế `DENY` tổng quát tương đương một số hệ quản trị khác. Cách thiết kế thông thường là không cấp quyền rộng ngay từ đầu, rồi chỉ cấp đúng quyền cần thiết.

## 5. Dùng role để quản lý quyền theo vai trò

Khi nhiều tài khoản làm cùng công việc, cấp từng quyền riêng cho từng tài khoản dễ gây sai lệch. Role gom quyền thành một vai trò có tên; sau đó cấp role cho các tài khoản cần vai trò đó.

Ví dụ tạo role đọc báo cáo:

```sql
CREATE ROLE 'sales_reader';

GRANT SELECT
ON sales.orders
TO 'sales_reader';

GRANT 'sales_reader'
TO 'analyst'@'10.20.%';

SET DEFAULT ROLE 'sales_reader'
TO 'analyst'@'10.20.%';
```

Role `sales_reader` nắm quyền đọc bảng `sales.orders`. Tài khoản `analyst` được gán role và role được đặt làm mặc định để tự kích hoạt khi tài khoản đăng nhập.

Trong phiên hiện tại, có thể kiểm tra hoặc thay đổi role đang hoạt động:

```sql
SELECT CURRENT_ROLE();
SET ROLE DEFAULT;
SET ROLE NONE;
SET ROLE ALL;
```

- `CURRENT_ROLE()` cho biết các role đang hoạt động trong phiên.
- `SET ROLE DEFAULT` kích hoạt các role mặc định.
- `SET ROLE NONE` tắt các role trong phiên hiện tại.
- `SET ROLE ALL` kích hoạt tất cả role đã được cấp và có thể kích hoạt.

Để thu hồi role:

```sql
REVOKE 'sales_reader'
FROM 'analyst'@'10.20.%';
```

`WITH ADMIN OPTION` trên câu lệnh cấp role cho phép người nhận quản trị việc cấp role đó cho người khác. Phân biệt rõ:

- `WITH GRANT OPTION` áp dụng cho quyền trên đối tượng dữ liệu.
- `WITH ADMIN OPTION` áp dụng cho việc quản trị role.

Nên đặt tên role theo nhiệm vụ, ví dụ `sales_reader`, `sales_writer`, `routine_executor` hoặc `schema_migrator`. Không nên tạo role theo tên cá nhân vì sẽ khó duy trì khi nhân sự hoặc trách nhiệm thay đổi.

## 6. Quyền động và quyền quản trị chuyên biệt

Ngoài các quyền tĩnh quen thuộc như `SELECT`, `INSERT` và `UPDATE`, MySQL còn có **dynamic privileges**. Chúng được bổ sung theo phiên bản server hoặc plugin và thường cấp ở mức global. Ví dụ có thể gồm `BACKUP_ADMIN`, `CONNECTION_ADMIN`, `ROLE_ADMIN`, `SYSTEM_USER` và `BINLOG_ADMIN`.

Ví dụ cấp quyền sao lưu chuyên biệt:

```sql
GRANT BACKUP_ADMIN
ON *.*
TO 'backup_operator'@'10.20.%';
```

Tên và yêu cầu của quyền động phụ thuộc phiên bản MySQL và thành phần đã cài. Trước khi cấp, hãy kiểm tra danh sách quyền mà instance hỗ trợ và tài liệu của đúng phiên bản hoặc plugin. Không dùng một danh sách quyền động từ máy chủ khác làm chuẩn tuyệt đối.

Các quyền nhạy cảm như `SYSTEM_USER`, `ROLE_ADMIN`, `CONNECTION_ADMIN` hoặc `BINLOG_ADMIN` có thể cho phép tác động đến tài khoản, kết nối, role hoặc binary log. Hãy cấp theo nhiệm vụ, tách tài khoản vận hành khỏi tài khoản ứng dụng và ghi nhận lý do cấp quyền.

## 7. Partial revoke: ngoại lệ có kiểm soát

Từ MySQL 8.0.16, tính năng `partial_revokes` cho phép giới hạn một số quyền đã được cấp ở mức global đối với một database cụ thể. Đây là ngoại lệ quan trọng cho mô hình quyền tổng hợp.

Ví dụ, một tài khoản có quyền `SELECT` toàn server nhưng cần bị giới hạn khỏi database `payroll`. Khi `partial_revokes` được bật, quản trị viên có thể thực hiện:

```sql
REVOKE SELECT
ON payroll.*
FROM 'auditor'@'10.20.%';
```

Tùy chọn này phải được cấu hình và kiểm tra theo phiên bản MySQL đang chạy; giá trị mặc định thường là tắt. Quản trị viên có thể kiểm tra trạng thái:

```sql
SHOW VARIABLES LIKE 'partial_revokes';
```

Partial revoke có phạm vi và quy tắc riêng, không phải một lệnh `DENY` tổng quát cho mọi cấp quyền. Nó cũng làm mô hình quyền khó đọc hơn nếu lạm dụng. Với hệ thống mới, thiết kế tài khoản và role chỉ có quyền cần thiết thường dễ kiểm tra hơn việc cấp global rộng rồi tạo nhiều ngoại lệ.

## 8. Rủi ro bảo mật của stored routine

Quyền `EXECUTE` chỉ cho biết tài khoản được gọi routine. Quyền mà routine sử dụng khi chạy còn phụ thuộc vào chế độ bảo mật SQL của routine.

### 8.1. SQL SECURITY DEFINER

`SQL SECURITY DEFINER` chạy routine với quyền của tài khoản được khai báo là `DEFINER`. Đây là chế độ mặc định nếu không chỉ định chế độ khác. Người gọi chỉ cần quyền `EXECUTE` trên routine; routine có thể thao tác dữ liệu bằng quyền của DEFINER.

Ví dụ minh họa:

```sql
DELIMITER //

CREATE DEFINER = 'routine_owner'@'localhost'
PROCEDURE sales.close_order(IN p_order_id BIGINT)
SQL SECURITY DEFINER
BEGIN
  UPDATE sales.orders
  SET status = 'closed'
  WHERE order_id = p_order_id;
END//

DELIMITER ;
```

Tài khoản `routine_owner` cần quyền phù hợp để cập nhật bảng. Tài khoản chạy batch chỉ cần:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

Cách này có thể hữu ích khi muốn cung cấp một thao tác nghiệp vụ được kiểm soát mà không cấp quyền cập nhật bảng trực tiếp cho ứng dụng. Tuy nhiên, routine trở thành một ranh giới bảo mật: nếu routine nhận đầu vào không an toàn, cho phép cập nhật dữ liệu tùy ý hoặc thực thi SQL động thiếu kiểm soát, người gọi có thể khai thác quyền cao hơn của DEFINER.

Hãy dùng một tài khoản DEFINER chuyên biệt, quyền hẹp, không dùng `root`; kiểm tra kỹ tham số và logic routine; rà soát routine khi quyền của DEFINER thay đổi. Cũng cần quản lý vòng đời tài khoản DEFINER để routine không bị phụ thuộc vào một tài khoản cá nhân có thể bị xóa hoặc đổi quyền ngoài dự kiến.

### 8.2. SQL SECURITY INVOKER

`SQL SECURITY INVOKER` chạy routine bằng quyền của người gọi. Ví dụ:

```sql
CREATE PROCEDURE sales.read_order(IN p_order_id BIGINT)
SQL SECURITY INVOKER
SELECT order_id, status
FROM sales.orders
WHERE order_id = p_order_id;
```

Với chế độ này, người gọi phải có các quyền cần thiết trên đối tượng mà routine truy cập, ngoài quyền `EXECUTE` theo yêu cầu của MySQL. Đây là lựa chọn phù hợp khi routine không cần nâng quyền của người gọi.

Khi review một routine, hãy kiểm tra ít nhất: ai là DEFINER, routine dùng `SQL SECURITY` nào, người gọi được cấp `EXECUTE` cho đối tượng nào, và câu lệnh bên trong có thể tác động đến những dữ liệu nào.

## 9. Kiểm tra quyền và điều tra lỗi

Sau khi cấp hoặc thu hồi quyền, hãy đọc lại kết quả từ server. Một số câu lệnh kiểm tra hữu ích:

```sql
-- Xem quyền của tài khoản cụ thể
SHOW GRANTS FOR 'report_user'@'10.20.%';

-- Xem quyền của tài khoản đang đăng nhập
SHOW GRANTS FOR CURRENT_USER;

-- Xem danh tính được dùng để kiểm tra quyền
SELECT USER(), CURRENT_USER(), CURRENT_ROLE();

-- Xem trạng thái partial revoke
SHOW VARIABLES LIKE 'partial_revokes';
```

`SHOW GRANTS` là điểm bắt đầu tốt để rà soát quyền trực tiếp và role được gán. Khi cần xác nhận hành vi thực tế, hãy kết nối bằng chính tài khoản ứng dụng hoặc tài khoản thử nghiệm đó rồi chạy một truy vấn đọc/ghi đại diện. Kiểm tra từ phiên quản trị viên không chứng minh rằng tài khoản ứng dụng có cùng quyền.

Các lệnh `GRANT` và `REVOKE` cập nhật quyền qua cơ chế quản lý của MySQL và có hiệu lực mà không cần chạy `FLUSH PRIVILEGES`. Không sửa trực tiếp các bảng cấp quyền trong schema `mysql`; thao tác trực tiếp có thể gây trạng thái không nhất quán và khó kiểm soát.

### 9.1. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `Access denied` khi kết nối | Mật khẩu sai, host không khớp hoặc tài khoản chưa tồn tại | Kiểm tra chính xác cặp `'user'@'host'`, chính sách xác thực và `CURRENT_USER()` sau khi kết nối được. |
| `SELECT command denied` | Thiếu `SELECT` trên database, table hoặc column cần đọc | Dùng `SHOW GRANTS`; xác định đúng database, bảng và các cột truy vấn sử dụng. |
| `UPDATE command denied` | Thiếu `UPDATE` ở phạm vi phù hợp hoặc thiếu quyền cần cho các phần khác của câu lệnh | Kiểm tra cột được cập nhật, điều kiện lọc và các quyền cần thiết cho câu SQL thực tế. |
| Đã cấp role nhưng ứng dụng vẫn bị từ chối | Role chưa được đặt mặc định hoặc chưa hoạt động trong phiên | Kiểm tra `CURRENT_ROLE()` và cấu hình `SET DEFAULT ROLE`. |
| Đã REVOKE nhưng người dùng vẫn đọc được | Quyền vẫn đến từ global grant, table grant, role khác hoặc tài khoản host khác | Kiểm tra toàn bộ `SHOW GRANTS`, role hoạt động và `CURRENT_USER()`. |
| Gọi procedure bị từ chối | Thiếu `EXECUTE`, gọi nhầm routine hoặc routine/DEFINER có vấn đề | Kiểm tra quyền routine, tên routine, DEFINER và `SQL SECURITY`. |
| Người dùng có thể cấp quyền cho người khác | Đã cấp `GRANT OPTION` hoặc role có `ADMIN OPTION` | Kiểm tra `SHOW GRANTS`, thu hồi đúng quyền ủy quyền nếu không cần. |

## 10. Quy trình phân quyền có thể áp dụng

Một quy trình thực tế nên đi theo thứ tự sau:

1. **Liệt kê nhiệm vụ.** Xác định tài khoản dùng để làm gì: đọc báo cáo, xử lý giao dịch, chạy routine, migration hay vận hành.
2. **Xác định đối tượng.** Ghi rõ database, table, column hoặc routine mà nhiệm vụ cần truy cập.
3. **Chọn quyền tối thiểu.** Chỉ chọn `SELECT`, `INSERT`, `UPDATE`, `EXECUTE` hoặc quyền khác mà câu lệnh thực sự cần.
4. **Chọn phạm vi hẹp nhất.** Ưu tiên routine, column hoặc table khi phù hợp; chỉ dùng database/global khi nhiệm vụ đòi hỏi.
5. **Dùng role cho nhóm nhiệm vụ.** Cấp quyền vào role rồi gán role cho tài khoản; cấu hình role mặc định nếu ứng dụng cần tự kích hoạt.
6. **Kiểm tra quyền hiệu lực.** Đọc `SHOW GRANTS`, `CURRENT_USER()` và `CURRENT_ROLE()`; tìm các quyền rộng hơn có thể làm mất tác dụng của giới hạn hẹp.
7. **Thử bằng tài khoản thực tế.** Kiểm tra các thao tác được phép và bị từ chối trong môi trường phù hợp.
8. **Rà soát định kỳ.** Thu hồi quyền không còn cần, tài khoản không còn dùng và quyền ủy quyền không có lý do rõ ràng.

### 10.1. Ví dụ thiết kế role cho ứng dụng bán hàng

Giả sử hệ thống có ba nhiệm vụ: nhân viên phân tích đọc đơn hàng, dịch vụ xử lý đơn cập nhật đơn hàng, và batch job đóng đơn qua procedure. Có thể thiết kế như sau:

```sql
CREATE ROLE 'sales_reader';
CREATE ROLE 'sales_order_writer';
CREATE ROLE 'sales_close_executor';

GRANT SELECT
ON sales.orders
TO 'sales_reader';

GRANT SELECT, INSERT, UPDATE
ON sales.orders
TO 'sales_order_writer';

GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'sales_close_executor';

CREATE USER 'analyst'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
CREATE USER 'order_api'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';
CREATE USER 'batch_runner'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT 'sales_reader' TO 'analyst'@'10.20.%';
GRANT 'sales_order_writer' TO 'order_api'@'10.20.%';
GRANT 'sales_close_executor' TO 'batch_runner'@'10.20.%';

SET DEFAULT ROLE 'sales_reader' TO 'analyst'@'10.20.%';
SET DEFAULT ROLE 'sales_order_writer' TO 'order_api'@'10.20.%';
SET DEFAULT ROLE 'sales_close_executor' TO 'batch_runner'@'10.20.%';
```

Thiết kế này giúp phân biệt người đọc dữ liệu, dịch vụ ghi dữ liệu và tác vụ chỉ được gọi procedure. Nếu `order_api` không cần đọc toàn bộ cột, có thể tách quyền đọc theo column hoặc cung cấp routine chuyên biệt; trước khi làm vậy, cần xác nhận tài khoản không có quyền đọc rộng hơn từ role hay grant khác.

Trong môi trường production, nên dùng tài khoản migration riêng để thay đổi schema. Ứng dụng đang chạy không nên giữ quyền `ALTER`, `DROP` hoặc `CREATE USER` chỉ để thuận tiện cho việc triển khai.

## 11. Bài tập thực hành

### Bài 1: Tài khoản chỉ đọc một bảng

Tạo tài khoản `inventory_viewer` từ host `10.30.%` và chỉ cho phép đọc bảng `warehouse.stock`.

```sql
CREATE USER 'inventory_viewer'@'10.30.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT
ON warehouse.stock
TO 'inventory_viewer'@'10.30.%';

SHOW GRANTS FOR 'inventory_viewer'@'10.30.%';
```

Kiểm tra bằng tài khoản này: đọc `warehouse.stock` phải thành công; đọc bảng khác và cập nhật `warehouse.stock` phải bị từ chối, miễn là tài khoản không nhận thêm quyền từ nguồn khác.

### Bài 2: Giới hạn cột được xem

Một nhân viên hỗ trợ chỉ được xem `order_id` và `status` trong `sales.orders`:

```sql
GRANT SELECT (order_id, status)
ON sales.orders
TO 'support_agent'@'10.20.%';
```

Thử truy vấn hai cột được cấp và một cột nhạy cảm khác. Nếu cột nhạy cảm vẫn đọc được, kiểm tra xem tài khoản có quyền `SELECT` ở mức table, database, global hoặc từ role nào không.

### Bài 3: Chỉ cho phép gọi procedure

Batch job được gọi `sales.close_order` nhưng không được cập nhật trực tiếp bảng `sales.orders`:

```sql
GRANT EXECUTE
ON PROCEDURE sales.close_order
TO 'batch_runner'@'10.20.%';
```

Kiểm tra `SQL SECURITY` và DEFINER của procedure. Với `SQL SECURITY DEFINER`, đánh giá quyền của DEFINER và logic bên trong routine; với `SQL SECURITY INVOKER`, kiểm tra quyền mà batch job cần trên các đối tượng được truy cập.

### Bài 4: Thu hồi quyền ủy quyền

Một trưởng nhóm vẫn cần đọc `sales.*` nhưng không còn được cấp tiếp quyền cho người khác:

```sql
REVOKE GRANT OPTION FOR SELECT
ON sales.*
FROM 'team_lead'@'10.20.%';

SHOW GRANTS FOR 'team_lead'@'10.20.%';
```

Xác nhận quyền đọc vẫn còn và quyền ủy quyền đã bị thu hồi. Nếu kết quả không đúng, kiểm tra các grant và role khác.

## 12. Checklist trước khi đưa phân quyền vào production

- Tài khoản có tên và host khớp với nguồn kết nối dự kiến.
- Không dùng `root` hoặc tài khoản quản trị cho ứng dụng.
- Mỗi tài khoản phục vụ một nhiệm vụ rõ ràng.
- Phạm vi cấp quyền là nhỏ nhất đáp ứng nhiệm vụ.
- Không cấp `ALL PRIVILEGES`, `GRANT OPTION` hoặc quyền động nhạy cảm theo thói quen.
- Role cần thiết đã được gán và kích hoạt mặc định đúng cách.
- Quyền của DEFINER và chế độ `SQL SECURITY` của routine đã được review.
- `SHOW GRANTS`, `CURRENT_USER()` và `CURRENT_ROLE()` đã được kiểm tra.
- Đã thử cả thao tác được phép và thao tác phải bị từ chối bằng tài khoản thực tế.
- Có quy trình thu hồi quyền khi ứng dụng, nhân sự hoặc nhiệm vụ kết thúc.

Phân quyền tốt giúp giảm phạm vi ảnh hưởng của lỗi ứng dụng, truy vấn ngoài dự kiến và thông tin đăng nhập bị lộ. Hãy xem quyền là một phần của thiết kế hệ thống: mô tả nhiệm vụ, chọn đúng đối tượng, cấp đúng thao tác, rồi kiểm chứng bằng chính tài khoản sẽ chạy trong môi trường thật.
