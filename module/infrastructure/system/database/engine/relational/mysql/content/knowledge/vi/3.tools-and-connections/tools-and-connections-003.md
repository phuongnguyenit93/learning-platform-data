# Classic Protocol, X Protocol và phạm vi sử dụng theo phiên bản

MySQL cho phép ứng dụng giao tiếp với máy chủ qua hai giao thức client/server chính: **MySQL Classic Protocol** và **MySQL X Protocol**. Cả hai đều có thể đưa yêu cầu đến cùng một MySQL Server và làm việc với cùng cơ sở dữ liệu, tài khoản, quyền truy cập và storage engine. Điểm khác biệt nằm ở cách biểu diễn thông điệp trên mạng, mô hình API mà client cung cấp, khả năng làm việc với dữ liệu quan hệ hoặc document và yêu cầu về phiên bản.

Khi phát triển hệ thống MySQL, cần hiểu giao thức đang được dùng để chọn đúng connector, cấu hình đúng cổng, chẩn đoán lỗi kết nối và triển khai bảo mật phù hợp. Việc chọn X Protocol không tự làm câu SQL chạy nhanh hơn; hiệu năng truy vấn vẫn phụ thuộc vào thiết kế bảng, index, transaction, kế hoạch thực thi, tài nguyên máy chủ và cách ứng dụng sử dụng kết nối.

Bài viết tập trung vào MySQL Server 5.7.12 trở lên, đặc biệt là các dòng 8.0 và 8.4. Các phiên bản cũ hơn hoặc bản phân phối có cấu hình riêng có thể có khác biệt.

## 1. Hai giao thức trong kiến trúc MySQL

Ứng dụng không gửi trực tiếp cấu trúc dữ liệu nội bộ của InnoDB qua mạng. Ứng dụng dùng một thư viện client (connector hoặc driver) để đóng gói yêu cầu theo giao thức mà MySQL Server hiểu. Server nhận thông điệp, xác thực phiên kết nối, kiểm tra quyền, xử lý SQL hoặc thao tác CRUD rồi trả kết quả.

Ở mức tổng quát, hai đường kết nối có thể hình dung như sau:

~~~text
Ứng dụng
   |
   +-------------------------------+
   |                               |
   v                               v
Connector dùng Classic       Connector dùng X DevAPI
   |                               |
   v                               v
MySQL Classic Protocol       MySQL X Protocol
   |                               |
   v                               v
Cổng Classic (thường 3306)   X Plugin (thường 33060)
   |                               |
   +---------------+---------------+
                   |
                   v
              MySQL Server
                   |
          Phân tích / thực thi
                   |
                   v
             Storage Engine
             (ví dụ InnoDB)
                   |
                   v
             Bảng và dữ liệu
~~~

Sơ đồ cho thấy X Plugin là thành phần phía server tiếp nhận X Protocol. Ở phía ứng dụng, X DevAPI là giao diện lập trình mà connector cung cấp để sử dụng các khả năng của X Protocol. Classic Protocol có hệ sinh thái connector lâu đời và thường được dùng trực tiếp qua các driver SQL quen thuộc.

Hai giao thức không tương ứng với hai cơ sở dữ liệu riêng. Một bảng được cập nhật qua ứng dụng dùng Classic Protocol có thể được đọc qua ứng dụng dùng X Protocol, miễn là cả hai kết nối đến cùng máy chủ, cùng schema và tài khoản có quyền phù hợp.

## 2. MySQL Classic Protocol

Classic Protocol là giao thức client/server truyền thống của MySQL. Nó được sử dụng rộng rãi bởi các ứng dụng SQL, công cụ quản trị và thư viện kết nối qua nhiều thế hệ MySQL.

### 2.1. Đặc điểm chính

- Là giao thức phổ biến cho các thao tác SQL truyền thống như SELECT, INSERT, UPDATE, DELETE, DDL và transaction.
- Hỗ trợ cơ chế gửi câu lệnh SQL và nhận result set, trạng thái thành công hoặc lỗi.
- Hỗ trợ prepared statement. Vì vậy, Classic Protocol không chỉ có một cách truyền SQL dạng văn bản; prepared statement sử dụng các thông điệp thực thi với tham số theo định dạng nhị phân.
- Được hỗ trợ bởi các client và connector lâu đời như chương trình dòng lệnh mysql và nhiều phiên bản Connector/J, Connector/C, Connector/Python, Connector/NET cùng driver của các nền tảng khác.
- Có thể kết nối qua TCP/IP; tùy hệ điều hành và cấu hình còn có các phương thức cục bộ như Unix socket hoặc named pipe.

Trong kết nối TCP/IP thông thường, cổng mặc định của Classic Protocol là **3306**. Cổng này có thể thay đổi bằng cấu hình máy chủ hoặc tham số khởi động, vì vậy ứng dụng cần dùng đúng cổng thực tế của môi trường.

### 2.2. Luồng xử lý cơ bản

Một kết nối Classic Protocol thường trải qua các bước:

1. Client mở kết nối đến địa chỉ và cổng của MySQL Server.
2. Server gửi gói bắt tay, trong đó có thông tin phiên bản giao thức và các khả năng kết nối.
3. Client gửi thông tin xác thực và các tùy chọn kết nối được thương lượng.
4. Sau khi xác thực thành công, client gửi lệnh như COM_QUERY hoặc các lệnh dành cho prepared statement.
5. Server thực thi yêu cầu và trả result set, số hàng bị ảnh hưởng, trạng thái hoặc lỗi.
6. Client tiếp tục dùng phiên kết nối cho các câu lệnh tiếp theo hoặc đóng kết nối.

Với câu SQL thông thường, client có thể gửi câu lệnh qua lệnh COM_QUERY. Với prepared statement, client chuẩn bị câu lệnh rồi gửi giá trị tham số khi thực thi. Cách làm này giúp tách dữ liệu khỏi cấu trúc SQL và giảm nguy cơ SQL injection khi ứng dụng dùng API tham số hóa đúng cách.

Ví dụ dùng chương trình dòng lệnh mysql để kết nối TCP:

~~~bash
mysql --protocol=TCP \
  --host=127.0.0.1 \
  --port=3306 \
  --user=app_user \
  --password
~~~

Tùy chọn password không kèm giá trị yêu cầu chương trình hỏi mật khẩu tương tác. Không nên ghi mật khẩu thật trực tiếp trong lịch sử shell, script hoặc dòng lệnh có thể bị tiến trình khác quan sát.

### 2.3. Text protocol và binary protocol

Hai khái niệm này thường gây nhầm lẫn:

- **Text protocol** thường chỉ cách gửi câu lệnh SQL thông thường và nhận các giá trị trong result set theo biểu diễn văn bản của giao thức.
- **Binary protocol** được dùng trong các bước thực thi prepared statement và truyền giá trị tham số hoặc kết quả theo định dạng nhị phân phù hợp.

Cả hai đều thuộc Classic Protocol. Do đó, không nên đồng nhất Classic Protocol với việc mọi dữ liệu đều được truyền dưới dạng chuỗi văn bản.

Prepared statement không chỉ là cách viết SQL có dấu hỏi. Driver cần sử dụng API prepare/bind/execute phù hợp để giá trị được truyền như tham số. Việc tự nối chuỗi đầu vào vào câu SQL vẫn có thể tạo SQL injection, dù ứng dụng đang kết nối bằng Classic Protocol.

## 3. MySQL X Protocol

X Protocol là giao thức client/server được thiết kế để hỗ trợ cả truy cập dữ liệu quan hệ và mô hình document store của MySQL. Nó được cung cấp thông qua **X Plugin** ở phía MySQL Server và thường được sử dụng từ ứng dụng qua **X DevAPI** trong connector tương ứng.

### 3.1. Đặc điểm chính

- Sử dụng Protocol Buffers để biểu diễn thông điệp trao đổi giữa client và server.
- Hỗ trợ gửi câu lệnh SQL và các thao tác CRUD theo mô hình X DevAPI.
- Hỗ trợ làm việc với bảng quan hệ và collection document.
- Cung cấp API hướng đối tượng hơn cho schema, table, collection, truy vấn và transaction.
- Có thể được sử dụng bởi các connector và công cụ có hỗ trợ X Protocol, chẳng hạn MySQL Shell và các connector cung cấp X DevAPI.

Trong kết nối TCP/IP, cổng mặc định của X Protocol là **33060**. Cổng này thuộc listener do X Plugin cung cấp. Nếu X Plugin không được cài đặt, không được bật hoặc listener không thể bind vào địa chỉ cấu hình, client X Protocol sẽ không thể kết nối dù cổng Classic vẫn hoạt động.

### 3.2. Phân biệt X Protocol, X Plugin và X DevAPI

Ba tên gọi này liên quan với nhau nhưng không có cùng ý nghĩa:

| Thành phần | Vai trò |
|---|---|
| X Protocol | Quy tắc và định dạng thông điệp client/server được truyền qua mạng |
| X Plugin | Thành phần trong MySQL Server tiếp nhận và xử lý kết nối X Protocol |
| X DevAPI | API phía client, được connector triển khai để ứng dụng thao tác với schema, table, collection, SQL và transaction |

Ví dụ, một ứng dụng Python có thể gọi phương thức của X DevAPI. Connector chuyển lời gọi đó thành thông điệp X Protocol; X Plugin nhận thông điệp và yêu cầu MySQL Server thực hiện thao tác. Ứng dụng không tự tạo gói Protocol Buffers bằng tay khi dùng connector.

### 3.3. SQL và CRUD qua X DevAPI

X Protocol không chỉ dành cho JSON hoặc document. Ứng dụng có thể dùng X DevAPI để thao tác với bảng quan hệ, chạy SQL, đồng thời dùng collection khi bài toán phù hợp với dữ liệu dạng document.

Ví dụ sau minh họa cách kết nối bằng MySQL Connector/Python có hỗ trợ X DevAPI và tìm document trong collection:

~~~python
import mysqlx

session = mysqlx.get_session({
    "host": "127.0.0.1",
    "port": 33060,
    "user": "app_user",
    "password": "your-password",
})

try:
    schema = session.get_schema("shop")
    customers = schema.get_collection("customers")

    result = customers.find("status = :status") \
        .bind("status", "ACTIVE") \
        .execute()

    for customer in result.fetch_all():
        print(customer)
finally:
    session.close()
~~~

Đây là ví dụ về API collection, không phải câu SQL trực tiếp. Collection lưu document JSON và có các thao tác tìm, thêm, sửa, xóa theo X DevAPI.

X DevAPI cũng cho phép chạy SQL trên session. Đây là ví dụ độc lập, tạo và đóng session riêng:

~~~python
sql_session = mysqlx.get_session({
    "host": "127.0.0.1",
    "port": 33060,
    "user": "app_user",
    "password": "your-password",
})

try:
    result = sql_session.sql(
        "SELECT order_id, status FROM orders WHERE customer_id = ?"
    ).bind(42).execute()

    for row in result.fetch_all():
        print(row)
finally:
    sql_session.close()
~~~

Tên phương thức cụ thể phụ thuộc phiên bản connector. Cần cài connector có hỗ trợ X DevAPI và tham khảo tài liệu đúng phiên bản đang dùng. Một driver SQL truyền thống chỉ hỗ trợ Classic Protocol không tự động trở thành client X Protocol chỉ vì đổi số cổng.

## 4. So sánh Classic Protocol và X Protocol

| Tiêu chí | Classic Protocol | X Protocol |
|---|---|---|
| Mục đích chính | SQL client/server truyền thống | SQL và CRUD qua X DevAPI, gồm cả document store |
| Biểu diễn thông điệp | Giao thức MySQL truyền thống; có text protocol và binary protocol cho prepared statement | Thông điệp dựa trên Protocol Buffers |
| Thành phần phía server | MySQL Server xử lý kết nối Classic | X Plugin trong MySQL Server tiếp nhận kết nối |
| Cổng TCP mặc định | 3306 | 33060 |
| API thường dùng | JDBC, DB-API, ADO.NET và API SQL của connector | X DevAPI thông qua connector hỗ trợ |
| Mô hình dữ liệu | Chủ yếu thao tác SQL trên bảng quan hệ | Bảng quan hệ và collection document |
| Tương thích client | Rất rộng, kể cả ứng dụng và công cụ cũ | Cần connector hoặc công cụ có hỗ trợ X Protocol |
| Trường hợp phổ biến | Ứng dụng hiện hữu, truy vấn SQL, công cụ quản trị | Ứng dụng muốn dùng X DevAPI hoặc document store |

Không thể kết luận một giao thức luôn nhanh hơn giao thức kia. Khi chạy cùng câu SQL trên cùng máy chủ, phần lớn công việc tối ưu hóa và truy cập dữ liệu vẫn diễn ra ở MySQL Server và storage engine. Khác biệt về chi phí mạng, cách đóng gói thông điệp, API và cách ứng dụng tạo truy vấn có thể ảnh hưởng đến một workload cụ thể; cần đo trên hệ thống thực tế trước khi đưa ra quyết định hiệu năng.

## 5. Phạm vi sử dụng theo phiên bản MySQL

Classic Protocol là giao thức truyền thống và có mặt trong các dòng MySQL lâu đời. X Protocol có yêu cầu phiên bản cụ thể vì cần X Plugin và connector tương thích.

| Phiên bản MySQL Server | Classic Protocol | X Protocol |
|---|---|---|
| MySQL 5.6 và cũ hơn | Có | Không có X Plugin/X Protocol tích hợp như các bản 5.7 mới |
| MySQL 5.7.12 trở lên | Có | X Plugin được cung cấp; với dòng 5.7, cần kiểm tra và cài đặt/bật plugin theo tài liệu phiên bản |
| MySQL 8.0 | Có | X Plugin được cài đặt và bật mặc định trong bản phân phối MySQL Server thông thường |
| MySQL 8.4 LTS | Có | Có X Plugin; kiểm tra trạng thái plugin và cấu hình listener của máy chủ triển khai |

X Protocol được giới thiệu trong MySQL 5.7.12. Điều này không có nghĩa mọi máy chủ 5.7 đều đã sẵn sàng nhận kết nối X: cần xác nhận bản phát hành, plugin đã được cài đặt và đang hoạt động, cổng được mở, đồng thời client phải có hỗ trợ X Protocol.

Với MySQL 8.0 và 8.4, X Plugin thường được cài đặt và bật theo cấu hình mặc định. Tuy nhiên, quản trị viên có thể thay đổi cấu hình, vô hiệu hóa plugin hoặc thay đổi cổng. Vì vậy, không nên suy ra trạng thái listener chỉ từ chuỗi phiên bản.

### 5.1. Phiên bản server và phiên bản connector phải tương thích

Việc server hỗ trợ X Protocol chưa đủ. Connector của ứng dụng cũng phải hiểu giao thức và các khả năng mà server cung cấp. Khi chọn connector, cần kiểm tra:

1. Phiên bản connector có hỗ trợ X DevAPI/X Protocol hay chỉ hỗ trợ Classic Protocol?
2. Phiên bản connector có tương thích với phiên bản runtime của ứng dụng và hệ điều hành không?
3. Connector có hỗ trợ phương thức xác thực mà server đang cấu hình không?
4. Connector có hỗ trợ TLS và các tùy chọn bảo mật cần thiết không?
5. Các API X DevAPI mà ứng dụng cần có được hỗ trợ trong phiên bản connector đó không?

Một connector có thể hỗ trợ Classic Protocol nhưng không hỗ trợ X Protocol. Ngược lại, một connector có X DevAPI có thể cung cấp cả API X DevAPI và API SQL truyền thống. Cần đọc đúng tài liệu connector, không chỉ dựa vào tên sản phẩm.

### 5.2. Công cụ client có thể hỗ trợ một hoặc cả hai giao thức

Chương trình dòng lệnh **mysql** là client truyền thống dùng Classic Protocol. **MySQL Shell** hỗ trợ cả Classic Protocol và X Protocol; người vận hành có thể chọn giao thức khi kết nối. Ví dụ:

~~~bash
# Kết nối Classic Protocol
mysqlsh --mysql \
  --host=127.0.0.1 \
  --port=3306 \
  --user=app_user

# Kết nối X Protocol
mysqlsh --mysqlx \
  --host=127.0.0.1 \
  --port=33060 \
  --user=app_user
~~~

Hai lệnh trên minh họa việc chọn giao thức rõ ràng. Khi dùng MySQL Shell, hãy kiểm tra chế độ kết nối và cổng đang thực sự sử dụng; không nên cho rằng mọi công cụ có giao diện SQL đều mặc định dùng cùng một giao thức.

## 6. Cấu hình hai listener trên máy chủ

Classic Protocol và X Protocol có listener riêng. Các tham số thường gặp gồm:

| Tham số | Ý nghĩa |
|---|---|
| port | Cổng TCP của Classic Protocol; mặc định thường là 3306 |
| bind_address | Địa chỉ mạng mà listener Classic dùng để bind |
| mysqlx_port | Cổng TCP của X Protocol; mặc định thường là 33060 |
| mysqlx_bind_address | Địa chỉ mạng mà X Plugin dùng để bind listener |

Một ví dụ cấu hình trong file tùy chọn MySQL:

~~~ini
[mysqld]
port=3306
bind_address=127.0.0.1

mysqlx_port=33060
mysqlx_bind_address=127.0.0.1
~~~

Ví dụ này giới hạn cả hai listener ở loopback, phù hợp khi client chạy trên cùng máy chủ. Nếu ứng dụng ở máy khác, quản trị viên cần chọn địa chỉ bind phù hợp với kiến trúc mạng, cấu hình firewall và giới hạn nguồn truy cập. Không nên mở cổng cơ sở dữ liệu ra Internet công cộng nếu không có thiết kế bảo vệ tương ứng.

Sau khi thay đổi tùy chọn khởi động, cần khởi động lại dịch vụ nếu tham số đó yêu cầu restart. Với môi trường container hoặc cloud, cũng cần kiểm tra port mapping, security group và network policy; cấu hình listener trong MySQL không tự động mở đường mạng ở lớp hạ tầng.

### 6.1. Kiểm tra phiên bản và trạng thái plugin

Có thể dùng các câu lệnh sau trong phiên SQL quản trị:

~~~sql
SELECT VERSION();

SHOW PLUGINS;

SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'mysqlx_port';
SHOW VARIABLES LIKE 'mysqlx_bind_address';
~~~

Trong kết quả SHOW PLUGINS, tìm plugin có tên mysqlx và kiểm tra trạng thái. Nếu biến mysqlx không tồn tại hoặc plugin không có trạng thái hoạt động, hãy kiểm tra bản phát hành, cách cài đặt và log khởi động của server. Tên biến và khả năng cấu hình có thể khác theo phiên bản hoặc cách đóng gói.

Lệnh kiểm tra kết nối ở phía hệ điều hành cần xác nhận listener thực sự đang lắng nghe đúng địa chỉ và cổng. Chỉ thấy giá trị cấu hình trong file chưa chứng minh server đã nạp cấu hình đó.

### 6.2. Khi không sử dụng X Protocol

Một hệ thống chỉ dùng Classic Protocol có thể không cần mở listener X Protocol. Quản trị viên nên kiểm tra yêu cầu ứng dụng, plugin đang hoạt động và chính sách triển khai trước khi thay đổi trạng thái X Plugin. Nếu quyết định tắt X Plugin, dùng tùy chọn cấu hình được tài liệu đúng phiên bản hỗ trợ, sau đó khởi động lại và xác minh listener đã ngừng hoạt động.

Không nên gỡ hoặc tắt plugin chỉ vì ứng dụng đang kết nối qua cổng 3306. Một số công cụ vận hành, thành phần quản trị hoặc ứng dụng khác trong cùng môi trường có thể đang sử dụng X Protocol.

## 7. Tài khoản, quyền và bảo mật kết nối

Hai giao thức đều kết nối đến MySQL Server và chịu sự kiểm soát xác thực, tài khoản, quyền SQL cùng chính sách bảo mật của máy chủ. Việc sử dụng X Protocol không bỏ qua cơ chế GRANT, và việc dùng Classic Protocol không tự động làm kết nối an toàn hơn.

Khi triển khai:

- Tạo tài khoản ứng dụng riêng theo vai trò và cấp quyền tối thiểu cần thiết trên schema hoặc đối tượng liên quan.
- Không dùng tài khoản quản trị như root cho kết nối từ ứng dụng.
- Dùng TLS khi lưu lượng đi qua mạng không tin cậy; xác minh chứng thư và cấu hình client để kiểm tra danh tính server.
- Giới hạn địa chỉ nguồn được phép truy cập ở firewall hoặc lớp mạng.
- Bảo vệ mật khẩu trong secret manager hoặc cơ chế quản lý bí mật của môi trường triển khai.
- Chọn phiên bản connector hỗ trợ phương thức xác thực đang bật trên server, đặc biệt khi hệ thống dùng cơ chế xác thực mặc định của các bản MySQL mới.

Nếu client cũ không hỗ trợ cơ chế xác thực hiện tại, ưu tiên nâng cấp connector hoặc cấu hình client phù hợp. Không nên hạ mức xác thực của máy chủ một cách tùy tiện chỉ để duy trì một driver đã lỗi thời.

## 8. Chọn giao thức cho từng tình huống

### 8.1. Nên ưu tiên Classic Protocol khi

- Ứng dụng hiện tại đang dùng JDBC, ODBC, ADO.NET hoặc driver SQL đã ổn định.
- Hệ thống cần tương thích với nhiều phiên bản MySQL hoặc công cụ cũ.
- Workload chủ yếu là SQL quan hệ và không có nhu cầu dùng X DevAPI.
- Đội vận hành đã có quy trình kết nối, giám sát, firewall và quản lý tài khoản dựa trên listener Classic.

Classic Protocol là lựa chọn hợp lý cho phần lớn ứng dụng MySQL hiện hữu. Không cần chuyển giao thức nếu driver hiện tại hoạt động tốt và đáp ứng yêu cầu bảo mật, hiệu năng, khả năng bảo trì.

### 8.2. Nên cân nhắc X Protocol khi

- Ứng dụng muốn sử dụng X DevAPI để thao tác bảng và collection.
- Bài toán có dữ liệu document và muốn dùng collection của MySQL Document Store.
- Connector trong ngôn ngữ lập trình hỗ trợ X DevAPI và đội phát triển muốn dùng API này.
- Hệ thống cần một giao diện lập trình CRUD theo mô hình X DevAPI thay vì tự xây dựng toàn bộ câu SQL cho từng thao tác.

X Protocol phù hợp khi các lợi ích của X DevAPI và document store giải quyết một nhu cầu cụ thể. Nó không bắt buộc mọi ứng dụng MySQL phải chuyển sang mô hình document hoặc thay thế SQL quan hệ.

### 8.3. Có thể vận hành cả hai giao thức

Một MySQL Server có thể đồng thời phục vụ client Classic và client X nếu hai listener được cấu hình và bật phù hợp. Ví dụ, một hệ thống có thể giữ ứng dụng Java cũ dùng JDBC qua Classic Protocol, đồng thời cho một dịch vụ mới dùng X DevAPI qua X Protocol.

Khi vận hành song song, cần quản lý rõ:

- Cổng và địa chỉ bind của từng listener.
- Quy tắc firewall, mạng riêng và port mapping.
- Tài khoản, quyền, TLS và phương thức xác thực của từng client.
- Phiên bản connector và quy trình nâng cấp.
- Log, metrics và cách xác định giao thức của từng kết nối khi điều tra sự cố.

Hai giao thức cùng truy cập một dữ liệu nên các thao tác ghi vẫn phải được thiết kế transaction và kiểm soát đồng thời đúng cách. Dùng hai giao thức không tạo ra hai bản sao dữ liệu hay hai cơ chế transaction độc lập.

## 9. Các lỗi thường gặp và cách chẩn đoán

### 9.1. Classic kết nối được nhưng X Protocol không kết nối được

Kiểm tra lần lượt:

1. MySQL Server có phiên bản hỗ trợ X Plugin hay không.
2. X Plugin có được cài đặt và đang ở trạng thái hoạt động không.
3. Cổng mysqlx_port có đúng với cổng client đang dùng không.
4. Listener có bind vào địa chỉ mà client truy cập được không.
5. Firewall, container port mapping hoặc security group có cho phép kết nối đến cổng X không.
6. Connector có thật sự hỗ trợ X Protocol/X DevAPI không.

Một kết nối thành công đến cổng 3306 chỉ xác nhận đường Classic đang hoạt động. Nó không chứng minh listener X trên cổng 33060 cũng hoạt động.

### 9.2. Kết nối được nhưng xác thực thất bại

Kiểm tra tên tài khoản, host part của tài khoản MySQL, mật khẩu, phương thức xác thực mà connector hỗ trợ và cấu hình TLS. Tài khoản có thể được phép kết nối từ một host nhưng không được phép từ host khác. Cũng cần phân biệt lỗi xác thực với lỗi quyền: xác thực thành công chưa có nghĩa tài khoản được phép đọc hoặc ghi bảng cần dùng.

### 9.3. Driver SQL không kết nối được đến cổng X

Kiểm tra tài liệu connector. Nếu connector chỉ triển khai Classic Protocol, thay đổi cổng từ 3306 sang 33060 sẽ không giúp nó hiểu X Protocol. Cần dùng connector có X DevAPI hoặc tiếp tục kết nối qua Classic Protocol.

### 9.4. Ứng dụng dùng X DevAPI nhưng không tìm thấy schema hoặc collection

Kiểm tra schema đã tồn tại, collection đã được tạo, tên đối tượng và quyền của tài khoản. Cũng cần xác định thao tác đang nhắm đến table hay collection: hai mô hình có API và quy tắc dữ liệu khác nhau dù cùng thuộc một MySQL Server.

### 9.5. Không rõ công cụ đang dùng giao thức nào

Kiểm tra tùy chọn kết nối của công cụ, địa chỉ/cổng thực tế và chế độ mà connector sử dụng. Với MySQL Shell, chỉ định rõ Classic hoặc X Protocol trong lệnh kết nối giúp tránh nhầm lẫn. Khi cần điều tra ở cấp máy chủ, đối chiếu listener và thông tin phiên kết nối với cấu hình triển khai.

## 10. Những hiểu lầm cần tránh

**“X Protocol là phiên bản mới thay thế hoàn toàn Classic Protocol.”** Không đúng. Hai giao thức cùng tồn tại; Classic Protocol vẫn là lựa chọn chính cho lượng lớn ứng dụng SQL hiện hữu.

**“X Plugin, X Protocol và X DevAPI là một.”** Không đúng. Plugin là thành phần phía server, protocol là định dạng trao đổi trên mạng, còn DevAPI là API phía client.

**“Classic Protocol chỉ truyền SQL dạng text.”** Không đúng. Classic Protocol còn hỗ trợ prepared statement với cơ chế truyền tham số và dữ liệu theo định dạng nhị phân.

**“X Protocol chỉ dùng cho JSON.”** Không đúng. X DevAPI hỗ trợ cả thao tác với bảng quan hệ, SQL và collection document.

**“Đổi sang cổng 33060 là đã dùng X Protocol.”** Không đúng. Client phải triển khai X Protocol; chỉ đổi cổng của một driver Classic sẽ dẫn đến lỗi kết nối hoặc lỗi giao thức.

**“X Protocol luôn nhanh hơn Classic Protocol.”** Không có bảo đảm như vậy. Cần benchmark với workload, connector, mạng và cấu hình thật.

**“MySQL 8.x luôn mở X Protocol trên cổng 33060.”** Đây là cổng mặc định thường gặp, không phải cam kết cho mọi máy chủ. Plugin, cổng, địa chỉ bind và firewall có thể đã được thay đổi.

## 11. Quy trình lựa chọn và triển khai

Khi bắt đầu một dự án hoặc chuẩn bị nâng cấp MySQL, hãy thực hiện theo trình tự:

1. Ghi nhận phiên bản MySQL Server thực tế bằng SELECT VERSION().
2. Liệt kê connector, phiên bản connector và API mà ứng dụng đang sử dụng.
3. Xác định workload chỉ cần SQL quan hệ hay có lợi ích rõ ràng từ X DevAPI và collection.
4. Nếu chọn Classic, xác nhận listener Classic, cổng, TLS và connector.
5. Nếu chọn X, xác nhận phiên bản hỗ trợ, trạng thái X Plugin, mysqlx_port, mysqlx_bind_address và connector X DevAPI.
6. Kiểm tra tài khoản, quyền tối thiểu, xác thực và firewall cho listener tương ứng.
7. Thử kết nối từ đúng môi trường chạy ứng dụng, sau đó kiểm tra truy vấn đọc, ghi và transaction.
8. Ghi lại cổng, giao thức, connector, phiên bản và cấu hình bảo mật trong tài liệu triển khai để đội vận hành có thể chẩn đoán sau này.

Không nên quyết định chỉ dựa vào tên giao thức hoặc cổng mặc định. Cần xác nhận phiên bản server, trạng thái plugin, khả năng connector và yêu cầu dữ liệu của ứng dụng trong cùng một lần đánh giá.

## Kết luận

Classic Protocol là giao thức MySQL truyền thống, tương thích rộng và phù hợp với hầu hết ứng dụng SQL hiện hữu. X Protocol được cung cấp qua X Plugin, dùng thông điệp Protocol Buffers và cho phép ứng dụng sử dụng X DevAPI để thao tác SQL, bảng quan hệ và collection document. Cổng TCP mặc định thường là 3306 cho Classic và 33060 cho X.

X Protocol có từ MySQL 5.7.12 trở lên; các bản 5.7 cần xác minh cài đặt plugin, còn các bản 8.0 và 8.4 thông thường đã cài đặt và bật plugin mặc định. Dù chọn giao thức nào, ứng dụng vẫn phải dùng connector tương thích, tài khoản có quyền phù hợp, kết nối được bảo vệ và transaction được thiết kế đúng. Lựa chọn tốt nhất là giao thức phù hợp với phiên bản MySQL, hệ sinh thái client và nhu cầu dữ liệu thực tế của hệ thống.
