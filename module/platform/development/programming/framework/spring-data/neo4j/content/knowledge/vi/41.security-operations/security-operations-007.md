# Health indicator, chỉ số driver/pool và truy vấn chậm

## Mục tiêu bài học

Một ứng dụng Spring Data Neo4j (SDN) có thể khởi động thành công nhưng vẫn gặp lỗi kết nối sau đó, cạn connection pool khi tải tăng hoặc trả response chậm do một số truy vấn Cypher. Để vận hành ổn định, cần theo dõi trạng thái kết nối, thời gian truy vấn, khả năng cấp connection và tải của Neo4j server.

Bài học này tập trung vào ba lớp quan sát:

- **Health indicator:** xác định ứng dụng có thể kết nối và thực thi thao tác cơ bản với Neo4j hay không.
- **Driver và connection pool metrics:** theo dõi thời gian chờ lấy connection, giới hạn pool, truy vấn từ ứng dụng và tải Bolt ở phía server.
- **Slow query diagnostics:** tìm truy vấn chậm, phân biệt thời gian lập kế hoạch, thực thi và chờ khóa, sau đó kiểm tra query plan.

Các ví dụ dùng Spring Boot Actuator, Micrometer, Neo4j Java Driver và Neo4j Operations Manual. Một số thuộc tính và cách instrument thay đổi giữa Spring Boot 3.x, 4.x và các major của Neo4j Java Driver; hãy đối chiếu phiên bản thực tế của dự án trước khi áp dụng.

## 1. Ba lớp quan sát và câu hỏi cần trả lời

Không có một metric đơn lẻ nào mô tả đầy đủ sức khỏe của tầng dữ liệu. Hãy phân chia tín hiệu theo nơi phát sinh:

| Lớp | Tín hiệu | Câu hỏi cần trả lời |
|---|---|---|
| Ứng dụng Spring Boot | Health, HTTP latency, repository invocation | Ứng dụng có phục vụ được request và truy cập Neo4j không? |
| Neo4j Java Driver | Query observation, acquisition timeout, pool configuration | Ứng dụng có chờ connection hoặc thực thi query lâu không? |
| Neo4j server | Bolt connections, transaction, page cache, query log | Server có quá tải, chờ khóa hoặc chạy query tốn tài nguyên không? |

Một request chậm có thể do nhiều nguyên nhân:

- Ứng dụng chờ lấy connection từ pool.
- Mạng giữa ứng dụng và Neo4j có độ trễ hoặc lỗi.
- Cypher mất nhiều thời gian lập kế hoạch hoặc thực thi.
- Query phải chờ khóa do transaction khác.
- Server thiếu CPU, heap, page cache hoặc tài nguyên I/O.
- SDN phải hydrate một graph lớn hoặc chuyển đổi nhiều object sau khi server trả kết quả.
- Service giữ transaction mở trong lúc thực hiện công việc không liên quan đến database.

Vì vậy, khi điều tra cần đối chiếu thời gian ở tầng HTTP, repository/driver và query log. Không nên kết luận server chậm chỉ từ thời gian response của endpoint.

## 2. Health indicator của Neo4j trong Spring Boot

Spring Boot Actuator cung cấp health endpoint để health monitor, load balancer hoặc nền tảng triển khai kiểm tra trạng thái ứng dụng.

Khi dependency Actuator và Neo4j auto-configuration được bật, Spring Boot có thể tự đăng ký Neo4j health contributor. Neo4jHealthIndicator kiểm tra trạng thái Neo4j bằng cách thực thi một câu lệnh Cypher và lấy thông tin server/database. Ứng dụng không cần tự tạo một query phức tạp chỉ để xác định kết nối còn hoạt động.

Các endpoint thường dùng:

| Endpoint | Mục đích |
|---|---|
| GET /actuator/health | Trạng thái tổng thể và các health component |
| GET /actuator/health/neo4j | Trạng thái riêng của Neo4j contributor |
| GET /actuator/health/readiness | Kiểm tra ứng dụng đã sẵn sàng nhận traffic |
| GET /actuator/health/liveness | Kiểm tra tiến trình ứng dụng còn sống |

Với ứng dụng reactive, Spring Boot có health indicator reactive tương ứng. Hãy kiểm tra stack imperative hay reactive để biết contributor nào được auto-configure.

### Phân biệt liveness và readiness

Hai probe có ý nghĩa vận hành khác nhau:

- **Liveness** trả lời tiến trình có còn hoạt động hay không. Không nên đưa dependency bên ngoài như Neo4j vào liveness. Nếu Neo4j tạm thời mất kết nối, Kubernetes có thể liên tục restart mọi instance ứng dụng, tạo thêm tải và làm sự cố kéo dài.
- **Readiness** trả lời instance có đủ điều kiện nhận request hay không. Nếu phần lớn request của ứng dụng bắt buộc truy cập Neo4j, có thể đưa contributor neo4j vào readiness group.

Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
      roles: OPS
      group:
        readiness:
          include: readinessState,neo4j
```

Cấu hình này bật health probes, thêm Neo4j vào readiness group và chỉ hiển thị chi tiết health cho role được ủy quyền. Nếu ứng dụng vẫn có thể phục vụ một số request khi Neo4j tạm thời không khả dụng, hãy cân nhắc readiness theo khả năng nghiệp vụ thực tế thay vì loại toàn bộ instance khỏi traffic.

Không nên đưa health, metrics và các endpoint quản trị ra mạng công khai. Hãy giới hạn bằng Spring Security, network policy hoặc management port riêng. Chi tiết health có thể chứa tên database, thông tin server và nguyên nhân lỗi kết nối.

### Kiểm tra health thủ công

Sau khi chạy ứng dụng, gọi:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/neo4j
curl -i http://localhost:8080/actuator/health/readiness
```

Kết quả thường có trạng thái như UP, DOWN, OUT_OF_SERVICE hoặc UNKNOWN, tùy health contributor và trạng thái tổng hợp. Nếu Neo4j contributor là DOWN, hãy đọc exception gốc ở log ứng dụng và kiểm tra URI, xác thực, quyền truy cập database, TLS và khả năng kết nối mạng.

Health indicator xác nhận một thao tác nhỏ có thể thực hiện được tại thời điểm kiểm tra. Nó không chứng minh mọi repository query đều đúng, không đo được độ trễ truy vấn nghiệp vụ và cũng không đảm bảo pool còn đủ capacity khi tải tăng.

## 3. Tránh tạo tải từ health check

Health endpoint có thể được gọi lặp lại bởi orchestrator, load balancer và monitoring system. Nếu mỗi lần kiểm tra chạy nhiều query hoặc hydrate một graph lớn, chính health check sẽ tạo thêm tải.

Nên áp dụng các nguyên tắc:

1. Chỉ dùng health indicator có thao tác nhẹ và ổn định.
2. Không truy vấn toàn bộ node hoặc relationship để kiểm tra kết nối.
3. Đặt timeout của probe phù hợp với thời gian phản hồi dự kiến.
4. Không đặt tần suất probe quá dày.
5. Không đưa kiểm tra sâu như migration, index scan hoặc business validation vào readiness.
6. Nếu ứng dụng có nhiều database, xác định database nào là dependency bắt buộc của request trước khi nhóm health contributor.

Có thể gọi Driver.verifyConnectivity() khi ứng dụng khởi tạo để phát hiện sớm cấu hình kết nối sai. Tuy nhiên, đây là kiểm tra tại thời điểm startup; nó không thay thế health check trong suốt vòng đời ứng dụng.

## 4. Bật Actuator metrics và Micrometer

Spring Boot Actuator sử dụng Micrometer làm facade cho metrics. Khi có registry phù hợp, metric có thể được xuất tới Prometheus, OTLP, Datadog, New Relic hoặc hệ thống quan sát khác.

Dependency Gradle thường dùng:

```groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-actuator"
    runtimeOnly "io.micrometer:micrometer-registry-prometheus"
}
```

Spring Boot quản lý version của Micrometer qua dependency management. Không tự thêm version khác nếu dự án đã dùng Spring Boot BOM.

Ví dụ bật các endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    metrics:
      access: read-only
    prometheus:
      access: read-only
```

Truy cập:

- /actuator/metrics để xem danh sách meter name đang có.
- /actuator/metrics/{name} để xem một meter cụ thể.
- /actuator/prometheus để scrape metric theo định dạng Prometheus.

Tên dùng ở endpoint metrics là tên meter Micrometer, không nhất thiết giống tên đã được chuẩn hóa khi gửi tới backend. Ví dụ, Prometheus có thể chuyển dấu chấm thành dấu gạch dưới.

Không giả định mọi meter đều được tạo sẵn. Danh sách thực tế phụ thuộc dependency, phiên bản Spring Boot, Driver, registry và các điều kiện auto-configuration.

## 5. Theo dõi repository và Driver observations

Spring Boot có thể tự instrument lời gọi Spring Data repository. Metric mặc định thường dùng tên:

```text
spring.data.repository.invocations
```

Metric này giúp xem tần suất và thời gian gọi repository. Nó hữu ích để phát hiện repository method được gọi quá nhiều hoặc có latency tăng. Tuy nhiên, metric repository không cung cấp đầy đủ chi tiết về connection pool hoặc query plan phía Neo4j.

Với Neo4j Java Driver, Spring Boot 4.x có auto-configuration đăng ký MicrometerObservationProvider cho Driver được auto-configure khi ObservationRegistry và lớp MicrometerObservationProvider có trên classpath. Module Micrometer Observation của Driver 6.x có thể được thêm bằng dependency:

```groovy
runtimeOnly "org.neo4j.driver:neo4j-java-driver-observation-micrometer"
```

Chọn cùng release line với Neo4j Java Driver. Nếu dependency management của dự án chưa quản lý module này, dùng Neo4j Java Driver BOM cùng version với Driver. Provider cho phép Driver phát observations để Micrometer xuất metrics và traces khi có registry/handler phù hợp. Spring Boot auto-configuration có điều kiện trên ObservationRegistry và MicrometerObservationProvider, vì vậy thiếu một trong hai thành phần thì Driver observations không được bật theo đường này. Observability API của Driver 6.x hiện được đánh dấu Preview, vì vậy cần kiểm tra lại khi nâng major/minor.

Nếu ứng dụng tự tạo Driver bean, hãy kiểm tra cấu hình observability của Driver đó. Auto-configuration dành cho Driver do Spring Boot quản lý không có nghĩa mọi Driver tự tạo đều tự động được instrument. Spring Boot cung cấp extension point ConfigBuilderCustomizer để tùy biến cấu hình Driver.

### Phân biệt observation với pool gauge

Một observation về query giúp đo hoạt động và thời gian của thao tác Driver. Pool gauge biểu diễn trạng thái tức thời của connection pool, chẳng hạn số connection đang được sử dụng hoặc còn nhàn rỗi. Hai loại tín hiệu này trả lời câu hỏi khác nhau.

Không nên giả định rằng chỉ cần thêm Actuator là mọi chỉ số pool đều xuất hiện. Hãy mở /actuator/metrics và xác nhận meter thực tế của đúng phiên bản Driver.

Một khác biệt cần chú ý giữa các phiên bản Spring Boot:

| Phiên bản | Cấu hình/đường observability |
|---|---|
| Spring Boot 3.5.x | Có thuộc tính spring.neo4j.pool.metrics-enabled, mặc định false, trong application properties |
| Spring Boot 4.2.x | Tài liệu hiện hành không còn liệt kê thuộc tính trên; Neo4j auto-configuration dùng MicrometerObservationProvider cho Driver được auto-configure |

Không sao chép spring.neo4j.pool.metrics-enabled từ cấu hình Boot 3.5 vào Boot 4.2 rồi cho rằng pool metrics đã được bật. Hãy xác định version của Boot và Neo4j Java Driver trước khi cấu hình.

Ví dụ bật pool metrics theo cấu hình Spring Boot 3.5.x:

```yaml
spring:
  neo4j:
    pool:
      metrics-enabled: true
```

Với Neo4j Java Driver 6.x, hai module observability có vai trò khác nhau: neo4j-java-driver-observation-metrics chứa bộ metrics thử nghiệm trước đây của Driver; neo4j-java-driver-observation-micrometer tích hợp với Micrometer Observation. Đây là các module riêng và tính năng observability của Driver 6.x đang ở trạng thái Preview. Không mặc định rằng Micrometer provider tự động xuất mọi pool gauge; hãy kiểm tra meter thực tế và tài liệu của release đang dùng.

Nếu cần thử bộ metrics gốc của Driver 6.x, module neo4j-java-driver-observation-metrics là một lựa chọn riêng. Module này cũng thuộc nhóm observability Preview; đánh giá meter và độ ổn định trên đúng release trước khi dùng trong production.

### Kiểm tra metric repository

Ví dụ truy vấn meter:

```bash
curl "http://localhost:8080/actuator/metrics/spring.data.repository.invocations"
```

Có thể lọc theo tag nếu meter công bố tag tương ứng:

```bash
curl "http://localhost:8080/actuator/metrics/spring.data.repository.invocations?tag=repository:CustomerRepository"
```

Tag repository mặc định dùng simple class name; các tag khác gồm method, state và exception. Có thể gắn @Timed vào repository interface hoặc method nếu chỉ muốn đo một số lời gọi, hoặc tắt auto-time bằng management.metrics.data.repository.autotime.enabled. Hãy đọc phần availableTags từ response trước khi dùng tag trong dashboard.

Không gắn email, customer ID, query parameter hoặc chuỗi Cypher đầy đủ thành metric tag. Các giá trị có số lượng biến thể rất lớn sẽ làm tăng cardinality, chi phí lưu trữ và có thể làm lộ dữ liệu. Dùng trace hoặc log có kiểm soát cho thông tin chi tiết theo từng request.

## 6. Connection pool của Neo4j Java Driver

Neo4j Java Driver quản lý connection pool và được thiết kế để dùng chung trong toàn ứng dụng. Driver thread-safe; session và transaction có vòng đời ngắn hơn, không nên chia sẻ giữa nhiều thread.

Một Driver duy trì pool cho từng Neo4j server ở xa. Với routing driver trong cluster, pool có thể tồn tại cho nhiều server mà Driver giao tiếp. Vì vậy, giới hạn pool không nhất thiết là tổng số connection của toàn cluster.

Các thuộc tính pool quan trọng trong Spring Boot:

| Property | Ý nghĩa |
|---|---|
| spring.neo4j.pool.max-connection-pool-size | Số connection tối đa trong pool cho một server mà Driver kết nối; Driver duy trì pool riêng cho mỗi server từ xa |
| spring.neo4j.pool.connection-acquisition-timeout | Thời gian tối đa Driver thử lấy connection từ pool hoặc tạo connection mới |
| spring.neo4j.pool.max-connection-lifetime | Tuổi tối đa của connection trước khi Driver loại bỏ |
| spring.neo4j.pool.idle-time-before-connection-test | Thời gian idle trước khi connection được kiểm tra liveness khi mượn lại |
| spring.neo4j.pool.log-leaked-sessions | Bật log để phát hiện session bị giữ quá lâu hoặc không được đóng |
| spring.neo4j.connection-timeout | Timeout cho thao tác mượn connection từ pool theo mô tả của Spring Boot |

Ví dụ minh họa:

```yaml
spring:
  neo4j:
    pool:
      max-connection-pool-size: 80
      connection-acquisition-timeout: 3s
      max-connection-lifetime: 1h
      log-leaked-sessions: true
```

Giá trị 80 và 3s chỉ là ví dụ cấu hình, không phải mức tối ưu mặc định. Hãy chọn theo concurrency của ứng dụng, thời gian giữ connection, số instance ứng dụng và giới hạn tài nguyên Neo4j server.

### Tính tổng connection khi scale ứng dụng

Giả sử mỗi instance ứng dụng có một Driver và pool tối đa 80 connection tới cùng một Neo4j server. Nếu chạy 6 instance, số connection tối đa có thể được tạo từ các pool này xấp xỉ:

\[
6 \times 80 = 480
\]

Đây chưa tính connection từ ứng dụng khác, công cụ quản trị, monitoring hoặc các pool khác. Với routing driver, mỗi server có thể có pool riêng; cần tính theo topology và số server mà Driver thực sự kết nối.

Đừng tăng pool size chỉ vì thấy request chậm. Pool lớn hơn có thể đẩy nhiều query đồng thời lên Neo4j, làm tăng contention, CPU và thời gian chờ khóa. Trước khi thay đổi, kiểm tra connection acquisition, thời gian query và tải Bolt ở server.

### Nhận diện dấu hiệu pool bị bão hòa

Một số dấu hiệu thường gặp:

- Request chậm tăng khi số request đồng thời tăng.
- Driver phát sinh lỗi timeout khi acquisition connection.
- Pool thường xuyên đạt giới hạn cấu hình.
- Server query latency không tăng tương ứng với latency ở ứng dụng.
- Session hoặc transaction được giữ lâu hơn dự kiến.
- Nhiều connection bị chiếm bởi query trả lượng dữ liệu lớn hoặc stream chưa được consume/close.

Kiểm tra service có mở session trực tiếp mà quên đóng hay không. Nếu dùng Neo4j Java Driver trực tiếp, dùng try-with-resources hoặc đóng session/transaction theo đúng lifecycle. Với SDN repository/template, tránh giữ transaction mở trong lúc gọi HTTP, chờ người dùng hoặc thực hiện xử lý không liên quan đến graph.

## 7. Phân biệt pool metrics và Bolt metrics phía server

Chỉ số pool thuộc phía client, còn Bolt metrics thuộc phía Neo4j server. Server không thể cho biết chính xác pool của một ứng dụng đang có bao nhiêu connection rảnh nếu nhiều client cùng kết nối vào một DBMS.

Neo4j Enterprise cung cấp các metric Bolt như:

| Metric | Ý nghĩa |
|---|---|
| neo4j.dbms.bolt.connections_opened | Tổng connection Bolt được mở kể từ khi server khởi động |
| neo4j.dbms.bolt.connections_closed | Tổng connection Bolt được đóng |
| neo4j.dbms.bolt.connections_running | Số connection đang thực thi Cypher hoặc trả kết quả |
| neo4j.dbms.bolt.connections_idle | Số connection Bolt đang nhàn rỗi |

Tên đầy đủ có thể có prefix khác nếu server cấu hình server.metrics.prefix. Các metric trên là số liệu của DBMS, không phải pool riêng của một instance Spring Boot.

Khi connections_running chạm giới hạn worker thread Bolt đã cấu hình, server có thể đang ở trạng thái quá tải. Cần đối chiếu với CPU, transaction, query latency và số client kết nối để xác định nguyên nhân.

### Bật và xuất metric server

Các metric tích hợp của Neo4j được quản lý bằng cấu hình server, ví dụ:

```properties
server.metrics.enabled=true
```

Neo4j Operations Manual ghi nhận metrics tích hợp này thuộc Enterprise Edition. Cách xuất có thể dùng Neo4j Ops Manager, JMX, CSV hoặc công cụ monitoring tương thích. Hãy xem danh sách metric và cấu hình export theo phiên bản server.

Các nhóm metric nên theo dõi:

- Bolt connection running/idle.
- Transaction started/committed/rolled back.
- Query execution latency.
- Page cache hit ratio và usage ratio.
- Heap, garbage collection, CPU và disk.
- Cluster health và trạng thái replication nếu chạy cluster.

Không so sánh counter tích lũy trực tiếp giữa hai thời điểm mà không tính delta theo khoảng thời gian. Với gauge, đọc giá trị tại thời điểm lấy mẫu; với histogram, xem phân phối và percentile thay vì chỉ nhìn trung bình.

## 8. Thiết lập slow query log trong Neo4j

Khi cần tìm query chậm, query log phía server là nguồn quan sát quan trọng. Với Neo4j 5.x trở lên, các cấu hình hiện hành dùng prefix db.logs.query.*. Neo4j 4.x có thể dùng tên cũ dbms.logs.query.*; cần kiểm tra tài liệu của đúng server version.

Query log hỗ trợ các mức. Tài liệu Neo4j hiện hành ghi nhận mặc định là VERBOSE, nghĩa là query được log ở cả thời điểm bắt đầu và kết thúc. Vì vậy, hãy cấu hình tường minh khi muốn chỉ lưu query chậm.

- OFF: tắt query log.
- INFO: ghi query sau khi thực thi nếu thời gian vượt ngưỡng db.logs.query.threshold.
- VERBOSE: ghi thời điểm bắt đầu và kết thúc của mọi query.

Query log là tính năng Enterprise Edition. Với môi trường cần tìm truy vấn chậm, INFO kết hợp threshold thường phù hợp hơn việc ghi mọi query ở VERBOSE.

Ví dụ cấu hình:

```properties
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
```

Ở đây, query hoàn tất sau hơn 250 ms mới được ghi vào query log. Giá trị 250 ms là ngưỡng minh họa; hãy đặt theo SLO và phân phối latency thực tế của hệ thống.

Nếu threshold là 0s, mọi query đều vượt ngưỡng. Điều này có thể tạo log rất lớn. Không nên dùng threshold bằng 0 trong production nếu mục tiêu chỉ là lọc slow query.

### Bảo vệ dữ liệu nhạy cảm trong query log

Theo tài liệu Neo4j hiện hành:

- db.logs.query.parameter_logging_enabled mặc định là true.
- db.logs.query.obfuscate_literals có thể che literal trong query text.
- Obfuscate literal không che giá trị parameter.
- db.logs.query.plan_description_enabled có thể ghi query plan nhưng làm tăng chi phí xử lý.

Do đó, nếu parameter có email, token, tên khách hàng hoặc thông tin nghiệp vụ nhạy cảm, hãy cân nhắc tắt parameter logging:

```properties
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
```

Giữ quyền đọc query log giới hạn cho nhóm vận hành được ủy quyền. Log có thể chứa câu lệnh, database, username, thời gian và thông tin kết nối. Cấu hình obfuscation cũng cần được xác nhận trên phiên bản server thực tế.

Một số phiên bản mới hỗ trợ thêm db.logs.query.obfuscate_errors để che thông tin nhạy cảm trong lỗi được ghi vào query log. Chỉ sử dụng khi phiên bản Neo4j triển khai có hỗ trợ setting này.

## 9. Đọc query log để tìm nguyên nhân chậm

Một query log entry có thể chứa nhiều dữ liệu hơn tổng thời gian thực thi. Bảng dưới đây mô tả tên field trong JSON query log; với plain-text layout, cùng thông tin được ghi dưới dạng các phần của log message.

| Trường | Ý nghĩa khi chẩn đoán |
|---|---|
| elapsedTimeMs | Tổng thời gian query |
| planning | Thời gian lập kế hoạch |
| cpu | Thời gian CPU thực thi query |
| waiting | Thời gian chờ khóa hoặc query khác |
| allocatedBytes | Bộ nhớ được cấp phát trong quá trình thực thi |
| pageHits | Số lần truy cập page cache |
| pageFaults | Số lần phải đọc page từ storage |
| database | Database chạy query |
| executingUser | User thực thi |
| query | Nội dung Cypher |
| queryParameters | Parameter nếu được bật logging |

Một vài cách đọc thường gặp:

- **Planning cao:** query plan cần nhiều thời gian lập kế hoạch; xem query shape, số label/type, statistics và query cache.
- **CPU cao:** query đang xử lý nhiều dữ liệu hoặc thực hiện nhiều phép toán.
- **Waiting cao:** query chờ khóa hoặc tài nguyên do transaction khác.
- **Page faults cao:** dữ liệu cần đọc từ storage thay vì có sẵn trong page cache.
- **Allocated bytes cao:** query tạo nhiều dữ liệu trung gian hoặc kết quả lớn.
- **Elapsed cao nhưng CPU thấp:** có thể có thời gian chờ, I/O hoặc contention; đối chiếu các trường còn lại.

Không kết luận chỉ từ một dòng log. Hãy tìm nhiều lần thực thi cùng query shape, xem percentile và đối chiếu với tải của server trong cùng khoảng thời gian.

## 10. Theo dõi transaction mở lâu

Một query có thể chạy nhanh nhưng transaction vẫn mở lâu. Ví dụ, service đọc dữ liệu từ Neo4j, sau đó gọi API thanh toán hoặc chờ một tác vụ khác trước khi commit. Connection và lock có thể bị giữ trong thời gian không cần thiết.

Neo4j Enterprise hỗ trợ transaction logging trong query log:

```properties
db.logs.query.transaction.enabled=INFO
db.logs.query.transaction.threshold=2s
```

Cấu hình này ghi nhận transaction mở lâu hơn 2 giây sau khi transaction kết thúc. Ngưỡng 2 giây là ví dụ; chọn theo đặc tính workload.

Khi query log cho thấy từng query ngắn nhưng transaction dài, hãy kiểm tra:

- Service có giữ @Transactional bao trùm cả lời gọi HTTP hoặc xử lý file không?
- Có đọc toàn bộ result trước khi xử lý không?
- Có xử lý từng record trong transaction quá lớn không?
- Có khóa hoặc contention từ transaction đồng thời không?
- Có giữ session hoặc cursor lâu hơn cần thiết không?

Đặt transaction boundary gần thao tác graph cần commit. Tránh giữ transaction trong khi chờ tài nguyên bên ngoài.

## 11. Dùng EXPLAIN và PROFILE để phân tích query

Sau khi tìm được query chậm, kiểm tra execution plan thay vì chỉ chỉnh code Java.

- EXPLAIN lập kế hoạch thực thi nhưng không chạy query.
- PROFILE thực thi query và thu thập thống kê runtime, ví dụ số row và database hits.

Ví dụ:

```cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c;
```

Sau khi đã kiểm tra query và chọn môi trường an toàn, có thể chạy:

```cypher
PROFILE
MATCH (c:Customer {email: $email})
RETURN c;
```

PROFILE thực sự chạy câu lệnh. Với query ghi như CREATE, MERGE, SET hoặc DELETE, thao tác có thể thay đổi dữ liệu. Hãy chạy trên dữ liệu kiểm thử/staging hoặc dùng transaction có rollback theo quy trình kiểm thử được kiểm soát.

Khi đọc plan, chú ý:

- Node/relationship scan có đọc nhiều dữ liệu không cần thiết không?
- Có sử dụng index seek khi điều kiện lọc phù hợp không?
- Số row trung gian có tăng mạnh ở một operator không?
- Có expand qua relationship với cardinality lớn không?
- Có sort, aggregation hoặc collect trên tập dữ liệu quá lớn không?
- Database hits có tăng bất thường so với số record trả về không?

Không phải mọi scan đều là lỗi. Một query cần trả về phần lớn graph có thể phải scan. Đánh giá plan dựa trên mục đích query, lượng dữ liệu và SLO.

## 12. Đối chiếu latency ở ứng dụng và server

Một cách hữu ích để khoanh vùng là so sánh ba mốc:

1. HTTP request duration.
2. Repository/Driver observation duration.
3. Query execution time trong Neo4j query log.

Ví dụ:

| HTTP | Repository/Driver | Query log | Hướng điều tra |
|---:|---:|---:|---|
| Cao | Cao | Cao | Query, server load, lock, page cache |
| Cao | Cao | Thấp | Pool acquisition, mạng, fetch result hoặc mapping |
| Cao | Thấp | Thấp | Service logic, HTTP downstream, serialization |
| Thấp | Cao | Cao | Request có thể chưa phản ánh đầy đủ query chậm hoặc timeout/retry |
| Cao đột biến | Acquisition timeout | Không có query tương ứng | Pool hết connection hoặc server không cấp connection |

Đây là cách phân loại ban đầu. Một request có thể chạy nhiều query, query retry hoặc query chạy song song, vì vậy cần trace ID, timestamp và query metadata phù hợp để liên kết các tín hiệu.

Nếu thời gian query ở server thấp nhưng repository method vẫn chậm, kiểm tra:

- Connection acquisition và network latency.
- Result có quá nhiều record hoặc graph depth quá lớn không?
- SDN có phải hydrate nhiều entity và relationship không?
- Có converter hoặc callback tốn thời gian không?
- Service có gọi repository nhiều lần theo vòng lặp không?

Nếu server query time cao, tập trung vào query plan, index, lock và tài nguyên server.

## 13. Gắn metadata để tìm query của một nghiệp vụ

Khi một service có nhiều query khác nhau, cần biết query nào thuộc luồng nghiệp vụ nào. Có thể gắn metadata/annotation cho transaction nếu phiên bản Neo4j và API Driver hỗ trợ, sau đó dùng metadata đó trong query log.

Ví dụ Cypher có thể dùng transaction metadata thông qua API tương ứng của Driver:

```java
import java.util.Map;

import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

try (var session = driver.session(
        SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

    session.executeRead(
            tx -> tx.run(
                    "MATCH (c:Customer {customerId: $id}) RETURN c",
                    Map.of("id", customerId)
            ).list(),
            TransactionConfig.builder()
                    .withMetadata(Map.of(
                            "operation", "customer-profile-read",
                            "component", "customer-service"
                    ))
                    .build()
    );
}
```

API overload và cách truyền TransactionConfig có thể khác giữa các major Driver. Ví dụ trên minh họa ý tưởng metadata transaction; hãy đối chiếu chữ ký method của Driver đang dùng trước khi đưa vào code.

Metadata nên là nhãn nghiệp vụ có số lượng giá trị hữu hạn, ví dụ operation=customer-profile-read. Không đưa access token, email, customer ID hoặc dữ liệu nhạy cảm vào metadata. Mục tiêu là lọc log theo use case, không tạo thêm một nơi lưu dữ liệu cá nhân.

## 14. Các lỗi thường gặp khi quan sát Driver và pool

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| /actuator/health/neo4j không tồn tại | Thiếu Actuator hoặc health auto-configuration không được kích hoạt | Kiểm tra dependency và điều kiện auto-config |
| Health DOWN dù ứng dụng vừa khởi động | URI, credential, TLS, quyền database hoặc mạng sai | Kiểm tra exception gốc và verifyConnectivity() |
| Health UP nhưng endpoint vẫn chậm | Health chỉ chạy thao tác nhỏ | Theo dõi repository, Driver và query log |
| Không thấy Neo4j meter trong /actuator/metrics | Driver không được instrument hoặc registry chưa có | Kiểm tra Driver auto-config, Observation và registry |
| Cấu hình spring.neo4j.pool.metrics-enabled không có tác dụng | Thuộc tính thuộc Boot 3.5, không còn trong Boot 4.2 | Dùng hướng observability đúng version |
| Connection acquisition timeout | Pool hết connection, query giữ connection lâu hoặc server không đáp ứng | Kiểm tra pool, session lifecycle, query latency và Bolt |
| Tăng pool nhưng latency tăng thêm | Server bị đẩy tới concurrency quá cao | Giảm contention, tối ưu query và đánh giá capacity |
| Server Bolt connections cao | Nhiều client hoặc pool lớn cùng kết nối | Đối chiếu số app replica và pool size mỗi server |
| Query log chứa dữ liệu nhạy cảm | Parameter/literal logging chưa được giới hạn | Tắt parameter logging, obfuscate literals và giới hạn quyền đọc log |
| Query log quá nhiều | Dùng VERBOSE hoặc threshold quá thấp | Chuyển INFO, đặt threshold phù hợp |
| Query chậm nhưng CPU thấp | Có thể đang chờ khóa hoặc I/O | Đọc waiting, page faults và transaction log |
| Query nhanh nhưng transaction dài | Service giữ transaction mở khi xử lý công việc khác | Thu hẹp transaction boundary |
| PROFILE làm thay đổi dữ liệu | PROFILE đã thực thi câu lệnh ghi | Chỉ profile trên dữ liệu thử nghiệm hoặc quy trình rollback an toàn |

## 15. Quy trình xử lý một sự cố query chậm

Khi nhận cảnh báo latency tăng, thực hiện theo thứ tự:

1. Xác định thời gian bắt đầu, phạm vi ảnh hưởng và endpoint bị ảnh hưởng.
2. Kiểm tra health của ứng dụng và Neo4j.
3. So sánh HTTP latency với repository/Driver observations.
4. Kiểm tra connection acquisition timeout và pool configuration.
5. Tìm query log entry tương ứng theo thời gian, database, user và query shape.
6. Đọc elapsed, planning, CPU, waiting, allocated bytes, page hits và page faults.
7. Dùng EXPLAIN để xem plan; dùng PROFILE trong môi trường được kiểm soát nếu cần runtime statistics.
8. Kiểm tra index, cardinality, relationship expansion và số record trả về.
9. Kiểm tra transaction mở lâu và lock contention.
10. Thay đổi một yếu tố tại một thời điểm, sau đó đo lại latency và tải server.
11. Ghi lại query shape, dữ liệu thử nghiệm, plan và kết quả trước/sau.

Không bắt đầu bằng cách tăng pool size hoặc thêm index hàng loạt. Một thay đổi thiếu bằng chứng có thể làm tăng tải hoặc khiến write path đắt hơn mà không giải quyết nguyên nhân.

## 16. Thiết kế dashboard và cảnh báo

Một dashboard vận hành nên có nhóm panel riêng cho ứng dụng và database.

| Nhóm | Chỉ số gợi ý | Cảnh báo khi |
|---|---|---|
| Health | Neo4j health, readiness | Contributor DOWN kéo dài |
| Request | HTTP p95/p99, error rate | Latency hoặc error rate vượt SLO |
| Repository | Invocation count, duration, error | Một repository có latency tăng bất thường |
| Driver | Query observations, acquisition timeout | Acquisition timeout xuất hiện hoặc tăng liên tục |
| Pool | Các pool gauge thực sự được expose bởi Driver/version | Pool thường xuyên chạm giới hạn |
| Bolt | Connections running/idle | Running tiến sát giới hạn server |
| Database | Transaction, query latency | Throughput giảm hoặc latency tăng |
| Storage/memory | Page cache, heap, GC, disk | Page cache hit ratio giảm, heap/GC bất thường |
| Slow query | Query log theo query shape | Query vượt threshold hoặc xuất hiện liên tục |

Với metric dạng counter, dùng rate hoặc delta theo thời gian. Với timer, theo dõi p95/p99 và histogram nếu backend hỗ trợ. Với gauge, theo dõi xu hướng và thời gian duy trì trạng thái bất thường.

Cảnh báo cần có thời gian duy trì để tránh false positive do một spike ngắn. Cũng cần giới hạn cardinality: không tạo metric riêng cho mỗi query text, parameter, email hoặc ID.

## 17. Bảo vệ endpoint và dữ liệu quan sát

Actuator, metrics và query log đều có thể tiết lộ thông tin vận hành. Hãy áp dụng các nguyên tắc:

- Chỉ expose endpoint cần thiết.
- Giới hạn quyền truy cập /actuator/metrics và /actuator/prometheus trong mạng quản trị.
- Health details chỉ hiển thị cho role được ủy quyền.
- Không log parameter nhạy cảm nếu không có nhu cầu điều tra được phê duyệt.
- Dùng obfuscation và retention phù hợp cho query log.
- Không đưa token, credential hoặc dữ liệu định danh vào metric tag.
- Giới hạn quyền đọc log và dashboard theo vai trò.
- Không gửi toàn bộ query log sang hệ thống bên ngoài nếu chưa đánh giá dữ liệu chứa trong đó.

Health endpoint phục vụ probe có thể cần truy cập từ orchestrator; điều đó không đồng nghĩa mọi chi tiết health phải công khai.

## 18. Tự kiểm tra

1. Neo4jHealthIndicator kiểm tra điều gì?
2. Vì sao health UP không chứng minh mọi repository query đều nhanh?
3. Khác biệt giữa liveness và readiness là gì?
4. Vì sao không nên đưa Neo4j vào liveness probe?
5. Spring Boot Actuator và Micrometer có vai trò gì trong metrics?
6. spring.data.repository.invocations cho biết loại thông tin nào?
7. Khác biệt giữa Driver observation và connection pool gauge là gì?
8. Spring Boot 3.5 và 4.2 khác nhau thế nào về cấu hình pool metrics?
9. Vì sao một Driver nên được dùng chung trong toàn ứng dụng?
10. connection-acquisition-timeout có ý nghĩa gì?
11. Vì sao tăng max-connection-pool-size không luôn cải thiện latency?
12. Khác biệt giữa Bolt metrics ở server và pool metrics ở client là gì?
13. Neo4j query log INFO và VERBOSE khác nhau như thế nào?
14. Vì sao cần tắt parameter logging khi parameter có dữ liệu nhạy cảm?
15. Các trường planning, cpu, waiting và pageFaults giúp chẩn đoán điều gì?
16. Vì sao transaction có thể mở lâu dù từng query đều nhanh?
17. Khác biệt giữa EXPLAIN và PROFILE là gì?
18. Vì sao không nên đưa query text hoặc customer ID vào metric tag?

Hãy bật Actuator cho một ứng dụng SDN, kiểm tra health contributor của Neo4j và thêm Neo4j vào readiness group. Ghi nhận meter name thực tế trong /actuator/metrics. Tiếp theo, kiểm tra pool configuration và mô phỏng nhiều request đồng thời để quan sát acquisition timeout. Trên Neo4j Enterprise test environment, bật query log mức INFO với threshold phù hợp và tắt parameter logging. Tạo một query chậm có kiểm soát, đọc query log, chạy EXPLAIN/PROFILE trong môi trường thử nghiệm, sau đó tối ưu query và so sánh latency trước/sau.

## Tài liệu tham khảo

- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/health.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot API — Neo4jHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/neo4j/health/Neo4jHealthIndicator.html)
- [Spring Boot API — Neo4jObservationAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/neo4j/autoconfigure/observation/Neo4jObservationAutoConfiguration.html)
- [Neo4j Java Driver — Driver API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Driver.html)
- [Neo4j Java Driver — Config API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.html)
- [Neo4j Java Driver — ConfigBuilder API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.ConfigBuilder.html)
- [Neo4j Java Driver — Session API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Session.html)
- [Neo4j Java Driver — ObservationProvider API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/observation/ObservationProvider.html)
- [Neo4j Java Driver — Micrometer Observation module](https://central.sonatype.com/artifact/org.neo4j.driver/neo4j-java-driver-observation-micrometer)
- [Neo4j Java Driver — Metrics observation module](https://central.sonatype.com/artifact/org.neo4j.driver/neo4j-java-driver-observation-metrics)
- [Neo4j Java Driver — Official repository and observability release notes](https://github.com/neo4j/neo4j-java-driver)
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Metrics Reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Essential Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
