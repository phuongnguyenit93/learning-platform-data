# Kích thước pool, thời gian sống kết nối và giới hạn session phía Oracle

Trong ứng dụng Spring Boot dùng JPA/Hibernate để truy cập Oracle Database, connection pool quyết định số kết nối JDBC vật lý mà mỗi instance ứng dụng có thể giữ và tái sử dụng. Mỗi kết nối vật lý thường tương ứng với một database session Oracle. Vì vậy, cấu hình pool ảnh hưởng trực tiếp đến số session, số server process, khả năng tiếp nhận request và mức độ cạnh tranh tài nguyên trong database.

Ba quyết định cần phối hợp là:

- **Kích thước pool**: số kết nối tối đa và số kết nối nhàn rỗi tối thiểu mà ứng dụng duy trì.
- **Vòng đời kết nối**: khi nào pool loại bỏ và tạo lại một kết nối để tránh dùng connection quá cũ hoặc đã bị tầng mạng/database ngắt.
- **Giới hạn phía Oracle**: số session/process database có thể phục vụ, cùng các giới hạn theo user, profile, service và instance.

Tăng maximum pool size không mặc nhiên làm ứng dụng nhanh hơn. Nếu database đã bão hòa CPU, I/O hoặc lock, nhiều session hơn có thể làm thời gian chờ tăng. Ngược lại, pool quá nhỏ có thể khiến request xếp hàng ở ứng dụng dù database còn năng lực. Thiết kế đúng phải dựa trên tổng số pool của toàn hệ thống, thời gian giữ connection, tải thực tế và headroom mà DBA dành cho ứng dụng.

## 1. Connection pool hoạt động như thế nào?

Mở một JDBC connection vật lý tới Oracle có chi phí: thiết lập network, xác thực, tạo session, khởi tạo trạng thái session và các bước liên quan. Nếu mỗi HTTP request đều mở rồi đóng một kết nối vật lý, hệ thống sẽ tạo nhiều session ngắn hạn, tốn tài nguyên và dễ tạo tải đăng nhập đột biến.

Connection pool giữ sẵn một số physical connection. Khi cần truy cập database, ứng dụng mượn một connection từ pool, thực hiện SQL/transaction rồi trả connection về pool. Lệnh close trên connection do pool quản lý thường trả connection về pool; nó không nhất thiết đóng socket và database session ngay lập tức.

    HTTP request
         |
         v
    Spring Controller
         |
         v
    Service / @Transactional
         |
         v
    JPA / Hibernate
         |
         v
    DataSource connection pool
       +-----------------------+
       | Connection A  busy    |
       | Connection B  idle    |
       | Connection C  idle    |
       | Connection D  busy    |
       +-----------------------+
         |
         | physical JDBC connections
         v
    Oracle Database sessions

Một connection đang idle trong pool vẫn thường giữ một Oracle session. Do đó, số HTTP request hiện tại không bằng số session Oracle. Một ứng dụng có thể đang xử lý 5 request nhưng vẫn giữ 20 session do pool đã mở và duy trì 20 connection.

### 1.1. Logical connection và physical connection

Ứng dụng thường nhận một logical connection handle từ DataSource. Pool ánh xạ handle đó tới physical connection thực tế. Khi ứng dụng gọi close, pool thu hồi handle và đánh dấu physical connection có thể được tái sử dụng.

Phân biệt này giải thích vì sao:

- Connection.close() trong ứng dụng không nhất thiết đóng session Oracle.
- Connection đang idle trong pool vẫn tiêu thụ session/process theo mô hình server của database.
- Một connection bị hỏng ở network có thể vẫn nằm trong pool cho đến khi được phát hiện và loại bỏ.
- Cấu hình pool có thể làm số session tồn tại lâu hơn vòng đời của một HTTP request.

Với Oracle dedicated server, một user session thường được phục vụ bởi một dedicated server process. Với shared server, nhiều session có thể chia sẻ một nhóm server process nên quan hệ session/process khác đi. Dù vậy, session vẫn tiêu thụ slot trong giới hạn SESSIONS.

### 1.2. Pool không phải thread pool

Thread pool giới hạn số thread thực thi công việc Java; connection pool giới hạn số kết nối database đồng thời. Hai con số này không cần bằng nhau.

Một request có thể xử lý validation, gọi dịch vụ khác hoặc serialize JSON mà không giữ connection. Ngược lại, một transaction có thể giữ connection trong suốt nhiều bước service. Nếu connection bị giữ trong lúc chờ HTTP hoặc xử lý không liên quan database, pool có thể cạn dù SQL thực tế rất ít.

Mục tiêu là giữ thời gian mượn connection ngắn và có thể dự đoán. Không giữ transaction mở trong lúc chờ người dùng, gọi API bên ngoài hoặc thực hiện công việc chậm không cần database.

## 2. HikariCP trong Spring Boot

Spring Boot thường tự cấu hình HikariCP làm connection pool nếu HikariCP có trên classpath và không có DataSource khác được cấu hình. HikariCP triển khai JDBC DataSource, quản lý connection, kiểm tra trạng thái và thu hồi connection theo các tham số pool.

Ví dụ cấu hình trong application.yml:

    spring:
      datasource:
        url: jdbc:oracle:thin:@//db-host:1521/appservice
        username: app_user
        password: DB_PASSWORD_FROM_SECRET_STORE
        hikari:
          pool-name: order-db-pool
          maximum-pool-size: 20
          minimum-idle: 5
          connection-timeout: 30000
          validation-timeout: 5000
          idle-timeout: 600000
          max-lifetime: 1800000
          keepalive-time: 300000
          leak-detection-threshold: 0

Các giá trị trên chỉ minh họa cách cấu hình. Chúng không phải khuyến nghị mặc định cho mọi hệ thống. Đơn vị của các tham số thời gian HikariCP là millisecond. Hãy tính pool size từ capacity database và đo tải trước khi áp dụng vào production.

### 2.1. maximumPoolSize

maximumPoolSize là số connection tối đa mà một HikariCP pool có thể quản lý, bao gồm connection đang được mượn và connection đang idle.

Khi số connection đang được sử dụng đạt giới hạn và không có connection rảnh, thread gọi getConnection() phải chờ. Nếu không lấy được connection trong connectionTimeout, HikariCP ném lỗi timeout lấy connection.

Tham số này là giới hạn concurrency tới database của một pool. Nếu một application instance có hai DataSource, mỗi DataSource có pool riêng và mỗi pool có maximumPoolSize riêng.

Ví dụ:

    maximumPoolSize = 20

Một instance ứng dụng có thể giữ tối đa 20 physical connection từ pool này. Nếu chạy 5 replica, tổng mức tối đa từ pool đó là 100 connection, chưa tính các pool khác.

### 2.2. minimumIdle

minimumIdle là số connection nhàn rỗi tối thiểu mà pool cố gắng duy trì. Nếu không cấu hình, HikariCP thường dùng giá trị maximumPoolSize làm minimumIdle, tạo hành vi pool có kích thước cố định.

Giá trị minimumIdle thấp hơn maximumPoolSize cho phép pool co lại khi tải giảm và mở rộng khi tải tăng. Tuy nhiên, connection idle được giữ vẫn tương ứng với session Oracle. Vì vậy, minimumIdle là một phần của ngân sách session thường trực.

Ví dụ:

    minimumIdle = 5
    maximumPoolSize = 20

Pool cố gắng duy trì khoảng 5 connection idle khi tải thấp và có thể mở rộng đến 20 khi cần. Con số thực tế còn phụ thuộc workload, connection creation và trạng thái pool.

Nếu hệ thống có nhiều replica nhưng lưu lượng thấp, đặt minimumIdle quá cao có thể tạo hàng trăm session nhàn rỗi ở Oracle. Ngược lại, minimumIdle quá thấp có thể làm tăng chi phí mở kết nối khi có burst traffic. Hãy chọn theo latency mở connection, pattern tải và ngân sách session.

### 2.3. connectionTimeout

connectionTimeout là thời gian tối đa một thread chờ lấy connection từ pool trước khi nhận lỗi. Nó không phải query timeout và cũng không phải thời gian sống của physical connection.

Ví dụ connectionTimeout 30.000 ms nghĩa là request có thể chờ tối đa 30 giây để mượn connection. Nếu toàn bộ connection đang bận lâu hơn thời gian này, request sẽ timeout dù Oracle vẫn hoạt động.

Timeout quá dài làm thread bị giữ và hàng đợi request tăng. Timeout quá ngắn có thể tạo lỗi khi tải tăng đột biến trong thời gian ngắn. Cần đặt phù hợp với SLA HTTP và thời gian xử lý database.

### 2.4. validationTimeout

validationTimeout là thời gian tối đa dành cho việc xác thực connection. Nó phải nhỏ hơn connectionTimeout. Validation giúp pool phát hiện một số connection không còn sử dụng được trước khi giao cho ứng dụng.

Với JDBC driver hỗ trợ Connection.isValid() tốt, HikariCP thường có thể dùng cơ chế JDBC validation mà không cần connectionTestQuery. Chỉ cấu hình connectionTestQuery khi driver hoặc môi trường cụ thể yêu cầu và đã kiểm thử.

Không nên dùng một câu SELECT tốn kém làm health check. Validation cần nhẹ và có timeout rõ ràng.

### 2.5. idleTimeout

idleTimeout là thời gian một connection có thể nằm idle trước khi pool xem xét loại bỏ nó. Tham số này chỉ có tác dụng co pool khi minimumIdle nhỏ hơn maximumPoolSize. Với pool cố định có minimumIdle bằng maximumPoolSize, pool không loại bỏ connection chỉ vì idleTimeout.

Ví dụ:

    minimumIdle = 5
    maximumPoolSize = 20
    idleTimeout = 600000

Khi pool đang có nhiều hơn 5 connection và một số connection dư nằm idle đủ lâu, HikariCP có thể đóng chúng để giảm số session. Pool vẫn cố giữ tối thiểu số connection idle đã cấu hình.

idleTimeout không phải timeout cho transaction hay SQL. Nó không tự ngắt một connection đang được ứng dụng mượn và đang thực hiện công việc.

### 2.6. maxLifetime

maxLifetime là tuổi thọ tối đa của một physical connection trong pool. Khi connection đạt tuổi thọ này, HikariCP đánh dấu để thu hồi và tạo connection mới. Connection đang được mượn thường không bị cưỡng bức đóng ngay giữa transaction; việc loại bỏ diễn ra khi connection được trả về pool.

Mục đích là tránh giữ connection lâu hơn giới hạn mà database, proxy, firewall hoặc network đặt ra. Nếu tầng thấp hơn tự ngắt connection sau một thời gian nhất định, pool có thể loại bỏ connection trước ngưỡng đó để giảm khả năng giao một connection đã chết cho request.

Nên đặt maxLifetime thấp hơn giới hạn connection lifetime cứng ở tầng database/network nếu có. Đừng đặt bằng đúng ngưỡng vì có thể có sai số, độ trễ và khác biệt giữa các node. HikariCP có cơ chế giảm trừ nhỏ ngẫu nhiên để tránh nhiều connection bị thu hồi cùng lúc.

maxLifetime không giới hạn thời gian một SQL statement được chạy. Một transaction dài có thể tiếp tục giữ connection quá maxLifetime cho đến khi trả connection về pool. Cần cấu hình query/transaction timeout riêng.

### 2.7. keepaliveTime

keepaliveTime cho phép HikariCP kiểm tra connection đang idle theo chu kỳ để phát hiện hoặc giữ cho một số connection không bị tầng mạng ngắt do idle timeout. Keepalive chỉ áp dụng với connection idle trong pool, không chạy trên connection đang được ứng dụng mượn.

Giá trị keepaliveTime phải nhỏ hơn maxLifetime. Cần đặt thấp hơn idle timeout của network device nếu mục tiêu là giữ connection idle, nhưng phải tránh ping quá thường xuyên gây tải không cần thiết.

Keepalive không thay thế maxLifetime, validation, network monitoring hoặc xử lý connection lỗi. Nó cũng không bảo vệ connection đang bận khỏi query timeout hay database shutdown.

### 2.8. leakDetectionThreshold

leakDetectionThreshold bật cảnh báo khi một connection được mượn quá lâu mà chưa được trả về pool. HikariCP ghi log stack trace tại thời điểm mượn để giúp tìm nơi giữ connection.

Tham số này phục vụ chẩn đoán, không tự động đóng connection bị nghi ngờ leak. Một transaction hợp lệ chạy lâu hơn threshold cũng có thể tạo cảnh báo. Chỉ bật trong thời gian điều tra hoặc đặt ngưỡng cao hơn thời gian giữ connection hợp lý của hệ thống.

Luôn đóng JDBC resource bằng try-with-resources và để Spring transaction manager quản lý transaction trong JPA. Không giữ EntityManager/connection qua các tác vụ không liên quan database.

## 3. Tính kích thước pool theo tải thực tế

Không nên chọn maximumPoolSize theo số thread của Tomcat, số CPU của application pod hoặc số user đăng nhập. Một hệ thống có 500 request đồng thời không nhất thiết cần 500 connection Oracle; nhiều request có thể đang chờ network, cache, external service hoặc thực hiện logic Java.

Pool cần đủ connection để phục vụ concurrency database thực tế, đồng thời không làm database quá tải.

### 3.1. Bắt đầu từ ngân sách database

DBA cần xác định số session có thể dành cho ứng dụng sau khi trừ:

- Background session và process của Oracle.
- Kết nối DBA, monitoring và backup.
- Batch job và integration khác.
- Các ứng dụng cùng dùng database service.
- Headroom cho burst traffic, rolling deployment và sự cố failover.
- Giới hạn theo user/profile, service, PDB hoặc instance nếu có.

Không sử dụng toàn bộ SESSIONS làm ngân sách cho một application pool. SESSIONS là giới hạn ở cấp instance và còn phải phục vụ hoạt động database cùng client khác.

### 3.2. Cộng tất cả replica và DataSource

Công thức ngân sách connection tiềm năng:

    TotalPotentialConnections
      = sum(
          maxReplicas
          x poolsPerReplica
          x maximumPoolSizePerPool
        )
      + batchConnections
      + adminConnections
      + monitoringConnections
      + otherClientConnections

Ví dụ một hệ thống có:

| Thành phần | Replica tối đa | Pool mỗi replica | Max mỗi pool | Tổng tối đa |
|---|---:|---:|---:|---:|
| Order Service | 4 | 1 | 20 | 80 |
| Billing Service | 3 | 1 | 12 | 36 |
| Reporting Service | 2 | 1 | 8 | 16 |
| Worker | 2 | 1 | 6 | 12 |
| Batch và công cụ vận hành | — | — | — | 20 |
| **Tổng client connection tiềm năng** | | | | **164** |

Con số 164 chưa phải giá trị SESSIONS cần cấu hình. Cần cộng session nền, process, headroom và các kết nối khác chưa có trong bảng. Nếu một replica có nhiều datasource, phải cộng từng pool. Nếu có rolling deployment, old replica và new replica có thể chạy đồng thời, làm số kết nối vượt số replica bình thường.

### 3.3. Tính cả giai đoạn autoscaling và deployment

Capacity phải dựa trên số replica tối đa có thể xuất hiện, không chỉ số replica trung bình.

Ví dụ:

- Bình thường chạy 4 pod, mỗi pod có maximumPoolSize 20: tối đa 80.
- Autoscaling tăng lên 8 pod: tối đa 160.
- Rolling deployment chạy 4 pod cũ và 4 pod mới cùng lúc: vẫn có thể có 160 connection trong thời gian overlap.
- Nếu mỗi pod có hai datasource với pool 20 và 5: mỗi pod có thể tạo tối đa 25 connection.

Nếu database chỉ dành 100 session cho service này, cấu hình trên có thể làm service tự chiếm quá nhiều capacity hoặc gây lỗi khi scale. Hãy giới hạn autoscaling theo ngân sách database hoặc dùng cơ chế quản lý concurrency ở cấp ứng dụng/platform.

### 3.4. Dùng thời gian giữ connection để ước lượng concurrency

Định luật Little có thể giúp ước lượng số connection trung bình cần thiết:

    Average concurrent connections
      = database throughput
      x average connection hold time

Ví dụ ứng dụng xử lý 80 database operation mỗi giây và mỗi operation giữ connection trung bình 0,1 giây:

    80 operations/s x 0.1 s = 8 concurrent connections

Đây là mức concurrency trung bình theo giả định. Pool tối đa cần tính thêm biến động, tail latency, transaction dài và yêu cầu burst. Hãy đo thời gian giữ connection thực tế thay vì chỉ đo thời gian SQL, vì connection có thể bị giữ trong toàn bộ transaction.

Công thức này không thay thế load test. Nếu database throughput bị giới hạn bởi CPU hoặc I/O, tăng pool có thể làm tăng queue và latency mà không tăng số operation hoàn tất.

### 3.5. Pool nhỏ có thể tốt hơn pool lớn

Database có năng lực xử lý hữu hạn. Một pool lớn có thể tạo nhiều session cùng chạy query, làm tăng:

- CPU context switching và contention.
- Buffer/cache pressure.
- I/O queue và wait event.
- Lock contention và thời gian chờ transaction.
- PGA/session memory.
- Số process ở chế độ dedicated server.

Hãy tìm điểm throughput cao nhất trong load test. Nếu tăng pool từ 20 lên 40 không tăng throughput nhưng làm p95 latency và CPU tăng, pool 40 không đem lại lợi ích.

Một số hướng dẫn dùng số core CPU hoặc công thức tham khảo để bắt đầu sizing, nhưng không có con số pool đúng cho mọi Oracle workload. SQL, transaction length, storage latency, RAC, Resource Manager và loại server connection đều ảnh hưởng kết quả.

## 4. Oracle SESSIONS và PROCESSES

Pool phía Java chỉ kiểm soát số kết nối mà ứng dụng tạo. Oracle Database vẫn có giới hạn riêng đối với session và process.

### 4.1. SESSIONS

SESSIONS giới hạn số session có thể tồn tại đồng thời trong một instance. User session được tạo khi client đăng nhập database. Một session idle vẫn tồn tại và chiếm slot cho tới khi được đóng hoặc Oracle kết thúc session.

Các kết nối từ Spring Boot, ORDS, batch, SQL Developer, monitoring và các ứng dụng khác cùng tiêu thụ session của instance tương ứng.

Không nên nhầm số session với số transaction đang chạy. Một session có thể tồn tại lâu nhưng không có transaction; một session có thể thực hiện nhiều transaction nối tiếp.

### 4.2. PROCESSES

PROCESSES giới hạn số process phía server mà Oracle instance có thể sử dụng. Nó phải đủ cho server process phục vụ client và các background process của Oracle.

Trong dedicated server mode, một user session thường cần một dedicated server process. Vì thế, khi số connection tăng, số process cũng có thể tăng tương ứng. Khi dùng shared server, nhiều session có thể chia sẻ một nhóm server process nên quan hệ giữa hai giới hạn khác đi.

Không giả định PROCESSES phải bằng SESSIONS hoặc số process hiện tại phải bằng số user session. Hãy kiểm tra cả hai resource và chế độ kết nối của database.

### 4.3. Kiểm tra tham số hiện tại

Có thể xem giá trị khởi tạo:

    SHOW PARAMETER processes;
    SHOW PARAMETER sessions;

Hoặc:

    SELECT name, value, isdefault, issys_modifiable
    FROM v$parameter
    WHERE name IN ('processes', 'sessions')
    ORDER BY name;

Giá trị mặc định và quan hệ giữa SESSIONS với PROCESSES phụ thuộc phiên bản và cấu hình Oracle. Không dùng một công thức mặc định để suy ra capacity production mà không kiểm tra giá trị đang chạy.

### 4.4. Kiểm tra mức sử dụng và giới hạn

V$RESOURCE_LIMIT cho biết mức sử dụng hiện tại, mức cao nhất kể từ lần khởi động instance gần nhất và giới hạn resource:

    SELECT
        resource_name,
        current_utilization,
        max_utilization,
        initial_allocation,
        limit_value
    FROM v$resource_limit
    WHERE resource_name IN ('sessions', 'processes')
    ORDER BY resource_name;

Ý nghĩa:

- CURRENT_UTILIZATION: số resource đang được sử dụng tại thời điểm truy vấn.
- MAX_UTILIZATION: mức cao nhất kể từ khi instance khởi động gần nhất; restart có thể đặt lại mốc peak.
- INITIAL_ALLOCATION: lượng resource được cấp ban đầu.
- LIMIT_VALUE: giới hạn resource theo cấu hình.

Nếu current_utilization tiến sát limit_value trong giờ cao điểm, cần điều tra trước khi scale ứng dụng. Max_utilization giúp phát hiện peak đã xảy ra nhưng không cho biết chính xác thời điểm; ghép với monitoring/AWR và log ứng dụng.

### 4.5. Đếm session theo ứng dụng

    SELECT
        username,
        service_name,
        machine,
        program,
        module,
        status,
        COUNT(*) AS session_count
    FROM v$session
    WHERE type = 'USER'
    GROUP BY
        username,
        service_name,
        machine,
        program,
        module,
        status
    ORDER BY session_count DESC;

Các cột service_name, machine, program và module giúp xác định ứng dụng tạo session. Ứng dụng nên đặt MODULE/ACTION hoặc client identifier phù hợp để DBA phân biệt các service cùng dùng một database user.

Session INACTIVE vẫn chiếm session slot. Không chỉ đếm ACTIVE khi tính capacity. Nếu cần phân biệt session đang thực hiện SQL, có thể xem SQL_ID, event và trạng thái nhưng không được coi session idle là không tiêu thụ tài nguyên.

### 4.6. Đếm process

    SELECT COUNT(*) AS process_count
    FROM v$process;

V$PROCESS gồm process Oracle quản lý, bao gồm background process và process phục vụ client. Đối chiếu số này với PROCESSES resource trong V$RESOURCE_LIMIT; không so sánh trực tiếp với số thread Java.

### 4.7. Oracle RAC

Với RAC, mỗi instance có giới hạn và mức sử dụng riêng. Tổng capacity của cluster không bảo đảm mọi instance đều còn chỗ nhận kết nối. Service có thể phân phối không đều hoặc failover làm dồn connection sang instance còn lại.

Dùng GV$RESOURCE_LIMIT để theo dõi từng instance:

    SELECT
        inst_id,
        resource_name,
        current_utilization,
        max_utilization,
        limit_value
    FROM gv$resource_limit
    WHERE resource_name IN ('sessions', 'processes')
    ORDER BY inst_id, resource_name;

Khi thiết kế pool cho RAC, cần xem service placement, load balancing, failover behavior và capacity còn lại khi một instance ngừng hoạt động. Không cấu hình tổng pool bằng toàn bộ capacity bình thường nếu hệ thống phải tiếp tục phục vụ khi mất một node.

## 5. Giới hạn session theo user và profile

Ngoài giới hạn toàn instance, Oracle có thể giới hạn session theo user thông qua profile.

Một số resource limit thường gặp:

- SESSIONS_PER_USER: số session đồng thời tối đa cho một user.
- IDLE_TIME: thời gian session không hoạt động tối đa theo profile.
- CONNECT_TIME: tổng thời gian kết nối tối đa theo profile.
- CPU_PER_SESSION và các giới hạn tài nguyên khác theo cấu hình.

Kiểm tra profile của user:

    SELECT username, profile
    FROM dba_users
    WHERE username = 'APP_USER';

Xem giới hạn:

    SELECT
        profile,
        resource_name,
        limit
    FROM dba_profiles
    WHERE profile = (
        SELECT profile
        FROM dba_users
        WHERE username = 'APP_USER'
    )
      AND resource_type = 'KERNEL'
    ORDER BY resource_name;

Việc thực thi các giới hạn resource trong profile phụ thuộc RESOURCE_LIMIT và cấu hình database. DBA cần kiểm tra trạng thái tham số và chính sách profile đang áp dụng.

Nếu SESSIONS_PER_USER thấp hơn tổng connection pool có thể mở cho một database user, ứng dụng có thể nhận lỗi ORA-02391 ngay cả khi instance còn session capacity. Dùng database user riêng cho từng service giúp giới hạn và quan sát tốt hơn.

IDLE_TIME hoặc CONNECT_TIME có thể làm Oracle kết thúc/đánh dấu session theo chính sách profile. Pool không nhất thiết biết ngay physical connection đã bị database chấm dứt. Request tiếp theo có thể gặp lỗi connection; pool cần phát hiện, loại bỏ và tạo lại connection. Đừng đặt profile idle limit ngắn hơn nhịp keepalive của pool mà không kiểm thử.

## 6. Vòng đời kết nối ở các tầng khác nhau

Một connection có thể chịu giới hạn từ nhiều tầng:

    Spring / HikariCP
      |  maxLifetime, idleTimeout, keepaliveTime
      v
    JDBC driver
      |  driver/network timeout, socket state
      v
    Network / Firewall / Proxy
      |  idle timeout, TCP reset, connection lifetime
      v
    Oracle listener / database service
      |  authentication, profile, service availability
      v
    Oracle session / server process

Các giới hạn này không giống nhau:

| Cơ chế | Kiểm soát điều gì | Có phải SQL timeout không? |
|---|---|---|
| Hikari maxLifetime | Tuổi thọ physical connection trong pool | Không |
| Hikari idleTimeout | Thời gian connection dư nằm idle trong pool | Không |
| Hikari keepaliveTime | Kiểm tra connection idle theo chu kỳ | Không |
| Hikari connectionTimeout | Thời gian chờ mượn connection | Không |
| Oracle profile IDLE_TIME | Thời gian session không hoạt động theo profile | Không |
| Oracle profile CONNECT_TIME | Tổng thời gian kết nối theo profile | Không |
| Network/firewall idle timeout | Kết nối không có traffic trong khoảng thời gian | Không |
| Statement/query timeout | Thời gian thực thi statement được phép | Có |
| Transaction timeout | Thời gian transaction được phép theo tầng quản lý | Không đồng nghĩa với connection lifetime |

Cấu hình phải phối hợp theo giới hạn ngắn nhất thực sự áp dụng. Ví dụ, nếu firewall ngắt connection idle sau 15 phút, maxLifetime 30 phút không bảo đảm connection idle vẫn sống qua mốc 15 phút. Có thể dùng keepalive dưới ngưỡng network nếu phù hợp, hoặc để pool chủ động loại bỏ và tạo lại connection trước giới hạn đó.

### 6.1. Chọn maxLifetime theo giới hạn thấp nhất

Giả sử môi trường có giới hạn lifetime cứng 60 phút từ một tầng network hoặc proxy. Có thể đặt maxLifetime thấp hơn giới hạn đó với một khoảng an toàn, ví dụ 50 phút, sau khi kiểm thử. Đây chỉ là ví dụ; phải lấy giới hạn thật từ network/DBA.

Không chọn maxLifetime theo thời gian deploy hoặc thời gian chạy một request. Nó quản lý vòng đời physical connection, không phải thời gian nghiệp vụ.

### 6.2. keepalive và idle timeout của network

Nếu firewall loại bỏ connection không có traffic sau 10 phút, keepalive 5 phút có thể giúp phát hiện hoặc giữ connection idle tùy network policy và driver. Tuy nhiên, một số thiết bị không coi JDBC validation giống traffic ứng dụng; cần kiểm tra thực tế.

Một lựa chọn khác là để idleTimeout loại bỏ connection trước mốc firewall. Khi request mới tới, pool mở connection mới. Việc này giảm session nhàn rỗi nhưng tăng chi phí tạo connection.

### 6.3. Oracle Net EXPIRE_TIME và TCP keepalive

SQLNET.EXPIRE_TIME là cơ chế Oracle Net gửi probe để phát hiện kết nối không còn hoạt động trong một số cấu hình. TCP keepalive là cơ chế ở tầng operating system/network. Chúng có thể giúp phát hiện dead peer nhưng không phải giới hạn max connection lifetime và không thay thế query timeout.

Cần phân biệt:

- Detect connection chết.
- Giữ connection idle qua network timeout.
- Chủ động recycle connection lâu năm.
- Hủy một SQL đang chạy quá lâu.

Mỗi mục tiêu cần cơ chế phù hợp.

## 7. Cấu hình Spring Boot thực tế

Một cấu hình có thể bắt đầu từ capacity plan đã được DBA thống nhất:

    spring:
      datasource:
        hikari:
          pool-name: order-pool
          maximum-pool-size: 16
          minimum-idle: 4
          connection-timeout: 20000
          validation-timeout: 3000
          idle-timeout: 300000
          max-lifetime: 1500000
          keepalive-time: 240000

Các giá trị chỉ minh họa cho một service. Hãy thay bằng giá trị đã được tính theo số replica, số datasource, database budget và giới hạn network. Không copy nguyên cấu hình này sang mọi service.

### 7.1. Cấu hình qua environment variables

Spring Boot có thể bind cấu hình từ environment variable:

    SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=16
    SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE=4
    SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT=20000
    SPRING_DATASOURCE_HIKARI_MAX_LIFETIME=1500000

Cách quản lý cấu hình theo môi trường giúp điều chỉnh pool mà không thay source code. Tuy nhiên, phải có giới hạn và review để tránh một replica hoặc môi trường tự tăng pool ngoài ngân sách Oracle.

### 7.2. Nhiều DataSource

Nếu ứng dụng dùng nhiều database hoặc nhiều schema connection pool, mỗi DataSource thường có pool riêng. Không chỉ xem spring.datasource.hikari khi có cấu hình custom; hãy kiểm tra mọi bean DataSource và tên pool.

Ví dụ:

    @Bean
    @ConfigurationProperties("app.datasource.orders.hikari")
    HikariDataSource ordersDataSource() {
        return new HikariDataSource();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting.hikari")
    HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }

Cần cộng maximumPoolSize của cả ordersDataSource và reportingDataSource trên mọi replica. Nếu reporting query có tải nặng, có thể dành pool riêng và giới hạn concurrency để tránh chiếm hết connection của transaction nghiệp vụ.

### 7.3. HikariCP hay Oracle UCP?

HikariCP là lựa chọn phổ biến, nhẹ và tích hợp tốt với Spring Boot. Oracle Universal Connection Pool (UCP) là pool của Oracle, có thể phù hợp khi cần các khả năng tích hợp Oracle như FAN/FCF hoặc runtime connection load balancing trong môi trường RAC, tùy phiên bản và cấu hình.

Không phải hệ thống nào dùng Oracle cũng bắt buộc dùng UCP. Chọn pool dựa trên tính năng cần thiết, khả năng vận hành, hỗ trợ driver, HA strategy và kết quả benchmark. Không chạy hai pool lồng nhau cho cùng một DataSource nếu không có lý do rõ ràng.

## 8. JPA/Hibernate giữ connection trong bao lâu?

Trong JPA, connection thường được lấy khi transaction cần truy cập database và được trả lại theo connection handling mode của Hibernate và transaction manager. Cách lấy/trả connection phụ thuộc cấu hình, phiên bản Hibernate, JTA hay local transaction và cách sử dụng EntityManager.

Điều quan trọng là không để transaction kéo dài hơn thời gian cần thiết.

### 8.1. Transaction ngắn

Ví dụ service:

    @Service
    class OrderService {

        private final OrderRepository repository;

        OrderService(OrderRepository repository) {
            this.repository = repository;
        }

        @Transactional
        public void updateStatus(Long orderId, OrderStatus status) {
            Order order = repository.findById(orderId)
                .orElseThrow();

            order.setStatus(status);
        }
    }

Transaction bao quanh thao tác đọc và cập nhật dữ liệu. Khi transaction hoàn tất, connection có thể được trả về pool theo cơ chế quản lý của framework.

### 8.2. Không giữ transaction khi gọi dịch vụ ngoài

Mẫu cần tránh:

    @Transactional
    public void placeOrder(OrderRequest request) {
        Order order = repository.save(createOrder(request));

        paymentClient.authorize(request.payment());

        inventoryClient.reserve(request.items());
    }

Trong ví dụ, transaction có thể giữ connection trong khi chờ payment và inventory qua network. Nếu dịch vụ ngoài chậm, connection pool bị chiếm lâu và số connection cần thiết tăng.

Nên thiết kế transaction ngắn cho các thay đổi database, sau đó phối hợp external service bằng outbox, saga hoặc quy trình bù trừ phù hợp. Nếu nghiệp vụ cần atomicity xuyên hệ thống, phải thiết kế distributed transaction có chủ đích; @Transactional đơn lẻ không bao phủ HTTP call.

### 8.3. Open Session in View

Trong ứng dụng web, Open Session in View có thể giữ persistence context mở đến cuối request để hỗ trợ lazy loading ở tầng view. Nó không đồng nghĩa mọi request luôn giữ một connection vật lý suốt toàn bộ thời gian; connection acquisition/release còn phụ thuộc Hibernate và transaction configuration. Tuy vậy, truy cập lazy ngoài service transaction có thể tạo thêm query ở thời điểm khó quan sát.

Hãy xác định rõ nơi truy cập dữ liệu, dùng DTO/projection hoặc fetch plan phù hợp và cân nhắc tắt Open Session in View nếu muốn transaction boundary rõ ràng. Kiểm thử để tránh lỗi LazyInitializationException sau khi thay đổi.

### 8.4. JDBC resource và connection leak

Với JDBC trực tiếp, luôn đóng Connection, PreparedStatement và ResultSet:

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT status FROM orders WHERE order_id = ?")) {

        statement.setLong(1, orderId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (resultSet.next()) {
                return resultSet.getString("status");
            }
        }
    }

Try-with-resources bảo đảm close được gọi khi thành công hoặc có exception. Với connection do pool quản lý, close trả connection về pool.

Trong JPA, để Spring transaction manager quản lý EntityManager và connection. Tránh tự lấy physical connection từ provider rồi đóng hoặc giữ ngoài vòng đời transaction nếu chưa hiểu rõ integration.

## 9. Timeout ở ứng dụng và database

Connection pool có nhiều timeout khác nhau. Đặt một timeout duy nhất cho mọi tầng thường dẫn tới lỗi khó chẩn đoán.

| Timeout | Ý nghĩa |
|---|---|
| Connection timeout | Chờ lấy connection từ pool |
| Validation timeout | Chờ kiểm tra connection còn hợp lệ |
| Idle timeout | Connection dư nằm idle trong pool |
| Max lifetime | Tuổi thọ tối đa physical connection |
| Keepalive interval | Chu kỳ kiểm tra connection idle |
| Query/statement timeout | Thời gian cho phép SQL thực thi |
| Transaction timeout | Thời gian transaction được phép tồn tại |
| HTTP client timeout | Thời gian client chờ response |
| Reverse proxy timeout | Thời gian proxy chờ upstream |
| Network idle timeout | Thời gian network device cho phép connection không có traffic |

Ví dụ một request HTTP có timeout 10 giây, nhưng connectionTimeout của Hikari là 30 giây. Client có thể bỏ request sau 10 giây trong khi thread Java vẫn chờ connection thêm 20 giây nếu cancellation không được truyền đúng. Cần đặt timeout theo thứ tự phù hợp và kiểm thử hành vi cancellation.

### 9.1. Query timeout

Có thể dùng JPA query timeout hint hoặc JDBC Statement.setQueryTimeout để giới hạn thời gian statement theo cơ chế được driver hỗ trợ.

Ví dụ JDBC:

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setQueryTimeout(5);
        // bind parameters and execute
    }

Đơn vị setQueryTimeout là giây. Khả năng cancel và thời gian phản hồi phụ thuộc driver/database. Query timeout không tự động đặt giới hạn connection lifetime.

### 9.2. Transaction timeout

Spring có thể đặt timeout cho transaction ở cấp annotation hoặc transaction manager:

    @Transactional(timeout = 10)
    public void processOrder(Long id) {
        // database work
    }

Cơ chế thực thi timeout phụ thuộc transaction manager và persistence provider. Không coi nó là thay thế cho statement timeout hoặc HTTP timeout. Một transaction timeout có thể đánh dấu transaction rollback-only nhưng statement đang chạy vẫn cần được hủy theo khả năng của driver/database.

### 9.3. Đặt timeout theo mục tiêu request

Một luồng request thường cần quan hệ hợp lý:

    HTTP client deadline
        >= API gateway/upstream budget
        >= application processing budget
        >= database statement budget

Connection acquisition budget là một phần của application processing budget. Các timeout phải có đủ khoảng để xử lý lỗi, rollback và trả response. Không đặt tất cả cùng một giá trị mà không tính overhead.

## 10. Theo dõi pool trong Spring Boot

Spring Boot Actuator và Micrometer có thể xuất metric cho HikariCP khi metrics integration được bật và cấu hình phù hợp.

Các metric thường cần quan sát:

| Metric | Ý nghĩa |
|---|---|
| hikaricp.connections.active | Connection đang được ứng dụng mượn |
| hikaricp.connections.idle | Connection đang idle trong pool |
| hikaricp.connections.pending | Thread đang chờ connection |
| hikaricp.connections.max | Giới hạn connection của pool |
| hikaricp.connections.min | Mức idle tối thiểu cấu hình |
| hikaricp.connections.timeout | Số lần timeout khi lấy connection |
| hikaricp.connections.creation | Thời gian tạo connection |
| hikaricp.connections.usage | Thời gian connection được sử dụng |

Tên metric và tag cụ thể có thể khác theo Micrometer/Spring Boot version. Nếu có nhiều pool, phân biệt bằng pool name và datasource tag.

### 10.1. Dấu hiệu pool quá nhỏ

- Active thường xuyên bằng max.
- Pending tăng trong giờ cao điểm.
- Connection acquire latency cao.
- Hikari connection timeout xuất hiện.
- Oracle còn headroom và query latency vẫn tốt.

Nếu các dấu hiệu này cùng xuất hiện, có thể pool đang nhỏ so với concurrency cần thiết. Tuy nhiên, phải kiểm tra connection usage time và transaction duration trước khi tăng pool. Một leak hoặc transaction dài có thể làm pool cạn dù số connection tối ưu thấp hơn.

### 10.2. Dấu hiệu pool quá lớn

- Active connection tăng nhưng throughput không tăng.
- Database CPU, I/O wait hoặc lock wait tăng.
- p95/p99 query latency xấu đi.
- Oracle session/process utilization tiến sát giới hạn.
- Nhiều session idle không cần thiết.
- Các service cạnh tranh connection với nhau.

Trong trường hợp này, giảm pool, giới hạn concurrency, tối ưu SQL hoặc phân bổ service workload có thể cải thiện hệ thống hơn là tăng capacity.

### 10.3. Dùng leak detection

Có thể bật tạm:

    leak-detection-threshold: 60000

Nếu connection được mượn lâu hơn 60 giây, HikariCP có thể ghi cảnh báo và stack trace nơi connection được mượn. Đây là tín hiệu điều tra; có thể là transaction hợp lệ chạy lâu chứ không phải leak thật.

Sau khi xác định nguyên nhân, tắt hoặc đặt threshold phù hợp. Không để cảnh báo leak trở thành noise khiến đội vận hành bỏ qua.

## 11. Theo dõi Oracle session/process cùng pool metrics

Cần ghép metric của Java với số liệu database. Một dashboard chỉ có Hikari active/idle không cho biết tổng session từ các service khác.

### 11.1. Mức sử dụng so với giới hạn

    SELECT
        resource_name,
        current_utilization,
        max_utilization,
        limit_value
    FROM v$resource_limit
    WHERE resource_name IN ('sessions', 'processes')
    ORDER BY resource_name;

Thu thập định kỳ để tạo time series. MAX_UTILIZATION chỉ là peak kể từ startup nên không thay thế lịch sử metric liên tục.

### 11.2. Session theo service/module

    SELECT
        service_name,
        module,
        machine,
        status,
        COUNT(*) AS session_count
    FROM v$session
    WHERE type = 'USER'
    GROUP BY service_name, module, machine, status
    ORDER BY session_count DESC;

Đặt MODULE/ACTION hoặc client identifier từ ứng dụng giúp nhận diện session. Không dùng một database user chung cho mọi service nếu việc phân biệt và kiểm soát quyền là yêu cầu quan trọng.

### 11.3. RAC theo instance

    SELECT
        inst_id,
        resource_name,
        current_utilization,
        max_utilization,
        limit_value
    FROM gv$resource_limit
    WHERE resource_name IN ('sessions', 'processes')
    ORDER BY inst_id, resource_name;

Trong RAC, cần theo dõi cả trạng thái bình thường và tình huống một instance down. Service failover có thể dồn workload sang node còn lại; pool sizing phải tính được kịch bản này.

### 11.4. Kết nối metric hai phía

Khi điều tra pool timeout:

1. Lấy thời điểm Hikari active=max và pending tăng.
2. Đối chiếu Oracle sessions/processes cùng thời điểm.
3. Xem session theo service/module và trạng thái ACTIVE/INACTIVE.
4. Xác định connection usage time và transaction duration ở ứng dụng.
5. Kiểm tra database wait, CPU, I/O và SQL execution time.
6. Phân biệt pool cạn do workload thực, connection leak hay database chậm.

Nếu Hikari pool hết connection nhưng Oracle còn nhiều session idle, có thể connection bị giữ ở ứng dụng. Nếu Oracle session/process gần limit và nhiều service cùng tăng, cần xử lý capacity ở cấp database/toàn hệ thống.

## 12. Lỗi thường gặp khi chạm giới hạn Oracle

| Oracle error | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| ORA-00018 | Vượt giới hạn số session của instance | SESSIONS, V$RESOURCE_LIMIT, tổng pool và client |
| ORA-00020 | Vượt giới hạn số process | PROCESSES, V$PROCESS, dedicated/shared server và background process |
| ORA-02391 | Vượt SESSIONS_PER_USER trong profile | Profile và tổng connection dùng chung database user |
| ORA-12516 / ORA-12519 | Listener không tìm được handler phù hợp hoặc handler không tiếp nhận kết nối | Listener, service, handler, trạng thái instance và capacity |

Các lỗi listener không chứng minh chắc chắn SESSIONS hoặc PROCESSES đã hết. Cần đọc listener log, trạng thái service và resource utilization trước khi kết luận.

### 12.1. ORA-00018

Khi session đạt giới hạn, database không thể cấp thêm session mới. Các connection đang tồn tại có thể tiếp tục hoạt động, nhưng login mới thất bại.

Kiểm tra V$RESOURCE_LIMIT, V$SESSION và tổng pool trên mọi application replica. Xác định session idle có bị giữ bởi minimumIdle quá cao hay connection leak không.

### 12.2. ORA-00020

Khi process đạt giới hạn, Oracle không thể tạo thêm process cần thiết cho kết nối hoặc hoạt động database. Với dedicated server, tăng user connection có thể làm process count tăng nhanh.

Kiểm tra V$PROCESS, resource limit, background process, server mode và hệ điều hành. Không chỉ tăng PROCESSES mà không kiểm tra giới hạn process và memory của host.

### 12.3. ORA-02391

Lỗi này thường liên quan SESSIONS_PER_USER trong profile. Instance có thể còn session capacity nhưng một user cụ thể đã đạt giới hạn.

Kiểm tra profile user, số session theo username và tổng maximumPoolSize của mọi ứng dụng đang dùng chung user. Tách user theo service hoặc điều chỉnh profile sau khi DBA đánh giá quyền và capacity.

## 13. Điều chỉnh giới hạn Oracle

Nếu dữ liệu cho thấy database thực sự thiếu session/process capacity, DBA có thể xem xét thay đổi tham số. Đây là thay đổi cấp database, cần đánh giá resource host, kiến trúc RAC, lịch bảo trì và phiên bản Oracle.

Trước khi tăng giới hạn:

- Xác nhận current và peak utilization trong giờ tải cao.
- Kiểm tra số session/process nền.
- Tính tổng connection tối đa từ mọi pool và client.
- Kiểm tra memory, OS process limit và capacity của server.
- Xác định PROCESSES/SESSIONS là static hay dynamic trong phiên bản đang dùng.
- Xác nhận thay đổi có cần restart instance hay không.
- Với RAC, tính riêng từng instance và kịch bản failover.
- Xem xét giới hạn profile, PDB, service và Resource Manager.

PROCESSES thường là tham số cần thay đổi qua SPFILE và restart instance. SESSIONS thường được dẫn xuất mặc định từ PROCESSES nếu không cấu hình riêng; khi đã đặt tường minh, DBA phải tính lại theo nhu cầu và tài liệu đúng phiên bản. Không copy giá trị mẫu từ database khác.

Ví dụ lệnh cấu hình chỉ để minh họa quy trình DBA:

    ALTER SYSTEM SET processes = 500 SCOPE = SPFILE;

Lệnh trên không có hiệu lực đầy đủ cho instance đang chạy cho đến khi restart theo yêu cầu của tham số. Giá trị 500 không phải khuyến nghị chung. DBA cần xác minh tham số, memory và OS limits trước khi thay đổi.

Tăng SESSIONS/PROCESSES chỉ mở rộng giới hạn, không tăng CPU, RAM, I/O hay năng lực xử lý SQL. Nếu database đang bão hòa, tăng giới hạn có thể khiến nhiều session hơn tranh chấp tài nguyên.

## 14. Session state và connection reuse

Pool tái sử dụng physical session. Một số trạng thái session có thể tồn tại sau khi connection được trả về pool, chẳng hạn:

- ALTER SESSION SET TIME_ZONE.
- NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS.
- CURRENT_SCHEMA.
- Transaction isolation hoặc read-only state nếu không được reset đúng.
- Package global variables.
- Application context.
- Client identifier, module và action.
- Temporary table/session state.

HikariCP có thể reset một số thuộc tính JDBC mà nó theo dõi, nhưng không thể tự hiểu và reset mọi lệnh ALTER SESSION hoặc trạng thái PL/SQL do ứng dụng tạo.

Nếu request A thay đổi TIME_ZONE rồi trả connection về pool, request B có thể nhận session với timezone của request A. Điều này gây kết quả không ổn định và rò rỉ trạng thái giữa tenant/request.

Cách quản lý:

1. Cố định session state ở lúc tạo physical connection nếu có thể.
2. Tránh thay đổi session state theo request.
3. Nếu cần thay đổi, lưu giá trị cũ và khôi phục trong finally trước khi trả connection.
4. Dùng connection initialization/reset hook phù hợp với pool.
5. Đặt MODULE/ACTION/client identifier có quy trình reset rõ ràng.
6. Kiểm thử với nhiều physical connection và request chạy đồng thời.
7. Không để package state hoặc temporary state tồn tại ngoài transaction dự kiến.

## 15. Quy trình xử lý khi pool timeout hoặc Oracle từ chối kết nối

Khi ứng dụng báo timeout lấy connection hoặc lỗi login Oracle, thực hiện theo trình tự:

### Bước 1: Xác định lỗi ở tầng nào

Phân biệt:
- Hikari timeout khi chờ connection.
- JDBC connect/login timeout.
- Oracle error khi tạo session/process.
- Network reset hoặc firewall timeout.
- SQL/query timeout sau khi đã lấy connection.
- HTTP timeout ở gateway/client.

Không xử lý tất cả bằng cách tăng maximumPoolSize.

### Bước 2: Lấy metric Hikari

Xem active, idle, pending, max, timeout và usage duration theo pool name. Nếu active=max và pending tăng, pool đang cạn connection có thể mượn.

### Bước 3: Đối chiếu Oracle

Truy vấn V$RESOURCE_LIMIT, session theo service/module, process count và listener log. Kiểm tra profile user và resource limit.

### Bước 4: Tìm nguyên nhân giữ connection

Xem transaction dài, query chậm, connection leak, gọi external service trong transaction, thread bị block và lazy loading ngoài phạm vi dự kiến.

### Bước 5: Kiểm tra vòng đời connection

Đối chiếu maxLifetime, idleTimeout, keepaliveTime với firewall, proxy, Oracle profile và network timeout. Kiểm tra session state và connection validation.

### Bước 6: Chọn thay đổi có căn cứ

- Pool nhỏ trong khi DB còn headroom: tăng từng bước và load test.
- Pool lớn nhưng DB bão hòa: giảm concurrency, tối ưu SQL và transaction.
- Connection bị network ngắt: điều chỉnh lifetime/keepalive/validation theo giới hạn thật.
- User vượt profile: điều chỉnh phân bổ user/pool hoặc profile.
- Instance hết session/process: DBA lập capacity plan và xem xét tham số sau khi kiểm tra host.
- Leak: sửa vòng đời resource và transaction, không che lỗi bằng cách tăng pool.

### Bước 7: Xác nhận dưới tải đại diện

Sau thay đổi, đo lại throughput, p95/p99 latency, pool pending, timeout, Oracle session/process utilization và database wait. So sánh cùng một kịch bản tải để biết thay đổi có cải thiện thực tế không.

## 16. Ví dụ capacity planning tổng thể

Một hệ thống có ba Spring Boot service và một worker. Oracle database có một instance dedicated server. DBA thống nhất ngân sách ban đầu cho các client của ứng dụng là 180 session; phần còn lại dành cho background, monitoring, DBA và headroom.

Các service chạy tối đa:

| Pool | Replica tối đa | MaximumPoolSize | Connection tối đa |
|---|---:|---:|---:|
| Order API | 4 | 20 | 80 |
| Billing API | 2 | 12 | 24 |
| Reporting API | 2 | 8 | 16 |
| Worker | 3 | 6 | 18 |
| **Tổng** | | | **138** |

Ngân sách còn 42 session cho batch, công cụ vận hành hoặc dao động khác trong giới hạn 180. Tuy nhiên, con số này cần được kiểm tra với số session thực tế, pool minimumIdle, rollout surge và các kết nối chưa được liệt kê.

Nếu deployment cho phép old và new replica cùng chạy đồng thời, capacity có thể tăng tạm thời. Platform nên giới hạn surge hoặc DBA phải dành thêm headroom. Nếu RAC failover dồn connection về một instance, phải tính lại giới hạn riêng node đó.

Load test cho thấy Order API chỉ cần khoảng 12 connection đồng thời để đạt throughput mục tiêu. Tăng pool từ 20 lên 40 không cải thiện throughput nhưng làm CPU database tăng. Nhóm giữ pool 20, giới hạn concurrency ở service và tối ưu query có thời gian giữ connection dài.

Đây là ví dụ về cách capacity plan phối hợp ngân sách Oracle với kết quả đo ứng dụng. Không chọn pool chỉ dựa trên tổng số session còn trống.

## 17. Nguyên tắc vận hành

- Một physical connection trong pool thường giữ một Oracle session; connection idle vẫn tiêu thụ session.
- maximumPoolSize là giới hạn của một pool; phải cộng mọi DataSource, replica, worker, batch và giai đoạn deployment overlap.
- minimumIdle quyết định số session nhàn rỗi mà pool cố duy trì.
- connectionTimeout là thời gian chờ mượn connection, không phải query timeout.
- idleTimeout chỉ co pool khi minimumIdle nhỏ hơn maximumPoolSize.
- maxLifetime recycle connection khi được trả về pool; nó không cưỡng bức hủy transaction đang chạy.
- keepaliveTime kiểm tra connection idle, phải nhỏ hơn maxLifetime và phù hợp với network idle timeout.
- Oracle SESSIONS giới hạn session; PROCESSES giới hạn process phía server. Với dedicated server, số process có thể tăng theo user session.
- Profile SESSIONS_PER_USER có thể giới hạn một database user trước khi instance hết session.
- Dùng V$RESOURCE_LIMIT, V$SESSION, V$PROCESS và GV$ view trong RAC để theo dõi giới hạn thực tế.
- Ghép metric Hikari với session/process và database wait để phân biệt pool cạn với database cạn capacity.
- Transaction ngắn, đóng resource đúng cách và tránh gọi external service trong transaction.
- Không tăng pool hoặc Oracle limit khi chưa xác định bottleneck; concurrency cao hơn không đồng nghĩa throughput cao hơn.

Thiết kế connection pool là bài toán phân bổ concurrency giữa ứng dụng và Oracle Database. Pool cần đủ nhỏ để bảo vệ database, đủ lớn để tránh xếp hàng không cần thiết, và có vòng đời phù hợp với giới hạn network/database. Khi tổng capacity được tính trên mọi replica và được kiểm chứng bằng metric hai phía, hệ thống sẽ ít gặp tình trạng cạn session, connection stale và timeout khó giải thích hơn.
