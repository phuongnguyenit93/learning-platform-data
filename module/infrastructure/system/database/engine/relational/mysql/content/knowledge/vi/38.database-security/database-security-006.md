# Static privilege, dynamic privilege và hạn chế tài khoản quản trị

Trong MySQL, quyền truy cập quyết định một tài khoản được đọc dữ liệu nào, thay đổi đối tượng nào và thực hiện những thao tác vận hành nào trên máy chủ. Thiết kế quyền cần đi cùng thiết kế bảng, truy vấn và quy trình vận hành: tài khoản ứng dụng chỉ nên có quyền trên schema mà ứng dụng sử dụng, tài khoản báo cáo chỉ nên đọc dữ liệu cần thiết, còn thao tác quản trị nên được chia thành các quyền nhỏ và cấp cho đúng người hoặc dịch vụ.

Bài học này tập trung vào hai nhóm quyền của MySQL là **static privilege** và **dynamic privilege**, sau đó áp dụng chúng để xây dựng tài khoản quản trị có phạm vi rõ ràng. Các câu lệnh minh họa hướng đến MySQL 8.0 trở lên. Danh sách dynamic privilege thay đổi theo phiên bản và component/plugin đang cài đặt, vì vậy hãy kiểm tra trực tiếp trên máy chủ đích trước khi triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt static privilege với dynamic privilege và giải thích phạm vi cấp quyền của từng nhóm.
- Chọn quyền theo thao tác cần thực hiện thay vì cấp một quyền quản trị quá rộng.
- Dùng role để gom quyền, tạo tài khoản riêng cho từng nhiệm vụ và giới hạn nguồn kết nối.
- Kiểm tra quyền đã cấp, thu hồi quyền không còn cần thiết và khóa tài khoản khi cần.

## 1. Tài khoản, xác thực và phân quyền

MySQL kiểm tra danh tính tài khoản khi client kết nối, sau đó kiểm tra quyền của tài khoản đối với từng câu lệnh và đối tượng dữ liệu. Hai bước này có mục đích khác nhau:

- **Xác thực (authentication)** trả lời client có chứng minh được danh tính tài khoản hay không, thông qua mật khẩu hoặc cơ chế xác thực được cấu hình.
- **Phân quyền (authorization)** quyết định tài khoản đã xác thực được phép làm gì trên máy chủ.

Một tài khoản MySQL được định danh bằng cả tên và host, theo dạng `'user'@'host'`. Ví dụ, `'dba'@'localhost'` và `'dba'@'192.0.2.25'` là hai tài khoản khác nhau, dù cùng tên `dba`. Khi giới hạn tài khoản quản trị, cần chú ý phần host vì nó xác định nơi tài khoản được phép kết nối.

Quyền được cấp bằng `GRANT`, thu hồi bằng `REVOKE`, và có thể được gom vào role để tái sử dụng. Không nên sửa trực tiếp các bảng quyền trong schema `mysql`; hãy dùng các câu lệnh quản trị tài khoản của MySQL để máy chủ cập nhật metadata và kiểm tra quyền nhất quán.

## 2. Static privilege

**Static privilege** là quyền hệ thống được tích hợp sẵn trong MySQL. Máy chủ định nghĩa trước các quyền này; plugin hoặc component không thể đăng ký thêm một static privilege mới trong lúc chạy. Đây là nhóm quyền quen thuộc dùng để đọc, ghi, tạo và thay đổi đối tượng cơ sở dữ liệu, cũng như thực hiện một số thao tác quản trị.

Một số ví dụ:

| Static privilege | Mục đích thường gặp | Lưu ý về rủi ro |
|---|---|---|
| `SELECT` | Đọc dữ liệu | Có thể lộ dữ liệu nhạy cảm nếu cấp trên schema hoặc bảng quá rộng |
| `INSERT`, `UPDATE`, `DELETE` | Thêm, sửa, xóa bản ghi | Có thể làm thay đổi hoặc mất dữ liệu nghiệp vụ |
| `CREATE`, `ALTER`, `DROP`, `INDEX` | Tạo, sửa, xóa bảng hoặc index | Có thể ảnh hưởng cấu trúc và hiệu năng của ứng dụng |
| `CREATE USER` | Tạo và quản lý tài khoản | Có thể mở rộng quyền truy cập nếu người được cấp quyền tạo tài khoản tùy ý |
| `FILE` | Đọc/ghi một số tệp mà tiến trình MySQL có thể truy cập | Là quyền toàn cục nhạy cảm, có thể làm lộ hoặc ghi tệp trên máy chủ |
| `PROCESS` | Xem thông tin tiến trình và truy vấn đang chạy | Có thể để lộ hoạt động của các phiên khác |
| `RELOAD`, `SHUTDOWN` | Thực hiện thao tác vận hành máy chủ | Chỉ cấp cho vai trò vận hành thực sự cần chúng |
| `GRANT OPTION` | Cho phép cấp tiếp quyền mà tài khoản có thể cấp | Có thể làm quyền lan rộng ngoài dự kiến |

### 2.1. Phạm vi cấp static privilege

Static privilege có thể được cấp ở nhiều phạm vi. Phạm vi càng rộng thì càng nhiều đối tượng chịu ảnh hưởng.

| Phạm vi | Cú pháp `ON` | Ý nghĩa |
|---|---|---|
| Toàn máy chủ | `*.*` | Áp dụng cho mọi database và đối tượng phù hợp với quyền đó |
| Database | `ten_database.*` | Áp dụng cho các đối tượng trong một database |
| Bảng | `ten_database.ten_bang` | Áp dụng cho một bảng cụ thể |
| Cột | `ten_database.ten_bang (cot1, cot2)` | Giới hạn một số quyền đọc hoặc ghi ở các cột được nêu |
| Stored routine | `PROCEDURE ten_database.ten_routine` hoặc `FUNCTION ...` | Áp dụng cho routine cụ thể, ví dụ quyền `EXECUTE` |

Không phải quyền nào cũng hỗ trợ mọi phạm vi. Ví dụ, `FILE` là quyền toàn cục; quyền đọc/ghi theo cột chỉ áp dụng cho những privilege hỗ trợ cấp theo cột. Khi thiết kế, hãy chọn phạm vi nhỏ nhất mà tác vụ có thể hoạt động.

Ví dụ, tài khoản báo cáo chỉ cần đọc hai cột trong bảng đơn hàng:

```sql
CREATE USER 'report_reader'@'10.30.5.20'
  IDENTIFIED BY '<mat-khau-duoc-cap-tu-secret-manager>'
  REQUIRE SSL;

GRANT SELECT (order_id, total_amount)
  ON sales.orders
  TO 'report_reader'@'10.30.5.20';

SHOW GRANTS FOR 'report_reader'@'10.30.5.20';
```

Tài khoản này có thể đọc các cột được cấp quyền trong bảng `sales.orders`; nó không tự động có quyền đọc mọi bảng trong database `sales`, cũng không có quyền sửa dữ liệu. Trong môi trường thật, thay placeholder mật khẩu bằng bí mật được tạo và phân phối qua hệ thống quản lý secret; không ghi mật khẩu thật vào source code hoặc tài liệu.

Nếu ứng dụng cần đọc và ghi một số bảng trong schema, có thể cấp quyền ở phạm vi database:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
  ON sales.*
  TO 'sales_app'@'10.30.8.14';
```

Lệnh này cấp quyền cho các bảng trong `sales`. Chỉ thêm `CREATE`, `ALTER` hoặc `DROP` nếu ứng dụng thực sự phải thay đổi cấu trúc database trong lúc chạy. Thông thường, nên dùng một tài khoản triển khai riêng cho migration thay vì cấp quyền thay đổi schema cho tài khoản phục vụ request hằng ngày.

## 3. Dynamic privilege

**Dynamic privilege** là quyền có thể được đăng ký khi máy chủ chạy, thường bởi MySQL hoặc component/plugin. Cơ chế này giúp bổ sung quyền quản trị chuyên biệt mà không cần gom nhiều thao tác không liên quan vào một quyền lớn như `SUPER`.

Dynamic privilege được cấp ở phạm vi toàn cục bằng `ON *.*`; không thể giới hạn chúng ở `sales.*`, một bảng hoặc một cột. Vì vậy, dù tên quyền mô tả một tác vụ hẹp, người quản trị vẫn cần đánh giá tác động của nó trên toàn instance.

Một số ví dụ thường gặp trong các phiên bản MySQL 8.0:

| Dynamic privilege | Mục đích khái quát |
|---|---|
| `CONNECTION_ADMIN` | Cho phép một số thao tác kết nối quản trị, bao gồm xử lý tình huống đạt giới hạn kết nối thông thường |
| `SYSTEM_VARIABLES_ADMIN` | Quản lý các system variable ở phạm vi toàn cục theo quyền được định nghĩa |
| `SESSION_VARIABLES_ADMIN` | Quản lý một số session variable mà tài khoản thông thường không được phép thay đổi |
| `BACKUP_ADMIN` | Thực hiện các thao tác quản trị liên quan đến backup lock |
| `ROLE_ADMIN` | Quản lý việc cấp và thu hồi role |
| `BINLOG_ADMIN` | Thực hiện một số thao tác quản trị binary log |
| `SYSTEM_USER` | Phân biệt tài khoản hệ thống và kiểm soát các thao tác quản trị liên quan đến chúng |

Danh sách trên chỉ là ví dụ, không phải danh sách đầy đủ. Một số quyền chỉ xuất hiện ở phiên bản nhất định hoặc khi component/plugin tương ứng được cài đặt. Không giả định rằng mọi MySQL server đều có cùng tập dynamic privilege.

Kiểm tra các quyền mà instance hiện tại hỗ trợ:

```sql
SHOW PRIVILEGES;
```

Ví dụ, giả sử tài khoản `maintenance_operator` đã được tạo. Kỹ sư vận hành sử dụng tài khoản này để thay đổi system variable và cần khả năng kết nối quản trị khi máy chủ đã đạt giới hạn kết nối thông thường:

```sql
GRANT SYSTEM_VARIABLES_ADMIN, CONNECTION_ADMIN
  ON *.*
  TO 'maintenance_operator'@'192.0.2.26';
```

Hai quyền này được cấp toàn cục. Không cấp chúng cho tài khoản ứng dụng chỉ vì ứng dụng có lúc cần xem trạng thái máy chủ. Nếu nhiệm vụ chỉ cần backup, hãy đánh giá `BACKUP_ADMIN` và các quyền bổ sung mà công cụ backup cụ thể yêu cầu, thay vì cấp toàn bộ quyền vận hành.

Trong MySQL 8.0.31, `SUPER` đã bị đánh dấu deprecated. Với thiết kế mới, hãy xác định thao tác cần làm rồi chọn dynamic privilege tương ứng nếu có. Việc giữ một quyền tổng quát chỉ vì cấu hình cũ đang dùng nó làm tăng phạm vi tác động khi tài khoản bị lộ hoặc bị sử dụng sai.

## 4. So sánh static và dynamic privilege

| Tiêu chí | Static privilege | Dynamic privilege |
|---|---|---|
| Nguồn định nghĩa | Tích hợp sẵn trong máy chủ | Có thể được đăng ký bởi máy chủ, component hoặc plugin |
| Tập quyền | Được xác định trong bản phát hành MySQL | Có thể thay đổi theo phiên bản và component/plugin |
| Phạm vi cấp | Tùy quyền: toàn cục, database, bảng, cột hoặc routine | Toàn cục (`ON *.*`) |
| Ví dụ | `SELECT`, `INSERT`, `CREATE`, `FILE`, `PROCESS` | `BACKUP_ADMIN`, `CONNECTION_ADMIN`, `SYSTEM_VARIABLES_ADMIN` |
| Cách chọn | Theo dữ liệu hoặc đối tượng cần thao tác | Theo tác vụ quản trị chuyên biệt cần thực hiện |

Hai nhóm quyền có thể cùng được cấp cho một tài khoản hoặc role. Chúng không thay thế hoàn toàn cho nhau: `SELECT` trên một bảng là quyền dữ liệu có phạm vi cụ thể, trong khi `SYSTEM_VARIABLES_ADMIN` là quyền vận hành toàn instance.

## 5. Hạn chế tài khoản quản trị

Tài khoản quản trị thường có khả năng ảnh hưởng đến nhiều database hoặc đến chính hoạt động của máy chủ. Một tài khoản có quyền rộng bị lộ có thể gây gián đoạn dịch vụ, thay đổi cấu hình, xóa dữ liệu hoặc mở rộng quyền cho tài khoản khác. Hãy giới hạn tài khoản theo các nguyên tắc sau.

### 5.1. Tách tài khoản theo nhiệm vụ

Một người vận hành có thể có tài khoản thông thường để chạy truy vấn đọc và một tài khoản riêng để thực hiện thay đổi quản trị. Tương tự, ứng dụng, báo cáo, backup và migration nên dùng các tài khoản riêng. Nhờ đó, việc lộ thông tin đăng nhập của ứng dụng không đồng nghĩa kẻ tấn công có quyền quản trị instance.

Không dùng chung một tài khoản `root` hoặc DBA cho ứng dụng, cron job và người vận hành. Tránh nhúng thông tin đăng nhập quản trị vào file cấu hình được triển khai cùng ứng dụng.

### 5.2. Dùng role để gom quyền tối thiểu

Role giúp định nghĩa một bộ quyền theo nhiệm vụ rồi gán bộ quyền đó cho nhiều tài khoản. Ví dụ, role chỉ đọc dữ liệu bán hàng:

```sql
CREATE ROLE 'r_sales_reader'@'%';

GRANT SELECT, SHOW VIEW
  ON sales.*
  TO 'r_sales_reader'@'%';

CREATE USER 'reporter'@'10.30.5.20'
  IDENTIFIED BY '<mat-khau-duoc-cap-tu-secret-manager>'
  REQUIRE SSL
  WITH MAX_USER_CONNECTIONS 3;

GRANT 'r_sales_reader'@'%'
  TO 'reporter'@'10.30.5.20';

SET DEFAULT ROLE 'r_sales_reader'@'%'
  TO 'reporter'@'10.30.5.20';
```

Role `r_sales_reader` chỉ có quyền đọc và xem định nghĩa view trong database `sales`. `SET DEFAULT ROLE` đặt role này làm role mặc định khi tài khoản đăng nhập. Nếu role không được kích hoạt, các quyền được cấp qua role có thể không nằm trong tập quyền đang hoạt động của phiên; vì vậy hãy kiểm tra role hiện hành sau khi kết nối.

Có thể tạo các role quản trị tách biệt theo tác vụ. Ví dụ dưới đây gom hai dynamic privilege cho một nhóm vận hành:

```sql
CREATE USER 'dba_ops'@'192.0.2.25'
  IDENTIFIED BY '<mat-khau-duoc-cap-tu-secret-manager>'
  REQUIRE SSL
  WITH MAX_USER_CONNECTIONS 2;

CREATE ROLE 'r_mysql_ops'@'%';

GRANT CONNECTION_ADMIN, SYSTEM_VARIABLES_ADMIN
  ON *.*
  TO 'r_mysql_ops'@'%';

GRANT 'r_mysql_ops'@'%'
  TO 'dba_ops'@'192.0.2.25';

SET DEFAULT ROLE 'r_mysql_ops'@'%'
  TO 'dba_ops'@'192.0.2.25';
```

Đây là ví dụ cho một nhóm vận hành có đúng hai nhu cầu nêu trên, không phải bộ quyền DBA đầy đủ. Chỉ bổ sung `ROLE_ADMIN`, `BACKUP_ADMIN`, `BINLOG_ADMIN`, `SYSTEM_USER` hoặc static privilege khác khi có quy trình cụ thể yêu cầu. Đặc biệt, `SYSTEM_USER` có ảnh hưởng đến khả năng quản trị tài khoản hệ thống; không cấp nó theo thói quen cho mọi DBA.

### 5.3. Giới hạn host và mã hóa kết nối

Phần host của tài khoản phải khớp với nơi kết nối thực tế. Ưu tiên host/IP cụ thể hoặc phạm vi mạng được kiểm soát. Tránh tạo tài khoản quản trị có host `%` nếu không có lý do rõ ràng, vì cấu hình đó cho phép thử đăng nhập từ nhiều nguồn hơn dự kiến. Tài khoản `dba_ops` ở ví dụ trên được giới hạn vào host `192.0.2.25` và yêu cầu TLS ngay khi tạo.

`REQUIRE SSL` buộc kết nối sử dụng TLS. Nếu chính sách yêu cầu xác minh chứng thư client, hãy xem xét `REQUIRE X509` và cấu hình CA/chứng thư phù hợp. TLS bảo vệ đường truyền; nó không thay thế việc giới hạn host, bảo vệ thông tin xác thực hoặc cấp quyền tối thiểu.

`MAX_USER_CONNECTIONS` trong ví dụ tạo tài khoản giới hạn số kết nối đồng thời của `dba_ops`. Đây là một lớp kiểm soát tài nguyên hữu ích, nhưng không thay thế giới hạn ở tầng ứng dụng, connection pool hoặc giám sát tải.

### 5.4. Hạn chế quyền cấp tiếp và quyền quản trị tổng quát

Không thêm `WITH GRANT OPTION` nếu tài khoản không có trách nhiệm cấp quyền cho người khác. Khi một tài khoản vừa có quyền rộng vừa có `GRANT OPTION`, nó có thể truyền các quyền đó sang tài khoản khác, làm việc kiểm soát quyền khó hơn.

Chỉ cấp `CREATE USER` hoặc `ROLE_ADMIN` cho nhóm chịu trách nhiệm quản lý danh tính và role. Chỉ cấp `FILE`, `SHUTDOWN`, `RELOAD`, `PROCESS` hoặc các quyền toàn cục nhạy cảm khi nhiệm vụ yêu cầu. Đối với `SUPER` trên hệ thống cũ, hãy lập danh sách thao tác đang phụ thuộc vào nó và chuyển dần sang các quyền nhỏ hơn được phiên bản hiện tại hỗ trợ.

### 5.5. Khóa tài khoản không sử dụng và thu hồi quyền

Tài khoản dự phòng hoặc tài khoản quản trị khẩn cấp có thể được giữ ở trạng thái khóa cho đến khi cần sử dụng:

```sql
ALTER USER 'dba_breakglass'@'localhost' ACCOUNT LOCK;

-- Chỉ mở khóa theo quy trình vận hành đã được kiểm soát
ALTER USER 'dba_breakglass'@'localhost' ACCOUNT UNLOCK;
```

Khóa tài khoản ngăn đăng nhập bằng tài khoản đó; các quyền đã cấp vẫn được lưu. Khi tài khoản đổi nhiệm vụ hoặc không còn cần quyền, thu hồi quyền hoặc role tương ứng:

```sql
REVOKE SYSTEM_VARIABLES_ADMIN
  ON *.*
  FROM 'dba_ops'@'192.0.2.25';

REVOKE 'r_mysql_ops'@'%'
  FROM 'dba_ops'@'192.0.2.25';
```

Nếu tài khoản không còn được sử dụng, cân nhắc khóa rồi xóa theo chính sách lưu giữ và quy trình thay đổi của hệ thống. Không xóa tài khoản dùng chung hoặc tài khoản hệ thống khi chưa xác định đầy đủ các dịch vụ đang phụ thuộc vào nó.

## 6. Kiểm tra và rà soát quyền

Sau khi cấp quyền, hãy kiểm tra cấu hình từ góc nhìn của tài khoản được cấp. Các câu lệnh sau hỗ trợ kiểm tra:

```sql
-- Liệt kê quyền được cấp trực tiếp và role được gán
SHOW GRANTS FOR 'dba_ops'@'192.0.2.25';

-- Xem các privilege mà instance hiện tại hỗ trợ
SHOW PRIVILEGES;

-- Chạy khi đăng nhập bằng tài khoản cần kiểm tra
SELECT CURRENT_USER(), CURRENT_ROLE();
```

`SHOW GRANTS` giúp xác nhận quyền và role được gán cho tài khoản. `CURRENT_ROLE()` cho biết role đang hoạt động trong phiên hiện tại. Sau đó, hãy thử đúng thao tác nghiệp vụ bằng chính tài khoản đó: truy vấn cần đọc phải thành công, còn thao tác ghi hoặc quản trị ngoài nhiệm vụ phải bị từ chối. Chỉ nhìn vào câu lệnh `GRANT` mà không thử bằng tài khoản đích có thể bỏ sót vấn đề role chưa được kích hoạt hoặc tài khoản đang kết nối dưới host khác.

Rà soát quyền nên được thực hiện định kỳ và sau các thay đổi nhân sự, ứng dụng hoặc hạ tầng:

1. Liệt kê tài khoản và xác định chủ sở hữu, ứng dụng hoặc quy trình đang sử dụng từng tài khoản.
2. So sánh quyền hiện tại với nhiệm vụ thực tế; tìm quyền toàn cục, `GRANT OPTION` và tài khoản có host quá rộng.
3. Tách quyền dùng chung thành role theo nhiệm vụ, sau đó gán role cho đúng tài khoản.
4. Thu hồi quyền dư thừa và khóa tài khoản không còn sử dụng.
5. Kiểm tra lại bằng `SHOW GRANTS`, `CURRENT_ROLE()` và các thao tác thử có kiểm soát.

Các câu lệnh `GRANT`, `REVOKE`, `CREATE USER` và `ALTER USER` là giao diện quản trị quyền cần sử dụng. Không cần chạy `FLUSH PRIVILEGES` sau các câu lệnh này. `FLUSH PRIVILEGES` chủ yếu dùng khi cần nạp lại bảng quyền sau thao tác trực tiếp ngoài cơ chế SQL được hỗ trợ; tránh sửa trực tiếp bảng hệ thống để không tạo trạng thái quyền khó kiểm soát.

## 7. Những lỗi thiết kế thường gặp

- **Cấp `ALL PRIVILEGES` hoặc `SUPER` cho tiện:** quyền quá rộng khiến một lỗi cấu hình hoặc thông tin đăng nhập bị lộ có thể ảnh hưởng toàn instance. Hãy xác định câu lệnh thực tế cần chạy và cấp đúng privilege.
- **Cho rằng dynamic privilege có thể giới hạn theo database:** dynamic privilege được cấp toàn cục. Đánh giá tác động ở cấp instance trước khi cấp.
- **Nhầm hai tài khoản cùng tên:** `'admin'@'localhost'` và `'admin'@'%'` là các account entry khác nhau. Kiểm tra cả user lẫn host khi rà soát.
- **Tạo role nhưng quên kích hoạt:** role được gán nhưng không phải lúc nào cũng tự hoạt động trong mọi cấu hình. Dùng `SET DEFAULT ROLE` và kiểm tra `CURRENT_ROLE()`.
- **Cấp `GRANT OPTION` không cần thiết:** người dùng có thể cấp tiếp quyền, khiến phạm vi truy cập lan rộng.
- **Chỉ kiểm tra bằng tài khoản DBA:** tài khoản DBA có quyền rộng nên không phản ánh chính xác trải nghiệm của ứng dụng hoặc báo cáo. Luôn thử bằng tài khoản đích.
- **Giả định mọi phiên bản có cùng dynamic privilege:** kiểm tra `SHOW PRIVILEGES` và tài liệu đúng phiên bản, đặc biệt khi chuyển giữa MySQL 5.7, MySQL 8.0/8.4 hoặc các bản phân phối tương thích MySQL.

## 8. Bài thực hành

Một hệ thống bán hàng có database `sales`. Ứng dụng web cần đọc, thêm và cập nhật đơn hàng; dịch vụ báo cáo chỉ cần đọc dữ liệu; kỹ sư vận hành cần thay đổi system variable trong một số lần bảo trì. Hãy thiết kế ba danh tính riêng và trả lời các câu hỏi sau:

1. Tài khoản ứng dụng nên nhận những static privilege nào và ở phạm vi nào? Có cần `DROP`, `ALTER` hoặc `CREATE USER` không?
2. Tài khoản báo cáo có thể nhận role nào để chỉ đọc dữ liệu? Có thể giới hạn tiếp quyền đọc ở một số cột nhạy cảm không?
3. Tài khoản vận hành cần dynamic privilege nào cho thao tác thay đổi system variable? Vì sao không nên cấp `SUPER` hoặc `ALL PRIVILEGES`?
4. Host nào được phép kết nối, có cần `REQUIRE SSL` hay `REQUIRE X509`, và có nên giới hạn `MAX_USER_CONNECTIONS` không?
5. Bạn sẽ dùng câu lệnh nào để xác minh quyền đã cấp và chứng minh tài khoản báo cáo không thể ghi dữ liệu?

Một thiết kế tốt phải giải thích được từng quyền gắn với thao tác cụ thể nào. Nếu không thể nêu ra tác vụ cần một quyền, hãy xem đó là ứng viên cần loại khỏi role hoặc tài khoản.

## Kết luận

Static privilege kiểm soát các thao tác có sẵn của MySQL trên dữ liệu và đối tượng; dynamic privilege bổ sung các khả năng quản trị chuyên biệt, thường ở phạm vi toàn máy chủ. Khi kết hợp hai nhóm quyền với role, host giới hạn, TLS, giới hạn tài nguyên và quy trình rà soát, hệ thống có thể trao đúng khả năng cho ứng dụng và người vận hành mà vẫn giữ được ranh giới truy cập rõ ràng. Hãy kiểm tra danh sách quyền trên đúng phiên bản MySQL đang chạy và xác minh kết quả bằng chính tài khoản sẽ sử dụng quyền đó.
