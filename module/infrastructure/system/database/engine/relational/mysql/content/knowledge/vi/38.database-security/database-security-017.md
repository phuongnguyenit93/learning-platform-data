# Rà soát tài khoản ẩn danh, quyền thừa và tài khoản không còn sử dụng

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành. Bài này hướng dẫn kiểm kê tài khoản, phát hiện tài khoản ẩn danh, xác định quyền vượt quá nhu cầu, nhận diện tài khoản có thể đã hết mục đích sử dụng và thu hồi quyền theo quy trình có kiểm soát.

Các ví dụ sử dụng MySQL 8.0. Việc kiểm tra metadata tài khoản cần quyền đọc phù hợp trên các đối tượng hệ thống. Chỉ chạy các lệnh thay đổi trên tài khoản đã được xác minh trong môi trường và quy trình quản trị của bạn.

## 1. Vì sao cần rà soát tài khoản định kỳ?

Mỗi tài khoản MySQL là một điểm có thể truy cập vào hệ thống. Theo thời gian, tài khoản thử nghiệm, tài khoản của nhân viên đã chuyển vị trí, tài khoản dịch vụ cũ hoặc quyền tạm cấp trong một đợt xử lý sự cố có thể vẫn còn tồn tại. Nếu không được rà soát, chúng làm tăng số danh tính có thể bị lạm dụng và khiến việc điều tra truy cập khó khăn hơn.

Một đợt rà soát nên trả lời được bốn câu hỏi:

- Tài khoản nào có thể đăng nhập, và chúng được phép kết nối từ những host nào?
- Có tài khoản ẩn danh hoặc tài khoản dùng host quá rộng không?
- Mỗi tài khoản có những quyền trực tiếp và quyền kế thừa từ role nào?
- Tài khoản nào không còn chủ sở hữu, ứng dụng phụ thuộc hoặc nhu cầu nghiệp vụ đã được xác nhận?

Không thể kết luận một tài khoản là không sử dụng chỉ từ tên tài khoản, ngày đổi mật khẩu hoặc việc hiện tại không có phiên kết nối. Cần kết hợp metadata MySQL với nhật ký đăng nhập, danh mục ứng dụng, người phụ trách và xác nhận của chủ sở hữu.

## 2. Kiểm kê tài khoản và phát hiện tài khoản ẩn danh

Trong MySQL, danh tính tài khoản gồm cả tên người dùng và host. Ví dụ, `'app_user'@'localhost'` và `'app_user'@'10.20.5.12'` là hai tài khoản khác nhau. Vì vậy, mọi báo cáo kiểm kê và thao tác thu hồi phải ghi đầy đủ cả hai thành phần.

### Liệt kê tài khoản

Với MySQL 8.0, có thể xem danh sách tài khoản cùng plugin xác thực và trạng thái khóa như sau:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired,
    password_last_changed
FROM mysql.user
ORDER BY User, Host;
```

Không truy vấn hoặc đưa `authentication_string` vào báo cáo kiểm kê thông thường. Đây là dữ liệu xác thực nhạy cảm; báo cáo rà soát chỉ cần các thuộc tính phục vụ nhận diện và kiểm soát.

### Tìm tài khoản ẩn danh

Tài khoản ẩn danh có giá trị `User` là chuỗi rỗng. Truy vấn sau liệt kê tất cả tài khoản dạng này:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked
FROM mysql.user
WHERE User = ''
ORDER BY Host;
```

Tài khoản ẩn danh không yêu cầu client cung cấp tên người dùng MySQL cụ thể để khớp với danh tính đó. Khi có cấu hình host phù hợp, nó có thể tạo ra đường đăng nhập ngoài dự kiến, đặc biệt nếu người quản trị hiểu nhầm rằng mọi kết nối đều phải khớp với một tên user đã đặt.

Nếu phát hiện tài khoản ẩn danh, hãy xác định host, trạng thái, lịch sử sử dụng và lý do tồn tại. Trong hệ thống ứng dụng thông thường, tài khoản ẩn danh hiếm khi có nhu cầu hợp lệ; cần xác nhận với chủ sở hữu và kiểm tra ảnh hưởng trước khi thu hồi.

Nếu đã xác minh tài khoản không còn cần thiết, xóa đúng cặp user/host được trả về. Ví dụ, chỉ khi kết quả kiểm kê có chính xác tài khoản dưới đây:

```sql
DROP USER ''@'localhost';
```

Không mặc định host của tài khoản ẩn danh là `localhost`. Có thể có nhiều tài khoản ẩn danh với các host khác nhau; cần xử lý từng danh tính đã xác minh. Nếu cần tạm dừng đăng nhập trong lúc điều tra, có thể dùng `ALTER USER ''@'localhost' ACCOUNT LOCK` với đúng host thực tế của tài khoản.

### Rà soát host quá rộng

Kiểm tra những tài khoản có host `%`:

```sql
SELECT User, Host, account_locked
FROM mysql.user
WHERE Host = '%'
ORDER BY User;
```

Host `%` có thể khớp nhiều nguồn kết nối, làm phạm vi đăng nhập rộng hơn dự kiến. Tuy nhiên, không phải mọi tài khoản dùng `%` đều chắc chắn sai: một số hệ thống có thể cần kết nối từ nhiều máy ứng dụng. Hãy đối chiếu với sơ đồ mạng, firewall, TLS, quyền được cấp và danh sách nguồn kết nối được phê duyệt. Nếu có thể, thu hẹp host về hostname hoặc địa chỉ cụ thể phù hợp với kiến trúc.

## 3. Rà soát quyền trực tiếp theo từng cấp

MySQL có thể cấp quyền ở nhiều phạm vi: toàn máy chủ, schema, bảng và cột. Một tài khoản có thể chỉ có vài quyền trực tiếp ở một cấp nhưng lại có thêm quyền rộng ở cấp khác. Vì vậy, kiểm tra một dòng quyền hoặc chỉ nhìn tên user là chưa đủ.

### Kiểm tra quyền toàn cục

Ví dụ kiểm tra quyền toàn cục của tài khoản `orders_app`:

```sql
SELECT
    GRANTEE,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.USER_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY PRIVILEGE_TYPE;
```

Quyền toàn cục áp dụng trên toàn máy chủ và thường cần được xem xét kỹ hơn quyền giới hạn trong một schema hoặc bảng. Các quyền quản trị, quyền đọc/ghi tệp trên máy chủ, quyền quản lý tài khoản hoặc quyền cấp lại quyền cần có lý do nghiệp vụ và chủ sở hữu rõ ràng. Đặc biệt, `IS_GRANTABLE = 'YES'` cho biết tài khoản có thể cấp lại quyền tương ứng; đây là thuộc tính cần được kiểm tra riêng.

### Kiểm tra quyền trên schema

```sql
SELECT
    TABLE_SCHEMA,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.SCHEMA_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, PRIVILEGE_TYPE;
```

Truy vấn này giúp tìm quyền áp dụng cho toàn bộ schema. Ví dụ, nếu dịch vụ chỉ cần đọc dữ liệu trong `shop`, quyền `SELECT` trên schema có thể phù hợp; quyền `INSERT`, `UPDATE`, `DELETE`, `DROP` hoặc `ALTER` cần được đối chiếu với chức năng thực tế.

### Kiểm tra quyền trên bảng và cột

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM information_schema.TABLE_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE;
```

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    PRIVILEGE_TYPE
FROM information_schema.COLUMN_PRIVILEGES
WHERE GRANTEE = CONCAT(QUOTE('orders_app'), '@', QUOTE('10.20.5.12'))
ORDER BY TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, PRIVILEGE_TYPE;
```

Quyền trên bảng hoặc cột thường cho phép giới hạn ứng dụng vào đúng dữ liệu cần thiết. Khi rà soát, hãy chú ý các quyền ghi, xóa, thay đổi cấu trúc và quyền truy cập vào cột nhạy cảm. Một tài khoản báo cáo chỉ cần đọc một vài bảng không nên mặc nhiên có quyền sửa dữ liệu hoặc đọc mọi schema.

### Đối chiếu bằng SHOW GRANTS

`SHOW GRANTS` cung cấp bản trình bày các quyền đã cấp cho một tài khoản:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

Đây là bước đối chiếu hữu ích vì kết quả thể hiện các câu lệnh `GRANT` tương ứng, bao gồm cả việc gán role. Hãy lưu kết quả vào hồ sơ rà soát theo quy định nội bộ và tránh đưa dữ liệu nhạy cảm không cần thiết vào log chia sẻ.

## 4. Rà soát role và quyền kế thừa

Từ MySQL 8.0, role giúp gom nhóm quyền theo chức năng và gán nhóm đó cho nhiều tài khoản. Khi kiểm tra một tài khoản, cần xem cả quyền cấp trực tiếp lẫn role được gán. Một tài khoản có thể trông ít quyền khi chỉ kiểm tra các quyền trực tiếp, nhưng role được kích hoạt lại mang thêm quyền đọc hoặc ghi rộng.

Liệt kê các role được gán trực tiếp cho tài khoản:

```sql
SELECT
    FROM_USER AS role_name,
    FROM_HOST AS role_host,
    WITH_ADMIN_OPTION
FROM mysql.role_edges
WHERE TO_USER = 'orders_app'
  AND TO_HOST = '10.20.5.12'
ORDER BY FROM_USER, FROM_HOST;
```

Trong `mysql.role_edges`, `FROM_USER`/`FROM_HOST` là role được cấp và `TO_USER`/`TO_HOST` là tài khoản hoặc role nhận role đó. `WITH_ADMIN_OPTION` cho biết bên nhận có quyền quản lý việc gán role theo tùy chọn này. Nếu role được gán cho một role khác, cần tiếp tục kiểm tra chuỗi kế thừa.

Kiểm tra các role mặc định của tài khoản:

```sql
SELECT
    USER,
    HOST,
    DEFAULT_ROLE_USER,
    DEFAULT_ROLE_HOST
FROM mysql.default_roles
WHERE USER = 'orders_app'
  AND HOST = '10.20.5.12';
```

Trong một phiên đăng nhập, có thể xem role hiện đang hoạt động bằng:

```sql
SELECT CURRENT_ROLE();
```

Để đánh giá đầy đủ, hãy kiểm tra `SHOW GRANTS` của tài khoản, các role được gán và `SHOW GRANTS` của từng role liên quan. Không kết luận tài khoản an toàn chỉ vì quyền trực tiếp của nó ít; quyền kế thừa có thể làm thay đổi đáng kể phạm vi truy cập.

## 5. Nhận diện tài khoản không còn sử dụng

MySQL không cung cấp một trường `last_login` đáng tin cậy trong `mysql.user` để quản trị viên kết luận tài khoản nào không còn sử dụng. `password_last_changed` là thời điểm mật khẩu được thay đổi, không phải thời điểm đăng nhập gần nhất. Việc không thấy tài khoản trong `SHOW PROCESSLIST` chỉ cho biết hiện tại không có phiên đang hiển thị; nó không chứng minh tài khoản đã ngừng hoạt động.

### Dùng bộ đếm kết nối như một tín hiệu tham khảo

Nếu Performance Schema được bật và bảng tổng hợp tài khoản có dữ liệu, có thể xem số kết nối hiện tại và tổng số kết nối được ghi nhận kể từ khi thống kê được khởi tạo hoặc đặt lại:

```sql
SELECT
    USER,
    HOST,
    CURRENT_CONNECTIONS,
    TOTAL_CONNECTIONS
FROM performance_schema.accounts
ORDER BY TOTAL_CONNECTIONS, USER, HOST;
```

Các bộ đếm này hữu ích để tìm tài khoản có ít hoặc không có kết nối trong khoảng thống kê hiện tại. Chúng không lưu mốc thời gian đăng nhập cuối cùng và có thể bị đặt lại khi khởi động lại máy chủ hoặc khi thống kê được reset. Vì vậy, không dùng `TOTAL_CONNECTIONS = 0` làm bằng chứng duy nhất để xóa tài khoản.

### Kết hợp log và danh mục ứng dụng

Để xác minh một tài khoản có còn hoạt động hay không, kết hợp nhiều nguồn:

- Nhật ký audit hoặc nhật ký kết nối có ghi nhận sự kiện đăng nhập thành công, thất bại và ngắt kết nối.
- Danh mục dịch vụ, cấu hình triển khai, secret manager và lịch chạy định kỳ để tìm ứng dụng còn tham chiếu tài khoản.
- Người sở hữu ứng dụng hoặc nhóm vận hành xác nhận mục đích, thời gian sử dụng và kế hoạch thay thế.
- Bộ đếm Performance Schema và danh sách phiên hiện tại để bổ sung tín hiệu hoạt động gần đây.

Nếu hệ thống chưa có log đăng nhập đủ thời gian, hãy ghi nhận giới hạn này và theo dõi thêm trong một chu kỳ nghiệp vụ phù hợp trước khi thu hồi. Không bật general log trên môi trường sản xuất chỉ để tìm tài khoản cũ mà chưa đánh giá tác động hiệu năng, dung lượng, dữ liệu nhạy cảm và chính sách lưu trữ. Ưu tiên audit log hoặc nguồn log kết nối đã được vận hành và phê duyệt.

## 6. Thu hẹp quyền và thu hồi tài khoản

Sau khi phát hiện quyền thừa, hãy xác định quyền nào không còn cần thiết và phạm vi chính xác trước khi dùng `REVOKE`. Ví dụ, thu hồi quyền `UPDATE` trên bảng đơn hàng:

```sql
REVOKE UPDATE
ON shop.orders
FROM 'orders_app'@'10.20.5.12';
```

Nếu tài khoản được cấp một role không còn cần thiết, thu hồi role đó riêng:

```sql
REVOKE 'reporting_role'@'localhost'
FROM 'orders_app'@'10.20.5.12';
```

Thay `reporting_role` và host bằng đúng role thực tế trong kết quả kiểm kê. Việc thu hồi quyền trực tiếp không thay thế việc thu hồi role; tương tự, thu hồi role không tự xóa các quyền đã cấp trực tiếp cho tài khoản.

Nếu cần thu hồi toàn bộ quyền trực tiếp và quyền cấp lại quyền của một tài khoản, MySQL hỗ trợ:

```sql
REVOKE ALL PRIVILEGES, GRANT OPTION
FROM 'orders_app'@'10.20.5.12';
```

Lệnh này không thay thế thao tác thu hồi các role đã gán. Hãy kiểm tra lại `SHOW GRANTS` và role edges sau khi thay đổi để xác minh trạng thái cuối cùng. Việc thu hồi quyền có thể làm ứng dụng lỗi nếu còn chức năng phụ thuộc; hãy kiểm thử với chủ sở hữu dịch vụ và theo dõi sau triển khai.

### Khóa tài khoản trước khi xóa

Với tài khoản nghi không còn sử dụng nhưng chưa thể xác minh ngay, có thể khóa để ngăn đăng nhập mới trong thời gian theo dõi:

```sql
ALTER USER 'old_batch_app'@'10.20.5.30' ACCOUNT LOCK;
```

Khóa tài khoản không kết thúc các phiên đã kết nối từ trước. Nếu cần chấm dứt truy cập đang diễn ra, phải kiểm tra và xử lý phiên hiện hữu theo quy trình vận hành. Việc mở khóa có thể thực hiện bằng:

```sql
ALTER USER 'old_batch_app'@'10.20.5.30' ACCOUNT UNLOCK;
```

Chỉ xóa sau khi chủ sở hữu xác nhận tài khoản không còn được dùng, các ứng dụng đã chuyển sang danh tính mới nếu cần, quyền và phụ thuộc đã được rà soát, và thời gian theo dõi không phát hiện ảnh hưởng:

```sql
DROP USER 'old_batch_app'@'10.20.5.30';
```

`DROP USER` xóa tài khoản và các quyền gắn với tài khoản đó; nó không xóa dữ liệu trong schema hoặc bảng mà tài khoản từng truy cập. Lệnh cũng không tự kết thúc những phiên đã mở trước đó. Với thao tác tự động hóa có thể gặp tài khoản đã bị xóa, có thể dùng `DROP USER IF EXISTS`, nhưng vẫn cần ghi nhận danh tính và lý do thu hồi.

Không xóa hoặc sửa các tài khoản hệ thống do MySQL tạo và sử dụng, chẳng hạn `mysql.session`, `mysql.sys` và `mysql.infoschema`, trừ khi tài liệu chính thức cho đúng phiên bản yêu cầu một thao tác cụ thể. Cũng cần xác minh tài khoản quản trị dự phòng và tài khoản phục vụ sao lưu, giám sát, replication trước khi thay đổi.

## 7. Quy trình rà soát định kỳ có thể kiểm toán

Một quy trình thực tế có thể chia thành các bước sau:

1. **Lập danh sách tài khoản.** Xuất `User`, `Host`, plugin xác thực và trạng thái khóa; loại bỏ thông tin xác thực nhạy cảm khỏi báo cáo.
2. **Tìm tài khoản bất thường.** Kiểm tra user rỗng, host `%`, tài khoản trùng mục đích và tài khoản không có chủ sở hữu rõ ràng.
3. **Lập bản đồ quyền.** Đối chiếu quyền toàn cục, schema, bảng, cột, role, quyền cấp lại và role mặc định.
4. **Xác minh mức sử dụng.** Kết hợp audit log, bộ đếm kết nối, cấu hình ứng dụng, lịch chạy và xác nhận từ chủ sở hữu.
5. **Đề xuất xử lý.** Ghi rõ quyền cần thu hồi, tài khoản cần khóa hoặc xóa, lý do, tác động dự kiến và người phê duyệt.
6. **Thực hiện theo đợt.** Ưu tiên thu hẹp quyền; khóa tài khoản không rõ trạng thái để theo dõi khi phù hợp; chỉ xóa sau khi xác nhận phụ thuộc.
7. **Kiểm tra sau thay đổi.** Chạy lại các truy vấn kiểm kê, `SHOW GRANTS`, kiểm tra role và thử các luồng ứng dụng quan trọng.
8. **Lưu bằng chứng.** Ghi thời điểm, người thực hiện, danh tính `user`/`host`, thay đổi, kết quả kiểm thử và người xác nhận.

Một báo cáo rà soát nên có tối thiểu các cột: tài khoản, host, chủ sở hữu, mục đích, nguồn kết nối được phép, quyền trực tiếp, role được gán, tín hiệu sử dụng, phát hiện, hành động đề xuất, người phê duyệt và trạng thái xử lý. Dữ liệu xác thực và bí mật triển khai không thuộc báo cáo này.

## 8. Bài tập thực hành

Giả sử máy chủ thử nghiệm có các tài khoản cho ứng dụng bán hàng, báo cáo, tác vụ batch và một tài khoản người dùng cũ. Hãy thực hành theo các yêu cầu sau:

1. Liệt kê tài khoản từ `mysql.user`; tìm các dòng có `User = ''` và kiểm tra các tài khoản có `Host = '%'`.
2. Chọn một tài khoản ứng dụng thử nghiệm, dùng các view `USER_PRIVILEGES`, `SCHEMA_PRIVILEGES`, `TABLE_PRIVILEGES` và `COLUMN_PRIVILEGES` để lập danh sách quyền trực tiếp.
3. Dùng `SHOW GRANTS`, `mysql.role_edges` và `mysql.default_roles` để xác định role được gán, quyền quản lý role và role mặc định.
4. Kiểm tra `performance_schema.accounts` nếu có dữ liệu; giải thích vì sao bộ đếm kết nối không đủ để kết luận tài khoản đã bỏ không.
5. Chọn một quyền ghi không cần thiết, thu hồi bằng `REVOKE`, sau đó chạy lại `SHOW GRANTS` và kiểm thử chức năng ứng dụng.
6. Với tài khoản cũ, xác minh log và chủ sở hữu, khóa trong môi trường thử nghiệm, kiểm tra các kết nối mới, rồi chỉ xóa sau khi đã xác nhận không còn phụ thuộc.

Kết thúc bài tập, hãy trình bày được sự khác nhau giữa quyền trực tiếp và quyền qua role, giữa khóa và xóa tài khoản, cũng như các bằng chứng cần có trước khi kết luận một tài khoản không còn sử dụng. Đây là nền tảng để giữ danh tính và quyền truy cập MySQL ở mức cần thiết trong suốt quá trình vận hành.
