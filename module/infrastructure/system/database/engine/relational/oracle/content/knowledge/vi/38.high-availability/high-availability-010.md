# FAN, Fast Connection Failover và phối hợp với connection pool trong Oracle Database

Trong môi trường Oracle RAC hoặc Oracle Data Guard, một instance, node hoặc database service có thể bị dừng do sự cố hoặc được chuyển đi để bảo trì. Ở phía ứng dụng, các kết nối đã mở trong connection pool có thể trở thành stale: pool vẫn giữ đối tượng connection nhưng database endpoint mà connection trỏ tới đã không còn phục vụ.

Nếu ứng dụng chỉ phát hiện kết nối hỏng khi gửi câu SQL tiếp theo, request có thể bị treo trong thời gian timeout mạng hoặc nhận lỗi muộn. Oracle cung cấp **Fast Application Notification (FAN)** để database thông báo nhanh cho client về thay đổi trạng thái service/instance/node. **Fast Connection Failover (FCF)** là cơ chế client/pool sử dụng các sự kiện FAN để xác định và xử lý các connection bị ảnh hưởng.

FCF phối hợp với connection pool để:

- Loại bỏ các connection stale khỏi pool khi xảy ra outage ngoài kế hoạch.
- Drain connection theo ranh giới an toàn khi bảo trì có kế hoạch.
- Nhận biết service/instance mới sẵn sàng và tạo connection đến nơi còn khả dụng.
- Hỗ trợ runtime load balancing khi cấu hình dịch vụ và pool phù hợp.

Điểm cần hiểu chính xác: FCF quản lý vòng đời physical connection và thông báo lỗi cho ứng dụng. FCF tự nó không replay SQL hoặc transaction đang chạy. Với outage ngoài kế hoạch, transaction chưa commit trên connection bị mất sẽ được rollback ở database và ứng dụng nhận exception. Nếu cần che outage và replay request, cần cấu hình Application Continuity/Transparent Application Continuity; nếu cần xác định commit outcome để tránh gửi transaction hai lần, cần Transaction Guard.

Tài liệu này trình bày FAN, FCF và cách phối hợp với connection pool, tập trung vào Oracle UCP/JDBC và các nguyên tắc có thể áp dụng cho pool bên thứ ba.

## 1. Kiến trúc FAN và FCF

### 1.1 FAN là gì?

Fast Application Notification là cơ chế phát thông báo sự kiện từ Oracle Clusterware/database services đến các client đã đăng ký nhận sự kiện. FAN cho biết trạng thái tài nguyên thay đổi, ví dụ:

- Một database service được start hoặc stop.
- Một service member trên một instance bị down hoặc up.
- Một instance hoặc node bị down.
- Một instance mới gia nhập và cung cấp service.
- Runtime Load Balancing Advisory thay đổi phân bố tải khuyến nghị.

FAN giúp client nhận thông tin thay đổi sớm thay vì chỉ phát hiện lỗi thông qua lần gửi SQL tiếp theo.

### 1.2 FCF là gì?

Fast Connection Failover là một FAN client được tích hợp với connection pool. Pool nhận sự kiện FAN, xác định connection nào được tạo từ service/instance bị ảnh hưởng và xử lý chúng theo loại sự kiện.

Trong Oracle Universal Connection Pool (UCP), FCF cung cấp khả năng quản lý connection theo vòng đời service. Oracle JDBC driver cũng hỗ trợ FAN events cho third-party pools từ JDBC 12.2.0.1, nhưng UCP có tích hợp sâu hơn và hỗ trợ đầy đủ hơn các chức năng FAN của Oracle.

### 1.3 Luồng sự kiện tổng quát

~~~text
Oracle RAC / Data Guard service
          |
          |  FAN event: UP / DOWN / Load Advisory
          v
Oracle Notification Service (ONS)
          |
          |  publish / subscribe notification
          v
JDBC driver / FAN client trong JVM
          |
          v
Fast Connection Failover trong connection pool
          |
          +--> xác định connection theo service/instance
          |
          +--> loại bỏ connection idle bị stale
          |
          +--> đánh dấu connection borrowed để drain
          |
          +--> tạo connection mới đến instance còn hoạt động
          |
          v
Ứng dụng tiếp tục request hoặc xử lý exception/retry
~~~

### 1.4 Phân biệt các thành phần

| Thành phần | Vai trò |
|---|---|
| Oracle RAC service | Định nghĩa workload và điểm kết nối logic cho ứng dụng |
| FAN | Thông báo thay đổi trạng thái service/instance/node và load advisory |
| ONS | Vận chuyển FAN notifications đến client subscribers |
| JDBC FAN support | Nhận và xử lý FAN events ở JDBC driver |
| FCF | Kết hợp FAN với connection pool để dọn/recreate connection |
| Connection pool | Quản lý physical connection, logical handle, borrow/return và validation |
| Application Continuity | Có thể replay database request sau recoverable outage |
| Transaction Guard | Cung cấp kết quả commit của transaction cuối cùng sau outage |

FAN và ONS là lớp thông báo; FCF là lớp quản lý connection; Application Continuity/Transaction Guard giải quyết các khía cạnh phục hồi request và transaction.

## 2. Các loại FAN event quan trọng

FAN event thường mang thông tin về loại event, trạng thái, service, instance, node và lý do thay đổi.

### 2.1 Service UP

UP event thông báo một service hoặc service member mới sẵn sàng. Connection pool có thể tạo connection mới đến instance vừa gia nhập hoặc service vừa khởi động.

Ví dụ:

- RAC instance được restart sau bảo trì.
- Service được relocate về node ban đầu.
- Một instance mới được thêm vào cluster và cung cấp service.

Pool có thể dần phân bổ connection mới sang instance vừa UP theo load balancing advisory.

### 2.2 Service DOWN ngoài kế hoạch

Unplanned DOWN có thể phát sinh khi:

- Instance crash.
- Node bị mất.
- Service bị lỗi hoặc không còn khả dụng.
- Network/storage failure khiến service không phục vụ được.

FCF xác định các connection thuộc service/instance bị down, ngắt network connection của connection stale và loại chúng khỏi pool. Cả connection đang idle lẫn connection đang được borrow có thể bị ảnh hưởng. Với connection đang được sử dụng, ứng dụng sẽ nhận exception khi thao tác trên connection hoặc khi driver báo connection đã đóng.

Transaction đang mở trên session bị mất sẽ được database rollback. Ứng dụng phải xử lý lỗi, lấy connection mới và quyết định có thể retry request/transaction an toàn hay không.

### 2.3 Planned DOWN

Planned DOWN được phát khi DBA chủ động stop hoặc relocate service/instance để bảo trì. Event có trạng thái down và reason biểu thị việc dừng có kế hoạch; trong nhiều event RAC, reason có thể là user.

FCF xử lý khác unplanned DOWN:

- Connection idle trong pool bị loại bỏ ngay vì không có request đang dùng.
- Connection borrowed được đánh dấu để drain và chỉ bị đóng khi công việc hoàn tất, connection được trả về pool hoặc đi qua safe-draining point phù hợp.
- Request đang chạy có cơ hội hoàn tất bình thường.

Đây là nền tảng để rolling maintenance mà không làm gián đoạn request đang thực thi.

### 2.4 Node DOWN và Instance DOWN

Node DOWN thông báo node không còn khả dụng. Instance DOWN thông báo database instance bị dừng hoặc không còn cung cấp service. Các event này có thể ảnh hưởng nhiều service và nhiều connection cùng lúc.

Pool nên dựa trên FAN metadata để xác định connection bị ảnh hưởng, không dùng một lần health check thất bại trên một connection để kết luận toàn bộ cluster đã down.

### 2.5 Load Balancing Advisory

Runtime Load Balancing Advisory (RLB) cung cấp thông tin khuyến nghị phân phối công việc giữa các instance đang cung cấp service. Event có thể chứa tỷ lệ phân bổ tải hoặc thông tin affinity.

UCP có thể dùng advisory để lựa chọn instance khi tạo connection mới và phân phối request khi connection được borrow. Advisory thay đổi theo tải thực tế, service goal và trạng thái instance.

RLB không thay thế connection load balancing lúc kết nối ban đầu. Hai cơ chế bổ sung nhau:

- Connection Load Balancing (CLB): listener phân phối các kết nối mới đến instance.
- Runtime Load Balancing (RLB): pool dùng FAN advisory để chọn nơi phù hợp cho connection/request trong quá trình chạy.

## 3. Planned outage và unplanned outage khác nhau thế nào?

Đây là khác biệt quan trọng nhất khi vận hành FCF.

| Tình huống | Connection idle trong pool | Connection đang được borrow | Transaction đang chạy |
|---|---|---|---|
| Planned DOWN | Bị loại khỏi pool | Được đánh dấu drain; đóng tại check-in/safe point | Có cơ hội hoàn tất |
| Unplanned DOWN | Bị loại ngay | Bị ngắt và loại khỏi pool | Có thể nhận exception; transaction chưa commit bị rollback |
| Service UP | Pool có thể tạo connection mới | Connection hiện hữu không cần đóng chỉ vì UP | Request tiếp tục trên connection đang hợp lệ |

### 3.1 Vì sao planned outage có thể không gây lỗi cho request?

Ứng dụng chỉ mượn connection trong thời gian thực hiện một database request, sau đó trả connection về pool. Khi FAN báo planned DOWN, pool ngừng cấp connection thuộc instance sắp bảo trì, nhưng cho request hiện tại hoàn tất. Khi ứng dụng gọi close() trên logical connection, pool đóng physical connection bị đánh dấu drain thay vì đưa nó trở lại danh sách idle.

Nếu service đã được relocate sang instance khác, pool có thể cấp connection mới ở instance còn hoạt động cho request kế tiếp.

### 3.2 Vì sao unplanned outage vẫn tạo exception?

Khi instance hoặc node bất ngờ mất, session server-side không còn khả năng phục vụ request. Pool có thể loại connection stale nhanh chóng, nhưng không thể giả vờ rằng transaction đã chạy thành công. Ứng dụng cần nhận exception và xử lý trạng thái transaction.

Không được giả định FCF sẽ tự chạy lại toàn bộ câu SQL. FCF chỉ phát hiện, loại bỏ và quản lý connection; replay là trách nhiệm của Application Continuity hoặc logic ứng dụng.

### 3.3 Không tự rollback connection đã bị FCF đóng

Trong một số lỗi unplanned, database đã rollback local transaction khi session bị mất. Oracle khuyến nghị ứng dụng không cố gọi rollback trên connection đã đóng như một cách khôi phục. Thay vào đó:

1. Bỏ connection lỗi.
2. Lấy connection mới từ pool.
3. Xác định commit outcome nếu request có thể đã gửi COMMIT.
4. Retry request chỉ khi logic và trạng thái transaction cho phép.

## 4. Connection pool tham gia vào HA như thế nào?

Connection pool giữ một tập physical database connections và cấp logical connection handles cho các thread/request.

### 4.1 Vòng đời borrow/return

~~~text
Pool có connection idle
          |
          v
Ứng dụng gọi getConnection()
          |
          v
Pool borrow logical connection
          |
          v
Ứng dụng thực hiện database request
          |
          v
Ứng dụng gọi close()
          |
          v
Pool thu hồi logical handle
          |
          +--> physical connection hợp lệ: đưa về idle
          |
          +--> connection bị FAN đánh dấu drain: đóng và loại bỏ
          |
          v
Connection sẵn sàng cho request tiếp theo hoặc pool tạo connection thay thế
~~~

Trong JDBC pool, Connection.close() thường trả logical handle về pool; nó không nhất thiết đóng physical database session. Điều này cho phép pool tái sử dụng connection và xử lý drain tại ranh giới request.

### 4.2 Giữ connection quá lâu làm giảm khả năng drain

Nếu ứng dụng mượn connection rồi giữ qua nhiều thao tác không liên quan, user think time hoặc cả một phiên làm việc dài, pool không thể trả connection đó về trạng thái idle để drain. Planned maintenance phải chờ connection được trả về hoặc đến hết drain timeout.

Best practice:

- Mượn connection ngay trước khi cần thao tác database.
- Thực hiện một request/database unit of work.
- Commit/rollback đúng transaction boundary.
- Đóng logical connection ngay sau khi hoàn tất.
- Không lưu Connection trong biến singleton hoặc chia sẻ giữa nhiều thread.

### 4.3 Request boundary

Request boundary xác định điểm bắt đầu/kết thúc một request logic. Khi pool hoặc driver biết ranh giới này, database có thể chọn thời điểm an toàn để drain hoặc replay.

Trong UCP, việc lấy connection từ PoolDataSource bắt đầu sử dụng connection cho request; close() trả connection về pool. Với các framework/pool có API requestBegin/requestEnd, hãy dùng đúng lifecycle tương ứng.

## 5. Fast Connection Failover với Oracle UCP

UCP là connection pool Java của Oracle, có tích hợp FAN/FCF. Đây là lựa chọn được Oracle khuyến nghị cho Java workload cần tận dụng đầy đủ các khả năng FAN của RAC.

### 5.1 Điều kiện cơ bản

Theo hướng dẫn UCP 19c, FCF với RAC cần:

- Sử dụng Oracle Universal Connection Pool.
- Dùng service name để kết nối; không dùng SID/service identifier thay cho service name.
- Database có RAC từ 12.1 trở lên hoặc Data Guard được cấu hình phù hợp.
- ONS được cấu hình và sẵn sàng trên môi trường chạy JDBC.
- JVM có cấu hình oracle.ons.oraclehome trỏ tới ORACLE_HOME theo yêu cầu môi trường UCP.
- Driver/JAR và ONS components tương thích với nhau.

Nếu FAN event không được truyền đến client, FCF không thể failover connection theo sự kiện.

### 5.2 FCF bị tắt mặc định trong UCP 19c

Trong UCP 19c, FCF pool property bị tắt mặc định. Ứng dụng phải bật rõ:

~~~java
pds.setFastConnectionFailoverEnabled(true);
~~~

Có thể kiểm tra trạng thái qua:

~~~java
boolean enabled = pds.getFastConnectionFailoverEnabled();
~~~

Đối với các bản UCP/JDBC mới hơn, hành vi mặc định có thể khác. Oracle ghi nhận UCP và JDBC 23ai hoặc mới hơn tự bật FCF khi kết nối đến Oracle RAC trong cấu hình hỗ trợ. Không áp dụng giả định này cho ứng dụng UCP 19c; hãy kiểm tra phiên bản driver, pool và tài liệu release tương ứng.

### 5.3 Ví dụ cấu hình UCP

~~~java
import java.sql.Connection;
import java.sql.SQLException;

import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public class RacPoolExample {

    public static PoolDataSource createPool() throws SQLException {
        PoolDataSource pds =
            PoolDataSourceFactory.getPoolDataSource();

        pds.setConnectionPoolName("OrdersPool");
        pds.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );

        pds.setURL(
            "jdbc:oracle:thin:@//rac-scan.example.com:1521/orders_svc"
        );
        pds.setUser("APP_USER");
        pds.setPassword("read-from-secret-store");

        pds.setInitialPoolSize(5);
        pds.setMinPoolSize(5);
        pds.setMaxPoolSize(40);

        pds.setFastConnectionFailoverEnabled(true);

        return pds;
    }

    public static void runRequest(PoolDataSource pds)
            throws SQLException {
        try (Connection connection = pds.getConnection()) {
            // Thực hiện một request database ngắn.
            // Close trả logical connection về UCP.
        }
    }
}
~~~

Password trong ví dụ chỉ là placeholder. Production nên lấy credential từ secret manager hoặc wallet/credential provider phù hợp, không hard-code trong source code.

URL dùng service name orders_svc. Với RAC, nên dùng SCAN/service connect descriptor để listener phân phối connection đến các instance đang cung cấp service.

### 5.4 Cấu hình ONS từ xa

UCP có thể nhận ONS configuration bằng property:

~~~java
pds.setONSConfiguration(
    "nodes=racnode1.example.com:6200," +
    "racnode2.example.com:6200"
);
~~~

Nếu ONS yêu cầu SSL, cấu hình thêm wallet theo hướng dẫn môi trường:

~~~java
pds.setONSConfiguration(
    "nodes=racnode1.example.com:6200," +
    "racnode2.example.com:6200\n" +
    "walletfile=/secure/ons-wallet"
);
~~~

Remote ONS configuration là lựa chọn Oracle khuyến nghị cho UCP standalone clients. Host/port phải trùng với remote ONS endpoints do DBA cung cấp; không đoán port hoặc mở firewall tùy tiện.

Với một số tổ hợp UCP/RAC từ 12.1 trở lên và không dùng wallet/keystore, UCP có thể tự cấu hình ONS mà không cần gọi setONSConfiguration. Kiểm tra release và yêu cầu bảo mật của môi trường trước khi bỏ cấu hình tường minh.

### 5.5 ONS JAR và phiên bản thư viện

Với UCP/JDBC, classpath cần các thành phần phù hợp như:

- ojdbcXXX.jar: Oracle JDBC driver.
- ons.jar: Oracle Notification Service client.
- simplefan.jar: FAN client support.

Sử dụng các JAR cùng một bộ phiên bản tương thích. Không trộn driver từ một release với ONS/SimpleFAN từ release khác nếu chưa được Oracle xác nhận tương thích.

Trong các triển khai JDBC FAN với third-party pool, Oracle cũng yêu cầu simplefan.jar và ons.jar được đặt ở nơi pool có thể load cùng driver. Nếu một JAR bị thiếu hoặc không load được, FAN support có thể bị vô hiệu.

### 5.6 ONS remote configuration và client-side daemon

Có hai cách cấu hình ONS:

| Cách | Mô tả | Khi phù hợp |
|---|---|---|
| Remote configuration | UCP/JDBC client kết nối trực tiếp tới ONS endpoints được khai báo | Thường được Oracle khuyến nghị cho standalone Java clients |
| Client-side ONS daemon | Chạy ONS daemon trên middle tier và cấu hình ons.config | Môi trường application server/kiến trúc cần daemon cục bộ |

Remote configuration thường dùng danh sách nodes=host:port. Nếu sử dụng wallet, tất cả ONS peers liên quan phải được cấu hình SSL/certificate phù hợp.

### 5.7 PlannedDrainingPeriod

UCP hỗ trợ system property:

~~~text
oracle.ucp.PlannedDrainingPeriod
~~~

Property này nhận số giây làm khoảng thời gian grace để UCP từ từ drain các connection borrowed bị ảnh hưởng bởi planned shutdown. Việc drain bắt đầu khi cùng service đã sẵn sàng trên instance khác.

Nếu không đặt property hoặc đặt bằng 0, UCP đóng connection bị ảnh hưởng khi connection được trả về pool. Khi đặt grace period, pool có thể phân tán việc loại bỏ connection trong khoảng thời gian cấu hình, giúp tránh logon storm và đột biến tải lên các instance còn lại.

Ví dụ JVM:

~~~bash
java -Doracle.ucp.PlannedDrainingPeriod=120 -jar orders-service.jar
~~~

Giá trị 120 giây chỉ là ví dụ. Chọn drain period dựa trên thời gian request thực tế và service drain timeout; property này không thay thế cấu hình server-side drain.

## 6. FAN với third-party connection pool

Từ Oracle JDBC 12.2.0.1, JDBC driver hỗ trợ FAN events cho planned và unplanned outages. Nhờ đó, các Java application dùng third-party pool không nhất thiết phải chuyển toàn bộ sang UCP để nhận một số lợi ích FAN.

Tuy nhiên, Oracle UCP cung cấp tích hợp FAN đầy đủ hơn. Với third-party pool, phải xác nhận pool có cơ chế kiểm tra connection khi borrow/return và biết loại bỏ connection khi driver phát hiện connection đã đóng.

### 6.1 Các điều kiện chính

- Dùng Oracle JDBC driver hỗ trợ FAN events, từ 12.2.0.1 trở lên.
- Có simplefan.jar và ons.jar cùng bộ phiên bản tương thích.
- Dùng OracleDataSource hoặc OracleDriver làm connection factory theo hướng dẫn Oracle.
- Pool có khả năng validate connection khi checkout hoặc check-in.
- Cấu hình ONS để client nhận được FAN notifications.
- Dùng service name và cấu hình connect descriptor phù hợp với RAC.

### 6.2 Safe-draining APIs

Với planned maintenance, JDBC driver cần một điểm an toàn để biết connection có thể được đóng mà không làm gián đoạn thao tác đang chạy. Các API được JDBC FAN hỗ trợ gồm:

- java.sql.Connection.isValid(int timeout)
- oracle.jdbc.OracleConnection.pingDatabase()
- oracle.jdbc.OracleConnection.pingDatabase(int timeout)
- oracle.jdbc.OracleConnection.endRequest()
- Các lệnh EXECUTE*** trên Statement, PreparedStatement và CallableStatement nếu câu SQL kiểm tra có hint CLIENT_CONNECTION_VALIDATION đúng vị trí.

Ví dụ connection validation SQL:

~~~sql
/*+ CLIENT_CONNECTION_VALIDATION */ SELECT 1 FROM DUAL
~~~

Hint phải là token đầu tiên sau phần comment trong SQL string theo yêu cầu JDBC FAN. Pool bên thứ ba thường gọi API/SQL validation tại thời điểm borrow hoặc return. Khi driver phát hiện connection không còn hợp lệ, pool phải đóng và loại connection đó.

Không dùng connection test của một session để kết luận toàn instance đã hỏng. Kết quả validation chỉ nói về connection được kiểm tra.

### 6.3 Ví dụ cấu hình theo loại pool

Tên property phụ thuộc sản phẩm và phiên bản. Oracle JDBC Developer's Guide liệt kê một số cấu hình:

| Pool | Ví dụ tùy chọn validation |
|---|---|
| WebLogic Generic/MDS data source | TestConnectionsOnReserve, TestConnectionsOnRelease, TestConnectionsOnCreate |
| IBM WebSphere | PreTest Connection |
| JBoss | check-valid-connection-sql |
| Apache Tomcat | testOnBorrow, testOnReturn |

Đây là tên tùy chọn theo từng sản phẩm; cần đọc tài liệu đúng version. Không copy một property của pool này sang pool khác.

### 6.4 UCP hay third-party pool?

| Tiêu chí | UCP | Third-party pool + JDBC FAN |
|---|---|---|
| Tích hợp FAN/FCF | Tích hợp trực tiếp | Phụ thuộc JDBC driver và pool validation |
| Planned draining | Có cơ chế pool drain và grace period | Cần safe-draining API/validation và cấu hình pool |
| Runtime Load Balancing | Có tích hợp RLB | Phụ thuộc khả năng của pool/client |
| Quản lý connection | Oracle quản lý toàn lifecycle | Pool vendor quản lý lifecycle |
| Cấu hình | UCP properties và ONS | Driver/JAR/ONS và property riêng của pool |

Nếu ứng dụng Java cần tích hợp RAC HA sâu và chưa bị ràng buộc bởi một pool cụ thể, UCP là lựa chọn tự nhiên. Nếu phải giữ third-party pool, kiểm tra đầy đủ FAN support, driver version, validation point và planned-draining behavior trước khi đưa vào production.

## 7. Cấu hình Oracle RAC service cho FAN và load balancing

FAN gắn với service, nên ứng dụng nên kết nối qua một service được quản trị rõ ràng thay vì dùng default database service hoặc SID cố định.

### 7.1 Service name

Service name đại diện cho workload. DBA có thể cấu hình service trên một hoặc nhiều instance, đặt preferred/available instances, notification và load balancing goals.

Khi một service bị relocate, FAN thông báo cho pool connection nào bị ảnh hưởng. Nếu ứng dụng kết nối thẳng đến một SID hoặc endpoint instance cố định, khả năng phân phối và failover theo service sẽ bị hạn chế.

### 7.2 Bật FAN notification và load balancing goals

Ví dụ cấu hình service trên RAC:

~~~bash
srvctl modify service -db salesdb \
  -service orders_svc \
  -notification TRUE \
  -clbgoal SHORT \
  -rlbgoal SERVICE_TIME
~~~

Các tham số:

- notification TRUE: bật FAN notifications cho service.
- clbgoal SHORT: phù hợp với workload request ngắn và runtime load balancing/integrated connection pool.
- rlbgoal SERVICE_TIME: advisory phân phối connection theo response time.

Nếu workload cần tối ưu throughput, có thể dùng rlbgoal THROUGHPUT. Với batch connections dài hạn cần cân bằng theo số lượng session, CLB goal LONG có thể phù hợp hơn. Chọn goal dựa trên đặc tính workload, không bật một cấu hình giống nhau cho mọi service.

### 7.3 Planned service stop hoặc relocate

Khi bảo trì một instance, ưu tiên relocate/stop service theo quy trình có drain:

~~~bash
srvctl relocate service -db salesdb \
  -service orders_svc \
  -oldinst sales1 \
  -newinst sales2 \
  -drain_timeout 300 \
  -stopoption TRANSACTIONAL
~~~

Hoặc stop service:

~~~bash
srvctl stop service -db salesdb \
  -service orders_svc \
  -drain_timeout 300 \
  -stopoption TRANSACTIONAL
~~~

Đây là ví dụ cho môi trường RAC và cú pháp có thể khác theo release/option đang dùng. Xác nhận bằng srvctl help và runbook của cluster trước khi thực hiện.

### 7.4 DRAIN_TIMEOUT và STOP_OPTION

Hai thuộc tính điều khiển planned maintenance:

| Thuộc tính | Ý nghĩa |
|---|---|
| DRAIN_TIMEOUT | Số giây cho phép request/session được drain trước khi áp dụng stop option |
| STOP_OPTION | Cách xử lý session còn lại sau drain timeout |

Đối với service, các stop option thường dùng là TRANSACTIONAL hoặc IMMEDIATE:

- TRANSACTIONAL: chờ transaction hiện tại hoàn tất trước khi kết thúc session theo semantics của service stop.
- IMMEDIATE: kết thúc session còn lại ngay sau khi hết thời gian drain.

Chọn drain timeout dựa trên phân bố thời gian request, không chỉ dựa vào một con số cố định. Nếu timeout quá ngắn, request dài bị ngắt; nếu quá dài, bảo trì bị kéo dài.

### 7.5 Service UP sau bảo trì

Sau khi instance/service khởi động lại, FAN UP event thông báo pool có thể tạo connection mới đến instance. Pool dần đưa connection về các instance sẵn sàng theo load balancing advisory.

Không cần restart toàn bộ application server chỉ để làm mới pool nếu FAN/FCF được cấu hình và hoạt động đúng.

## 8. Runtime Load Balancing và Connection Load Balancing

FAN/FCF còn hỗ trợ phân phối workload đến instance phù hợp.

### 8.1 Connection Load Balancing

CLB được thực hiện khi client tạo connection mới. Listener phân phối connection dựa trên service goal và trạng thái instance. Với pool tích hợp, CLB goal SHORT thường được dùng cho request ngắn và workload có nhiều lần borrow/return.

### 8.2 Runtime Load Balancing

RLB sử dụng Load Balancing Advisory events được gửi định kỳ. Pool nhận khuyến nghị từ database về instance phù hợp để phục vụ request tiếp theo.

Hai service goals thường gặp:

| RLB goal | Mục tiêu | Ví dụ workload |
|---|---|---|
| SERVICE_TIME | Cân bằng theo response time và khả năng phục vụ | OLTP, web shopping, request tương tác |
| THROUGHPUT | Cân bằng theo throughput | Batch hoặc workload xử lý lượng lớn |

### 8.3 Connection affinity

Connection affinity giữ các request liên quan trên cùng instance khi điều đó có lợi, ví dụ workload cần locality với cache hoặc state của service. Affinity phải được dùng đúng semantics; không nên ép affinity nếu nó làm lệch tải hoặc giữ session quá lâu.

Trong UCP, FCF phải được bật để sử dụng runtime connection load balancing và connection affinity theo hướng dẫn 19c.

### 8.4 Xem service goal

~~~sql
SELECT name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notification
FROM v$services
ORDER BY name;
~~~

Trong RAC, dùng GV$SERVICES nếu cần xem service theo instance và giữ INST_ID. Một số cột hoặc cách hiển thị có thể khác theo release.

## 9. FCF, TAF, Application Continuity và Transaction Guard

Các tính năng này bổ sung nhau nhưng giải quyết vấn đề khác nhau.

| Tính năng | Phạm vi | Hành vi |
|---|---|---|
| FAN | Notification | Báo trạng thái service/instance/node và load advisory |
| FCF | Connection pool | Phát hiện, loại bỏ hoặc drain connection bị ảnh hưởng |
| TAF | Session failover cho một số client/operation | Có thể reconnect session và hỗ trợ SELECT failover theo cấu hình; không replay transaction tổng quát |
| Application Continuity | Request/session replay | Rebuild session và replay các lời gọi database đủ điều kiện sau recoverable outage |
| Transparent Application Continuity | Replay được tích hợp và cấu hình ở service/client | Tự động hóa replay cho request đủ điều kiện |
| Transaction Guard | Commit outcome | Xác định transaction cuối đã commit hay chưa để tránh xử lý lặp |

### 9.1 FCF không phải transaction replay

FCF có thể đóng connection hỏng và làm ứng dụng nhận exception nhanh. Nhưng nó không tự biết toàn bộ logic nghiệp vụ để quyết định có thể chạy lại request hay không.

Ví dụ ứng dụng thực hiện:

1. INSERT một đơn hàng.
2. UPDATE tồn kho.
3. COMMIT.
4. Mất kết nối trước khi client nhận phản hồi commit.

Ứng dụng không thể chỉ nhìn exception rồi gửi lại cả transaction. Có thể transaction đã commit thành công nhưng phản hồi bị mất; gửi lại sẽ tạo đơn hàng trùng.

### 9.2 Transaction Guard

Transaction Guard dùng Logical Transaction ID (LTXID) để xác định outcome của transaction cuối cùng trên session bị lỗi. Ứng dụng có thể biết transaction đã commit hay chưa và quyết định retry an toàn.

Transaction Guard phù hợp khi ứng dụng tự quản lý retry và cần bảo đảm idempotence. Application Continuity sử dụng Transaction Guard để hỗ trợ replay an toàn.

### 9.3 Application Continuity

Application Continuity có thể:

- Tạo connection/session mới sau recoverable outage.
- Kiểm tra commit outcome bằng Transaction Guard.
- Khôi phục session state theo cấu hình.
- Replay các lời gọi database đủ điều kiện.
- Trả kết quả về ứng dụng như một request được tiếp tục sau độ trễ.

Replay có giới hạn. Các thao tác có side effects ngoài database, phụ thuộc thời gian bên ngoài, gửi email, gọi HTTP hoặc đồng bộ session độc lập có thể cần xử lý riêng. Không phải mọi request đều có thể replay an toàn.

### 9.4 Khi nào cần kết hợp?

- Chỉ cần loại bỏ connection stale và retry do ứng dụng quản lý: FAN + FCF.
- Cần drain kết nối khi rolling maintenance: FAN + FCF + pool request boundaries + service drain timeout.
- Cần tự động replay request đủ điều kiện: FAN/FCF kết hợp Application Continuity/TAC.
- Cần biết transaction đã commit hay chưa khi tự viết retry: Transaction Guard.

## 10. Quản lý connection lifecycle trong ứng dụng

FCF hoạt động tốt nhất khi ứng dụng có connection lifecycle ngắn và rõ ràng.

### 10.1 Dùng try-with-resources

~~~java
public Order findOrder(PoolDataSource pool, long orderId)
        throws SQLException {
    String sql =
        "SELECT order_id, status " +
        "FROM orders WHERE order_id = ?";

    try (Connection connection = pool.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return null;
            }

            return new Order(
                rs.getLong("order_id"),
                rs.getString("status")
            );
        }
    }
}
~~~

Connection.close() trả logical connection về pool. Statement và ResultSet cũng được đóng, tránh giữ resource qua request boundary.

### 10.2 Không chia sẻ connection giữa threads

Một JDBC Connection không nên được dùng đồng thời bởi nhiều thread độc lập. Mỗi request/thread nên mượn connection riêng từ pool và trả về sau khi xong.

### 10.3 Không giữ transaction qua thời gian chờ người dùng

Không mở transaction khi hiển thị form cho người dùng rồi giữ connection trong lúc người dùng suy nghĩ. Hãy hoàn thành database unit of work, commit/rollback và trả connection về pool.

### 10.4 Quản lý session state

Ứng dụng có thể đặt NLS, schema, client identifier, package state hoặc application context trên session. Khi connection được tái sử dụng cho request khác, phải bảo đảm session state được reset hoặc khôi phục đúng.

FCF chỉ quản lý connection; nó không tự hiểu trạng thái nghiệp vụ hoặc mọi biến session tùy chỉnh của ứng dụng. Với Application Continuity, session state cần được cấu hình để có thể restore/replay theo yêu cầu.

## 11. Giám sát FAN, service và connection pool

FCF cần được giám sát ở cả phía database, ONS và application pool. Chỉ thấy application vẫn trả lời request không đủ để chứng minh FAN/FCF đang hoạt động đúng; cần kiểm tra event delivery và pool behavior.

### 11.1 Kiểm tra service trên database

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notifications
FROM gv$services
ORDER BY inst_id, name;
~~~

Các cột hiển thị service, network name, runtime load balancing goal, connection load balancing goal và HA notification setting. Tên/cột cụ thể phụ thuộc release và quyền truy cập.

### 11.2 Xem session theo service và instance

~~~sql
SELECT inst_id,
       service_name,
       status,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name, status
ORDER BY service_name, inst_id, status;
~~~

Query này giúp quan sát session của service phân bố trên các instance. Sau planned relocation, số session của service trên instance đang bảo trì nên giảm theo quá trình drain; các instance còn lại tiếp nhận kết nối mới.

### 11.3 Xem client, module và pool

~~~sql
SELECT inst_id,
       service_name,
       machine,
       program,
       module,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name, machine, program, module
ORDER BY service_name, inst_id, session_count DESC;
~~~

MODULE, PROGRAM và MACHINE giúp phân biệt connection từ từng application server/pool. Ứng dụng nên đặt MODULE/ACTION và CLIENT_IDENTIFIER phù hợp để DBA nhận diện workload.

### 11.4 Kiểm tra trạng thái service bằng SRVCTL

~~~bash
srvctl status service -db salesdb -service orders_svc
srvctl config service -db salesdb -service orders_svc
~~~

STATUS cho biết service đang chạy trên instance nào. CONFIG giúp xác nhận notification, preferred/available instances, CLB/RLB goals và các thuộc tính service đã cấu hình.

### 11.5 Kiểm tra ONS phía client

Với client-side ONS daemon, dùng onsctl theo ORACLE_HOME của client:

~~~bash
onsctl ping
onsctl detailed
~~~

Ping xác nhận daemon đang chạy; detailed hiển thị trạng thái kết nối/topology. Với remote ONS, kiểm tra log client và khả năng kết nối tới host/port remote đã cấu hình.

Các file log ONS có thể cho biết lỗi SSL wallet, authentication, host resolution, firewall hoặc event delivery. Bảo vệ log vì nó có thể chứa thông tin hạ tầng.

### 11.6 Giám sát connection pool

Theo dõi các metric do pool cung cấp, ví dụ:

- Tổng số physical connections.
- Số available/idle connections.
- Số borrowed/in-use connections.
- Số connection bị đóng hoặc bị loại khỏi pool.
- Số connection được tạo mới sau FAN UP.
- Borrow wait time, timeout và pool exhaustion.
- Số lần validation thất bại.
- Số lần connection creation/reconnect.

Trong UCP, có thể dùng pool statistics/JMX hoặc API quản trị tương ứng với version. Với third-party pool, dùng metric và MBean của sản phẩm đó. Không chỉ đo số connection đang mở; cần đo cả tốc độ borrow/return và connection churn.

## 12. Quy trình kiểm thử FAN/FCF

Kiểm thử phải được thực hiện trong môi trường staging hoặc môi trường RAC được dành riêng cho HA test. Không tự ý stop/kill instance production để xác nhận FCF.

### 12.1 Kiểm tra trước khi test

1. Xác nhận service name và instance placement.
2. Xác nhận ONS nodes, ports, wallet và network route.
3. Xác nhận driver, UCP, ONS và SimpleFAN JAR tương thích.
4. Xác nhận FCF được bật.
5. Xác nhận pool trả connection về sau mỗi request.
6. Xác nhận ứng dụng xử lý exception/retry đúng semantics.
7. Ghi baseline session count, pool metrics và request latency.

### 12.2 Test planned relocation

1. Chạy workload có request ngắn và request dài.
2. Xác nhận connection được phân bổ trên service.
3. Dùng SRVCTL relocate service sang instance khác với drain timeout phù hợp.
4. Theo dõi FAN planned DOWN, pool idle cleanup và borrowed connection drain.
5. Xác nhận request đang chạy có cơ hội hoàn tất.
6. Xác nhận connection trả về pool bị đóng nếu gắn với instance cũ.
7. Xác nhận request mới được cấp connection đến instance đích.
8. Đưa service về cấu hình ban đầu và quan sát FAN UP/rebalance.

Tiêu chí thành công: không có request lỗi ngoài dự kiến trong thời gian drain, pool ngừng cấp connection mới đến instance đang rút service, và các request sau đó chạy trên instance còn phục vụ.

### 12.3 Test unplanned outage

Trong staging, mô phỏng instance/node/service failure theo runbook HA:

1. Có workload đang giữ connection idle và borrowed.
2. Gây outage ngoài kế hoạch cho instance/service được chọn.
3. Xác nhận FAN DOWN được gửi tới client.
4. Xác nhận pool ngắt và loại stale connections.
5. Xác nhận request đang chạy nhận exception theo thiết kế.
6. Xác nhận ứng dụng lấy connection mới và retry chỉ khi an toàn.
7. Xác nhận transaction chưa commit không bị áp dụng một phần.
8. Khôi phục instance/service và quan sát FAN UP.

Tiêu chí thành công không phải “không bao giờ có exception”. Với unplanned outage, exception trên request đang chạy là hành vi có thể xảy ra. Tiêu chí là connection stale bị loại nhanh, pool phục hồi và ứng dụng xử lý transaction đúng.

### 12.4 Test commit outcome

Tạo test case trong đó kết nối bị mất quanh thời điểm COMMIT. Kiểm tra ứng dụng không gửi lại transaction một cách mù quáng. Nếu yêu cầu exactly-once transaction outcome, kiểm thử Transaction Guard hoặc Application Continuity theo cấu hình service.

### 12.5 Test scale-out và service UP

Thêm hoặc khởi động instance mới cung cấp service. Xác nhận:

- FAN UP được nhận.
- Pool tạo connection mới đến instance mới.
- RLB phân phối request theo service goal.
- Pool không tạo connection dồn dập làm quá tải instance vừa khởi động.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pool vẫn giữ connection chết sau node failure | FCF tắt, ONS không kết nối hoặc FAN event không tới client | Kiểm tra UCP property, ONS topology, firewall, JAR và service notification |
| FCF không hoạt động dù code đã bật | Dùng SID thay service name, database/client không đáp ứng prerequisites hoặc ONS không sẵn sàng | Dùng service name và xác nhận đúng release/HA topology |
| UCP không nhận FAN event | Thiếu ons.jar/simplefan.jar hoặc version mismatch | Dùng bộ JAR tương thích và kiểm tra classpath |
| Planned maintenance vẫn làm request lỗi | Pool không trả connection ở request boundary, safe-draining API không chạy hoặc DBA dùng force stop | Sửa lifecycle, validation/drain configuration và stop procedure |
| Request dài bị ngắt trong planned outage | Drain timeout quá ngắn hoặc stop option kết thúc session sau timeout | Đo request duration và tăng drain interval phù hợp |
| Connection mới không được tạo ở instance còn lại | Service không chạy ở instance đích, connect descriptor sai hoặc pool chưa nhận UP | Kiểm tra SRVCTL status, service name và ONS |
| Sau khi node trở lại, pool không phân phối lại | FAN UP/RLB chưa được bật hoặc service goal không phù hợp | Kiểm tra notification, CLB/RLB goals và FCF |
| ORA-17008 Closed Connection xuất hiện | Connection bị đóng do unplanned outage hoặc pool validation phát hiện stale connection | Bỏ connection lỗi, lấy connection mới và xử lý retry |
| Transaction bị thực hiện hai lần sau retry | Ứng dụng retry mù khi chưa biết commit outcome | Dùng Transaction Guard/AC hoặc thiết kế idempotency key |
| Pool tạo logon storm sau relocation | Tất cả connection bị tạo lại cùng lúc hoặc pool không drain dần | Dùng planned draining period, drain timeout và giới hạn pool hợp lý |
| ONS SSL/authentication lỗi | Wallet/certificate không khớp giữa client và cluster | Đồng bộ trust/wallet theo runbook bảo mật |
| Third-party pool không drain connection borrowed | Pool không gọi safe-draining API hoặc validation ở sai thời điểm | Cấu hình pool validation và JDBC FAN integration |
| Connection validation làm tăng latency | Test SQL quá thường xuyên hoặc timeout quá dài | Chọn validation policy theo pool và dùng FAN để xử lý event thay polling quá dày |

## 14. Lỗi thiết kế ứng dụng làm giảm hiệu quả FCF

### 14.1 Giữ connection trong object sống lâu

Nếu service class giữ Connection trong field suốt vòng đời object, pool không thể drain connection ở request boundary. Connection nên được borrow trong scope của database operation và đóng ngay khi xong.

### 14.2 Dùng một pool cho nhiều service không tương đương

Pool gắn với URL/service và cấu hình HA cụ thể. Không nên dùng chung một pool cho các workload có service policy, credential, tenant hoặc availability requirement khác nhau nếu không có thiết kế rõ ràng.

### 14.3 Kết nối bằng SID hoặc instance host cố định

Kết nối cố định đến một instance bỏ qua service-level placement, service relocation và runtime load balancing. Dùng service name phù hợp với workload.

### 14.4 Retry mọi SQLException

Không phải mọi SQLException đều do outage. Lỗi constraint, dữ liệu không hợp lệ, deadlock hoặc lỗi nghiệp vụ không nên bị retry tự động như connection failure.

Retry phải:

- Phân loại recoverable connection errors.
- Có giới hạn số lần và backoff.
- Lấy connection mới.
- Không lặp transaction đã commit.
- Bảo đảm request idempotent hoặc dùng Transaction Guard/AC khi cần.

### 14.5 Pool quá lớn

Pool size lớn không tự làm ứng dụng HA hơn. Nhiều physical connections có thể làm tăng session count, memory, CPU scheduling và logon storm sau failover. Chọn min/max pool size theo concurrency thực tế và capacity của các instance còn lại khi một node bị rút.

### 14.6 Không dự trù capacity khi mất một node

Nếu RAC có N instances nhưng workload chỉ chạy được khi tất cả cùng hoạt động, failover sẽ làm instance còn lại quá tải. Capacity planning phải bảo đảm các instance còn lại chịu được tải khi một hoặc nhiều instance unavailable.

## 15. Lưu ý phiên bản và loại client

### 15.1 UCP 19c

- FCF bị tắt mặc định; bật bằng setFastConnectionFailoverEnabled(true).
- ONS cần được cấu hình và có thể dùng remote configuration.
- UCP hỗ trợ PlannedDrainingPeriod từ 12.1.0.2.
- Cần service name và topology RAC/Data Guard phù hợp.

### 15.2 JDBC 12.2 trở lên với third-party pool

- Oracle JDBC hỗ trợ FAN events cho planned/unplanned outages từ 12.2.0.1.
- Cần simplefan.jar và ons.jar.
- Planned draining cần safe-draining APIs và pool connection validation.
- UCP vẫn có tích hợp FAN toàn diện hơn.

### 15.3 UCP/JDBC 23ai trở lên

Tài liệu Oracle HA hiện hành ghi nhận UCP và JDBC 23ai trở lên tự bật FCF khi kết nối đến Oracle RAC trong cấu hình được hỗ trợ. Hãy xác nhận driver, pool và server version thực tế; không suy ra behavior của UCP 19c từ mặc định mới hơn.

### 15.4 Các loại client khác

Oracle có FAN/FCF integration cho nhiều loại client và pool, gồm OCI Session Pool, ODP.NET, Tuxedo, WebLogic Active GridLink, Python và Node.js drivers. Cách cấu hình, notification transport và pool properties khác nhau theo client. Không áp dụng Java ONS/JAR configuration cho OCI hoặc ODP.NET.

Với mỗi client, kiểm tra tài liệu Developer's Guide đúng phiên bản và xác nhận:

- FAN notification mechanism được hỗ trợ.
- Client có đăng ký nhận event hay không.
- Pool xử lý idle và borrowed connections thế nào.
- Planned draining có được hỗ trợ không.
- Retry, transaction outcome và request replay được giải quyết bởi tính năng nào.

## 16. Checklist triển khai FAN/FCF

### Database và service

1. Ứng dụng có dùng user-defined service name không?
2. Service có chạy trên nhiều instance hoặc có target failover phù hợp không?
3. FAN notification đã được bật cho service chưa?
4. CLB goal và RLB goal có phù hợp workload không?
5. Service có drain timeout và stop option phù hợp planned maintenance không?
6. Capacity còn lại có đủ khi một instance bị rút không?

### Client và connection pool

1. Driver, UCP, ONS và SimpleFAN JAR có cùng bộ version tương thích không?
2. FCF có được bật theo đúng release không?
3. ONS remote/local configuration có chính xác không?
4. Firewall, routing, DNS và wallet/certificate đã được kiểm tra chưa?
5. Pool có thể validate và loại stale connection không?
6. Ứng dụng có trả connection về pool sau mỗi request không?
7. Connection có bị giữ trong thread/object quá lâu không?
8. Pool size có phù hợp capacity của RAC không?

### Ứng dụng và recovery

1. Ứng dụng có phân biệt planned và unplanned outage không?
2. Có xử lý Closed Connection/SQLRecoverableException phù hợp không?
3. Có bỏ connection lỗi trước khi retry không?
4. Retry có idempotent và giới hạn số lần không?
5. Có Transaction Guard khi cần xác định commit outcome không?
6. Có Application Continuity/TAC nếu cần replay request không?
7. Session state có thể reset/restore khi connection được thay thế không?

### Kiểm thử và vận hành

1. Đã test planned service relocation chưa?
2. Đã test unplanned instance/node failure chưa?
3. Đã test service UP sau recovery chưa?
4. Đã test transaction đang COMMIT khi connection mất chưa?
5. Đã quan sát FAN/ONS logs và pool metrics chưa?
6. Đã xác nhận request latency và pool exhaustion trong failover chưa?
7. Có runbook rollback/restore service nếu relocation không thành công không?

## 17. Tổng kết

FAN và FCF phối hợp để connection pool phản ứng nhanh trước thay đổi của Oracle RAC/Data Guard:

- FAN phát thông báo UP/DOWN và load balancing advisory.
- ONS chuyển event đến client.
- FCF dùng event để loại connection stale, drain connection planned-down và tạo connection mới trên service instance còn khả dụng.
- Planned DOWN cho phép connection borrowed hoàn tất và được đóng tại check-in/safe point; unplanned DOWN có thể ngắt cả connection đang dùng và làm transaction chưa commit bị rollback.
- UCP cung cấp tích hợp FAN/FCF đầy đủ; third-party Java pool có thể dùng JDBC FAN từ 12.2 nếu có ONS/SimpleFAN và safe-draining/validation phù hợp.
- Ứng dụng cần trả connection về pool tại request boundary và không giữ connection lâu hơn thời gian database work.
- FCF không tự replay transaction. Application Continuity/Transparent Application Continuity phục hồi request đủ điều kiện; Transaction Guard giúp xác định commit outcome.
- Service name, ONS connectivity, driver/pool version, drain timeout, pool capacity và retry semantics đều là phần của một thiết kế HA hoàn chỉnh.

Một triển khai FCF chỉ đáng tin cậy khi đã kiểm thử cả planned maintenance lẫn unplanned outage. Hãy quan sát đồng thời FAN event, trạng thái service, pool metrics và kết quả transaction để chứng minh ứng dụng có thể tiếp tục phục vụ mà không tạo duplicate work hoặc làm quá tải các instance còn lại.

## 18. Tài liệu Oracle tham khảo

- Oracle Database 19c Universal Connection Pool Developer's Guide, “About Fast Connection Failover”: https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/fast-connection-failover.html
- Oracle Database 19c JDBC Developer's Guide, “Oracle JDBC Support for FAN Events”: https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-support-Oracle-FAN.html
- Oracle Database 19c High Availability Overview and Best Practices, “Configuring Level 2: Prepare Applications for Planned Maintenance”: https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/configuring-level-2-prepare-applications-planned-maintenance.html
- Oracle Database 19c Real Application Clusters Administration and Deployment Guide, “Ensuring Application Continuity”: https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html
- Oracle Database 19c Real Application Clusters Administration and Deployment Guide, “Workload Management with Dynamic Database Services”: https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/workload-management-with-dynamic-database-services.html
- Oracle Database 19c Server Control Utility Reference, “srvctl service options”: https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/server-control-utility-reference.html
- Oracle Database 19c SQL Processing for Application Developers, “Transaction Guard”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html
- Oracle Database 26ai Real Application Clusters Administration and Deployment Guide, “Managing Planned Maintenance”: https://docs.oracle.com/en/database/oracle/oracle-database/26/racad/ensuring-application-continuity/managing-planned-maintenance.html
