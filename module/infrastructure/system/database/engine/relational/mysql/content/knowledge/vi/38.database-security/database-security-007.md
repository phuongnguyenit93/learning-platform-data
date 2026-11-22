# Role, default role và quyền có hiệu lực trong phiên

Trong MySQL, **role** là một tập hợp quyền được đặt tên. Quản trị viên có thể cấp role cho nhiều tài khoản, bật hoặc tắt role trong từng kết nối, và chọn role nào tự động có hiệu lực khi người dùng đăng nhập. Muốn kiểm tra một tài khoản có thực sự thực hiện được câu lệnh hay không, cần xem cả quyền cấp trực tiếp, role được cấp và trạng thái kích hoạt role của chính phiên kết nối.

Bài học sử dụng cú pháp MySQL 8.0 trở lên, phù hợp với MySQL 8.4. MySQL 5.7 chưa hỗ trợ hệ thống role như mô tả ở đây. Các ví dụ giả định người thực hiện lệnh quản trị có đủ quyền cần thiết; hãy thay mật khẩu mẫu bằng bí mật được quản lý an toàn trong môi trường thực tế.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt tài khoản, role, role được cấp, default role và role đang active.
- Tạo role, cấp quyền cho role rồi cấp role cho tài khoản hoặc role khác.
- Thiết lập default role cho lúc đăng nhập và thay đổi role trong phiên hiện tại bằng `SET ROLE`.
- Xác định các quyền có hiệu lực trong một phiên và giải thích vì sao một lệnh SQL bị từ chối.
- Thiết kế role theo nguyên tắc quyền tối thiểu, đồng thời xử lý an toàn role trong connection pool và stored program.

## 1. Mô hình role và quyền hiệu lực

Tài khoản MySQL có dạng `'user_name'@'host_name'`. Phần `host_name` tham gia xác định tài khoản dùng để xác thực; cùng tên người dùng nhưng khác host có thể là hai tài khoản khác nhau. Role cũng có tên theo dạng user/host. Nếu bỏ phần host của role, MySQL mặc định host là `%`.

Role là một định danh chứa các quyền được cấp bằng `GRANT`. Ví dụ, `r_sales_read` có thể đại diện cho quyền đọc dữ liệu bán hàng, còn `r_sales_write` đại diện cho quyền ghi dữ liệu. Một role có thể được cấp cho tài khoản hoặc cho role khác, nhờ đó có thể xây dựng cấu trúc role lồng nhau. Role mới tạo bị khóa theo mặc định và không dùng để đăng nhập như tài khoản ứng dụng thông thường.

Cần phân biệt bốn trạng thái sau:

| Khái niệm | Ý nghĩa |
|---|---|
| Quyền trực tiếp | Quyền được `GRANT` thẳng cho tài khoản. Quyền này không phụ thuộc việc bật/tắt role. |
| Role được cấp | Role đã được cấp cho tài khoản hoặc được thừa hưởng qua role khác. Việc được cấp chưa đồng nghĩa role đang active. |
| Default role | Các role được chọn để tự động active khi tài khoản đăng nhập thành công. |
| Active role | Các role đang có hiệu lực trong phiên kết nối hiện tại. Quyền của chúng tham gia kiểm tra truy cập. |

Có thể hình dung tập quyền được xét trong một phiên như sau:

```text
Quyền hiệu lực của phiên
  = quyền cấp trực tiếp cho tài khoản
  + quyền từ các role đang active
  + quyền từ role được lồng bên trong các role active
```

Role nằm trong cấu hình `mandatory_roles` được MySQL xem như đã cấp cho mọi tài khoản. Những role này vẫn tuân theo cơ chế kích hoạt role: chúng chỉ có hiệu lực khi được active theo default role hoặc theo cấu hình tự động kích hoạt tất cả role. `SET ROLE` chỉ thay đổi tập role active; quyền cấp trực tiếp cho tài khoản vẫn còn nguyên.

## 2. Tạo role và cấp quyền

Giả sử ứng dụng dùng cơ sở dữ liệu `sales_db`. Tài khoản báo cáo chỉ cần đọc dữ liệu; tài khoản xử lý đơn hàng cần đọc và cập nhật một số bảng. Ta gom quyền theo nhiệm vụ thay vì lặp lại danh sách quyền trên từng tài khoản.

```sql
-- Tạo hai role theo nhiệm vụ.
CREATE ROLE 'r_sales_read'@'%', 'r_sales_write'@'%';

-- Gắn quyền dữ liệu vào từng role.
GRANT SELECT ON sales_db.*
TO 'r_sales_read'@'%';

GRANT INSERT, UPDATE ON sales_db.orders
TO 'r_sales_write'@'%';

-- Tạo tài khoản dịch vụ.
CREATE USER 'svc_report'@'localhost'
IDENTIFIED BY 'replace_with_secret';

-- Cấp role cho tài khoản.
GRANT 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

Hai dạng `GRANT` có ý nghĩa khác nhau:

```sql
-- Có ON: cấp quyền trên đối tượng cho role hoặc tài khoản.
GRANT SELECT ON sales_db.* TO 'r_sales_read'@'%';

-- Không có ON: cấp role cho tài khoản hoặc role khác.
GRANT 'r_sales_read'@'%' TO 'svc_report'@'localhost';
```

Một câu lệnh `GRANT` không thể đồng thời trộn việc cấp quyền đối tượng và cấp role. Nếu cần làm cả hai, hãy dùng hai câu lệnh riêng. Để cấp role cho người khác, quản trị viên cần `ROLE_ADMIN` (hoặc quyền `SUPER` cũ); người được cấp role kèm `WITH ADMIN OPTION` cũng có thể chuyển tiếp role đó khi role đang active. `WITH ADMIN OPTION` là quyền quản lý việc cấp role, khác với `WITH GRANT OPTION` dùng để chuyển tiếp quyền đối tượng.

## 3. Default role và active role

### 3.1. Chọn role tự động active khi đăng nhập

`SET DEFAULT ROLE` lưu lựa chọn role mặc định cho một hoặc nhiều tài khoản. Ví dụ, tài khoản báo cáo luôn cần quyền đọc khi mở kết nối:

```sql
SET DEFAULT ROLE 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

Các dạng thường dùng:

```sql
-- Tự động active tất cả role được cấp cho tài khoản.
SET DEFAULT ROLE ALL TO 'svc_report'@'localhost';

-- Không tự động active role nào khi đăng nhập.
SET DEFAULT ROLE NONE TO 'svc_report'@'localhost';

-- Chỉ active danh sách role được nêu.
SET DEFAULT ROLE 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

Default role được áp dụng khi người dùng đăng nhập và xác thực thành công. Thay đổi default role không tự thay đổi tập role đang active trong các phiên đã mở. Trong một phiên hiện tại, có thể dùng `SET ROLE DEFAULT` để nạp lại lựa chọn mặc định mới.

### 3.2. Thay đổi role trong phiên hiện tại

`SET ROLE` thay đổi ngay tập role active của kết nối hiện tại:

| Câu lệnh | Tác dụng trong phiên |
|---|---|
| `SET ROLE DEFAULT` | Active các default role của tài khoản. |
| `SET ROLE NONE` | Tắt toàn bộ role; quyền cấp trực tiếp vẫn có hiệu lực. |
| `SET ROLE ALL` | Active tất cả role được cấp cho tài khoản, bao gồm role mandatory. |
| `SET ROLE 'r_sales_read'@'%'` | Chỉ active role được chỉ định; role đó phải được cấp cho tài khoản. |
| `SET ROLE ALL EXCEPT 'r_sales_write'@'%'` | Active tất cả role được cấp, ngoại trừ role được nêu. |

Ví dụ:

```sql
-- Xem role đang active.
SELECT CURRENT_ROLE();

-- Tạm tắt mọi role trong kết nối này.
SET ROLE NONE;
SELECT CURRENT_ROLE();

-- Chỉ bật quyền đọc.
SET ROLE 'r_sales_read'@'%';
SELECT CURRENT_ROLE();

-- Trở về các role mặc định của tài khoản.
SET ROLE DEFAULT;
SELECT CURRENT_ROLE();
```

Tên hai câu lệnh dễ bị nhầm:

- `SET DEFAULT ROLE ... TO user` **định nghĩa chính sách mặc định** của tài khoản cho lúc đăng nhập và cho lần gọi `SET ROLE DEFAULT` tiếp theo.
- `SET ROLE DEFAULT` **thay đổi trạng thái phiên hiện tại** để dùng chính sách mặc định đã định nghĩa.

### 3.3. Cấu hình tự động kích hoạt tất cả role

Biến toàn cục `activate_all_roles_on_login` điều khiển cách MySQL kích hoạt role lúc đăng nhập. Giá trị mặc định là `OFF`:

```sql
SHOW VARIABLES LIKE 'activate_all_roles_on_login';
```

- Khi `OFF`, MySQL kích hoạt các default role đã cấu hình bằng `SET DEFAULT ROLE`.
- Khi `ON`, MySQL kích hoạt tất cả role được cấp cho tài khoản lúc đăng nhập; lựa chọn này ghi đè danh sách default role.

Đây là cấu hình toàn máy chủ, không phải lựa chọn riêng cho một tài khoản. Không nên bật toàn cục chỉ để khắc phục một tài khoản thiếu quyền: việc đó có thể làm các role rộng hơn cùng active ở nhiều tài khoản. Hãy cấu hình default role theo đúng nhiệm vụ của từng tài khoản, trừ khi có chính sách vận hành rõ ràng yêu cầu kích hoạt tất cả role.

## 4. Kiểm tra quyền có hiệu lực

Không nên kết luận một tài khoản có quyền chỉ vì thấy role xuất hiện trong danh sách đã cấp. Hãy kiểm tra cả role đang active và quyền được cấp bên trong role.

```sql
-- Xác định tài khoản đang được MySQL dùng và role active của phiên.
SELECT CURRENT_USER() AS authenticated_account,
       CURRENT_ROLE() AS active_roles;

-- Xem các quyền và role được cấp trực tiếp cho tài khoản.
SHOW GRANTS FOR 'svc_report'@'localhost';

-- Mở rộng quyền từ role được chỉ định để kiểm tra quyền mà role mang lại.
SHOW GRANTS FOR 'svc_report'@'localhost'
USING 'r_sales_read'@'%';

-- Với tài khoản hiện tại, có thể dùng:
SHOW GRANTS;
```

`SHOW GRANTS FOR account` cho biết các quyền và role được cấp, nhưng thường chỉ liệt kê tên role mà chưa mở rộng toàn bộ quyền bên trong role. Mệnh đề `USING` yêu cầu MySQL hiển thị thêm các quyền đến từ role được nêu. Khi có nhiều role tham gia, hãy liệt kê đầy đủ các role cần kiểm tra.

`CURRENT_ROLE()` trả lời câu hỏi “role nào đang active trong phiên này?”. `SHOW GRANTS ... USING ...` trả lời câu hỏi “các role được chọn mang lại những quyền nào?”. Hai phép kiểm tra bổ sung cho nhau; không phép nào thay thế được việc thử câu lệnh trên đúng đối tượng cần truy cập.

## 5. Thực hành: chứng minh quyền thay đổi theo phiên

Sau khi hoàn tất phần tạo role ở mục 2 và đặt `r_sales_read` làm default role ở mục 3, đăng nhập bằng `svc_report` rồi thực hiện:

```sql
-- Kiểm tra role được kích hoạt lúc đăng nhập.
SELECT CURRENT_USER(), CURRENT_ROLE();

-- Nếu bảng tồn tại, truy vấn này phải thành công nhờ role đọc.
SELECT * FROM sales_db.orders LIMIT 5;

-- Tắt role: quyền đọc từ r_sales_read không còn hiệu lực.
SET ROLE NONE;
SELECT CURRENT_ROLE();

-- Nếu tài khoản không có SELECT trực tiếp, truy vấn sau bị từ chối.
SELECT * FROM sales_db.orders LIMIT 5;

-- Nạp lại default role trong chính kết nối hiện tại.
SET ROLE DEFAULT;
SELECT CURRENT_ROLE();

-- Quyền đọc từ default role lại có hiệu lực.
SELECT * FROM sales_db.orders LIMIT 5;
```

Kết quả mong đợi: truy vấn đọc thành công khi `r_sales_read` active; sau `SET ROLE NONE`, truy vấn bị từ chối nếu không có quyền `SELECT` trực tiếp hoặc từ nguồn quyền active khác; sau `SET ROLE DEFAULT`, truy vấn đọc thành công trở lại. Thông báo lỗi cụ thể có thể khác theo phiên bản và cấu hình, nhưng nguyên nhân cần kiểm tra là quyền `SELECT` không còn nằm trong tập quyền hiệu lực của phiên.

Thí nghiệm này cũng chỉ ra một điểm quan trọng: `SET ROLE NONE` không phải lệnh thu hồi quyền của tài khoản. Nếu quản trị viên đã cấp `SELECT` trực tiếp cho `svc_report`, truy vấn vẫn có thể thành công sau khi tắt role. Muốn loại bỏ quyền trực tiếp phải dùng `REVOKE` trên đúng tài khoản.

## 6. Role lồng nhau và mandatory role

### 6.1. Role lồng nhau

MySQL cho phép cấp role cho một role khác. Ví dụ, một role ứng dụng có thể tập hợp quyền đọc và quyền xem báo cáo:

```sql
CREATE ROLE 'r_sales_base'@'%', 'r_sales_analyst'@'%';
GRANT SELECT ON sales_db.* TO 'r_sales_base'@'%';
GRANT 'r_sales_base'@'%' TO 'r_sales_analyst'@'%';
GRANT 'r_sales_analyst'@'%' TO 'svc_report'@'localhost';

SET DEFAULT ROLE 'r_sales_analyst'@'%'
TO 'svc_report'@'localhost';
```

Role được cấp cho role khác tạo thành quan hệ kế thừa quyền. Khi tính quyền từ role đang active, cần tính đến các role được lồng trong cấu trúc đó. Role lồng nhau giúp tái sử dụng quyền, nhưng cây role quá sâu hoặc có nhiều nhánh sẽ khó kiểm toán. Hãy giữ cấu trúc đơn giản và kiểm tra bằng `SHOW GRANTS ... USING` với các role liên quan.

### 6.2. Mandatory role

Biến toàn cục `mandatory_roles` cho phép máy chủ xem một hoặc nhiều role là được cấp cho mọi tài khoản. Ví dụ cấu hình một role kiểm toán dùng chung:

```sql
-- Ví dụ quản trị; cần ROLE_ADMIN và quyền quản lý system variable.
SET PERSIST mandatory_roles = 'r_audit@%';
```

`SET PERSIST` áp dụng giá trị cho máy chủ đang chạy và lưu để dùng sau khi khởi động lại. Mandatory role vẫn phải được kích hoạt theo cơ chế role của MySQL: default role hoặc `activate_all_roles_on_login`. Role nằm trong `mandatory_roles` không thể bị thu hồi hoặc xóa bằng `REVOKE`/`DROP ROLE` khi vẫn còn được cấu hình là mandatory. Vì cấu hình này ảnh hưởng toàn máy chủ, chỉ dùng cho quyền nền tảng thật sự cần áp dụng rộng rãi; tránh đưa các quyền quản trị mạnh vào mandatory role.

## 7. Thu hồi role và quản lý vòng đời phiên

Có thể thu hồi role khỏi một tài khoản hoặc thu hồi một quyền khỏi role:

```sql
-- Tài khoản không còn được cấp role đọc.
REVOKE 'r_sales_read'@'%'
FROM 'svc_report'@'localhost';

-- Thu hồi quyền cập nhật khỏi role ghi.
REVOKE UPDATE ON sales_db.orders
FROM 'r_sales_write'@'%';
```

Thu hồi quyền từ một role ảnh hưởng đến mọi tài khoản đang sử dụng quyền qua role đó. Đây là cách thay đổi chính sách tập trung, nhưng cũng có thể gây tác động diện rộng. Trước khi thay đổi, hãy kiểm tra các tài khoản được cấp role và đánh giá ứng dụng phụ thuộc vào quyền đó. `DROP ROLE` xóa role và loại bỏ việc cấp role đó khỏi các tài khoản liên quan.

`SET ROLE` tác động ngay lên phiên hiện tại. Vì vậy, ứng dụng dùng connection pool cần quản lý trạng thái role giống như trạng thái transaction, biến session hay schema hiện hành. Nếu một request chạy `SET ROLE` rồi trả kết nối về pool mà không đặt lại trạng thái, request tiếp theo có thể nhận một kết nối với tập role active ngoài dự kiến. Nên thiết lập role cần thiết khi lấy kết nối và khôi phục trạng thái chuẩn trước khi trả kết nối về pool; không giả định mỗi request đều nhận một phiên đăng nhập mới.

Các lệnh quản lý tài khoản chuẩn như `GRANT` và `REVOKE` tự cập nhật thông tin quyền trong MySQL; không cần chạy `FLUSH PRIVILEGES` sau các lệnh này. `FLUSH PRIVILEGES` chủ yếu liên quan đến trường hợp sửa trực tiếp các grant table trong schema `mysql`, việc không nên thực hiện trong quy trình quản trị thông thường. Hãy dùng `CREATE USER`, `CREATE ROLE`, `GRANT`, `REVOKE`, `SET DEFAULT ROLE` và `ALTER USER` thay cho việc cập nhật trực tiếp các bảng hệ thống.

## 8. Role trong view và stored program

Quyền dùng khi gọi view, procedure hoặc function còn phụ thuộc thuộc tính `SQL SECURITY` và `DEFINER`:

- Với `SQL SECURITY INVOKER`, thao tác chạy theo ngữ cảnh người gọi và các role đang active trong phiên người gọi.
- Với `SQL SECURITY DEFINER`, thao tác chạy theo ngữ cảnh người định nghĩa. MySQL sử dụng default role của tài khoản `DEFINER`; nếu `activate_all_roles_on_login` được bật, các role được cấp cho `DEFINER` cũng được kích hoạt theo quy tắc tương ứng.

Do đó, một câu `SELECT` trực tiếp có thể thất bại trong khi gọi một procedure vẫn thành công, hoặc ngược lại, tùy ngữ cảnh bảo mật. Khi điều tra lỗi quyền qua stored object, cần kiểm tra `SQL SECURITY`, `DEFINER`, quyền của tài khoản định nghĩa và trạng thái role liên quan, thay vì chỉ xem `CURRENT_ROLE()` của người gọi.

## 9. Nguyên tắc thiết kế và lỗi thường gặp

1. **Thiết kế role theo nhiệm vụ.** Tách đọc, ghi, triển khai schema và quản trị vận hành. Chỉ ghép các role khi một tài khoản thực sự cần tất cả nhiệm vụ đó.
2. **Ưu tiên quyền tối thiểu.** Cấp quyền trên database, table hoặc cột cần thiết. Tránh dùng `ALL ON *.*` cho tài khoản ứng dụng.
3. **Giữ quyền đặc biệt có chủ đích.** Nếu tài khoản có quyền cấp trực tiếp, tắt role vẫn không loại bỏ quyền đó. Hãy kiểm tra cả hai nguồn khi đánh giá rủi ro.
4. **Không nhầm role được cấp với role active.** Nếu quyền đã được cấp nhưng truy vấn vẫn bị từ chối, kiểm tra `CURRENT_ROLE()` và default role trước.
5. **Kiểm tra đúng tài khoản host.** `SHOW GRANTS` phải dùng đúng cặp user/host đang xác thực; cùng user name nhưng host khác có thể có bộ quyền khác.
6. **Đọc quyền bên trong role.** Dùng `SHOW GRANTS ... USING role` để mở rộng quyền của role khi kiểm toán.
7. **Thận trọng với cấu hình toàn cục.** `activate_all_roles_on_login` và `mandatory_roles` có phạm vi máy chủ; thay đổi chúng có thể tác động nhiều ứng dụng.
8. **Đặt lại trạng thái connection pool.** Không để role active từ request trước rò sang request sau.

Một quy trình chẩn đoán lỗi `Access denied` có thể đi theo thứ tự: xác nhận `CURRENT_USER()`; xem `CURRENT_ROLE()`; kiểm tra `SHOW GRANTS` của đúng tài khoản; mở rộng role bằng `USING`; xác nhận quyền đúng phạm vi database/table; cuối cùng kiểm tra ngữ cảnh `DEFINER`/`INVOKER` nếu truy cập thông qua stored object.

## 10. Bài tập tự kiểm tra

1. Tài khoản được cấp `r_sales_read` nhưng `CURRENT_ROLE()` trả về `NONE`. Vì sao role chưa cung cấp quyền đọc? Hãy nêu hai cách để kích hoạt role trong phiên.
2. Sau `SET ROLE NONE`, tài khoản vẫn đọc được một bảng. Nêu nguồn quyền có thể giải thích kết quả đó.
3. Một quản trị viên chạy `SET DEFAULT ROLE NONE TO 'svc_report'@'localhost'`. Điều này có lập tức tắt role trong mọi kết nối đang mở không? Cần lệnh nào để áp dụng default mới vào phiên hiện tại?
4. Khi thu hồi `UPDATE` khỏi `r_sales_write`, những tài khoản nào bị ảnh hưởng? Vì sao cách này có thể đơn giản hơn thu hồi từng tài khoản?
5. Ứng dụng dùng connection pool có request A chạy `SET ROLE NONE`. Cần làm gì để request B không nhận trạng thái quyền ngoài dự kiến?

**Gợi ý đáp án:** (1) Role được cấp nhưng chưa active; dùng `SET ROLE 'r_sales_read'@'%'` hoặc `SET ROLE DEFAULT` sau khi cấu hình default role. (2) Tài khoản có thể được cấp `SELECT` trực tiếp, hoặc có role khác đang active cung cấp quyền đó. (3) Không; default role chủ yếu điều khiển lúc đăng nhập và khi gọi `SET ROLE DEFAULT`; chạy `SET ROLE DEFAULT` trong từng phiên cần cập nhật. (4) Mọi tài khoản đang nhận quyền `UPDATE` qua role đó, bao gồm cả quyền kế thừa qua cấu trúc role. (5) Đặt role chuẩn khi lấy kết nối và khôi phục trạng thái trước khi trả kết nối về pool.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Using Roles](https://dev.mysql.com/doc/refman/8.4/en/roles.html)
- [MySQL 8.4 Reference Manual: SET ROLE](https://dev.mysql.com/doc/refman/8.4/en/set-role.html)
- [MySQL 8.4 Reference Manual: SET DEFAULT ROLE](https://dev.mysql.com/doc/refman/8.4/en/set-default-role.html)
- [MySQL 8.4 Reference Manual: GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)
- [MySQL 8.4 Reference Manual: When Privilege Changes Take Effect](https://dev.mysql.com/doc/refman/8.4/en/privilege-changes.html)
