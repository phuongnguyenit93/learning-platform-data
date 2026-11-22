# Sử dụng mysql client, MySQL Shell và MySQL Workbench

Khi làm việc với MySQL, bạn có thể gửi câu lệnh SQL từ terminal, chạy script quản trị bằng một shell có khả năng lập trình hoặc thao tác trực quan qua giao diện đồ họa. Ba công cụ thường gặp là **mysql client**, **MySQL Shell** và **MySQL Workbench**. Chúng cùng kết nối đến MySQL Server nhưng phục vụ những cách làm việc khác nhau.

Trong một hệ thống bán hàng, chẳng hạn, lập trình viên có thể dùng `mysql` để chạy file migration trong môi trường phát triển, dùng MySQL Workbench để xem cấu trúc bảng và kế hoạch truy vấn, rồi dùng MySQL Shell để tự động hóa việc kiểm tra hoặc dump dữ liệu. Biết cách chọn công cụ, thiết lập kết nối an toàn và xác minh đúng máy chủ giúp giảm lỗi khi phát triển cũng như vận hành cơ sở dữ liệu.

## 1. Phân biệt ba công cụ

| Công cụ | Cách làm việc | Phù hợp với | Điểm cần nhớ |
|---|---|---|---|
| `mysql` client | Giao diện dòng lệnh để gửi SQL qua giao thức MySQL cổ điển | Chạy câu SQL, file `.sql`, kiểm tra nhanh và thao tác trong terminal hoặc script | Gọn, dễ ghép với công cụ hệ điều hành; không phải môi trường lập trình quản trị chuyên dụng |
| MySQL Shell (`mysqlsh`) | Shell tương tác có chế độ SQL, JavaScript và Python; hỗ trợ AdminAPI cùng tiện ích import/export | Tự động hóa, quản trị topology, dump/load dữ liệu và thao tác SQL | Có thể kết nối bằng giao thức cổ điển hoặc X Protocol; cần chọn đúng chế độ và giao thức |
| MySQL Workbench | Ứng dụng đồ họa có SQL Editor, mô hình hóa và công cụ quản trị | Khám phá schema, viết SQL, xem kết quả, trực quan hóa kế hoạch và quản lý đối tượng | Thuận tiện cho thao tác trực quan; cần kiểm tra phiên bản tương thích với server |

Ba công cụ không thay thế MySQL Server. Chúng là các chương trình phía máy khách, cần thông tin kết nối và tài khoản có quyền phù hợp. Câu lệnh được thực thi với quyền của tài khoản đang kết nối, vì vậy mở Workbench bằng tài khoản quản trị cũng có thể gây thay đổi nguy hiểm như khi chạy cùng câu lệnh trong terminal.

## 2. Chuẩn bị thông tin kết nối

Trước khi mở một công cụ, hãy xác định rõ máy chủ và môi trường cần truy cập. Một cấu hình kết nối thường gồm:

- **Host:** địa chỉ IP hoặc tên DNS của máy chạy MySQL Server, ví dụ `127.0.0.1` hoặc `db-dev.example.net`.
- **Port:** cổng TCP. MySQL classic protocol thường dùng `3306`; MySQL X Protocol thường dùng `33060` theo cấu hình mặc định.
- **Username và password:** tài khoản MySQL được cấp cho công việc cụ thể.
- **Database/schema:** schema mặc định cần làm việc, ví dụ `shop`.
- **TLS/SSL:** chế độ mã hóa và chứng thư CA cần thiết khi kết nối qua mạng.
- **Đường mạng:** VPN, firewall, SSH tunnel hoặc mạng nội bộ có cho phép máy khách đến host và port hay không.

Không phải mọi môi trường đều dùng cổng mặc định. Quản trị viên có thể đổi port, tắt X Protocol hoặc đặt MySQL sau proxy. Hãy lấy thông số từ cấu hình môi trường hoặc người quản trị thay vì tự suy đoán.

### 2.1. Phân biệt localhost và kết nối từ xa

`localhost` có thể khiến một số client sử dụng Unix socket hoặc named pipe tùy hệ điều hành và cấu hình. `127.0.0.1` thường yêu cầu kết nối TCP loopback. Trên máy phát triển, hai cách này có thể dẫn đến phương thức xác thực hoặc cấu hình kết nối khác nhau.

Tài khoản MySQL còn gắn với phần host trong danh tính tài khoản. Ví dụ, `'app_user'@'localhost'` và `'app_user'@'10.20.%'` là hai tài khoản khác nhau. Vì vậy, đăng nhập được trên máy chủ chưa chắc đồng nghĩa ứng dụng từ một máy khác cũng đăng nhập được.

### 2.2. Bảo vệ thông tin đăng nhập

Không viết mật khẩu trực tiếp sau tùy chọn `-p`, không đưa mật khẩu vào script được commit lên Git và không chia sẻ file cấu hình có chứa secret. Với mysql client, dùng `-p` để client hỏi mật khẩu tương tác. Với MySQL Shell, có thể để shell yêu cầu mật khẩu khi mở kết nối.

Khi kết nối qua mạng, ưu tiên TLS và xác minh chứng thư máy chủ. Chế độ `VERIFY_IDENTITY` kiểm tra cả chuỗi chứng thư và danh tính máy chủ; cần cung cấp CA đáng tin cậy và dùng tên host khớp với chứng thư. `REQUIRED` yêu cầu mã hóa nhưng không xác minh danh tính máy chủ ở mức tương tự. Không nên tắt TLS chỉ để làm cho kết nối hoạt động.

Không mở cổng MySQL trực tiếp ra Internet nếu không có thiết kế bảo vệ phù hợp. Ưu tiên mạng riêng, VPN, firewall theo nguồn truy cập hoặc SSH tunnel; chỉ cấp quyền từ host cần thiết và dùng tài khoản có quyền tối thiểu.

## 3. Sử dụng mysql client

`mysql` là client dòng lệnh truyền thống để kết nối đến MySQL Server bằng classic protocol. Nó phù hợp khi cần chạy SQL nhanh, thực thi file script, kiểm tra trạng thái hoặc tích hợp thao tác cơ sở dữ liệu vào quy trình terminal.

### 3.1. Kết nối đến MySQL Server

Ví dụ kết nối đến server phát triển qua TCP, chọn schema `shop` và bật xác minh TLS:

```bash
mysql \
  --host=db-dev.example.net \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/mysql/certs/ca.pem \
  --database=shop
```

Client sẽ yêu cầu nhập mật khẩu. Trên Windows, có thể viết lệnh trên một dòng hoặc dùng ký tự nối dòng phù hợp với shell đang dùng; dấu `\` ở ví dụ dành cho shell kiểu Unix. Đường dẫn CA cũng phải tồn tại trên máy chạy client.

Để kết nối local qua TCP:

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p
```

Chỉ dùng tài khoản `root` trong môi trường và thao tác cần quyền quản trị. Khi làm việc với ứng dụng, nên dùng tài khoản riêng như `app_user` với quyền trên đúng schema.

### 3.2. Các lệnh thường dùng trong phiên tương tác

Sau khi kết nối, bạn có thể chạy SQL trực tiếp:

```sql
SELECT VERSION();
SELECT CURRENT_USER(), USER();
SHOW DATABASES;
USE shop;
SHOW TABLES;
SHOW CREATE TABLE orders;
```

Một số lệnh điều khiển của mysql client thường dùng:

| Lệnh | Tác dụng |
|---|---|
| `status` hoặc `\s` | Xem trạng thái kết nối, server, schema mặc định và một số thông tin phiên |
| `\c` | Hủy câu lệnh đang nhập dở |
| `\q` hoặc `exit` | Thoát client |
| `source path/to/file.sql` hoặc `\. path/to/file.sql` | Đọc và thực thi file SQL trong phiên hiện tại |
| `help` hoặc `\h` | Xem trợ giúp của client |

Lưu ý rằng `SHOW DATABASES`, `SHOW TABLES` và các truy vấn metadata chỉ hiển thị đối tượng mà tài khoản có quyền nhìn thấy. Nếu không thấy schema hoặc bảng, hãy kiểm tra quyền trước khi kết luận đối tượng không tồn tại.

### 3.3. Chạy file SQL

Có thể thực thi một file migration trong phiên tương tác:

```sql
USE shop;
source ./migrations/2026_11_add_order_index.sql;
```

Hoặc khởi chạy client và chuyển nội dung file qua standard input:

```bash
mysql -h 127.0.0.1 -P 3306 -u deploy_user -p shop < schema.sql
```

Cách thứ hai phù hợp với script tự động và pipeline triển khai. Hãy kiểm tra mã thoát của tiến trình, log lỗi và trạng thái schema sau khi chạy. Không giả định toàn bộ file luôn được rollback nếu một câu lệnh lỗi; hành vi transaction phụ thuộc vào loại câu lệnh, engine và cách script được viết.

Đối với file lớn, nên chạy trong môi trường có kết nối ổn định, theo dõi thời gian và dung lượng log, đồng thời chuẩn bị cách phục hồi. Trước khi chạy migration trên production, cần biết file có thể chạy lại an toàn hay không và có khóa bảng hoặc thay đổi cấu trúc ảnh hưởng ứng dụng không.

### 3.4. Chạy truy vấn một lần và lưu kết quả

Tùy chọn `--execute` cho phép gửi một câu SQL rồi thoát:

```bash
mysql -h 127.0.0.1 -u report_user -p \
  --database=shop \
  --execute="SELECT status, COUNT(*) FROM orders GROUP BY status;"
```

Để lấy kết quả dạng batch thuận tiện cho script, có thể dùng `--batch` và `--raw`:

```bash
mysql -h 127.0.0.1 -u report_user -p \
  --database=shop --batch --raw \
  --execute="SELECT id, status FROM orders LIMIT 10;" > orders.tsv
```

File đầu ra cần được xử lý như dữ liệu có thể chứa thông tin nhạy cảm. Không ghi kết quả khách hàng hoặc dữ liệu production vào thư mục công khai, log CI hoặc kho mã nguồn.

## 4. Sử dụng MySQL Shell

MySQL Shell (`mysqlsh`) là môi trường tương tác và tự động hóa hiện đại hơn. Ngoài việc gửi SQL, shell còn có thể chạy JavaScript hoặc Python, cung cấp AdminAPI để quản trị một số topology MySQL và các tiện ích dump/load dữ liệu.

### 4.1. Kết nối bằng classic protocol hoặc X Protocol

Để kết nối qua classic protocol trên cổng `3306`, có thể chỉ rõ `--mysql` và chuyển vào SQL mode:

```bash
mysqlsh --mysql \
  --uri app_admin@db-dev.example.net:3306/shop \
  --sql
```

Để dùng X Protocol, server phải bật X Plugin và mở cổng tương ứng, thường là `33060`:

```bash
mysqlsh --mysqlx \
  --uri app_admin@db-dev.example.net:33060/shop \
  --sql
```

Shell có thể yêu cầu nhập mật khẩu khi cần. Chọn giao thức khớp với port và cấu hình của server; không thể đổi sang X Protocol chỉ bằng cách thay client nếu server chưa bật X Plugin. Workbench và mysql client truyền thống thường dùng classic protocol.

### 4.2. Chuyển chế độ SQL, JavaScript và Python

MySQL Shell có ba chế độ chính:

- **SQL mode:** gửi câu lệnh SQL đến server.
- **JavaScript mode:** viết script JavaScript, truy cập session và các API quản trị.
- **Python mode:** viết script Python để tự động hóa tác vụ.

Trong phiên shell, dùng các lệnh sau để chuyển chế độ:

```text
\sql
\js
\py
\status
```

Ví dụ trong SQL mode:

```sql
SELECT VERSION();
SHOW DATABASES;
```

Ví dụ trong JavaScript mode, sử dụng session hiện tại để chạy truy vấn:

```javascript
var result = session.runSql("SELECT COUNT(*) AS total FROM shop.orders");
result.fetchAll();
```

Trong Python mode, API tương ứng dùng cách đặt tên theo Python:

```python
result = session.run_sql("SELECT COUNT(*) AS total FROM shop.orders")
result.fetch_all()
```

Không trộn cú pháp SQL thuần với cú pháp JavaScript hoặc Python khi shell đang ở chế độ khác. Nếu lệnh có vẻ không được nhận diện, hãy kiểm tra chế độ hiện tại bằng `\status`.

### 4.3. AdminAPI cho quản trị topology

MySQL Shell cung cấp AdminAPI để kiểm tra và quản trị các cấu hình như InnoDB Cluster và ReplicaSet. Trong JavaScript mode, một phiên đã kết nối có thể lấy trạng thái cluster hiện có:

```javascript
var cluster = dba.getCluster();
cluster.status();
```

AdminAPI còn có các thao tác kiểm tra cấu hình instance, tạo cluster, thêm instance và thay đổi topology. Đây là các thao tác quản trị có thể thay đổi trạng thái máy chủ. Trước khi thực hiện, cần xác minh phiên bản MySQL Shell/server, điều kiện cấu hình, quyền tài khoản, backup, trạng thái replication và kế hoạch chuyển đổi. Không chạy lệnh tạo hoặc thay đổi cluster trên production chỉ để thử nghiệm.

### 4.4. Dump và load dữ liệu

MySQL Shell có các tiện ích dump/load, hỗ trợ chia dữ liệu thành nhiều phần và chạy song song. Ví dụ trong JavaScript mode:

```javascript
util.dumpSchemas(["shop"], "/backup/shop-dump", {threads: 4});
```

Nạp bộ dump vào server đích:

```javascript
util.loadDump("/backup/shop-dump", {threads: 4});
```

Đường dẫn ở ví dụ là thư mục trên máy chạy MySQL Shell. Cần bảo đảm thư mục đích có quyền ghi/đọc, đủ dung lượng và không ghi đè dữ liệu ngoài dự kiến. Dump/load có thể cần các quyền MySQL cụ thể và tùy chọn phù hợp với phiên bản server. Hãy đọc kết quả lệnh, kiểm tra cảnh báo và xác minh dữ liệu sau khi nạp.

MySQL Shell dump là một hình thức sao lưu logic. Nó không tự thay thế mọi yêu cầu backup vật lý, lưu binary log để point-in-time recovery, mã hóa bản sao lưu, lưu bản sao ở nơi độc lập và diễn tập khôi phục. Một bản backup chỉ đáng tin khi quy trình restore đã được thử nghiệm.

## 5. Sử dụng MySQL Workbench

MySQL Workbench là ứng dụng đồ họa tích hợp công cụ truy vấn, thiết kế schema và quản trị server. Nó hữu ích khi cần quan sát cấu trúc dữ liệu hoặc làm việc với nhiều bảng mà việc nhớ tên và quan hệ qua terminal trở nên bất tiện.

### 5.1. Tạo kết nối

Quy trình cơ bản:

1. Mở MySQL Workbench và chọn tạo kết nối mới tại khu vực MySQL Connections.
2. Đặt tên dễ nhận biết, ví dụ `Local Dev` hoặc `Staging Read Only`.
3. Chọn phương thức kết nối: TCP/IP, TCP/IP over SSH hoặc phương thức được môi trường hỗ trợ.
4. Nhập hostname, port, username và cấu hình TLS nếu được yêu cầu.
5. Chọn **Test Connection** để kiểm tra, sau đó lưu và mở kết nối.

Không đặt tên kết nối chỉ là `MySQL` nếu bạn thường xuyên làm việc với nhiều môi trường. Tên như `DEV`, `STAGING` và `PRODUCTION READ ONLY` giúp giảm nguy cơ chạy nhầm câu lệnh, nhưng vẫn phải kiểm tra hostname và schema trong mỗi phiên.

Workbench có thể lưu mật khẩu qua cơ chế lưu trữ thông tin xác thực của hệ điều hành. Chỉ lưu trên thiết bị cá nhân được bảo vệ; không chia sẻ profile kết nối chứa thông tin nhạy cảm cho người khác.

### 5.2. SQL Editor và quản lý schema

Sau khi mở kết nối, SQL Editor cho phép:

- Viết và chạy câu lệnh SQL, chọn một phần câu lệnh để thực thi hoặc chạy toàn bộ script.
- Xem kết quả trong lưới, sắp xếp và lọc dữ liệu trả về.
- Mở schema, bảng, view, stored procedure và trigger trong Navigator.
- Xem định nghĩa bảng, khóa chính, khóa ngoại, chỉ mục và kiểu dữ liệu.
- Tạo hoặc chỉnh sửa đối tượng qua trình biên tập trực quan.

Khi chỉnh sửa cấu trúc bằng giao diện, hãy xem lại SQL mà Workbench dự định chạy trước khi áp dụng. Một thay đổi kiểu dữ liệu hoặc khóa có thể phải rebuild bảng, giữ metadata lock hoặc ảnh hưởng ứng dụng đang hoạt động.

### 5.3. Xem kế hoạch thực thi

Trong SQL Editor, Workbench có thể hiển thị kế hoạch thực thi trực quan cho truy vấn. Bạn có thể bắt đầu bằng:

```sql
EXPLAIN
SELECT id, status, total_amount
FROM shop.orders
WHERE customer_id = 120
ORDER BY created_at DESC
LIMIT 20;
```

Kế hoạch giúp xem MySQL dự định truy cập bảng bằng cách nào, chỉ mục nào có thể được chọn, thứ tự nối và số hàng ước lượng. Với phiên bản MySQL hỗ trợ `EXPLAIN ANALYZE` (MySQL 8.0.18 trở lên), câu lệnh này thực thi truy vấn và cung cấp số hàng/thời gian thực tế theo iterator:

```sql
EXPLAIN ANALYZE
SELECT id, status, total_amount
FROM shop.orders
WHERE customer_id = 120
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` thực sự chạy câu truy vấn. Hãy giới hạn phạm vi và đánh giá tác động trước khi dùng với truy vấn nặng trên production. Giao diện trực quan không thay thế việc đọc các ước lượng, số hàng thực tế, thời gian và điều kiện lọc trong kế hoạch.

### 5.4. Công cụ quản trị và import/export

Workbench có các khu vực quản trị để xem trạng thái server, tài khoản và quyền, biến cấu hình, phiên đang hoạt động và một số chỉ số hiệu năng. Tên và khả năng của từng màn hình phụ thuộc phiên bản Workbench và MySQL Server.

Các chức năng Data Export và Data Import/Restore hỗ trợ xuất schema/dữ liệu thành file SQL và nạp lại từ file dump. Trước khi import, hãy xác nhận đúng connection, schema đích, dung lượng đĩa và khả năng tương thích. Import vào schema đang được ứng dụng sử dụng có thể ghi đè hoặc làm thay đổi dữ liệu hiện có.

Workbench cũng có công cụ mô hình hóa EER để vẽ bảng, quan hệ và sinh SQL. Mô hình trực quan hữu ích khi thiết kế, nhưng schema thực tế vẫn cần được kiểm tra bằng `SHOW CREATE TABLE` và migration được quản lý trong quy trình phát triển.

## 6. Chọn công cụ theo công việc

| Công việc | Công cụ nên bắt đầu | Lý do |
|---|---|---|
| Chạy một câu `SELECT` hoặc `SHOW` nhanh | `mysql` client hoặc SQL Editor | Khởi động nhanh, kết quả trực tiếp |
| Chạy file migration trong CI/CD | `mysql` client | Dễ truyền file qua standard input và kiểm tra mã thoát |
| Viết script kiểm tra nhiều server | MySQL Shell | Có JavaScript/Python và session API |
| Kiểm tra InnoDB Cluster hoặc ReplicaSet | MySQL Shell | Có AdminAPI chuyên dụng |
| Dump/load schema lớn với xử lý song song | MySQL Shell | Có tiện ích dump/load tích hợp |
| Khám phá quan hệ giữa các bảng | MySQL Workbench | Navigator và EER Diagram giúp quan sát trực quan |
| Xem kết quả truy vấn và kế hoạch dạng đồ họa | MySQL Workbench | SQL Editor tích hợp kết quả và EXPLAIN |
| Chạy lệnh từ máy chủ không có giao diện đồ họa | `mysql` client hoặc MySQL Shell | Làm việc qua terminal và có thể tự động hóa |

Không có công cụ tốt nhất cho mọi tác vụ. Một quy trình phát triển có thể dùng Workbench để khám phá schema, lưu migration dưới dạng file SQL trong Git, chạy migration bằng mysql client ở CI/CD và dùng MySQL Shell cho kiểm tra hoặc backup theo lịch.

## 7. Một quy trình làm việc mẫu

Giả sử cần kiểm tra bảng đơn hàng, xác định một truy vấn chậm và triển khai chỉ mục ở môi trường phát triển.

### Bước 1: Xác nhận đúng server

Kết nối bằng công cụ bạn quen dùng rồi kiểm tra danh tính server:

```sql
SELECT
    @@hostname AS server_host,
    @@port AS server_port,
    DATABASE() AS current_schema,
    CURRENT_USER() AS authenticated_account,
    VERSION() AS mysql_version;
```

Nếu kết quả không đúng môi trường dự kiến, dừng lại và kết nối lại. Không dựa vào màu tab hoặc tên profile duy nhất để nhận diện production.

### Bước 2: Khám phá cấu trúc bảng

```sql
SHOW CREATE TABLE shop.orders;
SHOW INDEX FROM shop.orders;
```

Đọc kiểu dữ liệu, khóa, ràng buộc và chỉ mục hiện có trước khi đề xuất thay đổi. Không tạo chỉ mục trùng hoặc gần trùng mà chưa hiểu mục đích của các chỉ mục hiện tại.

### Bước 3: Đo và xem kế hoạch truy vấn

Chạy truy vấn với điều kiện thực tế, xem slow query log hoặc thống kê Performance Schema nếu có quyền, sau đó dùng `EXPLAIN`. Chỉ dùng `EXPLAIN ANALYZE` khi phiên bản hỗ trợ và có thể chấp nhận việc truy vấn được thực thi.

### Bước 4: Thử thay đổi trong môi trường phát triển

Viết migration thành file SQL, xem lại câu lệnh, ước lượng ảnh hưởng lên dữ liệu và kiểm tra bằng một tập dữ liệu đại diện. Nếu cần chạy qua terminal:

```bash
mysql -h 127.0.0.1 -u deploy_user -p shop < migrations/add_orders_customer_created_index.sql
```

### Bước 5: Xác minh sau thay đổi

Kiểm tra `SHOW INDEX`, chạy lại truy vấn và so sánh kế hoạch, thời gian phản hồi cùng tải ghi. Chỉ mục có thể cải thiện truy vấn đọc nhưng tăng chi phí `INSERT`, `UPDATE` và dung lượng lưu trữ. Cần đánh giá cả hai phía trước khi triển khai.

## 8. Xử lý lỗi kết nối thường gặp

| Thông báo hoặc triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `ERROR 2002` hoặc không kết nối được socket | Server chưa chạy, socket sai hoặc client đang dùng phương thức kết nối khác dự kiến | Kiểm tra dịch vụ MySQL, socket path và thử TCP loopback nếu phù hợp |
| `ERROR 2003` / connection refused hoặc timeout | Sai host/port, firewall chặn, server không lắng nghe TCP hoặc đường mạng không thông | Kiểm tra hostname, port, trạng thái server, firewall, VPN và bind address |
| `ERROR 1045: Access denied` | Sai mật khẩu, sai phần host của tài khoản hoặc thiếu phương thức xác thực tương thích | Xác minh username, host nguồn, thông tin xác thực và quyền tài khoản với quản trị viên |
| `ERROR 1049: Unknown database` | Schema không tồn tại hoặc gõ sai tên | Kiểm tra tên schema và quyền nhìn thấy schema |
| Lỗi chứng thư TLS | CA không đáng tin, hostname không khớp chứng thư hoặc chứng thư hết hạn | Kiểm tra CA, SAN/hostname, thời hạn chứng thư và cấu hình TLS của server |
| Kết nối bị ngắt giữa chừng | Mạng không ổn định, timeout, server restart hoặc truy vấn kéo dài | Kiểm tra log server, mạng, timeout và trạng thái truy vấn |
| MySQL Shell báo không kết nối được X Protocol | X Plugin chưa bật hoặc đang dùng sai port | Dùng classic protocol nếu phù hợp hoặc nhờ quản trị viên xác minh X Plugin và port |

Khi gặp lỗi, tách vấn đề thành từng lớp: client có chạy được không, tên host có phân giải được không, TCP có đến được port không, server có chấp nhận kết nối không, TLS có xác thực được không và tài khoản có quyền không. Cách kiểm tra tuần tự này giúp tránh thay đổi quyền hoặc cấu hình server khi lỗi thực ra nằm ở mạng.

## 9. Thói quen an toàn khi dùng công cụ MySQL

- **Kiểm tra môi trường trước khi ghi:** xác nhận host, port, schema và tài khoản trước `UPDATE`, `DELETE`, `ALTER` hoặc migration.
- **Dùng tài khoản đúng vai trò:** tài khoản báo cáo chỉ cần quyền đọc; tài khoản ứng dụng chỉ cần quyền trên schema nghiệp vụ; tài khoản quản trị chỉ dùng khi thật sự cần.
- **Không để lộ secret:** tránh mật khẩu trong command history, script, ảnh chụp màn hình, log và file cấu hình được chia sẻ.
- **Dùng TLS khi đi qua mạng:** xác minh danh tính server bằng CA và hostname hợp lệ.
- **Đọc lại SQL trước khi áp dụng:** đặc biệt với thay đổi cấu trúc, xóa dữ liệu, import/export và AdminAPI.
- **Giữ migration trong kiểm soát phiên bản:** ghi rõ mục đích, thứ tự chạy, điều kiện chạy lại và cách phục hồi.
- **Backup và kiểm tra restore:** export thành công không chứng minh có thể phục hồi hệ thống đúng thời điểm và đúng yêu cầu.
- **Không chạy thử thao tác phá hủy trên production:** dùng môi trường phát triển hoặc bản sao dữ liệu phù hợp.

## 10. Checklist trước khi thao tác

- Tôi đang kết nối đúng host, port và schema chưa?
- Tôi đang dùng classic protocol hay X Protocol, và server có hỗ trợ giao thức đó không?
- Phiên bản client, MySQL Shell, Workbench và server có tương thích không?
- TLS có được bật và chứng thư có được xác minh không?
- Tài khoản có đúng quyền tối thiểu cho công việc không?
- Lệnh sắp chạy chỉ đọc hay có thể thay đổi dữ liệu/cấu trúc?
- Nếu chạy migration, import hoặc dump, tôi đã xác nhận file, thư mục, dung lượng và phương án phục hồi chưa?
- Tôi đã xác minh kết quả sau khi chạy và lưu log cần thiết chưa?

## Kết luận

`mysql` client phù hợp cho SQL và script dòng lệnh; MySQL Shell bổ sung khả năng lập trình, AdminAPI và tiện ích dump/load; MySQL Workbench hỗ trợ khám phá schema, viết truy vấn và quản trị qua giao diện đồ họa. Dù dùng công cụ nào, hãy xác nhận đúng server, chọn giao thức phù hợp, bảo vệ thông tin đăng nhập, cấp quyền tối thiểu và kiểm tra tác động trước khi thay đổi dữ liệu. Những thói quen đó giúp công việc thiết kế, truy vấn, tối ưu và vận hành MySQL an toàn, có thể lặp lại và dễ kiểm tra.
