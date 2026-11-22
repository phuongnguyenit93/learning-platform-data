# Giới hạn autoReconnect, failover URL và tính toàn vẹn giao dịch

MySQL Connector/J có thể thử kết nối tới host khác khi kết nối hiện tại bị lỗi, nhưng việc chọn được host mới không có nghĩa transaction đang chạy được tiếp tục. Một kết nối JDBC gắn với một session MySQL; khi session mất, transaction chưa hoàn tất, temporary table, session variable, lock và các thiết lập session có thể không còn. Đặc biệt, nếu mạng đứt đúng lúc gửi COMMIT, ứng dụng có thể không biết server đã commit hay chưa.

Vì vậy, cần phân biệt ba lớp: **phát hiện kết nối lỗi**, **chọn endpoint thay thế** và **khôi phục nghiệp vụ an toàn**. Thuộc tính autoReconnect và multi-host failover URL hỗ trợ một phần ở hai lớp đầu. Tính toàn vẹn giao dịch vẫn cần được thiết kế ở ứng dụng, topology database và quy trình retry.

Bài học thuộc chương **Connector/J** của module DATABASE_MYSQL. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Ví dụ sử dụng JDBC và MySQL Connector/J; kiểm tra tài liệu của phiên bản driver đang triển khai vì một số thuộc tính failover và hành vi kết nối đã thay đổi giữa các phiên bản.

Sau bài học, bạn có thể:

- Giải thích autoReconnect có thể làm gì và không thể bảo đảm điều gì.
- Phân biệt lỗi kết nối với lỗi SQL và kết quả commit chưa xác định.
- Cấu hình multi-host failover URL đúng mục đích.
- Phân biệt failover, load balancing và replication connection.
- Hiểu vai trò của MySQL Router trong InnoDB Cluster.
- Thiết kế timeout, connection pool và validation.
- Retry transaction an toàn bằng idempotency key và reconciliation.
- Kiểm thử failover mà không tạo ghi trùng hoặc mất dữ liệu.

## 1. Ba lớp cần phân biệt

Một hệ thống Java kết nối MySQL có ít nhất ba lớp hành vi khi xảy ra sự cố:

| Lớp | Câu hỏi cần trả lời | Thành phần liên quan |
|---|---|---|
| Phát hiện lỗi | Socket hoặc session còn hoạt động không? | TCP, timeout, Connector/J, connection pool |
| Chuyển endpoint | Có host nào khác có thể nhận kết nối không? | Multi-host JDBC URL, MySQL Router, topology/cluster |
| Khôi phục nghiệp vụ | Transaction đã commit chưa và có thể thực hiện lại không? | Ứng dụng, transaction boundary, idempotency, unique constraint |

Ví dụ: ứng dụng gửi lệnh thanh toán, MySQL commit transaction, nhưng phản hồi COMMIT bị mất do network partition. Driver thấy kết nối hỏng. Một host khác có thể chấp nhận connection mới, nhưng driver không thể suy ra chỉ từ lỗi socket rằng transaction trước đã commit hay rollback.

Một thiết kế an toàn phải xử lý cả ba lớp. Chỉ thêm host vào URL hoặc bật autoReconnect không đủ để bảo đảm dữ liệu nghiệp vụ.

## 2. autoReconnect là gì?

Connector/J có thuộc tính kết nối §autoReconnect§. Thuộc tính này cho phép driver thử thiết lập lại kết nối khi phát hiện connection cũ bị stale hoặc chết. Theo mặc định, autoReconnect tắt.

Ví dụ cấu hình:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?autoReconnect=true
~~~

Không nên xem đây là cơ chế phục hồi transaction. Một connection mới là một session MySQL mới. Driver không thể khôi phục trạng thái transaction đang mở trên session cũ, cũng không thể tái tạo mọi trạng thái session mà ứng dụng đã thiết lập.

Các trạng thái có thể bị mất khi kết nối được tạo lại:

- Transaction đang mở và các thay đổi chưa commit.
- Temporary table tạo trong session.
- User variable và session variable.
- Lock được giữ bởi session, gồm named lock.
- Isolation level, autocommit và read-only state nếu ứng dụng đã thay đổi ở session.
- Current schema/database nếu được đổi bằng câu lệnh session.
- Prepared statement phía server và cursor đang mở.
- Trạng thái đọc ResultSet hoặc vị trí cursor.
- Session context như SQL mode hoặc timezone nếu ứng dụng đặt riêng.

Một số trạng thái có thể được driver hoặc pool thiết lập lại theo cấu hình, nhưng ứng dụng không được giả định session mới tương đương hoàn toàn session cũ.

**Nguyên tắc:** autoReconnect có thể giúp tạo lại kết nối cho một thao tác tiếp theo trong một số tình huống, nhưng không chứng minh câu lệnh trước đã hoàn tất và không khôi phục transaction đang chạy.

## 3. Vì sao không nên dựa vào autoReconnect cho transaction?

Giả sử ứng dụng thực hiện:

~~~sql
START TRANSACTION;
UPDATE sales.accounts
SET balance = balance - 100
WHERE account_id = 10;
UPDATE sales.accounts
SET balance = balance + 100
WHERE account_id = 20;
COMMIT;
~~~

Nếu kết nối mất sau UPDATE đầu tiên, transaction trên session cũ chưa commit. Khi server phát hiện session đã mất, transaction chưa commit sẽ được rollback theo cơ chế của InnoDB. Nhưng thời điểm server phát hiện lỗi có thể khác thời điểm ứng dụng nhận exception.

Nếu kết nối mất ngay trong lúc COMMIT, có hai khả năng:

1. Server chưa commit transaction. Khi session kết thúc, thay đổi được rollback.
2. Server đã commit, nhưng phản hồi xác nhận không tới được client.

Từ phía ứng dụng, cả hai trường hợp có thể biểu hiện thành timeout hoặc communication exception. Nếu ứng dụng kết nối lại và chạy toàn bộ transaction một cách mù quáng, trường hợp thứ hai có thể tạo giao dịch nghiệp vụ trùng.

autoReconnect không thể giải quyết sự mơ hồ này. Driver không có đủ thông tin để tự quyết định transaction nghiệp vụ có nên chạy lại hay không.

### 3.1. Kết quả COMMIT chưa xác định

Một lỗi xảy ra trước khi gửi COMMIT thường có thể được xử lý bằng rollback và retry toàn bộ transaction nếu lỗi tạm thời và nghiệp vụ cho phép. Nhưng lỗi xảy ra trong hoặc sau khi gửi COMMIT cần được xem là **outcome unknown** cho đến khi ứng dụng đối chiếu được trạng thái.

Không được suy luận rằng:

- Client nhận exception thì transaction chắc chắn rollback.
- Client không nhận exception thì mọi replica đã apply xong.
- Driver reconnect thành công thì transaction cũ đã được khôi phục.
- Câu lệnh UPDATE không trả kết quả thì database chưa thay đổi.

Hãy dùng mã request duy nhất và lưu kết quả nghiệp vụ trong cùng transaction để có thể tra cứu sau khi kết nối lại.

## 4. Multi-host failover URL

Connector/J hỗ trợ URL có nhiều host để driver có thể thử endpoint khác khi một host không kết nối được hoặc kết nối hiện tại gặp lỗi thuộc trường hợp driver hỗ trợ failover.

Ví dụ:

~~~text
jdbc:mysql://db-a.example.internal:3306,db-b.example.internal:3306/sales?connectTimeout=5000&socketTimeout=30000&sslMode=VERIFY_IDENTITY
~~~

Trong ví dụ:

- db-a và db-b là các endpoint của topology đã được thiết kế cho failover.
- sales là database mặc định.
- connectTimeout giới hạn thời gian thiết lập kết nối.
- socketTimeout giới hạn thời gian chờ đọc dữ liệu trên socket.
- sslMode=VERIFY_IDENTITY yêu cầu xác minh danh tính server qua TLS.

Host list chỉ mô tả các địa chỉ mà driver có thể thử. Nó không tự bầu primary, không kiểm tra quorum, không đồng bộ dữ liệu và không bảo đảm host tiếp theo có quyền ghi.

### 4.1. Điều kiện của các host trong danh sách

Trước khi đưa nhiều host vào URL, cần trả lời:

- Các host có thuộc cùng một logical database hoặc cùng topology replication không?
- Dữ liệu trên các host có cùng nguồn gốc và mức nhất quán được chấp nhận không?
- Host nào được phép nhận ghi tại thời điểm hiện tại?
- Cơ chế nào promote replica hoặc bầu primary khi node lỗi?
- Làm sao tránh hai host cùng nhận ghi độc lập sau network partition?
- Client có nhận biết trạng thái read-only và retry phù hợp không?
- Các host có cùng TLS policy, account, grants, schema và cấu hình session không?

Không đưa một replica bất kỳ vào danh sách failover ghi chỉ vì cổng TCP đang mở. Replica có thể đang trễ, read-only hoặc chưa được promote. Driver kết nối được tới replica không có nghĩa replica đã sẵn sàng nhận giao dịch ghi.

### 4.2. Thứ tự host và khả năng thử lại

Thứ tự host trong URL có thể ảnh hưởng thứ tự kết nối/thử host theo chế độ và phiên bản driver. Không dùng thứ tự này như một cơ chế bầu primary hoặc một hợp đồng đảm bảo host đầu tiên luôn là writer.

Một số thuộc tính liên quan failover, như §failOverReadOnly§ hoặc §retriesAllDown§, có hành vi phụ thuộc phiên bản và chế độ multi-host. Đọc tài liệu Connector/J của đúng phiên bản trước khi dùng. Đặc biệt, hãy hiểu rõ driver sẽ đặt connection thành read-only thế nào khi chuyển host và số lần thử khi tất cả host đều không khả dụng.

Không đặt retry vô hạn ở cả driver, pool, framework HTTP và tầng nghiệp vụ cùng lúc. Nhiều lớp retry có thể nhân số lần gọi, làm tăng tải khi hệ thống đang phục hồi và kéo dài thời gian request.

## 5. Failover URL không phải hệ thống HA

Failover URL chỉ giúp client thử một endpoint khác theo khả năng driver. Nó không cung cấp đầy đủ các chức năng của hệ thống high availability.

| Khả năng | Multi-host URL tự cung cấp? |
|---|---|
| Thử kết nối host khác | Có, trong các tình huống failover được driver hỗ trợ |
| Bầu primary mới | Không |
| Promote replica | Không |
| Kiểm tra quorum | Không |
| Đồng bộ transaction giữa các host | Không |
| Chọn node có dữ liệu mới nhất | Không tự bảo đảm |
| Ngăn split brain | Không |
| Khôi phục transaction đã mất session | Không |
| Biết chắc COMMIT đã thành công sau khi mất phản hồi | Không |

Topology database cần một cơ chế HA riêng như Group Replication/InnoDB Cluster, replication kèm orchestrator hoặc nền tảng quản lý database tương ứng. Driver chỉ là một phần của đường kết nối từ ứng dụng tới topology đó.

Nếu dùng MySQL asynchronous replication, replica có thể chưa nhận được transaction mới nhất. Nếu ứng dụng failover ghi sang replica trễ mà không có quy trình promote và xác nhận dữ liệu, có thể xảy ra mất dữ liệu đã xác nhận trên primary cũ hoặc phát sinh hai writer.

## 6. Phân biệt failover, load balancing và replication URL

Connector/J có các chế độ URL multi-host khác nhau. Không dùng chúng thay thế cho nhau.

| URL scheme | Mục đích | Ý nghĩa vận hành |
|---|---|---|
| jdbc:mysql://host1,host2/db | Kết nối MySQL với khả năng failover | Driver thử host khác khi kết nối hiện tại không còn dùng được theo chính sách failover. |
| jdbc:mysql:loadbalance://host1,host2/db | Load balancing | Phân phối kết nối/hoạt động theo cơ chế load balancing của driver và cấu hình. |
| jdbc:mysql:replication://source,replica/db | Replication connection | Hỗ trợ tách đường đọc/ghi giữa source và replica qua trạng thái read-only của connection. |

### 6.1. Load balancing

Ví dụ:

~~~text
jdbc:mysql:loadbalance://db-a.example.internal:3306,db-b.example.internal:3306/sales
~~~

Load balancing không đồng nghĩa failover. Driver có thể phân phối kết nối hoặc chuyển host theo chính sách load balancing. Chỉ dùng khi các host được thiết kế để phục vụ cùng workload với tính nhất quán và quyền ghi tương thích.

Không đưa các node có dữ liệu khác nhau hoặc vai trò writer/reader không đồng nhất vào load balancing như thể chúng là các máy giống nhau.

### 6.2. Replication connection

Ví dụ:

~~~text
jdbc:mysql:replication://mysql-source.example.internal:3306,mysql-replica.example.internal:3306/sales
~~~

Replication connection hỗ trợ quản lý kết nối tới source và replica. Ứng dụng có thể đánh dấu connection read-only để driver định tuyến truy vấn đọc theo chế độ hỗ trợ; khi read-only tắt, truy vấn ghi được gửi theo đường source.

Ví dụ khái quát:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setReadOnly(true);
    // Truy vấn đọc theo chính sách replication connection.
}
~~~

Không đặt read-only chỉ để “tăng tốc” nếu transaction có thể thực hiện ghi. Cũng không giả định mọi SELECT đều có thể gửi tới replica: một số truy vấn cần read-after-write, đọc dữ liệu mới nhất, dùng temporary table hoặc phụ thuộc session state cần ở cùng node.

Kiểm tra tài liệu Connector/J cho cách cấu hình replication connection, chuyển trạng thái read-only, phát hiện host và xử lý failover trong phiên bản sử dụng.

## 7. failOverReadOnly và nguy cơ ghi nhầm replica

Trong chế độ multi-host failover, thuộc tính §failOverReadOnly§ có thể điều khiển việc connection được đặt read-only khi driver chuyển sang host thay thế. Giá trị mặc định và chi tiết hành vi phải được kiểm tra theo phiên bản Connector/J.

Đặt connection read-only khi failover có thể giúp ngăn ứng dụng vô tình ghi lên một replica chưa được promote. Tuy nhiên, đây không phải cơ chế phân quyền ở server và cũng không thay thế việc kiểm tra vai trò node.

Các lớp bảo vệ nên gồm:

- Server replica được cấu hình read-only/super-read-only khi phù hợp.
- Driver hoặc Router định tuyến đúng endpoint theo vai trò.
- Ứng dụng kiểm tra trạng thái và xử lý lỗi read-only.
- Cơ chế HA xác nhận promotion hoàn tất trước khi mở ghi.
- Runbook ngăn primary cũ quay lại nhận ghi đồng thời với primary mới.

Không tắt failover read-only chỉ để tránh lỗi ghi khi driver chuyển host, trừ khi topology bảo đảm mọi host đều là writer hợp lệ và có cơ chế consistency tương ứng.

## 8. MySQL Router và InnoDB Cluster

Với InnoDB Cluster, MySQL Router là lớp định tuyến được thiết kế để theo dõi metadata của cụm và đưa kết nối tới endpoint phù hợp với vai trò hiện tại. Ứng dụng thường kết nối tới Router thay vì tự duy trì danh sách từng member.

Ví dụ URL dùng endpoint Router:

~~~text
jdbc:mysql://mysql-router.example.internal:6446/sales?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000
~~~

Cổng trong ví dụ là minh họa; dùng endpoint read/write hoặc read-only thực tế được cấu hình trên Router của môi trường.

Router không làm transaction JDBC sống sót qua một connection đã mất. Nếu kết nối tới Router bị ngắt giữa transaction, ứng dụng vẫn phải xử lý rollback/outcome unknown như bình thường. Router hỗ trợ định tuyến kết nối mới theo metadata cluster; nó không thể khôi phục session cũ ở một socket mới.

Khi dùng Router:

- Cấu hình Router và metadata theo hướng dẫn InnoDB Cluster.
- Dùng endpoint write cho transaction cần ghi.
- Chỉ dùng endpoint read-only khi ứng dụng chấp nhận consistency/replication lag.
- Bảo đảm Router instance đủ dự phòng để không trở thành điểm lỗi đơn.
- Theo dõi trạng thái Router, cluster member và quorum riêng biệt.
- Kiểm thử ứng dụng khi primary chuyển vai trò và khi Router restart.

## 9. Phát hiện kết nối hỏng và timeout

Các lỗi kết nối có thể được phát hiện bởi TCP, Connector/J, pool hoặc server. Không có một timeout duy nhất bao phủ mọi giai đoạn.

| Cơ chế | Phạm vi | Cần lưu ý |
|---|---|---|
| connectTimeout | Thiết lập socket/kết nối | Không giới hạn thời gian chạy query sau khi đã kết nối. |
| socketTimeout | Chờ dữ liệu từ socket | Quá ngắn có thể làm query hợp lệ bị xem là timeout. |
| Statement.setQueryTimeout | Thời gian thực thi theo JDBC | Hành vi cancel phụ thuộc driver/server. |
| Connection.isValid(timeout) | Kiểm tra connection | Dùng bởi ứng dụng/pool; không đảm bảo transaction chưa có lỗi. |
| TCP keepalive | Phát hiện một số kết nối chết qua mạng | Thời gian phát hiện phụ thuộc OS và network. |
| Pool validation/keepalive | Kiểm tra connection khi mượn hoặc lúc idle | Cần cấu hình theo idle timeout của database/proxy. |

Ví dụ URL với timeout:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?connectTimeout=5000&socketTimeout=30000&sslMode=VERIFY_IDENTITY
~~~

Các giá trị timeout của Connector/J thường được tính bằng millisecond. Chọn theo SLA, độ trễ mạng, kích thước kết quả và thời gian truy vấn hợp lệ. socketTimeout không nên được đặt thấp hơn p99 của truy vấn dài nếu ứng dụng cần cho phép truy vấn đó hoàn thành.

### 9.1. Connection.isClosed và Connection.isValid

§Connection.isClosed()§ chủ yếu cho biết connection đã bị đóng ở phía JDBC hay chưa. Nó không phải phép thử đáng tin cậy rằng socket và server vẫn có thể trao đổi dữ liệu.

§Connection.isValid(timeoutSeconds)§ yêu cầu driver kiểm tra tính hợp lệ của connection theo API JDBC. Pool có thể dùng phương thức này hoặc validation query để loại connection stale trước khi giao cho request.

Ngay cả isValid vừa trả true, mạng vẫn có thể đứt ngay sau đó. Validation giảm khả năng mượn connection đã chết nhưng không loại bỏ race condition.

## 10. Connection pool và stale connection

Trong ứng dụng server, connection pool thường quản lý vòng đời physical connection. Pool có thể kiểm tra connection khi mượn, giữ kết nối sống, loại bỏ connection quá tuổi và tạo connection mới khi cần.

Một cấu hình pool cần xem xét:

- Maximum pool size theo năng lực MySQL.
- Connection acquisition timeout.
- Validation timeout.
- Idle timeout.
- Max lifetime ngắn hơn timeout đóng kết nối của proxy/firewall khi cần.
- Keepalive phù hợp cho connection idle.
- Leak detection để tìm connection không được trả về.
- Cách pool loại connection sau SQLException loại connection failure.

Ví dụ cấu hình khái quát với HikariCP:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(
    "jdbc:mysql://mysql-router.example.internal:6446/sales" +
    "?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000"
);
config.setUsername(dbUser);
config.setPassword(dbPassword);
config.setMaximumPoolSize(20);
config.setConnectionTimeout(5000);
config.setValidationTimeout(3000);
config.setMaxLifetime(1500000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Các con số chỉ là ví dụ. maxLifetime cần được đặt theo giới hạn thực tế của MySQL, Router, proxy hoặc firewall. Không sao chép nguyên cấu hình này vào production mà chưa đo tải và kiểm tra timeout hạ tầng.

Không dùng autoReconnect để thay thế cơ chế pool. Pool cần biết connection vật lý nào đã lỗi để loại bỏ và cấp một connection mới sạch. Driver tự reconnect bên trong một connection có thể che giấu vòng đời vật lý và làm ứng dụng khó kiểm soát session state.

### 10.1. Validation query

Một số pool cho phép đặt validation query như §SELECT 1§. Nếu pool và driver hỗ trợ JDBC isValid tốt, thường không cần chạy validation query cho mọi lần mượn connection. Validation quá thường xuyên làm tăng round trip và tải database.

Cấu hình validation theo khả năng pool, phiên bản driver và hạ tầng. Không chạy một câu query kiểm tra bằng chính connection đang giữ transaction nghiệp vụ để suy luận transaction vẫn nguyên vẹn.

## 11. Nhận diện lỗi kết nối

JDBC cung cấp SQLState, vendor error code và loại SQLException để phân loại lỗi.

Các dấu hiệu thường gặp:

| Dấu hiệu | Ý nghĩa có thể | Hành động |
|---|---|---|
| SQLState class 08 | Connection exception | Kiểm tra socket, server, Router và khả năng host failover. |
| MySQL error 2006 | Server has gone away | Kiểm tra server restart, idle timeout, packet hoặc connection stale. |
| MySQL error 2013 | Lost connection during query | Kiểm tra network, query duration, socket timeout và server log. |
| SQLTransientConnectionException | Lỗi kết nối có thể tạm thời theo phân loại JDBC | Chỉ retry nếu transaction/outcome được xử lý an toàn. |
| SQLNonTransientConnectionException | Lỗi kết nối không được xem là tạm thời theo phân loại driver | Kiểm tra cấu hình, topology và trạng thái endpoint. |

Không phân loại chỉ bằng chuỗi message. Hãy ghi nhận SQLState, vendor code, exception class, thời điểm, host đã kết nối, thời gian query và trạng thái transaction. Tránh log password, access token hoặc dữ liệu nhạy cảm.

Một lỗi SQL như duplicate key, deadlock hoặc thiếu quyền không phải lỗi connection. Xử lý theo nguyên nhân cụ thể thay vì gửi mọi SQLException vào cùng một vòng retry.

## 12. Điều gì xảy ra với transaction khi failover?

Hãy phân biệt các thời điểm mất kết nối:

| Thời điểm mất kết nối | Điều ứng dụng biết | Cách xử lý |
|---|---|---|
| Trước khi gửi statement | Statement chưa được gửi theo luồng ứng dụng | Có thể mở connection mới và thử lại nếu request chưa có side effect. |
| Trong lúc statement chạy | Server có thể đã nhận một phần hoặc hoàn tất xử lý nhưng phản hồi mất | Xem transaction state; với thao tác ghi, không đoán kết quả chỉ từ timeout. |
| Sau statement, trước COMMIT | Transaction chưa được xác nhận commit | Nếu session đã kết thúc, transaction InnoDB chưa commit sẽ rollback; cần xử lý connection/session và retry toàn transaction khi an toàn. |
| Trong lúc gửi COMMIT | Outcome có thể không xác định ở client | Tra cứu idempotency key hoặc trạng thái nghiệp vụ trước khi chạy lại. |
| Sau khi nhận xác nhận COMMIT | Server đã xác nhận commit với client | Transaction đã commit trên server; độ bền và replication visibility phụ thuộc cấu hình MySQL/topology. |

Nếu session chết, server sẽ xử lý transaction chưa commit theo cơ chế của storage engine khi phát hiện session kết thúc. Nhưng ứng dụng có thể không biết thời điểm đó đã xảy ra. Không dùng connection mới để gọi rollback rồi nghĩ rằng transaction cũ đã rollback; rollback trên session mới không tác động transaction của session cũ.

Failover cũng không bảo đảm replica đã nhận transaction cuối cùng của primary cũ. Mức mất dữ liệu có thể có phụ thuộc replication mode, durability setting, quorum và quy trình promotion.

## 13. Idempotency key để retry an toàn

Một request ghi có thể được gửi lại vì client timeout, gateway retry hoặc người dùng bấm lại. Dùng idempotency key duy nhất cho một thao tác nghiệp vụ để server nhận biết request đã được xử lý.

Ví dụ bảng lưu kết quả request:

~~~sql
CREATE TABLE sales.processed_requests (
  request_id VARCHAR(64) NOT NULL,
  operation_type VARCHAR(40) NOT NULL,
  result_order_id BIGINT NULL,
  result_status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id)
) ENGINE=InnoDB;
~~~

Khi xử lý request, tạo request_id ở tầng ứng dụng và dùng cùng key cho mọi lần retry của đúng một thao tác nghiệp vụ.

Luồng transaction:

1. Bắt đầu transaction.
2. Insert request_id vào bảng processed_requests.
3. Thực hiện thay đổi nghiệp vụ.
4. Lưu kết quả hoặc mã đối tượng vào processed_requests.
5. Commit transaction.
6. Trả kết quả cho client.

Nếu request_id đã tồn tại, ứng dụng đọc kết quả đã lưu và trả lại, không thực hiện thay đổi nghiệp vụ lần nữa.

Ví dụ SQL minh họa:

~~~sql
START TRANSACTION;

INSERT INTO sales.processed_requests (
  request_id, operation_type, result_status
)
VALUES (
  'req-2026-000001', 'CREATE_ORDER', 'PROCESSING'
);

INSERT INTO sales.orders (
  customer_id, status, total_amount
)
VALUES (
  42, 'NEW', 125.00
);

SET @new_order_id = LAST_INSERT_ID();

UPDATE sales.processed_requests
SET result_order_id = @new_order_id,
    result_status = 'COMPLETED'
WHERE request_id = 'req-2026-000001';

COMMIT;
~~~

Nếu transaction rollback, cả request record và đơn hàng đều rollback. Nếu commit thành công nhưng phản hồi mất, lần retry insert cùng request_id sẽ gặp duplicate key; ứng dụng bắt lỗi duplicate, đọc record đã tồn tại và trả lại kết quả trước đó.

Trong code thật, dùng PreparedStatement cho request_id và dữ liệu đầu vào. Xử lý duplicate key riêng; không bỏ qua mọi lỗi SQL. Đảm bảo record idempotency được lưu đủ lâu theo chính sách retry và đối soát.

### 13.1. Tránh trạng thái PROCESSING bị treo

Nếu record PROCESSING được commit riêng trước nghiệp vụ, tiến trình có thể chết và để lại trạng thái dở dang. Thiết kế đơn giản hơn là tạo record, cập nhật nghiệp vụ và đánh dấu COMPLETED trong cùng transaction InnoDB.

Nếu cần xử lý bất đồng bộ, dùng state machine có lease/owner, timeout và cơ chế phục hồi rõ ràng. Không coi một trạng thái PROCESSING cũ là bằng chứng request chắc chắn chưa thực hiện side effect.

## 14. Side effect ngoài database và transactional outbox

Nếu transaction vừa ghi MySQL vừa gọi dịch vụ thanh toán, gửi email hoặc publish message trực tiếp, hai hệ thống không cùng một transaction local. Kết nối MySQL mất không thể rollback side effect ở hệ thống bên ngoài.

Mẫu transactional outbox:

1. Trong một transaction MySQL, cập nhật dữ liệu nghiệp vụ và insert một event vào bảng outbox.
2. Commit cả hai cùng lúc.
3. Worker đọc event chưa gửi và publish tới hệ thống bên ngoài.
4. Worker đánh dấu event đã gửi hoặc dùng trạng thái/lease để retry.
5. Consumer dùng event ID để xử lý idempotent.

Ví dụ:

~~~sql
CREATE TABLE sales.outbox_events (
  event_id CHAR(36) NOT NULL,
  aggregate_id BIGINT NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at TIMESTAMP NULL,
  PRIMARY KEY (event_id),
  KEY idx_outbox_pending (status, created_at)
) ENGINE=InnoDB;
~~~

Outbox không tự bảo đảm gửi đúng một lần. Worker có thể publish thành công rồi chết trước khi đánh dấu event; khi chạy lại, event có thể được publish lần nữa. Consumer cần deduplicate theo event_id hoặc áp dụng nghiệp vụ idempotent.

## 15. Retry policy ở tầng ứng dụng

Một retry policy cần xác định:

- Những exception nào được coi là tạm thời.
- Request nào có thể chạy lại an toàn.
- Transaction boundary ở đâu.
- Có cần tạo connection mới không.
- Số lần retry tối đa.
- Backoff và jitter.
- Deadline tổng của request.
- Cách xử lý commit outcome unknown.
- Cách ghi metric và cảnh báo.

Mẫu pseudocode:

~~~text
request_id = tạo hoặc nhận idempotency key

for attempt từ 1 đến giới hạn:
    mượn connection mới từ pool
    bắt đầu transaction
    thử xử lý request với request_id
    nếu thành công:
        commit
        trả kết quả
    nếu lỗi trước commit và có thể retry:
        rollback nếu connection còn dùng được
        đóng connection
        chờ exponential backoff + jitter
        tiếp tục
    nếu lỗi trong lúc commit:
        đóng connection
        tra cứu request_id qua connection mới
        nếu đã COMPLETED:
            trả kết quả đã lưu
        nếu chưa có:
            thực hiện lại theo chính sách idempotent
        nếu không xác định được:
            đưa vào reconciliation, không ghi mù quáng
~~~

Không retry vô hạn. Tổng thời gian retry phải nằm trong deadline của request và không tạo retry storm khi MySQL hoặc network đang phục hồi.

### 15.1. Exponential backoff và jitter

Nếu nhiều client cùng retry ngay sau failover, chúng có thể tạo một đợt tải lớn đúng lúc database đang phục hồi. Backoff làm giãn các lần thử; jitter thêm ngẫu nhiên để client không đồng bộ thời điểm retry.

Ví dụ thời gian chờ tăng theo lần thử:

| Lần thử | Khoảng chờ minh họa |
|---|---:|
| 1 | 100–200 ms |
| 2 | 200–400 ms |
| 3 | 400–800 ms |
| 4 | 800–1600 ms |

Đây chỉ là giá trị minh họa; dùng cap và deadline thực tế. Không để tầng driver, pool và business service cùng retry nhiều lần mà không có một ngân sách retry tổng.

## 16. Kiểm tra vai trò host và read-after-write

Sau failover, ứng dụng phải biết endpoint mới có vai trò gì. Một TCP connection thành công không xác nhận host là primary.

Có thể kiểm tra trạng thái server bằng truy vấn phù hợp:

~~~sql
SELECT
  @@hostname,
  @@server_uuid,
  @@read_only,
  @@super_read_only,
  @@global.gtid_executed;
~~~

Các giá trị này giúp quan sát host và trạng thái read-only, nhưng không thay thế metadata của cluster hoặc quy trình promotion. Một node read-write chưa chắc là primary hợp lệ trong topology; một node read-only có thể vẫn đang apply replication.

Read-after-write cũng cần được xem xét. Nếu ứng dụng ghi ở primary rồi đọc từ replica, replica có thể chưa apply transaction đó. Các cách xử lý gồm:

- Giữ truy vấn đọc sau ghi trên writer.
- Dùng consistency policy phù hợp của topology.
- Chờ replica đạt GTID cần thiết nếu kiến trúc có cơ chế xác nhận.
- Đưa request phụ thuộc dữ liệu mới nhất về cùng một endpoint có consistency phù hợp.

Không mặc định failover xong thì mọi replica đều đã đồng bộ đến transaction cuối.

## 17. Các tình huống cần kiểm thử

Failover phải được kiểm thử trên staging hoặc môi trường diễn tập với topology tương tự production. Các kịch bản tối thiểu:

| Kịch bản | Điều cần quan sát |
|---|---|
| Host đầu tiên không mở cổng | Driver thử host khác theo cấu hình; thời gian kết nối nằm trong deadline. |
| Connection idle bị firewall đóng | Pool phát hiện và loại connection stale trước hoặc trong lần sử dụng tiếp theo. |
| MySQL restart giữa SELECT | Ứng dụng phân loại connection exception và xử lý truy vấn đọc có thể retry. |
| Mất kết nối giữa UPDATE và COMMIT | Transaction chưa commit không được tiếp tục trên session mới. |
| Mất phản hồi ngay sau COMMIT | Ứng dụng tra cứu idempotency key và xác định kết quả. |
| Primary failover trong InnoDB Cluster | Router cập nhật định tuyến; request đang chạy xử lý exception đúng. |
| Replica bị trễ hoặc chưa promote | Không gửi ghi tới replica chỉ vì host kết nối được. |
| Tất cả host đều unavailable | Retry có giới hạn, circuit breaker và thông báo lỗi rõ ràng. |
| Host cũ quay lại sau partition | Không để hai writer nhận cùng workload ngoài topology được kiểm soát. |

Trong bài kiểm thử, ghi lại timestamp, host, SQLState, vendor code, thời gian reconnect, transaction outcome, request ID và số lần retry. Không dùng dữ liệu production thật nếu chưa có quy trình bảo vệ phù hợp.

## 18. Ví dụ Java xử lý outcome unknown

Đoạn code dưới đây minh họa ý tưởng, không phải một retry framework hoàn chỉnh. Phần quan trọng là dùng cùng request ID và truy vấn kết quả sau khi lỗi commit.

~~~java
public OrderResult createOrder(
        DataSource dataSource,
        String requestId,
        long customerId,
        BigDecimal total) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            // Thử ghi request key trong cùng transaction nghiệp vụ.
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO sales.processed_requests " +
                    "(request_id, operation_type, result_status) " +
                    "VALUES (?, 'CREATE_ORDER', 'PROCESSING')")) {
                ps.setString(1, requestId);
                ps.executeUpdate();
            }

            long orderId;
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO sales.orders " +
                    "(customer_id, status, total_amount) " +
                    "VALUES (?, 'NEW', ?)",
                    Statement.RETURN_GENERATED_KEYS)) {
                ps.setLong(1, customerId);
                ps.setBigDecimal(2, total);
                ps.executeUpdate();

                try (ResultSet keys = ps.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Missing generated order id");
                    }
                    orderId = keys.getLong(1);
                }
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE sales.processed_requests " +
                    "SET result_order_id = ?, result_status = 'COMPLETED' " +
                    "WHERE request_id = ?")) {
                ps.setLong(1, orderId);
                ps.setString(2, requestId);
                ps.executeUpdate();
            }

            connection.commit();
            return new OrderResult(orderId, "COMPLETED");

        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
~~~

Nếu commit ném exception do mất kết nối, phương thức trên chỉ ném lỗi ra ngoài; caller cần mở connection mới và tra cứu request_id. Nếu record đã tồn tại với trạng thái COMPLETED, trả lại order ID đã lưu. Nếu record chưa tồn tại, transaction trước có thể đã rollback; thực hiện lại cùng request ID theo quy tắc idempotent. Nếu trạng thái không thể xác định, đưa request vào reconciliation.

Trong triển khai thực tế, cần xử lý duplicate key ở bước insert request, kiểm tra operation_type, xác nhận request_id gắn với cùng payload/khách hàng, và không cho một request_id được tái sử dụng cho một nghiệp vụ khác.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bật autoReconnect và coi transaction vẫn sống | Ứng dụng tiếp tục trên session mới nhưng mất trạng thái transaction/session cũ | Xử lý connection failure và bắt đầu transaction mới theo quy trình an toàn. |
| Retry ngay khi COMMIT ném exception | Giao dịch đã commit có thể được thực hiện lần nữa | Dùng idempotency key và tra cứu kết quả. |
| Thêm replica vào writer failover list | Ghi nhầm vào node read-only hoặc dữ liệu trễ | Dùng topology/Router có promotion và role routing rõ ràng. |
| Cho rằng multi-host URL tự promote primary | Driver kết nối được nhưng node chưa có vai trò writer | Dùng Group Replication/Orchestrator hoặc cơ chế HA riêng. |
| Tắt failOverReadOnly mà không kiểm soát vai trò | Có thể ghi vào replica chưa promote | Bảo vệ ở server, Router và ứng dụng; kiểm thử promotion. |
| Dùng timeout quá ngắn | Query hợp lệ bị cắt, phát sinh lỗi và retry thừa | Đặt timeout theo SLA và p99 thực tế. |
| Pool giữ connection lâu hơn idle timeout mạng | Request mượn connection đã bị đóng | Cấu hình validation, keepalive và maxLifetime theo hạ tầng. |
| Nhiều lớp retry không có ngân sách chung | Retry storm và tăng tải khi phục hồi | Chọn một retry owner, giới hạn attempts và deadline. |
| Gọi API ngoài trong transaction DB | Side effect không rollback cùng MySQL | Dùng transactional outbox và consumer idempotent. |
| Chỉ kiểm tra kết nối thành công | Không biết host có dữ liệu mới nhất hoặc quyền ghi hợp lệ | Kiểm tra vai trò, GTID, quorum và trạng thái replication. |

## 20. Checklist cấu hình và vận hành

- [ ] Đã xác định topology MySQL và vai trò của từng host.
- [ ] Không dùng autoReconnect như cam kết phục hồi transaction.
- [ ] Multi-host URL chỉ chứa endpoint hợp lệ cho chế độ failover dự kiến.
- [ ] Đã phân biệt failover URL, loadbalance URL và replication URL.
- [ ] Đã xác định cách promote primary và ngăn split brain.
- [ ] Đã kiểm tra failOverReadOnly và các thuộc tính liên quan theo phiên bản.
- [ ] TLS xác minh danh tính server cho mọi endpoint.
- [ ] connectTimeout, socketTimeout và query timeout phù hợp SLA.
- [ ] Connection pool có validation, maxLifetime và giới hạn kích thước phù hợp.
- [ ] Connection/Statement/ResultSet được đóng đúng cách.
- [ ] Ứng dụng phân loại SQLState và vendor error code.
- [ ] Transaction được chia boundary rõ ràng.
- [ ] Có idempotency key cho request ghi có thể retry.
- [ ] Kết quả COMMIT chưa xác định được đối chiếu trước khi retry.
- [ ] Side effect ngoài database được xử lý qua outbox hoặc cơ chế tương đương.
- [ ] Đã kiểm thử mất kết nối trước, trong và sau COMMIT.
- [ ] Đã kiểm thử primary failover, replica lag và trường hợp tất cả host down.
- [ ] Có metric cho connection failure, reconnect, retry, transaction outcome và pool exhaustion.

## 21. Bài tập thực hành

### Bài 1: Quan sát autoReconnect

Trong môi trường thử nghiệm, mở Connection và thực hiện truy vấn. Dừng MySQL hoặc ngắt network rồi chạy truy vấn tiếp theo với autoReconnect tắt và bật. Ghi nhận exception, trạng thái Connection, transaction và session variable. Giải thích vì sao reconnect không khôi phục transaction cũ.

### Bài 2: Multi-host URL

Tạo hai MySQL endpoint trong topology thử nghiệm. Cấu hình multi-host URL, cho host đầu tiên unavailable và quan sát driver thử endpoint còn lại. Xác nhận endpoint thay thế có đúng dữ liệu, role và quyền ghi theo thiết kế.

### Bài 3: Mất phản hồi COMMIT

Thực hiện một giao dịch có request ID duy nhất. Dùng proxy hoặc môi trường thử nghiệm để ngắt kết nối ngay sau khi server nhận COMMIT nhưng trước khi client nhận phản hồi. Kết nối lại, tra cứu request ID và xác định transaction đã hoàn tất hay chưa.

### Bài 4: Pool và stale connection

Cấu hình pool với validation và maxLifetime. Đặt idle timeout của proxy/firewall thử nghiệm ngắn hơn vòng đời connection, sau đó quan sát cách pool loại connection stale và cấp connection mới. Kiểm tra request không dùng lại session đã chết.

### Bài 5: Failover trên InnoDB Cluster

Dùng Router endpoint, thực hiện transaction đọc/ghi rồi diễn tập chuyển primary. Ghi nhận thời gian gián đoạn, lỗi JDBC, số lần retry và cách ứng dụng xử lý transaction đang mở. Xác nhận request ID không tạo đơn hàng trùng.

### Bài 6: Retry storm

Chạy nhiều client và làm endpoint tạm thời unavailable. So sánh retry không giới hạn với exponential backoff có jitter, deadline và circuit breaker. Đo số lần kết nối, thời gian phục hồi và tải MySQL/Router.

Failover giúp ứng dụng có cơ hội kết nối tới một endpoint còn hoạt động; autoReconnect có thể thử tạo lại connection trong một số tình huống. Cả hai không khôi phục transaction của session cũ và không xác định được kết quả COMMIT khi phản hồi bị mất. Hãy để topology quản lý vai trò node, pool quản lý vòng đời connection và ứng dụng quản lý idempotency cùng kết quả nghiệp vụ; kiểm thử các điểm mất kết nối quanh COMMIT trước khi triển khai production.

