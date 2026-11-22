# Cạn pool, kết nối bị giữ lâu và lỗi khi hủy luồng

Trong ứng dụng Spring Data Relational R2DBC, connection pool cấp các kết nối database cho những publisher đang thực thi. Pool cạn thường biểu hiện bằng request chờ lâu, lỗi acquire timeout hoặc throughput giảm dù ứng dụng vẫn còn tài nguyên CPU. Tuy nhiên, “pool cạn” chỉ là triệu chứng: nguyên nhân có thể là query chậm, transaction giữ connection quá lâu, luồng đọc bị downstream tiêu thụ chậm, concurrency vượt khả năng pool, thao tác blocking hoặc connection không được đóng đúng cách.

Cancellation cũng cần được hiểu chính xác. Khi subscriber hủy một Mono hoặc Flux, Reactor gửi tín hiệu cancel ngược upstream. Driver có thể cố hủy query đang chạy và Spring transaction infrastructure có thể rollback/cleanup transaction, nhưng mức độ dừng tức thì phụ thuộc driver, database và vị trí cancellation. Một publisher bị hủy không tự động chứng minh database đã ngừng xử lý hoặc connection đã được trả về pool ngay lập tức.

Bài học này trình bày vòng đời connection trong R2DBC, cách nhận diện pool saturation và connection leak, các nguyên nhân giữ connection lâu, cách thiết kế transaction và stream ngắn, cách xử lý cancellation, timeout, metrics, kiểm thử và load test. Các ví dụ dùng Spring Boot, Reactor và PostgreSQL; tên property cụ thể cần đối chiếu phiên bản Spring Boot/R2DBC Pool của dự án.

## 1. Connection pool hoạt động như thế nào?

R2DBC sử dụng ConnectionFactory để tạo hoặc cấp connection. Khi bọc một ConnectionFactory bằng pool, lời gọi tạo connection sẽ lấy một connection rảnh từ pool hoặc chờ cho tới khi có connection được trả về hay timeout xảy ra.

Vòng đời đơn giản:

~~~mermaid
flowchart TD
    A[Reactive request subscribed] --> B[Acquire connection from pool]
    B --> C{Connection available?}
    C -->|Yes| D[Execute SQL]
    C -->|No| E[Wait in acquire queue]
    E --> F{Available before timeout?}
    F -->|Yes| D
    F -->|No| G[Acquire timeout error]
    D --> H[Consume result]
    H --> I[Complete, error or cancel]
    I --> J[Cleanup transaction/resource]
    J --> K[Return connection to pool]
    K --> L[Available for another request]
~~~

Connection được giữ trong khoảng thời gian từ lúc acquire tới lúc được release. Khoảng thời gian này không chỉ gồm thời gian database thực thi SQL. Nó có thể gồm:

- Chờ transaction bắt đầu hoặc hoàn tất.
- Đọc kết quả từ database.
- Chờ downstream yêu cầu thêm phần tử do backpressure.
- Thực hiện xử lý ứng dụng khi vẫn nằm trong transaction.
- Chờ một lời gọi HTTP hoặc message broker nếu code đặt thao tác đó bên trong transaction.
- Rollback hoặc cleanup sau lỗi/cancellation.

Pool quản lý số connection vật lý đang mở và số connection đang được mượn. Khi code dùng Spring Data repository, DatabaseClient hoặc R2dbcEntityTemplate theo đúng lifecycle, framework quản lý việc acquire/release. Khi tự làm việc với Connection, ứng dụng phải bảo đảm đóng connection ở mọi đường hoàn tất, lỗi và hủy.

## 2. Phân biệt pool saturation, connection leak và query chậm

Ba tình trạng này có thể tạo cùng một triệu chứng acquire timeout nhưng cách xử lý khác nhau.

| Tình trạng | Dấu hiệu thường gặp | Nguyên nhân điển hình |
| --- | --- | --- |
| Pool saturation | Active connection chạm max, pending acquire tăng trong giờ cao điểm. | Concurrency cao, pool nhỏ so với workload hoặc thời gian giữ connection dài. |
| Connection leak | Connection đã mượn không được trả lại; active không giảm cả sau khi tải kết thúc. | Không close connection, resource cleanup sai hoặc publisher bị tách khỏi lifecycle. |
| Query chậm/lock wait | Connection active lâu, database cho thấy query chạy lâu hoặc chờ lock. | SQL thiếu index, query plan xấu, lock contention, I/O chậm. |
| Downstream chậm | Query stream vẫn active nhưng ứng dụng tiêu thụ kết quả chậm. | Flux được chuyển trực tiếp cho client chậm hoặc xử lý từng row quá lâu. |
| Acquire/create bottleneck | Pending tăng dù active chưa đạt max hoặc connection mới tạo chậm. | Database không nhận thêm session, DNS/TLS/network chậm hoặc connection creation lỗi. |

### Pool saturation không nhất thiết là leak

Nếu tải tăng đột biến và mọi connection đang phục vụ query hợp lệ, pool có thể cạn tạm thời. Khi workload hoàn tất, active giảm và pending được phục vụ. Đây là saturation do capacity hoặc workload.

### Leak có dấu hiệu kéo dài

Nếu request đã kết thúc nhưng active connections vẫn bị giữ, pool không phục hồi sau khi tải giảm, hãy tìm đường code không release resource hoặc publisher không hoàn tất. Tuy nhiên, một transaction đang chờ query/lock hoặc một Flux chưa được consume cũng có thể trông giống leak.

### Query chậm thường là nguyên nhân gốc

Tăng max pool size có thể che triệu chứng query chậm trong thời gian ngắn nhưng đồng thời làm database nhận thêm truy vấn cạnh tranh. Hãy kiểm tra query duration, execution plan, index, lock wait và database load trước khi tăng pool.

## 3. Các metrics cần theo dõi

Chỉ nhìn vào số lượng connection hiện tại thường không đủ. Theo dõi cả pool và database.

| Metric/quan sát | Ý nghĩa |
| --- | --- |
| Allocated/total connections | Tổng connection vật lý pool đang quản lý. |
| Acquired/active connections | Connection hiện được mượn bởi publisher. |
| Idle connections | Connection sẵn sàng được cấp. |
| Pending acquire | Số request đang chờ connection. |
| Acquire duration | Thời gian từ yêu cầu tới lúc nhận connection. |
| Acquire timeout count | Số lần không lấy được connection đúng hạn. |
| Connection creation time/failure | Thời gian và lỗi mở connection mới. |
| Usage duration | Thời gian connection ở trạng thái được mượn. |
| Query duration | Thời gian thực thi SQL. |
| Transaction duration | Thời gian transaction tồn tại. |
| Database sessions/lock wait | Trạng thái nhìn từ phía database. |

Nếu có Micrometer/Actuator và R2DBC Pool metrics được bật, xuất metrics sang hệ thống quan sát của dự án. Tên metric cụ thể thay đổi theo phiên bản và registry; xác nhận bằng endpoint metrics thực tế thay vì giả định tên cố định.

Nên đặt cảnh báo dựa trên xu hướng, ví dụ pending acquire tăng liên tục, active giữ sát max trong nhiều phút, acquire timeout tăng hoặc usage duration vượt ngưỡng. Một mẫu spike ngắn trong deployment không nhất thiết là sự cố nếu pool phục hồi nhanh.

### Correlate metrics giữa ứng dụng và database

Khi active connections cao, kiểm tra database cùng thời điểm:

- Có bao nhiêu session đang chạy query?
- Có session idle in transaction không?
- Có truy vấn chờ lock không?
- Có query giống nhau chạy lặp lại quá nhiều không?
- Có session lâu không hoạt động nhưng vẫn ở trạng thái transaction?
- Database có đạt giới hạn connection hoặc CPU/I/O không?

Nếu pool cho thấy connection active nhưng database không có query đang chạy, có thể ứng dụng đang giữ connection trong khi xử lý logic, chờ downstream hoặc chờ lời gọi bên ngoài.

## 4. Tính pool size theo thời gian giữ connection

Pool size không nên chọn theo số CPU hoặc số request đồng thời một cách máy móc. Một cách ước lượng ban đầu dựa trên Little’s Law:

\[
L = \lambda \times W
\]

Trong đó:

- L là số công việc trung bình đang ở trong hệ thống.
- λ là tốc độ xử lý trung bình (requests/transactions mỗi giây).
- W là thời gian trung bình một công việc giữ connection (giây).

Ví dụ: nếu workload cần 100 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 0,05 giây, số connection trung bình cần thiết theo ước lượng này là khoảng 5. Đây chỉ là mức trung bình; cần headroom cho p95/p99 latency, burst, transaction dài và workload khác.

Một connection có thể phục vụ nhiều statement tuần tự trong cùng transaction, vì vậy hãy tính theo thời gian mượn connection của transaction/use case chứ không chỉ thời gian của một SQL statement.

### Tính tổng connection toàn hệ thống

Nếu có nhiều application replica, pool size được nhân lên:

\[
C_{total} = instances \times maxPoolSize + otherClients
\]

OtherClients gồm migration job, admin tools, background workers, reporting, monitoring và các ứng dụng khác. Tổng này phải nằm trong giới hạn an toàn của database, còn chỗ cho failover và hoạt động quản trị.

Ví dụ 6 replica, mỗi replica max pool size 20 có thể mở tới 120 connection, chưa tính worker hoặc công cụ khác. Không tăng pool trên từng instance mà không tính tổng toàn cluster.

### Pool lớn hơn không luôn nhanh hơn

Database có giới hạn CPU, I/O, lock và session. Quá nhiều connection đồng thời có thể làm context switching, memory và lock contention tăng, khiến latency xấu hơn. Tăng pool chỉ có ích nếu database còn capacity và acquire queue là bottleneck thực sự.

## 5. Cấu hình R2DBC Pool trong Spring Boot

Nếu dùng R2DBC Pool, cấu hình Spring Boot thường có dạng:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:pool:postgresql://db-host:5432/orders
    username: app_user
    password: secret
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
~~~

Tên property và việc có cần prefix r2dbc:pool trong URL hay không phụ thuộc cách Spring Boot version quản lý R2DBC Pool. Một số cấu hình dùng pool.enabled cùng URL driver; hãy kiểm tra reference documentation của đúng phiên bản dự án.

Các thuộc tính thường có ý nghĩa:

- initial-size: số connection tạo ban đầu.
- max-size: giới hạn connection pool được phép quản lý.
- max-acquire-time: thời gian tối đa chờ lấy connection.
- max-create-connection-time: giới hạn thời gian tạo connection mới.
- max-idle-time: thời gian idle tối đa trước khi connection có thể bị loại bỏ.
- max-life-time: tuổi thọ tối đa của connection.
- validation: cách kiểm tra connection còn sử dụng được, nếu driver/pool cấu hình hỗ trợ.

Không chọn max-acquire-time quá dài chỉ để che tình trạng pool cạn. Acquire timeout là tín hiệu backpressure ở tầng connection: nếu mọi connection bị giữ quá lâu, chờ lâu hơn chỉ khiến request tích tụ và latency tăng.

### Acquire timeout nên có ý nghĩa vận hành

Thời gian chờ connection cần phù hợp với ngân sách latency của request. Nếu API có SLA 2 giây, để acquire chờ 30 giây có thể khiến request sống lâu hơn mức hệ thống có thể chấp nhận. Kết hợp acquire timeout với request timeout và giới hạn concurrency ở tầng ứng dụng.

### Idle và lifetime

max-idle-time và max-life-time giúp pool loại connection quá cũ hoặc idle lâu theo chính sách. Chúng không sửa được connection đang bị mượn mãi. Một connection active chưa được trả về không thể được dọn như một connection idle thông thường.

## 6. Đảm bảo resource được release đúng cách

Spring Data repository và DatabaseClient quản lý connection theo lifecycle của publisher. Với code persistence thông thường, ưu tiên dùng các abstraction này thay vì tự lấy Connection.

Nếu tự làm việc với ConnectionFactory, cần đảm bảo close ở mọi kết thúc. Trong R2DBC, close trên pooled connection thường trả connection về pool chứ không nhất thiết đóng socket vật lý.

### Dùng usingWhen cho resource reactive

Ví dụ khái quát:

~~~java
Mono<ResultValue> work =
    Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeWork(connection),
        Connection::close,
        (connection, error) -> rollbackIfNeeded(connection)
            .then(connection.close()),
        connection -> rollbackIfNeeded(connection)
            .then(connection.close())
    );
~~~

usingWhen hỗ trợ cleanup bất đồng bộ cho ba trường hợp: complete, error và cancel. Ví dụ cần điều chỉnh rollbackIfNeeded theo việc connection có transaction đang mở hay không; không gọi rollback mù nếu chưa bắt đầu transaction hoặc transaction đã kết thúc.

Với code production, cân nhắc dùng Spring ConnectionFactoryUtils hoặc transaction-aware access phù hợp khi connection phải tham gia transaction do Spring quản lý. Không tự gọi connectionFactory.create() trong một service rồi kỳ vọng connection đó tự tham gia transaction hiện tại.

### Không dùng doFinally để thay thế async cleanup

doFinally nhận tín hiệu complete/error/cancel nhưng callback của nó không phải nơi thích hợp để thực hiện cleanup bất đồng bộ cần chờ, như Connection.close() trả Publisher. Gọi close mà không subscribe/compose sẽ không bảo đảm cleanup hoàn tất.

Dùng usingWhen hoặc API resource-management được framework hỗ trợ.

### Không giữ Connection trong field

Không lưu Connection vào singleton service, static field hoặc object dùng chung giữa request. Connection được mượn theo một thao tác và không được chia sẻ tùy tiện giữa nhiều publisher/thread.

## 7. Transaction dài giữ connection lâu

Khi reactive transaction bắt đầu, transaction manager thường acquire một connection và giữ nó tới khi transaction commit hoặc rollback. Mọi thao tác nằm trong transaction có thể tiếp tục giữ connection ngay cả khi code đang chờ công việc không liên quan tới database.

Ví dụ không tốt:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
        .flatMap(order ->
            webClient.post()
                .uri(paymentUrl)
                .bodyValue(command.payment())
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .map(result -> order.withPayment(result.id()))
        )
        .flatMap(orderRepository::save);
}
~~~

Transaction có thể giữ connection trong suốt thời gian chờ HTTP payment service. Nếu dịch vụ ngoài chậm, connection bị giữ lâu dù database không thực hiện query.

### Thu hẹp transaction boundary

Thực hiện các bước không cần transaction trước, sau đó mở transaction ngắn cho các thao tác database cần atomic. Tuy nhiên, không thể đơn giản chuyển payment HTTP ra ngoài mà vẫn giả định toàn bộ quy trình là nguyên tử. Giao tiếp với hệ thống ngoài thường cần saga, idempotency hoặc outbox tùy nghiệp vụ.

Một mẫu thường gặp:

1. Validate request và thực hiện các kiểm tra không cần transaction.
2. Gọi dịch vụ ngoài theo giao thức idempotent nếu phù hợp.
3. Mở transaction ngắn để lưu trạng thái nghiệp vụ và outbox/event.
4. Commit.
5. Worker xử lý side effect sau commit.

Nếu thứ tự nghiệp vụ đòi hỏi giữ trạng thái pending trong khi chờ payment, thiết kế trạng thái và compensation rõ ràng thay vì giữ database transaction mở qua network call.

## 8. Flux streaming có thể giữ connection trong suốt quá trình consume

Một repository method trả Flux thường thực thi query khi subscribe. Khi kết quả được stream, connection có thể cần tồn tại cho tới khi result được consume hết hoặc publisher bị hủy và cleanup hoàn tất.

Ví dụ:

~~~java
@GetMapping("/people/export")
public Flux<Person> exportPeople() {
    return repository.findAll();
}
~~~

Nếu client tải chậm, downstream backpressure có thể khiến database result được tiêu thụ chậm. Connection có thể bị giữ lâu hơn thời gian database cần để tìm kết quả.

Đây không nhất thiết là leak: publisher vẫn đang hoạt động hợp lệ. Nhưng nếu nhiều client mở export dài, pool có thể bị chiếm hết.

### Cách giảm thời gian giữ connection

- Dùng pagination theo chunk và hoàn tất query mỗi trang trước khi chuyển sang bước chậm.
- Giới hạn kích thước export và thời gian sống của request.
- Tạo file export theo job nền rồi cho client tải file sau.
- Tránh gọi API bên ngoài trong lúc đang consume database Flux.
- Không mở transaction dài cho toàn bộ export nếu không cần snapshot transaction.
- Giới hạn số export đồng thời.

Nếu cần snapshot nhất quán xuyên nhiều trang, phải cân nhắc isolation/snapshot strategy của database. Chia trang giúp release connection giữa các query nhưng không tự bảo đảm mọi trang nhìn cùng một snapshot.

### Không collectList dữ liệu không giới hạn

collectList có thể làm query hoàn tất sau khi toàn bộ kết quả được nạp vào memory, từ đó release connection sớm hơn downstream xử lý, nhưng đổi lại tiêu tốn heap theo kích thước dataset. Với dữ liệu lớn, nên stream theo chunk hoặc ghi file theo job thay vì collectList toàn bộ.

## 9. Backpressure và concurrency có thể làm pool cạn

Reactive stream kiểm soát demand giữa publisher và subscriber, nhưng không tự giới hạn mọi loại concurrency trong ứng dụng.

Ví dụ:

~~~java
return requests.flatMap(
    request -> repository.save(toEntity(request))
);
~~~

Nếu không đặt concurrency, flatMap có thể cho phép nhiều publisher con hoạt động đồng thời theo mặc định của Reactor. Với nguồn phát nhanh, số thao tác chờ hoặc đang giữ connection có thể lớn hơn pool.

Giới hạn rõ:

~~~java
return requests.flatMap(
    request -> repository.save(toEntity(request)),
    8
);
~~~

Hoặc tuần tự:

~~~java
return requests.concatMap(
    request -> repository.save(toEntity(request))
);
~~~

Concurrency 8 không có nghĩa cần pool size đúng bằng 8 cho toàn hệ thống; nhiều request khác vẫn dùng pool. Hãy phối hợp giới hạn concurrency của từng pipeline với tổng request load, pool size và database capacity.

### Buffer không phải giới hạn toàn bộ hệ thống

buffer(500) giới hạn số phần tử trong một nhóm, nhưng nếu downstream dùng flatMap với concurrency lớn, nhiều nhóm có thể cùng tồn tại. Tính cả số chunk đồng thời, số phần tử mỗi chunk và các buffer nội bộ.

### Pool không phải queue vô hạn

Khi pool hết connection, các request acquire chờ trong queue. Nếu queue tăng không giới hạn, latency và memory có thể tăng trước khi timeout. Cần giới hạn concurrency/queue ở tầng ứng dụng và đặt acquire timeout phù hợp.

## 10. Blocking call có thể kéo dài thời gian giữ connection

Một ứng dụng reactive vẫn có thể bị block nếu gọi:

- block() hoặc blockFirst()/blockLast().
- JDBC/JdbcTemplate.
- File I/O blocking.
- HTTP client blocking.
- Thread.sleep().
- API bên thứ ba không reactive.

Nếu blocking diễn ra bên trong transaction, connection có thể bị giữ trong suốt thời gian thread bị block. Nếu blocking diễn ra trên event loop, nó còn làm chậm nhiều request khác.

Không gọi blocking API trên event-loop thread. Nếu phải tích hợp thư viện blocking, chuyển công việc sang scheduler phù hợp như boundedElastic và đặt giới hạn concurrency. Nhưng việc chuyển scheduler không tự giải phóng connection nếu code vẫn nằm trong transaction; phải thiết kế lại ranh giới transaction.

Ví dụ không nên:

~~~java
@Transactional
public Mono<Person> update(UUID id) {
    return repository.findById(id)
        .map(person -> {
            ExternalBlockingClient.call(); // giữ transaction/connection trong lúc block
            return person;
        })
        .flatMap(repository::save);
}
~~~

Tách lời gọi blocking khỏi transaction database nếu nghiệp vụ cho phép, và không chặn event loop.

## 11. Cancellation trong Reactor và R2DBC

Cancellation xảy ra khi subscriber không còn muốn nhận kết quả. Các tình huống thường gặp:

- Client HTTP đóng kết nối.
- WebFlux response bị hủy.
- Subscriber gọi dispose().
- take(n) đã nhận đủ phần tử và hủy upstream.
- timeout operator hủy publisher nguồn.
- Test dùng StepVerifier.thenCancel().
- Một pipeline cha bị hủy do request thất bại.

Cancellation là tín hiệu riêng, không phải onComplete và cũng không phải onError. Vì vậy, chỉ dùng doOnError không đủ để quan sát các thao tác bị hủy.

Có thể quan sát:

~~~java
return repository.findAll()
    .doOnCancel(() -> log.info("Repository stream cancelled"))
    .doFinally(signal -> log.debug("Stream ended: {}", signal));
~~~

doOnCancel giúp ghi nhận cancellation; doFinally nhận SignalType.CANCEL, ON_COMPLETE hoặc ON_ERROR. Callback quan sát không nên thực hiện cleanup bất đồng bộ thay cho resource management.

### Cancellation có dừng query ngay không?

Không thể khẳng định cancellation luôn dừng database statement tức thì. Kết quả phụ thuộc:

- R2DBC driver có hỗ trợ cancel statement tới mức nào.
- Database có cơ chế hủy query hay không.
- Query đang ở giai đoạn execute, fetch hay đang chờ network.
- Transaction manager đang xử lý rollback/cleanup ra sao.
- Driver cần bao lâu để xác nhận connection an toàn cho lần dùng tiếp theo.

Khi hủy một query, connection có thể cần cleanup hoặc rollback trước khi được trả về pool. Hãy đo usage duration sau cancellation và kiểm tra database session thay vì chỉ thấy publisher đã bị dispose rồi kết luận connection đã rảnh.

### Cancellation trong transaction

Nếu publisher thuộc reactive transaction do Spring quản lý, cancellation có thể dẫn tới rollback và cleanup theo semantics của transaction manager. Không để thao tác database chạy tách rời bằng subscribe riêng, vì nó không còn được điều khiển bởi cancellation và transaction của caller.

Với transaction quan trọng, kiểm tra behavior của Spring Framework, Spring Data và driver version bằng integration test. Không giả định cancel tương đương commit hoặc completion bình thường.

## 12. take(), timeout() và cancellation ngoài ý muốn

Một số operator hủy upstream khi điều kiện hoàn thành:

~~~java
repository.findAll().take(10);
~~~

Sau khi nhận 10 phần tử, take hủy upstream. Nếu repository đang stream kết quả từ một connection, driver và framework phải cleanup result/connection.

Tương tự:

~~~java
repository.findAll()
    .timeout(Duration.ofSeconds(5));
~~~

Nếu không phát tín hiệu đúng hạn, timeout phát lỗi và hủy nguồn upstream. Đây không chỉ là “báo lỗi cho client”; nó còn tạo cancellation cho publisher database.

### Cẩn thận với giới hạn trên Flux trong transaction

Nếu transaction bao quanh Flux và downstream dùng take(1), cancellation có thể làm transaction rollback theo behavior của reactive transaction manager. Điều đó có thể khiến test hoặc code bất ngờ không commit thao tác ghi.

Đối với write use case, thường nên hoàn tất transaction publisher một cách rõ ràng trước khi chuyển sang stream response. Không biến publisher ghi trong transaction thành một stream bị cắt tùy ý.

### Đừng dùng timeout làm cơ chế sửa leak

timeout giúp giới hạn thời gian chờ, nhưng nếu resource cleanup sai thì timeout có thể làm leak dễ xuất hiện hơn. Luôn xác nhận connection được release sau timeout/cancel.

## 13. Quản lý cancellation khi dùng resource thủ công

Nếu tự acquire connection, cleanup cần bao phủ complete, error và cancel. usingWhen được thiết kế cho resource có cleanup trả Publisher:

~~~java
Mono<Long> countPeople() {
    return Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeCount(connection),
        connection -> connection.close(),
        (connection, error) -> rollbackIfActive(connection)
            .onErrorResume(cleanupError -> Mono.empty())
            .then(connection.close()),
        connection -> rollbackIfActive(connection)
            .onErrorResume(cleanupError -> Mono.empty())
            .then(connection.close())
    );
}
~~~

Đây là skeleton minh họa. Trong code thực tế:

- Chỉ rollback khi transaction đã bắt đầu và còn active.
- Không che giấu cleanup error nếu hệ thống cần quan sát hoặc xử lý nó.
- Bảo đảm close được gọi đúng một lần theo lifecycle.
- Không dùng connection ngoài scope resource callback.
- Nếu dùng transaction manager của Spring, tránh tự quản lý một connection không được transaction manager bind.

Không gọi close rồi bỏ qua Publisher:

~~~java
connection.close(); // Publisher chưa được subscribe, cleanup có thể chưa chạy.
~~~

Phải compose cleanup publisher hoặc dùng resource abstraction phù hợp.

## 14. Timeout nên đặt ở nhiều tầng có chủ đích

Không có một timeout duy nhất xử lý mọi tình huống. Một request có thể chờ ở nhiều giai đoạn:

| Tầng | Timeout kiểm soát | Khi hết hạn |
| --- | --- | --- |
| Connection acquire | Chờ connection từ pool. | Báo acquire timeout. |
| Connection creation | Mở kết nối vật lý. | Connection creation thất bại. |
| Query/statement/database | Thời gian SQL được phép chạy. | Driver/database hủy hoặc báo lỗi theo hỗ trợ. |
| Transaction | Thời gian transaction. | Transaction manager/database có thể timeout/rollback. |
| Reactor publisher | Thời gian chờ tín hiệu từ publisher. | Phát TimeoutException và cancel upstream. |
| HTTP/request | Ngân sách toàn request. | Client/server kết thúc request và có thể cancel downstream. |

Các timeout cần phối hợp. Ví dụ HTTP timeout 3 giây nhưng acquire timeout 10 giây khiến request đã hết hạn trước khi pool báo lỗi. Query timeout 30 giây cũng không có ích nếu API chỉ cho phép 2 giây.

### Đặt timeout theo ngân sách

Một cách suy nghĩ:

- Request budget: tổng thời gian API có thể chạy.
- Acquire budget: chỉ chiếm một phần nhỏ của request budget.
- Query budget: phù hợp độ phức tạp và SLA của query.
- Transaction budget: đủ cho các thao tác database cần atomic nhưng ngắn hơn timeout request tổng thể nếu có thể.
- Cleanup budget: dành thời gian rollback/release sau lỗi hoặc cancel.

Timeout statement/database cụ thể phụ thuộc driver và database. Có thể cấu hình qua driver option, database statement timeout hoặc API hỗ trợ của driver. Không giả định mọi R2DBC driver có cùng property.

## 15. Retry có thể làm connection bị giữ lâu hơn

Retry với backoff có thể hữu ích cho lỗi transient. Nhưng vị trí retry rất quan trọng.

Nếu retry nằm bên trong một transaction đang giữ connection, thời gian backoff có thể kéo dài transaction và giữ connection trong khi chờ.

Không nên giữ một transaction mở qua nhiều lần chờ dài hoặc gọi lại hệ thống ngoài. Với lỗi cần retry toàn bộ transaction, thường nên đặt retry quanh publisher transaction để mỗi lần thử có transaction lifecycle riêng, đồng thời bảo đảm thao tác idempotent.

Ví dụ ý tưởng:

~~~java
Mono<Order> attempt =
    transactionalOperator.transactional(createOrderWork(command));

return attempt.retryWhen(
    Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientDatabaseFailure)
);
~~~

Đây là mẫu khái quát. Chỉ retry lỗi thực sự transient; không retry validation, unique conflict hoặc lỗi SQL cố định. Nếu transaction commit thành công nhưng response bị mất, retry có thể tạo duplicate; cần idempotency key hoặc unique business key.

## 16. Chẩn đoán connection leak có hệ thống

Khi pool cạn, đừng chỉ tăng max-size. Thu thập bằng chứng theo thứ tự:

1. Ghi lại active, idle, allocated và pending acquire.
2. Kiểm tra acquire latency và timeout count.
3. Xem connection usage duration theo percentile.
4. Correlate với query duration và transaction duration.
5. Kiểm tra database sessions, lock wait và idle-in-transaction.
6. Xác định endpoint/job có concurrency cao hoặc stream dài.
7. Tìm nơi tự acquire Connection hoặc gọi subscribe tách rời.
8. Kiểm tra cancellation, error và cleanup path.
9. Dùng load test tái hiện và quan sát pool có phục hồi sau khi tải dừng không.

### Dấu hiệu nghi ngờ resource leak

- Active connections tăng dần theo thời gian và không giảm.
- Pool cạn kể cả khi request rate đã trở về bình thường.
- Connection usage duration có tail rất dài.
- Database còn session idle hoặc idle in transaction.
- Lỗi tăng sau các request bị client hủy.
- Một endpoint cụ thể gây tăng active connection bất thường.

### Tìm code path thủ công

Tìm trong code các mẫu:

- ConnectionFactory.create().
- Connection.close() không được compose.
- usingWhen/usingWhen cleanup không bao phủ mọi path.
- subscribe() bên trong service/repository wrapper.
- block() trong reactive flow.
- @Transactional bao quanh HTTP/file/queue operation.
- Flux database trả trực tiếp cho client có tốc độ tiêu thụ không kiểm soát.
- flatMap không giới hạn trên nguồn lớn.
- retry/backoff nằm trong transaction dài.

Không phải mọi lần xuất hiện của các API trên đều là lỗi. Dùng chúng làm điểm bắt đầu để lần theo lifecycle và subscription.

## 17. Phân biệt query chậm, lock wait và connection bị giữ trong ứng dụng

Một connection active không nhất thiết đang chạy SQL. Database monitoring giúp phân biệt:

- Query đang active: xem query duration và execution plan.
- Query chờ lock: xem blocker/blocked session.
- Idle in transaction: ứng dụng đã mở transaction nhưng chưa commit/rollback.
- Idle: connection đang không chạy query; nếu pool báo acquired thì ứng dụng có thể đang giữ connection giữa hai thao tác.
- Không thấy session tương ứng: kiểm tra proxy/pool metrics, connection creation và thời điểm lấy mẫu.

Với PostgreSQL, có thể dùng pg_stat_activity và lock views để quan sát session, state, query start và wait event. Chỉ chạy query monitoring phù hợp quyền và môi trường; tránh log toàn bộ SQL có dữ liệu nhạy cảm.

Nếu database cho thấy session idle in transaction trong thời gian dài, tìm transaction boundary rộng hoặc code chờ I/O bên ngoài trong transaction.

## 18. Kiểm tra cancellation và cleanup bằng integration test

Dùng Testcontainers với database thật để kiểm tra connection được giải phóng sau cancellation. Test nên:

1. Tạo một query stream có nhiều hàng hoặc query đủ lâu.
2. Subscribe và yêu cầu một phần dữ liệu.
3. Hủy subscription.
4. Đợi cleanup hoàn tất trong thời gian giới hạn.
5. Thực hiện query mới hoặc kiểm tra pool metrics để xác nhận pool còn cấp connection.
6. Nếu query có transaction ghi, đọc lại để xác nhận rollback theo mong đợi.

Ví dụ StepVerifier:

~~~java
StepVerifier.create(repository.findAll())
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Test này xác nhận publisher có thể bị cancel và test không treo. Nó chưa tự chứng minh database query đã dừng hoặc connection đã được release. Bổ sung kiểm tra bằng một query mới, pool metrics hoặc trạng thái session database.

### Test pool nhỏ để lộ lỗi nhanh

Một test profile có pool max-size rất nhỏ, chẳng hạn 1 hoặc 2, có thể giúp phát hiện connection bị giữ. Nếu một test cố tình giữ connection rồi thao tác thứ hai acquire, nó có thể tái hiện acquire timeout.

Không dùng pool nhỏ như cấu hình production mặc định. Đây là kỹ thuật kiểm thử resource lifecycle.

### Test lỗi trong cleanup

Có thể ép query phát lỗi trong transaction rồi xác nhận connection vẫn được trả lại pool. Sau lỗi, chạy một query đơn giản khác. Nếu query tiếp theo không lấy được connection, kiểm tra rollback/close path.

## 19. Thiết kế pipeline chống pool exhaustion

Các nguyên tắc thiết kế:

- Dùng repository/DatabaseClient để framework quản lý connection.
- Giữ transaction chỉ bao quanh các thao tác database cần atomic.
- Không gọi HTTP, file I/O hoặc sleep trong transaction.
- Giới hạn concurrency của flatMap và các job ghi.
- Phân trang/chunk thay vì giữ một Flux database mở trong thời gian dài.
- Tránh N+1 query và query thiếu index.
- Đặt acquire timeout và request/query timeout phù hợp.
- Không gọi subscribe/block trong service reactive.
- Dùng usingWhen cho resource thủ công.
- Quan sát active, idle, pending, acquire time và usage time.
- Xác nhận cancellation/error đều dẫn tới cleanup.
- Tính tổng connection của tất cả replica và worker trước khi tăng pool.

### Backpressure ở đầu vào

Nếu API nhận stream request hoặc job đọc message liên tục, hãy kiểm soát số công việc đang ghi. Có thể dùng bounded concurrency, bounded queue hoặc rate limit theo khả năng database.

Không chuyển toàn bộ message vào một queue không giới hạn rồi để pool xử lý dần. Khi database chậm, backlog sẽ tăng và tiêu thụ memory.

### Tách workload

Read-heavy export, write-heavy ingestion và API latency-sensitive có thể cạnh tranh cùng pool. Tùy kiến trúc, có thể dùng pool/ConnectionFactory riêng cho workload đặc biệt hoặc giới hạn concurrency riêng. Việc tách pool không tăng capacity database; tổng số connection vẫn phải nằm trong budget của database.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Acquire timeout tăng | Pool hết connection hoặc connection creation chậm. | Xem active/pending, query duration và DB session. |
| Active luôn bằng max | Concurrency cao, transaction dài hoặc leak. | Tìm connection usage dài và request đang giữ. |
| Pool không phục hồi sau tải | Resource chưa release hoặc publisher không kết thúc. | Kiểm tra close/usingWhen/cancel path. |
| Database có idle-in-transaction | Transaction mở quá lâu. | Thu hẹp transaction và bỏ network call khỏi transaction. |
| API export làm pool cạn | Flux giữ connection khi client đọc chậm. | Chunk/page hoặc export job nền. |
| flatMap làm pending tăng | Nhiều save/query đồng thời hơn pool. | Giới hạn concurrency. |
| Tăng max-size nhưng latency xấu hơn | Database đã quá tải. | Giảm concurrency, tối ưu query/index. |
| Client cancel nhưng query vẫn chạy | Driver/database cancel chưa tức thì hoặc cancellation không truyền tới nguồn. | Kiểm tra driver, query cancellation và DB session. |
| Timeout nhưng connection không được trả | Cleanup transaction/resource có vấn đề hoặc driver đang cleanup. | Dùng resource lifecycle đúng và đo thời gian release. |
| Cleanup dùng doFinally nhưng không chạy | Close Publisher không được compose. | Dùng usingWhen hoặc framework resource API. |
| Retry làm pool cạn | Backoff trong transaction hoặc retry concurrency cao. | Retry quanh transaction, giới hạn retry và idempotency. |
| Pool tạo connection thất bại | DB limit, network/TLS/DNS hoặc credentials. | Kiểm tra connection creation metrics và server logs. |

## 21. Quy trình xử lý sự cố pool cạn

Khi production báo acquire timeout, thực hiện theo thứ tự:

1. **Xác nhận phạm vi:** một instance hay tất cả replica; một endpoint hay toàn hệ thống.
2. **Đọc pool metrics:** active, idle, pending, allocated, acquire duration và timeout.
3. **Đọc database state:** query active, lock wait, idle-in-transaction, số session và giới hạn connection.
4. **So sánh latency:** query duration, transaction duration và connection usage duration.
5. **Tìm workload gây giữ connection:** export, import, transaction dài, flatMap concurrency, retry hoặc blocking call.
6. **Kiểm tra cancellation:** client disconnect, timeout và cleanup sau cancel.
7. **Kiểm tra resource thủ công:** ConnectionFactory.create/close và usingWhen.
8. **Giảm tải an toàn:** giới hạn concurrency hoặc tạm dừng job nền nếu database quá tải.
9. **Sửa nguyên nhân gốc:** tối ưu query, thu hẹp transaction, sửa lifecycle hoặc chia chunk.
10. **Đánh giá pool size:** chỉ tăng khi database còn capacity và số connection tổng vẫn trong budget.
11. **Load test lại:** xác nhận active giảm, pending không tích tụ và pool phục hồi sau burst.
12. **Đặt cảnh báo:** acquire timeout, pending duration, usage duration và DB lock wait.

Không restart ứng dụng như cách xử lý duy nhất nếu chưa tìm nguyên nhân. Restart có thể giải phóng connection đang bị giữ nhưng không sửa bug; tình trạng sẽ quay lại dưới cùng workload.

## 22. Quy trình load test và xác nhận phục hồi

Một load test hữu ích không chỉ đo throughput lúc tải ổn định. Nó cần kiểm tra cả khả năng phục hồi sau burst và cancellation.

Thiết kế kịch bản:

- Warm up để pool và database ổn định.
- Tăng request rate theo từng mức.
- Giữ tải đủ lâu để quan sát pending/acquire.
- Tạo một đợt burst cao hơn capacity dự kiến.
- Hủy một phần request/stream.
- Giảm tải về mức bình thường.
- Quan sát active, idle và pending có phục hồi không.
- Kiểm tra database không còn transaction/session bị bỏ quên.
- Xác nhận không có dữ liệu ghi dở hoặc duplicate do retry.

Chỉ số cần so sánh trước/sau thay đổi:

- Throughput.
- p95/p99 request latency.
- Acquire wait và timeout rate.
- Connection usage duration.
- Active/pending theo thời gian.
- Database CPU, I/O và lock wait.
- Số request bị cancel và thời gian cleanup.
- Tỷ lệ lỗi và retry.

Một cấu hình tốt phải vừa đáp ứng tải vừa phục hồi sau burst. Nếu throughput cao nhưng pool không bao giờ trở lại trạng thái idle sau khi tải dừng, cần điều tra lifecycle.

## 23. Checklist chẩn đoán nhanh

| Câu hỏi | Nếu câu trả lời là có |
| --- | --- |
| Active connection chạm max và pending tăng? | Pool saturation đang xảy ra; tìm workload giữ connection. |
| Pending tăng nhưng active thấp hơn max? | Kiểm tra connection creation, validation và DB session limit. |
| Connection usage duration dài hơn query duration nhiều? | Ứng dụng giữ connection ngoài thời gian SQL, có thể do transaction/downstream. |
| Có idle-in-transaction? | Transaction boundary có thể quá rộng hoặc flow bị chờ. |
| Một endpoint stream chậm làm pool cạn? | Cân nhắc paging, chunking hoặc export job. |
| Có flatMap không giới hạn? | Giới hạn concurrency và queue. |
| Có block/JDBC trong reactive flow? | Tách blocking work và tránh giữ transaction trong lúc block. |
| Có tự acquire connection? | Kiểm tra close/usingWhen trên complete/error/cancel. |
| Client cancel nhưng active không giảm? | Kiểm tra driver cancellation, transaction rollback và DB session. |
| Tăng pool khiến DB latency tăng? | Giảm concurrency và tối ưu database thay vì tăng connection. |

## 24. Quy trình triển khai bền vững

Để giảm nguy cơ cạn pool trong Spring Data Relational R2DBC:

1. **Chọn pool có giới hạn:** xác định max-size và timeout theo capacity database.
2. **Tính tổng connection:** nhân theo số replica và cộng background/migration/admin clients.
3. **Đo thời gian giữ connection:** phân biệt query duration với transaction/usage duration.
4. **Giữ transaction ngắn:** không chờ HTTP, file, message hoặc user trong transaction.
5. **Giới hạn concurrency:** phối hợp flatMap, batch job và pool.
6. **Thiết kế stream có giới hạn:** paging/chunk khi downstream có thể chậm.
7. **Quản lý resource thủ công:** usingWhen và cleanup trên complete/error/cancel.
8. **Thiết lập timeout theo tầng:** acquire, query, transaction, Reactor và HTTP.
9. **Quan sát cancellation:** đo cancel count và thời gian connection được release.
10. **Kiểm thử với database thật:** dùng Testcontainers, StepVerifier và pool nhỏ để tái hiện.
11. **Load test có burst:** xác nhận pool phục hồi sau khi tải giảm.
12. **Cảnh báo theo xu hướng:** pending acquire, active/max, usage duration và DB lock/session.

Pool cạn là tín hiệu rằng connection đang được yêu cầu nhiều hơn khả năng cấp tại thời điểm đó. Cách xử lý đúng bắt đầu từ việc đo thời gian acquire và thời gian giữ connection, sau đó phân biệt query chậm, transaction dài, downstream chậm, concurrency quá cao và resource leak. Cancellation phải được theo dõi như một đường kết thúc riêng: nó có thể hủy publisher nhưng việc dừng query và trả connection còn phụ thuộc driver, transaction manager và cleanup. Khi transaction ngắn, concurrency có giới hạn, stream có backpressure, resource được quản lý đúng và pool size phù hợp với database capacity, ứng dụng R2DBC sẽ ổn định hơn dưới tải và phục hồi tốt hơn sau lỗi hoặc request bị hủy.
