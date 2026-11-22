# Tài khoản dạng user@host và cách MySQL lựa chọn tài khoản khớp

Bài học thuộc chương **Công cụ và kết nối** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Trong các nội dung đó, tài khoản MySQL là lớp kiểm soát đầu tiên: máy khách phải xác thực bằng đúng tài khoản được phép kết nối từ vị trí của nó, sau đó mới được xét quyền đọc hoặc thay đổi dữ liệu.

Sau bài này, bạn có thể đọc và tạo tài khoản theo dạng `'user'@'host'`, phân biệt các tài khoản có cùng tên nhưng khác máy kết nối, giải thích cách MySQL chọn một bản ghi khi nhiều tài khoản cùng khớp, và chẩn đoán các tình huống đăng nhập nhầm tài khoản.

## 1. Một tài khoản MySQL gồm hai phần

MySQL không xác định tài khoản chỉ bằng tên người dùng. Một tài khoản được định danh bởi **tên người dùng** và **máy chủ hoặc địa chỉ nguồn mà người dùng kết nối từ đó**:

```sql
'user_name'@'host_name'
```

Ví dụ:

- `'app'@'localhost'`: tài khoản `app` dành cho kết nối cục bộ.
- `'app'@'192.0.2.15'`: tài khoản `app` dành cho máy có địa chỉ IP được chỉ định.
- `'app'@'db-client.example.com'`: tài khoản `app` dành cho máy có tên host tương ứng.
- `'app'@'192.0.2.0/24'`: tài khoản `app` dành cho các địa chỉ thuộc mạng IPv4 có tiền tố CIDR `/24`.

Như vậy, hai tài khoản sau là hai tài khoản độc lập, có thể dùng mật khẩu, plugin xác thực và quyền khác nhau:

```sql
'app'@'localhost'
'app'@'192.0.2.15'
```

Tài khoản `'app'@'localhost'` có thể chỉ được đọc dữ liệu trên máy chủ ứng dụng cục bộ, trong khi `'app'@'192.0.2.15'` được cấp quyền ghi cho một máy ứng dụng cụ thể. Cùng tên `app` không có nghĩa là hai kết nối được hưởng cùng quyền.

Tên tài khoản hệ điều hành cũng không quyết định tên tài khoản MySQL. Một người đăng nhập Windows hoặc Linux bằng tên `minh` vẫn có thể kết nối MySQL bằng `-u app`, nếu tài khoản MySQL tương ứng tồn tại và được phép kết nối.

Khi MySQL so khớp tài khoản, phần `User` được so sánh phân biệt chữ hoa và chữ thường; phần `Host` không phân biệt hoa thường. Phần `User` phải khớp theo tên cụ thể hoặc là chuỗi rỗng để đại diện anonymous, không dùng `%` hay `_` làm wildcard cho tên người dùng.

### Cách viết và trích dẫn tên tài khoản

Hai phần được trích dẫn riêng, không gộp thành một chuỗi:

```sql
-- Đúng: user và host là hai phần riêng
CREATE USER 'app'@'localhost' IDENTIFIED BY 'change_this_password';

-- Không phải cách viết tương đương:
-- 'app@localhost'
```

Phần host có thể được bỏ qua trong một số câu lệnh. Khi đó, tên tài khoản chỉ gồm user được hiểu tương đương với host `%`, tức mọi host. Vì phạm vi này rộng và wildcard host đã bị deprecated, hãy luôn ghi rõ host khi tạo tài khoản mới.

### Tài khoản anonymous

Nếu phần user là chuỗi rỗng, MySQL xem đó là tài khoản anonymous (người dùng ẩn danh):

```sql
''@'localhost'
```

Tài khoản này không có tên người dùng cụ thể nhưng vẫn có phần host và cơ chế xác thực, quyền riêng. Khi một kết nối được xác thực bằng tài khoản anonymous, `CURRENT_USER()` trả về chuỗi bắt đầu bằng `@`, chẳng hạn `@localhost`.

Trong hệ thống thực tế, nên rà soát và loại bỏ tài khoản anonymous nếu không có nhu cầu rõ ràng. Tài khoản này dễ khiến người quản trị hiểu nhầm rằng máy khách đã đăng nhập bằng tài khoản có tên mà họ nhập.

## 2. Phần host có thể biểu diễn như thế nào?

Phần host giới hạn nơi máy khách được phép kết nối. MySQL hỗ trợ tên máy, địa chỉ IP và một số dạng chỉ định mạng.

| Dạng host | Ý nghĩa | Ví dụ |
|---|---|---|
| Tên máy | Kết nối từ host có tên được phân giải tương ứng | `'client01.example.com'` |
| IPv4 cụ thể | Kết nối từ một địa chỉ IPv4 | `'192.0.2.15'` |
| IPv6 cụ thể | Kết nối từ một địa chỉ IPv6 | `'2001:db8::15'` |
| CIDR IPv4 | Kết nối từ một mạng có độ dài tiền tố xác định | `'192.0.2.0/24'` |
| IPv4 kèm subnet mask | Kết nối từ mạng được xác định bằng subnet mask | `'192.0.2.0/255.255.255.0'` |
| Wildcard | Khớp nhiều host theo mẫu | `'%.example.com'`, `'%'` |

### Địa chỉ cụ thể và mạng CIDR

Nếu ứng dụng chạy từ một máy có IP ổn định, khai báo đúng địa chỉ nguồn giúp giới hạn quyền truy cập:

```sql
CREATE USER 'billing_app'@'192.0.2.15'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON billing.*
    TO 'billing_app'@'192.0.2.15';
```

Nếu có nhiều máy ứng dụng nằm trong cùng một mạng, có thể dùng CIDR thay vì tạo từng tài khoản host riêng:

```sql
CREATE USER 'report_app'@'192.0.2.0/24'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT
    ON reporting.*
    TO 'report_app'@'192.0.2.0/24';
```

Tiền tố `/24` biểu thị 24 bit đầu của địa chỉ IPv4 dùng để xác định mạng. Với ví dụ trên, mạng có dải địa chỉ từ `192.0.2.0` đến `192.0.2.255`. Hãy dùng đúng dải mạng thực tế của ứng dụng; không mở rộng dải chỉ để khắc phục nhanh lỗi kết nối.

### Wildcard host và lý do nên tránh trong tài khoản mới

MySQL cho phép ký tự `%` và `_` trong phần host để khớp nhiều tên máy hoặc địa chỉ IP. Ví dụ:

- `'%.example.com'`: các host có hậu tố `.example.com`.
- `'198.51.100.%'`: mẫu địa chỉ trong dải `198.51.100.*`.
- `'%'`: mọi host.

Tuy nhiên, wildcard `%` và `_` trong phần host đã bị đánh dấu deprecated và có thể bị loại bỏ trong phiên bản tương lai. Vì vậy, hãy ưu tiên host cụ thể, địa chỉ IP, CIDR hoặc subnet mask. Tài khoản `'app'@'%'` trong các hệ thống cũ vẫn cần được nhận diện khi kiểm tra quy tắc khớp, nhưng không nên sao chép nó làm cấu hình mặc định cho hệ thống mới.

Giá trị host rỗng `''` cũng có nghĩa là mọi host và có độ ưu tiên thấp hơn `%`. Không nên tạo tài khoản có host rỗng.

## 3. MySQL chọn tài khoản nào khi có nhiều bản ghi khớp?

Đây là phần quan trọng nhất của bài học.

Khi máy khách kết nối, MySQL phải tìm một hàng tài khoản trong bảng hệ thống `mysql.user` có phần `User` và `Host` phù hợp. Nếu có nhiều hàng cùng khớp, MySQL không chọn ngẫu nhiên theo thứ tự mà người quản trị tạo tài khoản. Máy chủ sắp xếp các hàng theo quy tắc ưu tiên, sau đó dùng **hàng khớp đầu tiên**.

Quá trình khái quát:

1. Máy khách gửi yêu cầu kết nối với tên user, thông tin xác thực và kết nối từ một host/IP.
2. MySQL xác định thông tin host của máy khách theo cơ chế phân giải tên máy đang cấu hình.
3. Máy chủ xét các hàng tài khoản theo thứ tự đã sắp xếp.
4. Hàng đầu tiên có cả user và host khớp sẽ được chọn.
5. Máy chủ kiểm tra thông tin xác thực và trạng thái khóa tài khoản. Nếu xác thực thành công, kết nối được chấp nhận và quyền của hàng tài khoản đã chọn được áp dụng.

### Ưu tiên của Host

MySQL sắp xếp host cụ thể hơn trước host tổng quát hơn. Các trường hợp quan trọng:

| Mức ưu tiên | Ví dụ phần host | Cách hiểu |
|---|---|---|
| Cao nhất | `localhost`, `192.0.2.15`, tên host cụ thể | Host hoặc IP khớp chính xác |
| Tiếp theo | IP kèm tiền tố CIDR | Khớp mạng theo độ dài tiền tố |
| Tiếp theo | IP kèm subnet mask | Khớp mạng theo subnet mask |
| Thấp | `%` | Mọi host |
| Thấp nhất | `''` | Mọi host; đứng sau `%` |

Với nhiều mạng CIDR, mạng có phạm vi hẹp hơn thường cụ thể hơn mạng bao phủ phạm vi rộng hơn. Hãy tránh tạo nhiều hàng có độ cụ thể ngang nhau nhưng quyền khác nhau để không phụ thuộc vào thứ tự không xác định.

### Ưu tiên của User

Chỉ khi các hàng có cùng giá trị `Host`, MySQL mới xét độ cụ thể của `User`:

- User có tên cụ thể được ưu tiên trước user rỗng.
- User rỗng là anonymous, có thể khớp bất kỳ tên user nào.
- Nếu cả Host và User có độ cụ thể ngang nhau, thứ tự giữa các hàng không được bảo đảm. Tránh tạo cấu hình phụ thuộc vào trường hợp này.

**Điểm cần nhớ:** độ cụ thể của Host được xét trước độ cụ thể của User. Vì thế, một tài khoản anonymous với host cụ thể có thể được chọn trước tài khoản có tên user nhưng host là wildcard rộng.

## 4. Ví dụ: tài khoản anonymous che khuất tài khoản có tên

Giả sử trên MySQL Server có hai tài khoản:

```sql
-- Tài khoản app được phép kết nối từ mọi host
CREATE USER 'app'@'%'
    IDENTIFIED BY 'app_password';

-- Tài khoản anonymous chỉ dành cho kết nối cục bộ
CREATE USER ''@'localhost'
    IDENTIFIED BY 'anonymous_password';
```

Khi máy khách kết nối từ một kết nối cục bộ phù hợp với `localhost` và gửi tên user `app`, cả hai hàng đều có thể là ứng viên:

| Tài khoản | User có khớp? | Host có khớp kết nối cục bộ? | Độ cụ thể |
|---|---|---|---|
| `'app'@'%'` | Có, tên user là app | Có, wildcard khớp | Host ít cụ thể |
| `''@'localhost'` | Có, user rỗng khớp mọi tên | Có, host localhost cụ thể | Host cụ thể hơn |

MySQL ưu tiên hàng `''@'localhost'` vì Host cụ thể hơn `%`. Kết nối có thể được xác thực bằng tài khoản anonymous, dù người dùng đã nhập tên `app`. Kết quả là quyền nhận được không phải quyền của `'app'@'%'`.

Máy khách vẫn phải cung cấp thông tin xác thực của hàng được chọn. Trong ví dụ này, nếu MySQL chọn `''@'localhost'`, mật khẩu phải khớp với `anonymous_password`. Nếu máy khách gửi `app_password` nhưng hàng anonymous đang được chọn, xác thực sẽ thất bại; MySQL không tự chuyển sang thử mật khẩu của hàng `'app'@'%'` sau khi đã chọn hàng khớp đầu tiên.

Có thể phát hiện trường hợp này bằng cách chạy trong phiên kết nối:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS matched_account;
```

Ví dụ kết quả:

```text
+-----------------+-----------------+
| client_identity | matched_account |
+-----------------+-----------------+
| app@localhost   | @localhost      |
+-----------------+-----------------+
```

Ở đây:

- `USER()` cho biết tên user mà máy khách gửi và host của kết nối.
- `CURRENT_USER()` cho biết tài khoản MySQL thực sự được dùng để xác thực và xác định quyền.

Nếu cả hai tài khoản đều có cùng host cụ thể, ví dụ `'app'@'localhost'` và `''@'localhost'`, tài khoản có tên `app` được ưu tiên hơn anonymous vì Host ngang nhau nhưng User cụ thể hơn.

Ví dụ:

```sql
CREATE USER 'app'@'localhost'
    IDENTIFIED BY 'app_local_password';
```

Sau khi tạo tài khoản này, kết nối cục bộ với user `app` sẽ khớp hàng `'app'@'localhost'` trước hàng anonymous có cùng Host.

## 5. Phân biệt localhost, 127.0.0.1 và kết nối TCP

Ba cách viết dưới đây có liên quan nhưng không nên mặc định coi là giống hệt nhau:

- `localhost`: tên host chỉ máy cục bộ. Trên Unix, MySQL client thường dùng Unix socket khi kết nối tới `localhost`, trừ khi tham số kết nối buộc dùng TCP/IP. Trên Windows, kết nối cục bộ cũng có thể dùng named pipe hoặc shared memory tùy cấu hình.
- `127.0.0.1`: địa chỉ IPv4 loopback.
- `::1`: địa chỉ IPv6 loopback.

Kết nối qua socket hoặc named pipe được xem là kết nối cục bộ và khớp host `localhost` nếu tài khoản phù hợp tồn tại. Với TCP, MySQL có thể phân giải IP của máy khách thành tên host thông qua DNS hoặc host cache. Theo cấu hình mặc định, kết nối tới `127.0.0.1` thường được phân giải thành `localhost`; hành vi có thể khác khi bật `skip_name_resolve`.

Để kiểm tra một kết nối TCP tới loopback, có thể chỉ định rõ giao thức:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app --password
```

Để kết nối cục bộ theo cách mặc định của client:

```bash
mysql --host=localhost --user=app --password
```

Hai lệnh có thể khớp các hàng tài khoản khác nhau tùy hệ điều hành, giao thức, DNS và cấu hình Server. Khi chẩn đoán, đừng chỉ nhìn vào chuỗi host trên lệnh client; hãy chạy `USER()` và `CURRENT_USER()` trong chính phiên kết nối.

### Ảnh hưởng của skip_name_resolve

Biến hệ thống `skip_name_resolve` điều khiển việc máy chủ có phân giải tên host khi kiểm tra kết nối hay không.

Kiểm tra trạng thái:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

- Khi `OFF`, MySQL thực hiện phân giải tên host để đối chiếu với phần Host của tài khoản.
- Khi `ON`, MySQL chỉ dùng địa chỉ IP để khớp máy khách; các hàng tài khoản dùng hostname có thể không được sử dụng. Cần chuẩn bị tài khoản có Host là IP phù hợp trước khi bật cấu hình này.
- Kết nối cục bộ cần được kiểm tra riêng theo giao thức và nền tảng; không nên suy luận rằng mọi trường hợp `localhost` sẽ hoạt động giống nhau.

Nếu vừa bật `skip_name_resolve` vừa chỉ tạo tài khoản theo tên máy, ứng dụng có thể mất khả năng đăng nhập. Đây là thay đổi cấu hình cần kiểm tra trên môi trường thử nghiệm và có phương án khôi phục trước khi triển khai.

## 6. Tạo tài khoản và cấp quyền đúng phạm vi

Tạo tài khoản và cấp quyền là hai thao tác riêng. `CREATE USER` tạo danh tính và thông tin xác thực; `GRANT` cấp quyền trên phạm vi database, bảng hoặc đối tượng. Nên tạo user trước rồi cấp đúng các quyền mà ứng dụng cần.

Ví dụ tạo tài khoản ứng dụng chỉ kết nối từ máy chủ ứng dụng cụ thể:

```sql
CREATE USER 'orders_app'@'192.0.2.25'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON orders.*
    TO 'orders_app'@'192.0.2.25';

SHOW GRANTS FOR 'orders_app'@'192.0.2.25';
```

Tài khoản này được phép đọc, thêm và cập nhật dữ liệu trong database `orders` từ host `192.0.2.25`. Nó không tự có quyền xóa dữ liệu, tạo user, thay đổi cấu trúc bảng hay truy cập database khác.

Nếu cần cho một nhóm máy thuộc mạng ứng dụng:

Ví dụ CIDR dưới đây là một phương án thay thế cho tài khoản IP cụ thể ở trên. Chọn phạm vi phù hợp với kiến trúc thực tế; chỉ tạo đồng thời cả hai khi chủ đích là cấp quyền khác nhau cho một máy riêng và phần còn lại của mạng.

```sql
CREATE USER 'orders_app'@'192.0.2.0/24'
    IDENTIFIED BY 'replace_with_a_strong_password';

GRANT SELECT, INSERT, UPDATE
    ON orders.*
    TO 'orders_app'@'192.0.2.0/24';
```

Không tạo cả hai tài khoản cùng tên một cách tùy tiện. Nếu một tài khoản host cụ thể và một tài khoản CIDR cùng khớp, host cụ thể hơn sẽ được chọn. Điều này có thể là chủ ý để máy chủ đặc biệt nhận quyền khác, nhưng cần được ghi lại và kiểm tra.

### Xem các tài khoản cùng tên

Tài khoản được lưu trong bảng hệ thống `mysql.user`. Người quản trị có thể kiểm tra các cặp user-host hiện có:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked
FROM mysql.user
WHERE User = 'orders_app'
ORDER BY Host;
```

Truy vấn này cần quyền đọc bảng hệ thống tương ứng. Chỉ xem thông tin cần thiết để kiểm tra cấu hình; không truy xuất hoặc chia sẻ giá trị hash mật khẩu.

Xem quyền của một tài khoản cụ thể:

```sql
SHOW GRANTS FOR 'orders_app'@'192.0.2.25';
```

Nếu muốn thay đổi quyền, dùng `GRANT` hoặc `REVOKE`; nếu muốn thay đổi mật khẩu, dùng `ALTER USER`. Không chỉnh sửa trực tiếp các bảng grant trong database `mysql`.

Ví dụ thu hồi quyền cập nhật:

```sql
REVOKE UPDATE
    ON orders.*
    FROM 'orders_app'@'192.0.2.25';
```

Xóa tài khoản khi ứng dụng không còn sử dụng:

```sql
DROP USER IF EXISTS 'orders_app'@'192.0.2.25';
```

Lệnh `DROP USER` tác động tới đúng cặp user-host được chỉ định. Xóa `'orders_app'@'192.0.2.25'` không đồng nghĩa xóa `'orders_app'@'192.0.2.0/24'`.

## 7. Quy trình chẩn đoán khi đăng nhập sai hoặc bị từ chối

Khi ứng dụng không thể kết nối, hãy kiểm tra từ thông tin cụ thể thay vì thử đổi host thành `%` ngay lập tức.

### Bước 1: Ghi lại thông tin kết nối

Thu thập các giá trị:

- User mà ứng dụng truyền cho MySQL.
- Host hoặc IP nguồn thực tế của máy chạy ứng dụng.
- Host đích, port và giao thức kết nối.
- Tên database mà ứng dụng muốn truy cập.
- Thông báo lỗi đầy đủ, không kèm mật khẩu hoặc thông tin bí mật.

### Bước 2: Phân biệt lỗi không có hàng khớp và lỗi xác thực

Một số lỗi thường gặp:

| Thông báo hoặc hiện tượng | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `Host ... is not allowed to connect` | Không có hàng tài khoản có Host khớp máy khách | Kiểm tra Host, DNS, IP nguồn, CIDR và `skip_name_resolve` |
| `Access denied for user ...` | Có thể sai mật khẩu, sai plugin xác thực, tài khoản bị khóa hoặc tài khoản được chọn khác dự kiến | Kiểm tra user-host cụ thể, trạng thái khóa, plugin và thông tin xác thực |
| Kết nối thành công nhưng thiếu quyền | Xác thực thành công nhưng tài khoản được chọn không có quyền cần thiết | Chạy `CURRENT_USER()` và `SHOW GRANTS` cho tài khoản được chọn |
| `USER()` và `CURRENT_USER()` khác nhau | Máy chủ đã xác thực bằng một tài khoản khác với tên client gửi | Kiểm tra anonymous user và độ cụ thể của Host |

### Bước 3: Kiểm tra tài khoản thực sự được chọn

Nếu đăng nhập được, chạy:

```sql
SELECT USER(), CURRENT_USER();
SHOW VARIABLES LIKE 'skip_name_resolve';
```

Sau đó dùng kết quả `CURRENT_USER()` làm căn cứ kiểm tra quyền:

```sql
SHOW GRANTS FOR 'user_thuc_te'@'host_thuc_te';
```

Thay hai phần bằng đúng giá trị tài khoản mà `CURRENT_USER()` trả về. Nếu tài khoản là anonymous, phần user sẽ rỗng, ví dụ:

```sql
SHOW GRANTS FOR ''@'localhost';
```

### Bước 4: Kiểm tra DNS và Host cache khi có dấu hiệu phân giải sai

MySQL có thể dùng DNS để chuyển địa chỉ IP của máy khách thành tên host. Nếu DNS trả về tên khác với giá trị khai báo trong tài khoản, hàng dự kiến có thể không khớp.

Người quản trị có thể kiểm tra bảng `performance_schema.host_cache` nếu có quyền:

```sql
SELECT
    IP,
    HOST,
    HOST_VALIDATED,
    SUM_CONNECT_ERRORS
FROM performance_schema.host_cache
ORDER BY IP;
```

Bảng này giúp đối chiếu IP máy khách với hostname mà Server đã phân giải. Không nên xóa host cache hoặc bật `skip_name_resolve` một cách tùy tiện khi chưa kiểm tra các tài khoản hiện có.

### Bước 5: Sửa đúng tài khoản và thử lại

Nếu tài khoản bị thiếu, tạo đúng cặp user-host. Nếu host đang quá rộng, lập kế hoạch chuyển sang IP hoặc mạng cụ thể, tạo tài khoản mới, kiểm tra kết nối và quyền, sau đó thu hồi tài khoản cũ khi đã xác nhận ứng dụng hoạt động.

Không khắc phục lỗi bằng cách cấp `ALL PRIVILEGES` hoặc mở Host thành `%` nếu ứng dụng chỉ cần truy cập từ một máy hay một mạng xác định.

## 8. Bài thực hành: quan sát MySQL chọn tài khoản

Bài thực hành sau giúp nhìn thấy khác biệt giữa tên user máy khách gửi và tài khoản Server chọn. Thực hiện trên một MySQL Server dùng cho học tập, với tài khoản quản trị có quyền tạo và xóa user.

### Chuẩn bị

Tạo hai tài khoản thử nghiệm:

```sql
CREATE USER 'lab_app'@'%'
    IDENTIFIED BY 'lab_app_password';

CREATE USER ''@'localhost'
    IDENTIFIED BY 'lab_anonymous_password';
```

Thực hiện phần này trên một Server lab riêng, có thể xóa và tạo lại. Nếu môi trường đã có các tài khoản này, kiểm tra trước bằng truy vấn vào `mysql.user`; không ghi đè hoặc xóa tài khoản đang được ứng dụng khác sử dụng. Tài khoản anonymous có tên rỗng nên không thể đổi thành một tên lab riêng.

### Thử nghiệm 1: kết nối từ localhost

Mở một kết nối cục bộ có host được Server nhận diện là `localhost` với user `lab_app`:

~~~bash
mysql --host=localhost --user=lab_app --password
~~~

Khi được hỏi mật khẩu, nhập `lab_anonymous_password`, vì hàng anonymous có Host cụ thể hơn và được chọn trước hàng `lab_app`@`%`. Nếu nhập `lab_app_password`, xác thực sẽ thất bại do mật khẩu đó thuộc hàng tài khoản khác. Nếu môi trường hoặc giao thức kết nối không làm hai hàng cùng khớp, kết quả sẽ khác; hãy kiểm tra `USER()` và `CURRENT_USER()` thay vì giả định.

Sau khi kết nối thành công, chạy:

```sql
SELECT USER(), CURRENT_USER();
```

Quan sát xem Server chọn tài khoản `lab_app` hay anonymous. Kết quả phụ thuộc vào giao thức kết nối và host mà Server dùng để đối chiếu. Nếu kết nối được xác thực bằng anonymous, quyền trong phiên là quyền của `''@'localhost'`.

### Thử nghiệm 2: tạo hàng có Host cụ thể cho user

Tạo tài khoản:

```sql
CREATE USER 'lab_app'@'localhost'
    IDENTIFIED BY 'lab_local_password';
```

Kết nối lại từ localhost bằng user `lab_app` và chạy:

~~~bash
mysql --host=localhost --user=lab_app --password
~~~

Lần này nhập `lab_local_password`, vì hàng `'lab_app'@'localhost'` cụ thể hơn tài khoản anonymous có cùng Host.

Sau khi kết nối, chạy:

```sql
SELECT USER(), CURRENT_USER();
```

So sánh với thử nghiệm trước. Khi Host ngang nhau là `localhost`, User có tên cụ thể được ưu tiên hơn User rỗng.

### Thử nghiệm 3: kiểm tra quyền

Cấp quyền khác nhau để thấy tài khoản được chọn ảnh hưởng trực tiếp đến thao tác SQL:

```sql
CREATE DATABASE IF NOT EXISTS mysql_account_lab;

CREATE TABLE IF NOT EXISTS mysql_account_lab.sample (
    id INT PRIMARY KEY,
    note VARCHAR(100)
);

GRANT SELECT
    ON mysql_account_lab.*
    TO 'lab_app'@'localhost';
```

Kết nối lại bằng `lab_app`, kiểm tra:

```sql
SHOW GRANTS FOR 'lab_app'@'localhost';

SELECT *
FROM mysql_account_lab.sample;
```

Tài khoản có quyền SELECT có thể đọc dữ liệu. Thử một thao tác ghi để xác nhận Server từ chối nếu quyền INSERT chưa được cấp. Sau đó cấp đúng quyền cần thử và quan sát kết quả.

### Dọn dẹp

Sau khi hoàn tất, thoát các phiên dùng tài khoản lab rồi xóa các đối tượng thử nghiệm:

```sql
DROP USER IF EXISTS 'lab_app'@'localhost';
DROP USER IF EXISTS 'lab_app'@'%';
DROP USER IF EXISTS ''@'localhost';

DROP DATABASE IF EXISTS mysql_account_lab;
```

Chỉ chạy lệnh xóa anonymous user nếu đây đúng là tài khoản thử nghiệm do bạn vừa tạo trong môi trường lab. Không xóa tài khoản anonymous có sẵn trên một Server dùng chung hoặc đang phục vụ ứng dụng khác.

## 9. Những nguyên tắc cần ghi nhớ

1. Một tài khoản MySQL là cặp `'user'@'host'`; hai host khác nhau tạo thành hai tài khoản khác nhau ngay cả khi cùng tên user.
2. Host biểu thị nơi máy khách kết nối từ đó, không phải host đích mà client dùng để tìm MySQL Server.
3. Khi nhiều hàng cùng khớp, MySQL chọn hàng đầu tiên sau khi sắp xếp: Host cụ thể hơn được xét trước, sau đó mới đến User cụ thể hơn.
4. Anonymous user có thể được chọn nếu Host của nó cụ thể hơn tài khoản có tên nhưng Host rộng.
5. `USER()` cho biết danh tính máy khách gửi; `CURRENT_USER()` cho biết tài khoản được Server dùng để xác thực và tính quyền.
6. `localhost`, `127.0.0.1` và kết nối TCP có thể dẫn tới kết quả khớp khác nhau tùy giao thức, DNS và cấu hình.
7. Ưu tiên host cụ thể, IP hoặc CIDR; tránh tạo tài khoản mới dùng wildcard host `%` hoặc `_` vì các ký tự này đã deprecated.
8. Tạo user bằng `CREATE USER`, cấp quyền tối thiểu bằng `GRANT`, kiểm tra bằng `SHOW GRANTS` và quản lý thay đổi bằng các câu lệnh tài khoản chuyên dụng.

## Tài liệu tham khảo chính thức

Các quy tắc trong bài được đối chiếu với MySQL 9.7 Reference Manual tại ngày **19-11-2026**:

1. [Specifying Account Names](https://dev.mysql.com/doc/refman/9.7/en/account-names.html): cú pháp `user@host`, tài khoản anonymous, hostname, IP, CIDR, subnet mask và wildcard.
2. [Access Control, Stage 1: Connection Verification](https://dev.mysql.com/doc/refman/9.7/en/connection-access.html): thứ tự sắp xếp hàng tài khoản và quy tắc chọn hàng khớp đầu tiên.
3. [Access Control, Stage 2: Request Verification](https://dev.mysql.com/doc/refman/9.7/en/request-access.html): cách MySQL kiểm tra quyền sau khi kết nối được xác thực.
4. [Adding Accounts, Assigning Privileges, and Dropping Accounts](https://dev.mysql.com/doc/refman/9.7/en/creating-accounts.html): tạo, cấp quyền và xóa tài khoản.
5. [Information Functions](https://dev.mysql.com/doc/refman/9.7/en/information-functions.html): ý nghĩa của `USER()` và `CURRENT_USER()`.
6. [Server System Variables](https://dev.mysql.com/doc/refman/9.7/en/server-system-variables.html): cấu hình `skip_name_resolve`.
7. [DNS Lookups and the Host Cache](https://dev.mysql.com/doc/refman/9.7/en/host-cache.html): phân giải tên máy, host cache và chẩn đoán kết nối.
8. [Troubleshooting Problems Connecting to MySQL](https://dev.mysql.com/doc/refman/9.7/en/problems-connecting.html): các lỗi kết nối và hướng kiểm tra.

