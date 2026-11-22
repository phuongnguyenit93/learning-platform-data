# Network binding, firewall và giới hạn truy cập quản trị

MySQL có thể chỉ phục vụ ứng dụng trên cùng máy chủ, phục vụ một nhóm máy chủ trong mạng riêng hoặc nhận kết nối từ nhiều vùng mạng. Mỗi cách triển khai cần một phạm vi lắng nghe và một chính sách truy cập phù hợp. Nếu máy chủ lắng nghe trên mọi giao diện mạng và cổng cơ sở dữ liệu được mở rộng rãi, người ngoài có thể tiếp cận dịch vụ trước cả khi MySQL kiểm tra tài khoản. Nếu chỉ cấu hình firewall mà bỏ qua quyền của tài khoản, một máy đã được phép đi qua mạng vẫn có thể đăng nhập với quyền quá lớn.

Bài học này tập trung vào cách giới hạn nơi MySQL nhận kết nối, cách lọc nguồn truy cập bằng firewall và cách dành quyền quản trị cho đúng người, đúng máy và đúng mục đích. Đây là một phần trong việc làm chủ MySQL từ thiết kế dữ liệu, truy vấn và transaction đến bảo mật và vận hành.

## 1. Các lớp kiểm soát kết nối

Một kết nối từ máy khách đến MySQL thường phải đi qua nhiều lớp:

| Lớp | Câu hỏi cần trả lời | Cơ chế chính |
|---|---|---|
| Đường mạng | Máy khách có tuyến mạng đến máy chủ không? | Mạng riêng, subnet, VPN, route, bastion |
| Giao diện lắng nghe | MySQL có nhận kết nối trên địa chỉ đích không? | **bind_address**, **port**, **skip_networking** |
| Tường lửa | Nguồn nào được phép đi đến cổng MySQL? | Firewall máy chủ, security group, network ACL |
| Tài khoản MySQL | Tài khoản nào được đăng nhập từ máy nguồn nào? | Cặp **user** và **host** |
| Xác thực và mã hóa | Danh tính có hợp lệ và dữ liệu truyền có được bảo vệ không? | Mật khẩu, TLS, chứng chỉ |
| Phân quyền | Sau khi đăng nhập, tài khoản được làm gì? | Privilege, role, nguyên tắc quyền tối thiểu |

Các lớp này bổ sung cho nhau. **bind_address** quyết định MySQL lắng nghe ở đâu; firewall quyết định nguồn mạng nào được đi đến cổng; phần **user@host** quyết định tài khoản có khớp với nguồn kết nối hay không; privilege quyết định tài khoản được thao tác gì sau khi đăng nhập. Không lớp nào thay thế hoàn toàn các lớp còn lại.

Ví dụ, một máy ứng dụng có thể được firewall cho phép kết nối đến máy chủ cơ sở dữ liệu, nhưng tài khoản ứng dụng vẫn chỉ được đọc và ghi một schema cụ thể. Một máy quản trị có thể được phép truy cập qua VPN, nhưng tài khoản DBA vẫn phải dùng xác thực mạnh và chỉ có các quyền cần thiết cho công việc.

## 2. Chọn địa chỉ mạng mà MySQL lắng nghe

### 2.1. bind_address và port

MySQL dùng tùy chọn máy chủ **bind_address** để chọn địa chỉ IP mà dịch vụ nhận kết nối TCP/IP. Cổng giao thức MySQL thông thường là **3306**. Khi cấu hình địa chỉ cụ thể, máy chủ chỉ lắng nghe trên giao diện tương ứng; khi dùng địa chỉ wildcard như **0.0.0.0** hoặc **\***, dịch vụ có thể lắng nghe trên nhiều giao diện mạng.

Một số lựa chọn thường gặp:

| Giá trị | Ý nghĩa và trường hợp sử dụng |
|---|---|
| **127.0.0.1** | Chỉ nhận kết nối IPv4 từ chính máy chủ. Phù hợp khi ứng dụng và MySQL chạy cùng máy. |
| **::1** | Địa chỉ loopback IPv6. Chỉ phù hợp với máy khách cục bộ sử dụng IPv6. |
| **10.20.30.15** | Chỉ lắng nghe trên địa chỉ mạng riêng đã gán cho máy chủ. Phù hợp khi ứng dụng kết nối qua một mạng nội bộ được kiểm soát. |
| **0.0.0.0** | Lắng nghe trên mọi giao diện IPv4. Chỉ cân nhắc khi các lớp firewall và mạng đã giới hạn nguồn truy cập chặt chẽ. |
| **\*** | Giá trị wildcard của MySQL, yêu cầu lắng nghe trên các giao diện mạng khả dụng. Cần đánh giá cả IPv4 và IPv6 trong môi trường triển khai. |

Không nên chọn wildcard chỉ vì nó giúp kết nối từ xa hoạt động nhanh hơn. Nếu máy chủ có cả giao diện mạng nội bộ và giao diện công cộng, lắng nghe trên tất cả giao diện có thể khiến dịch vụ xuất hiện ở một vùng mạng không mong muốn. Hãy xác định trước địa chỉ mà ứng dụng hoặc máy quản trị thực sự sử dụng.

### 2.2. Cấu hình theo từng mô hình

Nếu MySQL chỉ phục vụ tiến trình chạy trên cùng máy, cấu hình loopback:

~~~ini
[mysqld]
bind-address = 127.0.0.1
port = 3306
~~~

Nếu ứng dụng chạy trên một máy khác trong mạng riêng, ví dụ máy chủ MySQL có địa chỉ **10.20.30.15**, có thể cấu hình:

~~~ini
[mysqld]
bind-address = 10.20.30.15
port = 3306
~~~

Địa chỉ được cấu hình phải thực sự tồn tại trên máy chủ khi MySQL khởi động. Nếu gõ nhầm địa chỉ hoặc địa chỉ chưa được gán cho giao diện mạng, dịch vụ có thể không khởi động được. Với máy chủ có nhiều giao diện, hãy chọn giao diện thuộc mạng ứng dụng hoặc mạng quản trị đã được thiết kế.

Các tệp cấu hình thường gặp gồm **/etc/mysql/mysql.conf.d/mysqld.cnf** trên một số bản phân phối Debian/Ubuntu, hoặc **/etc/my.cnf** và **/etc/mysql/my.cnf** tùy hệ điều hành và cách cài đặt. Đặt cấu hình trong nhóm **[mysqld]**, không đặt nhầm vào nhóm cấu hình của chương trình client.

Nếu không cần kết nối TCP/IP, có thể tắt mạng TCP/IP bằng:

~~~ini
[mysqld]
skip-networking = ON
~~~

Khi đó, ứng dụng cục bộ vẫn có thể kết nối qua Unix socket trên hệ điều hành hỗ trợ socket; các cơ chế cục bộ khác tùy hệ điều hành cũng có thể được sử dụng. Máy khách từ xa qua TCP/IP sẽ không kết nối được. Chỉ bật tùy chọn này khi kiến trúc thực sự không cần kết nối TCP.

Thay đổi các tùy chọn khởi động như **bind_address**, **port** hoặc **skip_networking** thường cần khởi động lại dịch vụ để có hiệu lực. Trên hệ thống dùng systemd, tên dịch vụ có thể là **mysql** hoặc **mysqld**:

~~~bash
sudo systemctl restart mysql
~~~

Hãy dùng đúng tên dịch vụ của bản cài đặt và kiểm tra trạng thái sau khi khởi động lại:

~~~bash
sudo systemctl status mysql
sudo ss -lntp | grep ':3306'
~~~

Có thể kiểm tra giá trị MySQL đang sử dụng bằng SQL:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN ('bind_address', 'port', 'skip_networking');
~~~

Kết quả từ MySQL cho biết cấu hình máy chủ; lệnh **ss** cho biết socket TCP thực tế đang lắng nghe trên địa chỉ nào. Nên kiểm tra cả hai vì một cấu hình đúng trong tệp chưa chắc đã được MySQL nạp, chẳng hạn khi chỉnh nhầm tệp hoặc nhóm cấu hình.

## 3. Giới hạn nguồn kết nối bằng firewall

Firewall lọc lưu lượng theo địa chỉ nguồn, địa chỉ đích, giao thức và cổng. Với MySQL, quy tắc thường cần cho phép TCP đến cổng **3306** từ các máy ứng dụng hoặc máy quản trị đã xác định. Firewall có thể nằm trên máy chủ, ở lớp mạng cloud hoặc ở cả hai nơi.

Ví dụ, máy chủ MySQL là **10.20.30.15** và chỉ máy ứng dụng **10.20.1.25** được phép kết nối. Với UFW trên Linux, có thể tạo quy tắc:

~~~bash
sudo ufw allow from 10.20.1.25 to any port 3306 proto tcp
sudo ufw status numbered
~~~

Quy tắc này giới hạn nguồn theo địa chỉ IP cụ thể. Nếu có nhiều máy ứng dụng, hãy tạo các quy tắc riêng hoặc dùng dải mạng nhỏ đã được phê duyệt. Trước khi thay đổi chính sách mặc định của firewall từ xa, cần bảo đảm đường quản trị như SSH vẫn được cho phép để tránh tự khóa quyền truy cập máy chủ.

Trong môi trường cloud, cấu hình security group hoặc firewall tương đương để chỉ nhận TCP **3306** từ security group của tầng ứng dụng hoặc dải IP riêng cần thiết. Ví dụ, nguồn **10.20.1.25/32** thể hiện một địa chỉ IPv4 duy nhất. Không mở cổng MySQL cho toàn Internet bằng nguồn **0.0.0.0/0**. Nếu môi trường có IPv6, hãy kiểm tra cả quy tắc IPv6; một quy tắc IPv4 chặt chẽ không tự động bảo vệ đường IPv6.

Nên áp dụng giới hạn ở nhiều lớp phù hợp:

1. Đặt MySQL trong subnet riêng, không gán địa chỉ công cộng nếu không có nhu cầu được phê duyệt.
2. Chỉ cho phép các subnet hoặc security group của ứng dụng đi đến cổng MySQL.
3. Trên máy chủ, duy trì firewall cho phép đúng nguồn và đúng cổng.
4. Dành một đường quản trị riêng qua VPN hoặc bastion; không cần mở cổng quản trị cho toàn bộ mạng người dùng.
5. Rà soát các quy tắc cũ, đặc biệt quy tắc cho phép mọi nguồn, sau khi thêm quy tắc giới hạn mới.

Firewall thường hoạt động ở cấp mạng nên không biết tài khoản MySQL nào đang đăng nhập. Ngược lại, quy tắc tài khoản MySQL không thể ngăn một máy không được phép dò cổng hoặc gửi lưu lượng đến máy chủ. Vì vậy, hãy phối hợp firewall với cấu hình MySQL và phân quyền tài khoản.

## 4. Giới hạn tài khoản và quyền quản trị

### 4.1. Tài khoản MySQL gắn với host

Trong MySQL, một tài khoản được xác định bởi cả tên người dùng và phần host, có dạng **'user'@'host'**. Phần host cho biết máy nguồn nào được phép sử dụng tài khoản đó. Ví dụ:

~~~sql
CREATE USER 'app_runtime'@'10.20.1.25'
  IDENTIFIED BY 'ThayBangBiMatTuSecretManager';
~~~

Tài khoản trên chỉ dành cho kết nối khớp với địa chỉ nguồn đã chỉ định. Có thể dùng **localhost** cho tài khoản chỉ đăng nhập cục bộ hoặc một địa chỉ IP cụ thể cho máy ứng dụng hay máy quản trị. Cần nhớ rằng tài khoản **'report'@'localhost'** và **'report'@'10.20.1.25'** là hai tài khoản khác nhau, có thể có mật khẩu và quyền khác nhau.

Ký tự wildcard trong phần host, đặc biệt **%**, có thể mở rộng phạm vi máy được phép đăng nhập. Tài khoản như **'root'@'%'** tạo phạm vi truy cập quản trị rất rộng và thường không phù hợp với hệ thống production. Hãy ưu tiên địa chỉ IP hoặc phạm vi mạng hẹp, ổn định. Nếu bật **skip_name_resolve**, MySQL không thực hiện phân giải tên máy khách; khi đó cần dùng các khai báo host bằng địa chỉ IP phù hợp thay vì dựa vào hostname.

Phần host của tài khoản là một lớp xác thực bổ sung. Nó không thay thế firewall, bởi firewall vẫn cần chặn kết nối từ các nguồn không được phép trước khi chúng chạm đến MySQL.

### 4.2. Tách tài khoản ứng dụng và tài khoản DBA

Không dùng chung tài khoản quản trị cho ứng dụng. Ứng dụng chỉ nên có các quyền cần thiết trên schema của nó. Người vận hành cơ sở dữ liệu sử dụng tài khoản riêng, được giới hạn theo máy quản trị hoặc mạng VPN và chỉ được cấp quyền phù hợp với nhiệm vụ.

Ví dụ, tạo tài khoản vận hành chỉ đọc thông tin giám sát từ một máy quản trị cụ thể:

~~~sql
CREATE ROLE 'ops_observer';
GRANT PROCESS ON *.* TO 'ops_observer';
GRANT SELECT ON performance_schema.* TO 'ops_observer';

CREATE USER 'ops_readonly'@'10.20.5.10'
  IDENTIFIED BY 'ThayBangBiMatTuSecretManager'
  REQUIRE SSL;

GRANT 'ops_observer' TO 'ops_readonly'@'10.20.5.10';
SET DEFAULT ROLE 'ops_observer'
  TO 'ops_readonly'@'10.20.5.10';
~~~

Đây là ví dụ về một vai trò quan sát; quyền thực tế cần được đối chiếu với công việc và phiên bản MySQL đang chạy. Tài khoản cần thay đổi cấu hình, quản lý người dùng, sao lưu hoặc phục hồi sẽ cần các quyền khác nhau. Hãy cấp đúng quyền cho từng nhiệm vụ và ưu tiên role để có thể quản lý quyền nhất quán. Tránh cấp **ALL PRIVILEGES** hoặc **WITH GRANT OPTION** theo thói quen, vì chúng có thể cho phép tài khoản thực hiện hoặc phân phối quyền vượt quá nhu cầu.

Tài khoản quản trị cấp cao nên đăng nhập từ máy quản trị được kiểm soát, qua VPN hoặc bastion. Không nên cho phép quản trị trực tiếp từ máy cá nhân bất kỳ hoặc từ Internet công cộng. Khi cần truy cập từ xa tạm thời, có thể dùng SSH tunnel qua bastion:

~~~bash
ssh -L 13306:10.20.30.15:3306 ops@bastion.example
~~~

Sau khi tunnel được thiết lập, máy quản trị kết nối đến cổng **13306** trên máy cục bộ; SSH chuyển tiếp kết nối đến máy MySQL qua mạng riêng. Bastion phải được bảo vệ như một thành phần hạ tầng quan trọng: giới hạn người đăng nhập, dùng khóa SSH, ghi nhận hoạt động và chỉ cho phép nó đi đến các máy đích cần thiết.

### 4.3. Mã hóa kết nối quản trị

Kết nối quản trị có thể chứa câu lệnh thay đổi dữ liệu, thông tin xác thực và kết quả truy vấn nhạy cảm. Khi kết nối đi qua mạng, hãy cấu hình TLS và yêu cầu tài khoản sử dụng kết nối mã hóa:

~~~sql
ALTER USER 'ops_readonly'@'10.20.5.10' REQUIRE SSL;
~~~

Phía client cần cấu hình CA và chế độ kiểm tra chứng chỉ phù hợp với chính sách của hệ thống. Chế độ chỉ yêu cầu TLS bảo đảm kết nối được mã hóa; chế độ xác minh danh tính máy chủ còn kiểm tra chứng chỉ và tên máy chủ. Có thể kiểm tra phiên hiện tại có dùng TLS hay không:

~~~sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
~~~

Giá trị **Ssl_cipher** không rỗng cho biết phiên đang dùng cipher TLS. Cần kiểm tra thêm cấu hình chứng chỉ và xác minh danh tính ở phía client để bảo đảm kết nối đang nói chuyện với đúng máy chủ.

## 5. Các cổng và đường truy cập cần rà soát

**3306/TCP** là cổng thường dùng cho giao thức MySQL cổ điển. Nếu triển khai bật MySQL X Protocol, cổng mặc định thường là **33060/TCP**; hãy kiểm tra cấu hình thực tế và chỉ mở cổng này cho ứng dụng thực sự sử dụng X Protocol. Không nên cho rằng chỉ cần bảo vệ 3306 là đã giới hạn mọi dịch vụ liên quan đến MySQL.

Trong môi trường container, cần kiểm tra cả địa chỉ bind bên trong container và quy tắc publish port trên host. Một dịch vụ chỉ lắng nghe trong mạng container vẫn có thể bị đưa ra mạng ngoài nếu cổng được publish rộng. Trong môi trường cloud hoặc Kubernetes, cần rà soát thêm security group, network policy, service và load balancer có liên quan.

Một số hệ thống MySQL hỗ trợ giao diện kết nối quản trị riêng qua các tùy chọn như **admin_address** và **admin_port**. Đây là cấu hình nâng cao, phụ thuộc phiên bản. Chỉ sử dụng khi đã kiểm tra tài liệu của đúng phiên bản, xác định rõ tài khoản nào có thể dùng giao diện đó và giới hạn nó trong mạng quản trị riêng. Giao diện riêng không thay thế việc giới hạn nguồn mạng và quyền của tài khoản.

## 6. Kiểm tra kết nối sau khi cấu hình

Hãy kiểm tra từ cả máy được phép và máy không được phép. Một cấu hình chỉ được xem là đúng khi máy hợp lệ kết nối thành công và nguồn ngoài phạm vi bị chặn.

**Trên máy chủ MySQL**, xác nhận địa chỉ và cổng đang lắng nghe:

~~~bash
sudo ss -lntp | grep ':3306'
~~~

Nếu kết quả hiển thị **127.0.0.1:3306**, MySQL chỉ nhận kết nối IPv4 loopback. Nếu hiển thị **10.20.30.15:3306**, dịch vụ đang lắng nghe trên địa chỉ mạng riêng đó. Nếu hiển thị **0.0.0.0:3306** hoặc địa chỉ wildcard, cần kiểm tra kỹ các giao diện mạng và firewall.

**Từ máy ứng dụng được phép**, thử kết nối TCP rõ ràng:

~~~bash
mysql --protocol=TCP --host=10.20.30.15 --port=3306 --user=app_runtime --password
~~~

Tùy chọn **--password** không kèm giá trị khiến client hỏi mật khẩu tương tác, tránh ghi mật khẩu trực tiếp vào lịch sử lệnh. Có thể kiểm tra riêng khả năng mở cổng bằng công cụ mạng như **nc**:

~~~bash
nc -vz 10.20.30.15 3306
~~~

**Từ một máy không được phép**, thực hiện kiểm tra tương tự. Kết nối phải bị chặn ở lớp mạng hoặc bị MySQL từ chối do tài khoản không khớp host. Ghi nhận rõ lớp nào đã chặn kết nối để việc kiểm tra có thể lặp lại.

Sau khi đăng nhập bằng tài khoản quản trị hoặc tài khoản kiểm tra phù hợp, xác nhận tài khoản đang dùng và quyền hiệu lực:

~~~sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS FOR CURRENT_USER();
~~~

**CURRENT_USER()** cho biết tài khoản MySQL thực tế được chọn để kiểm tra quyền; **USER()** thể hiện tên người dùng và host mà client trình bày khi kết nối. Hai giá trị có thể khác nhau do quy tắc khớp tài khoản. **SHOW GRANTS** giúp rà soát quyền được cấp cho tài khoản hiện tại.

## 7. Chẩn đoán lỗi kết nối thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Kết nối báo connection refused | Không có tiến trình lắng nghe tại địa chỉ/cổng; MySQL chỉ bind loopback; dịch vụ chưa chạy | Kiểm tra trạng thái dịch vụ, **bind_address**, **port** và kết quả **ss** |
| Kết nối bị timeout | Firewall chặn, route sai, security group hoặc network ACL chưa cho phép | Kiểm tra nguồn/đích, TCP 3306, route và quy tắc firewall ở từng lớp |
| Kết nối đến đúng máy nhưng báo Access denied | Mật khẩu sai, tài khoản không khớp host, tài khoản bị khóa hoặc yêu cầu TLS chưa được đáp ứng | Kiểm tra user-host, trạng thái tài khoản, mật khẩu, **REQUIRE SSL** và lỗi client |
| Kết nối cục bộ thành công nhưng kết nối từ xa thất bại | MySQL chỉ bind loopback, TCP bị tắt hoặc firewall chưa cho phép máy nguồn | Kiểm tra **bind_address**, **skip_networking** và firewall |
| Ứng dụng kết nối được nhưng máy quản trị không kết nối được | Firewall chỉ cho phép subnet ứng dụng hoặc tài khoản quản trị không cho phép host của máy quản trị | Kiểm tra quy tắc quản trị riêng và tài khoản **user@host** |
| Chỉ một số client IPv6 không kết nối được | Địa chỉ bind hoặc firewall IPv6 chưa được cấu hình tương ứng | Kiểm tra listener IPv6 và quy tắc IPv6 độc lập với IPv4 |

Khi điều tra, phân biệt ba nhóm lỗi. **Refused** thường cho thấy không có listener phù hợp hoặc kết nối bị từ chối ngay lập tức. **Timeout** thường liên quan đến firewall hoặc đường mạng. **Access denied** cho thấy client đã đến được MySQL và lỗi nằm ở xác thực, khớp tài khoản hoặc điều kiện đăng nhập. Phân biệt đúng nhóm lỗi giúp tránh thay đổi quyền hoặc mở firewall một cách không cần thiết.

## 8. Quy trình triển khai an toàn

Một thay đổi mạng cơ sở dữ liệu nên được thực hiện theo trình tự có thể kiểm chứng:

1. Liệt kê máy ứng dụng, máy quản trị, subnet, địa chỉ IP và cổng thực sự cần sử dụng.
2. Chọn địa chỉ bind riêng phù hợp; xác nhận địa chỉ đó đã được gán cho máy chủ.
3. Tạo quy tắc firewall cho đúng nguồn và đúng cổng; kiểm tra cả IPv4, IPv6 và lớp firewall cloud nếu có.
4. Tạo hoặc rà soát tài khoản MySQL theo cặp user-host; tách tài khoản ứng dụng khỏi tài khoản quản trị.
5. Cấp quyền theo nhiệm vụ, yêu cầu TLS cho các kết nối nhạy cảm và lưu bí mật trong hệ thống quản lý bí mật.
6. Khởi động lại MySQL nếu thay đổi yêu cầu khởi động lại; kiểm tra trạng thái dịch vụ và địa chỉ listener.
7. Thử kết nối từ nguồn được phép và nguồn không được phép; kiểm tra quyền bằng **SHOW GRANTS**.
8. Ghi lại cấu hình, người phê duyệt, thời điểm thay đổi và kết quả kiểm thử để hỗ trợ vận hành và khôi phục khi cần.

Không thay đổi bind address hoặc firewall trên máy production mà chưa xác định đường quản trị dự phòng. Nếu thay đổi khiến dịch vụ không khởi động hoặc ứng dụng mất kết nối, cần biết trước cách khôi phục tệp cấu hình và quy tắc mạng về trạng thái đã kiểm chứng.

## 9. Tình huống thực hành

Một hệ thống có ba thành phần:

- Máy MySQL: **10.20.30.15**.
- Máy ứng dụng: **10.20.1.25**.
- Máy quản trị: **10.20.5.10**, chỉ truy cập qua VPN.

Yêu cầu là ứng dụng được kết nối đến MySQL để thao tác dữ liệu của mình; máy quản trị được phép giám sát và thực hiện tác vụ vận hành; các máy khác không được mở kết nối trực tiếp đến cổng MySQL.

Hãy đề xuất cấu hình theo các bước sau:

1. Chọn **bind_address** là địa chỉ mạng riêng **10.20.30.15** nếu địa chỉ này đã được gán cho máy chủ.
2. Tạo firewall rule cho phép TCP 3306 từ **10.20.1.25** và **10.20.5.10**; không mở cổng cho toàn bộ Internet.
3. Tạo tài khoản ứng dụng với host là **10.20.1.25** và chỉ cấp quyền trên schema ứng dụng.
4. Tạo tài khoản quản trị hoặc giám sát riêng với host là **10.20.5.10**, yêu cầu TLS và cấp đúng quyền theo nhiệm vụ.
5. Kiểm thử từ hai máy được phép và một máy nằm ngoài hai địa chỉ trên. Xác nhận kết nối hợp lệ hoạt động, kết nối ngoài phạm vi bị chặn và quyền của tài khoản ứng dụng không vượt khỏi schema cần thiết.

Điểm cần đánh giá không chỉ là việc kết nối thành công. Thiết kế tốt còn phải chứng minh rằng mỗi nguồn chỉ có đường truy cập cần thiết, tài khoản có quyền tương ứng với vai trò và thay đổi có thể được kiểm tra lại.

## 10. Câu hỏi tự kiểm tra

1. **bind_address** khác firewall ở điểm nào? Vì sao cần dùng cả hai?
2. Khi đặt **bind_address = 127.0.0.1**, máy ứng dụng ở máy khác có thể kết nối qua TCP đến MySQL không? Giải thích.
3. Vì sao tài khoản **'root'@'%'** có thể tạo rủi ro lớn trong hệ thống production?
4. Một kết nối báo timeout khác gì với lỗi Access denied? Bạn sẽ kiểm tra lớp nào trước?
5. Nếu MySQL chỉ phục vụ ứng dụng trong subnet riêng, cần rà soát những lớp nào để bảo đảm cổng 3306 không bị mở ra Internet?
6. Vì sao tài khoản DBA nên tách khỏi tài khoản runtime của ứng dụng và cần yêu cầu TLS khi quản trị từ xa?

Hãy dùng các câu hỏi này để kiểm tra khả năng giải thích và vận hành cấu hình. Một thiết kế an toàn phải chỉ ra được địa chỉ nào đang lắng nghe, nguồn nào được phép đi qua firewall, tài khoản nào được phép đăng nhập và mỗi tài khoản có thể thực hiện những thao tác gì.
