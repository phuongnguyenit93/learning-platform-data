# maxLifetime, keepalive, wait_timeout và vòng đời kết nối

Trong ứng dụng Spring Boot dùng JPA với MySQL, một request thường không mở kết nối TCP mới cho mỗi câu SQL. Thay vào đó, ứng dụng mượn một kết nối từ connection pool, thực hiện transaction hoặc truy vấn, rồi trả kết nối về pool để request khác sử dụng. Cách làm này giảm chi phí thiết lập kết nối, nhưng cũng tạo ra một vòng đời kết nối được điều khiển đồng thời bởi HikariCP, MySQL Server, JDBC driver và các thành phần mạng trung gian.

Ba cấu hình thường bị nhầm lẫn là **HikariCP maxLifetime**, **HikariCP keepaliveTime** và **MySQL wait_timeout**. Chúng đo những khoảng thời gian khác nhau và tác động đến những trạng thái kết nối khác nhau. Cấu hình sai có thể khiến ứng dụng gặp lỗi "Communications link failure", "MySQL server has gone away", lỗi khi mượn connection hoặc transaction bị rollback ngoài dự kiến.

Bài học này giải thích vòng đời kết nối trong Spring Boot/JPA, cách các bộ định thời phối hợp, cách chọn giá trị an toàn và cách điều tra khi kết nối bị MySQL hoặc hạ tầng mạng đóng.

Trong phạm vi **DATABASE_MYSQL**, kết nối ứng dụng là cầu nối đến toàn bộ kiến thức MySQL: thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời. Việc vận hành pool cũng cần đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố cơ sở dữ liệu quan hệ. Chương **Spring Boot và JPA** đặt các nguyên tắc đó vào vòng đời kết nối của ứng dụng Java.

## 1. Mô hình vòng đời kết nối

### 1.1. Các thành phần tham gia

Một kết nối JDBC đến MySQL thường đi qua các lớp:

~~~mermaid
flowchart LR
    REQ[HTTP request / Job] --> TX[Spring Transaction / JPA]
    TX --> POOL[HikariCP connection pool]
    POOL --> JDBC[MySQL Connector/J]
    JDBC --> NET[TCP / Proxy / Firewall]
    NET --> DB[MySQL session]
~~~

- **Spring Transaction / JPA:** xác định phạm vi transaction và thời điểm cần dùng kết nối.
- **HikariCP:** tạo, quản lý, kiểm tra, cho mượn và thu hồi kết nối vật lý.
- **MySQL Connector/J:** triển khai JDBC, gửi câu lệnh và nhận kết quả từ server.
- **TCP, proxy, firewall hoặc load balancer:** có thể đóng kết nối vì idle timeout hoặc giới hạn tuổi kết nối riêng.
- **MySQL Server:** duy trì session và áp dụng các giới hạn như **wait_timeout**.

Kết nối mà code nhận từ **DataSource.getConnection()** thường là một wrapper do HikariCP quản lý. Khi gọi **close()** trên wrapper, ứng dụng thường trả connection về pool; nó không nhất thiết đóng TCP connection vật lý ngay lập tức.

### 1.2. Các trạng thái chính

Một physical connection thường trải qua các trạng thái:

1. **Tạo mới:** HikariCP mở kết nối qua Connector/J và MySQL tạo session.
2. **Đang được mượn (active/borrowed):** một request hoặc transaction đang sử dụng connection.
3. **Được trả về pool:** ứng dụng gọi **close()** sau khi hoàn tất công việc.
4. **Idle trong pool:** connection chưa được request khác mượn.
5. **Được kiểm tra keepalive:** HikariCP tạm lấy connection idle ra khỏi pool, kiểm tra nó còn sống rồi trả lại.
6. **Được retire:** HikariCP loại connection đã đến tuổi tối đa hoặc không còn cần thiết.
7. **Bị server/hạ tầng đóng:** MySQL hoặc thành phần mạng đóng socket; pool phải phát hiện và loại bỏ connection hỏng.

Sơ đồ rút gọn:

~~~mermaid
stateDiagram-v2
    [*] --> Creating
    Creating --> Borrowed: Kết nối thành công
    Borrowed --> Idle: close() trả về pool
    Idle --> Borrowed: Request mượn
    Idle --> Keepalive: Đến lịch kiểm tra
    Keepalive --> Idle: Ping thành công
    Keepalive --> Retired: Ping thất bại
    Idle --> Retired: maxLifetime / idleTimeout
    Borrowed --> Retired: Trả về sau khi hết maxLifetime
    Retired --> [*]
~~~

Điểm quan trọng: connection đang được mượn không phải connection idle trong pool. **keepaliveTime** chủ yếu kiểm tra connection idle; **maxLifetime** không cưỡng bức cắt một connection đang được ứng dụng sử dụng.

## 2. Ba bộ định thời cần phân biệt

| Cấu hình | Thuộc thành phần | Đơn vị | Đo điều gì? | Tác động chính |
|---|---|---:|---|---|
| **maxLifetime** | HikariCP | Millisecond | Tuổi tối đa của physical connection tính từ lúc tạo | Đánh dấu connection để loại khỏi pool khi hết tuổi |
| **keepaliveTime** | HikariCP | Millisecond | Khoảng cách giữa các lần kiểm tra connection idle | Ping connection idle để phát hiện hoặc ngăn bị đóng do idle timeout |
| **wait_timeout** | MySQL Server | Second | Thời gian server chờ hoạt động trên session không tương tác trước khi đóng | Đóng session đã idle quá lâu |
| **idleTimeout** | HikariCP | Millisecond | Thời gian connection dư thừa nằm idle trong pool | Loại bớt connection idle khi pool có thể co lại |
| **connectionTimeout** | HikariCP | Millisecond | Thời gian request chờ lấy được connection từ pool | Ném lỗi nếu không mượn được connection đúng hạn |

Không so sánh trực tiếp các con số nếu chưa đổi đơn vị. Ví dụ **wait_timeout=1800** là 1.800 giây, tức 30 phút; **maxLifetime=1500000** là 1.500.000 millisecond, tức 25 phút.

## 3. MySQL wait_timeout

### 3.1. Ý nghĩa của wait_timeout

**wait_timeout** là số giây MySQL chờ một kết nối không tương tác không có hoạt động trước khi đóng session. JDBC connection thông thường là non-interactive connection, vì vậy giá trị session **wait_timeout** thường được khởi tạo từ giá trị global **wait_timeout** khi kết nối được tạo.

Giá trị mặc định MySQL thường là 28.800 giây (8 giờ), nhưng cấu hình thực tế có thể thấp hơn nhiều do quản trị viên, dịch vụ database managed hoặc chính sách hạ tầng đặt ra. Luôn kiểm tra giá trị đang chạy thay vì dựa vào mặc định.

**wait_timeout** là giới hạn **idle time**, không phải giới hạn tổng tuổi của connection:

- Một câu query đang được MySQL thực thi không phải session đang chờ idle.
- Sau khi câu lệnh hoàn tất và session không gửi thêm lệnh, bộ đếm idle tiếp tục có ý nghĩa.
- Một connection được trả về pool và nằm yên có thể bị đóng khi vượt **wait_timeout**.
- Một transaction giữ connection nhưng không gửi câu lệnh trong thời gian dài cũng có thể để session ở trạng thái Sleep; server có thể đóng session đó và transaction chưa commit sẽ bị rollback.

Điều cuối cùng đặc biệt quan trọng với JPA: không giữ transaction mở trong lúc chờ người dùng, gọi API bên ngoài hoặc xử lý tác vụ dài không liên quan đến database.

### 3.2. wait_timeout và interactive_timeout

MySQL có hai biến liên quan:

- **wait_timeout:** dùng cho session không tương tác.
- **interactive_timeout:** dùng để khởi tạo timeout cho session được kết nối với cờ client interactive.

Khi một session mới được tạo, MySQL khởi tạo giá trị session **wait_timeout** dựa trên loại client. JDBC thường không đặt cờ interactive, nên ứng dụng Spring Boot cần quan tâm đến **wait_timeout**.

Kiểm tra giá trị global và session:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW SESSION VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';

SELECT
  CONNECTION_ID() AS connection_id,
  @@GLOBAL.wait_timeout AS global_wait_timeout,
  @@SESSION.wait_timeout AS session_wait_timeout;
~~~

Hai giá trị global và session có thể khác nhau. Session hiện tại giữ giá trị riêng được khởi tạo khi kết nối được tạo hoặc được thay đổi trực tiếp trong session.

### 3.3. Thay đổi wait_timeout

Thay đổi global:

~~~sql
SET GLOBAL wait_timeout = 1800;
~~~

Thao tác này áp dụng cho các session mới được tạo sau đó; các session đã tồn tại trong HikariCP không tự động nhận giá trị mới.

Thay đổi session hiện tại:

~~~sql
SET SESSION wait_timeout = 1800;
~~~

Lệnh này chỉ tác động session đang chạy lệnh. Nếu muốn đặt giá trị session cho mọi physical connection mới do HikariCP tạo, có thể dùng **connectionInitSql** trong trường hợp có lý do vận hành rõ ràng. Lệnh khởi tạo chỉ chạy khi tạo physical connection, không chạy mỗi lần request mượn connection.

Không nên giảm **wait_timeout** xuống vài giây để "dọn connection" khi chưa đánh giá pool và workload. Giá trị quá thấp có thể đóng connection trong lúc ứng dụng giữ transaction hoặc connection idle được mượn, dẫn đến lỗi khó tái hiện.

## 4. HikariCP maxLifetime

### 4.1. Tuổi tối đa của physical connection

**maxLifetime** là tuổi tối đa mà HikariCP cho phép một physical connection tồn tại trong pool, tính từ khi connection được tạo. Đến hạn, pool đánh dấu connection để retire và thay bằng connection mới khi cần.

Đặc điểm quan trọng:

- Giá trị tính bằng millisecond.
- Nó giới hạn tuổi connection, không đo thời gian connection nằm idle.
- Connection đang được mượn sẽ không bị HikariCP cưỡng bức đóng chỉ vì đã vượt **maxLifetime**.
- Khi connection được trả về pool sau khi hết tuổi, HikariCP sẽ loại nó thay vì tiếp tục tái sử dụng.
- Nên đặt thấp hơn giới hạn tuổi connection cứng do database proxy, cloud service hoặc hạ tầng mạng quy định, có một khoảng đệm an toàn.

Ví dụ, nếu một proxy có giới hạn tuổi connection vật lý 60 phút, có thể đặt **maxLifetime** thấp hơn giới hạn đó, chẳng hạn 55 phút. Giá trị cụ thể cần dựa trên chính sách của dịch vụ và kiểm thử thực tế.

### 4.2. maxLifetime không giống wait_timeout

**maxLifetime** và **wait_timeout** không thay thế nhau:

- **maxLifetime** đếm tuổi connection kể từ lúc tạo, kể cả khi connection được sử dụng thường xuyên.
- **wait_timeout** đếm khoảng thời gian session không có hoạt động.
- Một connection có thể sống nhiều giờ nếu liên tục hoạt động và không bị giới hạn tuổi bởi hạ tầng.
- Một connection mới tạo vài phút vẫn có thể bị MySQL đóng nếu nó idle quá **wait_timeout**.
- HikariCP không đóng một connection đang được mượn ngay khi **maxLifetime** hết hạn.

Có thể đặt **maxLifetime** thấp hơn **wait_timeout** như một chính sách bảo thủ để pool thường xuyên thay connection trước ngưỡng idle của server. Tuy nhiên, về mặt ngữ nghĩa, **wait_timeout** là idle timeout; nếu **keepaliveTime** đã duy trì connection idle trong pool và không có giới hạn tuổi cứng khác, không bắt buộc **maxLifetime** phải luôn nhỏ hơn **wait_timeout**.

### 4.3. Chọn maxLifetime

Trước khi đặt giá trị, tìm giới hạn tuổi connection của tất cả lớp hạ tầng: MySQL managed service, proxy, load balancer, firewall, NAT và service mesh nếu có.

Ví dụ:

- Database hoặc proxy đóng mọi connection sau 60 phút dù vẫn có hoạt động: đặt **maxLifetime** ngắn hơn 60 phút.
- Hạ tầng chỉ đóng connection khi idle 10 phút: cần xem **keepaliveTime** và trạng thái connection; **maxLifetime** giải quyết tuổi tổng, không trực tiếp thay thế keepalive.
- Không có giới hạn tuổi cứng đã biết: giá trị mặc định HikariCP có thể là điểm khởi đầu, sau đó đánh giá theo version và hành vi thực tế.

Không đặt **maxLifetime** bằng đúng giới hạn của proxy hoặc database. Thời điểm đóng có thể không chính xác tuyệt đối; cần khoảng đệm để pool chủ động retire trước.

## 5. HikariCP keepaliveTime

### 5.1. Keepalive làm gì?

**keepaliveTime** quy định khoảng cách giữa các lần kiểm tra một connection đang idle trong pool. Khi đến lịch, HikariCP tạm lấy connection đó ra khỏi pool, gửi một phép kiểm tra liveness qua JDBC, rồi trả connection lại nếu vẫn khỏe mạnh.

Keepalive hữu ích khi:

- MySQL **wait_timeout** ngắn.
- Firewall, NAT hoặc load balancer đóng TCP connection idle.
- Một database proxy có idle timeout.
- Ứng dụng giữ một số connection idle trong pool để phục vụ request tiếp theo.

HikariCP có thể sử dụng JDBC **Connection.isValid()** để kiểm tra liveness. Với JDBC driver hỗ trợ JDBC4, thường không cần cấu hình **connectionTestQuery** thủ công.

### 5.2. Keepalive chỉ áp dụng cho connection idle trong pool

Keepalive không gửi ping cho connection đang được ứng dụng mượn. Vì vậy:

- Connection idle trong pool có thể được kiểm tra định kỳ.
- Connection đang được mượn và đang chạy query không cần keepalive.
- Connection đang được mượn nhưng ứng dụng để yên trong transaction vẫn có thể bị MySQL hoặc proxy đóng.
- Keepalive không cứu được một connection đã bị mạng cắt khi nó đang được sử dụng.

Nếu ứng dụng giữ connection trong transaction rồi chờ một API bên ngoài 20 phút, đặt **keepaliveTime=2 phút** không có nghĩa HikariCP sẽ ping connection đó trong 20 phút. Cách xử lý đúng là rút ngắn transaction và không giữ connection khi không cần database.

### 5.3. Chọn keepaliveTime

**keepaliveTime** phải nhỏ hơn **maxLifetime**. Với HikariCP hiện hành, giá trị quá nhỏ dưới ngưỡng tối thiểu của thư viện sẽ không hợp lệ; kiểm tra tài liệu của version đang dùng.

Để tránh server hoặc network đóng connection trước khi ping, đặt keepalive thấp hơn **idle timeout nhỏ nhất** trong toàn bộ đường đi, có khoảng đệm đáng kể.

Ví dụ:

- MySQL **wait_timeout** là 30 phút.
- Proxy đóng TCP connection idle sau 10 phút.
- HikariCP cần ping trước ngưỡng 10 phút; có thể bắt đầu thử nghiệm với **keepaliveTime=5 phút**.
- Nếu pool không cần giữ connection idle, có thể giảm **minimumIdle** hoặc để pool co lại bằng **idleTimeout** thay vì ping quá nhiều connection.

Không đặt keepalive đúng bằng timeout của proxy. Scheduler, tải hệ thống và độ trễ mạng có thể khiến ping đến muộn.

## 6. idleTimeout, connectionTimeout và các timeout liên quan

### 6.1. idleTimeout

**idleTimeout** là thời gian connection dư thừa có thể nằm idle trong pool trước khi HikariCP loại bỏ nó. Nó giúp pool co lại khi nhu cầu giảm.

**idleTimeout** chỉ có tác dụng co pool khi **minimumIdle** nhỏ hơn **maximumPoolSize**. Nếu pool được cấu hình cố định với **minimumIdle** bằng **maximumPoolSize**, HikariCP giữ số connection đó và **idleTimeout** không làm pool giảm kích thước.

Đừng nhầm **idleTimeout** với MySQL **wait_timeout**:

- **idleTimeout:** pool quyết định có nên đóng connection idle của chính nó hay không.
- **wait_timeout:** MySQL quyết định đóng session không hoạt động.
- **keepaliveTime:** pool kiểm tra connection idle để phát hiện hoặc tránh bị lớp bên ngoài đóng.

### 6.2. connectionTimeout

**connectionTimeout** là thời gian tối đa một thread chờ lấy connection từ pool. Nó không phải:

- Thời gian MySQL cho phép một session idle.
- Thời gian tối đa một câu SQL chạy.
- TCP connect timeout.
- Socket read timeout.

Nếu pool đã hết connection và mọi connection đều đang được mượn, request mới có thể chờ đến **connectionTimeout** rồi nhận lỗi từ HikariCP.

Các timeout khác có thể nằm ở JDBC URL hoặc cấu hình transaction:

| Timeout | Thành phần | Mục đích |
|---|---|---|
| Hikari **connectionTimeout** | HikariCP | Chờ mượn connection |
| Connector/J **connectTimeout** | JDBC driver | Chờ thiết lập socket TCP |
| Connector/J **socketTimeout** | JDBC driver | Giới hạn thời gian chờ đọc dữ liệu từ socket |
| Hikari **validationTimeout** | HikariCP | Giới hạn thời gian kiểm tra connection |
| Hikari **idleTimeout** | HikariCP | Thu hồi connection dư thừa đang idle |
| Hikari **maxLifetime** | HikariCP | Giới hạn tuổi connection |
| MySQL **wait_timeout** | MySQL Server | Đóng session không tương tác đã idle |
| Query/transaction timeout | JDBC/Spring/database | Giới hạn thời gian thực thi hoặc transaction theo cơ chế tương ứng |

Đặt **connectionTimeout** thấp không làm query chậm chạy nhanh hơn. Nếu pool cạn, cần điều tra thời gian giữ connection, query chậm, transaction dài và kích thước pool.

## 7. Cấu hình Spring Boot với HikariCP

### 7.1. Ví dụ application.yml

Giả sử hệ thống có các giới hạn sau:

- MySQL **wait_timeout** được cấu hình 1.800 giây (30 phút).
- Proxy mạng đóng connection idle sau 10 phút.
- Hệ thống muốn thay connection chủ động sau khoảng 25 phút.
- Pool giữ tối thiểu 5 connection và tối đa 20 connection cho mỗi instance ứng dụng.

Một cấu hình khởi điểm để thử nghiệm:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal:3306/appdb?sslMode=VERIFY_IDENTITY&serverTimezone=UTC
    username: app_user
    password: ${DB_PASSWORD}
    hikari:
      pool-name: app-mysql-pool
      maximum-pool-size: 20
      minimum-idle: 5
      max-lifetime: 1500000
      keepalive-time: 300000
      idle-timeout: 600000
      connection-timeout: 30000
      validation-timeout: 5000
~~~

Giải thích:

- **max-lifetime: 1500000** là 25 phút.
- **keepalive-time: 300000** là 5 phút, thấp hơn proxy idle timeout 10 phút và MySQL wait timeout 30 phút.
- **idle-timeout: 600000** là 10 phút; pool có thể thu hồi connection idle vượt nhu cầu, miễn là **minimum-idle** nhỏ hơn **maximum-pool-size**.
- **connection-timeout: 30000** cho request chờ tối đa 30 giây để mượn connection.
- **validation-timeout: 5000** giới hạn thời gian kiểm tra connection.

Đây là ví dụ theo giả định cụ thể, không phải bộ giá trị phù hợp cho mọi môi trường. Cần kiểm tra giới hạn thực tế của database managed service, proxy, firewall và version HikariCP mà Spring Boot đã resolve.

Không commit mật khẩu thật vào YAML. Dùng secret hoặc biến môi trường. Nếu ứng dụng tự tạo nhiều **DataSource** bean, bảo đảm cấu hình Hikari được bind vào đúng pool thay vì chỉ cấu hình **spring.datasource.hikari** cho datasource mặc định.

### 7.2. Kiểm tra cấu hình hiệu lực

Sau khi khởi động, kiểm tra log khởi tạo HikariCP và cấu hình pool hiệu lực. Không suy luận rằng một property đã được áp dụng chỉ vì nó xuất hiện trong file YAML; profile, biến môi trường, cấu hình ngoài hoặc custom bean có thể ghi đè.

Nếu thay đổi **wait_timeout** global, những connection vật lý đã được tạo trước đó vẫn giữ session value cũ. Pool cần dần thay các connection cũ hoặc được drain/recycle có kiểm soát để các kết nối mới nhận giá trị session mới.

### 7.3. Không cấu hình connectionTestQuery một cách máy móc

HikariCP ưu tiên JDBC4 **Connection.isValid()** khi driver hỗ trợ. Với MySQL Connector/J hiện đại, thường không cần đặt:

~~~yaml
spring:
  datasource:
    hikari:
      connection-test-query: SELECT 1
~~~

Chỉ cấu hình **connection-test-query** khi driver hoặc môi trường không hỗ trợ JDBC4 validation như yêu cầu. Một câu query kiểm tra tùy chỉnh không tự giải quyết được timeout hoặc transaction giữ connection quá lâu.

## 8. Tính toán quan hệ giữa các timeout

### 8.1. Tìm timeout nhỏ nhất trên đường kết nối

Một connection có thể bị đóng bởi nhiều thành phần. Hãy kiểm tra:

- MySQL **wait_timeout** cho session idle.
- Idle timeout của proxy hoặc load balancer.
- TCP idle timeout của firewall/NAT.
- Giới hạn tuổi connection cứng của dịch vụ database hoặc proxy.
- Chính sách recycle connection của connection pool.

Đặt **keepaliveTime** thấp hơn idle timeout nhỏ nhất mà keepalive có thể tác động đến, có khoảng đệm. Đặt **maxLifetime** thấp hơn giới hạn tuổi connection cứng. Với MySQL **wait_timeout**, nhớ rằng đây là idle timeout chứ không phải giới hạn tuổi tổng.

### 8.2. Ví dụ đổi đơn vị

| Giá trị | Đơn vị ban đầu | Quy đổi |
|---|---:|---:|
| MySQL **wait_timeout=1800** | 1.800 giây | 30 phút |
| Proxy idle timeout | 600 giây | 10 phút |
| Hikari **keepaliveTime=300000** | 300.000 ms | 5 phút |
| Hikari **maxLifetime=1500000** | 1.500.000 ms | 25 phút |
| Hikari **idleTimeout=600000** | 600.000 ms | 10 phút |

Trong ví dụ, keepalive 5 phút có thể ping connection idle trong pool trước khi proxy đóng nó ở phút thứ 10. **maxLifetime** 25 phút chủ động thay connection theo tuổi. Nếu connection đang được mượn, cả keepalive lẫn việc hết maxLifetime đều không đảm bảo connection sẽ bị đóng ngay lúc đó; MySQL hoặc network vẫn có thể đóng một session borrowed đang idle theo quy tắc riêng.

### 8.3. Kích thước pool cũng ảnh hưởng vòng đời

Một pool quá lớn làm tăng số session MySQL và có thể giữ nhiều connection idle không cần thiết. Một pool quá nhỏ khiến request chờ connection dù database vẫn còn tài nguyên.

Tính tổng connection tối đa từ tất cả instance ứng dụng:

**Tổng connection ứng dụng = số instance × maximumPoolSize mỗi instance**

Cộng thêm worker, batch job, migration tool, monitoring và kết nối quản trị. Tổng này phải thấp hơn **max_connections** với headroom cho failover, rolling deployment và tác vụ vận hành.

Ví dụ, 4 instance với **maximumPoolSize=20** có thể tạo tối đa 80 connection. Nếu rolling deployment tạm thời chạy 2 nhóm instance cùng lúc, số connection có thể tăng gần gấp đôi. Đừng chỉ tính số pod ở trạng thái ổn định.

## 9. Spring Transaction và JPA có thể giữ connection bao lâu?

### 9.1. Transaction quyết định thời gian mượn connection

Trong một luồng xử lý thông thường:

1. Spring bắt đầu transaction.
2. JPA/Hibernate cần truy cập database và mượn connection từ DataSource.
3. Các câu SQL được gửi qua Connector/J.
4. Spring commit hoặc rollback transaction.
5. Connection được trả về pool.

Thời điểm lấy connection có thể phụ thuộc cấu hình Hibernate, transaction manager và lazy connection handling. Tuy nhiên, transaction dài thường giữ connection lâu và làm giảm số connection sẵn sàng cho request khác.

### 9.2. Không giữ transaction trong lúc gọi dịch vụ ngoài

Ví dụ không tốt:

~~~java
@Transactional
public void checkout(Long orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();

    paymentClient.charge(order); // Gọi mạng bên ngoài khi transaction còn mở

    order.markPaid();
}
~~~

Lời gọi thanh toán có thể mất nhiều giây hoặc timeout. Trong suốt thời gian đó, transaction có thể giữ connection, lock và tài nguyên database. Nếu không có hoạt động SQL trong thời gian vượt **wait_timeout**, MySQL có thể đóng session.

Một thiết kế tốt hơn thường chia transaction ngắn quanh thao tác database, gọi dịch vụ bên ngoài ngoài transaction và dùng outbox/saga hoặc trạng thái trung gian khi cần bảo đảm tính nhất quán nghiệp vụ. Chi tiết thiết kế phụ thuộc yêu cầu xử lý thanh toán; không chỉ đơn giản chuyển annotation là đủ.

### 9.3. maxLifetime không phải transaction timeout

Nếu một request giữ connection trong 40 phút và **maxLifetime** là 25 phút, HikariCP không cưỡng bức ngắt connection đó ở phút thứ 25. Connection sẽ được retire khi trả về pool. Tuy nhiên, MySQL **wait_timeout** hoặc proxy vẫn có thể đóng session trong thời gian ứng dụng giữ connection mà không gửi lệnh.

Dùng transaction timeout, query timeout và giới hạn thời gian xử lý nghiệp vụ theo yêu cầu riêng. Không dùng **maxLifetime** thay cho timeout transaction.

## 10. Chẩn đoán lỗi kết nối

### 10.1. Kiểm tra MySQL

Chạy trên một session mới và session đang tồn tại:

~~~sql
SELECT
  CONNECTION_ID(),
  @@GLOBAL.wait_timeout,
  @@SESSION.wait_timeout,
  @@SESSION.interactive_timeout;

SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Aborted_clients';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';

SHOW PROCESSLIST;
~~~

- **Threads_connected** cho biết số connection hiện tại.
- **Aborted_clients** tăng có thể phản ánh client ngắt không đúng cách hoặc connection bị đóng bất thường; cần xem cùng log.
- **Aborted_connects** phản ánh các lần kết nối thất bại.
- **SHOW PROCESSLIST** giúp nhận diện session đang Sleep, query chạy lâu hoặc trạng thái bất thường.

Các counter là số liệu tích lũy từ lúc server khởi động hoặc reset status; xem xu hướng theo thời gian, không kết luận từ một giá trị đơn lẻ.

### 10.2. Kiểm tra HikariCP

Theo dõi các metric pool nếu ứng dụng có Actuator/Micrometer:

- **hikaricp.connections.active:** connection đang được mượn.
- **hikaricp.connections.idle:** connection đang idle trong pool.
- **hikaricp.connections.pending:** số thread đang chờ connection.
- **hikaricp.connections.max** và **min:** giới hạn pool.
- **hikaricp.connections.timeout:** số lần timeout khi mượn connection.

Nếu **active** thường xuyên chạm **max** và **pending** tăng, điều tra query chậm, transaction dài, leak hoặc pool quá nhỏ. Tăng **maximumPoolSize** không tự động giải quyết vấn đề nếu MySQL đã gần giới hạn connection hoặc CPU/I/O đang bão hòa.

Chỉ mở endpoint Actuator metrics cho người hoặc hệ thống được phép. Metric và log có thể tiết lộ tên pool, cấu trúc hệ thống hoặc thông tin vận hành.

### 10.3. Dấu hiệu và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Lỗi xuất hiện sau một khoảng idle khá cố định | **wait_timeout** hoặc proxy idle timeout | So sánh session timeout với thời gian lỗi; kiểm tra log proxy |
| Lỗi khi request mượn connection từ pool | Connection idle trong pool đã bị server đóng | Kiểm tra keepalive, pool validation và MySQL error log |
| Lỗi khi đang xử lý transaction dài | Connection borrowed bị server/proxy đóng vì idle hoặc timeout khác | Kiểm tra thời gian không gửi SQL, transaction và proxy |
| Hikari báo timeout lấy connection | Pool cạn, connection bị giữ lâu hoặc tạo connection mới thất bại | Xem active/idle/pending, slow query và log kết nối |
| **Too many connections** | Tổng pool từ nhiều instance vượt năng lực server | Tính tổng maximumPoolSize và kiểm tra **max_connections** |
| Lỗi chỉ xuất hiện sau deploy hoặc thay đổi global timeout | Pool cũ còn physical connection với session value cũ | Kiểm tra **@@SESSION.wait_timeout**, recycle pool có kiểm soát |
| Lỗi xuất hiện trong query dài | Socket timeout, proxy query timeout, server restart hoặc network interruption | Đối chiếu Connector/J, proxy và MySQL error log |

Không gán mọi lỗi "MySQL server has gone away" cho **wait_timeout**. Nguyên nhân cũng có thể là restart server, packet quá lớn, network reset, proxy timeout, socket timeout hoặc lỗi tài nguyên.

## 11. Quy trình xử lý khi connection bị đóng bất ngờ

1. Ghi lại timestamp, request ID, thread, connection pool name và exception gốc.
2. Xác định lỗi xảy ra khi mượn connection, khi chạy SQL, lúc commit hay khi trả connection.
3. Kiểm tra **@@SESSION.wait_timeout** của session tương ứng nếu còn truy cập được.
4. Đối chiếu thời điểm lỗi với MySQL error log, proxy/firewall log và sự kiện restart/failover.
5. Kiểm tra Hikari active/idle/pending và connection creation/validation errors.
6. Kiểm tra transaction có bị giữ mở trong khi chờ I/O hoặc xử lý nghiệp vụ không.
7. Xác định idle timeout nhỏ nhất và hard lifetime của từng lớp hạ tầng.
8. Điều chỉnh **keepaliveTime**, **maxLifetime**, **idleTimeout** hoặc transaction boundary theo nguyên nhân.
9. Kiểm thử trong staging với timeout gần giống production.
10. Theo dõi metric và error rate sau khi triển khai.

Nếu một transaction bị mất connection trước khi commit, ứng dụng cần coi kết quả transaction là thất bại hoặc không xác định tùy thời điểm lỗi. Không retry mọi lệnh ghi một cách mù quáng: client có thể mất kết nối sau khi server đã commit nhưng trước khi nhận phản hồi. Dùng idempotency key hoặc cơ chế tra cứu trạng thái nghiệp vụ để retry an toàn.

## 12. Checklist cấu hình và vận hành

### Trước khi đặt timeout

- [ ] Xác định HikariCP version thực tế do Spring Boot resolve.
- [ ] Đọc **wait_timeout** global và session.
- [ ] Kiểm tra idle timeout của proxy, firewall, NAT và load balancer.
- [ ] Xác định hard connection lifetime nếu dịch vụ có áp dụng.
- [ ] Đổi mọi giá trị về cùng đơn vị trước khi so sánh.

### Khi cấu hình HikariCP

- [ ] Đặt **keepaliveTime** nhỏ hơn idle timeout nhỏ nhất mà pool cần vượt qua, có khoảng đệm.
- [ ] Bảo đảm **keepaliveTime** nhỏ hơn **maxLifetime**.
- [ ] Đặt **maxLifetime** thấp hơn hard connection lifetime của hạ tầng.
- [ ] Chọn **minimumIdle**, **maximumPoolSize** và **idleTimeout** theo tải.
- [ ] Đặt **connectionTimeout** theo thời gian chờ pool mà ứng dụng chấp nhận.
- [ ] Dùng JDBC4 validation nếu driver hỗ trợ; tránh cấu hình test query không cần thiết.
- [ ] Tính tổng connection từ tất cả instance và job trước khi tăng pool.

### Khi vận hành Spring/JPA

- [ ] Không giữ transaction trong lúc gọi API bên ngoài hoặc chờ người dùng.
- [ ] Giới hạn thời gian transaction và query theo yêu cầu nghiệp vụ.
- [ ] Theo dõi Hikari active, idle, pending và timeout.
- [ ] Kiểm tra **@@SESSION.wait_timeout** trên connection mới sau khi đổi global.
- [ ] Drain/recycle connection pool có kiểm soát khi cần áp dụng session setting mới.
- [ ] Kiểm thử rolling deployment, failover và network interruption.
- [ ] Retry transaction có tính idempotent hoặc có cơ chế xác minh kết quả commit.

## 13. Tự kiểm tra

**Tình huống 1:** MySQL **wait_timeout** là 600 giây, Hikari **keepaliveTime** là 900.000 ms. Điều gì có thể xảy ra với connection idle trong pool?

**Gợi ý:** Keepalive 900.000 ms là 900 giây, dài hơn 600 giây. MySQL có thể đóng session trước lần ping tiếp theo; cần đặt keepalive thấp hơn timeout có khoảng đệm.

**Tình huống 2:** Hikari **maxLifetime** là 20 phút nhưng một transaction giữ connection 35 phút. Hikari có cưỡng bức đóng connection ở phút thứ 20 không?

**Gợi ý:** Không. Hikari đánh dấu connection để retire và loại khi nó được trả về pool. Tuy nhiên, MySQL hoặc proxy vẫn có thể đóng session nếu connection idle hoặc vi phạm giới hạn riêng.

**Tình huống 3:** **keepaliveTime** là 2 phút, nhưng ứng dụng giữ connection trong transaction rồi chờ dịch vụ thanh toán 15 phút. Keepalive có bảo vệ connection đó không?

**Gợi ý:** Không. Connection đang được mượn nên không phải idle connection trong pool. Cần thiết kế transaction ngắn và không giữ connection trong lúc chờ mạng bên ngoài.

**Tình huống 4:** DBA chạy **SET GLOBAL wait_timeout=900**, nhưng một connection đã tồn tại vẫn báo **@@SESSION.wait_timeout=28800**. Đây có phải lỗi không?

**Gợi ý:** Không. Giá trị global được dùng để khởi tạo session mới; session đang tồn tại giữ giá trị riêng. Hãy kiểm tra connection mới hoặc recycle pool có kiểm soát.

**Tình huống 5:** Hikari báo connection timeout dù MySQL còn ít connection hơn **max_connections**. Nên kiểm tra gì?

**Gợi ý:** Kiểm tra **active**, **idle**, **pending**, thời gian giữ connection, transaction dài, query chậm và lỗi tạo/validation connection. **connectionTimeout** là thời gian chờ pool, không phải giới hạn connection của MySQL.

## 14. Điểm cần ghi nhớ

- HikariCP quản lý vòng đời physical connection; JPA/Spring mượn connection theo nhu cầu transaction.
- **maxLifetime** giới hạn tuổi tổng của connection và retire khi connection được trả về pool.
- **keepaliveTime** ping connection idle trong pool; nó không bảo vệ connection đang được ứng dụng mượn.
- MySQL **wait_timeout** là idle timeout của session non-interactive, không phải giới hạn tuổi tổng.
- Giá trị **wait_timeout** session được khởi tạo từ global khi kết nối được tạo; thay đổi global không sửa session đang tồn tại.
- **idleTimeout** giúp pool co lại; **connectionTimeout** giới hạn thời gian chờ mượn connection.
- Đặt keepalive thấp hơn idle timeout nhỏ nhất và maxLifetime thấp hơn hard connection lifetime, có khoảng đệm.
- Không giữ transaction mở khi gọi dịch vụ ngoài; connection borrowed vẫn có thể bị MySQL hoặc proxy đóng.
- Tổng maximum pool size của tất cả instance phải nằm trong ngân sách **max_connections**.
- Điều tra lỗi bằng timestamp, MySQL session, Hikari metrics và log của proxy/network; không mặc định mọi lỗi connection đều do wait_timeout.

## Tài liệu tham khảo

- [HikariCP: Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby) — maxLifetime, keepaliveTime, idleTimeout, pool sizing và validation.
- [Spring Boot Reference: SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html) — cấu hình DataSource và HikariCP trong Spring Boot.
- [MySQL 8.4 Reference Manual: Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_wait_timeout) — wait_timeout và interactive_timeout.
- [MySQL Connector/J: Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html) — connectTimeout, socketTimeout, TLS và cấu hình JDBC.
- [Spring Boot Reference: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — thu thập và quan sát metric ứng dụng.
