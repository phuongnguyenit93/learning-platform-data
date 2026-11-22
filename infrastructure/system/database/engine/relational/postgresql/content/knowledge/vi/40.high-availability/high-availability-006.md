# Định tuyến kết nối ghi, đọc và làm mới connection pool

Trong hệ thống PostgreSQL có primary và một hoặc nhiều standby, ứng dụng cần gửi thao tác ghi tới primary, đồng thời có thể phân phối các truy vấn đọc phù hợp sang standby để tăng khả năng phục vụ và giảm tải. Việc định tuyến này phải phối hợp với connection pool: pool giữ các kết nối đã mở trong thời gian dài, trong khi vai trò server, địa chỉ endpoint, trạng thái failover và độ trễ replication có thể thay đổi.

Một kiến trúc hoạt động tốt phải trả lời được ba câu hỏi:

1. **Kết nối nào nhận writes, kết nối nào nhận reads?** Phân loại theo transaction semantics, không chỉ nhìn từ khóa SELECT.
2. **Khi nào một read được phép chạy trên replica?** Cần xét replication lag, read-after-write consistency và yêu cầu dữ liệu mới nhất.
3. **Làm sao pool bỏ kết nối cũ và tạo kết nối mới?** Phải có health checks, connection lifetime, DNS refresh, eviction, retry có kiểm soát và quy trình drain khi failover.

Bài học này trình bày các mô hình định tuyến ở application, proxy và driver; thiết kế write/read endpoints; cách dùng PgBouncer và PostgreSQL connection parameters; các chế độ pooling; làm mới pool sau failover hoặc thay đổi endpoint; cùng monitoring, troubleshooting và runbooks. Trọng tâm là PostgreSQL trong môi trường high availability, nơi routing và connection lifecycle ảnh hưởng trực tiếp tới tính đúng đắn của ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt primary endpoint, read endpoint, standby endpoint và pooler endpoint.
2. Thiết kế write/read routing ở application hoặc proxy.
3. Phân loại transaction theo read-only/write semantics.
4. Xử lý read-after-write và stale reads do asynchronous replication.
5. Hiểu health check để phân biệt primary với standby.
6. Sử dụng libpq connection parameters như target_session_attrs.
7. Giải thích session, transaction và statement pooling.
8. Chọn pool size, connection lifetime và timeout phù hợp.
9. Làm mới connection pool sau failover, DNS change hoặc certificate rotation.
10. Drain connections an toàn và tránh pool tiếp tục dùng endpoint cũ.
11. Thiết kế retry/idempotency khi connection bị ngắt giữa transaction.
12. Theo dõi pool saturation, replication lag, routing distribution và connection errors.
13. Xây dựng runbooks và kiểm thử routing/failover bằng tình huống thực tế.

> **Phiên bản:** Các ví dụ dùng PostgreSQL và PgBouncer phổ biến. Cú pháp, tính năng pooling và health-check commands phụ thuộc phiên bản/tool. Driver Java, .NET, Go, Python và các framework có APIs khác nhau; luôn xác nhận tài liệu đúng phiên bản trước khi đưa cấu hình vào production.

## 2. Vì sao phải định tuyến reads và writes?

Trong physical replication, primary nhận writes và tạo WAL; standby nhận/replay WAL. Standby có thể phục vụ read-only queries khi hot standby hoạt động. Nếu mọi truy vấn đều đi primary, standby không giúp giảm tải đọc. Nếu writes bị gửi nhầm tới standby, PostgreSQL sẽ từ chối vì standby đang recovery/read-only.

Mô hình cơ bản:

```text
                     Application
                          |
                    Routing layer
                     /         \
              WRITE endpoint   READ endpoint
                    |               |
                    v               v
               PostgreSQL        PostgreSQL
                PRIMARY           STANDBY
                    |               ^
                    +---- WAL ------+
```

### Lợi ích của read routing

- Tách một phần SELECT workload khỏi primary.
- Dùng nhiều replicas để tăng read throughput.
- Cô lập workload analytics/reporting khỏi giao dịch ghi.
- Tận dụng standby ở region khác cho một số reads gần người dùng.

### Chi phí và giới hạn

- Replica có thể lag so với primary.
- Read-after-write không tự bảo đảm.
- Failover có thể làm đổi vai trò server.
- Mỗi endpoint/pool có connection budget riêng.
- Query routing sai có thể làm transaction không nhất quán.

Read scaling là tối ưu có điều kiện; không phải mọi truy vấn đọc đều phù hợp chạy trên replica.

## 3. Các endpoint thường gặp

| Endpoint | Mục đích | Hành vi mong muốn |
|---|---|---|
| Primary/write endpoint | Giao dịch ghi và reads cần dữ liệu mới nhất | Luôn trỏ tới primary hiện tại |
| Read endpoint | Truy vấn đọc có thể chấp nhận lag | Phân phối tới standby đủ khỏe |
| Per-replica endpoint | Chọn một standby cụ thể | Dùng cho workload/region riêng |
| Pooler endpoint | Nhận client connections rồi cấp server connections | Tách client lifecycle khỏi PostgreSQL sessions |
| Admin endpoint | Migration, monitoring, failover operations | Quyền truy cập hạn chế, không dùng chung app pool |

### Endpoint không nhất thiết là một server

Một DNS name, VIP, load balancer hoặc proxy có thể đại diện cho một nhóm PostgreSQL nodes. Endpoint chỉ là địa chỉ kết nối; thành phần đứng sau phải xác định node nào hiện là primary hoặc standby.

### Không dùng một read-write endpoint không có role awareness

Nếu load balancer phân phối mọi TCP connection ngẫu nhiên tới primary và standby, ứng dụng có thể gửi writes vào standby hoặc reads cần mới nhất vào một replica lag. Routing cần biết vai trò và policy của từng node.

## 4. Những lớp có thể thực hiện routing

### Application-side routing

Ứng dụng giữ hai data sources/pools: write pool trỏ primary endpoint, read pool trỏ read endpoint. Application/service layer chọn pool theo transaction intent.

Ưu điểm:

- Business logic biết transaction có cần read-after-write hay không.
- Dễ gắn consistency policy với từng use case.
- Có thể pin một transaction vào cùng connection.

Nhược điểm:

- Mỗi service phải triển khai routing đúng.
- Dễ phát sinh logic không nhất quán giữa các ứng dụng.
- Cần vận hành nhiều pools/endpoints.

### Proxy-side routing

Proxy nhận connection/query rồi chuyển tới PostgreSQL nodes. Một số proxy có thể kiểm tra node role và route theo rules; khả năng phân loại SQL, transaction và session state phụ thuộc sản phẩm.

Ưu điểm:

- Tập trung routing và health checks.
- Có thể cung cấp endpoint ổn định cho nhiều ứng dụng.
- Có thể che bớt topology.

Nhược điểm:

- Proxy trở thành thành phần quan trọng cần HA/monitoring.
- Query classification có thể sai với stored procedures, functions hoặc multi-statement transactions.
- Session semantics và prepared statements có thể bị giới hạn.

### Driver/connection string routing

Một số driver có thể thử nhiều hosts và chọn server theo target session attributes. Cách này hữu ích để chọn node lúc mở connection, nhưng thường không phân loại từng câu SQL sau khi connection đã được tạo.

## 5. Routing theo transaction semantics

Không nên phân loại query chỉ bằng cách xem câu SQL có bắt đầu bằng SELECT hay không. Một SELECT có thể gọi function có side effects, gọi sequence, hoặc phụ thuộc session state. Một transaction có thể đọc trước rồi ghi sau.

Phân loại thực tế:

| Loại workload | Endpoint phù hợp |
|---|---|
| INSERT/UPDATE/DELETE/MERGE | Primary |
| DDL và migrations | Primary |
| SELECT cần thấy write vừa commit | Primary hoặc replica đã replay tới commit LSN |
| SELECT chấp nhận eventual consistency | Standby |
| Reporting/analytics có thể chịu lag | Standby được chỉ định |
| Transaction đọc rồi ghi | Primary từ đầu transaction |
| Advisory locks/session state liên quan writes | Thường primary và session affinity |

### Quy tắc an toàn

Nếu transaction có khả năng ghi, hãy chọn primary ngay từ đầu và giữ cùng transaction/connection. Không bắt đầu trên replica rồi chuyển nửa chừng sang primary; transaction snapshot và locks không được chuyển theo connection.

### SELECT không luôn read-only

Một SELECT có thể gọi function thay đổi dữ liệu hoặc sequence. Hot standby chặn nhiều thao tác ghi, nhưng routing layer không nên dựa vào SQL prefix để quyết định transaction an toàn. Dùng application intent, read-only transaction semantics và kiểm thử functions.

## 6. Tách read pool và write pool trong ứng dụng

Một application có thể khai báo hai data sources:

```text
WriteDataSource
  jdbc:postgresql://pg-primary.service:5432/appdb
  maxPoolSize: 20

ReadDataSource
  jdbc:postgresql://pg-read.service:5432/appdb
  maxPoolSize: 40
```

Ví dụ minh họa, không phải cấu hình mặc định. Pool size phải dựa trên tổng số application instances, số workers và connection budget PostgreSQL/PgBouncer.

### Routing ở service layer

```java
public Order createOrder(CreateOrderCommand command) {
    return writeTransaction.execute(status -> {
        Order order = orderRepository.insert(command);
        auditRepository.insert(order.id(), "CREATED");
        return order;
    });
}

public OrderView getOrder(long orderId) {
    return readRepository.findViewById(orderId);
}
```

Service biết rõ createOrder là write transaction và getOrder là read use case. Nếu endpoint cần đọc ngay sau khi tạo order, use case đó cần primary routing hoặc consistency token thay vì mặc định dùng read pool.

### Đừng để repository tự chọn tùy tiện

Một quy ước rõ ràng như ReadRepository/WriteRepository hoặc transaction annotation giúp reviewer nhìn thấy routing intent. Tránh để mỗi method tự suy đoán endpoint theo tên SQL.

## 7. Transaction pinning và connection affinity

Một transaction phải chạy trên một connection từ BEGIN tới COMMIT/ROLLBACK. Nếu transaction bắt đầu trên primary, mọi câu lệnh bên trong transaction phải ở cùng primary connection.

Ví dụ:

```sql
BEGIN;

UPDATE public.account
SET balance = balance - 100
WHERE account_id = 1;

SELECT balance
FROM public.account
WHERE account_id = 1;

COMMIT;
```

SELECT trong transaction này phải đọc cùng primary transaction để thấy thay đổi chưa commit của chính transaction. Không route SELECT sang standby.

### Autocommit và nhiều câu lệnh

Ở autocommit mode, mỗi statement có thể là một transaction riêng. Tuy nhiên, business workflow nhiều statements cần atomicity phải được quản lý như một transaction duy nhất và pin vào write connection.

## 8. Read-after-write consistency

Asynchronous standby có thể chưa replay transaction vừa commit trên primary. Ví dụ:

1. Ứng dụng INSERT order trên primary.
2. Transaction commit thành công.
3. Ứng dụng lập tức SELECT order từ read endpoint.
4. Replica chưa replay WAL tương ứng nên query không thấy order.

Đây là stale read do replication lag, không nhất thiết là mất dữ liệu.

### Các lựa chọn

- Đọc từ primary trong một khoảng thời gian sau write.
- Giữ request/session sticky về primary.
- Chờ replica replay tới một LSN token rồi đọc.
- Dùng synchronous replication với acknowledgment phù hợp nếu yêu cầu durability/visibility cho phép.
- Thiết kế UX/API chấp nhận eventual consistency và trả dữ liệu vừa ghi từ write result.

### Đừng dùng sleep cố định

Chờ 500 ms hoặc 2 giây không bảo đảm replica đã bắt kịp. Lag thay đổi theo workload, network và replay capacity. Nếu cần consistency, dùng primary routing hoặc LSN-based wait với timeout rõ ràng.

## 9. LSN-based read-after-write

PostgreSQL có thể so sánh LSN trên primary và standby. Sau khi transaction commit trên primary, ứng dụng có thể lấy một LSN token ở hoặc sau commit point, rồi chờ standby replay tới token đó.

Ví dụ khái niệm trên primary sau COMMIT:

```sql
SELECT pg_current_wal_lsn() AS consistency_lsn;
```

Trên standby:

```sql
SELECT
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn
    AS replayed_to_target;
```

Trong ứng dụng, lặp kiểm tra với deadline/backoff và chỉ đọc replica khi điều kiện đạt. LSN ví dụ phải được thay bằng token thực tế từ primary.

### Giới hạn

- Token phải thuộc đúng timeline/history liên quan.
- Nếu failover xảy ra, cần xử lý timeline mới và xác định consistency boundary.
- LSN token lấy sau commit có thể bao gồm cả WAL từ transaction khác; điều đó an toàn nhưng có thể chờ lâu hơn.
- Nếu timeout, fallback về primary hoặc trả response theo consistency contract.

Không tự so sánh LSN giữa các cluster độc lập hoặc các histories không tương thích.

## 10. Synchronous replication và read visibility

Synchronous replication có nhiều mức acknowledgment. synchronous_commit=on thường đợi synchronous standby flush WAL; remote_apply đợi standby replay transaction trước khi primary báo commit thành công, khi synchronous standby được cấu hình đúng.

Ví dụ cấu hình minh họa:

```ini
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

Transaction có thể chọn:

```sql
SET LOCAL synchronous_commit = 'remote_apply';
```

### Không đánh đồng synchronous với routing

Synchronous replication xác định mức chờ khi commit. Nó không tự định tuyến SELECT của ứng dụng sang đúng standby đã acknowledge, cũng không thay thế endpoint/health checks. Nếu có nhiều standbys, cần xác định node nào đáp ứng synchronous policy và read endpoint có thể chọn node nào.

### Trade-off

remote_apply có thể tăng commit latency. Chỉ dùng khi yêu cầu consistency/durability biện minh cho chi phí và failover behavior đã được kiểm thử.

## 11. Replication lag ảnh hưởng read routing

Read endpoint nên chọn các replicas đáp ứng policy, ví dụ:

- Đang kết nối và ở recovery mode.
- WAL receiver hoạt động nếu dùng streaming.
- Replay lag dưới ngưỡng.
- Không quá tải CPU/I/O.
- Không bị pause/recovery conflict kéo dài.

### Byte lag và time lag

LSN distance phản ánh lượng WAL address chưa replay; timestamp lag phản ánh thời điểm transaction gần nhất được replay. Trên primary idle, timestamp có thể cũ mà replica không thực sự lag. Dùng nhiều metrics thay vì một con số.

### Ngưỡng lag

Ngưỡng phụ thuộc use case. Dashboard/reporting có thể chấp nhận vài phút; màn hình trạng thái giao dịch có thể cần primary hoặc lag rất thấp. Đặt threshold theo consistency contract của sản phẩm.

## 12. Health check cho primary và standby

TCP port mở hoặc SELECT 1 thành công chỉ chứng minh server nhận kết nối và query đơn giản. Nó không xác định node có phải primary hay replica.

Kiểm tra role:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    current_setting('transaction_read_only') AS transaction_read_only;
```

Primary candidate thường có pg_is_in_recovery() = false; standby thường có true.

### Kiểm tra writable thật sự

Một primary có thể ở ngoài recovery nhưng vẫn bị cấu hình read-only hoặc user thiếu quyền ghi. Health check có thể kết hợp:

- pg_is_in_recovery().
- transaction_read_only.
- Authentication bằng role health-check có quyền phù hợp.
- Một kiểm tra nhẹ không tạo dữ liệu hoặc một probe table chuyên dụng trong môi trường kiểm soát.

Không thực hiện INSERT/ROLLBACK probe trên mỗi health check nếu tần suất cao và không cần thiết.

### Read endpoint health

Đảm bảo node ở recovery/hot standby và replay progress nằm trong ngưỡng. Một replica đang recovery nhưng bị lag hàng giờ không nên nhận mọi reads mặc định.

## 13. Routing bằng libpq target_session_attrs

libpq hỗ trợ target_session_attrs để chọn host trong danh sách nhiều hosts dựa trên thuộc tính session. Ví dụ:

```text
host=pg1.internal,pg2.internal
port=5432
dbname=appdb
user=app_user
target_session_attrs=read-write
```

read-write yêu cầu connection tới server chấp nhận read-write transactions. Với client cần standby/read-only server, có thể dùng read-only hoặc standby tùy driver/version và semantics được hỗ trợ.

### primary và standby attributes

Các giá trị được libpq hỗ trợ có thể bao gồm any, read-write, read-only, primary, standby và prefer-standby; tập giá trị và hành vi phụ thuộc phiên bản. Kiểm tra tài liệu libpq của PostgreSQL đang dùng.

### Giới hạn

target_session_attrs chọn server khi tạo connection. Nó không phân tích từng query để tự route SELECT/UPDATE khác nhau trên cùng một connection. Connection đã mở sẽ tiếp tục gắn với node đó cho đến khi đóng/reconnect.

## 14. Nhiều hosts trong connection string

Một connection string có thể liệt kê nhiều hosts để client thử lần lượt:

```text
host=pg-a.internal,pg-b.internal
port=5432,5432
dbname=appdb
user=app_user
connect_timeout=3
target_session_attrs=read-write
```

Driver sẽ thử các host và áp dụng target session attribute. Cấu hình này hữu ích khi cần tìm primary trong danh sách nodes.

### Không phải load balancing query

Sau khi chọn một host, connection vẫn gắn với host đó. Để phân phối nhiều read connections qua nhiều replicas, cần endpoint/proxy/load balancing strategy riêng hoặc driver feature phù hợp.

## 15. DNS và stable endpoints

DNS name có thể trỏ tới VIP, proxy hoặc endpoint do HA manager cập nhật khi failover. Ứng dụng nên dùng hostname ổn định thay vì hard-code IP của primary hiện tại.

### DNS caching

DNS record TTL không bảo đảm mọi process đổi IP đúng lúc. JVM, OS resolver, driver, pooler hoặc service mesh có thể cache DNS lâu hơn TTL. Connection pool giữ TCP sockets đã mở nên DNS update không làm các sockets đó tự chuyển node.

### Thiết kế

- Dùng DNS/VIP/HA endpoint do control plane quản lý.
- Đặt TTL phù hợp nhưng hiểu cache ở từng layer.
- Cấu hình resolver/client cache có chủ đích.
- Kết hợp health checks và connection eviction.
- Không coi DNS change là toàn bộ quy trình failover.

## 16. Read load balancing

Có thể phân phối reads qua nhiều standby bằng:

- Round-robin ở proxy/load balancer.
- Weighted routing theo capacity.
- Least-connections hoặc queue-aware routing.
- Region-aware routing.
- Application chọn replica theo workload.

### Cần tránh

- Route tới replica lag vượt ngưỡng.
- Dồn reporting queries dài vào replica phục vụ API latency thấp.
- Dùng cùng weight cho nodes có capacity rất khác nhau.
- Không có fallback khi tất cả replicas unhealthy.

### Weighted example

Nếu replica A có capacity gấp đôi replica B, có thể thử weight 2:1, sau đó điều chỉnh dựa trên CPU, I/O, active sessions và query latency thực tế. Weight không thay thế circuit breaker/health check.

## 17. Routing bằng PgBouncer

PgBouncer là connection pooler cho PostgreSQL. Nó giảm số server connections bằng cách tái sử dụng connections giữa nhiều client connections.

Một kiến trúc phổ biến dùng hai PgBouncer pools/endpoints:

```text
Application
   |                         |
   v                         v
pgbouncer-write          pgbouncer-read
   |                         |
   v                         v
primary endpoint         standby/read endpoint
```

PgBouncer tự nó chủ yếu pool connections theo database/user/pool mode; không mặc định phân tích mọi SQL và tự chọn primary/standby cho từng statement. Tách write/read endpoints hoặc kết hợp routing layer có role awareness.

### Hai listener

Có thể chạy hai PgBouncer services/configurations hoặc dùng proxy phía trước để cung cấp hai ports/hostnames. Mỗi pool phải có backend phù hợp và failover update process rõ ràng.

## 18. PgBouncer pooling modes

| Mode | Server connection được giữ tới khi | Đặc điểm |
|---|---|---|
| Session | Client disconnect | Tương thích session state tốt hơn, ít multiplexing |
| Transaction | Transaction kết thúc | Nhiều clients dùng chung server connections hiệu quả |
| Statement | Statement kết thúc | Hạn chế mạnh; không dùng multi-statement transactions |

### Session pooling

Client giữ một server connection trong suốt client session. Phù hợp ứng dụng dựa vào session state nhưng multiplexing ít hơn.

### Transaction pooling

Server connection được trả về pool sau mỗi transaction. Tăng hiệu quả connection sharing, nhưng session state không được bảo đảm tồn tại giữa hai transactions của cùng client.

### Statement pooling

Server connection được trả sau mỗi statement. Không phù hợp với transaction nhiều statements và nhiều ứng dụng thông thường.

## 19. Transaction pooling và session features

Trong transaction pooling, tránh phụ thuộc vào:

- Session-level SET kéo dài qua transaction.
- Temporary tables tồn tại qua nhiều transactions.
- Session-level advisory locks.
- LISTEN/NOTIFY listener sessions dài hạn.
- Cursors/portals sống ngoài transaction.
- Session variables hoặc state do extension giữ.
- Prepared statements nếu pooler/version/config chưa hỗ trợ semantics cần thiết.

### Giải pháp

- Dùng SET LOCAL trong transaction thay cho session-level SET khi phù hợp.
- Đặt search_path/role/timezone trong connection startup config được pooler hỗ trợ.
- Dùng session pooling cho workload cần session affinity.
- Tách listener/worker dedicated khỏi transaction pool.
- Test prepared statements theo PgBouncer version và max_prepared_statements.

Không chuyển sang transaction pooling chỉ để giảm connections nếu ứng dụng dựa vào session state mà chưa thay đổi code.

## 20. Cấu hình PgBouncer minh họa

Ví dụ cho một endpoint write:

```ini
[databases]
appdb = host=pg-primary.internal port=5432 dbname=appdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
reserve_pool_size = 5
server_idle_timeout = 600
server_lifetime = 3600
server_connect_timeout = 5
server_login_retry = 5
```

Đây là ví dụ minh họa, không phải file production hoàn chỉnh. Cần cấu hình authentication, TLS, admin users, userlist/auth_query, logging, DNS behavior và security policy theo môi trường.

Read endpoint có thể có cấu hình/backend riêng trỏ tới read service. Nếu proxy/HA manager thay backend sau failover, pooler cần reload/reconnect/drain theo quy trình đã kiểm thử.

## 21. PgBouncer admin console

PgBouncer có admin database để xem pools/servers/clients và thực hiện maintenance commands. Các lệnh thường dùng gồm:

```sql
SHOW POOLS;
SHOW SERVERS;
SHOW CLIENTS;
SHOW STATS;
SHOW CONFIG;
```

Các maintenance commands như RELOAD, PAUSE, RESUME, RECONNECT và WAIT_CLOSE có semantics riêng. Xem tài liệu PgBouncer đúng version trước khi chạy trong production.

### Quan sát trước khi thay đổi

Ghi nhận:

- Số client active/waiting.
- Server connections active/idle/used.
- Pool database/user mapping.
- Query/transaction wait time.
- Server lifetime/idle timeout.
- Backend host/port hiện tại.

 Không chạy PAUSE/SUSPEND trong giờ cao điểm nếu chưa hiểu tác động tới requests đang chờ và transaction đang chạy.

## 22. PgBouncer RECONNECT, PAUSE và RESUME

Khi backend host hoặc credentials thay đổi, PgBouncer có các lệnh quản trị để tác động tới server connections:

- RECONNECT: yêu cầu server connections của database được đóng và tạo lại khi phù hợp với trạng thái sử dụng.
- WAIT_CLOSE: chờ các server connections đang được đánh dấu đóng thực sự kết thúc.
- PAUSE: đợi queries/transactions hiện tại kết thúc rồi đóng server connections của database.
- RESUME: tiếp tục nhận/phục vụ sau PAUSE hoặc SUSPEND.
- RELOAD: đọc lại cấu hình từ file.

Semantics chi tiết và phạm vi lệnh phụ thuộc phiên bản. Trước khi chạy, đọc tài liệu PgBouncer và thử trong staging. Đặc biệt, PAUSE có thể làm request mới phải chờ và ảnh hưởng availability nếu kéo dài.

### Ví dụ quy trình đổi backend

1. Xác nhận endpoint mới đã trỏ tới primary/standby đúng vai trò.
2. Kiểm tra credentials/TLS tới backend mới.
3. Reload cấu hình PgBouncer nếu file thay đổi.
4. RECONNECT database phù hợp để thay server connections cũ.
5. Theo dõi SHOW SERVERS và SHOW POOLS.
6. Xác nhận connection mới tới đúng backend.

Không coi RECONNECT là failover manager; nó chỉ làm mới connections của pooler theo cấu hình backend hiện tại.

## 23. Pool sizing và connection budget

Mỗi PostgreSQL backend có giới hạn connections. Tổng connection budget phải tính mọi application instances, workers, poolers, monitoring, migrations, replication và admin access.

Ví dụ:

| Thành phần | Số lượng |
|---|---:|
| 8 application instances × write pool 10 | 80 |
| 8 application instances × read pool 20 | 160 |
| 2 workers × pool 10 | 20 |
| Monitoring/admin/migrations reserve | 20 |
| Tổng client-side connections | 280 |

Nếu không có pooler multiplexing, con số này có thể trở thành số server connections. Nếu dùng PgBouncer transaction pooling, server connection count có thể thấp hơn đáng kể, nhưng cần tính theo database/user pools và workload concurrency.

### Không đặt max pool bằng max_connections

PostgreSQL cần headroom cho autovacuum workers, replication, superuser-reserved connections, monitoring và incident access. Pool exhaustion ở application không nên làm database mất khả năng admin khi sự cố.

### Pool size quá lớn

- Tăng memory/backend process overhead.
- Tăng context switching.
- Làm contention trên CPU, locks và I/O nặng hơn.
- Có thể giảm throughput thay vì tăng throughput.

Đo query concurrency, queue time, CPU và latency trước khi tăng pool size.

## 24. Tính số server connections khi có nhiều PgBouncer pools

PgBouncer thường tạo pool theo database/user pair. Một cấu hình có nhiều database aliases hoặc nhiều users có thể tạo nhiều pools độc lập.

Ví dụ:

- 3 databases.
- 5 database users.
- default_pool_size = 20.

Giới hạn lý thuyết có thể lên tới 3 × 5 × 20 server connections nếu tất cả pools hoạt động đồng thời, trước khi tính reserve pools và các giới hạn khác.

### Giới hạn tổng

Đặt max_db_connections/max_user_connections khi phù hợp để khống chế tổng backend connections. Kiểm tra option availability và semantics theo PgBouncer version.

## 25. Connection acquisition timeout và queueing

Application pool có thể phải chờ connection khi tất cả connections đang được sử dụng. Nếu queue quá lâu, request latency tăng và thread/request workers bị giữ lại.

Các timeout cần phân biệt:

| Timeout | Giới hạn |
|---|---|
| Pool acquisition timeout | Thời gian chờ lấy connection từ application pool |
| Connect timeout | Thời gian mở TCP/PostgreSQL connection |
| Server login timeout | Thời gian pooler chờ backend login |
| Query timeout | Thời gian query được phép chạy |
| Transaction timeout/deadline | Thời gian toàn transaction/request |
| Idle timeout | Thời gian connection không hoạt động trước khi đóng |

### Timeout hierarchy

Thiết kế để timeout bên trong có thể kết thúc trước timeout request tổng. Nếu request deadline hết nhưng query vẫn chạy, connection có thể tiếp tục chiếm pool và làm backlog tăng. Dùng cancellation/statement timeout phù hợp, nhưng hiểu transaction rollback behavior.

## 26. Connection lifetime và maxLifetime

Connection pool thường giữ connections lâu để tránh chi phí connect/authentication/TLS. Tuy nhiên, connections tồn tại vô thời hạn có thể giữ backend cũ sau DNS/failover changes hoặc gặp network middlebox idle timeouts.

Pool library có thể hỗ trợ:

- Maximum connection lifetime.
- Idle timeout.
- Keepalive/validation.
- Soft eviction/recycle.
- Connection test on borrow hoặc background validation.

### Chọn lifetime

Lifetime nên ngắn hơn các giới hạn hạ tầng cần tuân thủ (ví dụ server-side connection lifetime hoặc proxy maintenance window), có jitter nếu pool hỗ trợ để tránh mọi connections hết hạn cùng lúc.

### Tránh connection churn

Lifetime quá ngắn khiến pool liên tục mở/đóng connections, tăng TLS/auth load và connection storms. Đặt lifetime theo measured connection stability và failover objectives.

## 27. Keepalive và stale TCP connections

Một TCP connection có thể bị network path cắt mà client chưa nhận biết ngay. TCP keepalive, driver socket timeout và pool validation giúp phát hiện stale connections.

### Keepalive

TCP keepalive gửi probes khi connection idle đủ lâu. Các giá trị OS/driver khác nhau; cần cấu hình ở đúng layer. Keepalive không phải health check cho PostgreSQL role.

### Validation

Pool có thể kiểm tra connection trước khi cấp cho request hoặc chạy background validation. Validation query nên nhẹ; kiểm tra role/lag cần một probe riêng nếu routing policy yêu cầu.

### Không kiểm tra mọi connection bằng query nặng

Health check tần suất quá cao có thể tự tạo tải. Dùng connection validation tối thiểu và cache health state ở routing layer với thời hạn ngắn hợp lý.

## 28. HikariCP: các thuộc tính thường gặp

Trong ứng dụng Java dùng HikariCP, các thuộc tính thường được cân nhắc:

| Property | Ý nghĩa |
|---|---|
| maximumPoolSize | Số connections tối đa trong pool |
| minimumIdle | Số idle connections mục tiêu |
| connectionTimeout | Thời gian chờ lấy connection |
| idleTimeout | Thời gian idle trước khi connection có thể bị loại bỏ |
| maxLifetime | Tuổi thọ tối đa của connection |
| keepaliveTime | Chu kỳ keepalive cho idle connections |
| validationTimeout | Thời gian tối đa kiểm tra connection |

Ví dụ minh họa:

```properties
maximumPoolSize=20
minimumIdle=2
connectionTimeout=3000
idleTimeout=300000
maxLifetime=1500000
keepaliveTime=120000
validationTimeout=2000
```

Đơn vị thời gian và constraints phải xác nhận theo HikariCP version. Các giá trị này chỉ minh họa cấu hình; không sao chép nguyên xi nếu chưa đo workload.

### Read/write pools

Có thể tạo hai HikariDataSource độc lập, một cho write endpoint và một cho read endpoint. Cần đóng/recreate hoặc soft-evict connections theo API/lifecycle của version khi endpoint đổi.

## 29. Refresh pool là gì?

Refresh connection pool là quá trình làm cho ứng dụng ngừng dùng các connections cũ và mở connections mới theo endpoint, credentials, TLS certificates hoặc server roles hiện tại.

Refresh có thể cần khi:

- Primary failover sang node mới.
- DNS/VIP/backend mapping thay đổi.
- Standby bị promote hoặc bị loại khỏi read pool.
- Credentials/password được rotate.
- TLS certificate/CA được thay.
- PgBouncer/backend configuration thay đổi.
- Connection bị stale hoặc network path không còn hoạt động.

### Pool refresh không đồng nghĩa restart ứng dụng

Nhiều pool libraries hỗ trợ soft eviction hoặc close idle connections, sau đó tạo connections mới theo datasource configuration. Nếu endpoint nằm trong config object không thể mutate, cần thay datasource/pool có kiểm soát và drain pool cũ.

## 30. Failover ảnh hưởng connection pool thế nào?

Giả sử primary A gặp sự cố và standby B được promote:

```text
Before:
  write pool ---> Primary A
  read pool  ---> Standby B

Failover:
  A fenced / unavailable
  B promoted to primary

After:
  write pool ---> New primary B
  read pool  ---> Another healthy standby C
```

Các connections đã mở tới A không tự chuyển sang B. Chúng có thể lỗi, treo cho tới timeout hoặc vẫn kết nối vào A nếu A chưa bị fence và còn hoạt động.

### Vai trò fencing

Trước khi chuyển writes sang B, HA control plane phải bảo đảm A không tiếp tục nhận writes. Chỉ đổi DNS hoặc evict pool không ngăn split brain nếu old primary vẫn writable.

### Endpoint update

Sau promotion, cập nhật primary endpoint qua HA manager/proxy/DNS và xác nhận health check chỉ chọn B. Sau đó làm mới write pool. Read pool cần loại B khỏi replica pool nếu B đang là primary và thêm standby khác theo policy.

## 31. Thứ tự refresh sau failover

Một trình tự tham khảo:

1. Phát hiện primary failure.
2. Fencing/STONITH hoặc cơ chế bảo đảm old primary không writable.
3. Promote standby theo HA orchestration.
4. Xác minh node mới writable và timeline mới.
5. Cập nhật primary/write endpoint.
6. Cập nhật read endpoint membership; bỏ node mới promote khỏi standby list.
7. Yêu cầu pooler reconnect hoặc drain backend connections cũ.
8. Evict stale connections trong application pools.
9. Tạo connections mới và xác nhận chúng tới đúng role.
10. Chạy smoke tests và mở traffic dần.
11. Rejoin/reseed old primary theo quy trình.

### Không refresh quá sớm

Nếu pool chuyển writes sang node mới trước khi promotion hoàn tất, connection mới có thể gặp read-only/recovery errors. Chờ role verification và HA manager state chuyển sang primary.

## 32. Soft eviction và hard shutdown

**Soft eviction** đánh dấu connections hiện tại không nên được tái sử dụng sau khi trả về pool; requests đang chạy có thể hoàn tất. **Hard shutdown** đóng connections ngay, có thể làm query/transaction đang chạy thất bại.

### Khi nên soft evict

- DNS/backend changed nhưng server cũ vẫn phục vụ bình thường.
- Rotate credentials/TLS với thời gian overlap.
- Recycle connections theo maxLifetime.
- Thay cấu hình read endpoint không khẩn cấp.

### Khi cần hard close

- Old primary bị fence hoặc endpoint bị thu hồi.
- Credentials bị compromise.
- TLS identity không còn được tin cậy.
- Connection đang trỏ tới node không còn được phép nhận traffic.

Hard close có thể làm transaction có kết quả không xác định ở client. Phải có retry/idempotency policy.

## 33. Drain connections trước maintenance

Drain là giảm traffic mới vào endpoint/pool cũ, chờ in-flight work hoàn tất rồi đóng connections.

Quy trình:

1. Ngừng cấp connection mới từ routing layer tới backend cũ.
2. Chờ transactions đang chạy kết thúc trong deadline.
3. Theo dõi active clients/transactions.
4. Soft-evict idle/returned connections.
5. Đóng phần còn lại theo maintenance policy.
6. Xác nhận không còn traffic tới backend cũ.

### Long-running transactions

Một transaction dài có thể giữ connection không trả về pool. Cần đặt deadline/statement_timeout/transaction_timeout phù hợp và thông báo ứng dụng về thời gian drain.

Không terminate sessions hàng loạt mà chưa biết chúng đang chạy transaction nào và hậu quả rollback.

## 34. DNS refresh và connection lifetime phối hợp

Khi DNS đổi từ A sang B:

- Connections mới có thể resolve B sau khi cache hết hạn.
- Connections đang mở vẫn gắn với A.
- Pool có thể tiếp tục cấp lại connection cũ từ idle list.
- Driver/JVM có thể cache DNS lâu hơn record TTL.

### Chiến lược

- Dùng endpoint ổn định có role-aware routing.
- Giới hạn DNS cache theo môi trường/driver.
- Đặt maxLifetime để connections cũ được recycle.
- Sau failover, chủ động evict thay vì chờ lifetime hết.
- Quan sát backend address của connections mới.

DNS TTL ngắn không thay thế eviction; eviction không thay thế fencing.

## 35. Refresh sau password rotation

Khi password của application role được đổi:

1. Xác định thời điểm credential mới có hiệu lực.
2. Cập nhật secret manager/config cho pool mới.
3. Xác minh connection mới đăng nhập thành công.
4. Soft-evict hoặc drain connections cũ theo overlap policy.
5. Xác nhận không còn process dùng password cũ.
6. Thu hồi credential cũ khi không còn dependency.

Nếu server policy cho phép overlap bằng hai roles/credentials, có thể dùng staged rotation để tránh downtime. PostgreSQL role password rotation trực tiếp không tự làm mọi session hiện có bị ngắt; connections mới cần password mới.

## 36. Refresh sau TLS certificate rotation

TLS certificate/CA rotation có thể làm connection mới thất bại nếu client trust store chưa được cập nhật hoặc hostname verification không còn match.

### Quy trình overlap

1. Cập nhật trust store để tin CA mới trước.
2. Deploy certificate mới lên PostgreSQL/proxy.
3. Test TLS handshake và hostname verification.
4. Tạo pool connections mới.
5. Drain connections sử dụng certificate cũ theo policy.
6. Loại CA/certificate cũ sau khi hết thời gian overlap.

### Existing sessions

Một TLS session đã được thiết lập không tự đổi certificate giữa chừng. Refresh pool giúp tạo handshakes mới để xác nhận certificate mới.

## 37. Retry khi connection bị mất

Connection failure có thể xảy ra:

- Trước khi transaction bắt đầu.
- Giữa các statements.
- Trong lúc COMMIT.
- Sau khi server commit nhưng trước khi client nhận acknowledgment.

Trường hợp cuối cùng tạo **ambiguous outcome**: client không biết transaction đã commit hay chưa.

### Không retry mù

Retry INSERT/charge/payment/order creation có thể tạo duplicate nếu transaction trước đã commit. Cần:

- Idempotency key hoặc unique request ID.
- Unique constraint chống duplicate.
- Outbox/inbox pattern khi tích hợp external systems.
- Query trạng thái transaction theo business key trước khi retry.
- Phân biệt lỗi connect-before-send với lỗi mất kết nối khi commit.

### Retry policy

Dùng bounded retries, exponential backoff và jitter. Không retry vô hạn hoặc retry mọi SQLSTATE. Một số lỗi là permanent (authentication/permission/schema); một số lỗi có thể transient (connection failure/failover).

## 38. SQLSTATE thường gặp khi connection/failover

| SQLSTATE | Ý nghĩa tổng quát | Hướng xử lý |
|---|---|---|
| 08000 | Connection exception | Kiểm tra network/driver/pool |
| 08003 | Connection does not exist | Loại connection khỏi pool |
| 08006 | Connection failure | Reconnect có backoff |
| 57P01 | Admin shutdown | Chờ HA/pooler chuyển endpoint |
| 57P02 | Crash shutdown | Kiểm tra node/HA state |
| 57P03 | Cannot connect now | Node chưa sẵn sàng |
| 25006 | Read-only SQL transaction | Có thể đã route write vào standby hoặc transaction read-only |
| 28P01 | Invalid password | Kiểm tra credential rotation/secret |

SQLSTATE là tín hiệu chẩn đoán, không phải quyết định retry duy nhất. Cần xem transaction state, request idempotency và HA control plane.

## 39. Circuit breaker và fallback

Circuit breaker ngừng gửi requests tới endpoint đang lỗi sau khi vượt ngưỡng failure, sau đó thử lại có kiểm soát.

### Với write endpoint

Không fallback writes sang một replica bất kỳ. Chỉ chuyển khi HA control plane xác nhận primary mới đã được promote và old primary đã được fence.

### Với read endpoint

Nếu một standby lag/quá tải, có thể bỏ nó khỏi read pool. Nếu không còn standby khỏe:

- Route một số reads sang primary nếu capacity cho phép.
- Giảm/queue workload analytics.
- Trả lỗi/retry cho requests có consistency contract rõ.

Không dồn toàn bộ read traffic sang primary mà không có capacity guard.

## 40. Read routing theo workload class

Có thể tách read endpoints theo loại workload:

| Class | Replica/policy | Ví dụ |
|---|---|---|
| Low-latency reads | Replica gần app, lag thấp | Product detail, profile |
| Read-after-write | Primary hoặc LSN-wait | Vừa tạo/cập nhật record |
| Reporting | Replica chuyên dụng, query concurrency giới hạn | Dashboard, reports |
| Analytics/batch | Replica riêng hoặc warehouse | Scan lớn, exports |
| DR validation | Standby/isolated restore | Recovery checks |

### Tại sao tách reporting?

Một query scan dài có thể gây I/O pressure, cache eviction và replay conflicts. Tách workload giúp API read latency ổn định hơn và giảm tác động lên primary.

## 41. Session state và read routing

Một read query có thể phụ thuộc session settings:

- search_path.
- TimeZone.
- role/current_user.
- temporary objects.
- prepared statements.
- advisory locks.
- transaction isolation.

Nếu request chuyển giữa pools/endpoints, state không tự đi theo. Thiết lập state trong connection startup hoặc transaction-local scope theo policy.

### SET LOCAL

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SET LOCAL TIME ZONE 'UTC';
SELECT * FROM public.product WHERE product_id = 10;
COMMIT;
```

SET LOCAL kết thúc cùng transaction, phù hợp hơn với transaction pooling so với session-level SET kéo dài.

## 42. Connection pool metrics

Thu thập metrics ở cả application pool, PgBouncer và PostgreSQL:

### Application pool

- Active, idle và total connections.
- Threads/requests chờ connection.
- Acquisition latency và timeout count.
- Connection creation/close rate.
- Connection lifetime/eviction count.
- Validation failures.

### PgBouncer

- Client connections active/waiting.
- Server connections active/idle/used.
- Pool wait time.
- Query/transaction time.
- Login failures và server reconnects.

### PostgreSQL

- numbackends/active sessions.
- pg_stat_activity wait events.
- pg_stat_replication state/lag.
- pg_stat_wal_receiver status.
- Replication slot retained WAL.
- CPU, memory, disk I/O và network.

### Routing metrics

- Writes sent to primary.
- Reads sent to each standby.
- Reads pinned to primary for consistency.
- Fallback-to-primary count.
- Replica removed due to lag/health.
- Requests failed during refresh/failover.

## 43. Kiểm tra routing distribution

Không chỉ đo tổng query latency. Cần biết workload đang thực sự đi đâu.

Một log/trace record có thể ghi:

- route class: write/read/reporting/read-after-write.
- logical endpoint/pool name.
- database node/host được kết nối.
- transaction id/request id.
- query duration và pool acquisition duration.
- replica replay lag tại thời điểm routing.
- fallback reason nếu không dùng read endpoint.

Không log password, connection string chứa secret hoặc dữ liệu nhạy cảm trong SQL parameters.

### Xác minh từ PostgreSQL

Trên mỗi node:

```sql
SELECT
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_is_in_recovery() AS is_standby,
    current_database() AS database_name,
    current_user AS role_name;
```

Ứng dụng có thể gắn application_name khác nhau cho write/read/reporting pools để phân biệt sessions trong pg_stat_activity.

## 44. application_name và connection attribution

Đặt application_name rõ ràng trong connection string:

```text
application_name=orders-api-write
```

Ví dụ read pool:

```text
application_name=orders-api-read
```

Khi quan sát:

```sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    count(*) AS connections
FROM pg_catalog.pg_stat_activity
GROUP BY
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event
ORDER BY application_name, state;
```

application_name giúp phân biệt pool/worker nhưng không phải identity bảo mật. Không dùng nó thay authentication hoặc authorization.

## 45. pg_is_in_recovery và primary detection

Primary detection thường dựa trên:

```sql
SELECT pg_is_in_recovery();
```

- false: node không ở recovery tại thời điểm query.
- true: node đang ở recovery/standby.

### Vì sao cần nhiều tín hiệu?

Một node trả false có thể là old primary sau network partition, hoặc một cluster độc lập. HA manager phải xác nhận leader/term/lease/fencing state. Chỉ kiểm tra pg_is_in_recovery không chứng minh node là primary duy nhất được phép nhận writes.

### Health check có thể cache ngắn

Proxy có thể polling role/health định kỳ và cache kết quả trong vài giây. Khoảng cache càng dài thì detection càng chậm; quá ngắn tạo probe load và có thể gây flapping. Chọn dựa trên failover objectives.

## 46. Role-aware load balancer

Một load balancer PostgreSQL cần hiểu protocol hoặc dùng health-check agent để đưa node vào/out khỏi backend pool. TCP health check đơn giản không phân biệt primary/standby.

### Thiết kế an toàn

- Write backend pool chỉ chứa primary được HA control plane xác nhận.
- Read backend pool chỉ chứa standby đủ khỏe theo lag threshold.
- Khi promotion, node chuyển từ read membership sang write membership sau role verification.
- Khi node unhealthy, ngừng gửi connections mới và drain connections cũ.
- Không để hai primaries cùng nằm trong write backend pool.

Một số giải pháp dùng HAProxy với external check script/agent; cách cấu hình phụ thuộc OS, HA manager và version. Health check script phải có timeout, quyền tối thiểu và failure behavior rõ.

## 47. Pgpool-II và query load balancing

Pgpool-II có thể cung cấp connection pooling, health checks, failover handling và load balancing theo cấu hình. Nó có thể phân loại một số queries để route reads, nhưng hành vi phụ thuộc replication mode, query type, transaction state và configuration.

### Cần kiểm thử

- SELECT đơn giản và SELECT trong transaction.
- SELECT sau INSERT/UPDATE.
- Function có side effects.
- Temporary tables/session settings.
- Prepared statements.
- Explicit read-only transactions.
- Multi-statement transactions.
- Queries dùng advisory locks hoặc sequences.

Không giả định mọi SELECT đều được gửi tới standby hoặc mọi lỗi failover được xử lý tự động. Proxy phải được test bằng workload thực tế và failover drills.

## 48. Connection pooler không thay thế application routing

PgBouncer tối ưu việc tái sử dụng server connections. Nó không tự hiểu business semantics như “đọc order ngay sau khi vừa tạo order phải thấy dữ liệu mới”. Ứng dụng vẫn cần quyết định consistency policy và endpoint.

### Phân vai

- Application: quyết định write/read/consistency class.
- HA manager: xác định primary và trạng thái failover.
- Load balancer/proxy: cung cấp endpoint theo role/health.
- Pooler: multiplex và quản lý backend connections.
- PostgreSQL: thực thi transaction/recovery/replication.

Giữ trách nhiệm rõ giúp debug sự cố routing dễ hơn.

## 49. Pool refresh khi thay read replica membership

Khi thêm/bỏ một standby:

1. Health-check node mới và xác minh role.
2. Đo lag, CPU, disk và connection capacity.
3. Thêm node vào read backend pool với weight thấp.
4. Quan sát traffic distribution và latency.
5. Tăng weight dần nếu ổn định.
6. Khi loại node, ngừng cấp connections mới.
7. Drain/evict existing connections.
8. Xác nhận node không còn nhận read traffic.

### Không thêm replica chỉ vì TCP mở

Replica có thể đang initial recovery, đang catch up hoặc lag quá ngưỡng. Chỉ thêm khi application read policy được đáp ứng.

## 50. Pool refresh khi đổi endpoint config

Nếu datasource URL/host thay đổi:

- Xác định config source of truth.
- Cập nhật secret/config store.
- Đảm bảo process nhận config mới.
- Tạo pool mới hoặc cập nhật pool theo API được hỗ trợ.
- Validate connections tới backend mới.
- Chuyển traffic sang pool mới.
- Drain và close pool cũ.

### Blue/green pool replacement

Với ứng dụng cần availability cao, có thể tạo pool mới song song với pool cũ. Khi pool mới healthy, đổi routing sang pool mới rồi drain pool cũ. Cần giới hạn tổng connections trong thời gian overlap.

## 51. Pool refresh khi endpoint vẫn giống nhưng role đổi

Một DNS name có thể giữ nguyên trong failover, nhưng node phía sau đã đổi role. Connection đã mở tới node trước đó vẫn giữ session trên server đó.

Do đó:

- Kiểm tra role ở backend mới.
- Evict connections cũ theo failover event.
- Reconnect để nhận node mới.
- Xác minh application_name/host/role sau reconnect.

Không chỉ so sánh hostname; cùng hostname có thể đại diện cho node khác theo thời điểm.

## 52. Backoff và jitter khi reconnect

Sau outage, hàng nghìn application instances có thể cùng reconnect. Nếu tất cả retry ngay lập tức, primary/proxy có thể bị connection storm.

Dùng exponential backoff có jitter:

```text
attempt 1: short delay
attempt 2: longer delay
attempt 3: longer delay with random jitter
...
maximum delay: bounded
```

Các retry phải có deadline tổng và phân biệt lỗi transient/permanent. Authentication failure không nên retry vô hạn; connection refused trong failover có thể retry có kiểm soát.

## 53. Startup storm và pool warm-up

Sau deployment/restart, mọi instance có thể đồng thời tạo maximumPoolSize connections. Điều này làm PostgreSQL nhận một burst authentication/TLS handshakes.

Biện pháp:

- Giới hạn minimumIdle.
- Warm-up dần với concurrency cap.
- Dùng jitter cho startup/reconnect.
- Giới hạn pool max theo service tier.
- Dùng PgBouncer để multiplex khi phù hợp.
- Tránh autoscaling làm tổng connection count vượt budget.

## 54. Pool exhaustion và backpressure

Khi mọi connections đều bận, pool queue tăng. Nếu ứng dụng tiếp tục nhận request không giới hạn, memory/thread backlog có thể tăng.

### Backpressure

- Giới hạn concurrent requests theo pool capacity.
- Tách pool cho critical traffic và batch jobs.
- Đặt query/transaction deadlines.
- Queue có bounded capacity.
- Trả overload response sớm khi không thể phục vụ.
- Hạn chế reporting workload khi primary/replica đang quá tải.

### Không tăng pool vô hạn

Tăng max pool có thể chuyển bottleneck sang PostgreSQL và làm tình hình xấu hơn. Kiểm tra slow queries, locks, CPU, I/O và connection leaks trước.

## 55. Connection leaks và long transactions

Một connection leak xảy ra khi ứng dụng lấy connection nhưng không trả lại pool. Long transaction cũng giữ connection lâu dù code không leak.

### Dấu hiệu

- Active connections tăng nhưng throughput không tăng.
- Pool wait time tăng.
- Idle in transaction sessions kéo dài.
- Transaction giữ locks hoặc snapshot cũ.
- Read replica replay bị chặn bởi long-running queries.

### Khắc phục

- Dùng try-with-resources/context managers.
- Đặt transaction boundaries ngắn.
- Đóng result sets/statements/connections đúng lifecycle.
- Bật leak detection phù hợp.
- Theo dõi idle_in_transaction_session_timeout và statement/transaction deadlines.

Không terminate sessions chỉ dựa vào state idle in transaction; kiểm tra owner và business impact.

## 56. Read replica bị lag vì query workload

Một read query dài trên standby có thể xung đột với WAL replay. Nếu standby trì hoãn replay để chờ query, lag tăng; nếu replay ưu tiên, query có thể bị cancel do conflict.

### Tách workload

- API reads ngắn trên replica low-latency.
- Reports trên replica riêng.
- Exports lớn trên replica/warehouse dành cho batch.
- Read-after-write trên primary hoặc LSN-aware path.

### Theo dõi conflicts

```sql
SELECT *
FROM pg_catalog.pg_stat_database_conflicts
ORDER BY datname;
```

Kết hợp conflict counters, replay lag, query duration và max_standby_streaming_delay/hot_standby_feedback policy.

## 57. Troubleshooting: write request nhận read-only error

Lỗi SQLSTATE 25006 thường cho thấy transaction đang read-only. Điều tra:

1. Xác định host/server thực tế của connection.
2. Kiểm tra pg_is_in_recovery() trên node.
3. Kiểm tra write endpoint/backend membership.
4. Kiểm tra pool có giữ connection cũ tới standby không.
5. Kiểm tra transaction read-only setting.
6. Kiểm tra failover/DNS/proxy state.
7. Evict connection sai endpoint sau khi routing được sửa.
8. Retry request chỉ khi outcome transaction được xác định.

Đừng khắc phục bằng cách tắt read-only protections trên standby.

## 58. Troubleshooting: read request không thấy dữ liệu vừa ghi

Điều tra:

- Write transaction đã commit chưa?
- Read request đang đi primary hay standby?
- Replica replay LSN/time có theo kịp không?
- Có cache/application-level stale data không?
- Có transaction snapshot cũ giữ query không?
- Read pool có pin vào một replica lag hơn các replicas khác?

Khắc phục bằng primary routing, LSN wait hoặc consistency contract phù hợp. Đừng tăng sleep cố định như cách sửa chính.

## 59. Troubleshooting: pool giữ connections tới old primary

1. Xác nhận failover/promotion đã hoàn tất.
2. Xác nhận old primary đã fenced.
3. Kiểm tra DNS/VIP/proxy backend hiện tại.
4. Kiểm tra app pool và PgBouncer server connections.
5. Evict/reconnect theo pool lifecycle.
6. Kiểm tra connection mới đang tới node primary mới.
7. Theo dõi old node không còn nhận writes.
8. Xử lý unknown transaction outcomes bằng idempotency/reconciliation.

## 60. Troubleshooting: pool timeout dù database khỏe

Nguyên nhân có thể:

- Pool size quá nhỏ hoặc queue quá dài.
- Connection leak.
- Query/transaction quá lâu.
- Pooler server pool cạn.
- Per-user/per-database limit quá thấp.
- Authentication/connect latency cao.
- DNS/TLS/secret refresh gây connection creation failures.

Kiểm tra application pool metrics, PgBouncer SHOW POOLS/SERVERS, pg_stat_activity và query latency. Phân biệt pool acquisition timeout với PostgreSQL connect/query timeout.

## 61. Runbook: chuyển primary endpoint sau failover

1. Xác nhận failure và quyết định failover từ HA control plane.
2. Fence old primary để ngăn split brain.
3. Promote standby theo orchestration.
4. Xác minh pg_is_in_recovery() = false trên node mới.
5. Xác minh HA manager chỉ có một writable primary.
6. Cập nhật write endpoint/VIP/DNS/proxy backend.
7. Chờ routing layer nhận config mới.
8. RECONNECT/drain pooler backend connections theo runbook.
9. Soft-evict hoặc thay application write pool.
10. Chạy write/read smoke tests và xác minh host/role.
11. Rebuild read pool membership từ các standbys còn khỏe.
12. Theo dõi SQLSTATE, pool timeouts, transaction outcomes và replication lag.

## 62. Runbook: drain một standby khỏi read pool

1. Đánh dấu standby unhealthy/maintenance trong routing layer.
2. Ngừng gửi connections mới tới node.
3. Xác định long-running queries/transactions.
4. Chờ in-flight requests hoàn tất trong deadline.
5. Soft-evict/close idle connections.
6. Xác nhận pool không còn backend connections tới node.
7. Thực hiện maintenance/restart.
8. Kiểm tra recovery/streaming sau khi node lên.
9. Chờ lag xuống dưới threshold.
10. Add node trở lại với weight thấp và quan sát.

## 63. Runbook: rotate credentials và refresh pool

1. Phát hành credential mới qua secret manager.
2. Xác nhận PostgreSQL role/policy chấp nhận credential mới.
3. Cập nhật application/pooler configuration.
4. Tạo connection test từ từng service identity.
5. Reload/restart pooler nếu cần.
6. Soft-evict old application connections.
7. Theo dõi authentication failures.
8. Xác nhận không còn process dùng secret cũ.
9. Revoke credential cũ theo rotation plan.
10. Lưu audit evidence và cập nhật rollback procedure.

## 64. Runbook: xử lý connection storm sau outage

1. Giữ bounded retry và backoff/jitter.
2. Kiểm tra primary/proxy đã sẵn sàng chưa.
3. Tạm giới hạn autoscaling/worker concurrency nếu cần.
4. Kiểm tra server connection budget.
5. Warm up pools dần.
6. Theo dõi authentication/TLS handshake rate.
7. Mở traffic theo service tier.
8. Theo dõi pool queue và DB CPU.
9. Tăng concurrency chỉ khi database còn headroom.
10. Ghi nhận nguyên nhân storm và điều chỉnh startup policy.

## 65. Checklist routing và pool lifecycle

### Routing

- Writes/DDL luôn tới primary hiện tại.
- Transactions được pin vào một connection.
- Read-after-write policy được định nghĩa.
- Read endpoint lọc replicas theo role và lag.
- SELECT có side effects không bị route sai.
- Reporting/batch workload có endpoint phù hợp.

### Pooling

- Pool sizes được tính trên tổng instances/users/databases.
- Pool mode tương thích session features.
- Acquisition/connect/query timeouts có deadline.
- maxLifetime/idle timeout/keepalive được cấu hình.
- Connection leaks/long transactions được theo dõi.

### Failover/refresh

- Old primary được fence trước khi chuyển writes.
- DNS/endpoint update có control plane rõ.
- Application pools có soft eviction/recreate.
- Pooler backend connections có reconnect/drain procedure.
- Credential/TLS rotations có overlap và refresh.
- Retry có backoff, jitter và idempotency.

### Observability

- Route distribution theo endpoint/replica.
- Pool active/idle/waiting/acquisition latency.
- Backend host/role và health state.
- Replication lag/slot state.
- Failover/refresh events và SQLSTATE errors.
- RPO/RTO và read consistency failures.

## 66. Các lỗi thiết kế thường gặp

**Dùng TCP check làm primary health check.** TCP open không chứng minh node là primary.

**Route mọi SELECT sang standby.** Một số SELECT có side effects hoặc yêu cầu read-after-write.

**Đổi DNS rồi nghĩ connections cũ tự chuyển.** TCP sockets và pooled connections vẫn gắn với backend cũ.

**Dùng một pool cho cả read và write nhưng không có role awareness.** Connection có thể trỏ tới standby sau failover.

**Tăng pool size để sửa mọi timeout.** Có thể làm PostgreSQL quá tải hơn.

**Dùng transaction pooling mà giữ session state.** State có thể mất hoặc xuất hiện trên connection khác.

**Retry transaction khi COMMIT bị mất kết nối mà không idempotency.** Transaction có thể đã commit, dẫn tới duplicate effects.

**Đưa promoted primary vào read pool và write pool mà không cập nhật role membership.** Có thể tạo sai routing hoặc load skew.

**Không fence old primary.** Có nguy cơ split brain.

**Dùng replication lag timestamp duy nhất.** Trên primary idle, timestamp có thể cũ dù replica đã theo kịp.

**Chỉ test failover ở mức database.** Cần test application pool, DNS, proxy, retry và transaction outcomes.

## 67. Bài tập thực hành

### Bài 1 — Primary và read endpoint

Vẽ kiến trúc có primary, hai standbys, write endpoint, read endpoint và application pools. Giải thích node nào nhận writes.

### Bài 2 — Routing semantics

Phân loại INSERT, UPDATE, DDL, SELECT đơn giản, SELECT gọi function có side effects và transaction đọc rồi ghi.

### Bài 3 — SELECT không read-only

Một câu SELECT gọi function thực hiện side effect. Vì sao SQL prefix không đủ để quyết định read routing?

### Bài 4 — Separate pools

Thiết kế write pool và read pool cho một API service. Nêu cách service layer thể hiện routing intent.

### Bài 5 — Transaction pinning

Một transaction UPDATE balance rồi SELECT balance trước COMMIT. Vì sao SELECT phải ở cùng primary connection?

### Bài 6 — Read-after-write

Một order được commit ở primary nhưng chưa xuất hiện trên standby. Nêu ba cách đảm bảo user nhìn thấy order vừa tạo.

### Bài 7 — LSN token

Viết SQL lấy current WAL LSN sau commit và kiểm tra pg_last_wal_replay_lsn trên standby. Nêu điều kiện timeline.

### Bài 8 — Synchronous commit

So sánh synchronous_commit=on và remote_apply. Vì sao remote_apply không tự chọn read endpoint?

### Bài 9 — Replication lag

Giải thích sự khác nhau giữa byte lag và timestamp lag. Vì sao timestamp có thể cũ khi primary idle?

### Bài 10 — Health check

Viết query dùng pg_is_in_recovery và transaction_read_only để phân biệt primary/standby. Vì sao vẫn cần HA manager/fencing?

### Bài 11 — target_session_attrs

Viết libpq connection string thử nhiều hosts và chọn read-write server. Nêu giới hạn sau khi connection đã mở.

### Bài 12 — DNS

Primary endpoint đổi IP sau failover nhưng app vẫn dùng connection cũ. Giải thích DNS TTL, resolver cache và TCP sockets.

### Bài 13 — Read load balancing

Thiết kế weighted read routing cho hai replicas có capacity khác nhau. Metrics nào cần theo dõi?

### Bài 14 — PgBouncer

Vẽ hai PgBouncer endpoints cho write và read. Vì sao PgBouncer không mặc định phân tích SQL để route từng statement?

### Bài 15 — Pooling modes

So sánh session, transaction và statement pooling. Chọn mode cho ứng dụng dùng multi-statement transactions.

### Bài 16 — Session state

Một ứng dụng dùng temporary tables, LISTEN/NOTIFY và session advisory locks. Những tính năng nào có thể gặp vấn đề với transaction pooling?

### Bài 17 — SET LOCAL

Viết transaction dùng SET LOCAL statement_timeout và TimeZone. Vì sao nó phù hợp hơn session-level SET trong transaction pooling?

### Bài 18 — PgBouncer commands

Giải thích mục đích của RELOAD, RECONNECT, WAIT_CLOSE, PAUSE và RESUME. Vì sao cần đọc semantics theo version?

### Bài 19 — Pool sizing

Một service có 10 instances, mỗi instance write pool 15 và read pool 25. Tính tổng connections tiềm năng trước khi tính pooler và admin reserve.

### Bài 20 — Connection budget

PostgreSQL có max_connections=300. Thiết kế budget cho app, workers, monitoring, replication, migrations và admin headroom.

### Bài 21 — Pool timeout

Phân biệt acquisition timeout, connect timeout và query timeout. Một request chờ pool 3 giây rồi fail; cần xem metrics nào?

### Bài 22 — maxLifetime

Vì sao pool cần maxLifetime? Tại sao lifetime quá ngắn có thể gây connection churn?

### Bài 23 — Keepalive

Giải thích TCP keepalive và connection validation. Vì sao chúng không thay thế primary role health check?

### Bài 24 — HikariCP

Giải thích maximumPoolSize, minimumIdle, connectionTimeout, maxLifetime và keepaliveTime. Những giá trị nào cần đo trước khi chọn?

### Bài 25 — Pool refresh

Một endpoint đổi backend sau failover. Mô tả cách soft-evict/recreate pool và xác nhận connections mới tới đúng node.

### Bài 26 — Fencing

Vì sao phải fence old primary trước khi chuyển write endpoint? DNS update đơn thuần có ngăn split brain không?

### Bài 27 — Drain

Thiết kế drain một read replica trước maintenance mà không terminate long-running queries ngay lập tức.

### Bài 28 — Credential rotation

Một PostgreSQL password được rotate. Thiết kế overlap, cập nhật secret, refresh pool và revoke credential cũ.

### Bài 29 — TLS rotation

Thiết kế CA/certificate rotation có overlap. Vì sao pool cần tạo TLS sessions mới?

### Bài 30 — Ambiguous commit

Client mất kết nối ngay sau khi gửi COMMIT nhưng chưa nhận acknowledgment. Vì sao không thể biết chắc transaction đã commit hay chưa?

### Bài 31 — Idempotency

Thiết kế idempotency key/unique constraint cho API tạo payment để retry sau failover không tạo duplicate charge.

### Bài 32 — SQLSTATE

Giải thích cách xử lý tổng quát cho SQLSTATE 08006, 57P01, 57P03, 25006 và 28P01.

### Bài 33 — Circuit breaker

Thiết kế circuit breaker cho read endpoint. Vì sao write endpoint chỉ được chuyển khi HA control plane xác nhận primary mới?

### Bài 34 — Workload classes

Phân chia API reads, read-after-write, reporting và analytics thành endpoints/pools. Nêu lý do.

### Bài 35 — Pool metrics

Liệt kê application pool, PgBouncer và PostgreSQL metrics cần có để phát hiện pool saturation.

### Bài 36 — Read replica query conflicts

Một report query dài làm replay lag tăng. Thiết kế cách tách reporting workload và monitoring conflicts.

### Bài 37 — Startup storm

Sau outage, 50 application instances cùng mở pool tối đa. Thiết kế warm-up, backoff, jitter và concurrency caps.

### Bài 38 — Pool timeout dù DB khỏe

Một ứng dụng pool timeout nhưng PostgreSQL CPU thấp. Hãy điều tra connection leaks, pooler limits, acquisition queue và authentication.

### Bài 39 — Failover runbook

Viết trình tự từ fencing, promotion, endpoint update, pool refresh, smoke test tới read pool membership rebuild.

### Bài 40 — Thiết kế routing và pool lifecycle end-to-end

Một hệ thống thương mại điện tử có:

- Một PostgreSQL primary và ba physical standbys.
- 12 instances của API service.
- Write traffic peak 2.000 transactions/second.
- Read traffic peak 12.000 queries/second.
- Một standby phục vụ reporting.
- Hai standbys phục vụ API reads.
- RPO 10 giây và RTO 60 giây.
- Failover có thể đổi primary endpoint.
- Một số API phải thấy order ngay sau khi tạo.
- Ứng dụng dùng PgBouncer transaction pooling.

Hãy thiết kế:

1. Write/read/reporting endpoint topology.
2. Pool sizes và connection budget.
3. Routing rules theo transaction semantics.
4. Read-after-write policy bằng primary hoặc LSN wait.
5. Health checks cho primary/standby và lag thresholds.
6. PgBouncer pool mode và session-feature constraints.
7. DNS/HA endpoint và failover fencing.
8. Pool refresh/drain sequence sau promotion.
9. Retry/idempotency khi connection mất lúc COMMIT.
10. Monitoring, alerts, runbooks và chaos tests chứng minh RPO/RTO.

## Kết luận

**Định tuyến reads và writes phải dựa trên semantics của transaction và vai trò hiện tại của PostgreSQL node.** Writes, DDL và reads cần thấy dữ liệu vừa commit nên đi primary hoặc dùng một consistency mechanism rõ ràng. Reads có thể chấp nhận eventual consistency mới nên được phân phối sang standby, sau khi kiểm tra health và replay lag. Không thể chỉ nhìn từ khóa SELECT hoặc TCP port để chọn backend.

Application-side routing giúp business logic quyết định consistency; proxy/load balancer cung cấp endpoint theo role; PgBouncer quản lý và multiplex connections. Pool mode phải tương thích với session features, và pool sizes phải được tính trên tổng instances/users/databases cùng admin/replication headroom.

**Sau failover, connection pool phải được làm mới có chủ đích.** DNS update không chuyển các TCP sockets đã mở. Hãy fence old primary, promote và xác minh node mới, cập nhật endpoints, reconnect/drain pooler, soft-evict application connections và kiểm tra host/role của connections mới. Credential và TLS rotation cũng cần quy trình refresh tương tự.

Cuối cùng, retry phải xét transaction outcome: mất kết nối trong lúc COMMIT có thể để lại kết quả không xác định ở client. Bounded retries, exponential backoff, jitter và idempotency bảo vệ ứng dụng khỏi duplicate effects và connection storms. **Routing, health checks, pool lifecycle, replication lag và failover orchestration phải được kiểm thử cùng nhau** để đạt được tính sẵn sàng cao trong thực tế.

