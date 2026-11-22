# Thiết lập tài khoản thực hành với quyền tối thiểu

Một môi trường thực hành MySQL an toàn cần có database riêng và tài khoản riêng cho người học hoặc ứng dụng. Tài khoản này chỉ được phép làm những việc cần thiết trong phạm vi bài tập. Nếu dùng tài khoản `root` cho mọi thao tác, một câu lệnh nhầm có thể ảnh hưởng đến các database khác hoặc cấu hình của cả máy chủ.

Trong bài này, ta tạo database `mysql_lab` và một tài khoản `mysql_lab_user` để luyện tập SQL. Tài khoản có thể đọc, ghi dữ liệu, tạo và chỉnh sửa bảng, tạo chỉ mục trong database thực hành. Tài khoản không được quản trị người dùng, cấp quyền, tạo database tùy ý hoặc xóa database và bảng. Các ví dụ dùng cú pháp MySQL 8.x; hãy thay mật khẩu và địa chỉ kết nối theo môi trường thực tế.

## 1. Hiểu nguyên tắc quyền tối thiểu

Quyền tối thiểu (least privilege) nghĩa là mỗi tài khoản chỉ nhận tập quyền đủ để hoàn thành công việc của nó. Khi xác định quyền, hãy trả lời ba câu hỏi: tài khoản cần làm thao tác gì, trên đối tượng nào và từ máy nào được phép kết nối?

MySQL cho phép cấp quyền ở nhiều phạm vi:

| Phạm vi | Ví dụ | Ảnh hưởng |
|---|---|---|
| Toàn máy chủ | `ON *.*` | Áp dụng trên các database và đối tượng tương ứng trong toàn máy chủ |
| Một database | `ON mysql_lab.*` | Áp dụng cho các bảng và đối tượng thuộc database `mysql_lab` |
| Một bảng | `ON mysql_lab.customers` | Chỉ áp dụng cho bảng `customers` trong `mysql_lab` |
| Một số cột | `ON mysql_lab.customers (email)` | Chỉ áp dụng cho các cột được chỉ định, với những quyền hỗ trợ phạm vi cột |

Với một môi trường học tập, nên dành một database riêng cho bài thực hành và cấp quyền trên database đó. Tránh cấp quyền toàn cục bằng `ON *.*` nếu bài tập không yêu cầu quản trị cả máy chủ.

Các loại tài khoản thường có mục đích khác nhau:

- **Tài khoản quản trị hoặc khởi tạo môi trường** tạo database, tạo người dùng và cấp quyền. Chỉ người được giao quản trị mới sử dụng tài khoản này.
- **Tài khoản thực hành** thao tác với bảng và dữ liệu trong database được giao. Đây là tài khoản dùng trong MySQL Workbench, dòng lệnh hoặc chương trình Java của bài tập.
- **Tài khoản ứng dụng chạy thường xuyên** thường chỉ cần các quyền DML như `SELECT`, `INSERT`, `UPDATE`, `DELETE`. Việc thay đổi cấu trúc bảng nên được thực hiện bằng tài khoản triển khai/migration riêng.
- **Tài khoản chỉ đọc** thường chỉ cần `SELECT` trên các bảng được phép xem.

Không nên dùng chung tài khoản quản trị cho ứng dụng. Tách tài khoản theo mục đích giúp giới hạn thiệt hại khi lộ mật khẩu và giúp truy vết thao tác dễ hơn.

## 2. Chuẩn bị database thực hành

Đăng nhập MySQL bằng tài khoản quản trị có quyền tạo database, tạo user và cấp quyền. Trong môi trường học tập trên máy cá nhân, có thể dùng tài khoản quản trị cục bộ. Không đưa mật khẩu quản trị vào mã nguồn hoặc chia sẻ trong nhóm.

Kiểm tra máy chủ đang kết nối:

```sql
SELECT VERSION();
SELECT CURRENT_USER();
```

Tạo database riêng cho bài thực hành:

```sql
CREATE DATABASE mysql_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

`utf8mb4` hỗ trợ đầy đủ Unicode, phù hợp với dữ liệu tiếng Việt và nhiều loại ký tự khác. Database `mysql_lab` là vùng thực hành của bài học; không sử dụng database hệ thống như `mysql`, `sys`, `performance_schema` hoặc `information_schema` để làm bài tập.

Nếu database đã tồn tại, hãy kiểm tra chủ sở hữu và dữ liệu trước khi sử dụng. Không xóa hoặc tạo lại một database có sẵn khi chưa biết nó đang phục vụ mục đích gì.

## 3. Tạo tài khoản thực hành riêng

Trong MySQL, một tài khoản được xác định bởi cả tên người dùng và phần host. Vì vậy, `'mysql_lab_user'@'localhost'` và `'mysql_lab_user'@'10.0.0.25'` là hai account identity khác nhau, dù có cùng tên người dùng.

Với ứng dụng hoặc công cụ chạy ngay trên máy MySQL, tạo tài khoản dành cho kết nối cục bộ:

```sql
CREATE USER 'mysql_lab_user'@'localhost'
    IDENTIFIED BY 'replace-with-a-unique-strong-password';
```

Hãy thay chuỗi mật khẩu mẫu bằng mật khẩu mạnh, riêng cho môi trường thực hành. Lệnh trên để MySQL sử dụng cơ chế xác thực mặc định của máy chủ. Không dùng mật khẩu ví dụ trong môi trường thật và không ghi mật khẩu thật vào Git.

Nếu một ứng dụng chạy trên máy khác, hãy tạo account với host đúng là địa chỉ hoặc tên máy nguồn mà MySQL nhìn thấy, ví dụ:

```sql
CREATE USER 'mysql_lab_user'@'10.0.0.25'
    IDENTIFIED BY 'replace-with-a-unique-strong-password';
```

`10.0.0.25` chỉ là địa chỉ minh họa. Cần thay bằng địa chỉ máy khách thực tế và cấp quyền cho đúng account identity đó. Không mặc định dùng host `%`, vì nó cho phép kết nối từ nhiều địa chỉ nguồn; nếu buộc phải dùng trong một lab cô lập, cần giới hạn truy cập bằng mạng và firewall.

## 4. Cấp đúng quyền cần cho bài thực hành

Tài khoản thực hành cần làm việc với bảng và dữ liệu trong `mysql_lab`. Ta cấp các quyền sau ở phạm vi database:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, INDEX
ON mysql_lab.*
TO 'mysql_lab_user'@'localhost';
```

Ý nghĩa của từng quyền:

| Quyền | Công việc được phép |
|---|---|
| `SELECT` | Đọc dữ liệu |
| `INSERT` | Thêm bản ghi |
| `UPDATE` | Cập nhật bản ghi |
| `DELETE` | Xóa bản ghi |
| `CREATE` | Tạo bảng trong database được cấp quyền |
| `ALTER` | Thay đổi cấu trúc bảng |
| `INDEX` | Tạo và xóa chỉ mục |

Các quyền trên đủ cho nhiều bài thực hành thiết kế bảng, truy vấn và thao tác dữ liệu cơ bản. Chúng chỉ áp dụng trong `mysql_lab`, không cấp quyền tương tự trên toàn máy chủ.

Ta cố ý chưa cấp `DROP`, `CREATE USER`, `GRANT OPTION`, `FILE`, `PROCESS` hoặc quyền quản trị toàn cục. `DROP` có thể cho phép xóa các đối tượng trong phạm vi database, vì vậy chỉ cấp khi bài tập thật sự cần và vùng đó là database thử nghiệm có thể tạo lại. Nếu cần thực hành xóa bảng, hãy nhờ quản trị viên chuẩn bị một schema dùng riêng cho bài tập phá hủy dữ liệu và giới hạn quyền `DROP` ở schema đó.

Nếu ứng dụng chỉ cần thao tác trên một bảng đã được tạo sẵn, có thể giới hạn quyền chặt hơn ở cấp bảng. Ví dụ, tài khoản chỉ thao tác dữ liệu trong bảng `customers`:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON mysql_lab.customers
TO 'mysql_lab_user'@'localhost';
```

Trong trường hợp này, không cấp quyền DDL nếu ứng dụng không cần tự tạo hoặc thay đổi cấu trúc bảng. Hãy nhớ thay account host trong câu lệnh `GRANT` cho khớp với account đã tạo ở bước trước.

## 5. Kiểm tra quyền đã cấp

Sau khi tạo user và cấp quyền, dùng tài khoản quản trị để xem grant:

```sql
SHOW GRANTS FOR 'mysql_lab_user'@'localhost';
```

Kết quả thường có một dòng `USAGE ON *.*` và một dòng quyền trên `mysql_lab.*`. `USAGE` biểu thị account tồn tại nhưng tự nó không cấp thêm quyền truy cập. Hãy kiểm tra phạm vi của dòng `GRANT` để chắc chắn không có quyền ngoài ý muốn trên `*.*`.

Đăng nhập bằng tài khoản thực hành:

```bash
mysql --host=localhost --port=3306 --user=mysql_lab_user --password mysql_lab
```

Tùy chọn `--password` khiến client hỏi mật khẩu trong terminal. Không viết mật khẩu trực tiếp sau `--password` vì tham số dòng lệnh có thể bị lưu trong lịch sử hoặc hiển thị trong danh sách tiến trình.

Sau khi đăng nhập, kiểm tra danh tính account và database hiện tại:

```sql
SELECT USER(), CURRENT_USER(), DATABASE();
SHOW GRANTS;
```

`USER()` cho biết tên người dùng và host mà client gửi lên; `CURRENT_USER()` cho biết account mà MySQL thực sự dùng để xác thực và kiểm tra quyền. Hai giá trị này giúp phát hiện trường hợp kết nối khớp với một account host khác dự kiến.

## 6. Thử các thao tác được phép và bị từ chối

Khi đang đăng nhập bằng `mysql_lab_user`, tạo một bảng kiểm tra:

```sql
CREATE TABLE permission_check (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE INDEX idx_permission_check_email
    ON permission_check (email);
```

Hai lệnh trên kiểm tra quyền `CREATE` và `INDEX`. Tiếp tục thử các thao tác dữ liệu trong một transaction để có thể hoàn tác dữ liệu kiểm tra:

```sql
START TRANSACTION;

INSERT INTO permission_check (email)
VALUES ('learner@example.com');

SELECT id, email, created_at
FROM permission_check;

UPDATE permission_check
SET email = 'updated@example.com'
WHERE email = 'learner@example.com';

DELETE FROM permission_check
WHERE email = 'updated@example.com';

ROLLBACK;
```

Các câu lệnh đọc, thêm, sửa và xóa dữ liệu phải thực hiện được. `ROLLBACK` hoàn tác thay đổi trong transaction, giúp bảng không giữ lại bản ghi thử nghiệm. Nếu cần kiểm tra quyền `ALTER`, có thể thêm một cột thử nghiệm:

```sql
ALTER TABLE permission_check
ADD COLUMN note VARCHAR(100) NULL;
```

Tiếp theo, thử các lệnh sau. Với bộ quyền đã cấp ở bước 4, các lệnh này phải bị MySQL từ chối vì account không có quyền tương ứng:

```sql
CREATE DATABASE another_database;
CREATE USER 'another_user'@'localhost' IDENTIFIED BY 'temporary-password';
DROP TABLE mysql_lab.permission_check;
DROP DATABASE mysql_lab;
```

Thông báo lỗi cụ thể có thể khác nhau theo phiên bản và ngữ cảnh, nhưng kết quả mong đợi là account thực hành không thể tạo database, tạo user hoặc xóa bảng/database. Không cần thử lệnh `GRANT` trên môi trường thật; account này cũng không có `GRANT OPTION` để tự cấp quyền cho người khác.

Sau khi hoàn thành, quản trị viên có thể đăng nhập lại và xóa bảng kiểm tra nếu muốn giữ database sạch:

```sql
DROP TABLE IF EXISTS mysql_lab.permission_check;
```

Lệnh dọn dẹp này chạy bằng tài khoản quản trị. Tài khoản thực hành không cần được cấp quyền `DROP` chỉ để quản trị viên dọn dữ liệu kiểm tra.

## 7. Kết nối tài khoản từ ứng dụng Java

Ứng dụng Java kết nối đến MySQL Server qua JDBC driver MySQL Connector/J. Cấu hình kết nối phải dùng đúng username, host và database đã được cấp quyền. Ví dụ URL JDBC cục bộ:

```java
String url = "jdbc:mysql://localhost:3306/mysql_lab";
String username = "mysql_lab_user";
String password = System.getenv("MYSQL_LAB_PASSWORD");

if (password == null || password.isEmpty()) {
    throw new IllegalStateException("MYSQL_LAB_PASSWORD is not configured");
}

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    System.out.println("Connected to MySQL: " + connection.getCatalog());
}
```

Đoạn mã giả định dự án đã khai báo MySQL Connector/J và các kiểu JDBC như `Connection`, `DriverManager` đã được import. Biến môi trường `MYSQL_LAB_PASSWORD` chứa mật khẩu do người chạy ứng dụng cấu hình. Không hard-code mật khẩu thật trong Java, file cấu hình được commit hoặc log.

Nếu dùng Spring Boot, có thể cấu hình URL và username trong file cấu hình, còn mật khẩu lấy từ biến môi trường:

```properties
spring.datasource.url=jdbc:mysql://localhost:3306/mysql_lab
spring.datasource.username=mysql_lab_user
spring.datasource.password=${MYSQL_LAB_PASSWORD}
```

Tài khoản chạy ứng dụng thường xuyên nên chỉ có quyền DML cần cho nghiệp vụ. Nếu ứng dụng cần thay đổi schema khi triển khai, hãy dùng một tài khoản migration riêng trong bước triển khai và không để ứng dụng cấp quyền hoặc tạo user trong lúc chạy bình thường.

## 8. Lưu ý khi kết nối từ Docker hoặc máy khác

Giá trị host trong account MySQL là nguồn kết nối mà máy chủ nhìn thấy, không đơn giản là tên host trong JDBC URL. Ví dụ, nếu ứng dụng chạy trong container Docker còn MySQL chạy ở container hoặc máy khác, `localhost` bên trong container ứng dụng thường trỏ về chính container ứng dụng. Nó không tự trỏ đến MySQL.

Trong môi trường nhiều máy hoặc Docker, cần xác định địa chỉ nguồn mà MySQL nhìn thấy, sau đó tạo account với host phù hợp. Đồng thời kiểm tra:

- MySQL Server đang lắng nghe trên giao diện mạng phù hợp với kiến trúc triển khai.
- Firewall hoặc quy tắc mạng chỉ cho phép máy ứng dụng cần thiết truy cập cổng MySQL.
- Account `user` và `host` trong `CREATE USER`/`GRANT` khớp với kết nối thực tế.
- Kết nối từ xa được bảo vệ bằng TLS khi môi trường và chính sách triển khai yêu cầu.
- Không mở cổng MySQL ra Internet công cộng chỉ để tiện thực hành.

Nếu kết nối từ xa bị từ chối, hãy kiểm tra cả account host và cấu hình mạng. Chỉ đổi host thành `%` không giải quyết đúng nguyên nhân và có thể mở rộng bề mặt truy cập quá mức.

## 9. Thay đổi và thu hồi quyền khi cần

Quyền của tài khoản cần được xem xét khi vai trò thay đổi. Ví dụ, nếu tài khoản không còn cần sửa dữ liệu, quản trị viên có thể thu hồi các quyền ghi:

```sql
REVOKE INSERT, UPDATE, DELETE
ON mysql_lab.*
FROM 'mysql_lab_user'@'localhost';
```

Để thay mật khẩu, dùng `ALTER USER` bằng tài khoản có quyền quản trị user:

```sql
ALTER USER 'mysql_lab_user'@'localhost'
    IDENTIFIED BY 'replace-with-a-new-unique-password';
```

Khi không còn sử dụng tài khoản, quản trị viên có thể xóa account:

```sql
DROP USER 'mysql_lab_user'@'localhost';
```

Các lệnh `CREATE USER`, `GRANT`, `REVOKE` và `ALTER USER` cập nhật hệ thống quyền thông qua cơ chế quản trị của MySQL. Không cần chạy `FLUSH PRIVILEGES` sau những lệnh này. `FLUSH PRIVILEGES` chủ yếu liên quan đến trường hợp chỉnh sửa trực tiếp các bảng quyền hệ thống, việc không nên làm trong quy trình thông thường.

## 10. Xử lý một số lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `Access denied for user` khi đăng nhập | Sai mật khẩu, sai host account hoặc phương thức xác thực không phù hợp | Kiểm tra cặp `user`/`host`, mật khẩu, `CURRENT_USER()` và cấu hình driver |
| Đăng nhập được nhưng không chọn được database | Account chưa được cấp quyền trên database hoặc tên database sai | Chạy `SHOW GRANTS FOR ...` bằng tài khoản quản trị và kiểm tra tên schema |
| Có thể đọc nhưng không thêm hoặc sửa được dữ liệu | Thiếu `INSERT` hoặc `UPDATE`, hoặc quyền chỉ được cấp trên một bảng khác | Kiểm tra phạm vi `ON database.table` và các quyền được liệt kê |
| Không tạo được bảng | Thiếu quyền `CREATE` trên database hoặc đang kết nối nhầm schema | Kiểm tra `DATABASE()`, `SHOW GRANTS` và quyền của account đã khớp host |
| Lệnh quản trị bị từ chối | Tài khoản thực hành không có quyền quản trị user/database hoặc `GRANT OPTION` | Đây là kết quả đúng theo thiết kế quyền tối thiểu; dùng tài khoản quản trị cho tác vụ quản trị |
| Java không kết nối được nhưng CLI kết nối được | JDBC URL, driver, biến môi trường hoặc cấu hình kết nối khác với CLI | So sánh host, port, database, username và lỗi gốc từ Connector/J |

Khi chẩn đoán, hãy phân biệt lỗi kết nối với lỗi quyền. Nếu chưa tạo được phiên kết nối thì kiểm tra mạng, host, mật khẩu và xác thực. Nếu đã kết nối nhưng một câu SQL bị từ chối thì kiểm tra quyền của account thực tế bằng `CURRENT_USER()` và `SHOW GRANTS`.

## 11. Bài tập tự thực hành

1. Đăng nhập bằng tài khoản quản trị và tạo database `mysql_lab`.
2. Tạo account `mysql_lab_user` với host cục bộ, sau đó cấp đúng bảy quyền trong ví dụ.
3. Đăng nhập bằng tài khoản thực hành, chạy `SELECT USER(), CURRENT_USER(), DATABASE()` và ghi lại kết quả.
4. Tạo bảng, tạo chỉ mục, thêm và truy vấn dữ liệu trong `mysql_lab`.
5. Thử tạo database mới và xóa bảng; giải thích vì sao hai thao tác này bị từ chối.
6. Dùng `SHOW GRANTS` để xác nhận account không có quyền toàn cục và không có `GRANT OPTION`.
7. Thử thu hồi quyền `DELETE`, xác minh thao tác xóa bị từ chối, sau đó cấp lại nếu bài thực hành tiếp theo cần quyền đó.
8. Cấu hình một chương trình Java đọc dữ liệu bằng JDBC với mật khẩu lấy từ biến môi trường.

Bạn hoàn thành bài học khi có thể tạo một account thực hành độc lập, giải thích được từng quyền đã cấp, chứng minh được các thao tác ngoài phạm vi bị từ chối và kết nối thành công từ Java hoặc MySQL client. Hãy giữ tài khoản quản trị cho công việc quản trị và dùng account có phạm vi hẹp cho các thao tác hằng ngày.
