# CREATE USER, ALTER USER, DROP USER và vòng đời tài khoản

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành. Bài này tập trung vào một phần cốt lõi của bảo mật và phân quyền: tạo, điều chỉnh, tạm khóa và thu hồi tài khoản MySQL trong suốt vòng đời của một ứng dụng hoặc người dùng.

Các ví dụ dùng cú pháp MySQL 8.0. Một số tùy chọn chính sách mật khẩu phụ thuộc phiên bản máy chủ; hãy kiểm tra phiên bản thực tế bằng `SELECT VERSION()` trước khi áp dụng.

## 1. Tài khoản MySQL được định danh bằng user và host

Trong MySQL, một tài khoản không chỉ là tên đăng nhập. Danh tính tài khoản là cặp:

```sql
'ten_user'@'host'
```

Ví dụ, hai tài khoản dưới đây là hai danh tính khác nhau:

```sql
'orders_app'@'localhost'
'orders_app'@'10.20.5.12'
```

Tài khoản thứ nhất dành cho kết nối từ máy chủ cục bộ; tài khoản thứ hai dành cho kết nối có nguồn từ địa chỉ IP được chỉ định. Vì vậy, tạo `orders_app`@`localhost` không đồng nghĩa ứng dụng kết nối từ máy khác sẽ đăng nhập được bằng tài khoản đó. MySQL chọn tài khoản dựa trên tên người dùng và thông tin host của kết nối, nên cần khai báo đúng nguồn kết nối thực tế.

Một số nguyên tắc khi chọn host:

- Ưu tiên hostname hoặc địa chỉ IP cụ thể mà ứng dụng thực sự dùng để kết nối.
- Tránh tạo tài khoản dùng host `%` theo thói quen. `%` cho phép khớp nhiều nguồn kết nối và làm phạm vi đăng nhập rộng hơn dự kiến.
- Không dùng chung một tài khoản cho nhiều ứng dụng hoặc nhiều người nếu cần truy vết và thu hồi quyền độc lập.
- Không tạo tài khoản không có tên người dùng hoặc tài khoản có host quá rộng để giải quyết lỗi kết nối.

Có thể kiểm tra danh tính MySQL đã áp dụng cho phiên hiện tại bằng:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account;
```

`USER()` thể hiện tên người dùng và host mà client gửi lên; `CURRENT_USER()` cho biết tài khoản mà MySQL thực sự dùng để xác thực phiên. Khi gặp lỗi quyền hoặc kết nối nhầm tài khoản, hai giá trị này giúp xác định vấn đề nằm ở thông tin kết nối hay ở cấu hình `user`/`host`.

## 2. CREATE USER: tạo tài khoản mới

`CREATE USER` tạo danh tính đăng nhập trong MySQL. Lệnh này không tự cấp quyền đọc hoặc ghi dữ liệu trong schema, bảng hay view. Sau khi tạo, tài khoản mới chưa thể thực hiện công việc của ứng dụng cho đến khi quản trị viên cấp quyền phù hợp bằng `GRANT`.

Cú pháp thường dùng:

```sql
CREATE USER [IF NOT EXISTS] 'ten_user'@'host'
    IDENTIFIED BY 'mat_khau'
    [REQUIRE SSL]
    [WITH MAX_USER_CONNECTIONS so_ket_noi];
```

Ví dụ tạo tài khoản cho dịch vụ xử lý đơn hàng, chỉ cho phép kết nối từ máy ứng dụng có IP `10.20.5.12`, yêu cầu TLS và giới hạn số kết nối đồng thời:

```sql
CREATE USER 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'THAY_BANG_BI_MAT_LAY_TU_VAULT'
    REQUIRE SSL
    WITH MAX_USER_CONNECTIONS 20;
```

Chuỗi mật khẩu trong ví dụ là chỗ giữ chỗ, không phải mật khẩu dùng thật. Trong môi trường triển khai, hãy lấy bí mật từ secret manager hoặc kho lưu trữ được kiểm soát, giới hạn người có thể đọc và tránh ghi mật khẩu thật vào mã nguồn, log, ticket hay lịch sử lệnh dùng chung. `REQUIRE SSL` buộc kết nối của tài khoản sử dụng TLS; cấu hình client và chứng chỉ máy chủ cũng phải tương thích để kết nối thành công.

Sau khi tạo tài khoản, cấp đúng quyền theo công việc. Ví dụ, nếu dịch vụ chỉ cần thao tác trên bảng `shop.orders`:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.orders
TO 'orders_app'@'10.20.5.12';
```

Không cấp `ALL PRIVILEGES` hoặc quyền quản trị chỉ để làm cho ứng dụng chạy được. Hãy bắt đầu từ quyền tối thiểu, sau đó bổ sung quyền khi có yêu cầu nghiệp vụ và được xem xét. Có thể kiểm tra quyền đã cấp bằng:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

### `IF NOT EXISTS` có ý nghĩa gì?

```sql
CREATE USER IF NOT EXISTS 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'THAY_BANG_BI_MAT_LAY_TU_VAULT';
```

Nếu tài khoản đã tồn tại, `IF NOT EXISTS` giúp câu lệnh không dừng vì lỗi tài khoản trùng; MySQL phát cảnh báo và giữ cấu hình hiện có. Tùy chọn này không đồng bộ mật khẩu, plugin xác thực, trạng thái khóa hay chính sách của tài khoản hiện tại. Vì vậy, không nên dùng nó thay cho bước kiểm tra cấu hình hoặc `ALTER USER`.

### Plugin xác thực và mật khẩu

MySQL hỗ trợ nhiều plugin xác thực. Với các phiên bản MySQL 8.0 hiện đại, `caching_sha2_password` là plugin mặc định phổ biến. Khi cần chỉ định rõ plugin, cú pháp có dạng:

```sql
CREATE USER 'report_reader'@'10.20.5.25'
    IDENTIFIED WITH caching_sha2_password
    BY 'THAY_BANG_BI_MAT_LAY_TU_VAULT';
```

Chỉ chọn plugin mà máy chủ và client đều hỗ trợ. `mysql_native_password` đã bị đánh dấu lỗi thời từ MySQL 8.0.34 và bị tắt mặc định trong MySQL 8.4; không nên hạ chuẩn xác thực chỉ để né việc nâng cấp client. Hãy kiểm tra tài liệu đúng phiên bản MySQL và khả năng tương thích của driver trước khi thay đổi plugin.

## 3. ALTER USER: điều chỉnh tài khoản đang tồn tại

`ALTER USER` thay đổi thuộc tính của một tài khoản đã có. Các trường hợp phổ biến gồm đổi mật khẩu, đặt thời hạn mật khẩu, yêu cầu TLS, giới hạn tài nguyên và khóa hoặc mở khóa tài khoản.

### Đổi mật khẩu

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    IDENTIFIED BY 'MAT_KHAU_MOI_LAY_TU_VAULT';
```

Khi luân chuyển bí mật, cần cập nhật đồng bộ nơi lưu secret và cấu hình của ứng dụng theo quy trình triển khai. Nếu thay mật khẩu ở máy chủ nhưng ứng dụng vẫn dùng mật khẩu cũ, các kết nối mới sẽ thất bại. Với hệ thống nhiều instance, cần xác định thứ tự cập nhật để tránh gián đoạn.

### Đặt chính sách hết hạn mật khẩu

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    PASSWORD EXPIRE INTERVAL 90 DAY;
```

Một số lựa chọn thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| `PASSWORD EXPIRE` | Đánh dấu mật khẩu hết hạn ngay. |
| `PASSWORD EXPIRE INTERVAL 90 DAY` | Đặt mật khẩu hết hạn sau số ngày chỉ định. |
| `PASSWORD EXPIRE DEFAULT` | Áp dụng chính sách hết hạn mặc định của máy chủ. |
| `PASSWORD EXPIRE NEVER` | Không tự động hết hạn mật khẩu cho tài khoản này. |

Chính sách hết hạn cần phù hợp với cách ứng dụng quản lý bí mật. Một tài khoản dịch vụ không có cơ chế đổi mật khẩu tự động có thể gây gián đoạn nếu mật khẩu hết hạn bất ngờ. Hãy phối hợp thời hạn, quy trình luân chuyển secret và lịch triển khai; không đặt `NEVER` một cách mặc định mà không có biện pháp kiểm soát thay thế.

### Khóa và mở khóa tài khoản

Khi cần tạm dừng quyền đăng nhập, có thể khóa tài khoản:

```sql
ALTER USER 'orders_app'@'10.20.5.12' ACCOUNT LOCK;
```

Khi đã xử lý xong nguyên nhân và được phép khôi phục hoạt động:

```sql
ALTER USER 'orders_app'@'10.20.5.12' ACCOUNT UNLOCK;
```

Khóa tài khoản ngăn các lần đăng nhập mới. Lệnh này không tự kết thúc những phiên đã kết nối từ trước, vì vậy khi xử lý sự cố hoặc thu hồi quyền khẩn cấp, quản trị viên cần kiểm tra và xử lý riêng các phiên đang hoạt động theo quy trình vận hành. Mở khóa chỉ khôi phục khả năng đăng nhập; các quyền đã cấp trước đó vẫn còn hiệu lực.

### Giới hạn kết nối và áp dụng chính sách mật khẩu

Có thể điều chỉnh giới hạn kết nối sau khi tài khoản đã được tạo:

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    WITH MAX_USER_CONNECTIONS 20;
```

Trên MySQL 8.0.19 trở lên, có thể cấu hình thêm lịch sử mật khẩu và cơ chế khóa sau nhiều lần đăng nhập thất bại:

```sql
ALTER USER 'orders_app'@'10.20.5.12'
    PASSWORD HISTORY 5
    PASSWORD REUSE INTERVAL 365 DAY
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
```

Trong ví dụ, MySQL lưu chính sách không cho dùng lại năm mật khẩu gần nhất, không cho tái sử dụng mật khẩu trong 365 ngày, khóa tài khoản sau năm lần đăng nhập thất bại liên tiếp và giữ khóa trong một ngày. Giá trị thực tế cần dựa trên chính sách an toàn thông tin, khả năng hỗ trợ của ứng dụng và phiên bản máy chủ. Nếu dùng phiên bản cũ hơn 8.0.19, các tùy chọn theo dõi lần đăng nhập thất bại có thể không được hỗ trợ.

## 4. DROP USER: thu hồi tài khoản

Khi người dùng nghỉ việc, dịch vụ ngừng hoạt động hoặc tài khoản không còn mục đích hợp lệ, quản trị viên có thể xóa tài khoản:

```sql
DROP USER 'orders_app'@'10.20.5.12';
```

Để thao tác an toàn trong kịch bản tự động hóa có thể gặp trường hợp tài khoản đã bị xóa trước đó, dùng `IF EXISTS`:

```sql
DROP USER IF EXISTS 'orders_app'@'10.20.5.12';
```

`DROP USER` xóa tài khoản MySQL cùng các quyền gắn với tài khoản đó. Lệnh không xóa schema, bảng hay các dòng dữ liệu mà tài khoản từng tạo hoặc thao tác. Việc xóa tài khoản cũng không nên được xem là cách kết thúc các kết nối đang mở; hãy kiểm tra và xử lý phiên hiện hữu riêng. Trước khi xóa tài khoản dùng chung hoặc tài khoản dịch vụ, cần xác nhận không còn ứng dụng, lịch chạy hay quy trình vận hành phụ thuộc vào nó.

Nếu cần tạm dừng để điều tra hoặc chờ phê duyệt, `ACCOUNT LOCK` thường phù hợp hơn xóa ngay vì có thể mở khóa lại. Khi đã xác nhận tài khoản không còn cần thiết, hãy thu hồi quyền và xóa tài khoản theo quy trình quản lý thay đổi.

## 5. Quy trình quản lý vòng đời tài khoản

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Xác định chủ sở hữu và mục đích.** Ghi nhận ứng dụng hoặc cá nhân sử dụng tài khoản, môi trường, nguồn kết nối, người chịu trách nhiệm và thời điểm cần rà soát lại.
2. **Chọn danh tính chính xác.** Xác định cặp `user`/`host` theo nguồn kết nối thực tế; tránh dùng chung tài khoản giữa môi trường phát triển, kiểm thử và sản xuất.
3. **Tạo tài khoản với cấu hình an toàn.** Dùng `CREATE USER`, chọn plugin xác thực phù hợp, yêu cầu TLS khi cần và giới hạn kết nối theo tải dự kiến.
4. **Cấp quyền tối thiểu.** Dùng `GRANT` cho đúng schema, bảng hoặc thao tác mà tài khoản cần. Tạo tài khoản và cấp quyền là hai việc riêng biệt.
5. **Xác minh sau thay đổi.** Dùng `SHOW GRANTS` để kiểm tra quyền; kiểm tra cấu hình tài khoản bằng `SHOW CREATE USER` nếu có quyền phù hợp. Kết quả `SHOW CREATE USER` có thể chứa thông tin xác thực nhạy cảm, nên không đưa nguyên văn vào log hoặc kênh trao đổi công khai.
6. **Duy trì trong thời gian sử dụng.** Luân chuyển mật khẩu, rà soát quyền, cập nhật giới hạn và chính sách hết hạn khi yêu cầu nghiệp vụ thay đổi.
7. **Tạm khóa hoặc thu hồi.** Dùng `ACCOUNT LOCK` khi cần dừng đăng nhập tạm thời; dùng `DROP USER` khi tài khoản đã hết mục đích và các phụ thuộc đã được kiểm tra.

Ví dụ kiểm tra quyền sau khi tạo tài khoản:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.5.12';
```

Ví dụ xem định nghĩa tài khoản để rà soát plugin xác thực, yêu cầu TLS và trạng thái khóa:

```sql
SHOW CREATE USER 'orders_app'@'10.20.5.12';
```

Hãy giới hạn quyền xem kết quả này vì thông tin xác thực đã băm vẫn là dữ liệu nhạy cảm trong ngữ cảnh quản trị.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `CREATE USER` báo tài khoản đã tồn tại | Cặp `user`/`host` đã được tạo trước đó. | Kiểm tra đúng host và dùng `ALTER USER` nếu mục tiêu là cập nhật cấu hình. `IF NOT EXISTS` chỉ bỏ lỗi trùng, không cập nhật tài khoản. |
| Ứng dụng báo `Access denied` dù đã tạo user | Host trong tài khoản không khớp nguồn kết nối; mật khẩu hoặc plugin không tương thích; tài khoản đang khóa; hoặc chưa được cấp quyền. | Kiểm tra `USER()` và `CURRENT_USER()` từ phiên kết nối, xác minh mật khẩu/plugin, trạng thái khóa và `SHOW GRANTS`. |
| `ALTER USER` hoặc `DROP USER` không tác động tài khoản mong muốn | Dùng sai `host` hoặc tên user. | Xác định đầy đủ cặp `user`/`host`; không chỉ dựa vào tên đăng nhập. |
| Tài khoản đã khóa nhưng ứng dụng vẫn có truy vấn đang chạy | Khóa tài khoản chặn đăng nhập mới, không tự đóng phiên đã xác thực. | Kiểm tra các phiên hiện hữu và xử lý riêng theo quy trình vận hành. |
| Tài khoản đăng nhập được nhưng không truy vấn được bảng | `CREATE USER` không tự cấp quyền trên dữ liệu. | Cấp quyền tối thiểu bằng `GRANT` trên đúng đối tượng cần thiết. |

Không sửa trực tiếp bảng hệ thống `mysql.user` để tạo, đổi hoặc xóa tài khoản. Hãy dùng `CREATE USER`, `ALTER USER`, `DROP USER` và các câu lệnh quản lý quyền chính thức để MySQL kiểm tra cú pháp, cập nhật metadata và áp dụng chính sách nhất quán.

Các câu lệnh quản lý tài khoản này gây implicit commit trong MySQL. Vì vậy, không thiết kế quy trình với giả định có thể đặt `CREATE USER`, `ALTER USER` hoặc `DROP USER` trong một transaction rồi dùng `ROLLBACK` để hoàn tác. Hãy xem mỗi thay đổi tài khoản là một thao tác quản trị riêng, được ghi nhận, rà soát và thực hiện theo quy trình thay đổi.

## 7. Bài tập thực hành

Một ứng dụng quản lý kho chạy trên máy `10.20.5.18`, chỉ cần đọc bảng sản phẩm và cập nhật số lượng tồn trong bảng kho của schema `warehouse`. Hãy thực hiện các yêu cầu sau trên môi trường thử nghiệm:

1. Tạo tài khoản `inventory_app` gắn với host `10.20.5.18`, dùng mật khẩu lấy từ kho bí mật, yêu cầu TLS và giới hạn tối đa 15 kết nối đồng thời.
2. Cấp quyền `SELECT` trên bảng `warehouse.products` và quyền `SELECT`, `UPDATE` trên bảng `warehouse.stock`.
3. Dùng `SHOW GRANTS` xác minh quyền; kiểm tra `USER()` và `CURRENT_USER()` từ kết nối của ứng dụng.
4. Đặt chính sách hết hạn mật khẩu theo quy định của môi trường; nếu máy chủ hỗ trợ MySQL 8.0.19 trở lên, cân nhắc cấu hình giới hạn đăng nhập thất bại.
5. Mô phỏng ngừng dịch vụ bằng `ACCOUNT LOCK`, xác minh kết nối mới bị từ chối, sau đó mở khóa bằng `ACCOUNT UNLOCK`.
6. Khi kết thúc bài thực hành, xác nhận không còn phụ thuộc rồi xóa tài khoản bằng `DROP USER IF EXISTS`.

Sau bài tập, cần giải thích được vì sao `inventory_app`@`localhost` không thay thế cho `inventory_app`@`10.20.5.18`, vì sao tạo tài khoản chưa đủ để truy vấn bảng, và vì sao khóa tài khoản khác với xóa tài khoản. Đây là ba điểm quyết định để quản lý vòng đời tài khoản an toàn trong hệ thống MySQL đang vận hành.
