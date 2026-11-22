# Giới hạn pool theo tổng số bản sao ứng dụng

## 1. Vì sao pool đúng trên một pod vẫn có thể làm nghẽn database?

Trong module **Spring Boot Integration**, Spring Boot thường truy cập PostgreSQL, MySQL hoặc một RDBMS khác thông qua JDBC, JPA/Hibernate, JdbcTemplate, jOOQ, Spring Batch và các adapter của Spring Integration. Phần lớn các thành phần đó lấy kết nối từ một **DataSource có connection pool**, thường là **HikariCP**. Pool giảm chi phí mở kết nối mới, nhưng mỗi kết nối vật lý vẫn tiêu thụ tài nguyên tại database.

Một sai lầm thường gặp: đặt `maximumPoolSize=30` vì một pod chạy ổn, sau đó triển khai thành **8 replica** mà không xét giới hạn ở database. Chỉ riêng ứng dụng đó đã có thể mở tới **8 × 30 = 240 kết nối**, vượt ngưỡng nếu PostgreSQL chỉ cho phép khoảng 200 kết nối và còn những ứng dụng khác đang sử dụng.

Trong thực tế, tổng nhu cầu có thể còn lớn hơn vì:

- Pod cũ và pod mới **chạy song song trong rolling update**.
- Horizontal Pod Autoscaler (HPA) tăng số replica vào giờ cao điểm.
- Scheduler, Spring Batch worker và consumer Kafka/RabbitMQ dùng **pool riêng**.
- Một ứng dụng có **nhiều DataSource**, nhiều persistence unit hoặc read/write split.
- Job migration, dịch vụ vận hành, monitoring và các ứng dụng khác cùng dùng database.
- Một lời gọi có thể giữ connection trong transaction rồi mở thêm connection cho `REQUIRES_NEW` hoặc DataSource thứ hai.

**Mục tiêu bài học** là tính được giới hạn pool trên **toàn bộ bản sao và toàn bộ nguồn sử dụng chung một năng lực database**, cấu hình HikariCP phù hợp, nhận biết pool saturation, điều tiết lưu lượng và kiểm thử trước khi scale hoặc nâng cấp.

~~~mermaid
flowchart TB
    subgraph APP["Order Service - nhiều replica"]
      A["Pod A: Hikari max 12"]
      B["Pod B: Hikari max 12"]
      C["Pod C: Hikari max 12"]
      D["... Pod H: Hikari max 12"]
    end
    subgraph OTHER["Nguồn tải bổ sung"]
      X["Spring Batch: 3 worker x max 8"]
      Y["Dịch vụ khác, migration, vận hành"]
    end
    A --> DB[("PostgreSQL: giới hạn kết nối chung")]
    B --> DB
    C --> DB
    D --> DB
    X --> DB
    Y --> DB
~~~

Điểm then chốt: `maximumPoolSize` chỉ giới hạn **một pool trong một JVM**. Nó không đặt hạn mức toàn cụm và không tự điều phối với các pool ở pod khác.

## 2. Nắm vững connection pool và các đơn vị cần đo

| Khái niệm | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| **Connection pool** | Tập kết nối vật lý được tái sử dụng khi xử lý JDBC. | Không phải hàng đợi request có độ bền qua restart. |
| `maximumPoolSize` | Số connection vật lý tối đa mà **một pool Hikari** có thể quản lý. | Không phải giới hạn kết nối của toàn ứng dụng hoặc cluster. |
| `minimumIdle` | Số connection idle mục tiêu mà Hikari cố gắng duy trì. | Không thay đổi mức trần `maximumPoolSize`; số kết nối có thể tăng khi tải đến. |
| **Active connection** | Connection đã được ứng dụng checkout, đang do caller giữ. | Có thể không chạy SQL nhưng vẫn bị giữ vì transaction còn mở. |
| **Idle connection** | Connection đang nằm trong pool và sẵn sàng được checkout. | Vẫn là kết nối vật lý, vẫn tính vào quota server. |
| **Pending acquisition** | Thread đang chờ pool cấp connection. | Là tín hiệu thiếu capacity hoặc connection bị giữ quá lâu. |
| `connectionTimeout` | Thời gian tối đa chờ **lấy một connection từ Hikari**. | Không phải timeout SQL hay deadline của toàn request. |
| **Database connection limit** | Giới hạn backend session hoặc connection mà database cho phép. | Bao gồm nhiều ứng dụng và các session phục vụ quản trị/replication tùy hệ thống. |

Trong Spring Boot, các lời gọi `JdbcTemplate`, JPA `EntityManager`, jOOQ hoặc `DataSource` trực tiếp có thể **dùng chung một pool** nếu được cấu hình cùng DataSource. Ngược lại, hai bean `HikariDataSource` khác nhau thường là **hai pool độc lập**, ngay cả khi cả hai đều trỏ tới **cùng một PostgreSQL**.

**Active ≠ số truy vấn đang thực thi**: Một connection có thể được giữ bởi transaction đang chờ HTTP API hoặc code xử lý dữ liệu, dù database đang không chạy câu SQL nào. Điều này khiến pool hết connection mà CPU database vẫn thấp.

## 3. Công thức lập ngân sách kết nối toàn cụm

Trước khi chọn pool size, lập danh sách những nguồn kết nối **cùng tiêu thụ một ngân sách**. Với một database server/endpoint có giới hạn kết nối tổng, ước tính giới hạn ứng dụng như sau:

\[
C_{\text{app-budget}} =
C_{\text{db-limit}}
- C_{\text{reserved}}
- C_{\text{other-apps}}
- C_{\text{operations}}
- C_{\text{safety}}
\]

Trong đó:

- `C_db-limit`: giới hạn connection tại database instance/endpoint đang sử dụng, theo cấu hình và chính sách của dịch vụ quản lý.
- `C_reserved`: những slot không nên/không thể cấp cho ứng dụng thông thường, ví dụ kết nối quản trị và các khoản dự phòng do DB engine yêu cầu.
- `C_other-apps`: tổng ngân sách cho những client khác chia sẻ database.
- `C_operations`: dự phòng cho migration, backup/monitoring, script đối soát và tác vụ không chạy liên tục.
- `C_safety`: biên dự phòng thêm để tránh khai thác tới sát trần.

Với nhiều nhóm ứng dụng:

\[
\sum_{g=1}^{G}
\left(N_{g,\text{peak}} \times P_{g,\max}\right)
\le C_{\text{app-budget}}
\]

`N_g,peak` là **số bản sao cực đại có thể tồn tại đồng thời** của nhóm `g`, còn `P_g,max` là giới hạn pool **mỗi bản sao**. Nếu có nhiều DataSource trong cùng pod cùng kết nối tới một database, phải cộng từng pool. Nếu batch job chạy trên pool hoặc node riêng, tính nhóm batch riêng.

Đây là **giới hạn trên khi mọi pool mở hết connection**, không phải dự báo số connection sử dụng trung bình. Dùng giới hạn trên để tránh cấu hình có thể phá quota khi đạt tải đỉnh; sau đó dùng số liệu tải thật để quyết định pool có cần lớn đến mức đó hay không.

### 3.1. Ví dụ tính toán với 8 pod và batch worker

Giả sử một PostgreSQL có giới hạn kết nối tổng **200**. Đội vận hành phân bổ, theo dữ liệu và chính sách nội bộ:

| Khoản sử dụng | Số connection dự kiến/giữ lại |
| --- | ---: |
| Giới hạn PostgreSQL | **200** |
| Kết nối dành cho quản trị và các mục đích không dùng bởi ứng dụng | 25 |
| Ứng dụng khác cùng database | 20 |
| Migration, monitor và tác vụ vận hành | 15 |
| **Ngân sách còn lại để chia cho Order + Batch** | **140** |

Trong đợt nâng cấp hoặc khi HPA đạt ngưỡng, có thể tồn tại đồng thời **8 pod Order**. Ngoài ra có **3 worker Spring Batch** cùng sử dụng database.

Nếu đặt:

- Order pool: **12 connection/pod** ⇒ `8 × 12 = 96`.
- Batch pool: **8 connection/worker** ⇒ `3 × 8 = 24`.
- Tổng tối đa của hai nhóm: **120 connection**.
- Ngân sách còn dư theo mô hình: **140 − 120 = 20 connection**.

Hai nhóm còn lại vẫn phải được giám sát; “dư 20” là **biên trong mô hình**, không bảo đảm thực tế còn 20 slot ở mọi thời điểm khi giả định ban đầu thay đổi. Mức 25/20/15 và pool size 12/8 chỉ là **giá trị minh họa**, không phải chuẩn áp dụng mọi PostgreSQL.

~~~mermaid
flowchart LR
    A["200: giới hạn DB"] --> B["-25: dự phòng quản trị"]
    B --> C["-20: ứng dụng khác"]
    C --> D["-15: vận hành"]
    D --> E["140: ngân sách Order + Batch"]
    E --> F["96: Order (8 x 12)"]
    E --> G["24: Batch (3 x 8)"]
    E --> H["20: biên còn lại"]
~~~

Nếu pool Order tăng từ 12 lên 20, tổng của hai nhóm sẽ thành `8 × 20 + 3 × 8 = 184`, **vượt 140**. Trong khi đó, chỉ một pod chạy thử `maximumPoolSize=20` có thể vẫn không có lỗi nào.

### 3.2. Tính cả rolling update và HPA

Không dùng **replica hiện tại** làm giá trị `N_peak` khi sizing. Cần xem:

1. HPA có thể scale tối đa bao nhiêu pod?
2. `Deployment.spec.strategy.rollingUpdate.maxSurge` cho phép thêm bao nhiêu pod trong rollout?
3. Có job theo lịch, canary, blue-green deployment hoặc pod mới khởi động trong lúc pod cũ **chưa trả connection** không?
4. Có bao nhiêu namespace, cluster hoặc vùng địa lý cùng dùng một database?
5. Pool tạo kết nối khi startup hay chỉ tăng dần theo tải, và database có chịu được **connection storm** khi nhiều pod khởi động đồng loạt không?

Ví dụ HPA tối đa 6 replica, trong lúc rolling update có thể tạo thêm 2 pod → **8 pod** là một giới hạn phù hợp để tính, **nếu** đây là số lượng đồng thời tối đa thực sự được nền tảng cho phép. Với blue-green chạy hai deployment độc lập, cần tính cả hai nhóm, có thể lớn hơn con số này.

## 4. Pool size không nên bằng số thread hay số HTTP request

Một HTTP request có thể cần nhiều truy vấn JDBC, nhưng nó **không nhất thiết giữ một connection suốt thời gian phản hồi**. Pool size nên liên hệ với:

- Lưu lượng request thực tế, tính cả job theo lịch, event consumer và retry.
- Số truy vấn hoặc transaction mỗi request.
- Thời gian connection được **checkout** trung bình và p95/p99.
- Giới hạn CPU/I/O, lock, disk và số worker bên database.
- Số pool cùng chạy và tổng quota đã dành cho toàn hệ thống.

Theo **định luật Little**, ở trạng thái ổn định:

\[
L = \lambda W
\]

Nếu app xử lý **180 request/giây**, mỗi request dùng trung bình **2 lần checkout connection**, mỗi lần giữ connection khoảng **25 ms**, số checkout đồng thời trung bình trên cả cụm có thể ước tính:

\[
L \approx 180 \times 2 \times 0.025 = 9
\]

Con số **9** chỉ là **ước lượng trung bình**, không cho phép kết luận pool tổng là 9 sẽ an toàn. Nó không mô tả burst, phân bố request lệch pod, transaction lâu, deadlock, spike p99 hoặc job batch. Hãy dùng quan sát thực tế và load test để xác định pool tối thiểu đáp ứng latency SLO; sau đó kiểm tra giới hạn trên theo công thức **ngân sách toàn cụm** ở mục 3.

**Tăng pool không tự tăng thông lượng database.** Khi DB đã nghẽn CPU, I/O, lock hoặc WAL, tăng connection đồng thời thường chỉ tạo thêm tranh chấp và chờ, làm latency xấu đi. Có thể giảm pool và giới hạn concurrency ở tầng ứng dụng để ổn định hơn.

## 5. Cấu hình HikariCP trong Spring Boot theo ngân sách

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Data JDBC/JPA và PostgreSQL**. Khi dùng một DataSource tự cấu hình bởi Boot, có thể đặt:

~~~yaml
# application.yml — minh họa pool cho mỗi pod Order
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 1500
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 300000
      data-source-properties:
        ApplicationName: orders-service
~~~

Trong ví dụ, các timeout/lifetime của Hikari viết ở đơn vị **mili giây**. Mật khẩu phải lấy từ secret manager hoặc biến môi trường được cấp quyền; không đưa password vào repository. Ví dụ endpoint `db.internal` là giả định, cần cấu hình network/TLS riêng khi triển khai.

| Thuộc tính | Vai trò | Lưu ý quan trọng |
| --- | --- | --- |
| `maximum-pool-size: 12` | Giới hạn pool vật lý ở mỗi JVM. | Tổng tối đa phụ thuộc số JVM/pool cùng đích. |
| `minimum-idle: 3` | Giữ mục tiêu ít nhất 3 connection idle khi có điều kiện. | Pool có thể mở thêm tới 12; không giới hạn ở 3. |
| `connection-timeout: 1500` | Chờ tối đa 1,5 giây để lấy connection từ pool. | Không phải 1,5 giây cho toàn bộ SQL/HTTP request. |
| `validation-timeout: 1000` | Giới hạn thời gian kiểm tra connection. | Cần nhỏ hơn `connectionTimeout` và tuân ngưỡng của Hikari. |
| `idle-timeout: 600000` | Có thể thu hồi connection idle vượt mức `minimumIdle`. | Không có cùng hiệu lực với pool cố định `minimumIdle=maximumPoolSize`. |
| `max-lifetime: 1500000` | Cho phép nghỉ hưu connection sau khoảng đời tối đa. | Nên ngắn hơn giới hạn connection lifetime của DB/proxy; active connection chỉ được thu hồi khi trả về pool. |
| `keepalive-time: 300000` | Định kỳ kiểm tra một số connection idle để giảm lỗi đóng kết nối khi không dùng. | Phải nhỏ hơn `maxLifetime`; không thay thế health query và timeout. |
| `pool-name` | Định danh pool trong log và metrics. | Đặt tên theo nguồn; không đưa dữ liệu cá nhân hoặc instance ID vào tag cardinality cao. |

**Chính sách `minimumIdle`:** HikariCP thường khuyến nghị hoạt động như pool cố định để có phản hồi ổn định dưới tải, tức không cấu hình `minimumIdle` và dùng giá trị mặc định bằng `maximumPoolSize`. Ví dụ đặt `minimum-idle: 3` để minh họa pool co giãn nhưng cần đo độ trễ mở connection mới và khả năng tạo bão kết nối khi autoscale. Dù cố định hay co giãn, **ngân sách giới hạn trên phải tính theo `maximumPoolSize`**, không phải `minimumIdle`.

### 5.1. Dùng biến môi trường để thay đổi ngân sách theo deployment

Có thể đặt kích thước bằng placeholder:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: ${ORDERS_DB_POOL_MAX:12}
~~~

Hệ thống triển khai truyền `ORDERS_DB_POOL_MAX` (hoặc dùng biến môi trường có mapping của Spring Boot như `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE`). Khi thay đổi số replica, ngân sách này cần được điều chỉnh theo mô hình capacity; không tự thay đổi pool theo CPU của từng pod mà bỏ qua database tổng.

Nếu app có nhiều bean `DataSource` tự khai báo, thuộc tính `spring.datasource.hikari.*` **không tự động áp dụng cho tất cả bean**. Mỗi DataSource phải được bind đúng prefix và giới hạn pool riêng, ví dụ `app.datasource.orders.hikari.maximum-pool-size` và `app.datasource.reporting.hikari.maximum-pool-size` theo lớp `@ConfigurationProperties` thực tế.

### 5.2. Các timeout khác không được bỏ sót

`connectionTimeout` của Hikari chỉ kiểm soát việc **chờ checkout**. Cần phân biệt thêm:

- **JDBC driver connect/socket timeout:** thời gian thiết lập kết nối tới database và chờ I/O mạng, phụ thuộc driver.
- **Query/statement timeout:** giới hạn câu SQL chạy quá lâu; có thể được áp bằng JDBC statement timeout hoặc chính sách phía DB.
- **Transaction timeout:** giới hạn công việc giao dịch theo framework và cách thực thi; không mặc định hủy được mọi blocking call ở mọi driver.
- **Network proxy/load balancer idle timeout:** có thể đóng kết nối khi idle; cần đồng bộ với `maxLifetime` và `keepaliveTime`.
- **Request deadline:** ngân sách thời gian HTTP/gRPC/batch operation. Nếu request hết thời gian nhưng SQL vẫn đang chạy, cần chính sách cancellation và resource cleanup thích hợp.

Không chỉ tăng `connection-timeout` từ 1,5 giây lên 30 giây khi pool bị nghẽn. Điều đó có thể làm nhiều HTTP thread chờ hơn và che giấu nguyên nhân query chậm, lock hoặc leak.

## 6. Tổng hợp nhiều DataSource và nhiều loại worker

Một ứng dụng có thể có:

~~~text
Order Service pod
  ├── ordersDataSource      (PostgreSQL A, max 12)
  ├── auditDataSource       (PostgreSQL A, max 4)
  └── reportingDataSource   (PostgreSQL B, max 6)
~~~

Ở đây tổng mức trần đến **PostgreSQL A** mỗi pod là **12 + 4 = 16**, còn PostgreSQL B nhận tối đa **6**. Nếu có 8 pod, riêng A đã có thể nhận **128 connection** từ hai pool. Không tính 6 connection của Reporting vào A nếu nó thực sự dùng **database instance khác với quota kết nối độc lập**.

Tuy nhiên, đừng phân chia theo **tên schema** hoặc database logic rồi mặc định chúng có quota riêng. Hai schema hoặc hai logical database có thể cùng nằm trên một PostgreSQL server dùng chung `max_connections`. Hãy nhóm ngân sách theo **điểm giới hạn connection thực tế** (instance, cluster/proxy hoặc dịch vụ managed DB), sau đó tính tổng tất cả pool trỏ về đó.

| Nguồn kết nối | Thường tạo pool riêng? | Cần đưa vào ngân sách |
| --- | --- | --- |
| JPA/Hibernate qua một DataSource | Không nhất thiết; thường dùng pool đã cấu hình cho DataSource. | Có, nhưng **chỉ đếm pool một lần**. |
| Spring JDBC + jOOQ dùng cùng DataSource | Có thể cùng dùng một pool. | Không đếm gấp đôi nếu thực sự cùng bean DataSource. |
| Hai persistence unit với hai DataSource | Thường có hai pool độc lập. | Cộng cả hai nếu chúng cùng đích DB. |
| Spring Batch metadata và writer | Có thể dùng chung hoặc hai DataSource khác nhau. | Xác định bean thật; tính thêm pool riêng và worker đang chạy. |
| Quartz JDBC JobStore | Có thể có DataSource/pool cho metadata scheduler. | Cộng vào ngân sách nếu dùng cùng database. |
| Spring Integration JDBC poller | Thường dùng DataSource được inject. | Tính tải/concurrency; chỉ cộng pool mới nếu có DataSource riêng. |
| Flyway/Liquibase/migration tool | Có thể mở kết nối ngắn và riêng. | Chừa ngân sách vận hành ở thời điểm deployment. |

Với **read replica**, phải tính ngân sách cho từng nơi nhận kết nối. Replica có giới hạn kết nối riêng hoặc tài nguyên riêng, nhưng một proxy ở phía trước có thể áp mức trần khác; xem cấu hình thực tế thay vì xem “read-only” như miễn phí.

## 7. Giới hạn số việc đồng thời trước khi chúng giữ connection

Pool là rào chắn cuối, **không phải cơ chế điều tiết mọi luồng vào**. Nếu hàng nghìn request đi vào, mỗi request đợi checkout 1,5 giây rồi timeout, ứng dụng vẫn có thể bị quá tải thread và bộ nhớ. Thiết kế nên giới hạn concurrency theo khả năng thực tế ở tầng xử lý:

~~~mermaid
flowchart LR
    A["HTTP / Kafka / RabbitMQ / Batch"] --> B{"Admission / backpressure"}
    B -->|"Đủ năng lực"| C["Service transaction ngắn"]
    B -->|"Quá tải"| X["Từ chối/hoãn/queue bền vững"]
    C --> D["Hikari pool"]
    D --> E[("Database")]
    E --> F["Trả connection về pool"]
~~~

Cách làm:

1. **HTTP:** dùng concurrency limit, rate limit, timeout và trả lỗi có kiểm soát khi không thể nhận thêm việc. Không tạo thread vô hạn để chờ pool.
2. **Consumer broker:** chỉnh listener concurrency, prefetch/poll batch, worker pool và ack theo tốc độ DB thực; đừng để consumer nhận nhiều hơn số việc có thể xử lý.
3. **Spring Batch:** giới hạn số JobExecution/partition/thread đồng thời. Một step với 20 worker không nhất thiết cần pool 20, nhưng khi mỗi worker giữ connection trong thời gian dài phải tính concurrency thực tế.
4. **Spring Integration:** `ExecutorChannel` hoặc poller có thể làm tăng số handler chạy đồng thời. Chọn executor có giới hạn queue và concurrency; `QueueChannel` trong bộ nhớ không tự cung cấp độ bền qua restart.
5. **Scheduled jobs:** tránh cron trùng giữa nhiều replica hoặc chạy chồng lô; dùng JobRepository/Quartz cluster/distributed lock theo phạm vi nghiệp vụ.

Nếu DB đang nghẽn, **giảm số công việc đang thực thi** có thể giúp throughput và latency tốt hơn so với tăng `maximumPoolSize`. Phải đặt backpressure trước những bước có side effect để không bỏ mất công việc đã hứa xử lý; nếu dùng queue, chọn storage bền vững và chính sách timeout/retry/DLQ rõ ràng.

### 7.1. Tránh giữ transaction khi gọi hệ thống ngoài

~~~java
// Ví dụ phản diện: transaction DB có thể bị giữ khi chờ HTTP.
@Transactional
public void confirmOrder(UUID orderId) {
    OrderEntity order = repository.findById(orderId).orElseThrow();
    paymentClient.authorize(orderId); // HTTP có thể mất nhiều giây
    order.confirm();
}
~~~

Tùy JPA provider và thời điểm checkout, connection có thể bị giữ trong phần lớn thời gian transaction. Với 12 connection/pod, chỉ cần 12 transaction bị chặn lâu là pool đã cạn dù SQL thực thi rất ít. Đồng thời rollback DB **không** đảo ngược thanh toán đã được phía HTTP xử lý.

Một thiết kế phù hợp hơn cho tác vụ có thể kéo dài là transaction ngắn để lưu trạng thái `PENDING` và **transactional outbox**, rồi consumer gọi đối tác và xác nhận trạng thái ở transaction khác. Với yêu cầu đồng bộ, vẫn nên có deadline, giới hạn concurrency và ranh giới transaction nhỏ, không để HTTP chậm giữ connection không cần thiết.

### 7.2. Cẩn thận với giao dịch lồng nhau và `REQUIRES_NEW`

Khi một transaction đã giữ connection rồi gọi phương thức `@Transactional(propagation = REQUIRES_NEW)`, giao dịch mới có thể cần **connection thứ hai** trong khi connection cũ vẫn bị giữ. Nhiều thread cùng làm vậy có thể đợi nhau và làm pool thiếu connection dù mỗi thread bình thường chỉ “dùng một kết nối”.

Ưu tiên thiết kế lại ranh giới giao dịch, tránh nhiều transaction lồng nhau giữ nhiều connection cùng lúc. Nếu thật sự cần giao dịch lồng nhau độc lập, phải tính số connection được giữ đồng thời theo từng worker khi sizing và kiểm thử điều kiện saturation. Không chỉ lấy số request thread làm pool size rồi kỳ vọng luôn đủ.

## 8. Connection pool và transaction không tạo ra kết nối “miễn phí”

Một số câu hỏi thực tế:

**Pool dùng chung giữa nhiều bean có bị nhân đôi không?** Không. Nếu `JdbcTemplate`, repository JPA và jOOQ đều inject cùng một `DataSource` và pool được quản lý đúng, chúng dùng chung giới hạn `maximumPoolSize` của pool đó. Vẫn phải tính **nhu cầu cạnh tranh** giữa các thành phần.

**Một DataSource có thể tạo nhiều pool không?** Có thể nếu application context vô tình tạo nhiều bean Hikari cùng JDBC URL, hoặc thư viện tự tạo DataSource khác. Kiểm tra bean thực tế và metrics; đừng dựa vào tên database trùng để kết luận chỉ có một pool.

**Idle connection có tính vào giới hạn DB không?** Có. Kết nối idle thường vẫn là một backend session đang mở và chiếm slot tại database server cho đến khi đóng.

**Một instance có `maximumPoolSize=12` có luôn mở đủ 12 connection không?** Không nhất thiết. Hikari có thể bắt đầu với số connection nhỏ và mở theo tải, tùy `minimumIdle`, thời điểm khởi tạo và trạng thái pool. Nhưng **12 vẫn là mức trần cần dự trù**.

**Tăng connection pool có chữa query chậm?** Thường không nếu bottleneck nằm ở lock, index, disk hoặc CPU database. Khi connection acquisition wait cao nhưng active connection cũng cao, cần điều tra **tại sao connection bị giữ lâu** trước khi tăng pool.

## 9. Quan sát PostgreSQL và HikariCP để tìm đúng nút nghẽn

### 9.1. Kiểm tra giới hạn PostgreSQL

Có thể dùng SQL **chỉ đọc** để xem giới hạn kết nối của instance:

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;

-- Xem các tham số reservation có mặt trên phiên bản đang dùng:
SELECT name, setting
FROM pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
~~~

Một số version PostgreSQL có tham số `reserved_connections` bổ sung, một số không; truy vấn `pg_settings` giúp kiểm tra thông số có thực sự tồn tại. Trên managed PostgreSQL, cần xét thêm giới hạn dịch vụ, proxy, các role có quyền khác nhau và những connection phục vụ vận hành.

Đếm backend theo ứng dụng và trạng thái:

~~~sql
SELECT
    COALESCE(application_name, '') AS application_name,
    COALESCE(state, 'unknown') AS state,
    COUNT(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY 1, 2
ORDER BY connections DESC, application_name;
~~~

Trong driver PostgreSQL JDBC, `ApplicationName` có thể được gắn bằng property của DataSource. Một tên ổn định như `orders-service` giúp nhóm session; muốn phân biệt theo pod, nên gắn thông tin vào log/telemetry hoặc cách đặt tên được kiểm soát, tránh làm metric có cardinality không giới hạn.

Để tìm session giữ transaction mở quá lâu:

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 30;
~~~

SQL này cần quyền quan sát phù hợp. `idle in transaction` rất đáng chú ý: session có thể giữ lock/snapshot dù không thực thi truy vấn. Không hủy backend hàng loạt theo query trên; phải kiểm tra chủ sở hữu và ảnh hưởng transaction trước khi dùng công cụ quản trị.

### 9.2. Metrics Hikari cần xem đồng thời

Với `spring-boot-starter-actuator` và Micrometer được cấu hình, có thể theo dõi các số liệu Hikari như:

- `hikaricp.connections.active`: connection đã checkout.
- `hikaricp.connections.idle`: connection đang nhàn trong pool.
- `hikaricp.connections.pending`: thread chờ lấy connection.
- `hikaricp.connections.max` và `hikaricp.connections.min`: giới hạn tương ứng.
- `hikaricp.connections.timeout`: số lần chờ checkout quá hạn, theo cách metric được xuất.
- Connection acquire/usage/creation time nếu exporter/hệ sinh thái đang dùng cung cấp.

Tên và loại metric có thể khác theo phiên bản Micrometer/registry; kiểm tra endpoint Actuator/Prometheus thực tế. Đặt nhãn theo **pool name, service, môi trường**, tránh nhãn theo từng SQL, user ID hoặc request ID.

| Dấu hiệu | Diễn giải khả dĩ | Hướng xử lý đầu tiên |
| --- | --- | --- |
| Active ≈ max, pending tăng | Pool hết khả năng cấp connection. | Kiểm tra checkout duration, transaction, query chậm, lock và số worker đồng thời. |
| Active cao, DB CPU thấp | Connection bị giữ khi chờ HTTP, lock hoặc code không thực thi SQL. | Truy stack trace, `idle in transaction`, đuôi transaction. |
| DB `too many clients already` nhưng mỗi pod chưa đầy | Nhiều pod/pool/ứng dụng cùng tạo quá nhiều session. | Tổng hợp toàn cụm và kiểm tra pool surge sau rollout. |
| Acquisition timeout tăng sau khi scale | Connection mới không mở được hoặc cạnh tranh DB tăng. | Kiểm tra `max_connections`, network/TLS, bootstrap và maxSurge. |
| Idle quá cao trên nhiều replica | Mỗi pool giữ nhiều connection dự phòng, gây chiếm slot. | Đánh giá `minimumIdle`, pool count, replica count và tải giờ thấp điểm. |
| Connection đang dùng rất lâu | Transaction/leak hoặc công việc quá dài. | Trace checkout, query timeout, transaction scope và leak detection có kiểm soát. |

## 10. Lỗi kết nối thường gặp và cách chẩn đoán

### 10.1. `Connection is not available, request timed out after ...`

Đây thường là **timeout lấy connection từ pool Hikari**, không nhất thiết là database đã chết. Trình tự điều tra:

1. Xem active/idle/pending/max của đúng pool và pod tại thời điểm lỗi.
2. Nếu active ≈ max: tìm transaction lâu, query đang chờ lock hoặc đường code không trả connection.
3. Nếu connection mới không tạo được: xem DB log, auth/TLS/network, limit session và số pool tăng đột biến.
4. Đối chiếu khoảng thời gian với lịch Spring Batch, Kafka consumer rebalance, đợt cache miss lớn hoặc rollout.
5. Chỉ điều chỉnh pool sau khi đã kiểm tra tổng ngân sách toàn cụm và năng lực DB.

### 10.2. PostgreSQL báo `too many clients already`

Lỗi cho thấy database không còn chỗ cho kết nối mới của caller với quyền hiện tại. Nếu tổng pool cap của các ứng dụng vượt `max_connections` khả dụng, việc tăng `connectionTimeout` ở Hikari chỉ khiến caller chờ lâu hơn; nó không làm tăng số connection ở PostgreSQL.

Cần giảm tổng pool cap, số pod cùng kết nối, thời gian giữ connection hoặc chuyển một phần traffic tới kiến trúc thích hợp; nếu muốn tăng `max_connections`, phải đánh giá RAM, CPU, hệ điều hành và khả năng xử lý thực tế của database. Trên managed DB, tham số này có thể liên quan kích thước instance và yêu cầu restart/maintenance.

### 10.3. Connection leak và connection giữ quá lâu

Trong JDBC thuần, thiếu `try-with-resources` có thể không trả connection. Với Spring, các API quản lý tài nguyên thường trả connection thông qua template/transaction infrastructure, nhưng code tự lấy `dataSource.getConnection()` phải đóng đúng cách:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

public long countOrders(DataSource dataSource) throws Exception {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT COUNT(*) FROM orders");
         ResultSet rows = statement.executeQuery()) {
        rows.next();
        return rows.getLong(1);
    }
}
~~~

Nếu tham gia transaction do Spring quản lý, nên ưu tiên `JdbcTemplate`/JPA hoặc cơ chế lấy connection có ý thức về transaction thay vì tự quản lý connection mà phá ranh giới của Spring. Hikari có `leakDetectionThreshold` để log connection checkout lâu hơn ngưỡng; đây là **tín hiệu chẩn đoán**, không chứng minh leak thực sự và không tự đóng connection. Đặt ngưỡng phù hợp để tránh báo động giả với job hợp lệ chạy lâu; không bật log chi tiết nhạy cảm một cách vô hạn.

## 11. PgBouncer/RDS Proxy và giới hạn kết nối theo lớp

Khi số replica lớn hoặc ứng dụng tạo nhiều kết nối nhàn rỗi, có thể xem xét **connection pooler/proxy phía database** như PgBouncer hoặc proxy do nhà cung cấp quản lý. Khi đó cần tính **hai ngân sách**:

1. Số connection từ ứng dụng tới pooler/proxy.
2. Số server connection thực tế từ pooler/proxy tới database.

Ví dụ: 20 pod, mỗi pod có Hikari tối đa 10 ⇒ có thể tạo **200 connection phía client của pooler**, nhưng pooler có thể chỉ dùng **50 server connection** được chia sẻ theo cấu hình và tải. Điều này giảm số backend session đồng thời ở database, nhưng **không tạo thông lượng vô hạn**: giao dịch chờ slot tại pooler vẫn chịu timeout.

| Chế độ/khía cạnh | Điểm cần chú ý |
| --- | --- |
| **Session pooling** | Server connection được gắn với client lâu hơn; giảm hiệu quả multiplexing nhưng phù hợp hơn với state theo session. |
| **Transaction pooling** | Server connection có thể được tái sử dụng giữa các client sau mỗi transaction. | Không thể mặc định dựa vào session state tồn tại giữa các transaction. |
| **Prepared statements** | Khả năng tương thích phụ thuộc JDBC driver, phiên bản PgBouncer và cấu hình hỗ trợ prepared statement. | Test thực tế, không kết luận tất cả cấu hình đều hoạt động hoặc đều hỏng. |
| **Temporary tables, session variables, advisory locks** | Các cơ chế gắn với session có thể không hoạt động như mong đợi nếu chuyển server connection giữa transactions. | Xem lại cách dùng, scope hoặc chọn session pooling. |
| **Transaction dài** | Giữ server connection của pooler trong suốt transaction. | Proxy không chữa được việc ứng dụng giữ transaction khi chờ I/O ngoài. |

JPA/Hibernate, Spring Batch và driver có thể tạo prepared statement hoặc giữ transaction theo cách đặc biệt. Trước khi chuyển transaction pooling, chạy thử transaction, batch writer, migration, lock và các chức năng dùng session state. Không giảm pool ở app chỉ vì thấy có proxy mà quên kiểm tra pooler saturation và SLA của database.

## 12. Cân chỉnh pool khi triển khai và autoscale

### 12.1. Quy trình thay đổi cấu hình có kiểm soát

1. **Đo baseline** trong giờ cao điểm: số pod, các pool thực tế, active/pending, checkout time, DB sessions, CPU, I/O, lock waits và độ trễ ứng dụng.
2. **Lập bảng ngân sách** cho từng database instance/proxy, bao gồm các service khác, Batch, Quartz, migration và rolling surge.
3. **Chọn cap bảo thủ**, thử với concurrency được giới hạn; không tăng nhiều biến cùng lúc làm mất khả năng phân tích nguyên nhân.
4. **Load test** từ ít đến nhiều replica và bắt buộc thử kịch bản rolling update/autoscale ở tải cao.
5. **Theo dõi hậu triển khai**, đặc biệt số connection trong vài phút đầu khi nhiều pod khởi động, startup probes và batch chạy.
6. **Có phương án giảm tải/rollback** nếu DB hoặc pooler không đáp ứng, không phụ thuộc việc tăng `max_connections` khẩn cấp.

### 12.2. Ví dụ giới hạn theo một deployment

~~~yaml
# Trích đoạn cấu hình Kubernetes, không phải manifest đầy đủ.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
          env:
            - name: ORDERS_DB_POOL_MAX
              value: "12"
~~~

Trong ví dụ, `replicas: 6` và `maxSurge: 2` cho phép xét **8 pod** trong quá trình rollout. Giá trị thực phải tính thêm HPA, canary, blue-green và các deployment khác. **Các thông số này không tự chặn tổng connection**: nếu người vận hành tăng HPA hoặc tạo thêm worker deployment, ngân sách phải cập nhật theo.

**Tránh bão kết nối lúc khởi động:** Nếu 50 pod tạo nhiều connection cùng lúc để khởi tạo JPA metadata hoặc chạy health check, database có thể bị nghẽn dù tải request chưa tăng. Có thể dùng rollout có nhịp, readiness probe đúng, pool warm-up phù hợp và tách migration thành một tác vụ được điều phối thay vì để mọi pod cùng migrate.

## 13. Kiểm thử giới hạn kết nối dưới các điều kiện lỗi

Một bài load test cần đo **connection mà database thực sự nhận**, không chỉ số request trả thành công.

| Kịch bản | Điều mong đợi |
| --- | --- |
| Chạy một pod ở tải bình thường | Active/idle/pending phù hợp, không cần pool lớn chỉ vì nhiều HTTP threads. |
| Tăng tới mức HPA tối đa | Tổng connection của các pool không vượt ngân sách đích theo mô hình. |
| Rolling update khi đang có tải cao | Pod cũ + pod mới không làm tràn DB connection, readiness ổn định. |
| Đồng thời chạy Spring Batch và Quartz | Các pool bổ sung được tính; API không bị starvation khi job khởi động. |
| Chạy 2 persistence unit cùng một PostgreSQL | Cộng pool cả hai unit, không đếm sai theo tên schema. |
| DB query chậm gấp 10 lần | Pending tăng được quan sát, admission/backpressure hoạt động trước khi tràn thread. |
| Nhiều request timeout chờ checkout | Ứng dụng trả lỗi có kiểm soát, không retry tức thì vô hạn vào DB. |
| HTTP downstream chậm bên trong transaction | Phát hiện connection giữ lâu; refactor giảm thời gian giữ transaction. |
| Connection bị leak trong code JDBC tự viết | Metrics và leak detection có tín hiệu, bộ kiểm thử không bỏ qua việc đóng connection. |
| DB failover hoặc network partition | Pool phục hồi connection hỏng theo cơ chế thích hợp, không tạo reconnect storm vô hạn. |
| Thay đổi `minimumIdle` khi giờ thấp điểm | Kiểm chứng số idle thực tế và ảnh hưởng mở connection lúc burst tiếp theo. |
| PgBouncer transaction pooling | Kiểm thử prepared statements, state theo session, transaction JPA và batch writer. |

Với Spring Boot, có thể dùng `@SpringBootTest` cùng Testcontainers PostgreSQL, Micrometer/Actuator và công cụ tạo tải ở lớp HTTP hoặc broker. Đối với kịch bản **nhiều pod thật**, test một JVM không đủ; dùng một môi trường có cùng topology để xác minh tổng số session/connection tại database.

Đừng tắt giới hạn `max_connections` trên môi trường test rồi kết luận cấu hình an toàn. Nên mô phỏng giới hạn sát production theo tỷ lệ, đồng thời chỉ tạo tải trên database hoặc sandbox đã được phép.

## 14. Runbook sự cố: pool cạn khi tăng replica

Giả sử sau rollout, API trả 503 hàng loạt và log Hikari xuất hiện `Connection is not available, request timed out`:

1. **Khoanh vùng:** API nào lỗi, deployment nào vừa tăng pod, pool nào hết connection, DB nào đang sát trần.
2. **Ngăn khuếch đại:** giới hạn admission/concurrency, tạm dừng job ít ưu tiên, không cho retry storm; tránh scale thêm pod chỉ vì CPU ứng dụng tăng nếu DB đã quá tải.
3. **Xác minh quota:** lấy `max_connections` và session theo `application_name`, cộng tổng cap của tất cả pod/pool gồm batch và rollout surge.
4. **Kiểm tra thời gian giữ connection:** active/max, pending, slow query, lock wait, `idle in transaction` và đường code gọi HTTP trong transaction.
5. **Chọn cách giảm rủi ro:** giảm số worker/consumer, giảm pool quá mức, chuyển việc không khẩn sang queue hoặc thu hẹp rollout; tăng năng lực DB chỉ theo kế hoạch vận hành.
6. **Đối soát side effect:** nếu request timeout sau khi DB đã commit hoặc bên ngoài đã xử lý, dùng operation ID/idempotency thay vì retry ghi dữ liệu không kiểm soát.
7. **Phục hồi và kiểm thử lại:** mở traffic theo nhịp, theo dõi tổng session, pending và p95/p99; cập nhật ngân sách pool thành quy tắc deploy.

Nếu sự cố do query chậm hoặc lock, giảm pool có thể làm giảm tranh chấp tạm thời nhưng không thay thế tối ưu SQL/index và sửa transaction scope. Nếu do tổng số replica vượt quota, tăng pool từng pod gần như chắc chắn làm vấn đề nặng hơn.

## 15. Checklist trước khi thay đổi pool hoặc tăng replica

- [ ] Biết giới hạn kết nối **thực tế** tại database/proxy và số slot dành cho quản trị, hệ thống khác và dự phòng.
- [ ] Có danh sách toàn bộ pool đi vào từng database: JDBC, JPA, jOOQ, Batch, Quartz, adapter, migration và worker phụ.
- [ ] Đã tính **số pod đồng thời tối đa** gồm HPA, rolling update, canary/blue-green và nhiều cluster.
- [ ] Tổng `N_peak × maximumPoolSize` của mọi pool cùng đích không vượt ngân sách đã thống nhất.
- [ ] Kích thước pool được kiểm chứng bằng QPS, checkout duration, DB CPU/I/O/lock và p95/p99, không chỉ số thread.
- [ ] `minimumIdle`, `connectionTimeout`, `maxLifetime` và các timeout JDBC/SQL/deadline phù hợp với môi trường thực.
- [ ] Không giữ connection/transaction khi chờ HTTP hoặc tác vụ ngoài; các bước `REQUIRES_NEW` đã được xem xét.
- [ ] Có concurrency limit/backpressure cho HTTP, consumer, scheduler và Spring Batch.
- [ ] Metrics Hikari, `pg_stat_activity`, dashboard và alert cho pending/timeout/session saturation đã được thiết lập.
- [ ] Có load test đa replica, rollout trên giờ cao điểm, DB failover và phương án giảm tải/rollback.

**Kết luận:** Connection pool tối ưu không phải pool lớn nhất mà mỗi pod có thể mở, mà là pool **đủ nhỏ để toàn cụm không vượt năng lực database và đủ lớn cho workload đã đo**. Trong Spring Boot Integration, giới hạn HikariCP phải được nhìn cùng với số replica, nhiều DataSource, Batch/Quartz, luồng broker, transaction và độ trễ các hệ thống đích. Chỉ khi quản lý đồng thời ngân sách kết nối, thời gian giữ connection, backpressure và cách phục hồi sau lỗi, hệ thống mới có thể scale mà không gây quá tải dây chuyền lên SQL database.
