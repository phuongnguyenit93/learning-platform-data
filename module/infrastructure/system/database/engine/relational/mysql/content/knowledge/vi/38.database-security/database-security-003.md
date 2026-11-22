# user@host, wildcard và các điều kiện lựa chọn tài khoản

Bài học này thuộc module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ, việc hiểu cách MySQL nhận diện tài khoản là nền tảng để cấu hình quyền truy cập đúng phạm vi.

MySQL không xác định tài khoản chỉ bằng tên người dùng. Một tài khoản được định danh bởi **cặp tên người dùng và máy chủ nguồn** (`user` và `host`). Khi client kết nối, MySQL so khớp thông tin đăng nhập cùng nơi kết nối phát sinh với các tài khoản đã khai báo, chọn một tài khoản phù hợp rồi mới xác thực và áp dụng quyền của tài khoản đó. Hiểu thứ tự so khớp giúp tránh các lỗi như đăng nhập bằng tài khoản ẩn danh, dùng nhầm bộ quyền hoặc mở quyền truy cập rộng hơn dự kiến.

## 1. Tài khoản MySQL là một cặp `user` và `host`

Tên tài khoản thường được viết theo dạng:

```sql
'user_name'@'host_name'
```

Ví dụ:

```sql
'app'@'localhost'
'app'@'192.0.2.17'
'app'@'192.0.2.0/24'
'app'@'%'
```

Hai phần có ý nghĩa khác nhau:

- `user_name` là tên tài khoản mà client gửi khi đăng nhập.
- `host_name` xác định máy chủ, địa chỉ IP hoặc mẫu địa chỉ được phép kết nối với tài khoản đó.

Vì vậy, `'app'@'localhost'` và `'app'@'192.0.2.17'` là **hai tài khoản riêng biệt**, dù cùng có tên người dùng `app`. Mỗi tài khoản có thể có mật khẩu, plugin xác thực, trạng thái khóa và tập quyền khác nhau. Một tài khoản `app` chỉ được tạo cho `localhost` không mặc nhiên cho phép kết nối từ một máy khác.

Ví dụ tạo hai tài khoản cùng tên nhưng giới hạn nguồn kết nối khác nhau:

```sql
CREATE USER 'app'@'localhost'
  IDENTIFIED BY 'replace-with-a-secret';

CREATE USER 'app'@'192.0.2.17'
  IDENTIFIED BY 'replace-with-another-secret';

GRANT SELECT, INSERT, UPDATE
  ON shop.* TO 'app'@'localhost';

GRANT SELECT
  ON shop.* TO 'app'@'192.0.2.17';
```

Kết nối từ máy cục bộ sẽ dùng tài khoản `app@localhost`; kết nối từ địa chỉ `192.0.2.17` sẽ dùng tài khoản tương ứng với địa chỉ đó. Quyền của hai tài khoản không được gộp lại.

MySQL cũng hỗ trợ **tài khoản ẩn danh**: phần `user_name` là chuỗi rỗng, ví dụ `''@'localhost'`. Tài khoản này có thể khớp với kết nối không có tên người dùng tương ứng trong bảng tài khoản, vì thế cần kiểm tra và quản lý cẩn thận. Phần `user_name` không dùng `%` và `_` như wildcard để khớp nhiều tên người dùng; các ký tự này chỉ có ý nghĩa wildcard trong phần `host_name`.

## 2. Wildcard trong phần `host`

MySQL cho phép dùng một số ký tự đại diện trong phần host của tài khoản:

| Ký tự | Ý nghĩa | Ví dụ |
|---|---|---|
| `%` | Khớp với chuỗi gồm không, một hoặc nhiều ký tự | `'app'@'10.20.%'` |
| `_` | Khớp với đúng một ký tự | `'app'@'db_.example.net'` |

Ví dụ, tài khoản `'app'@'10.20.%'` có thể khớp với client có địa chỉ host bắt đầu bằng `10.20.`. Mẫu này là so khớp chuỗi, không phải phép kiểm tra subnet theo CIDR. Không nên xem `10.20.%` là cách biểu diễn mạng chính xác trong mọi tình huống, đặc biệt khi cần giới hạn một dải IP rõ ràng.

Từ MySQL **8.0.35**, việc dùng `%` và `_` trong giá trị host được đánh dấu deprecated. Với hệ thống mới, nên ưu tiên khai báo host/IP cụ thể hoặc dùng cú pháp mạng được phiên bản MySQL hỗ trợ. Nếu cần giới hạn theo subnet IPv4, có thể dùng netmask; MySQL 8.0.23 trở lên hỗ trợ thêm cách viết CIDR:

```sql
-- CIDR, được hỗ trợ từ MySQL 8.0.23
CREATE USER 'app'@'192.0.2.0/24'
  IDENTIFIED BY 'replace-with-a-secret';

-- Cách viết netmask IPv4
CREATE USER 'app'@'192.0.2.0/255.255.255.0'
  IDENTIFIED BY 'replace-with-a-secret';
```

Chọn cú pháp phù hợp với phiên bản máy chủ đang vận hành và kiểm tra lại bằng cách kết nối từ một địa chỉ nằm trong, cũng như ngoài, dải mạng dự kiến.

### `localhost` và `127.0.0.1` không phải lúc nào cũng tương đương

Trên các hệ thống Unix/Linux, client thường dùng Unix socket khi chỉ định `localhost`, trong khi `127.0.0.1` thường tạo kết nối TCP/IP. Do đó, hai kết nối này có thể khớp với hai tài khoản khác nhau:

```sql
CREATE USER 'app'@'localhost' IDENTIFIED BY 'replace-with-a-secret';
CREATE USER 'app'@'127.0.0.1' IDENTIFIED BY 'replace-with-another-secret';
```

Khi cần kiểm tra sự khác biệt, hãy chỉ định giao thức rõ ràng ở client:

```bash
# Kết nối qua Unix socket (nếu client và máy chủ hỗ trợ)
mysql --protocol=SOCKET -u app -p

# Kết nối TCP tới loopback
mysql --protocol=TCP -h 127.0.0.1 -u app -p
```

Không nên suy luận tài khoản được chọn chỉ từ việc client và MySQL Server nằm trên cùng một máy; hãy kiểm tra danh tính thực tế sau khi đăng nhập.

## 3. MySQL chọn tài khoản phù hợp như thế nào?

Trong giai đoạn kiểm tra kết nối, MySQL đối chiếu tên người dùng do client cung cấp và host nguồn mà máy chủ nhận diện được với các dòng tài khoản. Có thể hình dung quá trình theo các bước:

1. Client gửi tên người dùng và thực hiện kết nối từ một địa chỉ nguồn.
2. MySQL xác định host/IP của client. Việc phân giải tên máy phụ thuộc cấu hình `skip_name_resolve`.
3. MySQL tìm các dòng tài khoản có cả `User` và `Host` phù hợp.
4. Máy chủ xét các dòng có host cụ thể trước host rộng hơn. Host/IP khớp chính xác được ưu tiên; các mẫu có wildcard được sắp theo mức độ cụ thể, mẫu rộng như `%` thường đứng sau.
5. Với cùng một giá trị `Host`, tài khoản có tên người dùng cụ thể được ưu tiên hơn tài khoản ẩn danh có `User` rỗng.
6. Dòng phù hợp đầu tiên được chọn để xác thực. Nếu xác thực thất bại, MySQL không tiếp tục thử một dòng ít cụ thể hơn.

Điểm quan trọng là **Host được xét trước User**. Vì vậy, một tài khoản ẩn danh gắn với host rất cụ thể có thể được chọn trước tài khoản có tên người dùng rõ ràng nhưng chỉ khai báo với host rộng.

Ví dụ, giả sử có hai tài khoản:

```sql
CREATE USER 'report'@'%'
  IDENTIFIED BY 'replace-with-a-secret';

CREATE USER ''@'localhost'
  IDENTIFIED BY 'replace-with-another-secret';
```

Khi client gửi tên `report` từ `localhost`, dòng `''@'localhost'` có host cụ thể hơn `report@%`, nên có thể được chọn. Kết quả là kết nối được xác thực theo tài khoản ẩn danh. Nếu đồng thời tồn tại `report@localhost`, tài khoản có tên `report` sẽ được ưu tiên hơn tài khoản ẩn danh vì hai dòng có cùng Host.

Một số hệ quả cần nhớ:

- `app@localhost` có thể được chọn trước `app@%` khi kết nối từ máy cục bộ.
- `app@192.0.2.17` có thể được chọn trước `app@192.0.2.0/24` hoặc `app@%` nếu tất cả đều khớp.
- Tài khoản được chọn quyết định phương thức xác thực và quyền truy cập; MySQL không cộng quyền từ các dòng tài khoản khác có cùng tên người dùng.
- Nếu mật khẩu hoặc phương thức xác thực của dòng được chọn không hợp lệ, máy chủ không tự chuyển sang tài khoản rộng hơn để thử lại.

## 4. Ảnh hưởng của phân giải tên máy

Nếu `skip_name_resolve` tắt, MySQL có thể phân giải địa chỉ IP của client thành tên máy để so khớp với các giá trị host dạng hostname. Việc này phụ thuộc DNS và cấu hình mạng; thay đổi DNS có thể làm hành vi kết nối khác đi.

Khi `skip_name_resolve` bật, máy chủ không thực hiện phân giải tên máy cho kết nối client. Trong trường hợp đó, nên dùng địa chỉ IP hoặc subnet phù hợp trong phần Host; tài khoản `localhost` vẫn là trường hợp đặc biệt được hỗ trợ. Có thể kiểm tra cấu hình bằng:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

Ngoài ra, máy chủ chỉ nhìn thấy địa chỉ của peer kết nối trực tiếp tới nó. Nếu ứng dụng đi qua NAT, proxy, load balancer hoặc gateway của môi trường container, địa chỉ nguồn MySQL nhìn thấy có thể là địa chỉ của thành phần trung gian. Khi cấu hình `user@host`, hãy căn cứ vào địa chỉ thực tế mà MySQL nhận được, không chỉ căn cứ vào IP của máy người dùng cuối.

## 5. Xác minh tài khoản nào đang được sử dụng

Hai hàm `USER()` và `CURRENT_USER()` giúp phân biệt thông tin kết nối với tài khoản MySQL đã chọn:

```sql
SELECT
  USER() AS client_identity,
  CURRENT_USER() AS matched_account;
```

- `USER()` cho biết tên người dùng và host của client trong kết nối hiện tại.
- `CURRENT_USER()` cho biết tài khoản MySQL được dùng để kiểm tra quyền. Nếu một tài khoản ẩn danh được chọn, kết quả có thể có dạng `@localhost` dù client gửi tên `report`.

Sau khi xác định tài khoản, kiểm tra quyền đang áp dụng:

```sql
SHOW GRANTS;

-- Kiểm tra định nghĩa và quyền của một tài khoản cụ thể
SHOW CREATE USER 'app'@'192.0.2.17';
SHOW GRANTS FOR 'app'@'192.0.2.17';
```

Để rà soát các tài khoản có cùng tên hoặc tài khoản ẩn danh, người quản trị có thể đọc bảng hệ thống `mysql.user` nếu có đủ quyền:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
WHERE User IN ('app', '');
```

Chỉ dùng bảng này để kiểm tra. Hãy quản lý tài khoản và quyền bằng các câu lệnh như `CREATE USER`, `ALTER USER`, `DROP USER`, `GRANT` và `REVOKE`, không cập nhật trực tiếp bảng hệ thống.

## 6. Thiết kế tài khoản theo nguyên tắc quyền tối thiểu

Khi thiết kế quyền truy cập cho ứng dụng, nên áp dụng các nguyên tắc sau:

1. **Giới hạn host theo nhu cầu thực tế.** Ưu tiên IP máy ứng dụng hoặc subnet đã xác định. Chỉ dùng `%` khi thực sự cần chấp nhận kết nối từ nhiều nguồn và đã có biện pháp kiểm soát mạng bổ sung.
2. **Tách tài khoản theo ứng dụng và môi trường.** Tài khoản chạy ứng dụng, tài khoản báo cáo, tài khoản migration và tài khoản quản trị nên có định danh cùng quyền riêng. Tránh dùng chung một tài khoản quản trị cho mọi dịch vụ.
3. **Cấp đúng quyền trên đúng schema.** Ví dụ, dịch vụ xử lý đơn hàng có thể cần `SELECT`, `INSERT`, `UPDATE` trên `orders_db.*`, trong khi dịch vụ báo cáo chỉ cần `SELECT`.
4. **Đồng bộ cấu hình DNS và `skip_name_resolve`.** Nếu máy chủ không phân giải tên, đừng dựa vào hostname trong các dòng tài khoản.
5. **Kiểm thử từ đúng đường mạng của ứng dụng.** Kết nối từ máy quản trị hoặc từ localhost không chứng minh rằng tài khoản sẽ khớp giống hệt khi ứng dụng đi qua proxy hay NAT.
6. **Rà soát tài khoản ẩn danh và tài khoản cũ.** Xác minh mục đích sử dụng trước khi khóa hoặc xóa; không giữ tài khoản rộng chỉ vì một kết nối cũ đang phụ thuộc vào nó.

Ví dụ cấu hình hai vai trò với phạm vi host và quyền khác nhau:

```sql
-- Dịch vụ ghi đơn hàng: chỉ nhận từ một máy ứng dụng
CREATE USER 'orders_api'@'192.0.2.17'
  IDENTIFIED BY 'replace-with-a-secret';

GRANT SELECT, INSERT, UPDATE
  ON orders_db.* TO 'orders_api'@'192.0.2.17';

-- Dịch vụ báo cáo: nhận từ subnet IPv4 đã xác định
-- Cú pháp CIDR yêu cầu MySQL 8.0.23 trở lên
CREATE USER 'orders_report'@'192.0.2.0/24'
  IDENTIFIED BY 'replace-with-another-secret';

GRANT SELECT
  ON orders_db.* TO 'orders_report'@'192.0.2.0/24';
```

Các chuỗi mật khẩu trong ví dụ chỉ là giá trị thay thế. Khi triển khai, hãy dùng bí mật riêng, đủ mạnh và lưu trong hệ thống quản lý secret của môi trường.

## 7. Quy trình xử lý lỗi không khớp tài khoản

Khi gặp lỗi `Access denied`, hãy kiểm tra theo thứ tự sau để tìm đúng nguyên nhân:

1. Xác nhận client đang gửi tên người dùng nào và kết nối qua socket hay TCP.
2. Xác định địa chỉ nguồn mà MySQL nhìn thấy; kiểm tra NAT, proxy hoặc gateway nếu có.
3. Kiểm tra các dòng tài khoản có cùng `User`, bao gồm cả `User` rỗng, và so sánh độ cụ thể của `Host`.
4. Kiểm tra `skip_name_resolve` nếu tài khoản dùng hostname.
5. Sau khi đăng nhập được, chạy `SELECT USER(), CURRENT_USER();` để biết tài khoản thực sự được chọn.
6. Dùng `SHOW GRANTS;` để kiểm tra quyền của tài khoản đó, sau đó điều chỉnh đúng dòng tài khoản bằng câu lệnh quản trị phù hợp.

Không nên khắc phục bằng cách tạo thêm một tài khoản `user@'%'` ngay lập tức. Cách đó có thể che khuất lỗi khớp host và mở rộng bề mặt truy cập. Hãy tìm ra host thực tế, dòng tài khoản được chọn và quyền cần thiết trước khi thay đổi cấu hình.

## 8. Tự kiểm tra

Giả sử máy chủ có các tài khoản sau:

```sql
'api'@'localhost'
'api'@'192.0.2.17'
'api'@'192.0.2.0/24'
'api'@'%'
''@'localhost'
```

Hãy tự trả lời các câu hỏi:

1. Client đăng nhập bằng tên `api` từ `192.0.2.17` sẽ khớp tài khoản nào?
2. Client đăng nhập bằng tên `api` từ một IP khác trong subnet `192.0.2.0/24` sẽ khớp tài khoản nào?
3. Nếu kết nối từ localhost nhưng không có dòng `api@localhost`, tài khoản ẩn danh có thể ảnh hưởng thế nào?
4. Vì sao quyền của `api@%` không tự động được cộng vào quyền của `api@localhost`?
5. Khi `skip_name_resolve` bật, cần thay đổi gì nếu tài khoản hiện tại đang dựa trên hostname?

Đáp án cần dựa trên thứ tự ưu tiên host cụ thể, sau đó xét tên người dùng khi Host bằng nhau. Với kết nối từ `192.0.2.17`, tài khoản IP chính xác được ưu tiên; với IP khác trong subnet, tài khoản subnet được xét trước `%`. Với localhost, tài khoản host cụ thể có thể khiến tài khoản ẩn danh được chọn nếu không có tài khoản `api@localhost`. Quyền luôn thuộc về dòng tài khoản được chọn, không được hợp nhất từ các dòng còn lại.
